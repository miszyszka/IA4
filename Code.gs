/**
 * ============================================================================
 *  IA 4 — zbieranie świec 1h  (Yahoo Finance → Firestore)
 *
 *  Wersja projektu: 1.11 (2026-10-01) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Jedyne zadanie tego pliku: żeby baza świec w Firestore była kompletna
 *  i rosła każdego dnia. Zasady i format bazy: IA4_INSTRUKCJA.md.
 *
 *  • Trigger uruchamia runCollector() co minutę, całą dobę.
 *  • W czasie sesji, zaraz po zamknięciu każdej świecy godzinowej, pobiera
 *    dane z Yahoo i zapisuje WYŁĄCZNIE zamknięte świece, których jeszcze nie ma.
 *  • Raz na dobę, po sesji, przepisuje ostatnie 5 sesji wszystkich instrumentów
 *    (nocne odświeżenie) — dziura z dowolnego dnia łata się sama następnej nocy.
 *    Zaraz potem liczy, ile świec ma w bazie każdy instrument.
 *  • Arkusz STATS pokazuje tylko stan automatu. Dane są wyłącznie w Firestore.
 *
 *  Plik współpracuje z Telemetry.gs (stan → telemetry/state.json w GitHub)
 *  i Research.gs (wyniki poszukiwania z brancha `research` → arkusz RESEARCH)
 *  oraz Paper.gs + PaperEngine.gs (sygnały na żywo i wirtualny inwestor).
 * ============================================================================
 */

// ============================================================================
//  KONFIGURACJA
// ============================================================================
const CONFIG = {
  VERSION: '1.11',

  // Trzy grupy instrumentów — nazwy kolekcji w Firestore są historyczne
  // i zostają bez zmian (instrukcja, sekcja 4).
  SYMBOLS: ['AAPL', 'TSLA', 'NVDA'],                     // → stocks/  (dokument na świecę)
  PROOF_SYMBOLS: [                                       // → proof/   (dokument na sesję)
    'DELL', 'AMAT', 'PLTR', 'ORCL', 'XOM', 'V', 'WMT', 'JPM', 'MU', 'META', 'AVGO', 'MSFT',
    'GOOGL', 'JNJ', 'MA', 'ABBV', 'BAC', 'CVX', 'MRK', 'PG', 'HD', 'PM', 'WFC', 'CRM',
    'CAT', 'HON', 'UNP', 'RTX', 'AMZN', 'MCD', 'NKE', 'SBUX', 'T', 'VZ', 'NFLX', 'DIS',
    'UNH', 'LLY', 'PFE', 'MDT', 'PLD', 'AMT', 'LIN', 'FCX', 'NEE', 'DUK', 'GS', 'AXP',
    'KO', 'PEP',
  ],
  CONTEXT_SYMBOLS: ['SPY', 'QQQ'],                       // → context/ (dokument na sesję)
  // Druga grupa kontrolna — wyłącznie do weryfikacji strategii przez człowieka;
  // poszukiwanie na Macu jej nie używa (instrukcja, sekcja 6a).
  DOUBLE_PROOF_SYMBOLS: [                                // → doubleProof/ (dokument na sesję)
    'AMD', 'INTC', 'QCOM', 'CSCO', 'ADBE', 'LRCX', 'C', 'MS', 'SCHW', 'COP',
    'OXY', 'SLB', 'BA', 'GE', 'UBER', 'F', 'GM', 'COST', 'BMY', 'CMCSA',
  ],

  STATS_SHEET: 'STATS',

  // Pobieranie historii doubleProof wstecz (instrukcja, sekcja 4): co godzinę jedna porcja.
  BACKFILL_EVERY_MIN: 60,
  BACKFILL_WINDOW_DAYS: 60,    // porcja: 60 dni kalendarzowych na instrument
  BACKFILL_LIMIT_DAYS: 728,    // granica Yahoo dla świec 1h: ~730 dni wstecz
  BACKFILL_DAY_WRITES: 8000,   // dzienny limit zapisów pobierania historii (Firestore: 20 000)
  MARKET_TZ: 'America/New_York',
  LOCAL_TZ: 'Europe/Warsaw',
  SESSION_OPEN_MIN: 9 * 60 + 30,   // 9:30 ET
  SESSION_CLOSE_MIN: 16 * 60,      // 16:00 ET

  SLOT_LABELS_PL: ['15:30–16:30', '16:30–17:30', '17:30–18:30', '18:30–19:30',
                   '19:30–20:30', '20:30–21:30', '21:30–22:00'],

  TRIGGER_EVERY_MIN: 1,        // co ile minut działa automat
  POLL_AFTER_CLOSE_MIN: 45,    // jak długo po zamknięciu sesji jeszcze dociągamy braki
  // Yahoo publikuje świecę z opóźnieniem kilkunastu–kilkudziesięciu sekund.
  // Tuż po zamknięciu świecy jedno uruchomienie ponawia próbę co 30 s.
  FAST_RETRY_SEC: 30,
  FAST_MAX_TRIES: 8,
  FAST_WINDOW_MIN: 5,
  FAST_MAX_RUN_SEC: 240,       // ponawianie musi się zakończyć przed upływem tylu sekund

  LIVE_RANGE: '5d',            // zakres pobierania na żywo
  CATCHUP_RANGE: '1mo',        // „Uzupełnij ostatni miesiąc” (ręcznie)
  NIGHTLY_RANGE: '5d',         // nocne odświeżenie: ostatnie ~5 sesji
  NIGHTLY_RETRY_MIN: 30,       // odstęp ponowienia, gdy nocne odświeżenie się nie udało
  FETCH_PAUSE_MS: 700,         // odstęp między zapytaniami do Yahoo

  FIREBASE_PROJECT_ID: 'ia-4-ff7af',
  FIRESTORE_DATABASE: '(default)',

  LOG_MAX_ROWS: 60,
};

// Dni bez sesji NYSE (poza weekendami). Świece z tych dni nigdy nie trafiają
// do bazy, cokolwiek zwróci Yahoo. Listę trzeba uzupełnić przed każdym
// nowym rokiem (instrukcja, sekcja 4).
const US_MARKET_HOLIDAYS = {
  '2024-01-01': 1, '2024-01-15': 1, '2024-02-19': 1, '2024-03-29': 1, '2024-05-27': 1,
  '2024-06-19': 1, '2024-07-04': 1, '2024-09-02': 1, '2024-11-28': 1, '2024-12-25': 1,
  '2025-01-01': 1, '2025-01-09': 1, '2025-01-20': 1, '2025-02-17': 1, '2025-04-18': 1,
  '2025-05-26': 1, '2025-06-19': 1, '2025-07-04': 1, '2025-09-01': 1, '2025-11-27': 1,
  '2025-12-25': 1,
  '2026-01-01': 1, '2026-01-19': 1, '2026-02-16': 1, '2026-04-03': 1, '2026-05-25': 1,
  '2026-06-19': 1, '2026-07-03': 1, '2026-09-07': 1, '2026-11-26': 1, '2026-12-25': 1,
};

const SLOTS = CONFIG.SLOT_LABELS_PL.length;   // 7 świec w pełnej sesji
const OPEN = CONFIG.SESSION_OPEN_MIN;
const CLOSE = CONFIG.SESSION_CLOSE_MIN;
const DAY_NAMES_PL = ['pn', 'wt', 'śr', 'czw', 'pt', 'sob', 'nd'];
const YAHOO_HOSTS = ['query1.finance.yahoo.com', 'query2.finance.yahoo.com'];
const YAHOO_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
  'Accept': 'application/json',
};
const GROUP_LABELS = { main: 'główna', proof: 'kontrolna', context: 'tło rynku', doubleProof: 'doubleProof' };
const GROUP_COLLECTION = { main: 'stocks', proof: 'proof', context: 'context', doubleProof: 'doubleProof' };

// Układ arkusza STATS: blok statusu od wiersza 3, potem tabela instrumentów, potem dziennik.
const STATUS_LABELS = [
  'Status', 'Ostatnie uruchomienie (PL)', 'Ostatnia akcja', 'Ostatni zapis świecy (PL)',
  'Czas w Nowym Jorku (ET)', 'Sesja USA', 'Automat (trigger)', 'Zapisanych świec dziś',
  'Błędów dziś', 'Ostatni błąd', 'Nocne odświeżenie', 'Świec w bazie', 'Historia doubleProof',
];
const STATS_FIRST = 3;
const SYM_HEADER = STATS_FIRST + STATUS_LABELS.length + 1;
const SYM_FIRST = SYM_HEADER + 1;
const SYM_COLS = 7;

/** Wszystkie instrumenty: główne, kontrolne, tło rynku, doubleProof. */
function allSymbols_() {
  return CONFIG.SYMBOLS.concat(CONFIG.PROOF_SYMBOLS, CONFIG.CONTEXT_SYMBOLS, CONFIG.DOUBLE_PROOF_SYMBOLS);
}
function isMain_(symbol) { return CONFIG.SYMBOLS.indexOf(symbol) >= 0; }
function symbolGroup_(symbol) {
  if (isMain_(symbol)) return 'main';
  if (CONFIG.CONTEXT_SYMBOLS.indexOf(symbol) >= 0) return 'context';
  if (CONFIG.DOUBLE_PROOF_SYMBOLS.indexOf(symbol) >= 0) return 'doubleProof';
  return 'proof';
}
function fsCollection_(symbol) { return GROUP_COLLECTION[symbolGroup_(symbol)]; }

/** Klucz świecy do porównań „która nowsza”: RRRRMMDD * 10 + numer świecy (1…7). */
function barKey_(b) { return Number(b.date.replace(/-/g, '')) * 10 + b.slot + 1; }

function logFirstRow_() { return SYM_FIRST + allSymbols_().length + 3; }


// ============================================================================
//  MENU I FUNKCJE PUBLICZNE
// ============================================================================
function onOpen() {
  SpreadsheetApp.getUi().createMenu('IA 4')
    .addItem('⚙️ Konfiguruj i włącz automat', 'setup')
    .addItem('▶️ Uzupełnij ostatni miesiąc', 'runNow')
    .addItem('⏪ Historia doubleProof — jedna porcja teraz', 'backfillNow')
    .addItem('🌙 Nocne odświeżenie teraz', 'nightlyNow')
    .addItem('🔥 Test połączenia z Firestore', 'testFirestore')
    .addSeparator()
    .addItem('📡 Wyślij stan do GitHub teraz', 'telemetryPublishNow')
    .addItem('🔑 Ustaw token GitHub', 'telemetrySetToken')
    .addItem('🔬 Odśwież RESEARCH teraz', 'researchSyncNow')
    .addItem('📈 Paper trading — przelicz teraz', 'paperNow')
    .addSeparator()
    .addItem('⏹ Zatrzymaj automat', 'stopCollector')
    .addToUi();
}

/** Konfiguracja: arkusz STATS, triggery, lista instrumentów, uzupełnienie miesiąca. */
function setup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  ss.setSpreadsheetTimeZone(CONFIG.LOCAL_TZ);
  ss.setRecalculationInterval(SpreadsheetApp.RecalculationInterval.MINUTE); // watchdog w STATS
  setupStatsSheet_(ss);
  installTriggers_();
  try { fsWriteUniverse_(); } catch (e) { console.warn('system/universe: ' + e.message); }
  const s = execute_('manual', `Konfiguracja: automat co ${CONFIG.TRIGGER_EVERY_MIN} min dla ${allSymbols_().length} instrumentów.`);
  toast_(s ? `Gotowe. Zapisano ${s.written} świec.` : 'Automat włączony.');
}

/** Handler triggera — NIE zmieniaj nazwy. */
function runCollector() { execute_('auto'); }

function runNow() {
  const s = execute_('manual');
  toast_(s ? `Zapisano ${s.written} świec na ${s.symbolsWritten} instrumentach.` : 'Poprzednie uruchomienie wciąż trwa.');
}

function nightlyNow() {
  const s = execute_('nightly');
  toast_(s ? `Odświeżono: ${s.written} świec na ${s.symbolsWritten} instrumentach.` : 'Poprzednie uruchomienie wciąż trwa.');
}

function stopCollector() {
  const n = removeTriggers_(['runCollector']);
  toast_(`Automat zatrzymany (usunięto triggerów: ${n}). Włączysz go przez „Konfiguruj”.`);
}

function testFirestore() {
  try {
    firestoreCommit_([{ update: { name: `${fsBase_()}/system/status`, fields: statusFields_(0) } }]);
    alert_('✅ Firestore działa — zapisano system/status.');
  } catch (e) {
    alert_('❌ ' + e.message + '\n\nSprawdź zakres „datastore” w appsscript.json i dostęp konta do projektu Firebase.');
  }
}


// ============================================================================
//  SILNIK
// ============================================================================
let RUN_ = null; // stan bieżącego uruchomienia

function execute_(mode, initMessage) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) return null;
  let ctx = null, summary = null, action = '';
  const t0 = Date.now();
  try {
    startRun_();
    if (initMessage) log_('INFO', 'SYSTEM', initMessage);
    ctx = marketContext_(new Date());

    if (mode === 'auto') {
      const gate = gate_(ctx);
      if (gate.fetch) {
        summary = fastCollect_(ctx);
      } else {
        action = gate.reason;
        const extra = nightlyIfDue_(ctx) || countIfDue_() || backfillIfDue_(ctx);
        if (extra) action += ' · ' + extra;
      }
    } else if (mode === 'nightly') {
      summary = runNightly_(ctx);
    } else {
      summary = collectAll_(CONFIG.CATCHUP_RANGE, ctx, true);
      log_('INFO', 'SYSTEM', `Uzupełnianie (${CONFIG.CATCHUP_RANGE}): ${summary.written} świec na ${summary.symbolsWritten} instrumentach.`);
    }
    if (summary && !action) {
      action = `Pobrano ${summary.fetched}/${allSymbols_().length}, zapisano ${summary.written} świec` +
               (summary.skipped ? `, aktualnych: ${summary.skipped}` : '');
    }
    if (mode === 'auto') {
      // paper trading: sygnały i wirtualny inwestor po zamknięciu świecy (Paper.gs)
      try { const p = paperIfDue_(ctx, t0); if (p) action = (action ? action + ' · ' : '') + p; }
      catch (e) { recordError_('PAPER', e.message || String(e)); }
    }
  } catch (e) {
    if (!RUN_) startRun_();
    recordError_('SYSTEM', e.message || String(e));
    action = 'Błąd krytyczny — szczegóły w dzienniku';
  } finally {
    try { finishRun_(ctx || marketContext_(new Date()), action); }
    catch (e2) { console.error('STATS: ' + e2); }
    lock.releaseLock();
  }
  return summary;
}

/**
 * Tuż po zamknięciu świecy ponawia pobranie co FAST_RETRY_SEC, aż trzy spółki
 * główne dostaną nową świecę. Pozostałe instrumenty dociągną się przy
 * kolejnych uruchomieniach.
 */
function fastCollect_(ctx) {
  const closeMin = sessionCloseFor_(getSession_(), ctx.etDate);
  const expectedKey = liveExpectedKey_(ctx, closeMin);
  const expected = expectedSlots_(ctx.etMin, closeMin);
  const sinceClose = expected ? ctx.etMin - slotEnd_(expected - 1, closeMin) : null;
  const t0 = Date.now();
  const summary = collectAll_(CONFIG.LIVE_RANGE, ctx, false);
  let lastDur = Date.now() - t0;                 // ile trwało ostatnie pobranie (75 instrumentów ~1,5 min)
  if (!expectedKey || sinceClose === null || sinceClose >= CONFIG.FAST_WINDOW_MIN) return summary;

  for (let i = 1; i < CONFIG.FAST_MAX_TRIES; i++) {
    const live = liveLoad_();
    if (CONFIG.SYMBOLS.every(s => live[s] && live[s].k >= expectedKey)) break;
    // Limit Apps Script to 6 min na uruchomienie: kolejna próba (pauza + pobranie)
    // musi się zmieścić w FAST_MAX_RUN_SEC — zostaje zapas na STATS i paper trading.
    if (Date.now() - t0 + CONFIG.FAST_RETRY_SEC * 1000 + lastDur > CONFIG.FAST_MAX_RUN_SEC * 1000) break;
    Utilities.sleep(CONFIG.FAST_RETRY_SEC * 1000);
    const t1 = Date.now();
    const s2 = collectAll_(CONFIG.LIVE_RANGE, ctx, false);
    lastDur = Date.now() - t1;
    summary.fetched += s2.fetched;
    summary.written += s2.written;
    summary.symbolsWritten += s2.symbolsWritten;
  }
  return summary;
}

/** Czy w trybie automatycznym w ogóle warto pytać Yahoo? */
function gate_(ctx) {
  if (!ctx.weekday) return { fetch: false, reason: 'Weekend — giełda zamknięta' };
  const session = getSession_();
  if (isHolidayToday_(ctx, session)) return { fetch: false, reason: 'Święto w USA — brak sesji' };
  const closeMin = sessionCloseFor_(session, ctx.etDate);
  if (ctx.etMin < OPEN + 60) return { fetch: false, reason: 'Przed zamknięciem pierwszej świecy' };
  if (ctx.etMin > closeMin + CONFIG.POLL_AFTER_CLOSE_MIN) return { fetch: false, reason: 'Po sesji' };
  const expectedKey = liveExpectedKey_(ctx, closeMin);
  const live = liveLoad_();
  if (expectedKey && allSymbols_().every(s => live[s] && live[s].k >= expectedKey)) {
    return { fetch: false, reason: 'Sesja trwa — wszystko aktualne' };
  }
  return { fetch: true };
}

function isHolidayToday_(ctx, session) {
  return !!(US_MARKET_HOLIDAYS[ctx.etDate] || (session && session.date === ctx.etDate && session.holiday));
}

/** Klucz ostatniej świecy, która dziś powinna już być zamknięta (0 — żadna). */
function liveExpectedKey_(ctx, closeMin) {
  const expected = expectedSlots_(ctx.etMin, closeMin);
  return expected ? Number(ctx.etDate.replace(/-/g, '')) * 10 + expected : 0;
}

/**
 * Pobiera świece wszystkich instrumentów i zapisuje je do Firestore.
 * force = false: tylko świece nowsze niż ostatnia zapisana (praca na żywo).
 * force = true:  wszystkie zamknięte świece z zakresu (uzupełnianie, nocne odświeżenie).
 * Pamięć „co już zapisane” przesuwa się dopiero po potwierdzeniu zapisu.
 */
function collectAll_(range, ctx, force) {
  const summary = { fetched: 0, skipped: 0, written: 0, symbolsWritten: 0, errors: 0 };
  const live = liveLoad_();
  let session = getSession_();
  const nowIso = new Date().toISOString();

  allSymbols_().forEach(symbol => {
    const st = live[symbol] || (live[symbol] = {});
    try {
      if (!force) {
        const expectedKey = liveExpectedKey_(ctx, sessionCloseFor_(session, ctx.etDate));
        if (expectedKey && st.k >= expectedKey) { summary.skipped++; st.st = '✓ aktualne'; return; }
      }
      if (summary.fetched) Utilities.sleep(CONFIG.FETCH_PAUSE_MS);
      const r = fetchYahoo_(symbol, range);
      summary.fetched++;
      st.t = nowIso;

      const bars = parseBars_(r.result).filter(b => isoWeekday_(b.date) <= 5 && !US_MARKET_HOLIDAYS[b.date]);
      session = updateSessionFromMeta_(r.result.meta, ctx, bars.some(b => b.date === ctx.etDate)) || session;

      const done = bars.filter(b => isComplete_(b, ctx, session));
      const fresh = force ? done : done.filter(b => barKey_(b) > (st.k || 0));
      if (!fresh.length) { st.st = '✓ brak nowych'; clearError_(symbol); return; }
      fresh.forEach(b => { b.symbol = symbol; });

      if (isMain_(symbol)) fsWriteMainCandles_(symbol, fresh);
      else fsWriteSessions_(symbol, done, fresh);

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
    } catch (e) {
      const msg = e.message || String(e);
      st.st = '✗ ' + msg.slice(0, 120);
      summary.errors++;
      recordError_(symbol, msg);
    }
  });

  if (summary.written) {
    try { firestoreCommit_([{ update: { name: `${fsBase_()}/system/status`, fields: statusFields_(summary.written) } }]); }
    catch (e) { console.warn('system/status: ' + e.message); }
  }
  liveSave_(live);
  RUN_.live = live;
  return summary;
}

function liveLoad_() {
  return JSON.parse(PropertiesService.getScriptProperties().getProperty('LIVE_STATE') || '{}');
}
function liveSave_(live) {
  PropertiesService.getScriptProperties().setProperty('LIVE_STATE', JSON.stringify(live));
}


// ============================================================================
//  NOCNE ODŚWIEŻENIE I LICZENIE BAZY
//  Raz na dzień sesyjny, po jej zamknięciu, przepisuje ostatnie ~5 sesji
//  wszystkich instrumentów tymi samymi danymi z Yahoo (~400 zapisów). Jeśli
//  w ciągu dnia zabrakło świecy (awaria Yahoo, limit Firestore), wraca ona
//  sama tej samej nocy — bez audytów i list luk. Po udanym odświeżeniu,
//  w kolejnym wolnym przebiegu, liczymy świece każdego instrumentu w bazie.
// ============================================================================
function nightlyIfDue_(ctx) {
  const props = PropertiesService.getScriptProperties();
  if (!ctx.weekday || isHolidayToday_(ctx, getSession_())) return '';
  if (ctx.etMin <= sessionCloseFor_(getSession_(), ctx.etDate) + CONFIG.POLL_AFTER_CLOSE_MIN) return '';
  if (props.getProperty('NIGHTLY_DONE') === ctx.etDate) return '';
  const lastTry = Number(props.getProperty('NIGHTLY_TRY_AT') || 0);
  if (Date.now() - lastTry < CONFIG.NIGHTLY_RETRY_MIN * 60000) return '';

  const s = runNightly_(ctx);
  return `nocne odświeżenie: ${s.written} świec` + (s.errors ? `, błędów ${s.errors} (ponowię)` : '');
}

function runNightly_(ctx) {
  const props = PropertiesService.getScriptProperties();
  props.setProperty('NIGHTLY_TRY_AT', String(Date.now()));
  const s = collectAll_(CONFIG.NIGHTLY_RANGE, ctx, true);
  if (!s.errors) {
    props.setProperty('NIGHTLY_DONE', ctx.etDate);
    props.setProperty('NIGHTLY_INFO', JSON.stringify({ date: ctx.etDate, at: new Date().toISOString(), written: s.written }));
    log_('INFO', 'NOC', `Nocne odświeżenie ${ctx.etDate}: przepisano ${s.written} świec na ${s.symbolsWritten} instrumentach.`);
  }
  return s;
}

/** Po udanym nocnym odświeżeniu: liczba świec i pierwsza data każdego instrumentu. */
function countIfDue_() {
  const props = PropertiesService.getScriptProperties();
  const done = props.getProperty('NIGHTLY_DONE');
  if (!done) return '';
  const prev = JSON.parse(props.getProperty('BASE_COUNTS') || 'null');
  if (prev && prev.date === done) return '';
  const lastTry = Number(props.getProperty('COUNT_TRY_AT') || 0);
  if (Date.now() - lastTry < CONFIG.NIGHTLY_RETRY_MIN * 60000) return '';
  props.setProperty('COUNT_TRY_AT', String(Date.now()));
  const counts = countBase_();
  counts.date = done;
  props.setProperty('BASE_COUNTS', JSON.stringify(counts));
  return `baza policzona: ${counts.total} świec`;
}

function countBase_() {
  const out = { at: new Date().toISOString(), total: 0, items: {} };
  allSymbols_().forEach(symbol => {
    const parent = `${fsBase_()}/${fsCollection_(symbol)}/${symbol}`;
    const coll = isMain_(symbol) ? 'candles' : 'sessions';
    const agg = isMain_(symbol) ? { alias: 'n', count: {} } : { alias: 'n', sum: { field: { fieldPath: 'bars' } } };
    const r = firestorePost_(`${parent}:runAggregationQuery`, {
      structuredAggregationQuery: { structuredQuery: { from: [{ collectionId: coll }] }, aggregations: [agg] },
    });
    const f = r[0] && r[0].result && r[0].result.aggregateFields && r[0].result.aggregateFields.n;
    const n = f ? Number(f.integerValue || f.doubleValue || 0) : 0;
    const q = firestorePost_(`${parent}:runQuery`, {
      structuredQuery: {
        from: [{ collectionId: coll }], select: { fields: [{ fieldPath: 'date' }] },
        orderBy: [{ field: { fieldPath: 'date' }, direction: 'ASCENDING' }], limit: 1,
      },
    });
    const first = q[0] && q[0].document ? q[0].document.fields.date.stringValue : '';
    out.items[symbol] = { candles: n, first };
    out.total += n;
  });
  return out;
}


// ============================================================================
//  CZAS I SESJA
// ============================================================================
function marketContext_(now) {
  const etDate = Utilities.formatDate(now, CONFIG.MARKET_TZ, 'yyyy-MM-dd');
  const etMin = minutesOf_(now, CONFIG.MARKET_TZ);
  let offset = minutesOf_(now, CONFIG.LOCAL_TZ) - etMin; // PL − ET, zwykle 360 min
  if (offset < 0) offset += 1440;
  const dow = isoWeekday_(etDate);
  return { now, etDate, etMin, dow, weekday: dow <= 5, offset };
}

/** Godzina zamknięcia i święto na dziś — z metadanych Yahoo (sesje skrócone). */
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
  if (!prev || prev.date !== info.date || prev.holiday !== info.holiday || prev.closeMin !== info.closeMin) {
    RUN_.props.setProperty('SESSION', JSON.stringify(info));
    if (info.closeMin && info.closeMin < CLOSE) log_('INFO', 'SESJA', `Sesja skrócona — zamknięcie o ${fmtMin_(info.closeMin)} ET.`);
  }
  return info;
}

function getSession_() {
  return JSON.parse(PropertiesService.getScriptProperties().getProperty('SESSION') || 'null');
}
function sessionCloseFor_(session, date) {
  return (session && session.date === date && !session.holiday && session.closeMin) ? session.closeMin : CLOSE;
}
function slotsInSession_(closeMin) { return Math.min(SLOTS, Math.ceil((closeMin - OPEN) / 60)); }
function slotEnd_(slot, closeMin) { return Math.min(OPEN + (slot + 1) * 60, closeMin); }

/** Ile świec dzisiejszej sesji powinno już być zamkniętych. */
function expectedSlots_(etMin, closeMin) {
  let k = 0;
  for (let s = 0; s < slotsInSession_(closeMin); s++) if (etMin >= slotEnd_(s, closeMin)) k++;
  return k;
}

function isComplete_(bar, ctx, session) {
  if (bar.date < ctx.etDate) return true;
  if (bar.date > ctx.etDate) return false;
  return ctx.etMin >= slotEnd_(bar.slot, sessionCloseFor_(session, bar.date));
}


// ============================================================================
//  YAHOO FINANCE
// ============================================================================
function fetchYahoo_(symbol, range) {
  let lastErr = null;
  for (let i = 0; i < YAHOO_HOSTS.length; i++) {
    const url = `https://${YAHOO_HOSTS[i]}/v8/finance/chart/${encodeURIComponent(symbol)}` +
                `?interval=1h&range=${range}&includePrePost=false`;
    try {
      const resp = UrlFetchApp.fetch(url, { muteHttpExceptions: true, headers: YAHOO_HEADERS });
      if (resp.getResponseCode() !== 200) {
        lastErr = new Error(`Yahoo HTTP ${resp.getResponseCode()} (${YAHOO_HOSTS[i]})`);
      } else {
        const json = JSON.parse(resp.getContentText());
        const result = json && json.chart && json.chart.result && json.chart.result[0];
        if (result) return { result };
        const err = json && json.chart && json.chart.error;
        lastErr = new Error('Yahoo: ' + (err ? err.description : 'pusta odpowiedź'));
      }
    } catch (e) {
      lastErr = e;
    }
    if (i < YAHOO_HOSTS.length - 1) Utilities.sleep(1500);
  }
  throw lastErr;
}

/** Odpowiedź Yahoo → lista świec przypisanych do slotów sesji (0…6). */
function parseBars_(result) {
  const ts = result.timestamp || [];
  const q = (result.indicators && result.indicators.quote && result.indicators.quote[0]) || {};
  const o = q.open || [], h = q.high || [], l = q.low || [], c = q.close || [], v = q.volume || [];
  const out = [];
  for (let i = 0; i < ts.length; i++) {
    const vals = [o[i], h[i], l[i], c[i]];
    if (vals.some(x => typeof x !== 'number' || !isFinite(x))) continue;
    const d = new Date(ts[i] * 1000);
    const etMin = minutesOf_(d, CONFIG.MARKET_TZ);
    const slot = Math.floor((etMin - OPEN) / 60);
    if (slot < 0 || slot >= SLOTS) continue;
    let offset = minutesOf_(d, CONFIG.LOCAL_TZ) - etMin;
    if (offset < 0) offset += 1440;
    const slotStart = OPEN + slot * 60;
    out.push({
      date: Utilities.formatDate(d, CONFIG.MARKET_TZ, 'yyyy-MM-dd'),
      slot,
      open: round_(vals[0]), high: round_(vals[1]), low: round_(vals[2]), close: round_(vals[3]),
      // 0 = Yahoo nie podał wolumenu (nie „brak obrotu”)
      volume: (typeof v[i] === 'number' && isFinite(v[i])) ? Math.round(v[i]) : 0,
      startET: fmtMin_(slotStart),
      startPL: fmtMin_(slotStart + offset),
      openPL: fmtMin_(OPEN + offset),
      time: new Date(d.getTime() - ((etMin - slotStart) * 60 + d.getUTCSeconds()) * 1000),
    });
  }
  return out;
}


// ============================================================================
//  FIRESTORE (REST API, autoryzacja kontem Google, na którym działa skrypt)
//  Format bazy opisuje IA4_INSTRUKCJA.md, sekcja 4 — nie zmieniaj go bez
//  zmiany instrukcji.
// ============================================================================
function fsBase_() {
  return `projects/${CONFIG.FIREBASE_PROJECT_ID}/databases/${CONFIG.FIRESTORE_DATABASE}/documents`;
}

/** Spółka główna: dokument na świecę + podsumowanie stocks/{SYMBOL}. */
function fsWriteMainCandles_(symbol, bars) {
  const base = fsBase_();
  const nowIso = new Date().toISOString();
  const writes = bars.map(b => ({
    update: { name: `${base}/stocks/${symbol}/candles/${b.date}_${b.slot + 1}`, fields: candleFields_(b, nowIso) },
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
 * Pozostałe instrumenty: przepisuje cały dokument sesji dla każdego dnia
 * z nową świecą — sesja to jedna tablica, więc trafiają do niej wszystkie
 * zamknięte świece tego dnia, nie tylko nowe.
 */
function fsWriteSessions_(symbol, doneBars, freshBars) {
  const base = fsBase_();
  const nowIso = new Date().toISOString();
  const dates = {};
  freshBars.forEach(b => { dates[b.date] = 1; });
  const byDate = {};
  doneBars.forEach(b => {
    if (dates[b.date]) (byDate[b.date] = byDate[b.date] || {})[b.slot] = b;
  });
  const list = Object.keys(byDate).sort();
  const writes = list.map(date => ({
    update: { name: `${base}/${fsCollection_(symbol)}/${symbol}/sessions/${date}`, fields: sessionFields_(symbol, date, byDate[date], nowIso) },
  }));
  writes.push({
    update: {
      name: `${base}/${fsCollection_(symbol)}/${symbol}`,
      fields: { lastDate: { stringValue: list[list.length - 1] }, liveUpdatedAt: { timestampValue: nowIso } },
    },
    updateMask: { fieldPaths: ['lastDate', 'liveUpdatedAt'] },
  });
  for (let i = 0; i < writes.length; i += 400) firestoreCommit_(writes.slice(i, i + 400));
}

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
    v: arr(bars.map(b => b.volume || 0), 'int'),
    startPL: { stringValue: bars[0].openPL },
    firstCandleTime: { timestampValue: bars[0].time.toISOString() },
    updatedAt: { timestampValue: nowIso },
  };
}

function candleFields_(b, nowIso) {
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
    volume: { integerValue: String(b.volume || 0) },
    candleTime: { timestampValue: b.time.toISOString() },
    source: { stringValue: 'live' },
    updatedAt: { timestampValue: nowIso },
  };
}

function statusFields_(count) {
  return {
    lastWrite: { timestampValue: new Date().toISOString() },
    lastWriteCount: { integerValue: String(count) },
    symbols: { integerValue: String(allSymbols_().length) },
    version: { stringValue: CONFIG.VERSION },
    source: { stringValue: 'google-apps-script' },
  };
}

/** system/universe — listy instrumentów; czyta je synchronizacja w Pythonie. */
function fsWriteUniverse_() {
  const strArr = (list) => ({ arrayValue: { values: list.map(s => ({ stringValue: s })) } });
  firestoreCommit_([{
    update: {
      name: `${fsBase_()}/system/universe`,
      fields: {
        live: strArr(CONFIG.SYMBOLS),
        proof: strArr(CONFIG.PROOF_SYMBOLS),
        context: strArr(CONFIG.CONTEXT_SYMBOLS),
        doubleProof: strArr(CONFIG.DOUBLE_PROOF_SYMBOLS),
        updatedAt: { timestampValue: new Date().toISOString() },
      },
    },
  }]);
}

function firestoreCommit_(writes) {
  firestorePost_(`${fsBase_()}:commit`, { writes });
}

function firestorePost_(path, body) {
  const resp = UrlFetchApp.fetch(`https://firestore.googleapis.com/v1/${path}`, {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    payload: JSON.stringify(body),
    muteHttpExceptions: true,
  });
  const code = resp.getResponseCode();
  if (code !== 200) {
    let msg = resp.getContentText();
    try { msg = JSON.parse(msg).error.message; } catch (e) { /* surowy tekst */ }
    throw new Error(`Firestore HTTP ${code}: ${String(msg).slice(0, 250)}`);
  }
  return JSON.parse(resp.getContentText() || '{}');
}


// ============================================================================
//  ARKUSZ STATS
// ============================================================================
function setupStatsSheet_(ss) {
  const sh = ss.getSheetByName(CONFIG.STATS_SHEET) || ss.insertSheet(CONFIG.STATS_SHEET);
  sh.clear();
  sh.clearConditionalFormatRules();
  const needRows = logFirstRow_() + CONFIG.LOG_MAX_ROWS;
  if (sh.getMaxRows() < needRows) sh.insertRowsAfter(sh.getMaxRows(), needRows - sh.getMaxRows());
  sh.getRange(1, 1, sh.getMaxRows(), Math.max(SYM_COLS, sh.getMaxColumns())).breakApart();
  sh.setTabColor('#1a73e8');

  sh.getRange(1, 1, 1, SYM_COLS).merge().setValue(`IA 4 — ZBIERANIE DANYCH (wersja ${CONFIG.VERSION})`)
    .setFontSize(14).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(STATS_FIRST, 1, STATUS_LABELS.length, 1).setValues(STATUS_LABELS.map(x => [x]))
    .setFontWeight('bold').setBackground('#f1f3f4');
  sh.getRange(STATS_FIRST, 2, STATUS_LABELS.length, 1).setNumberFormat('@');
  sh.getRange(STATS_FIRST + 1, 2).setNumberFormat('yyyy-mm-dd hh:mm:ss');
  sh.getRange(STATS_FIRST + 3, 2).setNumberFormat('yyyy-mm-dd hh:mm:ss');
  // Watchdog: działa także wtedy, gdy skrypt przestał się uruchamiać.
  const lr = STATS_FIRST + 1;
  sh.getRange(lr, 3).setFormula(`=IF(B${lr}="","",IF(NOW()-B${lr}>15/1440,"⚠ brak uruchomień >15 min — sprawdź trigger","✓ automat żyje"))`);

  const symbols = allSymbols_();
  sh.getRange(SYM_HEADER, 1, 1, SYM_COLS)
    .setValues([['Instrument', 'Grupa', 'Ostatnia świeca', 'Godzina (PL)', 'Close', 'Świec w bazie', 'Status']])
    .setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(SYM_FIRST, 1, symbols.length, SYM_COLS).setNumberFormat('@');
  sh.getRange(SYM_FIRST, 5, symbols.length, 1).setNumberFormat('#,##0.00');
  sh.getRange(SYM_FIRST, 6, symbols.length, 1).setNumberFormat('#,##0');

  const lt = logFirstRow_() - 2;
  sh.getRange(lt, 1, 1, SYM_COLS).merge().setValue('DZIENNIK (najnowsze na górze)')
    .setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(lt + 1, 1, 1, 4).setValues([['Czas (PL)', 'Poziom', 'Źródło', 'Wiadomość']])
    .setFontWeight('bold').setBackground('#f1f3f4');
  sh.getRange(logFirstRow_(), 1, CONFIG.LOG_MAX_ROWS, 1).setNumberFormat('yyyy-mm-dd hh:mm:ss');

  sh.setColumnWidth(1, 200);
  sh.setColumnWidth(2, 260);
  sh.setColumnWidths(3, 5, 120);
  sh.setFrozenRows(1);

  const rule = () => SpreadsheetApp.newConditionalFormatRule();
  const status = sh.getRange(STATS_FIRST, 2);
  const symStatus = sh.getRange(SYM_FIRST, SYM_COLS, symbols.length, 1);
  sh.setConditionalFormatRules([
    rule().whenTextEqualTo('OK').setBackground('#ceead6').setFontColor('#0d652d').setRanges([status]).build(),
    rule().whenTextEqualTo('BŁĄD').setBackground('#fad2cf').setFontColor('#a50e0e').setRanges([status]).build(),
    rule().whenTextStartsWith('⚠').setBackground('#fad2cf').setFontColor('#a50e0e').setRanges([sh.getRange(lr, 3)]).build(),
    rule().whenTextStartsWith('✗').setFontColor('#a50e0e').setRanges([symStatus]).build(),
  ]);
  ss.setActiveSheet(sh);
  ss.moveActiveSheet(1);
}

function finishRun_(ctx, action) {
  const p = RUN_.props;
  p.setProperty('COUNTERS', JSON.stringify(RUN_.counters));
  p.setProperty('ERR_SEEN', JSON.stringify(RUN_.errSeen));
  p.setProperty('LAST_RUN', JSON.stringify({ at: ctx.now.toISOString(), action: action || '—', ok: !RUN_.errors.length }));

  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.STATS_SHEET);
  if (!sh || sh.getRange(SYM_HEADER, 1).getValue() !== 'Instrument') return;  // czeka na „Konfiguruj”

  const lastWrite = p.getProperty('LAST_WRITE');
  const lastErr = JSON.parse(p.getProperty('LAST_ERROR') || 'null');
  const nightly = JSON.parse(p.getProperty('NIGHTLY_INFO') || 'null');
  const counts = JSON.parse(p.getProperty('BASE_COUNTS') || 'null');
  const fmt = iso => Utilities.formatDate(new Date(iso), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm');
  const nTrig = ScriptApp.getProjectTriggers().filter(t => t.getHandlerFunction() === 'runCollector').length;

  sh.getRange(STATS_FIRST, 2, STATUS_LABELS.length, 1).setValues([
    [RUN_.errors.length ? 'BŁĄD' : 'OK'],
    [ctx.now],
    [action || '—'],
    [lastWrite ? new Date(lastWrite) : ''],
    [`${ctx.etDate} ${fmtMin_(ctx.etMin)} (${DAY_NAMES_PL[ctx.dow - 1]})`],
    [sessionLabel_(ctx)],
    [nTrig ? `AKTYWNY (co ${CONFIG.TRIGGER_EVERY_MIN} min)` : 'BRAK — uruchom IA 4 → Konfiguruj'],
    [RUN_.counters.candles],
    [RUN_.counters.errors],
    [lastErr ? `${fmt(lastErr.at)} — ${lastErr.text}` : 'brak'],
    [nightly ? `${nightly.date} (${fmt(nightly.at)}), ${nightly.written} świec` : 'jeszcze nie było'],
    [counts ? `${counts.total.toLocaleString('pl-PL')} (policzone ${fmt(counts.at)})` : 'po pierwszym nocnym odświeżeniu'],
    [backfillLabel_()],
  ]);

  const live = RUN_.live || liveLoad_();
  const rows = allSymbols_().map(s => {
    const st = live[s] || {};
    const n = counts && counts.items[s] ? counts.items[s].candles : '';
    return [s, GROUP_LABELS[symbolGroup_(s)], st.d || '—', st.d ? CONFIG.SLOT_LABELS_PL[st.s] : '—',
            st.c !== undefined ? st.c : '', n, st.st || '—'];
  });
  sh.getRange(SYM_FIRST, 1, rows.length, SYM_COLS).setValues(rows);

  if (RUN_.logs.length) {
    const range = sh.getRange(logFirstRow_(), 1, CONFIG.LOG_MAX_ROWS, 4);
    const existing = range.getValues().filter(r => r.some(x => x !== ''));
    const out = RUN_.logs.slice().reverse().concat(existing).slice(0, CONFIG.LOG_MAX_ROWS);
    while (out.length < CONFIG.LOG_MAX_ROWS) out.push(['', '', '', '']);
    range.setValues(out);
  }
}

function sessionLabel_(ctx) {
  const session = getSession_();
  if (!ctx.weekday) return 'ZAMKNIĘTA — weekend';
  if (isHolidayToday_(ctx, session)) return 'ZAMKNIĘTA — święto w USA';
  const closeMin = sessionCloseFor_(session, ctx.etDate);
  const hours = `${fmtMin_(OPEN + ctx.offset)}–${fmtMin_(closeMin + ctx.offset)} PL` + (closeMin < CLOSE ? ', skrócona' : '');
  if (ctx.etMin < OPEN) return `PRZED OTWARCIEM (${hours})`;
  if (ctx.etMin < closeMin) return `OTWARTA (${hours})`;
  return 'ZAMKNIĘTA — po sesji';
}


// ============================================================================
//  STAN URUCHOMIENIA I DZIENNIK
// ============================================================================
function startRun_() {
  const props = PropertiesService.getScriptProperties();
  const today = Utilities.formatDate(new Date(), CONFIG.LOCAL_TZ, 'yyyy-MM-dd');
  const c = JSON.parse(props.getProperty('COUNTERS') || '{}');
  RUN_ = {
    props,
    counters: c.date === today && c.candles !== undefined ? c : { date: today, candles: 0, errors: 0 },
    logs: [], errors: [], live: null,
    errSeen: JSON.parse(props.getProperty('ERR_SEEN') || '{}'),
  };
}

function log_(level, source, message) {
  if (!RUN_) startRun_();
  RUN_.logs.push([new Date(), level, source, message]);
  console.log(`[${level}] ${source}: ${message}`);
}

/** Błąd trafia do dziennika raz — powtórka tego samego komunikatu go nie zaśmieca. */
function recordError_(source, message) {
  RUN_.errors.push(`${source}: ${message}`);
  RUN_.counters.errors++;
  RUN_.props.setProperty('LAST_ERROR', JSON.stringify({ at: new Date().toISOString(), text: `${source}: ${message}` }));
  if (RUN_.errSeen[source] !== message) {
    log_('BŁĄD', source, message);
    RUN_.errSeen[source] = message;
  }
}
function clearError_(source) { delete RUN_.errSeen[source]; }


// ============================================================================
//  TRIGGERY
// ============================================================================
function installTriggers_() {
  removeTriggers_(['runCollector', 'telemetryHourly', 'researchSync']);
  ScriptApp.newTrigger('runCollector').timeBased().everyMinutes(CONFIG.TRIGGER_EVERY_MIN).create();
  ScriptApp.newTrigger('telemetryHourly').timeBased().everyHours(1).create();
  ScriptApp.newTrigger('researchSync').timeBased().everyMinutes(30).create();
}

function removeTriggers_(handlers) {
  let n = 0;
  ScriptApp.getProjectTriggers().forEach(t => {
    if (handlers.indexOf(t.getHandlerFunction()) >= 0) { ScriptApp.deleteTrigger(t); n++; }
  });
  return n;
}


// ============================================================================
//  HISTORIA doubleProof — pobieranie wstecz do granicy Yahoo (~730 dni)
//  Raz na BACKFILL_EVERY_MIN minut (w wolnym przebiegu runCollector) jedna
//  porcja: dla każdej spółki, która nie ma jeszcze pełnej historii, kolejne
//  60 dni wstecz. Okna zaczynają się i kończą o północy UTC, więc sesja nigdy
//  nie jest dzielona między porcje. Dzisiejsze i ostatnie sesje zapisuje
//  zbieranie na żywo i nocne odświeżenie — historia zaczyna się od wczoraj.
//  Stan: Script Properties → BACKFILL_DP.
// ============================================================================
function backfillState_() {
  return JSON.parse(PropertiesService.getScriptProperties().getProperty('BACKFILL_DP') || '{}');
}

function backfillLabel_() {
  const st = backfillState_();
  const syms = CONFIG.DOUBLE_PROOF_SYMBOLS;
  const done = syms.filter(s => st[s] && st[s].done).length;
  const oldest = syms.map(s => st[s] && st[s].end).filter(x => x).sort()[0] || '';
  if (done === syms.length) return `kompletna — ${syms.length} spółek od ${oldest}`;
  return `w toku: gotowe ${done}/${syms.length}` + (oldest ? `, najstarsza pobrana sesja ${oldest}` : ', jeszcze nie zaczęte');
}

function backfillIfDue_(ctx) {
  const props = PropertiesService.getScriptProperties();
  const st = backfillState_();
  if (CONFIG.DOUBLE_PROOF_SYMBOLS.every(s => st[s] && st[s].done)) return '';
  const lastTry = Number(props.getProperty('BACKFILL_TRY_AT') || 0);
  if (Date.now() - lastTry < CONFIG.BACKFILL_EVERY_MIN * 60000) return '';
  return runBackfill_(ctx);
}

function backfillNow() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Automat właśnie pracuje — spróbuj za minutę.'); return; }
  try {
    startRun_();
    const ctx = marketContext_(new Date());
    const r = runBackfill_(ctx);
    finishRun_(ctx, r || 'Historia doubleProof już kompletna');
    toast_(r || 'Historia doubleProof już kompletna.');
  } finally { lock.releaseLock(); }
}

function runBackfill_(ctx) {
  const props = PropertiesService.getScriptProperties();
  props.setProperty('BACKFILL_TRY_AT', String(Date.now()));
  const st = backfillState_();
  const today = Utilities.formatDate(new Date(), CONFIG.LOCAL_TZ, 'yyyy-MM-dd');
  const budget = JSON.parse(props.getProperty('BACKFILL_WRITES') || '{}');
  if (budget.date !== today) { budget.date = today; budget.n = 0; }
  const DAY = 86400000;
  const todayUtc = Math.floor(Date.now() / DAY) * DAY;              // dziś 00:00 UTC
  const limitUtc = todayUtc - CONFIG.BACKFILL_LIMIT_DAYS * DAY;
  let written = 0, symbolsDone = 0, errors = 0, n = 0;

  CONFIG.DOUBLE_PROOF_SYMBOLS.forEach(symbol => {
    const s = st[symbol] || (st[symbol] = {});
    if (s.done) return;
    if (budget.n + written > CONFIG.BACKFILL_DAY_WRITES) return;
    const end = s.endUtc || todayUtc;
    const start = Math.max(end - CONFIG.BACKFILL_WINDOW_DAYS * DAY, limitUtc);
    if (start >= end) { s.done = true; symbolsDone++; return; }
    try {
      if (n++) Utilities.sleep(CONFIG.FETCH_PAUSE_MS);
      const r = fetchYahooPeriod_(symbol, start / 1000, end / 1000);
      const bars = r ? parseBars_(r.result).filter(b =>
        isoWeekday_(b.date) <= 5 && !US_MARKET_HOLIDAYS[b.date] && b.date < ctx.etDate) : [];
      bars.forEach(b => { b.symbol = symbol; });
      if (bars.length) written += fsWriteHistory_(symbol, bars, start <= limitUtc);
      s.endUtc = start;
      if (bars.length) s.end = bars.map(b => b.date).sort()[0];
      if (!r || start <= limitUtc) { s.done = true; symbolsDone++; }
    } catch (e) {
      errors++;
      recordError_(symbol, 'historia doubleProof: ' + (e.message || e));
    }
  });

  budget.n += written;
  props.setProperty('BACKFILL_WRITES', JSON.stringify(budget));
  props.setProperty('BACKFILL_DP', JSON.stringify(st));
  const msg = `historia doubleProof: zapisano ${written} sesji` + (errors ? `, błędów ${errors}` : '') + ` · ${backfillLabel_()}`;
  log_('INFO', 'HISTORIA', msg);
  return msg;
}

/** Yahoo 1h dla okresu [p1, p2) w sekundach. null = okres poza granicą Yahoo (koniec historii). */
function fetchYahooPeriod_(symbol, p1, p2) {
  let lastErr = null;
  for (let i = 0; i < YAHOO_HOSTS.length; i++) {
    const url = `https://${YAHOO_HOSTS[i]}/v8/finance/chart/${encodeURIComponent(symbol)}` +
                `?interval=1h&period1=${Math.floor(p1)}&period2=${Math.floor(p2)}&includePrePost=false`;
    try {
      const resp = UrlFetchApp.fetch(url, { muteHttpExceptions: true, headers: YAHOO_HEADERS });
      const txt = resp.getContentText();
      let json = null;
      try { json = JSON.parse(txt); } catch (e) { /* nie-JSON */ }
      const err = json && json.chart && json.chart.error;
      if (err && /730|range must be|not available for startTime/i.test(err.description || '')) return null;
      if (resp.getResponseCode() === 200 && json && json.chart && json.chart.result && json.chart.result[0]) {
        return { result: json.chart.result[0] };
      }
      lastErr = new Error(`Yahoo HTTP ${resp.getResponseCode()}` + (err ? ': ' + err.description : ''));
    } catch (e) { lastErr = e; }
    if (i < YAHOO_HOSTS.length - 1) Utilities.sleep(1500);
  }
  throw lastErr;
}

/** Zapis sesji z historii: dokumenty sesji + pola historii w podsumowaniu (lastDate bez zmian). */
function fsWriteHistory_(symbol, bars, reachedLimit) {
  const base = fsBase_();
  const nowIso = new Date().toISOString();
  const byDate = {};
  bars.forEach(b => { (byDate[b.date] = byDate[b.date] || {})[b.slot] = b; });
  const dates = Object.keys(byDate).sort();
  const writes = dates.map(date => ({
    update: { name: `${base}/${fsCollection_(symbol)}/${symbol}/sessions/${date}`, fields: sessionFields_(symbol, date, byDate[date], nowIso) },
  }));
  writes.push({
    update: {
      name: `${base}/${fsCollection_(symbol)}/${symbol}`,
      fields: { historyFirstDate: { stringValue: dates[0] }, historyUpdatedAt: { timestampValue: nowIso },
                historyDone: { booleanValue: !!reachedLimit } },
    },
    updateMask: { fieldPaths: ['historyFirstDate', 'historyUpdatedAt', 'historyDone'] },
  });
  for (let i = 0; i < writes.length; i += 400) firestoreCommit_(writes.slice(i, i + 400));
  return dates.length;
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
  const d = new Date(Date.UTC(p[0], p[1] - 1, p[2])).getUTCDay();
  return d === 0 ? 7 : d;
}

function round_(v) { return Math.round(v * 10000) / 10000; }

function toast_(msg) {
  try { SpreadsheetApp.getActiveSpreadsheet().toast(msg, 'IA 4', 8); } catch (e) { console.log(msg); }
}

function alert_(msg) {
  try { SpreadsheetApp.getUi().alert(msg); } catch (e) { console.log(msg); }
}
