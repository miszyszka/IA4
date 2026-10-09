"""
IA 4 — średnie kroczące i wskaźniki (definicje: IA4_INSTRUKCJA.md, sekcja 8.2).
Wersja projektu: 1.26 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

Każda funkcja dostaje jedną ciągłą serię jednego instrumentu (świece w kolejności
(date, slot), przez noce i weekendy bez przerw) i zwraca tablicę tej samej
długości. Dopóki wskaźnik nie ma pełnego okna, wartość to NaN.
Tych wzorów nie wolno zmieniać bez zmiany instrukcji — zapisane strategie
muszą dawać te same sygnały w każdym systemie.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

MA_TYPES = ("SMA", "EMA", "WMA", "HMA", "DEMA", "TEMA", "KAMA", "VWMA", "ZLEMA")


@njit(cache=True)
def sma(x, n):
    out = np.full(x.size, np.nan)
    s = 0.0
    cnt = 0                       # ile kolejnych skończonych wartości w oknie
    for i in range(x.size):
        if not np.isfinite(x[i]):
            s = 0.0
            cnt = 0
            continue
        s += x[i]
        cnt += 1
        if cnt > n:
            s -= x[i - n]
            cnt = n
        if cnt == n:
            out[i] = s / n
    return out


@njit(cache=True)
def ema(x, n):
    """EMA z α = 2/(n+1). Start: SMA pierwszych n skończonych wartości."""
    out = np.full(x.size, np.nan)
    a = 2.0 / (n + 1.0)
    run = 0
    s = 0.0
    prev = np.nan
    for i in range(x.size):
        if np.isnan(prev):
            if not np.isfinite(x[i]):
                run = 0
                s = 0.0
                continue
            run += 1
            s += x[i]
            if run == n:
                prev = s / n
                out[i] = prev
        else:
            if not np.isfinite(x[i]):
                continue          # nie zdarza się w ciągłej serii — ostrożność
            prev = prev + a * (x[i] - prev)
            out[i] = prev
    return out


@njit(cache=True)
def wma(x, n):
    """Średnia ważona liniowo: najnowsza świeca waga n, najstarsza 1."""
    out = np.full(x.size, np.nan)
    den = n * (n + 1) / 2.0
    for i in range(n - 1, x.size):
        s = 0.0
        ok = True
        for k in range(n):
            v = x[i - k]
            if not np.isfinite(v):
                ok = False
                break
            s += v * (n - k)
        if ok:
            out[i] = s / den
    return out


@njit(cache=True)
def hma(x, n):
    """Hull: WMA(2·WMA(x, ⌊n/2⌋) − WMA(x, n), ⌊√n⌋)."""
    h = max(n // 2, 1)
    d = 2.0 * wma(x, h) - wma(x, n)
    return wma(d, max(int(math.floor(math.sqrt(n))), 1))


@njit(cache=True)
def dema(x, n):
    e1 = ema(x, n)
    return 2.0 * e1 - ema(e1, n)


@njit(cache=True)
def tema(x, n):
    e1 = ema(x, n)
    e2 = ema(e1, n)
    return 3.0 * e1 - 3.0 * e2 + ema(e2, n)


@njit(cache=True)
def kama(x, n):
    """Kaufman: ER z n świec, szybka 2, wolna 30. Start: kama[n-1] = x[n-1]."""
    out = np.full(x.size, np.nan)
    fast = 2.0 / 3.0
    slow = 2.0 / 31.0
    if x.size < n + 1:
        return out
    prev = x[n - 1]
    for i in range(n, x.size):
        change = abs(x[i] - x[i - n])
        vol = 0.0
        for k in range(i - n + 1, i + 1):
            vol += abs(x[k] - x[k - 1])
        er = change / vol if vol > 0 else 0.0
        sc = (er * (fast - slow) + slow) ** 2
        prev = prev + sc * (x[i] - prev)
        out[i] = prev
    return out


@njit(cache=True)
def vwma(x, v, n):
    """Σ(c·v)/Σv z n świec; wolumen 0 (brak danych) ma wagę 0; Σv = 0 → NaN."""
    out = np.full(x.size, np.nan)
    for i in range(n - 1, x.size):
        sv = 0.0
        sxv = 0.0
        for k in range(i - n + 1, i + 1):
            sv += v[k]
            sxv += x[k] * v[k]
        if sv > 0:
            out[i] = sxv / sv
    return out


@njit(cache=True)
def zlema(x, n):
    """EMA(n) z serii 2·x[t] − x[t−lag], lag = ⌊(n−1)/2⌋."""
    lag = (n - 1) // 2
    y = np.full(x.size, np.nan)
    for i in range(lag, x.size):
        y[i] = 2.0 * x[i] - x[i - lag]
    return ema(y, n)


def moving_average(kind: str, n: int, c: np.ndarray, v: np.ndarray) -> np.ndarray:
    kind = kind.upper()
    if kind == "SMA":
        return sma(c, n)
    if kind == "EMA":
        return ema(c, n)
    if kind == "WMA":
        return wma(c, n)
    if kind == "HMA":
        return hma(c, n)
    if kind == "DEMA":
        return dema(c, n)
    if kind == "TEMA":
        return tema(c, n)
    if kind == "KAMA":
        return kama(c, n)
    if kind == "VWMA":
        return vwma(c, v, n)
    if kind == "ZLEMA":
        return zlema(c, n)
    raise ValueError(f"nieznany typ średniej: {kind}")


@njit(cache=True)
def atr(h, l, c, n=14):
    """ATR Wildera. TR[0] = h−l; start: średnia TR[0..n−1]."""
    out = np.full(c.size, np.nan)
    if c.size < n:
        return out
    tr = np.empty(c.size)
    tr[0] = h[0] - l[0]
    for i in range(1, c.size):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    s = 0.0
    for i in range(n):
        s += tr[i]
    prev = s / n
    out[n - 1] = prev
    for i in range(n, c.size):
        prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


@njit(cache=True)
def rsi(c, n=14):
    """RSI Wildera. Start: średnie zysków/strat z pierwszych n zmian."""
    out = np.full(c.size, np.nan)
    if c.size <= n:
        return out
    g = 0.0
    ls = 0.0
    for i in range(1, n + 1):
        d = c[i] - c[i - 1]
        if d > 0:
            g += d
        else:
            ls -= d
    g /= n
    ls /= n
    out[n] = 100.0 if ls == 0 else 100.0 - 100.0 / (1.0 + g / ls)
    for i in range(n + 1, c.size):
        d = c[i] - c[i - 1]
        up = d if d > 0 else 0.0
        dn = -d if d < 0 else 0.0
        g = (g * (n - 1) + up) / n
        ls = (ls * (n - 1) + dn) / n
        out[i] = 100.0 if ls == 0 else 100.0 - 100.0 / (1.0 + g / ls)
    return out
