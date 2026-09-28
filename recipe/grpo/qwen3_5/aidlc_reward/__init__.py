"""AI-DLC compliance scoring for the openhands-sdk + AI-DLC arm.

    rubric/      the offline adherence rubric, vendored byte-identical (see rubric/__init__.py)
    episode.py   rLLM Episode -> rubric Run
    compliance.py  facts -> six signals in [0, 1] (order_v6, s1..s5) and their mean
    evaluator.py   verifier wrapper that adds the signals; evaluation policy for SandboxTaskHooks

``train.py`` installs ``AidlcEvaluation`` whenever ``recipe.aidlc.enable`` is set, and with
``recipe.aidlc.reward.enable`` folds ``aidlc/compliance`` into the reward: multiplied by default
(``mode: mul``), or ``lam * compliance`` added (``mode: add``).
"""
