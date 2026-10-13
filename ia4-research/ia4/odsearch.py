"""
IA 4 — One-Day: poszukiwanie strategii stabilnych (instrukcja, sekcja 6d).
Wersja projektu: 1.37 (2026-10-13) — musi zgadzać się z IA4_INSTRUKCJA.md

Szuka reguł wejścia na świecach dobowych, które rosną konsekwentnie, a nie tylko „na koniec”.
Żelazna zasada z 6c zostaje: wejście na open dnia, wyjście na close tego samego dnia, stała stawka
(bez kaskady), bez kosztów.

- Reguła = kierunek + jeden setup (stan wczorajszej świecy / serii) + najwyżej 2 filtry (trend, rynek,
  zmienność, dzień tygodnia). Wszystko, co reguła widzi, jest znane przed open dnia wejścia (zamknięcie
  poprzedniej pełnej sesji, data) — bez luki na otwarciu.
- Poszukiwanie widzi tylko 53 spółki handlowane. Okno handlu (po rozgrzewce) podzielone na 10 równych
  okresów kalendarza. Warunek konieczny: najwyżej 1 okres stratny (suma wyników transakcji < 0),
  najwyżej 1 okres „pusty” (< 3 transakcji), co najmniej 50 transakcji, suma > 0.
- doubleProof (20 spółek) — tylko potwierdzenie przyjętych reguł, nigdy wybór (6a).
- Wynik: ~/Desktop/IA4/ONE-DAY-SEARCH.xlsx (poza gitem): WYNIKI, OKRESY, PORTFEL dla 3 najlepszych, OPIS.

    python -m ia4.odsearch              # synchronizacja (gdy nie działa `ia4 start`), poszukiwanie, plik
    python -m ia4.odsearch --no-sync
    python -m ia4.odsearch --selftest   # „WYNIK: OK”
"""

from __future__ import annotations

import argparse
import itertools
import math
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from . import __version__, config
from . import oneday as od
from .lab.check import trading_days

# ---------------------------------------------------------------------------
#  Parametry (instrukcja 6d — zmiana tylko razem z instrukcją)
# ---------------------------------------------------------------------------
N_PERIODS = 10
MAX_LOSING = 1            # okresów stratnych (suma < 0) najwyżej
MAX_EMPTY = 1             # okresów pustych (< MIN_TRADES_PERIOD transakcji) najwyżej
MIN_TRADES_PERIOD = 3
MIN_TRADES = 50
MAX_FILTERS = 2
WARM_Q = 105              # rozgrzewka: pełnych sesji instrumentu (SMA100 + 5)
DEDUP_JACCARD = 0.7       # reguła podobna (wspólne transakcje ≥ 70%) do lepszej → pominięta
TOP = 200                 # najwyżej tyle reguł w arkuszu WYNIKI
DP_MAX_LOSING = 2         # potwierdzenie na doubleProof: suma > 0, najwyżej 2 okresy stratne
DP_MIN_T = 2.5            # … i t-stat dziennych wyników ≥ 2,5 (kalibracja na szumie: 0 fałszywych w 4 próbach)
PLACEBO_SEED = 2026       # placebo: losowy znak każdego dnia (ten sam dla wszystkich spółek)
PF_CAPITAL = 10_000.0     # arkusze PORTFEL: wspólny portfel, stawka 5% stanu portfela na transakcję
PF_STAKE_PCT = 5.0
PF_SHEETS = 3
R_DAYS = od.R_DAYS        # r — jak w 6c

DOW = ["pon", "wt", "śr", "czw", "pt"]


# ---------------------------------------------------------------------------
#  Panel świec dobowych na wspólnym kalendarzu NYSE
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


def build(days: dict[str, od.Days], groups: dict[str, str], spy: od.Days | None) -> Panel:
    """Świece dobowe instrumentów (oneday.daily) → tablice S×T na wspólnym kalendarzu."""
    syms = list(days)
    first = min(d.dates[0] for d in days.values())
    last = max(d.dates[-1] for d in days.values())
    cal = trading_days(first, last)
    pos = {d: i for i, d in enumerate(cal)}
    S, T = len(syms), len(cal)
    nan = np.full((S, T), np.nan)
    P = Panel(syms, [groups[s] for s in syms], cal, nan.copy(), nan.copy(), nan.copy(), nan.copy(),
              np.zeros((S, T), bool), np.zeros((S, T)))
    for i, s in enumerate(syms):
        dd = days[s]
        for j, d in enumerate(dd.dates):
            t = pos[d]
            if dd.valid[j]:
                P.o[i, t], P.h[i, t], P.l[i, t], P.c[i, t] = dd.o[j], dd.h[j], dd.l[j], dd.c[j]
                P.valid[i, t] = True
    P.ret = np.where(P.valid, (P.c / np.where(P.valid, P.o, 1.0) - 1.0) * 100.0, 0.0)
    _features(P)
    _spy(P, spy)
    return P


def _rsi(c: np.ndarray, n: int = 2) -> np.ndarray:
    """RSI Wildera z zamknięć (jak 8.2 w duchu; tu na świecach dobowych)."""
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


def series_features(o, h, l, c) -> dict[str, np.ndarray]:
    """Cechy na końcu każdej pełnej sesji q (ciąg pełnych sesji jednego instrumentu)."""
    Q = len(c)
    f: dict[str, np.ndarray] = {}
    col = np.sign(c - o)
    dn, up = np.zeros(Q), np.zeros(Q)
    for q in range(Q):
        dn[q] = dn[q - 1] + 1 if col[q] < 0 and q else (1 if col[q] < 0 else 0)
        up[q] = up[q - 1] + 1 if col[q] > 0 and q else (1 if col[q] > 0 else 0)
    f["dn"], f["up"] = dn, up
    rng = (h - l) / o * 100.0
    r = _sma(rng, R_DAYS)                                 # r na końcu sesji q: sesje q−19 … q
    f["r"] = r
    f["body_r"] = (c - o) / o * 100.0 / r
    for M in (3, 5, 10):
        chg = np.full(Q, np.nan)
        chg[M:] = (c[M:] / c[:-M] - 1.0) * 100.0
        f[f"chg{M}_r"] = chg / r
    hl = h - l
    f["cl"] = np.where(hl > 0, (c - l) / np.where(hl > 0, hl, 1.0), 0.5)
    f["rsi2"] = _rsi(c, 2)
    for n in (10, 20):
        lo, hi = np.full(Q, np.nan), np.full(Q, np.nan)
        for q in range(n - 1, Q):
            w = c[q - n + 1:q + 1]
            lo[q] = float(c[q] <= w.min())
            hi[q] = float(c[q] >= w.max())
        f[f"low{n}"], f[f"high{n}"] = lo, hi
    nr7 = np.full(Q, np.nan)
    for q in range(6, Q):
        nr7[q] = float(hl[q] < hl[q - 6:q].min())
    f["nr7"] = nr7
    for n in (20, 50, 100):
        f[f"above{n}"] = np.where(np.isnan(_sma(c, n)), np.nan, (c > _sma(c, n)).astype(float))
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


def _place(P: Panel, i: int, f: dict[str, np.ndarray]) -> np.ndarray:
    """Cecha z końca sesji q → dzień t = q+1 w kalendarzu (tylko gdy t−1 jest tą sesją)."""
    vi = np.flatnonzero(P.valid[i])
    tgt = vi + 1
    keep = tgt < len(P.dates)
    return vi[keep], tgt[keep]


def _features(P: Panel) -> None:
    S, T = P.o.shape
    P.base = np.zeros((S, T), bool)
    for i in range(S):
        vi = np.flatnonzero(P.valid[i])
        if len(vi) == 0:
            continue
        f = series_features(P.o[i, vi], P.h[i, vi], P.l[i, vi], P.c[i, vi])
        src, tgt = _place(P, i, f)
        qi = np.arange(len(src))                       # numer pełnej sesji (q) dla src
        for k, v in f.items():
            if k not in P.feat:
                P.feat[k] = np.full((S, T), np.nan)
            P.feat[k][i, tgt] = v[qi]
        warm = qi >= WARM_Q - 1                         # ≥ WARM_Q pełnych sesji przed dniem t
        P.base[i, tgt] = warm & P.valid[i, tgt]


def _spy(P: Panel, spy: od.Days | None) -> None:
    T = len(P.dates)
    P.spy = {"above50": np.full(T, np.nan), "down": np.full(T, np.nan)}
    if spy is None:
        return
    pos = {d: i for i, d in enumerate(P.dates)}
    vi = [j for j, v in enumerate(spy.valid) if v]
    o, h, l, c = (np.array([getattr(spy, k)[j] for j in vi]) for k in ("o", "h", "l", "c"))
    a50 = _sma(c, 50)
    for q, j in enumerate(vi):
        t = pos.get(spy.dates[j])
        if t is None or t + 1 >= T:
            continue
        P.spy["above50"][t + 1] = np.nan if np.isnan(a50[q]) else float(c[q] > a50[q])
        P.spy["down"][t + 1] = float(c[q] < o[q])


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
    out.append((Cond("spy>50", "SPY > SMA50", "m"), lambda P: np.broadcast_to(_gt(P.spy["above50"], 1), P.base.shape)))
    out.append((Cond("spy<50", "SPY < SMA50", "m"),
                lambda P: np.broadcast_to(_lt(np.nan_to_num(P.spy["above50"], nan=1), 0), P.base.shape)))
    out.append((Cond("spy_dn", "SPY wczoraj spadkowa", "md"), lambda P: np.broadcast_to(_gt(P.spy["down"], 1), P.base.shape)))
    out.append((Cond("spy_up", "SPY wczoraj wzrostowa", "md"),
                lambda P: np.broadcast_to(_lt(np.nan_to_num(P.spy["down"], nan=1), 0), P.base.shape)))
    out.append((Cond("vol+", "zmienność wysoka (r > średnia r z 60 sesji)", "v"), lambda P: _gt(P.feat["volhi"], 1)))
    out.append((Cond("vol-", "zmienność niska (r ≤ średnia r z 60 sesji)", "v"),
                lambda P: _lt(np.nan_to_num(P.feat["volhi"], nan=1), 0)))
    for k, name in enumerate(DOW):
        out.append((Cond(name, f"dzień: {name}", "dow"),
                    lambda P, k=k: np.broadcast_to(np.array([date.fromisoformat(d).weekday() == k for d in P.dates]),
                                                   P.base.shape)))
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
    def ok(self) -> bool:
        return (self.n >= MIN_TRADES and self.losing <= MAX_LOSING and self.empty <= MAX_EMPTY
                and self.total > 0)


def evaluate(m: np.ndarray, R: np.ndarray, d: int, win: tuple[int, list], base_avg: list[float]) -> Stats:
    """m — transakcje (S×T, bool), R — wyniki open→close %, d — kierunek; wyniki tylko w oknie."""
    g0, pers = win
    x = np.where(m, R * d, 0.0)
    daily = x.sum(axis=0)[g0:]
    dn = m.sum(axis=0)[g0:]
    n = int(dn.sum())
    pos = float(np.clip(x, 0, None)[:, g0:].sum())
    neg = float(-np.clip(x, None, 0)[:, g0:].sum())
    wins = int(((x > 0) & m)[:, g0:].sum())
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
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))
    mdd = float((peak - np.concatenate([[0.0], cum])).max())
    worst = min((s for k, s in zip(per_n, per_sum) if k >= MIN_TRADES_PERIOD), default=0.0)
    excess = (total - sum(k * b for k, b in zip(per_n, base_avg))) / n if n else 0.0
    return Stats(n, wins, total, total / n if n else 0.0, (pos / neg if neg > 0 else (99.0 if pos > 0 else 0.0)),
                 tstat, r2, mdd, per_n, per_sum, losing, empty, worst, better, excess)


def base_avgs(P: Panel, rows: np.ndarray, d: int, win, R: np.ndarray | None = None) -> list[float]:
    """Punkt odniesienia: ten sam kierunek każdego dnia — średni wynik transakcji w każdym okresie."""
    A = P.base[rows]
    x = np.where(A, (P.ret if R is None else R)[rows] * d, 0.0)
    out = []
    for a, b in win[1]:
        k = A[:, a:b].sum()
        out.append(float(x[:, a:b].sum() / k) if k else 0.0)
    return out


def search(P: Panel, log=print, sign: np.ndarray | None = None) -> dict:
    """Pełne przeszukanie siatki reguł na 53 spółkach handlowanych; potwierdzenie na doubleProof.
    sign — placebo: wyniki dnia t pomnożone przez sign[t] (±1), cechy bez zmian."""
    rows = np.array([i for i, g in enumerate(P.groups) if g in ("main", "proof")])
    dprows = np.array([i for i, g in enumerate(P.groups) if g == "doubleProof"])
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
    t0 = time.time()
    for si, (sc, _) in enumerate(S):
        sm = smask[si][rows] & Am
        for cmb in combos:
            m = sm
            for j in cmb:
                m = m & fmask[j][rows]
            if m.sum() < MIN_TRADES:
                tested += 2
                continue
            for d in (1, -1):
                tested += 1
                st = evaluate(m, Rm, d, win, bases[d])
                if st.ok:
                    passed.append((Rule(d, sc, tuple(F[j][0] for j in cmb)), st, si, cmb))
    log(f"  reguł sprawdzonych: {tested} · spełnia warunek 10 okresów: {len(passed)} · {time.time() - t0:.0f} s")
    passed.sort(key=lambda x: (x[1].losing, -x[1].tstat))

    def full_mask(si, cmb):
        m = smask[si] & A
        for j in cmb:
            m = m & fmask[j]
        return m

    kept, kept_masks = [], []
    for rule, st, si, cmb in passed:
        mm = full_mask(si, cmb)[rows]
        a = mm.sum()
        dup = False
        for km in kept_masks:
            inter = (mm & km).sum()
            if inter / (a + km.sum() - inter) >= DEDUP_JACCARD:
                dup = True
                break
        if dup:
            continue
        kept.append((rule, st, si, cmb))
        kept_masks.append(mm)
        if len(kept) >= TOP:
            break
    out = []
    for rule, st, si, cmb in kept:
        dp = None
        if win_dp is not None:
            mdp = full_mask(si, cmb)[dprows]
            dp = evaluate(mdp, R[dprows], rule.dir, win_dp, base_avgs(P, dprows, rule.dir, win_dp, R))
        out.append({"rule": rule, "st": st, "dp": dp, "mask": full_mask(si, cmb)})
    return {"tested": tested, "passed": len(passed), "kept": out, "win": win, "win_dp": win_dp,
            "bases": bases, "rows": rows, "dprows": dprows}


def confirmed(dp: Stats | None) -> bool:
    return (dp is not None and dp.n > 0 and dp.total > 0 and dp.losing <= DP_MAX_LOSING
            and dp.tstat >= DP_MIN_T)


def placebo(P: Panel) -> dict:
    """To samo poszukiwanie z losowym znakiem każdego dnia: ile reguł przechodzi z czystego przypadku
    na tych danych (ta sama zmienność, ta sama korelacja spółek, zero przewagi)."""
    sign = np.random.default_rng(PLACEBO_SEED).choice([-1.0, 1.0], size=len(P.dates))
    r = search(P, log=lambda *_: None, sign=sign)
    return {"passed": r["passed"], "kept": len(r["kept"]), "confirmed": sum(confirmed(it["dp"]) for it in r["kept"])}


# ---------------------------------------------------------------------------
#  Portfel 10 000 $ (stała stawka 5% stanu portfela, suma dnia ≤ stan portfela)
# ---------------------------------------------------------------------------
def portfolio(P: Panel, m: np.ndarray, d: int, rows: np.ndarray, capital: float = PF_CAPITAL, g0: int = 0) -> dict:
    eq = peak = capital
    mdd, ruined = 0.0, False
    out, n_scaled, trades, wins = [], 0, 0, 0
    tag = {"doubleProof": " · dP"}
    streak = P.feat["dn" if d > 0 else "up"]
    for t in range(g0, m.shape[1]):
        idx = [i for i in rows if m[i, t]]
        if not idx:
            continue
        e0 = eq
        stake0 = e0 * PF_STAKE_PCT / 100.0
        total = stake0 * len(idx)
        scale = min(1.0, e0 / total)
        n_scaled += scale < 1.0
        for i in idx:
            stake = stake0 * scale
            pct = d * P.ret[i, t]
            pnl = stake * pct / 100.0
            eq += pnl
            trades += 1
            wins += pnl > 0
            s = streak[i, t]
            out.append({"day": P.dates[t], "sym": P.syms[i] + tag.get(P.groups[i], ""),
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
def write_xlsx(path: Path, P: Panel, res: dict, meta: list[tuple[str, str]], pf_n: int = PF_SHEETS) -> Path:
    from openpyxl import Workbook
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

    wb = Workbook()
    ws = wb.active
    ws.title = "WYNIKI"
    fixed = ["Nr", "Kod reguły", "Opis", "Kierunek", "Transakcji", "Zyskownych %", "Śr. wynik transakcji %",
             "Suma wyników %", "PF", "t-stat (dni)", "R² krzywej", "Maks. obsunięcie (suma %)",
             "Okresy stratne", "Okresy puste", "Najgorszy okres (suma %)", "Okresy lepsze niż baza",
             "Nadwyżka nad bazą (śr. % na transakcję)"]
    dp_cols = ["dP transakcji", "dP suma %", "dP śr. %", "dP t-stat", "dP okresy stratne", "dP potwierdzona"]
    c_per = len(fixed) + 1
    c_dp = c_per + 2 * len(pers)
    for j, h in enumerate(fixed, start=1):
        ws.cell(1, j, "53 spółki handlowane — poszukiwanie" if j == 1 else None)
        ws.cell(2, j, h)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(fixed))
    for p, (a, b) in enumerate(pers):
        c = c_per + 2 * p
        ws.cell(1, c, f"Okres {p + 1}: {P.dates[a]} – {P.dates[b - 1]}")
        ws.merge_cells(start_row=1, start_column=c, end_row=1, end_column=c + 1)
        ws.cell(2, c, "transakcji")
        ws.cell(2, c + 1, "suma %")
    ws.cell(1, c_dp, "doubleProof (20 spółek) — potwierdzenie, nie wybór")
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
        vals = [r - 2, rule.code, rule.desc, "long" if rule.dir > 0 else "short", st.n,
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
            if st.per_n[p] < MIN_TRADES_PERIOD:
                cell.fill = sub
            else:
                cell.fill = good if st.per_sum[p] >= 0 else bad
        if dp is not None:
            dv = [dp.n, round(dp.total, 2), round(dp.avg, 4), round(dp.tstat, 2), dp.losing, "✓" if confirmed(dp) else "—"]
            for j, v in enumerate(dv):
                cell = ws.cell(r, c_dp + j, v)
                if j in (1, 2):
                    cell.number_format = pct
            ws.cell(r, c_dp).border = sep
            ws.cell(r, c_dp + 5).fill = good if confirmed(dp) else bad
    ws.freeze_panes = ws.cell(3, 4)
    widths = [5, 26, 64, 8, 10, 10, 11, 11, 7, 9, 9, 12, 9, 9, 12, 11, 12]
    for j, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(j)].width = w
    for j in range(c_per, c_dp + len(dp_cols)):
        ws.column_dimensions[get_column_letter(j)].width = 9
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 45
    if res["kept"]:
        ws.auto_filter.ref = f"A2:{get_column_letter(c_dp + len(dp_cols) - 1)}{len(res['kept']) + 2}"

    ok = wb.create_sheet("OKRESY")
    ok.append(["Okres", "Od", "Do", "Sesji", "Baza long: śr. wynik dnia % (53)", "Baza short: śr. wynik dnia % (53)"])
    for j in range(1, 7):
        ok.cell(1, j).font, ok.cell(1, j).fill = white, head
    for p, (a, b) in enumerate(pers):
        ok.append([p + 1, P.dates[a], P.dates[b - 1], b - a, round(res["bases"][1][p], 4), round(res["bases"][-1][p], 4)])
    for j, w in enumerate([8, 12, 12, 8, 26, 26], start=1):
        ok.column_dimensions[get_column_letter(j)].width = w

    for k, it in enumerate(res["kept"][:pf_n]):
        rows = np.concatenate([res["rows"], res["dprows"]]).astype(int)
        pf = portfolio(P, it["mask"], it["rule"].dir, rows, g0=res["win"][0])
        od.write_portfolio(wb, SimpleNamespace(id=f"#{k + 1}", desc=f"{it['rule'].code} — {it['rule'].desc} · "
                                                                        f"stawka {PF_STAKE_PCT:g}% portfela"),
                           pf, len(rows))
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
    import os
    os.close(fd)
    try:
        wb.save(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def meta_rows(P: Panel, res: dict, note: str, plc: dict | None = None) -> list[tuple[str, str]]:
    p_null = sum(math.comb(N_PERIODS, k) for k in range(N_PERIODS - MAX_LOSING, N_PERIODS + 1)) / 2 ** N_PERIODS
    S, F, combos = rules()
    conf = sum(confirmed(it["dp"]) for it in res["kept"])
    return [
        ("Poszukiwanie One-Day", f"IA 4 wersja {__version__} · instrukcja, sekcja 6d · policzono "
                                 f"{datetime.now().strftime('%Y-%m-%d %H:%M')} · {note}"),
        ("Dane", f"{P.dates[0]} – {P.dates[-1]}; okno handlu od {P.dates[res['win'][0]]} (po rozgrzewce {WARM_Q} sesji)"),
        ("Transakcja", "zawsze open → close tego samego dnia (6c), stała stawka, bez kaskady, bez kosztów; "
                       "wynik transakcji = ruch open → close w kierunku pozycji w %."),
        ("Reguła", f"kierunek + setup ({len(S)}) + najwyżej {MAX_FILTERS} filtry z różnych grup ({len(F)}); "
                   "wszystko znane przed open dnia wejścia (świece do wczoraj, data), bez luki na otwarciu."),
        ("Warunek konieczny", f"okno handlu podzielone na {N_PERIODS} równych okresów kalendarza; najwyżej {MAX_LOSING} "
                              f"okres stratny (suma < 0) i najwyżej {MAX_EMPTY} pusty (< {MIN_TRADES_PERIOD} transakcji); "
                              f"co najmniej {MIN_TRADES} transakcji; suma > 0. Liczone na 53 spółkach handlowanych."),
        ("Reguł sprawdzonych", str(res["tested"])),
        ("Spełnia warunek", f"{res['passed']} — z tego po odrzuceniu podobnych (wspólne transakcje ≥ "
                            f"{DEDUP_JACCARD:.0%}) w arkuszu WYNIKI: {len(res['kept'])} (najwyżej {TOP})"),
        ("UWAGA — przypadek", f"reguła bez żadnej przewagi spełnia warunek {N_PERIODS - MAX_LOSING}/{N_PERIODS} z "
                              f"prawdopodobieństwem ok. {p_null:.1%}; przy {res['tested']} regułach to ok. "
                              f"{res['tested'] * p_null:.0f} „trafień” z przypadku (mniej, bo reguły są do siebie podobne, "
                              "ale też więcej w hossie dla long). Dlatego liczy się potwierdzenie na doubleProof."),
        ("Potwierdzenie doubleProof", f"te same reguły na 20 spółkach, których poszukiwanie nie widzi: suma > 0, t-stat ≥ "
                                      f"{DP_MIN_T:g} i najwyżej {DP_MAX_LOSING} okresy stratne → ✓. Potwierdzonych: {conf} z "
                                      f"{len(res['kept'])}. Próg skalibrowany na danych syntetycznych: na czystym szumie 0 "
                                      "potwierdzeń w 4 próbach, przewaga +0,4% na transakcję wykryta (t ≈ 4,6)."),
        ("Placebo (przypadek na tych danych)", "—" if plc is None else
            f"to samo poszukiwanie z losowym znakiem każdego dnia (zero przewagi, ta sama zmienność i korelacja spółek): "
            f"warunek 10 okresów spełnia {plc['passed']} reguł, w arkuszu byłoby {plc['kept']}, potwierdzonych na "
            f"doubleProof {plc['confirmed']}. Wynik prawdziwy wart uwagi tylko wtedy, gdy wyraźnie przewyższa placebo."),
        ("Kolejność", "najmniej okresów stratnych, potem t-stat dziennych wyników (stałość wzrostu)."),
        ("Kolumny", "t-stat — średni dzienny wynik / odchylenie × √dni (im wyżej, tym równiej rośnie); R² — "
                    "dopasowanie krzywej sumy wyników do prostej (1 = idealnie równy wzrost; ujemne = krzywa spada); "
                    "maks. obsunięcie — w sumie % transakcji; okresy lepsze niż baza — średni wynik transakcji wyższy "
                    "niż wejście w ten sam kierunek każdego dnia (arkusz OKRESY); nadwyżka nad bazą — o ile średnia "
                    "transakcja reguły jest lepsza od takiego wejścia (≈ 0 = reguła tylko płynie z rynkiem; L|all i S|all "
                    "to sama baza)."),
        ("Arkusze PORTFEL", f"{PF_SHEETS} najlepsze reguły na wszystkich 73 spółkach (z doubleProof, „· dP”), wspólny portfel "
                            f"{PF_CAPITAL:,.0f} $, stawka {PF_STAKE_PCT:g}% stanu portfela na transakcję; suma stawek dnia ≤ stan "
                            "portfela (proporcjonalne zmniejszenie); „Świeca w serii” = liczba świec spadkowych (long) albo "
                            "wzrostowych (short) przed dniem + 1.".replace(",", " ")),
        ("Następny krok", "reguła z ✓ na doubleProof i ≥ 7/10 okresów lepszych niż baza — kandydat do obserwacji na żywo; "
                          "nic nie trafia do paper tradingu bez zgody człowieka."),
    ]


# ---------------------------------------------------------------------------
#  Uruchomienie
# ---------------------------------------------------------------------------
def default_path() -> Path:
    return config.RESEARCH_DIR.parent / "ONE-DAY-SEARCH.xlsx"


def load_panel(no_sync: bool = False) -> tuple[Panel, str]:
    u = od.universe()
    insts = od.ordered(u)
    syms = [s for s, _ in insts]
    note = "bez synchronizacji (--no-sync)" if no_sync else od.maybe_sync(syms)
    from .sync import load, parquet_path
    days, groups, spy = {}, {}, None
    for s, g in insts:
        if not parquet_path(s).exists():
            print(f"  ! {s}: brak kopii lokalnej — pominięta")
            continue
        dd = od.daily(load(s))
        if not dd.dates:
            continue
        if s == "SPY":
            spy = dd
        if g == "context":
            continue
        days[s], groups[s] = dd, g
    if not days:
        raise SystemExit("Brak danych w kopii lokalnej — uruchom najpierw `python -m ia4.sync`.")
    return build(days, groups, spy), note


def run(no_sync: bool = False, out: Path | None = None) -> Path:
    t0 = time.time()
    print("IA 4 — One-Day: poszukiwanie strategii stabilnych (instrukcja, sekcja 6d)\n")
    P, note = load_panel(no_sync)
    print(f"  {note}")
    res = search(P)
    plc = placebo(P)
    print(f"  placebo (losowy znak dni): spełnia {plc['passed']} · w arkuszu {plc['kept']} · potwierdzonych {plc['confirmed']}")
    path = write_xlsx(out or default_path(), P, res, meta_rows(P, res, note, plc))
    conf = sum(confirmed(it["dp"]) for it in res["kept"])
    print(f"\n  W arkuszu: {len(res['kept'])} reguł · potwierdzonych na doubleProof: {conf} · {time.time() - t0:.0f} s")
    for k, it in enumerate(res["kept"][:10], start=1):
        st, dp = it["st"], it["dp"]
        print(f"  {k:>2}. {it['rule'].code:<28} trans. {st.n:>5}  śr. {st.avg:+.3f}%  nadw. {st.excess:+.3f}%  stratne {st.losing}  "
              f"t {st.tstat:5.2f}  dP {'✓' if confirmed(dp) else '—'} ({dp.total:+.1f}%)" if dp else "")
    for k, it in enumerate(res["kept"][:PF_SHEETS], start=1):
        pf = it.get("pf")
        if pf:
            print(f"  PORTFEL #{k}: {pf['capital']:,.0f} $ → {pf['end']:,.2f} $ ({pf['ret']:+.2f}%), "
                  f"obsunięcie {pf['mdd']:.2f}%, transakcji {pf['trades']}".replace(",", " "))
    print(f"\nPlik: {path}")
    return path


# ---------------------------------------------------------------------------
#  Selftest
# ---------------------------------------------------------------------------
def _synth(n_stocks: int, n_days: int, seed: int, edge: float = 0.0, start: str = "2024-09-16"):
    """Dane syntetyczne (świece 1h → oneday.daily). edge > 0: long w poniedziałek po spadkowym piątku
    daje średnio +edge % (zaszyta przewaga do odnalezienia)."""
    import pandas as pd
    rng = np.random.default_rng(seed)
    cal = trading_days(start, "2027-12-31")[:n_days]
    out = {}
    for s in range(n_stocks):
        p, rows, prev_dn = 100.0, [], False
        for d in cal:
            mv = rng.normal(0.0, 1.0)
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
            prev_dn = c < o
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
    d = np.diff(c)
    ag, al = np.clip(d[:2], 0, None).mean(), np.clip(-d[:2], 0, None).mean()
    check("RSI(2) pierwszy", abs(f["rsi2"][2] - (100 - 100 / (1 + ag / al))) < 1e-9 if al else True, round(f["rsi2"][2], 4))
    check("najniższe z 10 — brak przed 10 sesjami", np.isnan(f["low10"][:9]).all())

    # 2. Panel i brak zaglądania w przyszłość
    data = _synth(6, 260, seed=3)
    P = build(data, {s: ("main" if i < 4 else "doubleProof") for i, s in enumerate(data)}, data["S0"])
    t = 200
    before = {k: v[:, t].copy() for k, v in P.feat.items()}
    before_spy = {k: v[t].copy() for k, v in P.spy.items()}
    data2 = _synth(6, 260, seed=3)
    for dd in data2.values():
        dd.c[t] *= 1.3
        dd.h[t] *= 1.3
    P2 = build(data2, {s: ("main" if i < 4 else "doubleProof") for i, s in enumerate(data2)}, data2["S0"])
    same = all(np.array_equal(np.nan_to_num(before[k], nan=-9), np.nan_to_num(P2.feat[k][:, t], nan=-9)) for k in before)
    same &= all(np.array_equal(np.nan_to_num(before_spy[k], nan=-9), np.nan_to_num(P2.spy[k][t], nan=-9)) for k in before_spy)
    check("cechy dnia t nie widzą świecy t", same)
    moved = any(not np.array_equal(np.nan_to_num(P.feat[k][:, t + 1], nan=-9), np.nan_to_num(P2.feat[k][:, t + 1], nan=-9))
                for k in P.feat)
    check("cechy dnia t+1 widzą świecę t", moved)
    check("rozgrzewka", not P.base[:, :WARM_Q].any() and P.base[:, WARM_Q + 5:].any())
    check("wynik transakcji open→close", abs(P.ret[0, t] - (P.c[0, t] / P.o[0, t] - 1) * 100) < 1e-12)
    w = periods(P, np.arange(4))
    check("10 okresów pokrywa okno", len(w[1]) == 10 and w[1][0][0] == w[0] and w[1][-1][1] == len(P.dates))

    # 3. Ocena na ręcznej masce
    m = np.zeros_like(P.base)
    a, b = w[1][0]
    m[0, a] = m[1, a] = True                       # okres 1: 2 transakcje (pusty)
    for p in range(1, 10):
        a, b = w[1][p]
        m[0, a:a + 3] = True
    R = np.zeros_like(P.ret)
    R[m] = 1.0
    a, b = w[1][4]
    R[0, a] = -5.0                                  # okres 5: suma 1 + 1 − 5 = −3 → stratny
    st = evaluate(m, R, 1, w, [0.0] * 10)
    check("ocena: transakcji / pusty / stratny", (st.n, st.empty, st.losing) == (29, 1, 1), (st.n, st.empty, st.losing))
    check("ocena: suma i najgorszy", abs(st.total - (29 - 6)) < 1e-9 and abs(st.worst + 3) < 1e-9, (st.total, st.worst))
    check("ocena: short odwraca", abs(evaluate(m, R, -1, w, [0.0] * 10).total + st.total) < 1e-9)
    check("ocena: za mało transakcji → nie spełnia", not st.ok)
    st_b = evaluate(m, R, 1, w, [0.5] * 10)
    check("ocena: nadwyżka nad bazą", abs(st_b.excess - (st.avg - 0.5)) < 1e-12, round(st_b.excess, 6))

    # 4. Zaszyta przewaga zostaje znaleziona i potwierdzona; szum — mało trafień
    data = _synth(30, 520, seed=11, edge=1.5)
    groups = {s: ("main" if i < 22 else "doubleProof") for i, s in enumerate(data)}
    P = build(data, groups, data["S0"])
    t0 = time.time()
    res = search(P, log=lambda *_: None)
    top = [it["rule"].code for it in res["kept"][:5]]
    hit = any(code.startswith("L|dn1") and "pon" in code for code in top)
    check("zaszyta przewaga w pierwszej piątce", hit, top)
    best = next((it for it in res["kept"] if it["rule"].code.startswith("L|dn1") and "pon" in it["rule"].code), None)
    check("przewaga potwierdzona na doubleProof", best is not None and confirmed(best["dp"]))
    check("czas poszukiwania", time.time() - t0 < 120, f"{time.time() - t0:.0f} s, reguł {res['tested']}")
    plc = placebo(P)
    real_conf = sum(confirmed(it["dp"]) for it in res["kept"])
    check("placebo: przewaga znika (potwierdzonych ≤ 2, prawdziwych ≥ 5 razy więcej)",
          plc["confirmed"] <= 2 and real_conf >= 5 * max(1, plc["confirmed"]), f"placebo {plc}, prawdziwe {real_conf}")
    noise = search(build(_synth(30, 520, seed=12), groups, None), log=lambda *_: None)
    rate = noise["passed"] / max(1, noise["tested"])
    check("szum: odsetek trafień z przypadku < 3%", rate < 0.03, f"{noise['passed']} z {noise['tested']} ({rate:.2%})")
    conf_noise = sum(confirmed(it["dp"]) for it in noise["kept"])
    check("szum: 0 potwierdzonych na doubleProof", conf_noise == 0, f"w arkuszu {len(noise['kept'])}, potwierdzonych {conf_noise}")

    # 5. Portfel: stała stawka, suma dnia ≤ stan portfela
    it = best or res["kept"][0]
    rows = np.concatenate([res["rows"], res["dprows"]]).astype(int)
    pf = portfolio(P, it["mask"], it["rule"].dir, rows, g0=res["win"][0])
    by_day: dict[str, float] = {}
    eq_start = {}
    eq = PF_CAPITAL
    for r in pf["rows"]:
        by_day[r["day"]] = by_day.get(r["day"], 0.0) + r["stake"]
    check("portfel: transakcje = maska w oknie", pf["trades"] == int(it["mask"][rows][:, res["win"][0]:].sum()), pf["trades"])
    check("portfel: start z okresem 1", pf["first"] >= P.dates[res["win"][0]], pf["first"])
    check("portfel: stan = start + suma wyników", abs(pf["end"] - PF_CAPITAL - sum(r["pnl"] for r in pf["rows"])) < 1e-6)
    ok_cap, eq = True, PF_CAPITAL
    for day in sorted(by_day):
        ok_cap &= by_day[day] <= eq + 1e-6
        eq += sum(r["pnl"] for r in pf["rows"] if r["day"] == day)
    check("portfel: suma stawek dnia ≤ stan portfela", ok_cap)

    # 6. Excel
    out = Path(tempfile.mkdtemp()) / "s.xlsx"
    write_xlsx(out, P, res, meta_rows(P, res, "selftest"))
    from openpyxl import load_workbook
    wb = load_workbook(out)
    check("Excel: arkusze", wb.sheetnames == ["WYNIKI", "OKRESY", "PORTFEL #1", "PORTFEL #2", "PORTFEL #3", "OPIS"],
          wb.sheetnames)
    ws = wb["WYNIKI"]
    check("Excel: wiersze WYNIKI", ws.max_row == 2 + len(res["kept"]), ws.max_row)
    check("Excel: kod pierwszej reguły", ws.cell(3, 2).value == res["kept"][0]["rule"].code)

    print("\nWYNIK:", "OK" if not fails else f"BŁĘDY ({len(fails)}): " + ", ".join(fails))
    sys.exit(0 if not fails else 1)


def main() -> None:
    ap = argparse.ArgumentParser(description="IA 4 — One-Day: poszukiwanie strategii stabilnych (instrukcja, 6d)")
    ap.add_argument("--no-sync", action="store_true", help="bez synchronizacji z Firestore")
    ap.add_argument("--out", type=Path, help="ścieżka pliku (domyślnie ~/Desktop/IA4/ONE-DAY-SEARCH.xlsx)")
    ap.add_argument("--selftest", action="store_true", help="test na danych syntetycznych")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    else:
        run(no_sync=a.no_sync, out=a.out)


if __name__ == "__main__":
    main()
