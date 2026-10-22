"""LLM judge: the atomic rules no code can decide -- whether an artifact's content is right for the issue.

One call per stage artifact, the stage's questions together (``QUESTIONS``). Each question is phrased so
that "yes" keeps the rule, and is answered yes / no / n/a with a verbatim quote from the material given;
code checks the quote:

    yes -> 1, no -> 0, n/a -> None
    a quote the material does not contain, a missing or malformed answer -> None (``aidlc/judge_void``)

Emitted as ``aidlc/judge/<rule>`` (``categories.JUDGE_KINDS`` places them by kind x stage), with
``aidlc/judge_void`` (the share of yes/no answers dropped for their quote) and ``aidlc/judge_calls``.
A question whose subject the artifact lacks (no deviations, no pre-existing failures, no test file the run
read) is not asked. The judge sees the issue, the artifacts and the extracts named per stage, never the
trajectory: it judges what the run wrote, and code judges what the run did.

Configured by environment, for an OpenAI-compatible endpoint (a vLLM server); with no model configured
there are no judge signals:

    AIDLC_JUDGE_BASE_URL     e.g. http://localhost:8000/v1
    AIDLC_JUDGE_MODEL        the served model name
    AIDLC_JUDGE_API_KEY      default "EMPTY"
    AIDLC_JUDGE_TEMPERATURE  default 0
    AIDLC_JUDGE_EXTRA_BODY   JSON merged into the request (e.g. {"chat_template_kwargs": {"enable_thinking": false}})
    AIDLC_JUDGE_CACHE        a directory: responses cached by request, so a rescoring asks once
    AIDLC_JUDGE_TIMEOUT      seconds, default 300
    AIDLC_JUDGE_SEED         a sampling seed (with a temperature above 0, a second sample for the flip rate)
    AIDLC_JUDGE_JSON         "0" to not ask for JSON mode (``response_format``), for a server without it
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ._claims import Observed, claimed_paths, is_none, norm_path, same_file, task_text
from ._claims import field_value as claims_field_value
from .content_checks import _section_none
from .rubric import artifacts as A
from .rubric import facts as F

log = logging.getLogger(__name__)

MAX_CHARS = 12_000  # per piece of material; what is cut is not shown, so a quote from it cannot verify
MIN_QUOTE = 8

# stage -> [(rule, question)]; "yes" keeps the rule
QUESTIONS: dict[int, list[tuple[str, str]]] = {
    1: [
        ("D1a", "Does Affected Scope `Files` list the source file(s) that implement the behaviour the issue describes (not only tests or unrelated files)?"),
        ("D1b", "If the issue names a file or a symbol directly, does `Files` start from it: the named file, or the file that defines the named symbol? Answer n/a if the issue names neither."),
        ("D3", "Is `Owning module` the module or package the listed Files belong to, and does any boundary it states agree with those Files?"),
        (
            "D6",
            "Is the `Build` entry right for this language and repository: a build or type-check command where the language needs one,"
            " or 'not applicable' (or an import / compile check) for an interpreted package?",
        ),
        ("D10b", "Does the Existing Tests `Contract` state what the shown test code actually checks (signatures, return values, raised errors)?"),
    ],
    2: [
        ("E1a", "Do the requirements keep the expected behaviour, names, signatures and paths exactly as the issue states them (no different expected behaviour, no renamed interface)?"),
        ("E1b", "Where the issue already specifies a behaviour or an interface, do the requirements take it as given rather than re-deriving it or proposing an alternative?"),
        ("E3b", "Can every requirement be checked by running a reproduction script or an existing test (each one describes observable behaviour, not intent or code style)?"),
        ("E6a", "Does Functional Requirements state the behaviour that must be observable once the issue is resolved?"),
        ("E6b", "Does Functional Requirements also state existing behaviour that must keep working, such as the contract of the existing tests recorded in artifact 01?"),
        ("E7a", "Is every Non-Functional requirement a constraint on how the code works (complexity, memory, performance, compatibility) rather than a functional behaviour?"),
        ("E7b", "Is every Non-Functional requirement something the issue itself states?"),
        ("E8a", "Do the Edge Cases cover the boundary, empty, invalid or out-of-range inputs that matter for this issue?"),
        ("E8b", "Do the Edge Cases state an error path: what is raised or handled, and what the caller observes? Answer n/a only if the changed behaviour has no failure mode at all."),
        ("E9", "Is each Assumption a decision taken in place of asking a question, given with its reason?"),
    ],
    3: [
        ("F2d", "Does every step's Contract name the signatures or return shapes that must be preserved, and any new interface the step introduces?"),
        ("F2e", "Does every step's Verification say what the reproduction script will check for that step?"),
        ("F4a", "Is the reproduction script planned so that it shows the issue before the fix and passes after it?"),
        ("F9a", "Can each step be carried out as written, without interpretation: a concrete target and a concrete change?"),
    ],
    4: [
        ("G5", "Does the patch keep the signatures and return shapes the plan's Contracts say are preserved? Answer n/a if no Contract preserves anything."),
        ("G8a", "Does each item under Deviations from Plan say what changed from the plan and why?"),
        ("G8c", "Does each structural invalidation name the step it invalidates, the reason, and what replaces it?"),
        ("B4b", "Where artifact 04 or the patch departs from the plan (artifact 03), is the difference recorded under Deviations from Plan? Answer yes if nothing departs from the plan."),
    ],
    5: [
        ("H3a", "Does the reproduction script check the behaviour each Functional requirement describes?"),
        ("H3b", "Does the reproduction script check the conditions the Edge Cases describe?"),
        ("H3c", "Does the reproduction script check the Non-Functional constraints?"),
        ("H8d", "Does each pre-existing failure listed give a reason, and is the reason plausible (the failure is unrelated to the change and was there at the baseline in artifact 01)?"),
        ("H9b", "Does each item under Fixes Applied say what was changed and why?"),
    ],
}

SYSTEM = (
    "You review the artifacts an autonomous coding agent wrote while resolving a software issue in a fixed five-stage"
    " workflow. You answer questions about whether an artifact's content is right, using only the material given.\n\n"
    'For each question answer "yes", "no" or "n/a" ("n/a" only where the question allows it). Give a quote: text copied'
    ' character for character from the material (at most 200 characters) that the answer rests on. For "no", quote the'
    " text that falls short, or the heading of the section that lacks what is asked. Do not quote the question. Add a"
    " one-sentence reason.\n\n"
    'Reply with JSON only: {"answers": [{"id": "<question id>", "answer": "yes|no|n/a", "quote": "...", "reason": "..."}]}'
)


def configured() -> bool:
    return bool(os.environ.get("AIDLC_JUDGE_MODEL") and os.environ.get("AIDLC_JUDGE_BASE_URL"))


# --- material ----------------------------------------------------------------------------------


def _cut(text: str, limit: int = MAX_CHARS) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "\n[... cut ...]"


def _field(p, section, label):
    return claims_field_value((p or {}).get("section_bodies", {}).get(section) or "", label) or None


def _repro_text(run, parsed: dict, patch: str | None) -> str | None:
    """The reproduction script's final text: rebuilt from the run's writes, or its added lines in the patch."""
    paths = [p for st in (4, 3) if parsed.get(st) for p in claimed_paths(_field(parsed[st], "Reproduction Script", "Path"))]
    for p in paths:
        # Its last text written, by any path naming it (the artifacts may give it relative, or by name only).
        # A later rm is the cleanup the workflow asks for, so the text before it is the script that ran.
        text = None
        for step in run.steps:
            for a in step.actions:
                if a.status == "fail":
                    continue
                if a.kind == "create" and a.path and same_file(norm_path(a.path), p):
                    text = a.text or ""
                elif a.kind in ("replace", "insert") and a.path and same_file(norm_path(a.path), p) and text is not None:
                    text = F._apply_edit(text, a)
                elif a.kind == "shell" and not F._rm_matches(a.command or "", p):
                    for t in F.write_targets(a):
                        if same_file(norm_path(t), p) and (body := A.shell_written_body(a.command or "", t)) is not None:
                            text = body
        if text:
            return text
        for block in re.split(r"(?m)^diff --git ", patch or ""):
            head = block.split("\n", 1)[0]
            if same_file(head.split(" b/")[-1], p) and "new file mode" in block:
                return "\n".join(line[1:] for line in block.splitlines() if line.startswith("+") and not line.startswith("+++"))
    return None


def _test_text(run, parsed: dict) -> str | None:
    """What the run saw of the existing tests artifact 01 names: its views and cat / sed reads of them."""
    p1 = parsed.get(1)
    paths = claimed_paths(_field(p1, "Existing Tests", "Path")) if p1 else []
    seen = []
    for step in run.steps:
        for a in step.actions:
            if a.kind == "view" and any(same_file(norm_path(a.path or ""), t) for t in paths):
                seen.append(a.observation)
            elif a.kind == "shell" and re.match(r"\s*(?:cd\s+\S+\s*&&\s*)?(?:cat|sed\s+-n|head|nl)\b", a.command or "") and any(norm_path(t).rsplit("/", 1)[-1] in (a.command or "") for t in paths):
                seen.append(a.observation)
    text = "\n".join(s for s in seen if s)
    return text or None


def stage_requests(run, parsed: dict, patch: str | None, task) -> dict[int, tuple[list[tuple[str, str]], dict[str, str]]]:
    """stage -> (the questions to ask, the material shown), for the stages whose artifact exists."""
    issue = task_text(task) if task is not None else ""
    body = {k: (parsed.get(k) or {}).get("body") for k in range(1, 6)}
    out = {}
    for st, questions in QUESTIONS.items():
        if not body[st]:
            continue
        material = {"ISSUE": issue} if st in (1, 2, 3) and issue else {}
        material |= {f"ARTIFACT 0{k}": body[k] for k in {1: [1], 2: [1, 2], 3: [2, 3], 4: [3, 4], 5: [1, 2, 5]}[st] if body[k]}
        skip = set()
        if st == 1:
            tests = _test_text(run, parsed)
            if tests:
                material["EXISTING TEST CODE THE AGENT READ"] = tests
            else:
                skip.add("D10b")
        if st == 2 or st == 5:
            nfr = (parsed.get(2) or {}).get("section_bodies", {}).get("Non-Functional Requirements")
            if nfr is None or _section_none(parsed.get(2), "Non-Functional Requirements") or all(is_none(v) for v in re.findall(r"R\d+\*{0,2}\s*:\s*(.*)", nfr)):
                skip |= {"E7a", "E7b", "H3c"}
        if st == 2 and _section_none(parsed.get(2), "Assumptions"):
            skip.add("E9")
        if st == 4:
            if patch:
                material["FINAL PATCH"] = patch
            else:
                skip |= {"G5", "B4b"}
            dev = (parsed.get(4) or {}).get("section_bodies", {}).get("Deviations from Plan")
            if dev is None or _section_none(parsed.get(4), "Deviations from Plan"):
                skip |= {"G8a", "G8c"}
            elif not re.search(r"structural invalidation", dev, re.I):
                skip.add("G8c")
        if st == 5:
            script = _repro_text(run, parsed, patch)
            if script:
                material["REPRODUCTION SCRIPT"] = script
            else:
                skip |= {"H3a", "H3b", "H3c"}
            pre = _field(parsed.get(5), "Existing Tests vs Baseline", "Pre-existing failures")
            if not pre or is_none(pre):
                skip.add("H8d")
            if _section_none(parsed.get(5), "Fixes Applied") in (None, True):
                skip.add("H9b")
        asked = [(r, q) for r, q in questions if r not in skip]
        if asked:
            out[st] = (asked, {k: _cut(v) for k, v in material.items()})
    return out


def prompt(stage: int, questions: list[tuple[str, str]], material: dict[str, str]) -> str:
    shown = "\n\n".join(f"=== {name} ===\n{text}" for name, text in material.items())
    asked = "\n".join(f"- {rule}: {q}" for rule, q in questions)
    return f"The material below is the stage {stage} artifact and what it is judged against.\n\n{shown}\n\n=== QUESTIONS (answer every id) ===\n{asked}"


# --- asking and checking -------------------------------------------------------------------------


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("`", "").replace("*", "")).strip().lower()


_TRIPLE = re.compile(r'"id"\s*:\s*"(\w+)"\s*,\s*"answer"\s*:\s*"(yes|no|n/a)"\s*,\s*"quote"\s*:\s*"((?:[^"\\]|\\.)*)"', re.I)


def verdicts(reply: str, questions: list[tuple[str, str]], material: dict[str, str]) -> tuple[dict[str, float | None], int, int]:
    """rule -> 1 / 0 / None from a reply, and (yes/no answers, those dropped for their quote)."""
    m = re.search(r"\{.*\}", reply or "", re.S)
    try:
        answers = json.loads(m.group(0)).get("answers", []) if m else []
    except (json.JSONDecodeError, AttributeError):
        # A reply broken further on (an unquoted reason) still holds well-formed id / answer / quote triples.
        answers = [{"id": i, "answer": a, "quote": json.loads(f'"{q}"')} for i, a, q in _TRIPLE.findall(reply or "")]
    shown = _norm("\n".join(material.values()))
    by_id = {str(a.get("id", "")).strip(): a for a in answers if isinstance(a, dict)}
    out, decided, void = {}, 0, 0
    for rule, _ in questions:
        a = by_id.get(rule) or {}
        answer = str(a.get("answer", "")).strip().lower()
        if answer not in ("yes", "no"):
            out[rule] = None
            continue
        decided += 1
        quote = _norm(str(a.get("quote", "")))
        if len(quote) < MIN_QUOTE or quote not in shown:
            out[rule] = None
            void += 1
        else:
            out[rule] = 1.0 if answer == "yes" else 0.0
    return out, decided, void


def ask(text: str, seed: int | None = None) -> str:
    import httpx

    body = {
        "model": os.environ["AIDLC_JUDGE_MODEL"],
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}],
        "temperature": float(os.environ.get("AIDLC_JUDGE_TEMPERATURE", "0")),
        **({"response_format": {"type": "json_object"}} if os.environ.get("AIDLC_JUDGE_JSON", "1") != "0" else {}),
        **json.loads(os.environ.get("AIDLC_JUDGE_EXTRA_BODY") or "{}"),
    }
    if seed is not None:
        body["seed"] = seed
    cache = os.environ.get("AIDLC_JUDGE_CACHE")
    path = Path(cache) / (hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() + ".json") if cache else None
    if path is not None and path.exists():
        return json.loads(path.read_text())["content"]
    url = os.environ["AIDLC_JUDGE_BASE_URL"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {os.environ.get('AIDLC_JUDGE_API_KEY', 'EMPTY')}"}
    r = httpx.post(url, json=body, headers=headers, timeout=float(os.environ.get("AIDLC_JUDGE_TIMEOUT", "300")))
    r.raise_for_status()
    content = r.json()["choices"][0]["message"].get("content") or ""
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"content": content}))
    return content


def judge_checks(run, obs: Observed, parsed: dict, patch: str | None, task, seed: int | None = None) -> dict[str, float]:
    """``aidlc/judge/<rule>``, ``aidlc/judge_void`` and ``aidlc/judge_calls``; {} when no judge is configured."""
    if not configured():
        return {}
    if seed is None and os.environ.get("AIDLC_JUDGE_SEED"):
        seed = int(os.environ["AIDLC_JUDGE_SEED"])
    requests = stage_requests(run, parsed, patch, task)
    if not requests:
        return {}

    def one(st):
        questions, material = requests[st]
        try:
            return st, verdicts(ask(prompt(st, questions, material), seed), questions, material)
        except Exception as e:  # a failed call leaves the stage unjudged, never a wrong verdict
            log.warning("aidlc judge: stage %s failed: %s", st, e)
            return st, ({r: None for r, _ in questions}, 0, 0)

    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        results = dict(pool.map(one, requests))
    out: dict[str, float] = {}
    decided = void = 0
    for st, (values, d, v) in sorted(results.items()):
        decided, void = decided + d, void + v
        out |= {f"aidlc/judge/{rule}": value for rule, value in values.items() if value is not None}
    out["aidlc/judge_calls"] = float(len(requests))
    if decided:
        out["aidlc/judge_void"] = void / decided
    return out
