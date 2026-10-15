"""What the run left in the sandbox, read before the verifier touches it -> ``context.Collected``.

Two moments, two calls:

* :func:`task_info` runs at ``resolve`` time -- after the task environment is set up, before
  ``hide_git_history`` swaps ``.git`` for a one-commit stand-in and before the agent can commit --
  so ``HEAD`` there is the task's base commit. It records the workdir, that SHA and the
  pre-agent ``git status``.
* :func:`collect` runs in ``evaluate``, before the inner verifier (which applies test patches and
  runs tests): the files under the rubric's artifact roots, the repository diff against the base
  SHA, and which paths the run talks about existed at that SHA (runner scripts, test targets,
  paths named in artifacts) -- the facts that let checks tell a real test run from an agent-made
  ``bin/test`` or a ``/tmp`` dummy.

Everything in the sandbox is the agent's to shape, so reading it must not fail because of it:
``find`` without ``-L`` (symlinks are not followed), at most :data:`MAX_FILES` files of at most
:data:`MAX_BYTES` each (``head -c``) within a :data:`MAX_TOTAL_BYTES` budget, ``timeout`` inside
the shell, ``; true`` at the end (``Sandbox.exec`` raises on a non-zero exit), and every path and
body base64-encoded under a marker line, so no file name or content can forge a record. Artifact
locations are read first, so a run that floods its artifact root with files still has its
artifacts collected. The code root is never collected wholesale -- only the artifact locations
that live under it.

Failures land in ``Collected.errors``; nothing here raises. Git runs read-only:
``-c safe.directory='*'`` (images often own the repo as another uid), ``GIT_OPTIONAL_LOCKS=0``
(``status`` would otherwise refresh the index), ``core.fsmonitor=false`` (a repo config hook
must not run as root here) and ``--literal-pathspecs`` (a path from the trace is a path, not a
pattern).
"""

from __future__ import annotations

import base64
import binascii
import logging
import posixpath
import re
import shlex
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from . import refs
from .context import Collected
from .schema import Rubric
from .trace.model import Run

logger = logging.getLogger(__name__)

MAX_FILES = 500
MAX_BYTES = 256 * 1024
MAX_DEPTH = 8
MAX_DIRS = 2000
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_GIT_BYTES = 4 * 1024 * 1024
MAX_CANDIDATES = 2000
MAX_COMMAND_CHARS = 32 * 1024  # of each command, when looking for paths in it
SHELL_TIMEOUT = 20  # inside the shell
EXEC_TIMEOUT = 60  # client side, the backend's own deadline
PRUNE = (".git", "node_modules", "__pycache__")

_MARK = "@@WFR"
_FAIL = b"\x01WFRFAIL"  # appended to a git listing whose command failed
_GIT = "GIT_OPTIONAL_LOCKS=0 git -c safe.directory='*' -c core.fsmonitor=false --literal-pathspecs"
_PH = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SHA = re.compile(r"[0-9a-f]{7,64}")
_BATCH_CHARS = 48_000


@dataclass
class TaskInfo:
    """The task repository before the agent ran, bound to one rollout's evaluator.

    pre_status is the raw ``git status --porcelain=v1 -z`` text (NUL-separated); see
    :func:`status_paths`.
    """

    workdir: str | None = None
    base_sha: str | None = None
    pre_status: str | None = None
    errors: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------------------
# Shell plumbing
# --------------------------------------------------------------------------------------------
def _command(script: str, seconds: int = SHELL_TIMEOUT) -> str:
    """``script`` under ``timeout`` when the image has a usable one, always exiting 0."""
    probe = "T=; timeout 5 true >/dev/null 2>&1 && T=" + shlex.quote(f"timeout {seconds}")
    return f"{probe}; $T sh -c {shlex.quote(script)}; true"


def _exec(sandbox, script: str) -> str:
    out = sandbox.exec(_command(script), timeout=EXEC_TIMEOUT, user="root")
    if isinstance(out, bytes):
        return out.decode("utf-8", errors="replace")
    return out if isinstance(out, str) else ""


def _short(e: BaseException) -> str:
    msg = str(e).strip().replace("\n", " ")
    return f"{type(e).__name__}: {msg[:300]}"


def _unb64(s: str) -> bytes:
    s = s.strip()
    s = s[: len(s) // 4 * 4]  # a line cut short still decodes up to the cut
    try:
        return base64.b64decode(s)
    except (binascii.Error, ValueError):
        return b""


def _b64path(s: str) -> str | None:
    p = _unb64(s).decode("utf-8", errors="replace")
    if not p.startswith("/") or "\x00" in p:
        return None
    return _normabs(p)


def _normabs(p: str) -> str:
    return posixpath.normpath("/" + p.lstrip("/"))


def _records(output: str) -> Iterator[tuple[str, str, str | None]]:
    """(tag, arg, next line) for every marker line; the next line is a record's body when it is not a marker."""
    lines = (output or "").replace("\r", "").split("\n")
    for i, line in enumerate(lines):
        if not line.startswith(_MARK + " "):
            continue
        tag, _, arg = line[len(_MARK) + 1 :].partition(" ")
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        yield tag, arg.strip(), (None if nxt is None or nxt.startswith(_MARK) else nxt)


# --------------------------------------------------------------------------------------------
# Task info (resolve time)
# --------------------------------------------------------------------------------------------
def _tools(*names: str) -> str:
    """A missing tool would make its listing silently empty; say so instead."""
    return f'for t in {" ".join(names)}; do command -v "$t" >/dev/null 2>&1 || echo "{_MARK} NOTOOL $t"; done'


def _task_info_script(workdir: str | None) -> str:
    cd = f"cd {shlex.quote(workdir)} 2>/dev/null || {{ echo '{_MARK} NOWD'; echo '{_MARK} END'; exit 0; }}" if workdir else ":"
    return "\n".join(
        [
            f"echo '{_MARK} BEGIN'",
            _tools("git", "base64", "head"),
            cd,
            f'printf \'{_MARK} WD %s\\n\' "$(printf %s "$PWD" | base64 -w0)"',
            f"printf '{_MARK} HEAD %s\\n' \"$({_GIT} rev-parse -q --verify HEAD 2>/dev/null)\"",
            f"echo '{_MARK} STATUS'",
            f"{{ {_GIT} status --porcelain=v1 -z 2>/dev/null || printf '\\001WFRFAIL'; }} | head -c {MAX_GIT_BYTES} | base64 -w0; echo",
            f"echo '{_MARK} END'",
        ]
    )


def parse_task_info(output: str, workdir: str | None) -> TaskInfo:
    info = TaskInfo(workdir=workdir)
    seen: set[str] = set()
    for tag, arg, body in _records(output):
        seen.add(tag)
        if tag == "NOTOOL":
            info.errors.append(f"task_info: {arg} not found in the sandbox")
        elif tag == "NOWD":
            info.errors.append(f"task_info: cannot cd to {workdir}")
        elif tag == "WD" and not (workdir and workdir.startswith("/")):
            info.workdir = _b64path(arg)
        elif tag == "HEAD":
            sha = arg.strip()
            if _SHA.fullmatch(sha):
                info.base_sha = sha
        elif tag == "STATUS":
            raw = _unb64(body or "")
            if raw.endswith(_FAIL):
                info.errors.append("task_info: git status failed")
            else:
                info.pre_status = raw.decode("utf-8", errors="replace")
    if "BEGIN" not in seen:
        info.errors.append("task_info: no output")
    elif "END" not in seen:
        info.errors.append("task_info: output cut short")
    elif "NOWD" not in seen and info.base_sha is None:
        info.errors.append(f"task_info: no git HEAD in {info.workdir}")
    return info


def task_info(sandbox, task) -> TaskInfo:
    """Workdir (``task.metadata["workdir"]`` or the sandbox's cwd), HEAD and ``git status``; never raises."""
    meta = getattr(task, "metadata", None)
    wd = meta.get("workdir") if isinstance(meta, dict) else None
    wd = _normabs(str(wd)) if isinstance(wd, str) and wd.startswith("/") else (str(wd) if wd else None)
    try:
        return parse_task_info(_exec(sandbox, _task_info_script(wd)), wd)
    except Exception as e:  # noqa: BLE001 -- a sandbox failure is recorded, never raised
        logger.warning("task_info failed for %s: %s", getattr(task, "id", "?"), _short(e))
        return TaskInfo(workdir=wd if wd and wd.startswith("/") else None, errors=[f"task_info: {_short(e)}"])


def status_paths(pre_status: str | None) -> dict[str, str]:
    """``git status --porcelain=v1 -z`` -> repo-relative path -> two-letter status (renames: the new path)."""
    out: dict[str, str] = {}
    toks = (pre_status or "").split("\x00")
    i = 0
    while i < len(toks):
        t = toks[i]
        i += 1
        if len(t) < 4:
            continue
        xy, path = t[:2], t[3:]
        out[path] = xy
        if "R" in xy or "C" in xy:
            i += 1  # the source path follows
    return out


# --------------------------------------------------------------------------------------------
# What to read: roots, artifact locations, var children
# --------------------------------------------------------------------------------------------
def resolve_roots(rubric: Rubric, workdir: str | None) -> dict[str, str | None]:
    """Root name -> absolute path (``{WORKDIR}`` and other roots substituted); None when unresolvable.

    ``code`` defaults to the workdir when the rubric does not name it.
    """
    raw = {**{"code": "{WORKDIR}"}, **{str(k): str(v) for k, v in (rubric.roots or {}).items()}}
    out: dict[str, str | None] = {}

    def res(name: str, depth: int) -> str | None:
        if depth > 8:
            return None
        text = raw[name]
        for key in set(_PH.findall(text)):
            if key == "WORKDIR":
                val = workdir
            elif key in raw and key != name:
                val = res(key, depth + 1)
            else:
                val = None
            if val is None:
                return None
            text = text.replace("{" + key + "}", val)
        return _absolute(text, workdir)

    for name in raw:
        out[name] = res(name, 0)
    return out


def _absolute(p: str, workdir: str | None) -> str | None:
    if not p.startswith("/"):
        if not workdir:
            return None
        p = f"{workdir}/{p}"
    return _normabs(p)


def expand(template: str, roots: dict[str, str | None], workdir: str | None) -> str | None:
    """A location template with roots substituted; var placeholders (``{FEATURE}``) are kept."""
    text = template
    for key in set(_PH.findall(template)):
        if key in roots or key == "WORKDIR":
            val = workdir if key == "WORKDIR" else roots[key]
            if val is None:
                return None
            text = text.replace("{" + key + "}", val)
    return _absolute(text, workdir)


def shell_glob(path: str) -> str:
    """An absolute path with ``{VAR}`` placeholders -> a shell word: static parts quoted, each var a ``*``."""
    words = []
    for comp in path.split("/"):
        if comp:
            words.append("*".join(shlex.quote(s) if s else "" for s in _PH.split(comp)[0::2]))
    return "/" + "/".join(words)


def _code_like(path: str, workdir: str | None) -> bool:
    if path == "/":
        return True
    return bool(workdir) and (path == workdir or workdir.startswith(path.rstrip("/") + "/"))


@dataclass
class ScanPlan:
    """roots: scanned wholesale with ``find``; file_globs / dir_globs: shell words for artifact locations and var children."""

    roots: list[str] = field(default_factory=list)
    file_globs: list[str] = field(default_factory=list)
    dir_globs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def scan_plan(rubric: Rubric, workdir: str | None) -> ScanPlan:
    roots = resolve_roots(rubric, workdir)
    plan = ScanPlan()
    used: list[str] = []

    def note_roots(template: str) -> None:
        for key in _PH.findall(template):
            if key in roots and key not in used:
                used.append(key)

    for a in rubric.artifacts.values():
        for loc in a.locations:
            note_roots(loc)
            p = expand(loc, roots, workdir)
            if p is None:
                plan.errors.append(f"collect: artifact {a.id}: cannot resolve {loc!r} (workdir {workdir})")
                continue
            g = shell_glob(p)
            target = plan.dir_globs if a.kind == "dir" else plan.file_globs
            if g not in target:
                target.append(g)
    for v in rubric.vars.values():
        note_roots(v.under)
        p = expand(v.under, roots, workdir)
        if p is None:
            plan.errors.append(f"collect: var {v.name}: cannot resolve {v.under!r} (workdir {workdir})")
            continue
        g = shell_glob(p.rstrip("/") + "/{_}")
        if g not in plan.dir_globs:
            plan.dir_globs.append(g)
    whole = [p for p in (roots[k] for k in used) if p and not _code_like(p, workdir)]
    for p in sorted(set(whole), key=len):
        if not any(p == q or p.startswith(q.rstrip("/") + "/") for q in plan.roots):
            plan.roots.append(p)
    return plan


# --------------------------------------------------------------------------------------------
# Exec 1: files and directories
# --------------------------------------------------------------------------------------------
_ENC_EXEC = "-exec sh -c 'for f; do printf %s \"$f\" | base64 -w0; echo; done' sh {} +"


def _find(kind: str, roots: list[str]) -> str:
    prune = " -o ".join(f"-name {shlex.quote(n)}" for n in PRUNE)
    rs = " ".join(shlex.quote(r) for r in roots)
    return f'for r in {rs}; do [ -d "$r" ] && find -H "$r" -maxdepth {MAX_DEPTH} \\( {prune} \\) -prune -o -type {kind} {_ENC_EXEC} 2>/dev/null; done'


def files_script(plan: ScanPlan) -> str:
    m = MAX_BYTES + 1  # one byte past the limit marks a truncated file
    files, dirs = [], []
    if plan.file_globs:
        files.append(f'for f in {" ".join(plan.file_globs)}; do [ -f "$f" ] && [ ! -L "$f" ] && enc "$f"; done')
    if plan.dir_globs:
        dirs.append(f'for d in {" ".join(plan.dir_globs)}; do [ -d "$d" ] && [ ! -L "$d" ] && enc "$d"; done')
    if plan.roots:
        files.append(_find("f", plan.roots))
        dirs.append(_find("d", plan.roots))
    lines = [
        f"M={m}; N={MAX_FILES}; B={MAX_TOTAL_BYTES}; D={MAX_DIRS}",
        'enc() { printf %s "$1" | base64 -w0; echo; }',
        f"echo '{_MARK} BEGIN'",
        _tools("base64", "head", "awk", "find"),
    ]
    if files:
        lines += [
            "{",
            *files,
            "} | awk '!s[$0]++' | head -n $((N+1)) | {",
            "i=0; t=0",
            "while IFS= read -r b; do",
            "  i=$((i+1))",
            f'  if [ "$i" -gt "$N" ]; then echo \'{_MARK} MORE\'; break; fi',
            '  f=$(printf %s "$b" | base64 -d 2>/dev/null)',
            '  s=$(stat -c %s "$f" 2>/dev/null) || s=$M',
            "  case $s in ''|*[!0-9]*) s=$M;; esac",
            '  [ "$s" -gt "$M" ] && s=$M',
            "  t=$((t+s))",
            f'  if [ "$t" -gt "$B" ]; then echo "{_MARK} SKIP $b"; continue; fi',
            f'  echo "{_MARK} F $b"',
            '  head -c "$M" "$f" 2>/dev/null | base64 -w0; echo',
            "done",
            "}",
        ]
    if dirs:
        lines += ["{", *dirs, f'}} | awk \'!s[$0]++\' | head -n "$D" | while IFS= read -r b; do echo "{_MARK} D $b"; done']
    lines.append(f"echo '{_MARK} END'")
    return "\n".join(lines)


def parse_files(output: str, c: Collected) -> None:
    """Fill ``c.files`` / ``truncated`` / ``dirs`` from the scan's output, enforcing the limits again."""
    seen: set[str] = set()
    n, more, skipped, last = 0, False, 0, None
    for tag, arg, body in _records(output):
        seen.add(tag)
        if tag == "F":
            path = _b64path(arg)
            if path is None:
                continue
            if n >= MAX_FILES:
                more = True
                continue
            n += 1
            raw = _unb64(body) if body is not None else b""
            c.files[path] = raw[:MAX_BYTES].decode("utf-8", errors="replace")
            if len(raw) > MAX_BYTES or body is None:
                c.truncated.add(path)
            last = path
        elif tag == "SKIP":
            path = _b64path(arg)
            if path is not None and n < MAX_FILES:
                n += 1
                skipped += 1
                c.files[path] = ""
                c.truncated.add(path)
        elif tag == "MORE":
            more = True
        elif tag == "NOTOOL":
            c.errors.append(f"collect: {arg} not found in the sandbox")
        elif tag == "D":
            path = _b64path(arg)
            if path is not None and len(c.dirs) < MAX_DIRS:
                c.dirs.add(path)
    for path in list(c.files):
        parent = posixpath.dirname(path)
        while parent not in ("/", "") and parent not in c.dirs:
            c.dirs.add(parent)
            parent = posixpath.dirname(parent)
    if "BEGIN" not in seen:
        c.errors.append("collect: no output from the file scan")
    elif "END" not in seen:
        c.errors.append("collect: file scan cut short (shell timeout?)")
        if last is not None:
            c.truncated.add(last)
    if more:
        c.errors.append(f"collect: more than {MAX_FILES} files under the artifact roots; only {MAX_FILES} were read")
    if skipped:
        c.errors.append(f"collect: {skipped} files not read: the {MAX_TOTAL_BYTES}-byte budget was spent")


# --------------------------------------------------------------------------------------------
# Exec 2: git diff, untracked files, base-tree membership
# --------------------------------------------------------------------------------------------
_KNOWN_EXT = frozenset("py pyi pyx js jsx mjs cjs ts tsx go rs rb java kt scala c cc cpp h hpp cs php sh bash pl lua swift r toml cfg ini json yaml yml txt md rst lock xml html css sql".split())
_TOKEN = re.compile(r"[\w./@+-]+")
_DOTTED = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")
_URL = re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]*://\S+")
_TEXT_PATH = re.compile(r"(?<![\w/.-])(?:\.{0,2}/)?[\w.-]+(?:/[\w.-]+)+/?|(?<![\w/.-])[\w-]+\.(?:" + "|".join(sorted(_KNOWN_EXT)) + r")\b")
_HEREDOC = re.compile(r"(?<!<)<<-?\s*(['\"]?)([A-Za-z_][\w.-]*)\1")
_OPS = frozenset({"&&", "||", ";", "|", "&", ";;", "(", ")", "|&"})
_WRAPPERS = frozenset({"sudo", "env", "nice", "time", "nohup", "stdbuf", "timeout", "command", "exec"})


def _strip_heredocs(command: str) -> str:
    lines, out, i = command.split("\n"), [], 0
    while i < len(lines):
        out.append(lines[i])
        delims = [m.group(2) for m in _HEREDOC.finditer(lines[i])]
        i += 1
        for d in delims:
            while i < len(lines) and lines[i].strip() != d:
                i += 1
            i += 1
    return "\n".join(out)


def _lex(line: str) -> list[str]:
    try:
        lx = shlex.shlex(line, posix=True, punctuation_chars=True)
        lx.whitespace_split = True
        return list(lx)
    except ValueError:
        return line.split()


def _segments(command: str) -> list[list[str]]:
    segs: list[list[str]] = []
    for line in _strip_heredocs(command.replace("\\\n", " ")).split("\n"):
        cur: list[str] = []
        for tok in _lex(line):
            if tok in _OPS:
                if cur:
                    segs.append(cur)
                cur = []
            else:
                cur.append(tok)
        if cur:
            segs.append(cur)
    return segs


def _unwrap(seg: list[str]) -> list[str]:
    i = 0
    while i < len(seg) and (re.fullmatch(r"[A-Za-z_]\w*=.*", seg[i]) or seg[i] in _WRAPPERS or (i and seg[i - 1] == "timeout" and re.fullmatch(r"[\d.]+[smhd]?", seg[i]))):
        i += 1
    return seg[i:]


def _rel(path: str, workdir: str) -> str | None:
    p = _normabs(path)
    if p.startswith(workdir.rstrip("/") + "/"):
        return p[len(workdir.rstrip("/")) + 1 :]
    return None


def _clean(tok: str) -> str | None:
    if tok.startswith("-"):
        if "=" not in tok:
            return None
        tok = tok.split("=", 1)[1]
    tok = tok.split("::", 1)[0]
    tok = re.sub(r":\d+(?::\d+)?$", "", tok).rstrip("/")
    if not tok or len(tok) > 512 or tok in (".", "..") or not _TOKEN.fullmatch(tok):
        return None
    return tok


def _forms(tok: str, cwd: str | None, workdir: str) -> list[str]:
    """Repo-relative spellings of a path token: resolved against the cwd, and as written."""
    if tok.startswith("/"):
        r = _rel(tok, workdir)
        return [r] if r else []
    out = []
    if cwd:
        r = _rel(posixpath.join(cwd, tok), workdir)
        if r:
            out.append(r)
    plain = posixpath.normpath(tok)
    if not plain.startswith("..") and plain != "." and plain not in out:
        out.append(plain)
    return out


def _is_pathish(tok: str) -> bool:
    return "/" in tok or ("." in tok and tok.rsplit(".", 1)[-1].lower() in _KNOWN_EXT)


def _run_tokens(run: Run, workdir: str) -> Iterator[tuple[int, str]]:
    """(priority, repo-relative path) for every path-like token the run used; cwd tracked across calls."""
    cwd: str | None = workdir
    for step in run.steps:
        for a in step.actions:
            if a.kind == "shell" and a.command:
                for seg in _segments(a.command[:MAX_COMMAND_CHARS]):
                    seg = _unwrap(seg)
                    if not seg:
                        continue
                    if seg[0] == "cd":
                        target = seg[1] if len(seg) > 1 else "~"
                        target = "/root" + target[1:] if target.startswith("~") else target
                        if target == "-":
                            pass
                        elif not _TOKEN.fullmatch(target):
                            cwd = None  # `cd "$(dirname x)"`: unknown until the next absolute cd
                        elif target.startswith("/") or cwd is not None:
                            cwd = _normabs(posixpath.join(cwd or "/", target))
                        continue
                    for j, raw in enumerate(seg):
                        tok = _clean(raw)
                        if tok is None or not re.search(r"[A-Za-z]", tok):
                            continue
                        if _is_pathish(tok):
                            yield from ((0, f) for f in _forms(tok, cwd, workdir))
                        elif _DOTTED.fullmatch(tok) and tok.count(".") <= 6:
                            parts = tok.split(".")
                            for k in range(1, len(parts) + 1):
                                stem = "/".join(parts[:k])
                                yield from ((2, f) for f in (*_forms(stem, cwd, workdir), *_forms(stem + ".py", cwd, workdir)))
                        elif j:  # a bare word argument (`pytest tests`), never the bare verb
                            yield from ((1, f) for f in _forms(tok, cwd, workdir))
            elif a.path and isinstance(a.path, str):
                tok = _clean(a.path)
                if tok:
                    yield from ((0, f) for f in _forms(tok, cwd, workdir))


def _text_tokens(files: dict[str, str], workdir: str) -> Iterator[tuple[int, str]]:
    for text in files.values():
        body = text[: 64 * 1024]
        body = _URL.sub(" ", body) if "://" in body else body
        for m in list(_TEXT_PATH.finditer(body))[:300]:
            p = refs.norm_path(m.group(0), workdir)
            tok = _clean(p)
            if tok is None:
                continue
            if tok.startswith("/"):
                yield from ((0, f) for f in _forms(tok, None, workdir))
            else:
                plain = posixpath.normpath(tok)
                if not plain.startswith(".."):
                    yield 0, plain


def candidate_paths(run: Run | None, files: dict[str, str], workdir: str) -> list[str]:
    """Repo-relative paths worth asking the base tree about, most useful first, at most :data:`MAX_CANDIDATES`."""
    found: dict[str, int] = {}
    sources: list[Iterable[tuple[int, str]]] = [_text_tokens(files, workdir)]
    if run is not None:
        sources.insert(0, _run_tokens(run, workdir))
    for src in sources:
        for prio, p in src:
            if p and "\x00" not in p and "\n" not in p and len(p) <= 512 and prio < found.get(p, 9):
                found[p] = prio
    ranked = sorted(found, key=lambda p: found[p])  # stable: first-seen order within a priority
    return ranked[:MAX_CANDIDATES]


def _batches(paths: list[str]) -> list[list[str]]:
    out: list[list[str]] = []
    cur: list[str] = []
    size = 0
    for p in paths:
        q = len(shlex.quote(p)) + 1
        if cur and size + q > _BATCH_CHARS:
            out.append(cur)
            cur, size = [], 0
        cur.append(p)
        size += q
    if cur:
        out.append(cur)
    return out


def _listing(cmd: str) -> str:
    return f"{{ {cmd} 2>/dev/null || printf '\\001WFRFAIL'; }} | head -c {MAX_GIT_BYTES} | base64 -w0; echo"


def git_script(workdir: str, base_sha: str, paths: list[str], diff: bool = True) -> str:
    sha = shlex.quote(base_sha)
    lines = [
        f"cd {shlex.quote(workdir)} 2>/dev/null || {{ echo '{_MARK} NOWD'; exit 0; }}",
        f'G() {{ {_GIT} "$@"; }}',
        f"echo '{_MARK} BEGIN'",
        f"if G rev-parse -q --verify {shlex.quote(base_sha + '^{commit}')} >/dev/null 2>&1; then",
    ]
    if diff:
        lines += [
            f"echo '{_MARK} DIFF'",
            _listing(f"G diff --name-status --no-renames -z --relative {sha}"),
            f"echo '{_MARK} UNTRACKED'",
            _listing("G ls-files --others --exclude-standard -z"),
        ]
    if paths:
        lines += [f"echo '{_MARK} TREE'", _listing(f"G ls-tree -t --name-only -z {sha} -- " + " ".join(shlex.quote(p) for p in paths))]
    lines += ["else", f"echo '{_MARK} NOSHA'", "fi", f"echo '{_MARK} END'"]
    return "\n".join(lines)


def _nul_list(raw: bytes, what: str, c: Collected) -> list[str] | None:
    if raw.endswith(_FAIL):
        c.errors.append(f"collect: git {what} failed")
        return None
    toks = raw.split(b"\x00")
    if len(raw) >= MAX_GIT_BYTES:
        c.errors.append(f"collect: git {what} output truncated at {MAX_GIT_BYTES} bytes")
        toks = toks[:-1]
    return [t.decode("utf-8", errors="replace") for t in toks if t]


def parse_git(output: str, c: Collected, paths: list[str]) -> None:
    """Fill ``c.diff`` / ``c.base_present`` from a :func:`git_script` run (diff only when it was asked for)."""
    seen: set[str] = set()
    diff: dict[str, str] | None = None
    for tag, _arg, body in _records(output):
        seen.add(tag)
        if tag == "NOWD":
            c.errors.append(f"collect: cannot cd to {c.workdir}")
        elif tag == "NOSHA":
            c.errors.append(f"collect: base sha {c.base_sha} not in the repository")
        elif tag == "DIFF":
            toks = _nul_list(_unb64(body or ""), "diff", c)
            if toks is not None:
                diff = {}
                for st, path in zip(toks[0::2], toks[1::2], strict=False):
                    s = st[:1].upper()
                    diff[path] = s if s in ("A", "D", "M") else "M"
        elif tag == "UNTRACKED":
            toks = _nul_list(_unb64(body or ""), "ls-files", c)
            if toks is not None and diff is not None:
                for path in toks:
                    diff.setdefault(path, "?")
        elif tag == "TREE":
            toks = _nul_list(_unb64(body or ""), "ls-tree", c)
            if toks is not None:
                present = set(toks)
                bp = c.base_present if c.base_present is not None else {}
                bp.update(dict.fromkeys(present, True))
                for p in paths:
                    bp.setdefault(p, p in present)
                c.base_present = bp
    if "BEGIN" in seen and not seen & {"NOWD", "NOSHA"} and c.base_present is None:
        c.base_present = {}
    if diff is not None:
        c.diff = diff
        bp = c.base_present if c.base_present is not None else {}
        for path, s in diff.items():
            bp.setdefault(path, s in ("M", "D"))
        c.base_present = bp
    if "BEGIN" not in seen and "NOWD" not in seen:
        c.errors.append("collect: no output from git")
    elif "END" not in seen:
        c.errors.append("collect: git step cut short (shell timeout?)")


# --------------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------------
def collect(sandbox, rubric: Rubric, info: TaskInfo, run: Run | None) -> Collected:
    """Artifact files, repository diff and base-tree membership, online; never raises."""
    c = Collected(workdir=info.workdir, base_sha=info.base_sha, pre_status=info.pre_status, errors=list(info.errors), mode="online")
    try:
        plan = scan_plan(rubric, c.workdir)
        c.errors.extend(plan.errors)
        if plan.roots or plan.file_globs or plan.dir_globs:
            parse_files(_exec(sandbox, files_script(plan)), c)
    except Exception as e:  # noqa: BLE001
        logger.warning("collect: file scan failed: %s", _short(e))
        c.errors.append(f"collect: file scan failed: {_short(e)}")
    if not (c.workdir and c.base_sha and _SHA.fullmatch(c.base_sha)):
        return c
    try:
        batches = _batches(candidate_paths(run, c.files, c.workdir)) or [[]]
    except Exception as e:  # noqa: BLE001
        c.errors.append(f"collect: candidate paths failed: {_short(e)}")
        batches = [[]]
    for i, batch in enumerate(batches):
        try:
            parse_git(_exec(sandbox, git_script(c.workdir, c.base_sha, batch, diff=i == 0)), c, batch)
        except Exception as e:  # noqa: BLE001
            logger.warning("collect: git step failed: %s", _short(e))
            c.errors.append(f"collect: git step failed: {_short(e)}")
    return c


__all__ = ["MAX_BYTES", "MAX_FILES", "TaskInfo", "candidate_paths", "collect", "resolve_roots", "scan_plan", "status_paths", "task_info"]
