"""The scoring methods: one registered function per judgment the code decides, with the materials it reads.

    @method("atom/H9b", materials=("AP", "EDIT", "NONE", "WRITE"))
    def h9b(m: Measures) -> float | None:
        ...

A method's key is its rubric items' id without the stage (``form/B1``, ``check/e1_scope_viewed``). A method held
per stage is registered with ``stages`` and called as ``fn(m, stage)``; its measurements are ``<key>@<stage>``
(``form/B1@1`` .. ``@5``), the rubric's item ids. A function returns 1 (kept) / 0 (broken) / a share / None
(nothing bears on it); it reads the run only through :class:`~..measures.Measures`, whose readings are computed
on first use and shared.

    form.py       form/*   an artifact's form: present, frontmatter, headings, each skeleton field
    procedure.py  proc/*   a stage's procedure: its document read first, alone, before its artifact
    claim.py      check/*  an artifact's claim held to the trajectory (evidence, temporal, consistency)
    rule.py       rule/*   what the run did against a stated rule, whatever its artifacts claim
    atom.py       atom/*   the remaining atomic rules, one function each, in rule id order
    run.py        run/*    whole-run readings: entry, a real test run, the diff's disclosure
    judge.py      judge/*  the judge's questions (declared here; asked by ``reward/judge.py``)

``MATERIALS`` names what a method can rest on; ``ruleset.py check`` requires every method the rule set places
to be registered here, and ``ruleset.md`` shows each one's materials.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

MATERIALS: dict[str, str] = {
    "COLLECT": "산출물 수집 (수집본만 인정)",
    "TEST": "테스트 실행 인식·출력의 통과/실패 수",
    "SCRIPT": "재현 스크립트 실행 인식",
    "EXIT": "exit code",
    "PATCH": "최종 변경 파일 (patch)",
    "EDIT": "trajectory의 편집 파일·시점",
    "NONE": "none 값",
    "TESTFILE": "테스트 파일 판별",
    "PATH": "경로 추출·비교",
    "AP": "산출물 section·field·step parser",
    "DOC": "문서 읽기 시점",
    "WRITE": "산출물 쓰기 시점",
    "TARGET": "test id·target 추출",
    "CMDMATCH": "기록한 명령과 실행 명령 대조",
    "SEEN": "파일 열람 여부",
    "SHELLCLS": "그 밖의 명령 분류 (설치, 조회, stash, 반복)",
    "ISSUE": "이슈 본문 추출",
    "FINAL": "마지막 응답",
    "JUDGE": "LLM judge (이슈·산출물·단계별 발췌만 봄, trajectory는 안 봄)",
    "MSG": "agent 메시지 (마지막 응답 앞의 것까지)",
}

STAGES = (1, 2, 3, 4, 5)


@dataclass(frozen=True)
class Method:
    key: str
    fn: Callable | None  # None: a judge question, asked by reward/judge.py
    materials: tuple[str, ...]
    stages: tuple[int, ...] | None = None
    family: str | None = None  # claims: evidence / temporal / consistency
    timed_by_edits: bool = False  # claims placed against the first or last source edit

    def keys(self) -> list[str]:
        return [self.key] if self.stages is None else [f"{self.key}@{s}" for s in self.stages]


METHODS: dict[str, Method] = {}


def _add(m: Method) -> None:
    if m.key in METHODS:
        raise RuntimeError(f"method {m.key!r} registered twice")
    unknown = [x for x in m.materials if x not in MATERIALS]
    if unknown:
        raise RuntimeError(f"method {m.key!r}: unknown materials {unknown}")
    METHODS[m.key] = m


def method(key: str, *, materials: tuple[str, ...], stages: tuple[int, ...] | None = None, family: str | None = None, timed_by_edits: bool = False):
    def deco(fn: Callable) -> Callable:
        _add(Method(key, fn, tuple(materials), tuple(stages) if stages is not None else None, family, timed_by_edits))
        return fn

    return deco


def question(rule: str, materials: tuple[str, ...]) -> None:
    """Declare the judge question ``rule`` (``judge/<rule>``) and what the judge is shown for it."""
    _add(Method(f"judge/{rule}", None, tuple(materials)))


def load() -> dict[str, Method]:
    """Every method, registered by importing the modules that define them."""
    from . import atom, claim, form, judge, procedure, rule, run  # noqa: F401  (registration side effects)

    return METHODS


def measurements() -> dict[str, tuple[Method, int | None]]:
    """Measurement key (an item id) -> its method and stage, for every method the code computes."""
    out: dict[str, tuple[Method, int | None]] = {}
    for m in load().values():
        if m.fn is None:
            continue
        for st in m.stages or (None,):
            out[m.key if st is None else f"{m.key}@{st}"] = (m, st)
    return out
