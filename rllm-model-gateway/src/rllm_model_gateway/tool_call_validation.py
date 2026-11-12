"""Validate tool calls before they reach the agent.

Why: a malformed tool call costs nothing in training when the agent just reports
an error and the model retries on the next turn. With no KL anchor the format
drifts unchecked (``<function=terminal=command>`` grew 1.6% -> 17% of calls in
run 20261019_050357; ``<function=terminal>`` followed by ``<function=command>``
grew to 64% in the floor-0.7 run 20261108_171417, ending it in a turn-limit
loop). In ``drop`` mode the gateway hands back a turn with any invalid call as a
plain text reply, which openhands-sdk takes as the final answer, so the episode
ends and the verifier grades the repository as it stands.

Checks (one code per violation; codes are logged and become metrics):

* ``N1`` the name is empty or not a plain identifier (``terminal=command``, XML
  fragments, whitespace).
* ``N2`` the name is not one of the request's ``tools``.
* ``S1`` the renderer could not parse the block (unclosed ``<tool_call>``, no
  ``<function=``, no function name, argument body not an object).
* ``S2`` the block has a second function tag (``<function=terminal>`` then
  ``<function=command>`` -- the parameter tag written as a function tag).
* ``S3`` anything else outside the ``<parameter=K>...</parameter>`` spans: an
  unclosed parameter (the renderer silently loses it), a stray
  ``</parameter>``, a missing ``</function>``, text between tags.
* ``S4`` the same parameter given twice (the renderer keeps the last one).
* ``A1`` a ``required`` argument is missing.
* ``A2`` an argument the tool does not declare (openhands-sdk action models
  forbid extra fields; ``security_risk`` is always allowed because the SDK
  removes it before validating).
* ``A3`` a value outside the argument's ``enum``.

Argument *types* are not checked here: pydantic's lax coercion (``"30"`` for a
number) cannot be mirrored exactly, and a stricter check would cut valid calls.
The openhands-sdk runner's ``end_on_invalid_tool_call`` backstop ends the
episode on anything the SDK itself rejects, types included.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

MODES = ("off", "log", "drop")

# Removed by openhands-sdk (Agent._extract_security_risk) before the action model
# validates the arguments, so it is never an unknown argument.
ALWAYS_ALLOWED_ARGS = frozenset({"security_risk"})

# Same pattern the renderers' Qwen3.5/3.6 parser uses to extract arguments
# (renderers.parsing._parse_xml_tool_calls); the structure check must see the
# block exactly as that parser does.
_PARAM_RE = re.compile(r"<parameter=([^>]+)>\n?(.*?)\n?</parameter>", re.DOTALL)
_FUNCTION_OPEN_RE = re.compile(r"<function[=>]")
_PLACEHOLDER = "\x00"
_SKELETON_RE = re.compile(r"\s*<function=[^>]+>\s*(?:\x00\s*)*</function>\s*")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]*")
_SWALLOWED_TAG_RE = re.compile(r"(?:^|\n)(?:<parameter=[^>\n]+>|</?function(?:=[^>\n]*)?>)[ \t]*(?:\n|$)")
_EXCERPT = 300


@dataclass(frozen=True)
class Violation:
    code: str
    tool: str | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolSchema:
    properties: frozenset[str] | None  # None: the tool declares no properties
    required: frozenset[str]
    enums: dict[str, tuple[Any, ...]]


def tool_index(tools: list[dict[str, Any]] | None) -> dict[str, ToolSchema] | None:
    """Declared tools of an OpenAI ``tools`` list, by name; None when there is no list."""
    if not tools:
        return None
    index: dict[str, ToolSchema] = {}
    for tool in tools:
        fn = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(fn, dict) or not fn.get("name"):
            continue
        params = fn.get("parameters") or {}
        props = params.get("properties")
        enums: dict[str, tuple[Any, ...]] = {}
        if isinstance(props, dict):
            for key, spec in props.items():
                if isinstance(spec, dict) and isinstance(spec.get("enum"), list):
                    enums[key] = tuple(spec["enum"])
        index[fn["name"]] = ToolSchema(
            properties=frozenset(props) if isinstance(props, dict) else None,
            required=frozenset(params.get("required") or ()),
            enums=enums,
        )
    return index or None


def check_name(name: str | None, index: dict[str, ToolSchema] | None) -> list[Violation]:
    if not name or not _NAME_RE.fullmatch(name):
        return [Violation("N1", name, f"invalid tool name {name!r}"[:_EXCERPT])]
    if index is not None and name not in index:
        return [Violation("N2", name, f"tool {name!r} is not in the request's tools")]
    return []


def check_arguments(name: str, arguments: Any, index: dict[str, ToolSchema] | None) -> list[Violation]:
    """``A*`` checks of one call whose name passed :func:`check_name`."""
    if not isinstance(arguments, dict):
        return [Violation("S1", name, f"arguments are not an object: {type(arguments).__name__}")]
    schema = index.get(name) if index is not None else None
    if schema is None:
        return []
    out: list[Violation] = []
    missing = sorted(schema.required - arguments.keys())
    if missing:
        out.append(Violation("A1", name, f"missing required argument(s) {missing}; given {sorted(arguments)}"))
    if schema.properties is not None:
        extra = sorted(set(arguments) - schema.properties - ALWAYS_ALLOWED_ARGS)
        if extra:
            out.append(Violation("A2", name, f"undeclared argument(s) {extra}"[:_EXCERPT]))
    for key, allowed in schema.enums.items():
        if key in arguments and arguments[key] not in allowed:
            out.append(Violation("A3", name, f"{key}={arguments[key]!r} not in {list(allowed)}"[:_EXCERPT]))
    return out


def check_block_structure(raw: str, name: str | None) -> list[Violation]:
    """``S2``-``S4`` on the text between ``<tool_call>`` and ``</tool_call>``.

    Parameter spans are cut out first (with the renderer's own pattern), so a
    value that happens to contain tag-like text is not mistaken for structure.
    What is left must be exactly ``<function=NAME>`` ... ``</function>``.
    """
    out: list[Violation] = []
    seen: set[str] = set()
    dup: list[str] = []
    swallowed: list[str] = []
    for m in _PARAM_RE.finditer(raw):
        key = m.group(1)
        if key in seen:
            dup.append(key)
        seen.add(key)
        # An unclosed parameter followed by another one: the pattern runs on to
        # the next ``</parameter>`` and the value swallows the next tag. The tag
        # has to stand on its own line, as the model writes tags, so file text
        # that merely mentions ``<parameter=`` inline is not caught.
        if _SWALLOWED_TAG_RE.search(m.group(2)):
            swallowed.append(key)
    if swallowed:
        out.append(Violation("S3", name, f"value of {sorted(set(swallowed))} contains a tag line (unclosed parameter)"[:_EXCERPT]))
    if dup:
        out.append(Violation("S4", name, f"parameter(s) given more than once {sorted(set(dup))}"[:_EXCERPT]))
    skeleton = _PARAM_RE.sub(_PLACEHOLDER, raw)
    if not _SKELETON_RE.fullmatch(skeleton):
        stray = skeleton.replace(_PLACEHOLDER, " ")
        code = "S2" if len(_FUNCTION_OPEN_RE.findall(skeleton)) > 1 else "S3"
        out.append(Violation(code, name, f"malformed block outside parameters: {stray.strip()!r}"[:_EXCERPT]))
    return out


def check_parsed_call(tc: Any, index: dict[str, ToolSchema] | None) -> list[Violation]:
    """All checks for one renderer ``ParsedToolCall``."""
    from renderers.base import ToolCallParseStatus

    status = tc.status
    usable = status == ToolCallParseStatus.OK or (status == ToolCallParseStatus.INVALID_JSON and isinstance(tc.arguments, dict))
    if not usable:
        return [Violation("S1", tc.name, f"parse status {getattr(status, 'name', status)}: {str(tc.raw or '')[:200]!r}")]
    out = check_name(tc.name, index)
    raw = tc.raw if isinstance(tc.raw, str) else ""
    out += check_block_structure(raw, tc.name)
    if not out or all(v.code.startswith("S") for v in out):
        out += check_arguments(tc.name, tc.arguments, index)
    return out


def check_chat_tool_call(call: dict[str, Any], index: dict[str, ToolSchema] | None) -> list[Violation]:
    """Name and argument checks for an OpenAI ``tool_calls`` entry (vLLM's chat path)."""
    import json

    fn = call.get("function") if isinstance(call, dict) else None
    if not isinstance(fn, dict):
        return [Violation("S1", None, "tool call without a function")]
    name = fn.get("name")
    out = check_name(name, index)
    if out:
        return out
    args = fn.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except (json.JSONDecodeError, ValueError):
            return [Violation("S1", name, f"arguments are not valid JSON: {args[:200]!r}")]
    return check_arguments(name, args, index)


def summarize(violations: list[Violation], *, turn: str, action: str, n_calls: int) -> dict[str, Any]:
    """Trace metadata for one turn (``tool_call_violation``)."""
    return {
        "turn": turn,
        "action": action,
        "n_calls": n_calls,
        "codes": sorted({v.code for v in violations}),
        "violations": [v.to_dict() for v in violations[:8]],
    }
