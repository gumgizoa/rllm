#!/usr/bin/env python3
"""Benchmark sandbox setup with vs without agent-image mount."""

from __future__ import annotations

import os
import statistics
import sys
import time

from rllm.eval.agent_loader import load_agent
from rllm.hooks import SandboxTaskHooks
from rllm.tasks.loader import BenchmarkLoader


def _run(label: str, mode: str, tasks: list) -> dict[str, float]:
    os.environ["RLLM_AGENT_IMAGE"] = mode
    agent = load_agent("mini-swe-agent")
    hooks = SandboxTaskHooks(sandbox_backend="docker", use_snapshot=False)
    totals: list[float] = []
    creates: list[float] = []
    setups: list[float] = []
    installs: list[float] = []
    for i, task in enumerate(tasks):
        t0 = time.perf_counter()
        ctx = hooks.setup(task, agent, f"bench-{i}")
        try:
            totals.append(time.perf_counter() - t0)
            creates.append(ctx.setup_metrics.get("time/env_create_s", 0.0))
            setups.append(ctx.setup_metrics.get("time/env_setup_s", 0.0))
            installs.append(ctx.setup_metrics.get("time/env_install_s", 0.0))
        finally:
            ctx.run_teardown()
    def _avg(xs: list[float]) -> float:
        return statistics.mean(xs) if xs else 0.0

    return {
        "label": label,
        "mode": mode,
        "total_avg": _avg(totals),
        "create_avg": _avg(creates),
        "setup_avg": _avg(setups),
        "install_avg": _avg(installs),
    }


def main() -> int:
    bench = BenchmarkLoader.load("/root/.rllm/datasets/swebench_pro", sandbox_backend="docker", harness_name="mini-swe-agent")
    tasks = list(bench.tasks)[:3]
    if not tasks:
        print("No tasks found", file=sys.stderr)
        return 1

    rows = [
        _run("without mount (per-task install)", "skip", tasks),
        _run("with agent-image mount", "auto", tasks),
    ]
    print(f"{'mode':<32} {'total':>8} {'create':>8} {'setup':>8} {'install':>8}")
    for row in rows:
        print(
            f"{row['label']:<32} "
            f"{row['total_avg']:7.1f}s "
            f"{row['create_avg']:7.1f}s "
            f"{row['setup_avg']:7.1f}s "
            f"{row['install_avg']:7.1f}s"
        )
    saved = rows[0]["install_avg"]
    if saved > 0:
        pct = 100 * (1 - rows[1]["install_avg"] / saved)
        print(f"\ninstall time reduction: {saved:.1f}s -> {rows[1]['install_avg']:.1f}s ({pct:.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
