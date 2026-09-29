"""Stage artifacts: what the skeleton prescribes, how to read one, and the 8/5/2/0 band.

Three concerns, in order:
  1. reconstructing the text a *shell* command wrote to an artifact path (heredoc, python
     triple-quoted literal, printf) -- editor tools hand the text over directly and skip this;
  2. parsing an artifact body against the prescribed skeleton (frontmatter, `##` sections,
     `- Label:` fields, `### Step n` plan blocks);
  3. grading: are the fields the v3 rubric scores filled in? Band 8 (all), 5 (one missing),
     2 (more), 0 (no artifact). Whether the content is TRUE is not decided here -- no rule can.

Two policy decisions, both deliberate:
  * STRICT SKELETON. `## Affected Scope` counts; `## Scope` does not, even with the right content,
    because core-workflow.md states that a renamed heading makes the stage unverifiable.
    `near_misses` records what the strictness cost so it stays visible.
  * THE GRADED FIELDS ARE THE v3 RUBRIC'S, NOT THE SKELETON'S. Sections the skeleton added later
    (Requirement Coverage, Plan Execution, Checks, Final Change) are extracted, not scored, so the
    difficulty of items 4-8 stays comparable to the measurements their weights came from.
"""

from __future__ import annotations

import re

ARTIFACT_DIR = "/tmp/swe-bench-pro"

# stage -> (filename, frontmatter name)
STAGE_FILES = {
    1: ("01-reverse-engineering.md", "reverse-engineering"),
    2: ("02-requirements-analysis.md", "requirements-analysis"),
    3: ("03-code-generation-planning.md", "code-generation-planning"),
    4: ("04-code-generation-generation.md", "code-generation-generation"),
    5: ("05-build-and-test.md", "build-and-test"),
}


def artifact_path(stage: int) -> str:
    return f"{ARTIFACT_DIR}/{STAGE_FILES[stage][0]}"


ARTIFACT_PATHS = {artifact_path(s): s for s in STAGE_FILES}

# `##` sections per stage: `graded` are scored, `extra` only extracted.
SECTIONS = {
    1: {"graded": ["Affected Scope", "Build & Test Commands", "Existing Tests", "Baseline"],
        "extra": []},
    2: {"graded": ["Functional Requirements", "Non-Functional Requirements",
                   "Edge Cases & Error Handling", "Assumptions"],
        "extra": []},
    3: {"graded": ["Plan", "Reproduction Script"], "extra": ["Requirement Coverage"]},
    4: {"graded": ["Changed Files", "Reproduction Script", "Deviations from Plan"],
        "extra": ["Plan Execution", "Checks"]},
    5: {"graded": ["Build", "Reproduction Script", "Existing Tests vs Baseline", "Fixes Applied",
                   "Outstanding Failures"],
        "extra": ["Final Change"]},
}


# --- 1. text a shell command wrote ---------------------------------------------------------

_HEREDOC_OPEN = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")
_TRIPLE = re.compile(r"(?:'''|\"\"\")(.*?)(?:'''|\"\"\")", re.DOTALL)
_QUOTED = re.compile(r"'((?:[^']|'\\'')*)'|\"((?:[^\"\\\\]|\\\\.)*)\"")


def heredocs(command: str):
    """(opener line, body, span) for every heredoc in a command.

    The opener LINE, not the `<<WORD` token: `cat > f <<'EOF'` and `cat <<'EOF' > f` put the
    redirect on opposite sides of the token. `span` is the body's (start, end) in `command`.
    """
    for m in _HEREDOC_OPEN.finditer(command):
        nl = command.find("\n", m.end())
        if nl == -1:
            continue
        opener = command[command.rfind("\n", 0, m.start()) + 1:nl]
        end = re.search(rf"^{re.escape(m.group(1))}\s*$", command[nl + 1:], re.M)
        stop = nl + 1 + (end.start() if end else len(command))
        yield opener, command[nl + 1:stop], (nl + 1, stop)


def _printf_body(command: str, path: str) -> str | None:
    """What `printf FMT ARG... > path` writes; None when not reconstructable.

    `%s\\n` joins arguments by line, bare `%s` concatenates; anything else -- or a double-quoted
    argument holding `$`/backtick, whose value the transcript never recorded -- is given up on
    rather than guessed.
    """
    for m in re.finditer(r"\bprintf\b", command):
        tail = command[m.end():]
        red = re.search(r">>?\s*([^\s|&;]+)", tail)
        if not red or red.group(1).strip("\"'") != path:
            continue
        args = []
        for sq, dq in _QUOTED.findall(tail[:red.start()]):
            if sq:
                args.append(sq)
                continue
            if re.search(r"(?<!\\\\)[$`]", dq):
                return None
            args.append(dq)
        if not args:
            return None
        fmt, rest = args[0], args[1:]
        if fmt in ("%s\\n", "%s\n"):
            return "\n".join(rest) + "\n"
        if fmt == "%s":
            return "".join(rest)
        return None
    return None


def shell_written_body(command: str, path: str) -> str | None:
    """The text a shell command writes to `path`, or None when the write cannot be reconstructed.

    The caller has already decided the command writes `path`; this only recovers the content.
    """
    for opener, body, _ in heredocs(command):
        if path in opener:
            return body
    for _, body, _ in heredocs(command):        # python3 <<'PY' ... write_text("""...""") ... PY
        if path in body and _TRIPLE.search(body):
            return max((m.group(1) for m in _TRIPLE.finditer(body)), key=len)
    return _printf_body(command, path)


# --- 2. skeleton parsing ------------------------------------------------------------------

FRONTMATTER = re.compile(r"\A\s*---\s*\n(.*?)\n\s*---\s*(?:\n|\Z)", re.DOTALL)
FENCE = re.compile(r"\A\s*```[a-zA-Z]*\s*\n(.*?)\n\s*```\s*\Z", re.DOTALL)
R_ID = re.compile(r"^\s*[-*+]\s*\*{0,2}(R\d+)\*{0,2}\s*:", re.M)
STEP_HEAD = re.compile(r"^\s{0,3}###\s*\*{0,2}Step\s+(\d+)\*{0,2}\s*(\[[^\]]*\])?", re.M)
SATISFIES = re.compile(r"\[\s*satisfies\s+([^\]]*)\]", re.I)
COVERAGE_LINE = re.compile(r"^\s*[-*+]\s*\*{0,2}(R\d+)\*{0,2}\s*:\s*(.+)$", re.M)
PATH_RE = re.compile(r"[\w./-]*[\w-]/[\w./-]+|[\w-]+\.[A-Za-z]{1,5}\b")

# The skeleton's own markers and obvious stand-ins. `none`/`n/a` are NOT here: they are values
# with a meaning (see NONE_VALUE) that some fields accept and others reject.
PLACEHOLDER = re.compile(r"^(?:tbd|todo|-+|\.{2,}|\?+|\[.*\]|<.*>)?$", re.I)
# A bare `no` is deliberately absent: `- Executed: no` is the value stage 4 prescribes.
NONE_VALUE = re.compile(r"^(?:none|none stated|not applicable|n/?a)\b[.,]?$", re.I)


def strip_fence(body: str) -> tuple[str, bool]:
    """Unwrap an artifact pasted inside one ```markdown fence -- the skeleton is shown fenced in
    every rule detail file, so copying the fence is a transcription slip, not missing work."""
    m = FENCE.match(body or "")
    return (m.group(1), True) if m else (body or "", False)


def frontmatter(body: str) -> dict:
    """The two-key frontmatter core-workflow.md prescribes. `keys` is reported next to `valid`
    so a botched frontmatter can be told apart from a stage never written."""
    m = FRONTMATTER.match(body or "")
    if not m:
        return {"present": False, "valid": False, "keys": [], "stage": None, "name": None}
    pairs, keys = {}, []
    for line in m.group(1).splitlines():
        kv = re.match(r"\s*([A-Za-z_][\w-]*)\s*:\s*(.*?)\s*$", line)
        if kv:
            keys.append(kv.group(1).lower())
            pairs[kv.group(1).lower()] = kv.group(2)
    stage = pairs.get("stage")
    return {"present": True, "keys": keys, "stage": stage, "name": pairs.get("name"),
            "valid": keys == ["stage", "name"] and (stage or "").strip().isdigit()}


def headings(body: str) -> list[tuple[str, str]]:
    """(text, body) for every `##` section; `###` and deeper stay inside their parent."""
    out, cur, buf = [], None, []
    for line in (body or "").splitlines():
        m = re.match(r"^\s{0,3}##(?!#)\s*\*{0,2}(.+?)\*{0,2}\s*$", line)
        if m:
            if cur is not None:
                out.append((cur, "\n".join(buf)))
            cur, buf = m.group(1).strip(), []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        out.append((cur, "\n".join(buf)))
    return out


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower().replace("&", "and"))


def section_map(stage: int, body: str) -> dict:
    """Prescribed section -> content (case and bold ignored), plus what strictness cost."""
    spec = SECTIONS[stage]
    wanted = spec["graded"] + spec["extra"]
    found = headings(body)
    exact, near, seen = {}, {}, set()
    for want in wanted:
        for text, content in found:
            if text.strip().rstrip(":").lower() == want.lower():
                exact[want] = content
                seen.add(text)
                break
        else:
            for text, _ in found:
                if _norm(text) == _norm(want):
                    near[want] = text
                    break
    wanted_norm = {_norm(w) for w in wanted}
    return {"exact": exact, "near_misses": near,
            "unknown": [t for t, _ in found if t not in seen and _norm(t) not in wanted_norm]}


def field_value(section_body: str, label: str) -> str | None:
    """Value of a `- Label: value` field with its indented continuation lines.

    None when the label is absent; "" when present but empty or a skeleton placeholder.
    """
    lines = (section_body or "").splitlines()
    lab = re.compile(rf"^\s*(?:[-*+]\s*)?\*{{0,2}}{re.escape(label)}\*{{0,2}}\s*:", re.I)
    other = re.compile(r"^\s*(?:[-*+]\s*)?\*{0,2}[A-Za-z][\w &/-]{2,30}\*{0,2}\s*:")
    for i, line in enumerate(lines):
        m = lab.match(line)
        if not m:
            continue
        val = [line[m.end():].strip()]
        for nxt in lines[i + 1:]:
            if not nxt.strip() or lab.match(nxt) or other.match(nxt) or nxt.startswith("#"):
                break
            val.append(nxt.strip())
        text = " ".join(v for v in val if v).strip(" *`")
        return "" if PLACEHOLDER.fullmatch(text) else text
    return None


def plan_steps(plan_body: str) -> list[dict]:
    """One record per `### Step n` block: number, `[satisfies ...]` tags, the four fields."""
    out = []
    marks = list(STEP_HEAD.finditer(plan_body or ""))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(plan_body)
        block = plan_body[m.end():end]
        tags = SATISFIES.search(m.group(2) or "")
        out.append({"n": int(m.group(1)),
                    "tags": re.findall(r"R\d+", tags.group(1)) if tags else [],
                    "fields": {k: field_value(block, k)
                               for k in ("Target", "Change", "Contract", "Verification")}})
    return out


def claimed_paths(changed_files_body: str) -> dict:
    """Paths stage 4 claims under `- Modified:` / `- Created:` -- those two labels only."""
    out = {"modified": [], "created": []}
    for line in (changed_files_body or "").splitlines():
        m = re.match(r"^\s*(?:[-*+]\s*)?\*{0,2}(Modified|Created)\*{0,2}\s*:\s*(.*)$", line, re.I)
        if not m:
            continue
        val = m.group(2).strip()
        if PLACEHOLDER.fullmatch(val) or NONE_VALUE.fullmatch(val):
            continue
        out[m.group(1).lower()].extend(PATH_RE.findall(val))
    return out


def parse(stage: int, body: str) -> dict:
    """Everything grading and fidelity need from one artifact body."""
    body, fenced = strip_fence(body)
    sm = section_map(stage, body)
    rec = {"frontmatter": frontmatter(body), "sections": sorted(sm["exact"]),
           "near_misses": sm["near_misses"], "unknown_sections": sm["unknown"],
           "section_bodies": sm["exact"], "fenced": fenced, "body": body}
    if stage == 2:
        rec["r_ids"] = R_ID.findall(body)
    if stage == 3:
        rec["steps"] = plan_steps(sm["exact"].get("Plan", ""))
        rec["coverage_ids"] = [m.group(1) for m in
                               COVERAGE_LINE.finditer(sm["exact"].get("Requirement Coverage", ""))]
    if stage == 4:
        rec["claims"] = claimed_paths(sm["exact"].get("Changed Files", ""))
    return rec


# --- 3. grading ---------------------------------------------------------------------------

# graded field -> (section, [(label, allow_none), ...] | None (section has content) | "allow_none")
SPEC = {
    1: {
        "scope":    ("Affected Scope", [("Files", False), ("Owning module", False),
                                        ("Language/framework", False)]),
        "commands": ("Build & Test Commands", [("Build", True), ("Test", False)]),
        "tests":    ("Existing Tests", [("Path", False), ("Contract", False)]),
        "baseline": ("Baseline", [("Passing", True), ("Failing", True)]),
    },
    2: {
        "functional":    ("Functional Requirements", None),
        "nonfunctional": ("Non-Functional Requirements", "allow_none"),
        "edge":          ("Edge Cases & Error Handling", None),
        "assumptions":   ("Assumptions", None),
        "rnum":          ("__r_ids__", None),
    },
    3: {
        "target":       ("__steps__", "Target"),
        "change":       ("__steps__", "Change"),
        "contract":     ("__steps__", "Contract"),
        "verification": ("__steps__", "Verification"),
        "tag":          ("__steps__", "__tags__"),
        "script":       ("Reproduction Script", [("Path", False), ("Exercises", False)]),
    },
    4: {
        "modified":   ("Changed Files", [("Modified", False)]),
        "created":    ("Changed Files", [("Created", True)]),
        "script":     ("Reproduction Script", [("Path", False), ("Executed", False)]),
        "deviations": ("Deviations from Plan", "allow_none"),
    },
    5: {
        "build":       ("Build", [("Result", False), ("Command", False)]),
        "script":      ("Reproduction Script", [("Result", False),
                                                ("Unmet requirements", True)]),
        "vs_baseline": ("Existing Tests vs Baseline", [("Command", False), ("Verdict", False),
                                                       ("Regressions", True),
                                                       ("Pre-existing failures", True)]),
        "fixes":       ("Fixes Applied", "allow_none"),
        "outstanding": ("Outstanding Failures", "allow_none"),
    },
}


def _section_has_content(body: str, allow_none: bool) -> bool:
    """A section whose skeleton is a bare bullet list, e.g. `## Assumptions`."""
    for line in (body or "").splitlines():
        text = line.strip().lstrip("-*+ ").strip(" *`")
        if not text:
            continue
        if NONE_VALUE.fullmatch(text):
            return allow_none
        if PLACEHOLDER.fullmatch(text):
            continue
        return True
    return False


def field_present(stage: int, parsed: dict, field: str) -> bool:
    """Is one graded field filled in, under the exact heading the skeleton prescribes?"""
    section, spec = SPEC[stage][field]
    if section == "__r_ids__":                       # S2: `- Rn:` ids, unique
        ids = parsed.get("r_ids", [])
        return bool(ids) and len(set(ids)) == len(ids)
    if section == "__steps__":                       # S3: every plan step carries the field
        steps = parsed.get("steps", [])
        if not steps:
            return False
        if spec == "__tags__":
            return all(s["tags"] for s in steps)
        return all(s["fields"].get(spec) for s in steps)
    body = parsed["section_bodies"].get(section)
    if body is None:
        return False
    if spec is None or spec == "allow_none":
        return _section_has_content(body, spec == "allow_none")
    for label, allow_none in spec:
        val = field_value(body, label)
        if val is None:  # `- Path: x — Contract: y` puts two labels on one line
            hit = re.search(rf"{re.escape(label)}\s*:\s*([^\n]*)", body, re.I)
            val = hit.group(1).strip(" *`") if hit else None
            if val is not None and PLACEHOLDER.fullmatch(val):
                val = ""
        if not val:
            return False
        if NONE_VALUE.fullmatch(val) and not allow_none:
            return False
    return True


def grade(stage: int, parsed: dict | None) -> dict:
    """The 8/5/2/0 band for one stage plus what the strict policy suppressed. Ungated: the
    frontmatter gate is applied by the scorer so `points` and `frontmatter_valid` stay separable."""
    if parsed is None:
        return {"points": 0, "missing": ["no artifact written"], "frontmatter_valid": False,
                "fenced": False, "near_misses": {}, "unknown_sections": []}
    missing = [f for f in SPEC[stage] if not field_present(stage, parsed, f)]
    return {"points": 8 if not missing else 5 if len(missing) == 1 else 2,
            "missing": missing,
            "frontmatter_valid": parsed["frontmatter"]["valid"],
            "fenced": parsed["fenced"],
            "near_misses": parsed["near_misses"],
            "unknown_sections": parsed["unknown_sections"]}
