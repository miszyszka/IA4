"""
IA 4 — kalendarz świec akcji NYSE dla feedu AI Investor (instrukcja, sekcje 4 i 11c.4).
Wersja projektu: 1.42 (2026-10-15) — musi zgadzać się z IA4_INSTRUKCJA.md

Sesja 9:30–16:00 czasu Nowego Jorku: świece 1–6 zamykają się o pełnej godzinie + 30 min (10:30 … 15:30),
świeca 7 o 16:00. Sesja skrócona (13:00): 4 świece, ostatnia o 13:00. Święta i sesje skrócone — listy
z ia4/lab/check.py (te same co US_MARKET_HOLIDAYS w Code.gs). Data świecy = data sesji w Nowym Jorku.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..lab.check import US_HALF_DAYS, US_MARKET_HOLIDAYS

NY = ZoneInfo("America/New_York")
PL = ZoneInfo("Europe/Warsaw")


def closes(d: date) -> list[tuple[int, float]]:
    """[(nr świecy, zamknięcie w s UTC)] sesji w dniu d; pusta lista — brak sesji."""
    s = d.isoformat()
    if d.weekday() >= 5 or s in US_MARKET_HOLIDAYS:
        return []
    mins = [630, 690, 750, 780] if s in US_HALF_DAYS else [630, 690, 750, 810, 870, 930, 960]
    base = datetime(d.year, d.month, d.day, tzinfo=NY)
    return [(i + 1, (base + timedelta(minutes=m)).timestamp()) for i, m in enumerate(mins)]


def key(d: str, slot: int) -> int:
    """Klucz świecy RRRRMMDDn (jak w telemetrii)."""
    return int(d.replace("-", "")) * 10 + int(slot)


def label(k: int) -> str:
    s = str(k)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]} #{s[8]}"


def _ny_date(ts: float) -> date:
    return datetime.fromtimestamp(ts, timezone.utc).astimezone(NY).date()


def last_closed(now: float, lag: float = 0.0) -> dict | None:
    """Najnowsza świeca, której zamknięcie + lag ≤ now: {date, slot, key, close}."""
    t = now - lag
    d = _ny_date(t)
    for _ in range(15):
        for slot, c in reversed(closes(d)):
            if c <= t:
                return {"date": d.isoformat(), "slot": slot, "key": key(d.isoformat(), slot), "close": c}
        d -= timedelta(days=1)
    return None


def next_close(now: float) -> dict | None:
    """Najbliższe zamknięcie świecy po chwili now."""
    d = _ny_date(now)
    for _ in range(15):
        for slot, c in closes(d):
            if c > now:
                return {"date": d.isoformat(), "slot": slot, "key": key(d.isoformat(), slot), "close": c}
        d += timedelta(days=1)
    return None


def session_last_close(d: str) -> float | None:
    c = closes(date.fromisoformat(d))
    return c[-1][1] if c else None


def is_open(now: float) -> bool:
    c = closes(_ny_date(now))
    return bool(c) and c[0][1] - 3600 <= now < c[-1][1]
