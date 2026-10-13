# Changes: speckit_bug  (upstream github/spec-kit@0443760, bug extension 1.0.1)

**1. user argument 삭제** (01-assess.md, 02-fix.md, 03-test.md) — G1-1
- 원문은 사람이 명령 뒤에 입력한 텍스트(`$ARGUMENTS`)로 버그 설명을 받는 구조. rllm에는 입력자가 없어 해당 섹션 삭제.
- 01-assess.md에 "task 메시지의 issue 본문 = 버그 설명" 명시.
- 02·03의 slug 입력 섹션 삭제, 회차 표(8번)로 대체.

**2. 사용자 개입 최소화** (01-assess.md, 02-fix.md, 03-test.md) — G2-1, G2-2
- 01~03.md 마지막의 "사용자에게 보고 및 다음 명령 안내" 지침 삭제. 대신 다음 단계 문서를 읽고 바로 이어서 수행하도록 지시.
- 앞 단계 산출물이 없을 때의 "사용자에게 실행 안내"를 "앞 단계 직접 선수행"으로 변경.

**3. core-workflow 신규 생성** (core-workflow.md, instruction.md, system-prompt.j2, \_\_init\_\_.py) — G3-1
- 원문은 각 단계를 사람이 명령으로 하나씩 실행하는 구조. 한 번의 실행 안에서 자동으로 이어지도록 초기 지침 파일 `core-workflow.md` 신규 작성.
- 내용: 단계 순서, 각 단계 문서 경로, 보고서 작성 규칙.
- instruction.md와 system-prompt.j2에 이 파일을 가장 먼저 읽으라는 지시 반영.
- \_\_init\_\_.py에서 진입 문서로 등록(`entry_doc="core-workflow.md"`).

**4. 질문·중단 분기 삭제** (01-assess.md, 02-fix.md, 03-test.md, core-workflow.md, system-prompt.j2) — G1-2, G4-1~6 — **semantic 포함**
- 원문은 판단이 필요한 지점에서 사람에게 질문하거나 중단하는 구조. rllm에서는 질문 즉시 실행이 종료되므로 해당 분기 전부 삭제.
- `invalid` 판정과 조기 종료 삭제, issue를 반드시 해결할 요구사항으로 명시(01).
- 모호한 부분은 가장 타당한 해석으로 진행하고 그 가정을 보고서에 기록(02).
- 분석 오류 발견 시 중단 없이 기록 후, 수정한 원인 기준으로 계속 진행(02).
- "비용이 크다"는 이유의 테스트 생략 금지(03).
- "질문하지 말고 가정을 기록하고 계속" 지시 추가(core-workflow.md, system-prompt.j2).

**5. 산출물 경로 저장소 밖으로 이동** (01-assess.md, 02-fix.md, 03-test.md, core-workflow.md, \_\_init\_\_.py) — G5-1, G9-2
- 원문의 저장소 안 보고서 경로(`.specify/bugs/<slug>/`)는 patch 혼입과 `git clean` 삭제 위험이 있어 `/tmp/speckit/bugs/issue/`로 이동.
- slug는 `issue`로 고정하고, slug 결정 섹션 삭제(01~03).
- 저장소 밖 수정 금지 규칙에 보고서 디렉터리 예외 추가(02).
- 보고서 디렉터리 규칙 명시(core-workflow.md).
- 지침 문서 업로드 위치 `/speckit/` 지정(\_\_init\_\_.py).

**6. URL fetch 금지** (01-assess.md, core-workflow.md) — G6-1 — **semantic**
- 원문은 issue 안의 github.com 등 링크를 확인 없이 가져오는 구조. 정답 PR 유출 경로이므로 금지하고, 링크는 기록만 하도록 변경.

**7. hook 섹션 삭제** (01-assess.md, 02-fix.md, 03-test.md) — G7-1
- 원문 각 명령 앞뒤의 확장 hook 검사(`.specify/extensions.yml`)는 rllm 환경에 해당 파일이 없어 동작하지 않으므로 삭제(216줄 감소).

**8. fix ↔ test 반복 추가 (최대 3회)** (02-fix.md, 03-test.md, core-workflow.md) — G8-1 — **loop**
- 원문은 test 실패 시 사람에게 재분석을 권고하고 종료하는 구조.
- test 결과가 실패나 부분 성공이면 fix로 돌아가 재수행하도록 변경, 최대 3회.
- 회차별 보고서: `fix.md`/`test.md` → `fix-2.md`/`test-2.md` → `fix-3.md`/`test-3.md`.

**9. 테스트 추가 대신 검증 스크립트(checks) 작성** (01-assess.md, 02-fix.md, 03-test.md, core-workflow.md) — G9-1 — **semantic**
- 원문의 저장소 테스트 추가 지시가 SWE-Gym task의 테스트 파일 수정 금지와 충돌.
- 재현·검증 스크립트는 `/tmp/speckit/bugs/issue/checks/`에 작성하고, 저장소 테스트는 실행만 하도록 변경.

**원문 없이 새로 쓴 문서**: `docs/core-workflow.md`, `instruction.md`, `system-prompt.j2`의 `<PROBLEM_SOLVING_WORKFLOW>` 섹션.
