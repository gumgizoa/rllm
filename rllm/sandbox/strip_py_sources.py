"""Replace every ``.py`` under a site-packages directory with a sourceless ``.pyc``.

Run at agent-image bake time with the venv's own interpreter (bytecode is tied
to its minor version)::

    <venv>/bin/python strip_py_sources.py <site-packages>

Why: the agent venv is mounted into every task container, and some training
tasks are repos the agent's own dependencies ship a newer release of (fastmcp,
starlette, uvicorn, websockets, filelock, cyclopts under openhands-sdk). A
``grep -r`` or ``find`` over the container would surface that newer source -
the gold patch - to the agent. Without ``.py`` files there is no source text
to read, while the interpreter imports the code as before.

How: ``x.py`` is compiled to ``x.pyc`` beside it (the legacy layout; the import
system only loads a ``.pyc`` without its ``.py`` from there, never from
``__pycache__``), then ``x.py``, ``__pycache__`` and ``.pyi`` stubs are removed.
Docstrings stay (no ``-OO``): libraries read them at run time (fastmcp turns
them into tool descriptions). A file that does not compile on this interpreter
could never be imported by it, so it is removed too and only counted.
"""

from __future__ import annotations

import py_compile
import shutil
import sys
from pathlib import Path


def strip(root: Path) -> tuple[int, int, int]:
    compiled = uncompilable = stubs = 0
    for py in sorted(root.rglob("*.py")):
        if not py.is_file():
            continue
        try:
            py_compile.compile(str(py), cfile=str(py.with_suffix(".pyc")), doraise=True)
            compiled += 1
        except py_compile.PyCompileError:
            uncompilable += 1
        py.unlink()
    for stub in root.rglob("*.pyi"):
        stub.unlink()
        stubs += 1
    for cache in sorted(root.rglob("__pycache__"), reverse=True):
        shutil.rmtree(cache)
    return compiled, uncompilable, stubs


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: strip_py_sources.py <site-packages>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"strip_py_sources: not a directory: {root}", file=sys.stderr)
        return 1
    compiled, uncompilable, stubs = strip(root)
    left = next(root.rglob("*.py"), None)
    if left is not None:
        print(f"strip_py_sources: source left behind: {left}", file=sys.stderr)
        return 1
    print(f"strip_py_sources: {compiled} compiled, {uncompilable} uncompilable removed, {stubs} stubs removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
