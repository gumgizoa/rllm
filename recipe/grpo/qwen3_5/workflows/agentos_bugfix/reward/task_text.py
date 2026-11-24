"""agentos_bugfix kinds that read the task description the run was given (``Collected.inputs["task"]``).

shape-spec.md has the run write the task description "exactly as given, without modification" to initialization.md, and
requirements.md's Initial Description quotes it again. Two common item rules cannot see that text:

* ``agentos_bugfix.task_residue`` -- ``no_template_residue`` (the fill-in marks: a line holding only ``...``, ``x`` or ``?``)
  with the lines that are lines of the task description taken out first: a ``    ...`` line of a quoted traceback is the
  task's own text, not a blank left in the file (E-1).
* ``agentos_bugfix.task_text`` -- initialization.md holds the task description: at least ``min_share`` (0.5) of its
  words appear in the file in their order (a summary or the first lines only do not), not only some text (E-4 row 2).
  A failure scores share / ``min_share``.

Without a task description (a stored episode or a caller that passes no task) each kind is exactly the common rule it
extends. The task description is the task's ``instruction``; when it wraps the issue in ``<issue_description>`` tags
(SWE-Gym training tasks), the text inside them.
"""

from __future__ import annotations

import difflib
import re
from typing import Any

from ....workflow_rubric.checks import artifacts as A
from ....workflow_rubric.checks import register
from ....workflow_rubric.context import EvalContext, Result
from ....workflow_rubric.schema import Item

_ISSUE = re.compile(r"<issue_description>\s*(.*?)\s*</issue_description>", re.S)
_MARKER = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+")


def task_description(ctx: EvalContext) -> str | None:
    """The task text the run was given, or None when the scorer was not handed the task."""
    task: Any = (getattr(ctx.collected, "inputs", None) or {}).get("task")
    text = getattr(task, "instruction", None)
    if not isinstance(text, str):
        meta = task.get("metadata") if isinstance(task, dict) else getattr(task, "metadata", None)
        text = meta.get("instruction") if isinstance(meta, dict) else (task.get("instruction") if isinstance(task, dict) else None)
    if not isinstance(text, str) or not text.strip():
        return None
    m = _ISSUE.search(text)
    return m.group(1) if m else text


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


class _WithoutTaskLines:
    """``ctx`` whose artifact texts lack the lines that are lines of the task description."""

    def __init__(self, ctx: EvalContext, lines: set[str]):
        self._ctx, self._lines = ctx, lines

    def __getattr__(self, name: str):
        return getattr(self._ctx, name)

    def artifact_text(self, aid: str, state: str = "final") -> str | None:
        t = self._ctx.artifact_text(aid, state)
        if t is None:
            return None
        return "\n".join(ln for ln in t.split("\n") if not (_ws(ln) in self._lines or _ws(_MARKER.sub("", ln)) in self._lines))


@register("agentos_bugfix.task_residue", params={"patterns": True, "section": False}, availability=("sandbox_file",), common=False)
def task_residue(item: Item, ctx: EvalContext):
    """``no_template_residue`` on the artifact without the lines it shares with the task description."""
    desc = task_description(ctx)
    if desc is None:
        return A.no_template_residue(item, ctx)
    lines = {_ws(x) for x in desc.splitlines() if _ws(x)}
    return A.no_template_residue(item, _WithoutTaskLines(ctx, lines))


@register("agentos_bugfix.task_text", params={"pattern": True, "min_share": False}, availability=("sandbox_file",), common=False)
def task_text(item: Item, ctx: EvalContext):
    """The file holds the task description: the share of its words (split on whitespace) that the file has in the same
    order (difflib's matching blocks) is at least ``min_share``. Without a task description: ``item_format`` with
    ``pattern`` (some text)."""
    desc = task_description(ctx)
    if desc is None:
        return A.item_format(item, ctx)
    text = A._text(item, ctx)
    if text is None:
        return Result.no(item, "artifact absent")
    want, got = desc.split(), text.split()
    if not want:
        return A.item_format(item, ctx)
    sm = difflib.SequenceMatcher(None, want, got, autojunk=False)
    share = sum(m.size for m in sm.get_matching_blocks()) / len(want)
    need = float((item.check.params or {}).get("min_share", 0.5))
    detail = f"{share:.2f} of the task description's {len(want)} words, in order"
    if share >= need:
        return Result.ok(item, detail)
    # a failure scored by how much of the text is there: a summary is a poor copy, not an absent file (the order item
    # reads the file's quality, and a format problem is this stage's to count, not the order's)
    return Result(item.id, "fail", share / need if need > 0 else 0.0, detail + f" < {need:g}")
