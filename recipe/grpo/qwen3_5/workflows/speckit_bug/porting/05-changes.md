# Changes: speckit_bug  (upstream github/spec-kit@0443760, bug extension 1.0.1)

## 구성 (`recipe/grpo/qwen3_5/workflows/speckit_bug/`)

| 파일 | 출처 | 내용 |
|---|---|---|
| `docs/core-workflow.md` | 직접 작성 | 진입 문서: 단계 순서, fix ↔ test 최대 3회, 입력 정의, 보고서 규칙 |
| `docs/stages/01-assess.md`, `02-fix.md`, `03-test.md` | spec-kit 원문을 변환 | 단계별 절차와 보고서 양식 (원문 634줄 → 319줄) |
| `build.py` | 직접 작성 | 원문 → stages 변환기(공용 엔진 `workflows/_port.py` 사용). 고친 곳마다 태그(env / loop / semantic). `--list`, `--check` |
| `instruction.md` | 직접 작성 | "`/speckit/core-workflow.md`부터 열고 단계마다 stage 문서를 연다". aidlc_v4와 다른 문장 |
| `system-prompt.j2` | SDK 기본 프롬프트 복사 | 절차 섹션만 새로 작성(aidlc_v4와 다른 문장), 나머지 15개 섹션 동일 |
| `__init__.py`, `LICENSE-spec-kit` | — | SPEC 등록 정보(문서 `/speckit`, 산출물 `/tmp/speckit`), MIT 고지 |
| `porting/03·05·06-*.md` | 단계별 기록 | 결정·변경·smoke (staged 절차 이전 이식이라 01·02 없음) |

## agent 행동 변화

| # | 단계 | upstream 원래 행동 | 지금 행동 | 바꾼 이유 | 원문으로 되돌리면 |
|---|---|---|---|---|---|
| 1 | assess | issue에 URL이 있으면 URL Trust Policy에 따라 **페이지를 가져와** 제목·본문·stack trace 추출 | **원래 행동 삭제**: 링크를 열지 않고 issue 본문만 읽음, 링크는 `[UNVERIFIED — not fetched]`로 기록 | 정답 PR 유출 경로 (G6-1) | 불가 (정답 유출) |
| 2 | assess | 판정에 **`invalid`/not a bug**(오용, 정상 동작, 중복, 범위 밖)가 있고, 이해 불가 보고는 즉시 중단 | **원래 행동 삭제**: `invalid` 판정·조기 종료 없음, issue는 반드시 충족할 요구사항, 판정은 `valid` / `likely valid, needs reproduction` 둘 | SWE task는 항상 고칠 대상이 있음 (G1-2) | 가능하지만 "버그 아님" 종료 = 미해결 |
| 3 | assess | 계획에 "추가·수정할 테스트" 기재 | 계획에 "실행할 check" 기재: `checks/` 재현 스크립트 + 실행할 기존 저장소 테스트, 테스트 파일 추가·수정은 계획하지 않음 | SWE task의 테스트 수정 금지와 충돌 (G9-1) | 가능하지만 테스트 파일 수정 위험 |
| 4 | fix | 회귀를 막을 **저장소 테스트 추가·수정** | **새 행동 유도**: check 스크립트를 `checks/`에 작성, 저장소 테스트 파일은 건드리지 않음, 보고서 섹션 "Tests Added" → "Checks Added" | G9-1 | 가능하지만 patch 오염 위험 |
| 5 | fix | assessment가 틀렸음을 발견하면 **코드 수정 중단**, 기록 후 assess 재실행 권고 | 기록 후 바로잡은 원인 기준으로 수정 계속, assess 재수행·`assessment.md` 수정 없음 | 권고를 실행할 사람 없음 (G4-4) | 불가. 대안: assess 재수행 |
| 6 | test | 파괴적·네트워크·**비용이 큰** check는 동의 없이 건너뜀 | 파괴적·네트워크 check만 건너뜀, **변경한 모듈의 저장소 테스트 실행은 기본으로 기대** | "비용" 사유로 테스트 전부 생략 가능 (G4-5) | 가능하지만 검증 생략 증가 |
| 7 | test → fix | 실패 시 Reopen·Hold 판정, "assess 재실행" 또는 "staging 확인 필요" 권고 후 종료 | **새 행동 추가**: `partial`·`failed`면 fix로 복귀, 다음 회차는 이전 fix·test 보고서를 증거로 읽음, 최대 3회차, 회차별 보고서(`fix-2.md`, `test-2.md` …) | 판단할 사람 없음 (G8-1) | 가능 (반복 없이 종료) |
| 8 | fix | check는 코드 수정과 나란히 작성, 수정 전에 돌리는 단계 없음 | **새 행동 추가**: 코드 수정 전에 issue 예제를 원문 그대로 옮긴 check와 재현 check를 쓰고 **실패하는지 확인**(통과하면 다시 작성), 변경할 파일의 기존 테스트를 돌려 기준선 기록, 수정 전·후 결과를 fix 보고서에 기록 | 판별력 없는 check 33%, 자기 이해만으로 쓴 check (G9-5) | 가능 (check 품질 저하) |
| 9 | test | `verified` = 중요한 check 통과, 증상 재현 안 됨 | `verified`는 세 조건 모두 충족할 때만: 수정 전 실패한 check가 지금 통과, issue 예제가 기대대로 동작, 기준선 대비 새 실패 없음. 하나라도 실패하면 `failed`, 못 돌렸으면 `partial` | 자기 판정이 정답과 무관(`verified` 정답률 63% ≈ 기저율) (G8-2) | 가능 (루프 발동 거의 없음) |

- 7번 발동 빈도(SWE-bench Verified 499, think on, `swebv499_speckitbug_262k-150_think_t1`): 2회차 진입 7/499. 1회차 `verified` 393건 중 145건이 실제 미해결, agent 자기 판정이 정답 여부를 거의 반영하지 못함.

**표에서 뺀 것**: `$ARGUMENTS` → issue 본문, slug `issue` 고정과 보고서 경로 `/tmp/speckit/bugs/issue/`, 다음 명령 안내 → 다음 단계 문서 연결과 앞 단계 직접 선수행, `[NEEDS CLARIFICATION]` → "가장 타당한 해석 + 기록" 단순 대체(G4-3), 덮어쓰기 확인 → 보고서 1회 작성, hook 검사 삭제, 동의 요구 문구 삭제.

## 변경

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

**10. 수정 전 check 실패 확인·기준선, 판정 기준 변경** (02-fix.md, 03-test.md) — G9-5, G8-2 — **semantic** (2026-10-15)
- 원문은 check(원문은 테스트)를 코드 수정과 함께 작성하고, test 단계가 "중요한 check 통과"로 판정하는 구조. 측정(SWE-bench Verified 499): `verified` 정답률 63%로 기저율과 같음, check의 33%가 수정 전에도 통과, 자기 check가 수정 후에도 실패하는데 `verified` 46건.
- fix 2단계 앞부분에 "코드 수정 전" 항목 추가: issue 예제를 원문 그대로 옮긴 check와 재현 check 작성, 현재 코드에서 실패 확인(통과하면 다시 작성), 변경할 파일의 기존 테스트 실행 결과를 기준선으로 기록. 2·3회차는 1회차 기준선 유지.
- fix 보고서 양식: Checks Added를 check별 수정 전·후 결과 표로, "Baseline: Existing Tests" 섹션 추가.
- test 판정: `verified`는 수정 전 실패한 check 통과 + issue 예제 기대대로 + 기준선 대비 새 실패 없음일 때만, 하나라도 실패하면 `failed`, 못 돌렸으면 `partial`.

**원문 없이 새로 쓴 문서**: `docs/core-workflow.md`, `instruction.md`, `system-prompt.j2`의 `<PROBLEM_SOLVING_WORKFLOW>` 섹션.
