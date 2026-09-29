"""
IA 4 — katalog okoliczności towarzyszących (Etap 2, przebieg 4; decyzja D34).
Wersja projektu: 0.45 (2026-09-29) — musi zgadzać się z IA4_INSTRUKCJA.md

Okoliczność = prosty warunek TAK/NIE opisujący stan rynku na świecy sygnału.
Nie jest sygnałem wejścia — jest opisem tła, w jakim sygnał odpalił. Każda
transakcja dostaje wektor ~200 takich wartości, policzonych na świecy sygnału
(t, czyli PRZED wejściem na t+1 — nic z przyszłości).

Każda okoliczność zwraca DWIE tablice:
  val      — bool: czy warunek jest spełniony na świecy t,
  defined  — bool: czy dało się go policzyć (jest historia, nie ma dziury).
Gdy `defined` jest fałszem, `val` jest fałszem, ale do ratingu taka transakcja
NIE jest liczona. Bez tego rozdziału „brak danych” udawałby „warunek nie
zachodzi” i pierwsze świece historii zaniżałyby każdą okoliczność.

Progi są stałe i zapisane w katalogu (`s1/okolicznosci.json`) razem z opisem.
Progi dobrane z góry, przed policzeniem czegokolwiek — nie wolno ich stroić
po obejrzeniu wyników (to byłoby to samo przeuczenie co w 5.7).

    python3 -m ia4.okolicznosci        # buduje s1/okolicznosci.json i wypisuje podsumowanie
"""
from __future__ import annotations

import json
import sys

import numpy as np

from . import nyse
from .bars import Bars
from .catalog import repo_root
from .signals import Ind, sh

OKOL_VERSION = "OK-v1"
OUT_PATH = repo_root() / "s1" / "okolicznosci.json"

GRUPY = {
    "T": "Trend średnich — nachylenie, ułożenie, położenie ceny względem średniej",
    "O": "Odchylenie ceny od średniej — jak daleko cena odbiegła",
    "P": "Położenie w zakresie — jak blisko szczytu albo dołka z ostatnich N świec",
    "R": "Tempo — o ile procent cena zmieniła się w N świecach",
    "Z": "Zmienność — ATR, szerokość wstęgi, zakres świecy",
    "W": "Wolumen — natężenie, kierunek, OBV",
    "S": "Wskaźniki — RSI, stochastyk, MACD, %B",
    "K": "Kształt świecy — korpus, cienie, serie świec",
    "C": "Czas — która świeca sesji, dzień tygodnia, koniec okresu",
    "M": "Rynek (SPY) — trend rynku, odchylenie, siła względna spółki",
    "L": "Luka na otwarciu sesji",
}

# ---------------------------------------------------------------------------
#  Pomocnicze
# ---------------------------------------------------------------------------


def _p(x) -> str:
    """Próg w identyfikatorze: 0.5 → 0p5, 2 → 2."""
    return str(x).replace(".0", "").replace(".", "p")


def _ok(n: int, warmup: int, B: Bars) -> np.ndarray:
    """defined: jest `warmup` świec historii w tym samym odcinku i bez dziury w oknie."""
    out = np.zeros(n, dtype=bool)
    for a, b in B.segments():
        lo = a + warmup
        if lo < b:
            out[lo:b] = True
    if warmup > 0:
        hole = B.hole_before.astype(bool)
        bad = np.zeros(n, dtype=bool)
        idx = np.flatnonzero(hole)
        for i in idx:
            bad[i:min(n, i + warmup + 1)] = True
        out &= ~bad
    return out


def _fin(a: np.ndarray) -> np.ndarray:
    return np.isfinite(np.asarray(a, dtype=float))


def _pct_change(c: np.ndarray, k: int) -> np.ndarray:
    prev = sh(c, k)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (c / prev - 1.0) * 100.0


def _roll_max(a: np.ndarray, k: int) -> np.ndarray:
    """Maksimum z ostatnich k świec włącznie z bieżącą; pierwsze k−1 = NaN."""
    n = len(a)
    out = np.full(n, np.nan)
    if n >= k:
        st = np.lib.stride_tricks.sliding_window_view(a, k)
        out[k - 1:] = st.max(axis=1)
    return out


def _roll_min(a: np.ndarray, k: int) -> np.ndarray:
    n = len(a)
    out = np.full(n, np.nan)
    if n >= k:
        st = np.lib.stride_tricks.sliding_window_view(a, k)
        out[k - 1:] = st.min(axis=1)
    return out


def _roll_mean(a: np.ndarray, k: int) -> np.ndarray:
    n = len(a)
    out = np.full(n, np.nan)
    if n >= k:
        st = np.lib.stride_tricks.sliding_window_view(np.asarray(a, dtype=float), k)
        out[k - 1:] = st.mean(axis=1)
    return out


MA_OKRESY = [7, 20, 35, 50, 140]          # 1 sesja, ~3, 5, ~7, 20 sesji
# Progi skalowane do długości okna: w jednej sesji 5% to rzadkość, w 20 sesjach — normalka.
# Dobrane z góry, przed policzeniem czegokolwiek (D34), tak żeby żadna okoliczność nie była
# ani prawie zawsze prawdziwa, ani prawie nigdy — inaczej nie niesie żadnej informacji.
PROGI_ODCHYLENIA = {7: (0.5, 1, 2), 20: (1, 2, 5), 50: (1, 3, 7), 140: (2, 5, 12)}
PROGI_ZAKRESU = {7: (1, 2, 5), 35: (2, 5, 12), 140: (5, 12, 20)}
PROGI_TEMPA = {7: (0.5, 1, 2), 35: (1, 3, 5), 140: (2, 5, 10)}
OKNA = [7, 35, 140]                       # 1 sesja, 5 sesji, 20 sesji

# ---------------------------------------------------------------------------
#  Definicje — każda pozycja: (id, grupa, opis, funkcja(Ind, B) -> (val, defined))
# ---------------------------------------------------------------------------
DEFS: list[tuple[str, str, str, object]] = []


def add(oid: str, grupa: str, opis: str, fn) -> None:
    assert not any(d[0] == oid for d in DEFS), f"powtórzone ID: {oid}"
    DEFS.append((oid, grupa, opis, fn))


def _build() -> None:
    # --- T: trend średnich ------------------------------------------------
    for kind in ("SMA", "EMA"):
        for n in MA_OKRESY:
            w = n * 2
            add(f"T_{kind}{n}_ROSNIE", "T",
                f"{kind}({n}) rośnie: średnia na tej świecy jest wyżej niż na poprzedniej.",
                lambda I, B, kind=kind, n=n, w=w: (
                    (lambda m: m > sh(m, 1))(I.ma(kind, n)),
                    _ok(B.n, w, B) & _fin(sh(I.ma(kind, n), 1))))
            if kind == "SMA":
                add(f"T_SMA{n}_ROSNIE_3", "T",
                    f"SMA({n}) rośnie nieprzerwanie od 3 świec.",
                    lambda I, B, n=n, w=w: (
                        (lambda m: (m > sh(m, 1)) & (sh(m, 1) > sh(m, 2)) & (sh(m, 2) > sh(m, 3)))(I.ma("SMA", n)),
                        _ok(B.n, w + 3, B)))
                add(f"T_SMA{n}_CENA_POWYZEJ", "T",
                    f"Zamknięcie jest powyżej SMA({n}).",
                    lambda I, B, n=n, w=w: (B.c > I.ma("SMA", n), _ok(B.n, w, B) & _fin(I.ma("SMA", n))))
    for a, b in ((7, 20), (7, 50), (20, 50), (20, 140), (50, 140)):
        add(f"T_SMA{a}_NAD_SMA{b}", "T",
            f"SMA({a}) jest powyżej SMA({b}) — układ wzrostowy tych dwóch średnich.",
            lambda I, B, a=a, b=b: (I.ma("SMA", a) > I.ma("SMA", b), _ok(B.n, b * 2, B)))
    add("T_WACHLARZ_WZROSTOWY", "T",
        "Pełny układ wzrostowy: EMA(7) > EMA(20) > EMA(50) > SMA(140).",
        lambda I, B: ((I.ma("EMA", 7) > I.ma("EMA", 20)) & (I.ma("EMA", 20) > I.ma("EMA", 50))
                      & (I.ma("EMA", 50) > I.ma("SMA", 140)), _ok(B.n, 280, B)))
    add("T_WACHLARZ_SPADKOWY", "T",
        "Pełny układ spadkowy: EMA(7) < EMA(20) < EMA(50) < SMA(140).",
        lambda I, B: ((I.ma("EMA", 7) < I.ma("EMA", 20)) & (I.ma("EMA", 20) < I.ma("EMA", 50))
                      & (I.ma("EMA", 50) < I.ma("SMA", 140)), _ok(B.n, 280, B)))
    add("T_CENA_NAD_WSZYSTKIMI", "T",
        "Zamknięcie powyżej wszystkich pięciu SMA (7, 20, 35, 50, 140).",
        lambda I, B: (np.all([B.c > I.ma("SMA", n) for n in MA_OKRESY], axis=0), _ok(B.n, 280, B)))
    add("T_CENA_POD_WSZYSTKIMI", "T",
        "Zamknięcie poniżej wszystkich pięciu SMA (7, 20, 35, 50, 140).",
        lambda I, B: (np.all([B.c < I.ma("SMA", n) for n in MA_OKRESY], axis=0), _ok(B.n, 280, B)))

    # --- O: odchylenie od średniej ---------------------------------------
    def dev(I, n, B, kind="SMA"):
        m = I.ma(kind, n)
        with np.errstate(invalid="ignore", divide="ignore"):
            return (B.c / m - 1.0) * 100.0

    for n, progi in PROGI_ODCHYLENIA.items():
        for prog in progi:
            add(f"O_SMA{n}_NAD_{_p(prog)}", "O",
                f"Zamknięcie co najmniej {prog}% powyżej SMA({n}).",
                lambda I, B, n=n, p=prog: (dev(I, n, B) >= p, _ok(B.n, n * 2, B) & _fin(dev(I, n, B))))
            add(f"O_SMA{n}_POD_{_p(prog)}", "O",
                f"Zamknięcie co najmniej {prog}% poniżej SMA({n}).",
                lambda I, B, n=n, p=prog: (dev(I, n, B) <= -p, _ok(B.n, n * 2, B) & _fin(dev(I, n, B))))
    for n in (20, 50):
        add(f"O_SMA{n}_ODCHYL_ROSNIE", "O",
            f"Odchylenie od SMA({n}) powiększa się: co do wartości bezwzględnej większe niż 3 świece temu.",
            lambda I, B, n=n: (np.abs(dev(I, n, B)) > np.abs(sh(dev(I, n, B), 3)), _ok(B.n, n * 2 + 3, B)))

    # --- P: położenie w zakresie -----------------------------------------
    for k in OKNA:
        for prog in PROGI_ZAKRESU[k]:
            add(f"P_POD_SZCZYTEM_{k}_{_p(prog)}", "P",
                f"Zamknięcie co najmniej {prog}% poniżej najwyższego high z ostatnich {k} świec.",
                lambda I, B, k=k, p=prog: (
                    (lambda hi: B.c <= hi * (1 - p / 100.0))(_roll_max(B.h, k)),
                    _ok(B.n, k, B) & _fin(_roll_max(B.h, k))))
            add(f"P_NAD_DOLKIEM_{k}_{_p(prog)}", "P",
                f"Zamknięcie co najmniej {prog}% powyżej najniższego low z ostatnich {k} świec.",
                lambda I, B, k=k, p=prog: (
                    (lambda lo: B.c >= lo * (1 + p / 100.0))(_roll_min(B.l, k)),
                    _ok(B.n, k, B) & _fin(_roll_min(B.l, k))))
        add(f"P_NOWY_SZCZYT_{k}", "P",
            f"Zamknięcie jest najwyższe z ostatnich {k} świec.",
            lambda I, B, k=k: (B.c >= _roll_max(B.c, k), _ok(B.n, k, B) & _fin(_roll_max(B.c, k))))
        add(f"P_NOWY_DOLEK_{k}", "P",
            f"Zamknięcie jest najniższe z ostatnich {k} świec.",
            lambda I, B, k=k: (B.c <= _roll_min(B.c, k), _ok(B.n, k, B) & _fin(_roll_min(B.c, k))))
        add(f"P_GORNA_POLOWA_{k}", "P",
            f"Zamknięcie w górnej połowie zakresu z ostatnich {k} świec (high–low).",
            lambda I, B, k=k: (
                (lambda hi, lo: (B.c - lo) > 0.5 * (hi - lo))(_roll_max(B.h, k), _roll_min(B.l, k)),
                _ok(B.n, k, B) & _fin(_roll_max(B.h, k))))

    # --- R: tempo ---------------------------------------------------------
    for k in OKNA:
        for prog in PROGI_TEMPA[k]:
            add(f"R_WZROST_{k}_{_p(prog)}", "R",
                f"Zamknięcie wyższe o co najmniej {prog}% niż {k} świec temu.",
                lambda I, B, k=k, p=prog: (_pct_change(B.c, k) >= p, _ok(B.n, k, B) & _fin(_pct_change(B.c, k))))
            add(f"R_SPADEK_{k}_{_p(prog)}", "R",
                f"Zamknięcie niższe o co najmniej {prog}% niż {k} świec temu.",
                lambda I, B, k=k, p=prog: (_pct_change(B.c, k) <= -p, _ok(B.n, k, B) & _fin(_pct_change(B.c, k))))
    add("R_PRZYSPIESZA_W_GORE", "R",
        "Wzrost przyspiesza: ostatnie 7 świec dało większy wzrost niż 7 świec przed nimi.",
        lambda I, B: (_pct_change(B.c, 7) > sh(_pct_change(B.c, 7), 7), _ok(B.n, 14, B)))
    add("R_PRZYSPIESZA_W_DOL", "R",
        "Spadek przyspiesza: ostatnie 7 świec dało większy spadek niż 7 świec przed nimi.",
        lambda I, B: (_pct_change(B.c, 7) < sh(_pct_change(B.c, 7), 7), _ok(B.n, 14, B)))
    add("R_ZWROT_PO_SPADKU", "R",
        "Zwrot w górę: spadek o ≥ 2% w 35 świecach, ale wzrost w ostatnich 7.",
        lambda I, B: ((_pct_change(B.c, 35) <= -2) & (_pct_change(B.c, 7) > 0), _ok(B.n, 35, B)))
    add("R_ZWROT_PO_WZROSCIE", "R",
        "Zwrot w dół: wzrost o ≥ 2% w 35 świecach, ale spadek w ostatnich 7.",
        lambda I, B: ((_pct_change(B.c, 35) >= 2) & (_pct_change(B.c, 7) < 0), _ok(B.n, 35, B)))

    # --- Z: zmienność -----------------------------------------------------
    def atrp(I, B, n=14):
        with np.errstate(invalid="ignore", divide="ignore"):
            return I.atr(n) / B.c * 100.0

    for prog in (0.5, 1.0, 1.5, 2.5):
        add(f"Z_ATR14_POWYZEJ_{str(prog).replace('.', 'p')}", "Z",
            f"ATR(14) to co najmniej {prog}% ceny — rynek ruchliwy.",
            lambda I, B, p=prog: (atrp(I, B) >= p, _ok(B.n, 28, B) & _fin(atrp(I, B))))
    add("Z_ATR_ROSNIE", "Z",
        "ATR(14) wyższy niż 7 świec temu — zmienność rośnie.",
        lambda I, B: (I.atr(14) > sh(I.atr(14), 7), _ok(B.n, 35, B)))
    add("Z_ATR_ROSNIE_MOCNO", "Z",
        "ATR(14) co najmniej o połowę wyższy niż 35 świec temu.",
        lambda I, B: (I.atr(14) >= 1.5 * sh(I.atr(14), 35), _ok(B.n, 70, B)))
    add("Z_ATR_MALEJE", "Z",
        "ATR(14) niższy niż 7 świec temu — zmienność spada.",
        lambda I, B: (I.atr(14) < sh(I.atr(14), 7), _ok(B.n, 35, B)))
    for prog in (1.0, 1.5, 2.5):
        add(f"Z_SWIECA_SZEROKA_{str(prog).replace('.', 'p')}", "Z",
            f"Zakres świecy (high−low) to co najmniej {prog} × ATR(14) z poprzedniej świecy.",
            lambda I, B, p=prog: ((B.h - B.l) >= p * sh(I.atr(14), 1), _ok(B.n, 29, B)))
    add("Z_SWIECA_WASKA", "Z",
        "Zakres świecy poniżej połowy ATR(14) z poprzedniej świecy — spokój.",
        lambda I, B: ((B.h - B.l) <= 0.5 * sh(I.atr(14), 1), _ok(B.n, 29, B)))
    add("Z_NAJWEZSZA_14", "Z",
        "Najwęższy zakres świecy z ostatnich 14 świec.",
        lambda I, B: ((B.h - B.l) <= _roll_min(B.h - B.l, 14), _ok(B.n, 14, B)))
    add("Z_NAJSZERSZA_14", "Z",
        "Najszerszy zakres świecy z ostatnich 14 świec.",
        lambda I, B: ((B.h - B.l) >= _roll_max(B.h - B.l, 14), _ok(B.n, 14, B)))
    for n, k in ((20, 2.0), (50, 2.0)):
        def bw(I, n=n, k=k):
            b = I.bb(n, k)
            with np.errstate(invalid="ignore", divide="ignore"):
                return (b["upper"] - b["lower"]) / b["mid"] * 100.0
        add(f"Z_WSTEGA{n}_SZEROKA", "Z",
            f"Szerokość wstęgi Bollingera({n}, 2) powyżej mediany z ostatnich 140 świec.",
            lambda I, B, n=n, k=k: (bw(I, n, k) > _roll_mean(bw(I, n, k), 140), _ok(B.n, 140 + n * 2, B)))
        add(f"Z_WSTEGA{n}_SCISK", "Z",
            f"Ścisk wstęgi Bollingera({n}, 2): szerokość najmniejsza z ostatnich 70 świec.",
            lambda I, B, n=n, k=k: (bw(I, n, k) <= _roll_min(bw(I, n, k), 70), _ok(B.n, 70 + n * 2, B)))

    # --- W: wolumen -------------------------------------------------------
    for prog in (0.7, 1.0, 1.5, 2.0, 3.0):
        add(f"W_RVOL_POWYZEJ_{str(prog).replace('.', 'p')}", "W",
            f"Wolumen świecy to co najmniej {prog} × średnia dla tej godziny z 20 sesji (RVOL).",
            lambda I, B, p=prog: (I.rvol() >= p, _ok(B.n, 140, B) & _fin(I.rvol())))
    add("W_WOLUMEN_ROSNIE", "W",
        "Wolumen wyższy niż na poprzedniej świecy.",
        lambda I, B: (B.v > sh(B.v, 1), _ok(B.n, 1, B) & (B.v > 0) & (sh(B.v, 1) > 0)))
    add("W_WOLUMEN_ROSNIE_3", "W",
        "Wolumen rośnie trzecią świecę z rzędu.",
        lambda I, B: ((B.v > sh(B.v, 1)) & (sh(B.v, 1) > sh(B.v, 2)) & (sh(B.v, 2) > sh(B.v, 3)),
                      _ok(B.n, 3, B) & (_roll_min(B.v, 4) > 0)))
    add("W_WZROST_NA_WOLUMENIE", "W",
        "Świeca zielona przy RVOL ≥ 1,5 — wzrost poparty wolumenem.",
        lambda I, B: ((B.c > B.o) & (I.rvol() >= 1.5), _ok(B.n, 140, B) & _fin(I.rvol())))
    add("W_SPADEK_NA_WOLUMENIE", "W",
        "Świeca czerwona przy RVOL ≥ 1,5 — spadek poparty wolumenem.",
        lambda I, B: ((B.c < B.o) & (I.rvol() >= 1.5), _ok(B.n, 140, B) & _fin(I.rvol())))
    add("W_WZROST_BEZ_WOLUMENU", "W",
        "Świeca zielona przy RVOL < 0,7 — wzrost bez wolumenu.",
        lambda I, B: ((B.c > B.o) & (I.rvol() < 0.7), _ok(B.n, 140, B) & _fin(I.rvol())))
    add("W_SPADEK_BEZ_WOLUMENU", "W",
        "Świeca czerwona przy RVOL < 0,7 — spadek bez wolumenu.",
        lambda I, B: ((B.c < B.o) & (I.rvol() < 0.7), _ok(B.n, 140, B) & _fin(I.rvol())))
    for k in (7, 35):
        add(f"W_WOLUMEN_{k}_ROSNACY", "W",
            f"Średni wolumen z ostatnich {k} świec wyższy niż z {k} świec przed nimi.",
            lambda I, B, k=k: (_roll_mean(B.v, k) > sh(_roll_mean(B.v, k), k), _ok(B.n, 2 * k, B)))
        add(f"W_OBV_{k}_ROSNIE", "W",
            f"OBV wyższe niż {k} świec temu — przewaga kupujących w tym oknie.",
            lambda I, B, k=k: (I.obv() > sh(I.obv(), k), _ok(B.n, k, B)))
    add("W_OBV_ROZJAZD_GORA", "W",
        "Rozjazd w górę: cena niższa niż 35 świec temu, a OBV wyższe.",
        lambda I, B: ((B.c < sh(B.c, 35)) & (I.obv() > sh(I.obv(), 35)), _ok(B.n, 35, B)))
    add("W_OBV_ROZJAZD_DOL", "W",
        "Rozjazd w dół: cena wyższa niż 35 świec temu, a OBV niższe.",
        lambda I, B: ((B.c > sh(B.c, 35)) & (I.obv() < sh(I.obv(), 35)), _ok(B.n, 35, B)))
    add("W_NAJWYZSZY_WOLUMEN_35", "W",
        "Najwyższy wolumen z ostatnich 35 świec.",
        lambda I, B: (B.v >= _roll_max(B.v, 35), _ok(B.n, 35, B) & (_roll_min(B.v, 35) > 0)))
    add("W_CENA_NAD_VWMA35", "W",
        "Zamknięcie powyżej VWMA(35) — średniej ważonej wolumenem.",
        lambda I, B: (B.c > I.vwma(35), _ok(B.n, 70, B) & _fin(I.vwma(35))))

    # --- S: wskaźniki -----------------------------------------------------
    for prog in (20, 30, 50):
        add(f"S_RSI14_PONIZEJ_{prog}", "S",
            f"RSI(14) poniżej {prog} — kurs wyprzedany w skali 14 świec (2 sesje).",
            lambda I, B, p=prog: (I.rsi(14) < p, _ok(B.n, 28, B) & _fin(I.rsi(14))))
    for prog in (50, 70, 80):
        add(f"S_RSI14_POWYZEJ_{prog}", "S",
            f"RSI(14) powyżej {prog} — kurs wykupiony w skali 14 świec (2 sesje).",
            lambda I, B, p=prog: (I.rsi(14) > p, _ok(B.n, 28, B) & _fin(I.rsi(14))))
    add("S_RSI14_ROSNIE", "S",
        "RSI(14) wyższe niż 3 świece temu.",
        lambda I, B: (I.rsi(14) > sh(I.rsi(14), 3), _ok(B.n, 31, B)))
    add("S_RSI2_SKRAJNIE_NISKO", "S",
        "RSI(2) poniżej 10 — bardzo krótkoterminowe wyprzedanie.",
        lambda I, B: (I.rsi(2) < 10, _ok(B.n, 14, B) & _fin(I.rsi(2))))
    add("S_RSI2_SKRAJNIE_WYSOKO", "S",
        "RSI(2) powyżej 90 — bardzo krótkoterminowe wykupienie.",
        lambda I, B: (I.rsi(2) > 90, _ok(B.n, 14, B) & _fin(I.rsi(2))))
    for prog in (20, 50, 80):
        add(f"S_STOCH_PONIZEJ_{prog}", "S",
            f"Stochastyk %K(14, 3) poniżej {prog}.",
            lambda I, B, p=prog: (I.stoch(14, 3, 3)["k"] < p, _ok(B.n, 28, B) & _fin(I.stoch(14, 3, 3)["k"])))
    add("S_STOCH_K_NAD_D", "S",
        "Stochastyk: %K powyżej %D.",
        lambda I, B: (I.stoch(14, 3, 3)["k"] > I.stoch(14, 3, 3)["d"], _ok(B.n, 28, B)))
    add("S_MACD_NAD_ZEREM", "S",
        "Linia MACD(12, 26, 9) powyżej zera.",
        lambda I, B: (I.macd(12, 26, 9)["macd"] > 0, _ok(B.n, 52, B) & _fin(I.macd(12, 26, 9)["macd"])))
    add("S_MACD_NAD_SYGNALEM", "S",
        "Linia MACD powyżej linii sygnału.",
        lambda I, B: (I.macd(12, 26, 9)["macd"] > I.macd(12, 26, 9)["signal"], _ok(B.n, 52, B)))
    add("S_MACD_HIST_ROSNIE", "S",
        "Histogram MACD wyższy niż na poprzedniej świecy.",
        lambda I, B: (I.macd(12, 26, 9)["hist"] > sh(I.macd(12, 26, 9)["hist"], 1), _ok(B.n, 53, B)))
    for n in (20, 50):
        def pctb(I, B, n=n):
            b = I.bb(n, 2.0)
            with np.errstate(invalid="ignore", divide="ignore"):
                return (B.c - b["lower"]) / (b["upper"] - b["lower"])
        add(f"S_BB{n}_NAD_GORNA", "S",
            f"Zamknięcie powyżej górnej wstęgi Bollingera({n}, 2).",
            lambda I, B, n=n: (pctb(I, B, n) > 1.0, _ok(B.n, n * 2, B) & _fin(pctb(I, B, n))))
        add(f"S_BB{n}_POD_DOLNA", "S",
            f"Zamknięcie poniżej dolnej wstęgi Bollingera({n}, 2).",
            lambda I, B, n=n: (pctb(I, B, n) < 0.0, _ok(B.n, n * 2, B) & _fin(pctb(I, B, n))))
        add(f"S_BB{n}_GORNA_POLOWA", "S",
            f"Zamknięcie w górnej połowie wstęgi Bollingera({n}, 2).",
            lambda I, B, n=n: (pctb(I, B, n) > 0.5, _ok(B.n, n * 2, B) & _fin(pctb(I, B, n))))
    add("S_NAD_VWAP", "S",
        "Zamknięcie powyżej VWAP bieżącej sesji.",
        lambda I, B: (B.c > I.vwap(), _ok(B.n, 1, B) & _fin(I.vwap())))
    for prog in (1, 2):
        add(f"S_VWAP_NAD_{prog}", "S",
            f"Zamknięcie co najmniej {prog}% powyżej VWAP sesji.",
            lambda I, B, p=prog: (B.c >= I.vwap() * (1 + p / 100.0), _ok(B.n, 1, B) & _fin(I.vwap())))
        add(f"S_VWAP_POD_{prog}", "S",
            f"Zamknięcie co najmniej {prog}% poniżej VWAP sesji.",
            lambda I, B, p=prog: (B.c <= I.vwap() * (1 - p / 100.0), _ok(B.n, 1, B) & _fin(I.vwap())))

    # --- K: kształt świecy ------------------------------------------------
    def rng(B):
        r = B.h - B.l
        return np.where(r > 0, r, np.nan)

    add("K_ZIELONA", "K", "Świeca zielona: zamknięcie powyżej otwarcia.",
        lambda I, B: (B.c > B.o, _ok(B.n, 0, B)))
    add("K_CZERWONA", "K", "Świeca czerwona: zamknięcie poniżej otwarcia.",
        lambda I, B: (B.c < B.o, _ok(B.n, 0, B)))
    for k in (2, 3, 4):
        add(f"K_ZIELONE_{k}", "K", f"{k} zielone świece z rzędu.",
            lambda I, B, k=k: (np.all([sh(B.c > B.o, i) for i in range(k)], axis=0), _ok(B.n, k, B)))
        add(f"K_CZERWONE_{k}", "K", f"{k} czerwone świece z rzędu.",
            lambda I, B, k=k: (np.all([sh(B.c < B.o, i) for i in range(k)], axis=0), _ok(B.n, k, B)))
    for prog in (0.5, 2.0):
        add(f"K_KORPUS_WZROST_{str(prog).replace('.', 'p')}", "K",
            f"Korpus wzrostowy co najmniej {prog}%: zamknięcie tyle powyżej otwarcia tej świecy.",
            lambda I, B, p=prog: (B.c >= B.o * (1 + p / 100.0), _ok(B.n, 0, B)))
        add(f"K_KORPUS_SPADEK_{str(prog).replace('.', 'p')}", "K",
            f"Korpus spadkowy co najmniej {prog}%: zamknięcie tyle poniżej otwarcia tej świecy.",
            lambda I, B, p=prog: (B.c <= B.o * (1 - p / 100.0), _ok(B.n, 0, B)))
    add("K_ZAMKNIECIE_GORNA_CWIARTKA", "K",
        "Zamknięcie w górnej ćwiartce zakresu świecy.",
        lambda I, B: ((B.c - B.l) >= 0.75 * rng(B), _ok(B.n, 0, B) & _fin(rng(B))))
    add("K_ZAMKNIECIE_DOLNA_CWIARTKA", "K",
        "Zamknięcie w dolnej ćwiartce zakresu świecy.",
        lambda I, B: ((B.c - B.l) <= 0.25 * rng(B), _ok(B.n, 0, B) & _fin(rng(B))))
    add("K_DLUGI_DOLNY_CIEN", "K",
        "Dolny cień dłuższy niż połowa zakresu świecy — odrzucenie niższych cen.",
        lambda I, B: ((np.minimum(B.o, B.c) - B.l) > 0.5 * rng(B), _ok(B.n, 0, B) & _fin(rng(B))))
    add("K_DLUGI_GORNY_CIEN", "K",
        "Górny cień dłuższy niż połowa zakresu świecy — odrzucenie wyższych cen.",
        lambda I, B: ((B.h - np.maximum(B.o, B.c)) > 0.5 * rng(B), _ok(B.n, 0, B) & _fin(rng(B))))
    add("K_DOJI", "K",
        "Doji: korpus mniejszy niż 10% zakresu świecy.",
        lambda I, B: (np.abs(B.c - B.o) < 0.1 * rng(B), _ok(B.n, 0, B) & _fin(rng(B))))
    add("K_POCHLANIA_W_GORE", "K",
        "Objęcie wzrostowe: zielona świeca z korpusem obejmującym czerwony korpus poprzedniej.",
        lambda I, B: ((B.c > B.o) & (sh(B.c, 1) < sh(B.o, 1)) & (B.c >= sh(B.o, 1)) & (B.o <= sh(B.c, 1)),
                      _ok(B.n, 1, B)))
    add("K_POCHLANIA_W_DOL", "K",
        "Objęcie spadkowe: czerwona świeca z korpusem obejmującym zielony korpus poprzedniej.",
        lambda I, B: ((B.c < B.o) & (sh(B.c, 1) > sh(B.o, 1)) & (B.c <= sh(B.o, 1)) & (B.o >= sh(B.c, 1)),
                      _ok(B.n, 1, B)))
    add("K_WYZSZY_SZCZYT_I_DOLEK", "K",
        "Wyższy szczyt i wyższy dołek niż na poprzedniej świecy.",
        lambda I, B: ((B.h > sh(B.h, 1)) & (B.l > sh(B.l, 1)), _ok(B.n, 1, B)))
    add("K_NIZSZY_SZCZYT_I_DOLEK", "K",
        "Niższy szczyt i niższy dołek niż na poprzedniej świecy.",
        lambda I, B: ((B.h < sh(B.h, 1)) & (B.l < sh(B.l, 1)), _ok(B.n, 1, B)))
    add("K_WEWNETRZNA", "K",
        "Świeca wewnętrzna: cały zakres mieści się w zakresie poprzedniej.",
        lambda I, B: ((B.h <= sh(B.h, 1)) & (B.l >= sh(B.l, 1)), _ok(B.n, 1, B)))

    # --- C: czas ----------------------------------------------------------
    for s in (1, 2, 3, 4, 5, 6, 7):
        add(f"C_SWIECA_{s}", "C",
            f"To {s}. świeca sesji (godzina {8 + s}:30–{9 + s}:30 ET)" + (" — ostatnia, 30 minut." if s == 7 else "."),
            lambda I, B, s=s: (B.slot == s, _ok(B.n, 0, B)))
    add("C_OSTATNIA_GODZINA", "C", "Jedna z dwóch ostatnich świec sesji.",
        lambda I, B: (B.slot >= 6, _ok(B.n, 0, B)))
    add("C_SESJA_SKROCONA", "C", "Sesja skrócona (4 świece zamiast 7).",
        lambda I, B: (np.array([nyse.expected_bars(d) == 4 for d in B.date]), _ok(B.n, 0, B)))
    for wd, nm in ((0, "PONIEDZIALEK"), (1, "WTOREK"), (2, "SRODA"), (3, "CZWARTEK"), (4, "PIATEK")):
        add(f"C_{nm}", "C", f"Sesja przypada na {nm.lower()}.",
            lambda I, B, wd=wd: (np.array([__import__("datetime").date.fromisoformat(d).weekday() == wd
                                           for d in B.date]), _ok(B.n, 0, B)))
    add("C_OSTATNIA_SESJA_TYGODNIA", "C", "Ostatnia sesja tygodnia.",
        lambda I, B: (np.array([nyse.is_last_of_week(d) for d in B.date]), _ok(B.n, 0, B)))
    add("C_OSTATNIA_SESJA_MIESIACA", "C", "Ostatnia sesja miesiąca.",
        lambda I, B: (np.array([nyse.is_last_of_month(d) for d in B.date]), _ok(B.n, 0, B)))

    # --- M: rynek (SPY) ---------------------------------------------------
    def mkt(B):
        return None if B.mkt_c is None else np.asarray(B.mkt_c, dtype=float)

    def _m_ok(B, w):
        m = mkt(B)
        return _ok(B.n, w, B) & (_fin(m) if m is not None else np.zeros(B.n, dtype=bool))

    for k in (7, 35):
        for prog in (1, 2):
            add(f"M_SPY_WZROST_{k}_{prog}", "M",
                f"SPY wyżej o co najmniej {prog}% niż {k} świec temu.",
                lambda I, B, k=k, p=prog: (
                    (_pct_change(mkt(B), k) >= p) if mkt(B) is not None else np.zeros(B.n, bool), _m_ok(B, k)))
            add(f"M_SPY_SPADEK_{k}_{prog}", "M",
                f"SPY niżej o co najmniej {prog}% niż {k} świec temu.",
                lambda I, B, k=k, p=prog: (
                    (_pct_change(mkt(B), k) <= -p) if mkt(B) is not None else np.zeros(B.n, bool), _m_ok(B, k)))
    add("M_SPY_NAD_SMA140", "M",
        "SPY powyżej swojej SMA(140) — rynek w trendzie wzrostowym.",
        lambda I, B: ((mkt(B) > _roll_mean(mkt(B), 140)) if mkt(B) is not None else np.zeros(B.n, bool),
                      _m_ok(B, 140)))
    add("M_SPY_NAD_SMA35", "M",
        "SPY powyżej swojej SMA(35).",
        lambda I, B: ((mkt(B) > _roll_mean(mkt(B), 35)) if mkt(B) is not None else np.zeros(B.n, bool),
                      _m_ok(B, 35)))
    for k in (7, 35):
        add(f"M_MOCNIEJ_NIZ_RYNEK_{k}", "M",
            f"Spółka urosła w {k} świecach więcej niż SPY.",
            lambda I, B, k=k: ((_pct_change(B.c, k) > _pct_change(mkt(B), k)) if mkt(B) is not None
                               else np.zeros(B.n, bool), _m_ok(B, k)))
        add(f"M_SLABIEJ_NIZ_RYNEK_{k}", "M",
            f"Spółka urosła w {k} świecach mniej niż SPY.",
            lambda I, B, k=k: ((_pct_change(B.c, k) < _pct_change(mkt(B), k)) if mkt(B) is not None
                               else np.zeros(B.n, bool), _m_ok(B, k)))
    add("M_RUCH_WLASNY_GORA", "M",
        "Ruch własny w górę: spółka +2% w 7 świecach, SPY nie więcej niż +0,3%.",
        lambda I, B: (((_pct_change(B.c, 7) >= 2) & (_pct_change(mkt(B), 7) <= 0.3)) if mkt(B) is not None
                      else np.zeros(B.n, bool), _m_ok(B, 7)))
    add("M_RUCH_WLASNY_DOL", "M",
        "Ruch własny w dół: spółka −2% w 7 świecach, SPY nie mniej niż −0,3%.",
        lambda I, B: (((_pct_change(B.c, 7) <= -2) & (_pct_change(mkt(B), 7) >= -0.3)) if mkt(B) is not None
                      else np.zeros(B.n, bool), _m_ok(B, 7)))
    add("M_RYNEK_ZMIENNY", "M",
        "Rynek ruchliwy: |zmiana SPY| w 7 świecach co najmniej 1%.",
        lambda I, B: ((np.abs(_pct_change(mkt(B), 7)) >= 1) if mkt(B) is not None else np.zeros(B.n, bool),
                      _m_ok(B, 7)))

    # --- L: luka ----------------------------------------------------------
    def gap(B):
        """Luka: otwarcie pierwszej świecy sesji wobec ostatniego zamknięcia poprzedniej."""
        first = B.is_first
        prev_c = sh(B.c, 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            g = (B.o / prev_c - 1.0) * 100.0
        return np.where(first, g, np.nan)

    for prog in (0.5, 1.0, 2.0):
        add(f"L_LUKA_GORA_{str(prog).replace('.', 'p')}", "L",
            f"Luka wzrostowa co najmniej {prog}% na otwarciu tej sesji (tylko pierwsza świeca).",
            lambda I, B, p=prog: (gap(B) >= p, _ok(B.n, 1, B) & _fin(gap(B))))
        add(f"L_LUKA_DOL_{str(prog).replace('.', 'p')}", "L",
            f"Luka spadkowa co najmniej {prog}% na otwarciu tej sesji (tylko pierwsza świeca).",
            lambda I, B, p=prog: (gap(B) <= -p, _ok(B.n, 1, B) & _fin(gap(B))))
    add("L_BRAK_LUKI", "L",
        "Otwarcie sesji bez luki: |luka| poniżej 0,2% (tylko pierwsza świeca).",
        lambda I, B: (np.abs(gap(B)) < 0.2, _ok(B.n, 1, B) & _fin(gap(B))))
    add("L_SESJA_PO_LUCE_GORA", "L",
        "W tej sesji była luka wzrostowa ≥ 1% (dotyczy każdej świecy sesji).",
        lambda I, B: (_sess_flag(B, gap(B) >= 1.0), _ok(B.n, 1, B)))
    add("L_SESJA_PO_LUCE_DOL", "L",
        "W tej sesji była luka spadkowa ≥ 1% (dotyczy każdej świecy sesji).",
        lambda I, B: (_sess_flag(B, gap(B) <= -1.0), _ok(B.n, 1, B)))


def _sess_flag(B: Bars, first_bar_flag: np.ndarray) -> np.ndarray:
    """Rozciąga wartość z pierwszej świecy sesji na całą sesję."""
    out = np.zeros(B.n, dtype=bool)
    cur = False
    for i in range(B.n):
        if B.is_first[i]:
            cur = bool(first_bar_flag[i])
        out[i] = cur
    return out


_build()

IDS = [d[0] for d in DEFS]


def evaluate(B: Bars) -> tuple[np.ndarray, np.ndarray]:
    """
    Zwraca dwie macierze (n świec × len(DEFS)) typu bool: wartości i „policzalne”.
    Liczone na świecy sygnału t — nic z przyszłości nie jest używane.
    """
    I = Ind(B)
    val = np.zeros((B.n, len(DEFS)), dtype=bool)
    dfn = np.zeros((B.n, len(DEFS)), dtype=bool)
    for j, (_, _, _, fn) in enumerate(DEFS):
        v, d = fn(I, B)
        v = np.asarray(v, dtype=bool)
        d = np.asarray(d, dtype=bool)
        val[:, j] = v & d
        dfn[:, j] = d
    return val, dfn


def build() -> dict:
    return {
        "meta": {"okolicznosci_version": OKOL_VERSION, "liczba": len(DEFS),
                 "grupy": GRUPY,
                 "zasada": "TAK/NIE na świecy sygnału (t), wejście na t+1 — żadna nie zagląda w przyszłość",
                 "brak_danych": "gdy okoliczności nie da się policzyć (za krótka historia, dziura, brak SPY), "
                                "transakcja nie jest liczona do ratingu tej okoliczności"},
        "okolicznosci": [{"id": i, "grupa": g, "opis": o} for i, g, o, _ in DEFS],
    }


def main(argv=None) -> int:
    doc = build()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Katalog okoliczności {OKOL_VERSION}: {len(DEFS)} pozycji → {OUT_PATH}")
    for g, opis in GRUPY.items():
        print(f"  {g}: {sum(1 for d in DEFS if d[1] == g):3d}  {opis}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
