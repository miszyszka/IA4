// IA 4 — „czy system żyje”: jeden model stanu dla magistrali (góra strony) i zakładki System.
// Wersja projektu: 1.29 (2026-10-11)
//
// Każde ogniwo ma: ts (chwila ostatniego znaku życia, ms), status ok / warn / bad / off,
// opis i oczekiwany rytm. Wiek liczony jest na żywo (co sekundę) z ts.

import { store, fxOpen, nyseOpen, stockClose, plStamp } from "./core.js";

const MIN = 60e3, H = 3600e3;
const stamp = s => (s ? Date.parse(s) : NaN);
const maxTs = (...a) => a.filter(x => isFinite(x)).reduce((m, x) => (isFinite(m) ? Math.max(m, x) : x), NaN);

/** Najnowsza świeca FX (ms zamknięcia) i lista ostatnich świec instrumentów — z forecast.json i state.json. */
export function fxLast() {
  const fc = store.get("forecast"), st = store.get("state");
  const out = {};
  ((fc && fc.instruments) || []).forEach(I => { out[I.id] = { t: stamp(I.lastCandle), close: I.lastClose, group: I.group }; });
  const sym = st && st.fx && st.fx.sym;
  if (sym) Object.entries(sym).forEach(([id, v]) => {
    const t = stamp(v.last);
    if (!out[id] || t > out[id].t) out[id] = Object.assign(out[id] || {}, { t, close: v.close });
  });
  return out;
}

export function nodes() {
  const now = Date.now();
  const st = store.get("state"), fc = store.get("forecast"), vi = store.get("vi"), commits = store.get("commits");
  const M = store.meta;
  const N = [];

  // 1. Yahoo — najnowsza zamknięta świeca, która dotarła do systemu (akcje albo FX)
  const fx = fxLast();
  const fxT = maxTs(...Object.values(fx).map(v => v.t)) + H;
  const stT = st && st.lastCandle ? stockClose(st.lastCandle.key) : NaN;
  const yT = maxTs(fxT, stT);
  const anyOpen = nyseOpen(now) || fxOpen("fx", now) || Object.values(fx).some(v => v.group === "crypto");
  N.push({ id: "yahoo", name: "Yahoo", ts: yT, every: "świeca co 1 h",
    status: !isFinite(yT) ? "off" : now - yT < 2.25 * H ? "ok" : anyOpen ? "warn" : "off",
    sub: isFinite(yT) ? `najnowsza świeca ${new Date(yT).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Warsaw" })}` : "brak danych" });

  // 2. Apps Script — ostatnie uruchomienie automatu (stan publikowany co godzinę i po świecy)
  const run = st && st.collector && st.collector.lastRun;
  const rT = run ? stamp(run.at) : NaN, gT = st ? stamp(st.generatedAt) : NaN;
  N.push({ id: "gas", name: "Apps Script", ts: rT, every: "co minutę",
    status: !st ? "off" : !run || run.ok === false ? "bad" : now - gT < 80 * MIN ? "ok" : now - gT < 3 * H ? "warn" : "bad",
    sub: run ? (run.action || "") : "brak telemetrii" });

  // 3. Firestore — ostatni zapis (akcje albo FX)
  const fsT = maxTs(st && st.collector ? stamp(st.collector.lastWrite) : NaN, st && st.fx ? stamp(st.fx.lastWriteAt) : NaN);
  const err = st && st.collector && st.collector.lastError;
  const errFresh = err && now - stamp(err.at) < 2 * H;
  N.push({ id: "fs", name: "Firestore", ts: fsT, every: "zapis po każdej świecy",
    status: !isFinite(fsT) ? "off" : errFresh ? "warn" : now - fsT < 2.25 * H ? "ok" : anyOpen ? "warn" : "off",
    sub: st && st.base ? `${st.base.totalCandles.toLocaleString("pl-PL")} świec akcji` : "" });

  // 4. GitHub — ostatni commit na main (telemetria, inwestor)
  const cT = maxTs(commits && commits[0] ? stamp(commits[0].commit.committer.date) : NaN, gT, vi ? stamp(vi.generatedAt) : NaN);
  N.push({ id: "gh", name: "GitHub", ts: cT, every: "co godzinę",
    status: !isFinite(cT) ? "off" : now - cT < 80 * MIN ? "ok" : now - cT < 3 * H ? "warn" : "bad",
    sub: commits && commits[0] ? commits[0].commit.message.split("\n")[0] : "telemetria" });

  // 5. Mac — FX-real-time (sygnał życia co 2 min)
  const aT = fc ? stamp(fc.aliveAt) : NaN;
  N.push({ id: "mac", name: "Mac · FX-real-time", ts: aT, every: "sygnał co 2 min",
    status: !fc ? "off" : fc.stoppedAt ? "off" : now - aT < 5 * MIN ? "ok" : "bad",
    sub: !fc ? "brak forecast.json" : fc.stoppedAt ? "program zatrzymany" : now - aT < 5 * MIN ? "połączony" : "offline" });

  // 6. Ta strona — ostatnie udane pobranie
  const okT = maxTs(...Object.values(M).filter(m => m.ok).map(m => m.at));
  const errs = Object.entries(M).filter(([k, m]) => !m.ok && m.err && m.err !== "brak pliku");
  N.push({ id: "web", name: "Ta strona", ts: okT, every: "co 30–60 s",
    status: !isFinite(okT) ? "off" : errs.length ? "warn" : now - okT < 2 * MIN ? "ok" : "warn",
    sub: errs.length ? `${errs.length} źródeł z błędem` : "dane aktualne" });
  return N;
}

/** Ogólny stan do znacznika w nagłówku. */
export function overall(N = nodes()) {
  const by = Object.fromEntries(N.map(n => [n.id, n.status]));
  if (by.gas === "bad" || by.gh === "bad") return { status: "bad", text: "automat milczy" };
  if (by.gas === "ok" && by.gh === "ok") return { status: "ok", text: "system żyje" };
  if (by.gas === "off") return { status: "warn", text: "łączenie" };
  return { status: "warn", text: "opóźnienia" };
}

/** Wersje: strona, Apps Script, Python (FX-real-time). */
export function versions() {
  const st = store.get("state"), fc = store.get("forecast"), vi = store.get("vi");
  return { gas: st && st.version, vi: vi && vi.version, mac: fc && fc.version };
}

export { stamp, plStamp };
