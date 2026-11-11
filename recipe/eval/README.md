# rLLM evaluation (native)

A guide to evaluating SWE-bench Verified, SWE-bench Pro and SWE-bench Pro V2 with `rllm eval`.

**Evaluate with the rLLM native path.** rLLM starts the sandbox itself, runs an rLLM harness (`--agent openhands-sdk` and others) in it, and grades with the task's `tests/test.sh`. Furthermore, rLLM itself supports the agent network block, the hidden git history and the detailed timeouts functions.

| Path | `--agent` | Status |
| --- | --- | --- |
| **native** | no prefix, e.g. `openhands-sdk`, `mini-swe-agent`, `oracle` | **In use.** rLLM `SandboxTaskHooks` + rLLM harness + `ShellScriptEvaluator` |
| harbor | `harbor:` prefix, e.g. `harbor:mini-swe-agent` | **Deprecated.** No longer used for evaluation; kept for reference in [Appendix B](#appendix-b-deprecated-harbor-path) |

Every evaluation uses `--sandbox-backend docker` (the local Docker daemon).

**Before running an evaluation, go through the [checklist in section 1](#1-pre-evaluation-checklist).** If any of the agent network block, hidden git history, agent kwargs, timeouts or model generation kwargs is missing, the score is not comparable with runs under other conditions, or the answer leaks and the score is inflated.

---

## 0. Environment and rLLM background

### 0.1 Container

- Base image: `pytorch/pytorch:2.12.1-cuda13.0-cudnn9-devel`.
- During evaluation the agent and verifier sandboxes are launched from inside this container through the host Docker daemon (docker out of docker, dood).
- So the container that runs rLLM needs three options:

  * `-v /var/run/docker.sock:/var/run/docker.sock`: share the host Docker daemon.
  * `--network host`: sandboxes reach the rLLM model gateway at `host.docker.internal`. The gateway binds `0.0.0.0` inside the rLLM process (= this container), so the container must be on the host network for sandboxes to reach it. On a bridge network the sandboxes cannot reach the gateway.
  * `-v /path/to/shared:/path/to/shared`: mount a shared host directory, and keep `$RLLM_HOME` (datasets, results) at the same path as on the host (0.3).

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

### 0.2 Installation

The container needs the Docker CLI.
```
apt-get update && apt-get install curl
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
cd /workspace/rllm
uv venv --python 3.12
source .venv/bin/activate

# [harbor] extra: the client that downloads Harbor Registry datasets such as harbor:swebench-verified (needed by native eval too)
uv pip install -e ".[harbor]"

apt-get update && apt-get install -y docker.io docker-compose-v2
# docker is included in [project].dependencies -> no need to install
```

### 0.3 Storage location

rLLM keeps datasets and evaluation results under `$RLLM_HOME` (default `~/.rllm`). In this setup, where rLLM runs dood-style inside a container rather than on the host, point it at **a large volume mounted at the same path as on the host** (`/raid/rllm-work` in the example above). Hundreds of task directories and episode JSONs pile up there, and anything under the container root disappears with the container.

The value below is assumed throughout this document. If you change it, datasets and results pulled earlier live elsewhere and look missing.
Fixing this path within the project lets everyone share the rLLM settings (`config.json`), each other's benchmark results, the SWE-bench Verified subset, training data built with rLLM, and so on.

```bash
export RLLM_HOME=/raid/rllm-work/rllm-home
```

### 0.3.1 Environment variables

| Var | Default | Why |
| --- | --- | --- |
| `RLLM_HOME` | `~/.rllm` | Datasets, results, `config.json` (model setup) |
| `RLLM_ROLLOUT_TIMEOUT_S` | unset (no limit) | Budget for one whole rollout (agent + verifier). The verifier's share is set aside first and what is left is the agent's limit. See 1.3 |
| `RLLM_HARNESS_RUN_TIMEOUT_S` | `1800` | Agent limit. **Ignored when `task.toml` sets `[agent].timeout_sec`**, which takes precedence. See 1.3 |
| `RLLM_VERIFIER_TIMEOUT_S` | `600` | Verifier limit. **Ignored when `task.toml` sets `[verifier].timeout_sec`**, which takes precedence. See 1.3 |
| `RLLM_AGENT_IMAGE` | `auto` | Same values as the `--agent-image` flag (`auto` / `skip` / `repo:tag`) |
| `HF_HOME` | `~/.cache/huggingface` | Where the `swebench_pro` builder downloads the HF dataset |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ... | `empty` when unset | Real values are not needed with the proxy. If exported, they are passed into the task container, so do not keep real keys in the shell when evaluating untrusted tasks (the agent runs arbitrary commands) |
| `RLLM_API_KEY` | unset | After `rllm login`, or with this variable set, results and episodes are uploaded to the rLLM UI server. Pass `--no-ui` for results that must not leave the machine |

Note: task directories downloaded from the Harbor Registry (`harbor:swebench-verified` and others) go to **`~/.cache/harbor/tasks`**, not `RLLM_HOME`, and the `task_path` in `$RLLM_HOME/datasets/<name>/default.parquet` points there. A new container loses that cache, leaving the parquet without its task directories. Run `rllm dataset pull harbor:<name>` again in that case.

### 0.3.2 Dataset terms: catalog, parquet, task directory

The three concepts are related.

| Concept | What it is | Role |
| --- | --- | --- |
| **catalog** | `rllm/registry/datasets.json` (in the code) | Dataset name -> where and how to get it. What `rllm dataset list` shows. `harbor:<name>` is not in this file; the entry is built on the fly by asking the Harbor registry |
| **parquet (DatasetRegistry)** | `$RLLM_HOME/datasets/<name>/<split>.parquet` + `registry.json` | rLLM's tabular dataset, **one row per task**. `rllm eval` / `rllm train` always get the task list from it |
| **task directory (Harbor format)** | `task.toml`, `instruction.md`, `environment/Dockerfile`, `tests/test.sh`, `solution/solve.sh` | **What actually runs.** The format is Harbor's and rLLM native uses it as is. A `dataset.toml` (name, split, default agent) sits on top of the set of directories |

The key is how parquet and task directories relate: for a text-only dataset such as math problems (e.g. gsm8k), the parquet row itself is the instruction given to the model. For datasets that need a container, such as SWE tasks, the parquet row is a pointer, and the directory its `task_path` points to holds the real content.

What `rllm dataset pull` does per kind:
- `rllm dataset pull` is the CLI command that reads a catalog entry and actually fetches the data. What it does depends on the kind of entry.

| type | ex | pull | task directory | parquet row |
| --- | --- | --- | --- | --- |
| HF dataset | `gsm8k` | Fetch rows from HF, transform, register | none (materialised at eval time) | The instruction itself |
| **builder** | `swebench_pro`, `rllm-swesmith`, `deepswe` | Call the `builder` function with `out_dir=$RLLM_HOME/datasets/<name>`. **Builds** directories from the source + `dataset.toml` + registers | `$RLLM_HOME/datasets/<name>/<task_id>/` | Pointer |
| **`harbor:<name>`** | `harbor:swebench-verified` | Download finished directories with the Harbor Registry client + register. Used as the **data source** of native eval (the harness is native) | `~/.cache/harbor/tasks/<hash>/<task_id>/` (independent of `RLLM_HOME`) | Pointer |
| **recipe script** | `swebenchpro_v2_full` | `recipe/eval/<benchmark>/prepare_*.py` fetches the source, makes copies and registers them | `$RLLM_HOME/datasets/<name>/<task_id>/` | Pointer |

`rllm dataset pull swebench_pro` and `python -m rllm.data.swebench_pro_builder ...` call **the same function** (`build_benchmark`) and produce the same format. `pull` always writes to `$RLLM_HOME/datasets/swebench_pro`, builds all 731 tasks and registers the parquet. Calling the module directly takes `--out-dir`, `--task-ids`, `--limit` and does not register a parquet, so subsets are built with the direct call.

How `rllm eval <X>` resolves X:

1. A path (starting with `./` or `/`) -> `BenchmarkLoader` reads that directory's `dataset.toml` / `task.toml`. No parquet.
2. `harbor:<name>` -> ask the registry and build a catalog entry -> pull if there is no parquet -> build Tasks from the rows' `task_path`.
3. A plain name -> if `$RLLM_HOME/datasets/<X>/dataset.toml` exists and the agent is not `harbor:*`, read the directory directly as in 1. Otherwise catalog -> parquet (pull if missing).

```
catalog (datasets.json)           "name -> how to get it"
        │  rllm dataset pull / recipe prepare script
        ▼
task directory                     the actual content (task.toml, Dockerfile, test.sh ...)
   ├─ harbor:*  → ~/.cache/harbor/tasks/...
   └─ builder, recipe script → $RLLM_HOME/datasets/<name>/...
        │  register
        ▼
parquet ($RLLM_HOME/datasets/<name>/<split>.parquet)   one row per task, task_path pointer
        │  rllm eval / rllm train
        ▼
results   $RLLM_HOME/eval_results/<run>/
```

`default_verl.parquet` is a second copy of the same rows in the verl trainer's format. It does not matter for evaluation.

### 0.4 Connecting a model: two ways

`rllm eval` always sends model calls through the **rLLM model gateway**. There are two cases depending on what sits behind the gateway.

**(A) Proprietary models (OpenAI, Anthropic, Gemini, ...)**

Register the provider and API key. `rllm eval` then starts a LiteLLM proxy on its own and routes through it.

```bash
rllm model setup            # choose provider (openai / anthropic / gemini / openrouter / ...), API key, model
rllm model show             # show the current settings
```

After that only `--model` needs to change. Without it the model chosen in setup is used.

**How the API key is used during eval.** The key given to setup is stored in `$RLLM_HOME/config.json`. `rllm eval` starts a local LiteLLM
proxy with that key, and the gateway forwards requests to the proxy. The agent in the task container gets a placeholder (`sk-rllm-gateway` or `empty`), not the real key. In other words **the real key never leaves the rLLM process during evaluation.**

```
container(agent, placeholder key) → gateway → LiteLLM proxy(real key) → api.openai.com
```

So give the key only to setup and do not export it in the shell. If `OPENAI_API_KEY` is exported, setup conveniently picks it up as the default, but `rllm eval` run from that shell **puts the real key into the task container** instead of the placeholder (it works the same, but the key is exposed in a container where the agent runs arbitrary commands).

Run `unset OPENAI_API_KEY` after setup. `config.json` is plain text, so on a shared volume use `chmod 600 $RLLM_HOME/config.json`.

One exception: when the provider is `custom` (an OpenAI-compatible endpoint) and a key is entered, no proxy is started and `rllm eval` puts the key into its own `OPENAI_API_KEY` env var (`rllm/cli/eval.py`). rLLM then reads that value and **the real key goes into the task container.** This applies when evaluating a vLLM server with a key configured, as `custom`.

If the proxy fails to start: `uv pip install "litellm[proxy]"`.

**(B) A local model served with vLLM / SGLang**

Give the OpenAI-compatible endpoint with `--base-url`. `--model` is then required and must exactly match the server's `served-model-name`.

```bash
# vLLM. SWE agent evaluation needs tool calling and a reasoning parser (1.1)
vllm serve Qwen/Qwen3.5-9B --port 8000 --served-model-name Qwen/Qwen3.5-9B --max-model-len 262144 \
    --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_xml --enable-prefix-caching

rllm eval <benchmark> --agent openhands-sdk --sandbox-backend docker ... \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3.5-9B
```

With `--network host`, the server is reachable at `127.0.0.1:<port>` whether it runs on the host or in another container.

- **Tool calling**: harnesses that use native tool calling, such as openhands-sdk, get unparsed tool calls without `--enable-auto-tool-choice --tool-call-parser <parser>` (Qwen3/3.5: `qwen3_xml`).
- **Reasoning**: thinking models need `--reasoning-parser` (Qwen3/3.5: `qwen3`) to split reasoning from the content.
- **Prefix caching**: Qwen3.5 is a hybrid architecture, so vLLM turns prefix caching off by default. Agent evaluation resends the same prefix every turn, and `--enable-prefix-caching` cuts task time a lot. Outputs then differ at floating-point noise level, so runs that are compared should use the same setting.
- **Context**: use the same `--max-model-len` as training (`recipe/grpo/qwen3_5`: 262144).
- **Multiple GPUs**: serve 9B-class models with `--data-parallel-size <number of GPUs>` to take concurrent rollouts.

Model names: mini-swe-agent style agents require the `provider/model` form, so rLLM adds a prefix. `qwen`, `deepseek`, `gpt-*` and unknown names get `openai/` and go the OpenAI-compatible way; names containing `claude` get `anthropic/`. Names that start with an HF organisation, such as `Qwen/Qwen3-8B`, also get `openai/` (`openai/Qwen/Qwen3-8B`). litellm strips `openai/` before sending, so the server receives `Qwen/Qwen3-8B` unchanged.

### 0.5 Results

Results are kept in `$RLLM_HOME/eval_results/<benchmark>_<model>_<timestamp>/` as `meta.json`, `results.json` and `episodes/`.
The console prints Accuracy, Errors and, with `--attempts`, pass@k.

```bash
rllm view <run-id>
```

`Errors` are not tasks the model failed but **infrastructure failures** (image build failure, verifier timeout, gateway unreachable, ...). If it is not 0, find the cause first. The console prints the first five; the rest are in `results.json`.

Episodes with zero LLM calls (`No traces found`) count as 0 points, not as Errors. An episode with 0 steps is an infrastructure failure (the harness never started); run it again.

### 0.6 `rllm eval` options

`rllm eval <benchmark> [option]`. Full list: `rllm eval --help`.

**Sampling (enforced by the gateway per session)**

| option | description |
| --- | --- |
| `--temperature FLOAT` | Temperature. Shorthand for `--sampling-params temperature=...` |
| `--top-p FLOAT` | Nucleus sampling |
| `--max-tokens INT` | Max generated tokens per call |
| `--sampling-params TEXT` | `"temperature=0.6,top_p=0.95,top_k=20,presence_penalty=0.1"` or `@file.yaml` / `@file.json`. Keys other than the core `temperature`, `top_p`, `top_k`, `max_tokens` (`presence_penalty`, `min_p`, `repetition_penalty` ...) are passed to the backend (vLLM, ...) as is |

`@file` is a YAML/JSON file of sampling parameters, with the same keys as the `key=value` form. `--sampling-params` takes either a string or an `@file`, not both, and shorthand options such as `--temperature` override the file.
So keep a shared file per model and change only `--temperature` per experiment. Per-model files live in `recipe/eval/config/` (generation kwargs in 1.1).

```yaml
# recipe/eval/config/qwen3_5.yaml
temperature: 1.0
top_p: 0.95
top_k: 20
min_p: 0.0
presence_penalty: 0.0
repetition_penalty: 1.0
max_tokens: 16384
```

```bash
rllm eval ... --sampling-params @recipe/eval/config/qwen3_5.yaml
rllm eval ... --sampling-params @recipe/eval/config/qwen3_5.yaml --temperature 0.6
```

The file is not limited to the four core keys. The gateway merges the keys into the top level of the request JSON (`payload.update`), so any key that vLLM/SGLang accept in `extra_body` works (`min_p`, `repetition_penalty`, `presence_penalty`, `seed`, `stop`, `chat_template_kwargs`, `reasoning_effort` ...). On the proprietary-model path, the LiteLLM proxy runs with `drop_params` and **silently drops** keys the provider does not know (`top_k` for an OpenAI model is ignored without an error). Do not set `model`, `logprobs` or `return_token_ids`; the gateway manages them.

These values are applied by **the rLLM gateway overwriting the request payload**. Whatever temperature a harness sends on its own, these values win. Precedence (lowest first): config file defaults < `@file` < `key=value` < shorthand options such as `--temperature`. **When nothing is given, whatever the harness sends is used** (it differs per harness, so runs are not comparable; always set it).

**Repetitions and samples**

| option | description |
| --- | --- |
| `--attempts INT` | Independent rollouts per task. Reports pass@k for `k=1..N` (default 1). At temperature 0 the attempts are identical, so use a temperature above 0. Rollouts of the same task share the task image |
| `--max-examples INT` | Only the first N |
| `--task-indices TEXT` | `'0'`, `'3,7,12'`, `'0-9'`, combinable |
| `--split TEXT` | Dataset split. Default is the catalog's eval_split (`default` for Harbor sources, the registered name for registered copies) |

**Model connection**

| option | description |
| --- | --- |
| `--model TEXT` | Model name. Required with `--base-url` (must match the served name), otherwise the `rllm model setup` value |
| `--base-url TEXT` | OpenAI-compatible endpoint. Without it a LiteLLM proxy is started from the setup |

**Agent and grading**

| option | description |
| --- | --- |
| `--agent TEXT` | Harness name (`openhands-sdk`, `mini-swe-agent`, `oracle` ...) or `module:object` |
| `--agent-kwargs TEXT` | Harness settings, `"key=value,..."` or `@file.yaml`. For openhands-sdk: `@recipe/eval/config/openhands-sdk.yaml` (3.2) |
| `--evaluator TEXT` | Force a grader. Leave it out for native (the task's `tests/test.sh`) |

**Sandbox**

| option | description |
| --- | --- |
| `--sandbox-backend` | `docker`, `local`, `modal`, `daytona`, `e2b`, `runloop`, `gke`, `apple-container` |
| `--sandbox-concurrency INT` | Concurrent sandboxes (default 64). Concurrency × per-task resources (CPU, memory) must fit on the host |
| `--concurrency INT` | LLM call concurrency (default 64), separate from the sandbox count |
| `--agent-image TEXT` | `auto` (default) / `skip` / `repo:tag`. Bakes the harness into an image once and mounts it. Supports mini-swe-agent, opencode, claude-code, openhands-sdk (1.1) |
| `--snapshot / --no-snapshot` | Use modal/daytona snapshots. No effect on docker |
| `--warm-queue-size INT` | Pre-create N sandboxes. `-1` means the same as `--concurrency` |
| `--agent-network / --no-agent-network` | Docker only. Whether the sandbox has internet access while the agent runs. When off, only the LLM gateway is reachable. **Default OFF** (1.4). Write `--no-agent-network` explicitly |
| `--verify-network / --no-verify-network` | Docker only. Opens the sandbox's internet access right before the verifier runs. Default ON (1.4) |
| `--hide-git-history / --no-hide-git-history` | While the agent runs, keeps the task workdir's `.git` outside the sandbox (on the host) and replaces it with a one-commit repository; puts the original `.git` back right before the verifier. Docker backend only; enabling it on other backends is an error. **Default OFF, so always turn it on** (1.4) |

**Output**

| option | description |
| --- | --- |
| `--output TEXT` | Result JSON path (default `results.json` in the run directory) |
| `--episodes-dir TEXT` | Run directory (default `$RLLM_HOME/eval_results/<bench>_<model>_<timestamp>/`) |
| `--save-episodes / --no-save-episodes` | Save episode JSONs (default on) |
| `--ui / --no-ui` | Live upload to the rLLM UI server; on automatically when logged in. Pass `--no-ui` for results that must not leave the machine |

---

## 1. Pre-evaluation checklist

Run SWE evaluations with **every** item below set. Left to defaults, the conditions differ per harness and environment and results are not comparable, and some of them (network, git history) let the answer leak and inflate the score.

### 1.1 Checklist

| # | Item | Setting | If missing |
| --- | --- | --- | --- |
| 1 | **Agent image mount** | `--agent-image auto` | The harness is installed inside every sandbox. Installing needs the internet, so it cannot be combined with the agent network block (item 2) |
| 2 | **Agent network block** | `--no-agent-network` | The agent fetches the answer from the task repo's upstream (the next release, `git clone`). Off by default, but write it in the command anyway |
| 3 | **Verifier network** | `--verify-network` | Tasks whose tests download packages or modules (some Go tasks) fail. On by default |
| 4 | **Hidden git history** | `--hide-git-history` | The agent finds the answer in later commits left in the SWE image's `.git` (`git log --all --grep=<issue>`). **Off by default** |
| 5 | **Timeouts** | the dataset `task.toml`'s `[agent]` / `[verifier]` `timeout_sec` + `RLLM_ROLLOUT_TIMEOUT_S` | Runs with the `task.toml` values (they differ per benchmark). Env vars alone do not change the agent and verifier limits (1.3) |
| 6 | **Agent kwargs** | openhands-sdk: `--agent-kwargs @recipe/eval/config/openhands-sdk.yaml` | Runs with the SDK defaults (500 steps, ThinkTool included), a different step limit and tool set from training and earlier results (3.2) |
| 7 | **Model generation kwargs** | `--sampling-params @recipe/eval/config/<model>.yaml` | Whatever the harness sends (differs per harness) is used. **Check the file before evaluating** (below) |
| 8 | **vLLM serving options** | `--enable-auto-tool-choice --tool-call-parser ... --reasoning-parser ...`, the same `--max-model-len` as training | Tool calls are not parsed and rollouts end after 1 step with 0 points (0.4) |
| 9 | **Oracle check** | `--agent oracle` on the same dataset under the same sandbox conditions | Tasks that do not score 1.0 even with the gold patch (environment problems) get mixed into the model score |
| 10 | **Resources** | `--sandbox-concurrency` × the task's cpus/memory ≤ host | OOM or CPU contention makes verifiers time out and Errors grow |

**Check the model generation kwargs.** Open the per-model file in `recipe/eval/config/` before evaluating.
- Does it match the sampling values the model card recommends (temperature, top_p, top_k, min_p, presence_penalty)? E.g. `qwen3_5.yaml` holds Qwen3.5's thinking-mode recommendation.
- Is `max_tokens` enough for one turn? Thinking models write long reasoning every turn. For the same conditions as training, follow the training config.
- Does the server accept what the harness sends by default? E.g. openhands-sdk sends `reasoning_effort: "high"`, but Qwen3.8 serving accepts only `xhigh` / `medium` / `low`. Unless the file overrides it, the first LLM call fails with 400 and the rollout looks like a normal 1-step, 0-point finish (`qwen3_8-flash-next.yaml` pins `reasoning_effort: xhigh`).
- Is `chat_template_kwargs` (e.g. `enable_thinking`) what you intend? The dict is replaced as a whole, not merged key by key.
- To use other values, do not edit an existing file; make a new yaml and point to it (reproducibility of earlier results).

When a run starts, the table at the top of the console shows the applied conditions (Git history, Network, Sampling). Stop right away if they are not what you intended.

### 1.2 Standard command

```bash
export RLLM_HOME=/raid/rllm-work/rllm-home
# Budget for the whole rollout (agent + verifier). Same value as training (recipe/grpo/qwen3_5)
export RLLM_ROLLOUT_TIMEOUT_S=4800
# Used only for tasks whose task.toml has no timeout (1.3)
export RLLM_HARNESS_RUN_TIMEOUT_S=3600 RLLM_VERIFIER_TIMEOUT_S=1000

rllm eval <dataset> \
    --split test \
    --agent openhands-sdk \
    --agent-image auto \
    --agent-kwargs @recipe/eval/config/openhands-sdk.yaml \
    --sampling-params @recipe/eval/config/qwen3_5.yaml \
    --attempts 2 \
    --concurrency 48 \
    --sandbox-concurrency 48 \
    --hide-git-history \
    --no-agent-network \
    --verify-network \
    --sandbox-backend docker \
    --no-ui \
    --base-url http://127.0.0.1:8000/v1 \
    --model <served-model-name>
```

Follow section 2 for each benchmark's dataset preparation and oracle. SWE-bench Pro V2 is covered end to end, from dataset preparation to results, in [`swebench-pro-v2/README.md`](swebench-pro-v2/README.md).

### 1.3 Timeouts

A rollout has three limits, and each uses **the first value that is set** in the order below (`rllm/timeouts.py`, PR #31).

| Limit | Covers | `rllm eval` | Training (`rllm train`, verl recipe) | Default |
| --- | --- | --- | --- | --- |
| rollout | agent + verifier | `$RLLM_ROLLOUT_TIMEOUT_S` | `rllm.timeouts.rollout` → env | none (no limit) |
| agent | the harness run | `task.toml [agent].timeout_sec` → `$RLLM_HARNESS_RUN_TIMEOUT_S` | `rllm.timeouts.agent` → task.toml → env | 1800 s |
| verifier | `tests/test.sh` | `task.toml [verifier].timeout_sec` → `$RLLM_VERIFIER_TIMEOUT_S` | `rllm.timeouts.verifier` → task.toml → env | 600 s |

- **In eval, `task.toml` comes before the env vars.** `rllm eval` has no experiment config, so the config step in the table does not exist. For benchmarks whose `task.toml` sets `timeout_sec`, such as SWE-bench Verified and Pro, `RLLM_HARNESS_RUN_TIMEOUT_S` and `RLLM_VERIFIER_TIMEOUT_S` **do not apply.** The env vars are used only for tasks whose `task.toml` has no value.
- **To change the agent and verifier limits, edit `task.toml` in a dataset copy.** For SWE-bench Pro V2, `prepare_swebenchpro_v2.py --agent-timeout --verifier-timeout` writes them. For other benchmarks, make a copy (2.4) and edit it.
- **The rollout limit is a budget.** Its clock starts when the agent flow starts (sandbox creation and image build are not counted). The verifier's limit is set aside first, so the agent runs under `min(agent limit, rollout - verifier limit)` and the verifier under `min(verifier limit, remaining)`. If the agent uses up its share (`AGENT_TIMEOUT`), the verifier still grades that state in its reserved time. A verifier that runs over is `VERIFIER_TIMEOUT` (an infrastructure failure).
- A budget smaller than the verifier limit, which leaves the agent no time, is a configuration error (`ValueError`). Zero or negative values are errors too, not "no limit".
- **Caution**: on a benchmark whose `task.toml` gives the verifier 3000 s (the original SWE-bench Pro V2), setting only `RLLM_ROLLOUT_TIMEOUT_S=4800` leaves the agent `4800 - 3000 = 1800` s.
- **Same conditions as training**: `recipe/grpo/qwen3_5` uses rollout 4800 / agent 3600 / verifier 1000 s (`rllm.timeouts` in `config/rllm_grpo.yaml`, which beats `task.toml`). To evaluate with the same values, write agent 3600 and verifier 1000 into `task.toml` and set `RLLM_ROLLOUT_TIMEOUT_S=4800`. The agent then gets `min(3600, 4800 - 1000) = 3600` s.

### 1.4 Network and git history

* **Network**: the sandbox starts on the `rllm-sandbox-isolated` network, which has no route out. The only exit, a relay container (`rllm-egress-relay`), forwards only the LLM gateway port to the host, so the agent can call the model and nothing else. With the internet open, the agent could fetch the task repo's upstream (the next release, `git clone`) and copy the fix. `--verify-network` (default ON) attaches the sandbox to a regular bridge (`rllm-sandbox-verify`) after the agent finishes, so the verifier can download datasets, models and build backends. `--agent-network` opens the internet from the start. The implementation is in `rllm/sandbox/backends/egress.py`. Installing the agent inside the sandbox (`--agent-image skip` and the like) needs `--agent-network`, so evaluation uses `--agent-image auto`.
* **The answer leaks through git history**: the `.git` of SWE task images often holds commits later than the base commit. SWE-rebench, SWE-Gym and R2E-Gym keep the upstream fix commit in a branch or tag, and in SWE-smith HEAD is the commit that introduced the bug, so `git show HEAD` alone shows the answer. In practice 16% of 7,200 SWE-Master SWE-rebench rollouts looked through that history with commands such as `git log --all --grep=<issue>`. Hence `--hide-git-history`. Verifiers rely on the history (`git checkout <base_commit> -- tests`, `git checkout HEAD~1 -- <tests>`), so it is moved away and put back, not deleted. The repository location comes from `[environment].workdir` in `task.toml` (or the Dockerfile's `WORKDIR` when absent); with neither, the run stops with an error rather than pretending the history is hidden. The implementation is `rllm/sandbox/git_history.py`, driven by `SandboxTaskHooks`.
* **Sources in the agent venv**: the site-packages of the openhands-sdk agent image hold only `.pyc` files, no `.py` (`rllm/sandbox/strip_py_sources.py`). For tasks on the same repositories as packages the SDK depends on (fastmcp, starlette, uvicorn, websockets, filelock, cyclopts, ...), this keeps the agent from grepping the mounted venv and reading the newer release of that package (the answer).

---

## 2. Per-benchmark evaluation

On the native path rLLM creates the container itself, runs the harness in it, then runs the task directory's `tests/test.sh` and reads the reward file. `ShellScriptEvaluator` looks for `/tmp/rllm/reward.json` (the rLLM convention) first and otherwise reads `/logs/verifier/reward.json|txt` (the Harbor task convention).

```
SandboxTaskHooks      docker build -t rllm-task-<task_id> --rm . && docker run (+ harness image mount)
OpenHandsSdkHarness   runs the openhands-sdk runner inside the container
  └─ LLM calls ─────► rLLM model gateway (host.docker.internal) ──► vLLM / LiteLLM proxy
ShellScriptEvaluator  /tests/test.sh
                        ├─ /tmp/rllm/reward.json          (rLLM builder convention, first)
                        └─ /logs/verifier/reward.json|txt (Harbor task convention)
                      → reward
```

Harnesses are the rLLM harnesses listed by `rllm agent list`. The validated harness is openhands-sdk (section 3).

`<common options>` in the commands below means everything from `--agent` to `--model` in the 1.2 standard command. Run the oracle under the same sandbox conditions with `--agent oracle --base-url http://127.0.0.1:1/v1 --model oracle-dummy` (it calls no LLM, but the CLI requires a provider setting, so give it a dead port).

### 2.1 SWE-bench Verified

The data source is `harbor:swebench-verified` from the Harbor Registry (500 tasks). Without the `harbor:` prefix on `--agent`, rLLM skips the Harbor grader and grades with each task's `tests/test.sh`.

```bash
rllm dataset pull harbor:swebench-verified

# Environment check: apply the gold patch and run only the verifier
# Tasks that do not score 1.0 in the oracle check can never be solved by the model; exclude them (known example: `astropy__astropy-7606`)
rllm eval harbor:swebench-verified --agent oracle --sandbox-backend docker \
    --hide-git-history --no-agent-network --verify-network \
    --concurrency 8 --sandbox-concurrency 8 --no-ui \
    --base-url http://127.0.0.1:1/v1 --model oracle-dummy

rllm eval harbor:swebench-verified <common options>
```

- Verified's `task.toml` gives 1 CPU and 4 GB of memory. To change resources or timeouts, make a copy as for the subset (2.4, `swebench-verified/`).
- The base images of all 500 Verified tasks take about 2 TB. Check the disk before a full run.

### 2.2 SWE-bench Pro (v1)

The `swebench_pro` entry in the rLLM catalog has its own builder. It combines HuggingFace `ScaleAI/SWE-bench_Pro` with the per-instance `run_script.sh` / `parser.py` of `scaleapi/SWE-bench_Pro-os` into task directories.
The verifier reproduces the upstream `swe_bench_pro_eval.py` flow (agent diff → reset to base_commit → apply the diff → check out the gold tests → F2P/P2P eval) in `tests/test.sh`.

```bash
rllm dataset pull swebench_pro          # creates 731 task directories in $RLLM_HOME/datasets/swebench_pro/

rllm eval swebench_pro --agent oracle --sandbox-backend docker \
    --hide-git-history --no-agent-network --verify-network \
    --concurrency 8 --sandbox-concurrency 8 --no-ui \
    --base-url http://127.0.0.1:1/v1 --model oracle-dummy

rllm eval swebench_pro <common options>
```

The image is `jefzda/sweap-images:<tag>`, different per task, pulled at `docker run` time when missing. The builder writes 4 CPUs and 16 GB of memory into `task.toml`, and the Docker backend limits the container to that. The JS/Go test suites are large, so too high a `--sandbox-concurrency` runs the host out of memory first. The HF dataset has no CPU or memory information; 4 / 16384 is the builder author's choice, based on the upstream evaluation script using 1-4 CPUs and 5-30 GiB (see the builder comments).

For the v1 subset see `swebench-pro/`. The Harbor Registry's `harbor:swebenchpro` (the same 731 tasks, built by the Harbor adapter) has 1 CPU and 4 GB, so the verifiers of the Go repositories do not finish in time. Use `swebench_pro` as the source for native evaluation (Appendix B.4).

### 2.3 SWE-bench Pro V2

The curated release Scale published on 2026-09-22 (642 tasks). It is not in the Harbor Registry; dataset preparation, oracle, evaluation and results are covered in [`swebench-pro-v2/README.md`](swebench-pro-v2/README.md).

```bash
python recipe/eval/swebench-pro-v2/prepare_swebenchpro_v2.py --agent-timeout 3600 --verifier-timeout 1000   # -> swebenchpro_v2_full
rllm eval swebenchpro_v2_full <common options>
```

### 2.4 Evaluating a subset

- **By index**: `--max-examples N` (the first N), `--task-indices 0-4,17,42`. The index is the row order of `$RLLM_HOME/datasets/<name>/<split>.parquet`.
- **A subset pinned by instance_id**: **copy** the task directories under `$RLLM_HOME/datasets/<subset name>/` and register them as a separate dataset. Being a copy, its `task.toml` (timeouts, resources) can be edited without touching the original, and the evaluated tasks do not change with whatever images were pulled. Per-benchmark scripts: `swebench-verified/prepare_swebench_verified_subset.py`, `swebench-pro/prepare_swebenchpro_subset.py`, `swebench-pro-v2/prepare_swebenchpro_v2.py --ids`.

instance_id → index:

```bash
python - <<'PY'
import os, pandas as pd
name = "swebench-verified"
want = {"django__django-11265", "sympy__sympy-16792"}
df = pd.read_parquet(f"{os.environ['RLLM_HOME']}/datasets/{name}/default.parquet")
print(",".join(str(i) for i, t in enumerate(df["task_id"]) if t in want))
PY
```

### 2.5 Other notes

* **Image resource limits**: the `[environment]` cpus/memory of `task.toml` are applied to the Docker container. Verified is small: 1 CPU, 4 GB.
* **Images**: each task's `environment/Dockerfile` is built into an `rllm-task-<task_id>` image, which is **not deleted** (a cache for reruns). Base images are left too. Cleanup is in Appendix A.
* **Repeats of a task**: the rollouts of `--attempts N` build the task image once and share it.

---

## 3. Per-harness settings

In principle only `--agent` changes, but harnesses differ in how they are installed and how they connect to the model, so use only validated combinations.

### 3.1 Support table

| harness | native (`--agent <name>`) |
| --- | --- |
| openhands-sdk | **Reference.** `--agent openhands-sdk --agent-image auto --agent-kwargs @recipe/eval/config/openhands-sdk.yaml` (3.2) |
| mini-swe-agent | Yes. `--agent mini-swe-agent --agent-image auto` |
| opencode | Yes. `--agent opencode --agent-image auto` (3.3) |
| openhands (openhands-ai) | None (not implemented: TODO) |
| claude-code, codex, aider, ... | Not validated |

`--agent-kwargs` uses the same format as `--sampling-params`: `"key=value,..."` or `@file.yaml` / `@file.json`. Nested dictionaries only via `@file`, and CLI values win key by key. Among native harnesses only `openhands-sdk` takes them; others ignore them with a warning.

### 3.2 openhands-sdk

Runs the SDK as an rLLM harness. Three files make it up.

| File | Role |
| --- | --- |
| `rllm/harnesses/openhands_sdk.py` | `OpenHandsSdkHarness`. Install script, env, placing the runner, the run command |
| `rllm/harnesses/tools/openhands_sdk_runner.py` | The script that drives the SDK. openhands-sdk is a library, not a CLI, so the harness writes this script into the sandbox and runs it with the SDK's interpreter |
| `rllm/registry/agents.json` | Registers `openhands-sdk` (listed by `rllm agent list`) |

* **Trajectory**: the gateway captures every LLM call and the engine builds the episode. `tool_calls` stay in native form, the same path as training (`recipe/grpo/qwen3_5`). The runner writes no trajectory file.
* **Grading**: rLLM runs the task's `tests/test.sh` itself.

**`--agent-kwargs` (always set it).** `recipe/eval/config/openhands-sdk.yaml`:

| key | Meaning | Value | When omitted |
| --- | --- | --- | --- |
| `max_iterations` | Agent step limit per rollout (`Conversation(max_iteration_per_run=...)`) | 250 (same as training's `agent_step_limit`) | SDK default 500 |
| `include_default_tools` | Which SDK built-in tools to include (`Agent(include_default_tools=...)`). `[]` includes none | `[FinishTool]` | `[FinishTool, ThinkTool]` |
| `strict_tool_calls` | When `true`, tool calls the model got wrong (`str_replace` → `file_editor`, ...) come back as errors instead of being repaired by the SDK | `false` (SDK default; earlier results were measured with it) | `false` |

- ThinkTool only records thoughts, so for a model with reasoning on (the runner resends the previous turns' reasoning) it only spends steps. FinishTool is how the agent signals it is done, so it stays.
- Training runs with `strict_tool_calls: true` (`openhands_strict_tool_calls` in `recipe/grpo/qwen3_5/config/config.yaml`). For the same conditions as validation during training, make a separate yaml with `strict_tool_calls: true`. Runs that are compared should use the same value.
- The harness passes the values to the runner as env vars, and the runner's first log line (`default_tools=... max_iterations=...`) shows what was applied. Unknown keys are logged as WARNING.

**Set reasoning options with `--sampling-params`.** The gateway writes the session's sampling params over every request body (`payload.update`), so `reasoning_effort` and `chat_template_kwargs` are fixed by one model file, whatever the harness. If the server does not accept the SDK's default `reasoning_effort: "high"`, the first call fails (1.1). Keys whose value is `null` are dropped from the sampling params, so "do not send" cannot be expressed; set an accepted value.

**Thinking models need their past reasoning resent.** openhands-sdk resends the previous turns' reasoning only for kimi, deepseek and minimax. For Qwen3.x and GLM the previous turns then render as an empty `<think></think>`, the model writes tool calls inside an unclosed think block, and the calls are not parsed. The runner (`ReasoningReplayLLM`) makes up for it, sending the reasoning in both `reasoning_content` and `reasoning` (vLLM below 0.22 reads only the latter).

**`--agent-image auto` removes the install cost.** uv + Python 3.12 + the SDK are baked once into `/opt/rllm/agent` and mounted read-only into the task container, so nothing is installed per task (measured: a qutebrowser task went from 163 s to 47 s overall, `env_install` from 112 s to 0 s). The bake turns the site-packages' `.py` files into `.pyc` (1.4).
- **The mount does not cover every image.** The harness runs `import openhands.sdk` with the mounted python first and, if that fails, falls back to a per-task install, logging `openhands-sdk: agent mount cannot serve <task>; installed the SDK per task instead` as WARNING. **The fallback install needs the internet and therefore fails under `--no-agent-network`.** Its time is counted in `agentflow`, not `env_install`.
  - The SDK must not import from the task repo. The harness command runs in the task workdir, so when the repo has a package named like an SDK dependency (`/testbed/aiohttp`, `/testbed/pydantic`, `/testbed/tornado`, ...), **both** the mount probe and the fallback install check fail and the agent never runs. There are two ways in: `python -c` putting the cwd first on `sys.path`, stopped with `-I` (which also ignores the image's `PYTHONPATH` / `PYTHONHOME`), and litellm running `sys.path.append(os.getcwd())` on import, stopped by importing from an empty temporary directory (both probe and runner).
  - musl (Alpine) images cannot run a glibc interpreter. The SWE-bench Pro V2 prepare script adds a glibc runtime to those images so the mount works (`swebench-pro-v2/README.md`).
  - glibc images depend on the glibc generation of the bake. Baking on `debian:bullseye-slim` (2.31) covers images with 2.31-2.36. Baking on `ubuntu:22.04` (2.35) makes uv pick manylinux_2_34 wheels, and `cryptography` then needs `GLIBC_2.33` and breaks imports on 2.31 images.
  - The bake stage does not use apt. bullseye is EOL, so that version is 404 in the security pool (`apt-get install curl` exits 100); the uv binary is copied from the official uv image. uv ships its own TLS roots, so ca-certificates is not needed either.
- **The bake image tag** (`rllm-agent-<hash>`) is a hash of the install script and the build context (Dockerfile and the files copied with it) (`agent_image_tag`). Changing the bake recipe changes the tag, and the image is baked again. The same holds for the other harnesses (mini-swe-agent, opencode, claude-code).
- **The version** is pinned by `SDK_VERSION` in `rllm/harnesses/openhands_sdk.py` (default `1.42.1`) and can be overridden with `RLLM_OPENHANDS_SDK_VERSION`, `RLLM_OPENHANDS_PYTHON_VERSION`. The bake recipe reads the same constants, so the mounted and per-task installs cannot drift apart.
- The SDK log is tee'd to `/tmp/openhands-sdk.log` in the container. On images without tmux the SDK warns that it falls back to a subprocess terminal; it works fine.

### 3.3 opencode

No extra options. The rLLM harness registers the gateway as an openai-compatible custom provider (`rllm-gateway`) and calls it through Chat Completions.

```bash
rllm eval <dataset> --split test --agent opencode --agent-image auto \
    --hide-git-history --no-agent-network --verify-network \
    --sandbox-backend docker --concurrency 8 --sandbox-concurrency 8 --no-ui \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3.5-4B \
    --sampling-params @recipe/eval/config/qwen3_5.yaml
```

---

## Appendix A. Image cleanup

On a shared host other people's runs are mixed in, so list first.

```bash
docker images --format '{{.Repository}}:{{.Tag}} {{.Size}} {{.CreatedSince}}' | grep '^rllm-task-'       # native task images
docker images --format '{{.Repository}}:{{.Tag}}' | grep '^rllm-task-' | xargs -r docker rmi             # delete, for example
docker images --format '{{.Repository}}:{{.Tag}} {{.Size}}' | grep '^rllm-agent-'                       # harness bake images
docker image prune                                                                                       # dangling layers
```

`docker rmi` refuses images used by running containers, so it does not break an evaluation in progress. Deleted base images are pulled again on the next run.

---

## Appendix B. (deprecated) Harbor path

> **Deprecated.** Evaluate with the native path. The Harbor path does not support the agent network block (Harbor 0.3.0 ignores the per-phase `network_mode` in `task.toml`), the agent image mount or the rollout timeout budget, and it is a different execution path from training. What follows is kept for reproducing or interpreting earlier results.

The Harbor path is chosen with `--agent harbor:<scaffold>`. Harbor's `Trial.run()` handles the environment build, the agent and the verifier.

### B.1 Environment

- **Shared volume**: Harbor bind-mounts `$RLLM_HOME/harbor_trials/{trial}/verifier` into the task container, and the host Docker daemon resolves that mount. So `$RLLM_HOME` must exist on the host **at the same path**. With a path that exists only inside the container (`~/.rllm`, `/workspace/rllm`), the verifier's reward file ends up only on the host and every task ends with `RewardFileNotFoundError`.
- **docker compose**: Harbor calls `docker compose`, so the container needs the compose plugin (`docker-compose-v2`).
- **Gateway address**: Harbor's compose file does not add `host.docker.internal` to the task container, and the Linux Docker Engine does not know that name by default (cf. Docker Desktop). On Linux rLLM therefore rewrites the URL to the docker0 gateway IP from `docker network inspect bridge` (usually `172.17.0.1`). This only works when the rLLM container uses `--network host`.
- **Env var** `RLLM_HARBOR_SESSION_TIMEOUT_S` (default `900`): limit for one trial (agent + verifier). The verifier phase alone takes over 15 minutes on SWE-bench Pro's Go repositories, so with the default even the oracle test scores 0 on timeout. Set `3000` or more.

### B.2 Evaluation

| Benchmark | Name | Tasks | Base image |
| --- | --- | --- | --- |
| SWE-bench Verified | `harbor:swebench-verified` | 500 | `swebench/sweb.eval.x86_64.<repo>_1776_<instance>` |
| SWE-bench Pro | `harbor:swebenchpro` | 731 | Pre-built image per task |

```bash
export RLLM_HARBOR_SESSION_TIMEOUT_S=3600

rllm eval harbor:swebench-verified --agent harbor:mini-swe-agent --sandbox-backend docker \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3-8B --sandbox-concurrency 8
rllm eval harbor:swebenchpro       --agent harbor:mini-swe-agent --sandbox-backend docker \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3-8B --sandbox-concurrency 8
```

- Without `--agent`, the Harbor dataset's default `harbor:mini-swe-agent` is used. Other scaffolds: `harbor:terminus-2`, `harbor:swe-agent`, `harbor:codex`, `harbor:claude-code`, `harbor:oracle` (applies the gold patch only, no LLM calls), and so on.
- Subsets are chosen by index (`--max-examples`, `--task-indices`). To run a registered copy of task directories with a Harbor harness, its parquet rows need `task_path` and `--evaluator harbor_reward_fn` must be given; when the name does not start with `harbor:`, the CLI cannot find the evaluator by itself. Copy from `harbor:swebenchpro` (the Harbor cache). The rLLM builder's (`swebench_pro`) `tests/test.sh` writes only `/tmp/rllm/reward.json` while the Harbor verifier reads only `/logs/verifier/reward.txt|json` (`RewardFileNotFoundError`), and the `docker_image` in the builder's `task.toml` makes Harbor skip the Dockerfile so the container dies with `exit 126`.

### B.3 Notes

* **Timeouts**: Harbor applies `[agent].timeout_sec` and `[verifier].timeout_sec` (3000 s each for SWE-bench) as given, and rLLM's `RLLM_HARBOR_SESSION_TIMEOUT_S` caps the whole trial on top; the shorter one wins. Harbor **retries a verifier timeout once** (`stop_after_attempt(2)`). Trials that hit the session limit count as **Errors**, not 0 points, and rLLM cleans up their containers, networks and derived images itself (`run_harbor_trial`).
* **Resource limits**: `task.toml` as is. Harbor applies the `[environment]` cpus/memory as compose `deploy.resources.limits`. The registry's `swebenchpro` has 1 CPU and 4 GB, so the verifiers of the Go repositories do not finish in time (task instance: flipt).
* **Harness install per task**: Harbor's mini-swe-agent runs `apt-get install build-essential` and then `uv tool install mini-swe-agent` in the container every time. It adds 1-2 minutes per task and needs the internet.
* **Git history**: `--hide-git-history` also applies through Harbor trial hooks (hide at `AGENT_START`, restore at `VERIFICATION_START`, clean up at `END` / `CANCEL`). Harbor's docker environment `download_dir` changes the owner of the source to the host user, so only a single tar file made inside the container crosses.
* **Images**: Harbor builds `environment/Dockerfile` into a derived image per task, `<trial>-main:latest` (about 7.5 GB for Verified), and deletes it with `compose down --rmi all` on a normal exit. After an abnormal exit it remains.

```bash
docker images --format '{{.Repository}}:{{.Tag}} {{.Size}} {{.CreatedSince}}' | grep -- '-main:latest'   # Harbor leftovers
docker images --format '{{.Repository}}:{{.Tag}}' | grep -- '-main:latest' | xargs -r docker rmi
docker network ls --format '{{.Name}}' | grep '_default$' | grep -E 'instance_|__' | xargs -r docker network rm  # Harbor leftover networks
```

### B.4 `harbor:swebenchpro` vs `swebench_pro`

**Two independently built sets of task directories** for the same benchmark and the same Docker images. The rLLM builder does not convert Harbor tasks; it builds from the source data.

| | `harbor:swebenchpro` | `swebench_pro` |
| --- | --- | --- |
| Built by | The Harbor adapter, uploaded to the registry | `rllm/data/swebench_pro_builder.py` (`rllm dataset pull swebench_pro`) |
| Input | Downloads 731 finished task directories | HF `ScaleAI/SWE-bench_Pro` rows + `run_script.sh`, `parser.py` from `scaleapi/SWE-bench_Pro-os` |
| `task.toml` resources | `cpus = 1`, `memory_mb = 4096` | `cpus = 4`, `memory_mb = 16384` (builder `_DEFAULT_RESOURCES`) |
| `tests/test.sh` | The adapter's wrapper | A wrapper the builder synthesises |
| Docker image | `jefzda/sweap-images:<tag>` | The same image |
| Location | `~/.cache/harbor/tasks/...` | `$RLLM_HOME/datasets/swebench_pro/<instance_id>/` |

| Command | Source | Container resources |
| --- | --- | --- |
| `rllm eval harbor:swebenchpro --agent harbor:mini-swe-agent` | Harbor | 1 CPU, 4 GB |
| `rllm eval harbor:swebenchpro --agent mini-swe-agent` | **Harbor** (native harness, but the task directories are Harbor's) | 1 CPU, 4 GB. The native path also applies the `task.toml` values as is |
| `rllm eval swebench_pro --agent mini-swe-agent` | rLLM builder | 4 CPUs, 16 GB |
| `rllm eval swebench_pro --agent harbor:*` | - | **Not possible.** The builder's `test.sh` writes only `/tmp/rllm/reward.json` and the Harbor verifier reads only `/logs/verifier/` |

### B.5 Per-harness settings on Harbor

**opencode (`harbor:opencode`).** Without `--agent-kwargs @recipe/eval/config/harbor-opencode-vllm.yaml` every task ends with 0 points after one LLM call. Harbor's opencode takes the model as `openai/<model>` and registers it under provider `openai`, and opencode uses the **Responses API** (`/v1/responses`) whenever the provider id is `openai`, regardless of the SDK. vLLM's Responses API rejects the second turn's assistant message with 400. So the config attaches the Chat Completions SDK (`@ai-sdk/openai-compatible`) to another provider id (`openrouter`). Keep `--model` as the served name. rLLM fills in `options.baseURL` (the gateway session URL), `options.apiKey` and the model_name prefix per trial (`trial_helper._apply_opencode_provider_config`).

**openhands-sdk (`harbor:openhands-sdk`).** The harbor 0.3.0 scaffold creates a venv with **the task image's system Python** and runs `pip install openhands-sdk`, and **all** 100 tasks of the SWE-bench Pro subset failed (Python < 3.12, a `pip.conf` pointing at an unresponsive pip index, no `apt-get` / `stdbuf` on Alpine, no `curl`). `recipe/eval/patches/harbor-0.3.0-openhands-sdk.patch` fixes the installed harbor: Python 3.12 via uv, `uv pip install` (ignores the pip config), `curl` and `coreutils` per package manager, uv installed separately in `/opt/openhands-sdk-uv`, 3 download retries, the gateway URL read from the trial's `AgentConfig.env`, and resending previous turns' reasoning.

```bash
bash recipe/eval/scripts/apply_harbor_patches.sh            # --check to inspect, --revert to undo
export RLLM_HARBOR_SESSION_TIMEOUT_S=4200
rllm eval swebenchpro_100 --split test \
    --agent harbor:openhands-sdk --evaluator harbor_reward_fn \
    --sandbox-backend docker --concurrency 8 --sandbox-concurrency 8 --no-ui \
    --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3.5-4B \
    --sampling-params @recipe/eval/config/qwen3_5.yaml \
    --agent-kwargs @recipe/eval/config/harbor-openhands-sdk.yaml
```

- Rerunning `uv pip install -e ".[harbor]"` reinstalls harbor and drops the patch; apply it again. Environments patched under the old name (`harbor-0.3.0-openhands-sdk-uv-install.patch`) need `uv pip install --reinstall harbor==0.3.0` before reapplying.
- Without `version` in `--agent-kwargs`, the latest openhands-sdk at run time is installed. Use `harbor-openhands-sdk.yaml` (= `1.42.1`) as is.
- Every task installs uv + Python 3.12 + the SDK inside the container (510 MB venv, about 180 packages, about 50 GB of PyPI traffic per 100 tasks, 16-19 s per task). Slow downloads exceed Harbor's agent setup limit (360 s) with `AgentSetupTimeoutError`.
- The trajectory is written to `$RLLM_HOME/harbor_trials/<trial>/agent/trajectory.json` (ATIF) and converted into an rLLM episode. The scaffold log is `openhands_sdk.txt` in the same directory.

### B.6 Native vs Harbor

| | Harbor (deprecated) | native |
| --- | --- | --- |
| container | Harbor **builds** each task's `environment/Dockerfile` with `docker compose` and starts it (`<trial>-main:latest`) | rLLM builds a per-task image (`rllm-task-<task_id>`) with `docker build` and starts it. Replaying RUN steps inside the container is only for the modal/daytona backends |
| derived image per task | Deleted with `compose down --rmi all` on a normal exit; left after an abnormal exit | **Not deleted** (kept as a rerun cache) |
| harness | Harbor scaffold (`harbor/agents/`), 20 kinds, `harbor:<name>` | rLLM harness (`rllm/harnesses/`), `rllm agent list` |
| harness install | Installed in the container per task (needs the internet) | Baked once with `--agent-image auto` and mounted |
| agent network | Open | Blocked with `--no-agent-network` (LLM gateway only) |
| verifier | Harbor verifier → `TrialResult.verifier_result` → `harbor_reward_fn` | rLLM runs the task's `tests/test.sh` itself → `/tmp/rllm/reward.json` (first) or `/logs/verifier/reward.json\|txt` |
| trajectory | Harbor ATIF trajectory converted into an rLLM episode | The gateway captures every LLM call and builds steps/episodes (same path as training) |
| timeout | `task.toml` values + the `RLLM_HARBOR_SESSION_TIMEOUT_S` cap | agent and verifier: the `task.toml` values, else `RLLM_HARNESS_RUN_TIMEOUT_S` / `RLLM_VERIFIER_TIMEOUT_S`; the rollout budget `RLLM_ROLLOUT_TIMEOUT_S` on top (1.3) |
| log | `$RLLM_HOME/harbor_trials/<trial>/` (Harbor format) | `$RLLM_HOME/eval_results/<run>/episodes/` |
| train | `examples/harbor_swe` (RemoteAgentFlowEngine + tinker) | `recipe/grpo/qwen3_5` (AgentFlowEngine + verl) |
