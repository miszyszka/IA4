"""
IA 4 — kalendarz sesji NYSE (Etap 1b, kontrakt silnika pkt 13).
Wersja projektu: 0.37 (2026-09-28) — musi zgadzać się z IA4_INSTRUKCJA.md

Kopia dwóch list z Apps Script, bez których silnik nie rozpozna dziury w danych
(D27): świąt (`US_MARKET_HOLIDAYS` w `History.gs`) i sesji skróconych
(`EARLY_CLOSE_DAYS` w `Project.gs`). To są TE SAME listy co w Apps Script —
test `tests/test_nyse.py` czyta oba pliki .gs i pilnuje, żeby się nie
rozjechały (ten sam typ ryzyka co L12). Listy kończą się na 2026 (L9):
uzupełniać wszystkie trzy miejsca na początku każdego roku.

Nazwa `nyse`, nie `calendar`, żeby nie przesłaniać modułu standardowego.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

HOLIDAYS = {
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27", "2024-06-19",
    "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
    "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19",
    "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
}

EARLY_CLOSE = {
    "2024-07-03", "2024-11-29", "2024-12-24",
    "2025-07-03", "2025-11-28", "2025-12-24",
    "2026-11-27", "2026-12-24",
}

FIRST_DAY = "2024-01-01"
LAST_DAY = "2026-12-31"      # L9: kalendarz kończy się na 2026
BARS_FULL = 7                # 9:30–16:00 ET: 6 świec 1h + świeca 7 (30 min)
BARS_EARLY = 4               # 9:30–13:00 ET: 3 świece 1h + świeca 4 (30 min)


@lru_cache(maxsize=1)
def trading_days() -> tuple[str, ...]:
    """Wszystkie dni sesyjne z zakresu kalendarza, rosnąco."""
    d, end = date.fromisoformat(FIRST_DAY), date.fromisoformat(LAST_DAY)
    out = []
    while d <= end:
        s = d.isoformat()
        if d.weekday() < 5 and s not in HOLIDAYS:
            out.append(s)
        d += timedelta(days=1)
    return tuple(out)


@lru_cache(maxsize=1)
def _ordinal() -> dict[str, int]:
    return {d: i for i, d in enumerate(trading_days())}


def ordinal(day: str) -> int:
    """Numer dnia sesyjnego. Dzień spoza kalendarza albo bez sesji = twardy błąd."""
    try:
        return _ordinal()[day]
    except KeyError:
        if not (FIRST_DAY <= day <= LAST_DAY):
            raise ValueError(f"{day} poza kalendarzem {FIRST_DAY}–{LAST_DAY} — uzupełnij listy (L9)") from None
        raise ValueError(f"{day} nie jest dniem sesyjnym NYSE, a są dla niego świece") from None


def is_trading_day(day: str) -> bool:
    return day in _ordinal()


def expected_bars(day: str) -> int:
    """Ile świec 1h ma pełna sesja tego dnia (7, a w sesji skróconej 4)."""
    return BARS_EARLY if day in EARLY_CLOSE else BARS_FULL


def next_trading_day(day: str) -> str | None:
    i = ordinal(day) + 1
    days = trading_days()
    return days[i] if i < len(days) else None


def is_last_of_month(day: str) -> bool:
    """Ostatnia sesja miesiąca — kalendarz znany z góry, więc bez zaglądania w przyszłość."""
    n = next_trading_day(day)
    return n is None or n[:7] != day[:7]


def is_last_of_week(day: str) -> bool:
    """Ostatnia sesja tygodnia (ISO): następna sesja wypada w innym tygodniu."""
    n = next_trading_day(day)
    if n is None:
        return True
    return date.fromisoformat(n).isocalendar()[:2] != date.fromisoformat(day).isocalendar()[:2]
