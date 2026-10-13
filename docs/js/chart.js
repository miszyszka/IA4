// IA 4 — wykresy SVG bez bibliotek: prognoza FX, mini-wykres, krzywa wyniku.
// Wersja projektu: 1.38 (2026-10-13)

import { t } from "./core.js";

export const SC_COL = { "spadkowy": "var(--sc-down)", "boczny": "var(--sc-mid)", "wzrostowy": "var(--sc-up)" };

/** Formaty instrumentu: pary walutowe — pipsy, BTC — dolary. */
export const inst = {
  dp: I => I.group === "fx" ? (I.pip >= 0.01 ? 3 : 5) : 0,
  px(I, v) { return v === null || v === undefined ? "—" : v.toLocaleString("pl-PL", { minimumFractionDigits: inst.dp(I), maximumFractionDigits: inst.dp(I) }); },
  chg(I, dv) {
    const s = (x, d) => (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toLocaleString("pl-PL", { minimumFractionDigits: d, maximumFractionDigits: d });
    return I.group === "fx" ? `${s(dv / I.pip, 1)} pips` : `${s(dv, 0)} USD`;
  },
  size(I, dv) { return I.group === "fx" ? `${(dv / I.pip).toLocaleString("pl-PL", { maximumFractionDigits: 1 })} pips` : `${Math.round(dv).toLocaleString("pl-PL")} USD`; },
};

/** Świece (48 wstecz) + stożek 50/80%, środek, scenariusze, typowe maks./min. Oś po świecach (weekend bez dziury). */
export function fxChart(svg, I) {
  const W = svg.clientWidth || 800, Hh = svg.clientHeight || 440;
  const C = I.candles || [], TT = I.times || [];
  if (!C.length) { svg.innerHTML = ""; return; }
  const narrow = W < 520;
  const m = { l: 6, r: narrow ? 58 : 72, t: 16, b: 24 };
  const back = narrow ? Math.min(24, C.length) : C.length;          // telefon: 24 świece wstecz
  const CC = C.slice(-back);
  const nx = CC.length + 48, cw = (W - m.l - m.r) / nx;
  const xs = i => m.l + (i + 0.5) * cw;
  const lastI = CC.length - 1;
  const series = [I.q10, I.q90, I.center].concat((I.scenarios || []).map(s => s.path)).filter(a => a && a.length);
  let lo = Infinity, hi = -Infinity;
  CC.forEach(c => { lo = Math.min(lo, c[3]); hi = Math.max(hi, c[2]); });
  series.forEach(a => a.forEach(v => { if (v !== null) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }));
  if (I.range) { lo = Math.min(lo, I.range.low); hi = Math.max(hi, I.range.high); }
  const pad = (hi - lo) * 0.06 || Math.abs(hi) * 0.001; lo -= pad; hi += pad;
  const ys = v => m.t + (hi - v) / (hi - lo) * (Hh - m.t - m.b);
  let s = "";
  for (let j = 0; j <= 5; j++) {
    const v = lo + (hi - lo) * j / 5, y = ys(v);
    s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}" stroke="var(--grid)"/><text x="${W - m.r + 6}" y="${y + 4}">${inst.px(I, v)}</text>`;
  }
  const xNow = xs(lastI) + cw / 2, c0 = CC[lastI][4];
  s += `<rect class="fcx" x="${xNow}" y="${m.t}" width="${W - m.r - xNow}" height="${Hh - m.t - m.b}" fill="rgba(95,212,230,.025)"/>`;
  s += `<line x1="${xNow}" x2="${xNow}" y1="${m.t}" y2="${Hh - m.b}" stroke="var(--amber)" stroke-dasharray="2 4" opacity=".7"/>`;
  const every = cw * 6 < 60 ? 12 : 6;
  let lastLab = -1e9;
  const label = (tt, x) => {
    const ms = tt * 1000, h = t.hour(ms);
    if (h % every !== 0 || x - lastLab < 46 || x < m.l + 18 || x > W - m.r - 18) return "";
    lastLab = x;
    const txt = h < every ? t.wd(ms) + " " + t.hm(ms) : t.hm(ms);
    return `<text x="${x}" y="${Hh - 7}" text-anchor="middle">${txt}</text>`;
  };
  CC.forEach((c, i) => {
    const x = xs(i), col = c[4] >= c[1] ? "var(--up)" : "var(--down)";
    const yo = ys(c[1]), yc = ys(c[4]), bw = Math.max(1, cw * 0.6);
    s += `<line x1="${x}" x2="${x}" y1="${ys(c[2])}" y2="${ys(c[3])}" stroke="${col}"/>` +
         `<rect x="${x - bw / 2}" y="${Math.min(yo, yc)}" width="${bw}" height="${Math.max(1, Math.abs(yc - yo))}" fill="${col}"/>`;
    s += label(c[0], x);
  });
  const xf = k => xs(lastI + k + 1);
  const pts = a => TT.map((tt, k) => (a[k] === null || a[k] === undefined) ? null : [xf(k), ys(a[k])]).filter(Boolean);
  const band = (a, b, fill) => {
    if (!a || !b || !a.length) return "";
    const top = [[xNow, ys(c0)]].concat(pts(b)), bot = pts(a).reverse().concat([[xNow, ys(c0)]]);
    return `<polygon class="fcx" points="${top.concat(bot).map(p => p.join(",")).join(" ")}" fill="${fill}"/>`;
  };
  const line = (a, stroke, w, dash = "") => (!a || !a.length) ? "" :
    `<polyline class="fcx" points="${[[xNow, ys(c0)]].concat(pts(a)).map(p => p.join(",")).join(" ")}" fill="none" stroke="${stroke}" stroke-width="${w}" stroke-linejoin="round" ${dash ? `stroke-dasharray="${dash}"` : ""}/>`;
  s += band(I.q10, I.q90, "var(--cyan-dim)") + band(I.q25, I.q75, "var(--cyan-dim2)");
  (I.scenarios || []).forEach(sc => { s += line(sc.path, SC_COL[sc.name] || "var(--sc-mid)", 1.2); });
  s += line(I.center, "var(--cyan)", 2.2);
  if (I.range && TT.length) {
    const xe = xf(TT.length - 1);
    for (const [v, lab] of [[I.range.high, "typ. maks."], [I.range.low, "typ. min."]]) {
      s += `<line class="fcx" x1="${xNow}" x2="${xe}" y1="${ys(v)}" y2="${ys(v)}" stroke="var(--dim)" stroke-dasharray="1 5"/>` +
           `<text x="${xe - 4}" y="${ys(v) - 4}" text-anchor="end">${lab}</text>`;
    }
  }
  TT.forEach((tt, k) => { s += label(tt, xf(k)); });
  s += `<text class="lab" x="${xNow + 6}" y="${m.t + 12}">prognoza 48 świec</text>`;
  s += `<circle cx="${xNow}" cy="${ys(c0)}" r="3" fill="var(--amber)"/>`;
  svg.setAttribute("viewBox", `0 0 ${W} ${Hh}`);
  svg.innerHTML = s;
}

/** Mini-wykres zamknięć (48 świec) z kropką na ostatniej. */
export function spark(values, w = 120, h = 22) {
  const v = values.filter(x => x !== null && isFinite(x));
  if (v.length < 2) return `<svg viewBox="0 0 ${w} ${h}"></svg>`;
  const lo = Math.min(...v), hi = Math.max(...v), r = hi - lo || 1;
  const p = v.map((x, i) => [(i / (v.length - 1)) * (w - 4) + 1, h - 3 - (x - lo) / r * (h - 6)]);
  const col = v[v.length - 1] >= v[0] ? "var(--up)" : "var(--down)";
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline points="${p.map(q => q.map(n => n.toFixed(1)).join(",")).join(" ")}" fill="none" stroke="${col}" stroke-width="1.2" vector-effect="non-scaling-stroke"/></svg>`;
}

/** Krzywa wyniku: schodki skumulowanego $ po kolejnych zamkniętych transakcjach. */
export function equity(svg, pts) {
  const W = svg.clientWidth || 600, Hh = svg.clientHeight || 160;
  if (!pts || pts.length < 1) { svg.innerHTML = `<text x="8" y="20">brak zamkniętych transakcji</text>`; return; }
  const m = { l: 6, r: 62, t: 10, b: 20 };
  const v = [0].concat(pts.map(p => p[1]));
  const lo = Math.min(0, ...v), hi = Math.max(0, ...v), r = (hi - lo) || 1;
  const xs = i => m.l + i / (v.length - 1) * (W - m.l - m.r);
  const ys = y => m.t + (hi - y) / r * (Hh - m.t - m.b);
  let d = `M${xs(0)},${ys(0)}`;
  for (let i = 1; i < v.length; i++) d += `H${xs(i).toFixed(1)}V${ys(v[i]).toFixed(1)}`;
  const last = v[v.length - 1], col = last >= 0 ? "var(--up)" : "var(--down)";
  let s = `<line x1="${m.l}" x2="${W - m.r}" y1="${ys(0)}" y2="${ys(0)}" stroke="var(--grid-2)"/>`;
  s += `<text x="${W - m.r + 6}" y="${ys(0) + 4}">0 $</text>`;
  s += `<path d="${d}" fill="none" stroke="${col}" stroke-width="1.6"/>`;
  s += `<text x="${W - m.r + 6}" y="${ys(last) + 4}" style="fill:${col}">${(last >= 0 ? "+" : "−") + Math.abs(last).toFixed(2).replace(".", ",")} $</text>`;
  s += `<text x="${m.l}" y="${Hh - 5}">${pts[0][0] ? pts[0][0].slice(5, 10) : ""}</text><text x="${W - m.r}" y="${Hh - 5}" text-anchor="end">${pts[pts.length - 1][0] ? pts[pts.length - 1][0].slice(5, 16) : ""}</text>`;
  svg.setAttribute("viewBox", `0 0 ${W} ${Hh}`);
  svg.innerHTML = s;
}
