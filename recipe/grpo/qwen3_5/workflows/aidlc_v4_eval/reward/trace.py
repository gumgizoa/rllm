"""How a trajectory becomes a :class:`Run`, and what its commands do -- no scoring here.

    model         ``Run`` / ``Step`` / ``Action``: the harness-independent view of a run
    front end     openhands-sdk tool calls -> actions (``parse_openhands``), rLLM episode -> ``Run``
                  (``episode_to_run``)
    commands      shell writes, document reads, test-run patterns, heredocs, artifact traces
                  (``trace_artifacts``) and diff files

Copied from the vendored rubric (legacy/rubric: ``model.py``, ``frontends/openhands.py``, ``facts.py``
without its ``analyse``) and ``episode.py``; the copies here move with this verifier, the legacy ones
stay byte-identical for the milestone-1 comparison.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Literal

from . import skeleton as A

Kind = Literal["shell", "view", "create", "replace", "insert", "undo", "other"]

Status = Literal["ok", "fail"] | None


@dataclass
class Action:
    """One tool call, reduced to what adherence scoring needs.

    kind   shell    `command` is a shell command line (may span lines, may hold heredocs)
           view     read `path`
           create   write `text` to `path` as the whole file
           replace  in `path`, replace `old` with `text`: the unique occurrence, or every
                    one when `replace_all` is set (opencode's `edit {replaceAll: true}`)
           insert   in `path`, insert `text` after 1-indexed line `line`
           undo     undo the last edit of `path` (counted as a write, not replayed)
           other    no effect on shell or file system (thinking, finishing, keystrokes ...)
    status what the tool itself reported: "ok", "fail", or None when its reply does not say.
    """

    kind: Kind
    name: str = ""
    command: str | None = None
    path: str | None = None
    text: str | None = None
    old: str | None = None
    replace_all: bool = False
    line: int | None = None
    status: Status = None
    observation: str = ""

    @property
    def acts(self) -> bool:
        return self.kind != "other"


@dataclass
class Step:
    """One assistant turn. `n` is 1-indexed; a turn with no acting tool call still counts.

    message is the agent's own text for the turn, with its tool calls excluded -- the channel the
    report-era rubric accepts a stage report on (see `reports.py`). A turn the harness discarded
    is left empty on both fields: nothing in it ran or was emitted.
    """

    n: int
    actions: list[Action] = field(default_factory=list)
    message: str = ""


@dataclass
class Run:
    """Everything the scorer knows about one instance.

    artifact_files  container path -> content of a stage artifact the harness collected from the
                    sandbox after the run (`/tmp/swe-bench-pro/NN-*.md`). When present it is the
                    ground truth for that stage's content; otherwise content is reconstructed from
                    the writes in `steps`.
    meta            harness-specific facts passed through to the facts record unchanged
                    (exit status, API calls, discarded turns ...).
    """

    instance_id: str
    steps: list[Step]
    patch: str = ""
    artifact_files: dict[str, str] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


OPENHANDS_NAMES = {"openhands-sdk", "openhands"}

_OK = re.compile(r"File created successfully|has been edited|has been inserted|Last edit to .* undone", re.I)

_FAIL = re.compile(
    r"File already exists|Invalid `path` parameter|Ran into .* while trying to write"
    r"|No replacement was performed|did not appear verbatim|Permission denied"
    r"|No such file or directory|is required for command",
    re.I,
)

_SHELL = {"terminal", "execute_bash", "bash", "shell"}

_EDITOR = {"file_editor", "str_replace_editor"}

_EDITOR_KIND = {"view": "view", "create": "create", "str_replace": "replace", "insert": "insert", "undo_edit": "undo"}


def _status(observation: str):
    return "ok" if _OK.search(observation) else "fail" if _FAIL.search(observation) else None


# The terminal refused the call: nothing in it ran (it reads two commands where one was meant).
_REJECTED = re.compile(r"^\s*(?:\[An error occurred during execution\.\]\s*)?Cannot execute multiple commands at once")


def parse_openhands(name: str, args: dict, observation: str) -> Action:
    if name in _SHELL:
        cmd = args.get("command")
        if args.get("is_input") or not isinstance(cmd, str) or not cmd.strip() or _REJECTED.match(observation or ""):
            return Action("other", name, observation=observation)
        return Action("shell", name, command=cmd, observation=observation)
    if name in _EDITOR and args.get("path") and args.get("command") in _EDITOR_KIND:
        kind = _EDITOR_KIND[args["command"]]
        act = Action(kind, name, path=args["path"], observation=observation)
        if kind != "view":
            act.status = _status(observation)
        if kind == "create":
            act.text = args.get("file_text") if isinstance(args.get("file_text"), str) else ""
        elif kind in ("replace", "insert"):
            act.text = args.get("new_str") or ""
            act.old = args.get("old_str") or ""
            try:
                act.line = int(args.get("insert_line") or 0)
            except (TypeError, ValueError):
                act.line = 0
        return act
    # `think` is where this agent puts the text other harnesses put in the assistant message, so
    # it carries the prose channel the report-era rubric reads; keep the thought, act on nothing.
    if name == "think":
        return Action("other", name, text=args.get("thought") or "", observation=observation)
    return Action("other", name, observation=observation)


# Vendored tool profiles, each naming the harnesses whose tool calls it parses (``NAMES``).
FRONTENDS = (SimpleNamespace(NAMES=OPENHANDS_NAMES, parse=parse_openhands),)


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and isinstance(p.get("text"), str))
    return ""


def _args(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {"command": raw}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _steps(episode: Any) -> list[Any]:
    return [s for traj in episode.trajectories for s in traj.steps]


def _tool_results(steps: list[Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for s in steps:
        for m in (s.chat_completions or [])[:-1]:
            if m.get("role") == "tool" and m.get("tool_call_id"):
                out.setdefault(m["tool_call_id"], _text(m.get("content")))
    return out


def frontend_for(episode: Any):
    """The tool profile for the harness that produced ``episode``, by its trajectories' ``name``.

    A tool call means something only to its own harness's profile (openhands' ``terminal`` /
    ``file_editor`` are not another agent's tools), so a harness without one is an error -- the
    scorer logs it and leaves the verifier's output alone -- never a score from the wrong parser.
    """
    names = {getattr(t, "name", None) for t in episode.trajectories}
    for frontend in FRONTENDS:
        if names & frontend.NAMES:
            return frontend
    vendored = sorted(n for frontend in FRONTENDS for n in frontend.NAMES)
    raise ValueError(f"no rubric front end for harness {sorted(map(str, names))}; vendored: {vendored}")


def episode_to_run(episode: Any, artifact_files: dict[str, str], instance_id: str = "") -> Run:
    """``artifact_files`` maps ``/tmp/swe-bench-pro/NN-*.md`` to the content read from the sandbox."""
    parse = frontend_for(episode).parse
    steps = _steps(episode)
    results = _tool_results(steps)
    run_steps: list[Step] = []
    for i, s in enumerate(steps, start=1):
        response = (s.chat_completions or [{}])[-1] or {}
        step = Step(i, message=_text(response.get("content")))
        for tc in response.get("tool_calls") or []:
            fn = tc.get("function") or {}
            step.actions.append(parse(fn.get("name") or "", _args(fn.get("arguments")), results.get(tc.get("id") or "", "")))
        run_steps.append(step)
    return Run(instance_id=instance_id, steps=run_steps, artifact_files=dict(artifact_files), meta={"api_calls": len(steps)})


STAGE_DOCS = ["01-reverse-engineering", "02-requirements-analysis", "03-code-generation-planning", "04-code-generation-generation", "05-build-and-test"]

# Where harnesses mount the workflow documents -> the one root the facts use.
DOC_PATH_REWRITES = [
    (re.compile(r"/app/AGENTS\.md\b"), "/aidlc/core-workflow.md"),  # core bind-mounted as AGENTS.md
    (re.compile(r"/app/ai-dlc(?=/|\b)"), "/aidlc"),
    (re.compile(r"(?<![\w/])/ai-dlc(?=/|\b)"), "/aidlc"),
    (re.compile(r"(?<![\w/.-])ai-dlc(?=/)"), "/aidlc"),  # relative form from cwd /app
]

# Shell commands that write to disk. Heuristic; the harness offers no per-step `git status`.
WRITE_PATTERNS = [
    r"\bsed\s+-i\b",
    r"\bcat\s*<<.*>\s*\S",
    r"\btee\b",
    r"\bpatch\s+-",
    r"\bcp\b\s+\S+\s+\S+",
    r"\bmv\b\s+\S+\s+\S+",
    # A python heredoc whose body actually opens a file for writing.
    r"(?s)\bpython[0-9.]*\s+(?:-\s+)?<<.*?"
    r"(?:open\s*\(\s*['\"][^'\"]+['\"]\s*,\s*['\"][wax]|\.write_text\s*\(|\.writelines\s*\("
    r"|\bshutil\.(?:copy|copyfile|copy2|move)\s*\(|\bos\.(?:rename|replace|remove|unlink)\s*\()",
    r">>?\s*/?(?!dev/null)\S+\.(py|js|ts|go|json|yaml|yml|md|txt|sh)\b",
    r"\bapply_patch\b",
    r"\btruncate\b",
    r"\brm\b\s",
    # Whole-patch writes: `git apply`, `patch -p1`, and `git checkout <rev> -- <path>`, which
    # rewrites the working tree from history. All three change the repo without naming a target.
    r"\bgit\s+apply\b",
    r"\bpatch\s+-p\d",
    r"\bgit\s+(?:checkout|restore)\s+\S+\s+--\s+\S",
]

# Reaching into git history for commits the task did not hand over. The SWE-bench Pro images
# keep the FIX commit and its cherry-picks in the object store and on refs, so `git log --all`
# lists the solution and `git show <hash>` prints it. A run that does this and then scores 1 did
# not solve the task; the reward must be able to tell.
GIT_HISTORY_RE = re.compile(
    r"\bgit\s+(?:log|rev-list|branch|for-each-ref)\b[^|;&\n]*(?:--all|--branches|--remotes|--tags|\s-a\b)"
    r"|\bgit\s+(?:reflog|fsck|cat-file|name-rev)\b"
    r"|\bgit\s+(?:show|diff|checkout|cherry-pick|restore|revert|format-patch)\b[^|;&\n]*\b[0-9a-f]{7,40}\b"
)

TEST_RUN_PATTERNS = [
    r"\bpytest\b",
    r"\bgo\s+test\b",
    r"\bnpm\s+(run\s+)?test\b",
    r"\bnpx\s+jest\b",
    r"\byarn\s+test\b",
    r"\bjest\b",
    r"\bmocha\b",
    r"\bunittest\b",
    r"\btox\b",
    r"\bmake\s+test\b",
    r"\bgotestsum\b",
    r"\bginkgo\b",
    r"\bansible-test\s+(units|integration|sanity)\b",
    r"\bvitest\b",
    r"\bcargo\s+test\b",
    r"\bpnpm\s+(run\s+)?test\b",
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

SCRATCH_HINT_RE = re.compile(r"(^|/)(reproduce|repro|final_test|test_fix|verify|scratch|tmp|temp|debug|check|sample|demo)[^/]*$", re.I)

ARTIFACT_RE = re.compile(
    r"\.(rdb|db|sqlite3?|log|pid|sock|lock|pyc|pyo|class|o|so|dylib|dll|exe|zip|tar|gz|tgz|jar"
    r"|coverage|prof|heapsnapshot|core)$|(^|/)(dump\.rdb|npm-debug\.log|yarn-error\.log|core)$"
    r"|(^|/)(node_modules|__pycache__|\.pytest_cache|\.mypy_cache|coverage|dist|build)/",
    re.I,
)

BACKUP_RE = re.compile(r"(\.(bak|backup|orig|rej|old|save|copy|swp|dup)$|~$|\.(bak|backup|orig|old)\.[a-z0-9]+$)", re.I)

# Outside the repository: scratch in /tmp is compliant, and the workflow documents (normalised to
# /aidlc) are read-only input, so writes there are never "modified the source".
OUTSIDE_REPO_RE = re.compile(r"^(/tmp/|/var/tmp/|/dev/|/proc/|/sys/|/root/|/etc/|/usr/|~/|/aidlc/)")

SCRIPT_EXT_RE = re.compile(r"\.(py|js|mjs|cjs|ts|tsx|go|sh|rb|java|pl)$", re.I)

DOCLIKE_RE = re.compile(r"\.(txt|md|patch|diff|rst)$|(^|/)[^/]*(plan|summary|report|notes)[^/]*$", re.I)

RUNNER = r"(?:python[0-9.]*|node|ts-node|npx\s+ts-node|go\s+run|bash|sh|zsh|ruby|perl|java)"


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
        return True  # a shell write whose target could not be parsed; assume the repo
    return any(not OUTSIDE_REPO_RE.match(t) for t in targets)


def probes_git_history(a: Action) -> bool:
    return a.kind == "shell" and GIT_HISTORY_RE.search(command_skeleton(a.command or "")) is not None


def ran_something(a: Action) -> bool:
    """A test attempt whose output does not say the tool was missing or ran nothing."""
    return not TOOL_MISSING_RE.search(a.observation or "")


@dataclass
class ArtifactTrace:
    """What happened to one stage's artifact file over the run.

    content is the FINAL state -- what a reader of the sandbox would find -- reconstructed by
    replaying whole-file writes and editor edits, or taken from the file the harness collected.
    """

    step: int | None = None  # first successful write
    content: str | None = None
    writes: int = 0
    failed_writes: list[int] = field(default_factory=list)
    unparsed: bool = False  # a shell write happened whose text could not be recovered
    deleted: bool = False  # an existing artifact was removed and not written again
    source: str | None = None  # "trajectory" | "file"

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
    for path, content in run.artifact_files.items():  # the collected file is the truth
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
    return content  # undo: not modelled


def diff_files(patch: str) -> tuple[list[str], list[str]]:
    """Paths a unified diff touches, and which of them are newly added (binary adds included)."""
    touched = [b for _, b in re.findall(r"^diff --git a/(\S+) b/(\S+)", patch, re.M)]
    added = set(re.findall(r"^\+\+\+ b/(\S+)", patch, re.M)) - set(re.findall(r"^--- a/(\S+)", patch, re.M))
    for block in re.split(r"^diff --git ", patch, flags=re.M)[1:]:
        m = re.match(r"a/(\S+) b/(\S+)", block)
        if m and re.search(r"^new file mode ", block, re.M):
            added.add(m.group(2))
    return touched, sorted(added)
