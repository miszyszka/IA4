/**
 * ============================================================================
 *  IA 4 — SMA 42/23 INVESTOR  (paper trading „zawsze w pozycji” na 10 parach FX 1h,
 *                             arkusz SMA.42-23.Investor, telemetry/sma.json)
 *
 *  Wersja projektu: 1.60 (2026-10-21) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Strategia (instrukcja, sekcja 7b „SMA-KRZYŻ”; decyzja człowieka z 21.10.2026 — komórka 42/23 tabeli 50 × 50):
 *   • SMA42 i SMA23 z zamknięć świec 1h; na zamknięciu świecy: SMA42 > SMA23 → LONG, SMA42 < SMA23 → SHORT
 *     (równe — bez zmiany). To wariant „przeciw ruchowi”: long, gdy krótka średnia spadła pod długą.
 *   • Zawsze w pozycji: na każdej z 10 par jedna transakcja; zmiana kierunku → zamknięcie i otwarcie przeciwnej
 *     po open następnej świecy (jak w badaniu — pesymistycznie, bez wejścia po zamknięciu).
 *   • Wynik transakcji % = kierunek × (wyjście − wejście) / wejście − spread / wejście (spread raz na transakcję).
 *  Rachunek: kapitał startowy (1000 $), wartość pozycji = % salda (zamknięte) w chwili otwarcia — żółte komórki;
 *  depozyt = wartość / dźwignia (tylko informacyjnie i do stop outu: poziom < 50% po najgorszej cenie świecy).
 *  Świece: pamięć Powrót.v2 (_PV2_DANE, te same 10 par); stan: ukryty arkusz _SMA_DANE.
 *  Uruchamia go fxIfDue_ (Fx.gs) po zapisie nowych świec FX. Silnik sma_* jest czysty (tests/sma_check.js).
 * ============================================================================
 */

const SMA = {
  SHEET: 'SMA.42-23.Investor',
  STORE_SHEET: '_SMA_DANE',
  A: 42, B: 23,               // long, gdy SMA(A) > SMA(B)
  CHART: 300,                 // świec na parę w telemetry/sma.json
  STOP_OUT: 0.5,
  PUB_PATH: 'telemetry/sma.json',
  DEFAULTS: { capital: 1000, pct: 0.10, lev: 30, active: 'TAK' },
  LOG_ROW: 20,
};
const SMA_COLS = ['Nr', 'Para', 'Kierunek', 'Decyzja — świeca (PL)', 'Wejście (PL)', 'Cena wejścia', 'Wartość pozycji ($)', 'Depozyt ($)', 'Lot',
  'Status', 'Ostatnia świeca (PL)', 'Cena aktualna', 'Wynik %', 'Wynik $', 'Wyjście (PL)', 'Cena wyjścia', 'Powód wyjścia', 'Świec w pozycji'];

// ============================================================================
//  SILNIK (czysty — używa go też tests/sma_check.js)
// ============================================================================
/** Kierunek na zamknięciu każdej świecy: +1 long, −1 short, 0 — za mało świec albo średnie równe. */
function sma_dirs_(c) {
  const a = pv2_sma_(c, SMA.A), b = pv2_sma_(c, SMA.B);
  return c.map((_, i) => !isFinite(a[i]) || !isFinite(b[i]) ? 0 : a[i] > b[i] ? 1 : a[i] < b[i] ? -1 : 0);
}

function sma_ret_(p, dir, en, ex) { return dir * (ex - en) / en * 100 - pv2_spreadPx_(p) / en * 100; }

/** Symulacja na świecach x od indeksu start: lista transakcji {dir, J (decyzja), e0 (wejście), e1 (wyjście albo −1), en, ex, ret}. */
function sma_batch_(p, x, start) {
  const d = sma_dirs_(x.c), out = [];
  let cur = null, want = 0;
  for (let j = Math.max(start, 1); j < x.n; j++) {
    if (want && (!cur || cur.dir !== want)) {                      // decyzja z poprzedniej świecy → open tej świecy
      if (cur) { cur.e1 = j; cur.ex = x.o[j]; cur.ret = sma_ret_(p, cur.dir, cur.en, cur.ex); out.push(cur); }
      cur = { dir: want, J: j - 1, e0: j, e1: -1, en: x.o[j], ex: NaN, ret: NaN };
    }
    if (d[j]) want = d[j];
  }
  if (cur) { cur.ex = x.c[x.n - 1]; cur.ret = sma_ret_(p, cur.dir, cur.en, cur.ex); out.push(cur); }
  return out;
}

// ============================================================================
//  APPS SCRIPT
// ============================================================================
function smaIfDue_(fxState) {
  const st = fxState || fxStateLoad_();
  const props = PropertiesService.getScriptProperties();
  const seen = PV2.PAIRS.map(p => (st.sym[p] && st.sym[p].last) || 0).join(',');
  if (seen === props.getProperty('SMA_SEEN')) return '';
  props.setProperty('SMA_SEEN', seen);                                   // błąd kroku nie powtarza się co minutę
  return smaStep_();
}

function smaNow() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Automat właśnie pracuje — spróbuj za minutę.'); return; }
  try { startRun_(); toast_(smaStep_(true) || 'SMA 42/23: brak nowych świec.'); finishRun_(marketContext_(new Date()), 'SMA 42/23 — przeliczenie z menu'); }
  catch (e) { alert_('SMA 42/23: ' + e.message); }
  finally { lock.releaseLock(); }
}

function smaResetNow() {
  const ui = SpreadsheetApp.getUi();
  if (ui.alert('SMA 42/23 od nowa: wszystkie pozycje zostaną skasowane, saldo wraca do kapitału startowego, liczy od teraz. Kontynuować?',
    ui.ButtonSet.OK_CANCEL) !== ui.Button.OK) return;
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Automat właśnie pracuje — spróbuj za minutę.'); return; }
  try {
    pv2_storeSave_({ cache: null, state: sma_newState_(sma_params_(sma_sheet_())) }, SMA.STORE_SHEET);
    startRun_(); smaStep_(true); finishRun_(marketContext_(new Date()), 'SMA 42/23 — od nowa');
    toast_('SMA 42/23 zaczyna od teraz.');
  } finally { lock.releaseLock(); }
}

function sma_newState_(prm) {
  return { startedAt: Math.floor(Date.now() / 1000), capital: prm.capital, cash: prm.capital, seq: 0, positions: [], pend: {}, done: {}, equity: [] };
}

/** Świece z pamięci Powrót.v2 (dociągnięte, gdy brakuje najnowszych). */
function sma_candles_() {
  const ps = pv2_storeLoad_();
  const st = fxStateLoad_();
  const stale = !ps.cache || PV2.PAIRS.some(p => { const b = (ps.cache[p] || []); return !b.length || (st.sym[p] && st.sym[p].last > b[b.length - 1].t); });
  if (stale) { ps.cache = pv2_refreshCache_(ps.cache || {}); pv2_storeSave_(ps); }
  return ps.cache;
}

function smaStep_(force) {
  const sh = sma_sheet_(), prm = sma_params_(sh);
  const store = pv2_storeLoad_(SMA.STORE_SHEET);
  if (!store.state) store.state = sma_newState_(prm);
  const S = store.state;
  const cache = sma_candles_();
  const X = {};
  PV2.PAIRS.forEach(p => { if ((cache[p] || []).length > SMA.A + 2) X[p] = pv2_series_(cache[p]); });
  // nowe świece wszystkich par po kolei w czasie (wspólne saldo)
  const todo = [];
  Object.keys(X).forEach(p => {
    const x = X[p], from = Math.max(S.done[p] || 0, S.startedAt - 3600);
    for (let j = SMA.A; j < x.n; j++) if (x.t[j] > from) todo.push({ p, j, t: x.t[j] });
  });
  todo.sort((a, b) => (a.t - b.t) || (PV2.PAIRS.indexOf(a.p) - PV2.PAIRS.indexOf(b.p)));
  const D = {};
  Object.keys(X).forEach(p => { D[p] = sma_dirs_(X[p].c); });
  const log = [];
  todo.forEach(({ p, j, t }) => {
    const x = X[p];
    let pos = S.positions.find(q => q.pair === p && q.status === 'otwarta');
    // 1. decyzja z wcześniejszej świecy → zamknięcie / otwarcie po open tej świecy
    const pend = S.pend[p];
    if (pend && t > pend.sigT) {
      if (pos && pos.dir !== pend.dir) { sma_close_(S, pos, t, x.o[j], 'zmiana kierunku', j); pos = null; }
      if (!pos && prm.active) {
        const notional = prm.pct * S.cash, bu = pv2_usd_(p, X, j);
        if (notional > 0) {
          pos = { no: ++S.seq, pair: p, dir: pend.dir, status: 'otwarta', sigT: pend.sigT, entryT: t, entry: x.o[j], notional,
                  margin: notional / prm.lev, units: isFinite(bu) ? notional / bu : null, lastT: t, price: x.c[j], bars: 0 };
          S.positions.push(pos);
        }
      }
      delete S.pend[p];
    }
    // 2. wycena otwartej
    if (pos) { pos.bars = (pos.bars || 0) + 1; pos.lastT = t; pos.price = x.c[j]; pos.retNow = sma_ret_(p, pos.dir, pos.entry, x.c[j]); }
    // 3. stop out (najgorsza cena świecy każdej otwartej pozycji)
    const opn = S.positions.filter(q => q.status === 'otwarta');
    if (opn.length) {
      let worst = 0, used = 0;
      opn.forEach(q => {
        const xx = X[q.pair], jj = xx.t.indexOf(t);
        const w = jj < 0 ? (q.price || q.entry) : q.dir > 0 ? xx.l[jj] : xx.h[jj];
        worst += q.notional * sma_ret_(q.pair, q.dir, q.entry, w) / 100; used += q.margin;
      });
      if (S.cash + worst < SMA.STOP_OUT * used) {
        opn.forEach(q => {
          const xx = X[q.pair], jj = xx.t.indexOf(t), w = jj < 0 ? (q.price || q.entry) : q.dir > 0 ? xx.l[jj] : xx.h[jj];
          sma_close_(S, q, t, w, 'stop out', jj);
        });
        log.push('STOP OUT');
      }
    }
    // 4. decyzja na zamknięciu tej świecy
    const d = D[p][j], curDir = pos && pos.status === 'otwarta' ? pos.dir : 0;
    if (d && d !== curDir && prm.active) S.pend[p] = { dir: d, sigT: t };
    else if (d && d === curDir) delete S.pend[p];
    S.done[p] = Math.max(S.done[p] || 0, t);
  });
  S.lastT = Math.max.apply(null, Object.keys(X).map(p => X[p].t[X[p].n - 1]).concat([S.lastT || 0]));
  pv2_storeSave_({ cache: null, state: S }, SMA.STORE_SHEET);
  sma_writeSheet_(sh, S, prm);
  try { sma_publish_(S, prm, X); } catch (e) { console.warn('sma.json: ' + e.message); }
  const opened = S.positions.filter(q => q.status === 'otwarta').length;
  const msg = todo.length || force ? `SMA 42/23: świec ${todo.length}, otwarte ${opened}, saldo ${Math.round(S.cash * 100) / 100} $` + (log.length ? ' · ' + log.join(', ') : '') : '';
  if (msg) log_('INFO', 'SMA', msg);
  return msg;
}

function sma_close_(S, q, t, px, why, j) {
  q.status = 'zamknięta'; q.exitT = t; q.exit = px; q.exitKind = why;
  q.ret = sma_ret_(q.pair, q.dir, q.entry, px); q.pnl = q.notional * q.ret / 100; S.cash += q.pnl;
  S.equity.push([t, Math.round(S.cash * 100) / 100]);
  if (S.equity.length > 3000) S.equity = S.equity.slice(-3000);
}

// ============================================================================
//  ARKUSZ SMA.42-23.Investor
// ============================================================================
const SMA_PARAMS = [['Kapitał startowy ($)', 'capital'], ['Wartość pozycji na parę (% salda)', 'pct'], ['Dźwignia (1:x) — depozyt i stop out', 'lev'],
  ['Inwestor aktywny (TAK/NIE)', 'active']];
const SMA_STATS = ['Liczy od (PL)', 'Saldo — kapitał + zamknięte ($)', 'Wynik zamkniętych ($)', 'Wynik otwartych ($)', 'Saldo, gdyby teraz zamknąć wszystko ($)',
  'Wynik całkowity (% kapitału)', 'Pozycji otwartych (long / short)', 'Transakcji zamkniętych', 'Zyskownych zamkniętych', 'Ostatnia przeliczona świeca (PL)'];

function sma_sheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(SMA.SHEET);
  if (sh) return sh;
  sh = ss.insertSheet(SMA.SHEET);
  sh.setTabColor('#1a73e8');
  if (sh.getMaxColumns() < SMA_COLS.length) sh.insertColumnsAfter(sh.getMaxColumns(), SMA_COLS.length - sh.getMaxColumns());
  sh.getRange(1, 1, 1, 10).merge().setValue('IA 4 — SMA 42/23 INVESTOR (paper trading: zawsze w pozycji na 10 parach FX 1h, long gdy SMA42 > SMA23, short gdy niżej)')
    .setFontSize(13).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(3, 1, 1, 2).setValues([['PARAMETRY (żółte — można zmieniać)', '']]).setFontWeight('bold').setBackground('#f1f3f4');
  const D = SMA.DEFAULTS;
  sh.getRange(4, 1, SMA_PARAMS.length, 2).setValues(SMA_PARAMS.map(([lab, k]) => [lab, D[k]]));
  sh.getRange(4, 2, SMA_PARAMS.length, 1).setBackground('#ffff00').setFontColor('#0000ff');
  sh.getRange(5, 2).setNumberFormat('0%');
  sh.getRange(4, 1, SMA_PARAMS.length, 1).setFontWeight('bold');
  sh.getRange(9, 1, 1, 2).merge().setValue('Wartość 10% salda × 10 par = całe saldo w rynku bez dźwigni — tak liczyła tabela SMA-KRZYŻ. Zmiana kapitału działa po „IA 4 → SMA 42/23 — zacznij od nowa”, wartość pozycji — od następnej transakcji.')
    .setFontStyle('italic').setFontColor('#555555').setWrap(true);
  sh.setRowHeight(9, 60);
  sh.getRange(3, 4, 1, 2).setValues([['STATYSTYKI', '']]).setFontWeight('bold').setBackground('#f1f3f4');
  sh.getRange(4, 4, SMA_STATS.length, 1).setValues(SMA_STATS.map(x => [x])).setFontWeight('bold');
  sh.getRange(3, 7, 1, 2).setValues([['REGUŁY (instrukcja 7b)', '']]).setFontWeight('bold').setBackground('#f1f3f4');
  const rules = [['Średnie', `SMA${SMA.A} i SMA${SMA.B} z zamknięć 1h`], ['Long', `SMA${SMA.A} > SMA${SMA.B} (krótka spadła pod długą)`],
    ['Short', `SMA${SMA.A} < SMA${SMA.B}`], ['Zmiana', 'po open świecy następnej po przecięciu: zamknięcie + otwarcie przeciwnej'],
    ['SL / TP', 'brak — zawsze w pozycji'], ['Pary', PV2.PAIRS.join(', ')], ['Spread (pipsy)', PV2.PAIRS.map(p => `${p} ${PV2.SPREAD[p]}`).join(', ')],
    ['Uwaga', 'najlepsza komórka tabeli w 2 latach (+7,8% bez dźwigni), ale w roku 2 −3,6% — ocena dopiero na żywo']];
  sh.getRange(4, 7, rules.length, 2).setValues(rules);
  sh.getRange(4, 7, rules.length, 1).setFontWeight('bold');
  sh.getRange(SMA.LOG_ROW - 1, 1, 1, 10).merge().setValue('TRANSAKCJE (otwarte na górze, potem zamknięte — najnowsze pierwsze)')
    .setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(SMA.LOG_ROW, 1, 1, SMA_COLS.length).setValues([SMA_COLS]).setFontWeight('bold').setBackground('#f1f3f4').setWrap(true);
  sh.setColumnWidth(1, 230); sh.setColumnWidth(4, 260); sh.setColumnWidth(7, 110); sh.setColumnWidth(8, 330);
  return sh;
}

function sma_params_(sh) {
  const v = sh.getRange(4, 2, SMA_PARAMS.length, 1).getValues().map(r => r[0]);
  const D = SMA.DEFAULTS, out = {};
  SMA_PARAMS.forEach(([, k], i) => { out[k] = (v[i] === '' || v[i] === null) ? D[k] : v[i]; });
  out.capital = Number(out.capital) > 0 ? Number(out.capital) : D.capital;
  let pct = Number(out.pct);
  if (pct > 10) pct /= 100;                              // wpisane „10” zamiast „10%”
  out.pct = pct > 0 && pct <= 10 ? pct : D.pct;
  out.lev = Number(out.lev) > 0 ? Number(out.lev) : D.lev;
  out.active = String(out.active).trim().toUpperCase().startsWith('T');
  return out;
}

function sma_writeSheet_(sh, S, prm) {
  const P = S.positions, closed = P.filter(q => q.status === 'zamknięta'), open = P.filter(q => q.status === 'otwarta');
  const unreal = open.reduce((a, q) => a + q.notional * (q.retNow || 0) / 100, 0), real = closed.reduce((a, q) => a + q.pnl, 0);
  sh.getRange(4, 5, SMA_STATS.length, 1).setValues([
    [pv2_pl_(S.startedAt)], [Math.round(S.cash * 100) / 100], [Math.round(real * 100) / 100], [Math.round(unreal * 100) / 100],
    [Math.round((S.cash + unreal) * 100) / 100], [(S.cash + unreal) / S.capital - 1],
    [`${open.length} (${open.filter(q => q.dir > 0).length} / ${open.filter(q => q.dir < 0).length})`], [closed.length],
    [closed.length ? `${closed.filter(q => q.pnl > 0).length} (${Math.round(100 * closed.filter(q => q.pnl > 0).length / closed.length)}%)` : ''],
    [S.lastT ? pv2_pl_(S.lastT) : '']]);
  sh.getRange(9, 5).setNumberFormat('+0.00%;-0.00%;0.00%');
  const pl = t => t ? pv2_pl_(t) : '', r2 = v => v === undefined || v === null ? '' : Math.round(v * 100) / 100;
  const rows = P.slice().sort((a, b) => ((a.status === 'otwarta' ? 0 : 1) - (b.status === 'otwarta' ? 0 : 1)) || (b.no - a.no)).map(q => [
    q.no, q.pair, q.dir > 0 ? 'long' : 'short', pl(q.sigT), pl(q.entryT), q.entry, r2(q.notional), r2(q.margin), q.units ? Math.round(q.units / 1000) / 100 : '',
    q.status, pl(q.lastT), q.price !== undefined ? q.price : '',
    q.status === 'zamknięta' ? q.ret / 100 : (q.retNow !== undefined ? q.retNow / 100 : ''),
    q.status === 'zamknięta' ? r2(q.pnl) : (q.retNow !== undefined ? r2(q.notional * q.retNow / 100) : ''),
    q.status === 'zamknięta' ? pl(q.exitT) : '', q.exit !== undefined ? q.exit : '', q.exitKind || '', q.bars || '']);
  const first = SMA.LOG_ROW + 1, old = sh.getLastRow() - first + 1;
  if (old > 0) sh.getRange(first, 1, old, SMA_COLS.length).clearContent();
  if (rows.length) {
    if (sh.getMaxRows() < first + rows.length) sh.insertRowsAfter(sh.getMaxRows(), first + rows.length - sh.getMaxRows());
    sh.getRange(first, 1, rows.length, SMA_COLS.length).setValues(rows);
    sh.getRange(first, 13, rows.length, 1).setNumberFormat('+0.000%;-0.000%;0.000%');
  }
}

// ============================================================================
//  telemetry/sma.json — strona IA4: zakładka FX → SMA 42/23
// ============================================================================
function sma_publish_(S, prm, X) {
  const props = PropertiesService.getScriptProperties();
  if (!props.getProperty('GITHUB_TOKEN')) return false;
  const r = (p, v) => v === undefined || v === null || !isFinite(v) ? null : Number(v.toFixed(/JPY$/.test(p) ? 3 : 5));
  const pairs = {}, sim = [];
  PV2.PAIRS.forEach(p => {
    const x = X[p];
    if (!x) return;
    const from = Math.max(0, x.n - SMA.CHART), a = pv2_sma_(x.c, SMA.A), b = pv2_sma_(x.c, SMA.B);
    pairs[p] = { pip: pv2_pip_(p), spread: PV2.SPREAD[p],
      candles: x.t.slice(from).map((t, k) => [t, r(p, x.o[from + k]), r(p, x.h[from + k]), r(p, x.l[from + k]), r(p, x.c[from + k]), r(p, a[from + k]), r(p, b[from + k])]) };
    sma_batch_(p, x, SMA.A).forEach(tr => {
      if (tr.e1 >= 0 && tr.e1 < from) return;
      sim.push({ pair: p, dir: tr.dir, sigT: x.t[tr.J], entryT: x.t[tr.e0], exitT: tr.e1 >= 0 ? x.t[tr.e1] : null, entry: r(p, tr.en), exit: r(p, tr.ex),
                 ret: Number(tr.ret.toFixed(4)), open: tr.e1 < 0 });
    });
  });
  const keep = S.positions.filter(q => q.status === 'otwarta').concat(S.positions.filter(q => q.status === 'zamknięta').slice(-400));
  const P = keep.map(q => ({ no: q.no, pair: q.pair, dir: q.dir, status: q.status, sigT: q.sigT, entryT: q.entryT, exitT: q.exitT || null,
    entry: r(q.pair, q.entry), exit: r(q.pair, q.exit), price: r(q.pair, q.price), kind: q.exitKind || null,
    ret: q.ret !== undefined ? Number(q.ret.toFixed(4)) : (q.retNow !== undefined ? Number(q.retNow.toFixed(4)) : null),
    pnl: q.pnl !== undefined ? Math.round(q.pnl * 100) / 100 : (q.retNow !== undefined ? Math.round(q.notional * q.retNow) / 100 : null),
    notional: Math.round(q.notional * 100) / 100, margin: Math.round(q.margin * 100) / 100, lots: q.units ? Number((q.units / 100000).toFixed(4)) : null, bars: q.bars || null }));
  const closed = S.positions.filter(q => q.status === 'zamknięta'), open = S.positions.filter(q => q.status === 'otwarta');
  const unreal = open.reduce((a, q) => a + q.notional * (q.retNow || 0) / 100, 0);
  const doc = { version: CONFIG.VERSION, generatedAt: new Date().toISOString(), lastT: S.lastT || null,
    params: { capital: S.capital, pct: prm.pct, lev: prm.lev, active: prm.active, startedAt: S.startedAt, a: SMA.A, b: SMA.B },
    summary: { cash: Math.round(S.cash * 100) / 100, unrealized: Math.round(unreal * 100) / 100, closed: closed.length, open: open.length,
      long: open.filter(q => q.dir > 0).length, short: open.filter(q => q.dir < 0).length, wins: closed.filter(q => q.pnl > 0).length,
      pending: Object.keys(S.pend || {}).length },
    pend: S.pend || {}, equity: S.equity, positions: P, sim, pairs };
  const body = JSON.parse(JSON.stringify(doc));
  delete body.generatedAt;
  const raw = Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, JSON.stringify(body), Utilities.Charset.UTF_8);
  const hash = raw.map(b => ((b & 0xFF) + 0x100).toString(16).slice(1)).join('');
  if (hash === props.getProperty('SMA_HASH')) return false;
  telemetryGithubPut_(SMA.PUB_PATH, JSON.stringify(doc), `SMA ${S.lastT ? pv2_pl_(S.lastT) : ''}`.trim());
  props.setProperty('SMA_HASH', hash);
  return true;
}
