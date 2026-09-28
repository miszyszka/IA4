"""
IA 4 — sygnały katalogu S1 (Etap 1b, instrukcja 1.7).
Wersja projektu: 0.39 (2026-09-28) — musi zgadzać się z IA4_INSTRUKCJA.md

Jedna funkcja na typ z `params["type"]` w `s1/catalog.json`. Każda dostaje
świece jednego odcinka (`bars.Bars`) i zwraca maskę bool: czy sygnał odpala
na zamkniętej świecy t. Definicje odpowiadają słowo w słowo polu
`definition` w katalogu (D20) — tam, gdzie opis był niejednoznaczny, katalog
został doprecyzowany w 0.36, zanim cokolwiek policzono (SQZ, ACC).

`mask(signal, bars)` to jedyne wejście z zewnątrz. Poza samą definicją nakłada
warunki ważności z kontraktu silnika (`S1_KATALOG_BAZOWY.md`):
  - rozgrzewka (pkt 10): pełne `warmup_bars` z katalogu w obrębie odcinka,
  - dziury w danych (pkt 13, D27): w oknie rozgrzewki nie ma dziury,
  - splity (pkt 14, D24): odcinki są cięte na splitach, okno ich nie przekracza,
  - wolumen (D12): sygnały `volume=true` wymagają v > 0 w całym oknie,
  - wejście NEXT_OPEN: następna świeca istnieje w tym samym odcinku i nie ma
    przed nią dziury (inaczej „otwarcie następnej świecy” byłoby otwarciem
    kilka dni później).

Zasady wspólne:
  - Porównania z NaN dają fałsz: brak historii = brak sygnału.
  - „Zdarzenie” (nowe rodziny, 1.3) = warunek na t prawdziwy, na t−1 nie.
    Sygnały bazowe i ich lustra zostają w pierwotnej postaci (część jest
    poziomowa — pkt 8 kontraktu i tak ignoruje sygnały w trakcie pozycji).
  - Rodziny H8 budowane na sygnale bez wolumenu (CAP ← DROP/BIGRED,
    VBRK ← DONCH, VMAX ← MAX, DRY ← PULLMA) mają tę samą postać co para, tylko
    z dodanym warunkiem RVOL — inaczej porównanie „ile daje wolumen” (1.4,
    2.2) mieszałoby dwie różnice naraz.
  - H7 (SPY) nie dotyczy samych SPY i QQQ (1.4): dla nich maska jest pusta.

Moduł nie liczy żadnego wyniku transakcji (1.1) — tylko to, KIEDY sygnał
odpala. Wyniki liczy `engine.py`, dopiero w Etapie 2.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from . import indicators as ind
from . import nyse
from .bars import Bars

MARKET_SYMBOLS = {"SPY", "QQQ"}

warnings.filterwarnings("ignore", category=RuntimeWarning, message="invalid value encountered")


# ---------------------------------------------------------------------------
#  Pomocnicze
# ---------------------------------------------------------------------------
def sh(a: np.ndarray, k: int) -> np.ndarray:
    """a[t−k] na pozycji t; na początku NaN (dla bool — False)."""
    a = np.asarray(a)
    if a.dtype == bool:
        out = np.zeros(len(a), dtype=bool)
        if k < len(a):
            out[k:] = a[:len(a) - k]
        return out
    out = np.full(len(a), np.nan)
    if k < len(a):
        out[k:] = a[:len(a) - k]
    return out


def roll_max(a, n):
    return pd.Series(a).rolling(n).max().to_numpy()


def roll_min(a, n):
    return pd.Series(a).rolling(n).min().to_numpy()


def roll_sum(a, n):
    return pd.Series(np.asarray(a, dtype=float)).rolling(n).sum().to_numpy()


def roll_mean(a, n):
    return pd.Series(np.asarray(a, dtype=float)).rolling(n).mean().to_numpy()


def event(cond: np.ndarray) -> np.ndarray:
    """Warunek staje się prawdziwy: na t tak, na t−1 nie (1.3)."""
    cond = np.asarray(cond, dtype=bool)
    return cond & ~sh(cond, 1)


def down(x, ref, pct):
    """x ≤ ref × (1 − pct%)."""
    return x <= ref * (1 - pct / 100.0)


def up(x, ref, pct):
    """x ≥ ref × (1 + pct%)."""
    return x >= ref * (1 + pct / 100.0)


def cross_up(a, b):
    return (a > b) & (sh(a, 1) <= sh(b, 1))


def cross_down(a, b):
    return (a < b) & (sh(a, 1) >= sh(b, 1))


def first_in_session(cond: np.ndarray, B: Bars) -> np.ndarray:
    """Tylko pierwsza świeca sesji, na której warunek jest prawdziwy."""
    cond = np.asarray(cond, dtype=bool)
    n_in_sess = pd.Series(cond.astype(int)).groupby(B.sess).cumsum().to_numpy()
    return cond & (n_in_sess == 1)


def last_true_index(cond: np.ndarray) -> np.ndarray:
    """Dla każdego t: największe j ≤ t z cond[j], albo −1."""
    idx = np.where(cond, np.arange(len(cond)), -1)
    return np.maximum.accumulate(idx) if len(idx) else idx


class Sess:
    """Wartości całych sesji i ich przypisanie do wierszy."""

    def __init__(self, B: Bars):
        s = B.sess
        g = pd.DataFrame({"s": s, "o": B.o, "h": B.h, "l": B.l, "c": B.c}).groupby("s")
        self.row = s
        self.open = g["o"].first().to_numpy()
        self.high = g["h"].max().to_numpy()
        self.low = g["l"].min().to_numpy()
        self.close = g["c"].last().to_numpy()
        self.date = pd.Series(B.date).groupby(s).first().to_numpy()
        # wartości „do świecy t włącznie” w bieżącej sesji
        self.high_to_t = pd.Series(B.h).groupby(s).cummax().to_numpy()
        self.low_to_t = pd.Series(B.l).groupby(s).cummin().to_numpy()
        self.open_row = self.open[s]

    def prev(self, arr: np.ndarray, k: int = 1) -> np.ndarray:
        """Wartość sesji s−k przypisana do każdego wiersza sesji s (NaN, gdy brak)."""
        out = np.full(len(self.row), np.nan)
        ok = self.row >= k
        out[ok] = arr[self.row[ok] - k]
        return out


class Ind:
    """Pamięć podręczna wskaźników dla jednego odcinka."""

    def __init__(self, B: Bars):
        self.B = B
        self._c: dict = {}

    def _get(self, key, fn):
        if key not in self._c:
            self._c[key] = fn()
        return self._c[key]

    def ma(self, kind: str, n: int) -> np.ndarray:
        f = ind.ema if kind == "EMA" else ind.sma
        return self._get(("ma", kind, n), lambda: f(pd.Series(self.B.c), n).to_numpy())

    def rsi(self, n):
        return self._get(("rsi", n), lambda: ind.rsi(pd.Series(self.B.c), n).to_numpy())

    def atr(self, n):
        B = self.B
        return self._get(("atr", n), lambda: ind.atr(pd.Series(B.h), pd.Series(B.l), pd.Series(B.c), n).to_numpy())

    def bb(self, n, k):
        return self._get(("bb", n, k), lambda: {kk: vv.to_numpy() for kk, vv in
                                                   ind.bollinger(pd.Series(self.B.c), n, k).items()})

    def macd(self, f, s, g):
        return self._get(("macd", f, s, g), lambda: {kk: vv.to_numpy() for kk, vv in
                                                        ind.macd(pd.Series(self.B.c), f, s, g).items()})

    def stoch(self, k, sm, d):
        B = self.B
        return self._get(("st", k, sm, d), lambda: {kk: vv.to_numpy() for kk, vv in ind.stochastic(
            pd.Series(B.h), pd.Series(B.l), pd.Series(B.c), k, sm, d).items()})

    def vwap(self):
        B = self.B
        return self._get("vwap", lambda: ind.vwap_session(
            pd.Series(B.date), pd.Series(B.h), pd.Series(B.l), pd.Series(B.c), pd.Series(B.v)).to_numpy())

    def vwma(self, n):
        B = self.B

        def f():
            tpv = ind.typical_price_x_volume(pd.Series(B.h), pd.Series(B.l), pd.Series(B.c), pd.Series(B.v))
            return ind.vwma(tpv, pd.Series(B.v), n).to_numpy()
        return self._get(("vwma", n), f)

    def obv(self):
        return self._get("obv", lambda: ind.obv(pd.Series(self.B.c), pd.Series(self.B.v)).to_numpy())

    def rvol(self):
        from .catalog import RVOL_SESSIONS
        return self._get("rvol", lambda: ind.rvol(pd.Series(self.B.slot), pd.Series(self.B.v),
                                                  RVOL_SESSIONS).to_numpy())

    def sess(self) -> Sess:
        return self._get("sess", lambda: Sess(self.B))


# ---------------------------------------------------------------------------
#  Rodziny — rejestr typów
# ---------------------------------------------------------------------------
FAMILIES: dict = {}


def family(*types):
    def deco(fn):
        for t in types:
            FAMILIES[t] = fn
        return fn
    return deco


def is_up(p: dict) -> bool:
    return p.get("dir") == "up"


# ============================ H1 — bazowe i lustra ============================
@family("DROP", "RISE")
def f_drop(p, B, I):
    ref = sh(B.c, p["n"])
    return up(B.c, ref, p["pct"]) if p["type"] == "RISE" else down(B.c, ref, p["pct"])


@family("RED", "GREEN")
def f_red(p, B, I):
    k = p["k"]
    color = (B.c > B.o) if p["type"] == "GREEN" else (B.c < B.o)
    run = roll_sum(color, k) == k
    ref = sh(B.o, k - 1)
    move = up(B.c, ref, p["pct"]) if p["type"] == "GREEN" else down(B.c, ref, p["pct"])
    return run & move


@family("MADEV", "MAUP")
def f_madev(p, B, I):
    m = I.ma("SMA", p["sma"])
    return up(B.c, m, p["pct"]) if p["type"] == "MAUP" else down(B.c, m, p["pct"])


@family("RSI")
def f_rsi(p, B, I):
    r = I.rsi(p["len"])
    if "above" in p:
        return (r > p["above"]) & (sh(r, 1) <= p["above"])
    return (r < p["below"]) & (sh(r, 1) >= p["below"])


@family("BB", "BBU")
def f_bb(p, B, I):
    b = I.bb(p["len"], p["k"])
    return (B.c > b["upper"]) if p["type"] == "BBU" else (B.c < b["lower"])


def _gap(B, p, dir_up: bool):
    prev_c = sh(B.c, 1)            # ostatnie zamknięcie poprzedniej sesji (dziury: pkt 13)
    g = up(B.o, prev_c, p["pct"]) if dir_up else down(B.o, prev_c, p["pct"])
    return B.is_first & g


@family("GAP", "GAPUP")
def f_gap(p, B, I):
    return _gap(B, p, p["type"] == "GAPUP")


@family("GAPRED", "GAPGREEN")
def f_gapred(p, B, I):
    if p["type"] == "GAPGREEN":
        return _gap(B, p, True) & (B.c > B.o)
    return _gap(B, p, False) & (B.c < B.o)


@family("SODD", "SORU")
def f_sodd(p, B, I):
    so = I.sess().open_row
    cond = up(B.c, so, p["pct"]) if p["type"] == "SORU" else down(B.c, so, p["pct"])
    return first_in_session(cond, B)


@family("HHDD", "LLRU")
def f_hhdd(p, B, I):
    n = p["lookback"]
    if p["type"] == "LLRU":
        return up(B.c, roll_min(B.l, n), p["pct"])
    return down(B.c, roll_max(B.h, n), p["pct"])


@family("BIGRED", "BIGGREEN")
def f_big(p, B, I):
    return up(B.c, B.o, p["pct"]) if p["type"] == "BIGGREEN" else down(B.c, B.o, p["pct"])


@family("HAMMER", "STAR")
def f_hammer(p, B, I):
    pb = p["priorBars"]
    body = np.abs(B.c - B.o)
    upper = B.h - np.maximum(B.o, B.c)
    lower = np.minimum(B.o, B.c) - B.l
    rng = B.h - B.l
    if p["type"] == "STAR":
        prior = up(sh(B.c, 1), sh(B.c, pb + 1), p["priorPct"])
        shape = (upper >= 2 * body) & (lower <= body) & (B.c <= B.l + rng / 3.0)
    else:
        prior = down(sh(B.c, 1), sh(B.c, pb + 1), p["priorPct"])
        shape = (lower >= 2 * body) & (upper <= body) & (B.c >= B.l + 2 * rng / 3.0)
    return prior & shape & (rng > 0)


@family("ENGULF", "ENGULFDN")
def f_engulf(p, B, I):
    if p["type"] == "ENGULFDN":
        m = p["minGreen"]
        run = sh(roll_sum(B.c > B.o, m) == m, 1)
        prior = up(sh(B.c, 1), sh(B.o, m), p["priorPct"])
        now = (B.c < B.o) & (B.o >= sh(B.c, 1)) & (B.c <= sh(B.o, 1))
    else:
        m = p["minRed"]
        run = sh(roll_sum(B.c < B.o, m) == m, 1)
        prior = down(sh(B.c, 1), sh(B.o, m), p["priorPct"])
        now = (B.c > B.o) & (B.o <= sh(B.c, 1)) & (B.c >= sh(B.o, 1))
    return run & prior & now


@family("REVCONF", "REVDN")
def f_revconf(p, B, I):
    pb = p["priorBars"]
    if p["type"] == "REVDN":
        return up(sh(B.c, 1), sh(B.c, pb + 1), p["priorPct"]) & (B.c < B.o) & (B.c < sh(B.l, 1))
    return down(sh(B.c, 1), sh(B.c, pb + 1), p["priorPct"]) & (B.c > B.o) & (B.c > sh(B.h, 1))


@family("ATRDROP", "ATRRISE")
def f_atrdrop(p, B, I):
    a = I.atr(p["atr"])
    d = sh(B.c, p["n"])
    if p["type"] == "ATRRISE":
        return (B.c - d) >= p["k"] * a
    return (d - B.c) >= p["k"] * a


@family("DDAYS", "UDAYS")
def f_ddays(p, B, I):
    S = I.sess()
    sc = S.close
    step = (sc > sh(sc, 1)) if p["type"] == "UDAYS" else (sc < sh(sc, 1))
    ok_sess = roll_sum(step, p["k"]) == p["k"]
    return B.is_last & ok_sess[S.row]


FILTERS = {
    "TREND140": lambda B, I: B.c > I.ma("SMA", 140),
    "DOWN140": lambda B, I: B.c < I.ma("SMA", 140),
    "LASTBAR": lambda B, I: B.is_last,
    "FIRSTBAR": lambda B, I: B.is_first,
}


# ============================ H2 — trend ============================
@family("MAX")
def f_max(p, B, I):
    fa, sl = I.ma(p["ma"], p["fast"]), I.ma(p["ma"], p["slow"])
    return cross_up(fa, sl) if is_up(p) else cross_down(fa, sl)


@family("PXMA")
def f_pxma(p, B, I):
    m = I.ma(p["ma"], p["n"])
    return cross_up(B.c, m) if is_up(p) else cross_down(B.c, m)


@family("PULLMA")
def f_pullma(p, B, I):
    m = I.ma(p["ma"], p["n"])
    tr = p["trend"]
    if tr["type"] == "EMA_GT":
        f, s = I.ma("EMA", tr["fast"]), I.ma("EMA", tr["slow"])
        trend = (f > s) if is_up(p) else (f < s)
    else:   # SLOPE: SMA(slow) wyższa / niższa niż `lag` świec temu
        s = I.ma("SMA", tr["slow"])
        trend = (s > sh(s, tr["lag"])) if is_up(p) else (s < sh(s, tr["lag"]))
    if is_up(p):
        touch = (B.l <= m) & (m < B.c) & (sh(B.l, 1) > sh(m, 1))
    else:
        touch = (B.h >= m) & (m > B.c) & (sh(B.h, 1) < sh(m, 1))
    return trend & touch


@family("MASLOPE")
def f_maslope(p, B, I):
    s = I.ma(p["ma"], p["n"])
    k = p["k"]
    if is_up(p):
        turn, before = s > sh(s, 1), s < sh(s, 1)
    else:
        turn, before = s < sh(s, 1), s > sh(s, 1)
    return turn & (sh(roll_sum(before, k), 1) == k)


@family("RIBBON")
def f_ribbon(p, B, I):
    mas = [I.ma(kind, n) for kind, n in p["mas"]]
    cond = np.ones(B.n, dtype=bool)
    for a, b in zip(mas[:-1], mas[1:]):
        cond &= (a > b) if is_up(p) else (a < b)
    return event(cond)


@family("MACD")
def f_macd(p, B, I):
    m = I.macd(p["fast"], p["slow"], p["signal"])
    line = m["macd"]
    ref = m["signal"] if p["cross"] == "signal" else np.zeros(B.n)
    x = cross_up(line, ref) if is_up(p) else cross_down(line, ref)
    if p.get("zone") == "below0":
        x &= line < 0
    elif p.get("zone") == "above0":
        x &= line > 0
    return x


def _same_session_prev(B: Bars) -> np.ndarray:
    ok = np.zeros(B.n, dtype=bool)
    ok[1:] = (B.date[1:] == B.date[:-1]) & (B.slot[1:] == B.slot[:-1] + 1)
    return ok


@family("VWAPX")
def f_vwapx(p, B, I):
    vw = I.vwap()
    x = cross_up(B.c, vw) if is_up(p) else cross_down(B.c, vw)
    return x & _same_session_prev(B)


@family("VWAPDEV")
def f_vwapdev(p, B, I):
    vw = I.vwap()
    cond = down(B.c, vw, p["pct"]) if p["side"] == "below" else up(B.c, vw, p["pct"])
    return first_in_session(cond, B)


@family("VWMAX")
def f_vwmax(p, B, I):
    m = I.vwma(p["n"])
    return cross_up(B.c, m) if is_up(p) else cross_down(B.c, m)


# ============================ H3 — wybicia ============================
def donch(B: Bars, n: int, dir_up: bool) -> np.ndarray:
    if dir_up:
        br = B.c > sh(roll_max(B.h, n), 1)
    else:
        br = B.c < sh(roll_min(B.l, n), 1)
    return event(br)


@family("DONCH")
def f_donch(p, B, I):
    return donch(B, p["n"], is_up(p))


@family("NSES")
def f_nses(p, B, I):
    S = I.sess()
    prev = sh(S.close, 1)
    if is_up(p):
        ok = S.close > roll_max(prev, p["n"])
    else:
        ok = S.close < roll_min(prev, p["n"])
    return B.is_last & ok[S.row]


@family("PDHL")
def f_pdhl(p, B, I):
    S = I.sess()
    cond = (B.c > S.prev(S.high)) if is_up(p) else (B.c < S.prev(S.low))
    return first_in_session(cond, B)


@family("ORB")
def f_orb(p, B, I):
    s = B.sess
    in_rng = B.slot <= p["bars"]
    rh = pd.Series(np.where(in_rng, B.h, np.nan)).groupby(s).transform("max").to_numpy()
    rl = pd.Series(np.where(in_rng, B.l, np.nan)).groupby(s).transform("min").to_numpy()
    window = (B.slot >= p["fromSlot"]) & (B.slot <= p["toSlot"])
    cond = window & ((B.c > rh) if is_up(p) else (B.c < rl))
    return first_in_session(cond, B)


@family("INSIDE")
def f_inside(p, B, I):
    S = I.sess()
    inside = (S.high <= sh(S.high, 1)) & (S.low >= sh(S.low, 1))   # sesja s w zakresie s−1
    was_inside = np.zeros(B.n, dtype=bool)
    ok = S.row >= 1
    was_inside[ok] = inside[S.row[ok] - 1]
    cond = was_inside & ((B.c > S.prev(S.high)) if is_up(p) else (B.c < S.prev(S.low)))
    return first_in_session(cond, B)


# ============================ H4 — zmienność ============================
@family("SQZ")
def f_sqz(p, B, I):
    b = I.bb(p["len"], p["k"])
    w = b["width"]
    tight = w <= roll_min(w, p["lookback"]) + 1e-15
    recent = sh(roll_sum(tight, p["recent"]) > 0, 1)          # świece t−7…t−1
    if is_up(p):
        brk = (B.c > b["upper"]) & (sh(B.c, 1) <= sh(b["upper"], 1))
    else:
        brk = (B.c < b["lower"]) & (sh(B.c, 1) >= sh(b["lower"], 1))
    return recent & brk


@family("NR")
def f_nr(p, B, I):
    n = p["n"]
    if p["unit"] == "session":
        S = I.sess()
        rng = S.high - S.low
        nr = rng <= roll_min(rng, n)                          # sesja s najwęższa z s−n+1…s
        prev_nr = np.zeros(B.n, dtype=bool)
        ok = S.row >= 1
        prev_nr[ok] = nr[S.row[ok] - 1]
        cond = prev_nr & ((B.c > S.prev(S.high)) if is_up(p) else (B.c < S.prev(S.low)))
        return first_in_session(cond, B)
    rng = B.h - B.l
    nr_prev = sh(rng <= roll_min(rng, n), 1)                 # świeca t−1 najwęższa z t−n…t−1
    return nr_prev & ((B.c > sh(B.h, 1)) if is_up(p) else (B.c < sh(B.l, 1)))


@family("WRB")
def f_wrb(p, B, I):
    rng = B.h - B.l
    wide = (rng >= p["k"] * sh(I.atr(p["atr"]), 1)) & (rng > 0)
    if is_up(p):
        return wide & (B.c >= B.l + 0.75 * rng)
    return wide & (B.c <= B.l + 0.25 * rng)


# ============================ H5 — oscylatory ============================
@family("STOCH")
def f_stoch(p, B, I):
    st = I.stoch(p["k"], p["smooth"], p["d"])
    k, d = st["k"], st["d"]
    if is_up(p):
        return cross_up(k, d) & (sh(k, 1) < p["level"])
    return cross_down(k, d) & (sh(k, 1) > p["level"])


@family("RSIX")
def f_rsix(p, B, I):
    r = I.rsi(p["len"])
    lv = p["level"]
    if is_up(p):
        return (r > lv) & (sh(r, 1) <= lv)
    return (r < lv) & (sh(r, 1) >= lv)


def divergence(B: Bars, osc: np.ndarray, lookback: int, min_gap: int, dir_up: bool) -> np.ndarray:
    """
    RSIDIV / OBVD: zamknięcie na minimum (maksimum) `lookback` świec, a oscylator
    wyżej (niżej) niż przy poprzednim takim ekstremum j — najbliższym z
    t−lookback…t−min_gap, które w swojej chwili było ekstremum z `lookback` świec.
    """
    ext = (B.c <= roll_min(B.c, lookback)) if dir_up else (B.c >= roll_max(B.c, lookback))
    lti = last_true_index(ext)
    t = np.arange(B.n)
    j = np.full(B.n, -1)
    j[min_gap:] = lti[:B.n - min_gap]
    has = (j >= 0) & (j >= t - lookback)
    oj = np.full(B.n, np.nan)
    oj[has] = osc[j[has]]
    return ext & has & ((osc > oj) if dir_up else (osc < oj))


@family("RSIDIV")
def f_rsidiv(p, B, I):
    return divergence(B, I.rsi(p["len"]), p["lookback"], p["minGap"], is_up(p))


# ============================ H6 — sesja i kalendarz ============================
@family("IBS")
def f_ibs(p, B, I):
    S = I.sess()
    rng = S.high_to_t - S.low_to_t
    ibs = (B.c - S.low_to_t) / np.where(rng > 0, rng, np.nan)
    cond = (ibs <= p["level"]) if p["side"] == "low" else (ibs >= 1 - p["level"])
    return B.is_last & cond


@family("FHR")
def f_fhr(p, B, I):
    second = (B.slot == 2) & _same_session_prev(B)
    o1, h1, l1, c1 = sh(B.o, 1), sh(B.h, 1), sh(B.l, 1), sh(B.c, 1)
    mid = (h1 + l1) / 2.0
    if is_up(p):
        return second & down(c1, o1, p["pct"]) & (B.c > mid)
    return second & up(c1, o1, p["pct"]) & (B.c < mid)


@family("CAL")
def f_cal(p, B, I):
    fn = nyse.is_last_of_month if p["when"] == "month_end" else nyse.is_last_of_week
    flag = np.array([fn(d) for d in B.date], dtype=bool) if B.n else np.zeros(0, dtype=bool)
    return B.is_last & flag


@family("BASE")
def f_base(p, B, I):
    if p["when"] == "session_open":
        return B.is_last.copy()
    return B.slot == B.expected - 1


# ============================ H7 — kontekst rynku ============================
def _mkt(B: Bars):
    if B.mkt_c is None or B.symbol in MARKET_SYMBOLS:
        return None
    return B.mkt_c


@family("IDIO")
def f_idio(p, B, I):
    m = _mkt(B)
    if m is None:
        return np.zeros(B.n, dtype=bool)
    n = p["n"]
    mret = m / sh(m, n) - 1
    if is_up(p):
        cond = up(B.c, sh(B.c, n), p["pct"]) & (mret <= p["mktMax"] / 100.0)
    else:
        cond = down(B.c, sh(B.c, n), p["pct"]) & (mret >= -p["mktMax"] / 100.0)
    return event(cond)


@family("MKT")
def f_mkt(p, B, I):
    m = _mkt(B)
    if m is None:
        return np.zeros(B.n, dtype=bool)
    n = p["n"]
    if is_up(p):
        cond = up(m, sh(m, n), p["mktPct"]) & up(B.c, sh(B.c, n), p["pct"])
    else:
        cond = down(m, sh(m, n), p["mktPct"]) & down(B.c, sh(B.c, n), p["pct"])
    return event(cond)


@family("RSX")
def f_rsx(p, B, I):
    m = _mkt(B)
    if m is None:
        return np.zeros(B.n, dtype=bool)
    n = p["n"]
    ratio = B.c / m
    if is_up(p):
        at = ratio >= roll_max(ratio, n)
        mkt_at = m >= roll_max(m, n)
    else:
        at = ratio <= roll_min(ratio, n)
        mkt_at = m <= roll_min(m, n)
    return at & ~sh(at, 1) & ~mkt_at & ~np.isnan(ratio)


# ============================ H8 — wolumen ============================
@family("CAP")
def f_cap(p, B, I):
    return raw(p["base"], B, I) & (I.rvol() >= p["rvol"])


@family("CLX")
def f_clx(p, B, I):
    rv = I.rvol() >= p["rvol"]
    n = p["n"]
    mid = (B.h + B.l) / 2.0
    if is_up(p):
        return rv & (B.h >= sh(roll_max(B.h, n), 1)) & (B.c <= mid)
    return rv & (B.l <= sh(roll_min(B.l, n), 1)) & (B.c >= mid)


@family("VBRK")
def f_vbrk(p, B, I):
    d = donch(B, p["n"], is_up(p))
    r = I.rvol()
    if "rvolMin" in p:
        return d & (r >= p["rvolMin"])
    return d & (r < p["rvolMax"])


@family("VMAX")
def f_vmax(p, B, I):
    return f_max(p, B, I) & (I.rvol() >= p["rvol"])


@family("DRY")
def f_dry(p, B, I):
    return f_pullma(p["pull"], B, I) & (roll_mean(I.rvol(), p["bars"]) <= p["rvolAvg"])


@family("OBVD")
def f_obvd(p, B, I):
    return divergence(B, I.obv(), p["lookback"], p["minGap"], is_up(p))


@family("GAPV")
def f_gapv(p, B, I):
    g = _gap(B, p, is_up(p))
    r = I.rvol()
    if "rvolMin" in p:
        return g & (r >= p["rvolMin"])
    return g & (r < p["rvolMax"])


@family("ACC")
def f_acc(p, B, I):
    n = p["n"]
    dc = B.c - sh(B.c, 1)
    upv = roll_sum(np.where(dc > 0, B.v, 0.0), n)
    dnv = roll_sum(np.where(dc < 0, B.v, 0.0), n)
    flat = np.abs(B.c / sh(B.c, n) - 1) < p["flat"] / 100.0
    if p["side"] == "acc":
        cond = (upv >= p["ratio"] * dnv) & (upv > 0)
    else:
        cond = (upv <= p["ratio"] * dnv) & (dnv > 0)
    return event(cond & flat & ~np.isnan(dc))


# ---------------------------------------------------------------------------
#  Złożenie: definicja + filtr + ważność
# ---------------------------------------------------------------------------
def raw(p: dict, B: Bars, I: Ind | None = None) -> np.ndarray:
    """Sama definicja sygnału (z filtrem), bez warunków ważności."""
    I = I or Ind(B)
    if B.n == 0:
        return np.zeros(0, dtype=bool)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.asarray(FAMILIES[p["type"]](p, B, I), dtype=bool)
        if "filter" in p:
            m = m & np.asarray(FILTERS[p["filter"]](B, I), dtype=bool)
    return m


def validity(signal: dict, B: Bars) -> np.ndarray:
    """Czy sygnał WOLNO liczyć na świecy t (pkt 10, 13, 14 kontraktu, D12, wejście)."""
    n = B.n
    w = int(signal["warmup_bars"])
    t = np.arange(n)
    a = t - w + 1                                    # początek okna
    ok = a >= B.seg_start                            # pełna rozgrzewka w odcinku (pkt 10, 14)
    holes = np.concatenate([[0], np.cumsum(B.hole_before.astype(int))])   # holes[i] = Σ hole[0..i−1]
    aa = np.clip(a, 0, n)
    ok &= (holes[t + 1] - holes[np.minimum(aa + 1, n)]) == 0      # brak dziury między wierszami okna
    if signal.get("volume"):
        zero = np.concatenate([[0], np.cumsum((B.v <= 0).astype(int))])
        ok &= (zero[t + 1] - zero[aa]) == 0
    if signal.get("entry", "NEXT_OPEN") == "NEXT_OPEN":
        nxt = np.zeros(n, dtype=bool)
        nxt[:-1] = (t[:-1] + 1 <= B.seg_end[:-1]) & ~B.hole_before[1:]
        ok &= nxt
    return ok


def mask(signal: dict, B: Bars) -> np.ndarray:
    """Kiedy sygnał z katalogu odpala na tym instrumencie (świeca sygnału t)."""
    out = np.zeros(B.n, dtype=bool)
    for a, b in B.segments():
        key = ("seg_ind", a, b)
        if key not in B._cache:                      # wskaźniki wspólne dla wszystkich sygnałów
            seg = B.segment(a, b)
            B._cache[key] = (seg, Ind(seg))
        seg, I = B._cache[key]
        out[a:b] = raw(signal["params"], seg, I)
    return out & validity(signal, B)


def entry_index(signal: dict, t: np.ndarray) -> np.ndarray:
    """Świeca wejścia: t+1 (NEXT_OPEN) albo t (SESSION_OPEN — luka znana na otwarciu)."""
    return t if signal.get("entry") == "SESSION_OPEN" else t + 1
