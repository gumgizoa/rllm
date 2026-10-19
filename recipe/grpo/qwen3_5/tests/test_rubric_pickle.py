"""A RubricEvaluation that crosses a process boundary (Ray actor) must still know its plugin kinds.

Training builds the evaluation policy in the driver and pickles it into ``VerlTaskRunner``; the
check registry is a module global filled by importing the plugin module, which unpickling does
not repeat. Before the fix every plugin-kind item scored as an engine error in the actor
(speckit_bug 19, openspec_ff 61-63 per rollout, 2026-10-16).
"""

from __future__ import annotations

import pickle

import pytest

from recipe.grpo.qwen3_5.workflow_rubric import checks


def _forget_plugin_kinds(prefixes: tuple[str, ...]) -> dict:
    """Simulate a fresh process: drop the plugin kinds from the registry, return them for restoring."""
    dropped = {k: v for k, v in checks.REGISTRY.items() if k.startswith(prefixes)}
    for k in dropped:
        del checks.REGISTRY[k]
    return dropped


@pytest.mark.parametrize(
    ("workflow", "prefixes", "probe"),
    [
        ("speckit_bug", ("speckit_bug.",), "speckit_bug.read"),
        ("openspec_ff", ("openspec_ff.", "openspec."), "openspec_ff.cli"),
        ("speckit_sdd", ("speckit_sdd.", "speckit."), "speckit_sdd.script"),
        ("agentos_v2", ("agentos_v2.",), "agentos_v2.read"),
    ],
)
def test_unpickled_evaluation_reregisters_plugin_kinds(workflow, prefixes, probe):
    mod = __import__(f"recipe.grpo.qwen3_5.workflows.{workflow}.reward.eval", fromlist=["Evaluation"])
    ev = mod.Evaluation()
    assert probe in checks.REGISTRY
    blob = pickle.dumps(ev)

    dropped = _forget_plugin_kinds(prefixes)
    assert probe not in checks.REGISTRY
    try:
        # Importing the plugin module again is a no-op for sys.modules, so re-run its registration
        # the way a fresh interpreter would: by executing the module body.
        import importlib
        import sys

        for name in ev.plugins:
            sys.modules.pop(name, None)
        restored = pickle.loads(blob)
        assert probe in checks.REGISTRY, "unpickling must re-register the workflow's check kinds"
        assert restored.plugins == ev.plugins
        # and resolve() repeats it, for any path that bypasses __setstate__
        _forget_plugin_kinds(prefixes)
        for name in ev.plugins:
            sys.modules.pop(name, None)
        restored._load_plugins()
        assert probe in checks.REGISTRY
        importlib.invalidate_caches()
    finally:
        checks.REGISTRY.update(dropped)
