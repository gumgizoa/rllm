# 10. 인수인계: 템플릿 분류, 층 분류, 층별 성능 분석을 이어서 하는 법

> 작성: 2026-11-02
> 대상: 08·09를 이어받는 사람. 01~07은 읽었다고 가정한다.
> 범위: "rubric 항목(또는 method)에 템플릿을 붙이고 → 층을 정하고 → 층별 성능을 내는" 작업의 절차, 봐야 할 코드, 지금 상태와 미결 사항.

## 0. 한 장 요약

```
workflow 문서 줄
   └─ constraint / 규칙        문서가 요구하는 것 한 가지          (constraints.yaml / ruleset.yaml)
        └─ rubric item / method  그것을 trajectory에서 재는 함수     (rubric.yaml, checks/*.py / methods/*.py)
             ├─ 템플릿 T-*       판정 로직의 종류. workflow 간 비교의 단위 (sdlc_if/templates.yaml)
             └─ 층 L1/L1C/L2M/L2F  그 템플릿을 학습 workflow가 보상·노출했는가    (constraints.yaml eval: → layers.yaml)
                  └─ 층 신호      항목별 pass/fail을 층으로 평균 (workflow_rubric/layers.py)
                       └─ 분석    base vs 학습 checkpoint, task 쌍 비교 (if/scripts/eval_step27, eval09)
```

세 가지만 기억하면 된다.

1. **템플릿은 규칙(문장)이 아니라 판정 함수에 붙인다.** 같은 문장이라도 코드로 재느냐 judge로 재느냐에 따라 템플릿이 다르고, 다른 문장이라도 같은 로직이면 같은 템플릿이다.
2. **층은 템플릿의 성질이되, 인스턴스 예외가 있다.** 기본값은 templates.yaml의 `eval.layer`, 예외는 constraints.yaml의 `eval.layer_reason`에 근거를 적는다. 층은 **학습 rubric 버전에 상대적**이다.
3. **층 평균은 항목 수와 천장에 지배된다.** 결론은 템플릿 단위로 내고, 층 평균은 요약으로만 쓴다(09의 L2가 그 예).

## 1. 코드 지도

두 브랜치에 걸쳐 있다. 작업 트리를 바꾸지 않고 다른 브랜치 코드를 쓰려면 `git worktree add --detach <dir> <branch>` 후 `sys.path.insert(0, <dir>)`.

### 1.1 `feat/workflow-if-templates` (템플릿 연구 본체)

| 경로 | 역할 |
|---|---|
| `sdlc_if/templates.yaml` | 템플릿 카탈로그. 기술 S1~S10, 템플릿마다 `name`, `kinds`(이 템플릿을 구현하는 kind·인자), `eval.layer`(기본 층)와 `reason`. 머리말에 "무엇이 인스턴스 차이고 무엇이 템플릿 차이인가" 규칙이 있다 |
| `sdlc_if/constraints.py` | constraints.yaml 형식 설명과 검증. `python -m recipe.grpo.qwen3_5.sdlc_if.constraints [WORKFLOW ...]` |
| `workflows/<wf>/constraints.yaml` | 네 workflow(agentos_v2, openspec_ff, speckit_bug, aidlc_v4_ifeval). rubric item과 **같은 id**로 constraint 하나: `template`, `status`(implemented/unimplemented), `requirement`, `rule`, `source{doc,lines,quote}`, `fidelity`, `change`. 평가 workflow에는 `eval: {layer, requirement, when, layer_reason}` 추가 |
| `workflows/<wf>/reward/rubric.yaml` | 채점 구현. item = `check: {kind, params}` + requirement/weight/gate/availability |
| `workflow_rubric/checks/*.py` | 공통 kind 18개(`register("kind", params=...)`). 템플릿을 정할 때 읽는 곳 |
| `workflow_rubric/layers.py` | 층 신호. `load`(rubric sha 검사), `_reached`, `_when`, `signals` → `{prefix}/layer/L`, `layer_reached/L`, `layer_should/L` |
| `workflows/aidlc_v4_ifeval/reward/build.py` | constraints.yaml의 `eval:`에서 `layers.yaml` 생성. `python -m ...aidlc_v4_ifeval.reward.build [--check]` |
| `workflows/aidlc_v4_ifeval/reward/eval.py` | `Evaluation(RubricEvaluation)`: prefix `aidlc_ifeval`, `layers_path` |
| `workflow_rubric/evaluation.py`, `engine.py`, `aggregate.py` | `parse_run`, `rubric_signals`, `engine.evaluate → Report(results, scores, facts)`, compliance 집계(sigma·kappa) |
| `workflow_rubric/offline/harbor.py` | 저장된 trace만으로 Collected 재구성(`collected_from_replay`) |
| `scripts/rescore_compliance.py` | 저장된 에피소드 오프라인 재채점(`artifacts.workflow_outputs` 필요) |
| `tests/test_sdlc_if.py` | constraints·templates 검증 테스트 |
| `workflows/if/01~09*.md`, `workflows/if/scripts/` | 연구 문서와 재현 스크립트 (untracked, 커밋 전) |

### 1.2 `feat/aidlc-openhands-sdk-recipe` (새 평가기)

| 경로 (`workflows/aidlc_v4_eval/`) | 역할 |
|---|---|
| `reward/ruleset.yaml` | 규칙 195개: `id, stage, kind(P/F/E/C/R/Q/A), text, methods{key: {kind, stage(s)}}`, method 없는 규칙은 사유. `reward/ruleset.py check / sync` |
| `reward/ruleset.md`, `reward/rubric.md` | 위를 렌더한 표. 규칙↔method↔재료가 한눈에 보인다. **템플릿 붙일 때 먼저 읽을 것** |
| `reward/methods/*.py` | method 189개. `@method("check/…", materials=(…), stages=…, family=…)`. form/proc/claim(check)/rule/atom/run/judge |
| `reward/methods/__init__.py` | 재료(MATERIALS) 정의, 등록 규칙 |
| `reward/measures.py`, `read.py`, `trace.py`, `skeleton.py` | run을 한 번 읽어 공유하는 측정값, 산출물 파서, trace 파서 |
| `reward/judge.py` | LLM judge 질문 26개(`QUESTIONS`), 환경 변수 `AIDLC_JUDGE_*` |
| `reward/rubric.yaml`, `checks.py`, `eval.py` | 항목 227개(= method@단계), kind 등록, `Evaluation(RubricEvaluation)` prefix `aidlc`, 집계 `kind_matrix` |
| `snapshot/audited.json` | 항목별 사람 판정 234건. 템플릿·판정 로직 검증 자료 |
| `docs/`, `system-prompt.j2` | aidlc_v4 원본과 동일(ifeval 사본과 다름: 09 문서 1절) |

이 브랜치의 `workflow_rubric/`에는 `layers.py`가 없다. 09는 층 신호를 분석 스크립트 안에서 직접 계산했다(`if/scripts/eval09/analysis_eval09.py`의 `layer_vals`).

## 2. 템플릿 분류 절차

### 2.1 단위를 정한다

- ifeval·학습 workflow: rubric item 하나 = constraint 하나(같은 id). 템플릿은 constraint에 적지만 실질은 item의 `check`에 붙는 것이다.
- aidlc_v4_eval: 규칙 1 : method n. **method마다** 템플릿을 붙인다. 예: 규칙 D6 → `check/e1_build_command_run`(T-RF1) + `judge/D6`(내용, 템플릿 밖). method가 단계마다 있으면(`proc/A2@1..5`) 템플릿은 method에 한 번 붙이고 항목은 상속한다.

### 2.2 판정 로직을 읽는다

item의 `check.kind`와 로직 인자(`mode, rule, invalidate, relation, type, predicate, window의 기준점`)를 보고, 함수 본문(checks/*.py 또는 methods/*.py의 docstring과 코드)에서 다음을 뽑는다.

- **무엇과 무엇을 비교하나**: 산출물↔산출물, 산출물↔trace(실행·편집·읽기), 산출물↔diff/저장소, trace↔문서 읽기 시점, 산출물 내부
- **비교 형태**: 존재 / 집합 포함 / 키별 1:1 / 동일성 / 시간 순서 / 구간 안 금지·요구
- **구간 기준점**: 첫 소스 수정 이전, 마지막 수정 이후, 산출물 쓰기 사이, 단계 안, 전체
- **방향(극성)**: 하라 / 하지 말라

### 2.3 카탈로그에 대응시킨다

`sdlc_if/templates.yaml`에서 `kinds` 필드에 같은 kind·인자가 있는 템플릿을 찾는다. 없으면 같은 기술(S1~S10) 안에서 비교 형태가 같은 것을 찾는다. 머리말의 규칙:

- **인스턴스 차이**(같은 템플릿): 극성, 대상 범위(어느 파일·어느 절), 기록 위치·형식, 개수 값, 단순 단계 구간
- **템플릿 차이**: 반복 단위(이벤트마다 vs 한 번), 키별 대응 vs 집합, 비교 대상의 종류(산출물 vs trace vs 이슈), 구간 경계가 행동으로 정의되는 경우(첫 수정 이전 등)

맞는 것이 없으면 새 템플릿을 만든다: `NEW-<기술>-<이름>: {skill, name, kinds, status: candidate}` 로 넣고, 구현 항목이 생기면 `T-*` id를 준다. 09에서 새로 필요했던 것: 관찰 후 기록(시간), 산출물 내부 일관성, 이슈 충실성(코드), 키별 순서, 패치 계약 보존, 명령 형식, 문서 하나씩 읽기, 쓰기 전 존재 확인(후보로 이미 있음).

### 2.4 기록하고 검증한다

- ifeval·학습: `workflows/<wf>/constraints.yaml`에 `template:` 기입 → `python -m recipe.grpo.qwen3_5.sdlc_if.constraints <wf>` → `tests/test_sdlc_if.py`.
- aidlc_v4_eval: 아직 constraints.yaml이 없다. 09의 초안은 `if/scripts/eval09/eval_method_templates.py`(MAP 딕셔너리)와 결과 `eval_method_layers.yaml`에 있다. 정식으로 하려면 ruleset.yaml 구조(규칙 밑에 methods)에 맞춰 method마다 `template`을 두는 constraints 형식을 하나 정해야 한다(08·09 작성자의 제안: 규칙 → `methods: {key: {template, eval}}`).

### 2.5 자주 틀리는 곳

- **같은 kind라도 인자에 따라 템플릿이 다르다.** `cross_ref(relation=subset)`은 T-TR1, `cross_ref(keyed_ids)`는 T-TR1b, `cross_ref(record vs diff)`는 T-RF3.
- **범주(P/F/E/C/R/Q/A)와 템플릿은 1:1이 아니다.** A 보고 정확성은 T-RF1/RF2/RF3에 흩어지고 T-RF2는 A와 C 양쪽에 나온다. 범주로 템플릿을 추정하지 말 것.
- **엄격함은 템플릿의 성질이 아니다.** T-RF1이 ifeval에서는 0.15, 새 평가기에서는 0.80 통과다(09 6절). 같은 템플릿이라도 평가기 사이에서 수치 비교는 안 된다.
- **judge 항목은 카탈로그 밖이다.** 내용 적절성은 기술 S1~S10에 없다. 넣으려면 기술을 추가하고 별도 축(J)으로 보고한다.
- **디버그용 진단 항목**(`log_only`, `diagnostic`)은 템플릿은 붙이되 층 점수에서 뺀다.

## 3. 층 분류 절차

### 3.1 정의 (03 문서)

| 층 | 조건 | 묻는 것 |
|---|---|---|
| L1 | 학습 workflow가 같은 템플릿·비슷한 인스턴스를 **보상**한다 | 배운 것을 새 문서에서도 지키나 |
| L1-충돌 | 학습 규칙·문서가 **반대 방향**을 보상·지시한다 | 습관이 아니라 현재 문서를 따르나. 떨어지면 과적합 신호 |
| L2-중간 | 보상은 없지만 학습 **문서가 보여 주거나** 학습 템플릿의 **구조 확장**이다 | 가까운 일반화 |
| L2-먼 | 학습 rubric·문서 어디에도 없다 | 먼 일반화 |

### 3.2 판정 절차

1. 템플릿의 기본 층을 `templates.yaml`의 `eval.layer`에서 읽는다. 없는 템플릿(T-OR2, T-PR6, T-RD5, T-WD3, NEW-*)은 2~4로 직접 정한다.
2. **보상 여부**: 세 학습 workflow의 `constraints.yaml`에서 같은 템플릿의 `implemented` 항목을 찾는다. `grep -c "template: T-XX" workflows/{agentos_v2,openspec_ff,speckit_bug}/constraints.yaml`. 있으면 L1 후보.
3. **방향**: 학습 항목의 극성·구간이 평가 지시와 반대인지 본다. 반대면 L1-충돌. 근거(학습 workflow 문서 줄, 항목 id)를 `layer_reason`에 적는다. 02 문서의 "충돌" 표가 출발점이다.
4. **문서 노출**: 보상이 없으면 학습 문서(`workflows/<wf>/docs/`)에 그 지시가 적혀 있는지 grep한다. 있거나 학습 템플릿의 확장이면 L2-중간, 아니면 L2-먼.
5. **인스턴스 예외**를 적는다. ifeval의 예: T-PR5의 "기록한 명령의 형태" 항목은 L1, "전체 suite 실행 금지"는 L1C; T-AW3의 "재현 스크립트 실행"은 L2M(학습은 체크박스 tick 단위로만 보상), "테스트 재실행"은 L1. 09의 예: T-OR2의 재시도 상한·결과 분기는 L1, 검증 순서(H1c)는 L2M.
6. `eval.requirement`(must/should)를 정한다. 층 점수는 must만 쓴다. rubric의 requirement와 달라도 된다(T-TR1b는 rubric should, 평가 must).
7. `when:` 조건이 필요한 항목(예: Deviations가 `none`일 때만 의미 있는 항목)은 `section_is_none` 등으로 적는다.

### 3.3 층은 학습 rubric 버전에 상대적이다

- 04에서 speckit_bug의 `fix*.cross_ref.changes`(T-RF3)를 학습에서 뺐다. 새 rubric으로 학습한 checkpoint에는 T-RF3이 L2, **옛 rubric으로 학습한 지금 step27에는 L1**이다. 09는 템플릿 기본값(L2M)을 썼으므로 step27 기준으로는 고쳐야 한다(수치 영향은 작음).
- 따라서 `layers.yaml`은 "평가 rubric sha"뿐 아니라 "학습 rubric 세트"에도 묶여야 한다. 지금 구조는 전자만 검사한다. checkpoint마다 층 파일을 따로 두거나 `eval.layer_by_train:`처럼 조건부 라벨을 두는 것이 제안 상태다.
- 학습 쪽을 바꾸면(holdout, 규칙 뒤집기) 평가 항목의 층이 바뀐다. 아래 6절.

### 3.4 파일 생성

- ifeval: constraints.yaml의 `eval:`을 채우고 `python -m recipe.grpo.qwen3_5.workflows.aidlc_v4_ifeval.reward.build` → `reward/layers.yaml`(rubric sha 포함). `--check`로 동기 확인.
- aidlc_v4_eval: `if/scripts/eval09/eval_method_layers.py`가 method→층을 정하고 `aidlc_v4_eval.layers.draft.yaml`(layers.py 형식, 항목 id는 `form/B1@1`처럼 단계 포함)을 만든다. OVERRIDE/NEW_LAYER 딕셔너리가 인스턴스 예외와 새 템플릿의 층이다.

## 4. 층 점수와 분석

### 4.1 신호의 뜻 (`workflow_rubric/layers.py`)

- `layer/L`: 그 층 must 항목 중 pass/fail로 채점된 것의 점수 평균. 산출물이 없어 판정된 실패도 포함 → "결과적으로 얼마나 지켰나".
- `layer_reached/L`: 그 항목의 단계에 **도달한** run만(산출물 존재 또는 단계 문서 읽음; global은 항상) → "그 단계에 왔을 때 지켰나". 완주율 차이를 걷어낸다. 모델마다 도달 집합이 달라 **선택 편향**이 있으니, 모델 간 비교는 "두 run 모두 도달한 같은 task"로 제한하는 것이 안전하다(08 §6, 09 §4).
- `layer_should/L`: should 항목, 진단용.
- 09의 새 평가기는 부분 점수(0.5)를 주므로 "통과율"은 평균 점수다.

### 4.2 재채점

- 평가 에피소드(`rllm eval`)는 `artifacts.workflow_outputs`(실제 산출물), `patch`, `stray_files`를 갖고 있어 거의 정확히 오프라인 채점된다. 학습 에피소드(trainer episode logger)는 trace만 있어 `collected_from_replay`로 복원해야 하고 openspec_ff처럼 샌드박스 산물이 필요한 workflow는 0.15쯤 낮게 나온다(08 작성 중 확인).
- ifeval: `if/scripts/eval_step27/score_eval_layers.py` (trace 복원 + workflow_outputs 덮어쓰기 + patch 파싱 → `engine.evaluate` → `layers.signals`).
- aidlc_v4_eval: `if/scripts/eval09/score_eval09.py` (`Evaluation().from_outputs(outputs)` + `inputs(task, episode)` → `engine.evaluate`). 에피소드당 약 4초, 8 shard × 2 모델 병렬이면 5분 안쪽.
- judge를 켜려면 vLLM 엔드포인트와 `AIDLC_JUDGE_BASE_URL/MODEL`을 주고 `AIDLC_JUDGE_CACHE`를 지정한다. 켜지 않으면 judge 항목은 unavailable로 빠지고 J 층이 없다.
- 입력 아카이브: `trajectories/aidlc_v4_run1_qwen35-9b_wf-tcx-step27.tar.gz`(평가 499×2), `trajectories/20261023_040408_episodes.tar.zst`(학습 run, 39GB). 아카이브 안 디렉터리 이름이 서로 바뀌어 있다(`step27-full-r2/`에 base, `swegym-ckpt-r3/`에 step27). run 이름과 에피소드의 `model` 필드로 구분할 것.

### 4.3 분석 스크립트 (`if/scripts/`)

| 스크립트 | 내용 |
|---|---|
| `eval_step27/analysis_by_compliance.py` | (task, 항목) 전이: 유지 P(s27✓\|base✓) / 획득 P(s27✓\|base✗), base compliance 사분위 |
| `eval_step27/analysis_by_entry.py` | 진입·완주 run만 비교, 둘 다 완주 쌍 |
| `eval_step27/analysis.txt`, `analysis_by_resolve.txt` | 전체·템플릿별·해결 묶음별 결과 (생성 스크립트는 인라인이었음; per_task.csv로 재계산 가능) |
| `eval09/analysis_eval09.py` | 09의 1~9절 전부: 전체·범주·층·템플릿·method·전이·해결 묶음·완주·ifeval 대조·정보 있는 method |

### 4.4 해석할 때 지킬 것 (08·09 작성 중 정리한 것)

- **두 가지 주장을 구분한다.** "이 N개 항목에서 step27이 낫다"는 task 499쌍으로 검정되는 주장(A). "이 층의 지시 일반에서 …"는 항목(템플릿)이 표본인 주장(B)이고 k가 5~7이면 구간이 0을 포함한다. 쌍 수를 늘려도 B의 불확실성은 줄지 않는다(pseudo-replication).
- **층 간 Δ 비교는 통제된 비교가 아니다.** L1은 형식 항목이 지배하고 충돌·L2는 행동 항목이라, "충돌이라서 덜 올랐다"는 말할 수 없다. 같은 템플릿의 충돌/비충돌 인스턴스를 짝지어야 한다(예: T-RD6 vs T-RD3/RD4, T-AW4 vs T-AW2/AW3).
- **천장·바닥 항목은 k에 안 들어간다.** base 통과율 0.1~0.9, 두 run 모두 도달 n≥50 정도를 "정보 있음"으로 세라(09 §3·§9). 같은 템플릿의 인스턴스 여러 개는 1개로 센다(ICC≈1).
- **전체 기준 vs 도달 기준으로 부호가 뒤집힐 수 있다.** 08의 T-AW4: 전체 −0.08(유의), 도달 +0.11(유의). base가 산출물을 안 써서 자동 통과한 항목 때문. 기준을 명시하지 않은 "악화 없음"은 성립하지 않는다.
- **항목 단위 검정은 McNemar**(같은 task에서 base만 통과 b vs step27만 통과 c의 이항검정)이 설계에 맞다. 층 단위 B 주장은 항목 Δ의 t-구간(자유도 k−1) 또는 task×항목 two-way bootstrap.
- **compliance↔해결률 상관은 base의 성질이다**(base 해결 task 0.42 vs 실패 0.27; step27 0.81 vs 0.76). 인과로 읽지 말 것.

## 5. 지금 상태

| 항목 | 상태 |
|---|---|
| 08 (ifeval 채점, 층별 분석) | 완료. 문서·스크립트 `if/`에 있음, untracked |
| 09 (새 평가기 채점, 층별 분석) | 완료. **층 라벨은 초안**, 검토 안 됨 |
| aidlc_v4_eval의 constraints.yaml | 없음. method→템플릿 매핑은 `eval09/eval_method_layers.yaml`에만 |
| templates.yaml의 새 템플릿 7개 | 미등록 (NEW-* 이름으로 초안에만) |
| T-RF3 층 | 템플릿 기본 L2M. step27(옛 rubric 학습)에는 L1이 맞음 |
| T-TR1b (키별 대응) | 새 평가기에 method 없음 → 08의 L2-먼 근거를 09에서 확인 못 함 |
| judge | 미실행 |
| 두 브랜치 | `feat/workflow-if-templates`(템플릿·if 문서), `feat/aidlc-openhands-sdk-recipe`(새 평가기). 어느 쪽에 통합할지 미정 |
| 통계 검정(McNemar, bootstrap) | 계획만 있음. 08·09의 ± 구간은 task 쌍 기준(주장 A) |
| 08 문서의 L1C·L2F 표현 | "이 5개/6개 항목에서"로 좁혀야 한다는 결론, 아직 수정 안 함 |
| 데이터 | 아카이브는 `trajectories/`. 풀어 둔 것과 채점 결과(`eval_out`, `eval09_out`)는 세션 scratchpad라 사라짐. `if/scripts/*/analysis*.txt`, `per_task.csv`만 남음. 항목별 채점 행이 필요하면 다시 채점(평가 499×2는 10분 안쪽) |

## 6. 논의만 된 다음 단계 (k를 늘리는 방법)

08·09의 한계는 충돌·L2-먼 템플릿 수다. 정리된 선택지:

1. **학습 holdout 교차 설계 (L2 k 늘리기).** 평가에도 있고 학습 rubric에도 있는 템플릿을 두 묶음으로 나눠 run A는 X 제외, run B는 Y 제외. 같은 평가 항목을 "본 상태/안 본 상태"로 비교. 뺄 수 있는 후보 12개(T-FM3, FM6, TR1, WD1, WD2, AW2, AW3, RF1, RF2, RF4, PR5, TR2), 구조 항목(FM1, FM2, RD1, OR1)은 불가. rubric만 빼면 학습 문서 노출 때문에 L2-중간, 문서까지 지워야 L2-먼.
2. **학습 규칙 뒤집기 (충돌 k 늘리기).** 평가는 고정하고 학습 문서+rubric에서 반대 규칙을 보상. 비용 중립인 것만: T-WD2(living spec), T-PR1(TDD), T-RD3(문서 통독), T-RD1(explore first), T-TR1(태그 없는 step 허용), T-FM2/FM6(해당 없는 절 생략), T-AW2(수정 후 첫 실행; TDD와 양립 불가), T-AW6(모듈 재실행), T-RF4(신규 파일 경로). 전체 suite 실행·점진 쓰기는 비용 때문에 제외. 짝은 "같은 평가 항목, 다른 학습 조건".
3. **평가 변형본으로 충돌 쌍 만들기.** 평가 문서 사본에 반대 지시를 넣어 같은 인스턴스의 충돌/비충돌 쌍. 평가 고정과는 어긋남.
4. **rubric만 추가 (문서 고정).** 새 평가기가 이미 이것을 했다. 그 결과가 09의 새 템플릿 7개이고, 정보 있는 것은 2~3개.

목표 수치: 층 평균 Δ를 ±0.1로 말하려면 템플릿 12~18개, 충돌 vs 비충돌 격차 0.15를 잡으려면 짝 8~10개.

## 7. 처음 한 주에 할 일 제안

1. `ruleset.md`와 `templates.yaml`을 나란히 놓고 `eval09/eval_method_layers.yaml`의 매핑 189개를 검토한다. 갈릴 만한 곳은 09 문서 7절에 적어 두었다.
2. 검토한 매핑을 constraints 형식으로 올릴지, 어느 브랜치에 둘지 정한다.
3. T-RF3을 step27 기준 L1로 두고 09의 층 수치를 다시 뽑는다(스크립트의 OVERRIDE에 두 줄).
4. 08 문서의 L1C·L2F 결론을 "이 N개 항목에서"로 고친다.
5. k를 늘리는 방향(6절 1·2)을 정하면 학습 rubric·문서 수정으로 넘어간다.
