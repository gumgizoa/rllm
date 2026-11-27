"""speckit_bug_repro's penalty item: the repository's code was run before the assessment proposed a remediation.

    pytest recipe/grpo/qwen3_5/tests/test_repro_penalty.py

The item is the fourth of ``speckit_bug/penalty`` under speckit_bug_repro only; speckit_bug keeps its three.
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RECIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECIPE.parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_aidlc_reward import _call, episode  # noqa: E402

from recipe.grpo.qwen3_5 import workflows  # noqa: E402
from recipe.grpo.qwen3_5.workflows.speckit_bug.reward.eval import Evaluation as BaseEvaluation  # noqa: E402
from recipe.grpo.qwen3_5.workflows.speckit_bug_repro.reward import checks  # noqa: E402
from recipe.grpo.qwen3_5.workflows.speckit_bug_repro.reward.eval import Evaluation  # noqa: E402

BUG = "/tmp/speckit/bugs/issue"
ITEM = "speckit_bug.assess.penalty.reproduction.before_remediation"
SIG = "speckit_bug/assess.penalty.reproduction.before_remediation"
APPLIES = "speckit_bug/penalty_applies.reproduction.before_remediation"
META = {"workdir": "/testbed", "instruction": "`UserAdmin` breaks with to_field: PasswordResetForm link is a 404."}
DJANGO = SimpleNamespace(id="django__django-16139", metadata=META)

ASSESSMENT = """# Bug Assessment: x

## Reproduction

1. python -c '...'
2. 404

## Proposed Remediation

**Preferred**: build the link from the pk.

**Files likely to change**:
- `django/contrib/auth/forms.py`
"""
SKELETON = "# Bug Assessment: x\n\n## Reproduction\n\n## Proposed Remediation\n\n"
FIX = "# Fix Report\n\n## Changes\n\n| File | Change | Notes |\n|------|--------|-------|\n| `django/contrib/auth/forms.py` | modified | link |\n\n## Deviations from Assessment\n\nNone\n"
FILES = {f"{BUG}/assessment.md": ASSESSMENT, f"{BUG}/fix.md": FIX}


def sh(command: str, observation: str = "ok\n[Command finished with exit code 0]"):
    return ("terminal", {"command": command}, observation)


def write(path: str, text: str):
    return ("file_editor", {"command": "create", "path": path, "file_text": text}, f"File created successfully at: {path}")


ASSESS = write(f"{BUG}/assessment.md", ASSESSMENT)
EDIT = ("file_editor", {"command": "str_replace", "path": "/testbed/django/contrib/auth/forms.py", "old_str": "a", "new_str": "b"}, "The file /testbed/django/contrib/auth/forms.py has been edited.")
REPORT = write(f"{BUG}/fix.md", FIX)
INLINE = sh("cd /testbed && python -c \"from django.contrib.auth.admin import UserAdmin; print(UserAdmin.form().fields['password'].help_text)\"")
RAN_4 = "....\n" + "-" * 70 + "\nRan 4 tests in 0.120s\n\nOK\n[Command finished with exit code 0]"
TEST_RUN = sh("cd /testbed && python tests/runtests.py auth_tests.test_forms", RAN_4)


@pytest.fixture(scope="module")
def ev() -> Evaluation:
    return Evaluation()


def _trace(*turns):
    """The last call's observation never reaches the model (as live), so a trailing look-up closes the trace."""
    turns = [*turns, ("file_editor", {"command": "view", "path": "/speckit/core-workflow.md"}, "# core")]
    return episode([(_call(i, name, **args), obs) for i, (name, args, obs) in enumerate(turns)])


def _score(ev, *turns, task=DJANGO, files=FILES, related=None):
    collected, extra = ev.from_outputs(files)
    collected.related_tests = {"django/contrib/auth/forms.py": []} if related is None else related
    return ev.score(task, _trace(*turns), (collected, extra))


def _kept(ev, *before, task=DJANGO) -> float:
    return _score(ev, *before, ASSESS, EDIT, REPORT, task=task)[SIG]


def test_the_item_is_the_variants_alone_and_the_fourth_of_its_penalty(ev):
    pen = sorted(i.id for i in ev.rubric.items if i.id.split(".")[2] == "penalty")
    assert pen == sorted([ITEM, "speckit_bug.fix.penalty.gold_files.named", "speckit_bug.fix.penalty.scope_consistency.recorded", "speckit_bug.test.penalty.related_test_run.after_last_edit"])
    item = next(i for i in ev.rubric.items if i.id == ITEM)
    assert item.log_only and item.check.params["issue_terms"] is False
    base = BaseEvaluation().rubric
    assert ITEM not in {i.id for i in base.items}  # speckit_bug's rubric is read, not written to
    assert len(ev.rubric.items) == len(base.items) + 1
    spec, orig = workflows.WORKFLOWS["speckit_bug_repro"], workflows.WORKFLOWS["speckit_bug"]
    assert spec.penalty_signal == orig.penalty_signal == "speckit_bug/penalty" and spec.reward_signal == orig.reward_signal
    assert isinstance(spec.scorers["openhands-sdk"](), Evaluation) and not isinstance(orig.scorers["openhands-sdk"](), Evaluation)


def test_each_of_the_four_items_is_a_quarter_of_the_penalty(ev):
    done = _score(ev, INLINE, ASSESS, EDIT, REPORT)
    assert done[SIG] == 1.0 and done[APPLIES] == 1.0 and done["speckit_bug/penalty"] == 1.0
    skipped = _score(ev, ASSESS, EDIT, REPORT)
    assert skipped[SIG] == 0.0 and skipped["speckit_bug/penalty"] == pytest.approx(0.75)
    for k in ("speckit_bug/compliance", "speckit_bug/stage.assess"):
        assert done[k] == pytest.approx(skipped[k])  # log-only: compliance does not move


def test_what_counts_as_running_the_code_before_the_plan(ev):
    assert _kept(ev, INLINE) == 1.0
    assert _kept(ev, sh("cd /testbed && python - <<'EOF'\nimport django\nfrom django.db.models import Q\nprint(Q(a=1) | Q(b=2))\nEOF")) == 1.0
    assert _kept(ev, TEST_RUN) == 1.0  # a valid repository test run, whatever it selected
    script = write("/testbed/repro.py", "import django\nfrom django.contrib.auth.forms import UserChangeForm\nprint(UserChangeForm().fields)\n")
    assert _kept(ev, script, sh("cd /testbed && python repro.py")) == 1.0
    assert _kept(ev, sh("cd /testbed && cat > /tmp/r.py <<'EOF'\nfrom django.utils.html import escape\nprint(escape('<'))\nEOF\npython /tmp/r.py")) == 1.0
    assert _kept(ev, sh("cd /testbed && python -m django check")) == 1.0  # the package's own command line


def test_what_does_not_count(ev):
    assert _kept(ev) == 0.0
    assert _kept(ev, sh("cd /testbed && python -c 'import django'")) == 0.0
    assert _kept(ev, sh("cd /testbed && python -c 'import django; print(django.__version__)'")) == 0.0
    assert _kept(ev, sh("cd /testbed && python -c 'import inspect, django.forms as f; print(inspect.getsource(f.Form))'")) == 0.0
    assert _kept(ev, sh("cd /testbed && python -c \"print(open('django/forms/forms.py').read()[:200])\"")) == 0.0
    assert _kept(ev, sh("cd /testbed && python -c 'import numpy as np; print(np.zeros(2))'")) == 0.0  # not the repository's code
    assert _kept(ev, sh("cd /testbed && python -m django --version")) == 0.0
    assert _kept(ev, sh("cd /testbed && python setup.py --name")) == 0.0  # a file of the repository, not one the run wrote
    assert _kept(ev, sh("cd /testbed && python -m pytest tests/auth_tests -q", "no tests ran in 0.01s")) == 0.0  # not a valid run
    assert _kept(ev, sh("grep -rn UserAdmin /testbed/django | head")) == 0.0


def test_the_run_has_to_come_before_the_remediation_is_written(ev):
    after = _score(ev, ASSESS, INLINE, EDIT, REPORT)
    assert after[SIG] == 0.0 and after[APPLIES] == 1.0
    # a skeleton written first and filled in after the run: the plan is the write that carries the remediation
    skeleton_first = _score(ev, write(f"{BUG}/assessment.md", SKELETON), INLINE, ASSESS, EDIT, REPORT)
    assert skeleton_first[SIG] == 1.0
    # ... and a remediation that never comes leaves the first write as the plan
    never = _score(ev, write(f"{BUG}/assessment.md", SKELETON), INLINE, EDIT, REPORT, files={**FILES, f"{BUG}/assessment.md": SKELETON})
    assert never[SIG] == 0.0


def test_a_run_without_an_assessment_stands_outside_the_item_and_is_worth_nothing(ev):
    s = _score(ev, INLINE, EDIT, files={})
    assert s[SIG] == 0.0 and s[APPLIES] == 0.0


def test_the_repositorys_own_runner_on_a_test_file_the_run_wrote(ev):
    task = SimpleNamespace(id="pytest-dev__pytest-7205", metadata={"workdir": "/testbed", "instruction": "--setup-show with a bytes parameter raises BytesWarning"})
    own = write("/testbed/test_repro.py", "import unittest\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        pass\n")
    run = sh("cd /testbed && python -m pytest test_repro.py --setup-show", "1 passed in 0.01s\n[Command finished with exit code 0]")
    assert _kept(ev, own, run, task=task) == 1.0  # not a valid run of repository tests, but pytest is the code under test
    assert _kept(ev, own, run) == 0.0  # in django's repository the same file runs nothing of django
    in_dir = [write("/testbed/repro_dir/test_a.py", "def test_a():\n    pass\n"), sh("cd /testbed && python -m pytest repro_dir/ -q", "1 passed in 0.01s\n[Command finished with exit code 0]")]
    assert _kept(ev, *in_dir, task=task) == 1.0  # a directory the run made
    assert _kept(ev, sh("cd /testbed && python -m pytest /tmp/nothing_here/ -q", "no tests ran in 0.01s"), task=task) == 0.0
    spawn = write("/testbed/repro.py", "import subprocess\nprint(subprocess.run(['python', '-m', 'pytest', 'x.py'], capture_output=True).stdout)\n")
    assert _kept(ev, spawn, sh("cd /testbed && python repro.py"), task=task) == 1.0


def test_issue_terms_asks_scripts_and_inline_code_to_name_something_of_the_issue(ev):
    strict = Evaluation()  # its own rubric object: the bound ``score`` of a copy would still read the original's
    next(i for i in strict.rubric.items if i.id == ITEM).check.params["issue_terms"] = True
    other = sh("cd /testbed && python -c 'from django.db.models.fields import Field; print(Field.class_lookups)'")
    assert _kept(ev, other) == 1.0 and _kept(strict, other) == 0.0
    assert _kept(strict, INLINE) == 1.0  # names UserAdmin
    assert _kept(strict, TEST_RUN) == 1.0  # a test run is taken as it is
    nameless = SimpleNamespace(id=DJANGO.id, metadata={"workdir": "/testbed", "instruction": "The admin page is slow."})
    assert _kept(strict, other, task=nameless) == 1.0  # an issue that names nothing asks nothing


def test_issue_terms_and_package_names():
    issue = "`UserAdmin` with to_field: see https://example.com/some_page and <img src='x_y.png'>\n\n    form = PasswordResetForm(data)\n\ncalling foo.bar(x) raises TypeError in django.contrib"
    terms = checks.issue_terms(issue, ["django"])
    assert {"UserAdmin", "to_field", "PasswordResetForm", "form", "foo", "bar", "contrib"} <= terms
    assert not terms & {"django", "TypeError", "some_page", "x_y", "https", "calling", "with", "data"}  # ``data``: a word every snippet holds
    table = checks.packages_table()
    assert table["django__django"] == ("django",) and table["getmoto__moto"] == ("moto",)
    assert table["pytest-dev__pytest"] == ("_pytest", "pytest") and table["matplotlib__matplotlib"] == ("matplotlib", "mpl_toolkits")
    assert all(names for names in table.values())
    assert checks.package_of("src/_pytest/setuponly.py") == "_pytest" and checks.package_of("setup.py") is None and checks.package_of("README.rst") is None
    assert checks.inputs(SimpleNamespace(id="getmoto__moto-4986:0", instruction="x"), None)["packages"] == ["moto"]
    assert checks.inputs(SimpleNamespace(id="unknown__task-1", metadata={"instruction": "the issue"}), None) == {"gold_files": None, "issue": "the issue", "packages": []}


def test_a_repository_the_table_does_not_know_takes_its_packages_from_the_change(ev):
    task = SimpleNamespace(id="unknown__task-1", metadata=META)
    assert _kept(ev, INLINE, task=task) == 1.0  # the run changed django/..., so django is the package
    assert _kept(ev, sh("cd /testbed && python -c 'import numpy as np; print(np.zeros(2))'"), task=task) == 0.0


def test_the_evaluation_survives_pickling(ev):
    back = pickle.loads(pickle.dumps(ev))
    assert ITEM in {i.id for i in back.rubric.items}
    assert _score(back, INLINE, ASSESS, EDIT, REPORT)[SIG] == 1.0
