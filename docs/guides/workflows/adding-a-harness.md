---
title: 워크플로우용 harness 추가하기
description: qwen3_5 레시피에서 openhands-sdk 외의 에이전트(harness)에 워크플로우를 얹어 학습·평가하는 방법
---

# 워크플로우용 harness 추가하기

**harness**는 sandbox 안에서 실제로 도는 에이전트 프로그램임(openhands-sdk, mini-swe-agent, opencode 등).
`recipe/grpo/qwen3_5` 레시피에서 harness와 워크플로우는 서로 독립된 두 축으로 설계됨.

- harness 하나를 추가하면 등록된 모든 워크플로우를 그 harness에 얹을 수 있음.
- 워크플로우 하나를 추가하면 지원하는 모든 harness에서 쓸 수 있음.
- 필요한 클래스 수는 harness 수만큼이고, (harness × 워크플로우) 조합 수만큼 늘지 않음.

현재 상태:

| harness | 학습 | 평가 | 워크플로우 |
| --- | --- | --- | --- |
| openhands-sdk | `recipe.agent=openhands-sdk` | `workflow_harness:OpenHandsSdkWorkflow` | 지원 (AI-DLC 채점 포함) |
| mini-swe-agent | `recipe.agent=mini-swe-agent` | rLLM 기본 harness | 미지원 (지정하면 학습 시작 시 거부) |

워크플로우 자체를 추가하는 방법은 [워크플로우 추가하기](/guides/workflows/adding-a-workflow) 참고.

## harness마다 달라지는 부분

워크플로우 주입 중 일부는 모든 CLI harness에 공통이고, 일부는 harness마다 구현이 필요함.

| 요소 | 공통 여부 | 담당 |
| --- | --- | --- |
| 문서 업로드, 개수 검사 | 공통 | `WorkflowMixin` (CLI harness의 설정 작성 단계에 끼어듦) |
| 지시를 task 텍스트 앞/뒤에 붙이기 | 공통 | `WorkflowMixin` (실행 명령 조립 단계에 끼어듦) |
| `--agent-kwargs` 처리 (`workflow=` 등) | 공통 | `AgentKwargsMixin` (`WorkflowMixin`이 포함) |
| 학습/평가 채점기 연결 | 공통 | `evaluation_policy` 속성 |
| system prompt 교체 | **harness별** | harness 클래스가 구현 |
| 턴 예산 | **harness별** | harness 클래스가 구현 |
| system prompt 템플릿 내용 | **harness별** | 각 워크플로우가 harness마다 제공 |
| 도구 호출 해석(준수율 채점) | **harness별** | 채점기의 해석기(front end) |

공통 부분은 `recipe/grpo/qwen3_5/workflow_harness.py`에 이미 있음.
harness 추가 작업은 harness별 부분을 채우는 일임.

## 0. 전제: rLLM에 기본 harness가 있어야 함

- 워크플로우 클래스는 rLLM의 CLI harness(`BaseCliHarness` 하위 클래스) 위에 얹음.
- 현재 `rllm/harnesses/`에 있는 CLI harness 예: `openhands_sdk.py`, `mini_swe_agent.py`, `opencode.py`, `claude_code.py`, `codex.py`, `qwen_code.py`, `kimi_cli.py`, `aider.py`.
- 목록에 없는 에이전트라면 [Harnesses](/core-concepts/harnesses) 문서를 참고해 기본 harness부터 작성함.
- 기본 harness만으로 `rllm eval --agent <이름>`이 정상 동작하는지 먼저 확인해 두면 이후 문제를 분리하기 쉬움.

## 1. 워크플로우 클래스 작성

`workflow_harness.py`에 클래스 하나를 추가함.
mixin을 앞에, 기본 harness를 뒤에 둠.

```python
from rllm.harnesses.opencode import OpenCodeHarness


class OpenCodeWorkflow(WorkflowMixin, OpenCodeHarness):
    """opencode following ``workflow`` (``None``: the plain harness)."""

    supports_system_prompt = True   # 2단계 참고

    def _system_prompt_env(self) -> dict[str, str]:
        ...

    def _write_system_prompt(self, sandbox, text: str) -> None:
        ...
```

- 이 클래스만으로 `workflow=`, `instruction_position=`을 `--agent-kwargs`로 받고, 문서 업로드와 지시 주입이 동작함.
- **`name`은 바꾸지 않음**(기본 harness의 이름 그대로).
  이름이 세 군데에서 키로 쓰이기 때문임.
  1. agent image mount: 미리 구운 에이전트 이미지를 이름으로 찾음.
     이름이 바뀌면 에러 없이 task마다 설치하는 느린 경로로 빠짐.
     현재 이미지 레시피가 있는 이름은 `mini-swe-agent`, `opencode`, `claude-code`, `openhands-sdk`.
  2. 워크플로우 등록 정보의 `system_prompt`, `scorers` 키.
  3. episode의 trajectory 이름 → 채점기의 도구 호출 해석기 선택.

## 2. system prompt 교체 지원

워크플로우가 실제로 지켜지려면 system prompt 교체가 사실상 필요함.
openhands-sdk의 경우 기본 프롬프트의 자체 절차 섹션이 사용자 메시지의 지시보다 우선해서, 교체 없이 돌린 실험에서 지시가 무시됨.
다른 에이전트도 기본 프롬프트에 작업 절차가 있는지 먼저 확인 필요.

구현할 것은 두 메서드임.

- `_system_prompt_env()`: 에이전트가 교체 템플릿을 읽도록 넘길 환경 변수.
- `_write_system_prompt(sandbox, text)`: 템플릿 내용을 sandbox에 쓰는 동작.

openhands-sdk 구현(참고):

```python
_SYSTEM_PROMPT_REMOTE = "/opt/openhands-sdk-system-prompt.j2"

class OpenHandsSdkWorkflow(WorkflowMixin, StepLimitedOpenHandsSdk):
    supports_system_prompt = True

    def _system_prompt_env(self):
        return {"OPENHANDS_SDK_SYSTEM_PROMPT_PATH": _SYSTEM_PROMPT_REMOTE}

    def _write_system_prompt(self, sandbox, text):
        sandbox.exec(self._heredoc_write(_SYSTEM_PROMPT_REMOTE, text), timeout=60, user="root")
```

- 템플릿 파일은 저장소 바깥 경로(예: `/opt/...`)에 씀.
- 에이전트 쪽에서 그 경로를 읽는 장치가 필요함.
  openhands-sdk는 rLLM의 runner(`rllm/harnesses/tools/openhands_sdk_runner.py`)가 환경 변수를 받아 SDK에 넘김.
  다른 에이전트는 설정 파일, CLI 옵션 등 그 에이전트의 방식에 맞춰야 함.
- 교체 방법이 없는 에이전트는 `supports_system_prompt = False`로 둠(기본값).
  - 이때 워크플로우 등록 정보에 이 harness용 템플릿을 넣으면 harness 생성 시 에러.
  - 템플릿 없이 지시만으로 돌 수는 있으나 지시가 무시될 위험이 큼.

## 3. 턴 예산

- rLLM 엔진은 harness의 `step_limit` 속성을 읽어, 그만큼 턴을 다 쓴 rollout을 턴 초과(`MAX_TURNS_EXCEEDED`)로 표시함.
- 학습의 `budget_reward_scale`(턴 예산 소진 시 reward 감쇠)이 이 표시에 의존함.
- 따라서 새 harness도 `step_limit`을 에이전트 실제 반복 한도로 전달해야 함.
  - openhands-sdk: `StepLimitedOpenHandsSdk`가 `OPENHANDS_MAX_ITERATIONS` 환경 변수로 전달.
  - mini-swe-agent: `train.py`의 `StepLimitedMiniSweAgent`가 실행 명령에 `agent.step_limit`을 넣음.
- `--agent-kwargs step_limit=...`로 문자열이 들어올 수 있으므로 `_after_configure`에서 `int`로 변환하고 `super()._after_configure()`를 호출함.

```python
class StepLimitedOpenCode(AgentKwargsMixin, OpenCodeHarness):
    step_limit: int = 50

    def _after_configure(self) -> None:
        super()._after_configure()          # AgentKwargsMixin의 기본 구현(빈 함수)까지 이어짐
        self.step_limit = int(self.step_limit)

    # build_env 또는 build_invocation에서 step_limit을 에이전트에 전달


class OpenCodeWorkflow(WorkflowMixin, StepLimitedOpenCode):   # 1단계 클래스를 이 형태로
    ...
```

- openhands-sdk도 같은 구조임(`OpenHandsSdkWorkflow(WorkflowMixin, StepLimitedOpenHandsSdk)`).

## 4. 학습에 연결: `train.py`

`_build_agent_flow`에 분기를 추가함.

```python
if agent == "opencode":
    from recipe.grpo.qwen3_5.workflow_harness import OpenCodeWorkflow

    return OpenCodeWorkflow(
        step_limit=step_limit,
        workflow=name,
        instruction_position=str(workflow.get("instruction_position", "suffix")),
    )
```

- `recipe.agent=opencode`로 선택함.
- 채점기 연결(`_build_hooks`)과 reward 합성(`_workflow_reward`)은 harness의 `evaluation_policy`와 등록 정보를 읽으므로 수정 불필요.
- `enable_thinking`은 openhands-sdk 전용 처리(chat template 인자 전달)라 다른 harness에는 해당 에이전트 방식으로 따로 구현해야 함.

## 5. 각 워크플로우에 harness용 자산 추가

harness를 추가해도 워크플로우 쪽 자산은 자동으로 생기지 않음.
쓰려는 워크플로우마다 다음을 추가함(`workflows/<워크플로우>/__init__.py`의 SPEC).

- `system_prompt["opencode"]`: 그 에이전트 **기본 프롬프트를 바탕으로** 절차 부분만 워크플로우용으로 바꾼 템플릿.
  openhands-sdk용 템플릿을 그대로 쓰면 도구 사용 규약이 맞지 않음.
- `scorers["opencode"]`: 준수율 채점기 factory.
  AI-DLC라면 같은 `_scorer`를 그대로 쓰되 6단계의 해석기가 필요함.

## 6. AI-DLC 채점 지원: 도구 호출 해석기

AI-DLC 채점은 에이전트의 도구 호출(셸 명령, 파일 생성·수정 등)을 읽어 단계 순서와 산출물 작성 여부를 판단함.
도구 이름과 인자 형식이 에이전트마다 다르므로 harness별 해석기가 필요함.

- 해석기 규약(`workflows/aidlc/reward/rubric/frontends/openhands.py` 참고):
  - `NAMES`: 이 해석기가 처리하는 harness 이름 집합.
  - `parse(name, args, observation)`: 도구 호출 하나를 채점용 동작(`Action`)으로 바꿈.
    동작 종류는 `shell`, `view`, `create`, `replace`, `insert`, `undo`, `other`.
- 새 해석기를 만들어 `workflows/aidlc/reward/episode.py`의 `FRONTENDS`에 등록함.
  - `rubric/` 디렉터리는 오프라인 채점기에서 그대로 복사한 코드(byte-identical)임.
    원본에서 가져온 해석기가 아니라면 `rubric/` 밖(예: `reward/` 아래)에 두는 편이 출처 구분에 좋음.
- 해석기가 없는 harness의 episode는 해석을 거부함.
  채점기는 경고를 남기고 verifier 결과만 반환하므로, 잘못된 해석으로 매긴 점수가 학습에 들어가지 않음.

## 7. 평가

```bash
rllm eval <dataset> --split test \
  --agent recipe.grpo.qwen3_5.workflow_harness:OpenCodeWorkflow \
  --agent-kwargs workflow=aidlc,step_limit=100,instruction_position=prefix \
  --agent-image auto --sandbox-backend docker --hide-git-history
```

`workflow=none`이면 같은 harness의 baseline임.

## 8. 확인 방법

- 단위 테스트: `recipe/grpo/qwen3_5/tests/test_workflow_harness.py`의 `test_mixin_brings_agent_kwargs_to_any_cli_harness`가 mini-swe-agent에 `WorkflowMixin`을 얹어 `--agent-kwargs workflow=...`가 동작하는지 확인하는 예시임.
- smoke 평가(task 2~3개)에서 확인할 것:
  - 에이전트가 실제로 LLM을 호출하는지(결과에 "No traces found"가 없어야 함).
  - sandbox 안 `<container_dir>`에 문서가 있고, system prompt 교체 파일이 쓰였는지.
  - 저장된 episode의 system 메시지가 `workflow=none` run과 다른지.
  - 준수율 signal이 나오는지(해석기를 붙인 경우).
- 학습 smoke: `recipe/grpo/qwen3_5/smoke_test.sh`로 1 step을 돌려 로그 첫 줄(`agent flow: ...`)에 harness, 워크플로우, 채점 여부가 기대대로 찍히는지 확인함.

## 주의점

- 기본 harness 이름에 맞는 에이전트 이미지 레시피가 없으면 rollout마다 에이전트를 설치함.
  rollout 시간이 크게 늘 수 있으므로 `rllm/sandbox/agent_image.py`에 레시피 추가를 검토함.
- mixin 순서는 `class X(WorkflowMixin, 기본harness)`여야 함.
  반대로 두면 문서 업로드·지시 주입이 기본 harness 동작에 가려짐.
- `_after_configure`를 구현할 때는 항상 `super()._after_configure()`를 먼저 호출해야 워크플로우 재검증이 함께 실행됨.
