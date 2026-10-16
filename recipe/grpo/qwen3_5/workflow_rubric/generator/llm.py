"""Model backends for the generator's LLM stages, behind a content-addressed cache.

The rubric is committed together with the cache of every model answer that produced it, so the
build is reproducible without a model (``--llm cache-only``; CI and G9 run that way) and a changed
prompt, input, schema, model or CLI version is a cache miss rather than a silently reused answer.
The key is ``sha256(prompt + input + schema + model + backend version + salt)``; ``salt`` separates
independent samples of the same question (G5 asks three times, G7 once per round).

Backends:

``claude-cli``     ``claude -p --model <id> --tools "" --system-prompt <prompt> --output-format json
                   --json-schema <schema> --no-session-persistence`` with the input on stdin, run in an
                   empty scratch directory (no tools, no project context, no session left behind). The
                   JSON envelope's ``structured_output`` is the answer (``result`` holds its text).
``openai://h:p/m`` an OpenAI-compatible ``/v1/chat/completions`` endpoint via urllib, with a
                   ``json_schema`` response format (``openai+https://`` for TLS).
``cache-only``     answers only from the cache; a miss raises :class:`CacheMiss`.
``none``           no model at all: the LLM stages are skipped (``Pipeline`` checks ``enabled``).

Answers are validated against the schema (a small subset validator, no new dependency); a reply
that does not validate is retried, then raised as :class:`LLMError`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .config import DEFAULT_MODEL

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The backend failed or kept answering outside the schema."""


class CacheMiss(LLMError):
    """``cache-only`` mode and the question was never asked."""


class Backend(Protocol):
    name: str
    model: str

    def version(self) -> str: ...

    def call(self, system: str, user: str, schema: dict) -> tuple[Any, dict]:
        """Return (answer, meta). ``meta`` may hold cost_usd, duration_ms."""
        ...


# ----------------------------------------------------------------------------------------------
@dataclass
class ClaudeCLI:
    model: str = DEFAULT_MODEL
    bin: str | None = None
    max_budget_usd: float | None = None
    timeout: int = 900
    scratch: str | None = None
    name: str = "claude-cli"
    _version: str | None = field(default=None, repr=False)

    def exe(self) -> str:
        # the first of (explicit, WFR_CLAUDE_BIN) that exists here; a configured path missing on this machine
        # yields to the env var, and only when neither is set does PATH decide (an old PATH claude may lack the model)
        env = os.environ.get("WFR_CLAUDE_BIN")
        b = next((c for c in (self.bin, env) if c and Path(c).is_file()), None) or self.bin or env or shutil.which("claude")
        if not b:
            raise LLMError("claude CLI not found (set llm.claude_bin or WFR_CLAUDE_BIN)")
        return b

    def version(self) -> str:
        if self._version is None:
            try:
                out = subprocess.run([self.exe(), "--version"], capture_output=True, text=True, timeout=60).stdout
            except (OSError, subprocess.SubprocessError) as e:
                raise LLMError(f"claude --version failed: {e}") from None
            m = re.search(r"\d+\.\d+\.\d+", out)
            self._version = m.group(0) if m else out.strip() or "unknown"
        return self._version

    def command(self, system: str, schema: dict) -> list[str]:
        cmd = [
            self.exe(), "-p", "--model", self.model, "--tools", "", "--system-prompt", system, "--output-format", "json",
            "--json-schema", json.dumps(schema, separators=(",", ":")), "--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands",
        ]  # fmt: skip
        if self.max_budget_usd:
            cmd += ["--max-budget-usd", str(self.max_budget_usd)]
        return cmd

    def call(self, system: str, user: str, schema: dict) -> tuple[Any, dict]:
        root = self.scratch or tempfile.gettempdir()
        Path(root).mkdir(parents=True, exist_ok=True)
        cwd = tempfile.mkdtemp(prefix="wfr-gen-", dir=root)
        t0 = time.monotonic()
        try:
            p = subprocess.run(self.command(system, schema), input=user, capture_output=True, text=True, cwd=cwd, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise LLMError(f"claude -p timed out after {self.timeout}s") from None
        finally:
            shutil.rmtree(cwd, ignore_errors=True)
        return parse_envelope(p.stdout, p.returncode, p.stderr, time.monotonic() - t0)


def parse_envelope(stdout: str, returncode: int = 0, stderr: str = "", wall: float = 0.0) -> tuple[Any, dict]:
    """``claude -p --output-format json`` envelope -> (structured answer, meta)."""
    try:
        env = json.loads(stdout.strip().splitlines()[-1] if stdout.strip() else "")
    except (ValueError, IndexError):
        raise LLMError(f"claude -p: no JSON envelope (rc={returncode}): {stderr.strip()[:300] or stdout[:300]}") from None
    meta = {"cost_usd": env.get("total_cost_usd"), "duration_ms": env.get("duration_ms"), "wall_s": round(wall, 2), "num_turns": env.get("num_turns")}
    if env.get("is_error") or env.get("subtype") not in (None, "success"):
        raise LLMError(f"claude -p error: {str(env.get('result'))[:400]}")
    ans = env.get("structured_output")
    if ans is None:
        ans = _loads_lenient(env.get("result") or "")
    return ans, meta


@dataclass
class OpenAICompat:
    url: str
    model: str
    timeout: int = 900
    name: str = "openai"

    @classmethod
    def from_spec(cls, spec: str, timeout: int = 900) -> OpenAICompat:
        m = re.fullmatch(r"openai(\+https)?://([^/]+)/(.+)", spec)
        if not m:
            raise LLMError(f"bad openai backend spec {spec!r}; expected openai://host:port/model")
        scheme = "https" if m.group(1) else "http"
        return cls(url=f"{scheme}://{m.group(2)}/v1/chat/completions", model=m.group(3), timeout=timeout)

    def version(self) -> str:
        return f"openai-compatible@{self.url}"

    def call(self, system: str, user: str, schema: dict) -> tuple[Any, dict]:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.7,
            "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}},
        }
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', 'EMPTY')}"})
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                d = json.loads(r.read().decode())
        except (OSError, ValueError) as e:
            raise LLMError(f"{self.url}: {e}") from None
        try:
            text = d["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"{self.url}: unexpected reply {str(d)[:300]}") from None
        return _loads_lenient(text), {"wall_s": round(time.monotonic() - t0, 2), "usage": d.get("usage")}


@dataclass
class NoBackend:
    model: str = ""
    name: str = "none"

    def version(self) -> str:
        return ""

    def call(self, system: str, user: str, schema: dict) -> tuple[Any, dict]:
        raise LLMError("no LLM backend configured (--llm none)")


# ----------------------------------------------------------------------------------------------
class LLM:
    """A backend plus the cache. ``mode``: ``use`` (read, then ask and write), ``only`` (cache-only), ``refresh`` (always ask)."""

    def __init__(self, backend, cache_dir: str | Path, mode: str = "use", retries: int = 2, max_total_usd: float | None = None):
        self.backend = backend
        self.cache_dir = Path(cache_dir)
        self.mode = mode
        self.retries = retries
        self.max_total_usd = max_total_usd  # no new model call once this much was spent (answers already cached stay free)
        self.calls = 0
        self.hits = 0
        self.cost = 0.0
        self._version: str | None = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.backend.name != "none"

    @property
    def version(self) -> str:
        if self._version is None:
            if self.mode == "only":
                info = self._backend_info()
                self._version = info.get("version", "")
                if not getattr(self.backend, "model", "") and info.get("model"):
                    self.backend.model = info["model"]
            else:
                self._version = self.backend.version()
        return self._version

    def describe(self) -> dict:
        return {"backend": self.backend.name, "model": getattr(self.backend, "model", ""), "cli": self.version if self.enabled else ""}

    def key(self, prompt: str, user: str, schema: dict, salt: str = "") -> str:
        h = hashlib.sha256()
        for part in (prompt, user, json.dumps(schema, sort_keys=True), getattr(self.backend, "model", ""), self.version, salt):
            h.update(part.encode())
            h.update(b"\x00")
        return h.hexdigest()

    def ask(self, prompt: str, user: str, schema: dict, salt: str = "") -> Any:
        """The answer to (prompt, user) under ``schema``, from the cache when possible."""
        if not self.enabled:
            raise LLMError("LLM disabled")
        k = self.key(prompt, user, schema, salt)
        path = self.cache_dir / k[:2] / f"{k}.json"
        if self.mode != "refresh" and path.is_file():
            try:
                rec = json.loads(path.read_text())
                if not validate(rec["answer"], schema):
                    with self._lock:
                        self.hits += 1
                    return rec["answer"]
            except (OSError, ValueError, KeyError):
                pass
        if self.mode == "only":
            raise CacheMiss(f"cache miss {k[:12]} (cache-only mode)")
        last = ""
        for attempt in range(self.retries + 1):
            if self.max_total_usd is not None and self.cost >= self.max_total_usd:
                raise LLMError(f"total LLM budget spent (${self.cost:.2f} >= ${self.max_total_usd:.2f}): no further model calls")
            ans, meta = self.backend.call(prompt, user, schema)
            with self._lock:
                self.calls += 1
                self.cost += float(meta.get("cost_usd") or 0.0)
            errs = validate(ans, schema)
            if not errs:
                self._write(path, k, prompt, user, schema, salt, ans, meta)
                # the answer as a cache read returns it (keys sorted): later prompts built from it (G7 refute /
                # conflicts dump item params) must be the same in this run and in a cache-only rebuild
                return json.loads(json.dumps(ans, sort_keys=True))
            last = "; ".join(errs[:5])
            logger.warning("LLM answer failed the schema (attempt %d): %s", attempt + 1, last)
        raise LLMError(f"answer kept failing the schema: {last}")

    def ask_many(self, jobs: list[tuple[str, str, dict, str]], parallel: int = 1) -> list[Any]:
        """``ask`` for each (prompt, user, schema, salt), up to ``parallel`` in flight; results in job order,
        an :class:`LLMError` in place of the answer of a job that failed (callers log and skip it)."""
        if not jobs:
            return []
        _ = self.version  # resolve once, before threads share it

        def one(job):
            try:
                return self.ask(*job)
            except LLMError as e:
                return e

        if parallel <= 1 or len(jobs) == 1:
            return [one(j) for j in jobs]
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=min(parallel, len(jobs))) as ex:
            return list(ex.map(one, jobs))

    def _write(self, path: Path, k: str, prompt: str, user: str, schema: dict, salt: str, ans, meta: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "key": k,
            "backend": self.backend.name,
            "model": getattr(self.backend, "model", ""),
            "version": self.version,
            "salt": salt,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "input_sha256": hashlib.sha256(user.encode()).hexdigest(),
            "schema_sha256": hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest(),
            "answer": ans,
            "meta": {**meta, "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")},
        }
        path.write_text(json.dumps(rec, indent=1, ensure_ascii=False, sort_keys=True))
        info = self.cache_dir / "backend.json"
        try:
            info.write_text(json.dumps({"backend": self.backend.name, "model": getattr(self.backend, "model", ""), "version": self.version}, indent=1))
        except OSError:
            pass

    def _backend_info(self) -> dict:
        try:
            return json.loads((self.cache_dir / "backend.json").read_text())
        except (OSError, ValueError):
            return {}


def make(
    spec: str, cache_dir: str | Path, model: str = DEFAULT_MODEL, claude_bin: str | None = None, max_budget_usd: float | None = None, timeout: int = 900, retries: int = 2, scratch: str | None = None
) -> LLM:
    """``claude-cli`` | ``openai://host:port/model`` | ``cache-only`` | ``refresh:<spec>`` | ``none``."""
    mode = "use"
    if spec.startswith("refresh:"):
        mode, spec = "refresh", spec[len("refresh:") :]
    if spec == "none":
        return LLM(NoBackend(), cache_dir, mode)
    if spec == "cache-only":
        info = {}
        try:
            info = json.loads((Path(cache_dir) / "backend.json").read_text())
        except (OSError, ValueError):
            pass
        be = NoCallBackend(name=info.get("backend", "claude-cli"), model=info.get("model", model))
        return LLM(be, cache_dir, "only", retries)
    if spec.startswith("openai"):
        return LLM(OpenAICompat.from_spec(spec, timeout), cache_dir, mode, retries)
    if spec == "claude-cli":
        return LLM(ClaudeCLI(model=model, bin=claude_bin, max_budget_usd=max_budget_usd, timeout=timeout, scratch=scratch), cache_dir, mode, retries)
    raise LLMError(f"unknown --llm {spec!r}")


@dataclass
class NoCallBackend:
    """Stands for the backend that filled the cache; never called."""

    name: str = "claude-cli"
    model: str = ""

    def version(self) -> str:
        return ""

    def call(self, system: str, user: str, schema: dict) -> tuple[Any, dict]:
        raise CacheMiss("cache-only mode")


# ----------------------------------------------------------------------------------------------
def validate(v: Any, s: dict, path: str = "$") -> list[str]:
    """Errors of ``v`` against a JSON-schema subset: type, required, properties, additionalProperties, items, enum, min/maxItems."""
    errs: list[str] = []
    if not isinstance(s, dict) or not s:
        return errs
    if "anyOf" in s:
        if all(validate(v, sub, path) for sub in s["anyOf"]):
            errs.append(f"{path}: matches no anyOf branch")
        return errs
    t = s.get("type")
    types = t if isinstance(t, list) else [t] if t else []
    if types and not any(_is_type(v, x) for x in types):
        return [f"{path}: expected {t}, got {type(v).__name__}"]
    if "enum" in s and v not in s["enum"]:
        errs.append(f"{path}: {v!r} not in enum")
    if isinstance(v, dict):
        for r in s.get("required", []):
            if r not in v:
                errs.append(f"{path}: missing {r!r}")
        props = s.get("properties", {})
        for k, sub in props.items():
            if k in v:
                errs += validate(v[k], sub, f"{path}.{k}")
        if s.get("additionalProperties") is False:
            errs += [f"{path}: unexpected {k!r}" for k in v if k not in props]
    if isinstance(v, list):
        if "minItems" in s and len(v) < s["minItems"]:
            errs.append(f"{path}: fewer than {s['minItems']} items")
        if "maxItems" in s and len(v) > s["maxItems"]:
            errs.append(f"{path}: more than {s['maxItems']} items")
        if "items" in s:
            for i, x in enumerate(v):
                errs += validate(x, s["items"], f"{path}[{i}]")
    return errs


def _is_type(v: Any, t: str) -> bool:
    return {
        "object": isinstance(v, dict),
        "array": isinstance(v, list),
        "string": isinstance(v, str),
        "integer": isinstance(v, int) and not isinstance(v, bool),
        "number": isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": isinstance(v, bool),
        "null": v is None,
    }.get(t, True)


def _loads_lenient(text: str) -> Any:
    t = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except ValueError:
        a, b = t.find("{"), t.rfind("}")
        if a >= 0 and b > a:
            try:
                return json.loads(t[a : b + 1])
            except ValueError:
                pass
    raise LLMError(f"reply is not JSON: {t[:200]}")
