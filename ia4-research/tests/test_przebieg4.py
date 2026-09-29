"""
Przebieg 4: okoliczności, rating, lepsza połowa, zmienna stawka (D34).
Wersja projektu: 0.47 (2026-09-29).

Wyłącznie sztuczne świece.

    python tests/test_przebieg4.py
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from _bars import frame, run
from ia4 import backtest as BT
from ia4 import okolicznosci as OK
from ia4 import przebieg4 as P4
from ia4.bars import REPO


def _f(V, D):
    """(V, D) → postać liczbowa, jakiej używa przebieg 4."""
    return V.astype(np.float32), (D & ~V).astype(np.float32)


def test_rating_skrajnosci():
    """Okoliczność, przy której zawsze jest TP → 100; przy której zawsze SL → 0; bez danych → 50."""
    T, M = 40, 3
    V = np.zeros((T, M), bool)
    D = np.ones((T, M), bool)
    reason = np.zeros(T, np.int8)
    reason[:20] = 1                      # 20 × TP, 20 × SL
    V[:20, 0] = True                     # okoliczność 0: TAK dokładnie przy TP
    V[20:, 1] = True                     # okoliczność 1: TAK dokładnie przy SL
    D[:, 2] = False                      # okoliczność 2: nigdy policzalna
    r_tak, r_nie, n = P4.ratingi(*_f(V, D), reason)
    assert r_tak[0] == 100 and r_nie[0] == 0
    assert r_tak[1] == 0 and r_nie[1] == 100
    assert r_tak[2] == P4.NEUTRAL and r_nie[2] == P4.NEUTRAL and n[2] == 0


def test_rating_za_malo_obserwacji():
    T = 30
    V = np.zeros((T, 1), bool)
    D = np.ones((T, 1), bool)
    V[:P4.MIN_OBS - 1, 0] = True          # o jedną za mało
    reason = np.ones(T, np.int8)
    r_tak, _, _ = P4.ratingi(*_f(V, D), reason)
    assert r_tak[0] == P4.NEUTRAL
    V[:P4.MIN_OBS, 0] = True
    r_tak, _, _ = P4.ratingi(*_f(V, D), reason)
    assert r_tak[0] == 100


def test_rating_pomija_wyjscia_czasowe():
    """TIME i END nie są ani TP, ani SL — nie wchodzą do mianownika."""
    T = 40
    V = np.ones((T, 1), bool)
    D = np.ones((T, 1), bool)
    reason = np.full(T, 2, np.int8)       # same wyjścia z limitu czasu
    reason[:12] = 1
    reason[12:16] = 0
    r_tak, _, n = P4.ratingi(*_f(V, D), reason)
    assert n[0] == 16 and abs(r_tak[0] - 75.0) < 1e-4


def test_ocena_transakcji():
    V = np.array([[True, False], [False, True]])
    D = np.ones((2, 2), bool)
    oc = P4.oceny(*_f(V, D), np.array([80.0, 20.0], np.float32), np.array([40.0, 60.0], np.float32))
    assert abs(oc[0] - 70.0) < 1e-4       # TAK dla 1. (80) i NIE dla 2. (60)
    assert abs(oc[1] - 30.0) < 1e-4       # NIE dla 1. (40) i TAK dla 2. (20)
    # „TAK" może wystąpić tylko tam, gdzie okoliczność jest policzalna (tak robi evaluate)
    D2 = np.array([[True, False], [False, False]])
    V2 = V & D2
    oc2 = P4.oceny(*_f(V2, D2), np.array([80.0, 20.0], np.float32), np.array([40.0, 60.0], np.float32))
    assert oc2[0] == 80.0 and oc2[1] == P4.NEUTRAL     # druga transakcja: nic policzalnego → neutralnie


def test_stawki_pelny_zakres():
    st = P4.stawki(np.array([50.0, 55.0, 60.0]))
    assert st[0] == P4.STAWKA_MIN and st[-1] == P4.STAWKA_MAX
    assert abs(st[1] - (P4.STAWKA_MIN + P4.STAWKA_MAX) / 2) < 1e-6
    assert P4.stawki(np.array([51.0, 51.0])).tolist() == [P4.STAWKA_MIN, P4.STAWKA_MIN]


def _rosnaca(symbol, sesje=40, krok=0.003):
    rows, p = [], 100.0
    for _ in range(sesje * 7):
        o, c = p, p * (1 + krok)
        rows.append((o, c * 1.0005, o * 0.9995, c, 1000))
        p = c
    return frame(rows, symbol=symbol)


def _mini():
    cat = json.loads((REPO / "s1" / "catalog.json").read_text(encoding="utf-8"))
    mini = {"meta": dict(cat["meta"]), "signals": [s for s in cat["signals"] if s["code"] == "BASE_OPEN"]}
    frames = {s: _rosnaca(s) for s in ("M1", "C1", "C2")}
    return mini, frames, {"main": ["M1"], "control": ["C1", "C2"]}


def test_baza_zgodna_z_przebiegiem_3():
    """Kolumny b_* (przed filtrem) muszą się zgadzać z backtestem przebiegu 3 — te same transakcje."""
    mini, frames, groups = _mini()
    df, meta, rat = P4.run(mini, frames, None, groups, boot=99, progress=lambda *_: None)
    ref, _ = BT.run(mini, frames, None, groups, boot=99, progress=lambda *_: None)
    ref = ref.set_index("id")
    a = df.set_index("id")
    wspolne = a.index.intersection(ref.index)
    assert len(wspolne) == len(a) == 4 * 2 * 15
    # liczba transakcji: przebieg 3 liczy grupy osobno, tu wszystkie razem
    suma3 = (ref.loc[wspolne, "gl_transakcji"] + ref.loc[wspolne, "kontr_transakcji"])
    assert (a.loc[wspolne, "b_transakcji"] == suma3).all()
    r = a.loc["BASE_OPEN__L__SL1_TP1_H14__1"]
    assert abs(r.b_ekspektancja - 1.0) < 1e-9 and r.b_skutecznosc == 100
    assert abs(r.b_wynik_portfela - r.b_transakcji * 0.1) < 1e-9      # stawka 10 $


def test_filtr_i_stawka():
    mini, frames, groups = _mini()
    df, meta, rat = P4.run(mini, frames, None, groups, boot=99, progress=lambda *_: None)
    assert list(df.columns) == P4.COLUMNS
    # lepsza połowa: dokładnie połowa transakcji (zaokrąglona w dół, minimum 1)
    n_b = df.b_transakcji.to_numpy()
    n_f = df.f_transakcji.to_numpy()
    assert np.all(n_f == np.maximum(1, n_b // 2))
    assert (df.f_srednia_stawka >= P4.STAWKA_MIN).all() and (df.f_srednia_stawka <= P4.STAWKA_MAX).all()
    assert (df.f_kapital >= df.f_transakcji * P4.STAWKA_MIN).all()
    # filtr nie może pogorszyć skuteczności w próbie, z której policzono rating (na tym polega L38)
    ok = df.f_poprawa_skutecznosci.notna()
    assert (df.loc[ok, "f_poprawa_skutecznosci"] >= -1e-9).all()
    assert (df.ok_policzalnych > 50).all() and df.ok_najlepsza.isin(OK.IDS).all()


def test_zapis_plikow():
    mini, frames, groups = _mini()
    df, meta, rat = P4.run(mini, frames, None, groups, boot=99, progress=lambda *_: None)
    assert meta["trials_counter_after"] == P4.PRIOR_TRIALS + 120
    assert meta["okolicznosci_liczba"] == len(OK.DEFS) and meta["grupy_razem"] is True
    with tempfile.TemporaryDirectory() as t:
        P4.write(df, meta, rat, Path(t))
        txt = (Path(t) / "results.csv").read_text(encoding="utf-8")
        assert txt.startswith("id,sygnal,") and len(txt.splitlines()) == 121
        z = np.load(Path(t) / "ratingi.npz", allow_pickle=False)
        assert z["rating_tak"].shape == (len(df), len(OK.DEFS)) and z["rating_tak"].dtype == np.uint8
        assert list(z["okolicznosci"]) == OK.IDS and len(z["id"]) == len(df)


def test_okolicznosci_z_ostatniej_zamknietej_swiecy():
    """Wiersz okoliczności to e−1; na początku odcinka i po dziurze — zaślepka (wiersz 0)."""
    mini, frames, groups = _mini()
    insts, W, VAL, DFN = P4.prepare(frames, None, groups, progress=lambda *_: None)
    it = insts[0]
    e = np.array([0, 1, 5, it.B.n - 1])
    r = P4.okol_row(it, e)
    assert r[0] == 0                      # przed pierwszą świecą nie ma zamkniętej
    assert r[1] == it.off + 0 and r[2] == it.off + 4 and r[3] == it.off + it.B.n - 2
    assert not DFN[0].any()               # zaślepka: nic nie jest policzalne


if __name__ == "__main__":
    raise SystemExit(run(dict(globals())))
