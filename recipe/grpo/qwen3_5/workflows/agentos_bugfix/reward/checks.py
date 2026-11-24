"""agentos_bugfix plugin kinds: agentos_v2's, one for one, under ``agentos_bugfix.<name>``.

The two workflows share the spec folder, tasks.md's shape, the check scripts and PHASE 3, so the rules are the same
functions (``..agentos_v2.reward.checks``); only the names differ, because a rubric's plugin kinds carry its workflow's
prefix. What differs between the documents is passed as a parameter (``report``'s ``suite_section``).
"""

from ....workflow_rubric.checks import REGISTRY, Kind, register_shell_vars
from ...agentos_v2.reward import checks as _v2  # registers agentos_v2.*

for _name, _kind in list(REGISTRY.items()):
    if _name.startswith("agentos_v2."):
        _alias = "agentos_bugfix." + _name.split(".", 1)[1]
        REGISTRY.setdefault(_alias, Kind(_alias, _kind.fn, dict(_kind.params), _kind.availability, _kind.common, _kind.doc, dict(_kind.choices)))

register_shell_vars("agentos_bugfix", _v2.spec_folder_vars)  # the same shape-spec.md snippet, the same variables

# the agentos_bugfix.penalty kind (the log_only penalty items) lives in penalty.py; imported last so that loading this
# module registers every kind the rubric names
from . import penalty as _penalty  # noqa: E402, F401
from . import task_text as _task_text  # noqa: E402, F401  -- the kinds that read the task description
from . import stages as _stages  # noqa: E402, F401  -- stage carried out, document read ahead (the three_signals aggregate)
