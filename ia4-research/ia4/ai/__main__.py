"""
IA 4 — nadzorca AI Investor: `ia4 start` (instrukcja, sekcja 8).
Wersja projektu: 1.50 (2026-10-20) — musi zgadzać się z IA4_INSTRUKCJA.md

  python -m ia4.ai                    # to samo co `ia4 start` i dwuklik IA4-start.command; Ctrl+C kończy
  python -m ia4.ai --no-push          # bez GitHub (test)
  python -m ia4.ai --no-sync          # bez synchronizacji przy starcie (praca na kopii lokalnej)
  python -m ia4.ai --no-llm-check     # bez sprawdzania Ollamy (Inwestor bez modelu = „brak decyzji”)

Start: Ollama i model → caffeinate i blokada → synchronizacja akcji i FX → playbook i Agent-Investor
(rozliczenie przerwy) → dyspozytor agentów (Inwestor, Krytyk, Badacz — jeden naraz, bez przerwy) → praca.
Pętla co 5 s: feed akcji (system/status → szybka synchronizacja), feed FX i prognoza FX (kod ia4.fx.live),
zapis do huba, sygnał życia ai-live/status.json. Nowa świeca akcji / godzina FX → runda Inwestora
w wątku agentów (agents.py). W terminalu co minutę jedna linia stanu i jedna linia na każde zadanie agenta.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import STEP, feed, lock, nyse, ollama, status
from .hub import Hub

PL = ZoneInfo("Europe/Warsaw")
LOOP_SEC = 5
ALIVE_SEC = 300               # sygnał życia ai-live co 5 min (limit API GitHub na stronie, 11c.11)
EVENT_PUB_SEC = 20
SOFT_PUB_SEC = 120            # praca Krytyka i Badacza — publikacja najwyżej co 2 min (limit API GitHub na stronie)
LINE_SEC = 60
ERROR_REPEAT_SEC = 600


def mmss(s) -> str:
    if s is None:
        return "—"
    s = int(round(s))
    return f"{'−' if s < 0 else '+'}{abs(s) // 60}:{abs(s) % 60:02d}"


def hm(t: float | None) -> str:
    return "—" if t is None else datetime.fromtimestamp(t, PL).strftime("%H:%M")


def describe(e: dict) -> str:
    """Zdarzenie feedu → zdanie do huba, terminala i strony."""
    k = e["kind"]
    if k == "stocks-night":
        return f"kopia akcji po nocnym odświeżeniu automatu (sesja {e['date']})"
    miss = e.get("missing") or []
    tail = f" · brak: {', '.join(miss[:8])}{'…' if len(miss) > 8 else ''}" if miss else ""
    lag = "" if e.get("firestore_at") is None else f" · Firestore → Mac {mmss(e['local_at'] - e['firestore_at'])[1:]}"
    if k == "stocks":
        return f"świeca akcji {e['candle']} (zamknięcie {hm(e['close_at'])}): {e['have']}/{e['need']} w kopii {mmss(e['local_at'] - e['close_at'])} po zamknięciu{lag}{tail}"
    if k == "stocks-late":
        return f"świeca akcji {e['candle']}: dociągnięte {e['have']}/{e['need']}{tail}"
    when = f"{hm(e['close_at'] - 3600)}–{hm(e['close_at'])}"
    if k == "fx":
        return f"świece FX {when}: {e['have']}/{e['need']} w kopii {mmss(e['local_at'] - e['close_at'])} po zamknięciu{lag}{tail}"
    return f"świece FX {when}: dociągnięte {e['have']}/{e['need']}{tail}"


class Supervisor:
    """Pętla nadzorcy. Wszystko wstrzykiwane — selftest podstawia atrapy i zegar."""

    def __init__(self, hub, stocks, fx, out, ollama_info: dict, fx_ratings, fx_note, clock=time.time, log=print,
                 version: str | None = None):
        from .. import __version__
        self.hub, self.stocks, self.fx, self.out = hub, stocks, fx, out
        self.ollama, self.fx_ratings, self.fx_note = ollama_info, fx_ratings, fx_note
        self.clock, self.log = clock, log
        self.version, self.step_name = version or __version__, STEP
        self.started_at = clock()
        self.last_pub = 0.0
        self.pending = False
        self.soft = False
        self.last_line = clock()
        self.errors: dict[str, float] = {}
        self.publishes = 0
        self.agent = None                      # AgentWorker (AI-2), ustawia main()

    @property
    def step(self):           # nazwa kroku do status.json (status.document czyta sup.step)
        return self.step_name

    def reads_today(self) -> int:
        n = 0
        for f in (self.stocks and self.stocks.src, self.fx and self.fx.live.src):
            n += int(getattr(f, "reads", 0) or 0)
        return n

    def publish(self, now: float, stopped: bool = False) -> bool:
        ok = self.out.publish(status.document(self, now, stopped))
        self.last_pub, self.pending, self.soft = now, False, False
        self.publishes += 1
        if not ok:
            self._error(f"publikacja ai-live nieudana: {getattr(self.out, 'last_error', '')}", now)
        return ok

    def _error(self, msg: str, now: float) -> None:
        if now - self.errors.get(msg, -1e9) >= ERROR_REPEAT_SEC:
            self.errors[msg] = now
            self.hub.event("error", msg, at=now)
            self.log(f"  ! {msg}")

    def line(self, now: float) -> str:
        s = self.stocks.status() if self.stocks else {}
        f = self.fx.status() if self.fx else {}
        sl, fl = s.get("last") or {}, f.get("last") or {}
        nx = s.get("nextCandle")
        ol = "✓" if self.ollama.get("present") else "—" if self.ollama.get("skipped") else "✗"
        pf = ""
        if self.agent is not None and self.agent.inv.public:
            p = self.agent.inv.public["portfolio"]
            eq = f"{p['equity']:,.0f}".replace(",", " ")
            pf = f" · portfel {eq} $ ({p['open']} otw., {p['pending']} oczek.)"
            cur = self.agent.now_doing()
            pf += f" · teraz: {cur['agent']}" if cur else " · agenci: przerwa"
        return (f"  {datetime.fromtimestamp(now, PL):%H:%M:%S}  akcje {sl.get('candle', '—')} {sl.get('have', '—')}/{sl.get('need', '—')}"
                f"{' · następna ' + nx[5:] if nx else ''} · FX {(fl.get('candle') or '—')[11:16]} UTC {fl.get('have', '—')}/{fl.get('need', '—')}"
                f"{pf} · Firestore dziś {self.reads_today()} · model {self.ollama.get('model', '—')} {ol}")

    def step_once(self) -> list[dict]:
        now = self.clock()
        ev = []
        for name, f in (("akcje", self.stocks), ("FX", self.fx)):
            if f is None:
                continue
            try:
                ev += f.step()
            except Exception as e:                       # sieć, Firestore — próbujemy w kolejnym obrocie
                self._error(f"feed {name}: {type(e).__name__}: {e}", now)
        for e in ev:
            txt = describe(e)
            self.hub.event(e["kind"], txt, data={k: v for k, v in e.items() if k in ("candle", "have", "need", "missing")}, at=now)
            self.log(f"  {datetime.fromtimestamp(now, PL):%H:%M:%S}  {txt}")
            if self.agent is not None:
                if e["kind"] == "stocks":
                    self.agent.submit("stocks", int(e["key"]), e["candle"], e["close_at"])
                elif e["kind"] == "fx":
                    T = int(e["close_at"]) - 3600
                    self.agent.submit("fx", T, f"FX {hm(T)}–{hm(T + 3600)}", e["close_at"])
        if ev:
            self.pending = True
        if (self.pending and now - self.last_pub >= EVENT_PUB_SEC) or (self.soft and now - self.last_pub >= SOFT_PUB_SEC) \
                or now - self.last_pub >= ALIVE_SEC:
            try:
                self.publish(now)
            except Exception as e:
                self._error(f"publikacja ai-live: {type(e).__name__}: {e}", now)
        if now - self.last_line >= LINE_SEC:
            self.last_line = now
            self.log(self.line(now))
        return ev


# ===========================================================================
#  Start
# ===========================================================================
def _fx_log(msg: str) -> None:
    """Komunikaty pętli FX — bez linii „nowe świece” (te same informacje daje zdarzenie feedu)."""
    if "nowe świece" not in msg:
        print(msg)


def _universe() -> tuple[list[str], list[str]]:
    """Spółki handlowane (główne + kontrolne) i tło rynku (SPY, QQQ) — bez doubleProof (sejf AI, zasada 17)."""
    from .. import config, sync
    try:
        u = config.universe()
        return u["main"] + u["proof"], u["context"]
    except Exception as e:
        print(f"  ! system/universe niedostępny ({type(e).__name__}) — lista z manifestu kopii lokalnej")
        m = sync.load_manifest()
        traded = [s for s, v in m.items() if v.get("group") in ("main", "proof")]
        return traded, [s for s, v in m.items() if v.get("group") == "context"]


def start_investor(hub, push, traded, context, live, model, info):
    """Branch `ai` (+ odtworzenie pustego huba), ai/config.json, playbook, Investor, rozliczenie przerwy, wątek agentów."""
    from . import config as aicfg
    from . import excel, playbook
    from .agents import AgentWorker, RoundData
    from .critic import Critic
    from .investor import Investor
    from .research import Researcher
    from .llm import LLM
    from .store import AiStore, restore
    try:
        store = AiStore(push=push)
    except Exception as e:
        print(f"  ! branch ai niedostępny ({type(e).__name__}: {e}) — Agent-Investor bez zapisu na GitHub")
        store = None
    cfg = aicfg.load(store.config_path if store else None)
    empty = not hub.db.execute("SELECT COUNT(*) FROM positions").fetchone()[0] and not hub.meta("round_n")
    if empty and store is not None and restore(hub, store.repo.dir):
        print("  hub był pusty — odtworzony z brancha ai")
    ihub = Hub()                                           # osobne połączenie dla wątku agentów
    llm = LLM(cfg, record=lambda **k: ihub.llm_call(**k))
    inv = Investor(cfg, ihub, llm, out=store, xlsx=lambda i, b, p: excel.write(i, b, p))
    pb = playbook.load(refresh=True)
    mech = playbook.mechanical()
    inv.set_playbook(pb, mech)
    sel = sum(1 for s in pb["strategies"] if s["selected"])
    print(f"  playbook: {len(pb['strategies'])} strategii (wybranych {sel}, mnożnik 1,0; pozostałe 0,5) · "
          f"mechaniczny inwestor: {(mech or {}).get('closed', '—')} zamkniętych")
    data = RoundData(traded, context, live, model)
    t0 = time.time()
    prices, sig, _ = data.get(need_signals=bool(inv.main.active() or inv.shadow.active()))
    r = inv.startup(prices, sig)
    pf = inv.public["portfolio"]
    eq = f"{pf['equity']:,.0f}".replace(",", " ")
    print(f"  Agent-Investor: rozliczenie przerwy — wejść {r['entries']}, wyjść {r['exits']} · stan konta {eq} $, "
          f"pozycji {pf['positions']} ({time.time() - t0:.0f} s) · Excel: {aicfg.xlsx_path(cfg)}")
    if not info.get("present") and not info.get("skipped"):
        print("  ! model językowy niedostępny — rundy skończą się „brak decyzji”")
    critic = Critic(cfg, ihub, llm, inv)
    researcher = Researcher(cfg, ihub, llm, data)
    ex = inv.explore()
    c = ihub.hyp_counts()
    print(f"  dyspozytor: Inwestor › Krytyk › Badacz, jeden naraz · poziom nauki {ex['level']} ({ex['name']}) · "
          f"hipotez {sum(c.values())}, w próbie {c.get('próba', 0)}")
    return AgentWorker(inv, data, store=store, pb_loader=lambda: playbook.load(refresh=True), mech_loader=playbook.mechanical,
                       critic=critic, researcher=researcher)


def main() -> None:
    from .. import __version__
    from .. import config, sync
    from ..fx import live as lv
    from ..fx import sync as fxs
    from ..fx.store import fx_repo
    from ..lab.store import ResultsRepo

    ap = argparse.ArgumentParser(description="IA 4 — AI Investor: nadzorca (`ia4 start`, instrukcja 11c.3)")
    ap.add_argument("--no-push", action="store_true", help="bez GitHub (status.json i forecast.json tylko lokalnie)")
    ap.add_argument("--no-sync", action="store_true", help="bez synchronizacji przy starcie")
    ap.add_argument("--no-llm-check", action="store_true", help="bez sprawdzania Ollamy i modelu")
    a = ap.parse_args()
    push = not a.no_push

    print(f"IA 4 — AI Investor, krok {STEP} (wersja {__version__})\n")
    lock.acquire()
    others = lock.others_running()
    if others:
        lock.release()
        raise SystemExit(f"Działa już: {', '.join(others)}. Zatrzymaj (Ctrl+C w jego oknie) i uruchom `ia4 start` ponownie — "
                         "prognoza FX liczy się wewnątrz nadzorcy, a pamięć zajmuje model językowy (11c.2).")
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["caffeinate", "-dims", "-w", str(os.getpid())])
            print("  caffeinate: Mac nie zaśnie, dopóki program działa (noc: laptop otwarty i na zasilaczu).")
        except OSError:
            print("  ! caffeinate niedostępny — Mac może zasnąć.")

    hub = Hub()
    run_id = hub.run_start(socket.gethostname(), __version__, STEP, " ".join(sys.argv[1:]))
    hub.event("start", f"start nadzorcy — wersja {__version__}, krok {STEP}")
    try:
        # 1. Ollama i model
        if a.no_llm_check:
            info = {"model": ollama.MODEL, "skipped": True}
            print("  Ollama: pominięte (--no-llm-check)")
        else:
            info = ollama.check(start=True)
            p = ollama.problem(info)
            if p:
                hub.event("error", p)
                raise SystemExit(p)
            print(f"  Ollama {info.get('version')}: {info['model']} ({info.get('quant') or '?'}, {info.get('sizeGB')} GB, "
                  f"digest {info.get('digest')}) ✓")
        hub.event("ollama", f"Ollama {info.get('version', '—')} · {info['model']} "
                            f"{'pominięte' if info.get('skipped') else 'gotowy'}")

        # 2. synchronizacja przy starcie (pełna przyrostowa — łapie wszystko z przerwy)
        traded, context = _universe()
        syms = traded + context
        t0 = time.time()
        synced = False
        if not a.no_sync:
            print(f"  synchronizacja akcji: {len(traded)} spółek handlowanych + {', '.join(context)} (bez doubleProof)…")
            try:
                sync.sync(syms, quiet=True)
                synced = True
            except Exception as e:
                print(f"  ! synchronizacja akcji nieudana ({type(e).__name__}: {e}) — praca na kopii lokalnej")
            print("  synchronizacja FX 1h…")
            try:
                dfs = fxs.sync(quiet=True)
            except Exception as e:
                print(f"  ! synchronizacja FX nieudana ({type(e).__name__}: {e}) — praca na kopii lokalnej")
                dfs = fxs.load_all()
        else:
            dfs = fxs.load_all()
        have = {s: feed.last_key(s) for s in syms}
        newest = max(have.values()) if have else 0
        hub.event("sync", f"synchronizacja przy starcie: akcje do {nyse.label(newest) if newest else '—'}, "
                          f"FX {len(dfs)} instrumentów ({time.time() - t0:.0f} s)")
        print(f"  kopia akcji do {nyse.label(newest) if newest else '—'} · FX {len(dfs)} instrumentów ({time.time() - t0:.0f} s)")

        # 5. prognoza FX wewnątrz nadzorcy (kod ia4.fx.live) albo sam feed FX
        now = time.time()
        fx_ratings, fx_note, live, model = None, None, None, None
        try:
            repo = fx_repo(push=push)
            repo.ensure()
            model = lv.Model(repo.root)
            out_fx = lv.LiveRepo(repo.root.parent / "fx-live-repo", push=push)
            out_fx.ensure(repo._origin() if push else None)
            live = lv.Live(dfs, model, lv.Source(), out_fx, log=_fx_log)
            live.recompute(now)
            live.publish(now)
            fx_ratings = {"run": model.run, "at": model.run_at, "method": model.model.get("method")}
            print(f"  prognoza FX: ratingi {model.run}, model {model.model.get('method')} → fx-live/forecast.json")
        except (SystemExit, Exception) as e:
            fx_note = f"prognoza FX wyłączona: {e}"
            print(f"  ! {fx_note} — działa sam feed FX")
            live = feed.feed_only(lv.Live)(dfs, feed._NoModel(), lv.Source(), None, log=_fx_log)
            model = None
        hub.event("fx", "prognoza FX " + (f"działa (ratingi {model.run})" if model else "wyłączona — sam feed FX"))

        # 3. Agent-Investor: branch ai, ustawienia, playbook, rozliczenie przerwy (przegląd Managera — od AI-4)
        worker = start_investor(hub, push, traded, context, live, model, info)

        stocks = feed.StockFeed(feed.StockSource(), traded, context, have, hub)
        if synced:
            stocks.startup_synced(time.time())
        fx = feed.FxFeed(live, hub)
        out = status.AiLiveRepo(config.RESEARCH_DIR / "ai-live-repo", push=push)
        out.ensure(ResultsRepo(config.RESEARCH_DIR / "ai-live-repo")._origin() if push else None)
        sup = Supervisor(hub, stocks, fx, out, info, fx_ratings, fx_note)
        sup.agent = worker
        if worker is not None:
            worker.on_change = lambda urgent=True: setattr(sup, "pending" if urgent else "soft", True)
            worker.start()
        sup.publish(time.time())
        print(f"\n  strona: https://miszyszka.github.io/IA4/#ai  (Ctrl+C kończy)\n")
        print(sup.line(time.time()))
        try:
            while True:
                sup.step_once()
                time.sleep(LOOP_SEC)
        except KeyboardInterrupt:
            print("\n  zatrzymuję… (zapis huba i ostatnia publikacja)")
            if worker is not None and worker.busy:
                print("  czekam na koniec bieżącego zadania agenta (najwyżej 3 min; Ctrl+C jeszcze raz — przerwij)…")
                try:
                    worker.stop(timeout=180)
                except KeyboardInterrupt:
                    print("  ! runda przerwana — ostatnia decyzja może nie być zapisana")
            elif worker is not None:
                worker.stop(timeout=5)
            now = time.time()
            hub.event("stop", "zatrzymano (Ctrl+C)", at=now)
            try:
                sup.publish(now, stopped=True)
                if model is not None:
                    live.publish(now, stopped=True)
            except Exception as e:
                print(f"  ! ostatnia publikacja nieudana: {e}")
            print("  zatrzymano — strona pokaże „zatrzymany”.")
    finally:
        hub.run_stop(run_id)
        hub.close()
        lock.release()


if __name__ == "__main__":
    main()
