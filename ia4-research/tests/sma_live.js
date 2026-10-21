// IA 4 — test pracy na żywo SmaKrzyz.gs: krok po każdej świecy (makiety Apps Script) = transakcje z sma_batch_.
// Wersja projektu: 1.60 (2026-10-21). Użycie: node tests/sma_live.js /tmp/sma.json (plik z tests/sma_check_dump.py)
const fs = require('fs'), path = require('path');
const src = ['PowrotV2.gs', 'SmaKrzyz.gs'].map(f => fs.readFileSync(path.join(__dirname, '..', '..', f), 'utf8')).join('\n');
const C = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const props = {}; let pub = null; let NOW = 0;
global.PropertiesService = { getScriptProperties: () => ({ getProperty: k => props[k] ?? null, setProperty: (k, v) => { props[k] = String(v); } }) };
global.CONFIG = { LOCAL_TZ: 'Europe/Warsaw', VERSION: 'test' };
global.Utilities = {
  formatDate: (d, tz) => new Intl.DateTimeFormat('sv-SE', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(d),
  computeDigest: (a, s) => Array.from(require('crypto').createHash('md5').update(s).digest()), DigestAlgorithm: {}, Charset: {} };
global.log_ = () => {}; global.recordError_ = (s, m) => { throw new Error(s + ': ' + m); };
global.telemetryGithubPut_ = (p, content) => { pub = JSON.parse(content); };
Date.now = () => NOW * 1000;
eval(src.replace(/^const (PV2|PV2_COLS|PV2_PARAMS|PV2_STATS|PV2_NOTE_ROW|SMA|SMA_COLS|SMA_PARAMS|SMA_STATS) =/gm, 'var $1 ='));
const stores = {};
pv2_storeLoad_ = name => JSON.parse(JSON.stringify(stores[name || 'pv2'] || {}));
pv2_storeSave_ = (s, name) => { stores[name || 'pv2'] = JSON.parse(JSON.stringify(s)); };
sma_sheet_ = () => null; sma_params_ = () => ({ capital: 1000, pct: 0.1, lev: 30, active: true }); sma_writeSheet_ = () => {};
props.GITHUB_TOKEN = 'x';
const B = {}; Object.keys(C.frames).forEach(p => { B[p] = C.frames[p].map(a => ({ t: a[0], o: a[1], h: a[2], l: a[3], c: a[4], f: a[5] })); });
const T = B.EURUSD.map(b => b.t), start = T[T.length - 2600];
let upto = 0;
fxStateLoad_ = () => ({ sym: Object.fromEntries(PV2.PAIRS.map(p => { const a = B[p].filter(b => b.t <= upto); return [p, { last: a.length ? a[a.length - 1].t : 0 }]; })) });
pv2_refreshCache_ = cache => { PV2.PAIRS.forEach(p => { cache[p] = B[p].filter(b => b.t <= upto).slice(-PV2.CACHE); }); return cache; };
NOW = start;
stores[SMA.STORE_SHEET] = { state: sma_newState_({ capital: 1000 }) };
for (const t of T) {
  if (t < start) continue;
  upto = t; NOW = t + 3600 + 40;
  smaIfDue_();
}
const S = stores[SMA.STORE_SHEET].state, from = start + 3 * 86400;
const live = S.positions.filter(q => q.status === 'zamknięta' && q.entryT >= from).map(q => `${q.pair}:${q.entryT}:${q.exitT}:${q.ret.toFixed(8)}`);
const batch = [];
PV2.PAIRS.forEach(p => { const X = pv2_series_(B[p]); sma_batch_(p, X, SMA.A).forEach(tr => { if (tr.e1 >= 0 && X.t[tr.e0] >= from) batch.push(`${p}:${X.t[tr.e0]}:${X.t[tr.e1]}:${tr.ret.toFixed(8)}`); }); });
const ls = new Set(live), bs = new Set(batch);
const onlyL = live.filter(k => !bs.has(k)), onlyB = batch.filter(k => !ls.has(k));
console.log(`na żywo: ${live.length} zamkniętych, symulacja: ${batch.length}; tylko na żywo ${onlyL.length}, tylko w symulacji ${onlyB.length}`);
onlyL.slice(0, 5).forEach(k => console.log('  tylko na żywo', k)); onlyB.slice(0, 5).forEach(k => console.log('  tylko w symulacji', k));
const open = S.positions.filter(q => q.status === 'otwarta');
const nums = S.positions.map(q => q.no).sort((a, b) => a - b), gaps = nums.some((v, i) => v !== i + 1);
console.log(`saldo ${S.cash.toFixed(2)} $ · otwarte ${open.length} · numeracja bez dziur ${!gaps} · sma.json ${pub ? Object.keys(pub.pairs).length + ' par, ' + pub.sim.length + ' transakcji symulacji, ' + pub.positions.length + ' pozycji' : 'brak'}`);
if (process.argv[3] && pub) fs.writeFileSync(process.argv[3], JSON.stringify(pub));
const ok = !onlyL.length && !onlyB.length && live.length > 50 && !gaps && open.length === PV2.PAIRS.length;
console.log(ok ? 'WYNIK: OK' : 'WYNIK: BŁĄD');
process.exit(ok ? 0 : 1);
