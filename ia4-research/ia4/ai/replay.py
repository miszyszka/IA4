"""
IA 4 — test silnika portfela AI Investor na danych historycznych (instrukcja, sekcja 11c.6–11c.7, krok AI-2).
Wersja projektu: 1.49 (2026-10-19) — musi zgadzać się z IA4_INSTRUKCJA.md

  python -m ia4.ai.replay                 # ostatnie 20 sesji kopii lokalnej, 60 strategii z brancha research
  python -m ia4.ai.replay --sessions 60   # dłużej

Świeca po świecy, bez modelu językowego: Inwestor „bierze każdego kandydata, na ile pozwalają limity”
(kolejność = pierwszeństwo strategii), księga cieni bierze każdego kandydata bez limitów. Sprawdza:
  • zgodność: każda transakcja cienia = ta sama transakcja policzona symulacją backtestu (ia4/lab/sim,
    każdy sygnał osobno) — wyjście, powód, zwrot; wynik musi brzmieć „rozbieżności 0”,
  • limity: najwięcej pozycji, ekspozycja, ryzyko otwarte — nigdy ponad 11c.7.
Niczego nie zapisuje (hub, branch `ai`, Excel bez zmian). Działa na kopii lokalnej — przed testem
`python -m ia4.sync` (albo `ia4 start`, który synchronizuje przy starcie).
"""

from __future__ import annotations

import argparse
import copy
import time
from collections import Counter

import numpy as np

from . import engine, market
from . import config as aicfg
from .playbook import Signals


def replay(frames: dict, traded: list[str], strategies: list[dict], cfg: dict, sessions: int = 20, log=print) -> dict:
    t0 = time.time()
    sig = Signals(frames, traded)
    m, key = sig.m, sig.key
    from ..lab import rules, sim
    from ..lab.portfolio import independent_trades
    masks = {s["id"]: rules.signal_mask(s["rule"], m, sig.lines(s)) & rules.filter_mask(s["rule"], m, sig.lines(s))
             for s in strategies}
    t_masks = time.time() - t0
    prices = market.Prices(stocks=frames)
    days = np.unique(m.date)
    window = days[-sessions:]
    keys = np.unique(key[np.isin(m.date, window)])
    seg = {sym: (int(a), int(b)) for sym, a, b in zip(m.symbols, m.seg_start, m.seg_end)}
    by_id = {s["id"]: s for s in strategies}
    main, shadow = engine.Book(cfg, "main"), engine.Book(cfg, "shadow")
    rej, n_sig, n_cand, n_in = Counter(), 0, 0, 0
    peak = cfg["capital"]
    worst = {"positions": 0, "grossPct": 0.0, "riskPct": 0.0, "ddPct": 0.0}
    origin = {}                                                    # id pozycji cienia → (strategia, indeks świecy sygnału)
    for k in keys:
        d = str(int(k))[:8]
        t_close = market.stock_close(f"{d[:4]}-{d[4:6]}-{d[6:8]}", int(k) % 10)
        prices.t_max = t_close + 1
        for b in (main, shadow):
            b.settle(prices)
        snap = main.snapshot(prices, t_close, cfg["capital"])
        eq = snap["equity"]
        peak = max(peak, eq)
        worst["ddPct"] = max(worst["ddPct"], 100 * (peak - eq) / peak)
        # sygnały na świecy k
        found = []
        for sym, (a, b) in seg.items():
            j = int(np.searchsorted(key[a:b], k)) + a
            if j >= b or key[j] != k or j + 1 >= b:
                continue
            for s in strategies:
                if masks[s["id"]][j]:
                    found.append((s["priority"], s["id"], sym, j))
        n_sig += len(found)
        best = {}
        for pr, sid, sym, j in sorted(found):
            best.setdefault(sym, (sid, j))
        cands = sorted(best.items(), key=lambda x: by_id[x[1][0]]["priority"])[: cfg["max_candidates"]]
        n_cand += len(cands)
        for sym, (sid, j) in cands:
            s = by_id[sid]
            side = 1 if s["direction"] == "long" else -1
            mult = cfg["mult"][s["basis_kind"]]
            kw = dict(round_id=f"k{k}", inst=sym, side=side, basis=sid, basis_kind=s["basis_kind"], decided_k=int(k), now=t_close,
                      sl_pct=s["sl"], tp_pct=s["tp"], max_bars=s["max_bars"], has_fc=s["has_fc"], mult=mult)
            fck = sig.fc_key(s, sym, int(k))
            q, r, _ = shadow.plan(prices, sym, side, s["sl"], mult, cfg["capital"], 1.0, t_close, limits=False)
            ps = shadow.add(prices, qty=q, risk=r, **kw)
            ps.fc_k = fck
            origin[ps.id] = (sid, j)
            snap = main.snapshot(prices, t_close, cfg["capital"])
            q, r, why = main.plan(prices, sym, side, s["sl"], mult, snap["equity"], cfg["risk_dial"], t_close, snap=snap)
            if why:
                rej[why.split(" (")[0]] += 1
                continue
            pm = main.add(prices, qty=q, risk=r, **kw)
            pm.fc_k = fck
            n_in += 1
            snap = main.snapshot(prices, t_close, cfg["capital"])
            worst["positions"] = max(worst["positions"], snap["positions"])
            worst["grossPct"] = max(worst["grossPct"], 100 * snap["gross"] / snap["equity"])
            worst["riskPct"] = max(worst["riskPct"], 100 * snap["risk"] / snap["equity"])
    prices.t_max = None
    # zgodność cieni z backtestem
    ref = {}
    for sid in {o[0] for o in origin.values()}:
        for row in independent_trades(by_id[sid]["rule"], m):
            ref[(sid, int(row[0]))] = (int(row[2]), float(row[3]), int(row[4]))
    kmap = {"SL": sim.K_SL, "TP": sim.K_TP, "FC": sim.K_FC, "LIMIT": sim.K_TIME}
    checked = bad = 0
    examples = []
    for p in shadow.closed():
        sid, j = origin[p.id]
        r = ref.get((sid, j))
        if r is None:
            continue
        checked += 1
        ok = key[r[0]] == p.exit_k and abs(engine.ret_gross_pct(p) - r[1]) < 1e-6 and kmap[p.reason] == r[2]
        if not ok:
            bad += 1
            if len(examples) < 5:
                examples.append(f"{sid} {p.inst} sygnał {key[j]}: silnik {p.exit_k} {p.reason} {engine.ret_gross_pct(p):+.4f}% · "
                                f"backtest {key[r[0]]} {r[2]} {r[1]:+.4f}%")
    cl = main.closed()
    net = np.array([p.ret_net_pct for p in cl]) if cl else np.zeros(0)
    end = main.snapshot(prices, time.time(), cfg["capital"])
    return {
        "sessions": int(window.size), "from": int(window[0]), "to": int(window[-1]), "rounds": int(keys.size),
        "signals": n_sig, "candidates": n_cand, "entered": n_in, "rejected": dict(rej),
        "closed": len(cl), "open": len(main.active()), "avgNetPct": float(net.mean()) if net.size else None,
        "avgR": float(np.mean([p.r_mult for p in cl])) if cl else None,
        "winShare": float((net > 0).mean()) if net.size else None,
        "realizedUsd": end["realized"], "equity": end["equity"], "worst": worst,
        "reasons": dict(Counter(p.reason for p in cl)),
        "shadow": {"closed": len(shadow.closed()), "avgNetPct": float(np.mean([p.ret_net_pct for p in shadow.closed()])) if shadow.closed() else None},
        "parity": {"checked": checked, "bad": bad, "examples": examples},
        "sec": {"masks": round(t_masks, 1), "total": round(time.time() - t0, 1)},
    }


def show(r: dict, cfg: dict, log=print) -> None:
    f = lambda d: f"{str(d)[:4]}-{str(d)[4:6]}-{str(d)[6:]}"
    log(f"\n  okno: {r['sessions']} sesji ({f(r['from'])} – {f(r['to'])}), {r['rounds']} świec")
    log(f"  sygnały {r['signals']} → kandydaci {r['candidates']} → wejścia {r['entered']}; odrzucone przez limity: "
        + (", ".join(f"{k} {v}" for k, v in sorted(r['rejected'].items(), key=lambda x: -x[1])) or "0"))
    a = r["avgNetPct"]
    usd = lambda x, sg="+": f"{x:{sg},.0f}".replace(",", " ")
    log(f"  Inwestor (wszyscy kandydaci w limitach): zamkniętych {r['closed']}, otwartych {r['open']} · "
        f"śr. wynik netto {'—' if a is None else f'{a:+.2f}%'} · śr. {'—' if r['avgR'] is None else f'{r['avgR']:+.2f}'}R · "
        f"wyjścia " + ", ".join(f"{k} {v}" for k, v in r['reasons'].items()) +
        f" · zrealizowane {usd(r['realizedUsd'])} $ · stan konta {usd(r['equity'], '')} $")
    w = r["worst"]
    log(f"  limity (najwięcej w oknie): pozycji {w['positions']}/{cfg['max_positions']} · ekspozycja {w['grossPct']:.0f}%/"
        f"{cfg['gross_max_pct']:.0f}% · ryzyko otwarte {w['riskPct']:.2f}%/{cfg['budget_pct']:.1f}% · obsunięcie {w['ddPct']:.2f}%")
    s = r["shadow"]["avgNetPct"]
    log(f"  cienie (każdy kandydat, bez limitów): zamkniętych {r['shadow']['closed']}, śr. wynik netto {'—' if s is None else f'{s:+.2f}%'}")
    p = r["parity"]
    log(f"  zgodność z backtestem (ia4/lab/sim): sprawdzonych transakcji {p['checked']}, rozbieżności {p['bad']}")
    for e in p["examples"]:
        log(f"    ! {e}")
    log(f"  czas: maski sygnałów {r['sec']['masks']} s, całość {r['sec']['total']} s")


def main() -> None:
    from .. import __version__
    from .. import config, sync
    from . import playbook
    ap = argparse.ArgumentParser(description="AI Investor — test silnika portfela na historii (bez modelu, nic nie zapisuje)")
    ap.add_argument("--sessions", type=int, default=20)
    ap.add_argument("--sync", action="store_true", help="najpierw synchronizacja akcji z Firestore")
    a = ap.parse_args()
    print(f"IA 4 — AI Investor: test silnika na historii (wersja {__version__})")
    u = config.universe()
    traded, ctx = u["main"] + u["proof"], u["context"]
    if a.sync:
        sync.sync(traded + ctx, quiet=True)
    frames = {s: sync.load(s) for s in traded + ctx if sync.parquet_path(s).exists()}
    pb = playbook.load(refresh=True)
    cfg = copy.deepcopy(aicfg.DEFAULTS)
    print(f"  {len(frames)} instrumentów w kopii, {len(pb['strategies'])} strategii w playbooku")
    r = replay(frames, traded, pb["strategies"], cfg, a.sessions)
    show(r, cfg)
    ok = r["parity"]["bad"] == 0 and r["worst"]["positions"] <= cfg["max_positions"] and \
        r["worst"]["riskPct"] <= cfg["budget_pct"] + 1e-6 and r["worst"]["grossPct"] <= cfg["gross_max_pct"] + 1e-6
    print(f"\nWYNIK: {'OK' if ok else 'BŁĄD'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
