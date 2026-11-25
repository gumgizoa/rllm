"""The shared reading of test behaviour on Go and JavaScript / TypeScript tasks (2026-11-25 review).

The scorers were written when every task was a Python repository. The cases here are the ways that reading went
wrong on ``go test``, jest and vitest; the commands are forms the tasks' graders and real rollouts use, the outputs
are cut from runs captured in the task images (``go test``, jest 29, vitest 1-3).

    pytest recipe/grpo/qwen3_5/tests/test_multilang_reading.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from recipe.grpo.qwen3_5.workflow_rubric import collect as C  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.context import Collected  # noqa: E402


# --------------------------------------------------------------------------------------------
# collect: a file whose mode alone differs from the commit is not a change
# --------------------------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout


def _sh(script: str) -> str:
    return subprocess.run(["sh", "-c", C._command(script)], check=True, capture_output=True, text=True, timeout=60).stdout


def test_a_file_whose_mode_alone_changed_is_no_change(tmp_path):
    """Task images copied with every file made executable (gqlgen: 1,319 files 644 -> 755 against HEAD): the diff
    after the run and the status before it list only files whose content differs."""
    r = tmp_path / "testbed"
    (r / "pkg").mkdir(parents=True)
    (r / "pkg/a.go").write_text("package pkg\n")
    (r / "pkg/b.go").write_text("package pkg\n")
    _git(r, "init", "-q")
    _git(r, "config", "core.fileMode", "true")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD").strip()
    os.chmod(r / "pkg/a.go", 0o755)
    os.chmod(r / "pkg/b.go", 0o755)
    assert "pkg/a.go" in _git(r, "status", "--porcelain")  # git itself, as the image is configured, sees them

    status = _sh(C._task_info_script(str(r)))
    assert "WFRFAIL" not in status
    (r / "pkg/b.go").write_text("package pkg\n\nfunc B() {}\n")  # the agent's one edit
    c = Collected(workdir=str(r), base_sha=base)
    C.parse_git(_sh(C.git_script(str(r), base, [])), c, [])
    assert c.errors == []
    assert c.diff == {"pkg/b.go": "M"}


# --------------------------------------------------------------------------------------------
# What a command runs: go test, jest, vitest, package scripts
# --------------------------------------------------------------------------------------------
from recipe.grpo.qwen3_5.workflow_rubric import evidence as E  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric import results as R  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace import shell  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Run, Step  # noqa: E402

WD = "/testbed"


def _hits(command: str) -> list:
    return [h for h in (E.classify(seg) for seg in shell.flat(shell.split(command, WD)[0])) if h is not None]


def _hit(command: str):
    (hit,) = _hits(command)
    return hit


def _rel(hit) -> list[str]:
    return [t[len(WD) :].lstrip("/") or "." for t in hit.targets]


def _full_suite(command: str) -> bool:
    return any(E.full_suite(seg, WD) for seg in shell.flat(shell.split(command, WD)[0]))


def _runs(steps, base=None, created=None):
    run = Run("x", [Step(i + 1, [Action("shell", command=c, observation=o)]) for i, (c, o) in enumerate(steps)] + [Step(len(steps) + 1, [Action("other")])])
    return E.runs_from(run, {(i + 1, 0): WD for i in range(len(steps))}, base, created or {}, workdir=WD)


def test_go_test_packages_are_its_targets():
    """``go test`` never had targets: nothing could say which package a run was of."""
    for command, targets, flat in (
        ("go test ./pkg/auth/...", ["pkg/auth"], 0),
        ("go test -count 1 -tags integration ./pkg/auth", ["pkg/auth"], 1),  # a flag's value is no package
        ("go test -v ./pkg/a ./pkg/b 2>&1 | tail -20", ["pkg/a", "pkg/b"], 2),
        ("cd pkg/auth && go test", ["pkg/auth"], 1),  # no package: the one in the current directory
        ("cd pkg/auth && go test ./...", ["pkg/auth"], 0),
        ("go test -C sub ./...", ["sub"], 0),
        ("go test ./pkg/a/a_test.go ./pkg/a/a.go", ["pkg/a/a_test.go", "pkg/a/a.go"], 0),
        ("go test ./... -args -run x", ["."], 0),  # after -args: the test binary's
    ):
        hit = _hit(command)
        assert hit.runner.name == "go-test" and _rel(hit) == targets and len(hit.flat) == flat, command
    hit = _hit("go test github.com/o/r/pkg/auth/...")  # an import path names no path the trace can resolve
    assert hit.targets == [] and hit.narrow == ["pkg github.com/o/r/pkg/auth/..."]
    assert _hit("go test -run 'TestLogin|TestLogout' -skip TestSlow ./pkg/auth").narrow == ["-run TestLogin|TestLogout", "-skip TestSlow"]
    for command in ("go test -list . ./...", "go test -c ./pkg/a", "go test -n ./..."):
        assert _hit(command).no_run, command


def test_go_whole_suite_and_selection():
    """``go test ./...`` at the root was "a selection" (its operand was no known sub-command), ``go test .`` the whole
    suite (the root itself)."""
    for command in ("go test ./...", "go test -count=1 -v ./...", "go test -mod=vendor ./...", "go test -race -timeout 5m ./..."):
        assert _full_suite(command), command
        assert E.command_selection(command, WD)[0] is False, command
    for command in ("go test .", "go test", "go test ./pkg/...", "go test -run TestX ./...", "cd pkg && go test ./...", "go test github.com/o/r/..."):
        assert not _full_suite(command), command
        assert E.command_selection(command, WD)[0] is True, command


def test_jest_and_vitest_started_another_way_are_test_runs():
    """A grader's own form of the command was no test run: ``node .../jest.js``, ``npm run jest --``, ``cross-env``."""
    for command, runner, targets in (
        ("node node_modules/.bin/jest lib/rules/x/__tests__/index.js", "jest", ["lib/rules/x/__tests__/index.js"]),
        ("node --experimental-vm-modules node_modules/jest/bin/jest.js --runInBand lib/a.test.js", "jest", ["lib/a.test.js"]),
        ("cross-env NODE_ENV=test jest lib/a.test.js", "jest", ["lib/a.test.js"]),
        ("NODE_OPTIONS=--experimental-vm-modules npx jest lib/a.test.js", "jest", ["lib/a.test.js"]),
        ("npm run jest -- lib/rules/foo", "npm-test", ["lib/rules/foo"]),
        ("npm test -- test/api.js", "npm-test", ["test/api.js"]),
        ("npm run test:unit -- src/a.test.ts", "npm-test", ["src/a.test.ts"]),
        ("yarn test src/a.test.ts", "npm-test", ["src/a.test.ts"]),
        ("yarn test:unit src/a.test.ts", "npm-test", ["src/a.test.ts"]),
        ("pnpm test -- src/a.test.ts", "npm-test", ["src/a.test.ts"]),
        ("yarn --cwd packages/core test src/a.test.ts", "npm-test", ["packages/core/src/a.test.ts"]),
        ("pnpm exec vitest run src/a.test.ts", "vitest", ["src/a.test.ts"]),
        ("npx vitest --run src/a.test.ts", "vitest", ["src/a.test.ts"]),  # --run is a flag, not an option taking the path
        ("npx jest --coverage --outputFile out/r.json --json", "jest", []),  # an option's value is no test file
        ("corepack yarn test", "npm-test", []),
    ):
        hit = _hit(command)
        assert hit.runner.name == runner and _rel(hit) == targets, command
    for command in ("npm run lint", "pnpm install", "yarn add -D jest", "npm install --save-dev vitest", "node repro.js"):
        assert _hits(command) == [], command


def test_jest_and_vitest_whole_suite_and_selection():
    for command in ("npx jest", "npm test", "yarn test", "pnpm test", "npx vitest run", "pnpm vitest run", "npx jest --coverage"):
        assert _full_suite(command), command
    for command in (
        "npx jest test/unit/foo.test.js",
        "npx jest --testPathPattern=foo",  # was the whole suite
        "npx jest foo",
        "npm test -- -t 'adds two'",
        "npx vitest run -t parses",
        "yarn test:unit",
        "yarn workspace @x/core test",
        "pnpm --filter core test",
        "pnpm -C packages/a test",
        "npx jest --onlyChanged",
    ):
        assert not _full_suite(command), command
        assert E.command_selection(command, WD)[0] is True, command
    assert _hit("npx jest -t 'adds two' test/a.test.js").narrow == ["-t adds two"]
    assert _hit("npx mocha test/topics.js -g delete").narrow == ["-t delete"]
    assert _hit("npx mocha -t 5000 test/x.js").narrow == []  # mocha's -t is its timeout
    assert _hit("npx vitest list").no_run == "list"


def test_narrowing_is_read_by_the_runner_not_as_pytest_options():
    """``go test -mod vendor`` was read as pytest's ``-m vendor`` marker filter."""
    assert R.selection("go test -mod vendor ./...") == ()
    assert R.selection("go test -mod=vendor -modfile=go.alt.mod ./pkg/...") == ()
    assert R.selection("go test -run TestLogin ./pkg/auth") == ("-run TestLogin",)
    assert R.selection("npx jest -t 'adds two' test/a.test.js") == ("-t adds two",)
    assert R.selection("npm test -- --testPathPattern foo") == ("--testPathPattern foo",)
    assert R.selection("pytest -m slow tests") == ("-m slow",) and R.selection("python -m pytest tests/x.py") == ()  # pytest's own stay


# --------------------------------------------------------------------------------------------
# What a run's output says
# --------------------------------------------------------------------------------------------
GO_FAIL = """--- FAIL: TestEmbeddedStructsWithNamelessJSONTag (0.00s)
    openapi3gen_test.go:342:
        	Error Trace:	/testbed/openapi3gen/openapi3gen_test.go:342
        	Error:      	openapi3.Schemas{} does not contain "field1"
        	Test:       	TestEmbeddedStructsWithNamelessJSONTag
FAIL
FAIL	github.com/getkin/kin-openapi/openapi3gen	0.010s
FAIL
"""
GO_V_TAIL = """--- PASS: TestExportComponentSchemasForTimeProp (0.00s)
=== RUN   TestFieldNameGenerator
=== RUN   TestFieldNameGenerator/customizes_untagged_fields
--- PASS: TestFieldNameGenerator (0.00s)
    --- PASS: TestFieldNameGenerator/customizes_untagged_fields (0.00s)
=== RUN   Example
--- PASS: Example (0.00s)
FAIL
FAIL	github.com/getkin/kin-openapi/openapi3gen	0.010s
FAIL
"""
GO_BUILD_FAILED = """# github.com/getkin/kin-openapi/openapi3gen [github.com/getkin/kin-openapi/openapi3gen.test]
openapi3gen/openapi3gen_test.go:345:14: undefined: openapi3gen.WithFieldNameGenerator
FAIL	github.com/getkin/kin-openapi/openapi3gen [build failed]
FAIL
"""
GO_SETUP_FAILED = """# github.com/99designs/gqlgen/codegen/testserver/followschema
codegen/testserver/followschema/ptr_to_any.go:5:2: package nosuch/pkg is not in std
FAIL	github.com/99designs/gqlgen/codegen/testserver/followschema [setup failed]
FAIL
"""
GO_WHOLE_TAIL = """ok  	github.com/getkin/kin-openapi/routers	0.013s
ok  	github.com/getkin/kin-openapi/routers/gorillamux	0.010s
?   	github.com/getkin/kin-openapi/openapi3gen/internal/subpkg	[no test files]
ok  	github.com/getkin/kin-openapi/routers/legacy	0.010s
FAIL
"""


def _one(text: str):
    (s,) = E.summaries(text)
    return s


def test_go_package_that_did_not_build_is_read():
    """``FAIL pkg [build failed]`` had no time on its line and was no result at all. Next to a passing package the
    run read as all passed; alone it was "no test summary in the output". It is one error: with other results a
    failing run, alone a run that loaded no test -- what a pytest run of collection errors only is."""
    for text in (GO_BUILD_FAILED, GO_SETUP_FAILED):
        s = _one(text)
        assert (s.family, s.passed, s.failed, s.errors) == ("go", 0, 0, 1)
    (alone,) = _runs([("go test ./openapi3gen/", GO_BUILD_FAILED)])
    assert not alone.valid and alone.errors == 1 and alone.targets == ["openapi3gen"]
    assert alone.reason == "invocation error (only load / collection errors: [build failed])"
    (mixed,) = _runs([("go test ./...", "ok  \tgithub.com/getkin/kin-openapi/routers\t0.013s\n" + GO_BUILD_FAILED)])
    assert mixed.valid and (mixed.passed, mixed.failed, mixed.errors) == (1, 0, 1), mixed.reason


def test_go_run_that_matched_no_test_ran_none():
    """Run from inside the package, go says ``no tests to run`` on a line of its own and the ``ok`` line has no
    ``[no tests to run]``: ``cd pkg && go test -run TestTypo -v`` read as one package passed (gqlgen-4256)."""
    local = "testing: warning: no tests to run\nPASS\nok  \tgithub.com/99designs/gqlgen/codegen/testserver/singlefile\t0.006s\n"
    (run,) = _runs([("cd codegen/testserver/singlefile && go test -run TestPtrToSliceNilPointer -v 2>&1", local)])
    assert not run.valid and run.reason == "zero tests (no tests to run)", run.reason
    listed = "ok  \tgithub.com/o/r/a\t0.010s [no tests to run]\n"
    (run,) = _runs([("go test -run TestTypo ./a", listed)])
    assert not run.valid and run.reason == "zero tests (no tests to run)"
    ran = "=== RUN   TestA\n--- PASS: TestA (0.00s)\nPASS\nok  \tgithub.com/o/r/a\t0.010s\n"
    (run,) = _runs([("cd a && go test -run TestA -v", ran)])
    assert run.valid and run.passed == 1


def test_go_failure_whose_test_line_was_cut_off_is_a_failure():
    """``go test -v ... | tail``: the ``--- FAIL`` line is above the cut, the passing tests below it; the run read as
    all passed (11 of 16 such captures)."""
    s = _one(GO_V_TAIL)
    assert s.passed == 3 and s.failed == 1
    whole = _one(GO_WHOLE_TAIL)  # ``go test ./... | tail``: only go's last bare FAIL is left of the failing package
    assert whole.passed == 3 and whole.failed == 1
    plain = _one(GO_FAIL)  # a failure the output names is counted once
    assert (plain.passed, plain.failed) == (0, 1)
    assert _one("ok  \tgithub.com/o/r/pkg\t0.006s [no tests to run]\n").zero == "no tests to run"


JEST_BROKEN = """FAIL lib/rules/declaration-block-trailing-semicolon/__tests__/index.js
  ● Test suite failed to run

    Jest encountered an unexpected token

    SyntaxError: /testbed/lib/rules/declaration-block-trailing-semicolon/__tests__/index.js: Unexpected token (251:0)

Test Suites: 1 failed, 1 total
Tests:       0 total
Snapshots:   0 total
Time:        0.696 s, estimated 1 s
"""
JEST_FAIL = """FAIL lib/rules/declaration-block-trailing-semicolon/__tests__/index.js
  declaration-block-trailing-semicolon
    accept
      [ 'always' ]
          ✓ single declaration block with trailing semicolon (21 ms)
          ✕ single declaration without trailing semicolon (4 ms)

  ● declaration-block-trailing-semicolon › accept › [ 'always' ] › single declaration without trailing semicolon

    expect(received).toHaveLength(expected)

  ● declaration-block-trailing-semicolon › reject › inconsistent case (with and without)

    expect(received).toHaveLength(expected)

Test Suites: 1 failed, 1 total
Tests:       2 failed, 25 passed, 27 total
Snapshots:   0 total
Time:        1.395 s
"""
JEST_PROJECTS = """FAIL ReactDOM 18 src/react/hooks/__tests__/useMutation.test.tsx (8.935 s)
  ● useMutation Hook › Callbacks › prefers the onCompleted handler

    expect(jest.fn()).toHaveBeenCalledTimes(expected)

FAIL ReactDOM 17 src/react/hooks/__tests__/useMutation.test.tsx (9.157 s)
  ● useMutation Hook › Callbacks › prefers the onCompleted handler

    expect(jest.fn()).toHaveBeenCalledTimes(expected)

Test Suites: 2 failed, 2 total
Tests:       2 failed, 70 passed, 72 total
"""
VITEST_FAIL = """ RUN  v3.1.1 /testbed

 ❯ test/cookie.test.ts (6 tests | 1 failed) 33ms
   ✓ parseCookies > can parse cookies 14ms
   × setCookie > can merge unique cookies 9ms
     → expected [ 'session=abc; Path=/a', …(5) ] to deeply equal [ 'session=abc; Path=/a', …(2) ]

⎯⎯⎯⎯⎯⎯⎯ Failed Tests 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  test/cookie.test.ts > setCookie > can merge unique cookies
AssertionError: expected [ 'session=abc; Path=/a', …(5) ] to deeply equal [ 'session=abc; Path=/a', …(2) ]

 Test Files  1 failed (1)
      Tests  1 failed | 5 passed (6)
   Start at  06:41:37
"""
VITEST_BROKEN = """ RUN  v3.1.1 /testbed

⎯⎯⎯⎯⎯⎯ Failed Suites 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  test/cookie.test.ts [ test/cookie.test.ts ]
Error: Transform failed with 1 error:
/testbed/test/cookie.test.ts:134:0: ERROR: Unexpected "}"

 Test Files  1 failed (1)
   Start at  06:41:37
"""


def test_a_test_file_that_could_not_be_loaded_is_read():
    """jest ``Tests: 0 total`` / vitest with no ``Tests`` line at all was no result; next to a file that ran, the run
    read as all passed. Each such file is one error (alone: a run that loaded no test)."""
    s = _one(JEST_BROKEN)
    assert (s.family, s.passed, s.failed, s.errors) == ("jest", 0, 0, 1)
    v = _one(VITEST_BROKEN)
    assert (v.family, v.passed, v.failed, v.errors) == ("jest", 0, 0, 1)
    for command, text, why in (("npx jest lib/rules/declaration-block-trailing-semicolon/__tests__/index.js", JEST_BROKEN, "Test suite failed to run"), ("npx vitest run test/cookie.test.ts", VITEST_BROKEN, "Failed Suites 1")):
        (alone,) = _runs([(command, text)])
        assert not alone.valid and alone.errors == 1 and alone.reason == f"invocation error (only load / collection errors: {why})"
    both_text = JEST_BROKEN.replace("Test Suites: 1 failed, 1 total\nTests:       0 total", "Test Suites: 1 failed, 1 passed, 2 total\nTests:       4 passed, 4 total")
    (both,) = _runs([("npx jest lib/rules", both_text)])
    assert both.valid and (both.passed, both.errors) == (4, 1), both.reason
    ok = _one(JEST_FAIL)  # failed tests are not counted again as failed files
    assert (ok.passed, ok.failed, ok.errors) == (25, 2, 0)
    assert (_one(VITEST_FAIL).passed, _one(VITEST_FAIL).failed, _one(VITEST_FAIL).errors) == (5, 1, 0)


VITEST_PROGRESS = """
 Test Files 0 passed (24)
      Tests 0 passed (0)
   Start at 07:17:38
   Duration 5.46s

 ❯ test/validate.test.ts 3/9

 Test Files 6 passed (24)
      Tests 147 passed | 1 skipped (316)
   Start at 07:17:38
   Duration 8.86s
 ✓ test/cookie.test.ts (7 tests) 307ms

 Test Files 1 failed | 22 passed (24)
      Tests 2 failed | 303 passed | 1 skipped (316)
   Start at 07:17:38
   Duration 11.66s
 ✓  TS  test/types.test-d.ts (11 tests)

 Test Files  1 failed | 23 passed (24)
      Tests  2 failed | 313 passed | 1 skipped (316)
Type Errors  no errors
   Start at  07:17:38
   Duration  12.28s (transform 4.71s, setup 3.68s, collect 39.27s, tests 9.18s, environment 6ms, prepare 19.91s, typecheck 5.49s)
"""

JEST_PROGRESS = """
Test Suites: 0 of 2 total
Tests:       0 total
Snapshots:   0 total
Time:        0 s, estimated 3 s

Test Suites: 1 passed, 1 of 2 total
Tests:       4 passed, 4 total
Snapshots:   0 total
Time:        2 s, estimated 3 s
PASS packages/autocomplete-core/src/__tests__/getSources.test.ts

Test Suites: 2 passed, 2 total
Tests:       9 passed, 9 total
Snapshots:   0 total
Time:        3.412 s
Ran all test suites matching /getSources/i.
"""


def test_the_frames_of_live_progress_are_not_results():
    """On a terminal vitest and jest redraw their counts while the run goes on and the captured output keeps every
    frame (160 of the 306 vitest outputs of the rollouts): the frames were added up -- ``2 failed | 313 passed`` read as
    20 failed, 3,344 passed, and its two failing names fitted no count. Only the result is read."""
    v = _one(VITEST_PROGRESS)
    assert (v.passed, v.failed, v.skipped, v.errors, v.collected) == (313, 2, 1, 0, 316)
    j = _one(JEST_PROGRESS)
    assert (j.passed, j.failed, j.errors, j.collected) == (9, 0, 0, 9)
    # a run that only got as far as its frames has no result; one that stopped early (--bail) has: its last line
    assert E.summaries(VITEST_PROGRESS[: VITEST_PROGRESS.index(" Test Files  1 failed")]) == []
    assert E.summaries(JEST_PROGRESS[: JEST_PROGRESS.index("PASS packages")]) == []
    bail = "Test Suites: 1 failed, 1 of 5 total\nTests:       1 failed, 3 passed, 4 total\nSnapshots:   0 total\nTime:        2.1 s\nRan all test suites.\n"
    b = _one(JEST_PROGRESS[: JEST_PROGRESS.index("PASS packages")] + bail)
    assert (b.passed, b.failed) == (3, 1)
    (run,) = _runs([("pnpm vitest --run --coverage", VITEST_PROGRESS)])
    assert run.valid and (run.passed, run.failed) == (313, 2)


def test_jest_and_vitest_failures_have_names():
    """No failing test of a jest / vitest run had a name, so every failure after the change counted as new and no
    failure before it could be the same one."""
    assert E.failing_ids(JEST_FAIL) == [
        "lib/rules/declaration-block-trailing-semicolon/__tests__/index.js::declaration-block-trailing-semicolon › accept › [ 'always' ] › single declaration without trailing semicolon",
        "lib/rules/declaration-block-trailing-semicolon/__tests__/index.js::declaration-block-trailing-semicolon › reject › inconsistent case (with and without)",
    ]
    assert E.failing_ids(VITEST_FAIL) == ["test/cookie.test.ts::setCookie > can merge unique cookies"]
    assert E.failing_ids(JEST_BROKEN) == ["lib/rules/declaration-block-trailing-semicolon/__tests__/index.js"]
    assert E.failing_ids(VITEST_BROKEN) == ["test/cookie.test.ts"]
    assert len(E.failing_ids(JEST_PROJECTS)) == 2  # the same test of two projects is two results
    for text, n in ((JEST_FAIL, 2), (VITEST_FAIL, 1), (JEST_PROJECTS, 2)):
        assert len(R.run_failed_ids(n, 0, text)) == n
    assert R.run_failed_ids(0, 1, JEST_BROKEN) == ("lib/rules/declaration-block-trailing-semicolon/__tests__/index.js",)


def test_a_go_failure_is_named_with_its_package():
    assert E.failing_ids(GO_FAIL) == ["TestEmbeddedStructsWithNamelessJSONTag"]
    assert R.run_failed_ids(1, 0, GO_FAIL) == ("github.com/getkin/kin-openapi/openapi3gen::TestEmbeddedStructsWithNamelessJSONTag",)
    assert R.run_failed_ids(1, 0, GO_V_TAIL) == ()  # a failure the output does not name: the run is judged by its package
    assert E.failing_ids(GO_BUILD_FAILED) == ["github.com/getkin/kin-openapi/openapi3gen"]


def test_a_test_state_is_read_from_go_jest_and_vitest_lines():
    """Only pytest's and unittest's words said a test passed; a jest test never failed by its own line."""
    assert E.test_state(GO_V_TAIL, "TestFieldNameGenerator") is True
    assert E.test_state(GO_FAIL, "TestEmbeddedStructsWithNamelessJSONTag") is False
    assert E.test_state(GO_V_TAIL, "TestNotThere") is None
    assert E.test_state(JEST_FAIL, "single declaration block with trailing semicolon") is True
    assert E.test_state(JEST_FAIL, "single declaration without trailing semicolon") is False
    assert E.test_state(VITEST_FAIL, "can parse cookies") is True
    assert E.test_state(VITEST_FAIL, "can merge unique cookies") is False


# --------------------------------------------------------------------------------------------
# A failed test that passes again
# --------------------------------------------------------------------------------------------
def _result(step: int, command: str, output: str) -> R.TestResult:
    (run,) = _runs([(command, output)])
    files = R.run_files(run, WD)
    whole = _full_suite(command)
    return R.TestResult(step, not (run.failed + run.errors), True, files if files and not whole else (R.WHOLE,), R.selection(run.segment), R.run_failed_ids(run.failed, run.errors, run.observation))


GO_OK = "ok  \tgithub.com/getkin/kin-openapi/openapi3gen\t0.010s\n"


def test_a_go_failure_is_cleared_by_a_run_of_its_package_and_not_by_a_narrower_one():
    failing = _result(1, "go test ./openapi3gen/", GO_FAIL)
    assert failing.keys == ("openapi3gen",) and failing.failed_ids
    for command, clears in (
        ("go test ./openapi3gen/", True),
        ("go test ./...", True),
        ("go test ./openapi3gen/ -run TestEmbeddedStructs", True),
        ("go test ./openapi3gen/ -run TestCyclicReferences", False),  # did not run the failed test
        ("go test ./openapi3gen/ -skip TestEmbedded", False),
        ("go test ./routers/...", False),  # another package
        ("go test -mod vendor ./openapi3gen/", True),  # -mod is no marker filter
    ):
        passing = _result(2, command, GO_OK)
        assert (R.standing_units([failing, passing]) == []) is clears, command


def test_a_jest_failure_is_cleared_by_a_run_that_ran_the_test():
    failing = _result(1, "npx jest lib/rules/declaration-block-trailing-semicolon/__tests__/index.js", JEST_FAIL)
    assert len(failing.failed_ids) == 2
    ok = "Test Suites: 1 passed, 1 total\nTests:       27 passed, 27 total\n"
    for command, clears in (
        ("npx jest lib/rules/declaration-block-trailing-semicolon/__tests__/index.js", True),
        ("npm test -- lib/rules/declaration-block-trailing-semicolon", True),
        ("npx jest", True),
        ("npx jest lib/rules/declaration-block-trailing-semicolon -t 'no such test'", False),
        ("npx jest lib/rules/color-named", False),
    ):
        passing = _result(2, command, ok)
        assert (R.standing_units([failing, passing]) == []) is clears, command


def test_a_jest_operand_that_is_a_pattern_is_not_held_to_the_base_tree():
    """Online, ``npx jest lib/rules/foo`` made the run invalid when no file of that very name was in the base tree."""
    ok = "Test Suites: 1 passed, 1 total\nTests:       27 passed, 27 total\n"
    (run,) = _runs([("npx jest lib/rules/foo.test", ok)], base={"lib/rules/foo.test": False})
    assert run.valid, run.reason
    (made,) = _runs([("npx jest lib/rules/mine.test.js", ok)], base={"lib/rules/mine.test.js": False}, created={"/testbed/lib/rules/mine.test.js": 1})
    assert not made.valid  # a test file the run made is still the run's own


# --------------------------------------------------------------------------------------------
# The run's own scripts
# --------------------------------------------------------------------------------------------
from recipe.grpo.qwen3_5.workflow_rubric import facts as F  # noqa: E402


def _executed(command: str) -> list[str]:
    return [p[len(WD) + 1 :] if p.startswith(WD + "/") else p for seg in shell.flat(shell.split(command, WD)[0]) for p in F._executed(seg)]


def test_a_script_run_by_go_run_or_a_typescript_runner_is_an_execution():
    """``go run repro.go`` and ``npx tsx repro.ts`` were no run of the script (356 and 16 of them in 288 rollouts)."""
    for command, ran in (
        ("go run repro.go", ["repro.go"]),
        ("go run /tmp/repro/main.go arg", ["/tmp/repro/main.go"]),
        ("go run -tags x ./cmd/repro a b", ["cmd/repro"]),  # a package: its directory
        ("go run a.go b.go -flag", ["a.go", "b.go"]),
        ("npx tsx repro.ts", ["repro.ts"]),
        ("npx ts-node --project tsconfig.json scripts/check.ts", ["scripts/check.ts"]),  # an option's value is not the script
        ("yarn tsx repro.ts", ["repro.ts"]),
        ("pnpm exec tsx repro.ts", ["repro.ts"]),
        ("bun run repro.ts", ["repro.ts"]),
        ("deno run -A repro.ts", ["repro.ts"]),
        ("node --require ./setup.js repro.js", ["repro.js"]),
        ("node repro.js", ["repro.js"]),
        ("python repro.py", ["repro.py"]),
    ):
        assert _executed(command) == ran, command
    for command in ("go build ./...", "go test ./...", "node -e 'console.log(1)'", "yarn test", "npm run build", "yarn install"):
        assert _executed(command) == [], command
    assert F.is_scratch_name("repro.go") and F.is_scratch_name("check_fix.tsx") and not F.is_scratch_name("server.go")


def test_a_script_that_printed_its_own_failure_behind_a_cross_failed():
    """``go run verify_fix.go`` printing ``✗ FIX FAILED: ...`` / ``✗ FAIL: ...`` and exiting 0 read as a pass."""
    segs = shell.flat(shell.split("go run verify_fix.go", "/testbed")[0])
    assert R.outcome(segs, 0, "Schema refs: 2\n✗ FAIL: NestedStruct is present (should be inlined)\n", path="/testbed/verify_fix.go") == "fail"
    assert R.outcome(segs, 0, "✓ PASS: NestedStruct is inlined\n", path="/testbed/verify_fix.go") == "pass"


def test_a_runner_the_package_manager_could_not_get_ran_nothing():
    """``npx tsx repro.ts`` with no network ends in npm's own error: the script did not fail, it never ran."""
    path = "/testbed/packages/arktype-validator/reproduce-issue.ts"
    segs = shell.flat(shell.split("npx tsx reproduce-issue.ts", "/testbed/packages/arktype-validator")[0])
    offline = "npm ERR! code EAI_AGAIN\nnpm ERR! syscall getaddrinfo\nnpm ERR! errno EAI_AGAIN\nnpm ERR! request to https://registry.npmjs.org/tsx failed\n"
    assert not R.started(segs, 0, offline, path)
    assert R.started(segs, 0, "leak: false\n", path)
    assert R.outcome(segs, 0, "Error: boom\n    at main (/testbed/packages/arktype-validator/reproduce-issue.ts:3:9)\n", path=path) == "fail"


def test_go_runs_the_files_of_the_package_directory_it_names():
    """go compiles a package, never a file by name: the run's own files in the directory are what ran."""
    mine = {"/testbed/cmd/repro/main.go", "/testbed/pkg/auth/repro_test.go", "/testbed/pkg/auth/sub/x_test.go", "/testbed/repro.go"}
    for command, ran in (
        ("go run ./cmd/repro", ["cmd/repro/main.go"]),
        ("go run repro.go", ["repro.go"]),
        ("go test ./pkg/auth", ["pkg/auth/repro_test.go"]),
        ("cd pkg/auth && go test -run TestRepro", ["pkg/auth/repro_test.go"]),
        ("go test ./pkg/auth/...", ["pkg/auth/repro_test.go", "pkg/auth/sub/x_test.go"]),
        ("go test ./pkg/other", []),
        ("go build ./cmd/repro", []),
    ):
        seg = shell.flat(shell.split(command, WD)[0])[-1]
        assert sorted(p[len(WD) + 1 :] for p in R.runs_of(seg, mine)) == ran, command


def test_a_go_or_node_script_that_failed_behind_a_pipe_failed():
    """With the exit code hidden by a pipe the output's words decide: a Go panic or compile error and an uncaught
    Node error were no failure text."""
    for command, output in (
        ("go run repro.go 2>&1 | tail -20", "panic: runtime error: index out of range [3] with length 3\n\ngoroutine 1 [running]:\nmain.main()\n\t/testbed/repro.go:9 +0x1d\nexit status 2\n"),
        ("go run repro.go 2>&1 | tail -20", "# command-line-arguments\n./repro.go:12:9: undefined: slug.MakeLang\n"),
        ("node repro.js 2>&1 | head -30", "/testbed/repro.js:4\n  throw new TypeError('x');\n  ^\n\nTypeError: x\n    at Object.<anonymous> (/testbed/repro.js:4:9)\n\nNode.js v20.11.0\n"),
    ):
        segs = shell.flat(shell.split(command, WD)[0])
        assert R.outcome(segs, 0, output, command, WD + "/" + command.split()[2]) == "fail", command
    segs = shell.flat(shell.split("go run repro.go 2>&1 | tail -20", WD)[0])
    assert R.outcome(segs, 0, "result: ok\nall checks passed\n", "go run repro.go 2>&1 | tail -20", WD + "/repro.go") == "pass"


# --------------------------------------------------------------------------------------------
# The existing tests of the changed code (R7)
# --------------------------------------------------------------------------------------------
def _repo(tmp_path: Path, files: dict[str, str]) -> tuple[Path, str]:
    r = tmp_path / "testbed"
    for name, text in files.items():
        (r / name).parent.mkdir(parents=True, exist_ok=True)
        (r / name).write_text(text)
    _git(r, "init", "-q")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    return r, _git(r, "rev-parse", "HEAD").strip()


def _related(r: Path, base: str, changed: list[str]) -> dict:
    c = Collected(workdir=str(r), base_sha=base)
    C.parse_related(_sh(C.related_script(str(r), base, changed)), c, changed)
    assert c.errors == []
    return c.related_tests


def test_the_changed_sources_are_not_python_only():
    """Only ``.py`` paths of the diff were looked up: on a Go or TypeScript task the list of related tests was always
    empty, which waived the item in one workflow and failed it in another."""
    c = Collected(workdir="/testbed", base_sha="x")
    c.diff = {"pkg/auth/token.go": "M", "pkg/auth/token_test.go": "M", "src/cookie.ts": "M", "src/types.d.ts": "M", "test/cookie.test.ts": "M", "lib/rules/x/index.js": "M",
              "lib/rules/x/__tests__/index.js": "M", "pkg/mod.py": "M", "README.md": "M", "go.sum": "M", "node_modules/a/index.js": "?"}  # fmt: skip
    assert C.changed_sources(c) == ["lib/rules/x/index.js", "pkg/auth/token.go", "pkg/mod.py", "src/cookie.ts"]


def test_related_tests_of_a_go_source_are_its_package_tests(tmp_path):
    r, base = _repo(
        tmp_path,
        {
            "pkg/auth/token.go": "package auth\n\nfunc Sign() string { return \"a\" }\n",
            "pkg/auth/token_test.go": "package auth\n",
            "pkg/auth/login_test.go": "package auth\n",
            "pkg/auth/internal/deep_test.go": "package internal\n",  # another package
            "pkg/other/other_test.go": "package other\n",
            "main.go": "package main\n",
            "main_test.go": "package main\n",
        },
    )
    assert _related(r, base, ["pkg/auth/token.go", "main.go"]) == {"pkg/auth/token.go": ["pkg/auth/login_test.go", "pkg/auth/token_test.go"], "main.go": ["main_test.go"]}


def test_related_tests_of_a_javascript_source_by_name_and_by_import(tmp_path):
    r, base = _repo(
        tmp_path,
        {
            "src/cookie.ts": "export function parse() {}\n",
            "test/cookie.test.ts": "import { parse } from '../src/cookie';\n",  # by name and by import
            "test/session.test.ts": 'import { parse } from "../src/cookie.ts";\n',  # by import only
            "test/other.test.ts": "import { x } from '../src/other';\n",
            "src/__tests__/cookie.ts": "test('x', () => {});\n",  # a file of that name in a test folder
            "lib/rules/color-named/index.js": "module.exports = 1;\n",
            "lib/rules/color-named/__tests__/index.js": "const rule = require('..');\n",  # the folder of a directory's index
            "lib/rules/other/__tests__/index.js": "const rule = require('..');\n",
            "lib/__tests__/standalone.test.js": "const named = require('../rules/color-named');\n",  # imports the directory
        },
    )
    got = _related(r, base, ["src/cookie.ts", "lib/rules/color-named/index.js"])
    assert got == {
        "src/cookie.ts": ["src/__tests__/cookie.ts", "test/cookie.test.ts", "test/session.test.ts"],
        "lib/rules/color-named/index.js": ["lib/__tests__/standalone.test.js", "lib/rules/color-named/__tests__/index.js"],
    }


def test_a_run_of_the_package_or_the_file_runs_the_related_test():
    from recipe.grpo.qwen3_5.workflow_rubric import testread as T

    ok_go = "ok  \tgithub.com/o/r/pkg/auth\t0.010s\n"
    ok_js = "Test Suites: 1 passed, 1 total\nTests:       27 passed, 27 total\n"
    for command, output, test, ran in (
        ("go test ./pkg/auth", ok_go, "pkg/auth/token_test.go", True),
        ("go test ./pkg/...", ok_go, "pkg/auth/token_test.go", True),
        ("cd pkg/auth && go test", ok_go, "pkg/auth/token_test.go", True),
        ("go test ./pkg/other", ok_go, "pkg/auth/token_test.go", False),
        ("npx jest lib/rules/color-named", ok_js, "lib/rules/color-named/__tests__/index.js", True),
        ("npm test -- test/cookie.test.ts", ok_js, "test/cookie.test.ts", True),
        ("yarn test cookie", ok_js, "test/cookie.test.ts", True),  # a pattern on test paths
        ("npx jest test/session.test.ts", ok_js, "test/cookie.test.ts", False),
    ):
        (run,) = _runs([(command, output)])
        assert run.valid, (command, run.reason)
        assert (T.mentions_test_file(run, test, WD) or T.targets_dir_of(run, test, WD)) is ran, command


# --------------------------------------------------------------------------------------------
# Builds, installs, byproducts
# --------------------------------------------------------------------------------------------
def test_a_go_or_typescript_build_that_failed_failed():
    """A build's evidence is its error text; go's and tsc's were not such text, so a failing build read as passed."""
    for command, output in (
        ("go build ./...", "# github.com/o/r/pkg/auth\npkg/auth/token.go:12:9: undefined: Sign\n"),
        ("go vet ./...", "# github.com/o/r/pkg/auth\nvet: pkg/auth/token.go:12:9: undefined: Sign\n"),
        ("npx tsc --noEmit", "src/cookie.ts(3,5): error TS2322: Type 'string' is not assignable to type 'number'.\n"),
    ):
        (run,) = _runs([(command, output)])
        assert run.kind == "build" and (run.passed, run.errors) == (0, 1), command
    ok = _runs([("go build ./... && echo built", "built\n")])[0]
    assert (ok.passed, ok.errors) == (1, 0)


def test_a_build_that_go_or_the_package_manager_refused_failed():
    """go prints no ``file.go:line:col`` line when it cannot load the packages, and a package script that failed ends
    in the package manager's own line: 19 builds of the rollouts that exited non-zero read as passed, among them
    builds the shell tool had stopped waiting for (they are no result at all)."""
    for command, output in (
        ("go build ./...", "package github.com/google/cel-go/cel\n\timports github.com/google/cel-go/interpreter\n\timports github.com/google/cel-go/cel: import cycle not allowed\n"),
        ("go build -o /tmp/gqlgen ./bin/gqlgen", "stat /testbed/bin/gqlgen: directory not found\n"),
        ("go build ./confmap/provider/envprovider/...", "pattern ./confmap/provider/envprovider/...: main module (go.opentelemetry.io/collector) does not contain package go.opentelemetry.io/collector/confmap/provider/envprovider\n"),
        ("go vet ./...", "found packages huma (api.go) and main (reproduce.go) in /testbed\n"),
        ("yarn build packages/arktype-validator", "[@hono/arktype-validator]: DTS Build error\n[@hono/arktype-validator]: Process exited (exit code 1), completed in 4s\n"),
        ("pnpm build", "src/index.ts\n ELIFECYCLE  Command failed with exit code 1.\n"),
        ("npm run build", "> docs@1.0.0 build\n> eleventy\n\nsh: 1: eleventy: not found\n"),
    ):
        (run,) = _runs([(command, output)])
        assert run.kind == "build" and (run.passed, run.errors) == (0, 1), command
    for command, output in (("go build ./...", "go: downloading github.com/x/y v1.2.3\n"), ("npm run build", "> peggy@3.0.0 build\n> rollup -c\n\ncreated build/rollup in 2.1s\n")):
        (run,) = _runs([(command, output)])
        assert run.valid and (run.passed, run.errors) == (1, 0), (command, run.reason)
    hung = "\n[The command has no new output after 30 seconds. You may wait longer to see additional output by sending empty command '']\n^C\n\n[The command completed with exit code 130. CTRL+C was sent.]"
    (run,) = _runs([("go build ./pkg/util/nodelock/...", hung)])
    assert not run.valid and run.reason == "the build had not finished when its output stopped"


def test_go_and_javascript_installs_and_byproducts():
    from recipe.grpo.qwen3_5.workflow_rubric.checks import actions as A

    for command in ("go mod tidy", "go mod download", "go get github.com/x/y", "bun add zod", "pnpm dlx create-x", "npx --yes tsx x.ts", "npm ci", "yarn add -D jest"):
        assert A._INSTALL.search(command), command
    for command in ("go test ./...", "go build ./...", "npx jest", "npx tsx x.ts", "yarn test", "go mod graph"):
        assert not A._INSTALL.search(command), command
    for path in ("coverage.out", "coverage/lcov.info", "tsconfig.tsbuildinfo", "c.out"):
        assert F.is_generated(path), path
    for path in ("pkg/auth/token.go", "src/cookie.test.ts", "test/coverage.ts", "docs/out.md", "test-data/unit/stubgen.test"):
        assert not F.is_generated(path), path


def test_the_package_at_the_repository_root_was_there_before_the_run():
    """``cd /testbed && go test -run TestX``: the target is the root; a replay that saw something moved onto it does
    not make the repository's own directory the agent's."""
    (run,) = _runs([("go test -run TestPathParam -v", "=== RUN   TestPathParam\n--- FAIL: TestPathParam (0.00s)\nFAIL\nFAIL\tgithub.com/o/r\t0.010s\n")], created={"/testbed": 1})
    assert run.valid, run.reason


JEST_REDRAWN = """
Test Suites: 0 of 2 total
Tests:       0 total
Snapshots:   0 total
Time:        5 s FAIL   ReactDOM 18  src/react/hooks/__tests__/repro-on-error.test.tsx

Test Suites: 1 failed, 1 of 2 total
Tests:       9 failed, 9 total
Snapshots:   0 total
Time:        6 s

Test Suites: 2 failed, 2 total
Tests:       6 failed, 6 total
Snapshots:   0 total
Time:        6 sTest Suites: 2 failed, 2 total
Tests:       6 failed, 6 total
Snapshots:   0 total
Time:        7.386 s
Ran all test suites matching /repro-on-error.test/i in 2 projects.
"""


def test_jest_result_is_the_block_that_ends_the_run():
    """jest's last frames already hold the final counts (and one frame counted 9 failures of a run that had 6): the
    result is the block ending in ``Ran all test suites``, also when the terminal glued its first line to the frame
    before it (apollo-client-10425: 6 failed read as 18)."""
    s = _one(JEST_REDRAWN)
    assert (s.passed, s.failed, s.collected) == (0, 6, 6)


def test_a_path_pattern_that_names_the_runs_own_test_file_is_that_file():
    """``npm run test -- --testPathPattern="repro-on-error.test"`` runs the test file the agent wrote, as ``jest
    src/__tests__/repro-on-error.test.tsx`` does: not a run of the repository's tests, and a run of that file (R4). A
    pattern holding a part of a name (``useMutation``) is a selection of the repository's tests."""
    own = "/testbed/src/react/hooks/__tests__/repro-on-error.test.tsx"
    out = "Test Suites: 1 passed, 1 total\nTests:       6 passed, 6 total\nTime:        3.1 s\nRan all test suites.\n"
    for command in ('npm run test -- --testPathPattern="repro-on-error.test" --no-coverage', "npx jest repro-on-error", "npx jest __tests__/repro-on-error"):
        (r,) = _runs([(command, out)], created={own: 1})
        assert not r.valid and r.reason == "test target created by the agent (src/react/hooks/__tests__/repro-on-error.test.tsx)", (command, r.reason)
        (seg,) = shell.flat(shell.split(command, "/testbed")[0])
        assert R.runs_of(seg, {own}) == {own}, command
    backup = "/testbed/lib/rules/color-named/__tests__/index.js.bak"  # a copy beside the repository's test file is not it
    (r,) = _runs([("npx jest lib/rules/color-named/__tests__/index.js", out)], created={backup: 1})
    assert r.valid, r.reason
    assert not E.pattern_names("lib/rules/color-named/__tests__/index.js", backup) and not E.pattern_names("__tests__/other.test.js", own)
    for command in ('npm run test -- --testPathPattern="useMutation.test"', "npx jest on-error", "npx jest src/react/hooks/__tests__/useMutation.test.tsx", "npx jest other/repro-on-error"):
        (r,) = _runs([(command, out)], created={own: 1})
        assert r.valid, (command, r.reason)
        (seg,) = shell.flat(shell.split(command, "/testbed")[0])
        assert R.runs_of(seg, {own}) == set(), command


def test_a_jest_or_vitest_output_cut_above_its_summary_is_read_by_its_own_lines():
    """``npm test 2>&1 | head -100`` / ``| grep -A5 "FAIL test/"`` leave jest's file lines and failure heads and no
    ``Tests:`` line: the run was "no test summary in the output" although it shows its failures (a pytest output cut
    the same way is read by its per-test lines). The frames of a run that never got to its result are no such lines."""
    cut = JEST_FAIL[: JEST_FAIL.index("Test Suites:")]
    s = _one(cut)
    assert (s.family, s.failed, s.errors) == ("jest", 2, 0)
    (r,) = _runs([("npm test 2>&1 | head -100", cut)])
    assert r.valid and r.failed == 2, r.reason
    grep = "FAIL test/types/peg.test-d.ts\n  ● peg.d.ts › executes a grammar\n--\nFAIL test/behavior/generated-parser-behavior.spec.js\n  ● generated parser behavior › syntax errors › formats\n"
    assert (_one(grep).passed, _one(grep).failed) == (0, 2)
    files_only = "PASS test/unit/parser.spec.js\nFAIL test/api/plugin-api.spec.js\nPASS test/cli/run.spec.ts\n"
    assert (_one(files_only).passed, _one(files_only).failed) == (2, 1)
    vitest = " ✓ test/cookie.test.ts (7 tests) 307ms\n ❯ src/engine/MacroChoiceEngine.test.ts (10 tests | 1 failed) 10ms\n"
    assert (_one(vitest).passed, _one(vitest).failed) == (16, 1)
    assert E.summaries(" ✓ test/cookie.test.ts (7 tests) 307ms\n" + VITEST_PROGRESS[: VITEST_PROGRESS.index(" Test Files  1 failed")]) == []
    assert E.summaries("npm ERR! code ELIFECYCLE\n") == []


def test_a_go_test_run_of_the_runs_own_test_functions_is_its_own_test():
    """go names no test file: the agent's own test in a repository package is run by ``-run`` and its functions'
    names. Such a run was a valid run of the repository's tests (cel-go-1084: the only runs after the last change
    were of the agent's ``TestPartialEvalFoldExpr``). A pattern that also names a repository test is a selection."""
    from recipe.grpo.qwen3_5.workflow_rubric.context import WriteEvent

    own = "/testbed/interpreter/fold_partial_eval_test.go"
    body = 'package interpreter\n\nimport "testing"\n\nfunc TestPartialEvalFoldExpr(t *testing.T) {\n}\n\nfunc helper() {}\n'
    out = "=== RUN   TestPartialEvalFoldExpr\n--- FAIL: TestPartialEvalFoldExpr (0.00s)\nFAIL\nFAIL\tgithub.com/google/cel-go/interpreter\t0.012s\nFAIL\n"

    def run_of(command: str):
        run = Run("x", [Step(1, [Action("other")]), Step(2, [Action("shell", command=command, observation=out)]), Step(3, [Action("other")])])
        writes = {own: [WriteEvent(path=own, step=1, op="create", content=body)]}
        (r,) = E.runs_from(run, {(2, 0): WD}, None, {own: 1}, workdir=WD, writes=writes)
        return r

    for command in ("go test -v -run TestPartialEvalFoldExpr ./interpreter/...", "go test -run '^TestPartialEvalFoldExpr$' ./...", "cd interpreter && go test -run TestPartialEvalFoldExpr"):
        r = run_of(command)
        assert not r.valid and r.reason == "test target created by the agent (interpreter/fold_partial_eval_test.go)", (command, r.reason)
    for command in (
        "go test -v ./interpreter/...",  # the package, the repository's tests with it
        'go test -run "TestPartialEvalFoldExpr|TestInterpreter_Plan" ./interpreter/...',  # and a repository test
        "go test -run TestPartialEval ./interpreter/...",  # a part of a name
        "go test -run TestPartialEvalFoldExpr ./checker/...",  # another package
    ):
        r = run_of(command)
        assert r.valid, (command, r.reason)


def test_a_javascript_run_started_in_a_package_directory_runs_that_packages_tests():
    """``cd packages/arktype-validator && yarn test --run`` (a workspace package's own suite) named no path, so it ran
    no test related to the change in the scorer's reading (hono middleware-1137: R7 a miss with three such runs)."""
    from types import SimpleNamespace

    from recipe.grpo.qwen3_5.workflow_rubric import testread as T

    ctx = SimpleNamespace(collected=SimpleNamespace(workdir=WD), facts=SimpleNamespace(_cwd_track={}))
    ok = " Test Files  1 passed (1)\n      Tests  5 passed (5)\n   Duration  1.2s (transform 30ms, setup 0ms)\n"
    for command, where in (
        ("cd /testbed/packages/arktype-validator && yarn test --run", "packages/arktype-validator"),
        ("cd packages/arktype-validator && npx vitest run -t 'Security'", "packages/arktype-validator"),
        ("yarn test --run", None),  # at the root: the whole suite
        ("cd packages/arktype-validator && yarn test --run src/other.test.ts", None),  # a path: read as a target
        ("cd packages/arktype-validator && yarn test other", None),  # a path pattern
        ("cd packages/arktype-validator && go test", None),
    ):
        (run,) = _runs([(command, ok if "go test" not in command else "ok  \tx/y\t0.1s\n")])
        assert T._package_dir(ctx, run) == where, command
    (run,) = _runs([("cd packages/arktype-validator && yarn test --run", ok)])
    assert T.runs_related(ctx, run, ["packages/arktype-validator/src/index.test.ts"])
    assert not T.runs_related(ctx, run, ["packages/zod-validator/src/index.test.ts"])


# --------------------------------------------------------------------------------------------
# what the items other than the test-run ones read: files, installs, recorded commands
# --------------------------------------------------------------------------------------------
def test_files_tests_keep_beside_the_code_are_test_files():
    """A golden file, a snapshot, a mock, an end-to-end suite or ``x-test.ts`` was application source: editing one
    was a code change and never a test file written or modified."""
    for path in ("pkg/x_test.go", "src/x.test.ts", "src/__tests__/x.js", "src/x-test.ts", "src/x_spec.js", "pkg/testdata/a.golden", "pkg/parser/testdata/in.json",
                 "src/__snapshots__/x.test.ts.snap", "__mocks__/a.js", "e2e/a.ts", "cypress/e2e/a.cy.ts", "src/login.cy.tsx", "test/helpers.go"):  # fmt: skip
        assert F.is_test_path(path), path
    for path in ("pkg/x.go", "src/latest.ts", "src/contest.js", "lib/spec.ts", "src/protest.go", "cmd/attest/main.go", "docs/testing.md"):
        assert not F.is_test_path(path), path


def test_lock_files_and_workspace_build_output_are_byproducts_and_go_mod_is_configuration():
    for path in ("go.sum", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "packages/core/dist/index.js", "apps/web/.next/server/app.js"):
        assert F.is_generated(path), path
    for path in ("packages/core/src/index.ts", "src/dist.ts", "internal/build/build.go", "package.json"):
        assert not F.is_generated(path), path
    assert F._CODE_EXT.search("go.mod") and F._CODE_EXT.search("tools/go.work") and not F._CODE_EXT.search("go.sum")


def test_installs_in_the_forms_the_package_managers_take():
    from recipe.grpo.qwen3_5.workflow_rubric.checks import actions as A

    for command in ("yarn --frozen-lockfile", "yarn --immutable --inline-builds", "npm update", "npm rebuild", "npm link", "yarn up zod", "go work sync", "go install golang.org/x/tools/cmd/goimports@latest"):
        assert A._INSTALL.search(command), command
    for command in ("go install ./...", "go install -v ./cmd/server", "go install .", "yarn test", "yarn build --watch", "npm run install-check"):  # the repository's own build / a script
        assert not A._INSTALL.search(command), command


def test_one_command_in_the_package_managers_spellings_is_one_command():
    """A document's recorded command is compared with the commands run: ``npx jest x`` / ``yarn jest x`` / ``pnpm exec
    jest x`` and ``npm test -- x`` / ``yarn test x`` / ``pnpm run test x`` were different commands."""
    from recipe.grpo.qwen3_5.workflow_rubric import refs

    n = refs.norm_command
    assert n("npx jest test/a.spec.js") == n("yarn jest test/a.spec.js") == n("cd /testbed && pnpm exec jest test/a.spec.js 2>&1 | tail -20") == "jest test/a.spec.js"
    assert n("npm test -- test/a.spec.js") == n("yarn test test/a.spec.js") == n("pnpm run test test/a.spec.js") == n("npm run test -- test/a.spec.js")
    assert n("yarn build") == n("npm run build") and n("npm t") == n("yarn test")
    assert n("npx vitest run a.test.ts") != n("npx jest a.test.ts") and n("yarn test a") != n("yarn test b")
    for same in ("yarn install", "pnpm add zod", "yarn", "npm install", "go test ./pkg/... -run TestA", "pytest tests/a.py -q"):
        assert n(same) == same.replace("./", ""), same  # installs and the other languages are left as they are
    assert n("python3 -m pytest tests/a.py") == n("pytest tests/a.py")


def test_stopping_at_the_first_failure_is_read_for_go_and_javascript():
    for segment in ("go test -failfast ./...", "npx jest --bail", "npx vitest run --bail=1", "npx mocha --bail test/"):
        assert R.stops_early(segment), segment
    assert not R.stops_early("go test -v ./...") and not R.stops_early("npx jest test/a.spec.js")


def test_a_recorded_test_id_is_matched_by_the_names_go_and_jest_use():
    """``field_type: test_id / failed_test_id`` knew a test by python's shapes: a jest title is free text (it has
    spaces), a go test function starts with a capital (python's class shape) and a quiet ``go test`` prints no name
    -- such ids never matched."""
    from types import SimpleNamespace

    from recipe.grpo.qwen3_5.workflow_rubric.checks import artifacts as A

    jest = "PASS test/getRenderer.spec.js\n  getRenderer\n    ✓ should return silent renderers when quiet (2 ms)\n    ✕ should return test renderers when NODE_ENV is test (5 ms)\n"
    vitest = " ✓ test/cookie.test.ts > parseCookies > can parse cookies 2ms\n FAIL  test/cookie.test.ts > setCookie > can merge unique cookies\n"
    titles = A._printed_titles([SimpleNamespace(observation=jest), SimpleNamespace(observation=vitest)])
    for entry in ("should return silent renderers when quiet", "`should return test renderers when NODE_ENV is test`", "parseCookies > can parse cookies",
                  "test/cookie.test.ts > setCookie > can merge unique cookies", "can merge unique cookies -> fails before the fix"):  # fmt: skip
        assert A._titled(entry, titles), entry
    for entry in ("all tests passed", "should return verbose renderers", "can parse", "none"):
        assert not A._titled(entry, titles), entry
    failing = ["test/cookie.test.ts::setCookie > can merge unique cookies", "lib/a/__tests__/index.js::rule › reject › inconsistent case"]
    forms = {t for f in failing for t in A._title_forms(f)}
    assert A._titled("can merge unique cookies", forms) and A._titled("rule › reject › inconsistent case", forms) and not A._titled("can parse cookies", forms)
    assert A._title_forms("tests/a.py::TestX::test_y") == {"tests/a.py::TestX::test_y", "TestX::test_y"} and A._title_forms("TestPtrToAny_Null") == set()

    # what the shown source defines: a quiet run prints no name
    assert [m.group(m.lastindex) for m in A._GO_DEF.finditer("func TestPtrToAny_Null(t *testing.T) {\n}\nfunc helper() {}\nfunc ExampleGenerator_SchemaRefs() {\n")] == ["TestPtrToAny_Null", "ExampleGenerator_SchemaRefs"]
    assert [m.group(m.lastindex) for m in A._JS_DEF.finditer("it('should return silent renderers when quiet', () => {})\ntest.each(cases)(\"adds %i\", fn)\ntest(`can parse cookies`, async () => {})\nsubmit('x')")] == ["should return silent renderers when quiet", "can parse cookies"]
    defs = {"TestPtrToAny_Null": {"codegen.testserver.followschema.ptr_to_any_test.go"}, "can parse cookies": {"test.cookie.test.ts"}, "test_parse": {"tests.test_a"}}
    go_scope, js_scope = {"codegen.testserver.followschema"}, {""}
    for entry, scopes in (("TestPtrToAny_Null", go_scope), ("followschema.TestPtrToAny_Null", go_scope), ("TestPtrToAny_Null/nil_value", go_scope), ("can parse cookies", js_scope), ("parseCookies › can parse cookies", js_scope)):
        assert A._anchored(entry, scopes, defs), entry
    for entry, scopes in (("TestGhost", go_scope), ("TestPtrToAny_Null", {"codegen.other"}), ("can parse everything", js_scope), ("TestClass", {"tests"})):
        assert not A._anchored(entry, scopes, defs), entry
    assert A._anchored("test_parse", {"tests"}, defs) and A._anchored("tests/test_a.py::test_parse", {"tests"}, defs)  # python as before


def test_a_file_a_tool_rewrote_is_written_at_that_tools_command():
    """``go generate`` / ``go mod tidy`` / ``prettier --write`` / ``jest -u`` / a build script change tracked files
    with no write in the trace: the change was "from outside the trace" and the first repository write unknown, which
    failed every item that asks when the repository was first written."""
    from recipe.grpo.qwen3_5.workflow_rubric.context import CommandFact, Facts

    def dated(commands: list[tuple[int, str, str]], diff: dict[str, str], authored=None) -> dict[str, tuple[int, str]]:
        f = Facts()
        f.commands = [CommandFact(step=n, action_index=0, command=c, cwd=cwd) for n, c, cwd in commands]
        return {e.path: (e.step, e.op) for e in F._date_by_tool(f, sorted(diff), diff, WD, authored)}

    # a build before any edit rewrote the generated file to what it was: the one after the run's first own write made the change
    looks = [(21, "npm run build", WD), (63, "npm run parser", WD), (77, "npm run parser", WD)]
    assert dated(looks, {"lib/parser.js": "M"}, authored=(61, 0)) == {"lib/parser.js": (63, "edit")}
    assert dated(looks, {"lib/parser.js": "M"}, authored=(90, 0)) == {"lib/parser.js": (21, "edit")} == dated(looks, {"lib/parser.js": "M"})

    diff = {"codegen/testserver/singlefile/generated.go": "M", "go.sum": "M", "go.mod": "M", "src/a.ts": "M", "src/__snapshots__/a.test.ts.snap": "M", "lib/parser.js": "M", "docs/x.md": "M", "yarn.lock": "M"}
    got = dated(
        [(3, "cat go.mod", WD), (5, "cd codegen/testserver/singlefile && go generate", WD), (7, "go mod tidy", WD), (9, "npx prettier --write src", WD),
         (11, "npx jest -u", WD), (13, "npm run parser 2>&1 | tail -3", WD), (15, "yarn add zod", WD)],
        diff,
    )  # fmt: skip
    assert got["codegen/testserver/singlefile/generated.go"] == (5, "edit") and got["go.sum"] == (7, "edit") and got["go.mod"] == (7, "edit")
    assert got["src/a.ts"] == (5, "edit")  # go generate runs any program: the first tool that can have written it
    assert got["src/__snapshots__/a.test.ts.snap"][0] == 5 and got["yarn.lock"] == (15, "edit")
    only = dated([(9, "npx prettier --write src", WD), (11, "npx jest -u", WD), (13, "npm run parser", WD)], diff)
    assert only["src/a.ts"] == (9, "edit") and only["src/__snapshots__/a.test.ts.snap"] == (11, "edit") and only["lib/parser.js"] == (13, "edit") and only["docs/x.md"] == (13, "edit")
    assert "go.sum" not in only and "yarn.lock" not in only
    # a reader, a test run, a formatter that only checks, a formatter run elsewhere: no tool that writes
    assert dated([(2, "gofmt -l .", WD), (3, "go test ./...", WD), (4, "npx prettier --check src", WD), (5, "npm test", WD), (6, "npx eslint src", WD), (7, "gofmt -w pkg/other", WD)], {"pkg/a/x.go": "M", "src/a.ts": "M"}) == {}
    assert dated([(7, "gofmt -w pkg/a", WD)], {"pkg/a/x.go": "M", "pkg/b/y.go": "M"}) == {"pkg/a/x.go": (7, "edit")}


# --------------------------------------------------------------------------------------------
# the workflows' own readings (agentos, speckit, openspec, aidlc_v4_gen)
# --------------------------------------------------------------------------------------------
def test_a_test_is_one_test_under_the_names_jest_gives_it():
    from recipe.grpo.qwen3_5.workflow_rubric import testread as T

    run_id = "test/cookie.test.ts::setCookie › can merge unique cookies"
    assert T.same_test(run_id, "can merge unique cookies") and T.same_test("setCookie > can merge unique cookies", run_id)
    assert not T.same_test(run_id, "can parse cookies") and not T.same_test(run_id, "test/other.test.ts::setCookie › can merge unique cookies")
    assert T.same_test("tests/test_io.py::TestA::test_x", "tests.test_io.TestA.test_x") and not T.same_test("tests/a.py::test_x", "tests/a.py::test_y")  # python as before
    assert T.name_of("test_x (pkg.mod.Class)") == (("test_x (pkg", ), "mod.Class)")  # an id of two words keeps python's reading


def test_agentos_reads_go_and_javascript_tests_scripts_and_verdicts():
    from recipe.grpo.qwen3_5.workflows.agentos_v2.reward import checks as C

    assert C.test_names("func TestRetry(t *testing.T) {\n}\nfunc helper() {}\n") == {"TestRetry"}
    assert C.test_names("describe('setCookie', () => {\n  it(\"can merge unique cookies\", () => {})\n  test.each(rows)(`adds`, fn)\n})") == {"setCookie", "can merge unique cookies"}
    assert C.test_names("def test_a():\n    pass\nclass TestB:\n    pass\n") == {"test_a", "TestB"}
    for path in ("checks/repro.go", "checks/repro.tsx", "checks/repro.mts", "checks/repro.py", "checks/run.sh"):
        assert C._SCRIPT_EXT.search(path), path
    for text in ("if got != want {\n\tpanic(\"mismatch\")\n}", "os.Exit(1)", "t.Fatalf(\"x\")", "if (a !== b) throw new Error('x')", "process.exit(1)", "expect(x).toBe(1)", "#!/bin/sh\ncd /testbed && go test ./pkg/auth -run TestRetry", "npx jest src/a.test.ts"):
        assert C._VERDICT.search(text), text
    assert not C._VERDICT.search("fmt.Println(result)\nconsole.log(result)")
    assert C.other_name_forms("test/cookie.test.ts::setCookie › can merge unique cookies") == {"can merge unique cookies"}
    assert C.other_name_forms("github.com/o/r/pkg::TestRetry/with_jitter") == {"TestRetry"} and C.other_name_forms("tests/a.py::TestX::test_y") == set()
    assert C._test_names_of("mod.Class.test_x") == {"Class", "test_x"}
    assert C.named_files("update `pkg/auth/token.go`, `src/App.tsx`, `go.mod` and `models.Sum`", "/testbed") == {"pkg/auth/token.go", "src/App.tsx", "go.mod"}
    assert C._no_basis("uses parseCookies") and not C._no_basis("uses parseCookies", camel=True) and not C._no_basis("see parse_cookies")


def test_speckit_reads_a_command_with_a_pipe_in_a_table_cell():
    from recipe.grpo.qwen3_5.workflows.speckit_bug.reward import checks as B
    from recipe.grpo.qwen3_5.workflows.speckit_sdd.reward import checks as S
    from recipe.grpo.qwen3_5.workflows.speckit_sdd.reward import speckit_kinds as K

    row = "| Regression suite | `go test ./... 2>&1 | tail -5` | pass | 12 packages |"
    assert B._cells(row) == ["Regression suite", "`go test ./... 2>&1 | tail -5`", "pass", "12 packages"] == S._cells(row)
    assert B._cells("| a | b \\| c | d |") == ["a", "b \\| c", "d"] and B._cells("| a | `x | y | z |") == ["a", "`x", "y", "z"]
    table = "| Check | Command | Result | Notes |\n|---|---|---|---|\n" + row + "\n"
    assert B.table_rows(table)[0]["result"] == "pass"
    for path in ("checks/go.mod", "checks/jest.config.js", "checks/out.snap", "checks/types.d.ts", "checks/notes.md"):
        assert B._DATA_FILE.search(path), path
    assert not B._DATA_FILE.search("checks/repro.go") and not B._DATA_FILE.search("checks/repro.test.ts") and S._SCRIPT_EXT.search("checks/repro.go")
    assert B._PATHLIKE.search("packages/@scope/pkg/src/[id].tsx").group(1) == "packages/@scope/pkg/src/[id].tsx"
    assert B._PATHLIKE.search("(see pkg/auth/token.go)").group(1) == "pkg/auth/token.go"
    assert B._norm_repo_path("./.eslintrc.js", "/testbed") == ".eslintrc.js" and B._norm_repo_path("/testbed/src/a.py:12", "/testbed") == "src/a.py"
    assert K.named_paths("update `app/(shop)/[id]/page.tsx` and .eslintrc.cjs", "/testbed") >= {"app/(shop)/[id]/page.tsx"}
    for text in ("fetch('https://github.com/o/r/issues/1')", 'http.Get("https://example.com/x")', "axios.get(`https://example.com`)", "requests.get('https://example.com')"):
        assert B._FETCH.search(text) and S._FETCH.search(text), text


def test_openspec_lists_failing_tests_by_the_names_the_runner_gives():
    from recipe.grpo.qwen3_5.workflows.openspec_ff.reward import penalty as P

    go = "- Command: `go test ./...`\n- Failing before the change: `TestCLIHelp` (go test ./humacli)\n- Result: fail\n"
    assert [n[1] for n in P.listed_failing(go)] == ["TestCLIHelp"]
    js = "- Failing before the change:\n  - `Server Sent Events (SSE) › streams events`\n  - `streams events with metadata`\n- Result: fail\n"
    listed = P.listed_failing(js)
    assert [n[1] for n in listed] == ["Server Sent Events (SSE) › streams events", "streams events with metadata"]
    actual = [P.name_of(i) for i in ("test/sse.test.ts::Server Sent Events (SSE) > streams events", "test/sse.test.ts::Server Sent Events (SSE) > streams events with metadata")]
    assert all(any(P._same_test(a, x) for x in listed) for a in actual) and all(any(P._same_test(x, a) for a in actual) for x in listed)
    py = "- Failing before the change: tests/test_a.py::test_x, test_mod.TestA.test_y\n"
    assert [n[1] for n in P.listed_failing(py)] == ["test_x", "TestA.test_y"]
    assert P.listed_failing("- Failing before the change: none\n") == []


def test_aidlc_v4_gen_selection_holds_what_narrows_a_go_or_jest_run():
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_gen.reward import checks as G

    a = G.selection("go test -run TestA ./pkg/auth", WD, WD)
    assert a == G.selection("cd /testbed && go test ./pkg/auth -run TestA -v", WD, WD) and a != G.selection("go test -run TestB ./pkg/auth", WD, WD) and a != G.selection("go test ./pkg/auth", WD, WD)
    assert G.selection("npx jest src/a.test.ts -t 'merges'", WD, WD) != G.selection("npx jest src/a.test.ts", WD, WD)
    assert G.selection("pytest tests/a.py::test_x", WD, WD) == frozenset({"tests/a.py::test_x", "runner:pytest"})


def test_aidlc_reads_the_test_names_go_and_jest_use():
    """aidlc_v5 / aidlc_v4_eval knew a test by ``test_x`` alone: a Baseline that lists ``TestCLIHelp`` or a jest title
    named no test, so the claims about it were not judged and the one-id-per-line rule failed every Go line."""
    for name in ("aidlc_v5", "aidlc_v4_eval"):
        import importlib

        EV = importlib.import_module(f"recipe.grpo.qwen3_5.workflows.{name}.reward.read")
        MS = importlib.import_module(f"recipe.grpo.qwen3_5.workflows.{name}.reward.measures")
        AT = importlib.import_module(f"recipe.grpo.qwen3_5.workflows.{name}.reward.methods.atom")

        assert EV.test_ids("- TestCLIHelp\n- ExampleGenerator_SchemaRefs\n- `TestRetry/with_jitter`") == ["TestCLIHelp", "ExampleGenerator_SchemaRefs", "TestRetry"]
        assert EV.test_ids("- `setCookie › can merge unique cookies`\n- `should return silent renderers when quiet`") == ["can merge unique cookies", "should return silent renderers when quiet"]
        # python's ids keep their reading: a class in an id is no test function of go's
        assert EV.test_ids("tests/test_a.py::TestFoo::test_bar, mod.TestBaz.test_qux, test_x (pkg.TestY)") == ["test_a", "test_bar", "test_qux", "test_x"]
        assert EV.test_ids("`pytest tests/test_a.py -q`, `go test ./pkg/... -run TestA`") == ["test_a", "TestA"]
        assert MS.test_names("tests/test_mod.py::test_parse, TestCLIHelp") == ["test_parse", "TestCLIHelp"]
        assert EV.names_test_ids("--- FAIL: TestCLIHelp (0.00s)\n") and EV.names_test_ids("    ✓ can parse cookies (2 ms)\n") and EV.names_test_ids("tests/a.py::test_x PASSED\n")
        assert not EV.names_test_ids("ok  \tgithub.com/o/r/pkg\t0.01s\n") and not EV.names_test_ids("Tests: 5 passed, 5 total\n")
        for line in ("TestCLIHelp", "github.com/o/r/humacli.TestCLIHelp", "`setCookie › can merge unique cookies`", "`should return silent renderers when quiet`", "tests/a.py::test_x", "test_x (mod.Class)"):
            assert AT._TEST_LIKE.search(line), (name, line)
        for line in ("test_x.py", "all tests in the package", "`npm test`", "pkg/auth/token_test.go"):
            assert not AT._TEST_LIKE.search(line), (name, line)
        assert EV.is_env_setup("npm ci") and EV.is_env_setup("go mod download") and EV.is_env_setup("yarn --frozen-lockfile") and EV.is_env_setup("pip install -e .")
        assert not EV.is_env_setup("go install ./...") and not EV.is_env_setup("yarn test") and not EV.is_env_setup("go test ./...")
        assert EV.test_command_tokens("go test -run TestA ./pkg/auth") == ["pkg/auth", "TestA"] and EV.test_command_tokens("npm test -- test/a.spec.js") == ["test/a.spec.js"]
        assert EV.test_command_tokens("pytest tests/a.py -k expr") == ["tests/a.py"]  # python as before
        assert EV.runs_script("npx tsx /tmp/repro.ts", "/tmp/repro.ts") and EV.runs_script("go run /tmp/repro.go", "/tmp/repro.go") and EV.runs_script("python /tmp/repro.py", "/tmp/repro.py")
        assert [m.group(0) for m in EV.PATH_RE.finditer("packages/@scope/pkg/src/[id].tsx and Makefile, see [src/a.py]")] == ["packages/@scope/pkg/src/[id].tsx", "Makefile", "src/a.py"]
        defs = AT._DEF_LINE.findall("-func (s *Server) Handle(w http.ResponseWriter, r *http.Request) {\n+func (s *Server) Handle(ctx context.Context, w http.ResponseWriter) {\n-export function parse(input, options) {\n-def parse(s, strict=False):\n")
        assert [(sign, n) for sign, n, _ in defs] == [("-", "Handle"), ("+", "Handle"), ("-", "parse"), ("-", "parse")]
        assert AT._runs_edited("go run ./cmd/server", {"cmd/server/main.go"}) and AT._runs_edited("node -e \"const p = require('./lib/parser'); console.log(p.parse('a'))\"", {"lib/parser.js"})
        assert not AT._runs_edited("go run /tmp/repro.go", {"cmd/server/main.go"}) and not AT._runs_edited("node -e \"console.log(1)\"", {"lib/parser.js"})
