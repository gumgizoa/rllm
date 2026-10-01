#!/usr/bin/env python3
"""Materialize SkyRL-v0-293-data (SWE-Gym) as native rLLM sandbox benchmarks.

Input: the SkyRL-v0 parquet pair (``train.parquet`` = 293 SWE-Gym instances,
``validation.parquet`` = 23 SWE-bench-style instances), each row carrying the
SWE-bench ``instance`` struct (instance_id, repo, version, base_commit,
problem_statement, test_patch, FAIL_TO_PASS, PASS_TO_PASS, ...).

Output: one Harbor-shaped task directory per instance under
``$RLLM_HOME/datasets/<name>/``, registered in ``DatasetRegistry`` with
``task_path`` rows so ``train.py`` (``as_tasks=True``) and ``rllm eval <name>``
root every Task at its directory::

    <name>/
    ├── dataset.toml
    └── <instance_id>/
        ├── task.toml            # [environment] docker_image + workdir=/testbed, timeouts, resources
        ├── instruction.md       # SkyRL-v0's SWE-Gym prompt (= OpenHands' SWE-bench prompt), paths rewritten to /testbed (--instruction aidlc: without its six-step procedure)
        ├── tests/
        │   ├── test.sh          # verifier entry: runs eval.sh, then grade.py -> /logs/verifier/reward.json
        │   ├── eval.sh          # swegym eval_script (byte-identical; see scripts/swegym_eval.py)
        │   ├── grade.py         # swegym grading rules, stdlib only
        │   ├── instance.json    # F2P / P2P / parser for grade.py
        │   └── evaluate.py      # only with --evaluate-py: hybrid (SWE + IF) verifier, see README
        └── solution/
            ├── gold.patch       # the reference fix
            └── solve.sh         # `rllm eval --agent oracle` applies it

The task image is the pre-built SWE-Gym instance image OpenHands/SkyRL used
(``xingyaoww/sweb.eval.x86_64.<owner>_s_<repo>-<n>:latest``): ``/testbed`` holds the
repo at ``base_commit`` and ``/opt/miniconda3/envs/testbed`` its environment. No
Dockerfile is written, so no per-task ``docker build`` happens; ``[environment]
docker_image`` is what the docker backend runs.

Usage::

    python recipe/grpo/qwen3_5/scripts/prepare_swegym.py \
        --parquet-dir /path/to/SkyRL-v0-293-data
    # -> swegym293/train (293 tasks) and swegym_val23/test (23 tasks)

    # AI-DLC arms: the same tasks without the prompt's six-step procedure in the
    # prompt (it competes with /ai-dlc/core-workflow.md; see INSTRUCTION_TEMPLATE_AIDLC):
    python recipe/grpo/qwen3_5/scripts/prepare_swegym.py \
        --parquet-dir /path/to/SkyRL-v0-293-data --instruction aidlc
    # -> swegym293_aidlc/train and swegym_val23_aidlc/test; point the variant at them with
    #    recipe.train_dataset=swegym293_aidlc recipe.val_dataset=swegym_val23_aidlc

    # Hybrid reward: a Python verifier that gets the live sandbox (rLLM's
    # python-host/hybrid evaluator) and combines the SWE-Gym result with
    # instruction-following signals. Rebuild under a distinct name so a run
    # pointing at swegym293 keeps its task dirs:
    python recipe/grpo/qwen3_5/scripts/prepare_swegym.py \
        --parquet-dir /path/to/SkyRL-v0-293-data --evaluate-py /path/to/evaluate.py \
        --train-name swegym293_hybrid --val-name swegym_val23_hybrid
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swegym_eval  # noqa: E402

TRAIN_NAME = "swegym293"
TRAIN_SPLIT = "train"
VAL_NAME = "swegym_val23"
VAL_SPLIT = "test"

# docker.io/xingyaoww/ is what SkyRL-v0 / OpenHands SWE-Gym eval pulls from
# (EVAL_DOCKER_IMAGE_PREFIX). ``__`` -> ``_s_`` and lower-case, per
# ``get_instance_docker_image`` in OpenHands' swe_bench/run_infer.py.
DEFAULT_IMAGE_PREFIX = "xingyaoww/"

# Wall clock, seconds. Agent: sized for OPENHANDS_MAX_ITERATIONS=30 with a
# thinking 8B policy under 32-way concurrency; the verifier grades whatever
# is in /testbed when it expires. Verifier: pandas' `pip install -ve .
# --no-build-isolation` (incremental meson rebuild) + the test file is the
# slow tail; moto's `make init` re-resolves deps over the network.
AGENT_TIMEOUT_SEC = 3600.0
VERIFIER_TIMEOUT_SEC = 1800.0

# Applied by the docker backend as nano_cpus / mem_limit (Harbor semantics).
# The verifier's test run and the agent's own pytest calls both live under it.
RESOURCES = {"cpus": 4, "memory_mb": 16384}

# The SWE-Gym task prompt SkyRL-v0 trained with: ``get_instruction`` in
# ``verl/workers/agentic/utils.py`` at NovaSky-AI/SkyRL commit a0d50c48 (the
# commit the SkyRL README names for reproducing SkyRL-v0), with
# /workspace/<repo> replaced by the image's /testbed. SkyRL took it verbatim
# from OpenHands' SWE-bench evaluation (``get_instruction`` in
# ``evaluation/benchmarks/swe_bench/run_infer.py``, present from OpenHands
# 0.15 through at least 0.30; the SkyRL and OpenHands 0.30.0 blocks are
# byte-identical), six-step procedure included. The parquet's ``prompt``
# column is the bare problem statement, so this template is what the rollout
# code added at run time.
INSTRUCTION_TEMPLATE = """<uploaded_files>
/testbed
</uploaded_files>

I've uploaded a python code repository in the directory /testbed. Consider the following issue description:

<issue_description>
{problem_statement}
</issue_description>

Can you help me implement the necessary changes to the repository so that the requirements specified in the <issue_description> are met?
I've already taken care of all changes to any of the test files described in the <issue_description>. This means you DON'T have to modify the testing logic or any of the tests in any way!
Also the development Python environment is already set up for you (i.e., all dependencies already installed), so you don't need to install other packages.
Your task is to make the minimal changes to non-test files in the /testbed directory to ensure the <issue_description> is satisfied.

Follow these steps to resolve the issue:

1. EXPLORATION: First, thoroughly explore the repository structure using tools like `find` and `grep`.
   - Identify all files mentioned in the problem statement
   - Locate where the issue occurs in the codebase
   - Understand the surrounding context and dependencies
   - Use `grep` to search for relevant functions, classes, or error messages

2. ANALYSIS: Based on your exploration, think carefully about the problem and propose 2-5 possible approaches to fix the issue.
   - Analyze the root cause of the problem
   - Consider trade-offs between different solutions
   - Select the most promising approach and explain your reasoning

3. TEST CREATION: Before implementing any fix, create a script to reproduce and verify the issue.
   - Look at existing test files in the repository to understand the test format/structure
   - Create a minimal reproduction script that demonstrates the issue
   - Run your script to confirm the error exists

4. IMPLEMENTATION: Edit the source code to implement your chosen solution.
   - Make minimal, focused changes to fix the issue

5. VERIFICATION: Test your implementation thoroughly.
   - Run your reproduction script to verify the fix works
   - Add edge cases to your test script to ensure comprehensive coverage
   - Run existing tests related to the modified code to ensure you haven't broken anything

6. FINAL REVIEW: Carefully re-read the problem description and compare your changes with the base commit {base_commit}.
   - Ensure you've fully addressed all requirements
   - Run any tests in the repository related to:
     * The issue you are fixing
     * The files you modified
     * The functions you changed
   - If any tests fail, revise your implementation until all tests pass

Be thorough in your exploration, testing, and reasoning. It's fine if your thinking process is lengthy - quality and completeness are more important than brevity.
"""

# The same task text for the AI-DLC arm (``--instruction aidlc``). The
# six-step procedure ("Follow these steps": EXPLORATION, ANALYSIS, TEST
# CREATION, IMPLEMENTATION, VERIFICATION, FINAL REVIEW) is dropped: it is a
# second, more detailed workflow for the same job as AI-DLC's five stages, and
# in run 2 (2026-09-29) 86% of rollouts followed it instead of reading
# /ai-dlc/core-workflow.md (reports/2026-09-30_aidlc_swegym_compliance.md).
# The base-commit sha went with step 6; with ``hide_git_history`` the agent
# cannot diff against it anyway. Everything that describes the *task* stays:
# where the repo is, that the tests are already taken care of, that the
# environment is ready, and that the change is minimal and to non-test files.
# ``{base_commit}`` is accepted and ignored so both templates format alike.
INSTRUCTION_TEMPLATE_AIDLC = """<uploaded_files>
/testbed
</uploaded_files>

I've uploaded a python code repository in the directory /testbed. Consider the following issue description:

<issue_description>
{problem_statement}
</issue_description>

Can you help me implement the necessary changes to the repository so that the requirements specified in the <issue_description> are met?
I've already taken care of all changes to any of the test files described in the <issue_description>. This means you DON'T have to modify the testing logic or any of the tests in any way!
Also the development Python environment is already set up for you (i.e., all dependencies already installed), so you don't need to install other packages.
Your task is to make the minimal changes to non-test files in the /testbed directory to ensure the <issue_description> is satisfied.
"""

INSTRUCTION_TEMPLATES = {"skyrl": INSTRUCTION_TEMPLATE, "aidlc": INSTRUCTION_TEMPLATE_AIDLC}

# Verifier entry. Runs in the same container the agent worked in, as root,
# after ShellScriptEvaluator uploaded tests/ to /tests. eval.sh is swegym's
# script: it restores the gold test files, applies the test patch, runs the
# repo's test command and restores the test files again. Its output is what
# grade.py parses. ``timeout`` is the evaluator's job ([verifier] timeout_sec).
TEST_SH = r"""#!/bin/bash
# SWE-Gym verifier (rLLM native path). See prepare_swegym.py for the contract.
set -uo pipefail
mkdir -p /logs/verifier /tmp/rllm
REWARD=/logs/verifier/reward.json
if ! cd /testbed 2>/dev/null; then
    echo '{"reward": 0.0, "is_correct": false, "metadata": {"error": "/testbed missing"}}' > "$REWARD"
    exit 0
fi
git config --global --add safe.directory /testbed >/dev/null 2>&1 || true
chmod +x /tests/eval.sh
# eval.sh has no `set -e` (swegym: keep going so the test files are restored).
bash /tests/eval.sh > /logs/verifier/eval_output.log 2>&1
echo "[verifier] eval.sh exit=$? log=$(wc -c < /logs/verifier/eval_output.log) bytes"
PY=/opt/miniconda3/bin/python
[ -x "$PY" ] || PY=python3
"$PY" /tests/grade.py /logs/verifier/eval_output.log /tests/instance.json "$REWARD" /logs/verifier/report.json \
    || echo '{"reward": 0.0, "is_correct": false, "metadata": {"error": "grade.py failed"}}' > "$REWARD"
cat "$REWARD"
"""

SOLVE_SH = """#!/bin/bash
# Oracle: apply the gold patch. The image already has /testbed at base_commit.
set -e
cd /testbed
git config --global --add safe.directory /testbed 2>/dev/null || true
git apply -v /solution/gold.patch
"""


def image_for(instance_id: str, prefix: str) -> str:
    return f"{prefix.rstrip('/')}/sweb.eval.x86_64.{instance_id.replace('__', '_s_')}:latest".lower()


def toml_str(s: str) -> str:
    return json.dumps(s)  # TOML basic strings share JSON's escaping for these values


def build_task_toml(inst: dict, image: str, name: str, verifier_module: str | None = None) -> str:
    lines = [
        'schema_version = "1.1"',
        "",
        "[task]",
        "name = " + toml_str(f"{name}/{inst['instance_id']}"),
        "description = " + toml_str(f"SWE-Gym: {inst['repo']} {inst['version']}"),
        'keywords = ["swe-gym", "python"]',
        "",
        "[metadata]",
        f"instance_id = {toml_str(inst['instance_id'])}",
        f"repo = {toml_str(inst['repo'])}",
        f"version = {toml_str(str(inst['version']))}",
        f"base_commit = {toml_str(inst['base_commit'])}",
        'data_source = "swe-gym"',
        "",
        "[environment]",
        f"docker_image = {toml_str(image)}",
        'workdir = "/testbed"',
        f"cpus = {RESOURCES['cpus']}",
        f"memory_mb = {RESOURCES['memory_mb']}",
        "allow_internet = true",
        "",
        "[agent]",
        f"timeout_sec = {AGENT_TIMEOUT_SEC}",
        "",
        "[verifier]",
        f"timeout_sec = {VERIFIER_TIMEOUT_SEC}",
    ]
    if verifier_module:
        # Explicit config outranks auto-detection, which would otherwise pick
        # tests/test.sh over tests/evaluate.py (rllm/eval/_resolution.py).
        lines.append(f"module = {toml_str(verifier_module)}")
    lines.append("")
    return "\n".join(lines)


def write_dataset_toml(out: Path, *, name: str, split: str, description: str, verifier_module: str | None = None) -> None:
    verifier = f"module = {toml_str(verifier_module)}" if verifier_module else 'script = "tests/test.sh"'
    (out / "dataset.toml").write_text(
        "\n".join(
            [
                "[dataset]",
                f"name = {toml_str(name)}",
                'type = "sandbox"',
                f"description = {toml_str(description)}",
                'default_sandbox = "docker"',
                'default_agent = "openhands-sdk"',
                f"split = {toml_str(split)}",
                "",
                "[verifier]",
                verifier,
                "",
            ]
        ),
        encoding="utf-8",
    )


def render_instruction(inst: dict, style: str = "skyrl") -> str:
    return INSTRUCTION_TEMPLATES[style].format(problem_statement=inst["problem_statement"].strip(), base_commit=inst["base_commit"])


def materialize(task_dir: Path, inst: dict, image: str, name: str, specs: dict, grade_src: Path, evaluate_src: Path | None = None, instruction: str = "skyrl") -> None:
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(build_task_toml(inst, image, name, "tests.evaluate" if evaluate_src else None), encoding="utf-8")
    (task_dir / "instruction.md").write_text(render_instruction(inst, instruction), encoding="utf-8")
    tests = task_dir / "tests"
    tests.mkdir()
    (tests / "test.sh").write_text(TEST_SH, encoding="utf-8")
    (tests / "test.sh").chmod(0o755)
    (tests / "eval.sh").write_text(swegym_eval.make_eval_script(inst, specs), encoding="utf-8")
    (tests / "eval.sh").chmod(0o755)
    shutil.copy2(grade_src, tests / "grade.py")
    (tests / "instance.json").write_text(json.dumps(swegym_eval.instance_json(inst, specs), indent=1), encoding="utf-8")
    if evaluate_src is not None:
        shutil.copy2(evaluate_src, tests / "evaluate.py")
    sol = task_dir / "solution"
    sol.mkdir()
    (sol / "gold.patch").write_text(inst["patch"], encoding="utf-8")
    (sol / "solve.sh").write_text(SOLVE_SH, encoding="utf-8")
    (sol / "solve.sh").chmod(0o755)


def read_instances(parquet: Path) -> list[dict]:
    import pyarrow.parquet as pq

    rows = pq.read_table(str(parquet), columns=["instance"]).to_pylist()
    return [r["instance"] for r in rows]


def local_images() -> set[str] | None:
    try:
        out = subprocess.check_output(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return None
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


def build(parquet: Path, *, name: str, split: str, out_root: Path, limit: int | None, image_prefix: str, description: str, have_images: set[str] | None, evaluate_src: Path | None = None, instruction: str = "skyrl") -> int:
    from rllm.data import DatasetRegistry

    specs = swegym_eval.load_specs()
    grade_src = Path(__file__).with_name("grade.py")
    instances = read_instances(parquet)
    if limit and limit > 0:
        instances = instances[:limit]

    out = out_root / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    rows, images = [], set()
    for inst in instances:
        image = image_for(inst["instance_id"], image_prefix)
        images.add(image)
        task_dir = out / inst["instance_id"]
        materialize(task_dir, inst, image, name, specs, grade_src, evaluate_src, instruction)
        rows.append(
            {
                "id": inst["instance_id"],
                "task_id": inst["instance_id"],
                "task_path": str(task_dir),
                "instruction": (task_dir / "instruction.md").read_text(encoding="utf-8"),
                "question": (task_dir / "instruction.md").read_text(encoding="utf-8"),
                "docker_image": image,
                "data_source": "swe-gym",
                "repo": inst["repo"],
                "version": str(inst["version"]),
            }
        )
    write_dataset_toml(out, name=name, split=split, description=description, verifier_module="tests.evaluate" if evaluate_src else None)
    (out / "images.txt").write_text("\n".join(sorted(images)) + "\n", encoding="utf-8")

    DatasetRegistry.register_dataset(name=name, data=rows, split=split, source=str(parquet), description=description, category="agentic")
    print(f"[{split}] {name}/{split}: {len(rows)} tasks -> {out}")
    if have_images is not None:
        missing = sorted(i for i in images if i not in have_images)
        print(f"[{split}] images: {len(images)} total, {len(missing)} not in the local docker daemon")
        if missing:
            print(f"[{split}] pull them with:  xargs -a {out / 'images.txt'} -P 4 -I{{}} docker pull {{}}")
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parquet-dir", required=True, help="Directory holding train.parquet and validation.parquet (SkyRL-v0-293-data).")
    ap.add_argument("--train-name", default=TRAIN_NAME)
    ap.add_argument("--val-name", default=VAL_NAME)
    ap.add_argument("--train-limit", type=int, default=None, help="Keep the first N train instances (default: all 293).")
    ap.add_argument("--val-limit", type=int, default=None, help="Keep the first N validation instances (default: all 23).")
    ap.add_argument("--image-prefix", default=DEFAULT_IMAGE_PREFIX, help="Registry prefix for the SWE-Gym instance images (default: %(default)s).")
    ap.add_argument("--train-only", action="store_true")
    ap.add_argument("--val-only", action="store_true")
    ap.add_argument("--no-image-check", action="store_true", help="Do not consult `docker images` for missing images.")
    ap.add_argument(
        "--evaluate-py",
        default=None,
        help=(
            "Optional Python verifier copied into every task's tests/evaluate.py and selected via "
            '[verifier] module = "tests.evaluate" (hybrid reward: the module gets the live sandbox and can '
            "run /tests/test.sh for the SWE-Gym reward, then add its own signals). Without it the verifier is "
            "tests/test.sh alone."
        ),
    )
    ap.add_argument(
        "--instruction",
        choices=sorted(INSTRUCTION_TEMPLATES),
        default="skyrl",
        help=(
            "Task prompt: 'skyrl' is the prompt SkyRL-v0 trained with, i.e. OpenHands' SWE-bench prompt with its six-step procedure (the control arm); "
            "'aidlc' drops that procedure so it does not compete with /ai-dlc/core-workflow.md (the AI-DLC arms). "
            "With 'aidlc' the default dataset names get an `_aidlc` suffix (swegym293_aidlc / swegym_val23_aidlc) "
            "so the control arm's task dirs are kept; pass --train-name / --val-name to choose otherwise."
        ),
    )
    args = ap.parse_args()
    if args.instruction != "skyrl":
        if args.train_name == TRAIN_NAME:
            args.train_name = f"{TRAIN_NAME}_{args.instruction}"
        if args.val_name == VAL_NAME:
            args.val_name = f"{VAL_NAME}_{args.instruction}"
    evaluate_src = Path(args.evaluate_py).expanduser().resolve() if args.evaluate_py else None
    if evaluate_src is not None and not evaluate_src.is_file():
        sys.exit(f"--evaluate-py: {evaluate_src} is not a file")

    from rllm import paths

    out_root = Path(paths.datasets_dir())
    out_root.mkdir(parents=True, exist_ok=True)
    parquet_dir = Path(args.parquet_dir).expanduser()
    have = None if args.no_image_check else local_images()
    if have is None and not args.no_image_check:
        print("[warn] `docker images` unavailable here; skipping the image check (run on the training node to verify).")

    summary: dict[str, int] = {}
    if not args.val_only:
        summary["train"] = build(
            parquet_dir / "train.parquet",
            name=args.train_name,
            split=TRAIN_SPLIT,
            out_root=out_root,
            limit=args.train_limit,
            image_prefix=args.image_prefix,
            description="SWE-Gym (SkyRL-v0 293-instance subset), swegym eval_script verifier" + ("" if args.instruction == "skyrl" else f" ({args.instruction} instruction)"),
            instruction=args.instruction,
            have_images=have,
            evaluate_src=evaluate_src,
        )
    if not args.train_only:
        summary["val"] = build(
            parquet_dir / "validation.parquet",
            name=args.val_name,
            split=VAL_SPLIT,
            out_root=out_root,
            limit=args.val_limit,
            image_prefix=args.image_prefix,
            description="SkyRL-v0 validation set (23 SWE-bench-style instances), swegym eval_script verifier" + ("" if args.instruction == "skyrl" else f" ({args.instruction} instruction)"),
            instruction=args.instruction,
            have_images=have,
            evaluate_src=evaluate_src,
        )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
