"""The openhands-sdk agent image ships its site-packages without Python source."""

import subprocess
import sys

from rllm.sandbox.agent_image import _build_context, agent_image_tag
from rllm.sandbox.strip_py_sources import strip


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_strip_leaves_importable_bytecode_only(tmp_path):
    site = tmp_path / "site-packages"
    _write(site / "gold" / "__init__.py", "from .server import answer\n")
    _write(site / "gold" / "server.py", 'def answer():\n    """GOLD_DOCSTRING"""\n    return "GOLD_SECRET_42"\n')
    _write(site / "gold" / "server.pyi", "def answer() -> str: ...\n")
    _write(site / "gold" / "py2_only.py", "print 'not python 3'\n")
    _write(site / "gold" / "__pycache__" / "stale.cpython-312.pyc", "x")

    compiled, uncompilable, stubs = strip(site)

    assert (compiled, uncompilable, stubs) == (2, 1, 1)
    assert not list(site.rglob("*.py")) and not list(site.rglob("*.pyi"))
    assert not list(site.rglob("__pycache__"))
    assert sorted(p.name for p in site.rglob("*.pyc")) == ["__init__.pyc", "server.pyc"]
    # Imports keep working, docstrings included (libraries read them at run time).
    out = subprocess.run(
        [sys.executable, "-I", "-c", "import sys; sys.path.insert(0, sys.argv[1]); import gold; print(gold.answer(), gold.server.answer.__doc__)", str(site)],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )
    assert out.stdout.split() == ["GOLD_SECRET_42", "GOLD_DOCSTRING"]
    # The source text itself is gone: grep finds no line of it in readable form.
    assert subprocess.run(["grep", "-rIl", "return", str(site)], capture_output=True).stdout == b""


def test_tag_follows_the_build_context():
    files = _build_context("install", "openhands-sdk")
    assert files is not None and "strip_py_sources.py" in files and "strip_py_sources.py" in files["Dockerfile"]
    tag = agent_image_tag("install", files)
    assert tag == agent_image_tag("install", dict(files))
    assert tag != agent_image_tag("install", {**files, "Dockerfile": files["Dockerfile"] + "\n"})
    assert tag != agent_image_tag("install")
