/**
 * ============================================================================
 *  IA 4 — MODUŁ FX 1h  (Yahoo, świece godzinowe 10 par + BTC + 10 par fx1h_double_proof →
 *                       Firestore fx1h/{SYMBOL}/days → arkusz FX)
 *
 *  Wersja projektu: 1.57 (2026-10-21) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Osobny moduł (instrukcja, sekcja 4b): zbiera dane. Nie bierze udziału
 *  w poszukiwaniu strategii, weryfikacji ani paper tradingu.
 *
 *  • fxIfDue_() woła runCollector (Code.gs) w każdym uruchomieniu (co minutę)
 *    i co 10 s w szybkiej ścieżce akcji — jeden trigger dla całego automatu.
 *  • Na żywo: dla każdego instrumentu, któremu brakuje zamkniętej świecy (zamknięcie
 *    + 20 s), jedno zapytanie Yahoo (wszystkie naraz, fetchAll) od początku dnia UTC
 *    ostatniej zapisanej świecy; dokument dnia przepisywany w całości, potem
 *    system/fx1h (ostatnia świeca każdego instrumentu — jeden odczyt dla Maca).
 *    Pary walutowe tylko w godzinach rynku (nd 17:00 – pt 17:00 Nowy Jork), BTC 24/7.
 *  • Historia (jednorazowo): 728 dni wstecz (granica Yahoo dla świec 1h), jeden
 *    instrument na wolne uruchomienie; braki starszych dni od razu uśrednione.
 *  • Kontrola zakończonego dnia (od 00:20 UTC): do 3 prób co 60 min; potem braki
 *    uśrednione (interpolacja liniowa, fillT) — każdy dzień kończy się kompletny.
 *  • Arkusz FX: wiersz na dzień UTC, kolumna na instrument: „zapisanych/oczekiwanych”.
 *  • Stara baza EURUSD 5 min (fx/EURUSD, do 1.26): menu „usuń stare świece 5 min”.
 *  • Arkusz OKOLICZNOSCI_FX (prognoza, sekcja 4c.11) — z brancha `fx` w researchSync.
 *  Stan: Script Properties FX1H_STATE i FX1H_CHECK.
 * ============================================================================
 */

const FX = {
  COLL: 'fx1h',                 // fx1h/{SYMBOL}/days/{RRRR-MM-DD}
  STATUS_DOC: 'system/fx1h',    // ostatnia świeca każdego instrumentu (jeden dokument)
  STEP_SEC: 3600,               // świeca 1 h
  FIRST_FETCH_SEC: 20,          // pytamy Yahoo najwcześniej tyle sekund po zamknięciu świecy
  RETRY_FAST_MIN: 10,           // przez tyle minut spóźnienia — próba w każdym uruchomieniu (co minutę)
  RETRY_SLOW_MIN: 10,           // potem co tyle minut
  HISTORY_DAYS: 728,            // historia: tyle dni wstecz (Yahoo 1h: do 730 dni)
  YAHOO_DAYS: 726,              // starsze dni Yahoo już nie odda — kontrola od razu uzupełnia
  CHECK_AFTER_MIN: 20,          // kontrola wczorajszego dnia: od 00:20 UTC
  CHECK_TRIES: 3,               // tyle prób pobrania brakujących świec
  CHECK_EVERY_MIN: 60,          // odstęp między próbami
  CHECK_PER_RUN: 11,            // najwyżej tyle (instrument, dzień) w jednym uruchomieniu
  OPEN_DOW: 7, OPEN_MIN: 17 * 60,         // rynek walutowy: od niedzieli 17:00 ET…
  CLOSE_DOW: 5, CLOSE_MIN: 17 * 60,       // …do piątku 17:00 ET
  SHEET: 'FX',
  LEGACY: 'fx/EURUSD',          // stara baza 5 min (1.15–1.26) — usuwana z menu
  // Instrumenty (instrukcja 4b). Kolejność = kolumny arkusza FX. dp — miejsca po przecinku,
  // pip — jednostka zmiany ceny na dashboardzie. Zmiana listy = zmiana instrukcji.
  INSTRUMENTS: [
    { id: 'EURUSD', yahoo: 'EURUSD=X', group: 'fx', dp: 6, pip: 0.0001 },
    { id: 'USDJPY', yahoo: 'JPY=X', alt: 'USDJPY=X', group: 'fx', dp: 4, pip: 0.01 },
    { id: 'GBPUSD', yahoo: 'GBPUSD=X', group: 'fx', dp: 6, pip: 0.0001 },
    { id: 'AUDUSD', yahoo: 'AUDUSD=X', group: 'fx', dp: 6, pip: 0.0001 },
    { id: 'USDCAD', yahoo: 'CAD=X', alt: 'USDCAD=X', group: 'fx', dp: 6, pip: 0.0001 },
    { id: 'USDCHF', yahoo: 'CHF=X', alt: 'USDCHF=X', group: 'fx', dp: 6, pip: 0.0001 },
    { id: 'NZDUSD', yahoo: 'NZDUSD=X', group: 'fx', dp: 6, pip: 0.0001 },
    { id: 'EURJPY', yahoo: 'EURJPY=X', group: 'fx', dp: 4, pip: 0.01 },
    { id: 'GBPJPY', yahoo: 'GBPJPY=X', group: 'fx', dp: 4, pip: 0.01 },
    { id: 'EURGBP', yahoo: 'EURGBP=X', group: 'fx', dp: 6, pip: 0.0001 },
    { id: 'BTCUSD', yahoo: 'BTC-USD', group: 'crypto', dp: 2, pip: 1 },
    // fx1h_double_proof (od 1.52): 10 par sprawdzianu — tylko zbierane; badania i agenci AI ich nie używają,
    // wyłącznie test zamrożonej strategii (instrukcja 4b, 7b). Na końcu listy: nowe kolumny dopisują się do arkusza FX.
    { id: 'EURCHF', yahoo: 'EURCHF=X', group: 'fx1h_double_proof', dp: 6, pip: 0.0001 },
    { id: 'EURAUD', yahoo: 'EURAUD=X', group: 'fx1h_double_proof', dp: 6, pip: 0.0001 },
    { id: 'EURCAD', yahoo: 'EURCAD=X', group: 'fx1h_double_proof', dp: 6, pip: 0.0001 },
    { id: 'GBPCHF', yahoo: 'GBPCHF=X', group: 'fx1h_double_proof', dp: 6, pip: 0.0001 },
    { id: 'GBPAUD', yahoo: 'GBPAUD=X', group: 'fx1h_double_proof', dp: 6, pip: 0.0001 },
    { id: 'AUDNZD', yahoo: 'AUDNZD=X', group: 'fx1h_double_proof', dp: 6, pip: 0.0001 },
    { id: 'AUDJPY', yahoo: 'AUDJPY=X', group: 'fx1h_double_proof', dp: 4, pip: 0.01 },
    { id: 'CADJPY', yahoo: 'CADJPY=X', group: 'fx1h_double_proof', dp: 4, pip: 0.01 },
    { id: 'CHFJPY', yahoo: 'CHFJPY=X', group: 'fx1h_double_proof', dp: 4, pip: 0.01 },
    { id: 'NZDJPY', yahoo: 'NZDJPY=X', group: 'fx1h_double_proof', dp: 4, pip: 0.01 },
  ],
};

const FX_DOW = ['', 'pn', 'wt', 'śr', 'czw', 'pt', 'sob', 'nd'];
function fxCols_() { return ['Data (UTC)', 'Dzień'].concat(FX.INSTRUMENTS.map(i => i.id)); }

function fxStateLoad_() {
  const st = JSON.parse(PropertiesService.getScriptProperties().getProperty('FX1H_STATE') || '{}');
  if (!st.sym) st.sym = {};
  return st;
}
function fxStateSave_(st) { PropertiesService.getScriptProperties().setProperty('FX1H_STATE', JSON.stringify(st)); }
function fxCheckLoad_() { return JSON.parse(PropertiesService.getScriptProperties().getProperty('FX1H_CHECK') || '{}'); }
function fxCheckSave_(c) { PropertiesService.getScriptProperties().setProperty('FX1H_CHECK', JSON.stringify(c)); }
function fxInst_(id) { return FX.INSTRUMENTS.find(i => i.id === id); }

function fxDay_(t) { return Utilities.formatDate(new Date(t * 1000), 'UTC', 'yyyy-MM-dd'); }
function fxDayStart_(d) { return Date.parse(d + 'T00:00:00Z') / 1000; }
function fxRound_(x, dp) { const m = Math.pow(10, dp); return Math.round(x * m) / m; }

/** Czy świeca 1 h zaczynająca się w chwili t (s) mieści się w godzinach rynku instrumentu. */
function fxSlotOpen_(inst, t) {
  if (inst.group === 'crypto') return true;
  const d = new Date(t * 1000);
  const dow = isoWeekday_(Utilities.formatDate(d, CONFIG.MARKET_TZ, 'yyyy-MM-dd'));
  const min = minutesOf_(d, CONFIG.MARKET_TZ);
  if (dow === 6) return false;
  if (dow === FX.OPEN_DOW) return min >= FX.OPEN_MIN;
  if (dow === FX.CLOSE_DOW) return min < FX.CLOSE_MIN;
  return true;
}

/** Początek najnowszej świecy w godzinach rynku zamkniętej przed chwilą t (s). */
function fxLastClosed_(inst, t) {
  let c = Math.floor(t / FX.STEP_SEC) * FX.STEP_SEC - FX.STEP_SEC;
  for (let i = 0; i < 80 && !fxSlotOpen_(inst, c); i++) c -= FX.STEP_SEC;
  return c;
}

/**
 * Oczekiwane świece dnia (UTC): początki świec (s) w godzinach rynku. Pary walutowe: przesunięcie
 * ET–UTC liczone raz na dzień (w południe UTC) — zmiana czasu w USA przypada na niedzielę rano,
 * gdy rynek jest zamknięty; BTC: 24. upTo — tylko świece zamknięte przed tą chwilą (s);
 * fromT — pierwszy dzień bazy: od pierwszej świecy.
 */
function fxExpected_(inst, date, upTo, fromT) {
  const t0 = fxDayStart_(date);
  const out = [];
  let off = 0;
  if (inst.group !== 'crypto') off = minutesOf_(new Date((t0 + 43200) * 1000), CONFIG.MARKET_TZ) - 12 * 60;
  const dowUtc = isoWeekday_(date);
  for (let i = 0; i < 24; i++) {
    const t = t0 + i * FX.STEP_SEC;
    if (upTo && t + FX.STEP_SEC > upTo) break;
    if (fromT && t < fromT) continue;
    let open = true;
    if (inst.group !== 'crypto') {
      let min = i * 60 + off, dow = dowUtc;
      if (min < 0) { min += 1440; dow = dow === 1 ? 7 : dow - 1; }
      if (dow === 6) open = false;
      else if (dow === FX.OPEN_DOW) open = min >= FX.OPEN_MIN;
      else if (dow === FX.CLOSE_DOW) open = min < FX.CLOSE_MIN;
    }
    if (open) out.push(t);
  }
  return out;
}

/** Podsumowanie dnia: świece z Yahoo, uśrednione, oczekiwane, brakujące. */
function fxDayInfo_(inst, date, realT, fillT, upTo, fromT) {
  const have = {};
  realT.forEach(t => { have[t] = 1; });
  fillT.forEach(t => { have[t] = 1; });
  const fullExp = fxExpected_(inst, date, 0, fromT).length;
  const exp = fxExpected_(inst, date, upTo || 0, fromT);
  const missingT = exp.filter(t => !have[t]);
  return { real: realT.length, filled: fillT.length, total: realT.length + fillT.length, expected: fullExp,
           missing: missingT.length, missingT };
}

// ============================================================================
//  WEJŚCIE (co minutę z runCollector)
// ============================================================================
function fxIfDue_(force) {
  const st = fxStateLoad_();
  const msgs = [];
  msgs.push(fxLive_(st, force));
  msgs.push(fxCheckIfDue_(st));
  try { msgs.push(pv2IfDue_(st)); } catch (e) { recordError_('PV2', e.message || String(e)); }   // PowrotV2.gs: sygnały i inwestor
  return msgs.filter(x => x).join(' · ');
}

/** Wolne uruchomienie (bez zbierania akcji): jedna porcja historii — jeden instrument. */
function fxHistoryIfDue_(force) {
  const st = fxStateLoad_();
  const now = Date.now();
  const inst = FX.INSTRUMENTS.find(i => !(st.sym[i.id] && st.sym[i.id].hist) &&
    (force || now - ((st.sym[i.id] || {}).histTry || 0) > 30 * 60000));
  if (!inst) return '';
  st.sym[inst.id] = Object.assign(st.sym[inst.id] || {}, { histTry: now });
  fxStateSave_(st);
  try { return fxHistory_(inst, st); }
  catch (e) { recordError_('FX', `historia ${inst.id}: ${e.message || e}`); return ''; }
}

/** Świece z odpowiedzi Yahoo: [{ t: start (s, pełna godzina), o, h, l, c }], tylko zamknięte i w godzinach rynku. */
function fxBars_(inst, result, nowSec) {
  const ts = (result && result.timestamp) || [];
  const q = (result && result.indicators && result.indicators.quote && result.indicators.quote[0]) || {};
  const byT = {};
  for (let i = 0; i < ts.length; i++) {
    const o = q.open && q.open[i], h = q.high && q.high[i], l = q.low && q.low[i], c = q.close && q.close[i];
    if ([o, h, l, c].some(x => typeof x !== 'number' || !isFinite(x) || x <= 0)) continue;
    const t = Math.floor(ts[i] / FX.STEP_SEC) * FX.STEP_SEC;
    if (t + FX.STEP_SEC > nowSec) continue;                 // świeca jeszcze trwa
    if (!fxSlotOpen_(inst, t)) continue;                    // poza godzinami rynku (pojedyncze wpisy Yahoo)
    const r = x => fxRound_(x, inst.dp);
    byT[t] = { t, o: r(o), h: r(Math.max(h, o, c)), l: r(Math.min(l, o, c)), c: r(c) };   // późniejszy wpis wygrywa
  }
  return Object.keys(byT).map(Number).sort((a, b) => a - b).map(t => byT[t]);
}

/**
 * Wiele zapytań Yahoo naraz (fetchAll): reqs = [{ inst, p1, p2 }] → { id: { result } | { error } }.
 * Nieudane — drugi serwer Yahoo, z symbolem zapasowym (alt), jeśli instrument go ma.
 */
function fxFetchMany_(reqs) {
  const out = {};
  let todo = reqs.map(r => Object.assign({ sym: r.inst.yahoo }, r));
  for (let h = 0; h < YAHOO_HOSTS.length && todo.length; h++) {
    const host = YAHOO_HOSTS[h];
    let resps = null;
    try {
      resps = UrlFetchApp.fetchAll(todo.map(r => ({
        url: yahooUrl_(host, r.sym, `interval=1h&period1=${Math.floor(r.p1)}&period2=${Math.floor(r.p2)}&includePrePost=false`),
        muteHttpExceptions: true, headers: YAHOO_HEADERS })));
    } catch (e) {
      todo.forEach(r => { out[r.inst.id] = { error: `Yahoo: ${e.message || e} (${host})` }; });
      resps = null;
    }
    if (RUN_) RUN_.yahooRequests = (RUN_.yahooRequests || 0) + todo.length;
    const failed = [];
    todo.forEach((r, k) => {
      if (resps) out[r.inst.id] = yahooParse_(resps[k], host);
      if (out[r.inst.id].error) failed.push(Object.assign({}, r, { sym: r.inst.alt || r.inst.yahoo }));
    });
    todo = failed;
    if (todo.length && h < YAHOO_HOSTS.length - 1) Utilities.sleep(1000);
  }
  return out;
}

// ============================================================================
//  FIRESTORE: dokument dnia, podsumowanie instrumentu, system/fx1h
// ============================================================================
function fxDocName_(id, date) { return `${fsBase_()}/${FX.COLL}/${id}/days/${date}`; }

/**
 * Zapis dokumentu dnia. real — świece z Yahoo, fill — uśrednione (oznaczone w fillT).
 * meta: { tries, status, upTo, fromT } — upTo: dla dnia, który trwa, braki liczone tylko do tej chwili.
 */
function fxDayWrite_(inst, date, real, fill, meta, nowIso) {
  const all = real.concat(fill).sort((a, b) => a.t - b.t);
  const t0 = fxDayStart_(date);
  const info = fxDayInfo_(inst, date, real.map(b => b.t), fill.map(b => b.t), meta.upTo, meta.fromT);
  const arr = (vals, int) => ({ arrayValue: { values: vals.map(v => int ? { integerValue: String(v) } : { doubleValue: v }) } });
  const write = {
    update: {
      name: fxDocName_(inst.id, date),
      fields: {
        symbol: { stringValue: inst.id }, date: { stringValue: date }, interval: { stringValue: '1h' },
        bars: { integerValue: String(all.length) },
        t: arr(all.map(b => (b.t - t0) / 60), true),
        o: arr(all.map(b => b.o)), h: arr(all.map(b => b.h)), l: arr(all.map(b => b.l)), c: arr(all.map(b => b.c)),
        expected: { integerValue: String(info.expected) }, missing: { integerValue: String(info.missing) },
        filled: { integerValue: String(fill.length) }, fillT: arr(fill.map(b => (b.t - t0) / 60), true),
        tries: { integerValue: String(meta.tries || 0) }, status: { stringValue: meta.status },
        updatedAt: { timestampValue: nowIso },
      },
    },
  };
  return { write, info };
}

/** fx1h/{SYMBOL} — opis instrumentu i historii (zapis przy pobraniu historii). */
function fxSummaryWrite_(inst, s, nowIso) {
  return { update: { name: `${fsBase_()}/${FX.COLL}/${inst.id}`, fields: {
    symbol: { stringValue: inst.id }, yahoo: { stringValue: inst.yahoo }, group: { stringValue: inst.group },
    interval: { stringValue: '1h' }, pip: { doubleValue: inst.pip }, digits: { integerValue: String(inst.dp) },
    historyFirstDate: { stringValue: s.first || '' }, historyAt: { timestampValue: nowIso },
    historyBars: { integerValue: String(s.histBars || 0) }, updatedAt: { timestampValue: nowIso } } } };
}

/** system/fx1h — lista instrumentów i ostatnia świeca każdego (Mac czyta jeden dokument). */
function fxStatusWrite_(st, nowIso) {
  const last = {}, close = {};
  FX.INSTRUMENTS.forEach(i => {
    const s = st.sym[i.id];
    if (s && s.last) {
      last[i.id] = { timestampValue: new Date(s.last * 1000).toISOString() };
      close[i.id] = { doubleValue: s.lastClose };
    }
  });
  return { update: { name: `${fsBase_()}/${FX.STATUS_DOC}`, fields: {
    interval: { stringValue: '1h' },
    symbols: { arrayValue: { values: FX.INSTRUMENTS.map(i => ({ stringValue: i.id })) } },
    groups: { mapValue: { fields: FX.INSTRUMENTS.reduce((m, i) => { m[i.id] = { stringValue: i.group }; return m; }, {}) } },
    last: { mapValue: { fields: last } }, lastClose: { mapValue: { fields: close } },
    updatedAt: { timestampValue: nowIso } } } };
}

/** Dokument dnia z Firestore → { real: [...], fillT: [s], tries, status } albo null. */
function fxDayRead_(id, date) {
  const resp = UrlFetchApp.fetch(`https://firestore.googleapis.com/v1/${fxDocName_(id, date)}`, {
    muteHttpExceptions: true, headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() } });
  if (resp.getResponseCode() === 404) return null;
  if (resp.getResponseCode() !== 200) throw new Error(`Firestore HTTP ${resp.getResponseCode()} (fx1h ${id} ${date})`);
  return fxDocParse_(JSON.parse(resp.getContentText()).fields || {}, date);
}

function fxDocParse_(f, date) {
  const t0 = fxDayStart_(date);
  const num = v => Number(v.doubleValue !== undefined ? v.doubleValue : v.integerValue);
  const a = k => ((f[k] && f[k].arrayValue && f[k].arrayValue.values) || []).map(num);
  const tt = a('t'), o = a('o'), h = a('h'), l = a('l'), c = a('c');
  const fillT = a('fillT').map(m => t0 + m * 60);
  const isFill = {};
  fillT.forEach(t => { isFill[t] = 1; });
  const real = [];
  for (let i = 0; i < tt.length; i++) {
    const t = t0 + tt[i] * 60;
    if (!isFill[t]) real.push({ t, o: o[i], h: h[i], l: l[i], c: c[i] });
  }
  return { real, fillT, tries: f.tries ? num(f.tries) : 0, status: f.status ? f.status.stringValue : '' };
}

function fxCommit_(writes, chunk) {
  for (let i = 0; i < writes.length; i += (chunk || 200)) firestoreCommit_(writes.slice(i, i + (chunk || 200)));
}

// ============================================================================
//  HISTORIA (jednorazowo, instrument po instrumencie)
// ============================================================================
/**
 * 728 dni wstecz jednym zapytaniem. Dni starsze niż wczoraj: braki od razu uśrednione (Yahoo właśnie
 * oddało wszystko, co ma); wczoraj — zwykła kontrola (3 próby); dziś — „dzień trwa”.
 */
function fxHistory_(inst, st) {
  const nowSec = Date.now() / 1000;
  const r = fxFetchMany_([{ inst, p1: nowSec - FX.HISTORY_DAYS * 86400, p2: nowSec }])[inst.id];
  if (r.error) throw new Error(r.error);
  const bars = fxBars_(inst, r.result, nowSec);
  if (!bars.length) throw new Error('Yahoo nie zwróciło świec historii');
  const nowIso = new Date().toISOString();
  const today = fxDay_(nowSec), yday = fxDay_(nowSec - 86400);
  const first = fxDay_(bars[0].t);
  const byDay = {};
  bars.forEach(b => { (byDay[fxDay_(b.t)] = byDay[fxDay_(b.t)] || []).push(b); });
  const writes = [], cells = {}, chk = fxCheckLoad_();
  let filled = 0;
  for (let t = fxDayStart_(first); fxDay_(t) <= today; t += 86400) {
    const d = fxDay_(t);
    const real = byDay[d] || [];
    const fromT = (d === first && real.length) ? real[0].t : 0;
    if (d === today) {
      if (real.length) writes.push(fxDayWrite_(inst, d, real, [], { status: 'dzień trwa', upTo: nowSec }, nowIso).write);
      continue;
    }
    const info = fxDayInfo_(inst, d, real.map(b => b.t), [], 0, fromT);
    if (!info.expected) { cells[d] = info; continue; }                 // sobota (pary walutowe) — bez dokumentu
    if (d === yday) {
      writes.push(fxDayWrite_(inst, d, real, [], { status: 'do kontroli', fromT }, nowIso).write);
      chk[`${inst.id}|${d}`] = { tries: 0, next: 0 };
      continue;
    }
    let fill = [], status = d === first ? `pierwszy dzień bazy — od ${Utilities.formatDate(new Date(real[0].t * 1000), 'UTC', 'HH:mm')} UTC` : 'kompletny';
    if (info.missing) {
      fill = fxFill_(inst, bars, info.missingT);
      filled += fill.length;
      status = fill.length === info.missing ? `historia: uzupełniony: ${fill.length} świec uśrednionych`
        : 'brak danych z Yahoo — nie da się uśrednić (brak świec obok)';
    }
    const w = fxDayWrite_(inst, d, real, fill, { status, fromT }, nowIso);
    writes.push(w.write);
    cells[d] = w.info;
  }
  const last = bars[bars.length - 1];
  const s = Object.assign(st.sym[inst.id] || {}, { last: last.t, lastClose: last.c, first, hist: nowIso,
                                                   histBars: bars.length, lastWriteAt: nowIso });
  st.sym[inst.id] = s;
  writes.push(fxSummaryWrite_(inst, s, nowIso), fxStatusWrite_(st, nowIso));
  fxCommit_(writes);
  fxStateSave_(st);
  fxCheckSave_(chk);
  try { fxSheetMerge_(inst.id, cells); } catch (e) { console.warn('FX arkusz: ' + e.message); }
  const done = FX.INSTRUMENTS.filter(i => st.sym[i.id] && st.sym[i.id].hist).length;
  const msg = `FX ${inst.id}: historia ${bars.length} świec 1h od ${first}, ${writes.length - 2} dni, uśrednionych ${filled} ` +
    `(${done}/${FX.INSTRUMENTS.length} instrumentów)`;
  log_('INFO', 'FX', msg);
  return msg;
}

// ============================================================================
//  NA ŻYWO
// ============================================================================
/**
 * Instrumenty z historią, którym brakuje świecy, która powinna być już zamknięta (zamknięcie + 20 s):
 * jedno zapytanie na instrument (fetchAll), od początku dnia UTC ostatniej zapisanej świecy.
 * Spóźnione: w każdym uruchomieniu przez 10 min, potem co 10 min.
 */
function fxLive_(st, force) {
  const nowSec = Date.now() / 1000;
  const due = [];
  FX.INSTRUMENTS.forEach(inst => {
    const s = st.sym[inst.id];
    if (!s || !s.hist || !s.last) return;
    const cur = fxLastClosed_(inst, nowSec - FX.FIRST_FETCH_SEC);     // najnowsza świeca, która powinna być gotowa
    if (cur <= s.last) return;
    const lateMin = (nowSec - cur - FX.STEP_SEC) / 60;               // spóźnienie liczone od najnowszej świecy
    if (!force && lateMin > FX.RETRY_FAST_MIN && nowSec - (s.lastTry || 0) < FX.RETRY_SLOW_MIN * 60) return;
    due.push(inst);
  });
  if (!due.length) return '';
  const res = fxFetchMany_(due.map(inst => ({ inst, p1: fxDayStart_(fxDay_(st.sym[inst.id].last)), p2: nowSec })));
  const today = fxDay_(nowSec);
  const nowIso = new Date().toISOString();
  const writes = [], got = [], errs = [];
  due.forEach(inst => {
    const s = st.sym[inst.id];
    s.lastTry = nowSec;
    const r = res[inst.id];
    if (!r || r.error) { errs.push(`${inst.id}: ${r ? r.error : 'brak odpowiedzi'}`); return; }
    const bars = fxBars_(inst, r.result, nowSec);
    const fresh = bars.filter(b => b.t > s.last);
    if (!fresh.length) return;
    const days = {};
    fresh.forEach(b => { days[fxDay_(b.t)] = 1; });
    Object.keys(days).sort().forEach(d => {
      const w = fxDayWrite_(inst, d, bars.filter(b => fxDay_(b.t) === d), [],
        { status: d === today ? 'dzień trwa' : 'do kontroli', upTo: d === today ? nowSec : 0 }, nowIso);
      writes.push(w.write);
      if (d === today) got.push({ id: inst.id, info: w.info });
    });
    got.push({ id: inst.id, fresh });
  });
  if (errs.length) recordError_('FX', errs.join(' · '));
  const fresh = got.filter(g => g.fresh);
  if (!fresh.length) { fxStateSave_(st); return ''; }
  fresh.forEach(g => {
    const s = st.sym[g.id], lastBar = g.fresh[g.fresh.length - 1];
    s.last = lastBar.t;
    s.lastClose = lastBar.c;
  });
  writes.push(fxStatusWrite_(st, nowIso));
  fxCommit_(writes);
  const at = Date.now() / 1000;                                 // zapis potwierdzony
  if (!st.today || st.today.date !== today) st.today = { date: today, n: 0, delays: [], bars: {}, missing: {} };
  got.forEach(g => {
    if (g.info) { st.today.bars[g.id] = g.info.total; st.today.missing[g.id] = g.info.missing; return; }
    g.fresh.forEach(b => {
      if (fxDay_(b.t) !== today) return;
      st.today.n++;
      st.today.delays.push(Math.round(at - (b.t + FX.STEP_SEC)));
    });
    st.sym[g.id].lastWriteAt = new Date(at * 1000).toISOString();
    st.sym[g.id].lastDelay = Math.round(at - (st.sym[g.id].last + FX.STEP_SEC));
  });
  if (st.today.delays.length > 400) st.today.delays = st.today.delays.slice(-400);
  st.lastWriteAt = new Date(at * 1000).toISOString();
  st.lastDelay = Math.max.apply(null, fresh.map(g => st.sym[g.id].lastDelay));
  fxStateSave_(st);
  return `FX: +${fresh.reduce((n, g) => n + g.fresh.length, 0)} świec (${fresh.map(g => g.id).join(', ')})`;
}

// ============================================================================
//  KONTROLA DNI: 3 próby pobrania braków, potem uśrednienie
// ============================================================================
/** Planuje wczorajszy dzień każdego instrumentu (raz na dobę, od 00:20 UTC) i wykonuje zaległe próby. */
function fxCheckIfDue_(st) {
  const now = new Date();
  const today = fxDay_(now.getTime() / 1000);
  const chk = fxCheckLoad_();
  if (st.checkedDay !== today && now.getUTCHours() * 60 + now.getUTCMinutes() >= FX.CHECK_AFTER_MIN) {
    const y = fxDay_(now.getTime() / 1000 - 86400);
    const cells = {};
    FX.INSTRUMENTS.forEach(inst => {
      const s = st.sym[inst.id];
      if (!s || !s.hist || s.first > y) return;
      if (fxExpected_(inst, y).length) { if (!chk[`${inst.id}|${y}`]) chk[`${inst.id}|${y}`] = { tries: 0, next: 0 }; }
      else (cells[inst.id] = cells[inst.id] || {})[y] = fxDayInfo_(inst, y, [], []);   // sobota: bez kontroli i bez dokumentu
    });
    Object.keys(cells).forEach(id => { try { fxSheetMerge_(id, cells[id]); } catch (e) { console.warn('FX arkusz: ' + e.message); } });
    st.checkedDay = today;
    st.yesterday = { date: y, done: 0, filled: 0 };
    fxStateSave_(st);
    fxCheckSave_(chk);
  }
  const due = Object.keys(chk).filter(k => chk[k].next <= now.getTime()).sort().slice(0, FX.CHECK_PER_RUN);
  if (!due.length) return '';
  const nowSec = now.getTime() / 1000;
  const items = due.map(k => { const p = k.split('|'); return { key: k, inst: fxInst_(p[0]), d: p[1] }; }).filter(x => x.inst);
  const fetchable = items.filter(x => nowSec - fxDayStart_(x.d) <= FX.YAHOO_DAYS * 86400);
  const res = fetchable.length ? fxFetchMany_(fetchable.map(x => ({ inst: x.inst, p1: fxDayStart_(x.d) - 3600,
                                                                     p2: fxDayStart_(x.d) + 86400 + 3600 }))) : {};
  const writes = [], cells = {}, out = [];
  items.forEach(x => {
    try {
      const r = fxCheckDay_(x, chk[x.key], res[x.inst.id], st);
      writes.push(r.write);
      if (r.final) { delete chk[x.key]; (cells[x.inst.id] = cells[x.inst.id] || {})[x.d] = r.info; }
      out.push(`${x.inst.id} ${x.d}: ${r.status}`);
    } catch (e) {
      const c = chk[x.key];
      c.tries++; c.next = Date.now() + FX.CHECK_EVERY_MIN * 60000;
      if (c.tries >= FX.CHECK_TRIES + 2) delete chk[x.key];             // dzień nie do pobrania i nie do zapisu — porzucony
      recordError_('FX', `kontrola ${x.inst.id} ${x.d}: ${e.message || e}`);
    }
  });
  if (writes.length) fxCommit_(writes);
  fxCheckSave_(chk);
  Object.keys(cells).forEach(id => { try { fxSheetMerge_(id, cells[id]); } catch (e) { console.warn('FX arkusz: ' + e.message); } });
  if (st.yesterday) {
    items.forEach(x => { if (x.d === st.yesterday.date && cells[x.inst.id] && cells[x.inst.id][x.d]) {
      st.yesterday.done++; st.yesterday.filled += cells[x.inst.id][x.d].filled; } });
    fxStateSave_(st);
  }
  const fin = out.filter(s => s.indexOf('braki') < 0).length;
  return out.length ? `FX kontrola: ${out.length} (zakończonych ${fin})` : '';
}

/**
 * Jedna próba dla (instrument, dzień): świece z Firestore + świeże z Yahoo (Yahoo wygrywa), braki
 * liczone na nowo. Brak braków → „kompletny”. Po CHECK_TRIES próbach z brakami → uśrednienie.
 * Dzień starszy niż YAHOO_DAYS — od razu uśrednienie.
 */
function fxCheckDay_(x, c, yahoo, st) {
  const inst = x.inst, d = x.d;
  const t0 = fxDayStart_(d);
  const nowSec = Date.now() / 1000;
  const stored = fxDayRead_(inst.id, d) || { real: [], fillT: [], tries: 0, status: '' };
  const byT = {};
  stored.real.forEach(b => { byT[b.t] = b; });
  let anchors = [];
  const old = nowSec - t0 > FX.YAHOO_DAYS * 86400;
  if (!old) {
    if (!yahoo || yahoo.error) throw new Error(yahoo ? yahoo.error : 'brak odpowiedzi Yahoo');
    const got = fxBars_(inst, yahoo.result, nowSec);
    got.forEach(b => { if (b.t >= t0 && b.t < t0 + 86400) byT[b.t] = b; });
    anchors = got.filter(b => b.t < t0 || b.t >= t0 + 86400);
  }
  const real = Object.keys(byT).map(Number).sort((a, b) => a - b).map(t => byT[t]);
  c.tries = old ? Math.max(c.tries + 1, FX.CHECK_TRIES) : c.tries + 1;
  const s = st.sym[inst.id] || {};
  const fromT = (d === s.first && real.length) ? real[0].t : 0;
  const info = fxDayInfo_(inst, d, real.map(b => b.t), [], 0, fromT);
  let fill = [], status;
  if (!info.expected) status = 'weekend — brak handlu';
  else if (!info.missing) status = 'kompletny';
  else if (c.tries < FX.CHECK_TRIES) {
    status = `braki — próba ${c.tries} z ${FX.CHECK_TRIES}`;
    c.next = Date.now() + FX.CHECK_EVERY_MIN * 60000;
  } else {
    fill = fxFill_(inst, real.concat(anchors), info.missingT);
    status = fill.length === info.missing ? `uzupełniony: ${fill.length} świec uśrednionych`
      : 'brak danych z Yahoo — nie da się uśrednić (brak świec obok)';
  }
  const w = fxDayWrite_(inst, d, real, fill, { tries: c.tries, status, fromT }, new Date().toISOString());
  return { write: w.write, info: w.info, status, final: status.indexOf('braki') !== 0 };
}

/**
 * Uśrednienie braków: dla brakującej świecy t najbliższa świeca przed (P) i po (N). Cena biegnie
 * liniowo od zamknięcia P do otwarcia N: open = wartość w chwili t, close = w chwili t + 1 h,
 * high/low = większa/mniejsza z nich. Tylko P albo tylko N — świeca płaska na tej cenie.
 */
function fxFill_(inst, known, missingT) {
  const k = known.slice().sort((a, b) => a.t - b.t);
  const out = [];
  const r = x => fxRound_(x, inst.dp);
  missingT.forEach(t => {
    let lo = 0, hi = k.length;                                    // pierwszy indeks z k[i].t > t
    while (lo < hi) { const m = (lo + hi) >> 1; if (k[m].t <= t) lo = m + 1; else hi = m; }
    const n = lo < k.length ? k[lo] : null;
    let pi = lo - 1;
    while (pi >= 0 && k[pi].t === t) pi--;
    const p = pi >= 0 ? k[pi] : null;
    if (!p && !n) return;
    let o, c;
    if (p && n) {
      const x0 = p.t + FX.STEP_SEC, x1 = n.t;
      const v = x => p.c + (n.o - p.c) * (x - x0) / (x1 - x0);
      o = v(t); c = v(t + FX.STEP_SEC);
    } else { o = c = p ? p.c : n.o; }
    out.push({ t, o: r(o), h: r(Math.max(o, c)), l: r(Math.min(o, c)), c: r(c) });
  });
  return out;
}

// ============================================================================
//  REJESTR DNI Z FIRESTORE (menu „przelicz arkusz FX”)
// ============================================================================
/** Czyta dni wszystkich instrumentów (ok. 1 odczyt na dzień), przebudowuje arkusz FX i planuje kontrolę dni z brakami. */
function fxScan_(st) {
  const nowSec = Date.now() / 1000;
  const today = fxDay_(nowSec), last = fxDay_(nowSec - 86400);
  const chk = fxCheckLoad_();
  const all = {};
  let nDays = 0;
  FX.INSTRUMENTS.forEach(inst => {
    const s = st.sym[inst.id];
    if (!s || !s.hist) return;
    const res = firestorePost_(`${fsBase_()}/${FX.COLL}/${inst.id}:runQuery`, { structuredQuery: {
      from: [{ collectionId: 'days' }],
      select: { fields: ['date', 't', 'fillT', 'status'].map(f => ({ fieldPath: f })) } } });
    const days = {};
    res.forEach(it => {
      const f = it.document && it.document.fields;
      if (!f) return;
      const d = f.date.stringValue;
      if (d >= today) return;
      const t0 = fxDayStart_(d);
      const num = v => Number(v.integerValue !== undefined ? v.integerValue : v.doubleValue);
      const arr = k => ((f[k] && f[k].arrayValue && f[k].arrayValue.values) || []).map(num);
      const fillT = arr('fillT').map(m => t0 + m * 60);
      const isFill = {};
      fillT.forEach(t => { isFill[t] = 1; });
      const realT = arr('t').map(m => t0 + m * 60).filter(t => !isFill[t]).sort((a, b) => a - b);
      const fromT = (d === s.first && realT.length) ? realT[0] : 0;
      const info = fxDayInfo_(inst, d, realT, fillT, 0, fromT);
      if (info.missing) { if (!chk[`${inst.id}|${d}`]) chk[`${inst.id}|${d}`] = { tries: 0, next: 0 }; return; }
      days[d] = info;
    });
    for (let t = fxDayStart_(s.first); fxDay_(t) <= last; t += 86400) {     // dni bez dokumentu
      const d = fxDay_(t);
      if (days[d] || chk[`${inst.id}|${d}`]) continue;
      if (fxExpected_(inst, d).length) chk[`${inst.id}|${d}`] = { tries: 0, next: 0 };
      else days[d] = fxDayInfo_(inst, d, [], []);
    }
    all[inst.id] = days;
    nDays += Object.keys(days).length;
  });
  fxCheckSave_(chk);
  fxSheetRebuild_(all);
  const n = Object.keys(chk).length;
  return `FX: rejestr ${nDays} dni (${Object.keys(all).length} instrumentów)` + (n ? `, do kontroli ${n}` : '');
}

/** Menu: przelicz arkusz FX i rejestr dni z Firestore. */
function fxRebuildNow() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Automat właśnie pracuje — spróbuj za minutę.'); return; }
  try {
    startRun_();
    const r = fxScan_(fxStateLoad_());
    finishRun_(marketContext_(new Date()), r);
    toast_(r);
  } catch (e) { alert_('FX: ' + e.message); }
  finally { lock.releaseLock(); }
}

/** Menu: pobierz teraz (świece na żywo + jedna porcja historii, jeśli trwa). */
function fxNow() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Automat właśnie pracuje — spróbuj za minutę.'); return; }
  try {
    startRun_();
    const r = [fxHistoryIfDue_(true), fxIfDue_(true)].filter(x => x).join(' · ');
    finishRun_(marketContext_(new Date()), r || 'FX: brak nowych świec');
    toast_(r || 'FX: brak nowych świec.');
  } catch (e) { alert_('FX: ' + e.message); }
  finally { lock.releaseLock(); }
}

/**
 * Menu: usuwa starą bazę EURUSD 5 min (fx/EURUSD/days/* i fx/EURUSD, wersje 1.15–1.26) — decyzja
 * człowieka z 10.10.2026 (instrukcja, zasada 2.2). Nieodwracalne: Yahoo nie oddaje świec 5 min
 * starszych niż 60 dni. Pyta o potwierdzenie.
 */
function fxLegacyDelete() {
  const ui = SpreadsheetApp.getUi();
  const ans = ui.alert('Usunąć stare świece EURUSD 5 min?',
    'Kasuje z Firestore całą bazę 5 min (fx/EURUSD, ok. 65 dokumentów) i jej stan w Script Properties. ' +
    'Tego nie da się cofnąć — Yahoo nie oddaje świec 5 min starszych niż 60 dni. Baza godzinowa (fx1h) zostaje.',
    ui.ButtonSet.YES_NO);
  if (ans !== ui.Button.YES) { toast_('Nic nie usunięto.'); return; }
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Automat właśnie pracuje — spróbuj za minutę.'); return; }
  try {
    startRun_();
    const res = firestorePost_(`${fsBase_()}/${FX.LEGACY}:runQuery`, { structuredQuery: {
      from: [{ collectionId: 'days' }], select: { fields: [{ fieldPath: '__name__' }] } } });
    const names = res.map(it => it.document && it.document.name).filter(x => x);
    const writes = names.map(n => ({ delete: n })).concat([{ delete: `${fsBase_()}/${FX.LEGACY}` }]);
    fxCommit_(writes, 400);
    const props = PropertiesService.getScriptProperties();
    ['FX_STATE', 'FX_CHECK'].forEach(k => props.deleteProperty(k));
    const msg = `FX: usunięto starą bazę EURUSD 5 min — ${names.length} dni`;
    log_('INFO', 'FX', msg);
    finishRun_(marketContext_(new Date()), msg);
    toast_(msg);
  } catch (e) { alert_('FX: ' + e.message); }
  finally { lock.releaseLock(); }
}

// ============================================================================
//  ARKUSZ FX — wiersz na dzień UTC (najnowszy na górze), kolumna na instrument
// ============================================================================
function fxSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const cols = fxCols_();
  let sh = ss.getSheetByName(FX.SHEET);
  if (sh && sh.getLastColumn() === cols.length &&
      sh.getRange(1, 1, 1, cols.length).getValues()[0].join('|') === cols.join('|')) return sh;
  if (sh && sh.getLastColumn() > 2 && sh.getLastColumn() < cols.length &&           // dopisane instrumenty (np. 1.52):
      sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].join('|') === cols.slice(0, sh.getLastColumn()).join('|')) {
    const k = sh.getLastColumn();                                                   // nowe kolumny, stare zostają
    if (sh.getMaxColumns() < cols.length) sh.insertColumnsAfter(sh.getMaxColumns(), cols.length - sh.getMaxColumns());
    sh.getRange(1, k + 1, 1, cols.length - k).setValues([cols.slice(k)]).setFontWeight('bold').setBackground('#f1f3f4')
      .setHorizontalAlignment('center');
    sh.setColumnWidths(k + 1, cols.length - k, 90);
    return sh;
  }
  if (!sh) sh = ss.insertSheet(FX.SHEET);
  sh.clear();                                                 // inny układ (np. dawny EURUSD 5 min) — od nowa
  sh.clearConditionalFormatRules();
  sh.getRange(1, 1, sh.getMaxRows(), sh.getMaxColumns()).breakApart();
  if (sh.getMaxColumns() < cols.length) sh.insertColumnsAfter(sh.getMaxColumns(), cols.length - sh.getMaxColumns());
  sh.setTabColor('#0b8043');
  sh.getRange(1, 1, 1, cols.length).setValues([cols]).setFontWeight('bold').setBackground('#f1f3f4');
  sh.setFrozenRows(1);
  sh.setFrozenColumns(2);
  sh.setColumnWidth(1, 100);
  sh.setColumnWidth(2, 50);
  sh.setColumnWidths(3, cols.length - 2, 90);
  sh.getRange(1, 3, 1, cols.length - 2).setHorizontalAlignment('center');
  return sh;
}

/** Komórka: „zapisanych/oczekiwanych”, z „(N)” gdy N świec uśrednionych; dzień bez handlu — „—”. */
function fxCell_(info) {
  if (!info.expected) return '—';
  return `${info.total}/${info.expected}` + (info.filled ? ` (${info.filled})` : '');
}

/** Dopisuje komórki jednego instrumentu: { date: info }. Daty w arkuszu — ciągła lista malejąco. */
function fxSheetMerge_(id, cellsByDate) {
  const dates = Object.keys(cellsByDate);
  if (!dates.length) return;
  const sh = fxSheet_();
  const cols = fxCols_(), W = cols.length, col = cols.indexOf(id);
  const n = Math.max(sh.getLastRow() - 1, 0);
  const cur = n ? sh.getRange(2, 1, n, W).getDisplayValues() : [];
  const map = {};
  cur.forEach(r => { if (r[0]) map[r[0]] = r; });
  dates.forEach(d => {
    if (!map[d]) { map[d] = new Array(W).fill(''); map[d][0] = d; map[d][1] = FX_DOW[isoWeekday_(d)]; }
    map[d][col] = fxCell_(cellsByDate[d]);
  });
  const all = Object.keys(map).sort();
  for (let t = fxDayStart_(all[0]); fxDay_(t) <= all[all.length - 1]; t += 86400) {   // bez dziur w datach
    const d = fxDay_(t);
    if (!map[d]) { map[d] = new Array(W).fill(''); map[d][0] = d; map[d][1] = FX_DOW[isoWeekday_(d)]; }
  }
  fxSheetWrite_(sh, Object.keys(map).sort().reverse().map(d => map[d]));
}

/** Cały arkusz od nowa: { id: { date: info } }. */
function fxSheetRebuild_(all) {
  const sh = fxSheet_();
  const cols = fxCols_(), W = cols.length;
  const map = {};
  Object.keys(all).forEach(id => {
    const col = cols.indexOf(id);
    Object.keys(all[id]).forEach(d => {
      if (!map[d]) { map[d] = new Array(W).fill(''); map[d][0] = d; map[d][1] = FX_DOW[isoWeekday_(d)]; }
      map[d][col] = fxCell_(all[id][d]);
    });
  });
  const n = Math.max(sh.getLastRow() - 1, 0);
  if (n) sh.getRange(2, 1, n, W).clearContent();
  fxSheetWrite_(sh, Object.keys(map).sort().reverse().map(d => map[d]));
}

function fxSheetWrite_(sh, rows) {
  if (!rows.length) return;
  const W = rows[0].length;
  if (sh.getMaxRows() < rows.length + 1) sh.insertRowsAfter(sh.getMaxRows(), rows.length + 1 - sh.getMaxRows());
  const rg = sh.getRange(2, 1, rows.length, W);
  rg.setNumberFormat('@');                                    // „24/24” to tekst, nie data
  rg.setValues(rows);
  const cells = sh.getRange(2, 3, rows.length, W - 2);
  cells.setHorizontalAlignment('center');
  sh.setConditionalFormatRules([SpreadsheetApp.newConditionalFormatRule().whenTextContains('(')   // dni z uśrednionymi
    .setBackground('#fef7e0').setRanges([cells]).build()]);
}

// ============================================================================
//  STATS I TELEMETRIA
// ============================================================================
function fxQuantile_(arr, q) {
  if (!arr.length) return null;
  const s = arr.slice().sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(q * (s.length - 1) + 0.5))];
}

/** Instrumenty z aktualną ostatnią świecą (nie czekają na świecę spóźnioną o więcej niż 5 min). */
function fxUpToDate_(st, nowSec) {
  return FX.INSTRUMENTS.filter(inst => {
    const s = st.sym[inst.id];
    return s && s.last && s.last >= fxLastClosed_(inst, nowSec - 300);
  }).length;
}

const FX_STATUS_LABELS = ['FX 1h — ostatnia świeca', 'FX 1h — opóźnienie', 'FX 1h — dziś / historia'];

/** 3 wiersze do bloku stanu STATS. */
function fxStatusRows_() {
  const st = fxStateLoad_();
  const nowSec = Date.now() / 1000;
  const N = FX.INSTRUMENTS.length;
  const hist = FX.INSTRUMENTS.filter(i => st.sym[i.id] && st.sym[i.id].hist);
  if (!hist.length) return ['historia jeszcze nie pobrana (porcje co minutę, gdy automat nie zbiera akcji)', '', ''];
  const lastT = Math.max.apply(null, hist.map(i => st.sym[i.id].last || 0));
  const t = new Date(lastT * 1000), t2 = new Date((lastT + FX.STEP_SEC) * 1000);
  const f = (dd, tz) => Utilities.formatDate(dd, tz, 'HH:mm');
  const sec = s => (s === null || s === undefined) ? '—' : fmtDelay_(s * 1000);
  const fxOpen = fxSlotOpen_(FX.INSTRUMENTS[0], Math.floor(nowSec / 3600) * 3600);
  const eur = st.sym.EURUSD, btc = st.sym.BTCUSD;
  const td = st.today || { delays: [], bars: {}, missing: {} };
  const d = td.delays || [];
  const sum = o => Object.keys(o || {}).reduce((n, k) => n + (o[k] || 0), 0);
  const y = st.yesterday;
  const first = hist.map(i => st.sym[i.id].first).sort()[0];
  return [
    `${fxDay_(lastT)} ${f(t, 'UTC')}–${f(t2, 'UTC')} UTC (${f(t, CONFIG.LOCAL_TZ)}–${f(t2, CONFIG.LOCAL_TZ)} PL) · aktualne ${fxUpToDate_(st, nowSec)}/${N}` +
      (eur && eur.lastClose ? ` · EURUSD ${eur.lastClose}` : '') + (btc && btc.lastClose ? ` · BTC ${btc.lastClose}` : '') +
      (fxOpen ? '' : ' · rynek walutowy zamknięty (BTC 24/7)'),
    `ostatni zapis ${sec(st.lastDelay)} po zamknięciu` + (d.length
      ? ` · dziś (UTC): mediana ${sec(fxQuantile_(d, 0.5))}, 90% ≤ ${sec(fxQuantile_(d, 0.9))}, max ${sec(Math.max.apply(null, d))}`
      : ''),
    `dziś (UTC ${td.date || '—'}): świec ${sum(td.bars)}, brakujących ${sum(td.missing)}` +
      (y ? ` · wczoraj ${y.date}: skontrolowanych ${y.done}/${N}, uśrednionych ${y.filled}` : '') +
      ` · historia ${hist.length}/${N} od ${first} · do kontroli ${Object.keys(fxCheckLoad_()).length} · szczegóły: arkusz FX`,
  ];
}

/** Pole fx w telemetry/state.json. */
function fxTelemetry_() {
  const st = fxStateLoad_();
  const hist = FX.INSTRUMENTS.filter(i => st.sym[i.id] && st.sym[i.id].hist);
  if (!hist.length) return { interval: '1h', collection: FX.COLL, history: `0/${FX.INSTRUMENTS.length}` };
  const nowSec = Date.now() / 1000;
  const d = (st.today && st.today.delays) || [];
  const sym = {};
  hist.forEach(i => { const s = st.sym[i.id]; sym[i.id] = { last: new Date(s.last * 1000).toISOString(), close: s.lastClose, first: s.first }; });
  const sum = o => Object.keys(o || {}).reduce((n, k) => n + (o[k] || 0), 0);
  return {
    interval: '1h', collection: FX.COLL, instruments: FX.INSTRUMENTS.length,
    history: `${hist.length}/${FX.INSTRUMENTS.length}`, upToDate: fxUpToDate_(st, nowSec),
    lastWriteAt: st.lastWriteAt || null, lastDelaySec: st.lastDelay === undefined ? null : st.lastDelay,
    today: st.today ? { date: st.today.date, bars: sum(st.today.bars), missing: sum(st.today.missing),
      delayMedianSec: fxQuantile_(d, 0.5), delayP90Sec: fxQuantile_(d, 0.9), delayMaxSec: d.length ? Math.max.apply(null, d) : null } : null,
    yesterday: st.yesterday || null,
    pendingChecks: Object.keys(fxCheckLoad_()).length,
    sym,
  };
}

// ============================================================================
//  ARKUSZ OKOLICZNOSCI_FX — prognoza FX 1h (instrukcja, sekcja 4c.11)
//  Źródło: branch `fx` (fx/conditions.json, fx/runs.jsonl), zapisuje go Python z Maca.
//  Co 30 min (researchSync) jedno małe zapytanie o ostatni commit brancha `fx`;
//  pliki są pobierane i arkusz przebudowany tylko, gdy commit się zmienił (FX_RUNS).
// ============================================================================
const FXR = {
  BRANCH: 'fx',
  COND: 'fx/conditions.json',
  RUNS: 'fx/runs.jsonl',
  SHEET: 'OKOLICZNOSCI_FX',
  MARK: 'okol-3',                       // znacznik układu (G1); inny — arkusz budowany od nowa
  HEAD: 9,                              // wiersz nagłówków kolumn (= 2 + liczba RUN_LABELS); okoliczności od wiersza 10
  FIX: ['ID', 'Rodzina', 'Kierunek', 'Para', 'Okoliczność', 'Próg', 'Częstość przy kalibracji %'],
  RUN_LABELS: ['Przeliczenie', 'Data (PL)', 'Świec', 'Model na żywo (λ środka)', 'Stożek 80% — trafność (cel 80%)',
               'Kierunek: Brier k=48 (0,25 = moneta)', 'Błąd prognozy zakresu 48 h'],   // wiersze 2–8, etykiety w kolumnie G
  GRAY: '#d9d9d9',
};

/** Trigger researchSync i menu: odświeża arkusz, gdy branch `fx` się zmienił. */
function fxOkolSync_(force) {
  try {
    const sha = fxGhRefSha_();
    if (!sha) return { ok: false, reason: 'brak brancha fx (najpierw python -m ia4.fx.catalog --commit)' };
    const props = PropertiesService.getScriptProperties();
    const st = JSON.parse(props.getProperty('FX_RUNS') || '{}');
    const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(FXR.SHEET);
    const layoutOk = sh && sh.getRange(1, FXR.FIX.length).getValue() === FXR.MARK;
    if (!force && layoutOk && st.sha === sha) return { ok: true, skipped: true };
    const condTxt = fxGhRaw_(FXR.COND);
    if (!condTxt) return { ok: false, reason: 'brak fx/conditions.json na branchu fx' };
    const runs = (fxGhRaw_(FXR.RUNS) || '').split('\n').filter(l => l.trim())
      .map(l => { try { return JSON.parse(l); } catch (e) { return null; } }).filter(x => x);
    const built = fxOkolBuild_(JSON.parse(condTxt), runs, iso =>
      Utilities.formatDate(new Date(iso), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm'));
    fxOkolWrite_(built);
    props.setProperty('FX_RUNS', JSON.stringify({ sha: sha, runs: runs.length, at: new Date().toISOString() }));
    return { ok: true, runs: runs.length };
  } catch (e) {
    console.error('OKOLICZNOSCI_FX: ' + e.message);
    if (force) throw e;
    return { ok: false, reason: e.message };
  }
}

function fxOkolNow() {
  const r = fxOkolSync_(true);
  toast_(r.ok ? `OKOLICZNOSCI_FX odświeżone (przeliczeń: ${r.runs}).` : 'OKOLICZNOSCI_FX: ' + r.reason);
}

/**
 * Czysta funkcja (bez Apps Script): katalog + przeliczenia → wartości, tła, liczba kolumn.
 * Wiersz 1: tytuł (A) i znacznik (G). Wiersze 2–8: nagłówki przeliczeń (etykiety w G).
 * Wiersz 9: nagłówki kolumn. Od wiersza 10: okoliczności w kolejności ID.
 * Komórka przeliczenia: „rating/wystąpienia” (tekst); szara, gdy częstość poza 10–50%.
 */
function fxOkolBuild_(cond, runs, fmtDate) {
  const C = cond.conditions || [];
  const F = FXR.FIX.length, W = F + runs.length, H = FXR.HEAD;
  const blank = () => new Array(W).fill('');
  const values = [], bg = [];
  const d = cond.data || {};
  const title = blank();
  title[0] = `IA 4 — OKOLICZNOSCI_FX · katalog ${cond.catalog} (${C.length} okoliczności, kalibracja ` +
    `${fmtDate(cond.calibratedAt)} na ${d.candles} świecach 1h` + (d.instruments ? ` ${d.instruments.length} instrumentów` : '') +
    `) · w kolumnach przeliczeń: rating / wystąpienia ` +
    `(szare: częstość poza 10–50%) · instrukcja 4c.11`;
  title[F - 1] = FXR.MARK;
  values.push(title);
  FXR.RUN_LABELS.forEach((lab, j) => {
    const row = blank();
    row[F - 1] = lab;
    runs.forEach((r, i) => {
      const sc = r.scenario || {};
      const pc = x => (x === null || x === undefined) ? '—' : Math.round(100 * x) + '%';
      const num = (x, d) => (x === null || x === undefined) ? '—' : x.toFixed(d).replace('.', ',');
      row[F + i] = [r.run, fmtDate(r.at), String((r.data || {}).candles || ''),
                    sc.model ? `${sc.model} (λ ${String(sc.lambda).replace('.', ',')})` : '—',
                    pc(sc.cov80_48), num(sc.brier48, 3), pc(sc.rangeErr)][j];
    });
    values.push(row);
  });
  const head = blank();
  FXR.FIX.forEach((h, i) => { head[i] = h; });
  runs.forEach((r, i) => { head[F + i] = 'rating / wystąpienia'; });
  values.push(head);
  for (let i = 0; i < H; i++) bg.push(new Array(W).fill('#ffffff'));
  C.forEach((c, k) => {
    const row = [c.id, c.familyName || c.family, c.dir, c.pair, c.desc,
                 String(c.theta).replace('.', ','), (100 * c.coverage).toFixed(1).replace('.', ',')];
    const b = new Array(W).fill('#ffffff');
    runs.forEach((r, i) => {
      const x = (r.r || [])[k];
      if (!x) { row.push(''); return; }
      row.push(`${x[0]}/${x[1]}`);
      if (x[2] < 10 || x[2] > 50) b[F + i] = FXR.GRAY;
    });
    values.push(row);
    bg.push(b);
  });
  return { values: values, bg: bg, width: W, fixed: F };
}

function fxOkolWrite_(b) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(FXR.SHEET) || ss.insertSheet(FXR.SHEET);
  const rows = b.values.length, W = b.width;
  sh.clear();
  if (sh.getMaxColumns() < W) sh.insertColumnsAfter(sh.getMaxColumns(), W - sh.getMaxColumns());
  if (sh.getMaxRows() < rows) sh.insertRowsAfter(sh.getMaxRows(), rows - sh.getMaxRows());
  sh.setTabColor('#1a73e8');
  const all = sh.getRange(1, 1, rows, W);
  all.setNumberFormat('@');                                   // „41/344” to tekst, nie data ani ułamek
  all.setValues(b.values);
  all.setBackgrounds(b.bg);
  sh.getRange(1, 1, 1, b.fixed - 1).merge().setFontWeight('bold');
  sh.getRange(1, b.fixed).setFontColor('#999999');
  sh.getRange(2, b.fixed, FXR.RUN_LABELS.length, 1).setFontWeight('bold').setHorizontalAlignment('right');
  if (W > b.fixed) sh.getRange(2, b.fixed + 1, FXR.RUN_LABELS.length + 1, W - b.fixed)
    .setFontWeight('bold').setHorizontalAlignment('center');
  sh.getRange(FXR.HEAD, 1, 1, W).setFontWeight('bold').setBackground('#e8f0fe');
  if (rows > FXR.HEAD) sh.getRange(FXR.HEAD + 1, b.fixed + 1, rows - FXR.HEAD, Math.max(W - b.fixed, 1))
    .setHorizontalAlignment('center');
  sh.setFrozenRows(FXR.HEAD);
  sh.setFrozenColumns(1);
  sh.setColumnWidth(5, 520);
  sh.setColumnWidth(2, 210);
}

/** Ostatni commit brancha fx (null = brak brancha). */
function fxGhRefSha_() {
  const resp = UrlFetchApp.fetch(`https://api.github.com/repos/${TELEMETRY.REPO}/git/ref/heads/${FXR.BRANCH}`, {
    muteHttpExceptions: true, headers: fxGhHeaders_('application/vnd.github+json') });
  const code = resp.getResponseCode();
  if (code === 404) return null;
  if (code !== 200) throw new Error(`GitHub HTTP ${code} (ref ${FXR.BRANCH})`);
  return JSON.parse(resp.getContentText()).object.sha;
}

/** Surowa treść pliku z brancha fx (null = brak). */
function fxGhRaw_(path) {
  const resp = UrlFetchApp.fetch(`https://api.github.com/repos/${TELEMETRY.REPO}/contents/${path}?ref=${FXR.BRANCH}`, {
    muteHttpExceptions: true, headers: fxGhHeaders_('application/vnd.github.raw') });
  const code = resp.getResponseCode();
  if (code === 404) return null;
  if (code !== 200) throw new Error(`GitHub HTTP ${code} (${path})`);
  return resp.getContentText('UTF-8');
}

function fxGhHeaders_(accept) {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('brak tokenu GitHub (menu IA 4 → Ustaw token GitHub)');
  return { Authorization: 'Bearer ' + token, Accept: accept };
}
