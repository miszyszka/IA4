"""
IA 4 — katalog okoliczności EURUSD `fx-cond/1` i jednorazowa kalibracja
(instrukcja, sekcje 4c.2 i 4c.3).
Wersja projektu: 1.23 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

Okoliczność = cecha f (liczba na świecy t, tylko ze świec ≤ t) i warunek  f ≥ próg.
Cecha jest zbudowana tak, że duża wartość = wzrost / wysoka cena. Okoliczność `+`
liczy f na serii zwykłej, jej para `−` — tę samą f na serii odbitej (series.py),
z tym samym progiem. Dzięki temu 500 par = dokładnie 500 `+` i 500 `−`.

DEFINICJI RODZAJÓW (FEATURES) NIE WOLNO ZMIENIAĆ po kalibracji (zasada 14) —
`fx/conditions.json` zapisuje tylko rodzaj, parametry i próg, a wartości liczy ten kod.

  python -m ia4.fx.catalog             # kalibracja próbna: podgląd w data/fx/catalog-preview.csv
  python -m ia4.fx.catalog --commit    # kalibracja właściwa → fx/conditions.json (branch fx), RAZ
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone

import numpy as np

from . import series as sr
from .series import PIP, Series, shift

CATALOG = "fx-cond/1"
TARGETS = (0.25, 0.15, 0.40)       # docelowe częstości (kolejność = kolejność kandydatów)
RANGE = (0.10, 0.50)               # każda okoliczność pary musi się w tym mieścić
CORR_STEPS = (0.85, 0.95)          # najwyższa korelacja (phi) z już wybraną okolicznością
PAIRS = 500

PER = (9, 20, 38, 50, 103, 200, 288)
MA_PAIRS = ((9, 20), (9, 38), (20, 50), (20, 103), (38, 103), (50, 200), (103, 288), (20, 200))
X_PAIRS = (("EMA", 9, "EMA", 20), ("EMA", 20, "EMA", 50), ("SMA", 20, "SMA", 50), ("EMA", 38, "KAMA", 103),
           ("SMA", 50, "SMA", 200), ("HMA", 20, "EMA", 50), ("DEMA", 20, "SMA", 103), ("EMA", 103, "EMA", 288),
           ("WMA", 9, "SMA", 38), ("KAMA", 20, "KAMA", 103))
TRENDS = (("EMA", 200), ("SMA", 288), ("KAMA", 103), ("EMA", 103))
ANCH = {"utc_day": "doby UTC", "ny_day": "doby handlowej (od 17:00 Nowy Jork)", "week": "tygodnia"}


# ===========================================================================
#  Rodzaje cech: f(S, p) → tablica (NaN = nie da się policzyć → warunek fałszywy)
# ===========================================================================
def _ma(S, k, n):
    return S.ma(k, n)


def f_chg_pips(S, p):
    return (S.c - shift(S.c, p["n"])) / PIP


def f_er_signed(S, p):
    n = p["n"]
    path = sr.roll_sum(np.abs(np.diff(S.c, prepend=np.nan)), n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(path > 0, (S.c - shift(S.c, n)) / path, 0.0 * path)


def f_body_er(S, p):
    n = p["n"]
    b = S.c - S.o
    num, den = sr.roll_sum(b, n), sr.roll_sum(np.abs(b), n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, 0.0 * den)


def f_green_cnt(S, p):
    return sr.roll_sum((S.c > S.o).astype(np.float64), p["n"])


def f_streak_green(S, p):
    return sr.streak(S.c > S.o)


def f_hhhl_streak(S, p):
    up = np.zeros(S.n, dtype=bool)
    up[1:] = (S.h[1:] > S.h[:-1]) & (S.l[1:] > S.l[:-1])
    return sr.streak(up)


def f_clv(S, p):
    rng = S.h - S.l
    with np.errstate(invalid="ignore", divide="ignore"):
        x = np.where(rng > 0, ((S.c - S.l) - (S.h - S.c)) / rng, 0.0)
    return sr.roll_sum(x, p["n"]) / p["n"]


def f_px_vs_ma(S, p):
    return (S.c - _ma(S, p["ma"], p["n"])) / S.U


def f_ma_slope(S, p):
    m = _ma(S, p["ma"], p["n"])
    return (m - shift(m, p["k"])) / S.U


def f_ma_spread(S, p):
    return (_ma(S, p["m1"], p["n1"]) - _ma(S, p["m2"], p["n2"])) / S.U


def _cross_up(a, b):
    ev = np.zeros(a.size, dtype=bool)
    ev[1:] = (a[1:] > b[1:]) & (a[:-1] <= b[:-1])
    return ev


def f_ma_cross(S, p):
    a, b = _ma(S, p["m1"], p["n1"]), _ma(S, p["m2"], p["n2"])
    ev = _cross_up(a, b)
    if p["against"]:                          # wolna średnia spadkowa (6 świec) w chwili przecięcia
        ev &= (b - shift(b, 6)) < 0
    bs = sr.bars_since(ev)
    return np.where(a > b, -bs, np.nan)


def f_px_cross(S, p):
    m = _ma(S, p["ma"], p["n"])
    bs = sr.bars_since(_cross_up(S.c, m))
    return np.where(S.c > m, -bs, np.nan)


def f_spread_pattern(S, p):
    d = _ma(S, p["m1"], p["n1"]) - _ma(S, p["m2"], p["n2"])
    sgn, cur, prev = sr.run_pair(d)
    want = -1 if p["mode"] == "fade" else 1
    ok = (d > 0) & (sgn == want) & (prev >= p["j"])
    return np.where(ok, cur, np.nan)


def _stoch(S, n):
    hh, ll = S.hh(n), S.ll(n)
    rng = hh - ll
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(rng > 0, (S.c - ll) / rng - 0.5, 0.0 * rng)


def f_stoch(S, p):
    return _stoch(S, p["n"])


def f_stoch_sm(S, p):
    return sr.roll_sum(_stoch(S, p["n"]), p["s"]) / p["s"]


def f_breakout(S, p):
    prior = shift(S.hh(p["n"]), 1)
    with np.errstate(invalid="ignore"):
        ev = S.c > prior
    return -sr.bars_since(ev)


def f_dist_high(S, p):
    return -(S.hh(p["n"]) - S.c) / S.U


def f_rsi(S, p):
    return S.rsi(p["n"]) - 50.0


def f_rsi_slope(S, p):
    r = S.rsi(p["n"])
    return r - shift(r, p["k"])


def _z(S, n):
    sd = S.std(n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(sd > 0, (S.c - S.ma("SMA", n)) / sd, 0.0 * sd)


def f_boll_z(S, p):
    return _z(S, p["n"])


def f_z_slope(S, p):
    z = _z(S, p["n"])
    return z - shift(z, p["k"])


def _macd(S, f, s, g):
    def build():
        from ..lab import indicators as ind
        line = S.ma("EMA", f) - S.ma("EMA", s)
        return line, line - ind.ema(line, g)
    return S.cached(("macd", f, s, g), build)


def f_macd(S, p):
    line, hist = _macd(S, p["f"], p["s"], p["g"])
    if p["part"] == "line":
        return line / S.U
    if p["part"] == "hist":
        return hist / S.U
    return (hist - shift(hist, 3)) / S.U          # hist_slope: zmiana histogramu w 3 świecach


def f_wick(S, p):
    lower = np.minimum(S.o, S.c) - S.l
    upper = S.h - np.maximum(S.o, S.c)
    return sr.roll_sum(lower - upper, p["n"]) / (p["n"] * S.U)


def _seg_open(S, anchor):
    return sr.anchor_ffill(S.starts(anchor), S.o)


def f_sess_chg(S, p):
    return (S.c - _seg_open(S, p["a"])) / PIP


def f_sess_chg_u(S, p):
    return (S.c - _seg_open(S, p["a"])) / S.U


def f_day_pos(S, p):
    st = S.starts(p["a"])
    hi, lo = sr.seg_cummax(st, S.h), sr.seg_cummin(st, S.l)
    rng = hi - lo
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(rng > 0, (S.c - lo) / rng - 0.5, np.nan)


def f_prev_day(S, p):
    st = S.starts("ny_day")
    if p["ref"] == "close":
        ref = sr.prev_seg_last(st, S.c)
    elif p["ref"] == "high":
        ref = sr.prev_seg_extreme(st, S.h, True)
    else:
        ref = sr.prev_seg_extreme(st, S.l, False)
    return (S.c - ref) / S.U


def _up(S, p):
    return S.c > _ma(S, p["ma"], p["n"])


def f_combo_pull(S, p):
    return np.where(_up(S, p), -(S.c - shift(S.c, p["m"])) / PIP, np.nan)


def f_combo_dip(S, p):
    short = _ma(S, p["sm"], p["sn"])
    with np.errstate(invalid="ignore"):
        ok = _up(S, p) & (S.c < short)                 # trend wzrostowy i cena pod krótką średnią
    return np.where(ok, (short - S.c) / S.U, np.nan)


def f_combo_rsi(S, p):
    return np.where(_up(S, p), 50.0 - S.rsi(p["r"]), np.nan)


def f_combo_stoch(S, p):
    return np.where(_up(S, p), -_stoch(S, p["s"]), np.nan)


# ===========================================================================
#  Opisy po polsku. q = wielkość w zwykłej orientacji; strona `−` to ta sama
#  wielkość ≤ −próg (wielkości są antysymetryczne względem odbicia).
# ===========================================================================
def num(x, d=None):
    """Liczba po polsku: przecinek dziesiętny, bez zbędnych zer (d — stała liczba miejsc)."""
    s = f"{x:.{d}f}" if d is not None else f"{x:.4g}"
    return s.replace(".", ",")


def sg(x, d=None):
    return ("+" if x > 0 else ("−" if x < 0 else "")) + num(abs(x), d)


def ma_name(k, n):
    return f"{k}{n}"


def _w(n):
    return "na ostatniej świecy" if n == 1 else f"w ostatnich {n} świecach"


def _zz(n):
    return "z ostatniej świecy" if n == 1 else f"z ostatnich {n} świec"


def generic(label, unit="", off=0.0, scale=1.0, d=None):
    """`+`: wielkość ≥ próg; `−`: ta sama wielkość ≤ −próg (wielkość antysymetryczna).
    off ≠ 0 — wielkość ograniczona (RSI, %), pokazywana bez znaku."""
    def desc(p, th, side):
        n = p.get("n", 1)
        lab = label.format(w=_w(n), z=_zz(n), **p)
        v = off + scale * th if side > 0 else off - scale * th
        val = num(v, d) if off else sg(v, d)
        return f"{lab} {'≥' if side > 0 else '≤'} {val}{unit}"
    return desc


def _d_green(p, th, side):
    kol = "zielonych (zamknięcie > otwarcie)" if side > 0 else "czerwonych (zamknięcie < otwarcie)"
    return f"Świec {kol} wśród ostatnich {p['n']}: ≥ {int(th)}"


def _d_streak(p, th, side):
    return f"Seria {'zielonych' if side > 0 else 'czerwonych'} świec z rzędu: ≥ {int(th)}"


def _d_hhhl(p, th, side):
    w = "wyższym maksimum i wyższym minimum" if side > 0 else "niższym minimum i niższym maksimum"
    return f"Seria świec z {w} niż poprzednia: ≥ {int(th)}"


def _d_cross(p, th, side):
    a, b = ma_name(p["m1"], p["n1"]), ma_name(p["m2"], p["n2"])
    tr = f", gdy {b} była {'spadkowa' if side > 0 else 'wzrostowa'}" if p["against"] else ""
    return (f"{a} przecięła {b} w {'górę' if side > 0 else 'dół'}{tr}; świec od przecięcia: ≤ {int(-th)} "
            f"(0 = na tej świecy), {a} nadal {'nad' if side > 0 else 'pod'} {b}")


def _d_pxcross(p, th, side):
    m = ma_name(p["ma"], p["n"])
    return (f"Cena przecięła {m} w {'górę' if side > 0 else 'dół'}; świec od przecięcia: ≤ {int(-th)} "
            f"(0 = na tej świecy), cena nadal {'nad' if side > 0 else 'pod'} {m}")


def _d_pattern(p, th, side):
    a, b = ma_name(p["m1"], p["n1"]), ma_name(p["m2"], p["n2"])
    pos = "nad" if side > 0 else "pod"
    if p["mode"] == "fade":
        return f"{a} {pos} {b}: odległość rosła (seria ≥ {p['j']} świec), potem maleje (seria ≥ {int(th)})"
    return f"{a} {pos} {b}: odległość malała (seria ≥ {p['j']} świec), potem rośnie (seria ≥ {int(th)})"


def _d_breakout(p, th, side):
    w = "powyżej maksimum" if side > 0 else "poniżej minimum"
    return f"Świec od ostatniego zamknięcia {w} poprzednich {p['n']} świec: ≤ {int(-th)} (0 = na tej świecy)"


def _d_disthigh(p, th, side):
    w = "maksimum" if side > 0 else "minimum"
    return f"Odległość ceny od {w} ostatnich {p['n']} świec [ATR100] ≤ {num(-th)}"


def _d_prevday(p, th, side):
    ref = {"close": "zamknięcia", "high": "maksimum", "low": "minimum"}
    if side < 0:
        ref = {"close": "zamknięcia", "high": "minimum", "low": "maksimum"}
    lab = f"Cena względem {ref[p['ref']]} poprzedniej doby handlowej [ATR100]"
    return f"{lab} {'≥' if side > 0 else '≤'} {sg(th if side > 0 else -th)}"


def _d_combo_pull(p, th, side):
    t = ma_name(p["ma"], p["n"])
    if side > 0:
        return f"Cena nad {t}, a zmiana ceny {_w(p['m'])} ≤ {sg(-th)} pips"
    return f"Cena pod {t}, a zmiana ceny {_w(p['m'])} ≥ {sg(th)} pips"


def _d_combo_dip(p, th, side):
    t, k = ma_name(p["ma"], p["n"]), ma_name(p["sm"], p["sn"])
    if side > 0:
        return f"Cena nad {t}, ale pod {k} o ≥ {num(max(th, 0))} ATR100"
    return f"Cena pod {t}, ale nad {k} o ≥ {num(max(th, 0))} ATR100"


def _d_combo_rsi(p, th, side):
    t = ma_name(p["ma"], p["n"])
    if side > 0:
        return f"Cena nad {t}, a RSI{p['r']} ≤ {num(50 - th)}"
    return f"Cena pod {t}, a RSI{p['r']} ≥ {num(50 + th)}"


def _d_combo_stoch(p, th, side):
    t = ma_name(p["ma"], p["n"])
    if side > 0:
        return f"Cena nad {t}, a położenie zamknięcia w zakresie {p['s']} świec ≤ {num(100 * (0.5 - th), 0)}%"
    return f"Cena pod {t}, a położenie zamknięcia w zakresie {p['s']} świec ≥ {num(100 * (0.5 + th), 0)}%"


# rodzaj → (funkcja, całkowita?, opis)
KINDS = {
    "chg_pips": (f_chg_pips, False, generic("Zmiana ceny {w}", " pips")),
    "er_signed": (f_er_signed, False, generic("Kierunkowość ruchu (ER ze znakiem) {z}")),
    "body_er": (f_body_er, False, generic("Przewaga korpusów Σ(c−o)/Σ|c−o| {z}")),
    "green_cnt": (f_green_cnt, True, _d_green),
    "streak_green": (f_streak_green, True, _d_streak),
    "hhhl_streak": (f_hhhl_streak, True, _d_hhhl),
    "clv": (f_clv, False, generic("Położenie zamknięcia w świecy (−1 = dołek, +1 = szczyt), średnia {z}")),
    "px_vs_ma": (f_px_vs_ma, False, generic("Odległość ceny od {ma}{n} [ATR100]")),
    "ma_slope": (f_ma_slope, False, generic("Nachylenie {ma}{n} w {k} świecach [ATR100]")),
    "ma_spread": (f_ma_spread, False, generic("Rozstaw {m1}{n1} − {m2}{n2} [ATR100]")),
    "ma_cross": (f_ma_cross, True, _d_cross),
    "px_cross": (f_px_cross, True, _d_pxcross),
    "spread_pattern": (f_spread_pattern, True, _d_pattern),
    "stoch": (f_stoch, False, generic("Położenie zamknięcia w zakresie ostatnich {n} świec", "%", 50, 100, 0)),
    "stoch_sm": (f_stoch_sm, False, generic("Położenie zamknięcia w zakresie ostatnich {n} świec, średnia z {s}", "%", 50, 100, 0)),
    "breakout": (f_breakout, True, _d_breakout),
    "dist_high": (f_dist_high, False, _d_disthigh),
    "rsi": (f_rsi, False, generic("RSI{n}", "", 50, 1)),
    "rsi_slope": (f_rsi_slope, False, generic("Zmiana RSI{n} w {k} świecach")),
    "boll_z": (f_boll_z, False, generic("Odchylenie ceny od SMA{n} w odchyleniach standardowych")),
    "z_slope": (f_z_slope, False, generic("Zmiana odchylenia od SMA{n} (w odch. std.) w {k} świecach")),
    "macd": (f_macd, False, None),
    "wick": (f_wick, False, generic("Przewaga dolnych knotów nad górnymi {z} [ATR100 na świecę]")),
    "sess_chg": (f_sess_chg, False, None),
    "sess_chg_u": (f_sess_chg_u, False, None),
    "day_pos": (f_day_pos, False, None),
    "prev_day": (f_prev_day, False, _d_prevday),
    "combo_dip": (f_combo_dip, False, _d_combo_dip),
    "combo_pull": (f_combo_pull, False, _d_combo_pull),
    "combo_rsi": (f_combo_rsi, False, _d_combo_rsi),
    "combo_stoch": (f_combo_stoch, False, _d_combo_stoch),
}


def _d_macd(p, th, side):
    nm = f"MACD({p['f']},{p['s']},{p['g']})"
    lab = {"line": f"Linia {nm} [ATR100]", "hist": f"Histogram {nm} [ATR100]",
           "hist_slope": f"Zmiana histogramu {nm} w 3 świecach [ATR100]"}[p["part"]]
    return generic(lab)(p, th, side)


def _d_sess(unit, scale_lab):
    def desc(p, th, side):
        return generic(f"Zmiana ceny od początku {ANCH[p['a']]}{scale_lab}", unit)(p, th, side)
    return desc


def _d_daypos(p, th, side):
    return generic(f"Położenie ceny w zakresie {ANCH[p['a']]} (od jej początku)", "%", 50, 100, 0)(p, th, side)


KINDS["macd"] = (f_macd, False, _d_macd)
KINDS["sess_chg"] = (f_sess_chg, False, _d_sess(" pips", ""))
KINDS["sess_chg_u"] = (f_sess_chg_u, False, _d_sess("", " [ATR100]"))
KINDS["day_pos"] = (f_day_pos, False, _d_daypos)


def describe(kind, p, th, side):
    return KINDS[kind][2](p, th, side)


# ===========================================================================
#  Rodziny i kandydaci (kolejność kandydatów jest częścią katalogu — stała)
# ===========================================================================
def _mapairs_same():
    return [dict(m1=k, n1=a, m2=k, n2=b) for (a, b) in MA_PAIRS for k in sr.MA_KINDS]


def _mapairs_x():
    return [dict(m1=a, n1=b, m2=c, n2=d) for (a, b, c, d) in X_PAIRS]


FAMILIES = [
    ("momentum", "Zmiana ceny (pips)", 35,
     [("chg_pips", dict(n=n)) for n in (1, 2, 3, 4, 6, 9, 12, 18, 24, 36, 48, 72, 96, 144, 288)]),
    ("kierunkowosc", "Kierunkowość ruchu i korpusów", 20,
     [("er_signed", dict(n=n)) for n in (6, 9, 12, 18, 24, 36, 48, 72, 96, 144, 288)] +
     [("body_er", dict(n=n)) for n in (6, 12, 24, 48, 96)]),
    ("kolory", "Kolory świec", 25,
     [("green_cnt", dict(n=n)) for n in (4, 6, 8, 10, 12, 15, 20, 30, 40, 50, 75, 100)]),
    ("serie", "Serie świec i położenie zamknięcia", 15,
     [("streak_green", {}), ("hhhl_streak", {})] + [("clv", dict(n=n)) for n in (1, 3, 6, 12, 24, 48)]),
    ("cena_ma", "Cena a średnia krocząca", 50,
     [("px_vs_ma", dict(ma=k, n=n)) for n in PER for k in sr.MA_KINDS]),
    ("nachylenie", "Nachylenie średniej", 40,
     [("ma_slope", dict(ma=k, n=n, k=kk)) for kk in (3, 12) for n in PER for k in sr.MA_KINDS]),
    ("rozstaw", "Rozstaw dwóch średnich", 50,
     [("ma_spread", p) for p in _mapairs_x() + _mapairs_same()]),
    ("przeciecia", "Przecięcia średnich i ceny", 40,
     [("ma_cross", dict(p, against=ag)) for ag in (0, 1) for p in _mapairs_x()] +
     [("px_cross", dict(ma=k, n=n)) for (k, n) in (("EMA", 20), ("SMA", 50), ("KAMA", 103), ("EMA", 200),
                                                    ("SMA", 288), ("HMA", 50), ("DEMA", 103), ("TEMA", 200),
                                                    ("ZLEMA", 38))]),
    ("dynamika", "Dynamika rozstawu średnich (rosła / malała)", 40,
     [("spread_pattern", dict(p, j=j, mode=md)) for md in ("fade", "grow") for j in (2, 3, 5)
      for p in _mapairs_x() + [dict(m1=k, n1=a, m2=k, n2=b) for k in ("EMA", "SMA", "KAMA")
                               for (a, b) in ((9, 38), (20, 103), (50, 200))]]),
    ("zakres", "Położenie w zakresie (stochastic)", 30,
     [("stoch", dict(n=n)) for n in (12, 18, 24, 36, 48, 96, 144, 288)] +
     [("stoch_sm", dict(n=n, s=s)) for (n, s) in ((24, 3), (48, 6), (96, 12), (288, 24))]),
    ("wybicia", "Wybicia i odległość od ekstremum", 25,
     [("breakout", dict(n=n)) for n in (12, 24, 36, 48, 72, 96, 144, 288)] +
     [("dist_high", dict(n=n)) for n in (12, 24, 48, 96, 144, 288)]),
    ("rsi", "RSI", 25,
     [("rsi", dict(n=n)) for n in (5, 7, 9, 14, 21, 30, 50, 100)] +
     [("rsi_slope", dict(n=n, k=k)) for (n, k) in ((14, 3), (14, 6), (14, 12), (7, 3), (7, 6), (30, 6), (30, 12))]),
    ("bollinger", "Odchylenie od średniej (Bollinger)", 25,
     [("boll_z", dict(n=n)) for n in (10, 12, 20, 30, 50, 75, 100, 150, 200, 288)] +
     [("z_slope", dict(n=n, k=k)) for (n, k) in ((20, 3), (20, 6), (50, 6), (50, 12), (100, 12))]),
    ("macd", "MACD", 25,
     [("macd", dict(f=f, s=s, g=g, part=pt)) for pt in ("hist", "line", "hist_slope")
      for (f, s, g) in ((12, 26, 9), (6, 13, 5), (24, 52, 18), (48, 104, 36), (5, 35, 5))]),
    ("knoty", "Knoty świec", 15,
     [("wick", dict(n=n)) for n in (1, 3, 6, 12, 24, 48)]),
    ("sesje", "Doba, tydzień, poprzednia doba", 15,
     [("sess_chg", dict(a=a)) for a in ANCH] + [("sess_chg_u", dict(a=a)) for a in ANCH] +
     [("day_pos", dict(a=a)) for a in ANCH] + [("prev_day", dict(ref=r)) for r in ("close", "high", "low")]),
    ("kombinacje", "Trend i korekta", 25,
     [("combo_dip", dict(ma=k, n=n, sm=sk, sn=sn)) for (sk, sn) in (("EMA", 20), ("EMA", 9), ("SMA", 38), ("EMA", 50))
      for (k, n) in TRENDS] +
     [("combo_pull", dict(ma=k, n=n, m=m)) for m in (3, 6) for (k, n) in TRENDS] +
     [("combo_rsi", dict(ma=k, n=n, r=14)) for (k, n) in TRENDS] +
     [("combo_stoch", dict(ma=k, n=n, s=24)) for (k, n) in TRENDS]),
]
assert sum(f[2] for f in FAMILIES) == PAIRS


# Rodziny z własnymi celami częstości. „Trend i korekta”: warunek trendu jest prawdziwy na ok. połowie
# świec, więc przy celu 25% „korekta” wypadałaby na medianie (np. „zmiana ≤ +1 pips”) — cel 15%
# i 12% wymuszają prawdziwą korektę.
FAMILY_TARGETS = {"kombinacje": (0.15, 0.12)}


def candidates():
    """(rodzina, rodzaj, parametry, cel) w stałej kolejności: najpierw wszystkie cechy rodziny
    z celem 25%, potem 15%, potem 40% (albo cele rodziny z FAMILY_TARGETS)."""
    for fam, _, _, feats in FAMILIES:
        for tg in FAMILY_TARGETS.get(fam, TARGETS):
            for kind, p in feats:
                yield fam, kind, p, tg


# ===========================================================================
#  Liczenie cech i okoliczności
# ===========================================================================
def _key(kind, p):
    return (kind, tuple(sorted(p.items())))


def feature(S: Series, kind: str, p: dict) -> np.ndarray:
    return S.cached(("feat",) + _key(kind, p), lambda: KINDS[kind][0](S, p))


def holds(S: Series, kind: str, p: dict, th: float) -> np.ndarray:
    f = feature(S, kind, p)
    with np.errstate(invalid="ignore"):
        return np.nan_to_num(f, nan=-np.inf) >= th


def evaluate(conds: list[dict], Sp: Series, Sm: Series) -> np.ndarray:
    """Macierz prawda/fałsz: wiersz = okoliczność (kolejność `conds`), kolumna = świeca serii."""
    out = np.zeros((len(conds), Sp.n), dtype=bool)
    for i, c in enumerate(conds):
        out[i] = holds(Sp if c["dir"] == "+" else Sm, c["kind"], c["p"], c["theta"])
    return out


def eligible(S: Series) -> np.ndarray:
    m = ~S.filled
    m[: sr.WARMUP] = False
    return m


# ===========================================================================
#  Kalibracja (4c.2, 4c.3) — tylko raz; wynik zapisany w fx/conditions.json
# ===========================================================================
def round_sig(x: float, sig: int = 2) -> float:
    if x == 0 or not math.isfinite(x):
        return x
    return round(x, -int(math.floor(math.log10(abs(x)))) + (sig - 1))


def _theta(pooled_sorted_desc: np.ndarray, target: float, is_int: bool) -> float | None:
    N = pooled_sorted_desc.size
    k = min(int(target * N), N - 1)
    th0 = pooled_sorted_desc[k]
    if not math.isfinite(th0):
        return None
    if not is_int:
        return float(round_sig(th0, 2))
    best, bd = None, 9.0
    for th in (math.floor(th0), math.ceil(th0)):
        cov = np.searchsorted(-pooled_sorted_desc, -th, side="right") / N   # udział ≥ th
        if abs(cov - target) < bd:
            best, bd = float(th), abs(cov - target)
    return best


def calibrate(Sp: Series, Sm: Series, log=print) -> list[dict]:
    el = eligible(Sp)
    N = int(el.sum())
    if N < 2000:
        raise RuntimeError(f"Za mało świec do kalibracji: {N} (po rozgrzewce {sr.WARMUP}).")
    quota = {f[0]: f[2] for f in FAMILIES}
    fam_name = {f[0]: f[1] for f in FAMILIES}

    # 1) każdy kandydat: próg, częstości obu stron, wektor `+`
    pool = []                                        # (fam, kind, p, tg, th, cov+, cov−, x+)
    seen = set()
    for fam, kind, p, tg in candidates():
        is_int = KINDS[kind][1]
        fp, fm = feature(Sp, kind, p)[el], feature(Sm, kind, p)[el]
        pooled = np.nan_to_num(np.concatenate([fp, fm]), nan=-np.inf)
        th = _theta(np.sort(pooled)[::-1], tg, is_int)
        if th is None:
            continue
        key = _key(kind, p) + (th,)
        if key in seen:                              # ten sam warunek z innego celu
            continue
        seen.add(key)
        xp = np.nan_to_num(fp, nan=-np.inf) >= th
        xm = np.nan_to_num(fm, nan=-np.inf) >= th
        cp, cm = float(xp.mean()), float(xm.mean())
        if not (RANGE[0] <= cp <= RANGE[1] and RANGE[0] <= cm <= RANGE[1]):
            continue
        pool.append((fam, kind, p, tg, th, cp, cm, xp))
    log(f"  kandydatów w zakresie {int(RANGE[0]*100)}–{int(RANGE[1]*100)}%: {len(pool)}")

    # 2) wybór: limity rodzin, korelacja z już wybranymi
    Z = np.zeros((PAIRS, N), dtype=np.float32)
    chosen, used = [], np.zeros(len(pool), dtype=bool)
    count = {f: 0 for f in quota}

    def try_take(i, limit):
        x = pool[i][7].astype(np.float32)
        sd = x.std()
        if sd == 0:
            return False
        z = (x - x.mean()) / sd
        if chosen and float((Z[: len(chosen)] @ z).max()) / N > limit:
            return False
        Z[len(chosen)] = z
        chosen.append(i)
        used[i] = True
        count[pool[i][0]] += 1
        return True

    for limit in CORR_STEPS:                         # rodziny w ramach limitów
        for i, c in enumerate(pool):
            if not used[i] and count[c[0]] < quota[c[0]]:
                try_take(i, limit)
    for limit in CORR_STEPS + (1.01,):               # dopełnienie do 500 — dowolna rodzina
        if len(chosen) >= PAIRS:
            break
        fams = [f[0] for f in FAMILIES]
        progress = True
        while len(chosen) < PAIRS and progress:
            progress = False
            for fam in fams:                         # po kolei rodziny, jeden kandydat na raz
                for i, c in enumerate(pool):
                    if not used[i] and c[0] == fam:
                        if try_take(i, limit):
                            progress = True
                            break
                if len(chosen) >= PAIRS:
                    break
    if len(chosen) < PAIRS:
        raise RuntimeError(f"Kalibracja dała tylko {len(chosen)} par z {PAIRS} — za mało danych.")

    # 3) ID: kolejność rodzin, w rodzinie kolejność wyboru; para = FX-(2i−1) `+`, FX-(2i) `−`
    order = sorted(chosen, key=lambda i: ([f[0] for f in FAMILIES].index(pool[i][0]), chosen.index(i)))
    conds = []
    for k, i in enumerate(order):
        fam, kind, p, tg, th, cp, cm, _ = pool[i]
        a, b = f"FX-{2*k+1:04d}", f"FX-{2*k+2:04d}"
        for cid, pid, d, cov in ((a, b, "+", cp), (b, a, "−", cm)):
            conds.append({"id": cid, "pair": pid, "dir": d, "family": fam, "familyName": fam_name[fam],
                          "kind": kind, "p": p, "theta": th, "target": tg, "coverage": round(cov, 4),
                          "desc": describe(kind, p, th, 1 if d == "+" else -1)})
    return conds


def family_summary(conds: list[dict]) -> list[tuple]:
    rows = []
    for fam, name, q, _ in FAMILIES:
        cs = [c for c in conds if c["family"] == fam]
        cov = [c["coverage"] for c in cs]
        rows.append((name, q, len(cs) // 2, (min(cov) if cov else 0), (float(np.mean(cov)) if cov else 0),
                     (max(cov) if cov else 0)))
    return rows


def document(conds, df, generated_by: str) -> dict:
    from .. import __version__
    t0, t1 = int(df["time"].iloc[0]), int(df["time"].iloc[-1])
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    return {
        "catalog": CATALOG, "version": __version__,
        "calibratedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "by": generated_by,
        "data": {"from": iso(t0), "to": iso(t1), "candles": int(len(df)), "filled": int(df["filled"].sum()),
                 "warmup": sr.WARMUP},
        "rules": {"targets": list(TARGETS), "familyTargets": {k: list(v) for k, v in FAMILY_TARGETS.items()}, "range": list(RANGE), "corrSteps": list(CORR_STEPS),
                  "unit": f"ATR{sr.U_PERIOD}", "pip": PIP, "condition": "f >= theta"},
        "families": [{"id": f, "name": n, "quota": q, "pairs": sum(1 for c in conds if c["family"] == f) // 2}
                     for f, n, q, _ in FAMILIES],
        "conditions": conds,
    }


def write_preview(conds, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ID", "Para", "Kierunek", "Rodzina", "Okoliczność", "Rodzaj", "Parametry", "Próg",
                    "Częstość %"])
        for c in conds:
            w.writerow([c["id"], c["pair"], c["dir"], c["familyName"], c["desc"], c["kind"],
                        json.dumps(c["p"], ensure_ascii=False), str(c["theta"]).replace(".", ","),
                        f"{100 * c['coverage']:.1f}".replace(".", ",")])


def load_conditions(repo_dir) -> dict | None:
    p = repo_dir / "fx" / "conditions.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ===========================================================================
#  CLI
# ===========================================================================
def main() -> None:
    from . import store
    from .sync import FX_DIR, load, sync

    ap = argparse.ArgumentParser(description="Katalog okoliczności EURUSD fx-cond/1 — kalibracja")
    ap.add_argument("--commit", action="store_true",
                    help="kalibracja właściwa: zapis fx/conditions.json na branch fx (tylko raz)")
    ap.add_argument("--no-sync", action="store_true", help="bez synchronizacji z Firestore")
    a = ap.parse_args()

    print(f"IA 4 — katalog okoliczności {CATALOG}\n")
    repo = store.fx_repo(push=a.commit)
    if a.commit:
        repo.ensure()
        if load_conditions(repo.root):
            print("fx/conditions.json już istnieje na branchu fx — katalog jest nienaruszalny (zasada 14).")
            sys.exit(1)
    df = load() if a.no_sync else sync()
    Sp, Sm = sr.pair_of(df)
    t = datetime.now()
    conds = calibrate(Sp, Sm)
    print(f"  kalibracja: {(datetime.now() - t).total_seconds():.0f} s\n")
    print(f"  {'rodzina':48s} {'limit':>5s} {'par':>4s}   częstość min / śr / max")
    for name, q, n, lo, mu, hi in family_summary(conds):
        print(f"  {name:48s} {q:5d} {n:4d}   {100*lo:4.1f}% / {100*mu:4.1f}% / {100*hi:4.1f}%")
    cov = [c["coverage"] for c in conds]
    print(f"\n  okoliczności: {len(conds)} ({sum(c['dir'] == '+' for c in conds)} `+`, "
          f"{sum(c['dir'] == '−' for c in conds)} `−`), częstość {100*min(cov):.1f}–{100*max(cov):.1f}%")
    prev = FX_DIR / "catalog-preview.csv"
    write_preview(conds, prev)
    print(f"  podgląd: {prev}")
    if not a.commit:
        print("\nTo była kalibracja próbna — nic nie zostało zapisane na GitHub.\n"
              "Kalibracja właściwa (raz, potem katalog jest nienaruszalny): python -m ia4.fx.catalog --commit")
        return
    repo.write_json("conditions.json", document(conds, df, "python -m ia4.fx.catalog --commit"))
    ok = repo.commit_push(f"fx: katalog {CATALOG} — kalibracja ({len(conds)} okoliczności)")
    print("\nZapisano fx/conditions.json na branchu fx." if ok else f"\n! push nieudany: {repo.last_error}")


if __name__ == "__main__":
    main()
