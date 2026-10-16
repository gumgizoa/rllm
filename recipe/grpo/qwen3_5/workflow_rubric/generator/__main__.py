"""CLI: ``python -m recipe.grpo.qwen3_5.workflow_rubric.generator <command> <workflow> [options]``.

    manifest | parse | templates | extract | ground | critic | build   run the pipeline up to that stage
    check                                                               validate a committed rubric (schema,
                                                                        params, lock vs current files, quotes)
    recall --pilot notes/x.statements.jsonl [--against items|statements] pilot statements covered by line overlap

Options: ``--config`` (default ``workflows/<name>/generator.yaml``), ``--llm claude-cli | openai://host:port/model
| cache-only | none | refresh:<spec>``, ``--out`` (default ``workflows/<name>/reward``), ``--model``, ``--claude-bin``,
``--samples``, ``--force-eval`` (overwrite eval.py), ``--selftest`` (G9 hook). Exit status 1 on problems.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .config import ConfigError, load
from .llm import LLMError, make
from .pipeline import Pipeline

RECIPE = Path(__file__).resolve().parents[2]  # recipe/grpo/qwen3_5
STAGES = ("manifest", "parse", "templates", "extract", "ground", "critic", "build")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m recipe.grpo.qwen3_5.workflow_rubric.generator", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=[*STAGES, "check", "recall"])
    ap.add_argument("workflow")
    ap.add_argument("--config")
    ap.add_argument("--llm")
    ap.add_argument("--out")
    ap.add_argument("--model")
    ap.add_argument("--claude-bin")
    ap.add_argument("--samples", type=int)
    ap.add_argument("--force-eval", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--pilot", nargs="*", default=[])
    ap.add_argument("--against", choices=["items", "statements"], default="items")
    ap.add_argument("-q", "--quiet", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    say = (lambda m: None) if a.quiet else (lambda m: print(m, file=sys.stderr))
    cfg_path = Path(a.config) if a.config else RECIPE / "workflows" / a.workflow / "generator.yaml"
    try:
        cfg = load(cfg_path)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    if cfg.workflow != a.workflow:
        say(f"note: config workflow {cfg.workflow!r} != argument {a.workflow!r}; using the config")
    if a.model:
        cfg.llm.model = a.model
    if a.samples:
        cfg.llm.samples = a.samples
    pkg = cfg_path.resolve().parent
    out = Path(a.out) if a.out else pkg / "reward"
    cache = Path(cfg.llm.cache_dir) if cfg.llm.cache_dir else out / "gen-cache"
    if not cache.is_absolute() and cfg.llm.cache_dir:
        cache = pkg / cache
    spec = a.llm or cfg.llm.backend
    scratch = str(out / "gen-work" / "llm-scratch")
    claude_bin = a.claude_bin or os.environ.get("WFR_CLAUDE_BIN") or cfg.llm.claude_bin
    try:
        llm = make(spec, cache, model=cfg.llm.model, claude_bin=claude_bin, max_budget_usd=cfg.llm.max_budget_usd, timeout=cfg.llm.timeout, retries=cfg.llm.retries, scratch=scratch)
    except LLMError as e:
        print(f"llm error: {e}", file=sys.stderr)
        return 2
    llm.max_total_usd = cfg.llm.max_total_usd
    pipe = Pipeline(cfg, llm, out, say=say)
    try:
        if a.command == "check":
            probs = pipe.check()
            for p in probs:
                print(p)
            say(f"check: {len(probs)} problem(s)")
            return 1 if probs else 0
        if a.command == "recall":
            return _recall(pipe, a)
        stage = a.command
        _ = pipe.manifest
        if stage == "manifest":
            return 0
        _ = pipe.parsed
        if stage == "parse":
            return 0
        _ = pipe.stage_model
        _ = pipe.templates
        if stage == "templates":
            return 0
        _ = pipe.mapped
        if stage == "extract":
            return 0
        _ = pipe.grounded
        if stage == "ground":
            return 0
        _ = pipe.critic
        if stage == "critic":
            return 0
        res = pipe.build(force_eval=a.force_eval, run_selftest=a.selftest)
        print(json.dumps({"paths": res["paths"], "items": res["report"]["n_items"], "by_requirement": res["report"]["by_requirement"], "llm": res["report"]["llm"]}, indent=1))
        if res.get("selftest") and res["selftest"].get("status") == "failed":
            return 1
        return 0
    except LLMError as e:
        print(f"llm error: {e}", file=sys.stderr)
        return 1


def _recall(pipe: Pipeline, a) -> int:
    from . import extract as X
    from .recall import load_pilot, recall

    if not a.pilot:
        print("recall needs --pilot FILE [FILE ...]", file=sys.stderr)
        return 2
    pilot = load_pilot(a.pilot)
    if a.against == "statements":
        path = pipe.work / "statements.jsonl"
        if not path.is_file():
            print(f"{path} missing: run 'extract' first", file=sys.stderr)
            return 2
        targets = [(s.source, int(s.line_start), int(s.line_end)) for s in X.read_jsonl(path)]
    else:
        from .. import schema as S

        rub = S.load(pipe.out / "rubric.yaml")
        # coverage counts only items that score: an unimplemented (weight 0) or log-only item cites a
        # line without checking anything, so it is reported apart, never as recall
        scored = [it for it in rub.items if it.check.kind != "unimplemented" and it.weight > 0 and not it.log_only]
        targets = [(s.doc, s.lines[0], s.lines[1]) for it in scored for s in it.sources]
        every = recall(pilot, [(s.doc, s.lines[0], s.lines[1]) for it in rub.items for s in it.sources], pipe.manifest, show=0)
        rep = recall(pilot, targets, pipe.manifest)
        rep["counted"] = "items with weight > 0 (unimplemented and log-only items excluded)"
        rep["including_unscored"] = {"covered": every["covered"], "recall": every["recall"], "by": every["by"]}
        print(json.dumps(rep, indent=1, ensure_ascii=False))
        return 0
    rep = recall(pilot, targets, pipe.manifest)
    print(json.dumps(rep, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
