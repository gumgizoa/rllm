"""G0: the manifest -- every file the agent sees, and nothing else (DESIGN P1).

The sources of a rubric are exactly what ``WorkflowSpec`` puts in front of the agent: every file
under ``docs_dir`` (uploaded as-is to ``container_dir``, top-level dot entries excluded like the
uploader does), the instruction joined to the task text, and each harness's system prompt -- plus
the files generator.yaml's ``extra_sources`` declares: agent-visible text that lives outside
``docs_dir`` (a schema the sandbox setup installs and a CLI serves), each with its container path. Notes,
summaries and verifier code are never sources. Each entry records its role (which decides how later
stages treat it: templates are compiled, adapters are whitelisted, the system prompt is split into
sections), its sha256 (``rubric.lock`` and ``check`` detect drift), and, when the documents were
rendered from an upstream repository, the line map back to the upstream file so a reviewer can
follow a cited line to its origin (``upstream-map.json`` from ``scripts/render_workflow_docs.py``).
"""

from __future__ import annotations

import fnmatch
import hashlib
import importlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..schema import Source
from .config import ConfigError, GeneratorConfig, norm_rel

ROLE_PREFIX = {
    "adapter": "ADAPTER",
    "instruction": "INS",
    "core": "CORE",
    "stage_rule": "RULE",
    "command": "CMD",
    "skill": "SKILL",
    "template": "TPL",
    "schema": "SCHEMA",
    "script": "SCRIPT",
    "system_prompt": "SP",
    "reference": "REF",
}
_SECTION_OPEN = re.compile(r"^<([A-Z][A-Z0-9_]*)>\s*$")
_GENERIC_STEMS = {"skill", "readme", "index", "instructions"}


@dataclass
class Entry:
    """One manifest file. ``path`` is relative to the workflow package (posix)."""

    id: str
    path: str
    abs_path: str
    role: str
    sha256: str
    container_path: str = ""
    n_lines: int = 0
    docs_rel: str = ""  # path relative to docs_dir ("" for instruction / system prompt)
    harness: str = ""  # system prompt: the harness key
    sections: dict[str, str] = field(default_factory=dict)  # system prompt: section -> workflow|harness_generic
    section_lines: dict[str, list[int]] = field(default_factory=dict)  # section -> [first, last] content line
    upstream: dict[str, Any] = field(default_factory=dict)
    binary: bool = False
    _lines: list[str] | None = field(default=None, repr=False)

    def lines(self) -> list[str]:
        """The file's lines (1-based access via ``lines()[n - 1]``), read once."""
        if self._lines is None:
            try:
                self._lines = Path(self.abs_path).read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                self._lines = []
        return self._lines

    def text(self, a: int, b: int) -> str:
        ls = self.lines()
        return "\n".join(ls[max(a, 1) - 1 : max(b, 0)])

    def section_of(self, line: int) -> str | None:
        for name, (a, b) in self.section_lines.items():
            if a <= line <= b:
                return name
        return None

    def section_role(self, line: int) -> str | None:
        """System prompt only: the role of the section holding ``line``."""
        if self.role != "system_prompt":
            return None
        name = self.section_of(line)
        return self.sections.get(name or "_preamble", self.sections.get("*", "harness_generic"))

    def to_source(self) -> Source:
        up = dict(self.upstream)
        return Source(id=self.id, path=self.path, role=self.role, sha256=self.sha256, container_path=self.container_path, sections=dict(self.sections), upstream=up)

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


@dataclass
class Manifest:
    workflow: str
    pkg_dir: str
    container_dir: str
    entry_doc: str
    entries: list[Entry]

    def by_id(self, sid: str) -> Entry | None:
        for e in self.entries:
            if e.id == sid:
                return e
        return None

    def by_path(self, path: str) -> Entry | None:
        """Exact package-relative, docs-relative, container or absolute path; else a unique suffix match."""
        p = norm_rel(str(path))
        for e in self.entries:
            if p in (e.path, e.docs_rel, e.container_path, e.abs_path) and p:
                return e
        cands = [e for e in self.entries if e.path.endswith("/" + p) or (e.container_path and e.container_path.endswith("/" + p)) or p.endswith("/" + e.path)]
        return cands[0] if len(cands) == 1 else None

    def resolve(self, ref: str) -> Entry | None:
        """A source id or a path."""
        return self.by_id(ref) or self.by_path(ref)

    def to_sources(self) -> list[Source]:
        return [e.to_source() for e in self.entries]

    def to_json(self) -> dict:
        return {"workflow": self.workflow, "pkg_dir": self.pkg_dir, "container_dir": self.container_dir, "entry_doc": self.entry_doc, "entries": [e.to_json() for e in self.entries]}

    @classmethod
    def from_json(cls, d: dict) -> Manifest:
        return cls(workflow=d["workflow"], pkg_dir=d["pkg_dir"], container_dir=d["container_dir"], entry_doc=d["entry_doc"], entries=[Entry(**e) for e in d["entries"]])


# ----------------------------------------------------------------------------------------------
def load_spec(cfg: GeneratorConfig):
    """Import the workflow's ``SPEC``; returns ``(spec, package_dir)``."""
    mod_name, _, attr = cfg.spec_import.partition(":")
    mod = importlib.import_module(mod_name)
    spec = getattr(mod, attr or "SPEC")
    return spec, Path(mod.__file__).resolve().parent


def build(spec, cfg: GeneratorConfig, pkg_dir: Path) -> Manifest:
    """G0 for a ``WorkflowSpec``-like object (``docs_dir``, ``container_dir``, ``entry_doc``, ``instruction_file``, ``system_prompt``)."""
    pkg_dir = Path(pkg_dir).resolve()
    docs_dir = Path(spec.docs_dir).resolve()
    container = str(spec.container_dir).rstrip("/")
    files: list[tuple[Path, str, str, str]] = []  # (abs, docs_rel, container_path, harness)
    for top in sorted(docs_dir.iterdir()):
        if top.name.startswith("."):
            continue  # the uploader skips top-level dot entries (workflow_harness._doc_entries)
        for p in sorted([top] if top.is_file() else (q for q in top.rglob("*") if q.is_file())):
            if "__pycache__" in p.parts:
                continue
            rel = p.relative_to(docs_dir).as_posix()
            files.append((p, rel, f"{container}/{rel}", ""))
    for x in cfg.extra_sources:
        src = (pkg_dir / x["path"]).resolve()
        if src.is_file():
            files.append((src, "", x["container"], ""))
        elif src.is_dir():
            for p in sorted(q for q in src.rglob("*") if q.is_file() and "__pycache__" not in q.parts):
                files.append((p, "", f"{x['container'].rstrip('/')}/{p.relative_to(src).as_posix()}", ""))
        else:
            raise ConfigError(f"extra_sources: {x['path']} is not a file or directory of {pkg_dir}")
    if spec.instruction_file:
        files.append((Path(spec.instruction_file).resolve(), "", "", ""))
    for harness, tpl in sorted(dict(spec.system_prompt or {}).items()):
        if cfg.harness is None or harness in cfg.harness:
            files.append((Path(tpl).resolve(), "", "", harness))
    upstream = _load_upstream(pkg_dir / cfg.upstream_map)
    entries: list[Entry] = []
    instruction = Path(spec.instruction_file).resolve() if spec.instruction_file else None
    for abs_p, docs_rel, cpath, harness in files:
        rel = Path(os.path.relpath(abs_p, pkg_dir)).as_posix()
        data = abs_p.read_bytes()
        try:
            text = data.decode("utf-8")
            binary = False
        except UnicodeDecodeError:
            text, binary = "", True
        if harness:
            role = "system_prompt"
        elif instruction is not None and abs_p == instruction:
            role = "instruction"
        else:
            role = _role(rel, docs_rel, cfg, is_entry=docs_rel == spec.entry_doc)
        e = Entry(
            id="",
            path=rel,
            abs_path=str(abs_p),
            role=role,
            sha256=hashlib.sha256(data).hexdigest(),
            container_path=cpath,
            n_lines=len(text.splitlines()),
            docs_rel=docs_rel,
            harness=harness,
            binary=binary,
        )
        if role == "system_prompt":
            e.section_lines = sp_sections(text.splitlines())
            e.sections = {name: _sp_role(name, cfg) for name in e.section_lines}
        up = upstream.get(rel) or (upstream.get(docs_rel) if docs_rel else None)
        if up:
            e.upstream = _compress_upstream(up)
        entries.append(e)
    _assign_ids(entries, cfg)
    return Manifest(workflow=cfg.workflow, pkg_dir=str(pkg_dir), container_dir=container, entry_doc=str(spec.entry_doc), entries=entries)


def sp_sections(lines: list[str]) -> dict[str, list[int]]:
    """``<SECTION>`` ... ``</SECTION>`` blocks of a system prompt -> content line ranges; text outside is ``_preamble``."""
    out: dict[str, list[int]] = {}
    open_name, start = None, 0
    covered: set[int] = set()
    for i, ln in enumerate(lines, start=1):
        if open_name is None:
            m = _SECTION_OPEN.match(ln.strip())
            if m:
                open_name, start = m.group(1), i
        elif ln.strip() == f"</{open_name}>":
            out[open_name] = [start + 1, i - 1]
            covered.update(range(start, i + 1))
            open_name = None
    rest = [i for i, ln in enumerate(lines, start=1) if i not in covered and ln.strip()]
    if rest:
        out["_preamble"] = [rest[0], rest[-1]]  # last: section_of() tries named sections first
    return out


def _sp_role(name: str, cfg: GeneratorConfig) -> str:
    return cfg.sp_sections.get(name, cfg.sp_sections.get("*", "harness_generic"))


def _role(rel: str, docs_rel: str, cfg: GeneratorConfig, is_entry: bool) -> str:
    for glob, role in cfg.roles:
        if fnmatch.fnmatch(rel, glob) or (docs_rel and fnmatch.fnmatch(docs_rel, glob)) or (docs_rel and fnmatch.fnmatch("docs/" + docs_rel, glob)):
            return role
    low = docs_rel.lower() or rel.lower()
    name = low.rsplit("/", 1)[-1]
    if is_entry:
        return "core"
    if "template" in low:
        return "template"
    if name in ("schema.yaml", "schema.yml"):
        return "schema"
    if name.endswith((".sh", ".py", ".ps1", ".bash")):
        return "script"
    if name == "skill.md":
        return "skill"
    if "/commands/" in "/" + low:
        return "command"
    if "rule-details/" in low or "rules/" in low:
        return "stage_rule"
    return "reference"


def _assign_ids(entries: list[Entry], cfg: GeneratorConfig) -> None:
    fixed = {norm_rel(k): v for k, v in cfg.ids.items()}
    taken: set[str] = set()
    for e in entries:
        sid = fixed.get(e.path) or (fixed.get(e.docs_rel) if e.docs_rel else None) or (fixed.get("docs/" + e.docs_rel) if e.docs_rel else None)
        if sid:
            e.id = sid
            taken.add(sid)
    by_role: dict[str, int] = {}
    for e in entries:
        by_role[e.role] = by_role.get(e.role, 0) + 1
    for e in entries:
        if e.id:
            continue
        prefix = ROLE_PREFIX[e.role]
        if e.role in ("instruction", "system_prompt") and by_role[e.role] == 1:
            cands = [prefix]
        else:
            parts = Path(e.docs_rel or e.path).with_suffix("").parts
            stem = parts[-1] if parts else "x"
            if stem.lower() in _GENERIC_STEMS and len(parts) > 1:
                stem = parts[-2]
            if e.role == "system_prompt" and e.harness:
                stem = e.harness
            cands = [f"{prefix}_{_slug(stem)}"]
            if len(parts) > 1:
                cands.append(f"{prefix}_{_slug(parts[-2])}_{_slug(stem)}")
        sid = next((c for c in cands if c not in taken), None)
        n = 2
        while sid is None:
            if f"{cands[0]}_{n}" not in taken:
                sid = f"{cands[0]}_{n}"
            n += 1
        e.id = sid
        taken.add(sid)


def _slug(s: str) -> str:
    out = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()
    return out or "X"


def _load_upstream(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    try:
        d = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return {norm_rel(str(k)): v for k, v in d.items() if isinstance(v, dict)} if isinstance(d, dict) else {}


def _compress_upstream(up: dict) -> dict:
    """``line_map: [[rendered, upstream], ...]`` -> ``line_runs: [[rendered, upstream, n], ...]`` (consecutive runs)."""
    out = {k: v for k, v in up.items() if k != "line_map"}
    pairs = sorted((int(a), int(b)) for a, b in (up.get("line_map") or []) if a is not None and b is not None)
    runs: list[list[int]] = []
    for r, u in pairs:
        if runs and r == runs[-1][0] + runs[-1][2] and u == runs[-1][1] + runs[-1][2]:
            runs[-1][2] += 1
        else:
            runs.append([r, u, 1])
    if runs:
        out["line_runs"] = runs
    return out


def to_upstream(entry: Entry, line: int) -> int | None:
    """Rendered line -> upstream line (None when the line was added by rendering)."""
    for r, u, n in entry.upstream.get("line_runs", []):
        if r <= line < r + n:
            return u + (line - r)
    return None


def from_upstream(entry: Entry, line: int) -> int | None:
    """Upstream line -> rendered line (None when rendering dropped it)."""
    for r, u, n in entry.upstream.get("line_runs", []):
        if u <= line < u + n:
            return r + (line - u)
    return None
