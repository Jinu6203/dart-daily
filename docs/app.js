const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[c]));
const dartUrl = r => "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + r;
const chgCls = v => v > 0 ? "u" : v < 0 ? "d" : "f";
const chgTxt = v => v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(2) + "%";
const GRADES = ["S","A","B","C"];
const GLAB = { S:["즉시 확인","지배구조·정책·자본정책의 실질 변화"], A:["당일 확인","수급·실적에 직접 영향"],
               B:["참고","맥락으로 기억할 건"], C:["아카이브","IR·형식·단순 정정"] };

let INDEX = null, DAY = null, TRACKER = null;
let filter = "all", query = "", axis = "all", tquery = "";

const j = async p => (await fetch(p + "?v=" + Date.now())).json();

async function boot() {
  try { INDEX = await j("data/index.json"); }
  catch { $("#list").innerHTML = '<div class="empty">아직 생성된 데이터가 없음. Actions에서 워크플로를 한 번 실행해 주세요.</div>'; return; }
  const sel = $("#date");
  sel.innerHTML = INDEX.days.map(d => `<option value="${d.date}">${d.date}</option>`).join("");
  sel.value = INDEX.latest;
  sel.onchange = () => loadDay(sel.value);
  $("#prev").onclick = () => step(1);
  $("#next").onclick = () => step(-1);
  $("#v-daily").onclick = () => setView("daily");
  $("#v-track").onclick = () => setView("track");
  $("#q").oninput = e => { query = e.target.value; renderList(); };
  $("#tq").oninput = e => { tquery = e.target.value; renderTracker(); };
  await loadDay(INDEX.latest);
}

function step(n) {
  const i = INDEX.days.findIndex(d => d.date === DAY.date) + n;
  if (i < 0 || i >= INDEX.days.length) return;
  $("#date").value = INDEX.days[i].date;
  loadDay(INDEX.days[i].date);
}

function setView(v) {
  const daily = v === "daily";
  $("#daily").hidden = !daily; $("#track").hidden = daily;
  $("#v-daily").setAttribute("aria-selected", String(daily));
  $("#v-track").setAttribute("aria-selected", String(!daily));
  if (!daily && !TRACKER) j("data/tracker.json").then(t => { TRACKER = t; renderAxes(); renderTracker(); });
}

async function loadDay(date) {
  DAY = await j(`data/${date}.json`);
  const i = INDEX.days.findIndex(d => d.date === date);
  $("#prev").disabled = i >= INDEX.days.length - 1;
  $("#next").disabled = i <= 0;
  $("#sub").textContent = `시총 상위 ${DAY.universe?.count || 500} · 룰셋 ${DAY.ruleset || "-"}`;
  renderFunnel(); renderTabs(); renderList(); renderRail(); renderFoot();
}

function renderFunnel() {
  const f = DAY.funnel || {};
  const cells = [
    ["수집", f.raw, `유형 A·B·C·D·E·I 전건`],
    ["노이즈 제외", f.kept, `일괄신고·투자설명서·ELS 등 제외 후`],
    ["유니버스 매칭", f.matched, `시총 상위 ${DAY.universe?.count || 500} 해당분`],
    ["원문 파싱", f.parsed, `구조화 필드 추출`],
    ["LLM 요약", f.llm, `상위 컷 + 지정 시그널`],
  ];
  $("#funnel").innerHTML = cells.map(([k, v, n]) =>
    `<div><div class="k">${k}</div><div class="v">${v ?? "—"}</div><div class="n">${esc(n)}</div></div>`).join("");
}

function renderTabs() {
  const V = DAY.items.filter(x => !x.dup_of);
  const n = g => V.filter(x => x.grade === g).length;
  const sig = V.filter(x => x.signals?.length).length;
  const llm = V.filter(x => x.llm).length;
  const t = [["all", "전체", V.length], ...GRADES.map(g => [g, g, n(g)]),
             ["sig", "시그널", sig], ["llm", "요약", llm]];
  $("#tabs").innerHTML = t.map(([k, l, c]) =>
    `<button class="tab" data-f="${k}" aria-pressed="${filter === k}">${l} <span class="ct">${c}</span></button>`).join("");
  $("#tabs").onclick = e => {
    const b = e.target.closest(".tab"); if (!b) return;
    filter = b.dataset.f; renderTabs(); renderList();
  };
}

function renderList() {
  const q = query.trim().toLowerCase();
  const rows = DAY.items.filter(d => {
    if (d.dup_of && !q && filter !== "all") return false;
    if (d.dup_of && !q) return false;
    if (filter === "sig" && !d.signals?.length) return false;
    else if (filter === "llm" && !d.llm) return false;
    else if (GRADES.includes(filter) && d.grade !== filter) return false;
    if (!q) return true;
    const hay = [d.corp_name, d.stock_code, d.report_nm, d.market, d.tag,
                 ...(d.signals || []).map(s => s.label + " " + s.axis)].join(" ").toLowerCase();
    return hay.includes(q);
  });
  $("#list").innerHTML = rows.length ? rows.map(rowHtml).join("")
    : '<div class="empty">조건에 맞는 공시가 없음</div>';
}

function rowHtml(d) {
  const sigs = d.signals || [];
  const flags = [
    d.llm ? '<span class="flag sig">LLM 요약</span>' : "",
    ...sigs.map(s => `<span class="flag ${s.w < 0 ? "neg" : "sig"}">${esc(s.label)}</span>`),
    d.amend ? '<span class="flag neg">정정</span>' : "",
    `<span class="flag">${esc(d.tag)}</span>`,
  ].filter(Boolean).join("");
  const why = sigs.filter(s => s.why).map(s =>
    `<div><b>${esc(s.label)}</b> · ${esc(s.why)}</div>`).join("");
  const kids = (d.children || []).map(k =>
    `<div class="kid"><span>${k.score}</span><a href="${dartUrl(k.rcept_no)}" target="_blank" rel="noopener">${esc(k.report_nm)}</a>${k.flr_nm ? `<span>· ${esc(k.flr_nm)}</span>` : ""}</div>`).join("");
  return `<article class="row" data-g="${d.grade}"><div class="stripe"></div><div class="body">
    <div class="meta">
      <span class="grade">${d.grade}</span>
      <span class="nm">${esc(d.corp_name)}</span>
      <span>${esc(d.stock_code)}</span>
      <span>${esc(d.market)} #${d.rank}</span>
      <span class="chg ${chgCls(d.chg)}">${chgTxt(d.chg)}</span>
    </div>
    <p class="title"><a href="${dartUrl(d.rcept_no)}" target="_blank" rel="noopener">${esc(d.report_nm)}</a></p>
    ${d.headline ? `<p class="hl">${esc(d.headline)}</p>` : ""}
    <div class="flags">${flags}</div>
    ${why ? `<div class="sigwhy">${why}</div>` : ""}
    ${d.summary ? `<div class="panel">
      <div><h4>요약</h4><p>${esc(d.summary)}</p></div>
      ${d.implication ? `<div class="imp"><h4>투자 함의</h4><p>${esc(d.implication)}</p></div>` : ""}
    </div>` : ""}
    ${kids ? `<div class="kids"><div class="kidh">같은 사건으로 묶인 공시 ${d.children.length}건</div>${kids}</div>` : ""}
    <div class="score">
      <span class="bar"><i style="width:${Math.min(100, d.score)}%"></i></span>
      <span>점수 ${d.score}</span>
      <span>= ${esc((d.score_parts || []).join(" "))}</span>
      ${d.rule_grade && d.rule_grade !== d.grade
        ? `<span class="adj">▸ LLM ${d.rule_grade}→${d.grade}${d.regrade_reason ? " · " + esc(d.regrade_reason) : ""}</span>` : ""}
      <span>접수 ${d.rcept_no}</span>
    </div></div></article>`;
}

function renderRail() {
  const V = DAY.items.filter(x => !x.dup_of);
  const n = g => V.filter(x => x.grade === g).length;
  const gk = GRADES.map(g => `<div class="gk"><span class="d" style="background:var(--${g.toLowerCase()})"></span>
    <span class="lb"><b>${g} — ${GLAB[g][0]}</b>${GLAB[g][1]}</span><span class="n">${n(g)}</span></div>`).join("");
  const ax = {};
  V.forEach(d => (d.signals || []).forEach(s => { ax[s.axis] = (ax[s.axis] || 0) + 1; }));
  const axl = Object.entries(ax).sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `<div class="axl"><span>${esc(k)}</span><span>${v}</span></div>`).join("")
    || '<div class="note">이 날은 탐지된 시그널이 없음</div>';
  const hist = INDEX.days.slice(0, 20).reverse();
  const sparkCard = hist.length < 3 ? `<div class="card"><h3>추이</h3>
      <p class="note">아직 ${hist.length}일치 데이터뿐임. 며칠 쌓이면 여기에 일자별 S+A 건수 추이가 표시됨.</p></div>` : null;
  const max = Math.max(1, ...hist.map(h => (h.dist?.S || 0) + (h.dist?.A || 0)));
  const spark = hist.map(h => {
    const v = (h.dist?.S || 0) + (h.dist?.A || 0);
    return `<i class="${h.date === DAY.date ? "hi" : ""}" style="height:${Math.max(6, v / max * 100)}%" title="${h.date} S+A ${v}건"></i>`;
  }).join("");
  $("#rail").innerHTML = `
    <div class="card"><h3>등급 분포</h3>${gk}</div>
    <div class="card"><h3>시그널 축</h3>${axl}</div>
    ${sparkCard || `<div class="card"><h3>최근 20일 S+A</h3><div class="spark">${spark}</div>
      <p class="note" style="margin-top:9px">막대 하나가 하루. 높을수록 그날 확인할 건이 많았다는 뜻.</p></div>`}
    <div class="card"><h3>보는 법</h3>
      <p class="note">점수는 <b>유형 가중치 + 시총·등락 보너스 ± 시그널</b>로만 계산됨. 근거가 각 행 하단에 그대로 표시되므로, 납득이 안 되면 <code>rules/rules.yaml</code>의 숫자를 고치면 됨.</p>
      <p class="note">정정 공시는 직전 원공시와 금액·기간을 비교해 <b>실질 변화가 있을 때만</b> 감점을 상쇄함.</p></div>`;
}

function renderFoot() {
  $("#foot").innerHTML = `데이터: DART OpenAPI · 시총·등락률 KRX Open API(${esc(DAY.universe?.as_of || "-")} 기준)<br>
    생성 ${esc(DAY.generated_at || "")} · 룰셋 ${esc(DAY.ruleset || "")}<br>
    요약·함의는 공시 원문에 적힌 사실만 사용함. 원문을 조회하지 않은 건에는 요약이 없음.`;
}

/* ---------------- 지배구조 트래커 ---------------- */
function renderAxes() {
  const ax = {};
  TRACKER.stocks.forEach(s => Object.entries(s.axes).forEach(([k, v]) => ax[k] = (ax[k] || 0) + v));
  const t = [["all", "전체", TRACKER.stocks.length],
             ...Object.entries(ax).sort((a, b) => b[1] - a[1]).map(([k, v]) => [k, k, v])];
  $("#taxes").innerHTML = t.map(([k, l, c]) =>
    `<button class="tab" data-a="${esc(k)}" aria-pressed="${axis === k}">${esc(l)} <span class="ct">${c}</span></button>`).join("");
  $("#taxes").onclick = e => {
    const b = e.target.closest(".tab"); if (!b) return;
    axis = b.dataset.a; renderAxes(); renderTracker();
  };
  $("#trail").innerHTML = `<div class="card"><h3>트래커란</h3>
    <p class="note">종목별로 <b>지배구조·자본정책·수주</b> 축의 시그널만 모아 시간순으로 쌓은 화면.</p>
    <p class="note">단발 공시는 노이즈지만, 같은 종목에서 <b>승계 → 담보 제공 → 지분 감소</b>처럼 연달아 찍히면 진행 중인 딜일 가능성이 큼. 아이디에이션은 여기서 시작하는 게 빠름.</p>
    <p class="note">건수가 많은 순 → 시총 순으로 정렬됨.</p></div>`;
}

function renderTracker() {
  const q = tquery.trim().toLowerCase();
  const rows = TRACKER.stocks.filter(s => {
    if (axis !== "all" && !s.axes[axis]) return false;
    if (!q) return true;
    return (s.name + " " + s.code).toLowerCase().includes(q);
  });
  $("#trklist").innerHTML = rows.length ? rows.map(s => `
    <div class="tstock">
      <div class="thead">
        <span class="n">${esc(s.name)}</span>
        <span class="m">${esc(s.code)} · ${esc(s.market)} #${s.rank ?? "-"}</span>
        <span class="m">시그널 ${s.n}건 · 최근 ${esc(s.last)}</span>
        <span class="m">${Object.entries(s.axes).map(([k, v]) => `${esc(k)} ${v}`).join(" · ")}</span>
      </div>
      ${s.events.filter(e => axis === "all" || e.signals.some(x => x.axis === axis)).map(e => `
        <div class="tline">
          <div class="d">${esc(e.date)} · <b>${e.grade}</b></div>
          <div class="c">
            <div class="rp"><a href="${dartUrl(e.rcept_no)}" target="_blank" rel="noopener">${esc(e.report)}</a></div>
            ${e.headline ? `<div class="d">${esc(e.headline)}</div>` : ""}
            <div class="flags">${e.signals.map(x => `<span class="flag sig">${esc(x.label)}</span>`).join("")}</div>
            ${e.signals.filter(x => x.why).map(x => `<div class="d">${esc(x.why)}</div>`).join("")}
          </div>
        </div>`).join("")}
    </div>`).join("") : '<div class="empty">해당 축의 시그널이 아직 없음</div>';
}

boot();
