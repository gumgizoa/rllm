"""workflows/_port.py: the converter every ported workflow's build.py uses.

    pytest recipe/grpo/qwen3_5/tests/test_port.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from recipe.grpo.qwen3_5.workflows._port import Copy, Edit, Port, Section, build, convert, copy_build, copy_drift, copy_write, drift, split_sections  # noqa: E402

UPSTREAM = """---
description: x
---

# Cmd

Intro uses $ARGUMENTS here.

## Hooks

check extensions.yml

## Body

   ## Indented heading stays (template inside a fence)

Ask the user before writing.
"""


def _port(tmp_path, **kw):
    base = dict(sources={"a": ("cmd.md", "a.md")}, out_dir=tmp_path / "out", upstream_commit="c")
    base.update(kw)
    return Port(**base)


def test_edits_sections_substitutions_apply_in_order(tmp_path):
    port = _port(
        tmp_path,
        edits=[Edit("a", "Ask the user before writing.", "Write once.", "semantic", "G4-1")],
        sections=[Section("a", "## Hooks", None, "env", "G7-1")],
        substitutions=[("$ARGUMENTS", "the issue")],
        forbidden=["$ARGUMENTS", "extensions.yml", "Ask the user"],
    )
    out = convert(port, "a", UPSTREAM)
    assert out.startswith("# Cmd") and "the issue" in out and "Write once." in out
    assert "## Hooks" not in out and "   ## Indented heading stays" in out


def test_anchor_must_occur_exactly_once(tmp_path):
    port = _port(tmp_path, edits=[Edit("a", "not upstream", "x", "env", "G1-1")])
    with pytest.raises(ValueError, match="anchor occurs 0 times"):
        convert(port, "a", UPSTREAM)


def test_missing_section_and_leftover_wording_fail(tmp_path):
    with pytest.raises(ValueError, match="sections not found"):
        convert(_port(tmp_path, sections=[Section("a", "## Nope", None, "env", "x")]), "a", UPSTREAM)
    with pytest.raises(ValueError, match="left after conversion"):
        convert(_port(tmp_path, forbidden=["Ask the user"]), "a", UPSTREAM)


def test_tags_and_sources_are_checked(tmp_path):
    with pytest.raises(ValueError, match="not declared"):
        _port(tmp_path, edits=[Edit("a", "x", "y", "loop", "n")])
    assert _port(tmp_path, edits=[Edit("a", "x", "y", "loop", "n")], extra_tags=["loop"]).tags == ("env", "semantic", "loop")
    with pytest.raises(ValueError, match="unknown source"):
        _port(tmp_path, edits=[Edit("b", "x", "y", "env", "n")])


def test_build_and_drift(tmp_path):
    (tmp_path / "up").mkdir()
    (tmp_path / "up" / "cmd.md").write_text(UPSTREAM)
    port = _port(tmp_path)
    built = build(port, tmp_path / "up")
    assert drift(port, built) == ["a.md"]
    port.out_dir.mkdir()
    (port.out_dir / "a.md").write_text(built["a.md"])
    assert drift(port, built) == []


STEPS = """# Cmd

## Steps

### 1. Keep

one

## Findings

a heading the step text prints

### 2. Hooks

check extensions.yml
"""


def test_level_three_section_cuts_one_step_up_to_the_next_heading(tmp_path):
    port = _port(tmp_path, frontmatter=False, sections=[Section("a", "### 2. Hooks", None, "env", "G7-1", level=3)])
    out = convert(port, "a", STEPS)
    assert "### 2. Hooks" not in out and "extensions.yml" not in out
    assert "### 1. Keep\n\none\n\n## Findings\n\na heading the step text prints\n" in out
    # a level-2 section of the same name is not a step: the step must be named with level=3
    with pytest.raises(ValueError, match="sections not found"):
        convert(_port(tmp_path, frontmatter=False, sections=[Section("a", "### 2. Hooks", None, "env", "x")]), "a", STEPS)


def test_level_two_split_ignores_steps():
    assert [h for h, _ in split_sections(STEPS)] == [None, "## Steps", "## Findings"]


def test_copy_is_byte_for_byte_with_the_executable_bit(tmp_path):
    up = tmp_path / "up"
    up.mkdir()
    raw = b"#!/usr/bin/env bash\n\n\n\necho  hi\r\n"  # blank runs and CRLF survive (convert would normalize them)
    (up / "x.sh").write_bytes(raw)
    copy = Copy(files={"x.sh": "bin/x.sh"}, out_dir=tmp_path / "out", executable=True)
    built = copy_build(copy, up)
    assert copy_drift(copy, built) == ["bin/x.sh"]
    copy_write(copy, built)
    dest = tmp_path / "out" / "bin" / "x.sh"
    assert dest.read_bytes() == raw and dest.stat().st_mode & 0o111
    assert copy_drift(copy, built) == []
    dest.chmod(0o644)
    assert copy_drift(copy, built) == ["bin/x.sh"]  # lost +x is drift
    copy_write(copy, built)
    dest.write_bytes(raw + b"#")
    assert copy_drift(copy, built) == ["bin/x.sh"]
    plain = Copy(files={"x.sh": "x.md"}, out_dir=tmp_path / "plain")
    copy_write(plain, copy_build(plain, up))
    assert not (tmp_path / "plain" / "x.md").stat().st_mode & 0o111
