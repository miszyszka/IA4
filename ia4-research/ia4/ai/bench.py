"""
IA 4 — punkty odniesienia Agent-Investora (instrukcja, sekcja 11c.10).
Wersja projektu: 1.46 (2026-10-17) — musi zgadzać się z IA4_INSTRUKCJA.md

Na tych samych świecach, wynik netto % na transakcję:
  • Inwestor — transakcje z playbooka (osobno: własne pomysły),
  • wszyscy kandydaci — księga cieni: każdy kandydat każdej rundy, ta sama reguła wyjścia, bez limitów,
  • losowy wybór — 200 losowań: w każdej rundzie, w której Inwestor wszedł w n kandydatów, n losowych
    kandydatów tej samej rundy (wyniki z cieni) → percentyl średniej Inwestora,
  • mechaniczny inwestor (Apps Script, telemetry/vi.json albo state.json → vi),
  • SPY kup i trzymaj od startedAt.
Plus kalibracja pewności (deklarowana pewność wobec udziału zyskownych).
"""

from __future__ import annotations

import math

import numpy as np

DRAWS = 200
MIN_VERDICT = 30


def stats(x) -> dict:
    x = np.asarray(list(x), float)
    n = int(x.size)
    if not n:
        return {"n": 0, "avg": None, "ci95": None, "win": None}
    ci = float(2 * x.std(ddof=1) / math.sqrt(n)) if n >= 2 else None
    return {"n": n, "avg": float(x.mean()), "ci95": ci, "win": float((x > 0).mean())}


def compute(main, shadow, prices, started_at: float | None, mech: dict | None, seed: int = 7) -> dict:
    closed = main.closed()
    pb = [p for p in closed if p.basis != "own"]
    own = [p for p in closed if p.basis == "own"]
    out = {"investor": stats(p.ret_net_pct for p in pb), "own": stats(p.ret_net_pct for p in own),
           "investorR": stats(p.r_mult for p in closed), "all": stats(p.ret_net_pct for p in shadow.closed())}
    # losowy wybór: rundy z wejściami Inwestora z playbooka, w których wszystkie cienie są już zamknięte
    sh_by_round: dict[str, list] = {}
    for p in shadow.pos:
        sh_by_round.setdefault(p.round_id, []).append(p)
    rounds, inv = [], []
    for rid, sh in sh_by_round.items():
        if any(p.status != "closed" for p in sh):
            continue
        took = [p for p in pb if p.round_id == rid]
        if took:
            rounds.append((np.array([p.ret_net_pct for p in sh]), len(took)))
            inv += [p.ret_net_pct for p in took]
    if rounds:
        rng = np.random.default_rng(seed)
        draws = np.empty(DRAWS)
        for d in range(DRAWS):
            vals = [rng.choice(arr, size=min(n, arr.size), replace=False) for arr, n in rounds]
            draws[d] = float(np.concatenate(vals).mean())
        m = float(np.mean(inv))
        out["random"] = {"rounds": len(rounds), "trades": len(inv), "investorAvg": m, "randomAvg": float(draws.mean()),
                         "lo": float(np.percentile(draws, 2.5)), "hi": float(np.percentile(draws, 97.5)),
                         "pctl": float((draws < m).mean() * 100)}
    else:
        out["random"] = None
    out["mechanical"] = mech
    spy = None
    if started_at and "SPY" in prices:
        a, b = prices.close_at("SPY", started_at), prices.last("SPY")
        if a and b:
            spy = {"pct": 100 * (b[1] / a - 1), "from": a, "to": b[1]}
    out["spy"] = spy
    cal = []
    for lo, hi in ((0, 40), (40, 55), (55, 70), (70, 101)):
        g = [p for p in closed if p.confidence is not None and lo <= p.confidence < hi]
        if g:
            cal.append({"from": lo, "to": min(hi, 100), "n": len(g), "win": sum(p.pnl_net_usd > 0 for p in g) / len(g),
                        "conf": float(np.mean([p.confidence for p in g])) / 100})
    out["calibration"] = cal
    out["verdict"] = verdict(out)
    return out


def verdict(b: dict) -> str:
    n = b["investor"]["n"]
    if n < MIN_VERDICT:
        return f"za wcześnie na ocenę: {n} z {MIN_VERDICT} zamkniętych transakcji z playbooka"
    r = b.get("random")
    if not r:
        return "brak porównania z losowym wyborem"
    if r["pctl"] >= 97.5:
        return f"wybór Inwestora lepszy niż losowy (percentyl {r['pctl']:.0f})"
    if r["pctl"] <= 2.5:
        return f"wybór Inwestora gorszy niż losowy (percentyl {r['pctl']:.0f})"
    return f"wybór Inwestora nie różni się od losowego (percentyl {r['pctl']:.0f})"
