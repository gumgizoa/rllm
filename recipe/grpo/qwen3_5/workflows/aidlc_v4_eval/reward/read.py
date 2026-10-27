"""How this verifier reads a run: its artifacts' fields and claims, and what the trajectory shows.

    paths / report readers   ``##`` sections, ``- Label:`` fields, bullets, tables, R ids, ``none``
    commands / evidence      test-runner invocations (Django's runner, ``python -c`` test calls; lookups,
                             agent-written runner scripts and tests out), exit codes, failures, test
                             targets, test files (the task's ``test_patch``), environment setup
    Observed / observe       the trajectory indexed: files read / created / edited / removed, shell
                             commands with output, test attempts and runs, artifact writes
    run readings             artifact write steps, parsed artifacts, stage bands, the final words

Merged from ``_claims.py`` (the content checks' shared machinery, 김규민 연구원 1b68a8e7) and
``evidence.py`` (where this verifier reads a run differently from the vendored rubric).
"""

from __future__ import annotations

import base64
import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean

from . import skeleton as A
from . import trace as F
from .trace import Run, _args, _text

SUPPORTED, PARTIAL, CONTRADICTED = 1.0, 0.5, 0.0

SOURCE_EXT = re.compile(
    r"\.(py|pyi|pyx|js|jsx|mjs|cjs|ts|tsx|go|rs|java|kt|rb|php|c|h|cc|cpp|hpp|cs|swift|sh|"
    r"yaml|yml|toml|json|cfg|ini|txt|md|rst|html|css|sql)$",
    re.I,
)

PATH_RE = re.compile(r"[\w./-]*[\w-]/[\w./-]+|[\w-]+\.[A-Za-z]{1,5}\b")

PATH_LINE_RE = re.compile(r"((?:[\w./-]*/)?[\w-]+\.[A-Za-z]{1,5}):(\d+)")

TEST_ID = re.compile(r"\b(test_\w+)")

# An R id named anywhere (``Exercises: R1, R3``); a requirement line of artifact 02 is ``R_LINE`` (skeleton ``R_ID``).
R_REF = re.compile(r"\bR\d+\b")

# A requirement line: ``- R1: statement`` / ``- **R1**: statement`` (id, statement).
R_LINE = re.compile(r"^\s*[-*+]\s*\*{0,2}(R\d+)\*{0,2}\s*:\s*(.*)$", re.M)

NONE_VALUE = A.NONE_VALUE

PLACEHOLDER = A.PLACEHOLDER  # a skeleton placeholder left in: `[statement]`, `TBD`, `...`

CHECKBOX = re.compile(r"^\s*[-*+]\s*\[([ xX]?)\]\s*(.*)$", re.M)

READ_VERB = re.compile(r"\b(?:cat|sed|head|tail|grep|rg|less|more|awk|nl|wc|bat|view|open)\b")

RUNNERS = rf"(?:{F.RUNNER}|pytest|py\.test|python[0-9.]*\s+-m\s+pytest)"

EXIT_CODE = re.compile(r"exit code[:\s]+(\d+)")

# unittest / Django's `OK (skipped=1, expected failures=1)` reports an expected failure, not a failure.
FAILURES = re.compile(r"\b(\d+) (?:failed|errors?)\b|(?<!expected )\bfailures=(\d+)|\berrors=(\d+)", re.I)

PASSES = re.compile(r"\b(\d+) passed\b")

NO_TESTS = re.compile(r"collected 0 items|no tests? (?:ran|found|to run|were run)", re.I)

PATCH_WRITE = re.compile(r"\bgit\s+apply\b|\bpatch\s+-p\d|\bgit\s+(?:checkout|restore)\s+\S+\s+--\s+\S")

NOT_A_PATH = re.compile(r"[()=,<>\"'`$]")

DUPLICATE = re.compile(r"(?:[-_.](?:new|fixed|backup|copy|old|orig|bak|tmp|v\d+|\d+))\.\w+$|\.(?:bak|orig|rej)$|(?:^|/)[^/]*\bcopy\b[^/]*$", re.I)


NETWORK = re.compile(r"\b(?:curl|wget|pip3?\s+install|npm\s+install|apt(?:-get)?\s+install|conda\s+install|uv\s+pip\s+install)\b")


def norm_path(p: str) -> str:
    p = p.strip().strip("`'\"*,;:()[]").rstrip(".")
    if p.startswith("./"):
        p = p[2:]
    if p.startswith("/testbed/"):
        p = p[len("/testbed/") :]
    return p


def same_file(a: str, b: str) -> bool:
    """Two mentions name the same file: equal, or one is the other's suffix; a bare basename matches
    any path with that basename, two different directories never match."""
    a, b = norm_path(a), norm_path(b)
    if not a or not b:
        return False
    if a == b:
        return True
    if a.rsplit("/", 1)[-1] != b.rsplit("/", 1)[-1]:
        return False
    return a.endswith("/" + b) or b.endswith("/" + a) or "/" not in a or "/" not in b


def claimed_paths(text: str | None) -> list[str]:
    """File paths named in a field value: anything with a directory or a source extension, so that
    dotted module names (``pandas.core.indexing``) and requirement ids are left out."""
    out: list[str] = []
    for tok in PATH_RE.findall(text or ""):
        tok = norm_path(tok.split(":")[0] if PATH_LINE_RE.fullmatch(tok) else tok)
        if tok and ("/" in tok or SOURCE_EXT.search(tok)) and tok not in out and not NONE_VALUE.fullmatch(tok):  # "N/A" is no path
            out.append(tok)
    return out


def path_line_refs(text: str | None) -> list[tuple[str, int]]:
    """``file.py:42`` references."""
    return [(norm_path(p), int(n)) for p, n in PATH_LINE_RE.findall(text or "")]


def pathlike(t: str) -> bool:
    """A shell write target that can be a file: the rubric's extraction is best effort and a ``>``
    inside ``python -c`` code yields tokens like ``0`` or ``Expected``."""
    return bool(t) and not NOT_A_PATH.search(t) and ("/" in t or SOURCE_EXT.search(t) is not None)


# What may follow a none to explain it: ``None - all tests pass``, ``None. The fix matched the plan``,
# ``N/A: no build step``, ``none (Python project)``. A bare continuation is not a separator, so
# ``None input -> TypeError`` (Python's None) and ``None verified yet`` are values, not none.
_NONE_EXPLAINED = re.compile(r"\s+[-–—]\s+|[.:;]\s+|\s*\(")

# Phrases that say none whatever follows them: ``None stated in the task description``.
_NONE_PHRASE = re.compile(r"^(?:none stated|not applicable|n/a)\b", re.I)


# A value that is only a parenthesised remark saying there is nothing to do.
_NO_STEP = re.compile(r"\([^()]*\b(?:no \w+ (?:step )?(?:required|needed)|not (?:required|needed|applicable))\b[^()]*\)", re.I)


def is_none(value: str | None) -> bool:
    """A field that says none / n/a: the whole value, its first clause before an explanation, or a
    phrase that cannot be anything else (see ``_NONE_EXPLAINED`` / ``_NONE_PHRASE``)."""
    if not value:
        return False
    v = value.strip()
    if _NO_STEP.fullmatch(v):  # `(Django is a library, no build step required)`: swebv100 000048
        return True
    return NONE_VALUE.fullmatch(_NONE_EXPLAINED.split(v, maxsplit=1)[0].strip()) is not None or _NONE_PHRASE.match(v) is not None


def is_filler(value: str | None) -> bool:
    return not value or PLACEHOLDER.fullmatch(value.strip()) is not None


def r_ids(text: str | None) -> list[str]:
    return list(dict.fromkeys(R_REF.findall(text or "")))


def command_core(command: str) -> list[str]:
    """A command as the tokens that must all appear in the shell line that ran it: backticks, a
    leading ``cd dir &&`` and output plumbing (``2>&1 | tail``) stripped."""
    core = re.sub(r"\s+", " ", command).strip().strip("`")
    core = re.sub(r"^cd\s+\S+\s*&&\s*", "", core)
    core = re.split(r"\s*(?:2>&1|\|)\s*", core, maxsplit=1)[0]
    return [t for t in core.split() if t]


def test_command_tokens(command: str | None) -> list[str]:
    """What identifies a test command: its test paths / node ids / files, not its flags or runner.
    Empty for anything that is not a test-runner invocation (a ``python -c`` one-liner cannot be
    matched token by token through the quoting)."""
    if not command or is_none(command) or not (F.matches_any(command, F.TEST_RUN_PATTERNS) or EXTRA_TEST_RUN.search(command)):
        return []
    core = re.sub(r"\s+", " ", command).strip("`")
    return [
        t
        for t in core.split()
        if "::" in t
        or t.endswith(".py")
        or re.search(r"(^|/)tests?(/|$)", t)
        or (EXTRA_TEST_RUN.search(core) and re.fullmatch(r"[\w.]+", t) and not t.startswith("-") and t not in ("python", "python3", "runtests.py", "manage.py", "test"))
    ]


def failures(out: str) -> int:
    return sum(int(g) for m in FAILURES.finditer(out) for g in m.groups() if g)


def passes(out: str) -> int:
    return sum(int(x) for x in PASSES.findall(out))


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_STATE_FAIL = re.compile(r"\b(?:FAILED|FAIL|ERROR)\b")
_STATE_PASS = re.compile(r"\bPASSED\b|\.\.\.\s*ok\b")


def test_state(out: str, name: str) -> bool | None:
    """Whether test ``name`` (a function name, ``test_x``) passed in a run's output: False when a line naming it
    reports a failure or error (pytest ``FAILED`` / ``ERROR``, unittest ``... FAIL``, ``FAIL: test_x (...)``),
    True when a line reports it passed (``PASSED``, ``... ok``) and none failed, None when no line says
    (a quiet ``pytest -q`` names no passing test). A file or directory of that name is not the test
    (``test_solveset.py::test_solve_sqrt_fail FAILED`` says nothing of ``test_solveset``: step24 004741 000464)."""
    pat = re.compile(rf"(?<![\w/]){re.escape(name)}(?!\w|\.py\b|/)")
    # (colours stripped first: ``\x1b[32mPASSED`` has no word boundary before PASSED -- 137 of 4,011 baseline
    # readings on swebv100 + step24 were lost to it)
    lines = [ln for ln in _ANSI.sub("", out).splitlines() if pat.search(ln)]
    if any(_STATE_FAIL.search(ln) for ln in lines):
        return False
    if any(_STATE_PASS.search(ln) for ln in lines):
        return True
    return None


def passed_count(out: str) -> int | None:
    """How many tests a run passed by its summary: pytest's ``N passed``, else unittest's ``Ran N tests``
    less its failures and errors; None when the output has neither."""
    if PASSES.search(out):
        return passes(out)
    ran = re.findall(r"\bRan (\d+) tests?\b", out)
    return max(0, int(ran[-1]) - failures(out)) if ran else None


def names_test_ids(out: str) -> bool:
    return TEST_ID.search(out) is not None


def last_exit(out: str) -> int | None:
    codes = EXIT_CODE.findall(out)
    return int(codes[-1]) if codes else None


def membership(claims: list, found: Iterable[bool]) -> float | None:
    if not claims:
        return None
    n = sum(found)
    return SUPPORTED if n == len(claims) else PARTIAL if n else CONTRADICTED


def both_ways(claims: list[str], actual: list[str]) -> float | None:
    """Two file lists name the same set: every claim is actual and every actual file is claimed."""
    if not claims and not actual:
        return None
    hit = [any(same_file(c, a) for a in actual) for c in claims]
    back = [any(same_file(a, c) for c in claims) for a in actual]
    if all(hit) and all(back):
        return SUPPORTED
    return PARTIAL if any(hit) else CONTRADICTED


def summarise(checks: dict[str, float | None], families: dict[str, list[str]]) -> dict:
    """``checks`` plus family means over applicable checks, their mean, and the contradiction count."""
    fam = {f: (mean(v) if (v := [checks[k] for k in names if checks[k] is not None]) else None) for f, names in families.items()}
    applicable = [v for v in fam.values() if v is not None]
    return {
        "checks": checks,
        "families": fam,
        "content": mean(applicable) if applicable else None,
        "contradictions": sum(1 for v in checks.values() if v == CONTRADICTED),
    }


_FRONTMATTER = re.compile(r"\A\s*---\s*\n.*?\n\s*---\s*(?:\n|\Z)", re.DOTALL)


def sections(body: str, level: int = 2) -> dict[str, str]:
    """Heading text -> body for every heading of exactly ``level`` hashes (deeper headings stay inside
    their parent); ``""`` holds the text before the first heading. Bold and trailing colons are dropped."""
    out: dict[str, list[str]] = {"": []}
    cur = ""
    head = re.compile(rf"^\s{{0,3}}#{{{level}}}(?!#)\s*\*{{0,2}}(.+?)\*{{0,2}}\s*:?\s*$")
    shallower = re.compile(rf"^\s{{0,3}}#{{1,{level - 1}}}(?!#)\s") if level > 1 else None
    for line in _FRONTMATTER.sub("", body or "").splitlines():
        m = head.match(line)
        if m:
            cur = m.group(1).strip()
            out.setdefault(cur, [])
        elif shallower is not None and shallower.match(line):
            cur = ""  # a shallower heading closes the section: "## Impact" ends "### New Capabilities"
            out.setdefault(cur, []).append(line)
        else:
            out[cur].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def section(body: str | None, name: str, level: int = 2) -> str | None:
    """One section by name, case- and punctuation-insensitive; None when absent."""
    if body is None:
        return None
    want = re.sub(r"[^a-z0-9]+", "", name.lower())
    found = {re.sub(r"[^a-z0-9]+", "", k.lower()): v for k, v in sections(body, level).items()}
    if want in found:
        return found[want]
    for k, v in found.items():  # "Report (verbatim or summarized)" answers to "Report"
        if k.startswith(want) and want:
            return v
    return None


field_value = A.field_value  # one reader of `- Label: value` fields for the parser and the checks


def get_field(body: str | None, label: str) -> str | None:
    """``field_value`` with "" folded into None: a value, or nothing to check."""
    return field_value(body, label) or None


def bullets(body: str | None, keep_code: bool = False) -> list[str]:
    """The bullet lines of a section, stripped of markers and emphasis, placeholders dropped.
    ``keep_code`` leaves backticks in place for a caller that reads them."""
    out = []
    for line in (body or "").splitlines():
        text = line.strip().lstrip("-*+ ").strip(" *" if keep_code else " *`")
        if text and not PLACEHOLDER.fullmatch(text):
            out.append(text)
    return out


def section_none(body: str | None) -> bool | None:
    """A bare-list section: True when every line says none, False when it has content, None when absent."""
    if body is None:
        return None
    lines = bullets(body)
    return bool(lines) and all(is_none(ln) for ln in lines)


def table(body: str | None) -> list[dict[str, str]]:
    """Rows of the first markdown table in ``body`` as header -> cell (headers lower-cased, cells
    stripped of emphasis and backticks)."""
    rows, header = [], None
    for line in (body or "").splitlines():
        if not line.strip().startswith("|"):
            if header is not None and rows:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower().strip(" *") for c in cells]
            continue
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        rows.append({h: cells[i].strip(" *`") if i < len(cells) else "" for i, h in enumerate(header)})
    return rows


def column(row: dict[str, str], *names: str) -> str:
    """The first cell whose header contains any of ``names``."""
    for n in names:
        for h, v in row.items():
            if n in h:
                return v
    return ""


def checkboxes(body: str | None) -> list[tuple[bool, str]]:
    """``- [ ]`` / ``- [x]`` items as (done, text). A box holding only ``x`` (any case) is done."""
    return [(m.group(1).strip().lower() == "x", m.group(2).strip()) for m in CHECKBOX.finditer(body or "")]


def quoted_lines(text: str | None, min_len: int = 24) -> list[str]:
    """Lines of a quoted / excerpted passage long enough to be looked for verbatim elsewhere."""
    out = []
    for line in (text or "").splitlines():
        t = line.strip().strip("`>*- ").strip()
        if len(t) >= min_len and not PLACEHOLDER.fullmatch(t):
            out.append(t)
    return out


def found_verbatim(needles: list[str], haystacks: Iterable[str]) -> list[bool]:
    """Whitespace-insensitive substring search of each needle in any haystack."""
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()  # noqa: E731
    hs = [norm(h) for h in haystacks]
    return [any(norm(n) in h for h in hs) for n in needles]


@dataclass
class Observed:
    """The trajectory, indexed for the checks. Steps are the rubric's 1-based turn numbers."""

    viewed: dict[str, int] = field(default_factory=dict)  # path -> first step read
    created: dict[str, int] = field(default_factory=dict)  # path -> first step written whole (any location)
    edited: dict[str, int] = field(default_factory=dict)  # repository path -> first step changed
    edit_steps: dict[str, list[int]] = field(default_factory=dict)  # repository path -> every step that changed it
    removed: dict[str, int] = field(default_factory=dict)  # repository path (or directory) -> last step rm'd
    edits_unknown: bool = False  # a whole-patch write changed files it did not name
    shell: list[tuple[int, str, str]] = field(default_factory=list)  # (step, command, output)
    shell_raw: list[str] = field(default_factory=list)  # the same commands as written (newlines kept)
    observations: list[str] = field(default_factory=list)  # every tool result, for verbatim quotes
    test_attempts: list[tuple[int, str, str]] = field(default_factory=list)  # test-runner invocations, whatever came of them
    test_runs: list[tuple[int, str, str]] = field(default_factory=list)  # the attempts that really ran tests
    writes: dict[str, list[int]] = field(default_factory=dict)  # watched report path -> every successful write step
    last_step: int = 0

    # -- derived views --

    @property
    def new_files(self) -> dict[str, int]:
        """Files the run brought into being: written whole without having been read or edited first.
        A ``cat > existing.py <<EOF`` rewrite registers as a whole write too, but the file was looked at
        before, so it is an edit of the repository's own file, not a new one."""
        out = {}
        for p, n in self.created.items():
            # the same path, both read from the trajectory (``same_file`` would take a root `test_x.py` read
            # for `pkg/tests/test_x.py`: swebv100 000089)
            seen_before = any(q == p and m < n for q, m in self.viewed.items())
            edited_before = any(m < n for m in self.edit_steps.get(p, []))
            if not seen_before and not edited_before:
                out[p] = n
        dirs = [p for p in out if p.endswith("/")]
        for p, n in self.edited.items():
            if p not in out and any(p.startswith(d) for d in dirs):
                out[p] = n
        return out

    @property
    def source_edits(self) -> dict[str, int]:
        """Edits to the repository's own files: files the run itself brought into being at the
        repository root, or that are test- or note-like, are the run's scratch (reproduction
        scripts, summaries), not source the existing tests depend on."""
        new = self.new_files
        return {p: n for p, n in self.edited.items() if not (p in new and ("/" not in p or F.TEST_PATH_RE.search(p) or F.DOCLIKE_RE.search(p)))}

    @property
    def remaining(self) -> dict[str, int]:
        """Repository files still changed at the end: edited, and not removed afterwards."""
        return {p: n for p, n in self.edited.items() if not any((p == r or p.startswith(r.rstrip("/") + "/")) and m > n for r, m in self.removed.items())}

    @property
    def first_edit(self) -> int | None:
        return min(self.source_edits.values()) if self.source_edits else None

    @property
    def last_edit(self) -> int | None:
        """The last step any source file changed (a file edited twice counts at its second edit)."""
        steps = [n for p in self.source_edits for n in self.edit_steps.get(p, [self.source_edits[p]])]
        return max(steps) if steps else None

    def first_write(self, path: str) -> int | None:
        steps = self.writes.get(path)
        return steps[0] if steps else None

    def source_edits_in(self, after: int | None, before: int | None) -> list[str]:
        """Repository source files changed strictly within (after, before)."""
        return [p for p in self.source_edits for n in self.edit_steps.get(p, []) if (after is None or n > after) and (before is None or n < before)]

    # -- queries --

    def ran(self, path: str, after: int | None = None, before: int | None = None) -> list[tuple[int, str, str]]:
        """Shell steps that executed ``path`` -- with an interpreter or test runner, directly, or by
        importing it as a module from a ``python -c`` one-liner -- within (after, before)."""
        name = norm_path(path).rsplit("/", 1)[-1]
        if not name:
            return []
        # The command as written, not flattened: a heredoc that writes the script and the line that runs it
        # are separate segments only while the newline is there (``evidence.runs_script``).
        return [(n, c, o) for (n, c, o), raw in zip(self.shell, self.shell_raw, strict=True) if (after is None or n > after) and (before is None or n < before) and runs_script(raw, name)]

    def tests_in(self, after: int | None = None, before: int | None = None) -> list[tuple[int, str, str]]:
        return [(n, c, o) for n, c, o in self.test_runs if (after is None or n > after) and (before is None or n < before)]

    def attempts_in(self, after: int | None = None, before: int | None = None) -> list[tuple[int, str, str]]:
        return [(n, c, o) for n, c, o in self.test_attempts if (after is None or n > after) and (before is None or n < before)]

    def shell_in(self, after: int | None = None, before: int | None = None) -> list[tuple[int, str, str]]:
        return [(n, c, o) for n, c, o in self.shell if (after is None or n > after) and (before is None or n < before)]

    def command_run(self, tokens: list[str], after: int | None = None, before: int | None = None, started: bool = False) -> bool:
        """Some shell step within (after, before) ran a test command holding every token, read against the
        directory it ``cd``'d into (``evidence.command_has_tokens``). Only a test run counts: a ``grep`` or
        ``cat`` of the recorded test file holds its path too (swebv100 + step24 004741: 12 of 449 recorded
        stage-1 commands were never run but looked up). ``started``: only a run that ran tests counts."""
        ran = {n for n, _, _ in self.test_runs}
        return bool(tokens) and any(
            command_has_tokens(raw, tokens) and is_test_attempt(raw) and (not started or n in ran)
            for (n, _, _), raw in zip(self.shell, self.shell_raw, strict=True)
            if (after is None or n > after) and (before is None or n < before)
        )

    def command_runs(self, command: str, after: int | None = None, before: int | None = None) -> list[tuple[int, str, str]]:
        """Shell steps that ran ``command`` as written (all its core tokens present), read without heredoc
        bodies: the artifact that records the command quotes it (swebv100 000004's 05 write)."""
        tokens = command_core(command)
        if not tokens:
            return []
        return [
            (n, c, o)
            for (n, c, o), raw in zip(self.shell, self.shell_raw, strict=True)
            if (after is None or n > after) and (before is None or n < before) and all(t in re.sub(r"\s+", " ", F.drop_heredoc_bodies(raw)) for t in tokens)
        ]

    def commands_matching(self, pattern: re.Pattern, after: int | None = None, before: int | None = None) -> list[tuple[int, str, str]]:
        return [(n, c, o) for n, c, o in self.shell_in(after, before) if pattern.search(c)]

    def seen(self, path: str, before: int | None = None) -> bool:
        return any(same_file(p, path) and (before is None or n <= before) for p, n in self.viewed.items())

    def mentioned_in_shell(self, path: str, before: int | None = None) -> bool:
        base = norm_path(path).rsplit("/", 1)[-1]
        return bool(base) and any(base in c for n, c, _ in self.shell if before is None or n <= before)

    def changed(self, path: str) -> bool:
        return any(same_file(p, path) for p in self.edited)

    def written(self, path: str) -> int | None:
        """First step that wrote ``path`` anywhere: repository edit, file created, or a watched write."""
        first_writes = {p: steps[0] for p, steps in self.writes.items() if steps}
        hits = [n for p, n in {**first_writes, **self.edited, **self.created}.items() if same_file(p, path)]
        return min(hits) if hits else None

    def exists_at_end(self, path: str) -> bool:
        """Written (anywhere) and not removed afterwards."""
        n = self.written(path)
        return n is not None and not any(same_file(r, path) and m > n for r, m in self.removed.items())


# ``grep -rn word /testbed/pkg`` / ``rg word``: a recursive search, whose output lines start ``path:line:``.
_SEARCH = re.compile(r"\b(?:grep|egrep)\s+(?:-\S*\s+)*-\w*[rR]|\brg\s")

_HIT = re.compile(r"^(/?[\w.-]+(?:/[\w.-]+)+\.\w+):(?:\d+:)?", re.M)


_LEADING_CD = re.compile(r"^\s*cd\s+(/\S+)\s*(?:&&|;)")


def _from_cwd(command: str, target: str) -> str:
    """``target`` read against the directory the command ``cd``'d into first: ``cd /tmp/t && cat > m.py``
    writes /tmp/t/m.py, not the repository's m.py (swebv100 000080); ``cd /testbed/tests/roots/x && cat >
    index.rst`` writes tests/roots/x/index.rst (000077)."""
    m = _LEADING_CD.match(command or "")
    if not m or not target or target.startswith(("/", "~")):
        return target
    return m.group(1).rstrip("/") + "/" + target.removeprefix("./")


def _observe(run: Run, watch: Iterable[str] = ()) -> Observed:
    """Index ``run``. ``watch`` are report paths whose successful writes are recorded in ``writes``
    (and kept out of ``created``), matched exactly or, for a directory ending in ``/``, by prefix."""
    watch = list(watch)
    obs = Observed()
    # Files the agent brought into being so far (``evidence.agent_written``), including the action at hand:
    # ``cat > /tmp/t.py <<EOF ... EOF; pytest /tmp/t.py`` runs the agent's own test, not the repository's.
    agent_made: list[str] = []

    def watched(p: str) -> str | None:
        for wpath in watch:
            if p == wpath or (wpath.endswith("/") and p.startswith(wpath)):
                return p
        return None

    for step in run.steps:
        obs.last_step = step.n
        for a in step.actions:
            agent_made.extend(agent_written(a))
            if a.observation:
                obs.observations.append(a.observation)
            if a.kind == "view":
                obs.viewed.setdefault(norm_path(a.path or ""), step.n)
                continue
            if a.kind in ("create", "replace", "insert", "undo"):
                if a.status == "fail" or not a.path:
                    continue
                if (wp := watched(a.path)) is not None:
                    obs.writes.setdefault(wp, []).append(step.n)
                    continue
                if a.kind == "create":
                    obs.created.setdefault(norm_path(a.path), step.n)
                if not F.OUTSIDE_REPO_RE.match(a.path):
                    obs.edited.setdefault(norm_path(a.path), step.n)
                    obs.edit_steps.setdefault(norm_path(a.path), []).append(step.n)
                continue
            if a.kind != "shell":
                continue
            cmd = a.command or ""
            out = a.observation or ""
            flat = re.sub(r"\s+", " ", cmd).strip()
            obs.shell.append((step.n, flat, out))
            obs.shell_raw.append(cmd)
            if is_test_attempt(cmd, agent_files=agent_made):
                obs.test_attempts.append((step.n, flat, out))
                if started(a):
                    obs.test_runs.append((step.n, flat, out))
            skeleton = F.command_skeleton(cmd)
            if READ_VERB.search(skeleton):
                for p in re.findall(r"(?<![\w-])(/?[\w.-]+(?:/[\w.-]+)+)", skeleton):
                    if not F.OUTSIDE_REPO_RE.match(p) or p.startswith("/testbed/"):
                        obs.viewed.setdefault(norm_path(p), step.n)
            if _SEARCH.search(skeleton):  # a recursive search shows the lines of the files it lists
                for p in _HIT.findall(out):
                    if not F.OUTSIDE_REPO_RE.match(p) or p.startswith("/testbed/"):
                        obs.viewed.setdefault(norm_path(p), step.n)
            if PATCH_WRITE.search(skeleton):
                obs.edits_unknown = True
            if a.status == "fail":
                continue
            for t in (_from_cwd(cmd, t) for t in F.write_targets(a)):
                if t.startswith("/dev/"):
                    continue
                if F._rm_matches(cmd, t):
                    if t and not F.OUTSIDE_REPO_RE.match(t):
                        obs.removed[norm_path(t)] = step.n
                    continue
                if (wp := watched(t)) is not None:
                    obs.writes.setdefault(wp, []).append(step.n)
                    continue
                if not pathlike(t):
                    continue
                obs.created.setdefault(norm_path(t), step.n)
                if not F.OUTSIDE_REPO_RE.match(t):
                    obs.edited.setdefault(norm_path(t), step.n)
                    obs.edit_steps.setdefault(norm_path(t), []).append(step.n)
    return obs


def written_texts(run: Run, watch: Iterable[str]) -> dict[str, str]:
    """Report path -> final text as reconstructed from the trajectory's writes (editor ``create`` and
    edits, shell heredocs), for a saved episode with no collected files. A write whose text cannot be
    recovered drops the report (a measurement gap, not a verdict). The collected files, when the
    sandbox was read, are the truth and should be preferred."""

    watch = list(watch)
    texts: dict[str, str] = {}

    def matches(p: str) -> bool:
        return any(p == w or (w.endswith("/") and p.startswith(w)) for w in watch)

    for step in run.steps:
        for a in step.actions:
            if a.status == "fail":
                continue
            if a.kind == "create" and a.path and matches(a.path):
                texts[a.path] = a.text or ""
            elif a.kind in ("replace", "insert") and a.path and matches(a.path) and a.path in texts and a.status == "ok":
                texts[a.path] = F._apply_edit(texts[a.path], a)
            elif a.kind == "shell":
                cmd = a.command or ""
                for t in F.write_targets(a):
                    if not matches(t):
                        continue
                    if F._rm_matches(cmd, t):
                        texts.pop(t, None)
                        continue
                    body = A.shell_written_body(cmd, t)
                    if body is None:
                        texts.pop(t, None)
                    else:
                        texts[t] = body
    return texts


MARK = "@@CLAIMS "

MAX_FILE_BYTES = 200_000


def collect_command(root: str) -> str:
    """One shell line printing every regular file under ``root`` (path, then its base64) -- the
    text channel of ``sandbox.exec`` keeps the bytes intact. ``; true``: a run that wrote nothing is
    not an error."""
    return (
        f'if [ -d "{root}" ]; then find "{root}" -type f -size -{MAX_FILE_BYTES // 1000}k 2>/dev/null | LC_ALL=C sort | '
        f"while IFS= read -r f; do printf '{MARK}%s\\n' \"$f\"; base64 -w0 \"$f\"; printf '\\n'; done; fi; true"
    )


def parse_collected(output: str) -> dict[str, str]:
    files, path = {}, None
    for line in (output or "").splitlines():
        if line.startswith(MARK):
            path = line[len(MARK) :].strip()
            continue
        if path is not None:
            files[path] = base64.b64decode(line.strip() or b"").decode("utf-8", errors="replace")
            path = None
    return files


def under(outputs: dict[str, str], root: str) -> dict[str, str]:
    """The files of ``outputs`` under ``root`` (a saved episode's ``workflow_outputs`` holds every output dir)."""
    root = root.rstrip("/") + "/"
    return {p: t for p, t in outputs.items() if p.startswith(root)}


def task_text(task) -> str:
    """The task's instruction (the issue), from a live Task or the SimpleNamespace rescoring builds."""
    text = getattr(task, "instruction", None)
    if text is None and isinstance(getattr(task, "metadata", None), dict):
        text = task.metadata.get("instruction") or task.metadata.get("question")
    if isinstance(text, list):
        text = "\n".join(str(p.get("text", p)) if isinstance(p, dict) else str(p) for p in text)
    return text or ""


# Django's runner and nose / ward, which the rubric's TEST_RUN_PATTERNS do not know.
EXTRA_RUNNERS = re.compile(r"\bruntests\.py\b|\bmanage\.py\s+test\b|-m\s+django\s+test\b|\bnosetests?\b|\bward\b")

# A command segment led by a verb that reads or lists a file, not one that runs it.
LOOKUP = re.compile(
    r"^\s*(?:sudo\s+)?(?:grep|egrep|fgrep|rg|cat|head|tail|sed|awk|less|more|ls|find|wc|echo|printf|test|\[|stat|file|which|type|whereis|nl|diff|cmp|realpath|readlink|du|tree|pip3?\s+show|git\s+(?:log|show|diff|status|grep|blame))\b"
)

_SEGMENT = re.compile(r"\s*(?:&&|\|\||;|\n)\s*")

_PIPE = re.compile(r"(?<!\|)\|(?!\|)")

_EXIT = re.compile(r"exit code[:\s]+(\d+)")

_CD = re.compile(r"^\s*cd\s+\S+\s*$")

_ENV = re.compile(r"^(?:\w+=\S*\s+)+")

_SCRIPT_ARG = re.compile(r"^(?:bash|sh|zsh|python[0-9.]*|\./|/)\s*(\S+)")


def segments(command: str) -> list[str]:
    """The command's executable parts: heredoc bodies and quoted strings blanked (``F.command_skeleton``),
    split on ``&&`` / ``||`` / ``;`` / newlines, with leading ``cd dir`` segments and ``VAR=value``
    prefixes dropped. A pipe stays inside its segment: ``a | b`` runs ``a``."""
    out = []
    for seg in _SEGMENT.split(F.command_skeleton(command or "")):
        seg = _ENV.sub("", seg.strip())
        if seg and not _CD.match(seg):
            out.append(seg)
    return out


def is_lookup(segment: str) -> bool:
    """A segment that reads or lists rather than runs: its first command (before any pipe) is a lookup verb."""
    return bool(LOOKUP.match(_PIPE.split(segment, maxsplit=1)[0]))


def _runner_in(segment: str) -> bool:
    head = _PIPE.split(segment, maxsplit=1)[0]
    if INSTALL.match(head.strip()):  # `pip install pytest` names a runner and runs nothing
        return False
    return F.matches_any(head, F.TEST_RUN_PATTERNS) or EXTRA_RUNNERS.search(head) is not None


def _agent_script(segment: str, agent_files) -> bool:
    """The segment's program is a file the agent wrote itself (``bash /tmp/pytest.sh``)."""
    m = _SCRIPT_ARG.match(_PIPE.split(segment, maxsplit=1)[0].strip())
    if not m:
        return False
    target = m.group(1) if not m.group(0).startswith(("./", "/")) else m.group(0).split()[0]
    name = target.rsplit("/", 1)[-1]
    return bool(name) and any(str(p).rsplit("/", 1)[-1] == name for p in agent_files)


_TEST_TARGET = re.compile(r"(\S+\.py)(?:::\S*)?$")

_RUNNER_PROGRAMS = {"runtests.py", "manage.py", "setup.py"}


def _only_agent_tests(segment: str, agent_files) -> bool:
    """Every test file the runner is pointed at is one the agent wrote (``pytest /tmp/dummy_tests/test_x.py``):
    its own tests, not the repository's covering ones."""
    head = _PIPE.split(segment, maxsplit=1)[0]
    targets = [m.group(1) for t in head.split() if (m := _TEST_TARGET.match(t)) and m.group(1).rsplit("/", 1)[-1] not in _RUNNER_PROGRAMS]
    names = {str(p).rsplit("/", 1)[-1] for p in agent_files}
    return bool(targets) and all(t.rsplit("/", 1)[-1] in names for t in targets)


# Asking a runner about itself runs no test.
_NO_RUN_FLAGS = re.compile(r"\s(?:--help|-h|--collect-only|--co|--version|--fixtures|--markers)(?:\s|$)")

# The runner script or a test module could not be found: nothing ran (beyond the rubric's TOOL_MISSING_RE).
_NOT_STARTED = re.compile(r"can't open file|No such file or directory: '[^']*(?:runtests|manage)\.py'|ERROR: file or directory not found|ERROR: not found:", re.I)


# The settings a Django run needs could not be loaded, and no test reported: nothing ran (swebv100 000009).
_NO_SETTINGS = re.compile(r"No module named '[\w.]*settings[\w.]*'|ImproperlyConfigured")

_TEST_REPORT = re.compile(r"\bRan \d+ tests?\b|\b\d+ (?:passed|failed)\b|\btests? (?:passed|failed)\b", re.I)


def started(a) -> bool:
    """A test attempt that ran tests: not one the rubric sees failing to start (``ran_something``), not one
    whose runner, target or settings was missing, and not a ``--help`` / ``--collect-only`` query."""
    out = a.observation or ""
    no_settings = _NO_SETTINGS.search(out) is not None and _TEST_REPORT.search(out) is None
    return F.ran_something(a) and not _NOT_STARTED.search(out) and not no_settings and not any(_NO_RUN_FLAGS.search(s) for s in segments(a.command or ""))


# ``python -c "from sympy.core.tests.test_evalf import test_x; test_x()"``: a repository test function called
# directly, the way runs test where no runner is installed (sympy's environment has no pytest).
_PY_C = re.compile(r"\bpython[0-9.]*\s+-c\s")

_TEST_IMPORT = re.compile(r"\bfrom\s+((?:[\w]+\.)*tests?(?:\.[\w]+)*)\s+import\s+([\w, ()*]+)|\bimport\s+((?:[\w]+\.)*tests?\.[\w.]+)")


# ``sympy.test('sympy.core.tests.test_x')``: the package's own test runner, called from Python.
_PKG_TEST = re.compile(r"\bsympy\.(?:test|doctest)\s*\(")

# ``get_runner(settings)(...).run_tests(['auth_tests.test_checks'])``: Django's runner, called from Python.
_DJANGO_RUN = re.compile(r"\bget_runner\s*\(.*?\.run_tests\s*\(", re.S)

# ``unittest.TextTestRunner().run(loader.loadTestsFromTestCase(UtilsTests))``: test classes run through unittest.
_UNITTEST_RUN = re.compile(r"\bunittest\.(?:TextTestRunner|main)\b|\bloadTestsFrom\w+\s*\(")

# ``python << 'EOF'``: the heredoc is the program python runs, not a file written.
_PY_STDIN = re.compile(r"\bpython[0-9.]*\s+(?:-\s+)?<<")


def _python_code(command: str) -> str:
    """The command with every heredoc body blanked but the ones fed to python: an artifact written by a
    heredoc may quote a test command, a ``python << EOF`` body is code that runs."""
    out, pos = [], 0
    for opener, _, (start, stop) in A.heredocs(command):
        if start >= pos and not _PY_STDIN.search(opener):
            out.append(command[pos:start])
            pos = stop
    out.append(command[pos:])
    return " ".join(out)


def _calls_repo_test(command: str, agent_files) -> bool:
    command = _python_code(command or "")
    if not (_PY_C.search(command) or _PY_STDIN.search(command)):
        return False
    names = {str(p).rsplit("/", 1)[-1] for p in agent_files}
    if _PKG_TEST.search(command):
        return True
    if _DJANGO_RUN.search(command):
        # not when every label is a module the agent wrote (``run_tests(['test_repro'])``, step24 000205)
        labels = [x for m in re.finditer(r"\.run_tests\s*\(\s*\[([^\]]*)\]", command) for x in re.findall(r"['\"]([\w.]+)['\"]", m.group(1))]
        return not labels or not all(any(f"{part}.py" in names for part in label.split(".")) for label in labels)
    for m in _TEST_IMPORT.finditer(command):
        module = m.group(1) or m.group(3)
        if f"{module.rsplit('.', 1)[-1]}.py" in names:  # a test module the agent wrote itself
            continue
        if _UNITTEST_RUN.search(command):
            return True
        called = re.findall(r"\b(test_\w+)\s*\(", command)
        if called and (m.group(3) or m.group(2).strip() == "*" or any(c in m.group(2) for c in called)):
            return True
    return False


def is_test_attempt(command: str, agent_files=()) -> bool:
    """A shell command that invokes a test runner on the repository's tests: some segment runs one, is not
    a lookup, is not a runner script the agent wrote, and is not pointed only at test files the agent wrote
    (``agent_files``: paths the run created before this command). A ``python -c`` that imports a test function
    from the repository's test modules and calls it is one too."""
    return any(_runner_in(s) and not is_lookup(s) and not _agent_script(s, agent_files) and not _only_agent_tests(s, agent_files) for s in segments(command)) or _calls_repo_test(command, agent_files)


def command_has_tokens(command: str, tokens) -> bool:
    """Every token of a recorded command (test paths, node ids, labels) appears in ``command``, reading a
    path written from the repository root against the directory the command ``cd``'d into first:
    ``tests/runtests.py`` is in ``cd tests && python runtests.py``."""
    if not tokens:
        return False
    cwd = ""
    for seg in _SEGMENT.split(command or ""):
        m = re.match(r"^\s*cd\s+(\S+)\s*$", seg)
        if m:
            cwd = m.group(1).rstrip("/").removeprefix("/testbed").lstrip("/")

    def found(t: str) -> bool:
        t = t.removeprefix("/testbed/")
        return t in command or bool(cwd) and t.startswith(cwd + "/") and t[len(cwd) + 1 :] in command

    return all(found(t) for t in tokens)


INSTALL = re.compile(
    r"^(?:sudo\s+)?(?:(?:pip3?|python[0-9.]*\s+-m\s+pip|uv\s+pip|conda|mamba|micromamba|gem|cargo)\s+install|(?:apt|apt-get|yum|dnf|apk)\s+(?:install|add)|(?:npm|pnpm)\s+(?:install|i|add)|yarn\s+add|python[0-9.]*\s+setup\.py\s+(?:install|develop))\b"
)


def is_env_setup(command: str) -> bool:
    """The command installs a dependency or sets up the environment (01 / 05: the environment can already
    build and test the project)."""
    return any(INSTALL.match(s) for s in segments(command))


_DJANGO_LABELS = re.compile(r"runtests\.py|manage\.py\s+test|-m\s+django\s+test")


def runs_script(command: str, path: str) -> bool:
    """``command`` executes the script at ``path``: an interpreter or test runner with it as an argument,
    ``./path`` / ``/abs/path`` as the program, or ``python -c`` importing it as a module."""
    name = (path or "").strip().rsplit("/", 1)[-1]
    if not name:
        return False
    base, module = re.escape(name), re.escape(name.rsplit(".", 1)[0])
    interp = re.compile(rf"^(?:{F.RUNNER}|pytest|py\.test|python[0-9.]*\s+-m\s+pytest|timeout\s+\d+\s+{F.RUNNER})\s+(?:-\S+\s+)*\S*{base}(?:\s|$|::)")
    direct = re.compile(rf"^\.?/\S*{base}(?:\s|$)")
    # Django's runner given the script as a dotted label: `runtests.py check_framework.test_inherited_pk`
    label = re.compile(rf"(?:^|\s)(?:\w+\.)*{module}(?:\.\w+)*(?:\s|$)")
    for seg in (s for s in segments(command) if not is_lookup(s)):
        head = _PIPE.split(seg, maxsplit=1)[0].strip()
        if interp.search(head) or direct.search(head):
            return True
        if _DJANGO_LABELS.search(head) and label.search(head):
            return True
    return bool(re.search(rf"\bpython[0-9.]*\s+-c\s+\S*(?:import\s+{module}\b|from\s+{module}\s+import)", command or ""))


def exit_code(command: str, output: str) -> int | None:
    """The command's exit code as the terminal reported it, or None when a pipe without ``pipefail``
    makes the reported code the pipe's last command's, or none was reported."""
    if any(_PIPE.search(s) for s in segments(command)) and "pipefail" not in (command or ""):
        return None
    codes = _EXIT.findall(output or "")
    return int(codes[-1]) if codes else None


def agent_written(a) -> list[str]:
    """Files this action brought into being: an editor ``create`` that succeeded (the editor refuses an
    existing file), or a shell write outside the repository. A shell write inside it may be an existing
    file rewritten (``cat > tests/test_x.py``), so it is not counted as the agent's own."""
    if a.kind == "create":
        return [a.path] if a.path and a.status != "fail" else []
    if a.kind == "shell" and a.status != "fail":
        return [t for t in F.write_targets(a) if F.OUTSIDE_REPO_RE.match(t) and not t.startswith("/dev/")]
    return []


def ran_real_test(run) -> bool:
    """Any test-runner invocation in the run that did not fail to start (the rubric's ``ran_something``)."""
    agent_files: set[str] = set()
    for step in run.steps:
        for a in step.actions:
            agent_files.update(agent_written(a))
            if a.kind == "shell" and is_test_attempt(a.command or "", agent_files) and started(a):
                return True
    return False


def patch_files(patch: str | None) -> tuple[list[str], list[str]] | None:
    """(changed, added) repository paths of the run's patch, or None when the patch is unknown."""
    if patch is None:
        return None
    return F.diff_files(patch)


def task_test_files(task) -> set[str]:
    """Paths the task's ``test_patch`` touches (``<task dir>/tests/config.json``), empty when unknown."""
    task_dir = getattr(task, "task_dir", None)
    if task_dir is None:
        meta = getattr(task, "metadata", None) or {}
        task_dir = meta.get("task_path") if isinstance(meta, dict) else None
    if not task_dir:
        return set()
    try:
        cfg = json.loads((Path(task_dir) / "tests" / "config.json").read_text())
    except (OSError, ValueError, TypeError):
        return set()
    return set(re.findall(r"^diff --git a/(\S+)", cfg.get("test_patch") or "", re.M))


_TEST_NAME = re.compile(r"(?:^|/)(?:test_[^/]*|[^/]*_test\.\w+|tests?\.py|conftest\.py)$")

_TESTS_DIR = re.compile(r"(?:^|/)(?:tests|__tests__|testing)/")


def is_test_file(path: str, test_files=()) -> bool:
    """A test file: one the task's test_patch touches, a test-named file (``test_x.py``, ``x_test.py``,
    ``tests.py``, ``conftest.py``), or a file under a ``tests/`` / ``testing/`` directory. Not the
    rubric's pattern, which also takes a library's own ``test`` package (``django/test/utils.py``) for
    tests (TRACE X14)."""
    return path in test_files or bool(_TEST_NAME.search(path)) or bool(_TESTS_DIR.search(path))


_FLAGS_WITH_VALUE = {"-k", "-m", "--settings", "--parallel", "-p", "--tb", "--verbosity", "-v", "--timeout", "-n", "-c", "--rootdir", "-o"}


def test_targets(command: str) -> list[str] | None:
    """The targets a test command names -- paths, node ids, dotted module or label names, a ``-k``
    expression -- or None when it runs no test runner. ``[]``: a runner with no target (the full suite)."""
    # Quoted values (``-k "index"``) would be blanked with the other quoted strings: keep them as one token.
    quoted = re.findall(r"\s-k\s+(?:'([^']*)'|\"([^\"]*)\")", command or "")
    count = iter(range(len(quoted)))
    command = re.sub(r"(\s-k\s+)(?:'[^']*'|\"[^\"]*\")", lambda m: f"{m.group(1)}__K{next(count)}__", command or "")
    for seg in segments(command or ""):
        head = _PIPE.split(seg, maxsplit=1)[0].strip()
        if not _runner_in(head) or is_lookup(head):
            continue
        toks = head.split()
        # Django's runner, unittest and nose take bare labels (``runtests.py middleware_exceptions``); pytest's
        # bare word may be a whole-suite directory, so only paths and node ids count there.
        labels = re.search(r"runtests\.py|manage\.py\s+test|-m\s+django\s+test|\bunittest\b|\bnosetests?\b", head) is not None
        out, skip = [], False
        for i, t in enumerate(toks):
            if skip:
                skip = False
                if toks[i - 1] == "-k":
                    k = re.fullmatch(r"__K(\d+)__", t)
                    out.append(f"-k {''.join(quoted[int(k.group(1))]) if k else t}")
                continue
            if t in _FLAGS_WITH_VALUE:
                skip = True
                continue
            if t.startswith("-") or "=" in t:
                continue
            name = t.rsplit("/", 1)[-1]
            if name in _RUNNER_PROGRAMS or re.fullmatch(r"python[0-9.]*|pytest|py\.test|unittest|django|test|manage\.py|nosetests?|tox|timeout|\d+", name):
                continue
            if "/" in t or "." in t or "::" in t or (labels and re.fullmatch(r"[\w.]+", t)):
                out.append(t.removeprefix("/testbed/"))
        return out
    return None


_DOCS = Path(__file__).resolve().parents[1] / "docs" / "rule-details"


def _content_lines(text: str) -> list[str]:
    body, _ = A.strip_fence(text or "")
    body = A.FRONTMATTER.sub("", body, count=1)
    return [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def skeleton(stage: int) -> str:
    """The artifact skeleton stage ``stage``'s rule document prescribes (its fenced markdown block)."""
    text = next(_DOCS.glob(f"0{stage}-*.md")).read_text()
    return text.split("```markdown\n", 1)[1].split("```", 1)[0]


def is_template_copy(stage: int, text: str) -> bool:
    """Every line under the headings is a line of the skeleton: nothing was filled in."""
    lines = _content_lines(text)
    return bool(lines) and set(lines) <= set(_content_lines(skeleton(stage)))


def stage_band(stage: int, text: str) -> int:
    """The rubric's 8/5/2 band for one artifact (all graded fields / one missing / more), except that an
    artifact with nothing of its own -- the skeleton verbatim, or nothing under its frontmatter but
    headings -- earns 0, and ``Assumptions: none`` counts as filled. An artifact with real content under
    renamed headings keeps the rubric's 2 (the skeleton was not kept, but the stage was worked)."""
    parsed = A.parse(stage, text)
    missing = list(A.grade(stage, parsed)["missing"])
    if stage == 2 and "assumptions" in missing:
        body = parsed["section_bodies"].get("Assumptions")
        if body is not None and A._section_has_content(body, True):
            missing.remove("assumptions")
    if not _content_lines(text) or is_template_copy(stage, text):
        return 0
    return 8 if not missing else 5 if len(missing) == 1 else 2


def final_words(episode) -> str:
    """What the run said last: the final response's text and the ``message`` of its ``finish`` call. The
    vendored front end keeps a finish call's name only, and its message is where a run that ends by asking
    for input would ask."""
    steps = [s for traj in getattr(episode, "trajectories", None) or [] for s in traj.steps]
    if not steps:
        return ""
    response = (steps[-1].chat_completions or [{}])[-1] or {}
    said = [_text(response.get("content"))]
    for tc in response.get("tool_calls") or []:
        fn = tc.get("function") or {}
        if fn.get("name") == "finish":
            said.append(str(_args(fn.get("arguments")).get("message") or ""))
    return " ".join(x for x in said if x).strip()


def observe(run: Run) -> Observed:
    """The shared trajectory index, with the five artifact paths watched (their writes are the
    stage write steps, not repository edits)."""
    return _observe(run, watch=A.ARTIFACT_PATHS)


def _section_none(parsed: dict | None, section: str) -> bool | None:
    """A bare-list section (``## Deviations from Plan``, ``## Outstanding Failures``): True when every
    line says none, False when it has content, None when the section is absent."""
    return None if parsed is None else section_none(parsed["section_bodies"].get(section))


def _field(parsed: dict | None, section: str, label: str) -> str | None:
    """A field value, or None when the stage, the section or the field is missing or empty."""
    if parsed is None:
        return None
    body = parsed["section_bodies"].get(section)
    if body is None:
        return None
    # _claims.field_value: labels up to 40 characters, so "Unintended files in the repository" (34) ends
    # the field before it instead of running into its value (the vendored reader stops at 30).
    return field_value(body, label) or None


_COPY = re.compile(r"\b(?:cp|mv)\s+(?:-\w+\s+)*(\S+)\s+(\S+)")
_NO_SOURCE = re.compile(r"cannot stat|No such file or directory")


def _copy_failed(a, target: str) -> bool:
    """A ``cp`` / ``mv`` onto ``target`` whose source the output reports missing (``cp: cannot stat 's5.md'``):
    nothing was written (swebv100 000081: ``cp s4 04 && cp s5 05``, the second failing)."""
    errors = [ln for ln in (a.observation or "").splitlines() if _NO_SOURCE.search(ln)]
    return any(F.normalise_doc_paths(dst.strip("'\"")) == target and any(src.strip("'\"").rsplit("/", 1)[-1] in ln for ln in errors) for src, dst in _COPY.findall(a.command or ""))


def first_write_steps(run: Run) -> dict[int, int | None]:
    """Stage -> the first step that successfully wrote its artifact's path, whether or not the
    text could be recovered and whether or not the file survived. ``None`` when never written."""
    first: dict[int, int] = {}
    for step in run.steps:
        for a in step.actions:
            if a.status == "fail":
                continue
            targets = F.write_targets(a) if a.kind == "shell" else ([a.path] if F.is_write(a) else [])
            for t in targets:
                st = A.ARTIFACT_PATHS.get(t)
                if st is not None and not (a.kind == "shell" and (F._rm_matches(a.command or "", t) or _copy_failed(a, t))):
                    first.setdefault(st, step.n)
    return {st: first.get(st) for st in A.STAGE_FILES}


def parsed_artifacts(run: Run, collected: bool = False) -> dict[int, dict | None]:
    """Stage -> parsed final artifact.

    ``collected``: the sandbox was read at the end, so ``run.artifact_files`` is what it held and a
    stage with no file there has no artifact -- as the compliance signals see it -- even when the
    trajectory wrote one and removed it some way the rubric does not recognise. Otherwise (an old
    saved episode without the files) the text is reconstructed from the trajectory's writes
    (``facts.trace_artifacts``)."""
    if collected:
        return {st: (A.parse(st, run.artifact_files[p]) if (p := A.artifact_path(st)) in run.artifact_files else None) for st in A.STAGE_FILES}
    traces = F.trace_artifacts(run)
    return {st: (A.parse(st, t.content) if t.content is not None else None) for st, t in traces.items()}


# Test runners the vendored rubric's TEST_RUN_PATTERNS do not know: Django's runtests.py / manage.py test
# (most of SWE-bench Verified), nose, ward. One list for every check, so the stage gate (compliance.py)
# and the content checks agree on what a test run is.
EXTRA_TEST_RUN = EXTRA_RUNNERS


# --- whole-run readings for the rubric (the milestone-1 rubric's definitions, read here) ---------

STAGE_DOCS = ["01", "02", "03", "04", "05"]


def doc_reads(run: Run) -> tuple[list[str], dict[str, int]]:
    """The workflow documents in the order the run opened them, and each one's first-read step."""
    reads = [(s.n, d) for s in run.steps for a in s.actions if a.acts for d in F.doc_reads(a)]
    first: dict[str, int] = {}
    for n, d in reads:
        first.setdefault(d, n)
    return [d for _, d in reads], first


def multi_read(read_step: dict[str, int]) -> list[str]:
    """Stage documents whose first read shares a step with another's: read by one command (order_v6)."""
    counts = Counter(read_step[d] for d in STAGE_DOCS if d in read_step)
    return sorted({d for d in STAGE_DOCS if d in read_step and counts[read_step[d]] > 1})


def entry(run: Run) -> float:
    """core-workflow.md read before any other document: 1 by step 3, 1/3 later, 0 otherwise."""
    reads, first = doc_reads(run)
    core = first.get("core")
    return 0.0 if core is None or (reads and reads[0] != "core") else (1.0 if core <= 3 else 1 / 3)


def leaks(run: Run) -> tuple[list[int], list[int]]:
    """Steps that browsed git history, and steps that applied a whole patch."""
    shell = [(s.n, a) for s in run.steps for a in s.actions if a.acts and a.kind == "shell"]
    history = sorted({n for n, a in shell if F.probes_git_history(a)})
    applied = sorted({n for n, a in shell if re.search(r"\bgit\s+apply\b|\bpatch\s+-p\d", F.command_skeleton(a.command or ""))})
    return history, applied


def artifact_write_steps(run: Run) -> dict[int, int | None]:
    """Stage -> the first step that wrote its artifact's path (:func:`first_write_steps`), counted only when
    the file was collected."""
    first = first_write_steps(run)
    return {st: (first[st] if path in run.artifact_files else None) for path, st in A.ARTIFACT_PATHS.items()}


def fidelity(run: Run) -> float:
    """The share of the final diff artifact 04 discloses, capped at half by a file it claims and the diff
    lacks; 0 without a usable 04 (collected, frontmatter valid, not a skeleton copy) or with an empty diff."""
    text = run.artifact_files.get(A.artifact_path(4))
    if text is None or not run.patch.strip():
        return 0.0
    parsed = A.parse(4, text)
    if not A.grade(4, parsed)["frontmatter_valid"] or stage_band(4, text) == 0:
        return 0.0
    touched, _ = F.diff_files(run.patch)
    if not touched:
        return 0.0
    claimed = sorted(set(parsed["claims"]["modified"] + parsed["claims"]["created"]))
    names = {p.rsplit("/", 1)[-1] for p in touched}
    phantom = [p for p in claimed if p.rsplit("/", 1)[-1] not in names and not p.startswith("/tmp")]
    undisclosed = [p for p in touched if p.rsplit("/", 1)[-1] not in parsed["body"]]
    ratio = 1 - len(undisclosed) / len(touched)
    return min(0.5, ratio) if phantom else ratio
