/**
 * ============================================================================
 *  IA 4 — TELEMETRIA  (stan zbierania → telemetry/state.json w GitHub)
 *
 *  Wersja projektu: 1.26 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  Claude widzi tylko repozytorium, nie arkusz. Ten plik raz na godzinę
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
  STAGE: 'Etap 2 — poszukiwanie strategii (wstrzymane) · Etap 3 — paper trading · moduł EURUSD — zbieranie · Etap 4 — prognoza EURUSD (rozkład, scenariusze)',   // zmieniać razem z nagłówkiem instrukcji
  MIN_GAP_MIN: 10,
};

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
