"""
IA 4 — One-Day: poszukiwanie strategii stabilnych (instrukcja, sekcja 6d).
Wersja projektu: 1.40 (2026-10-14) — musi zgadzać się z IA4_INSTRUKCJA.md

Szuka reguł wejścia na świecach dobowych, które rosną konsekwentnie, a nie tylko „na koniec”.
Żelazna zasada z 6c zostaje: wejście na open dnia, wyjście na close tego samego dnia, stała stawka
(bez kaskady), bez kosztów.

- Dwie rodziny reguł:
  * kierunkowe — kierunek + jeden setup (stan wczorajszej świecy / serii) + najwyżej 2 filtry,
  * neutralne wobec rynku (od 1.38) — każdego dnia long w k spółkach o najniższym wyniku cechy
    i short w k o najwyższym (albo odwrotnie), ta sama stawka; filtr dnia opcjonalny.
  Wszystko, co reguła widzi, jest znane przed open dnia wejścia — bez luki na otwarciu.
- Dwa źródła danych: `1h` — świece dobowe złożone ze świec 1h (ok. 2 lata), `daily` — baza świec
  dobowych z pełną historią (sekcja 4d, kopia lokalna `ia4.daily`), domyślnie od 2000 r.
- Poszukiwanie widzi tylko 53 spółki handlowane. Okno handlu podzielone na 20 równych okresów
  kalendarza (od 1.39; wcześniej 10). Warunek konieczny: najwyżej 3 okresy stratne (od 1.40), najwyżej 1 pusty (< 3 transakcji),
  co najmniej 50 transakcji, suma > 0. doubleProof (20 spółek) — tylko potwierdzenie (6a).
- Wynik: ~/Desktop/IA4/ONE-DAY-SEARCH.xlsx (1h) albo ONE-DAY-SEARCH-DAILY.xlsx (daily), poza gitem.

    python -m ia4.odsearch                      # świece 1h (ok. 2 lata)
    python -m ia4.odsearch --source daily       # baza dobowa od 2000 (najpierw: python -m ia4.daily)
    python -m ia4.odsearch --source daily --since 1990-01-01 --periods 10
    python -m ia4.odsearch --selftest           # „WYNIK: OK”
"""

from __future__ import annotations

import argparse
import itertools
import math
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from . import __version__, config
from . import oneday as od
from .lab.check import trading_days

# ---------------------------------------------------------------------------
#  Parametry (instrukcja 6d — zmiana tylko razem z instrukcją)
# ---------------------------------------------------------------------------
N_PERIODS = 20            # od 1.39 (decyzja człowieka z 14.10.2026); wcześniej 10; --periods
MAX_LOSING = 3            # okresów stratnych (suma < 0) najwyżej — od 1.40 (decyzja człowieka z 14.10.2026; wcześniej 1); --max-losing
MAX_EMPTY = 1             # okresów pustych (< MIN_TRADES_PERIOD transakcji) najwyżej
MIN_TRADES_PERIOD = 3
MIN_TRADES = 50
MAX_FILTERS = 2
WARM_Q = 105              # rozgrzewka: pełnych sesji instrumentu (SMA100 + 5)
DEDUP_JACCARD = 0.7       # reguła podobna (wspólne transakcje ≥ 70%) do lepszej → pominięta
TOP = 200                 # najwyżej tyle reguł w arkuszu WYNIKI (na rodzinę)
DP_LOSING_SHARE = 0.2     # potwierdzenie na doubleProof: suma > 0, stratnych najwyżej 20% okresów (4 z 20)
DP_MIN_T = 2.5            # … i t-stat dziennych wyników ≥ max(2,5; próg Bonferroniego dla liczby reguł w arkuszu)
DP_ALPHA = 0.05           # szansa choćby jednego fałszywego ✓ w całej liście (Bonferroni)
PLACEBO_SEED = 2026       # placebo: losowy znak każdego dnia (ten sam dla wszystkich spółek)
PF_CAPITAL = 10_000.0     # arkusze PORTFEL: wspólny portfel, stawka 5% stanu portfela na transakcję
PF_STAKE_PCT = 5.0
PF_SHEETS = 3             # kierunkowe
PF_SHEETS_N = 2           # neutralne
R_DAYS = od.R_DAYS        # r — jak w 6c
DAILY_SINCE = "2000-01-01"   # od 1.39 (decyzja człowieka z 14.10.2026); --since
NEUTRAL_K = (3, 5, 10)    # spółek w każdej nodze (53 spółki); doubleProof: k × 20/53, zaokrąglone, ≥ 1
NEUTRAL_MIN = 2           # dzień handlowany, gdy ≥ 2k spółek ma wynik cechy

DOW = ["pon", "wt", "śr", "czw", "pt"]


# ---------------------------------------------------------------------------
#  Panel świec dobowych na wspólnym kalendarzu
# ---------------------------------------------------------------------------
@dataclass
class Panel:
    syms: list[str]
    groups: list[str]
    dates: list[str]
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    valid: np.ndarray                     # pełna sesja
    ret: np.ndarray                       # (close/open − 1)·100, 0 gdy niepełna
    base: np.ndarray = None               # wolno handlować: pełna sesja t, pełna t−1, rozgrzewka
    feat: dict = field(default_factory=dict)   # nazwa → wartości liczbowe (S×T), znane przed open t
    spy: dict = field(default_factory=dict)    # cechy SPY na kalendarzu (T)
    source: str = "1h"
    mkt: np.ndarray = None                # wynik rynku dnia t: średni open→close % wszystkich spółek (tylko do oceny)


def build(days: dict[str, od.Days], groups: dict[str, str], spy: od.Days | None,
          calendar: list[str] | None = None, source: str = "1h") -> Panel:
    """Świece dobowe instrumentów → tablice S×T. Kalendarz: dni NYSE z listy świąt (1h) albo podany (daily)."""
    syms = list(days)
    if calendar is None:
        first = min(d.dates[0] for d in days.values())
        last = max(d.dates[-1] for d in days.values())
        calendar = trading_days(first, last)
    cal = calendar
    pos = {d: i for i, d in enumerate(cal)}
    S, T = len(syms), len(cal)
    nan = np.full((S, T), np.nan)
    P = Panel(syms, [groups[s] for s in syms], cal, nan.copy(), nan.copy(), nan.copy(), nan.copy(),
              np.zeros((S, T), bool), np.zeros((S, T)), source=source)
    for i, s in enumerate(syms):
        dd = days[s]
        idx = np.array([pos.get(d, -1) for d in dd.dates])
        v = np.array(dd.valid, bool) & (idx >= 0)
        t = idx[v]
        for arr, src in ((P.o, dd.o), (P.h, dd.h), (P.l, dd.l), (P.c, dd.c)):
            arr[i, t] = np.asarray(src, float)[v]
        P.valid[i, t] = True
    P.ret = np.where(P.valid, (P.c / np.where(P.valid, P.o, 1.0) - 1.0) * 100.0, 0.0)
    cnt = P.valid.sum(axis=0)
    P.mkt = np.where(cnt > 0, P.ret.sum(axis=0) / np.maximum(cnt, 1), 0.0)
    _features(P)
    _spy(P, spy)
    return P


def _rsi(c: np.ndarray, n: int = 2) -> np.ndarray:
    """RSI Wildera z zamknięć."""
    out = np.full(len(c), np.nan)
    if len(c) <= n:
        return out
    d = np.diff(c)
    g, ls = np.clip(d, 0, None), np.clip(-d, 0, None)
    ag, al = g[:n].mean(), ls[:n].mean()
    for q in range(n, len(c)):
        if q > n:
            ag = (ag * (n - 1) + g[q - 1]) / n
            al = (al * (n - 1) + ls[q - 1]) / n
        out[q] = 100.0 if al == 0 and ag > 0 else (50.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al))
    return out


def _sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.concatenate([[0.0], np.cumsum(x)])
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def _streak(flag: np.ndarray) -> np.ndarray:
    """Długość serii True kończącej się na każdej pozycji (wektorowo)."""
    f = flag.astype(np.int64)
    cs = np.cumsum(f)
    reset = np.where(f == 0, cs, 0)
    return (cs - np.maximum.accumulate(reset)).astype(float)


def _roll(x: np.ndarray, n: int, fn) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = fn(sliding_window_view(x, n), axis=1)
    return out


def series_features(o, h, l, c) -> dict[str, np.ndarray]:
    """Cechy na końcu każdej pełnej sesji q (ciąg pełnych sesji jednego instrumentu)."""
    Q = len(c)
    f: dict[str, np.ndarray] = {}
    f["dn"], f["up"] = _streak(c < o), _streak(c > o)
    rng = (h - l) / o * 100.0
    r = _sma(rng, R_DAYS)                                 # r na końcu sesji q: sesje q−19 … q
    f["r"] = r
    f["body_r"] = (c - o) / o * 100.0 / r
    for M in (1, 3, 5, 10):
        chg = np.full(Q, np.nan)
        chg[M:] = (c[M:] / c[:-M] - 1.0) * 100.0
        f[f"chg{M}_r"] = chg / r
        if M in (1, 5):
            f[f"chg{M}p"] = chg
    hl = h - l
    f["cl"] = np.where(hl > 0, (c - l) / np.where(hl > 0, hl, 1.0), 0.5)
    f["rsi2"] = _rsi(c, 2)
    for n in (10, 20):
        mn, mx = _roll(c, n, np.min), _roll(c, n, np.max)
        f[f"low{n}"] = np.where(np.isnan(mn), np.nan, (c <= mn).astype(float))
        f[f"high{n}"] = np.where(np.isnan(mx), np.nan, (c >= mx).astype(float))
    nr7 = np.full(Q, np.nan)
    if Q > 6:
        prev_min = _roll(hl, 6, np.min)                     # min z q−5 … q
        nr7[6:] = (hl[6:] < prev_min[5:-1]).astype(float)  # porównanie z q−6 … q−1
    f["nr7"] = nr7
    for n in (20, 50, 100):
        s = _sma(c, n)
        f[f"above{n}"] = np.where(np.isnan(s), np.nan, (c > s).astype(float))
        if n == 20:
            f["dist20_r"] = (c / s - 1.0) * 100.0 / r
    s50 = _sma(c, 50)
    sl = np.full(Q, np.nan)
    sl[5:] = np.sign(s50[5:] - s50[:-5])
    f["slope50"] = sl
    rv = np.full(Q, np.nan)
    ra = _sma(np.nan_to_num(r, nan=0.0), 60)
    ok = np.arange(Q) >= R_DAYS - 1 + 59
    rv[ok] = (r[ok] > ra[ok]).astype(float)
    f["volhi"] = rv
    return f


def _features(P: Panel) -> None:
    """Cecha z końca sesji q → dzień t = następny dzień kalendarza (tylko gdy t−1 jest tą sesją)."""
    S, T = P.o.shape
    P.base = np.zeros((S, T), bool)
    for i in range(S):
        vi = np.flatnonzero(P.valid[i])
        if len(vi) == 0:
            continue
        f = series_features(P.o[i, vi], P.h[i, vi], P.l[i, vi], P.c[i, vi])
        keep = vi + 1 < T
        src, tgt = np.flatnonzero(keep), vi[keep] + 1
        for k, v in f.items():
            if k not in P.feat:
                P.feat[k] = np.full((S, T), np.nan)
            P.feat[k][i, tgt] = v[src]
        warm = src >= WARM_Q - 1                        # ≥ WARM_Q pełnych sesji przed dniem t
        P.base[i, tgt] = warm & P.valid[i, tgt]


def _spy(P: Panel, spy: od.Days | None) -> None:
    T = len(P.dates)
    P.spy = {k: np.full(T, np.nan) for k in ("above50", "down", "chg1", "chg5")}
    if spy is None:
        return
    pos = {d: i for i, d in enumerate(P.dates)}
    vi = [j for j, v in enumerate(spy.valid) if v]
    o, c = (np.array([getattr(spy, k)[j] for j in vi], float) for k in ("o", "c"))
    a50 = _sma(c, 50)
    ch1, ch5 = np.full(len(c), np.nan), np.full(len(c), np.nan)
    ch1[1:] = (c[1:] / c[:-1] - 1) * 100
    ch5[5:] = (c[5:] / c[:-5] - 1) * 100
    for q, j in enumerate(vi):
        t = pos.get(spy.dates[j])
        if t is None or t + 1 >= T:
            continue
        P.spy["above50"][t + 1] = np.nan if np.isnan(a50[q]) else float(c[q] > a50[q])
        P.spy["down"][t + 1] = float(c[q] < o[q])
        P.spy["chg1"][t + 1], P.spy["chg5"][t + 1] = ch1[q], ch5[q]


# ---------------------------------------------------------------------------
#  Słownik warunków
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Cond:
    code: str
    desc: str
    group: str


def _gt(a, x):
    return np.nan_to_num(a, nan=-np.inf) >= x


def _lt(a, x):
    return np.nan_to_num(a, nan=np.inf) <= x


def _day(P: Panel, v: np.ndarray) -> np.ndarray:
    return np.broadcast_to(v, P.base.shape)


def setups() -> list[tuple[Cond, callable]]:
    out = [(Cond("all", "każdy dzień", "s"), lambda P: np.ones_like(P.base))]
    for n in range(1, 6):
        out.append((Cond(f"dn{n}", f"≥ {n} świec spadkowych z rzędu", "s"), lambda P, n=n: _gt(P.feat["dn"], n)))
    for n in range(1, 6):
        out.append((Cond(f"up{n}", f"≥ {n} świec wzrostowych z rzędu", "s"), lambda P, n=n: _gt(P.feat["up"], n)))
    for k in (0.5, 1.0, 1.5, 2.0):
        out.append((Cond(f"bd{k:g}", f"wczoraj spadek korpusu ≥ {k:g} r", "s"), lambda P, k=k: _lt(P.feat["body_r"], -k)))
        out.append((Cond(f"bu{k:g}", f"wczoraj wzrost korpusu ≥ {k:g} r", "s"), lambda P, k=k: _gt(P.feat["body_r"], k)))
    for M in (3, 5, 10):
        for k in (1.0, 2.0, 3.0):
            out.append((Cond(f"d{M}x{k:g}", f"spadek {M} sesji ≥ {k:g} r", "s"),
                        lambda P, M=M, k=k: _lt(P.feat[f"chg{M}_r"], -k)))
            out.append((Cond(f"u{M}x{k:g}", f"wzrost {M} sesji ≥ {k:g} r", "s"),
                        lambda P, M=M, k=k: _gt(P.feat[f"chg{M}_r"], k)))
    out.append((Cond("cl_lo", "wczoraj zamknięcie w dolnych 20% zakresu", "s"), lambda P: _lt(P.feat["cl"], 0.2)))
    out.append((Cond("cl_hi", "wczoraj zamknięcie w górnych 20% zakresu", "s"), lambda P: _gt(P.feat["cl"], 0.8)))
    for x in (5, 10):
        out.append((Cond(f"rsi<{x}", f"RSI(2) < {x}", "s"), lambda P, x=x: np.nan_to_num(P.feat["rsi2"], nan=50) < x))
        out.append((Cond(f"rsi>{100 - x}", f"RSI(2) > {100 - x}", "s"),
                    lambda P, x=x: np.nan_to_num(P.feat["rsi2"], nan=50) > 100 - x))
    for n in (10, 20):
        out.append((Cond(f"low{n}", f"zamknięcie najniższe z {n} sesji", "s"), lambda P, n=n: _gt(P.feat[f"low{n}"], 1)))
        out.append((Cond(f"high{n}", f"zamknięcie najwyższe z {n} sesji", "s"), lambda P, n=n: _gt(P.feat[f"high{n}"], 1)))
    out.append((Cond("nr7", "wczoraj najwęższy zakres z 7 sesji", "s"), lambda P: _gt(P.feat["nr7"], 1)))
    return out


def filters() -> list[tuple[Cond, callable]]:
    out = []
    for n in (20, 50, 100):
        out.append((Cond(f"c>sma{n}", f"cena > SMA{n}", f"t{n}"), lambda P, n=n: _gt(P.feat[f"above{n}"], 1)))
        out.append((Cond(f"c<sma{n}", f"cena < SMA{n}", f"t{n}"), lambda P, n=n: _lt(np.nan_to_num(P.feat[f"above{n}"], nan=1), 0)))
    out.append((Cond("sma50+", "SMA50 rosnąca", "sl"), lambda P: _gt(P.feat["slope50"], 1)))
    out.append((Cond("sma50-", "SMA50 spadkowa", "sl"), lambda P: _lt(np.nan_to_num(P.feat["slope50"], nan=0), -1)))
    out += day_filters()
    out.append((Cond("vol+", "zmienność wysoka (r > średnia r z 60 sesji)", "v"), lambda P: _gt(P.feat["volhi"], 1)))
    out.append((Cond("vol-", "zmienność niska (r ≤ średnia r z 60 sesji)", "v"),
                lambda P: _lt(np.nan_to_num(P.feat["volhi"], nan=1), 0)))
    return out


def day_filters() -> list[tuple[Cond, callable]]:
    """Filtry całego dnia (rynek, kalendarz) — te same dla każdej spółki."""
    out = [(Cond("spy>50", "SPY > SMA50", "m"), lambda P: _day(P, _gt(P.spy["above50"], 1))),
           (Cond("spy<50", "SPY < SMA50", "m"), lambda P: _day(P, _lt(np.nan_to_num(P.spy["above50"], nan=1), 0))),
           (Cond("spy_dn", "SPY wczoraj spadkowa", "md"), lambda P: _day(P, _gt(P.spy["down"], 1))),
           (Cond("spy_up", "SPY wczoraj wzrostowa", "md"), lambda P: _day(P, _lt(np.nan_to_num(P.spy["down"], nan=1), 0)))]
    for k, name in enumerate(DOW):
        out.append((Cond(name, f"dzień: {name}", "dow"),
                    lambda P, k=k: _day(P, np.array([date.fromisoformat(d).weekday() == k for d in P.dates]))))
    return out


@dataclass(frozen=True)
class Rule:
    dir: int
    setup: Cond
    filt: tuple[Cond, ...]

    @property
    def code(self) -> str:
        return "|".join(["L" if self.dir > 0 else "S", self.setup.code] + [f.code for f in self.filt])

    @property
    def desc(self) -> str:
        parts = [("LONG" if self.dir > 0 else "SHORT") + " — " + self.setup.desc] + [f.desc for f in self.filt]
        return " · ".join(parts)


def rules(max_filters: int = MAX_FILTERS):
    S, F = setups(), filters()
    combos = [()]
    for k in range(1, max_filters + 1):
        for cmb in itertools.combinations(range(len(F)), k):
            if len({F[j][0].group for j in cmb}) == k:
                combos.append(cmb)
    return S, F, combos


# --- rodzina neutralna (B) -------------------------------------------------
def scores() -> list[tuple[Cond, callable]]:
    """Cechy do rankingu spółek w danym dniu (znane przed open)."""
    def rel(P, M):
        return (P.feat[f"chg{M}p"] - P.spy[f"chg{M}"][None, :]) / P.feat["r"]
    return [
        (Cond("chg1", "zmiana wczoraj (zamknięcie → zamknięcie, w r)", "sc"), lambda P: P.feat["chg1_r"]),
        (Cond("body", "korpus wczorajszej świecy (w r)", "sc"), lambda P: P.feat["body_r"]),
        (Cond("chg3", "zmiana 3 sesji (w r)", "sc"), lambda P: P.feat["chg3_r"]),
        (Cond("chg5", "zmiana 5 sesji (w r)", "sc"), lambda P: P.feat["chg5_r"]),
        (Cond("chg10", "zmiana 10 sesji (w r)", "sc"), lambda P: P.feat["chg10_r"]),
        (Cond("rsi2", "RSI(2)", "sc"), lambda P: P.feat["rsi2"]),
        (Cond("cl", "położenie wczorajszego zamknięcia w zakresie dnia", "sc"), lambda P: P.feat["cl"]),
        (Cond("dist20", "odległość ceny od SMA20 (w r)", "sc"), lambda P: P.feat["dist20_r"]),
        (Cond("rel1", "zmiana wczoraj względem SPY (w r)", "sc"), lambda P: rel(P, 1)),
        (Cond("rel5", "zmiana 5 sesji względem SPY (w r)", "sc"), lambda P: rel(P, 5)),
    ]


@dataclass(frozen=True)
class NRule:
    mode: str                 # "rev" — long najniższe, short najwyższe; "mom" — odwrotnie
    score: Cond
    k: int
    day: Cond | None

    dir = 0

    @property
    def code(self) -> str:
        return "|".join(["N", self.mode, self.score.code, f"k{self.k}"] + ([self.day.code] if self.day else []))

    @property
    def desc(self) -> str:
        lo, hi = ("najniższą", "najwyższą") if self.mode == "rev" else ("najwyższą", "najniższą")
        s = (f"NEUTRALNY — long {self.k} spółek z {lo}, short {self.k} z {hi} wartością: {self.score.desc}")
        return s + (f" · {self.day.desc}" if self.day else "")


def rank_masks(score: np.ndarray, elig: np.ndarray, ks) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Dla każdego dnia: k spółek o najniższym i k o najwyższym wyniku (tylko dni z ≥ 2k wynikami)."""
    ok = elig & np.isfinite(score)
    cnt = ok.sum(axis=0)
    lo = np.argsort(np.where(ok, score, np.inf), axis=0, kind="stable")
    hi = np.argsort(np.where(ok, -score, np.inf), axis=0, kind="stable")
    S, T = score.shape
    cols = np.arange(T)
    out = {}
    for k in ks:
        low, high = np.zeros((S, T), bool), np.zeros((S, T), bool)
        day = cnt >= NEUTRAL_MIN * k
        for j in range(min(k, S)):
            low[lo[j], cols] = True
            high[hi[j], cols] = True
        out[k] = (low & day[None, :], high & day[None, :])
    return out


def k_dp(k: int, n_dp: int, n_main: int) -> int:
    return max(1, int(round(k * n_dp / max(1, n_main))))


# ---------------------------------------------------------------------------
#  Ocena reguły
# ---------------------------------------------------------------------------
def periods(P: Panel, rows: np.ndarray) -> tuple[int, list[tuple[int, int]]]:
    """Okno handlu: od dnia, w którym połowa spółek grupy ma rozgrzewkę, do końca; 10 równych części."""
    share = P.base[rows].mean(axis=0)
    g0 = int(np.argmax(share >= 0.5)) if (share >= 0.5).any() else len(P.dates)
    idx = np.array_split(np.arange(g0, len(P.dates)), N_PERIODS)
    return g0, [(int(a[0]), int(a[-1]) + 1) for a in idx if len(a)]


@dataclass
class Stats:
    n: int
    wins: int
    total: float
    avg: float
    pf: float
    tstat: float
    r2: float
    mdd: float
    per_n: list[int]
    per_sum: list[float]
    losing: int
    empty: int
    worst: float
    better_than_base: int
    excess: float = 0.0       # śr. wynik transakcji − śr. baza ważona transakcjami okresów

    @property
    def why_not(self) -> str:
        """Dlaczego reguła nie spełnia warunku (pusty tekst — spełnia)."""
        r = []
        if self.losing > MAX_LOSING:
            r.append(f"okresy stratne {self.losing} > {MAX_LOSING}")
        if self.empty > MAX_EMPTY:
            r.append(f"okresy puste {self.empty} > {MAX_EMPTY}")
        if self.n < MIN_TRADES:
            r.append(f"transakcji {self.n} < {MIN_TRADES}")
        if self.total <= 0:
            r.append("suma ≤ 0")
        return ", ".join(r)

    @property
    def ok(self) -> bool:
        return (self.n >= MIN_TRADES and self.losing <= MAX_LOSING and self.empty <= MAX_EMPTY
                and self.total > 0)


def evaluate_x(x: np.ndarray, m: np.ndarray, win, base_avg: list[float]) -> Stats:
    """x — wyniki transakcji % ze znakiem pozycji (0 poza transakcjami), m — transakcje (S×T)."""
    g0, pers = win
    xs, ms = x[:, g0:], m[:, g0:]
    daily = xs.sum(axis=0)
    dn = ms.sum(axis=0)
    n = int(dn.sum())
    pos = float(xs[xs > 0].sum())
    neg = float(-xs[xs < 0].sum())
    wins = int((xs > 0).sum())
    total = float(daily.sum())
    per_n = [int(dn[a - g0:b - g0].sum()) for a, b in pers]
    per_sum = [float(daily[a - g0:b - g0].sum()) for a, b in pers]
    losing = sum(1 for k, s in zip(per_n, per_sum) if k >= MIN_TRADES_PERIOD and s < 0)
    empty = sum(1 for k in per_n if k < MIN_TRADES_PERIOD)
    better = sum(1 for k, s, b in zip(per_n, per_sum, base_avg) if k >= MIN_TRADES_PERIOD and s / k > b)
    sd = float(daily.std(ddof=1)) if len(daily) > 1 else 0.0
    tstat = float(daily.mean() / sd * math.sqrt(len(daily))) if sd > 0 else 0.0
    cum = np.cumsum(daily)
    if len(cum) > 2 and cum.std() > 0:
        tt = np.arange(len(cum), dtype=float)
        r2 = float(np.corrcoef(tt, cum)[0, 1] ** 2) * (1 if cum[-1] >= cum[0] else -1)
    else:
        r2 = 0.0
    c0 = np.concatenate([[0.0], cum])
    mdd = float((np.maximum.accumulate(c0) - c0).max())
    worst = min((s for k, s in zip(per_n, per_sum) if k >= MIN_TRADES_PERIOD), default=0.0)
    excess = (total - sum(k * b for k, b in zip(per_n, base_avg))) / n if n else 0.0
    return Stats(n, wins, total, total / n if n else 0.0, (pos / neg if neg > 0 else (99.0 if pos > 0 else 0.0)),
                 tstat, r2, mdd, per_n, per_sum, losing, empty, worst, better, excess)


def evaluate(m: np.ndarray, R: np.ndarray, d: int, win, base_avg: list[float]) -> Stats:
    return evaluate_x(np.where(m, R * d, 0.0), m, win, base_avg)


def base_avgs(P: Panel, rows: np.ndarray, d: int, win, R: np.ndarray | None = None) -> list[float]:
    """Punkt odniesienia: ten sam kierunek każdego dnia — średni wynik transakcji w każdym okresie."""
    A = P.base[rows]
    x = np.where(A, (P.ret if R is None else R)[rows] * d, 0.0)
    out = []
    for a, b in win[1]:
        k = A[:, a:b].sum()
        out.append(float(x[:, a:b].sum() / k) if k else 0.0)
    return out


def _dedupe(passed: list, mask_of, rows: np.ndarray) -> list:
    kept, kept_masks = [], []
    for item in passed:
        mm = mask_of(item)[rows]
        a = mm.sum()
        if any((mm & km).sum() / (a + km.sum() - (mm & km).sum()) >= DEDUP_JACCARD for km in kept_masks):
            continue
        kept.append(item)
        kept_masks.append(mm)
        if len(kept) >= TOP:
            break
    return kept


def search(P: Panel, log=print, sign: np.ndarray | None = None) -> dict:
    """Rodzina kierunkowa na 53 spółkach handlowanych; potwierdzenie na doubleProof.
    sign — placebo: wyniki dnia t pomnożone przez sign[t] (±1), cechy bez zmian."""
    rows = np.array([i for i, g in enumerate(P.groups) if g in ("main", "proof")])
    dprows = np.array([i for i, g in enumerate(P.groups) if g == "doubleProof"], dtype=int)
    win = periods(P, rows)
    win_dp = periods(P, dprows) if len(dprows) else None
    S, F, combos = rules()
    smask = [fn(P) for _, fn in S]
    fmask = [fn(P) for _, fn in F]
    A = P.base
    R = P.ret if sign is None else P.ret * sign[None, :]
    Rm, Am = R[rows], A[rows]
    bases = {d: base_avgs(P, rows, d, win, R) for d in (1, -1)}
    passed = []
    tested = 0
    best_short = None                  # najlepszy short ogółem (także niespełniający warunku) — arkusz PORTFEL S1
    t0 = time.time()
    for si, (sc, _) in enumerate(S):
        sm = smask[si][rows] & Am
        for cmb in combos:
            m = sm
            for j in cmb:
                m = m & fmask[j][rows]
            tested += 2
            if m.sum() < MIN_TRADES:
                continue
            x = np.where(m, Rm, 0.0)
            for d in (1, -1):
                st = evaluate_x(x * d, m, win, bases[d])
                if st.ok:
                    passed.append((Rule(d, sc, tuple(F[j][0] for j in cmb)), st, si, cmb))
                if d < 0 and st.total > 0 and (best_short is None or
                                               (st.losing, -st.tstat) < (best_short[1].losing, -best_short[1].tstat)):
                    best_short = (Rule(d, sc, tuple(F[j][0] for j in cmb)), st, si, cmb)
    log(f"  kierunkowe: reguł {tested} · spełnia warunek {N_PERIODS} okresów: {len(passed)} · {time.time() - t0:.0f} s")
    passed.sort(key=lambda x: (x[1].losing, -x[1].tstat))

    def full_mask(item):
        _, _, si, cmb = item
        m = smask[si] & A
        for j in cmb:
            m = m & fmask[j]
        return m

    H = hedged(P, sign)

    def entry(item):
        rule, st = item[0], item[1]
        mk = full_mask(item)
        dp = dp_raw = None
        if win_dp is not None:
            dp = evaluate(mk[dprows], H[dprows], rule.dir, win_dp, [0.0] * N_PERIODS)
            dp_raw = evaluate(mk[dprows], R[dprows], rule.dir, win_dp, [0.0] * N_PERIODS)
        return {"rule": rule, "st": st, "dp": dp, "dp_raw": dp_raw, "sgn": np.where(mk, rule.dir, 0).astype(np.int8)}

    out = [entry(item) for item in _dedupe(passed, full_mask, rows)]
    short = next((it for it in out if it["rule"].dir < 0), None)
    if short is None and best_short is not None and sign is None:
        short = entry(best_short)
    return {"tested": tested, "passed": len(passed), "kept": out, "win": win, "win_dp": win_dp,
            "bases": bases, "rows": rows, "dprows": dprows, "tcrit": t_crit(len(out)), "short": short}


def search_neutral(P: Panel, log=print, sign: np.ndarray | None = None) -> dict:
    """Rodzina neutralna wobec rynku (B): ranking spółek w każdym dniu, long k + short k."""
    rows = np.array([i for i, g in enumerate(P.groups) if g in ("main", "proof")])
    dprows = np.array([i for i, g in enumerate(P.groups) if g == "doubleProof"], dtype=int)
    win = periods(P, rows)
    win_dp = periods(P, dprows) if len(dprows) else None
    R = P.ret if sign is None else P.ret * sign[None, :]
    zero = [0.0] * N_PERIODS
    days = [(None, None)] + [(c, fn(P)[0]) for c, fn in day_filters()]
    passed, tested, t0 = [], 0, time.time()
    cache = {}
    for sc, fn in scores():
        val = fn(P)
        rk = rank_masks(val[rows], P.base[rows], NEUTRAL_K)
        rk_dp = rank_masks(val[dprows], P.base[dprows], [k_dp(k, len(dprows), len(rows)) for k in NEUTRAL_K]) \
            if len(dprows) else {}
        for k in NEUTRAL_K:
            low, high = rk[k]
            xr = np.where(low, R[rows], 0.0) - np.where(high, R[rows], 0.0)
            mm = low | high
            for dc, dv in days:
                tested += 2
                m = mm if dv is None else mm & dv[None, :]
                if m.sum() < MIN_TRADES:
                    continue
                x = xr if dv is None else np.where(dv[None, :], xr, 0.0)
                for mode, sgn in (("rev", 1), ("mom", -1)):
                    st = evaluate_x(x * sgn, m, win, zero)
                    if st.ok:
                        passed.append((NRule(mode, sc, k, dc), st))
                        cache[(sc.code, k)] = (low, high, rk_dp.get(k_dp(k, len(dprows), len(rows))))
    log(f"  neutralne: reguł {tested} · spełnia warunek {N_PERIODS} okresów: {len(passed)} · {time.time() - t0:.0f} s")
    passed.sort(key=lambda x: (x[1].losing, -x[1].tstat))
    S, T = P.o.shape

    def sgn_of(item):
        r = item[0]
        low, high, _ = cache[(r.score.code, r.k)]
        s = np.zeros((S, T), np.int8)
        s[rows] = np.where(low, 1, np.where(high, -1, 0))
        if r.day is not None:
            s[:, ~dict((c.code, v) for c, v in days if c)[r.day.code]] = 0
        return s if r.mode == "rev" else -s

    def mask_of(item):
        return sgn_of(item) != 0

    H = hedged(P, sign)
    out = []
    for item in _dedupe(passed, mask_of, rows):
        r, st = item
        sg = sgn_of(item)
        dp = dp_raw = None
        if win_dp is not None:
            dl, dh = cache[(r.score.code, r.k)][2]
            sdp = np.where(dl, 1, np.where(dh, -1, 0)).astype(float) * (1 if r.mode == "rev" else -1)
            if r.day is not None:
                sdp[:, ~dict((c.code, v) for c, v in days if c)[r.day.code]] = 0
            dp = evaluate_x(sdp * H[dprows], sdp != 0, win_dp, zero)
            dp_raw = evaluate_x(sdp * R[dprows], sdp != 0, win_dp, zero)
            sg[dprows] = sdp.astype(np.int8)
        out.append({"rule": r, "st": st, "dp": dp, "dp_raw": dp_raw, "sgn": sg})
    return {"tested": tested, "passed": len(passed), "kept": out, "win": win, "rows": rows, "dprows": dprows,
            "tcrit": t_crit(len(out))}


def hedged(P: Panel, sign: np.ndarray | None = None) -> np.ndarray:
    """Wynik spółki bez rynku: open→close % spółki − średni open→close % wszystkich spółek tego dnia.
    Potwierdzenie na doubleProof liczone na tym wyniku — inne spółki, ale te same dni: bez odjęcia rynku
    reguła „long w dni X” potwierdzałaby się przypadkowym układem dni całego rynku."""
    H = np.where(P.valid, P.ret - P.mkt[None, :], 0.0)
    return H if sign is None else H * sign[None, :]


def t_crit(n: int) -> float:
    """Próg t-stat potwierdzenia: jednostronnie, Bonferroni dla n reguł w arkuszu, nie mniej niż DP_MIN_T."""
    from statistics import NormalDist
    return max(DP_MIN_T, NormalDist().inv_cdf(1.0 - DP_ALPHA / max(1, n)))


def dp_max_losing() -> int:
    return max(1, int(round(N_PERIODS * DP_LOSING_SHARE)))


def confirmed(dp: Stats | None, tc: float = DP_MIN_T) -> bool:
    return (dp is not None and dp.n > 0 and dp.total > 0 and dp.losing <= dp_max_losing()
            and dp.tstat >= tc)


def n_confirmed(r: dict) -> int:
    return sum(confirmed(it["dp"], r["tcrit"]) for it in r["kept"])


def placebo(P: Panel) -> dict:
    """To samo poszukiwanie z losowym znakiem każdego dnia: ile reguł przechodzi z czystego przypadku
    na tych danych (ta sama zmienność, ta sama korelacja spółek, zero przewagi)."""
    sign = np.random.default_rng(PLACEBO_SEED).choice([-1.0, 1.0], size=len(P.dates))
    out = {}
    for name, fn in (("dir", search), ("neu", search_neutral)):
        r = fn(P, log=lambda *_: None, sign=sign)
        out[name] = {"passed": r["passed"], "kept": len(r["kept"]), "confirmed": n_confirmed(r)}
    return out


# ---------------------------------------------------------------------------
#  Portfel 10 000 $ (stała stawka 5% stanu portfela, suma dnia ≤ stan portfela)
# ---------------------------------------------------------------------------
def portfolio(P: Panel, sgn: np.ndarray, rows: np.ndarray, capital: float = PF_CAPITAL, g0: int = 0) -> dict:
    """sgn — S×T: +1 long, −1 short, 0 bez transakcji."""
    eq = peak = capital
    mdd, ruined = 0.0, False
    out, n_scaled, trades, wins = [], 0, 0, 0
    tag = {"doubleProof": " · dP"}
    sub = sgn[rows]
    for t in range(g0, sgn.shape[1]):
        nz = np.flatnonzero(sub[:, t])
        if not len(nz):
            continue
        e0 = eq
        stake0 = e0 * PF_STAKE_PCT / 100.0
        scale = min(1.0, e0 / (stake0 * len(nz)))
        n_scaled += scale < 1.0
        for j in nz:
            i = rows[j]
            d = int(sub[j, t])
            stake = stake0 * scale
            pct = d * P.ret[i, t]
            pnl = stake * pct / 100.0
            eq += pnl
            trades += 1
            wins += pnl > 0
            s = P.feat["dn" if d > 0 else "up"][i, t]
            out.append({"day": P.dates[t], "sym": P.syms[i] + tag.get(P.groups[i], "") + ("" if d > 0 else " (short)"),
                        "candle": int(s) + 1 if not np.isnan(s) else None, "k": 1, "stake": stake, "pnl": pnl,
                        "trade_pct": pct, "ret": (eq / capital - 1.0) * 100.0, "eq": eq, "scale": scale})
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak * 100.0)
        if eq <= capital * od.RUIN_PCT / 100.0:
            ruined = True
            break
    return {"rows": out, "capital": capital, "end": eq, "ret": (eq / capital - 1.0) * 100.0, "mdd": mdd,
            "trades": trades, "wins": wins, "ruined": ruined, "days": len({r["day"] for r in out}),
            "scaled": n_scaled, "max_k": 1, "first": out[0]["day"] if out else None,
            "last": out[-1]["day"] if out else None}


# ---------------------------------------------------------------------------
#  Excel
# ---------------------------------------------------------------------------
def _results_sheet(wb, title: str, P: Panel, res: dict, head_note: str):
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    head = PatternFill("solid", fgColor="1F2A37")
    sub = PatternFill("solid", fgColor="E5E7EB")
    dpf = PatternFill("solid", fgColor="EDE9FE")
    good = PatternFill("solid", fgColor="DCFCE7")
    bad = PatternFill("solid", fgColor="FEE2E2")
    white, bold = Font(bold=True, color="FFFFFF"), Font(bold=True)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sep = Border(left=Side(style="thin", color="9CA3AF"))
    pct = "0.00;[Red]-0.00"
    pers = res["win"][1]

    ws = wb.create_sheet(title)
    fixed = ["Nr", "Kod reguły", "Opis", "Kierunek", "Transakcji", "Zyskownych %", "Śr. wynik transakcji %",
             "Suma wyników %", "PF", "t-stat (dni)", "R² krzywej", "Maks. obsunięcie (suma %)",
             "Okresy stratne", "Okresy puste", "Najgorszy okres (suma %)", "Okresy lepsze niż baza",
             "Nadwyżka nad bazą (śr. % na transakcję)"]
    dp_cols = ["dP transakcji", "dP suma % (surowa)", "dP suma % bez rynku", "dP śr. % bez rynku",
               "dP t-stat bez rynku", "dP okresy stratne bez rynku", "dP potwierdzona"]
    c_per = len(fixed) + 1
    c_dp = c_per + 2 * len(pers)
    for j, h in enumerate(fixed, start=1):
        ws.cell(1, j, head_note if j == 1 else None)
        ws.cell(2, j, h)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(fixed))
    for p, (a, b) in enumerate(pers):
        c = c_per + 2 * p
        ws.cell(1, c, f"Okres {p + 1}: {P.dates[a]} – {P.dates[b - 1]}")
        ws.merge_cells(start_row=1, start_column=c, end_row=1, end_column=c + 1)
        ws.cell(2, c, "transakcji")
        ws.cell(2, c + 1, "suma %")
    ws.cell(1, c_dp, f"doubleProof (20 spółek) — potwierdzenie na wyniku bez rynku (t ≥ {res['tcrit']:.2f}), nie wybór")
    ws.merge_cells(start_row=1, start_column=c_dp, end_row=1, end_column=c_dp + len(dp_cols) - 1)
    for j, h in enumerate(dp_cols):
        ws.cell(2, c_dp + j, h)
    for row in ws.iter_rows(min_row=1, max_row=2):
        for cell in row:
            cell.alignment = center
            cell.font = white if cell.row == 1 else bold
            cell.fill = head if cell.row == 1 else sub
    for j in range(len(dp_cols)):
        ws.cell(2, c_dp + j).fill = dpf

    for r, it in enumerate(res["kept"], start=3):
        rule, st, dp = it["rule"], it["st"], it["dp"]
        kier = "neutralny" if isinstance(rule, NRule) else ("long" if rule.dir > 0 else "short")
        vals = [r - 2, rule.code, rule.desc, kier, st.n,
                round(st.wins / st.n * 100, 2) if st.n else None, round(st.avg, 4), round(st.total, 2),
                round(min(st.pf, 99), 2), round(st.tstat, 2), round(st.r2, 3), round(st.mdd, 2),
                st.losing, st.empty, round(st.worst, 2), f"{st.better_than_base} / {N_PERIODS}", round(st.excess, 4)]
        for j, v in enumerate(vals, start=1):
            ws.cell(r, j, v)
        for col in (6, 7, 8, 12, 15, 17):
            ws.cell(r, col).number_format = pct
        for p in range(len(pers)):
            c = c_per + 2 * p
            ws.cell(r, c, st.per_n[p]).border = sep
            cell = ws.cell(r, c + 1, round(st.per_sum[p], 2))
            cell.number_format = pct
            cell.fill = sub if st.per_n[p] < MIN_TRADES_PERIOD else (good if st.per_sum[p] >= 0 else bad)
        if dp is not None:
            raw = it.get("dp_raw")
            ok_dp = confirmed(dp, res["tcrit"])
            dv = [dp.n, round(raw.total, 2) if raw else None, round(dp.total, 2), round(dp.avg, 4), round(dp.tstat, 2),
                  dp.losing, "✓" if ok_dp else "—"]
            for j, v in enumerate(dv):
                cell = ws.cell(r, c_dp + j, v)
                if j in (1, 2, 3):
                    cell.number_format = pct
            ws.cell(r, c_dp).border = sep
            ws.cell(r, c_dp + 6).fill = good if ok_dp else bad
    ws.freeze_panes = ws.cell(3, 4)
    widths = [5, 26, 64, 9, 10, 10, 11, 11, 7, 9, 9, 12, 9, 9, 12, 11, 12]
    for j, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(j)].width = w
    for j in range(c_per, c_dp + len(dp_cols)):
        ws.column_dimensions[get_column_letter(j)].width = 9
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 45
    if res["kept"]:
        ws.auto_filter.ref = f"A2:{get_column_letter(c_dp + len(dp_cols) - 1)}{len(res['kept']) + 2}"
    return ws


def write_xlsx(path: Path, P: Panel, res: dict, neu: dict | None, meta: list[tuple[str, str]],
               pf_n: int = PF_SHEETS, pf_nn: int = PF_SHEETS_N) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    head = PatternFill("solid", fgColor="1F2A37")
    white, bold = Font(bold=True, color="FFFFFF"), Font(bold=True)
    pers = res["win"][1]
    wb = Workbook()
    wb.remove(wb.active)
    _results_sheet(wb, "WYNIKI", P, res, "Kierunkowe — 53 spółki handlowane (poszukiwanie)")
    if neu is not None:
        _results_sheet(wb, "WYNIKI NEUTRALNE", P, neu, "Neutralne wobec rynku (long k + short k) — 53 spółki handlowane")

    ok = wb.create_sheet("OKRESY")
    ok.append(["Okres", "Od", "Do", "Sesji", "Baza long: śr. wynik dnia % (53)", "Baza short: śr. wynik dnia % (53)"])
    for j in range(1, 7):
        ok.cell(1, j).font, ok.cell(1, j).fill = white, head
    for p, (a, b) in enumerate(pers):
        ok.append([p + 1, P.dates[a], P.dates[b - 1], b - a, round(res["bases"][1][p], 4), round(res["bases"][-1][p], 4)])
    for j, w in enumerate([8, 12, 12, 8, 26, 26], start=1):
        ok.column_dimensions[get_column_letter(j)].width = w

    allrows = np.concatenate([res["rows"], res["dprows"]]).astype(int)
    sheets = [(f"#{k + 1}", it, "") for k, it in enumerate(res["kept"][:pf_n])]
    sh = res.get("short")
    if sh is not None and not any(it["rule"].dir < 0 for _, it, _ in sheets):
        note = "" if sh["st"].ok else (f" · UWAGA: nie spełnia warunku {N_PERIODS} okresów ({sh['st'].why_not}) — "
                                       "najlepszy short, pokazany dla porównania")
        sheets.append(("S1", sh, note))                     # zawsze co najmniej jeden portfel short (decyzja z 14.10.2026)
    if neu is not None:
        sheets += [(f"N{k + 1}", it, "") for k, it in enumerate(neu["kept"][:pf_nn])]
    for name, it, note in sheets:
        pf = portfolio(P, it["sgn"], allrows, g0=res["win"][0])
        od.write_portfolio(wb, SimpleNamespace(id=name, desc=f"{it['rule'].code} — {it['rule'].desc} · "
                                                             f"stawka {PF_STAKE_PCT:g}% portfela na transakcję{note}"),
                           pf, len(allrows))
        it["pf"] = pf

    op = wb.create_sheet("OPIS")
    op.column_dimensions["A"].width = 34
    op.column_dimensions["B"].width = 120
    for a, b in meta:
        op.append([a, b])
        op.cell(op.max_row, 1).font = bold
        op.cell(op.max_row, 2).alignment = Alignment(wrap_text=True, vertical="top")

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ONE-DAY-SEARCH-", suffix=".xlsx", dir=str(path.parent))
    os.close(fd)
    try:
        wb.save(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def meta_rows(P: Panel, res: dict, neu: dict | None, note: str, plc: dict | None = None) -> list[tuple[str, str]]:
    p_null = sum(math.comb(N_PERIODS, k) for k in range(N_PERIODS - MAX_LOSING, N_PERIODS + 1)) / 2 ** N_PERIODS
    S, F, combos = rules()
    conf = n_confirmed(res)
    conf_n = n_confirmed(neu) if neu else 0
    tested = res["tested"] + (neu["tested"] if neu else 0)
    src = ("świece dobowe złożone ze świec 1h (ok. 2 lata)" if P.source == "1h"
           else "baza świec dobowych (sekcja 4d) — pełna historia Yahoo")
    plc_txt = "—"
    if plc:
        plc_txt = (f"to samo poszukiwanie z losowym znakiem każdego dnia (zero przewagi, ta sama zmienność i korelacja "
                   f"spółek): kierunkowe — spełnia {plc['dir']['passed']}, w arkuszu {plc['dir']['kept']}, potwierdzonych "
                   f"{plc['dir']['confirmed']}; neutralne — spełnia {plc['neu']['passed']}, w arkuszu {plc['neu']['kept']}, "
                   f"potwierdzonych {plc['neu']['confirmed']}. Wynik prawdziwy wart uwagi tylko wtedy, gdy wyraźnie "
                   "przewyższa placebo.")
    return [
        ("Poszukiwanie One-Day", f"IA 4 wersja {__version__} · instrukcja, sekcja 6d · policzono "
                                 f"{datetime.now().strftime('%Y-%m-%d %H:%M')} · {note}"),
        ("Źródło danych", src),
        ("Dane", f"{P.dates[0]} – {P.dates[-1]}; okno handlu od {P.dates[res['win'][0]]} (po rozgrzewce {WARM_Q} sesji); "
                 f"okres ≈ {len(P.dates[res['win'][0]:]) // N_PERIODS} sesji"),
        ("Transakcja", "zawsze open → close tego samego dnia (6c), stała stawka, bez kaskady, bez kosztów; "
                       "wynik transakcji = ruch open → close w kierunku pozycji w %."),
        ("Reguły kierunkowe", f"kierunek + setup ({len(S)}) + najwyżej {MAX_FILTERS} filtry z różnych grup ({len(F)}); "
                              f"reguł {res['tested']}."),
        ("Reguły neutralne (od 1.38)", "każdego dnia ranking 53 spółek wg cechy znanej przed open (10 cech); long k spółek "
                                        "z najniższą i short k z najwyższą wartością (rev) albo odwrotnie (mom), k = 3, 5, 10, "
                                        "ta sama stawka na każdą transakcję; filtr dnia: brak, SPY, dzień tygodnia; "
                                        "baza = 0 (portfel bez kierunku rynku). doubleProof: k × 20/53 (1, 2, 4)."
                                        + (f" Reguł {neu['tested']}." if neu else "")),
        ("Warunek konieczny", f"okno handlu podzielone na {N_PERIODS} równych okresów kalendarza; najwyżej {MAX_LOSING} "
                              f"okresy stratne (suma < 0) i najwyżej {MAX_EMPTY} pusty (< {MIN_TRADES_PERIOD} transakcji); "
                              f"co najmniej {MIN_TRADES} transakcji; suma > 0. Liczone na 53 spółkach handlowanych."),
        ("Spełnia warunek", f"kierunkowe {res['passed']}, neutralne {neu['passed'] if neu else '—'}; po odrzuceniu podobnych "
                            f"(wspólne transakcje ≥ {DEDUP_JACCARD:.0%}) w arkuszach: {len(res['kept'])} i "
                            f"{len(neu['kept']) if neu else '—'} (najwyżej {TOP})"),
        ("UWAGA — przypadek", f"reguła bez żadnej przewagi spełnia warunek {N_PERIODS - MAX_LOSING}/{N_PERIODS} z "
                              f"prawdopodobieństwem ok. {p_null:.1%}; przy {tested} regułach to ok. {tested * p_null:.0f} "
                              "„trafień” z przypadku. Dlatego liczą się potwierdzenie na doubleProof i placebo."),
        ("Potwierdzenie doubleProof", f"te same reguły na 20 spółkach, których poszukiwanie nie widzi, na wyniku BEZ RYNKU "
                                      "(open→close spółki − średni open→close wszystkich spółek tego dnia): suma > 0, najwyżej "
                                      f"{dp_max_losing()} okresy stratne ({DP_LOSING_SHARE:.0%} okresów) i t-stat ≥ próg Bonferroniego dla liczby reguł w "
                                      f"arkuszu (kierunkowe {res['tcrit']:.2f}, neutralne {neu['tcrit'] if neu else 0:.2f}; "
                                      f"{DP_ALPHA:.0%} szans na choćby jedno fałszywe ✓ na liście, nie mniej niż {DP_MIN_T:g}) → ✓. Potwierdzonych: "
                                      f"kierunkowe {conf} z {len(res['kept'])}, neutralne {conf_n} z "
                                      f"{len(neu['kept']) if neu else 0}. Dlaczego bez rynku: doubleProof to inne spółki, ale "
                                      "te same dni — reguła „long w dni X” potwierdzałaby się przypadkowym układem dni całego "
                                      "rynku (test na długiej historii syntetycznej: 12 fałszywych ✓ na surowym wyniku). "
                                      "Przewagę samego wyczucia rynku (które dni) sprawdzają tylko kolejne okresy i nowe dane."),
        ("Placebo (przypadek na tych danych)", plc_txt),
        ("Kolejność", "najmniej okresów stratnych, potem t-stat dziennych wyników (stałość wzrostu)."),
        ("Kolumny", "t-stat — średni dzienny wynik / odchylenie × √dni; R² — dopasowanie krzywej sumy wyników do prostej "
                    "(1 = idealnie równy wzrost; ujemne = krzywa spada); maks. obsunięcie — w sumie % transakcji; "
                    "okresy lepsze niż baza i nadwyżka nad bazą — wobec wejścia w ten sam kierunek każdego dnia "
                    "(arkusz OKRESY; dla neutralnych baza = 0)."),
        ("Arkusze PORTFEL", f"#1–#{PF_SHEETS} — najlepsze kierunkowe; S1 — najlepszy short, gdy wśród #1–#{PF_SHEETS} nie ma "
                            "żadnego (pierwszy short z listy WYNIKI, a gdy żaden short nie spełnia warunku — najlepszy short "
                            "ogółem, z uwagą w nagłówku); "
                            f"N1–N{PF_SHEETS_N} — najlepsze neutralne, na wszystkich "
                            f"73 spółkach (doubleProof „· dP”), wspólny portfel {PF_CAPITAL:,.0f} $, stawka {PF_STAKE_PCT:g}% "
                            "stanu portfela na transakcję; suma stawek dnia ≤ stan portfela (proporcjonalne zmniejszenie); "
                            "„(short)” przy spółce = pozycja krótka.".replace(",", " ")),
        ("Następny krok", "reguła z ✓ na doubleProof, wyraźnie ponad placebo, najlepiej potwierdzona na bazie dobowej "
                          "(długa historia) — kandydat do obserwacji na żywo; nic nie trafia do paper tradingu bez zgody człowieka."),
    ]


# ---------------------------------------------------------------------------
#  Dane i uruchomienie
# ---------------------------------------------------------------------------
def default_path(source: str) -> Path:
    return config.RESEARCH_DIR.parent / ("ONE-DAY-SEARCH.xlsx" if source == "1h" else "ONE-DAY-SEARCH-DAILY.xlsx")


def days_from_daily(df, since: str | None) -> od.Days:
    """Tabela bazy dobowej → od.Days; dzień ważny tylko przy spójnych cenach (l ≤ o, c ≤ h, nie płaski)."""
    if since:
        df = df[df["date"] >= since]
    o, h, l, c = (df[k].to_numpy(float) for k in ("o", "h", "l", "c"))
    tol = 1e-4
    valid = ((o > 0) & (c > 0) & (l > 0) & (h >= l) & (o <= h * (1 + tol)) & (o >= l * (1 - tol))
             & (c <= h * (1 + tol)) & (c >= l * (1 - tol)) & ~((o == h) & (h == l) & (l == c)))
    dates = df["date"].astype(str).tolist()
    return od.Days(dates, o.tolist(), h.tolist(), l.tolist(), c.tolist(), valid.tolist(), [], [], [], [])


def load_panel(source: str = "1h", no_sync: bool = False, since: str | None = None) -> tuple[Panel, str]:
    u = od.universe()
    insts = od.ordered(u)
    syms = [s for s, _ in insts]
    days, groups, spy = {}, {}, None
    if source == "1h":
        note = "bez synchronizacji (--no-sync)" if no_sync else od.maybe_sync(syms)
        from .sync import load, parquet_path
        for s, g in insts:
            if not parquet_path(s).exists():
                print(f"  ! {s}: brak kopii lokalnej — pominięta")
                continue
            dd = od.daily(load(s))
            if not dd.dates:
                continue
            if s == "SPY":
                spy = dd
            if g != "context":
                days[s], groups[s] = dd, g
        calendar = None
    else:
        from . import daily as dl
        note = "bez synchronizacji (--no-sync)"
        if not no_sync:
            try:
                r = dl.sync(quiet=True)
                note = f"baza dobowa zsynchronizowana: {r['ready']}/{r['total']} instrumentów z historią"
            except Exception as e:                              # bez sieci / bez klucza — kopia lokalna
                note = f"bez synchronizacji ({type(e).__name__}: {e})"
        have = set(dl.local_symbols())
        alld = set()
        for s, g in insts:
            if s not in have:
                print(f"  ! {s}: brak w data/daily/ — pominięta")
                continue
            dd = days_from_daily(dl.load(s), since)
            if not dd.dates:
                continue
            alld.update(dd.dates)
            if s == "SPY":
                spy = dd
            if g != "context":
                days[s], groups[s] = dd, g
        calendar = sorted(alld)
        note += f" · od {since or 'początku'}"
    if not days:
        raise SystemExit("Brak danych w kopii lokalnej — uruchom najpierw `python -m ia4.sync` "
                         "(albo `python -m ia4.daily` dla --source daily).")
    return build(days, groups, spy, calendar, source), note


def run(source: str = "1h", no_sync: bool = False, out: Path | None = None, since: str | None = None) -> Path:
    t0 = time.time()
    print(f"IA 4 — One-Day: poszukiwanie strategii stabilnych (instrukcja, sekcja 6d) — źródło: {source}\n")
    P, note = load_panel(source, no_sync, since)
    print(f"  {note}")
    print(f"  dane {P.dates[0]} – {P.dates[-1]}, {len(P.dates)} sesji, {len(P.syms)} spółek")
    res = search(P)
    neu = search_neutral(P)
    plc = placebo(P)
    print(f"  placebo (losowy znak dni): kierunkowe — spełnia {plc['dir']['passed']} · potwierdzonych "
          f"{plc['dir']['confirmed']}; neutralne — spełnia {plc['neu']['passed']} · potwierdzonych {plc['neu']['confirmed']}")
    path = write_xlsx(out or default_path(source), P, res, neu, meta_rows(P, res, neu, note, plc))
    for title, rr, n_pf in (("KIERUNKOWE", res, PF_SHEETS), ("NEUTRALNE", neu, PF_SHEETS_N)):
        print(f"\n  {title}: w arkuszu {len(rr['kept'])} · potwierdzonych na doubleProof: {n_confirmed(rr)} "
              f"(próg t {rr['tcrit']:.2f})")
        for k, it in enumerate(rr["kept"][:10], start=1):
            st, dp = it["st"], it["dp"]
            print(f"  {k:>2}. {it['rule'].code:<28} trans. {st.n:>6}  śr. {st.avg:+.3f}%  nadw. {st.excess:+.3f}%  "
                  f"stratne {st.losing}  t {st.tstat:5.2f}  dP {'✓' if confirmed(dp, rr['tcrit']) else '—'}"
                  + (f" (bez rynku: t {dp.tstat:+.2f}, {dp.total:+.1f}%)" if dp else ""))
        extra = [rr["short"]] if rr is res and rr.get("short") is not None and rr["short"] not in rr["kept"][:n_pf] else []
        if extra and extra[0].get("pf"):
            sh = extra[0]
            print(f"  SHORT S1: {sh['rule'].code} — " + ("spełnia warunek" if sh["st"].ok else
                  f"nie spełnia warunku ({sh['st'].why_not})") +
                  f"; {sh['pf']['capital']:,.0f} $ → {sh['pf']['end']:,.2f} $ ({sh['pf']['ret']:+.2f}%)".replace(",", " "))
        for k, it in enumerate(rr["kept"][:n_pf], start=1):
            pf = it.get("pf")
            if pf:
                print(f"  PORTFEL {'#' if rr is res else 'N'}{k}: {pf['capital']:,.0f} $ → {pf['end']:,.2f} $ ({pf['ret']:+.2f}%), "
                      f"obsunięcie {pf['mdd']:.2f}%, transakcji {pf['trades']}".replace(",", " "))
    print(f"\n  {time.time() - t0:.0f} s · plik: {path}")
    return path


# ---------------------------------------------------------------------------
#  Selftest
# ---------------------------------------------------------------------------
def _synth(n_stocks: int, n_days: int, seed: int, edge: float = 0.0, start: str = "2024-09-16",
           rev: float = 0.0, mkt: float = 0.0):
    """Dane syntetyczne (świece 1h → oneday.daily). edge > 0: long w poniedziałek po spadkowym piątku daje
    średnio +edge %. rev > 0: odwrócenie względne (wynik dnia −rev × wczorajszy ruch własny spółki).
    mkt > 0: wspólny ruch rynku (odchylenie mkt %) — ten sam dla wszystkich spółek."""
    import pandas as pd
    rng = np.random.default_rng(seed)
    cal = trading_days(start, "2027-12-31")[:n_days]
    mk = rng.normal(0.0, mkt, len(cal)) if mkt else np.zeros(len(cal))
    out = {}
    for s in range(n_stocks):
        p, rows, prev_dn, prev_e = 100.0, [], False, 0.0
        for t, d in enumerate(cal):
            e = rng.normal(0.0, 1.0)
            mv = mk[t] + e - rev * prev_e
            if edge and prev_dn and date.fromisoformat(d).weekday() == 0:
                mv += edge
            o = p
            c = o * (1 + mv / 100.0)
            last = 4 if d in od.US_HALF_DAYS else 7
            for sl in range(1, last + 1):
                a = o + (c - o) * (sl - 1) / last
                b = o + (c - o) * sl / last
                rows.append({"symbol": f"S{s}", "date": d, "slot": sl, "o": a, "h": max(a, b) * 1.003,
                             "l": min(a, b) * 0.997, "c": b, "v": 0})
            prev_dn, prev_e = c < o, e
            p = c * (1 + rng.normal(0, 0.002))
        out[f"S{s}"] = od.daily(pd.DataFrame(rows))
    return out


def selftest() -> None:
    fails: list[str] = []

    def check(name, ok, info=""):
        print(f"  {'OK ' if ok else 'BŁĄD'} {name}{': ' + str(info) if info != '' else ''}")
        if not ok:
            fails.append(name)

    print("IA 4 — One-Day: poszukiwanie — selftest\n")
    S, F, combos = rules()
    check("siatka", (len(S), len(F), len(combos)) == (48, 19, 174), (len(S), len(F), len(combos)))
    check("filtry z różnych grup", all(len({F[j][0].group for j in c}) == len(c) for c in combos))

    # 1. Cechy ręcznie
    o = np.array([10, 11, 10.5, 10, 9.0, 9.5, 9.0])
    c = np.array([11, 10.5, 10, 9.5, 9.5, 9.0, 9.5])
    h, l = np.maximum(o, c) + 0.1, np.minimum(o, c) - 0.1
    f = series_features(o, h, l, c)
    check("serie spadkowe", f["dn"].tolist() == [0, 1, 2, 3, 0, 1, 0], f["dn"].tolist())
    check("serie wzrostowe", f["up"].tolist() == [1, 0, 0, 0, 1, 0, 1], f["up"].tolist())
    check("położenie zamknięcia", abs(f["cl"][1] - 0.1 / 0.7) < 1e-12, round(f["cl"][1], 6))
    check("najniższe z 10 — brak przed 10 sesjami", np.isnan(f["low10"][:9]).all())
    rng = np.random.default_rng(5)
    cc = 100 * np.cumprod(1 + rng.normal(0, 0.01, 300))
    oo = cc * (1 + rng.normal(0, 0.003, 300))
    hh, ll = np.maximum(oo, cc) * 1.004, np.minimum(oo, cc) * 0.996
    fv = series_features(oo, hh, ll, cc)
    ref_low = [float(cc[q] <= cc[q - 19:q + 1].min()) for q in range(19, 300)]
    ref_nr7 = [float((hh - ll)[q] < (hh - ll)[q - 6:q].min()) for q in range(6, 300)]
    check("najniższe z 20 (wektorowo = pętla)", fv["low20"][19:].tolist() == ref_low)
    check("NR7 (wektorowo = pętla)", fv["nr7"][6:].tolist() == ref_nr7)
    check("dist20", abs(fv["dist20_r"][50] - (cc[50] / cc[31:51].mean() - 1) * 100 / fv["r"][50]) < 1e-9)

    # 2. Panel i brak zaglądania w przyszłość
    data = _synth(6, 260, seed=3)
    grp = {s: ("main" if i < 4 else "doubleProof") for i, s in enumerate(data)}
    P = build(data, grp, data["S0"])
    t = 200
    before = {k: v[:, t].copy() for k, v in P.feat.items()}
    before_spy = {k: v[t].copy() for k, v in P.spy.items()}
    data2 = _synth(6, 260, seed=3)
    for dd in data2.values():
        dd.c[t] *= 1.3
        dd.h[t] *= 1.3
    P2 = build(data2, grp, data2["S0"])
    nn = lambda a: np.nan_to_num(a, nan=-9)
    same = all(np.array_equal(nn(before[k]), nn(P2.feat[k][:, t])) for k in before)
    same &= all(np.array_equal(nn(before_spy[k]), nn(P2.spy[k][t])) for k in before_spy)
    check("cechy dnia t nie widzą świecy t", same)
    check("cechy dnia t+1 widzą świecę t", any(not np.array_equal(nn(P.feat[k][:, t + 1]), nn(P2.feat[k][:, t + 1])) for k in P.feat))
    sc_all = scores()
    v1 = [fn(P)[:, t] for _, fn in sc_all]
    v2 = [fn(P2)[:, t] for _, fn in sc_all]
    check("cechy rankingu dnia t nie widzą świecy t", all(np.array_equal(nn(a), nn(b)) for a, b in zip(v1, v2)))
    check("rozgrzewka", not P.base[:, :WARM_Q].any() and P.base[:, WARM_Q + 5:].any())
    w = periods(P, np.arange(4))
    check(f"{N_PERIODS} okresów pokrywa okno", len(w[1]) == N_PERIODS and w[1][0][0] == w[0] and w[1][-1][1] == len(P.dates))

    # 3. Ocena na ręcznej masce
    m = np.zeros_like(P.base)
    a, b = w[1][0]
    m[0, a] = m[1, a] = True
    for p in range(1, N_PERIODS):
        a, b = w[1][p]
        m[0, a:a + 3] = True
    R = np.zeros_like(P.ret)
    R[m] = 1.0
    a, b = w[1][4]
    R[0, a] = -5.0
    z = [0.0] * N_PERIODS
    n_exp = 2 + 3 * (N_PERIODS - 1)
    st = evaluate(m, R, 1, w, z)
    check("ocena: transakcji / pusty / stratny", (st.n, st.empty, st.losing) == (n_exp, 1, 1), (st.n, st.empty, st.losing))
    check("ocena: suma i najgorszy", abs(st.total - (n_exp - 6)) < 1e-9 and abs(st.worst + 3) < 1e-9, (st.total, st.worst))
    check("ocena: short odwraca", abs(evaluate(m, R, -1, w, z).total + st.total) < 1e-9)
    check("ocena: 1 stratny i 1 pusty okres → spełnia", st.ok and st.why_not == "")
    R2 = R.copy()
    for p in range(6, 6 + MAX_LOSING - 1):          # razem MAX_LOSING stratnych → nadal spełnia
        R2[0, w[1][p][0]] = -5.0
    st2 = evaluate(m, R2, 1, w, z)
    check(f"ocena: {MAX_LOSING} stratne okresy → spełnia", st2.ok and st2.losing == MAX_LOSING, st2.losing)
    R2[0, w[1][6 + MAX_LOSING - 1][0]] = -5.0       # o jeden więcej
    st3 = evaluate(m, R2, 1, w, z)
    check(f"ocena: {MAX_LOSING + 1} stratne okresy → nie spełnia (z powodem)", not st3.ok and "stratne" in st3.why_not, st3.why_not)
    check("próg Bonferroniego", abs(t_crit(200) - 3.4808) < 1e-3 and t_crit(1) == DP_MIN_T, round(t_crit(200), 4))
    check("ocena: nadwyżka nad bazą", abs(evaluate(m, R, 1, w, [0.5] * N_PERIODS).excess - (st.avg - 0.5)) < 1e-12)

    # 4. Ranking neutralny
    sc = np.array([[3.0, 1, np.nan], [1.0, 2, 5], [2.0, 3, 4], [0.0, np.nan, 3]])
    rk = rank_masks(sc, np.ones_like(sc, bool), [1, 2])
    lo1, hi1 = rk[1]
    check("ranking: k=1 najniższa / najwyższa", lo1[:, 0].tolist() == [False, False, False, True] and
          hi1[:, 0].tolist() == [True, False, False, False])
    lo2, hi2 = rk[2]
    check("ranking: k=2 tylko dni z ≥ 4 wynikami", lo2[:, 0].sum() == 2 and not lo2[:, 1].any() and not lo2[:, 2].any())
    check("ranking: nogi rozłączne", not (lo2 & hi2).any())

    # 5. Kierunkowa: zaszyta przewaga zostaje znaleziona i potwierdzona; szum — mało trafień
    data = _synth(30, 520, seed=11, edge=1.5)
    groups = {s: ("main" if i < 22 else "doubleProof") for i, s in enumerate(data)}
    P = build(data, groups, data["S0"])
    t0 = time.time()
    res = search(P, log=lambda *_: None)
    top = [it["rule"].code for it in res["kept"][:5]]
    check("zaszyta przewaga w pierwszej piątce", any(c.startswith("L|dn1") and "pon" in c for c in top), top)
    best = next((it for it in res["kept"] if it["rule"].code.startswith("L|dn1") and "pon" in it["rule"].code), None)
    check("przewaga potwierdzona na doubleProof", best is not None and confirmed(best["dp"], res["tcrit"]),
          (round(best["dp"].tstat, 2), round(res["tcrit"], 2)) if best else None)
    check("czas poszukiwania", time.time() - t0 < 120, f"{time.time() - t0:.0f} s, reguł {res['tested']}")
    plc = placebo(P)
    real_conf = n_confirmed(res)
    check("placebo: przewaga znika (potwierdzonych ≤ 2, prawdziwych ≥ 5 razy więcej)",
          plc["dir"]["confirmed"] <= 2 and real_conf >= 5 * max(1, plc["dir"]["confirmed"]), f"placebo {plc['dir']}, prawdziwe {real_conf}")
    noise = search(build(_synth(30, 520, seed=12), groups, None), log=lambda *_: None)
    rate = noise["passed"] / max(1, noise["tested"])
    check("szum: odsetek trafień z przypadku < 3%", rate < 0.03, f"{noise['passed']} z {noise['tested']} ({rate:.2%})")
    conf_noise = n_confirmed(noise)
    check("szum: 0 potwierdzonych na doubleProof", conf_noise == 0, f"w arkuszu {len(noise['kept'])}, potwierdzonych {conf_noise}")

    # 6. Neutralna: odwrócenie względne przy silnym rynku; szum z rynkiem — bez potwierdzeń
    dn = _synth(40, 520, seed=21, rev=0.25, mkt=1.5)
    gn = {s: ("main" if i < 28 else "doubleProof") for i, s in enumerate(dn)}
    Pn = build(dn, gn, dn["S0"])
    neu = search_neutral(Pn, log=lambda *_: None)
    topn = [it["rule"].code for it in neu["kept"][:5]]
    hit = next((it for it in neu["kept"][:5] if it["rule"].code.startswith("N|rev|") and
                it["rule"].score.code in ("body", "chg1", "rel1")), None)
    check("neutralne: odwrócenie w pierwszej piątce", hit is not None, topn)
    check("neutralne: potwierdzone na doubleProof", hit is not None and confirmed(hit["dp"], neu["tcrit"]),
          (round(hit["dp"].tstat, 2) if hit else None))
    sg = hit["sgn"] if hit else np.zeros((1, 1))
    check("neutralne: tyle samo long i short każdego dnia", hit is not None and
          np.array_equal((sg[neu["rows"]] > 0).sum(0), (sg[neu["rows"]] < 0).sum(0)))
    plc_n = placebo(Pn)["neu"]
    check("neutralne placebo: ≤ 1 potwierdzona", plc_n["confirmed"] <= 1, plc_n)
    nz = search_neutral(build(_synth(40, 520, seed=22, mkt=1.5), gn, None), log=lambda *_: None)
    cz = n_confirmed(nz)
    check("neutralne szum z rynkiem: ≤ 1 potwierdzona", cz <= 1, f"spełnia {nz['passed']} z {nz['tested']}, potwierdzonych {cz}")

    # 7. Portfel: stała stawka, suma dnia ≤ stan portfela, short ze znakiem
    rows = np.concatenate([neu["rows"], neu["dprows"]]).astype(int)
    pf = portfolio(Pn, hit["sgn"], rows, g0=neu["win"][0]) if hit else None
    ok_pf = pf is not None and abs(pf["end"] - PF_CAPITAL - sum(r["pnl"] for r in pf["rows"])) < 1e-6
    check("portfel neutralny: stan = start + suma wyników", ok_pf)
    by_day, eq, ok_cap = {}, PF_CAPITAL, True
    for r in (pf["rows"] if pf else []):
        by_day.setdefault(r["day"], []).append(r)
    for d in sorted(by_day):
        ok_cap &= sum(r["stake"] for r in by_day[d]) <= eq + 1e-6
        eq += sum(r["pnl"] for r in by_day[d])
    check("portfel: suma stawek dnia ≤ stan portfela", ok_cap)
    check("portfel: transakcje short oznaczone", pf is not None and any("(short)" in r["sym"] for r in pf["rows"]))
    check("portfel: transakcje = sygnały w oknie", pf is not None and
          pf["trades"] == int((hit["sgn"][rows][:, neu["win"][0]:] != 0).sum()))

    # 8. Baza dobowa: kalendarz z danych, odrzucanie niespójnych dni
    import pandas as pd
    df = pd.DataFrame({"date": ["1989-12-29", "1990-01-02", "1990-01-03", "1990-01-04", "1990-01-05"],
                       "o": [10, 10, 10, 10, 12], "h": [11, 11, 10, 9, 13], "l": [9, 9, 10, 8, 11],
                       "c": [10.5, 10.5, 10, 8.5, 12.5], "v": [1] * 5})
    dd = days_from_daily(df, "1990-01-01")
    check("baza dobowa: od daty", dd.dates[0] == "1990-01-02" and len(dd.dates) == 4)
    check("baza dobowa: płaski dzień i open poza zakresem odrzucone", dd.valid == [True, False, False, True], dd.valid)
    Pd = build({"A": dd}, {"A": "main"}, None, calendar=dd.dates, source="daily")
    check("baza dobowa: kalendarz z danych", Pd.dates == dd.dates and Pd.valid[0].tolist() == [True, False, False, True])
    from . import daily as dl
    y1 = dl.parse_year({"d": ["2020-01-02", "2020-01-03"], "o": [1, 2], "h": [1, 2], "l": [1, 2], "c": [1, 2], "v": [5]})
    check("baza dobowa: dokument roku (v krótsze → 0)", y1["v"].tolist() == [5, 0] and len(y1) == 2)
    old = pd.DataFrame({"date": ["2019-12-31", "2020-01-02"], "o": [9, 9], "h": [9, 9], "l": [9, 9], "c": [9, 9], "v": [0, 0]})
    mg = dl.merge_years(old, {2020: y1})
    check("baza dobowa: rok zastąpiony w całości", mg["date"].tolist() == ["2019-12-31", "2020-01-02", "2020-01-03"]
          and mg["c"].tolist() == [9, 1, 2])

    # 9. Excel
    out = Path(tempfile.mkdtemp()) / "s.xlsx"
    write_xlsx(out, P, res, neu, meta_rows(P, res, neu, "selftest"))
    from openpyxl import load_workbook
    wb = load_workbook(out)
    check("Excel: arkusze (z portfelem short S1)", wb.sheetnames == ["WYNIKI", "WYNIKI NEUTRALNE", "OKRESY", "PORTFEL #1",
                                              "PORTFEL #2", "PORTFEL #3", "PORTFEL S1", "PORTFEL N1", "PORTFEL N2", "OPIS"],
          wb.sheetnames)
    s1 = wb["PORTFEL S1"]
    check("Excel: S1 to short", res["short"]["rule"].dir < 0 and all("(short)" in str(s1.cell(r, 3).value)
                                                                     for r in range(7, min(s1.max_row, 50) + 1)))
    check("Excel: wiersze WYNIKI", wb["WYNIKI"].max_row == 2 + len(res["kept"]), wb["WYNIKI"].max_row)
    check("Excel: kod pierwszej reguły neutralnej", wb["WYNIKI NEUTRALNE"].cell(3, 2).value == neu["kept"][0]["rule"].code)

    print("\nWYNIK:", "OK" if not fails else f"BŁĘDY ({len(fails)}): " + ", ".join(fails))
    sys.exit(0 if not fails else 1)


def main() -> None:
    global N_PERIODS, MAX_LOSING
    ap = argparse.ArgumentParser(description="IA 4 — One-Day: poszukiwanie strategii stabilnych (instrukcja, 6d)")
    ap.add_argument("--source", choices=["1h", "daily"], default="1h",
                    help="1h — świece dobowe ze świec 1h (ok. 2 lata); daily — baza dobowa (sekcja 4d)")
    ap.add_argument("--since", default=None, help=f"daily: od daty (domyślnie {DAILY_SINCE})")
    ap.add_argument("--no-sync", action="store_true", help="bez synchronizacji z Firestore")
    ap.add_argument("--out", type=Path, help="ścieżka pliku (domyślnie ~/Desktop/IA4/ONE-DAY-SEARCH[-DAILY].xlsx)")
    ap.add_argument("--periods", type=int, default=N_PERIODS, help=f"liczba okresów (domyślnie {N_PERIODS})")
    ap.add_argument("--max-losing", type=int, default=MAX_LOSING, help=f"najwyżej tyle okresów stratnych (domyślnie {MAX_LOSING})")
    ap.add_argument("--selftest", action="store_true", help="test na danych syntetycznych")
    a = ap.parse_args()
    N_PERIODS = max(2, a.periods)
    MAX_LOSING = max(0, min(a.max_losing, N_PERIODS - 1))
    if a.selftest:
        selftest()
    else:
        since = a.since if a.since else (DAILY_SINCE if a.source == "daily" else None)
        run(source=a.source, no_sync=a.no_sync, out=a.out, since=since)


if __name__ == "__main__":
    main()
