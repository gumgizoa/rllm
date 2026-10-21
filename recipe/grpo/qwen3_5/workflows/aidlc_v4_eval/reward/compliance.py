"""The six AI-DLC compliance signals, each in [0, 1], and their equal-weight mean.

    order   order_v6: 2/3 read/write chain + 1/3 read prefix  (aidlc-reward-lab eval-variants)
    s1..s5  the rubric's v4-profile stage bands 8/5/2/0 -> 1, 4/7, 2/7, 0, with its gates:
            frontmatter must be valid, and stages 1 and 5 are capped at band 5 when no real
            test suite ever ran (a baseline never observed cannot have been reported truthfully)

The stage bands come from the vendored rubric unchanged, graded on the files read out of the
sandbox; a stage with no file there scores 0. Stage weights (12/12/12/19/12) do not enter: each
stage is normalised to its own maximum, so the six signals weigh the same in the mean.

order_v6
    Events r1..r5 (first read of rule doc k) and w1..w5 (first write of stage k's artifact).
    chain: of the 9 adjacent pairs of r1 < w1 < r2 < w2 < ... < r5 < w5, how many hold.
    prefix: first reads in time order must start at 01 and run consecutively; the length of that
    run (1,2,3 -> 3; 2,1,3,4,5 -> 0; 1,3 -> 1).
    Stage docs whose first read shares a step with another stage doc were read by one command:
    they earn no read credit, in the chain or the prefix.

    w_k is the first step that wrote the artifact's path, counted only when the file exists at
    the end of the run. The rubric's own ``stage_artifact_step`` is not used for this: when a
    shell write cannot be reconstructed it falls back to the run's last step, which would break
    the chain for an artifact that was in fact written in its stage.
"""

from __future__ import annotations

from collections import Counter

from .rubric import artifacts as A
from .rubric import facts as F
from .rubric import score as S
from .rubric.model import Run

DOCS = ["01", "02", "03", "04", "05"]
SIGNALS = ["order", "s1", "s2", "s3", "s4", "s5"]
W_CHAIN, W_PREFIX = 2 / 3, 1 / 3


def artifact_write_steps(run: Run) -> dict[int, int | None]:
    first: dict[int, int] = {}
    for step in run.steps:
        for a in step.actions:
            if a.status == "fail":
                continue
            targets = F.write_targets(a) if a.kind == "shell" else ([a.path] if F.is_write(a) else [])
            for t in targets:
                st = A.ARTIFACT_PATHS.get(t)
                if st is not None and not (a.kind == "shell" and F._rm_matches(a.command or "", t)):
                    first.setdefault(st, step.n)
    return {st: (first.get(st) if path in run.artifact_files else None) for path, st in A.ARTIFACT_PATHS.items()}


def order_v6(read_step: dict[str, int], write_step: dict[int, int | None]) -> dict:
    counts = Counter(read_step[d] for d in DOCS if d in read_step)
    invalid = {d for d in DOCS if d in read_step and counts[read_step[d]] > 1}

    events = []
    for k, d in enumerate(DOCS, start=1):
        events.append(read_step.get(d) if d not in invalid else None)
        events.append(write_step.get(k))
    chain = sum(1 for a, b in zip(events, events[1:], strict=False) if a is not None and b is not None and a < b)

    prefix, expected = 0, 1
    for _, d in sorted((read_step[d], d) for d in DOCS if d in read_step):
        if d in invalid or int(d) != expected:
            break
        prefix += 1
        expected += 1

    return {"value": W_CHAIN * chain / 9 + W_PREFIX * prefix / 5, "chain": chain, "prefix": prefix, "invalid_multi_read": sorted(invalid)}


def stage_fractions(facts: dict) -> dict[int, float]:
    # stage_points rounds w * band_fraction; with w = 7 the fractions 1, 4/7, 2/7, 0 are exact.
    points = S.stage_points(facts, {st: 7 for st in A.STAGE_FILES})
    return {st: p / 7 for st, p in points.items()}


def compliance(run: Run) -> dict:
    """Signals, their mean, and the facts they came from (for logging).

    ``run.artifact_files`` is what the sandbox held at the end, and it is authoritative: a stage
    whose file is not there scores 0. The rubric would otherwise grade the text it reconstructs
    from the writes in the trajectory, which survives any deletion it does not recognise as one
    (``os.remove``, a script that clears /tmp) -- a file that no longer exists would still score.
    """
    facts = F.analyse(run)
    present = {A.ARTIFACT_PATHS[p] for p in run.artifact_files if p in A.ARTIFACT_PATHS}
    facts["stage_artifact_band"] = {k: (v if int(k) in present else 0) for k, v in facts["stage_artifact_band"].items()}
    order = order_v6(facts["aidlc_read_step"], artifact_write_steps(run))
    stages = stage_fractions(facts)
    signals = {"order": order["value"], **{f"s{st}": stages[st] for st in sorted(stages)}}
    return {"signals": signals, "mean": sum(signals[k] for k in SIGNALS) / len(SIGNALS), "order": order, "facts": facts}
