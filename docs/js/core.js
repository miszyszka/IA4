// IA 4 — rdzeń strony: źródła danych, odświeżanie, formaty, bramka hasła (instrukcja, sekcja 11b).
// Wersja projektu: 1.32 (2026-10-11)
//
// Każde źródło = jeden plik w publicznym repo. Nowe źródło: dopisz do SOURCES, a widok
// przeczyta je przez store.get("id"). Dane są tylko czytane — strona niczego nie zapisuje.

export const VERSION = "1.32";
export const REPO = "miszyszka/IA4";
const RAW = (branch, path) => `https://raw.githubusercontent.com/${REPO}/${branch}/${path}`;
const API = (branch, path) => `https://api.github.com/repos/${REPO}/contents/${path}?ref=${branch}`;

// every — co ile sekund; api — przez API GitHub z ETag (świeże, „bez zmian” nie zużywa limitu 60/h),
// inaczej raw.githubusercontent.com (bez limitu, do ok. 5 min opóźnienia — wystarcza dla plików godzinowych).
export const SOURCES = {
  state:      { label: "telemetry/state.json", branch: "main", path: "telemetry/state.json", every: 60 },
  vi:         { label: "telemetry/vi.json", branch: "main", path: "telemetry/vi.json", every: 60 },
  fxvi:       { label: "telemetry/fx-vi.json", branch: "main", path: "telemetry/fx-vi.json", every: 300 },   // przyszły inwestor FX
  forecast:   { label: "fx-live/forecast.json", branch: "fx-live", path: "forecast.json", every: 30, api: true },
  strategies: { label: "research/strategies.jsonl", branch: "research", path: "research/strategies.jsonl", every: 900, jsonl: true },
  research:   { label: "research/status.json", branch: "research", path: "research/status.json", every: 900 },
  fxruns:     { label: "fx/runs.jsonl", branch: "fx", path: "fx/runs.jsonl", every: 900, jsonl: true },
  commits:    { label: "git log main", url: `https://api.github.com/repos/${REPO}/commits?sha=main&per_page=25`, every: 180, api: true },
};

// ------------------------------------------------------------------ formaty
const TZ_PL = "Europe/Warsaw", TZ_NY = "America/New_York";
const fmt = (tz, opt) => new Intl.DateTimeFormat("pl-PL", Object.assign({ timeZone: tz }, opt));
const F = {
  hms: fmt(TZ_PL, { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }),
  hm: fmt(TZ_PL, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }),
  dhm: fmt(TZ_PL, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }),
  dm: fmt(TZ_PL, { day: "2-digit", month: "2-digit" }),
  wd: fmt(TZ_PL, { weekday: "short" }),
  h: fmt(TZ_PL, { hour: "2-digit", hourCycle: "h23" }),
  nyhm: fmt(TZ_NY, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }),
};
export const t = {
  hms: ms => F.hms.format(ms), hm: ms => F.hm.format(ms), dhm: ms => F.dhm.format(ms), dm: ms => F.dm.format(ms),
  wd: ms => F.wd.format(ms), hour: ms => +F.h.format(ms), nyhm: ms => F.nyhm.format(ms),
  short: ms => (Date.now() - ms < 20 * 3600e3 ? F.hm.format(ms) : F.dm.format(ms) + " " + F.hm.format(ms)),
};
/** Wiek w sekundach → „42 s”, „7 min”, „3 h 05”, „2 d”. */
export function age(s, long = false) {
  if (s === null || s === undefined || !isFinite(s)) return "—";
  s = Math.max(0, s);
  if (s < 90) return `${Math.floor(s)} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min` + (long ? ` ${String(Math.floor(s % 60)).padStart(2, "0")} s` : "");
  if (s < 48 * 3600) return `${Math.floor(s / 3600)} h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`;
  return `${Math.floor(s / 86400)} d`;
}
export const num = (v, d = 0) => (v === null || v === undefined || !isFinite(v)) ? "—"
  : v.toLocaleString("pl-PL", { minimumFractionDigits: d, maximumFractionDigits: d });
export const sgn = (v, d = 1) => (v === null || v === undefined || !isFinite(v)) ? "—"
  : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toLocaleString("pl-PL", { minimumFractionDigits: d, maximumFractionDigits: d });
export const pct = (v, d = 0) => (v === null || v === undefined || !isFinite(v)) ? "—" : num(100 * v, d) + "%";
export const usd = (v, d = 2) => (v === null || v === undefined || !isFinite(v)) ? "—" : sgn(v, d) + " $";
export const cls = v => v > 0 ? "up" : v < 0 ? "down" : "";
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const $ = (sel, root = document) => root.querySelector(sel);
/** „2026-10-09 15:30” (czas lokalny strefy tz bez oznaczenia, np. z Apps Script) → ms. */
export function plStamp(s, tz = TZ_PL) {
  if (!s) return NaN;
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(s);
  if (!m || /Z|[+-]\d\d:\d\d$/.test(s)) return Date.parse(s);
  const guess = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
  const off = (() => {                                   // przesunięcie strefy w tej chwili (czas letni / zimowy)
    const p = new Intl.DateTimeFormat("en-US", { timeZone: tz, hour12: false, year: "numeric", month: "2-digit",
      day: "2-digit", hour: "2-digit", minute: "2-digit" }).formatToParts(guess);
    const g = k => +p.find(x => x.type === k).value;
    return Date.UTC(g("year"), g("month") - 1, g("day"), g("hour") % 24, g("minute")) - guess;
  })();
  return guess - off;
}
export const nyStamp = s => plStamp(s, TZ_NY);
/** Klucz świecy akcji (RRRRMMDDn, n = 1…7) → zamknięcie świecy (ms). */
export function stockClose(key) {
  if (!key) return NaN;
  const d = String(Math.floor(key / 10)), n = key % 10;
  const min = Math.min(570 + n * 60, 960);
  return nyStamp(`${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)} ${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`);
}

// ------------------------------------------------------------------ godziny rynków
function nyParts(ms) {
  const p = new Intl.DateTimeFormat("en-US", { timeZone: TZ_NY, weekday: "short", hour: "numeric", minute: "numeric", hour12: false }).formatToParts(ms);
  const g = k => (p.find(x => x.type === k) || {}).value;
  return { wd: g("weekday"), m: (+g("hour") % 24) * 60 + +g("minute") };
}
/** Rynek walutowy: niedziela 17:00 – piątek 17:00 Nowy Jork; crypto 24/7. */
export function fxOpen(group, ms = Date.now()) {
  if (group && group !== "fx") return true;
  const { wd, m } = nyParts(ms);
  if (wd === "Sat") return false;
  if (wd === "Sun") return m >= 17 * 60;
  if (wd === "Fri") return m < 17 * 60;
  return true;
}
/** Sesja NYSE 9:30–16:00 (bez listy świąt — to tylko wskazówka na stronie). */
export function nyseOpen(ms = Date.now()) {
  const { wd, m } = nyParts(ms);
  return !["Sat", "Sun"].includes(wd) && m >= 570 && m < 960;
}

// ------------------------------------------------------------------ magazyn danych
const listeners = new Set();
const store = {
  data: {}, meta: {}, etag: {}, rawUntil: 0,
  get(id) { return this.data[id]; },
  on(fn) { listeners.add(fn); return () => listeners.delete(fn); },
};
export { store };

async function fetchSource(id) {
  const S = SOURCES[id], M = store.meta[id] || (store.meta[id] = {});
  const viaApi = S.api && Date.now() >= store.rawUntil;
  let url = S.url || (viaApi ? API(S.branch, S.path) : RAW(S.branch, S.path) + "?t=" + Math.floor(Date.now() / 60000));
  if (S.url && !viaApi) { M.at = Date.now(); return false; }               // lista commitów tylko przez API
  const headers = {};
  if (viaApi) {
    headers.Accept = S.url ? "application/vnd.github+json" : "application/vnd.github.raw";
    if (store.etag[id]) headers["If-None-Match"] = store.etag[id];
  }
  try {
    const r = await fetch(url, { headers, cache: viaApi ? "no-cache" : "no-store" });
    M.at = Date.now(); M.status = r.status;
    if (r.status === 304) { M.ok = true; M.err = null; return false; }
    if (r.status === 404) { M.ok = false; M.err = "brak pliku"; store.data[id] = null; return true; }
    if ((r.status === 403 || r.status === 429) && viaApi) {            // limit API — 10 min przez raw
      store.rawUntil = Date.now() + 10 * 60e3; M.err = "limit API GitHub — chwilowo raw"; return S.url ? false : fetchSource(id);
    }
    if (!r.ok) { M.ok = false; M.err = `HTTP ${r.status}`; return false; }
    const et = r.headers.get("ETag"); if (et) store.etag[id] = et;
    const text = await r.text();
    if (M.text === text) { M.ok = true; M.err = null; return false; }
    const val = S.jsonl ? text.split("\n").filter(l => l.trim()).map(l => { try { return JSON.parse(l); } catch (e) { return null; } }).filter(Boolean)
                        : JSON.parse(text);
    M.prev = store.data[id]; M.text = text; M.ok = true; M.err = null; M.changedAt = Date.now();
    store.data[id] = val;
    return true;
  } catch (e) {
    M.at = Date.now(); M.ok = false; M.err = "brak połączenia";
    return false;
  }
}

function emit(changed) { listeners.forEach(fn => { try { fn(changed); } catch (e) { console.error(e); } }); }

export function startPolling() {
  const due = {};
  const tick = async () => {
    const now = Date.now(), ids = Object.keys(SOURCES).filter(id => !(due[id] > now) && !document.hidden);
    if (!ids.length) return;
    ids.forEach(id => { due[id] = now + SOURCES[id].every * 1000; });
    const res = await Promise.all(ids.map(id => fetchSource(id).then(ch => ch ? id : null)));
    emit(res.filter(Boolean));
  };
  tick();
  setInterval(tick, 5000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { Object.keys(due).forEach(k => { due[k] = 0; }); tick(); } });
}

// ------------------------------------------------------------------ bramka hasła
// Strona leży w publicznym repo, więc to tylko bramka w przeglądarce — dane i tak są publiczne
// (instrukcja 11b). W kodzie jest wyłącznie skrót PBKDF2 hasła, nie samo hasło.
const GATE = { salt: "ia4/gate/v1", iter: 150000, hash: "9a6dbe3e3eb3be702eebc38360c6a3938816b0829ddcd72ad98d08dfc55ab0cf",
               key: "ia4.gate", days: 30 };

async function derive(pw) {
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey("raw", enc.encode(pw), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: enc.encode(GATE.salt), iterations: GATE.iter }, k, 256);
  return [...new Uint8Array(bits)].map(b => b.toString(16).padStart(2, "0")).join("");
}
export function gateRemembered() {
  try {
    const v = JSON.parse(localStorage.getItem(GATE.key) || "null");
    return !!v && v.h === GATE.hash && Date.now() - v.at < GATE.days * 86400e3;
  } catch (e) { return false; }
}
export async function gateTry(pw) {
  if (!window.crypto || !crypto.subtle) throw new Error("przeglądarka bez WebCrypto — otwórz stronę przez https");
  const ok = (await derive(pw)) === GATE.hash;
  if (ok) { try { localStorage.setItem(GATE.key, JSON.stringify({ h: GATE.hash, at: Date.now() })); } catch (e) { /* bez pamięci */ } }
  return ok;
}
export function gateForget() { try { localStorage.removeItem(GATE.key); } catch (e) { /* bez pamięci */ } }

// ------------------------------------------------------------------ pamięć wyborów (tylko wygoda)
export const pref = {
  get(k, d) { try { const v = localStorage.getItem("ia4." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("ia4." + k, JSON.stringify(v)); } catch (e) { /* bez pamięci */ } },
};
