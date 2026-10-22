#!/usr/bin/env python3
"""Convert SWE-Factory jsonl (swe_rl_v1) into Harbor-format task directories.

Input : one or more jsonl files, one instance per line, with the SWE-Factory
        fields ``instance_id, repo, base_commit, problem_statement, patch,
        test_patch, dockerfile, eval_script, ...``.
Output: ``$RLLM_HOME/datasets/<name>/<instance_id>/`` per task plus a root
        ``dataset.toml``, then (unless ``--no-register``) a DatasetRegistry
        entry so ``rllm eval <name> --split <split>`` finds it.

    <instance_id>/
    ├── task.toml                # id, repo, base_commit, language, resources, timeouts
    ├── instruction.md           # problem_statement verbatim
    ├── environment/Dockerfile   # original SWE-Factory dockerfile
    ├── tests/test.sh            # verifier wrapper: runs run_tests.sh, parses OMNIGRIL_EXIT_CODE
    ├── tests/run_tests.sh       # original eval_script (test_patch embedded as heredoc)
    ├── tests/config.json        # grading metadata
    └── solution/{solve.sh, gold.patch}

Verifier contract: ``run_tests.sh`` prints ``OMNIGRIL_EXIT_CODE=<rc>`` after
the test command; the last such line decides the reward (rc == 0 -> 1.0).
The wrapper writes ``/tmp/rllm/reward.json`` (native ShellScriptEvaluator)
and ``/logs/verifier/reward.{json,txt}`` (Harbor harness) so both paths work.

Usage::

    export RLLM_HOME=/path/to/rllm-home
    python recipe/eval/swe-rl/prepare_swe_rl.py \
        --name swe_rl_v1 /path/to/swe_rl_v1/*.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path

LANG_BY_STEM = {"python": "python", "go": "go", "javascript": "javascript", "typescript": "typescript"}

_TEST_SH = r"""#!/bin/bash
# Verifier wrapper for SWE-Factory tasks.
#
# run_tests.sh is the original SWE-Factory eval_script: it re-checks out the
# test files at base_commit, applies test_patch, runs the target tests and
# prints OMNIGRIL_EXIT_CODE=<rc>. Its own exit status is that of the trailing
# cleanup command, so the marker line is the only reliable signal.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG=/logs/verifier/run_tests.log
WORKDIR="${RLLM_TASK_WORKDIR:-/testbed}"

# Reward-file hijack (grader 1.2). The evaluator trusts the first reward file
# that exists, and the agent is root in this container: it can plant
# /tmp/rllm/reward.json and turn /logs/verifier into a plain file so that our
# own write fails and the planted 1.0 is read. Start from empty directories and
# refuse to go on if they cannot be made.
rm -rf /tmp/rllm /logs/verifier 2>/dev/null
[ -d /logs ] && [ ! -L /logs ] || rm -rf /logs 2>/dev/null    # agent may have made it a file or symlink
mkdir -p /tmp/rllm /logs/verifier 2>/dev/null
if [ ! -d /tmp/rllm ] || [ ! -d /logs/verifier ] || [ -L /tmp/rllm ] || [ -L /logs/verifier ] \
    || [ -n "$(ls -A /tmp/rllm 2>/dev/null)" ] || [ -n "$(ls -A /logs/verifier 2>/dev/null)" ]; then
    echo "GRADER: cannot reset reward directories" >&2
    exit 1
fi

# Leftover agent processes (grader 1.2). Anything the agent started in the
# background keeps running into grading and can edit files after the restore
# below, or rewrite the reward file after we exit. Keep PID 1, this script and
# its ancestors (the docker exec chain); kill everything else. Runs again right
# before the reward is written, since code under test can daemonize too.
_ppid_of() {
    local k v
    while read -r k v _; do [ "$k" = "PPid:" ] && { echo "$v"; return; }; done < "/proc/$1/status" 2>/dev/null
    echo 0
}
kill_strays() {
    local keep=" 1 $$ " p=$$ round pid
    while [ "$p" -gt 1 ]; do p="$(_ppid_of "$p")"; keep="$keep$p "; done
    for round in 1 2 3; do
        for pid in /proc/[0-9]*; do
            pid="${pid#/proc/}"
            case "$keep" in *" $pid "*) continue ;; esac
            [ "$(_ppid_of "$pid")" = "$$" ] && continue    # our own command substitutions
            kill -9 "$pid" 2>/dev/null
        done
        sleep 0.2
    done
}
kill_strays

# Git config isolation. An agent can point core.hooksPath at its own directory in
# /root/.gitconfig; that setting survives --hide-git-history (which only swaps
# .git) and the hook then fires inside run_tests.sh's own `git checkout`,
# re-creating the files the test patch adds *after* our pre-check has passed.
# Replace the global config with one we write, drop the system config, and point
# hooks at an empty directory. Exported so run_tests.sh inherits it.
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/tmp/rllm/grader.gitconfig
mkdir -p /tmp/rllm/empty-hooks
rm -f /tmp/rllm/empty-hooks/* 2>/dev/null || true
printf '[safe]\n\tdirectory = *\n[core]\n\thooksPath = /tmp/rllm/empty-hooks\n' > "$GIT_CONFIG_GLOBAL"
# pytest-xdist "-n auto" counts host CPUs (256 here), not the sandbox quota,
# and the workers crash-loop under the cgroup limit. Cap it to the task's cpus.
export PYTEST_XDIST_AUTO_NUM_WORKERS="${PYTEST_XDIST_AUTO_NUM_WORKERS:-4}"

write_reward() {
    local reward="$1" reason="$2" rc="$3" json
    kill_strays
    json="$(printf '{"reward": %s, "is_correct": %s, "metadata": {"reason": "%s", "omnigril_exit_code": %s, "grader_version": "1.2"}}' \
        "$reward" "$([ "$reward" = "1.0" ] && echo true || echo false)" "$reason" "$rc")"
    # One redirect per file: a failure on one path must not skip the others.
    echo "$json" > /tmp/rllm/reward.json
    echo "$json" > /logs/verifier/reward.json
    echo "$reward" > /logs/verifier/reward.txt
    echo "$json"
}

cd "$WORKDIR" 2>/dev/null || { write_reward 0.0 "workdir_missing" -1; exit 0; }
git config --global --add safe.directory "$WORKDIR" 2>/dev/null || true

if [ ! -f "$HERE/run_tests.sh" ]; then
    write_reward 0.0 "run_tests_missing" -1
    exit 0
fi

# Grading hole (swe_rl_v1): run_tests.sh's own `git checkout <base>` often has
# no paths and its `git apply` of the test patch is not checked, so an agent
# that edits (or pre-creates) the files the test patch touches makes the
# patch fail to apply and gets graded on its own tests instead. Mirror the
# SWE-bench grader: put every test-patch target back to base first, then
# refuse to grade if the real test patch cannot be applied.
if [ -f "$HERE/restore_test_targets.sh" ]; then
    if ! bash "$HERE/restore_test_targets.sh" > /logs/verifier/restore.log 2>&1; then
        cat /logs/verifier/restore.log
        write_reward 0.0 "test_target_restore_failed" -1
        exit 0
    fi
fi
if [ -f "$HERE/test.patch" ]; then
    if ! git apply --check "$HERE/test.patch" > /logs/verifier/apply_check.log 2>&1; then
        cat /logs/verifier/apply_check.log
        echo "TEST_PATCH_APPLY_FAILED"
        write_reward 0.0 "test_patch_apply_failed" -1
        exit 0
    fi
fi

bash "$HERE/run_tests.sh" > "$LOG" 2>&1
RT_STATUS=$?
# Forged marker (grader 1.2): code under test can print its own
# "OMNIGRIL_EXIT_CODE=0" plus a fake pass summary and then kill run_tests.sh
# before the real marker line. A script that died of a signal graded nothing.
if [ "$RT_STATUS" -ge 128 ]; then
    write_reward 0.0 "run_tests_killed_by_signal" "$RT_STATUS"
    exit 0
fi
RC_LINE="$(grep -a -o 'OMNIGRIL_EXIT_CODE=[0-9]*' "$LOG" | tail -n 1)"
if [ -z "$RC_LINE" ]; then
    write_reward 0.0 "no_exit_code_marker" -1
    exit 0
fi
RC="${RC_LINE#OMNIGRIL_EXIT_CODE=}"
if [ "$RC" != "0" ]; then
    write_reward 0.0 "tests_failed" "$RC"
    exit 0
fi

# Exit code alone is not proof (grader 1.2): code under test can call
# os._exit(0) during collection, or a Go init()/TestMain can os.Exit(0) before
# any test runs, and the runner then reports success having run nothing.
# Require a pass line in the log. pass_evidence.ere holds one extended regex
# per line (any match counts): pass lines that name the hidden test patch's
# own tests where the runner prints names, else the runner's summary line.
# No file = exit code only.
if [ -s "$HERE/pass_evidence.ere" ]; then
    # No grep -q: it exits on the first match, sed then dies of SIGPIPE on a
    # long log, and pipefail turns that into a miss.
    if ! sed 's/\x1b\[[0-9;]*[A-Za-z]//g' "$LOG" | grep -a -E -f "$HERE/pass_evidence.ere" > /dev/null; then
        echo "NO_PASS_EVIDENCE"
        write_reward 0.0 "no_pass_evidence" "$RC"
        exit 0
    fi
fi
write_reward 1.0 "tests_passed" "$RC"
exit 0
"""


def _toml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


# BuildKit cannot modify /etc/hosts (or /etc/resolv.conf) during a build: the
# file is bind-mounted, and ``RUN echo ... >> /etc/hosts`` fails with exit 2
# where the legacy builder silently succeeded. Those lines are moved out of
# the Dockerfile into ``[rllm].setup_commands``, which rllm runs inside the
# live sandbox where the file is writable.
_HOSTS_RUN = re.compile(r'^RUN\s+(echo\s+"[^"\n]*"\s*>>\s*/etc/hosts)\s*$', re.M)


def split_runtime_only_steps(dockerfile: str) -> tuple[str, list[str]]:
    cmds = [m.group(1) for m in _HOSTS_RUN.finditer(dockerfile)]
    if cmds:
        dockerfile = _HOSTS_RUN.sub(
            "# moved to [rllm].setup_commands in task.toml: BuildKit cannot write /etc/hosts at build time\nRUN true",
            dockerfile,
        )
    return dockerfile, cmds


def build_task_toml(row: dict, *, language: str, cpus: int, memory_mb: int, storage_mb: int,
                    workdir: str, agent_timeout: int, verifier_timeout: int, build_timeout: int,
                    setup_commands: list[str] | None = None) -> str:
    repo = row.get("repo", "")
    short = (row.get("problem_statement") or "").strip().splitlines()
    title = short[0][:120] if short else row["instance_id"]
    return "\n".join([
        'schema_version = "1.1"',
        "",
        "[task]",
        f"name = {_toml_str(row['instance_id'])}",
        f"description = {_toml_str(title)}",
        f'keywords = ["swe", "swe-factory", {_toml_str(language)}]',
        "",
        "[metadata]",
        f"instance_id = {_toml_str(row['instance_id'])}",
        f"repo = {_toml_str(repo)}",
        f"base_commit = {_toml_str(row.get('base_commit', ''))}",
        f"language = {_toml_str(language)}",
        f"pull_number = {int(row.get('pull_number') or 0)}",
        f"version = {_toml_str(str(row.get('version', '')))}",
        "",
        "[environment]",
        f"workdir = {_toml_str(workdir)}",
        f"cpus = {cpus}",
        f"memory_mb = {memory_mb}",
        f"storage_mb = {storage_mb}",
        f"build_timeout_sec = {build_timeout}",
        "allow_internet = true",
        "",
        "[agent]",
        f"timeout_sec = {agent_timeout}",
        "",
        "[verifier]",
        f"timeout_sec = {verifier_timeout}",
        "",
    ] + ([
        "[rllm]",
        "setup_commands = [" + ", ".join(_toml_str(c) for c in setup_commands) + "]",
        "",
    ] if setup_commands else []))


def build_solve_sh(base_commit: str, workdir: str) -> str:
    return "\n".join([
        "#!/bin/bash",
        "set -e",
        f"cd {workdir}",
        f"git config --global --add safe.directory {workdir} 2>/dev/null || true",
        f'git reset --hard "{base_commit}"',
        f'git checkout "{base_commit}"',
        "git apply -v /solution/gold.patch",
        "",
    ])


def classify_test_patch(test_patch: str) -> tuple[list[str], list[str]]:
    """Split the test patch's files into (restore_to_base, remove_if_present).

    Modified and deleted files exist at base_commit and are restored with
    ``git checkout <base> -- <path>``; files the patch creates do not exist at
    base and are removed so the patch's ``/dev/null`` hunk applies. A rename
    restores the source and removes the target. Parsed with ``unidiff`` (not
    regexes) so quoted paths and rename headers are handled.
    """
    from unidiff import PatchSet

    restore: list[str] = []
    remove: list[str] = []
    for pf in PatchSet(test_patch):
        src = pf.source_file[2:] if pf.source_file.startswith("a/") else pf.source_file
        dst = pf.target_file[2:] if pf.target_file.startswith("b/") else pf.target_file
        if pf.is_rename:
            restore.append(src)
            remove.append(dst)
        elif pf.is_added_file:
            remove.append(dst)
        elif pf.is_removed_file:
            restore.append(src)
        else:
            restore.append(pf.path)
    dedup = lambda xs: list(dict.fromkeys(x for x in xs if x and x != "/dev/null"))
    return dedup(restore), dedup(remove)


def patch_paths(patch: str) -> list[str]:
    """Every path a patch touches (both sides of a rename), in order."""
    restore, remove = classify_test_patch(patch)
    return list(dict.fromkeys(restore + remove))


# Test-harness files outside the test patch (grader 1.2). The test patch only
# names the test files themselves, but the runner also reads its own config
# and hook files, and an agent that edits those passes without fixing
# anything: a conftest.py hook that marks every test passed, pytest addopts in
# pyproject.toml, a TestMain in a new *_test.go that exits 0 before any test,
# a "test" script or jest block in package.json, a vitest setup file. Tracked
# ones are put back to base, untracked ones deleted. Files the gold patch
# touches are left alone (a correct fix may need them).
_HARNESS_GLOBS = [
    # python
    "**/conftest.py", "**/pytest.ini", "**/tox.ini", "**/setup.cfg", "**/pyproject.toml",
    "**/sitecustomize.py", "**/usercustomize.py",
    # go
    "**/*_test.go",
    # javascript / typescript
    "**/package.json", "**/jest.config.*", "**/jest.setup.*", "**/jest.preset.*",
    "**/vitest.config.*", "**/vitest.workspace.*", "**/vitest.setup.*", "**/vite.config.*",
    "**/babel.config.*", "**/.babelrc*", "**/.mocharc*", "**/karma.conf.*", "**/setupTests.*",
]
# Never walked: installed dependencies, not the agent's sources.
_PRUNE_GLOBS = ["**/node_modules/**", "**/vendor/**", "**/.venv/**", "**/venv/**", "**/.tox/**", "**/site-packages/**"]


def build_restore_script(base_commit: str, workdir: str, paths: list[str], keep: list[str] = ()) -> str:
    """Put every path the test patch touches back to its base_commit state.

    Decided at run time rather than from the diff headers, because the two can
    disagree: a patch header may name a file that is not in base, and the agent
    may have left a *directory* where the patch expects to create a file.

      * untracked at this path  -> the agent made it; ``rm -rf``
      * exists in base          -> ``git checkout <base> -- <path>``
      * not in base             -> ``rm -rf`` so the patch's new-file hunk applies

    Then the test-harness files (``_HARNESS_GLOBS``) outside the test patch:
    tracked ones that differ from base are checked out from base, untracked
    ones are deleted, except paths in ``keep`` (the gold patch's files).

    Failures are reported and make the script exit non-zero; ``test.sh`` then
    scores 0 rather than grading whatever is in the tree.
    """
    lines = [
        "#!/bin/bash",
        "# Generated by prepare_swe_rl.py: restore test-patch targets before grading.",
        "set -u",
        f"cd {shlex.quote(workdir)} || exit 2",
        f"BASE={shlex.quote(base_commit)}",
        "rc=0",
        "",
        "# Repo-local config outranks the global one test.sh isolated, so clear",
        "# core.hooksPath here too and empty the repo's own hooks directory.",
        "git config --local --unset-all core.hooksPath 2>/dev/null || true",
        'HOOKS="$(git rev-parse --git-path hooks 2>/dev/null)"',
        'if [ -n "$HOOKS" ] && [ -d "$HOOKS" ]; then rm -rf -- "$HOOKS" && mkdir -p -- "$HOOKS"; fi',
        "",
        "restore_one() {",
        '    local path="$1"',
        '    if [ -e "$path" ] && ! git ls-files --error-unmatch -- "$path" >/dev/null 2>&1; then',
        '        rm -rf -- "$path" || { echo "restore: rm untracked failed: $path" >&2; rc=1; return; }',
        "    fi",
        '    if git cat-file -e "$BASE:$path" 2>/dev/null; then',
        '        git checkout "$BASE" -- "$path" || { echo "restore: checkout failed: $path" >&2; rc=1; }',
        "    else",
        '        rm -rf -- "$path" || { echo "restore: rm failed: $path" >&2; rc=1; }',
        "    fi",
        "}",
        "",
    ]
    lines += [f"restore_one {shlex.quote(p)}" for p in paths]
    q = lambda xs: " ".join(shlex.quote(x) for x in xs)
    lines += [
        "",
        "# Test-harness files outside the test patch (grader 1.2).",
        f"HARNESS=({q(':(glob)' + g for g in _HARNESS_GLOBS)})",
        f"PRUNE=({q(':(exclude,glob)' + g for g in _PRUNE_GLOBS)})",
        f"KEEP=({q(list(dict.fromkeys(list(paths) + list(keep))))})",
        "keep_path() {",
        '    local k',
        '    for k in ${KEEP[@]+"${KEEP[@]}"}; do [ "$k" = "$1" ] && return 0; done',
        "    return 1",
        "}",
        "tracked=\"$(mktemp)\"; untracked=\"$(mktemp)\"",
        'git diff --name-only -z "$BASE" -- "${HARNESS[@]}" "${PRUNE[@]}" > "$tracked" \\',
        '    || { echo "restore: git diff failed" >&2; rc=1; }',
        "# --others without --exclude-standard: ignored files count too.",
        'git ls-files -z --others -- "${HARNESS[@]}" "${PRUNE[@]}" > "$untracked" \\',
        '    || { echo "restore: git ls-files failed" >&2; rc=1; }',
        'while IFS= read -r -d "" p; do',
        '    keep_path "$p" && continue',
        '    if git cat-file -e "$BASE:$p" 2>/dev/null; then',
        '        rm -rf -- "$p" 2>/dev/null',
        '        git checkout "$BASE" -- "$p" || { echo "restore: harness checkout failed: $p" >&2; rc=1; }',
        '        echo "restore: harness file reset to base: $p"',
        "    fi",
        'done < "$tracked"',
        'while IFS= read -r -d "" p; do',
        '    keep_path "$p" && continue',
        '    rm -rf -- "$p" || { echo "restore: harness rm failed: $p" >&2; rc=1; }',
        '    echo "restore: untracked harness file removed: $p"',
        'done < "$untracked"',
        'rm -f "$tracked" "$untracked"',
        "",
        "exit $rc",
    ]
    return "\n".join(lines) + "\n"


# Runner pass summaries for pass_evidence.ere (grader 1.2), as grep -E
# patterns. Matched against the run_tests.sh log with ANSI colours stripped.
_EVIDENCE = {
    "pytest": [r"[0-9]+ passed"],
    "go_test_v": [r"^[[:space:]]*--- PASS: "],
    "go_test": [r"^ok[[:space:]]", r"^[[:space:]]*--- PASS: "],
    "js": [
        r"^[[:space:]]*Tests:?[[:space:]]+.*[0-9]+ passed",   # jest "Tests: 3 passed", vitest "Tests  3 passed (3)"
        r"^[[:space:]]*PASS[[:space:]]",                      # jest per-file
        r"[0-9]+ passing",                                    # mocha
        r"^(# |ℹ )pass [1-9]",                                # node:test / tap
    ],
}


def evidence_mode(language: str, eval_script: str) -> str | None:
    """Which runner summary proves the target tests ran; None = exit code only."""
    body = re.sub(r"<<\s*'?(\w+)'?\n.*?\n\1\n", "", eval_script, flags=re.S)  # drop heredoc bodies
    if language == "python":
        return "pytest" if "pytest" in body else None
    if language == "go":
        runs = re.findall(r"^[^#\n]*\bgo test\b[^\n]*", body, re.M)
        if not runs or any("-json" in r for r in runs):
            return None
        return "go_test_v" if all(re.search(r"\s-v\b", r) for r in runs) else "go_test"
    if language in ("javascript", "typescript"):
        return "js"
    return None


def _ere(text: str) -> str:
    return re.sub(r"([.\[\]()*+?{}|^$\\])", r"\\\1", text)


def specific_evidence(mode: str, test_patch: str, eval_script: str = "") -> list[str] | None:
    """Pass lines naming the *test patch's own* tests; None = no names to pin.

    A generic summary ("3 passed", "--- PASS:") can be printed by the code
    under test itself before it exits 0, and was in the drill. These patterns
    name the tests the hidden test patch adds or edits, which the agent never
    sees, so a forged line has to guess them. Any one match counts: -run
    filters, skipped files and build tags make "all of them" too brittle.
    """
    files = re.findall(r"^diff --git a/\S+ b/(\S+)", test_patch, re.M)
    if mode == "go_test_v":
        names = re.findall(r"^\+func (Test\w+)\(", test_patch, re.M) \
            or re.findall(r"^@@[^@\n]*@@ func (Test\w+)\(", test_patch, re.M)
        # Tests named in run_tests.sh's own -run filters: the script is as hidden
        # from the agent as the test patch, and these are the tests that actually
        # run when the patch's new funcs sit behind a build tag or another package.
        body = re.sub(r"<<\s*'?(\w+)'?\n.*?\n\1\n", "", eval_script, flags=re.S)
        for arg in re.findall(r"-run[= ]+(\"[^\"]*\"|'[^']*'|\S+)", body):
            names += re.findall(r"Test\w+", arg.strip("\"'"))
        return [rf"^[[:space:]]*--- PASS: {_ere(n)}([[:space:]/]|$)" for n in dict.fromkeys(names)] or None
    if mode == "pytest":
        bases = [p.rsplit("/", 1)[-1] for p in files if re.search(r"(^|/)(test_[^/]*|[^/]*_test)\.py$", p)]
        pats = []
        for b in dict.fromkeys(bases):
            e = _ere(b)
            pats += [
                rf"(^|[[:space:]/]){e}::[^[:space:]]*[[:space:]]+PASSED",   # -v
                rf"PASSED[[:space:]]+([^[:space:]]*/)?{e}::",               # -rA summary
                rf"(^|/){e}[[:space:]]+[.sxX]*\.",                          # progress line, one '.' at least
            ]
        return pats or None
    if mode == "js":
        bases = [p.rsplit("/", 1)[-1] for p in files
                 if re.search(r"\.(test|spec)\.[cm]?[jt]sx?$", p) or "__tests__/" in p]
        pats = []
        for b in dict.fromkeys(bases):
            e = _ere(b)
            pats += [rf"(PASS|✓)[[:space:]].*{e}"]
        return pats or None
    return None


def build_config_json(row: dict, language: str) -> dict:
    return {
        "instance_id": row["instance_id"],
        "repo": row.get("repo", ""),
        "base_commit": row.get("base_commit", ""),
        "language": language,
        "pull_number": row.get("pull_number"),
        "issue_numbers": row.get("issue_numbers", []),
        "created_at": row.get("created_at"),
        "exit_code_before_patch": row.get("exit_code_before_patch"),
        "exit_code_after_patch": row.get("exit_code_after_patch"),
        "fail_to_pass_verified": row.get("fail_to_pass_verified"),
        "test_files": sorted(set(re.findall(r"^diff --git a/(\S+) b/", row.get("test_patch", ""), re.M))),
        "reward_rule": "last OMNIGRIL_EXIT_CODE in run_tests.sh output == 0 and pass_evidence.ere matches (if present)",
        "source_run": row.get("source_run"),
    }


def materialize(row: dict, task_dir: Path, *, language: str, args: argparse.Namespace) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    dockerfile, setup_commands = split_runtime_only_steps(row["dockerfile"])
    (task_dir / "task.toml").write_text(
        build_task_toml(
            row, language=language, cpus=args.cpus, memory_mb=args.memory_mb, storage_mb=args.storage_mb,
            workdir=args.workdir, agent_timeout=args.agent_timeout, verifier_timeout=args.verifier_timeout,
            build_timeout=args.build_timeout, setup_commands=setup_commands,
        ),
        encoding="utf-8",
    )
    (task_dir / "instruction.md").write_text(row["problem_statement"], encoding="utf-8")

    env_dir = task_dir / "environment"
    env_dir.mkdir(exist_ok=True)
    (env_dir / "Dockerfile").write_text(dockerfile, encoding="utf-8")

    tests = task_dir / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test.sh").write_text(_TEST_SH, encoding="utf-8")
    (tests / "test.sh").chmod(0o755)
    (tests / "run_tests.sh").write_text(row["eval_script"], encoding="utf-8")
    (tests / "run_tests.sh").chmod(0o755)
    test_patch = row.get("test_patch") or ""
    restore, remove = classify_test_patch(test_patch)
    all_paths = list(dict.fromkeys(restore + remove))
    gold_paths = patch_paths(row.get("patch") or "")
    (tests / "test.patch").write_text(test_patch, encoding="utf-8")
    (tests / "restore_test_targets.sh").write_text(
        build_restore_script(row["base_commit"], args.workdir, all_paths, keep=gold_paths), encoding="utf-8"
    )
    (tests / "restore_test_targets.sh").chmod(0o755)
    mode = None if row["instance_id"] in args.evidence_off else evidence_mode(language, row["eval_script"])
    named = None
    if mode and row["instance_id"] not in args.evidence_generic:
        named = specific_evidence(mode, test_patch, row["eval_script"])
    if mode:
        (tests / "pass_evidence.ere").write_text("\n".join(named or _EVIDENCE[mode]) + "\n", encoding="utf-8")
    config = build_config_json(row, language)
    config["restore_paths"] = restore
    config["remove_paths"] = remove
    config["harness_keep_paths"] = gold_paths
    config["pass_evidence"] = mode and (f"{mode}:named" if named else f"{mode}:generic")
    config["grader_version"] = "1.2"
    (tests / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    sol = task_dir / "solution"
    sol.mkdir(exist_ok=True)
    (sol / "gold.patch").write_text(row["patch"], encoding="utf-8")
    (sol / "solve.sh").write_text(build_solve_sh(row["base_commit"], args.workdir), encoding="utf-8")
    (sol / "solve.sh").chmod(0o755)


def write_dataset_toml(out: Path, *, name: str, split: str, description: str) -> None:
    (out / "dataset.toml").write_text("\n".join([
        "[dataset]",
        f"name = {_toml_str(name)}",
        'type = "sandbox"',
        f"description = {_toml_str(description)}",
        'default_sandbox = "docker"',
        'default_agent = "oracle"',
        f"split = {_toml_str(split)}",
        "",
        "[verifier]",
        'script = "tests/test.sh"',
        "",
    ]), encoding="utf-8")


def verify_sha256(files: list[Path]) -> None:
    """Check each file against a sibling SHA256SUMS when present."""
    for f in files:
        sums = f.parent / "SHA256SUMS"
        if not sums.exists():
            continue
        expected = {ln.split()[1].lstrip("*"): ln.split()[0] for ln in sums.read_text().splitlines() if ln.strip()}
        if f.name not in expected:
            continue
        actual = hashlib.sha256(f.read_bytes()).hexdigest()
        if actual != expected[f.name]:
            sys.exit(f"SHA256 mismatch for {f}: {actual} != {expected[f.name]}")
        print(f"  sha256 ok: {f.name}")


def rllm_home() -> Path:
    return Path(os.environ.get("RLLM_HOME") or Path.home() / ".rllm").expanduser()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsonl", nargs="+", type=Path, help="SWE-Factory jsonl files (stem prefix = language)")
    ap.add_argument("--name", default="swe_rl_v1")
    ap.add_argument("--split", default="test")
    ap.add_argument("--out-dir", type=Path, default=None, help="default: $RLLM_HOME/datasets/<name>")
    ap.add_argument("--workdir", default="/testbed")
    ap.add_argument("--cpus", type=int, default=4)
    ap.add_argument("--memory-mb", type=int, default=32768)
    ap.add_argument("--storage-mb", type=int, default=51200)
    ap.add_argument("--build-timeout", type=int, default=3600)
    ap.add_argument("--agent-timeout", type=int, default=1800)
    ap.add_argument("--verifier-timeout", type=int, default=5400)
    ap.add_argument("--limit", type=int, default=0, help="per-file cap (smoke tests)")
    ap.add_argument("--ids", type=Path, default=None, help="only these instance ids (one per line)")
    ap.add_argument("--force", action="store_true", help="rewrite task dirs that already exist")
    ap.add_argument("--no-register", action="store_true", help="skip DatasetRegistry (no rllm import needed)")
    ap.add_argument("--evidence-generic-ids", type=Path, default=None,
                    help="instance ids whose runner output does not name test files/functions: use the generic summary")
    ap.add_argument("--evidence-off-ids", type=Path, default=None,
                    help="instance ids graded on exit code only (runner prints no summary pass_evidence.ere knows)")
    args = ap.parse_args()
    args.evidence_generic = set()
    if args.evidence_generic_ids:
        args.evidence_generic = {ln.strip() for ln in args.evidence_generic_ids.read_text().splitlines() if ln.strip() and not ln.startswith("#")}
    args.evidence_off = set()
    if args.evidence_off_ids:
        args.evidence_off = {ln.strip() for ln in args.evidence_off_ids.read_text().splitlines() if ln.strip() and not ln.startswith("#")}

    out = args.out_dir or rllm_home() / "datasets" / args.name
    out.mkdir(parents=True, exist_ok=True)
    verify_sha256(args.jsonl)
    want = None
    if args.ids:
        want = {ln.strip() for ln in args.ids.read_text().splitlines() if ln.strip() and not ln.startswith("#")}

    rows_out, per_lang, skipped = [], {}, 0
    for f in args.jsonl:
        language = LANG_BY_STEM.get(f.stem.split("_")[0].lower(), f.stem.split("_")[0].lower())
        n = 0
        for line in f.open(encoding="utf-8"):
            if not line.strip():
                continue
            row = json.loads(line)
            iid = row["instance_id"]
            if want is not None and iid not in want:
                continue
            if args.limit and n >= args.limit:
                break
            n += 1
            task_dir = out / iid
            if task_dir.exists() and not args.force:
                skipped += 1
            else:
                if task_dir.exists():
                    shutil.rmtree(task_dir)
                materialize(row, task_dir, language=language, args=args)
            rows_out.append({
                "id": iid, "task_id": iid,
                "instruction": row["problem_statement"], "question": row["problem_statement"],
                "task_path": str(task_dir),
                "repo": row.get("repo", ""), "base_commit": row.get("base_commit", ""), "language": language,
            })
        per_lang[language] = per_lang.get(language, 0) + n

    description = f"SWE-Factory RL set ({len(rows_out)} tasks: " + ", ".join(f"{k}={v}" for k, v in per_lang.items()) + ")"
    write_dataset_toml(out, name=args.name, split=args.split, description=description)
    print(f"{args.name}: {len(rows_out)} tasks -> {out}  ({skipped} existing dirs kept)")
    print(f"  per language: {per_lang}")

    if args.no_register:
        return
    from rllm.data.dataset import DatasetRegistry

    DatasetRegistry.register_dataset(
        name=args.name,
        data=rows_out,
        split=args.split,
        source=f"swe-factory jsonl: {', '.join(p.name for p in args.jsonl)}; cpus={args.cpus} memory_mb={args.memory_mb}",
        description=description,
        category="agentic",
    )
    print(f"  registered: rllm eval {args.name} --split {args.split} --agent oracle --sandbox-backend docker ...")


if __name__ == "__main__":
    main()
