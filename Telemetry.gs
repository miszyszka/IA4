/**
 * ============================================================================
 *  IA 4 — TELEMETRIA  (stan systemu → Firestore → GitHub)
 *
 *  Wersja projektu: 0.27 (2026-09-26) — musi zgadzać się z IA4_INSTRUKCJA.md
 * ============================================================================
 *  PO CO TO JEST
 *  Claude nie ma dostępu do arkusza ani do edytora Apps Script — widzi wyłącznie
 *  repozytorium GitHub. Do tej pory stan systemu (luki, błędy, postęp pobierania,
 *  dziennik zdarzeń) trzeba było ręcznie kopiować do rozmowy. Ten plik zbiera to
 *  wszystko w jeden dokument JSON, zapisuje go w Firestore i wypycha do repo,
 *  żeby przy następnej rozmowie wystarczyło powiedzieć „zobacz telemetrię”.
 *
 *  DLACZEGO APPS SCRIPT PISZE DO GITHUB, A NIE GITHUB ODPYTUJE FIRESTORE
 *  Pierwszy pomysł był taki, żeby automat w repozytorium co 10 minut sprawdzał
 *  Firestore. Ma trzy wady, których to rozwiązanie nie ma:
 *    1. GitHub Actions musiałby mieć klucz serwisowy Firebase jako sekret —
 *       drugą kopię poświadczenia, które zgodnie z 6.5 trzymamy w jednym miejscu.
 *    2. Zadania cykliczne na GitHubie potrafią spóźniać się kilkanaście minut
 *       albo zostać pominięte przy obciążeniu — „co 10 minut” nie jest pewne.
 *    3. Odpytywanie zużywałoby odczyty Firestore także wtedy, gdy nic się nie
 *       zmieniło (~144 odczyty dziennie w kółko).
 *  Apps Script wie dokładnie, kiedy coś się zmieniło, więc wypycha tylko wtedy —
 *  natychmiast i bez dodatkowego sekretu po drugiej stronie.
 *
 *  TOKEN GITHUB
 *  Trzymany w Script Properties pod kluczem GITHUB_TOKEN, ustawiany z menu
 *  (IA 4 → Projekt → Telemetria → Ustaw token GitHub). Nigdy nie trafia do
 *  repozytorium ani do arkusza. Wystarczy token z prawem zapisu do zawartości
 *  tego jednego repozytorium.
 *
 *  CO POWSTAJE W REPO
 *    telemetry/state.json              — zawsze najnowszy stan
 *    telemetry/history/YYYY-MM-DD.json — migawka dnia (nadpisywana w ciągu dnia)
 *
 *  Plik wymaga Code.gs (CONFIG, log_, alert_, toast_, firestoreCommit_, fsBase_)
 *  oraz Project.gs (PROJECT, projLoad_, STAGES).
 * ============================================================================
 */

const TELEMETRY = {
  REPO: 'miszyszka/IA4',
  BRANCH: 'main',
  PATH: 'telemetry/state.json',
  HISTORY_DIR: 'telemetry/history',
  MIN_GAP_MIN: 10,      // najkrótszy odstęp między wypchnięciami do GitHub
  MAX_GAPS: 400,        // ile luk najwyżej trafia do dokumentu
  MAX_LOG: 80,          // ile ostatnich wpisów dziennika
  MAX_BYTES: 900000,    // zabezpieczenie przed rozdęciem dokumentu
};


// ============================================================================
//  FUNKCJE PUBLICZNE (menu)
// ============================================================================

/** Zbiera stan i publikuje go od razu, bez czekania na odstęp. */
function telemetryPublishNow() {
  const r = telemetryPublish_(true);
  alert_(r.pushed
    ? `Stan wysłany.\n\nFirestore: system/telemetry\nGitHub: ${TELEMETRY.PATH}\n\n` +
      `Luk: ${r.snapshot.data.gaps.total}, błędów: ${r.snapshot.collector.errors.length}, ` +
      `rozmiar: ${Math.round(r.bytes / 1024)} kB`
    : `Stan zapisany w Firestore, ale nie wysłany do GitHub:\n${r.reason}`);
}

/** Handler triggera godzinowego — NIE zmieniaj nazwy. */
function telemetryHourly() { telemetryPublish_(false); }

function telemetrySetToken() {
  const ui = SpreadsheetApp.getUi();
  const resp = ui.prompt('Token GitHub',
    'Wklej token z prawem zapisu do repozytorium ' + TELEMETRY.REPO + '.\n\n' +
    'GitHub → Settings → Developer settings → Personal access tokens.\n' +
    'Token zostanie zapisany w Script Properties i nigdy nie trafi do arkusza ani do repo.\n\n' +
    'Zostaw puste i kliknij OK, żeby usunąć zapisany token.',
    ui.ButtonSet.OK_CANCEL);
  if (resp.getSelectedButton() !== ui.Button.OK) return;

  const token = resp.getResponseText().trim();
  const props = PropertiesService.getScriptProperties();
  if (!token) { props.deleteProperty('GITHUB_TOKEN'); toast_('Token usunięty.'); return; }

  props.setProperty('GITHUB_TOKEN', token);
  const check = telemetryGithubGet_(TELEMETRY.PATH);
  toast_(check.ok || check.status === 404
    ? 'Token zapisany i działa.'
    : `Token zapisany, ale GitHub odpowiedział ${check.status}. Sprawdź uprawnienia.`);
}

function telemetryInstallTrigger() {
  telemetryRemoveTrigger_();
  ScriptApp.newTrigger('telemetryHourly').timeBased().everyHours(1).create();
  toast_('Telemetria będzie wysyłana co godzinę.');
}

function telemetryRemoveTrigger_() {
  let n = 0;
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'telemetryHourly') { ScriptApp.deleteTrigger(t); n++; }
  });
  return n;
}


// ============================================================================
//  PUBLIKACJA
// ============================================================================
function telemetryPublish_(force) {
  const snapshot = telemetryCollect_();
  const json = JSON.stringify(snapshot, null, 2);
  const bytes = Utilities.newBlob(json).getBytes().length;

  // 1) Firestore — źródło prawdy dla dashboardu. Przy wyczerpanym limicie
  //    pomijamy, ale NIE rezygnujemy z punktu 2: GitHub to inny serwis, więc
  //    właśnie wtedy telemetria jest najbardziej potrzebna — to z niej dowiemy
  //    się, co się działo w dniu, w którym baza przestała przyjmować zapisy.
  if (!fsQuotaBlocked_()) {
    try {
      telemetryToFirestore_(snapshot, json, bytes);
    } catch (e) {
      console.error('Telemetria → Firestore: ' + e.message);
    }
  }

  // 2) GitHub — tylko gdy treść się zmieniła i minął odstęp.
  const props = PropertiesService.getScriptProperties();
  const hash = telemetryHash_(snapshot);
  const lastHash = props.getProperty('TELEMETRY_HASH');
  const lastAt = Number(props.getProperty('TELEMETRY_PUSHED_AT') || 0);

  if (!force && hash === lastHash) return { pushed: false, reason: 'bez zmian', snapshot, bytes };
  if (!force && Date.now() - lastAt < TELEMETRY.MIN_GAP_MIN * 60000) {
    return { pushed: false, reason: 'za wcześnie po poprzednim wysłaniu', snapshot, bytes };
  }
  if (bytes > TELEMETRY.MAX_BYTES) {
    return { pushed: false, reason: `dokument za duży (${Math.round(bytes / 1024)} kB)`, snapshot, bytes };
  }
  if (!props.getProperty('GITHUB_TOKEN')) {
    return { pushed: false, reason: 'brak tokenu GitHub (menu → Ustaw token GitHub)', snapshot, bytes };
  }

  try {
    const day = Utilities.formatDate(new Date(), CONFIG.LOCAL_TZ, 'yyyy-MM-dd');
    telemetryGithubPut_(TELEMETRY.PATH, json, `Telemetria ${snapshot.meta.generatedAt}`);
    telemetryGithubPut_(`${TELEMETRY.HISTORY_DIR}/${day}.json`, json, `Telemetria — migawka ${day}`);
    props.setProperty('TELEMETRY_HASH', hash);
    props.setProperty('TELEMETRY_PUSHED_AT', String(Date.now()));
    return { pushed: true, snapshot, bytes };
  } catch (e) {
    log_('UWAGA', 'TELEMETRIA', 'Wysyłka do GitHub nie powiodła się: ' + e.message);
    return { pushed: false, reason: e.message, snapshot, bytes };
  }
}

function telemetryToFirestore_(snapshot, json, bytes) {
  firestoreCommit_([{
    update: {
      name: `${fsBase_()}/system/telemetry`,
      fields: {
        json: { stringValue: json },
        generatedAt: { timestampValue: snapshot.meta.generatedAt },
        version: { stringValue: snapshot.meta.version },
        stage: { integerValue: String(snapshot.project.stage) },
        gapsNew: { integerValue: String(snapshot.data.gaps.new) },
        errors: { integerValue: String(snapshot.collector.errors.length) },
        bytes: { integerValue: String(bytes) },
        updatedAt: { timestampValue: new Date().toISOString() },
      },
    },
  }]);
}

/**
 * Suma kontrolna TREŚCI, z pominięciem pól, które zmieniają się przy każdym
 * uruchomieniu (czas wygenerowania, czas ostatniego przebiegu automatu).
 *
 * Bez tego pominięcia porównanie „czy coś się zmieniło" nigdy nie wykrywało
 * braku zmian — `generatedAt` zawsze był inny, więc telemetria wypychała do
 * repozytorium nowy commit co godzinę, także w nocy i w weekend, gdy nic się
 * nie działo. Przy dwóch plikach na publikację dawało to ~48 commitów dziennie
 * i przepisywanie całej migawki od nowa bez powodu.
 */
function telemetryHash_(snapshot) {
  const copy = JSON.parse(JSON.stringify(snapshot));
  delete copy.meta.generatedAt;
  delete copy.meta.generatedAtPL;
  if (copy.collector) delete copy.collector.lastRunAt;
  const raw = Utilities.computeDigest(
    Utilities.DigestAlgorithm.MD5, JSON.stringify(copy), Utilities.Charset.UTF_8);
  return raw.map(b => ((b & 0xFF) + 0x100).toString(16).slice(1)).join('');
}


// ============================================================================
//  ZBIERANIE STANU
// ============================================================================
function telemetryCollect_() {
  const now = new Date().toISOString();
  const st = projLoad_();
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  return {
    meta: {
      version: PROJECT.INSTRUCTION_VERSION,
      generatedAt: now,
      generatedAtPL: Utilities.formatDate(new Date(), CONFIG.LOCAL_TZ, 'yyyy-MM-dd HH:mm'),
      spreadsheet: ss.getName(),
      note: 'Pełny stan systemu IA 4. Zapisywany przez Telemetry.gs, czytany przez Claude z repozytorium.',
    },
    project: telemetryProject_(st),
    data: telemetryData_(st, ss),
    collector: telemetryCollector_(),
    jobs: telemetryJobs_(),
    log: telemetryLog_(ss),
  };
}

function telemetryProject_(st) {
  const stage = STAGES.filter(s => s.n === st.current)[0] || STAGES[0];
  // Kryteria liczy ta sama funkcja, która buduje arkusz PROJEKT — dzięki temu
  // telemetria nie może pokazać czegoś innego niż arkusz (luka L12).
  let criteria = [];
  try {
    criteria = projEvalCriteria_(st.current, st, projReadInputs_())
      .map(c => ({ id: c.id, text: c.text, mode: c.mode, ok: !!c.ok, detail: String(c.detail || '') }));
  } catch (e) {
    criteria = [{ id: '?', text: 'nie udało się policzyć kryteriów: ' + e.message, ok: false, detail: '' }];
  }

  return {
    stage: st.current,
    stageName: stage.name,
    stages: STAGES.map(s => ({
      n: s.n, name: s.name,
      status: (st.stages[s.n] || {}).status || 'todo',
      started: (st.stages[s.n] || {}).started || '',
      finished: (st.stages[s.n] || {}).finished || '',
    })),
    criteria,
    criteriaMet: criteria.filter(c => c.ok).length,
    criteriaTotal: criteria.length,
    vault: {
      researchEndExclusive: PROJECT.RESEARCH_END_EXCLUSIVE,
      vaultStart: PROJECT.VAULT_START,
      vaultEnd: PROJECT.VAULT_END,
      liveFrom: PROJECT.LIVE_FROM,
      opened: !!st.vaultOpened,
      openedAt: st.vaultOpenedAt || '',
      writtenAt: (st.firestore || {}).at || '',
    },
  };
}

function telemetryData_(st, ss) {
  const a = st.audit || {};
  const gaps = telemetryGaps_(ss);
  return {
    audit: { fullAt: a.fullAt || '', nightlyAt: a.nightlyAt || '' },
    gaps: {
      total: gaps.length,
      new: gaps.filter(g => g.status !== 'zaakceptowana').length,
      accepted: gaps.filter(g => g.status === 'zaakceptowana').length,
      byType: gaps.reduce((acc, g) => { acc[g.type] = (acc[g.type] || 0) + 1; return acc; }, {}),
      bySymbol: gaps.reduce((acc, g) => { acc[g.symbol] = (acc[g.symbol] || 0) + 1; return acc; }, {}),
      items: gaps.slice(0, TELEMETRY.MAX_GAPS),
      truncated: gaps.length > TELEMETRY.MAX_GAPS,
    },
    instruments: telemetryInstruments_(st),
  };
}

function telemetryGaps_(ss) {
  const sh = ss.getSheetByName(PROJECT.AUDIT_SHEET);
  if (!sh || sh.getLastRow() < 2) return [];
  const rows = sh.getRange(2, 1, sh.getLastRow() - 1, 6).getValues();

  const dec = ss.getSheetByName(PROJECT.DECISION_SHEET);
  const decisions = {};
  if (dec && dec.getLastRow() > 1) {
    dec.getRange(2, 1, dec.getLastRow() - 1, 3).getValues()
      .forEach(r => { if (r[0]) decisions[String(r[0])] = { status: String(r[1] || ''), comment: String(r[2] || '') }; });
  }

  return rows.filter(r => r[1]).map(r => {
    const d = decisions[String(r[0])] || {};
    return {
      symbol: String(r[1]), type: String(r[2]), date: String(r[3]),
      desc: String(r[4]), detectedAt: String(r[5]),
      status: d.status || 'nowa', comment: d.comment || '',
    };
  });
}

function telemetryInstruments_(st) {
  // Pełny audyt zapisuje tabelę instrumentów pod st.audit.stats (nie st.stats) —
  // mapa symbol → { sessions, candles, first, last }.
  const s = (st.audit && st.audit.stats) || {};
  const items = Object.keys(s).map(sym => ({
    symbol: sym,
    sessions: s[sym].sessions || 0,
    candles: s[sym].candles || 0,
    first: s[sym].first || '',
    last: s[sym].last || '',
  }));
  return {
    countedAt: (st.audit || {}).fullAt || '',
    total: items.length,
    totalSessions: items.reduce((a, x) => a + x.sessions, 0),
    totalCandles: items.reduce((a, x) => a + x.candles, 0),
    items,
  };
}

/** Ostatnie uruchomienie automatu — komórka w STATS (nie ma go w Properties). */
function telemetryLastRun_() {
  try {
    const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.STATS_SHEET);
    const v = sh && sh.getRange(STATS.LAST_RUN, 2).getValue();
    return v instanceof Date ? v.toISOString() : String(v || '');
  } catch (e) {
    return '';
  }
}

function telemetryCollector_() {
  const props = PropertiesService.getScriptProperties();
  const live = JSON.parse(props.getProperty('LIVE_STATE') || '{}');
  const fs = JSON.parse(props.getProperty('FS_STATUS') || 'null');
  const lastError = JSON.parse(props.getProperty('LAST_ERROR') || 'null');

  const symbols = Object.keys(live).map(s => ({
    symbol: s,
    lastKey: live[s].k || 0,
    status: live[s].st || '',
    lastDate: live[s].d || '',
    lastClose: live[s].c || null,
  }));

  const quotaDay = props.getProperty('FS_QUOTA_DAY') || '';
  return {
    lastRunAt: telemetryLastRun_(),
    symbols,
    symbolsCount: symbols.length,
    firestore: fs,
    // Gdy limit jest wyczerpany, połowa dziennika to komunikaty o 429 i łatwo
    // uznać, że system jest zepsuty. To pole mówi wprost: czeka na reset.
    quota: {
      blocked: quotaDay === Utilities.formatDate(new Date(), 'America/Los_Angeles', 'yyyy-MM-dd'),
      exhaustedOnPacificDay: quotaDay,
      note: quotaDay ? 'Zadania w tle wstrzymane do resetu (północ czasu pacyficznego, ok. 9:00 w Polsce).' : '',
    },
    errors: symbols.filter(x => /✗|błąd|error/i.test(x.status))
      .map(x => ({ symbol: x.symbol, status: x.status })),
    lastError,
  };
}

function telemetryJobs_() {
  const props = PropertiesService.getScriptProperties();
  const parse = (k) => { try { return JSON.parse(props.getProperty(k) || 'null'); } catch (e) { return null; } };
  const proof = parse('PROOF_STATE') || {};
  const hist = parse('HISTORY_STATE') || {};
  const vol = parse('VOLFILL_STATE') || {};
  const aud = parse('AUDIT_STATE') || {};
  const audBudget = parse('AUDIT_READ_BUDGET') || {};

  return {
    proof: {
      mode: proof.mode || '', done: !!proof.done, current: proof.current || '',
      symbolsDone: (proof.symbolsDone || []).length,
      symbolsFailed: proof.symbolsFailed || [],
      symbolsPartial: proof.symbolsPartial || [],
      sessionsSaved: proof.sessionsSaved || 0,
      lastError: proof.lastError || null,
    },
    history: {
      done: !!hist.done, cursor: hist.cursor || hist.date || '',
      daysDone: hist.daysDone || 0, lastError: hist.lastError || null,
    },
    volumeBackfill: {
      done: !!vol.done, index: vol.idx || 0,
      total: (vol.symbols || []).length,
      current: (vol.symbols || [])[vol.idx || 0] || '',
      cursor: vol.cursor || '', written: vol.written || 0,
      spentToday: vol.spent || 0, spentDay: vol.spentDay || '',
    },
    // Pełny audyt idzie symbol po symbolu co minutę i kończy się dopiero po
    // ostatnim (wtedy ustawia audit.fullAt). Bez tego bloku nie dało się odróżnić
    // „audyt trwa" od „audyt padł" — data fullAt przez cały przebieg pokazuje
    // poprzedni, ukończony audyt.
    fullAudit: {
      running: !!(aud.symbols && aud.symbols.length) && !aud.done,
      done: !!aud.done,
      index: aud.idx || 0,
      total: (aud.symbols || []).length,
      current: (aud.symbols || [])[aud.idx || 0] || '',
      startedAt: aud.startedAt || '',
      lastError: aud.error || null,
      readsSpentToday: audBudget.used || 0,
      readsBudget: (typeof AUDIT_READ_BUDGET === 'object') ? AUDIT_READ_BUDGET.DAILY_MAX : null,
    },
    triggers: ScriptApp.getProjectTriggers().map(t => t.getHandlerFunction()),
  };
}

function telemetryLog_(ss) {
  const sh = ss.getSheetByName(CONFIG.STATS_SHEET);
  if (!sh) return [];
  try {
    const first = logFirstRow_();
    const n = Math.min(TELEMETRY.MAX_LOG, Math.max(0, sh.getLastRow() - first));
    if (n <= 0) return [];
    return sh.getRange(first, 1, n, 4).getValues()
      .filter(r => r[0])
      .map(r => ({ at: String(r[0]), level: String(r[1]), source: String(r[2]), message: String(r[3]) }));
  } catch (e) {
    return [{ at: '', level: 'BŁĄD', source: 'TELEMETRIA', message: 'nie udało się odczytać dziennika: ' + e.message }];
  }
}


// ============================================================================
//  GITHUB (Contents API)
// ============================================================================
function telemetryGithubGet_(path) {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) return { ok: false, status: 0, sha: null };
  const url = `https://api.github.com/repos/${TELEMETRY.REPO}/contents/${path}?ref=${TELEMETRY.BRANCH}`;
  const resp = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
  });
  const code = resp.getResponseCode();
  if (code === 200) {
    const j = JSON.parse(resp.getContentText());
    return { ok: true, status: code, sha: j.sha };
  }
  return { ok: false, status: code, sha: null };
}

function telemetryGithubPut_(path, content, message) {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('brak tokenu GitHub');

  const existing = telemetryGithubGet_(path);
  const payload = {
    message: message,
    content: Utilities.base64Encode(content, Utilities.Charset.UTF_8),
    branch: TELEMETRY.BRANCH,
  };
  if (existing.sha) payload.sha = existing.sha;   // nadpisanie wymaga sha

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
  return true;
}
