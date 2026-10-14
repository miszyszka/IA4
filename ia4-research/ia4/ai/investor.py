"""
IA 4 — Agent-Investor (instrukcja, sekcje 11c.6–11c.7, krok AI-2).
Wersja projektu: 1.40 (2026-10-14) — musi zgadzać się z IA4_INSTRUKCJA.md

Runda po każdej świecy akcji i każdej godzinie FX:
  1. rozliczenie (kod): obie księgi, wszystkie nowe świece — wejścia po open, luka / FC / zamknięcie
     decyzją / SL / TP / limit (engine.py),
  2. stan portfela, stop dzienny, obsunięcie, risk_dial,
  3. kandydaci (kod): sygnały strategii z playbooka na tej świecy (najwyżej 12, wg pierwszeństwa);
     prognoza FX — tylko dla instrumentu z udowodnioną przewagą kierunku; każdy kandydat → księga cieni,
  4. brief (kod) → decyzja (model, JSON) → sprawdzenie (kod) → wykonanie: pozycja „oczekuje” do open
     następnej świecy instrumentu; odrzucone przez kod — z powodem,
  5. zapis: hub, branch `ai`, AI-INVESTOR.xlsx, status dla `ai-live`.
Runda bez kandydatów i bez otwartych pozycji nie woła modelu.
"""

from __future__ import annotations

import json
import time
import traceback

import numpy as np

from . import bench, engine, lessons, market
from .engine import Book, Pos
from .market import Prices, iso, pl

AGENT = "investor"
SYSTEM = """Jesteś Agent-Investor w systemie IA 4. Prowadzisz wirtualny (papierowy) portfel w USD: akcje USA (NYSE, świece 1h) oraz 10 par walutowych i BTC (świece 1h). Tryb rygorystyczny.

Zasady:
1. Wszystkie liczby w briefie policzył kod. Nie wymyślaj liczb i nie licz wyników. Wielkość pozycji, koszty i limity ryzyka liczy i pilnuje kod — może odrzucić Twoją decyzję.
2. KANDYDACI (C1, C2, …) to sygnały strategii z playbooka (albo prognozy FX z udowodnioną przewagą). Dla każdego decydujesz "enter" albo "skip". Kierunek, SL, TP i limit świec są z reguły strategii — nie zmieniasz ich.
3. POZYCJE (P1, …): "hold", "close" (zamknięcie po open następnej świecy) albo "tighten_sl" z polem new_sl = nowa cena SL (tylko w stronę zysku, po właściwej stronie bieżącej ceny). W pozostałych przypadkach new_sl = null.
4. Własny pomysł (own_ideas): najwyżej 1 na rundę, tylko instrument wymieniony w briefie (KANDYDACI albo RYNEK FX), z cenami sl i tp: TP/SL od 1:3 do 3:1, SL co najmniej 1 × ATR14 od ceny, max_bars ≤ 120. Mały osobny budżet — tylko z konkretnego powodu; zwykle lista jest pusta.
5. confidence (0–100) = Twoje prawdopodobieństwo, że transakcja skończy się zyskiem. 50 = rzut monetą. Kod mierzy Twoją kalibrację.
6. note — po polsku, do 600 znaków: dlaczego, konkretnie, z odwołaniem do liczb z briefu (doubleProof, liczba transakcji, szacunek przewagi, wynik na żywo, odległość SL/TP, wnioski). Mało transakcji = niska pewność.
7. Wyniki z danych, na których szukano strategii, są zawyżone — liczą się doubleProof i wynik na żywo. Kierunek FX bez udowodnionej przewagi to rzut monetą.
8. round_note — 1–3 zdania o całej rundzie.
Odpowiadasz wyłącznie JSON-em zgodnym ze schematem: dokładnie jedna decyzja dla każdego kandydata i każdej pozycji."""

SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {"type": "array", "items": {"type": "object", "properties": {
            "ref": {"type": "string"}, "action": {"type": "string", "enum": ["enter", "skip"]},
            "confidence": {"type": "integer", "minimum": 0, "maximum": 100}, "note": {"type": "string"}},
            "required": ["ref", "action", "confidence", "note"]}},
        "positions": {"type": "array", "items": {"type": "object", "properties": {
            "ref": {"type": "string"}, "action": {"type": "string", "enum": ["hold", "close", "tighten_sl"]},
            "new_sl": {"type": ["number", "null"]}, "note": {"type": "string"}},
            "required": ["ref", "action", "new_sl", "note"]}},
        "own_ideas": {"type": "array", "items": {"type": "object", "properties": {
            "instrument": {"type": "string"}, "direction": {"type": "string", "enum": ["long", "short"]},
            "sl": {"type": "number"}, "tp": {"type": "number"}, "max_bars": {"type": "integer"},
            "confidence": {"type": "integer", "minimum": 0, "maximum": 100}, "note": {"type": "string"}},
            "required": ["instrument", "direction", "sl", "tp", "max_bars", "confidence", "note"]}},
        "round_note": {"type": "string"},
    },
    "required": ["candidates", "positions", "own_ideas", "round_note"],
}


def f(x, d=2) -> str:
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{d}f}"


def fs(x, d=2) -> str:
    return "—" if x is None else f"{x:+.{d}f}"


def px_fmt(prices: Prices, inst: str, x) -> str:
    if x is None:
        return "—"
    return f"{x:.{prices.digits(inst)}f}" if prices.kind(inst) != "stock" else f"{x:.2f}"


class Investor:
    def __init__(self, cfg: dict, hub, llm, out=None, xlsx=None, clock=time.time, log=print):
        self.cfg, self.hub, self.llm, self.out, self.xlsx, self.clock, self.log = cfg, hub, llm, out, xlsx, clock, log
        self.main = Book(cfg, "main", [Pos.from_dict(d) for d in hub.load_positions("main")])
        self.shadow = Book(cfg, "shadow", [Pos.from_dict(d) for d in hub.load_positions("shadow")])
        self.started_at = hub.meta("investor_started_at")
        if self.started_at is None:
            self.started_at = clock()
            hub.set_meta("investor_started_at", self.started_at)
            hub.event("investor", "start Agent-Investora — kapitał " + f"{cfg['capital']:,.0f}".replace(",", " ") + " $", agent=AGENT)
        self.peak = hub.meta("equity_peak") or cfg["capital"]
        self.halt = hub.meta("halt")
        self.pb: dict = {"strategies": []}
        self.mech = None
        self.state = {"state": "on", "doing": "czeka na świecę", "since": clock()}
        self.public: dict = {}
        self.dirty: set = set()
        if not hub.lessons_active():
            for t in lessons.SEED:
                hub.lesson_add("Claude", t)

    # ------------------------------------------------------------ playbook
    def set_playbook(self, pb: dict, mech: dict | None = None) -> None:
        st = self.hub.playbook_status()
        for s in pb.get("strategies", []):
            if s["id"] in st and st[s["id"]][0] not in ("bazowa",):        # status nadany później (Manager, AI-4) wygrywa
                s["status"], s["basis_kind"] = st[s["id"]]
        self.pb = pb
        self.by_id = {s["id"]: s for s in pb.get("strategies", [])}
        self.mech = mech
        self.hub.playbook_save(pb.get("strategies", []))

    def auto_withdraw(self) -> None:
        """Kod sam wycofuje strategię, gdy po ≥ 30 transakcjach Inwestora średni wynik netto ≤ 0 (11c.8)."""
        for s in self.pb.get("strategies", []):
            if s.get("status") == "wycofana":
                continue
            cl = [p.ret_net_pct for p in self.main.closed() if p.basis == s["id"]]
            if len(cl) >= 30 and float(np.mean(cl)) <= 0:
                s["status"], s["basis_kind"] = "wycofana", "wycofana"
                self.hub.playbook_set_status(s["id"], "wycofana", "wycofana")
                self.hub.event("playbook", f"{s['id']} wycofana przez kod: {len(cl)} transakcji, śr. {np.mean(cl):+.2f}% netto", agent=AGENT)

    def active_strategies(self) -> list[dict]:
        return [s for s in self.pb.get("strategies", []) if s.get("status") != "wycofana"]

    # ------------------------------------------------------------ pomocnicze
    def _set(self, doing: str) -> None:
        self.state = {"state": "on", "doing": doing, "since": self.clock()}

    def _note(self, kind: str, text: str, refs=None, agent: str = AGENT) -> None:
        self.hub.note(agent, kind, text, refs, at=self.clock())

    def _fc(self, sig) -> None:
        if sig is None:
            return
        for b in (self.main, self.shadow):
            for p in b.active():
                s = getattr(self, "by_id", {}).get(p.basis)
                if p.kind == "stock" and s and s.get("has_fc") and p.fc_k is None:
                    p.fc_k = sig.fc_key(s, p.inst, p.decided_k)

    def _settle(self, prices: Prices, label: str) -> list[dict]:
        before = {p.id for p in self.main.active()}
        ev = self.main.settle(prices) + self.shadow.settle(prices)
        for e in ev:
            p = e["pos"]
            self.dirty.add((p.book, p.id))
            if p.book != "main":
                continue
            txt = engine.describe(p, prices) + (f" · {label}" if label else "")
            self._note("wejście" if e["kind"] == "entry" else "wyjście", txt, {"pos": p.id}, agent="kod")
            self.hub.event("trade", txt, agent=AGENT)
        self.dirty |= {("main", i) for i in before}
        return ev

    def _risk_state(self, prices: Prices, now: float) -> dict:
        cfg = self.cfg
        snap = self.main.snapshot(prices, now, cfg["capital"])
        eq = snap["equity"]
        self.peak = max(self.peak, eq)
        dd = 100 * (self.peak - eq) / self.peak if self.peak else 0.0
        day = engine.utc_day(now)
        anchor = self.hub.meta("day_anchor") or {}
        if anchor.get("date") != day:
            anchor = {"date": day, "equity": eq}
            self.hub.set_meta("day_anchor", anchor)
        day_pct = 100 * (eq / anchor["equity"] - 1) if anchor.get("equity") else 0.0
        dial = cfg["risk_dial"]
        blocks = []
        if dd >= cfg["dd_half_pct"]:
            dial = min(dial, 0.5)
        if dd >= cfg["dd_stop_pct"] and not self.halt:
            self.halt = {"at": now, "dd": dd}
            self.hub.set_meta("halt", self.halt)
            self.hub.event("halt", f"obsunięcie {dd:.1f}% ≥ {cfg['dd_stop_pct']:.0f}% — bez nowych wejść do decyzji człowieka "
                                   "(ai/config.json → halt_ack)", agent=AGENT)
        if self.halt and cfg.get("halt_ack") and str(cfg["halt_ack"]) >= iso(self.halt["at"]):
            self.hub.event("halt", "człowiek potwierdził wznowienie (halt_ack) — wejścia znów dozwolone", agent=AGENT)
            self.halt = None
            self.hub.set_meta("halt", None)
        if self.halt:
            blocks.append(f"ZATRZYMANIE: obsunięcie {self.halt['dd']:.1f}% od {pl(self.halt['at'])} — czeka na decyzję człowieka")
        if day_pct <= -cfg["daily_stop_pct"]:
            blocks.append(f"STOP DZIENNY: wynik doby UTC {day_pct:.2f}% ≤ −{cfg['daily_stop_pct']:.1f}%")
        self.hub.set_meta("equity_peak", self.peak)
        return {"snap": snap, "equity": eq, "dd": dd, "dayPct": day_pct, "dial": dial, "blocks": blocks}

    # ------------------------------------------------------------ start: rozliczenie przerwy
    def startup(self, prices: Prices, sig=None) -> dict:
        self._set("rozliczenie przerwy")
        self._fc(sig)
        ev = self._settle(prices, "rozliczone po powrocie")
        now = self.clock()
        rs = self._risk_state(prices, now)
        n_in = sum(e["kind"] == "entry" and e["pos"].book == "main" for e in ev)
        n_out = sum(e["kind"] == "exit" and e["pos"].book == "main" for e in ev)
        eq = f"{rs['equity']:,.0f}".replace(",", " ")
        txt = f"rozliczenie przerwy: wejść {n_in}, wyjść {n_out}, pozycji {rs['snap']['positions']} · stan konta {eq} $"
        self.hub.event("investor", txt, agent=AGENT)
        self._persist(prices, rs, None, ev)
        self._set("czeka na świecę")
        return {"entries": n_in, "exits": n_out}

    # ------------------------------------------------------------ kandydaci
    def candidates(self, kind: str, key: int, sig, prices: Prices, forecast: dict | None) -> tuple[list[dict], list[str]]:
        cfg, skipped = self.cfg, []
        out = []
        if kind == "stocks" and sig is not None:
            found = sig.at(self.active_strategies(), key)
            by_inst: dict[str, list] = {}
            for x in found:
                by_inst.setdefault(x["inst"], []).append(x)
            for inst, L in by_inst.items():
                L.sort(key=lambda x: (self.by_id[x["id"]]["priority"], x["id"]))
                top = L[0]
                if self.main.holding(inst):
                    skipped.append(f"{inst} ({top['id']}) — pozycja już otwarta")
                    continue
                s = self.by_id[top["id"]]
                out.append({"inst": inst, "side": top["side"], "basis": s["id"], "basis_kind": s["basis_kind"],
                            "mult": cfg["mult"].get(s["basis_kind"], 0.5), "sl": float(s["sl"]), "tp": float(s["tp"]),
                            "max_bars": s.get("max_bars"), "has_fc": s.get("has_fc", False), "px": top["px"],
                            "atrp": top.get("atrp"), "s": s, "k": top["k"],
                            "also": [f"{x['id']} ({'long' if x['side'] > 0 else 'short'})" for x in L[1:4]]})
        if kind == "fx" and forecast:
            v = (forecast.get("verdict") or {}).get("direction", "")
            if "przewaga" in v and "brak" not in v:
                for I in forecast.get("instruments") or []:
                    chk = I.get("check") or {}
                    last = prices.last(I["id"])
                    if (chk.get("brier48") or 1) >= 0.245 or not I.get("q10") or last is None or last[0] != key:
                        continue
                    pu = (I.get("pUp") or {}).get("48")
                    if pu is None or pu == 0.5 or self.main.holding(I["id"]):
                        continue
                    side = 1 if pu > 0.5 else -1
                    px = float(last[1])
                    sl_px = I["q10"][-1] if side > 0 else I["q90"][-1]
                    tp_px = I["q90"][-1] if side > 0 else I["q10"][-1]
                    sl_pct, tp_pct = 100 * abs(px - sl_px) / px, 100 * abs(tp_px - px) / px
                    if side * (px - sl_px) <= 0 or side * (tp_px - px) <= 0:
                        continue
                    out.append({"inst": I["id"], "side": side, "basis": "fx-prognoza", "basis_kind": "fx_prognoza",
                                "mult": cfg["mult"]["fx_prognoza"], "sl": sl_pct, "tp": tp_pct, "max_bars": cfg["fx_forecast_limit"],
                                "has_fc": False, "px": px, "atrp": None, "s": None, "k": int(last[0]), "also": [],
                                "fc": {"pUp48": pu, "brier48": chk.get("brier48")}})
        prio = lambda c: c["s"]["priority"] if c["s"] else 0
        out.sort(key=lambda c: (prio(c), c["inst"]))
        if len(out) > cfg["max_candidates"]:
            skipped += [f"{c['inst']} ({c['basis']}) — poza 12 najwyższymi" for c in out[cfg["max_candidates"]:]]
            out = out[: cfg["max_candidates"]]
        for i, c in enumerate(out):
            c["ref"] = f"C{i + 1}"
        return out, skipped

    # ------------------------------------------------------------ brief
    def _live(self, sid: str) -> str:
        cl = [p for p in self.main.closed() if p.basis == sid]
        if not cl:
            return "Ty na tej strategii: 0 transakcji"
        x = np.array([p.ret_net_pct for p in cl])
        return f"Ty na tej strategii: {len(cl)} zamkniętych, śr. {x.mean():+.2f}% netto"

    def brief(self, rid: str, kind: str, label: str, close_t: float, cands, skipped, prices: Prices, rs: dict,
              forecast: dict | None) -> tuple[str, list[Pos]]:
        cfg, now = self.cfg, self.clock()
        s, eq = rs["snap"], rs["equity"]
        L = [f"RUNDA {rid} · {'akcje' if kind == 'stocks' else 'FX'} · świeca {label} (zamknięcie {pl(close_t)} PL) · teraz {pl(now)} PL",
             f"PORTFEL: stan konta {eq:.0f} $ (start {cfg['capital']:.0f} $, szczyt {self.peak:.0f} $, obsunięcie {rs['dd']:.2f}%) · "
             f"wynik doby UTC {rs['dayPct']:+.2f}% · zrealizowany {s['realized']:+.0f} $, niezrealizowany {s['unrealized']:+.0f} $ · "
             f"ekspozycja brutto {100 * s['gross'] / eq:.0f}% (limit {cfg['gross_max_pct']:.0f}%) · ryzyko otwarte {100 * s['risk'] / eq:.2f}% "
             f"(budżet {cfg['budget_pct']:.1f}%) · pozycji {s['positions']}/{cfg['max_positions']} · risk_dial {rs['dial']:.2f} · "
             f"własne pomysły: ryzyko {100 * s['ownRisk'] / eq:.2f}% (budżet {cfg['own_budget_pct']:.1f}%)"]
        for b in rs["blocks"]:
            L.append(f"!!! {b} — nowe wejścia zablokowane przez kod.")
        cl = self.main.closed()
        if cl:
            x = np.array([p.ret_net_pct for p in cl])
            ci = 2 * x.std(ddof=1) / np.sqrt(x.size) if x.size > 1 else None
            ex = {r: sum(p.reason == r for p in cl) for r in engine.REASONS}
            L.append(f"WYNIKI DOTĄD: zamkniętych {len(cl)} · śr. {x.mean():+.2f}% netto" +
                     (f" (95%: {x.mean() - ci:+.2f} … {x.mean() + ci:+.2f})" if ci is not None else "") +
                     f" · śr. {np.mean([p.r_mult for p in cl]):+.2f}R · " + " / ".join(f"{k} {v}" for k, v in ex.items() if v))
        else:
            L.append("WYNIKI DOTĄD: brak zamkniętych transakcji")
        poss = [p for p in self.main.active()]
        L.append("POZYCJE:" if poss else "POZYCJE: brak")
        for i, p in enumerate(poss):
            ref = f"P{i + 1}"
            if p.status == "pending":
                L.append(f"{ref} #{p.id} {p.inst} {p.direction} · {p.basis} · OCZEKUJE na open następnej świecy (decyzja {pl(p.decided_at)})")
                continue
            m = self.main.mark(p, prices)
            L.append(f"{ref} #{p.id} {p.inst} {p.direction} · podstawa {p.basis} · otwarta {pl(p.entry_t)} po {px_fmt(prices, p.inst, p.entry_px)} · "
                     f"teraz {px_fmt(prices, p.inst, m['px'])} · wynik {m['pct']:+.2f}% netto ({m['R']:+.2f}R, {m['pnl']:+.0f} $) · "
                     f"SL {px_fmt(prices, p.inst, p.sl_px)} · TP {px_fmt(prices, p.inst, p.tp_px)} · świec {p.bars}"
                     f"{f' z limitu {p.max_bars}' if p.max_bars else ''} · notatka przy wejściu: „{p.note_in[:200]}”")
        if rs["blocks"]:
            L.append("KANDYDACI: brak (wejścia zablokowane)")
        else:
            L.append("KANDYDACI (SL/TP/limit z reguły; cena = zamknięcie świecy sygnału):" if cands else "KANDYDACI: brak")
        for c in ([] if rs["blocks"] else cands):
            dirn = "long" if c["side"] > 0 else "short"
            if c["s"]:
                st, dp, vi = c["s"], c["s"]["dp"], c["s"].get("vi")
                L.append(f"{c['ref']} {c['inst']} {dirn} @ {px_fmt(prices, c['inst'], c['px'])} · {st['id']} [{st['group']}] „{st['desc'].split(' · SL ')[0][:220]}” · "
                         f"SL {c['sl']:.0f}% / TP {c['tp']:.0f}% / limit {c['max_bars'] or 'brak'} · "
                         f"szacunek przewagi {fs(st.get('est_pct'))}%/transakcję{' (wybrana)' if st.get('selected') else ''} · "
                         f"doubleProof: {dp.get('n') or 0} transakcji, śr. {fs(dp.get('avg'))}%, PF {f(dp.get('pf'))}, mediana {f(dp.get('hold'), 0)} świec · "
                         f"mechaniczny inwestor na żywo: " + (f"{vi.get('n') or 0} zamkniętych, śr. {fs(vi.get('avg'))}%" if vi else "brak danych") +
                         f" · {self._live(st['id'])} · ATR14 {f(c['atrp'])}% ceny" + (f" · też sygnał: {', '.join(c['also'])}" if c["also"] else ""))
            else:
                L.append(f"{c['ref']} {c['inst']} {dirn} @ {px_fmt(prices, c['inst'], c['px'])} · prognoza FX z przewagą kierunku: "
                         f"P(wzrost 48) {c['fc']['pUp48']:.2f}, Brier {c['fc']['brier48']:.3f} · SL {c['sl']:.2f}% (granica stożka 80%) / "
                         f"TP {c['tp']:.2f}% / limit {c['max_bars']} świec")
        if skipped:
            L.append("POMINIĘTE PRZEZ KOD: " + "; ".join(skipped[:10]))
        v = (forecast or {}).get("verdict") or {}
        L.append(f"RYNEK FX (kierunek: {v.get('direction') or 'brak prognozy'}; stożek: {v.get('cone') or '—'}):")
        fx = {I["id"]: I for I in (forecast or {}).get("instruments") or []}
        for inst in [s for s in prices.S if prices.kind(s) in ("fx", "crypto")]:
            last = prices.last(inst)
            if last is None:
                continue
            I, a = fx.get(inst, {}), prices.atr14(inst)
            rg = I.get("range") or {}
            pu = (I.get("pUp") or {}).get("48")
            L.append(f"{inst} {px_fmt(prices, inst, last[1])} (świeca {prices.label(inst, last[0])}) · ATR14 {px_fmt(prices, inst, a)}" +
                     (f" · oczekiwany zakres 48 h {px_fmt(prices, inst, rg.get('low'))}–{px_fmt(prices, inst, rg.get('high'))}" if rg else "") +
                     (f" · P(wzrost 48) {pu:.2f}" if pu is not None else ""))
        L.append("REKOMENDACJE MANAGERA: brak (Strategy-Manager od kroku AI-4)")
        L.append("WNIOSKI:")
        for i, x in enumerate(self.hub.lessons_active()[: cfg["lessons_max"]]):
            L.append(f"{i + 1}. {x['text']}")
        return "\n".join(L), poss

    # ------------------------------------------------------------ odpowiedź modelu
    def check(self, obj, cands, poss) -> list[str]:
        err = []
        if not isinstance(obj, dict):
            return ["odpowiedź nie jest obiektem JSON"]
        cr = [c["ref"] for c in cands]
        got = [d.get("ref") for d in obj.get("candidates") or [] if isinstance(d, dict)]
        for r in cr:
            if got.count(r) != 1:
                err.append(f"kandydat {r}: {'brak decyzji' if r not in got else 'kilka decyzji'}")
        err += [f"nieznany kandydat {r}" for r in got if r not in cr]
        pr = [f"P{i + 1}" for i in range(len(poss))]
        gp = [d.get("ref") for d in obj.get("positions") or [] if isinstance(d, dict)]
        for r in pr:
            if gp.count(r) != 1:
                err.append(f"pozycja {r}: {'brak decyzji' if r not in gp else 'kilka decyzji'}")
        err += [f"nieznana pozycja {r}" for r in gp if r not in pr]
        for d in obj.get("positions") or []:
            if isinstance(d, dict) and d.get("action") == "tighten_sl" and not isinstance(d.get("new_sl"), (int, float)):
                err.append(f"pozycja {d.get('ref')}: tighten_sl bez new_sl")
        for d in obj.get("candidates") or []:
            if isinstance(d, dict) and d.get("action") not in ("enter", "skip"):
                err.append(f"kandydat {d.get('ref')}: action musi być enter albo skip")
        if len(obj.get("own_ideas") or []) > self.cfg["own_per_round"]:
            err.append(f"własnych pomysłów najwyżej {self.cfg['own_per_round']}")
        return err

    def _own(self, d: dict, allowed: set, prices: Prices) -> tuple[dict | None, str | None]:
        cfg = self.cfg
        inst = str(d.get("instrument", "")).upper().replace("/", "")
        if inst not in allowed:
            return None, f"instrument {inst} spoza briefu"
        last = prices.last(inst)
        a = prices.atr14(inst)
        if last is None or not a:
            return None, "brak danych instrumentu"
        side = 1 if d.get("direction") == "long" else -1
        px, sl, tp = float(last[1]), float(d.get("sl") or 0), float(d.get("tp") or 0)
        dsl, dtp = side * (px - sl), side * (tp - px)
        if dsl <= 0 or dtp <= 0:
            return None, f"SL/TP po złej stronie ceny {px:g}"
        if dsl < cfg["own_min_sl_atr"] * a:
            return None, f"SL bliżej niż {cfg['own_min_sl_atr']:g} × ATR14 ({a:.6g})"
        rr = dtp / dsl
        if not (cfg["own_rr_min"] - 1e-9 <= rr <= cfg["own_rr_max"] + 1e-9):
            return None, f"TP/SL = {rr:.2f} poza 1:3…3:1"
        mb = int(d.get("max_bars") or 0)
        if not (1 <= mb <= cfg["own_max_bars"]):
            return None, f"max_bars {mb} poza 1…{cfg['own_max_bars']}"
        return {"inst": inst, "side": side, "basis": "own", "basis_kind": "own", "mult": cfg["mult"]["own"],
                "sl": 100 * dsl / px, "tp": 100 * dtp / px, "max_bars": mb, "has_fc": False, "px": px, "k": int(last[0])}, None

    # ------------------------------------------------------------ runda
    def run(self, kind: str, key: int, label: str, close_t: float, prices: Prices, sig=None, forecast: dict | None = None) -> dict:
        cfg, now = self.cfg, self.clock()
        n = int(self.hub.meta("round_n") or 0) + 1
        self.hub.set_meta("round_n", n)
        rid = f"R-{n:04d}"
        self._set(f"runda {rid}: rozliczenie")
        self._fc(sig)
        ev = self._settle(prices, "")
        rs = self._risk_state(prices, now)
        self.auto_withdraw()
        cands, skipped = self.candidates(kind, key, sig, prices, forecast)
        for c in cands:                                            # cienie — każdy kandydat, bez limitów
            q, r, _ = self.shadow.plan(prices, c["inst"], c["side"], c["sl"], c["mult"], cfg["capital"], 1.0, now, limits=False)
            ps = self.shadow.add(prices, round_id=rid, inst=c["inst"], side=c["side"], basis=c["basis"], basis_kind=c["basis_kind"],
                                 decided_k=c["k"], now=now, sl_pct=c["sl"], tp_pct=c["tp"], max_bars=c["max_bars"],
                                 has_fc=c["has_fc"], qty=q, risk=r, mult=c["mult"])
            if c["s"] and c["has_fc"] and sig is not None:
                ps.fc_k = sig.fc_key(c["s"], c["inst"], c["k"])
            self.dirty.add(("shadow", ps.id))
        shown = [] if rs["blocks"] else cands
        record = {"id": rid, "at": iso(now), "kind": kind, "candle": label, "closeAt": iso(close_t),
                  "candidates": [{"ref": c["ref"], "inst": c["inst"], "dir": "long" if c["side"] > 0 else "short", "basis": c["basis"]}
                                 for c in cands], "skipped": skipped, "blocks": rs["blocks"], "decisions": [], "ownIdeas": [],
                  "positions": [], "llm": None, "roundNote": ""}
        if not shown and not self.main.active():
            record["roundNote"] = "brak kandydatów i pozycji — bez modelu" if not cands else "wejścia zablokowane, brak pozycji — bez modelu"
            self._finish(rid, record, prices, rs, ev, now)
            return record
        self._set(f"runda {rid}: brief")
        text, poss = self.brief(rid, kind, label, close_t, shown, skipped, prices, rs, forecast)
        self._set(f"runda {rid}: myśli ({len(shown)} kandydatów, {len(poss)} pozycji)")
        obj, meta = self.llm.ask(AGENT, SYSTEM, text, SCHEMA, lambda o: self.check(o, shown, poss), cfg["temperature_investor"])
        record["llm"] = {k: meta.get(k) for k in ("attempts", "sec", "promptTokens", "evalTokens")}
        record["llm"]["errors"] = meta.get("errors")[:5] if meta.get("errors") else []
        self._set(f"runda {rid}: wykonanie")
        self._execute(rid, record, obj, shown, poss, prices, rs, now, meta)
        self._finish(rid, record, prices, rs, ev, now)
        return record

    def _execute(self, rid, record, obj, cands, poss, prices, rs, now, meta) -> None:
        cfg = self.cfg
        cut = lambda s: str(s or "").strip()[: cfg["note_max"]]
        ok = isinstance(obj, dict)
        if not ok:
            record["roundNote"] = "brak decyzji modelu (" + "; ".join((meta.get("errors") or ["?"])[:2]) + ") — kandydaci pominięci, pozycje bez zmian"
            self.hub.event("error", f"{rid}: {record['roundNote']}", agent=AGENT)
        cd = {d.get("ref"): d for d in (obj.get("candidates") or [] if ok else []) if isinstance(d, dict)}
        pdx = {d.get("ref"): d for d in (obj.get("positions") or [] if ok else []) if isinstance(d, dict)}
        for c in cands:
            d = cd.get(c["ref"]) or {"action": "skip", "confidence": None, "note": "brak decyzji modelu"}
            act, conf, note = d.get("action"), d.get("confidence"), cut(d.get("note"))
            conf = int(conf) if isinstance(conf, (int, float)) else None
            outcome, pid = "pominięte", None
            if act == "enter":
                snap = self.main.snapshot(prices, now, cfg["capital"])
                q, r, why = self.main.plan(prices, c["inst"], c["side"], c["sl"], c["mult"], snap["equity"], rs["dial"], now, snap=snap)
                if why:
                    outcome = f"odrzucone przez kod: {why}"
                else:
                    p = self.main.add(prices, round_id=rid, inst=c["inst"], side=c["side"], basis=c["basis"], basis_kind=c["basis_kind"],
                                      decided_k=c["k"], now=now, sl_pct=c["sl"], tp_pct=c["tp"], max_bars=c["max_bars"],
                                      has_fc=c["has_fc"], qty=q, risk=r, mult=c["mult"], confidence=conf, note=note)
                    self.dirty.add(("main", p.id))
                    pid = p.id
                    outcome = f"wykonano: #{p.id} oczekuje na open następnej świecy · ryzyko {r:.0f} $"
            self._decision(rid, record, c["ref"], c["inst"], c["side"], c["basis"], act, conf, note, outcome, pid, now)
        for i, p in enumerate(poss):
            ref = f"P{i + 1}"
            d = pdx.get(ref) or {"action": "hold", "note": "brak decyzji modelu"}
            act, note = d.get("action"), cut(d.get("note"))
            outcome = "bez zmian"
            if act == "close":
                why = self.main.request_close(p, note)
                outcome = f"odrzucone przez kod: {why}" if why else "zamknięcie po open następnej świecy"
            elif act == "tighten_sl":
                old = p.sl_px
                why = self.main.tighten(p, float(d.get("new_sl") or 0), prices, note, now)
                outcome = f"odrzucone przez kod: {why}" if why else f"SL {px_fmt(prices, p.inst, old)} → {px_fmt(prices, p.inst, p.sl_px)}"
            self.dirty.add(("main", p.id))
            self._decision(rid, record, ref, p.inst, p.side, p.basis, act, None, note, outcome, p.id, now, kind="positions")
        allowed = {c["inst"] for c in cands} | {s for s in prices.S if prices.kind(s) in ("fx", "crypto")}
        for d in (obj.get("own_ideas") or [] if ok else [])[: cfg["own_per_round"]]:
            if not isinstance(d, dict):
                continue
            note, conf = cut(d.get("note")), d.get("confidence")
            conf = int(conf) if isinstance(conf, (int, float)) else None
            c, why = self._own(d, allowed, prices)
            pid, inst = None, str(d.get("instrument", ""))
            side = 1 if d.get("direction") == "long" else -1
            if c and rs["blocks"]:
                why = rs["blocks"][0]
            if c and not why:
                snap = self.main.snapshot(prices, now, cfg["capital"])
                q, r, why = self.main.plan(prices, c["inst"], side, c["sl"], c["mult"], snap["equity"], rs["dial"], now, own=True, snap=snap)
                if not why:
                    p = self.main.add(prices, round_id=rid, inst=c["inst"], side=side, basis="own", basis_kind="own", decided_k=c["k"],
                                      now=now, sl_pct=c["sl"], tp_pct=c["tp"], max_bars=c["max_bars"], has_fc=False, qty=q, risk=r,
                                      mult=c["mult"], confidence=conf, note=note)
                    self.dirty.add(("main", p.id))
                    pid = p.id
            outcome = f"odrzucone przez kod: {why}" if why else f"wykonano: #{pid} oczekuje na open następnej świecy"
            self._decision(rid, record, "own", inst, side, "own", "enter", conf, note, outcome, pid, now, kind="ownIdeas",
                           extra={"sl": d.get("sl"), "tp": d.get("tp"), "max_bars": d.get("max_bars")})
        if ok:
            record["roundNote"] = cut(obj.get("round_note")) or record["roundNote"]
            if meta.get("errors"):
                record["roundNote"] += f" [kod: odpowiedź poprawiona — {meta['errors'][0]}]"
        self._note("runda", f"{rid}: {record['roundNote']}", {"round": rid})

    def _decision(self, rid, record, ref, inst, side, basis, action, conf, note, outcome, pid, now, kind="decisions", extra=None):
        self.hub.decision(round_id=rid, at=now, ref=ref, inst=inst, side=side, basis=basis, action=action, confidence=conf,
                          note=note, outcome=outcome, pos_id=pid)
        row = {"ref": ref, "inst": inst, "dir": "long" if side > 0 else "short", "basis": basis, "action": action,
               "confidence": conf, "note": note, "outcome": outcome, "pos": pid}
        if extra:
            row.update(extra)
        record[kind].append(row)
        verb = {"enter": "WCHODZĘ", "skip": "pomijam", "hold": "trzymam", "close": "ZAMYKAM", "tighten_sl": "zacieśniam SL"}.get(action, action)
        label = "własny pomysł" if ref == "own" else ref
        self._note("decyzja" if kind != "positions" else "pozycja",
                   f"{label} {inst} {row['dir']} ({basis}): {verb}" + (f" · pewność {conf}" if conf is not None else "") +
                   f" · {note}" + ("" if outcome in ("pominięte", "bez zmian") else f" → {outcome}"), {"round": rid, "pos": pid})

    # ------------------------------------------------------------ zapis
    def _finish(self, rid, record, prices, rs, ev, now) -> None:
        rs = self._risk_state(prices, now)                 # po decyzjach (oczekujące w ekspozycji)
        self.hub.round_save(rid, now, record["kind"], record["candle"], record)
        self._persist(prices, rs, record, ev)
        n_in = sum(1 for d in record["decisions"] if d["outcome"].startswith("wykonano"))
        self.hub.event("round", f"{rid} {record['candle']}: kandydatów {len(record['candidates'])}, wejść {n_in}"
                                f"{', model ' + str(round(record['llm']['sec'])) + ' s' if record.get('llm') else ''} · {record['roundNote'][:140]}",
                       agent=AGENT)
        self._set("czeka na świecę")

    def _persist(self, prices: Prices, rs: dict, record: dict | None, ev: list) -> None:
        now = self.clock()
        allp = {(p.book, p.id): p for p in self.main.pos + self.shadow.pos}
        self.hub.save_positions([allp[k] for k in self.dirty if k in allp])
        self.dirty = set()
        self.hub.equity_point(now, record["id"] if record else "start", rs["snap"], rs["dial"], rs["dd"])
        b = bench.compute(self.main, self.shadow, prices, self.started_at, self.mech)
        self.public = self._public(prices, rs, record, b)
        closed_now = [e["pos"] for e in ev if e["kind"] == "exit" and e["pos"].book == "main"]
        if self.out is not None:
            try:
                self.out.save(self, record, closed_now, b, prices)
            except Exception as e:
                self.hub.event("error", f"branch ai: {type(e).__name__}: {e}", agent=AGENT)
        if self.xlsx is not None:
            try:
                self.xlsx(self, b, prices)
            except Exception as e:
                self.hub.event("error", f"AI-INVESTOR.xlsx: {type(e).__name__}: {e}", agent=AGENT)
                self.log(traceback.format_exc())

    # ------------------------------------------------------------ dla status.json i strony
    def position_row(self, p: Pos, prices: Prices) -> dict:
        m = self.main.mark(p, prices) if p.status == "open" else {"px": None, "pnl": None, "pct": None, "R": None}
        return {"no": p.id, "inst": p.inst, "kind": p.kind, "dir": p.direction, "basis": p.basis, "status": p.status,
                "decidedAt": iso(p.decided_at), "entryAt": iso(p.entry_t), "entry": p.entry_px, "ref": p.ref_px,
                "sl": p.sl_px, "tp": p.tp_px, "slPct": round(p.sl_pct, 3), "tpPct": round(p.tp_pct, 3), "price": m["px"],
                "pnl": m["pnl"], "pct": m["pct"], "R": m["R"], "bars": p.bars, "maxBars": p.max_bars, "risk": p.risk_usd,
                "value": p.value_usd, "confidence": p.confidence, "note": p.note_in[:400], "closeReq": p.close_req,
                "digits": prices.digits(p.inst) if p.kind != "stock" else 2}

    def _public(self, prices, rs, record, b) -> dict:
        s, eq = rs["snap"], rs["equity"]
        cl = self.main.closed()
        return {
            "startedAt": iso(self.started_at), "capital": self.cfg["capital"],
            "portfolio": {"equity": eq, "realized": s["realized"], "unrealized": s["unrealized"], "peak": self.peak, "ddPct": rs["dd"],
                          "dayPct": rs["dayPct"], "grossPct": 100 * s["gross"] / eq, "riskPct": 100 * s["risk"] / eq,
                          "ownRiskPct": 100 * s["ownRisk"] / eq, "positions": s["positions"], "open": s["open"],
                          "pending": s["pending"], "dial": rs["dial"], "blocks": rs["blocks"], "closed": len(cl),
                          "costs": sum(p.cost_in_usd + p.cost_out_usd for p in cl)},
            "positions": [self.position_row(p, prices) for p in self.main.active()],
            "lastRound": record and {k: record[k] for k in ("id", "at", "kind", "candle", "candidates", "skipped", "blocks",
                                                             "decisions", "ownIdeas", "positions", "llm", "roundNote")},
            "bench": b,
        }

    def status(self) -> dict:
        return {"id": "investor", "state": "on", "doing": self.state["doing"], "since": iso(self.state["since"]),
                "llm": getattr(self.llm, "last", None) or None}
