// IA 4 — zakładka Inwestor: wirtualny inwestor, strategie i spółki (dane: telemetry/vi.json,
// research/strategies.jsonl, telemetry/state.json). Wersja projektu: 1.38 (2026-10-13)
//
// renderInvestor() jest wspólne z przyszłym inwestorem FX (zakładka FX, telemetry/fx-vi.json) —
// ten sam format pliku daje ten sam widok.

import { store, num, pct, usd, sgn, esc, cls, age, t, plStamp, nyseOpen } from "../core.js";
import { equity } from "../chart.js";

const ui = { filter: "vi", q: "", sort: "pf" };

const reads = (d, s) => `<div class="reads">
  <div class="read"><div class="k">wynik zrealizowany</div><div class="v ${cls(s.realizedUsd)}">${usd(s.realizedUsd)}</div><div class="s">${s.closed} zamkniętych · stawka ${num(d.stake)} $</div></div>
  <div class="read"><div class="k">niezrealizowany</div><div class="v ${cls(s.unrealizedUsd)}">${usd(s.unrealizedUsd)}</div><div class="s">${s.open} otwartych · ${s.pending} oczekuje</div></div>
  <div class="read"><div class="k">średni wynik transakcji</div><div class="v ${cls(s.avgPct)}">${s.avgPct === null ? "—" : sgn(s.avgPct, 2) + "%"}</div>
    <div class="s">${s.ci95Pct === null ? "przedział 95%: za mało transakcji" : `95%: ${sgn(s.avgPct - s.ci95Pct, 2)} … ${sgn(s.avgPct + s.ci95Pct, 2)}%`}</div></div>
  <div class="read"><div class="k">skuteczność (TP)</div><div class="v">${pct(s.tpShare)}</div><div class="s">TP ${s.exits.TP} · SL ${s.exits.SL} · FC ${s.exits.FC} · limit ${s.exits.LIMIT}</div></div>
  <div class="read"><div class="k">mediana świec w pozycji</div><div class="v">${s.medianBars ?? "—"}</div><div class="s">koszty ${num(s.costsUsd, 2)} $ (${num(100 * d.costPct * 2, 3)}% / transakcję)</div></div>
  <div class="read"><div class="k">od</div><div class="v">${d.since ? t.dm(Date.parse(d.since)) : "—"}</div><div class="s">kapitał ${num(d.capital)} $ · ${d.maxPerTicker || "∞"} poz. / spółkę</div></div>
</div>`;

function track(p) {
  if (!p.slPx || !p.tpPx || p.price === null) return `<span class="dim">${p.status === "oczekuje" ? "wejście na otwarciu" : "—"}</span>`;
  const f = x => Math.max(0, Math.min(1, (x - p.slPx) / (p.tpPx - p.slPx)));
  return `<span class="track" title="SL ${p.slPx} · wejście ${p.entry} · teraz ${p.price} · TP ${p.tpPx}"><b style="left:${100 * f(p.entry)}%"></b><i style="left:calc(${100 * f(p.price)}% - 1px)"></i></span>`;
}

function openTable(d) {
  const L = d.open || [];
  if (!L.length) return `<p class="empty">${d.fallback ? "lista pozycji pojawi się, gdy Apps Script zacznie wysyłać vi.json" : "brak otwartych pozycji"}</p>`;
  return `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>#</th><th>spółka</th><th>kier.</th><th class="desk-only">strategia</th><th class="desk-only">wejście</th>
    <th class="num desk-only">cena wej.</th><th class="num desk-only">teraz</th><th class="num">wynik</th><th class="num desk-only">$</th><th class="desk-only">SL ─ TP</th><th class="num desk-only">świec</th></tr></thead><tbody>` +
    L.map(p => `<tr><td class="dim">${p.no}</td><td><b>${esc(p.sym)}</b></td><td>${p.dir === "long" ? "▲ long" : "▼ short"}</td><td class="desk-only">${esc(p.id)}</td>
      <td class="desk-only">${p.entryAt ? esc(p.entryAt.slice(5)) : `<span class="am">oczekuje</span>`}</td><td class="num desk-only">${num(p.entry, 2)}</td><td class="num desk-only">${num(p.price, 2)}</td>
      <td class="num ${cls(p.retPct)}">${p.status === "oczekuje" ? "—" : sgn(p.retPct, 2) + "%"}</td><td class="num desk-only ${cls(p.usd)}">${p.status === "oczekuje" ? "" : usd(p.usd)}</td>
      <td class="desk-only">${track(p)}</td><td class="num desk-only">${p.bars}${p.maxBars ? `/${p.maxBars}` : ""}</td></tr>`).join("") + `</tbody></table></div>`;
}

function closedTable(d) {
  const L = d.closed || [];
  if (!L.length) return `<p class="empty">brak zamkniętych transakcji</p>`;
  return `<div class="tbl-wrap scroll"><table class="tbl"><thead><tr><th>#</th><th>spółka</th><th>kier.</th><th>strategia</th><th>wejście</th><th>wyjście</th><th>powód</th><th class="num">wynik</th><th class="num">$</th><th class="num">świec</th></tr></thead><tbody>` +
    L.map(p => `<tr><td class="dim">${p.no}</td><td><b>${esc(p.sym)}</b></td><td>${p.dir === "long" ? "▲" : "▼"}</td><td>${esc(p.id)}</td><td>${esc((p.entryAt || "").slice(5))}</td>
      <td>${esc((p.exitAt || "").slice(5))}</td><td><span class="tag ${p.kind === "TP" ? "cy" : ""}">${esc(p.kind)}</span></td><td class="num ${cls(p.retPct)}">${sgn(p.retPct, 2)}%</td>
      <td class="num ${cls(p.usd)}">${usd(p.usd)}</td><td class="num">${p.bars}</td></tr>`).join("") + `</tbody></table></div>`;
}

function signals(d) {
  const L = (d.signals || []).slice(0, 14);
  if (!L.length) return `<p class="empty">brak sygnałów</p>`;
  return `<ul class="log" style="max-height:330px">` + L.map(s => `<li><span class="t">${esc((s.at || "").slice(5))}</span><span class="src">${s.fired.length || "·"}</span>` +
    `<span class="m">${s.fired.length ? s.fired.map(f => `<b>${esc(f[1])}</b> <span class="dim">${esc(f[0])}</span>`).join(" · ") : `<span class="dim">bez sygnału</span>`}</span></li>`).join("") + `</ul>`;
}

function strategyRows(d) {
  const bt = Object.fromEntries((store.get("strategies") || []).map(s => [s.id, s]));
  const live = Object.fromEntries((d.strategies || []).map(s => [s.id, s]));
  const ids = Array.from(new Set(Object.keys(live).concat(Object.keys(bt))));
  return ids.map(id => Object.assign({ id }, bt[id] ? { bt: bt[id] } : {}, { live: live[id] || null }));
}

function strategies(d) {
  let R = strategyRows(d);
  const n = { all: R.length, vi: R.filter(r => r.live && r.live.forVI).length, live: R.filter(r => r.live && r.live.closed).length };
  if (ui.filter === "vi") R = R.filter(r => r.live && r.live.forVI);
  if (ui.filter === "live") R = R.filter(r => r.live && r.live.closed);
  if (ui.q) { const q = ui.q.toLowerCase(); R = R.filter(r => (r.id + " " + ((r.bt && r.bt.desc) || (r.live && r.live.desc) || "")).toLowerCase().includes(q)); }
  const key = { pf: r => -(r.bt ? r.bt.pf_w ?? r.bt.combined_pf ?? 0 : 0), live: r => -(r.live ? r.live.usd || 0 : 0),
                prio: r => (r.live && r.live.priority) || 1e6 }[ui.sort];
  R.sort((a, b) => key(a) - key(b));
  const chip = (f, lab) => `<button class="chip" type="button" data-f="${f}" aria-pressed="${ui.filter === f}">${lab} ${n[f]}</button>`;
  const sortb = (s, lab) => `<button class="chip" type="button" data-s="${s}" aria-pressed="${ui.sort === s}">${lab}</button>`;
  return `<div class="filters">${chip("vi", "for VI")}${chip("live", "z wynikiem na żywo")}${chip("all", "wszystkie")}
      <span class="dim" style="margin:0 6px">sortuj:</span>${sortb("pf", "PF backtest")}${sortb("live", "$ na żywo")}${sortb("prio", "pierwszeństwo")}
      <input class="search" type="search" placeholder="szukaj: ID, AAPL, EMA…" value="${esc(ui.q)}" data-q></div>
    <div class="tbl-wrap scroll" style="max-height:560px"><table class="tbl"><thead><tr><th>ID</th><th>VI</th><th class="num">pierw.</th><th>reguła</th>
      <th class="num">PF</th><th class="num">trans.</th><th class="num">skut.</th><th class="num">SL/TP</th><th class="num">na żywo</th><th class="num">śr. %</th><th class="num">$</th></tr></thead><tbody>` +
    (R.map(r => { const b = r.bt || {}, l = r.live || {};
      return `<tr><td>${esc(r.id)}</td><td>${l.forVI ? `<span class="tag am">VI</span>` : ""}</td><td class="num">${l.priority ?? ""}</td>
        <td class="wrap">${esc(b.desc || l.desc || "—")}</td><td class="num">${b.pf_w !== undefined ? num(b.pf_w, 2) : "—"}</td><td class="num">${b.trades ?? "—"}</td>
        <td class="num">${b.win_rate !== undefined ? pct(b.win_rate) : "—"}</td><td class="num">${b.sl !== undefined ? `${b.sl}/${b.tp}%` : ""}</td>
        <td class="num">${l.closed ? `${l.closed}${l.open ? ` +${l.open}` : ""}` : l.open ? `+${l.open}` : ""}</td>
        <td class="num ${cls(l.avgPct)}">${l.avgPct === null || l.avgPct === undefined ? "" : sgn(l.avgPct, 2)}</td><td class="num ${cls(l.usd)}">${l.closed ? usd(l.usd) : ""}</td></tr>`; }).join("") ||
      `<tr><td colspan="11" class="dim">brak strategii dla tego filtra</td></tr>`) + `</tbody></table></div>
    <p class="note">PF — PF ważony z poszukiwania (grupa główna + skarbiec) · „na żywo” — zamknięte (+ otwarte) transakcje wirtualnego inwestora · + otwarte.</p>`;
}

function tickers(d) {
  const st = store.get("state");
  const list = ((st && st.instruments) || []).filter(i => i.group === "main" || i.group === "proof");
  if (!list.length) return `<p class="empty">brak listy spółek</p>`;
  const pos = Object.fromEntries((d.open || []).map(p => [p.sym, p]));
  const sig = {}, res = {};
  (d.signals || []).forEach(s => s.fired.forEach(f => { sig[f[1]] = (sig[f[1]] || 0) + 1; }));
  (d.closed || []).forEach(p => { res[p.sym] = (res[p.sym] || 0) + p.usd; });
  return `<div class="matrix">` + list.map(i => { const p = pos[i.symbol];
    return `<div class="cell${p ? " pos" : ""}" title="${esc(i.symbol)} · ${esc(i.last)} · sygnałów (5 sesji): ${sig[i.symbol] || 0}${p ? ` · pozycja #${p.no} ${p.dir}` : ""}">` +
      `<b>${esc(i.symbol)}</b><span class="q">${num(i.lastClose, 2)}</span><span class="q">${sig[i.symbol] ? `⚡${sig[i.symbol]} ` : ""}${res[i.symbol] !== undefined ? `<span class="${cls(res[i.symbol])}">${usd(res[i.symbol])}</span>` : ""}` +
      `${p && p.status === "otwarta" ? ` <span class="${cls(p.retPct)}">${sgn(p.retPct, 1)}%</span>` : ""}</span></div>`; }).join("") +
    `</div><p class="note">▪ = otwarta pozycja · ⚡ = sygnały w ostatnich 5 sesjach · $ = wynik zamkniętych transakcji (ostatnie 150).</p>`;
}

/** Cały widok inwestora z dokumentu w formacie vi.json. opts.strategies — tabela strategii akcji. */
export function renderInvestor(d, opts = {}) {
  const s = d.summary;
  return `<div class="grid">
    <div class="pane c12 hero"><h2>${esc(opts.title || "wirtualny inwestor")}<span class="dim">ostatnia świeca ${esc(d.lastCandlePL || "—")}</span></h2>
      <span class="act">vi.json ${d.generatedAt ? age((Date.now() - Date.parse(d.generatedAt)) / 1000) + " temu" : ""}</span>${reads(d, s)}</div>
    <div class="pane c8"><h2>krzywa wyniku<span class="dim">skumulowane $ po zamkniętych transakcjach</span></h2><svg class="mini" data-eq></svg></div>
    <div class="pane c4"><h2>sygnały<span class="dim">ostatnie świece</span></h2>${signals(d)}</div>
    <div class="pane c12"><h2>otwarte pozycje<span class="dim">${s.open} otwartych · ${s.pending} oczekuje</span></h2>${openTable(d)}</div>
    ${opts.strategies ? `<div class="pane c12 desk-only" data-strat><h2>strategie</h2>${strategies(d)}</div>` : ""}
    <div class="pane c7 desk-only"><h2>zamknięte transakcje<span class="dim">ostatnie ${(d.closed || []).length}</span></h2>${closedTable(d)}</div>
    ${opts.tickers ? `<div class="pane c5 desk-only"><h2>spółki<span class="dim">53 handlowane</span></h2>${tickers(d)}</div>` : ""}
  </div>`;
}

export function mountInvestor(el, d) {
  const svg = el.querySelector("[data-eq]");
  if (svg) equity(svg, d.equity || []);
  const box = el.querySelector("[data-strat]");
  if (!box) return;
  const redraw = () => {
    const q = box.querySelector("[data-q]"), focused = document.activeElement === q, pos = q ? q.selectionStart : 0;
    box.innerHTML = `<h2>strategie</h2>${strategies(d)}`;
    if (focused) { const n = box.querySelector("[data-q]"); n.focus(); n.setSelectionRange(pos, pos); }
  };
  box.addEventListener("click", e => {
    const b = e.target.closest("button[data-f], button[data-s]");
    if (!b) return;
    if (b.dataset.f) ui.filter = b.dataset.f;
    if (b.dataset.s) ui.sort = b.dataset.s;
    redraw();
  });
  box.addEventListener("input", e => { if (e.target.matches("[data-q]")) { ui.q = e.target.value; redraw(); } });
}

/** Zastępczy dokument z podsumowania w state.json (zanim Apps Script zacznie wysyłać vi.json). */
function fallbackDoc(v) {
  return { since: v.since, capital: 100000, stake: 100, costPct: 0.005, maxPerTicker: 1, lastCandlePL: null,
    summary: { closed: v.closed, open: v.open, pending: 0, avgPct: v.avgPct, ci95Pct: v.ci95Pct, realizedUsd: v.sumUsd, unrealizedUsd: null,
               tpShare: v.tpShare, exits: { TP: Math.round((v.tpShare || 0) * v.closed), SL: "?", FC: "?", LIMIT: "?" }, medianBars: null, costsUsd: null },
    open: [], closed: [], equity: [], strategies: [], signals: [], fallback: true };
}

export default {
  id: "inwestor", title: "inwestor",
  render(el) {
    const vi = store.get("vi"), st = store.get("state");
    const q = el.querySelector("[data-q]");
    if (q && document.activeElement === q) return;          // nie przerywamy pisania w wyszukiwarce
    if (!vi && !(st && st.vi)) { el.innerHTML = `<div class="pane"><h2>wirtualny inwestor</h2><p class="empty">czekam na dane…</p></div>`; return; }
    const d = vi || fallbackDoc(st.vi);
    if (!vi && ui.filter === "vi") ui.filter = "all";          // bez vi.json nie wiemy, które są „for VI”
    el.innerHTML = (vi ? "" : `<div class="pane flat" style="margin-bottom:14px"><h2>uwaga</h2><p class="empty">Pełne dane (pozycje, transakcje, wyniki strategii) pojawią się po pierwszej świecy sesji po wdrożeniu 1.28 — Apps Script zacznie wysyłać <b>telemetry/vi.json</b>. Na razie: podsumowanie z telemetry/state.json.</p></div>`) +
      renderInvestor(d, { strategies: true, tickers: true }) +
      `<p class="note">${nyseOpen() ? "sesja NYSE trwa — inwestor przelicza się ok. 45 s po zamknięciu każdej świecy" : "NYSE zamknięta — kolejne przeliczenie po pierwszej świecy następnej sesji"}.</p>`;
    mountInvestor(el, d);
  },
};
