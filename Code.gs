/**
 * ============================================================================
 *  IA 4 — automat bieżący  (Yahoo Finance → Firestore)
 * ============================================================================
 *  Zbiera na bieżąco świece 1h z sesji regularnej USA dla 30 instrumentów:
 *    • GŁÓWNE    — AAPL, TSLA, NVDA (widoczne w dashboardzie),
 *    • KONTROLNE — 50 spółek „for proof” z listy w Proof.gs,
 *    • TŁO RYNKU — SPY, QQQ, ^VIX (kontekst do Etapu 3, nie handlujemy nimi).
 *
 *  Dane trafiają wyłącznie do Firestore. Arkusz służy tylko do monitoringu
 *  (STATS) i do analiz (STRATEGIE, BACKTEST, KOMBINACJE, BENCHMARK).
 *
 *  FORMAT W FIRESTORE — taki sam jak przy pobieraniu historii:
 *    stocks/{SYMBOL}/candles/{data}_{nr}   – spółki główne, jedna świeca na
 *                                            dokument (dashboard nasłuchuje
 *                                            ich na żywo)
 *    proof/{SYMBOL}/sessions/{data}        – spółki kontrolne, cała sesja
 *                                            w jednym dokumencie (tablice)
 *    context/{ID}/sessions/{data}          – tło rynku, ten sam format;
 *                                            ^VIX zapisywany jako VIX
 *
 *  JAK TO DZIAŁA
 *  • Trigger uruchamia runCollector() co 5 minut, całą dobę.
 *  • Poza sesją nic nie pobiera, tylko odświeża „heartbeat” w STATS.
 *  • Gdy zamknie się kolejna świeca godzinowa (+5 min zapasu), pobiera dane
 *    z Yahoo i zapisuje WYŁĄCZNIE zamknięte świece, których jeszcze nie ma.
 *  • Pamięć „co już zapisane” trzyma we właściwościach skryptu. Przesuwa ją
 *    dopiero po potwierdzeniu zapisu przez Firestore — nieudany zapis zostanie
 *    powtórzony przy kolejnym uruchomieniu, a nie uznany za wykonany.
 *  • Święta, sesje skrócone i zmiany czasu są obsługiwane automatycznie.
 *
 *  PIERWSZE URUCHOMIENIE PO ZMIANIE: menu IA 4 → Konfiguruj. Konfiguracja
 *  uzupełnia w Firestore ewentualne braki z ostatniego miesiąca i dopiero
 *  wtedy usuwa stare arkusze AAPL, TSLA i NVDA.
 *
 *  Plik wymaga Proof.gs (listy spółek kontrolnych i tła rynku) oraz
 *  Project.gs (stan projektu w STATS). Zasady pracy: IA4_INSTRUKCJA.md.
 * ============================================================================
 */

// ============================================================================
//  KONFIGURACJA
// ============================================================================
const CONFIG = {
  SYMBOLS: ['AAPL', 'TSLA', 'NVDA'],   // spółki główne (dashboard); kontrolne są w Proof.gs
  STATS_SHEET: 'STATS',

  MARKET_TZ: 'America/New_York',
  LOCAL_TZ: 'Europe/Warsaw',
  SESSION_OPEN_MIN: 9 * 60 + 30, // 9:30 ET
  SESSION_CLOSE_MIN: 16 * 60,    // 16:00 ET

  SLOT_LABELS_PL: ['15:30–16:30', '16:30–17:30', '17:30–18:30', '18:30–19:30',
                   '19:30–20:30', '20:30–21:30', '21:30–22:00'],
  SLOT_LABELS_ET: ['09:30–10:30', '10:30–11:30', '11:30–12:30', '12:30–13:30',
                   '13:30–14:30', '14:30–15:30', '15:30–16:00'],

  TRIGGER_EVERY_MIN: 5,      // co ile minut działa automat (dozwolone: 1, 5, 10, 15, 30)
  BUFFER_MIN: 5,             // ile minut po zamknięciu świecy czekamy, aż dane „dojrzeją”
  POLL_AFTER_CLOSE_MIN: 45,  // jak długo po zamknięciu sesji jeszcze dociągamy braki
  LIVE_RANGE: '5d',          // zakres pobierania w trybie automatycznym
  CATCHUP_RANGE: '1mo',      // zakres przy konfiguracji i „Uzupełnij braki”
  FETCH_PAUSE_MS: 700,       // odstęp między zapytaniami do Yahoo (27 spółek)

  FIRESTORE_ENABLED: true,
  FIREBASE_PROJECT_ID: 'ia-4-ff7af',
  FIRESTORE_DATABASE: '(default)',

  LOG_MAX_ROWS: 100,
};

const SLOTS = CONFIG.SLOT_LABELS_PL.length;          // 7 świec na pełną sesję
const OPEN = CONFIG.SESSION_OPEN_MIN;
const CLOSE = CONFIG.SESSION_CLOSE_MIN;
const DAY_NAMES_PL = ['pn', 'wt', 'śr', 'czw', 'pt', 'sob', 'nd'];
const YAHOO_HOSTS = ['query1.finance.yahoo.com', 'query2.finance.yahoo.com'];
const YAHOO_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
  'Accept': 'application/json',
};

// Układ arkusza STATS (numery wierszy)
const STATS = {
  STATUS: 3, LAST_RUN: 4, LAST_ACTION: 5, LAST_WRITE: 6, ET_NOW: 7, SESSION: 8,
  SESSION_HOURS: 9, TRIGGER: 10, RUNS: 11, FETCHES: 12, CANDLES: 13, ERRORS: 14,
  FIRESTORE: 15, LAST_ERROR: 16,
  PROJ_STAGE: 18, PROJ_GAPS: 19, PROJ_VAULT: 20,
  SYM_HEADER: 22, SYM_FIRST: 23,
};
const SYM_TABLE_COLS = 8;

/** Wszystkie spółki zbierane na bieżąco: najpierw główne, potem kontrolne. */
function liveSymbols_() {
  const proof = (typeof PROOF !== 'undefined' && PROOF.SYMBOLS) ? PROOF.SYMBOLS : [];
  const ctx = (typeof CONTEXT !== 'undefined' && CONTEXT.SYMBOLS) ? CONTEXT.SYMBOLS : [];
  const out = [];
  CONFIG.SYMBOLS.concat(proof, ctx).forEach(s => { if (out.indexOf(s) < 0) out.push(s); });
  return out;
}
function isMain_(symbol) { return CONFIG.SYMBOLS.indexOf(symbol) >= 0; }

/** Grupa instrumentu: main (główne), proof (kontrolne), context (tło rynku). */
function symbolGroup_(symbol) {
  if (isMain_(symbol)) return 'main';
  if (typeof CONTEXT !== 'undefined' && CONTEXT.SYMBOLS.indexOf(symbol) >= 0) return 'context';
  return 'proof';
}
const GROUP_LABELS = { main: 'główna', proof: 'kontrolna', context: 'tło rynku' };
const GROUP_COLLECTION = { main: 'stocks', proof: 'proof', context: 'context' };
function fsCollection_(symbol) { return GROUP_COLLECTION[symbolGroup_(symbol)]; }
/** Identyfikator w Firestore: bez „^” (np. ^VIX → VIX), żeby nie kodować go w adresach. */
function fsId_(symbol) { return String(symbol).replace(/^\^/, ''); }

function logTitleRow_() { return STATS.SYM_FIRST + liveSymbols_().length + 1; }
function logFirstRow_() { return logTitleRow_() + 2; }

/** Klucz świecy do porównań „która nowsza”: RRRRMMDD * 10 + numer świecy (1…7). */
function barKey_(b) { return Number(b.date.replace(/-/g, '')) * 10 + b.slot + 1; }


// ============================================================================
//  MENU I FUNKCJE PUBLICZNE
// ============================================================================
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('IA 4')
    .addSubMenu(ui.createMenu('🗂 Projekt')
      .addItem('📋 Pokaż / odśwież stan projektu', 'projectRefresh')
      .addItem('📤 Przygotuj podsumowanie do wklejenia', 'projectExportBriefing')
      .addItem('🔍 Pełny audyt danych', 'runFullAudit')
      .addItem('✅ Zamknij bieżący etap', 'closeCurrentStage')
      .addSeparator()
      .addItem('🧹 Etap 0: usuń stare analizy', 'etap0Cleanup'))
    .addSeparator()
    .addItem('⚙️ Konfiguruj i włącz automat', 'setup')
    .addItem('▶️ Uzupełnij braki (ostatni miesiąc)', 'runNow')
    .addItem('🔥 Test połączenia z Firestore', 'testFirestore')
    .addSeparator()
    .addSubMenu(ui.createMenu('📜 Historia wstecz → Firestore')
      .addItem('▶️ Start / wznów', 'startHistory')
      .addItem('⏭ Pobierz kolejny dzień teraz', 'historyStepNow')
      .addItem('⏸ Zatrzymaj', 'stopHistory')
      .addItem('↺ Reset do daty startowej', 'resetHistory'))
    .addSubMenu(ui.createMenu('🔬 Spółki kontrolne i tło rynku')
      .addItem('▶️ Pobierz historię', 'startProof')
      .addItem('🔄 Uzupełnij najnowsze', 'refreshProof')
      .addItem('⏸ Zatrzymaj', 'stopProof')
      .addItem('↺ Reset', 'resetProof'))
    .addSeparator()
    .addItem('⏹ Zatrzymaj automat bieżący', 'stopCollector')
    .addToUi();
}

/**
 * Konfiguracja. Można uruchamiać wielokrotnie.
 * Najpierw uzupełnia Firestore danymi z ostatniego miesiąca, a stare arkusze
 * spółek usuwa DOPIERO, gdy zapis się powiódł — żeby nic nie przepadło.
 */
function setup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  ss.setSpreadsheetTimeZone(CONFIG.LOCAL_TZ);
  ss.setRecalculationInterval(SpreadsheetApp.RecalculationInterval.MINUTE); // dla „watchdoga” w STATS

  setupStatsSheet_(ss);
  removeDefaultSheet_(ss);
  installTrigger_();

  const s = execute_('manual', `Konfiguracja: automat co ${CONFIG.TRIGGER_EVERY_MIN} min dla ${liveSymbols_().length} spółek.`);
  const removed = s && s.fsOk ? removeSymbolSheets_(ss) : [];
  orderSheets_(ss);

  if (typeof projectRefresh === 'function') {
    try { projectRefresh(); } catch (e) { console.warn('PROJEKT: ' + e.message); }
  }

  if (s && s.fsOk === false) {
    toast_('Automat działa, ale zapis do Firestore się nie powiódł — stare arkusze spółek zostawiam. Sprawdź STATS.');
  } else {
    toast_(`Gotowe. Automat zbiera ${liveSymbols_().length} spółek.` +
      (removed.length ? ` Usunięto arkusze: ${removed.join(', ')}.` : ''));
  }
}

/** Handler triggera — NIE zmieniaj nazwy. */
function runCollector() { execute_('auto'); }

function runNow() {
  const s = execute_('manual');
  toast_(s ? `Zapisano ${s.written} świec na ${s.symbolsWritten} spółkach.` : 'Poprzednie uruchomienie wciąż trwa.');
}

function stopCollector() {
  const n = removeTriggers_();
  toast_(`Automat zatrzymany (usunięto triggerów: ${n}). Włączysz go ponownie przez „Konfiguruj”.`);
}

function testFirestore() {
  try {
    firestoreCommit_([{
      update: {
        name: `${fsBase_()}/system/test`,
        fields: {
          ping: { timestampValue: new Date().toISOString() },
          from: { stringValue: 'IA 4 / Google Apps Script' },
        },
      },
    }]);
    setFsStatus_({ ok: true, at: new Date().toISOString(), count: 0 });
    alert_('✅ Firestore działa — zapisano dokument system/test.');
  } catch (e) {
    setFsStatus_({ ok: false, at: new Date().toISOString(), error: e.message });
    alert_('❌ ' + e.message +
      '\n\nNajczęstsze przyczyny:\n' +
      '• brak zakresu „datastore” w appsscript.json,\n' +
      '• konto Google, na którym działa skrypt, nie ma dostępu do projektu Firebase,\n' +
      '• baza Firestore nie została jeszcze utworzona w konsoli Firebase.');
  }
}


// ============================================================================
//  SILNIK
// ============================================================================
let RUN_ = null; // stan bieżącego uruchomienia

function execute_(mode, initMessage) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) {
    console.warn('Poprzednie uruchomienie wciąż trwa — pomijam.');
    return null;
  }
  let ctx = null;
  let summary = null;
  let action = '';
  try {
    startRun_();
    if (initMessage) log_('INFO', 'SYSTEM', initMessage);
    ctx = marketContext_(new Date());
    RUN_.counters.runs++;

    if (mode === 'auto') {
      const gate = gate_(ctx);
      if (gate.fetch) summary = collectAll_(CONFIG.LIVE_RANGE, ctx, false);
      else action = gate.reason;
    } else {
      summary = collectAll_(CONFIG.CATCHUP_RANGE, ctx, true);
      log_('INFO', 'SYSTEM', `Uzupełnianie (${CONFIG.CATCHUP_RANGE}): ${summary.written} świec na ${summary.symbolsWritten} spółkach.`);
    }
    if (summary) {
      action = `Pobrano ${summary.fetched}/${liveSymbols_().length} spółek, zapisano ${summary.written} świec` +
               (summary.skipped ? `, aktualnych: ${summary.skipped}` : '');
    }
  } catch (e) {
    if (!RUN_) startRun_();
    recordError_('SYSTEM', e.message || String(e));
    action = 'Błąd krytyczny — szczegóły w dzienniku';
  } finally {
    try {
      finishRun_(ctx || marketContext_(new Date()), action);
    } catch (e2) {
      console.error('Nie udało się zaktualizować STATS: ' + e2);
    }
    lock.releaseLock();
  }
  return summary;
}

/** Czy w trybie automatycznym w ogóle warto pytać Yahoo? */
function gate_(ctx) {
  if (!ctx.weekday) return { fetch: false, reason: 'Weekend — giełda zamknięta' };
  const session = getSession_();
  if (session && session.date === ctx.etDate && session.holiday) {
    return { fetch: false, reason: 'Święto w USA — dziś brak sesji' };
  }
  const closeMin = sessionCloseFor_(session, ctx.etDate);
  if (ctx.etMin < OPEN) return { fetch: false, reason: 'Przed otwarciem sesji' };
  if (ctx.etMin < OPEN + 60 + CONFIG.BUFFER_MIN) {
    return { fetch: false, reason: 'Sesja trwa — czekam na zamknięcie pierwszej świecy' };
  }
  if (ctx.etMin > closeMin + CONFIG.POLL_AFTER_CLOSE_MIN) {
    return { fetch: false, reason: 'Po sesji — dane z dzisiaj zamknięte' };
  }
  // Wszystkie spółki mają już ostatnią zamkniętą świecę — nie ma po co pytać Yahoo.
  const expectedKey = liveExpectedKey_(ctx, closeMin);
  const live = liveLoad_();
  if (expectedKey && liveSymbols_().every(s => live[s] && live[s].k >= expectedKey)) {
    return { fetch: false, reason: 'Sesja trwa — wszystkie spółki aktualne' };
  }
  return { fetch: true };
}

/** Klucz ostatniej świecy, która dziś powinna już być zamknięta (0 — żadna). */
function liveExpectedKey_(ctx, closeMin) {
  const expected = expectedSlots_(ctx.etMin, closeMin);
  return expected ? Number(ctx.etDate.replace(/-/g, '')) * 10 + expected : 0;
}

/**
 * Pobiera świece wszystkich spółek i zapisuje nowe do Firestore.
 * Każda spółka zapisuje się osobno, więc błąd jednej nie blokuje pozostałych.
 * Pamięć „co już zapisane” przesuwamy dopiero po potwierdzeniu zapisu.
 */
function collectAll_(range, ctx, force) {
  const summary = { fetched: 0, skipped: 0, written: 0, symbolsWritten: 0, fsOk: null };
  const symbols = liveSymbols_();
  const live = liveLoad_();
  let session = getSession_();
  const groupLog = { proof: { symbols: 0, candles: 0 }, context: { symbols: 0, candles: 0 } };
  const nowIso = new Date().toISOString();

  symbols.forEach(symbol => {
    const st = live[symbol] || (live[symbol] = {});
    try {
      if (!force) {
        if (session && session.date === ctx.etDate && session.holiday) { st.st = '— święto, brak sesji'; return; }
        const expectedKey = liveExpectedKey_(ctx, sessionCloseFor_(session, ctx.etDate));
        if (expectedKey && st.k >= expectedKey) { summary.skipped++; st.st = '✓ aktualne'; return; }
      }

      if (summary.fetched) Utilities.sleep(CONFIG.FETCH_PAUSE_MS);
      const r = fetchYahoo_(symbol, range);
      RUN_.counters.fetches++;
      summary.fetched++;
      st.t = nowIso;

      // Zabezpieczenie niezależne od `force`: nawet gdy „Uzupełnij braki” pomija
      // sprawdzenie święta na dziś, żadna świeca z dnia bez sesji (weekend albo
      // święto z kalendarza) i tak nie trafi do bazy — niezależnie od tego, co
      // akurat zwróci Yahoo.
      const bars = parseBars_(r.result).filter(b => isoWeekday_(b.date) <= 5 && !US_MARKET_HOLIDAYS[b.date]);
      const hasToday = bars.some(b => b.date === ctx.etDate);
      session = updateSessionFromMeta_(r.result.meta, ctx, hasToday) || session;

      const done = bars.filter(b => isComplete_(b, ctx, session));
      const fresh = force ? done : done.filter(b => barKey_(b) > (st.k || 0));
      if (!fresh.length) { st.st = '✓ OK (brak nowych)'; clearError_(symbol); return; }
      fresh.forEach(b => { b.symbol = symbol; });

      if (CONFIG.FIRESTORE_ENABLED) {
        if (isMain_(symbol)) fsWriteMainCandles_(symbol, fresh);
        else fsWriteSessions_(symbol, done, fresh);
        summary.fsOk = summary.fsOk === false ? false : true;
      }

      // Zapis potwierdzony — dopiero teraz przesuwamy pamięć.
      const last = fresh.reduce((a, b) => barKey_(b) > barKey_(a) ? b : a);
      if (!st.k || barKey_(last) >= st.k) {
        st.k = barKey_(last); st.d = last.date; st.s = last.slot; st.c = last.close;
      }
      st.st = `✓ zapisano ${fresh.length}`;
      summary.written += fresh.length;
      summary.symbolsWritten++;
      RUN_.counters.candles += fresh.length;
      RUN_.props.setProperty('LAST_WRITE', nowIso);
      clearError_(symbol);

      if (isMain_(symbol)) log_('ZAPIS', symbol, describeBars_(fresh));
      else { const g = groupLog[symbolGroup_(symbol)]; g.symbols++; g.candles += fresh.length; }
    } catch (e) {
      const msg = e.message || String(e);
      st.st = '✗ ' + msg.slice(0, 120);
      if (/Firestore/.test(msg)) summary.fsOk = false;
      recordError_(symbol, msg);
    }
  });

  if (groupLog.proof.symbols) {
    log_('ZAPIS', 'KONTROLNE', `Zapisano ${groupLog.proof.candles} świec na ${groupLog.proof.symbols} spółkach kontrolnych.`);
  }
  if (groupLog.context.symbols) {
    log_('ZAPIS', 'TŁO RYNKU', `Zapisano ${groupLog.context.candles} świec na ${groupLog.context.symbols} instrumentach tła.`);
  }
  if (CONFIG.FIRESTORE_ENABLED && summary.written) {
    try { fsWriteStatus_(summary.written); } catch (e) { console.warn('system/status: ' + e.message); }
    setFsStatus_({ ok: summary.fsOk !== false, at: nowIso, count: summary.written });
  }
  liveSave_(live);
  if (RUN_) RUN_.live = live;
  return summary;
}

function liveLoad_() {
  const raw = PropertiesService.getScriptProperties().getProperty('LIVE_STATE');
  return raw ? JSON.parse(raw) : {};
}

function liveSave_(live) {
  PropertiesService.getScriptProperties().setProperty('LIVE_STATE', JSON.stringify(live));
}


// ============================================================================
//  CZAS I SESJA
// ============================================================================
function marketContext_(now) {
  const etDate = Utilities.formatDate(now, CONFIG.MARKET_TZ, 'yyyy-MM-dd');
  const etMin = minutesOf_(now, CONFIG.MARKET_TZ);
  let offset = minutesOf_(now, CONFIG.LOCAL_TZ) - etMin; // PL − ET, zwykle 360 min
  if (offset < 0) offset += 1440;
  const dow = isoWeekday_(etDate); // 1 = pn … 7 = nd
  return { now, etDate, etMin, dow, weekday: dow <= 5, offset };
}

/** Informacje o dzisiejszej sesji (godzina zamknięcia, święto) z metadanych Yahoo. */
function updateSessionFromMeta_(meta, ctx, hasTodayBars) {
  const reg = meta && meta.currentTradingPeriod && meta.currentTradingPeriod.regular;
  if (!reg || !ctx.weekday) return null;

  const start = new Date(reg.start * 1000);
  const end = new Date(reg.end * 1000);
  let info = null;
  if (Utilities.formatDate(start, CONFIG.MARKET_TZ, 'yyyy-MM-dd') === ctx.etDate) {
    info = { date: ctx.etDate, holiday: false, closeMin: minutesOf_(end, CONFIG.MARKET_TZ) };
  } else if (!hasTodayBars && ctx.etMin >= OPEN + 60) {
    info = { date: ctx.etDate, holiday: true };
  }
  if (!info) return null;

  const prev = getSession_();
  const changed = !prev || prev.date !== info.date || prev.holiday !== info.holiday || prev.closeMin !== info.closeMin;
  if (changed) {
    RUN_.props.setProperty('SESSION', JSON.stringify(info));
    if (info.holiday) log_('INFO', 'SESJA', 'Dziś w USA nie ma sesji (święto) — pomijam pobieranie do jutra.');
    else if (info.closeMin < CLOSE) log_('INFO', 'SESJA', `Sesja skrócona — zamknięcie o ${fmtMin_(info.closeMin)} ET.`);
  }
  return info;
}

function getSession_() {
  const raw = PropertiesService.getScriptProperties().getProperty('SESSION');
  return raw ? JSON.parse(raw) : null;
}

function sessionCloseFor_(session, date) {
  return (session && session.date === date && !session.holiday && session.closeMin) ? session.closeMin : CLOSE;
}

function slotsInSession_(closeMin) {
  return Math.min(SLOTS, Math.ceil((closeMin - OPEN) / 60));
}

function slotEnd_(slot, closeMin) {
  return Math.min(OPEN + (slot + 1) * 60, closeMin);
}

/** Ile świec dzisiejszej sesji powinno już być zamkniętych i „dojrzałych”. */
function expectedSlots_(etMin, closeMin) {
  let k = 0;
  for (let s = 0; s < slotsInSession_(closeMin); s++) {
    if (etMin >= slotEnd_(s, closeMin) + CONFIG.BUFFER_MIN) k++;
  }
  return k;
}

function isComplete_(bar, ctx, session) {
  if (bar.date < ctx.etDate) return true;
  if (bar.date > ctx.etDate) return false;
  return ctx.etMin >= slotEnd_(bar.slot, sessionCloseFor_(session, bar.date)) + CONFIG.BUFFER_MIN;
}


// ============================================================================
//  YAHOO FINANCE
// ============================================================================
function fetchYahoo_(symbol, range) {
  const hosts = YAHOO_HOSTS;
  let lastErr = null;
  for (let i = 0; i < hosts.length; i++) {
    const url = `https://${hosts[i]}/v8/finance/chart/${encodeURIComponent(symbol)}` +
                `?interval=1h&range=${range}&includePrePost=false`;
    const t0 = Date.now();
    try {
      const resp = UrlFetchApp.fetch(url, { muteHttpExceptions: true, headers: YAHOO_HEADERS });
      const code = resp.getResponseCode();
      if (code !== 200) {
        lastErr = new Error(`Yahoo HTTP ${code} (${hosts[i]})`);
      } else {
        const json = JSON.parse(resp.getContentText());
        const result = json && json.chart && json.chart.result && json.chart.result[0];
        if (result) return { result, ms: Date.now() - t0, host: hosts[i] };
        const err = json && json.chart && json.chart.error;
        lastErr = new Error('Yahoo: ' + (err ? err.description : 'pusta odpowiedź'));
      }
    } catch (e) {
      lastErr = e;
    }
    if (i < hosts.length - 1) Utilities.sleep(1500);
  }
  throw lastErr;
}

/** Zamienia odpowiedź Yahoo na listę świec przypisanych do slotów sesji (0…6). */
function parseBars_(result) {
  const ts = result.timestamp || [];
  const q = (result.indicators && result.indicators.quote && result.indicators.quote[0]) || {};
  const o = q.open || [], h = q.high || [], l = q.low || [], c = q.close || [];
  const out = [];

  for (let i = 0; i < ts.length; i++) {
    const vals = [o[i], h[i], l[i], c[i]];
    if (vals.some(v => typeof v !== 'number' || !isFinite(v))) continue;

    const d = new Date(ts[i] * 1000);
    const etMin = minutesOf_(d, CONFIG.MARKET_TZ);
    const slot = Math.floor((etMin - OPEN) / 60);
    if (slot < 0 || slot >= SLOTS) continue;

    let offset = minutesOf_(d, CONFIG.LOCAL_TZ) - etMin;
    if (offset < 0) offset += 1440;
    const slotStart = OPEN + slot * 60;
    const aligned = new Date(d.getTime() - ((etMin - slotStart) * 60 + d.getUTCSeconds()) * 1000);

    out.push({
      date: Utilities.formatDate(d, CONFIG.MARKET_TZ, 'yyyy-MM-dd'),
      slot,
      open: round_(vals[0]),
      high: round_(vals[1]),
      low: round_(vals[2]),
      close: round_(vals[3]),
      startET: fmtMin_(slotStart),
      startPL: fmtMin_(slotStart + offset),
      openPL: fmtMin_(OPEN + offset),
      time: aligned,
    });
  }
  return out;
}



// ============================================================================
//  ARKUSZ STATS (monitoring)
// ============================================================================
function setupStatsSheet_(ss) {
  const sh = ss.getSheetByName(CONFIG.STATS_SHEET) || ss.insertSheet(CONFIG.STATS_SHEET);
  const needRows = logFirstRow_() + CONFIG.LOG_MAX_ROWS;
  if (sh.getMaxRows() < needRows) sh.insertRowsAfter(sh.getMaxRows(), needRows - sh.getMaxRows());
  if (sh.getMaxColumns() < SYM_TABLE_COLS) sh.insertColumnsAfter(sh.getMaxColumns(), SYM_TABLE_COLS - sh.getMaxColumns());
  sh.setTabColor('#1a73e8');

  // Układ zmienia się wraz z liczbą instrumentów i sekcją projektu, więc czyścimy
  // cały obszar pod blokiem statusu (kolumny A:H), żeby stare wiersze nie
  // nakładały się na nowe.
  sh.getRange(17, 1, sh.getMaxRows() - 16, SYM_TABLE_COLS)
    .breakApart().clearContent().clearFormat();

  sh.getRange('A1:H1').breakApart().merge()
    .setValue('IA 4 — MONITORING SYSTEMU')
    .setFontSize(14).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange('A2').setValue(`Odświeżane przy każdym uruchomieniu automatu (co ${CONFIG.TRIGGER_EVERY_MIN} min).`)
    .setFontStyle('italic').setFontColor('#5f6368');

  const labels = [
    'Status systemu', 'Ostatnie uruchomienie (PL)', 'Ostatnia akcja', 'Ostatni zapis świecy (PL)',
    'Czas w Nowym Jorku (ET)', 'Sesja USA', 'Godziny sesji dziś (PL)', 'Automat (trigger)',
    'Uruchomień dziś', 'Zapytań do Yahoo dziś', 'Zapisanych świec dziś', 'Błędów dziś',
    'Firestore', 'Ostatni błąd',
  ];
  sh.getRange(STATS.STATUS, 1, labels.length, 1).setValues(labels.map(x => [x]))
    .setFontWeight('bold').setBackground('#f1f3f4');
  sh.getRange(STATS.STATUS, 2, labels.length, 1).setNumberFormat('@');
  sh.getRange(STATS.LAST_RUN, 2).setNumberFormat('yyyy-mm-dd hh:mm:ss');
  sh.getRange(STATS.LAST_WRITE, 2).setNumberFormat('yyyy-mm-dd hh:mm:ss');
  sh.getRange(STATS.RUNS, 2, 4, 1).setNumberFormat('0').setHorizontalAlignment('left');
  sh.getRange(STATS.STATUS, 2).setFontWeight('bold').setHorizontalAlignment('center');

  // Watchdog: działa nawet wtedy, gdy skrypt przestał się uruchamiać
  sh.getRange(STATS.LAST_RUN, 3).setFormula(
    `=IF(B${STATS.LAST_RUN}="","",IF(NOW()-B${STATS.LAST_RUN}>15/1440,` +
    `"⚠ brak uruchomień >15 min — sprawdź trigger","✓ automat żyje"))`);

  // Stan projektu (Project.gs, zasady w IA4_INSTRUKCJA.md)
  sh.getRange(STATS.PROJ_STAGE, 1, 3, 1).setValues([['Etap projektu'], ['Luki w danych'], ['Skarbiec']])
    .setFontWeight('bold').setBackground('#fef7e0');
  sh.getRange(STATS.PROJ_STAGE, 2, 3, 1).setNumberFormat('@');

  // Tabela spółek
  const symbols = liveSymbols_();
  const n = symbols.length;
  sh.getRange(STATS.SYM_HEADER, 1, 1, SYM_TABLE_COLS)
    .setValues([['Spółka', 'Grupa', 'Ostatnia świeca', 'Godzina (PL)', 'Close', 'Świece dziś',
                 'Ostatni fetch (PL)', 'Status']])
    .setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(STATS.SYM_FIRST, 1, n, 2)
    .setValues(symbols.map(s => [s, GROUP_LABELS[symbolGroup_(s)]])).setFontWeight('bold');
  sh.getRange(STATS.SYM_FIRST, 2, n, 3).setNumberFormat('@');
  sh.getRange(STATS.SYM_FIRST, 5, n, 1).setNumberFormat('#,##0.00');
  sh.getRange(STATS.SYM_FIRST, 6, n, 1).setNumberFormat('@');
  sh.getRange(STATS.SYM_FIRST, 7, n, 1).setNumberFormat('yyyy-mm-dd hh:mm');
  sh.getRange(STATS.SYM_FIRST, 8, n, 1).setNumberFormat('@');
  sh.getRange(STATS.SYM_FIRST, 1, CONFIG.SYMBOLS.length, SYM_TABLE_COLS).setBackground('#e8f0fe');
  symbols.forEach((s, i) => {
    if (symbolGroup_(s) === 'context') sh.getRange(STATS.SYM_FIRST + i, 1, 1, SYM_TABLE_COLS).setBackground('#fef7e0');
  });

  // Dziennik zdarzeń
  const lt = logTitleRow_();
  sh.getRange(lt, 1, 1, SYM_TABLE_COLS).merge().setValue('DZIENNIK ZDARZEŃ (najnowsze na górze)')
    .setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(lt + 1, 1, 1, 4).setValues([['Czas (PL)', 'Poziom', 'Źródło', 'Wiadomość']])
    .setFontWeight('bold').setBackground('#f1f3f4');
  sh.getRange(logFirstRow_(), 1, CONFIG.LOG_MAX_ROWS, 1).setNumberFormat('yyyy-mm-dd hh:mm:ss');
  sh.getRange(logFirstRow_(), 2, CONFIG.LOG_MAX_ROWS, 3).setNumberFormat('@');

  sh.setColumnWidth(1, 210);
  sh.setColumnWidth(2, 280);
  sh.setColumnWidth(3, 260);
  sh.setColumnWidths(4, 5, 120);
  sh.setFrozenRows(2);

  // Zapamiętujemy, dla ilu instrumentów zbudowano ten układ. Nagłówek dziennika
  // i tło grup są scalone/pozycjonowane względem TEJ liczby — jeśli lista
  // instrumentów urośnie (np. po zmianie kodu) bez ponownego wywołania tej
  // funkcji, stare scalenie zostaje dokładnie tam, gdzie było, i automat
  // wpisujący nowe wiersze w tabelę zaczyna nadpisywać scaloną komórkę.
  // statsLayoutFresh_() sprawdza to przed każdym renderowaniem.
  PropertiesService.getScriptProperties().setProperty('STATS_LAYOUT_SYMS', String(n));

  // Kolorowanie statusów
  const status = sh.getRange(STATS.STATUS, 2);
  const watchdog = sh.getRange(STATS.LAST_RUN, 3);
  const symStatus = sh.getRange(STATS.SYM_FIRST, 8, n, 1);
  const logLevel = sh.getRange(logFirstRow_(), 2, CONFIG.LOG_MAX_ROWS, 1);
  const rule = () => SpreadsheetApp.newConditionalFormatRule();
  sh.setConditionalFormatRules([
    rule().whenTextEqualTo('OK').setBackground('#ceead6').setFontColor('#0d652d').setRanges([status]).build(),
    rule().whenTextEqualTo('UWAGA').setBackground('#feefc3').setFontColor('#b06000').setRanges([status]).build(),
    rule().whenTextEqualTo('BŁĄD').setBackground('#fad2cf').setFontColor('#a50e0e').setRanges([status]).build(),
    rule().whenTextStartsWith('⚠').setBackground('#fad2cf').setFontColor('#a50e0e').setRanges([watchdog]).build(),
    rule().whenTextStartsWith('✓').setFontColor('#0d652d').setRanges([watchdog, symStatus]).build(),
    rule().whenTextStartsWith('✗').setFontColor('#a50e0e').setRanges([symStatus]).build(),
    rule().whenTextEqualTo('BŁĄD').setFontColor('#a50e0e').setBold(true).setRanges([logLevel]).build(),
    rule().whenTextEqualTo('UWAGA').setFontColor('#b06000').setBold(true).setRanges([logLevel]).build(),
    rule().whenTextEqualTo('ZAPIS').setFontColor('#0d652d').setRanges([logLevel]).build(),
  ]);
}

/**
 * Sprawdza, czy układ arkusza STATS pasuje do bieżącej liczby instrumentów.
 * Gdy nie pasuje (lista spółek urosła po zmianie kodu, a nikt nie uruchomił
 * ponownie „Konfiguruj”), przebudowuje układ automatycznie — inaczej nowe
 * wiersze nadpisywałyby scaloną komórkę nagłówka dziennika ze starego układu
 * i psuły formatowanie w środku tabeli.
 */
function ensureStatsLayout_(ss) {
  const want = liveSymbols_().length;
  const have = Number(PropertiesService.getScriptProperties().getProperty('STATS_LAYOUT_SYMS') || 0);
  if (want === have) return false;
  setupStatsSheet_(ss);
  log_('INFO', 'SYSTEM', `Układ STATS przebudowany: liczba instrumentów zmieniła się z ${have} na ${want}. Dziennik poniżej zaczyna się od nowa.`);
  return true;
}

function finishRun_(ctx, action) {
  const p = RUN_.props;
  saveCounters_(p, RUN_.counters);
  p.setProperty('ERR_SEEN', JSON.stringify(RUN_.errSeen));

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  ensureStatsLayout_(ss);
  const sh = ss.getSheetByName(CONFIG.STATS_SHEET);
  if (!sh) return;

  const status = RUN_.errors.length ? 'BŁĄD' : (RUN_.warnings.length ? 'UWAGA' : 'OK');
  const lastWrite = p.getProperty('LAST_WRITE');
  const lastErr = JSON.parse(p.getProperty('LAST_ERROR') || 'null');
  const session = getSession_();
  const closeMin = sessionCloseFor_(session, ctx.etDate);
  const c = RUN_.counters;

  sh.getRange(STATS.STATUS, 2, 14, 1).setValues([
    [status],
    [ctx.now],
    [action || '—'],
    [lastWrite ? new Date(lastWrite) : ''],
    [`${ctx.etDate} ${fmtMin_(ctx.etMin)} (${DAY_NAMES_PL[ctx.dow - 1]})`],
    [sessionLabel_(ctx, session, closeMin)],
    [sessionHoursLabel_(ctx, session, closeMin)],
    [triggerLabel_()],
    [c.runs],
    [c.fetches],
    [c.candles],
    [c.errors],
    [firestoreLabel_(p)],
    [lastErr ? `${Utilities.formatDate(new Date(lastErr.at), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm')} — ${lastErr.text}` : 'brak'],
  ]);
  if (typeof projectSummary_ === 'function' && sh.getRange(STATS.PROJ_STAGE, 1).getValue() === 'Etap projektu') {
    try { sh.getRange(STATS.PROJ_STAGE, 2, 3, 1).setValues(projectSummary_().map(x => [x])); }
    catch (e) { console.warn('Stan projektu: ' + e.message); }
  }
  renderLiveTable_(sh, ctx, session, closeMin);
  flushLog_(sh);
}

/** Tabela 27 spółek rysowana jednym zapisem z pamięci automatu. */
function renderLiveTable_(sh, ctx, session, closeMin) {
  if (sh.getRange(STATS.SYM_HEADER, 2).getValue() !== 'Grupa') return;   // STATS sprzed zmiany — czeka na „Konfiguruj”
  const live = (RUN_ && RUN_.live) || liveLoad_();
  const symbols = liveSymbols_();
  const noSession = !ctx.weekday || (session && session.date === ctx.etDate && session.holiday);
  const nToday = slotsInSession_(closeMin);

  const rows = symbols.map(s => {
    const st = live[s] || {};
    const today = noSession ? '— (brak sesji)'
      : `${st.d === ctx.etDate ? st.s + 1 : 0} z ${nToday}`;
    return [
      s, GROUP_LABELS[symbolGroup_(s)],
      st.d || '—',
      st.d ? CONFIG.SLOT_LABELS_PL[st.s] : '—',
      st.c !== undefined ? st.c : '',
      today,
      st.t ? new Date(st.t) : '',
      st.st || '—',
    ];
  });
  sh.getRange(STATS.SYM_FIRST, 1, rows.length, SYM_TABLE_COLS).setValues(rows);
}

function sessionLabel_(ctx, session, closeMin) {
  if (!ctx.weekday) return 'ZAMKNIĘTA — weekend';
  if (session && session.date === ctx.etDate && session.holiday) return 'ZAMKNIĘTA — święto w USA';
  if (ctx.etMin < OPEN) return 'PRZED OTWARCIEM';
  if (ctx.etMin < closeMin) return 'OTWARTA';
  return 'ZAMKNIĘTA — po sesji';
}

function sessionHoursLabel_(ctx, session, closeMin) {
  if (!ctx.weekday || (session && session.date === ctx.etDate && session.holiday)) return '—';
  let txt = `${fmtMin_(OPEN + ctx.offset)}–${fmtMin_(closeMin + ctx.offset)}`;
  if (closeMin < CLOSE) txt += ' (sesja skrócona)';
  if (ctx.offset !== 360) txt += ` (różnica czasu ${ctx.offset / 60} h — okres zmiany czasu)`;
  return txt;
}

function triggerLabel_() {
  try {
    const n = ScriptApp.getProjectTriggers().filter(t => t.getHandlerFunction() === 'runCollector').length;
    return n ? `AKTYWNY (co ${CONFIG.TRIGGER_EVERY_MIN} min)` : 'BRAK — uruchom IA 4 → Konfiguruj';
  } catch (e) {
    return 'nie można sprawdzić';
  }
}

function firestoreLabel_(p) {
  if (!CONFIG.FIRESTORE_ENABLED) return 'wyłączony w CONFIG';
  const st = JSON.parse(p.getProperty('FS_STATUS') || 'null');
  if (!st) return 'czeka na pierwszy zapis';
  const at = Utilities.formatDate(new Date(st.at), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm');
  return st.ok ? `OK — ostatni zapis ${at} (${st.count} świec)` : `✗ ${at}: ${st.error}`;
}

function flushLog_(sh) {
  if (!RUN_.logs.length) return;
  const max = CONFIG.LOG_MAX_ROWS;
  const range = sh.getRange(logFirstRow_(), 1, max, 4);
  const existing = range.getValues().filter(r => r.some(x => x !== ''));
  const rows = RUN_.logs.slice().reverse().concat(existing).slice(0, max);
  while (rows.length < max) rows.push(['', '', '', '']);
  range.setValues(rows);
}



// ============================================================================
//  STAN, LICZNIKI, DZIENNIK
// ============================================================================
function startRun_() {
  const props = PropertiesService.getScriptProperties();
  RUN_ = {
    props,
    counters: loadCounters_(props),
    logs: [],
    errors: [],
    warnings: [],
    errSeen: JSON.parse(props.getProperty('ERR_SEEN') || '{}'),
  };
}

function loadCounters_(props) {
  const today = Utilities.formatDate(new Date(), CONFIG.LOCAL_TZ, 'yyyy-MM-dd');
  const c = JSON.parse(props.getProperty('COUNTERS') || '{}');
  return c.date === today ? c : { date: today, runs: 0, fetches: 0, candles: 0, errors: 0 };
}

function saveCounters_(props, c) { props.setProperty('COUNTERS', JSON.stringify(c)); }

function log_(level, source, message) {
  if (!RUN_) startRun_();
  RUN_.logs.push([new Date(), level, source, message]);
  console.log(`[${level}] ${source}: ${message}`);
}

/** Rejestruje błąd. Ten sam błąd z tego samego źródła trafia do dziennika tylko raz (bez spamu). */
function recordError_(source, message, isWarning) {
  (isWarning ? RUN_.warnings : RUN_.errors).push(`${source}: ${message}`);
  RUN_.counters.errors++;
  RUN_.props.setProperty('LAST_ERROR', JSON.stringify({ at: new Date().toISOString(), text: `${source}: ${message}` }));
  if (RUN_.errSeen[source] !== message) {
    log_(isWarning ? 'UWAGA' : 'BŁĄD', source, message);
    RUN_.errSeen[source] = message;
  }
  console.error(`${source}: ${message}`);
}

function clearError_(source) { delete RUN_.errSeen[source]; }

function setFsStatus_(st) {
  PropertiesService.getScriptProperties().setProperty('FS_STATUS', JSON.stringify(st));
}

function describeBars_(bars) {
  if (bars.length <= 3) {
    return 'Zapisano: ' + bars.map(b => `${b.date} ${CONFIG.SLOT_LABELS_PL[b.slot]} (C ${b.close})`).join(', ');
  }
  const first = bars[0].date, last = bars[bars.length - 1].date;
  return `Zapisano ${bars.length} świec: ` + (first === last ? `sesja ${first}` : `${first} → ${last}`);
}



// ============================================================================
//  FIRESTORE (REST API, autoryzacja kontem Google, na którym działa skrypt)
//  Struktura:
//    stocks/{SYMBOL}                         – ostatnia świeca spółki głównej
//    stocks/{SYMBOL}/candles/{data}_{nr}     – świeca spółki głównej (nr 1…7)
//    proof/{SYMBOL}                          – zakres danych spółki kontrolnej
//    proof/{SYMBOL}/sessions/{data}          – sesja spółki kontrolnej (tablice)
//    context/{ID}/sessions/{data}            – sesja instrumentu tła rynku
//    system/project                          – etap i granica skarbca (Project.gs)
//    system/status                           – kiedy był ostatni zapis
// ============================================================================
function fsBase_() {
  return `projects/${CONFIG.FIREBASE_PROJECT_ID}/databases/${CONFIG.FIRESTORE_DATABASE}/documents`;
}

/** Spółka główna: jeden dokument na świecę + podsumowanie stocks/{SYMBOL}. */
function fsWriteMainCandles_(symbol, bars) {
  const base = fsBase_();
  const nowIso = new Date().toISOString();
  const writes = bars.map(b => ({
    update: { name: `${base}/stocks/${symbol}/candles/${b.date}_${b.slot + 1}`, fields: candleFields_(b, nowIso, 'live') },
  }));
  const l = bars.reduce((a, b) => barKey_(b) > barKey_(a) ? b : a);
  writes.push({
    update: {
      name: `${base}/stocks/${symbol}`,
      fields: {
        symbol: { stringValue: symbol },
        lastDate: { stringValue: l.date },
        lastSlot: { integerValue: String(l.slot + 1) },
        lastLabel: { stringValue: CONFIG.SLOT_LABELS_PL[l.slot] },
        lastClose: { doubleValue: l.close },
        updatedAt: { timestampValue: nowIso },
      },
    },
  });
  for (let i = 0; i < writes.length; i += 400) firestoreCommit_(writes.slice(i, i + 400));
}

/**
 * Spółka kontrolna: przepisuje cały dokument sesji dla każdego dnia, w którym
 * pojawiła się nowa świeca. Do dokumentu trafiają wszystkie zamknięte świece
 * tego dnia (nie tylko nowe), bo sesja to jedna tablica — inaczej nadpisanie
 * wymazałoby wcześniejsze godziny.
 */
function fsWriteSessions_(symbol, doneBars, freshBars) {
  const base = fsBase_();
  const nowIso = new Date().toISOString();
  const dates = {};
  freshBars.forEach(b => { dates[b.date] = 1; });
  const byDate = {};
  doneBars.forEach(b => {
    if (!dates[b.date]) return;
    (byDate[b.date] = byDate[b.date] || {})[b.slot] = b;
  });

  const list = Object.keys(byDate).sort();
  const writes = list.map(date => ({
    update: { name: `${base}/${fsCollection_(symbol)}/${fsId_(symbol)}/sessions/${date}`, fields: sessionFields_(symbol, date, byDate[date], nowIso) },
  }));
  // Podsumowanie aktualizujemy częściowo (updateMask), żeby nie skasować
  // zakresu i liczby sesji zapisanych przy pobieraniu historii.
  writes.push({
    update: {
      name: `${base}/${fsCollection_(symbol)}/${fsId_(symbol)}`,
      fields: { lastDate: { stringValue: list[list.length - 1] }, liveUpdatedAt: { timestampValue: nowIso } },
    },
    updateMask: { fieldPaths: ['lastDate', 'liveUpdatedAt'] },
  });
  for (let i = 0; i < writes.length; i += 400) firestoreCommit_(writes.slice(i, i + 400));
}

/**
 * Wspólny format dokumentu sesji spółki kontrolnej. Używa go zarówno automat
 * bieżący, jak i pobieranie historii (Proof.gs) — dzięki temu backtest czyta
 * jeden format niezależnie od tego, skąd sesja pochodzi.
 */
function sessionFields_(symbol, date, bySlot, nowIso) {
  const slots = Object.keys(bySlot).map(Number).sort((a, b) => a - b);
  const bars = slots.map(s => bySlot[s]);
  const arr = (vals, kind) => ({
    arrayValue: { values: vals.map(v => kind === 'int' ? { integerValue: String(v) } : { doubleValue: v }) },
  });
  return {
    symbol: { stringValue: symbol },
    date: { stringValue: date },
    bars: { integerValue: String(slots.length) },
    slots: arr(slots.map(s => s + 1), 'int'),
    o: arr(bars.map(b => b.open)),
    h: arr(bars.map(b => b.high)),
    l: arr(bars.map(b => b.low)),
    c: arr(bars.map(b => b.close)),
    startPL: { stringValue: bars[0].openPL },
    firstCandleTime: { timestampValue: bars[0].time.toISOString() },
    updatedAt: { timestampValue: nowIso },
  };
}

function fsWriteStatus_(count) {
  firestoreCommit_([{
    update: {
      name: `${fsBase_()}/system/status`,
      fields: {
        lastWrite: { timestampValue: new Date().toISOString() },
        lastWriteCount: { integerValue: String(count) },
        symbols: { integerValue: String(liveSymbols_().length) },
        source: { stringValue: 'google-apps-script' },
      },
    },
  }]);
}

/** Wspólny format dokumentu świecy (automat bieżący i historia). */
function candleFields_(b, nowIso, source) {
  return {
    symbol: { stringValue: b.symbol },
    date: { stringValue: b.date },
    slot: { integerValue: String(b.slot + 1) },
    label: { stringValue: CONFIG.SLOT_LABELS_PL[b.slot] },
    startPL: { stringValue: b.startPL },
    startET: { stringValue: b.startET },
    open: { doubleValue: b.open },
    high: { doubleValue: b.high },
    low: { doubleValue: b.low },
    close: { doubleValue: b.close },
    candleTime: { timestampValue: b.time.toISOString() },
    source: { stringValue: source },
    updatedAt: { timestampValue: nowIso },
  };
}

function firestoreCommit_(writes) {
  const url = `https://firestore.googleapis.com/v1/projects/${CONFIG.FIREBASE_PROJECT_ID}` +
              `/databases/${CONFIG.FIRESTORE_DATABASE}/documents:commit`;
  const resp = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    payload: JSON.stringify({ writes }),
    muteHttpExceptions: true,
  });
  const code = resp.getResponseCode();
  if (code !== 200) {
    let msg = resp.getContentText();
    try { msg = JSON.parse(msg).error.message; } catch (e) { /* zostaw surowy tekst */ }
    throw new Error(`Firestore HTTP ${code}: ${String(msg).slice(0, 250)}`);
  }
}


// ============================================================================
//  TRIGGERY I PORZĄDKI
// ============================================================================
function installTrigger_() {
  removeTriggers_();
  ScriptApp.newTrigger('runCollector').timeBased().everyMinutes(CONFIG.TRIGGER_EVERY_MIN).create();
}

function removeTriggers_() {
  let n = 0;
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'runCollector') { ScriptApp.deleteTrigger(t); n++; }
  });
  return n;
}

/**
 * Usuwa dawne arkusze z świecami spółek głównych (AAPL, TSLA, NVDA).
 * Wywoływane z setup() dopiero po udanym zapisie do Firestore.
 */
function removeSymbolSheets_(ss) {
  const removed = [];
  CONFIG.SYMBOLS.forEach(name => {
    const sh = ss.getSheetByName(name);
    if (!sh || ss.getSheets().length <= 1) return;
    ss.deleteSheet(sh);
    removed.push(name);
  });
  if (removed.length) {
    startRun_();
    log_('INFO', 'SYSTEM', `Usunięto arkusze ${removed.join(', ')} — dane są w Firestore.`);
    const stats = ss.getSheetByName(CONFIG.STATS_SHEET);
    if (stats) flushLog_(stats);
  }
  return removed;
}

function orderSheets_(ss) {
  const stats = ss.getSheetByName(CONFIG.STATS_SHEET);
  if (!stats) return;
  ss.setActiveSheet(stats);
  ss.moveActiveSheet(1);
}

function removeDefaultSheet_(ss) {
  ['Arkusz1', 'Arkusz 1', 'Sheet1'].forEach(name => {
    const sh = ss.getSheetByName(name);
    if (sh && sh.getLastRow() === 0 && ss.getSheets().length > 1) ss.deleteSheet(sh);
  });
}


// ============================================================================
//  NARZĘDZIA
// ============================================================================
function minutesOf_(date, tz) {
  const p = Utilities.formatDate(date, tz, 'HH:mm').split(':');
  return Number(p[0]) * 60 + Number(p[1]);
}

function fmtMin_(m) {
  m = ((m % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

function isoWeekday_(ymd) {
  const p = ymd.split('-').map(Number);
  const d = new Date(Date.UTC(p[0], p[1] - 1, p[2])).getUTCDay(); // 0 = niedziela
  return d === 0 ? 7 : d;
}

function normDate_(v) {
  if (v instanceof Date) return Utilities.formatDate(v, CONFIG.LOCAL_TZ, 'yyyy-MM-dd');
  return String(v || '').trim();
}

function round_(v) { return Math.round(v * 10000) / 10000; }

function toast_(msg) {
  try { SpreadsheetApp.getActiveSpreadsheet().toast(msg, 'IA 4', 8); } catch (e) { console.log(msg); }
}

function alert_(msg) {
  try { SpreadsheetApp.getUi().alert(msg); } catch (e) { console.log(msg); }
}