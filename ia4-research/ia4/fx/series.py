"""
IA 4 — seria EURUSD i wskaźniki modułu prognozy (instrukcja, sekcje 4c.1 i 4c.3).
Wersja projektu: 1.25 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

Seria = wszystkie świece w kolejności czasu, indeks t bez przerw (przez weekend też).
Średnie kroczące, ATR i RSI — dokładnie wzory z sekcji 8.2 (ia4.lab.indicators).
Pozostałe wskaźniki — wzory z tabeli 4c.3, tutaj.

LUSTRO (para okoliczności, 4c.2): ta sama funkcja liczona na serii odbitej
  o' = −o, c' = −c, h' = −l, l' = −h
Wszystkie wskaźniki modułu są różnicowe (pipsy albo jednostki ATR), więc odbicie
jest dokładne: SMA(−c) = −SMA(c), RSI(−c) = 100 − RSI(c), ATR bez zmian itd.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import numpy as np
from numba import njit

from ..lab import indicators as ind

PIP = 0.0001
GAP_SEC = 3600            # przerwa: odstęp między świecami > 60 min (4c.1)
WARMUP = 1000             # rozgrzewka wskaźników: pierwsze 1000 świec serii (4c.3)
U_PERIOD = 100            # jednostka zmienności U = ATR(100) Wildera (4c.3)
MA_KINDS = ("SMA", "EMA", "WMA", "HMA", "DEMA", "TEMA", "KAMA", "ZLEMA")
NY = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
#  Pomocnicze (numba) — wszystkie przyczynowe: wartość na t tylko ze świec ≤ t
# ---------------------------------------------------------------------------
@njit(cache=True)
def roll_max(x, n):
    out = np.full(x.size, np.nan)
    for i in range(n - 1, x.size):
        m = x[i]
        for k in range(i - n + 1, i):
            if x[k] > m:
                m = x[k]
        out[i] = m
    return out


@njit(cache=True)
def roll_min(x, n):
    out = np.full(x.size, np.nan)
    for i in range(n - 1, x.size):
        m = x[i]
        for k in range(i - n + 1, i):
            if x[k] < m:
                m = x[k]
        out[i] = m
    return out


@njit(cache=True)
def roll_sum(x, n):
    """Suma n ostatnich wartości; NaN w oknie → NaN."""
    out = np.full(x.size, np.nan)
    for i in range(n - 1, x.size):
        s = 0.0
        ok = True
        for k in range(i - n + 1, i + 1):
            if not np.isfinite(x[k]):
                ok = False
                break
            s += x[k]
        if ok:
            out[i] = s
    return out


@njit(cache=True)
def roll_std(x, n):
    """Odchylenie standardowe populacji z n ostatnich wartości."""
    out = np.full(x.size, np.nan)
    for i in range(n - 1, x.size):
        s = 0.0
        for k in range(i - n + 1, i + 1):
            s += x[k]
        mu = s / n
        v = 0.0
        for k in range(i - n + 1, i + 1):
            v += (x[k] - mu) ** 2
        out[i] = np.sqrt(v / n)
    return out


@njit(cache=True)
def bars_since(ev):
    """Ile świec od ostatniego zdarzenia (0 = na tej świecy); NaN, gdy jeszcze nie było."""
    out = np.full(ev.size, np.nan)
    last = -1
    for i in range(ev.size):
        if ev[i]:
            last = i
        if last >= 0:
            out[i] = i - last
    return out


@njit(cache=True)
def streak(cond):
    """Długość bieżącej serii prawdziwych wartości kończącej się na t."""
    out = np.zeros(cond.size)
    run = 0
    for i in range(cond.size):
        run = run + 1 if cond[i] else 0
        out[i] = run
    return out


@njit(cache=True)
def run_pair(d):
    """Dla serii d: znak bieżącej serii zmian (+1 rośnie, −1 maleje, 0 brak), jej długość
    i długość poprzedniej serii (o znaku przeciwnym). Zmiana 0 albo NaN przerywa serie."""
    n = d.size
    sgn = np.zeros(n)
    cur = np.zeros(n)
    prev = np.zeros(n)
    s, c, p = 0, 0, 0
    for i in range(1, n):
        if not (np.isfinite(d[i]) and np.isfinite(d[i - 1])):
            s, c, p = 0, 0, 0
        else:
            x = d[i] - d[i - 1]
            ns = 1 if x > 0 else (-1 if x < 0 else 0)
            if ns == 0:
                s, c, p = 0, 0, 0
            elif ns == s:
                c += 1
            else:
                p = c if s == -ns else 0
                s, c = ns, 1
        sgn[i] = s
        cur[i] = c
        prev[i] = p
    return sgn, cur, prev


@njit(cache=True)
def anchor_ffill(start, x):
    """Wartość x z ostatniej świecy, na której start == True (np. otwarcie dnia)."""
    out = np.full(x.size, np.nan)
    v = np.nan
    for i in range(x.size):
        if start[i]:
            v = x[i]
        out[i] = v
    return out


@njit(cache=True)
def seg_cummax(start, x):
    out = np.empty(x.size)
    m = -np.inf
    for i in range(x.size):
        if start[i] or i == 0:
            m = -np.inf
        if x[i] > m:
            m = x[i]
        out[i] = m
    return out


@njit(cache=True)
def seg_cummin(start, x):
    out = np.empty(x.size)
    m = np.inf
    for i in range(x.size):
        if start[i] or i == 0:
            m = np.inf
        if x[i] < m:
            m = x[i]
        out[i] = m
    return out


@njit(cache=True)
def prev_seg_last(start, x):
    """Ostatnia wartość x poprzedniego segmentu (np. zamknięcie poprzedniej doby)."""
    out = np.full(x.size, np.nan)
    pv = np.nan
    for i in range(x.size):
        if start[i] and i > 0:
            pv = x[i - 1]
        out[i] = pv
    return out


@njit(cache=True)
def prev_seg_extreme(start, x, is_max):
    """Maksimum (is_max) albo minimum x w poprzednim segmencie."""
    out = np.full(x.size, np.nan)
    cur = np.nan
    pv = np.nan
    for i in range(x.size):
        if start[i] and i > 0:
            pv = cur
            cur = np.nan
        v = x[i]
        if np.isnan(cur) or (is_max and v > cur) or ((not is_max) and v < cur):
            cur = v
        out[i] = pv
    return out


def shift(x: np.ndarray, k: int) -> np.ndarray:
    """x[t − k] (NaN na początku)."""
    out = np.full(x.size, np.nan)
    if k < x.size:
        out[k:] = x[: x.size - k]
    return out


# ---------------------------------------------------------------------------
#  Seria
# ---------------------------------------------------------------------------
class Series:
    """Jedna strona serii: zwykła (side=+1) albo odbita (side=−1). Wskaźniki w pamięci."""

    def __init__(self, time, o, h, l, c, filled, side: int = 1):
        self.side = side
        self.time = np.asarray(time, dtype=np.int64)
        o, h, l, c = (np.asarray(a, dtype=np.float64) for a in (o, h, l, c))
        if side == 1:
            self.o, self.h, self.l, self.c = o, h, l, c
        else:
            self.o, self.h, self.l, self.c = -o, -l, -h, -c
        self.filled = np.asarray(filled, dtype=bool)
        self.n = self.c.size
        self._cache: dict = {}

    def cached(self, key, fn):
        v = self._cache.get(key)
        if v is None:
            v = fn()
            self._cache[key] = v
        return v

    # --- podstawowe
    @property
    def U(self):
        return self.cached(("U",), lambda: ind.atr(self.h, self.l, self.c, U_PERIOD))

    def ma(self, kind, n):
        return self.cached(("ma", kind, n), lambda: ind.moving_average(kind, n, self.c, self.c * 0))

    def rsi(self, n):
        return self.cached(("rsi", n), lambda: ind.rsi(self.c, n))

    def hh(self, n):
        return self.cached(("hh", n), lambda: roll_max(self.h, n))

    def ll(self, n):
        return self.cached(("ll", n), lambda: roll_min(self.l, n))

    def std(self, n):
        return self.cached(("std", n), lambda: roll_std(self.c, n))

    # --- czas (te same na obu stronach)
    def starts(self, anchor: str) -> np.ndarray:
        """Pierwsza świeca segmentu: utc_day (doba UTC), ny_day (doba handlowa od 17:00
        Nowy Jork), week (pierwsza świeca po przerwie > 60 min)."""
        def build():
            t = self.time
            st = np.zeros(t.size, dtype=bool)
            if t.size:
                st[0] = True
            if anchor == "week":
                st[1:] |= np.diff(t) > GAP_SEC
            else:
                did = day_ids(tuple(t.tolist()), anchor)
                st[1:] |= did[1:] != did[:-1]
            return st
        return self.cached(("starts", anchor), build)


@lru_cache(maxsize=8)
def day_ids(times: tuple, anchor: str) -> np.ndarray:
    t = np.asarray(times, dtype=np.int64)
    if anchor == "utc_day":
        return t // 86400
    if anchor == "ny_day":                    # doba handlowa: 17:00 NY → następny dzień
        out = np.empty(t.size, dtype=np.int64)
        for i, x in enumerate(t.tolist()):
            dt = datetime.fromtimestamp(x, timezone.utc).astimezone(NY)
            out[i] = dt.toordinal() + (1 if dt.hour >= 17 else 0)
        return out
    raise ValueError(anchor)


def pair_of(df) -> tuple[Series, Series]:
    """Seria zwykła i odbita z tabeli kopii lokalnej (time, o, h, l, c, filled)."""
    args = (df["time"].to_numpy(), df["o"].to_numpy(), df["h"].to_numpy(),
            df["l"].to_numpy(), df["c"].to_numpy(), df["filled"].to_numpy())
    return Series(*args, side=1), Series(*args, side=-1)


def gap_after(time: np.ndarray) -> np.ndarray:
    """gap[i] = True, gdy między świecą i a i+1 jest przerwa (> 60 min)."""
    g = np.zeros(time.size, dtype=bool)
    g[:-1] = np.diff(time) > GAP_SEC
    return g
