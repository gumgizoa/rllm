"""aidlc_v4_eval: the AI-DLC workflow scored with the rubric bands **and** the content checks.

    rubric/             the offline adherence rubric, vendored byte-identical (see rubric/__init__.py)
    episode.py          rLLM Episode -> rubric Run
    compliance.py       facts -> six signals in [0, 1] (order_v6, s1..s5) and their mean
    evidence.py         where this verifier reads a run differently from the vendored rubric: test runs
                        (Django's runner in, lookups and agent-written runner scripts out), script runs,
                        piped exit codes, final changes from the patch, test files from the task
    _claims.py          trajectory index, report readers, verdict reductions (shared machinery of the
                        content checks, kept here so this package is self-contained)
    content_checks.py   the five stage artifacts' claims against the trajectory (evidence / temporal /
                        consistency), 38 checks, each 1 / 0.5 / 0 or not applicable
    rule_checks.py      whether what the run did kept the workflow's rules, whatever its artifacts claim
                        (test files untouched, targeted stage-5 tests, no environment setup, no stage-4
                        reproduction run, artifacts written once, a clean repository): aidlc/rule*
    atomic_checks.py    the atomic rules the other checks leave unscored, where code can judge them: aidlc/atom/*
    judge.py            an LLM's yes / no on the content rules code cannot decide, one call per stage
                        artifact, each answer kept only if its quote is in the material: aidlc/judge/*
    categories.py       every measured rule placed by kind x stage: aidlc/cat/<kind><stage>, aidlc/kind/<kind>,
                        and their total aidlc/score (each kind alike; a stage not carried out scores 0)
    evaluator.py        collect_artifacts + score = the compliance signals plus aidlc/content*,
                        aidlc/content_{evidence,temporal,consistency}, aidlc/content_contradictions,
                        aidlc/check/<name> and the milestone-1 evaluation rubric's items (aidlc/entry,
                        aidlc/reports, aidlc/fidelity, aidlc/rubric with order_v6 as its order item),
                        the rule checks and the solution-leak flags (aidlc/leak_history, aidlc/leak_apply);
                        plugged into workflow_scoring.ComplianceEvaluation

``rubric/`` and ``episode.py`` are byte-identical copies of ``workflows/aidlc_v4/reward``'s (commit
4c3ee52c); ``compliance.py`` is a copy whose stage gate reads test runs through ``evidence.py``. None of
them moves with aidlc_v4. The headline is ``aidlc/score``, the kind x stage matrix's total; ``aidlc/compliance``
and ``aidlc/rubric`` are kept for comparison with earlier evaluations.
"""
