/**
 * ============================================================================
 *  IA 4 — POSZUKIWANIE STRATEGII  (GitHub, branch `research` → arkusz RESEARCH)
 *
 *  Wersja projektu: 1.15 (2026-10-04) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Program `python -m ia4.lab` na Macu co 30 minut zapisuje na branchu
 *  `research` pliki research/status.json i research/log.jsonl. Ten plik co
 *  30 minut (trigger researchSync) czyta je i przepisuje do arkusza RESEARCH:
 *  stan, ostatnie znalezione strategie i dziennik (najnowsze na górze),
 *  a do arkusza STRATEGIE — wszystkie strategie aktywne z wynikami,
 *  do STRATEGIE DOUBLEPROOF — te same strategie przeliczone na doubleProof,
 *  do BACKTEST DOUBLEPROOF — zapisany jednorazowy backtest (raz, przy nowym pliku),
 *  do BACKTEST PORTFELA — zapisany backtest portfela (raz, przy nowym pliku).
 *  Zapisuje też w Script Properties listę strategii aktywnych (ACTIVE_IDS) i ich
 *  pierwszeństwo (PRIORITY) — paper trading nie pyta GitHuba przy każdej świecy.
 *
 *  Tylko odczyt z GitHub — ten sam token co telemetria (GITHUB_TOKEN).
 * ============================================================================
 */

const RESEARCH = {
  BRANCH: 'research',
  STATUS: 'research/status.json',
  LOG: 'research/log.jsonl',
  INDEX: 'research/strategies.jsonl',   // indeks strategii aktywnych
  DP: 'research/doubleproof.json',       // strategie przeliczone na doubleProof (Python, verify.py)
  DP_SHEET: 'STRATEGIE DOUBLEPROOF',
  BT: 'research/backtest-doubleproof.json',   // jednorazowy backtest na doubleProof (Python, backtest_dp.py)
  BT_SHEET: 'BACKTEST DOUBLEPROOF',
  PF: 'research/portfolio-backtest.json',     // jednorazowy backtest portfela (Python, portfolio.py)
  PF_SHEET: 'BACKTEST PORTFELA',
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
  'PF ważony', 'Transakcji', 'Skuteczność (TP)'];

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
    const dpTxt = researchRaw_(RESEARCH.DP);
    const dp = dpTxt ? JSON.parse(dpTxt) : null;
    const order = strategiesWrite_(idx, dp);
    dpWrite_(order, dp);
    btSync_();
    const pf = pfSync_();
    paperListsSave_(idx, pf);
    return { ok: true };
  } catch (e) {
    console.error('RESEARCH: ' + e.message);
    if (interactive) throw e;
    return { ok: false, reason: e.message };
  }
}

/**
 * Lista strategii aktywnych i ich pierwszeństwo dla paper tradingu (Script Properties).
 * Pierwszeństwo: lista `priority` z backtestu portfela (instrukcja 6b); bez niego — PF ważony.
 */
function paperListsSave_(idx, pf) {
  if (!idx.length) return;
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
  const running = staleMin <= RESEARCH.STALE_MIN && st.note !== 'zatrzymano' && st.note !== 'koniec zadanego czasu' && st.note !== 'poszukiwanie zamknięte';
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
    [`PF ≥ ${c.pf_min} (główna i ważony), skarbiec PF ≥ ${c.vault_pf_min}, transakcji ≥ ${c.min_trades_main} + skarbiec ≥ ${c.min_trades_vault}, ` +
      `okresy ≥ ${c.folds_min_ok}/4, przewaga ≥ ${c.pf_edge_min}` +
      (c.max_time_share !== undefined ? `, limit czasu ≤ ${Math.round(c.max_time_share * 100)}%` : '') +
      (c.min_tp_share ? `, TP ≥ ${Math.round(c.min_tp_share * 100)}%` : '') +
      (c.tp_sl_ratio ? `, TP/SL ${Number(c.tp_sl_ratio[0]).toFixed(2)}–${c.tp_sl_ratio[1]}` : '')],
  ]);

  const strat = (st.recent_strategies || []).slice(-RESEARCH.STRAT_ROWS).map(s => [
    s.id, s.found_at ? Utilities.formatDate(new Date(s.found_at), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm') : '',
    s.desc, s.main_pf, s.blind_pf !== undefined ? s.blind_pf : '', s.vault_pf,
    s.pf_w !== undefined ? s.pf_w : s.combined_pf, s.trades,
    s.tp_pct !== undefined ? s.tp_pct : '']);
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
//  od najwyższego PF ważonego. Przepisywany w całości przy każdym odświeżeniu.
// ============================================================================
const S_COLS = ['Id', 'Grupa', 'Kierunek', 'Opis (reguła)', 'SL %', 'TP %',
  'PF główna', 'Transakcji główna', 'PF skarbiec', 'Transakcji skarbiec', 'PF ważony',
  'PF na ślepo', 'Przewaga', 'Skuteczność (TP)', '% SL', '% FC', '% limit',
  'Śr. wynik FC %', 'Śr. wynik transakcji %', 'Mediana świec w pozycji', 'Znaleziona'];

const S_VI_HEAD = 'for VI';
const S_VI_COL = S_COLS.length + 1;          // ostatnia kolumna: checkbox dla wirtualnego inwestora
const S_ID_RE = /^S-[0-9a-f]{10}$/;

/**
 * Strategie zaznaczone „for VI” (instrukcja 11a). Czyta checkboxy z arkusza STRATEGIE i zapamiętuje
 * je w Script Properties (VI_IDS), bo arkusz jest co 30 min przepisywany w całości.
 * Pierwsze użycie przejmuje ID wpisane ręcznie w VIRTUAL-INVESTOR (wersje ≤ 1.9).
 */
function viSelectedIds_() {
  const props = PropertiesService.getScriptProperties();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sel = JSON.parse(props.getProperty('VI_IDS') || 'null');
  if (sel === null) {
    sel = [];
    const inv = ss.getSheetByName(PAPER.INVESTOR_SHEET);
    if (inv && String(inv.getRange(3, 1).getValue()).indexOf('wpisz') >= 0) {
      sel = inv.getRange(4, 1, 20, 1).getValues().map(r => String(r[0] || '').trim()).filter(x => S_ID_RE.test(x));
    }
  }
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

/** Wiersz indeksu z pełnego pliku strategii (dla zaznaczonych, które wypadły do archiwum). */
function strategySummaryFromRec_(rec) {
  const st = rec.stats || {}, m = st.main || {}, vv = st.vault || {}, c = st.combined || {}, ex = (rec.rule || {}).exit || {};
  const n = (m.trades || 0) + (vv.trades || 0);
  const cap = x => Math.min(x || 0, 10);
  const share = k => c.trades ? (c[k] || 0) / c.trades : '';
  const avg = st.exit_avg_ret_pct || {};
  return {
    id: rec.id, desc: rec.description, found_at: rec.found_at,
    group: `${rec.rule.signal.kind}|${rec.rule.direction} (archiwum)`,
    sl: ex.sl, tp: ex.tp, main_pf: m.pf, main_trades: m.trades, vault_pf: vv.pf, vault_trades: vv.trades,
    pf_w: n ? Math.round((m.trades * cap(m.pf) + vv.trades * cap(vv.pf)) / n * 1000) / 1000 : '',
    blind_pf: (st.blind_entry_main || {}).pf, edge: (rec.robustness || {}).edge_vs_blind_entry,
    tp_pct: share('tp'), sl_pct: share('sl'), fc_pct: share('fc'), time_pct: share('time'),
    fc_avg: avg.fc, avg_ret: avg.all !== undefined ? avg.all : c.avg_ret_pct,
  };
}

function strategiesWrite_(idx, dp) {
  const hold = {};
  ((dp && dp.results) || []).forEach(r => { if (r.search_hold_median !== undefined) hold[r.id] = r.search_hold_median; });
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sel = viSelectedIds_();                  // PRZED przepisaniem — zachowuje checkboxy
  const selSet = {};
  sel.forEach(id => { selSet[id] = 1; });
  const sh = ss.getSheetByName(RESEARCH.STRAT_SHEET) || ss.insertSheet(RESEARCH.STRAT_SHEET);
  sh.clear();
  sh.getRange(1, 1, sh.getMaxRows(), sh.getMaxColumns()).clearDataValidations();
  sh.setTabColor('#e37400');
  if (sh.getMaxColumns() < S_VI_COL) sh.insertColumnsAfter(sh.getMaxColumns(), S_VI_COL - sh.getMaxColumns());
  const v = x => (x === undefined || x === null) ? '' : x;
  const list = idx.slice().sort((a, b) => (b.pf_w || 0) - (a.pf_w || 0));
  const shown = {};
  list.forEach(s => { shown[s.id] = 1; });
  sel.filter(id => !shown[id]).forEach(id => {     // zaznaczone, ale już nieaktywne — na dole
    let txt = null;
    try { txt = researchRaw_(`research/archive/${id}.json`) || researchRaw_(`research/strategies/${id}.json`); }
    catch (e) { console.warn('STRATEGIE: ' + id + ' — ' + e.message); }
    if (txt) list.push(strategySummaryFromRec_(JSON.parse(txt)));
    else list.push({ id, desc: '✗ nie znaleziono pliku strategii', group: '' });
  });
  const rows = list.map(s => [
    s.id, v(s.group), /^SHORT/.test(s.desc || '') ? 'short' : 'long', v(s.desc), v(s.sl), v(s.tp),
    v(s.main_pf), v(s.main_trades), v(s.vault_pf), v(s.vault_trades), v(s.pf_w),
    v(s.blind_pf), v(s.edge), v(s.tp_pct), v(s.sl_pct), v(s.fc_pct), v(s.time_pct),
    v(s.fc_avg), v(s.avg_ret), v(hold[s.id]),
    s.found_at ? Utilities.formatDate(new Date(s.found_at), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm') : '',
    !!selSet[s.id]]);
  sh.getRange(1, 1, 1, S_COLS.length).merge()
    .setValue(`IA 4 — STRATEGIE AKTYWNE: ${idx.length} (od najwyższego PF ważonego) · for VI: ${sel.length} · ` +
      Utilities.formatDate(new Date(), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm'))
    .setFontSize(13).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(2, 1, 1, S_VI_COL).setValues([S_COLS.concat([S_VI_HEAD])]).setFontWeight('bold').setBackground('#f1f3f4');
  sh.getRange(2, S_VI_COL).setBackground('#ceead6');
  if (rows.length) {
    const need = rows.length + 2;
    if (sh.getMaxRows() < need) sh.insertRowsAfter(sh.getMaxRows(), need - sh.getMaxRows());
    sh.getRange(3, 1, rows.length, S_VI_COL).setValues(rows);
    sh.getRange(3, S_VI_COL, rows.length, 1).insertCheckboxes();
    sh.getRange(3, S_VI_COL, rows.length, 1).setValues(rows.map(r => [r[S_VI_COL - 1]]));
    [7, 9, 11, 12, 13].forEach(c => sh.getRange(3, c, rows.length, 1).setNumberFormat('0.00'));
    sh.getRange(3, 14, rows.length, 4).setNumberFormat('0.0%');
    sh.getRange(3, 18, rows.length, 2).setNumberFormat('+0.00;-0.00;0.00');
  }
  sh.setFrozenRows(2);
  sh.setColumnWidth(1, 110);
  sh.setColumnWidth(2, 170);
  sh.setColumnWidth(4, 560);
  return list.map(s => ({ id: s.id, desc: s.desc, group: s.group, pf_w: s.pf_w, vi: !!selSet[s.id] }));
}

// ============================================================================
//  ARKUSZ STRATEGIE DOUBLEPROOF — te same strategie i ta sama kolejność co w
//  STRATEGIE, policzone przez Pythona na 20 spółkach doubleProof (instrukcja 6a).
//  Tylko do odczytu; przepisywany w całości przy każdym odświeżeniu.
// ============================================================================
const DP_COLS = ['Id', 'Grupa', 'Opis (reguła)', 'SL %', 'TP %', 'for VI',
  'PF ważony (poszukiwanie)', 'PF doubleProof', 'Transakcji', 'Mediana świec w pozycji', 'Spółek z transakcjami', 'Spółek z PF > 1',
  'Okresy z PF > 1 (z 4)', 'PF na ślepo', 'Przewaga', 'Skuteczność (TP)', '% SL', '% FC', '% limit',
  'Śr. wynik FC %', 'Śr. wynik transakcji %', 'Stan'];

function dpWrite_(order, dp) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(RESEARCH.DP_SHEET) || ss.insertSheet(RESEARCH.DP_SHEET);
  sh.clear();
  sh.clearConditionalFormatRules();
  sh.setTabColor('#a50e0e');
  if (sh.getMaxColumns() < DP_COLS.length) sh.insertColumnsAfter(sh.getMaxColumns(), DP_COLS.length - sh.getMaxColumns());
  const v = x => (x === undefined || x === null) ? '' : x;
  const res = {};
  ((dp && dp.results) || []).forEach(r => { res[r.id] = r; });
  const d = (dp && dp.data) || {};
  const fmtD = x => x ? String(x).replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3') : '?';
  const title = dp
    ? `IA 4 — STRATEGIE NA doubleProof: ${d.instruments} spółek, ${fmtD(d.first_date)} – ${fmtD(d.last_date)} · przeliczono ${dp.updatedAtPL}`
    : 'IA 4 — STRATEGIE NA doubleProof: brak wyników — uruchom program na Macu (ia4) po synchronizacji doubleProof';
  sh.getRange(1, 1, 1, DP_COLS.length).merge().setValue(title)
    .setFontSize(13).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(2, 1, 1, DP_COLS.length).setValues([DP_COLS]).setFontWeight('bold').setBackground('#f1f3f4');
  const rows = order.map(s => {
    const r = res[s.id];
    if (!r) return [s.id, v(s.group), v(s.desc), '', '', s.vi, v(s.pf_w), '', '', '', '', '', '', '', '', '', '', '', '', '', '',
                    dp ? 'jeszcze nie przeliczona' : 'brak wyników'];
    const nInst = (d.instruments || 20);
    return [s.id, v(s.group), v(s.desc), r.sl, r.tp, s.vi, v(r.search_pf_w !== null ? r.search_pf_w : s.pf_w),
      r.trades ? r.pf : '', r.trades, v(r.hold_median), `${r.instruments_traded} / ${nInst}`, r.instruments_pf_gt1, r.folds_pf_gt1,
      v(r.blind_pf), r.trades ? r.edge : '', r.tp_pct, r.sl_pct, r.fc_pct, r.time_pct, v(r.fc_avg), r.avg_ret_pct,
      !r.trades ? 'brak transakcji' : (r.trades < 10 ? 'mało transakcji (< 10)' : (r.active ? 'aktualna' : 'wynik z czasu, gdy była aktywna'))];
  });
  if (rows.length) {
    const need = rows.length + 2;
    if (sh.getMaxRows() < need) sh.insertRowsAfter(sh.getMaxRows(), need - sh.getMaxRows());
    sh.getRange(3, 1, rows.length, DP_COLS.length).setValues(rows);
    [7, 8, 14, 15].forEach(c => sh.getRange(3, c, rows.length, 1).setNumberFormat('0.00'));
    sh.getRange(3, 16, rows.length, 4).setNumberFormat('0.0%');
    sh.getRange(3, 20, rows.length, 2).setNumberFormat('+0.00;-0.00;0.00');
    const pfR = sh.getRange(3, 8, rows.length, 1);
    const rule = () => SpreadsheetApp.newConditionalFormatRule();
    sh.setConditionalFormatRules([
      rule().whenNumberGreaterThanOrEqualTo(1.5).setBackground('#ceead6').setRanges([pfR]).build(),
      rule().whenNumberLessThan(1).setBackground('#fad2cf').setRanges([pfR]).build(),
      rule().whenNumberBetween(1, 1.5).setBackground('#fef7e0').setRanges([pfR]).build(),
    ]);
  }
  sh.setFrozenRows(2);
  sh.setColumnWidth(1, 110);
  sh.setColumnWidth(2, 130);
  sh.setColumnWidth(3, 520);
}

// ============================================================================
//  ARKUSZ BACKTEST DOUBLEPROOF — jednorazowy backtest strategii aktywnych na
//  doubleProof (research/backtest-doubleproof.json, python -m ia4.lab.backtest_dp).
//  Zapisane wyniki: arkusz powstaje tylko wtedy, gdy pojawi się nowy plik backtestu
//  (createdAt pamiętany w Script Properties BT_DP_AT), potem się nie zmienia.
//  Tylko do odczytu.
// ============================================================================
const BT_COLS = ['Id', 'Grupa', 'Opis (reguła)', 'SL %', 'TP %', 'PF ważony (poszukiwanie)',
  'PF doubleProof', 'Transakcji', 'Mediana świec w pozycji', 'Suma wyników %', 'Śr. wynik transakcji %', 'Skuteczność (TP)',
  '% SL', '% FC', '% limit', 'Śr. wynik FC %', 'PF na ślepo', 'Przewaga',
  'Spółek z transakcjami', 'Spółek z PF > 1', 'Okresy z PF > 1 (z 4)',
  'PF okres 1', 'PF okres 2', 'PF okres 3', 'PF okres 4'];

function btSync_() {
  const txt = researchRaw_(RESEARCH.BT);
  if (txt === null) return;                                     // backtestu jeszcze nie było
  const bt = JSON.parse(txt);
  const props = PropertiesService.getScriptProperties();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (props.getProperty('BT_DP_AT') === bt.createdAt && ss.getSheetByName(RESEARCH.BT_SHEET)) return;
  btWrite_(bt);
  props.setProperty('BT_DP_AT', bt.createdAt);
}

function btWrite_(bt) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(RESEARCH.BT_SHEET) || ss.insertSheet(RESEARCH.BT_SHEET);
  sh.clear();
  sh.getRange(1, 1, sh.getMaxRows(), sh.getMaxColumns()).clearNote();
  sh.clearConditionalFormatRules();
  sh.setTabColor('#5f6368');
  const d = bt.data || {};
  const syms = d.symbols || [];
  const cols = BT_COLS.concat(syms.map(s => s + ' %'));
  if (sh.getMaxColumns() < cols.length) sh.insertColumnsAfter(sh.getMaxColumns(), cols.length - sh.getMaxColumns());
  const v = x => (x === undefined || x === null) ? '' : x;
  const fmtD = x => x ? String(x).replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3') : '?';
  const res = bt.results || [];
  sh.getRange(1, 1, 1, cols.length).setBackground('#202124');   // bez scalania: kolumna A jest zamrożona
  sh.getRange(1, 1)
    .setValue(`IA 4 — BACKTEST NA doubleProof (jednorazowy, zapisany ${bt.createdAtPL}): ${res.length} strategii · ` +
      `${d.instruments} spółek, ${fmtD(d.first_date)} – ${fmtD(d.last_date)}, ${Number(d.candles || 0).toLocaleString('pl-PL')} świec` +
      ((bt.errors || []).length ? ` · błędów: ${bt.errors.length}` : ''))
    .setFontSize(13).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(2, 1, 1, cols.length).setValues([cols]).setFontWeight('bold').setBackground('#f1f3f4').setWrap(true);
  const rows = res.map(r => {
    const f = r.folds || [];
    const inst = r.instruments || {};
    return [r.id, v(r.group), v(r.desc), r.sl, r.tp, v(r.search_pf_w), r.trades ? r.pf : '', r.trades,
      v(r.hold_median), v(r.sum_ret_pct), r.avg_ret_pct, r.tp_pct, r.sl_pct, r.fc_pct, r.time_pct, v(r.fc_avg),
      v(r.blind_pf), r.trades ? r.edge : '', `${r.instruments_traded} / ${d.instruments || 20}`,
      r.instruments_pf_gt1, r.folds_pf_gt1, v(f[0]), v(f[1]), v(f[2]), v(f[3])]
      .concat(syms.map(s => inst[s] ? inst[s].sum_ret_pct : ''));
  });
  if (!rows.length) return;
  const need = rows.length + 2;
  if (sh.getMaxRows() < need) sh.insertRowsAfter(sh.getMaxRows(), need - sh.getMaxRows());
  sh.getRange(3, 1, rows.length, cols.length).setValues(rows);
  // notatki przy wynikach spółek: liczba transakcji i PF
  sh.getRange(3, BT_COLS.length + 1, rows.length, syms.length).setNotes(res.map(r => syms.map(s => {
    const x = (r.instruments || {})[s];
    return x ? `${s}: transakcji ${x.trades}, PF ${x.pf}` : '';
  })));
  [6, 7, 17, 18, 22, 23, 24, 25].forEach(c => sh.getRange(3, c, rows.length, 1).setNumberFormat('0.00'));
  sh.getRange(3, 12, rows.length, 4).setNumberFormat('0.0%');
  [10, 11, 16].forEach(c => sh.getRange(3, c, rows.length, 1).setNumberFormat('+0.00;-0.00;0.00'));
  sh.getRange(3, BT_COLS.length + 1, rows.length, syms.length).setNumberFormat('+0.0;-0.0;0.0');
  const rule = () => SpreadsheetApp.newConditionalFormatRule();
  const pfR = sh.getRange(3, 7, rows.length, 1);
  const symR = sh.getRange(3, BT_COLS.length + 1, rows.length, syms.length);
  sh.setConditionalFormatRules([
    rule().whenNumberGreaterThanOrEqualTo(1.5).setBackground('#ceead6').setRanges([pfR]).build(),
    rule().whenNumberLessThan(1).setBackground('#fad2cf').setRanges([pfR]).build(),
    rule().whenNumberBetween(1, 1.5).setBackground('#fef7e0').setRanges([pfR]).build(),
    rule().whenNumberGreaterThan(0).setFontColor('#188038').setRanges([symR]).build(),
    rule().whenNumberLessThan(0).setFontColor('#c5221f').setRanges([symR]).build(),
  ]);
  sh.setFrozenRows(2);
  sh.setFrozenColumns(1);
  sh.setColumnWidth(1, 110);
  sh.setColumnWidth(2, 130);
  sh.setColumnWidth(3, 520);
  for (let c = BT_COLS.length + 1; c <= cols.length; c++) sh.setColumnWidth(c, 62);
}

// ============================================================================
//  ARKUSZ BACKTEST PORTFELA — jednorazowy backtest wirtualnego inwestora na
//  historii (research/portfolio-backtest.json, python -m ia4.lab.portfolio,
//  instrukcja 6b). Powstaje tylko przy nowym pliku (createdAt w BT_PF_AT).
//  Tylko do odczytu.
// ============================================================================
const PF_COLS = ['Wariant', 'Strategii', 'Zbiór', 'Transakcji', 'PF', 'Śr. wynik % (netto)', 'Wynik $',
  'Max obsunięcie $', 'Wynik / obsunięcie', 'Skuteczność (TP)', '% SL', '% FC', '% limit',
  'Mediana świec w pozycji', 'Wynik $ long', 'Wynik $ short', 'Transakcji long / short', 'Spółek'];
const PF_RANK_COLS = ['Miejsce', 'Id', 'Grupa', 'Transakcji doubleProof', 'Śr. wynik doubleProof %',
  'Mediana świec w pozycji (doubleProof)', 'Szacunek przewagi % (po ściągnięciu do średniej)', 'Waga własnego wyniku', 'Wybrana'];

function pfSync_() {
  const txt = researchRaw_(RESEARCH.PF);
  if (txt === null) return null;
  const pf = JSON.parse(txt);
  const props = PropertiesService.getScriptProperties();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (props.getProperty('BT_PF_AT') !== pf.createdAt || !ss.getSheetByName(RESEARCH.PF_SHEET)) {
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
  const W = Math.max(PF_COLS.length, PF_RANK_COLS.length);
  if (sh.getMaxColumns() < W) sh.insertColumnsAfter(sh.getMaxColumns(), W - sh.getMaxColumns());
  const fmtD = x => x ? String(x).replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3') : '?';
  const d = pf.data || {}, pr = pf.params || {}, sel = pf.selection || {};
  const v = x => (x === undefined || x === null) ? '' : x;
  sh.getRange(1, 1, 1, W).merge()
    .setValue(`IA 4 — BACKTEST PORTFELA (jednorazowy, zapisany ${pf.createdAtPL}) · główna: ${d.main.instruments} spółek ` +
      `${fmtD(d.main.first_date)} – ${fmtD(d.main.last_date)} · doubleProof: ${d.dp.instruments} spółek ` +
      `${fmtD(d.dp.first_date)} – ${fmtD(d.dp.last_date)} · stawka ${pr.stake_usd} $, koszt ${pr.cost_pct_per_side}% za stronę`)
    .setFontSize(12).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(2, 1, 1, W).merge()
    .setValue('„Wybrane” wybrano według wyników na doubleProof — ich wynik na doubleProof jest więc zawyżony; ' +
      'uczciwa ocena wyboru: grupa główna i skarbiec. Stawka wg SL = 100 $ × 5 / SL% (strata na SL ok. 5 $).')
    .setFontStyle('italic').setWrap(true);
  sh.getRange(3, 1, 1, PF_COLS.length).setValues([PF_COLS]).setFontWeight('bold').setBackground('#f1f3f4').setWrap(true);
  const names = { main: 'grupa główna (okresy 1–4)', vault: 'skarbiec', dp: 'doubleProof — całość',
                  dp_fold1: 'doubleProof — okres 1', dp_fold2: 'doubleProof — okres 2', dp_fold3: 'doubleProof — okres 3', dp_fold4: 'doubleProof — okres 4' };
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
  if (rows.length) {
    sh.getRange(4, 1, rows.length, PF_COLS.length).setValues(rows);
    sh.getRange(4, 6, rows.length, 1).setNumberFormat('+0.00%;-0.00%;0.00%');
    sh.getRange(4, 10, rows.length, 4).setNumberFormat('0.0%');
    [5, 9].forEach(c => sh.getRange(4, c, rows.length, 1).setNumberFormat('0.00'));
    [7, 8, 15, 16].forEach(c => sh.getRange(4, c, rows.length, 1).setNumberFormat('#,##0.00'));
    for (let i = 0; i < rows.length; i += 7) sh.getRange(4 + i, 1, 1, PF_COLS.length).setFontWeight('bold');
  }
  let r0 = 4 + rows.length + 2;
  const rank = sel.ranking || [];
  sh.getRange(r0, 1, 1, W).merge()
    .setValue(`PIERWSZEŃSTWO STRATEGII (to samo w wirtualnym inwestorze) · wybrane: ${sel.selected} — szacunek przewagi ≥ ${sel.select_min_pct}% ` +
      `· średnia ${sel.mean_pct}%, rozrzut prawdziwych przewag ${sel.tau_pct}%, rozrzut pojedynczej transakcji ${sel.pooled_sd_pct}%`)
    .setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff').setWrap(true);
  sh.getRange(r0 + 1, 1, 1, PF_RANK_COLS.length).setValues([PF_RANK_COLS]).setFontWeight('bold').setBackground('#f1f3f4').setWrap(true);
  if (rank.length) {
    sh.getRange(r0 + 2, 1, rank.length, PF_RANK_COLS.length).setValues(rank.map((x, i) => [i + 1, x.id, x.group, x.dp_trades,
      x.dp_avg_ret_pct / 100, v(x.dp_hold_median), x.shrunk_pct / 100, x.weight, x.selected ? '✓' : '']));
    sh.getRange(r0 + 2, 5, rank.length, 1).setNumberFormat('+0.00%;-0.00%;0.00%');
    sh.getRange(r0 + 2, 7, rank.length, 1).setNumberFormat('+0.00%;-0.00%;0.00%');
  }
  const rule = () => SpreadsheetApp.newConditionalFormatRule();
  const usd = sh.getRange(4, 7, Math.max(rows.length, 1), 1);
  sh.setConditionalFormatRules([
    rule().whenNumberGreaterThan(0).setFontColor('#188038').setRanges([usd]).build(),
    rule().whenNumberLessThan(0).setFontColor('#c5221f').setRanges([usd]).build(),
  ]);
  sh.setFrozenRows(3);
  sh.setColumnWidth(1, 330);
  sh.setColumnWidth(2, 110);
  sh.setColumnWidth(3, 190);
}
