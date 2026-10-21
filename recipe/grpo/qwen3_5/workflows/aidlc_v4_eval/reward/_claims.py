"""Shared machinery for a workflow's content checks: what the run did, and how to read a report.

A workflow's ``reward/content_checks.py`` grades the CLAIMS its reports make against the trajectory.
The claims differ per workflow (AI-DLC's ``- Passing:`` baseline, Spec Kit's ``Checks Performed`` table,
OpenSpec's ``X/Y tasks`` scorecard) but the evidence and the ways of comparing do not, so they live
here:

    Observed / observe   the trajectory indexed by what matters to a claim: files read, created, edited
                         and removed in the repository, shell commands with their output, test-runner
                         invocations, the first write of each report
    report readers       ``##`` sections, ``- Label:`` / ``- **Label**:`` fields, markdown tables,
                         ``- [ ]`` checkboxes, ``path:line`` references, requirement ids
    evidence readers     pytest / unittest summaries, exit codes, "no tests ran"
    verdicts             SUPPORTED / PARTIAL / CONTRADICTED / None (not applicable) and the
                         ``membership`` / ``both_ways`` reductions every check is built from

Verdict policy, shared by every workflow: a claim nothing bears on is not applicable, never
contradicted, so a run cannot lose for a measurement gap; and a report that was never written makes
no claims. ``none`` is a claim like any other and is held to the evidence that would make it true.

The tool-call parsing (``Run``, ``Action``) is the vendored rubric's, under ``reward/rubric`` (copied from aidlc_v4);
it is harness-specific (openhands-sdk), not workflow-specific, which is why every workflow reads
through it.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from statistics import mean

from .rubric import facts as F
from .rubric.model import Run

SUPPORTED, PARTIAL, CONTRADICTED = 1.0, 0.5, 0.0

# --- regexes ------------------------------------------------------------------------------

SOURCE_EXT = re.compile(
    r"\.(py|pyi|pyx|js|jsx|mjs|cjs|ts|tsx|go|rs|java|kt|rb|php|c|h|cc|cpp|hpp|cs|swift|sh|"
    r"yaml|yml|toml|json|cfg|ini|txt|md|rst|html|css|sql)$",
    re.I,
)
PATH_RE = re.compile(r"[\w./-]*[\w-]/[\w./-]+|[\w-]+\.[A-Za-z]{1,5}\b")
PATH_LINE_RE = re.compile(r"((?:[\w./-]*/)?[\w-]+\.[A-Za-z]{1,5}):(\d+)")
TEST_ID = re.compile(r"\b(test_\w+)")
R_ID = re.compile(r"\bR\d+\b")
NONE_VALUE = re.compile(r"^(?:none|none stated|not applicable|n/?a|empty)\b[.,]?$", re.I)
PLACEHOLDER = re.compile(r"^(?:tbd|todo|-+|\.{2,}|\?+|\[.*\]|<.*>)?$", re.I)
CHECKBOX = re.compile(r"^\s*[-*+]\s*\[([ xX]?)\]\s*(.*)$", re.M)
READ_VERB = re.compile(r"\b(?:cat|sed|head|tail|grep|rg|less|more|awk|nl|wc|bat|view|open)\b")
RUNNERS = rf"(?:{F.RUNNER}|pytest|py\.test|python[0-9.]*\s+-m\s+pytest)"
EXIT_CODE = re.compile(r"exit code[:\s]+(\d+)")
FAILURES = re.compile(r"\b(\d+) (?:failed|errors?)\b|\bfailures=(\d+)|\berrors=(\d+)", re.I)
PASSES = re.compile(r"\b(\d+) passed\b")
NO_TESTS = re.compile(r"collected 0 items|no tests? (?:ran|found|to run|were run)", re.I)
PATCH_WRITE = re.compile(r"\bgit\s+apply\b|\bpatch\s+-p\d|\bgit\s+(?:checkout|restore)\s+\S+\s+--\s+\S")
NOT_A_PATH = re.compile(r"[()=,<>\"'`$]")
DUPLICATE = re.compile(r"(?:[-_.](?:new|fixed|backup|copy|old|orig|bak|tmp|v\d+|\d+))\.\w+$|\.(?:bak|orig|rej)$|(?:^|/)[^/]*\bcopy\b[^/]*$", re.I)
# Test runners the vendored rubric's TEST_RUN_PATTERNS do not know: Django's runtests.py / manage.py test
# (most of SWE-bench Verified), nose, ward.
EXTRA_TEST_RUN = re.compile(r"\bruntests\.py\b|\bmanage\.py\s+test\b|\bnosetests?\b|\bward\b")
NETWORK = re.compile(r"\b(?:curl|wget|pip3?\s+install|npm\s+install|apt(?:-get)?\s+install|conda\s+install|uv\s+pip\s+install)\b")


# --- paths --------------------------------------------------------------------------------


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
        if tok and ("/" in tok or SOURCE_EXT.search(tok)) and tok not in out:
            out.append(tok)
    return out


def path_line_refs(text: str | None) -> list[tuple[str, int]]:
    """``file.py:42`` references."""
    return [(norm_path(p), int(n)) for p, n in PATH_LINE_RE.findall(text or "")]


def pathlike(t: str) -> bool:
    """A shell write target that can be a file: the rubric's extraction is best effort and a ``>``
    inside ``python -c`` code yields tokens like ``0`` or ``Expected``."""
    return bool(t) and not NOT_A_PATH.search(t) and ("/" in t or SOURCE_EXT.search(t) is not None)


def is_none(value: str | None) -> bool:
    """A field that says none / n/a (its first clause, so ``none (Python project)`` counts)."""
    return bool(value) and NONE_VALUE.fullmatch(value.split("(")[0].strip()) is not None


def is_filler(value: str | None) -> bool:
    return not value or PLACEHOLDER.fullmatch(value.strip()) is not None


def r_ids(text: str | None) -> list[str]:
    return list(dict.fromkeys(R_ID.findall(text or "")))


# --- commands -----------------------------------------------------------------------------


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


def names_test_ids(out: str) -> bool:
    return TEST_ID.search(out) is not None


def last_exit(out: str) -> int | None:
    codes = EXIT_CODE.findall(out)
    return int(codes[-1]) if codes else None


# --- verdicts -----------------------------------------------------------------------------


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


# --- reading a report ---------------------------------------------------------------------

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


def field_value(body: str | None, label: str) -> str | None:
    """Value of a ``- Label: value`` / ``- **Label**: value`` line with its indented continuation
    lines. None when the label is absent (or the body is), "" when present but empty or a placeholder."""
    if body is None:
        return None
    lines = body.splitlines()
    lab = re.compile(rf"^\s*(?:[-*+]\s*)?\*{{0,2}}{re.escape(label)}\*{{0,2}}\s*:\s*\**", re.I)
    other = re.compile(r"^\s*(?:[-*+]\s*)?\*{0,2}[A-Za-z][\w &/()-]{2,40}\*{0,2}\s*:")
    for i, line in enumerate(lines):
        m = lab.match(line)
        if not m:
            continue
        val = [line[m.end() :].strip()]
        for nxt in lines[i + 1 :]:
            if not nxt.strip() or lab.match(nxt) or other.match(nxt) or nxt.lstrip().startswith(("#", "|")):
                break
            val.append(nxt.strip())
        text = " ".join(v for v in val if v).strip(" *`")
        return "" if PLACEHOLDER.fullmatch(text) else text
    return None


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


# --- what the run did ---------------------------------------------------------------------


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
            seen_before = any(same_file(q, p) and m < n for q, m in self.viewed.items())
            edited_before = any(m < n for m in self.edit_steps.get(p, []))
            if not seen_before and not edited_before:
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
        base, module = re.escape(name), re.escape(name.rsplit(".", 1)[0])
        pat = re.compile(
            rf"\b{RUNNERS}\s+(?:-\S+\s+)*\S*{base}(?:\s|$|::)|(?:^|\s)\.?/\S*{base}(?:\s|$)"
            rf"|\bpython[0-9.]*\s+-c\s+\S*(?:import\s+{module}\b|from\s+{module}\s+import)"
        )
        return [(n, c, o) for n, c, o in self.shell if pat.search(c) and (after is None or n > after) and (before is None or n < before)]

    def tests_in(self, after: int | None = None, before: int | None = None) -> list[tuple[int, str, str]]:
        return [(n, c, o) for n, c, o in self.test_runs if (after is None or n > after) and (before is None or n < before)]

    def attempts_in(self, after: int | None = None, before: int | None = None) -> list[tuple[int, str, str]]:
        return [(n, c, o) for n, c, o in self.test_attempts if (after is None or n > after) and (before is None or n < before)]

    def shell_in(self, after: int | None = None, before: int | None = None) -> list[tuple[int, str, str]]:
        return [(n, c, o) for n, c, o in self.shell if (after is None or n > after) and (before is None or n < before)]

    def command_run(self, tokens: list[str], after: int | None = None, before: int | None = None) -> bool:
        return bool(tokens) and any(all(t in c for t in tokens) for n, c, _ in self.shell_in(after, before))

    def command_runs(self, command: str, after: int | None = None, before: int | None = None) -> list[tuple[int, str, str]]:
        """Shell steps that ran ``command`` as written (all its core tokens present)."""
        tokens = command_core(command)
        return [(n, c, o) for n, c, o in self.shell_in(after, before) if tokens and all(t in c for t in tokens)]

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


def observe(run: Run, watch: Iterable[str] = ()) -> Observed:
    """Index ``run``. ``watch`` are report paths whose successful writes are recorded in ``writes``
    (and kept out of ``created``), matched exactly or, for a directory ending in ``/``, by prefix."""
    watch = list(watch)
    obs = Observed()

    def watched(p: str) -> str | None:
        for wpath in watch:
            if p == wpath or (wpath.endswith("/") and p.startswith(wpath)):
                return p
        return None

    for step in run.steps:
        obs.last_step = step.n
        for a in step.actions:
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
            if F.is_test_attempt(a) or EXTRA_TEST_RUN.search(F.command_skeleton(cmd)):
                obs.test_attempts.append((step.n, flat, out))
                if F.ran_something(a):
                    obs.test_runs.append((step.n, flat, out))
            skeleton = F.command_skeleton(cmd)
            if READ_VERB.search(skeleton):
                for p in re.findall(r"(?<![\w-])(/?[\w.-]+(?:/[\w.-]+)+)", skeleton):
                    if not F.OUTSIDE_REPO_RE.match(p) or p.startswith("/testbed/"):
                        obs.viewed.setdefault(norm_path(p), step.n)
            if PATCH_WRITE.search(skeleton):
                obs.edits_unknown = True
            if a.status == "fail":
                continue
            for t in F.write_targets(a):
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
    from .rubric import artifacts as A  # the rubric's shell-write recovery

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


# --- collecting a workflow's output directory from the sandbox -------------------------------

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
