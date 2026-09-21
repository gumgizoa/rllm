#!/usr/bin/env python3
"""Convert gateway-traced ``rllm eval`` runs into the SFT parquet contract.

Named for what it reads: the episode's ``chat_completions`` as the rLLM model
gateway recorded it. See "Which episodes this accepts" below for the one case
that produces something else.

    python recipe/sft/converters/from_rllm_gateway.py <run_id> [<run_id> ...] \\
        --output-dir recipe/sft/data/swe/raw

Like every converter here, this stage decides *shape*, not *selection* in the
training sense: which task and which attempt survive is an eval-level question
(pass@k, reward), answered here because the answer lives in ``results.json`` and
nowhere else. What to train on out of the survivors - a length ceiling, reasoning
required, train/valid - stays with ``scripts/filter_sft_parquet.py``, so this
expensive pass runs once per eval and any number of mixes come out of it.

Why not ``rllm dataset from-eval``
---------------------------------
That command emits ``{"messages": [...]}`` rows, and its ``_clean_message`` keeps
only ``role``/``content``/``tool_calls``/``tool_call_id``/``name``. ``reasoning``
is dropped, and it is the one field that cannot be reconstructed afterwards: with
it gone every row must be ``enable_thinking: false``, which trains Qwen3.5 to
answer without thinking. So this converter reads the episode JSON directly and
keeps reasoning, while reusing that module's *selection* logic (the filter DSL,
pass@k aggregation, per-task ranking) so the two cannot disagree about what
"solved" means.

It therefore imports a few private names from ``rllm.eval.curation``. That is a
deliberate in-repo coupling, not a public API bet: both files live in this
repository, so a rename breaks the import here and gets fixed in the same commit.
The alternative is copying the ``eval_idx = idx * attempts + attempt`` episode
indexing rule, which would drift silently.

What the episode messages need fixing for (see ``swe_sft/schemas.py`` for why each
one matters):

* ``tool_calls[*].function.arguments`` arrives as a JSON *string* (OpenAI
  convention), but chat templates iterate it with Jinja ``|items``.
* Reasoning arrives either in its own ``reasoning`` / ``reasoning_content`` key
  (vLLM with a reasoning parser) or fused into ``content`` as
  ``"<think>...</think>answer"`` (without one). Both are normalized into the
  contract's ``reasoning`` field.
* Trajectories frequently end on a ``tool`` message - trailing context no
  assistant turn ever consumes.
* The tool schemas the policy saw are nowhere on disk - the gateway holds them
  in ``TraceRecord.raw_request``, ``trace_record_to_step`` does not copy them
  onto the Step, and the Harbor trial dir records the agent's prompt templates
  but not its tool definitions. Pass them with ``--tools`` and they are written
  per row, which is where the contract keeps them. Getting the file wrong is
  silent, so take it from the scaffold's source rather than reconstructing it.
  An agent that does not use tool calling needs no ``--tools``: ``tools: null``
  is then correct, because that is what the policy saw.

Which episodes this accepts
---------------------------
An episode is assembled in two stages, and the second decides the shape. The
agent produces a lightweight Episode first - for ``--agent harbor:*`` that is
``load_atif_steps``, whose ``chat_completions`` is flattened into strings
(reasoning as ``<think>...</think>``, each tool call as a
``<tool_call>{json}</tool_call>`` block inside ``content``, the observation as a
``user`` turn). Then ``AgentFlowEngine._enrich``
(``engine/agentflow_engine.py:236``) replaces every step with the gateway trace
step, keeping only ``action``/``reward``/``done`` from the agent's. The trace
step carries ``trace.messages + trace.response_message`` - the OpenAI wire
format, verbatim.

So whenever the agent's calls went through the gateway, the episode on disk is
in the wire format, Harbor or native alike, and this converter handles it.

The flattened shape reaches disk only via the ``if not traces`` branch
(``agentflow_engine.py:169``), i.e. nothing was traced. Such rows are
contract-*valid* but wrong - the model would learn to emit the literal
characters ``<tool_call>`` - so this converter refuses them rather than passing
them through, because nothing downstream can tell the difference. A converter
for that case should read the structured fields ``_build_step`` leaves on each
Step (``action``, ``thought``, ``model_response``, ``observation``), not parse
the flattened text.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from swe_sft.dataset.utils.parquet import BatchWriter, check_contract
from swe_sft.schemas import SFTSample

# rllm.* is imported lazily inside select_attempts()/main(), not here: importing
# rllm pulls in the whole engine dependency tree, and everything above that line is
# pure episode-JSON -> contract conversion that should stay testable without it.

VALID_ROLES = ("system", "user", "assistant", "tool")

# Mirrors rllm.engine.trace_converter.REQUEST_TOOLS_KEY, duplicated so the
# conversion functions stay importable without rllm. main() asserts they agree.
REQUEST_TOOLS_KEY = "request_tools"


class SkipRow(Exception):
    """Raised when an attempt cannot be made contract-valid at all."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


# --------------------------------------------------------------------------- #
# Episode -> contract messages
# --------------------------------------------------------------------------- #


def split_thinking(content: str) -> tuple[str, str]:
    """Split ``"<think>reasoning</think>answer"`` into ``(reasoning, answer)``.

    Splits on the **first** ``</think>``. Qwen's template splits on the last
    (``content.split('</think>')[-1]``), so an answer that quotes a closing tag
    would lose everything before its own last one - rare, and silent.

    Returns ``("", content)`` when the turn carries no inline reasoning.
    """
    stripped = content.strip()
    if not stripped.startswith("<think>") or "</think>" not in stripped:
        return "", stripped
    reasoning, _, answer = stripped[len("<think>") :].partition("</think>")
    return reasoning.strip(), answer.lstrip("\n")


def clean_message(message: dict[str, Any]) -> dict[str, Any]:
    """Normalize one episode ``chat_completions`` entry into a contract message."""
    if not isinstance(message, dict):
        raise SkipRow("message is not an object", type(message).__name__)

    role = message.get("role")
    if role not in VALID_ROLES:
        raise SkipRow("unexpected role", repr(role))

    content = message.get("content")
    if content is None:
        content = ""
    elif not isinstance(content, str):
        # A list-shaped multimodal content block has no place in a text SFT row,
        # and str() of it would train the model on a Python repr.
        raise SkipRow("non-string content", type(content).__name__)

    out: dict[str, Any] = {"role": role, "content": content}

    if role == "tool":
        if message.get("tool_call_id"):
            out["tool_call_id"] = message["tool_call_id"]
        return out

    if role == "assistant":
        # rLLM stores the engine's reasoning under "reasoning" (see
        # rllm/types.py Step.from_model_output); Harbor traces use
        # "reasoning_content". Either way the contract keeps it in "reasoning".
        reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
        inline_reasoning, answer = split_thinking(out["content"])
        if inline_reasoning and reasoning and inline_reasoning != reasoning:
            # Both filled and disagreeing means we would have to guess which one
            # the model actually emitted. Refusing beats picking one.
            raise SkipRow("reasoning present both inline and in its own field, and they differ")
        out["content"] = answer
        reasoning = (reasoning or inline_reasoning).strip()
        if reasoning:
            out["reasoning"] = reasoning
        if "<tool_call>" in out["content"]:
            # See "Which episodes this accepts": the Harbor/ATIF bridge serializes
            # tool calls into the message text. Contract-valid, silently wrong.
            raise SkipRow(
                "assistant content carries a flattened <tool_call> block",
                "Harbor/ATIF episodes need their own converter",
            )

    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        return out
    if role != "assistant":
        raise SkipRow("tool_calls on non-assistant role", repr(role))

    converted = []
    for call in tool_calls:
        if not isinstance(call, dict):
            raise SkipRow("tool call is not an object", type(call).__name__)
        # OpenAI shape is {"function": {...}}; some engines emit the bare function.
        function = call.get("function") if isinstance(call.get("function"), dict) else call
        name = function.get("name")
        if not name:
            raise SkipRow("tool call without a function name")

        raw_arguments = function.get("arguments")
        if raw_arguments is None:
            arguments: Any = {}
        elif isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise SkipRow("unparsable tool call arguments", str(exc)) from exc
        else:
            arguments = raw_arguments
        if not isinstance(arguments, dict):
            raise SkipRow("tool call arguments are not an object", type(arguments).__name__)

        entry: dict[str, Any] = {"type": "function", "function": {"name": name, "arguments": arguments}}
        if call.get("id"):
            entry["id"] = call["id"]
        converted.append(entry)

    out["tool_calls"] = converted
    return out


def episode_messages(episode: dict[str, Any], trajectory_name: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """``(messages, tools)`` from an episode's chosen trajectory.

    Uses the last step that carries ``chat_completions`` - that step holds the
    whole conversation, which is also how eval scores the trajectory - and
    takes the tool schemas from that same step's
    ``metadata["request_tools"]``, which ``trace_record_to_step`` copies out of
    the gateway's ``raw_request``. Runs recorded before that existed have no
    such key and fall back to ``--tools``.
    """
    trajectories = episode.get("trajectories") or []
    if not trajectories:
        raise SkipRow("episode has no trajectories")

    if trajectory_name:
        chosen = next((t for t in trajectories if t.get("name") == trajectory_name), None)
        if chosen is None:
            raise SkipRow("named trajectory not found", trajectory_name)
    else:
        chosen = trajectories[0]

    for step in reversed(chosen.get("steps") or []):
        raw = step.get("chat_completions")
        if raw:
            recorded = (step.get("metadata") or {}).get(REQUEST_TOOLS_KEY)
            tools = recorded if isinstance(recorded, list) and recorded else None
            return [clean_message(m) for m in raw], tools
    raise SkipRow("no step carries chat_completions")


def build_sample(
    episode: dict[str, Any],
    trajectory_name: str | None,
    tools: list[dict[str, Any]] | None,
    metadata: dict[str, Any],
) -> SFTSample:
    """Convert one episode into a contract sample. Raises :class:`SkipRow`.

    ``tools`` is the ``--tools`` fallback. Schemas recorded on the episode win:
    they are what the policy was actually served, while the flag is a file a
    human keeps in sync by hand. Which one was used is recorded in
    ``metadata["tools_source"]``, so a mix can be filtered on it later
    (``--metadata-eq tools_source=episode``).
    """
    messages, recorded_tools = episode_messages(episode, trajectory_name)
    if recorded_tools is not None:
        tools, metadata = recorded_tools, {**metadata, "tools_source": "episode"}
    elif tools is not None:
        metadata = {**metadata, "tools_source": "flag"}

    # Trailing context that no assistant turn ever consumes.
    last_assistant = max((i for i, m in enumerate(messages) if m["role"] == "assistant"), default=-1)
    if last_assistant < 0:
        raise SkipRow("no assistant turn")
    messages = messages[: last_assistant + 1]

    if not any(m["role"] == "user" for m in messages):
        raise SkipRow("no user query")

    # A turn with no reasoning needs enable_thinking=false, or the template's
    # forced </think> ends up inside the supervised target. Contract compliance,
    # not a filtering decision - dropping such rows is --require-reasoning's call.
    all_have_reasoning = all(m.get("reasoning") for m in messages if m["role"] == "assistant")
    kwargs = None if all_have_reasoning else {"enable_thinking": False}

    try:
        return SFTSample(messages=messages, tools=tools, apply_chat_template_kwargs=kwargs, metadata=metadata)
    except ValueError as exc:
        raise SkipRow("format validation", str(exc).splitlines()[0]) from exc


# --------------------------------------------------------------------------- #
# Attempt selection (reuses rllm.eval.curation)
# --------------------------------------------------------------------------- #


def select_attempts(run_refs: list[str], config):
    """Yield ``(ref, task_id)`` for every attempt that survives the eval filter.

    Mirrors ``rllm.eval.curation.curate``'s selection, minus its message
    extraction. ``--select shortest`` is deliberately absent: ranking by length
    means loading every candidate episode of every task, and a length ceiling is
    already ``filter_sft_parquet.py --max-tokens``'s job, measured in tokens
    against the real template rather than in characters.
    """
    # In-repo coupling on private names, see the module docstring.
    from rllm.eval.curation import _build_groups, _load_run, _ranked_candidates
    from rllm.eval.filter_dsl import compile_filter

    config.validate()
    flt = compile_filter(config.filter_expr)
    runs = [_load_run(r) for r in run_refs]
    groups = _build_groups(runs, config.metric)

    kept = [g for g in groups if flt.evaluate(g.filter_namespace())]
    print(f"runs {len(runs)}, tasks {len(groups)}, attempts {sum(g.n for g in groups)}")
    print(f"tasks kept by {config.filter_expr!r} (metric={config.metric}): {len(kept)}")

    limit = 1 if config.select == "best" else config.max_per_task
    for group in kept:
        for taken, ref in enumerate(_ranked_candidates(group, config)):
            if limit is not None and taken >= limit:
                break
            yield ref, group.task_id


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #


def load_tools(path: str | None) -> list[dict[str, Any]] | None:
    if not path:
        return None
    tools = json.loads(Path(path).read_text())
    if not isinstance(tools, list):
        raise SystemExit(f"--tools {path} must hold a JSON array of tool schemas, got {type(tools).__name__}")
    return tools or None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+", help="Eval run ids (under ~/.rllm/eval_results) or paths to run dirs.")
    parser.add_argument("--output-dir", required=True, help="Directory to write data.parquet into.")
    parser.add_argument(
        "--tools",
        default=None,
        help="Fallback JSON file of OpenAI tool schemas, for runs recorded before the gateway started saving them. Schemas found on the episode always win.",
    )
    # Selection, same vocabulary as `rllm dataset from-eval`.
    parser.add_argument("--metric", default="is_correct", help="What avg/best/worst aggregate (default: is_correct).")
    parser.add_argument("--filter", dest="filter_expr", default="solved", help='Task-level filter, e.g. "0 < avg < 1" (default: solved).')
    parser.add_argument("--select", default="correct", choices=["correct", "best", "all"], help="Which trajectories to keep per task (default: correct).")
    parser.add_argument("--max-per-task", type=int, default=None, help="Cap trajectories kept per task.")
    parser.add_argument("--min-reward", type=float, default=None, help="Per-trajectory passing threshold on the metric.")
    parser.add_argument("--trajectory", default=None, help="Named trajectory to extract for multi-agent flows (default: first).")
    parser.add_argument("--max-rows", type=int, default=-1, help="Stop after N written rows (smoke tests).")
    parser.add_argument("--batch-size", type=int, default=512, help="Rows per write batch.")
    parser.add_argument(
        "--check",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Read the written file back and validate every row.",
    )
    return parser.parse_args()


def main() -> None:
    from rllm.engine import trace_converter
    from rllm.eval.curation import CurationConfig, CurationError

    if trace_converter.REQUEST_TOOLS_KEY != REQUEST_TOOLS_KEY:
        raise SystemExit(f"key drift: rllm writes tool schemas under {trace_converter.REQUEST_TOOLS_KEY!r} but this converter reads {REQUEST_TOOLS_KEY!r}")

    args = parse_args()

    tools = load_tools(args.tools)

    config = CurationConfig(
        metric=args.metric,
        filter_expr=args.filter_expr,
        select=args.select,
        max_per_task=args.max_per_task,
        min_reward=args.min_reward,
        trajectory=args.trajectory,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "data.parquet"

    skipped: Counter[str] = Counter()
    stats: Counter[str] = Counter()
    n_read = 0
    n_added = 0

    try:
        with BatchWriter(output_path, batch_size=args.batch_size) as writer:
            for ref, task_id in select_attempts(args.runs, config):
                if 0 < args.max_rows <= n_added:
                    break
                n_read += 1

                if ref.episode_path is None or not Path(ref.episode_path).is_file():
                    skipped["episode file missing"] += 1
                    continue
                try:
                    episode = json.loads(Path(ref.episode_path).read_text())
                except (OSError, json.JSONDecodeError) as exc:
                    skipped["unreadable episode"] += 1
                    print(f"  {ref.episode_path}: {exc}", file=sys.stderr)
                    continue

                metadata = {
                    # filter_sft_parquet.py splits train/valid on this by default,
                    # so every attempt of one task lands on the same side.
                    "instance_id": task_id,
                    "run_id": ref.run_id,
                    "eval_idx": ref.eval_idx,
                    "attempt": ref.attempt,
                    "reward": ref.reward,
                    "score": ref.score,
                    "is_correct": ref.is_correct,
                }
                try:
                    sample = build_sample(episode, args.trajectory, tools, metadata)
                except SkipRow as exc:
                    skipped[exc.reason] += 1
                    continue

                stats["assistant_turns"] += sum(1 for m in sample.messages if m.role == "assistant")
                if sample.apply_chat_template_kwargs:
                    stats["rows_without_reasoning"] += 1
                if any(m.tool_calls for m in sample.messages):
                    stats["rows_with_tool_calls"] += 1
                    if sample.tools is None:
                        stats["rows_missing_tools"] += 1
                if (sample.metadata or {}).get("tools_source") == "episode":
                    stats["rows_with_recorded_tools"] += 1
                writer.add(sample.to_parquet_row())
                n_added += 1
    except CurationError as exc:
        raise SystemExit(f"FAILED: {exc}") from exc
    n_written = writer.n_written

    print("\n=== summary ===")
    print(f"attempts selected  : {n_read}")
    print(f"rows written       : {n_written} -> {output_path}")
    print(f"assistant turns    : {stats['assistant_turns']}")
    print(f"rows with a reasoning-less turn (enable_thinking=false): {stats['rows_without_reasoning']}")
    print(f"rows with structured tool calls: {stats['rows_with_tool_calls']} (tool schemas recorded on the episode: {stats['rows_with_recorded_tools']})")
    if skipped:
        print("skipped (could not be made contract-valid):")
        for reason, count in skipped.most_common():
            print(f"  {reason:<34} {count}")
    if n_written == 0:
        raise SystemExit("FAILED: no rows written")

    # Warn only when it actually matters: rows that call tools but carry no schemas
    # render a system prompt the policy never saw - for Qwen3.5 that drops the whole
    # <function=...> call-format instruction while still training the calls themselves.
    # Rows with no tool calls at all are supposed to have tools=null.
    if stats["rows_missing_tools"]:
        print(
            f"\nWARNING: {stats['rows_missing_tools']} row(s) contain tool calls but carry no tool schemas.\n"
            "         The episode recorded none (a run older than trace_converter's request_tools)\n"
            "         and no --tools was given, so the rendered system prompt will be missing the\n"
            "         tool block the policy saw at inference.",
            file=sys.stderr,
        )

    if args.check:
        print(f"\nvalidating {output_path} ...")
        problems, check_stats = check_contract(output_path, batch_size=args.batch_size)
        print(
            f"  rows {check_stats['rows']}, assistant turns {check_stats['assistant_turns']}"
            f" (without reasoning: {check_stats['turns_without_reasoning']}),"
            f" rows with tools {check_stats['rows_with_tools']},"
            f" non-thinking rows {check_stats['rows_non_thinking']}"
        )
        if problems:
            for problem in problems:
                print(f"  INVALID: {problem}")
            raise SystemExit(f"FAILED: {output_path} does not satisfy the contract")
        print("  OK: output satisfies the SFT parquet contract")

    print(f"\nnext: python recipe/sft/scripts/filter_sft_parquet.py {output_path}")


if __name__ == "__main__":
    main()
