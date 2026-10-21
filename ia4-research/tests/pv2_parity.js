// IA 4 — test zgodności PowrotV2.gs z Pythonem (ia4.fxpowrot2, V2). Wersja projektu: 1.55 (2026-10-21). Opis: tests/pv2_parity_dump.py
const fs = require('fs');
const src = fs.readFileSync(require('path').join(__dirname, '..', '..', 'PowrotV2.gs'), 'utf8');
eval(src.replace(/^const (PV2|PV2_COLS|PV2_PARAMS|PV2_STATS) =/gm, 'var $1 ='));
const C = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
let bad = 0, n = 0, maxd = 0;
const js = [];
Object.keys(C.frames).forEach(p => {
  if (Math.abs(PV2.SPREAD[p] - C.spread[p]) > 1e-9) { console.log(`spread ${p}: Apps Script ${PV2.SPREAD[p]} ≠ Python ${C.spread[p]}`); bad++; }
  const X = pv2_series_(C.frames[p].map(a => ({ t: a[0], o: a[1], h: a[2], l: a[3], c: a[4], f: a[5] })));
  pv2_batch_(p, X, C.warmup).forEach(tr => js.push([p, tr.J, tr.x, tr.ret]));
});
const key = a => `${a[0]}:${a[1]}:${a[2]}`;
const py = new Map(C.trades.map(a => [key(a), a[3]]));
js.forEach(a => { n++; const r = py.get(key(a)); if (r === undefined) { bad++; if (bad < 10) console.log('tylko JS:', a); } else { maxd = Math.max(maxd, Math.abs(r - a[3])); if (Math.abs(r - a[3]) > 1e-7) bad++; } });
const jk = new Set(js.map(key));
C.trades.forEach(a => { if (!jk.has(key(a))) { bad++; if (bad < 10) console.log('tylko Python:', a); } });
console.log(`transakcje: JS ${js.length}, Python ${C.trades.length}, największa różnica wyniku ${maxd.toExponential(1)}`);
console.log(`rozbieżności: ${bad}`);
process.exit(bad ? 1 : 0);
