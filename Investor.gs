/**
 * ============================================================================
 *  IA 4 — WIRTUALNI INWESTORZY: wspólny log transakcji
 *
 *  Wersja projektu: 0.19 (2026-09-24) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Jeden arkusz `Transaction LOG` zbiera transakcje WSZYSTKICH inwestorów.
 *  Kolumna `inwestor` pozwala filtrować je w Excelu — celowo nie rozbijamy ich
 *  na osobne arkusze, bo kilku inwestorów z różnymi ustawieniami wykonuje
 *  częściowo te same transakcje i porównanie ich obok siebie jest sensowniejsze
 *  niż przełączanie się między zakładkami.
 *
 *  SKĄD BIORĄ SIĘ DANE
 *  Silnik inwestora rusza w Etapie 5 i będzie zapisywał transakcje do Firestore
 *  (`investors/{id}/trades/{tradeId}`). Ten plik je stamtąd zabiera i dopisuje
 *  do arkusza. Do tego czasu funkcje działają, ale nie mają czego przepisać —
 *  arkusz powstaje pusty, z samymi nagłówkami.
 *
 *  ZASADA 5.8: log jest TYLKO DOPISYWANY. Transakcja raz zapisana nie jest
 *  poprawiana wstecz; zmiana statusu (otwarta → zamknięta) aktualizuje wiersz
 *  po `id_transakcji`, ale historia wejścia zostaje nietknięta.
 *
 *  Plik wymaga Code.gs (CONFIG, log_, alert_, toast_, fsBase_).
 * ============================================================================
 */

const TXLOG = {
  SHEET: 'Transaction LOG',
  MAX_PULL: 500,        // ile transakcji najwyżej przepisujemy na jedno uruchomienie
};

const TXLOG_COLUMNS = [
  'inwestor',            // nazwa nadana w dashboardzie
  'id_inwestora',
  'id_transakcji',
  'id_strategii',
  'sygnal',
  'spolka',
  'grupa',
  'kierunek',            // LONG / SHORT
  'data_wejscia',
  'godzina_wejscia',
  'swieca_wejscia',      // numer świecy 1–7
  'cena_wejscia',
  'kwota',               // kapitał zaangażowany w tę transakcję ($)
  'SL_pct',
  'TP_pct',
  'H_swiec',             // limit czasu
  'PT',                  // rating sygnału 1–100
  'prog_PT',             // próg ustawiony u tego inwestora
  'data_wyjscia',
  'godzina_wyjscia',
  'cena_wyjscia',
  'powod_wyjscia',       // SL / TP / limit czasu
  'swiec_trzymania',
  'wynik_pct',
  'wynik_usd',
  'status',              // otwarta / zamknięta zyskownie / zamknięta stratnie
  'wieloznaczna',        // świeca zahaczyła i o SL, i o TP (5.4)
  'kapital_po',
  'skutecznosc_biegnaca',
  'ekspektancja_biegnaca',
  'wolumen_wejscia',
  'zrodlo',              // live / backtest
  'zapisano',
];


// ============================================================================
//  FUNKCJE PUBLICZNE (menu)
// ============================================================================

/** Tworzy arkusz Transaction LOG albo odświeża jego nagłówki. */
function txlogSetup() {
  const sh = txlogSheet_();
  alert_(`Arkusz „${TXLOG.SHEET}" gotowy.\n\n` +
    `Kolumn: ${TXLOG_COLUMNS.length}. Transakcji: ${Math.max(0, sh.getLastRow() - 1)}.\n\n` +
    'Filtruj po kolumnie „inwestor", żeby oglądać jednego naraz.');
}

/** Zabiera z Firestore transakcje, których jeszcze nie ma w arkuszu. */
function txlogSync() {
  const n = txlogSyncFromFirestore_();
  toast_(n ? `Dopisano transakcji: ${n}.` : 'Brak nowych transakcji do dopisania.');
}

/** Handler triggera — NIE zmieniaj nazwy. */
function txlogHourly() {
  try { txlogSyncFromFirestore_(); } catch (e) { console.error('TXLOG: ' + e.message); }
}

function txlogInstallTrigger() {
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'txlogHourly') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('txlogHourly').timeBased().everyHours(1).create();
  toast_('Log transakcji będzie odświeżany co godzinę.');
}


// ============================================================================
//  ARKUSZ
// ============================================================================
function txlogSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(TXLOG.SHEET);
  if (!sh) {
    sh = ss.insertSheet(TXLOG.SHEET);
    sh.setTabColor('#e8a33d');
  }
  const head = sh.getRange(1, 1, 1, TXLOG_COLUMNS.length);
  if (String(sh.getRange(1, 1).getValue()) !== TXLOG_COLUMNS[0]) {
    head.setValues([TXLOG_COLUMNS]);
  }
  head.setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.setFrozenRows(1);
  if (sh.getMaxColumns() > TXLOG_COLUMNS.length) {
    sh.deleteColumns(TXLOG_COLUMNS.length + 1, sh.getMaxColumns() - TXLOG_COLUMNS.length);
  }
  return sh;
}

/** Mapa id_transakcji → numer wiersza, żeby aktualizować zamiast duplikować. */
function txlogIndex_(sh) {
  const last = sh.getLastRow();
  if (last < 2) return {};
  const col = TXLOG_COLUMNS.indexOf('id_transakcji') + 1;
  const ids = sh.getRange(2, col, last - 1, 1).getValues();
  const map = {};
  ids.forEach((r, i) => { if (r[0]) map[String(r[0])] = i + 2; });
  return map;
}

/**
 * Dopisuje albo aktualizuje transakcje.
 * trades: tablica obiektów o kluczach zgodnych z TXLOG_COLUMNS (brakujące = puste).
 */
function txlogWrite_(trades) {
  if (!trades || !trades.length) return 0;
  const sh = txlogSheet_();
  const index = txlogIndex_(sh);
  const nowIso = new Date().toISOString();

  const toAppend = [];
  trades.forEach(t => {
    t.zapisano = nowIso;
    const row = TXLOG_COLUMNS.map(c => (t[c] === undefined || t[c] === null) ? '' : t[c]);
    const at = index[String(t.id_transakcji)];
    if (at) {
      sh.getRange(at, 1, 1, TXLOG_COLUMNS.length).setValues([row]);
    } else {
      toAppend.push(row);
    }
  });

  if (toAppend.length) {
    const start = Math.max(2, sh.getLastRow() + 1);
    if (sh.getMaxRows() < start + toAppend.length) {
      sh.insertRowsAfter(sh.getMaxRows(), toAppend.length + 200);
    }
    sh.getRange(start, 1, toAppend.length, TXLOG_COLUMNS.length).setValues(toAppend);
  }
  return trades.length;
}


// ============================================================================
//  FIRESTORE → ARKUSZ
// ============================================================================
/**
 * Czyta investors/{id}/trades z Firestore i przepisuje do arkusza.
 * Kolekcja powstanie w Etapie 5 — do tego czasu zwraca 0 bez błędu.
 */
function txlogSyncFromFirestore_() {
  if (!CONFIG.FIRESTORE_ENABLED) return 0;
  const investors = txlogListInvestors_();
  if (!investors.length) return 0;

  let written = 0;
  investors.forEach(invDoc => {
    const trades = txlogFetchTrades_(invDoc.id);
    if (!trades.length) return;
    trades.forEach(t => { t.inwestor = invDoc.name || invDoc.id; t.id_inwestora = invDoc.id; });
    written += txlogWrite_(trades);
  });
  if (written) log_('ZAPIS', 'INWESTOR', `Transaction LOG: przepisano ${written} transakcji.`);
  return written;
}

function txlogListInvestors_() {
  const resp = txlogFsGet_('investors');
  if (!resp || !resp.documents) return [];
  return resp.documents.map(d => {
    const id = d.name.split('/').pop();
    const f = d.fields || {};
    return { id, name: f.name ? f.name.stringValue : id };
  });
}

function txlogFetchTrades_(investorId) {
  const resp = txlogFsGet_(`investors/${investorId}/trades?pageSize=${TXLOG.MAX_PULL}`);
  if (!resp || !resp.documents) return [];
  return resp.documents.map(d => {
    const f = d.fields || {};
    const val = (k) => {
      const x = f[k];
      if (!x) return '';
      if (x.stringValue !== undefined) return x.stringValue;
      if (x.doubleValue !== undefined) return Number(x.doubleValue);
      if (x.integerValue !== undefined) return Number(x.integerValue);
      if (x.booleanValue !== undefined) return x.booleanValue;
      if (x.timestampValue !== undefined) return x.timestampValue;
      return '';
    };
    const t = { id_transakcji: d.name.split('/').pop() };
    TXLOG_COLUMNS.forEach(c => { if (c !== 'id_transakcji') t[c] = val(c); });
    return t;
  });
}

function txlogFsGet_(path) {
  const url = `https://firestore.googleapis.com/v1/${fsBase_()}/${path}`;
  const resp = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
  });
  const code = resp.getResponseCode();
  if (code === 404) return null;              // kolekcja jeszcze nie istnieje
  if (code !== 200) {
    console.warn(`Transaction LOG: HTTP ${code} dla ${path}`);
    return null;
  }
  try { return JSON.parse(resp.getContentText()); } catch (e) { return null; }
}
