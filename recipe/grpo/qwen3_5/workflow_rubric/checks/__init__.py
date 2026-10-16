"""Check kinds: one function per kind, ``fn(item, ctx) -> Result``.

A kind is registered with the parameters it accepts (``params``: name -> required?) and the inputs
it needs (``availability``). The engine calls it only after ``applies_when`` held; it must not
raise on anything the agent controls -- a malformed artifact is a ``fail``, not an exception.

Workflow plugins register ``<wf>.<name>`` kinds from their ``reward/checks.py``; the common kinds
live in ``actions.py`` (doc reads, order, writes, execution, prohibitions) and ``artifacts.py``
(existence, paths, frontmatter, sections, labels, fields, item formats, residue, cross refs).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..context import EvalContext, Result
from ..schema import Item, Rubric, RubricError

CheckFn = Callable[[Item, EvalContext], Result]


@dataclass
class Kind:
    name: str
    fn: CheckFn
    params: dict[str, bool] = field(default_factory=dict)  # param -> required
    availability: tuple[str, ...] = ("sandbox_file",)
    common: bool = True  # False for workflow plugins (scope must be "specific")
    doc: str = ""
    choices: dict[str, tuple[str, ...]] = field(default_factory=dict)  # param -> the values the kind understands


REGISTRY: dict[str, Kind] = {}


def register(name: str, params: dict[str, bool] | None = None, availability: tuple[str, ...] = ("sandbox_file",), common: bool = True, choices: dict[str, tuple[str, ...]] | None = None):
    """``choices``: for an enumerated parameter (a plugin's ``rule``), every value the kind implements; the
    generator rejects any other value (G6) and so does :func:`validate_params` -- an invented rule name would
    otherwise be an item that fails every run."""

    def deco(fn: CheckFn) -> CheckFn:
        if name in REGISTRY and REGISTRY[name].fn is not fn:
            raise RuntimeError(f"check kind {name!r} registered twice")
        REGISTRY[name] = Kind(name, fn, dict(params or {}), tuple(availability), common, (fn.__doc__ or "").strip(), {k: tuple(v) for k, v in (choices or {}).items()})
        return fn

    return deco


def get(name: str) -> Kind:
    load_common()
    try:
        return REGISTRY[name]
    except KeyError:
        raise RubricError(f"unknown check kind {name!r}; registered: {sorted(REGISTRY)}") from None


def load_common() -> None:
    from . import actions, artifacts  # noqa: F401  (registration side effects)


def validate_params(rubric: Rubric) -> None:
    """Every item's kind exists and gets exactly the parameters it accepts; plugin kinds are specific."""
    load_common()
    errors = []
    for it in rubric.items:
        if it.check.kind == "unimplemented":
            continue
        k = REGISTRY.get(it.check.kind)
        if k is None:
            errors.append(f"{it.id}: unknown kind {it.check.kind!r}")
            continue
        missing = [p for p, req in k.params.items() if req and p not in it.check.params]
        extra = [p for p in it.check.params if p not in k.params]
        if missing or extra:
            errors.append(f"{it.id}: {it.check.kind} missing={missing} unexpected={extra}")
        if not k.common and it.scope != "specific":
            errors.append(f"{it.id}: plugin kind {it.check.kind} must be scope specific")
        for p, allowed in k.choices.items():
            bad = [v for v in _values(it.check.params.get(p)) if v not in allowed]
            if p in it.check.params and bad:
                errors.append(f"{it.id}: {it.check.kind} {p}={bad[0]!r} not one of {list(allowed)}")
    if errors:
        raise RubricError("; ".join(errors[:20]))


def _values(v) -> list:
    """An enumerated parameter's value(s), as strings ('' for a value that is not one: never a valid choice)."""
    if v is None:
        return []
    return [x if isinstance(x, str) else "" for x in (v if isinstance(v, (list, tuple)) else [v])]


__all__ = ["REGISTRY", "Kind", "get", "register", "validate_params", "load_common"]
