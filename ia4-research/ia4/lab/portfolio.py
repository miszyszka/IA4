"""
IA 4 — jednorazowy backtest portfela (instrukcja, sekcja 6b).
Wersja projektu: 1.21 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

Symuluje wirtualnego inwestora na historii: wszystkie strategie aktywne naraz, na
spółkach grupy głównej (53, z podziałem na skarbiec i okresy) i na doubleProof (20).
Każda transakcja liczona tym samym silnikiem i na tych samych zasadach co strategie
(sekcja 8.6); poziom portfela dokłada tylko zasady inwestora:

  • limit pozycji na spółkę — bez limitu (każda strategia osobno, jak dziś) albo 1,
  • pierwszeństwo, gdy kilka strategii daje sygnał na tej samej spółce na tej samej świecy,
  • koszt transakcyjny — % wartości pozycji przy wejściu i przy wyjściu,
  • stawka — stała 100 $ albo według SL (100 $ × 5 / SL%: strata na SL zawsze ok. 5 $).

Wybór strategii i pierwszeństwo: szacunek przewagi z doubleProof „ściągnięty” do średniej
wszystkich strategii (empiryczny Bayes) — im mniej transakcji, tym bliżej średniej.

Wynik: research/portfolio-backtest.json (branch `research`, zapisany raz) → arkusz
BACKTEST PORTFELA; lista `priority` → pierwszeństwo strategii w wirtualnym inwestorze.

Uruchomienie (w ia4-research/, z aktywnym .venv):
  python -m ia4.lab.portfolio            # synchronizacja, backtest, zapis, push
  python -m ia4.lab.portfolio --force    # nadpisuje istniejący zapis
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

from .. import __version__
from .. import config as base_config
from . import data, rules, sim, verify

RESULT_FILE = "portfolio-backtest.json"
COST_PCT = 0.005          # % wartości pozycji przy wejściu i przy wyjściu (instrukcja 11a)
STAKE = 100.0             # $ na transakcję
RISK_REF_SL = 5.0         # stawka wg SL: STAKE × RISK_REF_SL / SL%
SELECT_MIN = 0.40         # wybór: szacunek przewagi (po ściągnięciu) ≥ tyle % na transakcję
KIND_NAMES = {sim.K_SL: "sl", sim.K_TP: "tp", sim.K_FC: "fc", sim.K_TIME: "time"}


# ----------------------------------------------------------------------------- transakcje
def independent_trades(rule: dict, m) -> np.ndarray:
    """Wynik transakcji otwartej na KAŻDYM sygnale osobno (bez „jednej pozycji naraz”).
    Kolumny: t, e, wyjście, zwrot %, rodzaj, strefa; anulowane mają rodzaj 0 i wyjście = koniec serii."""
    sig_t, fcb, _ = rules.entries(rule, m)
    if not sig_t.size:
        return np.zeros((0, 6))
    se = rules._seg_end_of(m)
    d = 1 if rule["direction"] == "long" else -1
    ex = rule["exit"]
    sl = np.asarray([ex["sl"]], float)
    tp = np.asarray([ex["tp"]], float)
    mb = int(ex.get("max_bars") or 0)
    out = np.zeros((sig_t.size, 6))
    for i in range(sig_t.size):
        _, rec = sim.simulate(m.o, m.h, m.l, m.c, m.zone, se, sig_t[i:i + 1], fcb[i:i + 1], d, sl, tp, mb, 0, 0)
        if rec.shape[0]:
            out[i] = rec[0]
        else:                                                  # anulowana — blokuje spółkę do końca danych
            t = sig_t[i]
            out[i] = (t, t + 1, se[t], 0.0, sim.K_CANCEL, m.zone[t + 1])
    return out


def candidates(recs: list, m) -> dict:
    """{indeks strategii: transakcje} na danym rynku."""
    return {k: independent_trades(r["rule"], m) for k, r in enumerate(recs)}


# ----------------------------------------------------------------------------- portfel
def run_portfolio(recs, cand, m, chosen, prio, per_ticker_limit, cost, sizing):
    """Lista przyjętych transakcji: (strategia, spółka, t, e, wyjście, zwrot netto %, rodzaj, strefa, stawka $)."""
    inst_of = np.searchsorted(m.seg_end, np.arange(m.n), side="right")
    rows = []
    for k in chosen:
        tr = cand[k]
        for x in tr:
            rows.append((int(inst_of[int(x[0])]), int(x[0]), prio[k], k, x))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    busy_strat = {}                 # (spółka, strategia) → świeca wyjścia
    busy_ticker = {}                # spółka → świeca wyjścia
    taken = []
    for inst, t, _, k, x in rows:
        if t < busy_strat.get((inst, k), -1):
            continue                                           # jedna pozycja naraz w strategii (8.6 p. 5)
        if per_ticker_limit == 1 and t < busy_ticker.get(inst, -1):
            continue                                           # spółka zajęta przez inną strategię
        exit_bar = int(x[2])
        busy_strat[(inst, k)] = exit_bar
        busy_ticker[inst] = max(busy_ticker.get(inst, -1), exit_bar)
        if int(x[4]) == sim.K_CANCEL:
            continue
        sl = recs[k]["rule"]["exit"]["sl"]
        stake = STAKE if sizing == "flat" else STAKE * RISK_REF_SL / sl
        taken.append((k, inst, t, int(x[1]), exit_bar, float(x[3]) - 2 * cost, int(x[4]), int(x[5]), stake))
    return taken


def summarize(taken, m, recs, zones):
    rows = [r for r in taken if r[7] in zones]
    n = len(rows)
    if not n:
        return {"trades": 0}
    ret = np.array([r[5] for r in rows])
    usd = np.array([r[5] * r[8] / 100 for r in rows])
    key = np.array([m.date[r[4]] * 10 + m.slot[r[4]] for r in rows])   # kolejność wg świecy wyjścia
    eq = np.cumsum(usd[np.argsort(key, kind="stable")])
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], eq])) - np.concatenate([[0.0], eq])))
    kinds = np.array([r[6] for r in rows])
    hold = np.array([r[4] - r[3] + 1 for r in rows])
    longs = np.array([recs[r[0]]["rule"]["direction"] == "long" for r in rows])
    gw, gl = usd[usd > 0].sum(), -usd[usd <= 0].sum()
    out = {
        "trades": n,
        "pf": round(float(sim.profit_factor(gw, gl)), 3),
        "avg_ret_pct": round(float(ret.mean()), 4),
        "sum_usd": round(float(usd.sum()), 2),
        "max_dd_usd": round(dd, 2),
        "ret_to_dd": round(float(usd.sum()) / dd, 2) if dd > 0 else None,
        "hold_median": float(np.median(hold)),
        "sum_usd_long": round(float(usd[longs].sum()), 2),
        "sum_usd_short": round(float(usd[~longs].sum()), 2),
        "trades_long": int(longs.sum()),
        "trades_short": int((~longs).sum()),
        "instruments": int(len({r[1] for r in rows})),
    }
    for code, name in KIND_NAMES.items():
        out[f"{name}_pct"] = round(float((kinds == code).mean()), 4)
    return out


# ----------------------------------------------------------------------------- wybór
def shrink_ranking(recs, cand_dp, m_dp):
    """Szacunek przewagi każdej strategii na doubleProof ściągnięty do średniej (empiryczny Bayes).
    Transakcje jak w strategii (jedna pozycja naraz), bez kosztów — jak backtest doubleProof."""
    per = []
    for k, r in enumerate(recs):
        x = run_portfolio(recs, cand_dp, m_dp, [k], {k: 0}, None, 0.0, "flat")
        rets = np.array([t[5] for t in x])
        hold = np.array([t[4] - t[3] + 1 for t in x])
        per.append((k, rets, float(np.median(hold)) if hold.size else None))
    allr = np.concatenate([p[1] for p in per if p[1].size]) if any(p[1].size for p in per) else np.zeros(1)
    sd = float(allr.std()) or 1.0
    avgs = np.array([p[1].mean() for p in per if p[1].size])
    ns = np.array([p[1].size for p in per if p[1].size])
    mu = float(avgs.mean()) if avgs.size else 0.0
    samp = float(np.mean(sd * sd / ns)) if ns.size else 0.0
    tau2 = max(float(avgs.var()) - samp, 0.02)
    out = []
    for k, rets, hold in per:
        r = recs[k]
        n = int(rets.size)
        avg = float(rets.mean()) if n else 0.0
        w = tau2 / (tau2 + sd * sd / n) if n else 0.0
        est = mu + w * (avg - mu)
        out.append({"id": r["id"], "group": f"{r['rule']['signal']['kind']}|{r['rule']['direction']}",
                    "dp_trades": n, "dp_avg_ret_pct": round(avg, 4), "dp_hold_median": hold,
                    "shrunk_pct": round(est, 4), "weight": round(w, 3), "selected": bool(est >= SELECT_MIN and n > 0)})
    out.sort(key=lambda x: -x["shrunk_pct"])
    stats = {"pooled_sd_pct": round(sd, 3), "mean_pct": round(mu, 4), "tau_pct": round(math.sqrt(tau2), 3),
             "select_min_pct": SELECT_MIN}
    return out, stats


# ----------------------------------------------------------------------------- całość
def run(repo, m_main, m_dp, log=print) -> dict | None:
    recs = verify._active_records(repo.dir)
    if not recs or m_main is None or m_dp is None:
        log("Brak strategii albo danych (python -m ia4.sync) — backtest portfela pominięty.")
        return None
    log(f"Strategie: {len(recs)}; transakcje na każdym sygnale osobno…")
    cand_main = candidates(recs, m_main)
    cand_dp = candidates(recs, m_dp)
    ranking, rstats = shrink_ranking(recs, cand_dp, m_dp)
    idx = {r["id"]: k for k, r in enumerate(recs)}
    prio = {idx[x["id"]]: i for i, x in enumerate(ranking)}
    all_k = list(range(len(recs)))
    sel_k = [idx[x["id"]] for x in ranking if x["selected"]]
    variants = [
        ("Dziś: wszystkie strategie, bez limitu, 100 $, bez kosztów", all_k, None, 0.0, "flat"),
        ("Wszystkie, 1 pozycja na spółkę, koszty", all_k, 1, COST_PCT, "flat"),
        (f"Wybrane ({len(sel_k)}), 1 pozycja na spółkę, koszty", sel_k, 1, COST_PCT, "flat"),
        ("Wszystkie, 1 pozycja na spółkę, koszty, stawka wg SL", all_k, 1, COST_PCT, "risk"),
        (f"Wybrane ({len(sel_k)}), 1 pozycja na spółkę, koszty, stawka wg SL", sel_k, 1, COST_PCT, "risk"),
    ]
    out_v = []
    for name, ks, lim, cost, sizing in variants:
        tm = run_portfolio(recs, cand_main, m_main, ks, prio, lim, cost, sizing)
        td = run_portfolio(recs, cand_dp, m_dp, ks, prio, lim, cost, sizing)
        u = {"main": summarize(tm, m_main, recs, (1, 2, 3, 4)),
             "vault": summarize(tm, m_main, recs, (0,)),
             "dp": summarize(td, m_dp, recs, (0, 1, 2, 3, 4))}
        for k in range(1, 5):
            u[f"dp_fold{k}"] = summarize(td, m_dp, recs, (k,))
        out_v.append({"name": name, "strategies": len(ks), "per_ticker_limit": lim, "cost_pct": cost,
                      "sizing": sizing, "universes": u})
        log(f"  {name}: główna {u['main'].get('sum_usd')} $, doubleProof {u['dp'].get('sum_usd')} $ "
            f"(PF {u['dp'].get('pf')}, transakcji {u['dp'].get('trades')})")
    now = datetime.now(timezone.utc)
    payload = {
        "version": __version__,
        "kind": "jednorazowy backtest portfela (wirtualny inwestor na historii)",
        "createdAt": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "createdAtPL": now.astimezone(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M"),
        "params": {"stake_usd": STAKE, "cost_pct_per_side": COST_PCT, "risk_ref_sl_pct": RISK_REF_SL,
                   "select_min_pct": SELECT_MIN},
        "data": {
            "main": {"instruments": len(m_main.symbols), "candles": int(m_main.n), "first_date": int(m_main.date.min()),
                     "last_date": int(m_main.last_date), "folds": m_main.fold_dates},
            "dp": {"instruments": len(m_dp.symbols), "candles": int(m_dp.n), "first_date": int(m_dp.date.min()),
                   "last_date": int(m_dp.last_date), "folds": m_dp.fold_dates},
        },
        "selection": {**rstats, "selected": len(sel_k), "ranking": ranking},
        "priority": [x["id"] for x in ranking],
        "variants": out_v,
    }
    repo.write_json(RESULT_FILE, payload)
    return payload


def main() -> int:
    import argparse
    from . import store
    ap = argparse.ArgumentParser(description="IA 4 — jednorazowy backtest portfela")
    ap.add_argument("--force", action="store_true", help="nadpisz istniejący zapis")
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    print(f"IA 4 — jednorazowy backtest portfela (wersja {__version__})\n")
    repo = store.ResultsRepo(base_config.RESEARCH_DIR / "research-repo", push=not a.no_push)
    repo.ensure()
    old = repo.read_json(RESULT_FILE)
    if old and not a.force:
        print(f"Backtest portfela już zapisany ({old.get('createdAtPL')}) — nic nie zmieniam. Nowy: --force.")
        return 0
    if not a.no_sync:
        try:
            from .. import sync
            sync.sync()
        except Exception as e:
            print(f"  ! Synchronizacja nieudana ({type(e).__name__}: {e}) — liczę na kopii lokalnej.")
    from .__main__ import _traded_symbols
    m_main = data.load_local(_traded_symbols(), base_config.CACHE_DIR)
    m_dp = verify.load_dp_market(base_config.CACHE_DIR)
    payload = run(repo, m_main, m_dp)
    if payload is None:
        return 1
    repo.commit_push(f"research: jednorazowy backtest portfela — {len(payload['variants'])} wariantów")
    print("Gotowe. Arkusz BACKTEST PORTFELA i pierwszeństwo strategii w wirtualnym inwestorze odświeżą się przy "
          "najbliższym researchSync (albo menu IA 4 → „Odśwież RESEARCH teraz”).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
