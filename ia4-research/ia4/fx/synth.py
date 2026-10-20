"""
IA 4 — syntetyczne świece 1h do testów modułu FX (bez Firestore): pary walutowe w godzinach
rynku i BTC 24/7, zmienność zależna od pory dnia, okresy trendu, braki uśrednione.
Wersja projektu: 1.50 (2026-10-20) — musi zgadzać się z IA4_INSTRUKCJA.md
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import instruments as fi

SPEC = {                    # cena startowa, zmienność godzinowa (ułamek ceny)
    "EURUSD": (1.10, 0.0011),
    "USDJPY": (150.0, 0.0013),
    "GBPUSD": (1.30, 0.0012),
    "AUDUSD": (0.66, 0.0014),
    "USDCAD": (1.37, 0.0009),
    "USDCHF": (0.88, 0.0011),
    "NZDUSD": (0.60, 0.0014),
    "EURJPY": (162.0, 0.0014),
    "GBPJPY": (192.0, 0.0016),
    "EURGBP": (0.85, 0.0008),
    "BTCUSD": (60000.0, 0.006),
}


def synthetic(sym: str = "EURUSD", days: int = 420, seed: int = 7, trend: float = 0.15,
              end: str = "2026-10-09T20:00:00Z") -> pd.DataFrame:
    """trend — siła okresów trendu w jednostkach zmienności godzinowej (0 = czysty szum)."""
    group = fi.group_of(sym)
    p0, vol0 = SPEC.get(sym, (1.0, 0.001))
    rng = np.random.default_rng(seed + 1000 * fi.IDS.index(sym) if sym in fi.IDS else seed)
    t_end = int(datetime.fromisoformat(end.replace("Z", "+00:00")).timestamp())
    grid = t_end - 3600 * np.arange(days * 24)[::-1]
    t = grid[fi.market_open(group, grid)]
    n = t.size
    hour = (t // 3600) % 24
    season = 0.6 + 0.9 * np.exp(-((hour - 14) / 3.5) ** 2) + 0.3 * np.exp(-((hour - 8) / 2.0) ** 2)
    vol = np.empty(n)
    v = 1.0
    for i in range(n):
        v = 0.97 * v + 0.03 + 0.10 * abs(rng.standard_normal()) - 0.08
        vol[i] = max(v, 0.3)
    drift = np.repeat(rng.normal(0, trend, n // 150 + 1), 150)[:n]
    step = (drift + rng.standard_t(5, n) * 0.75) * season * vol * vol0
    logc = np.log(p0) + np.cumsum(step)
    c = np.exp(logc)
    o = np.concatenate([[c[0] / np.exp(step[0])], c[:-1]])
    wig = np.abs(rng.normal(0, 0.5, (2, n))) * season * vol * vol0 * c
    h = np.maximum(o, c) + wig[0]
    l = np.minimum(o, c) - wig[1]
    filled = rng.random(n) < 0.003
    dp = fi.INFO.get(sym, {"digits": 6})["digits"]
    r = lambda x: np.round(x, dp)
    return pd.DataFrame({"time": t.astype(np.int64), "o": r(o), "h": r(h), "l": r(l), "c": r(c), "filled": filled})


def planted(sym: str = "EURUSD", seed: int = 5, thr: float = 2.0, drift: float = 0.35, span: int = 12,
            days: int = 420) -> pd.DataFrame:
    """Czysty szum + zasiany sygnał: po ruchu > thr zmienności godzinowych w 6 świecach cena dryfuje
    o drift zmienności na świecę w tę samą stronę przez span świec (lustrzanie dla spadku)."""
    df = synthetic(sym, days=days, seed=seed, trend=0.0)
    c = df["c"].to_numpy()
    lc = np.log(c)
    step = np.diff(lc, prepend=lc[0])
    s = np.nanstd(step[1:])
    add = np.zeros(c.size)
    out = lc.copy()
    for i in range(1, c.size):
        out[i] = out[i - 1] + step[i] + add[i]
        if i >= 6:
            ch = (out[i] - out[i - 6]) / s
            if abs(ch) > thr:
                add[i + 1: i + 1 + span] = np.sign(ch) * drift * s
    k = np.exp(out - lc)
    df["c"] = df["c"] * k
    df["o"] = df["o"] * np.concatenate([[1.0], k[:-1]])
    df["h"] = np.maximum(df["h"] * k, np.maximum(df["o"], df["c"]))
    df["l"] = np.minimum(df["l"] * k, np.minimum(df["o"], df["c"]))
    return df


def universe(kind: str = "noise", syms=("EURUSD", "USDJPY", "BTCUSD"), days: int = 420, seed: int = 7) -> dict:
    """Kilka instrumentów naraz: noise (szum + trendy), pure (czysty szum), planted (zasiany sygnał)."""
    out = {}
    for j, s in enumerate(syms):
        if kind == "planted":
            out[s] = planted(s, seed=seed + j, days=days)
        else:
            out[s] = synthetic(s, days=days, seed=seed + j, trend=0.0 if kind == "pure" else 0.15)
    return out
