// IA 4 — zakładka AI: AI Investor na Macu — nadzorca, feed świec, agenci (instrukcja, sekcja 11c.11).
// Wersja projektu: 1.33 (2026-10-11)
//
// Źródło: ai-live/status.json (sygnał życia co 5 min i po każdym zdarzeniu). Krok AI-1: nadzorca, feed akcji
// i FX, Ollama; agenci pojawiają się w krokach AI-2…AI-4 (portfel, transakcje, hipotezy — kolejne panele).

import { store, num, esc, age, t } from "../core.js";
import { stamp } from "../health.js";

const MIN = 60e3;
const ALIVE_OK = 11 * MIN;               // status.json co 5 min — dwa sygnały z zapasem
const LAG_OK = 120;                      // kryterium AI-1: świeca w kopii ≤ 2 min po zapisie w Firestore
const seen = new Set();
let firstPaint = true;

const led = s => `<span class="led ${s}${s === "ok" ? " beat" : ""}"></span>`;
const mmss = s => s === null || s === undefined ? "—" : `${s < 0 ? "−" : "+"}${Math.floor(Math.abs(s) / 60)}:${String(Math.abs(s) % 60).padStart(2, "0")}`;
const KIND = { start: "start", stop: "stop", sync: "sync", ollama: "model", fx: "fx", "fx-late": "fx", stocks: "akcje",
               "stocks-late": "akcje", "stocks-night": "noc", error: "błąd" };
const KCLS = { fx: "cy", "fx-late": "cy", stocks: "ok", "stocks-late": "ok", error: "", "stocks-night": "dim", sync: "dim" };

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
    `</tbody></table></div><p class="note">kryterium kroku AI-1: świeca w kopii na Macu najpóźniej 2 min po zapisie w Firestore — spełnione w ${okN} z ${lags.length} ostatnich świec</p>`;
}

function agents(ai) {
  return `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>agent</th><th class="desk-only">rola</th><th>stan</th></tr></thead><tbody>` +
    (ai.agents || []).map(a => `<tr><td>${led(a.state === "on" ? "ok" : "off")} ${esc(a.name)}</td><td class="desk-only dim">${esc(a.role || "")}</td><td>${a.state === "on" ? esc(a.note || "działa") : `<span class="dim">od kroku ${esc(a.step)}</span>`}</td></tr>`).join("") +
    `</tbody></table></div>
    <p class="note">${ai.fxForecast && ai.fxForecast.on ? `prognoza FX liczy się w nadzorcy (ratingi ${esc(ai.fxForecast.ratings.run)}) → zakładka FX` : esc((ai.fxForecast || {}).note || "prognoza FX wyłączona")}</p>`;
}

function journal(ai) {
  const E = (ai.events || []).map(e => ({ t: stamp(e.at), kind: e.kind, text: e.text, k: e.at + e.kind + e.text }));
  const fresh = E.filter(e => !seen.has(e.k));
  const h = `<ul class="log">${E.map(e => `<li class="${!firstPaint && fresh.includes(e) ? "new" : ""}"><span class="t">${t.short(e.t)}</span>` +
    `<span class="src ${KCLS[e.kind] || ""}${e.kind === "error" ? " bad" : ""}">${KIND[e.kind] || esc(e.kind)}</span><span class="m">${esc(e.text)}</span></li>`).join("") ||
    `<li><span class="m dim">brak zdarzeń</span></li>`}</ul>`;
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
      el.innerHTML = `<div class="grid"><div class="pane c12"><h2>AI Investor<span class="dim">krok AI-1</span></h2>
        <p class="empty">${m && m.err && m.err !== "brak pliku" ? esc(m.err) + " — " : ""}AI Investor jeszcze nie był uruchomiony. Na Macu: <b>ia4 start</b> albo dwuklik <b>IA4-start.command</b> — po minucie pojawi się tu stan nadzorcy, feedu świec i agentów (instrukcja 11c.3).</p></div></div>`;
      return;
    }
    const st = aiState(ai);
    const fd = ai.feed || {};
    el.innerHTML = `<div class="grid">
      <div class="pane c12 hero ${st.s === "ok" ? "" : "stale"}"><h2>AI Investor<span class="dim">trzej agenci na Macu · ${esc(ai.step || "")}</span></h2>${hero(ai)}</div>
      <div class="pane c7"><h2>feed świec<span class="dim">Firestore → kopia na Macu</span></h2>
        ${feedBlock("akcje · 53 spółki + SPY, QQQ", fd.stocks, L => L.candle || "—")}
        ${feedBlock("FX · 10 par + BTC", fd.fx, L => L.closeAt ? t.hm(stamp(L.closeAt) - 3600e3) + "–" + t.hm(stamp(L.closeAt)) : "—")}</div>
      <div class="pane c5"><h2>agenci<span class="dim">${(ai.agents || []).filter(a => a.state === "on").length}/${(ai.agents || []).length} aktywnych</span></h2>${agents(ai)}</div>
      <div class="pane c7 desk-only"><h2>spływ świec<span class="dim">ostatnie 24</span></h2>${flow(ai)}</div>
      <div class="pane c5"><h2>dziennik<span class="dim">${(ai.events || []).length} zdarzeń</span></h2>${journal(ai)}</div>
    </div>
    <p class="note">Portfel, transakcje z notatkami, hipotezy i przeglądy pojawią się tu w krokach AI-2…AI-4. Bez połączenia z Makiem panel jest wyblakły — to ostatni znany stan.</p>`;
  },
  tick(el) {
    const now = Date.now();
    el.querySelectorAll("[data-ts]").forEach(s => { const ts = +s.dataset.ts; if (ts) s.textContent = age((now - ts) / 1000); });
    el.querySelectorAll("[data-cd]").forEach(s => { s.textContent = age(Math.max(0, (+s.dataset.cd - now) / 1000), true); });
  },
};
