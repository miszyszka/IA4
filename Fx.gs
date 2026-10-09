/**
 * ============================================================================
 *  IA 4 — MODUŁ EURUSD  (Yahoo EURUSD=X, świece 5 min → Firestore fx/EURUSD → arkusz FX)
 *
 *  Wersja projektu: 1.20 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Osobny moduł (instrukcja, sekcja 4b): zbiera dane. Nie bierze udziału
 *  w poszukiwaniu, weryfikacji ani paper tradingu.
 *
 *  • fxIfDue_() woła runCollector (Code.gs) w każdym uruchomieniu (co minutę)
 *    i co 10 s w szybkiej ścieżce akcji — jeden trigger dla całego automatu.
 *  • Na żywo: Yahoo jest pytane tylko wtedy, gdy powinna już być zamknięta świeca
 *    nowsza niż ostatnia zapisana, i tylko w godzinach rynku walutowego
 *    (niedziela 17:00 – piątek 17:00 czasu Nowego Jorku). Dokument dnia (UTC)
 *    jest przepisywany w całości przy każdej nowej świecy.
 *  • Kontrola dnia (po jego końcu, od 00:20 UTC): do 3 prób pobrania całego dnia
 *    co 60 min; braki, których Yahoo nie odda, są uzupełniane interpolacją liniową
 *    między sąsiednimi świecami i oznaczane (fillT) — każdy dzień kończy się kompletny.
 *  • Arkusz FX: jeden wiersz na dzień — oczekiwanych, zapisanych, w tym uśrednionych —
 *    dopisywany po kontroli zakończonego dnia.
 *  Stan: Script Properties FX_STATE (bieżący) i FX_CHECK (dni czekające na kolejną próbę).
 * ============================================================================
 */

const FX = {
  NAME: 'EURUSD',               // dokument fx/EURUSD
  YAHOO: 'EURUSD=X',
  STEP_SEC: 300,                // świeca 5 min
  FIRST_FETCH_SEC: 5,           // pytamy Yahoo najwcześniej tyle sekund po zamknięciu świecy
  HISTORY_DAYS: 59,             // pierwsze pobranie: tyle dni wstecz
  YAHOO_DAYS: 58,               // starsze dni Yahoo już nie odda — kontrola od razu uzupełnia
  CHECK_AFTER_MIN: 20,          // kontrola wczorajszego dnia: od 00:20 UTC
  CHECK_TRIES: 3,               // tyle prób pobrania brakujących świec
  CHECK_EVERY_MIN: 60,          // odstęp między próbami
  CHECK_PER_RUN: 2,             // najwyżej tyle dni kontrolowanych w jednym uruchomieniu
  OPEN_DOW: 7, OPEN_MIN: 17 * 60,         // rynek walutowy: od niedzieli 17:00 ET…
  CLOSE_DOW: 5, CLOSE_MIN: 17 * 60,       // …do piątku 17:00 ET
  MARGIN_MIN: 5,                // zapas przy pytaniu Yahoo na granicach tygodnia
  SHEET: 'FX',
};

const FX_COLS = ['Data (UTC)', 'Dzień', 'Oczekiwanych świec', 'Zapisanych świec', 'w tym uśrednionych'];
const FX_DOW = ['', 'pn', 'wt', 'śr', 'czw', 'pt', 'sob', 'nd'];

function fxStateLoad_() { return JSON.parse(PropertiesService.getScriptProperties().getProperty('FX_STATE') || '{}'); }
function fxStateSave_(st) { PropertiesService.getScriptProperties().setProperty('FX_STATE', JSON.stringify(st)); }
function fxCheckLoad_() { return JSON.parse(PropertiesService.getScriptProperties().getProperty('FX_CHECK') || '{}'); }
function fxCheckSave_(c) { PropertiesService.getScriptProperties().setProperty('FX_CHECK', JSON.stringify(c)); }

function fxDay_(t) { return Utilities.formatDate(new Date(t * 1000), 'UTC', 'yyyy-MM-dd'); }
function fxDayStart_(d) { return Date.parse(d + 'T00:00:00Z') / 1000; }

/** Czy świeca zaczynająca się w chwili t (s) mieści się w godzinach rynku walutowego. */
function fxSlotOpen_(t, marginMin) {
  const m = marginMin || 0;
  const d = new Date(t * 1000);
  const dow = isoWeekday_(Utilities.formatDate(d, CONFIG.MARKET_TZ, 'yyyy-MM-dd'));
  const min = minutesOf_(d, CONFIG.MARKET_TZ);
  if (dow === 6) return false;
  if (dow === FX.OPEN_DOW) return min >= FX.OPEN_MIN - m;
  if (dow === FX.CLOSE_DOW) return min < FX.CLOSE_MIN + m;
  return true;
}
function fxMarketOpen_(now) { return fxSlotOpen_(now.getTime() / 1000, FX.MARGIN_MIN); }

/**
 * Oczekiwane świece dnia (UTC): początki świec (s) w godzinach rynku. Przesunięcie ET–UTC
 * liczone raz na dzień (w południe UTC) — zmiana czasu w USA przypada na niedzielę rano,
 * gdy rynek walutowy jest zamknięty. upTo — tylko świece zamknięte przed tą chwilą (s).
 */
function fxExpected_(date, upTo, fromT) {
  const t0 = fxDayStart_(date);
  const noon = new Date((t0 + 43200) * 1000);
  const off = minutesOf_(noon, CONFIG.MARKET_TZ) - 12 * 60;            // ET − UTC w minutach (−240 / −300)
  const dowUtc = isoWeekday_(date);
  const out = [];
  for (let i = 0; i < 288; i++) {
    const t = t0 + i * FX.STEP_SEC;
    if (upTo && t + FX.STEP_SEC > upTo) break;
    if (fromT && t < fromT) continue;                         // pierwszy dzień bazy: od pierwszej świecy
    let min = i * 5 + off, dow = dowUtc;
    if (min < 0) { min += 1440; dow = dow === 1 ? 7 : dow - 1; }
    let open = true;
    if (dow === 6) open = false;
    else if (dow === FX.OPEN_DOW) open = min >= FX.OPEN_MIN;
    else if (dow === FX.CLOSE_DOW) open = min < FX.CLOSE_MIN;
    if (open) out.push(t);
  }
  return out;
}

/** Podsumowanie dnia: świece z Yahoo, uśrednione, oczekiwane, brakujące. */
function fxDayInfo_(date, realT, fillT, upTo, fromT) {
  const have = {};
  realT.forEach(t => { have[t] = 1; });
  fillT.forEach(t => { have[t] = 1; });
  const fullExp = fxExpected_(date, 0, fromT).length;
  const exp = fxExpected_(date, upTo || 0, fromT);
  return { real: realT.length, filled: fillT.length, total: realT.length + fillT.length, expected: fullExp,
           missing: exp.filter(t => !have[t]).length, missingT: exp.filter(t => !have[t]) };
}

// ============================================================================
//  WEJŚCIE (co minutę z runCollector)
// ============================================================================
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
  if (st.scanV !== 3) { msgs.push(fxScan_(st)); }          // 1.18: rejestr dni i arkusz FX z istniejących danych
  const nextClose = (st.last + 2 * FX.STEP_SEC) * 1000;    // zamknięcie świecy następnej po ostatniej zapisanej
  const due = now >= nextClose + FX.FIRST_FETCH_SEC * 1000 && fxMarketOpen_(new Date(now));
  if (force || due) msgs.push(fxLive_(st));
  msgs.push(fxCheckIfDue_(st));
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
    byT[t] = { t, o: fxR6_(o), h: fxR6_(Math.max(h, o, c)), l: fxR6_(Math.min(l, o, c)), c: fxR6_(c) };   // późniejszy wpis wygrywa
  }
  return Object.keys(byT).map(Number).sort((a, b) => a - b).map(t => byT[t]);
}
function fxR6_(x) { return Math.round(x * 1e6) / 1e6; }

function fxFetch_(p1, p2) {
  const r = fetchYahooMany_([FX.YAHOO], `interval=5m&period1=${Math.floor(p1)}&period2=${Math.floor(p2)}&includePrePost=false`)[FX.YAHOO];
  if (r.error) throw new Error(r.error);
  return r.result;
}

// ============================================================================
//  FIRESTORE: dokument dnia
// ============================================================================
function fxDocName_(date) { return `${fsBase_()}/fx/${FX.NAME}/days/${date}`; }

/**
 * Zapis dokumentu dnia. real — świece z Yahoo, fill — uśrednione (oznaczone w fillT).
 * meta: { tries, status, upTo } — upTo: dla dnia, który trwa, braki liczone tylko do tej chwili.
 */
function fxDayWrite_(date, real, fill, meta, nowIso) {
  const all = real.concat(fill).sort((a, b) => a.t - b.t);
  const t0 = fxDayStart_(date);
  const info = fxDayInfo_(date, real.map(b => b.t), fill.map(b => b.t), meta.upTo, meta.fromT);
  const arr = (vals, int) => ({ arrayValue: { values: vals.map(v => int ? { integerValue: String(v) } : { doubleValue: v }) } });
  const write = {
    update: {
      name: fxDocName_(date),
      fields: {
        symbol: { stringValue: FX.NAME }, date: { stringValue: date }, bars: { integerValue: String(all.length) },
        t: arr(all.map(b => (b.t - t0) / 60), true),
        o: arr(all.map(b => b.o)), h: arr(all.map(b => b.h)), l: arr(all.map(b => b.l)), c: arr(all.map(b => b.c)),
        expected: { integerValue: String(info.expected) }, missing: { integerValue: String(info.missing) },
        filled: { integerValue: String(fill.length) }, fillT: arr(fill.map(b => (b.t - t0) / 60), true),
        tries: { integerValue: String(meta.tries || 0) }, status: { stringValue: meta.status },
        updatedAt: { timestampValue: nowIso },
      },
    },
  };
  return { write, info };
}

function fxSummaryWrite_(last, nowIso) {
  return {
    update: {
      name: `${fsBase_()}/fx/${FX.NAME}`,
      fields: {
        symbol: { stringValue: FX.NAME }, yahoo: { stringValue: FX.YAHOO }, interval: { stringValue: '5m' },
        lastDate: { stringValue: fxDay_(last.t) },
        lastTime: { stringValue: Utilities.formatDate(new Date(last.t * 1000), 'UTC', 'HH:mm') },
        lastClose: { doubleValue: last.c }, liveUpdatedAt: { timestampValue: nowIso },
      },
    },
    updateMask: { fieldPaths: ['symbol', 'yahoo', 'interval', 'lastDate', 'lastTime', 'lastClose', 'liveUpdatedAt'] },
  };
}

/** Dokument dnia z Firestore → { real: [...], fillT: [s], tries, status } albo null. */
function fxDayRead_(date) {
  const resp = UrlFetchApp.fetch(`https://firestore.googleapis.com/v1/${fxDocName_(date)}`, {
    muteHttpExceptions: true, headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() } });
  if (resp.getResponseCode() === 404) return null;
  if (resp.getResponseCode() !== 200) throw new Error(`Firestore HTTP ${resp.getResponseCode()} (fx ${date})`);
  return fxDocParse_(JSON.parse(resp.getContentText()).fields || {}, date);
}

function fxDocParse_(f, date) {
  const t0 = fxDayStart_(date);
  const num = v => Number(v.doubleValue !== undefined ? v.doubleValue : v.integerValue);
  const a = k => ((f[k] && f[k].arrayValue && f[k].arrayValue.values) || []).map(num);
  const tt = a('t'), o = a('o'), h = a('h'), l = a('l'), c = a('c');
  const fillT = a('fillT').map(m => t0 + m * 60);
  const isFill = {};
  fillT.forEach(t => { isFill[t] = 1; });
  const real = [];
  for (let i = 0; i < tt.length; i++) {
    const t = t0 + tt[i] * 60;
    if (!isFill[t]) real.push({ t, o: o[i], h: h[i], l: l[i], c: c[i] });
  }
  return { real, fillT, tries: f.tries ? num(f.tries) : 0, status: f.status ? f.status.stringValue : '' };
}

// ============================================================================
//  NA ŻYWO I HISTORIA
// ============================================================================
/** Pierwsze uruchomienie: ostatnie HISTORY_DAYS dni; rejestr dni i arkusz FX — przez fxScan_. */
function fxHistory_(st) {
  const nowSec = Date.now() / 1000;
  const bars = fxBars_(fxFetch_(nowSec - FX.HISTORY_DAYS * 86400, nowSec), nowSec);
  if (!bars.length) throw new Error('EURUSD: Yahoo nie zwróciło świec historii');
  const nowIso = new Date().toISOString();
  const today = fxDay_(nowSec);
  const byDay = {};
  bars.forEach(b => { (byDay[fxDay_(b.t)] = byDay[fxDay_(b.t)] || []).push(b); });
  const writes = Object.keys(byDay).sort().map(d => fxDayWrite_(d, byDay[d], [],
    { tries: 0, status: d === today ? 'dzień trwa' : 'do kontroli', upTo: d === today ? nowSec : 0 }, nowIso).write);
  writes.push(fxSummaryWrite_(bars[bars.length - 1], nowIso));
  for (let i = 0; i < writes.length; i += 400) firestoreCommit_(writes.slice(i, i + 400));
  st.last = bars[bars.length - 1].t;
  st.lastClose = bars[bars.length - 1].c;
  st.lastWriteAt = nowIso;
  st.first = fxDay_(bars[0].t);
  st.historyAt = nowIso;
  st.checkedDay = today;                                   // kontrolę dni historii planuje fxScan_
  fxStateSave_(st);
  const msg = `EURUSD: historia ${bars.length} świec 5 min, ${Object.keys(byDay).length} dni od ${st.first}`;
  log_('INFO', 'EURUSD', msg);
  return msg + ' · ' + fxScan_(st);
}

/** Nowe świece: pobiera od początku dnia (UTC) ostatniej zapisanej świecy i przepisuje dni z nowymi świecami. */
function fxLive_(st) {
  const nowSec = Date.now() / 1000;
  const fromDay = fxDayStart_(fxDay_(st.last));
  const bars = fxBars_(fxFetch_(fromDay, nowSec), nowSec);
  const fresh = bars.filter(b => b.t > st.last);
  if (!fresh.length) return '';
  const days = {};
  fresh.forEach(b => { days[fxDay_(b.t)] = 1; });
  const today = fxDay_(nowSec);
  const nowIso = new Date().toISOString();
  const res = Object.keys(days).sort().map(d => fxDayWrite_(d, bars.filter(b => fxDay_(b.t) === d), [],
    { tries: 0, status: d === today ? 'dzień trwa' : 'do kontroli', upTo: d === today ? nowSec : 0 }, nowIso));
  firestoreCommit_(res.map(r => r.write).concat([fxSummaryWrite_(fresh[fresh.length - 1], nowIso)]));
  const at = Date.now();                                   // zapis potwierdzony
  if (!st.today || st.today.date !== today) st.today = { date: today, n: 0, delays: [] };
  fresh.forEach(b => {
    if (fxDay_(b.t) !== today) return;
    st.today.n++;
    st.today.delays.push(Math.round(at / 1000 - (b.t + FX.STEP_SEC)));
  });
  const ti = res.find(r => r.write.update.fields.date.stringValue === today);
  if (ti) { st.today.bars = ti.info.total; st.today.missing = ti.info.missing; st.today.expectedSoFar = fxExpected_(today, nowSec).length; }
  st.lastDelay = Math.round(at / 1000 - (fresh[fresh.length - 1].t + FX.STEP_SEC));
  st.last = fresh[fresh.length - 1].t;
  st.lastClose = fresh[fresh.length - 1].c;
  st.lastWriteAt = new Date(at).toISOString();
  fxStateSave_(st);
  return `EURUSD: +${fresh.length} świec`;
}

// ============================================================================
//  KONTROLA DNI: 3 próby pobrania braków, potem uśrednienie
// ============================================================================
/** Planuje wczorajszy dzień (raz na dobę, od 00:20 UTC) i wykonuje zaległe próby. */
function fxCheckIfDue_(st) {
  const now = new Date();
  const today = fxDay_(now.getTime() / 1000);
  const chk = fxCheckLoad_();
  if (st.checkedDay !== today && now.getUTCHours() * 60 + now.getUTCMinutes() >= FX.CHECK_AFTER_MIN) {
    const y = fxDay_(now.getTime() / 1000 - 86400);
    if (fxExpected_(y).length) { if (!chk[y]) chk[y] = { tries: 0, next: 0 }; }       // sobota: bez kontroli i bez dokumentu
    else { try { fxSheetRow_(y, fxDayInfo_(y, [], [])); } catch (e) { console.warn('FX arkusz: ' + e.message); } }
    st.checkedDay = today;
    fxStateSave_(st);
    fxCheckSave_(chk);
  }
  const due = Object.keys(chk).filter(d => chk[d].next <= now.getTime()).sort().slice(0, FX.CHECK_PER_RUN);
  if (!due.length) return '';
  const out = [];
  due.forEach(d => {
    try { out.push(fxCheckDay_(d, chk)); }
    catch (e) {
      chk[d].tries++; chk[d].next = Date.now() + FX.CHECK_EVERY_MIN * 60000;
      if (chk[d].tries >= FX.CHECK_TRIES + 2) delete chk[d];          // dzień nie do pobrania i nie do zapisu — porzucony
      recordError_('EURUSD', `kontrola ${d}: ${e.message || e}`);
    }
  });
  fxCheckSave_(chk);
  return out.filter(x => x).join(' · ');
}

/**
 * Jedna próba dla dnia d: świece z Firestore + świeże z Yahoo (Yahoo wygrywa), braki liczone na nowo.
 * Brak braków → „kompletny”. Po CHECK_TRIES próbach z brakami → uśrednienie, tak żeby dzień był
 * kompletny. Dzień zamknięty wypada z FX_CHECK i dopiero wtedy dostaje wiersz w arkuszu FX.
 * Pierwszy dzień bazy (zaczyna się w połowie — granica historii Yahoo) liczony od swojej pierwszej świecy.
 */
function fxCheckDay_(d, chk) {
  const c = chk[d];
  const t0 = fxDayStart_(d);
  const nowSec = Date.now() / 1000;
  const stored = fxDayRead_(d) || { real: [], fillT: [], tries: 0, status: '' };
  const byT = {};
  stored.real.forEach(b => { byT[b.t] = b; });
  let anchors = [];
  const old = nowSec - t0 > FX.YAHOO_DAYS * 86400;
  if (!old) {
    const got = fxBars_(fxFetch_(t0 - 3600, t0 + 86400 + 3600), nowSec);
    got.forEach(b => { if (b.t >= t0 && b.t < t0 + 86400) byT[b.t] = b; });
    anchors = got.filter(b => b.t < t0 || b.t >= t0 + 86400);
  }
  const real = Object.keys(byT).map(Number).sort((a, b) => a - b).map(t => byT[t]);
  c.tries = old ? Math.max(c.tries + 1, FX.CHECK_TRIES) : c.tries + 1;
  const fromT = (d === fxStateLoad_().first && real.length) ? real[0].t : 0;
  const info = fxDayInfo_(d, real.map(b => b.t), [], 0, fromT);
  let fill = [], status;
  if (!info.expected) status = 'weekend — brak handlu';
  else if (!info.missing) status = 'kompletny';
  else if (c.tries < FX.CHECK_TRIES) {
    status = `braki — próba ${c.tries} z ${FX.CHECK_TRIES}`;
    c.next = Date.now() + FX.CHECK_EVERY_MIN * 60000;
  } else {
    fill = fxFill_(real.concat(anchors), info.missingT);
    status = fill.length === info.missing ? `uzupełniony: ${fill.length} świec uśrednionych`
      : 'brak danych z Yahoo — nie da się uśrednić (brak świec obok)';
  }
  const nowIso = new Date().toISOString();
  const res = fxDayWrite_(d, real, fill, { tries: c.tries, status, fromT }, nowIso);
  firestoreCommit_([res.write]);
  const final = status.indexOf('braki') !== 0;
  if (final) delete chk[d];
  const st = fxStateLoad_();
  if (d === fxDay_(nowSec - 86400)) { st.yesterday = { date: d, bars: res.info.total, missing: res.info.missing, filled: fill.length, status }; fxStateSave_(st); }
  if (final) { try { fxSheetRow_(d, res.info); } catch (e) { console.warn('FX arkusz: ' + e.message); } }
  return `EURUSD ${d}: ${status}`;
}

/**
 * Uśrednienie braków: dla każdej brakującej świecy t szukamy najbliższej świecy przed (P) i po (N).
 * Cena rośnie liniowo od zamknięcia P do otwarcia N: open = wartość w chwili t, close = w chwili t+5 min,
 * high/low = większa/mniejsza z nich. Tylko P albo tylko N — świeca płaska na tej cenie.
 */
function fxFill_(known, missingT) {
  const k = known.slice().sort((a, b) => a.t - b.t);
  const out = [];
  missingT.forEach(t => {
    let p = null, n = null;
    for (let i = 0; i < k.length; i++) {
      if (k[i].t < t) p = k[i];
      else if (k[i].t > t) { n = k[i]; break; }
    }
    if (!p && !n) return;
    let o, c;
    if (p && n) {
      const x0 = p.t + FX.STEP_SEC, x1 = n.t;
      const v = x => p.c + (n.o - p.c) * (x - x0) / (x1 - x0);
      o = v(t); c = v(t + FX.STEP_SEC);
    } else { o = c = p ? p.c : n.o; }
    out.push({ t, o: fxR6_(o), h: fxR6_(Math.max(o, c)), l: fxR6_(Math.min(o, c)), c: fxR6_(c) });
  });
  return out;
}

// ============================================================================
//  REJESTR DNI Z FIRESTORE (pierwsze uruchomienie 1.17 i menu „przelicz arkusz FX”)
// ============================================================================
/**
 * Czyta wszystkie dni z Firestore, buduje arkusz FX (tylko dni zakończone i sprawdzone) i planuje kontrolę
 * dni, które nie są kompletne: bez statusu końcowego, z brakami albo bez dokumentu.
 */
function fxScan_(st) {
  const res = firestorePost_(`${fsBase_()}/fx/${FX.NAME}:runQuery`, { structuredQuery: {
    from: [{ collectionId: 'days' }],
    select: { fields: ['date', 't', 'fillT', 'tries', 'status'].map(f => ({ fieldPath: f })) } } });
  const nowSec = Date.now() / 1000;
  const today = fxDay_(nowSec);
  const chk = fxCheckLoad_();
  const days = {};
  res.forEach(it => {
    const f = it.document && it.document.fields;
    if (!f) return;
    const d = f.date.stringValue;
    if (d >= today) return;
    const t0 = fxDayStart_(d);
    const num = v => Number(v.integerValue !== undefined ? v.integerValue : v.doubleValue);
    const arr = k => ((f[k] && f[k].arrayValue && f[k].arrayValue.values) || []).map(num);
    const fillT = arr('fillT').map(m => t0 + m * 60);
    const isFill = {};
    fillT.forEach(t => { isFill[t] = 1; });
    const realT = arr('t').map(m => t0 + m * 60).filter(t => !isFill[t]).sort((a, b) => a - b);
    const fromT = (d === st.first && realT.length) ? realT[0] : 0;
    const info = fxDayInfo_(d, realT, fillT, 0, fromT);
    const tries = f.tries ? num(f.tries) : 0;
    if (info.missing) { if (!chk[d]) chk[d] = { tries, next: 0 }; return; }
    days[d] = info;
  });
  // dni robocze bez dokumentu — też do kontroli; soboty — wiersz 0 / 0
  const last = fxDay_(nowSec - 86400);
  for (let t = fxDayStart_(st.first || last); fxDay_(t) <= last; t += 86400) {
    const d = fxDay_(t);
    if (days[d] || chk[d]) continue;
    if (fxExpected_(d).length) chk[d] = { tries: 0, next: 0 };
    else days[d] = fxDayInfo_(d, [], []);
  }
  fxCheckSave_(chk);
  fxSheetRebuild_(days);
  st.scanV = 3;
  fxStateSave_(st);
  const n = Object.keys(chk).length;
  return `EURUSD: rejestr ${Object.keys(days).length} dni` + (n ? `, do kontroli ${n}` : '');
}

/** Menu: przelicz arkusz FX i rejestr dni z Firestore. */
function fxRebuildNow() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30 * 1000)) { toast_('Automat właśnie pracuje — spróbuj za minutę.'); return; }
  try {
    startRun_();
    const st = fxStateLoad_();
    const r = st.last ? fxScan_(st) : 'EURUSD jeszcze nie zbierane';
    finishRun_(marketContext_(new Date()), r);
    toast_(r);
  } catch (e) { alert_('EURUSD: ' + e.message); }
  finally { lock.releaseLock(); }
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

// ============================================================================
//  ARKUSZ FX
// ============================================================================
function fxSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(FX.SHEET);
  if (sh && sh.getRange(1, 1).getValue() === FX_COLS[0] && sh.getRange(1, FX_COLS.length).getValue() === FX_COLS[FX_COLS.length - 1]) return sh;
  if (!sh) sh = ss.insertSheet(FX.SHEET);
  sh.clear();
  sh.clearConditionalFormatRules();
  sh.getRange(1, 1, sh.getMaxRows(), sh.getMaxColumns()).breakApart();
  sh.setTabColor('#0b8043');
  sh.getRange(1, 1, 1, FX_COLS.length).setValues([FX_COLS]).setFontWeight('bold').setBackground('#f1f3f4');
  sh.setFrozenRows(1);
  sh.setColumnWidth(1, 110);
  sh.setColumnWidths(2, 4, 140);
  sh.setConditionalFormatRules([SpreadsheetApp.newConditionalFormatRule().whenNumberGreaterThan(0)
    .setBackground('#fef7e0').setRanges([sh.getRange(2, 5, 3000, 1)]).build()]);
  return sh;
}

function fxRowValues_(d, info) {
  return [d, FX_DOW[isoWeekday_(d)], info.expected, info.total, info.filled];
}

/** Jeden wiersz na dzień: nadpisuje wiersz tego dnia albo wstawia nowy (dni malejąco, najnowszy na górze). */
function fxSheetRow_(d, info) {
  const sh = fxSheet_();
  const n = Math.max(sh.getLastRow() - 1, 0);
  const dates = n ? sh.getRange(2, 1, n, 1).getDisplayValues().map(r => r[0]) : [];
  const row = fxRowValues_(d, info);
  const i = dates.indexOf(d);
  if (i >= 0) { sh.getRange(2 + i, 1, 1, row.length).setValues([row]); return; }
  let pos = dates.findIndex(x => x < d);
  if (pos < 0) pos = dates.length;
  sh.insertRowsBefore(2 + pos, 1);
  sh.getRange(2 + pos, 1, 1, row.length).setNumberFormat('@').setValues([row]).setFontWeight('normal').setBackground(null);
  sh.getRange(2 + pos, 3, 1, 3).setNumberFormat('0');
}

/** Cała lista od nowa (dni zakończone i sprawdzone), najnowszy na górze. */
function fxSheetRebuild_(days) {
  const sh = fxSheet_();
  const n = Math.max(sh.getLastRow() - 1, 0);
  if (n) sh.getRange(2, 1, n, FX_COLS.length).clearContent();
  const rows = Object.keys(days).sort().reverse().map(d => fxRowValues_(d, days[d]));
  if (!rows.length) return;
  if (sh.getMaxRows() < rows.length + 1) sh.insertRowsAfter(sh.getMaxRows(), rows.length + 1 - sh.getMaxRows());
  sh.getRange(2, 1, rows.length, 2).setNumberFormat('@');
  sh.getRange(2, 1, rows.length, FX_COLS.length).setValues(rows);
}

// ============================================================================
//  STATS I TELEMETRIA
// ============================================================================
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
  const f = (dd, tz) => Utilities.formatDate(dd, tz, 'HH:mm');
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
      (st.yesterday ? ` · wczoraj ${st.yesterday.bars} świec — ${st.yesterday.status || ''}` : '') +
      ` · szczegóły: arkusz FX`,
  ];
}

/** Pole fx w telemetry/state.json. */
function fxTelemetry_() {
  const st = fxStateLoad_();
  if (!st.last) return null;
  const d = (st.today && st.today.delays) || [];
  return {
    last: new Date(st.last * 1000).toISOString(), lastClose: st.lastClose, first: st.first, lastWriteAt: st.lastWriteAt || null,
    lastDelaySec: st.lastDelay === undefined ? null : st.lastDelay,
    today: st.today ? { date: st.today.date, bars: st.today.bars || 0, missing: st.today.missing || 0,
      delayMedianSec: fxQuantile_(d, 0.5), delayP90Sec: fxQuantile_(d, 0.9), delayMaxSec: d.length ? Math.max.apply(null, d) : null } : null,
    yesterday: st.yesterday || null,
    pendingChecks: fxCheckLoad_(),
  };
}
