/**
 * ============================================================================
 *  IA 4 — SILNIK REGUŁ ia4-rule/1 w JavaScript (paper trading na żywo)
 *
 *  Wersja projektu: 1.20 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Wierne przeniesienie ia4-research/ia4/lab/{indicators,data,rules,sim}.py
 *  (instrukcja, sekcja 8). Każda zmiana tu wymaga tej samej zmiany w Pythonie
 *  i odwrotnie. Zgodność sprawdza test parytetu (instrukcja, sekcja 12).
 *
 *  Seria instrumentu X = { o, h, l, c, v: Float64Array, d: daty RRRRMMDD,
 *  s: numer świecy 1–7, lines: {} } — świece w kolejności (data, numer).
 *  Brak wartości = NaN; każde porównanie z NaN jest fałszywe (jak w numpy).
 * ============================================================================
 */

// ---------------------------------------------------------------- średnie
function pe_nan_(n) { const a = new Float64Array(n); a.fill(NaN); return a; }
function pe_fin_(x) { return x - x === 0; }     // liczba skończona (NaN, ±Inf, undefined → false)

function pe_sma_(x, n) {
  const out = pe_nan_(x.length);
  let s = 0, cnt = 0;
  for (let i = 0; i < x.length; i++) {
    if (!pe_fin_(x[i])) { s = 0; cnt = 0; continue; }
    s += x[i]; cnt++;
    if (cnt > n) { s -= x[i - n]; cnt = n; }
    if (cnt === n) out[i] = s / n;
  }
  return out;
}

function pe_ema_(x, n) {
  const out = pe_nan_(x.length);
  const a = 2 / (n + 1);
  let run = 0, s = 0, prev = NaN;
  for (let i = 0; i < x.length; i++) {
    if (isNaN(prev)) {
      if (!pe_fin_(x[i])) { run = 0; s = 0; continue; }
      run++; s += x[i];
      if (run === n) { prev = s / n; out[i] = prev; }
    } else {
      if (!pe_fin_(x[i])) continue;
      prev = prev + a * (x[i] - prev);
      out[i] = prev;
    }
  }
  return out;
}

/** Średnie okienkowe liczone od indeksu `from` (wcześniej NaN) — te same wzory, mniej pracy na żywo. */
function pe_wma_(x, n, from) {
  const out = pe_nan_(x.length);
  const den = n * (n + 1) / 2;
  for (let i = Math.max(n - 1, from || 0); i < x.length; i++) {
    let s = 0, ok = true;
    for (let k = 0; k < n; k++) {
      const v = x[i - k];
      if (v - v !== 0) { ok = false; break; }
      s += v * (n - k);
    }
    if (ok) out[i] = s / den;
  }
  return out;
}

function pe_hma_(x, n, from) {
  const h = Math.max(Math.floor(n / 2), 1), q = Math.max(Math.floor(Math.sqrt(n)), 1);
  const f0 = Math.max((from || 0) - q + 1, 0);
  const w1 = pe_wma_(x, h, f0), w2 = pe_wma_(x, n, f0);
  const d = new Float64Array(x.length);
  for (let i = 0; i < x.length; i++) d[i] = 2 * w1[i] - w2[i];
  return pe_wma_(d, q, from);
}

function pe_dema_(x, n) {
  const e1 = pe_ema_(x, n), e2 = pe_ema_(e1, n);
  const out = new Float64Array(x.length);
  for (let i = 0; i < x.length; i++) out[i] = 2 * e1[i] - e2[i];
  return out;
}

function pe_tema_(x, n) {
  const e1 = pe_ema_(x, n), e2 = pe_ema_(e1, n), e3 = pe_ema_(e2, n);
  const out = new Float64Array(x.length);
  for (let i = 0; i < x.length; i++) out[i] = 3 * e1[i] - 3 * e2[i] + e3[i];
  return out;
}

function pe_kama_(x, n) {
  const out = pe_nan_(x.length);
  const fast = 2 / 3, slow = 2 / 31;
  if (x.length < n + 1) return out;
  let prev = x[n - 1];
  // suma |zmian| z n kroków: liczona od nowa co 64 świece, w międzyczasie przesuwana
  let vol = 0;
  for (let i = n; i < x.length; i++) {
    const change = Math.abs(x[i] - x[i - n]);
    if ((i - n) % 64 === 0) { vol = 0; for (let k = i - n + 1; k <= i; k++) vol += Math.abs(x[k] - x[k - 1]); }
    else vol += Math.abs(x[i] - x[i - 1]) - Math.abs(x[i - n] - x[i - n - 1]);
    const er = vol > 0 ? change / vol : 0;
    const sc = Math.pow(er * (fast - slow) + slow, 2);
    prev = prev + sc * (x[i] - prev);
    out[i] = prev;
  }
  return out;
}

function pe_vwma_(x, v, n, from) {
  const out = pe_nan_(x.length);
  for (let i = Math.max(n - 1, from || 0); i < x.length; i++) {
    let sv = 0, sxv = 0;
    for (let k = i - n + 1; k <= i; k++) { sv += v[k]; sxv += x[k] * v[k]; }
    if (sv > 0) out[i] = sxv / sv;
  }
  return out;
}

function pe_zlema_(x, n) {
  const lag = Math.floor((n - 1) / 2);
  const y = pe_nan_(x.length);
  for (let i = lag; i < x.length; i++) y[i] = 2 * x[i] - x[i - lag];
  return pe_ema_(y, n);
}

function pe_ma_(kind, n, c, v, from) {
  switch (String(kind).toUpperCase()) {
    case 'SMA': return pe_sma_(c, n);
    case 'EMA': return pe_ema_(c, n);
    case 'WMA': return pe_wma_(c, n, from);
    case 'HMA': return pe_hma_(c, n, from);
    case 'DEMA': return pe_dema_(c, n);
    case 'TEMA': return pe_tema_(c, n);
    case 'KAMA': return pe_kama_(c, n);
    case 'VWMA': return pe_vwma_(c, v, n, from);
    case 'ZLEMA': return pe_zlema_(c, n);
  }
  throw new Error('nieznany typ średniej: ' + kind);
}

function pe_atr_(h, l, c, n) {
  const out = pe_nan_(c.length);
  if (c.length < n) return out;
  const tr = new Float64Array(c.length);
  tr[0] = h[0] - l[0];
  for (let i = 1; i < c.length; i++) {
    tr[i] = Math.max(h[i] - l[i], Math.abs(h[i] - c[i - 1]), Math.abs(l[i] - c[i - 1]));
  }
  let s = 0;
  for (let i = 0; i < n; i++) s += tr[i];
  let prev = s / n;
  out[n - 1] = prev;
  for (let i = n; i < c.length; i++) { prev = (prev * (n - 1) + tr[i]) / n; out[i] = prev; }
  return out;
}

function pe_rsi_(c, n) {
  const out = pe_nan_(c.length);
  if (c.length <= n) return out;
  let g = 0, ls = 0;
  for (let i = 1; i <= n; i++) { const d = c[i] - c[i - 1]; if (d > 0) g += d; else ls -= d; }
  g /= n; ls /= n;
  out[n] = ls === 0 ? 100 : 100 - 100 / (1 + g / ls);
  for (let i = n + 1; i < c.length; i++) {
    const d = c[i] - c[i - 1];
    const up = d > 0 ? d : 0, dn = d < 0 ? -d : 0;
    g = (g * (n - 1) + up) / n;
    ls = (ls * (n - 1) + dn) / n;
    out[i] = ls === 0 ? 100 : 100 - 100 / (1 + g / ls);
  }
  return out;
}

// ---------------------------------------------------------------- seria instrumentu
/** rows: [[dateInt, slot, o, h, l, c, v], …] posortowane po (data, numer). */
function pe_series_(rows) {
  const n = rows.length;
  const X = { n, d: new Int32Array(n), s: new Int32Array(n), o: new Float64Array(n), h: new Float64Array(n),
              l: new Float64Array(n), c: new Float64Array(n), v: new Float64Array(n), lines: {}, feat: {} };
  for (let i = 0; i < n; i++) {
    const r = rows[i];
    X.d[i] = r[0]; X.s[i] = r[1]; X.o[i] = r[2]; X.h[i] = r[3]; X.l[i] = r[4]; X.c[i] = r[5]; X.v[i] = r[6];
  }
  return X;
}

/**
 * X.from — od której świecy liczyć średnie okienkowe (WMA, HMA, VWMA); 0 = cała seria.
 * Na żywo potrzebne są tylko ostatnie świece; cecha `since` wymaga całej serii (full).
 */
function pe_line_(X, spec, full) {
  const from = full ? 0 : (X.from || 0);
  const key = String(spec.ma).toUpperCase() + spec.n + '@' + from;
  if (!X.lines[key]) X.lines[key] = pe_ma_(spec.ma, spec.n, X.c, X.v, from);
  return X.lines[key];
}

function pe_lines_(rule, X) {
  const full = (rule.filters || []).some(f => f.f === 'since');
  const L = {};
  Object.keys(rule.lines).forEach(k => { L[k] = pe_line_(X, rule.lines[k], full); });
  return L;
}

function pe_atrArr_(X) {
  if (!X.feat.atr) X.feat.atr = pe_atr_(X.h, X.l, X.c, 14);
  return X.feat.atr;
}

/** z = (c − EMA_n(c)) / ATR14 dla SPY/QQQ: mapa klucz (data·10 + numer) → z. */
function pe_contextMap_(X) {
  const a = pe_atr_(X.h, X.l, X.c, 14);
  const out = { 35: {}, 140: {} };
  [35, 140].forEach(n => {
    const e = pe_ema_(X.c, n);
    for (let i = 0; i < X.n; i++) out[n][X.d[i] * 10 + X.s[i]] = (X.c[i] - e[i]) / a[i];
  });
  return out;
}

/** Cechy sesyjne gap, d5, d20 dla świecy t. */
function pe_sessionFeat_(X, t, name) {
  if (!X.feat.sess) {
    // pierwsze open i ostatnie close każdej sesji, w kolejności dat
    const dates = [], firstO = {}, lastC = {};
    for (let i = 0; i < X.n; i++) {
      const d = X.d[i];
      if (!(d in firstO)) { firstO[d] = X.o[i]; dates.push(d); }
      lastC[d] = X.c[i];
    }
    const idx = {};
    dates.forEach((d, k) => { idx[d] = k; });
    X.feat.sess = { dates, firstO, lastC, idx };
  }
  const S = X.feat.sess;
  const d = X.d[t], k = S.idx[d];
  if (name === 'gap') {
    if (k < 1) return NaN;
    return (S.firstO[d] / S.lastC[S.dates[k - 1]] - 1) * 100;
  }
  const n = name === 'd5' ? 5 : 20;
  if (k < n) return NaN;
  let s = 0;
  for (let j = k - n; j < k; j++) s += S.lastC[S.dates[j]];
  return (X.c[t] / (s / n) - 1) * 100;
}

function pe_isoDow_(dInt) {
  const y = Math.floor(dInt / 10000), m = Math.floor(dInt / 100) % 100, dd = dInt % 100;
  const w = new Date(Date.UTC(y, m - 1, dd)).getUTCDay();
  return w === 0 ? 7 : w;
}

/** Wartość cechy filtra na świecy t (instrukcja 8.4). CTX = {spy:{35,140}, qqq:{35,140}}. */
function pe_feature_(name, X, t, L, CTX) {
  const atr = pe_atrArr_(X);
  switch (name) {
    case 'ret7': case 'ret35': {
      const n = name === 'ret7' ? 7 : 35;
      return t >= n ? (X.c[t] / X.c[t - n] - 1) * 100 : NaN;
    }
    case 'vrel': {
      const w = 35;
      if (t < w || !(X.v[t] > 0)) return NaN;
      let s = 0, n = 0;
      for (let k = t - w; k < t; k++) if (X.v[k] > 0) { s += X.v[k]; n++; }
      return n > 0 ? X.v[t] / (s / n) : NaN;
    }
    case 'atrp': return atr[t] / X.c[t] * 100;
    case 'atrrank': {
      const w = 350;
      if (t < w - 1) return NaN;
      const cur = atr[t] / X.c[t] * 100;
      if (!pe_fin_(cur)) return NaN;
      let le = 0, tot = 0;
      for (let k = t - w + 1; k <= t; k++) {
        const x = atr[k] / X.c[k] * 100;
        if (pe_fin_(x)) { tot++; if (x <= cur) le++; }
      }
      return tot === w ? 100 * le / tot : NaN;
    }
    case 'rsi':
      if (!X.feat.rsi) X.feat.rsi = pe_rsi_(X.c, 14);
      return X.feat.rsi[t];
    case 'slot': return X.s[t];
    case 'dow': return pe_isoDow_(X.d[t]);
    case 'gap': case 'd5': case 'd20': return pe_sessionFeat_(X, t, name);
    case 'spy35': case 'spy140': case 'qqq35': case 'qqq140': {
      const sym = name.slice(0, 3), n = Number(name.slice(3));
      const m = CTX && CTX[sym] && CTX[sym][n];
      const z = m ? m[X.d[t] * 10 + X.s[t]] : undefined;
      return z === undefined ? NaN : z;
    }
    case 'zAB': return (L.A[t] - L.B[t]) / atr[t];
    case 'slopeA': return t >= 3 ? (L.A[t] - L.A[t - 3]) / atr[t] : NaN;
    case 'since': {
      for (let j = t; j >= 1; j--) {
        const d = L.A[j] - L.B[j], d1 = L.A[j - 1] - L.B[j - 1];
        if ((d1 <= 0 && d > 0) || (d1 >= 0 && d < 0)) return t - j;
      }
      return NaN;
    }
  }
  throw new Error('nieznana cecha: ' + name);
}

// ---------------------------------------------------------------- sygnał na świecy t
function pe_at_(arr, i) { return i >= 0 ? arr[i] : NaN; }

/** Czy reguła daje sygnał na zamknięciu świecy t (instrukcja 8.3 + filtry 8.4). */
function pe_signalAt_(rule, X, t, CTX) {
  const L = pe_lines_(rule, X);
  const sig = rule.signal, long = rule.direction === 'long';
  const A = L.A;
  const dAt = i => pe_at_(A, i) - pe_at_(L.B, i);
  let need = 3, ok = false;
  switch (sig.kind) {
    case 'cross': {
      const d = dAt(t), d1 = dAt(t - 1);
      ok = long ? (d1 <= 0 && d > 0) : (d1 >= 0 && d < 0);
      break;
    }
    case 'converge': {
      const G = sig.grow, S = sig.shrink;
      need = G + S + 2;
      const ad = i => Math.abs(dAt(i));
      ok = true;
      for (let k = 0; k < S && ok; k++) ok = ad(t - k) < ad(t - k - 1);
      for (let k = S; k < S + G && ok; k++) ok = ad(t - k) > ad(t - k - 1);
      for (let k = 0; k <= G + S && ok; k++) ok = long ? dAt(t - k) < 0 : dAt(t - k) > 0;
      break;
    }
    case 'turn': {
      const a = A[t], a1 = pe_at_(A, t - 1), a2 = pe_at_(A, t - 2);
      ok = long ? (a > a1 && a1 <= a2) : (a < a1 && a1 >= a2);
      const pos = sig.pos || 'any';
      if (pos === 'below') ok = ok && A[t] < L.B[t];
      else if (pos === 'above') ok = ok && A[t] > L.B[t];
      else if (pos !== 'any') throw new Error('turn.pos: ' + pos);
      break;
    }
    case 'revert': {
      const atr = pe_atrArr_(X);
      const z = dAt(t) / atr[t], z1 = dAt(t - 1) / pe_at_(atr, t - 1), k = sig.k;
      ok = long ? (z1 <= -k && z > -k) : (z1 >= k && z < k);
      break;
    }
    case 'ribbon': {
      const B = L.B, C = L.C;
      const fin = i => pe_fin_(pe_at_(A, i)) && pe_fin_(pe_at_(B, i)) && pe_fin_(pe_at_(C, i));
      const now = i => long ? (pe_at_(A, i) > pe_at_(B, i) && pe_at_(B, i) > pe_at_(C, i))
                            : (pe_at_(A, i) < pe_at_(B, i) && pe_at_(B, i) < pe_at_(C, i));
      ok = now(t) && fin(t) && fin(t - 1) && !now(t - 1);
      break;
    }
    case 'pcross': {
      const c1 = pe_at_(X.c, t - 1), a1 = pe_at_(A, t - 1);
      ok = long ? (c1 <= a1 && X.c[t] > A[t]) : (c1 >= a1 && X.c[t] < A[t]);
      break;
    }
    default: throw new Error('nieznany sygnał: ' + sig.kind);
  }
  if (!ok || t < need) return false;
  const fl = rule.filters || [];
  for (let i = 0; i < fl.length; i++) {
    const x = pe_feature_(fl[i].f, X, t, L, CTX);
    if (fl[i].op === '>' ? !(x > fl[i].x) : !(x < fl[i].x)) return false;
  }
  return true;
}

// ---------------------------------------------------------------- FC na zamknięciu świecy f
/**
 * Czy na zamknięciu świecy f (f ≥ świeca wejścia) zachodzi FC (instrukcja 8.5).
 * pos.crossed — dla reexpand: czy od świecy wejścia nastąpiło przecięcie (aktualizowane tu).
 */
function pe_fcAt_(rule, X, f, pos) {
  const fcs = (rule.exit && rule.exit.fc) || [];
  if (!fcs.length || f < 3) return false;
  const L = pe_lines_(rule, X);
  const long = rule.direction === 'long';
  const A = L.A;
  const dAt = i => A[i] - L.B[i];
  let hit = false;
  fcs.forEach(fc => {
    switch (fc.kind) {
      case 'reexpand': {
        const r = fc.n || 2;
        if (long ? dAt(f) > 0 : dAt(f) < 0) pos.crossed = true;
        if (pos.crossed) break;
        let ok = true;
        for (let k = 0; k < r && ok; k++) ok = Math.abs(dAt(f - k)) > Math.abs(dAt(f - k - 1));
        for (let k = 0; k <= r && ok; k++) ok = long ? dAt(f - k) < 0 : dAt(f - k) > 0;
        if (ok) hit = true;
        break;
      }
      case 'cross_back': {
        const d = dAt(f), d1 = dAt(f - 1);
        if (long ? (d1 >= 0 && d < 0) : (d1 <= 0 && d > 0)) hit = true;
        break;
      }
      case 'turn_back': {
        const a = A[f], a1 = A[f - 1], a2 = A[f - 2];
        if (long ? (a < a1 && a1 >= a2) : (a > a1 && a1 <= a2)) hit = true;
        break;
      }
      case 'pcross_back': {
        const c1 = X.c[f - 1], a1 = A[f - 1];
        if (long ? (c1 >= a1 && X.c[f] < A[f]) : (c1 <= a1 && X.c[f] > A[f])) hit = true;
        break;
      }
      default: throw new Error('nieznany FC: ' + fc.kind);
    }
  });
  return hit;
}

// ---------------------------------------------------------------- krok pozycji na świecy j
/**
 * Pozycja: { dir: +1/−1, entry: P (cena wejścia), e: indeks świecy wejścia, sl, tp (%),
 * maxBars, fcPending, crossed }. Kolejność zdarzeń jak w sim.py (instrukcja 8.6):
 * luka SL/TP → FC z poprzedniego zamknięcia → SL w trakcie → TP w trakcie → limit czasu.
 * Zwraca { price, kind: 'SL'|'TP'|'FC'|'LIMIT' } albo null; bez wyjścia sprawdza FC na zamknięciu j.
 */
function pe_stepPosition_(rule, X, pos, j) {
  const dir = pos.dir, P = pos.entry;
  const slv = P * (1 - dir * pos.sl / 100), tpv = P * (1 + dir * pos.tp / 100);
  let res = null;
  if (j > pos.e) {
    if (dir > 0 ? X.o[j] <= slv : X.o[j] >= slv) res = { price: X.o[j], kind: 'SL' };
    else if (dir > 0 ? X.o[j] >= tpv : X.o[j] <= tpv) res = { price: tpv, kind: 'TP' };
    else if (pos.fcPending) res = { price: X.o[j], kind: 'FC' };
  }
  if (!res && (dir > 0 ? X.l[j] <= slv : X.h[j] >= slv)) res = { price: slv, kind: 'SL' };
  if (!res && (dir > 0 ? X.h[j] >= tpv : X.l[j] <= tpv)) res = { price: tpv, kind: 'TP' };
  if (!res && pos.maxBars && j === pos.e + pos.maxBars - 1) res = { price: X.c[j], kind: 'LIMIT' };
  if (res) {
    res.ret = dir > 0 ? (res.price / P - 1) * 100 : (P - res.price) / P * 100;
    return res;
  }
  pos.fcPending = pe_fcAt_(rule, X, j, pos);
  return null;
}
