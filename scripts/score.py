"""룰 엔진.

파라미터(가중치·임계값·등급 컷)는 rules/rules.yaml에서 읽고,
시그널 판정 로직은 아래 SIGNALS 레지스트리에 함수로 구현한다.
튜닝은 yaml만 고치면 되고, 새 시그널을 추가할 때만 이 파일을 건드린다.
"""
import re, datetime, pathlib
from common import STATE, load_json, save_json, num

ST = STATE
GOV_AXES = {"승계", "경영권", "지주사", "행동주의", "지배구조"}


# ---------------------------------------------------------------- 유형
def match_type(cfg, report_nm):
    for t in cfg["types"]:
        if re.search(t["re"], report_nm):
            return t
    return {"id": "MISC", "w": 12, "tag": "기타"}


def is_amendment(nm):
    return bool(re.search(r"\[(기재|첨부|정정)[^\]]*\]", nm))


def base_score(cfg, d):
    s, parts = 0, []
    s += d["type_w"]; parts.append(f"{d['type_w']} 유형")
    rk = d.get("rank")
    if rk:
        for b in cfg["market_cap_bonus"]:
            if rk <= b["max"]:
                s += b["v"]; parts.append(f"+{b['v']} 시총"); break
    ch = abs(d.get("chg") or 0)
    for b in cfg["price_move_bonus"]:
        if ch >= b["min"]:
            s += b["v"]; parts.append(f"+{b['v']} 등락"); break
    return s, parts


# ---------------------------------------------------------------- 상태
def _p(kind, corp):
    return ST / kind / f"{corp}.json"


def hist(kind, corp):
    return load_json(_p(kind, corp), {})


def put(kind, corp, obj):
    save_json(_p(kind, corp), obj)


# ---------------------------------------------------------------- 시그널
def sig(cfg, sid):
    for s in cfg["signals"]:
        if s["id"] == sid:
            return s
    return {}


def scaled(spec, value):
    """scale 테이블에서 value에 해당하는 가중치."""
    if value is None:
        return 0
    for row in spec.get("scale", []):
        if value >= row["gte"]:
            return row["w"]
    return 0


def eval_signals(cfg, d, f, day_ctx):
    """d: 공시 레코드, f: 파싱 필드, day_ctx: 당일/과거 맥락"""
    out = []
    T, nm, amend = d["type_id"], d["report_nm"], d["amend"]
    corp, cap = d["corp_code"], d.get("cap")

    def add(sid, extra_w=0, why=""):
        s = sig(cfg, sid)
        if not s:
            return
        out.append({"id": sid, "label": s.get("label", sid), "axis": s.get("axis", ""),
                    "w": s.get("w", 0) + extra_w, "why": why,
                    "force_grade": s.get("force_grade"),
                    "offsets_amendment": bool(s.get("offsets_amendment"))})

    # --- 3-A 승계 · 지분이동 ---
    reason = f.get("change_reason") or ""
    if re.search(r"증여|수증", reason):
        moved, tot = abs(f.get("moved") or 0), f.get("total_shares") or 0
        ratio = round(moved / tot * 100, 2) if tot else None
        extra = 15 if (ratio or 0) >= 1.0 else 0
        why = (f"증여 {int(moved):,}주" + (f" (발행주식 대비 {ratio}%)" if ratio else "")) if moved \
              else "소유주식 변동원인: 증여·수증"
        add("SUCCESSION_GIFT", extra, why)
    if re.search(r"상속", reason):
        add("SUCCESSION_INHERIT", 0, "상속에 의한 소유주식 변동")

    if T == "LARGE_HOLD":
        prev = hist("holders", corp)
        pnow = f.get("hold_purpose") or ""
        pold = prev.get("hold_purpose") or ""
        if pold and re.search(r"단순투자|일반투자", pold) and re.search(r"경영권|경영참가|경영에 영향", pnow):
            add("PURPOSE_SHIFT", 0, f"보유목적 '{pold}' → '{pnow}'")
        rn, rp = f.get("ratio_now"), prev.get("ratio_now")
        if rn is not None and rp is not None and rn - rp <= -3.0:
            add("STAKE_DROP", 0, f"지분율 {rp}% → {rn}%")
        if pnow or rn is not None:
            put("holders", corp, {"hold_purpose": pnow or pold, "ratio_now": rn if rn is not None else rp,
                                  "date": d["date"], "rcept_no": d["rcept_no"]})

    if T in ("LARGE_HOLD", "MAJOR_CHG"):
        if re.search(r"파트너스|에쿼티|PE|사모|인베스트|캐피탈|자산운용|어드바이저", d.get("flr_nm", "")):
            add("PE_ENTRY", 0, f"보고자 {d.get('flr_nm')}")

    if T == "PLEDGE":
        add("PLEDGE_RELEASE" if re.search(r"해제|취소", nm) else "PLEDGE_RISK")

    if T == "MERGE":
        add("HOLDCO_RESTRUCT", 0, "합병·분할·주식교환 등 구조 재편")

    # --- 3-B 자본정책 ---
    if T == "VALUEUP":
        h = hist("valueup", corp)
        if not h:
            add("VALUEUP_FIRST", 0, "밸류업 계획 최초 확인")
        else:
            ups = []
            for k, lab in (("payout_target", "주주환원율"), ("roe_target", "ROE")):
                a, b = f.get(k), h.get(k)
                if a is not None and b is not None and a > b:
                    ups.append(f"{lab} {b}% → {a}%")
            if ups:
                add("VALUEUP_UPGRADE", 0, " · ".join(ups))
        put("valueup", corp, {**h, **{k: v for k, v in f.items() if k.endswith("_target")},
                              "date": d["date"]})

    if T in ("BUYBACK", "CANCEL_SHR"):
        amt = f.get("contract_amount")
        pct = round(amt / (cap * 1e8) * 100, 3) if (amt and cap) else None
        w = scaled(sig(cfg, "BUYBACK_SIZE"), pct)
        add("BUYBACK_SIZE", w, (f"금액 {amt/1e8:.0f}억원 = 시총의 {pct}%" if pct is not None else "금액 미확인"))
        d["ratio_pct"] = pct
        if T == "CANCEL_SHR":
            add("CANCEL_PREMIUM", 0, "취득이 아닌 소각 결정")
        if re.search(r"임직원|성과보상|스톡옵션", f.get("purpose") or ""):
            add("BUYBACK_FAKE", 0, f"취득목적: {f.get('purpose')}")

    if T in ("DISPOSE_SHR", "CB_BW"):
        amt = f.get("issue_amount") or f.get("contract_amount")
        pct = round(amt / (cap * 1e8) * 100, 3) if (amt and cap) else None
        add("OVERHANG", scaled(sig(cfg, "OVERHANG"), pct),
            (f"규모 {amt/1e8:.0f}억원 = 시총의 {pct}%" if pct is not None else "규모 미확인"))
        d["ratio_pct"] = pct

    if T in ("CB_BW", "RIGHTS") and re.search(r"제3자", f.get("allocation") or ""):
        allottee = f.get("allottee") or ""
        if allottee and re.search(r"최대주주|특수관계|대표이사|회장|본인", allottee):
            add("CONTROL_CB", 0, f"제3자배정 대상: {allottee}")

    if T == "TRUST_END":
        add("TRUST_CUT", 0, "자사주 신탁계약 해지")

    # --- 3-C 수주 diff ---
    if T == "ORDER":
        key = re.sub(r"\[[^\]]*\]", "", nm).strip()
        book = hist("orders", corp)
        prev = book.get(key)
        cur = {"amount": f.get("contract_amount"), "start": f.get("start_date"),
               "end": f.get("end_date"), "counterparty": f.get("counterparty"),
               "rcept_no": d["rcept_no"], "date": d["date"]}
        if amend and prev:
            material = False
            pa, ca = prev.get("amount"), cur.get("amount")
            if pa and ca:
                chg = (ca - pa) / pa * 100
                if chg <= -95 or re.search(r"해지|해제", nm):
                    add("ORDER_CANCEL", 0, f"계약금액 {pa/1e8:.0f}억 → {ca/1e8:.0f}억"); material = True
                elif chg <= -5:
                    add("ORDER_DOWN", 0, f"계약금액 {chg:+.1f}% ({pa/1e8:.0f}억 → {ca/1e8:.0f}억)"); material = True
                elif chg >= 5:
                    add("ORDER_UP", 0, f"계약금액 {chg:+.1f}% ({pa/1e8:.0f}억 → {ca/1e8:.0f}억)"); material = True
            pe, ce = prev.get("end"), cur.get("end")
            if pe and ce and pe != ce:
                if ce == "TBD":
                    add("ORDER_DELAY", 0, f"종료일 {pe} → 미정"); material = True
                elif pe != "TBD":
                    try:
                        dd = (datetime.date.fromisoformat(ce) - datetime.date.fromisoformat(pe)).days
                        if dd >= 30:
                            add("ORDER_DELAY", 0, f"종료일 {pe} → {ce} ({dd}일 연장)"); material = True
                    except ValueError:
                        pass
            if not material:
                add("ORDER_TRIVIAL", 0, "금액·기간·상대방 실질 변화 없음")
        elif not amend:
            pct = f.get("sales_pct")
            if pct is None and f.get("contract_amount") and f.get("recent_sales"):
                pct = round(f["contract_amount"] / f["recent_sales"] * 100, 2)
            add("ORDER_SIZE", scaled(sig(cfg, "ORDER_SIZE"), pct),
                (f"계약금액 = 최근매출액의 {pct}%" if pct is not None else "규모 미확인"))
            d["ratio_pct"] = pct
        if any(v is not None for v in cur.values()):
            book[key] = cur
            put("orders", corp, book)

    # --- 3-D 종목 패턴 ---
    if day_ctx["corp_count"].get(corp, 0) >= 3:
        add("CLUSTER_DAY", 0, f"당일 {day_ctx['corp_count'][corp]}건 공시")
    if day_ctx["gov5d"].get(corp, 0) >= 2 and any(s["axis"] in GOV_AXES for s in out):
        add("STREAK_GOV", 0, f"최근 5영업일 지배구조 시그널 {day_ctx['gov5d'][corp]}건")

    return out


# ---------------------------------------------------------------- 종합
def finalize(cfg, d, base, parts, signals):
    s = base
    for sg in signals:
        s += sg["w"]
        if sg["w"]:
            parts.append(f"{sg['w']:+d} {sg['label']}")
    if d["amend"] and not any(sg["offsets_amendment"] for sg in signals):
        p = cfg["penalties"]["amendment"]; s += p; parts.append(f"{p} 정정")
    if re.search(r"자율공시.*일정금액미만", d["report_nm"]):
        p = cfg["penalties"]["voluntary_small"]; s += p; parts.append(f"{p} 자율")
    s = max(0, min(120, round(s)))
    g = grade_of(cfg, s)
    forced = [sg["force_grade"] for sg in signals if sg.get("force_grade")]
    if forced:
        g = sorted(forced)[-1]
    return s, g, parts


def grade_of(cfg, s):
    for g in ("S", "A", "B"):
        if s >= cfg["grades"][g]:
            return g
    return "C"


# ---------------------------------------------------------------- 중복 묶기
def dedupe(items):
    """같은 종목의 같은 사건이 여러 건으로 공시된 경우 대표 1건만 남기고 자식으로 접는다.

    묶는 기준: (종목, 탐지된 시그널 집합). 시그널이 없으면 (종목, 유형).
    지주-자회사 동시 공시, 최대주주변동+대량보유+임원소유 3종 세트가 여기서 정리된다.
    """
    groups = {}
    for it in items:
        sids = tuple(sorted(s["id"] for s in it.get("signals", []) if s["id"] not in
                            ("CLUSTER_DAY", "STREAK_GOV")))
        key = (it["corp_code"], sids or ("TYPE:" + it["type_id"],))
        groups.setdefault(key, []).append(it)
    out = []
    for key, rows in groups.items():
        rows.sort(key=lambda r: (-r["score"], r["rcept_no"]))
        head, rest = rows[0], rows[1:]
        head["children"] = [{"rcept_no": r["rcept_no"], "report_nm": r["report_nm"],
                             "flr_nm": r.get("flr_nm", ""), "score": r["score"]} for r in rest]
        for r in rest:
            r["dup_of"] = head["rcept_no"]
        out.append(head)
        out += rest
    return out
