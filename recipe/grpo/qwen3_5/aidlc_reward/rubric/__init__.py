"""The AI-DLC adherence rubric, vendored unchanged.

Source: aidlc-swebenchpro-evalv1, branch eval/rubric-v1-profile, commit c4130b0 --
``eval/aidlc/{model,artifacts,reports,facts,score}.py`` and ``eval/aidlc/frontends/openhands.py``.
The files are byte-identical to that commit so the training reward and the offline compliance
numbers come from one implementation. Do not edit them here: change the source and re-copy,
then update the commit above.

Only the source's ``frontends/__init__.py`` is left out -- it imports the harbor / mini-swe /
opencode loaders, which read result directories this recipe never has. The rLLM episode is
turned into a ``model.Run`` by ``aidlc_reward.episode`` instead.
"""
