/**
 * ============================================================================
 *  IA 4 — MODUŁ EURUSD  (Yahoo EURUSD=X, świece 5 min → Firestore fx/EURUSD → arkusz FX)
 *
 *  Wersja projektu: 1.17 (2026-10-07) — musi zgadzać się z IA4_INSTRUKCJA.md
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
 *    między sąsiednimi świecami i oznaczane (fillT) — dzień jest wtedy zamknięty.
 *  • Arkusz FX: stan (czy działa, ostatni zapis) + lista wszystkich dni.
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
  FILL_MIN_SHARE: 0.5,          // uzupełniamy tylko dzień, który ma co najmniej połowę świec z Yahoo
  OPEN_DOW: 7, OPEN_MIN: 17 * 60,         // rynek walutowy: od niedzieli 17:00 ET…
  CLOSE_DOW: 5, CLOSE_MIN: 17 * 60,       // …do piątku 17:00 ET
  MARGIN_MIN: 5,                // zapas przy pytaniu Yahoo na granicach tygodnia
  STALE_MIN: 5,                 // arkusz FX: „⚠”, gdy świeca nie przyszła tyle minut po spodziewanym zapisie
  SHEET: 'FX',
  TABLE_ROW: 13,                // nagłówek listy dni
};

const FX_STATUS_LABELS = ['Działa?', 'Ostatnia świeca (UTC)', 'Ostatnia świeca (PL)', 'Ostatni zapis (PL)',
  'Następna świeca spodziewana do (PL)', 'Opóźnienie zapisu', 'Dziś (UTC)', 'Dni w bazie'];
const FX_COLS = ['Data (UTC)', 'Dzień', 'Świec z Yahoo', 'Uśrednionych', 'Razem', 'Oczekiwanych',
  'Brakuje', 'Próby pobrania', 'Status', 'Aktualizacja (PL)'];
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
function fxExpected_(date, upTo) {
  const t0 = fxDayStart_(date);
  const noon = new Date((t0 + 43200) * 1000);
  const off = minutesOf_(noon, CONFIG.MARKET_TZ) - 12 * 60;            // ET − UTC w minutach (−240 / −300)
  const dowUtc = isoWeekday_(date);
  const out = [];
  for (let i = 0; i < 288; i++) {
    const t = t0 + i * FX.STEP_SEC;
    if (upTo && t + FX.STEP_SEC > upTo) break;
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
function fxDayInfo_(date, realT, fillT, upTo) {
  const have = {};
  realT.forEach(t => { have[t] = 1; });
  fillT.forEach(t => { have[t] = 1; });
  const fullExp = fxExpected_(date).length;
  const exp = upTo ? fxExpected_(date, upTo) : fxExpected_(date);
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
  if (st.scanV !== 2) { msgs.push(fxScan_(st)); }          // 1.17: rejestr dni i arkusz FX z istniejących danych
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
  const info = fxDayInfo_(date, real.map(b => b.t), fill.map(b => b.t), meta.upTo);
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
  try {
    res.forEach(r => fxSheetRow_(r.write.update.fields.date.stringValue, r.info, 0, r.write.update.fields.status.stringValue));
    fxSheetStatus_(st);
  } catch (e) { console.warn('FX arkusz: ' + e.message); }
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
    else { try { fxSheetRow_(y, fxDayInfo_(y, [], []), 0, 'weekend — brak handlu'); } catch (e) { console.warn('FX arkusz: ' + e.message); } }
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
  try { fxSheetStatus_(fxStateLoad_()); } catch (e) { console.warn('FX arkusz: ' + e.message); }
  return out.filter(x => x).join(' · ');
}

/**
 * Jedna próba dla dnia d: świece z Firestore + świeże z Yahoo (Yahoo wygrywa), braki liczone na nowo.
 * Brak braków → „kompletny”. Po CHECK_TRIES próbach z brakami → uśrednienie (gdy jest co najmniej
 * połowa świec z Yahoo) albo „brak danych z Yahoo”. Dzień zamknięty wypada z FX_CHECK.
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
  c.tries = old ? FX.CHECK_TRIES : c.tries + 1;
  let info = fxDayInfo_(d, real.map(b => b.t), []);
  let fill = [], status;
  const first = fxStateLoad_().first;
  if (!info.expected) status = 'weekend — brak handlu';
  else if (d === first && real.length) status = fxFirstDayStatus_(real[0].t);
  else if (!info.missing) status = 'kompletny';
  else if (c.tries < FX.CHECK_TRIES) {
    status = `braki — próba ${c.tries} z ${FX.CHECK_TRIES}`;
    c.next = Date.now() + FX.CHECK_EVERY_MIN * 60000;
  } else if (real.length >= FX.FILL_MIN_SHARE * info.expected) {
    fill = fxFill_(real.concat(anchors), info.missingT);
    status = `uzupełniony: ${fill.length} świec uśrednionych`;
  } else {
    status = 'brak danych z Yahoo — nie uzupełniono';
  }
  const nowIso = new Date().toISOString();
  const res = fxDayWrite_(d, real, fill, { tries: c.tries, status }, nowIso);
  firestoreCommit_([res.write]);
  if (status.indexOf('braki') !== 0) delete chk[d];
  const st = fxStateLoad_();
  if (d === fxDay_(nowSec - 86400)) { st.yesterday = { date: d, bars: res.info.total, missing: res.info.missing, filled: fill.length, status }; fxStateSave_(st); }
  try { fxSheetRow_(d, res.info, c.tries, status); } catch (e) { console.warn('FX arkusz: ' + e.message); }
  return `EURUSD ${d}: ${status}`;
}

/** Pierwszy dzień bazy zaczyna się w połowie (granica historii Yahoo) — nie jest ani kontrolowany, ani uzupełniany. */
function fxFirstDayStatus_(t) {
  return `pierwszy dzień bazy — od ${Utilities.formatDate(new Date(t * 1000), 'UTC', 'HH:mm')} UTC`;
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
/** Czyta wszystkie dni z Firestore, buduje arkusz FX i planuje kontrolę dni z brakami bez statusu końcowego. */
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
    const t0 = fxDayStart_(d);
    const num = v => Number(v.integerValue !== undefined ? v.integerValue : v.doubleValue);
    const arr = k => ((f[k] && f[k].arrayValue && f[k].arrayValue.values) || []).map(num);
    const fillT = arr('fillT').map(m => t0 + m * 60);
    const isFill = {};
    fillT.forEach(t => { isFill[t] = 1; });
    const realT = arr('t').map(m => t0 + m * 60).filter(t => !isFill[t]);
    const info = fxDayInfo_(d, realT, fillT, d === today ? nowSec : 0);
    let status = f.status ? f.status.stringValue : '';
    const tries = f.tries ? num(f.tries) : 0;
    const final = /^(kompletny|uzupełniony|weekend|brak danych)/.test(status);
    if (d === today) status = 'dzień trwa';
    else if (d === st.first && realT.length) status = fxFirstDayStatus_(realT[0]);
    else if (!final) {
      if (!info.expected) status = 'weekend — brak handlu';
      else if (!info.missing) status = 'kompletny';
      else { status = status || 'do kontroli'; if (!chk[d]) chk[d] = { tries, next: 0 }; }
    }
    days[d] = { info, tries, status };
  });
  fxCheckSave_(chk);
  fxSheetRebuild_(days, st.first);
  st.scanV = 2;
  fxStateSave_(st);
  fxSheetStatus_(st);
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
  if (sh && sh.getRange(FX.TABLE_ROW, 1).getValue() === FX_COLS[0]) return sh;
  if (!sh) sh = ss.insertSheet(FX.SHEET);
  sh.clear();
  sh.clearConditionalFormatRules();
  const W = FX_COLS.length;
  if (sh.getMaxColumns() < W) sh.insertColumnsAfter(sh.getMaxColumns(), W - sh.getMaxColumns());
  sh.setTabColor('#0b8043');
  sh.getRange(1, 1, 1, W).merge().setValue('IA 4 — EURUSD 5 min (Yahoo EURUSD=X → Firestore fx/EURUSD)')
    .setFontSize(14).setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff');
  sh.getRange(3, 1, FX_STATUS_LABELS.length, 1).setValues(FX_STATUS_LABELS.map(x => [x])).setFontWeight('bold').setBackground('#f1f3f4');
  sh.getRange(3, 2, FX_STATUS_LABELS.length, 1).setNumberFormat('@');
  sh.getRange(6, 2, 2, 1).setNumberFormat('yyyy-mm-dd hh:mm:ss');
  // „Działa?” liczy arkusz sam (co minutę), więc pokazuje problem także wtedy, gdy skrypt stanął
  sh.getRange(3, 2).setFormula(`=IF(B7="","",IF(NOW()>B7+${FX.STALE_MIN}/1440,"⚠ NIE — brak nowej świecy od "&TEXT(NOW()-B6,"[h]:mm")&" (sprawdź STATS i trigger)","✓ TAK — świece przychodzą na bieżąco"))`);
  sh.getRange(FX.TABLE_ROW - 1, 1, 1, W).merge()
    .setValue('DNI (UTC) — najnowsze na górze. Pełny dzień ma 288 świec; piątek i niedziela mniej (rynek otwarty od niedzieli 17:00 do piątku 17:00 czasu Nowego Jorku), sobota — 0.')
    .setFontWeight('bold').setBackground('#202124').setFontColor('#ffffff').setWrap(true);
  sh.getRange(FX.TABLE_ROW, 1, 1, W).setValues([FX_COLS]).setFontWeight('bold').setBackground('#f1f3f4').setWrap(true);
  sh.setColumnWidth(1, 270);
  sh.setColumnWidth(2, 330);
  sh.setColumnWidth(9, 280);
  sh.setColumnWidth(10, 130);
  sh.setFrozenRows(FX.TABLE_ROW);
  const rule = () => SpreadsheetApp.newConditionalFormatRule();
  sh.setConditionalFormatRules([
    rule().whenTextStartsWith('✓').setBackground('#ceead6').setFontColor('#0d652d').setRanges([sh.getRange(3, 2)]).build(),
    rule().whenTextStartsWith('⚠').setBackground('#fad2cf').setFontColor('#a50e0e').setRanges([sh.getRange(3, 2)]).build(),
    rule().whenNumberGreaterThan(0).setBackground('#fad2cf').setRanges([sh.getRange(FX.TABLE_ROW + 1, 7, 2000, 1)]).build(),
    rule().whenNumberGreaterThan(0).setBackground('#fef7e0').setRanges([sh.getRange(FX.TABLE_ROW + 1, 4, 2000, 1)]).build(),
  ]);
  return sh;
}

function fxRowValues_(d, info, tries, status) {
  return [d, FX_DOW[isoWeekday_(d)], info.real, info.filled, info.total, info.expected, info.missing, tries,
    status, Utilities.formatDate(new Date(), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm')];
}

/** Wiersz dnia: nadpisuje istniejący albo wstawia nowy (dni malejąco, najnowszy na górze). */
function fxSheetRow_(d, info, tries, status) {
  const sh = fxSheet_();
  const first = FX.TABLE_ROW + 1;
  const n = Math.max(sh.getLastRow() - FX.TABLE_ROW, 0);
  const dates = n ? sh.getRange(first, 1, n, 1).getValues().map(r => String(r[0])) : [];
  const row = fxRowValues_(d, info, tries, status);
  const i = dates.indexOf(d);
  if (i >= 0) { sh.getRange(first + i, 1, 1, row.length).setValues([row]); return; }
  let pos = dates.findIndex(x => x < d);                   // pierwszy starszy dzień
  if (pos < 0) pos = dates.length;
  // dni bez dokumentu (sobota) między nowym dniem a następnym w tabeli
  const rows = [row];
  const next = dates[pos - 1];                             // nowszy sąsiad (jeśli wstawiamy w środek)
  if (pos === 0 && dates.length) {
    for (let t = fxDayStart_(d) - 86400; fxDay_(t) > dates[0]; t -= 86400) {
      const dd = fxDay_(t);
      rows.push(fxRowValues_(dd, fxDayInfo_(dd, [], []), 0, fxExpected_(dd).length ? 'brak danych' : 'weekend — brak handlu'));
    }
  }
  if (next === undefined || pos === 0) {
    sh.insertRowsBefore(first + pos, rows.length);
    sh.getRange(first + pos, 1, rows.length, row.length).setValues(rows).setFontWeight('normal').setBackground(null);
  } else {
    sh.insertRowsBefore(first + pos, 1);
    sh.getRange(first + pos, 1, 1, row.length).setValues([row]).setFontWeight('normal').setBackground(null);
  }
}

/** Cała lista dni od pierwszego dnia bazy do dziś (także soboty bez dokumentu). */
function fxSheetRebuild_(days, firstDay) {
  const sh = fxSheet_();
  const first = FX.TABLE_ROW + 1;
  const n = Math.max(sh.getLastRow() - FX.TABLE_ROW, 0);
  if (n) sh.getRange(first, 1, n, FX_COLS.length).clearContent();
  const known = Object.keys(days).sort();
  if (!known.length) return;
  const start = firstDay && firstDay < known[0] ? firstDay : known[0];
  const rows = [];
  for (let t = fxDayStart_(fxDay_(Date.now() / 1000)); fxDay_(t) >= start; t -= 86400) {
    const d = fxDay_(t);
    const x = days[d];
    rows.push(x ? fxRowValues_(d, x.info, x.tries, x.status)
      : fxRowValues_(d, fxDayInfo_(d, [], []), 0, fxExpected_(d).length ? 'brak danych' : 'weekend — brak handlu'));
  }
  if (sh.getMaxRows() < first + rows.length) sh.insertRowsAfter(sh.getMaxRows(), first + rows.length - sh.getMaxRows());
  sh.getRange(first, 1, rows.length, FX_COLS.length).setValues(rows);
}

/** Blok stanu arkusza FX. */
function fxSheetStatus_(st) {
  if (!st.last) return;
  const sh = fxSheet_();
  const tz = CONFIG.LOCAL_TZ;
  const t = new Date(st.last * 1000), t2 = new Date((st.last + FX.STEP_SEC) * 1000);
  // następna świeca: zamknięcie kolejnej + zapas na opóźnienie; przy zamkniętym rynku — od otwarcia
  let nextT = st.last + FX.STEP_SEC;
  for (let i = 0; i < 2 * 24 * 12 * 3 && !fxSlotOpen_(nextT); i++) nextT += FX.STEP_SEC;
  const expectBy = new Date((nextT + FX.STEP_SEC + 120) * 1000);
  const d = (st.today && st.today.delays) || [];
  const sec = s => (s === null || s === undefined) ? '—' : fmtDelay_(s * 1000);
  const chk = fxCheckLoad_();
  const nCheck = Object.keys(chk).length;
  const td = st.today || {};
  sh.getRange(4, 2, FX_STATUS_LABELS.length - 1, 1).setValues([
    [`${fxDay_(st.last)} ${Utilities.formatDate(t, 'UTC', 'HH:mm')}–${Utilities.formatDate(t2, 'UTC', 'HH:mm')} · close ${st.lastClose}`],
    [`${Utilities.formatDate(t, tz, 'yyyy-MM-dd HH:mm')}–${Utilities.formatDate(t2, tz, 'HH:mm')}`],
    [st.lastWriteAt ? new Date(st.lastWriteAt) : ''],
    [expectBy],
    [`ostatnia ${sec(st.lastDelay)}` + (d.length ? ` · dziś: mediana ${sec(fxQuantile_(d, 0.5))}, max ${sec(Math.max.apply(null, d))}` : '')],
    [`${td.date || '—'}: świec ${td.bars || 0} z ${td.expectedSoFar || 0} oczekiwanych do teraz, brakuje ${td.missing || 0}` +
      (fxMarketOpen_(new Date()) ? '' : ' · rynek zamknięty')],
    [`od ${st.first || '?'}` + (nCheck ? ` · dni czekających na kolejną próbę pobrania: ${nCheck}` : ' · wszystkie zakończone dni sprawdzone')],
  ]);
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
