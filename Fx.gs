/**
 * ============================================================================
 *  IA 4 — MODUŁ EURUSD  (Yahoo EURUSD=X, świece 5 min → Firestore fx/EURUSD)
 *
 *  Wersja projektu: 1.15 (2026-10-04) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Osobny moduł (instrukcja, sekcja 4b): na razie tylko zbiera dane. Nie bierze
 *  udziału w poszukiwaniu, weryfikacji ani paper tradingu.
 *
 *  • fxIfDue_() woła runCollector (Code.gs) w każdym uruchomieniu (co minutę)
 *    i co 10 s w szybkiej pętli po zamknięciu świecy akcji — jeden trigger dla
 *    całego automatu, bo dzienny czas pracy triggerów jest limitowany.
 *  • Yahoo jest pytane tylko wtedy, gdy powinna już być zamknięta świeca nowsza
 *    niż ostatnia zapisana, i tylko w godzinach rynku walutowego
 *    (niedziela 17:00 – piątek 17:00 czasu Nowego Jorku).
 *  • Dokument dnia (UTC) jest przepisywany w całości przy każdej nowej świecy.
 *  • Pierwsze uruchomienie: historia z Yahoo — ostatnie 59 dni (granica Yahoo dla 5 min: 60 dni).
 *  • Raz na dobę (po 00:20 UTC) przepisuje cały wczorajszy dzień — łapie poprawki i braki.
 *  • Opóźnienie świecy = chwila potwierdzenia zapisu w Firestore − zamknięcie świecy.
 *  Stan: Script Properties FX_STATE. Wyniki: 3 wiersze w STATS, pole fx w telemetrii.
 * ============================================================================
 */

const FX = {
  NAME: 'EURUSD',               // dokument fx/EURUSD
  YAHOO: 'EURUSD=X',
  STEP_SEC: 300,                // świeca 5 min
  FIRST_FETCH_SEC: 5,           // pytamy Yahoo najwcześniej tyle sekund po zamknięciu świecy
  HISTORY_DAYS: 59,             // pierwsze pobranie: tyle dni wstecz
  REFRESH_AFTER_MIN: 20,        // dzienne przepisanie wczorajszego dnia: po 00:20 UTC
  OPEN_DOW: 7, OPEN_MIN: 17 * 60 - 5,     // niedziela 16:55 ET (z zapasem)
  CLOSE_DOW: 5, CLOSE_MIN: 17 * 60 + 10,  // piątek 17:10 ET (z zapasem)
};

function fxStateLoad_() {
  return JSON.parse(PropertiesService.getScriptProperties().getProperty('FX_STATE') || '{}');
}
function fxStateSave_(st) {
  PropertiesService.getScriptProperties().setProperty('FX_STATE', JSON.stringify(st));
}

/** Czy rynek walutowy jest otwarty (z zapasem): od niedzieli 17:00 do piątku 17:00 ET. */
function fxMarketOpen_(now) {
  const dow = isoWeekday_(Utilities.formatDate(now, CONFIG.MARKET_TZ, 'yyyy-MM-dd'));
  const min = minutesOf_(now, CONFIG.MARKET_TZ);
  if (dow === 6) return false;
  if (dow === FX.OPEN_DOW) return min >= FX.OPEN_MIN;
  if (dow === FX.CLOSE_DOW) return min < FX.CLOSE_MIN;
  return true;
}

/**
 * Wołane z runCollector. Zwraca opis albo ''. force = true (menu) — pobiera bez sprawdzania terminu.
 */
function fxIfDue_(force) {
  const st = fxStateLoad_();
  const now = Date.now();
  if (!st.last) {                                          // pierwsze uruchomienie: historia 59 dni
    if (!force && now - (st.historyTry || 0) < 30 * 60000) return '';   // po błędzie — ponowienie co 30 min
    st.historyTry = now;
    fxStateSave_(st);
    return fxHistory_(st);
  }
  const msgs = [];
  const r = fxRefreshIfDue_(st);
  if (r) msgs.push(r);
  const nextClose = (st.last + 2 * FX.STEP_SEC) * 1000;    // zamknięcie świecy następnej po ostatniej zapisanej
  const due = now >= nextClose + FX.FIRST_FETCH_SEC * 1000 && fxMarketOpen_(new Date(now));
  if (force || due) msgs.push(fxLive_(st));
  return msgs.filter(x => x).join(' · ');
}

/** Świece z odpowiedzi Yahoo: [{ t: start (s, wielokrotność 300), o, h, l, c }], tylko zamknięte. */
function fxBars_(result, nowSec) {
  const ts = result.timestamp || [];
  const q = (result.indicators && result.indicators.quote && result.indicators.quote[0]) || {};
  const byT = {};
  for (let i = 0; i < ts.length; i++) {
    const o = q.open && q.open[i], h = q.high && q.high[i], l = q.low && q.low[i], c = q.close && q.close[i];
    if ([o, h, l, c].some(x => typeof x !== 'number' || !isFinite(x) || x <= 0)) continue;
    const t = Math.floor(ts[i] / FX.STEP_SEC) * FX.STEP_SEC;
    if (t + FX.STEP_SEC > nowSec) continue;                 // świeca jeszcze trwa
    const r6 = x => Math.round(x * 1e6) / 1e6;
    byT[t] = { t, o: r6(o), h: r6(Math.max(h, o, c)), l: r6(Math.min(l, o, c)), c: r6(c) };   // późniejszy wpis wygrywa
  }
  return Object.keys(byT).map(Number).sort((a, b) => a - b).map(t => byT[t]);
}

function fxDay_(t) { return Utilities.formatDate(new Date(t * 1000), 'UTC', 'yyyy-MM-dd'); }

function fxFetch_(p1, p2) {
  const r = fetchYahooMany_([FX.YAHOO], `interval=5m&period1=${Math.floor(p1)}&period2=${Math.floor(p2)}&includePrePost=false`)[FX.YAHOO];
  if (r.error) throw new Error(r.error);
  return r.result;
}

/** Zapisuje całe dni (UTC), w których są świece z listy. Zwraca liczbę dokumentów dnia. */
function fxWriteDays_(bars, onlyDays) {
  const nowIso = new Date().toISOString();
  const base = `${fsBase_()}/fx/${FX.NAME}`;
  const byDay = {};
  bars.forEach(b => { const d = fxDay_(b.t); if (!onlyDays || onlyDays[d]) (byDay[d] = byDay[d] || []).push(b); });
  const days = Object.keys(byDay).sort();
  if (!days.length) return 0;
  const arr = (vals, int) => ({ arrayValue: { values: vals.map(v => int ? { integerValue: String(v) } : { doubleValue: v }) } });
  const writes = days.map(d => {
    const list = byDay[d];
    const t0 = Date.parse(d + 'T00:00:00Z') / 1000;
    return {
      update: {
        name: `${base}/days/${d}`,
        fields: {
          symbol: { stringValue: FX.NAME }, date: { stringValue: d }, bars: { integerValue: String(list.length) },
          t: arr(list.map(b => (b.t - t0) / 60), true),
          o: arr(list.map(b => b.o)), h: arr(list.map(b => b.h)), l: arr(list.map(b => b.l)), c: arr(list.map(b => b.c)),
          updatedAt: { timestampValue: nowIso },
        },
      },
    };
  });
  const last = bars[bars.length - 1];
  writes.push({
    update: {
      name: base,
      fields: {
        symbol: { stringValue: FX.NAME }, yahoo: { stringValue: FX.YAHOO }, interval: { stringValue: '5m' },
        lastDate: { stringValue: fxDay_(last.t) },
        lastTime: { stringValue: Utilities.formatDate(new Date(last.t * 1000), 'UTC', 'HH:mm') },
        lastClose: { doubleValue: last.c }, liveUpdatedAt: { timestampValue: nowIso },
      },
    },
    updateMask: { fieldPaths: ['symbol', 'yahoo', 'interval', 'lastDate', 'lastTime', 'lastClose', 'liveUpdatedAt'] },
  });
  for (let i = 0; i < writes.length; i += 400) firestoreCommit_(writes.slice(i, i + 400));
  return days.length;
}

/** Brakujące świece w obrębie dnia: odstępy > 5 min między kolejnymi świecami (bez przerwy weekendowej). */
function fxGaps_(list) {
  let miss = 0;
  for (let i = 1; i < list.length; i++) {
    const gap = (list[i].t - list[i - 1].t) / FX.STEP_SEC - 1;
    if (gap > 0 && gap < 12 * 24) miss += gap;
  }
  return miss;
}

/** Pierwsze uruchomienie: ostatnie HISTORY_DAYS dni. */
function fxHistory_(st) {
  const nowSec = Date.now() / 1000;
  const bars = fxBars_(fxFetch_(nowSec - FX.HISTORY_DAYS * 86400, nowSec), nowSec);
  if (!bars.length) throw new Error('EURUSD: Yahoo nie zwróciło świec historii');
  const days = fxWriteDays_(bars, null);
  st.last = bars[bars.length - 1].t;
  st.lastClose = bars[bars.length - 1].c;
  st.first = fxDay_(bars[0].t);
  st.historyAt = new Date().toISOString();
  st.refreshed = fxDay_(nowSec);
  fxStateSave_(st);
  const msg = `EURUSD: historia ${bars.length} świec 5 min, ${days} dni od ${st.first}`;
  log_('INFO', 'EURUSD', msg);
  return msg;
}

/** Nowe świece: pobiera od początku dnia (UTC) ostatniej zapisanej świecy i przepisuje dni z nowymi świecami. */
function fxLive_(st) {
  const nowSec = Date.now() / 1000;
  const fromDay = Date.parse(fxDay_(st.last) + 'T00:00:00Z') / 1000;
  const bars = fxBars_(fxFetch_(fromDay, nowSec), nowSec);
  const fresh = bars.filter(b => b.t > st.last);
  if (!fresh.length) return '';
  const days = {};
  fresh.forEach(b => { days[fxDay_(b.t)] = 1; });
  fxWriteDays_(bars, days);
  const at = Date.now();                                   // zapis potwierdzony
  const today = fxDay_(nowSec);
  if (!st.today || st.today.date !== today) st.today = { date: today, n: 0, delays: [] };
  fresh.forEach(b => {
    if (fxDay_(b.t) !== today) return;
    st.today.n++;
    st.today.delays.push(Math.round(at / 1000 - (b.t + FX.STEP_SEC)));
  });
  const todayBars = bars.filter(b => fxDay_(b.t) === today);
  st.today.missing = fxGaps_(todayBars);
  st.today.bars = todayBars.length;
  st.lastDelay = Math.round(at / 1000 - (fresh[fresh.length - 1].t + FX.STEP_SEC));
  st.last = fresh[fresh.length - 1].t;
  st.lastClose = fresh[fresh.length - 1].c;
  fxStateSave_(st);
  return `EURUSD: +${fresh.length} świec`;
}

/** Raz na dobę: cały wczorajszy dzień (UTC) od nowa. */
function fxRefreshIfDue_(st) {
  const now = new Date();
  const today = fxDay_(now.getTime() / 1000);
  if (st.refreshed === today) return '';
  if (now.getUTCHours() * 60 + now.getUTCMinutes() < FX.REFRESH_AFTER_MIN) return '';
  const t0 = Date.parse(today + 'T00:00:00Z') / 1000;
  st.refreshed = today;                                    // jedna próba na dobę (błąd — w „Ostatni błąd”)
  fxStateSave_(st);
  const bars = fxBars_(fxFetch_(t0 - 86400, t0), t0);
  if (!bars.length) return '';                             // np. sobota — rynek zamknięty
  fxWriteDays_(bars, null);
  st.yesterday = { date: fxDay_(t0 - 86400), bars: bars.length, missing: fxGaps_(bars) };
  fxStateSave_(st);
  return `EURUSD: przepisano ${st.yesterday.date} (${bars.length} świec)`;
}

/** Menu: pobierz teraz. */
function fxNow() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Automat właśnie pracuje — spróbuj za minutę.'); return; }
  try {
    startRun_();
    const r = fxIfDue_(true);
    finishRun_(marketContext_(new Date()), r || 'EURUSD: brak nowych świec');
    toast_(r || 'EURUSD: brak nowych świec.');
  } catch (e) { alert_('EURUSD: ' + e.message); }
  finally { lock.releaseLock(); }
}

function fxQuantile_(arr, q) {
  if (!arr.length) return null;
  const s = arr.slice().sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(q * (s.length - 1) + 0.5))];
}

/** 3 wiersze do bloku stanu STATS. */
function fxStatusRows_() {
  const st = fxStateLoad_();
  if (!st.last) return ['jeszcze nie zbierane', '', ''];
  const t = new Date(st.last * 1000), t2 = new Date((st.last + FX.STEP_SEC) * 1000);
  const f = (d, tz) => Utilities.formatDate(d, tz, 'HH:mm');
  const sec = s => (s === null || s === undefined) ? '—' : fmtDelay_(s * 1000);
  const td = st.today || { n: 0, delays: [] };
  const d = td.delays || [];
  return [
    `${fxDay_(st.last)} ${f(t, 'UTC')}–${f(t2, 'UTC')} UTC (${f(t, CONFIG.LOCAL_TZ)}–${f(t2, CONFIG.LOCAL_TZ)} PL) · close ${st.lastClose}` +
      (fxMarketOpen_(new Date()) ? '' : ' · rynek zamknięty'),
    `ostatnia ${sec(st.lastDelay)}` + (d.length
      ? ` · dziś (UTC): mediana ${sec(fxQuantile_(d, 0.5))}, 90% ≤ ${sec(fxQuantile_(d, 0.9))}, max ${sec(Math.max.apply(null, d))}`
      : ''),
    `dziś (UTC ${td.date || '—'}): świec ${td.bars || 0}, brakujących ${td.missing || 0}` +
      (st.yesterday ? ` · wczoraj ${st.yesterday.bars} świec, brakujących ${st.yesterday.missing}` : '') +
      ` · w bazie od ${st.first || '?'}`,
  ];
}

/** Pole fx w telemetry/state.json. */
function fxTelemetry_() {
  const st = fxStateLoad_();
  if (!st.last) return null;
  const d = (st.today && st.today.delays) || [];
  return {
    last: new Date(st.last * 1000).toISOString(), lastClose: st.lastClose, first: st.first,
    lastDelaySec: st.lastDelay === undefined ? null : st.lastDelay,
    today: st.today ? { date: st.today.date, bars: st.today.bars || 0, missing: st.today.missing || 0,
      delayMedianSec: fxQuantile_(d, 0.5), delayP90Sec: fxQuantile_(d, 0.9), delayMaxSec: d.length ? Math.max.apply(null, d) : null } : null,
    yesterday: st.yesterday || null,
  };
}
