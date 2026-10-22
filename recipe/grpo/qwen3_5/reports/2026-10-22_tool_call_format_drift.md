# Tool call 형식 표류: 분석과 대응

작성 2026-10-22. 대상 run: `qwen3_5-9b-openhands-sdk-speckit-openspec-agentos-think-reward-swegym293` / `20261019_050357`
(variant `openhands_9b_speckit_openspec_agentos_swegym_reward`, Qwen3.5-9B, thinking on, 250턴, 262144 컨텍스트, 27 step).

## 요약

- 학습이 진행되면서 모델이 내는 tool call 중 **함수 이름이 비정상인 비율이 1.6%(step 1) → 17.0%(step 27)** 로 늘었다.
  거의 전부 `<function=terminal=command>` (인자 없음) 한 형태다.
- 학습 중에는 이 호출이 **비용을 치르지 않았다.** gateway renderer가 이름을 그대로 받아 SDK로 넘기고, SDK는 검증 오류를
  돌려주며, 모델은 다음 턴에 제대로 다시 부른다. 턴 하나 낭비일 뿐 verifier 결과도 compliance도 바뀌지 않고, KL 항이 0이라
  base 분포로 돌아오는 힘도 없었다.
- 평가에서 `hermes` 계열 파서로 vLLM을 띄우면 같은 호출이 **텍스트로 처리되어 SDK가 도구 호출이 없다고 보고 에피소드를
  끝낸다.** 학습에서는 재시도로 회복되던 실수가 평가에서는 실패가 된다. 이전 run에서 문제가 없었던 이유는 경로가 달라서가
  아니라 표류가 시작되는 길이까지 가지 않았거나(10-18 run, 12 step), 출발 비율이 0이었기(9월 no-think run) 때문이다.
- **지금 체크포인트**(step 27 HF 변환본)는 학습과 같은 `qwen3_xml` 파서로 평가하면 된다. **다음 학습**은 형식 오류에 비용을
  만드는 수정(gateway 이름 검증, 보상 형식 항, loss masking 중 택일 이상)과 작은 KL 항을 넣고 다시 돌려야 한다.

## 증상

### 학습 중 비정상 함수 이름 비율

SDK가 노출하는 도구는 `terminal`, `file_editor`, `think`, `finish`, `task_tracker`, `browser`다. 그 외 이름은 전부 비정상으로 셌다.

| step | tool call 수 | 비정상 | 비율 | 주된 이름 |
| --- | --- | --- | --- | --- |
| 1 | 10,043 | 159 | 1.6% | `str_replace` 152, `terminal=command` 5 |
| 3 | 8,230 | 71 | 0.9% | `str_replace` 58, `terminal=command` 7 |
| 6 | 9,498 | 88 | 0.9% | `str_replace` 69, `terminal=command` 12 |
| 9 | 8,070 | 91 | 1.1% | `str_replace` 47, `terminal=command` 24, `terminal=terminal` 19 |
| 12 | 8,585 | 217 | 2.5% | `terminal=command` 121, `terminal=terminal` 75 |
| 15 | 8,379 | 372 | 4.4% | `terminal=command` 339 |
| 18 | 9,018 | 924 | 10.2% | `terminal=command` 879 |
| 21 | 8,528 | 860 | 10.1% | `terminal=command` 833 |
| 24 | 8,803 | 1,185 | 13.5% | `terminal=command` 1,159 |
| 27 | 9,161 | 1,554 | 17.0% | `terminal=command` 1,501 |

- step 1의 `str_replace`는 file_editor의 `command` 값을 함수 이름 자리에 쓴 base 모델의 실수이고, 학습 중 줄어든다(152 → 29).
- `terminal=command`는 step 12~18 사이에 급증하며, 세 워크플로에 고루 퍼진다. step 27 기준 speckit_bug 16.4%(64 에피소드 중 54개에
  등장), openspec_ff 18.7%, agentos_v2 11.8%.
- 비정상 호출에 대한 SDK 응답은 1,501건 전부 동일하다:
  `Error validating tool 'terminal=command': 1 validation error for TerminalAction / command Field required`.
  모델은 다음 턴에 올바른 `terminal` 호출로 이어간다.

### 다른 run과의 비교

| run | 설정 | step 1 | 마지막 step |
| --- | --- | --- | --- |
| `20260923_055723` (`openhands_9b_swegym`) | no-think, 80턴, 27 step | 0.0% | 0.0% (step 27) |
| `20261018_082600` (speckit + openspec) | think on, 250턴, 12 step에서 중단 | 1.1% | 0.3% (step 12, 감소 중) |
| `20261019_050357` (speckit + openspec + agentos) | think on, 250턴, 27 step | 1.6% | 17.0% (step 27) |

세 run 모두 같은 gateway 경로(cumulative token mode)였다.

### 평가에서의 현상

- `hermes`는 `<tool_call>{"name": ..., "arguments": ...}</tool_call>` JSON만 파싱한다. `hermes_lenient2`(팀 평가용 vLLM docker의
  커스텀 파서)는 빠진 `<tool_call>` 래퍼는 복구하지만 빠진/비정상 `<function=`은 복구하지 못한다(speckit_sdd porting/02-gaps.md G10-6).
- 따라서 `<function=terminal=command>` 턴은 도구 호출 없는 응답으로 떨어지고, openhands-sdk는 "assistant가 도구 없이 답했다"로
  보고 에피소드를 종료한다. 학습에서 17%의 호출이 이 형태였으므로 상당수 에피소드가 중간에 끊긴다.
- `qwen3_xml`(vLLM)은 `<function=NAME>`의 NAME을 그대로 받아 SDK에 넘기므로 학습 때와 같은 "오류 → 재시도" 경로가 된다.

## 학습 경로: 어떤 파서가 어디서 쓰이는가

학습 데이터는 파서를 거치지 않지만, agent는 거친다. 경로가 둘로 나뉜다.

1. **첫 턴**: openhands-sdk → gateway → vLLM `/v1/chat/completions`. 여기서만 vLLM의 `reasoning_parser qwen3`,
   `tool_call_parser qwen3_xml`이 돈다 (`config/verl_trainer.yaml`).
2. **둘째 턴부터** (`rllm.gateway.cumulative_token_mode: true`): gateway가 이전 턴의 토큰 id에 새 관찰을 이어 붙여 프롬프트를
   직접 만들고 vLLM `/v1/completions`를 호출한다. 돌아오는 것은 `<think>…</think><tool_call><function=…>` 마크업이 그대로 든
   생 텍스트와 토큰 id다. gateway는 이 텍스트를 **자체 renderer(tinker_cookbook `Qwen3_5Renderer`)** 로 파싱해 SDK에
   `tool_calls`로 넘긴다 (`rllm-model-gateway/src/rllm_model_gateway/proxy.py` `_completion_to_chat_message`). vLLM 파서는 관여하지 않는다.
3. **학습**은 gateway가 모아 둔 토큰 id(프롬프트 + 샘플링된 completion)를 그대로 쓴다. 파서 출력은 agent의 다음 행동을 정할 뿐,
   loss에 들어가는 토큰은 모델이 뱉은 원본이다.

그러므로 "학습 중 어떤 형식이 살아남는가"는 vLLM 파서가 아니라 **tinker renderer가 무엇을 받아들이는가**로 정해진다.
renderer의 함수 이름 정규식은 `<function=(?P<name>[^>\n]+)>`라 `terminal=command`를 함수 이름으로 그대로 받고
(`tinker_cookbook/renderers/qwen3_5.py`), gateway의 `_forwardable`은 이름이 도구 목록에 있는지 보지 않는다.

```
모델 토큰 ──► gateway(renderer 파싱) ──► SDK(검증 오류 → 재시도)      [학습: 비용 0]
       └──► 학습 배치(토큰 원본 그대로, advantage는 trajectory 단위)
모델 토큰 ──► vLLM hermes 파서(텍스트로 처리) ──► SDK 종료           [평가: 보상 0]
```

## 원인 분석

**메커니즘**

1. think on인 base 모델이 1~2% 비율로 `<function=terminal=command>` 같은 형식을 낸다. 생각 블록 뒤에 도구 호출 마크업을
   이어 쓰는 자리가 no-think보다 불안정하다 (no-think run은 step 1부터 0건).
2. 그 턴이 아무 벌을 받지 않는다. renderer 통과 → SDK 검증 오류 → 재시도. verifier 결과도 compliance도 변하지 않는다.
3. GRPO는 trajectory 전체 토큰을 하나의 advantage로 민다. 비정상 호출 턴은 좋은 rollout에 섞이면 함께 강화되고 나쁜 rollout에
   섞이면 함께 약화된다. 보상과 상관이 없으니 평균적으로는 중립이지만 억제력도 없다.
4. `rllm.algorithm.kl_beta: 0`이라 reference 정책이 없다. 중립적인 방향으로 정책이 흘러도 되돌릴 힘이 없고, 한 번 흘러간 쪽에서
   더 많이 샘플링되면 다시 강화되는 되먹임이 생긴다. 1.6% → 17%의 단조 증가는 이 되먹임으로 설명된다.

**배제한 가설**

| 가설 | 확인 | 판정 |
| --- | --- | --- |
| cumulative token mode가 깨진 텍스트를 보존해서 학습됨 | 어떤 모드든 샘플링된 토큰은 그대로 학습된다. 같은 모드의 9월 run은 0%, 10-18 run은 감소 | 아님 |
| agentos_v2 문서/프롬프트가 형식을 유도 | 세 워크플로의 docs와 system-prompt.j2에 `<function=`·`<parameter=` 마크업 없음. 비정상 비율은 세 워크플로에 고루 분포 | 아님 |
| 비정상 호출이 보상에 유리해서 선택됨 | step 27 각 GRPO group 안에서 비정상 비율이 중앙값보다 높은 rollout(61) vs 낮은 rollout(67): 해결률 0.85 vs 0.82, compliance 0.72 vs 0.79, 턴 82 vs 62 | 아님 (선택이 아니라 표류) |
| thinking on 단독 효과 | think-on base가 1.1~1.6%로 시작하는 것은 확인. 다만 9월 run은 no-think와 80턴 두 조건이 달라 단독 효과로 단정 불가 | 부분 |

**부수 관찰**: 학습 중 SDK가 본 assistant `content`의 99%가 사고 텍스트 + `</think>`를 그대로 담고 있었고 `reasoning_content`는
비어 있었다. renderer가 프롬프트에 미리 들어간 `<think>\n`을 복원하지 못한 것으로, 학습 토큰에는 영향이 없지만 vLLM 평가에서는
reasoning이 분리되어 나오므로 SDK가 보는 메시지 모양이 학습 때와 다르다. 학습·평가 불일치 목록에 올려 둔다.

## 대응 방안

세 층이 필요하다. 형식 오류에 **비용**을 만들고, 표류를 **억제**하고, 다시 생기면 **일찍 보이게** 하는 것. 비용 층은 아래 1~3 중 하나 이상.

| # | 방안 | 어디를 바꾸나 | 효과 | 비용·부작용 |
| --- | --- | --- | --- | --- |
| 1 | **gateway 이름 검증(drop)** | `proxy.py` `_forwardable`: `tc.name`이 요청의 `tools` 목록에 없거나 `=`를 포함하면 버림 | 그 턴이 도구 호출 없는 응답이 되어 SDK가 종료 → 미해결 → 보상 0. 평가(hermes)와 같은 조건이 되어 학습·평가 불일치가 사라진다. 가장 직접적인 벌 | 초반 1~2% 호출이 걸려 step 1 해결률이 조금 내려감. 재시도로 회복하는 행동은 학습되지 않음 |
| 2 | **보상 형식 항** | `train.py` grouping hook: 에피소드의 tool call 중 도구 목록 밖 이름 비율 $m_i$를 세어 $r_i \leftarrow r_i(1-m_i)$ 또는 $r_i - \lambda m_i$ | 재시도 회복 행동은 유지하면서 형식만 깎는다. 지금 보상 구조(verifier × compliance × budget)에 인자 하나 추가라 변경이 작다 | 벌의 세기를 $\lambda$로 조절해야 함. 비정상 호출을 많이 낸 rollout 전체가 깎이므로 토큰 단위 정밀도는 없음 |
| 3 | **loss masking** | `rllm/trainer/verl/transform.py`의 `response_mask`(모델 출력 토큰만 1, 관찰 토큰 0)에 더해, renderer가 비정상으로 판정한 turn의 응답 토큰(또는 `<tool_call>…</tool_call>` 구간)을 loss에서 제외. 판정 플래그는 gateway가 trace에 기록 | 비정상 토큰이 **강화되지 않는다**(좋은 rollout에 섞여도 올라가지 않음). 표류의 되먹임 고리를 끊는 가장 보수적인 방법. 모델 행동이나 평가 조건은 바뀌지 않음 | **벌도 없다.** 비정상 토큰의 확률을 적극적으로 낮추지 않으므로 이미 17%인 체크포인트를 고치지는 못하고, base에서 시작할 때 "자라지 않게" 하는 용도. 그 턴의 올바른 부분(생각 등)까지 마스킹하면 신호 손실이 있으므로 tool_call 구간만 마스킹하는 쪽이 낫다. 1·2와 병행 가능 |
| 4 | **KL 항** | `rllm.algorithm.kl_beta` 0.01~0.05 | base 분포로 되돌리는 힘이 생겨 보상 중립 방향의 표류를 억제 | reference worker 생성: step당 forward 한 번(old_log_probs와 비슷한 6~7분)과 메모리 추가. 262K + SP2 피크 94.5 GB 위에 얹히므로 smoke 1 step으로 확인 필요 |
| 5 | **모니터링 지표** | 에피소드 신호 `tool_call/malformed_rate` → wandb `batch/tool_call/malformed_rate` | 1~3에서 어차피 세는 값. step 12 전후 2%를 넘으면 중단하는 기준 | 없음 |
| 6 | **평가 파서 정렬** | 평가용 vLLM을 `--tool-call-parser qwen3_xml --reasoning-parser qwen3 --enable-auto-tool-choice`로 | 지금 체크포인트가 학습 때 측정된 성능대로 평가됨 | 모델의 형식 오류를 감춰 주므로 1~3 없이는 근본 해결이 아님 |

**loss masking에 대해 조금 더**: GRPO loss는 응답 토큰별 log-prob에 trajectory advantage를 곱해 합친다(`seq-mean-token-sum`).
관찰(도구 출력) 토큰은 모델이 생성한 것이 아니라 이미 마스킹되어 있는데, 같은 마스크에 "모델이 생성했지만 형식이 깨진 구간"을 더하는
것이 3번이다. 효과는 비대칭이다. 좋은 rollout 안의 깨진 구간이 올라가는 것은 막지만, 나쁜 rollout 안의 깨진 구간이 내려가는 것도
막는다. 표류가 보상 중립적 방향이라면(이번 사례) 되먹임의 상승 쪽만 끊어도 충분하고, 1번이나 2번과 함께 쓰면 "올라가지 않으면서
내려가는" 조합이 된다. 단독으로는 이미 표류한 체크포인트를 되돌리지 못한다.

`entropy_coeff`를 올리는 것은 권하지 않는다. 형식 다양성을 키우는 쪽이라 반대 효과가 날 수 있다.

## 권고와 재학습 계획

- **지금 체크포인트 평가**: 6번. `/vast-ib/MMI/home/kyuminkim/rllm-artifacts/hf/qwen3_5-9b-openhands-sdk-speckit-openspec-agentos-think-reward-swegym293-step27`을
  `qwen3_xml`로 띄운다. hermes 계열 결과는 이 체크포인트에는 쓸 수 없다.
- **다음 학습**: 1번(gateway drop) + 5번(지표)을 넣고, 4번(KL)은 smoke 1 step으로 메모리를 확인한 뒤 결정. 3번(loss masking)은
  1번과 병행하면 안전장치가 되지만, 1번만으로 비용이 생기므로 필수는 아니다. 2번은 1번 대신 "재시도 행동을 유지하고 싶을 때"의 대안.
- **이어서 학습하기는 어렵다.** agentos run은 step 23~27만 남아 있고(keep 5) 전부 10% 이상이다. 10-18 run의 step 12(0.3%)는 남아
  있지만 두 워크플로 배정이라 세 워크플로 run의 연속이 아니다. base에서 다시 시작하는 것이 맞다(27 step 약 35시간).
- thinking on은 유지해도 된다. 씨앗이 1~2%여도 비용이 생기면 자라지 않는다. no-think는 씨앗 자체가 0이라 더 안전하지만 다른
  실험 조건이 된다.

## 부록

**데이터 출처**: 에피소드 JSON `$RLLM_ARTIFACT_DIR/episodes/qwen3_5-swe-grpo/<experiment>/<run_id>/episodes/train_step_N_epoch_E/*.json`의
`trajectories[].steps[].chat_completions[-1].tool_calls[].function.name`과, 같은 step의 다음 요청에 든 `role: tool` 메시지(SDK 응답).

**재현(비정상 비율, 로그인 노드 python3로 충분)**:

```python
import json, glob, collections
OK = {"terminal", "file_editor", "think", "finish", "task_tracker", "browser"}
E = ".../episodes"
for st in (1, 9, 18, 27):
    calls = 0; bad = collections.Counter()
    for f in glob.glob(f"{E}/train_step_{st}_*/*.json"):
        if f.endswith("batch_summary.json"): continue
        for t in json.load(open(f))["trajectories"]:
            for s in t["steps"]:
                for tc in ((s.get("chat_completions") or [{}])[-1] or {}).get("tool_calls") or []:
                    n = (tc.get("function") or {}).get("name"); calls += 1
                    if n not in OK: bad[n] += 1
    print(st, calls, sum(bad.values()), bad.most_common(3))
```

**관련 코드**

| 역할 | 위치 |
| --- | --- |
| vLLM 파서 설정(첫 턴) | `recipe/grpo/qwen3_5/config/verl_trainer.yaml` `engine_kwargs.vllm` |
| cumulative turn → renderer 파싱 → SDK | `rllm-model-gateway/src/rllm_model_gateway/proxy.py` `_handle_cumulative_turn`, `_completion_to_chat_message`, `_forwardable` |
| 함수 이름 정규식 | `tinker_cookbook/renderers/qwen3_5.py` `_FUNCTION_BLOCK_RE` |
| 보상 합성(grouping hook) | `recipe/grpo/qwen3_5/train.py` `make_budget_scaled_grouping_hook` |
| 토큰 마스크(`response_mask`: 모델 출력 토큰만 1, 관찰 토큰 0) | `rllm/trainer/verl/transform.py` |
| KL 설정 | `recipe/grpo/qwen3_5/config/rllm_grpo.yaml` `rllm.algorithm.kl_beta` |
| 이전 관찰(G10-6, hermes_lenient2) | `recipe/grpo/qwen3_5/workflows/speckit_sdd/porting/02-gaps.md` |
