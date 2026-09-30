#!/usr/bin/env python3
"""First-turn probe: does the model open /ai-dlc/core-workflow.md before anything else?

Reproduces turn 1 of the openhands-sdk conversation as the trained arm sees it -- the SDK
1.42.1 system prompt with the AI-DLC ``<PROBLEM_SOLVING_WORKFLOW>`` section, the five tool
schemas, and the user message the harness builds -- and samples it against any
OpenAI-compatible endpoint. One request per (arrangement, task, sample); nothing is executed.

Arrangements (``--arrangements``), ``<task template>+<aidlc position>``:

    skyrl+suffix   run 2's prompt: SkyRL's six-step procedure, AI-DLC pointer appended
    skyrl+prefix   same task text, AI-DLC pointer first
    aidlc+suffix   task text without the six steps (prepare_swegym --instruction aidlc), pointer appended
    aidlc+prefix   the new default arrangement
    skyrl+none     no AI-DLC pointer in the user message (system prompt still carries it)

What is counted, from the tool calls of the sampled turn:

    entry          a call that opens /ai-dlc/core-workflow.md (file_editor view, or cat/head/less/sed on it)
    touch          any call naming /ai-dlc (find, ls, view of the directory ...)
    repo_search    a find/grep for "workflow" or "core-workflow" that does not name /ai-dlc
                   (run 2's typical miss: looking for the document inside /testbed)
    repo           any other repository action
    no_tool        a text-only turn

In run 2 only 9 of 2,849 rollouts opened the document on turn 1 and 13.8% ever did, so the
turn-1 entry rate is a strict but informative proxy; a rollout that enters late also tends
to abandon the workflow within a few turns (reports/2026-09-30_aidlc_swegym_compliance.md).

Fixtures (``aidlc_entry_probe/``): the system prompt as rendered inside a run-2 sandbox
(identical across tasks) and the tool schemas dumped from the agent image. Re-extract both
when ``SDK_VERSION`` changes.

Usage::

    python recipe/grpo/qwen3_5/scripts/aidlc_entry_probe.py --base-url http://HOST:PORT/v1 \\
        --parquet /path/to/SkyRL-v0-293-data/train.parquet --n-tasks 20 --samples 8

    # or from materialized task dirs (uses their instruction.md as the skyrl template):
    ... --tasks-dir $RLLM_HOME/datasets/swegym293

Only the standard library is needed unless ``--parquet`` is given (pyarrow).
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECIPE = HERE.parent
FIXTURES = HERE / "aidlc_entry_probe"
DEFAULT_SYSTEM_PROMPT = FIXTURES / "system_prompt_sdk1.42.1_rendered.txt"
DEFAULT_TOOLS = FIXTURES / "tools_sdk1.42.1.json"
DEFAULT_INSTRUCTION = RECIPE / "aidlc" / "instruction.md"

ARRANGEMENTS = ["skyrl+suffix", "skyrl+prefix", "aidlc+suffix", "aidlc+prefix", "skyrl+none"]
CORE_RE = re.compile(r"/ai-dlc/core-workflow\.md")
READ_VERB_RE = re.compile(r"\b(cat|head|less|more|sed|awk|bat|tail)\b")
WORKFLOW_SEARCH_RE = re.compile(r"\b(find|grep|rg|locate|ls)\b.*\b(workflow|core-workflow|rule-details|ai-dlc)\b", re.I | re.S)


def load_prepare():
    import importlib.util

    spec = importlib.util.spec_from_file_location("prepare_swegym_probe", HERE / "prepare_swegym.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_tasks(args) -> list[dict]:
    """[{id, skyrl, aidlc}]: the two task templates rendered per instance."""
    prepare = load_prepare()
    tasks = []
    if args.parquet:
        for inst in prepare.read_instances(Path(args.parquet)):
            tasks.append({"id": inst["instance_id"], "skyrl": prepare.render_instruction(inst, "skyrl"), "aidlc": prepare.render_instruction(inst, "aidlc")})
    elif args.tasks_dir:
        for d in sorted(Path(args.tasks_dir).iterdir()):
            f = d / "instruction.md"
            if not f.is_file():
                continue
            skyrl = f.read_text(encoding="utf-8")
            m = re.search(r"<issue_description>\n(.*?)\n</issue_description>", skyrl, re.S)
            inst = {"problem_statement": m.group(1) if m else skyrl, "base_commit": "unknown"}
            tasks.append({"id": d.name, "skyrl": skyrl, "aidlc": prepare.render_instruction(inst, "aidlc")})
    else:
        sys.exit("give --parquet or --tasks-dir")
    if not tasks:
        sys.exit("no tasks found")
    rng = random.Random(args.seed)
    rng.shuffle(tasks)
    return tasks[: args.n_tasks] if args.n_tasks > 0 else tasks


def compose(task_text: str, pointer: str, position: str) -> str:
    if position == "none" or not pointer:
        return task_text.strip()
    if position == "prefix":
        return f"{pointer}\n\n{task_text.strip()}"
    return f"{task_text.rstrip()}\n\n{pointer}"


def post_json(url: str, payload: dict, api_key: str | None, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str, api_key: str | None, timeout: float) -> dict:
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def tool_calls(message: dict) -> list[tuple[str, dict]]:
    out = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        raw = fn.get("arguments")
        try:
            args = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except json.JSONDecodeError:
            args = {"_raw": raw}
        out.append((fn.get("name") or "?", args if isinstance(args, dict) else {"_raw": args}))
    return out


def classify(calls: list[tuple[str, dict]]) -> str:
    if not calls:
        return "no_tool"
    labels = []
    for name, a in calls:
        cmd = str(a.get("command") or "")
        path = str(a.get("path") or "")
        text = f"{cmd} {path}"
        if name == "file_editor" and a.get("command") == "view" and CORE_RE.search(path):
            labels.append("entry")
        elif name == "terminal" and CORE_RE.search(cmd) and READ_VERB_RE.search(cmd):
            labels.append("entry")
        elif "/ai-dlc" in text or "ai-dlc" in text:
            labels.append("touch")
        elif name == "terminal" and WORKFLOW_SEARCH_RE.search(cmd):
            labels.append("repo_search")
        elif name in ("think", "task_tracker", "finish"):
            labels.append("meta")
        else:
            labels.append("repo")
    for lab in ("entry", "touch", "repo_search", "repo", "meta"):
        if lab in labels:
            return lab
    return "no_tool"


def describe(calls: list[tuple[str, dict]]) -> str:
    parts = []
    for name, a in calls[:2]:
        if name == "terminal":
            parts.append(f"terminal: {str(a.get('command') or '')[:90]}")
        elif name == "file_editor":
            parts.append(f"file_editor {a.get('command')}: {str(a.get('path') or '')[:80]}")
        else:
            parts.append(name)
    return " ;; ".join(parts).replace("\n", " | ")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True, help="OpenAI-compatible base URL, e.g. http://host:8007/v1")
    ap.add_argument("--model", default=None, help="Model id; default: the first entry of GET /models")
    ap.add_argument("--api-key", default=None)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--parquet", default=None, help="SkyRL-v0-293-data train.parquet or validation.parquet (needs pyarrow)")
    src.add_argument("--tasks-dir", default=None, help="Materialized dataset dir with <instance_id>/instruction.md")
    ap.add_argument("--n-tasks", type=int, default=20)
    ap.add_argument("--samples", type=int, default=8, help="Samples per (arrangement, task)")
    ap.add_argument("--arrangements", default="skyrl+suffix,aidlc+prefix", help=f"Comma list from {ARRANGEMENTS}")
    ap.add_argument("--instruction-file", default=str(DEFAULT_INSTRUCTION), help="The AI-DLC pointer text (aidlc/instruction.md)")
    ap.add_argument("--system-prompt", default=str(DEFAULT_SYSTEM_PROMPT))
    ap.add_argument("--tools", default=str(DEFAULT_TOOLS))
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--think", action="store_true", help="Leave thinking on (the recipe trains no-think)")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None, help="JSONL of every sampled turn (default: ./aidlc_entry_probe_<ts>.jsonl)")
    ap.add_argument("--show", type=int, default=3, help="Example first calls to print per arrangement and label")
    args = ap.parse_args()

    arrangements = [a.strip() for a in args.arrangements.split(",") if a.strip()]
    bad = [a for a in arrangements if a not in ARRANGEMENTS]
    if bad:
        sys.exit(f"unknown arrangement(s) {bad}; choose from {ARRANGEMENTS}")

    base = args.base_url.rstrip("/")
    model = args.model
    if model is None:
        models = get_json(f"{base}/models", args.api_key, args.timeout)
        model = models["data"][0]["id"]
        print(f"model: {model}", file=sys.stderr)

    system_prompt = Path(args.system_prompt).read_text(encoding="utf-8")
    tools = json.loads(Path(args.tools).read_text(encoding="utf-8"))
    pointer = Path(args.instruction_file).read_text(encoding="utf-8").strip() if args.instruction_file not in (None, "", "null") else ""
    tasks = load_tasks(args)
    out_path = Path(args.out) if args.out else Path(f"aidlc_entry_probe_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")

    jobs = []
    for arr in arrangements:
        tmpl, pos = arr.split("+")
        for t in tasks:
            user = compose(t[tmpl], pointer, pos)
            for k in range(args.samples):
                jobs.append((arr, t["id"], k, user))
    print(f"{len(jobs)} requests: {len(arrangements)} arrangements x {len(tasks)} tasks x {args.samples} samples", file=sys.stderr)

    def run(job):
        arr, tid, k, user = job
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user}],
            "tools": tools,
            "temperature": args.temperature,
            "top_p": args.top_p,
            "max_tokens": args.max_tokens,
            "chat_template_kwargs": {"enable_thinking": bool(args.think)},
        }
        t0 = time.time()
        try:
            resp = post_json(f"{base}/chat/completions", payload, args.api_key, args.timeout)
            msg = (resp.get("choices") or [{}])[0].get("message") or {}
            calls = tool_calls(msg)
            return {"arrangement": arr, "task": tid, "sample": k, "label": classify(calls), "calls": [{"name": n, "args": a} for n, a in calls], "content": (msg.get("content") or "")[:400], "latency_s": round(time.time() - t0, 2)}
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            return {"arrangement": arr, "task": tid, "sample": k, "label": "error", "error": str(e)[:300], "calls": [], "content": ""}

    results = []
    with cf.ThreadPoolExecutor(max_workers=args.concurrency) as ex, out_path.open("w", encoding="utf-8") as fh:
        for i, rec in enumerate(ex.map(run, jobs), 1):
            results.append(rec)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if i % 20 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)}", file=sys.stderr)

    labels = ["entry", "touch", "repo_search", "repo", "meta", "no_tool", "error"]
    print(f"\n{'arrangement':<14}{'n':>5}" + "".join(f"{lab:>13}" for lab in labels))
    for arr in arrangements:
        rs = [r for r in results if r["arrangement"] == arr]
        c = collections.Counter(r["label"] for r in rs)
        n = len(rs) or 1
        print(f"{arr:<14}{len(rs):>5}" + "".join(f"{c[lab] / n:>12.1%} " for lab in labels))
    print("\nentry = opens /ai-dlc/core-workflow.md in the first turn; touch = names /ai-dlc without opening it;")
    print("repo_search = looks for the workflow inside the repository; repo = starts on the repository instead.")
    if args.show > 0:
        for arr in arrangements:
            print(f"\n[{arr}] examples")
            for lab in ("entry", "touch", "repo_search", "repo"):
                ex_ = [r for r in results if r["arrangement"] == arr and r["label"] == lab][: args.show]
                for r in ex_:
                    print(f"  {lab:<12} {r['task'][:28]:<30} {describe([(c['name'], c['args']) for c in r['calls']])}")
    print(f"\nraw turns: {out_path}")


if __name__ == "__main__":
    main()
