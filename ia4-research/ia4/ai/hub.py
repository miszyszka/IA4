"""
IA 4 — hub: wspólna pamięć agentów AI Investor (instrukcja, sekcja 11c.5).
Wersja projektu: 1.34 (2026-10-12) — musi zgadzać się z IA4_INSTRUKCJA.md

Jeden plik SQLite (tryb WAL) w data/ai/hub.sqlite, poza gitem. Tabele powstają w kroku, który ich
używa (AI-1: meta, runs, events, notes, feed_log; AI-2: positions, rounds, decisions, llm_calls,
equity, playbook, lessons); kolejne kroki dopisują swoje (`meta.schema`). Czas zawsze w sekundach
UTC (REAL). Każdy wątek ma własne połączenie (nadzorca i agent).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .. import config

PATH = config.CACHE_DIR / "ai" / "hub.sqlite"
SCHEMA = 2

DDL = [
    """CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)""",
    """CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, started_at REAL NOT NULL, stopped_at REAL,
         host TEXT, version TEXT, step TEXT, args TEXT)""",
    """CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL,
         agent TEXT NOT NULL DEFAULT 'system', text TEXT NOT NULL, data TEXT)""",
    """CREATE INDEX IF NOT EXISTS events_at ON events(at)""",
    """CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, at REAL NOT NULL, agent TEXT NOT NULL,
         kind TEXT NOT NULL, text TEXT NOT NULL, refs TEXT)""",
    # spływ świec: jedna linia na świecę akcji (cała fala 53 + SPY/QQQ) i na godzinę FX (11 instrumentów)
    """CREATE TABLE IF NOT EXISTS feed_log (kind TEXT NOT NULL, candle TEXT NOT NULL, close_at REAL NOT NULL,
         firestore_at REAL, local_at REAL, have INTEGER, need INTEGER, missing TEXT, PRIMARY KEY (kind, candle))""",
    # --- AI-2: Agent-Investor
    """CREATE TABLE IF NOT EXISTS positions (id INTEGER NOT NULL, book TEXT NOT NULL, status TEXT NOT NULL, inst TEXT,
         round_id TEXT, data TEXT NOT NULL, updated REAL, PRIMARY KEY (book, id))""",
    """CREATE TABLE IF NOT EXISTS rounds (id TEXT PRIMARY KEY, at REAL NOT NULL, kind TEXT, candle TEXT, data TEXT)""",
    """CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, round_id TEXT, at REAL, ref TEXT, inst TEXT,
         side INTEGER, basis TEXT, action TEXT, confidence INTEGER, note TEXT, outcome TEXT, pos_id INTEGER)""",
    """CREATE TABLE IF NOT EXISTS llm_calls (id INTEGER PRIMARY KEY, at REAL, agent TEXT, model TEXT, ok INTEGER, err TEXT,
         sec REAL, prompt_tokens INTEGER, eval_tokens INTEGER, prompt_sha TEXT, prompt TEXT, response TEXT)""",
    """CREATE TABLE IF NOT EXISTS equity (at REAL, round_id TEXT, equity REAL, realized REAL, unrealized REAL, gross REAL,
         risk REAL, positions INTEGER, dial REAL, dd REAL)""",
    """CREATE TABLE IF NOT EXISTS playbook (id TEXT PRIMARY KEY, status TEXT, basis_kind TEXT, updated REAL, data TEXT)""",
    """CREATE TABLE IF NOT EXISTS lessons (id INTEGER PRIMARY KEY, at REAL, author TEXT, text TEXT, active INTEGER DEFAULT 1)""",
]


class Hub:
    def __init__(self, path: Path = PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(str(path), timeout=10, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        for q in DDL:
            self.db.execute(q)
        if (self.meta("schema") or 0) < SCHEMA:
            self.set_meta("schema", SCHEMA)

    # ------------------------------------------------------------ meta
    def meta(self, key: str, default=None):
        r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return default if r is None else json.loads(r["value"])

    def set_meta(self, key: str, value) -> None:
        self.db.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, json.dumps(value)))

    # ------------------------------------------------------------ uruchomienia
    def run_start(self, host: str, version: str, step: str, args: str, at: float | None = None) -> int:
        cur = self.db.execute("INSERT INTO runs(started_at, host, version, step, args) VALUES(?,?,?,?,?)",
                              (at or time.time(), host, version, step, args))
        return int(cur.lastrowid)

    def run_stop(self, run_id: int, at: float | None = None) -> None:
        self.db.execute("UPDATE runs SET stopped_at=? WHERE id=?", (at or time.time(), run_id))

    def runs(self, limit: int = 10) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))]

    # ------------------------------------------------------------ zdarzenia i notatki
    def event(self, kind: str, text: str, agent: str = "system", data=None, at: float | None = None) -> int:
        cur = self.db.execute("INSERT INTO events(at, kind, agent, text, data) VALUES(?,?,?,?,?)",
                              (at or time.time(), kind, agent, text, None if data is None else json.dumps(data, ensure_ascii=False)))
        return int(cur.lastrowid)

    def events(self, limit: int = 30) -> list[dict]:
        rows = self.db.execute("SELECT at, kind, agent, text FROM events ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def note(self, agent: str, kind: str, text: str, refs=None, at: float | None = None) -> int:
        cur = self.db.execute("INSERT INTO notes(at, agent, kind, text, refs) VALUES(?,?,?,?,?)",
                              (at or time.time(), agent, kind, text, None if refs is None else json.dumps(refs)))
        return int(cur.lastrowid)

    # ------------------------------------------------------------ spływ świec
    def feed(self, kind: str, candle: str, close_at: float, firestore_at: float | None, local_at: float | None,
             have: int, need: int, missing: list[str]) -> None:
        """Zapis albo uzupełnienie wiersza świecy (późniejsze instrumenty uzupełniają ten sam wiersz)."""
        self.db.execute(
            "INSERT INTO feed_log(kind, candle, close_at, firestore_at, local_at, have, need, missing) VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(kind, candle) DO UPDATE SET firestore_at=excluded.firestore_at, local_at=excluded.local_at, "
            "have=excluded.have, need=excluded.need, missing=excluded.missing",
            (kind, candle, close_at, firestore_at, local_at, have, need, json.dumps(missing)))

    def feed_recent(self, kind: str, limit: int) -> list[dict]:
        rows = self.db.execute("SELECT * FROM feed_log WHERE kind=? ORDER BY close_at DESC LIMIT ?", (kind, limit))
        out = []
        for r in rows:
            d = dict(r)
            d["missing"] = json.loads(d["missing"] or "[]")
            out.append(d)
        return out

    # ------------------------------------------------------------ AI-2: pozycje, rundy, decyzje
    def save_positions(self, positions) -> None:
        now = time.time()
        with self.db:
            for p in positions:
                self.db.execute("INSERT INTO positions(id, book, status, inst, round_id, data, updated) VALUES(?,?,?,?,?,?,?) "
                                "ON CONFLICT(book, id) DO UPDATE SET status=excluded.status, data=excluded.data, updated=excluded.updated",
                                (p.id, p.book, p.status, p.inst, p.round_id, json.dumps(p.to_dict(), ensure_ascii=False), now))

    def load_positions(self, book: str) -> list[dict]:
        return [json.loads(r["data"]) for r in self.db.execute("SELECT data FROM positions WHERE book=? ORDER BY id", (book,))]

    def round_save(self, rid: str, at: float, kind: str, candle: str, data: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO rounds(id, at, kind, candle, data) VALUES(?,?,?,?,?)",
                        (rid, at, kind, candle, json.dumps(data, ensure_ascii=False)))

    def rounds(self, limit: int = 1000) -> list[dict]:
        rows = self.db.execute("SELECT data FROM rounds ORDER BY at DESC LIMIT ?", (limit,))
        return [json.loads(r["data"]) for r in rows]

    def decision(self, **d) -> None:
        self.db.execute("INSERT INTO decisions(round_id, at, ref, inst, side, basis, action, confidence, note, outcome, pos_id) "
                        "VALUES(:round_id,:at,:ref,:inst,:side,:basis,:action,:confidence,:note,:outcome,:pos_id)", d)

    def decisions(self, limit: int = 5000) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,))]

    def llm_call(self, agent, model, ok, err, sec, prompt_tokens, eval_tokens, prompt, response) -> None:
        import hashlib
        self.db.execute("INSERT INTO llm_calls(at, agent, model, ok, err, sec, prompt_tokens, eval_tokens, prompt_sha, prompt, response) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (time.time(), agent, model, int(bool(ok)), err, sec, prompt_tokens, eval_tokens,
                                                          hashlib.sha1(prompt.encode("utf-8")).hexdigest(), prompt, response))

    def equity_point(self, at, rid, s: dict, dial: float, dd: float) -> None:
        self.db.execute("INSERT INTO equity(at, round_id, equity, realized, unrealized, gross, risk, positions, dial, dd) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?)", (at, rid, s["equity"], s["realized"], s["unrealized"], s["gross"], s["risk"],
                                                        s["positions"], dial, dd))

    def equity_series(self, limit: int = 20000) -> list[dict]:
        rows = self.db.execute("SELECT * FROM (SELECT * FROM equity ORDER BY at DESC LIMIT ?) ORDER BY at", (limit,))
        return [dict(r) for r in rows]

    def notes(self, limit: int = 30, agent: str | None = None) -> list[dict]:
        q, a = "SELECT at, agent, kind, text, refs FROM notes", ()
        if agent:
            q, a = q + " WHERE agent=?", (agent,)
        return [dict(r) for r in self.db.execute(q + " ORDER BY id DESC LIMIT ?", a + (limit,))]

    def playbook_save(self, strategies: list[dict]) -> None:
        now = time.time()
        with self.db:
            for s in strategies:
                self.db.execute("INSERT INTO playbook(id, status, basis_kind, updated, data) VALUES(?,?,?,?,?) "
                                "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated=excluded.updated",
                                (s["id"], s["status"], s["basis_kind"], now, json.dumps(s, ensure_ascii=False)))

    def playbook_set_status(self, sid: str, status: str, basis_kind: str) -> None:
        self.db.execute("UPDATE playbook SET status=?, basis_kind=?, updated=? WHERE id=?", (status, basis_kind, time.time(), sid))

    def playbook_status(self) -> dict:
        return {r["id"]: (r["status"], r["basis_kind"]) for r in self.db.execute("SELECT id, status, basis_kind FROM playbook")}

    def lessons_active(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT id, at, author, text FROM lessons WHERE active=1 ORDER BY id")]

    def lesson_add(self, author: str, text: str, at: float | None = None) -> int:
        cur = self.db.execute("INSERT INTO lessons(at, author, text) VALUES(?,?,?)", (at or time.time(), author, text))
        return int(cur.lastrowid)

    def close(self) -> None:
        try:
            self.db.close()
        except sqlite3.Error:
            pass
