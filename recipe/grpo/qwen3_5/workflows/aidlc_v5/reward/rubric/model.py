"""The harness-independent view of a run that the scorer consumes.

A front-end (aidlc/frontends/*) turns whatever a harness recorded -- a mini-swe-agent transcript,
a harbor ATIF trajectory -- into a `Run`: numbered steps, each holding the `Action`s the agent took
and what came back. Everything downstream (facts, grading, scoring) reads only these types, so a
new harness is a new front-end and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

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
