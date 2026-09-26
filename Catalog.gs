/**
 * ============================================================================
 *  IA 4 — KATALOG S1  (s1/catalog.json z GitHub → arkusz S1)
 *
 *  Wersja projektu: 0.27 (2026-09-26) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  PO CO TO JEST
 *  Źródłem prawdy katalogu jest plik s1/catalog.json w repozytorium (D20),
 *  generowany przez ia4-research/ia4/catalog.py. Arkusz S1 jest tylko jego
 *  widokiem: ta funkcja pobiera plik i buduje arkusz od zera. Arkusza nie
 *  edytuje się ręcznie — zmiana wpisana w komórkę nie trafiłaby do silnika.
 *  Jedyny wyjątek to kolumna „Uwagi”: jej treść jest zapamiętywana po ID
 *  sygnału i przywracana przy każdej odbudowie.
 *
 *  Plik jest czytany przez GitHub API tym samym tokenem, którego używa
 *  telemetria (IA 4 → Telemetria → Ustaw token GitHub).
 * ============================================================================
 */

const CATALOG = {
  SHEET: 'S1',
  PATH: 's1/catalog.json',
  PROP: 'S1_CATALOG',          // Script Properties: wersja i hash ostatnio wczytanego katalogu
  HEADER_ROWS: 7,              // wiersze nagłówka nad tabelą
};

const CATALOG_COLUMNS = [
  // [nagłówek, klucz/funkcja, szerokość]
  ['ID', s => s.id, 50],
  ['Kod', s => s.code, 190],
  ['Kat.', s => s.category, 45],
  ['Rodzina', s => s.family, 170],
  ['Zdarzenie', s => s.event, 85],
  ['Definicja', s => s.definition, 460],
  ['Parametry JSON', s => JSON.stringify(s.params), 260],
  ['Wolumen', s => (s.volume ? 'tak' : ''), 65],
  ['SPY', s => (s.market ? 'tak' : ''), 45],
  ['Rozgrzewka (świec)', s => s.warmup_bars, 80],
  ['Na żywo (świec)', s => s.live_lookback_bars, 75],
  ['Wejście', s => s.entry, 105],
  ['Pochodzenie', s => s.origin, 95],
  ['Para', s => s.paired_with || '', 170],
  ['Częstość: sygnałów / dni', s => (s.frequency ? `${s.frequency.signals} / ${s.frequency.days}` : ''), 95],
  ['Status', s => s.status, 80],
  ['Strategii', s => s.strategies, 65],
  ['Uwagi', null, 260],
];

const CATALOG_CAT_COLORS = {
  H1: '#fce8e6', H2: '#e8f0fe', H3: '#e6f4ea', H4: '#fef7e0',
  H5: '#f3e8fd', H6: '#e4f7fb', H7: '#fde7f3', H8: '#eef3e2',
};

/** Menu: IA 4 → Projekt → Wczytaj katalog S1 z GitHub. */
function catalogLoadS1() {
  let cat;
  try {
    cat = catalogFetch_();
  } catch (e) {
    alert_('Nie udało się wczytać katalogu S1.\n\n' + e.message);
    return;
  }
  const n = catalogRender_(cat);
  const m = cat.meta;
  PropertiesService.getScriptProperties().setProperty(CATALOG.PROP, JSON.stringify({
    version: m.catalog_version, hash: m.content_hash, status: m.status,
    signals: m.signals, strategies: m.strategies, loadedAt: new Date().toISOString(),
  }));
  toast_(`Katalog S1 wczytany: ${n} sygnałów, ${m.strategies} strategii (hash ${m.content_hash}).`);
}

/** Pobiera s1/catalog.json z repozytorium jako surowy tekst (działa też dla plików > 1 MB). */
function catalogFetch_() {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('Brak tokenu GitHub. Ustaw go: IA 4 → Telemetria → Ustaw token GitHub.');
  const url = `https://api.github.com/repos/${TELEMETRY.REPO}/contents/${CATALOG.PATH}?ref=${TELEMETRY.BRANCH}`;
  const resp = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github.raw+json' },
  });
  const code = resp.getResponseCode();
  if (code === 404) throw new Error(`W repozytorium nie ma pliku ${CATALOG.PATH}.`);
  if (code !== 200) throw new Error(`GitHub HTTP ${code}.`);
  const cat = JSON.parse(resp.getContentText('UTF-8'));
  if (!cat || !cat.meta || !Array.isArray(cat.signals)) throw new Error('Plik nie wygląda na katalog S1.');
  return cat;
}

/** Buduje arkusz S1 od zera. Zwraca liczbę sygnałów. */
function catalogRender_(cat) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(CATALOG.SHEET);
  const notes = sh ? catalogReadNotes_(sh) : {};
  if (!sh) { sh = ss.insertSheet(CATALOG.SHEET); sh.setTabColor('#1a73e8'); }
  sh.clear();

  const m = cat.meta;
  const W = CATALOG_COLUMNS.length;
  const pad = r => r.concat(new Array(W - r.length).fill(''));
  const byCat = Object.keys(m.by_category).map(k => `${k} ${m.by_category[k]}`).join(' · ');

  const head = [
    pad(['KATALOG SYGNAŁÓW S1']),
    pad(['Wersja katalogu', m.catalog_version, '', `hash ${m.content_hash}`, `projekt v${m.project_version}`]),
    pad(['Status', m.status]),
    pad(['Sygnałów', `${m.signals} (aktywnych ${m.signals_active}, kontrolnych ${m.signals_control})`, '', byCat]),
    pad(['Strategii', `${m.strategies} = sygnały × ${cat.exits.directions.length} kierunki × ${cat.exits.sl_pct.length}×${cat.exits.tp_pct.length} wyjść`]),
    pad(['Wczytano', Utilities.formatDate(new Date(), 'Europe/Warsaw', 'yyyy-MM-dd HH:mm'), '',
      'Widok pliku s1/catalog.json (D20) — nie edytuj ręcznie. Wolno pisać tylko w kolumnie „Uwagi”.']),
    pad([]),
  ];
  const header = CATALOG_COLUMNS.map(c => c[0]);
  const rows = cat.signals.map(s => CATALOG_COLUMNS.map(([name, fn]) => (fn ? fn(s) : (notes[s.id] || ''))));

  // Pod tabelą: przepis na wyjście z transakcji — cały przepis na strategię w jednym miejscu (1.6).
  const tail = [pad([]), pad(['WYJŚCIA (D4, D5, D10)'])];
  tail.push(pad(['SL i TP [%]', cat.exits.sl_pct.join(' · '), '', 'wszystkie 100 kombinacji']));
  tail.push(pad(['Kierunki', cat.exits.directions.join(', '), '', 'każdy sygnał liczony jako LONG i SHORT (D9)']));
  tail.push(pad(['H — punkt wyjścia', cat.exits.h_default.map(h => `TP ≤ ${h.tp_max}% → ${h.bars} świec`).join(' · ')]));
  tail.push(pad(['H — reguła', cat.exits.h_rule]));
  tail.push(pad([]), pad(['DEFINICJE WSPÓLNE (1.3)']));
  Object.keys(m.conventions).forEach(k => tail.push(pad([k, m.conventions[k]])));

  const all = head.concat([header], rows, tail);
  sh.getRange(1, 1, all.length, W).setValues(all);

  // --- wygląd --------------------------------------------------------------
  const top = CATALOG.HEADER_ROWS + 1;
  sh.getRange(1, 1).setFontSize(14).setFontWeight('bold');
  sh.getRange(2, 1, CATALOG.HEADER_ROWS - 2, 1).setFontWeight('bold').setFontColor('#5f6368');
  sh.getRange(top, 1, 1, W).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff')
    .setWrap(true).setVerticalAlignment('middle');
  sh.setFrozenRows(top);
  sh.setFrozenColumns(2);
  CATALOG_COLUMNS.forEach(([, , w], i) => sh.setColumnWidth(i + 1, w));
  const body = sh.getRange(top + 1, 1, rows.length, W);
  body.setVerticalAlignment('top').setFontSize(9);
  sh.getRange(top + 1, 6, rows.length, 1).setWrap(true);                     // definicja
  sh.getRange(top + 1, 7, rows.length, 1).setWrap(true).setFontFamily('Roboto Mono');
  sh.getRange(top + 1, W, rows.length, 1).setBackground('#fffde7').setWrap(true);   // uwagi — edytowalne

  // Kolor pasa według kategorii: czytelny podział na 8 hipotez (1.2).
  const bg = cat.signals.map(s => {
    const c = CATALOG_CAT_COLORS[s.category] || '#ffffff';
    return CATALOG_COLUMNS.map((col, i) => (i === W - 1 ? '#fffde7' : c));
  });
  body.setBackgrounds(bg);
  cat.signals.forEach((s, i) => {
    if (s.status !== 'aktywny') sh.getRange(top + 1 + i, 1, 1, W - 1).setFontColor('#9aa0a6');
  });

  const tailStart = top + rows.length + 2;
  sh.getRange(tailStart, 1).setFontWeight('bold');
  sh.getRange(tailStart + 6, 1).setFontWeight('bold');
  return rows.length;
}

/** Uwagi wpisane ręcznie w bieżącym arkuszu, po ID sygnału. */
function catalogReadNotes_(sh) {
  const last = sh.getLastRow();
  const lastCol = sh.getLastColumn();
  if (last < 2 || lastCol < 2) return {};
  const values = sh.getRange(1, 1, last, lastCol).getValues();
  let hdr = -1, col = -1;
  for (let r = 0; r < values.length && hdr < 0; r++) {
    if (values[r][0] === 'ID') { hdr = r; col = values[r].indexOf('Uwagi'); }
  }
  if (hdr < 0 || col < 0) return {};
  const out = {};
  for (let r = hdr + 1; r < values.length; r++) {
    const id = String(values[r][0] || '');
    if (/^S\d{3}$/.test(id) && values[r][col] !== '') out[id] = values[r][col];
  }
  return out;
}
