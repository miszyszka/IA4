/**
 * ============================================================================
 *  IA 4 — STRATEGIE  (GitHub, branch `research` → arkusze STRATEGIE i BACKTEST PORTFELA)
 *
 *  Wersja projektu: 1.17 (2026-10-07) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Trigger researchSync (co 30 min) i menu „Odśwież STRATEGIE teraz”:
 *   • STRATEGIE — wszystkie strategie aktywne w kolejności pierwszeństwa: wynik
 *     z backtestu doubleProof, szacunek przewagi z backtestu portfela, wynik na
 *     żywo w wirtualnym inwestorze, checkbox „for VI” (instrukcja, sekcja 11),
 *   • BACKTEST PORTFELA — tylko przy nowym pliku backtestu portfela,
 *   • Script Properties: ACTIVE_IDS i PRIORITY dla paper tradingu.
 *  Tylko odczyt z GitHub — ten sam token co telemetria (GITHUB_TOKEN).
 * ============================================================================
 */

const RESEARCH = {
  BRANCH: 'research',
  INDEX: 'research/strategies.jsonl',             // indeks strategii aktywnych
  BT: 'research/backtest-doubleproof.json',       // jednorazowy backtest na doubleProof (sekcja 6a)
  PF: 'research/portfolio-backtest.json',         // jednorazowy backtest portfela (sekcja 6b)
  STRAT_SHEET: 'STRATEGIE',
  PF_SHEET: 'BACKTEST PORTFELA',
};

/** Handler triggera co 30 min — NIE zmieniaj nazwy. */
function researchSync() { researchUpdate_(false); }

function researchSyncNow() {
  const r = researchUpdate_(true);
  toast_(r.ok ? 'STRATEGIE odświeżone.' : 'STRATEGIE: ' + r.reason);
}

function researchUpdate_(interactive) {
  try {
    const parse = txt => (txt || '').split('\n').filter(l => l.trim())
      .map(l => { try { return JSON.parse(l); } catch (e) { return null; } }).filter(x => x);
    const idx = parse(researchRaw_(RESEARCH.INDEX));
    if (!idx.length) return { ok: false, reason: 'brak research/strategies.jsonl' };
    const btTxt = researchRaw_(RESEARCH.BT);
    const pf = pfSync_();
    paperListsSave_(idx, pf);
    strategiesWrite_(idx, btTxt ? JSON.parse(btTxt) : null, pf);
    return { ok: true };
  } catch (e) {
    console.error('STRATEGIE: ' + e.message);
    if (interactive) throw e;
    return { ok: false, reason: e.message };
  }
}

/**
 * Lista strategii aktywnych i ich pierwszeństwo dla paper tradingu (Script Properties).
 * Pierwszeństwo: lista `priority` z backtestu portfela (instrukcja 6b); bez niego — PF ważony.
 */
function paperListsSave_(idx, pf) {
  const props = PropertiesService.getScriptProperties();
  props.setProperty('ACTIVE_IDS', JSON.stringify(idx.map(s => s.id)));
  const byPf = idx.slice().sort((a, b) => (b.pf_w || 0) - (a.pf_w || 0)).map(s => s.id);
  const pri = (pf && pf.priority) ? pf.priority.concat(byPf.filter(id => pf.priority.indexOf(id) < 0)) : byPf;
  props.setProperty('PRIORITY', JSON.stringify(pri));
}

/** Surowa treść pliku z brancha research (null = brak pliku/brancha). */
function researchRaw_(path) {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('brak tokenu GitHub (menu IA 4 → Ustaw token GitHub)');
  const resp = UrlFetchApp.fetch(
    `https://api.github.com/repos/${TELEMETRY.REPO}/contents/${path}?ref=${RESEARCH.BRANCH}`, {
      muteHttpExceptions: true,
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github.raw' },
    });
  const code = resp.getResponseCode();
  if (code === 404) return null;
  if (code !== 200) throw new Error(`GitHub HTTP ${code} (${path})`);
  return resp.getContentText('UTF-8');
}


// ============================================================================
//  ARKUSZ STRATEGIE — jeden arkusz o strategiach (instrukcja, sekcja 11)
// ============================================================================
const S_COLS = ['Id', 'Miejsce', 'Wybrana', 'Grupa', 'Opis (reguła)', 'SL %', 'TP %',
  'PF doubleProof', 'Transakcji doubleProof', 'Śr. wynik doubleProof %', 'Szacunek przewagi %',
  'Skuteczność TP (doubleProof)', 'Mediana świec w pozycji (doubleProof)',
  'VI: zamkniętych', 'VI: śr. wynik %', 'VI: wynik $', 'VI: otwarte', 'PF ważony (poszukiwanie)'];
const S_VI_HEAD = 'for VI';
const S_VI_COL = S_COLS.length + 1;          // ostatnia kolumna: checkbox dla wirtualnego inwestora
const S_ID_RE = /^S-[0-9a-f]{10}$/;

/**
 * Strategie zaznaczone „for VI” (instrukcja 11a). Czyta checkboxy z arkusza STRATEGIE i zapamiętuje
 * je w Script Properties (VI_IDS), bo arkusz jest przepisywany w całości. Id jest zawsze w kolumnie A.
 */
function viSelectedIds_() {
  const props = PropertiesService.getScriptProperties();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sel = JSON.parse(props.getProperty('VI_IDS') || '[]');
  const sh = ss.getSheetByName(RESEARCH.STRAT_SHEET);
  if (sh && sh.getRange(2, S_VI_COL).getValue() === S_VI_HEAD && sh.getLastRow() > 2) {
    const set = new Set(sel);
    sh.getRange(3, 1, sh.getLastRow() - 2, S_VI_COL).getValues().forEach(r => {
      const id = String(r[0] || '').trim();
      if (!S_ID_RE.test(id)) return;
      if (r[S_VI_COL - 1] === true) set.add(id); else set.delete(id);
    });
    sel = Array.from(set);
  }
  props.setProperty('VI_IDS', JSON.stringify(sel));
  return sel;
}

function strategiesWrite_(idx, bt, pf) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sel = viSelectedIds_();                  // PRZED przepisaniem — zachowuje checkboxy
  const selSet = {};
  sel.forEach(id => { selSet[id] = 1; });
  const btBy = {};
  ((bt && bt.results) || []).forEach(r => { btBy[r.id] = r; });
  const rank = {};
  ((pf && pf.selection && pf.selection.ranking) || []).forEach((r, i) => { rank[r.id] = Object.assign({ place: i + 1 }, r); });
  const vi = JSON.parse(PropertiesService.getScriptProperties().getProperty('VI_BY_STRAT') || '{}');

  const list = idx.map(s => ({ id: s.id, group: s.group, desc: s.desc, sl: s.sl, tp: s.tp, pf_w: s.pf_w }));
  list.sort((a, b) => ((rank[a.id] || {}).place || 999) - ((rank[b.id] || {}).place || 999) || (b.pf_w || 0) - (a.pf_w || 0));
  const shown = {};
  list.forEach(s => { shown[s.id] = 1; });
  sel.filter(id => !shown[id]).forEach(id => {     // zaznaczone, ale już nieaktywne — na dole
    list.push({ id, group: '(archiwum)', desc: 'strategia spoza aktywnych — odznacz „for VI”, jeśli niepotrzebna' });
  });

  const v = x => (x === undefined || x === null) ? '' : x;
  const rows = list.map(s => {
    const b = btBy[s.id] || {}, r = rank[s.id] || {}, w = vi[s.id] || {};
    return [s.id, v(r.place), r.selected ? '✓' : '', v(s.group), v(s.desc), v(s.sl), v(s.tp),
      b.trades ? b.pf : '', v(b.trades), b.trades ? b.avg_ret_pct / 100 : '',
      r.shrunk_pct !== undefined ? r.shrunk_pct / 100 : '', b.trades ? b.tp_pct : '', v(b.hold_median),
      v(w.n), w.n ? w.sum / w.n / 100 : '', w.n ? Math.round(w.usd * 100) / 100 : '', v(w.open), v(s.pf_w),
      !!selSet[s.id]];
  });

  const sh = ss.getSheetByName(RESEARCH.STRAT_SHEET) || ss.insertSheet(RESEARCH.STRAT_SHEET);
  sh.clear();
  sh.clearConditionalFormatRules();
  sh.getRange(1, 1, sh.getMaxRows(), sh.getMaxColumns()).clearDataValidations();
  sh.setTabColor('#e37400');
  if (sh.getMaxColumns() < S_VI_COL) sh.insertColumnsAfter(sh.getMaxColumns(), S_VI_COL - sh.getMaxColumns());
  const nSel = Object.keys(rank).filter(id => rank[id].selected).length;
  sh.getRange(1, 1, 1, 10).merge()
    .setValue(`IA 4 — STRATEGIE: ${idx.length} aktywnych · wybranych w backteście portfela: ${nSel} · for VI: ${sel.length} · ` +
      Utilities.formatDate(new Date(), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm'))
    .setFontSize(13).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(2, 1, 1, S_VI_COL).setValues([S_COLS.concat([S_VI_HEAD])])
    .setFontWeight('bold').setBackground('#f1f3f4').setWrap(true).setVerticalAlignment('middle');
  sh.getRange(2, 8, 1, 6).setBackground('#e8f0fe');             // backtest doubleProof
  sh.getRange(2, 14, 1, 4).setBackground('#fef7e0');            // na żywo
  sh.getRange(2, S_VI_COL).setBackground('#ceead6');
  if (rows.length) {
    const need = rows.length + 2;
    if (sh.getMaxRows() < need) sh.insertRowsAfter(sh.getMaxRows(), need - sh.getMaxRows());
    sh.getRange(3, 1, rows.length, S_VI_COL).setValues(rows);
    sh.getRange(3, S_VI_COL, rows.length, 1).insertCheckboxes();
    sh.getRange(3, S_VI_COL, rows.length, 1).setValues(rows.map(r => [r[S_VI_COL - 1]]));
    [8, 18].forEach(c => sh.getRange(3, c, rows.length, 1).setNumberFormat('0.00'));
    [10, 11, 15].forEach(c => sh.getRange(3, c, rows.length, 1).setNumberFormat('+0.00%;-0.00%;0.00%'));
    sh.getRange(3, 12, rows.length, 1).setNumberFormat('0%');
    sh.getRange(3, 16, rows.length, 1).setNumberFormat('+0.00;-0.00;0.00');
    const rule = () => SpreadsheetApp.newConditionalFormatRule();
    const pfR = sh.getRange(3, 8, rows.length, 1), viR = sh.getRange(3, 15, rows.length, 1);
    sh.setConditionalFormatRules([
      rule().whenNumberGreaterThanOrEqualTo(1.5).setBackground('#ceead6').setRanges([pfR]).build(),
      rule().whenNumberLessThan(1).setBackground('#fad2cf').setRanges([pfR]).build(),
      rule().whenNumberBetween(1, 1.5).setBackground('#fef7e0').setRanges([pfR]).build(),
      rule().whenNumberGreaterThan(0).setFontColor('#188038').setRanges([viR]).build(),
      rule().whenNumberLessThan(0).setFontColor('#c5221f').setRanges([viR]).build(),
    ]);
  }
  sh.setFrozenRows(2);
  sh.setFrozenColumns(1);
  sh.setColumnWidth(1, 110);
  sh.setColumnWidths(2, 2, 70);
  sh.setColumnWidth(4, 120);
  sh.setColumnWidth(5, 520);
}

/** Menu: „for VI” = strategie wybrane w backteście portfela (pozostałe odznaczone). */
function viSelectFromBacktest() {
  const txt = researchRaw_(RESEARCH.PF);
  if (!txt) { alert_('Brak backtestu portfela (python -m ia4.lab.portfolio na Macu).'); return; }
  const ids = JSON.parse(txt).selection.ranking.filter(r => r.selected).map(r => r.id);
  const ui = SpreadsheetApp.getUi();
  if (ui.alert(`Zaznaczyć „for VI” dokładnie ${ids.length} strategii wybranych w backteście portfela ` +
      '(wszystkie inne zostaną odznaczone)?', ui.ButtonSet.OK_CANCEL) !== ui.Button.OK) return;
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Automat właśnie pracuje — spróbuj za minutę.'); return; }
  try {
    const set = {};
    ids.forEach(id => { set[id] = 1; });
    const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(RESEARCH.STRAT_SHEET);
    if (sh && sh.getRange(2, S_VI_COL).getValue() === S_VI_HEAD && sh.getLastRow() > 2) {
      const n = sh.getLastRow() - 2;
      sh.getRange(3, S_VI_COL, n, 1).setValues(sh.getRange(3, 1, n, 1).getValues().map(r => [!!set[String(r[0]).trim()]]));
    }
    PropertiesService.getScriptProperties().setProperty('VI_IDS', JSON.stringify(ids));
    researchUpdate_(true);
    toast_(`for VI: ${ids.length} strategii.`);
  } finally { lock.releaseLock(); }
}


// ============================================================================
//  ARKUSZ BACKTEST PORTFELA — jednorazowy backtest wirtualnego inwestora na
//  historii (research/portfolio-backtest.json, instrukcja 6b). Powstaje tylko
//  przy nowym pliku (createdAt w BT_PF_AT); usunięty ręcznie — nie wraca, dopóki
//  nie pojawi się nowy backtest. Tylko do odczytu.
// ============================================================================
const PF_COLS = ['Wariant', 'Strategii', 'Zbiór', 'Transakcji', 'PF', 'Śr. wynik % (netto)', 'Wynik $',
  'Max obsunięcie $', 'Wynik / obsunięcie', 'Skuteczność (TP)', '% SL', '% FC', '% limit',
  'Mediana świec w pozycji', 'Wynik $ long', 'Wynik $ short', 'Transakcji long / short', 'Spółek'];

function pfSync_() {
  const txt = researchRaw_(RESEARCH.PF);
  if (txt === null) return null;
  const pf = JSON.parse(txt);
  const props = PropertiesService.getScriptProperties();
  if (props.getProperty('BT_PF_AT') !== pf.createdAt) {
    pfWrite_(pf);
    props.setProperty('BT_PF_AT', pf.createdAt);
  }
  return pf;
}

function pfWrite_(pf) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(RESEARCH.PF_SHEET) || ss.insertSheet(RESEARCH.PF_SHEET);
  sh.clear();
  sh.clearConditionalFormatRules();
  sh.setTabColor('#5f6368');
  const W = PF_COLS.length;
  if (sh.getMaxColumns() < W) sh.insertColumnsAfter(sh.getMaxColumns(), W - sh.getMaxColumns());
  const fmtD = x => x ? String(x).replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3') : '?';
  const d = pf.data || {}, pr = pf.params || {};
  const v = x => (x === undefined || x === null) ? '' : x;
  sh.getRange(1, 1, 1, W).merge()
    .setValue(`IA 4 — BACKTEST PORTFELA (jednorazowy, zapisany ${pf.createdAtPL}) · główna: ${d.main.instruments} spółek ` +
      `${fmtD(d.main.first_date)} – ${fmtD(d.main.last_date)} · doubleProof: ${d.dp.instruments} spółek ` +
      `${fmtD(d.dp.first_date)} – ${fmtD(d.dp.last_date)} · stawka ${pr.stake_usd} $, koszt ${pr.cost_pct_per_side}% za stronę`)
    .setFontSize(12).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(2, 1, 1, W).merge()
    .setValue('Uczciwy obraz daje doubleProof (spółki, których poszukiwanie nie widziało). Grupa główna i skarbiec ' +
      'są zawyżone — na nich strategie były wybierane. „Wybrane” wybrano wg doubleProof. Pierwszeństwo strategii: arkusz STRATEGIE.')
    .setFontStyle('italic').setWrap(true);
  sh.getRange(3, 1, 1, W).setValues([PF_COLS]).setFontWeight('bold').setBackground('#f1f3f4').setWrap(true);
  const names = { dp: 'doubleProof — całość', dp_fold1: 'doubleProof — okres 1', dp_fold2: 'doubleProof — okres 2',
                  dp_fold3: 'doubleProof — okres 3', dp_fold4: 'doubleProof — okres 4',
                  main: 'grupa główna (zawyżona)', vault: 'skarbiec (zawyżony)' };
  const rows = [];
  (pf.variants || []).forEach(vr => {
    Object.keys(names).forEach(u => {
      const x = (vr.universes || {})[u] || {};
      rows.push([vr.name, vr.strategies, names[u], v(x.trades), v(x.pf), x.trades ? x.avg_ret_pct / 100 : '', v(x.sum_usd),
        v(x.max_dd_usd), v(x.ret_to_dd), x.trades ? x.tp_pct : '', x.trades ? x.sl_pct : '', x.trades ? x.fc_pct : '',
        x.trades ? x.time_pct : '', v(x.hold_median), v(x.sum_usd_long), v(x.sum_usd_short),
        x.trades ? `${x.trades_long} / ${x.trades_short}` : '', v(x.instruments)]);
    });
  });
  if (!rows.length) return;
  sh.getRange(4, 1, rows.length, W).setValues(rows);
  sh.getRange(4, 6, rows.length, 1).setNumberFormat('+0.00%;-0.00%;0.00%');
  sh.getRange(4, 10, rows.length, 4).setNumberFormat('0.0%');
  [5, 9].forEach(c => sh.getRange(4, c, rows.length, 1).setNumberFormat('0.00'));
  [7, 8, 15, 16].forEach(c => sh.getRange(4, c, rows.length, 1).setNumberFormat('#,##0.00'));
  for (let i = 0; i < rows.length; i += 7) sh.getRange(4 + i, 1, 1, W).setFontWeight('bold');
  const rule = () => SpreadsheetApp.newConditionalFormatRule();
  const usd = sh.getRange(4, 7, rows.length, 1);
  sh.setConditionalFormatRules([
    rule().whenNumberGreaterThan(0).setFontColor('#188038').setRanges([usd]).build(),
    rule().whenNumberLessThan(0).setFontColor('#c5221f').setRanges([usd]).build(),
  ]);
  sh.setFrozenRows(3);
  sh.setColumnWidth(1, 330);
  sh.setColumnWidth(3, 190);
}
