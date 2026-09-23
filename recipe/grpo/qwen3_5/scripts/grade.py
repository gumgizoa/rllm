#!/usr/bin/env python
"""In-sandbox grader for SWE-Gym tasks: swegym's grading rules, stdlib only.

Copied into every task's ``tests/`` by ``prepare_swegym.py`` and run by ``tests/test.sh``
with the image's ``/opt/miniconda3/bin/python`` after ``eval.sh`` has produced its log.

Reproduces ``swegym.harness.grading`` (fork of SWE-bench, MIT):

* ``get_logs_eval``: the log must contain ``"applied patch"`` (git's ``Applied patch ...
  cleanly`` from applying the gold *test* patch), else nothing was graded -> 0. The status
  map is parsed from the text after ``">>>>> Applied Patch (pred)"`` when that marker exists
  (it does not on this path: the agent's edits are graded in place, no patch is re-applied).
* ``get_eval_tests_report`` / ``get_resolution_status``: a test *passed* if its status is
  PASSED or XFAIL, *failed* if it is missing or FAILED/ERROR (SKIPPED counts as neither).
  resolved <=> every FAIL_TO_PASS and every PASS_TO_PASS test passed (an empty list is 1.0).

Reward is binary, written as Harbor-style JSON so rLLM's ``ShellScriptEvaluator`` picks up
per-test signals alongside it.

Usage: grade.py <eval_output.log> <instance.json> <reward.json> [report.json]
"""

from __future__ import annotations

import json
import re
import sys

STATUSES = ("FAILED", "PASSED", "SKIPPED", "ERROR", "XFAIL")
APPLY_PATCH_FAIL = ">>>>> Patch Apply Failed"
APPLY_PATCH_PASS = ">>>>> Applied Patch"
RESET_FAILED = ">>>>> Reset Failed"
TESTS_ERROR = ">>>>> Tests Errored"
TESTS_TIMEOUT = ">>>>> Tests Timed Out"


# --- swegym.harness.log_parsers -------------------------------------------------------------


def parse_log_pytest(log: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in log.split("\n"):
        if any(line.startswith(s) for s in STATUSES):
            if line.startswith("FAILED"):
                line = line.replace(" - ", " ")
            parts = line.split()
            if len(parts) <= 1:
                continue
            out[parts[1]] = parts[0]
    return out


def parse_log_pytest_options(log: str) -> dict[str, str]:
    option_pattern = re.compile(r"(.*?)\[(.*)\]")
    out: dict[str, str] = {}
    for line in log.split("\n"):
        if any(line.startswith(s) for s in STATUSES):
            if line.startswith("FAILED"):
                line = line.replace(" - ", " ")
            parts = line.split()
            if len(parts) <= 1:
                continue
            has_option = option_pattern.search(parts[1])
            if has_option:
                main, option = has_option.groups()
                if option.startswith("/") and not option.startswith("//") and "*" not in option:
                    option = "/" + option.split("/")[-1]
                name = f"{main}[{option}]"
            else:
                name = parts[1]
            out[name] = parts[0]
    return out


def parse_log_pytest_pydantic(log: str) -> dict[str, str]:
    out: dict[str, str] = {}
    escapes = "".join(chr(c) for c in range(1, 32))
    translator = str.maketrans("", "", escapes)
    for line in log.split("\n"):
        line = re.sub(r"\[(\d+)m", "", line).translate(translator)
        line = re.sub(r"FAILED\s*\[.*?\]", "FAILED", line)
        if any(line.startswith(s) for s in STATUSES):
            if line.startswith("FAILED"):
                line = line.replace(" - ", " ")
            parts = line.split()
            out[parts[1]] = parts[0]
        elif any(line.endswith(s) for s in STATUSES):
            parts = line.split()
            out[parts[0]] = parts[1]
    return out


PARSERS = {
    "pytest": parse_log_pytest,
    "pytest_options": parse_log_pytest_options,
    "pytest_pydantic": parse_log_pytest_pydantic,
}


# --- swegym.harness.grading -----------------------------------------------------------------


def test_passed(case: str, sm: dict[str, str]) -> bool:
    return case in sm and sm[case] in ("PASSED", "XFAIL")


def test_failed(case: str, sm: dict[str, str]) -> bool:
    return case not in sm or sm[case] in ("FAILED", "ERROR")


def get_logs_eval(content: str, parser) -> tuple[dict[str, str], bool]:
    bad = (APPLY_PATCH_FAIL, RESET_FAILED, TESTS_ERROR, TESTS_TIMEOUT, "Failed to reset task environment")
    if any(x in content for x in bad) or "applied patch" not in content.lower():
        return {}, False
    content = content.split(f"{APPLY_PATCH_PASS} (pred)")[-1]
    return parser(content), True


def split_report(cases: list[str], sm: dict[str, str]) -> tuple[list[str], list[str]]:
    success, failure = [], []
    for case in cases:
        if test_passed(case, sm):
            success.append(case)
        elif test_failed(case, sm):
            failure.append(case)
    return success, failure


def ratio(success: list[str], failure: list[str]) -> float:
    total = len(success) + len(failure)
    return 1.0 if total == 0 else len(success) / total


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__, file=sys.stderr)
        return 2
    log_path, instance_path, reward_path = argv[1:4]
    report_path = argv[4] if len(argv) > 4 else None

    inst = json.load(open(instance_path, encoding="utf-8"))
    try:
        content = open(log_path, encoding="utf-8", errors="replace").read()
    except OSError as e:
        content = ""
        log_error = f"eval log unreadable: {e}"
    else:
        log_error = None

    parser = PARSERS[inst.get("log_parser", "pytest")]
    status_map, found = get_logs_eval(content, parser)
    f2p_ok, f2p_bad = split_report(inst["FAIL_TO_PASS"], status_map)
    p2p_ok, p2p_bad = split_report(inst["PASS_TO_PASS"], status_map)
    resolved = found and ratio(f2p_ok, f2p_bad) == 1.0 and ratio(p2p_ok, p2p_bad) == 1.0
    reward = 1.0 if resolved else 0.0

    report = {
        "instance_id": inst["instance_id"],
        "test_patch_applied": found,
        "resolved": resolved,
        "FAIL_TO_PASS": {"success": f2p_ok, "failure": f2p_bad},
        "PASS_TO_PASS": {"success": p2p_ok, "failure": p2p_bad},
        "n_parsed_tests": len(status_map),
    }
    if log_error:
        report["error"] = log_error
    out = {
        "reward": reward,
        "is_correct": resolved,
        "signals": {
            "f2p_success": len(f2p_ok),
            "f2p_total": len(inst["FAIL_TO_PASS"]),
            "p2p_success": len(p2p_ok),
            "p2p_total": len(inst["PASS_TO_PASS"]),
            "test_patch_applied": 1.0 if found else 0.0,
        },
        "metadata": {"f2p_failure": f2p_bad[:50], "p2p_failure": p2p_bad[:50], "test_patch_applied": found},
    }
    with open(reward_path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1)
    print(f"[grade] {inst['instance_id']}: applied={found} f2p={len(f2p_ok)}/{len(inst['FAIL_TO_PASS'])} p2p={len(p2p_ok)}/{len(inst['PASS_TO_PASS'])} reward={reward}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
