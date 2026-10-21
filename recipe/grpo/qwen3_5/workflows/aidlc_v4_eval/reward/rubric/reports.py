"""Report-era stage reports: the five printed headings, and which channel carried each one.

The report-era workflow (RUBRIC.md v1, before stages began writing files) ends each stage by
EMITTING a report -- `REVERSE ENGINEERING`, `REQUIREMENTS ANALYSIS`, ... -- and forbids report
files outright ("This workflow produces no design, requirement, plan, or report files"). So the
channel a heading travelled on decides whether the stage was reported at all:

    prose        the agent's own text for the turn. Compliant.
    stdout       echo'd or printed, unredirected. Also compliant.
    file         redirected into a file. NOT a report, and a breach of "No documents".
    stdout+file  printed AND saved. Reported, but the forbidden file exists -- the two readings of
                 the rule split here, so it is kept distinct instead of resolved silently.

This module only says WHERE each heading appeared; `score.py` decides what that is worth, and the
artifact-era equivalent lives in `artifacts.py`. Both are extracted for every run, so which era a
run belongs to is visible from which set is populated rather than configured.

WHERE `prose` COMES FROM PER HARNESS. mini-swe-agent puts the agent's text in the assistant
message. harbor's ATIF has a `message` field too, but the tool-calling agents leave it empty
almost always (measured: opencode 1% of steps, openhands-sdk 0%); OpenHands instead reasons inside
its `think` tool. So the front-ends fold both into `Step.message`, and a heading those agents
"printed" will in practice show up on the `stdout` channel (an `echo`/`cat`) or not at all.
"""

from __future__ import annotations

import re

from . import artifacts as A
from .model import Action, Run

STAGE_HEADINGS = [
    "REVERSE ENGINEERING",
    "REQUIREMENTS ANALYSIS",
    "CODE GENERATION PLAN",
    "CODE GENERATION COMPLETE",
    "BUILD AND TEST",
]

# A redirect, excluding the arrow operators that appear in ordinary report prose: `-> Author` in a
# type annotation read as `> Author` and classified a printed report as file-written, i.e. missing.
REDIRECT_RE = re.compile(r"(?<![-=<>!])>>?\s*[^\s|&;]+")
TEE_RE = re.compile(r"\|\s*tee\b")

# Best channel wins when one turn emitted the same heading more than one way: a heading printed
# cleanly is reported even if another action in the same turn also saved it.
PRECEDENCE = ["prose", "stdout", "stdout+file", "file"]

WRITE_KINDS = ("create", "replace", "insert")


def shell_channel(heading: str, command: str) -> str | None:
    """Channel for a heading that appears in a shell command, or None if it does not."""
    if heading not in command:
        return None
    pos = command.index(heading)

    for opener, _body, (start, stop) in A.heredocs(command):
        if not start <= pos < stop:
            continue
        if "/dev/null" in opener:
            return "stdout"
        target = re.search(r">>?\s*([^\s|&;]+)", opener)
        if REDIRECT_RE.search(opener) or TEE_RE.search(opener):
            # `cat <<EOF > /tmp/plan.md && cat /tmp/plan.md` -- the trailing cat prints the whole
            # report unredirected, so it WAS emitted. Scoring that 0 fell almost entirely on the
            # un-optimised configuration, where it is the model's default way of reporting.
            if target and re.search(rf"\bcat\s+{re.escape(target.group(1))}(?!\s*[>|])", command):
                return "stdout+file"
            return "file"
        return "stdout"

    # Not inside a heredoc: the heading is inline, e.g. `echo "HEADING ..." > file`.
    head, tail = command[:pos], command[pos:]
    if REDIRECT_RE.search(head) and "/dev/null" not in head:
        return "file"
    if REDIRECT_RE.search(tail) and not re.search(r">>?\s*/dev/null", tail):
        return "file"
    if TEE_RE.search(tail):
        return "file"
    return "stdout"


def action_channel(heading: str, a: Action) -> str | None:
    """Channel for one action. A tool write is a file by construction -- no redirect to read."""
    if a.kind == "shell":
        return shell_channel(heading, a.command or "")
    if a.kind in WRITE_KINDS and heading in (a.text or ""):
        return "file"
    return None


def step_prose(step) -> str:
    """The agent's own text for a turn: its message plus any non-acting tool's text (`think`)."""
    return "\n".join([step.message] + [a.text or "" for a in step.actions if not a.acts])


def trace(run: Run) -> dict:
    """v1's report facts. Key names match the frozen extractor's so its scoring ports unchanged.

    A turn the harness discarded emitted nothing, so its headings cannot satisfy a stage; the
    front-ends express that by leaving such a turn empty (no actions, no message).
    """
    first: dict[str, int] = {}
    channel: dict[str, str] = {}
    file_bound: list[dict] = []
    also_file: list[dict] = []

    for step in run.steps:
        prose = step_prose(step)
        for heading in STAGE_HEADINGS:
            found = {"prose"} if heading in prose else set()
            found |= {c for c in (action_channel(heading, a) for a in step.actions) if c}
            if not found:
                continue
            best = min(found, key=PRECEDENCE.index)
            if best == "file":
                file_bound.append({"step": step.n, "heading": heading})
                continue          # not a report: the report-era workflow forbids report files
            if best == "stdout+file":
                also_file.append({"step": step.n, "heading": heading})
                best = "stdout"
            if heading not in first:
                first[heading], channel[heading] = step.n, best

    return {
        "stage_report_first_step": first,
        "stage_report_channel": channel,
        "stage_reports_missing": [h for h in STAGE_HEADINGS if h not in first],
        "reports_written_to_file": file_bound,
        "reports_also_written_to_file": also_file,
    }


def strictly_missing(f: dict) -> list[str]:
    """Headings the strict "No documents" reading counts as never reported.

    Only an emission that was *itself* file-bound is withdrawn: a heading whose first appearance
    was clean stdout and which a later step also saved was still reported cleanly.
    """
    first = f.get("stage_report_first_step", {})
    withdrawn = {r["heading"] for r in f.get("reports_also_written_to_file", [])
                 if first.get(r["heading"]) == r["step"]}
    return sorted(set(f["stage_reports_missing"]) | withdrawn)
