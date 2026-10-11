// IA 4 — zakładka System: czy wszystko żyje, strumień zdarzeń, parametry, instrumenty.
// Wersja projektu: 1.30 (2026-10-11)

import { store, SOURCES, VERSION, age, num, pct, esc, t, nyseOpen, fxOpen, stockClose, plStamp } from "../core.js";
import { nodes, fxLast, stamp } from "../health.js";

const MIN = 60e3, H = 3600e3;
const LIMIT_MIN = 90;                  // Apps Script (konto Gmail): 90 min triggerów dziennie
const seen = new Set();                // zdarzenia już pokazane (podświetlenie nowych)
let firstPaint = true;

const led = s => `<span class="led ${s}${s === "ok" ? " beat" : ""}"></span>`;
const ageCell = ts => `<span data-ts="${isFinite(ts) ? ts : ""}">${isFinite(ts) ? age((Date.now() - ts) / 1000) : "—"}</span>`;
const mmss = s => s === null || s === undefined ? "—" : `${s < 0 ? "−" : "+"}${Math.floor(Math.abs(s) / 60)}:${String(Math.abs(s) % 60).padStart(2, "0")}`;

/** Następne zamknięcie świecy akcji (sesja NYSE, świece co godzinę od 9:30, ostatnia o 16:00). */
function nextStockClose(now) {
  if (!nyseOpen(now)) return null;
  const p = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "numeric", second: "numeric", hour12: false }).formatToParts(now);
  const g = k => +p.find(x => x.type === k).value;
  const m = (g("hour") % 24) * 60 + g("minute") + g("second") / 60;
  const next = Math.min(570 + Math.ceil((m - 570 + 1e-9) / 60) * 60, 960);
  return now + (next - m) * MIN;
}
const nextHour = now => Math.ceil((now + 1) / H) * H;

function components() {
  const st = store.get("state") || {}, vi = store.get("vi"), fc = store.get("forecast"), runs = store.get("fxruns"), rs = store.get("research");
  const N = Object.fromEntries(nodes().map(n => [n.id, n]));
  const now = Date.now(), rows = [];
  const run = st.collector && st.collector.lastRun;
  rows.push({ name: "Automat (Apps Script)", s: N.gas.status, ts: run ? stamp(run.at) : NaN, every: "co minutę",
    detail: run ? `${esc(run.action || "")}${run.ok === false ? " · <span class='bad'>błąd</span>" : ""}` : "brak telemetrii" });
  const lc = st.lastCandle;
  const nx = nextStockClose(now);
  rows.push({ name: "Zbieranie akcji (75)", s: lc ? (nyseOpen(now) && now - stockClose(lc.key) > 2 * H ? "warn" : "ok") : "off",
    ts: lc ? stockClose(lc.key) : NaN, every: "świeca co 1 h w sesji",
    detail: lc ? `świeca ${String(lc.key).replace(/(\d{4})(\d{2})(\d{2})(\d)/, "$1-$2-$3 #$4")} · ${lc.written}/75 zapisane w ${mmss(lc.all75)}` +
      (lc.missing && lc.missing.length ? ` · <span class="warn">brak: ${esc(lc.missing.join(", "))}</span>` : "") +
      ` · ${nx ? `następna za <span data-cd="${nx}">${age((nx - now) / 1000, true)}</span>` : "NYSE zamknięta"}` : "—" });
  const f = st.fx || {};
  if (f.interval === "1h") {
    const nh = nextHour(now);
    rows.push({ name: "Zbieranie FX 1h (11)", s: !f.lastWriteAt ? "off" : now - stamp(f.lastWriteAt) < 2 * H ? "ok" : "warn",   // BTC zapisuje co godzinę także w weekend
      ts: stamp(f.lastWriteAt), every: "świeca co 1 h",
      detail: `historia ${esc(f.history || "—")} · aktualne ${f.upToDate ?? "—"}/${f.instruments || 11} · opóźnienie ${f.lastDelaySec ?? "—"} s` +
        (f.today ? ` · dziś ${f.today.bars} świec, braki ${f.today.missing}` : "") + ` · następna za <span data-cd="${nh}">${age((nh - now) / 1000, true)}</span>` });
  } else {
    rows.push({ name: "Zbieranie FX", s: "warn", ts: stamp(f.lastWriteAt), every: "—",
      detail: "Apps Script w starej wersji (EURUSD 5 min) — podmień pliki .gs na 1.27+" });
  }
  const viT = vi ? stamp(vi.generatedAt) : NaN, sv = vi ? vi.summary : st.vi;
  rows.push({ name: "Paper trading · inwestor", s: vi ? "ok" : st.vi ? "warn" : "off", ts: vi ? plStamp(vi.lastCandlePL) : NaN, every: "po każdej świecy akcji",
    detail: sv ? `zamkniętych ${sv.closed} · otwartych ${sv.open}${sv.pending !== undefined ? ` · oczekuje ${sv.pending}` : ""}` + (vi ? ` · świeca ${esc(vi.lastCandlePL)}` : " · <span class='warn'>vi.json jeszcze nie opublikowany</span>") : "—" });
  rows.push({ name: "Telemetria → GitHub", s: N.gh.status, ts: stamp(st.generatedAt), every: "co godzinę i po świecy", detail: `telemetry/state.json · wersja ${esc(st.version || "—")}` });
  const ni = st.nightly;
  rows.push({ name: "Nocne odświeżenie", s: ni ? (now - stamp(ni.at) < 4 * 86400e3 ? "ok" : "warn") : "off", ts: ni ? stamp(ni.at) : NaN, every: "po każdej sesji",
    detail: ni ? `sesja ${esc(ni.date)} · przepisanych ${num(ni.written)}` : "—" });
  rows.push({ name: "FX-real-time (Mac)", s: N.mac.status, ts: fc ? stamp(fc.aliveAt) : NaN, every: "sygnał co 2 min",
    detail: fc ? `${N.mac.sub} · prognoza ${t.short(stamp(fc.generatedAt))} · ratingi ${esc((fc.ratings || {}).run || "—")} · odczyty Firestore dziś ${fc.firestoreReadsToday ?? "—"}` : "brak forecast.json" });
  const lr = runs && runs.length ? runs[runs.length - 1] : null;
  rows.push({ name: "FX-research (Mac, ręcznie)", s: lr ? "ok" : "off", ts: lr ? stamp(lr.at) : NaN, every: "ręcznie",
    detail: lr ? `przeliczenie ${esc(lr.run)} · ${num((lr.data || {}).candles)} świec · wersja ${esc(lr.version)}` : "—" });
  rows.push({ name: "Poszukiwanie strategii", s: "off", ts: rs ? stamp(rs.updatedAt) : NaN, every: "wstrzymane",
    detail: rs ? `wstrzymane od 3.10.2026 · ostatnio faza „${esc(rs.phase || "")}” · ${num((rs.totals || {}).accepted)} przyjętych` : "wstrzymane" });
  rows.push({ name: "Ta strona", s: N.web.status, ts: N.web.ts, every: "co 30–60 s", detail: esc(N.web.sub) });
  return rows;
}

/** Zdarzenia ze wszystkich źródeł w jednej osi czasu (najnowsze na górze). */
function events() {
  const E = [], st = store.get("state"), vi = store.get("vi"), fc = store.get("forecast"), commits = store.get("commits"), runs = store.get("fxruns");
  (commits || []).slice(0, 20).forEach(c => {
    const msg = c.commit.message.split("\n")[0];
    E.push({ t: stamp(c.commit.committer.date), src: "git", cls: msg.startsWith("Stan bazy") || msg.startsWith("VI ") ? "dim" : "", m: esc(msg), k: "c" + c.sha });
  });
  if (st && st.lastCandle) {
    const lc = st.lastCandle, k = String(lc.key).replace(/(\d{4})(\d{2})(\d{2})(\d)/, "$1-$2-$3 #$4");
    E.push({ t: stockClose(lc.key) + (lc.all75 || 0) * 1000, src: "akcje", cls: "ok", k: "s" + lc.key,
      m: `świeca ${k}: ${lc.written}/75 zapisane w ${mmss(lc.all75)}, sygnały ${mmss(lc.signals)}, arkusze ${mmss(lc.sheets)}` });
  }
  if (st && st.nightly) E.push({ t: stamp(st.nightly.at), src: "noc", cls: "dim", k: "n" + st.nightly.at, m: `nocne odświeżenie sesji ${esc(st.nightly.date)} · ${num(st.nightly.written)} zapisów` });
  if (fc) (fc.instruments || []).forEach(I => {
    const c = I.candles && I.candles[I.candles.length - 1], p = I.candles && I.candles[I.candles.length - 2];
    if (!c) return;
    const d = p ? c[4] - p[4] : 0;
    E.push({ t: (c[0] + 3600) * 1000, src: "fx", cls: "cy", k: "f" + I.id + c[0],
      m: `${I.id} świeca ${t.hm(c[0] * 1000)}–${t.hm((c[0] + 3600) * 1000)} · ${c[4]} <span class="${d >= 0 ? "up" : "down"}">${d >= 0 ? "▲" : "▼"}</span>` });
  });
  if (fc && fc.stoppedAt) E.push({ t: stamp(fc.stoppedAt), src: "mac", cls: "", k: "x" + fc.stoppedAt, m: "FX-real-time zatrzymany (Ctrl+C)" });
  if (vi) {
    (vi.closed || []).slice(0, 12).forEach(p => E.push({ t: plStamp(p.exitAt), src: "vi", cls: "", k: "vc" + p.no,
      m: `zamknięta #${p.no} ${esc(p.sym)} ${p.dir} (${esc(p.id)}) · ${esc(p.kind)} <span class="${p.retPct >= 0 ? "up" : "down"}">${p.retPct >= 0 ? "+" : ""}${num(p.retPct, 2)}%</span>` }));
    (vi.open || []).filter(p => p.entryAt).slice(0, 12).forEach(p => E.push({ t: plStamp(p.entryAt), src: "vi", cls: "", k: "vo" + p.no,
      m: `otwarta #${p.no} ${esc(p.sym)} ${p.dir} po ${num(p.entry, 2)} (${esc(p.id)})` }));
    (vi.signals || []).filter(s => s.fired.length).slice(0, 8).forEach(s => E.push({ t: plStamp(s.at), src: "sygnał", cls: "", k: "g" + s.key,
      m: `${s.fired.length} sygn.: ${esc(s.fired.slice(0, 6).map(f => f[1]).join(", "))}${s.fired.length > 6 ? "…" : ""}` }));
  }
  (runs || []).slice(-3).forEach(r => E.push({ t: stamp(r.at), src: "research", cls: "", k: "r" + r.run, m: `FX-research ${esc(r.run)} · model ${esc((r.scenario || {}).model || "—")}` }));
  return E.filter(e => isFinite(e.t)).sort((a, b) => b.t - a.t).slice(0, 60);
}

function params() {
  const st = store.get("state") || {}, c = st.collector || {}, td = c.today || {};
  const runMin = td.runMs ? td.runMs / 60000 : null, use = runMin === null ? 0 : runMin / LIMIT_MIN;
  const ver = st.version, vOk = !ver || ver === VERSION;
  const err = c.lastError;
  return `<div class="reads">
    <div class="read"><div class="k">wersja systemu</div><div class="v ${vOk ? "" : "warn"}">${esc(ver || "—")}</div><div class="s">${vOk ? "zgodna ze stroną" : `strona ${VERSION} — podmień pliki .gs`}</div></div>
    <div class="read"><div class="k">czas pracy automatu dziś</div><div class="v">${runMin === null ? "—" : num(runMin, 1) + " min"}</div>
      <div class="meter ${use > .85 ? "bad" : use > .65 ? "warn" : ""}"><i style="width:${Math.min(100, 100 * use)}%"></i></div><div class="s">limit Google ${LIMIT_MIN} min · ${pct(use)}</div></div>
    <div class="read"><div class="k">uruchomień dziś</div><div class="v">${num(td.runs)}</div><div class="s">dzień ${esc(td.date || "—")} (NY)</div></div>
    <div class="read"><div class="k">świec zapisanych dziś</div><div class="v">${num(td.candles)}</div><div class="s">akcje</div></div>
    <div class="read"><div class="k">błędów dziś</div><div class="v ${td.errors ? "warn" : ""}">${num(td.errors)}</div><div class="s">${err ? "ostatni " + t.short(stamp(err.at)) : "brak"}</div></div>
    <div class="read"><div class="k">świec akcji w bazie</div><div class="v">${st.base ? num(st.base.totalCandles) : "—"}</div><div class="s">${st.base ? "liczone " + t.short(stamp(st.base.countedAt)) : ""}</div></div>
  </div>
  ${err ? `<p class="note">ostatni błąd (${t.dhm(stamp(err.at))}): <b>${esc(err.text)}</b></p>` : ""}
  <p class="note">etap: ${esc(st.stage || "—")}</p>`;
}

/** Ostatnia świeca akcji: kiedy który etap był gotowy (sekundy od zamknięcia). */
function stockFlow() {
  const st = store.get("state"), lc = st && st.lastCandle;
  if (!lc) return `<p class="empty">brak danych o ostatniej świecy</p>`;
  const steps = [["start automatu", lc.start], ["3 główne spółki", lc.main3], ["53 handlowane", lc.traded53], ["75 spółek", lc.all75],
                 ["sygnały strategii", lc.signals], ["arkusze SIGNALS i VI", lc.sheets]];
  const max = Math.max(240, ...steps.map(s => s[1] || 0));
  return `<div class="tape" style="grid-template-columns: 150px 1fr 60px">` + steps.map(([n, s]) =>
    `<span class="ink2">${n}</span><span class="cells" style="height:10px"><i class="u" style="flex:none;max-width:none;width:${s === null ? 0 : Math.max(2, 100 * s / max)}%"></i></span><span class="num">${mmss(s)}</span>`).join("") +
    `</div><p class="note">świeca ${String(lc.key).replace(/(\d{4})(\d{2})(\d{2})(\d)/, "$1-$2-$3 #$4")} · czas od zamknięcia świecy · rund Yahoo ${lc.rounds} · etapy: ` +
    Object.entries(lc.stagesMs || {}).map(([k, v]) => `${esc(k)} ${num(v / 1000, 1)} s`).join(", ") + `</p>`;
}

function matrix() {
  const st = store.get("state"), vi = store.get("vi");
  const list = (st && st.instruments) || [];
  if (!list.length) return `<p class="empty">brak listy instrumentów</p>`;
  const lastDay = list.map(i => (i.last || "").slice(0, 10)).sort().pop();
  const pos = new Set(((vi && vi.open) || []).map(p => p.sym));
  const grp = { main: "główne", proof: "kontrolne", context: "tło rynku", doubleProof: "doubleProof" };
  let h = "";
  for (const g of Object.keys(grp)) {
    const L = list.filter(i => i.group === g);
    if (!L.length) continue;
    h += `<p class="note" style="margin:10px 0 6px">${grp[g]} · ${L.length}</p><div class="matrix">` + L.map(i =>
      `<div class="cell grp-${g}${(i.last || "").slice(0, 10) < lastDay ? " stale" : ""}${pos.has(i.symbol) ? " pos" : ""}" title="${esc(i.symbol)} · ${esc(i.last)} · ${num(i.candles)} świec od ${esc(i.first)} · ${esc(i.status)}">` +
      `<b>${esc(i.symbol)}</b><span class="q">${num(i.lastClose, 2)} · ${esc((i.last || "").slice(11))}</span></div>`).join("") + `</div>`;
  }
  const fx = fxLast();
  const ids = Object.keys(fx);
  if (ids.length) h += `<p class="note" style="margin:12px 0 6px">FX 1h · ${ids.length}</p><div class="matrix">` + ids.map(id =>
    `<div class="cell"><b>${esc(id)}</b><span class="q">${fx[id].close ?? "—"}</span><span class="q">${isFinite(fx[id].t) ? "świeca " + t.hm(fx[id].t) : "—"}</span></div>`).join("") + `</div>`;
  return h + `<p class="note">▪ = otwarta pozycja inwestora · ramka przerywana = brak świecy z ostatniego dnia</p>`;
}

function sources() {
  return `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>źródło</th><th>stan</th><th>pobrane</th><th>zmiana</th></tr></thead><tbody>` +
    Object.entries(SOURCES).map(([id, S]) => {
      const m = store.meta[id] || {};
      const s = !m.at ? "off" : m.ok ? "ok" : m.err === "brak pliku" ? "off" : "warn";
      return `<tr><td>${esc(S.label)}</td><td>${led(s)} ${esc(m.ok ? "ok" : m.err || "czekam")}</td><td>${ageCell(m.at)}</td><td>${ageCell(m.changedAt)}</td></tr>`;
    }).join("") + `</tbody></table></div>`;
}

export default {
  id: "system", title: "system",
  render(el) {
    const C = components(), E = events();
    const fresh = E.filter(e => !seen.has(e.k));
    el.innerHTML = `<div class="grid">
      <div class="pane c7 hero"><h2>stan składników<span class="dim">${C.filter(c => c.s === "ok").length}/${C.length} ok</span></h2>
        <div class="tbl-wrap"><table class="tbl"><thead><tr><th>składnik</th><th>ostatni znak życia</th><th class="desk-only">rytm</th><th class="desk-only">szczegóły</th></tr></thead><tbody>` +
        C.map(c => `<tr><td>${led(c.s)} ${c.name}</td><td>${ageCell(c.ts)} <span class="dim">temu</span></td><td class="desk-only dim">${c.every}</td><td class="desk-only wrap">${c.detail}</td></tr>`).join("") +
        `</tbody></table></div></div>
      <div class="pane c5"><h2>strumień zdarzeń<span class="dim">tail -f · ${E.length}</span></h2>
        <ul class="log">${E.map(e => `<li class="${!firstPaint && fresh.includes(e) ? "new" : ""}"><span class="t">${t.short(e.t)}</span><span class="src ${e.cls}">${e.src}</span><span class="m">${e.m}</span></li>`).join("") || `<li><span class="m dim">czekam na dane…</span></li>`}</ul></div>
      <div class="pane c7"><h2>parametry</h2>${params()}</div>
      <div class="pane c5"><h2>ostatnia świeca akcji<span class="dim">spływ</span></h2>${stockFlow()}</div>
      <div class="pane c8 desk-only"><h2>instrumenty</h2>${matrix()}</div>
      <div class="pane c4 desk-only"><h2>źródła danych</h2>${sources()}</div>
    </div>`;
    E.forEach(e => seen.add(e.k));
    if (E.length) firstPaint = false;
  },
  tick(el) {
    const now = Date.now();
    el.querySelectorAll("[data-ts]").forEach(s => { const ts = +s.dataset.ts; if (ts) s.textContent = age((now - ts) / 1000); });
    el.querySelectorAll("[data-cd]").forEach(s => { s.textContent = age(Math.max(0, (+s.dataset.cd - now) / 1000), true); });
  },
};
