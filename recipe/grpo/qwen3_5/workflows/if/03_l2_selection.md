# 03. 역할 배정과 L2 선정 (설계 문서 9.1절 4단계 결과)

> 기준: `02_train_eval_comparison.md` 5절의 결정(2026-10-23)
> 작성: 2026-10-23

## 1. 평가 층 정의 (확정)

| 층 | 의미 | AI-DLC에서 해당하는 규칙 | 해석 |
|---|---|---|---|
| **L1** | 학습에 있는 템플릿을 처음 보는 workflow 문서에 적용 (seen) | 02에서 "같음 / 가까운 변형" | cross-workflow 전이 |
| **L1-충돌** | 학습 규칙·문서와 반대 방향의 지시 | 02에서 "충돌" | 학습 습관이 아니라 현재 지시를 따르는가. 학습 후 하락하면 습관 과적합의 신호 |
| **L2-먼** | 학습 rubric과 문서 어디에도 없는 템플릿 (순수 unseen) | 02에서 "먼 변형" | 처음 보는 지시 형태로의 일반화 |
| **L2-중간** | 학습 보상에는 없지만, 학습 템플릿 구조를 확장했거나(구조 확장형) 학습 문서에 지시가 노출된(문서 노출형) 템플릿 | 02에서 "중간" | 일반화의 약한 근거. 문서 노출형은 IFBench 기준으로는 seen에 가깝다. L2-먼과 따로 보고 |
| **L3** | IFBench | — | SDLC 밖 정밀 지시 따르기로의 전이 |

### 1.1 평가 문항의 요구 수준 (결정 2026-10-23)

- **평가 점수(L1, L1-충돌, L2-먼, L2-중간)는 must 항목만으로 계산한다.** should는 점수에 넣지 않고 진단용으로 따로 기록한다.
- **평가 문항의 must/should는 AI-DLC 원문을 보고 직접 검토한다.** 생성기가 붙인 구분을 그대로 쓰지 않는다. 예를 들어 T-TR1b(Step→R 대응)는 생성기에서 should지만, CW "Quote identifiers … verbatim, never renumbered"가 must 근거가 될 수 있다. 검토 결과에 따라 아래 층 배정이 바뀔 수 있다(6단계에서 수행).
- 학습 보상의 should 가중치(0.25)는 이 결정과 별개로 유지한다.

## 2. 템플릿별 역할

### 2.1 AI-DLC 평가 문항의 층 배정

| 층 | 템플릿 / 규칙 (02의 #) | 측정 수단 (현재) |
|---|---|---|
| **L2-먼** | T-FM5 frontmatter 키 고정 (G10) | v4 점수(gate), gen |
| | T-TR1b 실행 기록의 Step→R 대응 = 계획 (Stg4b) | gen(should 1) |
| | T-FM6 Step 블록별 필드 (Stg3a) — 학습 보상에서 AOS `blocks` 제외로 전환 | v4 점수, gen |
| | 목록 = 실제 (equal) (Stg4e, Stg5i) — 학습 보상에서 SKB 파일 목록 `cross_ref` 제외로 전환 | gen |
| **L2-중간** | T-TR1 요구사항 ID 대응: 태그, Coverage, Exercises (Stg3b, Stg3c, G12) | gen |
| | T-TR2 계획 이행: 계획 경로 사용, 기록한 빌드 명령 실행 (Stg4a, Stg5b) | gen |
| | T-AW6 baseline과 같은 범위 재실행 (Stg5d) | gen |
| | 기록 경로의 재현 스크립트 실행 (Stg5c) | v4 기록, gen |
| | G15 진전 없을 때 종료하고 미해결 기록 | v4 기록(반복 명령 수)만. 판정 기준 정의 필요 |
| **L1-충돌** | T-AW4 재현 스크립트 지연 실행 (Stg4c) — vs SKB 즉시 실행 | v4 기록, gen |
| | T-RD6 보이는 산출물 재독 금지 (G11, Stg5a) — vs 학습 T-RD4, OSF "항상 다시 읽기" | **없음 → 검증 함수 신규 (3절)** |
| | T-PR5 전체 스위트 금지 (Stg5e) — vs AOS 검증 단계 전체 스위트, SKB "broader regression suite" | gen |
| | G5 이전 단계 복귀 금지 — vs OSF "back to ff", SKB 라운드 | gen(order) |
| | G8 이전 단계 산출물 재작성 금지 — vs OSF "설계 문제 시 이전 산출물 직접 수정" (SKB는 같은 방향이라 L1 성격도 있음) | v4(rewrites), gen |
| | T-PR3 설치 금지 (G14) — vs system prompt "설치하라" | gen |
| | Stg1b 저장소를 넓게 훑지 않기 — vs AOS 검색 요구 | 없음. 판정 기준이 모호해 보류 |
| **L1** | 나머지 (문서 읽기, 순서, 산출물 쓰기, 테스트 파일 금지, baseline, 기록 사실성, 골격, 자리표시자 등) | v4, gen |

### 2.2 학습 쪽 처리

- **학습 보상에서 뺄 것 (결정 2026-10-23):** L2-중간 중 문서를 고치지 않고 보상 항목만 빼면 L2-먼이 되는 두 가지를 뺀다. 5단계에서 rubric에 반영한다.
  - AOS `agentos_v2.blocks` 2개 → T-FM6(Step 블록별 필드)이 L2-먼이 된다.
  - SKB `cross_ref`(fix·fix_2·fix_3의 "쓴 파일 ⊆ 보고서 Changes 목록") 3개 → T-RF3(목록 = 실제)이 L2-먼이 된다. 같은 기술의 T-RF1(기록한 명령·결과 = 실제)은 학습에 남는다.
  - 9.0.1(workflow 고유 템플릿 유지) 원칙의 예외다. 빠지는 항목은 5개이고, 해당 workflow의 다른 고유 템플릿은 남는다.
- **유지하되 나중에 제외를 검토할 것:** T-TR1에 대응하는 OSF `openspec.capabilities`(proposal ↔ delta spec 대응). 이것을 빼면 학습 보상에서 S8(산출물 간 추적) 기술 전체가 빠져 leave-one-category-out이 된다. 첫 학습 결과를 보고 결정한다(설계 문서 Future work 10.2). 그때까지 T-TR1은 "중간"으로 남는다.
- **나머지 L2 템플릿은 이미 학습 rubric에 없다.** T-TR2와 T-AW6은 학습 문서(SKB)에 노출돼 있지만, 공개 방법론 문서는 고치지 않기로 해서 "중간"으로 남긴다.
- **충돌의 원인인 학습 workflow 고유 행동은 유지한다(결정 3).**
  - SKB `check_scripts(before_change, run)`: 수정 전 즉시 실행
  - OSF ff "항상 디스크에서 다시 읽기"와 학습 T-RD4(이전 산출물 읽기)
  - AOS `verify(whole_suite)`
  - OSF "apply에서 ff로 복귀 가능"
  - SKB fix/test 라운드
- **학습 workflow 고유 템플릿은 학습 다양성으로 유지한다(9.0.1):** T-RD5, T-AW5, T-PG1, T-PG2, T-SR1, T-OR2, T-WD4, T-FM7, T-FM8, AOS `whole_suite`.

### 2.3 기술별 L2 확보 현황

설계 문서 8절 3단계는 "기술마다 L2가 하나 이상"을 목표로 한다. 현재 상태는 다음과 같다.

| 기술 | L2-먼 | L2-중간 | L1-충돌 | 비고 |
|---|---|---|---|---|
| S1 문서 따르기 | | | T-RD6 | L2 없음 |
| S2 단계 순서 | | G15 | G5 | |
| S3 행동 허용 구간 | | T-AW6, Stg5c | T-AW4, Stg1b | |
| S4 금지 대상 | | | T-PR5, T-PR3 | L2 없음 |
| S5 산출물 쓰기 규율 | | | G8 (T-WD2) | L2 없음. 충돌은 5단계 문서 검토로 추가 |
| S6 기록의 사실성 | equal (Stg4e·Stg5i) | | | |
| S7 진행 기록 | | | | **AI-DLC에 해당 규칙 없음** |
| S8 산출물 간 추적 | T-TR1b | T-TR1, T-TR2 | | AI-DLC의 특징이 가장 잘 드러나는 기술 |
| S9 질문 대신 스스로 결정 | | | | **L2·충돌 없음** |
| S10 산출물 형식 | T-FM5, T-FM6 | | | |

**L2가 없는 기술: S1, S4, S5, S7, S9.** (S5는 G8 충돌 문항은 있음.) 이 기술들은 AI-DLC 평가에서 L1(또는 충돌)로만 측정된다. 보강은 Future work 10.2의 방법으로 한다. 특히 학습 workflow 교차 검증을 쓰면 S7(AOS·OSF 체크박스)과 S9(AOS 질문·답)가 평가 workflow 쪽 고유 템플릿이 될 수 있다.

## 3. T-RD6 검증 함수 명세 (결정 4)

**규칙:** "Do not re-read an artifact you can still see. … Read an artifact only to recover, when an earlier stage's content is no longer visible because output was truncated or history was compacted." (CW "Artifact Rules", BT 11)

| 항목 | 내용 |
|---|---|
| 이름 (안) | `no_reread_visible_artifact` (공통 kind 후보, 학습 workflow에도 쓸 수 있도록) |
| 기술 / 템플릿 | S1 문서 따르기 / T-RD6 |
| 입력 | trajectory (도구 호출: view, shell의 `cat`/`head`/`sed -n` 등 읽기 명령), 산출물 경로, (가능하면) 문맥 압축 이벤트 |
| 판정 | 산출물 k가 처음 쓰인 시점 이후, 같은 경로를 읽는 행동이 있으면 위반. 단, 쓰기 이후 읽기 사이에 문맥 압축 이벤트가 있으면 예외 |
| 읽기의 정의 | 경로를 대상으로 하는 view, 또는 경로를 인자로 받는 출력 명령(`cat`, `head`, `tail`, `sed -n`, `less`, `grep`). 쓰기 직후 확인용 `ls`는 읽기가 아니다 |
| 점수 | 위반 읽기 수에 따른 비율, 또는 0/1 (정해야 함) |
| 발동 조건 | 산출물이 하나 이상 쓰인 실행. 조건 없이 사실상 항상 발동 |
| 반례 (학습 습관) | Stage 2 시작 시 `cat /tmp/swe-bench-pro/01-reverse-engineering.md`로 이전 산출물을 다시 읽음. 학습 T-RD4와 OSF ff 지시를 따르면 자연스럽게 나오는 행동 |
| 구현 위치 | `workflow_rubric/checks/actions.py`의 읽기 fact(`doc_reads`와 같은 방식)를 산출물 경로에 적용. `aidlc_v4_gen` rubric에 항목을 추가 |

**열린 질문**
- OpenHands SDK trajectory(rLLM episode)에 문맥 압축(condenser) 이벤트가 기록되는지 확인해야 한다. rubric 엔진에는 이를 다루는 코드가 없다. 기록되지 않는다면 예외 없이 판정하는 엄격한 버전으로 시작한다. 이 경우 긴 실행에서 정당한 복구 읽기도 위반으로 잡히므로, 결과를 볼 때 실행 길이와 함께 확인한다.
- 이 kind를 학습 workflow에서는 쓰지 않는다. 학습 쪽 습관(T-RD4)과 반대라서, 학습에 넣으면 충돌 문항이 사라진다.

## 4. 남은 일

1. **5단계 (학습 rubric 정리):** 학습 문서 전체를 검토한다. 골격 항목을 묶고, 반복 라운드의 중복 항목과 너무 쉬운 항목을 정리한다. 2.2의 "유지" 목록은 건드리지 않는다.
2. **6단계 (평가 scorer 보완):** 2.1의 층별 점수를 항목 단위로 낼 수 있도록 평가를 `aidlc_v4_gen` 형식에 맞추고, T-RD6을 구현한다. G15와 Stg1b는 판정 기준을 정의한 뒤 결정한다.
3. **기준점 측정 (별도 세션):** 원본 모델 non-thinking의 IFBench와 AI-DLC 점수, step24 모델의 IFBench(non-thinking).
