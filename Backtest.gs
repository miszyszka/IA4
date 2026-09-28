/**
 * ============================================================================
 *  IA 4 — S1-BACKTEST  (s1-backtest/results.csv z GitHub → arkusz S1-BACKTEST)
 *
 *  Wersja projektu: 0.32 (2026-09-28) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  PO CO TO JEST
 *  Etap 2 liczy w Pythonie (na Macu) wszystkie 57 200 strategii S1, osobno
 *  na grupie głównej i kontrolnej (instrukcja 2.1–2.2), i zapisuje pełny
 *  wynik do jednego pliku: s1-backtest/results.csv w repozytorium.
 *
 *  Ten plik go WCZYTUJE. To NIE jest odświeżany widok jak arkusz S1
 *  (Catalog.gs) — to jednorazowy zrzut jednego przebiegu (2.3). Uruchomienie
 *  tej samej pozycji menu drugi raz po prostu nadpisuje arkusz od zera,
 *  jeśli w międzyczasie Python policzył poprawkę.
 *
 *  Arkusz S1-BACKTEST jest celowo ogromny (D22, L25) — to jedyne miejsce,
 *  gdzie widać wszystkie policzone strategie naraz. Z niego, ręcznie,
 *  wybiera się 10–50 strategii do S2 (2.4): ten plik dokleja na końcu
 *  kolumnę „Wybrana” (checkbox) właśnie do tego celu. Zaznaczenie w niej
 *  NIE zapisuje się nigdzie automatycznie — o przeniesienie zaznaczonych
 *  wierszy do `s2/strategies.json` prosi się Claude wprost (D18: do repo
 *  piszą tylko Python i Claude, nie Apps Script).
 *
 *  Kolumny CSV nie są tu na sztywno wpisane (w odróżnieniu od Catalog.gs):
 *  ten loader jest celowo "głupi" — bierze nagłówek i wiersze takie, jakie
 *  są w pliku, i kładzie je do arkusza. Dzięki temu nie trzeba nic zmieniać
 *  w Apps Script, gdy w Pythonie dojdzie albo zmieni się kolumna wyniku.
 * ============================================================================
 */

const BACKTEST = {
  SHEET: 'S1-BACKTEST',
  PATH: 's1-backtest/results.csv',
  PROP: 'S1_BACKTEST',
  WRITE_CHUNK: 5000,     // wierszy na jedno setValues — jedno wywołanie na 57 200 byłoby zbyt duże/wolne
};

/** Menu: IA 4 → Projekt → Wczytaj wyniki S1-BACKTEST z GitHub (jednorazowo). */
function backtestLoadS1() {
  const ui = SpreadsheetApp.getUi();
  const existing = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(BACKTEST.SHEET);
  if (existing) {
    const resp = ui.alert('Arkusz S1-BACKTEST już istnieje',
      'Wczytanie nadpisze cały arkusz S1-BACKTEST od zera (łącznie z zaznaczeniami w kolumnie „Wybrana”, ' +
      'jeśli ktoś już coś zaznaczył). Jeśli wybór strategii do S2 jest w toku, najpierw go zabezpiecz.\n\n' +
      'Wczytać mimo to?', ui.ButtonSet.YES_NO);
    if (resp !== ui.Button.YES) return;
  }

  let data;
  try {
    data = backtestFetch_();
  } catch (e) {
    alert_('Nie udało się wczytać wyników S1-BACKTEST.\n\n' + e.message);
    return;
  }

  toast_(`S1-BACKTEST: pobrano ${data.rows.length} strategii, ${data.header.length} kolumn. Zapisuję do arkusza…`);
  const n = backtestRender_(data);

  PropertiesService.getScriptProperties().setProperty(BACKTEST.PROP, JSON.stringify({
    sha: data.sha, path: BACKTEST.PATH, rows: n, columns: data.header.length,
    loadedAt: new Date().toISOString(),
  }));
  toast_(`S1-BACKTEST wczytany: ${n} strategii, ${data.header.length} kolumn (commit ${data.sha || '?'}).`);
}

/**
 * Pobiera s1-backtest/results.csv z repozytorium jako surowy tekst (jak
 * catalogFetch_ w Catalog.gs — działa też dla plików znacznie większych
 * niż 1 MB, dzięki Accept: application/vnd.github.raw+json).
 * Osobnym, tanim zapytaniem doczytuje sha ostatniego commitu, który
 * dotknął tego pliku — tylko do nagłówka w arkuszu, nic więcej.
 */
function backtestFetch_() {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('Brak tokenu GitHub. Ustaw go: IA 4 → Telemetria → Ustaw token GitHub.');
  const auth = { Authorization: 'Bearer ' + token };

  let sha = '';
  try {
    const cUrl = `https://api.github.com/repos/${TELEMETRY.REPO}/commits` +
      `?path=${encodeURIComponent(BACKTEST.PATH)}&sha=${TELEMETRY.BRANCH}&per_page=1`;
    const cResp = UrlFetchApp.fetch(cUrl, { muteHttpExceptions: true, headers: auth });
    if (cResp.getResponseCode() === 200) {
      const arr = JSON.parse(cResp.getContentText('UTF-8'));
      if (arr.length) sha = String(arr[0].sha).slice(0, 7);
    }
  } catch (e) {
    // nieistotne — sha trafia tylko do nagłówka arkusza, brak nie blokuje wczytania
  }

  const url = `https://api.github.com/repos/${TELEMETRY.REPO}/contents/${BACKTEST.PATH}?ref=${TELEMETRY.BRANCH}`;
  const resp = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    headers: Object.assign({}, auth, { Accept: 'application/vnd.github.raw+json' }),
  });
  const code = resp.getResponseCode();
  if (code === 404) {
    throw new Error(`W repozytorium nie ma pliku ${BACKTEST.PATH}.\n` +
      'Etap 2 (backtest w Pythonie) musi go najpierw policzyć i zcommitować.');
  }
  if (code !== 200) throw new Error(`GitHub HTTP ${code}.`);

  const text = resp.getContentText('UTF-8');
  const table = Utilities.parseCsv(text);
  if (!table.length) throw new Error('Plik CSV jest pusty.');
  const header = table[0];
  const rows = table.slice(1);
  if (!rows.length) throw new Error('Plik CSV nie ma żadnych wierszy z danymi (sam nagłówek).');
  return { header, rows, sha };
}

/** Buduje arkusz S1-BACKTEST od zera. Zwraca liczbę wczytanych strategii. */
function backtestRender_(data) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(BACKTEST.SHEET);
  if (!sh) { sh = ss.insertSheet(BACKTEST.SHEET); } else { sh.clear(); sh.clearFormats(); }
  sh.setTabColor('#d93025');

  const W = data.header.length + 1;                          // +1: kolumna "Wybrana" doklejana tutaj
  const headerRow = data.header.concat(['Wybrana']);
  const HEAD_ROWS = 4;

  const meta = [
    ['WYNIKI BACKTESTU S1 — arkusz S1-BACKTEST (Etap 2, instrukcja 2.3)'],
    [`Strategii: ${data.rows.length}`, `Kolumn: ${data.header.length}`,
      `Plik: ${BACKTEST.PATH}`, `Commit: ${data.sha || '?'}`,
      `Wczytano: ${Utilities.formatDate(new Date(), 'Europe/Warsaw', 'yyyy-MM-dd HH:mm')}`],
    ['Widok jednorazowy — ponowne wczytanie z tej samej pozycji menu nadpisuje cały arkusz od zera.'],
    ['Zaznacz „Wybrana” przy strategiach do S2 (10–50, 2.4), potem poproś Claude o zapisanie ich do s2/strategies.json.'],
  ];
  const padTo = r => r.concat(new Array(Math.max(0, W - r.length)).fill(''));
  const head = meta.map(padTo);

  const startRow = HEAD_ROWS + 1;
  sh.getRange(1, 1, HEAD_ROWS, W).setValues(head);
  sh.getRange(startRow, 1, 1, W).setValues([headerRow]);

  // Zapis w kawałkach: jedno setValues na 57 200 wierszy byłoby jedną wielką,
  // wolną operacją — po WRITE_CHUNK naraz jest szybciej i bezpieczniej
  // mieścić się w limicie czasu jednego uruchomienia.
  for (let i = 0; i < data.rows.length; i += BACKTEST.WRITE_CHUNK) {
    const slice = data.rows.slice(i, i + BACKTEST.WRITE_CHUNK).map(r => padTo(r.concat([''])));
    sh.getRange(startRow + 1 + i, 1, slice.length, W).setValues(slice);
  }

  // --- wygląd (minimalny — to arkusz roboczy do filtrowania, nie widok jak S1) ---
  sh.getRange(1, 1).setFontSize(13).setFontWeight('bold');
  sh.getRange(2, 1, HEAD_ROWS - 1, 1).setFontColor('#5f6368');
  sh.getRange(startRow, 1, 1, W).setFontWeight('bold').setBackground('#202124')
    .setFontColor('#ffffff').setWrap(true).setVerticalAlignment('middle');
  sh.setFrozenRows(startRow);
  sh.setFrozenColumns(1);
  if (data.rows.length) {
    sh.getRange(startRow + 1, 1, data.rows.length, W).setVerticalAlignment('top').setFontSize(9);
    sh.getRange(startRow + 1, W, data.rows.length, 1).insertCheckboxes();
    sh.getRange(startRow, 1, data.rows.length + 1, W).createFilter();
  }
  sh.autoResizeColumns(1, Math.min(W, 40));   // reszta zostaje na szerokości domyślnej — 50 kolumn nie trzeba wszystkich dopasowywać ręcznie

  return data.rows.length;
}

/**
 * Menu: IA 4 → Projekt → Przygotuj wybrane strategie do S2 (podgląd).
 * NIE zapisuje nic do GitHub (D18 — tylko Python/Claude piszą do repo).
 * Zbiera zaznaczone w arkuszu S1-BACKTEST wiersze i pokazuje je w oknie,
 * żeby dało się je skopiować do rozmowy z Claude z prośbą o zapisanie
 * `s2/strategies.json` — patrz instrukcja 2.4.
 */
function backtestPreviewSelection() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(BACKTEST.SHEET);
  if (!sh) { alert_('Brak arkusza S1-BACKTEST. Wczytaj go najpierw: IA 4 → Projekt → Wczytaj wyniki S1-BACKTEST z GitHub.'); return; }

  const last = sh.getLastRow();
  const lastCol = sh.getLastColumn();
  const values = sh.getRange(1, 1, last, lastCol).getValues();
  let headRow = -1;
  for (let r = 0; r < values.length; r++) {
    if (values[r][lastCol - 1] === 'Wybrana') { headRow = r; break; }
  }
  if (headRow < 0) { alert_('Nie znaleziono nagłówka z kolumną „Wybrana”. Wczytaj arkusz ponownie.'); return; }

  const header = values[headRow];
  const chosen = [];
  for (let r = headRow + 1; r < values.length; r++) {
    if (values[r][lastCol - 1] === true) chosen.push(values[r]);
  }
  if (!chosen.length) { toast_('Żadna strategia nie jest jeszcze zaznaczona w kolumnie „Wybrana”.'); return; }
  if (chosen.length < 10 || chosen.length > 50) {
    toast_(`Uwaga: zaznaczono ${chosen.length} strategii — instrukcja (2.4) mówi o 10–50. To nie blokada, tylko przypomnienie.`);
  }

  const csv = [header].concat(chosen).map(row => row.map(v => {
    const s = String(v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }).join(',')).join('\n');

  const html = HtmlService.createHtmlOutput(
    `<p>${chosen.length} strategii zaznaczonych do S2. Skopiuj poniższy CSV i wklej Claude z prośbą ` +
    `„zapisz to jako s2/strategies.json (Etap 2, D18)”:</p>` +
    `<textarea style="width:100%;height:350px;font-family:monospace;font-size:11px">${csv.replace(/</g, '&lt;')}</textarea>`
  ).setWidth(700).setHeight(450);
  SpreadsheetApp.getUi().showModalDialog(html, `Wybrane strategie → S2 (${chosen.length})`);
}
