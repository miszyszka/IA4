"""
IA 4 — kontrola kompletności kopii lokalnej (instrukcja, sekcja 7).
Wersja projektu: 1.21 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

Porównuje każdy instrument z kalendarzem NYSE: czy są wszystkie dni sesyjne
od pierwszej daty instrumentu i czy każda sesja ma komplet świec (7, a w dni
skrócone 4). Niczego nie łata — braki uzupełnia automat w Apps Script
(nocne odświeżenie, „Uzupełnij ostatni miesiąc”). Wynik trafia do logu.

Listy świąt i sesji skróconych trzeba uzupełniać co roku w grudniu, razem
z US_MARKET_HOLIDAYS w Code.gs.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

US_MARKET_HOLIDAYS = {
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
    "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27",
    "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
}
# Sesje skrócone do 13:00 ET — 4 świece.
US_HALF_DAYS = {
    "2024-07-03", "2024-11-29", "2024-12-24",
    "2025-07-03", "2025-11-28", "2025-12-24",
    "2026-11-27", "2026-12-24",
}


def trading_days(first: str, last: str) -> list[str]:
    d0, d1 = date.fromisoformat(first), date.fromisoformat(last)
    out = []
    d = d0
    while d <= d1:
        s = d.isoformat()
        if d.weekday() < 5 and s not in US_MARKET_HOLIDAYS:
            out.append(s)
        d += timedelta(days=1)
    return out


def last_closed_session(now: datetime | None = None) -> str:
    """Ostatni dzień sesyjny, którego sesja jest już zamknięta i odświeżona w nocy (≈ 17:00 ET)."""
    now = now or datetime.now(timezone.utc)
    et = now - timedelta(hours=4)          # przybliżenie ET (EDT); różnica 1 h nie ma tu znaczenia
    d = et.date() if et.hour >= 17 else et.date() - timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in US_MARKET_HOLIDAYS:
        d -= timedelta(days=1)
    return d.isoformat()


def check(data_dir: Path, symbols: list[str]) -> dict:
    expected_last = last_closed_session()
    items = {}
    total = {"instruments": 0, "candles": 0, "missing_sessions": 0, "incomplete_sessions": 0,
             "stale": 0, "zero_volume": 0}
    for s in symbols:
        p = data_dir / f"{s.lstrip('^')}.parquet"
        if not p.exists():
            items[s] = {"error": "brak pliku"}
            total["stale"] += 1
            continue
        df = pd.read_parquet(p, columns=["date", "slot", "v"])
        per = df.groupby("date")["slot"].count()
        first, last = str(per.index.min()), str(per.index.max())
        days = trading_days(first, max(last, expected_last))
        have = set(per.index.astype(str))
        missing = [d for d in days if d not in have]
        incomplete = [d for d, n in per.items() if n < (4 if d in US_HALF_DAYS else 7)]
        zero_v = int((df["v"] <= 0).sum())
        items[s] = {"candles": int(len(df)), "first": first, "last": last,
                    "missing": missing[-10:], "missing_n": len(missing),
                    "incomplete": [str(d) for d in incomplete][-10:], "incomplete_n": len(incomplete),
                    "zero_volume": zero_v}
        total["instruments"] += 1
        total["candles"] += int(len(df))
        total["missing_sessions"] += len(missing)
        total["incomplete_sessions"] += len(incomplete)
        total["zero_volume"] += zero_v
        if last < expected_last:
            total["stale"] += 1
    total["expected_last"] = expected_last
    total["ok"] = total["missing_sessions"] == 0 and total["incomplete_sessions"] == 0 and total["stale"] == 0
    return {"summary": total, "items": items}


def describe(rep: dict) -> str:
    t = rep["summary"]
    n = f"{t['candles']:,}".replace(",", " ")
    if t["ok"]:
        return f"Baza kompletna: {t['instruments']} instrumentów, {n} świec, do {t['expected_last']}."
    return (f"Baza: {n} świec; brakujących sesji {t['missing_sessions']}, "
            f"niepełnych {t['incomplete_sessions']}, nieaktualnych instrumentów {t['stale']} "
            f"(oczekiwana ostatnia sesja {t['expected_last']}).")
