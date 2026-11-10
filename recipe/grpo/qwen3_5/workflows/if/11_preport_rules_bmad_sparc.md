# 11. 포팅 전 규칙 인벤토리: BMAD build-auto와 SPARC 1.0 run의 템플릿 분류

> 작성: 2026-11-04
> 입력: `workflows/bmad_build_auto/porting/{rules.yaml,01b-rules.md}`, `workflows/sparc_run/porting/{rules.yaml,01b-rules.md}` (port-workflow 1단계 조사 뒤, 2단계 gap 감사 앞에 만든 규칙 목록). 스키마: `.claude/skills/port-workflow/references/rules-schema.md`
> 학습 열(AOS/OSF/SKB/AID)은 01 문서 2절 표를 그대로 옮겼다(구현된 채점 항목 수). BMAD/SPARC 열은 **규칙 수**이고 괄호 안은 그중 port 후 남을 것으로 추정되며 code/judge로 잴 수 있는 수다(enforced·none·drop 제외). 단위가 다르므로 열 사이의 크기 비교는 하지 말 것.

## 0. 요약

- BMAD build-auto: 규칙 280개(15개 파일 1,045줄). 범주 {'P': 104, 'R': 22, 'F': 76, 'Q': 42, 'A': 13, 'E': 16, 'C': 7}. 판정 {'code': 211, 'enforced': 4, 'none': 12, 'judge': 53}. port 운명 추정 {'drop': 84, 'env': 27, 'keep': 104, 'semantic': 65}. 층 후보 {'L1': 163, None: 18, 'L2F': 63, 'L2M': 24, 'L1C': 12}.
- SPARC run: 규칙 72개(산문 18개 파일 + 코드 5개 파일; 54개가 코드를 인용, 9개는 코드에만 있음). 범주 {'Q': 5, 'P': 17, 'F': 20, 'A': 6, 'C': 13, 'E': 4, 'R': 7}. 판정 {'judge': 5, 'enforced': 42, 'code': 24, 'none': 1}. port 운명 추정 {'semantic': 8, 'keep': 50, 'env': 9, 'drop': 5}. 층 후보 {None: 5, 'L1': 47, 'L2M': 7, 'L2F': 11, 'L1C': 2}.
- 두 upstream 모두 기존 카탈로그 41개 템플릿으로 규칙의 대부분이 덮인다. 새 템플릿 후보는 BMAD 5개(judge 축 1개 포함), SPARC 6개다.
- SPARC의 T-TR1b(키별 대응) 7개는 전부 CLI gate가 **코드로 강제**한다. 평가 항목으로는 천장이다. 09 문서가 찾던 L2-먼 템플릿이 여기 있지만, 포팅에서 CLI 강제를 유지하면 잴 수 없고 문서로만 재표현하면 잴 수 있다. 3단계 결정이 IF 연구의 k에 직접 걸린다.
- BMAD는 규칙의 30%(84개)가 port에서 빠질 것으로 추정된다(서브에이전트 38, 입력 모드 23, 렌더러·훅 18). 남는 196개 중 code 판정 가능한 템플릿은 T-FM2 26, T-OR2 13, T-FM3 11, T-RD4 10이 상위다.

## 1. 기술 × 템플릿 분포

| 기술 | 템플릿 | 내용 | BMAD | SPARC | AOS | OSF | SKB | AID | 분포 |
|---|---|---|---|---|---|---|---|---|---|
| S1 | T-RD1 | read the core document first | 1 (1) | — | 1 | 1 | 1 | 1 | 학습·평가 공통 |
| S1 | T-RD2 | read a stage's document when the stage starts | 8 (8) | 1 (1) | 4 | 5 | 7 | 5* | 학습·평가 공통 |
| S1 | T-RD3 | do not read a later stage's document early | 3 (3) | — | (order) | (order) | (order) | 5* | 학습·평가 공통 |
| S1 | T-RD4 | read an earlier artifact or a recorded input inside a window | 18 (10) | — | 6 | 5 | 6 | 1 | 학습·평가 공통 |
| S1 | T-RD5 | read specific repository files | 5 (4) | — | 7 | — | — | — | 학습 고유 |
| S2 | NEW-S2-carried-revision | a value returned by the previous tool call is carried into the next mutating call (compare-and-set revision) | — | 1 (0) | — | — | — | — | **새 후보** |
| S2 | NEW-S2-idempotency-key | one fresh key per distinct mutating request; a key reused only with an identical request | — | 1 (0) | — | — | — | — | **새 후보** |
| S2 | T-OR1 | chain of stage-document reads and artifact writes in order | 8 (6) | 4 (2) | 1 | 1 | 3 | 1 | 학습·평가 공통 |
| S2 | T-OR2 | branch on a result | 27 (13) | 5 (3) | — | 1 | 1 | — | 학습 고유 |
| S2 | T-OR3 | never return to an earlier stage (no earlier stage document read again once a later one was) | 1 (0) | — | — | — | — | — | **BMAD/SPARC 고유** |
| S3 | NEW-AW-subagent | a delegation call (subagent launch) required or forbidden inside a window, with its launch parameters | 17 (4) | — | — | — | — | — | **새 후보** |
| S3 | NEW-S3-command-format | a CLI command is invoked with the documented option set and value types | — | 1 (0) | — | — | — | — | **새 후보** |
| S3 | T-AW1 | no repository edit outside the allowed stage | 2 (2) | 1 (1) | 4 | 4 | 7 | 1 | 학습·평가 공통 |
| S3 | T-AW3 | run tests/checks after the last source edit | 3 (3) | 1 (1) | 1 | 1 | 10 | 4 | 학습·평가 공통 |
| S3 | T-AW5 | run (or not) a CLI command inside a window | 5 (2) | 4 (3) | — | 22 | — | — | 학습 고유 |
| S4 | T-PR1 | no test file added or modified | 1 (1) | 1 (0) | 1 | 1 | 1 | 1 | 학습·평가 공통 |
| S4 | T-PR2 | no working file left in the repository | 1 (0) | — | 2 | 2 | 2 | 1 | 학습·평가 공통 |
| S4 | T-PR5 | no full test suite run | 1 (1) | — | 1 | — | — | 1 | 학습 일부·평가 |
| S4 | T-PR6 | a specific command is prohibited | 3 (1) | 2 (1) | — | 1 | — | — | 학습 고유 |
| S5 | NEW-WD-exists-after | check an artifact exists after writing it | 4 (3) | — | — | — | — | — | **새 후보** |
| S5 | NEW-WD-exists-before | check whether a file exists before writing it | 2 (0) | — | — | — | — | — | **새 후보** |
| S5 | NEW-WD-revert | after a decision the working tree is restored to the baseline (the attempt is saved elsewhere) | 2 (0) | — | — | — | — | — | **새 후보** |
| S5 | T-WD2 | do not rewrite an earlier stage's artifact | — | 1 (0) | — | — | (order) | 4 | 학습 일부·평가 |
| S5 | T-WD3 | write artifacts and scripts only at designated locations | 3 (2) | 1 (1) | 6 | 5 | 1 | — | 학습 고유 |
| S5 | T-WD4 | do not edit a finished file (checkbox exception) | 4 (3) | 1 (0) | 4 | — | 3 | — | 학습 고유 |
| S6 | NEW-S6-attested-record | a recorded result carries a signature from a configured verifier over the exact run-bound subject | — | 1 (0) | — | — | — | — | **새 후보** |
| S6 | T-RF1 | a recorded command/result/test equals what was run or read | 6 (6) | 3 (3) | 6 | 1 | 24 | 9 | 학습·평가 공통 |
| S6 | T-RF2 | a recorded 'none/no' claim is not refuted by the run | 2 (2) | 2 (2) | — | — | — | 4 | AI-DLC 고유 |
| S6 | T-RF3 | the recorded list of changed files against the files actually changed | 2 (1) | 1 (1) | — | — | 3 | 5 | 학습 일부·평가 |
| S6 | T-RF4 | recorded paths exist in the base repository | 2 (2) | — | 2 | — | — | 9 | 학습 일부·평가 |
| S8 | NEW-S8-intra-keyed | keyed 1:1 mapping between two sections of one artifact | — | 1 (0) | — | — | — | — | **새 후보** |
| S8 | NEW-S8-intra-set | set relation between two sections of one artifact (cited ⊆ declared) | — | 2 (0) | — | — | — | — | **새 후보** |
| S8 | T-TR1 | ID coverage between artifacts (set relation) | 3 (3) | 3 (0) | — | — | — | 7 | AI-DLC 고유 |
| S8 | T-TR1b | keyed per-element mapping between artifacts | 1 (1) | 7 (0) | — | — | — | — | **BMAD/SPARC 고유** |
| S8 | T-TR2 | the planned or recorded target is what was executed (plan adherence) | 1 (1) | — | — | — | — | 3 | AI-DLC 고유 |
| S9 | T-SR2 | do not ask the user: no question file, no request for input | 2 (2) | 1 (0) | — | — | — | — | **BMAD/SPARC 고유** |
| S10 | NEW-CQ | code hygiene judged on the final diff (comments | — | 1 (1) | — | — | — | — | **새 후보** |
| S10 | NEW-FM-internal | artifact-internal consistency — a field equals a value derived from other parts of the same artifact | 6 (6) | — | — | — | — | — | **새 후보** |
| S10 | NEW-FM-language | artifact (or message) language equals the configured language | 2 (2) | — | — | — | — | — | **새 후보** |
| S10 | T-FM1 | artifact exists at its path | 8 (5) | 2 (1) | 12 | 6 | 7 | 10 | 학습·평가 공통 |
| S10 | T-FM2 | skeleton: headings, labels, fields present and filled, allowed values | 33 (28) | 10 (0) | 49 | 26 | 117 | 82 | 학습·평가 공통 |
| S10 | T-FM3 | repeated-item format (numbering, count, uniqueness) | 13 (11) | 3 (0) | 27 | 19 | 82 | 16 | 학습·평가 공통 |
| S10 | T-FM4 | no template placeholder residue | 3 (2) | 1 (1) | 10 | 14 | 14 | 5 | 학습·평가 공통 |
| S10 | T-FM5 | frontmatter keys fixed | 2 (2) | — | — | — | — | 5 | AI-DLC 고유 |
| S10 | T-FM6 | every block of a repeated structure has its fields | 9 (9) | 4 (0) | — | — | — | 4 | AI-DLC 고유 |
| S10 | T-FM7 | heading set within an allowed list | 2 (1) | — | 2 | — | — | — | 학습 고유 |
| S10 | T-FM8 | domain format rules (OpenSpec delta and spec grammar | 2 (2) | — | 4 | 21 | 1 | — | 학습 고유 |
| J | NEW-J-content | content judged by an LLM judge over the artifact and the issue/diff (outside S1-S10) | 44 (41) | — | — | — | — | — | **새 후보** |
| — | null | 체크 불가 또는 judge 전용 | 18 (0) | 5 (4) | — | — | — | — |  |

## 2. 새 템플릿 후보

| 후보 | 기술 | 출처 | 비교 대상 | 가장 가까운 기존 템플릿과 차이 |
|---|---|---|---|---|
| NEW-J-content | J | BMAD | content judged by an LLM judge over the artifact and the issue/diff (outside S1-S10) | none in the catalogue; 10_handover 2.5 keeps judge items outside S1-S10 and reports them on a separate axis (J); defined here so every judge-checkable rule carries a template id |
| NEW-AW-subagent | S3 | BMAD | a delegation call (subagent launch) required or forbidden inside a window, with its launch parameters | T-AW5 (run a CLI command inside a window); differs in the compared object (a child-agent call with a prescribed prompt, not a shell command) and in the parameters judged (one message, blocking, prompt verbatim) |
| NEW-FM-internal | S10 | BMAD | artifact-internal consistency — a field equals a value derived from other parts of the same artifact | T-FM3 (count against a fixed number) and T-RF1 (record against the run); differs because both sides are inside the artifact (09 named it '산출물 내부 일관성') |
| NEW-FM-language | S10 | BMAD | artifact (or message) language equals the configured language | T-FM2 (allowed values of a field); differs because it is a property of the whole text, not of a field |
| NEW-WD-revert | S5 | BMAD | after a decision the working tree is restored to the baseline (the attempt is saved elsewhere) | T-AW1 (no repository edit outside the allowed stage); differs because it compares an end state with the baseline rather than forbidding edit events |
| NEW-S8-intra-set | S8 | SPARC | set relation between two sections of one artifact (cited ⊆ declared) | T-TR1 (set relation between artifacts). Differs in the object compared: both sides are inside one artifact, and the elements may be literal strings (invariant sentences), not ids. 10_handover §2.3 lists '산출물 내부 일관성' as a template 09 needed |
| NEW-S8-intra-keyed | S8 | SPARC | keyed 1:1 mapping between two sections of one artifact | T-TR1b (keyed mapping between artifacts); same difference as NEW-S8-intra-set vs T-TR1 (inside one artifact) |
| NEW-S6-attested-record | S6 | SPARC | a recorded result carries a signature from a configured verifier over the exact run-bound subject | T-RF1 (recorded result equals what was run). Differs in what fidelity is checked against: not the trace but a second party's signature bound to the run; the trace is never consulted |
| NEW-S2-carried-revision | S2 | SPARC | a value returned by the previous tool call is carried into the next mutating call (compare-and-set revision) | T-PG2 (re-run the tool after ticking) and T-TR2 (plan adherence) touch 'use the tool's output', but neither compares an argument value with a previous output. T-RF1 compares a record with the trace, not two calls |
| NEW-S2-idempotency-key | S2 | SPARC | one fresh key per distinct mutating request; a key reused only with an identical request | NEW-S2-carried-revision (same protocol family) but keyed uniqueness rather than carried equality; T-FM3 uniqueness is artifact-internal, not across calls |
| NEW-S3-command-format | S3 | SPARC | a CLI command is invoked with the documented option set and value types | T-AW5 (run a CLI command inside a window) judges presence/absence of a command, not its argument form; 10_handover §2.3 lists '명령 형식' among the templates 09 needed |

## 3. 학습과 반대 방향 (L1C 후보)

**BMAD (12개, 세 갈래)**
- intent gap이면 추정하지 않고 `blocked`로 멈춤 (C12, C23, D20, F7, G72, G84c). 학습은 T-SR1을 보상하고(AOS `requirements.answers`, OSF `note.summary`) 문서도 "가장 타당한 해석으로 계속"(SKB CW:38-40, AOS CW:70).
- 매트릭스 엣지 케이스를 단위 테스트할 task를 넣음 (D42; G50 "추가할 테스트 이름"도 같은 방향). 학습 셋 다 테스트 파일 쓰기 금지.
- "N/A"·"None"을 쓰지 말고 절을 지움 (D40). 학습은 none 리터럴을 요구(SKB FX:55/90, AOS IT:279/306).
- 그 밖에 리뷰어 severity 미부여(G16) vs SKB severity 필수; 수정 파일 테스트만 실행(F12) vs AOS verify 전체 스위트; step-01로 돌아가지 않음(C2)은 카탈로그 T-OR3의 사유 그대로.

**SPARC (2개)**
- MCP 서버가 없으면 멈추고 사용자에게 물음 (J1, T-SR2 극성 반대). 학습 문서 셋 다 "묻지 않음".
- 독립 verifier가 없으면 증거 gate를 blocked로 보고 (E9). port에서 drop 또는 "fail 증거 기록 후 Refinement에서 종료"로 semantic.

## 4. SPARC에서 평가기가 잴 수 있는 것 (enforced 42개를 빼고 남는 것)

- 증거의 사실성: `details.command`·`exitCode`가 실제 실행과 일치 (E10, E11, G3, G4, H1; T-RF1/RF2/RF3). SPARC는 명령을 실행하지 않으므로 이것이 유일한 사실성 검사다.
- 저장소 작업 시점: Refinement 밖에서 코드 수정 없음, 마지막 수정 뒤 테스트 (G1, G2; T-AW1/AW3). upstream 원문은 한 줄.
- 강제되지 않는 사슬: status 읽기, gate 뒤 advance, `completed` 도달 (A3, A7a, A9, A12, H2). `completed` 도달이 가장 큰 단일 신호.
- 거부 뒤 회복: gate exit 2, CAS_MISMATCH, IDEMPOTENCY_MISMATCH 뒤 재제출 (A8, F3; 거부 횟수 자체도 신호).
- 자리표시자 잔존(C7), CLI 옵션 형식(F4, NEW-S3-command-format).

## 5. port 결정과의 연결 (2·3단계에서 볼 것)

| 결정 | 걸린 규칙 | IF 연구에 미치는 영향 |
|---|---|---|
| BMAD 리뷰 4개 레이어를 한 agent가 순서대로 수행 vs 삭제 | G 블록 45개(리뷰어 프롬프트) + NEW-AW-subagent 17 | 수행이면 judge 항목 30여 개와 T-OR2 루프가 남고, 삭제면 BMAD는 spec 형식 + 구현 + 검증만 남아 speckit_sdd와 가까워짐 |
| BMAD `blocked` → HALT 유지 vs 가정하고 계속 | T-OR2 27개 중 intent-gap 6개 | HALT 유지면 L1C 6개가 살아남아 충돌 층 k가 늘지만 패치 없는 rollout이 생김 |
| SPARC CLI를 sandbox에 넣음 vs 문서로 재표현 | enforced 42개 | CLI면 T-TR1b 7개·gate 11개가 천장. 문서면 전부 code 판정 항목이 되어 L2-먼 후보 11개가 생김 |
| SPARC verifier 서명 | E 블록 11개, NEW-S6-attested-record | 동봉 signer면 "서명 전 실제 실행"이 T-RF1 인스턴스로 잴 수 있음 |

## 6. 한계

- 템플릿은 판정 로직에 붙는 것이라 여기 배정은 잠정이다. method를 만들 때 `logic` 네 필드로 다시 판정한다.
- `train.relation`은 현재 constraints.yaml 기준이고 1절 표의 학습 열은 01 문서(10월 22일) 기준이라 T-TR1, T-RF2, T-OR1 행이 서로 안 맞는다. 01 표를 현재 constraints로 다시 뽑으면 해결된다.
- BMAD의 content 규칙 44개를 judge 템플릿 하나(NEW-J-content)에 모았다. 10 문서 2.5절대로 S1~S10 밖의 J 축으로 따로 센다.
- 두 서브에이전트가 각자 판단이 갈린 곳을 `01b-rules.md` 8절에 적어 두었다(BMAD 10곳, SPARC 5곳).
