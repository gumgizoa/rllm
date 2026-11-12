# aidlc_v5 — aidlc_v4 대비 변경 내역

- 모든 변경의 근거: AI-DLC v4 를 추론 시 붙이면 SWE-bench Verified resolve 가 떨어지는 원인 분석
  (`2026-2_DFM/04-03-02. workflow resolve 하락 원인 분석 - 가설 검증 기록.md` 4.1 · 5.10 · 5.11 · 5.12절)
- 방침: 원본 AWS AI-DLC (`aidlc-workflows/aidlc-rules/`) 유지.
  v4 가 원본을 뒤집은 규칙은 원본 쪽으로 되돌리고, v4 가 추가한 규칙은 완화함.
  v4 가 원본에서 그대로 가져온 규칙은 하나도 바꾸지 않음

## 변경표

| # | 위치 | v4 | v5 | 원본 AI-DLC | 근거 |
|---|---|---|---|---|---|
| 1 | core "Modification Boundaries"; 01 Step 3 주석; 03 Code Location Rules·완료 기준; 04 Step 2 MANDATORY·Checks·완료 기준; 05 Step 5·Final Change·Step 7·완료 기준 | 테스트 파일 수정 전면 금지. 새 동작은 재현 스크립트로만 검증 | 테스트 파일은 **추가만 허용**. 기존 테스트 모듈에 새 테스트 함수 추가 또는 새 모듈 생성 가능. 기존 줄의 수정·삭제는 금지. 산출물에 `Test files with additions` 와 `Existing test lines modified or removed: none` 기재 | 금지 없음. Code Generation 이 단위 테스트를 계획·생성하고, brownfield 는 기존 파일을 제자리에서 수정 | w/o 런은 기존 테스트 모듈에 테스트를 추가함 (25~33%). 그 런들은 같은 과제의 w/ 런보다 resolve 가 4~9pp 높음. v4 는 이 비율을 1~8% (wf-tcx 1.1%) 로 떨어뜨리고 테스트를 새 파일로 밀어내며, 새 파일 런은 w/o 보다 낮음. v4 변경 중 원본을 뒤집은 유일한 규칙 |
| 2 | 03 Step 2·골격; 04 Step 2·골격; 05 Step 2·골격 | — | **Added Test**: 덮는 기존 테스트 모듈에 새 테스트 함수를 계획·작성하고, Stage 5 에서 테스트 러너로 실행 (스크립트로 직접 실행하지 않음) | 단위 테스트를 유닛마다 생성하고 Build & Test 에서 실행 | 테스트 파일을 쓰고도 테스트 러너를 한 번도 안 돌린 런의 resolve 48~52%, 같은 과제 w/o 53~61% |
| 3 | 05 Step 3; Step 4 표; 골격 Command; core Stage 5 2항 | 기준선과 **같은 선택**만 재실행. 전체 suite 금지 | 기준선 선택 **+ 수정한 모든 파일을 덮는 테스트 모듈** 재실행. 기준선 밖 모듈의 실패는 수정 전 소스(`git stash`)에서 먼저 돌려 분류. 전체 suite 금지는 유지 | 기준선 개념 없음. "모든 단위 테스트 실행 … 통과할 때까지 반복" | v4 아래서 마지막 편집 후 공식 모듈 재실행 53% → 38%. 재실행한 런은 w/o 와의 차이가 5~10pp 좁음 |
| 4 | 05 골격 (Output 필드)·Outstanding Failures 뒤 주석 | `Regressions: none` 은 자유 기입 | 실행마다 **Command 와 Output** (러너 요약 줄 그대로) 기록. 실행 기록 없는 `Regressions: none` 은 무효 | 요약에 Total / Passed / Failed 수치 기재 | wf-tcx w/ 런 중 테스트 러너 0회인데 "회귀 없음"을 적은 비율 89% |
| 5 | 01 Step 1·골격·완료 기준; core Stage 1 2항 | 범위 = 이슈가 가리키는 파일 + 직접 호출자·피호출자. "그 너머는 조사하지 말 것" | 과제가 말하는 심볼·오류 문자열을 **저장소 전체에서 검색**해 참조 파일을 모두 나열. 제외한 파일은 이유와 함께 기재 | 저장소 전체 조사, 모든 소스 파일의 "Existing Files Inventory" | 계획이 gold 파일을 놓친 런은 같은 과제 w/o 보다 8~15pp 낮음. 다중 파일 과제는 8~18pp 손실 |
| 6 | 04 "When the Plan Proves Wrong"; core "No stage returns" 뒤 | 계획대로 실행, 이탈은 기록 | 동일 + 이탈은 계획을 고치는 **정상 경로**. 코드·오류·테스트가 가리키는 파일은 열어 확인하고, 필요하면 변경에 추가 | 계획은 그대로 따르되 사용자가 단계마다 변경 요청 가능, 오류 처리에서 이전 단계 복귀 | v4 아래서 편집 후 새 파일 열람 58% → 44%, 빠뜨린 gold 회복률은 ≈10% 그대로 |
| 7 | core "Execution Context" | — | **런은 Stage 5 뒤에만 끝남**. 단계 경계의 진행 보고는 종료가 아님 | 단계마다 완료 메시지 후 승인 대기 | base 모델이 "Stage 1 complete, proceeding" 을 finish 로 보낸 런 6 → 20 |
| 8 | core "Artifact Rules" | "한 번의 쓰기로 전체 내용" | 동일 + **파일 편집 도구로 작성, 셸 heredoc 금지** | IDE 파일 도구 전제 | 편집 전 깨진 tool call 84건 중 12건이 tool call 안의 `cat > … <<EOF` 산출물 작성 |
| 9 | reward/rubric/facts.py, score.py | diff 에 테스트 파일이 있으면 hygiene −8 | 기존 테스트 줄이 바뀌거나 삭제된 경우에만 −8 (`diff_test_files_modified`) | — | 규칙 1 과 채점기를 맞춤 |

## v4 에서 그대로 둔 것 (원본과도 일치)

- 고정 5단계 파이프라인, 단계마다 규칙 파일 하나씩 로딩
- 첫 편집 전 기준선 기록
- "계획은 쓰인 대로 실행" (원본의 FOLLOW PLAN EXACTLY)
- "이전 단계로 돌아가지 않음" 문장 자체 (단, 6번에서 이탈을 정상 경로로 서술)
- 전체 suite 실행 금지
- 사용자 상호작용 없음, 산출물 골격과 frontmatter

## 알려진 공백

- 복사한 채점기는 v4 의 채점 필드만 평가함. 새 절·필드 (`## Added Test`, `Output:`, `Referencing files left out of scope`) 는 미지 항목으로 파싱만 되고 compliance 점수에 반영되지 않음. 이 항목들과 로그 5.10절의 행동 항목 b1~b4 는 아직 구현되지 않음
- `system-prompt.j2` 와 `instruction.md` 는 v4 와 바이트 단위로 동일
- 평가 3런 (2026-11-08~09, wf-tcx-step27, w/ 각 499과제; 분석 기록 5.13절, 비교표 `rllm-home/eval_results/m2/v5_eval/wf_drop_analysis/out/compare_v4_v5.md`):
  resolve 53.4% (런별 54.5/51.7/54.1) vs v4 w/ 52.8% (51.9/50.9/55.5) vs w/o 59.9% → 회복 없음 (+0.7pp, p = 0.7).
  규칙이 직접 지시한 행동은 바뀜: 기존 테스트 파일에 추가 1.1 → 63.2%, 새 테스트 파일만 39.9 → 7.0%, Stage 5 `Output:` 기재 0 → 60.5%, `Added Test` 절 91%.
  모델 판단에 맡긴 행동은 그대로: 마지막 편집 후 공식 모듈 재실행 37.6 → 37.4% (w/o 53.0), 계획이 빠뜨린 gold 회복 10.0 → 8.5%, 편집 후 새 파일 열람 43.8 → 43.8%, 테스트 0회 런의 `Regressions: none` 84 → 83%.
  기존 테스트 줄 수정 8.7% 는 새 금지 규칙 위반 (hygiene 감점 대상).
  v5 w/ 에서 기존 모듈에 테스트를 추가한 런도 같은 과제 w/o 보다 6.5pp 낮아, 테스트 위치는 resolve 의 원인이 아니라 표지였음.
  결론: 문서 규칙은 직접 지시한 행동만 바꾸며 resolve 하락의 세 요인은 문서로 해소되지 않음. 남은 수단은 reward (b1 판별력 있는 재현, b2 수정 모듈 테스트 재실행) 와 하네스
- 학습 워크플로우 3종 (speckit_bug, openspec_ff, agentos_v2) 의 테스트 파일 규칙은 2026-11-07 에 같은 방식으로 수정함 (금지는 세 곳 모두 원본이 아닌 우리 편집이었음). 채점의 `prohibited_action` 은 `test_file_modify` (기존 줄 삭제가 있는 쓰기) 로 정렬. 수정본으로의 평가는 아직 없음
