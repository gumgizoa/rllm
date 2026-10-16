"""Workflow compliance from a rubric: one schema, one engine, a thin ``eval.py`` per workflow.

A workflow's verifier is a ``rubric.yaml`` (:mod:`.schema`) generated from the documents the agent
sees (``workflows/<name>/docs``, the instruction, the system prompt) by :mod:`.generator`, and this
package interprets it:

    trace/        rLLM episode (or a harbor ATIF trajectory, ``offline/``) -> ``trace.model.Run``
    collect.py    what the run left in the sandbox, read before the verifier -> ``context.Collected``
    facts.py      Run + Collected -> ``context.Facts`` (doc reads, writes and their replay, test runs,
                  repo edits, stage windows), the only things checks look at
    checks/       one function per check kind; workflow plugins register ``<wf>.<name>`` kinds
    engine.py     every item -> pass / fail / unavailable with a score in [0, 1]
    aggregate.py  items -> stage scores and signals by the rubric's own ``scoring`` block
    evaluation.py ``RubricEvaluation``: the ``workflow_scoring.ComplianceEvaluation`` a workflow's
                  ``reward/eval.py`` subclasses

Nothing at reward time calls a model: the rubric is data, the engine is rules. See
``docs/guides/workflows/generating-a-verifier.md``.
"""
