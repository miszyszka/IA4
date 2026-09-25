/**
 * ============================================================================
 *  IA 4 — STAN PROJEKTU, SKARBIEC I AUDYT DANYCH
 *
 *  Wersja projektu: 0.20 (2026-09-25) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Realizuje zasady z pliku IA4_INSTRUKCJA.md:
 *   • arkusz PROJEKT — etapy, kryteria ukończenia, skarbiec, luki, decyzje,
 *   • trzy wiersze podsumowania w STATS,
 *   • granica skarbca zapisana w Firestore (system/project), żeby Python
 *     i Apps Script używały dokładnie tej samej,
 *   • audyt danych: pełny na żądanie i przyrostowy co noc,
 *   • jednorazowe sprzątanie Etapu 0.
 *
 *  MENU: IA 4 → Projekt
 *
 *  Plik wymaga Code.gs, History.gs (kalendarz świąt, addDays_) i Proof.gs.
 * ============================================================================
 */

const PROJECT = {
  INSTRUCTION_VERSION: '0.20',
  SHEET: 'PROJEKT',
  AUDIT_SHEET: '_AUDYT',
  DECISION_SHEET: '_AUDYT_DECYZJE',

  // Skarbiec (decyzja D1): 6 miesięcy przed datą cięcia 2026-09-22.
  //   odkrywanie:     wszystko PRZED PLOT_START  (uczenie i strojenie, bez ograniczen)
  //   poletko:        PLOT_START … PLOT_END       (sprawdzian raz na etap)
  //   skarbiec:       VAULT_START … VAULT_END     (jeden sprawdzian w calym projekcie)
  //   dane na zywo:   PO VAULT_END
  //
  // Poletko (0.19) wydzielono z okresu badawczego, zeby Etapy 1-3 mialy tania
  // informacje zwrotna przed otwarciem skarbca. Szczegoly: instrukcja, 5.1.
  PLOT_START: '2025-10-01',
  PLOT_END: '2026-03-22',
  VAULT_START: '2026-03-23',
  VAULT_END: '2026-09-22',

  NIGHTLY_HOUR: 23,          // nocny audyt (czas polski), po zamknięciu sesji w USA
  NIGHTLY_DAYS: 14,          // ile dni kalendarzowych wstecz sprawdza audyt nocny
  JUMP_PCT: 15,              // skok ceny podejrzany o split (D11 — 30% przepuszczało split 3:2 i 5:4)
  JUMP_PCT_BY_SYMBOL: {},    // progi wyjątkowe per instrument (obecnie brak)
  MAX_GAP_ROWS: 300,         // ile luk pokazywać w arkuszu PROJEKT
  MAX_RUNTIME_MS: 4.5 * 60 * 1000,
  PAGE: 1000,
};

// Sesje skrócone NYSE (zamknięcie 13:00 ET → 4 świece zamiast 7).
// Lista trzeba uzupełniać co rok razem z US_MARKET_HOLIDAYS w History.gs.
const EARLY_CLOSE_DAYS = {
  '2024-07-03': 1, '2024-11-29': 1, '2024-12-24': 1,
  '2025-07-03': 1, '2025-11-28': 1, '2025-12-24': 1,
  '2026-11-27': 1, '2026-12-24': 1,
};

const OLD_SHEETS = [
  'BACKTEST', 'KOMBINACJE', 'KOMBINACJE_LEGENDA', 'KOMBINACJE_PODOBIENSTWO', 'BENCHMARK',
  'STRATEGIE', 'STRATEGIE_LEGENDA',
  '_BACKTEST_DANE', '_KOMBINACJE_DANE', '_KOMBINACJE_TAB', '_BENCHMARK_DANE',
];
const OLD_TRIGGERS = ['btStep', 'comboStep', 'benchStep'];
const OLD_PROPS = ['BT_STATE', 'COMBO_STATE', 'BENCH_STATE'];

const STAGE_STATUS = { todo: '⬜ nie rozpoczęty', doing: '🟨 w toku', done: '✅ zakończony', held: '⏸ odroczony' };

// Kryteria ukończenia — kopia sekcji 6 instrukcji. auto = sprawdzane przez skrypt,
// brak auto = pole do zaznaczenia ręcznie w arkuszu PROJEKT.
const STAGES = [
  { n: 0, name: 'Porządki i fundamenty', criteria: [
    { id: '0.1', text: 'Stare arkusze analiz usunięte', auto: 'oldSheetsGone' },
    { id: '0.2', text: 'Stare pliki kodu i ich triggery usunięte', auto: 'oldCodeGone' },
    { id: '0.3', text: 'Tło rynku (SPY, QQQ): historia pobrana', auto: 'contextHistory' },
    { id: '0.4', text: 'Tło rynku zbierane na żywo', auto: 'contextLive' },
    { id: '0.5', text: 'Pełny audyt danych wykonany', auto: 'fullAudit' },
    { id: '0.6', text: 'Każda luka naprawiona albo zaakceptowana', auto: 'noNewGaps' },
    { id: '0.7', text: 'Granica skarbca zapisana w Firestore i w instrukcji', auto: 'vaultWritten' },
    { id: '0.8', text: 'Nocny audyt danych działa', auto: 'nightlyTrigger' },
    { id: '0.9', text: 'Python wczytuje dane wszystkich spółek, liczby zgadzają się z audytem (Etap 0B)' },
  ] },
  { n: 1, name: 'Katalog strategii S1', criteria: [
    { id: '1.1', text: 'Katalog S1 z opisami i parametrami gotowy' },
    { id: '1.2', text: 'Silnik w Pythonie przechodzi testy na ręcznie policzonych przypadkach' },
    { id: '1.3', text: 'Wyniki próbnych strategii zgodne z dotychczasowym silnikiem' },
  ] },
  { n: 2, name: 'Backtest S1 i wybór S2', criteria: [
    { id: '2.1', text: 'Wszystkie strategie S1 policzone na okresie badawczym' },
    { id: '2.2', text: 'Lista S2 zatwierdzona i zapisana (arkusz + Firestore)' },
    { id: '2.3', text: 'Kryteria wyboru S2 zapisane w instrukcji' },
  ] },
  { n: 3, name: 'Parametry towarzyszące i rating PT', criteria: [
    { id: '3.1', text: 'Raport najsilniejszych zależności' },
    { id: '3.2', text: 'Model PT i próg PT dobrane na walidacji kroczącej' },
    { id: '3.3', text: 'Model przenośny: ≤ ~50 parametrów, test zgodności Python ↔ Apps Script' },
    { id: '3.4', text: 'Jednorazowy sprawdzian na skarbcu wykonany i zapisany' },
  ] },
  { n: 4, name: 'Monitor sygnałów na żywo', criteria: [
    { id: '4.1', text: 'Monitor działa co najmniej 2 tygodnie bez luk' },
    { id: '4.2', text: 'Statystyka sygnałów na godzinę i rozkład PT' },
    { id: '4.3', text: 'Wyniki na żywo porównane z oczekiwaniami z Etapu 3' },
  ] },
  { n: 5, name: 'Paper trading', criteria: [
    { id: '5.1', text: 'Zasady wirtualnego inwestora ustalone i zapisane w instrukcji' },
    { id: '5.2', text: 'Wirtualny inwestor działa i zapisuje portfel' },
  ] },
];

const DECISIONS = [
  ['D1', 'Wielkość skarbca', 'ostatnie 6 miesięcy: 2026-03-23 – 2026-09-22', '✅ przyjęta'],
  ['D2', 'Gdzie działa Etap 4', 'Apps Script, zaraz po dopisaniu świecy; model z Pythona eksportowany jako JSON', '✅ przyjęta'],
  ['D3', 'Tło rynku', 'SPY, QQQ zbierane od Etapu 0 (VIX usunięty — D8)', '✅ przyjęta'],
  ['D4', 'Siatka SL/TP', 'pełna 10×10: 0,5 / 0,75 / 1 / 1,25 / 1,5 / 2 / 2,5 / 3 / 4 / 5%', '🔸 domyślna — potwierdzić przed Etapem 1'],
  ['D5', 'Limit czasu H', 'TP ≤ 1% → 14 świec, ≤ 2,5% → 35, ≤ 5% → 70', '🔸 domyślna — potwierdzić przed Etapem 1'],
  ['D6', 'Koszty', 'wynik bez kosztów + kolumna z 0,05% za transakcję', '🔸 domyślna — potwierdzić przed Etapem 1'],
  ['D7', 'Stary katalog STRATEGIE', 'usunięty w Etapie 0, zastąpi go S1', '✅ przyjęta'],
];

const PJ_WIDTH = 7;


// ============================================================================
//  FUNKCJE PUBLICZNE
// ============================================================================
/** Tworzy lub odświeża arkusz PROJEKT, zapisuje skarbiec, instaluje nocny audyt. */
function projectRefresh() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Inne zadanie trwa — spróbuj za chwilę.'); return; }
  try {
    const st = projLoad_();
    if (!st.stages[0].started) { st.stages[0].status = 'doing'; st.stages[0].started = new Date().toISOString(); }
    if (st.vaultVersion !== PROJECT.INSTRUCTION_VERSION || !st.vaultWrittenAt) projWriteFirestore_(st);
    projEnsureNightly_();
    projRender_(st);
    projSave_(st);
  } finally {
    lock.releaseLock();
  }
  toast_('Stan projektu odświeżony — arkusz PROJEKT.');
}

/**
 * Jednorazowe sprzątanie Etapu 0: usuwa stare arkusze analiz, ich triggery
 * i zapisany stan. Samych plików .gs skrypt nie potrafi usunąć — trzeba to
 * zrobić ręcznie w edytorze (arkusz PROJEKT pokaże, czy zostały).
 */
function etap0Cleanup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const removed = [];
  OLD_SHEETS.forEach(name => {
    const sh = ss.getSheetByName(name);
    if (sh && ss.getSheets().length > 1) { ss.deleteSheet(sh); removed.push(name); }
  });
  let trig = 0;
  ScriptApp.getProjectTriggers().forEach(t => {
    if (OLD_TRIGGERS.indexOf(t.getHandlerFunction()) >= 0) { ScriptApp.deleteTrigger(t); trig++; }
  });
  const props = PropertiesService.getScriptProperties();
  OLD_PROPS.forEach(k => props.deleteProperty(k));

  startRun_();
  log_('INFO', 'PROJEKT', `Etap 0: usunięto arkuszy ${removed.length}, triggerów ${trig}, stanów ${OLD_PROPS.length}.`);
  const stats = ss.getSheetByName(CONFIG.STATS_SHEET);
  if (stats) flushLog_(stats);

  projectRefresh();
  const left = projOldCodeLeft_();
  alert_(`Usunięto arkuszy: ${removed.length}, triggerów: ${trig}.` +
    (left.length ? `\n\nW edytorze skryptów zostały jeszcze pliki ze starymi funkcjami: ${left.join(', ')}. Usuń je ręcznie (trzy kropki przy nazwie pliku → Usuń).` : '\n\nStarych plików kodu już nie ma.'));
}

/**
 * ZEROWANIE STANU PO WYCZYSZCZENIU FIRESTORE
 *
 * Skrypt pamięta we właściwościach projektu, co już zapisał do bazy. Gdy baza
 * zostanie skasowana ręcznie w konsoli Firebase, ta pamięć zostaje i automat
 * uznaje, że wszystko ma — czyli nie pobiera niczego, a historia nigdy nie
 * rusza. Ta funkcja czyści wszystkie stany pobierania, żeby projekt zaczął od
 * zera razem z pustą bazą.
 *
 * NIE kasuje niczego w Firestore — od tego jest konsola Firebase. Nie rusza
 * też stanu projektu (etap, decyzje, akceptacje luk), bo to zapis Twoich
 * ustaleń, a nie danych giełdowych.
 */
function resetAfterWipe() {
  const props = PropertiesService.getScriptProperties();
  // Każdy nowy stan trzymany w Script Properties MUSI trafić na tę listę —
  // inaczej po wyczyszczeniu bazy system wierzy w postęp, którego już nie ma
  // (np. „wolumen dopisany" dla danych, które właśnie skasowano).
  const keys = ['LIVE_STATE', 'HISTORY_STATE', 'PROOF_STATE', 'AUDIT_STATE',
                'SESSION', 'LAST_WRITE', 'COUNTERS', 'FS_STATUS',
                'LAST_ERROR', 'ERR_SEEN',
                'PATCH_LAST_AT', 'PATCH_ATTEMPTS',        // łatanie luk (0.10, 0.17)
                'VOLFILL_STATE', 'VOLFILL_LAST_AT',       // dopisywanie wolumenu (0.10)
                'AUDIT_READ_BUDGET',                      // budżet odczytów (0.15)
                'FS_QUOTA_DAY',                           // blokada po wyczerpaniu limitu (0.18)
                'TELEMETRY_HASH', 'TELEMETRY_PUSHED_AT',  // telemetria (0.12)
                'STATS_LAYOUT_SYMS'];                     // cache układu arkusza STATS
  // Świadomie NIE czyścimy: GITHUB_TOKEN (poświadczenie, nie postęp)
  // ani PROJECT_STATE (etap, decyzje i zaakceptowane luki — obiecane niżej w oknie).
  try {
    const ui = SpreadsheetApp.getUi();
    const ok = ui.alert('Zerowanie stanu po wyczyszczeniu bazy',
      'Użyj tego TYLKO po skasowaniu danych w konsoli Firebase.\n\n' +
      'Wyzeruje postęp pobierania (bieżący automat, historia spółek głównych, ' +
      'spółki kontrolne, audyt), żeby wszystko zaczęło się od nowa.\n\n' +
      'Stan projektu — etap, decyzje, zaakceptowane luki — zostaje nietknięty.\n\n' +
      'Kontynuować?', ui.ButtonSet.YES_NO);
    if (ok !== ui.Button.YES) return;
  } catch (e) { /* uruchomione z edytora */ }

  // Triggery pobierania zatrzymujemy, żeby nie ruszyły w połowie czyszczenia.
  let stopped = 0;
  ScriptApp.getProjectTriggers().forEach(t => {
    if (['runProof', 'runHistory', 'auditStep'].indexOf(t.getHandlerFunction()) >= 0) {
      ScriptApp.deleteTrigger(t); stopped++;
    }
  });
  keys.forEach(k => props.deleteProperty(k));

  startRun_();
  log_('INFO', 'PROJEKT', `Stan wyzerowany po wyczyszczeniu bazy (usunięto triggerów: ${stopped}).`);
  const stats = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.STATS_SHEET);
  if (stats) flushLog_(stats);

  alert_('Stan wyzerowany.\n\nKolejność uruchamiania:\n' +
         '1. IA 4 → Konfiguruj i włącz automat  (odtworzy system/status i zacznie zbierać na żywo)\n' +
         '2. IA 4 → Projekt → Pokaż / odśwież stan projektu  (odtworzy system/project)\n' +
         '3. IA 4 → Historia → Start / wznów  (3 spółki główne, ~17 h)\n' +
         '4. Następnego dnia: IA 4 → Spółki kontrolne → Pobierz historię');
}

/** Pełny audyt wszystkich spółek. Liczy się w tle w partiach. */
/**
 * Pełny audyt czyta z Firestore KAŻDY dokument całej historii każdego
 * instrumentu — przy obecnym rozmiarze bazy (~35-40 tys. dokumentów) to
 * prawie cały dzienny darmowy limit 50 000 odczytów. Dwa uruchomienia tego
 * samego dnia go przebijają. AUDIT_READ_BUDGET (poniżej) pilnuje tego licznika
 * i wstrzymuje audyt, zanim zabraknie odczytów potrzebnych czemuś innemu;
 * ta stała pilnuje drugiej strony — żeby w ogóle nie zaczynać drugi raz bez
 * pytania, gdy pierwszy przebieg i tak już dziś wykorzystał budżet.
 */
function runFullAudit() {
  const today = Utilities.formatDate(new Date(), CONFIG.MARKET_TZ, 'yyyy-MM-dd');
  const prev = auditLoadState_();
  if (prev && prev.startedAt && prev.startedAt.slice(0, 10) === today && !prev.forceConfirmed) {
    const ui = SpreadsheetApp.getUi();
    const resp = ui.alert('Pełny audyt już dziś ruszał',
      `Pełny audyt dziś już był uruchamiany (${prev.done ? 'ukończony' : 'w toku'}) i zużył część ` +
      'dziennego limitu odczytów Firestore (50 000). Uruchomienie go ponownie dziś może wyczerpać ' +
      'limit potrzebny bieżącej zbiórce świec.\n\nUruchomić mimo to?',
      ui.ButtonSet.YES_NO);
    if (resp !== ui.Button.YES) return;
  }

  const ctx = marketContext_(new Date());
  auditPrepareSheet_(true);
  auditSaveState_({
    mode: 'full', since: null, symbols: liveSymbols_(), idx: 0,
    startedAt: new Date().toISOString(), etDate: ctx.etDate, stats: {}, forceConfirmed: true,
  });
  auditRemoveTrigger_();
  ScriptApp.newTrigger('auditStep').timeBased().everyMinutes(1).create();
  auditStep();
  toast_('Audyt danych ruszył. Wynik pojawi się w arkuszu PROJEKT.');
}

// ----------------------------------------------------------------------------
//  BUDŻET ODCZYTÓW FIRESTORE (dotyczy pełnego audytu — jedynego, co czyta dużo)
// ----------------------------------------------------------------------------
const AUDIT_READ_BUDGET = {
  DAILY_MAX: 35000,   // margines poniżej limitu 50 000 — zostawia miejsce na dashboard i inne zadania
};

/** Współdzielony licznik na czas jednego wywołania auditStep_; zapisywany raz na koniec. */
function auditReadBudget_() {
  const day = Utilities.formatDate(new Date(), CONFIG.MARKET_TZ, 'yyyy-MM-dd');
  const raw = JSON.parse(PropertiesService.getScriptProperties().getProperty('AUDIT_READ_BUDGET') || '{}');
  const used = raw.day === day ? (raw.used || 0) : 0;
  const b = { day, used, spent: 0 };
  b.left = () => AUDIT_READ_BUDGET.DAILY_MAX - b.used - b.spent;
  b.spend = (n) => { b.spent += n; };
  b.persist = () => PropertiesService.getScriptProperties()
    .setProperty('AUDIT_READ_BUDGET', JSON.stringify({ day: b.day, used: b.used + b.spent }));
  return b;
}

/** Handler triggera pełnego audytu — NIE zmieniaj nazwy. */
function auditStep() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10 * 1000)) return;
  const t0 = Date.now();
  const st = auditLoadState_();
  const budget = auditReadBudget_();
  try {
    if (!st || st.done) { auditRemoveTrigger_(); return; }
    if (budget.left() <= 0) {
      log_('UWAGA', 'AUDYT', `Dzienny budżet odczytów Firestore wyczerpany (${AUDIT_READ_BUDGET.DAILY_MAX}) — pełny audyt czeka do jutra.`);
      return;   // trigger co minutę zostaje — sam ruszy dalej, gdy dzień się zmieni
    }
    const ctx = marketContext_(new Date());
    let stoppedByBudget = false;
    do {
      const symbol = st.symbols[st.idx];
      const r = auditSymbol_(symbol, st.since, ctx, budget);
      if (r.partial) {
        // Symbol nie doczytany do końca — spróbujemy go od nowa, gdy budżet się odnowi.
        stoppedByBudget = true;
        break;
      }
      auditAppend_(r.gaps);
      st.stats[symbol] = r.stats;
      st.idx++;
    } while (st.idx < st.symbols.length && budget.left() > 0 && Date.now() - t0 < PROJECT.MAX_RUNTIME_MS);

    if (stoppedByBudget) {
      log_('UWAGA', 'AUDYT', `Budżet odczytów wyczerpany w trakcie ${st.symbols[st.idx]} — dokończy jutro.`);
    }
    if (st.idx >= st.symbols.length) {
      st.done = true;
      auditRemoveTrigger_();
      const p = projLoad_();
      p.audit = p.audit || {};
      p.audit.fullAt = new Date().toISOString();
      p.audit.stats = st.stats;
      projRender_(p);
      projSave_(p);
      startRun_();
      log_('INFO', 'AUDYT', `Pełny audyt: ${st.symbols.length} spółek, luk: ${p.summary ? p.summary.gapsTotal : '?'}.`);
      const stats = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.STATS_SHEET);
      if (stats) flushLog_(stats);
    }
  } catch (e) {
    st.error = String(e.message || e).slice(0, 300);
    console.error(e);
  } finally {
    if (st) auditSaveState_(st);
    budget.persist();
    lock.releaseLock();
  }
}

/** Nocny audyt przyrostowy — ostatnie 14 dni. Handler triggera, NIE zmieniaj nazwy. */
function auditNightly() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(60 * 1000)) return;
  try {
    const ctx = marketContext_(new Date());
    const since = addDays_(ctx.etDate, -PROJECT.NIGHTLY_DAYS);
    const symbols = liveSymbols_();
    const gaps = [];
    symbols.forEach(s => {
      try { gaps.push.apply(gaps, auditSymbol_(s, since, ctx).gaps); }
      catch (e) { gaps.push(auditGap_(s, 'BLAD_ODCZYTU', ctx.etDate, '', String(e.message || e).slice(0, 150))); }
    });
    auditMerge_(symbols, since, gaps);
    const p = projLoad_();
    p.audit = p.audit || {};
    p.audit.nightlyAt = new Date().toISOString();
    projRender_(p);
    projSave_(p);
  } finally {
    lock.releaseLock();
  }
}

/** Zamyka bieżący etap, jeśli spełnione są wszystkie kryteria. */
function closeCurrentStage() {
  const st = projLoad_();
  const n = st.current;
  const crit = projEvalCriteria_(n, st, projReadInputs_());
  const missing = crit.filter(c => !c.ok);
  if (missing.length) {
    alert_(`Etap ${n} nie może być zamknięty. Niespełnione kryteria:\n\n` +
      missing.map(c => `• ${c.id} ${c.text}${c.detail ? ' — ' + c.detail : ''}`).join('\n'));
    return;
  }
  st.stages[n].status = 'done';
  st.stages[n].finished = new Date().toISOString();
  if (n + 1 < STAGES.length) {
    st.current = n + 1;
    st.stages[n + 1].status = 'doing';
    st.stages[n + 1].started = new Date().toISOString();
  }
  projWriteFirestore_(st);
  projRender_(st);
  projSave_(st);
  startRun_();
  log_('INFO', 'PROJEKT', `Etap ${n} zamknięty. Następny: Etap ${st.current}. Zaktualizuj instrukcję .md.`);
  const stats = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.STATS_SHEET);
  if (stats) flushLog_(stats);
  alert_(`✅ Etap ${n} zamknięty. Aktualny etap: ${st.current} — ${STAGES[st.current].name}.\n\n` +
    'Poproś Claude o nową wersję instrukcji IA4_INSTRUKCJA.md z tym statusem.');
}

/**
 * Pokazuje okno z gotowym tekstem do wklejenia na początku nowej rozmowy
 * z Claude — obok pliku IA4_INSTRUKCJA.md. Zawiera dokładnie to, co Claude
 * i tak by musiał ustalić pytaniami: etap, kryteria, luki czekające na
 * decyzję, otwarte decyzje. Nic nie zapisuje, tylko czyta bieżący stan.
 */
function projectExportBriefing() {
  const st = projLoad_();
  const inputs = projReadInputs_();
  const md = projectBriefingText_(st, inputs);
  const esc = md.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const html = HtmlService.createHtmlOutput(
    '<textarea id="t" style="width:96%;height:430px;font-family:monospace;font-size:12px;padding:8px;" readonly>' +
    esc + '</textarea>' +
    '<p style="font-family:Arial,sans-serif;font-size:13px;color:#555;margin:8px 2px 0">' +
    'Zaznaczone i skopiowane (Ctrl/Cmd+C). Wklej to na początku nowej rozmowy z Claude, ' +
    'razem z załączonym plikiem IA4_INSTRUKCJA.md.</p>' +
    '<script>const t=document.getElementById("t");t.focus();t.select();</script>'
  ).setWidth(680).setHeight(520);
  SpreadsheetApp.getUi().showModalDialog(html, 'Podsumowanie dla Claude — wklej na start rozmowy');
}

/** Luki połączone z decyzjami użytkownika. Współdzielone przez arkusz i briefing. */
function projComputeGaps_(inputs) {
  const decisions = auditLoadDecisions_();
  Object.keys(inputs.gaps).forEach(k => { decisions[k] = inputs.gaps[k]; });
  auditSaveDecisions_(decisions);
  return auditLoadGaps_().map(r => {
    const d = decisions[r[0]] || {};
    return { key: r[0], symbol: r[1], type: r[2], date: String(r[3]), desc: r[4], status: d.status || 'nowa', comment: d.comment || '' };
  });
}

/** Treść briefingu — czysta funkcja, testowalna bez arkusza kalkulacyjnego. */
function projectBriefingText_(st, inputs) {
  const stg = STAGES[st.current];
  const crit = projEvalCriteria_(st.current, st, inputs);
  const gaps = projComputeGaps_(inputs);
  const gapsNew = gaps.filter(g => g.status === 'nowa');
  const lines = [];
  const p = (s) => lines.push(s);

  p(`# IA 4 — stan projektu (wygenerowano ${projFmt_(new Date().toISOString())})`);
  p('');
  p(`Wersja instrukcji zapisana w kodzie: **${PROJECT.INSTRUCTION_VERSION}**. ` +
    'Jeśli to inna wersja niż nagłówek załączonego IA4_INSTRUKCJA.md — plik jest nieaktualny, dopytaj.');
  p('');
  p(`## Etap ${st.current} — ${stg.name} (${STAGE_STATUS[st.stages[st.current].status]})`);
  crit.forEach(c => p(`- [${c.ok ? 'x' : ' '}] ${c.id} ${c.text}${c.detail ? ' — ' + c.detail : ''}`));
  p('');
  p('## Skarbiec');
  p(`Badawczy: do ${addDays_(PROJECT.VAULT_START, -1)} włącznie · Skarbiec: ${PROJECT.VAULT_START} – ${PROJECT.VAULT_END} ` +
    `(${st.vaultOpenedAt ? 'OTWARTY ' + projFmt_(st.vaultOpenedAt) : 'zamknięty'}) · ` +
    `Zapisany w Firestore: ${st.vaultWrittenAt ? projFmt_(st.vaultWrittenAt) : 'NIE'}`);
  p('');
  p('## Dane');
  const a = st.audit || {};
  p(`Pełny audyt: ${a.fullAt ? projFmt_(a.fullAt) : 'nie wykonany'} · Nocny: ${a.nightlyAt ? projFmt_(a.nightlyAt) : 'nie było'}`);
  p(`Luk łącznie: ${gaps.length} (nowych: ${gapsNew.length}, zaakceptowanych: ${gaps.length - gapsNew.length})`);
  if (gapsNew.length) {
    p('');
    p(`### Nowe luki czekające na decyzję (pokazano ${Math.min(20, gapsNew.length)} z ${gapsNew.length})`);
    gapsNew.slice(0, 20).forEach(g => p(`- ${g.symbol} · ${g.type} · ${g.date} — ${g.desc}`));
  }
  p('');
  p('## Decyzje');
  DECISIONS.forEach(d => p(`- ${d[0]} ${d[1]}: ${d[2]} [${d[3]}]`));
  const open = DECISIONS.filter(d => d[3].indexOf('🔸') === 0);
  if (open.length) {
    p('');
    p(`Otwarte, do potwierdzenia: ${open.map(d => d[0]).join(', ')}.`);
  }
  p('');
  p('## Co dalej');
  const missing = crit.filter(c => !c.ok);
  p(missing.length
    ? `Etap ${st.current} nie jest zamknięty — brakuje: ${missing.map(c => c.id).join(', ')}.`
    : `Wszystkie kryteria Etapu ${st.current} spełnione — do rozważenia zamknięcie etapu (menu IA 4 → Projekt → Zamknij bieżący etap).`);
  return lines.join('\n');
}

/** Podsumowanie do STATS (trzy wiersze). Czyta tylko zapisany stan — jest tanie. */
function projectSummary_(st) {
  st = st || projLoad_();
  const stg = STAGES[st.current];
  const s = st.summary || {};
  const stage = `Etap ${st.current} — ${stg.name} (${STAGE_STATUS[st.stages[st.current].status]}` +
    (s.critTotal ? `, kryteria ${s.critOk}/${s.critTotal}` : '') + ')';
  const gaps = !st.audit || !st.audit.fullAt ? 'pełny audyt jeszcze nie wykonany'
    : `nowych: ${s.gapsNew || 0}, zaakceptowanych: ${s.gapsAccepted || 0} (pełny audyt ${projFmt_(st.audit.fullAt)}` +
      (st.audit.nightlyAt ? `, nocny ${projFmt_(st.audit.nightlyAt)}` : '') + ')';
  const vault = st.vaultOpenedAt
    ? `OTWARTY ${projFmt_(st.vaultOpenedAt)} — ${PROJECT.VAULT_START} – ${PROJECT.VAULT_END}`
    : `zamknięty: ${PROJECT.VAULT_START} – ${PROJECT.VAULT_END}`;
  return [stage, gaps, vault];
}


// ============================================================================
//  AUDYT DANYCH
// ============================================================================
/** Sprawdza jedną spółkę od daty `since` (albo od początku danych). */
function auditSymbol_(symbol, since, ctx, budget) {
  const data = auditRead_(symbol, since, budget);
  if (data.partial) return { gaps: [], stats: null, partial: true };

  const dates = Object.keys(data.byDate).sort();
  const gaps = [];
  const add = (type, date, extra, desc) => gaps.push(auditGap_(symbol, type, date, extra, desc));

  if (!dates.length) {
    add('BRAK_DANYCH', since || ctx.etDate, '', since ? `brak danych od ${since}` : 'brak jakichkolwiek danych');
    return { gaps, stats: { sessions: 0, candles: 0, first: '', last: '' } };
  }
  const first = dates[0];
  const last = dates[dates.length - 1];
  const end = auditLastExpectedDay_(ctx);
  const start = since && since > first ? since : first;

  // Brakujące całe sesje
  for (let d = start, guard = 0; d <= end && guard < 1000; d = addDays_(d, 1), guard++) {
    if (projTradingDay_(d) && !data.byDate[d]) add('BRAK_SESJI', d, '', 'brak całej sesji');
  }
  // Spółka przestała się aktualizować
  if (last < end) add('NIEAKTUALNE', end, '', `ostatnie dane z ${last}, oczekiwane do ${end}`);

  const jump = (PROJECT.JUMP_PCT_BY_SYMBOL[symbol] || PROJECT.JUMP_PCT);
  let candles = 0;
  let prev = null;
  dates.forEach(d => {
    const slots = data.byDate[d];
    const keys = Object.keys(slots).map(Number).sort((a, b) => a - b);
    candles += keys.length;
    const expected = EARLY_CLOSE_DAYS[d] ? 4 : 7;

    if (d <= end) {   // dzisiejsza, niezakończona sesja nie jest sprawdzana pod kątem braków
      const missing = [];
      for (let s = 0; s < expected; s++) if (!slots[s]) missing.push(s + 1);
      if (missing.length) add('BRAK_SWIEC', d, '', `brak świec nr ${missing.join(', ')} z ${expected}`);
      const extra = keys.filter(s => s >= expected);
      if (extra.length) add('NADMIAR', d, '', `świece ponad ${expected}: nr ${extra.map(s => s + 1).join(', ')} — sprawdź, czy to sesja skrócona`);
    }
    keys.forEach(s => {
      const b = slots[s];
      const bad = !(b.o > 0 && b.h > 0 && b.l > 0 && b.c > 0) ||
        b.h < Math.max(b.o, b.c) - 1e-9 || b.l > Math.min(b.o, b.c) + 1e-9;
      if (bad) add('BLEDNE_OHLC', d, s + 1, `świeca nr ${s + 1}: O ${b.o} H ${b.h} L ${b.l} C ${b.c}`);
      if (prev && prev.c > 0) {
        const j = Math.abs(b.o / prev.c - 1) * 100;
        if (j > jump) add('SKOK_CENY', d, s + 1, `świeca nr ${s + 1}: ${prev.c} → ${b.o} (${j.toFixed(1)}%) — możliwy split`);
      }
      prev = b;
    });
  });
  data.dups.forEach(d => add('DUPLIKAT', d, '', 'ten sam numer świecy występuje w sesji więcej niż raz'));

  return { gaps, stats: { sessions: dates.length, candles, first, last } };
}

function auditGap_(symbol, type, date, extra, desc) {
  return [`${symbol}|${type}|${date}${extra ? '|' + extra : ''}`, symbol, type, date, desc, new Date().toISOString()];
}

/** Ostatni dzień sesji, który powinien już być kompletny. */
function auditLastExpectedDay_(ctx) {
  let d = ctx.etDate;
  const closeMin = sessionCloseFor_(getSession_(), d);
  const todayDone = projTradingDay_(d) && ctx.etMin >= closeMin + CONFIG.POLL_AFTER_CLOSE_MIN;
  if (!todayDone) {
    d = addDays_(d, -1);
    for (let g = 0; g < 10 && !projTradingDay_(d); g++) d = addDays_(d, -1);
  }
  return d;
}

function projTradingDay_(d) {
  return isoWeekday_(d) <= 5 && !US_MARKET_HOLIDAYS[d];
}

/**
 * Czyta świece spółki z Firestore w jednolitej postaci byDate[data][nr 0…6].
 * Spółki główne: dokument na świecę. Kontrolne i tło rynku: dokument na sesję.
 * Stronicowanie po (date, __name__) działa na indeksie jednego pola.
 */
function auditRead_(symbol, since, budget) {
  const coll = fsCollection_(symbol);
  const id = fsId_(symbol);
  const main = coll === 'stocks';
  const sub = main ? 'candles' : 'sessions';
  const fields = main ? ['date', 'slot', 'open', 'high', 'low', 'close'] : ['date', 'slots', 'o', 'h', 'l', 'c'];
  const byDate = {};
  const dups = [];
  const num = (v) => v ? Number(v.doubleValue !== undefined ? v.doubleValue : v.integerValue) : NaN;
  let cursor = null;

  for (let page = 0; page < 100; page++) {
    if (budget && budget.left() <= 0) return { byDate, dups, partial: true };
    const q = {
      from: [{ collectionId: sub }],
      select: { fields: fields.map(f => ({ fieldPath: f })) },
      orderBy: [
        { field: { fieldPath: 'date' }, direction: 'ASCENDING' },
        { field: { fieldPath: '__name__' }, direction: 'ASCENDING' },
      ],
      limit: PROJECT.PAGE,
    };
    if (since) q.where = { fieldFilter: { field: { fieldPath: 'date' }, op: 'GREATER_THAN_OR_EQUAL', value: { stringValue: since } } };
    if (cursor) q.startAt = { values: [{ stringValue: cursor.date }, { referenceValue: cursor.name }], before: false };

    const rows = fsRunQuery_(`${coll}/${id}`, q);
    if (budget) budget.spend(rows.filter(r => r.document).length);
    let got = 0;
    rows.forEach(r => {
      if (!r.document) return;
      got++;
      const f = r.document.fields;
      const date = f.date.stringValue;
      cursor = { date, name: r.document.name };
      const day = byDate[date] || (byDate[date] = {});
      if (main) {
        day[Number(f.slot.integerValue) - 1] = { o: num(f.open), h: num(f.high), l: num(f.low), c: num(f.close) };
      } else {
        const arr = (k) => (f[k] && f[k].arrayValue && f[k].arrayValue.values) || [];
        const sl = arr('slots'), o = arr('o'), h = arr('h'), l = arr('l'), c = arr('c');
        const seen = {};
        sl.forEach((v, i) => {
          const s = Number(v.integerValue) - 1;
          if (seen[s]) dups.push(date);
          seen[s] = 1;
          day[s] = { o: num(o[i]), h: num(h[i]), l: num(l[i]), c: num(c[i]) };
        });
      }
    });
    if (got < PROJECT.PAGE) break;
  }
  return { byDate, dups };
}

function fsRunQuery_(parent, structuredQuery) {
  const url = `https://firestore.googleapis.com/v1/${fsBase_()}/${parent}:runQuery`;
  const resp = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    payload: JSON.stringify({ structuredQuery }),
    muteHttpExceptions: true,
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error(`Firestore HTTP ${resp.getResponseCode()}: ${resp.getContentText().slice(0, 200)}`);
  }
  return JSON.parse(resp.getContentText());
}

// --- magazyn luk ------------------------------------------------------------
function auditPrepareSheet_(clear) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(PROJECT.AUDIT_SHEET);
  if (!sh) { sh = ss.insertSheet(PROJECT.AUDIT_SHEET); sh.hideSheet(); }
  if (clear) sh.clearContents();
  sh.getRange(1, 1, 1, 6).setValues([['klucz', 'spolka', 'typ', 'data', 'opis', 'wykryto']]);
  let dec = ss.getSheetByName(PROJECT.DECISION_SHEET);
  if (!dec) {
    dec = ss.insertSheet(PROJECT.DECISION_SHEET);
    dec.hideSheet();
    dec.getRange(1, 1, 1, 3).setValues([['klucz', 'status', 'komentarz']]);
  }
  return sh;
}

function auditAppend_(gaps) {
  if (!gaps.length) return;
  const sh = auditPrepareSheet_(false);
  const start = Math.max(2, sh.getLastRow() + 1);
  if (sh.getMaxRows() < start + gaps.length) sh.insertRowsAfter(sh.getMaxRows(), gaps.length + 500);
  sh.getRange(start, 1, gaps.length, 6).setNumberFormat('@').setValues(gaps);
}

/** Audyt nocny: podmienia luki z ostatnich dni, starsze zostawia. */
function auditMerge_(symbols, since, gaps) {
  const sh = auditPrepareSheet_(false);
  const last = sh.getLastRow();
  const old = last > 1 ? sh.getRange(2, 1, last - 1, 6).getValues() : [];
  const set = {};
  symbols.forEach(s => { set[s] = 1; });
  const keep = old.filter(r => !(set[r[1]] && (String(r[3]) >= since || r[2] === 'NIEAKTUALNE' || r[2] === 'BRAK_DANYCH')));
  const rows = keep.concat(gaps);
  sh.getRange(2, 1, Math.max(last - 1, 1), 6).clearContent();
  if (rows.length) {
    if (sh.getMaxRows() < rows.length + 1) sh.insertRowsAfter(sh.getMaxRows(), rows.length + 500);
    sh.getRange(2, 1, rows.length, 6).setNumberFormat('@').setValues(rows);
  }
}

function auditLoadGaps_() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(PROJECT.AUDIT_SHEET);
  if (!sh || sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, 6).getValues().filter(r => r[0]);
}

function auditLoadDecisions_() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(PROJECT.DECISION_SHEET);
  const map = {};
  if (!sh || sh.getLastRow() < 2) return map;
  sh.getRange(2, 1, sh.getLastRow() - 1, 3).getValues().forEach(r => { if (r[0]) map[r[0]] = { status: r[1], comment: r[2] }; });
  return map;
}

function auditSaveDecisions_(map) {
  auditPrepareSheet_(false);
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(PROJECT.DECISION_SHEET);
  const rows = Object.keys(map).filter(k => map[k].status !== 'nowa' || map[k].comment)
    .map(k => [k, map[k].status, map[k].comment || '']);
  const last = sh.getLastRow();
  if (last > 1) sh.getRange(2, 1, last - 1, 3).clearContent();
  if (rows.length) {
    if (sh.getMaxRows() < rows.length + 1) sh.insertRowsAfter(sh.getMaxRows(), rows.length + 100);
    sh.getRange(2, 1, rows.length, 3).setNumberFormat('@').setValues(rows);
  }
}

/**
 * Postęp trwającego pełnego audytu. Jedno miejsce prawdy dla arkusza PROJEKT,
 * kryteriów i telemetrii — audyt kończy się dopiero po ostatnim symbolu.
 */
function auditProgress_() {
  const st = auditLoadState_();
  const total = (st && st.symbols || []).length;
  const running = !!total && !st.done;
  return {
    running, done: !!(st && st.done), total,
    index: st ? (st.idx || 0) : 0,
    current: st && st.symbols ? (st.symbols[st.idx || 0] || '') : '',
    startedAt: st ? (st.startedAt || '') : '',
  };
}

function auditLoadState_() {
  const raw = PropertiesService.getScriptProperties().getProperty('AUDIT_STATE');
  return raw ? JSON.parse(raw) : null;
}
function auditSaveState_(st) {
  PropertiesService.getScriptProperties().setProperty('AUDIT_STATE', JSON.stringify(st));
}
function auditRemoveTrigger_() {
  ScriptApp.getProjectTriggers().forEach(t => { if (t.getHandlerFunction() === 'auditStep') ScriptApp.deleteTrigger(t); });
}


// ============================================================================
//  KRYTERIA UKOŃCZENIA
// ============================================================================
function projEvalCriteria_(n, st, inputs) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ctxSyms = (typeof CONTEXT !== 'undefined') ? CONTEXT.SYMBOLS : [];
  const checks = {
    oldSheetsGone: () => {
      const left = OLD_SHEETS.filter(s => ss.getSheetByName(s));
      return [!left.length, left.length ? 'zostały: ' + left.join(', ') : ''];
    },
    oldCodeGone: () => {
      const left = projOldCodeLeft_();
      const trig = ScriptApp.getProjectTriggers().filter(t => OLD_TRIGGERS.indexOf(t.getHandlerFunction()) >= 0).length;
      const parts = [];
      if (left.length) parts.push('pliki: ' + left.join(', '));
      if (trig) parts.push(`triggerów: ${trig}`);
      return [!parts.length, parts.join('; ')];
    },
    contextHistory: () => {
      const ps = (typeof proofLoad_ === 'function') ? proofLoad_() : null;
      const done = ps ? ps.symbolsDone : [];
      const left = ctxSyms.filter(s => done.indexOf(s) < 0);
      return [ctxSyms.length > 0 && !left.length, left.length ? 'brak historii: ' + left.join(', ') : ''];
    },
    contextLive: () => {
      const live = liveLoad_();
      const left = ctxSyms.filter(s => !(live[s] && live[s].k));
      return [ctxSyms.length > 0 && !left.length, left.length ? 'jeszcze nie zapisane: ' + left.join(', ') : ''];
    },
    fullAudit: () => {
      const done = !!(st.audit && st.audit.fullAt);
      const p = auditProgress_();
      // Trwający przebieg ustawia fullAt dopiero na końcu, więc bez tej informacji
      // kryterium przez cały audyt pokazywałoby datę POPRZEDNIego audytu i wyglądało
      // na zepsute. Postęp ma pierwszeństwo przed starą datą.
      if (p.running) {
        return [done, `audyt w toku: ${p.index}/${p.total}` + (p.current ? ` (${p.current})` : '') +
          (done ? ` · poprzedni: ${projFmt_(st.audit.fullAt)}` : '')];
      }
      return [done, done ? projFmt_(st.audit.fullAt) : 'jeszcze nie wykonany'];
    },
    noNewGaps: () => {
      const s = st.summary || {};
      const p = auditProgress_();
      const ok = !!(st.audit && st.audit.fullAt) && !p.running && !s.gapsNew;
      if (p.running) return [false, `audyt w toku (${p.index}/${p.total}) — luki policzone po zakończeniu`];
      return [ok, st.audit && st.audit.fullAt ? `nowych luk: ${s.gapsNew || 0}` : 'najpierw pełny audyt'];
    },
    vaultWritten: () => [!!st.vaultWrittenAt, st.vaultWrittenAt ? projFmt_(st.vaultWrittenAt) : 'jeszcze nie zapisana'],
    nightlyTrigger: () => {
      const ok = ScriptApp.getProjectTriggers().some(t => t.getHandlerFunction() === 'auditNightly');
      return [ok, ok ? `codziennie ok. ${PROJECT.NIGHTLY_HOUR}:00` : 'brak triggera'];
    },
  };
  return STAGES[n].criteria.map(c => {
    if (c.auto) {
      const r = checks[c.auto]();
      return { id: c.id, text: c.text, mode: 'automatycznie', ok: r[0], detail: r[1] };
    }
    const ok = !!(inputs.manual && inputs.manual[c.id]);
    return { id: c.id, text: c.text, mode: 'ręcznie', ok, detail: ok ? '' : 'zaznacz, gdy spełnione' };
  });
}

function projOldCodeLeft_() {
  const left = [];
  if (typeof createStrategiesSheet === 'function') left.push('Strategies.gs');
  if (typeof runBacktest === 'function') left.push('Backtest.gs');
  if (typeof runCombos === 'function') left.push('Combo.gs');
  if (typeof runBenchmark === 'function') left.push('Benchmark.gs');
  return left;
}


// ============================================================================
//  ARKUSZ PROJEKT
// ============================================================================
/** Odczyt tego, co użytkownik wpisał w arkuszu: ręczne kryteria i decyzje o lukach. */
function projReadInputs_() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(PROJECT.SHEET);
  const st = projLoad_();
  const inputs = { manual: Object.assign({}, st.manual || {}), gaps: {} };
  if (!sh || sh.getLastRow() < 1) return inputs;
  sh.getRange(1, 1, sh.getLastRow(), PJ_WIDTH).getValues().forEach(r => {
    const id = String(r[0] || '');
    if (id.indexOf('K') === 0) inputs.manual[id.slice(1)] = r[4] === true;
    if (id.indexOf('L|') === 0) inputs.gaps[id.slice(2)] = { status: r[5] || 'nowa', comment: r[6] || '' };
  });
  return inputs;
}

function projRender_(st) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const inputs = projReadInputs_();
  st.manual = inputs.manual;

  // Decyzje o lukach: to, co jest w arkuszu, ma pierwszeństwo przed zapisanym.
  const gaps = projComputeGaps_(inputs);
  const gapsNew = gaps.filter(g => g.status === 'nowa').length;
  st.summary = { gapsTotal: gaps.length, gapsNew, gapsAccepted: gaps.length - gapsNew };

  const crit = projEvalCriteria_(st.current, st, inputs);
  st.summary.critOk = crit.filter(c => c.ok).length;
  st.summary.critTotal = crit.length;

  // --- budowa arkusza --------------------------------------------------------
  let sh = ss.getSheetByName(PROJECT.SHEET);
  if (!sh) { sh = ss.insertSheet(PROJECT.SHEET, 0); sh.setTabColor('#e37400'); }
  sh.getDataRange().clearDataValidations();
  sh.clear();
  sh.setConditionalFormatRules([]);

  const rows = [];
  const styles = [];   // [wiersz, rodzaj]
  const push = (cells, kind) => {
    const r = cells.concat(new Array(PJ_WIDTH - cells.length).fill(''));
    rows.push(r);
    if (kind) styles.push([rows.length, kind]);
  };
  const stg = STAGES[st.current];

  push(['', 'IA 4 — STAN PROJEKTU'], 'title');
  push(['', 'Wersja instrukcji', `IA4_INSTRUKCJA.md v${PROJECT.INSTRUCTION_VERSION}`]);
  push(['', 'Aktualny etap', `Etap ${st.current} — ${stg.name}`]);
  push(['', 'Kryteria bieżącego etapu', `${st.summary.critOk} z ${st.summary.critTotal} spełnionych`]);
  push(['', 'Ostatnie odświeżenie', projFmt_(new Date().toISOString())]);
  push([]);

  push(['#ETAPY', 'ETAPY'], 'section');
  push(['', 'Etap', 'Nazwa', 'Status', 'Rozpoczęty', 'Zakończony'], 'head');
  STAGES.forEach(s => {
    const x = st.stages[s.n];
    push(['', s.n, s.name, STAGE_STATUS[x.status], x.started ? projFmt_(x.started) : '—', x.finished ? projFmt_(x.finished) : '—'],
      s.n === st.current ? 'current' : null);
  });
  push([]);

  push(['#KRYTERIA', `KRYTERIA UKOŃCZENIA — ETAP ${st.current}`], 'section');
  push(['', 'Nr', 'Kryterium', 'Sprawdzanie', 'Spełnione', 'Szczegóły'], 'head');
  const manualRows = [];   // [wiersz, zaznaczone?] — pola wyboru wstawiamy po zapisie
  crit.forEach(c => {
    push(['K' + c.id, c.id, c.text, c.mode, c.mode === 'ręcznie' ? '' : (c.ok ? '✓' : '✗'), c.detail]);
    if (c.mode === 'ręcznie') manualRows.push([rows.length, c.ok]);
  });
  push([]);

  push(['#SKARBIEC', 'SKARBIEC DANYCH'], 'section');
  push(['', 'Okres badawczy', `do ${addDays_(PROJECT.VAULT_START, -1)} włącznie`, 'Etapy 1–3']);
  push(['', 'Skarbiec', `${PROJECT.VAULT_START} – ${PROJECT.VAULT_END}`, 'otwierany raz, na końcu Etapu 3']);
  push(['', 'Dane na żywo', `od ${addDays_(PROJECT.VAULT_END, 1)}`, 'Etapy 4–5']);
  push(['', 'Status skarbca', st.vaultOpenedAt ? `OTWARTY ${projFmt_(st.vaultOpenedAt)}` : 'zamknięty',
    st.vaultWrittenAt ? `zapisany w Firestore ${projFmt_(st.vaultWrittenAt)}` : 'jeszcze nie zapisany w Firestore']);
  push([]);

  push(['#DANE', 'DANE'], 'section');
  const a = st.audit || {};
  const ap = auditProgress_();
  push(['', 'Pełny audyt',
    ap.running ? `W TOKU ${ap.index}/${ap.total}${ap.current ? ' — ' + ap.current : ''}`
      : (a.fullAt ? projFmt_(a.fullAt) : 'jeszcze nie wykonany'),
    ap.running ? `idzie co minutę, kończy się sam; poprzedni: ${a.fullAt ? projFmt_(a.fullAt) : 'brak'}`
      : 'menu IA 4 → Projekt → Pełny audyt danych']);
  push(['', 'Nocny audyt', a.nightlyAt ? projFmt_(a.nightlyAt) : 'jeszcze nie było', `codziennie ok. ${PROJECT.NIGHTLY_HOUR}:00, ostatnie ${PROJECT.NIGHTLY_DAYS} dni`]);
  push(['', 'Luki', `nowych: ${gapsNew}`, `zaakceptowanych: ${gaps.length - gapsNew}`]);
  if (a.stats) {
    push(['', 'Spółka', 'Grupa', 'Sesji', 'Świec', 'Zakres', 'Luk'], 'head');
    const byS = {};
    gaps.forEach(g => { byS[g.symbol] = (byS[g.symbol] || 0) + 1; });
    liveSymbols_().forEach(s => {
      const x = a.stats[s];
      if (!x) return;
      push(['', s, GROUP_LABELS[symbolGroup_(s)], x.sessions, x.candles, x.first ? `${x.first} – ${x.last}` : '—', byS[s] || 0]);
    });
  }
  push([]);

  push(['#LUKI', `LUKI W DANYCH (${gaps.length}${gaps.length > PROJECT.MAX_GAP_ROWS ? `, pokazano ${PROJECT.MAX_GAP_ROWS}` : ''})`], 'section');
  push(['', 'Spółka', 'Typ', 'Data', 'Opis', 'Status', 'Komentarz'], 'head');
  const gapStart = rows.length + 1;
  gaps.sort((x, y) => (x.status === 'nowa' ? 0 : 1) - (y.status === 'nowa' ? 0 : 1) ||
    (x.symbol < y.symbol ? -1 : x.symbol > y.symbol ? 1 : 0) || (x.date < y.date ? -1 : 1));
  gaps.slice(0, PROJECT.MAX_GAP_ROWS).forEach(g => push(['L|' + g.key, g.symbol, g.type, g.date, g.desc, g.status, g.comment]));
  const gapRows = Math.min(gaps.length, PROJECT.MAX_GAP_ROWS);
  if (!gaps.length) push(['', a.fullAt ? 'Brak luk ✓' : 'Uruchom pełny audyt, żeby zobaczyć luki.']);
  push([]);

  push(['#DECYZJE', 'DECYZJE'], 'section');
  push(['', 'Nr', 'Decyzja', 'Ustalenie', 'Status'], 'head');
  DECISIONS.forEach(d => push(['', d[0], d[1], d[2], d[3]]));

  // --- zapis i formatowanie --------------------------------------------------
  if (sh.getMaxRows() < rows.length + 5) sh.insertRowsAfter(sh.getMaxRows(), rows.length + 5 - sh.getMaxRows());
  if (sh.getMaxColumns() < PJ_WIDTH) sh.insertColumnsAfter(sh.getMaxColumns(), PJ_WIDTH - sh.getMaxColumns());
  sh.getRange(1, 1, rows.length, PJ_WIDTH).setNumberFormat('@').setValues(rows).setVerticalAlignment('top');
  sh.getRange(1, 1, rows.length, 1).setFontColor('#bdc1c6').setFontSize(8);

  styles.forEach(([r, kind]) => {
    const rg = sh.getRange(r, 2, 1, PJ_WIDTH - 1);
    if (kind === 'title') rg.merge().setFontSize(14).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
    if (kind === 'section') rg.merge().setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
    if (kind === 'head') rg.setFontWeight('bold').setBackground('#f1f3f4');
    if (kind === 'current') rg.setBackground('#fef7e0').setFontWeight('bold');
  });
  // Pole wyboru potrzebuje wartości logicznej, a nie tekstu — dlatego najpierw
  // zdejmujemy format tekstowy, potem wstawiamy pole i ustawiamy stan.
  manualRows.forEach(([r, ok]) => sh.getRange(r, 5).clearFormat().insertCheckboxes().setValue(ok));
  if (gapRows) {
    const rule = SpreadsheetApp.newDataValidation().requireValueInList(['nowa', 'zaakceptowana'], true).build();
    sh.getRange(gapStart, 6, gapRows, 1).setDataValidation(rule);
  }

  const cr = () => SpreadsheetApp.newConditionalFormatRule();
  const all = sh.getRange(1, 2, rows.length, PJ_WIDTH - 1);
  sh.setConditionalFormatRules([
    cr().whenTextEqualTo('✓').setFontColor('#0d652d').setBold(true).setRanges([all]).build(),
    cr().whenTextEqualTo('✗').setFontColor('#a50e0e').setBold(true).setRanges([all]).build(),
    cr().whenTextEqualTo('nowa').setBackground('#fad2cf').setFontColor('#a50e0e').setRanges([all]).build(),
    cr().whenTextEqualTo('zaakceptowana').setFontColor('#5f6368').setRanges([all]).build(),
    cr().whenTextStartsWith('✅').setFontColor('#0d652d').setRanges([all]).build(),
    cr().whenTextStartsWith('🟨').setFontColor('#b06000').setBold(true).setRanges([all]).build(),
  ]);

  sh.setColumnWidth(1, 60);
  sh.setColumnWidth(2, 190);
  sh.setColumnWidth(3, 330);
  sh.setColumnWidth(4, 230);
  sh.setColumnWidth(5, 330);
  sh.setColumnWidth(6, 200);
  sh.setColumnWidth(7, 240);
  sh.setFrozenRows(1);
}


// ============================================================================
//  STAN PROJEKTU
// ============================================================================
/**
 * Usuwa pozostałości po instrumentach, których nie ma już w projekcie (D8: VIX).
 *
 * Usunięcie symbolu z list w kodzie nie czyści tego, co już zostało zapisane:
 * w LIVE_STATE zostaje jego wpis, a w arkuszu luk jego luki, które liczą się
 * do kryterium 0.6 i blokują zamknięcie etapu. Ta funkcja sprząta jedno i drugie.
 * Dokumentów w Firestore nie rusza — te kasuje się świadomie, z konsoli.
 */
function cleanupRemovedSymbols() {
  const known = liveSymbols_();
  const props = PropertiesService.getScriptProperties();

  // 1) stan automatu
  const live = JSON.parse(props.getProperty('LIVE_STATE') || '{}');
  const strayLive = Object.keys(live).filter(s => known.indexOf(s) < 0);
  strayLive.forEach(s => delete live[s]);
  if (strayLive.length) props.setProperty('LIVE_STATE', JSON.stringify(live));

  // 2) luki w arkuszu audytu
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(PROJECT.AUDIT_SHEET);
  let removedGaps = 0;
  if (sh && sh.getLastRow() > 1) {
    const rows = sh.getRange(2, 1, sh.getLastRow() - 1, 6).getValues();
    const keep = rows.filter(r => !r[1] || known.indexOf(String(r[1])) >= 0);
    removedGaps = rows.length - keep.length;
    if (removedGaps) {
      sh.getRange(2, 1, rows.length, 6).clearContent();
      if (keep.length) sh.getRange(2, 1, keep.length, 6).setNumberFormat('@').setValues(keep);
    }
  }

  // 3) stan dopisywania wolumenu
  const vol = JSON.parse(props.getProperty('VOLFILL_STATE') || 'null');
  let strayVol = 0;
  if (vol && vol.symbols) {
    const before = vol.symbols.length;
    vol.symbols = vol.symbols.filter(s => known.indexOf(s) >= 0);
    strayVol = before - vol.symbols.length;
    if (strayVol) {
      if (vol.idx >= vol.symbols.length) { vol.idx = Math.max(0, vol.symbols.length - 1); }
      props.setProperty('VOLFILL_STATE', JSON.stringify(vol));
    }
  }

  projRender_(projLoad_());
  alert_('Sprzątanie po usuniętych instrumentach:\n\n' +
    `• stan automatu: ${strayLive.length ? strayLive.join(', ') : 'nic do usunięcia'}\n` +
    `• luki w audycie: usunięto ${removedGaps}\n` +
    `• kolejka wolumenu: usunięto ${strayVol}\n\n` +
    'Dokumenty w Firestore zostają — skasuj je ręcznie w konsoli, jeśli chcesz.');
}

function projLoad_() {
  const raw = PropertiesService.getScriptProperties().getProperty('PROJECT_STATE');
  const st = raw ? JSON.parse(raw) : {};
  if (st.current === undefined) st.current = 0;
  if (!st.stages) {
    st.stages = {};
    STAGES.forEach(s => { st.stages[s.n] = { status: 'todo', started: '', finished: '' }; });
  }
  st.manual = st.manual || {};
  return st;
}

function projSave_(st) {
  PropertiesService.getScriptProperties().setProperty('PROJECT_STATE', JSON.stringify(st));
  projUpdateStats_(st);
}

/** Od razu przepisuje trzy wiersze stanu projektu w STATS — bez czekania na automat. */
function projUpdateStats_(st) {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.STATS_SHEET);
  if (!sh || sh.getRange(STATS.PROJ_STAGE, 1).getValue() !== 'Etap projektu') return;
  sh.getRange(STATS.PROJ_STAGE, 2, 3, 1).setValues(projectSummary_(st).map(x => [x]));
}

/** Zapisuje granicę skarbca i etap do Firestore (system/project). */
function projWriteFirestore_(st) {
  firestoreCommit_([{
    update: {
      name: `${fsBase_()}/system/project`,
      fields: {
        instructionVersion: { stringValue: PROJECT.INSTRUCTION_VERSION },
        stage: { integerValue: String(st.current) },
        stageName: { stringValue: STAGES[st.current].name },
        researchEndExclusive: { stringValue: PROJECT.VAULT_START },
        discoveryEndExclusive: { stringValue: PROJECT.PLOT_START },
        plotStart: { stringValue: PROJECT.PLOT_START },
        plotEnd: { stringValue: PROJECT.PLOT_END },
        vaultStart: { stringValue: PROJECT.VAULT_START },
        vaultEnd: { stringValue: PROJECT.VAULT_END },
        liveFrom: { stringValue: addDays_(PROJECT.VAULT_END, 1) },
        vaultOpened: { booleanValue: !!st.vaultOpenedAt },
        updatedAt: { timestampValue: new Date().toISOString() },
      },
    },
  }]);
  st.vaultWrittenAt = new Date().toISOString();
  st.vaultVersion = PROJECT.INSTRUCTION_VERSION;
}

function projEnsureNightly_() {
  const has = ScriptApp.getProjectTriggers().some(t => t.getHandlerFunction() === 'auditNightly');
  if (!has) ScriptApp.newTrigger('auditNightly').timeBased().atHour(PROJECT.NIGHTLY_HOUR).everyDays(1).create();
}

function projFmt_(iso) {
  return Utilities.formatDate(new Date(iso), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm');
}