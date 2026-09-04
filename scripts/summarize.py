"""Anthropic API로 상위 공시만 요약 + 투자 함의 생성."""
import os, json, re

SYSTEM = """너는 한국 주식 공시를 읽는 애널리스트다. 아래 규칙을 반드시 지켜라.

1) 공시 원문에 적힌 사실만 쓴다. 원문에 없는 수치·배경·전망을 만들어내지 않는다.
2) 문장은 '~음', '~함' 체로 끝낸다.
3) summary: 무슨 일이 일어났는지 2~3문장. 금액·주식수·비율·날짜는 원문 표기 그대로 쓴다.
4) implication: 투자 판단에 왜 중요한지 1~2문장. 해석은 하되 주가 예측·매수매도 의견은 쓰지 않는다.
   특히 다음을 확인해서 밝혀라 — 정정 공시라면 무엇이 실제로 바뀌었는지, 신규 건인지 아닌지.
   금액이 시가총액이나 매출액 대비 얼마나 되는지(주어진 값이 있을 때만).
5) headline: 12자 이내 한국어 명사구.
6) regrade: 규칙 점수가 매긴 등급이 과대/과소하면 조정한다. 근거가 없으면 null.
   - 원문이 형식적·반복적이거나 실질 변화가 없으면 낮춘다.
   - 지배구조 승계·경영권 이전·정부정책 확인·주주환원 목표 신설처럼
     유형 가중치가 놓치는 실질이 있으면 올린다.
7) regrade_reason: 조정했을 때만 20자 이내로.

반드시 아래 JSON 스키마만 출력한다. 다른 텍스트 금지.
{"headline":str,"summary":str,"implication":str,"regrade":"S"|"A"|"B"|"C"|null,"regrade_reason":str|null}"""


def build_prompt(d, doc):
    ctx = [f"종목: {d['corp_name']} ({d.get('stock_code') or '-'}) / {d.get('market') or '-'} 시총순위 {d.get('rank') or '-'}",
           f"당일 등락률: {d.get('chg')}%" if d.get("chg") is not None else "",
           f"공시명: {d['report_nm']}",
           f"접수일: {d['date']} / 접수번호: {d['rcept_no']}",
           f"규칙 점수: {d['score']} → 등급 {d['grade']} ({' '.join(d['score_parts'])})"]
    if d.get("signals"):
        ctx.append("탐지된 시그널: " + ", ".join(f"{s['label']}({s['why']})" if s.get("why") else s["label"]
                                              for s in d["signals"]))
    if d.get("fields"):
        ctx.append("파싱된 필드: " + json.dumps(d["fields"], ensure_ascii=False))
    ctx = "\n".join(x for x in ctx if x)
    return f"{ctx}\n\n=== 공시 원문 ===\n{doc}"


def summarize_batch(items, cfg, get_doc):
    """items: 요약 대상 레코드 리스트. get_doc(rcept_no)->str"""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("[llm] ANTHROPIC_API_KEY 없음 → 요약 건너뜀 (규칙 점수만 게시)")
        return 0
    try:
        import anthropic
    except ImportError:
        print("[llm] anthropic 패키지 없음 → 건너뜀")
        return 0

    client = anthropic.Anthropic(api_key=key)
    model = cfg["llm"]["model"]
    done = 0
    for d in items:
        try:
            doc = get_doc(d["rcept_no"])
            if not doc:
                continue
            r = client.messages.create(
                model=model, max_tokens=900, system=SYSTEM,
                messages=[{"role": "user", "content": build_prompt(d, doc[:cfg["llm"]["doc_max_chars"]])}])
            txt = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
            m = re.search(r"\{.*\}", txt, re.S)
            if not m:
                continue
            j = json.loads(m.group(0))
            d["headline"] = j.get("headline")
            d["summary"] = j.get("summary")
            d["implication"] = j.get("implication")
            rg = j.get("regrade")
            if cfg["llm"].get("allow_regrade") and rg in ("S", "A", "B", "C") and rg != d["grade"]:
                d["rule_grade"] = d["grade"]
                d["grade"] = rg
                d["regrade_reason"] = j.get("regrade_reason") or ""
            d["llm"] = True
            d["tokens"] = {"in": r.usage.input_tokens, "out": r.usage.output_tokens}
            done += 1
        except Exception as e:  # noqa: BLE001
            print(f"[llm] {d['rcept_no']} 실패: {e}")
    print(f"[llm] {done}/{len(items)}건 요약 완료")
    return done
