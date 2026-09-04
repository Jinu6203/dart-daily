"""KRX Open API로 시총 상위 유니버스(코스피 300 + 코스닥 200) 생성.

- ETF/ETN/ELW는 별도 엔드포인트라 자동 제외됨
- 우선주는 종목코드 끝자리·종목명으로 제외
- KRX 키가 없거나 실패하면 직전 universe.json을 그대로 재사용
"""
import os, re, sys
from common import DATA, get, load_json, save_json, target_date

KRX_BASE = "https://data-dbg.krx.co.kr/svc/apis"
ENDPOINTS = [("sto/stk_bydd_trd", "KOSPI", 300), ("sto/ksq_bydd_trd", "KOSDAQ", 200)]
PREF = re.compile(r"(우$|우B$|\d우B?$|우선주)")


def fetch(path, basDd, key):
    r = get(f"{KRX_BASE}/{path}", params={"basDd": basDd},
            headers={"AUTH_KEY": key}, timeout=40)
    return r.json().get("OutBlock_1", [])


def build(basDd):
    key = os.environ.get("KRX_API_KEY", "").strip()
    out_path = DATA / "universe.json"
    if not key:
        print("[universe] KRX_API_KEY 없음 → 기존 universe.json 재사용")
        return load_json(out_path, {"as_of": None, "items": {}})

    rows = []
    for path, mkt, top in ENDPOINTS:
        try:
            raw = fetch(path, basDd, key)
        except Exception as e:  # noqa: BLE001
            print(f"[universe] {mkt} 조회 실패({e}) → 기존 파일 재사용")
            return load_json(out_path, {"as_of": None, "items": {}})
        cand = []
        for x in raw:
            code = (x.get("ISU_SRT_CD") or "").strip()
            name = (x.get("ISU_ABBRV") or "").strip()
            cap = x.get("MKTCAP")
            if not code or not name or not cap:
                continue
            if PREF.search(name) or not code[-1].isdigit() or code[-1] != "0":
                # 보통주는 통상 끝자리 0. 스팩/신주인수권 등도 함께 걸러짐
                if PREF.search(name):
                    continue
            try:
                cap = int(str(cap).replace(",", ""))
            except ValueError:
                continue
            cand.append({
                "code": code, "name": name, "market": mkt, "cap": cap,
                "close": str(x.get("TDD_CLSPRC", "")).replace(",", ""),
                "chg": str(x.get("FLUC_RT", "")).replace(",", ""),
            })
        cand.sort(key=lambda r: -r["cap"])
        rows += cand[:top]

    rows.sort(key=lambda r: -r["cap"])
    items = {}
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        items[r["code"]] = r
    uni = {"as_of": basDd, "count": len(items), "items": items}
    save_json(out_path, uni)
    print(f"[universe] {basDd} 기준 {len(items)}종목")
    return uni


if __name__ == "__main__":
    build(target_date(sys.argv[1] if len(sys.argv) > 1 else None))
