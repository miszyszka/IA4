"""
IA 4 — dyspozytor agentów AI Investor (instrukcja, sekcja 8). Od 1.41.
Wersja projektu: 1.57 (2026-10-21) — musi zgadzać się z IA4_INSTRUKCJA.md

Nadzorca (wątek główny) pilnuje feedu świec i sygnału życia; agenci pracują w osobnym wątku — ZAWSZE JEDEN
NARAZ (jeden model językowy, jeden laptop). Kolejność wyboru następnego zadania:
  1. Inwestor — runda po nowej świecy (na każdy rynek tylko najnowsza; starsza, nieruszona runda jest pomijana),
  2. odświeżenie playbooka i ai/config.json (co `playbook_refresh_hours`),
  3. Krytyk — gdy jest pora na przegląd (critic.due),
  4. Badacz — w każdym pozostałym czasie, z przerwą `idle_pause_sec` między cyklami.
Nowa świeca czeka najwyżej na koniec bieżącego zadania (jedno wywołanie modelu, 1–3 min). Każde zadanie to
wiersz w `agent_runs` (agent, zadanie, start, czas, czas modelu, wynik) — strona pokazuje, jak często i jak
długo pracują agenci. Co `work_flush_min` praca trafia na branch `ai` (runs, hipotezy, przeglądy).
"""

from __future__ import annotations

import threading
import time
import traceback

import pandas as pd

from . import config as aicfg
from .market import Prices


class RoundData:
    """Dane do rundy: kopia akcji z dysku, FX z pamięci pętli FX, prognoza FX."""

    def __init__(self, traded: list[str], context: list[str], live, model=None):
        self.traded, self.context, self.live, self.model = traded, context, live, model

    def frames(self) -> dict[str, pd.DataFrame]:
        from .. import sync
        out = {}
        for s in self.traded + self.context:
            p = sync.parquet_path(s)
            if not p.exists():
                continue
            for _ in range(3):
                try:
                    out[s] = pd.read_parquet(p)
                    break
                except Exception:                    # plik właśnie przepisywany przez feed
                    time.sleep(0.5)
        return out

    def get(self, need_signals: bool):
        from .playbook import Signals
        frames = self.frames()
        prices = Prices(stocks=frames, fx=dict(self.live.dfs) if self.live is not None else {})
        sig = None
        if need_signals and frames:
            sig = Signals(frames, self.traded)
        return prices, sig, self.forecast()

    def forecast(self) -> dict | None:
        if self.live is None or self.model is None:
            return None
        fc = (self.live.state or {}).get("fc")
        if not fc:
            return None
        from ..fx.scenario import verdict
        return {"instruments": fc.get("instruments") or [], "verdict": verdict(self.model.check or None)}


NAMES = {"investor": "Agent-Investor", "critic": "Krytyk", "researcher": "Badacz", "system": "dyspozytor"}


class AgentWorker:
    def __init__(self, investor, data: RoundData, store=None, on_change=None, log=print, clock=time.time, pb_loader=None,
                 mech_loader=None, critic=None, researcher=None):
        self.inv, self.data, self.store, self.on_change, self.log, self.clock = investor, data, store, on_change, log, clock
        self.pb_loader, self.mech_loader = pb_loader, mech_loader
        self.critic, self.researcher = critic, researcher
        self.jobs: dict[str, dict] = {}
        self.cv = threading.Condition()
        self.stop_flag = False
        self.busy = False
        self.current: dict | None = None
        self.thread = threading.Thread(target=self._loop, name="ia4-agents", daemon=True)
        self.next_refresh = clock() + 3600 * float(investor.cfg["playbook_refresh_hours"])
        self.research_after = clock() + 60                  # chwila na rozruch feedu przed pierwszym cyklem Badacza
        self.last_flush = clock()
        self.done = 0
        self.superseded: list[str] = []

    # ------------------------------------------------------------ sterowanie
    def start(self) -> None:
        self.thread.start()

    def stop(self, timeout: float = 30) -> None:
        with self.cv:
            self.stop_flag = True
            self.cv.notify_all()
        self.thread.join(timeout)
        self._flush(force=True)

    def submit(self, kind: str, key: int, label: str, close_t: float) -> None:
        with self.cv:
            old = self.jobs.get(kind)
            if old and old["key"] != key:
                self.superseded.append(f"runda {old['label']} pominięta — przyszła nowsza świeca {label} (rozliczy ją następna runda)")
            self.jobs[kind] = {"kind": kind, "key": key, "label": label, "close_t": close_t, "at": self.clock()}
            self.cv.notify_all()

    def pending(self) -> int:
        with self.cv:
            return len(self.jobs)

    # ------------------------------------------------------------ pętla
    def _next(self):
        with self.cv:
            if self.stop_flag:
                return ("stop", None)
            if self.jobs:
                job = min(self.jobs.values(), key=lambda j: j["close_t"])
                del self.jobs[job["kind"]]
                return ("investor", job)
        now = self.clock()
        if now >= self.next_refresh:
            return ("refresh", None)
        if self.critic is not None and self.critic.due():
            return ("critic", None)
        if self.researcher is not None and now >= self.research_after and self.researcher.ready():
            return ("research", None)
        return None

    def step(self) -> str | None:
        """Jedno zadanie (albo nic). Zwraca rodzaj zadania — używa go pętla i selftest."""
        try:
            task = self._next()
        except Exception as e:                                     # błąd w ocenie „czy pora” nie zatrzymuje pętli
            self.log(f"  ! dyspozytor: {type(e).__name__}: {e}")
            task = None
        if task is None:
            return None
        kind, job = task
        if kind == "stop":
            return "stop"
        with self.cv:
            sup, self.superseded = self.superseded, []
        for m in sup:
            self.inv.hub.event("round", m, agent="investor")
        if kind == "investor":
            self._run("investor", f"runda {job['label']}", lambda: self._round(job), urgent=True)
        elif kind == "refresh":
            self._run("system", "odświeżenie playbooka i ustawień", self.refresh)
        elif kind == "critic":
            self._run("critic", "przegląd", self.critic.review)
        elif kind == "research":
            self._run("researcher", "nowe hipotezy", self.researcher.cycle)
            self.research_after = self.clock() + float(self.inv.cfg["idle_pause_sec"])
        self._flush()
        return kind

    def _loop(self) -> None:
        while True:
            kind = self.step()
            if kind == "stop":
                return
            if kind is None:
                with self.cv:
                    if not self.jobs and not self.stop_flag:
                        self.cv.wait(timeout=10)

    def _run(self, agent: str, task: str, fn, urgent: bool = False) -> None:
        llm = self.inv.llm
        c0, s0 = getattr(llm, "calls", 0), getattr(llm, "sec_total", 0.0)
        t0 = self.clock()
        with self.cv:
            self.busy = True
            self.current = {"agent": agent, "task": task, "since": t0}
        if self.on_change:
            self.on_change(False)
        ok, summary = True, ""
        try:
            r = fn() or {}
            ok, summary = bool(r.get("ok", True)), str(r.get("summary") or "")
        except Exception as e:
            ok, summary = False, f"{type(e).__name__}: {e}"
            self.inv.hub.event("error", f"{NAMES.get(agent, agent)}: {summary}", agent=agent)
            self.log(f"  ! {NAMES.get(agent, agent)}: {summary}")
            self.log(traceback.format_exc())
            if agent == "investor":
                self.inv._set("czeka na świecę (po błędzie)")
        finally:
            t1 = self.clock()
            try:
                self.inv.hub.agent_run(agent, task, t0, t1, getattr(llm, "sec_total", 0.0) - s0, getattr(llm, "calls", 0) - c0,
                                       ok, summary)
            except Exception as e:
                self.log(f"  ! zapis pracy agenta: {e}")
            with self.cv:
                self.busy = False
                self.current = None
            if agent != "investor":
                self.log(f"  {time.strftime('%H:%M:%S')}  {NAMES.get(agent, agent)}: {task} ({t1 - t0:.0f} s) · {summary[:140]}")
            if self.on_change:
                self.on_change(urgent)

    def _round(self, job: dict) -> dict:
        inv = self.inv
        need_sig = job["kind"] == "stocks" or any(p.kind == "stock" and p.has_fc and p.fc_k is None
                                                  for b in (inv.main, inv.shadow) for p in b.active())
        prices, sig, fc = self.data.get(need_sig)
        t0 = time.time()
        rec = inv.run(job["kind"], job["key"], job["label"], job["close_t"], prices, sig, fc)
        self.done += 1
        n_in = sum(1 for d in rec["decisions"] + rec["ownIdeas"] if d["outcome"].startswith("wykonano"))
        line = (f"{rec['id']}: kandydatów {len(rec['candidates'])}, wejść {n_in}"
                f"{', model ' + str(round(rec['llm']['sec'])) + ' s' if rec.get('llm') else ''} · {rec['roundNote'][:120]}")
        self.log(f"  {time.strftime('%H:%M:%S')}  {job['label']} {line} ({time.time() - t0:.0f} s)")
        return {"ok": True, "summary": line}

    def refresh(self) -> dict:
        """Świeży playbook (branch research, vi.json) i ai/config.json."""
        self.next_refresh = self.clock() + 3600 * float(self.inv.cfg["playbook_refresh_hours"])
        if self.store is not None:
            self.store.pull()
            new = aicfg.load(self.store.config_path, self.log)
            for obj in (self.inv, self.critic, self.researcher):
                if obj is not None:
                    obj.cfg.update(new)
        n = 0
        if self.pb_loader:
            pb = self.pb_loader()
            n = len(pb.get("strategies", []))
            self.inv.set_playbook(pb, self.mech_loader() if self.mech_loader else self.inv.mech)
            self.inv.hub.event("playbook", f"playbook odświeżony: {n} strategii", agent="investor")
        return {"ok": True, "summary": f"playbook: {n} strategii"}

    def _flush(self, force: bool = False) -> None:
        now = self.clock()
        if self.store is None or (not force and now - self.last_flush < 60 * float(self.inv.cfg["work_flush_min"])):
            return
        self.last_flush = now
        try:
            self.store.save_work(self.inv.hub, self.inv)
        except Exception as e:
            self.inv.hub.event("error", f"branch ai (praca agentów): {type(e).__name__}: {e}", agent="system")

    # ------------------------------------------------------------ dla status.json
    def now_doing(self) -> dict | None:
        with self.cv:
            return dict(self.current) if self.current else None
