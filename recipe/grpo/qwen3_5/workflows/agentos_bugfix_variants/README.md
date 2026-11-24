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
| `variants/` | 생성물 (문서, instruction, system prompt). 직접 고치지 않음 |
| `__init__.py` | 변형마다 `WorkflowSpec` 을 만들어 `SPECS` 로 내보냄. `workflows/__init__.py` 가 등록함 |
| `run_eval.sh` | 워크플로 하나를 평가함 |
| `run_all.sh` | 워크플로 여러 개를 차례로 평가함 |

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

# 1. 과제 하나로 에이전트 이미지를 먼저 만듦 (아래 "알려진 문제" 참고)
bash $D/run_eval.sh agentos_bugfix_v5all base <served-model-name> http://<host>:<port>/v1 1 0

# 2. smoke 3과제
bash $D/run_eval.sh agentos_bugfix_v5all base <served-model-name> http://<host>:<port>/v1 1 0,1,2

# 3. 1차: 대조, 기준, 합친 변형 (499 과제 × 3회씩)
bash $D/run_all.sh base <served-model-name> http://<host1>:<port>/v1,http://<host2>:<port>/v1 3 \
  agentos_bugfix agentos_bugfix_v0base agentos_bugfix_v5all

# 4. 2차: 합친 변형이 기준보다 3%p 이상 높을 때만
bash $D/run_all.sh base <served-model-name> <endpoints> 3 \
  agentos_bugfix_v1result agentos_bugfix_v2place agentos_bugfix_v3pre agentos_bugfix_v4docs
```

- endpoint를 쉼표로 여러 개 주면 그 수만큼 shard로 나눠 동시에 돎 (과제 i → shard i % endpoint 수)
- 설정은 기존 평가와 같음: step_limit 250, thinking on, instruction suffix, FinishTool만 기본 도구, strict_tool_calls, git history 숨김, 에이전트 네트워크 차단, sampling은 `recipe/eval/config/qwen3_5.yaml`
- 결과 위치: `$RLLM_HOME/eval_results/wfvar/<워크플로>__<run key>_x<attempts>/`
  - `results/s<N>.json`, `shards/s<N>/episodes/episodes/episode_*.json`, `logs/s<N>.log`, `run_info.txt`, `run.log`
  - `run.log` 마지막 줄에 `ALL DONE: <해결>/<전체> resolved` 가 찍힘
- 끝난 shard는 다시 돌리면 건너뜀
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
