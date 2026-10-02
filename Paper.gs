/**
 * ============================================================================
 *  IA 4 — PAPER TRADING  (sygnały na żywo + wirtualny inwestor)
 *
 *  Wersja projektu: 1.12 (2026-10-02) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Po zamknięciu każdej świecy, gdy automat zapisał ją do Firestore:
 *   1. dociąga nowe świece z Firestore do pamięci (ukryty arkusz _IA4_DANE,
 *      ostatnie PAPER.CACHE_BARS świec każdego instrumentu),
 *   2. sprawdza na tej świecy wszystkie strategie aktywne (research/strategies.jsonl)
 *      oraz strategie wpisane w VIRTUAL-INVESTOR — silnik: PaperEngine.gs,
 *   3. dopisuje wiersz do SIGNALS-REALTIME (każdy sygnał: ID + ticker),
 *   4. wirtualny inwestor: prowadzi otwarte pozycje (luka/FC/SL/TP/limit — jak
 *      w backteście) i otwiera nowe dla sygnałów strategii z jego listy.
 *  Uruchamia go runCollector (Code.gs) — bez osobnego triggera.
 * ============================================================================
 */

const PAPER = {
  CACHE_BARS: 1800,            // świec na instrument w pamięci (EMA/KAMA zbiegają się dużo wcześniej)
  STORE_SHEET: '_IA4_DANE',
  SIGNALS_SHEET: 'SIGNALS-REALTIME',
  INVESTOR_SHEET: 'VIRTUAL-INVESTOR',
  CAPITAL: 100000,
  STAKE: 100,
  MAX_IDS: 20,                 // ile zaznaczonych strategii pokazuje lista w VIRTUAL-INVESTOR
  ID_FIRST_ROW: 4,             // A4:B23 — lista strategii „for VI” (tylko podgląd)
  TRADES_HEADER_ROW: 27,
  SIGNALS_MAX_ROWS: 3000,
  MAX_CATCHUP: 21,             // najwięcej świec nadrabianych naraz (3 sesje)
  WAIT_AFTER_WRITE_MIN: 8,     // gdy brakuje świecy części spółek — czekamy tyle od ostatniego zapisu
  CHUNK: 45000,                // znaków w jednej komórce magazynu
};

// ============================================================================
//  WEJŚCIE: z runCollector (Code.gs) i z menu
// ============================================================================
/** Czy jest nowa, zamknięta świeca do przeliczenia — i przelicza. Zwraca opis albo ''. */
function paperIfDue_(ctx, t0) {
  if (Date.now() - t0 > 150 * 1000) return '';               // za mało czasu w tym uruchomieniu
  const props = PropertiesService.getScriptProperties();
  const live = liveLoad_();
  const traded = CONFIG.SYMBOLS.concat(CONFIG.PROOF_SYMBOLS);
  const keys = traded.map(s => (live[s] && live[s].k) || 0);
  const newest = Math.max.apply(null, keys);
  const last = Number(props.getProperty('PAPER_LAST_KEY') || 0);
  if (!newest || newest <= last) return '';
  const allIn = keys.every(k => k >= newest);
  const lastWrite = Date.parse(props.getProperty('LAST_WRITE') || '') || 0;
  if (!allIn && Date.now() - lastWrite < PAPER.WAIT_AFTER_WRITE_MIN * 60000) return '';
  return paperStep_();
}

function paperNow() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Automat właśnie pracuje — spróbuj za minutę.'); return; }
  try { toast_(paperStep_() || 'Brak nowych świec do przeliczenia.'); }
  catch (e) { alert_('Paper trading: ' + e.message); }
  finally { lock.releaseLock(); }
}

// ============================================================================
//  KROK
// ============================================================================
function paperStep_() {
  const props = PropertiesService.getScriptProperties();
  const store = pp_storeLoad_();
  const traded = CONFIG.SYMBOLS.concat(CONFIG.PROOF_SYMBOLS);
  const all = traded.concat(CONFIG.CONTEXT_SYMBOLS);
  const state = store.state || { lastKey: 0, positions: [], seq: 0, rules: {}, refreshDay: '' };
  state.rules = state.rules || {};

  // 1. Pamięć świec z Firestore
  let note = '';
  if (!store.cache) {
    store.cache = pp_buildCache_(all);
    note = 'zbudowano pamięć świec z Firestore';
  } else {
    const today = Utilities.formatDate(new Date(), CONFIG.MARKET_TZ, 'yyyy-MM-dd');
    const back = state.refreshDay === today ? 1 : 7;          // raz dziennie 7 dni (nocne odświeżenie)
    pp_refreshCache_(store.cache, all, back);
    state.refreshDay = today;
  }

  // 2. Strategie: aktywne + lista inwestora
  const active = pp_activeIds_();
  const sh = pp_investorSheet_();
  const invIds = viSelectedIds_();               // checkboxy „for VI” w arkuszu STRATEGIE (Research.gs)
  const ids = Array.from(new Set(active.concat(invIds)));
  ids.forEach(id => { if (!state.rules[id]) { const r = pp_fetchRule_(id); if (r) state.rules[id] = r; } });
  const rules = ids.filter(id => state.rules[id]).map(id => ({ id, rule: state.rules[id].rule }));

  // 3. Serie i tło rynku
  const X = {};
  all.forEach(s => {
    const rows = store.cache[s] || [];
    if (!rows.length) return;
    X[s] = pe_series_(rows);
    X[s].idx = {};
    for (let i = 0; i < X[s].n; i++) X[s].idx[X[s].d[i] * 10 + X[s].s[i]] = i;
  });
  // średnie okienkowe tylko dla końcówki serii: ostatnie 64 świece + świece otwartych pozycji
  traded.forEach(s => {
    const x = X[s];
    if (!x) return;
    let from = x.n - 64;
    state.positions.forEach(p => {
      if (p.sym !== s || p.status === 'zamknięta') return;
      const i = x.idx[p.lastKey];
      from = Math.min(from, i === undefined ? 0 : i - 8);
    });
    x.from = Math.max(0, from);
  });
  const CTX = {};
  if (X.SPY) CTX.spy = pe_contextMap_(X.SPY);
  if (X.QQQ) CTX.qqq = pe_contextMap_(X.QQQ);

  // 4. Nowe świece do przeliczenia (po kolei)
  const keySet = {};
  traded.forEach(s => { if (X[s]) for (let i = 0; i < X[s].n; i++) keySet[X[s].d[i] * 10 + X[s].s[i]] = 1; });
  let keys = Object.keys(keySet).map(Number).filter(k => k > state.lastKey).sort((a, b) => a - b);
  if (!state.lastKey || note) keys = keys.slice(-1);           // start: tylko najnowsza świeca
  if (keys.length > PAPER.MAX_CATCHUP) { note = `pominięto ${keys.length - PAPER.MAX_CATCHUP} starszych świec`; keys = keys.slice(-PAPER.MAX_CATCHUP); }

  const invSet = {};
  invIds.forEach(id => { invSet[id] = 1; });
  const sigRows = [];
  let opened = 0, closed = 0, nSig = 0;

  keys.forEach(K => {
    // a) pozycje: wszystkie świece instrumentu do K włącznie, których jeszcze nie widziały
    state.positions.forEach(p => {
      if (p.status === 'zamknięta') return;
      const x = X[p.sym], rule = state.rules[p.id] && state.rules[p.id].rule;
      if (!x || !rule) return;
      for (let i = 0; i < x.n; i++) {
        const k = x.d[i] * 10 + x.s[i];
        if (k <= p.lastKey || k > K) continue;
        if (p.status === 'oczekuje') {                 // wejście: open świecy po sygnale
          p.status = 'otwarta'; p.entryKey = k; p.entry = x.o[i];
          p.slPx = round_(p.entry * (1 - p.dir * p.sl / 100)); p.tpPx = round_(p.entry * (1 + p.dir * p.tp / 100));
        }
        const pos = { dir: p.dir, entry: p.entry, e: x.idx[p.entryKey], sl: p.sl, tp: p.tp,
                      maxBars: p.maxBars, fcPending: p.fcPending, crossed: p.crossed };
        const r = pe_stepPosition_(rule, x, pos, i);
        p.fcPending = pos.fcPending; p.crossed = pos.crossed;
        p.lastKey = k; p.bars = i - pos.e + 1; p.price = x.c[i];
        p.retNow = p.dir > 0 ? (x.c[i] / p.entry - 1) * 100 : (p.entry - x.c[i]) / p.entry * 100;
        if (r) {
          p.status = 'zamknięta'; p.exitKey = k; p.exitPx = round_(r.price); p.exitKind = r.kind;
          p.ret = r.ret; p.pnl = PAPER.STAKE * r.ret / 100; p.price = r.price; p.retNow = r.ret;
          closed++;
          break;
        }
      }
    });

    // b) sygnały na świecy K
    const fired = [];
    traded.forEach(s => {
      const x = X[s];
      if (!x || x.idx[K] === undefined) return;
      const t = x.idx[K];
      rules.forEach(R => {
        let hit = false;
        try { hit = pe_signalAt_(R.rule, x, t, CTX); } catch (e) { console.warn(R.id + ': ' + e.message); }
        if (!hit) return;
        fired.push([R.id, s]);
        if (!invSet[R.id]) return;
        const busy = state.positions.some(p => p.id === R.id && p.sym === s && p.status !== 'zamknięta');
        if (busy) return;                               // jedna pozycja naraz (instrukcja 8.6 p. 5)
        state.seq++;
        state.positions.push({
          no: state.seq, id: R.id, sym: s, dir: R.rule.direction === 'long' ? 1 : -1,
          sl: R.rule.exit.sl, tp: R.rule.exit.tp, maxBars: R.rule.exit.max_bars || 0,
          sigKey: K, lastKey: K, status: 'oczekuje', fcPending: false, crossed: false,
        });
        opened++;
      });
    });
    nSig += fired.length;
    sigRows.push([K, fired]);
    state.lastKey = K;
  });

  // 5. Zapis
  store.state = state;
  pp_storeSave_(store);
  props.setProperty('PAPER_LAST_KEY', String(state.lastKey));
  pp_writeSignals_(sigRows, X);
  pp_writeInvestor_(sh, state, invIds, X);
  return `paper: świec ${keys.length}, sygnałów ${nSig}, otwarto ${opened}, zamknięto ${closed}` + (note ? ` (${note})` : '');
}

// ============================================================================
//  MAGAZYN: ukryty arkusz _IA4_DANE, JSON pocięty na komórki
// ============================================================================
function pp_storeSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(PAPER.STORE_SHEET);
  if (!sh) { sh = ss.insertSheet(PAPER.STORE_SHEET); sh.hideSheet(); }
  return sh;
}

function pp_storeLoad_() {
  const sh = pp_storeSheet_();
  const out = {};
  ['cache', 'state'].forEach((name, r) => {
    const n = Number(sh.getRange(r + 1, 2).getValue() || 0);
    if (!n) return;
    const txt = sh.getRange(r + 1, 3, 1, n).getValues()[0].join('');
    try { out[name] = JSON.parse(txt); } catch (e) { console.warn('magazyn ' + name + ': ' + e.message); }
  });
  return out;
}

function pp_storeSave_(store) {
  const sh = pp_storeSheet_();
  ['cache', 'state'].forEach((name, r) => {
    const txt = JSON.stringify(store[name] || null);
    const parts = [];
    for (let i = 0; i < txt.length; i += PAPER.CHUNK) parts.push(txt.slice(i, i + PAPER.CHUNK));
    const need = parts.length + 2;
    if (sh.getMaxColumns() < need) sh.insertColumnsAfter(sh.getMaxColumns(), need - sh.getMaxColumns());
    sh.getRange(r + 1, 1, 1, sh.getMaxColumns()).clearContent();
    sh.getRange(r + 1, 1, 1, need).setValues([[name, parts.length].concat(parts)]);
  });
}

// ============================================================================
//  ŚWIECE Z FIRESTORE
// ============================================================================
function pp_num_(v) { return v ? Math.round(Number(v.doubleValue !== undefined ? v.doubleValue : v.integerValue) * 10000) / 10000 : NaN; }
function pp_arr_(v) { return (v && v.arrayValue && v.arrayValue.values) || []; }

function pp_query_(sym, where, desc, limit) {
  const main = CONFIG.SYMBOLS.indexOf(sym) >= 0;
  const q = {
    from: [{ collectionId: main ? 'candles' : 'sessions' }],
    select: { fields: (main ? ['date', 'slot', 'open', 'high', 'low', 'close', 'volume']
                            : ['date', 'slots', 'o', 'h', 'l', 'c', 'v']).map(f => ({ fieldPath: f })) },
    orderBy: [{ field: { fieldPath: 'date' }, direction: desc ? 'DESCENDING' : 'ASCENDING' }],
  };
  if (where) q.where = { fieldFilter: { field: { fieldPath: 'date' }, op: 'GREATER_THAN_OR_EQUAL', value: { stringValue: where } } };
  if (limit) q.limit = limit;
  return {
    url: `https://firestore.googleapis.com/v1/${fsBase_()}/${fsCollection_(sym)}/${sym}:runQuery`,
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    payload: JSON.stringify({ structuredQuery: q }),
  };
}

/** Odpowiedź runQuery → [[RRRRMMDD, nr, o, h, l, c, v], …]. */
function pp_parse_(sym, resp) {
  if (resp.getResponseCode() !== 200) throw new Error(`Firestore ${sym}: HTTP ${resp.getResponseCode()}`);
  const main = CONFIG.SYMBOLS.indexOf(sym) >= 0;
  const rows = [];
  JSON.parse(resp.getContentText() || '[]').forEach(it => {
    const f = it.document && it.document.fields;
    if (!f) return;
    const d = Number(String(f.date.stringValue).replace(/-/g, ''));
    if (main) {
      rows.push([d, pp_num_(f.slot), pp_num_(f.open), pp_num_(f.high), pp_num_(f.low), pp_num_(f.close), pp_num_(f.volume) || 0]);
    } else {
      const sl = pp_arr_(f.slots), o = pp_arr_(f.o), h = pp_arr_(f.h), l = pp_arr_(f.l), c = pp_arr_(f.c), v = pp_arr_(f.v);
      const n = Math.min(sl.length, o.length, h.length, l.length, c.length);
      for (let i = 0; i < n; i++) {
        rows.push([d, pp_num_(sl[i]), pp_num_(o[i]), pp_num_(h[i]), pp_num_(l[i]), pp_num_(c[i]), i < v.length ? (pp_num_(v[i]) || 0) : 0]);
      }
    }
  });
  return rows;
}

function pp_merge_(old, fresh) {
  const m = {};
  (old || []).forEach(r => { m[r[0] * 10 + r[1]] = r; });
  fresh.forEach(r => { if (r.slice(2, 6).every(x => isFinite(x))) m[r[0] * 10 + r[1]] = r; });
  return Object.keys(m).map(Number).sort((a, b) => a - b).slice(-PAPER.CACHE_BARS).map(k => m[k]);
}

/** Pierwsze zbudowanie pamięci: ostatnie CACHE_BARS świec (~19 tys. odczytów, raz). */
function pp_buildCache_(symbols) {
  const reqs = symbols.map(s => CONFIG.SYMBOLS.indexOf(s) >= 0
    ? pp_query_(s, null, true, PAPER.CACHE_BARS)
    : pp_query_(s, null, true, Math.ceil(PAPER.CACHE_BARS / 7) + 10));
  const resps = UrlFetchApp.fetchAll(reqs);
  const cache = {};
  symbols.forEach((s, i) => { cache[s] = pp_merge_([], pp_parse_(s, resps[i])); });
  return cache;
}

/** Dociągnięcie: sesje od (ostatnia data w pamięci − back dni). */
function pp_refreshCache_(cache, symbols, back) {
  const reqs = symbols.map(s => {
    const rows = cache[s] || [];
    const last = rows.length ? String(rows[rows.length - 1][0]) : '20240101';
    const d = new Date(Date.UTC(+last.slice(0, 4), +last.slice(4, 6) - 1, +last.slice(6, 8)) - back * 86400000);
    return pp_query_(s, Utilities.formatDate(d, 'UTC', 'yyyy-MM-dd'), false, 0);
  });
  const resps = UrlFetchApp.fetchAll(reqs);
  symbols.forEach((s, i) => {
    try { cache[s] = pp_merge_(cache[s], pp_parse_(s, resps[i])); }
    catch (e) { console.warn('paper: ' + e.message); }
  });
}

// ============================================================================
//  STRATEGIE Z GITHUB (branch research)
// ============================================================================
function pp_activeIds_() {
  try {
    return (researchRaw_(RESEARCH.INDEX) || '').split('\n').filter(l => l.trim())
      .map(l => { try { return JSON.parse(l).id; } catch (e) { return null; } }).filter(x => x);
  } catch (e) { console.warn('paper: lista strategii — ' + e.message); return []; }
}

/** Reguła strategii (raz pobrana jest pamiętana — reguła o danym ID nigdy się nie zmienia). */
function pp_fetchRule_(id) {
  if (!/^S-[0-9a-f]{10}$/.test(id)) return null;
  for (const dir of ['strategies', 'archive']) {
    try {
      const txt = researchRaw_(`research/${dir}/${id}.json`);
      if (txt) { const rec = JSON.parse(txt); return { rule: rec.rule, desc: rec.description }; }
    } catch (e) { console.warn('paper: ' + id + ' — ' + e.message); }
  }
  return null;
}

// ============================================================================
//  CZAS ŚWIECY
// ============================================================================
function pp_closeLabel_(K, X) {
  const d = Math.floor(K / 10), s = K % 10;
  const ds = String(d);
  const iso = `${ds.slice(0, 4)}-${ds.slice(4, 6)}-${ds.slice(6, 8)}`;
  let closeMin = Math.min(OPEN + s * 60, CLOSE);
  const sess = getSession_();
  if (sess && sess.date === iso && sess.closeMin) closeMin = Math.min(closeMin, sess.closeMin);
  const et = Utilities.parseDate(`${iso} ${fmtMin_(closeMin)}`, CONFIG.MARKET_TZ, 'yyyy-MM-dd HH:mm');
  return { date: iso, pl: Utilities.formatDate(et, CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm'), et: fmtMin_(closeMin) };
}

// ============================================================================
//  ARKUSZ SIGNALS-REALTIME — wiersz na zamkniętą świecę, najnowsze na górze
// ============================================================================
function pp_writeSignals_(sigRows, X) {
  if (!sigRows.length) return;
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(PAPER.SIGNALS_SHEET);
  if (!sh) {
    sh = ss.insertSheet(PAPER.SIGNALS_SHEET);
    sh.getRange(1, 1, 1, 4).merge().setValue('IA 4 — SYGNAŁY NA ŻYWO (wiersz = zamknięta świeca, najnowsze na górze)')
      .setFontSize(13).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
    sh.setFrozenRows(2);
    sh.setFrozenColumns(4);
    sh.setTabColor('#a142f4');
  }
  const maxSig = Math.max.apply(null, sigRows.map(r => r[1].length).concat([1]));
  const width = 4 + 2 * maxSig;
  if (sh.getMaxColumns() < width) sh.insertColumnsAfter(sh.getMaxColumns(), width - sh.getMaxColumns());
  const curHead = sh.getRange(2, 1, 1, sh.getMaxColumns()).getValues()[0].filter(x => x !== '').length;
  if (curHead < width) {
    const head = ['Data', 'Świeca', 'Zamknięcie (PL)', 'Sygnałów'];
    for (let i = 1; i <= (Math.max(width, curHead) - 4) / 2; i++) head.push('ID ' + i, 'Ticker ' + i);
    sh.getRange(2, 1, 1, head.length).setValues([head]).setFontWeight('bold').setBackground('#f1f3f4');
  }
  sigRows.slice().reverse().forEach(([K, fired]) => {
    const lab = pp_closeLabel_(K, X);
    const row = [lab.date, K % 10, lab.pl, fired.length];
    fired.forEach(f => row.push(f[0], f[1]));
    sh.insertRowBefore(3);
    sh.getRange(3, 1, 1, row.length).setValues([row]);
    sh.getRange(3, 1, 1, Math.max(row.length, 4)).setFontWeight(fired.length ? 'bold' : 'normal');
  });
  const extra = sh.getMaxRows() - (PAPER.SIGNALS_MAX_ROWS + 2);
  if (extra > 0) sh.deleteRows(PAPER.SIGNALS_MAX_ROWS + 3, extra);
}

// ============================================================================
//  ARKUSZ VIRTUAL-INVESTOR
// ============================================================================
const INV_STATS = [
  'Kapitał początkowy ($)', 'Stawka na transakcję ($)', 'Stan konta ($) — kapitał + zamknięte',
  'Wynik zamkniętych ($)', 'Wynik zamkniętych (% kapitału)', 'Wynik otwartych ($)',
  'Stan konta, gdyby teraz zamknąć wszystko ($)', 'Wynik całkowity (% kapitału)',
  'Wolna gotówka ($)', 'Pozycji otwartych / oczekujących', 'Transakcji zamkniętych',
  'Zamknięte: TP / SL / FC / limit', 'Skuteczność (TP)', 'Średni wynik zamkniętej (%)',
  'Ostatnia przeliczona świeca',
];
const INV_COLS = ['Nr', 'Strategia', 'Ticker', 'Kierunek', 'Sygnał (zamknięcie PL)', 'Wejście (PL)',
  'Cena wejścia', 'SL', 'TP', 'Status', 'Ostatnia świeca (PL)', 'Cena aktualna', 'Wynik %', 'Wynik $',
  'Wyjście (PL)', 'Cena wyjścia', 'Powód wyjścia', 'Świec w pozycji'];

function pp_investorSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(PAPER.INVESTOR_SHEET);
  if (sh) return sh;
  sh = ss.insertSheet(PAPER.INVESTOR_SHEET);
  sh.setTabColor('#0b8043');
  if (sh.getMaxColumns() < INV_COLS.length) sh.insertColumnsAfter(sh.getMaxColumns(), INV_COLS.length - sh.getMaxColumns());
  sh.getRange(1, 1, 1, 8).merge().setValue('IA 4 — WIRTUALNY INWESTOR (paper trading, 100 $ na transakcję)')
    .setFontSize(13).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(3, 1, 1, 2).setValues([['Strategie for VI', 'Opis']]).setFontWeight('bold').setBackground('#f1f3f4');
  sh.getRange(3, 4, 1, 2).setValues([['Statystyki', '']]).setFontWeight('bold').setBackground('#f1f3f4');
  sh.getRange(4, 4, INV_STATS.length, 1).setValues(INV_STATS.map(x => [x])).setFontWeight('bold');
  sh.getRange(PAPER.TRADES_HEADER_ROW - 1, 1, 1, 8).merge()
    .setValue('TRANSAKCJE (otwarte i oczekujące na górze, potem zamknięte — najnowsze pierwsze)')
    .setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(PAPER.TRADES_HEADER_ROW, 1, 1, INV_COLS.length).setValues([INV_COLS])
    .setFontWeight('bold').setBackground('#f1f3f4');
  sh.setColumnWidth(1, 150);
  sh.setColumnWidth(2, 420);
  sh.setColumnWidth(4, 300);
  return sh;
}


function pp_usd_(x) { return Math.round(x * 100) / 100; }

function pp_writeInvestor_(sh, state, invIds, X) {
  // podgląd listy „for VI” (wybór: checkboxy w arkuszu STRATEGIE)
  sh.getRange(3, 1, 1, 2).setValues([[`Strategie for VI: ${invIds.length}`,
    'Opis — wybór: zaznacz „for VI” w arkuszu STRATEGIE (bez limitu)']]);
  const view = invIds.length > PAPER.MAX_IDS ? invIds.slice(0, PAPER.MAX_IDS - 1) : invIds.slice();
  const list = view.map(id => [id, state.rules[id] ? state.rules[id].desc : '✗ nie znaleziono takiej strategii na branchu research']);
  if (invIds.length > view.length) list.push([`… i ${invIds.length - view.length} więcej`, 'pełna lista: arkusz STRATEGIE, kolumna „for VI”']);
  while (list.length < PAPER.MAX_IDS) list.push(['', '']);
  sh.getRange(PAPER.ID_FIRST_ROW, 1, PAPER.MAX_IDS, 2).setValues(list).setBackground(null);

  const P = state.positions;
  const closed = P.filter(p => p.status === 'zamknięta');
  const open = P.filter(p => p.status === 'otwarta');
  const pend = P.filter(p => p.status === 'oczekuje');
  const realized = closed.reduce((a, p) => a + p.pnl, 0);
  const unreal = open.reduce((a, p) => a + PAPER.STAKE * (p.retNow || 0) / 100, 0);
  const cnt = k => closed.filter(p => p.exitKind === k).length;
  const lab = K => K ? pp_closeLabel_(K, X).pl : '';
  sh.getRange(4, 5, INV_STATS.length, 1).setValues([
    [PAPER.CAPITAL], [PAPER.STAKE], [pp_usd_(PAPER.CAPITAL + realized)],
    [pp_usd_(realized)], [realized / PAPER.CAPITAL], [pp_usd_(unreal)],
    [pp_usd_(PAPER.CAPITAL + realized + unreal)], [(realized + unreal) / PAPER.CAPITAL],
    [pp_usd_(PAPER.CAPITAL + realized - PAPER.STAKE * open.length)], [`${open.length} / ${pend.length}`],
    [closed.length], [`${cnt('TP')} / ${cnt('SL')} / ${cnt('FC')} / ${cnt('LIMIT')}`],
    [closed.length ? cnt('TP') / closed.length : ''],
    [closed.length ? closed.reduce((a, p) => a + p.ret, 0) / closed.length / 100 : ''],
    [lab(state.lastKey)],
  ]);
  sh.getRange(8, 5).setNumberFormat('0.000%');
  sh.getRange(11, 5).setNumberFormat('0.000%');
  sh.getRange(16, 5).setNumberFormat('0.0%');
  sh.getRange(17, 5).setNumberFormat('0.00%');

  const order = { 'otwarta': 0, 'oczekuje': 1, 'zamknięta': 2 };
  const rows = P.slice().sort((a, b) => (order[a.status] - order[b.status]) || (b.no - a.no)).map(p => [
    p.no, p.id, p.sym, p.dir > 0 ? 'long' : 'short', lab(p.sigKey), lab(p.entryKey),
    p.entry !== undefined ? round_(p.entry) : '', p.slPx || '', p.tpPx || '',
    p.status === 'oczekuje' ? 'oczekuje (wejście na otwarciu następnej świecy)' : p.status,
    lab(p.lastKey !== p.sigKey ? p.lastKey : 0), p.price !== undefined ? round_(p.price) : '',
    p.retNow !== undefined ? p.retNow / 100 : '',
    p.retNow !== undefined ? pp_usd_(PAPER.STAKE * p.retNow / 100) : '',
    lab(p.exitKey), p.exitPx || '', p.exitKind || '', p.bars || '']);
  const first = PAPER.TRADES_HEADER_ROW + 1;
  const old = sh.getLastRow() - first + 1;
  if (old > 0) sh.getRange(first, 1, old, INV_COLS.length).clearContent();
  if (rows.length) {
    const need = first + rows.length;
    if (sh.getMaxRows() < need) sh.insertRowsAfter(sh.getMaxRows(), need - sh.getMaxRows());
    sh.getRange(first, 1, rows.length, INV_COLS.length).setValues(rows);
    sh.getRange(first, 13, rows.length, 1).setNumberFormat('+0.00%;-0.00%;0.00%');
  }
}
