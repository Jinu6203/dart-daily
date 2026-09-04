"""공통 유틸 — 경로, HTTP, 날짜, 상태 파일."""
import os, json, time, datetime, pathlib, re
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DAILY = DATA / "daily"
STATE = DATA / "state"
DOCS = ROOT / "docs"
RULES = ROOT / "rules" / "rules.yaml"
KST = datetime.timezone(datetime.timedelta(hours=9))

for p in (DAILY, STATE, DOCS / "data"):
    p.mkdir(parents=True, exist_ok=True)


def kst_now():
    return datetime.datetime.now(KST)


def target_date(argv_date=None):
    """대상 영업일. 인자가 있으면 그대로, 없으면 '한 시간 전 KST'의 날짜.
    00:05 KST에 돌면 전날(장 마감된 날)을 가리킨다."""
    if argv_date:
        return argv_date.replace("-", "")
    return (kst_now() - datetime.timedelta(hours=1)).strftime("%Y%m%d")


def dash(d):
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def get(url, params=None, headers=None, tries=4, timeout=30):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = str(e)
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"GET 실패 {url}: {last}")


def load_json(p, default=None):
    p = pathlib.Path(p)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(p, obj):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def clean_title(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def num(s):
    """'1,300,000,000' -> 1300000000.0 / 실패 시 None"""
    if s is None:
        return None
    t = re.sub(r"[^\d.\-]", "", str(s))
    if t in ("", "-", "."):
        return None
    try:
        return float(t)
    except ValueError:
        return None
