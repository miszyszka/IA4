"""
IA 4 — test AI Investor (krok AI-1) na danych syntetycznych (instrukcja, sekcja 11c).
Wersja projektu: 1.56 (2026-10-21) — musi zgadzać się z IA4_INSTRUKCJA.md

  python -m ia4.ai.selftest          # kilka sekund; wynik musi brzmieć „WYNIK: OK”

Bez Firestore, GitHub i Ollamy: kalendarz NYSE (czas letni, sesja skrócona, święto), feed akcji na
fałszywym Firestore i zegarze (rytm pytań, odczyty, zdarzenia, spóźnione i zablokowane spółki, weekend,
synchronizacja po sesji), feed FX (komplet, weekend — tylko BTC), szybka synchronizacja (`ia4.sync`,
quick), hub, blokada, nadzorca i status.json (rytm publikacji, bez NaN).
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import feed, lock, nyse, selftest2, selftest3, status
from .__main__ import Supervisor, describe
from .hub import Hub


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'OK ' if ok else 'BŁĄD'}  {name}" + (f"  — {detail}" if detail else ""))
    return bool(ok)


# ---------------------------------------------------------------------------
def test_calendar() -> bool:
    ok = True
    d = nyse.closes(datetime(2026, 10, 9).date())
    ok &= check("sesja zwykła (czas letni USA): 7 świec, 1. zamyka się 14:30 UTC, 7. o 20:00 UTC",
                len(d) == 7 and d[0][1] == ts("2026-10-09T14:30:00Z") and d[-1][1] == ts("2026-10-09T20:00:00Z"))
    d = nyse.closes(datetime(2026, 11, 27).date())
    ok &= check("sesja skrócona 27.11.2026: 4 świece, ostatnia 13:00 ET = 18:00 UTC",
                len(d) == 4 and d[-1][1] == ts("2026-11-27T18:00:00Z") and d[2][1] == ts("2026-11-27T17:30:00Z"))
    ok &= check("święto 26.11.2026 i sobota: bez świec", nyse.closes(datetime(2026, 11, 26).date()) == []
                and nyse.closes(datetime(2026, 10, 10).date()) == [])
    d = nyse.closes(datetime(2026, 10, 30).date())
    pl = datetime.fromtimestamp(d[0][1], nyse.PL).strftime("%H:%M")
    ok &= check("30.10.2026 (zima w Europie, lato w USA): 1. świeca zamyka się 15:30 PL", pl == "15:30", pl)
    sat = ts("2026-10-10T12:00:00Z")
    lc, nx = nyse.last_closed(sat), nyse.next_close(sat)
    ok &= check("sobota: ostatnia świeca — piątek #7, następna — poniedziałek #1",
                lc["key"] == 202610097 and nx["key"] == 202610121, f"{nyse.label(lc['key'])} → {nyse.label(nx['key'])}")
    return ok


# ---------------------------------------------------------------------------
class FakeStocks:
    """Fałszywy Firestore akcji: świeca k instrumentu s „zapisana” w chwili close + delay(s, k)."""

    def __init__(self, syms, days, delay):
        self.syms, self.delay = syms, delay
        self.cand = [(nyse.key(d, sl), c) for d in days for sl, c in nyse.closes(datetime.fromisoformat(d).date())]
        self.now = 0.0
        self.reads = self.status_reads = self.refreshes = 0
        self.status_at: list[float] = []

    def visible(self, s) -> int:
        k = 0
        for key, c in self.cand:
            dl = self.delay(s, key)
            if dl is not None and c + dl <= self.now:
                k = max(k, key)
        return k

    def last_write(self):
        self.reads += 1
        self.status_reads += 1
        self.status_at.append(self.now)
        w = [c + self.delay(s, k) for k, c in self.cand for s in self.syms
             if self.delay(s, k) is not None and c + self.delay(s, k) <= self.now]
        return max(w) if w else None

    def refresh(self, syms):
        self.refreshes += 1
        self.reads += len(syms)                       # ok. 1 dokument na instrument (szybka ścieżka)
        return {s: self.visible(s) for s in syms}


def test_stock_feed(hubdir: Path) -> bool:
    traded = [f"S{i:02d}" for i in range(53)]
    context = ["SPY", "QQQ"]
    days = ["2026-10-13", "2026-10-14"]

    def delay(s, k):
        if s == "S07" and k == 202610133:
            return 7 * 60                              # spóźniona spółka na 3. świecy
        if s == "S11" and k >= 202610135:
            return None                                # zablokowana od 5. świecy (Yahoo nie oddaje)
        return 120 + (hash((s, k)) % 50)               # zwykle 2:00–2:50 po zamknięciu

    src = FakeStocks(traded + context, days, delay)
    hub = Hub(hubdir / "feed.sqlite")
    clock = {"t": ts("2026-10-13T12:00:00Z")}
    src.now = clock["t"]
    have = {s: nyse.key("2026-10-12", 7) for s in traded + context}
    F = feed.StockFeed(src, traded, context, have, hub, clock=lambda: clock["t"], log=lambda *a: None)
    evs = []
    end = ts("2026-10-14T04:00:00Z")
    while clock["t"] < end:
        src.now = clock["t"]
        for e in F.step():
            evs.append(e)
        clock["t"] += 5
    ok = True
    waves = [e for e in evs if e["kind"] == "stocks"]
    ok &= check("7 fal świec akcji 13.10.2026, każda raz", len(waves) == 7 and len({e["key"] for e in waves}) == 7,
                ", ".join(f"#{e['key'] % 10}:{e['have']}" for e in waves))
    full = [e for e in waves if not e["missing"]]
    lags = [e["local_at"] - e["firestore_at"] for e in full]
    dly = [e["local_at"] - e["close_at"] for e in full]
    ok &= check("komplet 53/53 w kopii najpóźniej 35 s po zapisie ostatniej spółki w Firestore (kryterium AI-1: ≤ 2 min)",
                len(full) == 3 and max(lags) <= 35, f"Firestore → Mac ≤ {max(lags):.0f} s, od zamknięcia ≤ {max(dly):.0f} s")
    w3 = [e for e in waves if e["key"] == 202610133][0]
    late3 = [e for e in evs if e["kind"] == "stocks-late" and e["key"] == 202610133]
    ok &= check("świeca #3: po 4 min zdarzenie bez S07, potem S07 dociągnięta ≤ 35 s po zapisie",
                abs(w3["local_at"] - (w3["close_at"] + 240)) <= 5 and w3["missing"] == ["S07"] and late3
                and late3[0]["have"] == 53 and late3[0]["local_at"] - (w3["close_at"] + 420) <= 35)
    w5 = [e for e in waves if e["key"] == 202610135][0]
    after = [t for t in src.status_at if w5["close_at"] + 3600 < t < w5["close_at"] + 3600 + 3000 and t < ts("2026-10-13T19:31:00Z")]
    ok &= check("zablokowana S11: zdarzenie z brakiem, ściganie najwyżej godzinę", w5["missing"] == ["S11"] and not after)
    night = [e for e in evs if e["kind"] == "stocks-night"]
    last_c = ts("2026-10-13T20:00:00Z")
    ok &= check("synchronizacja po sesji: raz, ≥ 75 min po zamknięciu ostatniej świecy",
                len(night) == 1 and night[0]["local_at"] >= last_c + 75 * 60, f"{len(night)}×")
    idle = [t for t in src.status_at if t < ts("2026-10-13T14:31:00Z") or ts("2026-10-13T21:30:00Z") < t]
    ok &= check("brak pytań poza sesją (przed 1. świecą i w nocy)", not idle, f"{len(idle)} zbędnych")
    ok &= check("odczyty Firestore na dzień sesyjny (55 spółek): ≤ 1100", src.reads <= 1100,
                f"{src.reads} (system/status {src.status_reads}, synchronizacji {src.refreshes})")
    rows = hub.feed_recent("stocks", 10)
    r3 = [r for r in rows if r["candle"] == nyse.label(202610133)][0]
    ok &= check("hub: spływ świec — 7 wierszy, spóźniona spółka uzupełnia wiersz #3",
                len(rows) == 7 and r3["have"] == 53 and r3["missing"] == [])
    # start w środku sesji z kompletną świecą — bez zdarzenia o świecy, która już była
    clock["t"] = ts("2026-10-13T16:45:00Z")
    src.now = clock["t"]
    have2 = {s: src.visible(s) for s in traded + context}
    F2 = feed.StockFeed(src, traded, context, have2, Hub(hubdir / "feed2.sqlite"), clock=lambda: clock["t"])
    ok &= check("start z kompletną świecą: bez zdarzenia", F2.step() == [])
    # weekend: zero odczytów
    src2 = FakeStocks(traded + context, ["2026-10-09"], lambda s, k: 130)
    clock["t"] = ts("2026-10-10T08:00:00Z")
    F3 = feed.StockFeed(src2, traded, context, {s: 202610097 for s in traded + context}, Hub(hubdir / "feed3.sqlite"),
                        clock=lambda: clock["t"])
    F3.night_done = "2026-10-09"
    while clock["t"] < ts("2026-10-12T08:00:00Z"):
        src2.now = clock["t"]
        F3.step()
        clock["t"] += 30
    ok &= check("weekend: 0 odczytów Firestore (akcje)", src2.reads == 0, f"{src2.reads}")
    return ok


# ---------------------------------------------------------------------------
class FakeLive:
    """Atrapa ia4.fx.live.Live: last {SYMBOL: początek ostatniej świecy}, świeca widoczna 90 s po zamknięciu."""

    def __init__(self, clock, syms):
        from ..fx import instruments as fi
        self.fi, self.clock = fi, clock
        self.src = type("S", (), {"reads": 0, "updated": None})()
        self.last = {s: self._vis(s, clock()) for s in syms}

    def _vis(self, s, now):
        h = int(now - 3600 - 90) // 3600 * 3600
        while not self.fi.market_open(self.fi.group_of(s), h)[0]:
            h -= 3600
        return h

    def step(self):
        now = self.clock()
        for s in self.last:
            v = self._vis(s, now)
            if v > self.last[s]:
                self.last[s] = v
                self.src.reads += 1
                self.src.updated = v + 3600 + 90
        return True


def test_fx_feed(hubdir: Path) -> bool:
    syms = ["EURUSD", "USDJPY", "BTCUSD"]
    clock = {"t": ts("2026-10-09T15:10:00Z")}
    L = FakeLive(lambda: clock["t"], syms)
    F = feed.FxFeed(L, Hub(hubdir / "fx.sqlite"), clock=lambda: clock["t"])
    evs = []
    while clock["t"] < ts("2026-10-11T23:00:00Z"):
        evs += F.step()
        clock["t"] += 30
    fx = [e for e in evs if e["kind"] == "fx"]
    ok = True
    hours = len({e["candle"] for e in fx})
    ok &= check("każda godzina FX raz (piątek do niedzieli 23:00 UTC)", hours == len(fx) and hours > 50, f"{hours} godzin")
    wk = [e for e in fx if "2026-10-10" in e["candle"]]
    ok &= check("sobota: godzina = sam BTC (1/1)", wk and all(e["need"] == 1 and e["have"] == 1 for e in wk))
    wd = [e for e in fx if "2026-10-09T16" in e["candle"]]
    ok &= check("piątek: komplet 3/3, w kopii ≤ 2 min po zamknięciu", wd and wd[0]["have"] == 3
                and wd[0]["local_at"] - wd[0]["close_at"] <= 120, f"{wd[0]['local_at'] - wd[0]['close_at']:.0f} s" if wd else "")
    return ok


# ---------------------------------------------------------------------------
def test_quick_sync(tmp: Path) -> bool:
    from .. import config, sync
    old = (config.CACHE_DIR, config.MANIFEST_PATH, config.group_of, sync.fetch_updated)
    try:
        config.CACHE_DIR, config.MANIFEST_PATH = tmp / "data", tmp / "data" / "_manifest.json"
        config.group_of = lambda s: "proof"
        rows = [("XYZ", "2026-10-13", sl, 10.0 + sl, 11.0, 9.0, 10.5, 100) for sl in range(1, 8)]
        df = pd.DataFrame(rows[:5], columns=sync.COLUMNS)
        (tmp / "data").mkdir(parents=True)
        df.to_parquet(sync.parquet_path("XYZ"), index=False)
        m = {"XYZ": {"last_date": "2026-10-13", "synced_at": "2026-10-13T18:00:00+00:00", "group": "proof"}}
        asked = {}

        def fake(sym, since):
            asked["since"] = since
            return pd.DataFrame(rows, columns=sync.COLUMNS), 1        # dokument sesji przepisany w całości
        sync.fetch_updated = fake
        st = sync.sync_symbol("XYZ", m, quick=True, quiet=True)
        got = pd.read_parquet(sync.parquet_path("XYZ"))
        ok = check("szybka synchronizacja: tylko dokumenty zmienione (od poprzedniej − 30 min), sesja scalona, manifest przesunięty",
                   len(got) == 7 and st["docs"] == 1 and asked["since"].isoformat().startswith("2026-10-13T17:30")
                   and m["XYZ"]["synced_at"] != "2026-10-13T18:00:00+00:00" and feed.last_key("XYZ") == 202610137,
                   f"świec {len(got)}, odczytów {st['docs']}")
    finally:
        config.CACHE_DIR, config.MANIFEST_PATH, config.group_of, sync.fetch_updated = old
    return ok


# ---------------------------------------------------------------------------
def test_lock(tmp: Path) -> bool:
    p = tmp / "ia4-start.lock"
    ok = True
    p.write_text(json.dumps({"pid": os.getppid(), "host": socket.gethostname(), "startedAt": "teraz"}))
    try:
        lock.guard("python -m ia4.fx.research", p)
        blocked = False
    except SystemExit as e:
        blocked = "ia4 start" in str(e)
    ok &= check("blokada: działający `ia4 start` zatrzymuje fx.research / fx.live / lab", blocked)
    p.write_text(json.dumps({"pid": 2 ** 22 + 12345, "host": socket.gethostname(), "startedAt": "dawno"}))
    try:
        lock.guard("python -m ia4.lab", p)
        free = True
    except SystemExit:
        free = False
    lock.acquire(p)
    mine = json.loads(p.read_text())["pid"] == os.getpid()
    lock.release(p)
    ok &= check("blokada po twardym przerwaniu (PID nie żyje) — nieważna; zdjęcie po końcu", free and mine and not p.exists())
    return ok


# ---------------------------------------------------------------------------
def test_supervisor(tmp: Path) -> bool:
    clock = {"t": ts("2026-10-13T14:00:00Z")}
    traded, context = [f"S{i:02d}" for i in range(53)], ["SPY", "QQQ"]
    src = FakeStocks(traded + context, ["2026-10-13"], lambda s, k: 140)
    src.now = clock["t"]
    hub = Hub(tmp / "sup.sqlite")
    stocks = feed.StockFeed(src, traded, context, {s: 202610127 for s in traded + context}, hub, clock=lambda: clock["t"])
    L = FakeLive(lambda: clock["t"], ["EURUSD", "USDJPY", "BTCUSD"])
    fx = feed.FxFeed(L, hub, clock=lambda: clock["t"])

    class Out:
        def __init__(s):
            s.docs, s.last_error = [], ""

        def publish(s, d):
            s.docs.append(json.loads(json.dumps(d, allow_nan=False)))
            return True

    out = Out()
    lines = []
    sup = Supervisor(hub, stocks, fx, out, {"model": "qwen2.5:14b", "skipped": True}, None, "prognoza FX wyłączona: test",
                     clock=lambda: clock["t"], log=lines.append, version="test")
    sup.publish(clock["t"])
    end = clock["t"] + 3 * 3600
    while clock["t"] < end:
        src.now = clock["t"]
        sup.step_once()
        clock["t"] += 5
    sup.publish(clock["t"], stopped=True)
    d = out.docs[-2]
    ok = True
    ok &= check("status.json co 5 min i po zdarzeniach (≤ 1 na 20 s), bez NaN", 36 <= len(out.docs) <= 60,
                f"{len(out.docs)} publikacji w 3 h")
    ok &= check("status.json: feed akcji i FX, agenci (bez dyspozytora — wyłączeni), spływ, zdarzenia, maszyna",
                d["feed"]["stocks"]["last"]["have"] == 53 and d["feed"]["fx"]["last"]["need"] == 3
                and [a["id"] for a in d["agents"]] == ["investor", "critic", "researcher"]
                and all(a["state"] == "off" for a in d["agents"]) and len(d["flow"]["stocks"]) == 3
                and any(e["kind"] == "stocks" for e in d["events"]) and "cpus" in d["machine"],
                f"{len(json.dumps(d)) // 1024} KB, odczyty dziś {d['feed']['readsToday']}")
    ok &= check("Ctrl+C: ostatnia publikacja ze stoppedAt", "stoppedAt" in out.docs[-1])
    ok &= check("terminal: linia stanu co minutę", 170 <= len([x for x in lines if "akcje" in x and "FX" in x]) <= 200)
    txt = describe({"kind": "stocks", "candle": "2026-10-13 #2", "close_at": ts("2026-10-13T15:30:00Z"),
                    "local_at": ts("2026-10-13T15:32:41Z"), "firestore_at": ts("2026-10-13T15:32:20Z"),
                    "have": 52, "need": 53, "missing": ["S07"]})
    ok &= check("opis zdarzenia po polsku", "17:30" in txt and "+2:41" in txt and "0:21" in txt and "S07" in txt, txt)
    return ok


def main() -> None:
    from .. import __version__
    print(f"IA 4 — selftest AI Investor (wersja {__version__})\n")
    tmp = Path(tempfile.mkdtemp(prefix="ia4-ai-"))
    ok = True
    for name, fn in (("kalendarz NYSE", test_calendar), ("feed akcji", lambda: test_stock_feed(tmp)),
                     ("feed FX", lambda: test_fx_feed(tmp)), ("szybka synchronizacja", lambda: test_quick_sync(tmp / "q")),
                     ("blokada", lambda: test_lock(tmp)), ("nadzorca i status.json", lambda: test_supervisor(tmp)),
                     ("AI-2: silnik portfela", lambda: selftest2.test_engine()),
                     ("AI-2: runda Agent-Investora", lambda: selftest2.test_round(tmp / "inv")),
                     ("1.41: Badacz — hipotezy", lambda: selftest3.test_research(tmp / "res")),
                     ("1.41: zespół — Krytyk, tryb nauki, dyspozytor, zapis", lambda: selftest3.test_team(tmp / "team"))):
        print(f"\n{name}")
        try:
            ok &= fn()
        except Exception as e:
            import traceback
            traceback.print_exc()
            ok &= check(f"{name}: wyjątek", False, f"{type(e).__name__}: {e}")
    print(f"\nWYNIK: {'OK' if ok else 'BŁĄD'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
