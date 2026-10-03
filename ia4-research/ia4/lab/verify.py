"""
IA 4 — weryfikacja strategii na doubleProof (instrukcja, sekcja 6a).
Wersja projektu: 1.14 (2026-10-03) — musi zgadzać się z IA4_INSTRUKCJA.md

Bierze strategie aktywne (research/strategies/) i liczy je backtestowo — tym samym
silnikiem i tymi samymi zasadami (sekcja 8) — na 20 spółkach doubleProof, których
poszukiwanie nigdy nie widzi. Wynik: research/doubleproof.json na branchu `research`
(czyta go Research.gs → arkusz STRATEGIE DOUBLEPROOF).

Weryfikacja jest wyłącznie informacyjna: nie przyjmuje, nie odrzuca i nie zmienia
strategii, a jej wyniki nie wracają do poszukiwania.

Uruchomienie:
  automatycznie — przez python -m ia4.lab (start + co 30 min, gdy zmieniły się strategie),
  ręcznie       — python -m ia4.lab.verify   (synchronizacja, przeliczenie, push).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from .. import __version__
from .. import config as base_config
from . import data, rules, sim

RESULT_FILE = "doubleproof.json"
MIN_BARS = 200                      # instrument z krótszą historią jest pomijany


def dp_symbols() -> list[str]:
    try:
        return list(base_config.universe()["doubleProof"]) or list(base_config.DOUBLE_PROOF_FALLBACK)
    except Exception:
        return list(base_config.DOUBLE_PROOF_FALLBACK)


def refresh(data_dir: Path, sync_first: bool = True, log=print):
    """Dociąga z Firestore świece doubleProof (+ SPY, QQQ do filtrów) i wczytuje je od nowa."""
    if sync_first:
        try:
            import contextlib, io
            from .. import sync
            with contextlib.redirect_stdout(io.StringIO()):
                sync.sync(dp_symbols() + list(data.CONTEXT))
        except Exception as e:
            log(f"doubleProof: synchronizacja nieudana ({type(e).__name__}) — liczę na kopii lokalnej.")
    return load_dp_market(data_dir)


def load_dp_market(data_dir: Path):
    """Rynek doubleProof: bez skarbca (vault_bars = 0) — każda transakcja się liczy."""
    syms = [s for s in dp_symbols() if (data_dir / f"{s}.parquet").exists()]
    if not syms:
        return None
    try:
        return data.load_local(syms, data_dir, vault_bars=0)
    except RuntimeError:
        return None


def _block(s: np.ndarray) -> dict:
    n = int(s[sim.N])
    sh = (lambda k: round(float(s[k]) / n, 4)) if n else (lambda k: 0.0)
    return {"trades": n, "pf": round(float(sim.profit_factor(s[sim.GW], s[sim.GL])), 3),
            "avg_ret_pct": round(float(s[sim.SUMRET]) / n, 4) if n else 0.0,
            "tp_pct": sh(sim.NTP), "sl_pct": sh(sim.NSL), "fc_pct": sh(sim.NFC), "time_pct": sh(sim.NTIME),
            "cancelled": int(s[sim.NCANCEL])}


def _blind_pf(m, rule, cache: dict) -> float:
    """PF wejścia „na ślepo” na doubleProof (8.6 p. 10), ten sam kierunek, SL, TP, limit."""
    ex = rule["exit"]
    key = (rule["direction"], int(ex.get("max_bars") or 0), ex["sl"], ex["tp"])
    if key not in cache:
        se = rules._seg_end_of(m)
        t = np.flatnonzero((rules._pos(m) >= 150) & (np.arange(m.n) + 1 < se)).astype(np.int64)
        st, _ = sim.simulate(m.o, m.h, m.l, m.c, m.zone, se, t, np.full(t.size, -1, dtype=np.int64),
                             1 if rule["direction"] == "long" else -1, np.asarray([ex["sl"]], float),
                             np.asarray([ex["tp"]], float), int(ex.get("max_bars") or 0), -1, -1)
        g = st[0, 0].sum(axis=0)
        cache[key] = round(float(sim.profit_factor(g[sim.GW], g[sim.GL])), 3)
    return cache[key]


def evaluate(rec: dict, m, blind_cache: dict) -> dict:
    """Jedna strategia na doubleProof: wynik łączny, okresy, spółki, rodzaje wyjść."""
    rule = rec["rule"]
    ex = rule["exit"]
    stats, tr = rules.run(rule, m, [ex["sl"]], [ex["tp"]], rec=(0, 0))
    s = stats[0, 0]
    tot = _block(s.sum(axis=0))
    folds = [_block(s[k]) for k in range(1, 5)]
    out = {"id": rec["id"], "desc": rec.get("description", ""),
           "group": f"{rule['signal']['kind']}|{rule['direction']}",
           "sl": ex["sl"], "tp": ex["tp"], **tot,
           "folds_pf_gt1": sum(1 for f in folds if f["trades"] and f["pf"] > 1),
           "folds": [f["pf"] for f in folds]}
    # średni wynik wg rodzaju wyjścia i wyniki spółek
    if tr.size:
        for code, name in ((sim.K_FC, "fc_avg"), (sim.K_TP, "tp_avg"), (sim.K_SL, "sl_avg")):
            r = tr[tr[:, 4] == code, 3]
            out[name] = round(float(r.mean()), 4) if r.size else None
        inst = np.searchsorted(m.seg_end, tr[:, 0].astype(np.int64), side="right")
        per = {}
        for i in np.unique(inst):
            r = tr[inst == i, 3]
            per[m.symbols[i]] = {"trades": int(r.size),
                                 "pf": round(float(sim.profit_factor(r[r > 0].sum(), -r[r <= 0].sum())), 3),
                                 "sum_ret_pct": round(float(r.sum()), 3)}
        out["instruments"] = per
        out["instruments_traded"] = len(per)
        out["instruments_pf_gt1"] = sum(1 for v in per.values() if v["pf"] > 1)
    else:
        out.update({"fc_avg": None, "tp_avg": None, "sl_avg": None, "instruments": {},
                    "instruments_traded": 0, "instruments_pf_gt1": 0})
    out["blind_pf"] = _blind_pf(m, rule, blind_cache)
    out["edge"] = round(out["pf"] / max(out["blind_pf"], 0.01), 3) if out["trades"] else 0.0
    # porównanie z wynikiem z poszukiwania (grupa główna + skarbiec)
    st = rec.get("stats", {})
    mm, vv = st.get("main", {}), st.get("vault", {})
    n0 = mm.get("trades", 0) + vv.get("trades", 0)
    out["search_pf_w"] = round((mm.get("trades", 0) * min(mm.get("pf", 0), 10)
                                + vv.get("trades", 0) * min(vv.get("pf", 0), 10)) / n0, 3) if n0 else None
    return out


def _active_records(repo_dir: Path) -> list[dict]:
    out = []
    for p in sorted((repo_dir / "strategies").glob("S-*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def run(repo, m, log=print, force: bool = True) -> bool:
    """Przelicza WSZYSTKIE aktywne strategie na doubleProof (na aktualnie wczytanych danych).
    force=False — tylko gdy zmienił się zestaw strategii albo dane."""
    if m is None:
        log("doubleProof: brak danych na Macu (python -m ia4.sync) — weryfikacja pominięta.")
        return False
    recs = _active_records(repo.dir)
    old = repo.read_json(RESULT_FILE, {}) or {}
    ids = sorted(r["id"] for r in recs)
    sig = {"ids": ids, "last_date": int(m.last_date), "candles": int(m.n)}
    if not force and old.get("signature") == sig:
        return False
    results = {r["id"]: r for r in old.get("results", [])}       # wyniki zarchiwizowanych zostają
    cache: dict = {}
    for rec in recs:
        try:
            results[rec["id"]] = {**evaluate(rec, m, cache), "active": True}
        except Exception as e:                                    # zła reguła nie zatrzymuje reszty
            log(f"doubleProof: {rec['id']} — {type(e).__name__}: {e}")
    for rid, r in results.items():
        if rid not in ids:
            r["active"] = False
    now = datetime.now(timezone.utc)
    first = int(m.date.min())
    payload = {
        "version": __version__,
        "updatedAt": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "updatedAtPL": now.astimezone(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M"),
        "signature": sig,
        "data": {"instruments": len(m.symbols), "symbols": m.symbols, "candles": int(m.n),
                 "first_date": first, "last_date": int(m.last_date), "folds": m.fold_dates},
        "results": sorted(results.values(), key=lambda r: (not r.get("active"), r.get("trades", 0) < 10, -r.get("pf", 0))),
    }
    repo.write_json(RESULT_FILE, payload)
    act = [r for r in payload["results"] if r.get("active")]
    good = sum(1 for r in act if r["trades"] and r["pf"] >= 1.5)
    log(f"doubleProof: przeliczono {len(act)} strategii na {len(m.symbols)} spółkach "
        f"({first}–{m.last_date}); PF ≥ 1,5 ma {good}.")
    return True


def main() -> int:
    import argparse
    from . import store
    from .. import sync
    ap = argparse.ArgumentParser(description="IA 4 — strategie aktywne na doubleProof")
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    if not a.no_sync:
        try:
            sync.sync()
        except Exception as e:
            print(f"  ! Synchronizacja nieudana ({type(e).__name__}: {e}) — liczę na kopii lokalnej.")
    repo = store.ResultsRepo(base_config.RESEARCH_DIR / "research-repo", push=not a.no_push)
    repo.ensure()
    m = load_dp_market(base_config.CACHE_DIR)
    if run(repo, m, force=True):
        repo.commit_push("research: doubleProof — weryfikacja strategii aktywnych")
    return 0


if __name__ == "__main__":
    sys.exit(main())
