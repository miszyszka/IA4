"""
IA 4 — świece jednego instrumentu przygotowane dla sygnałów i silnika (Etap 1b).
Wersja projektu: 0.37 (2026-09-28) — musi zgadzać się z IA4_INSTRUKCJA.md

`prepare()` zamienia ramkę z `data.load()` (jeden instrument) na tablice numpy
plus to, czego wskaźniki same nie wiedzą (indicators.py liczy na ciągłym
szeregu wierszy, kontrakt pkt 9):

- **dziury w danych (D27, pkt 13):** `hole_before[i]` = między wierszem i−1
  a i czegoś brakuje — świecy w sesji, końcówki sesji, całej sesji dnia
  sesyjnego (kalendarz `nyse`). Dziura jest przypisana do wiersza PO niej,
  więc rozpoznanie jej nie wymaga wiedzy o przyszłości: w chwili świecy t
  wiadomo, czy między t−1 a t coś zginęło.
- **splity (D24, pkt 14):** szereg jest cięty na odcinki na pierwszej świecy
  sesji z `s1/splits.json`. Wskaźniki liczą się w każdym odcinku od nowa,
  pozycja nie przechodzi przez granicę. To ostrzejsze niż samo „okno nie
  obejmuje sesji ze splitem”: EMA i Wilder pamiętają całą przeszłość, więc po
  skoku −90% (NFLX) RSI byłby zaniżony jeszcze długo po końcu rozgrzewki.
- **pierwsza / ostatnia świeca sesji** z numeru świecy i kalendarza (sesja
  skrócona ma 4 świece), nie z tego, który wiersz akurat jest ostatni w danych —
  to też bez zaglądania w przyszłość.
- **SPY** (rodziny H7): zamknięcie SPY dopasowane do wierszy spółki po
  (dzień, numer świecy) — „w tych samych godzinach”.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import nyse

REPO = Path(__file__).resolve().parents[2]
SPLITS_PATH = REPO / "s1" / "splits.json"


def load_splits(path: Path = SPLITS_PATH) -> dict[str, list[str]]:
    """{symbol: [daty sesji ze splitem]} z s1/splits.json (D24)."""
    if not path.exists():
        return {}
    out: dict[str, list[str]] = {}
    for s in json.loads(path.read_text(encoding="utf-8")).get("splits", []):
        out.setdefault(s["symbol"], []).append(s["date"])
    return out


@dataclass
class Bars:
    """Tablice jednego instrumentu (albo jednego odcinka — patrz `segment`)."""
    symbol: str
    date: np.ndarray          # str 'RRRR-MM-DD'
    slot: np.ndarray          # int, 1…7
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray
    hole_before: np.ndarray   # bool: brak czegoś między wierszem i−1 a i
    seg: np.ndarray           # int: numer odcinka (cięcie na splitach)
    mkt_c: np.ndarray | None = None   # zamknięcie SPY w tej samej świecy (NaN = brak)
    _cache: dict = field(default_factory=dict, repr=False)

    @property
    def n(self) -> int:
        return len(self.c)

    # --- sesje ---------------------------------------------------------------
    @property
    def expected(self) -> np.ndarray:
        if "expected" not in self._cache:
            self._cache["expected"] = np.array([nyse.expected_bars(d) for d in self.date], dtype=int)
        return self._cache["expected"]

    @property
    def is_first(self) -> np.ndarray:
        return self.slot == 1

    @property
    def is_last(self) -> np.ndarray:
        return self.slot == self.expected

    @property
    def sess(self) -> np.ndarray:
        """Numer sesji w szeregu (0, 1, 2…) — zmienia się wraz z datą."""
        if "sess" not in self._cache:
            ch = np.ones(self.n, dtype=bool)
            ch[1:] = self.date[1:] != self.date[:-1]
            self._cache["sess"] = np.cumsum(ch) - 1
        return self._cache["sess"]

    def segments(self) -> list[tuple[int, int]]:
        """Odcinki [start, end) między splitami."""
        if self.n == 0:
            return []
        cut = np.flatnonzero(self.seg[1:] != self.seg[:-1]) + 1
        edges = [0, *cut.tolist(), self.n]
        return list(zip(edges[:-1], edges[1:]))

    def segment(self, a: int, b: int) -> "Bars":
        return Bars(
            symbol=self.symbol, date=self.date[a:b], slot=self.slot[a:b], o=self.o[a:b], h=self.h[a:b],
            l=self.l[a:b], c=self.c[a:b], v=self.v[a:b], hole_before=self.hole_before[a:b],
            seg=self.seg[a:b], mkt_c=None if self.mkt_c is None else self.mkt_c[a:b],
        )

    @property
    def seg_end(self) -> np.ndarray:
        """Dla każdego wiersza: indeks ostatniego wiersza jego odcinka."""
        if "seg_end" not in self._cache:
            out = np.empty(self.n, dtype=int)
            for a, b in self.segments():
                out[a:b] = b - 1
            self._cache["seg_end"] = out
        return self._cache["seg_end"]

    @property
    def seg_start(self) -> np.ndarray:
        if "seg_start" not in self._cache:
            out = np.empty(self.n, dtype=int)
            for a, b in self.segments():
                out[a:b] = a
            self._cache["seg_start"] = out
        return self._cache["seg_start"]


def find_holes(date: np.ndarray, slot: np.ndarray) -> np.ndarray:
    """hole_before[i] — czy między wierszem i−1 a i czegoś brakuje (D27)."""
    n = len(date)
    out = np.zeros(n, dtype=bool)
    if n < 2:
        return out
    # Dzień spoza kalendarza sesji (nie powinien się zdarzyć — audyt by go zgłosił) nie wywraca
    # liczenia: dostaje numer, który nie sąsiaduje z niczym, więc staje się dziurą z obu stron.
    known = nyse._ordinal()
    ordn = np.array([known.get(d, -10**9 - 10 * k) for k, d in enumerate(date)])
    exp = np.array([nyse.expected_bars(d) for d in date])
    same = date[1:] == date[:-1]
    inside = same & (slot[1:] != slot[:-1] + 1)
    across = (~same) & ((slot[:-1] != exp[:-1]) | (slot[1:] != 1) | (ordn[1:] - ordn[:-1] != 1))
    out[1:] = inside | across
    return out


def prepare(df: pd.DataFrame, splits: list[str] | None = None,
            market: pd.DataFrame | None = None) -> Bars:
    """
    df      świece JEDNEGO instrumentu (kolumny jak z data.load: symbol, date, slot, o, h, l, c, v)
    splits  daty sesji ze splitem tego instrumentu (None = z s1/splits.json)
    market  świece SPY (te same kolumny) dla rodzin H7; None = bez H7
    """
    if df["symbol"].nunique() > 1:
        raise ValueError("prepare() przyjmuje świece jednego instrumentu")
    df = df.sort_values(["date", "slot"]).reset_index(drop=True)
    sym = str(df["symbol"].iloc[0]) if len(df) else ""
    if splits is None:
        splits = load_splits().get(sym, [])
    date = df["date"].astype(str).to_numpy()
    slot = df["slot"].astype(int).to_numpy()
    seg = np.zeros(len(df), dtype=int)
    for d in sorted(splits):
        seg += (date >= d).astype(int)
    mkt = None
    if market is not None and len(df):
        m = market[["date", "slot", "c"]].rename(columns={"c": "mc"})
        mkt = df[["date", "slot"]].merge(m, on=["date", "slot"], how="left")["mc"].to_numpy(dtype=float)
    return Bars(
        symbol=sym, date=date, slot=slot,
        o=df["o"].to_numpy(dtype=float), h=df["h"].to_numpy(dtype=float),
        l=df["l"].to_numpy(dtype=float), c=df["c"].to_numpy(dtype=float),
        v=df["v"].to_numpy(dtype=float) if "v" in df else np.zeros(len(df)),
        hole_before=find_holes(date, slot), seg=seg, mkt_c=mkt,
    )
