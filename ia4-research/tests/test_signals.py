"""
Testy sygnałów S1 (Etap 1b, kryterium 1.2). Wersja projektu: 0.38 (2026-09-28).

Każdy przypadek policzony ręcznie — rachunek w komentarzu obok. Co najmniej
jeden test na każdą rodzinę z katalogu (test_every_catalog_type_has_a_family
pilnuje, że żadnej nie brakuje) plus warunki ważności z kontraktu silnika:
rozgrzewka, dziury w danych (D27), split (D24), brak wolumenu (D12), wejście.

Świece sztuczne (tests/_bars.py) — żadnych prawdziwych danych, żadnego wyniku
transakcji (1.1, D25).

    python tests/test_signals.py
"""
from __future__ import annotations

import json

import numpy as np

from _bars import closes, doji, fires, mk, run
from ia4 import signals as S
from ia4.bars import REPO

F = S.FAMILIES


def raw(p, B):
    return fires(S.raw(p, B))


# ============================ H1 ============================
def test_drop_and_rise():
    # c[3] = 98,4 ≤ c[1] × 0,985 = 98,5 → t=3; c[4] = 100 > c[2] × 0,985
    assert raw({"type": "DROP", "n": 2, "pct": 1.5}, closes([100, 100, 100, 98.4, 100])) == [3]
    assert raw({"type": "RISE", "n": 2, "pct": 1.5}, closes([100, 100, 100, 101.6, 100])) == [3]
    assert raw({"type": "DROP", "n": 2, "pct": 1.5}, closes([100, 100, 100, 98.6])) == []


def test_red_and_green():
    # 3 czerwone (t=1..3), c[3] = 97,9 ≤ o[1] × 0,98 = 98 → t=3; na t=2 świeca 0 to doji
    B = mk([doji(100), (100, 100, 99.5, 99.5), (99.5, 99.5, 99, 99), (99, 99, 97.9, 97.9)])
    assert raw({"type": "RED", "k": 3, "pct": 2}, B) == [3]
    B = mk([doji(100), (100, 100.5, 100, 100.5), (100.5, 101, 100.5, 101), (101, 102.1, 101, 102.1)])
    assert raw({"type": "GREEN", "k": 3, "pct": 2}, B) == [3]


def test_madev_and_maup():
    # SMA7 na t=7 = (6×100 + 98)/7 = 99,714; 98 ≤ 99,714 × 0,985 = 98,22
    assert raw({"type": "MADEV", "sma": 7, "pct": 1.5}, closes([100] * 7 + [98])) == [7]
    # 98,5 > (6×100+98,5)/7 × 0,985 = 98,29 → brak
    assert raw({"type": "MADEV", "sma": 7, "pct": 1.5}, closes([100] * 7 + [98.5])) == []
    assert raw({"type": "MAUP", "sma": 7, "pct": 1.5}, closes([100] * 7 + [102])) == [7]


def test_rsi_cross_down_and_up():
    # RSI(2) Wildera: 100, 50, 7,14 na t=2..4 (rachunek jak w test_indicators) → przecięcie 10 w dół na t=4
    assert raw({"type": "RSI", "len": 2, "below": 10}, closes([100, 101, 102, 101, 95])) == [4]
    # lustro: 100, 50, 92,86 → przecięcie 90 w górę na t=4
    assert raw({"type": "RSI", "len": 2, "above": 90}, closes([100, 99, 98, 99, 105])) == [4]


def test_bollinger_lower_and_upper():
    # 19 × 100 i 97: średnia 99,85; wariancja (19×0,15² + 2,85²)/20 = 0,4275; σ = 0,6538
    # dolna = 99,85 − 2 × 0,6538 = 98,54 > 97 → t=19
    assert raw({"type": "BB", "len": 20, "k": 2}, closes([100] * 19 + [97])) == [19]
    assert raw({"type": "BBU", "len": 20, "k": 2}, closes([100] * 19 + [103])) == [19]


def test_gap_and_gapup():
    # sesja 0: 7 × 100; sesja 1 otwiera się 98,9 ≤ 100 × 0,99 → t=7 (pierwsza świeca sesji)
    rows = [doji(100)] * 7 + [(98.9, 99, 98.8, 99)] + [doji(99)] * 6
    assert raw({"type": "GAP", "pct": 1}, mk(rows)) == [7]
    rows = [doji(100)] * 7 + [(101.1, 101.2, 101, 101)] + [doji(101)] * 6
    assert raw({"type": "GAPUP", "pct": 1}, mk(rows)) == [7]
    # luka w środku sesji nie liczy się (to nie pierwsza świeca)
    rows = [doji(100)] * 3 + [(98, 98, 98, 98)] + [doji(98)] * 3
    assert raw({"type": "GAP", "pct": 1}, mk(rows)) == []


def test_gapred_and_gapgreen():
    base = [doji(100)] * 7
    assert raw({"type": "GAPRED", "pct": 1}, mk(base + [(98.9, 98.9, 98.4, 98.5)])) == [7]
    assert raw({"type": "GAPRED", "pct": 1}, mk(base + [(98.9, 99.6, 98.9, 99.5)])) == []   # zielona
    assert raw({"type": "GAPGREEN", "pct": 1}, mk(base + [(101.1, 101.6, 101.1, 101.5)])) == [7]


def test_sodd_first_in_session_only():
    # otwarcie sesji 100; t=2: 98,6 > 98,5; t=3: 98,4 ≤ 98,5 → pierwszy; t=4 już nie
    B = mk([doji(100), doji(99), doji(98.6), doji(98.4), doji(98.0), doji(98), doji(98)])
    assert raw({"type": "SODD", "pct": 1.5}, B) == [3]
    B = mk([doji(100), doji(101), doji(101.4), doji(101.6), doji(102), doji(102), doji(102)])
    assert raw({"type": "SORU", "pct": 1.5}, B) == [3]


def test_hhdd_and_llru():
    # max H z t−34…t = 105 (świeca 10); C[34] = 99,7 ≤ 105 × 0,95 = 99,75
    rows = [doji(100)] * 35
    rows[10] = (100, 105, 100, 100)
    rows[34] = doji(99.7)
    assert raw({"type": "HHDD", "lookback": 35, "pct": 5}, mk(rows)) == [34]
    rows = [doji(100)] * 35
    rows[10] = (100, 100, 95, 100)
    rows[34] = doji(99.8)          # 99,8 ≥ 95 × 1,05 = 99,75
    assert raw({"type": "LLRU", "lookback": 35, "pct": 5}, mk(rows)) == [34]


def test_bigred_and_biggreen():
    B = mk([(100, 100, 98.4, 98.4), (100, 100, 98.6, 98.6)])
    assert raw({"type": "BIGRED", "pct": 1.5}, B) == [0]
    B = mk([(100, 101.6, 100, 101.6), (100, 101.4, 100, 101.4)])
    assert raw({"type": "BIGGREEN", "pct": 1.5}, B) == [0]


def test_hammer_and_star():
    # C[5] = 97,9 ≤ C[0] × 0,98 = 98; świeca 6: korpus 0,2, dolny cień 0,8 ≥ 0,4, górny 0,05 ≤ 0,2,
    # zakres 1,05, górna 1/3 od 97,1 + 0,7 = 97,8 ≤ C = 98,1
    rows = [doji(c) for c in (100, 100, 99.5, 99, 98.5, 97.9)] + [(97.9, 98.15, 97.1, 98.1)]
    assert raw({"type": "HAMMER", "priorBars": 5, "priorPct": 2}, mk(rows)) == [6]
    rows = [doji(c) for c in (100, 100, 100.5, 101, 101.5, 102.1)] + [(102.1, 102.9, 101.85, 101.9)]
    assert raw({"type": "STAR", "priorBars": 5, "priorPct": 2}, mk(rows)) == [6]


def test_engulf_and_engulfdn():
    # 3 czerwone, C[3] = 97,9 ≤ O[1] × 0,98 = 98; t=4 zielona: O 97,8 ≤ C[3], C 98,7 ≥ O[3] = 98,6
    rows = [doji(100), (100, 100, 99.3, 99.3), (99.3, 99.3, 98.6, 98.6), (98.6, 98.6, 97.9, 97.9),
            (97.8, 98.7, 97.8, 98.7)]
    assert raw({"type": "ENGULF", "minRed": 3, "priorPct": 2}, mk(rows)) == [4]
    rows = [doji(100), (100, 100.7, 100, 100.7), (100.7, 101.4, 100.7, 101.4), (101.4, 102.1, 101.4, 102.1),
            (102.2, 102.2, 101.3, 101.3)]
    assert raw({"type": "ENGULFDN", "minGreen": 3, "priorPct": 2}, mk(rows)) == [4]


def test_revconf_and_revdn():
    # C[5] = 96,9 ≤ C[0] × 0,97 = 97; t=6 zielona, 97,2 > H[5] = 96,9
    rows = [doji(c) for c in (100, 99.5, 99, 98, 97.5, 96.9)] + [(96.9, 97.2, 96.9, 97.2)]
    assert raw({"type": "REVCONF", "priorBars": 5, "priorPct": 3}, mk(rows)) == [6]
    rows = [doji(c) for c in (100, 100.5, 101, 102, 102.5, 103.1)] + [(103.1, 103.1, 102.8, 102.8)]
    assert raw({"type": "REVDN", "priorBars": 5, "priorPct": 3}, mk(rows)) == [6]


def test_atrdrop_and_atrrise():
    # 20 świec o zakresie 1 → ATR(14) = 1; t=20: TR = 2,5 → ATR = (13 + 2,5)/14 = 1,107;
    # spadek C[17] − C[20] = 2,5 ≥ 2 × 1,107 = 2,214
    rows = [(100, 100.5, 99.5, 100)] * 20 + [(100, 100, 97.5, 97.5)]
    assert raw({"type": "ATRDROP", "n": 3, "k": 2, "atr": 14}, mk(rows)) == [20]
    rows = [(100, 100.5, 99.5, 100)] * 20 + [(100, 102.5, 100, 102.5)]
    assert raw({"type": "ATRRISE", "n": 3, "k": 2, "atr": 14}, mk(rows)) == [20]


def test_ddays_and_udays():
    # zamknięcia sesji 100, 99, 98, 97: trzy spadki z rzędu → ostatnia świeca 4. sesji (t=27)
    cs = [c for c in (100, 99, 98, 97) for _ in range(7)]
    assert raw({"type": "DDAYS", "k": 3}, closes(cs)) == [27]
    cs = [c for c in (100, 101, 102, 103) for _ in range(7)]
    assert raw({"type": "UDAYS", "k": 3}, closes(cs)) == [27]


def test_filters():
    # SMA140 na t=140 = (139×100 + 101)/140 = 100,007 < 101 → TREND140 tylko na t=140
    B = closes([100] * 140 + [101])
    I = S.Ind(B)
    assert fires(S.FILTERS["TREND140"](B, I)) == [140]
    B = closes([100] * 14)
    assert fires(S.FILTERS["LASTBAR"](B, S.Ind(B))) == [6, 13]
    assert fires(S.FILTERS["FIRSTBAR"](B, S.Ind(B))) == [0, 7]
    # filtr w parametrach sygnału: spadek na ostatniej świecy sesji
    B = closes([100] * 5 + [97, 96.9])
    assert raw({"type": "DROP", "n": 1, "pct": 0.05, "filter": "LASTBAR"}, B) == [6]


# ============================ H2 ============================
def test_max_cross():
    # SMA2: _,3,3,2,1,3; SMA3: _,_,3,2,333,1,667,2,333 → w dół t=3, w górę t=5
    B = closes([3, 3, 3, 1, 1, 5])
    assert raw({"type": "MAX", "ma": "SMA", "fast": 2, "slow": 3, "dir": "up"}, B) == [5]
    assert raw({"type": "MAX", "ma": "SMA", "fast": 2, "slow": 3, "dir": "down"}, B) == [3]


def test_pxma():
    B = closes([3, 3, 3, 1, 1, 5])      # C przecina SMA3 w dół na t=3 (1 < 2,333; 3 ≥ 3), w górę na t=5
    assert raw({"type": "PXMA", "ma": "SMA", "n": 3, "dir": "up"}, B) == [5]
    assert raw({"type": "PXMA", "ma": "SMA", "n": 3, "dir": "down"}, B) == [3]


def test_pullma():
    # SMA3: t=3 → 12; t=4 → (12+13+13,8)/3 = 12,933 > 12 (trend); L=12,5 ≤ 12,933 < C=13,8; L[3]=13 > 12
    rows = [doji(10), doji(11), doji(12), doji(13), (13.5, 14, 12.5, 13.8)]
    p = {"type": "PULLMA", "ma": "SMA", "n": 3, "trend": {"type": "SLOPE", "slow": 3, "lag": 1}, "dir": "up"}
    assert raw(p, mk(rows)) == [4]
    rows = [doji(14), doji(13), doji(12), doji(11), (10.5, 11.5, 10, 10.2)]
    p = dict(p, dir="down")
    assert raw(p, mk(rows)) == [4]    # SMA3 = 11,067; H 11,5 ≥ 11,067 > 10,2; H[3] = 11 < 12


def test_maslope():
    # SMA2: _,9,5,8,5,7,5,8 → t=4 rośnie po dwóch spadkach
    assert raw({"type": "MASLOPE", "ma": "SMA", "n": 2, "k": 2, "dir": "up"}, closes([10, 9, 8, 7, 9])) == [4]
    assert raw({"type": "MASLOPE", "ma": "SMA", "n": 2, "k": 2, "dir": "down"}, closes([7, 8, 9, 10, 8])) == [4]


def test_ribbon_is_an_event():
    # C > SMA2 > SMA3 prawdziwe na t=4 i t=5 → zdarzenie tylko t=4
    p = {"type": "RIBBON", "mas": [["SMA", 1], ["SMA", 2], ["SMA", 3]], "dir": "up"}
    assert raw(p, closes([3, 2, 1, 2, 3, 4])) == [4]


def test_macd_zero_and_signal():
    # EMA2: _,4,5,3,5,2,5,2,833,4,278; EMA3: _,_,4,3,3,4 → MACD: −0,5, −0,5, −0,167, 0,278
    # sygnał EMA2 z MACD: t=3 −0,5, t=4 −0,278, t=5 0,093
    B = closes([5, 4, 3, 2, 3, 5])
    base = {"type": "MACD", "fast": 2, "slow": 3, "signal": 2}
    assert raw(dict(base, cross="zero", dir="up"), B) == [5]
    assert raw(dict(base, cross="signal", dir="up"), B) == [4]
    assert raw(dict(base, cross="signal", dir="up", zone="below0"), B) == [4]
    assert raw(dict(base, cross="signal", dir="up", zone="above0"), B) == []


def test_vwap_cross_from_second_bar():
    # VWAP: 100; (10000+9900)/200 = 99,5; (…+10100)/300 = 100 → C 101 > 100, C[1] 99 ≤ 99,5
    rows = [(100, 100, 100, 100, 100), (99, 99, 99, 99, 100), (101, 101, 101, 101, 100)]
    assert raw({"type": "VWAPX", "dir": "up"}, mk(rows)) == [2]
    # pierwsza świeca nowej sesji nie przecina VWAP poprzedniej
    rows = [doji(100)] * 6 + [doji(99)] + [doji(101)]
    assert raw({"type": "VWAPX", "dir": "up"}, mk(rows)) == []


def test_vwapdev_first_in_session():
    # VWAP t=2 = (10000+9890+9700)/300 = 98,633; 97 ≤ 98,633 × 0,99 = 97,65
    rows = [(100, 100, 100, 100, 100), (98.9, 98.9, 98.9, 98.9, 100), (97, 97, 97, 97, 100), (96, 96, 96, 96, 100)]
    assert raw({"type": "VWAPDEV", "pct": 1, "side": "below"}, mk(rows)) == [2]


def test_vwma_cross():
    # h=l=c, v=1: VWMA2 = _,100,99,99,5 → C 101 > 99,5, C[2] 98 ≤ 99
    assert raw({"type": "VWMAX", "n": 2, "dir": "up"}, mk([(c, c, c, c, 1) for c in (100, 100, 98, 101)])) == [3]


# ============================ H3 ============================
def test_donchian_event():
    # max H z 3 poprzednich: t=4 → 12 < 13 (wybicie), t=5 → 13 < 14, ale na t−1 już było
    B = closes([10, 11, 12, 11, 13, 14])
    assert raw({"type": "DONCH", "n": 3, "dir": "up"}, B) == [4]
    assert raw({"type": "DONCH", "n": 3, "dir": "down"}, closes([14, 13, 12, 13, 11, 10])) == [4]


def test_nses():
    cs = [c for c in (100, 101, 102) for _ in range(7)]
    assert raw({"type": "NSES", "n": 2, "dir": "up"}, closes(cs)) == [20]
    cs = [c for c in (102, 101, 100) for _ in range(7)]
    assert raw({"type": "NSES", "n": 2, "dir": "down"}, closes(cs)) == [20]


def test_pdhl_first_close_above_previous_high():
    rows = [doji(100)] * 7
    rows[3] = (100, 100.5, 99.5, 100)
    rows += [doji(100.4), doji(100.6), doji(101), doji(101), doji(101), doji(101), doji(101)]
    assert raw({"type": "PDHL", "dir": "up"}, mk(rows)) == [8]


def test_orb():
    rows = [(100, 101, 99, 100), doji(100.5), doji(101.2), doji(102), doji(102), doji(102), doji(102)]
    assert raw({"type": "ORB", "bars": 1, "fromSlot": 2, "toSlot": 5, "dir": "up"}, mk(rows)) == [2]
    # wybicie dopiero na świecy 6 — poza oknem 2–5
    rows = [(100, 101, 99, 100)] + [doji(100)] * 4 + [doji(101.5), doji(101.5)]
    assert raw({"type": "ORB", "bars": 1, "fromSlot": 2, "toSlot": 5, "dir": "up"}, mk(rows)) == []


def test_inside_session():
    s0 = [doji(100)] * 7
    s0[2], s0[4] = (100, 102, 100, 100), (100, 100, 99, 100)            # zakres 99–102
    s1 = [doji(100)] * 7
    s1[1], s1[5] = (100, 101.5, 100, 100), (100, 100, 99.5, 100)        # 99,5–101,5: wewnętrzna
    s2 = [doji(101), doji(101.6), doji(102)] + [doji(102)] * 4
    assert raw({"type": "INSIDE", "dir": "up"}, mk(s0 + s1 + s2)) == [15]


# ============================ H4 ============================
def test_squeeze_breakout():
    # BB(3,1) szerokość: t=4 → 0,0884 (min z 3), t=5 → 0; t=6: górna = 12 + √2 = 13,41 < 14,
    # t=5: C = 11 ≤ górna 11 → wybicie na t=6 po ściśnięciu w t−2…t−1
    p = {"type": "SQZ", "len": 3, "k": 1, "lookback": 3, "recent": 2, "dir": "up"}
    assert raw(p, closes([10, 12, 10, 11, 11, 11, 14])) == [6]


def test_narrow_range_bar_and_session():
    rows = [(100, 102, 98, 100), (100, 101.5, 98.5, 100), (100, 100.5, 99.5, 100), (100.2, 101, 100, 100.6)]
    assert raw({"type": "NR", "unit": "bar", "n": 3, "dir": "up"}, mk(rows)) == [3]

    def sess(lo, hi):
        s = [doji(100)] * 7
        s[1], s[2] = (100, hi, 100, 100), (100, 100, lo, 100)
        return s
    rows = sess(98, 102) + sess(98.5, 101.5) + sess(99.5, 100.5) + [doji(100.6)] + [doji(100.6)] * 6
    assert raw({"type": "NR", "unit": "session", "n": 3, "dir": "up"}, mk(rows)) == [21]


def test_wide_range_bar():
    # 15 świec o zakresie 1 → ATR[14] = 1; t=15: zakres 2,5 ≥ 2 × 1, C 101,2 ≥ 99 + 0,75 × 2,5
    rows = [(100, 100.5, 99.5, 100)] * 15 + [(99.5, 101.5, 99, 101.2)]
    assert raw({"type": "WRB", "k": 2, "atr": 14, "dir": "up"}, mk(rows)) == [15]
    rows[-1] = (99.5, 101.5, 99, 100)
    assert raw({"type": "WRB", "k": 2, "atr": 14, "dir": "up"}, mk(rows)) == []


# ============================ H5 ============================
def test_stochastic_cross_from_oversold():
    # %K(2) surowy: _,0,0,100,100; %D = SMA2: _,_,0,50,100 → przecięcie w górę na t=3, %K[2] = 0 < 20
    p = {"type": "STOCH", "k": 2, "smooth": 1, "d": 2, "level": 20, "dir": "up"}
    assert raw(p, closes([10, 8, 6, 7, 9])) == [3]


def test_rsix_exit_from_zone():
    # RSI(2) na t=4 = 7,14, na t=5: zysk (0,25+5)/2 = 2,625, strata 1,625 → 61,76 > 30
    assert raw({"type": "RSIX", "len": 2, "level": 30, "dir": "up"}, closes([100, 101, 102, 101, 95, 100])) == [5]


def test_divergence_helper_and_rsidiv():
    # min z 3 świec: t=2 (8) i t=5 (7); j dla t=5 = 2 (≥ t−3), oscylator 25 > 20
    B = closes([10, 9, 8, 9, 10, 7])
    osc = np.array([np.nan, np.nan, 20, 0, 0, 25.0])
    assert fires(S.divergence(B, osc, 3, 1, True)) == [5]
    osc[5] = 15
    assert fires(S.divergence(B, osc, 3, 1, True)) == []


# ============================ H6 ============================
def test_ibs():
    rows = [doji(100), (100, 102, 100, 100), (100, 100, 98, 100), doji(99), doji(98.5), doji(98.4), doji(98.3)]
    assert raw({"type": "IBS", "level": 0.1, "side": "low"}, mk(rows)) == [6]    # (98,3 − 98)/4 = 0,075


def test_first_hour_reversal():
    rows = [(100, 100.2, 98.5, 98.9), doji(99.5)] + [doji(99.5)] * 5          # połowa = 99,35
    assert raw({"type": "FHR", "pct": 1, "dir": "up"}, mk(rows)) == [1]
    rows = [(100, 101.5, 99.8, 101.1), doji(100.4)] + [doji(100.4)] * 5       # połowa = 100,65
    assert raw({"type": "FHR", "pct": 1, "dir": "down"}, mk(rows)) == [1]


def test_calendar_month_and_week_end():
    # 2025-03-27 (czw), 03-28 (pt), 03-31 (pn), 04-01 (wt)
    B = closes([100] * 28, start="2025-03-27")
    assert raw({"type": "CAL", "when": "month_end"}, B) == [20]
    assert raw({"type": "CAL", "when": "week_end"}, B) == [13]
    # tydzień kończący się w czwartek (Wielki Piątek 2025-04-18 bez sesji)
    B = closes([100] * 14, start="2025-04-16")
    assert raw({"type": "CAL", "when": "week_end"}, B) == [13]


def test_base_control_signals():
    B = closes([100] * 14)
    assert raw({"type": "BASE", "when": "session_open"}, B) == [6, 13]
    assert raw({"type": "BASE", "when": "session_close"}, B) == [5, 12]


# ============================ H7 ============================
def test_idio_and_mkt():
    stock = [doji(100)] * 7 + [doji(97.9), doji(97.9)]
    flat = [doji(400)] * 9
    B = mk(stock, market_rows=flat)
    p = {"type": "IDIO", "n": 7, "pct": 2, "mkt": "SPY", "mktMax": 0.3, "dir": "down"}
    assert raw(p, B) == [7]                                  # zdarzenie: t=8 już nie
    falling = [doji(400)] * 7 + [doji(398), doji(398)]      # SPY −0,5% → to nie ruch własny
    assert raw(p, mk(stock, market_rows=falling)) == []
    stock = [doji(100)] * 7 + [doji(98.4)]
    spy = [doji(400)] * 7 + [doji(395.6)]                   # −1,1% i −1,6%
    assert raw({"type": "MKT", "n": 7, "mkt": "SPY", "mktPct": 1, "pct": 1.5, "dir": "down"},
               mk(stock, market_rows=spy)) == [7]


def test_relative_strength_and_market_symbols_excluded():
    # iloraz: 0,1; 0,0909; 0,1122 — nowe maksimum z 3, SPY (100, 99, 98) nie na maksimum
    p = {"type": "RSX", "n": 3, "mkt": "SPY", "dir": "up"}
    B = mk([doji(10), doji(9), doji(11)], market_rows=[doji(100), doji(99), doji(98)])
    assert raw(p, B) == [2]
    B = mk([doji(10), doji(9), doji(11)], market_rows=[doji(100), doji(99), doji(98)], symbol="SPY")
    assert raw(p, B) == []


# ============================ H8 ============================
class FixedRvol(S.Ind):
    def __init__(self, B, rv):
        super().__init__(B)
        self._rv = np.asarray(rv, dtype=float)

    def rvol(self):
        return self._rv


def fam(p, B, rv):
    return fires(S.FAMILIES[p["type"]](p, B, FixedRvol(B, rv)))


def test_cap_is_base_plus_rvol():
    B = closes([100, 100, 100, 98, 97.9])                    # DROP_N3_X2: t=3 (98 ≤ 98), t=4
    p = {"type": "CAP", "base": {"type": "DROP", "n": 3, "pct": 2}, "rvol": 2, "dir": "down"}
    assert fam(p, B, [1, 1, 1, 2.5, 1.5]) == [3]


def test_clx():
    rows = [doji(100)] * 4 + [(99.5, 100, 98, 99.2)]          # L = 98 < min, C ≥ (100+98)/2 = 99
    p = {"type": "CLX", "rvol": 3, "n": 4, "dir": "down"}
    assert fam(p, mk(rows), [1, 1, 1, 1, 3.2]) == [4]
    assert fam(p, mk(rows), [1, 1, 1, 1, 2.9]) == []


def test_vbrk_vmax_dry():
    B = closes([10, 11, 12, 11, 13, 14])                      # DONCH n=3 w górę: t=4
    assert fam({"type": "VBRK", "n": 3, "rvolMin": 1.5, "dir": "up"}, B, [1, 1, 1, 1, 1.6, 1]) == [4]
    assert fam({"type": "VBRK", "n": 3, "rvolMax": 0.8, "dir": "up"}, B, [1, 1, 1, 1, 0.5, 1]) == [4]
    assert fam({"type": "VBRK", "n": 3, "rvolMax": 0.8, "dir": "up"}, B, [1, 1, 1, 1, 0.9, 1]) == []
    B = closes([3, 3, 3, 1, 1, 5])                            # MAX SMA2/3 w górę: t=5
    p = {"type": "VMAX", "ma": "SMA", "fast": 2, "slow": 3, "rvol": 1.5, "dir": "up"}
    assert fam(p, B, [1, 1, 1, 1, 1, 2]) == [5]
    rows = [doji(10), doji(11), doji(12), doji(13), (13.5, 14, 12.5, 13.8)]      # PULLMA z testu wyżej: t=4
    pull = {"type": "PULLMA", "ma": "SMA", "n": 3, "trend": {"type": "SLOPE", "slow": 3, "lag": 1}, "dir": "up"}
    p = {"type": "DRY", "pull": pull, "rvolAvg": 0.7, "bars": 3, "dir": "up"}
    assert fam(p, mk(rows), [1, 1, 0.5, 0.6, 0.9]) == [4]    # (0,5+0,6+0,9)/3 = 0,667
    assert fam(p, mk(rows), [1, 1, 0.8, 0.6, 0.9]) == []     # 0,767


def test_gapv():
    rows = [doji(100)] * 7 + [(97.9, 98, 97.5, 97.8)]
    p = {"type": "GAPV", "pct": 2, "rvolMin": 2, "dir": "down"}
    assert fam(p, mk(rows), [1] * 7 + [2.1]) == [7]
    assert fam({"type": "GAPV", "pct": 2, "rvolMax": 1, "dir": "down"}, mk(rows), [1] * 7 + [0.9]) == [7]
    assert fam(p, mk(rows), [1] * 7 + [1.9]) == []


def test_obv_divergence():
    # OBV: 0, −10, −20, −10, 0, −5 (v = 10; ostatnia świeca v = 5) → t=5: min z 3, OBV −5 > OBV[2] = −20
    rows = [(c, c, c, c, v) for c, v in ((10, 10), (9, 10), (8, 10), (9, 10), (10, 10), (7, 5))]
    p = {"type": "OBVD", "lookback": 3, "minGap": 1, "dir": "up"}
    assert fires(S.FAMILIES["OBVD"](p, mk(rows), S.Ind(mk(rows)))) == [5]


def test_accumulation_event():
    # okno 3 świec: t=3 → wzrostowy wolumen 200, spadkowy 20, zmiana C z 3 świec 1% → pierwsze spełnienie
    rows = [(c, c, c, c, v) for c, v in ((100, 50), (101, 100), (100.5, 20), (101, 100), (100.8, 10))]
    p = {"type": "ACC", "n": 3, "ratio": 2, "flat": 2, "side": "acc"}
    assert fires(S.FAMILIES["ACC"](p, mk(rows), S.Ind(mk(rows)))) == [3]


# ============================ ważność (kontrakt) ============================
SIG_DROP = {"params": {"type": "DROP", "n": 2, "pct": 1.5}, "warmup_bars": 3, "entry": "NEXT_OPEN", "volume": False}


def test_warmup_and_entry_needs_next_bar():
    B = closes([100, 98.4, 98.4, 96.8, 96.8, 95])
    # surowo: t=2 (98,4 ≤ 98,5), t=3, t=4, t=5; ważność: rozgrzewka 3 → od t=2; t=5 = ostatnia świeca → brak wejścia
    assert raw(SIG_DROP["params"], B) == [2, 3, 4, 5]
    assert fires(S.mask(SIG_DROP, B)) == [2, 3, 4]


def test_hole_inside_window_blocks_signal():
    # brak świecy nr 4 w sesji 0 (pozycja 3): dziura między wierszami 2 i 3 (w danych)
    rows = [doji(c) for c in (100, 100, 100, 100, 98.4, 98.4, 98.4, 96.8, 96.8)]
    B = mk(rows, skip={3})
    assert B.hole_before.tolist() == [False, False, False, True, False, False, False, False]
    # wiersze po usunięciu: C = 100, 100, 100, 98,4, 98,4, 98,4, 96,8, 96,8 → surowo t = 3, 4, 6, 7
    assert raw(SIG_DROP["params"], B) == [3, 4, 6, 7]
    # okno 3 świec (t−2…t) nie może zawierać dziury: t=3 (wiersze 1–3) i t=4 (2–4) odpadają,
    # t=7 to ostatnia świeca (brak wejścia) → zostaje t=6
    assert fires(S.mask(SIG_DROP, B)) == [6]


def test_missing_whole_session_is_a_hole():
    rows = [doji(100)] * 21
    B = mk(rows, skip=set(range(7, 14)))                     # brak całej drugiej sesji
    assert B.hole_before.sum() == 1 and B.hole_before[7]
    assert B.date[6] == "2025-03-03" and B.date[7] == "2025-03-05"


def test_zero_volume_blocks_volume_signal():
    sig = dict(SIG_DROP, volume=True)
    rows = [(c, c, c, c, 1000) for c in (100, 98.4, 98.4, 96.8, 96.8, 95, 95)]
    rows[3] = (96.8, 96.8, 96.8, 96.8, 0)
    B = mk(rows)
    m = fires(S.mask(sig, B))
    assert 3 not in m and 4 not in m and 5 not in m          # okna t−2…t zawierają v = 0 na t=3
    assert fires(S.mask(SIG_DROP, B)) == [2, 3, 4, 5]


def test_split_cuts_series():
    # split przed drugą sesją: spadek ×10 na granicy nie jest „spadkiem o 90%”
    rows = [doji(1000)] * 7 + [doji(100)] * 7
    B = mk(rows, splits=["2025-03-04"])
    assert B.segments() == [(0, 7), (7, 14)]
    sig = {"params": {"type": "DROP", "n": 1, "pct": 5}, "warmup_bars": 2, "entry": "NEXT_OPEN"}
    assert fires(S.mask(sig, B)) == []
    B = mk(rows)                                              # bez listy splitów — fałszywy sygnał
    assert fires(S.mask(sig, B)) == [7]


def test_session_open_entry_uses_signal_bar():
    t = np.array([7])
    assert S.entry_index({"entry": "SESSION_OPEN"}, t).tolist() == [7]
    assert S.entry_index({"entry": "NEXT_OPEN"}, t).tolist() == [8]


# ============================ katalog ============================
def test_every_catalog_type_has_a_family():
    cat = json.loads((REPO / "s1" / "catalog.json").read_text(encoding="utf-8"))
    types = set()
    for s in cat["signals"]:
        p = s["params"]
        types.add(p["type"])
        for k in ("base", "pull"):
            if k in p:
                types.add(p[k]["type"])
    missing = sorted(types - set(S.FAMILIES))
    assert not missing, f"brak funkcji dla typów: {missing}"


def test_all_catalog_signals_run_on_synthetic_bars():
    """Każdy z 286 sygnałów liczy się bez błędu na 60 sesjach sztucznych świec (+ SPY)."""
    import math
    cat = json.loads((REPO / "s1" / "catalog.json").read_text(encoding="utf-8"))
    rows, spy = [], []
    for i in range(60 * 7):
        c = 100 + 5 * math.sin(i / 9.0) + (i % 7) * 0.1
        rows.append((c - 0.2, c + 0.6, c - 0.7, c, 1000 + 400 * ((i * 7919) % 5)))
        s = 400 + 8 * math.sin(i / 13.0)
        spy.append((s, s + 1, s - 1, s, 5000))
    B = mk(rows, market_rows=spy, start="2025-01-02")
    total = 0
    for s in cat["signals"]:
        m = S.mask(s, B)
        assert m.dtype == bool and len(m) == B.n, s["id"]
        assert not m[: s["warmup_bars"] - 1].any(), f"{s['id']} odpala przed końcem rozgrzewki"
        total += int(m.sum())
    assert total > 0


if __name__ == "__main__":
    raise SystemExit(run(dict(globals())))
