// IA 4 — zakładka FX: 10 par walutowych + BTC, świece 1h, prognoza rozkładu, spływ świec,
// przeliczenia FX-research i (w przyszłości) wirtualny inwestor FX. Wersja projektu: 1.41 (2026-10-14)

import { store, num, pct, esc, age, t, fxOpen, pref } from "../core.js";
import { help } from "../help.js";
import { fxChart, spark, inst, SC_COL } from "../chart.js";
import { fxLast, stamp } from "../health.js";
import { renderInvestor, mountInvestor } from "./investor.js";

const H = 3600e3;
const METHOD = { analogi: "analogi (podobne chwile, cała grupa)", pora: "pora dnia (ten sam instrument)" };
let sel = pref.get("fx", null);

function nextClose(I, now) {                 // zamknięcie najbliższej świecy w godzinach rynku
  let s = Math.floor(now / H) * H;
  for (let i = 0; i < 80; i++, s += H) if (fxOpen(I.group, s)) return s + H;
  return NaN;
}

function hero(fc) {
  const now = Date.now(), alive = stamp(fc.aliveAt), on = !fc.stoppedAt && now - alive < 5 * 60e3;
  const ch = fc.check || {}, v = fc.verdict || {}, m = fc.model || {}, r = fc.ratings || {};
  return `<div class="reads">
    <div class="read"><div class="k">Mac · FX-real-time</div><div class="v ${on ? "ok" : "bad"}">${on ? "połączony" : fc.stoppedAt ? "zatrzymany" : "offline"}</div>
      <div class="s">sygnał <span data-ts="${alive}">${age((now - alive) / 1000)}</span> temu</div></div>
    <div class="read"><div class="k">rynek walutowy</div><div class="v">${fxOpen("fx", now) ? "otwarty" : "zamknięty"}</div><div class="s">nd 23:00 – pt 23:00 PL · BTC 24/7</div></div>
    <div class="read"><div class="k">prognoza</div><div class="v">${t.hm(stamp(fc.generatedAt))}</div><div class="s">${esc(t.dhm(stamp(fc.generatedAt)))}</div></div>
    <div class="read"><div class="k">model na żywo</div><div class="v">${esc(m.method || "—")}</div><div class="s">${m.K || "?"} ścieżek · ×${m.f} · λ ${m.lambda}</div></div>
    <div class="read"><div class="k">sprawdzian (wszystkie)</div><div class="v">stożek ${pct(ch.cov80_48)}</div><div class="s">${esc(v.cone || "")} · Brier ${ch.brier48 === undefined || ch.brier48 === null ? "—" : num(ch.brier48, 3)}</div></div>
    <div class="read"><div class="k">ratingi</div><div class="v">${esc(r.run || "—")}</div><div class="s">${r.at ? esc(t.dhm(stamp(r.at))) : ""} · wersja ${esc(fc.version || "")}</div></div>
  </div>`;
}

function rail(list, last) {
  return `<div class="rail">` + list.map(I => {
    const c = (I.candles || []).map(x => x[4]), p = I.pUp ? I.pUp["48"] : null, open = fxOpen(I.group);
    const newer = last[I.id] && last[I.id].t > stamp(I.lastCandle);
    return `<button type="button" data-id="${I.id}" aria-pressed="${I.id === sel}"><span><span class="id">${I.id}</span><br><span class="mk">${open ? "● rynek" : "○ zamknięty"}${newer ? " · <span class='warn'>nowsza w bazie</span>" : ""}</span></span>` +
      `${spark(c.slice(-48))}<span class="p">${inst.px(I, I.lastClose)}</span><span class="p ${p === null ? "" : p > 0.5 ? "up" : p < 0.5 ? "down" : ""}">${p === null ? "—" : Math.round(100 * p) + "%"}</span></button>`;
  }).join("") + `</div><p class="note">ostatnie 48 świec · P(wzrost) po 48 świecach — kolor to tylko kierunek, nie przewaga (patrz sprawdzian)</p>`;
}

function detail(fc, I) {
  const n = (I.times || []).length, c0 = I.lastClose, lastT = stamp(I.lastCandle);
  const pu = I.pUp || {}, uc = I.upCount || {}, v = fc.verdict || {}, ci = I.check || {};
  const edge = (v.direction || "").startsWith("przewaga");
  const p = pu["48"];
  return `<div class="reads">
    <div class="read"><div class="k">ostatnie zamknięcie</div><div class="v">${inst.px(I, c0)}</div><div class="s">świeca ${t.short(lastT)} · ATR100 ${inst.size(I, I.atr100)}</div></div>
    <div class="read"><div class="k">oczekiwany zakres 48 h</div><div class="v">${I.range ? inst.size(I, I.range.size) : "—"}</div><div class="s">${I.range ? `maks. ${inst.px(I, I.range.high)} · min. ${inst.px(I, I.range.low)}` : ""}</div></div>
    <div class="read"><div class="k">za 48 świec — 80%</div><div class="v" style="font-size:16px">${I.q10 && n ? `${inst.px(I, I.q10[n - 1])} – ${inst.px(I, I.q90[n - 1])}` : "—"}</div>
      <div class="s">${I.q10 && n ? `${inst.chg(I, I.q10[n - 1] - c0)} / ${inst.chg(I, I.q90[n - 1] - c0)} · do ${t.dhm(I.times[n - 1] * 1000 + H)}` : "za mało historii"}</div></div>
    <div class="read"><div class="k">kierunek</div><div class="v ${edge && p > 0.55 ? "up" : edge && p < 0.45 ? "down" : ""}">${p === undefined ? "—" : "wzrost " + pct(p)}</div>
      <div class="s">${uc["48"] ? `${uc["48"][0]} z ${uc["48"][1]} podobnych · ${esc(v.direction || "")}` : ""}</div></div>
    <div class="read"><div class="k">sprawdzian ${I.id}</div><div class="v">${ci.cov80_48 === undefined || ci.cov80_48 === null ? "—" : "stożek " + pct(ci.cov80_48)}</div>
      <div class="s">cel 80% · Brier ${ci.brier48 === undefined || ci.brier48 === null ? "—" : num(ci.brier48, 3)} (0,25 = moneta)</div></div>
  </div>`;
}

/** Spływ świec: po jednej komórce na świecę (ostatnie 24 godziny rynku) + świeca, na którą czekamy. */
function tape(list, last) {
  const now = Date.now();
  return `<div class="tape"><span class="hd">instrument</span><span class="hd">ostatnie 24 świece → teraz</span><span class="hd">ostatnia</span><span class="hd x4">następna</span>` +
    list.map(I => {
      const C = (I.candles || []).slice(-24);
      const lastFc = stamp(I.lastCandle), lb = last[I.id] ? last[I.id].t : lastFc;
      const nc = nextClose(I, now);
      const expectedLast = nc - 2 * H;                 // początek świecy, która powinna już być zamknięta
      const late = fxOpen(I.group, now - H) && lb < expectedLast && now - (expectedLast + H) > 3 * 60e3;
      const cells = C.map((c, i) => `<i class="${c[4] >= c[1] ? "u" : "d"}${i === C.length - 1 && now - (c[0] * 1000 + H) < 15 * 60e3 ? " new" : ""}" title="${t.dhm(c[0] * 1000)} · ${c[4]}"></i>`).join("") +
        (lb > lastFc ? `<i class="x" title="w bazie, prognoza jeszcze nie przeliczona"></i>` : "") +
        (fxOpen(I.group, now) ? `<i class="${late ? "wait" : "x"}" title="${late ? "spóźniona świeca" : "świeca trwa"}"></i>` : `<i class="closed"></i>`);
      return `<span><b>${I.id}</b></span><span class="cells">${cells}</span>` +
        `<span class="${late ? "warn" : ""}">${t.hm(lb + H)} <span class="dim" data-ts="${lb + H}">${age((now - lb - H) / 1000)}</span></span>` +
        `<span class="x4 dim">${fxOpen(I.group, now) ? `za <span data-cd="${nc}">${age((nc - now) / 1000, true)}</span>` : "rynek zamknięty"}</span>`;
    }).join("") + `</div>
    <p class="note">komórka = świeca 1h (zielona — wzrost, czerwona — spadek) · ramka = świeca, która jeszcze trwa · migająca ramka = świeca spóźniona (powinna już być) · godzina = zamknięcie ostatniej świecy, PL.</p>`;
}

function scen(I) {
  const c0 = I.lastClose;
  const S = (I.scenarios || []).map(s => {
    const lastv = s.path[s.path.length - 1], vals = s.path.filter(v => v !== null);
    return `<li><span class="t" style="color:${SC_COL[s.name]}">● ${s.name}</span><span class="m">jak po ${t.dhm(stamp(s.from))} (${esc(s.source)}): za 48 świec <b>${inst.chg(I, lastv - c0)}</b>, maks. ${inst.chg(I, Math.max(...vals) - c0)}, min. ${inst.chg(I, Math.min(...vals) - c0)}</span></li>`;
  }).join("");
  const T = (I.activeTop || []).map(c => `<li><span class="t am">${esc(c.id)} · ${c.rating}</span><span class="m">${esc(c.desc)}</span></li>`).join("");
  return `<ul class="log" style="max-height:none">${S.replace(/<li>/g, '<li style="grid-template-columns:110px 1fr">') || `<li><span class="m dim">brak — za mało historii</span></li>`}</ul>
    <div class="desk-only"><p class="note" style="margin:14px 0 6px">okoliczności prawdziwe teraz: ${I.active ?? "—"} (suma ratingów ${I.activeRatingSum ?? "—"}) · najwyższy rating:</p>
    <ul class="log" style="max-height:none">${T.replace(/<li>/g, '<li style="grid-template-columns:110px 1fr">') || `<li><span class="m dim">brak</span></li>`}</ul></div>`;
}

function runs() {
  const R = (store.get("fxruns") || []).slice().reverse();
  if (!R.length) return `<p class="empty">brak przeliczeń</p>`;
  return `<div class="tbl-wrap scroll" style="max-height:300px"><table class="tbl"><thead><tr><th>przeliczenie</th><th>kiedy</th><th>wersja</th><th class="num">świec</th><th class="num">instr.</th>
    <th>model</th><th class="num">λ</th><th class="num">stożek 80%</th><th class="num">Brier k=48</th><th class="num">błąd zakresu</th></tr></thead><tbody>` +
    R.map(r => { const s = r.scenario || {};
      return `<tr><td><b>${esc(r.run)}</b></td><td>${t.short(stamp(r.at))}</td><td>${esc(r.version)}</td><td class="num">${num((r.data || {}).candles)}</td><td class="num">${r.instruments || 1}</td>
        <td>${esc(s.model || "—")}</td><td class="num">${s.lambda ?? "—"}</td><td class="num">${pct(s.cov80_48)}</td><td class="num">${s.brier48 === undefined || s.brier48 === null ? "—" : num(s.brier48, 3)}</td><td class="num">${pct(s.rangeErr)}</td></tr>`; }).join("") +
    `</tbody></table></div><p class="note">R-… — dawne przeliczenia EURUSD 5 min (archiwum) · H-… — świece 1h, 11 instrumentów. Wyniki z części B sprawdzianu (dane niewidziane przez model).</p>`;
}

function fxInvestor() {
  const d = store.get("fxvi");
  if (d && d.summary) return `<div class="c12">${renderInvestor(d, { title: "wirtualny inwestor FX" })}</div>`;
  return `<div class="pane c12 flat"><h2>wirtualny inwestor FX<span class="dim">nieaktywny</span></h2>${help("fx.vi")}
    <p class="empty">Czeka na strategie FX. Gdy FX-research znajdzie reguły z udowodnioną przewagą, Apps Script zacznie wysyłać <b>telemetry/fx-vi.json</b> w tym samym formacie co inwestor akcji — ten panel pokaże wtedy wynik, krzywą, pozycje i transakcje bez zmian w stronie.</p></div>`;
}

export default {
  id: "fx", title: "fx",
  render(el, changed, force) {
    const fc = store.get("forecast");
    if (!fc || !(fc.instruments || []).length) {
      el.innerHTML = `<div class="grid"><div class="pane c12"><h2>FX</h2><p class="empty">${store.meta.forecast && store.meta.forecast.err ? esc(store.meta.forecast.err) + " — " : ""}czekam na forecast.json (uruchom <b>python -m ia4.fx.live</b> na Macu)</p></div>${fxInvestor()}</div>`;
      return;
    }
    const list = fc.instruments, last = fxLast();
    if (!list.find(i => i.id === sel)) sel = list[0].id;
    const I = list.find(i => i.id === sel);
    const on = !fc.stoppedAt && Date.now() - stamp(fc.aliveAt) < 5 * 60e3;
    const m = fc.model || {};
    el.innerHTML = `<div class="grid">
      <div class="pane c12 hero"><h2>prognoza FX<span class="dim">48 świec 1h · rozkład, nie jedna linia</span></h2>${help("fx.hero")}${hero(fc)}</div>
      <div class="pane c3"><h2>instrumenty<span class="dim">${list.length}</span></h2>${help("fx.list")}${rail(list, last)}</div>
      <div class="pane c9 ${on ? "" : "stale"}"><h2>${esc(I.name)}<span class="dim">${METHOD[m.method] || esc(m.method || "")} · ${I.K || "?"} ścieżek</span></h2>
        <svg class="chart" data-chart></svg>
        <div class="legend"><span><i style="background:var(--cyan-dim2)"></i>50% przypadków</span><span><i style="background:var(--cyan-dim)"></i>80% przypadków</span>
          <span><i style="background:var(--cyan);height:2px"></i>środek</span><span><i style="background:linear-gradient(90deg,var(--sc-up),var(--sc-mid),var(--sc-down));height:2px"></i>scenariusze: prawdziwe ścieżki z podobnych chwil</span></div>
        ${detail(fc, I)}</div>
      <div class="pane c7"><h2>spływ świec 1h<span class="dim">na żywo</span></h2>${help("fx.tape")}${tape(list, last)}</div>
      <div class="pane c5"><h2>scenariusze ${esc(I.id)}<span class="dim">co działo się po podobnych chwilach</span></h2>${help("fx.scen")}${scen(I)}</div>
      <div class="pane c12 desk-only"><h2>przeliczenia FX-research<span class="dim">fx/runs.jsonl</span></h2>${help("fx.runs")}${runs()}</div>
      ${fxInvestor()}
    </div>
    <p class="note">Linia środkowa odchyla się od ceny tylko wtedy, gdy sprawdzian na danych niewidzianych przez model potwierdził przewagę (instrukcja 4c.7). Bez połączenia z Makiem prognoza jest wyblakła — to ostatnia znana.</p>`;
    fxChart(el.querySelector("[data-chart]"), I);
    el.querySelector(".rail").addEventListener("click", e => {
      const b = e.target.closest("button[data-id]");
      if (!b) return;
      sel = b.dataset.id; pref.set("fx", sel);
      this.render(el, [], true);
    });
    const d = store.get("fxvi");
    if (d && d.summary) mountInvestor(el, d);
  },
  tick(el) {
    const now = Date.now();
    el.querySelectorAll("[data-ts]").forEach(s => { const ts = +s.dataset.ts; if (ts) s.textContent = age((now - ts) / 1000); });
    el.querySelectorAll("[data-cd]").forEach(s => { s.textContent = age(Math.max(0, (+s.dataset.cd - now) / 1000), true); });
  },
};
