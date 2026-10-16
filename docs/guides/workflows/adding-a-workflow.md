---
title: 워크플로우 추가하기
description: qwen3_5 레시피에 새 워크플로우(문서·지시·system prompt·준수율 채점)를 등록하고 학습과 평가에서 쓰는 방법
---

# 워크플로우 추가하기

`recipe/grpo/qwen3_5` 레시피에서 에이전트에게 특정 작업 절차를 따르게 하는 단위를 **워크플로우**라 부름.
현재 등록된 워크플로우는 AI-DLC(`aidlc_v4`), Spec Kit bug 절차(`speckit_bug`, 채점기 없음), OpenSpec OPSX 절차(`openspec_ff`, sandbox에서 `openspec` CLI 실행, 채점기 없음), Spec Kit SDD 핵심 절차(`speckit_sdd`, sandbox의 `/tmp/speckit-sdd/.specify`에 upstream 스크립트 탑재, 채점기 없음), Agent OS v2.1.1 spec 파이프라인(`agentos_v2`, upstream 설치 스크립트로 렌더한 명령 문서 4개, 채점기 없음) 다섯 개임.
이 문서는 새 워크플로우를 추가해 학습과 `rllm eval` 양쪽에서 쓰는 방법을 정리함.

- 워크플로우 추가에 harness 클래스, `train.py`, 평가 코드 수정은 필요 없음.
- 워크플로우 디렉터리 하나와 등록 한 줄로 끝남.
- harness(에이전트 프로그램) 자체를 추가하는 방법은 [harness 추가하기](/guides/workflows/adding-a-harness) 참고.
- 외부 워크플로우(spec-kit 등)를 옮겨 올 때 원문 변환은 공용 엔진 `workflows/_port.py` 위에서 워크플로우마다 편집표(`build.py`)로 기술함.
  - 예시는 `workflows/speckit_bug/`이고, 원문을 바꾼 결정·변경 내역·smoke 결과는 `porting/`에 기록되어 있음.

## 워크플로우가 하는 일

워크플로우는 task 위에 세 가지를 얹고, 에이전트가 그것을 따랐는지 채점함.

1. **문서**: 절차를 설명하는 문서를 sandbox의 고정 경로(예: `/ai-dlc`)에 업로드함.
   저장소 바깥 경로라 `git diff`나 verifier의 정리 작업에 걸리지 않음.
2. **지시(instruction)**: "이 문서를 따르라"는 짧은 안내를 task 텍스트 앞(`prefix`) 또는 뒤(`suffix`)에 붙임.
3. **system prompt 교체**: harness 기본 system prompt 중 절차를 지정하는 부분을 워크플로우용으로 바꿈.
   - openhands-sdk 기본 프롬프트에는 자체 절차 섹션(`<PROBLEM_SOLVING_WORKFLOW>`)이 있고, 이것이 사용자 메시지에 붙인 지시보다 우선함.
   - 교체 없이 돌린 Harbor 실험에서 에이전트가 지시를 무시함.
     사실상 필수 layer임.
4. **준수율 채점(선택)**: verifier가 돌기 직전에 sandbox에서 워크플로우 산출물을 읽고, 각 [0, 1] 범위의 signal을 계산함.
   - verifier의 reward와 해결 여부(`is_correct`)는 그대로 통과시키고 signal만 덧붙임.
   - 학습에서는 설정에 따라 이 signal 하나를 reward에 합성함.

실행 흐름은 학습과 평가가 동일함.

- harness 생성 시점: 워크플로우 이름 → 등록 정보 조회 → 파일·경로 검사 (sandbox 생성 전에 실패시킴).
- rollout 시작: 문서 업로드 → 업로드된 `.md` 개수 확인 → system prompt 파일 작성 → 지시를 붙인 task 텍스트로 에이전트 실행.
- rollout 종료: 산출물 수집 → verifier 실행 → 준수율 signal 추가.
- 학습만: `recipe.workflow.compliance_reward`가 켜져 있으면 지정 signal을 verifier reward와 합성.

## 1. 디렉터리 만들기

워크플로우 하나는 `recipe/grpo/qwen3_5/workflows/<이름>/` 패키지 하나에 모두 들어감.

```
workflows/<이름>/
├── __init__.py          # SPEC (등록 정보)
├── docs/                # sandbox로 업로드할 문서만. 하위 디렉터리 가능
│   └── core-workflow.md #   진입 문서 (이름은 자유, SPEC의 entry_doc과 일치)
├── instruction.md       # task 텍스트에 붙는 지시
├── system-prompt.j2     # harness별 system prompt 템플릿 (현재 openhands-sdk)
└── reward/              # (선택) 준수율 채점
```

`docs/` 규칙:

- `docs/` 안의 모든 항목이 그대로 업로드됨.
  지시나 system prompt 파일은 `docs/` 밖(옆)에 둠.
- 이름이 `.`으로 시작하는 항목은 업로드하지 않음.
- 업로드 후 sandbox 안의 `.md` 파일 수가 로컬 `docs/`의 `.md` 수와 다르면 rollout을 멈춤.
  일부만 올라간 상태로 돌면 "문서를 무시한 정책"과 구분이 안 되기 때문임.

## 2. 지시(instruction.md) 작성

- 진입 문서의 sandbox 절대 경로(`<container_dir>/<entry_doc>`, 예: `/ai-dlc/core-workflow.md`)를 **반드시 문자열로 포함**해야 함.
  포함하지 않으면 harness 생성 시 에러.
- 위치는 실행 설정 `instruction_position`으로 정함.
  - `prefix`: task 텍스트 앞. 레시피 기본값.
  - `suffix`: task 텍스트 뒤. 코드 기본값이자 Harbor 실험 배치.
- 데이터셋 프롬프트와의 충돌 주의.
  - SWE-Gym 프롬프트에는 자체 6단계 절차가 들어 있음.
  - 지시를 그 뒤(`suffix`)에 붙인 학습(2026-09-29)에서 rollout의 86%가 워크플로우 문서를 한 번도 열지 않음.
  - 대응: 지시를 앞(`prefix`)에 두고, 데이터셋 쪽에서 절차를 뺀 프롬프트 템플릿 사용(`scripts/prepare_swegym.py --instruction aidlc`로 만든 `swegym293_aidlc` 등).
  - 새 워크플로우도 데이터셋 프롬프트에 경쟁하는 절차가 있는지 먼저 확인 필요.

## 3. system prompt 템플릿 작성

- 시작점은 기존 템플릿 `workflows/aidlc_v4/system-prompt.j2`.
  - openhands-sdk 1.42.1 기본 프롬프트를 그대로 두고 `<PROBLEM_SOLVING_WORKFLOW>` 섹션만 바꾼 Jinja 템플릿임.
  - 나머지 15개 섹션(도구 사용 규약 등)은 유지해야 도구 호출 형식이 깨지지 않음.
- 복사 후 그 섹션만 새 워크플로우 절차로 다시 씀.
- 진입 문서 절대 경로를 문자열로 포함해야 함(지시와 같은 검사).
- SDK 버전(`rllm/harnesses/openhands_sdk.py`의 `SDK_VERSION`)을 올리면 기본 프롬프트를 다시 추출해야 함.
  오래된 템플릿은 에러 없이 조용히 SDK 기본 절차로 되돌아갈 수 있음.
- 템플릿은 harness별로 따로 필요함.
  다른 harness의 기본 프롬프트를 바탕으로 해야 하기 때문임.

## 4. SPEC 작성: `workflows/<이름>/__init__.py`

```python
from pathlib import Path

from ..spec import WorkflowSpec

HERE = Path(__file__).resolve().parent


def _scorer():
    # 채점기가 없으면 이 함수와 scorers 항목을 생략.
    # 함수 안에서 import해야 워크플로우를 안 쓰는 실행이 채점 코드를 로드하지 않음.
    from .reward.evaluator import Evaluation

    return Evaluation()


SPEC = WorkflowSpec(
    docs_dir=HERE / "docs",
    container_dir="/<이름>",                       # 절대 경로. 지시·system prompt 안의 경로와 일치
    entry_doc="core-workflow.md",                  # docs/ 안에 반드시 있어야 함
    instruction_file=HERE / "instruction.md",      # 없으면 None → task 텍스트 그대로
    system_prompt={"openhands-sdk": HERE / "system-prompt.j2"},
    scorers={"openhands-sdk": _scorer},            # 없으면 {} → resolve rate만 측정
    reward_signal="<이름>/compliance",              # 학습에서 reward에 합성할 signal (채점기가 있을 때)
)
```

- `system_prompt`와 `scorers`의 키는 harness 이름임(`openhands-sdk` 등).
  내용이 harness마다 다르기 때문임.
- 키가 없는 harness에서 이 워크플로우를 쓰면 경고만 남기고 진행함.
  - system prompt 없음 → harness 기본 프롬프트 유지.
  - 채점기 없음 → resolve rate만 측정.

## 5. 등록: `workflows/__init__.py`

```python
from . import aidlc_v4, <이름>
from .spec import WorkflowSpec

WORKFLOWS: dict[str, WorkflowSpec] = {
    "aidlc_v4": aidlc_v4.SPEC,
    "<이름>": <이름>.SPEC,
}
```

여기까지 하면 학습과 평가 양쪽에서 문서·지시·system prompt 주입과 resolve rate 측정이 동작함.

## 6. (선택) 준수율 채점: `workflows/<이름>/reward/`

채점기 공통 동작(verifier 감싸기, 실패 처리, signal 추가)은 `recipe/grpo/qwen3_5/workflow_scoring.py`의 `ComplianceEvaluation`이 맡음.
워크플로우가 쓸 것은 함수 두 개뿐임.

```python
from recipe.grpo.qwen3_5.workflow_scoring import ComplianceEvaluation


def collect(sandbox):
    """verifier가 돌기 전에 sandbox에서 산출물을 읽음. 실패하면 예외."""
    return parse(sandbox.exec("...", timeout=60, user="root"))


def score(task, episode, data) -> dict[str, float]:
    """{"<이름>/...": [0, 1] 값}. SPEC.reward_signal 키를 반드시 포함."""
    return {"<이름>/compliance": ..., "<이름>/stage1": ...}


class Evaluation(ComplianceEvaluation):
    def __init__(self):
        super().__init__(collect, score, "<이름>")
```

규칙:

- `collect`는 verifier 전에 호출됨.
  verifier가 테스트 패치 적용·`git checkout` 등으로 sandbox를 바꾸기 전 상태를 읽기 위함임.
- `sandbox.exec`의 텍스트 출력을 거치므로 파일 내용은 base64 등으로 감싸 옮기는 편이 안전함(AI-DLC가 그렇게 함).
- signal 이름은 `<이름>/` 접두어를 씀.
  학습 로그와 `rllm eval` 결과의 `signal_averages`에 이 이름으로 나옴.
- `collect`나 `score`가 예외를 내면 경고를 남기고 verifier 결과만 반환함.
  즉 signal이 빠질 뿐 잘못된 점수가 들어가지는 않음.
- 에이전트 도구 호출을 해석해야 하면 AI-DLC 구현을 참고함.
  - `workflows/aidlc_v4/reward/episode.py`: episode를 step 단위 도구 호출 목록으로 바꿈.
  - episode를 만든 harness(trajectory 이름)에 맞는 해석기(front end)를 고르고, 해석기가 없는 harness면 거부함.

## 7. 사용

학습 (`recipe/grpo/qwen3_5/config/config.yaml`의 `recipe.workflow`):

```bash
bash recipe/grpo/qwen3_5/train_verl.sh variant=openhands_9b recipe.workflow.name=<이름>
# 준수율을 reward에 합성
... recipe.workflow.compliance_reward.enable=true recipe.workflow.compliance_reward.mode=mul
```

- 자주 쓰면 `config/variant/openhands_9b_<이름>.yaml`에 `recipe: {workflow: {name: <이름>}}`를 넣어 둠.
- `compliance_reward` 합성 방식:
  - `mul`: reward = verifier × 준수율. 못 푼 rollout은 0.
  - `add`: reward = verifier + lam × 준수율. lam 기본 0.2.
  - 턴 예산을 다 쓴 rollout은 그 뒤에 `budget_reward_scale`을 곱함.
- 워크플로우가 없는데(`name: null`) `compliance_reward`가 켜져 있으면 경고 후 verifier reward만 씀.
- 워크플로우는 있는데 해당 harness용 채점기가 없는 상태에서 켜면 학습 시작 시 멈춤.

평가:

```bash
rllm eval <dataset> --split test \
  --agent recipe.grpo.qwen3_5.workflow_harness:OpenHandsSdkWorkflow \
  --agent-kwargs workflow=<이름>,step_limit=100,enable_thinking=false,instruction_position=prefix \
  --agent-image auto --sandbox-backend docker --hide-git-history
```

- repo root에서 실행해야 `recipe.grpo.qwen3_5`가 import됨.
- `workflow=none`이면 같은 harness로 워크플로우 없이 돌아 baseline 비교에 씀.
- 학습과 평가가 같은 채점기를 쓰므로 준수율 signal의 정의가 동일함.

### 여러 워크플로우 섞기

`name`에 리스트를 주면 task마다 그중 하나로 실행됨.
`none`을 넣으면 워크플로우 없는 plain harness도 섞임.

```bash
bash recipe/grpo/qwen3_5/train_verl.sh variant=openhands_9b_aidlc_swegym_v2 \
  'recipe.workflow.name=[none,aidlc_v4,speckit_bug]' \
  recipe.workflow.seed=0 recipe.workflow.val_name=aidlc_v4
```

- 배정 방식
  - 리스트 위에서 균등하게, task마다 독립적으로 뽑음.
  - 뽑기는 `(seed, task id)`의 hash라 한 run 안에서 고정됨.
    epoch이 바뀌어도, resume해도, 리스트 순서를 바꿔도 같은 task는 같은 워크플로우를 받음.
  - 한 task의 rollout은 모두 같은 워크플로우이므로, GRPO 그룹 안에서는 같은 워크플로우끼리만 비교됨.
    한 배치에는 여러 워크플로우가 섞임.
  - 비율은 정확히 맞추지 않음.
    3개를 3000개 task에 배정하는 테스트에서 워크플로우마다 800~1200개 범위.
  - 학습 시작 로그(`workflow mix, train tasks: ...`)에 실제 배정 수가 나옴.
- `val_name`
  - 검증 task 전체를 한 워크플로우로 고정함.
  - `name` 리스트에 없어도 됨(학습에는 섞지 않고 검증에만 쓰는 경우).
  - `null`이면 검증 task도 학습 task와 같은 방식으로 나뉨.
- 동작 원리
  - engine은 harness 객체 하나를 모든 rollout이 동시에 공유함.
    그래서 rollout마다 harness의 워크플로우 속성을 바꾸는 방식은 쓸 수 없음.
  - 대신 워크플로우마다 harness 복사본을 하나씩 미리 만들고, rollout은 task가 배정된 복사본에 통째로 넘김.
  - 복사본 하나하나는 워크플로우 하나짜리 harness와 같음.
    문서 업로드·지시·system prompt·산출물 수집 코드가 그대로 쓰임.
- 기록
  - episode마다 `workflow/<이름>/resolved`(해결 여부, 0 또는 1)가 붙음.
    episode 지표는 그 key가 있는 episode끼리만 평균하므로, 학습 로그와 `rllm eval`의 `signal_averages`에서 워크플로우별 해결률로 읽힘.
  - `episode.artifacts["workflow"]`에는 그 rollout이 실제로 따른 워크플로우 이름과 fingerprint가 남음.
- agent image
  - task를 보기 전에 정해지므로 run 전체가 하나를 씀.
  - 섞은 워크플로우들의 `agent_image_extra`를 모두 합쳐 구움.
  - 예: `openspec_ff`를 섞으면 node와 openspec 파일이 모든 sandbox의 `/opt/rllm/agent/node`에 들어감.
    PATH에는 없고, `openspec` 명령은 `openspec_ff`의 setup script가 만들 때만 생김.
    따라서 다른 워크플로우 task에서는 명령이 보이지 않으며, `/opt/rllm/agent`를 직접 뒤져야만 발견됨.
  - 합친 image가 문제가 되는 경우: extra가 PATH나 agent venv를 바꾸거나, 두 워크플로우의 extra가 같은 경로에 다른 것을 설치하는 경우.
    그때는 task별 image가 필요하며, rllm core(hooks·warm queue·trainer·eval runner)가 task별 mount image를 받도록 고쳐야 함.
- 준수율 reward(`compliance_reward.enable=true`)
  - `none`을 뺀 모든 워크플로우에 채점기가 있어야 함.
    하나라도 없으면 학습 시작 시 멈춤.
    현재 채점기는 `aidlc_v4`에만 있음.
  - `none` task는 verifier reward만 받음.
  - 이 레시피의 RLOO는 그룹 표준편차로 나누지 않음(`norm_adv_by_std_in_grpo: false`).
    그래서 그룹의 advantage 크기가 reward 크기를 그대로 따라감.
    `mul`에서 준수율이 낮은 워크플로우(AI-DLC smoke 평균 0.0028)의 그룹은 gradient가 거의 0이 되어, 학습이 사실상 다른 워크플로우로 쏠림.
    섞는 첫 run은 verifier reward만으로 돌리는 편이 해석하기 쉬움.
- 데이터셋 프롬프트
  - `swegym293_aidlc`(`prepare_swegym.py --instruction aidlc`)는 SWE-Gym 프롬프트에서 6단계 절차만 뺀 것임.
    AI-DLC 전용 문구는 없어 다른 워크플로우와 섞어도 됨.
  - 다만 이 데이터셋에서 `none` task는 6단계 절차가 없는 프롬프트를 받음.
    그래서 원래 프롬프트(`swegym293`)로 돌린 기존 baseline과는 조건이 다름.

평가에서는 `--agent-kwargs`가 쉼표로 인자를 나누므로 `+`로 이음.

```bash
... --agent-kwargs workflow=none+aidlc_v4,workflow_seed=0,step_limit=100,instruction_position=prefix
```

## 8. 확인 방법

빠른 점검(sandbox·GPU 불필요):

```python
from recipe.grpo.qwen3_5.workflow_harness import OpenHandsSdkWorkflow

h = OpenHandsSdkWorkflow(workflow="<이름>", instruction_position="prefix")
print([p.name for p in h._doc_entries()], h._expected_doc_count())   # 업로드될 항목, .md 개수
print(h.compose_instruction("TASK TEXT"))                            # 지시가 붙은 사용자 메시지
print(h.system_prompt_file, type(h.evaluation_policy).__name__)      # 템플릿, 채점기
```

- 단위 테스트는 `recipe/grpo/qwen3_5/tests/test_workflow_harness.py`의 `wf2` fixture 방식(임시 디렉터리에 워크플로우를 만들어 등록)을 참고함.
- 실제 동작은 task 2~3개로 `rllm eval` smoke를 돌려 확인함.
  - sandbox 안 `<container_dir>`에 문서가 있는지.
  - 결과의 `signal_averages`에 `<이름>/*`가 나오는지.
  - `workflow=none` run과 system prompt·사용자 메시지가 다른지.

## 자동 검사

harness 생성 시점(sandbox 생성 전)에 다음을 확인함.

| 상황 | 결과 |
| --- | --- |
| 등록되지 않은 이름 | 에러 |
| `container_dir`이 절대 경로가 아님 | 에러 |
| `docs/` 없음 / 비어 있음 / 진입 문서 없음 | 에러 |
| 지시·system prompt 파일 없음 | 에러 |
| 지시·system prompt가 진입 문서 경로를 언급하지 않음 | 에러 |
| system prompt를 바꿀 수 없는 harness에 템플릿 지정 | 에러 |
| 해당 harness용 템플릿 없음 | 경고 (기본 프롬프트 유지) |
| 해당 harness용 채점기 없음 | 경고 (resolve rate만) |
| rollout 중 업로드된 `.md` 수 불일치 | rollout 중단 |
| 섞는 리스트에 같은 이름 중복 / 등록되지 않은 이름 | 에러 |
| task metadata가 이 harness에 없는 워크플로우를 지정 | 에러 |

## 주의점과 한계

- **`mul` 합성에서 준수율이 낮으면 해결해도 reward가 거의 0**임.
  - 학습 smoke(25턴, task 2개 × rollout 4개)에서 AI-DLC 준수율 평균이 0.0028에 그침.
  - verifier 기준 3/8 rollout이 해결했지만 합성 후 reward 평균은 0.0.
  - 턴 예산이 짧거나 초기 정책이 워크플로우를 거의 안 따를 때는 `add`나 verifier-only 학습부터 검토 필요.
- 경로 검사는 지시·system prompt에 진입 문서 경로 문자열이 있는지만 봄.
  다른 문서 경로의 오타까지는 잡지 못함.
- 경로 덮어쓰기나 layer 끄기(예: 지시 없이 system prompt만) 실행 옵션은 없음.
  필요하면 그 조합을 별도 워크플로우로 등록해야 함.
- 문서·지시·system prompt는 서로를 절대 경로로 가리키므로 한 디렉터리에서 함께 버전 관리함.
  실행 시점에 다른 곳에서 복사해 오면 셋이 어긋날 수 있음.
