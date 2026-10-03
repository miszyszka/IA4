"""
IA 4 — obliczenia wykonywane w procesach roboczych.
Wersja projektu: 1.14 (2026-10-03) — musi zgadzać się z IA4_INSTRUKCJA.md

SKARBIEC WYMUSZONY KODEM (instrukcja, sekcja 6): `evaluate` i `evaluate_fixed`
zwracają wyłącznie wyniki grupy głównej — liczby skarbca są zerowane, zanim
opuszczą proces. Wyniki skarbca zwraca tylko `open_vault`, wołane przez
bramkę skarbca w search.py, która liczy i loguje każde otwarcie.
"""

from __future__ import annotations

import numpy as np

from . import data, rules, sim

_M: data.Market | None = None
_BASE: dict = {}


def init(data_dir, traded, vault_bars):
    """Start procesu roboczego: Ctrl+C obsługuje tylko proces główny."""
    import signal
    from pathlib import Path
    global _M
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    _M = data.load_local(traded, Path(data_dir), vault_bars)


def warmup(m) -> None:
    """Kompiluje (numba, cache na dysku) wszystko przed startem procesów roboczych."""
    from .settings import MA_TYPES
    for ma in MA_TYPES:
        m.line(ma, 10)
    set_market(m)
    rule = {"schema": rules.SCHEMA, "direction": "long", "signal": {"kind": "cross"}, "filters": [],
            "lines": {"A": {"ma": "EMA", "n": 10}, "B": {"ma": "SMA", "n": 30}},
            "exit": {"max_bars": None, "fc": [{"kind": "cross_back"}], "sl": 3, "tp": 5}}
    rules.run(rule, m, [3.0], [5.0])


def set_market(m):
    global _M
    _M = m


def market():
    return _M


def baseline_stats(direction: str, max_bars, sl_grid, tp_grid) -> np.ndarray:
    """Wejście „na ślepo”: każda świeca grupy głównej (od 150. świecy instrumentu) jest
    sygnałem, ten sam kierunek i to samo wyjście SL/TP/limit, bez FC, jedna pozycja
    naraz. Punkt odniesienia dla przewagi strategii (instrukcja, sekcja 9.3)."""
    key = (direction, int(max_bars or 0), tuple(sl_grid), tuple(tp_grid))
    st = _BASE.get(key)
    if st is None:
        m = _M
        se = rules._seg_end_of(m)
        t = np.flatnonzero((rules._pos(m) >= 150) & (np.arange(m.n) + 1 < se)).astype(np.int64)
        st, _ = sim.simulate(m.o, m.h, m.l, m.c, m.zone, se, t, np.full(t.size, -1, dtype=np.int64),
                             1 if direction == "long" else -1, np.asarray(sl_grid, float),
                             np.asarray(tp_grid, float), int(max_bars or 0), -1, -1)
        st[:, :, 0, :] = 0.0
        _BASE[key] = st
    return st


def baseline_pf(direction, max_bars, sl_grid, tp_grid) -> np.ndarray:
    g = baseline_stats(direction, max_bars, sl_grid, tp_grid)[:, :, 1:5, :].sum(axis=2)
    return sim.profit_factor(g[..., sim.GW], g[..., sim.GL])


# ---------------------------------------------------------------- ocena grupy głównej
def _main_view(stats: np.ndarray) -> dict:
    """Statystyki grupy głównej (okresy 1–4) dla wszystkich kombinacji SL × TP."""
    g = stats[:, :, 1:5, :].sum(axis=2)
    folds = stats[:, :, 1:5, :]
    return {"n": g[..., sim.N], "gw": g[..., sim.GW], "gl": g[..., sim.GL],
            "wins": g[..., sim.WINS], "pf": sim.profit_factor(g[..., sim.GW], g[..., sim.GL]),
            "fold_pf": sim.profit_factor(folds[..., sim.GW], folds[..., sim.GL]),
            "fold_n": folds[..., sim.N], "g": g}


def _neighbor_median(pf: np.ndarray) -> np.ndarray:
    """Mediana PF sąsiadów (±1 w siatce SL i TP, bez samego punktu)."""
    a, b = pf.shape
    out = np.zeros_like(pf)
    for i in range(a):
        for j in range(b):
            vals = [pf[x, y] for x in range(max(0, i - 1), min(a, i + 2))
                    for y in range(max(0, j - 1), min(b, j + 2)) if (x, y) != (i, j)]
            out[i, j] = float(np.median(vals)) if vals else 0.0
    return out


def screen(stats: np.ndarray, cfg: dict, base_pf: np.ndarray) -> dict:
    v = _main_view(stats)
    n, pf = v["n"], v["pf"]
    nb = _neighbor_median(pf)
    edge = pf / np.maximum(base_pf, 0.01)
    folds_ok = ((v["fold_n"] > 0) & (v["fold_pf"] > 1.0)).sum(axis=2)
    enough = n >= cfg["min_trades_main"]
    eligible = (enough & (pf >= cfg["pf_min"]) & (folds_ok >= cfg["folds_min_ok"])
                & (nb >= cfg["pf_sltp_neighbors"]))
    if cfg.get("pf_edge_min", 0) > 0:
        eligible &= edge >= cfg["pf_edge_min"]
    with np.errstate(divide="ignore", invalid="ignore"):
        time_share = np.where(n > 0, v["g"][..., sim.NTIME] / np.maximum(n, 1), 0.0)
        tp_share = np.where(n > 0, v["g"][..., sim.NTP] / np.maximum(n, 1), 0.0)
    exit_ok = (time_share <= cfg.get("max_time_share", 1.0)) & (tp_share >= cfg.get("min_tp_share", 0.0))
    eligible &= exit_ok
    lo, hi = cfg.get("tp_sl_ratio", [0, 1e9])
    ratio = np.asarray(cfg["tp_grid"], float)[None, :] / np.asarray(cfg["sl_grid"], float)[:, None]
    eligible &= (ratio >= lo) & (ratio <= hi)
    # pula rodziców: tylko hipotezy z wyjściami zgodnymi z celem (TP, mało limitu czasu)
    smooth = np.where(enough & exit_ok, np.minimum(pf, nb), 0.0)
    ia, ib = np.unravel_index(int(np.argmax(smooth)), smooth.shape)
    out = {"score": float(smooth[ia, ib]), "best": [int(ia), int(ib)],
           "n": int(n[ia, ib]), "pf": float(pf[ia, ib]), "edge": float(edge[ia, ib]),
           "win": float(v["wins"][ia, ib] / n[ia, ib]) if n[ia, ib] else 0.0,
           "eligible": bool(eligible.any()), "max_n": int(n.max())}
    if eligible.any():
        cand = np.where(eligible, pf + 1e-6 * n, -1.0)
        ea, eb = np.unravel_index(int(np.argmax(cand)), cand.shape)
        out.update({"elig_best": [int(ea), int(eb)], "elig_pf": float(pf[ea, eb]),
                    "elig_n": int(n[ea, eb]), "elig_folds_ok": int(folds_ok[ea, eb]),
                    "elig_nb": float(nb[ea, eb]), "elig_edge": float(edge[ea, eb]),
                    "elig_base_pf": float(base_pf[ea, eb]),
                    "pf_matrix": np.round(pf, 3).tolist(), "n_matrix": n.astype(int).tolist()})
    return out


def evaluate(task: dict) -> dict:
    """Reguła bez SL/TP → wszystkie kombinacje SL × TP, tylko grupa główna."""
    rule, cfg = task["rule"], task["cfg"]
    try:
        stats, _ = rules.run(rule, _M, cfg["sl_grid"], cfg["tp_grid"])
    except Exception as e:  # zła reguła nie zatrzymuje pętli
        return {"key": task["key"], "error": f"{type(e).__name__}: {e}", "rule": rule}
    stats[:, :, 0, :] = 0.0                     # skarbiec nie opuszcza procesu
    base = baseline_pf(rule["direction"], rule["exit"].get("max_bars"), cfg["sl_grid"], cfg["tp_grid"])
    res = screen(stats, cfg, base)
    res["key"] = task["key"]
    res["rule"] = rule
    return res


def evaluate_fixed(task: dict) -> dict:
    """PF i liczba transakcji grupy głównej dla jednej ustalonej pary SL/TP."""
    rule, cfg = task["rule"], task["cfg"]
    sl, tp = rule["exit"]["sl"], rule["exit"]["tp"]
    try:
        stats, _ = rules.run(rule, _M, [sl], [tp])
    except Exception as e:
        return {"pf": 0.0, "n": 0, "error": str(e)}
    g = stats[0, 0, 1:5, :].sum(axis=0)
    return {"pf": float(sim.profit_factor(g[sim.GW], g[sim.GL])), "n": int(g[sim.N])}


def main_entries(task: dict) -> list:
    """Świece wejścia transakcji grupy głównej (do wykrywania duplikatów)."""
    rule = task["rule"]
    _, rec = rules.run(rule, _M, [rule["exit"]["sl"]], [rule["exit"]["tp"]], rec=(0, 0))
    return rec[rec[:, 5] > 0, 1].astype(np.int64).tolist() if rec.size else []


# ---------------------------------------------------------------- skarbiec
def _block(s: np.ndarray) -> dict:
    n = int(s[sim.N])
    return {
        "trades": n,
        "pf": round(float(sim.profit_factor(s[sim.GW], s[sim.GL])), 3),
        "win_rate": round(s[sim.WINS] / n, 4) if n else 0.0,
        "avg_ret_pct": round(s[sim.SUMRET] / n, 4) if n else 0.0,
        "sum_ret_pct": round(float(s[sim.SUMRET]), 3),
        "sl": int(s[sim.NSL]), "tp": int(s[sim.NTP]), "fc": int(s[sim.NFC]),
        "time": int(s[sim.NTIME]), "cancelled": int(s[sim.NCANCEL]),
    }


def open_vault(task: dict) -> dict:
    """Pełny wynik reguły z ustalonym SL/TP: grupa główna, skarbiec, łącznie, rozbicia."""
    rule = task["rule"]
    m = _M
    sl, tp = rule["exit"]["sl"], rule["exit"]["tp"]
    stats, rec = rules.run(rule, m, [sl], [tp], rec=(0, 0))
    s = stats[0, 0]
    main = s[1:5].sum(axis=0)
    comb = s.sum(axis=0)
    bs = baseline_stats(rule["direction"], rule["exit"].get("max_bars"), [sl], [tp])[0, 0, 1:5].sum(axis=0)
    # średni wynik % wg rodzaju wyjścia (wszystkie transakcje: grupa główna + skarbiec)
    exit_avg = {}
    if rec.size:
        for code, name in ((sim.K_TP, "tp"), (sim.K_SL, "sl"), (sim.K_FC, "fc"), (sim.K_TIME, "time")):
            r = rec[rec[:, 4] == code, 3]
            exit_avg[name] = round(float(r.mean()), 4) if r.size else None
        exit_avg["all"] = round(float(rec[:, 3].mean()), 4)
    out = {"main": _block(main), "vault": _block(s[0]), "combined": _block(comb),
           "exit_avg_ret_pct": exit_avg,
           "blind_entry_main": _block(bs),
           "folds": [dict(_block(s[k]), period=f"{m.fold_dates[k-1][0]}–{m.fold_dates[k-1][1]}")
                     for k in range(1, 5) if k - 1 < len(m.fold_dates)]}

    # Rozbicia (tylko grupa główna): numer świecy wejścia, dzień tygodnia, instrument.
    main_rec = rec[rec[:, 5] > 0] if rec.size else rec
    def split(keys):
        res = {}
        for k in np.unique(keys):
            r = main_rec[keys == k, 3]
            gw, gl = r[r > 0].sum(), -r[r <= 0].sum()
            res[str(k)] = {"trades": int(r.size), "pf": round(float(sim.profit_factor(gw, gl)), 3),
                           "avg_ret_pct": round(float(r.mean()), 4)}
        return res
    if main_rec.size:
        t = main_rec[:, 0].astype(np.int64)
        e = main_rec[:, 1].astype(np.int64)
        inst = np.searchsorted(m.seg_end, t, side="right")
        out["breakdown"] = {
            "entry_slot": split(m.slot[e]),
            "entry_dow": split(m.feat["dow"][e].astype(int)),
            "instruments_with_trades": int(np.unique(inst).size),
            "top_instruments": dict(sorted(((m.symbols[i], int((inst == i).sum())) for i in np.unique(inst)),
                                           key=lambda x: -x[1])[:10]),
            "hold_bars": {"median": float(np.median(main_rec[:, 2] - e + 1)),
                          "p90": float(np.percentile(main_rec[:, 2] - e + 1, 90))},
        }

    # Statystyka przecięć linii A i B (czas między przecięciami, grupa główna).
    if "B" in rule["lines"]:
        L = rules.lines_of(rule, m)
        d = L["A"] - L["B"]
        runs = []
        for a, b in zip(m.seg_start, m.seg_end):
            dd = d[a:b]
            fin = np.isfinite(dd)
            sg = np.sign(dd)
            ch = np.flatnonzero(fin[1:] & fin[:-1] & (sg[1:] != sg[:-1]) & (sg[1:] != 0)) + 1
            ch = ch[m.zone[a + ch] > 0]
            if ch.size > 1:
                runs.extend(np.diff(ch).tolist())
        if runs:
            r = np.asarray(runs)
            out["cross_stats"] = {"crosses": int(r.size + 1), "bars_between_median": float(np.median(r)),
                                  "p25": float(np.percentile(r, 25)), "p75": float(np.percentile(r, 75)),
                                  "p90": float(np.percentile(r, 90))}
    return out
