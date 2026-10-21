// IA 4 — zakładka FX → Powrót.v2: paper trading strategii FX-POWRÓT v2 (Apps Script, PowrotV2.gs → telemetry/pv2.json).
// Wykres każdej pary: świece 1h, gdzie były transakcje (sygnał ▼, wejście ●, wyjście ■, TP - - -, baza ···).
// Wersja projektu: 1.59 (2026-10-21)

import { store, num, pct, usd, sgn, esc, age, t, cls, pref } from "../core.js";
import { help } from "../help.js";
import { renderHistory, mountHistory, renderGallery, mountGallery, setOnLoaded, index } from "./pv2hist.js";

const MODES = [["przeglad", "przegląd (na żywo)"], ["historia", "historia — przewijanie"], ["galeria", "galeria transakcji"]];
let mode = pref.get("pv2.mode", "przeglad");

/** Cały widok Powrót.v2 (fx.js): prefix — przełącznik pod-zakładek FX. */
export function pv2View(el, prefix) {
  const again = () => pv2View(el, prefix);
  setOnLoaded(() => { if (el.isConnected && !el.hidden && (location.hash.split("/")[1] || "") === "powrot") again(); });
  const bar = `<div class="pv2-modes">${MODES.map(([k, lab]) => `<button type="button" class="chip" data-mode="${k}" aria-pressed="${k === mode}">${lab}</button>`).join(" ")}</div>`;
  if (mode === "historia") { index(); el.innerHTML = prefix + bar + renderHistory(); mountHistory(el, again); }
  else if (mode === "galeria") { el.innerHTML = prefix + bar + renderGallery(); mountGallery(el, again, () => { mode = "historia"; pref.set("pv2.mode", mode); again(); window.scrollTo(0, 0); }); }
  else { el.innerHTML = prefix + bar + renderPv2(el); mountPv2(el); }
  el.querySelectorAll("[data-mode]").forEach(b => b.addEventListener("click", () => { mode = b.dataset.mode; pref.set("pv2.mode", mode); again(); }));
}

const H = 3600e3;
const px = (p, v) => v === null || v === undefined || !isFinite(v) ? "—" :
  v.toLocaleString("pl-PL", { minimumFractionDigits: /JPY$/.test(p) ? 3 : 5, maximumFractionDigits: /JPY$/.test(p) ? 3 : 5 });
const KIND = k => !k ? "" : k === "TP" ? "TP" : k.startsWith("czas") ? "limit 60 św." : k;

function hero(d) {
  const s = d.summary || {}, pr = d.params || {};
  const eq = (s.cash ?? 0) + (s.unrealized ?? 0), res = eq - (pr.capital || 0);
  const gen = d.generatedAt ? (Date.now() - Date.parse(d.generatedAt)) / 1000 : null;
  return `<div class="reads">
    <div class="read"><div class="k">saldo (zamknięte)</div><div class="v">${num(s.cash, 2)} $</div><div class="s">start ${num(pr.capital, 0)} $ · od ${pr.startedAt ? esc(t.dhm(pr.startedAt * 1000)) : "—"}</div></div>
    <div class="read"><div class="k">wynik z otwartymi</div><div class="v ${cls(res)}">${usd(res)}</div><div class="s">${pr.capital ? sgn(100 * res / pr.capital, 2) + "%" : ""} · otwarte ${usd(s.unrealized)}</div></div>
    <div class="read"><div class="k">pozycje</div><div class="v">${s.open ?? 0} otw. · ${s.pending ?? 0} oczek.</div><div class="s">depozyt ${pct(pr.pct)} salda · 1:${pr.lev ?? "—"}</div></div>
    <div class="read"><div class="k">zamknięte</div><div class="v">${s.closed ?? 0}</div><div class="s">TP ${s.tp ?? 0} · średnio ${s.avgPct === null || s.avgPct === undefined ? "—" : sgn(s.avgPct, 3) + "%"}</div></div>
    <div class="read"><div class="k">ostatnia świeca</div><div class="v">${d.lastT ? t.hm(d.lastT * 1000 + H) : "—"}</div><div class="s">zamknięcie · pv2.json ${gen === null ? "—" : age(gen) + " temu"}</div></div>
    <div class="read"><div class="k">maile</div><div class="v">${pr.mails ? "włączone" : "wyłączone"}</div><div class="s">sygnał, anulowanie, limit 60 świec${pr.active === false ? " · inwestor wstrzymany" : ""}</div></div>
  </div>`;
}

/** Wykres pary: oś po świecach (weekend bez dziury), transakcje symulacji (cyjan) i inwestora (bursztyn). */
function chart(svg, p, P, sims, live) {
  const W = svg.clientWidth || 560, Hh = svg.clientHeight || 260;
  const C = P.candles || [];
  if (!C.length) { svg.innerHTML = `<text x="8" y="20">brak świec</text>`; return; }
  const m = { l: 4, r: 64, t: 10, b: 20 };
  const n = C.length, cw = (W - m.l - m.r) / n;
  const idx = new Map(C.map((c, i) => [c[0], i]));
  const xs = i => m.l + (i + 0.5) * cw;
  let lo = Infinity, hi = -Infinity;
  C.forEach(c => { lo = Math.min(lo, c[3]); hi = Math.max(hi, c[2]); });
  const all = sims.concat(live);
  all.forEach(tr => { [tr.tp, tr.base].forEach(v => { if (v !== null && v !== undefined && (idx.has(tr.entryT) || idx.has(tr.sigT))) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }); });
  const pad = (hi - lo) * 0.05 || hi * 0.001; lo -= pad; hi += pad;
  const ys = v => m.t + (hi - v) / (hi - lo) * (Hh - m.t - m.b);
  let s = "";
  for (let j = 0; j <= 4; j++) {
    const v = lo + (hi - lo) * j / 4, y = ys(v);
    s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}" stroke="var(--grid)"/><text x="${W - m.r + 5}" y="${y + 4}">${px(p, v)}</text>`;
  }
  let lastDay = "";
  C.forEach((c, i) => {
    const x = xs(i), col = c[4] >= c[1] ? "var(--up)" : "var(--down)", bw = Math.max(1, cw * 0.62);
    const yo = ys(c[1]), yc = ys(c[4]);
    s += `<line x1="${x}" x2="${x}" y1="${ys(c[2])}" y2="${ys(c[3])}" stroke="${col}" opacity=".8"/>` +
         `<rect x="${x - bw / 2}" y="${Math.min(yo, yc)}" width="${bw}" height="${Math.max(1, Math.abs(yc - yo))}" fill="${col}" opacity=".8"/>`;
    const day = t.dm(c[0] * 1000);
    if (day !== lastDay && t.hour(c[0] * 1000) < 3) {
      if (i > 2 && i < n - 3) s += `<line x1="${x}" x2="${x}" y1="${m.t}" y2="${Hh - m.b}" stroke="var(--grid)" stroke-dasharray="1 4"/><text x="${x + 2}" y="${Hh - 6}">${day}</text>`;
      lastDay = day;
    }
  });
  const iOf = (tt, dflt) => idx.has(tt) ? idx.get(tt) : dflt;
  const draw = (tr, liveTr) => {
    const iS = iOf(tr.sigT, null), iE = tr.entryT ? iOf(tr.entryT, tr.entryT < C[0][0] ? 0 : null) : null;
    const open = !tr.exitT || tr.status === "otwarta" || tr.kind === "otwarta";
    const iX = open ? n - 1 : iOf(tr.exitT, tr.exitT > C[n - 1][0] ? n - 1 : null);
    if (iS === null && iE === null && iX === null) return "";
    const good = (tr.ret ?? 0) > 0, colR = open ? "var(--amber)" : good ? "var(--up)" : "var(--down)";
    const base = liveTr ? "var(--amber)" : "var(--cyan)", op = liveTr ? 1 : 0.75, wd = liveTr ? 2 : 1.2;
    const tip = `${p} ${liveTr ? "inwestor" : "symulacja"} · sygnał ${t.dhm(tr.sigT * 1000)} · wejście ${px(p, tr.entry)} · TP ${px(p, tr.tp)}` +
      (open ? " · otwarta" : ` · wyjście ${px(p, tr.exit)} (${KIND(tr.kind)}) · ${sgn(tr.ret, 3)}%`);
    let g = `<g opacity="${op}"><title>${esc(tip)}</title>`;
    if (iS !== null) {
      const c = C[iS];
      g += `<path d="M${xs(iS) - 4},${ys(c[2]) - 9} h8 l-4,6 z" fill="${base}"/>`;                   // ▼ świeca sygnału
    }
    if (iE !== null && iX !== null) {
      const x0 = xs(iE), x1 = xs(iX);
      if (tr.base !== null && tr.base !== undefined) g += `<line x1="${x0}" x2="${x1}" y1="${ys(tr.base)}" y2="${ys(tr.base)}" stroke="var(--dim)" stroke-dasharray="1 3"/>`;
      if (tr.tp !== null && tr.tp !== undefined) g += `<line x1="${x0}" x2="${Math.max(x1, x0 + 6)}" y1="${ys(tr.tp)}" y2="${ys(tr.tp)}" stroke="var(--up)" stroke-dasharray="4 3" stroke-width="${wd * 0.8}"/>`;
      const yE = ys(tr.entry), yX = ys(open ? C[n - 1][4] : tr.exit);
      g += `<rect x="${x0}" y="${Math.min(yE, yX)}" width="${Math.max(2, x1 - x0)}" height="${Math.max(1, Math.abs(yX - yE))}" fill="${colR}" opacity=".10"/>`;
      g += `<line x1="${x0}" x2="${x1}" y1="${yE}" y2="${yX}" stroke="${colR}" stroke-width="${wd}"/>`;
      g += `<circle cx="${x0}" cy="${yE}" r="${liveTr ? 4 : 3}" fill="${base}" stroke="var(--void)"/>`;
      if (!open) g += `<rect x="${x1 - 3.5}" y="${yX - 3.5}" width="7" height="7" fill="${colR}" stroke="var(--void)"/>`;
      else g += `<text x="${x1 - 2}" y="${yE - 7}" text-anchor="end" style="fill:var(--amber)">otwarta</text>`;
    }
    return g + `</g>`;
  };
  sims.forEach(tr => { s += draw(tr, false); });
  live.forEach(tr => { s += draw(tr, true); });
  const lc = C[n - 1][4];
  s += `<line x1="${xs(n - 1)}" x2="${W - m.r}" y1="${ys(lc)}" y2="${ys(lc)}" stroke="var(--amber)" opacity=".6"/>` +
       `<text x="${W - m.r + 5}" y="${ys(lc) + 4}" style="fill:var(--amber)">${px(p, lc)}</text>`;
  svg.setAttribute("viewBox", `0 0 ${W} ${Hh}`);
  svg.innerHTML = s;
}

function pairPane(d, p) {
  const live = (d.positions || []).filter(q => q.pair === p && q.status !== "anulowana");
  const sims = (d.sim || []).filter(q => q.pair === p);
  const opn = live.find(q => q.status === "otwarta" || q.status === "oczekuje");
  const closed = live.filter(q => q.status === "zamknięta"), sum = closed.reduce((a, q) => a + (q.pnl || 0), 0);
  return `<div class="pane c6"><h2>${p}<span class="dim">${opn ? `<span class="am">${opn.status}</span> · TP ${px(p, opn.tp)} · ` : ""}inwestor: ${closed.length} zamkn. ${closed.length ? usd(sum) : ""} · symulacja: ${sims.length}</span></h2>
    <svg class="chart pv2" data-pv2="${p}" style="height:250px"></svg></div>`;
}

function trades(d) {
  const P = (d.positions || []).slice().sort((a, b) => b.no - a.no);
  if (!P.length) return `<p class="empty">jeszcze żadnej transakcji — inwestor liczy od ${d.params && d.params.startedAt ? esc(t.dhm(d.params.startedAt * 1000)) : "startu"}; sygnał przychodzi średnio co 2–3 dni (na 10 parach)</p>`;
  return `<div class="tbl-wrap scroll" style="max-height:420px"><table class="tbl"><thead><tr><th>nr</th><th>para</th><th>status</th><th>sygnał</th><th>wejście</th>
    <th class="num">cena wejścia</th><th class="num">TP</th><th class="num">depozyt</th><th class="num">lot</th><th>wyjście</th><th class="num">cena wyjścia</th><th>powód</th>
    <th class="num">świec</th><th class="num">wynik %</th><th class="num">wynik $</th><th>zamknąć najpóźniej</th></tr></thead><tbody>` +
    P.map(q => `<tr${q.status === "otwarta" ? ' class="sel"' : ""}><td>${q.no || ""}</td><td><b>${q.pair}</b></td><td>${esc(q.status)}</td><td>${q.sigT ? t.short(q.sigT * 1000) : ""}</td>
      <td>${q.entryT ? t.short(q.entryT * 1000) : ""}</td><td class="num">${px(q.pair, q.entry)}</td><td class="num">${px(q.pair, q.tp)}</td>
      <td class="num">${num(q.margin, 2)} $</td><td class="num">${q.lots === null ? "—" : num(q.lots, 4)}</td><td>${q.status === "zamknięta" && q.exitT ? t.short(q.exitT * 1000 + H) : ""}</td>
      <td class="num">${q.status === "zamknięta" ? px(q.pair, q.exit) : ""}</td><td>${esc(KIND(q.kind))}</td><td class="num">${q.bars ?? ""}</td>
      <td class="num ${cls(q.ret)}">${q.ret === null ? "—" : sgn(q.ret, 3) + "%"}</td><td class="num ${cls(q.pnl)}">${q.pnl === null ? "" : usd(q.pnl)}</td>
      <td>${q.deadlineT && q.status !== "zamknięta" ? t.short(q.deadlineT * 1000) : ""}</td></tr>`).join("") + `</tbody></table></div>`;
}

export function renderPv2(el) {
  const d = store.get("pv2");
  if (!d || !d.pairs) {
    const m = store.meta.pv2;
    return `<div class="grid"><div class="pane c12"><h2>Powrót.v2<span class="dim">paper trading FX-POWRÓT v2</span></h2>${help("fx.pv2")}
      <p class="empty">${m && m.err ? esc(m.err) + " — " : ""}czekam na <b>telemetry/pv2.json</b>: wysyła go Apps Script (plik PowrotV2.gs, wersja 1.53) po każdej nowej świecy FX.</p></div></div>`;
  }
  const pairs = Object.keys(d.pairs);
  return `<div class="grid">
    <div class="pane c12 hero"><h2>Powrót.v2 investor<span class="dim">short po gwałtownym wzroście · TP w połowie drogi do ceny sprzed wzrostu · bez SL · najwyżej 60 świec</span></h2>${help("fx.pv2")}${hero(d)}
      <div class="legend"><span><i style="background:var(--amber)"></i>transakcja inwestora</span><span><i style="background:var(--cyan)"></i>symulacja tych samych reguł (ostatnie ${(d.pairs[pairs[0]].candles || []).length} świec)</span>
        <span>▼ świeca sygnału</span><span>● wejście (short)</span><span>■ wyjście — zielone zysk, czerwone strata</span><span><i style="background:var(--up);height:2px"></i>TP</span><span><i style="background:var(--dim);height:1px"></i>baza (cena sprzed wzrostu)</span></div></div>
    ${pairs.map(p => pairPane(d, p)).join("")}
    <div class="pane c12"><h2>transakcje inwestora<span class="dim">jak w arkuszu Powrót.v2.Investor</span></h2>${help("fx.pv2.trades")}${trades(d)}</div>
  </div>`;
}

export function mountPv2(el) {
  const d = store.get("pv2");
  if (!d || !d.pairs) return;
  el.querySelectorAll("svg[data-pv2]").forEach(svg => {
    const p = svg.dataset.pv2;
    chart(svg, p, d.pairs[p], (d.sim || []).filter(q => q.pair === p),
      (d.positions || []).filter(q => q.pair === p && q.status !== "anulowana" && (q.entryT || q.status === "oczekuje")));
  });
}
