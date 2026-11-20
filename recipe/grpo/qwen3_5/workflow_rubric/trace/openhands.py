"""OpenHands (openhands-sdk) tool calls -> Action.

Tools as harbor records them (tool_definitions in trajectory.json):
    terminal     {command, is_input, timeout, reset}   is_input=true sends keystrokes, not a command
    file_editor  {command: view|create|str_replace|insert|undo_edit, path, file_text, old_str,
                  new_str, insert_line, view_range}
    think / task_tracker / finish                       no effect

The editor's replies are the only success signal the trajectory keeps, so ok/fail is read off them.
"""

from __future__ import annotations

import re

from .model import Action

NAMES = {"openhands-sdk", "openhands"}

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


# The harness refused the call, so nothing in it ran: the terminal reads two commands where one
# was meant, or a previous command is still running, or the arguments failed validation. The
# refusal is always the very start of the observation (after the optional error banner); the same
# words later in an observation are a command's own output and do not count. The previous command's
# output may stand between the "[Below is the output ...]" header and the "is NOT executed" notice.
_REJECTED = re.compile(
    r"\A\s*(?:\[An error occurred during execution\.\]\s*)?"
    r"(?:Cannot execute multiple commands at once"
    r"|\[Below is the output of the previous command\.\][\s\S]*?\[Your command \"[\s\S]*?\" is NOT executed\."
    r"|Error validating tool ')"
)


def rejected(observation: str) -> bool:
    """True when the harness answered the call with a refusal: the call did not run."""
    return bool(_REJECTED.match(observation or ""))


def parse(name: str, args: dict, observation: str) -> Action:
    if (name in _SHELL or name in _EDITOR) and rejected(observation):
        return Action("other", name, observation=observation)
    if name in _SHELL:
        cmd = args.get("command")
        if args.get("is_input") or not isinstance(cmd, str) or not cmd.strip():
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
