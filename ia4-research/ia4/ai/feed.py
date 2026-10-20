"""
IA 4 — feed AI Investor: kopia lokalna nadążająca za Firestore (instrukcja, sekcja 11c.4).
Wersja projektu: 1.51 (2026-10-20) — musi zgadzać się z IA4_INSTRUKCJA.md

AKCJE (StockFeed): od zamknięcia świecy sesji + 60 s co 30 s 1 odczyt system/status; gdy `lastWrite`
jest nowszy niż ostatnio widziany — szybka synchronizacja (tylko dokumenty zmienione od poprzedniego
razu, `ia4.sync`, quick) instrumentów, którym brakuje tej świecy. Zdarzenie „świeca akcji” — gdy
wszystkie 53 spółki handlowane mają świecę albo 4 min po zamknięciu (z listą brakujących). Po 15 min
spóźnienia pytanie co 5 min. Raz po sesji (zamknięcie + 75 min, po nocnym odświeżeniu automatu) szybka
synchronizacja wszystkich instrumentów. Instrument spóźniony ponad godzinę nie jest już ścigany — dociąga go
następna świeca albo synchronizacja po sesji. doubleProof — nigdy (sejf AI, zasada 17).

FX (FxFeed): pętla `ia4.fx.live` (4c.9) bez zmian — ten sam kod, te same odczyty; tu tylko zapis
spływu świec: godzina = komplet instrumentów z otwartym rynkiem albo 5 min po zamknięciu.

Źródła danych są wstrzykiwane (selftest podstawia fałszywe Firestore i zegar).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from . import nyse

FIRST_CHECK_SEC = 60          # pierwsze pytanie o świecę akcji: zamknięcie + 60 s
LOOP_SEC = 30
LATE_SEC = 15 * 60
LATE_EVERY_SEC = 300
MAX_CHASE_SEC = 3600          # po godzinie spóźnienia czekamy na następną świecę albo synchronizację po sesji
STOCK_WAVE_SEC = 4 * 60       # zdarzenie świecy akcji najpóźniej 4 min po zamknięciu (jak 11a)
FX_WAVE_SEC = 5 * 60          # godzina FX najpóźniej 5 min po zamknięciu (11c.6)
NIGHT_AFTER_SEC = 75 * 60     # szybka synchronizacja wszystkich po nocnym odświeżeniu (45 min + ponowienie)
NIGHT_UNTIL_SEC = 6 * 3600


def iso(t: float | None) -> str | None:
    return None if t is None else datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ===========================================================================
#  Firestore — akcje (na Macu; w selftest — atrapa z tym samym interfejsem)
# ===========================================================================
class StockSource:
    """last_write() — 1 odczyt system/status; refresh(syms) — szybka synchronizacja → {SYMBOL: klucz ostatniej świecy}."""

    def __init__(self):
        self.reads = 0
        self.day = None

    def _count(self, n: int) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self.day:
            self.day, self.reads = today, 0
        self.reads += n

    def last_write(self) -> float | None:
        from .. import config
        d = config.client().document("system/status").get()
        self._count(1)
        v = (d.to_dict() or {}).get("lastWrite") if d.exists else None
        return v.timestamp() if hasattr(v, "timestamp") else None

    def refresh(self, syms: list[str]) -> dict[str, int]:
        from .. import sync
        m = sync.load_manifest()
        out = {}
        for s in syms:
            try:
                st = sync.sync_symbol(s, m, quick=True, quiet=True)
                self._count(int(st.get("docs") or 1))
                out[s] = last_key(s)
            except Exception as e:                    # jeden instrument nie zatrzymuje reszty
                print(f"  ! {s}: {type(e).__name__}: {e}")
        sync.save_manifest(m)
        return out


def last_key(sym: str) -> int:
    """Klucz ostatniej świecy instrumentu w kopii lokalnej (0 — brak pliku)."""
    import pandas as pd
    from .. import sync
    p = sync.parquet_path(sym)
    if not p.exists():
        return 0
    df = pd.read_parquet(p, columns=["date", "slot"])
    if df.empty:
        return 0
    r = df.iloc[-1]
    return nyse.key(str(r["date"]), int(r["slot"]))


# ===========================================================================
#  Feed akcji
# ===========================================================================
class StockFeed:
    def __init__(self, src, traded: list[str], context: list[str], have: dict[str, int], hub, clock=time.time, log=print):
        self.src, self.traded, self.context, self.hub, self.clock, self.log = src, list(traded), list(context), hub, clock, log
        self.syms = self.traded + self.context
        self.have = {s: int(have.get(s, 0)) for s in self.syms}
        self.next_check = 0.0
        self.target: int | None = None
        self.seen_write: float | None = None
        self.last: dict | None = None             # ostatnia zapisana fala (do status.json)
        self.done: set[int] = set()
        self.syncs = 0
        self.night_done = hub.meta("stock_night_done") if hub else None
        t = nyse.last_closed(clock(), FIRST_CHECK_SEC)
        if t and not self.lacking(t["key"], self.traded):
            self.done.add(t["key"])                # świeca była już w kopii przy starcie — to nie przybycie

    def startup_synced(self, now: float) -> None:
        """Pełna synchronizacja przy starcie była już po nocnym odświeżeniu — nie powtarzamy go dziś."""
        t = nyse.last_closed(now, FIRST_CHECK_SEC)
        last_c = nyse.session_last_close(t["date"]) if t else None
        if last_c and now - last_c >= NIGHT_AFTER_SEC:
            self.night_done = t["date"]
            if self.hub:
                self.hub.set_meta("stock_night_done", t["date"])

    def lacking(self, k: int, syms=None) -> list[str]:
        return [s for s in (syms or self.syms) if self.have.get(s, 0) < k]

    def _record(self, t: dict, now: float) -> dict:
        miss = self.lacking(t["key"], self.traded)
        row = {"candle": nyse.label(t["key"]), "key": t["key"], "close_at": t["close"], "firestore_at": self.seen_write,
               "local_at": now, "have": len(self.traded) - len(miss), "need": len(self.traded), "missing": miss}
        if self.hub:
            self.hub.feed("stocks", row["candle"], t["close"], self.seen_write, now, row["have"], row["need"], miss)
        self.last = row
        return row

    def step(self) -> list[dict]:
        """Jeden obrót. Zwraca listę zdarzeń: {kind: 'stocks'|'stocks-late'|'stocks-night', ...}."""
        now = self.clock()
        ev = []
        t = nyse.last_closed(now, FIRST_CHECK_SEC)
        if t:
            k = t["key"]
            if k != self.target:                       # nowa świeca: rytm pytań od nowa (nie po ściganiu poprzedniej)
                self.target, self.next_check = k, 0.0
            lack = self.lacking(k)
            if lack and now - t["close"] > MAX_CHASE_SEC:
                lack = []                              # nie ścigamy dalej (następna świeca / po sesji)
            if lack and now >= self.next_check:
                lw = self.src.last_write()
                if lw is not None and (self.seen_write is None or lw > self.seen_write):
                    got = self.src.refresh(lack)
                    self.syncs += 1
                    self.have.update({s: v for s, v in got.items() if v})
                    self.seen_write = lw
                lack = self.lacking(k)
                late = now - t["close"]
                self.next_check = (now + (LATE_EVERY_SEC if late > LATE_SEC else LOOP_SEC) - 1) if lack else 0.0
            miss = self.lacking(k, self.traded)
            if k not in self.done and (not miss or now >= t["close"] + STOCK_WAVE_SEC):
                self.done.add(k)
                ev.append({"kind": "stocks", **self._record(t, now)})
            elif k in self.done and self.last and self.last["key"] == k and self.last["missing"] and len(miss) < len(self.last["missing"]):
                ev.append({"kind": "stocks-late", **self._record(t, now)})     # spóźnione spółki uzupełniają wiersz
            # raz po sesji: nocne odświeżenie automatu przepisuje ostatnie sesje (4 p. 2)
            last_c = nyse.session_last_close(t["date"])
            if (last_c and NIGHT_AFTER_SEC <= now - last_c < NIGHT_UNTIL_SEC and self.night_done != t["date"]):
                self.src.refresh(self.syms)
                self.syncs += 1
                self.night_done = t["date"]
                if self.hub:
                    self.hub.set_meta("stock_night_done", t["date"])
                ev.append({"kind": "stocks-night", "date": t["date"], "local_at": now})
        return ev

    def status(self) -> dict:
        now = self.clock()
        nx = nyse.next_close(now)
        last = self.last
        if last is None:
            t = nyse.last_closed(now, FIRST_CHECK_SEC)
            if t:
                miss = self.lacking(t["key"], self.traded)
                last = {"candle": nyse.label(t["key"]), "key": t["key"], "close_at": t["close"], "firestore_at": None,
                        "local_at": None, "have": len(self.traded) - len(miss), "need": len(self.traded), "missing": miss}
        return {"symbols": len(self.syms), "traded": len(self.traded), "marketOpen": nyse.is_open(now),
                "next": iso(nx["close"]) if nx else None, "nextCandle": nyse.label(nx["key"]) if nx else None,
                "last": _row(last), "syncs": self.syncs}


def _row(r: dict | None) -> dict | None:
    if not r:
        return None
    lag = None if r.get("firestore_at") is None or r.get("local_at") is None else round(r["local_at"] - r["firestore_at"])
    dly = None if r.get("local_at") is None else round(r["local_at"] - r["close_at"])
    return {"candle": r["candle"], "closeAt": iso(r["close_at"]), "firestoreAt": iso(r.get("firestore_at")),
            "localAt": iso(r.get("local_at")), "lagSec": lag, "delaySec": dly,
            "have": r.get("have"), "need": r.get("need"), "missing": r.get("missing") or []}


def flow(hub, kind: str, n: int) -> list[dict]:
    return [_row(r) for r in hub.feed_recent(kind, n)]


# ===========================================================================
#  Feed FX — opakowanie pętli ia4.fx.live
# ===========================================================================
class _NoModel:
    run, run_at, model, check = None, None, {}, {}

    def reload_if_changed(self) -> bool:
        return False


def feed_only(live_cls):
    """Pętla FX bez prognozy (brak katalogu albo ratingów na branchu `fx`): te same odczyty i kopia, bez publikacji."""
    class FeedOnly(live_cls):
        def recompute(self, now):
            self.state["generatedAt"] = iso(now)

        def publish(self, now, stopped=False):
            self.last_alive = now
            return True
    return FeedOnly


class FxFeed:
    def __init__(self, live, hub, clock=time.time):
        from ..fx import instruments as fi
        self.live, self.hub, self.clock, self.fi = live, hub, clock, fi
        self.done: set[int] = set()
        self.last: dict | None = None
        self.arrived: dict[int, float] = {}
        T = self._target(clock())
        if T is not None and not self._missing(T):
            self.done.add(T)

    def _target(self, now: float) -> int | None:
        """Początek najnowszej godziny, której świeca powinna już być (zamknięcie + 60 s), z otwartym rynkiem."""
        h = int(now - 60) // 3600 * 3600 - 3600
        for _ in range(24 * 4):
            if any(self.fi.market_open(self.fi.group_of(s), h)[0] for s in self.live.last):
                return h
            h -= 3600
        return None

    def _need(self, T: int) -> list[str]:
        return [s for s in self.live.last if self.fi.market_open(self.fi.group_of(s), T)[0]]

    def _missing(self, T: int) -> list[str]:
        return [s for s in self._need(T) if self.live.last[s] < T]

    def _record(self, T: int, now: float) -> dict:
        need, miss = self._need(T), self._missing(T)
        fs = getattr(self.live.src, "updated", None)
        row = {"candle": iso(T), "close_at": T + 3600, "firestore_at": fs, "local_at": self.arrived.get(T, now),
               "have": len(need) - len(miss), "need": len(need), "missing": miss}
        if self.hub:
            self.hub.feed("fx", row["candle"], row["close_at"], fs, row["local_at"], row["have"], row["need"], miss)
        self.last = row
        return row

    def step(self) -> list[dict]:
        before = dict(self.live.last)
        self.live.step()
        now = self.clock()
        fresh = [s for s in self.live.last if self.live.last[s] > before.get(s, 0)]
        ev = []
        T = self._target(now)
        if T is None:
            return ev
        if fresh:
            self.arrived[T] = now
        miss = self._missing(T)
        if T not in self.done and (not miss or now >= T + 3600 + FX_WAVE_SEC):
            self.done.add(T)
            ev.append({"kind": "fx", **self._record(T, now)})
        elif T in self.done and self.last and self.last["candle"] == iso(T) and len(miss) < len(self.last["missing"]):
            ev.append({"kind": "fx-late", **self._record(T, now)})
        for k in [k for k in self.arrived if k < T - 86400]:
            del self.arrived[k]
        return ev

    def status(self) -> dict:
        now = self.clock()
        T = self._target(now)
        last = self.last
        if last is None and T is not None:
            need, miss = self._need(T), self._missing(T)
            last = {"candle": iso(T), "close_at": T + 3600, "firestore_at": None, "local_at": None,
                    "have": len(need) - len(miss), "need": len(need), "missing": miss}
        nxt = (int(now) // 3600 + 1) * 3600
        return {"instruments": len(self.live.last), "upToDate": sum(1 for s in self.live.last if T is not None and self.live.last[s] >= T),
                "marketOpen": bool(self.fi.market_open("fx", int(now) // 3600 * 3600)[0]), "next": iso(nxt),
                "last": _row(last), "reads": getattr(self.live.src, "reads", 0)}
