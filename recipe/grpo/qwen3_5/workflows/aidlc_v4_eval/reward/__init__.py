"""aidlc_v4_eval: the AI-DLC workflow scored with the rubric bands **and** the content checks.

    _claims.py          trajectory index, report readers, verdict reductions (shared machinery of the
                        content checks, kept here so this package is self-contained)
    content_checks.py   the five stage artifacts' claims against the trajectory (evidence / temporal /
                        consistency), 38 checks, each 1 / 0.5 / 0 or not applicable
    evaluator.py        collect_artifacts + score = aidlc_v4's compliance signals plus aidlc/content*,
                        aidlc/content_{evidence,temporal,consistency}, aidlc/content_contradictions and
                        aidlc/check/<name>; plugged into workflow_scoring.ComplianceEvaluation

The documents, instruction and system prompt are aidlc_v4's (``workflows/aidlc_v4``), reused by path, so
the agent sees exactly the same workflow; only the scorer differs. ``aidlc/compliance`` stays the reward
signal -- the content signals are logged. Rubric and adapter come from ``aidlc_v4.reward``.
"""
