"""
Testy wskaźników (Etap 1b, instrukcja 1.3). Wersja projektu: 0.41 (2026-09-29).

Każda wartość jest policzona ręcznie (nie przez wywołanie tej samej funkcji
z innymi parametrami) — patrz uzasadnienie liczb w komentarzach. Bez
Firestore i bez ia4.config: ten moduł nie czyta żadnych danych (D25).

Uruchomienie z katalogu ia4-research:
    python -m pytest tests             # jeśli jest pytest
    python tests/test_indicators.py    # bez pytest
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ia4 import indicators as I  # noqa: E402


def assert_series_close(got: pd.Series, expected: list, tol=1e-4, name=""):
    got = list(got)
    assert len(got) == len(expected), f"{name}: długość {len(got)} != {len(expected)}"
    for i, (g, e) in enumerate(zip(got, expected)):
        if e is None or (isinstance(e, float) and math.isnan(e)):
            assert g is None or (isinstance(g, float) and math.isnan(g)), \
                f"{name}[{i}]: oczekiwano NaN, jest {g}"
        else:
            assert g is not None and not (isinstance(g, float) and math.isnan(g)), \
                f"{name}[{i}]: oczekiwano {e}, jest NaN"
            assert abs(g - e) < tol, f"{name}[{i}]: oczekiwano {e}, jest {g}"


# ---------------------------------------------------------------------------
def test_sma():
    s = pd.Series([1, 2, 3, 4, 5])
    assert_series_close(I.sma(s, 3), [np.nan, np.nan, 2.0, 3.0, 4.0], name="sma")


def test_ema():
    # seed = SMA(3) pierwszych 3 = 2.0, alpha = 0.5
    s = pd.Series([1, 2, 3, 4, 5, 6])
    assert_series_close(I.ema(s, 3), [np.nan, np.nan, 2.0, 3.0, 4.0, 5.0], name="ema")


def test_ema_on_series_with_leading_nan():
    # symuluje EMA(2) z linii MACD, która sama zaczyna się od NaN
    s = pd.Series([np.nan, np.nan, 0.5, 0.5, 0.5])
    # seed = mean(pierwsze 2 dostępne) = 0.5, potem stała (wszystko 0.5)
    assert_series_close(I.ema(s, 2), [np.nan, np.nan, np.nan, 0.5, 0.5], name="ema_nan_prefix")


def test_rsi_wilder_hand_computed():
    # closes = 44, 44.5, 44.25, 44.6, 43.9, 44.3 ; n=3
    # diffs: 0.5, -0.25, 0.35, -0.7, 0.4
    # avg_gain seed (mean 0.5,0,0.35)=17/60; avg_loss seed (mean 0,0.25,0)=5/60
    # dalej Wilder: (prev*(n-1)+x)/n
    closes = pd.Series([44, 44.5, 44.25, 44.6, 43.9, 44.3])
    got = I.rsi(closes, n=3)
    expected = [np.nan, np.nan, np.nan, 77.27273, 39.53488, 57.37705]
    assert_series_close(got, expected, tol=1e-3, name="rsi")


def test_rsi_all_gains_is_100():
    closes = pd.Series([1, 2, 3, 4, 5])
    got = I.rsi(closes, n=2)
    assert got.iloc[-1] == 100.0


def test_atr_wilder_hand_computed():
    h = pd.Series([10, 11, 10.5, 11.5, 11])
    l = pd.Series([9, 9.5, 9.8, 10, 10.2])
    c = pd.Series([9.5, 10.8, 10, 11, 10.5])
    # TR ręcznie: [1, 1.5, 1.0, 1.5, 0.8] (patrz uzasadnienie w opisie zadania)
    tr = I.true_range(h, l, c)
    assert_series_close(tr, [1.0, 1.5, 1.0, 1.5, 0.8], name="true_range")
    got = I.atr(h, l, c, n=3)
    expected = [np.nan, np.nan, 1.166667, 1.277778, 1.118519]
    assert_series_close(got, expected, name="atr")


def test_bollinger_hand_computed():
    s = pd.Series([1, 2, 3, 4, 5])
    b = I.bollinger(s, n=3, k=2.0)
    assert_series_close(b["mid"], [np.nan, np.nan, 2.0, 3.0, 4.0], name="boll_mid")
    # std populacyjny okna [1,2,3]/[2,3,4]/[3,4,5] = sqrt(2/3) = 0.816497 (stałe)
    std = math.sqrt(2.0 / 3.0)
    assert_series_close(b["upper"], [np.nan, np.nan, 2 + 2 * std, 3 + 2 * std, 4 + 2 * std], name="boll_upper")
    assert_series_close(b["lower"], [np.nan, np.nan, 2 - 2 * std, 3 - 2 * std, 4 - 2 * std], name="boll_lower")
    assert_series_close(b["width"], [np.nan, np.nan, 4 * std / 2, 4 * std / 3, 4 * std / 4], name="boll_width")


def test_macd_hand_computed():
    # fast=2 (alpha=2/3), slow=3 (alpha=0.5), signal=2, closes 1..7
    # ema2 = [NaN,1.5,2.5,3.5,4.5,5.5,6.5]; ema3 = [NaN,NaN,2,3,4,5,6]
    # macd = ema2-ema3 = [NaN,NaN,0.5,0.5,0.5,0.5,0.5] (stała -> EMA sygnału też 0.5)
    closes = pd.Series([1, 2, 3, 4, 5, 6, 7])
    m = I.macd(closes, fast=2, slow=3, signal=2)
    assert_series_close(m["macd"], [np.nan, np.nan, 0.5, 0.5, 0.5, 0.5, 0.5], name="macd_line")
    assert_series_close(m["signal"], [np.nan, np.nan, np.nan, 0.5, 0.5, 0.5, 0.5], name="macd_signal")
    assert_series_close(m["hist"], [np.nan, np.nan, np.nan, 0.0, 0.0, 0.0, 0.0], name="macd_hist")


def test_stochastic_hand_computed():
    h = pd.Series([10, 12, 11, 13, 12, 14])
    l = pd.Series([8, 9, 9, 10, 10, 11])
    c = pd.Series([9, 11, 10, 12, 11, 13])
    st = I.stochastic(h, l, c, n=3, smooth=2, d=2)
    assert_series_close(st["k"], [np.nan, np.nan, np.nan, 62.5, 62.5, 62.5], name="stoch_k")
    assert_series_close(st["d"], [np.nan, np.nan, np.nan, np.nan, 62.5, 62.5], name="stoch_d")


def test_vwap_session_resets_each_day():
    date = pd.Series(["d1", "d1", "d1", "d2", "d2"])
    h = pd.Series([10, 11, 10.5, 12, 12.5])
    l = pd.Series([9, 10, 9.5, 11, 11.5])
    c = pd.Series([9.5, 10.5, 10, 11.5, 12])
    v = pd.Series([100, 200, 150, 300, 100])
    got = I.vwap_session(date, h, l, c, v)
    expected = [9.5, 3050 / 300, 4550 / 450, 11.5, 4650 / 400]
    assert_series_close(got, expected, name="vwap_session")


def test_vwma_ignores_session_boundary():
    h = pd.Series([10, 11, 10.5, 12, 12.5])
    l = pd.Series([9, 10, 9.5, 11, 11.5])
    c = pd.Series([9.5, 10.5, 10, 11.5, 12])
    v = pd.Series([100, 200, 150, 300, 100])
    tpv = I.typical_price_x_volume(h, l, c, v)
    got = I.vwma(tpv, v, n=3)
    expected = [np.nan, np.nan, 4550 / 450, 7050 / 650, 6150 / 550]
    assert_series_close(got, expected, name="vwma")


def test_obv_hand_computed():
    c = pd.Series([10, 11, 10, 10, 12])
    v = pd.Series([100, 200, 150, 50, 300])
    got = I.obv(c, v)
    assert_series_close(got, [0.0, 200.0, 50.0, 50.0, 350.0], name="obv")


def test_rvol_uses_same_slot_not_trailing_candles():
    slot = pd.Series([1, 2, 1, 2, 1, 2, 1, 2])
    v = pd.Series([10, 20, 12, 22, 14, 24, 16, 26], dtype=float)
    got = I.rvol(slot, v, lookback_sessions=2)
    expected = [np.nan, np.nan, np.nan, np.nan, 14 / 11, 24 / 21, 16 / 13, 26 / 23]
    assert_series_close(got, expected, name="rvol")


def test_cross_up_and_down():
    a = pd.Series([1, 3, 2, 4, 1])
    b = pd.Series([2, 2, 2, 2, 2])
    assert list(I.cross_up(a, b)) == [False, True, False, True, False]
    assert list(I.cross_down(a, b)) == [False, False, False, False, True]


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"✓ {name}")
        except AssertionError as e:
            failed += 1
            print(f"✗ {name}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} testów zaliczonych")
    sys.exit(1 if failed else 0)
