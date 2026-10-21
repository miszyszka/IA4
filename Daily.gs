/**
 * ============================================================================
 *  IA 4 — BAZA ŚWIEC DOBOWYCH  (Yahoo 1d, pełna historia → Firestore daily/)
 *
 *  Wersja projektu: 1.58 (2026-10-21) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Osobna baza (instrukcja, sekcja 4d): wszystkie instrumenty w jednym miejscu,
 *  bez podziału na grupy. Pełna historia z Yahoo (świece dobowe sesji regularnej,
 *  ceny skorygowane o splity, bez korekty o dywidendy) i dopisywanie każdego dnia.
 *
 *  • Historia (jednorazowo): porcja DAILY.HIST_PER_RUN instrumentów, w wolnych
 *    uruchomieniach runCollector poza sesją (nie opóźnia świec 1h); jedno zapytanie
 *    Yahoo na instrument (range=max, interval=1d).
 *  • Aktualizacja: raz na dzień sesyjny, 75 min po zamknięciu — bieżący rok każdego
 *    instrumentu pobrany od 1 stycznia i przepisany w całości (do 15 stycznia także
 *    poprzedni rok). Nowy split w danych → historia instrumentu pobierana od nowa
 *    (Yahoo przelicza wtedy wszystkie starsze ceny).
 *  • Format: daily/{SYMBOL}/years/{RRRR} — tablice d, o, h, l, c, v (dokument = rok);
 *    daily/{SYMBOL} — podsumowanie; system/daily — lista instrumentów i stan (jeden
 *    odczyt dla Maca). Ceny: 6 cyfr znaczących (stare ceny po splitach bywają < 0,01).
 *  Stan: Script Properties DAILY_STATE.
 * ============================================================================
 */

const DAILY = {
  COLL: 'daily',
  HIST_PER_RUN: 6,          // instrumentów w jednej porcji historii
  HIST_EVERY_MIN: 3,        // odstęp między porcjami
  HIST_RETRY_MIN: 30,       // instrument z błędem — ponowienie najwcześniej po tylu minutach
  QUIET_BEFORE_OPEN: 15,    // historia nie rusza od 15 min przed otwarciem …
  QUIET_AFTER_CLOSE: 60,    // … do 60 min po zamknięciu (czas świec 1h i nocnego odświeżenia)
  AFTER_CLOSE_MIN: 75,      // aktualizacja: tyle minut po zamknięciu sesji
  TODAY_AFTER_MIN: 30,      // dzisiejsza świeca dobowa przyjmowana dopiero tyle minut po zamknięciu
  RETRY_MIN: 30,            // ponowienie nieudanej aktualizacji
  TRIES: 3,                 // po tylu próbach z błędami dzień uznany (błędy w dzienniku)
  JAN_DAYS: 15,             // do 15 stycznia aktualizacja obejmuje też poprzedni rok
  COMMIT_DOCS: 40,          // dokumentów w jednym zapisie do Firestore
  SIG: 6,                   // cyfr znaczących ceny
};

function dailyStateLoad_() {
  const st = JSON.parse(PropertiesService.getScriptProperties().getProperty('DAILY_STATE') || '{}');
  st.s = st.s || {};
  return st;
}
function dailyStateSave_(st) { PropertiesService.getScriptProperties().setProperty('DAILY_STATE', JSON.stringify(st)); }
function dailySig_(x) { return Number(Number(x).toPrecision(DAILY.SIG)); }
function dailyDocBase_(sym) { return `${fsBase_()}/${DAILY.COLL}/${sym.replace(/^\^/, '')}`; }
function dailyGran_(result) { return (result && result.meta && result.meta.dataGranularity) || ''; }

/** Dzień, który powinien już być w bazie: dziś po zamknięciu + 75 min, inaczej poprzedni dzień sesyjny. */
function dailyTarget_(ctx, session) {
  const closeMin = sessionCloseFor_(session, ctx.etDate);
  if (ctx.weekday && !isHolidayToday_(ctx, session) && ctx.etMin >= closeMin + DAILY.AFTER_CLOSE_MIN) return ctx.etDate;
  let t = Date.parse(ctx.etDate + 'T12:00:00Z');
  for (let i = 0; i < 10; i++) {
    t -= 86400000;
    const d = new Date(t).toISOString().slice(0, 10);
    if (isoWeekday_(d) <= 5 && !US_MARKET_HOLIDAYS[d]) return d;
  }
  return '';
}

/** Czy teraz wolno pobierać historię (poza czasem świec 1h i nocnego odświeżenia). */
function dailyQuiet_(ctx, session) {
  if (!ctx.weekday || isHolidayToday_(ctx, session)) return true;
  const closeMin = sessionCloseFor_(session, ctx.etDate);
  return ctx.etMin < OPEN - DAILY.QUIET_BEFORE_OPEN || ctx.etMin >= closeMin + DAILY.QUIET_AFTER_CLOSE;
}

/**
 * Odpowiedź Yahoo (interval=1d) → { rows: [{ d, o, h, l, c, v }], splits: [{ d, r }] }.
 * Tylko zamknięte sesje: dzisiejsza dopiero TODAY_AFTER_MIN po zamknięciu; dni bez sesji i niepełne
 * wartości pomijane; ta sama data dwa razy — wygrywa późniejsza.
 */
function dailyParse_(result, ctx, session) {
  const ts = result.timestamp || [];
  const q = (result.indicators && result.indicators.quote && result.indicators.quote[0]) || {};
  const o = q.open || [], h = q.high || [], l = q.low || [], c = q.close || [], v = q.volume || [];
  const todayOk = ctx.etMin >= sessionCloseFor_(session, ctx.etDate) + DAILY.TODAY_AFTER_MIN && ctx.weekday;
  const byD = {};
  for (let i = 0; i < ts.length; i++) {
    const vals = [o[i], h[i], l[i], c[i]];
    if (vals.some(x => typeof x !== 'number' || !isFinite(x) || x <= 0)) continue;
    const d = Utilities.formatDate(new Date(ts[i] * 1000), CONFIG.MARKET_TZ, 'yyyy-MM-dd');
    if (d > ctx.etDate || (d === ctx.etDate && !todayOk)) continue;
    if (isoWeekday_(d) > 5 || US_MARKET_HOLIDAYS[d]) continue;
    byD[d] = { d, o: dailySig_(vals[0]), h: dailySig_(vals[1]), l: dailySig_(vals[2]), c: dailySig_(vals[3]),
               v: (typeof v[i] === 'number' && isFinite(v[i])) ? Math.round(v[i]) : 0 };
  }
  const rows = Object.keys(byD).sort().map(d => byD[d]);
  const ev = (result.events && result.events.splits) || {};
  const splits = Object.keys(ev).map(k => {
    const s = ev[k];
    return { d: Utilities.formatDate(new Date(Number(s.date || k) * 1000), CONFIG.MARKET_TZ, 'yyyy-MM-dd'),
             r: `${s.numerator}:${s.denominator}` };
  }).sort((a, b) => a.d < b.d ? -1 : 1);
  return { rows, splits };
}

/** Dokumenty lat: daily/{SYMBOL}/years/{RRRR} (całe lata z `rows`, tylko `years`, jeśli podane). */
function dailyYearWrites_(sym, rows, nowIso, years) {
  const by = {};
  rows.forEach(r => { const y = r.d.slice(0, 4); (by[y] = by[y] || []).push(r); });
  const arr = (list, f) => ({ arrayValue: { values: list.map(f) } });
  return Object.keys(by).sort().filter(y => !years || years.indexOf(Number(y)) >= 0).map(y => {
    const rs = by[y];
    return { update: { name: `${dailyDocBase_(sym)}/years/${y}`, fields: {
      symbol: { stringValue: sym }, year: { integerValue: String(Number(y)) }, n: { integerValue: String(rs.length) },
      d: arr(rs, r => ({ stringValue: r.d })),
      o: arr(rs, r => ({ doubleValue: r.o })), h: arr(rs, r => ({ doubleValue: r.h })),
      l: arr(rs, r => ({ doubleValue: r.l })), c: arr(rs, r => ({ doubleValue: r.c })),
      v: arr(rs, r => ({ integerValue: String(r.v) })),
      updatedAt: { timestampValue: nowIso },
    } } };
  });
}

function dailySummaryWrite_(sym, p, nowIso) {
  const rows = p.rows, last = rows[rows.length - 1];
  return { update: { name: dailyDocBase_(sym), fields: {
    symbol: { stringValue: sym }, group: { stringValue: symbolGroup_(sym) },
    first: { stringValue: rows[0].d }, last: { stringValue: last.d }, lastClose: { doubleValue: last.c },
    n: { integerValue: String(rows.length) },
    splits: { arrayValue: { values: p.splits.map(s => ({ stringValue: `${s.d} ${s.r}` })) } },
    historyAt: { timestampValue: nowIso }, updatedAt: { timestampValue: nowIso },
  } } };
}

/** Aktualizacja: tylko ostatnia świeca w podsumowaniu (reszta pól bez zmian). */
function dailyLastWrite_(sym, last, nowIso) {
  return { update: { name: dailyDocBase_(sym), fields: {
    last: { stringValue: last.d }, lastClose: { doubleValue: last.c }, updatedAt: { timestampValue: nowIso },
  } }, updateMask: { fieldPaths: ['last', 'lastClose', 'updatedAt'] } };
}

/** system/daily — równoległe listy: symbol, gotowa historia, pierwsza i ostatnia data. */
function dailyStatusWrite_(st, nowIso) {
  const syms = allSymbols_();
  const strs = f => ({ arrayValue: { values: syms.map(s => ({ stringValue: f(st.s[s] || {}) })) } });
  return { update: { name: `${fsBase_()}/system/daily`, fields: {
    symbols: { arrayValue: { values: syms.map(s => ({ stringValue: s })) } },
    hist: { arrayValue: { values: syms.map(s => ({ booleanValue: !!(st.s[s] && st.s[s].h) })) } },
    first: strs(x => x.f || ''), last: strs(x => x.l || ''),
    updated: { stringValue: st.upd || '' }, version: { stringValue: CONFIG.VERSION },
    updatedAt: { timestampValue: nowIso },
  } } };
}

function dailyCommit_(writes) {
  for (let i = 0; i < writes.length; i += DAILY.COMMIT_DOCS) firestoreCommit_(writes.slice(i, i + DAILY.COMMIT_DOCS));
}

// ============================================================================
//  WEJŚCIE Z runCollector (wolne uruchomienie) i z menu
// ============================================================================
function dailyIfDue_(ctx) {
  try {
    return dailyUpdateIfDue_(ctx, false) || dailyHistoryIfDue_(ctx, false);
  } catch (e) { recordError_('DAILY', e.message || String(e)); return ''; }
}

function dailyHistoryIfDue_(ctx, force) {
  const st = dailyStateLoad_();
  const session = getSession_();
  if (!force && !dailyQuiet_(ctx, session)) return '';
  if (!force && Date.now() - (st.ht || 0) < DAILY.HIST_EVERY_MIN * 60000) return '';
  const now = Date.now();
  const todo = allSymbols_().filter(s => !(st.s[s] && st.s[s].h) &&
    (force || now - ((st.s[s] || {}).t || 0) > DAILY.HIST_RETRY_MIN * 60000)).slice(0, DAILY.HIST_PER_RUN);
  if (!todo.length) return '';
  st.ht = now;
  todo.forEach(s => { st.s[s] = Object.assign(st.s[s] || {}, { t: now }); });
  dailyStateSave_(st);

  const res = fetchYahooMany_(todo, 'range=max&interval=1d&events=split&includePrePost=false');
  const bad = todo.filter(s => res[s] && res[s].result && dailyGran_(res[s].result) !== '1d');
  if (bad.length) {                                    // zapasowo: od 1970 r. jawnie dziennie
    const r2 = fetchYahooMany_(bad, `period1=0&period2=${Math.floor(now / 1000)}&interval=1d&events=split&includePrePost=false`);
    bad.forEach(s => { res[s] = r2[s]; });
  }
  const nowIso = new Date().toISOString();
  const writes = [], done = [], errs = [];
  todo.forEach(s => {
    const r = res[s];
    if (!r || r.error) { errs.push(`${s}: ${r ? r.error : 'brak odpowiedzi'}`); return; }
    if (dailyGran_(r.result) !== '1d') { errs.push(`${s}: Yahoo zwrócił ${dailyGran_(r.result) || '?'} zamiast 1d`); return; }
    const p = dailyParse_(r.result, ctx, session);
    if (!p.rows.length) { errs.push(`${s}: brak świec`); return; }
    dailyYearWrites_(s, p.rows, nowIso).forEach(w => writes.push(w));
    writes.push(dailySummaryWrite_(s, p, nowIso));
    done.push({ s, p });
  });
  if (writes.length) dailyCommit_(writes);           // najpierw zapis, potem stan
  const st2 = dailyStateLoad_();
  done.forEach(x => {
    const rows = x.p.rows, sp = x.p.splits;
    st2.s[x.s] = { h: 1, f: rows[0].d, l: rows[rows.length - 1].d, sp: sp.length ? sp[sp.length - 1].d : '' };
  });
  if (done.length) dailyCommit_([dailyStatusWrite_(st2, nowIso)]);
  dailyStateSave_(st2);
  if (errs.length) recordError_('DAILY', errs.join(' · '));
  const n = allSymbols_().filter(s => st2.s[s] && st2.s[s].h).length;
  return done.length ? `świece dobowe: historia ${done.map(x => `${x.s} od ${x.p.rows[0].d}`).join(', ')} (${n}/${allSymbols_().length})` : '';
}

function dailyUpdateIfDue_(ctx, force) {
  const st = dailyStateLoad_();
  const session = getSession_();
  const syms = allSymbols_().filter(s => st.s[s] && st.s[s].h);
  if (!syms.length) return '';
  const target = dailyTarget_(ctx, session);
  if (!force && (!target || (st.upd || '') >= target)) return '';
  if (!force && Date.now() - (st.ut || 0) < DAILY.RETRY_MIN * 60000) return '';
  st.ut = Date.now();
  dailyStateSave_(st);

  const y = Number(ctx.etDate.slice(0, 4));
  const jan = ctx.etDate.slice(5, 7) === '01' && Number(ctx.etDate.slice(8, 10)) <= DAILY.JAN_DAYS;
  const years = jan ? [y - 1, y] : [y];
  const p1 = Math.floor(Date.UTC(years[0], 0, 1) / 1000) - 86400;
  const res = fetchYahooMany_(syms, `period1=${p1}&period2=${Math.floor(Date.now() / 1000)}&interval=1d&events=split&includePrePost=false`);
  const nowIso = new Date().toISOString();
  const writes = [], errs = [], redo = [], ok = [];
  syms.forEach(s => {
    const r = res[s];
    if (!r || r.error) { errs.push(`${s}: ${r ? r.error : 'brak odpowiedzi'}`); return; }
    if (dailyGran_(r.result) !== '1d') { errs.push(`${s}: Yahoo zwrócił ${dailyGran_(r.result) || '?'} zamiast 1d`); return; }
    const p = dailyParse_(r.result, ctx, session);
    const known = st.s[s];
    const fresh = p.splits.filter(x => x.d > (known.sp || '') && x.d > (known.f || ''));
    if (fresh.length) { redo.push(`${s} (split ${fresh[fresh.length - 1].d} ${fresh[fresh.length - 1].r})`); known.h = 0; known.t = 0; return; }
    const rows = p.rows.filter(x => years.indexOf(Number(x.d.slice(0, 4))) >= 0);
    // bezpiecznik: rok przepisujemy w całości tylko, gdy Yahoo oddał go od początku stycznia
    const full = years.filter(yy => {
      const first = rows.find(x => Number(x.d.slice(0, 4)) === yy);
      return first && (first.d <= `${yy}-01-08` || (known.f || '') >= `${yy}-01-01`);
    });
    if (!full.length) { errs.push(`${s}: niepełny rok z Yahoo — pominięty`); return; }
    dailyYearWrites_(s, rows, nowIso, full).forEach(w => writes.push(w));
    const last = rows[rows.length - 1];
    writes.push(dailyLastWrite_(s, last, nowIso));
    ok.push({ s, last });
  });
  if (writes.length) dailyCommit_(writes);
  const st2 = dailyStateLoad_();
  ok.forEach(x => { st2.s[x.s].l = x.last.d; });
  redo.forEach(r => { const s = r.split(' ')[0]; st2.s[s].h = 0; st2.s[s].t = 0; });
  st2.un = st2.ud === target ? (st2.un || 0) + 1 : 1;     // próby dla tego dnia
  st2.ud = target;
  if (!errs.length || st2.un >= DAILY.TRIES) st2.upd = target || ctx.etDate;
  dailyCommit_([dailyStatusWrite_(st2, nowIso)]);
  dailyStateSave_(st2);
  if (errs.length) recordError_('DAILY', errs.join(' · '));
  if (redo.length) log_('INFO', 'DAILY', `Nowy split — historia pobierana od nowa: ${redo.join(', ')}`);
  return `świece dobowe: aktualizacja ${target} — ${ok.length}/${syms.length}` + (redo.length ? `, od nowa: ${redo.length}` : '') +
         (errs.length ? `, błędów ${errs.length} (ponowię)` : '');
}

function dailyHistoryNow() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Automat właśnie pracuje — spróbuj za minutę.'); return; }
  try {
    startRun_();
    const ctx = marketContext_(new Date());
    const r = dailyHistoryIfDue_(ctx, true);
    finishRun_(ctx, r || 'Świece dobowe: historia kompletna');
    toast_(r || 'Świece dobowe: historia wszystkich instrumentów już jest.');
  } finally { lock.releaseLock(); }
}

function dailyUpdateNow() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Automat właśnie pracuje — spróbuj za minutę.'); return; }
  try {
    startRun_();
    const ctx = marketContext_(new Date());
    const r = dailyUpdateIfDue_(ctx, true);
    finishRun_(ctx, r || 'Świece dobowe: brak instrumentów z historią');
    toast_(r || 'Świece dobowe: najpierw historia (menu „porcja historii”).');
  } finally { lock.releaseLock(); }
}

/** Do telemetry/state.json. */
function dailyTelemetry_() {
  const st = dailyStateLoad_();
  const syms = allSymbols_();
  const done = syms.filter(s => st.s[s] && st.s[s].h);
  const firsts = done.map(s => st.s[s].f).filter(x => x).sort();
  const lasts = done.map(s => st.s[s].l).filter(x => x).sort();
  return { collection: DAILY.COLL, instruments: syms.length, history: `${done.length}/${syms.length}`,
           oldest: firsts[0] || '', newest: lasts[lasts.length - 1] || '', updated: st.upd || '',
           waiting: syms.filter(s => !(st.s[s] && st.s[s].h)).slice(0, 10) };
}
