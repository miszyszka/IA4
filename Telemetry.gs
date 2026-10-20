/**
 * ============================================================================
 *  IA 4 — TELEMETRIA  (stan zbierania → telemetry/state.json w GitHub)
 *
 *  Wersja projektu: 1.51 (2026-10-20) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Claude widzi tylko repozytorium, nie arkusz. Ten plik raz na godzinę (i zaraz po świecy sesji)
 *  publikuje krótki stan bazy: etap, wersję, stan automatu i dla każdego
 *  instrumentu ostatnią świecę oraz liczbę świec w bazie. Commit powstaje
 *  tylko wtedy, gdy coś się zmieniło.
 *
 *  Token GitHub: Script Properties → GITHUB_TOKEN (menu IA 4 → Ustaw token).
 *  Nigdy nie trafia do repozytorium ani do arkusza.
 * ============================================================================
 */

const TELEMETRY = {
  REPO: 'miszyszka/IA4',
  BRANCH: 'main',
  PATH: 'telemetry/state.json',
  STAGE: 'Etap 1 baza akcji ✅ · Etap 2 poszukiwanie (wstrzymane) · Etap 3 paper trading i wirtualny inwestor · Etap 4 FX 1h — zbieranie 10 par + BTC i prognoza (FX-7) · Etap 5 strona IA4 · Etap 6 AI Investor (AI-2: Agent-Investor)',   // zmieniać razem z nagłówkiem instrukcji
  MIN_GAP_MIN: 10,
};

// ============================================================================
//  telemetry/vi.json — wirtualny inwestor dla strony IA4 (instrukcja, sekcja 11b)
//  Wysyła go Paper.gs zaraz po przeliczeniu świecy (i „zacznij od nowa”); commit
//  tylko, gdy treść się zmieniła (VI_HASH). Cała zawartość pochodzi ze stanu
//  inwestora (_IA4_DANE) — nic nowego nie jest liczone.
// ============================================================================
const VI_PUB = {
  PATH: 'telemetry/vi.json',
  CLOSED: 150,          // ostatnich zamkniętych transakcji z pełnym opisem
  EQUITY: 2000,         // punktów krzywej wyniku (każda zamknięta transakcja)
  SIGNALS: 35,          // ostatnich świec z sygnałami (5 sesji)
};

function telemetryViPublish_(state, X, invIds, active, prio) {
  const doc = telemetryViDoc_(state, invIds, active, prio);
  const props = PropertiesService.getScriptProperties();
  const body = JSON.parse(JSON.stringify(doc));
  delete body.generatedAt;
  const raw = Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, JSON.stringify(body), Utilities.Charset.UTF_8);
  const hash = raw.map(b => ((b & 0xFF) + 0x100).toString(16).slice(1)).join('');
  if (hash === props.getProperty('VI_HASH')) return false;
  if (!props.getProperty('GITHUB_TOKEN')) return false;
  telemetryGithubPut_(VI_PUB.PATH, JSON.stringify(doc), `VI ${doc.lastCandlePL || ''}`.trim());
  props.setProperty('VI_HASH', hash);
  return true;
}

function telemetryViDoc_(state, invIds, active, prio) {
  const lab = K => K ? pp_closeLabel_(K, {}).pl : null;
  const r2 = x => (x === undefined || x === null) ? null : Math.round(x * 100) / 100;
  const r4 = x => (x === undefined || x === null) ? null : Math.round(x * 10000) / 10000;
  const P = state.positions || [];
  const closed = P.filter(p => p.status === 'zamknięta').sort((a, b) => (a.exitKey - b.exitKey) || (a.no - b.no));
  const live = P.filter(p => p.status !== 'zamknięta').sort((a, b) => b.no - a.no);
  const cs = pp_closedStats_(P);
  const cnt = k => closed.filter(p => p.exitKind === k).length;
  const unreal = live.filter(p => p.status === 'otwarta').reduce((a, p) => a + PAPER.STAKE * (p.retNow || 0) / 100, 0);
  let cum = 0;
  const equity = closed.map(p => { cum += p.pnl; return [lab(p.exitKey), r2(cum)]; }).slice(-VI_PUB.EQUITY);
  const by = {};
  P.forEach(p => {
    const b = by[p.id] || (by[p.id] = { n: 0, tp: 0, sumPct: 0, usd: 0, open: 0 });
    if (p.status === 'zamknięta') { b.n++; b.sumPct += p.ret; b.usd += p.pnl; if (p.exitKind === 'TP') b.tp++; } else b.open++;
  });
  const ids = Array.from(new Set((active || []).concat(invIds || [])));
  const vi = new Set(invIds || []);
  return {
    version: CONFIG.VERSION,
    generatedAt: new Date().toISOString(),
    lastCandleKey: state.lastKey || 0,
    lastCandlePL: lab(state.lastKey),
    since: state.startedAt || null,
    capital: PAPER.CAPITAL, stake: PAPER.STAKE, costPct: PAPER.COST_PCT, maxPerTicker: PAPER.MAX_PER_TICKER,
    summary: {
      closed: closed.length, open: live.filter(p => p.status === 'otwarta').length,
      pending: live.filter(p => p.status === 'oczekuje').length,
      avgPct: r4(cs.avg), ci95Pct: r4(cs.ci), realizedUsd: r2(cs.usd), unrealizedUsd: r2(unreal), tpShare: r4(cs.tp),
      exits: { TP: cnt('TP'), SL: cnt('SL'), FC: cnt('FC'), LIMIT: cnt('LIMIT') },
      medianBars: closed.length ? pp_median_(closed.map(p => p.bars || 0)) : null,
      costsUsd: r2(closed.reduce((a, p) => a + PAPER.STAKE * (p.cost || 0) / 100, 0)),
    },
    open: live.map(p => ({ no: p.no, id: p.id, sym: p.sym, dir: p.dir > 0 ? 'long' : 'short', status: p.status,
      signal: lab(p.sigKey), entryAt: lab(p.entryKey), entry: r4(p.entry), sl: p.sl, tp: p.tp, slPx: p.slPx || null,
      tpPx: p.tpPx || null, price: r4(p.price), retPct: r4(p.retNow), usd: r2(PAPER.STAKE * (p.retNow || 0) / 100),
      bars: p.bars || 0, maxBars: p.maxBars || 0, lastAt: lab(p.lastKey) })),
    closed: closed.slice(-VI_PUB.CLOSED).reverse().map(p => ({ no: p.no, id: p.id, sym: p.sym, dir: p.dir > 0 ? 'long' : 'short',
      entryAt: lab(p.entryKey), entry: r4(p.entry), exitAt: lab(p.exitKey), exit: r4(p.exitPx), kind: p.exitKind,
      retPct: r4(p.ret), usd: r2(p.pnl), bars: p.bars || 0 })),
    equity,
    strategies: ids.map(id => {
      const b = by[id] || { n: 0, tp: 0, sumPct: 0, usd: 0, open: 0 };
      const rl = state.rules && state.rules[id];
      return { id, desc: rl ? rl.desc : null, forVI: vi.has(id), active: (active || []).indexOf(id) >= 0,
               priority: prio && prio[id] !== undefined ? prio[id] + 1 : null, closed: b.n, open: b.open,
               avgPct: b.n ? r4(b.sumPct / b.n) : null, tpShare: b.n ? r4(b.tp / b.n) : null, usd: r2(b.usd) };
    }),
    signals: (state.sigLog || []).slice().reverse().map(([K, fired]) => ({ at: lab(K), key: K, fired })),
  };
}

/** Handler triggera godzinowego — NIE zmieniaj nazwy. */
function telemetryHourly() { telemetryPublish_(false); }

function telemetryPublishNow() {
  const r = telemetryPublish_(true);
  alert_(r.pushed ? `Stan wysłany do GitHub: ${TELEMETRY.PATH}` : `Nie wysłano: ${r.reason}`);
}

function telemetrySetToken() {
  const ui = SpreadsheetApp.getUi();
  const resp = ui.prompt('Token GitHub',
    `Wklej token z prawem zapisu (Contents: Read and write) do ${TELEMETRY.REPO}.\n` +
    'Zostaw puste i kliknij OK, żeby usunąć zapisany token.', ui.ButtonSet.OK_CANCEL);
  if (resp.getSelectedButton() !== ui.Button.OK) return;
  const token = resp.getResponseText().trim();
  const props = PropertiesService.getScriptProperties();
  if (!token) { props.deleteProperty('GITHUB_TOKEN'); toast_('Token usunięty.'); return; }
  props.setProperty('GITHUB_TOKEN', token);
  const check = telemetryGithubGet_(TELEMETRY.PATH);
  toast_(check.ok || check.status === 404 ? 'Token zapisany i działa.' : `GitHub odpowiedział ${check.status} — sprawdź uprawnienia.`);
}

function telemetryPublish_(force) {
  const snapshot = telemetryCollect_();
  const json = JSON.stringify(snapshot, null, 2);
  const props = PropertiesService.getScriptProperties();
  const hash = telemetryHash_(snapshot);

  if (!force && hash === props.getProperty('TELEMETRY_HASH')) return { pushed: false, reason: 'bez zmian' };
  if (!force && Date.now() - Number(props.getProperty('TELEMETRY_PUSHED_AT') || 0) < TELEMETRY.MIN_GAP_MIN * 60000) {
    return { pushed: false, reason: 'za wcześnie po poprzednim wysłaniu' };
  }
  if (!props.getProperty('GITHUB_TOKEN')) return { pushed: false, reason: 'brak tokenu GitHub (menu → Ustaw token GitHub)' };
  try {
    telemetryGithubPut_(TELEMETRY.PATH, json, `Stan bazy ${snapshot.generatedAtPL}`);
    props.setProperty('TELEMETRY_HASH', hash);
    props.setProperty('TELEMETRY_PUSHED_AT', String(Date.now()));
    return { pushed: true };
  } catch (e) {
    console.error('Telemetria → GitHub: ' + e.message);
    return { pushed: false, reason: e.message };
  }
}

function telemetryCollect_() {
  const p = PropertiesService.getScriptProperties();
  const now = new Date();
  const live = JSON.parse(p.getProperty('LIVE_STATE') || '{}');
  const counts = JSON.parse(p.getProperty('BASE_COUNTS') || 'null');
  return {
    version: CONFIG.VERSION,
    stage: TELEMETRY.STAGE,
    generatedAt: now.toISOString(),
    generatedAtPL: Utilities.formatDate(now, CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm'),
    collector: {
      triggers: ScriptApp.getProjectTriggers().map(t => t.getHandlerFunction()).sort(),
      lastRun: JSON.parse(p.getProperty('LAST_RUN') || 'null'),
      lastWrite: p.getProperty('LAST_WRITE') || '',
      today: JSON.parse(p.getProperty('COUNTERS') || '{}'),
      lastError: JSON.parse(p.getProperty('LAST_ERROR') || 'null'),
    },
    nightly: JSON.parse(p.getProperty('NIGHTLY_INFO') || 'null'),
    doubleProofHistory: backfillLabel_(),
    lastCandle: telemetryCandle_(p),
    fx: fxTelemetry_(),
    daily: dailyTelemetry_(),                        // Daily.gs: baza świec dobowych (sekcja 4d)
    vi: JSON.parse(p.getProperty('VI_SUMMARY') || 'null'),
    base: counts ? { countedAt: counts.at, totalCandles: counts.total } : null,
    instruments: allSymbols_().map(s => {
      const st = live[s] || {};
      const c = counts && counts.items[s];
      return {
        symbol: s,
        group: symbolGroup_(s),
        last: st.d ? `${st.d} #${st.s + 1}` : '',
        lastClose: st.c !== undefined ? st.c : null,
        candles: c ? c.candles : null,
        first: c ? c.first : '',
        status: st.st || '',
      };
    }),
  };
}

/** Ostatnia świeca z tabeli STATS: czasy od zamknięcia w sekundach (instrukcja, sekcja 4a). */
function telemetryCandle_(p) {
  const r = JSON.parse(p.getProperty('CANDLE_LOG') || 'null');
  if (!r) return null;
  const rel = t => t ? Math.round((t - r.closeAt) / 1000) : null;
  return { key: r.key, start: rel(r.start), main3: rel(r.main), traded53: rel(r.d53), all75: rel(r.all),
           signals: rel(r.sig), sheets: rel(r.sheets), written: r.written || 0, missing: r.missing || [],
           rounds: r.rounds || 0, stagesMs: r.stages || {} };
}

/** Suma kontrolna treści bez pól, które zmieniają się przy każdym uruchomieniu. */
function telemetryHash_(snapshot) {
  const copy = JSON.parse(JSON.stringify(snapshot));
  delete copy.generatedAt;
  delete copy.generatedAtPL;
  delete copy.collector.lastRun;
  copy.instruments.forEach(i => { delete i.status; });
  const raw = Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, JSON.stringify(copy), Utilities.Charset.UTF_8);
  return raw.map(b => ((b & 0xFF) + 0x100).toString(16).slice(1)).join('');
}

function telemetryGithubGet_(path) {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) return { ok: false, status: 0, sha: null };
  const resp = UrlFetchApp.fetch(`https://api.github.com/repos/${TELEMETRY.REPO}/contents/${path}?ref=${TELEMETRY.BRANCH}`, {
    muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
  });
  const code = resp.getResponseCode();
  return code === 200 ? { ok: true, status: code, sha: JSON.parse(resp.getContentText()).sha } : { ok: false, status: code, sha: null };
}

function telemetryGithubPut_(path, content, message) {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  const existing = telemetryGithubGet_(path);
  const payload = {
    message,
    content: Utilities.base64Encode(content, Utilities.Charset.UTF_8),
    branch: TELEMETRY.BRANCH,
  };
  if (existing.sha) payload.sha = existing.sha;
  const resp = UrlFetchApp.fetch(`https://api.github.com/repos/${TELEMETRY.REPO}/contents/${path}`, {
    method: 'put',
    contentType: 'application/json',
    muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
    payload: JSON.stringify(payload),
  });
  const code = resp.getResponseCode();
  if (code !== 200 && code !== 201) {
    let msg = '';
    try { msg = JSON.parse(resp.getContentText()).message || ''; } catch (e) { /* nie-JSON */ }
    throw new Error(`GitHub HTTP ${code}${msg ? ' — ' + msg : ''}`);
  }
}
