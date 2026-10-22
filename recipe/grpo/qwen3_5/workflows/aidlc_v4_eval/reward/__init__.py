"""aidlc_v4_eval's verifier: the workflow's atomic rules as ``rubric.yaml``, on the common rubric engine.

    rubric.yaml   the rules: one item per measurement (its atomic rule, category, stage and the document
                  lines it comes from), the ``kind_matrix`` aggregate, the rules no item measures and why
    eval.py       the evaluation policy (``workflow_rubric.RubricEvaluation``)
    checks.py     the ``aidlc_v4_eval.*`` check kinds: the run measured once, each item reads its value
    claims.py     content checks: each artifact claim against the trajectory
    rules.py      rule checks and atomic checks: what the run did, whatever its artifacts claim
    judge.py      the LLM judge for the content rules code cannot decide (off unless configured)
    read.py       reading a run: report fields, test runs, exit codes, the trajectory index, whole-run readings
    trace.py      trajectory -> Run, what shell commands do (copied from the vendored rubric)
    skeleton.py   the artifact skeletons and parser (copied from the vendored rubric)

The milestone-1 scoring (``aidlc/compliance``, ``aidlc/rubric``) is ``../legacy``, plugged in by the spec.
"""
