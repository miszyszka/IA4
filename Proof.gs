/**
 * ============================================================================
 *  IA 4 — SPÓŁKI KONTROLNE („for proof”)
 *
 *  Wersja projektu: 0.9 (2026-09-23) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Zbiera historię świec 1h dla 50 dodatkowych spółek i zapisuje je w Firestore.
 *  Te spółki NIE pojawiają się w dashboardzie ani w arkuszach — służą wyłącznie
 *  do sprawdzania, czy strategia znaleziona na AAPL, TSLA i NVDA działa też
 *  gdzie indziej, czy była tylko dopasowaniem do tych trzech wykresów.
 *
 *  URUCHOMIENIE:  menu IA 4 → Spółki kontrolne → Pobierz historię
 *                 (albo funkcja startProof w edytorze)
 *
 *  Ten plik pobiera HISTORIĘ (dwa lata wstecz). Nowe świece tych spółek
 *  zapisuje na bieżąco automat z Code.gs, w tym samym formacie — listy
 *  PROOF.SYMBOLS i CONTEXT.SYMBOLS poniżej sterują oboma.
 *
 *  TŁO RYNKU (CONTEXT): SPY i QQQ. Nie handlujemy nimi — służą jako kontekst
 *  w Etapie 3. Zapisywane w context/{SYMBOL}/sessions/{data}; format sesji
 *  identyczny jak u spółek kontrolnych. (VIX usunięty z projektu — decyzja D8.)
 *
 *  DLACZEGO INNY FORMAT NIŻ GŁÓWNE TRZY SPÓŁKI
 *  Główne spółki mają jeden dokument na świecę, bo dashboard nasłuchuje ich
 *  na żywo i musi dostawać pojedyncze świece. Spółki kontrolne są czytane
 *  hurtowo przy backteście, więc cała sesja (7 świec) siedzi w jednym
 *  dokumencie. To siedem razy mniej zapisów i odczytów — przy 24 spółkach
 *  różnica między 84 000 a 12 000 dokumentów, czyli między przekroczeniem
 *  darmowego limitu Firestore a zmieszczeniem się w nim.
 *
 *  STRUKTURA W FIRESTORE
 *    proof/{SYMBOL}                  – zakres i liczba zebranych sesji
 *    proof/{SYMBOL}/sessions/{data}  – jedna sesja: tablice slots, o, h, l, c
 *    system/universe                 – lista spółek w obu grupach
 *
 *  TEMPO: jedna spółka na uruchomienie, co 10 minut. Komplet 50 spółek zajmuje
 *  około 8 godzin. Wolno celowo — Yahoo blokuje zbyt częste zapytania,
 *  a jednocześnie działa zbieranie historii głównych trzech spółek.
 *
 *  Plik wymaga Code.gs (CONFIG, parseBars_, fsBase_, firestoreCommit_, log_)
 *  oraz History.gs (addDays_).
 * ============================================================================
 */

const PROOF = {
  SYMBOLS: [
    // pierwotna dwudziestka czwórka
    'DELL', 'AMAT', 'PLTR', 'ORCL', 'XOM', 'V', 'WMT', 'JPM', 'MU', 'META', 'AVGO', 'MSFT',
    'GOOGL', 'JNJ', 'MA', 'ABBV', 'BAC', 'CVX', 'MRK', 'PG', 'HD', 'PM', 'WFC', 'CRM',
    // dodane dla różnorodności sektorowej (poprzednia lista była mocno przechylona
    // w stronę technologii i finansów) — wyłącznie duże, płynne spółki
    'CAT', 'HON', 'UNP', 'RTX',           // przemysł
    'AMZN', 'MCD', 'NKE', 'SBUX',         // dobra cykliczne
    'T', 'VZ', 'NFLX', 'DIS',             // media i telekomunikacja
    'UNH', 'LLY', 'PFE', 'MDT',           // ochrona zdrowia
    'PLD', 'AMT',                         // nieruchomości (REIT)
    'LIN', 'FCX',                         // surowce
    'NEE', 'DUK',                         // użyteczność publiczna
    'GS', 'AXP',                          // bankowość inwestycyjna
    'KO', 'PEP',                          // dobra pierwszej potrzeby
  ],
  EVERY_MINUTES: 5,        // co ile minut kolejna spółka
  SYMBOLS_PER_RUN: 3,       // ile spółek na jedno uruchomienie
  CHUNK_DAYS: 120,          // na ile dni dzielimy jedno zapytanie do Yahoo
  YAHOO_MAX_AGE_DAYS: 729,  // granica Yahoo dla świec 1h
  REFRESH_DAYS: 40,         // ile dni wstecz odświeża „Uzupełnij najnowsze”
  MAX_RETRIES: 3,
  MIN_SESSIONS: 100,        // poniżej tylu sesji spółka trafia na listę „niepełne”
  STATS_COL: 13,            // blok w STATS zaczyna się w kolumnie M
  STATS_ROW: 3,
};

// Tło rynku (decyzja D3). Historia pobiera się w tej samej kolejce co spółki
// kontrolne, po nich.
const CONTEXT = {
  SYMBOLS: ['SPY', 'QQQ'],
};

/** Wszystkie instrumenty pobierane przez ten plik: kontrolne, potem tło rynku. */
function proofAllSymbols_() {
  return PROOF.SYMBOLS.concat(CONTEXT.SYMBOLS);
}

const PROOF_LABELS = [
  'Status', 'Spółek gotowych', 'Aktualnie pobierana', 'Zebranych sesji', 'Zapisanych dokumentów',
  'Zakres danych', 'Ostatnie uruchomienie (PL)', 'Szacowany koniec', 'Niepełna historia', 'Spółki z problemem', 'Ostatni błąd / info',
];


// ============================================================================
//  FUNKCJE PUBLICZNE
// ============================================================================
function startProof() {
  if (!CONFIG.FIRESTORE_ENABLED) {
    alert_('Spółki kontrolne zapisują się tylko do Firestore — włącz FIRESTORE_ENABLED w CONFIG (Code.gs).');
    return;
  }
  let st = proofLoad_();
  // Zapisany stan pochodzi z innego trybu (np. „Uzupełnij najnowsze”, mode:
  // 'refresh') — to nie jest bezpieczne wznowienie pełnej historii, tylko
  // inne zadanie. Zaczynamy prawdziwe pełne pobieranie od nowa, żeby
  // „Pobierz historię” zawsze robiło to, co obiecuje w nazwie. Dane w
  // Firestore się nie cofają — proofSaveSessions_ tylko dopisuje.
  if (st && st.mode !== 'full') st = null;
  // Lista się wydłużyła (np. doszło tło rynku) — wznawiamy tylko brakujące.
  if (st && st.done && st.mode === 'full' &&
      proofAllSymbols_().some(s => st.symbolsDone.indexOf(s) < 0 && st.symbolsFailed.indexOf(s) < 0)) {
    st.done = false;
    st.finishedAt = '';
  }
  if (st && st.done && st.mode === 'full') {
    alert_(`Historia jest już pobrana (${st.symbolsDone.length} z ${proofAllSymbols_().length}).\n` +
           'Użyj „Uzupełnij najnowsze”, żeby dociągnąć świeże dane, albo „Reset”, żeby pobrać wszystko od nowa.');
    return;
  }
  if (!st || st.done) st = proofInit_('full');
  st.stopped = false;   // wznowienie po „Zatrzymaj”
  proofSave_(st);
  proofSetupStats_();
  proofInstallTrigger_();
  const left = proofAllSymbols_().filter(s => st.symbolsDone.indexOf(s) < 0 && st.symbolsFailed.indexOf(s) < 0).length;
  proofExecute_(`Pobieranie historii: zostało ${left} z ${proofAllSymbols_().length} (1 co ${PROOF.EVERY_MINUTES} min).`);
  toast_('Spółki kontrolne pobierają się w tle. Postęp w arkuszu STATS, kolumny M–N.');
}

/** Handler triggera — NIE zmieniaj nazwy. */
function runProof() { proofExecute_(); }

function refreshProof() {
  const st = proofInit_('refresh');
  proofSave_(st);
  proofSetupStats_();
  proofInstallTrigger_();
  proofExecute_(`Uzupełnianie ostatnich ${PROOF.REFRESH_DAYS} dni dla spółek kontrolnych.`);
  toast_('Uzupełnianie najnowszych sesji trwa w tle.');
}

function stopProof() {
  const n = proofRemoveTrigger_();
  const st = proofLoad_();
  if (st && !st.done) { st.stopped = true; proofSave_(st); }
  proofRefreshStats_();
  toast_(`Zatrzymano (usunięto triggerów: ${n}). Postęp jest zapamiętany.`);
}

function resetProof() {
  try {
    const ui = SpreadsheetApp.getUi();
    if (ui.alert('Reset spółek kontrolnych',
      'Postęp zostanie wyzerowany i wszystkie 50 spółek pobiorą się od nowa.\n' +
      'Dane w Firestore zostają i zostaną nadpisane. Kontynuować?', ui.ButtonSet.YES_NO) !== ui.Button.YES) return;
  } catch (e) { /* uruchomione z edytora */ }
  proofSave_(proofInit_('full'));
  startRun_();
  log_('INFO', 'KONTROLNE', 'Reset — wszystkie spółki kontrolne pobiorą się od nowa.');
  proofRefreshStats_();
  toast_('Wyzerowano. Kliknij „Pobierz historię”, żeby ruszyć.');
}

/**
 * Pobiera PONOWNIE wskazane instrumenty, nie ruszając pozostałych.
 *
 * Po co: spółka raz wpisana na listę „gotowych” jest pomijana na zawsze, nawet
 * jeśli zapisała się z niepełną historią (tak stało się przy luce L13 — dziesięć
 * spółek zostało oznaczonych jako gotowe, mając po 6–28 sesji zamiast ~500).
 * „Reset” naprawiłby to kosztem ponownego pobrania wszystkich 53 instrumentów:
 * osiem godzin i ~24 000 zapisów do Firestore po to, żeby poprawić kilka spółek.
 * Ta funkcja zdejmuje z listy gotowych tylko wskazane symbole, więc kolejka
 * pobierze je od nowa, a resztę zostawi w spokoju.
 *
 * Dane w Firestore nie są kasowane — zapis tylko nadpisuje sesje tymi samymi
 * albo pełniejszymi wartościami.
 */
function refetchProof() {
  let input = '';
  try {
    const ui = SpreadsheetApp.getUi();
    const resp = ui.prompt('Pobierz ponownie wybrane instrumenty',
      'Podaj symbole po przecinku, np.:\n\nCAT, HON, UNP, RTX, AMZN, MCD, NKE, SBUX, T, VZ\n\n' +
      'Zostaną zdjęte z listy „gotowych” i pobrane od nowa. Pozostałe instrumenty nie są ruszane.',
      ui.ButtonSet.OK_CANCEL);
    if (resp.getSelectedButton() !== ui.Button.OK) return;
    input = resp.getResponseText();
  } catch (e) {
    alert_('Tę funkcję uruchamia się z menu arkusza (IA 4 → Spółki kontrolne).');
    return;
  }

  const wanted = String(input).toUpperCase().split(/[,\s]+/).filter(String);
  if (!wanted.length) { alert_('Nie podałeś żadnego symbolu.'); return; }

  const all = proofAllSymbols_();
  const unknown = wanted.filter(s => all.indexOf(s) < 0);
  if (unknown.length) {
    alert_(`Nie znam tych symboli: ${unknown.join(', ')}.\n\n` +
           'Muszą być na liście PROOF.SYMBOLS albo CONTEXT.SYMBOLS w Proof.gs.');
    return;
  }

  let st = proofLoad_();
  if (!st || st.mode !== 'full') st = proofInit_('full');

  const before = st.symbolsDone.length;
  st.symbolsDone = st.symbolsDone.filter(s => wanted.indexOf(s) < 0);
  st.symbolsFailed = st.symbolsFailed.filter(s => wanted.indexOf(s) < 0);
  st.symbolsPartial = st.symbolsPartial.filter(s => wanted.indexOf(s) < 0);
  st.done = false;
  st.finishedAt = '';
  st.stopped = false;
  st.retries = 0;
  proofSave_(st);

  proofSetupStats_();
  proofInstallTrigger_();
  startRun_();
  log_('INFO', 'KONTROLNE',
    `Ponowne pobranie: ${wanted.join(', ')} (zdjęto z listy gotowych ${before - st.symbolsDone.length}).`);
  proofExecute_();
  toast_(`Pobieram ponownie ${wanted.length} instrumentów. Postęp w STATS, kolumny M–N.`);
}

/** Lista spółek kontrolnych gotowych do backtestu (mają komplet danych). */
function proofReadySymbols() {
  const st = proofLoad_();
  return st ? st.symbolsDone.filter(s => PROOF.SYMBOLS.indexOf(s) >= 0) : [];
}


// ============================================================================
//  SILNIK
// ============================================================================
function proofExecute_(initMessage) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(60 * 1000)) {
    console.warn('Inne uruchomienie trwa — spółki kontrolne poczekają.');
    return;
  }
  startRun_();
  const st = proofLoad_() || proofInit_('full');
  try {
    if (initMessage) log_('INFO', 'KONTROLNE', initMessage);
    if (st.done || st.stopped) { proofRemoveTrigger_(); return; }
    st.lastRunAt = new Date().toISOString();

    for (let k = 0; k < PROOF.SYMBOLS_PER_RUN && !st.done; k++) {
      const symbol = proofNextSymbol_(st);
      if (!symbol) { proofFinish_(st); break; }
      if (!proofProcessSymbol_(st, symbol)) break;  // błąd — ponowimy za 10 minut
    }
  } catch (e) {
    proofError_(st, e.message || String(e));
  } finally {
    proofSave_(st);
    try { proofRefreshStats_(st); } catch (e2) { console.error(e2); }
    lock.releaseLock();
  }
}

function proofNextSymbol_(st) {
  const all = proofAllSymbols_();
  for (let i = 0; i < all.length; i++) {
    const s = all[i];
    if (st.symbolsDone.indexOf(s) < 0 && st.symbolsFailed.indexOf(s) < 0) return s;
  }
  return null;
}

/** Pobiera i zapisuje całą historię jednej spółki. Zwraca true, gdy się udało. */
function proofProcessSymbol_(st, symbol) {
  st.current = symbol;
  const to = Utilities.formatDate(new Date(), CONFIG.MARKET_TZ, 'yyyy-MM-dd');
  const from = st.mode === 'refresh'
    ? addDays_(to, -PROOF.REFRESH_DAYS)
    : addDays_(to, -PROOF.YAHOO_MAX_AGE_DAYS);

  let sessions;
  try {
    sessions = proofFetchRange_(symbol, from, to);
  } catch (e) {
    return proofRetry_(st, symbol, e.message || String(e));
  }

  const dates = Object.keys(sessions).sort();
  if (!dates.length) return proofRetry_(st, symbol, `${symbol}: Yahoo nie zwróciło żadnych sesji`);

  // Niepełną historię też zapisujemy — lepiej mieć 300 sesji niż nic. Spółka
  // trafia na listę „niepełne”, żeby było wiadomo, że jej wyniki opierają się
  // na krótszym okresie niż pozostałe.
  const partial = st.mode === 'full' && dates.length < PROOF.MIN_SESSIONS;

  try {
    const docs = proofSaveSessions_(symbol, sessions, dates);
    st.docsWritten += docs;
    st.sessionsSaved += dates.length;
  } catch (e) {
    // Błąd zapisu NIE liczy się do MAX_RETRIES i nigdy nie odkłada spółki na
    // listę „nieudanych” — dane są już pobrane z Yahoo, więc kolejna próba to
    // tylko ponowny zapis, bez ryzyka utraty danych. To ważne przy limicie
    // dziennym Firestore (HTTP 429): limit resetuje się dopiero po wielu
    // godzinach, więc próby liczone w minutach i tak nic by nie dały —
    // ta sama spółka po prostu czeka do skutku, tak jak w History.gs.
    const quota = /\b429\b|quota exceeded/i.test(e.message);
    proofError_(st, `${symbol}: zapis do Firestore nie powiódł się — ${e.message}` +
      (quota ? ' — to dzienny limit Firestore, nie problem z tą spółką; ponowię przy kolejnym uruchomieniu.' : ' — ponowię przy kolejnym uruchomieniu.'));
    return false;
  }

  st.symbolsDone.push(symbol);
  if (partial && st.symbolsPartial.indexOf(symbol) < 0) st.symbolsPartial.push(symbol);
  st.retries = 0;
  st.lastError = null;
  st.lastErrorMsg = '';
  st.coverage = `${dates[0]} – ${dates[dates.length - 1]}`;
  st.current = '';
  log_(partial ? 'UWAGA' : 'ZAPIS', 'KONTROLNE',
    `${symbol}: ${dates.length} sesji (${st.coverage})${partial ? ' — historia krótsza niż u pozostałych spółek' : ''}. ` +
    `Gotowych: ${st.symbolsDone.length}/${proofAllSymbols_().length}.`);
  proofStatusToFirestore_(st);
  return true;
}

function proofRetry_(st, symbol, msg) {
  st.retries++;
  if (st.retries >= PROOF.MAX_RETRIES) {
    st.symbolsFailed.push(symbol);
    st.retries = 0;
    st.current = '';
    proofError_(st, `${msg} — po ${PROOF.MAX_RETRIES} próbach pomijam tę spółkę`);
  } else {
    proofError_(st, `${msg} — ponowię za ${PROOF.EVERY_MINUTES} min (próba ${st.retries}/${PROOF.MAX_RETRIES})`);
  }
  return false;
}

function proofFinish_(st) {
  st.done = true;
  st.finishedAt = new Date().toISOString();
  proofRemoveTrigger_();
  const failed = st.symbolsFailed.length ? `, nie udało się: ${st.symbolsFailed.join(', ')}` : '';
  const partial = st.symbolsPartial.length ? `, niepełna historia: ${st.symbolsPartial.join(', ')}` : '';
  log_('INFO', 'KONTROLNE',
    `✓ Gotowe: ${st.symbolsDone.length} spółek, ${st.sessionsSaved} sesji, ${st.docsWritten} dokumentów${partial}${failed}.`);
  proofStatusToFirestore_(st);
}

function proofError_(st, msg) {
  st.lastError = { at: new Date().toISOString(), msg };
  if (st.lastErrorMsg !== msg) log_('UWAGA', 'KONTROLNE', msg);
  st.lastErrorMsg = msg;
  console.error('KONTROLNE: ' + msg);
}


// ============================================================================
//  YAHOO
// ============================================================================
/**
 * Świece 1h z zakresu dat, pogrupowane w sesje.
 * Zapytanie dzielimy na kawałki po CHUNK_DAYS dni, żeby odpowiedzi nie były
 * zbyt duże i żeby jedna nieudana część nie przekreślała całości.
 */
function proofFetchRange_(symbol, fromYmd, toYmd) {
  const sessions = {};
  let chunkStart = fromYmd;
  let problems = 0;
  let firstError = '';

  for (let guard = 0; guard < 20 && chunkStart <= toYmd; guard++) {
    let chunkEnd = addDays_(chunkStart, PROOF.CHUNK_DAYS);
    if (chunkEnd > toYmd) chunkEnd = toYmd;

    let bars = null;
    try {
      bars = proofFetchChunk_(symbol, chunkStart, chunkEnd);
    } catch (e) {
      problems++;
      if (!firstError) firstError = e.message || String(e);
    }
    if (bars) {
      bars.forEach(b => {
        const s = sessions[b.date] || (sessions[b.date] = {});
        s[b.slot] = b;   // duplikaty z zachodzących zakresów nadpisują się tą samą wartością
      });
    }
    if (chunkEnd === toYmd) break;
    chunkStart = addDays_(chunkEnd, 1);
    Utilities.sleep(1500);  // odstęp między zapytaniami, żeby Yahoo nie blokowało
  }

  if (!Object.keys(sessions).length) throw new Error(firstError || 'Yahoo nie zwróciło żadnych danych');
  if (problems) log_('UWAGA', 'KONTROLNE', `${symbol}: ${problems} z zakresów nie pobrało się (${firstError}). Zapisuję to, co jest.`);
  return sessions;
}

function proofFetchChunk_(symbol, fromYmd, toYmd) {
  const p1 = fromYmd.split('-').map(Number);
  const p2 = toYmd.split('-').map(Number);
  const period1 = Date.UTC(p1[0], p1[1] - 1, p1[2]) / 1000;
  const period2 = Date.UTC(p2[0], p2[1] - 1, p2[2] + 1, 6) / 1000;
  let lastMsg = 'nieznany błąd';

  for (let i = 0; i < YAHOO_HOSTS.length; i++) {
    const url = `https://${YAHOO_HOSTS[i]}/v8/finance/chart/${encodeURIComponent(symbol)}` +
                `?interval=1h&period1=${period1}&period2=${period2}&includePrePost=false`;
    try {
      const resp = UrlFetchApp.fetch(url, { muteHttpExceptions: true, headers: YAHOO_HEADERS });
      const code = resp.getResponseCode();
      let json = null;
      try { json = JSON.parse(resp.getContentText()); } catch (e) { /* nie-JSON */ }
      const result = json && json.chart && json.chart.result && json.chart.result[0];
      if (code === 200 && result) return parseBars_(result);

      const err = json && json.chart && json.chart.error;
      const desc = err ? String(err.description || err.code || '') : '';
      if (/no data found|not found/i.test(desc)) {
        log_('UWAGA', 'KONTROLNE', `${symbol}: Yahoo „brak danych” dla ${fromYmd}–${toYmd} (${desc || 'brak opisu'})`);
        return [];
      }
      lastMsg = `HTTP ${code}${desc ? ' — ' + desc : ''}`;
    } catch (e) {
      lastMsg = e.message || String(e);
    }
    if (i < YAHOO_HOSTS.length - 1) Utilities.sleep(1500);
  }
  throw new Error(lastMsg);
}


// ============================================================================
//  FIRESTORE
// ============================================================================
/** Jedna sesja = jeden dokument z tablicami slots, o, h, l, c. */
function proofSaveSessions_(symbol, sessions, dates) {
  const base = fsBase_();
  const nowIso = new Date().toISOString();

  // Ten sam format co automat bieżący (sessionFields_ w Code.gs).
  const writes = dates.map(date => ({
    update: {
      name: `${base}/${fsCollection_(symbol)}/${fsId_(symbol)}/sessions/${date}`,
      fields: sessionFields_(symbol, date, sessions[date], nowIso),
    },
  }));

  writes.push({
    update: {
      name: `${base}/${fsCollection_(symbol)}/${fsId_(symbol)}`,
      fields: {
        symbol: { stringValue: symbol },
        group: { stringValue: symbolGroup_(symbol) },
        sessions: { integerValue: String(dates.length) },
        firstDate: { stringValue: dates[0] },
        lastDate: { stringValue: dates[dates.length - 1] },
        format: { stringValue: 'session-arrays' },
        updatedAt: { timestampValue: nowIso },
      },
    },
  });

  for (let i = 0; i < writes.length; i += 400) firestoreCommit_(writes.slice(i, i + 400));
  return writes.length;
}

function proofStatusToFirestore_(st) {
  try {
    const strArr = (list) => ({ arrayValue: { values: list.map(s => ({ stringValue: s })) } });
    firestoreCommit_([{
      update: {
        name: `${fsBase_()}/system/universe`,
        fields: {
          live: strArr(CONFIG.SYMBOLS),
          proof: strArr(PROOF.SYMBOLS),
          context: strArr(CONTEXT.SYMBOLS),
          contextIds: strArr(CONTEXT.SYMBOLS.map(fsId_)),
          proofReady: strArr(st.symbolsDone.filter(s => PROOF.SYMBOLS.indexOf(s) >= 0)),
          contextReady: strArr(st.symbolsDone.filter(s => CONTEXT.SYMBOLS.indexOf(s) >= 0)),
          proofPartial: strArr(st.symbolsPartial),
          proofFailed: strArr(st.symbolsFailed),
          proofDone: { booleanValue: !!st.done },
          note: { stringValue: 'live: dokument na świecę w stocks/{SYM}/candles. proof: sesja w proof/{SYM}/sessions/{data}. context: sesja w context/{SYMBOL}/sessions/{data}.' },
          updatedAt: { timestampValue: new Date().toISOString() },
        },
      },
    }]);
  } catch (e) {
    console.warn('system/universe: ' + e.message);
  }
}


// ============================================================================
//  STAN
// ============================================================================
function proofInit_(mode) {
  return {
    mode: mode || 'full', symbolsDone: [], symbolsFailed: [], symbolsPartial: [], current: '',
    sessionsSaved: 0, docsWritten: 0, retries: 0, coverage: '',
    done: false, stopped: false, startedAt: new Date().toISOString(),
    finishedAt: '', lastRunAt: '', lastError: null, lastErrorMsg: '',
  };
}

function proofLoad_() {
  const raw = PropertiesService.getScriptProperties().getProperty('PROOF_STATE');
  return raw ? JSON.parse(raw) : null;
}

function proofSave_(st) {
  PropertiesService.getScriptProperties().setProperty('PROOF_STATE', JSON.stringify(st));
}

function proofInstallTrigger_() {
  proofRemoveTrigger_();
  ScriptApp.newTrigger('runProof').timeBased().everyMinutes(PROOF.EVERY_MINUTES).create();
}

function proofRemoveTrigger_() {
  let n = 0;
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'runProof') { ScriptApp.deleteTrigger(t); n++; }
  });
  return n;
}

function proofTriggerExists_() {
  try {
    return ScriptApp.getProjectTriggers().some(t => t.getHandlerFunction() === 'runProof');
  } catch (e) {
    return false;
  }
}


// ============================================================================
//  BLOK „SPÓŁKI KONTROLNE” W ARKUSZU STATS (kolumny M:N)
// ============================================================================
function proofSetupStats_() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.STATS_SHEET);
  if (!sh) return;
  const col = PROOF.STATS_COL, row = PROOF.STATS_ROW;
  if (sh.getMaxColumns() < col + 1) sh.insertColumnsAfter(sh.getMaxColumns(), col + 1 - sh.getMaxColumns());

  sh.getRange(row, col, 1, 2).breakApart().merge()
    .setValue(`KONTROLNE (${PROOF.SYMBOLS.length}) + TŁO RYNKU (${CONTEXT.SYMBOLS.length}) → Firestore`)
    .setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(row + 1, col, PROOF_LABELS.length, 1).setValues(PROOF_LABELS.map(x => [x]))
    .setFontWeight('bold').setBackground('#f1f3f4');
  sh.getRange(row + 1, col + 1, PROOF_LABELS.length, 1).setNumberFormat('@').setHorizontalAlignment('left');
  sh.setColumnWidth(col, 200);
  sh.setColumnWidth(col + 1, 330);
}

function proofRefreshStats_(st) {
  st = st || proofLoad_() || proofInit_('full');
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.STATS_SHEET);
  if (!sh) return;
  const col = PROOF.STATS_COL, row = PROOF.STATS_ROW;
  if (sh.getRange(row + 1, col).getValue() !== PROOF_LABELS[0]) proofSetupStats_();

  const fmt = iso => Utilities.formatDate(new Date(iso), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm');
  const left = proofAllSymbols_().length - st.symbolsDone.length - st.symbolsFailed.length;
  const active = proofTriggerExists_();

  let status;
  if (st.done) status = '✓ GOTOWE';
  else if (st.stopped || !active) status = '⏸ ZATRZYMANE';
  else if (st.retries) status = `⚠ ponawiam ${st.current}`;
  else status = `✓ AKTYWNE (co ${PROOF.EVERY_MINUTES} min)`;

  const eta = st.done ? '—'
    : `≈ ${fmt(new Date(Date.now() + Math.ceil(left / PROOF.SYMBOLS_PER_RUN) * PROOF.EVERY_MINUTES * 60000).toISOString())} (zostało ${left} spółek)`;

  let info = 'brak';
  if (st.done) info = `${st.mode === 'refresh' ? 'Uzupełnianie' : 'Pobieranie'} zakończone ${fmt(st.finishedAt)}`;
  else if (st.lastError) info = `${fmt(st.lastError.at)} — ${st.lastError.msg}`;

  sh.getRange(row + 1, col + 1, PROOF_LABELS.length, 1).setValues([
    [status],
    [`${st.symbolsDone.length} z ${proofAllSymbols_().length}`],
    [st.current || '—'],
    [String(st.sessionsSaved)],
    [String(st.docsWritten)],
    [st.coverage || '—'],
    [st.lastRunAt ? fmt(st.lastRunAt) : '—'],
    [eta],
    [st.symbolsPartial.length ? st.symbolsPartial.join(', ') : 'brak'],
    [st.symbolsFailed.length ? st.symbolsFailed.join(', ') : 'brak'],
    [info],
  ]);

  if (RUN_ && RUN_.logs.length) flushLog_(sh);
}