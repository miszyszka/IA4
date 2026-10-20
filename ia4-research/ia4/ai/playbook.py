"""
IA 4 — playbook Agent-Investora i sygnały strategii na Macu (instrukcja, sekcje 11c.6, 11c.8).
Wersja projektu: 1.50 (2026-10-20) — musi zgadzać się z IA4_INSTRUKCJA.md

Playbook na start (AI-2) = 60 aktywnych strategii Etapu 2, status `bazowa`: „wybrane” w backteście
portfela (6b) — mnożnik ryzyka 1,0 (`bazowa_wybrana`), pozostałe 0,5. Źródło: branch `research`
(strategies.jsonl, strategies/S-*.json, backtest-doubleproof.json, portfolio-backtest.json) i wynik
mechanicznego inwestora na żywo (telemetry/vi.json na `main`, gdy istnieje) — czytane przez
`git fetch` + `git show` w repozytorium ~/Desktop/IA4 (tylko odczyt, zasada 11). Kopia: data/ai/playbook.json
(praca bez sieci).

Sygnały: ten sam silnik co poszukiwanie i test zgodności z PaperEngine.gs (`ia4/lab/rules.py`) — na
ostatniej świecy każdej z 53 spółek. FC pozycji: `rules.fc_bars` od świecy sygnału.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .. import config as base_config
from ..lab import data, rules

CACHE = base_config.CACHE_DIR / "ai" / "playbook.json"
REPO = base_config.RESEARCH_DIR.parent           # ~/Desktop/IA4


def _git(*args, timeout=60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=timeout)


def git_show(path: str, ref: str) -> str | None:
    try:
        r = _git("show", f"{ref}:{path}", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def fetch(log=print) -> bool:
    try:
        r = _git("fetch", "-q", "origin", "research", "main")
        if r.returncode != 0:
            log(f"  ! git fetch: {r.stderr.strip()[:200]}")
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError) as e:
        log(f"  ! git fetch: {e}")
        return False


def build(read=git_show, log=print) -> dict:
    """Playbook z brancha `research` (+ vi.json z `main`). `read(path, ref)` — wstrzykiwane w selftest."""
    R = "origin/research"
    idx = read("research/strategies.jsonl", R)
    if not idx:
        raise RuntimeError("brak research/strategies.jsonl")
    rows = [json.loads(l) for l in idx.splitlines() if l.strip()]
    pf = json.loads(read("research/portfolio-backtest.json", R) or "{}")
    rank = {x["id"]: x for x in (pf.get("selection") or {}).get("ranking") or []}
    prio = {sid: i + 1 for i, sid in enumerate(pf.get("priority") or [])}
    bt = {x["id"]: x for x in (json.loads(read("research/backtest-doubleproof.json", R) or "{}").get("results") or [])}
    vi = {}
    v = read("telemetry/vi.json", "origin/main")
    if v:
        try:
            vi = {x["id"]: x for x in json.loads(v).get("strategies") or []}
        except ValueError:
            pass
    out = []
    for r in rows:
        sid = r["id"]
        doc = read(f"research/strategies/{sid}.json", R)
        if not doc:
            log(f"  ! brak reguły {sid} — pomijam")
            continue
        rule = json.loads(doc)["rule"]
        rk, b, lv = rank.get(sid, {}), bt.get(sid, {}), vi.get(sid, {})
        sel = bool(rk.get("selected"))
        out.append({
            "id": sid, "desc": r.get("desc", ""), "group": r.get("group", ""), "direction": rule["direction"],
            "rule": rule, "sl": rule["exit"]["sl"], "tp": rule["exit"]["tp"], "max_bars": rule["exit"].get("max_bars"),
            "has_fc": bool(rule["exit"].get("fc")), "status": "bazowa", "basis_kind": "bazowa_wybrana" if sel else "bazowa",
            "selected": sel, "priority": prio.get(sid, 999), "est_pct": rk.get("shrunk_pct"),
            "dp": {"n": b.get("trades"), "avg": b.get("avg_ret_pct"), "pf": b.get("pf"), "hold": b.get("hold_median"),
                   "tp": b.get("tp_pct")},
            "search": {"pf_w": r.get("pf_w"), "n": r.get("trades")},
            "vi": {"n": lv.get("closed"), "avg": lv.get("avgPct"), "usd": lv.get("usd")} if lv else None,
        })
    out.sort(key=lambda x: (x["priority"], x["id"]))
    return {"builtAt": time.time(), "source": {"portfolio": pf.get("createdAt"), "vi": bool(vi)}, "strategies": out}


def mechanical(read=git_show) -> dict | None:
    """Mechaniczny inwestor (Apps Script): podsumowanie z telemetry/vi.json, a bez niego z state.json → vi."""
    for path, pick in (("telemetry/vi.json", lambda d: d.get("summary")), ("telemetry/state.json", lambda d: d.get("vi"))):
        txt = read(path, "origin/main")
        if not txt:
            continue
        try:
            s = pick(json.loads(txt)) or {}
        except ValueError:
            continue
        if s:
            return {"closed": s.get("closed"), "open": s.get("open"), "avgPct": s.get("avgPct"), "ci95Pct": s.get("ci95Pct"),
                    "usd": s.get("realizedUsd", s.get("sumUsd")), "source": path}
    return None


def load(refresh: bool = True, log=print) -> dict:
    """Playbook: świeży z gita (po fetch), a bez sieci — kopia z data/ai/playbook.json."""
    if refresh:
        fetch(log)
        try:
            pb = build(log=log)
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(pb, ensure_ascii=False), encoding="utf-8")
            return pb
        except Exception as e:
            log(f"  ! playbook z gita nieudany ({type(e).__name__}: {e}) — kopia lokalna")
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {"builtAt": None, "source": {}, "strategies": []}


# ===========================================================================
#  Sygnały
# ===========================================================================
class Signals:
    """Rynek akcji (ia4/lab/data.Market) z jednej kopii lokalnej — sygnały na ostatniej świecy i FC pozycji."""

    def __init__(self, frames: dict[str, pd.DataFrame], traded: list[str]):
        self.m = data.load_market(frames, traded, vault_bars=0)
        self.key = self.m.date * 10 + self.m.slot
        self._L: dict[str, dict] = {}

    def lines(self, s: dict) -> dict:
        if s["id"] not in self._L:
            self._L[s["id"]] = rules.lines_of(s["rule"], self.m)
        return self._L[s["id"]]

    def at(self, strategies: list[dict], key: int) -> list[dict]:
        """Sygnały na świecy `key` (tylko spółki, których ostatnia świeca to `key`)."""
        m = self.m
        last = m.seg_end - 1
        live = [(i, int(t)) for i, t in enumerate(last) if self.key[t] == key]
        out = []
        if not live:
            return out
        for s in strategies:
            L = self.lines(s)
            mask = rules.signal_mask(s["rule"], m, L) & rules.filter_mask(s["rule"], m, L)
            for i, t in live:
                if mask[t]:
                    out.append({"id": s["id"], "inst": m.symbols[i], "side": 1 if s["direction"] == "long" else -1,
                                "k": int(self.key[t]), "px": float(m.c[t]), "atrp": float(m.feat["atrp"][t])})
        return out

    def fc_key(self, s: dict, inst: str, decided_k: int) -> int | None:
        """Świeca (klucz), na której zamknięciu zachodzi FC pozycji z sygnału na świecy decided_k; None — jeszcze nie."""
        if not s.get("has_fc"):
            return None
        m = self.m
        try:
            i = m.symbols.index(inst)
        except ValueError:
            return None
        a, b = int(m.seg_start[i]), int(m.seg_end[i])
        j = int(np.searchsorted(self.key[a:b], decided_k)) + a
        if j + 1 >= b or self.key[j] != decided_k:            # świeca wejścia jeszcze nie istnieje
            return None
        f = rules.fc_bars(s["rule"], m, self.lines(s), np.array([j], dtype=np.int64))[0]
        return int(self.key[f]) if f >= 0 else None

    def atrp(self, inst: str) -> float | None:
        try:
            i = self.m.symbols.index(inst)
        except ValueError:
            return None
        v = self.m.feat["atrp"][int(self.m.seg_end[i]) - 1]
        return float(v) if np.isfinite(v) else None
