// IA 4 — FX → Powrót.v2: HISTORIA (wykres pary z przewijaniem po całych 2 latach) i GALERIA (każda transakcja na
// własnym wykresie, z filtrem: stratne, zyskowne, limit czasu, inwestor). Dane: branch fx, fx/pv2/ (Mac:
// python -m ia4.fxpowrot2 --strona) + najnowsze świece i pozycje z telemetry/pv2.json (Apps Script).
// Wersja projektu: 1.55 (2026-10-21)

import { store, num, sgn, esc, t, cls, pref, REPO } from "../core.js";

const H = 3600e3;
const URL = path => `https://raw.githubusercontent.com/${REPO}/fx/fx/pv2/${path}?h=${Math.floor(Date.now() / 600e3)}`;
const px = (p, v) => v === null || v === undefined || !isFinite(v) ? "—" :
  v.toLocaleString("pl-PL", { minimumFractionDigits: /JPY$/.test(p) ? 3 : 5, maximumFractionDigits: /JPY$/.test(p) ? 3 : 5 });
const KIND = k => !k ? "" : k === "TP" ? "TP" : k.startsWith("czas") ? "limit 60 św." : k;
export const FILTERS = [["all", "wszystkie"], ["loss", "stratne"], ["win", "zyskowne"], ["time", "limit czasu"], ["live", "inwestor"]];
const pass = (f, tr) => f === "all" ? true : f === "loss" ? (tr.ret ?? 0) <= 0 && tr.kind !== "otwarta" : f === "win" ? (tr.ret ?? 0) > 0 :
  f === "time" ? (tr.kind || "").startsWith("czas") : f === "live" ? !!tr.live : true;

// ------------------------------------------------------------------ stan widoku (pamiętany w przeglądarce)
export const ui = {
  pair: pref.get("pv2.pair", "EURUSD"), filter: pref.get("pv2.filter", "all"), span: pref.get("pv2.span", matchMedia("(max-width: 760px)").matches ? 72 : 240), end: null, sel: null,
  gFilter: pref.get("pv2.gFilter", "loss"), gPair: pref.get("pv2.gPair", "all"), gSort: pref.get("pv2.gSort", "worst"), gShow: 24,
};
const save = () => { ["pair", "filter", "span", "gFilter", "gPair", "gSort"].forEach(k => pref.set("pv2." + k, ui[k])); };

// ------------------------------------------------------------------ dane
const cache = { index: null, indexErr: null, pairs: {}, loading: {} };
let onLoaded = () => {};
export function setOnLoaded(fn) { onLoaded = fn; }

async function getJson(path) {
  const r = await fetch(URL(path), { cache: "no-cache" });
  if (!r.ok) throw new Error(r.status === 404 ? "brak pliku" : `HTTP ${r.status}`);
  return r.json();
}
export function index() {
  if (!cache.index && !cache.loading.index) {
    cache.loading.index = true;
    getJson("index.json").then(d => { cache.index = d; }).catch(e => { cache.indexErr = e.message; }).finally(() => { cache.loading.index = false; onLoaded(); });
  }
  return cache.index;
}
export const indexErr = () => cache.indexErr;
export const loading = () => cache.loading.index || Object.values(cache.loading).some(Boolean);

/** Świece pary: historia z brancha fx + nowsze z pv2.json (Apps Script). [[t,o,h,l,c], …] */
export function candles(p) {
  if (cache.pairs[p]) return cache.pairs[p];
  if (!cache.loading[p]) {
    cache.loading[p] = true;
    getJson(`${p}.json`).then(d => {
      const k = 10 ** d.dp, C = [];
      let tt = d.t0;
      for (let i = 0; i < d.o.length; i++) { tt += d.dt[i] * 3600; C.push([tt, d.o[i] / k, d.h[i] / k, d.l[i] / k, d.c[i] / k]); }
      cache.pairs[p] = C;
    }).catch(() => { cache.pairs[p] = []; }).finally(() => { cache.loading[p] = false; onLoaded(); });
  }
  return null;
}
function merged(p) {
  const C = candles(p);
  if (!C) return null;
  const live = ((store.get("pv2") || {}).pairs || {})[p];
  const L = (live && live.candles) || [];
  if (!L.length) return C;
  const last = C.length ? C[C.length - 1][0] : 0;
  return C.concat(L.filter(c => c[0] > last));
}

/** Transakcje: cała historia (Python) + nowsze z symulacji Apps Script + pozycje inwestora (live). */
export function trades(p) {
  const I = cache.index, d = store.get("pv2") || {};
  const T = ((I && I.trades) || []).filter(x => !p || x.pair === p).map(x => Object.assign({ src: "hist" }, x));
  const lastSig = {};
  T.forEach(x => { lastSig[x.pair] = Math.max(lastSig[x.pair] || 0, x.sigT); });
  const upto = I ? I.do : 0;
  (d.sim || []).filter(x => (!p || x.pair === p) && x.sigT > upto).forEach(x => T.push(Object.assign({ src: "sim" }, x)));
  (d.positions || []).filter(x => (!p || x.pair === p) && x.status !== "anulowana" && (x.entryT || x.status === "oczekuje"))
    .forEach(x => T.push(Object.assign({ src: "live", live: true }, x, { kind: x.status === "zamknięta" ? x.kind : x.status === "otwarta" ? "otwarta" : "oczekuje" })));
  return T.sort((a, b) => a.sigT - b.sigT);
}

// ------------------------------------------------------------------ wykres zakresu świec
function at(C, tt) {                                    // indeks świecy o czasie tt (albo najbliższej późniejszej)
  let lo = 0, hi = C.length - 1;
  if (!C.length) return -1;
  if (tt <= C[0][0]) return 0;
  if (tt >= C[hi][0]) return hi;
  while (lo < hi) { const m = (lo + hi) >> 1; if (C[m][0] < tt) lo = m + 1; else hi = m; }
  return lo;
}

/** Świece C[i0..i1) i transakcje T; sel — wyróżniona transakcja. */
export function drawRange(svg, p, C, i0, i1, T, sel, opt = {}) {
  const W = svg.clientWidth || 800, Hh = svg.clientHeight || 420;
  i0 = Math.max(0, Math.floor(i0)); i1 = Math.min(C.length, Math.ceil(i1));
  if (i1 - i0 < 2) { svg.innerHTML = `<text x="8" y="20">${C.length ? "za mało świec" : "ładuję świece…"}</text>`; return; }
  const m = { l: 4, r: opt.small ? 52 : 66, t: 12, b: 20 };
  const n = i1 - i0, cw = (W - m.l - m.r) / n;
  const xs = i => m.l + (i - i0 + 0.5) * cw;
  const vis = T.filter(tr => { const a = at(C, tr.sigT), b = tr.exitT ? at(C, tr.exitT) : C.length - 1; return b >= i0 && a < i1; });
  let lo = Infinity, hi = -Infinity;
  for (let i = i0; i < i1; i++) { lo = Math.min(lo, C[i][3]); hi = Math.max(hi, C[i][2]); }
  vis.forEach(tr => [tr.tp, tr.base, tr.entry].forEach(v => { if (v !== null && v !== undefined && isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }));
  const pad = (hi - lo) * 0.05 || hi * 0.001; lo -= pad; hi += pad;
  const ys = v => m.t + (hi - v) / (hi - lo) * (Hh - m.t - m.b);
  let s = "";
  for (let j = 0; j <= 4; j++) {
    const v = lo + (hi - lo) * j / 4, y = ys(v);
    s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}" stroke="var(--grid)"/><text x="${W - m.r + 5}" y="${y + 4}">${px(p, v)}</text>`;
  }
  // etykiety dat: co tyle dni, żeby nie nachodziły
  const days = n / 24, every = days <= 12 ? 1 : days <= 30 ? 2 : days <= 70 ? 7 : days <= 200 ? 14 : 30;
  let lastLab = -1e9, lastDay = "";
  const bw = Math.max(1, cw * 0.62);
  for (let i = i0; i < i1; i++) {
    const c = C[i], x = xs(i), col = c[4] >= c[1] ? "var(--up)" : "var(--down)";
    if (cw >= 1.2) {
      const yo = ys(c[1]), yc = ys(c[4]);
      s += `<line x1="${x}" x2="${x}" y1="${ys(c[2])}" y2="${ys(c[3])}" stroke="${col}" opacity=".75"/>` +
           (cw >= 2.5 ? `<rect x="${x - bw / 2}" y="${Math.min(yo, yc)}" width="${bw}" height="${Math.max(1, Math.abs(yc - yo))}" fill="${col}" opacity=".8"/>` : "");
    }
    const day = t.dm(c[0] * 1000), dd = Math.floor(c[0] / 86400);
    if (day !== lastDay) {
      if (dd % every === 0 && x - lastLab > 44 && x > m.l + 14 && x < W - m.r - 20) {
        s += `<line x1="${x}" x2="${x}" y1="${m.t}" y2="${Hh - m.b}" stroke="var(--grid)" stroke-dasharray="1 4"/>` +
             `<text x="${x + 2}" y="${Hh - 6}">${every >= 14 ? new Date(c[0] * 1000).toISOString().slice(2, 10) : day}</text>`;
        lastLab = x;
      }
      lastDay = day;
    }
  }
  if (cw < 1.2) {                                     // bardzo daleko — linia zamknięć zamiast świec
    let d = "";
    const step = Math.max(1, Math.floor(1 / cw));
    for (let i = i0; i < i1; i += step) d += (d ? "L" : "M") + xs(i).toFixed(1) + "," + ys(C[i][4]).toFixed(1);
    s += `<path d="${d}" fill="none" stroke="var(--ink-2)" stroke-width="1"/>`;
  }
  vis.forEach(tr => {
    const iS = at(C, tr.sigT), iE = tr.entryT ? at(C, tr.entryT) : null;
    const open = tr.kind === "otwarta" || tr.kind === "oczekuje";
    const iX = open ? C.length - 1 : at(C, tr.exitT);
    const isSel = sel && sel.pair === tr.pair && sel.sigT === tr.sigT && sel.src === tr.src;
    const good = (tr.ret ?? 0) > 0, colR = open ? "var(--amber)" : good ? "var(--up)" : "var(--down)";
    const base = tr.live ? "var(--amber)" : "var(--cyan)", wd = isSel ? 2.6 : tr.live ? 2 : 1.3;
    const tip = `${p} ${tr.live ? "inwestor" : "symulacja"} · sygnał ${t.dhm(tr.sigT * 1000)} · wejście ${px(p, tr.entry)} · TP ${px(p, tr.tp)}` +
      (open ? ` · ${tr.kind}` : ` · wyjście ${px(p, tr.exit)} (${KIND(tr.kind)}) · ${sgn(tr.ret, 3)}% · ${tr.bars} św.`);
    let g = `<g data-tr="${tr.src}:${tr.sigT}" style="cursor:pointer" opacity="${sel && !isSel ? 0.55 : 1}"><title>${esc(tip)}</title>`;
    if (iS >= i0 && iS < i1) g += `<path d="M${xs(iS) - 4},${ys(C[iS][2]) - 9} h8 l-4,6 z" fill="${base}"/>`;
    if (iE !== null) {
      const x0 = xs(iE), x1 = xs(iX), yE = ys(tr.entry), yX = ys(open ? C[C.length - 1][4] : tr.exit);
      if (tr.base !== null && tr.base !== undefined) g += `<line x1="${x0}" x2="${x1}" y1="${ys(tr.base)}" y2="${ys(tr.base)}" stroke="var(--dim)" stroke-dasharray="1 3"/>`;
      if (tr.tp !== null && tr.tp !== undefined) g += `<line x1="${x0}" x2="${Math.max(x1, x0 + 6)}" y1="${ys(tr.tp)}" y2="${ys(tr.tp)}" stroke="var(--up)" stroke-dasharray="4 3" stroke-width="${wd * 0.7}"/>`;
      g += `<rect x="${x0}" y="${Math.min(yE, yX)}" width="${Math.max(2, x1 - x0)}" height="${Math.max(1, Math.abs(yX - yE))}" fill="${colR}" opacity="${isSel ? 0.2 : 0.1}"/>`;
      g += `<line x1="${x0}" x2="${x1}" y1="${yE}" y2="${yX}" stroke="${colR}" stroke-width="${wd}"/>`;
      g += `<circle cx="${x0}" cy="${yE}" r="${isSel ? 5 : tr.live ? 4 : 3}" fill="${base}" stroke="var(--void)"/>`;
      if (!open) g += `<rect x="${x1 - 3.5}" y="${yX - 3.5}" width="7" height="7" fill="${colR}" stroke="var(--void)"/>`;
      if (isSel || opt.label) g += `<text x="${x1 + 6}" y="${yX + 4}" style="fill:${colR};font-weight:600">${open ? tr.kind : sgn(tr.ret, 3) + "%"}</text>`;
    }
    s += g + `</g>`;
  });
  const lc = C[i1 - 1][4];
  s += `<text x="${W - m.r + 5}" y="${ys(lc) + 4}" style="fill:var(--amber)">${px(p, lc)}</text>`;
  svg.setAttribute("viewBox", `0 0 ${W} ${Hh}`);
  svg.innerHTML = s;
}

/** Pasek nawigacji: całe 2 lata (linia zamknięć), znaczniki transakcji, okno widoku. */
function drawNav(svg, C, T, i0, i1) {
  const W = svg.clientWidth || 800, Hh = svg.clientHeight || 54;
  if (!C.length) { svg.innerHTML = ""; return; }
  const n = C.length, xs = i => 2 + i / (n - 1) * (W - 4);
  let lo = Infinity, hi = -Infinity;
  C.forEach(c => { lo = Math.min(lo, c[4]); hi = Math.max(hi, c[4]); });
  const ys = v => 6 + (hi - v) / ((hi - lo) || 1) * (Hh - 12);
  let d = "", step = Math.max(1, Math.floor(n / W));
  for (let i = 0; i < n; i += step) d += (d ? "L" : "M") + xs(i).toFixed(1) + "," + ys(C[i][4]).toFixed(1);
  let s = `<path d="${d}" fill="none" stroke="var(--dim)" stroke-width="1"/>`;
  T.forEach(tr => {
    const x = xs(at(C, tr.sigT)), col = tr.kind === "otwarta" || tr.kind === "oczekuje" ? "var(--amber)" : (tr.ret ?? 0) > 0 ? "var(--up)" : "var(--down)";
    s += `<line x1="${x}" x2="${x}" y1="${Hh - 9}" y2="${Hh}" stroke="${col}" stroke-width="${(tr.ret ?? 0) > 0 ? 1 : 2}"/>`;
  });
  s += `<rect x="${xs(i0)}" y="1" width="${Math.max(3, xs(i1 - 1) - xs(i0))}" height="${Hh - 2}" fill="rgba(255,181,71,.10)" stroke="var(--amber)"/>`;
  svg.setAttribute("viewBox", `0 0 ${W} ${Hh}`);
  svg.innerHTML = s;
}

// ------------------------------------------------------------------ HISTORIA
const chips = (list, cur, attr) => list.map(([k, lab]) => `<button type="button" class="chip" data-${attr}="${k}" aria-pressed="${k === cur}">${lab}</button>`).join(" ");

function tradeTable(p, T, sel) {
  if (!T.length) return `<p class="empty">brak transakcji w tym filtrze</p>`;
  const sum = T.reduce((a, x) => a + (x.kind === "otwarta" || x.kind === "oczekuje" ? 0 : (x.ret || 0)), 0);
  return `<p class="note" style="margin:0 0 6px">${T.length} transakcji · suma ${sgn(sum, 3)}% · średnio ${sgn(sum / T.length, 3)}% (bez dźwigni) — kliknij wiersz, żeby przewinąć wykres</p>
  <div class="tbl-wrap scroll" style="max-height:340px"><table class="tbl"><thead><tr><th>źródło</th><th>sygnał</th><th class="num">wejście</th><th class="num">TP</th>
    <th>wyjście</th><th class="num">cena wyjścia</th><th>powód</th><th class="num">świec</th><th class="num">wynik %</th></tr></thead><tbody>` +
    T.slice().reverse().map(x => `<tr data-row="${x.src}:${x.sigT}" style="cursor:pointer"${sel && sel.sigT === x.sigT && sel.src === x.src ? ' class="sel"' : ""}>
      <td>${x.live ? '<span class="am">inwestor</span>' : x.src === "sim" ? "symulacja (nowa)" : "historia"}</td><td>${t.short(x.sigT * 1000)}</td><td class="num">${px(p, x.entry)}</td>
      <td class="num">${px(p, x.tp)}</td><td>${x.exitT && x.kind !== "otwarta" ? t.short(x.exitT * 1000 + H) : ""}</td><td class="num">${x.kind === "otwarta" ? "" : px(p, x.exit)}</td>
      <td>${esc(KIND(x.kind))}</td><td class="num">${x.bars ?? ""}</td><td class="num ${cls(x.ret)}">${x.ret === null || x.ret === undefined ? "—" : sgn(x.ret, 3) + "%"}</td></tr>`).join("") +
    `</tbody></table></div>`;
}

export function renderHistory() {
  const I = index(), p = ui.pair, C = merged(p);
  const pairs = (I && I.pairs) || Object.keys((store.get("pv2") || {}).pairs || {});
  const T = C ? trades(p).filter(x => pass(ui.filter, x)) : [];
  const head = `<div class="pv2-ctl"><span class="dim">para</span> ${chips(pairs.map(x => [x, x]), p, "pair")}</div>
    <div class="pv2-ctl"><span class="dim">transakcje</span> ${chips(FILTERS, ui.filter, "filter")}
      <span class="sep"></span><button type="button" class="chip" data-nav="prev" title="poprzednia transakcja w filtrze">‹ transakcja</button>
      <button type="button" class="chip" data-nav="next" title="następna transakcja w filtrze">transakcja ›</button>
      <span class="sep"></span><button type="button" class="chip" data-nav="left" title="w lewo">«</button><button type="button" class="chip" data-nav="right" title="w prawo">»</button>
      <button type="button" class="chip" data-nav="out" title="oddal">−</button><button type="button" class="chip" data-nav="in" title="przybliż">+</button>
      <button type="button" class="chip" data-nav="end" title="najnowsze świece">teraz</button></div>`;
  const msg = !I && indexErr() ? `<p class="empty">historia niedostępna (${esc(indexErr())}) — na Macu: <b>python -m ia4.fxpowrot2 --strona</b> (zapisuje fx/pv2/ na branchu fx)</p>` :
    !C ? `<p class="empty">ładuję świece ${esc(p)}…</p>` : "";
  return `<div class="grid"><div class="pane c12"><h2>historia ${esc(p)}<span class="dim" data-range></span></h2>${head}${msg}
      <svg class="chart pv2h" data-hist style="height:460px;touch-action:pan-y"></svg>
      <svg class="pv2nav" data-nav-strip style="width:100%;height:54px;display:block;cursor:pointer"></svg>
      <p class="note">przeciągnij wykres albo przewiń kółkiem, żeby przesuwać w czasie · Ctrl / ⌘ + kółko albo − / + — przybliżenie · pasek pod wykresem = całe 2 lata (kreski: zielone — zyskowne, czerwone — stratne), kliknij, żeby skoczyć · kliknij transakcję na wykresie albo w tabeli</p></div>
    <div class="pane c12"><h2>transakcje ${esc(p)}<span class="dim">${FILTERS.find(f => f[0] === ui.filter)[1]}</span></h2><div data-ttable>${C ? tradeTable(p, T, ui.sel) : ""}</div></div></div>`;
}

export function mountHistory(el, rerender) {
  const p = ui.pair, C = merged(p);
  const svg = el.querySelector("[data-hist]"), nav = el.querySelector("[data-nav-strip]");
  if (!svg) return;
  if (!C || !C.length) { svg.innerHTML = `<text x="8" y="20">${C ? "brak świec" : "ładuję…"}</text>`; return; }
  const all = trades(p), T = all.filter(x => pass(ui.filter, x));
  const n = C.length;
  ui.span = Math.max(30, Math.min(n, ui.span));
  if (ui.end === null || ui.end > n) ui.end = n;
  const clamp = () => { ui.end = Math.max(Math.min(n, ui.span), Math.min(n, ui.end)); };
  let raf = 0;
  const draw = () => {
    clamp();
    const i0 = ui.end - ui.span;
    drawRange(svg, p, C, i0, ui.end, T, ui.sel);
    drawNav(nav, C, T, i0, ui.end);
    const r = el.querySelector("[data-range]");
    if (r) r.textContent = `${t.dhm(C[Math.max(0, Math.floor(i0))][0] * 1000)} – ${t.dhm(C[ui.end - 1][0] * 1000 + H)} · ${Math.round(ui.span)} świec`;
  };
  const later = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; draw(); }); };
  const center = tr => { const i = Math.floor((at(C, tr.sigT) + at(C, tr.exitT || tr.sigT)) / 2); ui.end = i + Math.floor(ui.span / 2); ui.sel = tr; };
  draw();
  const cw = () => (svg.clientWidth - 70) / ui.span;
  svg.addEventListener("wheel", e => {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) {
      const f = e.deltaY > 0 ? 1.15 : 1 / 1.15, mid = ui.end - ui.span / 2;
      ui.span = Math.max(30, Math.min(n, ui.span * f)); ui.end = mid + ui.span / 2;
    } else ui.end += (Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY) / cw() * 0.6;
    later();
  }, { passive: false });
  let drag = null;
  svg.addEventListener("pointerdown", e => { drag = { x: e.clientX, end: ui.end, moved: false }; svg.setPointerCapture(e.pointerId); });
  svg.addEventListener("pointermove", e => { if (!drag) return; const dx = e.clientX - drag.x; if (Math.abs(dx) > 3) drag.moved = true; ui.end = drag.end - dx / cw(); later(); });
  svg.addEventListener("pointerup", e => {
    const was = drag; drag = null;
    if (was && !was.moved) {
      const g = e.target.closest("[data-tr]");
      if (g) { const [src, sig] = g.dataset.tr.split(":"); ui.sel = all.find(x => x.src === src && String(x.sigT) === sig) || null; rerender(); }
    }
  });
  const jump = e => { const r = nav.getBoundingClientRect(); const i = (e.clientX - r.left) / r.width * n; ui.end = i + ui.span / 2; later(); };
  let navDrag = false;
  nav.addEventListener("pointerdown", e => { navDrag = true; nav.setPointerCapture(e.pointerId); jump(e); });
  nav.addEventListener("pointermove", e => { if (navDrag) jump(e); });
  nav.addEventListener("pointerup", () => { navDrag = false; });
  el.querySelectorAll("[data-nav]").forEach(b => b.addEventListener("click", () => {
    const k = b.dataset.nav;
    if (k === "left") ui.end -= ui.span * 0.8;
    if (k === "right") ui.end += ui.span * 0.8;
    if (k === "in" || k === "out") { const mid = ui.end - ui.span / 2; ui.span = Math.max(30, Math.min(n, ui.span * (k === "in" ? 0.6 : 1.7))); ui.end = mid + ui.span / 2; }
    if (k === "end") { ui.end = n; ui.sel = null; }
    if (k === "prev" || k === "next") {
      if (!T.length) return;
      const ref = ui.sel ? ui.sel.sigT : C[Math.min(n - 1, Math.floor(ui.end - ui.span / 2))][0];
      const cand = k === "prev" ? T.filter(x => x.sigT < ref).pop() : T.find(x => x.sigT > ref);
      const tr = cand || (k === "prev" ? T[T.length - 1] : T[0]);
      center(tr); save(); rerender(); return;
    }
    save(); draw();
  }));
  el.querySelectorAll("[data-pair]").forEach(b => b.addEventListener("click", () => { ui.pair = b.dataset.pair; ui.end = null; ui.sel = null; save(); rerender(); }));
  el.querySelectorAll("[data-filter]").forEach(b => b.addEventListener("click", () => { ui.filter = b.dataset.filter; ui.sel = null; save(); rerender(); }));
  const tt = el.querySelector("[data-ttable]");
  if (tt) tt.addEventListener("click", e => {
    const r = e.target.closest("[data-row]");
    if (!r) return;
    const [src, sig] = r.dataset.row.split(":");
    const tr = all.find(x => x.src === src && String(x.sigT) === sig);
    if (tr) { center(tr); rerender(); svg.scrollIntoView({ block: "center", behavior: "smooth" }); }
  });
}

// ------------------------------------------------------------------ GALERIA
const SORTS = [["worst", "najgorsze"], ["best", "najlepsze"], ["new", "najnowsze"], ["old", "najstarsze"]];

export function renderGallery() {
  const I = index();
  const pairs = (I && I.pairs) || Object.keys((store.get("pv2") || {}).pairs || {});
  const head = `<div class="pv2-ctl"><span class="dim">transakcje</span> ${chips(FILTERS, ui.gFilter, "gfilter")}</div>
    <div class="pv2-ctl"><span class="dim">para</span> ${chips([["all", "wszystkie"]].concat(pairs.map(x => [x, x])), ui.gPair, "gpair")}</div>
    <div class="pv2-ctl"><span class="dim">kolejność</span> ${chips(SORTS, ui.gSort, "gsort")}</div>`;
  if (!I) return `<div class="grid"><div class="pane c12"><h2>galeria transakcji</h2>${head}<p class="empty">${indexErr() ?
    `historia niedostępna (${esc(indexErr())}) — na Macu: <b>python -m ia4.fxpowrot2 --strona</b>` : "ładuję listę transakcji…"}</p></div></div>`;
  let T = trades(ui.gPair === "all" ? null : ui.gPair).filter(x => pass(ui.gFilter, x));
  const sum = T.reduce((a, x) => a + (x.kind === "otwarta" || x.kind === "oczekuje" ? 0 : (x.ret || 0)), 0);
  const key = { worst: (a, b) => (a.ret ?? 0) - (b.ret ?? 0), best: (a, b) => (b.ret ?? 0) - (a.ret ?? 0), new: (a, b) => b.sigT - a.sigT, old: (a, b) => a.sigT - b.sigT }[ui.gSort];
  T = T.slice().sort(key);
  const show = T.slice(0, ui.gShow);
  const need = [...new Set(show.map(x => x.pair))];
  need.forEach(p => candles(p));                        // pobranie świec potrzebnych par
  const cards = show.map((x, k) => `<div class="pane c4 pv2card"><h2>${x.pair}<span class="dim">${t.short(x.sigT * 1000)} · ${esc(KIND(x.kind))} · ${x.bars ?? "?"} św.</span>
      <span class="${cls(x.ret)}" style="margin-left:auto;font-weight:600">${x.ret === null || x.ret === undefined ? "" : sgn(x.ret, 3) + "%"}</span></h2>
      <svg class="chart pv2" data-card="${k}" style="height:210px"></svg>
      <p class="note" style="margin:4px 0 0">${x.live ? '<span class="am">inwestor</span> · ' : ""}wejście ${px(x.pair, x.entry)} · TP ${px(x.pair, x.tp)} · baza ${px(x.pair, x.base)} ·
        <a href="#fx/powrot" data-open="${k}">pokaż w historii ›</a></p></div>`).join("");
  return `<div class="grid"><div class="pane c12"><h2>galeria transakcji<span class="dim">${T.length} w filtrze · suma ${sgn(sum, 3)}% · średnio ${T.length ? sgn(sum / T.length, 3) : "—"}% (bez dźwigni)</span></h2>${head}
      <p class="note">każda transakcja na własnym wykresie: ok. 30 świec przed sygnałem i 10 po wyjściu · ▼ sygnał, ● wejście, ■ wyjście, zielona przerywana — TP, kropkowana — baza</p></div>
    ${cards || `<div class="pane c12"><p class="empty">brak transakcji w tym filtrze</p></div>`}
    ${T.length > show.length ? `<div class="pane c12 flat"><button type="button" class="btn ghost" data-more>pokaż więcej (${T.length - show.length})</button></div>` : ""}</div>`;
}

export function mountGallery(el, rerender, toHistory) {
  if (!index()) { bindGalleryCtl(el, rerender); return; }
  let T = trades(ui.gPair === "all" ? null : ui.gPair).filter(x => pass(ui.gFilter, x));
  const key = { worst: (a, b) => (a.ret ?? 0) - (b.ret ?? 0), best: (a, b) => (b.ret ?? 0) - (a.ret ?? 0), new: (a, b) => b.sigT - a.sigT, old: (a, b) => a.sigT - b.sigT }[ui.gSort];
  T = T.slice().sort(key).slice(0, ui.gShow);
  el.querySelectorAll("svg[data-card]").forEach(svg => {
    const x = T[+svg.dataset.card], C = merged(x.pair);
    if (!C) { svg.innerHTML = `<text x="8" y="20">ładuję świece ${x.pair}…</text>`; return; }
    const a = at(C, x.sigT), b = x.exitT && x.kind !== "otwarta" ? at(C, x.exitT) : C.length - 1;
    drawRange(svg, x.pair, C, a - 30, Math.min(C.length, b + 11), [x], x, { small: true, label: true });
  });
  el.querySelectorAll("[data-open]").forEach(a => a.addEventListener("click", e => {
    e.preventDefault();
    const x = T[+a.dataset.open];
    ui.pair = x.pair; ui.sel = x; ui.filter = "all";
    const C = merged(x.pair);
    if (C) ui.end = Math.floor((at(C, x.sigT) + at(C, x.exitT || x.sigT)) / 2) + Math.floor(ui.span / 2);
    save(); toHistory();
  }));
  const more = el.querySelector("[data-more]");
  if (more) more.addEventListener("click", () => { ui.gShow += 24; rerender(); });
  bindGalleryCtl(el, rerender);
}

function bindGalleryCtl(el, rerender) {
  el.querySelectorAll("[data-gfilter]").forEach(b => b.addEventListener("click", () => { ui.gFilter = b.dataset.gfilter; ui.gShow = 24; save(); rerender(); }));
  el.querySelectorAll("[data-gpair]").forEach(b => b.addEventListener("click", () => { ui.gPair = b.dataset.gpair; ui.gShow = 24; save(); rerender(); }));
  el.querySelectorAll("[data-gsort]").forEach(b => b.addEventListener("click", () => { ui.gSort = b.dataset.gsort; save(); rerender(); }));
}
