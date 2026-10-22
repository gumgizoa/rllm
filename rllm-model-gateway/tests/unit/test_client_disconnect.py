"""A client that gives up on a turn must not leave its upstream call running.

An agent with a request timeout (openhands-sdk: 300 s, then retries) closes its
connection and resends the turn. If the gateway kept waiting on the upstream
call, every abandoned call would keep generating on vLLM and the queue would
grow faster than it drains. These tests run the gateway and an upstream on real
sockets, so a client timeout is a real disconnect on both hops.
"""

import asyncio
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from rllm_model_gateway import GatewayConfig, create_app

from tests.helpers.mock_vllm import MOCK_RESPONSE, _reserve_local_port, stream_chunks


def _abort_aware_upstream(delay: float, headers_first: bool = False) -> FastAPI:
    """Answers after ``delay`` s; stops early and counts an abort if the caller hangs up (as vLLM does).

    By default a streaming request waits the ``delay`` *before* its response
    headers. With ``headers_first`` it sends the headers at once and waits
    before the first chunk instead -- what vLLM does with a streaming request
    queued behind others.
    """
    app = FastAPI()
    app.state.completed = 0
    app.state.aborted = 0

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        body = await request.json()
        if headers_first and body.get("stream"):

            async def queued_then_streamed():
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    app.state.aborted += 1
                    raise
                app.state.completed += 1
                for chunk in stream_chunks():
                    yield chunk

            return StreamingResponse(queued_then_streamed(), media_type="text/event-stream")
        deadline = time.monotonic() + delay
        while time.monotonic() < deadline:
            if await request.is_disconnected():
                app.state.aborted += 1
                return JSONResponse(status_code=499, content={})
            await asyncio.sleep(0.02)
        app.state.completed += 1
        if body.get("stream"):
            return StreamingResponse(stream_chunks(), media_type="text/event-stream")
        return JSONResponse(content=MOCK_RESPONSE)

    return app


class _Server:
    def __init__(self, app):
        self.app = app
        self.port = _reserve_local_port("127.0.0.1")
        self._server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="error"))
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        self._thread.start()
        deadline = time.time() + 5.0
        while not self._server.started:
            if time.time() > deadline:
                raise RuntimeError("server failed to start")
            time.sleep(0.05)
        return self

    def __exit__(self, *exc):
        self._server.should_exit = True
        self._thread.join(timeout=5.0)


def _gateway(upstream_url: str) -> _Server:
    config = GatewayConfig(
        store_worker="memory",
        workers=[{"url": f"{upstream_url}/v1", "worker_id": "w0"}],
        health_check_interval=999,
        sync_traces=True,
    )
    return _Server(create_app(config))


async def _active_requests(gateway_url: str) -> int:
    """Worker slots the gateway still holds (released once a call ends or is cancelled)."""
    async with httpx.AsyncClient(base_url=gateway_url, timeout=5.0) as client:
        workers = (await client.get("/admin/workers")).json()
    return sum(w.get("active_requests", 0) for w in workers)


async def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


@pytest.mark.asyncio
async def test_client_timeout_cancels_the_upstream_call_and_keeps_no_trace():
    upstream_app = _abort_aware_upstream(delay=10.0)
    with _Server(upstream_app) as upstream, _gateway(upstream.url) as gateway:
        async with httpx.AsyncClient(base_url=gateway.url, timeout=0.5) as client:
            with pytest.raises(httpx.ReadTimeout):
                await client.post("/sessions/gone/v1/chat/completions", json={"model": "m", "messages": [{"role": "user", "content": "hi"}]})
        assert await _wait_for(lambda: upstream_app.state.aborted == 1), "upstream call kept running after the client left"
        assert upstream_app.state.completed == 0
        assert await _active_requests(gateway.url) == 0
        async with httpx.AsyncClient(base_url=gateway.url, timeout=5.0) as client:
            traces = (await client.get("/sessions/gone/traces")).json()
        assert traces == []  # the client never received this turn


@pytest.mark.asyncio
async def test_client_timeout_before_the_stream_headers_cancels_it():
    """Until the upstream's headers arrive the handler is still running, out of Starlette's reach.

    vLLM sends them at once, so this guards an upstream that holds them back.
    """
    upstream_app = _abort_aware_upstream(delay=10.0)
    with _Server(upstream_app) as upstream, _gateway(upstream.url) as gateway:
        async with httpx.AsyncClient(base_url=gateway.url, timeout=0.5) as client:
            with pytest.raises(httpx.ReadTimeout):
                payload = {"model": "m", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
                async with client.stream("POST", "/sessions/no-headers/v1/chat/completions", json=payload) as resp:
                    await resp.aread()
        assert await _wait_for(lambda: upstream_app.state.aborted == 1), "streaming call kept running after the client left"
        assert upstream_app.state.completed == 0
        assert await _active_requests(gateway.url) == 0


@pytest.mark.asyncio
async def test_client_timeout_on_a_queued_stream_cancels_it():
    """The vLLM shape: headers at once, then nothing while queued. Starlette cancels the returned stream."""
    upstream_app = _abort_aware_upstream(delay=10.0, headers_first=True)
    with _Server(upstream_app) as upstream, _gateway(upstream.url) as gateway:
        async with httpx.AsyncClient(base_url=gateway.url, timeout=0.5) as client:
            with pytest.raises(httpx.ReadTimeout):
                payload = {"model": "m", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
                async with client.stream("POST", "/sessions/queued/v1/chat/completions", json=payload) as resp:
                    assert resp.status_code == 200
                    await resp.aread()
        assert await _wait_for(lambda: upstream_app.state.aborted == 1), "queued streaming call kept running after the client left"
        assert upstream_app.state.completed == 0
        assert await _active_requests(gateway.url) == 0


@pytest.mark.asyncio
async def test_a_streaming_client_that_waits_gets_its_stream():
    upstream_app = _abort_aware_upstream(delay=0.3)
    with _Server(upstream_app) as upstream, _gateway(upstream.url) as gateway:
        async with httpx.AsyncClient(base_url=gateway.url, timeout=10.0) as client:
            payload = {"model": "m", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
            async with client.stream("POST", "/sessions/streams/v1/chat/completions", json=payload) as resp:
                assert resp.status_code == 200
                text = (await resp.aread()).decode()
        assert "data: [DONE]" in text
        assert upstream_app.state.completed == 1 and upstream_app.state.aborted == 0
        assert await _active_requests(gateway.url) == 0


@pytest.mark.asyncio
async def test_a_client_that_waits_gets_the_answer_and_its_trace():
    upstream_app = _abort_aware_upstream(delay=0.3)
    with _Server(upstream_app) as upstream, _gateway(upstream.url) as gateway:
        async with httpx.AsyncClient(base_url=gateway.url, timeout=10.0) as client:
            resp = await client.post("/sessions/stays/v1/chat/completions", json={"model": "m", "messages": [{"role": "user", "content": "hi"}]})
            assert resp.status_code == 200
            traces = (await client.get("/sessions/stays/traces")).json()
        assert upstream_app.state.completed == 1 and upstream_app.state.aborted == 0
        assert len(traces) == 1


@pytest.mark.asyncio
async def test_abandoned_retries_do_not_pile_up_upstream():
    """The failure mode itself: a client that times out and resends, three times."""
    upstream_app = _abort_aware_upstream(delay=10.0)
    with _Server(upstream_app) as upstream, _gateway(upstream.url) as gateway:
        async with httpx.AsyncClient(base_url=gateway.url, timeout=0.3) as client:
            for _ in range(3):
                with pytest.raises(httpx.ReadTimeout):
                    await client.post("/sessions/retry/v1/chat/completions", json={"model": "m", "messages": [{"role": "user", "content": "hi"}]})
        assert await _wait_for(lambda: upstream_app.state.aborted == 3), f"aborted={upstream_app.state.aborted}"
        assert upstream_app.state.completed == 0
        assert await _active_requests(gateway.url) == 0
