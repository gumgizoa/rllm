# aidlc_v5 — aidlc_v4 대비 변경 내역

- 패키지 기준 (2026-11-17 교체): **aidlc_v4_eval** (평가용 verifier) 에 아래 문서 변경을 얹은 것.
  처음 만들 때(60ddc546)는 학습용 aidlc_v4 의 채점기(milestone-1 rubric)를 복사했음. 문서·instruction·system prompt 는
  그대로이므로 에이전트가 보는 것은 같음 (`SPEC.fingerprint` = 11-08~09 평가 3런이 기록한 값). 채점기만 바뀜 → 아래 "채점기" 절
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
| 9 | legacy/rubric/facts.py, score.py (11-17 전 reward/rubric/) | diff 에 테스트 파일이 있으면 hygiene −8 | 기존 테스트 줄이 바뀌거나 삭제된 경우에만 −8 (`diff_test_files_modified`) | — | 규칙 1 과 채점기를 맞춤 |

## 채점기 (2026-11-17, aidlc_v4_eval 기반으로 교체)

- `reward/`: `aidlc_v4_eval/reward` 를 복사해 v5 문서로 옮김. check kind 이름공간 `aidlc_v4_eval.*` → `aidlc_v5.*`, `aidlc_v4_eval` 을 import 하지 않음.
  `ruleset.yaml` 은 v5 문서 줄에 맞춤 (바뀐 줄 27개 삭제, 새 줄 54개 배정, 나머지는 `ruleset.py sync` 로 번호만 이동). 헤드라인은 `aidlc/score`
- `legacy/`: `aidlc_v4_eval/legacy` 에 60ddc546 의 v5 채점기 수정(위 9번)을 얹은 것. `aidlc/compliance`·`aidlc/rubric` 을 함께 냄.
  `legacy/rubric/` 은 60ddc546 의 `aidlc_v5/reward/rubric/` 과 바이트 단위로 같음 (`tests/test_aidlc_v5.py` 가 해시로 고정)
- 판정 검증: `tests/test_aidlc_v5.py`. aidlc_v4_eval 의 정직 런 2개를 v5 양식으로 옮긴 런이 모든 판정 1.0. 코드 판정마다 깨는 케이스와 지키는 케이스가 있음 (aidlc_v4_eval 케이스 재사용 + v5 케이스)

- 규모: 문서 줄 389 → 원자 규칙 219 → method 210 → 판정 242 (aidlc_v4_eval: 362 → 195 → 190 → 222)
- 회귀 확인 (2026-11-17): aidlc_v4_eval snapshot 의 aidlc_v4 런 600개 (swebv100 100 + step24 500, judge 끔) 를 이 채점기로 다시 채점해 셀 단위로 대조.
  다른 셀은 아래 의도한 변경뿐: B5b@3·4·5 (분모), S4.testcheck@4·S5.final_tests@5 (필드 이름; v4 산출물엔 없음 → 0), F7 15런 (새 테스트 모듈 create 허용), H7 5런 (baseline 선택 밖 stash 실행 허용).
  v5 가 안 바꾼 판정은 600런 모두 같음
- 평가 3런 재채점 (judge 끔, `rescore_compliance.py --workflow aidlc_v5`): `aidlc/score` 0.826 / 0.830 / 0.834. 같은 런을 aidlc_v4_eval 로 채점하면 0.837 / 0.841 / 0.846.
  `aidlc/compliance` (legacy) 0.866 / 0.870 / 0.870. 평가 당시 live 채점기가 episode 에 저장한 값은 0.831 / 0.835 / 0.836 으로 다름:
  legacy/compliance.py 가 테스트 실행·단계 band 를 reward/read.py 로 읽기 때문 (aidlc_v4_eval/legacy 와 aidlc_v4 의 차이와 같음)

### rubric 변경 (aidlc_v4_eval 대비)

| id | 처리 | 내용 |
|---|---|---|
| D13 | 판정 교체 | `rule/r_tests_untouched` → `rule/r_test_lines_kept`: patch 가 테스트 파일의 기존 줄을 지우거나 바꾸면, 또는 trajectory 편집이 기존 줄을 바꿨으면(되돌려도) 0. 추가만 하면 1 |
| S4.testcheck | 판정 교체 | 필드 `Test files modified` → `Existing test lines modified or removed`. `check/e4_tests_untouched` → `check/e4_test_lines_kept` |
| H14 | 판정 교체 | `check/e5_test_files_none` → `check/e5_test_lines_none` (05 Final Change 의 `Existing test lines modified or removed: none` 을 같은 기준으로 대조) |
| S5.final_tests | 판정 교체 | 필드 `Test files in the change` → `Test files with additions`. `check/e5_test_additions` 추가 (적은 목록 = patch 의 테스트 파일) |
| F7 | 판정 변경 | 테스트 파일을 대상으로 하는 step 은 03 Added Test 모듈이거나 (create) 일 때만 허용 |
| H7 | 판정 변경 | stash 후 테스트 실행이 baseline 선택(01 Test) 밖 모듈이면 허용 (v5 05 Step 4 가 시키는 분류). 01 Test 가 없으면 예전처럼 모두 위반 |
| H5b (`check/c15_preexisting_subset`) | 판정 변경 | 01 Failing 에 없는 Pre-existing 항목도 5단계 stash 실행에서 실패로 보이면 인정 |
| c45 (`check/c45_final_files`) | 판정 변경 | 04 쪽 파일에 Checks `Test files with additions`·`## Added Test` Module 을 포함 (v5 는 추가한 테스트 모듈을 Changed Files 에 적지 않음) |
| B5d@4 | 판정 변경 | 04 의 모든 `Executed:` 필드가 `no` (Reproduction Script, Added Test) |
| B5b | 분모 변경 | 03·04·05 skeleton 제목에 `Added Test` 추가 |
| D4b | 삭제 | v5 가 "Affected Scope 밖 조사 금지" 줄을 지움. 규칙·`atom/D4b` 삭제 |
| D4c | 제외 사유 변경 | 근거였던 D4b 가 없어져 judge 미질문으로 둠 (예전 judge 에서 56/56 yes) |
| G4b | 판정 삭제 | v5 가 뒤집음 (테스트 추가 허용). `atom/G4b` 삭제, F10·G10·H18·H2 가 대신함 |
| G4a | 문구 변경 | "애플리케이션 소스를 수정하고, 테스트 파일에는 추가만" (제외 유지) |
| D1c | 신설 | 1단계에서 과제 텍스트의 단어로 저장소 전체 검색 (`grep -r` 등, 경로 `.`·`/testbed`·없음) |
| D1e | 신설 | 그 검색이 찾은 소스 파일이 01 Files 나 `Referencing files left out of scope` 에 있음 (비율) |
| S1.leftout | 신설 (form) | 01 `Referencing files left out of scope` |
| F10 | 신설 | 01 Existing Tests 에 테스트 파일이 있으면 03 Added Test 에 Module·Test 를 적음 |
| S3.at_module, S3.at_test | 신설 (form) | 03 Added Test 필드 |
| G10 | 신설 | 03 Added Test 모듈을 04 쓰기 전에 편집했고 patch 에 있음 |
| S4.at_module, S4.at_test, S4.testadds | 신설 (form) | 04 Added Test 필드, Checks `Test files with additions` |
| H4c | 신설 | 바꾼 소스 파일마다, 그 파일 이름을 딴 테스트 모듈(`test_<stem>.py` 등, 런이 본 것)을 04 뒤 테스트 실행이 대상으로 함 (비율). import 로 덮는 모듈은 못 읽음 |
| H5c | 신설 | `Regressions: none` 이면 같은 절 Command·Output 이 있고 마지막 편집 뒤 테스트 실행이 있음 |
| H5d | 신설 | 05 의 두 `Output` 값이 04~05 사이 셸 출력에 그대로 있음 |
| H8h | 신설 | 01 Failing 에 없는 Pre-existing 항목은 5단계 stash 실행에서 실패로 확인됨 |
| H18 | 신설 | patch 의 테스트 파일마다 마지막 편집·04 뒤 테스트 러너 실행이 대상으로 함 |
| S5.routput, S5.output, S5.at_cmd, S5.at_result, S5.final_testlines | 신설 (form) | 05 의 새 필드 |
| B12 | 신설 | 산출물을 셸 명령(heredoc 등)으로 쓰지 않음 |
| C3, G11, G12, S4.at_executed | 신설 (제외) | 다른 판정이 덮음: C1a·B1 / B4b (gold 없이 "가리킨 파일이 고쳐야 했는지"는 못 가림) / G7c / B5d@4 |

## v4 에서 그대로 둔 것 (원본과도 일치)

- 고정 5단계 파이프라인, 단계마다 규칙 파일 하나씩 로딩
- 첫 편집 전 기준선 기록
- "계획은 쓰인 대로 실행" (원본의 FOLLOW PLAN EXACTLY)
- "이전 단계로 돌아가지 않음" 문장 자체 (단, 6번에서 이탈을 정상 경로로 서술)
- 전체 suite 실행 금지
- 사용자 상호작용 없음, 산출물 골격과 frontmatter

## 알려진 공백

- (11-17 해소) 처음 복사한 채점기는 v4 의 채점 필드만 평가했음. 지금 `reward/` 는 v5 의 새 절·필드와 규칙을 판정함 ("채점기" 절). 로그 5.10절의 행동 항목 b1~b4 는 여전히 reward 에 없음
- `system-prompt.j2` 와 `instruction.md` 는 v4 와 바이트 단위로 동일
- 평가 3런 (2026-11-08~09, wf-tcx-step27, w/ 각 499과제; 분석 기록 5.13절, 비교표 `rllm-home/eval_results/m2/v5_eval/wf_drop_analysis/out/compare_v4_v5.md`):
  resolve 53.4% (런별 54.5/51.7/54.1) vs v4 w/ 52.8% (51.9/50.9/55.5) vs w/o 59.9% → 회복 없음 (+0.7pp, p = 0.7).
  규칙이 직접 지시한 행동은 바뀜: 기존 테스트 파일에 추가 1.1 → 63.2%, 새 테스트 파일만 39.9 → 7.0%, Stage 5 `Output:` 기재 0 → 60.5%, `Added Test` 절 91%.
  모델 판단에 맡긴 행동은 그대로: 마지막 편집 후 공식 모듈 재실행 37.6 → 37.4% (w/o 53.0), 계획이 빠뜨린 gold 회복 10.0 → 8.5%, 편집 후 새 파일 열람 43.8 → 43.8%, 테스트 0회 런의 `Regressions: none` 84 → 83%.
  기존 테스트 줄 수정 8.7% 는 새 금지 규칙 위반 (hygiene 감점 대상).
  v5 w/ 에서 기존 모듈에 테스트를 추가한 런도 같은 과제 w/o 보다 6.5pp 낮아, 테스트 위치는 resolve 의 원인이 아니라 표지였음.
  결론: 문서 규칙은 직접 지시한 행동만 바꾸며 resolve 하락의 세 요인은 문서로 해소되지 않음. 남은 수단은 reward (b1 판별력 있는 재현, b2 수정 모듈 테스트 재실행) 와 하네스
- 학습 워크플로우 3종 (speckit_bug, openspec_ff, agentos_v2) 의 테스트 파일 규칙은 2026-11-07 에 같은 방식으로 수정함 (금지는 세 곳 모두 원본이 아닌 우리 편집이었음). 채점의 `prohibited_action` 은 `test_file_modify` (기존 줄 삭제가 있는 쓰기) 로 정렬. 수정본으로의 평가는 아직 없음
