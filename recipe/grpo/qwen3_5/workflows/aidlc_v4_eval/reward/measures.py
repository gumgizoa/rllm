"""The run, read once for every scoring method: :class:`Measures`.

A method (``methods/``) reads the run only through a ``Measures``: the readings below are computed the first time a
method asks for one and shared after that. Each measurement is computed on demand too (:meth:`Measures.value`), so
a method that raises costs its own item, not the others.

    the run       ``run`` (the trajectory as steps), ``obs`` (its index: files read / written / edited, shell
                  commands, test runs), ``parsed`` / ``p1`` .. ``p5`` (the collected artifacts, parsed), the patch
    timing        ``read_step`` (each rule document's first read), ``w`` (each artifact's first write),
                  ``w_collected`` (the same, counted only when the file was collected)
    shared by several claims or atomic rules: what changed, the baseline runs, the reproduction script, the stage-5
                  runs; each is documented where it is defined
    ``judged``    the judge's verdicts (``judge.judge_checks``), asked once when a judge item or the diagnostics
                  need them
"""

from __future__ import annotations

import re
from functools import cached_property
from statistics import mean

from recipe.grpo.qwen3_5.workflow_rubric import testread as T

from . import read as EV
from . import skeleton as A
from . import trace as F
from .judge import judge_checks
from .read import (
    SOURCE_EXT,
    _field,
    artifact_write_steps,
    claimed_paths,
    first_write_steps,
    norm_path,
    observe,
    parsed_artifacts,
    same_file,
    task_text,
)
from .trace import episode_to_run

CONTRADICTED = EV.CONTRADICTED

# A plan target that changes nothing: `common.py (verify existing fix)` (no "(modify in place)" / "(create)").
_VERIFY_ONLY = re.compile(r"\((?![^)]*\b(?:modify|create)\b)[^)]*\b(?:verify|verification|check|inspect|read|no change)\b[^)]*\)", re.I)

# A test run on stashed source (`git stash && pytest`) tests the baseline, not the change (step24 000003): the shared
# rule (``on_stash``), not a regex of this scorer's own.

def plain_segments(command: str) -> list[str]:
    """The command split at ``&&`` / ``||`` / ``;`` / newlines, quoted strings kept."""
    return [s.strip() for s in re.split(r"&&|\|\||;|\n", F.drop_heredoc_bodies(command or "")) if s.strip()]


# A test's name in an artifact field, not its file's (`tests/test_mod.py::test_parse` names test_parse only)
_TEST_NAME = re.compile(r"\b(test_\w+)(?!\w|\.py\b|/)")


def test_names(text: str | None) -> list[str]:
    return list(dict.fromkeys([*_TEST_NAME.findall(text or ""), *EV.other_test_ids(text)]))


def on_stash(command: str) -> bool:
    """A test attempt of the command runs with the change put away (``git stash && pytest x; git stash pop``): the
    shared marks (``testread.stash_flags``, R3 of the 11-24 review: ``git stash`` .. ``pop`` / ``apply``, ``git apply
    -R`` / ``patch -R`` and back)."""
    segs = plain_segments(command)
    flags, _ = T.stash_flags(F.drop_heredoc_bodies(command or ""), segs)
    return any(f and EV.is_test_attempt(s) for s, f in zip(segs, flags, strict=False))


def hidden_attempts(shell, after: int, edit_steps) -> list[tuple[int, str, str, bool]]:
    """(step, segment, output, put away) of every test attempt after step ``after``: the change put away by the shared
    marks (R3), carried from one command to the next until a mark brings it back or the run edits the repository again
    (the shared rule: a put-away change never brought back was thrown away, what is written next is a new change)."""
    edits = sorted(set(edit_steps))
    hidden, since, out = False, after, []
    for n, cmd, o in shell:
        if n <= after:
            continue
        if hidden and any(since < e <= n for e in edits):
            hidden = False
        segs = plain_segments(cmd)
        flags, after_cmd = T.stash_flags(F.drop_heredoc_bodies(cmd or ""), segs, hidden)
        out += [(n, s, o, f) for s, f in zip(segs, flags, strict=False) if EV.is_test_attempt(s)]
        if after_cmd != hidden or T.R.stash_marks(F.drop_heredoc_bodies(cmd or "")):
            since = n
        hidden = after_cmd
    return out


def _regressed(out: str, failing1: str | None, baseline_runs: list) -> bool | None:
    """The last stage-5 run fails a test that was not already failing (the shared reading, ``workflow_rubric/testread``;
    R5 / R6 of the 11-24 review): a test is already failing when, in the last baseline run that ran it, it failed by
    name. A failure the output does not name cannot be matched and is new; a baseline run that failed a test without
    naming it explains nothing. None when that cannot be told -- the run executed no test (an import or setUpClass
    error: step24 000119, 000140) -- and when there is no valid baseline run to compare with (item 23 of the review:
    step24 000123, a baseline that executed no test, is no baseline; regressions are then not judged).
    ``baseline_runs`` are the recorded selection's (an earlier attempt under the wrong settings that errored is not the
    baseline the run reports: step24 000042). ``failing1`` (what artifact 01 wrote) is no baseline run and is not read."""
    if EV.ran_no_test(out):
        return None
    valid = [o for _, _, o in baseline_runs if not EV.ran_no_test(o)]
    if not valid:
        return None
    n = EV.failures(out)
    if n <= 0:
        return False
    named = list(dict.fromkeys(EV.failed_tests(out)))
    if len(named) < n:
        return True  # a failure the output does not name is new
    for t in named:
        last = None
        for o in valid:  # the last baseline run that ran the test: it names it failed, or reads its state
            if t in EV.failed_tests(o) or EV.test_state(o, t) is not None:
                last = o
        if last is None or t not in EV.failed_tests(last):
            return True
    return False


class _Failed:
    """A measurement whose method raised: re-raised for its item alone."""

    def __init__(self, error: Exception):
        self.error = error


class Measures:
    """``files``: what was collected from the sandbox (container path -> text), the five artifacts and whatever
    else the artifact directory held. ``facts``: the shared layer's facts of the run (the engine's
    ``EvalContext.facts``), whose test runs (``evidence.runs_from``) are the ones read here; ``workdir``: the
    repository root (``Collected.workdir``); ``ctx``: the engine's context of the run, whose shared readings of the
    code change (``testread``) are the ones used here. Without them they are built from the episode
    (``read.bare_context``)."""

    def __init__(self, task, episode, files: dict[str, str], facts=None, workdir: str | None = None, ctx=None):
        self.task, self.episode, self.files = task, episode, files
        self._facts, self.workdir, self._ctx = facts if facts is not None else getattr(ctx, "facts", None), workdir, ctx
        self._values: dict[str, float | None | _Failed] = {}

    # -- measurements -------------------------------------------------------------------------------

    def value(self, key: str) -> float | None:
        """The measurement ``key`` (an item id: ``atom/H9b``, ``form/B1@3``), computed once; a method that raised
        raises again here."""
        if key not in self._values:
            from .methods import measurements

            meth, st = measurements()[key]
            try:
                v = meth.fn(self) if st is None else meth.fn(self, st)
                if v is not None and meth.timed_by_edits and self.timing_unknown:
                    v = None
                self._values[key] = None if v is None else float(v)
            except Exception as e:  # noqa: BLE001 -- the engine reports it as this item's error
                self._values[key] = _Failed(e)
        v = self._values[key]
        if isinstance(v, _Failed):
            raise v.error
        return v

    def all_values(self) -> dict[str, float | None]:
        """Every measurement, a failed one left out."""
        from .methods import measurements

        out = {}
        for key in measurements():
            try:
                out[key] = self.value(key)
            except Exception:  # noqa: BLE001
                pass
        return out

    def diagnostics(self) -> dict[str, float]:
        """Beside the matrix: the content checks' family means and contradictions, the rule checks' mean, the
        solution-leak flags, an empty patch, the judge's calls and dropped answers."""
        from .methods import load

        vals = self.all_values()
        claims = [m for m in load().values() if m.key.startswith("check/")]
        families: dict[str, list[float]] = {}
        for m in claims:
            families.setdefault(m.family, [])
            if vals.get(m.key) is not None:
                families[m.family].append(vals[m.key])
        fam_means = {f: (mean(v) if v else None) for f, v in families.items()}
        applicable = [v for v in fam_means.values() if v is not None]
        rules = [vals[m.key] for m in load().values() if m.key.startswith("rule/") and vals.get(m.key) is not None]
        history, applied = self.leaks
        return {
            **({"content": mean(applicable)} if applicable else {}),
            **{f"content_{f}": v for f, v in fam_means.items() if v is not None},
            "content_contradictions": float(sum(1 for m in claims if vals.get(m.key) == CONTRADICTED)),
            **({"rules": float(sum(rules) / len(rules))} if rules else {}),
            "leak_history": float(bool(history)),
            "leak_apply": float(bool(applied)),
            **({"patch_empty": float(not self.patch.strip())} if self.patch is not None else {}),
            **{k.removeprefix("aidlc/"): v for k, v in self.judged.items() if not k.startswith("aidlc/judge/")},
        }

    # -- the run --------------------------------------------------------------------------------------

    @cached_property
    def recorded(self) -> dict:
        return getattr(self.episode, "artifacts", None) or {}

    @cached_property
    def patch(self) -> str | None:
        """The run's final ``git diff`` as recorded, or None when none was."""
        return self.recorded.get("patch")

    @cached_property
    def whole_patch(self) -> str | None:
        """The patch when it was recorded whole (None when truncated or not recorded)."""
        return None if self.recorded.get("patch_truncated") else self.patch

    @cached_property
    def run(self):
        artifacts = {p: t for p, t in self.files.items() if p in A.ARTIFACT_PATHS}
        run = episode_to_run(self.episode, artifacts, instance_id=str(getattr(self.task, "id", "") or ""))
        run.patch = self.patch or ""
        return run

    @cached_property
    def ctx(self):
        """The shared layer's context of the run: the engine's, else one built from the episode (``read.bare_context``;
        in the repository root ``read.TEXT_CWD`` when the task names none, as the artifacts' commands are read)."""
        if self._ctx is not None and self._ctx.collected.workdir:
            return self._ctx
        from recipe.grpo.qwen3_5.workflow_rubric.evaluation import _episode_diff, _task_workdir

        self.workdir = self.workdir or _task_workdir(self.task)
        return EV.bare_context(self.episode, self.workdir or EV.TEXT_CWD, _episode_diff(self.episode))

    @cached_property
    def shared(self):
        """The shared layer's facts of the run (``workflow_rubric.facts.build``)."""
        if self._facts is not None:
            return self._facts
        from recipe.grpo.qwen3_5.workflow_rubric.evaluation import _episode_diff, _task_workdir

        self.workdir = self.workdir or _task_workdir(self.task)
        return EV.bare_facts(self.episode, self.workdir, _episode_diff(self.episode))

    @cached_property
    def runs(self) -> list:
        """The shared layer's test-runner invocations of the run (``RunFact``s of kind ``test``, valid or not)."""
        return EV.test_runs_of(self.shared)

    @cached_property
    def obs(self) -> EV.Observed:
        obs = observe(self.run, self.shared, self.workdir, ctx=self.ctx)
        recorded = self.repro_recorded
        if recorded:
            history = T.script_history(obs.ctx, recorded)
            obs.histories = {norm_path(p): history for p in recorded}
        return obs

    @cached_property
    def parsed(self) -> dict[int, dict | None]:
        return parsed_artifacts(self.run, collected=True)

    @property
    def p1(self) -> dict | None:
        return self.parsed.get(1)

    @property
    def p2(self) -> dict | None:
        return self.parsed.get(2)

    @property
    def p3(self) -> dict | None:
        return self.parsed.get(3)

    @property
    def p4(self) -> dict | None:
        return self.parsed.get(4)

    @property
    def p5(self) -> dict | None:
        return self.parsed.get(5)

    @cached_property
    def steps(self) -> list[dict]:
        """The plan's steps (artifact 03), [] without one."""
        return (self.p3 or {}).get("steps", [])

    @cached_property
    def tests(self) -> set[str]:
        """The task's test files (its ``test_patch``)."""
        return EV.task_test_files(self.task)

    @cached_property
    def final(self) -> tuple[list[str], list[str]] | None:
        """(changed, added) files of the whole patch, None without one."""
        return EV.patch_files(self.whole_patch)

    @cached_property
    def issue(self) -> str:
        return task_text(self.task) if self.task is not None else ""

    @cached_property
    def final_words(self) -> str:
        return EV.final_words(self.episode)

    @cached_property
    def art_dir(self) -> list[str]:
        """What the artifact directory held at the end, beside the five artifacts too."""
        return sorted(p for p in self.files if p.startswith(A.ARTIFACT_DIR + "/"))

    @cached_property
    def leaks(self) -> tuple[list[int], list[int]]:
        return EV.leaks(self.run)

    @cached_property
    def judged(self) -> dict[str, float]:
        return judge_checks(self.run, self.obs, self.parsed, self.whole_patch, self.task)

    # -- timing ---------------------------------------------------------------------------------------

    @cached_property
    def read_step(self) -> dict[str, int]:
        """Rule document ("core", "01".."05") -> its first read."""
        return EV.doc_reads(self.run)[1]

    @cached_property
    def w(self) -> dict[int, int | None]:
        """Stage -> the first step that wrote its artifact."""
        return first_write_steps(self.run)

    @cached_property
    def w_collected(self) -> dict[int, int | None]:
        """Stage -> the first write of its artifact, counted only when the file was collected."""
        return artifact_write_steps(self.run)

    @cached_property
    def multi_read(self) -> set[str]:
        """Stage documents first read by one command together with another."""
        return set(EV.multi_read(self.read_step))

    # -- what changed (the claims) --------------------------------------------------------------------
    # With a whole patch, what the run changed is the patch's files, not the trajectory's writes; and when the patch
    # changed a source file the trajectory never shows being edited, when the source last changed is unknown, so the
    # claims timed against the first or last edit are left out (``timed_by_edits``).

    @cached_property
    def changed_now(self) -> list[str]:
        if self.final is not None:
            return list(dict.fromkeys(norm_path(p) for p in self.final[0]))
        return list(self.obs.remaining)

    @cached_property
    def new_now(self) -> set[str]:
        return {norm_path(p) for p in self.final[1]} if self.final is not None else set(self.obs.new_files)

    @cached_property
    def edits_unknown(self) -> bool:
        return False if self.final is not None else self.obs.edits_unknown

    @cached_property
    def timing_unknown(self) -> bool:
        """The patch changed a source file no write of the trajectory shows (the shared layer's ``unseen_repo_paths``:
        a change made outside the trace, so when the code last changed is unknown)."""
        if self.final is None:
            return False
        return bool(self.unseen_sources)

    @cached_property
    def unseen_sources(self) -> list[str]:
        """Source files of the patch that no write of the trajectory shows (``facts.unseen_repo_paths``, the task's test
        files and new files aside)."""
        return [p for p in getattr(self.ctx.facts, "unseen_repo_paths", None) or [] if p not in self.new_now and SOURCE_EXT.search(p) and not EV.is_test_file(p, self.tests)]

    def changed(self, path: str) -> bool:
        return any(same_file(path, q) for q in self.changed_now) if self.final is not None else self.obs.changed(path)

    @cached_property
    def edited4(self) -> list[str]:
        """The files changed, as stage 4 reports them: the patch's, else the trajectory's edits."""
        return self.changed_now if self.final is not None else list(self.obs.edited)

    # -- stage 1's baseline (the claims) --------------------------------------------------------------

    @cached_property
    def passing1(self) -> str | None:
        return _field(self.p1, "Baseline", "Passing")

    @cached_property
    def failing1(self) -> str | None:
        return _field(self.p1, "Baseline", "Failing")

    @cached_property
    def both_none(self) -> bool:
        return EV.is_none(self.passing1) and EV.is_none(self.failing1)

    @cached_property
    def baseline_runs(self) -> list:
        """The test runs before the first source edit."""
        return self.obs.tests_in(before=self.obs.first_edit)

    @cached_property
    def recorded_targets(self) -> set[str]:
        """The test targets artifact 01 recorded (empty without 01)."""
        if self.p1 is None:
            return set()
        return set(EV.test_targets(_field(self.p1, "Build & Test Commands", "Test") or "", workdir=self.workdir) or [])

    @cached_property
    def evidence_runs(self) -> list:
        """The baseline the artifact reports: the runs of the recorded test selection before the first edit (every
        target a run names is a recorded one: the selection may be run in parts), else any baseline run; [] without
        01. Other runs before the first edit (a mistyped module, an unrelated suite) are not what it describes."""
        if self.p1 is None:
            return []
        rt = self.recorded_targets
        recorded = [r for r in self.baseline_runs if rt and (t := self.obs.targets(r)) and set(t) <= rt]
        return recorded or self.baseline_runs

    @cached_property
    def evidence_out(self) -> str:
        return "\n".join(o for _, _, o in self.evidence_runs)

    # -- requirements and the plan (the claims) -------------------------------------------------------

    @cached_property
    def r_ids(self) -> list[str]:
        return list(dict.fromkeys(self.p2["r_ids"])) if self.p2 else []

    @cached_property
    def step_nums(self) -> list[int]:
        return sorted({s["n"] for s in self.p3["steps"]}) if self.p3 else []

    @cached_property
    def tags(self) -> list[str]:
        return sorted({t for s in self.p3["steps"] for t in s["tags"]}) if self.p3 else []

    @cached_property
    def plan_targets(self) -> list[str]:
        """The files the plan's steps change (a step that only verifies a file left out)."""
        if self.p3 is None:
            return []
        return list(dict.fromkeys(t for s in self.p3["steps"] if not _VERIFY_ONLY.search(s["fields"].get("Target") or "") for t in claimed_paths(s["fields"].get("Target"))))

    @cached_property
    def mod(self) -> list[str]:
        """The files artifact 04 claims it modified."""
        return [x for x in (norm_path(x) for x in self.p4["claims"]["modified"]) if x] if self.p4 else []

    @cached_property
    def cre(self) -> list[str]:
        """The files artifact 04 claims it created."""
        return [x for x in (norm_path(x) for x in self.p4["claims"]["created"]) if x] if self.p4 else []

    # -- the reproduction script ----------------------------------------------------------------------

    @cached_property
    def repro(self) -> str | None:
        """The reproduction script's path as 04 records it, else 03."""
        return next((p for st in (4, 3) if self.parsed.get(st) for p in claimed_paths(_field(self.parsed[st], "Reproduction Script", "Path"))), None)

    @cached_property
    def repro_paths(self) -> list[str]:
        """Every reproduction script path 03 and 04 record."""
        return [p for st in (3, 4) if self.parsed.get(st) for p in claimed_paths(_field(self.parsed[st], "Reproduction Script", "Path"))]

    @cached_property
    def repro_recorded(self) -> list[str]:
        """Every reproduction script path artifacts 03 and 04 recorded, in any version the run wrote (the shared
        replay's contents of their writes) or collected: the paths the script had while the run went on (D2)."""
        out = list(self.repro_paths)
        writes = getattr(self.ctx.facts, "writes", None) or {}
        for path, st in A.ARTIFACT_PATHS.items():
            if st not in (3, 4):
                continue
            for e in writes.get(path, []):
                if e.content:
                    try:
                        out += claimed_paths(_field(A.parse(st, e.content), "Reproduction Script", "Path"))
                    except Exception:  # noqa: BLE001 -- a version the parser cannot take records nothing
                        continue
        return list(dict.fromkeys(norm_path(p) for p in out if p))

    def is_repro(self, path: str) -> bool:
        return any(same_file(path, q) for q in self.repro_paths)

    def not_repro(self, paths: list[str]) -> list[str]:
        """``paths`` without the reproduction script (it has its own section in 03 and 04, a step or not)."""
        return [x for x in paths if not (self.repro and same_file(x, self.repro))]

    # -- stage 5's runs (the claims) ------------------------------------------------------------------

    @cached_property
    def post(self) -> list:
        """The test runs after the last source edit, before artifact 05."""
        return self.obs.tests_in(after=self.obs.last_edit, before=self.w[5]) or []

    @cached_property
    def described(self) -> list:
        """The runs 05's Regressions / Pre-existing / Outstanding describe: the last runs of the recorded selection (05
        Command, else 01 Test) after the last edit; an exploratory run of other tests after it is not what the report
        compares with the baseline (step24 000346), nor a run on stashed source."""
        candidates = [r for r in self.post if not on_stash(r[1])] or self.post
        command = _field(self.p5, "Existing Tests vs Baseline", "Command")
        selection = set(EV.test_targets(command or "", workdir=self.workdir) or []) or self.recorded_targets
        return [r for r in candidates if selection and (t := self.obs.targets(r)) and set(t) <= selection] or candidates

    @cached_property
    def regressed(self) -> bool | None:
        """The described run fails a test the baseline did not (None when that cannot be told)."""
        return _regressed(self.described[-1][2], self.failing1, self.evidence_runs) if self.described else None

    # -- the atomic rules' shared readings ------------------------------------------------------------

    @cached_property
    def known(self) -> set[str]:
        """Every repository path the run read, edited, created or changed in the patch."""
        obs, final = self.obs, self.final
        return {norm_path(p) for p in [*obs.viewed, *obs.edited, *obs.created, *(final[0] if final else [])]}

    @cached_property
    def edits_unseen(self) -> bool:
        """The patch changed a source file the trajectory never shows being edited (:attr:`unseen_sources`)."""
        return self.final is not None and any(re.search(r"\.(?:py|pyx|js|jsx|mjs|cjs|ts|tsx|mts|cts|go|rs|java|rb|c|h|cpp)$", q) for q in self.unseen_sources)

    @cached_property
    def art_writes(self) -> dict[int, list[int]]:
        """Stage -> every successful write of its artifact."""
        return {A.ARTIFACT_PATHS[p]: steps for p, steps in self.obs.writes.items() if p in A.ARTIFACT_PATHS and steps}

    @cached_property
    def start5(self) -> int | None:
        """Stage 5 begins at its document read, after artifact 04 (an edit between an early 04 and that read is stage
        4's: step24 000406)."""
        return max((x for x in (self.w.get(4), self.read_step.get("05")) if x is not None), default=None)

    @cached_property
    def edits5(self) -> list[int]:
        """The source edits of stage 5 (between its start and artifact 05)."""
        w5 = self.w.get(5)
        return sorted(n for ns in self.obs.source_steps.values() for n in ns if self.start5 < n < w5)
