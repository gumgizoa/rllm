"""Run -> deterministic adherence facts (facts_v2.json records).

Nothing here scores. It records what mechanically happened -- which workflow documents were read
and in what order, what was written where, which test commands actually ran, what the artifacts
ended up containing, what the final diff touched -- so that the scoring profile (score.py) is a
pure function of a small, inspectable record and stays stable across harnesses and iterations.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from . import artifacts as A, reports as R
from .model import Action, Run

STAGE_DOCS = ["01-reverse-engineering", "02-requirements-analysis",
              "03-code-generation-planning", "04-code-generation-generation",
              "05-build-and-test"]

# Where harnesses mount the workflow documents -> the one root the facts use.
DOC_PATH_REWRITES = [
    (re.compile(r"/app/AGENTS\.md\b"), "/aidlc/core-workflow.md"),   # core bind-mounted as AGENTS.md
    (re.compile(r"/app/ai-dlc(?=/|\b)"), "/aidlc"),
    (re.compile(r"(?<![\w/])/ai-dlc(?=/|\b)"), "/aidlc"),
    (re.compile(r"(?<![\w/.-])ai-dlc(?=/)"), "/aidlc"),               # relative form from cwd /app
]

# Shell commands that write to disk. Heuristic; the harness offers no per-step `git status`.
WRITE_PATTERNS = [
    r"\bsed\s+-i\b", r"\bcat\s*<<.*>\s*\S", r"\btee\b", r"\bpatch\s+-",
    r"\bcp\b\s+\S+\s+\S+", r"\bmv\b\s+\S+\s+\S+",
    # A python heredoc whose body actually opens a file for writing.
    r"(?s)\bpython[0-9.]*\s+(?:-\s+)?<<.*?"
    r"(?:open\s*\(\s*['\"][^'\"]+['\"]\s*,\s*['\"][wax]|\.write_text\s*\(|\.writelines\s*\("
    r"|\bshutil\.(?:copy|copyfile|copy2|move)\s*\(|\bos\.(?:rename|replace|remove|unlink)\s*\()",
    r">>?\s*/?(?!dev/null)\S+\.(py|js|ts|go|json|yaml|yml|md|txt|sh)\b",
    r"\bapply_patch\b", r"\btruncate\b", r"\brm\b\s",
    # Whole-patch writes: `git apply`, `patch -p1`, and `git checkout <rev> -- <path>`, which
    # rewrites the working tree from history. All three change the repo without naming a target.
    r"\bgit\s+apply\b", r"\bpatch\s+-p\d", r"\bgit\s+(?:checkout|restore)\s+\S+\s+--\s+\S",
]
# Reaching into git history for commits the task did not hand over. The SWE-bench Pro images
# keep the FIX commit and its cherry-picks in the object store and on refs, so `git log --all`
# lists the solution and `git show <hash>` prints it. A run that does this and then scores 1 did
# not solve the task; the reward must be able to tell.
GIT_HISTORY_RE = re.compile(
    r"\bgit\s+(?:log|rev-list|branch|for-each-ref)\b[^|;&\n]*(?:--all|--branches|--remotes|--tags|\s-a\b)"
    r"|\bgit\s+(?:reflog|fsck|cat-file|name-rev)\b"
    r"|\bgit\s+(?:show|diff|checkout|cherry-pick|restore|revert|format-patch)\b[^|;&\n]*\b[0-9a-f]{7,40}\b")
TEST_RUN_PATTERNS = [
    r"\bpytest\b", r"\bgo\s+test\b", r"\bnpm\s+(run\s+)?test\b", r"\bnpx\s+jest\b",
    r"\byarn\s+test\b", r"\bjest\b", r"\bmocha\b", r"\bunittest\b", r"\btox\b",
    r"\bmake\s+test\b", r"\bgotestsum\b",
    r"\bginkgo\b", r"\bansible-test\s+(units|integration|sanity)\b", r"\bvitest\b",
    r"\bcargo\s+test\b", r"\bpnpm\s+(run\s+)?test\b",
]
# The runner was missing or ran nothing: such an attempt observed no baseline. `0 passing` is
# word-bounded so `10 passing` does not match; a bare `No such file or directory` is not here
# because real test output prints it whenever a test exercises a missing file.
TOOL_MISSING_RE = re.compile(
    r"command not found|<returncode>127</returncode>|\bError 127\b|is not recognized as"
    r"|ModuleNotFoundError: No module named 'pytest'|No module named pytest"
    r"|executable file not found"
    r"|ECONNREFUSED|ECONNRESET|Connection refused|could not connect"
    r"|\b0 passing\b|no tests? (?:ran|found|to run|were run)|collected 0 items"
    r"|ERROR collecting|INTERNALERROR",
    re.I,
)
TEST_PATH_RE = re.compile(r"(^|/)(tests?|__tests__|spec)/|[-_.](test|spec)\.[a-z]+$|(^|/)test[-_][^/]+$")
SCRATCH_HINT_RE = re.compile(
    r"(^|/)(reproduce|repro|final_test|test_fix|verify|scratch|tmp|temp|debug|check|sample|demo)[^/]*$",
    re.I)
ARTIFACT_RE = re.compile(
    r"\.(rdb|db|sqlite3?|log|pid|sock|lock|pyc|pyo|class|o|so|dylib|dll|exe|zip|tar|gz|tgz|jar"
    r"|coverage|prof|heapsnapshot|core)$|(^|/)(dump\.rdb|npm-debug\.log|yarn-error\.log|core)$"
    r"|(^|/)(node_modules|__pycache__|\.pytest_cache|\.mypy_cache|coverage|dist|build)/", re.I)
BACKUP_RE = re.compile(
    r"(\.(bak|backup|orig|rej|old|save|copy|swp|dup)$|~$|\.(bak|backup|orig|old)\.[a-z0-9]+$)", re.I)
# Outside the repository: scratch in /tmp is compliant, and the workflow documents (normalised to
# /aidlc) are read-only input, so writes there are never "modified the source".
OUTSIDE_REPO_RE = re.compile(r"^(/tmp/|/var/tmp/|/dev/|/proc/|/sys/|/root/|/etc/|/usr/|~/|/aidlc/)")
SCRIPT_EXT_RE = re.compile(r"\.(py|js|mjs|cjs|ts|tsx|go|sh|rb|java|pl)$", re.I)
DOCLIKE_RE = re.compile(r"\.(txt|md|patch|diff|rst)$|(^|/)[^/]*(plan|summary|report|notes)[^/]*$", re.I)
RUNNER = r"(?:python[0-9.]*|node|ts-node|npx\s+ts-node|go\s+run|bash|sh|zsh|ruby|perl|java)"


# --- shell text helpers -------------------------------------------------------------------

def matches_any(text: str, patterns) -> bool:
    return any(re.search(p, text) for p in patterns)


def drop_heredoc_bodies(command: str) -> str:
    """The command with heredoc bodies blanked: an artifact that quotes a document or a test
    command inside its body must not read as having opened or run it."""
    out, pos = [], 0
    for _, _, (start, stop) in A.heredocs(command):
        if start >= pos:
            out.append(command[pos:start])
            pos = stop
    out.append(command[pos:])
    return " ".join(out)


def command_skeleton(command: str) -> str:
    """Only what can execute: heredoc bodies and quoted strings removed. `echo "pytest ..."`
    is a report about a test run, not a test run."""
    sk = drop_heredoc_bodies(command)
    sk = re.sub(r"'[^']*'", " ", sk)
    return re.sub(r'"[^"]*"', " ", sk)


def normalise_doc_paths(text: str) -> str:
    for rx, rep in DOC_PATH_REWRITES:
        text = rx.sub(rep, text)
    return text


# --- what one action does -----------------------------------------------------------------

# Shell verbs that touch a path without reading its content. A segment led by one of these
# (`rm /app/ai-dlc/...`, `ls -la .../01-...md`, `chmod ...`) names a document but is not a read.
_NON_READ_VERB = re.compile(r"^\s*(?:cd\s+\S+\s*)?(?:sudo\s+)?(?:rm|ls|stat|test|\[|touch|chmod|chown|mkdir|du|file|realpath|readlink|wc)\b")


def doc_reads(a: Action) -> list[str]:
    """Workflow documents this action opened: "core" and/or "01".."05"."""
    if a.kind == "shell":
        segments = re.split(r"\s*(?:&&|\|\||;|\|)\s*", drop_heredoc_bodies(a.command or ""))
        text = " ".join(normalise_doc_paths(s) for s in segments if not _NON_READ_VERB.match(s))
    elif a.kind == "view":
        text = normalise_doc_paths(a.path or "")
    else:
        return []
    if "/aidlc" not in text:
        return []
    out = ["core"] if "core-workflow" in text else []
    return out + [d[:2] for d in STAGE_DOCS if d in text]


def write_targets(a: Action) -> list[str]:
    """Paths this action writes to (best effort for shell)."""
    if a.kind in ("create", "replace", "insert", "undo"):
        return [normalise_doc_paths(a.path or "")]
    if a.kind != "shell":
        return []
    c = a.command or ""
    found = re.findall(r">>?\s*([^\s|&;<>]+)", c)
    found += re.findall(r"\|\s*tee\s+(?:-a\s+)?([^\s|&;]+)", c)
    found += re.findall(r"\bsed\s+-i[^\s]*\s+(?:-e\s+\S+\s+)?(?:'[^']*'|\"[^\"]*\"|\S+)\s+([^\s|&;]+)", c)
    found += re.findall(r"\b(?:cp|mv)\s+\S+\s+([^\s|&;]+)", c)
    found += re.findall(r"\brm\s+(?:-\w+\s+)*([^\s|&;]+)", c)
    found += re.findall(r"\bapply_patch\s+([^\s|&;]+)", c)
    found += re.findall(r"open\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"][wax]", c)
    found += re.findall(r"Path\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\.write_text", c)
    found += re.findall(r"\bshutil\.(?:copy|copyfile|copy2|move)\s*\([^,]+,\s*['\"]([^'\"]+)['\"]", c)
    return [normalise_doc_paths(t.strip("'\"")) for t in found]


def is_write(a: Action) -> bool:
    if a.kind == "shell":
        return matches_any(a.command or "", WRITE_PATTERNS)
    return a.kind in ("create", "replace", "insert", "undo")


def is_repo_write(a: Action) -> bool:
    if not is_write(a):
        return False
    targets = write_targets(a)
    if not targets:
        return True     # a shell write whose target could not be parsed; assume the repo
    return any(not OUTSIDE_REPO_RE.match(t) for t in targets)


def is_test_attempt(a: Action) -> bool:
    return a.kind == "shell" and matches_any(command_skeleton(a.command or ""), TEST_RUN_PATTERNS)


def probes_git_history(a: Action) -> bool:
    return a.kind == "shell" and GIT_HISTORY_RE.search(command_skeleton(a.command or "")) is not None


def ran_something(a: Action) -> bool:
    """A test attempt whose output does not say the tool was missing or ran nothing."""
    return not TOOL_MISSING_RE.search(a.observation or "")


# --- artifact traces ----------------------------------------------------------------------

@dataclass
class ArtifactTrace:
    """What happened to one stage's artifact file over the run.

    content is the FINAL state -- what a reader of the sandbox would find -- reconstructed by
    replaying whole-file writes and editor edits, or taken from the file the harness collected.
    """

    step: int | None = None             # first successful write
    content: str | None = None
    writes: int = 0
    failed_writes: list[int] = field(default_factory=list)
    unparsed: bool = False              # a shell write happened whose text could not be recovered
    deleted: bool = False               # an existing artifact was removed and not written again
    source: str | None = None           # "trajectory" | "file"

    def delete(self) -> None:
        if self.content is not None:
            self.content, self.deleted = None, True


def _rm_matches(command: str, path: str) -> bool:
    return re.search(rf"\brm\b[^|;&\n]*{re.escape(path)}(?:\s|$)", command) is not None


def trace_artifacts(run: Run) -> dict[int, ArtifactTrace]:
    traces = {st: ArtifactTrace() for st in A.STAGE_FILES}
    for step in run.steps:
        for a in step.actions:
            if a.kind == "shell":
                cmd = a.command or ""
                if _rm_matches(cmd, A.ARTIFACT_DIR) or _rm_matches(cmd, A.ARTIFACT_DIR + "/"):
                    for t in traces.values():
                        t.delete()
                targets = write_targets(a)
                for path, st in A.ARTIFACT_PATHS.items():
                    if _rm_matches(cmd, path):
                        traces[st].delete()
                    elif path in targets:
                        _record_write(traces[st], step.n, a, A.shell_written_body(cmd, path))
                continue
            st = A.ARTIFACT_PATHS.get(a.path or "")
            if st is None:
                continue
            t = traces[st]
            if a.kind == "create":
                _record_write(t, step.n, a, a.text or "")
            elif a.kind in ("replace", "insert", "undo"):
                t.writes += 1
                if a.status == "fail":
                    t.failed_writes.append(step.n)
                elif a.status == "ok" and t.content is not None:
                    t.content = _apply_edit(t.content, a)
    for path, content in run.artifact_files.items():      # the collected file is the truth
        st = A.ARTIFACT_PATHS.get(path)
        if st is None:
            continue
        t = traces[st]
        t.content, t.source, t.unparsed, t.deleted = content, "file", False, False
        if t.step is None:
            t.step = run.steps[-1].n if run.steps else None
    return traces


def _record_write(t: ArtifactTrace, n: int, a: Action, body: str | None) -> None:
    t.writes += 1
    if a.status == "fail":
        t.failed_writes.append(n)
    elif body is None:
        # The file changed and nobody knows into what: any earlier content is stale now. Dropping
        # it makes the stage a reported measurement gap (rubric 3.2) rather than a confident grade
        # of text the file no longer holds. A collected file, if any, restores certainty later.
        t.unparsed, t.content, t.source = True, None, None
    else:
        t.content, t.source, t.deleted = body, "trajectory", False
        if t.step is None:
            t.step = n


def _apply_edit(content: str, a: Action) -> str:
    if a.kind == "replace":
        if not a.old:
            return content
        # Editors refuse an ambiguous match unless asked to replace every occurrence.
        if a.replace_all or content.count(a.old) == 1:
            return content.replace(a.old, a.text or "")
        return content
    if a.kind == "insert":
        lines = content.split("\n")
        n = max(0, min(len(lines), a.line or 0))
        lines[n:n] = (a.text or "").split("\n")
        return "\n".join(lines)
    return content                                   # undo: not modelled


# --- diff --------------------------------------------------------------------------------

def diff_files(patch: str) -> tuple[list[str], list[str]]:
    """Paths a unified diff touches, and which of them are newly added (binary adds included)."""
    touched = [b for _, b in re.findall(r"^diff --git a/(\S+) b/(\S+)", patch, re.M)]
    added = set(re.findall(r"^\+\+\+ b/(\S+)", patch, re.M)) - set(
        re.findall(r"^--- a/(\S+)", patch, re.M))
    for block in re.split(r"^diff --git ", patch, flags=re.M)[1:]:
        m = re.match(r"a/(\S+) b/(\S+)", block)
        if m and re.search(r"^new file mode ", block, re.M):
            added.add(m.group(2))
    return touched, sorted(added)


# --- the record ---------------------------------------------------------------------------

def analyse(run: Run) -> dict:
    acts = [(s.n, a) for s in run.steps for a in s.actions if a.acts]
    shell = [(n, a) for n, a in acts if a.kind == "shell"]

    reads = [{"step": n, "doc": d} for n, a in acts for d in doc_reads(a)]
    read_step: dict[str, int] = {}
    for r in reads:
        read_step.setdefault(r["doc"], r["step"])

    attempts = [(n, a) for n, a in shell if is_test_attempt(a)]
    test_attempt_steps = sorted({n for n, _ in attempts})
    test_run_steps = sorted({n for n, a in attempts if ran_something(a)})
    first_test_run = test_run_steps[0] if test_run_steps else None

    first_write = next((n for n, a in acts if is_write(a)), None)
    repo_writes = [n for n, a in acts if is_repo_write(a)]
    first_repo_write = repo_writes[0] if repo_writes else None
    last_repo_write = repo_writes[-1] if repo_writes else None

    touched, added = diff_files(run.patch)
    scratch = sorted({t for n, a in acts if is_write(a) for t in write_targets(a)
                      if OUTSIDE_REPO_RE.match(t) and "/dev/null" not in t})
    repro_candidates = [p for p in scratch if SCRIPT_EXT_RE.search(p)] + [
        p for p in added if SCRIPT_EXT_RE.search(p)]
    repro_exec = sorted({n for n, a in shell if any(
        re.search(rf"\b{RUNNER}\s+(?:-\S+\s+)*{re.escape(p)}(?:\s|$)", command_skeleton(a.command))
        for p in repro_candidates)})

    traces = trace_artifacts(run)
    graded = {st: A.grade(st, A.parse(st, t.content) if t.content is not None else None)
              for st, t in traces.items()}
    parsed4 = A.parse(4, traces[4].content) if traces[4].content is not None else None
    a4_claimed, a4_phantom, a4_undisclosed, a4_ratio = [], [], [], None
    if parsed4 is not None:
        a4_claimed = sorted(set(parsed4["claims"]["modified"] + parsed4["claims"]["created"]))
        basenames = {p.rsplit("/", 1)[-1] for p in touched}
        # Asymmetric on purpose: a phantom claim is judged on the two claim labels only, an
        # undisclosed file against the whole artifact body.
        a4_phantom = [p for p in a4_claimed
                      if p.rsplit("/", 1)[-1] not in basenames and not p.startswith("/tmp")]
        a4_undisclosed = [p for p in touched if p.rsplit("/", 1)[-1] not in parsed4["body"]]
        a4_ratio = None if not touched else 1 - len(a4_undisclosed) / len(touched)

    repeats = Counter(re.sub(r"\s+", " ", a.command or "") for _, a in shell)
    per_stage = lambda f: {str(st): f(st) for st in traces}  # noqa: E731
    nonempty = lambda d: {k: v for k, v in d.items() if v}  # noqa: E731

    return {
        "instance_id": run.instance_id,
        "n_steps": len(run.steps),
        **run.meta,
        # workflow documents
        "aidlc_reads_in_order": [r["doc"] for r in reads],
        "aidlc_read_step": read_step,
        "stage_docs_read": sorted(d for d in read_step if d != "core"),
        # tests
        "first_test_run_step": first_test_run,
        "test_run_steps": test_run_steps,
        "test_attempt_steps": test_attempt_steps,
        "test_runs_failed_to_start": [n for n in test_attempt_steps if n not in test_run_steps],
        "ran_real_test_suite": bool(test_run_steps),
        # writes and ordering
        "first_write_step": first_write,
        "first_repo_write_step": first_repo_write,
        "last_repo_write_step": last_repo_write,
        "baseline_before_first_write": (
            None if first_test_run is None or first_repo_write is None
            else first_test_run < first_repo_write),
        "regression_rerun_after_last_write": (
            None if last_repo_write is None else any(n > last_repo_write for n in test_run_steps)),
        # reproduction script: written in stage 4, run in stage 5
        "repro_script_candidates": repro_candidates,
        "repro_executed_steps": repro_exec,
        "repro_executed_after_stage4": bool(
            repro_exec and traces[4].step and max(repro_exec) > traces[4].step),
        # scratch outside the repository
        "scratch_files_outside_repo": scratch,
        "scratch_scripts_outside_repo": [p for p in scratch if SCRIPT_EXT_RE.search(p)],
        "scratch_docs_outside_repo": [p for p in scratch if DOCLIKE_RE.search(p)
                                      and not SCRIPT_EXT_RE.search(p)
                                      and not p.startswith(A.ARTIFACT_DIR + "/")],
        "backup_files_outside_repo": [p for p in scratch if BACKUP_RE.search(p)],
        # solution leakage: history browsing and whole-patch application
        "git_history_probe_steps": sorted({n for n, a in shell if probes_git_history(a)}),
        "git_apply_steps": sorted({n for n, a in shell
                                   if re.search(r"\bgit\s+apply\b|\bpatch\s+-p\d", command_skeleton(a.command or ""))}),
        # diff hygiene
        "patch_empty": not run.patch.strip(),
        "diff_files": touched,
        "diff_files_added": added,
        "diff_test_files": [p for p in touched if TEST_PATH_RE.search(p)],
        "diff_backup_files": [p for p in touched if BACKUP_RE.search(p)],
        "diff_scratch_suspects": sorted({p for p in added if SCRATCH_HINT_RE.search(p)
                                         or BACKUP_RE.search(p) or ARTIFACT_RE.search(p)}),
        "diff_artifact_files": [p for p in touched if ARTIFACT_RE.search(p)],
        # stage reports (report-era workflow: the stage's result is PRINTED). Extracted
        # for every run alongside the artifact keys below, so which era a run belongs to
        # is visible from which set is populated.
        **R.trace(run),
        # stage artifacts (artifact-era workflow: the stage's result is a FILE)
        "stage_artifact_step": per_stage(lambda st: traces[st].step),
        "stage_artifact_source": per_stage(lambda st: traces[st].source),
        "stage_artifacts_missing": [st for st, t in traces.items() if t.content is None],
        # Written, then removed by the agent and never rewritten: the file a reader of the sandbox
        # would find is gone, so the stage grades as missing. Listed so that is never mistaken for
        # "never written".
        "stage_artifact_deleted": [st for st, t in traces.items() if t.deleted],
        "stage_artifact_band": per_stage(lambda st: graded[st]["points"]),
        "stage_artifact_missing_fields": nonempty(per_stage(lambda st: graded[st]["missing"])),
        "stage_artifact_frontmatter_valid": per_stage(lambda st: graded[st]["frontmatter_valid"]),
        "stage_artifact_fenced": [st for st in traces if graded[st]["fenced"]],
        "stage_artifact_near_misses": nonempty(per_stage(lambda st: graded[st]["near_misses"])),
        "stage_artifact_unknown_sections": nonempty(per_stage(lambda st: graded[st]["unknown_sections"])),
        "stage_artifact_write_unparsed": [st for st, t in traces.items()
                                          if t.unparsed and t.content is None],
        "stage_artifact_failed_writes": nonempty(per_stage(lambda st: traces[st].failed_writes)),
        "stage_artifact_rewrites": nonempty(per_stage(lambda st: max(0, traces[st].writes - 1))),
        # stage 4 vs the diff
        "a4_claimed_files": a4_claimed,
        "a4_phantom_files": a4_phantom,
        "a4_undisclosed_files": a4_undisclosed,
        "a4_disclosed_ratio": a4_ratio,
        # shape of the run
        "steps_without_action": sum(1 for s in run.steps if not any(a.acts for a in s.actions)),
        "max_identical_command_repeats": max(repeats.values()) if repeats else 0,
        "top_repeated_commands": [{"count": n, "command": c[:120]}
                                  for c, n in repeats.most_common(3) if n > 1],
    }
