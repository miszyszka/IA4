// IA 4 — test Daily.gs (baza świec dobowych, instrukcja 4d) w Node na atrapach Apps Script.
// Wersja projektu: 1.51 (2026-10-20). Uruchomienie: node ia4-research/tests/daily.js  → „WYNIK: OK”
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..', '..');
let NOW = Date.parse('2026-10-13T21:30:00Z');          // 17:30 ET (EDT) — 90 min po zamknięciu

// ---------------------------------------------------------------- atrapy
function fmt(date, tz, f) {
  const p = {};
  new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(date).forEach(x => { p[x.type] = x.value; });
  if (f === 'yyyy-MM-dd') return `${p.year}-${p.month}-${p.day}`;
  if (f === 'HH:mm') return `${p.hour}:${p.minute}`;
  if (f === 'yyyy-MM-dd HH:mm') return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`;
  throw new Error('format ' + f);
}
const PROPS = {};
const COMMITS = [];
const FETCHED = [];
let YAHOO = null;                                       // (symbol, query) → obiekt odpowiedzi
const resp = (code, obj) => ({ getResponseCode: () => code, getContentText: () => JSON.stringify(obj) });
const sandbox = {
  console: { log() {}, warn() {}, error() {} },
  Utilities: { formatDate: fmt, sleep() {} },
  PropertiesService: { getScriptProperties: () => ({
    getProperty: k => (k in PROPS ? PROPS[k] : null), setProperty: (k, v) => { PROPS[k] = String(v); },
    deleteProperty: k => { delete PROPS[k]; } }) },
  ScriptApp: { getOAuthToken: () => 'tok' },
  LockService: { getScriptLock: () => ({ tryLock: () => true, releaseLock() {} }) },
  UrlFetchApp: {
    fetchAll: reqs => reqs.map(r => {
      const m = r.url.match(/chart\/([^?]+)\?(.*)$/);
      const sym = decodeURIComponent(m[1]);
      FETCHED.push({ sym, q: m[2] });
      const o = YAHOO(sym, m[2]);
      return o ? resp(200, o) : resp(404, { chart: { error: { description: 'Not Found' } } });
    }),
    fetch: (url, opt) => { COMMITS.push(JSON.parse(opt.payload)); return resp(200, {}); },
  },
  SpreadsheetApp: { getActiveSpreadsheet: () => ({ toast() {} }), getUi: () => ({ alert() {} }) },
};
sandbox.Date = class extends Date {
  constructor(...a) { if (a.length) super(...a); else super(NOW); }
  static now() { return NOW; }
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'Code.gs'), 'utf8'), sandbox);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'Daily.gs'), 'utf8'), sandbox);
vm.runInContext(`startRun_(); var ERRS = []; recordError_ = (s, m) => { ERRS.push(s + ': ' + m); }; finishRun_ = () => {};`, sandbox);
const G = (expr) => vm.runInContext(expr, sandbox);

// ---------------------------------------------------------------- dane Yahoo
const DAY = 86400000;
function series(sym, from, to) {                        // dni robocze (z „świętami” w danych — Yahoo ich nie ma)
  const out = [];
  let t = Date.parse(from + 'T13:30:00Z'), p = 50 + sym.length;
  const end = Date.parse(to + 'T13:30:00Z');
  for (; t <= end; t += DAY) {
    const d = new Date(t).toISOString().slice(0, 10);
    const wd = new Date(t).getUTCDay();
    if (wd === 0 || wd === 6) continue;
    const c = p * (1 + Math.sin(t / 7e8) * 0.01);
    out.push({ t: t / 1000, o: p, h: Math.max(p, c) * 1.01, l: Math.min(p, c) * 0.99, c, v: 1000 });
    p = c;
  }
  return out;
}
function yahooJson(rows, gran, splits) {
  return { chart: { result: [{
    meta: { dataGranularity: gran || '1d', exchangeTimezoneName: 'America/New_York' },
    timestamp: rows.map(r => r.t),
    indicators: { quote: [{ open: rows.map(r => r.o), high: rows.map(r => r.h), low: rows.map(r => r.l),
                            close: rows.map(r => r.c), volume: rows.map(r => r.v) }] },
    events: splits ? { splits } : undefined,
  }] } };
}
function byQuery(q, rows) {
  const p1 = /period1=(-?\d+)/.exec(q);
  return p1 ? rows.filter(r => r.t >= Number(p1[1])) : rows;
}

let fails = 0;
function check(name, ok, info) {
  console.log(`  ${ok ? 'OK ' : 'BŁĄD'} ${name}${info !== undefined ? ': ' + JSON.stringify(info) : ''}`);
  if (!ok) fails++;
}
const writesOf = () => [].concat(...COMMITS.map(c => c.writes));
const docs = (re) => writesOf().filter(w => re.test(w.update.name));
const reset = () => { COMMITS.length = 0; FETCHED.length = 0; };
const ctxAt = (iso) => { NOW = Date.parse(iso); return G(`marketContext_(new Date(${NOW}))`); };

console.log('IA 4 — test Daily.gs (świece dobowe)\n');

// 1. Parser: cyfry znaczące, puste wartości, weekend / święto, duplikat, dzisiejsza świeca
{
  const rows = [
    { t: Date.parse('2026-10-09T13:30:00Z') / 1000, o: 0.0997123456, h: 0.11, l: 0.09, c: 0.1, v: 5 },
    { t: Date.parse('2026-10-10T13:30:00Z') / 1000, o: 1, h: 1, l: 1, c: 1, v: 1 },        // sobota
    { t: Date.parse('2026-09-07T13:30:00Z') / 1000, o: 1, h: 1, l: 1, c: 1, v: 1 },        // święto
    { t: Date.parse('2026-10-12T13:30:00Z') / 1000, o: null, h: 1, l: 1, c: 1, v: 1 },     // brak open
    { t: Date.parse('2026-10-08T13:30:00Z') / 1000, o: 2, h: 2, l: 2, c: 2, v: 2 },
    { t: Date.parse('2026-10-08T19:59:00Z') / 1000, o: 3, h: 3, l: 3, c: 3, v: 3 },        // ta sama data — późniejsza wygrywa
    { t: Date.parse('2026-10-13T13:30:00Z') / 1000, o: 4, h: 4, l: 4, c: 4, v: 4 },        // dziś
  ];
  const res = yahooJson(rows, '1d', { x: { date: Date.parse('2026-06-01T13:30:00Z') / 1000, numerator: 4, denominator: 1 } });
  sandbox.__r = res.chart.result[0];
  const ctxIn = ctxAt('2026-10-13T20:10:00Z');           // 16:10 ET — za wcześnie na dzisiejszą
  sandbox.__c = ctxIn;
  const p = G('dailyParse_(__r, __c, null)');
  check('parser: daty', p.rows.map(r => r.d).join(',') === '2026-10-08,2026-10-09', p.rows.map(r => r.d));
  check('parser: 6 cyfr znaczących', p.rows[1].o === 0.0997123, p.rows[1].o);
  check('parser: duplikat — późniejsza', p.rows[0].c === 3, p.rows[0].c);
  check('parser: split', p.splits.length === 1 && p.splits[0].d === '2026-06-01' && p.splits[0].r === '4:1', p.splits);
  sandbox.__c = ctxAt('2026-10-13T20:31:00Z');           // 16:31 ET — 31 min po zamknięciu
  check('parser: dzisiejsza po zamknięciu + 30 min', G('dailyParse_(__r, __c, null)').rows.length === 3);
}

// 2. Pory: w sesji historia nie rusza, po zamknięciu + 60 min — tak
{
  const syms = G('allSymbols_()');
  const data = {};
  syms.forEach((s, i) => { data[s] = series(s, i % 3 ? '2019-01-02' : '2016-01-04', '2026-10-13'); });
  YAHOO = (sym, q) => data[sym] ? yahooJson(byQuery(q, data[sym])) : null;
  reset();
  check('w sesji: bez historii', G(`dailyIfDue_(marketContext_(new Date(${Date.parse('2026-10-13T17:00:00Z')})))`) === '' && !FETCHED.length);
  NOW = Date.parse('2026-10-13T20:30:00Z');              // 16:30 ET — wciąż cisza (do +60 min)
  check('tuż po zamknięciu: bez historii', G(`dailyIfDue_(marketContext_(new Date(${NOW})))`) === '');

  // 3. Porcje historii aż do kompletu
  let portions = 0;
  NOW = Date.parse('2026-10-13T21:30:00Z');
  for (let k = 0; k < 30; k++) {
    const msg = G(`dailyHistoryIfDue_(marketContext_(new Date(${NOW})), false)`);
    if (msg) portions++;
    NOW += 3 * 60000 + 1000;
  }
  const st = JSON.parse(PROPS.DAILY_STATE);
  const done = syms.filter(s => st.s[s] && st.s[s].h).length;
  check('historia: wszystkie instrumenty', done === syms.length, `${done}/${syms.length}`);
  check('historia: porcje po 6', portions === Math.ceil(syms.length / 6), portions);
  const yearDocs = docs(/\/daily\/[^/]+\/years\/\d{4}$/);
  const expYears = syms.reduce((n, s, i) => n + (i % 3 ? 8 : 11), 0);
  check('historia: dokument na rok', yearDocs.length === expYears, `${yearDocs.length} vs ${expYears}`);
  const aapl2020 = yearDocs.find(w => /daily\/AAPL\/years\/2020$/.test(w.update.name)).update.fields;
  const n2020 = data.AAPL.filter(r => new Date(r.t * 1000).toISOString().startsWith('2020')).length;
  check('historia: rok 2020 kompletny', Number(aapl2020.n.integerValue) === n2020 && aapl2020.d.arrayValue.values.length === n2020,
        [aapl2020.n.integerValue, n2020]);
  check('historia: tablice równej długości', ['o', 'h', 'l', 'c', 'v'].every(k => aapl2020[k].arrayValue.values.length === n2020));
  check('historia: zapisy w paczkach ≤ 40', COMMITS.every(c => c.writes.length <= 40));
  check('historia: system/daily', docs(/system\/daily$/).length === portions);
  check('historia: stan < 9 KB (limit Script Properties)', PROPS.DAILY_STATE.length < 9000, PROPS.DAILY_STATE.length);
  check('historia: bez błędów', G('ERRS').length === 0, G('ERRS'));
  const tel = G('dailyTelemetry_()');
  check('telemetria', tel.history === `${syms.length}/${syms.length}` && tel.oldest === '2016-01-04', tel);
}

// 4. Zapasowe zapytanie, gdy Yahoo odda inną granulację
{
  PROPS.DAILY_STATE = JSON.stringify({ s: {} });
  const rows = series('X', '2020-01-02', '2026-10-13');
  YAHOO = (sym, q) => yahooJson(byQuery(q, rows), /range=max/.test(q) ? '3mo' : '1d');
  reset();
  NOW = Date.parse('2026-10-13T22:00:00Z');
  G(`dailyHistoryIfDue_(marketContext_(new Date(${NOW})), true)`);
  check('granulacja ≠ 1d → zapytanie od 1970', FETCHED.some(f => /period1=0&/.test(f.q)) && JSON.parse(PROPS.DAILY_STATE).s.AAPL.h === 1);
}

// 5. Aktualizacja: bieżący rok od 1 stycznia, podsumowanie z updateMask, split → historia od nowa, bezpiecznik
{
  const syms = G('allSymbols_()');
  const st = { s: {} };
  syms.forEach(s => { st.s[s] = { h: 1, f: '2016-01-04', l: '2026-10-12', sp: '' }; });
  PROPS.DAILY_STATE = JSON.stringify(st);
  const data = {};
  syms.forEach(s => { data[s] = series(s, '2025-12-01', '2026-10-13'); });
  YAHOO = (sym, q) => {
    let rows = byQuery(q, data[sym]);
    if (sym === 'KO') rows = rows.filter(r => r.t > Date.parse('2026-03-01T00:00:00Z') / 1000);   // niepełny rok
    const sp = sym === 'NVDA' ? { a: { date: Date.parse('2026-06-10T13:30:00Z') / 1000, numerator: 10, denominator: 1 } } : undefined;
    return yahooJson(rows, '1d', sp);
  };
  reset();
  PROPS.DAILY_STATE = JSON.stringify(Object.assign({}, st, { upd: '2026-10-12' }));
  NOW = Date.parse('2026-10-13T21:00:00Z');              // 17:00 ET — przed +75 min, wczoraj już jest
  check('aktualizacja: nie przed zamknięciem + 75 min', G(`dailyUpdateIfDue_(marketContext_(new Date(${NOW})), false)`) === '' && !FETCHED.length);
  reset();
  sandbox.ERRS.length = 0;
  NOW = Date.parse('2026-10-13T21:20:00Z');              // 17:20 ET
  PROPS.DAILY_STATE = JSON.stringify(st);
  const msg = G(`dailyUpdateIfDue_(marketContext_(new Date(${NOW})), false)`);
  const q = FETCHED[0].q;
  check('aktualizacja: od 1 stycznia', /period1=(\d+)/.exec(q)[1] == Math.floor(Date.UTC(2026, 0, 1) / 1000) - 86400, q);
  const yd = docs(/years\/\d{4}$/);
  check('aktualizacja: tylko rok 2026', yd.every(w => /years\/2026$/.test(w.update.name)));
  const ad = yd.find(w => /daily\/AAPL\/years\/2026$/.test(w.update.name)).update.fields;
  check('aktualizacja: rok od początku do dziś', ad.d.arrayValue.values[0].stringValue <= '2026-01-08' &&
        ad.d.arrayValue.values.slice(-1)[0].stringValue === '2026-10-13');
  const sm = writesOf().find(w => /daily\/AAPL$/.test(w.update.name));
  check('aktualizacja: podsumowanie z updateMask', sm && sm.updateMask && sm.updateMask.fieldPaths.join() === 'last,lastClose,updatedAt');
  const st2 = JSON.parse(PROPS.DAILY_STATE);
  check('aktualizacja: split → historia od nowa', st2.s.NVDA.h === 0 && !yd.some(w => /NVDA/.test(w.update.name)));
  check('aktualizacja: niepełny rok pominięty', !yd.some(w => /daily\/KO\//.test(w.update.name)) && sandbox.ERRS.some(e => /KO/.test(e)));
  check('aktualizacja: przy błędach ponowienie (upd bez zmian)', !st2.upd, st2.upd);
  check('aktualizacja: komunikat', /aktualizacja 2026-10-13/.test(msg), msg);
  NOW += 31 * 60000; G(`dailyUpdateIfDue_(marketContext_(new Date(${NOW})), false)`);
  check('aktualizacja: 2. próba z błędem — dzień nadal otwarty', !JSON.parse(PROPS.DAILY_STATE).upd);
  NOW += 31 * 60000; G(`dailyUpdateIfDue_(marketContext_(new Date(${NOW})), false)`);
  check('aktualizacja: 3. próba — dzień uznany mimo błędu', JSON.parse(PROPS.DAILY_STATE).upd === '2026-10-13');
  // styczeń: dwa lata
  reset();
  PROPS.DAILY_STATE = JSON.stringify(st);
  const jan = {};
  syms.forEach(s => { jan[s] = series(s, '2024-12-02', '2026-01-09'); });
  YAHOO = (sym, q) => yahooJson(byQuery(q, jan[sym]));
  NOW = Date.parse('2026-01-09T22:30:00Z');              // 17:30 ET (EST)
  G(`dailyUpdateIfDue_(marketContext_(new Date(${NOW})), false)`);
  const yrs = new Set(docs(/years\/\d{4}$/).map(w => w.update.name.slice(-4)));
  check('aktualizacja w styczniu: 2025 i 2026', yrs.has('2025') && yrs.has('2026') && yrs.size === 2, [...yrs]);
  check('aktualizacja w styczniu: zapytanie od 1.01.2025', /period1=(\d+)/.exec(FETCHED[0].q)[1] == Math.floor(Date.UTC(2025, 0, 1) / 1000) - 86400);
  const st3 = JSON.parse(PROPS.DAILY_STATE);
  check('aktualizacja: dzień zapisany', st3.upd === '2026-01-09', st3.upd);
  // weekend: dzień docelowy = piątek
  sandbox.__c = ctxAt('2026-10-17T15:00:00Z');           // sobota
  check('dzień docelowy w sobotę = piątek', G('dailyTarget_(__c, null)') === '2026-10-16');
  sandbox.__c = ctxAt('2026-09-08T14:00:00Z');           // wtorek rano po święcie (7.09)
  check('dzień docelowy po święcie = piątek przed', G('dailyTarget_(__c, null)') === '2026-09-04');
}

console.log('\nWYNIK:', fails ? `BŁĘDY (${fails})` : 'OK');
process.exit(fails ? 1 : 0);
