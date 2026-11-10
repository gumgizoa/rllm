# 05. AI-DLC 평가 scorer 보완 (설계 문서 9.1절 6단계 결과)

> 작성: 2026-10-23
> 코드 위치: `/mnt/nas1/mmi/ks.lim/repos/rllm`, 로컬 브랜치 `feat/sdlc-if-eval-layers` (기준 `feat/aidlc-openhands-sdk-recipe` `9d538dcc`). **커밋·push하지 않았다.**
> 재현 스크립트: `scripts/eval_layers.py` (층 배정 규칙의 초안), 저장소의 `workflows/aidlc_v4_ifeval/reward/build.py` (최종본)

## 0. 요약

1. **평가 전용 workflow `aidlc_v4_ifeval`을 추가했다.**
   - 에이전트가 보는 것은 `aidlc_v4`와 똑같다(문서, instruction, system prompt를 참조).
   - 채점은 `aidlc_v4_gen` rubric을 그대로 쓰고, 여기에 두 가지만 더했다: 재독 금지 항목 1개(`log_only`), 층 배정 파일 `layers.yaml`.
   - 그래서 `aidlc_ifeval/compliance`는 `aidlc_gen/compliance`와 같은 값이다. 평가는 층별 점수 `aidlc_ifeval/layer*/<L>`로 한다.
   - 동료들이 작업 중인 `aidlc_v4_gen`은 수정하지 않았다.
2. **평가 문항 구성 (must만 채점):**
   - L1 150, L1-충돌 9, L2-먼 13, L2-중간 11
   - should 6개는 진단용
3. **must/should를 원문과 대조했다.** 생성기가 "양쪽 다 에이전트가 쓴 산출물"이라는 이유(보상 조작 우려)로 should로 낮춘 11개를, AI-DLC 원문 근거로 평가용 must로 올렸다. 계획 이행 2개는 "편차가 기록되지 않은 경우에만" 판정한다.
4. **T-RD6(자기 산출물 재독 금지) 검증 함수를 구현했다.** 학습·평가 하네스는 문맥 압축(condenser) 없이 Agent를 만든다. 그래서 "보이는 산출물"을 "이미 쓴 산출물"로 정확히 판정할 수 있다.
5. **학습 rubric에서 결정 P1을 반영했다.** speckit_bug 3개(정식 재생성), agentos_v2 2개(직접 제거, 아래 4절의 재현성 문제 때문)를 뺐다.
6. **테스트:** golden trajectory 기반 테스트 6개가 통과했다. 기존 테스트는 변경 전후 결과가 같아서 회귀가 없다.

## 1. 평가 문항 층 배정 결과

| 층 | must | should | 예 |
|---|---|---|---|
| L1 (seen) | 150 | 5 | 문서 읽기, 순서, 산출물 쓰기, 테스트 파일 금지, baseline, 기록 사실성, 골격 |
| L1C (충돌) | 9 | — | 재현 스크립트 지연 실행 2, 전체 스위트 금지 1, 설치 금지 1, 이전 산출물 재작성 금지 4, 재독 금지 1 |
| L2F (먼) | 13 | — | frontmatter 5, 계획 Step 블록 필드 4, 변경 파일 목록 = 실제 3, Step→R 대응 1 |
| L2M (중간) | 11 | 1 | 요구사항 ID 대응 5, 계획 이행 3, 같은 범위 재실행 1, 기록 경로 실행 2 (should: Exercises ⊇ 예외 상황 요구사항) |

**L1C 안에서는 이전 산출물 재작성 금지(산출물마다 1개, 4개)가 큰 비중을 차지한다.** 층 점수가 문항의 단순 평균이기 때문이다. 규칙별 결과는 6절의 오프라인 재채점으로 본다.

## 2. 평가용 must/should 재판정

생성기의 `modality_evidence`를 보면, 아래 항목은 원문이 must인데 생성기가 낮췄다.

| 항목 (`aidlc_v4_gen.` 생략) | 생성기 | 평가 | AI-DLC 근거 | 비고 |
|---|---|---|---|---|
| `code_generation_generation.a4.cross_ref.plan_execution_tags` (T-TR1b) | should | **must** | CW 42 "Quote identifiers — R1, step numbers, full paths — verbatim, never renumbered" | |
| `code_generation_generation.a4.cross_ref.4` (T-RF3) | should | **must** | CG 완료 기준 "listing modified and created files" | |
| `build_and_test.a5.cross_ref` (T-RF3) | should | **must** | BT 103 "Confirm the files in the change are exactly those Code Generation listed" | |
| `code_generation_planning.a3.cross_ref{,.2,.step_tags_cover,.coverage_ids,.coverage}` (T-TR1) | should | **must** | CP 15 "MANDATORY: Create one or more explicit steps for each requirement", CP 84-86 "Requirement Traceability", CP 67 "it must account for every identifier" | 생성기는 "양쪽 다 에이전트가 쓴 산출물"(규칙 6)이라 낮춤. 보상 조작 우려는 평가에 해당하지 않음 |
| `code_generation_generation.a3.cross_ref` (T-TR2 계획 대상 = 실제 수정) | should | **must + 조건** | CG 21 "Use the path recorded in the plan" | CG 34은 편차를 기록하면 계획과 달라도 된다고 함. 생성기도 이 이유로 낮춤 → `Deviations from Plan`이 none일 때만 판정 |
| `code_generation_generation.a4.cross_ref.repro_path` (T-TR2) | should | **must + 조건** | CG 68 "[full path as written, matching the planned path]" | 위와 같은 조건 |
| `build_and_test.a5.cross_ref.build_command` (T-TR2) | should | **must** | BT 11 "The baseline and the test command are established, not re-derived", BT 17 | |
| `code_generation_planning.a3.cross_ref.exercises_edge_cases` | should | should (유지) | CP 28 "Include the conditions from the Edge Cases …" (체크리스트 항목, 완료 기준에 없음) | |

학습 보상의 요구 수준은 바꾸지 않았다. 재판정은 `layers.yaml`에만 있다.

## 3. T-RD6 검증 함수 `aidlc_ifeval.no_reread`

- **규칙:** CW 42-43 "Do not re-read an artifact you can still see … Read an artifact only to recover, when … history was compacted"
- **문맥 압축 확인:**
  - `rllm/harnesses/tools/openhands_sdk_runner.py`는 `Agent(llm, tools[, system_prompt_filename])`로 Agent를 만들고 condenser를 넘기지 않는다.
  - SDK의 `condenser` 기본값은 `None`이다.
  - 따라서 실행 중 대화 기록이 압축되지 않으므로, "보이는 산출물" = "이미 쓴 산출물"이다.
- **판정:** 산출물마다 첫 내용 쓰기 단계 이후에 그 경로를 읽는 행동(editor view, `cat`/`head`/`sed -n` 등 셸 읽기)이 있으면 위반이다. 같은 단계 안의 확인 읽기는 세지 않는다. 점수는 재독하지 않은 산출물의 비율이다.
- **배치:** `log_only` 항목이라 compliance에는 들어가지 않고 L1C 층에만 들어간다. 학습 workflow에는 넣지 않는다. 넣으면 충돌 문항이 사라지기 때문이다.
- **주의:** condenser를 켜는 설정으로 바뀌면 판정을 다시 봐야 한다. 그 경우 `chat_completions`의 요청 메시지에 쓰기 도구 호출이 남아 있는지로 "보이는지"를 판정할 수 있다.

## 4. 구현 내용 (브랜치 `feat/sdlc-if-eval-layers`, 미커밋)

| 파일 | 변경 | 비고 |
|---|---|---|
| `workflow_rubric/layers.py` (신규) | `layers.yaml` 로드·검증(rubric sha256 일치, id 존재), 층별 신호 계산 | `section_is_none` 조건(라벨 없는 절이 none인지) 포함 |
| `workflow_rubric/evaluation.py` | `RubricEvaluation(..., layers_path=None)`, `rubric_signals(..., layers=None)` | **기본값이면 기존 동작과 동일** |
| `workflows/aidlc_v4_ifeval/` (신규) | `__init__.py`(SPEC), `reward/build.py`, `reward/rubric.yaml`, `reward/layers.yaml`, `reward/checks.py`, `reward/eval.py` | `build.py --check`로 `aidlc_v4_gen` rubric이 바뀌었는지 감지 |
| `workflows/__init__.py` | `aidlc_v4_ifeval` 등록 | |
| `tests/test_aidlc_v4_ifeval.py` (신규) | 6개 + `rllm` 필요 1개(skip) | 아래 |
| `workflows/speckit_bug/generator.yaml` + `reward/rubric.{yaml,md,lock}` | manual `cross_ref.changes` 3개 삭제, 생성기로 재생성(`--llm cache-only --selftest`) | 항목 332 → 329, 다른 항목 변화 없음, self-test 통과(golden 1.0). 생성기 검토 메모(`conflicts`)는 16 → 11 (채점 무관) |
| `workflows/agentos_v2/generator.yaml` + `reward/rubric.{yaml,md,lock}` | manual `agentos_v2_blocks` 2개 삭제. LLM 추출분을 막는 `exclude` 사유 문구 수정. rubric은 **직접 제거** 후 lock 갱신 | `check` 통과, golden compliance 1.0 |

**테스트 내용:**
- 커밋된 rubric·layers가 새로 빌드한 것과 같은지
- golden에서 모든 층 = 1.0이고 compliance가 `aidlc_v4_gen`과 같은지
- 산출물 1회 재독 시 L1C만 하락하는지(0.978)
- Stage 2에서 멈춘 실행에서 `layer_reached`와 `layer`가 갈리는지
- 편차를 기록하면 계획 이행 문항이 층에서 빠지는지

**기존 테스트:** 변경 전후 모두 "실패 4, 통과 10, 수집 오류 11"이다. 오류는 이 서버에 `rllm` 등이 없어서 생기는 환경 문제다. 변경 후 통과가 16(새 테스트 6개)이 됐다.

**발견한 문제: agentos_v2 rubric은 현재 설정과 캐시로 재현되지 않는다.**
- `--llm cache-only`로 다시 생성하면 채점 항목이 157개에서 152개로, unimplemented가 50개에서 19개로 줄어든다. 남는 항목의 내용은 같다.
- 빠지는 채점 항목은 LLM이 추출한 5개다: `shape_spec.verifications_dir.agentos_v2_paths_written`, `shape_spec.requirements.cross_ref{,.2}`, `shape_spec.spec.agentos_v2_holds`, `write_spec.spec.field_filled.existing_code_to_leverage`.
- 마지막 커밋(`ae6882a1`, 10-19)의 rubric이 커밋된 캐시와 맞지 않는 것으로 보인다. 그래서 agentos_v2는 재생성하지 않고 2개 항목만 직접 제거했다. **동료에게 알려 재생성 경로를 맞춰야 한다.**
- speckit_bug는 날짜 외에 완전히 재현됐다.

## 5. U2(작업 직후 체크 표시) 검토

- **규칙:** OSF apply "Update task checkbox immediately after completing each task" (must, unimplemented)
- **템플릿:** T-PG1(진행 기록)의 반복형이다. 사건마다 반복하는 구조라 템플릿 축에 해당한다. 설계 문서 7.4절의 E8과 같은 축이다.
- **AI-DLC와의 관계:**
  - AI-DLC에는 단계 안에서 진행을 즉시 기록하는 규칙이 없다. Stage 4의 "Record Progress"도 산출물 한 번 쓰기(추가 쓰기 금지)로 끝에 기록한다.
  - 따라서 U2를 학습에 넣어도 L2 판정(02, 03)은 바뀌지 않는다.
  - 반복 쓰기라는 점에서 AI-DLC의 한 번에 쓰기(T-WD1)와 방향이 다르다. 하지만 학습에는 이미 tasks.md 체크 갱신(AOS, OSF)이 있어서 새로운 충돌이 생기지는 않는다.
- **판정 방법 (안):** 체크 쓰기가 모든 작업을 끝낸 뒤 한꺼번에 일어나지 않고 저장소 수정 사이사이에 나뉘어 일어나는지 본다. 예: 체크가 쓰인 시점 사이마다 소스 수정이 있는지. 작업과 행동을 정확히 대응시키기는 어렵지만, 이 근사로 "한꺼번에 체크"는 잡을 수 있다.
- **결론:** 구현해도 평가 설계에 영향이 없고, 학습 쪽 S7(진행 기록, 현재 비중 1.6~3.9%) 다양성을 늘린다. Future work ①에서 우선 구현 후보로 둔다.

## 6. 사용 방법

**평가 실행 (기존 `aidlc_v4` 대신):**
```bash
rllm eval <dataset> --agent-kwargs workflow=aidlc_v4_ifeval ...
# 로그 신호: aidlc_ifeval/compliance (= aidlc_gen), aidlc_ifeval/layer/{L1,L1C,L2F,L2M},
#            aidlc_ifeval/layer_reached/{...}, aidlc_ifeval/layer_should/{...}, 그리고 aidlc/* (v4 scorer)
```

**층 점수 해석:**
- `layer/L`은 도달하지 못한 단계의 문항도 실패로 센다. 진입·진행 실패가 섞인 값이다.
- `layer_reached/L`은 도달한 단계의 문항만 센다. "그 단계에 왔을 때 지시를 지켰는가"에 가깝다.
- 원본 모델은 진입률이 낮았으므로(이전 보고서) 두 값을 함께 보고한다.

**규칙별 결과:** 온라인 신호는 층 단위까지만 남는다. 규칙(템플릿)별 비율은 저장된 trajectory를 `engine.evaluate`로 오프라인 재채점해서 본다. 필요하면 재채점 스크립트를 만든다.

**`aidlc_v4_gen` rubric이 바뀌면:** `python -m recipe.grpo.qwen3_5.workflows.aidlc_v4_ifeval.reward.build`로 다시 빌드한다. 테스트가 `--check`로 불일치를 잡는다.

## 7. 다음 단계

1. **검토와 커밋:** 브랜치 변경을 검토한 뒤 커밋한다. push와 PR은 동료와 협의한다. agentos_v2 재현성 문제도 함께 공유한다.
2. **기준점 측정:**
   - 원본 모델(non-thinking)로 `aidlc_v4_ifeval`을 돌려 층별 점수를 낸다.
   - 학습 workflow 세 개의 compliance와 형식 항목 통과율을 잰다(선택지 B 판단용).
   - IFBench non-thinking도 측정한다.
3. **unimplemented 정리(P4)와 Future work ① 구현:** agentos_v2 재현성 문제를 해결한 뒤 진행한다.
