"""
Testy backtestu Etapu 2 (portfel, metryki 2.2, D10, bootstrap, FDR). Wersja projektu: 0.39 (2026-09-28).

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
    assert BT.max_concurrent(np.array([1, 3]), np.array([3, 4])) == 2       # wyjście i wejście w tej samej świecy
    assert BT.max_concurrent(np.array([1, 4]), np.array([3, 5])) == 1
    assert BT.max_concurrent(np.array([], int), np.array([], int)) == 0


def test_benjamini_hochberg():
    p = np.array([0.01, 0.04, 0.03])
    assert np.allclose(BT.bh_qvalues(p, 3), [0.03, 0.04, 0.04])
    # m = 6 (3 niepoliczone próby z p = 1): 0,06; 0,08; 0,08
    assert np.allclose(BT.bh_qvalues(p, 6), [0.06, 0.08, 0.08])


def test_bootstrap_p_direction():
    W = 20
    S = np.vstack([np.full(W, 5.0), np.tile([1.0, -1.0], W // 2), np.zeros(W)])
    N = np.vstack([np.full(W, 5.0), np.ones(W), np.zeros(W)])
    p = BT.bootstrap_p(S, N, np.array([0.0, 0.0, 0.0]), B=499, seed=1)
    assert p[0] == 1 / 500                     # zawsze +1% na transakcję: przewaga pewna
    assert 0.3 < p[1] < 0.7                    # średnio zero: brak przewagi
    assert p[2] == 1.0                         # brak transakcji
    # ta sama strategia (1% na transakcję), ale wejście losowe daje 2% → przewaga −1%;
    # wszystkie tygodnie identyczne, więc m* − m̂ = 0 ≥ −1 w każdym losowaniu → p = 1
    p = BT.bootstrap_p(S[:1], N[:1], np.array([2.0]), B=499, seed=1)
    assert p[0] == 1.0

def test_metrics_columns_and_purging():
    tr = {
        "ret": np.array([1.0, -0.5, 2.0, 3.0]), "reason": np.array([1, 0, 1, 3], dtype=np.int8),
        "amb": np.array([False, True, False, False]), "bars": np.array([3, 1, 5, 2]),
        "e_ord": np.array([10, 20, 30, 40]), "x_ord": np.array([12, 20, 34, 41]),
        "e_date": np.array(["d1", "d1", "d2", "d3"]), "week": np.array([0, 0, 1, 1]),
        "rising": np.array([True, False, True, True]),
    }
    m, S, N = BT.metrics(tr, 0.25, 2)
    assert m["transakcji"] == 3 and m["end_usuniete"] == 1 and m["dni"] == 2
    assert abs(m["ekspektancja"] - 2.5 / 3) < 1e-12 and abs(m["ekspektancja_netto"] - (2.5 / 3 - 0.05)) < 1e-12
    assert abs(m["pf"] - 6.0) < 1e-12 and m["sr_zysk"] == 1.5 and m["sr_strata"] == -0.5
    assert abs(m["obsuniecie"] - 0.5) < 1e-12                      # 0 → 1 → 0,5 → 2,5
    assert abs(m["pct_wieloznacznych"] - 100 / 3) < 1e-9 and abs(m["pct_tp"] - 200 / 3) < 1e-9
    assert m["med_trzymania_tp"] == 4.0 and m["med_trzymania_czas"] is None
    assert abs(m["przewaga"] - (2.5 / 3 - 0.25)) < 1e-12
    assert m["eksp_rosnace"] == 1.5 and m["eksp_spadajace"] == -0.5
    assert S.tolist() == [0.5, 2.0] and N.tolist() == [2, 1]


def _rising(symbol, sessions=20, step=0.003):
    rows, p = [], 100.0
    for _ in range(sessions * 7):
        o, c = p, p * (1 + step)
        rows.append((o, c * 1.0005, o * 0.9995, c, 1000))
        p = c
    return frame(rows, symbol=symbol)


def test_run_d10_h_from_control_group_and_csv():
    # cena rośnie o 0,3% na świecę: LONG TP 1% zawsze na 4. świecy (licząc wejście), TP 0,5% na 2.
    cat = json.loads((REPO / "s1" / "catalog.json").read_text(encoding="utf-8"))
    base = [s for s in cat["signals"] if s["code"] == "BASE_OPEN"]
    mini = {"meta": dict(cat["meta"]), "signals": base}
    frames = {s: _rising(s) for s in ("M1", "C1", "C2")}
    df, meta = BT.run(mini, frames, None, {"main": ["M1"], "control": ["C1", "C2"]}, boot=99, progress=lambda *_: None)
    assert len(df) == 200
    r = df[(df.kierunek == "L") & (df.sl == 1) & (df.tp == 1)].iloc[0]
    assert r.h == 4 and r.h_zrodlo == "D10" and r.id == "BASE_OPEN__L__SL1_TP1_H4"
    assert r.kontr_pct_tp == 100 and abs(r.kontr_ekspektancja - 1.0) < 1e-9 and r.gl_transakcji > 0
    r = df[(df.kierunek == "L") & (df.sl == 1) & (df.tp == 0.5)].iloc[0]
    assert r.h == 2
    with tempfile.TemporaryDirectory() as t:
        BT.write(df, meta, Path(t))
        txt = (Path(t) / "results.csv").read_text(encoding="utf-8")
        assert txt.startswith("id,sygnal,kod,") and len(txt.splitlines()) == 201
        assert (Path(t) / "runs.jsonl").exists()


if __name__ == "__main__":
    raise SystemExit(run(dict(globals())))
