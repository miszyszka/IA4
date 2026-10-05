"""
IA 4 — dane do badań: kopia lokalna → jedna płaska tablica świec.
Wersja projektu: 1.16 (2026-10-05) — musi zgadzać się z IA4_INSTRUKCJA.md

Wszystkie instrumenty handlowane (spółki główne + kontrolne) leżą jedna za drugą
w tych samych tablicach o, h, l, c, v; `seg_start/seg_end` mówią, gdzie zaczyna
się i kończy każdy instrument. Wskaźniki liczone są osobno dla każdego odcinka —
nigdy przez granicę instrumentów.

STREFY (instrukcja, sekcja 6):
  zone = 0   skarbiec — najstarsze 800 świec instrumentu,
  zone = 1–4 grupa główna, podzielona na 4 okresy (równa liczba dni sesyjnych),
             żeby sprawdzać stabilność w czasie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

from . import indicators as ind

VAULT_BARS = 800
N_FOLDS = 4
CONTEXT = ("SPY", "QQQ")

# Cechy niezależne od linii strategii (definicje: instrukcja, sekcja 8.4).
BASE_FEATURES = ("ret7", "ret35", "vrel", "atrp", "atrrank", "rsi", "slot", "dow",
                 "gap", "d5", "d20", "spy35", "spy140", "qqq35", "qqq140")
# Cechy liczone z linii A/B danej strategii.
LINE_FEATURES = ("zAB", "slopeA", "since")


@njit(cache=True)
def _rank_window(x, w):
    """Percentyl bieżącej wartości wśród ostatnich w (łącznie z bieżącą), 0–100."""
    out = np.full(x.size, np.nan)
    for i in range(w - 1, x.size):
        cur = x[i]
        if not np.isfinite(cur):
            continue
        le = 0
        tot = 0
        for k in range(i - w + 1, i + 1):
            if np.isfinite(x[k]):
                tot += 1
                if x[k] <= cur:
                    le += 1
        if tot == w:
            out[i] = 100.0 * le / tot
    return out


@njit(cache=True)
def _vrel(v, w):
    """v[t] / średnia dodatnich wolumenów z w poprzednich świec; v[t]=0 → NaN."""
    out = np.full(v.size, np.nan)
    for i in range(w, v.size):
        if v[i] <= 0:
            continue
        s = 0.0
        n = 0
        for k in range(i - w, i):
            if v[k] > 0:
                s += v[k]
                n += 1
        if n > 0:
            out[i] = v[i] / (s / n)
    return out


@dataclass
class Market:
    symbols: list                      # instrumenty handlowane, w kolejności odcinków
    seg_start: np.ndarray
    seg_end: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray
    date: np.ndarray                   # RRRRMMDD jako int
    slot: np.ndarray                   # 1–7
    zone: np.ndarray                   # 0 = skarbiec, 1–4 = okresy grupy głównej
    feat: dict = field(default_factory=dict)
    fold_dates: list = field(default_factory=list)   # [(od, do)] okresów 1–4
    last_date: int = 0
    _lines: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return self.c.size

    # ------------------------------------------------------------------ linie
    def line(self, ma: str, n: int) -> np.ndarray:
        key = (ma.upper(), int(n))
        arr = self._lines.get(key)
        if arr is None:
            arr = np.full(self.n, np.nan)
            for a, b in zip(self.seg_start, self.seg_end):
                arr[a:b] = ind.moving_average(key[0], key[1], self.c[a:b], self.v[a:b])
            if len(self._lines) >= 120:            # pamięć (~1,5 MB na linię): najstarsze wypadają
                self._lines.pop(next(iter(self._lines)))
            self._lines[key] = arr
        return arr

    def per_segment(self, fn, *arrays) -> np.ndarray:
        out = np.full(self.n, np.nan)
        for a, b in zip(self.seg_start, self.seg_end):
            out[a:b] = fn(*[x[a:b] for x in arrays])
        return out


def _session_features(df: pd.DataFrame) -> dict:
    """gap, d5, d20 dla jednego instrumentu (df posortowany po date, slot)."""
    first_o = df.groupby("date", sort=True)["o"].first()
    last_c = df.groupby("date", sort=True)["c"].last()
    prev_c = last_c.shift(1)
    gap = (first_o / prev_c - 1.0) * 100.0
    out = {"gap": df["date"].map(gap).to_numpy(float)}
    for n in (5, 20):
        base = last_c.rolling(n).mean().shift(1)       # tylko poprzednie sesje
        out[f"d{n}"] = (df["c"].to_numpy(float) / df["date"].map(base).to_numpy(float) - 1.0) * 100.0
    return out


def _context_series(df: pd.DataFrame) -> dict:
    """(date, slot) → z = (c − EMA(c, n)) / ATR14 dla n = 35, 140."""
    c = df["c"].to_numpy(float)
    a = ind.atr(df["h"].to_numpy(float), df["l"].to_numpy(float), c, 14)
    key = df["date"].astype(str).str.replace("-", "").astype(np.int64) * 10 + df["slot"].astype(np.int64)
    out = {}
    for n in (35, 140):
        z = (c - ind.ema(c, n)) / a
        out[n] = pd.Series(z, index=key.to_numpy())
    return out


def load_market(frames: dict, traded: list, vault_bars: int = VAULT_BARS) -> Market:
    """frames: {symbol: DataFrame(symbol, date, slot, o, h, l, c, v)} — handlowane + SPY/QQQ."""
    parts, starts, ends, syms = [], [], [], []
    pos = 0
    for s in traded:
        df = frames.get(s)
        if df is None or len(df) < vault_bars + 200:
            continue
        df = df.sort_values(["date", "slot"]).reset_index(drop=True)
        parts.append(df)
        starts.append(pos)
        pos += len(df)
        ends.append(pos)
        syms.append(s)
    if not parts:
        raise RuntimeError("Brak danych — uruchom synchronizację (python -m ia4.sync).")
    big = pd.concat(parts, ignore_index=True)

    dates = big["date"].astype(str)
    date_int = dates.str.replace("-", "").astype(np.int64).to_numpy()
    slot = big["slot"].to_numpy(np.int64)
    zone = np.ones(len(big), dtype=np.int64)
    for a in starts:
        zone[a:a + vault_bars] = 0

    # Okresy grupy głównej: dni sesyjne spoza skarbca, podzielone na 4 równe części.
    g_dates = np.unique(date_int[zone > 0])
    bounds = np.array_split(g_dates, N_FOLDS)
    fold_dates = [(int(b[0]), int(b[-1])) for b in bounds if b.size]
    for k, (d0, d1) in enumerate(fold_dates, start=1):
        zone[(zone > 0) & (date_int >= d0) & (date_int <= d1)] = k

    m = Market(
        symbols=syms,
        seg_start=np.array(starts, dtype=np.int64), seg_end=np.array(ends, dtype=np.int64),
        o=big["o"].to_numpy(float), h=big["h"].to_numpy(float), l=big["l"].to_numpy(float),
        c=big["c"].to_numpy(float), v=big["v"].to_numpy(float),
        date=date_int, slot=slot, zone=zone, fold_dates=fold_dates,
        last_date=int(date_int.max()),
    )

    # ---------------------------------------------------------------- cechy
    f = m.feat
    f["atr"] = m.per_segment(lambda h, l, c: ind.atr(h, l, c, 14), m.h, m.l, m.c)
    f["atrp"] = f["atr"] / m.c * 100.0
    f["atrrank"] = m.per_segment(lambda x: _rank_window(x, 350), f["atrp"])
    f["rsi"] = m.per_segment(lambda c: ind.rsi(c, 14), m.c)
    for n in (7, 35):
        f[f"ret{n}"] = m.per_segment(lambda c, n=n: _ret(c, n), m.c)
    f["vrel"] = m.per_segment(lambda v: _vrel(v, 35), m.v)
    f["slot"] = slot.astype(float)
    f["dow"] = (pd.to_datetime(dates).dt.dayofweek.to_numpy() + 1).astype(float)
    sess = [_session_features(p) for p in parts]
    for k in ("gap", "d5", "d20"):
        f[k] = np.concatenate([s[k] for s in sess])

    key = date_int * 10 + slot
    for cs in CONTEXT:
        cdf = frames.get(cs)
        for n in (35, 140):
            name = f"{cs.lower()}{n}"
            if cdf is None or cdf.empty:
                f[name] = np.full(m.n, np.nan)
                continue
            ser = _context_series(cdf.sort_values(["date", "slot"]).reset_index(drop=True))[n]
            ser = ser[~ser.index.duplicated(keep="last")]
            f[name] = ser.reindex(key).to_numpy(float)
    return m


@njit(cache=True)
def _ret(c, n):
    out = np.full(c.size, np.nan)
    for i in range(n, c.size):
        out[i] = (c[i] / c[i - n] - 1.0) * 100.0
    return out


def load_local(traded: list, data_dir: Path, vault_bars: int = VAULT_BARS) -> Market:
    """Wczytuje parquet z kopii lokalnej (format z ia4.sync)."""
    frames = {}
    for s in list(traded) + list(CONTEXT):
        p = data_dir / f"{s.lstrip('^')}.parquet"
        if p.exists():
            frames[s] = pd.read_parquet(p)
    return load_market(frames, traded, vault_bars)
