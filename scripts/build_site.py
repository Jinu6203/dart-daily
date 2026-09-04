"""data/daily/*.json → docs/data/ 로 복사하고 인덱스·트래커 생성."""
import sys, os, json, shutil, collections
sys.path.insert(0, os.path.dirname(__file__))
from common import DAILY, DOCS, load_json, save_json
import score

OUT = DOCS / "data"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    days = sorted(p.stem for p in DAILY.glob("20*.json"))
    index, tracker = [], collections.defaultdict(list)
    for day in days:
        j = load_json(DAILY / f"{day}.json", {})
        shutil.copyfile(DAILY / f"{day}.json", OUT / f"{day}.json")
        index.append({"date": day, "dist": j.get("dist", {}),
                      "funnel": j.get("funnel", {}), "ruleset": j.get("ruleset")})
        for it in j.get("items", []):
            govs = [s for s in it.get("signals", []) if s.get("axis") in score.GOV_AXES
                    or s.get("axis") in ("밸류업", "주주환원", "수주", "희석")]
            if not govs:
                continue
            tracker[it["stock_code"]].append({
                "date": day, "name": it["corp_name"], "market": it.get("market"),
                "rank": it.get("rank"), "grade": it["grade"], "score": it["score"],
                "report": it["report_nm"], "rcept_no": it["rcept_no"],
                "headline": it.get("headline"),
                "signals": [{"label": s["label"], "axis": s["axis"], "why": s.get("why")} for s in govs],
            })
    index.sort(key=lambda x: x["date"], reverse=True)
    save_json(OUT / "index.json", {"days": index, "latest": index[0]["date"] if index else None})

    trk = []
    for code, evs in tracker.items():
        evs.sort(key=lambda e: e["date"], reverse=True)
        axes = collections.Counter(s["axis"] for e in evs for s in e["signals"])
        trk.append({"code": code, "name": evs[0]["name"], "market": evs[0].get("market"),
                    "rank": evs[0].get("rank"), "n": len(evs),
                    "last": evs[0]["date"], "axes": dict(axes), "events": evs[:20]})
    trk.sort(key=lambda t: (-t["n"], t["rank"] or 9999))
    save_json(OUT / "tracker.json", {"stocks": trk})
    print(f"[site] {len(index)}일치 · 트래커 {len(trk)}종목")


if __name__ == "__main__":
    main()
