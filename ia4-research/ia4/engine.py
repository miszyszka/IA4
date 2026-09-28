"""
IA 4 — silnik transakcji (Etap 1b, instrukcja 1.7; liczy wyniki dopiero w Etapie 2).
Wersja projektu: 0.38 (2026-09-28) — musi zgadzać się z IA4_INSTRUKCJA.md

Kontrakt silnika (`S1_KATALOG_BAZOWY.md`) punkt po punkcie:
  2–3. Wejście po otwarciu świecy wejścia: t+1 (NEXT_OPEN) albo t (SESSION_OPEN,
       luki) — `signals.entry_index`.
  4.   SL i TP od ceny wejścia, sprawdzane na każdej świecy od świecy wejścia
       włącznie, po jej high i low.
  5.   SL i TP osiągalne w tej samej świecy → SL; transakcja oznaczona jako
       wieloznaczna (5.4).
  6.   Świeca otwiera się za poziomem SL albo TP (luka) → wyjście po cenie tego
       otwarcia. Świeca wejścia nie może mieć luki: jej otwarcie JEST ceną wejścia.
  7.   Limit czasu H świec: bez SL/TP wyjście po zamknięciu H-tej świecy, licząc
       świecę wejścia jako pierwszą. H w faktycznych świecach (D27), nie w czasie.
  8.   Jedna pozycja naraz na strategię i instrument: następne wejście musi być
       na świecy PÓŹNIEJSZEJ niż świeca wyjścia; sygnały w trakcie pozycji giną.
  12.  Wynik bez kosztów + `ret_net` z kosztem za całą transakcję (0,05%, 5.5).
  13.  Pozycja trwa mimo dziury w danych — liczone są tylko istniejące świece.
  14.  Pozycja nie przechodzi przez split: odcinek kończy się przed sesją ze
       splitem (bars.py). Jeśli do końca odcinka albo danych nie padł SL/TP/H,
       wyjście po zamknięciu ostatniej świecy z powodem END — osobny powód, żeby
       dało się takie transakcje policzyć albo odrzucić w Etapie 2.

Wydajność (Etap 2 = 286 sygnałów × 2 kierunki × 100 wyjść × 53 instrumenty):
dla każdego instrumentu i kierunku raz liczone jest, na której świecy cena
PIERWSZY raz dotyka każdego z 10 poziomów SL i 10 poziomów TP, dla wejścia na
KAŻDEJ świecy (`Engine`). Wynik dowolnej strategii to potem tylko wybór kolumn
z tych tablic i przejście po sygnałach z pkt 8 — bez ponownego skanowania świec.
Z tych samych tablic wychodzi wejście losowe z 5.3 (wejście w każdą świecę).

Moduł niczego nie wczytuje: dostaje gotowe `Bars`. W Etapie 1 (1.1) jest
sprawdzany wyłącznie na sztucznych świecach w `tests/test_engine.py`.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from .bars import Bars
from .catalog import H_DEFAULT, SL_TP_GRID

COST_PCT = 0.05          # 5.5 / D6: za całą transakcję (tam i z powrotem)
NEVER = np.iinfo(np.int64).max // 4
REASONS = ("SL", "TP", "TIME", "END")


def h_default(tp_pct: float) -> int:
    """D5: TP ≤ 1% → 14 świec, ≤ 2,5% → 35, ≤ 5% → 70 (punkt wyjścia dla D10)."""
    for row in H_DEFAULT:
        if tp_pct <= row["tp_max"] + 1e-12:
            return int(row["bars"])
    return int(H_DEFAULT[-1]["bars"])


def _first_hits(B: Bars, direction: str, levels: list[float], kind: str, hmax: int) -> np.ndarray:
    """
    [n × len(levels)]: indeks pierwszej świecy j ∈ [e, min(e+hmax−1, koniec odcinka)],
    w której cena dotyka poziomu, dla wejścia po otwarciu świecy e; NEVER = wcale.
    kind 'sl' / 'tp'; poziom = O[e] × (1 ± x%) zależnie od kierunku.
    """
    n = B.n
    E = B.o
    use_low = (direction == "L") == (kind == "sl")          # LONG-SL i SHORT-TP patrzą na low
    sign = -1.0 if use_low else 1.0
    src = B.l if use_low else B.h
    pad = np.full(hmax - 1, np.inf if use_low else -np.inf)
    win = sliding_window_view(np.concatenate([src, pad]), hmax)          # (n, hmax)
    idx = np.arange(n)[:, None] + np.arange(hmax)[None, :]
    inside = idx <= B.seg_end[:, None]
    out = np.full((n, len(levels)), NEVER, dtype=np.int64)
    for k, x in enumerate(levels):
        thr = E * (1 + sign * x / 100.0)
        hit = (win <= thr[:, None]) if use_low else (win >= thr[:, None])
        hit &= inside
        anyhit = hit.any(axis=1)
        first = np.argmax(hit, axis=1)
        out[anyhit, k] = np.arange(n)[anyhit] + first[anyhit]
    return out


@dataclass
class Resolved:
    """Wynik wejścia na każdej z podanych świec, bez pkt 8 (każde niezależnie)."""
    entry: np.ndarray
    exit: np.ndarray
    entry_price: np.ndarray
    exit_price: np.ndarray
    reason: np.ndarray        # 0 SL, 1 TP, 2 TIME, 3 END
    ambiguous: np.ndarray
    ret: np.ndarray           # ułamek, bez kosztów

    @property
    def bars(self) -> np.ndarray:
        return self.exit - self.entry + 1


class Engine:
    """Tablice pierwszego dotknięcia poziomów SL/TP dla jednego instrumentu."""

    def __init__(self, B: Bars, sl_grid=SL_TP_GRID, tp_grid=SL_TP_GRID, hmax: int | None = None):
        self.B = B
        self.sl_grid = list(sl_grid)
        self.tp_grid = list(tp_grid)
        self.hmax = hmax or max(h_default(x) for x in self.tp_grid)
        self._t: dict = {}

    def table(self, direction: str, kind: str) -> np.ndarray:
        key = (direction, kind)
        if key not in self._t:
            grid = self.sl_grid if kind == "sl" else self.tp_grid
            self._t[key] = _first_hits(self.B, direction, grid, kind, self.hmax)
        return self._t[key]

    def resolve(self, entries: np.ndarray, direction: str, sl: float, tp: float,
                H: int | None = None) -> Resolved:
        B = self.B
        e = np.asarray(entries, dtype=np.int64)
        H = int(H or h_default(tp))
        if H > self.hmax:
            raise ValueError(f"H = {H} > hmax = {self.hmax} tablic — zbuduj Engine z większym hmax")
        i, j = self.sl_grid.index(sl), self.tp_grid.index(tp)
        s_hit = self.table(direction, "sl")[e, i]
        p_hit = self.table(direction, "tp")[e, j]
        lim = np.minimum(e + H - 1, B.seg_end[e])
        s_in, p_in = s_hit <= lim, p_hit <= lim
        s_at = np.where(s_in, s_hit, NEVER)
        p_at = np.where(p_in, p_hit, NEVER)
        x = np.minimum(s_at, p_at)
        hit = x < NEVER
        xi = np.where(hit, x, lim)

        E = B.o[e]
        if direction == "L":
            slv, tpv = E * (1 - sl / 100.0), E * (1 + tp / 100.0)
        else:
            slv, tpv = E * (1 + sl / 100.0), E * (1 - tp / 100.0)
        Ox = B.o[xi]
        later = xi > e                                        # świeca wejścia nie ma luki (pkt 6)
        if direction == "L":
            gap_sl, gap_tp = later & (Ox <= slv), later & (Ox >= tpv)
        else:
            gap_sl, gap_tp = later & (Ox >= slv), later & (Ox <= tpv)

        both = hit & (s_at == p_at)
        sl_first = hit & (s_at < p_at)
        tp_first = hit & (p_at < s_at)

        reason = np.full(len(e), 2, dtype=np.int8)
        price = B.c[xi].copy()
        amb = np.zeros(len(e), dtype=bool)
        # SL pierwszy
        reason[sl_first] = 0
        price[sl_first] = np.where(gap_sl, Ox, slv)[sl_first]
        # TP pierwszy
        reason[tp_first] = 1
        price[tp_first] = np.where(gap_tp, Ox, tpv)[tp_first]
        # oba w tej samej świecy: luka rozstrzyga (otwarcie było pierwsze), inaczej SL (pkt 5)
        b_gsl, b_gtp = both & gap_sl, both & ~gap_sl & gap_tp
        b_amb = both & ~gap_sl & ~gap_tp
        reason[b_gsl], price[b_gsl] = 0, Ox[b_gsl]
        reason[b_gtp], price[b_gtp] = 1, Ox[b_gtp]
        reason[b_amb], price[b_amb], amb[b_amb] = 0, slv[b_amb], True
        # bez SL/TP: limit czasu albo koniec odcinka / danych
        none = ~hit
        reason[none & (lim < e + H - 1)] = 3

        ret = price / E - 1.0 if direction == "L" else 1.0 - price / E
        return Resolved(entry=e, exit=xi, entry_price=E, exit_price=price, reason=reason,
                        ambiguous=amb, ret=ret)


def one_position(entries: np.ndarray, exits: np.ndarray) -> np.ndarray:
    """
    Pkt 8: indeksy przyjętych wejść. `entries` rosnąco; każde kolejne przyjęte
    wejście jest na świecy późniejszej niż świeca wyjścia poprzedniego.
    """
    e = entries.tolist()
    x = exits.tolist()
    out = []
    k = 0
    while k < len(e):
        out.append(k)
        k = bisect_right(e, x[k], lo=k + 1)
    return np.array(out, dtype=np.int64)


def trades(engine: Engine, signal: dict, sig_mask: np.ndarray, direction: str, sl: float, tp: float,
           H: int | None = None, cost_pct: float = COST_PCT) -> pd.DataFrame:
    """
    Transakcje jednej strategii (sygnał × kierunek × SL × TP) na jednym instrumencie.
    `sig_mask` — z `signals.mask` (świeca sygnału t). Wynik: jedna linia na transakcję.
    """
    from .signals import entry_index
    B = engine.B
    t = np.flatnonzero(sig_mask)
    e = entry_index(signal, t)
    ok = e < B.n
    t, e = t[ok], e[ok]
    if len(e) == 0:
        return pd.DataFrame(columns=TRADE_COLUMNS)
    r = engine.resolve(e, direction, sl, tp, H)
    keep = one_position(r.entry, r.exit)
    t, r_e, r_x = t[keep], r.entry[keep], r.exit[keep]
    df = pd.DataFrame({
        "symbol": B.symbol,
        "signal_date": B.date[t], "signal_slot": B.slot[t],
        "entry_date": B.date[r_e], "entry_slot": B.slot[r_e], "entry_price": r.entry_price[keep],
        "exit_date": B.date[r_x], "exit_slot": B.slot[r_x], "exit_price": r.exit_price[keep],
        "reason": [REASONS[k] for k in r.reason[keep]],
        "ambiguous": r.ambiguous[keep],
        "bars": (r_x - r_e + 1),
        "ret": r.ret[keep],
    })
    df["ret_net"] = df["ret"] - cost_pct / 100.0
    return df


TRADE_COLUMNS = ["symbol", "signal_date", "signal_slot", "entry_date", "entry_slot", "entry_price",
                 "exit_date", "exit_slot", "exit_price", "reason", "ambiguous", "bars", "ret", "ret_net"]
