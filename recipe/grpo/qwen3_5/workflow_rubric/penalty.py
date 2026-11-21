"""Penalty items: the rules a workflow keeps outside ``compliance``, and the one signal they give.

A penalty item is a rubric item marked ``log_only`` whose id reads ``<workflow>.<stage>.penalty.<name>``: the engine
judges it with every run and never counts it in ``<workflow>/compliance``. :func:`post` (a ``RubricEvaluation``'s
``post`` hook, the same for every workflow) turns their results into

    <workflow>/penalty                       the mean of the items' values, 1 = every rule kept
    <workflow>/<stage>.penalty.<name>        each item's value
    <workflow>/penalty_applies.<name>        1 when the item was judged on the run, 0 when it stood outside it
    <workflow>/penalty_unavailable           how many items could not be judged
    <workflow>/penalty_solved                the mean a solved rollout is paid by, when the workflow has
                                             ``unsolved_only`` items (below); absent otherwise

What an item is worth, by its result:

    pass / fail        its score (0 or 1; a ratio where the kind counts several things)
    not_applicable     the score the kind gave it (:func:`outside`): 0 when the run never did what the item is about
                       (it changed no code, it ran no test), 1 when it did and the item's condition did not arise
                       (it ran the tests and none failed). Every item stays in the mean, so a run cannot gain by
                       not doing the thing an item would have judged.
    unavailable        left out of the mean: what the item needs was not there to read (no reference fix for the
                       task, a sandbox step that failed), which says nothing about the run.

A run whose items are all unavailable has no ``penalty`` signal; a kind that raises is a failed item, as everywhere
in the engine. ``train.py`` folds ``<workflow>/penalty`` into the reward (``WorkflowSpec.penalty_signal``).

Items that only tell failures apart (``unsolved_only``)
    An item judged against something the agent cannot see -- the task's reference fix -- would cost a rollout that
    solved the task another way. Such an item is named in ``post(report, unsolved_only=...)`` (by its name after
    ``penalty.``): it stays in ``penalty`` as judged, and ``penalty_solved`` is the same mean with each of them worth
    1. ``train.py`` pays a solved rollout by ``penalty_solved`` and an unsolved one by ``penalty``
    (:data:`SOLVED_SUFFIX`), so every other item -- the test behaviour, the plan -- still costs a solve that broke it.
    This is per item; ``compliance_reward.penalty_gate=unsolved`` is the same waiver for the whole mean.
"""

from __future__ import annotations

from .context import Result
from .schema import Item

SEGMENT = "penalty"
SOLVED_SUFFIX = "_solved"  # <penalty signal> + this: the mean with the ``unsolved_only`` items worth 1
JUDGED = ("pass", "fail")


def names(item_id: str) -> tuple[str, str] | None:
    """(the id without its workflow, the part after ``penalty.``) of a penalty item's id; None for any other item."""
    parts = str(item_id).split(".")
    if len(parts) > 3 and parts[2] == SEGMENT:
        return ".".join(parts[1:]), ".".join(parts[3:])
    return None


def outside(item: Item, detail: str, *, premise: bool) -> Result:
    """The result of an item the run stands outside of. ``premise``: the run did what the item is about (it changed
    code, it ran a test) and only the item's condition did not arise -> worth 1; it never did -> worth 0."""
    return Result.not_applicable(item, detail, score=1.0 if premise else 0.0)


def post(report, unsolved_only: tuple[str, ...] = ()) -> dict[str, float]:
    """The penalty signals of a finished report (names without the workflow prefix); empty without a penalty item.
    ``unsolved_only``: the items (their names after ``penalty.``) a solved rollout is not judged by -- with any,
    ``penalty_solved`` is the mean with those worth 1."""
    out: dict[str, float] = {}
    values: list[float] = []
    solved: list[float] = []
    unavailable = 0
    seen = False
    for item_id, r in report.results.items():
        nm = names(item_id)
        if nm is None:
            continue
        seen = True
        key, short = nm
        status = getattr(r, "status", None)
        if status not in JUDGED and status != "not_applicable":
            unavailable += 1
            continue
        v = float(getattr(r, "score", 0.0))
        values.append(v)
        solved.append(1.0 if short in unsolved_only else v)
        out[key] = v
        out[f"penalty_applies.{short}"] = float(status in JUDGED)
    if not seen:
        return {}
    if values:
        out["penalty"] = sum(values) / len(values)
        if unsolved_only:
            out["penalty" + SOLVED_SUFFIX] = sum(solved) / len(solved)
    out["penalty_unavailable"] = float(unavailable)
    return out


__all__ = ["SEGMENT", "SOLVED_SUFFIX", "names", "outside", "post"]
