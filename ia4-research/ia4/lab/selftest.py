"""
IA 4 — testy silnika na danych syntetycznych (bez Firestore).
Uruchomienie (w ia4-research/):  python -m ia4.lab.selftest
Porównuje jądro numba z niezależną, prostą symulacją świeca po świecy.
"""

from __future__ import annotations

import itertools
import sys
import time

import numpy as np
import pandas as pd

from . import data, rules, sim


def synthetic(n_inst=6, sessions=520, seed=7) -> dict:
    """Losowe błądzenie z lukami między sesjami, 7 świec na sesję (co 40. sesja: 4)."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-09-16", periods=sessions)
    frames = {}
    names = [f"X{i}" for i in range(n_inst)] + ["SPY", "QQQ"]
    for s in names:
        rows = []
        p = 100.0 * rng.uniform(0.5, 2.0)
        for di, d in enumerate(days):
            p *= np.exp(rng.normal(0, 0.012))            # luka na otwarciu
            bars = 4 if di % 40 == 39 else 7
            for k in range(1, bars + 1):
                o = p
                path = o * np.exp(np.cumsum(rng.normal(0.0001, 0.004, 6)))
                c = path[-1]
                h = max(o, c, path.max()) * (1 + abs(rng.normal(0, 0.001)))
                lo = min(o, c, path.min()) * (1 - abs(rng.normal(0, 0.001)))
                v = 0 if rng.random() < 0.01 else int(rng.integers(1e5, 1e6))
                rows.append((s, d.strftime("%Y-%m-%d"), k, o, h, lo, c, v))
                p = c
        frames[s] = pd.DataFrame(rows, columns=["symbol", "date", "slot", "o", "h", "l", "c", "v"])
    return frames


def reference(rule, m, sl, tp):
    """Prosta symulacja jednej kombinacji (sl, tp) — świeca po świecy."""
    sig_t, fcb, _ = rules.entries(rule, m)
    long = rule["direction"] == "long"
    mb = rule["exit"].get("max_bars") or 0
    seg_end = rules._seg_end_of(m)
    busy = -1
    out = []
    for t, f in zip(sig_t, fcb):
        if t < busy:
            continue
        e = t + 1
        end = seg_end[t] - 1
        p = m.o[e]
        slv = p * (1 - sl / 100) if long else p * (1 + sl / 100)
        tpv = p * (1 + tp / 100) if long else p * (1 - tp / 100)
        res = None
        for j in range(e, end + 1):
            if j > e:
                if (long and m.o[j] <= slv) or (not long and m.o[j] >= slv):
                    res = (j, m.o[j], "SL"); break
                if (long and m.o[j] >= tpv) or (not long and m.o[j] <= tpv):
                    res = (j, tpv, "TP"); break
                if f >= 0 and j == f + 1:
                    res = (j, m.o[j], "FC"); break
            if (long and m.l[j] <= slv) or (not long and m.h[j] >= slv):
                res = (j, slv, "SL"); break
            if (long and m.h[j] >= tpv) or (not long and m.l[j] <= tpv):
                res = (j, tpv, "TP"); break
            if mb and j == e + mb - 1:
                res = (j, m.c[j], "TIME"); break
        if res is None:
            busy = seg_end[t]
            continue
        j, px, k = res
        r = (px / p - 1) * 100 if long else (p - px) / p * 100
        out.append((t, j, r, k, m.zone[e]))
        busy = j
    return out


RULES = [
    {"direction": "long", "lines": {"A": {"ma": "EMA", "n": 10}, "B": {"ma": "SMA", "n": 40}},
     "signal": {"kind": "cross"}, "filters": [], "exit": {"fc": [{"kind": "cross_back"}]}},
    {"direction": "short", "lines": {"A": {"ma": "HMA", "n": 13}, "B": {"ma": "WMA", "n": 50}},
     "signal": {"kind": "cross"}, "filters": [{"f": "rsi", "op": ">", "x": 40}], "exit": {"max_bars": 21}},
    {"direction": "long", "lines": {"A": {"ma": "EMA", "n": 8}, "B": {"ma": "EMA", "n": 30}},
     "signal": {"kind": "converge", "grow": 3, "shrink": 2}, "filters": [],
     "exit": {"fc": [{"kind": "reexpand", "n": 2}]}},
    {"direction": "short", "lines": {"A": {"ma": "KAMA", "n": 10}, "B": {"ma": "VWMA", "n": 30}},
     "signal": {"kind": "revert", "k": 1.5}, "filters": [{"f": "spy140", "op": "<", "x": 0}],
     "exit": {"max_bars": 35, "fc": [{"kind": "turn_back"}]}},
    {"direction": "long", "lines": {"A": {"ma": "DEMA", "n": 20}, "B": {"ma": "TEMA", "n": 40}},
     "signal": {"kind": "turn", "pos": "below"}, "filters": [{"f": "since", "op": ">", "x": 10}], "exit": {}},
    {"direction": "long", "lines": {"A": {"ma": "ZLEMA", "n": 10}, "B": {"ma": "EMA", "n": 20}, "C": {"ma": "EMA", "n": 50}},
     "signal": {"kind": "ribbon"}, "filters": [{"f": "slot", "op": "<", "x": 5}], "exit": {"max_bars": 14}},
    {"direction": "short", "lines": {"A": {"ma": "SMA", "n": 26}},
     "signal": {"kind": "pcross"}, "filters": [{"f": "gap", "op": "<", "x": 0}], "exit": {"fc": [{"kind": "pcross_back"}]}},
]


def main() -> int:
    frames = synthetic()
    m = data.load_market(frames, [f"X{i}" for i in range(6)])
    print(f"Dane syntetyczne: {len(m.symbols)} instrumentów, {m.n} świec, okresy {m.fold_dates}")
    sl_grid = np.arange(1, 11, dtype=float)
    tp_grid = np.arange(1, 11, dtype=float)
    bad = 0
    for rule in RULES:
        rule["schema"] = rules.SCHEMA
        rule["exit"].setdefault("sl", 3)
        rule["exit"].setdefault("tp", 5)
        t0 = time.time()
        stats, _ = rules.run(rule, m, sl_grid, tp_grid)
        dt = time.time() - t0
        for a, b in [(0, 0), (2, 4), (9, 9), (4, 1), (1, 7)]:
            ref = reference(rule, m, sl_grid[a], tp_grid[b])
            _, rec = rules.run(rule, m, sl_grid, tp_grid, rec=(a, b))
            n_ref = len(ref)
            n_sim = int(stats[a, b, :, sim.N].sum())
            sum_ref = sum(r[2] for r in ref)
            sum_sim = float(stats[a, b, :, sim.SUMRET].sum())
            same = n_ref == n_sim == len(rec) and abs(sum_ref - sum_sim) < 1e-6
            if same:
                same = all(int(x[0]) == y[0] and int(x[2]) == y[1] and abs(x[3] - y[2]) < 1e-9
                           for x, y in zip(rec, ref))
            if not same:
                bad += 1
                print(f"  ✗ {rule['signal']['kind']} {rule['direction']} sl={sl_grid[a]} tp={tp_grid[b]}: "
                      f"ref {n_ref}/{sum_ref:.3f} vs sim {n_sim}/{sum_sim:.3f}")
        n = stats[:, :, :, sim.N].sum(axis=2)
        print(f"  ✓ {rule['signal']['kind']:9s} {rule['direction']:5s} "
              f"transakcji (SL3/TP5): {int(n[2, 4])}, czas {dt*1000:.0f} ms")
    print("WYNIK:", "OK" if not bad else f"{bad} rozbieżności")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
