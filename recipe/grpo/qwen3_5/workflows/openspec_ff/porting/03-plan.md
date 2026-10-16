# Plan: openspec_ff — explore extension  (upstream Fission-AI/OpenSpec@9111a76)

- **승인**: user 2026-10-15 (G4-19, G7-10 추가 결정 반영 2026-10-15)
- 범위: upstream explore 단계(`skills/openspec-explore/SKILL.md`)를 ff 앞에 추가하는 변경만. ff → apply → verify →
  archive는 기존 openspec_ff 그대로(`05-changes.md`). 근거 결정: `03-decisions.md` "Explore extension".
- 원문 링크는 `/gpfs/home/daink/2026-2_DFM/OpenSpec` checkout 기준.

## 수정한 내용

### 각 단계 수행 방식 변화 (explore)

| Before (upstream explore) | After (rllm) |
|---|---|
| 1. **사람**이 (선택) agent 앱 채팅창에 `/opsx:explore`를 입력하고, 바꿀 영역이나 문제를 말합니다([existing-projects:41-54](../../../../../../../OpenSpec/docs/existing-projects.md#L41-L54)).<br>2. **agent 앱**이 `openspec-explore` SKILL.md를 지침으로 불러옵니다.<br>3. agent가 `openspec list`·`list --specs`·`show`와 `config.yaml`로 현황을 보고, 코드를 읽고 읽기 전용 명령을 실행합니다.<br>  • 다이어그램과 선택지를 보여 주며 **사람에게 한 번에 하나씩 질문**합니다.<br>  • 코드는 쓰지 않습니다. change 문서는 **사람의 yes 뒤에만** 씁니다.<br>4. 정해진 끝이 없습니다. **사람**이 `/opsx:propose`를 입력하면 끝나고, 대화 내용이 proposal로 옮겨집니다. | 1. task 메시지(instruction + issue)가 탐색 주제입니다.<br>2. agent가 `core-workflow.md`를 읽고 **`/opsx/stages/00-explore.md`를 먼저** 엽니다.<br>3. agent가 현황 명령(`openspec list` 등)과 `config.yaml`을 보고, 코드를 읽고 검색합니다.<br>  • 실행은 **기존 코드·기존 테스트, issue 예시를 그대로**만 합니다. 직접 짠 코드(한 줄 `python -c` 포함)와 파일 쓰기는 하지 않습니다.<br>  • 사람만 답할 수 있는 질문은 **가정**으로 기록하고, 선택은 agent가 추천안과 대안으로 정합니다.<br>4. 문제와 바꿀 위치를 근거와 함께 말할 수 있으면, **"What We Figured Out" 요약**을 쓰고 같은 turn에 `01-ff.md`를 엽니다.<br>5. ff부터는 기존과 같습니다. ff는 요약을 근거로 proposal과 design을 씁니다. |

### 수정 사항

| # | 범주 | 내용 |
|---|---|---|
| 1 | **사람 피드백이 필요한 부분 삭제** | 쓰기 전 yes/no 질문과 "Want me to create a proposal?" 제안 삭제. 범위·의도 질문은 가정 기록으로, 사람의 선택은 agent의 추천안·대안 기록으로 대체 |
| 2 | **보고 후 멈춤 → 다음 단계로 진행** | `/openspec-propose` 안내 5곳을 "`01-ff.md`를 열고 계속"으로 변경. 구현 요청 거절 문장을 "구현은 이 세션의 ff·apply가 수행"으로 변경 |
| 3 | **이름·경로 고정** | explore 단계 문서 `00-explore.md`. explore는 change를 만들지 않으므로 change 이름은 기존대로 ff의 `issue` |
| 4 | **실행 환경 구성** | 해당 없음(CLI·이미지 그대로). smoke 전에 빈 spec 트리에서 `openspec list --specs`를 시험 |
| 5 | **agent 앱 전용 요소 삭제** | explore의 frontmatter, store 선택 문단 삭제 |
| 6 | **SWE task 조건에 맞춤** | 해당 없음(explore는 원래 파일을 쓰지 않음) |
| 7 | **절차 구조 변경** | ff 앞에 explore 단계 추가(선택 → 항상). 끝 조건: 요약의 문제·바꿀 위치를 근거와 함께 말할 수 있을 때. 요약은 항상 작성. capture 전환, "When a change exists", 구현 중 예시, 상황별 예시 4개 중 3개 삭제(해당 없음) |
| 8 | **환경 사실 명시** | config `context`의 checks 문장을 "From the ff action on, …"으로 변경 |
| 9 | **harness·데이터셋 설정** | `instruction.md`와 system prompt 절차 섹션에 explore를 첫 단계로 명시. build.py 금지어 검사에 `explore:48` 예외 |
| 10 | **범위·방식 결정** | "코드 작성"의 경계: 기존 코드·테스트와 issue 예시를 그대로 실행하는 것만 허용, 직접 짠 코드와 파일 쓰기 금지. explore는 아무것도 쓰지 않음 |
| 11 | **원문 유지** | "NEVER write code"(`:14`, `:345`), 사실 확인 문장 `:48`, 현황 명령과 config 읽기(`:122-146`), ff의 "reuse findings … inspect more only as needed" 문장 |

**적용 위치**
- **단계 문서 편집**: `build.py`가 upstream `openspec-explore/SKILL.md`를 `00-explore.md`로 변환할 때 태그 편집으로 적용(약 25건: 질문·쓰기 확인·예시 문장마다 따로 고침). 범주 1, 2, 5, 7, 10
- **환경 파일**: `sandbox/openspec-config.yaml` 1줄. 범주 8
- **새로 작성**: `core-workflow.md`의 행동 표 행·흐름 줄·읽기/실행 규칙, `instruction.md`, system prompt 절차 섹션. 범주 7, 9, 10
- **build·test**: `build.py`의 `SOURCES`·`STAGE_DOCS`·`FORBIDDEN` 예외, 테스트, README, `__init__.py` docstring

## agent 행동 변화

| # | 단계 | upstream 원래 행동 | 지금 행동 | 바꾼 이유 | 원문으로 되돌리면 |
|---|---|---|---|---|---|
| 1 | explore | 선택 단계. 사람이 `/opsx:explore`를 부를 때만 실행 ([existing-projects:19](../../../../../../../OpenSpec/docs/existing-projects.md#L19) "optional") | **새 행동 추가**: 매 rollout에서 ff 전에 항상 실행 | 재현 전에 design을 확정하는 계획 고착을 줄이려고 사용자가 순서를 정함 (G3-2) | 가능 (explore 없는 기존 openspec_ff) |
| 2 | explore | "run read-only commands or tools … NEVER write code" ([explore:14](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L14)). 직접 짠 snippet 실행 여부는 원문상 불명확 | **원래 행동 삭제**(불명확한 부분): 기존 코드·테스트와 issue 예시를 그대로 실행하는 것만 허용, 직접 짠 코드 실행 금지 | "NEVER write code"를 문자 그대로 적용 (G9-5) | 가능 (snippet 허용 시 재현은 늘지만 원문 규칙과 충돌) |
| 3 | explore | 끝이 없음. "There's no required ending" ([explore:314-321](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L314-L321)), 사람의 명령으로 끝남 | **새 행동 추가**: 요약의 문제·바꿀 위치를 근거와 함께 말할 수 있으면 끝내고 ff로 감 | 끝낼 사람이 없음 (G8-6) | 불가 (무인 실행에 끝이 없음) |
| 4 | explore | 결정은 대화에 남김, "Track decisions in the conversation, not in files" ([explore:53](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L53)). 요약은 선택 ([:323-339](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L323-L339)) | **새 행동 추가**: "What We Figured Out" 요약을 항상 작성(문제, 동작 방식, 바꿀 위치·대안, 가정, 남은 질문 + 근거). ff 문서를 여는 turn에 둠 | 확인 가능한 기록, ff의 근거 (G2-12) | 가능하지만 근거가 대화에 흩어짐 |
| 5 | explore | yes를 받으면 change 문서 작성, capture 요청 시 change 생성 ([explore:14](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L14), [:150-162](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L150-L162)) | **원래 행동 삭제**: 아무것도 쓰지 않음. change는 ff가 만듦 | 답할 사람이 없고, ff의 `new change`와 충돌 (G4-13) | 가능하지만 ff 2단계 변경 필요 (`later.md`) |
| 6 | explore | 추천안을 말하고 사람이 고름, "The user decides" ([explore:52](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L52), [:195](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L195)). spike는 사람에게 제안 | **새 행동 추가**: agent가 추천안·대안·이유를 요약에 쓰고, ff의 design.md Decisions에 기록. spike는 ff 조사에서 풀 질문으로 넘김 | 고를 사람이 없음 (G4-15) | 불가 (선택할 사람 없음) |
| 7 | ff | explore 대화를 보고 proposal을 씀, "the AI carries the context from your conversation into the artifacts" ([docs/explore.md:91](../../../../../../../OpenSpec/docs/explore.md#L91)) | **새 행동 유도**: 요약을 근거로 proposal Why·design Context·Decisions를 씀. ff 문서는 원문 그대로 | explore 결과를 계획에 반영 (G2-12, G2-13) | 가능 |

**표에서 뺀 것**: 입력 = issue(G1-4), "계획 세우기" 예시의 범위 질문 → 근거에서 끌어낸 가정과 틀렸을 때의 대안(G4-19), "change를 손으로 만들지 마라" guardrail 삭제(G7-10), propose 안내 → ff 문서 열기(G2-10), 구현 요청 문장(G4-16), 질문 → 가정 기록(G4-14), 메시지는 tool call과 같은 turn에(G2-11), frontmatter·store 삭제(G7-7, G7-8), capture·기존 change·예시 3개 삭제(G4-17, G4-18), 현황 명령 유지(G7-9), config 문장(G10-9).

**smoke에서 반드시 확인할 것** (새 행동 추가 행 1, 3, 4, 6): explore가 매번 실행되는지, explore 중 파일 쓰기와 직접 짠 코드가 0인지, 끝 조건에 맞춰 요약을 쓰고 ff로 가는지, 요약의 추천안이 design Decisions에 기록되는지. 함께 측정: explore와 ff의 step 수, ff 조사량(G2-13), 계획 고착 사례 수.
