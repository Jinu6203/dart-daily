"""KRX Open API로 시총 상위 유니버스(코스피 300 + 코스닥 200) 생성."""
import os, re, sys
from common import DATA, get, load_json, save_json, target_date

KRX_BASE = "https://data-dbg.krx.co.kr/svc/apis"
ENDPOINTS = [("sto/stk_bydd_trd", "KOSPI", 300), ("sto/ksq_bydd_trd", "KOSDAQ", 200)]
PREF = re.compile(r"(우$|우B$|\d우B?$|우선주)")


def fetch(path, basDd, key):
    r = get(f"{KRX_BASE}/{path}", params={"basDd": basDd},
            headers={"AUTH_KEY": key}, timeout=60)
    j = r.json()
    for k in ("OutBlock_1", "outBlock_1", "output", "data"):
        if isinstance(j.get(k), list):
            return j[k]
    for v in j.values():
        if isinstance(v, list):
            return v
    return []


def normalize(x, mkt):
    code = str(x.get("ISU_CD") or "").strip()
    name = str(x.get("ISU_NM") or "").strip()
    cap = str(x.get("MKTCAP") or "").replace(",", "").strip()
    if not code or not name or not cap.isdigit():
        return None
    if PREF.search(name):          # 삼성전자우, 현대차2우B 등
        return None
    if code[-1] != "0":            # 보통주는 단축코드 끝자리가 0
        return None
    chg = str(x.get("FLUC_RT") or "").replace(",", "").strip()
    return {"code": code, "name": name,
            "market": str(x.get("MKT_NM") or mkt).strip() or mkt,
            "cap": round(int(cap) / 1e8),          # 원 → 억원
            "close": str(x.get("TDD_CLSPRC") or "").replace(",", ""),
            "chg": chg}


def build(basDd):
    key = os.environ.get("KRX_API_KEY", "").strip()
    out_path = DATA / "universe.json"
    prev = load_json(out_path, {"as_of": None, "count": 0, "items": {}})
    if not key:
        print("[universe] KRX_API_KEY 없음 → 기존 universe.json 재사용")
        return prev

    rows = []
    for path, mkt, top in ENDPOINTS:
        try:
            raw = fetch(path, basDd, key)
        except Exception as e:
            print(f"[universe] {mkt} 조회 실패({e}) → 기존 파일 재사용")
            return prev
        cand = [n for n in (normalize(x, mkt) for x in raw) if n]
        cand.sort(key=lambda r: -r["cap"])
        print(f"[universe] {mkt} 응답 {len(raw)}행 → 보통주 {len(cand)}종목 → 상위 {min(top, len(cand))} 채택")
        rows += cand[:top]

    if not rows:
        print("[universe] 채택된 종목 0 → 기존 파일 재사용 (응답 형식 확인 필요)")
        return prev

    rows.sort(key=lambda r: -r["cap"])
    items = {}
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        items[r["code"]] = r
    uni = {"as_of": basDd, "count": len(items), "items": items}
    save_json(out_path, uni)
    print(f"[universe] {basDd} 기준 {len(items)}종목 "
          f"(1위 {rows[0]['name']} {rows[0]['cap']:,}억 / 꼴찌 {rows[-1]['name']} {rows[-1]['cap']:,}억)")
    return uni


if __name__ == "__main__":
    build(target_date(sys.argv[1] if len(sys.argv) > 1 else None))
