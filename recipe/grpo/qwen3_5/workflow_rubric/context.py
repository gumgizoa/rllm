"""The data the checks read: what the sandbox held (:class:`Collected`), what the trace shows
(:class:`Facts`), and per-item results (:class:`Result`).

Everything here is plain data. ``collect.py`` fills :class:`Collected`; ``facts.py`` fills
:class:`Facts` from a ``trace.model.Run``, the :class:`Collected` and the rubric; checks
(``checks/``) read both through :class:`EvalContext` and never touch the sandbox or the episode.

Steps are 1-indexed LLM calls (``Run.steps[i].n``). An event that did not happen is ``None``;
an event that happened at an unknown time (a repo edit the trace does not show but the diff does)
is :data:`UNKNOWN`, which compares as *earlier than every step* so "before X" checks fail safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .schema import Item, Rubric
    from .trace.model import Run


class _Unknown(int):
    """An event that happened at an unknown step: sorts before step 1, never equals a real step."""

    def __new__(cls):
        return super().__new__(cls, 0)

    def __repr__(self) -> str:
        return "UNKNOWN"


UNKNOWN = _Unknown()
Step = int  # 1-indexed; UNKNOWN (== 0) or None where noted

Mode = Literal["online", "offline"]
Status = Literal["pass", "fail", "unavailable", "not_applicable"]


# --------------------------------------------------------------------------------------------
# Sandbox state (collect.py)
# --------------------------------------------------------------------------------------------
@dataclass
class Collected:
    """What the run left behind, read before the verifier touches the machine.

    files         absolute container path -> text, for every file under the rubric's artifact roots
                  (dotfiles included), up to the collector's count/size limits
    truncated     paths whose content was cut at the size limit
    dirs          absolute directories seen under the roots (for var binding and moved trees)
    diff          repo-relative path -> status vs BASE_SHA (``A``/``M``/``D``/``R``, ``?`` untracked);
                  ``None`` when not available (offline mode, or git failed -- see ``errors``)
    base_present  repo-relative path -> existed at BASE_SHA, for the paths the engine asked about
    workdir       the code root (task ``workdir``), absolute
    base_sha      HEAD at reset time (resolve), or None
    errors        collection problems; in online mode they make dependent checks *fail*, never skip
    mode          ``online`` (training / rllm eval, live sandbox) or ``offline`` (harbor replay):
                  only offline may mark checks ``unavailable``
    inputs        what the task and the recorded episode give besides the sandbox, for a workflow's own
                  checks (the evaluation policy's ``inputs`` hook fills it; the common kinds never read it)
    snapshot      offline roots whose ``files`` are the real end-of-run tree (harbor ``artifacts:``),
                  not a replay: an artifact missing there is missing, whatever the trace wrote
    """

    files: dict[str, str] = field(default_factory=dict)
    truncated: set[str] = field(default_factory=set)
    dirs: set[str] = field(default_factory=set)
    diff: dict[str, str] | None = None
    base_present: dict[str, bool] | None = None
    workdir: str | None = None
    base_sha: str | None = None
    pre_status: str | None = None
    errors: list[str] = field(default_factory=list)
    mode: Mode = "online"
    snapshot: frozenset[str] = frozenset()
    inputs: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------------------------
# Trace facts (facts.py)
# --------------------------------------------------------------------------------------------
@dataclass
class DocRead:
    """Evidence that document ``doc`` (a source id) reached the agent at ``step``.

    via        ``command``: a read verb / view on its path (cwd, globs, loops resolved);
               ``fingerprint``: its distinctive lines appeared in an observation, whatever the tool
    coverage   fraction of the doc's fingerprint lines seen in that step's observations (0..1)
    """

    doc: str
    step: Step
    via: Literal["command", "fingerprint"]
    coverage: float = 0.0


@dataclass
class WriteEvent:
    """One write to one path, as far as the trace shows it.

    path        absolute for artifacts; repo-relative (to Collected.workdir) for repo writes
    op          create | overwrite | append | edit | delete | move_in | move_out | unknown
                (create = the replay knew no prior content; checks treat create and overwrite alike)
    ok          the tool's own success signal (editor replies; shell failure markers), None if silent
    content     file content right after this write, replayed; None when it cannot be replayed
    source      the tool: file_editor | heredoc | redirect | printf | python | tee | cp | mv | sed | other
    """

    path: str
    step: Step
    op: str
    ok: bool | None = None
    content: str | None = None
    source: str = "other"
    action_index: int = 0


@dataclass
class RunFact:
    """One invocation of a test / build runner, and what its own output proves.

    valid       the invocation counts as evidence: runner verb in command position, the summary is
                in this call's observation and attributable to the runner segment (no echo/printf
                after it, no result text in the command), its targets / runner script existed at
                BASE_SHA, and the summary reports N >= 1 tests collected or run
    reason      why not valid (empty when valid)
    """

    step: Step
    action_index: int
    command: str
    segment: str
    runner: str
    kind: Literal["test", "build", "script"]
    targets: list[str] = field(default_factory=list)
    valid: bool = False
    reason: str = ""
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    collected: int = 0
    ids: list[str] = field(default_factory=list)  # test ids / files that appear in the output
    observation: str = ""


@dataclass
class CommandFact:
    """A shell command (or one segment of it) the agent ran, for command-equality checks."""

    step: Step
    action_index: int
    command: str
    segments: list[str] = field(default_factory=list)
    cwd: str | None = None
    observation: str = ""


@dataclass
class Facts:
    """Everything the checks may know about the run. Built once per episode by ``facts.build``.

    doc_reads           source id -> reads in step order
    multi_read_steps    steps whose observations carry fingerprints of >= 2 stage documents
    writes              absolute path -> write events in order (artifact roots and anything else)
    repo_writes         writes to the code root, repo-relative paths, in order
    first_repo_write    first repo write step; UNKNOWN when the diff shows edits the trace does not
    last_repo_write     last repo write step (UNKNOWN as above)
    runs                runner invocations (valid or not) in order
    commands            every shell command in order
    final_mismatch      artifact path -> True when the sandbox file differs from the trace replay,
                        i.e. it was (also) written by something the trace does not show
    artifact_paths      artifact id -> resolved absolute path in the final state (None: not found)
    artifact_location   artifact id -> index into Artifact.locations it was found at (None)
    var_bindings        var name -> bound value (None: unbound); var_ambiguous: names bound among several
    windows             stage id -> (start, end) half-open step window; end None = open to the end
    n_steps             number of steps
    edits_by_path       repo-relative path -> steps that edited it (for task/diff relations)
    location_counts     artifact id -> how many of its locations exist at the end (exclusive artifacts)
    unseen_repo_paths   repo paths the diff shows changed that no trace write touched (not dirty before the run)
    """

    doc_reads: dict[str, list[DocRead]] = field(default_factory=dict)
    multi_read_steps: set[int] = field(default_factory=set)
    writes: dict[str, list[WriteEvent]] = field(default_factory=dict)
    repo_writes: list[WriteEvent] = field(default_factory=list)
    first_repo_write: Step | None = None
    last_repo_write: Step | None = None
    runs: list[RunFact] = field(default_factory=list)
    commands: list[CommandFact] = field(default_factory=list)
    final_mismatch: dict[str, bool] = field(default_factory=dict)
    artifact_paths: dict[str, str | None] = field(default_factory=dict)
    artifact_location: dict[str, int | None] = field(default_factory=dict)
    var_bindings: dict[str, str | None] = field(default_factory=dict)
    var_ambiguous: set[str] = field(default_factory=set)
    windows: dict[str, tuple[Step, Step | None]] = field(default_factory=dict)
    n_steps: int = 0
    edits_by_path: dict[str, list[Step]] = field(default_factory=dict)
    location_counts: dict[str, int] = field(default_factory=dict)
    unseen_repo_paths: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    # ---------------------------------------------------------------------------------------
    def first_read(self, doc: str, min_coverage: float = 0.0) -> DocRead | None:
        for r in self.doc_reads.get(doc, []):
            if r.coverage >= min_coverage or r.via == "command":
                return r
        return None

    def artifact_writes(self, path: str | None) -> list[WriteEvent]:
        return list(self.writes.get(path, [])) if path else []


# --------------------------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------------------------
@dataclass
class Result:
    item_id: str
    status: Status
    score: float = 0.0  # in [0, 1]; ratio kinds give fractions, binary kinds 0/1
    detail: str = ""

    @classmethod
    def ok(cls, item: Item, detail: str = "") -> Result:
        return cls(item.id, "pass", 1.0, detail)

    @classmethod
    def no(cls, item: Item, detail: str = "", score: float = 0.0) -> Result:
        return cls(item.id, "fail", score, detail)

    @classmethod
    def ratio(cls, item: Item, num: float, den: float, detail: str = "", threshold: float = 1.0) -> Result:
        if den <= 0:
            return cls(item.id, "fail", 0.0, detail or "nothing to check")
        r = max(0.0, min(1.0, num / den))
        return cls(item.id, "pass" if r >= threshold else "fail", r, detail or f"{num:g}/{den:g}")

    @classmethod
    def unavailable(cls, item: Item, detail: str) -> Result:
        return cls(item.id, "unavailable", 0.0, detail)

    @classmethod
    def not_applicable(cls, item: Item, detail: str = "") -> Result:
        return cls(item.id, "not_applicable", 0.0, detail)


@dataclass
class EvalContext:
    """What a check function receives besides its item.

    artifact_text(id, state)  content of an artifact at ``final`` (sandbox) or ``stage_end`` (replay at
                              the end of its stage window); None when absent / not replayable
    quality                   artifact id -> structure x content score of the items targeting it,
                              filled by the engine's first pass (order checks use it to decide
                              whether a write event is substantive)
    """

    rubric: Rubric
    run: Run
    collected: Collected
    facts: Facts
    quality: dict[str, float] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=dict)

    @property
    def mode(self) -> Mode:
        return self.collected.mode

    def artifact_text(self, artifact_id: str, state: str = "final") -> str | None:
        from . import facts as F  # local: facts imports context

        return F.artifact_text(self, artifact_id, state)
