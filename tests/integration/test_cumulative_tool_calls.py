"""Cumulative token mode must hand a tool-calling agent parsed ``tool_calls``.

Turn 1 goes through ``/v1/chat/completions``, where vLLM's own tool parser runs.
Turn 2+ is rewritten to ``/v1/completions`` with raw prompt token ids, and that
endpoint has no reasoning or tool-call parser — so the gateway has to recover the
structure itself, using the same renderer that built the cumulative prompt.
Without that, an agent like mini-swe-agent (whose prompt *requires* a bash tool
call every turn) sees raw ``<tool_call>`` markup as ``content`` and stalls.

Both delivery paths are covered: JSON and SSE. Streaming requests that carry
tools are buffered, because these tool calls are markup that cannot be
recognised from a partial text delta.
"""

import json
import socket
import threading
import time

import pytest

MODEL = "Qwen/Qwen3.5-4B"
RENDERER_FAMILY = "qwen3.6"

TURN1_COMPLETION = "<think>\nLooking around.\n</think>\n\n<tool_call>\n<function=bash>\n<parameter=command>\nls -la\n</parameter>\n</function>\n</tool_call>"
TURN2_REASONING = "Now read the file."
TURN2_COMMAND = "cat setup.py"
TURN2_COMPLETION = f"<think>\n{TURN2_REASONING}\n</think>\n\n<tool_call>\n<function=bash>\n<parameter=command>\n{TURN2_COMMAND}\n</parameter>\n</function>\n</tool_call>"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "run a bash command",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    }
]

pytest.importorskip("renderers", reason="cumulative token mode requires the renderers package")
pytest.importorskip("openai")
pytest.importorskip("uvicorn")


@pytest.fixture(scope="module")
def tokenizer():
    transformers = pytest.importorskip("transformers")
    try:
        return transformers.AutoTokenizer.from_pretrained(MODEL)
    except Exception as e:  # offline CI without the tokenizer cached
        pytest.skip(f"{MODEL} tokenizer unavailable: {e}")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(app, port):
    import uvicorn

    threading.Thread(
        target=uvicorn.run,
        args=(app,),
        kwargs={"host": "127.0.0.1", "port": port, "log_level": "error"},
        daemon=True,
    ).start()


def _wait_healthy(port, timeout=120.0):
    import httpx

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.25)
    raise TimeoutError(f"server on :{port} never became healthy")


def _fake_worker(tokenizer):
    """A vLLM stand-in that answers both endpoints with token ids + logprobs."""
    from fastapi import FastAPI, Request
    from fastapi.responses import StreamingResponse

    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/v1/models")
    async def models():
        return {"object": "list", "data": [{"id": MODEL, "object": "model"}]}

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        rendered = tokenizer.apply_chat_template(
            body["messages"],
            tools=[t["function"] for t in TOOLS],
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
        )
        prompt_ids = list(rendered["input_ids"])
        completion_ids = tokenizer.encode(TURN1_COMPLETION + "<|im_end|>", add_special_tokens=False)
        return {
            "id": "cmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": MODEL,
            "prompt_token_ids": prompt_ids,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "token_ids": completion_ids,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning_content": "Looking around.",
                        "tool_calls": [
                            {
                                "id": "call_a",
                                "type": "function",
                                "function": {"name": "bash", "arguments": '{"command": "ls -la"}'},
                            }
                        ],
                    },
                    "logprobs": {"content": [{"token": "x", "logprob": -0.1} for _ in completion_ids]},
                }
            ],
            "usage": {"prompt_tokens": len(prompt_ids), "completion_tokens": len(completion_ids), "total_tokens": 0},
        }

    @app.post("/v1/completions")
    async def completions(request: Request):
        body = await request.json()
        prompt_ids = body["prompt"]
        completion_ids = tokenizer.encode(TURN2_COMPLETION + "<|im_end|>", add_special_tokens=False)
        payload = {
            "id": "cmpl-2",
            "object": "text_completion",
            "created": 0,
            "model": MODEL,
            "prompt_token_ids": prompt_ids,
            "choices": [
                {
                    "index": 0,
                    "text": tokenizer.decode(completion_ids),
                    "finish_reason": "stop",
                    "token_ids": completion_ids,
                    "logprobs": {
                        "tokens": ["x"] * len(completion_ids),
                        "token_logprobs": [-0.1] * len(completion_ids),
                    },
                }
            ],
            "usage": {"prompt_tokens": len(prompt_ids), "completion_tokens": len(completion_ids), "total_tokens": 0},
        }
        if not body.get("stream"):
            return payload

        def gen():
            yield f"data: {json.dumps(payload)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


@pytest.fixture(scope="module")
def gateway_port(tokenizer):
    from rllm_model_gateway.models import GatewayConfig, WorkerConfig
    from rllm_model_gateway.server import create_app

    worker_port, gw_port = _free_port(), _free_port()
    _serve(_fake_worker(tokenizer), worker_port)
    _wait_healthy(worker_port)

    app = create_app(
        config=GatewayConfig(
            host="127.0.0.1",
            port=gw_port,
            store_worker="memory",
            model=MODEL,
            cumulative_token_mode=True,
            renderer_family=RENDERER_FAMILY,
            # Without this the bridge refuses to extend across a new user
            # message, so there would be no cumulative turn to test.
            renderer_kwargs={"preserve_thinking": True},
            workers=[WorkerConfig(url=f"http://127.0.0.1:{worker_port}")],
        )
    )
    _serve(app, gw_port)
    _wait_healthy(gw_port)
    return gw_port


def _second_turn(gw_port, session, stream):
    """Drive two turns through the gateway; return the second turn's message."""
    import httpx
    from openai import OpenAI

    httpx.post(f"http://127.0.0.1:{gw_port}/sessions/{session}", timeout=10)
    client = OpenAI(base_url=f"http://127.0.0.1:{gw_port}/sessions/{session}/v1", api_key="test")

    messages = [{"role": "user", "content": "fix the bug"}]
    first = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto")
    m1 = first.choices[0].message
    assert m1.tool_calls, "turn 1 lost its tool call — the fake worker or gateway is misconfigured"
    messages.append(
        {
            "role": "assistant",
            "content": m1.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in m1.tool_calls
            ],
        }
    )
    messages.append({"role": "tool", "tool_call_id": m1.tool_calls[0].id, "content": "total 4\nsetup.py"})

    if not stream:
        choice = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto"
        ).choices[0]
        calls = [
            {"name": tc.function.name, "arguments": tc.function.arguments} for tc in (choice.message.tool_calls or [])
        ]
        return choice.message.content or "", getattr(choice.message, "reasoning_content", None) or "", calls, choice.finish_reason

    content, reasoning, finish = "", "", None
    slots: dict[int, dict] = {}
    for event in client.chat.completions.create(
        model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto", stream=True
    ):
        if not event.choices:
            continue
        delta = event.choices[0].delta
        content += delta.content or ""
        reasoning += getattr(delta, "reasoning_content", None) or ""
        for tc in delta.tool_calls or []:
            slot = slots.setdefault(tc.index, {"name": "", "arguments": ""})
            if tc.function:
                slot["name"] += tc.function.name or ""
                slot["arguments"] += tc.function.arguments or ""
        finish = event.choices[0].finish_reason or finish
    return content, reasoning, [slots[i] for i in sorted(slots)], finish


@pytest.mark.parametrize("stream", [False, True], ids=["json", "sse"])
def test_cumulative_turn_returns_parsed_tool_calls(gateway_port, stream):
    content, reasoning, calls, finish_reason = _second_turn(gateway_port, f"tool-{stream}", stream)

    assert "<tool_call>" not in content, f"raw tool-call markup leaked into content: {content!r}"
    assert len(calls) == 1, f"expected one parsed tool call, got {calls}"
    assert calls[0]["name"] == "bash"
    assert json.loads(calls[0]["arguments"]) == {"command": TURN2_COMMAND}
    assert reasoning.strip() == TURN2_REASONING
    assert finish_reason == "tool_calls"
