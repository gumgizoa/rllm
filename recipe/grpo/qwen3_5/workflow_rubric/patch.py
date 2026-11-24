"""The final patch's test-file sections, and the existing lines a section changes or removes.

A workflow whose rubric judges the final change line by line (``prohibited_action`` with ``action:
test_file_modify`` and ``final_patch: true``) hands the rule, through its evaluation policy's ``inputs`` hook,
``{"test_patch": test_sections(...)}``: the test-file sections of the patch the harness recorded at the end of
the run (``episode.artifacts["patch"]``, ``run_artifacts.collect_command``: ``git diff --binary <base>`` of the
whole tree, cut at ``run_artifacts.MAX_PATCH_BYTES``). Live and offline read the same field of the same episode,
so no workflow collects anything more for it, and a workflow whose hook does not pass it is judged as before.

Bounds: only sections of test files (``facts.is_test_path``) are kept, whole sections in patch order up to
:data:`MAX_TEST_PATCH_CHARS` characters; a section that does not fit is listed under ``omitted`` and not judged
(the rule then knows of that file only what the trace shows, as before). When the recorded patch itself was cut
(``patch_bytes`` larger than what arrived), its last section is dropped the same way, since its missing tail
could hold the added counterpart of a removed line.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .facts import is_test_path

MAX_TEST_PATCH_CHARS = 256 * 1024
_HEAD = re.compile(r"diff --git a/(\S+) b/(\S+)$")
_HUNK = re.compile(r"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


def sections(patch: str) -> list[tuple[str, str]]:
    """``(path, section text)`` per file of a ``git diff`` text, in order (the path after ``b/``)."""
    out: list[tuple[str, list[str]]] = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            m = _HEAD.match(line)
            out.append((m.group(2) if m else "", [line]))
        elif out:
            out[-1][1].append(line)
    return [(p, "\n".join(ls)) for p, ls in out if p]


def test_sections(patch: Any, patch_bytes: Any = None, cap: int = MAX_TEST_PATCH_CHARS) -> dict[str, Any] | None:
    """The test-file sections of a recorded patch: ``{"files": {path: text}, "omitted": [path, ...]}``;
    None when there is no patch text."""
    if not isinstance(patch, str):
        return None
    secs = sections(patch)
    omitted: list[str] = []
    if isinstance(patch_bytes, int) and patch_bytes > len(patch.encode("utf-8")) and secs:
        omitted.append(secs.pop()[0])  # the recorded patch was cut inside (or right after) its last section
    files: dict[str, str] = {}
    size = 0
    for path, text in secs:
        if not is_test_path(path):
            continue
        if size + len(text) > cap:
            omitted.append(path)
            continue
        files[path] = text
        size += len(text)
    return {"files": files, "omitted": [p for p in omitted if is_test_path(p)]}


def _norm(line: str) -> str:
    return "".join(line.split())


def changed_lines(section: str) -> list[str] | None:
    """The lines of the base version that one file's section changes or removes.

    A ``-`` line counts unless, with all whitespace taken out, it is empty (a blank line) or equal to a ``+`` line of
    the same section (an indentation or spacing change, or a line moved within the file; each ``+`` line answers
    one ``-`` line). A section of a file the patch creates has no ``-`` lines. None when a hunk holds fewer lines
    than its header says (a cut section: not judged)."""
    removed: list[str] = []
    added: Counter[str] = Counter()
    lines = section.splitlines()
    i = 0
    while i < len(lines):
        m = _HUNK.match(lines[i])
        i += 1
        if m is None:
            continue
        old = int(m.group(1)) if m.group(1) is not None else 1
        new = int(m.group(2)) if m.group(2) is not None else 1
        while (old > 0 or new > 0) and i < len(lines):
            ln = lines[i]
            i += 1
            if ln.startswith("\\"):  # "\ No newline at end of file"
                continue
            tag, body = ln[:1], ln[1:]
            if tag == "-":
                old -= 1
                removed.append(body)
            elif tag == "+":
                new -= 1
                added[_norm(body)] += 1
            elif tag == " " or ln == "":
                old -= 1
                new -= 1
            else:
                return None
        if old > 0 or new > 0:
            return None
    out: list[str] = []
    for body in removed:
        key = _norm(body)
        if not key:
            continue
        if added[key] > 0:
            added[key] -= 1
            continue
        out.append(body)
    return out


__all__ = ["MAX_TEST_PATCH_CHARS", "changed_lines", "sections", "test_sections"]
