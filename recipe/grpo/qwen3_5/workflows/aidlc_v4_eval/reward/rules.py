"""What the run did against the workflow's rules, whatever its artifacts claim: the rule checks and the
atomic checks (``rubric.yaml`` items ``rule/*`` and ``atom/*``).

Rule checks (:func:`rule_checks`, 1 / 0 / None each, ``aidlc/rules`` their mean). The content checks hold each artifact claim to the trajectory, so a violation reported honestly -- a test
file edited and listed as modified, a reproduction script left in the repository and listed as created --
passes them. These checks look at what the run did, against the rules the documents state:

    r_tests_untouched       no existing test file changed: the patch, plus a test edited and put back
                            (01 Step 3, 04, 05 Step 5, core "DO NOT MODIFY: test files")
    r_targeted_tests        every test run of stage 5 names its targets (05 Step 3: "Do NOT run the full
                            repository test suite"); ``-k`` selects too
    r_no_env_setup          nothing installed (01 Step 2, 05 Step 1, core "Do not spend effort on
                            environment setup")
    r_repro_not_in_stage4   the reproduction script not run in stage 4 (04 Step 2: "do not execute it in
                            this stage")
    r_artifacts_written_once  each artifact written once, never rewritten later (core "One write, full
                            content", "Never rewrite an earlier stage's artifact")
    r_repo_clean            no scratch, backup, duplicate or generated file added to the repository (05
                            Step 7); the reproduction script belongs outside it

Atomic checks (:func:`atomic_checks`): each is named after the atomic rule it judges (its rubric item
places it by category and stage) and is 1 (kept) / 0 (broken) / None (nothing bears on it). Rules that
hold per artifact are scored per stage, as ``<rule>@<stage>`` (``aidlc/atom/<rule>[@<stage>]``).

    form         B5d skeleton sentences kept, B6b/B6c frontmatter values, D5/F2a full paths, D12b one test id
                 per line, E4a one sequence R1..Rn, E8c edge items "condition -> behaviour", F1b steps 1..n,
                 F2b "(modify in place | create)", G8b deviations classified, S4.tags requirement tags, H15a
                 allowed values, H15d "test id -> ..." items
    consistency  G3c planned creations made, H1a/H4a stage 5 reruns stage 1's build and test selection,
                 H15b verdict vs regressions, H15c unmet requirements vs the reproduction result
    execution    H8a a failing reproduction is followed by a source fix, H8e no regression left unfixed,
                 H9a a stage-5 fix is re-verified, D10a stage 1 read or ran existing tests, H1b stage 5 ran the
                 recorded build (D10a and H1b are reports too: their A items are content checks)
    forbidden    B10 no design/report document, E10a no question file, F7 no step on a test file, F8a/F8b
                 no create over an existing file or duplicate variant, G4b no new test file in the
                 repository, C2 no stage document re-read after its stage closed
    content      D1b files the issue names are in scope, D4a language
                 matches the files, D7b the test command names targets, E7b no non-functional requirement
                 the task does not state, F4b the reproduction exercises the edge-case requirements
    writing      B3a an artifact written once, whole, in its stage; B4a an earlier stage's artifact never
                 rewritten once the next stage began
    procedure    B8 no artifact re-read (with no history condensing, a written artifact stays visible),
                 E10b the run does not end asking for input, G3a a stage-4 file is looked for before it is
                 written, G1a steps are carried out in plan order, H1c a failing build is fixed before
                 anything else is verified, H10 no endless retry
    more         D8 the test command reduces output, D4b no unfiltered survey of the repository in stage 1,
                 H7 no baseline rebuilt from stashed source, E3a one sentence per requirement, F9b new
                 files go under existing directories, F3 the issue's names are not altered, H11 a failed
                 or unmet reproduction is left outstanding
    found by the independent rule extraction (2026-10-27): D5b Files one path per line, B11 no file in the
                 artifact directory but the five artifacts, G7c stage 4 runs no test, H17 no stage-5 source change
                 before anything failed, E10c no approval asked mid-run
"""

from __future__ import annotations

import re

from . import read as EV
from . import skeleton as A
from . import trace as F
from .read import DUPLICATE, R_LINE, Observed, _field, _section_none, bullets, claimed_paths, command_core, failures, is_none, norm_path, r_ids, same_file, task_text

RULE_CHECKS = ["r_tests_untouched", "r_targeted_tests", "r_no_env_setup", "r_repro_not_in_stage4", "r_artifacts_written_once", "r_repo_clean"]

# Every key :func:`atomic_checks` may set (a rule, or ``<rule>@<stage>`` for one held per artifact).
ATOMIC = (
    *(f"{r}@{k}" for r in ("B6b", "B6c") for k in range(1, 6)),
    "B5d@1",
    "B5d@4",
    *"B3a B4a B8 B10 C2 D1b D4a D4b D5 D7b D8 D10a D12b E3a E4a E7b E8c E10a E10b F1b F2a F2b F3 F4b F7 F8a F8b F9b".split(),
    *"G1a G3a G3c G4b G8b H1a H1b H1c H4a H7 H8a H8e H9a H10 H11 H15a H15b H15c H15d S4.tags".split(),
    *"D5b B11 G7c H17 E10c".split(),
)

_MEDIA = re.compile(r"\.(?:png|jpe?g|gif|bmp|pdf|svg|eps)$", re.I)

_ROOT_SCRATCH = re.compile(r"^[^/]+\.(?:py|sh|txt|md|log|json|out|diff|patch)$")


def _scratch(path: str, test_files) -> bool:
    """An added repository file that is no part of a fix: scratch-named, a backup or duplicate, build
    output, a generated image outside the tests, or a loose script or note at the repository root."""
    if _ROOT_SCRATCH.match(path) and path not in test_files:
        return True
    if EV.is_test_file(path, test_files) and not _MEDIA.search(path):
        return False
    return bool(F.SCRATCH_HINT_RE.search(path) or F.BACKUP_RE.search(path) or F.ARTIFACT_RE.search(path) or DUPLICATE.search(path) or _MEDIA.search(path) or _ROOT_SCRATCH.match(path))


def rule_checks(run, obs: Observed, parsed: dict, read_step: dict, write_step: dict, patch: str | None, test_files=()) -> dict:
    """``read_step``: rule document ("01".."05") -> first read; ``write_step``: stage -> first artifact write."""
    c: dict[str, float | None] = dict.fromkeys(RULE_CHECKS)
    final = EV.patch_files(patch)

    # Existing test files changed: still changed in the patch, or edited and put back.
    changed_tests = [p for p in obs.edited if EV.is_test_file(p, test_files) and p not in obs.new_files]
    if final is not None:
        added = set(final[1])
        changed_tests += [p for p in final[0] if p not in added and EV.is_test_file(p, test_files)]
    c["r_tests_untouched"] = 0.0 if changed_tests else 1.0

    # Stage 5's test runs name their targets.
    start5 = write_step.get(4) or read_step.get("05")
    if start5 is not None:
        runs = obs.tests_in(after=start5, before=write_step.get(5))
        if runs:
            untargeted = [cmd for _, cmd, _ in runs if EV.test_targets(cmd) == []]
            c["r_targeted_tests"] = 0.0 if untargeted else 1.0

    c["r_no_env_setup"] = 0.0 if any(EV.is_env_setup(raw) for raw in obs.shell_raw) else 1.0

    repro = next((p for st in (4, 3) if parsed.get(st) for p in claimed_paths(A.field_value(parsed[st]["section_bodies"].get("Reproduction Script") or "", "Path"))), None)
    r4, w4 = read_step.get("04"), write_step.get(4)
    if repro and r4 is not None and w4 is not None:
        c["r_repro_not_in_stage4"] = 0.0 if obs.ran(repro, after=r4, before=w4) else 1.0

    writes = {path: steps for path, steps in obs.writes.items() if path in A.ARTIFACT_PATHS}
    if writes:
        c["r_artifacts_written_once"] = 0.0 if any(len(steps) > 1 for steps in writes.values()) else 1.0

    if final is not None:
        c["r_repo_clean"] = 0.0 if any(_scratch(p, test_files) for p in final[1]) else 1.0

    applicable = [v for v in c.values() if v is not None]
    return {"checks": c, "rules": sum(applicable) / len(applicable) if applicable else None}


_LITERALS = {1: ["Recorded before any source file was modified."], 4: ["- Executed: no"]}

_TEST_LIKE = re.compile(r"::|\btest_\w+|\w+ \([\w.]+\)|\.[Tt]est\w*\b")

_ARROW = re.compile(r"->|→")

_ISSUE_PATH = re.compile(r"(?<![\w/.-])((?:[\w-]+/)+[\w.-]+\.(?:py|pyi|js|ts|go|rs|java|rb|c|h|cpp|cfg|toml|ini))\b")

_PERF = re.compile(r"\b(?:performance|slow(?:er|ly)?|fast(?:er)?|speed|memory|complexity|efficien\w*|latency|O\(|quadratic|linear time|time-?out)\b", re.I)

_LANG = {"py": "python", "pyi": "python", "js": "javascript", "ts": "typescript", "go": "go", "rs": "rust", "java": "java", "rb": "ruby", "c": "c", "h": "c", "cpp": "c++"}

_DOC = re.compile(r"\.(?:md|rst)$|(?:^|/)[^/]*(?:plan|summary|report|notes|design)[^/]*\.(?:md|txt|rst)$", re.I)

_ARTIFACT = re.compile(r"/tmp/swe-bench-pro/(0[1-5])-[\w-]+\.md")

_READ_VERB = re.compile(r"^\s*(?:sudo\s+)?(?:cat|head|tail|less|more|grep|egrep|sed\s+-n|awk|nl)\b")

# A message that hands the run back to the user (E10c, before the last turn: the narrower phrases, since a
# working note says "should I check ..." to itself)
_ASK_USER = re.compile(
    r"\b(?:would you like me to|do you want me to|shall i (?:proceed|continue|go ahead)|please (?:confirm|approve|advise|let me know)"
    r"|awaiting your|let me know (?:if|whether|how) you|before i (?:proceed|continue), (?:please|could you))\b",
    re.I,
)

_LABEL_LINE = re.compile(r"^\s*[-*]\s*[A-Z][\w /&().-]*:")

_ASK = re.compile(r"\b(?:would you like|shall i|should i|do you want|let me know|please (?:confirm|review|advise|approve)|awaiting your|your (?:approval|confirmation|input))\b", re.I)

_REDUCE = re.compile(r"(?<!\S)-[a-zA-Z]*q[a-zA-Z]*\b|--quiet\b|--tb=(?:short|line|no)\b|--no-header\b")

_STASH = re.compile(r"^\s*git\s+stash(?:\s+(?:push|save)\b.*)?\s*$|^\s*(?:git\s+apply|patch)\b.*\s-R\b")

_UNSTASH = re.compile(r"^\s*git\s+stash\s+(?:pop|apply)\b")

_CODE_LIKE = re.compile(r"_|\.|[a-z][A-Z]")

_GREP_FED = re.compile(r"\|\s*(?:xargs\s+)?grep|-exec\s+grep")

# a find that names what it looks for: anything but a bare "*" or "*.ext" (``-name "py.py"`` is a lookup)
_NAME_FILTER = re.compile(r"-(?:i?name|i?path|regex)\s+(?!['\"]?\*(?:\.\w+)?['\"]?(?:\s|$))\S")

_IDENT = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")

_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

_ABBREV = re.compile(r"\b(?:e\.g|i\.e|etc|vs|cf)\.", re.I)


def _plain_segments(command: str) -> list[str]:
    """The command split at ``&&`` / ``||`` / ``;`` / newlines, quoted strings kept (``evidence.segments``
    blanks them, and a ``find -name "*foo*"`` filter is in the quotes)."""
    return [s.strip() for s in re.split(r"&&|\|\||;|\n", F.drop_heredoc_bodies(command or "")) if s.strip()]


def _near(a: str, b: str) -> bool:
    """One edit apart (insert, delete or substitute), not a case-only difference."""
    if a == b or a.lower() == b.lower() or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    s, t = (a, b) if len(a) < len(b) else (b, a)
    return any(t[:i] + t[i + 1 :] == s for i in range(len(t)))


def _lines(value: str) -> list[str]:
    """A field's items, one per line (a field value's continuation lines are joined by spaces, so a
    multi-item value reads as one line: "one per line" is then not kept)."""
    return [x.strip(" -*`") for x in re.split(r"\n+", value or "") if x.strip(" -*`")]


def _dotted(target: str) -> str:
    """A test target as a dotted name, so a pytest path and a Django label compare: ``tests/migrations/
    test_operations.py::OperationsTests::test_x`` and ``migrations.test_operations.OperationsTests.test_x``
    both read ``migrations.test_operations.OperationsTests.test_x``."""
    t = target.removeprefix("/testbed/").removeprefix("./")
    path, _, node = t.partition("::")
    if path.endswith(".py"):
        t = path[:-3].replace("/", ".") + ("." + node.replace("::", ".") if node else "")
    return t.removeprefix("tests.")


def _covers(selection: list[str], target: str) -> bool:
    """``target`` is in ``selection``: the same, or under a file / class / module of it."""
    for u in selection:
        for a, b in ((target, u), (_dotted(target), _dotted(u))):
            if a == b or any(a.startswith(b.rstrip("/") + sep) for sep in ("::", ".", "/")):
                return True
    return False


def _raw_rows(body: str, label: str) -> list[str]:
    """A field's physical lines in the artifact: the label line's value and the lines under it up to the next
    label (``skeleton.field_value`` joins them, so "one per line" cannot be read from the value)."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        m = re.match(rf"^\s*[-*]\s*{re.escape(label)}\s*:(.*)$", line)
        if not m:
            continue
        rows = [m.group(1)]
        for nxt in lines[i + 1 :]:
            if not nxt.strip() or _LABEL_LINE.match(nxt) and not nxt.startswith((" ", "\t")):
                break
            rows.append(nxt)
        return [r.strip(" -*`") for r in rows if r.strip(" -*`")]
    return []


def _frac(flags: list[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


def atomic_checks(
    run, obs: Observed, parsed: dict, read_step: dict, write_step: dict, facts: dict, patch: str | None, task=None, test_files=(), final_words: str | None = None
) -> dict[str, float | None]:
    c: dict[str, float | None] = {}
    final = EV.patch_files(patch)
    known = {norm_path(p) for p in [*obs.viewed, *obs.edited, *obs.created, *(final[0] if final else [])]}
    p1, p2, p3, p4, p5 = (parsed.get(k) for k in range(1, 6))

    def full_paths(paths: list[str]) -> float | None:
        verdicts = []
        for p in paths:
            q = norm_path(p)
            if q in known:
                verdicts.append(True)
            elif "/" not in q and any(k.rsplit("/", 1)[-1] == q and "/" in k for k in known):
                verdicts.append(False)
        return _frac(verdicts)

    repro = next((p for st in (4, 3) if parsed.get(st) for p in claimed_paths(_field(parsed[st], "Reproduction Script", "Path"))), None)
    repro_paths = [p for st in (3, 4) if parsed.get(st) for p in claimed_paths(_field(parsed[st], "Reproduction Script", "Path"))]

    def is_repro(path: str) -> bool:
        return any(same_file(path, q) for q in repro_paths)

    # -- form, per artifact ---------------------------------------------------------------
    for st, p in parsed.items():
        if p is None:
            continue
        fm = p["frontmatter"]
        if fm["present"]:
            c[f"B6b@{st}"] = float((fm["stage"] or "").strip() == str(st))
            c[f"B6c@{st}"] = float((fm["name"] or "").strip() == A.STAGE_FILES[st][1])
        if st in _LITERALS:
            c[f"B5d@{st}"] = float(all(lit in p["body"] for lit in _LITERALS[st]))
    if p1:
        c["D5"] = full_paths(claimed_paths(_field(p1, "Affected Scope", "Files")) + claimed_paths(_field(p1, "Existing Tests", "Path")))
        ids = [x for k in ("Passing", "Failing") if (v := _field(p1, "Baseline", k)) and not is_none(v) for x in _lines(v)]
        # one id per line: a line listing several ("test_a, test_b"; brackets masked for parametrized ids) breaks it
        several = [x for x in ids if sum(bool(_TEST_LIKE.search(p)) for p in re.sub(r"\[[^\]]*\]", "[]", x).split(",")) > 1]
        c["D12b"] = float(all(_TEST_LIKE.search(x) for x in ids) and not several) if ids else None
    if p2:
        seq = list(dict.fromkeys(p2.get("r_ids", [])))
        c["E4a"] = float(seq == [f"R{i}" for i in range(1, len(seq) + 1)]) if seq else None
        edge = p2["section_bodies"].get("Edge Cases & Error Handling") or ""
        lines = [v for _, v in R_LINE.findall(edge) if not is_none(v)]
        c["E8c"] = _frac([bool(_ARROW.search(v)) for v in lines])
    steps = (p3 or {}).get("steps", [])
    if steps:
        c["F1b"] = float([s["n"] for s in steps] == list(range(1, len(steps) + 1)))
        targets = [s["fields"].get("Target") or "" for s in steps]
        c["F2a"] = full_paths([t for v in targets for t in claimed_paths(v)])
        c["F2b"] = _frac([bool(re.search(r"\(\s*(?:modify in place|create)\s*\)", v, re.I)) for v in targets])
    if p4:
        dev = [x for x in bullets(p4["section_bodies"].get("Deviations from Plan")) if not is_none(x)]
        c["G8b"] = _frac([bool(re.match(r"(?:local correction|structural invalidation)\b", x, re.I)) for x in dev])
        claims = [m.group(2) for m in re.finditer(r"^\s*[-*+]\s*\*{0,2}(Modified|Created)\*{0,2}\s*:\s*(.*)$", p4["section_bodies"].get("Changed Files") or "", re.M | re.I)]
        c["S4.tags"] = _frac([bool(re.search(r"\[\s*R\d+", v)) for v in claims if v.strip() and not is_none(v) and not A.PLACEHOLDER.fullmatch(v.strip())])
    if p5:
        allowed = {
            ("Build", "Result"): ("success", "failure"),
            ("Reproduction Script", "Result"): ("pass", "fail"),
            ("Existing Tests vs Baseline", "Verdict"): ("unchanged", "regression resolved", "pre-existing failures only"),
        }
        vals = [(v.lower().strip(" .`*"), ok) for (sec, lab), ok in allowed.items() if (v := _field(p5, sec, lab))]
        c["H15a"] = _frac([v.startswith(ok) for v, ok in vals])
        entries = [v for k in ("Regressions", "Pre-existing failures") if (v := _field(p5, "Existing Tests vs Baseline", k)) and not is_none(v)]
        c["H15d"] = _frac([bool(_ARROW.search(v)) for v in entries])

    # -- consistency ----------------------------------------------------------------------
    if steps and final is not None:
        made = {norm_path(p) for p in final[1]} | {norm_path(p) for p in obs.created}
        existing = {norm_path(p) for p in final[0]} - {norm_path(p) for p in final[1]}
        planned = [t for s in steps if re.search(r"\(\s*create\s*\)", s["fields"].get("Target") or "", re.I) for t in claimed_paths(s["fields"].get("Target"))]
        planned = [t for t in planned if not any(same_file(t, e) for e in existing) and not obs.seen(t, before=write_step.get(3))]
        c["G3c"] = _frac([any(same_file(t, m) for m in made) for t in planned])
    if p1 and p5:
        b1, b5 = _field(p1, "Build & Test Commands", "Build"), _field(p5, "Build", "Command")
        if b1 and b5 and not is_none(b1) and not is_none(b5):
            c["H1a"] = float(command_core(b1) == command_core(b5))
        t1, t5 = EV.test_targets(_field(p1, "Build & Test Commands", "Test") or ""), EV.test_targets(_field(p5, "Existing Tests vs Baseline", "Command") or "")
        if t1 and t5:
            # The baseline's selection rerun: every stage-1 target is covered by a stage-5 one (the same, or
            # a file / class / module that holds it). A narrower rerun is not comparable to the baseline.
            # Or a test run after stage 4 that covers the stage-1 selection, whatever 05 records (a -k selection
            # cannot be compared as a set, so a differing -k in 05 alone decides nothing).
            after4 = write_step.get(4)
            runs5 = [EV.test_targets(cmd) for _, cmd, _ in obs.tests_in(after=after4)] if after4 is not None else []
            rerun = any(tt and all(_covers(tt, t) for t in t1) for tt in runs5)
            c["H4a"] = float(rerun or all(_covers(t5, t) for t in t1))
    if p5:
        verdict = (_field(p5, "Existing Tests vs Baseline", "Verdict") or "").lower()
        reg, pre = _field(p5, "Existing Tests vs Baseline", "Regressions"), _field(p5, "Existing Tests vs Baseline", "Pre-existing failures")
        if verdict:
            if verdict.startswith("unchanged"):
                # unchanged from a baseline that may itself have failed: only a regression contradicts it
                c["H15b"] = float(is_none(reg)) if reg else None
            elif verdict.startswith("pre-existing"):
                c["H15b"] = float(bool(pre) and not is_none(pre) and (not reg or is_none(reg)))
            elif verdict.startswith("regression"):
                c["H15b"] = float(bool(reg) and not is_none(reg))
        result, unmet = (_field(p5, "Reproduction Script", "Result") or "").lower(), _field(p5, "Reproduction Script", "Unmet requirements")
        if result and unmet:
            c["H15c"] = float(is_none(unmet)) if result.startswith("pass") else float(not is_none(unmet)) if result.startswith("fail") else None

    # -- execution in stage 5 -------------------------------------------------------------
    w4, w5 = write_step.get(4), write_step.get(5)
    edits_unseen = final is not None and any(
        q not in set(final[1]) and not EV.is_test_file(q, test_files) and re.search(r"\.(?:py|pyx|js|ts|go|rs|java|rb|c|h|cpp)$", q) and not any(same_file(q, e) for e in obs.edited) for q in final[0]
    )
    if repro and w4 is not None and not edits_unseen:
        runs = obs.ran(repro, after=w4, before=w5)
        failing = [n for n, cmd, out in runs if (code := EV.exit_code(cmd, out)) is not None and code != 0]
        if failing:
            # A failed reproduction is acted on: the source (or the script) changed and it ran again, or the
            # run closed. Moving on to the artifact with nothing done is what the rule forbids.
            acted = [n for p in [*obs.source_edits, repro] for n in obs.edit_steps.get(norm_path(p), []) + ([obs.written(repro)] if p == repro and obs.written(repro) else []) if n > failing[-1]]
            later_runs = [n for n, _, _ in runs if n > failing[-1]]
            c["H8a"] = float(bool(acted) or bool(later_runs))
    baseline = obs.tests_in(before=obs.first_edit) if obs.first_edit is not None else []
    post = obs.tests_in(after=obs.last_edit, before=w5) if obs.last_edit is not None else []
    if baseline and post:
        clean = all(failures(o) == 0 for _, _, o in baseline)
        c["H8e"] = 0.0 if clean and failures(post[-1][2]) > 0 else 1.0
    if w4 is not None:
        fixes = [n for p in obs.source_edits for n in obs.edit_steps.get(p, []) if n > w4 and (w5 is None or n < w5)]
        if fixes:
            last = max(fixes)
            rerun = obs.tests_in(after=last, before=w5) or (obs.ran(repro, after=last, before=w5) if repro else [])
            c["H9a"] = float(bool(rerun))

    # -- forbidden ------------------------------------------------------------------------
    c["B10"] = 0.0 if any(_DOC.search(p) and not p.startswith(A.ARTIFACT_DIR) and not EV.is_test_file(norm_path(p), test_files) for p in obs.created) else 1.0
    c["E10a"] = 0.0 if any(re.search(r"question", p.rsplit("/", 1)[-1], re.I) for p in obs.created) else 1.0
    if steps:
        # The plan's own reproduction script is no test file even when named test_*.py (left in the
        # repository, r_repo_clean catches it).
        targets = [t for s in steps for t in claimed_paths(s["fields"].get("Target")) if not is_repro(t)]
        if targets:
            c["F7"] = 0.0 if any(EV.is_test_file(norm_path(t), test_files) for t in targets) else 1.0
            c["F8b"] = 0.0 if any(DUPLICATE.search(t) or F.BACKUP_RE.search(t) for t in targets) else 1.0
        creates = [t for s in steps if re.search(r"\(\s*create\s*\)", s["fields"].get("Target") or "", re.I) for t in claimed_paths(s["fields"].get("Target"))]
        w3 = write_step.get(3)
        if creates:
            c["F8a"] = 0.0 if any(obs.seen(t, before=w3) for t in creates) else 1.0
    if final is not None:
        new_tests = [p for p in final[1] if EV.is_test_file(norm_path(p), test_files) and not is_repro(p) and "/" in p and p.endswith(".py") and "/_build/" not in p]
        c["G4b"] = 0.0 if new_tests else 1.0
    if any(write_step.values()):
        # A stage's rule document read again after the stage's artifact was written: the run went back.
        reread = [step.n for step in run.steps for a in step.actions for d in F.doc_reads(a) if d != "core" and write_step.get(int(d)) is not None and step.n > write_step[int(d)]]
        c["C2"] = 0.0 if reread else 1.0

    # -- content --------------------------------------------------------------------------
    issue = task_text(task) if task is not None else ""
    if p1:
        files = claimed_paths(_field(p1, "Affected Scope", "Files"))
        # (a test file the issue quotes, e.g. in a test diff, is not the source scope to start from)
        # (an example or documentation file the issue shows the bug with is not the source to start from:
        # step24 000354 `examples/decomposition/plot_sparse_coding.py`)
        named = [
            p for p in dict.fromkeys(_ISSUE_PATH.findall(issue)) if norm_path(p) in known and not EV.is_test_file(norm_path(p), test_files) and not re.match(r"(?:examples?|docs?)/", norm_path(p))
        ]
        c["D1b"] = (1.0 if any(same_file(p, f) for p in named for f in files) else 0.0) if named else None
        # D3 (the owning module matches the files) is left to the judge: a name match is either too loose
        # (`django` passes any file) or too strict ("Django ORM", "matplotlib.widgets" for
        # lib/matplotlib/widgets.py fail), both seen on swebv100.
        exts = [f.rsplit(".", 1)[-1].lower() for f in files if "." in f.rsplit("/", 1)[-1]]
        langs = {_LANG[e] for e in exts if e in _LANG}
        lang = (_field(p1, "Affected Scope", "Language/framework") or "").lower()
        if langs and lang:
            c["D4a"] = float(any(re.search(rf"(?<![\w+]){re.escape(x)}(?![\w+])", lang) for x in langs))
        test = _field(p1, "Build & Test Commands", "Test")
        if test and not is_none(test) and (targets := EV.test_targets(test)) is not None:
            c["D7b"] = float(bool(targets))
    if p2:
        nfr = p2["section_bodies"].get("Non-Functional Requirements")
        if nfr is not None and issue:
            r_lines = R_LINE.findall(nfr)
            stated = [v for _, v in r_lines if not is_none(v)] if r_lines else [x for x in bullets(nfr) if not is_none(x)]
            c["E7b"] = 1.0 if not stated else (None if _PERF.search(issue) else 0.0)
        edge_ids = r_ids(p2["section_bodies"].get("Edge Cases & Error Handling"))
        real = [r for r in edge_ids if not any(rid == r and is_none(v) for rid, v in R_LINE.findall(p2["body"]))]
        exercises = r_ids(_field(p3, "Reproduction Script", "Exercises")) if p3 else []
        if real and p3:
            c["F4b"] = _frac([r in exercises for r in real])
        # E3a: one sentence per requirement, read with quotes, code spans and abbreviations masked
        reqs = [v for _, v in R_LINE.findall(p2["body"]) if not is_none(v)]
        masked = [_ABBREV.sub("x", re.sub(r"`[^`]*`|\"[^\"]*\"|'[^']*'", "x", v.strip())) for v in reqs]
        c["E3a"] = _frac([len([s for s in _SENTENCE.split(v) if s.strip()]) == 1 for v in masked])
    if steps and issue:
        # F3: an identifier the issue names in code that the plan and the patch never use as written but
        # use one edit apart (`refit_time` for `refit_time_`) -- a renamed name, not a different one.
        # (```fit``` inline fences read as one span; only code-like names: an underscore, a dot or camelCase)
        spans = re.findall(r"`([^`\n]+)`", re.sub(r"`{3,}", "`", issue))
        said = {t for span in spans for t in _IDENT.findall(span) if len(t) >= 6 and _CODE_LIKE.search(t)}
        added = "\n".join(line[1:] for line in (patch or "").splitlines() if line.startswith("+") and not line.startswith("+++"))
        used_text = p3["body"] + "\n" + added
        used = {part for t in _IDENT.findall(used_text) for part in (t, *t.split("."))}

        def as_written(t: str) -> bool:
            return re.search(rf"(?<!\w){re.escape(t)}(?!\w)", used_text) is not None

        kept = [t for t in said if as_written(t)]
        # A near name the issue also writes, or the code the run read defines, is the real name (an issue's
        # typo, swebv500 step24 000371: `strip_accent_unicode` for strip_accents_unicode), not a rename.
        read = issue + "\n" + "\n".join(obs.observations)
        renamed = [t for t in said if not as_written(t) and any(_near(t, u) and not re.search(rf"(?<!\w){re.escape(u)}(?!\w)", read) for u in used)]
        if kept or renamed:
            c["F3"] = 0.0 if renamed else 1.0
    if steps:
        # F9b: a planned new file goes under a directory the repository has (one the run read a file in or
        # named in a command), not a structure of its own
        planned = [norm_path(t) for s in steps if re.search(r"\(\s*create\s*\)", s["fields"].get("Target") or "", re.I) for t in claimed_paths(s["fields"].get("Target"))]
        dirs = [t.rsplit("/", 1)[0] for t in planned if "/" in t]
        read = {norm_path(p) for p in obs.viewed} | {norm_path(p) for p in obs.edited if p not in obs.new_files}
        c["F9b"] = _frac([any(k.startswith(d + "/") for k in read) or any(d in cmd for _, cmd, _ in obs.shell) for d in dirs])
    if p5:
        # H11: a reproduction that failed, or requirements left unmet, are outstanding failures
        result, unmet = (_field(p5, "Reproduction Script", "Result") or "").lower(), _field(p5, "Reproduction Script", "Unmet requirements")
        # (a run that never started -- "can't open file" -- is no result)
        last_runs = [r for r in (obs.ran(repro, after=obs.last_edit, before=w5) if repro and obs.last_edit is not None else []) if not EV._NOT_STARTED.search(r[2])]
        failed = result.startswith("fail") or bool(unmet and not is_none(unmet)) or (bool(last_runs) and EV.exit_code(last_runs[-1][1], last_runs[-1][2]) not in (None, 0))
        if failed and (outstanding := _section_none(p5, "Outstanding Failures")) is not None:
            c["H11"] = 0.0 if outstanding else 1.0

    # -- writing the artifacts ----------------------------------------------------------------
    # B3a: an artifact written once, whole (no append, no blank filled in later in its own stage); B4a: an
    # earlier stage's artifact never rewritten once a later stage began. A later stage begins with its first
    # sign after artifact k's first write: a later stage's document read, a later artifact written, a source
    # edit (after stages 1-3) or a test or reproduction run (after stage 4) -- not a document read ahead before
    # artifact k was written (that is A3b's concern).
    art_writes = {A.ARTIFACT_PATHS[p]: steps for p, steps in obs.writes.items() if p in A.ARTIFACT_PATHS and steps}
    if art_writes:
        doc_steps = [(s.n, int(d)) for s in run.steps for a in s.actions if a.acts for d in F.doc_reads(a) if d != "core"]
        edits = sorted(n for p in obs.source_edits for n in obs.edit_steps.get(p, []))

        def next_began(k: int) -> int | None:
            first = art_writes[k][0]
            signs = [n for n, d in doc_steps if d > k and n > first]
            signs += [w for j, w in write_step.items() if j > k and w is not None]
            signs += [n for n in edits if n > first] if k <= 3 else []
            if k == 4:
                signs += [n for n, _, _ in obs.tests_in(after=first)] + ([n for n, _, _ in obs.ran(repro, after=first)] if repro else [])
            return min(signs) if signs else None

        rewrites = [(k, n) for k, steps in art_writes.items() for n in steps[1:]]
        later = [(k, n) for k, n in rewrites if (b := next_began(k)) is not None and n > b]
        c["B4a"] = 0.0 if later else 1.0
        c["B3a"] = 0.0 if len(rewrites) > len(later) else 1.0

    # -- procedure and loops ----------------------------------------------------------------
    w1, w3 = write_step.get(1), write_step.get(3)
    if any(write_step.values()):
        # B8: an artifact read back after it was written (the same command's read-back too). The recipe runs
        # without history condensing, so what the run wrote is still in its context: no read recovers it.
        reread = False
        for step in run.steps:
            for a in step.actions:
                texts = [a.path or ""] if a.kind == "view" else [re.sub(r"\d?>>?\s*\S+", "", s) for s in _plain_segments(a.command or "") if _READ_VERB.match(s)] if a.kind == "shell" else []
                reread |= any(write_step.get(int(m.group(1))) is not None and step.n >= write_step[int(m.group(1))] for t in texts for m in _ARTIFACT.finditer(t))
        c["B8"] = 0.0 if reread else 1.0
    if run.steps:
        # (``final_words``: the run's last response and its finish message, ``evidence.final_words``)
        said_last = final_words if final_words is not None else run.steps[-1].message.strip()
        c["E10b"] = 0.0 if _ASK.search(said_last) or said_last.endswith("?") else 1.0
    if w3 is not None:
        # G3a: each file written whole in stage 4 inside the repository was looked for first: read, named
        # in a command, or its directory listed
        end4 = w4 if w4 is not None else w5
        made4 = [(p, n) for p, n in obs.created.items() if n > w3 and (end4 is None or n < end4) and not F.OUTSIDE_REPO_RE.match(p if p.startswith("/") else "/" + p) and not p.startswith("tmp/")]

        def looked(path: str, n: int) -> bool:
            base, parent = path.rsplit("/", 1)[-1], (path.rsplit("/", 1)[0] if "/" in path else "")
            if obs.seen(path, before=n - 1):
                return True
            for m, cmd, _ in obs.shell:
                if m >= n:
                    break
                # (a file at the repository root: its listing, not a find that searches the tree for something
                # else -- step24 000361's stage-1 `find /testbed -name "*.py" | xargs grep` looked for no file)
                listing = r"(?:ls|find|test|stat|\[)\b" if parent else r"(?:ls|test|stat|\[)\b"
                if base in cmd or any(re.match(listing, s) and (parent in s if parent else not re.search(r"\s/testbed/\S", s)) for s in _plain_segments(cmd)):
                    return True
            return False

        c["G3a"] = _frac([looked(p, n) for p, n in made4])
        # G1a: the plan's steps carried out in order (each step's first edit in stage 4, ties allowed)
        firsts = []
        for s in steps:
            hits = [m for t in claimed_paths(s["fields"].get("Target")) for q, ns in obs.edit_steps.items() if same_file(q, t) for m in ns if m > w3 and (end4 is None or m < end4)]
            if hits:
                firsts.append(min(hits))
        if len(firsts) >= 2:
            c["G1a"] = float(firsts == sorted(firsts))
    if w4 is not None and p1:
        # H1c: a stage-5 build that failed is followed by a source fix (or a passing build) before any
        # other verification runs
        # (the build stage 1 recorded, or stage 5's own when stage 1 had none to record; a test runner written
        # in the build field is no build -- swebv100 000034 recorded `runtests.py messages_tests` there)
        named = (_field(p1, "Build & Test Commands", "Build"), _field(p5, "Build", "Command"))
        build = next((b for b in named if b and not is_none(b) and EV.test_targets(b) is None and not (repro and EV.runs_script(b, norm_path(repro).rsplit("/", 1)[-1]))), None)
        builds = obs.command_runs(build, after=w4, before=w5) if build else []
        failed_at = next((n for n, cmd, out in builds if EV.exit_code(cmd, out) not in (None, 0)), None)
        if failed_at is not None:
            fixes = [m for p in obs.source_edits for m in obs.edit_steps.get(p, []) if m > failed_at]
            fixed = min(fixes + [n for n, cmd, out in builds if n > failed_at and EV.exit_code(cmd, out) == 0], default=None)
            checks = [n for n, _, _ in obs.tests_in(after=failed_at, before=w5)] + ([n for n, _, _ in obs.ran(repro, after=failed_at, before=w5)] if repro else [])
            c["H1c"] = float(not checks or (fixed is not None and fixed < min(checks)))
    # -- the execution side of rules the content checks hold as reports (E, beside their A items) -------
    if w1 is not None:
        # D10a: stage 1 looked for the tests that cover the scope -- read an existing test file or ran tests
        # before 01 was written (which tests the artifact names, and whether they were seen, is e1_test_path_seen's)
        new = obs.new_files
        read_tests = [p for p, n in obs.viewed.items() if n <= w1 and EV.is_test_file(norm_path(p), test_files) and p not in new]
        c["D10a"] = 1.0 if read_tests or obs.tests_in(before=w1) else 0.0
    if w4 is not None and p1:
        # H1b: stage 5 ran the build stage 1 recorded ("Run the build or type-check command Reverse Engineering
        # recorded"); whether it succeeded as 05 says is e5_build_result's. None recorded (`not applicable`), or an
        # install written in the build field (D9's to forbid, not a build to run), leaves it out.
        build = _field(p1, "Build & Test Commands", "Build")
        if build and not is_none(build) and command_core(build) and EV.test_targets(build) is None and not EV.is_env_setup(build):
            c["H1b"] = 1.0 if obs.command_runs(build, after=w4, before=w5) else 0.0
    if run.steps:
        # H10: no endless retry -- the same command with the same output three more times with nothing
        # written in between, or a run cut off (its last turn a tool call, no finish) after the plan with
        # stage 5 never closed
        written = sorted({m for ns in obs.edit_steps.values() for m in ns} | set(obs.created.values()) | {m for ns in obs.writes.values() for m in ns})
        seen_at: dict[tuple[str, str], int] = {}
        idle: dict[str, int] = {}
        for n, cmd, out in obs.shell:
            if (cmd, out) in seen_at and not any(seen_at[(cmd, out)] < m < n for m in written):
                idle[cmd] = idle.get(cmd, 0) + 1
            seen_at[(cmd, out)] = n
        last = run.steps[-1]
        cut = bool(last.actions) and not any(a.name == "finish" for a in last.actions)
        c["H10"] = 0.0 if max(idle.values(), default=0) >= 3 or (cut and w3 is not None and w5 is None) else 1.0
    before1 = w1 if w1 is not None else obs.first_edit
    if before1 is not None:
        # D4b: stage 1 does not survey the repository: tree / ls -R, or a find from the root that names
        # nothing and feeds no grep. One listing to get one's bearings is allowed; a second is a survey
        # (on swebv100 a single `find /testbed -name "*.py" | head -20` was 32 of 93 runs).
        surveys = sum(
            bool(re.match(r"(?:tree\b|ls\s+-[a-zA-Z]*R)", s) or (re.match(r"find\s+(?:\.|/testbed)/?(?:\s|$)", s) and not _NAME_FILTER.search(s) and not _GREP_FED.search(s)))
            for _, cmd, _ in obs.shell_in(before=before1)
            for s in _plain_segments(cmd)
        )
        c["D4b"] = 0.0 if surveys >= 2 else 1.0
    if p1:
        # D8: a pytest command reduces its output (-q, --tb=short ...); other runners have no common flag
        test = _field(p1, "Build & Test Commands", "Test") or ""
        if re.search(r"\bpytest\b", test):
            c["D8"] = 1.0 if _REDUCE.search(test) else 0.0
    if w4 is not None:
        # H7: from stage 5 on, no test run on stashed (or reverse-applied) source: that rebuilds the baseline
        # stage 1 established, which stage 5 must use as recorded. (Before stage 1 closed, a stash to measure
        # the baseline after an early edit is stage 1's own baseline; the early edit is D11's concern.)
        hidden, rebuilt, ran = False, False, False
        for n, cmd, _ in obs.shell:
            if n <= w4:
                continue
            for s in _plain_segments(cmd):
                if _UNSTASH.match(s):
                    hidden = False
                elif _STASH.match(s):
                    hidden = True
                elif EV.is_test_attempt(s):
                    ran = True
                    rebuilt |= hidden
        if ran:
            c["H7"] = 0.0 if rebuilt else 1.0

    # -- found by the independent rule extraction ------------------------------------------
    if p1:
        # D5b: Files lists one path per line (01 skeleton "[full paths from the repository root, one per line]")
        rows = _raw_rows(p1["section_bodies"].get("Affected Scope") or "", "Files")
        if any(claimed_paths(r) for r in rows):
            c["D5b"] = 0.0 if any(len(claimed_paths(r)) > 1 for r in rows) else 1.0
    if any(write_step.values()):
        # B11: each stage writes one artifact file (core "Each stage writes one artifact file"): nothing else in
        # the artifact directory but a script (the reproduction script may live there); documents elsewhere are B10's
        extra = [p for p in obs.created if p.startswith(A.ARTIFACT_DIR + "/") and p not in A.ARTIFACT_PATHS and not is_repro(p) and not re.search(r"\.(?:py|sh)$", p)]
        c["B11"] = 0.0 if extra else 1.0
    start4 = read_step.get("04") if read_step.get("04") is not None else w3
    if start4 is not None and w4 is not None:
        # G7c: stage 4 executes nothing it changed (04 "modify the source files in place and write the
        # reproduction script, executing neither yet"): no test attempt between the stage's start and its
        # artifact. Running the reproduction script there is G7b's (r_repro_not_in_stage4).
        c["G7c"] = 0.0 if obs.attempts_in(after=start4, before=w4) else 1.0
    if w4 is not None and w5 is not None:
        # H17: with nothing failed, stage 5 changes no source (05 "If the build succeeded and both Step 2 and
        # Step 3 passed, nothing has failed -- skip to Step 6"): a stage-5 source edit comes after some
        # stage-5 verification failed -- a test attempt with failures or a nonzero exit, the reproduction
        # script or the build exiting nonzero. (Once something failed, the fixes that follow are not judged.)
        edits5 = sorted(n for p in obs.source_edits for n in obs.edit_steps.get(p, []) if w4 < n < w5)

        def failed_before(n: int) -> bool:
            runs = obs.attempts_in(after=w4, before=n) + (obs.ran(repro, after=w4, before=n) if repro else [])
            build = _field(p1, "Build & Test Commands", "Build") if p1 else None
            if build and not is_none(build) and command_core(build):
                runs += obs.command_runs(build, after=w4, before=n)
            return any(failures(out) > 0 or EV.exit_code(cmd, out) not in (None, 0) for _, cmd, out in runs)

        c["H17"] = 0.0 if edits5 and not failed_before(edits5[0]) else 1.0
    if len(run.steps) > 1:
        # E10c: no approval asked before the end either (core "never ask for approval, never wait for input");
        # the last turn is E10b's
        c["E10c"] = 0.0 if any(_ASK_USER.search(s.message or "") for s in run.steps[:-1]) else 1.0
    return c
