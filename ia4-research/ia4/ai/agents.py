"""
IA 4 — wątek agentów AI Investor (instrukcja, sekcje 11c.3, 11c.6).
Wersja projektu: 1.39 (2026-10-14) — musi zgadzać się z IA4_INSTRUKCJA.md

Nadzorca (wątek główny) pilnuje feedu świec i sygnału życia; agenci liczą w osobnym wątku, żeby
myślenie modelu (1–2 min) nie wstrzymywało feedu. Kolejka rund: na każdy rynek tylko najnowsza
świeca — runda, która zdążyła się zestarzeć (przyszła nowsza świeca tego rynku), jest pomijana
(rozliczy ją następna runda). Co `playbook_refresh_hours` — świeży playbook i ai/config.json.
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


class AgentWorker:
    def __init__(self, investor, data: RoundData, store=None, on_change=None, log=print, clock=time.time, pb_loader=None,
                 mech_loader=None):
        self.inv, self.data, self.store, self.on_change, self.log, self.clock = investor, data, store, on_change, log, clock
        self.pb_loader, self.mech_loader = pb_loader, mech_loader
        self.jobs: dict[str, dict] = {}
        self.cv = threading.Condition()
        self.stop_flag = False
        self.busy = False
        self.thread = threading.Thread(target=self._loop, name="ia4-agents", daemon=True)
        self.next_refresh = clock() + 3600 * float(investor.cfg["playbook_refresh_hours"])
        self.done = 0
        self.superseded: list[str] = []

    def start(self) -> None:
        self.thread.start()

    def stop(self, timeout: float = 30) -> None:
        with self.cv:
            self.stop_flag = True
            self.cv.notify_all()
        self.thread.join(timeout)

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

    def _loop(self) -> None:
        while True:
            with self.cv:
                while not self.jobs and not self.stop_flag and self.clock() < self.next_refresh:
                    self.cv.wait(timeout=30)
                if self.stop_flag:
                    return
                job = min(self.jobs.values(), key=lambda j: j["close_t"]) if self.jobs else None
                if job:
                    del self.jobs[job["kind"]]
                sup, self.superseded = self.superseded, []
                self.busy = True
            for m in sup:
                self.inv.hub.event("round", m, agent="investor")
            try:
                if job:
                    self._round(job)
                elif self.clock() >= self.next_refresh:
                    self.refresh()
            except Exception as e:
                self.inv.hub.event("error", f"agent: {type(e).__name__}: {e}", agent="investor")
                self.log(f"  ! agent: {type(e).__name__}: {e}")
                self.log(traceback.format_exc())
                self.inv._set("czeka na świecę (po błędzie)")
            finally:
                self.busy = False
                if self.on_change:
                    self.on_change()

    def _round(self, job: dict) -> None:
        inv = self.inv
        need_sig = job["kind"] == "stocks" or any(p.kind == "stock" and p.has_fc and p.fc_k is None
                                                  for b in (inv.main, inv.shadow) for p in b.active())
        prices, sig, fc = self.data.get(need_sig)
        t0 = time.time()
        rec = inv.run(job["kind"], job["key"], job["label"], job["close_t"], prices, sig, fc)
        self.done += 1
        n_in = sum(1 for d in rec["decisions"] + rec["ownIdeas"] if d["outcome"].startswith("wykonano"))
        self.log(f"  {time.strftime('%H:%M:%S')}  {rec['id']} {job['label']}: kandydatów {len(rec['candidates'])}, wejść {n_in}"
                 f"{', model ' + str(round(rec['llm']['sec'])) + ' s' if rec.get('llm') else ''} ({time.time() - t0:.0f} s) · "
                 f"{rec['roundNote'][:120]}")

    def refresh(self) -> None:
        """Świeży playbook (branch research, vi.json) i ai/config.json."""
        self.next_refresh = self.clock() + 3600 * float(self.inv.cfg["playbook_refresh_hours"])
        if self.store is not None:
            self.store.pull()
            self.inv.cfg.update(aicfg.load(self.store.config_path, self.log))
        if self.pb_loader:
            pb = self.pb_loader()
            self.inv.set_playbook(pb, self.mech_loader() if self.mech_loader else self.inv.mech)
            self.inv.hub.event("playbook", f"playbook odświeżony: {len(pb.get('strategies', []))} strategii", agent="investor")
