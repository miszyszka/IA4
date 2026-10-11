"""
IA 4 — hub: wspólna pamięć agentów AI Investor (instrukcja, sekcja 11c.5).
Wersja projektu: 1.33 (2026-10-11) — musi zgadzać się z IA4_INSTRUKCJA.md

Jeden plik SQLite (tryb WAL) w data/ai/hub.sqlite, poza gitem. Tabele powstają w kroku, który ich
używa (AI-1: meta, runs, events, notes, feed_log); kolejne kroki dopisują swoje przez migracje
(`meta.schema`). Czas zawsze w sekundach UTC (REAL).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .. import config

PATH = config.CACHE_DIR / "ai" / "hub.sqlite"
SCHEMA = 1

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
        if self.meta("schema") is None:
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

    def close(self) -> None:
        try:
            self.db.close()
        except sqlite3.Error:
            pass
