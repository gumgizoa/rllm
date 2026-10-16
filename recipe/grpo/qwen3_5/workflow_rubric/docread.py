"""Which workflow documents reached the agent, at which step, and how much of each.

The AI-DLC reward counted a read when a command *named* the document: ``cat rule-details/*.md``,
``for f in ...; do cat $f; done``, a relative path after ``cd``, ``cp -r /ai-dlc /tmp/x`` and
``find ... -exec cat {} +`` all escaped it, while ``echo /ai-dlc/...`` counted (audit loophole
[5]). A document reaches the agent through an observation, so that is where a read is decided:

* **fingerprints** -- distinctive lines of each document (>= 24 characters, not fence lines, not
  shared with the workflow's other documents; prose before fenced template/example lines, since
  the agent copies those into its own artifacts), spread over head, middle and tail;
* **command reads** -- a reading verb / editor view whose target resolves (cwd, globs, loops,
  find, xargs) to the document's container path; its coverage is the share of fingerprints in
  that call's own observation. A call whose observation is non-empty but shows none of the
  document (``grep`` that matched elsewhere, ``cat doc > copy``) did not read it; the final call,
  whose observation never returned, reads with coverage 0;
* **fingerprint reads** -- any step whose observations carry >= ``FINGERPRINT_MIN`` of a
  document's fingerprints, whatever the tool or path.

Text the agent itself typed (commands, editor text) is removed from observations before matching,
so echoing a heredoc or viewing an artifact the agent filled with copied lines is not a read.
A step whose observations carry two or more stage documents (each >= ``FINGERPRINT_MIN``) is a
*multi-read* step (AI-DLC "Load one file at a time").
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from .context import DocRead
from .trace import shell
from .trace.model import Action, Run

Split = Callable[[str, "str | None"], tuple[list[shell.Segment], "str | None"]]

K = 16  # fingerprints per document
MIN_CHARS = 24  # a fingerprint line's length after whitespace normalisation
FALLBACK_CHARS = 12  # used when a document has too few lines of MIN_CHARS
FINGERPRINT_MIN = 0.2  # coverage for a fingerprint-only read and for multi-read

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][A-Za-z0-9]|\r")
_WS = re.compile(r"\s+")
_FENCE = re.compile(r"^\s*(```|~~~)")
_BORING = re.compile(r"^[\s|:\-=*_#>+.`~]*$")  # table rules, horizontal rules, bare markup
_PROMPT = re.compile(r"^\s*>\s?")  # bash's continuation prompt in front of an echoed heredoc line
_PREFIX = re.compile(r"^\s*\d+\t|^\s*\d+[:-]|^[^\s:]+:\d+[:-]|^\s*\d+\s{2,}")  # cat -n / editor view, grep -n, grep -rn, nl
_PLAIN_READERS = frozenset({"cat", "tac", "head", "tail", "less", "more", "nl", "bat", "batcat", "sed", "awk", "gawk", "sort", "uniq", "strings"})


def _key(line: str) -> str:
    return _WS.sub("", line)


def _norm(line: str) -> str:
    return _WS.sub(" ", line).strip()


def fingerprints(text: str | None, k: int = K, others: Iterable[str | None] = ()) -> list[str]:
    """Up to ``k`` distinctive normalised lines of ``text``, spread across it.

    Lines shorter than :data:`MIN_CHARS` (after collapsing whitespace), fence and rule lines, lines
    repeated in the document and lines any of ``others`` (the workflow's other documents) also
    holds are skipped. Prose lines come first; lines inside fenced blocks (templates, examples)
    fill up only when the prose has fewer than ``k``.
    """
    if not text:
        return []
    shared = {_key(ln) for t in others if t for ln in t.splitlines() if ln.strip()}
    for floor in (MIN_CHARS, FALLBACK_CHARS):
        prose, fenced, seen, dup = [], [], set(), set()
        inside = False
        for line in text.splitlines():
            if _FENCE.match(line):
                inside = not inside
                continue
            n = _norm(line)
            if len(n) < floor or _BORING.match(n):
                continue
            key = _key(n)
            if key in shared:
                continue
            if key in seen:
                dup.add(key)
                continue
            seen.add(key)
            (fenced if inside else prose).append(n)
        prose = [n for n in prose if _key(n) not in dup]
        fenced = [n for n in fenced if _key(n) not in dup]
        if len(prose) + len(fenced) >= min(3, k) or floor == FALLBACK_CHARS:
            break
    picked = _spread(prose, k)
    if len(picked) < k:
        picked += _spread(fenced, k - len(picked))
    return picked


def _spread(lines: list[str], k: int) -> list[str]:
    if k <= 0 or not lines:
        return []
    if len(lines) <= k:
        return list(lines)
    if k == 1:
        return [lines[len(lines) // 2]]
    idx = sorted({round(i * (len(lines) - 1) / (k - 1)) for i in range(k)})
    return [lines[i] for i in idx]


@dataclass
class Scan:
    """Everything :func:`scan` learns; :func:`reads` returns its first two fields.

    hits          (doc, step) -> indices of that doc's fingerprints seen in the step's observations
    action_docs   (step, action index) -> docs that action read (command read, or its own
                  observation carries >= FINGERPRINT_MIN of the doc)
    fps           doc -> its fingerprints
    """

    reads: dict[str, list[DocRead]] = field(default_factory=dict)
    multi: set[int] = field(default_factory=set)
    hits: dict[tuple[str, int], set[int]] = field(default_factory=dict)
    action_docs: dict[tuple[int, int], set[str]] = field(default_factory=dict)
    fps: dict[str, list[str]] = field(default_factory=dict)


def _typed(a: Action) -> set[str]:
    """Whitespace-free lines of everything the agent typed in this action."""
    out: set[str] = set()
    for t in (a.command, a.text, a.old):
        if isinstance(t, str) and t:
            out.update(k for k in (_key(ln) for ln in t.splitlines()) if k)
    return out


def visible(observation: str, own: set[str]) -> str:
    """The observation as whitespace-free text, without lines that repeat what the agent typed."""
    if not observation:
        return ""
    kept = []
    for line in _ANSI.sub("", observation).splitlines():
        whole = _key(line)
        if not whole:
            continue
        body = _PREFIX.sub("", line, count=1)
        if whole in own or _key(body) in own or _key(_PROMPT.sub("", body, count=1)) in own:
            continue
        kept.append(whole)
    return "".join(kept)


def _hits(keys: list[str], vis: str) -> set[int]:
    return {i for i, k in enumerate(keys) if k in vis} if vis else set()


def _cmd_targets(a: Action, cwd: str | None, known: list[str], split: Split) -> list[tuple[str, bool]]:
    """(path, stdout visible) for every file this action reads by command."""
    if a.kind == "view" and a.path:
        return [(shell.resolve(a.path, cwd), True)]
    if a.kind != "shell" or not a.command:
        return []
    out: list[tuple[str, bool]] = []
    segs = shell.flat(split(a.command, cwd)[0])
    for i, seg in enumerate(segs):
        targets = shell.read_targets(seg, known)
        if not targets:
            continue
        shown = not any(op in (">", ">>", "&>", "&>>") for op, _ in seg.redirects)
        nxt = segs[i + 1] if i + 1 < len(segs) else None
        if nxt is not None and nxt.op_before == "|" and any(op in (">", ">>", "&>", "&>>") for op, _ in nxt.redirects):
            shown = False
        plain = seg.verb in _PLAIN_READERS or (seg.verb or "").startswith("python")
        out.extend((p, shown and plain) for p in targets)
    return out


def scan(
    run: Run,
    docs: Mapping[str, tuple[str, str | None]],
    cwd_track: Mapping[tuple[int, int], str | None],
    *,
    stage_docs: Iterable[str] | None = None,
    split: Split = shell.split,
    others: Iterable[str | None] = (),
    k: int = K,
    fps: Mapping[str, list[str]] | None = None,
) -> Scan:
    """Doc reads of ``run``. ``docs``: source id -> (container path, text or None when unknown).

    ``stage_docs``: the ids that count for multi-read (default: all). ``others``: further texts of
    the workflow (templates without a container path ...) whose lines are not distinctive.
    ``fps``: fingerprints computed beforehand (they depend on the documents only).
    """
    out = Scan()
    texts = {sid: t for sid, (_, t) in docs.items()}
    extra = list(others)
    for sid, t in texts.items():
        out.fps[sid] = list(fps[sid]) if fps is not None and sid in fps else fingerprints(t, k, [o for s2, o in texts.items() if s2 != sid] + extra)
    keys = {sid: [_key(x) for x in fp] for sid, fp in out.fps.items()}
    by_path: dict[str, list[str]] = {}
    for sid, (cp, _) in docs.items():
        if cp:
            by_path.setdefault(posixpath.normpath(cp), []).append(sid)
    known = sorted(by_path)
    stage = set(docs) if stage_docs is None else set(stage_docs)
    own: set[str] = set()
    for step in run.steps:
        n = step.n
        step_hits: dict[str, set[int]] = {sid: set() for sid in docs}
        cmd_read: dict[str, DocRead] = {}
        for idx, a in enumerate(step.actions):
            own |= _typed(a)
            vis = visible(a.observation, own)
            act = {sid: _hits(keys[sid], vis) for sid in out.fps} if vis else {}
            for sid, h in act.items():
                step_hits[sid] |= h
            mine = out.action_docs.setdefault((n, idx), set())
            for sid, h in act.items():
                fp = out.fps[sid]
                if fp and len(h) / len(fp) >= FINGERPRINT_MIN:
                    mine.add(sid)
            for path, shown in _cmd_targets(a, cwd_track.get((n, idx)), known, split):
                for sid in by_path.get(posixpath.normpath(path), []):
                    fp = out.fps[sid]
                    h = act.get(sid, set())
                    if fp:
                        cov = len(h) / len(fp)
                        ok = cov > 0 or (not (a.observation or "").strip() and shown)
                    else:
                        cov = 1.0 if vis else 0.0
                        ok = bool(vis) or (not (a.observation or "").strip() and shown)
                    if not ok:
                        continue
                    mine.add(sid)
                    if sid not in cmd_read:
                        cmd_read[sid] = DocRead(sid, n, "command", cov)
                        out.reads.setdefault(sid, []).append(cmd_read[sid])
                    cmd_read[sid].coverage = max(cmd_read[sid].coverage, cov)
            if not mine:
                out.action_docs.pop((n, idx))
        strong = 0
        for sid in docs:
            fp = out.fps[sid]
            h = step_hits[sid]
            if h:
                out.hits[(sid, n)] = h
            cov = len(h) / len(fp) if fp else 0.0
            if sid not in cmd_read and cov >= FINGERPRINT_MIN:
                out.reads.setdefault(sid, []).append(DocRead(sid, n, "fingerprint", cov))
            if sid in stage and (cov >= FINGERPRINT_MIN or (not fp and sid in cmd_read and cmd_read[sid].coverage > 0)):
                strong += 1
        if strong >= 2:
            out.multi.add(n)
    return out


def reads(
    run: Run,
    docs: Mapping[str, tuple[str, str | None]],
    cwd_track: Mapping[tuple[int, int], str | None],
    **kw,
) -> tuple[dict[str, list[DocRead]], set[int]]:
    """(source id -> reads in step order, multi-read steps); see :func:`scan` for the keywords."""
    s = scan(run, docs, cwd_track, **kw)
    return s.reads, s.multi


def multi_read(hits: Mapping[tuple[str, int], set[int]], fps: Mapping[str, list[str]], stage_docs: Iterable[str], threshold: float = FINGERPRINT_MIN) -> set[int]:
    """Steps whose observations carry >= ``threshold`` of two or more of ``stage_docs``."""
    count: dict[int, int] = {}
    stage = set(stage_docs)
    for (sid, step), h in hits.items():
        fp = fps.get(sid) or []
        if sid in stage and fp and len(h) / len(fp) >= threshold:
            count[step] = count.get(step, 0) + 1
    return {s for s, c in count.items() if c >= 2}


def union_coverage(hits: Mapping[tuple[str, int], set[int]], fps: Mapping[str, list[str]], doc: str, steps: Iterable[int]) -> float:
    """Share of ``doc``'s fingerprints seen over ``steps`` together (a document read in chunks)."""
    fp = fps.get(doc) or []
    if not fp:
        return 0.0
    seen: set[int] = set()
    for s in steps:
        seen |= hits.get((doc, s), set())
    return len(seen) / len(fp)


__all__ = ["K", "FINGERPRINT_MIN", "Scan", "fingerprints", "visible", "scan", "reads", "multi_read", "union_coverage"]
