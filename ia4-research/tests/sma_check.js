// IA 4 — test zgodności SmaKrzyz.gs z Pythonem (tests/sma_check_dump.py). Wersja projektu: 1.60 (2026-10-21)
const fs = require('fs'), path = require('path');
const src = ['PowrotV2.gs', 'SmaKrzyz.gs'].map(f => fs.readFileSync(path.join(__dirname, '..', '..', f), 'utf8')).join('\n');
eval(src.replace(/^const (PV2|PV2_COLS|PV2_PARAMS|PV2_STATS|SMA|SMA_COLS|SMA_PARAMS|SMA_STATS) =/gm, 'var $1 ='));
const C = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
let bad = 0, maxd = 0, sum = 0;
const js = [];
Object.keys(C.frames).forEach(p => {
  if (Math.abs(PV2.SPREAD[p] - C.spread[p]) > 1e-9) { console.log(`spread ${p}: Apps Script ${PV2.SPREAD[p]} ≠ Python ${C.spread[p]}`); bad++; }
  const X = pv2_series_(C.frames[p].map(a => ({ t: a[0], o: a[1], h: a[2], l: a[3], c: a[4], f: a[5] })));
  sma_batch_(p, X, SMA.A).filter(tr => tr.e1 >= 0).forEach(tr => { js.push([p, tr.e0, tr.e1, tr.ret]); sum += tr.ret; });
});
const key = a => `${a[0]}:${a[1]}:${a[2]}`;
const py = new Map(C.trades.map(a => [key(a), a[3]]));
js.forEach(a => { const r = py.get(key(a)); if (r === undefined) { if (++bad < 10) console.log('tylko JS:', a); } else { maxd = Math.max(maxd, Math.abs(r - a[3])); if (Math.abs(r - a[3]) > 1e-7) bad++; } });
const jk = new Set(js.map(key));
C.trades.forEach(a => { if (!jk.has(key(a))) { if (++bad < 10) console.log('tylko Python:', a); } });
console.log(`transakcje: JS ${js.length}, Python ${C.trades.length}, największa różnica wyniku ${maxd.toExponential(1)}, suma / 10 par ${(sum / 10).toFixed(2)}%`);
console.log(`rozbieżności: ${bad}`);
process.exit(bad ? 1 : 0);
