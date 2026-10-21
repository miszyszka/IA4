// IA 4 — zakładka AI: agenci na Macu — praca agentów, portfel Inwestora, Krytyk, Badacz, feed (instrukcja, sekcja 8–9).
// Wersja projektu: 1.59 (2026-10-21)
//
// Źródła: ai-live/status.json (sygnał życia: nadzorca, feed, agenci, praca agentów `work`, portfel, pozycje, ostatnia runda,
// punkty odniesienia, krzywa, notatki, `critic`, `research`) oraz branch ai: trades.jsonl, playbook.json, lessons.json.

import { store, num, esc, age, t, usd, sgn, cls, pct } from "../core.js";
import { help } from "../help.js";
import { stamp } from "../health.js";
import { equity } from "../chart.js";

const MIN = 60e3;
const ALIVE_OK = 11 * MIN;               // status.json co 5 min — dwa sygnały z zapasem
const LAG_OK = 120;                      // kryterium AI-1: świeca w kopii ≤ 2 min po zapisie w Firestore
const seen = new Set();
let firstPaint = true;

const led = s => `<span class="led ${s}${s === "ok" ? " beat" : ""}"></span>`;
const mmss = s => s === null || s === undefined ? "—" : `${s < 0 ? "−" : "+"}${Math.floor(Math.abs(s) / 60)}:${String(Math.abs(s) % 60).padStart(2, "0")}`;
const KIND = { start: "start", stop: "stop", sync: "sync", ollama: "model", fx: "fx", "fx-late": "fx", stocks: "akcje",
               "stocks-late": "akcje", "stocks-night": "noc", error: "błąd", round: "runda", trade: "pozycja", investor: "inwestor",
               playbook: "playbook", halt: "STOP", restore: "hub", hypothesis: "hipoteza", review: "Krytyk" };
const KCLS = { fx: "cy", "fx-late": "cy", stocks: "ok", "stocks-late": "ok", error: "", "stocks-night": "dim", sync: "dim", round: "am", trade: "am",
               hypothesis: "ag-researcher", review: "ag-critic" };
const NOTE = { decyzja: "decyzja", pozycja: "pozycja", runda: "runda", "wejście": "wejście", "wyjście": "wyjście", "przegląd": "Krytyk" };
const AG = { investor: "Inwestor", critic: "Krytyk", researcher: "Badacz", system: "dyspozytor" };
const dir = d => d === "long" ? "▲ long" : "▼ short";
const px = (v, d = 2) => v === null || v === undefined ? "—" : num(v, d);
const pxd = p => p.kind === "stock" ? 2 : Math.min(p.digits || 5, 6);

export function aiState(ai, now = Date.now()) {
  if (!ai) return { s: "off", text: "nie uruchomiony" };
  if (ai.stoppedAt) return { s: "off", text: "zatrzymany" };
  return now - stamp(ai.aliveAt) < ALIVE_OK ? { s: "ok", text: "połączony" } : { s: "bad", text: "offline" };
}

function hero(ai) {
  const now = Date.now(), st = aiState(ai, now), alive = stamp(ai.aliveAt), start = stamp(ai.startedAt);
  const ol = ai.ollama || {}, mc = ai.machine || {}, inMem = (ol.loaded || []).find(m => m.name === ol.model);
  const model = ol.skipped ? "nie sprawdzany" : ol.present ? "gotowy" : "brak";
  return `<div class="reads">
    <div class="read"><div class="k">Mac · AI Investor</div><div class="v ${st.s === "ok" ? "ok" : st.s === "bad" ? "bad" : ""}">${st.text}</div>
      <div class="s">sygnał <span data-ts="${alive}">${age((now - alive) / 1000)}</span> temu</div></div>
    <div class="read"><div class="k">działa od</div><div class="v">${isFinite(start) ? t.hm(start) : "—"}</div>
      <div class="s">${isFinite(start) ? esc(t.dhm(start)) : ""}${ai.stoppedAt ? " · zatrzymany " + t.short(stamp(ai.stoppedAt)) : ""}</div></div>
    <div class="read"><div class="k">krok</div><div class="v">${esc(ai.step || "—")}</div><div class="s">wersja ${esc(ai.version || "—")} · ${esc(ai.host || "")}</div></div>
    <div class="read"><div class="k">model językowy</div><div class="v ${ol.present ? "" : ol.skipped ? "" : "warn"}">${esc(ol.model || "—")}</div>
      <div class="s">${model}${ol.version ? " · Ollama " + esc(ol.version) : ""}${inMem ? ` · w pamięci ${num(inMem.sizeGB, 1)} GB` : ol.present ? " · nie załadowany" : ""}</div></div>
    <div class="read"><div class="k">odczyty Firestore dziś</div><div class="v">${num((ai.feed || {}).readsToday)}</div><div class="s">akcje + FX (limit 50 000)</div></div>
    <div class="read"><div class="k">Mac</div><div class="v">${mc.memGB ? mc.memGB + " GB" : "—"}</div>
      <div class="s">${mc.cpus || "?"} rdzeni${mc.load ? " · obciążenie " + mc.load.map(x => num(x, 1)).join(" / ") : ""}</div></div>
  </div>`;
}

// ------------------------------------------------------------------ portfel
function level(n) {
  return `<span class="lvl" title="poziom nauki ${n} z 3">${[1, 2, 3].map(i => `<i class="${i <= n ? "on" : ""}"></i>`).join("")}</span>`;
}

function portfolio(I, C) {
  const p = I.portfolio || {}, b = I.bench || {}, inv = b.investor || {}, ex = (C || {}).explore;
  const cap = I.capital || 100000, total = p.equity - cap;
  return `<div class="reads">
    <div class="read"><div class="k">stan konta</div><div class="v ${cls(total)}">${num(p.equity, 0)} $</div><div class="s">${sgn(100 * total / cap, 2)}% od ${I.startedAt ? t.dm(stamp(I.startedAt)) : "startu"} · kapitał ${num(cap, 0)} $</div></div>
    <div class="read"><div class="k">zrealizowany / otwarte</div><div class="v ${cls(p.realized)}">${usd(p.realized, 0)}</div><div class="s">otwarte ${usd(p.unrealized, 0)} · koszty ${num(p.costs, 0)} $</div></div>
    <div class="read"><div class="k">śr. wynik transakcji</div><div class="v ${cls(inv.avg)}">${inv.avg === null || inv.avg === undefined ? "—" : sgn(inv.avg, 2) + "%"}</div>
      <div class="s">${inv.n || 0} zamkniętych z playbooka${inv.ci95 ? ` · 95%: ±${num(inv.ci95, 2)}` : ""}</div></div>
    <div class="read"><div class="k">pozycje</div><div class="v">${p.open ?? 0}<small class="dim"> + ${p.pending ?? 0} oczek.</small></div><div class="s">limit 12 · ekspozycja ${num(p.grossPct, 0)}%</div></div>
    <div class="read"><div class="k">ryzyko otwarte</div><div class="v">${num(p.riskPct, 2)}%</div>
      <div class="meter ${p.riskPct > 5 ? "warn" : ""}"><i style="width:${Math.min(100, 100 * (p.riskPct || 0) / 6)}%"></i></div><div class="s">budżet 6% · risk_dial ${num(p.dial, 2)}</div></div>
    <div class="read"><div class="k">obsunięcie</div><div class="v ${p.ddPct >= 10 ? "bad" : p.ddPct >= 5 ? "warn" : ""}">${num(p.ddPct, 2)}%</div><div class="s">doba UTC ${sgn(p.dayPct, 2)}% · stop −2%</div></div>
    ${ex ? `<div class="read"><div class="k">poziom nauki</div><div class="v">${ex.level}${level(ex.level)}</div>
      <div class="s">${esc(ex.name)} · bez wejścia ${ex.passive} rund${ex.auto ? " · podniósł automat bierności" : ""}</div></div>` : ""}
  </div>${(p.blocks || []).length ? `<p class="note"><b class="bad">${esc(p.blocks.join(" · "))}</b></p>` : ""}`;
}

function track(p) {
  if (!p.sl || !p.tp || p.price === null || p.price === undefined) return `<span class="dim">${p.status === "pending" ? "wejście na otwarciu" : "—"}</span>`;
  const lo = Math.min(p.sl, p.tp), hi = Math.max(p.sl, p.tp), f = x => Math.max(0, Math.min(1, (x - lo) / (hi - lo || 1)));
  const flip = p.dir === "short";                               // short: TP po lewej — odwracamy, żeby zawsze SL ─ TP
  const pos = x => 100 * (flip ? 1 - f(x) : f(x));
  return `<span class="track" title="SL ${p.sl} · wejście ${p.entry} · teraz ${p.price} · TP ${p.tp}"><b style="left:${pos(p.entry)}%"></b><i style="left:calc(${pos(p.price)}% - 1px)"></i></span>`;
}

function noteCell(text, n = 90) {
  if (!text) return `<span class="dim">—</span>`;
  return text.length <= n ? esc(text) : `<details class="nt"><summary>${esc(text.slice(0, n))}…</summary>${esc(text)}</details>`;
}

function positions(I) {
  const L = I.positions || [];
  if (!L.length) return `<p class="empty">brak otwartych i oczekujących pozycji</p>`;
  return `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>#</th><th>instrument</th><th>kier.</th><th class="desk-only">podstawa</th><th class="desk-only">wejście</th>
    <th class="num desk-only">cena wej.</th><th class="num desk-only">teraz</th><th class="num">wynik</th><th class="num desk-only">$</th><th class="num desk-only">R</th>
    <th class="desk-only">SL ─ TP</th><th class="num desk-only">świec</th><th class="num desk-only">pewn.</th><th class="desk-only">dlaczego</th></tr></thead><tbody>` +
    L.map(p => { const d = pxd(p);
      return `<tr><td class="dim">${p.no}</td><td><b>${esc(p.inst)}</b></td><td>${dir(p.dir)}</td><td class="desk-only">${esc(p.basis)}</td>
        <td class="desk-only">${p.entryAt ? t.short(stamp(p.entryAt)) : `<span class="am">oczekuje</span>`}</td><td class="num desk-only">${px(p.entry, d)}</td>
        <td class="num desk-only">${px(p.price, d)}</td><td class="num ${cls(p.pct)}">${p.status === "pending" ? "—" : sgn(p.pct, 2) + "%"}</td>
        <td class="num desk-only ${cls(p.pnl)}">${p.status === "pending" ? "" : usd(p.pnl, 0)}</td><td class="num desk-only">${p.status === "pending" ? "" : sgn(p.R, 2)}</td>
        <td class="desk-only">${track(p)}</td><td class="num desk-only">${p.bars}${p.maxBars ? `/${p.maxBars}` : ""}</td>
        <td class="num desk-only">${p.confidence ?? "—"}</td><td class="desk-only wrap">${p.closeReq ? `<span class="am">zamknięcie zlecone</span> ` : ""}${noteCell(p.note)}${p.hypothesis ? `<br><span class="dim">hipoteza:</span> ${noteCell(p.hypothesis, 80)}` : ""}</td></tr>`; }).join("") +
    `</tbody></table></div>`;
}

function lastRound(I) {
  const r = I.lastRound;
  if (!r) return `<p class="empty">jeszcze żadnej rundy — pierwsza po najbliższej świecy akcji albo godzinie FX</p>`;
  const rows = [...(r.decisions || []), ...(r.ownIdeas || []), ...(r.positions || []).filter(d => d.action !== "hold")];
  const verb = { enter: "wchodzę", skip: "pomijam", hold: "trzymam", close: "zamykam", tighten_sl: "zacieśniam SL" };
  return `<p class="note" style="margin-top:0"><b>${esc(r.id)}</b> · ${esc(r.candle)} · ${t.short(stamp(r.at))} · kandydatów ${(r.candidates || []).length}` +
    `${r.llm ? ` · model ${num(r.llm.sec, 0)} s, ${r.llm.promptTokens ?? "?"} tok. briefu${r.llm.attempts > 1 ? `, prób ${r.llm.attempts}` : ""}` : " · bez modelu"}` +
    `${r.explore !== undefined && r.explore !== null ? ` · poziom nauki ${r.explore}` : ""}</p>` +
    (r.roundNote ? `<p class="note"><b>notatka rundy:</b> ${esc(r.roundNote)}</p>` : "") +
    (rows.length ? `<ul class="log" style="max-height:420px">` + rows.map(d =>
      `<li><span class="t">${esc(d.ref === "own" ? "własny" : d.ref)}</span><span class="src ${d.action === "enter" ? "am" : "dim"}">${esc(verb[d.action] || d.action)}</span>` +
      `<span class="m"><b>${esc(d.inst)}</b> ${esc(d.dir)} · ${esc(d.basis)}${d.confidence !== null && d.confidence !== undefined ? ` · pewność ${d.confidence}` : ""}<br>` +
      `${esc(d.note)}${d.hypothesis ? `<br><span class="dim">hipoteza:</span> ${esc(d.hypothesis)}` : ""}${d.outcome && !["pominięte", "bez zmian"].includes(d.outcome) ? `<br><span class="${d.outcome.startsWith("odrzucone") ? "warn" : "ok"}">→ ${esc(d.outcome)}</span>` : ""}</span></li>`).join("") + `</ul>`
      : `<p class="empty">brak decyzji w tej rundzie</p>`) +
    ((r.skipped || []).length ? `<p class="note">pominięte przez kod: ${esc(r.skipped.slice(0, 6).join("; "))}</p>` : "");
}

function trades() {
  const L = (store.get("aitrades") || []).slice().reverse().slice(0, 60);
  if (!L.length) return `<p class="empty">brak zamkniętych transakcji (ai/trades.jsonl)</p>`;
  return `<div class="tbl-wrap scroll"><table class="tbl"><thead><tr><th>#</th><th>instrument</th><th>kier.</th><th>podstawa</th><th>wejście</th><th>wyjście</th><th>powód</th>
    <th class="num">wynik</th><th class="num">$</th><th class="num">R</th><th class="num">pewn.</th><th>dlaczego weszłem</th><th>wyjście</th></tr></thead><tbody>` +
    L.map(p => `<tr><td class="dim">${p.no}</td><td><b>${esc(p.inst)}</b></td><td>${p.dir === "long" ? "▲" : "▼"}</td><td>${esc(p.basis)}</td>
      <td>${t.short(stamp(p.entryAt))}</td><td>${t.short(stamp(p.exitAt))}</td><td><span class="tag ${p.reason === "TP" ? "cy" : ""}">${esc(p.reason)}${p.gap ? " (luka)" : ""}</span></td>
      <td class="num ${cls(p.retPct)}">${sgn(p.retPct, 2)}%</td><td class="num ${cls(p.pnlUsd)}">${usd(p.pnlUsd, 0)}</td><td class="num">${sgn(p.R, 2)}</td>
      <td class="num">${p.confidence ?? "—"}</td><td class="wrap">${noteCell(p.noteIn, 70)}${p.hypothesis ? `<br><span class="dim">hipoteza:</span> ${noteCell(p.hypothesis, 60)}` : ""}</td><td class="wrap">${noteCell(p.noteOut, 50)}</td></tr>`).join("") +
    `</tbody></table></div>`;
}

function bench(I) {
  const b = I.bench || {};
  const row = (name, s, hint) => `<tr><td>${name}</td><td class="num">${s && s.n ? s.n : 0}</td><td class="num ${cls(s && s.avg)}">${s && s.avg !== null && s.avg !== undefined ? sgn(s.avg, 2) + "%" : "—"}</td>
    <td class="num">${s && s.ci95 ? "±" + num(s.ci95, 2) : "—"}</td><td class="num desk-only">${s && s.win !== null && s.win !== undefined ? pct(s.win) : "—"}</td><td class="dim wrap desk-only">${hint}</td></tr>`;
  const r = b.random, m = b.mechanical, spy = b.spy;
  return `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>na transakcję, netto</th><th class="num">n</th><th class="num">śr.</th><th class="num">95%</th><th class="num desk-only">zysk.</th><th class="desk-only"></th></tr></thead><tbody>` +
    row("Inwestor (kandydaci)", b.investor, "wybór i zarządzanie modelu") + row("Inwestor — własne pomysły", b.own, "osobny budżet 2%") +
    row("wszyscy kandydaci", b.all, "każdy sygnał bez limitów (cienie)") +
    `<tr><td>losowy wybór</td><td colspan="5" class="wrap">${r ? `percentyl Inwestora <b>${num(r.pctl, 0)}</b> · losowo śr. ${sgn(r.randomAvg, 2)}% (95%: ${sgn(r.lo, 2)} … ${sgn(r.hi, 2)}) · ${r.rounds} rund` : "<span class='dim'>czeka na rundy z zamkniętymi cieniami</span>"}</td></tr>` +
    `<tr><td>mechaniczny inwestor</td><td colspan="5">${m && m.avgPct !== null && m.avgPct !== undefined ? `${m.closed} zamkniętych · śr. ${sgn(m.avgPct, 2)}%${m.ci95Pct ? ` ± ${num(m.ci95Pct, 2)}` : ""}` : "<span class='dim'>brak danych</span>"}</td></tr>` +
    `<tr><td>SPY kup i trzymaj</td><td colspan="5">${spy ? sgn(spy.pct, 2) + "% od startu" : "—"}</td></tr></tbody></table></div>` +
    `<p class="note"><b>${esc(b.verdict || "")}</b>${(b.calibration || []).length ? " · kalibracja: " + b.calibration.map(c => `pewność ${c.from}–${c.to}: ${c.n} trans., zyskownych ${pct(c.win)}`).join(" · ") : ""}</p>`;
}

function playbook() {
  const pb = store.get("aipb");
  const L = (pb && pb.strategies) || [];
  if (!L.length) return `<p class="empty">brak ai/playbook.json</p>`;
  return `<div class="tbl-wrap scroll" style="max-height:420px"><table class="tbl"><thead><tr><th class="num">pierw.</th><th>ID</th><th>status</th><th class="num">mnożnik</th><th>reguła</th>
    <th class="num">szac. %</th><th class="num">dP n</th><th class="num">dP śr.</th><th class="num">AI n</th><th class="num">AI $</th></tr></thead><tbody>` +
    L.map(s => `<tr><td class="num">${s.priority}</td><td>${esc(s.id)}</td><td>${esc(s.status)}</td><td class="num">${num(s.mult, 2)}</td><td class="wrap">${esc(s.desc)}</td>
      <td class="num">${s.est_pct === null || s.est_pct === undefined ? "—" : sgn(s.est_pct, 2)}</td><td class="num">${(s.dp || {}).n ?? "—"}</td>
      <td class="num ${cls((s.dp || {}).avg)}">${(s.dp || {}).avg === undefined || (s.dp || {}).avg === null ? "—" : sgn(s.dp.avg, 2)}</td>
      <td class="num">${s.ai.n || ""}</td><td class="num ${cls(s.ai.usd)}">${s.ai.n ? usd(s.ai.usd, 0) : ""}</td></tr>`).join("") + `</tbody></table></div>`;
}

function lessons() {
  const L = store.get("ailessons") || [];
  if (!L.length) return `<p class="empty">brak ai/lessons.json</p>`;
  return `<ol class="lessons">${L.map(x => `<li>${esc(x.text)} <span class="dim">— ${esc(x.author)}</span></li>`).join("")}</ol>`;
}

// ------------------------------------------------------------------ praca agentów (1.41)
const dur = s => s === null || s === undefined ? "—" : s < 90 ? `${num(s, 0)} s` : s < 5400 ? `${num(s / 60, 1)} min` : `${num(s / 3600, 1)} h`;

function work(ai) {
  const W = ai.work;
  if (!W) return `<p class="empty">brak danych o pracy agentów — pojawią się po pierwszym zadaniu dyspozytora (wersja 1.41+ na Macu)</p>`;
  const now = Date.now(), S = W.stats || {}, span = W.spanSec || 86400;
  const A = (ai.agents || []);
  const cur = W.now;
  const rows = A.map(a => {
    const s = S[a.id] || {};
    const working = cur && cur.agent === a.id;
    const every = s.n ? span / s.n : null;
    const last = stamp(s.last);
    return `<tr><td class="ag-${a.id}"><b>${esc(a.name)}</b></td>
      <td class="wrap-s">${working ? `${led("ok")} <b>pracuje</b> · ${esc(cur.task)} · od <span data-ts="${stamp(cur.since)}">${age((now - stamp(cur.since)) / 1000)}</span>`
        : a.state === "off" ? `<span class="dim">wyłączony</span>` : `<span class="dim">${esc(a.note || "czeka")}</span>`}</td>
      <td class="num">${s.n || 0}</td><td class="num">${every ? "co " + dur(every) : "—"}</td><td class="num">${dur(s.avg)}</td>
      <td class="num desk-only">${dur(s.max)}</td><td class="num desk-only">${s.n ? dur(s.llmSec / s.n) : "—"}</td>
      <td class="num desk-only">${num(s.busyPct || 0, 0)}%</td><td class="num ${s.fail ? "warn" : "dim"}">${s.fail || 0}</td>
      <td class="desk-only">${isFinite(last) ? `<span data-ts="${last}">${age((now - last) / 1000)}</span> temu` : "—"}</td></tr>`;
  }).join("");
  return `<div class="reads">
      <div class="read"><div class="k">teraz</div><div class="v ${cur ? "ok" : ""}">${cur ? esc(AG[cur.agent] || cur.agent) : "przerwa"}</div>
        <div class="s">${cur ? esc(cur.task) : "następne zadanie za chwilę"}${W.queue ? ` · w kolejce świec ${W.queue}` : ""}</div></div>
      <div class="read"><div class="k">zajęci</div><div class="v">${num(W.busyPct || 0, 0)}%</div><div class="s">czasu z ostatnich ${dur(span)} · jeden agent naraz</div></div>
      <div class="read"><div class="k">zadań (24 h)</div><div class="v">${Object.values(S).reduce((a, s) => a + s.n, 0)}</div>
        <div class="s">${Object.entries(S).map(([k, s]) => `${AG[k] || k} ${s.n}`).join(" · ")}</div></div>
    </div>
    ${timeline(W)}
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>agent</th><th>stan</th><th class="num">zadań 24 h</th><th class="num">rytm</th>
      <th class="num">śr. czas</th><th class="num desk-only">najdłużej</th><th class="num desk-only">model / zad.</th><th class="num desk-only">czasu</th>
      <th class="num">błędy</th><th class="desk-only">ostatnio</th></tr></thead><tbody>${rows}</tbody></table></div>
    <details class="nt desk-only" style="margin-top:8px;max-width:none"><summary>ostatnie zadania (${(W.runs || []).length}) ▸</summary>
      <div class="tbl-wrap scroll" style="max-height:340px"><table class="tbl"><thead><tr><th>start</th><th>agent</th><th>zadanie</th><th class="num">czas</th>
        <th class="num">model</th><th></th><th>wynik</th></tr></thead><tbody>` +
    (W.runs || []).map(r => `<tr><td>${t.short(stamp(r.start))}</td><td class="ag-${r.agent}">${esc(AG[r.agent] || r.agent)}</td><td class="wrap-s">${esc(r.task)}</td>
      <td class="num">${dur(r.sec)}</td><td class="num">${r.llmSec ? dur(r.llmSec) : "—"}</td><td class="${r.ok ? "ok" : "bad"}">${r.ok ? "✓" : "✗"}</td>
      <td class="wrap">${esc(r.summary)}</td></tr>`).join("") + `</tbody></table></div></details>`;
}

function timeline(W) {
  const T = W.timeline;
  if (!T || !(T.runs || []).length) return "";
  const from = stamp(T.from), span = 86400;
  const rows = ["investor", "critic", "researcher"].map((id, ai) => {
    const bars = T.runs.filter(r => r[0] === ai).map(r =>
      `<i style="left:${(100 * r[1] / span).toFixed(2)}%;width:max(2px,${(100 * r[2] / span).toFixed(3)}%)" class="${r[3] ? "" : "x"}" title="${t.short(from + r[1] * 1e3)} · ${dur(r[2])}"></i>`).join("");
    return `<div class="tl-row"><span class="ag-${id}">${AG[id]}</span><div class="tl-bar ag-${id}">${bars}</div></div>`;
  }).join("");
  const ticks = [0, 6, 12, 18, 24].map(h => `<span style="left:${(100 * h / 24).toFixed(1)}%">${t.hm(from + h * 3600e3)}</span>`).join("");
  return `<div class="tl">${rows}<div class="tl-row"><span></span><div class="tl-ax">${ticks}</div></div></div>`;
}

// ------------------------------------------------------------------ Krytyk (1.41)
function critic(ai) {
  const C = ai.critic;
  if (!C) return `<p class="empty">Krytyk jeszcze nie pracował (wersja 1.41+ na Macu)</p>`;
  const ex = C.explore || {}, R = (C.reviews || [])[0];
  const notes = (L, who) => (L || []).length ? `<p class="note"><b>dla ${who}:</b></p><ul class="plain">${L.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  return `<div class="reads">
      <div class="read"><div class="k">poziom nauki</div><div class="v">${ex.level}${level(ex.level)}</div>
        <div class="s">${esc(ex.name || "")} · własne pomysły do ${ex.own}/rundę, ryzyko ×${num(ex.own_mult, 2)}${ex.min_enter ? " · wymagane wejście" : ""}</div></div>
      <div class="read"><div class="k">ustawił</div><div class="v">${ex.auto ? "automat" : esc(ex.by || "—")}</div>
        <div class="s">${ex.auto ? `bierność: ${ex.passive} rund bez wejścia` : esc(ex.reason || "")}</div></div>
    </div>` +
    (R ? `<p class="note"><b>ostatni przegląd</b> ${t.short(stamp(R.at))}: ${esc(R.summary || "")}</p>` +
      notes(R.investorNotes, "Inwestora") + notes(R.researcherNotes, "Badacza") +
      ((R.verdicts || []).length ? `<p class="note"><b>werdykty:</b> ${R.verdicts.map(v => `<span class="${v.applied ? "" : "dim"}">${esc(v.id)} → ${esc(v.verdict)}${v.applied ? "" : " (kod: " + esc(v.why || "odrzucony") + ")"}</span>`).join(" · ")}</p>` : "") +
      `<p class="note">wnioski +${R.lessonsAdded || 0} / −${R.lessonsRemoved || 0} · przeglądów pokazanych ${(C.reviews || []).length}</p>`
      : `<p class="empty">jeszcze bez przeglądu — pierwszy po kilku rundach Inwestora albo gdy czekają hipotezy do oceny</p>`);
}

// ------------------------------------------------------------------ Badacz (1.41)
const HST = { "do oceny": "am", "próba": "cy", "zatwierdzona": "cy", "odrzucona przez kod": "", "odrzucona": "", "do poprawy": "am", "wycofana": "" };
function research(ai) {
  const R = ai.research;
  if (!R) return `<p class="empty">Badacz jeszcze nie pracował (wersja 1.41+ na Macu)</p>`;
  const c = R.counts || {};
  const parts = L => (L || []).map(x => x === null || x === undefined ? "·" : x > 0 ? `<span class="up">+</span>` : `<span class="down">−</span>`).join("");
  const row = h => `<tr><td>${esc(h.id)}</td><td><span class="tag ${HST[h.status] || ""}">${esc(h.status)}</span></td>
    <td class="wrap">${esc(h.desc)}${h.idea ? `<br><span class="dim">${esc(h.idea)}</span>` : ""}${h.verdict ? `<br><span class="ag-critic">Krytyk:</span> ${esc(h.verdict)}` : ""}${(h.why || []).length ? `<br><span class="dim">sito: ${esc(h.why.join("; "))}</span>` : ""}</td>
    <td class="num">${h.n ?? "—"}</td><td class="num ${cls(h.avg)}">${h.avg === null || h.avg === undefined ? "—" : sgn(h.avg, 3) + "%"}</td>
    <td class="num dim desk-only">${h.blind === null || h.blind === undefined ? "—" : sgn(h.blind, 3) + "%"}</td>
    <td class="num desk-only">${h.t === null || h.t === undefined ? "—" : num(h.t, 1)}</td><td class="parts desk-only">${parts(h.parts)}</td>
    <td class="num">${h.live && h.live.n ? `${h.live.n} · ${sgn(h.live.avg, 2)}%` : "—"}</td></tr>`;
  const head = `<thead><tr><th>ID</th><th>status</th><th>hipoteza</th><th class="num">trans.</th><th class="num">śr. netto</th><th class="num desk-only">na ślepo</th>
    <th class="num desk-only">t</th><th class="desk-only">części</th><th class="num">na żywo</th></tr></thead>`;
  return `<div class="reads">
      <div class="read"><div class="k">sprawdzonych</div><div class="v">${R.total || 0}</div><div class="s">odrzuconych przez kod ${c["odrzucona przez kod"] || 0}</div></div>
      <div class="read"><div class="k">do oceny</div><div class="v ${c["do oceny"] ? "am" : ""}">${c["do oceny"] || 0}</div><div class="s">czekają na Krytyka</div></div>
      <div class="read"><div class="k">w próbie</div><div class="v ${c["próba"] ? "cy" : ""}">${c["próba"] || 0}</div><div class="s">Inwestor handluje nimi małym ryzykiem</div></div>
      <div class="read"><div class="k">zatwierdzone / wycofane</div><div class="v">${c["zatwierdzona"] || 0} / ${c["wycofana"] || 0}</div><div class="s">po ≥ 20 transakcjach na żywo</div></div>
    </div>` +
    ((R.live || []).length ? `<p class="note"><b>na żywo</b> (próba i zatwierdzone)</p><div class="tbl-wrap"><table class="tbl">${head}<tbody>${R.live.map(row).join("")}</tbody></table></div>` : "") +
    `<p class="note"><b>ostatnie hipotezy</b></p><div class="tbl-wrap scroll" style="max-height:460px"><table class="tbl">${head}<tbody>` +
    ((R.recent || []).map(row).join("") || `<tr><td colspan="9" class="dim">brak — Badacz pracuje w wolnym czasie agentów</td></tr>`) + `</tbody></table></div>`;
}

// ------------------------------------------------------------------ feed (AI-1)
function feedBlock(name, f, unit) {
  if (!f) return `<p class="empty">${name}: brak danych</p>`;
  const L = f.last || {}, now = Date.now(), nx = stamp(f.next);
  const full = L.have !== undefined && L.have === L.need;
  return `<div class="feed-row"><p class="note" style="margin:8px 0 4px"><b>${name}</b> · ${f.marketOpen ? "rynek otwarty" : "rynek zamknięty"}</p>
    <div class="reads">
      <div class="read"><div class="k">ostatnia świeca</div><div class="v">${esc(unit(L))}</div><div class="s">zamknięcie ${L.closeAt ? t.short(stamp(L.closeAt)) : "—"}</div></div>
      <div class="read"><div class="k">w kopii</div><div class="v ${full ? "ok" : L.have === undefined ? "" : "warn"}">${L.have ?? "—"}/${L.need ?? "—"}</div>
        <div class="s">${(L.missing || []).length ? "brak: " + esc(L.missing.slice(0, 6).join(", ")) + (L.missing.length > 6 ? "…" : "") : L.localAt ? mmss(L.delaySec) + " po zamknięciu" : "przy starcie"}</div></div>
      <div class="read"><div class="k">Firestore → Mac</div><div class="v ${L.lagSec > LAG_OK ? "warn" : ""}">${L.lagSec === null || L.lagSec === undefined ? "—" : L.lagSec + " s"}</div><div class="s">cel ≤ 120 s</div></div>
      <div class="read"><div class="k">następna</div><div class="v">${isFinite(nx) ? t.hm(nx) : "—"}</div>
        <div class="s">${isFinite(nx) ? `za <span data-cd="${nx}">${age(Math.max(0, (nx - now) / 1000), true)}</span>` : ""}</div></div>
    </div></div>`;
}

function flow(ai) {
  const F = ai.flow || {};
  const rows = [...(F.stocks || []).map(r => Object.assign({ k: "akcje" }, r)), ...(F.fx || []).map(r => Object.assign({ k: "fx" }, r))]
    .filter(r => r && r.closeAt).sort((a, b) => stamp(b.closeAt) - stamp(a.closeAt)).slice(0, 24);
  if (!rows.length) return `<p class="empty">jeszcze żadna świeca nie przyszła na żywo (pierwsza po starcie trafi tutaj)</p>`;
  const lags = rows.filter(r => r.lagSec !== null && r.lagSec !== undefined);
  const okN = lags.filter(r => r.lagSec <= LAG_OK).length;
  return `<div class="tbl-wrap scroll"><table class="tbl"><thead><tr><th>rynek</th><th>świeca</th><th>zamknięcie</th><th class="num">w kopii</th><th class="num">Firestore → Mac</th><th class="num">komplet</th><th>brak</th></tr></thead><tbody>` +
    rows.map(r => `<tr><td class="${r.k === "fx" ? "cy" : "ok"}">${r.k}</td><td>${esc(r.k === "fx" ? t.hm(stamp(r.closeAt) - 3600e3) + "–" + t.hm(stamp(r.closeAt)) : r.candle)}</td>` +
      `<td>${t.short(stamp(r.closeAt))}</td><td class="num">${mmss(r.delaySec)}</td><td class="num ${r.lagSec > LAG_OK ? "warn" : ""}">${r.lagSec === null || r.lagSec === undefined ? "—" : r.lagSec + " s"}</td>` +
      `<td class="num ${r.have === r.need ? "" : "warn"}">${r.have}/${r.need}</td><td class="dim">${esc((r.missing || []).join(", "))}</td></tr>`).join("") +
    `</tbody></table></div><p class="note">świeca w kopii na Macu najpóźniej 2 min po zapisie w Firestore — spełnione w ${okN} z ${lags.length} ostatnich świec</p>`;
}

function journal(ai) {
  const I = ai.investor || {};
  const E = [...(ai.events || []).map(e => ({ t: stamp(e.at), src: KIND[e.kind] || e.kind, cls: (KCLS[e.kind] || "") + (e.kind === "error" || e.kind === "halt" ? " bad" : ""), text: e.text, k: "e" + e.at + e.kind + e.text })),
             ...(I.notes || []).map(n => ({ t: stamp(n.at), src: NOTE[n.kind] || n.kind, cls: n.agent === "critic" ? "ag-critic" : n.kind === "decyzja" ? "am" : "dim", text: n.text, k: "n" + n.at + n.text }))]
    .filter((x, i, a) => a.findIndex(y => y.k === x.k) === i).sort((a, b) => b.t - a.t).slice(0, 60);
  const fresh = E.filter(e => !seen.has(e.k));
  const h = `<ul class="log">${E.map(e => `<li class="${!firstPaint && fresh.includes(e) ? "new" : ""}"><span class="t">${t.short(e.t)}</span>` +
    `<span class="src ${e.cls}">${esc(e.src)}</span><span class="m">${esc(e.text)}</span></li>`).join("") || `<li><span class="m dim">brak zdarzeń</span></li>`}</ul>`;
  E.forEach(e => seen.add(e.k));
  if (E.length) firstPaint = false;
  return h;
}

export default {
  id: "ai", title: "ai",
  render(el) {
    const ai = store.get("ailive");
    if (!ai) {
      const m = store.meta.ailive;
      el.innerHTML = `<div class="grid"><div class="pane c12"><h2>AI Investor</h2>
        <p class="empty">${m && m.err && m.err !== "brak pliku" ? esc(m.err) + " — " : ""}AI Investor jeszcze nie był uruchomiony. Na Macu: <b>ia4 start</b> albo dwuklik <b>IA4-start.command</b> — po minucie pojawi się tu stan nadzorcy, feedu świec i agentów (instrukcja 11c.3).</p></div></div>`;
      return;
    }
    const st = aiState(ai), fd = ai.feed || {}, I = ai.investor, dim = st.s === "ok" ? "" : "stale";
    const fxn = ai.fxForecast && ai.fxForecast.on ? `prognoza FX liczy się w nadzorcy (ratingi ${esc(ai.fxForecast.ratings.run)})` : esc((ai.fxForecast || {}).note || "prognoza FX wyłączona");
    el.innerHTML = `<div class="grid">
      <div class="pane c12 hero ${dim}"><h2>AI Investor<span class="dim">agenci na Macu · ${esc(ai.step || "")}</span></h2>${help("ai.hero")}${hero(ai)}<p class="note">${fxn}</p></div>
      <div class="pane c12 ${dim}"><h2>praca agentów<span class="dim">jeden naraz · bez przerwy · oś 24 h</span></h2>${help("ai.work")}${work(ai)}</div>
      ${I ? `
      <div class="pane c12 ${dim}"><h2>Agent-Investor · portfel<span class="dim">na papierze · USD</span></h2>${help("ai.portfolio")}${portfolio(I, ai.critic)}</div>
      <div class="pane c7 desk-only"><h2>krzywa stanu konta<span class="dim">$ od startu</span></h2>${help("ai.curve")}<svg class="mini" data-eq></svg></div>
      <div class="pane c5 ${dim}"><h2>Krytyk<span class="dim">poziom nauki · uwagi · werdykty</span></h2>${help("ai.critic")}${critic(ai)}</div>
      <div class="pane c12"><h2>pozycje<span class="dim">otwarte i oczekujące · dlaczego</span></h2>${help("ai.positions")}${positions(I)}</div>
      <div class="pane c7"><h2>ostatnia runda<span class="dim">decyzje modelu i kodu</span></h2>${help("ai.round")}${lastRound(I)}</div>
      <div class="pane c5"><h2>punkty odniesienia</h2>${help("ai.bench")}${bench(I)}</div>
      <div class="pane c12 ${dim}"><h2>Badacz · hipotezy<span class="dim">liczone na historii z kosztami</span></h2>${help("ai.research")}${research(ai)}</div>
      <div class="pane c12 desk-only"><h2>zamknięte transakcje<span class="dim">ai/trades.jsonl · ostatnie 60</span></h2>${help("ai.trades")}${trades()}</div>` : ""}
      <div class="pane c7"><h2>dziennik<span class="dim">zdarzenia i notatki agentów</span></h2>${help("ai.journal")}${journal(ai)}</div>
      <div class="pane c5 desk-only"><h2>feed świec<span class="dim">Firestore → Mac</span></h2>${help("ai.feed")}
        ${feedBlock("akcje · 53 spółki + SPY, QQQ", fd.stocks, L => L.candle || "—")}
        ${feedBlock("FX · 10 par + BTC", fd.fx, L => L.closeAt ? t.hm(stamp(L.closeAt) - 3600e3) + "–" + t.hm(stamp(L.closeAt)) : "—")}</div>
      ${I ? `<div class="pane c7 desk-only"><h2>playbook<span class="dim">ai/playbook.json</span></h2>${help("ai.playbook")}${playbook()}</div>
      <div class="pane c5 desk-only"><h2>wnioski<span class="dim">ai/lessons.json</span></h2>${help("ai.lessons")}${lessons()}</div>` : ""}
      <div class="pane c12 desk-only"><h2>spływ świec<span class="dim">ostatnie 24</span></h2>${help("ai.flow")}${flow(ai)}</div>
    </div>
    <p class="note">Bez połączenia z Makiem panele są wyblakłe — to ostatni znany stan.</p>`;
    const svg = el.querySelector("[data-eq]");
    if (svg && I) equity(svg, (I.equity || []).map(([a, v]) => [a, v - (I.capital || 100000)]));
  },
  tick(el) {
    const now = Date.now();
    el.querySelectorAll("[data-ts]").forEach(s => { const ts = +s.dataset.ts; if (ts) s.textContent = age((now - ts) / 1000); });
    el.querySelectorAll("[data-cd]").forEach(s => { s.textContent = age(Math.max(0, (+s.dataset.cd - now) / 1000), true); });
  },
};
