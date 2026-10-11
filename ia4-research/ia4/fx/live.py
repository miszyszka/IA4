"""
IA 4 — FX-real-time: prognoza rozkładu na żywo dla 11 instrumentów 1h (instrukcja, sekcje 4c.6, 4c.9, 4c.10).
Wersja projektu: 1.33 (2026-10-11) — musi zgadzać się z IA4_INSTRUKCJA.md

  python -m ia4.fx.live              # działa do Ctrl+C
  python -m ia4.fx.live --no-push    # bez GitHub (test: forecast.json tylko w fx-live-repo/)

Start: katalog, ratingi, profile i model na żywo z fx-repo/fx/ (ostatnie przeliczenie FX-research),
synchronizacja kopii lokalnej, prognoza z ostatniej świecy każdego instrumentu.
Pętla co 30 s:
  • gdy któremuś instrumentowi powinna już przybyć świeca (zamknięcie + 60 s; pary walutowe tylko
    w godzinach rynku, BTC co godzinę) — 1 odczyt system/fx1h; instrumenty z nowszą świecą — ich
    dokumenty dni; prognoza wszystkich instrumentów (ten sam kod co FX-research), publikacja;
    bez nowej świecy — ponowienie co 30 s, a po 15 min spóźnienia co 5 min,
  • co 2 min sygnał życia (aliveAt) — dashboard wie, że Mac jest połączony.
Publikacja: forecast.json na branchu `fx-live`, zawsze jeden commit (force push).
Ctrl+C: ostatnia publikacja z `stoppedAt` — dashboard pokaże „program zatrzymany”.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import catalog as cat
from . import instruments as fi

PL = ZoneInfo("Europe/Warsaw")
STEP = fi.STEP
H = 48
LOOP_SEC = 30
FIRST_CHECK_SEC = 60          # pierwsze pytanie o świecę: zamknięcie + 60 s (Fx.gs zapisuje ok. 20–180 s po zamknięciu)
LATE_SEC = 15 * 60            # po 15 min spóźnienia — pytanie co 5 min
LATE_EVERY_SEC = 300
ALIVE_EVERY_SEC = 120         # sygnał życia
SHOW = 48                     # świec wstecz na dashboardzie
TOP = 5                       # okoliczności o najwyższym ratingu wśród prawdziwych (na dashboard)


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fill_path(v: np.ndarray) -> np.ndarray:
    """Ścieżka scenariusza bez dziur: świeca uśredniona w historii (NaN) — interpolacja liniowa między sąsiadami."""
    v = np.asarray(v, dtype=np.float64)
    ok = np.isfinite(v)
    if ok.all() or not ok.any():
        return np.nan_to_num(v, nan=0.0)
    k = np.arange(v.size)
    return np.interp(k, np.r_[-1, k[ok]], np.r_[0.0, v[ok]])          # przed pierwszą znaną — od ceny teraz


def clean(x):
    """JSON bez NaN i nieskończoności (przeglądarka nie odczyta takiego pliku) — zamiana na null."""
    if isinstance(x, float):
        return x if np.isfinite(x) else None
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating,)):
        return clean(float(x))
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def last_closed(group: str, now: float) -> int:
    """Początek najnowszej świecy rynku zamkniętej przed chwilą now."""
    grid = int(now) // STEP * STEP - STEP * np.arange(1, 24 * 4)
    return int(grid[fi.market_open(group, grid)][0])


# ===========================================================================
#  Model: katalog + ostatnie przeliczenie FX-research
# ===========================================================================
class Model:
    def __init__(self, repo_root: Path):
        self.root = repo_root
        self.path = repo_root / "fx" / "ratings.json"
        self.mtime = None
        self.load()

    def load(self):
        cond = cat.load_conditions(self.root)
        if not cond or not self.path.exists():
            raise SystemExit(f"Brak fx/conditions.json ({cat.CATALOG}) albo fx/ratings.json w fx-repo — najpierw "
                             "python -m ia4.fx.catalog --commit i python -m ia4.fx.research")
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        rows = doc["conditions"]
        if doc.get("catalog") != cat.CATALOG or [r["id"] for r in rows] != [c["id"] for c in cond["conditions"]]:
            raise SystemExit("fx/ratings.json nie pasuje do fx/conditions.json — uruchom python -m ia4.fx.research")
        sc_ = doc.get("scenario") or {}
        if not sc_.get("model"):
            raise SystemExit("fx/ratings.json bez sprawdzianu rozkładu — uruchom python -m ia4.fx.research")
        self.conds = cond["conditions"]
        self.ratings = np.array([r["rating"] for r in rows], dtype=np.float64)
        self.profiles = np.array([[np.nan if v is None else v for v in r["profile"]] for r in rows], dtype=np.float64)
        self.run, self.run_at = doc["run"], doc["at"]
        self.model = sc_["model"]
        self.check = ((sc_.get("methods") or {}).get(self.model["method"]) or {}).get("B") or {}
        self.mtime = self.path.stat().st_mtime

    def reload_if_changed(self) -> bool:
        try:
            if self.path.stat().st_mtime != self.mtime:
                self.load()
                return True
        except (OSError, SystemExit) as e:
            print(f"  ! nowe ratingi nieczytelne ({e}) — zostaję przy {self.run}")
        return False


# ===========================================================================
#  Prognoza wszystkich instrumentów
# ===========================================================================
def compute(dfs: dict, model: Model, now: float | None = None) -> dict:
    """Prognoza rozkładu na ostatniej świecy każdego instrumentu (4c.6) — ten sam kod co FX-research."""
    from . import scenario as sc
    from .research import Pool, forecast_from
    now = time.time() if now is None else now
    P = Pool(dfs, model.conds)
    eng = sc.Engine(P, model.ratings)
    mdl = model.model
    inst_chk = (model.check or {}).get("inst") or {}
    out = []
    for j, sym in enumerate(P.syms):
        t = int(P.last[j])
        info = fi.INFO.get(sym, {"pip": 1.0, "digits": 6, "group": P.groups[j]})
        u, c0 = float(P.U100[t]), float(P.c[t])
        times = fi.next_slots(P.groups[j], int(P.time[t]), H)
        price = lambda v: [round(c0 + u * float(x), info["digits"]) for x in v]
        df = dfs[sym]
        e = {"id": sym, "name": fi.NAMES.get(sym, sym), "group": P.groups[j], "pip": info["pip"], "digits": info["digits"],
             "lastCandle": iso(P.time[t]), "lastClose": c0, "atr100": round(u, info["digits"] + 2),
             "marketOpen": bool(fi.market_open(P.groups[j], int(now) // STEP * STEP)[0]),
             "candles": [[int(r.time), r.o, r.h, r.l, r.c] for r in df.iloc[-SHOW:].itertuples()],
             "times": times, "check": inst_chk.get(sym)}
        a = eng.select(t, int(P.time[t]) + 1, mdl["method"])
        if a.size >= 10:
            paths = eng.paths(t, a)
            center = sc.center_of(mdl, paths, forecast_from(P.M[:, t], model.ratings, model.profiles))
            d = sc.distribution(paths, center, mdl["f"])
            e.update({
                "K": int(a.size), "center": price(d["center"]), **{f"q{q}": price(d["q"][q]) for q in d["q"]},
                "pUp": {str(k): round(float(d["pUp"][k - 1]), 3) for k in (12, 48)},
                "upCount": {str(k): [int((d["X"][:, k - 1] > 0).sum()), int(a.size)] for k in (12, 48)},
                "range": {"high": round(c0 + u * d["high"], info["digits"]), "low": round(c0 + u * d["low"], info["digits"]),
                          "size": round(u * d["range"], info["digits"])},
                "scenarios": [{"name": nm, "from": iso(int(P.time[i])), "source": P.syms[int(P.inst[i])],
                               "path": price(fill_path(path))} for nm, i, path in sc.scenarios(d["X"], a)],
                "forecastPips": {str(k): round(u * float(d["center"][k - 1]) / info["pip"], 1) for k in (12, 48)},
            })
        else:
            e.update({"K": int(a.size), "scenarios": [], "forecastPips": {"12": None, "48": None}})
        idx = np.flatnonzero(P.M[:, t])
        top = sorted(idx, key=lambda i: (-model.ratings[i], model.conds[i]["id"]))[:TOP]
        e.update({"active": int(idx.size), "activeRatingSum": int(model.ratings[idx].sum()),
                  "activeTop": [{"id": model.conds[i]["id"], "rating": int(model.ratings[i]), "desc": model.conds[i]["desc"]}
                                for i in top]})
        out.append(e)
    return {"instruments": out}


def document(state: dict, model: Model, now: float, stopped: bool = False) -> dict:
    from .. import __version__
    from .scenario import verdict
    ch = model.check or {}
    doc = {"version": __version__, "interval": "1h", "horizon": H, "aliveAt": iso(now), "generatedAt": state.get("generatedAt"),
           "ratings": {"run": model.run, "at": model.run_at},
           "model": {k: model.model.get(k) for k in ("method", "f", "lambda", "center", "K", "hourWindow", "spacingHours")},
           "check": {k: ch.get(k) for k in ("n", "cov80_12", "cov80_48", "cov50_48", "brier12", "brier48",
                                             "rangeErr", "pinball48", "centerS")},
           "verdict": verdict(ch or None),
           "firestoreReadsToday": state.get("reads", 0)}
    doc.update(state.get("fc") or {})
    if stopped:
        doc["stoppedAt"] = iso(now)
    return doc


# ===========================================================================
#  Firestore — tylko to, co konieczne
# ===========================================================================
class Source:
    """Odczyty Firestore na żywo: system/fx1h i dokumenty dni. Liczy odczyty."""

    def __init__(self):
        self.reads = 0
        self.day = None
        self.updated = None          # updatedAt dokumentu system/fx1h (s) — opóźnienie Firestore → Mac (11c.4)

    def _count(self, n=1):
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self.day:
            self.day, self.reads = today, 0
        self.reads += n

    def status(self) -> dict:
        """{SYMBOL: początek ostatniej zapisanej świecy (s)} z system/fx1h."""
        from .. import config
        d = config.client().document("system/fx1h").get()
        self._count()
        if not d.exists:
            return {}
        out = {}
        u = d.to_dict().get("updatedAt")
        self.updated = int(u.timestamp()) if hasattr(u, "timestamp") else None
        for s, v in (d.to_dict().get("last") or {}).items():
            out[s] = int(v.timestamp()) if hasattr(v, "timestamp") else int(datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp())
        return out

    def days(self, sym: str, dates: list[str]) -> dict:
        from .. import config
        from .sync import doc_to_frame
        out = {}
        for date in dates:
            d = config.client().document(f"fx1h/{sym}/days/{date}").get()
            self._count()
            if d.exists:
                out[date] = doc_to_frame(d.to_dict())
        return out


def days_between(t0: int, t1: int) -> list[str]:
    d0 = datetime.fromtimestamp(t0, timezone.utc).date()
    d1 = datetime.fromtimestamp(t1, timezone.utc).date()
    return [d.isoformat() for d in pd.date_range(d0, d1, freq="D").date]


# ===========================================================================
#  Branch fx-live — jeden commit, force push
# ===========================================================================
def _git(cwd: Path, *args, check=False):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


class LiveRepo:
    """Branch „na żywo”: zawsze jeden commit z jednym plikiem (force push). Ten sam mechanizm dla
    `fx-live/forecast.json` i `ai-live/status.json` (11c.11)."""
    BRANCH = "fx-live"
    FILE = "forecast.json"

    def __init__(self, root: Path, push: bool = True):
        self.root, self.push = root, push
        self.n = 0
        self.last_error = ""

    def ensure(self, origin: str | None):
        if not (self.root / ".git").exists():
            self.root.mkdir(parents=True, exist_ok=True)
            _git(self.root, "init", "-q")
            if origin:
                _git(self.root, "remote", "add", "origin", origin)

    def publish(self, doc: dict) -> bool:
        (self.root / self.FILE).write_text(json.dumps(clean(doc), ensure_ascii=False, separators=(",", ":"),
                                                            allow_nan=False), encoding="utf-8")
        ident = []
        if not _git(self.root, "config", "user.email").stdout.strip():
            ident = ["-c", "user.name=IA4 fx-live", "-c", "user.email=ia4-lab@users.noreply.github.com"]
        _git(self.root, "checkout", "-q", "--orphan", "_next")
        _git(self.root, "add", "-A")
        r = _git(self.root, *ident, "commit", "-q", "-m", f"{self.BRANCH}: {doc.get('aliveAt')}")
        if r.returncode != 0:
            self.last_error = (r.stderr or r.stdout).strip()[:200]
            return False
        _git(self.root, "branch", "-q", "-D", self.BRANCH)
        _git(self.root, "branch", "-q", "-m", self.BRANCH)
        self.n += 1
        if self.n % 100 == 0:                        # stare commity nie są potrzebne
            _git(self.root, "reflog", "expire", "--expire=now", "--all")
            _git(self.root, "gc", "-q", "--prune=now")
        if not self.push:
            return True
        r = _git(self.root, "push", "-q", "-f", "origin", self.BRANCH)
        self.last_error = "" if r.returncode == 0 else r.stderr.strip()[:200]
        return r.returncode == 0


# ===========================================================================
#  Pętla
# ===========================================================================
class Live:
    def __init__(self, dfs: dict, model: Model, source, out: LiveRepo, clock=time.time, log=print):
        self.dfs, self.model, self.src, self.out, self.clock, self.log = dfs, model, source, out, clock, log
        self.state = {"reads": 0}
        self.last = {s: int(d["time"].iloc[-1]) for s, d in dfs.items()}
        self.next_check = 0.0
        self.last_alive = 0.0

    def recompute(self, now):
        self.state["fc"] = compute(self.dfs, self.model, now)
        self.state["generatedAt"] = iso(now)

    def publish(self, now, stopped=False):
        self.state["reads"] = self.src.reads
        ok = self.out.publish(document(self.state, self.model, now, stopped))
        self.last_alive = now
        if not ok:
            self.log(f"  ! publikacja nieudana: {self.out.last_error}")
        return ok

    def waiting(self, now) -> dict:
        """{SYMBOL: świeca, na którą czekamy} — tylko te, które powinny już być w Firestore."""
        out = {}
        for s, t_last in self.last.items():
            cur = last_closed(fi.group_of(s), now - FIRST_CHECK_SEC)
            if cur > t_last:
                out[s] = cur
        return out

    def step(self) -> bool:
        """Jeden obrót pętli. Zwraca True, gdy przyszła nowa świeca."""
        from .sync import merge_days
        now = self.clock()
        new = False
        wait = self.waiting(now)
        if wait and now >= self.next_check:
            st = self.src.status()
            fresh = [s for s in self.last if st.get(s, 0) > self.last[s]]
            for s in fresh:
                got = self.src.days(s, days_between(self.last[s], st[s]))
                self.dfs[s] = merge_days(self.dfs[s], got)
                self.last[s] = int(self.dfs[s]["time"].iloc[-1])
            if fresh:
                if self.model.reload_if_changed():
                    self.log(f"  nowe ratingi: {self.model.run}")
                t = time.time()
                self.recompute(now)
                self.publish(now)
                self.log(f"  {datetime.fromtimestamp(now, PL):%H:%M:%S}  nowe świece: {', '.join(fresh)} · "
                         f"przeliczenie {time.time() - t:.0f} s · odczytów Firestore dziś {self.src.reads}")
                new = True
            still = self.waiting(now)
            if still:
                late = now - min(still.values()) - STEP
                self.next_check = now + (LATE_EVERY_SEC if late > LATE_SEC else LOOP_SEC) - 1
            else:
                self.next_check = 0.0
        if not new and now - self.last_alive >= ALIVE_EVERY_SEC:
            self.publish(now)
        return new


def main() -> None:
    from .store import fx_repo
    from .sync import load_all, sync

    ap = argparse.ArgumentParser(description="FX-real-time — prognoza FX 1h na żywo (4c.9)")
    ap.add_argument("--no-push", action="store_true", help="bez GitHub")
    ap.add_argument("--no-sync", action="store_true", help="bez synchronizacji przy starcie")
    a = ap.parse_args()
    from .. import __version__
    from ..ai.lock import guard
    guard("python -m ia4.fx.live")           # przy działającym `ia4 start` prognoza FX liczy się w nim (11c.3)
    print(f"IA 4 — FX-real-time 1h (wersja {__version__})\n")
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["caffeinate", "-dims", "-w", str(os.getpid())])
            print("caffeinate: Mac nie zaśnie, dopóki program działa.")
        except OSError:
            print("  ! caffeinate niedostępny — Mac może zasnąć.")
    repo = fx_repo(push=not a.no_push)
    repo.ensure()
    model = Model(repo.root)
    dfs = load_all() if a.no_sync else sync()
    out = LiveRepo(repo.root.parent / "fx-live-repo", push=not a.no_push)
    out.ensure(repo._origin() if not a.no_push else None)
    live = Live(dfs, model, Source(), out)
    now = time.time()
    t = time.time()
    live.recompute(now)
    live.publish(now)
    print(f"  ratingi {model.run} ({model.run_at}), model {model.model['method']} (×{model.model['f']}, "
          f"λ {model.model['lambda']}), {len(dfs)} instrumentów, przeliczenie {time.time() - t:.0f} s")
    for e in live.state["fc"]["instruments"]:
        unit = "pips" if e["group"] == "fx" else "USD"
        rg = (e.get("range") or {}).get("size")
        print(f"    {e['id']:7s} świeca {e['lastCandle'][:16]} · zakres 48 h {rg / e['pip'] if rg else 0:.0f} {unit} · "
              f"P(wzrost) {(e.get('pUp') or {}).get('48')}")
    print(f"  strona: https://miszyszka.github.io/IA4/#fx  (Ctrl+C kończy)\n")
    try:
        while True:
            try:
                live.step()
            except Exception as e:                 # sieć, Firestore — próbujemy dalej
                print(f"  ! {type(e).__name__}: {e}")
            time.sleep(LOOP_SEC)
    except KeyboardInterrupt:
        print("\n  zatrzymano — dashboard dostaje informację „program zatrzymany”")
        live.publish(time.time(), stopped=True)


if __name__ == "__main__":
    main()
