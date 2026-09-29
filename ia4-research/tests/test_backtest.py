"""
Testy backtestu Etapu 2 (D30, D31, D32). Wersja projektu: 0.46 (2026-09-29).

Wyłącznie sztuczne świece — ten test nigdy nie widzi prawdziwych danych.

    python tests/test_backtest.py
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from _bars import frame, run
from ia4 import backtest as BT
from ia4.bars import REPO


def test_max_concurrent_inclusive_intervals():
    assert BT.max_concurrent(np.array([1, 2, 6]), np.array([3, 5, 7])) == 2
    assert BT.max_concurrent(np.array([1, 3]), np.array([3, 4])) == 2
    assert BT.max_concurrent(np.array([1, 4]), np.array([3, 5])) == 1
    assert BT.max_concurrent(np.array([], int), np.array([], int)) == 0


def test_limit_positions_and_new_signal():
    # wejścia 1..6, każda pozycja trwa do 10: przy limicie 5 szóste wejście odpada
    e = np.arange(1, 7)
    x = np.full(6, 10)
    assert BT.limit_positions(e, x, 5).tolist() == [0, 1, 2, 3, 4]
    # pozycja zamknięta na świecy 3 zwalnia miejsce dla wejścia na 4 (nie na 3)
    assert BT.limit_positions(np.array([1, 2, 3, 4]), np.array([3, 9, 9, 9]), 2).tolist() == [0, 1, 3]
    m = np.array([False, True, True, False, True, True, True])
    assert BT.new_signal_only(m).tolist() == [False, True, False, False, True, False, False]


def test_benjamini_hochberg():
    p = np.array([0.01, 0.04, 0.03])
    assert np.allclose(BT.bh_qvalues(p, 3), [0.03, 0.04, 0.04])
    assert np.allclose(BT.bh_qvalues(p, 6), [0.06, 0.08, 0.08])


def test_bootstrap_normal_p_can_be_tiny():
    """D30: przy wyraźnej przewadze p schodzi dużo poniżej 1/(B+1) — FDR może zadziałać."""
    rng = np.random.default_rng(3)
    W = 50
    N = np.full((3, W), 20.0)
    S = np.vstack([rng.normal(0.5, 0.2, W) * 20,       # +0,5% na transakcję, mała zmienność
                   rng.normal(0.0, 0.2, W) * 20,       # zero
                   np.zeros(W)])
    N[2] = 0
    p = BT.bootstrap_p(S, N, np.zeros(3), B=999, seed=1)
    assert p[0] < 1e-6 and 0.05 < p[1] < 0.95 and p[2] == 1.0


def test_metrics_net_of_costs_and_portfolio():
    tr = {"ret": np.array([0.95, -1.05, 1.95, -0.05]), "reason": np.array([1, 0, 1, 3], dtype=np.int8),
          "e_ord": np.array([10, 20, 30, 40]), "x_ord": np.array([12, 20, 34, 41]), "week": np.array([0, 0, 1, 1])}
    m, S, N = BT.metrics(tr, 0.1, 2)
    assert m["transakcji"] == 4 and m["skutecznosc"] == 50.0
    assert abs(m["ekspektancja"] - 0.45) < 1e-12 and abs(m["przewaga"] - 0.35) < 1e-12
    assert m["pct_czas"] == 25.0                      # END (koniec okresu) liczony jako „nie SL, nie TP”
    assert abs(m["wynik_portfela"] - 0.18) < 1e-12    # 10 $ × 1,8% = 0,18 $
    assert m["max_otwartych"] == 1 and np.allclose(S, [-0.1, 1.9]) and N.tolist() == [2, 2]


def _rising(symbol, sessions=20, step=0.003):
    rows, p = [], 100.0
    for _ in range(sessions * 7):
        o, c = p, p * (1 + step)
        rows.append((o, c * 1.0005, o * 0.9995, c, 1000))
        p = c
    return frame(rows, symbol=symbol)


def test_run_modes_columns_and_csv():
    # cena rośnie 0,3% na świecę; BASE_OPEN odpala na ostatniej świecy każdej sesji
    cat = json.loads((REPO / "s1" / "catalog.json").read_text(encoding="utf-8"))
    mini = {"meta": dict(cat["meta"]), "signals": [s for s in cat["signals"] if s["code"] == "BASE_OPEN"]}
    frames = {s: _rising(s) for s in ("M1", "C1", "C2")}
    df, meta = BT.run(mini, frames, None, {"main": ["M1"], "control": ["C1", "C2"]}, boot=99,
                      progress=lambda *_: None)
    assert len(df) == 4 * 2 * 15 and list(df.columns) == BT.COLUMNS          # D32: 4 tryby × 2 × SL 5 × TP 3
    assert sorted(df.sl.unique().tolist()) == [1, 2, 3, 4, 5] and sorted(df.tp.unique().tolist()) == [1, 2, 3]
    assert set(df.tryb) == {"1", "5", "10", "nowy"} and meta["cost_pct"] == 0.0
    r = df[(df.kierunek == "L") & (df.sl == 1) & (df.tp == 1) & (df.tryb == "1")].iloc[0]
    # LONG TP 1% zawsze na 4. świecy: +1% bez kosztów (D32), 10 $ × 1% = 0,10 $
    assert r.h == 14 and bool(r.sl_rowne_tp) and r.id == "BASE_OPEN__L__SL1_TP1_H14__1"
    assert abs(r.kontr_ekspektancja - 1.0) < 1e-9 and r.kontr_skutecznosc == 100
    assert abs(r.kontr_wynik_portfela - r.kontr_transakcji * 0.1) < 1e-9
    # SL 5% / TP 1%: ta sama transakcja (TP pierwszy), sl_rowne_tp = False
    r5 = df[(df.kierunek == "L") & (df.sl == 5) & (df.tp == 1) & (df.tryb == "1")].iloc[0]
    assert r5.id == "BASE_OPEN__L__SL5_TP1_H14__1" and not bool(r5.sl_rowne_tp) and r5.h == 14
    assert r5.kontr_transakcji == r.kontr_transakcji and abs(r5.kontr_ekspektancja - 1.0) < 1e-9
    # 70 świec limitu przy TP 3% i jednej pozycji naraz: tryb "5" pozwala na więcej naraz
    one = df[(df.kierunek == "L") & (df.sl == 1) & (df.tp == 3) & (df.tryb == "1")].iloc[0]
    five = df[(df.kierunek == "L") & (df.sl == 1) & (df.tp == 3) & (df.tryb == "5")].iloc[0]
    ten = df[(df.kierunek == "L") & (df.sl == 1) & (df.tp == 3) & (df.tryb == "10")].iloc[0]
    assert five.kontr_transakcji >= one.kontr_transakcji and five.kontr_max_otwartych >= one.kontr_max_otwartych
    assert ten.kontr_transakcji >= five.kontr_transakcji and ten.kontr_max_otwartych >= five.kontr_max_otwartych
    assert ten.kontr_max_otwartych <= 2 * 10                         # 2 spółki kontrolne × najwyżej 10
    assert meta["trials_counter_after"] == BT.PRIOR_TRIALS + 120 == 68_270 + 120
    with tempfile.TemporaryDirectory() as t:
        BT.write(df, meta, Path(t))
        txt = (Path(t) / "results.csv").read_text(encoding="utf-8")
        assert txt.startswith("id,sygnal,kategoria,kierunek,sl,tp,h,sl_rowne_tp,tryb,") and len(txt.splitlines()) == 121


if __name__ == "__main__":
    raise SystemExit(run(dict(globals())))
