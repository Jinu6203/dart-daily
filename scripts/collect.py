"""DART OpenAPI에서 대상일 공시 전건 수집 + 노이즈 1차 폐기."""
import os, re, sys
from common import get, save_json, DATA, dash

LIST_URL = "https://opendart.fss.or.kr/api/list.json"


def fetch_type(key, d, ty):
    out, page = [], 1
    while True:
        r = get(LIST_URL, params={"crtfc_key": key, "bgn_de": d, "end_de": d,
                                  "pblntf_ty": ty, "page_no": page, "page_count": 100})
        j = r.json()
        if j.get("status") == "013":       # 조회된 데이터 없음
            break
        if j.get("status") != "000":
            print(f"[collect] {ty} p{page} status={j.get('status')} {j.get('message')}")
            break
        out += j.get("list", [])
        if page >= int(j.get("total_page", 1)):
            break
        page += 1
    return out


def collect(d, cfg):
    key = os.environ["DART_API_KEY"]
    drop_re = re.compile("|".join(cfg["collect"]["drop_report_patterns"]))
    drop_cls = set(cfg["collect"]["drop_corp_cls"])
    raw, kept = [], []
    for ty in cfg["collect"]["pblntf_ty"]:
        got = fetch_type(key, d, ty)
        for x in got:
            x["pblntf_ty"] = ty
        raw += got
    seen = set()
    for x in raw:
        rc = x.get("rcept_no")
        if not rc or rc in seen:
            continue
        seen.add(rc)
        nm = re.sub(r"\s+", " ", x.get("report_nm", "")).strip()
        x["report_nm"] = nm
        if drop_re.search(nm):
            continue
        if x.get("corp_cls") in drop_cls and not x.get("stock_code"):
            continue
        kept.append(x)
    print(f"[collect] {dash(d)} 수집 {len(raw)} → 노이즈 제외 후 {len(kept)}")
    save_json(DATA / "state" / f"raw-{dash(d)}.json",
              {"date": dash(d), "raw": len(raw), "kept": len(kept), "list": kept})
    return raw, kept
