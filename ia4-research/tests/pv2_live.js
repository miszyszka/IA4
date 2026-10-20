// IA 4 — test pracy na żywo PowrotV2.gs: krok po każdej świecy (makiety Apps Script) = transakcje z pv2_batch_.
// Wersja projektu: 1.53 (2026-10-20). Użycie: node tests/pv2_live.js /tmp/pv2.json (plik z tests/pv2_parity_dump.py)
const fs = require('fs');
const src = fs.readFileSync(require('path').join(__dirname, '..', '..', 'PowrotV2.gs'), 'utf8');
const C = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
// ---- makiety Apps Script
const props = {}; const mails = []; let pub = null; let NOW = 0;
global.PropertiesService = { getScriptProperties: () => ({ getProperty: k => props[k] ?? null, setProperty: (k, v) => { props[k] = String(v); } }) };
global.MailApp = { sendEmail: m => mails.push(m) };
global.CONFIG = { LOCAL_TZ: 'Europe/Warsaw', VERSION: 'test' };
global.Utilities = {
  formatDate: (d, tz, f) => new Intl.DateTimeFormat('sv-SE', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(d).replace(',', ''),
  computeDigest: (a, s) => Array.from(require('crypto').createHash('md5').update(s).digest()), DigestAlgorithm: {}, Charset: {} };
global.log_ = () => {}; global.recordError_ = (s, m) => { throw new Error(s + ': ' + m); };
global.fxInst_ = () => ({});
global.fxSlotOpen_ = (inst, t) => {                    // rynek: nd 17:00 – pt 17:00 Nowy Jork
  const p = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday: 'short', hour: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(t * 1000));
  const wd = p.find(x => x.type === 'weekday').value, h = +p.find(x => x.type === 'hour').value;
  if (wd === 'Sat') return false; if (wd === 'Sun') return h >= 17; if (wd === 'Fri') return h < 17; return true;
};
global.telemetryGithubPut_ = (path, content) => { pub = JSON.parse(content); };
Date.now = () => NOW * 1000;
eval(src.replace(/^const (PV2|PV2_COLS|PV2_PARAMS|PV2_STATS) =/gm, 'var $1 ='));
const PRM = { capital: 100, pct: 0.2, lev: 30, mail: 'test@example.com', mails: true, mailTp: false, active: true };
let store = {};
pv2_sheet_ = () => null; pv2_params_ = () => Object.assign({}, PRM); pv2_writeSheet_ = () => {};
pv2_storeLoad_ = () => JSON.parse(JSON.stringify(store)); pv2_storeSave_ = s => { store = JSON.parse(JSON.stringify(s)); };
props.GITHUB_TOKEN = 'x';
// ---- świece wszystkich par po kolei w czasie; cache = ostatnie 640 świec ≤ chwili
const B = {}; Object.keys(C.frames).forEach(p => { B[p] = C.frames[p].map(a => ({ t: a[0], o: a[1], h: a[2], l: a[3], c: a[4], f: a[5] })); });
const T = B.EURUSD.map(b => b.t), start = T[T.length - 2600];                 // ok. 5 miesięcy na żywo
let upto = 0;
pv2_refreshCache_ = cache => { PV2.PAIRS.forEach(p => { const a = B[p].filter(b => b.t <= upto); cache[p] = a.slice(-PV2.CACHE); }); return cache; };
store.state = { startedAt: start, capital: 100, cash: 100, seq: 0, positions: [], equity: [] };
for (const t of T) {
  if (t < start) continue;
  upto = t; NOW = t + 3600 + 40;                       // świeca t zamknięta, 40 s później krok
  pv2Step_();
}
// ---- porównanie z pv2_batch_ (pełna historia) dla sygnałów po starcie + 3 dni
const S = store.state, from = start + 3 * 86400;
const live = S.positions.filter(q => q.status === 'zamknięta' && q.sigT >= from).map(q => `${q.pair}:${q.sigT}:${q.bars}:${q.ret.toFixed(8)}`);
const batch = [];
const endT = T[T.length - 1] - 5 * 86400;                    // sygnały blisko końca danych — symulacja ich nie zamyka
live.splice(0, live.length, ...live.filter(k => +k.split(':')[1] <= endT));
PV2.PAIRS.forEach(p => { const X = pv2_series_(B[p]); pv2_batch_(p, X, C.warmup).forEach(tr => { if (X.t[tr.J] >= from && X.t[tr.J] <= endT) batch.push(`${p}:${X.t[tr.J]}:${tr.x}:${tr.ret.toFixed(8)}`); }); });
const ls = new Set(live), bs = new Set(batch);
const onlyL = live.filter(k => !bs.has(k)), onlyB = batch.filter(k => !ls.has(k));
console.log(`na żywo: ${live.length} zamkniętych, symulacja całości: ${batch.length}; tylko na żywo ${onlyL.length}, tylko w symulacji ${onlyB.length}`);
onlyL.slice(0, 5).forEach(k => console.log('  tylko na żywo', k)); onlyB.slice(0, 5).forEach(k => console.log('  tylko w symulacji', k));
const kinds = {}; mails.forEach(m => { const k = m.subject.split(':')[1].trim().split(' ')[0]; kinds[k] = (kinds[k] || 0) + 1; });
const nums = S.positions.map(q => q.no).filter(Boolean).sort((a, b) => a - b), gaps = nums.some((v, i) => v !== i + 1);
console.log('maile:', JSON.stringify(kinds), '· saldo', S.cash.toFixed(2), '$ · anulowane', S.positions.filter(q => q.status === 'anulowana').length,
  '· pv2.json', pub ? `${Object.keys(pub.pairs).length} par, ${pub.sim.length} transakcji symulacji, ${pub.positions.length} pozycji` : 'brak');
if (mails.length) console.log('\n--- przykładowy mail ---\n' + mails[0].subject + '\n' + mails[0].body + '\n');
const closeMail = mails.find(m => /ZAMKNIJ/.test(m.subject)); if (closeMail) console.log('--- ' + closeMail.subject + '\n' + closeMail.body + '\n');
console.log('numeracja bez dziur:', !gaps, '· pozycji w logu', S.positions.length);
if (process.argv[3] && pub) fs.writeFileSync(process.argv[3], JSON.stringify(pub));
const ok = !onlyL.length && !onlyB.length && live.length > 10 && !gaps;
console.log(ok ? 'WYNIK: OK' : 'WYNIK: BŁĄD');
process.exit(ok ? 0 : 1);
