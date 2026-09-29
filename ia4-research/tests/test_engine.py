"""
Testy silnika transakcji (Etap 1b, kryterium 1.2). Wersja projektu: 0.44 (2026-09-29).

Wyłącznie sztuczne świce (1.1, D25): każdy przypadek sprawdza jeden punkt
kontraktu silnika na liczbach policzonych ręcznie, a na koniec wektorowy
silnik jest porównany z prostą, dosłowną implementacją kontraktu (pętla po
świecach) na losowych świecach dla całej siatki SL/TP w obu kierunkach.

    python tests/test_engine.py
"""
from __future__ import annotations

import numpy as np

from _bars import closes, doji, mk, run
from ia4 import engine as E

GRID = [1, 2]


def eng(B, hmax=70):
    return E.Engine(B, sl_grid=GRID, tp_grid=GRID, hmax=hmax)


def one(B, entry, d="L", sl=1, tp=1, H=None):
    r = eng(B).resolve(np.array([entry]), d, sl, tp, H)
    return (int(r.exit[0]), round(float(r.exit_price[0]), 6), E.REASONS[r.reason[0]],
            bool(r.ambiguous[0]), round(float(r.ret[0]), 6))


def test_h_default_d5():
    assert [E.h_default(x) for x in (0.5, 1, 1.25, 2.5, 3, 5)] == [14, 14, 35, 35, 70, 70]


def test_long_take_profit():
    # wejście 100 (otwarcie t=1); TP 1% = 101 dotknięte na t=2 → wyjście 101, +1%
    B = mk([doji(100), (100, 100.5, 99.8, 100.2), (100.2, 101.3, 100, 101)] + [doji(101)] * 3)
    assert one(B, 1) == (2, 101.0, "TP", False, 0.01)


def test_long_stop_loss():
    B = mk([doji(100), (100, 100.5, 99.8, 100.2), (100.2, 100.3, 98.9, 99.2)] + [doji(99)] * 3)
    assert one(B, 1) == (2, 99.0, "SL", False, -0.01)


def test_both_in_one_bar_is_stop_and_ambiguous():
    B = mk([doji(100), (100, 100.5, 99.8, 100.2), (100.1, 101.2, 98.8, 100)] + [doji(100)] * 3)
    assert one(B, 1) == (2, 99.0, "SL", True, -0.01)


def test_gap_through_stop_exits_at_open():
    # otwarcie 98,5 poniżej SL 99 → wyjście po 98,5, nawet jeśli później świeca sięga TP
    B = mk([doji(100), (100, 100.5, 99.8, 100.2), (98.5, 101.5, 98.4, 101)] + [doji(101)] * 3)
    assert one(B, 1) == (2, 98.5, "SL", False, -0.015)


def test_gap_through_target_exits_at_open():
    B = mk([doji(100), (100, 100.5, 99.8, 100.2), (101.5, 101.8, 98.5, 99)] + [doji(99)] * 3)
    assert one(B, 1) == (2, 101.5, "TP", False, 0.015)


def test_entry_bar_counts_and_has_no_gap():
    # cel osiągnięty już w świecy wejścia — po poziomie, nie po otwarciu (otwarcie = cena wejścia)
    B = mk([doji(100), (100, 101.2, 99.9, 101)] + [doji(101)] * 3)
    r = eng(B).resolve(np.array([1]), "L", 1, 1)
    assert E.REASONS[r.reason[0]] == "TP" and r.exit[0] == 1 and r.bars[0] == 1 and r.exit_price[0] == 101


def test_time_limit_counts_entry_bar_as_first():
    # TP 1% → H = 14: bez SL/TP wyjście po zamknięciu 14. świecy od wejścia (t = 1 + 13 = 14)
    rows = [doji(100)] + [(100, 100.4, 99.6, 100.1)] * 25
    rows[14] = (100, 100.4, 99.6, 100.3)
    B = mk(rows)
    assert one(B, 1) == (14, 100.3, "TIME", False, 0.003)


def test_end_of_data_before_h():
    B = mk([doji(100)] + [(100, 100.4, 99.6, 100.2)] * 5)
    assert one(B, 1)[:3] == (5, 100.2, "END")


def test_short_mirror():
    B = mk([doji(100), (100, 100.5, 99.8, 100.2), (100.2, 100.3, 98.9, 99.2)] + [doji(99)] * 3)
    assert one(B, 1, d="S") == (2, 99.0, "TP", False, 0.01)
    B = mk([doji(100), (100, 100.5, 99.8, 100.2), (100.2, 101.1, 100, 101)] + [doji(101)] * 3)
    assert one(B, 1, d="S") == (2, 101.0, "SL", False, -0.01)
    B = mk([doji(100), (100, 100.5, 99.8, 100.2), (101.5, 101.6, 101, 101.2)] + [doji(101)] * 3)
    assert one(B, 1, d="S") == (2, 101.5, "SL", False, -0.015)


def test_position_does_not_cross_split():
    # split przed sesją 2025-03-04: odcinek kończy się na t=6 → wyjście END po zamknięciu t=6,
    # mimo że w nowym odcinku cena „spada o 90%” (to tylko zmiana skali)
    rows = [doji(1000)] + [(1000, 1003, 997, 1001)] * 6 + [doji(100)] * 7
    B = mk(rows, splits=["2025-03-04"])
    assert one(B, 1)[:3] == (6, 1001.0, "END")
    B = mk(rows)                                             # bez splitu: fałszywe SL
    assert one(B, 1)[2] == "SL"


def test_position_survives_data_hole_and_counts_real_bars():
    # brak całej sesji 2025-03-04 (pozycje 7–13): H = 14 liczone w istniejących świecach —
    # wiersz 14 to świeca nr 1 z 2025-03-06, a nie „14 godzin później” w czasie kalendarzowym
    rows = [doji(100)] + [(100, 100.4, 99.6, 100.1)] * 27
    B = mk(rows, skip=set(range(7, 14)))
    ex, px, why, amb, ret = one(B, 1)
    assert why == "TIME" and ex == 14 and B.date[14] == "2025-03-06" and B.slot[14] == 1


def test_one_position_at_a_time():
    # wejścia 1, 2, 3, 6; wyjścia 3, 4, 5, 7 → przyjęte 1 (do 3) i 6; wejście na świecy wyjścia (3) odpada
    keep = E.one_position(np.array([1, 2, 3, 6]), np.array([3, 4, 5, 7]))
    assert keep.tolist() == [0, 3]
    keep = E.one_position(np.array([1, 4]), np.array([3, 5]))
    assert keep.tolist() == [0, 1]


def test_trades_table_costs_and_session_open():
    rows = [doji(100)] * 7 + [(98.9, 100, 98.8, 99.9)] + [doji(99.9)] * 6
    B = mk(rows)
    sig = {"entry": "SESSION_OPEN"}
    m = np.zeros(B.n, dtype=bool)
    m[7] = True
    df = E.trades(eng(B), sig, m, "L", 1, 1)
    # wejście po otwarciu świecy sygnału (luka znana na otwarciu): 98,9; TP 1% = 99,889 dotknięty na t=7
    assert len(df) == 1 and df.loc[0, "entry_date"] == "2025-03-04" and df.loc[0, "entry_slot"] == 1
    assert abs(df.loc[0, "entry_price"] - 98.9) < 1e-12 and df.loc[0, "reason"] == "TP"
    assert abs(df.loc[0, "ret_net"] - (0.01 - 0.0005)) < 1e-12


def _reference(B, e, d, sl, tp, H):
    """Kontrakt silnika napisany wprost, świeca po świecy (do porównania z wersją wektorową)."""
    ent = B.o[e]
    slv = ent * (1 - sl / 100) if d == "L" else ent * (1 + sl / 100)
    tpv = ent * (1 + tp / 100) if d == "L" else ent * (1 - tp / 100)
    last = min(e + H - 1, B.seg_end[e])
    for j in range(e, last + 1):
        o, h, lo = B.o[j], B.h[j], B.l[j]
        if j > e:
            if (d == "L" and o <= slv) or (d == "S" and o >= slv):
                return j, o, "SL", False
            if (d == "L" and o >= tpv) or (d == "S" and o <= tpv):
                return j, o, "TP", False
        hit_sl = lo <= slv if d == "L" else h >= slv
        hit_tp = h >= tpv if d == "L" else lo <= tpv
        if hit_sl and hit_tp:
            return j, slv, "SL", True
        if hit_sl:
            return j, slv, "SL", False
        if hit_tp:
            return j, tpv, "TP", False
    return last, B.c[last], ("TIME" if last == e + H - 1 else "END"), False


def test_vectorized_engine_matches_literal_contract():
    rng = np.random.default_rng(7)
    rows, p = [], 100.0
    for _ in range(7 * 40):
        o = p * (1 + rng.normal(0, 0.006))
        c = o * (1 + rng.normal(0, 0.009))
        rows.append((o, max(o, c) * (1 + abs(rng.normal(0, 0.004))), min(o, c) * (1 - abs(rng.normal(0, 0.004))), c))
        p = c
    B = mk(rows, splits=["2025-03-24"])
    grid = [0.5, 1, 2, 3]
    en = E.Engine(B, sl_grid=grid, tp_grid=grid, hmax=70)
    entries = np.arange(B.n)
    checked = 0
    for d in ("L", "S"):
        for sl in grid:
            for tp in grid:
                H = E.h_default(tp)
                r = en.resolve(entries, d, sl, tp, H)
                for k, e in enumerate(entries):
                    ex, px, why, amb = _reference(B, int(e), d, sl, tp, H)
                    assert r.exit[k] == ex and abs(r.exit_price[k] - px) < 1e-9, (d, sl, tp, e)
                    assert E.REASONS[r.reason[k]] == why and bool(r.ambiguous[k]) == amb, (d, sl, tp, e)
                    checked += 1
    assert checked == 2 * 16 * B.n


def test_grid_matches_single():
    """resolve_grid (cała siatka naraz, Etap 2) = resolve dla każdej pary SL/TP, oba kierunki."""
    rng = np.random.default_rng(11)
    rows, p = [], 100.0
    for _ in range(7 * 30):
        o = p * (1 + rng.normal(0, 0.006))
        c = o * (1 + rng.normal(0, 0.009))
        rows.append((o, max(o, c) * (1 + abs(rng.normal(0, 0.004))), min(o, c) * (1 - abs(rng.normal(0, 0.004))), c))
        p = c
    B = mk(rows)
    grid = [0.5, 1, 2, 4]
    en = E.Engine(B, sl_grid=grid, tp_grid=grid, hmax=70)
    Hm = np.array([[E.h_default(tp) - k for tp in grid] for k in range(len(grid))])
    ent = np.arange(B.n)
    for d in ("L", "S"):
        g = E.resolve_grid(en, ent, d, Hm)
        for i, sl in enumerate(grid):
            for j, tp in enumerate(grid):
                r = en.resolve(ent, d, sl, tp, int(Hm[i, j]))
                assert (g.exit[:, i, j] == r.exit).all() and (g.reason[:, i, j] == r.reason).all(), (d, sl, tp)
                assert (g.ambiguous[:, i, j] == r.ambiguous).all() and np.allclose(g.ret[:, i, j], r.ret), (d, sl, tp)


if __name__ == "__main__":
    raise SystemExit(run(dict(globals())))
