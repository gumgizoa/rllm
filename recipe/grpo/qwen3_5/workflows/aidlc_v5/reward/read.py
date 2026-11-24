"""How this verifier reads a run: its artifacts' fields and claims, and what the trajectory shows.

    paths / report readers   ``##`` sections, ``- Label:`` fields, bullets, tables, R ids, ``none``
    commands / evidence      test-runner invocations, whether they really ran, their targets, their outputs'
                             counts and failing tests, and test files: the shared layer's readings
                             (``workflow_rubric``: ``evidence.runs_from`` / ``classify`` / ``summaries`` /
                             ``failing_ids``, ``facts.is_test_path``; the task's ``test_patch`` files are test
                             files too); exit codes, environment setup
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

from recipe.grpo.qwen3_5.workflow_rubric import evidence as SE
from recipe.grpo.qwen3_5.workflow_rubric import facts as SF
from recipe.grpo.qwen3_5.workflow_rubric import results as SR
from recipe.grpo.qwen3_5.workflow_rubric.refs import norm_path as _repo_path
from recipe.grpo.qwen3_5.workflow_rubric.trace import shell as SH

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

EXIT_CODE = re.compile(r"exit code[:\s]+(\d+)")

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
    """What identifies a test command: what it targets (``test_targets``: test paths, node ids, labels), not its
    flags or runner. Empty for anything that is not a test-runner invocation."""
    if not command or is_none(command):
        return []
    return [t for t in test_targets(command) or [] if not t.startswith("-")]


# --- a test run's output, read by the shared layer's parsers (``workflow_rubric.evidence``: the summaries and failing
# ids a ``RunFact``'s counts come from). The output of a whole call, or of several joined, is read as one text. ----


def _summaries(out: str) -> tuple[str, list]:
    clean = SE.clean_observation(out or "")
    return clean, SE.summaries(clean)


def _total(found: list):
    """The summaries of one output added up (``None`` when it has none)."""
    if not found:
        return None
    return SE.Summary(found[0].family, found[0].pos, passed=sum(s.passed for s in found), failed=sum(s.failed for s in found), errors=sum(s.errors for s in found),
                      skipped=sum(s.skipped for s in found), xfail=sum(s.xfail for s in found))  # fmt: skip


def failures(out: str) -> int:
    """Failed plus errored tests by the output's result summaries (0 when it has none)."""
    return sum(s.failed + s.errors for s in _summaries(out)[1])


def passes(out: str) -> int:
    """Passed tests by the output's result summaries (0 when it has none)."""
    return sum(s.passed for s in _summaries(out)[1])


def found_no_tests(out: str) -> bool:
    """The output's summaries report a runner that ran no test (``collected 0 items``, ``no tests ran``, ``Ran 0
    tests``, only skipped / deselected)."""
    total = _total(_summaries(out)[1])
    return total is not None and total.ran < 1


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


def _test_name(test_id: str) -> str:
    """A test id's own name: ``tests/x.py::TestC::test_a[1]`` and ``mod.TestC.test_a`` are ``test_a``."""
    return re.split(r"::|\.", test_id.split("[", 1)[0])[-1]


def failed_tests(out: str) -> list[str]:
    """The names of the tests a run's output reports failed or errored (``evidence.failing_ids``, each id cut to its
    test's own name); empty when it names none -- a quiet run reports a count only (``failures``). A loader stub
    (``unittest.loader._FailedTest``) is a module that did not import, not a test."""
    return list(dict.fromkeys(n for n in (_test_name(i) for i in SE.failing_ids(SE.clean_observation(out or ""))) if n))


def ran_no_test(out: str) -> bool:
    """The output's summaries report no test run: none ran (``found_no_tests``), or every outcome is the runner
    failing to load its selection (``evidence.invocation_error``: step24 000119, 000140 -- the covering tests never
    ran before or after the change). An output with no summary says nothing either way."""
    clean, found = _summaries(out)
    total = _total(found)
    return total is not None and (total.ran < 1 or bool(SE.invocation_error(clean, total)))


def passed_count(out: str) -> int | None:
    """How many tests a run passed by its summaries; None when the output has none."""
    total = _total(_summaries(out)[1])
    return None if total is None else total.passed


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


class ShellEntry(tuple):
    """One shell call as ``(step, command with whitespace collapsed, output)``, carrying the command as written
    (``raw``), the directory it ran in (``cwd``, the shared layer's tracking) and the shared layer's test-runner
    invocations in it (``runs``: ``RunFact``s of kind ``test``, valid or not)."""

    def __new__(cls, n: int, flat: str, out: str, raw: str = "", cwd: str | None = None, runs=()):
        self = super().__new__(cls, (n, flat, out))
        self.raw, self.cwd, self.runs = raw, cwd, list(runs)
        return self


@dataclass
class Observed:
    """The trajectory, indexed for the checks. Steps are the rubric's 1-based turn numbers."""

    viewed: dict[str, int] = field(default_factory=dict)  # path -> first step read
    created: dict[str, int] = field(default_factory=dict)  # path -> first step written whole (any location)
    edited: dict[str, int] = field(default_factory=dict)  # repository path -> first step changed
    edit_steps: dict[str, list[int]] = field(default_factory=dict)  # repository path -> every step that changed it
    removed: dict[str, int] = field(default_factory=dict)  # repository path (or directory) -> last step rm'd
    edits_unknown: bool = False  # a whole-patch write changed files it did not name
    shell: list[ShellEntry] = field(default_factory=list)  # (step, command, output)
    shell_raw: list[str] = field(default_factory=list)  # the same commands as written (newlines kept)
    observations: list[str] = field(default_factory=list)  # every tool result, for verbatim quotes
    # test-runner invocations by the shared layer (``evidence.runs_from``): a call holding one, whatever came of it ...
    test_attempts: list[ShellEntry] = field(default_factory=list)
    test_runs: list[ShellEntry] = field(default_factory=list)  # ... and the calls holding a valid one (tests really ran)
    writes: dict[str, list[int]] = field(default_factory=dict)  # watched report path -> every successful write step
    last_step: int = 0
    workdir: str | None = None  # the repository root, as the shared layer reads it

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
        """Edits to the repository's own source files: files the run itself brought into being at the
        repository root, or that are note-like, are the run's scratch (reproduction scripts, summaries),
        not source the existing tests depend on; and a test file -- one the run created, or an existing
        test module it added tests to -- is no source change (R1 of the 11-24 review: "before any source
        file is modified", 01-reverse-engineering.md; the shared ``facts.source_change_steps``)."""
        new = self.new_files
        return {p: n for p, n in self.edited.items() if not (is_test_file(p) or (p in new and ("/" not in p or F.DOCLIKE_RE.search(p))))}

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

    def tests_in(self, after: int | None = None, before: int | None = None) -> list[ShellEntry]:
        return [e for e in self.test_runs if (after is None or e[0] > after) and (before is None or e[0] < before)]

    def attempts_in(self, after: int | None = None, before: int | None = None) -> list[ShellEntry]:
        return [e for e in self.test_attempts if (after is None or e[0] > after) and (before is None or e[0] < before)]

    def shell_in(self, after: int | None = None, before: int | None = None) -> list[ShellEntry]:
        return [e for e in self.shell if (after is None or e[0] > after) and (before is None or e[0] < before)]

    def command_run(self, tokens: list[str], after: int | None = None, before: int | None = None, started: bool = False) -> bool:
        """Some shell step within (after, before) ran a test command holding every token, read against the
        directory it ``cd``'d into (``evidence.command_has_tokens``). Only a test-runner invocation counts: a ``grep``
        or ``cat`` of the recorded test file holds its path too (swebv100 + step24 004741: 12 of 449 recorded
        stage-1 commands were never run but looked up). ``started``: only a valid run (tests really ran) counts."""
        return bool(tokens) and any(
            command_has_tokens(e.raw, tokens) and e.runs and (not started or any(r.valid for r in e.runs))
            for e in self.shell
            if (after is None or e[0] > after) and (before is None or e[0] < before)
        )

    def targets(self, entry: ShellEntry) -> list[str] | None:
        """What a shell call's test runs target (``test_targets`` read in the directory the call ran in)."""
        return test_targets(entry.raw, entry.cwd, self.workdir)

    def whole_suite(self, entry: ShellEntry) -> bool:
        """A test run of the call selects nothing at the repository root: the whole suite (``evidence.full_suite``)."""
        return any(SE.full_suite(h.seg, self.workdir or TEXT_CWD) for h in _test_hits(entry.raw, entry.cwd or self.workdir or TEXT_CWD))

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


def _observe(run: Run, watch: Iterable[str] = (), shared=None, workdir: str | None = None) -> Observed:
    """Index ``run``. ``watch`` are report paths whose successful writes are recorded in ``writes``
    (and kept out of ``created``), matched exactly or, for a directory ending in ``/``, by prefix.

    ``shared``: the shared layer's facts of the same run (``workflow_rubric.facts.build``), whose ``runs`` say which
    calls invoke a test runner and which of those really ran tests (``RunFact.valid``: the runner in command position,
    its own summary with a test run in this call's output, targets that existed before the agent -- a lookup, an
    install, ``--collect-only``, a run of only agent-written tests or a runner that did not start is no valid run)."""
    watch = list(watch)
    obs = Observed(workdir=workdir)
    runs: dict[tuple[int, int], list] = {}
    for r in getattr(shared, "runs", None) or []:
        if r.kind == "test":
            runs.setdefault((int(r.step), r.action_index), []).append(r)
    cwd_track = getattr(shared, "_cwd_track", None) or {}

    def watched(p: str) -> str | None:
        for wpath in watch:
            if p == wpath or (wpath.endswith("/") and p.startswith(wpath)):
                return p
        return None

    for step in run.steps:
        obs.last_step = step.n
        for idx, a in enumerate(step.actions):
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
            # (the shared layer parses the same episode: the same steps, the same calls in each)
            here = [r for r in runs.get((step.n, idx), []) if r.command == cmd]
            entry = ShellEntry(step.n, flat, out, raw=cmd, cwd=cwd_track.get((step.n, idx)), runs=here)
            obs.shell.append(entry)
            obs.shell_raw.append(cmd)
            if here:
                obs.test_attempts.append(entry)
                if any(r.valid for r in here):
                    obs.test_runs.append(entry)
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


# The runner script could not be found: the reproduction script's run (``atom/H11``) is no result.
_NOT_STARTED = re.compile(r"can't open file|No such file or directory: '[^']*(?:runtests|manage)\.py'|ERROR: file or directory not found|ERROR: not found:", re.I)


# --- test runs, read by the shared layer (``workflow_rubric``) ---------------------------------------------------
# What a test run is, whether it really ran, what it targets and what a test file is: the shared layer's answers,
# the ones every other workflow's scorer and the training metrics read. A call recorded in an artifact (no run to
# look at) is read with the same classifier, in the repository root.

TEXT_CWD = "/testbed"  # where an artifact's recorded command runs when the task names no repository root


def _test_hits(command: str | None, cwd: str | None) -> list:
    """The test-runner invocations of ``command`` run in ``cwd`` (``evidence.classify`` on its shell segments: the
    runner is a segment's verb -- ``cat tox.ini``, ``pip install pytest`` and ``grep pytest`` run none)."""
    try:
        segs = SH.flat(SH.split((command or "")[: SR.MAX_CMD], cwd)[0])
    except Exception:  # noqa: BLE001 -- agent text: an unparsable command runs nothing we can attribute
        return []
    out = []
    for seg in segs:
        try:
            hit = SE.classify(seg)
        except Exception:  # noqa: BLE001
            continue
        if hit is not None and hit.runner.kind == "test":
            out.append(hit)
    return out


def is_test_attempt(command: str | None, cwd: str | None = None) -> bool:
    """``command`` invokes a test runner, whatever came of it (``evidence.classify``). For a call the run made, the
    shared layer's ``RunFact``s say the same (``Observed.test_attempts``); this reads a command as text."""
    return bool(_test_hits(command, cwd or TEXT_CWD))


def _hit_targets(hit, workdir: str | None) -> list[str]:
    """What one invocation targets, repository-relative: its node ids, the files and directories it names (but
    those a node id already names), its dotted labels, and the options that narrow it (``-k expr``, ``-m mark``,
    ``--deselect``, ``--ignore``: ``results.selection``). The repository root itself names nothing."""
    nodes = [n for n in (_repo_path(x, workdir) for x in hit.node_ids) if n]
    named = {n.split("::", 1)[0] for n in nodes}
    files = [f for f in (_repo_path(t, workdir) for t in hit.targets) if f and f not in named]
    loose = [t[2:] if t.startswith("./") else t for t in hit.loose]
    labels = [lbl for lbl, _ in hit.labels]
    options = [o for o in SR.selection(hit.seg.text) if o.startswith("-")]
    return list(dict.fromkeys([*nodes, *files, *loose, *labels, *options]))


def test_targets(command: str | None, cwd: str | None = None, workdir: str | None = None) -> list[str] | None:
    """What a test command targets (``_hit_targets`` over its test-runner invocations), or None when it invokes no
    test runner. ``[]``: a runner with no target. ``cwd``: where it ran (an artifact's command: the repository root)."""
    hits = _test_hits(command, cwd or workdir or TEXT_CWD)
    if not hits:
        return None
    return list(dict.fromkeys(t for h in hits for t in _hit_targets(h, workdir)))


def test_runs_of(shared) -> list:
    """The shared layer's test-runner invocations (``RunFact``s of kind ``test``, valid or not) of a run's facts."""
    return [r for r in (getattr(shared, "runs", None) or []) if r.kind == "test"]


def bare_facts(episode, workdir: str | None, diff: dict[str, str] | None = None):
    """The shared layer's facts of ``episode`` -- an rLLM episode, or a run already parsed into steps of actions --
    with no rubric (as ``rollout_metrics.test_evidence`` reads a rollout): for a reading made without the engine's
    context. Empty facts when the episode cannot be read."""
    from recipe.grpo.qwen3_5.workflow_rubric.context import Collected, Facts
    from recipe.grpo.qwen3_5.workflow_rubric.schema import Rubric
    from recipe.grpo.qwen3_5.workflow_rubric.trace.episode import episode_to_run

    try:
        rubric = Rubric(workflow="", sources=[], roots={}, stages=[], artifacts={}, items=[], scoring={})
        run = episode if hasattr(episode, "steps") else episode_to_run(episode)
        return SF.build(rubric, run, Collected(workdir=workdir, diff=diff, mode="offline"))
    except Exception:  # noqa: BLE001 -- a harness without a trace front end, or agent text the replay cannot take
        return Facts()


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


def ran_real_test(shared, workdir: str | None = None) -> bool:
    """Some test-runner invocation of the run really ran tests: a valid shared ``RunFact`` of kind ``test``.
    ``shared``: the run's shared facts, or the run itself (its facts built here, ``bare_facts``)."""
    if not hasattr(shared, "runs"):
        shared = bare_facts(shared, workdir)
    return any(r.valid for r in test_runs_of(shared))


def patch_files(patch: str | None) -> tuple[list[str], list[str]] | None:
    """(changed, added) repository paths of the run's patch, or None when the patch is unknown."""
    if patch is None:
        return None
    return F.diff_files(patch)


def removed_line_files(patch: str | None) -> list[str] | None:
    """Repository paths whose diff block removes or rewrites an existing line (a ``-`` line in a hunk, not the
    ``---`` header); a file that only gains lines is not one. None when the patch is unknown. (v5: a test file may
    gain a test, never lose or change one of its lines; the reading of legacy/rubric/facts.py
    ``diff_files_with_removed_lines``.)"""
    if patch is None:
        return None
    out = []
    for block in re.split(r"^diff --git ", patch, flags=re.M)[1:]:
        hit = re.match(r"a/(\S+) b/(\S+)", block)
        if not hit:
            continue
        body = block.split("\n@@", 1)
        if len(body) > 1 and re.search(r"^-(?!--)", "\n@@" + body[1], re.M):
            out.append(norm_path(hit.group(2)))
    return out


_SED_INPLACE = re.compile(r"\bsed\s+(?:-\w+\s+)*-i")


def test_line_changes(run: Run, test_files=()) -> list[tuple[int, str]]:
    """(step, path) of each trajectory edit that changes or removes a line a repository test file had: an editor
    ``replace`` whose old text the new text does not keep, a whole-file ``create`` over a test file the run had seen
    (its old lines are not kept as such), a ``sed -i`` or a ``>`` (not ``>>``) write to one. Lines the run itself
    wrote (a new module, a test it added and then corrected) are not the file's: a file the run created unseen is
    left out, and a replace whose old text lies inside the run's own earlier additions to that file. Seen in the
    patch the change may be gone (put back); the trajectory still shows it."""
    seen: set[str] = set()
    new: set[str] = set()
    added: dict[str, list[str]] = {}
    out: list[tuple[int, str]] = []

    def repo_test(p: str) -> str | None:
        q = norm_path(p or "")
        return q if p and not F.OUTSIDE_REPO_RE.match(p) and is_test_file(q, test_files) else None

    for step in run.steps:
        for a in step.actions:
            if a.kind == "view":
                seen.add(norm_path(a.path or ""))
                continue
            if a.status == "fail":
                continue
            if a.kind in ("create", "replace", "insert"):
                q = repo_test(a.path or "")
                if q is None:
                    continue
                if a.kind == "create":
                    if q in seen and q not in new:
                        out.append((step.n, q))
                    elif q not in seen:
                        new.add(q)
                elif q not in new:
                    old, text = (a.old or "").strip("\n"), a.text or ""
                    if a.kind == "replace" and old and old not in text and not any(old in x for x in added.get(q, [])):
                        out.append((step.n, q))
                    added.setdefault(q, []).append(text)
                seen.add(q)
                continue
            if a.kind != "shell":
                continue
            cmd = F.drop_heredoc_bodies(a.command or "")
            for t in F.write_targets(a):
                q = repo_test(t)
                if q is None or q in new or F._rm_matches(a.command or "", t):
                    continue
                if _SED_INPLACE.search(cmd) or re.search(rf"(?<!>)>\s*['\"]?{re.escape(t)}", cmd):
                    out.append((step.n, q))
    return out


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


def is_test_file(path: str, test_files=()) -> bool:
    """A test file: one the task's test_patch touches, or a test file by the shared layer's rule
    (``facts.is_test_path``: ``tests/``, ``test_x.py``, ``x_test.py``, ``tests.py``, ``conftest.py`` ...; a library's
    own test framework, ``django/test/utils.py``, is library code -- TRACE X14)."""
    return path in test_files or SF.is_test_path(path)


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


def observe(run: Run, shared=None, workdir: str | None = None) -> Observed:
    """The shared trajectory index, with the five artifact paths watched (their writes are the
    stage write steps, not repository edits); ``shared``: the shared layer's facts of the run (its test runs)."""
    return _observe(run, watch=A.ARTIFACT_PATHS, shared=shared, workdir=workdir)


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
