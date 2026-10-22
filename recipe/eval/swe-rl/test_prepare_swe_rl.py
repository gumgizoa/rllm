#!/usr/bin/env python3
"""Unit tests for the grader hardening in prepare_swe_rl.py (swe_rl_v1_1).

Run inside the rllm venv (needs unidiff):  python recipe/eval/swe-rl/test_prepare_swe_rl.py
"""

from __future__ import annotations

import importlib.util
import re
import shlex
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("prep", Path(__file__).with_name("prepare_swe_rl.py"))
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)

MIXED = """\
diff --git a/tests/test_core.py b/tests/test_core.py
--- a/tests/test_core.py
+++ b/tests/test_core.py
@@ -1,3 +1,4 @@
 import core
+import pytest
 def test_a():
     assert core.f() == 1
diff --git a/tests/test_new_feature.py b/tests/test_new_feature.py
new file mode 100644
--- /dev/null
+++ b/tests/test_new_feature.py
@@ -0,0 +1,2 @@
+def test_new():
+    assert True
diff --git a/pkg/old_test.go b/pkg/old_test.go
deleted file mode 100644
--- a/pkg/old_test.go
+++ /dev/null
@@ -1,3 +0,0 @@
-package pkg
-
-func TestOld(t *testing.T) {}
diff --git a/pkg/server_test.go b/pkg/server_test.go
--- a/pkg/server_test.go
+++ b/pkg/server_test.go
@@ -10,2 +10,3 @@
 func TestServer(t *testing.T) {
+\tt.Parallel()
 }
diff --git a/test/old-name.test.js b/test/new-name.test.js
similarity index 90%
rename from test/old-name.test.js
rename to test/new-name.test.js
--- a/test/old-name.test.js
+++ b/test/new-name.test.js
@@ -1 +1 @@
-describe('old', () => {});
+describe('new', () => {});
diff --git a/lib/rules/__tests__/index.mjs b/lib/rules/__tests__/index.mjs
new file mode 100644
--- /dev/null
+++ b/lib/rules/__tests__/index.mjs
@@ -0,0 +1 @@
+export default 1;
"""


def test_classification() -> None:
    restore, remove = prep.classify_test_patch(MIXED)
    assert restore == ["tests/test_core.py", "pkg/old_test.go", "pkg/server_test.go", "test/old-name.test.js"], restore
    assert remove == ["tests/test_new_feature.py", "test/new-name.test.js", "lib/rules/__tests__/index.mjs"], remove


def test_empty_patch() -> None:
    assert prep.classify_test_patch("") == ([], [])


def test_restore_script_quoting() -> None:
    script = prep.build_restore_script("abc123", "/testbed", ["tests/a b.py", "tests/it's.py", "new file.go"])
    lines = script.splitlines()
    assert lines[3] == "cd /testbed || exit 2"
    assert lines[4] == "BASE=abc123"
    calls = [ln for ln in lines if ln.startswith("restore_one ")]
    assert len(calls) == 3, calls
    # Every call must round-trip to the original path through the shell.
    assert [shlex.split(c)[1] for c in calls] == ["tests/a b.py", "tests/it's.py", "new file.go"]
    assert lines[-1] == "exit $rc"


def test_restore_script_runtime_logic() -> None:
    """The per-path body handles all three states the grading fix calls out."""
    script = prep.build_restore_script("abc123", "/testbed", ["tests/x.py"])
    assert "git ls-files --error-unmatch" in script  # untracked detection
    assert 'rm -rf -- "$path"' in script  # agent file or directory
    assert 'git cat-file -e "$BASE:$path"' in script  # exists-in-base check
    assert 'git checkout "$BASE" -- "$path"' in script  # restore from base
    assert "rc=1" in script and "exit $rc" in script  # failures surface


def test_restore_script_no_paths() -> None:
    script = prep.build_restore_script("abc123", "/testbed", [])
    assert "restore_one " not in script and script.rstrip().endswith("exit $rc")


def _git(repo: Path, *args: str) -> str:
    import subprocess

    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin", "HOME": str(repo)}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout


def test_restore_script_harness_files() -> None:
    """Grader 1.2: harness files outside the test patch go back to base; gold files are kept."""
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "testbed"
        repo.mkdir()
        files = {
            "conftest.py": "# base\n",
            "pyproject.toml": "[project]\n",
            "pkg/a_test.go": "package pkg\n",
            "package.json": '{"scripts": {"test": "jest"}}\n',
            "src/mod.py": "x = 1\n",
            "tests/test_a.py": "def test_a(): pass\n",
            "go.mod": "module m\n",
            "node_modules/dep/conftest.py": "# dep\n",
        }
        for p, c in files.items():
            (repo / p).parent.mkdir(parents=True, exist_ok=True)
            (repo / p).write_text(c)
        _git(repo, "init", "-q")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "base")
        base = _git(repo, "rev-parse", "HEAD").strip()

        # The agent: edits tracked harness files, deletes one, plants new ones, fixes source.
        (repo / "conftest.py").write_text("def pytest_runtest_makereport(): pass  # cheat\n")
        (repo / "package.json").write_text('{"scripts": {"test": "true"}}\n')
        (repo / "pkg/a_test.go").unlink()
        (repo / "pkg/zz_test.go").write_text("package pkg\nfunc TestMain(m *testing.M) { os.Exit(0) }\n")
        (repo / "tests/conftest.py").write_text("# cheat\n")
        (repo / "tests/pytest.ini").write_text("[pytest]\naddopts = -p cheat\n")
        (repo / "sitecustomize.py").write_text("# cheat\n")
        (repo / "src/mod.py").write_text("x = 2  # the real fix\n")
        (repo / "go.mod").write_text("module m\nrequire x v1\n")  # not a harness file: kept
        (repo / "node_modules/dep/conftest.py").write_text("# dep changed\n")  # pruned: kept
        (repo / "pyproject.toml").write_text("[project]\n# gold edits this\n")  # gold path: kept

        script = Path(d) / "restore.sh"
        script.write_text(prep.build_restore_script(base, str(repo), ["tests/test_a.py"], keep=["pyproject.toml", "src/mod.py"]))
        r = subprocess.run(["bash", str(script)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

        assert (repo / "conftest.py").read_text() == "# base\n"
        assert (repo / "package.json").read_text() == files["package.json"]
        assert (repo / "pkg/a_test.go").read_text() == files["pkg/a_test.go"]
        for gone in ("pkg/zz_test.go", "tests/conftest.py", "tests/pytest.ini", "sitecustomize.py"):
            assert not (repo / gone).exists(), gone
        assert (repo / "src/mod.py").read_text() == "x = 2  # the real fix\n"
        assert (repo / "go.mod").read_text().endswith("require x v1\n")
        assert (repo / "node_modules/dep/conftest.py").read_text() == "# dep changed\n"
        assert (repo / "pyproject.toml").read_text().endswith("# gold edits this\n")


def test_evidence_mode() -> None:
    assert prep.evidence_mode("python", "pytest -vv tests/a.py\nrc=$?\n") == "pytest"
    assert prep.evidence_mode("python", "python runtests.py\n") is None
    assert prep.evidence_mode("go", "go test -v ./pkg -run .\n") == "go_test_v"
    assert prep.evidence_mode("go", "go test -v ./a\ngo test ./b\n") == "go_test"
    assert prep.evidence_mode("go", "go test -json ./a\n") is None
    assert prep.evidence_mode("typescript", "npx vitest run a.test.ts\n") == "js"
    # A heredoc body that mentions pytest is not a test command.
    assert prep.evidence_mode("python", "cat > x <<'EOF'\npytest\nEOF\npython run.py\n") is None


def test_evidence_patterns() -> None:
    import re as _re

    def hit(mode: str, log: str) -> bool:
        # grep -E's [[:space:]] is not Python re syntax; translate for the check.
        pats = [p.replace("[[:space:]]", r"\s") for p in prep._EVIDENCE[mode]]
        return any(_re.search(p, ln) for p in pats for ln in log.splitlines())

    assert hit("pytest", "==== 3 passed, 1 warning in 0.2s ====")
    assert not hit("pytest", "==== no tests ran in 0.01s ====")
    assert hit("go_test_v", "=== RUN   TestX\n--- PASS: TestX (0.00s)\nok  \tm/pkg\t0.1s")
    assert not hit("go_test_v", "ok  \tm/pkg\t0.1s")  # TestMain exit 0: no test ran
    assert hit("js", "      Tests  12 passed (12)")  # vitest
    assert hit("js", "Tests:       4 passed, 4 total")  # jest
    assert hit("js", "  7 passing (30ms)")  # mocha
    assert not hit("js", "No test files found, exiting with code 0")


def _hits(pats: list[str], log: str) -> bool:
    """Same check test.sh runs: grep -E -f <patterns> over the log."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".ere", delete=False) as f:
        f.write("\n".join(pats) + "\n")
    r = subprocess.run(["grep", "-a", "-E", "-f", f.name], input=log, capture_output=True, text=True)
    Path(f.name).unlink()
    return r.returncode == 0


def test_specific_evidence_go() -> None:
    tp = "diff --git a/pkg/a_test.go b/pkg/a_test.go\n@@ -1,3 +1,9 @@ func TestOld(t *testing.T) {\n+func TestNewThing(t *testing.T) {\n+}\n"
    pats = prep.specific_evidence("go_test_v", tp)
    assert _hits(pats, "=== RUN   TestNewThing\n--- PASS: TestNewThing (0.01s)")
    assert not _hits(pats, "--- PASS: TestForged (0.00s)")  # forged generic line
    assert not _hits(pats, "--- PASS: TestNewThingElse (0.00s)")  # prefix of another name
    # No new funcs: fall back to the edited funcs named in hunk headers.
    tp2 = "diff --git a/pkg/a_test.go b/pkg/a_test.go\n@@ -10,2 +10,3 @@ func TestOld(t *testing.T) {\n+\tt.Parallel()\n"
    assert _hits(prep.specific_evidence("go_test_v", tp2), "--- PASS: TestOld (0.00s)")
    # The patch's new func never runs (build tag); the script's -run filter names what does.
    pats = prep.specific_evidence("go_test_v", tp, 'go test -v . -run "TestParseDSN|TestOther"\n')
    assert _hits(pats, "--- PASS: TestParseDSN (0.00s)")
    assert not _hits(pats, "--- PASS: TestForged (0.00s)")


def test_specific_evidence_pytest_and_js() -> None:
    tp = "diff --git a/tests/test_core.py b/tests/test_core.py\n--- a/tests/test_core.py\n+++ b/tests/test_core.py\ndiff --git a/tests/helpers.py b/tests/helpers.py\n"
    pats = prep.specific_evidence("pytest", tp)
    assert _hits(pats, "tests/test_core.py::test_a PASSED                 [ 50%]")  # -v
    assert _hits(pats, "tests/test_core.py ..s.                            [100%]")  # default
    assert _hits(pats, "PASSED tests/test_core.py::test_a")  # -rA
    assert not _hits(pats, "============ 5 passed in 0.10s ============")  # forged summary
    assert not _hits(pats, "tests/test_core.py FFF")  # all failed
    js = "diff --git a/src/a.test.ts b/src/a.test.ts\n"
    jp = prep.specific_evidence("js", js)
    assert _hits(jp, " ✓ src/a.test.ts (3 tests) 12ms")  # vitest
    assert _hits(jp, "PASS src/a.test.ts")  # jest
    assert not _hits(jp, "      Tests  3 passed (3)")  # forged summary
    assert prep.specific_evidence("js", "diff --git a/src/a.ts b/src/a.ts\n") is None


def test_evidence_survives_ansi_colours() -> None:
    """test.sh strips colour codes before matching; runners colour PASS/check marks."""
    import subprocess

    src = (Path(__file__).with_name("prepare_swe_rl.py")).read_text()
    sed_expr = re.search(r"sed '(s/[^']*)' \"\$LOG\"", src).group(1)

    def colored_hit(pats: list[str], log: str) -> bool:
        clean = subprocess.run(["sed", sed_expr], input=log, capture_output=True, text=True).stdout
        return _hits(pats, clean)

    esc = "\x1b"
    jest = f"{esc}[0m{esc}[7m{esc}[1m{esc}[32m PASS {esc}[39m{esc}[22m{esc}[27m{esc}[0m {esc}[2msrc/{esc}[22m{esc}[1ma.test.ts{esc}[22m"
    vitest = f" {esc}[32m✓{esc}[39m src/a.test.ts {esc}[2m({esc}[22m{esc}[2m3 tests{esc}[22m{esc}[2m)"
    js = prep.specific_evidence("js", "diff --git a/src/a.test.ts b/src/a.test.ts\n")
    assert colored_hit(js, jest)
    # vitest puts a colour code between the check mark and the space: only the stripped log matches.
    assert not _hits(js, vitest) and colored_hit(js, vitest)
    gotest = f"{esc}[32m--- PASS: TestNewThing (0.00s){esc}[0m"
    go = prep.specific_evidence("go_test_v", "diff --git a/a_test.go b/a_test.go\n+func TestNewThing(t *testing.T) {\n")
    assert colored_hit(go, gotest)
    py = prep.specific_evidence("pytest", "diff --git a/tests/test_core.py b/tests/test_core.py\n")
    pyt = f"tests/test_core.py::test_a {esc}[32mPASSED{esc}[0m{esc}[32m                 [100%]{esc}[0m"
    assert colored_hit(py, pyt)


def test_real_v1_patches_parse(limit: int = 300) -> None:
    """Every real test patch must parse and yield at least one target."""
    import json
    import os

    src = Path(os.environ.get("SWE_RL_V1_PYTHON_JSONL", "/nonexistent"))
    if not src.exists():
        print("  (skip: set SWE_RL_V1_PYTHON_JSONL to a swe_rl_v1 python jsonl)")
        return
    n = 0
    with src.open() as f:
        for line in f:
            row = json.loads(line)
            restore, remove = prep.classify_test_patch(row["test_patch"])
            assert restore or remove, row["instance_id"]
            n += 1
            if n >= limit:
                break
    print(f"  parsed {n} real test patches")


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
