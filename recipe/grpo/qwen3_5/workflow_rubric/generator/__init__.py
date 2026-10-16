"""Offline generator: a workflow's documents -> ``reward/rubric.yaml`` (DESIGN §10, G0-G9).

The rubric must be traceable to what the agent actually sees, so every stage either derives items
by rule from the files in the workflow package or asks a model and then checks the answer against
those files again::

    G0 manifest.py   SPEC -> every file the agent sees, with role, sha256 and upstream line map
    G1 parse.py      markdown structure + modal sentence candidates (deterministic dictionary)
    G2 templates.py  template skeletons -> structure/content items, one line class at a time
    G3 extract.py    stage model (stages, artifacts, roots, vars) -- fixed in config or asked
    G4 extract.py    normative statements, in the pilot ``*.statements.jsonl`` format
    G5 extract.py    statement -> items in the closed kind vocabulary, 3 samples voted
    G6 ground.py     quotes, parameter literals, modality, adapter whitelist, overrides
    G7 critic.py     coverage / refutation / conflicts, until two dry rounds
    G8 compile.py    dedup, precedence, scope, ids -> rubric.yaml, rubric.md, rubric.lock, eval.py
    G9 selftest.py   golden run + exploit mutations scored with the built rubric (``--selftest``)

Model calls (``llm.py``) are cached by content hash so a committed cache rebuilds the rubric
without a model (``--llm cache-only``). See ``docs/guides/workflows/generating-a-verifier.md``.

    python -m recipe.grpo.qwen3_5.workflow_rubric.generator build <workflow> [--llm ...] [--out DIR]
"""

VERSION = "0.1"
TOOL = "workflow_rubric.generator"
