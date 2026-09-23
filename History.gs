/**
 * ============================================================================
 *  IA 4 — HISTORIA WSTECZ  (Yahoo Finance → Firestore)
 *
 *  Wersja projektu: 0.8 (2026-09-23) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Co kilka minut pobiera świece 1h z kolejnych dni sesji dla AAPL, TSLA i NVDA
 *  i zapisuje je w Firestore. Każde kolejne uruchomienie cofa się o jeden
 *  dzień sesyjny:  2026-09-02 → 2026-09-01 → 2026-08-31 → 2026-08-28 → …
 *
 *  • Weekendy i święta giełdowe w USA są pomijane od razu (nie „zjadają” godziny).
 *  • Dane trafiają do tych samych dokumentów co automat bieżący:
 *        stocks/{SYMBOL}/candles/{data}_{nr}      (pole source = "history")
 *  • Postęp widać w Firestore (system/history) i w bloku „HISTORIA” w STATS.
 *  • Jeśli Yahoo odda niepełne dane, dzień jest ponawiany w kolejnych godzinach
 *    (maks. MAX_RETRIES razy). Dopiero potem zostaje zapisany „jak jest” i oznaczony.
 *  • Yahoo udostępnia świece 1h tylko z ostatnich ~730 dni. Po dojściu do tej
 *    granicy funkcja sama się kończy i usuwa swój trigger.
 *
 *  Plik korzysta z funkcji z Code.gs (parseBars_, firestoreCommit_, log_ itd.),
 *  więc oba pliki muszą być w tym samym projekcie Apps Script.
 *
 *  START: menu IA 4 → Historia wstecz → Start  (albo funkcja startHistory w edytorze).
 * ============================================================================
 */

const HISTORY = {
  START_DATE: '2026-09-02',  // pierwszy dzień do pobrania (potem w tył)
  EVERY_MINUTES: 10,         // co ile minut kolejna porcja (dozwolone: 1, 5, 10, 15, 30)
  DAYS_PER_RUN: 2,           // ile dni sesyjnych na jedno uruchomienie
  MAX_RETRIES: 3,            // ile razy ponawiać dzień z niepełnymi danymi, zanim go przepuścimy
  YAHOO_MAX_AGE_DAYS: 729,   // granica Yahoo dla interwału 1h (~730 dni wstecz)
  STATS_COL: 10,             // blok w STATS zaczyna się w kolumnie J
  STATS_ROW: 3,
};

// Dni bez sesji na NYSE/NASDAQ (poza weekendami) w zakresie dostępnym w Yahoo dla świec 1h.
const US_MARKET_HOLIDAYS = {
  '2024-01-01': 'Nowy Rok', '2024-01-15': 'Dzień M. L. Kinga', '2024-02-19': 'Dzień Prezydentów',
  '2024-03-29': 'Wielki Piątek', '2024-05-27': 'Memorial Day', '2024-06-19': 'Juneteenth',
  '2024-07-04': 'Dzień Niepodległości', '2024-09-02': 'Labor Day', '2024-11-28': 'Święto Dziękczynienia',
  '2024-12-25': 'Boże Narodzenie',

  '2025-01-01': 'Nowy Rok', '2025-01-09': 'Żałoba narodowa (J. Carter)', '2025-01-20': 'Dzień M. L. Kinga',
  '2025-02-17': 'Dzień Prezydentów', '2025-04-18': 'Wielki Piątek', '2025-05-26': 'Memorial Day',
  '2025-06-19': 'Juneteenth', '2025-07-04': 'Dzień Niepodległości', '2025-09-01': 'Labor Day',
  '2025-11-27': 'Święto Dziękczynienia', '2025-12-25': 'Boże Narodzenie',

  '2026-01-01': 'Nowy Rok', '2026-01-19': 'Dzień M. L. Kinga', '2026-02-16': 'Dzień Prezydentów',
  '2026-04-03': 'Wielki Piątek', '2026-05-25': 'Memorial Day', '2026-06-19': 'Juneteenth',
  '2026-07-03': 'Dzień Niepodległości (obchodzony)', '2026-09-07': 'Labor Day',
  '2026-11-26': 'Święto Dziękczynienia', '2026-12-25': 'Boże Narodzenie',
};

const HIST_LABELS = [
  'Status', 'Następny dzień do pobrania', 'Ostatnio zapisany dzień', 'Zapisanych dni',
  'Zapisanych świec', 'Pominiętych świąt', 'Dni z brakami', 'Ostatnie uruchomienie (PL)',
  'Granica Yahoo (1h)', 'Szacowany koniec', 'Ostatni błąd / info',
];


// ============================================================================
//  FUNKCJE PUBLICZNE
// ============================================================================
function startHistory() {
  if (!CONFIG.FIRESTORE_ENABLED) {
    alert_('Historia zapisuje dane tylko do Firestore — włącz FIRESTORE_ENABLED w CONFIG (Code.gs).');
    return;
  }
  const st = histLoad_();
  if (st && st.done) {
    alert_('Historia jest już zakończona (' + st.doneReason + ').\n' +
           'Jeśli chcesz zacząć od nowa, użyj „Reset do daty startowej”.');
    return;
  }
  if (!st) histSave_(histInit_());
  histSetupStats_();
  removeHistoryTrigger_();
  ScriptApp.newTrigger('runHistory').timeBased().everyMinutes(HISTORY.EVERY_MINUTES).create();

  const tempo = `co ${HISTORY.EVERY_MINUTES} min po ${HISTORY.DAYS_PER_RUN} dni sesji`;
  histExecute_(st ? `Historia wznowiona od ${st.cursor} (${tempo}).` : `Historia uruchomiona od ${HISTORY.START_DATE} (${tempo}, wstecz).`);
  toast_(`Historia wstecz działa — ${tempo} trafia do Firestore.`);
}

/** Handler triggera — NIE zmieniaj nazwy. */
function runHistory() { histExecute_(); }

function historyStepNow() {
  histExecute_('Ręczne pobranie kolejnego dnia historii.');
  toast_('Gotowe — szczegóły w arkuszu STATS (blok HISTORIA).');
}

function stopHistory() {
  const n = removeHistoryTrigger_();
  startRun_();
  log_('INFO', 'HISTORIA', `Historia zatrzymana (usunięto triggerów: ${n}). Postęp jest zapamiętany.`);
  histRefreshStats_();
  toast_('Historia zatrzymana. „Start / wznów” kontynuuje od miejsca, w którym skończyła.');
}

function resetHistory() {
  try {
    const ui = SpreadsheetApp.getUi();
    const answer = ui.alert('Reset historii',
      `Postęp zostanie wyzerowany, a historia zacznie się od ${HISTORY.START_DATE}.\n` +
      'Dane zapisane już w Firestore zostają. Kontynuować?', ui.ButtonSet.YES_NO);
    if (answer !== ui.Button.YES) return;
  } catch (e) { /* uruchomione z edytora — bez okienka */ }

  histSave_(histInit_());
  startRun_();
  log_('INFO', 'HISTORIA', `Reset historii — start od ${HISTORY.START_DATE}.`);
  histRefreshStats_();
  toast_(`Historia wyzerowana. Kliknij „Start / wznów”, aby ruszyła od ${HISTORY.START_DATE}.`);
}


// ============================================================================
//  SILNIK
// ============================================================================
function histExecute_(initMessage) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(60 * 1000)) {
    console.warn('Inne uruchomienie wciąż trwa — historia poczeka do następnego razu.');
    return;
  }
  startRun_();
  const st = histLoad_() || histInit_();
  try {
    if (initMessage) log_('INFO', 'HISTORIA', initMessage);
    if (!CONFIG.FIRESTORE_ENABLED) throw new Error('Firestore jest wyłączony w CONFIG');
    if (st.done) {
      removeHistoryTrigger_();
      return;
    }
    st.lastRunAt = new Date().toISOString();

    let processed = 0;
    while (processed < HISTORY.DAYS_PER_RUN && !st.done) {
      st.cursor = histNormalize_(st, st.cursor);
      if (st.cursor < histLimitDate_()) {
        histFinish_(st, 'dojście do granicy Yahoo (świece 1h są dostępne tylko z ostatnich ~730 dni)');
        break;
      }
      if (!histProcessDay_(st)) break; // błąd — ten sam dzień spróbujemy za godzinę
      processed++;
    }
  } catch (e) {
    histError_(st, e.message || String(e));
  } finally {
    histSave_(st);
    try { histRefreshStats_(st); } catch (e2) { console.error('STATS: ' + e2); }
    lock.releaseLock();
  }
}

/**
 * Pobiera i zapisuje jeden dzień (st.cursor).
 * Zwraca true, gdy dzień jest „załatwiony” (kursor cofnięty), false — gdy trzeba ponowić później.
 */
function histProcessDay_(st) {
  const date = st.cursor;
  const results = {};
  const problems = [];
  let limitMsg = null;

  CONFIG.SYMBOLS.forEach((symbol, i) => {
    if (limitMsg) return;
    if (i) Utilities.sleep(700); // delikatnie dla Yahoo
    const r = histFetchDay_(symbol, date);
    if (r.kind === 'ok') results[symbol] = r.bars;
    else if (r.kind === 'limit') limitMsg = r.msg;
    else problems.push(`${symbol}: ${r.kind === 'empty' ? 'brak danych' : r.msg}`);
  });

  if (limitMsg) {
    histFinish_(st, 'Yahoo: ' + limitMsg);
    return false;
  }

  const complete = problems.length === 0;
  if (!complete && st.retries + 1 < HISTORY.MAX_RETRIES) {
    st.retries++;
    histError_(st, `${date}: ${problems.join('; ')} — ponowię przy kolejnym uruchomieniu (próba ${st.retries}/${HISTORY.MAX_RETRIES})`);
    return false;
  }

  const symbols = Object.keys(results);
  if (symbols.length) {
    try {
      st.candlesSaved += histSaveDay_(results);
    } catch (e) {
      // Błąd zapisu nie przesuwa kursora i nie liczy się do prób — dane nie mogą przepaść.
      histError_(st, `${date}: ${e.message} — ponowię przy kolejnym uruchomieniu`);
      return false;
    }
    st.daysSaved++;
    st.lastDate = date;
  }

  const counts = symbols.map(s => `${s} ${results[s].length}`).join(', ');
  if (complete) {
    log_('ZAPIS', 'HISTORIA', `${date}: ${counts} świec`);
  } else {
    st.skipped.push(date);
    if (st.skipped.length > 50) st.skipped.shift();
    log_('UWAGA', 'HISTORIA', `${date}: zapisano niepełne dane${counts ? ' (' + counts + ')' : ''} — ${problems.join('; ')}`);
  }

  st.retries = 0;
  st.lastError = null;
  st.lastErrorMsg = '';
  st.cursor = addDays_(date, -1);
  histStatusToFirestore_(st);
  return true;
}

/** Świece 1h z jednego dnia sesji: { kind: 'ok' | 'empty' | 'limit' | 'error', bars?, msg? } */
function histFetchDay_(symbol, date) {
  const p = date.split('-').map(Number);
  const period1 = Date.UTC(p[0], p[1] - 1, p[2], 0, 0) / 1000;      // 00:00 UTC danego dnia
  const period2 = Date.UTC(p[0], p[1] - 1, p[2] + 1, 6, 0) / 1000;  // 06:00 UTC dnia następnego
  let lastMsg = 'nieznany błąd';

  for (let i = 0; i < YAHOO_HOSTS.length; i++) {
    const url = `https://${YAHOO_HOSTS[i]}/v8/finance/chart/${encodeURIComponent(symbol)}` +
                `?interval=1h&period1=${period1}&period2=${period2}&includePrePost=false`;
    try {
      const resp = UrlFetchApp.fetch(url, { muteHttpExceptions: true, headers: YAHOO_HEADERS });
      const code = resp.getResponseCode();
      let json = null;
      try { json = JSON.parse(resp.getContentText()); } catch (e) { /* nie-JSON */ }
      const err = json && json.chart && json.chart.error;
      const desc = err ? String(err.description || err.code || '') : '';

      if (/730|within the last/i.test(desc)) return { kind: 'limit', msg: desc };
      const result = json && json.chart && json.chart.result && json.chart.result[0];
      if (code === 200 && result) {
        const bars = parseBars_(result).filter(b => b.date === date);
        return bars.length ? { kind: 'ok', bars } : { kind: 'empty' };
      }
      if (/no data found/i.test(desc)) return { kind: 'empty' };
      lastMsg = `HTTP ${code}${desc ? ' — ' + desc : ''} (${YAHOO_HOSTS[i]})`;
    } catch (e) {
      lastMsg = e.message || String(e);
    }
    if (i < YAHOO_HOSTS.length - 1) Utilities.sleep(1500);
  }
  return { kind: 'error', msg: lastMsg };
}

function histSaveDay_(results) {
  const nowIso = new Date().toISOString();
  const writes = [];
  Object.keys(results).forEach(symbol => {
    results[symbol].forEach(b => {
      b.symbol = symbol;
      writes.push({
        update: {
          name: `${fsBase_()}/stocks/${symbol}/candles/${b.date}_${b.slot + 1}`,
          fields: candleFields_(b, nowIso, 'history'),
        },
      });
    });
  });
  for (let i = 0; i < writes.length; i += 400) firestoreCommit_(writes.slice(i, i + 400));
  return writes.length;
}

function histStatusToFirestore_(st) {
  try {
    firestoreCommit_([{
      update: {
        name: `${fsBase_()}/system/history`,
        fields: {
          startDate: { stringValue: st.startDate },
          nextDate: { stringValue: st.done ? '' : st.cursor },
          lastDate: { stringValue: st.lastDate || '' },
          daysSaved: { integerValue: String(st.daysSaved) },
          candlesSaved: { integerValue: String(st.candlesSaved) },
          done: { booleanValue: !!st.done },
          updatedAt: { timestampValue: new Date().toISOString() },
        },
      },
    }]);
  } catch (e) {
    console.warn('system/history: ' + e.message);
  }
}

/** Cofa datę do najbliższego dnia sesji (pomija weekendy i święta). */
function histNormalize_(st, date) {
  let d = date;
  for (let guard = 0; guard < 30; guard++) {
    const wd = isoWeekday_(d);
    const holiday = US_MARKET_HOLIDAYS[d];
    if (wd <= 5 && !holiday) return d;
    if (wd <= 5 && holiday) {
      st.holidaysSkipped++;
      log_('INFO', 'HISTORIA', `${d} — brak sesji (${holiday}), pomijam.`);
    }
    d = addDays_(d, -1);
  }
  return d;
}

function histFinish_(st, reason) {
  reason = String(reason).replace(/\.+$/, '');
  st.done = true;
  st.doneReason = reason;
  removeHistoryTrigger_();
  log_('INFO', 'HISTORIA', `✓ Historia zakończona: ${reason}. Zapisano ${st.daysSaved} dni / ${st.candlesSaved} świec.`);
  histStatusToFirestore_(st);
}

function histError_(st, msg) {
  st.lastError = { at: new Date().toISOString(), msg };
  if (st.lastErrorMsg !== msg) log_('UWAGA', 'HISTORIA', msg);
  st.lastErrorMsg = msg;
  console.error('HISTORIA: ' + msg);
}


// ============================================================================
//  STAN
// ============================================================================
function histInit_() {
  return {
    startDate: HISTORY.START_DATE, cursor: HISTORY.START_DATE, lastDate: '',
    daysSaved: 0, candlesSaved: 0, holidaysSkipped: 0, skipped: [], retries: 0,
    done: false, doneReason: '', lastRunAt: '', lastError: null, lastErrorMsg: '',
  };
}

function histLoad_() {
  const raw = PropertiesService.getScriptProperties().getProperty('HISTORY_STATE');
  return raw ? JSON.parse(raw) : null;
}

function histSave_(st) {
  PropertiesService.getScriptProperties().setProperty('HISTORY_STATE', JSON.stringify(st));
}

function histLimitDate_() {
  const today = Utilities.formatDate(new Date(), CONFIG.MARKET_TZ, 'yyyy-MM-dd');
  return addDays_(today, -HISTORY.YAHOO_MAX_AGE_DAYS);
}

function removeHistoryTrigger_() {
  let n = 0;
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'runHistory') { ScriptApp.deleteTrigger(t); n++; }
  });
  return n;
}

function histTriggerExists_() {
  try {
    return ScriptApp.getProjectTriggers().some(t => t.getHandlerFunction() === 'runHistory');
  } catch (e) {
    return false;
  }
}


// ============================================================================
//  BLOK „HISTORIA” W ARKUSZU STATS (kolumny J:K)
// ============================================================================
function histSetupStats_() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.STATS_SHEET);
  if (!sh) return;
  const col = HISTORY.STATS_COL;
  const row = HISTORY.STATS_ROW;
  if (sh.getMaxColumns() < col + 1) sh.insertColumnsAfter(sh.getMaxColumns(), col + 1 - sh.getMaxColumns());

  sh.getRange(row, col, 1, 2).breakApart().merge()
    .setValue('HISTORIA WSTECZ → Firestore')
    .setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(row + 1, col, HIST_LABELS.length, 1)
    .setValues(HIST_LABELS.map(x => [x]))
    .setFontWeight('bold').setBackground('#f1f3f4');
  sh.getRange(row + 1, col + 1, HIST_LABELS.length, 1).setNumberFormat('@').setHorizontalAlignment('left');
  sh.setColumnWidth(col, 210);
  sh.setColumnWidth(col + 1, 330);
}

function histRefreshStats_(st) {
  st = st || histLoad_() || histInit_();
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.STATS_SHEET);
  if (!sh) return;
  const col = HISTORY.STATS_COL;
  const row = HISTORY.STATS_ROW;
  if (sh.getRange(row + 1, col).getValue() !== HIST_LABELS[0]) histSetupStats_();

  const fmt = iso => Utilities.formatDate(new Date(iso), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm');
  const limit = histLimitDate_();
  const active = histTriggerExists_();

  let status;
  if (st.done) status = '✓ ZAKOŃCZONA';
  else if (!active) status = '⏸ ZATRZYMANA';
  else if (st.retries) status = `⚠ AKTYWNA — ponawiam ${st.cursor}`;
  else status = `✓ AKTYWNA (co ${HISTORY.EVERY_MINUTES} min × ${HISTORY.DAYS_PER_RUN} dni)`;

  let eta = '—';
  if (!st.done) {
    const left = countTradingDays_(limit, st.cursor);
    const mins = Math.ceil(left / HISTORY.DAYS_PER_RUN) * HISTORY.EVERY_MINUTES;
    eta = `≈ ${fmt(new Date(Date.now() + mins * 60 * 1000).toISOString())} (zostało ~${left} dni sesji)`;
  }

  let info = 'brak';
  if (st.done) info = st.doneReason;
  else if (st.lastError) info = `${fmt(st.lastError.at)} — ${st.lastError.msg}`;

  sh.getRange(row + 1, col + 1, HIST_LABELS.length, 1).setValues([
    [status],
    [st.done ? '—' : st.cursor],
    [st.lastDate || '—'],
    [String(st.daysSaved)],
    [String(st.candlesSaved)],
    [String(st.holidaysSkipped)],
    [st.skipped.length ? st.skipped.slice(-5).join(', ') : 'brak'],
    [st.lastRunAt ? fmt(st.lastRunAt) : '—'],
    [limit],
    [eta],
    [info],
  ]);

  if (RUN_ && RUN_.logs.length) flushLog_(sh);
}


// ============================================================================
//  NARZĘDZIA KALENDARZOWE
// ============================================================================
function addDays_(ymd, n) {
  const p = ymd.split('-').map(Number);
  return new Date(Date.UTC(p[0], p[1] - 1, p[2] + n)).toISOString().slice(0, 10);
}

/** Liczba dni sesyjnych w przedziale [from, to] (włącznie). */
function countTradingDays_(from, to) {
  let n = 0;
  for (let d = to; d >= from; d = addDays_(d, -1)) {
    if (isoWeekday_(d) <= 5 && !US_MARKET_HOLIDAYS[d]) n++;
  }
  return n;
}