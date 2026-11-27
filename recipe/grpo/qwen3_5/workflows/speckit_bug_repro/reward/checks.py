"""speckit_bug_repro's own penalty item: the code was run before the assessment proposed a remediation.

``speckit_bug_repro.reproduction`` reads the trace only. The *plan step* is the first successful write of
``assessment.md`` that carries a **Proposed Remediation** (a first write without one -- a skeleton filled in later --
is not yet the plan; when no write shows one, the first write stands). The item is kept when, at a step before it,
the run did one of:

    test run      a valid repository test run (``evidence.runs_from``: the runner's own summary, N >= 1 tests, on
                  tests that existed before the run) -- whatever it selected, whatever it reported
    script        it executed a file it had created (``python repro.py``, ``pytest`` on a test file it wrote, a
                  shell script that does one of the things below)
    inline code   ``python -c`` / a heredoc that imports the repository's package and does something with it
    command line  the repository's own command (``python -m <package>``, ``<package> ...``, ``<package>-build ...``)

Not a run of the code: looking it up (``inspect.getsource``, ``__file__``, ``__version__``, ``help()``,
``dir()``), an import and nothing else, ``--help`` / ``--version``, python that only reads or writes files.

``issue_terms``: a script or inline code must also name something the issue names -- an
identifier from the issue text (``snake_case``, ``CamelCase``, a dotted name, a called name, anything in backticks or
a code block), the package's own name and Python's builtins aside. An issue that names nothing asks nothing here.
A test run and the repository's command line are taken as they are. The rubric item has it OFF: on 1,455 saved
speckit_bug runs it turned 11 of 775 kept items into failures, and most of the ones read were reproductions whose
issue named only short things (``Min()``, ``S(0.0)``, ``foo(a, b=0, /, c=1)``).

What the task gives (``inputs``, next to speckit_bug's gold files): the issue text and the import names of the
repository's packages, read off the gold table's paths for every task of the same repository (``django/...`` ->
``django``; ``src/_pytest/...`` -> ``_pytest``). For a repository the table does not know, the top-level directories
the run itself changed stand in.

Worth, as a penalty item (``workflow_rubric/penalty.py``): 1 kept, 0 not kept, 0 for a run that wrote no assessment
(it stands outside the item, having planned nothing).
"""

from __future__ import annotations

import builtins
import keyword
import posixpath
import re
from collections import Counter

from recipe.grpo.qwen3_5.workflow_rubric import evidence, refs
from recipe.grpo.qwen3_5.workflow_rubric import penalty as PEN
from recipe.grpo.qwen3_5.workflow_rubric.checks import register
from recipe.grpo.qwen3_5.workflow_rubric.context import EvalContext, Result
from recipe.grpo.qwen3_5.workflow_rubric.facts import change_paths
from recipe.grpo.qwen3_5.workflow_rubric.schema import Item
from recipe.grpo.qwen3_5.workflow_rubric.trace import shell

from ...speckit_bug.reward import checks as base

MAX_CODE = 200_000  # characters of agent-written code looked at
MAX_ISSUE = 100_000
MAX_TERMS = 400
_DEPTH = 2  # a shell script that runs a script: followed this far

# --------------------------------------------------------------------------------------------
# What the task gives: the issue text, the repository's package names
# --------------------------------------------------------------------------------------------
_LAYOUT_DIRS = ("src", "lib")  # ``src/<package>/...`` layouts: the package is the next component
_NOT_PACKAGES = frozenset({"setup", "conftest", "docs", "doc", "examples", "example", "scripts", "tools", "ci", "benchmarks", "asv_bench", "tests", "test", "testing", "build", "misc", "plugins"})
_MIN_SHARE = 0.05  # of a repository's gold paths: one stray path under ``tools/`` does not make ``tools`` a package
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
# import names the gold paths do not show: pytest's code lives in ``_pytest``, and is imported as ``pytest``
_ALSO = {"pytest-dev__pytest": ("pytest",)}
_PACKAGES: dict[str, tuple[str, ...]] | None = None


def package_of(path: str) -> str | None:
    """The import name a repository path belongs to: its first component (the second under ``src/`` / ``lib/``),
    ``.py`` dropped; None for a path that names no importable module."""
    parts = [p for p in (path or "").split("/") if p]
    if len(parts) > 2 and parts[0] in _LAYOUT_DIRS:
        parts = parts[1:]
    if not parts or (len(parts) == 1 and not parts[0].endswith(".py")):
        return None
    name = parts[0][:-3] if parts[0].endswith(".py") else parts[0]
    return name if _IDENT.match(name) and name not in _NOT_PACKAGES else None


def _repo(instance_id: str) -> str:
    return instance_id.rsplit("-", 1)[0]


def packages_table() -> dict[str, tuple[str, ...]]:
    """Repository (``owner__name``) -> its packages' import names, from every gold path of its tasks."""
    global _PACKAGES
    if _PACKAGES is None:
        counts: dict[str, Counter] = {}
        for tid, g in base._gold_table().items():
            c = counts.setdefault(_repo(tid), Counter())
            for p in g["src"]:
                c[package_of(p) or ""] += 1
        _PACKAGES = {repo: tuple(sorted({n for n, k in c.items() if n and k >= _MIN_SHARE * sum(c.values())} | set(_ALSO.get(repo, ())))) for repo, c in counts.items()}
    return _PACKAGES


def _issue_text(task) -> str:
    for src in (task, getattr(task, "metadata", None)):
        for key in ("instruction", "question", "problem_statement"):
            v = src.get(key) if isinstance(src, dict) else getattr(src, key, None)
            if isinstance(v, str) and v.strip():
                return v[:MAX_ISSUE]
    return ""


def inputs(task, episode) -> dict:
    """speckit_bug's inputs (the gold source files) plus the issue text and the repository's package names."""
    out = base.inputs(task, episode)
    out["issue"] = _issue_text(task)
    out["packages"] = list(packages_table().get(_repo(base._instance_id(task)), ()))
    return out


post = base.post


# --------------------------------------------------------------------------------------------
# What the issue names
# --------------------------------------------------------------------------------------------
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_FENCE = re.compile(r"```.*?(?:```|\Z)|`[^`\n]+`", re.S)
_INDENTED = re.compile(r"^(?: {4,}|\t).*$", re.M)
_NOT_TEXT = re.compile(r"https?://\S+|<[a-zA-Z/][^>\n]*>")  # a link, an html tag: their words name nothing in the code
_COMMON = frozenset(dir(builtins)) | frozenset(keyword.kwlist) | frozenset(
    "self cls args kwargs main name file line path test tests python import from traceback most recent call last stdin module "
    "error errors warning true false none null return print http https www com org github html json yaml toml code text data "
    "value values result results expected actual output input example examples version versions issue bug fix description".split()
)


def _codelike(word: str) -> bool:
    return len(word) >= 4 and ("_" in word.strip("_") or re.search(r"[a-z0-9][A-Z]", word) is not None)


def issue_terms(issue: str, packages: list[str] | tuple[str, ...] = ()) -> set[str]:
    """What the issue names: identifiers written as code. In running text only the ones that look like code
    (``snake_case``, ``CamelCase``, a part of a dotted name, a name followed by ``(``); inside backticks, fences and
    indented blocks every word of four letters or more. The repository's package names, Python's keywords and
    builtins and a few words every traceback holds are left out: naming those says nothing about this issue."""
    text = _NOT_TEXT.sub(" ", (issue or "")[:MAX_ISSUE])
    out: set[str] = set()
    for block in [m.group(0) for m in _FENCE.finditer(text)] + [m.group(0) for m in _INDENTED.finditer(text)]:
        out.update(w for w in _WORD.findall(block) if len(w) >= 3)
    for m in _WORD.finditer(text):
        w = m.group(0)
        before, after = text[max(0, m.start() - 1) : m.start()], text[m.end() : m.end() + 1]
        dotted = (before == "." and m.start() >= 2 and (text[m.start() - 2].isalnum() or text[m.start() - 2] == "_")) or (after == "." and text[m.end() + 1 : m.end() + 2].isalpha())
        if _codelike(w) or (len(w) >= 3 and (after == "(" or dotted)):
            out.add(w)
    skip = {p.lower() for p in packages} | {c.lower() for c in _COMMON}
    # an all-capitals word without an underscore is an abbreviation (HTTP, JSON), not a name
    return set(sorted(w for w in out if w.lower() not in skip and not (w.isupper() and "_" not in w))[:MAX_TERMS])


def names_one(code: str, terms: set[str]) -> str | None:
    """A term the code names (whole word), or None."""
    if not terms:
        return None
    have = set(_WORD.findall(code[:MAX_CODE]))
    return next((t for t in sorted(terms) if t in have), None)


# --------------------------------------------------------------------------------------------
# Code that runs the repository
# --------------------------------------------------------------------------------------------
_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import\b|import\s+(.+))")
_LOOKUP = re.compile(r"inspect\.(?:getsource|getsourcelines|getfile|signature)|__file__|__version__|__doc__|__path__|\bhelp\(|\bdir\(")
_STATEMENT_SEP = re.compile(r"[\n;]")
_SPAWN = re.compile(r"\bsubprocess\.|\bos\.(?:system|popen)\(|\bpexpect\.")


def imported(code: str) -> set[str]:
    """Top-level names of the modules the code imports."""
    out: set[str] = set()
    for line in _STATEMENT_SEP.split(code[:MAX_CODE]):
        m = _IMPORT.match(line)
        if not m:
            continue
        if m.group(1):
            out.add(m.group(1).split(".")[0])
        else:
            out.update(part.strip().split(" as ")[0].strip().split(".")[0] for part in m.group(2).split(","))
    return {n for n in out if n}


def runs_package(code: str, packages: list[str] | tuple[str, ...]) -> bool:
    """The code imports one of ``packages`` (any import when none is known) -- or starts one as a command through
    ``subprocess`` / ``os.system`` -- and holds a statement besides its imports and its look-ups: something of the
    package is called, built or printed."""
    code = (code or "")[:MAX_CODE]
    names = imported(code)
    if not names:
        return False
    if packages and not names & set(packages):
        # the package started as a command of its own: subprocess.run(["pylint", ...]), os.system("python -m pytest ...")
        return _SPAWN.search(code) is not None and bool(set(_WORD.findall(code)) & set(packages))
    for line in _STATEMENT_SEP.split(code):
        s = line.strip()
        if not s or s.startswith("#") or _IMPORT.match(s) or _LOOKUP.search(s):
            continue
        if s in ("pass", "try:", "else:", "finally:") or s.startswith(("except", '"""', "'''")):
            continue
        return True
    return False


# --------------------------------------------------------------------------------------------
# The plan step
# --------------------------------------------------------------------------------------------
def plan_step(ctx: EvalContext, artifact: str, section: str) -> int | None:
    """Step of the first successful write of ``artifact`` whose content has a non-blank ``section``; the first
    successful write when no write shows one (the content could not be replayed, or the section never came)."""
    art = ctx.rubric.artifacts.get(artifact)
    path = ctx.facts.artifact_paths.get(artifact)
    if art is None or not path:
        return None
    evs = refs._artifact_events(ctx, art, path)
    if not evs:
        return None
    for e in evs:
        body = base._section(e.content, section) if e.content else None
        if body and body.strip():
            return int(e.step)
    return int(evs[0].step)


# --------------------------------------------------------------------------------------------
# speckit_bug_repro.reproduction
# --------------------------------------------------------------------------------------------
_NO_RUN = frozenset({"--help", "-h", "--version", "-V", "--help-all"})
_SHELLS = ("bash", "sh", "zsh", "dash", "ksh")


class _Look:
    """What one evaluation looks things up in."""

    def __init__(self, ctx: EvalContext, terms: set[str]):
        self.ctx = ctx
        self.terms = terms
        c = ctx.collected
        self.packages = tuple(c.inputs.get("packages") or ()) or tuple(sorted({n for n in map(package_of, change_paths(ctx)) if n}))
        self.wd = c.workdir
        self.created: dict[str, int] = dict(getattr(ctx.facts, "_created", None) or {})
        self.created_norm = {refs.norm_path(p, self.wd): (p, s) for p, s in self.created.items()}

    def content(self, path: str, step: int) -> str | None:
        """The file as it stood when ``step`` ran it (a write in the same step is the same command's)."""
        text = None
        for e in self.ctx.facts.writes.get(path, []):
            if e.step <= step and e.ok is not False and e.content is not None:
                text = e.content
        return text

    def own_file(self, path: str, step: int) -> str | None:
        """``path`` (absolute, or as ``refs.norm_path`` gives it) as the absolute path of a file the run created by ``step``."""
        if path in self.created:
            return path if self.created[path] <= step else None
        p, s = self.created_norm.get(refs.norm_path(path, self.wd), (None, None))
        return p if p is not None and s <= step else None

    def code(self, code: str, what: str) -> str | None:
        """Inline code or a script's text: None when it counts, else why not."""
        if not runs_package(code, self.packages):
            return f"{what} runs nothing of {list(self.packages)[:3] or 'the repository'}"
        if self.terms and names_one(code, self.terms) is None:
            return f"{what} names nothing the issue names"
        return None

    def script(self, path: str, step: int, depth: int, by_package: bool = False) -> str | None:
        """Running the file at ``path``: None when it counts, else why not. ``by_package``: what runs it is the
        repository's own program (pytest on a test file, in pytest's repository), so the file need not import it."""
        own = self.own_file(path, step)
        name = posixpath.basename(path.rstrip("/"))
        if own is None:
            # a directory the run made (``pytest repro_dir/``): the files it wrote there, any of them
            under = refs.norm_path(path, self.wd).rstrip("/") + "/"
            inside = sorted(q for n, (q, at) in self.created_norm.items() if n.startswith(under) and at <= step)[:20]
            if inside and depth < _DEPTH and any(self.script(q, step, depth + 1, by_package) is None for q in inside):
                return None
            return f"{name} is not a file the run created"
        text = self.content(own, step)
        if text is None:
            return None  # the run wrote it and ran it; what it held cannot be replayed
        if by_package:
            return None if not self.terms or names_one(text, self.terms) else f"{name} names nothing the issue names"
        if not name.endswith((".sh", ".bash")):
            return self.code(text, name)
        if depth >= _DEPTH:
            return f"{name}: nested too deep"
        why = [self.segment(seg, step, depth + 1) for seg in shell.flat(shell.split(text[:MAX_CODE], posixpath.dirname(own))[0])]
        return None if any(w is None for w in why) else f"{name} runs nothing of the repository"

    def segment(self, seg: shell.Segment, step: int, depth: int = 0) -> str | None:
        """One command segment: None when it runs the repository's code, else why not ('' = nothing to say)."""
        words = seg.cmd_words
        if not words or seg.verb is None or evidence.classify(seg) is not None:
            return ""  # a runner call is read from ``facts.runs``
        verb = posixpath.basename(seg.verb)
        rest = [w.text for w in words[1:]]
        if evidence._PYTHON.match(verb):
            mode, val, _ = evidence.py_args(words[1:])
            if mode in ("code", "stdin"):
                code = (val if mode == "code" else (seg.stdin_text if seg.stdin_text is not None else seg.heredoc)) or ""
                return self.code(code, "inline code") if code.strip() else ""
            if mode == "module":
                top = (val or "").split(".")[0]
                if top in self.packages:
                    return None if not _NO_RUN & set(rest) else f"python -m {top}: no run"
                return ""
            return self.script(shell.resolve(val, seg.cwd), step, depth) if val and (seg.cwd is not None or val.startswith(("/", "~"))) else ""
        if any(verb == p or verb.startswith(p + "-") for p in self.packages):
            return None if not _NO_RUN & set(rest) else f"{verb}: no run"
        if verb in _SHELLS:
            ops = [t for t in rest if not t.startswith("-")]
            if any(t.startswith("-") and "c" in t[1:] for t in rest[:1]) or not ops:
                return ""  # ``bash -c``: its body is segments of its own
            return self.script(shell.resolve(ops[0], seg.cwd), step, depth) if seg.cwd is not None or ops[0].startswith(("/", "~")) else ""
        if "/" in words[0].text and (seg.cwd is not None or words[0].text.startswith(("/", "~"))):
            return self.script(shell.resolve(words[0].text, seg.cwd), step, depth)
        return ""


@register("speckit_bug_repro.reproduction", params={"artifact": False, "section": False, "issue_terms": False}, availability=("trace",), common=False)
def reproduction(item: Item, ctx: EvalContext) -> Result:
    """Before the assessment's first write that carries a Proposed Remediation, the run executed the repository's code:
    a valid test run, a script it created, inline python importing the package, or the package's command line
    (``issue_terms``: scripts and inline code must name an identifier of the issue). Outside the item, worth 0: a run
    that wrote no assessment."""
    p = item.check.params or {}
    plan = plan_step(ctx, str(p.get("artifact") or "assessment"), str(p.get("section") or "Proposed Remediation"))
    if plan is None:
        return PEN.outside(item, "no assessment written: nothing was planned", premise=False)
    look = _Look(ctx, issue_terms(str(ctx.collected.inputs.get("issue") or ""), ctx.collected.inputs.get("packages") or ()) if p.get("issue_terms") else set())
    why: list[str] = []
    for r in ctx.facts.runs:
        if r.kind != "test" or r.step >= plan:
            continue
        if r.valid:
            return Result.ok(item, f"step {r.step}: test run {r.command.strip()[:70]}")
        own_runner = any(r.runner == p or r.runner.startswith(p + "-") for p in look.packages)
        for t in r.targets:  # a runner pointed at a test file the run wrote itself
            w = look.script(t, int(r.step), 0, by_package=own_runner)
            if w is None:
                return Result.ok(item, f"step {r.step}: ran its own {posixpath.basename(t)}")
            why.append(f"step {r.step}: {w}")
    for c in ctx.facts.commands:
        if c.step >= plan:
            continue
        for seg in shell.flat(shell.split(c.command, c.cwd)[0]):
            w = look.segment(seg, int(c.step))
            if w is None:
                return Result.ok(item, f"step {c.step}: {seg.text.strip()[:70]}")
            if w:
                why.append(f"step {c.step}: {w}")
    return Result.no(item, f"nothing of the repository run before the assessment (step {plan})" + (f"; {why[0]}" if why else ""))


__all__ = ["inputs", "post", "package_of", "packages_table", "issue_terms", "names_one", "imported", "runs_package", "plan_step", "reproduction"]
