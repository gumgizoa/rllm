"""Read the results of the variant evaluations: resolve rate, where the final patch stands against the gold patch,
and whether the run followed the workflow.

The resolve rate alone mixes two losses that the workflow causes (analysis of 2026-11-25): runs that end with no
source change, and runs that change the gold location but with the wrong content. This script reports them apart.

    python analyze.py --run control=<dir>[,<dir>...] --run s2after=<dir> [--compare control s2after] [--out report.md]

    <dir>       a result folder of run_eval.sh (or any folder holding episode_*.json at any depth). Several folders,
                separated by commas, are pooled into one condition (for example a 1-attempt run and a 2-attempt run).
    --dataset   the task folders with tests/config.json (default: $RLLM_HOME/datasets/swebench_verified_all)
    --compare   two labels; prints task-paired differences with bootstrap intervals. May be given several times.

Stages of a rollout, first match wins (the gold patch never holds test files):
    no_source_patch   the final patch holds no source file: nothing, only test files, or only files the run created
                      that the gold patch does not have (scratch scripts left in the repository)
    other_file        none of the changed source files is a gold file
    part_of_gold      some but not all gold files are changed
    same_file_far     all gold files are changed, but in one of them the nearest changed line is more than NEAR
                      lines away from the nearest gold-changed line
    same_spot         all gold files are changed within NEAR lines of the gold change

Workflow-following columns and the number of source-edit steps are read from the tool calls and are approximate.
A source edit is a file-editor change of a non-test file under /testbed, or a terminal command that rewrites one
(sed -i, git apply / patch, a redirect, tee, cp or mv onto a source file, inline Python that opens one for writing,
or running a script written earlier that does). Terminal calls the sandbox refused are skipped. A file the run creates counts only when it is a gold file or the final patch
changes it as an existing file, so that scratch scripts are not edits; reverts through git are not counted.
Checked against the scorer's trajectory replay on the 2026-11 runs: the 1 / 2 / 3+ edit-step bins agree for about
nine rollouts in ten, equally with and without the workflow.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from typing import Callable

NEAR = 10
STAGES = ["no_source_patch", "other_file", "part_of_gold", "same_file_far", "same_spot"]
TEST_RE = re.compile(r"(^|/)(tests?|testing)(/|$)|(^|/)test_[^/]*\.py$|_tests?\.py$|(^|/)conftest\.py$|(^|/)tests\.py$")
# Source packages whose path looks like a test path.
SOURCE_PKG = re.compile(r"^(django/test/|sympy/testing/|lib/matplotlib/testing/|sklearn/utils/(_?testing|estimator_checks)|xarray/testing|src/_pytest/|pylint/testutils/|sphinx/testing/)")
SPEC_DIR = "/tmp/agent-os/specs"
SPEC_REF = r"(?:\$\{?SPEC_PATH\}?|" + re.escape(SPEC_DIR) + r")"
SRC_EXT = r"(?:py|pyx|pxd|pyi|c|h|cpp|cfg|toml|ini)"
SED_INPLACE = re.compile(r"\bsed\s+(-[a-zA-Z]*\s+)*-i")
APPLY_PATCH = re.compile(r"\bgit\s+apply\b|\bpatch\s+-p")
REDIRECT = re.compile(r"(?:>>?|\btee\s+(?:-a\s+)?)\s*[\"']?([\w./${}-]+\." + SRC_EXT + r")\b")
COPY = re.compile(r"\b(?:cp|mv)\s+(?:-\w+\s+)*\S+\s+[\"']?([\w./${}-]+\." + SRC_EXT + r")[\"']?(?:\s|$|&|;)")
PY_INLINE = re.compile(r"\bpython3?\s+-c\b|\bpython3?\s*(?:-\s*)?<<")
CD_ELSEWHERE = re.compile(r"\bcd\s+[\"']?(?!/testbed\b)[$/~]")  # a cd to anywhere but the repository


def is_test(path: str) -> bool:
    return bool(TEST_RE.search(path)) and not SOURCE_PKG.match(path)


def repo_rel(p: str, cwd_repo: bool) -> str | None:
    """Path of ``p`` inside the repository when it is a non-test file there, else None. A relative path is taken
    as inside the repository only when the command does not move elsewhere."""
    if p.startswith("/testbed/"):
        rel = p[len("/testbed/") :]
    elif p.startswith(("/", "$", "~")) or not cwd_repo:
        return None
    else:
        rel = p[2:] if p.startswith("./") else p
    return None if is_test(rel) else rel


def _python_targets(code: str, cwd_repo: bool) -> list[str]:
    """Source files that Python code opens for writing: open("<path>", "w"), open(var, "w") with var = "<path>",
    "<path>".write_text / Path("<path>").write_text, var.write_text with var = Path("<path>")."""
    def assigned(var: str) -> list[str]:
        return re.findall(r"\b" + re.escape(var) + r"\s*=\s*(?:Path\(\s*)?['\"]([^'\"]+)['\"]", code)

    paths: list[str] = []
    for m in re.finditer(r"open\(\s*([^,()]+?)\s*,\s*['\"][wa]\+?['\"]", code):
        arg = m.group(1).strip()
        lit = re.match(r"['\"]([^'\"]+)['\"]$", arg)
        paths += [lit.group(1)] if lit else (assigned(arg) if re.match(r"[A-Za-z_]\w*$", arg) else [])
    paths += re.findall(r"['\"]([^'\"]+)['\"]\s*\)?\.write_text\(", code)
    for m in re.finditer(r"\b([A-Za-z_]\w*)\.write_text\(", code):
        paths += assigned(m.group(1))
    return [r for r in (repo_rel(p, cwd_repo) for p in paths if re.search(r"\." + SRC_EXT + r"$", p)) if r]


def terminal_source_edit(cmd: str, helpers: set[str], counts: Callable[[str, bool], bool]) -> bool:
    """Does this terminal command change a source file of the repository? Approximate, from the command text alone.

    ``counts(rel, creates)`` says whether a write to the repository path ``rel`` is a source edit; ``creates`` is true
    for commands that write a whole file (a redirect, cp, mv)."""
    head = cmd.split("<<", 1)[0]
    cwd_repo = not CD_ELSEWHERE.search(cmd)
    for p in REDIRECT.findall(head) + COPY.findall(head):
        rel = repo_rel(p, cwd_repo)
        if rel and counts(rel, True):
            return True
    for m in SED_INPLACE.finditer(head):
        # The file sed rewrites is the last word of that sed command; names inside its expression are not targets.
        segment = re.split(r"&&|\|\||;|\|", head[m.start() :])[0].strip()
        target = segment.split()[-1].strip("\"'") if segment.split() else ""
        if re.search(r"\.[A-Za-z]{1,5}$", target):
            rel = repo_rel(target, cwd_repo) if re.search(r"\." + SRC_EXT + r"$", target) else None
            if rel and counts(rel, False):
                return True
        elif cwd_repo:  # no file recognizable (a variable, a glob): counted
            return True
    if APPLY_PATCH.search(head) and cwd_repo:
        return True
    if PY_INLINE.search(cmd) and any(counts(r, False) for r in _python_targets(cmd, cwd_repo)):
        return True
    return any(re.search(r"\bpython3?\s+(?:\S*/)?" + re.escape(os.path.basename(h)) + r"(?:\s|$|;|&)", cmd) for h in helpers)


def helper_written(tool: str, a: dict) -> str | None:
    """Path of a script this call writes, outside the source files, whose code edits a source file."""
    if tool == "file_editor" and a.get("command") == "create" and str(a.get("path", "")).endswith(".py"):
        p = str(a.get("path", ""))
        return p if _python_targets(str(a.get("file_text", "")), True) else None
    if tool == "terminal":
        cmd = str(a.get("command", ""))
        m = re.search(r"\bcat\s*>\s*[\"']?([^\s\"']+\.py)[\"']?\s*<<", cmd)
        if m and _python_targets(cmd[m.end() :], True):
            return m.group(1)
    return None


def read_patch(patch: str) -> tuple[dict[str, list[int]], set[str]]:
    """({path: pre-image line numbers the patch changes}, paths the patch creates). An insertion counts at the line
    it is inserted before."""
    out: dict[str, set[int]] = {}
    new: set[str] = set()
    cur, pre, in_hunk = None, 0, False
    for line in (patch or "").split("\n"):
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*?) b/(.*)$", line)
            cur, in_hunk = (m.group(2) if m else None), False
            if cur is not None:
                out.setdefault(cur, set())
        elif cur is None:
            continue
        elif line.startswith("@@"):
            m = re.match(r"@@ -(\d+)", line)
            pre, in_hunk = (int(m.group(1)) if m else 0), True
        elif not in_hunk:  # headers of the file section: "new file mode", "--- a/x", "+++ b/x"
            if line.startswith("new file mode") or line.startswith("--- /dev/null"):
                new.add(cur)
        elif line.startswith("-"):
            out[cur].add(pre)
            pre += 1
        elif line.startswith("+"):
            out[cur].add(pre)
        elif line.startswith(" "):
            pre += 1
    return {k: sorted(v) for k, v in out.items()}, new


def stage_of(mine: dict[str, list[int]], gold: dict[str, list[int]], new: set[str] = frozenset()) -> str:
    src = {k: v for k, v in mine.items() if k in gold or (not is_test(k) and k not in new)}
    if not src:
        return "no_source_patch"
    hit = [f for f in gold if f in src]
    if not hit:
        return "other_file"
    if len(hit) < len(gold):
        return "part_of_gold"
    far = 0
    for f in hit:
        g, m = gold[f], src[f]
        far = max(far, min((abs(a - b) for a in m for b in g), default=10**6) if g and m else 10**6)
    return "same_spot" if far <= NEAR else "same_file_far"


def _messages(episode: dict) -> list[dict]:
    trajs = episode.get("trajectories") or []
    if not trajs or not trajs[0].get("steps"):
        return []
    return trajs[0]["steps"][-1].get("chat_completions") or []


REFUSED = "Cannot execute multiple commands at once"


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in content)
    return "" if content is None else str(content)


def _calls(messages: list[dict]):
    """(step, tool name, arguments dict) of every tool call that ran, in order; step counts assistant messages
    from 1. A terminal call the sandbox refused as several commands did nothing and is left out."""
    refused = {m.get("tool_call_id") for m in messages if m.get("role") == "tool" and REFUSED in _text(m.get("content"))[:600]}
    step = 0
    for m in messages:
        if m.get("role") != "assistant":
            continue
        step += 1
        for tc in m.get("tool_calls") or []:
            if tc.get("id") is not None and tc.get("id") in refused:
                continue
            fn = tc.get("function") or {}
            a = fn.get("arguments")
            if isinstance(a, str):
                try:
                    a = json.loads(a)
                except Exception:
                    a = {"raw": a}
            yield step, fn.get("name"), a if isinstance(a, dict) else {}


def _facts(job: tuple[str, str]) -> dict | None:
    path, dataset = job
    try:
        e = json.load(open(path))
    except Exception as exc:  # a half-written file of a run still in progress
        return {"file": path, "error": f"unreadable: {exc}"}
    task = (e.get("task") or {}).get("id") or (e.get("task") or {}).get("task_id")
    cfg = os.path.join(dataset, str(task), "tests", "config.json")
    if not os.path.isfile(cfg):
        return {"file": path, "error": f"no gold patch for {task} under {dataset}"}
    gold, _ = read_patch(json.load(open(cfg))["patch"])
    art = e.get("artifacts") or {}
    outs = art.get("workflow_outputs") or {}
    mine, new = read_patch(art.get("patch") or "")
    keep_created = {f for f in mine if f not in new} | set(gold)  # a created file is a source edit only here
    scratch = new - set(gold)
    created_here: set[str] = set()

    def counts(rel: str, creates: bool) -> bool:
        if rel in keep_created:
            return True
        if creates:
            created_here.add(rel)
            return False
        return rel not in scratch and rel not in created_here

    messages = _messages(e)
    n_steps = sum(1 for m in messages if m.get("role") == "assistant")
    first_doc = first_edit = last_edit = first_report = None
    doc_steps, edit_steps = [], []
    helpers: set[str] = set()
    for step, tool, a in _calls(messages):
        is_doc = is_edit = False
        h = helper_written(tool, a)
        if h:
            helpers.add(h)
        if tool == "file_editor":
            p = str(a.get("path", ""))
            command = a.get("command")
            write = command in ("create", "str_replace", "insert", "undo_edit")
            is_doc = write and p.startswith(SPEC_DIR) and "/verify/" not in p and p.endswith(".md")
            rel = repo_rel(p, False) if write else None
            is_edit = bool(rel) and counts(rel, command == "create")
            if is_doc and p.endswith("final-verification.md") and first_report is None:
                first_report = step
        elif tool == "terminal":
            cmd = str(a.get("command", ""))
            head = cmd.split("<<", 1)[0]
            target = re.search(r"(?:>>?|\btee\s+(?:-a\s+)?)\s*[\"']?(" + SPEC_REF + r"[^\s\"']*\.md)", head)
            if not target and re.search(r"\bcd\s+[\"']?" + SPEC_REF, head):  # cd into the spec folder, then a relative file
                target = re.search(r"(?:>>?|\btee\s+(?:-a\s+)?)\s*[\"']?([\w./-]+\.md)", head)
            is_doc = bool(target) and "verify/" not in target.group(1)
            if is_doc and "final-verification.md" in target.group(1) and first_report is None:
                first_report = step
            is_edit = not is_doc and terminal_source_edit(cmd, helpers, counts)
        if is_doc:
            doc_steps.append(step)
            first_doc = first_doc or step
        if is_edit:
            edit_steps.append(step)
            first_edit = first_edit or step
            last_edit = step

    def has(suffix: str) -> bool:
        return any(k.endswith(suffix) and (v or "").strip() for k, v in outs.items())

    return {
        "file": os.path.basename(path), "task": task, "solved": bool(e.get("is_correct")), "stage": stage_of(mine, gold, new),
        "termination": e.get("termination_reason"), "n_steps": n_steps, "started": bool(messages),
        "has_requirements": has("requirements.md"), "has_spec": has("/spec.md"), "has_tasks": has("/tasks.md"), "has_report": has("final-verification.md"),
        "first_doc": first_doc, "first_edit": first_edit, "last_edit": last_edit, "first_report": first_report,
        "edit_steps": len(set(edit_steps)),
        "edits_after_first_doc": len({s for s in edit_steps if first_doc is not None and s > first_doc}),
        "docs_before_first_edit": len({s for s in doc_steps if first_edit is None or s < first_edit}),
    }


def load(dirs: list[str], dataset: str, workers: int) -> tuple[list[dict], list[dict]]:
    files: list[str] = []
    for d in dirs:
        found = sorted(glob.glob(os.path.join(d, "**", "episode_*.json"), recursive=True))
        if not found:
            print(f"warning: no episode_*.json under {d}", file=sys.stderr)
        files += found
    jobs = [(f, dataset) for f in files]
    if workers > 1 and len(jobs) > 8:
        with Pool(workers) as pool:
            rows = pool.map(_facts, jobs, chunksize=8)
    else:
        rows = [_facts(j) for j in jobs]
    good = [r for r in rows if r and "error" not in r]
    bad = [r for r in rows if r and "error" in r]
    return good, bad


def pct(a: float, b: float) -> str:
    return f"{100 * a / b:.1f}" if b else "-"


def metrics(rows: list[dict], weights: list[float] | None = None) -> dict[str, float]:
    """Resolve rate, share without a source patch, share and resolve rate of same_spot rollouts (weighted)."""
    w = weights if weights is not None else [1.0] * len(rows)
    n = sum(w)
    spot = sum(x for r, x in zip(rows, w) if r["stage"] == "same_spot")
    nan = float("nan")
    return {
        "resolve": sum(x for r, x in zip(rows, w) if r["solved"]) / n if n else nan,
        "no_patch": sum(x for r, x in zip(rows, w) if r["stage"] == "no_source_patch") / n if n else nan,
        "spot_share": spot / n if n else nan,
        "spot_resolve": sum(x for r, x in zip(rows, w) if r["stage"] == "same_spot" and r["solved"]) / spot if spot else nan,
    }


def compare(a: list[dict], b: list[dict], draws: int = 2000) -> list[tuple[str, float, float, float, int]]:
    """Task-paired difference b - a for each metric, with a bootstrap over tasks. Returns (name, diff, lo, hi, tasks).

    Every task weighs the same in both conditions whatever its number of attempts (each rollout weighs
    1 / attempts of its task), so a condition pooled from runs with different attempt counts is not tilted
    toward the tasks that were run more often."""
    ta, tb = defaultdict(list), defaultdict(list)
    for r in a:
        ta[r["task"]].append(r)
    for r in b:
        tb[r["task"]].append(r)
    tasks = sorted(set(ta) & set(tb))
    rnd = random.Random(0)
    names = [("resolve", "해결률"), ("no_patch", "소스 patch 없는 rollout 비율"), ("spot_resolve", "같은 자리 rollout의 해결률"), ("spot_share", "같은 자리 rollout 비율")]

    def one(groups: dict, ts: list[str]) -> dict[str, float]:
        rows = [r for t in ts for r in groups[t]]
        return metrics(rows, [1.0 / len(groups[t]) for t in ts for _ in groups[t]])

    def diff(ts: list[str]) -> dict[str, float]:
        ma, mb = one(ta, ts), one(tb, ts)
        return {k: mb[k] - ma[k] for k, _ in names}

    point = diff(tasks) if tasks else {k: float("nan") for k, _ in names}
    samples = [diff([rnd.choice(tasks) for _ in tasks]) for _ in range(draws)] if tasks else []
    out = []
    for k, label in names:
        vals = sorted(s[k] for s in samples if s[k] == s[k])
        lo = vals[int(0.025 * len(vals))] if vals else float("nan")
        hi = vals[int(0.975 * len(vals)) - 1] if vals else float("nan")
        out.append((label, 100 * point[k], 100 * lo, 100 * hi, len(tasks)))
    return out


def report(runs: dict[str, list[dict]], errors: dict[str, list[dict]], pairs: list[tuple[str, str]]) -> str:
    L: list[str] = []
    L += ["## 해결률과 단계", "",
          "| 조건 | rollout 수 | 과제 수 | 과제당 시도 수 최소 | 과제당 시도 수 최대 | 시작 못 한 rollout 수 | 해결률 (%) | 소스 patch 없음 (%) | 같은 자리 (%) | 같은 자리의 해결률 (%) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for name, rows in runs.items():
        m = metrics(rows)
        per = Counter(r["task"] for r in rows)
        L.append(f"| {name} | {len(rows)} | {len(per)} | {min(per.values(), default=0)} | {max(per.values(), default=0)} | {sum(not r['started'] for r in rows)} | "
                 f"{100 * m['resolve']:.1f} | {100 * m['no_patch']:.1f} | {100 * m['spot_share']:.1f} | {100 * m['spot_resolve']:.1f} |")
    L += ["", "- 이 표의 비율은 rollout을 그대로 합친 값임 (과제당 시도 수가 다르면 시도가 많은 과제가 더 크게 들어감)",
          "- 시작 못 한 rollout은 trajectory가 없는 것임 (이미지 빌드 실패 등). 해결률의 분모에 들어감", ""]
    L += ["## 단계별 rollout 비율 (%)", "", "| 조건 | " + " | ".join(STAGES) + " |", "|---|" + "---|" * len(STAGES)]
    for name, rows in runs.items():
        c = Counter(r["stage"] for r in rows)
        L.append(f"| {name} | " + " | ".join(pct(c[s], len(rows)) for s in STAGES) + " |")
    L += ["", "## 단계별 해결률 (%)", "", "| 조건 | " + " | ".join(STAGES) + " |", "|---|" + "---|" * len(STAGES)]
    for name, rows in runs.items():
        L.append(f"| {name} | " + " | ".join(pct(sum(r["solved"] for r in rows if r["stage"] == s), sum(r["stage"] == s for r in rows)) for s in STAGES) + " |")
    L += ["", "## 같은 자리 rollout: 소스 수정 step 수별 (근사)", "",
          "| 조건 | 1회 이하, 비율 (%) | 1회 이하, 해결률 (%) | 2회, 비율 (%) | 2회, 해결률 (%) | 3회 이상, 비율 (%) | 3회 이상, 해결률 (%) | 수정 step을 못 찾은 rollout 수 |", "|---|---|---|---|---|---|---|---|"]
    for name, rows in runs.items():
        spot = [r for r in rows if r["stage"] == "same_spot"]
        cells = []
        for f in (lambda r: r["edit_steps"] <= 1, lambda r: r["edit_steps"] == 2, lambda r: r["edit_steps"] >= 3):
            x = [r for r in spot if f(r)]
            cells += [pct(len(x), len(spot)), pct(sum(r["solved"] for r in x), len(x))]
        L.append(f"| {name} | " + " | ".join(cells) + f" | {sum(r['edit_steps'] == 0 for r in spot)} |")
    L += ["", "- 수정 step은 도구 호출의 명령 글에서 읽은 근사임. 같은 자리를 고쳤는데 수정 step을 못 찾은 rollout은 \"1회 이하\"에 들어감", ""]
    L += ["## 워크플로를 따랐는지 (시작한 rollout 대비 %, 도구 호출에서 읽은 근사)", "",
          "| 조건 | requirements.md 있음 | spec.md 있음 | tasks.md 있음 | 보고서 있음 | 첫 소스 수정이 첫 문서 작성보다 앞 | 문서를 쓰기 시작한 뒤 소스를 수정함 | 소스 수정이 한 번도 없음 |", "|---|---|---|---|---|---|---|---|"]
    for name, rows in runs.items():
        s = [r for r in rows if r["started"]]
        n = len(s)
        L.append(f"| {name} | {pct(sum(r['has_requirements'] for r in s), n)} | {pct(sum(r['has_spec'] for r in s), n)} | {pct(sum(r['has_tasks'] for r in s), n)} | {pct(sum(r['has_report'] for r in s), n)} | "
                 f"{pct(sum(1 for r in s if r['first_edit'] is not None and (r['first_doc'] is None or r['first_edit'] < r['first_doc'])), n)} | "
                 f"{pct(sum(1 for r in s if r['edits_after_first_doc'] > 0), n)} | {pct(sum(1 for r in s if r['first_edit'] is None), n)} |")
    L += ["", "- 문서는 spec 폴더 아래의 .md 파일 (verify/ 제외)을 쓰는 호출로 셈",
          "- `s2after` 가 지침대로 돌았다면 \"첫 소스 수정이 첫 문서 작성보다 앞\"이 높고 문서 넷이 있어야 함. \"문서를 쓰기 시작한 뒤 소스를 수정함\"은 문서 단계에서 코드를 다시 건드린 비율임 (실패한 테스트를 고친 것도 포함됨)",
          "- 대조와 `s4prompt`, `p1nofix` 는 \"첫 소스 수정이 첫 문서 작성보다 앞\"이 0에 가까워야 함", ""]
    for a, b in pairs:
        L += [f"## 비교: {b} − {a} (같은 과제끼리 짝지음, 과제마다 같은 무게, 과제를 다시 뽑는 bootstrap 2000회)", "", "| 지표 | 차이 (%p) | 95% 구간 하한 (%p) | 95% 구간 상한 (%p) | 과제 수 |", "|---|---|---|---|---|"]
        for label, d, lo, hi, n in compare(runs[a], runs[b]):
            L.append(f"| {label} | {d:+.1f} | {lo:+.1f} | {hi:+.1f} | {n} |")
        L.append("")
    bad = {k: v for k, v in errors.items() if v}
    if bad:
        L += ["## 읽지 못한 파일", ""] + [f"- {k}: {len(v)}건, 예: {v[0]['error']}" for k, v in bad.items()] + [""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", action="append", required=True, metavar="LABEL=DIR[,DIR...]")
    ap.add_argument("--compare", action="append", nargs=2, default=[], metavar=("A", "B"))
    ap.add_argument("--dataset", default=os.path.join(os.environ.get("RLLM_HOME", os.path.expanduser("~/.rllm")), "datasets", "swebench_verified_all"))
    ap.add_argument("--out", help="write the report here as well as to stdout")
    ap.add_argument("--rows", help="write the per-rollout rows here (jsonl), for a closer look")
    ap.add_argument("--workers", type=int, default=min(16, os.cpu_count() or 1))
    args = ap.parse_args()
    if not os.path.isdir(args.dataset):
        print(f"dataset folder not found: {args.dataset} (give --dataset)", file=sys.stderr)
        return 2
    runs: dict[str, list[dict]] = {}
    errors: dict[str, list[dict]] = {}
    for spec in args.run:
        label, _, dirs = spec.partition("=")
        if not dirs:
            print(f"--run needs LABEL=DIR, got {spec!r}", file=sys.stderr)
            return 2
        runs[label], errors[label] = load([d for d in dirs.split(",") if d], args.dataset, args.workers)
    for a, b in args.compare:
        if a not in runs or b not in runs:
            print(f"--compare {a} {b}: unknown label (have {', '.join(runs)})", file=sys.stderr)
            return 2
    text = report(runs, errors, [tuple(p) for p in args.compare])
    print(text)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
    if args.rows:
        with open(args.rows, "w") as f:
            for label, rows in runs.items():
                for r in rows:
                    f.write(json.dumps({"run": label, **r}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
