"""오프라인 셀프테스트 — 실제 2026-09-03 공시로 룰 엔진 검증 (네트워크·API키 불필요)."""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(__file__))
import yaml
from common import RULES, STATE, save_json
import score

cfg = yaml.safe_load(open(RULES, encoding="utf-8"))
ok = fail = 0

def check(name, cond, detail=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS  {name}")
    else:    fail += 1; print(f"  FAIL  {name}  {detail}")

def run(rec, fields, ctx=None):
    ctx = ctx or {"corp_count": collections.Counter(), "gov5d": collections.Counter()}
    rec.setdefault("amend", score.is_amendment(rec["report_nm"]))
    t = score.match_type(cfg, rec["report_nm"])
    rec["type_id"], rec["type_w"], rec["tag"] = t["id"], t["w"], t["tag"]
    base, parts = score.base_score(cfg, rec)
    sigs = score.eval_signals(cfg, rec, fields, ctx)
    s, g, parts = score.finalize(cfg, rec, base, parts, sigs)
    return {"score": s, "grade": g, "parts": parts, "signals": [x["id"] for x in sigs],
            "why": {x["id"]: x.get("why") for x in sigs}}

print("\n[1] 유형 매칭")
for nm, want in [("최대주주등소유주식변동신고서","MAJOR_MOVE"),
                 ("기업가치 제고 계획(자율공시)","VALUEUP"),
                 ("[기재정정]단일판매ㆍ공급계약체결(자회사의 주요경영사항)","ORDER"),
                 ("주요사항보고서(자기주식취득 신탁계약 체결 결정)","BUYBACK"),
                 ("주요사항보고서(자기주식취득신탁계약해지결정)","TRUST_END"),
                 ("풍문 또는 보도에 대한 해명(미확정)","RUMOR"),
                 ("기업설명회(IR)개최(안내공시)","IR"),
                 ("불성실공시법인지정예고 (공시번복 2건)","BAD_DISC")]:
    check(f"{nm[:28]} → {want}", score.match_type(cfg, nm)["id"] == want,
          f"got {score.match_type(cfg,nm)['id']}")

print("\n[2] HD현대 승계 (정몽준 → 정기선 280만주 증여)")
r = run({"rcept_no":"20260903800626","date":"2026-09-03","corp_code":"01205709",
         "corp_name":"HD현대","stock_code":"267250","flr_nm":"HD현대(주)",
         "report_nm":"최대주주등소유주식변동신고서","market":"KOSPI","rank":42,
         "cap":189978,"chg":12.65},
        {"change_reason":"증여(-)","total_shares":78993085.0,"moved":-2800000.0})
print("   ", r["score"], r["grade"], r["signals"], r["why"].get("SUCCESSION_GIFT"))
check("SUCCESSION_GIFT 탐지", "SUCCESSION_GIFT" in r["signals"])
check("증여비율 1% 초과 → +15 escalate", r["score"] >= 75, f"score={r['score']}")
check("등급 S", r["grade"] == "S", r["grade"])

print("\n[3] HD현대 수주공시 정정 — 종료일 2026-09-03 → 미정")
STATE.joinpath("orders").mkdir(parents=True, exist_ok=True)
save_json(STATE/"orders"/"01205709.json", {
  "단일판매ㆍ공급계약체결(자회사의 주요경영사항)": {
    "amount": 878100000000.0, "start": "2021-05-08", "end": "2026-09-03",
    "counterparty": "Keppel Shipyard Limited", "rcept_no":"20210511800001","date":"2021-05-11"}})
r2 = run({"rcept_no":"20260903800541","date":"2026-09-03","corp_code":"01205709",
          "corp_name":"HD현대","stock_code":"267250","flr_nm":"HD현대(주)",
          "report_nm":"[기재정정]단일판매ㆍ공급계약체결(자회사의 주요경영사항)",
          "market":"KOSPI","rank":42,"cap":189978,"chg":12.65},
         {"contract_amount":878100000000.0,"recent_sales":8312000000000.0,
          "sales_pct":10.56,"start_date":"2021-05-08","end_date":"TBD",
          "counterparty":"Keppel Shipyard Limited"})
print("   ", r2["score"], r2["grade"], r2["signals"], r2["why"].get("ORDER_DELAY"))
check("ORDER_DELAY 탐지", "ORDER_DELAY" in r2["signals"])
check("ORDER_TRIVIAL 아님", "ORDER_TRIVIAL" not in r2["signals"])
check("정정 감점 상쇄됨(offsets_amendment)", not any("정정" in p for p in r2["parts"]), r2["parts"])

print("\n[4] 단순 오기 정정 → 강제 C")
save_json(STATE/"orders"/"99999999.json", {
  "단일판매ㆍ공급계약체결": {"amount": 1000e8, "start":"2026-01-01","end":"2027-01-01",
                          "counterparty":"A","rcept_no":"x","date":"2026-08-01"}})
r3 = run({"rcept_no":"z","date":"2026-09-03","corp_code":"99999999","corp_name":"테스트",
          "stock_code":"000000","flr_nm":"","report_nm":"[기재정정]단일판매ㆍ공급계약체결",
          "market":"KOSPI","rank":10,"cap":500000,"chg":0.1},
         {"contract_amount":1000e8,"start_date":"2026-01-01","end_date":"2027-01-01","counterparty":"A"})
print("   ", r3["score"], r3["grade"], r3["signals"])
check("ORDER_TRIVIAL 탐지", "ORDER_TRIVIAL" in r3["signals"])
check("강제 C등급", r3["grade"] == "C", r3["grade"])

print("\n[5] 가온칩스 자사주 13억 — 시총 대비 0.26%")
r4 = run({"rcept_no":"20260903000301","date":"2026-09-03","corp_code":"01364747",
          "corp_name":"가온칩스","stock_code":"399720","flr_nm":"",
          "report_nm":"주요사항보고서(자기주식취득 신탁계약 체결 결정)",
          "market":"KOSDAQ","rank":320,"cap":4993,"chg":4.47},
         {"contract_amount":1300000000.0,"purpose":"주주가치 제고 및 임직원 보상"})
print("   ", r4["score"], r4["grade"], r4["signals"], r4["why"].get("BUYBACK_SIZE"))
check("BUYBACK_SIZE 0.5% 미만 → 가산 0", r4["score"] < 60, f"score={r4['score']}")
check("BUYBACK_FAKE(임직원 보상) 감점", "BUYBACK_FAKE" in r4["signals"])

print("\n[6] BNK 밸류업 — 최초 vs 목표 상향")
import shutil; shutil.rmtree(STATE/"valueup", ignore_errors=True)
base_rec = lambda: {"rcept_no":"20260903800537","date":"2026-09-03","corp_code":"00858364",
  "corp_name":"BNK금융지주","stock_code":"138930","flr_nm":"","market":"KOSPI",
  "rank":120,"cap":47223,"chg":-2.72,"report_nm":"기업가치 제고 계획(자율공시)"}
r5 = run(base_rec(), {"roe_target":10.5,"payout_target":50.0,"cet1_target":12.5})
check("VALUEUP_FIRST 탐지", "VALUEUP_FIRST" in r5["signals"])
check("등급 S", r5["grade"]=="S", f"{r5['score']} {r5['grade']}")
r6 = run(base_rec(), {"roe_target":10.5,"payout_target":60.0,"cet1_target":12.5})
print("   재공시:", r6["score"], r6["grade"], r6["signals"], r6["why"].get("VALUEUP_UPGRADE"))
check("2회차는 UPGRADE로 판정", "VALUEUP_UPGRADE" in r6["signals"])
check("목표 상향 근거 표기", "50.0% → 60.0%" in (r6["why"].get("VALUEUP_UPGRADE") or ""),
      r6["why"].get("VALUEUP_UPGRADE"))

print("\n[7] 보유목적 전환 (단순투자 → 경영참가)")
shutil.rmtree(STATE/"holders", ignore_errors=True)
h = {"rcept_no":"a","date":"2026-09-01","corp_code":"00111111","corp_name":"X","stock_code":"111111",
     "flr_nm":"OO파트너스","report_nm":"주식등의대량보유상황보고서(일반)","market":"KOSPI",
     "rank":200,"cap":30000,"chg":1.0}
run(dict(h), {"hold_purpose":"단순투자","ratio_now":6.1})
r7 = run(dict(h, rcept_no="b", date="2026-09-03"), {"hold_purpose":"경영권에 영향을 주기 위한 목적","ratio_now":9.8})
print("   ", r7["score"], r7["grade"], r7["signals"], r7["why"].get("PURPOSE_SHIFT"))
check("PURPOSE_SHIFT 탐지", "PURPOSE_SHIFT" in r7["signals"])
check("PE_ENTRY 동시 탐지", "PE_ENTRY" in r7["signals"])
check("등급 S", r7["grade"]=="S", f"{r7['score']} {r7['grade']}")

print("\n[8] IR 공시는 C로 남는가")
r8 = run({"rcept_no":"i","date":"2026-09-03","corp_code":"00164742","corp_name":"현대차",
          "stock_code":"005380","flr_nm":"","report_nm":"기업설명회(IR)개최(안내공시)",
          "market":"KOSPI","rank":7,"cap":785246,"chg":0.0}, {})
check("현대차 IR도 C등급", r8["grade"]=="C", f"{r8['score']} {r8['grade']}")

print(f"\n=== {ok} passed, {fail} failed ===")
sys.exit(1 if fail else 0)
