"""AI-DLC compliance scoring for the openhands-sdk + AI-DLC arm.

    rubric/      the offline adherence rubric, vendored byte-identical (see rubric/__init__.py)
    episode.py   rLLM Episode -> rubric Run
    compliance.py  facts -> six signals in [0, 1] (order_v6, s1..s5) and their mean
    evaluator.py   verifier wrapper that adds the signals; evaluation policy for SandboxTaskHooks

``workflows.py`` registers ``AidlcEvaluation`` as the ``aidlc`` workflow's scorer for openhands-sdk, so
``train.py`` (``recipe.workflow.name=aidlc``) and ``rllm eval`` (``--agent-kwargs workflow=aidlc``)
install the same policy. With ``recipe.workflow.compliance_reward.enable`` train.py folds ``aidlc/compliance``
into the reward: multiplied by default (``mode: mul``), or ``lam * compliance`` added (``mode: add``).
"""
