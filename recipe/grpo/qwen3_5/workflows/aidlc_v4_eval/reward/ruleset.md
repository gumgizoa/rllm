# aidlc_v4_eval rule set

Rendered from ruleset.yaml by `reward/ruleset.py sync`; edit the yaml, not this file.
362 document lines -> 195 atomic rules -> 194 methods -> 226 judgments (scored rubric items; 5 more are diagnostics).
A method's category and stages are its items' (`rubric.yaml`); `global` is stage 0.

Materials: `COLLECT` 산출물 수집 (수집본만 인정); `TEST` 테스트 실행 인식·출력의 통과/실패 수; `SCRIPT` 재현 스크립트 실행 인식; `EXIT` exit code; `PATCH` 최종 변경 파일 (patch); `EDIT` trajectory의 편집 파일·시점; `NONE` none 값; `TESTFILE` 테스트 파일 판별; `PATH` 경로 추출·비교; `AP` 산출물 section·field·step parser; `DOC` 문서 읽기 시점; `WRITE` 산출물 쓰기 시점; `TARGET` test id·target 추출; `CMDMATCH` 기록한 명령과 실행 명령 대조; `SEEN` 파일 열람 여부; `SHELLCLS` 그 밖의 명령 분류 (설치, 조회, stash, 반복); `ISSUE` 이슈 본문 추출; `FINAL` 마지막 응답; `JUDGE` LLM judge (이슈·산출물·단계별 발췌만 봄, trajectory는 안 봄); `MSG` agent 메시지 (마지막 응답 앞의 것까지)

| rule | stage | kind | rule text | lines | methods (category: stages; materials) |
|---|---|---|---|---|---|
| A1 | 0 | P | core-workflow.md를 다른 어떤 행동보다 먼저 읽음 | I:3, SP:64 | `run/entry` (P: 0; DOC) |
| A2 | 0 | P | 각 단계의 첫 행동으로 그 단계 규칙 문서를 읽음 | I:4, I:5, SP:65, SP:66, SP:67, CW:11 | `proc/A2` (P: 1 2 3 4 5; DOC WRITE) |
| A3a | 0 | P | 규칙 문서는 한 번에 하나씩 읽음 | SP:68, CW:18 | `proc/A3a` (P: 0; DOC) |
| A3b | 0 | P | 이전 단계를 마치기(산출물) 전에 다음 단계 규칙 문서를 읽지 않음 | SP:69, CW:18 | `proc/A3b` (P: 2 3 4 5; DOC WRITE) |
| A4 | 0 | P | 규칙 문서 경로 탐색 순서를 따름 | CW:13, CW:14, CW:15, CW:16 | none: not applicable (document lookup order) |
| A5 | 0 | P | 이 워크플로우가 다른 절차보다 우선함 (전체 지시) | CW:3 | none: not applicable (an overall instruction) |
| B1 | 0 | F | 각 단계 결과를 채팅이 아닌 파일로 씀 | SP:70, CW:22 | `form/B1` (F: 1 2 3 4 5; AP COLLECT) |
| B2 | 0 | F | 산출물 경로는 /tmp/swe-bench-pro/<규칙 파일명> | CW:24 | none: covered by another rule's items (B1 (the artifact at its fixed path)) |
| B2b | 0 | P | 첫 산출물을 쓰기 전에 /tmp/swe-bench-pro/를 mkdir -p로 만듦 | CW:24 | none: not applicable (an instrumental step: the edit tool makes the directory, and the artifact at its path is B1's) |
| B3a | 0 | P | 산출물은 한 번의 write로 씀 (덧붙이기·같은 단계 안 다시 쓰기 없음) | CW:28 | `rule/r_artifacts_written_once` (F: 0; WRITE, diagnostic)<br>`atom/B3a` (P: 0; WRITE DOC EDIT TEST SCRIPT) |
| B3c | 0 | F | 산출물에 나중에 채울 빈칸·placeholder를 남기지 않음 (전체 내용으로 씀) | CW:28 | none: covered by another rule's items (the field items (a placeholder reads as an empty field) and B5b (a missing section)) |
| B3b | 0 | P | 산출물은 단계 끝에 씀 (다음 단계 문서를 읽기 전) | SP:71, CW:28, CW:40, S4:48 | `proc/B3b` (P: 1 2 3 4; DOC WRITE)<br>note: Completion Criteria met first: each criterion's own timing rule scores it (D11c, G7a, H2, H4b) |
| B4a | 0 | R | 이전 단계 산출물을 다시 쓰지 않음 | CW:29 | `atom/B4a` (R: 0; WRITE DOC EDIT TEST SCRIPT) |
| B4b | 0 | Q | 이전 단계와 모순되면 지금 단계 산출물에 deviation·정정·pre-existing으로 기록 | CW:29, CW:71 | `judge/B4b` (Q: 0; JUDGE ISSUE COLLECT) |
| B5a | 0 | F | frontmatter 키를 skeleton대로 씀 | CW:30, S1:47 | none: covered by another rule's items (B6a (frontmatter keys)) |
| B5b | 0 | F | ## 제목을 skeleton대로 씀 (이름 바꾸기·빠뜨리기 금지) | CW:30, S1:47 | `form/B5b` (F: 1 2 3 4 5; AP COLLECT) |
| B5c | 0 | F | 필드 접두어(- Label:)를 skeleton대로 씀 | CW:30, S1:47 | none: covered by another rule's items (the per-field rules (field prefixes)) |
| B5d | 0 | F | 괄호 안만 채우고 skeleton의 나머지 문장은 그대로 둠 | S1:47 | none: covered by another rule's items (S1.recorded, S4.executed (the skeleton's two fixed sentences)) |
| B6a | 0 | F | frontmatter는 stage, name 두 키만 | CW:31 | `form/B6a` (F: 1 2 3 4 5; AP COLLECT) |
| B6b | 0 | F | frontmatter stage 값이 파일의 단계와 같음 | CW:35 | `atom/B6b` (F: 1 2 3 4 5; AP COLLECT) |
| B6c | 0 | F | frontmatter name 값이 파일의 단계 이름과 같음 | CW:36 | `atom/B6c` (F: 1 2 3 4 5; AP COLLECT) |
| B7 | 5 | Q | 04·05에 언급된 미해결 작업을 모두 Outstanding Failures에 적음 (none으로 포장하지 않음) | CW:40, S5:98 | `judge/B7` (Q: 5; JUDGE ISSUE COLLECT SCRIPT TEST) |
| B7b | 5 | R | Outstanding Failures 밖의 섹션에 미해결 작업을 적지 않음 | CW:40, S5:98 | `judge/B7b` (R: 5; JUDGE ISSUE COLLECT) |
| B8 | 0 | P | 보이는 산출물은 다시 읽지 않고, 내용이 안 보일 때만 복구용으로 읽음 | CW:42, CW:43, S5:11 | `atom/B8` (P: 0; WRITE SHELLCLS) |
| B9 | 0 | C | R id, step 번호, 경로를 바꾸지 않고 그대로 인용함 | CW:42 | none: covered by another rule's items (the reference checks (R ids, steps quoted as written)) |
| B10 | 0 | R | 산출물 외에 설계·보고서 문서를 만들지 않음 | CW:133 | `atom/B10` (R: 0; EDIT) |
| B11 | 0 | F | 단계마다 산출물 파일은 하나만 씀 (산출물 디렉터리에 다섯 산출물 외 문서를 만들지 않음) | CW:133 | `atom/B11` (F: 0; WRITE PATH) |
| C1a | 0 | P | 다섯 단계를 하나도 빠뜨리지 않고 모두 실행함 (단계 선택·깊이 조정 없음) | CW:7 | `proc/C1a` (P: 1 2 3 4 5; DOC WRITE) |
| C1b | 0 | P | 단계를 1→5 순서대로 실행함 (앞 단계 산출물 뒤에 다음 단계 산출물) | CW:7 | `proc/C1b` (P: 2 3 4 5; WRITE) |
| C2 | 0 | P | 이전 단계로 돌아가지 않음 (문제는 드러난 단계에서 처리) | CW:71, S4:34, S5:58 | `atom/C2` (P: 0; DOC WRITE) |
| E10a | 0 | R | 질문 파일을 만들지 않음 | CW:132 | `atom/E10a` (R: 0; EDIT) |
| E10b | 0 | P | 입력을 기다리며 끝내지 않음 (마지막 응답이 질문·승인 요청이 아님) | CW:132 | `atom/E10b` (P: 0; FINAL) |
| E10c | 0 | P | 중간에도 사용자에게 승인을 묻지 않음 | CW:132 | `atom/E10c` (P: 0; MSG) |
| D9 | 0 | R | 의존성 설치·환경 설정을 하지 않음 (계획도 하지 않음) | CW:134, S1:30 | `rule/r_no_env_setup` (R: 0; SHELLCLS) |
| I1 | 0 | R | 정답을 git history에서 가져오지 않음 (task 조건) | task | none: a flag, in no score (leak_history) |
| I2 | 0 | R | 가짜 테스트로 실행을 꾸미지 않음 (task 조건) | task | `run/ran_real_test` (E: 1; TEST) |
| D1a | 1 | Q | 이슈가 가리키는 소스 파일을 찾아 Affected Scope에 적음 | S1:15 | `check/e1_scope_viewed` (A: 1; AP COLLECT PATH SEEN WRITE)<br>note: not a judge question: whether Files is the right source needs the repository; code checks the files were opened (check/e1_scope_viewed) |
| D1b | 1 | P | 이슈가 파일·심볼을 직접 지목하면 거기서 시작함 | S1:15 | `atom/D1b` (Q: 1; AP COLLECT ISSUE PATH SEEN TESTFILE)<br>note: not a judge question: same; code checks the issue's paths are in scope (atom/D1b) |
| D2 | 1 | Q | 직접 연결된 파일(호출자·피호출자)까지 확장함 | S1:16 | none: judge, low priority, not asked (the scope extends to direct callers and callees) |
| D3 | 1 | Q | Owning module이 Files가 속한 모듈·패키지임 | S1:17 | `judge/D3` (Q: 1; JUDGE ISSUE COLLECT SEEN) |
| D3b | 1 | Q | Owning module에 저장소 안의 경계(디렉터리 등)를 적고, 그 경계가 Files를 포함함 | S1:17, S1:57 | `judge/D3b` (Q: 1; JUDGE ISSUE COLLECT) |
| D4a | 1 | Q | 언어·프레임워크를 Files에서 판단해 기록함 | S1:18 | `atom/D4a` (Q: 1; AP COLLECT) |
| D4b | 1 | R | 1단계에서 repo를 넓게 조사하지 않음 | S1:18, S1:21 | `atom/D4b` (R: 1; SHELLCLS WRITE EDIT) |
| D4c | 1 | R | Affected Scope에 이슈와 무관한 패키지·모듈을 나열하지 않음 | S1:21 | `judge/D4c` (R: 1; JUDGE ISSUE COLLECT) |
| D5 | 1 | F | 모든 경로를 repo root부터 전체 경로로 적음 | S1:19, S1:56 | `atom/D5` (F: 1; AP COLLECT PATH SEEN) |
| D5b | 1 | F | 01 Files에 경로를 한 줄에 하나씩 적음 | S1:56 | `atom/D5b` (F: 1; AP COLLECT PATH) |
| D6 | 1 | Q | build·type-check 방법을 정함 (언어가 요구하면) | S1:25 | `check/e1_build_command_run` (A: 1; AP COLLECT NONE CMDMATCH)<br>`judge/D6` (Q: 1; JUDGE ISSUE COLLECT SEEN) |
| D7a | 1 | Q | 테스트를 어떻게 실행하는지 정함 | S1:26 | `check/e1_test_command_run` (A: 1; AP COLLECT CMDMATCH TARGET) |
| D7b | 1 | Q | 테스트 명령이 해당 범위의 테스트를 대상으로 함 (전체 suite 아님) | S1:27, S1:62 | `atom/D7b` (Q: 1; AP COLLECT NONE TARGET) |
| D8 | 1 | E | 출력을 줄이는 옵션(-q, --tb=short)을 씀 | S1:28 | `atom/D8` (E: 1; AP COLLECT) |
| D10a | 1 | E | 해당 범위를 덮는 기존 테스트를 찾음 | S1:34 | `check/e1_test_path_seen` (A: 1; AP COLLECT PATH SEEN)<br>`atom/D10a` (E: 1; SEEN TESTFILE TEST WRITE) |
| D10b | 1 | Q | 기존 테스트가 강제하는 계약(시그니처·반환·예외)을 맞게 파악해 Contract에 적음 | S1:35 | `judge/D10b` (Q: 1; JUDGE ISSUE COLLECT SEEN) |
| D10c | 1 | E | 찾은 기존 테스트 파일을 실제로 엶 | S1:35 | none: covered by another rule's items (D10a (atom/D10a, check/e1_test_path_seen)) |
| D11a | 1 | E | 소스를 고치기 전에 그 테스트를 한 번 실행함 (baseline) | S1:36, S1:77 | `check/t1_baseline_before_edit` (E: 1; TEST EDIT) |
| D11c | 1 | E | baseline 테스트를 실행한 뒤 그 결과를 01에 적음 (실행 전에 쓰지 않음) | S1:37, S1:77 | `check/t1_baseline_before_write` (E: 1; AP COLLECT NONE TEST WRITE) |
| D11b | 1 | P | 1단계 산출물을 소스 수정 전에 씀 | CW:84 | `check/t1_no_edit_before_write` (P: 1; EDIT WRITE) |
| D12a | 1 | A | 01 Baseline에 적은 테스트 이름이 baseline 실행 출력에 있음 | S1:37 | `check/e1_baseline_tests` (A: 1; AP COLLECT TEST EDIT TARGET) |
| D12c | 1 | A | 01 Failing 기록이 baseline 실행 결과와 맞음 (none이면 실패가 없음) | S1:37 | `check/e1_baseline_failing` (A: 1; AP COLLECT NONE TEST EDIT TARGET) |
| D12d | 1 | A | Passing·Failing이 둘 다 none이면 baseline 실행에서 돈 테스트가 없음 | S1:37 | `check/e1_baseline_none` (A: 1; AP COLLECT NONE TEST EDIT) |
| D12e | 1 | A | 01 Passing에 적은 테스트는 baseline 실행에서 실제로 통과함 | S1:69 | `check/e1_baseline_passing` (A: 1; AP COLLECT NONE TEST EDIT) |
| D12b | 1 | F | 테스트를 하나씩 이름으로, 한 줄에 하나씩 적음 | S1:69, S1:70, S1:77 | `atom/D12b` (F: 1; AP COLLECT NONE) |
| S1.files | 1 | F | 01 필드 Files | S1:56 | `form/S1.files` (F: 1; AP COLLECT) |
| S1.module | 1 | F | 01 필드 Owning module | S1:57 | `form/S1.module` (F: 1; AP COLLECT) |
| S1.lang | 1 | F | 01 필드 Language/framework | S1:58 | `form/S1.lang` (F: 1; AP COLLECT) |
| S1.build | 1 | F | 01 필드 Build (없으면 not applicable) | S1:61 | `form/S1.build` (F: 1; AP COLLECT) |
| S1.test | 1 | F | 01 필드 Test | S1:62 | `form/S1.test` (F: 1; AP COLLECT) |
| S1.tpath | 1 | F | 01 필드 Existing Tests의 Path | S1:65 | `form/S1.tpath` (F: 1; AP COLLECT) |
| S1.contract | 1 | F | 01 필드 Existing Tests의 Contract | S1:65 | `form/S1.contract` (F: 1; AP COLLECT) |
| S1.passing | 1 | F | 01 필드 Passing (없으면 none) | S1:69 | `form/S1.passing` (F: 1; AP COLLECT) |
| S1.failing | 1 | F | 01 필드 Failing (없으면 none) | S1:70 | `form/S1.failing` (F: 1; AP COLLECT) |
| S1.recorded | 1 | F | 01 고정 문장 'Recorded before any source file was modified.' | S1:68 | `atom/B5d` (F: 1; AP COLLECT) |
| E1a | 2 | Q | task 설명(기대 동작·이름·시그니처·경로)을 권위로 삼음 | S2:14 | `judge/E1a` (Q: 2; JUDGE ISSUE COLLECT) |
| E1b | 2 | Q | 이슈가 정한 동작·인터페이스를 다시 도출하거나 대안을 내지 않음 | S2:15 | `judge/E1b` (Q: 2; JUDGE ISSUE COLLECT) |
| E1c | 2 | Q | 이슈가 정한 동작을 뜻이 달라지게(바꾸거나 좁히거나 넓혀) 바꿔 쓰지 않음 | S2:15 | `judge/E1c` (Q: 2; JUDGE ISSUE COLLECT) |
| E2 | 2 | C | 1단계 결과를 맥락으로 사용함 | S2:16 | none: judge, low priority, not asked (stage 1's result used as context) |
| E3a | 2 | Q | 요구사항 하나에 문장 하나 | S2:20 | `atom/E3a` (Q: 2; AP COLLECT NONE) |
| E3b | 2 | Q | 요구사항이 재현 스크립트나 기존 테스트로 검증 가능함 (아니면 범위 밖) | S2:20 | `judge/E3b` (Q: 2; JUDGE ISSUE COLLECT) |
| E3c | 2 | F | 요구사항 id를 R1, R2…로 붙임 | S2:20 | `form/E3c` (F: 2; AP COLLECT) |
| E4a | 2 | F | 세 범주를 통틀어 하나의 연속된 번호 | S2:22 | `atom/E4a` (F: 2; AP COLLECT) |
| E4b | 2 | F | 요구사항 id가 중복되지 않음 | S2:22 | `form/E4b` (F: 2; AP COLLECT) |
| E5a | 2 | F | 세 범주(Functional, Non-Functional, Edge Cases & Error Handling) 제목이 모두 있음 | S2:24 | none: covered by another rule's items (B5b@2 and the S2 fields (S2.fr, S2.nfr, S2.edge)) |
| E5b | 2 | Q | 세 범주를 각각 검토함 | S2:24 | none: covered by another rule's items (judge/E6a (Functional), judge/E7a and atom/E7b (Non-Functional), judge/E8a and judge/E8b (Edge Cases)) |
| E6a | 2 | Q | Functional에 해결 후 보여야 할 동작을 적음 | S2:27 | `judge/E6a` (Q: 2; JUDGE ISSUE COLLECT) |
| E6b | 2 | Q | Functional에 계속 유지할 동작(기존 테스트의 계약)을 적음 | S2:28 | `judge/E6b` (Q: 2; JUDGE ISSUE COLLECT) |
| E7a | 2 | Q | Non-Functional은 복잡도·메모리 같은 방식의 제약 | S2:31 | `judge/E7a` (Q: 2; JUDGE ISSUE COLLECT) |
| E7b | 2 | Q | Non-Functional은 task에 적힌 것만, 없으면 none stated | S2:32, S2:55 | `atom/E7b` (Q: 2; AP COLLECT NONE ISSUE)<br>`judge/E7b` (Q: 2; JUDGE ISSUE COLLECT, diagnostic)<br>note: judge/E7b asks the same question as atom/E7b and is a diagnostic |
| E8a | 2 | Q | Edge Cases에 경계값·빈 값·잘못된 입력·타입/범위 한계를 적음 | S2:35 | `judge/E8a` (Q: 2; JUDGE ISSUE COLLECT) |
| E8b | 2 | Q | 오류 경로(무엇이 raise·처리되고 무엇이 관찰되는지)를 적음 | S2:36 | `judge/E8b` (Q: 2; JUDGE ISSUE COLLECT) |
| E8c | 2 | F | Edge Cases 항목은 '조건 -> 기대 동작' 형식 | S2:58, S2:59 | `atom/E8c` (F: 2; AP COLLECT NONE) |
| E9 | 2 | Q | 질문 대신 내린 결정을 가정으로, 이유와 함께 기록함 | CW:132, S2:62 | `judge/E9` (Q: 2; JUDGE ISSUE COLLECT) |
| S2.fr | 2 | F | 02 섹션 Functional Requirements (- Rn: 항목) | S2:51, S2:52 | `form/S2.fr` (F: 2; AP COLLECT) |
| S2.nfr | 2 | F | 02 섹션 Non-Functional Requirements (없으면 none stated) | S2:55 | `form/S2.nfr` (F: 2; AP COLLECT) |
| S2.edge | 2 | F | 02 섹션 Edge Cases & Error Handling | S2:58, S2:59 | `form/S2.edge` (F: 2; AP COLLECT) |
| S2.assume | 2 | F | 02 섹션 Assumptions (없으면 none) | S2:62 | `form/S2.assume` (F: 2; AP COLLECT) |
| F1a | 3 | C | 요구사항마다 step이 하나 이상 있음 | S3:15 | `check/c23_requirements_covered` (C: 3; AP COLLECT NONE) |
| F1b | 3 | F | step 번호가 1부터 순서대로 | S3:15 | `atom/F1b` (F: 3; AP COLLECT) |
| F2a | 3 | F | step Target이 repo root부터 전체 경로 | S3:17, S3:46, S3:52 | `atom/F2a` (F: 3; AP COLLECT PATH SEEN) |
| F2b | 3 | F | step Target에 (modify in place \| create) 표기 | S3:17, S3:46, S3:52 | `atom/F2b` (F: 3; AP COLLECT) |
| F2c | 3 | F | step 제목 형식 '### Step n [satisfies Rx]' | S3:35, S3:45, S3:51 | none: covered by another rule's items (the step parse behind the S3 fields and tags) |
| F2d | 3 | Q | Contract에 보존할 기존 시그니처·반환 형태를 적음 (영향이 없으면 그렇게 적음) | S3:19 | `judge/F2d` (Q: 3; JUDGE ISSUE COLLECT) |
| F2f | 3 | Q | 뒤 step이 쓸 새 인터페이스를 도입하면 그 step의 Contract에 적음 | S3:19 | `judge/F2f` (Q: 3; JUDGE ISSUE COLLECT) |
| F2e | 3 | Q | Verification에 재현 스크립트가 확인할 것을 적음 | S3:20 | `judge/F2e` (Q: 3; JUDGE ISSUE COLLECT) |
| F3 | 3 | Q | task가 지정한 이름·시그니처·경로를 그대로 씀 | S3:19 | `atom/F3` (Q: 3; AP COLLECT ISSUE PATCH SEEN) |
| F4a | 3 | Q | 재현 스크립트가 수정 전에는 문제를 보이고 수정 후에는 정상임을 보이도록 계획 | S3:27 | `judge/F4a` (Q: 3; JUDGE ISSUE COLLECT) |
| F4b | 3 | C | 재현 스크립트에 Edge Cases 요구사항의 조건을 포함함 | S3:28 | `atom/F4b` (C: 3; AP COLLECT NONE) |
| F5 | 3 | C | Requirement Coverage가 2단계의 모든 요구사항을 step에 연결함 | S3:67 | `check/c23_coverage_refs` (A: 3; AP COLLECT) |
| F6 | 3 | Q | step 순서가 도달했을 때 실행 가능한 순서 | S3:91 | `judge/F6` (Q: 3; JUDGE ISSUE COLLECT) |
| F7 | 3 | R | 테스트 파일을 대상으로 하는 step이 없음 | S3:78 | `atom/F7` (R: 3; AP COLLECT PATH TESTFILE) |
| F8a | 3 | R | 있는 파일은 in place 수정으로 계획함 | S3:81 | `atom/F8a` (R: 3; AP COLLECT PATH SEEN WRITE) |
| F8b | 3 | R | 중복 변형 파일(module_new.py)을 계획하지 않음 | S3:82 | `atom/F8b` (R: 3; AP COLLECT PATH) |
| F9a | 3 | Q | 해석 없이 step별로 실행 가능한 plan | S3:73 | `judge/F9a` (Q: 3; JUDGE ISSUE COLLECT) |
| F9b | 3 | Q | 기존 repo 구조를 따름 | S3:76 | `atom/F9b` (Q: 3; AP COLLECT PATH SEEN EDIT) |
| S3.target | 3 | F | 03 step 필드 Target | S3:17, S3:46, S3:52 | `form/S3.target` (F: 3; AP COLLECT) |
| S3.change | 3 | F | 03 step 필드 Change | S3:18, S3:47, S3:53 | `form/S3.change` (F: 3; AP COLLECT) |
| S3.contract | 3 | F | 03 step 필드 Contract | S3:19, S3:48, S3:54 | `form/S3.contract` (F: 3; AP COLLECT) |
| S3.verify | 3 | F | 03 step 필드 Verification | S3:20, S3:49, S3:55 | `form/S3.verify` (F: 3; AP COLLECT) |
| S3.tag | 3 | F | 03 step 요구사항 태그 | S3:21 | `check/c23_tags_exist` (A: 3; AP COLLECT)<br>`form/S3.tag` (F: 3; AP COLLECT) |
| S3.rpath | 3 | F | 03 필드 Reproduction Script Path | S3:29, S3:58 | `form/S3.rpath` (F: 3; AP COLLECT) |
| S3.exercises | 3 | F | 03 필드 Reproduction Script Exercises | S3:59 | `check/c23_exercises_exist` (A: 3; AP COLLECT)<br>`form/S3.exercises` (F: 3; AP COLLECT) |
| S3.coverage | 3 | F | 03 섹션 Requirement Coverage ('- Rn: Step k') | S3:62, S3:63, S3:64, S3:67 | `form/S3.coverage` (F: 3; AP COLLECT) |
| G1a | 4 | C | plan 순서대로 step을 실행함 | S4:16 | `atom/G1a` (C: 4; AP COLLECT PATH EDIT WRITE) |
| G1b | 4 | C | plan의 모든 step을 실행함 | S4:48 | none: covered by another rule's items (G9, G2) |
| G2 | 4 | C | plan에 적힌 경로를 사용함 | S4:21 | `check/c14_scope_changed` (C: 4; AP COLLECT PATH, diagnostic)<br>`check/c34_targets_changed` (C: 4; AP COLLECT PATH)<br>note: check/c14_scope_changed (04 Modified가 01 Affected Scope와 겹침) is a diagnostic: no document line states it |
| G3a | 4 | P | 쓰기 전에 파일이 있는지 확인함 | CW:145, S4:22 | `atom/G3a` (P: 4; EDIT SEEN WRITE SHELLCLS) |
| G3b | 4 | R | 있는 파일은 in place 수정, 중복 변형 파일을 만들지 않음 | CW:146, S4:23 | none: covered by another rule's items (H12, F8b, S4.dupcheck) |
| G3c | 4 | C | plan이 create로 계획한 파일을 새로 만듦 | S4:24 | `atom/G3c` (C: 4; AP COLLECT PATH PATCH EDIT) |
| G4a | 4 | R | 애플리케이션 소스만 수정함 | CW:140, S4:25 | none: covered by another rule's items (D13) |
| G4b | 4 | R | 새 동작은 재현 스크립트로 검증하고 repo에 새 테스트를 추가하지 않음 | CW:142 | `atom/G4b` (R: 4; AP COLLECT PATCH TESTFILE) |
| D13 | 4 | R | 테스트 파일을 수정하지 않음 | CW:141, CW:142, S4:30, S5:53 | `rule/r_tests_untouched` (R: 4; EDIT PATCH TESTFILE) |
| G5 | 4 | C | plan이 보존한다고 적은 계약(시그니처·반환 형태)을 유지함 | CW:152, S4:26 | `judge/G5` (C: 4; JUDGE ISSUE COLLECT PATCH) |
| G6a | 4 | Q | 태그된 요구사항을 충족함 (resolve가 담당) | CW:150, S4:27 | none: not applicable (resolve, the task verifier's) |
| G6b | 4 | Q | 이전에 통과하던 테스트는 계속 통과함 (결과 조건, verifier가 담당) | CW:150 | none: not applicable (the task verifier's tests) |
| G7a | 4 | C | 재현 스크립트를 plan에 적은 경로에 씀 | S4:28, S4:68 | `check/c34_repro_path` (C: 4; AP COLLECT PATH)<br>`check/t4_repro_written_before_write` (A: 4; AP COLLECT PATH EDIT WRITE) |
| G7b | 4 | R | 4단계에서는 재현 스크립트를 실행하지 않음 | S4:28, S4:86 | `rule/r_repro_not_in_stage4` (R: 4; AP COLLECT PATH SCRIPT DOC WRITE) |
| G7c | 4 | R | 4단계에서는 테스트 등으로 수정한 소스를 실행하지 않음 | CW:113, S4:86 | `atom/G7c` (R: 4; DOC WRITE TEST) |
| G8a | 4 | Q | plan과 달라진 것을 무엇이·왜와 함께 기록함 (없으면 none) | S4:34 | `check/c34_deviations_none` (A: 4; AP COLLECT NONE PATH)<br>`judge/G8a` (Q: 4; JUDGE ISSUE COLLECT PATCH) |
| G8b | 4 | F | deviation을 local correction / structural invalidation으로 구분함 | S4:36, S4:37, S4:76 | `atom/G8b` (F: 4; AP COLLECT NONE) |
| G8c | 4 | Q | structural이면 무효가 된 step, 이유, 대체 방법을 적음 | S4:37 | `judge/G8c` (Q: 4; JUDGE ISSUE COLLECT PATCH) |
| G9 | 4 | F | step마다 완료와 충족한 요구사항을 Plan Execution에 기록함 | S4:41, S4:72, S4:73 | `check/c34_plan_execution_steps` (A: 4; AP COLLECT)<br>`form/G9` (F: 4; AP COLLECT) |
| S4.modified | 4 | F | 04 필드 Modified (전체 경로 + 요구사항 태그) | S4:63, S4:64 | `form/S4.modified` (F: 4; AP COLLECT) |
| S4.modified_real | 4 | A | 04 Modified에 적은 파일은 실제로 바뀜 | S4:63, S4:64 | `check/e4_modified` (A: 4; AP COLLECT PATH PATCH) |
| S4.modified_all | 4 | A | 4단계에서 바꾼 파일은 모두 04에 적음 | S4:63, S4:64 | `check/e4_undisclosed` (A: 4; AP COLLECT PATH PATCH)<br>`run/fidelity` (A: 4; AP COLLECT PATH PATCH, diagnostic) |
| S4.created | 4 | F | 04 필드 Created (없으면 none) | S4:65 | `check/e4_created` (A: 4; AP COLLECT PATH EDIT PATCH)<br>`form/S4.created` (F: 4; AP COLLECT) |
| S4.tags | 4 | F | 04 Modified·Created 항목에 전체 경로와 요구사항 태그 | S4:63, S4:64, S4:65 | `atom/S4.tags` (F: 4; AP COLLECT NONE) |
| S4.rpath | 4 | F | 04 필드 Reproduction Script Path | S4:68 | `form/S4.rpath` (F: 4; AP COLLECT) |
| S4.executed | 4 | F | 04 고정값 Executed: no | S4:69 | `atom/B5d` (F: 4; AP COLLECT)<br>`form/S4.executed` (F: 4; AP COLLECT, diagnostic)<br>note: form/S4.executed@4 (the field filled) is a diagnostic: atom/B5d@4 checks the prescribed value |
| S4.deviations | 4 | F | 04 섹션 Deviations from Plan (없으면 none) | S4:76 | `form/S4.deviations` (F: 4; AP COLLECT) |
| S4.dupcheck | 4 | F | 04 Checks 필드 Duplicate files created: none | S4:79 | `check/e4_duplicates_none` (A: 4; AP COLLECT NONE PATCH)<br>`form/S4.dupcheck` (F: 4; AP COLLECT) |
| S4.testcheck | 4 | F | 04 Checks 필드 Test files modified: none | S4:80 | `check/e4_tests_untouched` (A: 4; AP COLLECT NONE PATCH EDIT TESTFILE)<br>`form/S4.testcheck` (F: 4; AP COLLECT) |
| H1a | 5 | C | 1단계에 적은 build 명령을 실행함 | S5:17 | `atom/H1a` (C: 5; AP COLLECT NONE) |
| H1b | 5 | E | build를 실행해 성공을 확인함 | S5:17, S5:18 | `check/e5_build_result` (A: 5; AP COLLECT NONE CMDMATCH EXIT EDIT WRITE)<br>`atom/H1b` (E: 5; AP COLLECT NONE TARGET SHELLCLS CMDMATCH WRITE) |
| H1c | 5 | P | build 실패를 다른 검증보다 먼저 해결함 | S5:22 | `atom/H1c` (P: 5; AP COLLECT NONE TARGET CMDMATCH EXIT EDIT TEST SCRIPT WRITE) |
| H2 | 5 | E | 재현 스크립트를 실행함 (마지막 수정 뒤) | S5:26 | `check/t5_repro_run_after_last_edit` (E: 5; AP COLLECT PATH SCRIPT EDIT WRITE)<br>`check/e5_repro_result` (A: 5; AP COLLECT PATH SCRIPT EXIT EDIT WRITE) |
| H3a | 5 | Q | 재현으로 Functional 요구사항의 동작을 확인함 | S5:27 | `judge/H3a` (Q: 5; JUDGE ISSUE COLLECT SCRIPT TEST) |
| H3b | 5 | Q | 재현으로 Edge Cases 조건을 확인함 | S5:28 | `judge/H3b` (Q: 5; JUDGE ISSUE COLLECT SCRIPT TEST) |
| H3c | 5 | Q | 재현으로 Non-Functional 제약을 확인함 (있으면) | S5:29 | `judge/H3c` (Q: 5; JUDGE ISSUE COLLECT SCRIPT TEST) |
| H4a | 5 | C | baseline과 같은 테스트 선택(1단계 Test 명령)으로 다시 실행함 | S5:11, S5:36, S5:81 | `atom/H4a` (C: 5; AP COLLECT TARGET TEST WRITE) |
| H4b | 5 | E | 기존 커버 테스트를 마지막 수정 뒤 다시 실행함 | S5:35 | `check/t5_regression_after_last_edit` (E: 5; TEST EDIT WRITE)<br>`check/e5_command_run` (A: 5; AP COLLECT CMDMATCH TARGET EDIT) |
| H5a | 5 | A | 05 Regressions·Verdict 기록이 수정 뒤 마지막 테스트 실행과 맞음 (none·unchanged인데 실패가 남지 않음) | S5:37, S5:83 | `check/e5_regressions` (A: 5; AP COLLECT NONE TEST EDIT WRITE) |
| H5b | 5 | C | 05 Pre-existing failures는 01 baseline에서 실패한 테스트만 | S5:37, S5:84 | `check/c15_preexisting_subset` (C: 5; AP COLLECT NONE TARGET) |
| H6 | 5 | R | 전체 테스트 suite를 돌리지 않음 | S5:39 | `rule/r_targeted_tests` (R: 5; TEST TARGET DOC WRITE) |
| H7 | 5 | R | baseline을 다시 만들려고 테스트를 재실행하지 않음 | S5:11 | `atom/H7` (R: 5; SHELLCLS TEST WRITE) |
| H8a | 5 | E | 재현 스크립트가 실패하면 소스를 고침 | S5:47, S5:53 | `atom/H8a` (E: 5; AP COLLECT SCRIPT EXIT EDIT WRITE PATCH) |
| H8b | 5 | C | baseline에서 통과하던 테스트가 실패하면 Pre-existing이 아니라 Regressions에 적음 | S5:48 | `judge/H8b` (C: 5; JUDGE ISSUE COLLECT SCRIPT TEST) |
| H8g | 5 | Q | Regressions 항목마다 무엇이 테스트를 깨뜨렸고 어떻게 해결했는지 적음 | S5:48, S5:83 | `judge/H8g` (Q: 5; JUDGE ISSUE COLLECT) |
| H8c | 5 | R | baseline에서도 실패하던 테스트(pre-existing)는 고치지 않음 | S1:39, S5:49 | none: judge, low priority, not asked (pre-existing failures left unfixed) |
| H8d | 5 | Q | 적은 pre-existing 실패마다 그렇게 판단한 이유를 붙임 | CW:125, S5:49, S5:84 | `judge/H8d` (Q: 5; JUDGE ISSUE COLLECT SCRIPT TEST) |
| H8f | 5 | A | 마지막 실행에서도 실패하는 baseline 실패 테스트를 모두 05 Pre-existing failures에 적음 | CW:125, S5:49, S5:84 | `check/e5_preexisting_listed` (A: 5; AP COLLECT NONE TEST EDIT WRITE) |
| H8e | 5 | E | patch가 만든 regression(baseline에서 통과하던 테스트의 실패)을 고침 | CW:125 | `atom/H8e` (E: 5; TEST EDIT WRITE) |
| H9a | 5 | E | 고친 뒤 영향받은 검증을 다시 실행함 | S5:54 | `atom/H9a` (E: 5; EDIT TEST SCRIPT WRITE AP COLLECT) |
| H9b | 5 | Q | 고친 것을 무엇·왜와 함께 Fixes Applied에 기록함 | S5:55, S5:87 | `judge/H9b` (Q: 5; JUDGE ISSUE COLLECT SCRIPT TEST) |
| H10 | 0 | P | 무한 재시도하지 않음 (진전이 없으면 멈춤) | CW:135, S5:56 | `atom/H10` (P: 0; SHELLCLS EDIT WRITE) |
| H11 | 5 | Q | 남은 실패를 Outstanding Failures에 사실대로 적음 (none으로 포장하지 않음) | S5:90, S5:98 | `check/e5_outstanding_none` (A: 5; AP COLLECT NONE TEST EDIT WRITE)<br>`atom/H11` (Q: 5; AP COLLECT NONE SCRIPT EXIT EDIT WRITE) |
| H12 | 5 | R | repo에 의도치 않은 파일(임시 스크립트·스크래치·디버그 출력)이 없음 | S5:94, S5:102 | `rule/r_repo_clean` (R: 5; PATCH TESTFILE)<br>`check/e5_unintended_none` (A: 5; AP COLLECT NONE PATH PATCH) |
| H13 | 5 | C | 최종 변경 파일 = 4단계에 적은 수정·생성 파일 | S5:93, S5:103 | `check/c45_final_files` (C: 5; AP COLLECT PATH)<br>`check/e5_final_files_diff` (A: 5; AP COLLECT PATH PATCH) |
| H14 | 5 | R | 최종 변경에 테스트 파일이 없음 | S5:95, S5:104 | `check/e5_test_files_none` (A: 5; AP COLLECT NONE PATCH TESTFILE) |
| H15a | 5 | F | Result·Verdict는 정해진 값 중 하나 (success\|failure, pass\|fail, unchanged\|regression resolved\|pre-existing failures only) | S5:73, S5:77, S5:82 | `atom/H15a` (F: 5; AP COLLECT) |
| H15b | 5 | C | Verdict가 Regressions·Pre-existing failures와 모순되지 않음 | S5:82, S5:83 | `atom/H15b` (C: 5; AP COLLECT NONE) |
| H15c | 5 | C | Unmet requirements가 재현 결과와 모순되지 않음 | S5:78 | `check/c25_unmet_exist` (A: 5; AP COLLECT)<br>`atom/H15c` (C: 5; AP COLLECT NONE) |
| H15d | 5 | F | Regressions·Pre-existing 항목은 '테스트 id -> 원인 -> 해결·이유' 형식 | S5:83, S5:84 | `atom/H15d` (F: 5; AP COLLECT NONE) |
| H16 | 5 | E | 최종 diff를 만듦 | CW:128 | none: a flag, in no score (patch_empty; an empty diff also contradicts 04's Modified (check/e4_modified)) |
| H17 | 5 | P | 빌드·재현·기존 테스트가 모두 통과하면 5단계에서 소스를 더 고치지 않고 05를 씀 | S5:43 | `atom/H17` (P: 5; EDIT TEST SCRIPT EXIT CMDMATCH WRITE) |
| S5.bresult | 5 | F | 05 필드 Build Result | S5:73 | `form/S5.bresult` (F: 5; AP COLLECT) |
| S5.bcmd | 5 | F | 05 필드 Build Command | S5:74 | `form/S5.bcmd` (F: 5; AP COLLECT) |
| S5.rresult | 5 | F | 05 필드 Reproduction Script Result | S5:77 | `form/S5.rresult` (F: 5; AP COLLECT) |
| S5.unmet | 5 | F | 05 필드 Unmet requirements (없으면 none) | S5:78 | `form/S5.unmet` (F: 5; AP COLLECT) |
| S5.cmd | 5 | F | 05 필드 Existing Tests vs Baseline Command | S5:81 | `form/S5.cmd` (F: 5; AP COLLECT) |
| S5.verdict | 5 | F | 05 필드 Verdict | S5:82 | `form/S5.verdict` (F: 5; AP COLLECT) |
| S5.regress | 5 | F | 05 필드 Regressions (없으면 none) | S5:83 | `form/S5.regress` (F: 5; AP COLLECT) |
| S5.pre | 5 | F | 05 필드 Pre-existing failures (없으면 none) | S5:84 | `form/S5.pre` (F: 5; AP COLLECT) |
| S5.fixes | 5 | F | 05 섹션 Fixes Applied (없으면 none) | S5:87 | `form/S5.fixes` (F: 5; AP COLLECT) |
| S5.outstanding | 5 | F | 05 섹션 Outstanding Failures (없으면 none) | S5:90 | `form/S5.outstanding` (F: 5; AP COLLECT) |
| S5.final_files | 5 | F | 05 필드 Files in the change | S5:93 | `form/S5.final_files` (F: 5; AP COLLECT) |
| S5.final_unintended | 5 | F | 05 필드 Unintended files in the repository (없으면 none) | S5:94 | `form/S5.final_unintended` (F: 5; AP COLLECT) |
| S5.final_tests | 5 | F | 05 필드 Test files in the change (없으면 none) | S5:95 | `form/S5.final_tests` (F: 5; AP COLLECT) |
