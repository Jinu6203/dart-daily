"""DART 공시 원문(document.xml)에서 구조화 필드를 뽑는다.

수주·자사주·유증/CB·지분변동 공시의 핵심 숫자를 정규식으로 파싱.
파싱 실패는 None으로 두고 절대 추정값을 만들지 않는다.
"""
import io, os, re, zipfile
from common import get, num

DOC_URL = "https://opendart.fss.or.kr/api/document.xml"
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"[ \t\xa0]+")


def fetch_text(rcept_no, key=None, max_chars=20000):
    key = key or os.environ["DART_API_KEY"]
    r = get(DOC_URL, params={"crtfc_key": key, "rcept_no": rcept_no}, timeout=60)
    if r.content[:2] != b"PK":
        return ""
    z = zipfile.ZipFile(io.BytesIO(r.content))
    parts = []
    for n in z.namelist():
        b = z.read(n)
        for enc in ("utf-8", "cp949", "euc-kr"):
            try:
                parts.append(b.decode(enc)); break
            except UnicodeDecodeError:
                continue
    s = "\n".join(parts)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = TAG.sub("\n", s)
    s = WS.sub(" ", s)
    s = re.sub(r"\n\s*\n+", "\n", s).strip()
    return s[:max_chars]


def _after(text, *labels, window=90):
    """라벨 뒤 window자 안의 첫 숫자 문자열을 반환."""
    for lab in labels:
        m = re.search(re.escape(lab) + r"[^\d\-]{0,%d}([\d,\.]+)" % window, text)
        if m:
            return m.group(1)
    return None


def _date_after(text, *labels, window=120):
    for lab in labels:
        m = re.search(re.escape(lab) + r".{0,%d}?(\d{4})[-.년 ]{1,3}(\d{1,2})[-.월 ]{1,3}(\d{1,2})" % window, text, re.S)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        m2 = re.search(re.escape(lab) + r".{0,40}?(미정|-)\s*\n", text, re.S)
        if m2 and m2.group(1) == "미정":
            return "TBD"
    return None


def parse(text, type_id):
    f = {}
    t = text

    if type_id == "ORDER":
        f["contract_amount"] = num(_after(t, "계약금액(원)", "계약금액"))
        f["recent_sales"] = num(_after(t, "최근매출액(원)", "최근매출액"))
        f["sales_pct"] = num(_after(t, "매출액대비(%)", "매출액대비"))
        f["counterparty"] = _text_after(t, "3. 계약상대", "계약상대")
        f["start_date"] = _date_after(t, "시작일")
        f["end_date"] = _date_after(t, "종료일")
        if f["end_date"] is None and re.search(r"종료일\s*\n?\s*-\s*\n", t):
            f["end_date"] = "TBD"
        f["amend_reason"] = _text_after(t, "3. 정정사유", "정정사유")

    elif type_id in ("BUYBACK", "CANCEL_SHR", "DISPOSE_SHR", "TRUST_END"):
        f["contract_amount"] = num(_after(t, "계약금액(원)", "취득금액", "처분금액", "소각할 주식의 취득금액", "계약금액"))
        f["shares"] = num(_after(t, "취득예정주식(주)", "처분예정주식(주)", "소각할 주식의 종류와 수", "보통주식"))
        f["purpose"] = _text_after(t, "계약목적", "취득목적", "처분목적", "4. 계약목적")
        f["limit"] = num(_after(t, "자기주식 취득금액 한도", "배당가능이익 한도"))

    elif type_id in ("CB_BW", "RIGHTS"):
        f["issue_amount"] = num(_after(t, "시설자금(원)", "자금조달의 목적", "사채의 권면(전자등록)총액(원)", "신주발행가액", "자금조달금액"))
        if f.get("issue_amount") is None:
            f["issue_amount"] = num(_after(t, "총액", "증자금액"))
        f["allocation"] = _text_after(t, "증자방식", "배정방법", "공모 또는 사모")
        f["allottee"] = _text_after(t, "제3자배정 대상자", "사채인수인")

    elif type_id in ("MAJOR_MOVE", "INSIDER", "LARGE_HOLD"):
        f["change_reason"] = _joined(t, r"변경원인\s*\n([^\n]{0,40})", r"(증여\(\-\)|수증\(\+\)|상속|장내매수|장내매도|시간외매매|담보제공)")
        f["total_shares"] = num(_after(t, "발행주식총수(1+2)", "보통주식총수(1)"))
        f["moved"] = _signed_change(t)
        f["hold_purpose"] = _text_after(t, "보유목적", "보유 목적")
        f["ratio_now"] = num(_after(t, "이번보고서제출일", window=200))
        f["ratio_prev"] = num(_after(t, "직전보고서제출일", window=200))

    elif type_id == "VALUEUP":
        f["roe_target"] = num(_grab(t, r"ROE\s*([\d.]+)\s*%"))
        f["payout_target"] = num(_grab(t, r"주주환원율\s*([\d.]+)\s*%"))
        f["cet1_target"] = num(_grab(t, r"(?:CET1|보통주자본비율)[^\d]{0,12}([\d.]+)\s*%"))
        f["prev_payout"] = num(_after(t, "배당성향(%)"))

    elif type_id == "RUMOR":
        f["rumor"] = _text_after(t, "1. 풍문 또는 보도의 내용", "풍문 또는 보도의 내용")
        f["media"] = _text_after(t, "2. 풍문 또는 보도의 매체", "풍문 또는 보도의 매체")
        f["reply"] = _text_after(t, "해명내용", window=600)
        f["recheck"] = _date_after(t, "재공시예정일")

    return {k: v for k, v in f.items() if v not in (None, "", [])}


def _text_after(t, *labels, window=160):
    for lab in labels:
        m = re.search(re.escape(lab) + r"\s*\n\s*([^\n]{1,%d})" % window, t)
        if m:
            v = m.group(1).strip()
            if v and v != "-":
                return v
    return None


def _grab(t, pattern):
    m = re.search(pattern, t)
    return m.group(1) if m else None


def _joined(t, *patterns):
    for p in patterns:
        m = re.search(p, t)
        if m:
            return m.group(1).strip()
    return None


def _signed_change(t):
    """개인별 세부변동사항의 증감주식수(부호 포함) 중 절대값 최대치."""
    best = None
    for m in re.finditer(r"(증여\(\-\)|수증\(\+\)|상속|매도|매수)[^\n]*\n[^\n]*\n\s*([\-\d,]+)", t):
        v = num(m.group(2))
        if v is not None and (best is None or abs(v) > abs(best)):
            best = v
    if best is None:
        m = re.search(r"증감주식수\s*\n[^\n]*\n\s*([\-\d,]+)", t)
        best = num(m.group(1)) if m else None
    return best
