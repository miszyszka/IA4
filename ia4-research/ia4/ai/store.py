"""
IA 4 — branch `ai`: trwała historia AI Investor i odtworzenie huba (instrukcja, sekcje 11c.1 p. 8, 11c.11).
Wersja projektu: 1.36 (2026-10-13) — musi zgadzać się z IA4_INSTRUKCJA.md

Klon w ia4-research/ai-repo/ (poza gitem głównego repo). Pisze wyłącznie Python z Maca; człowiek
(z Claude) zmienia tylko ai/config.json. Commit i push po każdej rundzie Inwestora.

  python -m ia4.ai.restore     # hub od nowa z brancha `ai` (gdy data/ai/hub.sqlite zginął) — też automatycznie
                               # przy starcie, gdy hub jest pusty, a branch ma ai/state.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .. import __version__
from .. import config as base_config
from ..lab.store import ResultsRepo
from .market import iso

README = """# IA 4 — AI Investor (branch `ai`)

Ten branch zapisuje wyłącznie Python z Maca (`ia4 start`). Zasady: `IA4_INSTRUKCJA.md` na branchu `main`, sekcja 11c.
Ręcznie (człowiek z Claude) zmienia się tylko `ai/config.json` — nadpisania limitów i ustawień (klucze: `ia4/ai/config.py`).

- `ai/trades.jsonl` — zamknięta transakcja Agent-Investora = wiersz (wejście, wyjście, powód, wynik netto, koszty, notatki, pewność)
- `ai/decisions.jsonl` — runda = wiersz (kandydaci, decyzje modelu z notatkami, odrzucenia przez kod, notatka rundy)
- `ai/shadow.jsonl` — zamknięty cień (każdy kandydat bez limitów — punkt odniesienia „wszyscy kandydaci”)
- `ai/state.json` — otwarte i oczekujące pozycje, szczyt stanu konta, liczniki (odtworzenie huba)
- `ai/playbook.json` — strategie, których Inwestor może używać, ze statusem i wynikami na żywo
- `ai/benchmarks.json` — punkty odniesienia (11c.10)
- `ai/lessons.json` — aktywne wnioski
- `ai/config.json` — nadpisania ustawień
"""


def trade_row(p) -> dict:
    return {"no": p.id, "round": p.round_id, "inst": p.inst, "kind": p.kind, "dir": p.direction, "basis": p.basis,
            "basisKind": p.basis_kind, "mult": p.mult, "confidence": p.confidence, "decidedAt": iso(p.decided_at),
            "entryAt": iso(p.entry_t), "entry": p.entry_px, "sl": p.sl_px, "tp": p.tp_px, "slPct": p.sl_pct, "tpPct": p.tp_pct,
            "qty": p.qty, "valueUsd": p.value_usd, "riskUsd": p.risk_usd, "maxBars": p.max_bars, "exitAt": iso(p.exit_t),
            "exit": p.exit_px, "reason": p.reason, "gap": p.gap, "bars": p.bars, "costUsd": p.cost_in_usd + p.cost_out_usd,
            "pnlGrossUsd": p.pnl_gross_usd, "pnlUsd": p.pnl_net_usd, "retPct": p.ret_net_pct, "R": p.r_mult,
            "noteIn": p.note_in, "noteOut": p.note_out, "slMoves": p.sl_moves}


class AiStore:
    def __init__(self, push: bool = True, root: Path | None = None):
        self.repo = ResultsRepo(root or base_config.RESEARCH_DIR / "ai-repo", push=push, branch="ai", subdir="ai", readme=README)
        self.repo.ensure()
        if not (self.repo.dir / "config.json").exists():
            self.repo.write_json("config.json", {})
            if not (self.repo.dir / "README.md").exists():
                (self.repo.dir / "README.md").write_text(README, encoding="utf-8")
            self.repo.commit_push("ai: nowy branch AI Investor")
        self.saved_shadow: set = set()

    @property
    def config_path(self) -> Path:
        return self.repo.dir / "config.json"

    def pull(self) -> None:
        self.repo.pull()

    def save(self, inv, record, closed_now, bench, prices) -> bool:
        r = self.repo
        if record:
            r.append_jsonl("decisions.jsonl", record)
        for p in closed_now:
            r.append_jsonl("trades.jsonl", trade_row(p))
        for p in inv.shadow.closed():
            if p.id not in self.saved_shadow:
                if not self._has_shadow(p.id):
                    r.append_jsonl("shadow.jsonl", {"no": p.id, "round": p.round_id, "inst": p.inst, "dir": p.direction,
                                                    "basis": p.basis, "entryAt": iso(p.entry_t), "exitAt": iso(p.exit_t),
                                                    "reason": p.reason, "retPct": p.ret_net_pct, "R": p.r_mult, "data": p.to_dict()})
                self.saved_shadow.add(p.id)
        r.write_json("state.json", {
            "version": __version__, "savedAt": iso(time.time()), "startedAt": iso(inv.started_at), "peak": inv.peak,
            "halt": inv.halt, "roundN": inv.hub.meta("round_n"), "dayAnchor": inv.hub.meta("day_anchor"),
            "positions": [p.to_dict() for p in inv.main.active() + inv.shadow.active()]})
        r.write_json("benchmarks.json", bench)
        r.write_json("lessons.json", inv.hub.lessons_active())
        r.write_json("playbook.json", playbook_view(inv))
        msg = f"ai: {record['id']} {record['candle']}" if record else "ai: rozliczenie przerwy"
        if closed_now:
            msg += " · zamknięte: " + ", ".join(f"#{p.id} {p.inst} {p.reason}" for p in closed_now[:5])
        return r.commit_push(msg)

    def _has_shadow(self, pid: int) -> bool:
        if not hasattr(self, "_shadow_ids"):
            self._shadow_ids = set()
            p = self.repo.dir / "shadow.jsonl"
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    try:
                        self._shadow_ids.add(json.loads(line)["no"])
                    except (ValueError, KeyError):
                        pass
        return pid in self._shadow_ids


def playbook_view(inv) -> dict:
    out = []
    for s in inv.pb.get("strategies", []):
        cl = [p for p in inv.main.closed() if p.basis == s["id"]]
        out.append({k: s.get(k) for k in ("id", "priority", "status", "basis_kind", "selected", "group", "desc", "direction", "sl", "tp",
                                          "max_bars", "est_pct", "dp", "vi", "search")} |
                   {"mult": inv.cfg["mult"].get(s["basis_kind"]), "ai": {"n": len(cl), "usd": sum(p.pnl_net_usd for p in cl),
                                                                       "avg": (sum(p.ret_net_pct for p in cl) / len(cl)) if cl else None}})
    return {"builtAt": iso(inv.pb.get("builtAt")), "source": inv.pb.get("source"), "strategies": out}


# ===========================================================================
#  Odtworzenie huba z brancha `ai`
# ===========================================================================
def restore(hub, repo_dir: Path, log=print) -> bool:
    from .engine import Pos
    st_path = repo_dir / "state.json"
    if not st_path.exists():
        return False
    st = json.loads(st_path.read_text(encoding="utf-8"))
    pos = [Pos.from_dict(d) for d in st.get("positions") or []]
    n_tr = n_sh = 0
    tp = repo_dir / "trades.jsonl"
    if tp.exists():
        for line in tp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            t = json.loads(line)
            pos.append(_pos_from_trade(t))
            n_tr += 1
    sp = repo_dir / "shadow.jsonl"
    if sp.exists():
        for line in sp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                pos.append(Pos.from_dict(json.loads(line)["data"]))
                n_sh += 1
    hub.save_positions(pos)
    from datetime import datetime
    ts = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None
    hub.set_meta("investor_started_at", ts(st.get("startedAt")))
    hub.set_meta("equity_peak", st.get("peak"))
    hub.set_meta("halt", st.get("halt"))
    hub.set_meta("round_n", st.get("roundN") or 0)
    hub.set_meta("day_anchor", st.get("dayAnchor"))
    lp = repo_dir / "lessons.json"
    if lp.exists() and not hub.lessons_active():
        for x in json.loads(lp.read_text(encoding="utf-8")):
            hub.lesson_add(x.get("author", "?"), x["text"], x.get("at"))
    hub.event("restore", f"hub odtworzony z brancha ai: pozycji aktywnych {len(st.get('positions') or [])}, "
                         f"transakcji {n_tr}, cieni {n_sh}")
    log(f"  hub odtworzony z brancha ai: aktywnych {len(st.get('positions') or [])}, transakcji {n_tr}, cieni {n_sh}")
    return True


def _pos_from_trade(t: dict):
    from datetime import datetime
    from .engine import Pos
    ts = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None
    return Pos(id=t["no"], book="main", round_id=t["round"], inst=t["inst"], kind=t["kind"], side=1 if t["dir"] == "long" else -1,
               basis=t["basis"], basis_kind=t.get("basisKind", ""), decided_k=0, decided_at=ts(t["decidedAt"]) or 0,
               sl_pct=t["slPct"], tp_pct=t["tpPct"], max_bars=t.get("maxBars"), has_fc=False, qty=t["qty"], ref_px=t["entry"],
               risk_usd=t["riskUsd"], mult=t.get("mult") or 0, confidence=t.get("confidence"), note_in=t.get("noteIn", ""),
               status="closed", entry_t=ts(t["entryAt"]), entry_px=t["entry"], sl_px=t["sl"], tp_px=t["tp"], value_usd=t["valueUsd"],
               cost_in_usd=t["costUsd"], bars=t["bars"], note_out=t.get("noteOut", ""), sl_moves=t.get("slMoves") or [],
               exit_t=ts(t["exitAt"]), exit_px=t["exit"], reason=t["reason"], gap=t.get("gap", False),
               pnl_gross_usd=t.get("pnlGrossUsd", 0.0), pnl_net_usd=t["pnlUsd"], ret_net_pct=t["retPct"], r_mult=t["R"])


def main() -> None:
    from .hub import Hub
    from .lock import holder
    if holder():
        raise SystemExit("Działa `ia4 start` — zatrzymaj go przed odtwarzaniem huba.")
    h = Hub()
    if h.db.execute("SELECT COUNT(*) FROM positions").fetchone()[0]:
        raise SystemExit("Hub ma już pozycje — odtworzenie tylko do pustego huba (usuń data/ai/hub.sqlite, jeśli na pewno).")
    s = AiStore(push=True)
    s.pull()
    ok = restore(h, s.repo.dir)
    print("Gotowe." if ok else "Branch ai nie ma state.json — nie ma czego odtwarzać.")


if __name__ == "__main__":
    main()
