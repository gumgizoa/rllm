"""BMAD (bmad_build_auto) as the evaluation workflow, AFTER the stage-3 headline decisions of 2026-11-09:
subagents kept (openhands-sdk DelegateTool), intent gaps assumed-and-recorded instead of HALT, unit tests in
repository test files, bad_spec loopback and patch re-verification kept (upstream cap 5), artifacts outside
/testbed, judge items not scored for now.

Reads porting/rules.yaml (pre-port inventory, stage 1b), applies the decision table DECIDED (rule id -> new
fate [, template, layer]) on top of the inventory's port.fate estimate, and prints the layer distribution.

    python3 decided_layers.py [--rows]
"""
import yaml, collections, sys
W = "/vast-ib/MMI/home/kyuminkim/project/if/rllm/recipe/grpo/qwen3_5/workflows"
R = yaml.safe_load(open(f"{W}/bmad_build_auto/porting/rules.yaml"))
rules = {x["id"]: x for x in R["rules"]}
cat = yaml.safe_load(open(f"{W}/../sdlc_if/templates.yaml"))["templates"]
train = collections.defaultdict(collections.Counter)
for wf, lab in [("agentos_v2", "AOS"), ("openspec_ff", "OSF"), ("speckit_bug", "SKB")]:
    for c in yaml.safe_load(open(f"{W}/{wf}/constraints.yaml"))["constraints"]:
        if c["status"] == "implemented": train[str(c["template"])][lab] += 1

# decision table: id -> (fate, template or None=unchanged, layer or None=unchanged, note)
K = "keep"; E = "env"; D = "drop"; S = "semantic"
DECIDED = {
    # --- 결정 1: 서브에이전트 사용 (DelegateTool). G7 drop 중 되살리는 것 / 도구가 강제하는 것(env, enforced)
    "I1": (K, None, None, "단계가 요구하는 서브에이전트를 쓴다: delegate 호출이 trace에 남는다"),
    "I2": (E, None, None, "DelegateTool이 있으므로 도달 불가"),
    "I3": (K, None, None, "한 delegate 호출에 렌즈 4개를 함께 넣는다 (SDK의 delegate는 블로킹·동시)"),
    "I4": (E, None, None, "SDK delegate는 블로킹만 제공 (enforced)"),
    "I5": (E, None, None, "서브에이전트 LLM은 부모 LLM의 복사본 (enforced)"),
    "D4": (K, None, None, "깊은 탐색을 서브에이전트에 맡기는 선택지가 생긴다"),
    "E10": (E, None, None, "블로킹만 가능 (enforced)"),
    "E11": (K, None, None, "구현 서브에이전트 반환 뒤 Verify (순서)"),
    "E12": (E, None, None, "executor가 spawn한 서브에이전트를 세션 동안 유지 (enforced)"),
    "E13": (K, None, None, "구현자 보고의 미완 항목을 부모가 마무리 (judge; 당분간 미채점)"),
    "E3": (K, None, None, "핸드오프 텍스트 치환 (judge; 미채점)"),
    "E4": (K, None, None, "핸드오프에 덧붙이지 않음 (judge; 미채점)"),
    "E6": (E, None, None, "새 LocalConversation, 부모 맥락 없음 (enforced)"),
    "E9": (K, None, None, "구현자의 마지막 응답이 보고 (judge; 미채점)"),
    "G12": (E, None, None, "서브에이전트에 delegate 도구를 주지 않음; 결과는 마지막 메시지 (enforced)"),
    "G3": (K, None, None, "delegate task 텍스트에 diff 본문을 넣지 않는다"),
    "G86a": (K, None, None, "같은 id로 다시 delegate"),
    "G86b": (K, None, None, "정해진 patch 메시지"),
    "E7": (K, None, None, "구현 서브에이전트가 spec을 끝까지 읽는다 (서브 대화 trace)"),
    # --- 결정 2: 의도 공백은 가정하고 기록한 뒤 진행 (HALT 대신)
    # D-2 (2026-11-10): the intent HALT sentences are deleted, not replaced (SWE-bench Verified issues are
    # human-screened as well specified). Replaces the 2026-11-09 assume-and-record (T-SR1) decision.
    "C23": (D, None, None, "의도 미확정 HALT 문장 삭제 (D-2)"),
    "C12": (D, None, None, "unclear intent HALT 문장 삭제 (D-2)"),
    "D20": (D, None, None, "intent gap 항목 삭제 (D-2)"),
    "F7": (D, None, None, "matrix ambiguity HALT 삭제 (D-2)"),
    "G84c": (D, None, None, "intent_gap 라우트 삭제 (D-2)"),
    "G72": (D, None, None, "intent_gap 판정 삭제 (D-2)"),
    "G71": (K, None, None, "라우트 enum에서 intent_gap 제거 (D-2)"), "G77": (K, None, None, "행 형식에서 intent_gap 제거 (D-2)"),
    "G68": (K, None, None, "intent_gap → bad_spec 로 문구 수정 (D-2)"), "G74": (K, None, None, "intent_gap 분기 문구 삭제 (D-2)"),
    "G84a": (D, None, None, "intent_gap 라우트가 없으므로 patch 파일 저장 없음"),
    "G84b": (D, None, None, "intent_gap 라우트 없음"),
    # 실패 HALT(검증 실패·spec 기준 미달·루프 상한·matrix 감사 실패): status blocked와 사유를 기록하고 최종 보고까지 진행 (기본값, 확인 요망)
    "D28": (S, None, None, "기록하고 최선의 spec으로 진행"),
    "F2": (S, None, None, "실패 명령·사유를 기록하고 보고까지 진행"),
    "F10": (S, None, None, "같음"),
    "F8": (S, None, None, "같음"),
    "G83": (S, None, None, "상한 5 유지; 넘으면 기록하고 보고"),
    # --- 결정 3: 저장소 테스트 파일에 단위 테스트 추가
    "D42": (K, None, None, "I/O Matrix edge case를 저장소 테스트 파일에 추가하는 task (L1C 유지)"),
    "F4": (K, None, None, "행마다 테스트 (judge; 미채점)"),
    "F5": (K, None, None, ""),
    "G50": (K, None, None, "patch = 추가할 테스트 지명"),
    # --- 결정 4: bad_spec 루프백·patch 재검증 유지 (되돌리기 포함, 상한 5)
    "G85b": (K, None, None, "bad_spec: 코드 되돌리기 유지 (NEW-WD-revert)"),
    "G58": (K, None, None, "루프백이 살아 있으므로 이월 행 대조 유지"),
    "G73": (K, None, None, "judge; 미채점"), "G85a": (K, None, None, "judge; 미채점"),
    "G81": (K, None, None, "폭포식에서 intent_gap 단계 제거 (D-2)"), "G82": (K, None, None, ""), "G85c": (K, None, None, ""), "G85d": (K, None, None, ""),
    "G85e": (K, None, None, ""), "G85f": (K, None, None, ""), "F11": (K, None, None, "patch 뒤 diff 재생성"),
    # --- 결정 5: 산출물 디렉터리를 /testbed 밖으로 (G5 env 묶음 확인) -> fate env 그대로, 규칙은 남는다
    # --- 결정 6: judge 일단 미사용 -> measure == judge 항목은 분포에서 별도 열
    # --- 결정 7 (G12, 2026-11-10 user "빼자"): spec 파일 소실 HALT 두 문장 삭제 (build.py semantic edits) -> 규칙도 drop
    "D25": (D, None, None, "G12: step-02 게이트의 'If the file is missing' HALT 삭제 -- 부모가 같은 trajectory 에서 쓴 파일"),
    "C30": (D, None, None, "G12: step-03 PRECONDITION(spec 존재 확인) 삭제 -- 상동; 원문의 방어는 step 파일 간 변수 전달용"),
}
# G7 semantic rows not named above: subagents are kept, so the row stays as upstream wrote it (fate keep).
for x in R["rules"]:
    p = x["port"]
    if x["id"] in DECIDED: continue
    if p.get("gap") == "G7" and p["fate"] == S:
        DECIDED[x["id"]] = (K, None, None, "서브에이전트 유지: 상류 그대로")

def final(x):
    p = dict(x["port"]); t = x["template"]; L = x["train"].get("layer_candidate")
    if x["id"] in DECIDED:
        f, nt, nl, note = DECIDED[x["id"]]
        p = {"fate": f, "gap": p.get("gap"), "note": note}
        if nt:
            t = nt
            L = (cat.get(nt, {}).get("eval") or {}).get("layer") or ("L1" if train.get(nt) else "L2M")
        if nl: L = nl
    return p, t, L

rows = []
for x in R["rules"]:
    p, t, L = final(x)
    if p["fate"] == D: continue
    if x["measure"] in ("enforced", "none") or p["fate"] == E and x["id"] in DECIDED and "enforced" in DECIDED[x["id"]][3]:
        continue  # not scorable
    rows.append((x["id"], x["stage"], x["measure"], t, L, p["fate"], x["text"]))

def table(rs, title):
    c = collections.Counter(L for *_, L, _, _ in [(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in rs])
    print(f"\n== {title}: {len(rs)} ==")
    print(" ".join(f"{L}={c.get(L,0)}" for L in ("L1", "L1C", "L2M", "L2F")), " 템플릿없음=", c.get(None, 0))
code = [r for r in rows if r[2] == "code"]; judge = [r for r in rows if r[2] == "judge"]
table(rows, "비-drop·측정 가능 전체"); table(code, "code (채점 대상)"); table(judge, "judge (당분간 미채점)")
piv = collections.defaultdict(collections.Counter)
for r in code: piv[r[3]][r[4]] += 1
print("\n| 템플릿 | L1 | L1C | L2M | L2F | 계 |\n|---|---|---|---|---|---|")
order = sorted(piv, key=lambda t: (t is None, str(t)))
for t in order:
    c = piv[t]; print(f"| {t} | " + " | ".join(str(c.get(L, 0)) or "–" for L in ("L1", "L1C", "L2M", "L2F")) + f" | {sum(c.values())} |")
print("\nL1C code:"); [print(" ", r[0], r[3], "|", r[6][:70]) for r in code if r[4] == "L1C"]
print("\nL2F code:"); [print(" ", r[0], r[3], "|", r[6][:70]) for r in code if r[4] == "L2F"]
print("\nL2M code:"); [print(" ", r[0], r[3], "|", r[6][:70]) for r in code if r[4] == "L2M"]
if "--rows" in sys.argv:
    print("\n변경된 행:")
    for i, (f, nt, nl, note) in DECIDED.items():
        x = rules[i]; print(f"  {i:>5} {x['port']['fate']:<8}->{f:<8} {x['template']}->{nt or x['template']} | {note}")
