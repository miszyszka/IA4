"""
IA 4 — instrumenty modułu FX 1h (instrukcja, sekcja 4b) i godziny rynku.
Wersja projektu: 1.34 (2026-10-12) — musi zgadzać się z IA4_INSTRUKCJA.md

Kopia listy z Fx.gs (FX.INSTRUMENTS) — używana, gdy Firestore (system/fx1h) jest
niedostępny, i do opisu instrumentów (pip, miejsca po przecinku, grupa).
Zmiana listy = zmiana instrukcji i obu plików naraz.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

STEP = 3600                                   # świeca 1 h

INSTRUMENTS = (
    # id,      Yahoo,      grupa,    pip,    miejsc
    ("EURUSD", "EURUSD=X", "fx", 0.0001, 6),
    ("USDJPY", "JPY=X", "fx", 0.01, 4),
    ("GBPUSD", "GBPUSD=X", "fx", 0.0001, 6),
    ("AUDUSD", "AUDUSD=X", "fx", 0.0001, 6),
    ("USDCAD", "CAD=X", "fx", 0.0001, 6),
    ("USDCHF", "CHF=X", "fx", 0.0001, 6),
    ("NZDUSD", "NZDUSD=X", "fx", 0.0001, 6),
    ("EURJPY", "EURJPY=X", "fx", 0.01, 4),
    ("GBPJPY", "GBPJPY=X", "fx", 0.01, 4),
    ("EURGBP", "EURGBP=X", "fx", 0.0001, 6),
    ("BTCUSD", "BTC-USD", "crypto", 1.0, 2),
)
IDS = tuple(i[0] for i in INSTRUMENTS)
INFO = {i[0]: {"id": i[0], "yahoo": i[1], "group": i[2], "pip": i[3], "digits": i[4]} for i in INSTRUMENTS}
NAMES = {"EURUSD": "EUR/USD", "USDJPY": "USD/JPY", "GBPUSD": "GBP/USD", "AUDUSD": "AUD/USD", "USDCAD": "USD/CAD",
         "USDCHF": "USD/CHF", "NZDUSD": "NZD/USD", "EURJPY": "EUR/JPY", "GBPJPY": "GBP/JPY", "EURGBP": "EUR/GBP",
         "BTCUSD": "Bitcoin (BTC/USD)"}


def group_of(sym: str) -> str:
    return INFO.get(sym, {"group": "fx"})["group"]


def market_open(group: str, t) -> np.ndarray:
    """Czy świeca 1 h o początku t (sekundy UTC, skalar albo tablica) wypada w godzinach rynku:
    pary walutowe — niedziela 17:00 do piątku 17:00 czasu Nowego Jorku; crypto — zawsze."""
    t = np.atleast_1d(np.asarray(t, dtype=np.int64))
    if group == "crypto":
        return np.ones(t.size, dtype=bool)
    ny = pd.to_datetime(t, unit="s", utc=True).tz_convert("America/New_York")
    wd = np.asarray(ny.dayofweek)                     # 0 = pon … 6 = nd
    m = np.asarray(ny.hour) * 60 + np.asarray(ny.minute)
    return ~((wd == 5) | ((wd == 6) & (m < 17 * 60)) | ((wd == 4) & (m >= 17 * 60)))


def next_slots(group: str, t_last: int, n: int) -> list[int]:
    """Początki n kolejnych świec w godzinach rynku po świecy t_last."""
    grid = t_last + STEP * np.arange(1, 24 * 4 + n * 2)
    ok = grid[market_open(group, grid)]
    return [int(x) for x in ok[:n]]
