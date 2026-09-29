"""
Sprawdzian poletka (D33). Wersja projektu: 0.43 (2026-09-29).

Wyłącznie sztuczne świece — ten test nigdy nie widzi prawdziwych danych.

    python tests/test_poletko.py
"""
from __future__ import annotations

import copy
import hashlib
import json

import numpy as np
import pandas as pd

from _bars import frame, run
from ia4 import backtest as BT
from ia4 import nyse
from ia4 import poletko as P
from ia4.bars import REPO


def _rising(symbol, sessions=20, step=0.003):
    rows, p = [], 100.0
    for _ in range(sessions * 7):
        o, c = p, p * (1 + step)
        rows.append((o, c * 1.0005, o * 0.9995, c, 1000))
        p = c
    return frame(rows, symbol=symbol)


def _doc(*specs):
    strat = []
    for n, (d, sl, tp, mode) in enumerate(specs, 1):
        h = BT.h_default(tp)
        strat.append({"nr": n, "id": BT.strategy_id("BASE_OPEN", d, sl, tp, h, mode), "sygnal": "BASE_OPEN",
                      "kategoria": "H6", "kierunek": d, "sl": sl, "tp": tp, "h": h, "tryb": mode, "motyw": "test",
                      "odkrywanie": {f"{p}_{k}": 0.0 for p in ("gl", "kontr") for k in
                                     ("transakcji", "ekspektancja", "przewaga")}})
    ids = "\n".join(s["id"] for s in strat)
    return {"meta": {"sha256_ids": hashlib.sha256(ids.encode()).hexdigest()}, "strategie": strat}


def _setup():
    cat = json.loads((REPO / "s1" / "catalog.json").read_text(encoding="utf-8"))
    mini = {"meta": dict(cat["meta"]), "signals": [s for s in cat["signals"] if s["code"] == "BASE_OPEN"]}
    frames = {s: _rising(s) for s in ("M1", "C1", "C2")}
    return mini, frames, {"main": ["M1"], "control": ["C1", "C2"]}


def test_passes_rule():
    df = pd.DataFrame({"gl_transakcji": [5, 5, 0, 5, 5], "kontr_transakcji": [50, 50, 50, 50, 50],
                       "gl_przewaga": [0.2, 0.2, None, -0.1, 0.2], "kontr_przewaga": [0.1, 0.1, 0.1, 0.1, 0.1],
                       "gl_ekspektancja": [0.1, 0.3, None, 0.3, 0.3], "kontr_ekspektancja": [0.1, 0.09, 0.2, 0.2, 0.2]})
    assert P.passes(df).tolist() == [True, False, False, False, True]


def test_discovery_mode_equals_backtest():
    """Ten sam kod bez okna = dokładnie liczby backtestu (kontrola --sprawdz-odkrywanie)."""
    mini, frames, groups = _setup()
    doc = _doc(("L", 1, 1, "1"), ("L", 3, 3, "5"), ("S", 2, 2, "nowy"), ("L", 5, 3, "10"))
    df = P.evaluate(doc, mini, frames, None, groups, None, boot=99)
    ref, _ = BT.run(mini, frames, None, groups, boot=99, progress=lambda *_: None)
    ref = ref.set_index("id")
    for col in ("gl_transakcji", "kontr_transakcji", "kontr_ekspektancja", "kontr_przewaga", "kontr_wynik_portfela"):
        a = df.set_index("id")[col].astype(float)
        assert np.allclose(a.values, ref.loc[a.index, col].astype(float).values, equal_nan=True), col


def test_window_only_entries_on_or_after_start():
    mini, frames, groups = _setup()
    doc = _doc(("L", 1, 1, "1"))
    full = P.evaluate(doc, mini, frames, None, groups, None, boot=99).iloc[0]
    start = nyse.trading_days()[nyse.ordinal("2025-03-03") + 10]        # 11. sesja
    win = P.evaluate(doc, mini, frames, None, groups, start, boot=99).iloc[0]
    # BASE_OPEN: sygnał na ostatniej świecy sesji, wejście na otwarciu następnej → 19 wejść w 20 sesjach,
    # w oknie od 11. sesji: wejścia w sesjach 11–20 = 10 na spółkę
    assert full.kontr_transakcji == 2 * 19 and win.kontr_transakcji == 2 * 10 and win.gl_transakcji == 10
    # każda transakcja +1%; losowe wejścia z końca okna kończą się END z mniejszym zyskiem → przewaga ≥ 0
    assert abs(win.kontr_ekspektancja - 1.0) < 1e-9 and win.kontr_przewaga >= 0
    assert win.kontr_przewaga_odkrywanie == 0.0


def test_random_baseline_uses_window_only():
    """Wejście losowe z okna: na końcu serii (koniec poletka) część pozycji kończy się END — inne niż całość."""
    mini, frames, groups = _setup()
    insts, _ = BT.prepare(frames, None, groups)
    H = BT.h_matrix()
    a = BT.random_baseline(insts, H)[("control", "L")]
    P.window(insts, nyse.trading_days()[nyse.ordinal("2025-03-03") + 17])
    b = BT.random_baseline(insts, H)[("control", "L")]
    assert all(it.start > 0 for it in insts) and not np.allclose(a, b)


def test_candidates_hash_guard():
    import tempfile
    from pathlib import Path
    doc = _doc(("L", 1, 1, "1"), ("S", 2, 2, "5"))
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "k.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        assert len(P.load_candidates(p)["strategie"]) == 2
        bad = copy.deepcopy(doc)
        bad["strategie"][1]["id"] = bad["strategie"][1]["id"].replace("__5", "__10")
        p.write_text(json.dumps(bad), encoding="utf-8")
        try:
            P.load_candidates(p)
            raise AssertionError("zmieniona lista przeszła")
        except ValueError:
            pass


def test_frozen_candidates_file():
    """s2/kandydaci.json: 50 strategii, hash zgodny, każda istnieje w siatce przebiegu 3, kryterium D33 zapisane."""
    doc = P.load_candidates()
    s = doc["strategie"]
    assert len(s) == 50 and len({x["sygnal"] for x in s}) == 50
    assert all(x["sl"] in BT.SL_GRID and x["tp"] in BT.TP_GRID and x["tryb"] in BT.MODES for x in s)
    assert all(x["id"] == BT.strategy_id(x["sygnal"], x["kierunek"], x["sl"], x["tp"], x["h"], x["tryb"]) for x in s)
    assert doc["meta"]["decyzja"] == "D33" and "20 z 50" in doc["meta"]["kryterium_poletka"]["lista_cos_znaczy"]


if __name__ == "__main__":
    raise SystemExit(run(dict(globals())))
