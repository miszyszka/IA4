"""
IA 4 — FX-real-time: prognoza EURUSD na żywo (instrukcja, sekcje 4c.6, 4c.9, 4c.10).
Wersja projektu: 1.26 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

  python -m ia4.fx.live              # działa do Ctrl+C
  python -m ia4.fx.live --no-push    # bez GitHub (test: forecast.json tylko w fx-live-repo/)

Start: synchronizacja kopii lokalnej, ratingi i profile z fx-repo/fx/ratings.json (ostatnie
przeliczenie FX-research), dashboard na branch `fx`, prognoza z ostatniej świecy.
Pętla co 30 s:
  • poza godzinami rynku — zero odczytów Firestore,
  • gdy powinna już być w Firestore nowa świeca (zamknięcie + 30 s) — 1 odczyt podsumowania
    fx/EURUSD; jeśli jest nowsza świeca — dokument(y) dnia, prognoza, publikacja;
    jeśli nie ma — ponowienie co 30 s, a po 3 min spóźnienia co 2 min,
  • co 2 min sygnał życia (aliveAt) — dashboard wie, że Mac jest połączony.
Publikacja: forecast.json na branchu `fx-live`, zawsze jeden commit (force push).
Ctrl+C: ostatnia publikacja z `stoppedAt` — dashboard pokaże „program zatrzymany”.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import catalog as cat
from . import series as sr
from .research import H

NY = ZoneInfo("America/New_York")
PL = ZoneInfo("Europe/Warsaw")
STEP = 300
LOOP_SEC = 30
FIRST_CHECK_SEC = 30          # pierwsze pytanie o świecę: zamknięcie + 30 s (zapis w Firestore zwykle po ~21 s)
LATE_SEC = 180                # po 3 min spóźnienia — pytanie co 2 min
LATE_EVERY_SEC = 120
ALIVE_EVERY_SEC = 120         # sygnał życia
SHOW = 48                     # świec wstecz na dashboardzie
TOP = 5                       # okoliczności o najwyższym ratingu wśród prawdziwych (na dashboard)
DEFAULT_MODEL = {"method": "pora", "f": 1.15, "lambda": 0.0}   # tylko gdy ratings.json nie ma jeszcze sprawdzianu 1.26
DASHBOARD = Path(__file__).resolve().parent / "dashboard" / "index.html"


# ===========================================================================
#  Godziny rynku (te same co Fx.gs, sekcja 4b): niedziela 17:00 – piątek 17:00 Nowy Jork
# ===========================================================================
def candle_in_market(t: int) -> bool:
    """Czy świeca o początku t (sekundy UTC) wypada w godzinach rynku."""
    d = datetime.fromtimestamp(t, timezone.utc).astimezone(NY)
    wd, m = d.isoweekday(), d.hour * 60 + d.minute
    if wd == 6:
        return False
    if wd == 7:
        return m >= 17 * 60
    if wd == 5:
        return m < 17 * 60
    return True


def next_candle(t: int) -> int:
    """Początek najbliższej świecy po t, która wypada w godzinach rynku."""
    n = t + STEP
    for _ in range(2 * 24 * 12 + 10):         # najwyżej przez weekend
        if candle_in_market(n):
            return n
        n += STEP
    return n


def market_open_now(now: float) -> bool:
    return candle_in_market(int(now) // STEP * STEP)


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
            raise SystemExit("Brak fx/conditions.json albo fx/ratings.json w fx-repo — najpierw "
                             "python -m ia4.fx.catalog --commit i python -m ia4.fx.research")
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        rows = doc["conditions"]
        if [r["id"] for r in rows] != [c["id"] for c in cond["conditions"]]:
            raise SystemExit("fx/ratings.json nie pasuje do fx/conditions.json — uruchom python -m ia4.fx.research")
        self.conds = cond["conditions"]
        self.ratings = np.array([r["rating"] for r in rows], dtype=np.float64)
        self.profiles = np.array([[np.nan if v is None else v for v in r["profile"]] for r in rows], dtype=np.float64)
        self.run, self.run_at = doc["run"], doc["at"]
        sc_ = doc.get("scenario") or {}
        self.model = sc_.get("model") or dict(DEFAULT_MODEL)     # przeliczenie sprzed 1.26 — ustawienia domyślne
        self.default = not sc_.get("model")
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
#  Prognoza i dokument forecast.json
# ===========================================================================
def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute(df: pd.DataFrame, model: Model) -> dict:
    """Prognoza rozkładu na ostatniej świecy (4c.6) — ten sam silnik co sprawdzian w FX-research."""
    from . import scenario as sc
    from .research import forecast_from, future_changes, occurrence_ok
    from ..lab import indicators as ind
    Sp, Sm = sr.pair_of(df)
    M = cat.evaluate(model.conds, Sp, Sm)
    R = future_changes(Sp.c, Sp.filled)
    ok = occurrence_ok(Sp.time, Sp.filled)
    eng = sc.Engine(Sp.time, R, ok, M, model.ratings, Sp.U, ind.atr(Sp.h, Sp.l, Sp.c, 12))
    T = Sp.n
    t_last, c_last = int(Sp.time[-1]), float(Sp.c[-1])
    mdl = model.model
    a = eng.select(T - 1, T, mdl["method"])
    times = []
    for k in range(1, H + 1):                   # prognoza kończy się na zamknięciu rynku (piątek 17:00 NY)
        t = t_last + k * STEP
        if not candle_in_market(t):
            break
        times.append(t)
    n = len(times)
    price = lambda pips: [round(c_last + sr.PIP * float(v), 6) for v in pips[:n]]
    out = {"lastCandle": iso(t_last), "lastClose": c_last,
           "candles": [[int(r.time), r.o, r.h, r.l, r.c] for r in df.iloc[-SHOW:].itertuples()],
           "times": times, "model": {**mdl, "K": int(a.size), "default": model.default}}
    if a.size >= 10:
        P = eng.paths(T - 1, a)
        center = mdl["lambda"] * np.nan_to_num(forecast_from(M[:, -1], model.ratings, model.profiles), nan=0.0)
        d = sc.distribution(P, center, mdl["f"])
        out.update({
            "center": price(d["center"]), **{f"q{q}": price(d["q"][q]) for q in d["q"]},
            "pUp": {str(k): round(float(d["pUp"][k - 1]), 3) for k in (12, 48) if k <= n},
            "upCount": {str(k): [int((d["X"][:, k - 1] > 0).sum()), int(P.shape[0])] for k in (12, 48) if k <= n},
            "range": {"high": round(c_last + sr.PIP * d["high"], 6), "low": round(c_last + sr.PIP * d["low"], 6),
                      "pips": round(d["range"], 1)},
            "scenarios": [{"name": nm, "from": iso(int(Sp.time[i])), "path": price(path)}
                          for nm, i, path in sc.scenarios(d["X"], a)],
            "forecast": [[t, p] for t, p in zip(times, price(d["center"]))],
            "forecastPips": {str(k): (round(float(d["center"][k - 1]), 2) if k <= n else None) for k in (12, 48)},
        })
    else:
        out.update({"forecast": [], "forecastPips": {"12": None, "48": None}, "scenarios": []})
    active = M[:, -1]
    idx = np.flatnonzero(active)
    top = sorted(idx, key=lambda i: (-model.ratings[i], model.conds[i]["id"]))[:TOP]
    out.update({"active": int(idx.size), "activeRatingSum": int(model.ratings[idx].sum()),
                "activeTop": [{"id": model.conds[i]["id"], "rating": int(model.ratings[i]), "desc": model.conds[i]["desc"]}
                              for i in top]})
    return out


def document(state: dict, model: Model, now: float, stopped: bool = False) -> dict:
    from .. import __version__
    from .scenario import verdict
    ch = model.check or {}
    doc = {"version": __version__, "aliveAt": iso(now), "generatedAt": state.get("generatedAt"),
           "marketOpen": market_open_now(now),
           "ratings": {"run": model.run, "at": model.run_at},
           "check": {k: ch.get(k) for k in ("n", "cov80_12", "cov80_48", "cov50_48", "brier12", "brier48",
                                             "rangeErr", "pinball48")},
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
    """Odczyty Firestore na żywo: podsumowanie fx/EURUSD i dokumenty dni. Liczy odczyty."""

    def __init__(self):
        self.reads = 0
        self.day = None

    def _count(self, n=1):
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self.day:
            self.day, self.reads = today, 0
        self.reads += n

    def last_time(self) -> int | None:
        from .. import config
        d = config.client().document("fx/EURUSD").get()
        self._count()
        if not d.exists:
            return None
        x = d.to_dict()
        if not x.get("lastDate") or not x.get("lastTime"):
            return None
        return int(datetime.fromisoformat(f"{x['lastDate']}T{x['lastTime']}:00+00:00").timestamp())

    def days(self, dates: list[str]) -> dict:
        from .. import config
        from .sync import doc_to_frame
        out = {}
        for date in dates:
            d = config.client().document(f"fx/EURUSD/days/{date}").get()
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
    BRANCH = "fx-live"

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
        (self.root / "forecast.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")),
                                                 encoding="utf-8")
        ident = []
        if not _git(self.root, "config", "user.email").stdout.strip():
            ident = ["-c", "user.name=IA4 fx-live", "-c", "user.email=ia4-lab@users.noreply.github.com"]
        _git(self.root, "checkout", "-q", "--orphan", "_next")
        _git(self.root, "add", "-A")
        r = _git(self.root, *ident, "commit", "-q", "-m", f"fx-live: {doc.get('aliveAt')}")
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


def publish_dashboard(repo) -> bool:
    """Kopia dashboardu (ia4/fx/dashboard/index.html) w korzeniu brancha `fx` — GitHub Pages (4c.10)."""
    dst = repo.root / "index.html"
    if dst.exists() and dst.read_bytes() == DASHBOARD.read_bytes() and (repo.root / ".nojekyll").exists():
        return False
    shutil.copyfile(DASHBOARD, dst)
    (repo.root / ".nojekyll").write_text("", encoding="utf-8")
    return repo.commit_push("fx: dashboard (index.html)")


# ===========================================================================
#  Pętla
# ===========================================================================
class Live:
    def __init__(self, df: pd.DataFrame, model: Model, source, out: LiveRepo, clock=time.time, log=print):
        self.df, self.model, self.src, self.out, self.clock, self.log = df, model, source, out, clock, log
        self.state = {"reads": 0}
        self.last_t = int(df["time"].iloc[-1])
        self.next_check = 0.0
        self.last_alive = 0.0

    def recompute(self, now):
        self.state["fc"] = compute(self.df, self.model)
        self.state["generatedAt"] = iso(now)

    def publish(self, now, stopped=False):
        self.state["reads"] = self.src.reads
        ok = self.out.publish(document(self.state, self.model, now, stopped))
        self.last_alive = now
        if not ok:
            self.log(f"  ! publikacja nieudana: {self.out.last_error}")
        return ok

    def due(self) -> float:
        """Kiedy pytać Firestore o następną świecę."""
        return next_candle(self.last_t) + STEP + FIRST_CHECK_SEC

    def step(self) -> bool:
        """Jeden obrót pętli. Zwraca True, gdy przyszła nowa świeca."""
        now = self.clock()
        new = False
        due = self.due()
        if now >= due and now >= self.next_check:
            t = self.src.last_time()
            if t is not None and t > self.last_t:
                fresh = self.src.days(days_between(self.last_t, t))
                from .sync import merge_days
                self.df = merge_days(self.df, fresh)
                self.last_t = int(self.df["time"].iloc[-1])
                if self.model.reload_if_changed():
                    self.log(f"  nowe ratingi: {self.model.run}")
                self.recompute(now)
                self.publish(now)
                fc = self.state["fc"]
                rg = (fc.get("range") or {}).get("pips")
                self.log(f"  {datetime.fromtimestamp(now, PL):%H:%M:%S}  świeca "
                         f"{datetime.fromtimestamp(self.last_t, timezone.utc):%H:%M} UTC · "
                         f"okoliczności {fc['active']} · zakres 4 h {rg} pips · P(wzrost) {fc.get('pUp')} · "
                         f"odczytów Firestore dziś {self.src.reads}")
                new = True
                self.next_check = 0.0
            else:
                late = now - (due - FIRST_CHECK_SEC)
                self.next_check = now + (LATE_EVERY_SEC if late > LATE_SEC else LOOP_SEC) - 1
        if not new and now - self.last_alive >= ALIVE_EVERY_SEC:
            self.publish(now)
        return new


def main() -> None:
    from .store import fx_repo
    from .sync import sync

    ap = argparse.ArgumentParser(description="FX-real-time — prognoza EURUSD na żywo (4c.9)")
    ap.add_argument("--no-push", action="store_true", help="bez GitHub")
    ap.add_argument("--no-sync", action="store_true", help="bez synchronizacji przy starcie")
    a = ap.parse_args()
    from .. import __version__
    print(f"IA 4 — FX-real-time (wersja {__version__})\n")
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["caffeinate", "-dims", "-w", str(os.getpid())])
            print("caffeinate: Mac nie zaśnie, dopóki program działa.")
        except OSError:
            print("  ! caffeinate niedostępny — Mac może zasnąć.")
    repo = fx_repo(push=not a.no_push)
    repo.ensure()
    model = Model(repo.root)
    if publish_dashboard(repo):
        print("  dashboard zaktualizowany na branchu fx")
    from .sync import load
    df = load() if a.no_sync else sync()
    out = LiveRepo(repo.root.parent / "fx-live-repo", push=not a.no_push)
    out.ensure(repo._origin() if not a.no_push else None)
    live = Live(df, model, Source(), out)
    now = time.time()
    live.recompute(now)
    live.publish(now)
    fc = live.state["fc"]
    if model.default:
        print("  ! ratings.json bez sprawdzianu rozkładu (sprzed 1.26) — model domyślny; uruchom python -m ia4.fx.research")
    print(f"  ratingi {model.run} ({model.run_at}), model {model.model['method']} (×{model.model['f']}, "
          f"λ {model.model['lambda']}), ostatnia świeca {fc['lastCandle']}, okoliczności {fc['active']}, "
          f"zakres 4 h {(fc.get('range') or {}).get('pips')} pips")
    print(f"  dashboard: https://miszyszka.github.io/IA4/  (Ctrl+C kończy)\n")
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
