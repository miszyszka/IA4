/**
 * ============================================================================
 *  IA 4 — POSZUKIWANIE STRATEGII  (GitHub, branch `research` → arkusz RESEARCH)
 *
 *  Wersja projektu: 1.3 (2026-10-01) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Program `python -m ia4.lab` na Macu co 30 minut zapisuje na branchu
 *  `research` pliki research/status.json i research/log.jsonl. Ten plik co
 *  30 minut (trigger researchSync) czyta je i przepisuje do arkusza RESEARCH:
 *  stan, ostatnie znalezione strategie i dziennik (najnowsze na górze),
 *  a do arkusza STRATEGIE — wszystkie strategie aktywne z wynikami.
 *
 *  Tylko odczyt z GitHub — ten sam token co telemetria (GITHUB_TOKEN).
 * ============================================================================
 */

const RESEARCH = {
  BRANCH: 'research',
  STATUS: 'research/status.json',
  LOG: 'research/log.jsonl',
  INDEX: 'research/strategies.jsonl',   // indeks strategii aktywnych
  SHEET: 'RESEARCH',
  STRAT_SHEET: 'STRATEGIE',
  LOG_ROWS: 500,          // ile ostatnich wpisów dziennika pokazujemy
  STRAT_ROWS: 20,
  STALE_MIN: 45,          // brak nowego logu dłużej = program na Macu nie liczy
};

const R_STATUS_LABELS = [
  'Ostatni log (PL)', 'Program na Macu', 'Komputer', 'Etap poszukiwania', 'Reguł przetestowanych',
  'Hipotez SL/TP', 'Tempo (reguł/min)', 'Przeszło sito', 'Obiecujących (stabilne)', 'Duplikatów',
  'Otwarć skarbca', 'Strategii aktywnych', 'Przyjętych łącznie', 'Odrzuconych przez skarbiec',
  'Pominiętych (grupa pełna)', 'Przeniesionych do archiwum', 'Łączny czas pracy (h)',
  'Baza na Macu', 'Kryteria',
];
const R_FIRST = 3;
const R_STRAT_HEADER = R_FIRST + R_STATUS_LABELS.length + 2;
const R_LOG_HEADER = R_STRAT_HEADER + RESEARCH.STRAT_ROWS + 3;
const R_LOG_COLS = ['Czas (PL)', 'Komputer', 'Etap', 'Siatka %', 'Reguł', '+ reguł', 'Reguł/min',
  'Obiecujących', '+ obiec.', 'Skarbiec', '+ skarbiec', 'Strategii', '+ strategii',
  'Najlepszy wynik', 'Baza do', 'Baza OK', 'Uwagi'];
const R_STRAT_COLS = ['Id', 'Znaleziona', 'Opis', 'PF główna', 'PF na ślepo', 'PF skarbiec',
  'PF łącznie', 'Transakcji', 'Skuteczność'];

/** Handler triggera co 30 min — NIE zmieniaj nazwy. */
function researchSync() { researchUpdate_(false); }

function researchSyncNow() {
  const r = researchUpdate_(true);
  toast_(r.ok ? 'RESEARCH odświeżony.' : 'RESEARCH: ' + r.reason);
}

function researchUpdate_(interactive) {
  try {
    const statusTxt = researchRaw_(RESEARCH.STATUS);
    if (statusTxt === null) return { ok: false, reason: 'brak brancha research — program na Macu jeszcze nie działał' };
    const status = JSON.parse(statusTxt);
    const logTxt = researchRaw_(RESEARCH.LOG) || '';
    const log = logTxt.split('\n').filter(l => l.trim()).map(l => { try { return JSON.parse(l); } catch (e) { return null; } })
      .filter(x => x).reverse().slice(0, RESEARCH.LOG_ROWS);
    researchWrite_(status, log);
    const idx = (researchRaw_(RESEARCH.INDEX) || '').split('\n').filter(l => l.trim())
      .map(l => { try { return JSON.parse(l); } catch (e) { return null; } }).filter(x => x);
    strategiesWrite_(idx);
    return { ok: true };
  } catch (e) {
    console.error('RESEARCH: ' + e.message);
    if (interactive) throw e;
    return { ok: false, reason: e.message };
  }
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

function researchSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(RESEARCH.SHEET);
  if (sh && sh.getRange(R_LOG_HEADER, 1).getValue() === R_LOG_COLS[0]) return sh;
  if (!sh) sh = ss.insertSheet(RESEARCH.SHEET);
  sh.clear();
  const need = R_LOG_HEADER + RESEARCH.LOG_ROWS + 1;
  if (sh.getMaxRows() < need) sh.insertRowsAfter(sh.getMaxRows(), need - sh.getMaxRows());
  if (sh.getMaxColumns() < R_LOG_COLS.length) sh.insertColumnsAfter(sh.getMaxColumns(), R_LOG_COLS.length - sh.getMaxColumns());
  sh.setTabColor('#188038');
  sh.getRange(1, 1, 1, 9).merge().setValue('IA 4 — POSZUKIWANIE STRATEGII')
    .setFontSize(14).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(R_FIRST, 1, R_STATUS_LABELS.length, 1).setValues(R_STATUS_LABELS.map(x => [x]))
    .setFontWeight('bold').setBackground('#f1f3f4');
  sh.getRange(R_FIRST, 2, R_STATUS_LABELS.length, 1).setNumberFormat('@');
  sh.getRange(R_STRAT_HEADER - 1, 1, 1, 9).merge().setValue('OSTATNIE AKTYWNE STRATEGIE (najnowsze na dole)')
    .setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(R_STRAT_HEADER, 1, 1, R_STRAT_COLS.length).setValues([R_STRAT_COLS]).setFontWeight('bold').setBackground('#f1f3f4');
  sh.getRange(R_LOG_HEADER - 1, 1, 1, 9).merge().setValue('DZIENNIK — co 30 minut pracy programu (najnowsze na górze)')
    .setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(R_LOG_HEADER, 1, 1, R_LOG_COLS.length).setValues([R_LOG_COLS]).setFontWeight('bold').setBackground('#f1f3f4');
  sh.setColumnWidth(1, 210);
  sh.setColumnWidth(2, 150);
  sh.setColumnWidth(3, 420);
  sh.setFrozenRows(1);
  return sh;
}

function researchWrite_(st, log) {
  const sh = researchSheet_();
  const t = st.totals || {};
  const lastAt = st.updatedAt ? new Date(st.updatedAt) : null;
  const staleMin = lastAt ? (Date.now() - lastAt.getTime()) / 60000 : 1e9;
  const running = staleMin <= RESEARCH.STALE_MIN && st.note !== 'zatrzymano' && st.note !== 'koniec zadanego czasu';
  const g = st.grid || {};
  const chk = (st.data && st.data.check) || {};
  const c = st.config || {};
  const n = x => (x === undefined || x === null) ? '' : Number(x).toLocaleString('pl-PL');
  sh.getRange(R_FIRST, 2, R_STATUS_LABELS.length, 1).setValues([
    [st.updatedAtPL || '—'],
    [running ? `✓ liczy (od ${st.run ? st.run.startedAtPL : '?'})` : `⏸ nie liczy — ostatni log ${Math.round(staleMin)} min temu${st.note ? ' (' + st.note + ')' : ''}`],
    [`${st.host || '?'} · procesów ${st.workers || '?'}`],
    [st.phase === 'siatka' ? `siatka ${g.pct}% (${n(g.cursor)} / ${n(g.total)})` : 'adaptacja (siatka zakończona)'],
    [n(t.evals)], [n(t.hypotheses)],
    [st.run ? n(st.run.evals_per_min) : ''],
    [n(t.eligible)], [n(t.promising)], [n(t.duplicates)], [n(t.vault_peeks)],
    [st.active_strategies !== undefined ? `${n(st.active_strategies)} (najwyżej ${c.max_per_group || '?'} w grupie)` : n(t.accepted)],
    [n(t.accepted)], [n(t.rejected_vault)], [n(t.group_full || 0)], [n(t.archived || 0)],
    [t.run_minutes ? (t.run_minutes / 60).toFixed(1) : '0'],
    [st.data ? `${st.data.instruments} instr., ${n(st.data.candles)} świec, do ${st.data.last_date}` +
      (chk.ok ? ' · kompletna' : ` · braki: sesji ${chk.missing_sessions || 0}, niepełnych ${chk.incomplete_sessions || 0}, nieaktualnych ${chk.stale || 0}`) : ''],
    [`PF ≥ ${c.pf_min} (główna i łącznie), skarbiec PF ≥ ${c.vault_pf_min}, transakcji ≥ ${c.min_trades_main} + skarbiec ≥ ${c.min_trades_vault}, ` +
      `okresy ≥ ${c.folds_min_ok}/4, przewaga ≥ ${c.pf_edge_min}` +
      (c.tp_sl_ratio ? `, TP/SL ${Number(c.tp_sl_ratio[0]).toFixed(2)}–${c.tp_sl_ratio[1]}` : '')],
  ]);

  const strat = (st.recent_strategies || []).slice(-RESEARCH.STRAT_ROWS).map(s => [
    s.id, s.found_at ? Utilities.formatDate(new Date(s.found_at), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm') : '',
    s.desc, s.main_pf, s.blind_pf !== undefined ? s.blind_pf : '', s.vault_pf, s.combined_pf, s.trades,
    s.win_rate !== undefined ? s.win_rate : '']);
  while (strat.length < RESEARCH.STRAT_ROWS) strat.push(R_STRAT_COLS.map(() => ''));
  sh.getRange(R_STRAT_HEADER + 1, 1, RESEARCH.STRAT_ROWS, R_STRAT_COLS.length).setValues(strat);
  sh.getRange(R_STRAT_HEADER + 1, 9, RESEARCH.STRAT_ROWS, 1).setNumberFormat('0.0%');

  const rows = log.map(e => [e.atPL, e.host || '', e.phase, e.grid_pct, e.evals, e.evals_delta, e.evals_per_min,
    e.promising, e.promising_delta, e.vault_peeks, e.vault_delta, e.accepted, e.accepted_delta,
    e.best_score, String(e.data_last || ''), e.data_ok ? '✓' : '✗', e.note || '']);
  const range = sh.getRange(R_LOG_HEADER + 1, 1, RESEARCH.LOG_ROWS, R_LOG_COLS.length);
  range.clearContent();
  if (rows.length) sh.getRange(R_LOG_HEADER + 1, 1, rows.length, R_LOG_COLS.length).setValues(rows);
}


// ============================================================================
//  ARKUSZ STRATEGIE — wszystkie strategie aktywne (research/strategies.jsonl),
//  od najwyższego PF łącznego. Przepisywany w całości przy każdym odświeżeniu.
// ============================================================================
const S_COLS = ['Id', 'Grupa', 'Kierunek', 'Opis (reguła)', 'PF główna', 'PF na ślepo', 'Przewaga',
  'PF skarbiec', 'PF łącznie', 'Transakcji', 'Skuteczność', 'Znaleziona'];

function strategiesWrite_(idx) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(RESEARCH.STRAT_SHEET) || ss.insertSheet(RESEARCH.STRAT_SHEET);
  sh.clear();
  sh.setTabColor('#e37400');
  const rows = idx.slice().sort((a, b) => (b.combined_pf || 0) - (a.combined_pf || 0)).map(s => [
    s.id, s.group || '', /^SHORT/.test(s.desc || '') ? 'short' : 'long', s.desc || '',
    s.main_pf, s.blind_pf !== undefined && s.blind_pf !== null ? s.blind_pf : '',
    s.edge !== undefined && s.edge !== null ? s.edge : '', s.vault_pf, s.combined_pf, s.trades,
    s.win_rate !== undefined ? s.win_rate : '',
    s.found_at ? Utilities.formatDate(new Date(s.found_at), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm') : '']);
  sh.getRange(1, 1, 1, S_COLS.length).merge()
    .setValue(`IA 4 — STRATEGIE AKTYWNE: ${rows.length} (od najwyższego PF łącznego) · ` +
      Utilities.formatDate(new Date(), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm'))
    .setFontSize(13).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(2, 1, 1, S_COLS.length).setValues([S_COLS]).setFontWeight('bold').setBackground('#f1f3f4');
  if (rows.length) {
    const need = rows.length + 2;
    if (sh.getMaxRows() < need) sh.insertRowsAfter(sh.getMaxRows(), need - sh.getMaxRows());
    sh.getRange(3, 1, rows.length, S_COLS.length).setValues(rows);
    sh.getRange(3, 5, rows.length, 5).setNumberFormat('0.00');
    sh.getRange(3, 11, rows.length, 1).setNumberFormat('0.0%');
  }
  sh.setFrozenRows(2);
  sh.setColumnWidth(1, 110);
  sh.setColumnWidth(2, 170);
  sh.setColumnWidth(4, 560);
}
