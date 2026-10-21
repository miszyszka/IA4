// IA 4 — zakładka FX → SMA 42/23: paper trading „zawsze w pozycji” (Apps Script, SmaKrzyz.gs → telemetry/sma.json).
// Wykres każdej pary: świece 1h, SMA42 i SMA23, pozycje (▲ long / ▼ short przy wejściu, linia do wyjścia).
// Wersja projektu: 1.60 (2026-10-21)

import { store, num, pct, usd, sgn, esc, age, t, cls } from "../core.js";
import { help } from "../help.js";

const H = 3600e3;
const px = (p, v) => v === null || v === undefined || !isFinite(v) ? "—" :
  v.toLocaleString("pl-PL", { minimumFractionDigits: /JPY$/.test(p) ? 3 : 5, maximumFractionDigits: /JPY$/.test(p) ? 3 : 5 });
const DIR = d => d > 0 ? "long" : "short";

function hero(d) {
  const s = d.summary || {}, pr = d.params || {};
  const eq = (s.cash ?? 0) + (s.unrealized ?? 0), res = eq - (pr.capital || 0);
  const gen = d.generatedAt ? (Date.now() - Date.parse(d.generatedAt)) / 1000 : null;
  return `<div class="reads">
    <div class="read"><div class="k">saldo (zamknięte)</div><div class="v">${num(s.cash, 2)} $</div><div class="s">start ${num(pr.capital, 0)} $ · od ${pr.startedAt ? esc(t.dhm(pr.startedAt * 1000)) : "—"}</div></div>
    <div class="read"><div class="k">wynik z otwartymi</div><div class="v ${cls(res)}">${usd(res)}</div><div class="s">${pr.capital ? sgn(100 * res / pr.capital, 2) + "%" : ""} · otwarte ${usd(s.unrealized)}</div></div>
    <div class="read"><div class="k">pozycje</div><div class="v">${s.open ?? 0} otwarte</div><div class="s">long ${s.long ?? 0} · short ${s.short ?? 0}${s.pending ? ` · zmiana na open: ${s.pending}` : ""}</div></div>
    <div class="read"><div class="k">zamknięte</div><div class="v">${s.closed ?? 0}</div><div class="s">zyskownych ${s.wins ?? 0}${s.closed ? ` (${Math.round(100 * s.wins / s.closed)}%)` : ""}</div></div>
    <div class="read"><div class="k">wartość pozycji</div><div class="v">${pct(pr.pct)} salda</div><div class="s">na parę · depozyt przy 1:${pr.lev ?? "—"}</div></div>
    <div class="read"><div class="k">ostatnia świeca</div><div class="v">${d.lastT ? t.hm(d.lastT * 1000 + H) : "—"}</div><div class="s">zamknięcie · sma.json ${gen === null ? "—" : age(gen) + " temu"}</div></div>
  </div>`;
}

/** Wykres pary: świece (oś po świecach), SMA42 (bursztyn) i SMA23 (cyjan), transakcje symulacji i inwestora. */
function chart(svg, p, P, sims, live) {
  const W = svg.clientWidth || 560, Hh = svg.clientHeight || 260;
  const C = P.candles || [];
  if (!C.length) { svg.innerHTML = `<text x="8" y="20">brak świec</text>`; return; }
  const m = { l: 4, r: 64, t: 10, b: 20 }, n = C.length, cw = (W - m.l - m.r) / n;
  const idx = new Map(C.map((c, i) => [c[0], i])), xs = i => m.l + (i + 0.5) * cw;
  let lo = Infinity, hi = -Infinity;
  C.forEach(c => { lo = Math.min(lo, c[3]); hi = Math.max(hi, c[2]); });
  const pad = (hi - lo) * 0.05 || hi * 0.001; lo -= pad; hi += pad;
  const ys = v => m.t + (hi - v) / (hi - lo) * (Hh - m.t - m.b);
  let s = "";
  for (let j = 0; j <= 4; j++) {
    const v = lo + (hi - lo) * j / 4, y = ys(v);
    s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}" stroke="var(--grid)"/><text x="${W - m.r + 5}" y="${y + 4}">${px(p, v)}</text>`;
  }
  // tło: kierunek pozycji symulacji (zielone long, czerwone short)
  sims.forEach(tr => {
    const i0 = idx.has(tr.entryT) ? idx.get(tr.entryT) : (tr.entryT < C[0][0] ? 0 : null);
    const i1 = tr.open || !tr.exitT ? n - 1 : (idx.has(tr.exitT) ? idx.get(tr.exitT) : null);
    if (i0 === null || i1 === null) return;
    s += `<rect x="${xs(i0) - cw / 2}" y="${m.t}" width="${Math.max(1, (i1 - i0) * cw)}" height="${Hh - m.t - m.b}" fill="${tr.dir > 0 ? "var(--up)" : "var(--down)"}" opacity=".05"/>`;
  });
  let lastDay = "";
  C.forEach((c, i) => {
    const x = xs(i), col = c[4] >= c[1] ? "var(--up)" : "var(--down)", bw = Math.max(1, cw * 0.62), yo = ys(c[1]), yc = ys(c[4]);
    s += `<line x1="${x}" x2="${x}" y1="${ys(c[2])}" y2="${ys(c[3])}" stroke="${col}" opacity=".7"/>` +
         `<rect x="${x - bw / 2}" y="${Math.min(yo, yc)}" width="${bw}" height="${Math.max(1, Math.abs(yc - yo))}" fill="${col}" opacity=".7"/>`;
    const day = t.dm(c[0] * 1000);
    if (day !== lastDay && t.hour(c[0] * 1000) < 3) {
      if (i > 2 && i < n - 3) s += `<line x1="${x}" x2="${x}" y1="${m.t}" y2="${Hh - m.b}" stroke="var(--grid)" stroke-dasharray="1 4"/><text x="${x + 2}" y="${Hh - 6}">${day}</text>`;
      lastDay = day;
    }
  });
  const line = (k, col) => {
    let d = "";
    C.forEach((c, i) => { if (c[k] !== null && c[k] !== undefined) d += (d ? "L" : "M") + xs(i).toFixed(1) + "," + ys(c[k]).toFixed(1); });
    return d ? `<path d="${d}" fill="none" stroke="${col}" stroke-width="1.6"/>` : "";
  };
  s += line(5, "var(--amber)") + line(6, "var(--cyan)");
  const draw = (tr, liveTr) => {
    const i0 = idx.has(tr.entryT) ? idx.get(tr.entryT) : null;
    const open = tr.open || tr.status === "otwarta" || !tr.exitT;
    const i1 = open ? n - 1 : (idx.has(tr.exitT) ? idx.get(tr.exitT) : null);
    if (i0 === null && i1 === null) return "";
    const colR = open ? "var(--amber)" : (tr.ret ?? 0) > 0 ? "var(--up)" : "var(--down)";
    const tip = `${p} ${liveTr ? "inwestor" : "symulacja"} · ${DIR(tr.dir)} · wejście ${tr.entryT ? t.dhm(tr.entryT * 1000) : ""} ${px(p, tr.entry)}` +
      (open ? " · otwarta" : ` · wyjście ${px(p, tr.exit)} · ${sgn(tr.ret, 3)}%`);
    let g = `<g opacity="${liveTr ? 1 : 0.7}"><title>${esc(tip)}</title>`;
    if (i0 !== null) {
      const x0 = xs(i0), y0 = ys(tr.entry), up = tr.dir > 0;
      g += `<path d="M${x0 - 5},${up ? y0 + 9 : y0 - 9} h10 l-5,${up ? -7 : 7} z" fill="${liveTr ? "var(--amber)" : up ? "var(--up)" : "var(--down)"}" stroke="var(--void)" stroke-width=".5"/>`;
      if (i1 !== null) {
        const yX = ys(open ? C[n - 1][4] : tr.exit);
        g += `<line x1="${x0}" x2="${xs(i1)}" y1="${y0}" y2="${yX}" stroke="${colR}" stroke-width="${liveTr ? 2 : 1.1}" stroke-dasharray="${liveTr ? "" : "3 2"}"/>`;
        if (!open) g += `<rect x="${xs(i1) - 3}" y="${yX - 3}" width="6" height="6" fill="${colR}" stroke="var(--void)"/>`;
      }
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

/** Saldo po każdym zamknięciu (S.equity) — prosta linia. */
function equity(svg, d) {
  const E = (d.equity || []).slice(), cap = (d.params || {}).capital || 0;
  const W = svg.clientWidth || 900, Hh = svg.clientHeight || 160, m = { l: 6, r: 70, t: 10, b: 18 };
  if (d.params && d.params.startedAt) E.unshift([d.params.startedAt, cap]);
  if (E.length < 2) { svg.innerHTML = `<text x="8" y="20">saldo pojawi się po pierwszych zamknięciach</text>`; svg.setAttribute("viewBox", `0 0 ${W} ${Hh}`); return; }
  const t0 = E[0][0], t1 = E[E.length - 1][0] || t0 + 1;
  let lo = Math.min(cap, ...E.map(e => e[1])), hi = Math.max(cap, ...E.map(e => e[1]));
  const pad = (hi - lo) * 0.1 || 1; lo -= pad; hi += pad;
  const xs = tt => m.l + (tt - t0) / Math.max(1, t1 - t0) * (W - m.l - m.r), ys = v => m.t + (hi - v) / (hi - lo) * (Hh - m.t - m.b);
  let s = `<line x1="${m.l}" x2="${W - m.r}" y1="${ys(cap)}" y2="${ys(cap)}" stroke="var(--dim)" stroke-dasharray="3 3"/><text x="${W - m.r + 5}" y="${ys(cap) + 4}">${num(cap, 0)} $</text>`;
  s += `<path d="${E.map((e, i) => (i ? "L" : "M") + xs(e[0]).toFixed(1) + "," + ys(e[1]).toFixed(1)).join("")}" fill="none" stroke="var(--cyan)" stroke-width="1.8"/>`;
  const last = E[E.length - 1];
  s += `<text x="${W - m.r + 5}" y="${ys(last[1]) + 4}" style="fill:var(--cyan)">${num(last[1], 2)} $</text>`;
  svg.setAttribute("viewBox", `0 0 ${W} ${Hh}`);
  svg.innerHTML = s;
}

function pairPane(d, p) {
  const live = (d.positions || []).filter(q => q.pair === p);
  const opn = live.find(q => q.status === "otwarta"), pend = (d.pend || {})[p];
  const closed = live.filter(q => q.status === "zamknięta"), sum = closed.reduce((a, q) => a + (q.pnl || 0), 0);
  return `<div class="pane c6"><h2>${p}<span class="dim">${opn ? `<span class="am">${DIR(opn.dir)}</span> od ${px(p, opn.entry)} · ${sgn(opn.ret, 3)}% · ` : "bez pozycji · "}` +
    `${pend ? `zmiana na ${DIR(pend.dir)} na open · ` : ""}zamknięte: ${closed.length}${closed.length ? " " + usd(sum) : ""}</span></h2>
    <svg class="chart pv2" data-sma="${p}" style="height:250px"></svg></div>`;
}

function trades(d) {
  const P = (d.positions || []).slice().sort((a, b) => b.no - a.no);
  if (!P.length) return `<p class="empty">jeszcze żadnej pozycji — pierwsze otwierają się po open świecy następnej po starcie (${d.params && d.params.startedAt ? esc(t.dhm(d.params.startedAt * 1000)) : "start"})</p>`;
  return `<div class="tbl-wrap scroll" style="max-height:420px"><table class="tbl"><thead><tr><th>nr</th><th>para</th><th>kierunek</th><th>status</th><th>wejście</th>
    <th class="num">cena wejścia</th><th class="num">wartość</th><th class="num">lot</th><th>wyjście</th><th class="num">cena wyjścia / teraz</th>
    <th class="num">świec</th><th class="num">wynik %</th><th class="num">wynik $</th></tr></thead><tbody>` +
    P.map(q => `<tr${q.status === "otwarta" ? ' class="sel"' : ""}><td>${q.no}</td><td><b>${q.pair}</b></td><td class="${q.dir > 0 ? "up" : "down"}">${DIR(q.dir)}</td><td>${esc(q.status)}</td>
      <td>${q.entryT ? t.short(q.entryT * 1000) : ""}</td><td class="num">${px(q.pair, q.entry)}</td><td class="num">${num(q.notional, 2)} $</td>
      <td class="num">${q.lots === null ? "—" : num(q.lots, 4)}</td><td>${q.status === "zamknięta" && q.exitT ? t.short(q.exitT * 1000) : ""}</td>
      <td class="num">${px(q.pair, q.status === "zamknięta" ? q.exit : q.price)}</td><td class="num">${q.bars ?? ""}</td>
      <td class="num ${cls(q.ret)}">${q.ret === null ? "—" : sgn(q.ret, 3) + "%"}</td><td class="num ${cls(q.pnl)}">${q.pnl === null ? "" : usd(q.pnl)}</td></tr>`).join("") +
    `</tbody></table></div>`;
}

export function renderSma() {
  const d = store.get("sma");
  if (!d || !d.pairs) {
    const m = store.meta.sma;
    return `<div class="grid"><div class="pane c12"><h2>SMA 42/23<span class="dim">paper trading — zawsze w pozycji</span></h2>${help("fx.sma")}
      <p class="empty">${m && m.err ? esc(m.err) + " — " : ""}czekam na <b>telemetry/sma.json</b>: wysyła go Apps Script (plik SmaKrzyz.gs, wersja 1.60) po każdej nowej świecy FX.</p></div></div>`;
  }
  const pairs = Object.keys(d.pairs);
  return `<div class="grid">
    <div class="pane c12 hero"><h2>SMA 42/23 investor<span class="dim">zawsze w pozycji na 10 parach · long gdy SMA42 &gt; SMA23, short gdy niżej · zmiana po open następnej świecy</span></h2>${help("fx.sma")}${hero(d)}
      <div class="legend"><span><i style="background:var(--amber);height:2px"></i>SMA42</span><span><i style="background:var(--cyan);height:2px"></i>SMA23</span>
        <span>▲ wejście long · ▼ wejście short (bursztyn — inwestor, zielony/czerwony — symulacja tych samych reguł)</span><span>■ wyjście — zielone zysk, czerwone strata</span>
        <span><i style="background:var(--up);opacity:.3"></i>tło: kierunek pozycji</span></div></div>
    <div class="pane c12"><h2>saldo<span class="dim">po każdej zamkniętej transakcji</span></h2><svg class="chart" data-sma-eq style="height:160px"></svg></div>
    ${pairs.map(p => pairPane(d, p)).join("")}
    <div class="pane c12"><h2>transakcje inwestora<span class="dim">jak w arkuszu SMA.42-23.Investor</span></h2>${help("fx.sma.trades")}${trades(d)}</div>
  </div>`;
}

export function mountSma(el) {
  const d = store.get("sma");
  if (!d || !d.pairs) return;
  el.querySelectorAll("svg[data-sma]").forEach(svg => {
    const p = svg.dataset.sma;
    chart(svg, p, d.pairs[p], (d.sim || []).filter(q => q.pair === p), (d.positions || []).filter(q => q.pair === p));
  });
  const eq = el.querySelector("svg[data-sma-eq]");
  if (eq) equity(eq, d);
}
