"""
IA 4 — ceny dla AI Investor: świece akcji i FX w jednym kształcie (instrukcja, sekcje 11c.4, 11c.6).
Wersja projektu: 1.37 (2026-10-13) — musi zgadzać się z IA4_INSTRUKCJA.md

Każdy instrument = tablice k (klucz świecy, rośnie), tc (zamknięcie, s UTC), o, h, l, c.
Akcje: k = RRRRMMDDn (data sesji i numer świecy), zamknięcie wg kalendarza NYSE (świeca 7 — 16:00 ET,
sesja skrócona — 4 świece do 13:00). FX i BTC: k = początek świecy (s UTC), zamknięcie = k + 3600.
Przeliczenie na USD (11c.6): waluta kwotowana pary → USD kursem z zamknięcia ostatniej świecy
nie późniejszej niż chwila t (USDJPY, USDCAD, USDCHF, GBPUSD).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ..fx import instruments as fi
from ..lab import indicators as ind
from ..lab.check import US_HALF_DAYS

NY = ZoneInfo("America/New_York")
PL = ZoneInfo("Europe/Warsaw")
FULL_MIN = (630, 690, 750, 810, 870, 930, 960)          # zamknięcia świec 1–7 (min od północy ET)
HALF_MIN = (630, 690, 750, 780)
CONV = {"USD": None, "JPY": ("USDJPY", -1), "CAD": ("USDCAD", -1), "CHF": ("USDCHF", -1), "GBP": ("GBPUSD", 1)}


@lru_cache(maxsize=4096)
def stock_close(date: str, slot: int) -> float:
    mins = HALF_MIN if date in US_HALF_DAYS else FULL_MIN
    m = mins[min(int(slot), len(mins)) - 1]
    d = datetime.fromisoformat(date)
    return datetime(d.year, d.month, d.day, tzinfo=NY).timestamp() + m * 60


@lru_cache(maxsize=4096)
def stock_open(date: str, slot: int) -> float:
    """Początek świecy: 9:30 ET dla pierwszej, dla kolejnych — zamknięcie poprzedniej."""
    if int(slot) <= 1:
        d = datetime.fromisoformat(date)
        return datetime(d.year, d.month, d.day, tzinfo=NY).timestamp() + 570 * 60
    return stock_close(date, int(slot) - 1)


def stock_key(date: str, slot: int) -> int:
    return int(date.replace("-", "")) * 10 + int(slot)


def key_date(k: int) -> str:
    s = str(int(k))[:8]
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


@dataclass
class Series:
    inst: str
    kind: str                       # stock | fx | crypto
    k: np.ndarray
    to: np.ndarray                  # początek świecy (s UTC)
    tc: np.ndarray                  # zamknięcie świecy (s UTC)
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray

    @property
    def n(self) -> int:
        return self.k.size

    def after(self, k0) -> range:
        """Indeksy świec z kluczem > k0."""
        return range(int(np.searchsorted(self.k, k0, side="right")), self.n)

    def index_of(self, k) -> int:
        i = int(np.searchsorted(self.k, k))
        return i if i < self.n and self.k[i] == k else -1


def stock_series(sym: str, df: pd.DataFrame) -> Series:
    df = df.sort_values(["date", "slot"]).drop_duplicates(["date", "slot"], keep="last")
    d = df["date"].astype(str).to_numpy()
    s = df["slot"].to_numpy(np.int64)
    k = np.array([stock_key(a, b) for a, b in zip(d, s)], dtype=np.int64)
    tc = np.array([stock_close(a, int(b)) for a, b in zip(d, s)], dtype=float)
    to = np.array([stock_open(a, int(b)) for a, b in zip(d, s)], dtype=float)
    f = lambda c: df[c].to_numpy(float)
    return Series(sym, "stock", k, to, tc, f("o"), f("h"), f("l"), f("c"))


def fx_series(sym: str, df: pd.DataFrame) -> Series:
    df = df.sort_values("time")
    k = df["time"].to_numpy(np.int64)
    f = lambda c: df[c].to_numpy(float)
    return Series(sym, "crypto" if fi.group_of(sym) == "crypto" else "fx", k, k.astype(float), k + 3600.0,
                  f("o"), f("h"), f("l"), f("c"))


class Prices:
    """Wszystkie instrumenty, które Inwestor może mieć w portfelu, + SPY/QQQ (tło)."""

    def __init__(self, stocks: dict[str, pd.DataFrame] | None = None, fx: dict[str, pd.DataFrame] | None = None):
        self.S: dict[str, Series] = {}
        for s, df in (stocks or {}).items():
            if df is not None and len(df):
                self.S[s] = stock_series(s, df)
        for s, df in (fx or {}).items():
            if df is not None and len(df):
                self.S[s] = fx_series(s, df)
        self._atr: dict[tuple, float] = {}
        self.t_max: float | None = None          # odtwarzanie historii: ceny widoczne tylko do tej chwili

    def _n(self, s: Series) -> int:
        return s.n if self.t_max is None else int(np.searchsorted(s.tc, self.t_max, side="right"))

    def __contains__(self, inst) -> bool:
        return inst in self.S

    def kind(self, inst: str) -> str:
        if inst in self.S:
            return self.S[inst].kind
        return "crypto" if fi.group_of(inst) == "crypto" and inst in fi.INFO else "fx" if inst in fi.INFO else "stock"

    def last(self, inst: str) -> tuple[int, float, float] | None:
        """(klucz, zamknięcie, chwila zamknięcia) ostatniej świecy."""
        s = self.S.get(inst)
        n = self._n(s) if s is not None else 0
        if not n:
            return None
        return int(s.k[n - 1]), float(s.c[n - 1]), float(s.tc[n - 1])

    def close_at(self, inst: str, t: float) -> float | None:
        s = self.S.get(inst)
        if s is None or not s.n:
            return None
        if self.t_max is not None:
            t = min(t, self.t_max)
        i = int(np.searchsorted(s.tc, t, side="right")) - 1
        return float(s.c[max(i, 0)])

    def atr14(self, inst: str) -> float | None:
        s = self.S.get(inst)
        if s is None:
            return None
        n = self._n(s)
        if (inst, n) not in self._atr:
            if n < 20:
                return None
            a = ind.atr(s.h[:n], s.l[:n], s.c[:n], 14)
            self._atr[(inst, n)] = float(a[-1]) if np.isfinite(a[-1]) else None
        return self._atr[(inst, n)]

    # ------------------------------------------------------------------ USD
    def quote(self, inst: str) -> str:
        return inst[3:] if self.kind(inst) in ("fx", "crypto") else "USD"

    def conv(self, inst: str, t: float) -> float | None:
        """USD za 1 jednostkę waluty kwotowanej instrumentu w chwili t."""
        q = self.quote(inst)
        rule = CONV.get(q, "?")
        if rule is None:
            return 1.0
        if rule == "?":
            return None
        pair, sgn = rule
        px = self.close_at(pair, t)
        if px is None or px <= 0:
            return None
        return px if sgn > 0 else 1.0 / px

    def pip(self, inst: str) -> float:
        return fi.INFO.get(inst, {"pip": 0.01})["pip"]

    def digits(self, inst: str) -> int:
        return fi.INFO.get(inst, {"digits": 2})["digits"] if inst in fi.INFO else 2

    # ------------------------------------------------------------------ opisy
    def label(self, inst: str, k: int) -> str:
        if self.kind(inst) == "stock":
            return f"{key_date(k)} #{int(k) % 10}"
        a = datetime.fromtimestamp(int(k), PL)
        return f"{a:%d.%m %H:%M}–{(a + timedelta(hours=1)):%H:%M}"


def iso(t: float | None) -> str | None:
    return None if t is None else datetime.fromtimestamp(float(t), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pl(t: float | None) -> str:
    return "" if t is None else datetime.fromtimestamp(float(t), PL).strftime("%Y-%m-%d %H:%M")
