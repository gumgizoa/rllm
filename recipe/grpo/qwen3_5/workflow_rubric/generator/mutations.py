"""G9 mutations: the ways a run can game a workflow rubric, and harmless ways an honest run can differ.

The self-test (:mod:`.selftest`, DESIGN §10 G9) scores a rubric on a synthetic honest run -- the
workflow's golden, ``workflows/<wf>/selftest_golden.py`` -- and on variants of it built here. Each
mutation is a function ``(run, collected, rubric, *, env=None) -> (run, collected) | None`` that
returns modified copies, or None when the run has nothing it applies to (no checkbox artifacts, no
archive move, no test run before the first repo edit, ...).

What an exploit is comes from the documents, never from the rubric's items: the template skeletons
say which values are placeholders, which offer a none alternative and which are literal output; the
trace says which commands ran, which tests passed and which documents were read. The rubric is used
only to locate things -- the stage documents, the artifact locations and roots -- through the same
:func:`..facts.build` the engine uses. So a requirement the rubric does not check shows up as an
exploit it does not catch, instead of being silently skipped.

Generic over workflows: artifacts are rewritten through their write actions (an editor ``create`` or
a shell write; later content writes of the same artifact are dropped and the final text is set in
``Collected``), fields are found by their template shape (``- Label: value``, ``- R1: value``, plain
list items, per section), and test runs are the engine's own :class:`~..context.RunFact` records.
:func:`simulate` stands in for the online collector (``collect.py``) when a golden or a mutation
changes what the sandbox would hold: the diff against BASE_SHA and the base-tree answers follow from
the replayed trace and the golden's ``base_tree`` (kept in ``Run.meta["selftest"]``).
"""

from __future__ import annotations

import copy
import posixpath
import re
import shlex
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .. import collect as CL
from .. import evidence as E
from .. import facts as F
from .. import markdown as M
from ..context import Collected, Facts, RunFact
from ..refs import norm_command, norm_path
from ..replay import replay
from ..schema import Rubric
from ..trace.model import Action, Run, Step

CONTENT_OPS = frozenset({"create", "overwrite", "append", "edit", "unknown"})
NOT_APPLICABLE = "not applicable (no reason)"
DUMMY_DIR = "/tmp/dummy_tests"
CONFIG_FILES = ("tox.ini", "setup.cfg", "pytest.ini", "pyproject.toml", "package.json", "Makefile")
_EOF = "WFR_SELFTEST_EOF"
# A local exploit (one field, one run, one read) must lower compliance at least this much: about half
# of one failed must item in a 15-item stage of a 7-signal rubric -- the rubric notices, it does not tie.
MIN_DROP = 0.005
# An exploit only an agent-written relation can see (both sides written by the agent: DESIGN P6 keeps such a cross_ref
# at should, weight 0.25) is noticed at the same scale: about half of one failed should item.
SHOULD_DROP = MIN_DROP * 0.25


# ============================================================================================
# The online collector, simulated
# ============================================================================================
def _parents(paths: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for p in paths:
        d = posixpath.dirname(p)
        while d and d != "/" and d not in out:
            out.add(d)
            d = posixpath.dirname(d)
    return out


def _under(path: str, dirs: Iterable[str]) -> bool:
    return any(path == d or path.startswith(d.rstrip("/") + "/") for d in dirs)


def _diff(run: Run, workdir: str, base_tree: set[str]) -> dict[str, str]:
    """``git diff --name-status BASE_SHA`` + untracked, as the replayed trace implies it."""
    rep = replay(run, workdir)
    pre = workdir.rstrip("/") + "/"
    out: dict[str, str] = {}
    for path, evs in rep.writes.items():
        if not path.startswith(pre):
            continue
        rel = path[len(pre) :]
        if rel == ".git" or rel.startswith(".git/"):
            continue
        ok = [e for e in evs if e.ok is not False]
        if not ok:
            continue
        exists = ok[-1].op not in ("delete", "move_out")
        if rel in base_tree:
            out[rel] = "M" if exists else "D"
        elif exists:
            out[rel] = "?"
    return out


def _base_present(run: Run, files: dict[str, str], workdir: str, base_tree: set[str], diff: dict[str, str]) -> dict[str, bool]:
    """What collect.py's ``git ls-tree`` query answers for the paths the run and the artifacts mention."""
    dirs = _parents(f"/{p}" for p in base_tree)
    base_dirs = {d.lstrip("/") for d in dirs}
    out: dict[str, bool] = {}
    for p in CL.candidate_paths(run, files, workdir):
        q = p.rstrip("/")
        out[p] = q in base_tree or q in base_dirs
    for p, st in diff.items():
        out[p] = st in ("M", "D")
    for p in [p for p, ok in out.items() if ok]:
        for d in _parents([f"/{p}"]):
            out[d.lstrip("/")] = True
    return out


def simulate(
    run: Run,
    *,
    workdir: str,
    base_sha: str,
    base_tree: Iterable[str],
    artifact_dirs: Iterable[str],
    files: dict[str, str] | None = None,
    base_files: dict[str, str] | None = None,
    pre_status: str = "",
    opaque_commands: bool = False,
) -> Collected:
    """The online ``Collected`` for ``run``: files under ``artifact_dirs`` (the replayed final content
    unless ``files`` is given), their directories, the diff and the base-tree answers.

    The arguments are kept in ``run.meta["selftest"]`` so :func:`refresh` can redo this after a
    mutation changed the trace (``base_files``: repo file texts a mutation may show, e.g. a config file).
    ``opaque_commands``: ``files`` holds what commands the replay cannot follow made (a CLI that moves the
    artifacts, openspec_ff's ``openspec archive``), so a replayed directory none of whose files the sandbox
    holds is gone (:func:`_live_dirs`), as the online collector, which lists the sandbox, would see it.
    """
    base = set(base_tree)
    arts = [posixpath.normpath(d) for d in artifact_dirs]
    rep = replay(run, workdir)
    if files is None:
        files = {p: t for p, t in rep.final.items() if t is not None and _under(p, arts)}
    run.meta["selftest"] = {"workdir": workdir, "base_sha": base_sha, "base_tree": sorted(base), "artifact_dirs": arts, "pre_status": pre_status, "base_files": dict(base_files or {})}
    if opaque_commands:
        run.meta["selftest"]["opaque_commands"] = True
    col = Collected(files=dict(files), workdir=workdir, base_sha=base_sha, pre_status=pre_status, mode="online")
    _fill(run, col, rep)
    return col


def _live_dirs(rep, files: Iterable[str], arts: Iterable[str]) -> set[str]:
    """The replay's directories under ``arts`` that the sandbox still has, when commands the replay cannot follow
    made the sandbox (``simulate(opaque_commands=True)``): a directory whose replayed files the sandbox holds none of
    was moved or removed by such a command (openspec_ff: ``openspec archive`` moves the change)."""
    held = set(files)
    inside: dict[str, bool] = {}
    for p, t in rep.final.items():
        if t is None:
            continue
        d = posixpath.dirname(p)
        while d and d != "/":
            inside[d] = inside.get(d, False) or p in held
            d = posixpath.dirname(d)
    return {d for d in rep.dirs if _under(d, arts) and inside.get(d, True)}


def _fill(run: Run, col: Collected, rep=None) -> None:
    meta = run.meta.get("selftest") or {}
    arts = meta.get("artifact_dirs") or []
    if rep is None:
        rep = replay(run, col.workdir or "/")
    dirs = _live_dirs(rep, col.files, arts) if meta.get("opaque_commands") else {d for d in rep.dirs if _under(d, arts)}
    col.dirs = dirs | _parents(col.files)
    if meta.get("base_tree") is not None and col.workdir:
        base = set(meta["base_tree"])
        col.diff = _diff(run, col.workdir, base)
        col.base_present = _base_present(run, col.files, col.workdir, base, col.diff)


def refresh(run: Run, col: Collected) -> tuple[Run, Collected]:
    """Recompute the directories, diff and base-tree answers after the trace or the files changed."""
    _fill(run, col)
    return run, col


# ============================================================================================
# Documents and skeletons
# ============================================================================================
@dataclass
class Env:
    """What mutations may read besides the run: document texts and each artifact's template skeleton.

    docs        source id -> text (from the manifest, the rubric's package, or the run's own reads)
    skeletons   artifact id -> the skeleton the documents prescribe (template block or file)
    """

    docs: dict[str, str] = field(default_factory=dict)
    skeletons: dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(cls, rubric: Rubric, run: Run | None = None, manifest=None, cfg=None) -> Env:
        env = cls()
        for s in rubric.sources:
            text = None
            if manifest is not None:
                e = manifest.by_id(s.id)
                if e is not None:
                    text = "\n".join(e.lines()) + "\n"
            if text is None:
                text = _package_text(rubric, s.path)
            if text is not None:
                env.docs[s.id] = text
        if run is not None:
            for sid, text in _read_texts(rubric, run).items():
                env.docs.setdefault(sid, text)
        exact = _cfg_skeletons(rubric, manifest, cfg) if manifest is not None and cfg is not None else {}
        for aid, art in rubric.artifacts.items():
            if aid in exact:
                env.skeletons[aid] = exact[aid]
            elif art.template and art.template in env.docs:
                whole = next((s.role == "template" for s in rubric.sources if s.id == art.template), False)
                sk = env.docs[art.template] if whole else guess_skeleton(env.docs[art.template])
                if sk:
                    env.skeletons[aid] = sk
        return env


def _package_text(rubric: Rubric, rel: str) -> str | None:
    if rubric.path is None or not rel:
        return None
    try:
        return (Path(rubric.path).parent.parent / rel).resolve().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _read_texts(rubric: Rubric, run: Run) -> dict[str, str]:
    """Source id -> text, from the observations of plain ``cat <container path>`` reads in the run."""
    by_path = {s.container_path: s.id for s in rubric.sources if s.container_path}
    out: dict[str, str] = {}
    for st in run.steps:
        for a in st.actions:
            if a.kind == "shell" and a.command and a.observation:
                words = a.command.split()
                if len(words) == 2 and words[0] == "cat" and words[1] in by_path:
                    out.setdefault(by_path[words[1]], a.observation)
    return out


def _cfg_skeletons(rubric: Rubric, manifest, cfg) -> dict[str, str]:
    from .templates import skeleton

    out: dict[str, str] = {}
    for ts in getattr(cfg, "templates", []) or []:
        entry = manifest.resolve(ts.path)
        if entry is None:
            continue
        aid = ts.artifact or next((a for a, art in rubric.artifacts.items() if art.template == entry.id), None)
        if aid and aid in rubric.artifacts and aid not in out:
            lines = skeleton(entry, ts)
            if lines:
                out[aid] = "\n".join(t for _, t in lines) + "\n"
    return out


_FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)")


def guess_skeleton(text: str) -> str | None:
    """The fenced block of a rule document that looks most like an artifact (frontmatter, headings,
    label lines), or the whole document when it has no fenced block. Used without a generator config;
    with one, the config's ``templates[].block`` picks the block exactly."""
    lines = text.splitlines()
    blocks: list[list[str]] = []
    cur: list[str] | None = None
    fence = ""
    for ln in lines:
        m = _FENCE.match(ln)
        if cur is None and m:
            cur, fence = [], m.group(1)
            continue
        if cur is not None and ln.strip().startswith(fence) and ln.strip().strip(fence[0]) == "":
            blocks.append(cur)
            cur = None
            continue
        if cur is not None:
            cur.append(ln)
    if not blocks:
        return text

    def score(b: list[str]) -> int:
        heads = sum(1 for x in b if re.match(r"^#{1,6}\s", x))
        labels = sum(1 for x in b if _FIELD.match(x))
        return heads * 3 + labels + (5 if b and b[0].strip() == "---" else 0)

    best = max(blocks, key=score)
    return "\n".join(best) + "\n" if score(best) > 0 else None


# ============================================================================================
# Fields of a markdown artifact, by template shape
# ============================================================================================
_HEAD = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_FIELD = re.compile(
    r"^(?P<lead>[ \t]*(?:[-*+]|\d{1,3}[.)])[ \t]+)(?P<box>\[[ xX]\][ \t]+)?"
    r"(?P<b1>\*\*|__)?(?P<key>[A-Za-z][\w /&()'.,\[\]-]{0,60}?)(?P<b2>\*\*|__)?[ \t]*:(?P<b3>\*\*|__)?(?:[ \t]+(?P<value>.*)|[ \t]*$)"
)
# a bold label opening a line without a list marker (spec-kit plan: ``**Language/Version**: Python 3.11``)
_BOLD_FIELD = re.compile(r"^(?P<lead>[ \t]*)(?P<box>)(?P<b1>\*\*|__)(?P<key>[A-Za-z][\w /&()'.,\[\]-]{0,60}?)(?:(?P<b2>\*\*|__)[ \t]*:(?P<b3>)|[ \t]*:(?P<b3b>\*\*|__))(?:[ \t]+(?P<value>.*)|[ \t]*$)")
_ITEM = re.compile(r"^(?P<lead>[ \t]*(?:[-*+]|\d{1,3}[.)])[ \t]+)(?P<box>\[[ xX]\][ \t]+)?(?P<value>.*)$")
_ID_KEY = re.compile(r"[A-Z]{1,5}-?\d+|[A-Za-z]+[ -]?\d+(?:\.\d+)*(?:\s*\[[^\]]*\])*")  # R1, FR-001, Step 2 [R1, R4]
_GROUP = re.compile(r"\[([^\[\]\n]*)\]|<([^<>\n]*)>|\{([^{}\n]*)\}")
DROP = object()


@dataclass
class Fld:
    """One field line (with its continuation lines): ``- Label: value``, ``- R1: value``, a bold label opening a
    line without a list marker (``**Label**: value``) or a plain item."""

    start: int
    end: int  # exclusive
    section: str
    kind: str  # label | id | item
    key: str | None
    value: str  # inline value and continuation lines, joined with newlines
    lead: str
    box: str = ""
    b1: str = ""
    b2: str = ""
    b3: str = ""

    @property
    def shape(self) -> tuple[str, str, str | None]:
        return (_shape(self.section), self.kind, _shape(self.key) if self.key else None)

    @property
    def indent(self) -> int:
        return len(self.lead) - len(self.lead.lstrip())


def _shape(s: str | None) -> str:
    s = (s or "").replace("**", "").replace("__", "").replace("`", "").lower()
    s = re.sub(r"\[[^\]]*\]", "[]", s)
    s = re.sub(r"\d+", "#", s)
    return re.sub(r"\s+", " ", s).strip(" :")


def _fm_end(lines: list[str]) -> int:
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                return j + 1
    return 0


def parse_fields(text: str) -> list[Fld]:
    """Every field line of ``text`` outside the frontmatter and fenced blocks, in order."""
    lines = text.split("\n")
    out: list[Fld] = []
    section = ""
    i = _fm_end(lines)
    inside = None
    while i < len(lines):
        ln = lines[i]
        fm = _FENCE.match(ln)
        if fm and (inside is None or ln.strip().startswith(inside)):
            inside = None if inside else fm.group(1)
            i += 1
            continue
        if inside:
            i += 1
            continue
        h = _HEAD.match(ln)
        if h:
            section = h.group(2)
            i += 1
            continue
        m = _FIELD.match(ln) or _BOLD_FIELD.match(ln)
        mi = None if m else _ITEM.match(ln)
        if not m and not mi:
            i += 1
            continue
        lead = (m or mi).group("lead")
        ind = len(lead) - len(lead.lstrip())
        j = i + 1
        cont: list[str] = []
        while j < len(lines) and lines[j].strip() and not _HEAD.match(lines[j]) and (len(lines[j]) - len(lines[j].lstrip())) > ind:
            cont.append(M.strip_list_marker(lines[j]).strip())
            j += 1
        if m:
            key = m.group("key").strip()
            kind = "id" if _ID_KEY.fullmatch(key) else "label"
            value = "\n".join([x for x in [(m.group("value") or "").strip(), *cont] if x])
            b3 = m.group("b3") or (m.groupdict().get("b3b") or "")
            out.append(Fld(i, j, section, kind, key, value, lead, m.group("box") or "", m.group("b1") or "", m.group("b2") or "", b3))
        else:
            value = "\n".join([mi.group("value").strip(), *cont])
            out.append(Fld(i, j, section, "item", None, value, lead, mi.group("box") or ""))
        i = j
    return out


def _render(f: Fld, value: str) -> str:
    if f.kind == "item":
        return f"{f.lead}{f.box}{value}"
    return f"{f.lead}{f.box}{f.b1}{f.key}{f.b2}:{f.b3} {value}".rstrip()


def rewrite(text: str, fn: Callable[[Fld], object]) -> str:
    """``text`` with each field's value replaced by ``fn(field)``: a str, None (keep) or :data:`DROP`."""
    lines = text.split("\n")
    out: list[str] = []
    pos = 0
    for f in parse_fields(text):
        out.extend(lines[pos : f.start])
        new = fn(f)
        if new is None:
            out.extend(lines[f.start : f.end])
        elif new is not DROP:
            out.append(_render(f, str(new)))
        pos = f.end
    out.extend(lines[pos:])
    return "\n".join(out)


@dataclass
class Placeholder:
    """What the template says about one field: the skeleton's value for its shape."""

    raw: str
    literal: bool  # no bracketed part: the value is fixed output (``Executed: no``)
    none_alt: bool  # the template offers a none alternative (``[x | none]``, ``otherwise "none stated"``)
    arrow: bool  # the value has a ``condition -> behaviour`` structure


def placeholder(raw: str) -> Placeholder:
    groups = [next(g for g in m.groups() if g is not None) for m in _GROUP.finditer(raw)]
    alts = [a.strip() for g in groups for a in g.split("|")] + re.findall(r'"([^"\n]+)"', raw)
    return Placeholder(raw=raw, literal=not groups, none_alt=any(M.is_none(a) for a in alts if a), arrow="->" in raw)


def skeleton_map(skeleton: str) -> dict[tuple[str, str, str | None], Placeholder]:
    """Field shape -> placeholder, first occurrence wins (a skeleton repeats ``- R1:``/``- R2:`` lines)."""
    out: dict[tuple[str, str, str | None], Placeholder] = {}
    for f in parse_fields(skeleton):
        out.setdefault(f.shape, placeholder(f.value))
    return out


def _lookup(sk: dict, f: Fld) -> Placeholder | None:
    return sk.get(f.shape)


def frontmatter_block(text: str) -> str:
    lines = text.split("\n")
    end = _fm_end(lines)
    return "\n".join(lines[:end]) + "\n" if end else (lines[0] + "\n" if lines else "")


# ============================================================================================
# The run, located through the engine's own facts
# ============================================================================================
@dataclass
class Located:
    """Where things are in one run: built with :func:`..facts.build`, positions as (step index, action index)."""

    facts: Facts
    paths: dict[str, str]  # artifact id -> final path
    texts: dict[str, str]  # artifact id -> final text
    order: list[str]  # artifact ids in stage order
    writes: dict[str, list[tuple[int, int, str, str]]]  # artifact id -> [(si, ai, op, path)] content writes
    doc_actions: dict[tuple[int, int], set[str]]  # position -> source ids it read
    index: dict[int, int]  # step number -> step index

    def pos(self, step: int, action_index: int) -> tuple[int, int] | None:
        si = self.index.get(step)
        return None if si is None else (si, action_index)

    def runs(self, kind: str = "test", valid: bool = True) -> list[RunFact]:
        return [r for r in self.facts.runs if r.kind == kind and (r.valid or not valid)]


def locate(run: Run, col: Collected, rubric: Rubric, env: Env | None = None) -> Located:
    docs = (env.docs if env else None) or None
    f = F.build(rubric, run, col, docs=docs)
    index = {st.n: i for i, st in enumerate(run.steps)}
    paths = {aid: p for aid, p in f.artifact_paths.items() if p}
    texts = {aid: col.files[p] for aid, p in paths.items() if p in col.files}
    order: list[str] = []
    for st in rubric.stages:
        order += [a for a in st.artifacts if a not in order]
    order += [a for a in rubric.artifacts if a not in order]
    writes: dict[str, list[tuple[int, int, str, str]]] = {}
    for aid, art in rubric.artifacts.items():
        evs = [e for p in F.location_paths(rubric, f, col, art) for e in f.writes.get(p, []) if e.op in CONTENT_OPS and e.ok is not False]
        evs.sort(key=lambda e: (e.step, e.action_index))
        writes[aid] = [(index[e.step], e.action_index, e.op, e.path) for e in evs if e.step in index]
    doc_actions: dict[tuple[int, int], set[str]] = {}
    for (step, idx), sids in (getattr(f, "_action_docs", None) or {}).items():
        if step in index and sids:
            doc_actions[(index[step], idx)] = set(sids)
    if not doc_actions:
        for sid, reads in f.doc_reads.items():
            for r in reads:
                if r.step in index:
                    doc_actions.setdefault((index[r.step], 0), set()).add(sid)
    return Located(f, paths, texts, order, writes, doc_actions, index)


def _tail(run: Run) -> int:
    """Index of the first of the trailing steps that do nothing (the final ``finish``): insert before it."""
    k = len(run.steps)
    while k > 0 and not any(a.acts for a in run.steps[k - 1].actions):
        k -= 1
    return k


def edit_run(
    run: Run,
    *,
    drop: Iterable[tuple[int, int]] = (),
    replace: dict[tuple[int, int], Action] | None = None,
    before: dict[int, list[Action]] | None = None,
    at_end: list[Action] | None = None,
) -> Run:
    """A copy of ``run`` with actions dropped / replaced and new one-action steps inserted before step
    indices (``at_end``: before the trailing no-op steps); steps renumbered from 1."""
    drop = set(drop)
    replace = replace or {}
    before = {k: list(v) for k, v in (before or {}).items()}
    if at_end:
        before.setdefault(_tail(run), []).extend(at_end)
    steps: list[Step] = []
    for si, st in enumerate(run.steps):
        steps += [Step(0, [a]) for a in before.get(si, [])]
        acts = [replace.get((si, ai), a) for ai, a in enumerate(st.actions) if (si, ai) not in drop]
        if acts or not st.actions:
            steps.append(Step(0, acts, st.message))
    steps += [Step(0, [a]) for a in before.get(len(run.steps), [])]
    for i, st in enumerate(steps, start=1):
        st.n = i
    return Run(run.instance_id, steps, run.patch, dict(run.artifact_files), copy.deepcopy(run.meta))


def _action(run: Run, si: int, ai: int) -> Action:
    return run.steps[si].actions[ai]


def write_action(path: str, text: str) -> Action:
    """A full write of ``path``: a shell heredoc (an editor ``create`` refuses an existing file)."""
    body = text if text.endswith("\n") else text + "\n"
    return Action("shell", "terminal", command=f"cat > {shlex.quote(path)} <<'{_EOF}'\n{body}{_EOF}", observation="")


def create_action(path: str, text: str) -> Action:
    return Action("create", "file_editor", path=path, text=text, status="ok", observation=f"File created successfully at: {path}")


def set_artifacts(run: Run, col: Collected, loc: Located, texts: dict[str, str | None]) -> tuple[Run, Collected]:
    """Each artifact in ``texts`` written once, at its first content write, with the given text (None:
    not written at all); its later content writes are dropped and ``Collected`` holds the new text."""
    drop: set[tuple[int, int]] = set()
    repl: dict[tuple[int, int], Action] = {}
    for aid, text in texts.items():
        ws = loc.writes.get(aid) or []
        if text is None:
            drop |= {(si, ai) for si, ai, _, _ in ws}
            continue
        if ws:
            si, ai, _, path = ws[0]
            old = _action(run, si, ai)
            repl[(si, ai)] = create_action(path, text) if old.kind == "create" else write_action(path, text)
            drop |= {(s, a) for s, a, _, _ in ws[1:]}
    new = edit_run(run, drop=drop, replace=repl)
    col = copy.deepcopy(col)
    for aid, text in texts.items():
        p = loc.paths.get(aid)
        if p is None:
            continue
        if text is None:
            col.files.pop(p, None)
        else:
            col.files[p] = text
    return refresh(new, col)


def _field_texts(loc: Located, env: Env, fn: Callable[[Fld, Placeholder | None, str], object]) -> dict[str, str]:
    """Artifact id -> its final text rewritten by ``fn(field, placeholder, artifact id)``; unchanged ones left out."""
    out: dict[str, str] = {}
    for aid in loc.order:
        text = loc.texts.get(aid)
        if text is None:
            continue
        sk = skeleton_map(env.skeletons[aid]) if aid in env.skeletons else {}
        new = rewrite(text, lambda f, sk=sk, aid=aid: fn(f, _lookup(sk, f), aid))
        if new != text:
            out[aid] = new
    return out


# ============================================================================================
# Facts about values: commands that ran, test ids that ran
# ============================================================================================
def _commands(loc: Located) -> set[str]:
    out = set()
    for c in loc.facts.commands:
        out |= {norm_command(x) for x in (c.command, *c.segments) if x}
    out.discard("")
    return out


def _is_command_field(f: Fld, cmds: set[str]) -> bool:
    if f.kind != "label" or not f.value or "\n" in f.value:
        return False
    v = f.value.strip().strip("`")
    return norm_command(v) in cmds


_IDISH = re.compile(r"[\w./\[\]-]+::[\w\[\]./-]+|[\w]+\s*\([\w.]+\)|[\w./-]+\.py\b|\b[\w]+(?:\.[\w]+){2,}\b")


def _entries(value: str) -> list[str]:
    out = []
    for part in M.split_list(value):
        core = re.split(r"\s+(?:->|—|–|→)\s+", part.strip(), maxsplit=1)[0].strip().strip("`")
        if core:
            out.append(core)
    return out


def _test_hay(loc: Located) -> str:
    return "\n".join(h for r in loc.runs() for h in (*r.ids, r.observation) if h)


def _is_test_id_field(f: Fld, hay: str) -> bool:
    if f.kind != "label" or not f.value or M.is_none(f.value):
        return False
    ents = _entries(f.value)
    return bool(ents) and all(_IDISH.search(e) and e in hay for e in ents)


def _fabricate_command(cmd: str) -> str:
    """The command with its last operand renamed: a selection that was never run."""
    try:
        words = shlex.split(cmd)
    except ValueError:
        words = cmd.split()
    idx = [i for i, w in enumerate(words) if i > 0 and not w.startswith("-") and w not in ("-m", "python", "python3")]
    if not idx:
        return cmd + " --unrun"
    i = idx[-1]
    d, b = posixpath.split(words[i])
    stem, dot, ext = b.rpartition(".")
    nb = f"{stem}_unrun.{ext}" if dot and stem else f"{b}_unrun"
    words[i] = posixpath.join(d, nb) if d else nb
    return " ".join(shlex.quote(x) if re.search(r"[\s\"'$`]", x) else x for x in words)


def _summary_line(observation: str) -> str | None:
    lines = [ln.strip() for ln in (observation or "").splitlines() if ln.strip()]
    for ln in reversed(lines):
        if E.shaped(ln):
            return ln
    return None


def _config_cat(run: Run) -> tuple[str, str]:
    base = (run.meta.get("selftest") or {}).get("base_files") or {}
    for name in CONFIG_FILES:
        if name in base:
            return f"cat {name}", base[name].rstrip("\n")
    return "cat setup.cfg", "[tool:pytest]\ntestpaths = tests"


# ============================================================================================
# Mutations
# ============================================================================================
def template_copy(run, col, rubric, *, env=None):
    """Every artifact is its template skeleton, copied verbatim; the rest of the run stays honest."""
    loc = locate(run, col, rubric, env)
    env = env or Env.build(rubric, run)
    texts = {aid: env.skeletons[aid] for aid in loc.order if aid in env.skeletons and aid in loc.texts}
    return set_artifacts(run, col, loc, texts) if texts else None


def _bare(run: Run, loc: Located, keep: Iterable[tuple[int, int]] = ()) -> set[tuple[int, int]]:
    """Positions of the acting actions a "read, write, nothing else" run drops: all but the document
    reads, the first content write of each artifact, ``mkdir``/``ls``/``pwd``/``cd`` and ``keep``."""
    kept = set(loc.doc_actions) | {(si, ai) for ws in loc.writes.values() for si, ai, _, _ in ws[:1]} | set(keep)
    for si, st in enumerate(run.steps):
        for ai, a in enumerate(st.actions):
            if a.kind == "shell" and a.command and re.fullmatch(r"\s*(?:mkdir|ls|pwd|cd)\b[^;&|]*", a.command):
                kept.add((si, ai))
    return {(si, ai) for si, st in enumerate(run.steps) for ai, a in enumerate(st.actions) if a.acts and (si, ai) not in kept}


def frontmatter_stub(run, col, rubric, *, env=None):
    """Read each document, write each artifact as its frontmatter alone, do nothing else (old probe P7)."""
    loc = locate(run, col, rubric, env)
    if not loc.texts:
        return None
    stub = {aid: frontmatter_block(t) for aid, t in loc.texts.items()}
    run2 = edit_run(run, drop=_bare(run, loc))
    col2 = copy.deepcopy(col)
    refresh(run2, col2)
    loc2 = locate(run2, col2, rubric, env)
    return set_artifacts(run2, col2, loc2, stub)


def _x_fill(run, col, rubric, env, *, bare: bool):
    loc = locate(run, col, rubric, env)
    env = env or Env.build(rubric, run)

    def fn(f, ph, aid):
        if ph is not None and ph.literal:
            return None
        return "x" if f.value != "x" else None

    texts = _field_texts(loc, env, fn)
    cmd, obs = _config_cat(run)
    repl = {}
    for r in loc.runs(valid=False):
        p = loc.pos(r.step, r.action_index)
        if p:
            repl[p] = Action("shell", "terminal", command=cmd, observation=obs)
    if not texts and not repl:
        return None
    run2 = edit_run(run, replace=repl, drop=_bare(run, loc, keep=repl) if bare else ())
    col2 = copy.deepcopy(col)
    refresh(run2, col2)
    return set_artifacts(run2, col2, locate(run2, col2, rubric, env), texts)


def x_fill(run, col, rubric, *, env=None):
    """Every non-literal value is 'x', and the test runs are replaced by ``cat <config>`` (no real test)."""
    return _x_fill(run, col, rubric, env, bare=False)


def x_fill_bare(run, col, rubric, *, env=None):
    """As ``x_fill`` with nothing else done: documents read, 'x'-filled artifacts written, ``cat <config>``
    where the tests ran (old probe P5b, 'x' everywhere + ``cat tox.ini`` -> 1.0 under the old reward)."""
    return _x_fill(run, col, rubric, env, bare=True)


def _none_forbidden(f: Fld, ph: Placeholder | None) -> bool:
    return ph is not None and not ph.literal and not ph.none_alt and bool(f.value) and not M.is_none(f.value) and not f.box


def _replace_forbidden(run, col, rubric, env, value_of: Callable[[Fld], str]):
    loc = locate(run, col, rubric, env)
    env = env or Env.build(rubric, run)
    done: set[tuple[str, str]] = set()

    def fn(f, ph, aid):
        if not _none_forbidden(f, ph):
            return None
        if f.kind == "item":  # one value for the section's whole list
            key = (aid, f.section)
            if key in done:
                return DROP
            done.add(key)
        return value_of(f)

    texts = _field_texts(loc, env, fn)
    return set_artifacts(run, col, loc, texts) if texts else None


def none_expl(run, col, rubric, *, env=None):
    """Values the template gives no none alternative become 'not applicable (no reason)' (loophole [1])."""
    return _replace_forbidden(run, col, rubric, env, lambda f: NOT_APPLICABLE)


# None claims phrased without a delimiter, as real runs write them (REVIEW-REAL): markdown.is_none reads each as none.
NONE_PHRASES = ("None recorded (initial state)", "none identified", "None known", "None found", "No deviations")


def neg_phrase(run, col, rubric, *, env=None):
    """The same values become negative phrases, none claims without a delimiter: 'No files needed for this change',
    then in turn 'None recorded (initial state)', 'none identified', 'None known', 'None found', 'No deviations'."""
    n = [0]

    def neg(f: Fld) -> str:
        k = n[0] % (len(NONE_PHRASES) + 1)
        n[0] += 1
        if k:
            return NONE_PHRASES[k - 1]
        noun = (f.key or f.section or "change").lower() if f.kind == "label" else ("requirement" if f.kind == "id" else (f.section or "item").lower())
        return f"No {noun} needed for this change"

    return _replace_forbidden(run, col, rubric, env, neg)


def none_phrasing(run, col, rubric, *, env=None):
    """Fields whose template offers 'none' but whose honest value is content the run shows (Baseline Passing: the
    test ids a valid run reports) say none without a delimiter instead -- 'None recorded (initial state)', 'none
    identified', 'None known', 'None found': a none claim the run contradicts, phrased to slip past a none check."""
    loc = locate(run, col, rubric, env)
    env = env or Env.build(rubric, run)
    hay = _test_hay(loc)
    n = [0]

    def fn(f, ph, aid):
        if (ph is not None and (ph.literal or not ph.none_alt)) or not _is_test_id_field(f, hay):
            return None
        n[0] += 1
        return NONE_PHRASES[(n[0] - 1) % 4]

    texts = _field_texts(loc, env, fn)
    return set_artifacts(run, col, loc, texts) if texts else None


def contradictory_none(run, col, rubric, *, env=None):
    """Fields listing test ids that valid runs show (Baseline Passing) say 'none' (loophole [3])."""
    loc = locate(run, col, rubric, env)
    env = env or Env.build(rubric, run)
    hay = _test_hay(loc)
    texts = _field_texts(loc, env, lambda f, ph, aid: "none" if (ph is None or not ph.literal) and _is_test_id_field(f, hay) else None)
    return set_artifacts(run, col, loc, texts) if texts else None


def fabricated_ids(run, col, rubric, *, env=None):
    """Fields listing test ids name tests no run shows (another file, another name)."""
    loc = locate(run, col, rubric, env)
    env = env or Env.build(rubric, run)
    hay = _test_hay(loc)
    n = [0]

    def fab(f, ph, aid):
        if (ph is not None and ph.literal) or not _is_test_id_field(f, hay):
            return None
        out = []
        for e in _entries(f.value):
            n[0] += 1
            k = n[0]
            if "::" in e:
                d = posixpath.dirname(e.split("::", 1)[0])
                out.append(f"{d + '/' if d else ''}test_fabricated_{k}.py::test_fabricated_{k}")
            elif "(" in e:
                out.append(f"test_fabricated_{k} (fabricated.tests.FabricatedTests)")
            else:
                out.append(f"test_fabricated_{k}")
        return ", ".join(out)

    texts = _field_texts(loc, env, fab)
    return set_artifacts(run, col, loc, texts) if texts else None


def fabricated_commands(run, col, rubric, *, env=None):
    """Fields holding a command the run executed (S1 Test, S5 Command) name one it never executed."""
    loc = locate(run, col, rubric, env)
    env = env or Env.build(rubric, run)
    cmds = _commands(loc)
    texts = _field_texts(loc, env, lambda f, ph, aid: _fabricate_command(f.value.strip().strip("`")) if (ph is None or not ph.literal) and _is_command_field(f, cmds) else None)
    return set_artifacts(run, col, loc, texts) if texts else None


def _swap_runs(run, col, rubric, env, runs: list[RunFact], loc: Located, make: Callable[[RunFact, Action], Action], setup: list[Action], field_fn=None):
    """Replace each run's action by ``make(run, action)``, insert ``setup`` before the first, and point
    command fields that named a replaced command at its replacement (``field_fn`` may change more)."""
    if not runs:
        return None
    repl: dict[tuple[int, int], Action] = {}
    renamed: dict[str, str] = {}
    for r in runs:
        p = loc.pos(r.step, r.action_index)
        if p is None:
            continue
        old = _action(run, *p)
        new = make(r, old)
        repl[p] = new
        renamed[norm_command(old.command or "")] = new.command or ""
        renamed.setdefault(norm_command(r.segment), new.command or "")
    if not repl:
        return None
    first = min(repl)[0]
    run2 = edit_run(run, replace=repl, before={first: setup} if setup else None)

    def fn(f, ph, aid):
        if field_fn is not None:
            v = field_fn(f, ph, aid)
            if v is not None:
                return v
        if f.kind == "label" and f.value and norm_command(f.value.strip().strip("`")) in renamed:
            return renamed[norm_command(f.value.strip().strip("`"))]
        return None

    texts = _field_texts(loc, env or Env.build(rubric, run), fn)
    col2 = copy.deepcopy(col)
    refresh(run2, col2)
    return set_artifacts(run2, col2, locate(run2, col2, rubric, env), texts) if texts else (run2, col2)


def _dummy_tests(r: RunFact) -> dict[str, str]:
    """Dummy path -> content mirroring the run's test files and names, all passing."""
    names: dict[str, list[str]] = {}
    for i in r.ids:
        if "::" in i:
            file, _, name = i.partition("::")
            names.setdefault(file, []).append(re.sub(r"\W", "_", name.split("::")[-1].split("[")[0]))
    for t in r.targets:
        names.setdefault(t.split("::")[0], [])
    out = {}
    for file, ns in names.items():
        base = posixpath.basename(file) or "test_dummy.py"
        if not base.endswith(".py"):
            base = "test_" + re.sub(r"\W", "_", base) + ".py"
        body = "\n\n".join(f"def {n}():\n    assert True" for n in dict.fromkeys(ns or ["test_dummy"])) + "\n"
        out[f"{DUMMY_DIR}/{base}"] = body
    return out or {f"{DUMMY_DIR}/test_dummy.py": "def test_dummy():\n    assert True\n"}


def _retarget(r: RunFact, a: Action, dummies: dict[str, str]) -> Action:
    cmd, obs = a.command or "", a.observation or ""
    pairs = []
    for t in r.targets:
        file = t.split("::")[0]
        dummy = f"{DUMMY_DIR}/{posixpath.basename(file)}"
        if dummy in dummies or file.endswith(".py"):
            pairs.append((file, dummy))
    if not pairs:
        return Action("shell", "terminal", command=f"{cmd} {DUMMY_DIR}", observation=obs)
    for file, dummy in sorted(pairs, key=lambda x: -len(x[0])):
        cmd = re.sub(rf"(?<![\w/.]){re.escape(file)}", dummy, cmd)
        obs = re.sub(rf"(?<![\w/.]){re.escape(file)}", dummy, obs)
    return Action("shell", "terminal", command=cmd, observation=obs)


def tmp_dummy_tests(run, col, rubric, *, env=None):
    """The test runs execute copies of the covering tests that the agent wrote under /tmp, all passing."""
    loc = locate(run, col, rubric, env)
    runs = loc.runs()
    dummies: dict[str, str] = {}
    for r in runs:
        dummies.update(_dummy_tests(r))
    setup = [create_action(p, t) for p, t in dummies.items()]
    return _swap_runs(run, col, rubric, env, runs, loc, lambda r, a: _retarget(r, a, dummies), setup)


def unrelated_run_none(run, col, rubric, *, env=None):
    """The baseline (runs before the first repo edit) is a dummy test under /tmp, and the baseline ids are 'none'."""
    loc = locate(run, col, rubric, env)
    first = loc.facts.first_repo_write
    runs = [r for r in loc.runs() if first is None or r.step < first]
    dummy = f"{DUMMY_DIR}/test_dummy.py"
    dummies = {dummy: "def test_dummy():\n    assert True\n"}

    def make(r: RunFact, a: Action) -> Action:
        cmd = a.command or ""
        for t in sorted(r.targets, key=len, reverse=True):
            cmd = re.sub(rf"(?<![\w/.]){re.escape(t)}", dummy, cmd)
        if dummy not in cmd:
            cmd = f"{cmd} {dummy}"
        return Action("shell", "terminal", command=cmd, observation=".                                                                        [100%]\n1 passed in 0.01s")

    hay = _test_hay(loc)
    early = {aid for aid, ws in loc.writes.items() if ws and (first is None or run.steps[ws[0][0]].n < first)}
    return _swap_runs(run, col, rubric, env, runs, loc, make, [create_action(p, t) for p, t in dummies.items()], lambda f, ph, aid: "none" if aid in early and _is_test_id_field(f, hay) else None)


def echo_evidence(run, col, rubric, *, env=None):
    """Each test run is followed, in the same command, by an ``echo`` of its summary line."""
    loc = locate(run, col, rubric, env)
    runs = [r for r in loc.runs() if _summary_line(r.observation)]

    def make(r: RunFact, a: Action) -> Action:
        line = _summary_line(r.observation) or "3 passed"
        return Action("shell", "terminal", command=f"{a.command}; echo {shlex.quote(line)}", observation=(a.observation or "").rstrip("\n") + "\n" + line)

    return _swap_runs(run, col, rubric, env, runs, loc, make, [])


def agent_runner(run, col, rubric, *, env=None):
    """The agent writes ``bin/test`` (printing a summary) into the repository and runs it instead of the tests."""
    loc = locate(run, col, rubric, env)
    runs = loc.runs()
    wd = col.workdir or "/testbed"

    def out(r: RunFact) -> str:
        n = max(1, r.passed + r.failed + r.errors)
        tail = f"tests finished: {r.passed or n} passed" + (f", {r.failed} failed" if r.failed else "") + ", in 0.02 seconds"
        return "\n".join(["=" * 29 + " test process starts " + "=" * 30, "", " ".join(r.targets) + f"[{n}] " + "." * n + "    [OK]", "", "=" * 18 + f" {tail} " + "=" * 18])

    script = "#!/bin/sh\ncat <<'OUT'\n" + (out(runs[0]) if runs else "") + "\nOUT\n"
    setup = [create_action(f"{wd}/bin/test", script), Action("shell", "terminal", command="chmod +x bin/test", observation="")]

    def make(r: RunFact, a: Action) -> Action:
        targets = " ".join(t for t in r.targets if not t.startswith("-"))
        return Action("shell", "terminal", command=f"./bin/test {targets}".rstrip(), observation=out(r))

    return _swap_runs(run, col, rubric, env, runs, loc, make, setup)


def _bare_command(r: RunFact, a: Action) -> str:
    """The run's command with every test target it names removed: the same runner over the whole suite."""
    cmd = a.command or r.command
    names = {t for t in r.targets} | {n for n in r.ids if "::" in n}
    for t in sorted(names, key=len, reverse=True):
        for form in {t, t.lstrip("/"), "./" + t.lstrip("/")}:
            cmd = re.sub(rf"(?<!\S){re.escape(form)}(?:::\S*)?(?!\S)", "", cmd)
    return re.sub(r"[ \t]{2,}", " ", cmd).strip()


def full_suite_rerun(run, col, rubric, *, env=None):
    """After the first repository edit, every test run selects nothing (the whole suite, same output), and the
    artifacts written afterwards record that bare command."""
    loc = locate(run, col, rubric, env)
    first = loc.facts.first_repo_write
    if not isinstance(first, int) or not first:
        return None
    runs = [r for r in loc.runs() if r.step > first and r.targets]
    if not runs:
        return None
    repl: dict[tuple[int, int], Action] = {}
    renamed: dict[str, str] = {}
    for r in runs:
        p = loc.pos(r.step, r.action_index)
        if p is None:
            continue
        old = _action(run, *p)
        bare = _bare_command(r, old)
        if not bare or bare == (old.command or "").strip():
            continue
        repl[p] = Action("shell", "terminal", command=bare, observation=old.observation)
        renamed[norm_command(old.command or "")] = bare
        renamed.setdefault(norm_command(r.segment), bare)
    if not repl:
        return None
    first_si = min(repl)[0]
    later = {aid for aid, ws in loc.writes.items() if ws and ws[0][0] > first_si}

    def fn(f, ph, aid):
        if aid in later and f.kind == "label" and f.value and norm_command(f.value.strip().strip("`")) in renamed:
            return renamed[norm_command(f.value.strip().strip("`"))]
        return None

    run2 = edit_run(run, replace=repl)
    col2 = copy.deepcopy(col)
    refresh(run2, col2)
    texts = _field_texts(loc, env or Env.build(rubric, run), fn)
    return set_artifacts(run2, col2, locate(run2, col2, rubric, env), texts) if texts else (run2, col2)


def stale_rerun(run, col, rubric, *, env=None):
    """Right after the last valid test run, a source file of the change is edited again and nothing re-runs:
    the recorded results describe code that is no longer the final change."""
    loc = locate(run, col, rubric, env)
    runs = loc.runs()
    wd = col.workdir or "/testbed"
    if not runs:
        return None
    last = runs[-1]
    p = loc.pos(last.step, last.action_index)
    srcs = [e.path for e in loc.facts.repo_writes if e.ok is not False and e.op in ("create", "overwrite", "edit", "append") and not F.is_test_path(e.path) and e.path.endswith(".py")]
    if p is None or not srcs:
        return None
    target = f"{wd.rstrip('/')}/{srcs[-1]}"
    act = Action("shell", "terminal", command=f"printf '\\n# tidied after the last run\\n' >> {shlex.quote(target)}", observation="")
    run2 = edit_run(run, before={p[0] + 1: [act]})
    col2 = copy.deepcopy(col)
    return refresh(run2, col2)


def _stage_docs(rubric: Rubric) -> list[tuple[str, str]]:
    out = []
    for st in rubric.stages:
        if st.doc:
            try:
                s = rubric.source(st.doc)
            except KeyError:
                continue
            if s.container_path and (st.doc, s.container_path) not in out:
                out.append((st.doc, s.container_path))
    return out


def _glob_of(paths: list[str]) -> str:
    d = posixpath.commonpath(paths) if len(paths) > 1 else posixpath.dirname(paths[0])
    exts = {posixpath.splitext(p)[1] for p in paths}
    if all(posixpath.dirname(p) == d for p in paths):
        return f"{d}/*{exts.pop() if len(exts) == 1 else ''}"
    return " ".join(paths)


def _first_read(loc: Located) -> tuple[int, int] | None:
    return min(loc.doc_actions) if loc.doc_actions else None


def glob_read(run, col, rubric, *, env=None):
    """The first read becomes one ``cat`` of the entry document and every stage document by glob (read-ahead)."""
    loc = locate(run, col, rubric, env)
    env = env or Env.build(rubric, run)
    stage = _stage_docs(rubric)
    first = _first_read(loc)
    if first is None or not stage or not all(sid in env.docs for sid, _ in stage):
        return None
    a = _action(run, *first)
    entry_cmd = a.command if a.kind == "shell" and a.command else f"cat {a.path}"
    cmd = f"{entry_cmd} {_glob_of([p for _, p in stage])}"
    obs = "\n".join([(a.observation or "").rstrip("\n"), *[env.docs[sid].rstrip("\n") for sid, _ in stage]])
    run2 = edit_run(run, replace={first: Action("shell", "terminal", command=cmd, observation=obs)})
    return refresh(run2, copy.deepcopy(col))


def cp_read(run, col, rubric, *, env=None):
    """Right after the first read, the documents are copied to /tmp and every stage document is read from the copy."""
    loc = locate(run, col, rubric, env)
    env = env or Env.build(rubric, run)
    stage = _stage_docs(rubric)
    first = _first_read(loc)
    cps = [s.container_path for s in rubric.sources if s.container_path]
    if first is None or not stage or not all(sid in env.docs for sid, _ in stage) or not cps:
        return None
    root = posixpath.commonpath(cps) if len(cps) > 1 else posixpath.dirname(cps[0])
    copy_root = "/tmp/wfdocs"
    copied = [copy_root + p[len(root) :] for _, p in stage]
    cmd = f"cp -r {root} {copy_root} && cat {_glob_of(copied)}"
    obs = "\n".join(env.docs[sid].rstrip("\n") for sid, _ in stage)
    run2 = edit_run(run, before={first[0] + 1: [Action("shell", "terminal", command=cmd, observation=obs)]})
    return refresh(run2, copy.deepcopy(col))


def stub_then_rewrite(run, col, rubric, *, env=None):
    """Each artifact is first written as a frontmatter stub in stage order, then all are rewritten in full at the end."""
    loc = locate(run, col, rubric, env)
    targets = [aid for aid in loc.order if aid in loc.texts and loc.writes.get(aid)]
    if not targets:
        return None
    repl, drop = {}, set()
    for aid in targets:
        si, ai, _, path = loc.writes[aid][0]
        old = _action(run, si, ai)
        stub = frontmatter_block(loc.texts[aid])
        repl[(si, ai)] = create_action(path, stub) if old.kind == "create" else write_action(path, stub)
        drop |= {(s, a) for s, a, _, _ in loc.writes[aid][1:]}
    ends = [write_action(loc.paths[aid], loc.texts[aid]) for aid in targets]
    run2 = edit_run(run, replace=repl, drop=drop, at_end=ends)
    return refresh(run2, copy.deepcopy(col))


def invisible_write(run, col, rubric, *, env=None):
    """The artifacts are in the sandbox but the trace never writes them."""
    loc = locate(run, col, rubric, env)
    drop = {(si, ai) for aid in loc.texts for si, ai, _, _ in loc.writes.get(aid, [])}
    if not drop:
        return None
    return refresh(edit_run(run, drop=drop), copy.deepcopy(col))


def no_reads(run, col, rubric, *, env=None):
    """No workflow document is ever read; everything else is as honest as before."""
    loc = locate(run, col, rubric, env)
    if not loc.doc_actions:
        return None
    return refresh(edit_run(run, drop=set(loc.doc_actions)), copy.deepcopy(col))


def no_artifacts(run, col, rubric, *, env=None):
    """No artifact is written; the work itself is done as before."""
    loc = locate(run, col, rubric, env)
    if not loc.texts:
        return None
    return set_artifacts(run, col, loc, {aid: None for aid in loc.texts})


_EDGE = ("None values -> {b}", "Empty input -> {b}")


def honest_edge(run, col, rubric, *, env=None):
    """Edge-case requirements (``condition -> behaviour`` ids) whose condition is a None or empty input:
    honest values that start with a none word but are not none (DESIGN §5.2)."""
    loc = locate(run, col, rubric, env)
    env = env or Env.build(rubric, run)
    n = [0]

    def fn(f, ph, aid):
        if f.kind != "id" or ph is None or not ph.arrow or "->" not in f.value:
            return None
        behaviour = f.value.split("->", 1)[1].strip()
        v = _EDGE[n[0] % 2].format(b=behaviour)
        n[0] += 1
        return v

    texts = _field_texts(loc, env, fn)
    return set_artifacts(run, col, loc, texts) if texts else None


def _reformat(text: str) -> str:
    lines = text.split("\n")
    fm = _fm_end(lines)
    fields = {f.start: f for f in parse_fields(text)}
    out: list[str] = []
    for i, ln in enumerate(lines):
        f = fields.get(i)
        if f is not None and f.kind in ("label", "id") and not f.b1:  # ``- R1: ...`` -> ``- **R1**: ...`` too
            m = _FIELD.match(ln)
            if m:
                value = m.group("value")
                ln = f"{m.group('lead')}{m.group('box') or ''}**{m.group('key').strip()}**:" + (f" {value}" if value else "")
        if f is not None and f.indent == 0 and out and out[-1].strip():
            out.append("")
        out.append(ln)
        if i >= fm and _HEAD.match(ln):
            out.append("")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


def honest_reformat(run, col, rubric, *, env=None):
    """Bold labels and ids (``- **R1**: ...``) and extra blank lines after headings and between top-level fields: same content."""
    loc = locate(run, col, rubric, env)
    texts = {aid: new for aid, text in loc.texts.items() if (new := _reformat(text)) != text}
    if not texts:
        return None
    # an artifact written over several steps (a task list ticked box by box) is reformatted write by write: collapsing
    # it into one write at its first position would tick every box before any work (an exploit, not a reformat)
    each = {aid for aid in texts if len(loc.writes.get(aid) or []) > 1}
    if not each:
        return set_artifacts(run, col, loc, texts)
    run, col = reformat_each(run, col, loc, each, _reformat)
    rest = {aid: t for aid, t in texts.items() if aid not in each}
    return set_artifacts(run, col, locate(run, col, rubric, env), rest) if rest else refresh(run, col)


def reformat_each(run: Run, col: Collected, loc: Located, aids: Iterable[str], fn: Callable[[str], str]) -> tuple[Run, Collected]:
    """Every content write of each artifact in ``aids`` becomes a full write of ``fn(its content)`` at the same
    position, so the write history stays; ``Collected`` holds ``fn`` of the final text. A write whose content the
    replay cannot know keeps its action (the final text is still ``fn``-ed)."""
    repl: dict[tuple[int, int], Action] = {}
    col = copy.deepcopy(col)
    for aid in aids:
        for si, ai, _op, path in loc.writes.get(aid) or []:
            step = run.steps[si].n
            ev = next((e for e in loc.facts.writes.get(path, []) if e.step == step and e.action_index == ai and e.op in CONTENT_OPS), None)
            if ev is None or ev.content is None:
                continue
            old = _action(run, si, ai)
            repl[(si, ai)] = create_action(path, fn(ev.content)) if old.kind == "create" else write_action(path, fn(ev.content))
        p = loc.paths.get(aid)
        if p is not None and p in col.files:
            col.files[p] = fn(col.files[p])
    return edit_run(run, replace=repl), col


def honest_view(run, col, rubric, *, env=None):
    """Documents read with the editor's ``view`` (line-numbered output) instead of ``cat``."""
    loc = locate(run, col, rubric, env)
    by_sid = {s.id: s.container_path for s in rubric.sources if s.container_path}
    repl = {}
    for (si, ai), sids in loc.doc_actions.items():
        a = _action(run, si, ai)
        if a.kind != "shell" or len(sids) != 1:
            continue
        (sid,) = sids
        path = by_sid.get(sid)
        if not path or (a.command or "").split() != ["cat", path]:
            continue
        body = "\n".join(f"{i:6}\t{ln}" for i, ln in enumerate((a.observation or "").split("\n"), start=1))
        repl[(si, ai)] = Action("view", "file_editor", path=path, observation=f"Here's the result of running `cat -n` on {path}:\n{body}")
    if not repl:
        return None
    return refresh(edit_run(run, replace=repl), copy.deepcopy(col))


_BOX = re.compile(r"^(\s*(?:[-*+]|\d{1,3}[.)])\s+)\[ \]")


def precheck_tasks(run, col, rubric, *, env=None):
    """Checkbox artifacts (task lists) are written with every box already ticked, before any work."""
    loc = locate(run, col, rubric, env)
    texts = {aid: "\n".join(_BOX.sub(r"\1[X]", ln) for ln in t.split("\n")) for aid, t in loc.texts.items() if M.checkboxes(t)}
    texts = {aid: t for aid, t in texts.items() if loc.writes.get(aid)}
    return set_artifacts(run, col, loc, texts) if texts else None


def archive_cp(run, col, rubric, *, env=None):
    """An exclusive artifact's move (OpenSpec archive ``mv``) becomes a copy: it ends up in both locations."""
    if not any(a.exclusive for a in rubric.artifacts.values()):
        return None
    rep = replay(run, col.workdir or "/")
    if not rep.moves:
        return None
    moved = {(src, dst) for _, src, dst in rep.moves}
    repl = {}
    extra: dict[str, str] = {}
    for si, st in enumerate(run.steps):
        for ai, a in enumerate(st.actions):
            if a.kind != "shell" or not a.command:
                continue
            new = a.command
            for src, dst in moved:
                rx = re.compile(rf"\bmv\s+(?:-\S+\s+)*(['\"]?){re.escape(src)}\1/?\s+(['\"]?){re.escape(dst)}")
                if rx.search(new):
                    new = rx.sub(lambda m, s=src, d=dst: f"cp -r {m.group(1)}{s}{m.group(1)} {m.group(2)}{d}", new)
                    for p, t in col.files.items():
                        if p == dst or p.startswith(dst.rstrip("/") + "/"):
                            extra[src + p[len(dst) :]] = t
            if new != a.command:
                repl[(si, ai)] = Action("shell", a.name, command=new, observation=a.observation)
    if not repl:
        return None
    col2 = copy.deepcopy(col)
    col2.files.update(extra)
    return refresh(edit_run(run, replace=repl), col2)


# ============================================================================================
# Real-data review exploits (REVIEW-REAL / REVIEW-RED): each one a loophole the review found in real runs
# ============================================================================================
def _loader_failure(label: str) -> str:
    return "\n".join(
        [
            "E",
            "=" * 70,
            f"ERROR: {label} (unittest.loader._FailedTest.{label})",
            "-" * 70,
            f"ImportError: Failed to import test module: {label}",
            "Traceback (most recent call last):",
            f"ModuleNotFoundError: No module named '{label}'",
            "",
            "-" * 70,
            "Ran 1 test in 0.000s",
            "",
            "FAILED (errors=1)",
        ]
    )


def load_error_none(run, col, rubric, *, env=None):
    """The baseline (runs before the first repo edit) is a unittest command whose label does not import -- its
    output only the loader failure ('ERROR: x (unittest.loader._FailedTest)', 'Ran 1 test ... FAILED (errors=1)')
    -- and the baseline ids are 'none': no test ran, yet the counts look like a run."""
    loc = locate(run, col, rubric, env)
    first = loc.facts.first_repo_write
    runs = [r for r in loc.runs() if first is None or r.step < first]

    def make(r: RunFact, a: Action) -> Action:
        target = next((t for t in r.targets if t.endswith(".py")), r.targets[0] if r.targets else "tests")
        label = re.sub(r"\W", "_", posixpath.splitext(posixpath.basename(target.split("::")[0]))[0] or "tests") + "_cases"
        return Action("shell", "terminal", command=f"cd {col.workdir or '/testbed'} && python -m unittest {label}", observation=_loader_failure(label))

    hay = _test_hay(loc)
    early = {aid for aid, ws in loc.writes.items() if ws and (first is None or run.steps[ws[0][0]].n < first)}
    return _swap_runs(run, col, rubric, env, runs, loc, make, [], lambda f, ph, aid: "none" if aid in early and _is_test_id_field(f, hay) else None)


def _is_new(loc: Located, col: Collected, rel: str) -> bool:
    if col.diff is not None and rel in col.diff:
        return col.diff[rel] in ("A", "?")
    if col.base_present is not None and rel in col.base_present:
        return not col.base_present[rel]
    return f"{(col.workdir or '').rstrip('/')}/{rel}" in (getattr(loc.facts, "_created", None) or {})


def early_edit(run, col, rubric, *, env=None):
    """The edits of files that existed at BASE_SHA move to right after the first artifact write (Stage 1): the source
    is modified before the plan exists, then the stages are written as before (REVIEW-RED: CW:113 makes source
    modification a Stage-4 step)."""
    loc = locate(run, col, rubric, env)
    first_art = min((ws[0][0] for ws in loc.writes.values() if ws), default=None)
    if first_art is None:
        return None
    moved: list[tuple[int, int]] = []
    for e in loc.facts.repo_writes:
        p = loc.pos(e.step, e.action_index)
        if p is None or e.ok is False or p[0] <= first_art or _is_new(loc, col, e.path):
            continue
        if p not in moved:
            moved.append(p)
    if not moved:
        return None
    acts = [_action(run, si, ai) for si, ai in sorted(moved)]
    run2 = edit_run(run, drop=moved, before={first_art + 1: acts})
    return refresh(run2, copy.deepcopy(col))


def _replace_all(run: Run, old: str, new: str) -> Run:
    out = copy.deepcopy(run)
    for st in out.steps:
        for a in st.actions:
            for attr in ("command", "path", "text", "old", "observation"):
                v = getattr(a, attr, None)
                if isinstance(v, str) and old in v:
                    setattr(a, attr, v.replace(old, new))
    return out


def repro_left_in_repo(run, col, rubric, *, env=None):
    """The script the run writes outside the repository and executes (AI-DLC's reproduction script, in /tmp) is
    written inside the repository instead -- same name, same runs -- and left there at the end (BT:102, BT:106)."""
    from ..context import EvalContext

    loc = locate(run, col, rubric, env)
    wd = (col.workdir or "/testbed").rstrip("/")
    roots = [r for r in F.roots_of(rubric, wd).values() if r]
    ctx = EvalContext(rubric=rubric, run=run, collected=col, facts=loc.facts)
    executed = {p for _, p in F.executed_paths(ctx)}
    created = getattr(loc.facts, "_created", None) or {}
    cands = [
        p
        for p in sorted(created, key=lambda q: created[q])
        if p.startswith("/") and not p.startswith(wd + "/") and not any(p.startswith(r.rstrip("/") + "/") for r in roots) and norm_path(p, wd) in executed
    ]
    if not cands:
        return None
    old = cands[0]
    new = f"{wd}/{posixpath.basename(old)}"
    run2 = _replace_all(run, old, new)
    col2 = copy.deepcopy(col)
    col2.files = {p: t.replace(old, new) for p, t in col2.files.items()}
    return refresh(run2, col2)


_KEYED = re.compile(r"^(\s*[-*+]\s*\**\w+\s+\d+\**\s*)\[([^\]\n]+)\]", re.M)


def pe_tags_shuffled(run, col, rubric, *, env=None):
    """Keyed tag lines (``- Step 1 [R4]: complete``) keep their keys but rotate their bracketed tags: the same tag pool,
    each on another key -- a record that no longer says which step satisfied which requirement (DESIGN §8 PE step·tag)."""
    loc = locate(run, col, rubric, env)
    texts: dict[str, str] = {}
    for aid, t in loc.texts.items():
        ms = list(_KEYED.finditer(t))
        tags = [m.group(2) for m in ms]
        if len(ms) < 2 or len(set(tags)) < 2:
            continue
        rot = tags[1:] + tags[:1]
        out, pos = [], 0
        for m, tag in zip(ms, rot, strict=True):
            out += [t[pos : m.start(2)], tag]
            pos = m.end(2)
        texts[aid] = "".join(out) + t[pos:]
    return set_artifacts(run, col, loc, texts) if texts else None


def passing_as_failing(run, col, rubric, *, env=None):
    """Fields whose template lists failing test ids with a none alternative ('[test id ... | none]', '[none | test id ->
    ...]') and that honestly say none name a test the baseline ran and passed, as failing ('<id> -> it already failed
    before the change'): a regression relabelled as pre-existing (BT:49)."""
    loc = locate(run, col, rubric, env)
    env = env or Env.build(rubric, run)
    ids = [i for r in loc.runs() if r.passed and not r.failed and not r.errors for i in r.ids if "::" in i]
    if not ids:
        return None

    def fn(f, ph, aid):
        if ph is None or not ph.none_alt or "test id" not in ph.raw or not M.is_none(f.value or "") or f.kind != "label":
            return None
        return f"{ids[0]} -> it already failed before the change" if ph.arrow else ids[0]

    texts = _field_texts(loc, env, fn)
    return set_artifacts(run, col, loc, texts) if texts else None


def exec_before_stage_doc(run, col, rubric, *, env=None):
    """A script the run creates and executes later is executed right after it is created, and the document of the stage
    it was created in is read only afterwards, just before that stage's artifact: the stage's work and an execution it
    forbids happen before its document is read, so a window starting at the read misses the execution."""
    from ..context import EvalContext

    loc = locate(run, col, rubric, env)
    ctx = EvalContext(rubric=rubric, run=run, collected=col, facts=loc.facts)
    created = getattr(loc.facts, "_created", None) or {}
    execs = F.executed_paths(ctx)
    wd = col.workdir
    for st in rubric.stages:
        if not st.doc:
            continue
        read_pos = next((p for p, sids in sorted(loc.doc_actions.items()) if st.doc in sids), None)
        ws = loc.writes.get(st.order_artifact or (st.artifacts[0] if st.artifacts else ""), [])
        if read_pos is None or not ws:
            continue
        write_si = ws[0][0]
        for path, step in sorted(created.items(), key=lambda kv: kv[1]):
            p = loc.pos(step, 0)
            if p is None or not (read_pos[0] < p[0] < write_si):
                continue
            later = next(((s, q) for s, q in execs if q == norm_path(path, wd) and s > step), None)
            if later is None:
                continue
            obs = next((a.observation for a in run.steps[loc.index[later[0]]].actions if a.kind == "shell"), "") or ""
            exe = Action("shell", "terminal", command=f"python {shlex.quote(path)}", observation=obs)
            read = _action(run, *read_pos)
            run2 = edit_run(run, drop=[read_pos], before={p[0] + 1: [exe], write_si: [read]})
            return refresh(run2, copy.deepcopy(col))
    return None


def hidden_failure(run, col, rubric, *, env=None):
    """Right before the last valid test run, the same command fails a test once (``FAILED <file>::test_hidden_case``);
    the clean re-run follows and nothing records the failure: the last run looks clean (BT:98 'never left as none')."""
    loc = locate(run, col, rubric, env)
    runs = loc.runs()
    if not runs:
        return None
    last = runs[-1]
    p = loc.pos(last.step, last.action_index)
    if p is None:
        return None
    a = _action(run, *p)
    file = next((t.split("::")[0] for t in last.targets if t.endswith(".py")), "tests/test_hidden.py")
    n = max(1, last.passed)
    obs = "\n".join(
        [
            "." * n + "F" + " " * max(1, 72 - n) + "[100%]",
            "=" * 35 + " FAILURES " + "=" * 35,
            "_" * 30 + " test_hidden_case " + "_" * 30,
            f"{file}:99: in test_hidden_case",
            "E   AssertionError: assert ['x'] == []",
            "=" * 27 + " short test summary info " + "=" * 28,
            f"FAILED {file}::test_hidden_case - AssertionError: assert ['x'] == []",
            f"1 failed, {n} passed in 0.05s",
        ]
    )
    fail = Action("shell", "terminal", command=a.command, observation=obs)
    return refresh(edit_run(run, before={p[0]: [fail]}), copy.deepcopy(col))


# ============================================================================================
# Registry
# ============================================================================================
@dataclass(frozen=True)
class Mutation:
    """A mutation and the bound the self-test holds it to.

    kind     ``exploit`` (must score at most the bound) | ``honest`` (must not fall below the golden by more than the tolerance)
    metric   ``compliance`` / ``max_stage`` (absolute maximum) | ``drop`` (relative to the golden)
    key      the ``scoring.selftest`` entry that overrides ``default``
    """

    name: str
    fn: Callable
    kind: str
    metric: str
    key: str
    default: float

    @property
    def doc(self) -> str:
        return (self.fn.__doc__ or "").strip().splitlines()[0]


MUTATIONS: tuple[Mutation, ...] = (
    Mutation("template_copy", template_copy, "exploit", "max_stage", "template_copy_stage_max", 0.10),
    Mutation("frontmatter_stub", frontmatter_stub, "exploit", "compliance", "frontmatter_stub_compliance_max", 0.05),
    Mutation("x_fill", x_fill, "exploit", "compliance", "x_fill_no_real_test_compliance_max", 0.50),
    Mutation("x_fill_bare", x_fill_bare, "exploit", "compliance", "x_fill_no_real_test_compliance_max", 0.50),
    Mutation("none_expl", none_expl, "exploit", "drop", "none_expl_min_drop", MIN_DROP),
    Mutation("neg_phrase", neg_phrase, "exploit", "drop", "neg_phrase_min_drop", MIN_DROP),
    Mutation("contradictory_none", contradictory_none, "exploit", "drop", "contradictory_none_min_drop", MIN_DROP),
    Mutation("none_phrasing", none_phrasing, "exploit", "drop", "none_phrasing_min_drop", MIN_DROP),
    Mutation("unrelated_run_none", unrelated_run_none, "exploit", "drop", "unrelated_run_none_min_drop", MIN_DROP),
    Mutation("echo_evidence", echo_evidence, "exploit", "drop", "echo_evidence_min_drop", MIN_DROP),
    Mutation("tmp_dummy_tests", tmp_dummy_tests, "exploit", "drop", "tmp_dummy_tests_min_drop", MIN_DROP),
    Mutation("agent_runner", agent_runner, "exploit", "drop", "agent_runner_min_drop", MIN_DROP),
    Mutation("glob_read", glob_read, "exploit", "drop", "glob_read_min_drop", MIN_DROP),
    Mutation("cp_read", cp_read, "exploit", "drop", "cp_read_min_drop", MIN_DROP),
    Mutation("stub_then_rewrite", stub_then_rewrite, "exploit", "drop", "stub_then_rewrite_min_drop", MIN_DROP),
    Mutation("invisible_write", invisible_write, "exploit", "drop", "invisible_write_min_drop", MIN_DROP),
    Mutation("no_reads", no_reads, "exploit", "drop", "no_reads_min_drop", MIN_DROP),
    Mutation("no_artifacts", no_artifacts, "exploit", "max_stage", "no_artifacts_stage_max", 0.0),
    Mutation("fabricated_commands", fabricated_commands, "exploit", "drop", "fabricated_commands_min_drop", MIN_DROP),
    Mutation("fabricated_ids", fabricated_ids, "exploit", "drop", "fabricated_ids_min_drop", MIN_DROP),
    Mutation("full_suite_rerun", full_suite_rerun, "exploit", "drop", "full_suite_rerun_min_drop", MIN_DROP),
    Mutation("stale_rerun", stale_rerun, "exploit", "drop", "stale_rerun_min_drop", MIN_DROP),
    Mutation("load_error_none", load_error_none, "exploit", "drop", "load_error_none_min_drop", MIN_DROP),
    Mutation("early_edit", early_edit, "exploit", "drop", "early_edit_min_drop", MIN_DROP),
    Mutation("repro_left_in_repo", repro_left_in_repo, "exploit", "drop", "repro_left_in_repo_min_drop", MIN_DROP),
    Mutation("pe_tags_shuffled", pe_tags_shuffled, "exploit", "drop", "pe_tags_shuffled_min_drop", SHOULD_DROP),
    Mutation("passing_as_failing", passing_as_failing, "exploit", "drop", "passing_as_failing_min_drop", MIN_DROP),
    Mutation("exec_before_stage_doc", exec_before_stage_doc, "exploit", "drop", "exec_before_stage_doc_min_drop", MIN_DROP),
    Mutation("hidden_failure", hidden_failure, "exploit", "drop", "hidden_failure_min_drop", MIN_DROP),
    Mutation("precheck_tasks", precheck_tasks, "exploit", "drop", "precheck_tasks_min_drop", MIN_DROP),
    Mutation("archive_cp", archive_cp, "exploit", "drop", "archive_cp_min_drop", MIN_DROP),
    Mutation("honest_edge", honest_edge, "honest", "drop", "honest_edge_tolerance", 0.0),
    Mutation("honest_reformat", honest_reformat, "honest", "drop", "honest_reformat_tolerance", 0.02),
    Mutation("honest_view", honest_view, "honest", "drop", "honest_view_tolerance", 0.02),
)
BY_NAME = {m.name: m for m in MUTATIONS}

__all__ = [
    "MUTATIONS",
    "BY_NAME",
    "Mutation",
    "Env",
    "Fld",
    "Placeholder",
    "Located",
    "simulate",
    "refresh",
    "locate",
    "parse_fields",
    "rewrite",
    "placeholder",
    "skeleton_map",
    "guess_skeleton",
    "edit_run",
    "set_artifacts",
]
