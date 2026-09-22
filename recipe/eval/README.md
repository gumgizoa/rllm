# rLLM evaluation (ref. harbor)

`rllm eval` -> SWE-bench Verified와 SWE-bench Pro 평가 방법

실행 방식은 두 가지:

| Way | `--agent` | Runtime |
| --- | --- | --- |
| **harbor** | `harbor:mini-swe-agent` 처럼 `harbor:` 접두어 | Harbor `Trial.run()` — 환경 build, agent, verifier를 Harbor가 모두 담당 |
| **native** | `mini-swe-agent`, `oracle` 처럼 접두어 없음 | rLLM `SandboxTaskHooks` + rLLM harness + `ShellScriptEvaluator` |

두 방식 모두 `--sandbox-backend docker`(local Docker daemon) 사용

---

## 0. 환경 구성 및 rLLM 배경 지식

### 0.1 Container

- base image: `pytorch/pytorch:2.12.1-cuda13.0-cudnn9-devel`. 
- 평가 시 agent sandbox/verifier sandbox는 이 container 안에서 host Docker daemon을 빌려 dood (docker out of docker)로 launch 
- 이에 따라 rllm을 사용할 Container를 launch할 때 세 가지 option 설정 필요:

  * `-v /var/run/docker.sock:/var/run/docker.sock` — 호스트 Docker daemon 공유
  * `--network host` — host 주소로 rLLM model gateway에 접속 
      - native는 `host.docker.internal`, harbor는 docker0 gateway IP `172.17.0.1`
      - gateway는 rLLM process(=Container) 안에서 `0.0.0.0`에 바인드되므로, 이 Container가 host network에 있어야 그 주소를 gateway로 활용 가능. bridge network로 띄우면 agent container/verifier container에서 접근 불가.
  * `-v /path/to/shared:/path/to/shared` — Host shared directory volume mount. rLLM integrated harbor를 통한 평가 수행 시, Harbor가 `$RLLM_HOME/harbor_trials/{trial}/verifier`를 task container에 bind-mount하고, 이는 host docker daemon이 resolve하므로 해당 경로가 host에도 **반드시 같은 위치**에 존재해야 접근 가능.

```bash
# Host 
docker run -d --name {CONTAINER_NAME} 
  --gpus all \
  --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /raid/rllm-work:/raid/rllm-work \ # i.e. /path/to/shared
  -v /gpfs/home/exaone/.cache/huggingface:/root/.cache/huggingface # i.e. change to shared hf directory
  -v /path/to/rllm:/workspace/rllm \
  --shm-size 32g \
  pytorch/pytorch:2.12.1-cuda13.0-cudnn9-devel sleep infinity
docker exec -it {CONTAINER_NAME} bash
```

### 0.2 환경 설치

Container 안에는 Docker CLI와 compose plugin 설치 필수 (Harbor는 `docker compose`를 호출).
```
apt-get update && apt-get install curl
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
cd /workspace/rllm
uv venv --python 3.12
source .venv/bin/activate

uv pip install -e ".[harbor]"

apt-get update && apt-get install -y docker.io docker-compose-v2
# docker is included in [project].dependencies -> no need to install
```

`harbor:openhands-sdk`로 평가할 때만 추가로 설치된 harbor에 patch를 적용한다(3.4). 다른 harness에는 영향이 없다.

```bash
bash recipe/eval/scripts/apply_harbor_patches.sh
```

### 0.3 저장 위치

rLLM은 dataset, 평가 결과, Harbor trial log를 `$RLLM_HOME`(기본 `~/.rllm`) 아래에 둔다. Host가 아닌 Container 내부에서 dood 형태로 실행하는 본 환경에서는 두 이유로 **host와 같은 경로로 mount된 큰 volume**(위 예시의 `/raid/rllm-work`) 아래를 가리키게 한다.

1. 용량. task directory 수백 개와 Episode JSON이 쌓이고, Container Root에 두면 Container와 함께 사라진다.
2. Harbor 방식은 `$RLLM_HOME/harbor_trials/...`를 task container에 bind-mount하는데, 이 mount는 host docker daemon이 해석한다. Container 안에만 있는 경로(`~/.rllm`, `/workspace/rllm`)를 주면 verifier의 reward 파일이 host에만 남아 모든 task가 `RewardFileNotFoundError`로 끝난다. 이 위치를 따로 바꾸는 설정은 없고, `RLLM_HOME`을 host와 공유하는 directory 경로로 바꾸는 방법이 있다.

아래는 이 문서 전체에서 가정하는 값이다. 바꾸면 이전에 pull한 dataset과 결과가 다른 위치에 있어 없는 것처럼 보인다. 
프로젝트 내부에서 해당 경로를 고정해서 사용하면, rLLM 설정 (config.json), 프로젝트 내부 인원이 특정 벤치마크를 평가한 결과, SWE-Bench Verified Subset, rLLM을 통해 build한 학습 데이터 등 모든 것을 공유해서 사용할 수 있다.

```bash
export RLLM_HOME=/raid/rllm-work/rllm-home
```

### 0.3.1 환경변수

| Var | Default | Why |
| --- | --- | --- |
| `RLLM_HOME` | `~/.rllm` | dataset, 결과, `config.json`(model setup), Harbor Trial 등
| `RLLM_HARBOR_SESSION_TIMEOUT_S` | `900` | Harbor 방식 전용. Trial 1개(agent + verifier)의 상한. SWE-bench Pro의 Go 저장소는 verifier 단계만 15분 넘게 걸리므로, 기본값이면 oracle test조차 timeout으로 0점. `3000` 이상으로 설정 권장 |
| `RLLM_AGENT_IMAGE` | `auto` | native 방식 전용. `--agent-image` flag와 같은 값(`auto` / `skip` / `repo:tag`) |
| `HF_HOME` | `~/.cache/huggingface` | `swebench_pro` 빌더가 HF dataset을 받는 곳 |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` 등 | 없으면 `empty` | proxy를 사용할 경우 실제 값 필요 X. export되어 있으면 task container 안으로 전달되므로, 신뢰하지 않는 task(agent가 임의 명령을 실행함)를 평가할 때는 shell에 실제 키 설정 X |
| `RLLM_API_KEY` | 없음 | `rllm login`을 했거나 이 변수가 있으면 평가 결과와 Episode가 rLLM UI 서버로 upload. 외부로 나가면 안 되는 결과라면 `--no-ui` 명시 |

※ Harbor Registry에서 받은 task directory는 `RLLM_HOME`이 아니라 **`~/.cache/harbor/tasks`**에 들어가고, `$RLLM_HOME/datasets/<name>/default.parquet`의 `task_path`가 그곳을 가리킨다. Container를 새로 만들면 이 cache가 사라져 parquet은 있는데 task directory가 없는 상태가 된다. 그때는 `rllm dataset pull harbor:<name>`을 다시 실행해야한다.

### 0.3.2 dataset 용어 정리: catalog, parquet, task directory

세 개념이 서로 연관되어 있다.

| 개념 | 실체 | 역할 |
| --- | --- | --- |
| **catalog** | `rllm/registry/datasets.json` (코드에 포함) | dataset 이름 → 어디서 어떻게 받는지. `rllm dataset list`가 보여주는 것. `harbor:<이름>`은 이 파일에 없고 호출 시 Harbor registry에 물어 항목을 즉석에서 만든다 |
| **parquet (DatasetRegistry)** | `$RLLM_HOME/datasets/<이름>/<split>.parquet` + `registry.json` | rLLM의 표 형식 Dataset. **task당 한 행.** `rllm eval`/`rllm train`은 항상 이걸 통해 task 목록을 얻는다 |
| **task directory (Harbor 형식)** | `task.toml`, `instruction.md`, `environment/Dockerfile`, `tests/test.sh`, `solution/solve.sh` | **실제로 실행되는 것.** Harbor가 정한 형식이고 rLLM도 그대로 쓴다. directory 묶음 위에 `dataset.toml`(이름, split, 기본 agent)이 붙는다 |

parquet과 task directory의 관계가 핵심: 수학 문제(e.g. gsm8k)처럼 텍스트만 있는 dataset은 parquet 행 자체가 model 입력으로 사용되는 instruction. SWE task처럼 container가 필요한 dataset은 parquet 행이 포인터. 행의 `task_path`가 가리키는 directory가 진짜 내용.

`rllm dataset pull`이 종류별로 하는 일:
- `rllm dataset pull`: CLI 명령으로, catalog 항목을 읽어 실제로 데이터를 받아오는 동작. 항목 종류에 따라 하는 일이 다르다.

| type | ex | pull | task directory | parquet row |
| --- | --- | --- | --- | --- |
| HF dataset | `gsm8k` | HF에서 행을 받아 transform 후 등록 | 없음 (eval 시 즉석 materialise) | Instruction 자체 |
| **builder** | `swebench_pro`, `rllm-swesmith`, `deepswe` | `builder` 함수를 `out_dir=$RLLM_HOME/datasets/<이름>`으로 호출. 원본에서 directory **생성** + `dataset.toml` + 등록 | `$RLLM_HOME/datasets/<이름>/<task_id>/` | 포인터 |
| **`harbor:<이름>`** | `harbor:swebench-verified`, `harbor:swebenchpro` | Harbor Registry Client로 완성된 directory를 download + 등록 | `~/.cache/harbor/tasks/<해시>/<task_id>/` (`RLLM_HOME` 무관) | 포인터 |

`rllm dataset pull swebench_pro`와 `python -m rllm.data.swebench_pro_builder ...`는 **같은 함수**(`build_benchmark`)를 호출하고 결과물 형식도 같다. pull은 출력 위치가 `$RLLM_HOME/datasets/swebench_pro`로 고정되고 731개 전체를 만들며 parquet도 등록한다. 모듈 직접 호출은 `--out-dir`, `--task-ids`, `--limit`을 받고 parquet은 등록하지 않는다. 그래서 subset은 직접 호출로 만든다.

`rllm eval <X>`가 X를 해석하는 순서:

1. 경로(`./`, `/`로 시작) → 그 directory의 `dataset.toml`/`task.toml`을 `BenchmarkLoader`가 읽는다. parquet 사용 X.
2. `harbor:<이름>` → registry에 물어 catalog 항목 합성 → parquet 없으면 pull → 행의 `task_path`로 Task 생성.
3. Pure 이름 → `$RLLM_HOME/datasets/<X>/dataset.toml`이 있고 agent가 `harbor:*`가 아니면 1번처럼 directory를 직접 읽는다. 아니면 catalog → parquet(없으면 pull).

```
catalog (datasets.json)           "이름 → 받는 방법"
        │  rllm dataset pull
        ▼
task directory                     실제 내용 (task.toml, Dockerfile, test.sh ...)
   ├─ harbor:*  → ~/.cache/harbor/tasks/...
   └─ builder      → $RLLM_HOME/datasets/<이름>/...
        │  등록
        ▼
parquet ($RLLM_HOME/datasets/<이름>/default.parquet)   task당 한 행, task_path 포인터
        │  rllm eval / rllm train
        ▼
실행 결과
   ├─ $RLLM_HOME/eval_results/<실행>/       
   └─ $RLLM_HOME/harbor_trials/<트라이얼>/  
```

`default_verl.parquet`는 같은 행을 verl 학습기 형식으로 한 번 더 저장한 사본이다. 평가에서는 무관하다.

### 0.4 model 연결 — 두 가지

`rllm eval`은 model 호출을 항상 **rLLM model gateway**를 거쳐 보낸다. gateway 뒤에 무엇을 두느냐에 따라 두 가지로 나뉜다.

**(A) Proprietary model (OpenAI, Anthropic, Gemini 등)**

provider & API 키를 등록한다. 이후 `rllm eval`이 LiteLLM proxy를 자동으로 띄워 routing한다.

```bash
rllm model setup            # provider(openai / anthropic / gemini / openrouter / ...), API key, model 선택
rllm model show             # 현재 설정 확인
```

이후 명령에서는 `--model`만 바꾸면 된다. 생략하면 setup에서 고른 model을 사용한다.

```bash
rllm eval <benchmark> --agent <agent> --sandbox-backend docker --model gpt-5.5
```

**How the API KEY is used during eval** setup이 받은 키는 `$RLLM_HOME/config.json`에 저장된다. `rllm eval`은 그 키로 local LiteLLM
proxy를 띄우고, gateway가 proxy로 요청을 넘긴다. task container 안의 agent에는 실제 키가 아니라 placeholder(`sk-rllm-gateway` 또는 `empty`)가 들어간다. 즉 **평가 중 실제 키는 rLLM process 밖으로 나가지 않는다.**

```
container(agent, placeholder 키) → gateway → LiteLLM proxy(실제 키) → api.openai.com
```

그래서 키는 setup에만 주고, shell에는 export하지 않는 것을 권장한다. `OPENAI_API_KEY`가 shell에 export되어 있으면 setup이 그 값을 기본값으로 읽어 편하지만, 그 상태로 `rllm eval`을 실행하면 placeholder 대신 **실제 키를 task container에 넣는다**(동작에는 차이가 없지만 agent가 임의 명령을 실행하는 container에 키가 노출된다).

setup을 마친 뒤 `unset OPENAI_API_KEY` 하면 된다. `config.json`은 평문이므로 공유 volume에 둘 때는 `chmod 600 $RLLM_HOME/config.json`.

예외가 하나 있다. provider를 `custom`(OpenAI compatible endpoint)으로 잡고 키를 입력하면 proxy를 띄우지 않고 `rllm eval`이 그 키를 자기 환경변수 `OPENAI_API_KEY`에 넣는다(`rllm/cli/eval.py`). 그러면 rLLM이 그 값을 읽어 **실제 키가 task container에 들어간다.** 키를 설정한 vLLM을 `custom`으로 평가할 때 해당한다.

proxy 시작에 실패하면 `uv pip install "litellm[proxy]"`.

**(B) vLLM / SGLang으로 서빙한 로컬 model**

OpenAI compatible endpoint를 `--base-url`로 직접 준다. 이때 `--model`은 필수이며, 서버의 `served-model-name`과 정확히 같아야 한다.

```bash
# vLLM
vllm serve Qwen/Qwen3-8B --port 8000 --served-model-name Qwen/Qwen3-8B --max-model-len 65536

# SGLang
python -m sglang.launch_server --model-path Qwen/Qwen3-8B --port 30000 --served-model-name Qwen/Qwen3-8B

rllm eval <benchmark> --agent <agent> --sandbox-backend docker \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3-8B
```

`--network host`로 띄웠으므로 서빙 서버가 호스트나 다른 container에 있어도 `127.0.0.1:<port>`로 닿는다.

model명 규칙: mini-swe-agent 계열 agent는 `provider/model` 형식을 요구해서 rLLM이 접두어를 자동으로 붙인다. `qwen`, `deepseek`, `gpt-*`, 알 수 없는 이름은 `openai/`가 붙어 OpenAI 호환 경로로 나가고, `claude`가 들어간 이름은 `anthropic/`이 붙는다. `Qwen/Qwen3-8B`처럼 HF 조직명이 앞에 오는 이름도 `openai/` 접두어가 붙는다(`openai/Qwen/Qwen3-8B`). litellm이 `openai/`를 떼고 보내므로 서버에는 `Qwen/Qwen3-8B` 그대로 도착한다.

### 0.5 결과 확인

결과는 `$RLLM_HOME/eval_results/<benchmark>_<model>_<timestamp>/`에 `meta.json`, `results.json`, `episodes/`로
남는다. 콘솔에는 Accuracy, Errors, `--attempts`를 썼다면 pass@k가 찍힌다.

```bash
rllm view <run-id> 
```

`Errors`는 model이 못 푼 것이 아니라 **인프라 실패**(image build 실패, timeout, gateway 접속 불가 등)다. 0이 아니면 먼저 원인을 잡는다. Console에 처음 다섯 개가 찍히고 나머지는 `results.json`에 있다.

### 0.6 `rllm eval` option 정리

`rllm eval <benchmark> [option]`. 전체는 `rllm eval --help`.

**sampling (gateway가 session 단위로 강제)**

| option | 설명 |
| --- | --- |
| `--temperature FLOAT` | 온도. `--sampling-params temperature=...`의 단축 |
| `--top-p FLOAT` | nucleus sampling |
| `--max-tokens INT` | 호출당 최대 생성 token |
| `--sampling-params TEXT` | `"temperature=0.6,top_p=0.95,top_k=20,presence_penalty=0.1"` 형식 또는 `@file.yaml` / `@file.json`. 핵심 키 `temperature`, `top_p`, `top_k`, `max_tokens` 외의 키(`presence_penalty`, `min_p`, `repetition_penalty` ...)는 backend(vLLM 등)에 그대로 전달 |

`@file`은 sampling 파라미터를 담은 YAML/JSON 파일이다. 키는 `key=value`로 줄 때와 같다. `--sampling-params`에는 문자열과 `@file` 중 하나만 줄 수 있고, `--temperature` 같은 단축 option이 파일 값을 덮는다.
그래서 팀 공통 파일을 두고 실험별로 `--temperature`만 바꾸는 식으로 쓴다.

```yaml
# sampling.yaml
temperature: 0.7
top_p: 0.95
top_k: 20
max_tokens: 8192
```

```bash
rllm eval ... --sampling-params @/path/to/sampling.yaml                     
rllm eval ... --sampling-params @/path/to/sampling.yaml --temperature 1.0  
```

파일에 적을 수 있는 키는 핵심 4개(`temperature`, `top_p`, `top_k`, `max_tokens`)에 한정되지 않는다. gateway가 키들을 요청 JSON의 최상위에 그대로 합치므로(`payload.update`), vLLM/SGLang의 `extra_body`에 넣을 수 있는 키(`min_p`, `repetition_penalty`, `presence_penalty`, `seed`, `stop`, `chat_template_kwargs` ...)는 전부 쓸 수 있다. proprietary model 경로의 LiteLLM proxy는 `drop_params`로 띄워져 provider가 모르는 키를 **조용히 버린다**(OpenAI model에 `top_k`를 주면 오류 없이 무시됨). `model`, `logprobs`, `return_token_ids`는 gateway가 관리하므로 적지 않는다.

예시 파일이 `recipe/eval/sampling_qwen3_5_4b.yaml`에 있다. Qwen3.5-4B model 카드의 "thinking mode, precise coding
tasks" 프리셋(`temperature=0.6, top_p=0.95, top_k=20, min_p=0, presence_penalty=0, repetition_penalty=1.0`)에
recipe의 val과 같은 턴당 `max_tokens: 8192`를 붙인 것이다. Qwen3.5-4B는 chat template이 기본으로 thinking을 켜므로
thinking 프리셋이 맞다. 반복 루프가 보이면 `presence_penalty`를 0~2 사이로 올린다(model 카드 권고).

```bash
# vLLM. Qwen3.5는 128K context를 권하므로 recipe와 같은 131072로 띄운다 (8192 prompt + 122880 response)
vllm serve Qwen/Qwen3.5-4B --port 8000 --served-model-name Qwen/Qwen3.5-4B \
    --max-model-len 131072 --reasoning-parser qwen3

rllm eval harbor:swebench-verified --agent mini-swe-agent --sandbox-backend docker --agent-image auto \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3.5-4B \
    --sampling-params @recipe/eval/sampling_qwen3_5_4b.yaml \
    --task-indices 0-9 --attempts 4 --sandbox-concurrency 8 --no-ui
```

이 값들은 **rLLM gateway가 요청 payload을 덮어써서** 적용한다. harness(mini-swe-agent 등)가 자체 설정으로 보내는 temperature가 있어도 여기서 설정한 값이 이긴다. 우선순위(낮은 쪽부터): 설정 파일 기본값 < `@file` < `key=value` < `--temperature` 같은 단축 option. 아무것도 주지 않으면 harness가 보낸 값이 그대로 사용된다.

**반복·표본 수**

| option | 설명 |
| --- | --- |
| `--attempts INT` | task당 독립 rollout 수. `k=1..N`의 pass@k를 보고 (기본 1). 온도 0이면 시도가 같아지므로 `--temperature 0.7`처럼 함께 준다 |
| `--max-examples INT` | 앞에서 N개만 |
| `--task-indices TEXT` | `'0'`, `'3,7,12'`, `'0-9'`, 조합 가능 |
| `--split TEXT` | dataset split. 기본은 catalog의 eval_split (Harbor 소스는 `default`, 등록한 사본은 등록 시 이름) |

**model 연결**

| option | 설명 |
| --- | --- |
| `--model TEXT` | model명. `--base-url`을 주면 필수(서빙 이름과 일치), 아니면 `rllm model setup` 값 |
| `--base-url TEXT` | OpenAI 호환 endpoint. 생략하면 setup 설정으로 LiteLLM proxy 자동 시작 |

**agent·채점**

| option | 설명 |
| --- | --- |
| `--agent TEXT` | harness 이름(`mini-swe-agent`, `oracle`, `harbor:mini-swe-agent` ...) 또는 `module:object` |
| `--evaluator TEXT` | 채점기 강제 지정. 등록한 사본을 Harbor harness로 돌릴 때 `harbor_reward_fn` (1.2.1절) |

**sandbox**

| option | 설명 |
| --- | --- |
| `--sandbox-backend` | `docker`, `local`, `modal`, `daytona`, `e2b`, `runloop`, `gke`, `apple-container` |
| `--sandbox-concurrency INT` | 동시에 뜨는 sandbox 수 (기본 64). 로컬 Docker에서는 8 안팎부터 |
| `--concurrency INT` | LLM 호출 동시성 (기본 64). sandbox 수와 별개 |
| `--agent-image TEXT` | native 전용. `auto`(기본) / `skip` / `repo:tag`. mini-swe-agent, opencode, claude-code 지원 |
| `--snapshot / --no-snapshot` | modal, daytona snapshot 사용 여부. docker에는 영향 없음 |
| `--warm-queue-size INT` | sandbox N개 선생성. `-1`이면 `--concurrency`와 동일 |

**출력**

| option | 설명 |
| --- | --- |
| `--output TEXT` | 결과 JSON 경로 (기본 run directory의 `results.json`) |
| `--episodes-dir TEXT` | run directory 위치 (기본 `$RLLM_HOME/eval_results/<bench>_<model>_<timestamp>/`) |
| `--save-episodes / --no-save-episodes` | episode JSON 저장 (기본 저장) |
| `--ui / --no-ui` | rLLM UI 서버로 실시간 upload. 로그인 상태면 자동 켜짐. 외부로 나가면 안 되는 결과는 `--no-ui` 명시 |

자주 쓰는 조합:

```bash
# ex. local vLLM, 10 task, 4 runs/task, pass@k
rllm eval harbor:swebench-verified --agent mini-swe-agent --sandbox-backend docker --agent-image auto \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3-8B \
    --task-indices 0-9 --attempts 4 --temperature 0.7 --top-p 0.95 --max-tokens 8192 \
    --sandbox-concurrency 8 --no-ui
```

---

## 1. Harbor 방식

| 벤치마크 | 이름 | task 수 | base image |
| --- | --- | --- | --- |
| SWE-bench Verified | `harbor:swebench-verified` | 500 | `swebench/sweb.eval.x86_64.<repo>_1776_<instance>` |
| SWE-bench Pro | `harbor:swebenchpro` | 731 | task별 사전 build image |

첫 실행 때 task directory(only text, not image)를 자동으로 내려받아 `$RLLM_HOME/datasets/<name>/`에 등록한다. 미리 받아두려면:

```bash
rllm dataset pull harbor:swebench-verified
rllm dataset pull harbor:swebenchpro
```

Docker image는 task가 실행될 때 Harbor가 `environment/Dockerfile`을 build하면서 `FROM` image를 pull한다.
Verified 500개 전체의 base image는 약 2TB다. 전체 평가 전에 disk를 확인한다.

### 1.1 전체 평가

```bash
export RLLM_HARBOR_SESSION_TIMEOUT_S=3600   

# (A) proprietary
rllm eval harbor:swebench-verified --agent harbor:mini-swe-agent --sandbox-backend docker \
    --model gpt-5.5 --sandbox-concurrency 8
rllm eval harbor:swebenchpro       --agent harbor:mini-swe-agent --sandbox-backend docker \
    --model gpt-5.5 --sandbox-concurrency 8

# (B) vLLM / SGLang
rllm eval harbor:swebench-verified --agent harbor:mini-swe-agent --sandbox-backend docker \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3-8B --sandbox-concurrency 8
rllm eval harbor:swebenchpro       --agent harbor:mini-swe-agent --sandbox-backend docker \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3-8B --sandbox-concurrency 8
```

`--agent`를 생략하면 Harbor dataset의 기본값인 `harbor:mini-swe-agent`가 쓰인다. 다른 Harbor scaffold도 같은 형식으로 고른다: `harbor:terminus-2`, `harbor:swe-agent`, `harbor:codex`, `harbor:claude-code`, `harbor:oracle`(정답 patch만 적용, LLM 미호출) 등.

### 1.2 Subset 평가

Harbor 경로에서 task를 고르는 수단은 **Index**다. Index는 `$RLLM_HOME/datasets/<name>/default.parquet`의 행 순서다.

```bash
# 앞에서 10개
rllm eval harbor:swebench-verified --agent harbor:mini-swe-agent --sandbox-backend docker \
    --max-examples 10 --model gpt-5.5

# 특정 Index. '0', '3,7,12', '0-9' 형식
rllm eval harbor:swebench-verified --agent harbor:mini-swe-agent --sandbox-backend docker \
    --task-indices 0-4,17,42 --model gpt-5.5
```

instance_id로 고르고 싶으면 id → Index를 먼저 뽑는다.

```bash
python - <<'PY'
import os, pandas as pd
name = "swebench-verified"                     #  or "swebenchpro"
want = {"django__django-11265", "sympy__sympy-16792"}
df = pd.read_parquet(f"{os.environ['RLLM_HOME']}/datasets/{name}/default.parquet")
print(",".join(str(i) for i, t in enumerate(df["task_id"]) if t in want))
PY
```

출력값을 `--task-indices`에 그대로 넣는다. Index는 dataset을 다시 pull해도 바뀌지 않는다 (registry manifest 순서).

같은 task를 여러 번 평가해 pass@k를 보려면 `--attempts 4`처럼 준다. 이때는 온도를 0보다 크게 주는 것을 권장한다(`--temperature 0.7`).

#### 1.2.1 subset을 Harbor harness로 평가

Harbor harness(`harbor:*`)가 필요로 하는 것은 dataset 이름이 `harbor:`로 시작하는 것이 아니라, **parquet 행에 `task_path`가 있는 것**이다(`HarborRuntime`은 `task.metadata["task_path"]`로 trial을 만든다). 그래서 native와 같은 방법으로 task directory를 `$RLLM_HOME` 아래에 복사해 등록한 subset도 Harbor harness로 실행할 수 있다.
단, 1.2 방법으로 충분히 같은 일을 할 수 있기에 권장하지 않는다. 별도의 이유로 subset을 분리하고 싶은 경우에만 참고로 사용한다.

조건:
- **소스는 `harbor:swebenchpro`(Harbor cache)에서 복사한다.** rLLM builder(`swebench_pro`)의 task directory는 Harbor harness로 채점되지 않는다. 이유는 아래와 같다: 
  - builder의 `tests/test.sh`가 결과를 `/tmp/rllm/reward.json`에만 쓰는데(rLLM 규약), Harbor verifier는 `/logs/verifier/reward.txt|json`만 읽기 때문이다(`RewardFileNotFoundError`). 
  - builder `task.toml`의 `docker_image` 때문에 Harbor가 Dockerfile을 건너뛰어 Container가 `exit 126`으로 죽는다. 
- **parquet 행에 `task_path` 추가**: 사본 경로를 가리키는 행으로 `DatasetRegistry.register_dataset` 한다.
- **`--evaluator harbor_reward_fn` 명시**: `harbor:` 이름이 아니면 CLI가 catalog에서 Evaluator를 찾지 못해 멈추는데, 이 flag가 그 분기를 지나게 한다.

<harbor:swebenchpro subset 100 예시> 

```bash
export RLLM_HOME=/raid/rllm-work/rllm-home
rllm dataset pull harbor:swebenchpro
```

`$RLLM_HOME/datasets/swebench_pro_100/<task_id>/` 100개 복사 + registry 등록

```python
import json
import re
import shutil
import sys
from pathlib import Path

from rllm import paths
from rllm.data import DatasetRegistry

src = DatasetRegistry.load_dataset(src_name, src_split)
if src is None:
    sys.exit(f"source dataset '{src_name}/{src_split}' is not registered. Run: rllm dataset pull " + ("swebench_pro" if args.source == "builder" else "harbor:swebenchpro"))
# Harbor lower-cases some ids (instance_NodeBB__NodeBB-... -> instance_nodebb__nodebb-...).
by_id = {row[id_col].lower(): row for row in src}

out = Path(paths.rllm_path("datasets", name))
out.mkdir(parents=True, exist_ok=True)
rows, missing = [], []
for iid in want:
    row = by_id.get(iid.lower())
    if row is None:
        missing.append(iid)
        continue
    src_dir = Path(row["task_path"])
    dst = out / src_dir.name
    if dst.exists() and args.force:
        shutil.rmtree(dst)
    if not dst.exists():
        shutil.copytree(src_dir, dst)
    toml = dst / "task.toml"
    if not args.keep_docker_image:
        toml.write_text(re.sub(r"^docker_image\s*=.*\n", "", toml.read_text(), flags=re.M))
    instruction = row.get("instruction") or (dst / "instruction.md").read_text()
    rows.append({"id": src_dir.name, "task_id": src_dir.name, "instruction": instruction, "question": instruction, "task_path": str(dst), "design_id": iid})

if missing:
    sys.exit(f"{len(missing)} ids not found in source '{src_name}': {missing[:5]}")

DatasetRegistry.register_dataset(
    name=name,
    data=rows,
    split=args.split,
    source=f"{src_name} subset from {Path(args.design).name}",
    description=f"SWE-bench Pro subset '{design.get('name', '')}' ({len(rows)} tasks) from {args.source} source",
    category="agentic",
)
print(f"{name}/{args.split}: {len(rows)} tasks -> {out}")
print("harbor harness :", f"rllm eval {name} --split {args.split} --agent harbor:mini-swe-agent --evaluator harbor_reward_fn --sandbox-backend docker ...")
```

평가 수행
```bash
export RLLM_HARBOR_SESSION_TIMEOUT_S=3300
rllm eval swebench_pro_100 --split test \
    --agent harbor:oracle --evaluator harbor_reward_fn \
    --sandbox-backend docker --concurrency 8 --sandbox-concurrency 8 --no-ui \
    --base-url http://127.0.0.1:1/v1 --model oracle-dummy         # oracle 점검
rllm eval swebench_pro_100 --split test \
    --agent harbor:mini-swe-agent --evaluator harbor_reward_fn \
    --sandbox-backend docker --concurrency 8 --sandbox-concurrency 8 --no-ui \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3.5-4B \
    --sampling-params @recipe/eval/config/qwen3_5.yaml            # model 평가
```

### 1.3 Harbor 경로에서 알아둘 것

* **timeout**: Harbor trial 하나에 rLLM이 거는 상한은 `RLLM_HARBOR_SESSION_TIMEOUT_S`(기본 900초)다. SWE-bench task의 `task.toml`은 Agent와 Verifier에 각 3000초를 주므로 기본값이면 긴 rollout이 먼저 잘린다. 3600 이상으로 올리는 것을 권장한다. 단, harbor와 동일한 평가 결과를 재현하고자 할 경우, task.toml 설정을 따른다.
  - `[agent].timeout_sec`와 `[verifier].timeout_sec`(두 벤치마크 모두 3000초)를 Harbor가 그대로 적용하고, 그 위에 rLLM의 `RLLM_HARBOR_SESSION_TIMEOUT_S`가 Trial 전체 상한으로 한 번 더 걸린다. 둘 중 짧은 쪽이 이긴다. 단, Harbor는 Verifier timeout을 **한 번 재시도**한다(`stop_after_attempt(2)`).
  - session 상한에 걸린 trial은 0점이 아니라 **Errors**로 집계되고, container·network·derived image는 rLLM이 직접 정리한다(`run_harbor_trial`).
* **concurrency**: `--sandbox-concurrency`가 동시에 뜨는 sandbox 수(default 64)이며, 로컬 Docker에서는 CPU, memory, disk I/O를 보고 8 안팎에서 시작한다. `--concurrency`는 LLM 호출 동시성으로 별도다.
* **자원 제한**: `task.toml` 그대로. Harbor는 `[environment]`의 cpus/memory를 compose `deploy.resources.limits`로 적용하고, rLLM은 이를 바꾸지 않는다. registry의 `swebenchpro`는 CPU 1개, 4GB라서 Go 저장소의 Verifier가 시간 안에 끝나지 않는다(task instance: flipt). 이 task들을 Harbor 방식으로 채점하려면 자원 상한을 올릴 방법이 필요하다.
* **task마다 harness 설치**: Harbor의 mini-swe-agent는 container 안에서 `apt-get install build-essential` 후 `uv tool install mini-swe-agent`를 매번 실행한다. native 방식의 `--agent-image`에 해당하는 cache가 없어 task당 1~2분이 추가된다.
* **gateway 주소**: Harbor의 compose 파일은 task container에 `host.docker.internal`을 넣어주지 않고, Linux Docker Engine은 그 이름을 기본으로 모른다(cf. Docker Desktop). 그래서 rLLM은 Linux에서 `docker network inspect bridge`로 얻은 docker0 gateway IP(보통 `172.17.0.1`)로 URL을 바꿔 넘긴다. rLLM container가 `--network host`라는 전제 위에서만 성립한다.
* **image download 시점**: 실행 중에 task별로 받는다. 사전 download는 필요 없다. Harbor는 `environment/Dockerfile`을 build해 task별 derived image `<trial>-main:latest`(Verified 기준 약 7.5 GB)를 만들고, 정상 종료 시 `compose down --rmi all`로 지운다. 비정상 종료 시에는 남는다. base image(`swebench/sweb.eval...`, `jefzda/sweap-images:...`, 개당 약 4 GB)는 어느 방식도 지우지 않는다. 

---

## 2. Native 방식

native 방식은 Harbor runtime 없이 rLLM이 직접 container를 만들고, 그 안에서 harness(예: mini-swe-agent CLI)를 실행하여 추론을 진행한 뒤, task directory의 `tests/test.sh`를 실행해 `reward.txt`를 읽는다.

```
SandboxTaskHooks      docker build -t rllm-task-<task_id> --rm . && docker run (+ harness CLI image mount)
MiniSweAgentHarness   mini-swe-agent CLI를 Container 안에서 실행
  └─ litellm ───────► rLLM model gateway (host.docker.internal) ──► LiteLLM proxy
ShellScriptEvaluator  /tests/test.sh → /logs/verifier/reward.txt → reward
```

harness는 `rllm agent list`에 나오는 rLLM harness를 사용한다.

### 2.1 SWE-bench Verified

데이터 소스는 Harbor 방식과 **같은** `harbor:swebench-verified`다. `--agent`에 `harbor:` 접두어가 없으면 rLLM이 Harbor 채점기(`harbor_reward_fn`)를 건너뛰고 task별 `tests/test.sh`로 채점한다.

```bash
rllm dataset pull harbor:swebench-verified

# 환경 점검: 정답 patch를 적용하고 verifier만 돌린다. LLM 미호출 (LLM을 호출하지 않지만 CLI가 Provider 설정을 요구하므로 죽은 port를 준다)
# oracle 점검에서 1.0이 안 나오는 task는 model도 절대 풀 수 없으니 제외한다 (알려진 예: `astropy__astropy-7606`).
rllm eval harbor:swebench-verified --agent oracle --sandbox-backend docker \
    --max-examples 5 --concurrency 3 --no-ui \
    --base-url http://127.0.0.1:1/v1 --model oracle-dummy

# (A) proprietary
rllm eval harbor:swebench-verified --agent mini-swe-agent --sandbox-backend docker \
    --agent-image auto --sandbox-concurrency 8 --model gpt-5.5

# (B) vLLM / SGLang
rllm eval harbor:swebench-verified --agent mini-swe-agent --sandbox-backend docker \
    --agent-image auto --sandbox-concurrency 8 \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3-8B
```

`--agent-image auto`는 mini-swe-agent CLI를 한 번 Docker image로 구워 두고 모든 task container에 read only로 mount한다. 없으면 task마다 `uv tool install`을 반복한다. 

### 2.2 SWE-bench Pro

rLLM catalog의 `swebench_pro` 항목이 전용 builder를 갖고 있다. HuggingFace `ScaleAI/SWE-bench_Pro`와 `scaleapi/SWE-bench_Pro-os`의 인스턴스별 `run_script.sh`/`parser.py`를 합쳐 task directory를 만든다.
verifier는 upstream `swe_bench_pro_eval.py` 흐름(agent diff → base_commit으로 reset → diff apply → gold test checkout → F2P/P2P eval)을 `tests/test.sh`로 재현한다.

```bash
rllm dataset pull swebench_pro          # $RLLM_HOME/datasets/swebench_pro/ 에 731개 task directory 생성

rllm eval swebench_pro --agent oracle --sandbox-backend docker \
    --max-examples 5 --concurrency 3 --no-ui \
    --base-url http://127.0.0.1:1/v1 --model oracle-dummy

# (A) proprietary
rllm eval swebench_pro --agent mini-swe-agent --sandbox-backend docker \
    --agent-image auto --sandbox-concurrency 8 --model gpt-5.5

# (B) vLLM / SGLang
rllm eval swebench_pro --agent mini-swe-agent --sandbox-backend docker \
    --agent-image auto --sandbox-concurrency 8 \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3-8B
```

image는 `jefzda/sweap-images:<tag>`이며 task마다 다르다. 없으면 `docker run` 시점에 pull한다. builder는 `task.toml`에 CPU 4개, memory 16 GB를 적어 두는데, Docker backend는 이 값으로 container 자원을 제한한다. JS/Go test 스위트가 커서 `--sandbox-concurrency`를 너무 올리면 호스트 memory가 먼저 마른다.

### 2.2.1 harbor:swebenchpro vs swebench_pro

`harbor:swebenchpro`와 `swebench_pro`는 같은 벤치마크, 같은 Docker image에 대해 **독립적으로 만들어진 두 벌의 task directory**다. rLLM builder는 Harbor task를 변환하는 것이 아니라 원본 데이터에서 처음부터 만든다.

| | `harbor:swebenchpro` | `swebench_pro` |
| --- | --- | --- |
| 만드는 쪽 | Harbor adapter가 만들어 registry에 올린 것 | `rllm/data/swebench_pro_builder.py` (`rllm dataset pull swebench_pro`) |
| 입력 | 완성된 task directory 731개를 download | HF `ScaleAI/SWE-bench_Pro` 행 + `scaleapi/SWE-bench_Pro-os`의 `run_script.sh`, `parser.py` |
| `task.toml` 자원 | `cpus = 1`, `memory_mb = 4096` | `cpus = 4`, `memory_mb = 16384` (builder `_DEFAULT_RESOURCES`) |
| `tests/test.sh` | adapter의 래퍼 | builder가 합성한 래퍼 |
| Docker image | `jefzda/sweap-images:<tag>` | 같은 image |
| 저장 위치 | `~/.cache/harbor/tasks/...` | `$RLLM_HOME/datasets/swebench_pro/<instance_id>/` |

HF dataset에는 CPU·memory 정보가 없다. 4 / 16384는 업스트림 평가 script가 1–4 CPU, 5–30 GiB를 쓴다는 점을 근거로 builder 작성자가 설정한 값이다(ref. builder 주석).

어느 명령이 어느 소스를 쓰는지:

| 명령 | 소스 | container 자원 |
| --- | --- | --- |
| `rllm eval harbor:swebenchpro --agent harbor:mini-swe-agent` | Harbor | CPU 1, 4 GB |
| `rllm eval harbor:swebenchpro --agent mini-swe-agent` | **Harbor** (native harness라도 task directory는 Harbor) | CPU 1, 4 GB. native 경로도 `task.toml` 값을 그대로 적용한다 |
| `rllm eval swebench_pro --agent mini-swe-agent` | rLLM builder | CPU 4, 16 GB |
| `rllm eval swebench_pro --agent harbor:*` | — | **불가.** builder의 `test.sh`는 `/tmp/rllm/reward.json`에만 쓰고 Harbor verifier는 `/logs/verifier/`만 읽는다. Harbor harness로 subset을 돌리려면 1.2.1절대로 `harbor:swebenchpro`에서 복사한다 |

### 2.3 Subset만 평가

- **Index로 고르기**: Harbor 방식과 같다 (`--max-examples`, `--task-indices`). 
- **instance_id로 고정한 subset 만들기**: task directory를 `$RLLM_HOME/datasets/<subset명>/` 아래에 **복사**해 별도 dataset으로 만든다. 사본이므로 `task.toml`(timeout, 자원)을 고쳐도 원본에 영향이 없고, 어떤 image가 pull됐든 평가 대상이 바뀌지 않는다.

### 2.4 Native 경로에서 알아둘 것

* **image 자원 제한**: `task.toml`의 `[environment]` cpus/memory를 Docker container에 적용한다. Verified는 CPU 1, memory 4 GB로 작다.
* **network**: task container는 기본 bridge network에 붙고 `--add-host=host.docker.internal:host-gateway`가 자동으로 들어간다.

---

## 3. 다른 harness로 평가 (mini-swe-agent 외)

원칙은 `--agent`만 바꾸는 것이지만, harness마다 설치 방식과 model 연결 방식이 달라 확인된 조합만 사용한다. 

### 3.1 지원 표

| harness | native (`--agent <이름>`) | Harbor (`--agent harbor:<이름>`) |
| --- | --- | --- |
| mini-swe-agent | O  | O  |
| opencode | O. `--agent opencode --agent-image auto` | O. `--agent-kwargs @recipe/eval/config/harbor-opencode-vllm.yaml` **필수** (3.3) |
| openhands-sdk | O. `--agent openhands-sdk --agent-image auto` (3.5) | O. `recipe/eval/patches` 적용 **필수** (3.4) |
| openhands (openhands-ai) | 없음 (미구현: TODO) | 미확인 |
| claude-code, codex, aider, ... | 미확인 | 미확인 |

### 3.2 `--agent-kwargs`

- Harbor harness 생성자에 넘길 kwargs.
- 형식은 `--sampling-params`와 같다: `"key=value,..."` 또는 `@file.yaml` / `@file.json`. 
- nested dictionary는 `@file`로만 주며, CLI 값이 키 단위로 우선한다. 
- native harness에는 효과가 없고 경고만 발생한다.

### 3.3 opencode

- **native.** 추가 option 없다. rLLM harness가 gateway를 openai-compatible custom provider(`rllm-gateway`)로 등록하고 Chat Completions로 호출한다.

```bash
rllm eval swebenchpro_100 --split test --agent opencode --agent-image auto \
    --sandbox-backend docker --concurrency 8 --sandbox-concurrency 8 --no-ui \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3.5-4B \
    --sampling-params @recipe/eval/config/qwen3_5.yaml
```

- **Harbor.** `--agent-kwargs`가 없으면 모든 task가 LLM 1회 호출 후 0점으로 끝난다. Harbor의 opencode는 model을 `openai/<model>`로 받아 provider `openai`로 등록하고, opencode는 provider id가 `openai`이면 SDK와 무관하게 **Responses API**(`/v1/responses`)를 쓴다. vLLM의 Responses API는 두 번째 턴의 assistant 메시지를 거부해 400이 난다. 그래서 다른 provider id에 Chat Completions SDK(`@ai-sdk/openai-compatible`)를 붙인 설정을 넘긴다.

```bash
rllm eval swebenchpro_100 --split test --agent harbor:opencode --evaluator harbor_reward_fn \
    --sandbox-backend docker --concurrency 8 --sandbox-concurrency 8 --no-ui \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3.5-4B \
    --sampling-params @recipe/eval/config/qwen3_5.yaml \
    --agent-kwargs @recipe/eval/config/harbor-opencode-vllm.yaml
```

```yaml
# recipe/eval/config/harbor-opencode-vllm.yaml
opencode_config:
  provider:
    openrouter:
      npm: "@ai-sdk/openai-compatible"
```

- `--model`은 서빙 이름 그대로 둔다. gateway가 요청의 `model`을 `--model` 값으로 고정하므로 `--model openrouter/...`로 주면 vLLM이 404를 낸다.
- provider id는 Harbor가 아는 이름이어야 한다(`openai`, `anthropic`, `deepseek`, `openrouter`, `huggingface`, ... `harbor/agents/installed/opencode.py`). 이름만 빌리는 것이고 해당 서비스와는 무관하다. `openai`는 위 이유로 쓸 수 없다.
- 나머지는 rLLM이 trial마다 채운다(`trial_helper._apply_opencode_provider_config`): `options.baseURL`을 그 trial의 gateway session URL로, `options.apiKey`를 `OPENAI_API_KEY`(없으면 `empty`)로, Harbor에 넘기는 model_name의 접두어를 선언된 provider id로(`openai/Qwen/X` → `openrouter/Qwen/X`). 파일에 `options`를 직접 적으면 그 값이 우선한다.

### 3.4 openhands-sdk

Harbor의 OpenHands scaffold는 두 개다. `harbor:openhands`는 제품 전체(`openhands-ai`)를, `harbor:openhands-sdk`는 container 내부에서 직접 실행되는 경량 Software Agent SDK를 설치한다. 아래는 **openhands-sdk** 기준이며 버전은 `1.42.1`로 고정한다(`openhands-sdk`와 `openhands-tools`는 동일한 버전으로 함께 설치된다).

- harbor patch 적용: harbor 0.3.0의 openhands-sdk scaffold는 **task image의 system Python**으로 venv를 생성하고 `pip install openhands-sdk`를 실행한다. SWE-bench Pro subset에서는 이 조합이 100개 **전부** 실패한다. 원인은 네 가지가 중첩되어 있다.

| 원인 | 증상 | 해당 task |
| --- | --- | --- |
| `openhands-sdk`/`openhands-tools`는 `requires-python >=3.12`인데 image Python이 그보다 낮다(3.8~3.11) | `ERROR: Could not find a version that satisfies the requirement openhands-sdk` | 88개 (openlibrary 12개 제외) |
| 8개 저장소 image에 `/root/.config/pip/pip.conf`가 있고 `index-url = http://127.0.0.1:9876/`(build 시점의 로컬 mirror)를 가리킨다. runtime에는 응답하지 않는 주소이므로 pip이 index를 읽지 못한다 | `Connection refused ... /openhands-sdk/` → `No matching distribution found` | 78개 (teleport·protonmail·tutanota 제외). Python 3.12인 openlibrary 12개는 이 원인만으로 실패 |
| teleport image는 Alpine(musl)이라 `apt-get`이 없고 coreutils(`stdbuf`)도 없다. scaffold의 `python3-venv` 설치와 `run()`의 `\| stdbuf -oL tee` pipeline이 모두 실패한다 | `apt-get: not found`, 이어서 `stdbuf: not found` (exit 127) | teleport 10개 |
| qutebrowser image에는 `curl`이 없다. 설치 경로를 uv로 변경하면 uv 설치 script부터 download할 수 없다 | `curl: not found` | qutebrowser 11개 |

subset 11개 저장소의 base image(각 저장소 대표 1개 확인):

| 저장소 (task 수) | OS | system python3 | curl | stdbuf | 응답 없는 pip index |
| --- | --- | --- | --- | --- | --- |
| ansible (13) | Ubuntu 20.04 | 3.9.5 | O | O | O |
| internetarchive/openlibrary (12) | Debian 12 | 3.12.2 | O | O | O |
| flipt (12) | Debian 12 | 3.11.2 | O | O | O |
| qutebrowser (11) | Debian 12 | 3.11.13 | **X** | O | O |
| gravitational/teleport (10) | **Alpine 3.17 (musl)** | 3.10.15 | O | **X** | - |
| protonmail/webclients (9) | Ubuntu 20.04 | 3.8.10 | O | O | - |
| navidrome (8) | Debian 12 | 3.11.2 | O | O | O |
| vuls (8) | Debian 12 | 3.11.2 | O | O | O |
| element-web (8) | Debian 11 | 3.9.2 | O | O | O |
| nodebb (6) | Debian 11 | 3.9.2 | O | O | O |
| tutanota (3) | Debian 11 | 3.9.2 | O | O | - |

`recipe/eval/patches/harbor-0.3.0-openhands-sdk-uv-install.patch`가 설치된 harbor의 `agents/installed/openhands_sdk.py`를 수정한다.

* interpreter를 **uv로 확보**한다(`uv python install 3.12` → `uv venv --python 3.12`). image의 Python 버전과 무관하며, `python_version` kwarg로 변경할 수 있다.
* `uv pip install`은 pip의 설정 파일을 읽지 않으므로 응답하지 않는 `index-url`을 무시한다. musl(Alpine)에서도 uv가 musl build Python을 download한다.
* system 의존성(`curl`, `coreutils`)을 package manager에 맞춰 설치한다(`apt-get`/`apk`/`dnf`/`yum`). `curl`은 uv 설치 script용, `coreutils`는 `run()`의 `stdbuf`에 필요하다.
* uv를 `/opt/openhands-sdk-uv`에 따로 설치한다. subset 100개의 `environment/Dockerfile`에는 전부 `RUN curl -LsSf https://astral.sh/uv/0.7.13/install.sh | sh || true`가 있어서, PATH의 uv를 그대로 사용하면 scaffold가 task image에 고정된 버전(0.7.13)을 따라가게 된다.
* uv download 단계(`curl`, `uv python install`, `uv pip install`)를 3회까지 재시도한다. task마다 약 180개 package(510 MB)를 download하며 100개 실행 기준 PyPI 전송량은 약 50 GB에 이른다. 그중 하나라도 중단되면 trial 전체가 `NonZeroAgentExitCodeError`로 실패한다(Harbor 0.3.0은 agent setup을 재시도하지 않는다).
* 버전 조회를 `pip show`에서 `python -c "import openhands.sdk; print(openhands.sdk.__version__)"`로 변경했다. uv venv에는 pip이 없다(SDK banner는 stderr로 출력되므로 stdout에는 버전만 남는다).
* `run()`이 `LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`을 host의 `os.environ`뿐 아니라 그 trial의 `AgentConfig.env`에서도 읽는다. rLLM이 trial마다 gateway session URL을 이 경로로 전달한다.

```bash
# patch 적용 (ref: --check 로 상태 확인; --revert 로 상태 되돌리기)
bash recipe/eval/scripts/apply_harbor_patches.sh
```

`uv pip install -e ".[harbor]"`를 재실행하면 harbor가 새로 설치되어 patch가 사라지므로 재적용한다.

```bash
export RLLM_HOME=/path/to/rllm-home RLLM_HARBOR_SESSION_TIMEOUT_S=4200
rllm eval swebenchpro_100 \
    --split test \
    --agent harbor:openhands-sdk \
    --evaluator harbor_reward_fn \
    --sandbox-backend docker \
    --concurrency 8 --sandbox-concurrency 8 --no-ui \
    --base-url http://127.0.0.1:8000/v1 \
    --model Qwen/Qwen3.5-4B \
    --sampling-params @recipe/eval/config/qwen3_5.yaml \
    --agent-kwargs @recipe/eval/config/harbor-openhands-sdk.yaml
```

- `--agent-kwargs`의 `version`을 생략하면 실행 시점의 최신 openhands-sdk가 설치된다. 재현성을 위해 `recipe/eval/config/harbor-openhands-sdk.yaml`(= `1.42.1`)을 그대로 사용한다.
- task마다 container 내부에 uv + Python 3.12 + SDK를 새로 설치한다(venv 510 MB, package 약 180개). PyPI 트래픽이 100개 실행 기준 약 50 GB이므로 동시 실행 수를 늘릴 때는 대역폭도 함께 확인해야 한다. H200 호스트에서 측정한 설치 시간은 task당 16~19초(`result.json`의 `agent_setup`→`agent_execution` 간격)이다.
- SDK는 native tool calling을 사용한다. vLLM은 `--enable-auto-tool-choice --tool-call-parser ... --reasoning-parser ...`로 서빙해야 한다(mini-swe-agent와 같은 조건).
- trajectory는 `$RLLM_HOME/harbor_trials/<trial>/agent/trajectory.json`(ATIF)에 기록되고 rLLM Episode로 변환된다. scaffold log는 같은 directory의 `openhands_sdk.txt`이다.

### 3.5 openhands-sdk (native)

같은 SDK를 rLLM harness로 실행한다. harbor patch와 무관하며, 구성은 세 파일이다.

| 파일 | 역할 |
| --- | --- |
| `rllm/harnesses/openhands_sdk.py` | `OpenHandsSdkHarness`. 설치 script, env, runner 배치, 실행 명령 |
| `rllm/harnesses/tools/openhands_sdk_runner.py` | SDK를 구동하는 script. openhands-sdk는 CLI가 아니라 library이므로 harness가 이 script를 sandbox에 기록하고 SDK의 interpreter로 실행한다 |
| `rllm/registry/agents.json` | `openhands-sdk` 등록 (`rllm agent list`에 노출) |

Harbor 경로와의 차이는 두 가지다.

* **trajectory**: gateway가 모든 LLM 호출을 capture하고 engine이 Episode를 구성한다. ATIF 변환이 없고 `tool_calls`가 native 형식으로 남아 학습(`recipe/grpo/qwen3_5`)과 같은 경로다. runner는 trajectory 파일을 쓰지 않는다.
* **채점**: task의 `tests/test.sh`를 rLLM이 직접 실행한다. `--evaluator harbor_reward_fn`이 필요 없다.

```bash
export RLLM_HOME=/path/to/rllm-home
rllm eval swebenchpro_100 \
    --split test \
    --agent openhands-sdk \
    --agent-image auto \
    --sandbox-backend docker \
    --concurrency 8 --sandbox-concurrency 8 --no-ui \
    --base-url http://127.0.0.1:8000/v1 \
    --model Qwen/Qwen3.5-4B \
    --sampling-params @recipe/eval/config/qwen3_5.yaml
```

- **`--agent-image auto`가 설치 비용을 없앤다.** uv + Python 3.12 + SDK를 `/opt/rllm/agent`에 한 번 구워 task container에 read-only로 mount하므로 task당 설치가 사라진다(측정: qutebrowser task 전체 시간이 163초 → 47초, `env_install` 112초 → 0초). Harbor 경로는 task마다 510 MB를 새로 설치한다.
- **Alpine task는 예외다.** bake image는 ubuntu(glibc) 기반이라 musl task image(SWE-bench Pro의 teleport 10개)에서는 mount된 interpreter가 실행되지 못한다. mount가 있으면 rLLM이 설치 훅을 건너뛰므로(`hooks.py`의 `baked_install`), harness가 mount된 python을 **실행해 보고** 실패하면 task별 설치로 폴백한다. 이때 설치 시간은 `env_install`이 아니라 `agentflow`에 잡힌다.
- **버전 고정**은 `rllm/harnesses/openhands_sdk.py`의 `SDK_VERSION`(기본 `1.42.1`)이며 `RLLM_OPENHANDS_SDK_VERSION`, `RLLM_OPENHANDS_PYTHON_VERSION`으로 덮어쓸 수 있다. bake 레시피가 같은 상수를 읽으므로 mount본과 task별 설치본이 어긋나지 않는다. native harness에는 `--agent-kwargs`가 적용되지 않는다(3.2).
- SDK log는 container의 `/tmp/openhands-sdk.log`에 tee된다. tmux가 없는 image에서는 SDK가 subprocess 터미널로 폴백한다는 경고를 남기지만 동작에는 문제가 없다.
- runner는 `OPENHANDS_SDK_SYSTEM_PROMPT_PATH`(container 안 절대경로)가 설정되면 그 Jinja 템플릿을 `Agent(system_prompt_filename=...)`로 넘겨 SDK 기본 system prompt를 교체한다. Harbor scaffold와 같은 변수명이다. 기본 harness는 이 변수를 설정하지 않는다.
- **AI-DLC 워크플로우로 평가**하려면 `recipe/grpo/qwen3_5/aidlc_flow.py`의 harness를 import path로 지정한다. 학습(`variant=openhands_9b_aidlc`)과 같은 문서·지시·system prompt를 sandbox에 넣는다(`recipe/grpo/qwen3_5/README.md` "Variants" 참고):

  ```bash
  rllm eval swebench_verified_balanced --split test \
      --agent recipe.grpo.qwen3_5.aidlc_flow:AidlcOpenHandsSdkHarness \
      --agent-image auto --sandbox-backend docker --no-ui \
      --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3.5-9B
  ```

  repo root에서 실행해야 `recipe.grpo.qwen3_5`가 import된다. `step_limit`은 class 기본값(50)이며 `--agent-kwargs`는 native harness에 적용되지 않는다(3.2).

---

## Appendix

### 1. derived image 정리(공유 호스트라면 다른 사람의 실행분이 섞여 있으니 목록을 먼저 본다):

```bash
docker images --format '{{.Repository}}:{{.Tag}} {{.Size}} {{.CreatedSince}}' | grep -- '-main:latest'   # Harbor 잔여
docker images --format '{{.Repository}}:{{.Tag}} {{.Size}} {{.CreatedSince}}' | grep '^rllm-task-'       # native rllm 잔여
docker images --format '{{.Repository}}:{{.Tag}}' | grep '^rllm-task-' | xargs -r docker rmi             # 삭제 예
docker images --format '{{.Repository}}:{{.Tag}}' | grep -- '-main:latest' | xargs -r docker rmi
docker network ls --format '{{.Name}}' | grep '_default$' | grep -E 'instance_|__' | xargs -r docker network rm  # Harbor 잔여 network
docker image prune                                                                                       # dangling layer
```

`docker rmi`는 실행 중인 container가 쓰는 image는 거부하므로 진행 중인 평가를 깨뜨리지 않는다. base image를 지우면 다음 실행 때 다시 받는다.

---

### 2. Native 방식과 Harbor 방식의 차이

| | Harbor | native |
| --- | --- | --- |
| container | Harbor가 `docker compose`로 task별 `environment/Dockerfile`을 **build**해서 띄움 (`<trial>-main:latest`) | rLLM도 docker backend에서는 `docker build`로 task별 image(`rllm-task-<task_id>`)를 만들어 띄움. RUN 단계를 container 안에서 재생하는 것은 modal/daytona backend만 |
| derived image per task | 정상 종료 시 `compose down --rmi all`로 삭제. 비정상 종료 시 남음 | **삭제하지 않음** (재실행 cache로 남김) |
| harness | Harbor scaffold (`harbor/agents/`). 20종, `harbor:<이름>` | rLLM harness (`rllm/harnesses/`). `rllm agent list` |
| harness install | task마다 container 안에서 설치 | `--agent-image auto`로 한 번 구워 mount |
| verifier | Harbor verifier → `TrialResult.verifier_result` → `harbor_reward_fn` | task의 `tests/test.sh`를 rLLM이 직접 실행 → `reward.txt` |
| trajectory | Harbor ATIF trajectory를 rLLM Episode로 변환 | gateway가 모든 LLM 호출을 capture해 Step/Episode 구성 (학습과 동일 경로) |
| timeout | `task.toml` 값 + `RLLM_HARBOR_SESSION_TIMEOUT_S` 상한 | `task.toml` 값만 |
| log | `$RLLM_HOME/harbor_trials/<trial>/` (Harbor 형식) | `$RLLM_HOME/eval_results/<run>/episodes/` |
| train | `examples/harbor_swe` (RemoteAgentFlowEngine + tinker) | `recipe/grpo/qwen3_5` (AgentFlowEngine + verl) |


