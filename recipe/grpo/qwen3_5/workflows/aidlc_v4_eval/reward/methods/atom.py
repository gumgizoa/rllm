"""atom/*: the atomic rules the claims, rules and forms leave unscored, one function each, in rule id order (B core,
C cross-stage, D stage 1, E stage 2, F stage 3, G stage 4, H stage 5, S4 stage 4's skeleton).

Each is 1 (kept) / 0 (broken) / a share / None (nothing bears on it). Rules held per artifact are registered per stage
(``atom/<rule>@<stage>``). Where a rule came from is in its docstring when it is not one of the documents' first
extraction: the independent rule extraction (2026-10-27), the none-field review (2026-10-28), or a judge question
replaced by code (2026-10-27).
"""

from __future__ import annotations

import re

from .. import read as EV
from .. import skeleton as A
from .. import trace as F
from ..read import DUPLICATE, R_LINE, _field, _section_none, bullets, claimed_paths, command_core, failures, is_none, norm_path, r_ids, same_file
from . import STAGES, method

_LITERALS = {1: ["Recorded before any source file was modified."], 4: ["- Executed: no"]}

_TEST_LIKE = re.compile(r"::|\btest_\w+|\w+ \([\w.]+\)|\.[Tt]est\w*\b")

_ARROW = re.compile(r"->|→")

_ISSUE_PATH = re.compile(r"(?<![\w/.-])((?:[\w-]+/)+[\w.-]+\.(?:py|pyi|js|ts|go|rs|java|rb|c|h|cpp|cfg|toml|ini))\b")

_PERF = re.compile(r"\b(?:performance|slow(?:er|ly)?|fast(?:er)?|speed|memory|complexity|efficien\w*|latency|O\(|quadratic|linear time|time-?out)\b", re.I)

_LANG = {"py": "python", "pyi": "python", "js": "javascript", "ts": "typescript", "go": "go", "rs": "rust", "java": "java", "rb": "ruby", "c": "c", "h": "c", "cpp": "c++"}

_DOC = re.compile(r"\.(?:md|rst)$|(?:^|/)[^/]*(?:plan|summary|report|notes|design)[^/]*\.(?:md|txt|rst)$", re.I)

_ARTIFACT = re.compile(r"/tmp/swe-bench-pro/(0[1-5])-[\w-]+\.md")

_READ_VERB = re.compile(r"^\s*(?:sudo\s+)?(?:cat|head|tail|less|more|grep|egrep|sed\s+-n|awk|nl)\b")

# A message that hands the run back to the user (E10c, before the last turn: the narrower phrases, since a
# working note says "should I check ..." to itself)
_ASK_USER = re.compile(
    r"\b(?:would you like me to|do you want me to|shall i (?:proceed|continue|go ahead)|please (?:confirm|approve|advise|let me know)"
    r"|awaiting your|let me know (?:if|whether|how) you|before i (?:proceed|continue), (?:please|could you))\b",
    re.I,
)

_PY_SCRIPT = re.compile(r"\bpython[\d.]*\s+(?!-[mc]\b)[^\s|;&]+\.py\b")

# A module boundary written in Owning module: a dotted name (`django.db.models`) or a path (`django/db/models`)
_BOUNDARY = re.compile(r"(?<![\w./])((?:[A-Za-z_]\w*)(?:[./][A-Za-z_]\w*)+)/?(?![\w])")

# A signature a plan Contract names: `parse(s)`, `QuerySet.filter(**kwargs)`
_SIGNATURE = re.compile(r"(?<![\w.])((?:\w+\.)*(\w+))\s*\(([^()]*)\)")

_DEF_LINE = re.compile(r"^([-+])\s*(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)", re.M)

_NEW_CONTRACT = re.compile(r"\b(?:new|introduc\w*|add(?:s|ed)?)\b", re.I)

_LABEL_LINE = re.compile(r"^\s*[-*]\s*[A-Z][\w /&().-]*:")

_ASK = re.compile(r"\b(?:would you like|shall i|should i|do you want|let me know|please (?:confirm|review|advise|approve)|awaiting your|your (?:approval|confirmation|input))\b", re.I)

_REDUCE = re.compile(r"(?<!\S)-[a-zA-Z]*q[a-zA-Z]*\b|--quiet\b|--tb=(?:short|line|no)\b|--no-header\b")

_STASH = re.compile(r"^\s*git\s+stash(?:\s+(?:push|save)\b.*)?\s*$|^\s*(?:git\s+apply|patch)\b.*\s-R\b")

_UNSTASH = re.compile(r"^\s*git\s+stash\s+(?:pop|apply)\b")

_CODE_LIKE = re.compile(r"_|\.|[a-z][A-Z]")

_GREP_FED = re.compile(r"\|\s*(?:xargs\s+)?grep|-exec\s+grep")

# a find that names what it looks for: anything but a bare "*" or "*.ext" (``-name "py.py"`` is a lookup)
_NAME_FILTER = re.compile(r"-(?:i?name|i?path|regex)\s+(?!['\"]?\*(?:\.\w+)?['\"]?(?:\s|$))\S")

_IDENT = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")

_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

_ABBREV = re.compile(r"\b(?:e\.g|i\.e|etc|vs|cf)\.", re.I)

_CREATE = re.compile(r"\(\s*create\s*\)", re.I)


def _plain_segments(command: str) -> list[str]:
    """The command split at ``&&`` / ``||`` / ``;`` / newlines, quoted strings kept (``evidence.segments``
    blanks them, and a ``find -name "*foo*"`` filter is in the quotes)."""
    return [s.strip() for s in re.split(r"&&|\|\||;|\n", F.drop_heredoc_bodies(command or "")) if s.strip()]


def _near(a: str, b: str) -> bool:
    """One edit apart (insert, delete or substitute), not a case-only difference."""
    if a == b or a.lower() == b.lower() or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    s, t = (a, b) if len(a) < len(b) else (b, a)
    return any(t[:i] + t[i + 1 :] == s for i in range(len(t)))


def _lines(value: str) -> list[str]:
    """A field's items, one per line (a field value's continuation lines are joined by spaces, so a
    multi-item value reads as one line: "one per line" is then not kept)."""
    return [x.strip(" -*`") for x in re.split(r"\n+", value or "") if x.strip(" -*`")]


def _dotted(target: str) -> str:
    """A test target as a dotted name, so a pytest path and a Django label compare: ``tests/migrations/
    test_operations.py::OperationsTests::test_x`` and ``migrations.test_operations.OperationsTests.test_x``
    both read ``migrations.test_operations.OperationsTests.test_x``."""
    t = target.removeprefix("/testbed/").removeprefix("./")
    path, _, node = t.partition("::")
    if path.endswith(".py"):
        t = path[:-3].replace("/", ".") + ("." + node.replace("::", ".") if node else "")
    return t.removeprefix("tests.")


def _covers(selection: list[str], target: str) -> bool:
    """``target`` is in ``selection``: the same, or under a file / class / module of it."""
    for u in selection:
        for a, b in ((target, u), (_dotted(target), _dotted(u))):
            if a == b or any(a.startswith(b.rstrip("/") + sep) for sep in ("::", ".", "/")):
                return True
    return False


def _raw_rows(body: str, label: str) -> list[str]:
    """A field's physical lines in the artifact: the label line's value and the lines under it up to the next
    label (``skeleton.field_value`` joins them, so "one per line" cannot be read from the value)."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        hit = re.match(rf"^\s*[-*]\s*{re.escape(label)}\s*:(.*)$", line)
        if not hit:
            continue
        rows = [hit.group(1)]
        for nxt in lines[i + 1 :]:
            if not nxt.strip() or _LABEL_LINE.match(nxt) and not nxt.startswith((" ", "\t")):
                break
            rows.append(nxt)
        return [r.strip(" -*`") for r in rows if r.strip(" -*`")]
    return []


def _required_params(params: str) -> list[str]:
    """The positional parameters a caller must pass, in order (no default, not *args / **kwargs / self)."""
    out = []
    for raw in params.split(","):
        p = raw.strip()
        if not p or p.startswith("*") or "=" in p or p in ("self", "cls", "/"):
            continue
        out.append(p.split(":")[0].strip())
    return out


def _frac(flags: list[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


def _full_paths(m, paths: list[str]) -> float | None:
    """The share of ``paths`` written in full: a bare file name the run knows under a directory is not."""
    verdicts = []
    for p in paths:
        q = norm_path(p)
        if q in m.known:
            verdicts.append(True)
        elif "/" not in q and any(k.rsplit("/", 1)[-1] == q and "/" in k for k in m.known):
            verdicts.append(False)
    return _frac(verdicts)


def _planned_creates(m) -> list[str]:
    """The files the plan marks ``(create)``."""
    return [t for s in m.steps if _CREATE.search(s["fields"].get("Target") or "") for t in claimed_paths(s["fields"].get("Target"))]


def _doc_steps(m) -> list[tuple[int, int]]:
    """(step, stage) of every stage document read."""
    return [(s.n, int(d)) for s in m.run.steps for a in s.actions if a.acts for d in F.doc_reads(a) if d != "core"]


# -- B: core ---------------------------------------------------------------------------------------------


def _rewrites(m) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Every rewrite of an artifact (stage, step), and those after a later stage began. A later stage begins with its
    first sign after artifact k's first write: a later stage's document read, a later artifact written, a source edit
    (after stages 1-3) or a test or reproduction run (after stage 4) -- not a document read ahead before artifact k
    was written (that is A3b's concern)."""
    obs, art_writes, write_step, repro = m.obs, m.art_writes, m.w, m.repro
    doc_steps = _doc_steps(m)
    edits = sorted(n for p in obs.source_edits for n in obs.edit_steps.get(p, []))

    def next_began(k: int) -> int | None:
        first = art_writes[k][0]
        signs = [n for n, d in doc_steps if d > k and n > first]
        signs += [w for j, w in write_step.items() if j > k and w is not None]
        signs += [n for n in edits if n > first] if k <= 3 else []
        if k == 4:
            signs += [n for n, _, _ in obs.tests_in(after=first)] + ([n for n, _, _ in obs.ran(repro, after=first)] if repro else [])
        return min(signs) if signs else None

    rewrites = [(k, n) for k, steps in art_writes.items() for n in steps[1:]]
    later = [(k, n) for k, n in rewrites if (b := next_began(k)) is not None and n > b]
    return rewrites, later


@method("atom/B3a", materials=("WRITE", "DOC", "EDIT", "TEST", "SCRIPT"))
def b3a(m):
    """An artifact written once, whole, in its stage (no append, no blank filled in later in its own stage)."""
    if not m.art_writes:
        return None
    rewrites, later = _rewrites(m)
    return 0.0 if len(rewrites) > len(later) else 1.0


@method("atom/B4a", materials=("WRITE", "DOC", "EDIT", "TEST", "SCRIPT"))
def b4a(m):
    """An earlier stage's artifact never rewritten once a later stage began."""
    if not m.art_writes:
        return None
    _, later = _rewrites(m)
    return 0.0 if later else 1.0


@method("atom/B5d", materials=("AP", "COLLECT"), stages=(1, 4))
def b5d(m, st):
    """The skeleton's fixed sentences kept (01 "Recorded before any source file was modified.", 04 "- Executed: no")."""
    p = m.parsed.get(st)
    return None if p is None else float(all(lit in p["body"] for lit in _LITERALS[st]))


@method("atom/B6b", materials=("AP", "COLLECT"), stages=STAGES)
def b6b(m, st):
    """The frontmatter's stage is the stage."""
    p = m.parsed.get(st)
    if p is None or not p["frontmatter"]["present"]:
        return None
    return float((p["frontmatter"]["stage"] or "").strip() == str(st))


@method("atom/B6c", materials=("AP", "COLLECT"), stages=STAGES)
def b6c(m, st):
    """The frontmatter's name is the stage's."""
    p = m.parsed.get(st)
    if p is None or not p["frontmatter"]["present"]:
        return None
    return float((p["frontmatter"]["name"] or "").strip() == A.STAGE_FILES[st][1])


@method("atom/B8", materials=("WRITE", "SHELLCLS"))
def b8(m):
    """No artifact read back after it was written (the same command's read-back too). The recipe runs without history
    condensing, so what the run wrote is still in its context: no read recovers it."""
    write_step = m.w
    if not any(write_step.values()):
        return None
    reread = False
    for step in m.run.steps:
        for a in step.actions:
            texts = [a.path or ""] if a.kind == "view" else [re.sub(r"\d?>>?\s*\S+", "", s) for s in _plain_segments(a.command or "") if _READ_VERB.match(s)] if a.kind == "shell" else []
            reread |= any(write_step.get(int(x.group(1))) is not None and step.n >= write_step[int(x.group(1))] for t in texts for x in _ARTIFACT.finditer(t))
    return 0.0 if reread else 1.0


@method("atom/B10", materials=("EDIT",))
def b10(m):
    """No design, plan or report document created outside the artifact directory."""
    return 0.0 if any(_DOC.search(p) and not p.startswith(A.ARTIFACT_DIR) and not EV.is_test_file(norm_path(p), m.tests) for p in m.obs.created) else 1.0


@method("atom/B11", materials=("WRITE", "PATH"))
def b11(m):
    """Each stage writes one artifact file (core "Each stage writes one artifact file"): nothing else in the artifact
    directory but a script (the reproduction script may live there); documents elsewhere are B10's. Read from what
    the directory held at the end when it was collected (a temporary file moved onto an artifact -- `tr ... < 01.md >
    tmp.md && mv tmp.md 01.md`, swebv100 000016 -- is no second file). Found by the independent rule extraction."""
    if not any(m.w.values()):
        return None
    left = m.art_dir or m.obs.created
    extra = [p for p in left if p.startswith(A.ARTIFACT_DIR + "/") and p not in A.ARTIFACT_PATHS and not m.is_repro(p) and not re.search(r"\.(?:py|sh)$", p)]
    return 0.0 if extra else 1.0


# -- C: across stages -------------------------------------------------------------------------------------


@method("atom/C2", materials=("DOC", "WRITE"))
def c2(m):
    """No stage document read again after its stage's artifact was written: the run went back."""
    write_step = m.w
    if not any(write_step.values()):
        return None
    reread = [step.n for step in m.run.steps for a in step.actions for d in F.doc_reads(a) if d != "core" and write_step.get(int(d)) is not None and step.n > write_step[int(d)]]
    return 0.0 if reread else 1.0


# -- D: stage 1 -------------------------------------------------------------------------------------------


@method("atom/D1b", materials=("AP", "COLLECT", "ISSUE", "PATH", "SEEN", "TESTFILE"))
def d1b(m):
    """A source file the issue names is in Affected Scope (a test file the issue quotes, e.g. in a test diff, is not the
    source scope to start from; nor an example or documentation file it shows the bug with: step24 000354)."""
    if not m.p1:
        return None
    files = claimed_paths(_field(m.p1, "Affected Scope", "Files"))
    named = [p for p in dict.fromkeys(_ISSUE_PATH.findall(m.issue)) if norm_path(p) in m.known and not EV.is_test_file(norm_path(p), m.tests) and not re.match(r"(?:examples?|docs?)/", norm_path(p))]
    return (1.0 if any(same_file(p, f) for p in named for f in files) else 0.0) if named else None


@method("atom/D3b", materials=("AP", "COLLECT", "PATH"))
def d3b(m):
    """Owning module states the module's boundary in the repository and the Files lie inside it. The boundary is read
    from a dotted module or a path in the field (`django.db.models (Django ORM)` -> django/db/models); a field with no
    such token (a name only) leaves it undecided. Replaced the judge question 2026-10-27."""
    if not m.p1:
        return None
    owning = _field(m.p1, "Affected Scope", "Owning module") or ""
    bounds = [norm_path(b.replace(".", "/")) if "/" not in b else norm_path(b) for b in _BOUNDARY.findall(owning)]
    bounds = [b.rstrip("/") for b in bounds if b and not b.endswith((".py", ".md", ".txt"))]
    # the source files listed (a test file listed there belongs to Existing Tests, not to the owning module)
    files1 = [norm_path(f) for f in claimed_paths(_field(m.p1, "Affected Scope", "Files")) if not EV.is_test_file(norm_path(f), m.tests)]
    # a bare package name is a boundary too when it is a directory of a listed file (`pkg` for pkg/mod.py, lib/pkg/mod.py)
    bounds += [w for w in re.findall(r"[A-Za-z_]\w*", owning) if any(w in f.split("/")[:-1] for f in files1)]

    def inside(f: str, b: str) -> bool:
        # under the boundary directory, the boundary's own module file (`matplotlib.figure` for lib/matplotlib/figure.py),
        # at any depth (a `lib/` or `src/` source root before it)
        return f == b or f.startswith(b + "/") or f"/{b}/" in f"/{f}" or f"/{f}".endswith(f"/{b}.py")

    if bounds and files1:
        return _frac([any(inside(f, b) for b in bounds) for f in files1])
    return None


@method("atom/D4a", materials=("AP", "COLLECT"))
def d4a(m):
    """Language/framework names the language of the Files."""
    if not m.p1:
        return None
    files = claimed_paths(_field(m.p1, "Affected Scope", "Files"))
    exts = [f.rsplit(".", 1)[-1].lower() for f in files if "." in f.rsplit("/", 1)[-1]]
    langs = {_LANG[e] for e in exts if e in _LANG}
    lang = (_field(m.p1, "Affected Scope", "Language/framework") or "").lower()
    if langs and lang:
        return float(any(re.search(rf"(?<![\w+]){re.escape(x)}(?![\w+])", lang) for x in langs))
    return None


@method("atom/D4b", materials=("SHELLCLS", "WRITE", "EDIT"))
def d4b(m):
    """Stage 1 does not survey the repository: tree / ls -R, or a find from the root that names nothing and feeds no
    grep. One listing to get one's bearings is allowed; a second is a survey (on swebv100 a single `find /testbed
    -name "*.py" | head -20` was 32 of 93 runs)."""
    before1 = m.w.get(1) if m.w.get(1) is not None else m.obs.first_edit
    if before1 is None:
        return None
    surveys = sum(
        bool(re.match(r"(?:tree\b|ls\s+-[a-zA-Z]*R)", s) or (re.match(r"find\s+(?:\.|/testbed)/?(?:\s|$)", s) and not _NAME_FILTER.search(s) and not _GREP_FED.search(s)))
        for _, cmd, _ in m.obs.shell_in(before=before1)
        for s in _plain_segments(cmd)
    )
    return 0.0 if surveys >= 2 else 1.0


@method("atom/D5", materials=("AP", "COLLECT", "PATH", "SEEN"))
def d5(m):
    """Files and Existing Tests' Path are full paths from the repository root."""
    if not m.p1:
        return None
    return _full_paths(m, claimed_paths(_field(m.p1, "Affected Scope", "Files")) + claimed_paths(_field(m.p1, "Existing Tests", "Path")))


@method("atom/D5b", materials=("AP", "COLLECT", "PATH"))
def d5b(m):
    """Files lists one path per line (01 skeleton "[full paths from the repository root, one per line]"). Found by the
    independent rule extraction."""
    if not m.p1:
        return None
    rows = _raw_rows(m.p1["section_bodies"].get("Affected Scope") or "", "Files")
    if any(claimed_paths(r) for r in rows):
        return 0.0 if any(len(claimed_paths(r)) > 1 for r in rows) else 1.0
    return None


@method("atom/D7b", materials=("AP", "COLLECT", "NONE", "TARGET"))
def d7b(m):
    """The recorded test command names its targets."""
    if not m.p1:
        return None
    test = _field(m.p1, "Build & Test Commands", "Test")
    if test and not is_none(test) and (targets := EV.test_targets(test)) is not None:
        return float(bool(targets))
    return None


@method("atom/D8", materials=("AP", "COLLECT"))
def d8(m):
    """A pytest command reduces its output (-q, --tb=short ...); other runners have no common flag."""
    if not m.p1:
        return None
    test = _field(m.p1, "Build & Test Commands", "Test") or ""
    if re.search(r"\bpytest\b", test):
        return 1.0 if _REDUCE.search(test) else 0.0
    return None


@method("atom/D10a", materials=("SEEN", "TESTFILE", "TEST", "WRITE"))
def d10a(m):
    """Stage 1 looked for the tests that cover the scope: read an existing test file or ran tests before 01 was
    written (which tests the artifact names, and whether they were seen, is e1_test_path_seen's)."""
    w1, obs = m.w.get(1), m.obs
    if w1 is None:
        return None
    new = obs.new_files
    read_tests = [p for p, n in obs.viewed.items() if n <= w1 and EV.is_test_file(norm_path(p), m.tests) and p not in new]
    return 1.0 if read_tests or obs.tests_in(before=w1) else 0.0


@method("atom/D12b", materials=("AP", "COLLECT", "NONE"))
def d12b(m):
    """Baseline lists one test id per line: a line listing several ("test_a, test_b"; brackets masked for parametrized
    ids) breaks it."""
    if not m.p1:
        return None
    ids = [x for k in ("Passing", "Failing") if (v := _field(m.p1, "Baseline", k)) and not is_none(v) for x in _lines(v)]
    several = [x for x in ids if sum(bool(_TEST_LIKE.search(p)) for p in re.sub(r"\[[^\]]*\]", "[]", x).split(",")) > 1]
    return float(all(_TEST_LIKE.search(x) for x in ids) and not several) if ids else None


# -- E: stage 2 -------------------------------------------------------------------------------------------


@method("atom/E3a", materials=("AP", "COLLECT", "NONE"))
def e3a(m):
    """One sentence per requirement, read with quotes, code spans and abbreviations masked."""
    if not m.p2:
        return None
    reqs = [v for _, v in R_LINE.findall(m.p2["body"]) if not is_none(v)]
    masked = [_ABBREV.sub("x", re.sub(r"`[^`]*`|\"[^\"]*\"|'[^']*'", "x", v.strip())) for v in reqs]
    return _frac([len([s for s in _SENTENCE.split(v) if s.strip()]) == 1 for v in masked])


@method("atom/E4a", materials=("AP", "COLLECT"))
def e4a(m):
    """The requirements are numbered as one sequence R1..Rn."""
    if not m.p2:
        return None
    seq = list(dict.fromkeys(m.p2.get("r_ids", [])))
    return float(seq == [f"R{i}" for i in range(1, len(seq) + 1)]) if seq else None


@method("atom/E7b", materials=("AP", "COLLECT", "NONE", "ISSUE"))
def e7b(m):
    """No non-functional requirement the task does not state (an issue about performance leaves it undecided)."""
    if not m.p2:
        return None
    nfr = m.p2["section_bodies"].get("Non-Functional Requirements")
    if nfr is None or not m.issue:
        return None
    r_lines = R_LINE.findall(nfr)
    stated = [v for _, v in r_lines if not is_none(v)] if r_lines else [x for x in bullets(nfr) if not is_none(x)]
    return 1.0 if not stated else (None if _PERF.search(m.issue) else 0.0)


@method("atom/E8c", materials=("AP", "COLLECT", "NONE"))
def e8c(m):
    """Each edge case is written "condition -> behaviour"."""
    if not m.p2:
        return None
    edge = m.p2["section_bodies"].get("Edge Cases & Error Handling") or ""
    return _frac([bool(_ARROW.search(v)) for _, v in R_LINE.findall(edge) if not is_none(v)])


@method("atom/E10a", materials=("EDIT",))
def e10a(m):
    """No question file written for the user."""
    return 0.0 if any(re.search(r"question", p.rsplit("/", 1)[-1], re.I) for p in m.obs.created) else 1.0


@method("atom/E10b", materials=("FINAL",))
def e10b(m):
    """The run does not end asking for input (``final_words``: its last response and its finish message)."""
    if not m.run.steps:
        return None
    said_last = m.final_words if m.final_words is not None else m.run.steps[-1].message.strip()
    return 0.0 if _ASK.search(said_last) or said_last.endswith("?") else 1.0


@method("atom/E10c", materials=("MSG",))
def e10c(m):
    """No approval asked before the end either (core "never ask for approval, never wait for input"); the last turn is
    E10b's. Found by the independent rule extraction."""
    if len(m.run.steps) <= 1:
        return None
    return 0.0 if any(_ASK_USER.search(s.message or "") for s in m.run.steps[:-1]) else 1.0


# -- F: stage 3 -------------------------------------------------------------------------------------------


@method("atom/F1b", materials=("AP", "COLLECT"))
def f1b(m):
    """The plan's steps are numbered 1..n."""
    if not m.steps:
        return None
    return float([s["n"] for s in m.steps] == list(range(1, len(m.steps) + 1)))


@method("atom/F2a", materials=("AP", "COLLECT", "PATH", "SEEN"))
def f2a(m):
    """The steps' Targets are full paths."""
    if not m.steps:
        return None
    return _full_paths(m, [t for s in m.steps for t in claimed_paths(s["fields"].get("Target") or "")])


@method("atom/F2b", materials=("AP", "COLLECT"))
def f2b(m):
    """Each Target says "(modify in place)" or "(create)"."""
    if not m.steps:
        return None
    return _frac([bool(re.search(r"\(\s*(?:modify in place|create)\s*\)", s["fields"].get("Target") or "", re.I)) for s in m.steps])


@method("atom/F3", materials=("AP", "COLLECT", "ISSUE", "PATCH", "SEEN"))
def f3(m):
    """The issue's names are not altered: an identifier the issue names in code that the plan and the patch never use
    as written but use one edit apart (`refit_time` for `refit_time_`) -- a renamed name, not a different one. (```fit```
    inline fences read as one span; only code-like names: an underscore, a dot or camelCase.)"""
    issue = m.issue
    if not (m.steps and issue):
        return None
    spans = re.findall(r"`([^`\n]+)`", re.sub(r"`{3,}", "`", issue))
    said = {t for span in spans for t in _IDENT.findall(span) if len(t) >= 6 and _CODE_LIKE.search(t)}
    added = "\n".join(line[1:] for line in (m.whole_patch or "").splitlines() if line.startswith("+") and not line.startswith("+++"))
    used_text = m.p3["body"] + "\n" + added
    used = {part for t in _IDENT.findall(used_text) for part in (t, *t.split("."))}

    def as_written(t: str) -> bool:
        return re.search(rf"(?<!\w){re.escape(t)}(?!\w)", used_text) is not None

    kept = [t for t in said if as_written(t)]
    # A near name the issue also writes, or the code the run read defines, is the real name (an issue's typo,
    # swebv500 step24 000371: `strip_accent_unicode` for strip_accents_unicode), not a rename.
    read = issue + "\n" + "\n".join(m.obs.observations)
    renamed = [t for t in said if not as_written(t) and any(_near(t, u) and not re.search(rf"(?<!\w){re.escape(u)}(?!\w)", read) for u in used)]
    if kept or renamed:
        return 0.0 if renamed else 1.0
    return None


@method("atom/F4b", materials=("AP", "COLLECT", "NONE"))
def f4b(m):
    """The reproduction script exercises the edge-case requirements: the share it lists."""
    if not m.p2:
        return None
    edge_ids = r_ids(m.p2["section_bodies"].get("Edge Cases & Error Handling"))
    real = [r for r in edge_ids if not any(rid == r and is_none(v) for rid, v in R_LINE.findall(m.p2["body"]))]
    if not (real and m.p3):
        return None
    exercises = r_ids(_field(m.p3, "Reproduction Script", "Exercises"))
    return _frac([r in exercises for r in real])


def _step_targets(m) -> list[str]:
    """The plan's targets but its own reproduction script (no test file even when named test_*.py; left in the
    repository, r_repo_clean catches it)."""
    return [t for s in m.steps for t in claimed_paths(s["fields"].get("Target")) if not m.is_repro(t)]


@method("atom/F7", materials=("AP", "COLLECT", "PATH", "TESTFILE"))
def f7(m):
    """No plan step targets a test file."""
    targets = _step_targets(m) if m.steps else []
    if not targets:
        return None
    return 0.0 if any(EV.is_test_file(norm_path(t), m.tests) for t in targets) else 1.0


@method("atom/F8a", materials=("AP", "COLLECT", "PATH", "SEEN", "WRITE"))
def f8a(m):
    """No ``(create)`` over a file the run had seen before the plan."""
    creates = _planned_creates(m) if m.steps else []
    if not creates:
        return None
    return 0.0 if any(m.obs.seen(t, before=m.w.get(3)) for t in creates) else 1.0


@method("atom/F8b", materials=("AP", "COLLECT", "PATH"))
def f8b(m):
    """No plan step targets a duplicate or backup variant of a file."""
    targets = _step_targets(m) if m.steps else []
    if not targets:
        return None
    return 0.0 if any(DUPLICATE.search(t) or F.BACKUP_RE.search(t) for t in targets) else 1.0


@method("atom/F9b", materials=("AP", "COLLECT", "PATH", "SEEN", "EDIT"))
def f9b(m):
    """A planned new file goes under a directory the repository has (one the run read a file in or named in a
    command), not a structure of its own."""
    if not m.steps:
        return None
    obs = m.obs
    planned = [norm_path(t) for t in _planned_creates(m)]
    dirs = [t.rsplit("/", 1)[0] for t in planned if "/" in t]
    read = {norm_path(p) for p in obs.viewed} | {norm_path(p) for p in obs.edited if p not in obs.new_files}
    return _frac([any(k.startswith(d + "/") for k in read) or any(d in cmd for _, cmd, _ in obs.shell) for d in dirs])


# -- G: stage 4 -------------------------------------------------------------------------------------------


def _end4(m) -> int | None:
    return m.w.get(4) if m.w.get(4) is not None else m.w.get(5)


@method("atom/G1a", materials=("AP", "COLLECT", "PATH", "EDIT", "WRITE"))
def g1a(m):
    """The plan's steps carried out in order (each step's first edit in stage 4, ties allowed)."""
    w3, end4 = m.w.get(3), _end4(m)
    if w3 is None:
        return None
    firsts = []
    for s in m.steps:
        hits = [n for t in claimed_paths(s["fields"].get("Target")) for q, ns in m.obs.edit_steps.items() if same_file(q, t) for n in ns if n > w3 and (end4 is None or n < end4)]
        if hits:
            firsts.append(min(hits))
    return float(firsts == sorted(firsts)) if len(firsts) >= 2 else None


@method("atom/G3a", materials=("EDIT", "SEEN", "WRITE", "SHELLCLS"))
def g3a(m):
    """Each file written whole in stage 4 inside the repository was looked for first: read, named in a command, or its
    directory listed. The reproduction script is not one of them: the rule (04 Step 2, core "File Modification") is
    about the plan's targets and duplicate variants of existing files (on step24 262 of 403 runs failed G3a, and in a
    sample of 60 every unchecked file was the reproduction script)."""
    w3, end4, obs = m.w.get(3), _end4(m), m.obs
    if w3 is None:
        return None
    made4 = [
        (p, n)
        for p, n in obs.created.items()
        if n > w3 and (end4 is None or n < end4) and not F.OUTSIDE_REPO_RE.match(p if p.startswith("/") else "/" + p) and not p.startswith("tmp/") and not m.is_repro(p)
    ]

    def looked(path: str, n: int) -> bool:
        base, parent = path.rsplit("/", 1)[-1], (path.rsplit("/", 1)[0] if "/" in path else "")
        if obs.seen(path, before=n - 1):
            return True
        for k, cmd, _ in obs.shell:
            if k >= n:
                break
            # (a file at the repository root: its listing, not a find that searches the tree for something
            # else -- step24 000361's stage-1 `find /testbed -name "*.py" | xargs grep` looked for no file)
            listing = r"(?:ls|find|test|stat|\[)\b" if parent else r"(?:ls|test|stat|\[)\b"
            if base in cmd or any(re.match(listing, s) and (parent in s if parent else not re.search(r"\s/testbed/\S", s)) for s in _plain_segments(cmd)):
                return True
        return False

    return _frac([looked(p, n) for p, n in made4])


@method("atom/G3c", materials=("AP", "COLLECT", "PATH", "PATCH", "EDIT"))
def g3c(m):
    """The creations the plan marks are made (a file that existed, or that the run saw before the plan, left out)."""
    final, obs = m.final, m.obs
    if not m.steps or final is None:
        return None
    made = {norm_path(p) for p in final[1]} | {norm_path(p) for p in obs.created}
    existing = {norm_path(p) for p in final[0]} - {norm_path(p) for p in final[1]}
    planned = [t for t in _planned_creates(m) if not any(same_file(t, e) for e in existing) and not obs.seen(t, before=m.w.get(3))]
    return _frac([any(same_file(t, x) for x in made) for t in planned])


@method("atom/G4b", materials=("AP", "COLLECT", "PATCH", "TESTFILE"))
def g4b(m):
    """No new test file added to the repository."""
    if m.final is None:
        return None
    new_tests = [p for p in m.final[1] if EV.is_test_file(norm_path(p), m.tests) and not m.is_repro(p) and "/" in p and p.endswith(".py") and "/_build/" not in p]
    return 0.0 if new_tests else 1.0


@method("atom/G5", materials=("AP", "COLLECT", "PATCH"))
def g5(m):
    """The patch keeps the signatures the plan's Contracts preserve: for each `name(...)` a Contract names (not one it
    introduces), a `def name` the patch rewrites keeps its required positional parameters in order, and is not
    removed; a function the patch does not touch decides nothing (on step24 no run touched one in the first 150
    checked). Replaced the judge question 2026-10-27."""
    patch = m.whole_patch
    if not (m.steps and patch):
        return None
    named: dict[str, str] = {}
    for s in m.steps:
        contract = s["fields"].get("Contract") or ""
        if _NEW_CONTRACT.search(contract) and not re.search(r"\b(?:preserv\w*|unchanged|keep\w*|same)\b", contract, re.I):
            continue
        for _, name, params in _SIGNATURE.findall(contract):
            named.setdefault(name, params)
    defs: dict[str, dict[str, list[str]]] = {}
    for sign, name, params in _DEF_LINE.findall(patch):
        defs.setdefault(name, {}).setdefault(sign, []).append(params)
    verdicts = []
    for name in named:
        d = defs.get(name)
        if not d or "-" not in d:
            continue
        if "+" not in d:
            verdicts.append(False)  # removed
            continue
        old = [_required_params(x) for x in d["-"]]
        new = [_required_params(x) for x in d["+"]]
        verdicts.append(all(any(o == n[: len(o)] for n in new) for o in old))
    return _frac(verdicts) if verdicts else None


@method("atom/G7c", materials=("DOC", "WRITE", "TEST"))
def g7c(m):
    """Stage 4 executes nothing it changed (04 "modify the source files in place and write the reproduction script,
    executing neither yet"): no test attempt between the stage's start and its artifact. Running the reproduction
    script there is G7b's (r_repro_not_in_stage4). Found by the independent rule extraction."""
    start4 = m.read_step.get("04") if m.read_step.get("04") is not None else m.w.get(3)
    w4 = m.w.get(4)
    if start4 is None or w4 is None:
        return None
    return 0.0 if m.obs.attempts_in(after=start4, before=w4) else 1.0


@method("atom/G8b", materials=("AP", "COLLECT", "NONE"))
def g8b(m):
    """Each deviation is classified (local correction / structural invalidation)."""
    if not m.p4:
        return None
    dev = [x for x in bullets(m.p4["section_bodies"].get("Deviations from Plan")) if not is_none(x)]
    return _frac([bool(re.match(r"(?:local correction|structural invalidation)\b", x, re.I)) for x in dev])


# -- H: stage 5 -------------------------------------------------------------------------------------------


@method("atom/H1a", materials=("AP", "COLLECT", "NONE"))
def h1a(m):
    """Stage 5 reruns the build stage 1 recorded."""
    if not (m.p1 and m.p5):
        return None
    b1, b5 = _field(m.p1, "Build & Test Commands", "Build"), _field(m.p5, "Build", "Command")
    if b1 and b5 and not is_none(b1) and not is_none(b5):
        return float(command_core(b1) == command_core(b5))
    return None


@method("atom/H1b", materials=("AP", "COLLECT", "NONE", "TARGET", "SHELLCLS", "CMDMATCH", "WRITE"))
def h1b(m):
    """Stage 5 ran the build stage 1 recorded ("Run the build or type-check command Reverse Engineering recorded");
    whether it succeeded as 05 says is e5_build_result's. None recorded (`not applicable`), or an install written in
    the build field (D9's to forbid, not a build to run), leaves it out."""
    w4 = m.w.get(4)
    if w4 is None or not m.p1:
        return None
    build = _field(m.p1, "Build & Test Commands", "Build")
    if build and not is_none(build) and command_core(build) and EV.test_targets(build) is None and not EV.is_env_setup(build):
        return 1.0 if m.obs.command_runs(build, after=w4, before=m.w.get(5)) else 0.0
    return None


@method("atom/H1c", materials=("AP", "COLLECT", "NONE", "TARGET", "CMDMATCH", "EXIT", "EDIT", "TEST", "SCRIPT", "WRITE"))
def h1c(m):
    """A stage-5 build that failed is followed by a source fix (or a passing build) before any other verification
    runs. (The build stage 1 recorded, or stage 5's own when stage 1 had none to record; a test runner written in the
    build field is no build -- swebv100 000034 recorded `runtests.py messages_tests` there.)"""
    w4, w5, obs, repro = m.w.get(4), m.w.get(5), m.obs, m.repro
    if w4 is None or not m.p1:
        return None
    named = (_field(m.p1, "Build & Test Commands", "Build"), _field(m.p5, "Build", "Command"))
    build = next((b for b in named if b and not is_none(b) and EV.test_targets(b) is None and not (repro and EV.runs_script(b, norm_path(repro).rsplit("/", 1)[-1]))), None)
    builds = obs.command_runs(build, after=w4, before=w5) if build else []
    failed_at = next((n for n, cmd, out in builds if EV.exit_code(cmd, out) not in (None, 0)), None)
    if failed_at is None:
        return None
    fixes = [k for p in obs.source_edits for k in obs.edit_steps.get(p, []) if k > failed_at]
    fixed = min(fixes + [n for n, cmd, out in builds if n > failed_at and EV.exit_code(cmd, out) == 0], default=None)
    checks = [n for n, _, _ in obs.tests_in(after=failed_at, before=w5)] + ([n for n, _, _ in obs.ran(repro, after=failed_at, before=w5)] if repro else [])
    return float(not checks or (fixed is not None and fixed < min(checks)))


@method("atom/H4a", materials=("AP", "COLLECT", "TARGET", "TEST", "WRITE"))
def h4a(m):
    """Stage 5 reruns stage 1's test selection: every stage-1 target is covered by a stage-5 one (the same, or a file /
    class / module that holds it) -- a narrower rerun is not comparable to the baseline -- or a test run after stage 4
    covers it, whatever 05 records (a -k selection cannot be compared as a set, so a differing -k in 05 alone decides
    nothing)."""
    if not (m.p1 and m.p5):
        return None
    t1, t5 = EV.test_targets(_field(m.p1, "Build & Test Commands", "Test") or ""), EV.test_targets(_field(m.p5, "Existing Tests vs Baseline", "Command") or "")
    if not (t1 and t5):
        return None
    after4 = m.w.get(4)
    runs5 = [EV.test_targets(cmd) for _, cmd, _ in m.obs.tests_in(after=after4)] if after4 is not None else []
    rerun = any(tt and all(_covers(tt, t) for t in t1) for tt in runs5)
    return float(rerun or all(_covers(t5, t) for t in t1))


@method("atom/H7", materials=("SHELLCLS", "TEST", "WRITE"))
def h7(m):
    """From stage 5 on, no test run on stashed (or reverse-applied) source: that rebuilds the baseline stage 1
    established, which stage 5 must use as recorded. (Before stage 1 closed, a stash to measure the baseline after an
    early edit is stage 1's own baseline; the early edit is D11's concern.)"""
    w4 = m.w.get(4)
    if w4 is None:
        return None
    hidden, rebuilt, ran = False, False, False
    for n, cmd, _ in m.obs.shell:
        if n <= w4:
            continue
        for s in _plain_segments(cmd):
            if _UNSTASH.match(s):
                hidden = False
            elif _STASH.match(s):
                hidden = True
            elif EV.is_test_attempt(s):
                ran = True
                rebuilt |= hidden
    if not ran:
        return None
    return 0.0 if rebuilt else 1.0


@method("atom/H8a", materials=("AP", "COLLECT", "SCRIPT", "EXIT", "EDIT", "WRITE", "PATCH"))
def h8a(m):
    """A failed reproduction is acted on: the source (or the script) changed and it ran again, or the run closed.
    Moving on to the artifact with nothing done is what the rule forbids."""
    repro, w4, obs = m.repro, m.w.get(4), m.obs
    if not (repro and w4 is not None and not m.edits_unseen):
        return None
    runs = obs.ran(repro, after=w4, before=m.w.get(5))
    failing = [n for n, cmd, out in runs if (code := EV.exit_code(cmd, out)) is not None and code != 0]
    if not failing:
        return None
    acted = [n for p in [*obs.source_edits, repro] for n in obs.edit_steps.get(norm_path(p), []) + ([obs.written(repro)] if p == repro and obs.written(repro) else []) if n > failing[-1]]
    later_runs = [n for n, _, _ in runs if n > failing[-1]]
    return float(bool(acted) or bool(later_runs))


@method("atom/H8e", materials=("TEST", "EDIT", "WRITE"))
def h8e(m):
    """No regression left unfixed: a baseline that ran clean is clean after the last edit too."""
    obs = m.obs
    baseline = obs.tests_in(before=obs.first_edit) if obs.first_edit is not None else []
    post = obs.tests_in(after=obs.last_edit, before=m.w.get(5)) if obs.last_edit is not None else []
    if not (baseline and post):
        return None
    clean = all(failures(o) == 0 for _, _, o in baseline)
    return 0.0 if clean and failures(post[-1][2]) > 0 else 1.0


@method("atom/H9a", materials=("EDIT", "TEST", "SCRIPT", "WRITE", "AP", "COLLECT"))
def h9a(m):
    """A stage-5 fix is re-verified: tests or the reproduction script ran after the last one."""
    w4, w5, obs, repro = m.w.get(4), m.w.get(5), m.obs, m.repro
    if w4 is None:
        return None
    fixes = [n for p in obs.source_edits for n in obs.edit_steps.get(p, []) if n > w4 and (w5 is None or n < w5)]
    if not fixes:
        return None
    last = max(fixes)
    rerun = obs.tests_in(after=last, before=w5) or (obs.ran(repro, after=last, before=w5) if repro else [])
    return float(bool(rerun))


@method("atom/H9b", materials=("AP", "EDIT", "NONE", "WRITE"))
def h9b(m):
    """The part of H9b code can read: a stage-5 source edit is recorded under Fixes Applied (05 Step 5 "Record what was
    changed and why"), so `none` there after one is false. Whether each item says what and why is the judge's
    question, asked only when the section is not none. Found by the none-field review (2026-10-28)."""
    if m.w.get(4) is None or m.w.get(5) is None:
        return None
    if _section_none(m.p5, "Fixes Applied"):
        return 0.0 if m.edits5 else 1.0
    return None


@method("atom/H10", materials=("SHELLCLS", "EDIT", "WRITE"))
def h10(m):
    """No endless retry: the same command with the same output three more times with nothing written in between, or a
    run cut off (its last turn a tool call, no finish) after the plan with stage 5 never closed."""
    obs, run = m.obs, m.run
    if not run.steps:
        return None
    written = sorted({n for ns in obs.edit_steps.values() for n in ns} | set(obs.created.values()) | {n for ns in obs.writes.values() for n in ns})
    seen_at: dict[tuple[str, str], int] = {}
    idle: dict[str, int] = {}
    for n, cmd, out in obs.shell:
        if (cmd, out) in seen_at and not any(seen_at[(cmd, out)] < k < n for k in written):
            idle[cmd] = idle.get(cmd, 0) + 1
        seen_at[(cmd, out)] = n
    last = run.steps[-1]
    cut = bool(last.actions) and not any(a.name == "finish" for a in last.actions)
    return 0.0 if max(idle.values(), default=0) >= 3 or (cut and m.w.get(3) is not None and m.w.get(5) is None) else 1.0


@method("atom/H11", materials=("AP", "COLLECT", "NONE", "SCRIPT", "EXIT", "EDIT", "WRITE"))
def h11(m):
    """A reproduction that failed, or requirements left unmet, are outstanding failures (a run that never started --
    "can't open file" -- is no result)."""
    p5, repro, obs = m.p5, m.repro, m.obs
    if not p5:
        return None
    result, unmet = (_field(p5, "Reproduction Script", "Result") or "").lower(), _field(p5, "Reproduction Script", "Unmet requirements")
    last_runs = [r for r in (obs.ran(repro, after=obs.last_edit, before=m.w.get(5)) if repro and obs.last_edit is not None else []) if not EV._NOT_STARTED.search(r[2])]
    failed = result.startswith("fail") or bool(unmet and not is_none(unmet)) or (bool(last_runs) and EV.exit_code(last_runs[-1][1], last_runs[-1][2]) not in (None, 0))
    if failed and (outstanding := _section_none(p5, "Outstanding Failures")) is not None:
        return 0.0 if outstanding else 1.0
    return None


@method("atom/H15a", materials=("AP", "COLLECT"))
def h15a(m):
    """05's Result and Verdict fields take the allowed values."""
    if not m.p5:
        return None
    allowed = {
        ("Build", "Result"): ("success", "failure"),
        ("Reproduction Script", "Result"): ("pass", "fail"),
        ("Existing Tests vs Baseline", "Verdict"): ("unchanged", "regression resolved", "pre-existing failures only"),
    }
    vals = [(v.lower().strip(" .`*"), ok) for (sec, lab), ok in allowed.items() if (v := _field(m.p5, sec, lab))]
    return _frac([v.startswith(ok) for v, ok in vals])


@method("atom/H15b", materials=("AP", "COLLECT", "NONE"))
def h15b(m):
    """The Verdict agrees with Regressions and Pre-existing failures (unchanged from a baseline that may itself have
    failed: only a regression contradicts it)."""
    if not m.p5:
        return None
    verdict = (_field(m.p5, "Existing Tests vs Baseline", "Verdict") or "").lower()
    reg, pre = _field(m.p5, "Existing Tests vs Baseline", "Regressions"), _field(m.p5, "Existing Tests vs Baseline", "Pre-existing failures")
    if not verdict:
        return None
    if verdict.startswith("unchanged"):
        return float(is_none(reg)) if reg else None
    if verdict.startswith("pre-existing"):
        return float(bool(pre) and not is_none(pre) and (not reg or is_none(reg)))
    if verdict.startswith("regression"):
        return float(bool(reg) and not is_none(reg))
    return None


@method("atom/H15c", materials=("AP", "COLLECT", "NONE"))
def h15c(m):
    """Unmet requirements agree with the reproduction Result."""
    if not m.p5:
        return None
    result, unmet = (_field(m.p5, "Reproduction Script", "Result") or "").lower(), _field(m.p5, "Reproduction Script", "Unmet requirements")
    if not (result and unmet):
        return None
    return float(is_none(unmet)) if result.startswith("pass") else float(not is_none(unmet)) if result.startswith("fail") else None


@method("atom/H15d", materials=("AP", "COLLECT", "NONE"))
def h15d(m):
    """Regressions and Pre-existing failures are written "test id -> ..."."""
    if not m.p5:
        return None
    entries = [v for k in ("Regressions", "Pre-existing failures") if (v := _field(m.p5, "Existing Tests vs Baseline", k)) and not is_none(v)]
    return _frac([bool(_ARROW.search(v)) for v in entries])


@method("atom/H17", materials=("EDIT", "TEST", "SCRIPT", "EXIT", "CMDMATCH", "WRITE"))
def h17(m):
    """With nothing failed, stage 5 changes no source (05 "If the build succeeded and both Step 2 and Step 3 passed,
    nothing has failed -- skip to Step 6"): a stage-5 source edit comes after some stage-5 verification failed -- a
    test attempt with failures or a nonzero exit, the reproduction script, the build or any python script exiting
    nonzero or with a traceback (the script's path is unknown when no artifact was collected: step24 000309). Once
    something failed, the fixes that follow are not judged. Found by the independent rule extraction."""
    if m.w.get(4) is None or m.w.get(5) is None:
        return None
    obs, repro, start5 = m.obs, m.repro, m.start5

    def failed_before(n: int) -> bool:
        runs = obs.attempts_in(after=start5, before=n) + (obs.ran(repro, after=start5, before=n) if repro else [])
        runs += [r for r in obs.shell_in(after=start5, before=n) if _PY_SCRIPT.search(r[1])]
        build = _field(m.p1, "Build & Test Commands", "Build") if m.p1 else None
        if build and not is_none(build) and command_core(build):
            runs += obs.command_runs(build, after=start5, before=n)
        return any(failures(out) > 0 or EV.exit_code(cmd, out) not in (None, 0) or "Traceback (most recent call last)" in out for _, cmd, out in runs)

    edits5 = m.edits5
    return 0.0 if edits5 and not failed_before(edits5[0]) else 1.0


# -- S4: stage 4's skeleton -------------------------------------------------------------------------------


@method("atom/S4.tags", materials=("AP", "COLLECT", "NONE"))
def s4_tags(m):
    """Each Changed Files entry tags its requirements ([R1])."""
    if not m.p4:
        return None
    claims = [x.group(2) for x in re.finditer(r"^\s*[-*+]\s*\*{0,2}(Modified|Created)\*{0,2}\s*:\s*(.*)$", m.p4["section_bodies"].get("Changed Files") or "", re.M | re.I)]
    return _frac([bool(re.search(r"\[\s*R\d+", v)) for v in claims if v.strip() and not is_none(v) and not A.PLACEHOLDER.fullmatch(v.strip())])
