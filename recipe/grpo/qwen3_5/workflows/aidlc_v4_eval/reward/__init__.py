"""aidlc_v4_eval: the AI-DLC workflow scored with the rubric bands **and** the content checks.

    rubric/             the offline adherence rubric, vendored byte-identical (see rubric/__init__.py)
    episode.py          rLLM Episode -> rubric Run
    compliance.py       facts -> six signals in [0, 1] (order_v6, s1..s5) and their mean
    _claims.py          trajectory index, report readers, verdict reductions (shared machinery of the
                        content checks, kept here so this package is self-contained)
    content_checks.py   the five stage artifacts' claims against the trajectory (evidence / temporal /
                        consistency), 38 checks, each 1 / 0.5 / 0 or not applicable
    evaluator.py        collect_artifacts + score = the compliance signals plus aidlc/content*,
                        aidlc/content_{evidence,temporal,consistency}, aidlc/content_contradictions,
                        aidlc/check/<name> and the milestone-1 evaluation rubric's items (aidlc/entry,
                        aidlc/reports, aidlc/fidelity, aidlc/rubric with order_v6 as its order item);
                        plugged into workflow_scoring.ComplianceEvaluation

``rubric/``, ``episode.py`` and ``compliance.py`` are copies of ``workflows/aidlc_v4/reward``'s (commit
4c3ee52c), so ``aidlc/compliance`` and the signals behind it score as aidlc_v4's do, but no longer move
with it. ``aidlc/compliance`` stays the reward signal -- the content signals are logged.
"""
