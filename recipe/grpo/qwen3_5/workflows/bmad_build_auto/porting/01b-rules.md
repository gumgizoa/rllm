# 01b. 규칙 목록: BMAD-METHOD `bmad-build-auto`, port 전 상태

> 입력: `rules.yaml`(이 디렉터리; 이 문서는 scratchpad의 `render_rules.py`가 그 파일에서 만든다). 방법: `if/10_handover_templates_layers.md` 0·2·3절, 카탈로그 `sdlc_if/templates.yaml`, 선례 `aidlc_v4_eval.ruleset.md`. 상류: BMAD-METHOD @ 10db8f35 (v6.12.2), 읽기 전용, 실행한 것 없음.

## 1. 방법과 범위

- 단위: 문서의 한 줄이 에이전트에게 요구·금지하는 것 하나 = 규칙 하나. 설명·예시·제목·상태 변수 선언(step-01 frontmatter, customize.toml 머리말, VG:5-9의 gap 종류 정의, VG:57-66의 예시, spec-template의 placeholder 문장)은 규칙을 내지 않았다. 같은 로직이 여러 파일에 반복되면(언어 규칙, NEXT 줄, 리뷰어 공통 금지) 출처를 합쳐 규칙 하나로 두었다.
- 템플릿은 문장이 아니라 판정 로직(무엇과 무엇을, 어떤 형태로, 어느 구간에서, 어느 극성으로)에 붙였다. 맞는 것이 없으면 `NEW-*`를 만들고 yaml 끝 `new_templates:`에 한 번 정의했다. judge만 볼 수 있는 내용 규칙은 카탈로그 밖(10 문서 2.5절)이므로 별도 축 `NEW-J-content`(기술 J) 하나에 모았다. `template: null`은 함수도 judge도 볼 수 없는 것(정신 상태, 설정 훅, 절 단위 읽기)에만 썼다.
- `학습 대비`는 세 학습 workflow의 constraints.yaml에서 같은 템플릿의 `implemented` 항목(`rewarded`), 반대 방향 항목·문서(`opposite`), 항목은 없지만 문서가 보여 주는 것(`shown`), 그 밖(`none`)으로 나눴고 층 후보는 10 문서 3.1절대로 L1/L1C/L2M/L2F다. `판정`은 enforced(기계가 위반을 막음)/code/judge/none. `port 운명`은 단일 무인 openhands-sdk 에이전트·SWE 과제·/testbed·서브에이전트 없음·네트워크 없음·숨은 테스트·저장소 밖 산출물·커밋 없음을 전제한 2단계용 추정이다.

읽은 파일 (상류 경로, 줄 수):

| id | 파일 | 역할 | 줄 |
|---|---|---|---|
| SK | `src/bmm-skills/ship/bmad-build-auto/SKILL.md` | skill | 13 |
| WF | `src/bmm-skills/ship/bmad-build-auto/workflow.md` | skill | 104 |
| S1 | `src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md` | step | 84 |
| S2 | `src/bmm-skills/ship/bmad-build-auto/step-02-plan.md` | step | 27 |
| S3 | `src/bmm-skills/ship/bmad-build-auto/step-03-implement.md` | step | 48 |
| S4 | `src/bmm-skills/ship/bmad-build-auto/step-04-review.md` | step | 116 |
| ST | `src/bmm-skills/ship/bmad-build-auto/spec-template.md` | template | 96 |
| CT | `src/bmm-skills/ship/bmad-build-auto/customize.toml` | prompt | 119 |
| EH | `src/bmm-skills/ship/bmad-build-auto/review-prompts/edge-case-hunter.md` | prompt | 112 |
| VG | `src/bmm-skills/ship/bmad-build-auto/review-prompts/verification-gap.md` | prompt | 113 |
| CC | `src/bmm-skills/ship/bmad-build-auto/references/claims-check.md` | prompt | 14 |
| DC | `src/bmm-skills/ship/bmad-build-auto/references/deletion-check.md` | prompt | 14 |
| CE | `src/bmm-skills/ship/bmad-build-auto/compile-epic-context.md` | prompt | 62 |
| MB | `src/bmm-skills/module.yaml` | code | 85 |
| MC | `src/core-skills/module.yaml` | code | 38 |
| | **합계** | | 1045 |

규칙 수 280 (범주별: P 절차 104, F 형식 76, E 실행 16, C 일관성 7, R 금지 22, Q 내용 42, A 보고 13). 템플릿 있는 규칙 262, `null` 18. 판정: code 211, judge 53, none 12, enforced 4.

블록: A 활성화·읽기, B 산출물 규율(언어·경로·frontmatter·고정 구역), C 라우팅·status(step-01, HALT 분기), D 계획·spec 내용(step-02, spec-template, READY 기준), E 구현(step-03, 핸드오프), F 검증(Verification 명령, matrix 감사, 재검증), G 리뷰(step-04, 레이어 프롬프트, 분류, 라우팅, 루프), H 마무리·HALT, I 서브에이전트 기계, J epic 맥락 컴파일.

## 2. 규칙 표

출처는 `문서id:줄`(1절 표). 학습 대비는 `relation → 층 후보`. port 운명은 `fate (gap)`. 근거 상세(학습 항목 id, 문서 줄)는 `rules.yaml`의 `train.note`·`port.note`에 있다.

| id | stage | 범주 | 규칙 | 출처 | template | 학습 대비 | 판정 | port 운명 |
|---|---|---|---|---|---|---|---|---|
| A1 | 0 전역 | P | 첫 행동으로 render_skill.py 명령을 정확히 한 번, cwd를 바꾸지 않고, {project-root}·{skill-root}를 절대경로로 치환해 실행한다 | SK:6, SK:9 | T-AW5 | rewarded → L1 | code | drop (G7) |
| A2 | 0 전역 | P | 렌더 성공 시 stdout에 찍힌 workflow.md 절대경로 하나를 읽고 따른다 (가장 먼저 읽는 문서) | SK:12 | T-RD1 | rewarded → L1 | code | env (G5) |
| A3a | 0 전역 | P | 렌더 실패(uv 없음 포함) 시 명령 출력을 보고하고 HALT한다 | SK:13 | T-OR2 | rewarded → L1 | code | drop (G7) |
| A3b | 0 전역 | R | 렌더 실패 시 원본 workflow 소스 파일을 직접 실행하지 않는다 | SK:13 | T-PR6 | rewarded → L1 | code | drop (G7) |
| A4 | 0 전역 | P | 단계 파일이 다른 snapshot 파일을 가리키면 그 파일을 끝까지 읽고 따른다 | WF:5, S1:14 | T-RD2 | rewarded → L1 | code | env (G5) |
| A5 | 0 전역 | P | 파일 간 참조는 모두 절대 snapshot 경로다: 그 경로를 바로 열고 skill 디렉터리 기준으로 해석하지 않는다 | WF:71 | T-RD2 | rewarded → L1 | code | env (G5) |
| A6 | 0 전역 | P | 활성화 1단계: prepend 단계를 순서대로 실행한다 (`_None._`이면 건너뜀; 기본값 빈 목록) | WF:80-82, CT:17 | null | none | enforced | drop (G7) |
| A7 | 0 전역 | P | 활성화 2단계: persistent_facts 항목을 실행 내내 기본 맥락으로 삼고 `file:` 항목은 내용을 로드한다 (기본값 빈 목록) | WF:86-88, CT:23-27 | null | none | enforced | drop (G7) |
| A8 | 0 전역 | P | 활성화 3단계: append 단계를 순서대로 실행한다 (`_None._`이면 건너뜀; 기본값 빈 목록) | WF:92-94, CT:21 | null | none | enforced | drop (G7) |
| A10 | 0 전역 | P | 단계 파일을 순서대로 따른다: 한 단계를 끝까지 읽고 실행한 뒤, 지시받을 때만 다음 단계를 연다 | WF:100 | T-OR1 | rewarded → L1 | code | keep |
| A11 | 0 전역 | P | 단계를 건너뛰거나 순서를 바꾸지 않는다 (의도가 상세해도 step-02 조사·spec 작성은 생략하지 않음) | WF:100, S1:13 | T-OR1 | rewarded → L1 | code | keep |
| A12 | 0 전역 | P | 다음 단계 파일을 미리 읽지 않는다 | WF:100 | T-RD3 | rewarded → L1 | code | keep |
| A14 | 0 전역 | P | 각 단계 파일 끝의 NEXT가 가리키는 다음 단계 파일을 끝까지 읽고 따른다 (workflow.md→step-01→02→03→04) | WF:104, S1:84, S2:27, S3:48 | T-RD2 | rewarded → L1 | code | env (G5) |
| B1 | 0 전역 | F | 문서(spec 등 파일)는 {{.document_output_language}}(기본 English)로 쓴다 | WF:73, S1:12, S2:5, S3:8, S4:5, MC:25-28 | NEW-FM-language | none → L2F | code | env (G10) |
| B2 | 0 전역 | F | 대화(메시지)는 {{.communication_language}}(기본 English)로 한다 | WF:73, S1:12, MC:19-23 | NEW-FM-language | none → L2F | code | env (G10) |
| B3 | 0 전역 | Q | 설명 수준을 {{.user_skill_level}}(기본 intermediate)에 맞춘다 | WF:73, S1:12, MB:13-18 | null | none | none | drop (G2) |
| B4 | 0 전역 | A | 버전관리 리비전을 기록할 때는 VCS에서 직접 얻은 전체 정식 식별자를 그대로 적는다 | WF:74 | T-RF1 | rewarded → L1 | code | keep |
| B5 | 3 implement | F | spec 안의 markdown 링크는 spec 파일 디렉터리 기준 상대경로로 쓴다 (앞에 `/` 없음) | S3:32 | T-FM2 | none → L2M | code | env (G5) |
| B6 | 3 implement | F | 터미널·대화에 쓰는 파일 경로는 CWD 기준 상대경로에 `:line`을 붙인다 (앞에 `/` 없음) | S3:32 | T-FM2 | shown → L2M | code | env (G10) |
| B7 | 0 전역 | F | spec frontmatter 키는 title, type, created, status, review_loop_iteration, followup_review_recommended, context, warnings, deferred다 | ST:1-11 | T-FM5 | none → L2F | code | keep |
| B8 | 0 전역 | F | frontmatter `type`은 feature \| bugfix \| refactor \| chore 중 하나다 | ST:3 | T-FM2 | rewarded → L1 | code | keep |
| B9 | 0 전역 | F | frontmatter `status`는 draft \| ready-for-dev \| in-progress \| in-review \| done \| blocked 중 하나다 | ST:5 | T-FM2 | rewarded → L1 | code | keep |
| B10 | 0 전역 | F | `review_loop_iteration`은 0에서 시작하는 정수, `followup_review_recommended`는 false에서 시작하는 불리언이다 | ST:6-7 | T-FM2 | rewarded → L1 | code | keep |
| B11 | 0 전역 | F | `context:`에는 `{project-root}/` 접두 경로만, 짧게, spec 본문에 녹지 않은 것만 적는다 | ST:8 | T-RF4 | rewarded → L1 | code | keep |
| B12 | 0 전역 | F | `warnings:`에는 기계가 읽는 값(oversized, multiple-goals)만 넣는다 | ST:9 | T-FM2 | rewarded → L1 | code | keep |
| B13 | 0 전역 | R | spec의 `<intent-contract>` 안 내용은 계획 후 읽기 전용이다: 구현·리뷰 중 수정하지 않는다 | S3:10, S4:72 | T-WD4 | rewarded → L1 | code | keep |
| B14 | 0 전역 | R | `## Spec Change Log`과 `## Review Triage Log`은 append-only다: 기존 항목을 고치거나 지우지 않는다 | ST:68, ST:75, ST:10 | T-WD4 | rewarded → L1 | code | keep |
| B15 | 0 전역 | F | 한 실행은 하나의 spec 파일만 만든다: 교차 레이어 스토리도 한 파일에 두고, 다른 story spec을 만들거나 건드리지 않는다 | ST:15, S1:39 | T-WD3 | rewarded → L1 | code | keep |
| C1 | 1 clarify | P | 호출 프롬프트를 의도로 삼는다 (story id, ticket id, 파일 경로, 짧은 설명, 자유 서술 모두 가능) | S1:18, S1:41 | null | none | none | env (G1) |
| C2 | 1 clarify | P | EARLY EXIT 뒤에는 나중 단계가 명시적으로 되돌리라고 할 때만 step-01로 돌아온다 | S1:14 | T-OR3 | opposite → L1C | code | drop (G1) |
| C3a | 1 clarify | P | 프롬프트가 status frontmatter가 있는 기존 spec을 가리키면 status로 바로 분기한다: draft→step-02, ready-for-dev/in-progress→step-03, in-review→step-04 | S1:20-23 | T-OR2 | rewarded → L1 | code | drop (G1) |
| C3b | 1 clarify | P | 기존 spec의 status가 blocked면 HALT blocked, 차단 조건 `blocked spec supplied` | S1:24 | T-OR2 | rewarded → L1 | code | drop (G1) |
| C3c | 1 clarify | P | 기존 spec의 status가 done이면 review_loop_iteration을 0으로, followup_pass를 true로 놓고 step-04로 간다 (후속 리뷰, 재개 아님) | S1:25 | T-FM2 | rewarded → L1 | code | drop (G1) |
| C4 | 1 clarify | P | folder+id 디스패치: spec 폴더와 story id를 프롬프트에서 받고, 그 외 프롬프트 문구는 경쟁 설명이 아니라 step-02의 추가 맥락으로만 쓴다 | S1:27 | null | none | none | drop (G1) |
| C5a | 1 clarify | P | folder+id: `{spec_folder}/stories.yaml`을 읽고 `id == story_id` 항목을 찾는다 | S1:29 | T-RD4 | rewarded → L1 | code | drop (G1) |
| C5b | 1 clarify | P | stories.yaml이 없거나 파싱 실패면 `no stories.yaml found`, 항목이 없으면 `story id not found in stories.yaml`로 HALT blocked | S1:29 | T-OR2 | rewarded → L1 | code | drop (G1) |
| C5c | 1 clarify | R | stories.yaml 항목에서 title과 description만 쓴다: checkpoint 필드와 invoke_dev_with는 읽지 않는다 | S1:29 | null | none | none | drop (G1) |
| C6 | 1 clarify | P | folder+id: `{spec_folder}/stories/{story_id}-*.md`를 찾아 둘 이상이면 `ambiguous story file match`로 HALT blocked, 하나면 spec_file로 삼는다 | S1:31-33 | T-OR2 | rewarded → L1 | code | drop (G1) |
| C7 | 1 clarify | P | folder+id의 draft story: 다른 `stories/*.md`를 status와 무관하게 모두 읽어 Code Map·Design Notes·Spec Change Log·Tasks 체크 상태·Auto Run Result를 step-02 맥락으로 가져간 뒤 step-02로 간다 | S1:34 | T-RD4 | rewarded → L1 | code | drop (G1) |
| C8 | 1 clarify | P | folder+id의 다른 status는 C3과 같이 분기하되 blocked story는 `story already blocked`로, status가 없거나 모르는 값이면 `unrecognized status in existing story file`로 HALT blocked | S1:35-36 | T-OR2 | rewarded → L1 | code | drop (G1) |
| C9a | 1 clarify | P | folder+id 첫 디스패치: `{spec_folder}/SPEC.md`가 없으면 `no epic spec found`로 HALT blocked | S1:37 | T-OR2 | rewarded → L1 | code | drop (G1) |
| C9b | 1 clarify | P | folder+id 첫 디스패치: SPEC.md와 그 `companions:` 파일, 모든 `stories/*.md`를 계획 맥락으로 읽는다 | S1:37 | T-RD4 | rewarded → L1 | code | drop (G1) |
| C9c | 1 clarify | P | folder+id 첫 디스패치: INSTRUCTIONS 1·2항을 건너뛰고 3항(VCS 점검)부터 계속한다 | S1:37 | T-OR1 | rewarded → L1 | code | drop (G1) |
| C10 | 1 clarify | R | 호출당 stories.yaml 항목 하나만 다룬다: 다른 항목을 읽지 않고 결과와 무관하게 다른 story로 넘어가지 않는다 | S1:39 | T-WD3 | rewarded → L1 | code | drop (G1) |
| C11 | 1 clarify | R | spec이 아닌 파일에서 workflow 상태를 추론하지 않는다 | S1:41 | null | none | judge | drop (G1) |
| C12 | 1 clarify | P | 프롬프트만으로 무엇을 구현할지 알 수 없으면 `unclear intent`로 HALT blocked | S1:42 | T-OR2 | opposite → L1C | code | semantic (G8) |
| C13 | 1 clarify | P | 맥락 로드: `{{.planning_artifacts}}`와 `{{.implementation_artifacts}}` 디렉터리의 파일 목록을 본다 (기본 `{project-root}/_bmad-output/planning-artifacts`, `.../implementation-artifacts`) | S1:47, MB:28-36, MC:30-33 | T-RD5 | rewarded → L1 | code | env (G5) |
| C14 | 1 clarify | P | 프롬프트가 비정형 spec/intent 파일을 가리키면 그 파일만 읽고, 관련 없는 intent 파일을 뒤지지 않는다 | S1:48 | T-RD4 | rewarded → L1 | code | drop (G1) |
| C15 | 1 clarify | Q | epic 스토리인지는 의도·목록·epics 파일 내용을 함께 추론해 정하고, 파일명 패턴이나 정규식으로 정하지 않는다 | S1:49 | null | none | none | drop (G3) |
| C16 | 1 clarify | P | epic 경로: epic 번호(와 story 번호)를 알아내고, epic 번호를 못 찾으면 freeform 경로(B)로 간다 | S1:51-53 | T-OR2 | rewarded → L1 | code | drop (G3) |
| C17 | 1 clarify | P | epic 경로: 쓰기 전에 `IA/epic-<N>-context.md` 캐시가 유효한지(존재·비어 있지 않음·`# Epic <N> Context:`로 시작·planning 파일보다 새것) 확인하고, 유효하면 그것만 읽고 원본 계획 문서는 읽지 않는다 | S1:55-57 | NEW-WD-exists-before | none → L2F | code | drop (G3) |
| C18 | 1 clarify | P | epic 경로: 캐시가 없거나 무효면 compile-epic-context.md를 프롬프트로 한 동기 서브에이전트로 `IA/epic-<N>-context.md`를 만든다 (epic 번호·epics 파일·PA·출력 경로 전달) | S1:59 | NEW-AW-subagent | none → L2F | code | drop (G7) |
| C19 | 1 clarify | P | epic 경로: 컴파일했으면 출력 파일이 존재하고 비어 있지 않고 `# Epic <N> Context:`로 시작하는지 확인하고, 아니면 `context compilation verification failed`로 HALT blocked | S1:61 | NEW-WD-exists-after | none → L2F | code | drop (G3) |
| C20 | 1 clarify | P | epic 경로: 같은 epic의 `status: done`이고 story 번호가 낮은 spec 중 가장 최근 것을 읽어 Code Map·Design Notes·Spec Change Log·task list를 연속성 맥락으로 삼는다; done은 없고 in-review만 있으면 `missing previous-story continuity decision`으로 HALT blocked | S1:63 | T-RD4 | rewarded → L1 | code | drop (G3) |
| C21 | 1 clarify | P | freeform 경로: 목록에서 PRD(*prd*)·Architecture·UX·Epics·Brief 패턴 파일을 찾아 의도와 관련된 것만 골라 읽는다 (전부 읽지 않아도 되지만 코드만 보고 추측하지 않음) | S1:66-72 | T-RD5 | rewarded → L1 | code | drop (G3) |
| C22 | 1 clarify | Q | 프롬프트와 읽은 산출물로 의도를 확정한다: 지어내지 않고 열린 질문을 남기지 않는다 | S1:73 | NEW-J-content | shown → L2M | judge | keep |
| C23 | 1 clarify | P | 의도를 확정할 수 없으면 미해결 질문을 차단 조건으로 HALT blocked | S1:73 | T-OR2 | opposite → L1C | code | semantic (G4) |
| C24a | 1 clarify | E | VCS 점검: Git이면 계획 전에 `git add --refresh -- .`를 실행하고 트리가 여전히 깨끗한지 확인한다 (VCS가 없으면 생략) | S1:74 | T-AW5 | rewarded → L1 | code | drop (G7) |
| C24b | 1 clarify | P | 작업 트리가 더럽거나 브랜치가 의도와 맞지 않거나 메타데이터를 쓸 수 없으면 HALT blocked (`version-control metadata not writable`) | S1:74 | T-OR2 | rewarded → L1 | code | drop (G7) |
| C24c | 1 clarify | P | folder+id에서는 브랜치를 story가 아니라 epic에 맞춰 판단한다 | S1:74 | null | none | none | drop (G1) |
| C25 | 1 clarify | Q | 의도에 독립적으로 출시 가능한 목표가 여럿이면 `multiple-goals`를 step-02로 넘겨 warnings에 넣게 하고, 쪼개거나 막지 않는다 | S1:75 | NEW-J-content | none → L2F | judge | keep |
| C26 | 1 clarify | F | folder+id의 spec 경로는 `{spec_folder}/stories/{story_id}-{slug}.md` (title에서 kebab-case slug, id 접두 없음, IA fallback·-2 접미 없음) | S1:78, WF:13-15 | T-FM1 | rewarded → L1 | code | drop (G1) |
| C27 | 1 clarify | F | spec 파일명 slug는 의도에서 만든 kebab-case이며, 추적 식별자(story/issue/ticket)가 있으면 그것으로 시작한다 (예 `gh-47-fix-auth`) | S1:80 | T-FM1 | rewarded → L1 | code | env (G5) |
| C28 | 1 clarify | P | `IA/spec-{slug}.md`가 이미 있으면 draft일 때만 같은 작업으로 재개하고, 아니면 `-2`, `-3`을 붙인다 | S1:80 | NEW-WD-exists-before | none → L2F | code | drop (G5) |
| C29 | 1 clarify | F | spec은 `{{.implementation_artifacts}}/spec-{slug}.md`에 있다 (기본 `{project-root}/_bmad-output/implementation-artifacts/`) | S1:80, MB:33-36, MC:30-33 | T-FM1 | rewarded → L1 | code | env (G5) |
| C30 | 3 implement | P | step-03 전제: spec_file이 비어 있지 않은 경로이고 디스크에 존재해야 한다; 아니면 `missing spec_file before implementation`으로 HALT blocked | S3:14 | NEW-WD-exists-after | none → L2F | code | keep |
| C31 | 3 implement | P | 구현을 시작하기 전에 spec status를 `in-progress`로 바꾼다 (첫 코드 수정 이전) | S3:24 | T-AW1 | rewarded → L1 | code | keep |
| C32 | 4 review | P | 리뷰를 시작하기 전에 spec status를 `in-review`로 바꾼다 | S4:11 | T-OR1 | rewarded → L1 | code | keep |
| C33 | HALT | F | HALT 시 spec_file이 있으면 frontmatter status를 최종 상태(done \| blocked \| ready-for-dev)로 갱신한다 | WF:16, WF:31, S4:109-111 | T-FM2 | rewarded → L1 | code | keep |
| C34 | HALT | F | 정상 완료의 최종 status는 `done`이다 | S4:116 | T-FM2 | rewarded → L1 | code | keep |
| D1 | 0 전역 | P | 사람과 상호작용하지 않는다: 질문하거나 승인을 기다리지 않는다 (step-02·03·04 공통) | WF:3, S2:6, S3:9, S4:6 | T-SR2 | shown → L2M | code | keep |
| D2 | 2 plan | P | draft 재개: spec_file이 `status: draft`로 있으면 읽고 `<intent-contract>` 블록을 그대로 preserved_intent_contract로 보관한다 | S2:10 | T-RD4 | rewarded → L1 | code | drop (G1) |
| D3 | 2 plan | E | 코드베이스를 조사한다: 좁은 작업은 코드를 직접 읽는다 | S2:11 | T-RD5 | rewarded → L1 | code | keep |
| D4 | 2 plan | P | 깊은 탐색은 동기 서브에이전트에 맡기고 요약만 받아 그 요약으로 계획한다 | S2:11 | NEW-AW-subagent | none → L2F | code | drop (G7) |
| D5a | 2 plan | Q | 조사 결과 중 실행에 실제로 필요한 것(파일, 심볼/라인, 재사용 지점, 읽기 전용 제약)만 골라 Code Map으로 가져간다 | S2:11-12 | NEW-J-content | shown → L2M | judge | keep |
| D5b | 2 plan | E | Code Map에 적은 파일은 spec을 쓰기 전에 실제로 열어 본 파일이다 | S2:11-12, ST:49 | T-RD4 | rewarded → L1 | code | keep |
| D6 | 2 plan | P | spec-template.md를 끝까지 읽은 뒤 채운다 (spec 쓰기 전) | S2:12 | T-RD2 | rewarded → L1 | code | env (G5) |
| D7 | 2 plan | F | frontmatter `created`는 현재 시스템 날짜다 | S2:12, ST:4 | T-FM2 | rewarded → L1 | code | keep |
| D8 | 2 plan | F | `## Code Map` 항목은 `` `FILE` -- ROLE_OR_RELEVANCE `` 형식(주석 단 경로, 심볼/라인 anchor, 재사용 포인터)이다 | S2:12, ST:47-52 | T-FM3 | rewarded → L1 | code | keep |
| D9 | 2 plan | A | Code Map의 경로는 저장소에 실제로 존재한다 | S2:12, ST:51-52 | T-RF4 | rewarded → L1 | code | keep |
| D10 | 2 plan | P | preserved_intent_contract가 있으면 쓰기 전에 채운 spec의 `<intent-contract>` 블록을 그것으로 바꾼다 (이전 계약 보존) | S2:12 | T-WD4 | rewarded → L1 | code | drop (G1) |
| D11 | 2 plan | F | 채운 spec을 spec_file에 쓴다 | S2:12 | T-FM1 | rewarded → L1 | code | env (G5) |
| D12 | 2 plan | P | READY FOR DEVELOPMENT 기준으로 스스로 점검한다 | S2:13 | null | none | none | keep |
| D13 | 2 plan | F | Actionable: 모든 task에 파일 경로와 구체적 행동이 있다 (`` `FILE` -- ACTION -- RATIONALE ``) | WF:61, ST:56, ST:61 | T-FM3 | rewarded → L1 | code | keep |
| D14 | 2 plan | Q | Logical: task는 의존 순서로 배열된다 | WF:62 | NEW-J-content | shown → L2M | judge | keep |
| D15 | 2 plan | F | Testable: 모든 Acceptance Criteria는 Given/When/Then 형식이다 | WF:63, ST:64 | T-FM3 | rewarded → L1 | code | keep |
| D16 | 2 plan | Q | Surface-anchored: AC는 의도가 가리키는 가장 바깥 표면을 관찰하고, 더 안쪽 대리물을 쓰지 않는다 | WF:64 | NEW-J-content | none → L2F | judge | keep |
| D17 | 2 plan | F | Complete: placeholder나 TBD가 없다 | WF:65, ST:16 | T-FM4 | rewarded → L1 | code | keep |
| D18 | 2 plan | Q | Sufficient: 알려진 요구사항·수용·의존·구현 공백이 미해결로 남지 않는다 | WF:66 | NEW-J-content | none → L2F | judge | keep |
| D19 | 2 plan | Q | Coherent: 미해결 모호함이나 내부 모순이 없다 | WF:67 | NEW-J-content | none → L2F | judge | keep |
| D20 | 2 plan | P | intent gap(의도로 고를 수 없고 관찰 가능한 결과가 다른 복수 해석)이 있으면 하나를 골라 해소하지 않고 `intent gap`으로 HALT blocked, 미답 질문과 수집한 증거를 포함한다 | S2:14 | T-OR2 | opposite → L1C | code | semantic (G4) |
| D21 | 2 plan | F | step-01이 `multiple-goals`를 넘겼으면 frontmatter warnings에 넣는다 | S2:15 | T-FM2 | rewarded → L1 | judge | keep |
| D22 | 2 plan | F | spec이 1600 토큰을 넘으면 warnings에 `oversized`를 넣고 계속한다 (막지 않음) | S2:15, ST:13 | NEW-FM-internal | none → L2F | code | keep |
| D23 | 2 plan | P | READY 게이트: workflow.md를 다시 읽는다 | S2:19 | T-RD2 | none → L2M | code | keep |
| D24 | 2 plan | P | READY 게이트: spec_file을 디스크에서 다시 읽고 기준 충족을 확인한다 | S2:19, S2:23 | T-RD4 | rewarded → L1 | code | keep |
| D25 | 2 plan | P | 게이트에서 spec 파일이 사라졌으면 `planned spec file disappeared before implementation`으로 HALT blocked | S2:21 | NEW-WD-exists-after | none → L2F | code | keep |
| D26 | 2 plan | F | spec이 기준을 충족하면 frontmatter status를 `ready-for-dev`로 놓는다 (step-03으로 넘어가기 전) | S2:22 | T-FM2 | rewarded → L1 | code | keep |
| D27 | 2 plan | P | 호출 프롬프트가 계획 후 정지를 지시하면(`Halt after planning.` 또는 동등 표현) status ready-for-dev로 HALT한다 | S2:22 | T-OR2 | rewarded → L1 | code | drop (G1) |
| D28 | 2 plan | P | 기준 미달이면 한 번만 수선하고 디스크에서 다시 읽어 재확인한다; 그래도 미달이면 `spec failed ready-for-development standard`로 HALT blocked, 미달 기준과 증거를 포함한다 | S2:23 | T-OR2 | rewarded → L1 | code | semantic (G8) |
| D29 | 2 plan | F | spec 길이는 900–1600 토큰을 목표로 한다 | ST:13 | T-FM3 | rewarded → L1 | code | keep |
| D30 | 2 plan | Q | '어떻게'를 과하게 지정하지 않는다: 경계와 예시로 쓴다 | ST:14 | NEW-J-content | shown → L2M | judge | keep |
| D31 | 2 plan | F | 채울 때 template의 HTML 주석을 모두 지운다 | ST:16 | T-FM4 | rewarded → L1 | code | keep |
| D32 | 2 plan | F | `<intent-contract>`…`</intent-contract>` 태그가 Intent, Boundaries & Constraints, I/O & Edge-Case Matrix를 감싼다 | ST:18, ST:45 | T-FM2 | rewarded → L1 | code | keep |
| D33 | 2 plan | F | `## Intent`에 **Problem:**과 **Approach:** 라벨이 있고 채워져 있다 | ST:20-26 | T-FM2 | rewarded → L1 | code | keep |
| D34 | 2 plan | F | Problem과 Approach는 각각 한두 문장이다 | ST:24, ST:26 | T-FM3 | rewarded → L1 | code | keep |
| D35 | 2 plan | Q | Problem은 무엇이 깨졌거나 없는지와 왜 중요한지, Approach는 '무엇'(how가 아님)을 적는다 | ST:22 | NEW-J-content | shown → L2M | judge | keep |
| D36 | 2 plan | F | `## Boundaries & Constraints`에 **Always:**(불변 규칙)와 **Never:**(비목표·금지 접근) 라벨이 있고 채워져 있다 | ST:28-34 | T-FM2 | rewarded → L1 | code | keep |
| D37 | 2 plan | Q | Always에는 불변 규칙만, Never에는 범위 밖과 금지 접근만 적는다 | ST:30 | NEW-J-content | shown → L2M | judge | keep |
| D38 | 2 plan | F | `## I/O & Edge-Case Matrix`는 Scenario \| Input / State \| Expected Output / Behavior \| Error Handling 4열 표이고 행마다 네 칸이 채워져 있다 | ST:36-43 | T-FM6 | rewarded → L1 | code | keep |
| D39 | 2 plan | F | 해당 내용이 없는 선택 섹션(I/O Matrix, Design Notes, Verification)은 통째로 지운다: 제목 집합은 template 제목의 부분집합이다 | ST:38, ST:82, ST:89 | T-FM7 | rewarded → L1 | code | keep |
| D40 | 2 plan | R | 비어 있는 섹션에 "N/A"나 "None"을 쓰지 않는다 (섹션을 지운다) | ST:38, ST:82, ST:89 | T-FM2 | opposite → L1C | code | keep |
| D41 | 2 plan | Q | task는 파일당 하나를 선호하고, 쪼개면 부자연스러운 밀접한 변경만 묶는다 | ST:56 | NEW-J-content | none → L2F | judge | keep |
| D42 | 2 plan | F | I/O Matrix가 있으면 그 edge case를 단위 테스트하는 task를 포함한다 | ST:57 | T-TR1 | opposite → L1C | code | semantic (G9) |
| D43 | 2 plan | Q | AC는 I/O Matrix에 없는 시스템 수준 행동만 다루고 I/O 시나리오를 중복하지 않는다 | ST:58 | NEW-J-content | none → L2F | judge | keep |
| D44 | 2 plan | F | `## Tasks & Acceptance`에 **Execution:** 목록과 **Acceptance Criteria:** 목록이 있다 | ST:54-64 | T-FM2 | rewarded → L1 | code | keep |
| D45 | 2 plan | F | `## Spec Change Log`과 `## Review Triage Log` 섹션이 있다 (처음에는 비어 있음) | ST:66, ST:73 | T-FM2 | rewarded → L1 | code | keep |
| D46 | 2 plan | Q | `## Design Notes`는 접근이 뻔하면 지우고, 비자명할 때만 근거와 5–10줄 golden example을 쓴다 | ST:80-85 | NEW-J-content | shown → L2M | judge | keep |
| D47 | 2 plan | F | `## Verification`에 **Commands:** 목록이 `` `COMMAND` -- expected: SUCCESS_CRITERIA `` 형식으로 있고, CLI가 없을 때만 **Manual checks (if no CLI):**를 쓴다 | ST:87-96 | T-FM3 | rewarded → L1 | code | keep |
| D48 | 2 plan | Q | Verification은 CLI 명령을 우선하고, CLI 점검이 없을 때만 수동 점검 대상과 기대 상태를 적는다 | ST:90 | NEW-J-content | shown → L2M | judge | keep |
| E1 | 3 implement | A | frontmatter `baseline_revision`은 실제 HEAD의 전체 식별자다 (VCS가 없으면 `NO_VCS`) | S3:20, WF:74 | T-RF1 | rewarded → L1 | code | keep |
| E2 | 3 implement | P | `baseline_revision`은 어떤 코드 변경보다 먼저 기록한다 | S3:20 | T-AW1 | rewarded → L1 | code | keep |
| E3 | 3 implement | P | 구현 핸드오프 텍스트에 런타임 자리표시자(`{spec_file}`)를 치환해 그대로 따른다 | S3:26 | NEW-AW-subagent | none → L2F | judge | drop (G7) |
| E4 | 3 implement | R | 핸드오프에 부모가 쓴 목표 재진술·파일 목록·소유 경계·수용 기준을 덧붙이지 않는다: spec이 유일한 진실원이다 | S3:26 | NEW-AW-subagent | none → L2F | judge | drop (G7) |
| E5 | 3 implement | P | 핸드오프가 spec과 충돌하면 두 구절을 포함해 `handoff conflicts with spec`으로 HALT blocked | S3:26 | T-OR2 | rewarded → L1 | code | drop (G7) |
| E6 | 3 implement | P | 구현 서브에이전트는 이전 대화 맥락 없이 띄운다 | CT:40 | NEW-AW-subagent | none → L2F | code | drop (G7) |
| E7 | 3 implement | P | (구현자) 구현 전에 spec_file을 끝까지 읽고 spec만을 진실원으로 삼아 구현한다 | CT:42 | T-RD4 | rewarded → L1 | code | env (G7) |
| E8 | 3 implement | P | (구현자) 시작 전에 frontmatter `context:`의 파일을 모두 읽는다 | CT:42, ST:8 | T-RD4 | rewarded → L1 | code | drop (G3) |
| E9 | 3 implement | A | (구현자) 끝나면 무엇을 바꿨고 어떻게 검증했고 무엇이 미완·위험한지 보고한다 | CT:44 | T-FM2 | rewarded → L1 | judge | drop (G7) |
| E10 | 3 implement | P | 구현 서브에이전트는 동기로 호출해 같은 턴에서 기다린다; 백그라운드·분리·알림 대기 금지 | S3:30, WF:55 | NEW-AW-subagent | none → L2F | code | drop (G7) |
| E11 | 3 implement | P | 서브에이전트가 돌아온 뒤에만 Verify로 넘어간다 | S3:30 | T-OR1 | rewarded → L1 | code | drop (G7) |
| E12 | 3 implement | P | 플랫폼이 허용하면 구현 서브에이전트를 재호출 가능하게 유지한다 (step-04의 patch 전달용) | S3:30 | null | none | none | drop (G7) |
| E13 | 3 implement | E | 서브에이전트가 미완 작업을 보고했으면 진행 전에 직접 마무리한다 | S3:36 | null | none | judge | drop (G7) |
| E14a | 3 implement | E | 구현 후 VCS 도구로 baseline_revision 이후의 모든 변경(미추적 파일 포함)을 unified diff로 만든다 | S3:38 | T-AW5 | rewarded → L1 | code | env (G7) |
| E14b | 3 implement | F | diff 파일은 시스템 임시 디렉터리의 고유 이름 파일에 쓰고 그 절대경로를 diff_file로 삼는다 (저장소 안이 아님) | S3:38, S4:15 | T-WD3 | rewarded → L1 | code | keep |
| E15 | 3 implement | P | diff 파일을 자기 맥락으로 읽는다 | S3:38 | T-RD4 | rewarded → L1 | code | keep |
| E16 | 3 implement | Q | 판단은 서브에이전트의 보고가 아니라 diff에 대해 한다 | S3:38 | NEW-J-content | none → L2F | judge | semantic (G7) |
| F1 | 3 implement | E | spec의 `## Verification` 명령을 실행한다 (또는 수동 점검을 수행한다) | S3:40 | T-TR2 | shown → L2M | code | keep |
| F2 | 3 implement | P | 검증이 실패하고 고칠 수 없으면 실패한 명령·이유를 포함해 `implementation verification failed`로 HALT blocked | S3:40 | T-OR2 | rewarded → L1 | code | semantic (G8) |
| F3 | 3 implement | E | 실패 수정으로 코드가 바뀌면 diff_file을 다시 만들고 다시 읽는다 (마지막 수정 이후) | S3:40 | T-AW3 | rewarded → L1 | code | env (G7) |
| F4 | 3 implement | C | I/O Matrix가 있으면 모든 행이 그 기대 행동을 검증하는 테스트 하나 이상으로 덮인다 | S3:44 | T-TR1 | rewarded → L1 | judge | semantic (G9) |
| F5 | 3 implement | A | 행을 덮는 테스트는 검증 출력에서 실제로 실행되어 통과했다; 존재하지만 미실행(미등록·필터·skip·disabled)이면 없는 것으로 친다 | S3:44 | T-RF1 | rewarded → L1 | code | semantic (G9) |
| F6 | 3 implement | R | 테스트가 matrix와 어긋나도 기대값을 코드에 맞춰 고치지 않는다: 코드를 고친다 | S3:44 | T-PR1 | rewarded → L1 | code | keep |
| F7 | 3 implement | P | matrix 행 자체가 모호하면 `matrix ambiguity`로 HALT blocked | S3:44 | T-OR2 | opposite → L1C | code | semantic (G4) |
| F8 | 3 implement | P | 그 밖에 감사를 만족시킬 수 없으면 `matrix test audit failed`로 HALT blocked | S3:44 | T-OR2 | rewarded → L1 | code | semantic (G9) |
| F9 | 4 review | E | patch 적용 후 `## Verification` 명령을 다시 실행한다 (마지막 수정 이후) | S4:83, S4:78 | T-AW3 | rewarded → L1 | code | keep |
| F10 | 4 review | P | patch 후 검증이 실패하고 고칠 수 없으면 `patch verification failed`로 HALT blocked | S4:83 | T-OR2 | rewarded → L1 | code | semantic (G8) |
| F11 | 4 review | E | patch 후 diff_file을 패치된 트리에 맞게 다시 쓴다 | S4:83 | T-AW3 | rewarded → L1 | code | env (G7) |
| F12 | 4 review | R | (patch 구현자) 편집한 파일을 덮는 테스트만 실행하고 더 넓게 돌리지 않는다; 전체 검증은 부모가 한다 | S4:78 | T-PR5 | opposite → L1C | code | semantic (G7) |
| G1 | 4 review | P | 리뷰 전에 spec frontmatter에서 baseline_revision을 읽는다; 없거나 NO_VCS면 최선으로 변경을 파악한다 | S4:15 | T-RD4 | rewarded → L1 | code | keep |
| G2 | 4 review | E | 리뷰 전에 diff_file을 baseline 이후 모든 변경(미추적 포함)의 unified diff로 다시 쓴다 | S4:15 | T-AW5 | rewarded → L1 | code | env (G7) |
| G3 | 4 review | R | 리뷰 레이어는 diff 파일을 읽는다; diff 본문을 프롬프트에 붙여 넣지 않는다 | S4:15, S4:23 | NEW-AW-subagent | none → L2F | code | drop (G7) |
| G4 | 4 review | P | claims_file = spec_file이며 edge-case 레이어에만 경로로 넘긴다; 그 레이어는 추적을 마친 뒤에만 읽고 다른 레이어는 보지 않는다 | S4:17, CT:81 | NEW-AW-subagent | none → L2F | code | semantic (G7) |
| G5 | 4 review | R | diff 스테이징에서 바꾸는 것은 diff_file뿐이다: `git add`를 하지 않는다 | S4:19 | T-PR6 | rewarded → L1 | code | keep |
| G6 | 4 review | P | verbatim_intent는 step-01에서 받은 호출 의도 원문이다 (기존 spec에서 시작했으면 그 `<intent-contract>` 블록) | S4:23, CT:109-111 | NEW-AW-subagent | none → L2F | code | semantic (G7) |
| G7 | 4 review | F | 레이어를 띄우기 전에 skill-root 자리표시자를 설치 디렉터리 절대경로로 바꾼다; 자식 프롬프트에 자리표시자를 남기지 않는다 | S4:23 | T-FM4 | rewarded → L1 | code | drop (G7) |
| G8 | 4 review | P | 건너뛰는 레이어를 먼저 알린 뒤, 활성 레이어 전부를 어느 결과도 처리하기 전에 동시에(블로킹, 같은 턴) 띄운다; 모두 띄운 뒤에야 수집·분류한다 | S4:25 | NEW-AW-subagent | none → L2F | code | semantic (G7) |
| G9 | 4 review | R | 리뷰어 서브에이전트에는 치환된 프롬프트 텍스트만 넘기고, 리뷰어 지시 파일을 부모가 직접 읽지 않는다 | S4:25 | T-RD3 | rewarded → L1 | code | semantic (G7) |
| G10 | 4 review | P | 서브에이전트를 띄우지 않는 커스텀 레이어 지시는 적힌 대로 실행한다 | S4:25 | null | none | none | drop (G7) |
| G11 | 4 review | P | 각 리뷰 레이어는 맥락 없는 서브에이전트(intent-alignment는 서브에이전트)를 주어진 프롬프트로 띄운다 | CT:58, CT:77, CT:93, CT:107 | NEW-AW-subagent | none → L2F | code | semantic (G7) |
| G12 | 4 review | R | (리뷰어) skill을 호출하거나 자기 서브에이전트를 띄우지 않고, 결과를 마지막 메시지의 텍스트로 돌려주며 호스트의 findings 보고 도구로 보내지 않는다 | CT:69, CT:85, CT:99, CT:117 | NEW-AW-subagent | none → L2F | code | drop (G7) |
| G13 | 4 review | P | (리뷰어) 지시 파일을 읽을 수 없으면 그 실패를 그대로 보고하고 멈춘다 | CT:85, CT:99 | T-OR2 | rewarded → L1 | code | drop (G7) |
| G14 | 4 review | Q | (Blind Hunter) diff를 리뷰하되 틀린 것만이 아니라 빠진 것을 찾는다 | CT:60-61, CT:67 | NEW-J-content | shown → L2M | judge | semantic (G7) |
| G15 | 4 review | F | (Blind Hunter) diff 파일 크기로 하한 N = min(floor(sqrt(kB)+1), 10)을 계산해 한 줄로 산식을 적고, 최소 N개 finding을 낸다 | CT:62 | T-FM3 | rewarded → L1 | code | semantic (G7) |
| G16 | 4 review | F | 리뷰어 출력에 severity·priority·ranking·confidence를 달지 않는다 (Blind Hunter 목록, Edge Case Hunter, Verification Gap 공통) | CT:63, EH:17, VG:17, VG:80 | T-FM2 | opposite → L1C | code | semantic (G7) |
| G17 | 4 review | P | (Blind Hunter) 내용이 비어 있으면 멈추고 그렇게 말한다; finding이 0개면 다시 점검하고 빈 목록으로 끝내지 않는다 | CT:64-65 | T-FM3 | rewarded → L1 | code | semantic (G7) |
| G18 | 4 review | P | (Edge Case Hunter) `{skill-root}/review-prompts/edge-case-hunter.md`를 끝까지 읽고 리뷰 지시로 따른다 | CT:79 | T-RD2 | rewarded → L1 | code | env (G5) |
| G19 | 4 review | R | (Edge Case Hunter) claims_file(spec)은 5단계 Claims Check 전에는 읽지 않는다: 경로 추적이 먼저 끝나야 한다 | CT:81, EH:13, CC:3 | T-RD3 | rewarded → L1 | code | semantic (G7) |
| G20 | 4 review | P | (리뷰어) 리뷰 대상은 띄운 메시지의 'Review content:'가 주는 diff 파일이다: 경로면 읽고, 지시 파일 자체는 대상이 아니다 | CT:83, CT:97, CT:113, EH:24, EH:112, VG:112 | T-RD4 | rewarded → L1 | code | keep |
| G21 | 4 review | Q | (Edge Case Hunter) 순수 경로 추적자로서 코드의 좋고 나쁨을 말하지 않고, 처리가 빠진 경로·조건만 나열한다; 처리된 것은 조용히 버린다 | EH:3, EH:17, EH:37-38 | NEW-J-content | none → L2F | judge | semantic (G7) |
| G22 | 4 review | R | (Edge Case Hunter) diff hunk만 훑고, 바뀐 줄에서 직접 닿는 경계 중 diff에 명시적 가드가 없는 것만 적는다; 나머지 코드베이스는 외부 함수를 참조할 때만 본다 | EH:4, EH:6 | T-RD5 | rewarded → L1 | code | semantic (G7) |
| G23 | 4 review | P | (Edge Case Hunter) diff가 없으면 주어진 내용 전체가 범위다 | EH:5 | null | none | none | drop (G7) |
| G24 | 4 review | P | (Edge Case Hunter) 1~6단계를 정확히 그 순서로 모두 실행한다; 정지 조건이 걸리면 그 지시를 그대로 따른다 | EH:15 | T-OR1 | rewarded → L1 | code | semantic (G7) |
| G25 | 4 review | F | (Edge Case Hunter) 내용이 없거나 비었거나 읽을 수 없으면 정해진 한 원소 JSON 배열(location N/A, 'Input empty or undecodable' …)을 돌려주고 멈춘다 | EH:25, EH:76 | T-FM2 | rewarded → L1 | code | drop (G7) |
| G26 | 4 review | Q | (Edge Case Hunter) 모든 분기 경로와 경계 조건을 기계적으로 전부 걷는다: 제어 흐름과 도메인 경계, 고정 집합의 암묵 분기(나머지 enum 값 등), 재확인이 있는 핸들 수명, 추가·변경된 모든 호출부의 인자 수·순서·타입·기본값(테스트 파일 포함) | EH:30-36, EH:42-43 | NEW-J-content | opposite → L1C | judge | semantic (G7) |
| G27 | 4 review | E | (Edge Case Hunter) 호출부를 점검할 때 피호출자의 선언을 실제로 읽는다 | EH:36 | T-RD5 | rewarded → L1 | code | keep |
| G28 | 4 review | P | (Edge Case Hunter) diff가 의미 있는 코드를 지우거나 바꿨으면(이름 변경·공백 제외) references/deletion-check.md를 읽고 따르고, 5단계에서 references/claims-check.md를 읽고 따른다 | EH:47, EH:51 | T-RD2 | rewarded → L1 | code | env (G5) |
| G29 | 4 review | F | (Edge Case Hunter) 출력은 유효한 JSON 배열 하나뿐이다: 추가 텍스트·설명·markdown 감싸기 없음; 아무것도 없으면 `[]` | EH:55, EH:60, EH:71 | T-FM8 | rewarded → L1 | code | semantic (G7) |
| G30 | 4 review | F | (Edge Case Hunter) finding마다 정확히 네 필드 location, trigger_condition, guard_snippet, potential_consequence가 있다 (deletion/claim finding은 kind, confidence 추가) | EH:60-68, EH:71, DC:7-10, CC:7-10 | T-FM6 | rewarded → L1 | code | semantic (G7) |
| G31 | 4 review | F | (Edge Case Hunter) 필드 형식: location은 file:start-end(또는 file:line, file:hunk), trigger_condition·potential_consequence는 15단어 이하, guard_snippet은 줄바꿈·비이스케이프 따옴표 없는 한 줄 문자열 | EH:64-67 | T-FM3 | rewarded → L1 | code | semantic (G7) |
| G32 | 4 review | Q | (Deletion Check) 지워지거나 바뀐 코드 덩어리마다 그것이 지닌 행동·계약이 재확립되지도 의도적으로 폐기되지도 않았는지 묻고, 회귀·고아 참조·새 dead code만 finding으로 추가한다; 이미 edge-case finding에 있는 것은 건너뛴다 | DC:3-5, DC:14, EH:80-82 | NEW-J-content | shown → L2M | judge | semantic (G7) |
| G33 | 4 review | F | (Deletion Check) deletion finding은 kind "deletion", confidence high\|medium\|low를 더하고, 표준 필드는 지워진 항목·그것이 강제하던 계약·재확립 방법·회귀로 읽는다 | DC:7-12, EH:84-89 | T-FM2 | rewarded → L1 | code | semantic (G7) |
| G34 | 4 review | P | (Claims Check) 경로 추적이 끝난 5단계에서 처음으로 claims 파일을 읽는다 | CC:3, EH:96 | T-RD4 | rewarded → L1 | code | semantic (G7) |
| G35 | 4 review | R | (Claims Check) spec에서 `## Intent`와 `## Tasks & Acceptance`만 읽고 나머지는 무시한다 | CC:5, EH:98 | null | none | none | drop (G7) |
| G36 | 4 review | Q | (Claims Check) spec은 증언이지 증거가 아니다(주석에 반복된 주장도 확인이 아님); 검증 가능한 주장(하는 것, 보존하는 것, 순서, 산술, 기존 코드와의 동등성)을 뽑아 추적한 코드로 반증을 시도하고, 부족하면 결정하는 코드를 더 읽는다; 검증된 주장은 아무것도 내지 않는다 | CC:5, CC:14, EH:98, EH:107 | NEW-J-content | shown → L2M | judge | semantic (G7) |
| G37 | 4 review | F | (Claims Check) 반증된 주장마다 finding 하나: kind "claim", confidence, location=모순 위치, trigger_condition=주장, guard_snippet=코드가 실제로 하는 일, potential_consequence=주장을 믿은 사람에게 생기는 문제 | CC:7-12, EH:100-105 | T-FM6 | rewarded → L1 | code | semantic (G7) |
| G38 | 4 review | P | (Verification Gap) `{skill-root}/review-prompts/verification-gap.md`를 끝까지 읽고 따른다 | CT:95 | T-RD2 | rewarded → L1 | code | env (G5) |
| G39 | 4 review | Q | (Verification Gap) 한 질문만 묻는다: 이 변경이 내야 할 행동이 실제 쓰이는 곳에서 깨지면 검증이 실패하는가; 정확성 버그를 사냥하지 않되 추적 중 본 진짜 문제는 보고한다 | VG:3, VG:76 | NEW-J-content | shown → L2M | judge | semantic (G7) |
| G40 | 4 review | E | (Verification Gap) 테스트가 무엇을 덮고 실행하고 단언하고 놓치는지 주장하기 전에 그 테스트를 읽는다; finding을 쓰기 직전에 근거 테스트·검색 결과를 다시 연다 | VG:13, VG:70 | T-RD4 | rewarded → L1 | code | keep |
| G41 | 4 review | A | (Verification Gap) 테스트가 없다고 주장하기 전에 대상 심볼과 import 참조로 저장소 전체를 검색한다; 예상 위치만으로는 부족하다 | VG:14, VG:16 | T-RF2 | rewarded → L1 | code | keep |
| G42 | 4 review | A | (Verification Gap) 확인하지 않은 것을 단언하지 않는다; 근거 없는 finding은 버린다; finding에 실제로 무엇을 어디까지 확인했는지 적는다 | VG:15-16, VG:70 | NEW-J-content | shown → L2M | judge | keep |
| G43 | 4 review | Q | (Verification Gap) 변경을 부분별로 선별한다: 반환값·예외·호출자 가시 부작용·관찰 가능 상태(반복 순서·메시지 포함)를 바꾸지 않는 부분만 비행동적으로 보고 건너뛴다; 정적 텍스트·LLM 출력은 건너뛴다; 의존성·툴체인·빌드/설정·데이터 파일 변경은 행동적으로 본다 | VG:23, VG:27, VG:35 | NEW-J-content | none → L2F | judge | semantic (G7) |
| G44 | 4 review | Q | (Verification Gap) 바뀐 행동마다 그것을 관찰하는 곳(직접 호출자, 등록 진입점, 계약 소비자)으로 추적한다; 도달 가능하고 미검증인 동안만 따라가고 1–3 hop의 가장 가까운 관찰 경계를 택하며, 비슷한 소비자가 5개를 넘으면 대표만 본다 | VG:33, VG:39, VG:41 | NEW-J-content | none → L2F | judge | semantic (G7) |
| G45 | 4 review | Q | (Verification Gap) 소비자마다 가장 작은 현실적 회귀(Demonstration)를 지명한다; 없으면 경로를 버린다 — 미검증 하류 코드 자체는 finding이 아니다; Missing-adoption은 대체 신호와 공유 계약이 있을 때만 성립한다 | VG:45, VG:47 | NEW-J-content | none → L2F | judge | semantic (G7) |
| G46 | 4 review | Q | (Verification Gap) 관련 테스트를 읽고 Demonstration이 단언을 실패시키는지 묻는다; 그렇다면 finding 없음; 경로를 도는 테스트가 없거나 skip/flaky/비정상 경로이거나 바뀐 결과를 확인하지 않으면 Regression 또는 Broken-verification gap; 적응을 단언하는 테스트가 없으면 Missing-adoption gap | VG:49-53 | NEW-J-content | none → L2F | judge | semantic (G7) |
| G47 | 4 review | Q | (Verification Gap) 테스트는 정상 실행되고 단언이 바뀐 출력·분기·계약을 관찰할 때만 인정한다; 미실행, 소스 텍스트 단언, 성공/no-throw/snapshot만 확인, mock/log 호출 확인, 사람만 하는 점검, 통합을 mock한 테스트, 확인 없이 통과하는 e2e, 오래된 단언은 인정하지 않는다 | VG:55 | NEW-J-content | none → L2F | judge | semantic (G7) |
| G48 | 4 review | Q | (Verification Gap) 보고하지 않는 것: 컴파일러·타입체커가 강제하는 경우, 통합·계약·e2e 테스트가 이미 검증한 행동, 구현 세부·mock 전용 테스트, 낮은 커버리지나 테스트 파일 부재 자체, 변경이 건드리지 않은 레거시 미테스트 코드 | VG:74 | NEW-J-content | none → L2F | judge | semantic (G7) |
| G49 | 4 review | F | (Verification Gap) gap finding마다 한 블록: `### 제목`, Changed surface(file:line), Impacted consumer or site(file:line, 구체적), Existing test evidence(gap 종류별), Missing verification, Demonstration, Consequence, Disposition 필드; 일반 조언 없음; 각 블록은 자체 증거로 선다 | VG:78-96 | T-FM6 | rewarded → L1 | code | semantic (G7) |
| G50 | 4 review | F | (Verification Gap) Disposition은 `patch`(추가할 테스트를 저장소 방식에 맞게 지명) 또는 `defer`(한 문장 이유) 중 하나다 | VG:96 | T-FM2 | rewarded → L1 | code | semantic (G9) |
| G51 | 4 review | F | (Verification Gap) gap이 아닌 진짜 문제는 `## Other findings` 아래 설명만 있는 불릿으로 적는다 | VG:76, VG:99-105 | T-FM3 | rewarded → L1 | code | semantic (G7) |
| G52 | 4 review | F | (Verification Gap) gap도 other finding도 없으면 정확히 `No verification gaps found.` 한 줄을 낸다 (빈 응답 금지) | VG:29, VG:107-109 | T-FM2 | rewarded → L1 | code | semantic (G7) |
| G53 | 4 review | A | (Verification Gap) 내용이 없거나 파일이 없거나 비었거나 읽을 수 없으면 그렇게 말하고 멈춘다; 읽지 못한 내용에 대해 깨끗한 리뷰를 보고하지 않는다 | VG:113 | T-RF2 | rewarded → L1 | code | keep |
| G54 | 4 review | Q | (Intent Alignment) 엄격히 기술적으로만 보고하고 추가 작업을 처방하지 않는다 | CT:115 | NEW-J-content | none → L2F | judge | semantic (G7) |
| G55 | 4 review | F | (Intent Alignment) 보고는 (1) 의도의 방어 가능한 해석들 열거, (2) diff가 구현한 해석, (3) 해석과 diff가 갈리는 곳 — 의도의 기대가 사는 표면 대 diff와 그 테스트가 행사하는 표면 — 세 부분이다 | CT:115 | T-FM2 | rewarded → L1 | judge | semantic (G7) |
| G56 | 4 review | P | 모든 레이어가 보고한 뒤에야, 중복 제거나 묶기 전에, finding마다 verdict를 낸다 | S4:31 | T-OR1 | rewarded → L1 | code | semantic (G7) |
| G57 | 4 review | R | 리뷰 서브에이전트가 매긴 severity는 무시한다 (맥락이 없어 등급을 못 매김) | S4:31 | null | none | enforced | drop (G7) |
| G58 | 4 review | P | Triage Log에 이미 행이 있으면(루프백·재개·후속) finding을 먼저 그 행과 대조한다: 같은 위치·같은 주장이고 코드가 행대로면 그 verdict·route를 유지해 증거 앞에 `carried`를 붙여 다시 쓰고, 검증·patch·defer를 반복하지 않는다 | S4:33 | T-TR1b | none → L2F | code | semantic (G8) |
| G59 | 4 review | P | verification-gap 레이어의 gap finding은 사전 검증된 것으로 받아 검증을 건너뛰고 제출된 증거로 verdict를 내며 라우팅 때 그 disposition을 참작한다; 그 레이어의 Other findings는 보통처럼 검증한다 | S4:36 | NEW-J-content | none → L2F | judge | semantic (G7) |
| G60 | 4 review | E | finding의 주장을 인용된 파일·줄에서 검증한다: 바뀐 줄 너머(호출자, 상류 가드)를 읽어 예/아니오를 낼 때까지 본다 | S4:37 | T-RD4 | rewarded → L1 | code | keep |
| G61 | 4 review | Q | 근처 코드에 대한 다른 finding이 이 finding을 결정하지 않는다; 수정안이 그럴듯한지가 아니라 문제가 실재하는지를 판단한다; 도달 가능함을 보이지 못한 상황에서 크게 실패하는 코드는 결함이 아니라 올바른 행동이다 | S4:37 | NEW-J-content | none → L2F | judge | keep |
| G62 | 4 review | F | finding마다 verdict는 정확히 하나, high \| medium \| low \| false \| maybe-false 중 하나다 (verdict가 triage 결정 전부; 별도 keep/dismiss 없음) | S4:38-41 | T-FM2 | rewarded → L1 | code | keep |
| G63 | 4 review | Q | high/medium/low는 실재하는 나쁜 결과에 대해 사용자·개발자 피해로 매긴다; 개발자 전용 문제는 어디서 탈이 날지 지명해야 하고, 피해를 못 대는 '지저분함'은 false/maybe-false로 한다; 피해는 실재하나 정도를 모르면 높은 등급을 고른다 | S4:39 | NEW-J-content | shown → L2M | judge | keep |
| G64 | 4 review | F | `false`에는 이 주장을 반증하는 내용을, `maybe-false`에는 알아내려면 무엇을 확인해야 하는지를 증거로 적는다; maybe-false는 diff와 주변 코드로 결정할 수 없을 때만 쓴다 | S4:40-41, S4:67 | T-FM6 | rewarded → L1 | judge | keep |
| G65 | 4 review | C | 모든 finding은 triage log에 행 하나를 갖는다: 하나도 버리거나 합치거나 조용히 건너뛰지 않는다; `<total>`은 레이어가 보고한 finding 수와 같다 | S4:43, S4:69 | T-TR1 | rewarded → L1 | code | semantic (G7) |
| G66 | 4 review | C | `false` finding은 반증을 근거로 reject한다 (verdict false ↔ route reject) | S4:45 | NEW-FM-internal | none → L2F | code | keep |
| G67 | 4 review | Q | `low` finding은 일상 사용에서 만나기 어렵고 수정이 직접 교정·삭제 이상(가드·분기·매개변수·복잡도 추가)이면 reject한다 | S4:47 | NEW-J-content | none → L2F | judge | keep |
| G68 | 4 review | Q | 범위 밖 판단은 의도 자체가 배제할 때만 한다; spec의 범위 절·계획·diff 모양만 배제하면 finding을 남겨 intent_gap/bad_spec으로 보내고 patch/defer로 보내지 않는다 | S4:49 | NEW-J-content | none → L2F | judge | keep |
| G69 | 4 review | R | 수정이 이 빌드의 spec을 고치는 것인 finding은 reject한다 | S4:51 | NEW-J-content | none → L2F | judge | keep |
| G70 | 4 review | Q | 살아남은 finding을 같은 결함이 만든 것끼리만 묶는다 (같은 위치나 같은 수정만으로는 안 됨); 묶음은 모든 구성원의 나쁜 결과와 최고 verdict(high>medium>low>maybe-false)를 지닌다 | S4:55 | NEW-J-content | none → L2F | judge | keep |
| G71 | 4 review | F | 묶음마다 intent_gap \| bad_spec \| patch \| defer 중 정확히 하나로 라우팅한다; 검증된 high/medium/low 구성원이 있으면 그 최고 verdict로 라우팅하고 maybe-false 구성원 때문에 defer하지 않는다 | S4:56 | T-FM2 | rewarded → L1 | code | keep |
| G72 | 4 review | Q | intent_gap: 변경이 야기했고 captured intent가 불완전해 spec으로 풀 수 없는 것; 가능한 해석이 정확히 하나일 때 외에는 의도를 추론하지 않는다 | S4:57 | NEW-J-content | opposite → L1C | judge | semantic (G4) |
| G73 | 4 review | Q | bad_spec: 변경이 야기했고(spec 이탈 포함) spec이 충분히 명확했어야 하는 것; bad_spec과 patch 사이에서 망설이면 bad_spec을 택한다 | S4:58 | NEW-J-content | shown → L2M | judge | semantic (G8) |
| G74 | 4 review | Q | patch: 변경이 야기했고 최소 수정이 사소하며 공개 표면을 늘리지 않고 입증하지 않은 상태를 가드하지 않는 것; 하나라도 어기면 spec이 그 수정을 정하지 않을 때 intent_gap, 정하면 bad_spec | S4:59 | NEW-J-content | none → L2F | judge | keep |
| G75 | 4 review | Q | defer: 이 스토리가 만들지 않은 기존 문제; 또는 구성원이 모두 maybe-false이고 참이면 medium/high인 것(미검증 표시한 severity와 해결 조건 기록; low면 같은 메모로 reject); 또는 수정이 agent 맥락 파일(CLAUDE.md, AGENTS.md, rules)을 고치는 것 | S4:60 | NEW-J-content | shown → L2M | judge | keep |
| G76 | 4 review | F | `## Review Triage Log`에 새 항목을 붙인다: `### {date} — Review pass` 제목, `- verdicts: <total> findings — high <N>, medium <N>, low <N>, false <N>, maybe-false <N>` 줄, `- findings:` 목록 | S4:62-68 | T-FM2 | rewarded → L1 | code | keep |
| G77 | 4 review | F | finding 행은 `` `[verdict]` `[intent_gap\|bad_spec\|patch\|defer\|reject]` <요약> — <증거> `` 형식이다 (false의 반증, maybe-false의 해결 조건, patch의 조치, reject된 low의 이유) | S4:67 | T-FM3 | rewarded → L1 | code | keep |
| G78 | 4 review | F | Triage Log 항목의 {date}는 현재 시스템 날짜다 | S4:69 | T-FM2 | rewarded → L1 | code | keep |
| G79 | 4 review | A | 행은 레이어가 보고한 순서대로 모든 레이어의 finding마다 하나다 | S4:69 | T-RF1 | rewarded → L1 | code | semantic (G7) |
| G80 | 4 review | C | `<total>`은 행 수와 같고 다섯 verdict 수의 합과 같다; 묶인 항목의 구성원도 각자 행을 가지며 route를 공유한다 | S4:69 | NEW-FM-internal | none → L2F | code | keep |
| G81 | 4 review | P | 항목을 폭포식으로 처리한다: intent_gap이 있으면 나머지는 무의미, bad_spec이 있으면 코드가 재도출되므로 나머지는 무의미, 둘 다 없으면 patch와 defer를 처리한다 | S4:70 | T-OR2 | rewarded → L1 | code | semantic (G8) |
| G82 | 4 review | A | bad_spec 루프백 전에 frontmatter `review_loop_iteration`(없으면 0)을 읽어 1 올려 쓴다 (값 = 지금까지의 루프백 수) | S4:70 | T-RF1 | rewarded → L1 | code | semantic (G8) |
| G83 | 4 review | P | review_loop_iteration이 5를 넘으면 이번 패스의 triage 항목을 붙인 뒤 `review repair loop exceeded 5 iterations (non-convergence)`로 HALT blocked | S4:70 | T-OR2 | rewarded → L1 | code | semantic (G8) |
| G84a | 4 review | F | intent_gap: 시도한 변경을 `{{.implementation_artifacts}}`에 patch 파일로 저장하고 triage 항목에서 참조한다 | S4:71 | T-FM1 | rewarded → L1 | code | env (G5) |
| G84b | 4 review | E | intent_gap: 코드 변경을 되돌린다 (작업 트리를 baseline으로) | S4:71 | NEW-WD-revert | none → L2F | code | drop (G8) |
| G84c | 4 review | P | intent_gap: 이번 패스의 triage 항목을 붙인 뒤 미해결 질문과 patch 경로를 포함해 `intent gap`으로 HALT blocked | S4:71 | T-OR2 | opposite → L1C | code | semantic (G4) |
| G85a | 4 review | P | bad_spec: 되돌리기 전에 KEEP 지시(잘 된 것, 재도출에서 살아남아야 할 것)를 뽑아 둔다 | S4:72 | NEW-J-content | none → L2F | judge | semantic (G8) |
| G85b | 4 review | E | bad_spec: 코드 변경을 되돌린다 | S4:72 | NEW-WD-revert | none → L2F | code | drop (G8) |
| G85c | 4 review | P | bad_spec: `## Spec Change Log`을 읽고 기록된 제약을 엄격히 지키며 `<intent-contract>` 밖의 근본 원인 절만 고친다 | S4:72 | T-RD4 | rewarded → L1 | code | semantic (G8) |
| G85d | 4 review | F | bad_spec: change-log 항목을 붙인다 — 촉발 finding, 고친 것, 피한 known-bad 상태, KEEP 지시 | S4:72, ST:68-71 | T-FM6 | rewarded → L1 | code | semantic (G8) |
| G85e | 4 review | F | bad_spec: 이번 패스의 triage 항목을 붙이고 각 bad_spec 행에 그것이 촉발한 수정을 적는다 | S4:72 | T-FM6 | rewarded → L1 | code | semantic (G8) |
| G85f | 4 review | P | bad_spec: step-03을 다시 읽고 따라 코드를 재도출한 뒤 step-04가 다시 돈다 (루프백) | S4:72 | T-OR2 | rewarded → L1 | code | semantic (G8) |
| G86a | 4 review | P | patch: step-03의 같은 구현 서브에이전트를 이름/id로 재호출한다 (새로 띄우면 재호출이 아님) | S4:73 | NEW-AW-subagent | none → L2F | code | drop (G7) |
| G86b | 4 review | F | patch: 정해진 메시지 한 통을 보낸다 — 'Review of your implementation found problems. Fix each one below with the smallest change ...' 와 `- <file> — <what is wrong> — <what the smallest fix must do>` 행 | S4:73-81 | NEW-AW-subagent | none → L2F | code | drop (G7) |
| G86c | 4 review | P | patch: 서브에이전트를 이어 쓸 수 없으면 patch를 직접 적용한다 | S4:83 | T-OR2 | rewarded → L1 | code | semantic (G7) |
| G86d | 4 review | F | patch: 이번 패스의 triage 항목을 붙이고 patch된 각 행에 적용한 수정을 적는다 | S4:83 | T-FM6 | rewarded → L1 | code | keep |
| G87a | 4 review | F | defer: frontmatter의 `deferred` 키는 하나뿐인 리스트다 — 없으면 빈 리스트로 한 번 추가, `[]`면 첫 항목으로 대체, 있으면 뒤에 붙임; 두 번째 `deferred:` 키를 만들지 않는다 | S4:84, ST:10 | T-FM5 | none → L2F | code | keep |
| G87b | 4 review | R | defer: 기존 deferred 항목을 모두 보존하고(중복 검사 없이) 새 항목만 뒤에 붙인다 | S4:84 | T-WD4 | rewarded → L1 | code | keep |
| G87c | 4 review | F | defer: 자유 서술 값은 YAML block scalar로 직렬화해 `:`, `#`, 따옴표, 줄바꿈이 데이터로 남게 한다 | S4:84 | T-FM8 | rewarded → L1 | code | keep |
| G87d | 4 review | F | defer: 항목마다 summary(>-, 한 문장), evidence(\|-), 선택 location(file:line/component), 선택 severity(high\|medium\|low; maybe-false는 if-true 등급 + " (unverified)") | S4:85-93 | T-FM6 | rewarded → L1 | code | keep |
| G87e | 4 review | P | defer: 모두 붙인 뒤 frontmatter 전체를 YAML로 파싱해 `deferred`가 기존+새 항목을 모두 담은 하나의 리스트인지 확인하고 직렬화 오류를 고친다 | S4:95 | NEW-WD-exists-after | none → L2F | code | keep |
| H1 | HALT | F | `## Auto Run Result`에 여섯 가지를 쓴다: 구현 요약, 바뀐 파일과 한 줄 설명, 리뷰 finding 내역(적용한 patch, defer한 것, reject한 finding 전부와 이유), 후속 리뷰 권고, 수행한 검증(명령 결과·수동 점검 메모), 잔여 위험 | S4:99-105 | T-FM2 | rewarded → L1 | code | keep |
| H2 | HALT | A | Auto Run Result의 '바뀐 파일' 목록은 최종 diff의 파일 집합과 같다 | S4:101 | T-RF3 | shown → L2M | code | keep |
| H3 | HALT | C | Auto Run Result의 finding 내역(patch/defer/reject 수와 reject 이유)은 Review Triage Log의 행과 일치한다 | S4:102 | NEW-FM-internal | none → L2F | code | keep |
| H4 | HALT | C | 후속 리뷰 권고는 기본 false; 이번 패스의 patch 항목만 항목 verdict로 센다(defer·false 제외); 첫 패스는 high patch가 있거나 medium patch가 둘 이상이면 true, 후속 패스는 high patch가 있을 때만 true; true면 구체적 미검증 위험을 지명하고 못 하면 false; verdict별 patch 수를 적는다 | S4:103 | NEW-FM-internal | none → L2F | code | env (G8) |
| H5 | HALT | C | frontmatter `followup_review_recommended`는 H4의 계산값과 같다 | S4:107, ST:7 | NEW-FM-internal | none → L2F | code | keep |
| H6 | HALT | A | '수행한 검증'에 적은 명령과 결과는 실제 실행과 일치한다 | S4:104 | T-RF1 | rewarded → L1 | code | keep |
| H7 | HALT | E | VCS가 있으면 status done을 쓴 뒤 미커밋 상태인 리뷰된 diff 파일을 모두(추적 중이면 spec도) 로컬 커밋한다; 이번 실행의 기존 커밋은 유지한다 | S4:111-113 | T-AW5 | none → L2F | code | drop (G7) |
| H8 | HALT | A | 리뷰된 diff 파일 전부가 baseline 이후 변경 집합에 있고 미커밋으로 남은 것이 없음을 확인한다 | S4:113 | T-RF3 | shown → L2M | code | drop (G7) |
| H9 | HALT | R | push하지 않는다 | S4:113 | T-PR6 | rewarded → L1 | code | drop (G6) |
| H10 | HALT | P | 커밋 후 작업 사본이 깨끗한지 확인하고, 아니면 `finalization left repository dirty`로 HALT blocked | S4:114 | T-PR2 | rewarded → L1 | code | drop (G7) |
| H11 | HALT | F | spec_file을 모르거나 없을 때는 `{{.implementation_artifacts}}/bmad-build-auto-result-<slug-or-timestamp>.md`를 만든다 | WF:32 | T-FM1 | rewarded → L1 | code | env (G5) |
| H12 | HALT | F | 결과 파일(또는 folder+id의 골격 story spec)은 frontmatter `status: <final status>`, `# BMad Build Auto Result`(또는 `# <entry title>`), `## Auto Run Result`, `Status:` 줄, `Blocking condition:` 줄로 이루어진다 | WF:18-29, WF:33-42 | T-FM2 | rewarded → L1 | code | keep |
| H13 | HALT | F | folder+id HALT: 쓰기 되돌림은 항상 id 키 story spec에 간다 — 미해결 항목이면 `{story_id}-unresolved.md`, 모호한 일치면 `{story_id}-ambiguous.md`, 그 외 `{story_id}-{slug}.md`; IA fallback은 쓰지 않는다 | WF:11-15 | T-FM1 | rewarded → L1 | code | drop (G1) |
| H14 | HALT | P | 결과를 쓴 뒤 On Complete를 따르고(기본 빈 값) workflow를 멈춘다: 마지막 결과 쓰기 뒤에 다른 행동이 없다 | WF:43, WF:47-49, CT:29-32 | T-OR1 | rewarded → L1 | code | env (G8) |
| H15 | 0 전역 | P | 턴을 끝내는 유일한 허용 방식은 명시적 최종 status를 쓰는 HALT 프로토콜이다 (알림 대기나 질문으로 끝내지 않음) | WF:55, WF:9 | T-SR2 | shown → L2M | code | env (G8) |
| I1 | 0 전역 | P | 단계가 서브에이전트를 지시하면 반드시 쓴다 | WF:53 | NEW-AW-subagent | none → L2F | code | drop (G7) |
| I2 | 0 전역 | P | 서브에이전트를 쓸 수 없으면 `no subagents`로 HALT blocked | WF:53 | T-OR2 | rewarded → L1 | code | drop (G7) |
| I3 | 0 전역 | P | 한 단계가 요구하는 서브에이전트는 모두 한 메시지에서 블로킹 호출로 함께 띄우고 결과를 모두 기다린 뒤 계속한다; 한 단계의 호출을 여러 메시지로 나누지 않는다 | WF:55 | NEW-AW-subagent | none → L2F | code | drop (G7) |
| I4 | 0 전역 | R | 서브에이전트를 백그라운드·분리·비동기로 돌리지 않고(`run_in_background: true` 금지) 완료 알림을 기다리려고 턴을 끝내지 않는다 | WF:55, S3:30, S4:25 | NEW-AW-subagent | none → L2F | code | drop (G7) |
| I5 | 4 review | P | 리뷰 서브에이전트는 모두 현재 세션과 같은 모델 능력으로 돌린다 | S4:7 | null | none | none | drop (G7) |
| J1 | 1 clarify | P | (epic 컴파일) epics 파일을 읽어 대상 epic의 제목·목표·스토리 목록을 뽑고, planning 디렉터리의 표준 파일(PRD, architecture, UX, brief)을 훑는다 | CE:8-9 | T-RD4 | rewarded → L1 | code | drop (G3) |
| J2 | 1 clarify | Q | (epic 컴파일) 이 epic에 관련된 정보만 뽑는다; 공격적으로 범위를 줄이고 의심스러우면 뺀다; 스토리 수준 세부와 코드베이스에서 알 수 있는 것은 쓰지 않는다 | CE:10, CE:50, CE:53-54 | NEW-J-content | none → L2F | judge | drop (G3) |
| J3 | 1 clarify | F | (epic 컴파일) 정확히 지정된 출력 경로 `IA/epic-<N>-context.md`에 쓴다 | CE:11, S1:59 | T-FM1 | rewarded → L1 | code | drop (G3) |
| J4 | 1 clarify | F | (epic 컴파일) 제목은 `# Epic {N} Context: {Epic Title}`, 생성 주석, 그리고 ## Goal, ## Stories, ## Requirements & Constraints, ## Technical Decisions, ## UX & Interaction Patterns, ## Cross-Story Dependencies 순이다 | CE:15-46 | T-FM2 | rewarded → L1 | code | drop (G3) |
| J5 | 1 clarify | F | (epic 컴파일) Stories는 `- Story X.Y: Brief title only` 형식이다 | CE:28 | T-FM3 | rewarded → L1 | code | drop (G3) |
| J6 | 1 clarify | Q | (epic 컴파일) 출처가 아니라 목적으로 기술한다; 원문·절 번호·큰 블록을 그대로 옮기지 않고 늘 요약한다 | CE:51-52 | NEW-J-content | none → L2F | judge | drop (G3) |
| J7 | 1 clarify | F | (epic 컴파일) 전체 800–1500 토큰을 목표로 한다 | CE:55 | T-FM3 | rewarded → L1 | code | drop (G3) |
| J8 | 1 clarify | Q | (epic 컴파일) 내용을 지어내지 않는다: 출처에 없으면 쓰지 않는다 | CE:56, CE:62 | NEW-J-content | none → L2F | judge | drop (G3) |
| J9 | 1 clarify | F | (epic 컴파일) 빈 섹션은 통째로 생략한다; Goal과 Stories는 항상 있다 | CE:57 | T-FM7 | rewarded → L1 | code | drop (G3) |
| J10 | 1 clarify | P | (epic 컴파일) epics 파일이 없거나 epic을 못 찾으면 아무것도 쓰지 않고 호출한 에이전트에 문제를 보고한다 | CE:61 | T-OR2 | rewarded → L1 | code | drop (G3) |
| J11 | 1 clarify | F | (epic 컴파일) planning 산출물이 없거나 비면 Goal·Stories만 채운 파일을 만들고 Requirements & Constraints에 정확히 "Planning artifacts were unavailable; only epics-file context was used."를 쓴다 | CE:62 | T-FM2 | rewarded → L1 | code | drop (G3) |

## 3. 기술 × 템플릿 분포

`여기` = 이 목록에서 그 템플릿을 받은 규칙 수. AOS/OSF/SKB/AID는 `if/01_template_layer.md` 2절 표(2026-10-22, 채점 항목 수)를 그대로 옮겼고(`*`·`(order)` 표기 포함), 표에 없는 템플릿은 `—`로 두고 ifeval constraints의 구현 항목 수를 AID 칸에 `ifeval n`으로 적었다. 분포도 01의 라벨을 옮겼다; 01에 없는 것만 여기서 정했다. 01 표는 constraints.yaml의 지금 상태와 조금 다르다(예: T-TR1은 지금 AOS 1·OSF 2, T-RF2는 AOS 1, T-OR1은 AOS 12 — 7절·8절에서 언급).

| 기술 | 템플릿 | 내용 | 여기 | AOS | OSF | SKB | AID | 분포 |
|---|---|---|---|---|---|---|---|---|
| S1 문서 따르기 | T-RD1 | read the core document first | 1 | 1 | 1 | 1 | 1 | 학습·평가 공통 |
|  | T-RD2 | read a stage's document when the stage starts | 8 | 4 | 5 | 7 | 5* | 학습·평가 공통 |
|  | T-RD3 | do not read a later stage's document early | 3 | (order) | (order) | (order) | 5* | 학습·평가 공통 |
|  | T-RD4 | read an earlier artifact or a recorded input inside a window | 18 | 6 | 5 | 6 | 1 | 학습·평가 공통 |
|  | T-RD5 | read specific repository files | 5 | 7 | — | — | — | 학습 AOS 고유 |
| S2 단계 순서 | T-OR1 | chain of stage-document reads and artifact writes in order | 8 | 1 | 1 | 3 | 1 | 학습·평가 공통 |
|  | T-OR2 | branch on a result | 27 | — | 1 | 1 | — | 학습 OSF+SKB |
|  | T-OR3 | never return to an earlier stage (no earlier stage document read again once a later one was) | 1 | — | — | — | ifeval 1 | AI-DLC 고유 (ifeval, L1C) |
| S3 행동 허용 구간 | T-AW1 | no repository edit outside the allowed stage | 2 | 4 | 4 | 7 | 1 | 학습·평가 공통 |
|  | T-AW3 | run tests/checks after the last source edit | 3 | 1 | 1 | 10 | 4 | 학습·평가 공통 |
|  | T-AW5 | run (or not) a CLI command inside a window | 5 | — | 22 | — | — | 학습 OSF 고유 |
|  | NEW-AW-subagent | a delegation call (subagent launch) required or forbidden inside a window, with its launch parameters | 17 | — | — | — | — | **이 workflow 고유** |
| S4 금지 대상 | T-PR1 | no test file added or modified | 1 | 1 | 1 | 1 | 1 | 학습·평가 공통 |
|  | T-PR2 | no working file left in the repository | 1 | 2 | 2 | 2 | 1 | 학습·평가 공통 |
|  | T-PR5 | no full test suite run | 1 | 1 | — | — | 1 | 학습(AOS)·평가 |
|  | T-PR6 | a specific command is prohibited | 3 | — | 1 | — | — | 학습 OSF 고유 |
| S5 산출물 쓰기 규율 | T-WD3 | write artifacts and scripts only at designated locations | 3 | 6 | 5 | 1 | — | 학습 공통 |
|  | T-WD4 | do not edit a finished file (checkbox exception) | 4 | 4 | — | 3 | — | 학습 AOS+SKB |
|  | NEW-WD-exists-after | check an artifact exists after writing it | 4 | — | — | — | — | **이 workflow 고유** (카탈로그 후보, 구현 항목 없음) |
|  | NEW-WD-exists-before | check whether a file exists before writing it | 2 | — | — | — | — | **이 workflow 고유** (카탈로그 후보, 구현 항목 없음) |
|  | NEW-WD-revert | after a decision the working tree is restored to the baseline (the attempt is saved elsewhere) | 2 | — | — | — | — | **이 workflow 고유** |
| S6 기록의 사실성 | T-RF1 | a recorded command/result/test equals what was run or read | 6 | 6 | 1 | 24 | 9 | 학습·평가 공통 |
|  | T-RF2 | a recorded 'none/no' claim is not refuted by the run | 2 | — | — | — | 4 | AI-DLC 고유 |
|  | T-RF3 | the recorded list of changed files against the files actually changed | 2 | — | — | 3 | 5 | 학습(SKB)·평가 |
|  | T-RF4 | recorded paths exist in the base repository | 2 | 2 | — | — | 9 | 학습(AOS)·평가 |
| S8 산출물 간 추적 | T-TR1 | ID coverage between artifacts (set relation) | 3 | — | — | — | 7 | AI-DLC 고유 |
|  | T-TR1b | keyed per-element mapping between artifacts | 1 | — | — | — | ifeval 1 | AI-DLC 고유 (ifeval, L2F) |
|  | T-TR2 | the planned or recorded target is what was executed (plan adherence) | 1 | — | — | — | 3 | AI-DLC 고유 |
| S9 질문 대신 스스로 결정 | T-SR2 | do not ask the user: no question file, no request for input | 2 | — | — | — | ifeval 2 | AI-DLC 고유 (ifeval, L2M) |
| S10 산출물 형식 | T-FM1 | artifact exists at its path | 8 | 12 | 6 | 7 | 10 | 학습·평가 공통 |
|  | T-FM2 | skeleton: headings, labels, fields present and filled, allowed values | 33 | 49 | 26 | 117 | 82 | 학습·평가 공통 |
|  | T-FM3 | repeated-item format (numbering, count, uniqueness) | 13 | 27 | 19 | 82 | 16 | 학습·평가 공통 |
|  | T-FM4 | no template placeholder residue | 3 | 10 | 14 | 14 | 5 | 학습·평가 공통 |
|  | T-FM5 | frontmatter keys fixed | 2 | — | — | — | 5 | AI-DLC 고유 |
|  | T-FM6 | every block of a repeated structure has its fields | 9 | — | — | — | 4 | AI-DLC 고유 |
|  | T-FM7 | heading set within an allowed list | 2 | 2 | — | — | — | 학습 AOS 고유 |
|  | T-FM8 | domain format rules (OpenSpec delta and spec grammar | 2 | 4 | 21 | 1 | — | 학습 (workflow별 형식) |
|  | NEW-FM-internal | artifact-internal consistency — a field equals a value derived from other parts of the same artifact | 6 | — | — | — | — | **이 workflow 고유** |
|  | NEW-FM-language | artifact (or message) language equals the configured language | 2 | — | — | — | — | **이 workflow 고유** |
| J 내용 판단 (judge 축) | NEW-J-content | content judged by an LLM judge over the artifact and the issue/diff (outside S1-S10) | 44 | — | — | — | — | **이 workflow 고유** |
| | | **합계** | 262 | | | | | |

분포 요약(규칙 수): 학습·평가 공통 108, 이 workflow 고유 77, 학습 일부/평가 일부 56, AI-DLC 고유 21. 서로 다른 템플릿 40개 중 카탈로그의 T-* 33개, 카탈로그 후보 NEW 2개, 이 목록에서 만든 NEW 5개. 01 표의 41개 중 여기 나타난 것은 30개; 나타나지 않은 것: T-AW2, T-AW4, T-AW6, T-AW7, T-PR3, T-PR4, T-WD1, T-WD2, T-PG1, T-PG2, T-SR1.

## 4. 새 템플릿 후보

yaml 끝 `new_templates:`의 정의를 옮긴다. 상태는 모두 candidate(구현 항목 없음). 카탈로그에 이미 후보로 있는 `NEW-WD-exists-before`(C17, C28)·`NEW-WD-exists-after`(C19, C30, D25, G87e)는 그대로 썼다.

- **NEW-J-content** (J, 44개: C22, C25, D5a, D14, D16, D18, D19, D30, D35, D37, D41, D43, D46, D48, E16, G14, G21, G26, G32, G36, G39, G42, G43, G44, G45, G46, G47, G48, G54, G59, G61, G63, G67, G68, G69, G70, G72, G73, G74, G75, G85a, J2, J6, J8)
  - 이름: content judged by an LLM judge over the artifact and the issue/diff (outside S1-S10)
  - 비교: issue-artifact or artifact-diff or artifact-internal, form judgement; the judge sees the artifact, the issue and the diff, not the trajectory
  - 가장 가까운 기존 템플릿과 차이: none in the catalogue; 10_handover 2.5 keeps judge items outside S1-S10 and reports them on a separate axis (J); defined here so every judge-checkable rule carries a template id
- **NEW-AW-subagent** (S3, 17개: C18, D4, E3, E4, E6, E10, G3, G4, G6, G8, G11, G12, G86a, G86b, I1, I3, I4)
  - 이름: a delegation call (subagent launch) required or forbidden inside a window, with its launch parameters
  - 비교: trace vs document — the tool call that launches a child agent, its count per message, blocking/background flag and prompt text, inside the stage window
  - 가장 가까운 기존 템플릿과 차이: T-AW5 (run a CLI command inside a window); differs in the compared object (a child-agent call with a prescribed prompt, not a shell command) and in the parameters judged (one message, blocking, prompt verbatim)
- **NEW-FM-internal** (S10, 6개: D22, G66, G80, H3, H4, H5)
  - 이름: artifact-internal consistency — a field equals a value derived from other parts of the same artifact
  - 비교: artifact-internal, form equal/count/keyed — e.g. `<total>` equals the row count, `followup_review_recommended` equals the triage-derived value, verdict false implies route reject, `oversized` present iff the body exceeds 1600 tokens
  - 가장 가까운 기존 템플릿과 차이: T-FM3 (count against a fixed number) and T-RF1 (record against the run); differs because both sides are inside the artifact (09 named it '산출물 내부 일관성')
- **NEW-FM-language** (S10, 2개: B1, B2)
  - 이름: artifact (or message) language equals the configured language
  - 비교: artifact-internal, form equal — language detection over the whole text
  - 가장 가까운 기존 템플릿과 차이: T-FM2 (allowed values of a field); differs because it is a property of the whole text, not of a field
- **NEW-WD-revert** (S5, 2개: G84b, G85b)
  - 이름: after a decision the working tree is restored to the baseline (the attempt is saved elsewhere)
  - 비교: artifact-diff, form equal — the repository state after the revert equals the baseline revision; the saved patch file equals the discarded diff
  - 가장 가까운 기존 템플릿과 차이: T-AW1 (no repository edit outside the allowed stage); differs because it compares an end state with the baseline rather than forbidding edit events

## 5. 학습과 반대 방향 (L1C 후보)

| id | 규칙 | template | 학습 쪽 근거 |
|---|---|---|---|
| C2 | EARLY EXIT 뒤에는 나중 단계가 명시적으로 되돌리라고 할 때만 step-01로 돌아온다 | T-OR3 | SKB rewards reading 02-fix.md again each round (order round_2/round_3); OSF lets apply send the run back to ff (templates.yaml T-OR3 reason) |
| C12 | 프롬프트만으로 무엇을 구현할지 알 수 없으면 `unclear intent`로 HALT blocked | T-OR2 | training rewards assuming and continuing: agentos_v2.shape_spec.requirements.agentos_v2_requirements.answers, openspec_ff.explore.run.openspec_ff_note.summary (T-SR1); SKB CW:38-40 'take the most plausible reading, record it in the current report, and continue' |
| C23 | 의도를 확정할 수 없으면 미해결 질문을 차단 조건으로 HALT blocked | T-OR2 | as C12 (T-SR1 items; SKB CW:38-40, AOS CW:70) |
| D20 | intent gap(의도로 고를 수 없고 관찰 가능한 결과가 다른 복수 해석)이 있으면 하나를 골라 해소하지 않고 `intent gap`으로 HALT blocked, 미답 질문과 수집한 증거를 포함한다 | T-OR2 | T-SR1 rewarded (agentos_v2.shape_spec.requirements.agentos_v2_requirements.answers; openspec_ff.explore.run.openspec_ff_note.summary); SKB CW:38-40 and AOS CW:70 instruct picking the most plausible reading and recording it |
| D40 | 비어 있는 섹션에 "N/A"나 "None"을 쓰지 않는다 (섹션을 지운다) | T-FM2 | training requires a none literal in empty fields: SKB FX:55 'Previous verification: none \| ./test.md', FX:90 '<Empty if none. ...>', AOS IT:279 'note "None" if all complete', IT:306 'None - all tests passing' (agentos_v2.implement_tasks.final_verification.agentos_v2_report.incomplete_listed, T-RF2; SKB field_filled none_allowed items) |
| D42 | I/O Matrix가 있으면 그 edge case를 단위 테스트하는 task를 포함한다 | T-TR1 | training forbids test files: agentos_v2.global.run.prohibited_action.test_file_write (CW:84-85), openspec_ff ... test_file_write (CW:79), speckit_bug ... test_file_write (CW:53, FX:36); AOS CT:382-384 'Do NOT test edge cases' |
| F7 | matrix 행 자체가 모호하면 `matrix ambiguity`로 HALT blocked | T-OR2 | as C12 (training assumes and records, T-SR1) |
| F12 | (patch 구현자) 편집한 파일을 덮는 테스트만 실행하고 더 넓게 돌리지 않는다; 전체 검증은 부모가 한다 | T-PR5 | agentos_v2.implement_tasks.run.agentos_v2_verify.whole_suite 'run the entire tests suite so that ALL tests run' (IT:237-239, must); the same direction is rewarded in phase 2 (agentos_v2.implement_tasks.run.prohibited_action.full_suite_phase2, IT:39) and SKB FX:41 'run the tests that exercise the changed paths' |
| G16 | 리뷰어 출력에 severity·priority·ranking·confidence를 달지 않는다 (Blind Hunter 목록, Edge Case Hunter, Verification Gap 공통) | T-FM2 | SKB AS:40 requires a severity per finding (critical\|high\|medium\|low with rationale) |
| G26 | (Edge Case Hunter) 모든 분기 경로와 경계 조건을 기계적으로 전부 걷는다: 제어 흐름과 도메인 경계, 고정 집합의 암묵 분기(나머지 enum 값 등), 재확인이 있는 핸들 수명, 추가·변경된 모든 호출부의 인자 수·순서·타입·기본값(테스트 파일 포함) | NEW-J-content | AOS CT:382-384 / IT:206-208 'Defer Edge Case Testing: Do NOT test edge cases, error states, or validation logic unless business-critical' (a test rule, not a review rule; direction differs) |
| G72 | intent_gap: 변경이 야기했고 captured intent가 불완전해 spec으로 풀 수 없는 것; 가능한 해석이 정확히 하나일 때 외에는 의도를 추론하지 않는다 | NEW-J-content | training rewards inferring and recording the most plausible reading (T-SR1 items; SKB CW:38-40) |
| G84c | intent_gap: 이번 패스의 triage 항목을 붙인 뒤 미해결 질문과 patch 경로를 포함해 `intent gap`으로 HALT blocked | T-OR2 | as D20 (T-SR1) |

묶으면 세 갈래다. (1) **intent gap → blocked**(C12, C23, D20, F7, G72, G84c): 상류는 해석이 갈리면 고르지 말고 멈추라 하고, 학습은 가장 그럴듯한 해석을 골라 기록하고 계속하라고 보상한다(T-SR1). (2) **테스트 추가**(D42; G50의 `patch — name the test to add`도 같은 방향): matrix edge case를 단위 테스트하라는 지시는 세 학습 workflow의 `test_file_write` 금지와 정면으로 반대다. (3) **표기**: 빈 섹션에 `None`을 쓰지 말고 지우라(D40) vs 학습의 `none` 리터럴 요구; 리뷰어는 severity를 달지 말라(G16) vs SKB의 severity 필수; 편집한 파일을 덮는 테스트만 돌려라(F12) vs AOS 검증 단계의 전체 suite. C2의 '돌아가지 않음'은 T-OR3의 카탈로그 사유를 그대로 따른 것이고, G26은 리뷰 규칙과 테스트 규칙의 방향 차이라 약하다.

## 6. 천장 항목과 체크 불가

**enforced (기계가 위반을 막음, 층 점수에서 뺄 것)**

- A6 — 활성화 1단계: prepend 단계를 순서대로 실행한다 (`_None._`이면 건너뜀; 기본값 빈 목록) (WF:80-82, CT:17): renders to `_None._`; nothing to do
- A7 — 활성화 2단계: persistent_facts 항목을 실행 내내 기본 맥락으로 삼고 `file:` 항목은 내용을 로드한다 (기본값 빈 목록) (WF:86-88, CT:23-27): renders to `_None._`
- A8 — 활성화 3단계: append 단계를 순서대로 실행한다 (`_None._`이면 건너뜀; 기본값 빈 목록) (WF:92-94, CT:21): renders to `_None._`
- G57 — 리뷰 서브에이전트가 매긴 severity는 무시한다 (맥락이 없어 등급을 못 매김) (S4:31): the prompts already forbid severity (G16); nothing to disregard

상류에는 renderer·status 라우팅 같은 기계가 있지만, 그것이 막는 것은 '잘못된 파일을 읽는 것'이 아니라 '토큰이 안 채워진 파일을 읽는 것'뿐이다. step 사이의 전환은 모두 텍스트 지시라 enforced가 아니다. 그래서 천장 항목은 빈 훅 네 개뿐이다.

**template null (함수도 judge도 볼 수 없음)**

- A6 — 활성화 1단계: prepend 단계를 순서대로 실행한다 (`_None._`이면 건너뜀; 기본값 빈 목록) (WF:80-82, CT:17; 판정 enforced; drop (G7))
- A7 — 활성화 2단계: persistent_facts 항목을 실행 내내 기본 맥락으로 삼고 `file:` 항목은 내용을 로드한다 (기본값 빈 목록) (WF:86-88, CT:23-27; 판정 enforced; drop (G7))
- A8 — 활성화 3단계: append 단계를 순서대로 실행한다 (`_None._`이면 건너뜀; 기본값 빈 목록) (WF:92-94, CT:21; 판정 enforced; drop (G7))
- B3 — 설명 수준을 {{.user_skill_level}}(기본 intermediate)에 맞춘다 (WF:73, S1:12, MB:13-18; 판정 none; drop (G2))
- C1 — 호출 프롬프트를 의도로 삼는다 (story id, ticket id, 파일 경로, 짧은 설명, 자유 서술 모두 가능) (S1:18, S1:41; 판정 none; env (G1))
- C4 — folder+id 디스패치: spec 폴더와 story id를 프롬프트에서 받고, 그 외 프롬프트 문구는 경쟁 설명이 아니라 step-02의 추가 맥락으로만 쓴다 (S1:27; 판정 none; drop (G1))
- C5c — stories.yaml 항목에서 title과 description만 쓴다: checkpoint 필드와 invoke_dev_with는 읽지 않는다 (S1:29; 판정 none; drop (G1))
- C11 — spec이 아닌 파일에서 workflow 상태를 추론하지 않는다 (S1:41; 판정 judge; drop (G1))
- C15 — epic 스토리인지는 의도·목록·epics 파일 내용을 함께 추론해 정하고, 파일명 패턴이나 정규식으로 정하지 않는다 (S1:49; 판정 none; drop (G3))
- C24c — folder+id에서는 브랜치를 story가 아니라 epic에 맞춰 판단한다 (S1:74; 판정 none; drop (G1))
- D12 — READY FOR DEVELOPMENT 기준으로 스스로 점검한다 (S2:13; 판정 none; keep)
- E12 — 플랫폼이 허용하면 구현 서브에이전트를 재호출 가능하게 유지한다 (step-04의 patch 전달용) (S3:30; 판정 none; drop (G7))
- E13 — 서브에이전트가 미완 작업을 보고했으면 진행 전에 직접 마무리한다 (S3:36; 판정 judge; drop (G7))
- G10 — 서브에이전트를 띄우지 않는 커스텀 레이어 지시는 적힌 대로 실행한다 (S4:25; 판정 none; drop (G7))
- G23 — (Edge Case Hunter) diff가 없으면 주어진 내용 전체가 범위다 (EH:5; 판정 none; drop (G7))
- G35 — (Claims Check) spec에서 `## Intent`와 `## Tasks & Acceptance`만 읽고 나머지는 무시한다 (CC:5, EH:98; 판정 none; drop (G7))
- G57 — 리뷰 서브에이전트가 매긴 severity는 무시한다 (맥락이 없어 등급을 못 매김) (S4:31; 판정 enforced; drop (G7))
- I5 — 리뷰 서브에이전트는 모두 현재 세션과 같은 모델 능력으로 돌린다 (S4:7; 판정 none; drop (G7))

## 7. port 후 남을 규칙 추정

fate별 규칙 수: **keep** 104, **env** 27, **semantic** 65, **drop** 84 (합 280).

| fate | gap | 수 | 대표 규칙 |
|---|---|---|---|
| drop | G7 | 38 | A1, A3a, A3b, A6, A7, A8, C18, C24a … |
| drop | G1 | 23 | C2, C3a, C3b, C3c, C4, C5a, C5b, C5c … |
| drop | G3 | 18 | C15, C16, C17, C19, C20, C21, E8, J1 … |
| drop | G8 | 2 | G84b, G85b |
| drop | G2 | 1 | B3 |
| drop | G5 | 1 | C28 |
| drop | G6 | 1 | H9 |
| env | G5 | 15 | A2, A4, A5, A14, B5, C13, C27, C29 … |
| env | G7 | 5 | E7, E14a, F3, F11, G2 |
| env | G10 | 3 | B1, B2, B6 |
| env | G8 | 3 | H4, H14, H15 |
| env | G1 | 1 | C1 |
| semantic | G7 | 41 | E16, F12, G4, G6, G8, G9, G11, G14 … |
| semantic | G8 | 14 | C12, D28, F2, F10, G58, G73, G81, G82 … |
| semantic | G4 | 5 | C23, D20, F7, G72, G84c |
| semantic | G9 | 5 | D42, F4, F5, F8, G50 |

템플릿별 생존(규칙 수, keep/env/semantic/drop):

| 템플릿 | keep | env | semantic | drop | 판단 |
|---|---|---|---|---|---|
| T-RD1 | 0 | 1 | 0 | 0 | 남음 |
| T-RD2 | 1 | 7 | 0 | 0 | 남음 |
| T-RD3 | 1 | 0 | 2 | 0 | 남음 |
| T-RD4 | 7 | 1 | 2 | 8 | 남음 |
| T-RD5 | 2 | 1 | 1 | 1 | 남음 |
| T-OR1 | 3 | 1 | 2 | 2 | 남음 |
| T-OR2 | 0 | 0 | 13 | 14 | semantic만으로 남음 — 2단계에서 뜻이 바뀜 |
| T-OR3 | 0 | 0 | 0 | 1 | 사라짐 |
| T-AW1 | 2 | 0 | 0 | 0 | 남음 |
| T-AW3 | 1 | 2 | 0 | 0 | 남음 |
| T-AW5 | 0 | 2 | 0 | 3 | 남음 |
| T-PR1 | 1 | 0 | 0 | 0 | 남음 |
| T-PR2 | 0 | 0 | 0 | 1 | 사라짐 |
| T-PR5 | 0 | 0 | 1 | 0 | semantic만으로 남음 — 2단계에서 뜻이 바뀜 |
| T-PR6 | 1 | 0 | 0 | 2 | 남음 |
| T-WD3 | 2 | 0 | 0 | 1 | 남음 |
| T-WD4 | 3 | 0 | 0 | 1 | 남음 |
| T-RF1 | 3 | 0 | 3 | 0 | 남음 |
| T-RF2 | 2 | 0 | 0 | 0 | 남음 |
| T-RF3 | 1 | 0 | 0 | 1 | 남음 |
| T-RF4 | 2 | 0 | 0 | 0 | 남음 |
| T-TR1 | 0 | 0 | 3 | 0 | semantic만으로 남음 — 2단계에서 뜻이 바뀜 |
| T-TR1b | 0 | 0 | 1 | 0 | semantic만으로 남음 — 2단계에서 뜻이 바뀜 |
| T-TR2 | 1 | 0 | 0 | 0 | 남음 |
| T-SR2 | 1 | 1 | 0 | 0 | 남음 |
| T-FM1 | 0 | 5 | 0 | 3 | 남음 |
| T-FM2 | 21 | 2 | 5 | 5 | 남음 |
| T-FM3 | 7 | 0 | 4 | 2 | 남음 |
| T-FM4 | 2 | 0 | 0 | 1 | 남음 |
| T-FM5 | 2 | 0 | 0 | 0 | 남음 |
| T-FM6 | 4 | 0 | 5 | 0 | 남음 |
| T-FM7 | 1 | 0 | 0 | 1 | 남음 |
| T-FM8 | 1 | 0 | 1 | 0 | 남음 |
| NEW-WD-exists-after | 3 | 0 | 0 | 1 | 남음 |
| NEW-WD-exists-before | 0 | 0 | 0 | 2 | 사라짐 |
| NEW-J-content | 23 | 0 | 18 | 3 | 남음 |
| NEW-AW-subagent | 0 | 0 | 4 | 13 | semantic만으로 남음 — 2단계에서 뜻이 바뀜 |
| NEW-FM-internal | 5 | 1 | 0 | 0 | 남음 |
| NEW-FM-language | 0 | 2 | 0 | 0 | 남음 |
| NEW-WD-revert | 0 | 0 | 0 | 2 | 사라짐 |

fate대로 하면 남는 템플릿 36개, 사라지는 템플릿 4개 (T-OR3, NEW-WD-exists-before, NEW-WD-revert, T-PR2). semantic만으로 남는 것(NEW-AW-subagent, T-TR1b, T-PR5)은 2단계가 '무엇으로 바꿀지'를 정해야 템플릿이 확정된다 — 서브에이전트 호출은 인라인 패스로 바뀌면 템플릿이 사라지고, 리뷰 레이어의 출력 형식 규칙(G29-G31, G49-G52)은 리뷰 기록을 산출물로 남길 때만 T-FM*로 살아남는다.

남는 핵심은 네 갈래다: 순서·읽기(A10-A12, A14, D6, D23-D24, E7), spec 골격·내용(B7-B15, D7-D9, D13-D19, D29-D48), 기록의 사실성(B4, E1-E2, F5-F6, H2, H6), 리뷰 triage의 형식과 판단(G60-G80, G87). 상류의 가장 독특한 부분인 '검토 뒤 patch/defer 루프'는 T-OR2·NEW-FM-internal·T-FM6로 남고, '되돌리고 재도출'(NEW-WD-revert)과 'blocked로 끝내기'(T-OR2의 8건)는 SWE 과제의 '패치 하나를 남겨라'와 충돌해 semantic/drop이다.

## 8. 판단이 갈릴 수 있는 곳

- **T-OR2를 넓게 썼다.** `blocked`로 끝나는 분기 27건을 모두 T-OR2(결과에 따른 분기·재시도 상한)에 붙였다. 카탈로그의 T-OR2 구현 항목은 OSF archive 재시도와 SKB 라운드 종료 두 가지뿐이라, '결과에 따라 멈춘다'가 '결과에 따라 한 번 더 한다'와 같은 템플릿인지는 09가 말한 '재시도 상한·결과 분기 L1'의 범위 문제다. 따라서 L1로 둔 blocked 규칙(C3-C9, F2, F8, F10, G83 등)은 실제로는 '인스턴스 예외로 L1C'일 수 있다 — 학습은 재시도, 상류는 정지.
- **intent gap 규칙의 템플릿.** D20·C12·C23·F7·G84c는 로직상 T-OR2지만 충돌의 상대는 T-SR1이다. 층은 템플릿이 아니라 인스턴스 사유로 L1C를 적었다. 다른 선택은 '묻지 않는 대신 멈춘다'를 T-SR2의 극성 반전 인스턴스로 보는 것이다.
- **judge 축을 템플릿으로 만들었다.** 지시대로 `null`을 최소화하려고 44건의 내용 규칙을 `NEW-J-content` 하나에 모았다. 10 문서 2.5절은 judge 항목을 카탈로그 밖에 두라고 하므로, 3절 표의 'J' 행은 S1-S10과 같은 줄에서 세지 않는 것이 맞을 수 있다. 분포 요약과 7절 생존 수는 J를 포함한다.
- **크기·개수 규칙을 T-FM3에 넣었다.** spec 900–1600 토큰(D29), Blind Hunter의 N=min(⌊√kB⌋+1,10)(G15), epic 문맥 800–1500 토큰(J7), 15단어 제한(G31). T-FM3는 '반복 항목 형식(번호·개수·고유성)'이라 토큰 길이는 경계다. 특히 G15는 기준값이 diff 크기에서 나오므로 artifact-diff 비교에 가깝고 NEW-FM-internal의 사촌일 수 있다.
- **리뷰어 프롬프트의 규칙을 에이전트 규칙으로 셌다.** EH/VG/CC/DC와 customize.toml의 레이어 지시(G11-G55, 45건)는 상류에서는 서브에이전트가 읽는다. 단일 에이전트 port에서는 본 에이전트가 읽게 되므로 포함했지만, '리뷰어는 claims를 늦게 읽는다'(G19)·'리뷰어 지시 파일을 부모가 읽지 않는다'(G9)처럼 두 역할이 하나가 되면 뜻이 뒤집히는 규칙이 섞여 있다. 2단계가 리뷰를 인라인으로 할지 버릴지에 따라 이 45건이 통째로 semantic이거나 drop이다.
- **다시 읽기 규칙의 층.** D24(spec을 디스크에서 다시 읽기)·E7(구현 전 spec을 끝까지 읽기)·E15(diff 파일 읽기)는 OSF의 '디스크에서 재독' 보상으로 L1이지만, 평가 workflow의 T-RD6(보이는 산출물 다시 읽지 않기, L1C)와 정반대다. 이 workflow를 학습에 넣으면 T-RD6의 층 사유가 더 강해진다.
- **G79의 순서 규칙과 G58의 keyed 대응.** '레이어가 보고한 순서대로 행을 적는다'는 T-RF1(기록=실행)에 넣었고, '이전 triage 행과 같은 위치·주장이면 carried'는 T-TR1b(키별 대응)에 넣었다. 09가 말한 '키별 순서' 새 템플릿을 만들지 않은 결과이며, 둘 다 다른 사람이면 NEW를 택할 수 있다.
- **train 수치의 출처.** `rewarded` 판정은 constraints.yaml의 지금 `implemented` 항목으로 했고(예: T-TR1은 AOS 1·OSF 2), 3절 표의 AOS/OSF/SKB/AID 칸은 지시대로 01 문서의 옛 표를 옮겼다. 그래서 T-TR1·T-RF2·T-OR1 행은 '학습 대비'(rewarded)와 표의 칸(—)이 어긋나 보인다. 01 표를 다시 만들 때 함께 고칠 것.
- **H15·H14와 T-SR2/T-OR1.** 'HALT만이 턴을 끝내는 방식'을 T-SR2(입력을 기다리며 끝내지 않음)로, '결과를 쓴 뒤 멈춤'을 T-OR1(마지막 쓰기)로 두었다. 둘 다 '마지막 메시지의 성질'을 보는 것이라 aidlc의 E10b와 같은 함수가 재면 한 항목으로 합쳐질 수 있다.
- **규칙 수의 밀도.** spec-template의 섹션마다 형식 규칙(D32-D47)을 따로 두어 F가 76건이다. aidlc 선례(S1.files처럼 필드마다 한 규칙)와 같은 밀도지만, 리뷰 레이어 출력 형식(G29-G31, G49-G52)까지 세면 port 후 사라질 형식 규칙이 상당수다. 7절의 생존 수는 그 과대 계상을 포함한다.
