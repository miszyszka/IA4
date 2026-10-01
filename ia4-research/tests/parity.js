// IA 4 — test zgodności PaperEngine.gs z Pythonem. Wersja projektu: 1.8 (2026-10-01). Opis: tests/parity_dump.py
const fs = require('fs');
eval(fs.readFileSync(require('path').join(__dirname, '..', '..', 'PaperEngine.gs'), 'utf8'));
const C = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const KIND = { SL: 1, TP: 2, FC: 3, LIMIT: 4 };
const X = {}, CTX = {};
for (const s of Object.keys(C.frames)) X[s] = pe_series_(C.frames[s]);
CTX.spy = pe_contextMap_(X.SPY); CTX.qqq = pe_contextMap_(X.QQQ);
let badMask = 0, badTr = 0, nMask = 0, nTr = 0;
const t0 = Date.now();
C.rules.forEach((R, ri) => {
  const rule = R.rule;
  const mask = [], trades = [];
  C.traded.forEach((s, si) => {
    const x = X[s], base = C.seg[si][0];
    let pos = null, pending = null;
    for (let j = 0; j < x.n; j++) {
      if (pending !== null) {
        pos = { dir: rule.direction === 'long' ? 1 : -1, entry: x.o[j], e: j, sl: rule.exit.sl, tp: rule.exit.tp,
                maxBars: rule.exit.max_bars || 0, fcPending: false, crossed: false, t: pending };
        pending = null;
      }
      if (pos) {
        const r = pe_stepPosition_(rule, x, pos, j);
        if (r) { trades.push([base + pos.t, base + j, r.ret, KIND[r.kind]]); pos = null; }
      }
      const sig = pe_signalAt_(rule, x, j, CTX);
      if (sig) mask.push(base + j);
      if (sig && !pos && pending === null && j + 1 < x.n) pending = j;
    }
  });
  nMask += R.mask.length; nTr += R.trades.length;
  const ms = new Set(R.mask), js = new Set(mask);
  const dm = R.mask.filter(i => !js.has(i)).length + mask.filter(i => !ms.has(i)).length;
  let dt = 0;
  const key = a => a[0] + ':' + a[1] + ':' + a[3];
  const pm = new Map(R.trades.map(a => [key(a), a[2]]));
  trades.forEach(a => { const p = pm.get(key(a)); if (p === undefined || Math.abs(p - a[2]) > 1e-6) dt++; });
  dt += Math.abs(R.trades.length - trades.length);
  if (dm || dt) { badMask += dm; badTr += dt;
    if (badMask + badTr < 40) console.log('✗', ri, JSON.stringify(rule).slice(0, 220), 'mask diff', dm, 'trade diff', dt, R.trades.length, trades.length); }
});
console.log(`reguł ${C.rules.length}, sygnałów ${nMask}, transakcji ${nTr}; rozbieżności: sygnały ${badMask}, transakcje ${badTr}; ${Date.now() - t0} ms`);
