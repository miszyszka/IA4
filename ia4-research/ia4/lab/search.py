"""
IA 4 — pętla poszukiwania strategii (instrukcja, sekcja 9).
Wersja projektu: 1.1 (2026-09-30) — musi zgadzać się z IA4_INSTRUKCJA.md

Kolejność dla każdej reguły:
  1. symulacja na grupie głównej, wszystkie hipotezy SL × TP,
  2. sito: liczba transakcji, PF, stabilność w 4 okresach, PF sąsiednich SL/TP,
  3. stabilność parametrów: sąsiednie reguły (±10% okresu, sąsiedni próg…),
  4. duplikat? (ta sama rodzina, parametry w promieniu) → bez skarbca,
  5. OTWARCIE SKARBCA (liczone) → PF łączny i liczba transakcji w skarbcu,
  6. zapis strategii + natychmiastowy push.
Co `log_every_min` minut: status, dziennik, punkt wznowienia, push.
"""

from __future__ import annotations

import itertools
import json
import os
import platform
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from .. import __version__
from . import rules, settings, space, worker

PL = ZoneInfo("Europe/Warsaw")

TOTAL_KEYS = ("evals", "hypotheses", "eligible", "unstable", "promising", "duplicates",
              "vault_peeks", "accepted", "rejected_vault", "errors", "run_minutes")
CRITERIA_KEYS = ("sl_grid", "tp_grid", "min_trades_main", "pf_min", "pf_sltp_neighbors", "folds_min_ok",
                 "pf_param_neighbors", "param_neighbors_share_ok", "pf_edge_min", "dup_jaccard")


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _pl(dt):
    return dt.astimezone(PL).strftime("%Y-%m-%d %H:%M")


class Lab:
    def __init__(self, market, repo, data_dir: Path, traded: list, vault_bars: int,
                 state_dir: Path, check_report: dict, workers: int | None = None,
                 hours: float | None = None, log=print):
        self.m = market
        self.repo = repo
        self.data_dir = data_dir
        self.traded = traded
        self.vault_bars = vault_bars
        self.state_dir = state_dir
        self.check = check_report
        self.hours = hours
        self.log = log
        self.cfg = settings.merged(repo.read_json("config.json"))
        self.workers = workers or self.cfg["workers"] or max(1, (os.cpu_count() or 2) - 1)
        self.th = space.thresholds(market)

        cp = repo.read_json("checkpoint.json", {}) or {}
        self.totals = {k: 0 for k in TOTAL_KEYS}
        self.totals.update(cp.get("totals", {}))
        self.grid = cp.get("grid", {"signature": "", "cursor": 0, "total": 0, "done": False})
        self.pool = {e["key"]: e for e in cp.get("pool", [])}
        self.accepted = cp.get("accepted", [])
        self.rejected = cp.get("rejected", [])
        self.recent = cp.get("recent_strategies", [])
        self.rng = random.Random(cp.get("rng_seed", int(time.time())))
        self.first_start = cp.get("first_start", _iso(_now()))
        self.session = {k: 0 for k in TOTAL_KEYS}
        self.at_last_log = dict(self.totals)
        self.tested = self._load_tested()
        self._new_tested = []
        self._check_grid_signature()

    # ------------------------------------------------------------ stan lokalny
    def _load_tested(self) -> set:
        p = self.state_dir / "tested.txt"
        if not p.exists():
            return set()
        return set(p.read_text().split())

    def _flush_tested(self):
        if not self._new_tested:
            return
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with (self.state_dir / "tested.txt").open("a") as f:
            f.write("\n".join(self._new_tested) + "\n")
        self._new_tested = []

    def _check_grid_signature(self):
        sig = space.grid_signature(self.cfg)
        if self.grid.get("signature") != sig:
            if self.grid.get("signature"):
                self.log(f"Siatka zmieniona w config.json — zaczynam ją od początku (podpis {sig}).")
            self.grid = {"signature": sig, "cursor": 0, "total": space.grid_total(self.cfg), "done": False}
        self._grid_it = None

    def _task(self, rule):
        return {"key": rules.signal_key(rule), "rule": rule, "cfg": self.cfg}

    # ------------------------------------------------------------ źródła zadań
    def _grid_tasks(self, k):
        if self._grid_it is None:
            self._grid_it = itertools.islice(space.grid_iter(self.cfg), self.grid["cursor"], None)
        out = []
        for rule in self._grid_it:
            self.grid["cursor"] += 1
            key = rules.signal_key(rule)
            if key in self.tested:
                continue
            out.append({"key": key, "rule": rule, "cfg": self.cfg})
            if len(out) >= k:
                break
        if not out and self.grid["cursor"] >= self.grid["total"]:
            self.grid["done"] = True
            self.log("Siatka zakończona — przechodzę do poszukiwania adaptacyjnego.")
        return out

    def _pick_parent(self):
        entries = list(self.pool.values())
        cand = self.rng.sample(entries, min(3, len(entries)))
        return max(cand, key=lambda e: e["score"])["rule"]

    def _adaptive_tasks(self, k):
        out, keys = [], set()
        for _ in range(k * 20):
            if len(out) >= k:
                break
            if not self.pool or self.rng.random() < self.cfg["explore_share"]:
                rule = space.random_rule(self.rng, self.cfg, self.th)
            else:
                rule = space.mutate(self._pick_parent(), self.rng, self.cfg, self.th)
            if rule["signal"]["kind"] in self.cfg["paused_kinds"] or not space.valid(rule, self.cfg):
                continue
            key = rules.signal_key(rule)
            if key in self.tested or key in keys:
                continue
            keys.add(key)
            out.append({"key": key, "rule": rule, "cfg": self.cfg})
        return out

    def phase(self):
        return "adaptacja" if self.grid["done"] else "siatka"

    # ------------------------------------------------------------ pula rodziców
    def _pool_add(self, res):
        if res["score"] <= 0:
            return
        self.pool[res["key"]] = {"key": res["key"], "score": round(res["score"], 4), "n": res["n"],
                                 "pf": round(res["pf"], 3), "edge": round(res.get("edge", 0), 3),
                                 "best": res["best"], "rule": res["rule"]}
        limit = self.cfg["pool_size"]
        if len(self.pool) > limit * 1.2:
            per_fam, keep = {}, {}
            for e in sorted(self.pool.values(), key=lambda e: -e["score"]):
                fam = space.family(e["rule"])
                if per_fam.get(fam, 0) >= self.cfg["pool_per_family"]:
                    continue
                per_fam[fam] = per_fam.get(fam, 0) + 1
                keep[e["key"]] = e
                if len(keep) >= limit:
                    break
            self.pool = keep

    def _count(self, key, n=1):
        self.totals[key] += n
        self.session[key] += n

    # ------------------------------------------------------------ obiecujące → skarbiec
    def _full_rule(self, res, a, b):
        rule = json.loads(json.dumps(res["rule"]))
        rule["exit"]["sl"] = self.cfg["sl_grid"][a]
        rule["exit"]["tp"] = self.cfg["tp_grid"][b]
        return rule

    def _handle_eligible(self, res, ex):
        rule = self._full_rule(res, *res["elig_best"])
        nbrs = space.neighbors(rule, self.cfg, self.th, self.rng)
        pfs = []
        if nbrs:
            outs = ex.map(worker.evaluate_fixed, [{"rule": r, "cfg": self.cfg} for r in nbrs])
            pfs = [o["pf"] for o in outs]
            self._count("evals", len(nbrs))
        med = float(np.median(pfs)) if pfs else 0.0
        share = float(np.mean([p >= 1.0 for p in pfs])) if pfs else 0.0
        if not pfs or med < self.cfg["pf_param_neighbors"] or share < self.cfg["param_neighbors_share_ok"]:
            self._count("unstable")
            return
        self._count("promising")
        entries = np.asarray(ex.apply(worker.main_entries, {"rule": rule}), dtype=np.int64)
        if self._duplicate(rule["direction"], entries):
            self._count("duplicates")
            return
        self._open_vault(rule, res, med, share, ex, entries)

    # ------------------------------------------------------------ duplikaty
    def _entries_of(self, rule):
        return np.asarray(worker.main_entries({"rule": rule}), dtype=np.int64)

    def _build_dedup(self):
        """Świece wejścia strategii zapisanych i odrzuconych — liczone na bieżących danych."""
        worker.set_market(self.m)
        self.known = [(r["direction"], self._entries_of(r)) for r in self.accepted + self.rejected[-500:]]

    def _duplicate(self, direction, entries) -> bool:
        if entries.size == 0:
            return False
        thr = self.cfg["dup_jaccard"]
        for d, e in self.known:
            if d != direction or e.size == 0:
                continue
            inter = np.intersect1d(entries, e, assume_unique=True).size
            if inter / (entries.size + e.size - inter) >= thr:
                return True
        return False

    def _open_vault(self, rule, res, nb_med, nb_share, ex, entries):
        """BRAMKA SKARBCA — jedyne miejsce, które prosi proces roboczy o wyniki skarbca."""
        self._count("vault_peeks")
        full = ex.apply(worker.open_vault, {"rule": rule})
        main, vault, comb = full["main"], full["vault"], full["combined"]
        ok = (main["trades"] >= self.cfg["min_trades_main"] and main["pf"] >= self.cfg["pf_min"]
              and vault["trades"] >= self.cfg["min_trades_vault"] and comb["pf"] >= self.cfg["pf_min"])
        sid = rules.rule_id(rule)
        now = _now()
        self.repo.append_jsonl("vault.jsonl", {
            "at": _iso(now), "peek": self.totals["vault_peeks"], "id": sid, "accepted": ok,
            "main_pf": main["pf"], "main_trades": main["trades"],
            "blind_pf": full["blind_entry_main"]["pf"], "vault_pf": vault["pf"],
            "vault_trades": vault["trades"], "combined_pf": comb["pf"], "combined_trades": comb["trades"],
            "desc": space.describe(rule)})
        self.known.append((rule["direction"], entries))
        if not ok:
            self._count("rejected_vault")
            self.rejected.append(rule)
            self.rejected = self.rejected[-2000:]
            return
        self._count("accepted")
        self.accepted.append(rule)
        rec = {
            "id": sid, "version": __version__, "found_at": _iso(now), "found_at_pl": _pl(now),
            "description": space.describe(rule),
            "rule": json.loads(rules.canonical(rule)),
            "execution": {"entry": "open świecy po sygnale", "intrabar": "najpierw SL, potem TP",
                          "gap": "luka przez SL → cena otwarcia; luka przez TP → poziom TP",
                          "fc": "sygnał FC na zamknięciu → wyjście po open następnej świecy",
                          "time": "limit → wyjście po close ostatniej świecy",
                          "positions": "jedna naraz na instrument", "costs": 0},
            "stats": full,
            "sltp_hypotheses": {"sl": self.cfg["sl_grid"], "tp": self.cfg["tp_grid"],
                                "pf_main": res.get("pf_matrix"), "trades_main": res.get("n_matrix")},
            "robustness": {"sltp_neighbors_median_pf": round(res["elig_nb"], 3),
                           "edge_vs_blind_entry": round(res["elig_edge"], 3),
                           "folds_ok": res["elig_folds_ok"],
                           "param_neighbors_median_pf": round(nb_med, 3),
                           "param_neighbors_share_pf_ge_1": round(nb_share, 3)},
            "data": {"last_date": self.m.last_date, "instruments": len(self.m.symbols),
                     "vault_bars_per_instrument": self.vault_bars, "folds": self.m.fold_dates},
            "search": {"phase": self.phase(), "evals_before": self.totals["evals"],
                       "vault_peek_no": self.totals["vault_peeks"]},
            "criteria": {k: self.cfg[k] for k in CRITERIA_KEYS + ("min_trades_vault",)},
        }
        self.repo.write_json(f"strategies/{sid}.json", rec)
        summary = {"id": sid, "found_at": rec["found_at"], "desc": rec["description"],
                   "main_pf": main["pf"], "blind_pf": full["blind_entry_main"]["pf"],
                   "vault_pf": vault["pf"], "combined_pf": comb["pf"],
                   "trades": comb["trades"], "win_rate": comb["win_rate"]}
        self.repo.append_jsonl("strategies.jsonl", summary)
        self.recent = (self.recent + [summary])[-20:]
        self.log(f"★ Nowa strategia {sid}: PF łączny {comb['pf']} ({comb['trades']} transakcji) — "
                 f"{rec['description']}")
        self.repo.commit_push(f"research: strategia {sid} (PF {comb['pf']})")

    # ------------------------------------------------------------ log co 30 min
    def _write_status(self, started, note=""):
        now = _now()
        minutes = (now - self.last_log_at).total_seconds() / 60
        self._count("run_minutes", round(minutes, 1))
        self.last_log_at = now
        d = {k: round(self.totals[k] - self.at_last_log.get(k, 0), 1) for k in TOTAL_KEYS}
        self.at_last_log = dict(self.totals)
        best = sorted(self.pool.values(), key=lambda e: -e["score"])[:10]
        grid_pct = round(100.0 * min(self.grid["cursor"], self.grid["total"]) / max(1, self.grid["total"]), 2)
        eval_rate = round(d["evals"] / minutes, 1) if minutes > 0 else 0.0
        status = {
            "version": __version__,
            "updatedAt": _iso(now), "updatedAtPL": _pl(now),
            "host": platform.node(), "workers": self.workers,
            "run": {"startedAt": _iso(started), "startedAtPL": _pl(started),
                    "uptime_min": round((now - started).total_seconds() / 60, 1),
                    "evals_per_min": eval_rate},
            "phase": self.phase(),
            "grid": {"done": self.grid["done"], "cursor": self.grid["cursor"], "total": self.grid["total"],
                     "pct": grid_pct},
            "data": {"last_date": self.m.last_date, "instruments": len(self.m.symbols),
                     "candles": int(self.m.n), "check": self.check.get("summary", {})},
            "totals": self.totals, "session": self.session,
            "pool": len(self.pool),
            "best_candidates": [{"score": e["score"], "trades": e["n"], "pf": e["pf"], "edge": e.get("edge"),
                                 "sl": self.cfg["sl_grid"][e["best"][0]], "tp": self.cfg["tp_grid"][e["best"][1]],
                                 "desc": space.describe(e["rule"])} for e in best],
            "recent_strategies": self.recent,
            "config": {k: self.cfg[k] for k in CRITERIA_KEYS + ("min_trades_vault", "paused_kinds")},
            "note": note,
        }
        self.repo.write_json("status.json", status)
        self.repo.append_jsonl("log.jsonl", {
            "at": _iso(now), "atPL": _pl(now), "host": platform.node(), "phase": self.phase(),
            "grid_pct": grid_pct, "evals": self.totals["evals"], "evals_delta": d["evals"],
            "evals_per_min": eval_rate, "hypotheses": self.totals["hypotheses"],
            "eligible": self.totals["eligible"], "promising": self.totals["promising"],
            "promising_delta": d["promising"], "vault_peeks": self.totals["vault_peeks"],
            "vault_delta": d["vault_peeks"], "accepted": self.totals["accepted"],
            "accepted_delta": d["accepted"], "rejected_vault": self.totals["rejected_vault"],
            "best_score": best[0]["score"] if best else 0, "pool": len(self.pool),
            "data_last": self.m.last_date, "data_ok": bool(self.check.get("summary", {}).get("ok")),
            "errors": self.totals["errors"], "note": note})
        self.repo.write_json("checkpoint.json", {
            "version": __version__, "saved_at": _iso(now), "first_start": self.first_start,
            "grid": self.grid, "totals": self.totals, "rng_seed": self.rng.randrange(1 << 30),
            "pool": sorted(self.pool.values(), key=lambda e: -e["score"]),
            "accepted": self.accepted, "rejected": self.rejected[-2000:], "recent_strategies": self.recent})
        self._flush_tested()
        ok = self.repo.commit_push(f"research: log {_pl(now)} — {self.phase()}, "
                                   f"{self.totals['evals']} reguł, skarbiec {self.totals['vault_peeks']}, "
                                   f"strategii {self.totals['accepted']}")
        self.log(f"[{_pl(now)}] {self.phase()} {grid_pct}% · reguł {self.totals['evals']} "
                 f"(+{int(d['evals'])}, {eval_rate}/min) · obiecujących {self.totals['promising']} · "
                 f"skarbiec {self.totals['vault_peeks']} · strategii {self.totals['accepted']}"
                 + ("" if ok else f" · PUSH NIEUDANY: {self.repo.last_error}"))

    def _reload_config(self):
        self.repo.pull()
        new = settings.merged(self.repo.read_json("config.json"))
        if new != self.cfg:
            self.log("Wczytano zmieniony research/config.json.")
            self.cfg = new
            self._check_grid_signature()

    # ------------------------------------------------------------ główna pętla
    def run(self):
        started = _now()
        self.last_log_at = started
        if self.repo.read_json("config.json") is None:
            self.repo.write_json("config.json", {"_opis": "Nadpisania ustawień z ia4/lab/settings.py. "
                                                 "Puste = wartości domyślne. Zmienia Claude lub człowiek.",
                                                 **{k: settings.DEFAULTS[k] for k in CRITERIA_KEYS + ("min_trades_vault",)}})
        self.log("Kompiluję silnik i przygotowuję wykrywanie duplikatów…")
        worker.warmup(self.m)
        self._build_dedup()
        ex = _Executor(self.workers, self.data_dir, self.traded, self.vault_bars, self.m)
        self.log(f"Start: {self.phase()}, siatka {self.grid['cursor']}/{self.grid['total']}, "
                 f"procesów {self.workers}, przetestowanych wcześniej reguł {len(self.tested)}.")
        self._write_status(started, note="start")
        deadline = started.timestamp() + self.hours * 3600 if self.hours else None
        batch = self.cfg["batch"] or 24 * self.workers
        note = "zatrzymano"
        try:
            while True:
                tasks = self._grid_tasks(batch) if not self.grid["done"] else self._adaptive_tasks(batch)
                if not tasks:
                    continue
                eligible = []
                for res in ex.imap(worker.evaluate, tasks):
                    self.tested.add(res["key"])
                    self._new_tested.append(res["key"])
                    if "error" in res:
                        self._count("errors")
                        continue
                    self._count("evals")
                    self._count("hypotheses", len(self.cfg["sl_grid"]) * len(self.cfg["tp_grid"]))
                    self._pool_add(res)
                    if res["eligible"]:
                        self._count("eligible")
                        eligible.append(res)
                for res in eligible:
                    self._handle_eligible(res, ex)
                if (_now() - self.last_log_at).total_seconds() >= self.cfg["log_every_min"] * 60:
                    self._write_status(started)
                    self._reload_config()
                    batch = self.cfg["batch"] or 24 * self.workers
                if deadline and time.time() >= deadline:
                    note = "koniec zadanego czasu"
                    break
        except KeyboardInterrupt:
            self.log("\nPrzerwano (Ctrl+C) — zapisuję stan…")
        finally:
            ex.close()
            self._write_status(started, note=note)


class _Executor:
    """Pula procesów; przy 1 procesie liczy w bieżącym (łatwiejsze testy)."""

    def __init__(self, n, data_dir, traded, vault_bars, market):
        self.n = n
        if n <= 1:
            worker.set_market(market)
            self.pool = None
        else:
            import multiprocessing as mp
            ctx = mp.get_context("spawn")
            self.pool = ctx.Pool(n, initializer=worker.init, initargs=(str(data_dir), traded, vault_bars))

    def imap(self, fn, tasks):
        if self.pool is None:
            return map(fn, tasks)
        return self.pool.imap_unordered(fn, tasks, chunksize=2)

    def map(self, fn, tasks):
        return list(map(fn, tasks)) if self.pool is None else self.pool.map(fn, tasks)

    def apply(self, fn, task):
        return fn(task) if self.pool is None else self.pool.apply(fn, (task,))

    def close(self):
        if self.pool is not None:
            self.pool.terminate()
            self.pool.join()
