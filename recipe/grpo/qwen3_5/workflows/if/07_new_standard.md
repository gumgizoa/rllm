# 07. 새 기준 구성과 AI-DLC 평가 정리 (B단계 1차 결과)

> 작성: 2026-10-23 (effort: extra high)
> 기준: `06_item_template_audit.md` 7절의 결정
> 코드: rllm 브랜치 `feat/sdlc-if-eval-layers` (로컬 커밋, push 안 함)

## 0. 요약

1. **새 기준의 구조를 만들었다.** constraint(문서가 요구하는 것)와 rubric(그것을 채점하는 방법)을 파일로 분리했다.
   - `sdlc_if/templates.yaml`: template 목록
   - `workflows/<wf>/constraints.yaml`: 네 workflow, 항목 1,011개(AOS `blocks` 2개 복원 포함)
   - 검증기: `sdlc_if/constraints.py`
2. **AI-DLC 평가 workflow를 문서 사본 위에서 돌리도록 바꿨다.** 사본에서 충돌하는 지시를 정리했다(A1, B1~B4). system prompt에서는 AI-DLC가 금지하는 지시 세 개만 뺐다. 원본 `aidlc_v4`와 `aidlc_v4_gen`은 그대로다.
3. **평가 rubric의 판정 결함을 고쳤다.**
   - 반복 라벨을 첫 줄만 읽던 항목 10개
   - 항상 통과하던 `no_test_target`
   - T-RD6를 원문대로 엄격하게
   - rubric 원문 인용 전체를 사본 기준으로 다시 맞춤
4. **최종 평가 층 (must 항목 수)**

   | 층 | 항목 수 | 템플릿 |
   |---|---|---|
   | L1 | 167 | 22개 |
   | L1-충돌 | 5 | T-RD6, T-AW4, T-PR5, T-RF2(`Executed: no`), T-OR3(6.2에서 추가) |
   | L2-중간 | 13 | T-TR2 5, T-RF3 3, T-AW6, Stg5c, `sequence`, T-SR2 2(6.2에서 추가) |
   | L2-먼 | 6 | T-FM5 5, T-TR1b 1 |

5. **테스트:** 전체 152개 통과, 20개 건너뜀. rubric 세 개의 generator check는 문제 0건이다.

## 1. 새 기준의 구조

```
recipe/grpo/qwen3_5/sdlc_if/templates.yaml    template 목록: 기술, 판정 로직, 대표 kind, 평가 기본 층
recipe/grpo/qwen3_5/sdlc_if/constraints.py    형식 설명과 검증: python -m recipe.grpo.qwen3_5.sdlc_if.constraints
workflows/<wf>/constraints.yaml               rubric 항목마다 constraint 하나 (같은 id)
workflows/<wf>/reward/rubric.yaml             채점 구현 (기존 형식 그대로)
```

**constraint 필드**
- `template`: 판정 로직. 체크할 수 없는 규칙은 null
- `status`: 구현 여부(implemented / unimplemented)
- `requirement`: 학습 보상에서의 must/should
- `rule`: 원문 규칙의 한 줄 요약(DOC:line 포함)
- `source`: 원문 인용과 위치
- `fidelity`: 검사가 규칙을 얼마나 그대로 보는지(faithful/narrower/broader/different). unimplemented면 대신 `class`
- `eval`: 평가 workflow에만 있음. layer, 평가 요구 수준, gate, layer_reason

**검증기가 확인하는 것**
- 항목 id가 rubric과 1:1로 맞는다.
- template이 목록에 있다.
- requirement와 출처가 rubric과 같다.
- 층이 template의 기본 층과 다르면 `layer_reason`이 있다.

**층을 정하는 곳이 하나가 됐다.** 예전에는 `layer.py`와 `build.py`가 따로 판정해서 어긋났다. 지금은 `aidlc_v4_ifeval/reward/build.py`가 `constraints.yaml`의 층과 평가 요구 수준을 읽어 `layers.yaml`을 만든다.

**첫 버전의 출처:** `scripts/seed_constraints.py`가 `mapping.tsv`(06의 통합표)에 07 결정을 반영해 처음 한 번 생성했다. 그 뒤로는 `constraints.yaml`을 직접 관리한다.

## 2. AI-DLC 평가 workflow: 문서 사본

`aidlc_v4_ifeval/`이 `docs/`, `instruction.md`, `system-prompt.j2`의 사본을 갖고 SPEC이 이 사본을 가리킨다. 컨테이너 경로(`/ai-dlc`, `/tmp/swe-bench-pro`)는 같다. `output_dirs`가 빠져 있어 오프라인 재채점에 필요한 산출물이 저장되지 않던 문제도 함께 고쳤다.

| # | 위치 (사본) | 수정 | 이유 |
|---|---|---|---|
| A1 | BT:47 | "Re-read the requirement and correct the source" → "Correct the source against the requirement it fails" | CW:42 "다시 읽지 말 것"과 충돌 |
| A1 | CG:17 | "Load the target files, change, …" → "Open the target files; take the change, … from the plan, which is still in context" | 계획 파일을 다시 읽으라는 뜻으로 읽힘 |
| B1 | BT Step 6·7 | 최종 변경 확인(Step 6)을 산출물 쓰기(Step 7) 앞으로 옮김. BT:43 "skip to Step 6"에 맞춤 | 쓰기 뒤에 확인하면 한 번만 쓰라는 규칙과 부딪힘 |
| B2 | BT:63 | "… listed as modified or created, plus any file a Step 5 fix changed" | Stage 5 수정 파일과 "A4 목록과 정확히 일치"의 모순 |
| B3 | CG:54 | "The reproduction script is recorded under Reproduction Script, not under Changed Files." | rubric이 이미 이렇게 판정함(Created에서 제외) |
| B4 | CW:40 | "and nowhere else" → "not in an earlier stage's artifact" | Unmet requirements, Regressions와 모순 |
| B4 | BT:106 | "the only place … recorded" → "lists all unresolved work, including any unmet requirement or regression left unresolved" | 위와 같음 |
| A2 | SP | `<ENVIRONMENT_SETUP>` 절 삭제 | 설치 지시가 CW:134, BT:20과 충돌 |
| A3 | SP | "first thoroughly understand the codebase through exploration" 삭제 | RE:21과 충돌 |
| A4 | SP | "propose a new plan and confirm with the user" 삭제 | CW:132(사용자와 상호작용 금지)와 충돌 |

**하지 않은 것**
- **B7(태그 표기 통일):** 기존 `aidlc_v4` scorer가 `[satisfies …]`를 파싱한다(`artifacts.py:132`). 또 문서마다 자기 산출물 안에서는 표기가 일관돼서 문서를 그대로 따른 에이전트가 감점되지 않는다. rubric도 괄호 안의 id를 읽는다.
- **B5, B6, B8:** rubric이 이미 한쪽으로 해석했고 감점 위험이 낮아서 보류했다.
- **학습 workflow 세 개의 system prompt:** 06 7절의 "나중에 할 일(T-PR3)"로 남겼다. 지금은 공통 부분이 학습과 평가에서 다르다. 평가에는 세 지시가 없고 학습에는 있다.

## 3. 평가 rubric 정리 (`aidlc_v4_ifeval/reward/build.py`)

1. **사본 기준으로 다시 맞춤**
   - 출처의 경로와 sha256을 사본으로 바꿨다. 엔진은 문서 읽기를 원문 지문으로 감지하므로 반드시 필요하다. 이전에는 원본을 가리키고 있었다.
   - 인용 112개를 새 위치로 옮겼다. 원래 범위 폭을 유지하며 평행 이동했고, 옮긴 뒤 원문이 같은지 대조했다.
   - 문구가 바뀐 줄의 인용 4개는 새 문구로 바꿨다(`QUOTES`).
   - 문서화된 충돌 7건에 `resolved_in_copy` 표시를 했다.
   - `modality_evidence`와 `note` 안의 자유 문장에 적힌 행 번호는 `aidlc_v4` 기준으로 남겨 두었다. `constraints.yaml`의 `rule` 안 BT·SP 행 번호는 사본 기준으로 바꿨다.
2. **반복 라벨을 모두 읽기**
   - 엔진에 선택 옵션 `all`을 추가했다(`field_list` 선택자와 `field_type`). 새 함수는 `markdown.field_values`다.
   - 기본 동작은 그대로다. 학습 rubric에는 반복 라벨을 첫 줄만 읽는 항목이 없음을 확인했다.
   - 평가 항목 10개에 `all`을 켰다.
3. **`no_test_target` 정규식 수정**
   - 접두부를 원자적으로 만들었다(Python 3.10 호환 방식).
   - `test_*.py`, `*_test.py`, `conftest.py`도 잡는다.
4. **T-RD6 엄격판 (`aidlc_ifeval.no_reread`)**
   - 같은 step 예외를 없앴다.
   - CW:43의 "보이지 않을 때만 복구"를 그대로 반영했다. 쓰기 호출이 내용을 보여 주지 않은 산출물(cp, 스크립트로 생성)만 첫 읽기를 복구로 인정한다.
   - 읽기는 step 단위로 센다(기존 `_read_steps`).
5. **평가 요구 수준:** 06 3.4의 5개를 must로 올렸다. 평가 must가 아닌 항목은 `plan_execution.2` 하나만 남았다.

## 4. 학습 쪽

**복원**
- AOS `blocks` 2개: `agentos_v2` 네 파일을 커밋 상태로 되돌렸다. generator check는 문제 0건이다.

**유지**
- SKB 파일 목록 `cross_ref` 3개 제외(5단계 P1)

**하지 않은 것 (보상이 바뀌므로 결정 필요)**
- OSF residue 2개가 항상 통과하는 문제
- OSF 요구 수준 4개(kebab-case, TPL_TASKS 제목 3개)
- SKB `local_verification` should → must(×3)
- SKB `reproduction`이 `[NEEDS CLARIFICATION]` 표시를 실패로 처리하는 문제와 `checks_table.consistent`가 넓게 보는 문제
- AOS 요구 수준 8개(`group_parts` 등)

목록은 06 5.2에 있다. 각 항목의 문제는 해당 workflow `constraints.yaml`의 `fidelity_note`에도 남아 있다.

## 5. 테스트

- **`tests/test_aidlc_v4_ifeval.py` (13개)**
  - 빌드 재현, constraints 정합, 사본 사용, 모든 인용이 사본의 자기 행에 있음
  - 골든 run(문서 읽기를 사본 텍스트로 바꿔 줌)이 모든 층 1.0
  - 다시 읽기는 L1-충돌만 떨어뜨림
  - 쓰기 호출 안에서 읽기 = 위반
  - 내용을 보여 주지 않은 쓰기 뒤 첫 읽기는 허용, 두 번째 읽기는 위반
  - 마지막 Step의 Target을 테스트 파일로 바꾸면 반복 라벨 항목이 잡아냄
  - 정규식, 단계 미도달, 편차 gate
- **`tests/test_sdlc_if.py`:** 네 workflow의 constraints 정합, 검증기가 어긋남을 잡는지, `field_values`
- **`tests/test_agentos_v2.py`:** "공통 system prompt는 SDK 기본값" 불변식에서 `aidlc_v4_ifeval`을 예외로 두고 이유를 주석으로 적었다.

## 6. B단계 2차 (같은 날, 사용자 결정 반영)

### 6.1 학습 rubric: "현재 기준"으로 재설계 시작

예전 rubric보다 지금의 기준을 우선한다는 결정에 따라 다음 원칙을 적용했다.

| 원칙 | 내용 |
|---|---|
| R1 | 항상 통과하는 항목은 핵심이 아니면 뺀다 |
| R2 | 문서가 허용하는 행동을 감점하는 항목(broader)은 판정을 고치거나, 핵심이 아니면 뺀다 |
| R3 | 요구 수준은 원문 표현을 따른다. 단 대리 지표인 항목과 양쪽을 모두 에이전트가 쓰는 항목(보상 조작 우려)의 하향은 유지한다 |
| R4 | 같은 것을 보는 중복 항목은 must 하나만 남긴다 |

**구현 방식:** 생성기를 캐시만으로 다시 돌리면 결과가 재현되지 않는다(OSF는 248개가 131개로 줄고, AOS도 다르다). 그래서 생성된 `reward/rubric.yaml`은 그대로 두고, `constraints.yaml`의 `change`(사유 포함)를 적용해 `reward/rubric.train.yaml`을 만든다(`sdlc_if/build.py`). 학습의 `eval.py`는 이 파일로 채점한다. 생성기 lock과 check는 그대로 통과한다.

| workflow | 변경 | 원칙 |
|---|---|---|
| OSF | `ff.spec.no_template_residue.template`, `ff.tasks.no_template_residue` 제외 | R1 (패턴이 모두 HTML 주석인데 검사 전에 주석을 지운다) |
| OSF | `ff.tasks.item_format.tasks`, `.line` 제외 | R4 (`groups`, `task_lines`와 중복) |
| OSF | `verify.verify.item_format.priorities` 제외 | R2 (문제가 없는 깨끗한 보고서를 실패시킴) |
| OSF | `new_capabilities` kebab-case, `ff.tasks.section_present.tasks`를 must로 | R3 |
| SKB | `fix*.section_present.local_verification` ×3을 must로 | R3 |
| SKB | `assess.field_filled.reproduction` → "비어 있지 않음"(`item_format \S`) | R2 (`[NEEDS CLARIFICATION]` 표시만 있는 경우 허용. 템플릿 잔여물은 residue 항목이 잡음) |
| SKB | `checks_table.consistent`에서 lint / type-check 행 제외(`checks.py` 한 줄) | R2. baseline부터 있던 실패 행 문제는 남음(fidelity_note) |
| AOS | `group_parts`, `existing_code_to_leverage`, write-spec `visuals_checked`, `requirements.artifact_exists`, `spec_dir.artifact_exists`, `verifications_dir.paths_written`을 must로 | R3 |
| AOS | `final_verification.no_template_residue`를 should로 | R3 (IT:249 "should follow", 같은 템플릿의 나머지 29개가 should) |
| AOS | implement `read.spec_inputs` 제외 | R2 (IT:29 "provided"는 읽으라는 지시가 아님) |
| 유지 | AOS `read.tasks_phase3`, OSF 대리 지표 3개 | R3 예외 |

채점되는 항목은 다음과 같이 바뀌었다(must/should, 구현 항목).

| workflow | 생성된 rubric | 학습용 rubric |
|---|---|---|
| AOS | 108/49 | 113/43 |
| OSF | 119/22 | 119/17 |
| SKB | 242/57 | 245/54 |

### 6.2 AI-DLC 새 평가 항목 (log_only, 층에만 반영)

| 항목 | 템플릿 (신규) | 층 | 판정 |
|---|---|---|---|
| `aidlc_v4_ifeval.global.run.no_return` | T-OR3 이전 단계로 돌아가지 않음 | L1-충돌 | 다음 단계 문서를 읽은 뒤 이전 단계 문서를 다시 읽으면 위반(CW:71, BT:58, CG:34). SKB는 라운드마다 02-fix.md를 다시 읽는 것을 보상하고, OSF는 apply에서 ff로 돌아가는 것을 허용한다 |
| `aidlc_v4_ifeval.global.run.no_question_file` | T-SR2 사용자에게 묻지 않음 | L2-중간 | 질문 파일 이름의 파일을 쓰면 위반(CW:132) |
| `aidlc_v4_ifeval.global.run.no_request_for_input` | T-SR2 | L2-중간 | run의 마지막 메시지가 사용자에게 묻거나 승인을 기다리면 위반. 휴리스틱이고, `finish` 도구의 메시지는 trace에 없다 |

- 원래 unimplemented였던 같은 규칙 4개는 constraint를 "duplicate(새 항목이 구현)"로 바꿨다.
- 이로써 **S9가 평가 가능**해졌다(L2-중간).
- 최종 평가 must 항목 수: L1 167, L1-충돌 5, L2-중간 13, L2-먼 6.

### 6.3 테스트

전체 157개 통과, 20개 건너뜀. 새로 추가한 테스트는 다음과 같다.
- 학습용 rubric이 최신이고 세 workflow의 골든 run이 학습용 rubric에서 1.0
- 새 평가 항목의 통과·실패 사례

생성기 check는 세 workflow 모두 문제 0건이다.

### 6.4 rubric 파일을 하나로, 학습 system prompt 정리 (3차)

- **생성기와의 관계:** `workflow_rubric.generator`는 문서에서 LLM으로 규칙을 뽑고, 그것을 검증 함수로 옮겨 `rubric.yaml`을 만든다. constraint 추출과 채점 구현을 한 파일에 섞어 둔 셈이다. 다시 돌려도 재현되지 않으므로(6.1) 생성기 출력은 첫 버전의 출처로만 남긴다.
- **rubric은 workflow마다 하나다.** `reward/rubric.yaml`이 우리 기준의 채점 rubric이고 `constraints.yaml`과 함께 관리한다. 6.1의 `rubric.train.yaml`과 `sdlc_if/build.py`는 없앴다. `change` 필드는 생성기 첫 출력과의 차이를 남긴 기록이다.
- **학습 system prompt:** 세 개에서 평가 사본과 같은 세 지시를 뺐다. 이제 연구 대상 네 workflow의 system prompt는 workflow 절 밖이 똑같다(테스트로 고정).
  - SP 인용 30개는 새 위치로 옮겼다(`sdlc_if/anchor.py`, 평가 빌드와 같은 함수). 사라진 인용은 없다.
  - 연구 범위 밖 workflow(`speckit_sdd`, `aidlc_v4`, `aidlc_v4_gen`)는 SDK 기본 prompt 그대로다. 공통 부분 테스트는 두 무리로 나눠 검사한다.
- **남은 생성기 산출물:** `generator.yaml`, `rubric.lock`, `rubric.md`, `gen-cache`, `gen-work`는 더 이상 `rubric.yaml`과 맞지 않아 `generator check`가 실패한다. 삭제 여부는 결정이 필요하다.

## 7. 남은 일

1. 학습 workflow의 생성기 산출물 정리(삭제 여부)
2. 학습 rubric 재설계 계속(보상 결합 방식, 형식 항목의 비중: 04의 선택지 B)
3. push, 그리고 기준점 측정(원본 모델 non-thinking: `workflow=aidlc_v4_ifeval` 층별 점수, 학습 workflow compliance, IFBench)
