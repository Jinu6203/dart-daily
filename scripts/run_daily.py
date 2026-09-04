"""하루치 파이프라인 전체 실행.

  python scripts/run_daily.py [YYYY-MM-DD]

인자가 없으면 '한 시간 전 KST'의 날짜(=00:05 KST에 돌면 전날)를 대상으로 한다.
"""
import os, sys, json, datetime, collections, re
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from common import RULES, DAILY, STATE, DOCS, dash, target_date, save_json, load_json
import universe, collect, parse_doc, score, summarize

GOV_AXES = score.GOV_AXES


def gov5d_counts(d):
    """대상일 직전 5영업일치 파일에서 종목별 지배구조 시그널 수."""
    cnt = collections.Counter()
    files = sorted(DAILY.glob("*.json"))[-6:]
    for p in files:
        if p.stem >= dash(d):
            continue
        for r in load_json(p, {}).get("items", []):
            for s in r.get("signals", []):
                if s.get("axis") in GOV_AXES:
                    cnt[r["corp_code"]] += 1
    return cnt


def main():
    d = target_date(sys.argv[1] if len(sys.argv) > 1 else None)
    cfg = yaml.safe_load(open(RULES, encoding="utf-8"))
    print(f"=== {dash(d)} 파이프라인 시작 (룰셋 {cfg['version']}) ===")

    uni = universe.build(d)
    items_uni = uni.get("items", {})

    raw, kept = collect.collect(d, cfg)

    # 유니버스 매칭
    matched = []
    for x in kept:
        u = items_uni.get(x.get("stock_code") or "")
        if not u:
            continue
        t = score.match_type(cfg, x["report_nm"])
        matched.append({
            "rcept_no": x["rcept_no"], "date": dash(d),
            "corp_code": x["corp_code"], "corp_name": x["corp_name"],
            "stock_code": x["stock_code"], "flr_nm": x.get("flr_nm", ""),
            "report_nm": x["report_nm"], "pblntf_ty": x.get("pblntf_ty"),
            "market": u["market"], "rank": u["rank"], "cap": u["cap"],
            "chg": float(u["chg"]) if u.get("chg") not in (None, "") else None,
            "type_id": t["id"], "type_w": t["w"], "tag": t["tag"],
            "amend": score.is_amendment(x["report_nm"]),
        })
    print(f"[match] 유니버스 매칭 {len(matched)}건")

    day_ctx = {"corp_count": collections.Counter(m["corp_code"] for m in matched),
               "gov5d": gov5d_counts(d)}

    # 1차 채점 (원문 없이)
    for m in matched:
        m["base"], m["score_parts"] = score.base_score(cfg, m)
        m["fields"] = {}
        m["signals"] = []
        m["score"], m["grade"], m["score_parts"] = score.finalize(
            cfg, m, m["base"], list(m["score_parts"]), [])

    # 원문 파싱 대상: 1차 점수 상위 + 파싱이 의미있는 유형
    NEED_DOC = {"ORDER", "BUYBACK", "CANCEL_SHR", "DISPOSE_SHR", "TRUST_END", "CB_BW",
                "RIGHTS", "MAJOR_MOVE", "INSIDER", "LARGE_HOLD", "VALUEUP", "RUMOR", "MERGE"}
    docs_cache = {}

    def get_doc(rc):
        if rc not in docs_cache:
            try:
                docs_cache[rc] = parse_doc.fetch_text(rc, max_chars=30000)
            except Exception as e:  # noqa: BLE001
                print(f"[doc] {rc} 실패: {e}")
                docs_cache[rc] = ""
        return docs_cache[rc]

    parse_targets = [m for m in matched if m["type_id"] in NEED_DOC and m["base"] >= 25]
    parse_targets.sort(key=lambda m: -m["base"])
    parse_targets = parse_targets[:60]
    print(f"[doc] 원문 파싱 {len(parse_targets)}건")
    for m in parse_targets:
        txt = get_doc(m["rcept_no"])
        if txt:
            m["fields"] = parse_doc.parse(txt, m["type_id"])

    # 2차 채점 (시그널 반영)
    for m in matched:
        m["signals"] = score.eval_signals(cfg, m, m.get("fields", {}), day_ctx)
        m["score"], m["grade"], m["score_parts"] = score.finalize(
            cfg, m, m["base"], [p for p in m["score_parts"] if "유형" in p or "시총" in p or "등락" in p],
            m["signals"])
        m["rule_grade"] = m["grade"]

    matched = score.dedupe(matched)
    matched.sort(key=lambda m: (-m["score"], m["rank"]))

    # LLM 요약 대상
    always = set(cfg["llm"]["always_if_signal"])
    llm_items = [m for m in matched
                 if not m.get("dup_of") and m["score"] >= cfg["llm"]["min_score"]
                 or any(s["id"] in always for s in m["signals"])]
    llm_items = llm_items[:cfg["llm"]["max_per_day"]]
    n = summarize.summarize_batch(llm_items, cfg, get_doc)
    matched.sort(key=lambda m: ({"S": 0, "A": 1, "B": 2, "C": 3}[m["grade"]], -m["score"]))

    dist = collections.Counter(m["grade"] for m in matched)
    payload = {
        "date": dash(d), "ruleset": cfg["version"],
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "funnel": {"raw": len(raw), "kept": len(kept), "matched": len(matched),
                   "parsed": len(parse_targets), "llm": n},
        "universe": {"as_of": uni.get("as_of"), "count": uni.get("count", 0)},
        "dist": {g: dist.get(g, 0) for g in "SABC"},
        "items": matched,
    }
    save_json(DAILY / f"{dash(d)}.json", payload)
    print(f"[done] S{dist['S']} A{dist['A']} B{dist['B']} C{dist['C']} · 요약 {n}건")
    return payload


if __name__ == "__main__":
    main()
