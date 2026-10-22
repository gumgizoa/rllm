#!/usr/bin/env python3
"""Write prompt_sha256.json for a prepare_swe_rl.py dataset dir.

GuardedOpenHandsSdkHarness (recipe/data/swe_rl_v1/prompt_guard.py) refuses a
task whose instruction is not the pinned problem_statement; it reads the pins
from <dataset_dir>/prompt_sha256.json. prepare_swe_rl.py writes instruction.md
as the row's problem_statement verbatim, so the pin is its hash.

    python write_prompt_manifest.py $RLLM_HOME/datasets/swe_rl_v2_diff [...]
"""

import json
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from recipe.data.swe_rl_v1.prompt_guard import prompt_sha256  # noqa: E402

for d in map(Path, sys.argv[1:]):
    pins = {}
    for toml in sorted(d.glob("*/task.toml")):
        name = tomllib.loads(toml.read_text())["task"]["name"]
        pins[f"{d.name}/{name}"] = prompt_sha256((toml.parent / "instruction.md").read_text(encoding="utf-8"))
    (d / "prompt_sha256.json").write_text(json.dumps(pins, indent=1, sort_keys=True))
    print(f"{d}: {len(pins)} pins")
