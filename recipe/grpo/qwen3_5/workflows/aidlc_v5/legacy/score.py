"""The milestone-1 signals, as an extra scorer next to the rubric (``reward/eval.py``): what earlier
aidlc_v4 evaluations reported, for comparison.

    aidlc/compliance, aidlc/order, aidlc/s1..s5   the six compliance signals and their mean (compliance.py)
    aidlc/order_chain, aidlc/order_prefix         order_v6's parts
    aidlc/docs_read, aidlc/artifacts_written      counts
    aidlc/entry, aidlc/reports, aidlc/fidelity,   the milestone-1 evaluation rubric's items (rubric/score.py
    aidlc/rubric                                  profile v4: entry 3 + order 21 + reports 67 + fidelity 9,
                                                  order_v6 as the order item); fidelity and rubric only when
                                                  a patch was recorded
"""

from __future__ import annotations

import base64

from .compliance import compliance
from .episode import episode_to_run
from .rubric import artifacts as A
from .rubric import score as S

RUBRIC_WEIGHTS = {"entry": 3, "order": 21, "reports": 67, "fidelity": 9}

_MARK = "@@AIDLC "
# base64 keeps the files intact through exec's text channel; `; true` because exec raises on a
# non-zero exit and a run that wrote no artifact is not an error.
_COLLECT = f'for f in {A.ARTIFACT_DIR}/0[1-5]-*.md; do [ -f "$f" ] || continue; printf \'{_MARK}%s\\n\' "$f"; base64 -w0 "$f"; printf \'\\n\'; done; true'


def parse_collected(output: str) -> dict[str, str]:
    files, path = {}, None
    for line in (output or "").splitlines():
        if line.startswith(_MARK):
            path = line[len(_MARK) :].strip()
            continue
        if path is not None:
            if path in A.ARTIFACT_PATHS:
                files[path] = base64.b64decode(line.strip() or b"").decode("utf-8", errors="replace")
            path = None
    return files


def collect(sandbox) -> dict[str, str]:
    """Container path -> content of each stage artifact the run left in the sandbox."""
    return parse_collected(sandbox.exec(_COLLECT, timeout=60, user="root"))


def from_outputs(outputs: dict[str, str]) -> dict[str, str]:
    """``collect``'s result from a saved episode's ``workflow_outputs``."""
    return {path: text for path, text in outputs.items() if path in A.ARTIFACT_PATHS}


def score(task, episode, artifacts: dict[str, str]) -> dict[str, float]:
    run = episode_to_run(episode, artifacts, instance_id=str(getattr(task, "id", "")))
    patch = (getattr(episode, "artifacts", None) or {}).get("patch")
    run.patch = patch or ""
    c = compliance(run)
    facts = c["facts"]
    u = S.unit_scores(facts, S.PROFILES["v4"])
    u["order"] = c["order"]["value"]
    out = {
        **{f"aidlc/{k}": float(v) for k, v in c["signals"].items()},
        "aidlc/compliance": float(c["mean"]),
        "aidlc/order_chain": float(c["order"]["chain"]),
        "aidlc/order_prefix": float(c["order"]["prefix"]),
        "aidlc/docs_read": float(len(facts["stage_docs_read"])),
        "aidlc/artifacts_written": float(len(artifacts)),
        "aidlc/ran_real_test": float(bool(facts["ran_real_test_suite"])),
        "aidlc/entry": float(u["entry"]),
        "aidlc/reports": float(u["reports"]),
    }
    if patch is not None:
        out["aidlc/fidelity"] = float(u["fidelity"])
        out["aidlc/rubric"] = sum(w * u[k] for k, w in RUBRIC_WEIGHTS.items()) / sum(RUBRIC_WEIGHTS.values())
    return out


SCORER = (collect, score, from_outputs)
