/**
 * ============================================================================
 *  IA 4 — POWRÓT.V2 INVESTOR  (paper trading strategii FX-POWRÓT v2 na 10 parach FX 1h,
 *                              arkusz Powrót.v2.Investor, maile z sygnałami, telemetry/pv2.json)
 *
 *  Wersja projektu: 1.55 (2026-10-21) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Strategia (instrukcja, sekcja 7b; Python: ia4/fxpowrot2.py, V2 — reguły zamrożone):
 *   • impuls: świeca zamyka się ≥ 2 ATR(100) wyżej niż poprzednia; baza B = zamknięcie przed nią,
 *     szczyt P = najwyższy punkt od impulsu; kolejne takie świece przedłużają impuls,
 *   • sygnał: pierwsza czerwona świeca w ciągu 3 świec od ostatniej świecy impulsu (impuls wygasa,
 *     gdy zamknięcie spadnie do bazy), świeca sygnału zaczyna się 7–16 UTC,
 *   • SHORT po open następnej świecy, gdy open > B i open ≥ B + 0,5 ATR; TP = P − ½(P − B);
 *     bez transakcji, gdy do TP < 1 × spread albo < 0,1 ATR; bez SL; najwyżej 60 świec (potem
 *     zamknięcie po close 60. świecy); jedna pozycja na parę.
 *   Rozliczenie jak w Pythonie: TP w świecy, gdy low ≤ TP (luka przez TP — po TP), wynik % netto
 *   po spreadzie (raz na transakcję).
 *  Rachunek: kapitał startowy, depozyt na pozycję = % salda (zamknięte), dźwignia — z żółtych
 *  komórek arkusza; wartość pozycji = depozyt × dźwignia (bez zaokrąglania do 0,01 lota — mail
 *  ostrzega, gdy pozycja jest mniejsza niż minimum XTB); stop out < 50% depozytu (najgorsza cena świecy).
 *  Uruchamia go fxIfDue_ (Fx.gs) po zapisie nowych świec FX — sygnał i mail ok. 1 min po zamknięciu świecy.
 *  Silnik (funkcje pv2_*) jest czysty — ten sam kod liczy test zgodności z Pythonem (tests/pv2_parity.js).
 * ============================================================================
 */

const PV2 = {
  SHEET: 'Powrót.v2.Investor',
  STORE_SHEET: '_PV2_DANE',
  PAIRS: ['EURUSD', 'USDJPY', 'GBPUSD', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD', 'EURJPY', 'GBPJPY', 'EURGBP'],
  // spread w pipsach, raz na transakcję (EUR/USD 1,1 — zrzut XTB; reszta: koszty AI × 1,1 / 0,8 — jak ia4.fxshort.spreads())
  SPREAD: { EURUSD: 1.1, USDJPY: 1.24, GBPUSD: 1.65, AUDUSD: 1.38, USDCAD: 2.06, USDCHF: 2.06, NZDUSD: 2.2, EURJPY: 2.2, GBPJPY: 3.44, EURGBP: 1.65 },
  // reguły zamrożone (fxpowrot2.V2) — zmiana = zmiana instrukcji i Pythona naraz
  K: 2.0, WAIT: 3, H_FROM: 7, H_TO: 16, DIST: 0.5, F: 0.5, HOLD: 60, MINTP: 1.0, ATR: 100, ATR_LONG: 500,
  CACHE: 820,                 // świec na parę w pamięci (ATR500 potrzebuje 500; + 300 świec wykresu z symulacją)
  CHART: 300,                 // świec na parę w telemetry/pv2.json (wykresy na stronie)
  STOP_OUT: 0.5,
  CHUNK: 45000,
  PUB_PATH: 'telemetry/pv2.json',
  DEFAULTS: { capital: 100, pct: 0.20, lev: 30, mail: 'mi.szyszka@gmail.com', mails: 'TAK', mailTp: 'NIE', active: 'TAK', warn: 'TAK', warnMin: 15 },
  LOG_ROW: 24,                // wiersz nagłówka logu transakcji
};
const PV2_COLS = ['Nr', 'Para', 'Kierunek', 'Sygnał — świeca (PL)', 'Wejście (PL)', 'Cena wejścia', 'TP', 'Baza (cena sprzed wzrostu)',
  'Szczyt', 'Depozyt ($)', 'Wartość pozycji ($)', 'Lot', 'Status', 'Ostatnia świeca (PL)', 'Cena aktualna', 'Wynik %', 'Wynik $',
  'Wyjście (PL)', 'Cena wyjścia', 'Powód wyjścia', 'Świec w pozycji', 'Zamknąć najpóźniej (PL)', 'Mail'];

// ============================================================================
//  SILNIK (czysty — bez Apps Script; używa go też tests/pv2_parity.js)
// ============================================================================
function pv2_pip_(p) { return /JPY$/.test(p) ? 0.01 : 0.0001; }
function pv2_spreadPx_(p) { return PV2.SPREAD[p] * pv2_pip_(p); }

/** Średnia z ostatnich n wartości (jak pandas rolling(n).mean(); NaN, dopóki brak n wartości). */
function pv2_sma_(x, n) {
  const out = new Array(x.length).fill(NaN);
  for (let i = n - 1; i < x.length; i++) {
    let s = 0;
    for (let k = i - n + 1; k <= i; k++) s += x[k];
    out[i] = s / n;
  }
  return out;
}

/** bars: [{t,o,h,l,c,f}] rosnąco → tablice + ATR(100), ATR(500), run1 (jak fxshort.features). */
function pv2_series_(bars) {
  const n = bars.length, o = [], h = [], l = [], c = [], t = [], f = [], tr = [];
  for (let i = 0; i < n; i++) {
    const b = bars[i];
    t.push(b.t); o.push(b.o); h.push(b.h); l.push(b.l); c.push(b.c); f.push(!!b.f);
    const pc = i ? bars[i - 1].c : b.c;
    tr.push(Math.max(b.h - b.l, Math.max(Math.abs(b.h - pc), Math.abs(b.l - pc))));
  }
  const atr = pv2_sma_(tr, PV2.ATR), atr5 = pv2_sma_(tr, PV2.ATR_LONG);
  const run1 = c.map((x, i) => i ? (x - c[i - 1]) / atr[i] : NaN);
  return { n, t, o, h, l, c, f, atr, atr5, run1 };
}

/** Czy świeca s może być sygnałem (fxshort.features → valid): ATR i ATR500 policzone, następna świeca za 1 h, nie uśredniona. */
function pv2_valid_(X, s, nextOpen) {
  if (isNaN(X.atr[s]) || isNaN(X.atr5[s]) || X.f[s]) return false;
  if (s + 1 < X.n) return X.t[s + 1] - X.t[s] === 3600;
  return !!nextOpen;                                  // ostatnia świeca: czy następna godzina to rynek (na żywo)
}

/**
 * Impuls → pierwsza czerwona świeca (fxpowrot.gen_trades: N = 1, k = 2, baza = zamknięcie przed impulsem, okno 3).
 * Zwraca zdarzenia { J, B, P, S0, open } — open = false: sygnał na ostatniej świecy (wejście jeszcze nieznane).
 */
function pv2_events_(X, start, nextOpen) {
  const out = [];
  let active = false, s0 = 0, last = 0, B = 0, P = 0;
  for (let s = Math.max(start, 2); s < X.n; s++) {
    if (isNaN(X.atr[s]) || isNaN(X.run1[s])) continue;
    const trig = X.run1[s] >= PV2.K;
    if (!active) {
      if (trig) { active = true; s0 = s; last = s; B = X.c[s - 1]; P = X.h[s]; }
      continue;
    }
    if (X.h[s] > P) P = X.h[s];
    if (trig) { last = s; continue; }
    if (X.c[s] <= B || s - last > PV2.WAIT) { active = false; continue; }
    if (X.c[s] < X.o[s]) {                            // pierwsza czerwona świeca
      if (s + 1 < X.n) {
        if (pv2_valid_(X, s, false) && X.o[s + 1] > B) out.push({ J: s, B, P, S0: s0, open: true });
      } else if (pv2_valid_(X, s, nextOpen)) {
        out.push({ J: s, B, P, S0: s0, open: false });
      }
      active = false;
    }
  }
  return out;
}

/**
 * Uprzedzenie: czy świeca, która właśnie się zaczyna (po ostatniej zamkniętej n − 1), może dać sygnał.
 * Ten sam automat co pv2_events_: aktywny impuls, następna świeca mieści się w oknie 3 świec od ostatniej świecy impulsu.
 * Zwraca { B, P, A, open, lo, TP } — sygnał będzie, jeśli świeca zamknie się w przedziale [lo, open) (czerwona, nad bazą,
 * wejście ≥ 0,5 ATR nad bazą i ≥ 1 × spread nad TP; TP liczony z obecnego szczytu — wyższy szczyt podniesie lo) — albo null.
 */
function pv2_armed_(p, X, start) {
  let active = false, last = 0, B = 0, P = 0;
  for (let s = Math.max(start, 2); s < X.n; s++) {
    if (isNaN(X.atr[s]) || isNaN(X.run1[s])) continue;
    const trig = X.run1[s] >= PV2.K;
    if (!active) { if (trig) { active = true; last = s; B = X.c[s - 1]; P = X.h[s]; } continue; }
    if (X.h[s] > P) P = X.h[s];
    if (trig) { last = s; continue; }
    if (X.c[s] <= B || s - last > PV2.WAIT) { active = false; continue; }
    if (X.c[s] < X.o[s]) active = false;               // czerwona: sygnał (albo odrzucony) — impuls zużyty
  }
  const s = X.n;                                     // kandydatka (jeszcze trwa)
  if (!active || s - last > PV2.WAIT) return null;
  const A = X.atr[X.n - 1], open = X.c[X.n - 1];     // open kandydatki ≈ ostatnie zamknięcie
  if (isNaN(A) || isNaN(X.atr5[X.n - 1])) return null;
  const TP = P - PV2.F * (P - B), sp = pv2_spreadPx_(p);
  const lo = Math.max(B + PV2.DIST * A, TP + Math.max(PV2.MINTP * sp, 0.1 * A));
  if (!(lo < open)) return null;
  return { B, P, A, open, lo, TP };
}

/** Godzina UTC świecy (s). */
function pv2_hourUtc_(t) { return Math.floor((t % 86400) / 3600); }

/** Filtr godziny i wejście: { ok, en, TP, A, why } dla wejścia po open en (fxpowrot2.events + run_exit). */
function pv2_entryCheck_(p, ev, A, t, en) {
  const hr = pv2_hourUtc_(t);
  if (hr < PV2.H_FROM || hr > PV2.H_TO) return { ok: false, why: 'godzina' };
  if (!(en > ev.B)) return { ok: false, why: 'open nie wyżej niż baza' };
  if ((en - ev.B) / A < PV2.DIST) return { ok: false, why: `wejście bliżej bazy niż ${PV2.DIST} ATR` };
  const TP = ev.P - PV2.F * (ev.P - ev.B), sp = pv2_spreadPx_(p);
  if (en - TP < PV2.MINTP * sp || en - TP < 0.1 * A) return { ok: false, why: 'TP bliżej niż spread / 0,1 ATR' };
  return { ok: true, en, TP, A };
}

/** Jedna świeca j pozycji short (wejście e0): { exit, px, kind } albo null. k = j − e0 + 1. */
function pv2_exitStep_(X, j, e0, TP) {
  const k = j - e0 + 1;
  if (j > e0 && X.o[j] <= TP) return { px: TP, kind: 'TP', k };
  if (X.l[j] <= TP) return { px: TP, kind: 'TP', k };
  if (k === PV2.HOLD) return { px: X.c[j], kind: 'czas (60 świec)', k };
  return null;
}

function pv2_ret_(p, en, ex) { return (en - ex) / en * 100 - pv2_spreadPx_(p) / en * 100; }

/** Cała historia jednej pary (test zgodności, wykresy): transakcje { J, e0, x, ret, kind, en, TP, ex, B, P }.
 *  openEnd = true: transakcja bez wyjścia do końca danych zostaje jako otwarta (kind 'otwarta') — tylko wykresy. */
function pv2_batch_(p, X, start, openEnd) {
  const ev = pv2_events_(X, start, false).filter(e => e.open);
  const out = [];
  let last = -1;
  ev.forEach(e => {
    if (e.J <= last) return;
    const e0 = e.J + 1;
    if (e0 + PV2.HOLD > X.n && !openEnd) return;      // koniec danych (jak run_exit)
    const chk = pv2_entryCheck_(p, e, X.atr[e.J], X.t[e.J], X.o[e0]);
    if (!chk.ok) return;
    let r = null;
    for (let j = e0; j < Math.min(e0 + PV2.HOLD, X.n) && !r; j++) r = pv2_exitStep_(X, j, e0, chk.TP);
    if (!r) r = { px: X.c[X.n - 1], kind: 'otwarta', k: X.n - e0 };
    out.push({ J: e.J, e0, x: r.k, ret: pv2_ret_(p, chk.en, r.px), kind: r.kind, en: chk.en, TP: chk.TP, ex: r.px, B: e.B, P: e.P });
    last = e.J + r.k;
  });
  return out;
}

// ============================================================================
//  APPS SCRIPT: wejście z Fx.gs i z menu
// ============================================================================
/** Po fxLive_ (Fx.gs): czy któraś z 10 par ma świecę nowszą niż przeliczona — wtedy krok. */
function pv2IfDue_(fxState) {
  const st = fxState || fxStateLoad_();
  const props = PropertiesService.getScriptProperties();
  let warnMsg = '';
  try { warnMsg = pv2_alertsDue_(props); } catch (e) { recordError_('PV2', 'uprzedzenie: ' + (e.message || e)); }
  const done = JSON.parse(props.getProperty('PV2_LAST') || '{}');
  const fresh = PV2.PAIRS.some(p => st.sym[p] && st.sym[p].last && st.sym[p].last > (done[p] || 0));
  if (!fresh) return warnMsg;
  const seen = PV2.PAIRS.map(p => (st.sym[p] && st.sym[p].last) || 0).join(',');
  if (seen === props.getProperty('PV2_SEEN')) return warnMsg;             // ten stan FX już przeliczony (np. para bez świecy w Firestore)
  props.setProperty('PV2_SEEN', seen);
  return pv2Step_();
}

function pv2Now() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Automat właśnie pracuje — spróbuj za minutę.'); return; }
  try { startRun_(); toast_(pv2Step_(true) || 'Powrót.v2: brak nowych świec.'); finishRun_(marketContext_(new Date()), 'Powrót.v2 — przeliczenie z menu'); }
  catch (e) { alert_('Powrót.v2: ' + e.message); }
  finally { lock.releaseLock(); }
}

/** Menu: mail testowy (pierwsze uruchomienie prosi o zgodę Google na wysyłanie poczty). */
function pv2TestMail() {
  const prm = pv2_params_(pv2_sheet_());
  MailApp.sendEmail(prm.mail, 'IA4 Powrót.v2 — mail testowy',
    `To jest mail testowy z arkusza IA4 (Powrót.v2.Investor).\n\nSygnały przyjdą na ten adres ok. 1 min po zamknięciu świecy 1h.\n` +
    `Zmiana adresu: żółta komórka „Mail do” w zakładce ${PV2.SHEET}.`);
  toast_(`Wysłano mail testowy na ${prm.mail}.`);
}

/** Menu: inwestor od nowa — od teraz, z kapitałem z żółtej komórki. */
function pv2ResetNow() {
  const ui = SpreadsheetApp.getUi();
  if (ui.alert('Powrót.v2 od nowa: wszystkie pozycje zostaną skasowane, saldo wraca do kapitału startowego, liczy od teraz. Kontynuować?',
    ui.ButtonSet.OK_CANCEL) !== ui.Button.OK) return;
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Automat właśnie pracuje — spróbuj za minutę.'); return; }
  try {
    const store = pv2_storeLoad_();
    store.state = pv2_newState_(pv2_params_(pv2_sheet_()));
    pv2_storeSave_(store);
    startRun_();
    pv2Step_(true);
    finishRun_(marketContext_(new Date()), 'Powrót.v2 — od nowa');
    toast_('Powrót.v2 zaczyna od teraz.');
  } finally { lock.releaseLock(); }
}

function pv2_newState_(prm) {
  return { startedAt: Math.floor(Date.now() / 1000), capital: prm.capital, cash: prm.capital, seq: 0, positions: [], equity: [] };
}

// ============================================================================
//  KROK
// ============================================================================
function pv2Step_(force) {
  const sh = pv2_sheet_();
  const prm = pv2_params_(sh);
  const store = pv2_storeLoad_();
  const props = PropertiesService.getScriptProperties();
  store.cache = pv2_refreshCache_(store.cache || {});
  if (!store.state) store.state = pv2_newState_(prm);
  const S = store.state;
  const nowSec = Date.now() / 1000;
  const X = {}, newest = {};
  PV2.PAIRS.forEach(p => { if ((store.cache[p] || []).length) { X[p] = pv2_series_(store.cache[p]); newest[p] = X[p].t[X[p].n - 1]; } });
  const done = JSON.parse(props.getProperty('PV2_LAST') || '{}');
  // nowe świece wszystkich par po kolei w czasie (wspólne saldo)
  const todo = [];
  Object.keys(X).forEach(p => {
    const x = X[p], from = Math.max(done[p] || 0, S.startedAt - 3600);
    for (let j = Math.max(0, x.n - 48); j < x.n; j++) if (x.t[j] > from) todo.push({ p, j, t: x.t[j] });
  });
  todo.sort((a, b) => (a.t - b.t) || (PV2.PAIRS.indexOf(a.p) - PV2.PAIRS.indexOf(b.p)));
  const mails = [], log = [];
  const active = prm.active;
  todo.forEach(({ p, j, t }) => {
    const x = X[p];
    const pos = S.positions.find(q => q.pair === p && (q.status === 'otwarta' || q.status === 'oczekuje'));
    // 1. oczekująca: wejście po open tej świecy
    if (pos && pos.status === 'oczekuje' && t > pos.sigT) {
      const sj = x.t.indexOf(pos.sigT);
      const chk = sj >= 0 && sj + 1 === j ? pv2_entryCheck_(p, { B: pos.B, P: pos.P }, pos.A, pos.sigT, x.o[j]) : { ok: false, why: 'brak świecy wejścia' };
      if (!chk.ok) {
        pos.status = 'anulowana'; pos.exitKind = 'anulowana: ' + chk.why; pos.exitT = t;
        if (pos.mailed) mails.push(pv2_mailCancel_(pos, x.o[j], chk.why));
        else S.positions.splice(S.positions.indexOf(pos), 1);      // sygnał bez maila i bez wejścia — nie zaśmieca logu
      } else {
        const used = S.positions.filter(q => q.status === 'otwarta').reduce((a, q) => a + q.margin, 0);
        const margin = Math.min(prm.pct * S.cash, S.cash - used);
        const bu = pv2_usd_(p, X, j);
        if (margin <= 0 || !isFinite(bu)) {
          pos.status = 'anulowana'; pos.exitKind = 'anulowana: brak wolnego depozytu'; pos.exitT = t;
          if (pos.mailed) mails.push(pv2_mailCancel_(pos, x.o[j], 'brak wolnego depozytu'));
        } else {
          if (!pos.no) pos.no = ++S.seq;
          Object.assign(pos, { status: 'otwarta', entryT: t, cashAt: S.cash, entry: chk.en, TP: chk.TP, margin, notional: margin * prm.lev,
                               units: margin * prm.lev / bu, deadlineT: pv2_deadline_(t) });
          if (!pos.mailed) { mails.push(pv2_mailSignal_(pos, prm, true)); pos.mailed = true; }
        }
      }
    }
    // 2. otwarta: TP / limit czasu (świeca wejścia też)
    if (pos && pos.status === 'otwarta') {
      const e0 = x.t.indexOf(pos.entryT);
      if (e0 >= 0 && j >= e0) {
        const r = pv2_exitStep_(x, j, e0, pos.TP);
        pos.bars = j - e0 + 1; pos.lastT = t; pos.price = x.c[j];
        pos.retNow = pv2_ret_(p, pos.entry, x.c[j]);
        if (r) {
          pos.status = 'zamknięta'; pos.exitT = t; pos.exit = r.px; pos.exitKind = r.kind; pos.ret = pv2_ret_(p, pos.entry, r.px);
          pos.pnl = pos.notional * pos.ret / 100; S.cash += pos.pnl; pos.bars = r.k;
          S.equity.push([t + 3600, Math.round(S.cash * 100) / 100]);
          if (r.kind !== 'TP') mails.push(pv2_mailClose_(pos, x.c[j]));
          else if (prm.mailTp) mails.push(pv2_mailTp_(pos));
        }
      }
    }
    // 3. stop out (najgorsza cena świecy — short: szczyt)
    const opn = S.positions.filter(q => q.status === 'otwarta');
    if (opn.length) {
      let worst = 0, used = 0;
      opn.forEach(q => {
        const xx = X[q.pair], jj = xx.t.indexOf(t);
        const hi = jj >= 0 ? xx.h[jj] : (q.price || q.entry);
        worst -= q.notional * (hi - q.entry + pv2_spreadPx_(q.pair)) / q.entry; used += q.margin;
      });
      if (S.cash + worst < PV2.STOP_OUT * used) {
        opn.forEach(q => {
          const xx = X[q.pair], jj = xx.t.indexOf(t), hi = jj >= 0 ? xx.h[jj] : (q.price || q.entry);
          q.status = 'zamknięta'; q.exitT = t; q.exit = hi; q.exitKind = 'stop out'; q.ret = pv2_ret_(q.pair, q.entry, hi);
          q.pnl = q.notional * q.ret / 100; S.cash += q.pnl;
          mails.push(pv2_mailClose_(q, hi));
        });
        S.equity.push([t + 3600, Math.round(S.cash * 100) / 100]);
        log.push('STOP OUT');
      }
    }
    // 4. sygnał na tej świecy
    if (active) {
      const busy = S.positions.some(q => q.pair === p && ((q.status === 'otwarta' || q.status === 'oczekuje') || (q.status === 'zamknięta' && q.exitT >= t)));
      // wyłącznie najnowsza świeca pary (sygnałów sprzed przerwy nie nadrabiamy — wejście już minęło)
      if (!busy && j === x.n - 1 && t + 3600 > S.startedAt) {
        const ev = pv2_events_(x, Math.max(2, x.n - 200), fxSlotOpen_(fxInst_(p), t + 3600)).filter(e => e.J === j)[0];
        if (ev) {
          const A = x.atr[j];
          const proxy = pv2_entryCheck_(p, ev, A, t, x.c[j]);        // wejście ≈ zamknięcie świecy sygnału
          const hr = pv2_hourUtc_(t);
          if (hr >= PV2.H_FROM && hr <= PV2.H_TO) {
            const used = S.positions.filter(q => q.status === 'otwarta').reduce((a, q) => a + q.margin, 0);
            const margin = Math.max(0, Math.min(prm.pct * S.cash, S.cash - used));
            const bu = pv2_usd_(p, X, j);
            const q = { no: 0, pair: p, status: 'oczekuje', sigT: t, B: ev.B, P: ev.P, A, entryEst: x.c[j],
                        TP: ev.P - PV2.F * (ev.P - ev.B), margin, notional: margin * prm.lev, units: margin * prm.lev / bu,
                        deadlineT: pv2_deadline_(t + 3600), mailed: false, cashAt: S.cash };
            S.positions.push(q);
            if (proxy.ok) { q.no = ++S.seq; mails.push(pv2_mailSignal_(q, prm, false)); q.mailed = true; }
          }
        }
      }
    }
    done[p] = Math.max(done[p] || 0, t);
  });
  // uprzedzenia: świeca, która się właśnie zaczęła, może dać sygnał — mail warnMin minut po zamknięciu poprzedniej
  if (active && prm.mails && prm.warn) {
    const al = JSON.parse(props.getProperty('PV2_ALERTS') || '[]').filter(a => a.candT + 3600 > nowSec);
    Object.keys(X).forEach(p => {
      const x = X[p], t = x.t[x.n - 1], candT = t + 3600;
      if (candT + 3600 <= nowSec || al.some(a => a.pair === p && a.candT === candT)) return;           // świeca już się skończyła / jest
      if (S.positions.some(q => q.pair === p && (q.status === 'otwarta' || q.status === 'oczekuje'))) return;
      const hr = pv2_hourUtc_(candT), inst = fxInst_(p);
      if (hr < PV2.H_FROM || hr > PV2.H_TO || !fxSlotOpen_(inst, candT) || !fxSlotOpen_(inst, candT + 3600)) return;
      const a = pv2_armed_(p, x, Math.max(2, x.n - 200));
      if (!a) return;
      const used = S.positions.filter(q => q.status === 'otwarta').reduce((s_, q) => s_ + q.margin, 0);
      const margin = Math.max(0, Math.min(prm.pct * S.cash, S.cash - used)), bu = pv2_usd_(p, X, x.n - 1);
      al.push({ pair: p, candT, sendAt: t + 3600 + prm.warnMin * 60, B: a.B, P: a.P, open: a.open, lo: a.lo, TP: a.TP,
                margin, notional: margin * prm.lev, lots: margin * prm.lev / bu / 100000, lev: prm.lev, mail: prm.mail,
                again: S.lastWarnB === p + ':' + a.B });
      S.lastWarnB = p + ':' + a.B;
    });
    props.setProperty('PV2_ALERTS', JSON.stringify(al));
  }
  // wysyłka maili (po przeliczeniu — jeden mail na zdarzenie)
  let sent = 0;
  if (prm.mails) mails.forEach(m => {
    try { MailApp.sendEmail({ to: prm.mail, subject: m.subject, body: m.body }); sent++; }
    catch (e) { recordError_('PV2', 'mail: ' + (e.message || e)); }
  });
  S.lastT = Math.max.apply(null, Object.keys(newest).map(p => newest[p]).concat([S.lastT || 0]));
  pv2_storeSave_(store);
  props.setProperty('PV2_LAST', JSON.stringify(done));
  pv2_writeSheet_(sh, S, prm, X);
  try { pv2_publish_(S, prm, X, store.cache); } catch (e) { console.warn('pv2.json: ' + e.message); }
  const opened = S.positions.filter(q => q.status === 'otwarta').length;
  const msg = todo.length || force ? `Powrót.v2: świec ${todo.length}, otwarte ${opened}, saldo ${Math.round(S.cash * 100) / 100} $` +
    (mails.length ? `, maile ${sent}/${mails.length}` : '') + (log.length ? ' · ' + log.join(', ') : '') : '';
  if (msg) log_('INFO', 'PV2', msg);
  return msg;
}

/** Wartość 1 jednostki waluty bazowej w USD (open świecy j; pary z USD w cache). */
function pv2_usd_(p, X, j) {
  const base = p.slice(0, 3);
  if (base === 'USD') return 1;
  const q = { EUR: 'EURUSD', GBP: 'GBPUSD', AUD: 'AUDUSD', NZD: 'NZDUSD' }[base];
  const x = X[q];
  if (!x) return NaN;
  const tj = X[p] ? X[p].t[j] : null;
  let k = tj ? x.t.indexOf(tj) : -1;
  if (k < 0) k = x.n - 1;
  return x.o[k];
}

/** Początek świecy, po której zamknięciu mija limit 60 świec (świece w godzinach rynku FX), → zamknięcie (s). */
function pv2_deadline_(entryT) {
  const inst = fxInst_('EURUSD');
  let t = entryT, k = 1;
  while (k < PV2.HOLD) { t += 3600; if (fxSlotOpen_(inst, t)) k++; }
  return t + 3600;
}

// ============================================================================
//  ŚWIECE: pamięć ostatnich 640 świec każdej pary (_PV2_DANE), dociągana z Firestore fx1h
// ============================================================================
function pv2_refreshCache_(cache) {
  const reqs = PV2.PAIRS.map(p => {
    const have = cache[p] || [];
    const limit = have.length >= PV2.CACHE - 30 ? 3 : 60;            // pierwszy raz: ok. 60 dni
    return { p, limit, req: {
      url: `https://firestore.googleapis.com/v1/${fsBase_()}/${FX.COLL}/${p}:runQuery`,
      method: 'post', contentType: 'application/json', muteHttpExceptions: true,
      headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
      payload: JSON.stringify({ structuredQuery: { from: [{ collectionId: 'days' }],
        orderBy: [{ field: { fieldPath: 'date' }, direction: 'DESCENDING' }], limit } }) } };
  });
  const resps = UrlFetchApp.fetchAll(reqs.map(r => r.req));
  reqs.forEach((r, i) => {
    if (resps[i].getResponseCode() !== 200) { recordError_('PV2', `Firestore ${r.p}: HTTP ${resps[i].getResponseCode()}`); return; }
    const bars = {};
    (cache[r.p] || []).forEach(b => { bars[b.t] = b; });
    JSON.parse(resps[i].getContentText()).forEach(row => {
      if (!row.document) return;
      const f = row.document.fields || {};
      const date = f.date && f.date.stringValue;
      if (!date) return;
      pv2_docBars_(f, date).forEach(b => { bars[b.t] = b; });
    });
    cache[r.p] = Object.keys(bars).map(Number).sort((a, b) => a - b).slice(-PV2.CACHE).map(t => bars[t]);
  });
  return cache;
}

/** Dokument dnia fx1h → świece (także uśrednione, f = 1). */
function pv2_docBars_(f, date) {
  const t0 = fxDayStart_(date);
  const num = v => Number(v.doubleValue !== undefined ? v.doubleValue : v.integerValue);
  const a = k => ((f[k] && f[k].arrayValue && f[k].arrayValue.values) || []).map(num);
  const tt = a('t'), o = a('o'), h = a('h'), l = a('l'), c = a('c');
  const fill = {};
  a('fillT').forEach(m => { fill[t0 + m * 60] = 1; });
  const out = [];
  for (let i = 0; i < tt.length; i++) {
    const t = t0 + tt[i] * 60;
    out.push({ t, o: o[i], h: h[i], l: l[i], c: c[i], f: fill[t] ? 1 : 0 });
  }
  return out;
}

function pv2_storeSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(PV2.STORE_SHEET);
  if (!sh) { sh = ss.insertSheet(PV2.STORE_SHEET); sh.hideSheet(); }
  return sh;
}

function pv2_storeLoad_() {
  const sh = pv2_storeSheet_(), out = {};
  ['cache', 'state'].forEach((name, r) => {
    const n = Number(sh.getRange(r + 1, 2).getValue() || 0);
    if (!n) return;
    try { out[name] = JSON.parse(sh.getRange(r + 1, 3, 1, n).getValues()[0].join('')); }
    catch (e) { console.warn('_PV2_DANE ' + name + ': ' + e.message); }
  });
  return out;
}

function pv2_storeSave_(store) {
  const sh = pv2_storeSheet_();
  ['cache', 'state'].forEach((name, r) => {
    const txt = JSON.stringify(store[name] || null);
    const parts = [];
    for (let i = 0; i < txt.length; i += PV2.CHUNK) parts.push(txt.slice(i, i + PV2.CHUNK));
    const need = parts.length + 2;
    if (sh.getMaxColumns() < need) sh.insertColumnsAfter(sh.getMaxColumns(), need - sh.getMaxColumns());
    sh.getRange(r + 1, 1, 1, sh.getMaxColumns()).clearContent();
    sh.getRange(r + 1, 1, 1, need).setValues([[name, parts.length].concat(parts)]);
  });
}

// ============================================================================
//  MAILE
// ============================================================================
/** Co minutę (pv2IfDue_): uprzedzenia, którym minął czas wysyłki, a świeca jeszcze trwa → mail z ceną z Yahoo. */
function pv2_alertsDue_(props) {
  const all = JSON.parse(props.getProperty('PV2_ALERTS') || '[]');
  if (!all.length) return '';
  const now = Date.now() / 1000;
  const due = all.filter(a => !a.sent && a.sendAt <= now && now < a.candT + 3600 - 120);
  const keep = all.filter(a => a.candT + 3600 > now && !due.includes(a));
  if (!due.length) { if (keep.length !== all.length) props.setProperty('PV2_ALERTS', JSON.stringify(keep)); return ''; }
  let quotes = {};
  try {
    const res = fxFetchMany_(due.map(a => ({ inst: fxInst_(a.pair), p1: a.candT - 3600, p2: now })));
    due.forEach(a => {
      const r = res[a.pair];
      if (!r || r.error || !r.result) return;
      const ts = r.result.timestamp || [], q = (r.result.indicators && r.result.indicators.quote && r.result.indicators.quote[0]) || {};
      let open = null, last = r.result.meta && r.result.meta.regularMarketPrice;
      for (let i = 0; i < ts.length; i++) if (ts[i] >= a.candT && typeof q.open[i] === 'number') { if (open === null) open = q.open[i]; if (typeof q.close[i] === 'number') last = q.close[i]; }
      quotes[a.pair] = { open, last };
    });
  } catch (e) { quotes = {}; }
  due.forEach(a => {
    const m = pv2_mailWarn_(a, quotes[a.pair] || {});
    MailApp.sendEmail({ to: a.mail, subject: m.subject, body: m.body });
  });
  props.setProperty('PV2_ALERTS', JSON.stringify(keep));
  const msg = `Powrót.v2: uprzedzenie ${due.map(a => a.pair).join(', ')}`;
  log_('INFO', 'PV2', msg);
  return msg;
}

function pv2_mailWarn_(a, q) {
  const p = a.pair, op = q.open || a.open, now = q.last;
  const state = now === undefined || now === null ? '' : `\nTeraz: ${pv2_px_(p, now)} — świeca na razie ${now < op ? 'CZERWONA (sygnał byłby, gdyby tak się zamknęła' + (now >= a.lo ? ')' : ', ale za nisko — poniżej dolnej granicy)') : 'zielona albo płaska (sygnału na razie nie ma)'}.`;
  return {
    subject: `IA4 Powrót.v2: UWAGA ${p} — możliwy sygnał o ${pv2_pl_(a.candT + 3600).slice(11)}${a.again ? ' (ten sam wzrost)' : ''}`,
    body: `Za ok. ${Math.max(1, Math.round((a.candT + 3600 - Date.now() / 1000) / 60))} min, po zamknięciu świecy ${pv2_pl_(a.candT).slice(11)}–${pv2_pl_(a.candT + 3600).slice(11)} (PL), może przyjść sygnał SHORT ${p}.\n\n` +
      `Był gwałtowny wzrost (baza — cena sprzed wzrostu: ${pv2_px_(p, a.B)}, szczyt: ${pv2_px_(p, a.P)}).\n` +
      `Sygnał będzie, jeśli ta świeca zamknie się poniżej swojego otwarcia (${pv2_px_(p, op)}) i nie niżej niż ok. ${pv2_px_(p, a.lo)}.${state}\n\n` +
      `Gdyby sygnał przyszedł: TP ok. ${pv2_px_(p, a.TP)} (wyższy szczyt w tej świecy podniesie TP), bez SL, limit 60 świec; ` +
      `kwota ok. ${a.margin.toFixed(2)} $ depozytu = ${a.notional.toFixed(2)} $ przy 1:${a.lev} (${a.lots.toFixed(4)} lota).\n\n` +
      `To tylko uprzedzenie — w historii ok. 1 na 3 takie sytuacje kończy się sygnałem. Nie wchodź przed mailem „SHORT” ok. 1 min po zamknięciu świecy.`,
  };
}

function pv2_pl_(t) { return Utilities.formatDate(new Date(t * 1000), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm'); }
function pv2_px_(p, v) { return v === undefined || v === null || !isFinite(v) ? '—' : v.toFixed(/JPY$/.test(p) ? 3 : 5); }
function pv2_lots_(q) { return q.units / 100000; }

function pv2_mailSignal_(q, prm, late) {
  const lots = pv2_lots_(q), pips = (q.entryEst || q.entry) - q.TP;
  const warn = lots < 0.01 ? `\nUWAGA: ${lots.toFixed(4)} lota to mniej niż minimalne 0,01 lota w XTB — ta pozycja wymagałaby depozytu ok. ${(0.01 * 100000 * (q.notional / q.units) / prm.lev).toFixed(0)} $.` : '';
  return {
    subject: `IA4 Powrót.v2: SHORT ${q.pair} — TP ${pv2_px_(q.pair, q.TP)}${late ? ' (wejście teraz)' : ''}`,
    body: `${late ? 'Wejście potwierdzone na otwarciu świecy' : 'Sygnał po zamknięciu świecy'} — strategia FX-POWRÓT v2 (paper trading IA4).\n\n` +
      `Para: ${q.pair}\nKierunek: SHORT (sprzedaż)\n` +
      `Wejście: ${late ? 'po cenie ' + pv2_px_(q.pair, q.entry) : 'teraz, po otwarciu następnej świecy (ok. ' + pv2_px_(q.pair, q.entryEst) + ')'}\n` +
      `TP: ${pv2_px_(q.pair, q.TP)}  (ok. ${(pips / pv2_pip_(q.pair)).toFixed(1)} pipsa od wejścia; połowa drogi do ceny sprzed wzrostu ${pv2_px_(q.pair, q.B)})\n` +
      `SL: brak (strategia bez SL — wyjście TP albo limit czasu)\n` +
      `Kwota: depozyt ${q.margin.toFixed(2)} $ (${Math.round(prm.pct * 100)}% salda ${(Math.round(q.cashAt * 100) / 100).toFixed(2)} $), ` +
      `wartość pozycji ${q.notional.toFixed(2)} $ przy 1:${prm.lev} = ${lots.toFixed(4)} lota${warn}\n` +
      `Limit czasu: zamknąć najpóźniej ${pv2_pl_(q.deadlineT)} (PL) — przyjdzie osobny mail.\n\n` +
      `Świeca sygnału: ${pv2_pl_(q.sigT)}–${pv2_pl_(q.sigT + 3600).slice(11)} (PL). Szczyt ruchu: ${pv2_px_(q.pair, q.P)}.\n` +
      `Arkusz: zakładka ${PV2.SHEET}. Strona: zakładka FX → Powrót.v2.`,
  };
}

function pv2_mailCancel_(q, open, why) {
  return { subject: `IA4 Powrót.v2: ANULUJ ${q.pair} — sygnał nieważny`,
    body: `Sygnał ${q.pair} z ${pv2_pl_(q.sigT)} (PL) został anulowany na otwarciu świecy (open ${pv2_px_(q.pair, open)}): ${why}.\n` +
      `Jeśli już otworzyłeś pozycję — zamknij ją. Paper trading IA4 tej transakcji nie liczy.` };
}

function pv2_mailClose_(q, px) {
  const why = q.exitKind === 'stop out' ? 'STOP OUT rachunku (poziom depozytu < 50%)' : 'minął limit 60 świec bez TP';
  return { subject: `IA4 Powrót.v2: ZAMKNIJ ${q.pair} — ${q.exitKind === 'stop out' ? 'stop out' : 'limit czasu'}`,
    body: `Zamknij teraz pozycję SHORT ${q.pair} po cenie rynkowej (ok. ${pv2_px_(q.pair, px)}): ${why}.\n\n` +
      `Wejście ${pv2_pl_(q.entryT)} po ${pv2_px_(q.pair, q.entry)}, TP był ${pv2_px_(q.pair, q.TP)}.\n` +
      `Wynik paper tradingu: ${q.ret >= 0 ? '+' : ''}${q.ret.toFixed(3)}% = ${q.pnl >= 0 ? '+' : ''}${q.pnl.toFixed(2)} $ (świec w pozycji: ${q.bars}).` };
}

function pv2_mailTp_(q) {
  return { subject: `IA4 Powrót.v2: TP ${q.pair} osiągnięty`,
    body: `SHORT ${q.pair}: TP ${pv2_px_(q.pair, q.TP)} osiągnięty (${pv2_pl_(q.exitT)}–${pv2_pl_(q.exitT + 3600).slice(11)} PL).\n` +
      `Wynik: ${q.ret >= 0 ? '+' : ''}${q.ret.toFixed(3)}% = ${q.pnl >= 0 ? '+' : ''}${q.pnl.toFixed(2)} $, świec w pozycji: ${q.bars}.` };
}

// ============================================================================
//  ARKUSZ Powrót.v2.Investor: żółte parametry na górze, statystyki, log transakcji
// ============================================================================
const PV2_PARAMS = [
  ['Kapitał startowy ($)', 'capital'], ['Depozyt na pozycję (% salda)', 'pct'], ['Dźwignia (1:x)', 'lev'],
  ['Mail do', 'mail'], ['Maile z sygnałami (TAK/NIE)', 'mails'], ['Mail także przy TP (TAK/NIE)', 'mailTp'], ['Inwestor aktywny (TAK/NIE)', 'active'],
  ['Uprzedzenie „możliwy sygnał” (TAK/NIE)', 'warn'], ['Uprzedzenie: minut po zamknięciu świecy', 'warnMin'],
];
const PV2_NOTE_ROW = 4 + 9 + 1;      // wiersz opisu pod parametrami
const PV2_STATS = ['Liczy od (PL)', 'Saldo — kapitał + zamknięte ($)', 'Wynik zamkniętych ($)', 'Wynik otwartych ($)',
  'Saldo, gdyby teraz zamknąć wszystko ($)', 'Wynik całkowity (% kapitału)', 'Pozycji otwartych / oczekujących', 'Transakcji zamkniętych',
  'Zamknięte: TP / limit czasu / stop out', 'Średni wynik zamkniętej (%)', 'Mediana świec w pozycji', 'Ostatnia przeliczona świeca (PL)'];

function pv2_sheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(PV2.SHEET);
  if (sh) { pv2_migrate_(sh); return sh; }
  sh = ss.insertSheet(PV2.SHEET);
  sh.setTabColor('#e37400');
  if (sh.getMaxColumns() < PV2_COLS.length) sh.insertColumnsAfter(sh.getMaxColumns(), PV2_COLS.length - sh.getMaxColumns());
  sh.getRange(1, 1, 1, 10).merge().setValue('IA 4 — POWRÓT.V2 INVESTOR (paper trading FX-POWRÓT v2: short po gwałtownym wzroście, 10 par 1h)')
    .setFontSize(13).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(3, 1, 1, 2).setValues([['PARAMETRY (żółte — można zmieniać)', '']]).setFontWeight('bold').setBackground('#f1f3f4');
  const D = PV2.DEFAULTS;
  sh.getRange(4, 1, PV2_PARAMS.length, 2).setValues(PV2_PARAMS.map(([lab, k]) => [lab, D[k]]));
  sh.getRange(4, 2, PV2_PARAMS.length, 1).setBackground('#ffff00').setFontColor('#0000ff');
  sh.getRange(5, 2).setNumberFormat('0%');
  sh.getRange(4, 1, PV2_PARAMS.length, 1).setFontWeight('bold');
  sh.getRange(PV2_NOTE_ROW, 1, 1, 2).merge().setValue('Zmiana kapitału startowego działa po „IA 4 → Powrót.v2 — zacznij od nowa”. Depozyt i dźwignia — od następnej transakcji.')
    .setFontStyle('italic').setFontColor('#555555').setWrap(true);
  sh.getRange(3, 4, 1, 2).setValues([['STATYSTYKI', '']]).setFontWeight('bold').setBackground('#f1f3f4');
  sh.getRange(4, 4, PV2_STATS.length, 1).setValues(PV2_STATS.map(x => [x])).setFontWeight('bold');
  sh.getRange(3, 7, 1, 2).setValues([['REGUŁY (zamrożone, instrukcja 7b)', '']]).setFontWeight('bold').setBackground('#f1f3f4');
  const rules = [['Impuls', 'świeca zamyka się ≥ 2 ATR(100) wyżej niż poprzednia'], ['Sygnał', 'pierwsza czerwona świeca w ciągu 3 świec, 7–16 UTC'],
    ['Wejście', 'SHORT po open następnej świecy, ≥ 0,5 ATR nad bazą'], ['TP', 'połowa drogi od szczytu do ceny sprzed wzrostu (≥ 1 × spread)'],
    ['SL', 'brak'], ['Limit', '60 świec 1h — potem zamknięcie (mail)'], ['Pary', PV2.PAIRS.join(', ')],
    ['Spread (pipsy)', PV2.PAIRS.map(p => `${p} ${PV2.SPREAD[p]}`).join(', ')]];
  sh.getRange(4, 7, rules.length, 2).setValues(rules);
  sh.getRange(4, 7, rules.length, 1).setFontWeight('bold');
  sh.getRange(PV2.LOG_ROW - 1, 1, 1, 10).merge().setValue('TRANSAKCJE (otwarte i oczekujące na górze, potem zamknięte — najnowsze pierwsze)')
    .setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(PV2.LOG_ROW, 1, 1, PV2_COLS.length).setValues([PV2_COLS]).setFontWeight('bold').setBackground('#f1f3f4').setWrap(true);
  sh.setFrozenRows(0);
  sh.setColumnWidth(1, 220); sh.setColumnWidth(2, 110); sh.setColumnWidth(4, 260); sh.setColumnWidth(5, 120); sh.setColumnWidth(7, 110); sh.setColumnWidth(8, 330);
  return sh;
}

/** Arkusz z 1.53 (7 parametrów, opis w wierszu 12) → nowe parametry dopisane, stare wartości zostają. */
function pv2_migrate_(sh) {
  const n = PV2_PARAMS.length, lab = sh.getRange(4, 1, n, 1).getValues().map(r => r[0]);
  if (lab.join('|') === PV2_PARAMS.map(x => x[0]).join('|')) return;
  const old = {};
  sh.getRange(4, 1, 7, 2).getValues().forEach(r => { const k = PV2_PARAMS.find(x => x[0] === r[0]); if (k) old[k[1]] = r[1]; });
  sh.getRange(4, 1, n + 8, 2).breakApart().clearContent().setBackground(null).setFontColor(null).setFontStyle(null);
  sh.getRange(4, 1, n, 2).setValues(PV2_PARAMS.map(([l, k]) => [l, old[k] !== undefined && old[k] !== '' ? old[k] : PV2.DEFAULTS[k]]));
  sh.getRange(4, 2, n, 1).setBackground('#ffff00').setFontColor('#0000ff');
  sh.getRange(5, 2).setNumberFormat('0%');
  sh.getRange(4, 1, n, 1).setFontWeight('bold');
  sh.getRange(PV2_NOTE_ROW, 1, 1, 2).merge().setValue('Zmiana kapitału startowego działa po „IA 4 → Powrót.v2 — zacznij od nowa”. Depozyt i dźwignia — od następnej transakcji.')
    .setFontStyle('italic').setFontColor('#555555').setWrap(true);
}

function pv2_params_(sh) {
  const v = sh.getRange(4, 2, PV2_PARAMS.length, 1).getValues().map(r => r[0]);
  const D = PV2.DEFAULTS, out = {};
  PV2_PARAMS.forEach(([, k], i) => { out[k] = (v[i] === '' || v[i] === null) ? D[k] : v[i]; });
  out.capital = Number(out.capital) > 0 ? Number(out.capital) : D.capital;
  let pct = Number(out.pct);
  if (pct > 1) pct /= 100;                               // wpisane „20” zamiast „20%”
  out.pct = pct > 0 && pct <= 1 ? pct : D.pct;
  out.lev = Number(out.lev) > 0 ? Number(out.lev) : D.lev;
  const yes = x => String(x).trim().toUpperCase().startsWith('T');
  out.mails = yes(out.mails); out.mailTp = yes(out.mailTp); out.active = yes(out.active); out.warn = yes(out.warn);
  out.warnMin = Math.min(55, Math.max(1, Number(out.warnMin) || D.warnMin));
  out.mail = String(out.mail || D.mail).trim();
  return out;
}

function pv2_writeSheet_(sh, S, prm, X) {
  const P = S.positions;
  const closed = P.filter(q => q.status === 'zamknięta'), open = P.filter(q => q.status === 'otwarta'), pend = P.filter(q => q.status === 'oczekuje');
  const unreal = open.reduce((a, q) => a + q.notional * (q.retNow || 0) / 100, 0);
  const real = closed.reduce((a, q) => a + q.pnl, 0);
  const cnt = k => closed.filter(q => q.exitKind && q.exitKind.indexOf(k) === 0).length;
  const bars = closed.map(q => q.bars).sort((a, b) => a - b);
  sh.getRange(4, 5, PV2_STATS.length, 1).setValues([
    [pv2_pl_(S.startedAt)], [Math.round(S.cash * 100) / 100], [Math.round(real * 100) / 100], [Math.round(unreal * 100) / 100],
    [Math.round((S.cash + unreal) * 100) / 100], [(S.cash + unreal) / S.capital - 1], [`${open.length} / ${pend.length}`], [closed.length],
    [`${cnt('TP')} / ${cnt('czas')} / ${cnt('stop')}`], [closed.length ? closed.reduce((a, q) => a + q.ret, 0) / closed.length / 100 : ''],
    [bars.length ? bars[Math.floor(bars.length / 2)] : ''], [S.lastT ? pv2_pl_(S.lastT) : '']]);
  sh.getRange(9, 5).setNumberFormat('+0.00%;-0.00%;0.00%'); sh.getRange(13, 5).setNumberFormat('+0.000%;-0.000%;0.000%');
  const order = { 'otwarta': 0, 'oczekuje': 1, 'zamknięta': 2, 'anulowana': 3 };
  const pl = t => t ? pv2_pl_(t) : '';
  const rows = P.slice().sort((a, b) => (order[a.status] - order[b.status]) || (b.no - a.no)).map(q => [
    q.no, q.pair, 'short', pl(q.sigT), pl(q.entryT), q.entry !== undefined ? q.entry : '', q.TP, q.B, q.P,
    q.margin !== undefined ? Math.round(q.margin * 100) / 100 : '', q.notional !== undefined ? Math.round(q.notional * 100) / 100 : '',
    q.units ? Math.round(pv2_lots_(q) * 10000) / 10000 : '',
    q.status === 'oczekuje' ? 'oczekuje (wejście na otwarciu następnej świecy)' : q.status,
    pl(q.lastT), q.price !== undefined ? q.price : '',
    q.status === 'zamknięta' ? q.ret / 100 : (q.retNow !== undefined && q.status === 'otwarta' ? q.retNow / 100 : ''),
    q.status === 'zamknięta' ? Math.round(q.pnl * 100) / 100 : (q.status === 'otwarta' && q.retNow !== undefined ? Math.round(q.notional * q.retNow) / 100 : ''),
    q.status === 'zamknięta' ? pl(q.exitT) : '', q.exit !== undefined ? q.exit : '', q.exitKind || '', q.bars || '', pl(q.deadlineT),
    q.mailed ? 'tak' : 'nie']);
  const first = PV2.LOG_ROW + 1, old = sh.getLastRow() - first + 1;
  if (old > 0) sh.getRange(first, 1, old, PV2_COLS.length).clearContent();
  if (rows.length) {
    if (sh.getMaxRows() < first + rows.length) sh.insertRowsAfter(sh.getMaxRows(), first + rows.length - sh.getMaxRows());
    sh.getRange(first, 1, rows.length, PV2_COLS.length).setValues(rows);
    sh.getRange(first, 16, rows.length, 1).setNumberFormat('+0.000%;-0.000%;0.000%');
  }
}

// ============================================================================
//  telemetry/pv2.json — strona IA4: zakładka FX → Powrót.v2 (świece, transakcje, symulacja)
// ============================================================================
function pv2_publish_(S, prm, X, cache) {
  const props = PropertiesService.getScriptProperties();
  if (!props.getProperty('GITHUB_TOKEN')) return false;
  const r = (p, v) => v === undefined || v === null || !isFinite(v) ? null : Number(v.toFixed(/JPY$/.test(p) ? 3 : 5));
  const pairs = {}, sim = [];
  PV2.PAIRS.forEach(p => {
    const x = X[p];
    if (!x) return;
    const from = Math.max(0, x.n - PV2.CHART);
    pairs[p] = { pip: pv2_pip_(p), spread: PV2.SPREAD[p],
      candles: x.t.slice(from).map((t, k) => [t, r(p, x.o[from + k]), r(p, x.h[from + k]), r(p, x.l[from + k]), r(p, x.c[from + k])]) };
    // symulacja na pamięci świec (te same reguły) — transakcje, które wypadają na wykresie
    pv2_batch_(p, x, 2, true).forEach(tr => {
      if (tr.e0 + tr.x - 1 < from) return;
      sim.push({ pair: p, sigT: x.t[tr.J], entryT: x.t[tr.e0], exitT: x.t[tr.e0 + tr.x - 1], entry: r(p, tr.en), tp: r(p, tr.TP), exit: r(p, tr.ex),
                 base: r(p, tr.B), peak: r(p, tr.P), kind: tr.kind, ret: Number(tr.ret.toFixed(4)), bars: tr.x });
    });
  });
  const P = S.positions.map(q => ({ no: q.no, pair: q.pair, status: q.status, sigT: q.sigT, entryT: q.entryT || null, exitT: q.exitT || null,
    entry: r(q.pair, q.entry !== undefined ? q.entry : q.entryEst), tp: r(q.pair, q.TP), base: r(q.pair, q.B), peak: r(q.pair, q.P),
    exit: r(q.pair, q.exit), price: r(q.pair, q.price), kind: q.exitKind || null, ret: q.ret !== undefined ? Number(q.ret.toFixed(4)) : (q.retNow !== undefined ? Number(q.retNow.toFixed(4)) : null),
    pnl: q.pnl !== undefined ? Math.round(q.pnl * 100) / 100 : null, margin: q.margin !== undefined ? Math.round(q.margin * 100) / 100 : null,
    notional: q.notional !== undefined ? Math.round(q.notional * 100) / 100 : null, lots: q.units ? Number(pv2_lots_(q).toFixed(4)) : null,
    bars: q.bars || null, deadlineT: q.deadlineT || null, mailed: !!q.mailed }));
  const closed = S.positions.filter(q => q.status === 'zamknięta');
  const unreal = S.positions.filter(q => q.status === 'otwarta').reduce((a, q) => a + q.notional * (q.retNow || 0) / 100, 0);
  const doc = { version: CONFIG.VERSION, generatedAt: new Date().toISOString(), lastT: S.lastT || null,
    params: { capital: S.capital, pct: prm.pct, lev: prm.lev, mails: prm.mails, active: prm.active, startedAt: S.startedAt },
    rules: { k: PV2.K, wait: PV2.WAIT, hours: [PV2.H_FROM, PV2.H_TO], dist: PV2.DIST, f: PV2.F, hold: PV2.HOLD, minTpSpread: PV2.MINTP },
    summary: { cash: Math.round(S.cash * 100) / 100, unrealized: Math.round(unreal * 100) / 100, closed: closed.length,
      open: S.positions.filter(q => q.status === 'otwarta').length, pending: S.positions.filter(q => q.status === 'oczekuje').length,
      tp: closed.filter(q => q.exitKind === 'TP').length, avgPct: closed.length ? closed.reduce((a, q) => a + q.ret, 0) / closed.length : null },
    equity: S.equity, positions: P, sim, pairs };
  const body = JSON.parse(JSON.stringify(doc));
  delete body.generatedAt;
  const raw = Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, JSON.stringify(body), Utilities.Charset.UTF_8);
  const hash = raw.map(b => ((b & 0xFF) + 0x100).toString(16).slice(1)).join('');
  if (hash === props.getProperty('PV2_HASH')) return false;
  telemetryGithubPut_(PV2.PUB_PATH, JSON.stringify(doc), `PV2 ${S.lastT ? pv2_pl_(S.lastT) : ''}`.trim());
  props.setProperty('PV2_HASH', hash);
  return true;
}
