"""Shared converter for porting an upstream workflow's agent-facing text into ``workflows/<name>/docs/``.

A workflow's ``build.py`` declares a :class:`Port` -- which upstream files become which documents, and every
change to their text as a tagged :class:`Section` (replace or drop a ``## `` section) or :class:`Edit`
(replace one exact upstream string) -- and calls :func:`main`. The engine applies edits first (their anchors
are upstream text), then sections, then plain substitutions, and fails when

* an edit anchor does not occur exactly once (upstream reworded: the edit must be revisited),
* a section heading is missing upstream,
* a ``forbidden`` string survives (an edit missed a case),
* an edit or section carries a tag the port does not declare.

Tags say how far a document is from upstream. ``env`` (closes a gap between the upstream's setting and an
unattended sandbox run without changing what is asked) and ``semantic`` (changes what is asked) are always
declared; a port adds its own (``loop`` for speckit_bug's fix/test rounds). ``--list`` prints the edits by
tag for the porting record; ``--check`` exits 1 when the committed documents drifted from a fresh build.

    python -m recipe.grpo.qwen3_5.workflows.<name>.build --upstream /path/to/checkout [--check | --list]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

BASE_TAGS = ("env", "semantic")


@dataclass(frozen=True)
class Section:
    """Replace (``new``) or drop (``new=None``) a whole unindented ``## `` section of one source."""

    source: str
    heading: str
    new: str | None
    tag: str
    note: str


@dataclass(frozen=True)
class Edit:
    """Replace one exact upstream string of one source; it must occur exactly once."""

    source: str
    old: str
    new: str
    tag: str
    note: str


@dataclass(frozen=True)
class Port:
    """What one workflow's ``build.py`` declares.

    sources        key -> (path inside the upstream checkout, output path relative to ``out_dir``)
    out_dir        where the converted documents go (a subdirectory of the workflow's ``docs/``)
    upstream_commit  the commit ``out_dir`` was built from; another commit only warns -- the anchors decide
    substitutions  (old, new) applied to every source after edits and sections
    forbidden      strings that must not survive in any output
    extra_tags     tags beyond ``env`` / ``semantic`` this port uses
    frontmatter    strip a leading ``---`` YAML block from every source
    """

    sources: dict[str, tuple[str, str]]
    out_dir: Path
    upstream_commit: str
    sections: Sequence[Section] = ()
    edits: Sequence[Edit] = ()
    substitutions: Sequence[tuple[str, str]] = ()
    forbidden: Sequence[str] = ()
    extra_tags: Sequence[str] = ()
    frontmatter: bool = True
    tags: tuple[str, ...] = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "tags", (*BASE_TAGS, *self.extra_tags))
        for item in (*self.sections, *self.edits):
            if item.tag not in self.tags:
                raise ValueError(f"{item.source}: tag {item.tag!r} not declared (have {self.tags})")
            if item.source not in self.sources:
                raise ValueError(f"unknown source {item.source!r} (have {sorted(self.sources)})")


def strip_frontmatter(text: str) -> str:
    m = re.match(r"---\n.*?\n---\n", text, flags=re.S)
    if not m:
        raise ValueError("no frontmatter")
    return text[m.end() :].lstrip("\n")


def split_sections(text: str) -> list[tuple[str | None, str]]:
    """Split on unindented ``## `` lines (template headings inside indented fences are left alone)."""
    parts: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            parts.append((line.rstrip("\n"), [line]))
        else:
            parts[-1][1].append(line)
    return [(h, "".join(lines)) for h, lines in parts]


def apply_sections(port: Port, source: str, text: str) -> str:
    wanted = {s.heading: s for s in port.sections if s.source == source}
    out, seen = [], set()
    for heading, body in split_sections(text):
        s = wanted.get(heading)
        if s is None:
            out.append(body)
            continue
        seen.add(heading)
        if s.new is not None:
            out.append(s.new + "\n")
    missing = set(wanted) - seen
    if missing:
        raise ValueError(f"{source}: sections not found upstream: {sorted(missing)}")
    return "".join(out)


def apply_edits(port: Port, source: str, text: str) -> str:
    for e in (e for e in port.edits if e.source == source):
        n = text.count(e.old)
        if n != 1:
            raise ValueError(f"{source}: anchor occurs {n} times (want 1): {e.old[:90]!r}")
        text = text.replace(e.old, e.new)
    return text


def convert(port: Port, source: str, upstream_text: str) -> str:
    text = strip_frontmatter(upstream_text) if port.frontmatter else upstream_text
    text = apply_edits(port, source, text)
    text = apply_sections(port, source, text)
    for old, new in port.substitutions:
        text = text.replace(old, new)
    text = re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n"
    left = [w for w in port.forbidden if w in text]
    if left:
        raise ValueError(f"{source}: upstream wording left after conversion: {left}")
    return text


def build(port: Port, upstream: Path) -> dict[str, str]:
    """Output path (relative to ``out_dir``) -> converted text."""
    return {out: convert(port, key, (upstream / src).read_text(encoding="utf-8")) for key, (src, out) in port.sources.items()}


def drift(port: Port, built: dict[str, str]) -> list[str]:
    return [n for n, t in built.items() if not (port.out_dir / n).is_file() or (port.out_dir / n).read_text(encoding="utf-8") != t]


def git_head(path: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def list_edits(port: Port) -> None:
    for tag in port.tags:
        print(f"[{tag}]")
        for s in port.sections:
            if s.tag == tag:
                print(f"  {s.source:10} section {s.heading!r}: {s.note}")
        for e in port.edits:
            if e.tag == tag:
                print(f"  {e.source:10} edit: {e.note}")


def main(port: Port, argv: list[str] | None = None, *, description: str = "") -> int:
    ap = argparse.ArgumentParser(description=description or "Build docs from an upstream checkout.")
    ap.add_argument("--upstream", "--spec-kit", dest="upstream", type=Path, help="upstream checkout")
    ap.add_argument("--check", action="store_true", help="compare with the committed docs instead of writing")
    ap.add_argument("--list", action="store_true", help="print the edits by tag")
    args = ap.parse_args(argv)
    if args.list:
        list_edits(port)
        return 0
    if args.upstream is None:
        ap.error("--upstream is required")
    commit = git_head(args.upstream)
    if commit != port.upstream_commit:
        print(f"warning: upstream at {commit}, docs pinned to {port.upstream_commit}", file=sys.stderr)
    built = build(port, args.upstream)
    if args.check:
        bad = drift(port, built)
        for n in bad:
            print(f"drift: {port.out_dir.name}/{n}", file=sys.stderr)
        return 1 if bad else 0
    for name, text in built.items():
        dest = port.out_dir / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        print(f"wrote {dest.relative_to(port.out_dir.parent.parent)} ({text.count(chr(10))} lines)")
    return 0
