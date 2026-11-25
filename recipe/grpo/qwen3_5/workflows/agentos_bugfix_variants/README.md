# agentos_bugfix 지침 변형

- 목적: `agentos_bugfix` 워크플로의 지침 문장을 바꾼 변형을 만들어 SWE-bench Verified 해결률이 오르는지 확인함
- 배경: 학습 전 Qwen3.5-9B의 해결률이 워크플로 없음 57.6%, `agentos_bugfix` 48.8% (499 과제 × 3회)
  - 워크플로를 쓰면 기존 테스트 실행이 rollout당 7.38건에서 3.87건으로 줄어듦
  - 마지막 소스 수정 뒤 테스트 통과를 읽고 제출하는 비율이 59.4%에서 43.0%로 줄어듦
  - 위 값은 저장소 밖 분석 결과임 (2026-11-24, 네 평가 조건의 trajectory 집계)
- 변형에는 채점기가 없어 해결률만 나옴
- 네 명령(shape-spec, write-spec, create-tasks, implement-tasks)과 spec 폴더 구조는 모든 변형에서 그대로임

## 구성

| 파일 | 내용 |
|---|---|
| `build.py` | `agentos_bugfix` 문서에서 정해진 문장을 찾아 바꿔 `variants/<이름>/` 에 씀 |
| `structure/` | 구조 변형의 손으로 쓴 원문 (overview, instruction, system prompt 문단)과 기본 system prompt의 절차 구역 |
| `variants/` | 생성물 (문서, instruction, system prompt). 직접 고치지 않음 |
| `__init__.py` | 변형마다 `WorkflowSpec` 을 만들어 `SPECS` 로 내보냄. `workflows/__init__.py` 가 등록함 |
| `run_eval.sh` | 워크플로 하나를 평가함 |
| `run_all.sh` | 워크플로 여러 개를 차례로 평가함 |
| `analyze.py` | 평가 결과에서 해결률, 최종 patch와 정답 patch의 관계(단계), 워크플로를 따랐는지를 냄 |

- 바꿀 문장이 원본에 정확히 한 번 있지 않으면 빌드가 멈춤
- `agentos_bugfix` 문서가 바뀌면 `python build.py` 로 다시 만들고 `python build.py --check` 로 확인함
- `python build.py --list` 는 변형별 후보와 수정 수를 보여 줌

## 후보

| 기호 | 후보 | 바꾸는 곳 |
|---|---|---|
| X | spec 파일을 file editor로 쓰게 함 | overview.md |
| A | 기존 테스트 모듈과 실행 명령을 계획 단계에서 찾아 한 번 돌리고 spec.md의 `## Existing Tests` 에 적음 | write-spec.md, create-tasks.md, implement-tasks.md |
| L | 러너가 안 뜬 것은 결과가 아니라고 적고, 실행 방법을 찾아 다시 돌리게 함 | implement-tasks.md |
| H | 마지막 수정 뒤 기존 테스트의 통과·실패 수를 얻은 뒤에만 체크하고 보고서를 씀 | overview.md, create-tasks.md, implement-tasks.md |
| E | 새 테스트의 기본 위치를 기존 테스트 모듈로 하고, `verify/` 는 맞는 모듈이 없을 때만 씀 | overview.md, create-tasks.md, implement-tasks.md |
| K | PHASE 3에서 테스트 디렉터리의 나머지도 한 번 돌림 | implement-tasks.md |
| F | 과제가 바꾸라는 동작을 단정하는 기존 테스트는 고칠 수 있게 함 | overview.md, create-tasks.md, implement-tasks.md |
| B | shape-spec에서 보고된 동작을 실행해 보고 requirements.md의 `## Observed Behavior` 에 적음 | shape-spec.md |
| M | x.1 테스트를 수정 전에 돌려 실패를 확인함 | create-tasks.md, implement-tasks.md |
| G | 파일 없는 즉석 확인(`python -c`)을 허용한다고 적음 | overview.md |
| C | 계획 문서 양식을 줄임 | shape-spec.md, write-spec.md |
| I | tasks.md 예시에서 테스트 검토 그룹을 뺌 | create-tasks.md |
| D | 기본 system prompt의 테스트 문장 3개를 워크플로 안내 뒤에 덧붙임 | system-prompt.j2 |
| J | `verify/` 스크립트를 테스트 함수로 쓰고 러너로 돌림 | create-tasks.md, implement-tasks.md |
| N | 계획 문서에는 성립해야 할 동작만 적고 코드 변경은 implement-tasks에서 정함 (3차) | overview.md, shape-spec.md, write-spec.md, create-tasks.md, implement-tasks.md |

- F는 근거가 약해 예비 변형에만 넣음
- "전체 suite 금지" 삭제와 재시도 상한 완화는 넣지 않음. 데이터에서 원인이 아닌 것으로 나옴

## 변형

| 워크플로 이름 | 후보 | 겨냥하는 것 | 문서 수정 수 |
|---|---|---|---|
| `agentos_bugfix_v0base` | X | 기준 (공통 수정만) | 1 |
| `agentos_bugfix_v1result` | X A L H | 기존 테스트 결과 확보 | 8 |
| `agentos_bugfix_v2place` | X E K | 테스트 위치와 범위 | 6 |
| `agentos_bugfix_v3pre` | X B M G | 수정 전 확인 | 7 |
| `agentos_bugfix_v4docs` | X C I | 문서 부담 | 12 |
| `agentos_bugfix_v5all` | X A L H E K B M G C I D J | 전부 합친 것 | 28 |
| `agentos_bugfix_v2fplace` | X E K F | 예비 (기본 실행 목록에 없음) | 6 |
| `agentos_bugfix_p1nofix` | N | 수정 내용을 정하는 시점 (3차, 공통 수정 X 없음) | 10 |

## 구조 변형 (2차, 2026-11-25)

- 만든 이유: 1차 중간 결과(499 과제 × 1회)에서 문장 변형이 학습 전 모델의 해결률을 움직이지 못함
  - 학습 전 모델: 대조 51.5%, v0base 50.9%, v5all 50.7%, v1result 52.1%, v2place 49.3%, 워크플로 없음 59.3%
  - 1회 실행끼리의 차이는 95% 구간 반폭이 약 4%p임 (기존 3회 실행 자료에서 시도 하나씩 뽑아 잰 값). 위 변형은 모두 대조와 구분되지 않음
  - 문장 변형은 전부 "코드 수정 전에 문서 넷"이라는 구조를 유지함. 손실이 그 구조에서 오는지는 문장 변형으로 알 수 없음
- 구조 변형은 어떤 문서를 언제 쓰는지를 바꿈
- 네 변형 모두 system prompt의 기본 절차 구역(탐색, 분석, 테스트, 구현, 검증 다섯 항목)을 남기고, 그 뒤에 `/agent-os/overview.md` 를 가리키는 문단을 붙임
  - 대조(`agentos_bugfix`)는 그 구역을 Agent OS 안내로 통째로 바꿈
- 공통 수정 X는 넣지 않음. 1차 smoke에서 모델이 따르지 않았고, `s4prompt` 가 대조와 한 가지만 다르게 하기 위함

| 워크플로 이름 | 코드 수정 전에 쓰는 문서 | 코드 수정 뒤에 쓰는 문서 | system prompt 절차 구역 |
|---|---|---|---|
| (워크플로 없음) | 없음 | 없음 | 기본 |
| `agentos_bugfix_s1report` | 없음 | 보고서 | 기본 + 안내 문단 |
| `agentos_bugfix_s2after` | 없음 | requirements, spec, tasks, 보고서 | 기본 + 안내 문단 |
| `agentos_bugfix_s3tasks` | tasks | 보고서 | 기본 + 안내 문단 |
| `agentos_bugfix_s4prompt` | requirements, spec, tasks | 보고서 | 기본 + 안내 문단 |
| `agentos_bugfix` (대조) | requirements, spec, tasks | 보고서 | Agent OS 안내로 교체 |

- 읽는 법: 워크플로 없음 → `s1report` → `s3tasks` → `s4prompt` → 대조 순서로 한 가지씩 더해짐
  - 워크플로 없음 → `s1report`: 워크플로 문서를 먼저 열고 마지막에 보고서를 쓰는 것의 비용
  - `s1report` → `s3tasks`: 코드 전에 작업 목록 하나를 쓰고 implement-tasks 규칙을 따르는 것의 비용
  - `s3tasks` → `s4prompt`: 계획 문서 둘(requirements, spec)을 더 쓰는 것의 비용
  - `s4prompt` → 대조: system prompt의 기본 절차 구역을 지우는 것의 비용
  - `s1report` → `s2after`: 같은 문서 넷을 코드 수정 뒤에 쓸 때의 비용. `s2after` 가 `s1report` 에 가깝고 `s4prompt` 가 낮으면 문서 양이 아니라 "코드 전에 계획"이 원인임
- 변형별 차이
  - `s1report`: 문서는 overview.md 하나뿐임. 보고서 양식은 그 안에 있고 작업 목록 절은 뺌
  - `s2after`: 명령 문서 넷은 대조와 같음. overview.md가 "먼저 평소대로 풀고, 수정과 테스트가 끝난 뒤 네 명령을 기록으로 수행"이라고 정함
  - `s3tasks`: create-tasks가 spec 폴더를 만들고 과제 글과 저장소에서 바로 작업 목록을 만듦 (create-tasks 5곳, implement-tasks 2곳 수정)
  - `s4prompt`: 대조와 다른 곳은 system prompt와 overview.md의 한 문장임. 대조의 overview.md는 "이 순서가 다른 절차를 대신한다"고 하는데, 기본 절차를 남긴 채 그 문장을 두면 다시 무효가 되므로 "system prompt의 절차를 이 순서 안에서 수행한다"로 바꿈
- 한계: 1회 실행의 구간 반폭이 4%p라 한 단계의 차이가 그보다 작으면 가릴 수 없음. 7.8%p가 한두 단계에 몰려 있을 때만 위치가 보임

## 3차 (2026-11-25): 손실 위치와 수정한 실행 계획

### 손실이 생기는 자리

- 기존 3회 실행 자료(조건당 1497 rollout)에서 최종 patch를 정답 patch와 맞대어 나눈 결과임 (저장소 밖 분석, `loss_origin.md`)
- 손실은 두 군데임
  - 소스 patch 없이 끝난 rollout: 학습 전 모델 2.7% → 8.7%, 학습 모델(step 27) 1.6% → 3.9% (워크플로 없음 → agentos_bugfix)
  - 정답과 같은 자리를 고친 rollout의 해결률: 학습 전 70.7% → 65.1%, 학습 모델 71.7% → 64.4%
- 다른 파일을 고친 비율(10.3% 대 9.9%)과 정답 파일 일부만 고친 비율(9.3% 대 10.0%)은 같음. 파일 찾기는 원인이 아님
- 테스트 행동의 비율을 워크플로 없음과 같게 맞춰도 해결률 변화는 학습 전 −0.7%p (95% 구간 −2.5 ~ +1.4), 학습 모델 +1.0%p (−0.5 ~ +2.3). 1차 문장 변형이 겨냥한 곳은 손실의 자리가 아님
- 같은 자리 손실은 소스를 1회만 수정한 rollout에 몰려 있음 (해결률 83% → 74%, 두 모델 모두)
- 워크플로 조건에서 수정 내용은 계획 문서에서 정해짐
  - 같은 과제의 푼 시도와 못 푼 시도 32쌍을 가려 놓고 읽은 결과, 계획에 적힌 수정이 통과할 것으로 판정된 것이 푼 시도 32건 중 26건, 못 푼 시도 32건 중 7건
  - 못 푼 시도 중 22건은 계획이 틀렸고 patch가 그 계획을 그대로 따름
- 학습 전 모델의 "소스 patch 없음" 가운데 계획 단계에서 끝난 것(전체의 4.5%)은 학습 모델에서 0건이라 겨냥하지 않기로 함

### 추가한 변형: `agentos_bugfix_p1nofix`

- 문서 넷과 순서는 대조와 같음. 계획 문서(requirements.md, spec.md, tasks.md)에는 성립해야 할 동작과 고칠 파일만 적고, 코드 변경 자체(어느 조건·값·호출을 무엇으로 바꾸는지)는 implement-tasks PHASE 2에서 코드를 보고 실행해 본 뒤 정하게 함
- 대조와 다른 곳은 문서 10곳뿐임 (overview.md 1, shape-spec.md 2, write-spec.md 4, create-tasks.md 2, implement-tasks.md 1). instruction과 system prompt는 대조와 같음
- 실행·재현을 요구하는 문장은 넣지 않음. 바뀌는 것은 수정 내용을 정하는 시점뿐임
- 읽는 법: 대조보다 "같은 자리 rollout의 해결률"이 오르면 문서에 수정을 먼저 적는 것이 손실의 원인임. 계획을 먼저 쓰는 구조는 유지하므로, 효과가 있으면 그대로 쓸 수 있는 워크플로가 됨
- 모델이 따랐는지는 자동으로 못 셈. spec.md 10건쯤을 읽어 코드 변경이 적혀 있는지 봐야 함

### 수정한 실행 계획

- 바꾼 이유
  - 1회 실행의 95% 구간 반폭은 해결률 4.0~4.3%p, 같은 자리 해결률 4.7~5.2%p임. 3회 실행은 2.5%p, 2.9~3.1%p임. 네 변형을 1회씩 돌리면 단계 사이 차이를 가를 수 없음
  - 학습 전 모델은 계획 단계 종료가 섞임. `s1report`, `s2after` 에는 계획 단계가 없어 그 몫(약 2.6%p)이 저절로 회복됨. 학습 모델에는 그 몫이 없음
  - 변형은 모델로 돌려 본 적이 없음. 따르지 않으면 `s2after` 는 워크플로 없음과 같은 값이 나와 "순서가 원인"으로 잘못 읽힘
- 순서
  1. 따랐는지 확인: `s2after`, `s4prompt`, `p1nofix` 를 20과제씩 돌리고 `analyze.py` 의 "워크플로를 따랐는지" 표를 봄
  2. 본 실행: 학습 모델로 `s2after`, `s4prompt`, `p1nofix` 를 3회씩, 대조와 워크플로 없음은 이미 있는 1회에 2회를 더함
  3. 분석: `analyze.py` 로 해결률, 소스 patch 없음 비율, 같은 자리 해결률을 따로 냄. 1차 변형의 결과 폴더도 같이 넣음
  4. `s1report`, `s3tasks` 는 `s2after` 가 대조보다 3%p 이상 높을 때만 돌림
- 변형별로 읽는 값

| 비교 | 보는 값 | 이렇게 나오면 |
|---|---|---|
| `s2after` − 대조 | 같은 자리 rollout의 해결률 | 오르면 코드보다 먼저 문서를 쓰는 순서가 원인 |
| `s4prompt` − 대조 | 같은 자리 rollout의 해결률 | 오르면 system prompt의 기본 절차 구역이 사라진 것이 원인 |
| `p1nofix` − 대조 | 같은 자리 rollout의 해결률 | 오르면 문서에 수정 내용을 먼저 적는 것이 원인 |
| `s2after` − 워크플로 없음 | 해결률 | 0에 가까우면 문서를 뒤에 쓰는 비용은 없음 |

```bash
# 저장소 루트에서 실행함
export RLLM_HOME=<데이터셋과 결과가 놓일 곳>
D=recipe/grpo/qwen3_5/workflows/agentos_bugfix_variants
W=$RLLM_HOME/eval_results/wfvar
M=<served-model-name>; U=<endpoints>

# 0. 에이전트 이미지가 없는 장비라면 과제 하나로 먼저 만듦 ("알려진 문제" 참고)
bash $D/run_eval.sh agentos_bugfix_s2after imgbuild $M $U 1 0

# 1. 따랐는지 확인 (20과제, 1회). 결과 폴더 이름 끝에 -smoke 가 붙음
IDX=$(seq -s, 0 25 498)
for wf in agentos_bugfix_s2after agentos_bugfix_s4prompt agentos_bugfix_p1nofix; do
  bash $D/run_eval.sh $wf step27 $M $U 1 $IDX
done
python $D/analyze.py \
  --run s2after=$W/agentos_bugfix_s2after__step27_x1-smoke \
  --run s4prompt=$W/agentos_bugfix_s4prompt__step27_x1-smoke \
  --run p1nofix=$W/agentos_bugfix_p1nofix__step27_x1-smoke

# 2. 본 실행. 대조와 워크플로 없음은 run key 를 달리해 2회를 더함 (1차의 1회분과 합쳐 3회)
bash $D/run_all.sh step27 $M $U 3 agentos_bugfix_s2after agentos_bugfix_s4prompt agentos_bugfix_p1nofix
bash $D/run_all.sh step27b $M $U 2 agentos_bugfix none

# 3. 분석. 쉼표로 이은 폴더는 한 조건으로 합쳐짐
python $D/analyze.py \
  --run 대조=$W/agentos_bugfix__step27_x1,$W/agentos_bugfix__step27b_x2 \
  --run 없음=$W/none__step27_x1,$W/none__step27b_x2 \
  --run s2after=$W/agentos_bugfix_s2after__step27_x3 \
  --run s4prompt=$W/agentos_bugfix_s4prompt__step27_x3 \
  --run p1nofix=$W/agentos_bugfix_p1nofix__step27_x3 \
  --run v1result=$W/agentos_bugfix_v1result__step27_x1 \
  --compare 대조 s2after --compare 대조 s4prompt --compare 대조 p1nofix --compare 없음 s2after --compare 대조 v1result \
  --out $W/round3_step27.md
```

- 1차 결과 폴더의 이름은 그때 쓴 run key에 따라 다름. 위 `step27` 자리에 실제 이름을 넣음
- `analyze.py` 는 표준 라이브러리만 쓰고, 정답 patch는 `$RLLM_HOME/datasets/swebench_verified_all/<과제>/tests/config.json` 에서 읽음 (다른 곳이면 `--dataset`)
- `analyze.py` 검산 (기존 3회 실행 자료, 학습 전 모델의 워크플로 없음과 대조, 각 1497 rollout)
  - 해결률 57.6%, 48.8%와 같은 자리 해결률 70.7%, 65.1%가 앞선 분석과 같음
  - 단계 분류는 앞선 분석과 조건당 5건, 11건만 다름. 모두 "다른 파일"에서 "소스 patch 없음"으로 옮겨진 것임 (저장소에 남긴 임시 스크립트만 있는 patch, 소스 패키지 `django/test/` 를 잘못 센 것). 소스 patch 없음 비율은 2.9%, 9.0%로 나옴
  - "소스 수정 step 수" 구간(1회 이하, 2회, 3회 이상)은 채점기의 trajectory 재생으로 센 값과 워크플로 없음 95.4%, 대조 92.1% 일치함. 첫 소스 수정 step은 두 조건 모두 95% 일치함
  - 1회 이하 수정 rollout의 해결률은 84.2%, 73.3%로 나옴 (재생 기준 83.4%, 74.4%)
- 1번에서 볼 것
  - `s2after`: 문서 넷이 있고, "첫 소스 수정이 첫 문서 작성보다 앞"이 대부분이어야 함. "문서를 쓰기 시작한 뒤 소스를 수정함"이 높으면 문서 단계에서 코드를 다시 건드리는 것이므로 결과를 순서의 효과로 읽을 수 없음
  - `s4prompt`, `p1nofix`: 문서 넷이 있고, "첫 소스 수정이 첫 문서 작성보다 앞"이 0에 가까워야 함
- `s2after`, `s4prompt` 의 문서는 3차 커밋에서 고쳐짐 (검토에서 나온 모순 수정). 그 전 커밋(`4e5607bd`)으로 돌린 결과가 있으면 섞지 않음. `run_info.txt` 의 workflow fingerprint로 구분함 (이 커밋의 값: `s2after` `f988e2553be3`, `s4prompt` `4aece598c755`, `p1nofix` `46ba0e541176`)
- 학습 모델은 지금 문서로 학습된 모델임. 구조를 바꾼 결과는 "새 구조로 학습한 모델"의 값이 아니라 "학습된 모델에 다른 구조를 준 값"임

## 평가를 돌릴 장비에 필요한 것

- 이 브랜치의 checkout과 rllm이 설치된 파이썬 환경
  - 기본은 저장소의 `.venv` 를 씀. 다른 곳이면 `PY=<python 경로>` 로 줌
- docker
  - 과제마다 `rllm-task-<과제>` 이미지를 실행 때 빌드함 (과제당 약 4.2GB, 기반 이미지는 `swebench/sweb.eval.x86_64.*`)
  - 에이전트 이미지 `rllm-agent-<hash>` 도 처음 한 번 빌드함 (약 1.5GB)
- 데이터셋 `swebench_verified_all` (499 과제)이 `$RLLM_HOME/datasets/` 에 등록돼 있어야 함
  - 만드는 법: `recipe/eval/swebench-verified/README.md` 의 `prepare_swebench_verified_subset.py --ids ... --name swebench_verified_all`
- 모델 서버: OpenAI 호환 endpoint. 기존 평가와 같은 vLLM 옵션이어야 비교가 됨
  - `--max-model-len 262144 --enable-prefix-caching --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_xml`
  - 기존 평가는 GPU 한 장에 서버 하나, 8대, 서버당 동시 실행 24

## 실행

```bash
D=recipe/grpo/qwen3_5/workflows/agentos_bugfix_variants
export RLLM_HOME=<데이터셋과 결과가 놓일 곳>

# 1. 과제 하나로 에이전트 이미지를 먼저 만듦 (아래 "알려진 문제" 참고). 2번과 결과 폴더가 겹치지 않게 run key 를 달리함
bash $D/run_eval.sh agentos_bugfix_v5all imgbuild <served-model-name> http://<host>:<port>/v1 1 0

# 2. smoke 3과제
bash $D/run_eval.sh agentos_bugfix_v5all base <served-model-name> http://<host>:<port>/v1 1 0,1,2

# 3. 1차: 대조, 기준, 합친 변형 (499 과제 × 3회씩)
bash $D/run_all.sh base <served-model-name> http://<host1>:<port>/v1,http://<host2>:<port>/v1 3 \
  agentos_bugfix agentos_bugfix_v0base agentos_bugfix_v5all

# 4. 2차: 합친 변형이 기준보다 3%p 이상 높을 때만
bash $D/run_all.sh base <served-model-name> <endpoints> 3 \
  agentos_bugfix_v1result agentos_bugfix_v2place agentos_bugfix_v3pre agentos_bugfix_v4docs
```

```bash
# 5. 구조 변형 (2차)
bash $D/run_all.sh base <served-model-name> <endpoints> 1 \
  agentos_bugfix_s1report agentos_bugfix_s4prompt agentos_bugfix_s3tasks agentos_bugfix_s2after
```

- 구조 변형의 순서는 정보가 큰 순서임: `s1report` 와 `s4prompt` 가 양 끝을 먼저 가름
- endpoint를 쉼표로 여러 개 주면 그 수만큼 shard로 나눠 동시에 돎 (과제 i → shard i % endpoint 수)
- 설정은 기존 평가와 같음: step_limit 250, thinking on, instruction suffix, FinishTool만 기본 도구, strict_tool_calls, git history 숨김, 에이전트 네트워크 차단, sampling은 `recipe/eval/config/qwen3_5.yaml`
- 결과 위치: `$RLLM_HOME/eval_results/wfvar/<워크플로>__<run key>_x<attempts>/`. 과제 목록(task_indices)을 주면 이름 끝에 `-smoke` 가 붙음
  - `results/s<N>.json`, `shards/s<N>/episodes/episodes/episode_*.json`, `logs/s<N>.log`, `run_info.txt`, `run.log`
  - `run.log` 마지막 줄에 `ALL DONE: <해결>/<전체> resolved` 가 찍힘
- 끝난 shard는 다시 돌리면 건너뜀. 오류로 끝난 과제를 다시 돌리려면 그 shard의 `results/s<N>.json` 을 지우고 다시 실행함
- 같은 결과 폴더를 다른 과제 목록이나 다른 endpoint 수로 다시 쓰면 실행이 멈춤 (`run_sig.txt`). 그때는 run key를 달리함
- 대조(`agentos_bugfix`)를 다시 돌리는 이유: 기존 48.8%는 다른 장비·다른 vLLM 배치에서 잰 값이라, 같은 환경의 값이 있어야 변형과 비교가 됨
- 워크플로 없음 대조가 필요하면 워크플로 이름에 `none` 을 줌

## 판정

- 499 과제 × 3회에서 해결률 차이의 95% 구간은 반폭이 약 2.5%p (과제 단위 짝 비교 bootstrap, 기존 네 조건에서 잰 값)
- 3%p보다 작은 회복은 가릴 수 없음
- 메울 차이는 8.8%p (48.8% 대 57.6%)
- 학습 전 모델로 먼저 봄. 학습된 모델은 현재 문서로 학습돼서 문서를 바꾸면 학습 때와 다른 입력이 됨
- 해결률보다 먼저 겨냥한 행동이 움직였는지 봄. 행동이 움직였는데 해결률이 그대로면 그 요인은 원인이 아니라는 결론임

| 변형 | 확인할 행동 | 현재 지침 값 | 워크플로 없음 값 |
|---|---|---|---|
| v1result | 마지막 소스 수정 뒤 기존 테스트 결과가 읽힌 rollout 비율 | 49.4% | 64.2% |
| v1result | 러너를 불렀지만 결과 없이 제출한 비율 | 33.1% | 19.8% |
| v2place | 기존 테스트 모듈을 수정한 rollout 비율 | 18.5% | 46.9% |
| v2place | 처음 통과 뒤 실패를 만나는 구간 비율 | 26.6% | 39.8% |
| v3pre | 첫 소스 수정 전에 아무 실행도 없는 rollout 비율 | 36.2% | 21.5% |
| v3pre | rollout당 파일 없는 python 실행 건수 | 5.35 | 11.86 |
| v4docs | rollout당 문서 작업 외 step 수 | 54.6 | 74.0 |

## smoke에서 확인한 것 (2026-11-24, `agentos_bugfix_v5all`, 3과제 × 1회)

- 결과: 해결 1건, 미해결 1건, 오류 1건
- 돈 2건은 변형 문서로 돌았고 산출물 5개를 모두 씀
  - 두 건 모두 spec.md에 `## Existing Tests`, requirements.md에 `## Observed Behavior` 를 적음
  - pytest 호출 11회, 24회 가운데 `verify/` 대상은 0회
- 후보 X는 두 건 모두 따르지 않음
  - 문장은 읽었으나 spec 파일을 file editor로 쓴 호출이 0회이고, 터미널 heredoc으로 씀 (6회, 12회)
  - 여러 명령 거부는 0회, 10회
  - 3과제만 본 것이라 비율은 모름. `v0base` 와 대조의 차이가 작게 나올 수 있음

## 알려진 문제

- 에이전트 이미지가 없는 장비에서 여러 과제가 동시에 시작하면 같은 이미지를 동시에 빌드하다가 일부가 `image ... already exists` 로 실패함
  - 실패한 과제는 재시도 없이 오류로 남음 (smoke의 오류 1건이 이것임)
  - 과제 하나짜리 실행으로 이미지를 먼저 만들어 두면 이후 실행은 재사용함
- 과제 이미지 태그 `rllm-task-<과제>` 는 docker daemon을 같이 쓰는 다른 평가와 공유됨
  - 실행할 때마다 다시 빌드해 같은 태그를 덮어씀 (`RLLM_REUSE_TASK_IMAGES=1` 이면 있는 태그를 재사용함)
