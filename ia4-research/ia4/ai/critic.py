"""
IA 4 — Krytyk: weryfikuje Inwestora i Badacza, ustawia poziom nauki (instrukcja, sekcja 8 — „Krytyk”).
Wersja projektu: 1.44 (2026-10-15) — musi zgadzać się z IA4_INSTRUKCJA.md

Kiedy (dyspozytor): po `critic_every_rounds` rundach Inwestora z modelem, po `critic_every_min` minutach
(jeśli coś się wydarzyło) albo od razu, gdy czekają ≥ 3 hipotezy „do oceny”.

Brief (kod): aktywność Inwestora (rundy, wejścia, pominięcia, własne pomysły i powody odrzuceń), wynik
pominiętych kandydatów (cienie) wobec wejść, własne pomysły z hipotezami i wynikiem, kalibracja pewności,
hipotezy Badacza „do oceny” i „w próbie”, wnioski. Model odpowiada JSON-em; kod pilnuje granic:
  • poziom nauki 0–3, zmiana najwyżej o 1 na przegląd,
  • „próba” tylko dla hipotezy „do oceny” i najwyżej `hyp_trial_max` naraz,
  • „zatwierdzona” / „wycofana” tylko po ≥ `hyp_live_min` transakcjach na żywo; zatwierdzenie wymaga średniej > 0,
  • wnioski: najwyżej 2 nowe na przegląd, najwyżej `lessons_max` aktywnych.
"""

from __future__ import annotations

import time
from collections import Counter

import numpy as np

from . import config as aicfg
from . import research
from .market import iso

AGENT = "critic"

SYSTEM = """Jesteś Krytyk w systemie IA 4. Weryfikujesz pracę dwóch agentów: Agent-Investora (papierowy portfel, tryb nauki) i Badacza (hipotezy liczone przez Python). Twoje zadanie: żeby system się uczył — więcej sensownych prób, mniej powtarzania błędów.

Zasady:
1. Wszystkie liczby policzył kod. Nie wymyślaj liczb. Mało transakcji = słaby dowód (podawaj n).
2. explore (0–3) — poziom śmiałości Inwestora: 0 ostrożnie, 1 normalnie, 2 śmielej, 3 nauka wymuszona (co najmniej jedno wejście w rundzie). Inwestor bierny (dużo rund bez wejścia, pominięci kandydaci zarobiliby) → podnieś. Inwestor traci na pochopnych wejściach (wyraźnie ujemny wynik przy n ≥ 20) → obniż. Kod zmienia poziom najwyżej o 1.
3. investor_notes — najwyżej 3 krótkie, konkretne uwagi dla Inwestora (co robić inaczej w następnych rundach).
4. verdicts — dla hipotez z listy DO OCENY: "próba" (warta sprawdzenia na żywo małym ryzykiem), "odrzucona" (np. sztuczna, za mało niezależnych przypadków, przypadek przy tylu próbach) albo "popraw" (z uwagą, co zmienić). Dla hipotez W PRÓBIE z n ≥ wymaganego: "zatwierdzona" albo "wycofana". Każdy werdykt z notatką.
5. researcher_notes — najwyżej 3 kierunki dla Badacza (co badać, czego unikać).
6. lessons_add — najwyżej 2 nowe wnioski (zdanie, trwała wiedza); lessons_remove — numery wniosków nieaktualnych albo blokujących naukę.
7. summary — 2–4 zdania: co działa, co nie, co dalej.
Odpowiadasz wyłącznie JSON-em zgodnym ze schematem."""

SCHEMA = {
    "type": "object",
    "properties": {
        "explore": {"type": "integer", "minimum": 0, "maximum": 3},
        "explore_reason": {"type": "string"},
        "investor_notes": {"type": "array", "items": {"type": "string"}},
        "verdicts": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"},
            "verdict": {"type": "string", "enum": ["próba", "odrzucona", "popraw", "zatwierdzona", "wycofana"]},
            "note": {"type": "string"}}, "required": ["id", "verdict", "note"]}},
        "researcher_notes": {"type": "array", "items": {"type": "string"}},
        "lessons_add": {"type": "array", "items": {"type": "string"}},
        "lessons_remove": {"type": "array", "items": {"type": "integer"}},
        "summary": {"type": "string"},
    },
    "required": ["explore", "explore_reason", "investor_notes", "verdicts", "researcher_notes", "lessons_add", "lessons_remove",
                 "summary"],
}


def _st(x) -> str:
    x = np.asarray(list(x), float)
    if not x.size:
        return "n 0"
    ci = 2 * x.std(ddof=1) / np.sqrt(x.size) if x.size > 1 else None
    return f"n {x.size}, śr. {x.mean():+.2f}% netto" + (f" (±{ci:.2f})" if ci is not None else "") + f", zyskownych {100 * (x > 0).mean():.0f}%"


class Critic:
    def __init__(self, cfg: dict, hub, llm, inv, clock=time.time, log=print):
        self.cfg, self.hub, self.llm, self.inv, self.clock, self.log = cfg, hub, llm, inv, clock, log
        self.state = {"state": "on", "doing": "czeka na przegląd", "since": clock()}
        self.fail_until = 0.0
        self.started = clock()

    def _set(self, doing: str) -> None:
        self.state = {"state": "on", "doing": doing, "since": self.clock()}

    def last(self) -> float:
        rv = self.hub.reviews(1)
        return float(rv[0]["at"]) if rv else 0.0

    def since(self) -> float:
        """Od kiedy liczyć „pora na przegląd”: ostatni przegląd, ale nie wcześniej niż start tego uruchomienia."""
        return max(self.last(), self.started)

    def due(self) -> bool:
        now = self.clock()
        if now < self.fail_until:
            return False
        last = self.since()
        rounds = [r for r in self.hub.rounds(300) if _ts(r.get("at")) > last]
        model_rounds = sum(1 for r in rounds if r.get("llm"))
        new_hyp = sum(1 for h in self.hub.hypotheses(50) if (h.get("updated") or 0) > last)
        waiting = self.hub.hyp_count("do oceny")
        if waiting >= 3 or model_rounds >= int(self.cfg["critic_every_rounds"]):
            return True
        return (now - last) >= 60 * float(self.cfg["critic_every_min"]) and (rounds or new_hyp)

    # ------------------------------------------------------------ brief
    def brief(self) -> tuple[str, dict]:
        inv, hub, cfg = self.inv, self.hub, self.cfg
        last = self.last()
        ex = inv.explore()
        rounds = [r for r in hub.rounds(300) if _ts(r.get("at")) > last] or hub.rounds(12)
        dec = [d for r in rounds for d in r.get("decisions") or []]
        own = [d for r in rounds for d in r.get("ownIdeas") or []]
        L = [f"PRZEGLĄD · od {'ostatniego przeglądu' if last else 'startu'} · rund Inwestora {len(rounds)} "
             f"(z modelem {sum(1 for r in rounds if r.get('llm'))})",
             f"POZIOM NAUKI teraz {ex['level']} ({ex['name']}; ustawiony {ex['base']} przez {ex['by']}) · rund z rzędu bez wejścia: "
             f"{ex['passive']} (automat bierności podnosi poziom do 2 po {cfg['passive_rounds']}, do 3 po {2 * cfg['passive_rounds']})",
             f"KANDYDACI: zaproponowani {len(dec)} · enter {sum(d['action'] == 'enter' for d in dec)} "
             f"(wykonane {sum(d['outcome'].startswith('wykonano') for d in dec)}) · skip {sum(d['action'] == 'skip' for d in dec)}",
             f"WŁASNE POMYSŁY: zgłoszone {len(own)} · wykonane {sum(d['outcome'].startswith('wykonano') for d in own)}" +
             (" · odrzucone przez kod: " + "; ".join(f"{k} ×{v}" for k, v in Counter(
                 d["outcome"].replace("odrzucone przez kod: ", "")[:60] for d in own if d["outcome"].startswith("odrzucone")).most_common(3))
              if any(d["outcome"].startswith("odrzucone") for d in own) else "")]
        # pominięci a wejścia (cienie: każdy kandydat bez limitów)
        acts = {(d["round_id"], d["inst"]): d["action"] for d in hub.decisions(5000) if d["ref"] not in ("own",) and d["action"] in ("enter", "skip")}
        sh = inv.shadow.closed()
        sk = [p.ret_net_pct for p in sh if acts.get((p.round_id, p.inst)) == "skip"]
        en = [p.ret_net_pct for p in sh if acts.get((p.round_id, p.inst)) == "enter"]
        L.append(f"POMINIĘCI KANDYDACI — gdyby wszedł (cienie zamknięte): {_st(sk)}")
        L.append(f"KANDYDACI, W KTÓRYCH WSZEDŁ (te same cienie): {_st(en)}")
        cl = inv.main.closed()
        L.append(f"TRANSAKCJE INWESTORA (zamknięte, wszystkie): {_st(p.ret_net_pct for p in cl)} · "
                 f"własne pomysły: {_st(p.ret_net_pct for p in cl if p.basis == 'own')}")
        for p in [p for p in cl if p.basis == "own"][-8:]:
            L.append(f"- własny #{p.id} {p.inst} {p.direction}: {p.ret_net_pct:+.2f}% ({p.reason}, {p.bars} świec) · "
                     f"pewność {p.confidence} · hipoteza: {p.hypothesis[:160] or '—'}")
        for p in [p for p in cl if p.basis != "own"][-5:]:
            L.append(f"- #{p.id} {p.inst} {p.direction} ({p.basis}): {p.ret_net_pct:+.2f}% ({p.reason}) · {p.note_in[:120]}")
        cal = ((inv.public or {}).get("bench") or {}).get("calibration") or []
        if cal:
            L.append("KALIBRACJA PEWNOŚCI: " + " · ".join(f"pewność {c['from']}–{c['to']}: n {c['n']}, zyskownych {100 * c['win']:.0f}%" for c in cal))
        act = inv.main.active()
        L.append(f"POZYCJE OTWARTE: {len(act)}" + (" · " + ", ".join(f"{p.inst} {p.direction} ({p.basis})" for p in act[:8]) if act else ""))
        todo = hub.hypotheses(6, statuses=("do oceny",))
        L.append("DO OCENY (hipotezy Badacza po sicie kodu):" if todo else "DO OCENY: brak")
        for h in todo:
            L.append(f"{h['id']} {research.describe(h)} · pomysł: {h.get('idea', '')[:200]} · {research.res_line(h.get('result'))} · "
                     f"instrumentów z transakcjami {(h.get('result') or {}).get('insts')}")
        live = hub.hypotheses(20, statuses=("próba", "zatwierdzona"))
        L.append("W PRÓBIE / ZATWIERDZONE (na żywo):" if live else "W PRÓBIE: brak")
        for h in live:
            r = [p.ret_net_pct for p in cl if p.basis == h["id"]]
            L.append(f"{h['id']} [{h['status']}] {research.describe(h)} · na żywo {_st(r)} (werdykt możliwy od n {cfg['hyp_live_min']})")
        c = hub.hyp_counts()
        L.append(f"BADACZ: hipotez łącznie {sum(c.values())} · " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())) +
                 " — przy tylu próbach część wyników „do oceny” to przypadek.")
        L.append("WNIOSKI (numer: treść):")
        L += [f"{x['id']}: {x['text']}" for x in hub.lessons_active()]
        ctx = {"todo": {h["id"] for h in todo}, "live": {h["id"]: [p.ret_net_pct for p in cl if p.basis == h["id"]] for h in live},
               "lessons": {x["id"] for x in hub.lessons_active()}, "explore": ex}
        return "\n".join(L), ctx

    # ------------------------------------------------------------ przegląd
    def review(self) -> dict:
        self._set("pisze przegląd")
        text, ctx = self.brief()
        obj, meta = self.llm.ask(AGENT, SYSTEM, text, SCHEMA, self._check, float(self.cfg["temperature_critic"]))
        if not isinstance(obj, dict):
            self.fail_until = self.clock() + 600
            self._set("czeka (model niedostępny — ponowi za 10 min)")
            return {"ok": False, "summary": "brak odpowiedzi modelu: " + "; ".join((meta.get("errors") or ["?"])[:1])}
        applied = self.apply(obj, ctx)
        self._set("czeka na przegląd")
        return {"ok": True, "summary": applied["summary_line"]}

    def _check(self, obj) -> list[str]:
        if not isinstance(obj, dict):
            return ["odpowiedź nie jest obiektem JSON"]
        err = []
        if not isinstance(obj.get("explore"), int) or not 0 <= obj["explore"] <= 3:
            err.append("explore musi być liczbą całkowitą 0–3")
        return err

    def apply(self, obj: dict, ctx: dict) -> dict:
        hub, cfg, now = self.hub, self.cfg, self.clock()
        ex = ctx["explore"]
        want = int(obj.get("explore", ex["base"]))
        new = max(ex["base"] - 1, min(ex["base"] + 1, want))
        reason = str(obj.get("explore_reason") or "")[:300]
        if new != ex["base"] or not hub.meta("explore"):
            hub.set_meta("explore", {"level": new, "by": "Krytyk", "reason": reason, "at": now})
        else:
            hub.set_meta("explore", dict(hub.meta("explore"), reason=reason, at=now))
        verdicts = []
        trial = hub.hyp_count("próba")
        for v in obj.get("verdicts") or []:
            if not isinstance(v, dict):
                continue
            hid, vd, note = str(v.get("id")), v.get("verdict"), str(v.get("note") or "")[:400]
            h = hub.hyp_get(hid)
            why = None
            if h is None:
                why = "nieznana hipoteza"
            elif vd in ("próba", "odrzucona", "popraw"):
                if h["status"] != "do oceny":
                    why = f"status {h['status']} — werdykt tylko dla „do oceny”"
                elif vd == "próba" and trial >= int(cfg["hyp_trial_max"]):
                    why = f"w próbie jest już {trial} (limit {cfg['hyp_trial_max']})"
            elif vd in ("zatwierdzona", "wycofana"):
                r = ctx["live"].get(hid)
                if r is None:
                    why = "werdykt tylko dla hipotezy w próbie"
                elif len(r) < int(cfg["hyp_live_min"]):
                    why = f"na żywo {len(r)} < {cfg['hyp_live_min']} transakcji"
                elif vd == "zatwierdzona" and float(np.mean(r)) <= 0:
                    why = "średni wynik na żywo ≤ 0"
            else:
                why = "nieznany werdykt"
            if why:
                verdicts.append({"id": hid, "verdict": vd, "note": note, "applied": False, "why": why})
                continue
            status = {"popraw": "do poprawy"}.get(vd, vd)
            hub.hyp_update(hid, status=status, verdict=vd, verdict_note=note, verdict_at=now)
            if vd == "próba":
                trial += 1
            verdicts.append({"id": hid, "verdict": vd, "note": note, "applied": True})
            hub.event("hypothesis", f"{hid}: Krytyk → {status} · {note[:120]}", agent=AGENT)
        removed = [int(i) for i in obj.get("lessons_remove") or [] if int(i) in ctx["lessons"] and hub.lesson_remove(int(i))]
        added = []
        for t in (obj.get("lessons_add") or [])[:2]:
            t = str(t).strip()[:400]
            if t and len(hub.lessons_active()) < int(cfg["lessons_max"]):
                added.append(hub.lesson_add("Krytyk", t, at=now))
        rec = {"explore": new, "exploreWanted": want, "exploreReason": reason,
               "investor_notes": [str(x)[:300] for x in (obj.get("investor_notes") or [])[:3]],
               "researcher_notes": [str(x)[:300] for x in (obj.get("researcher_notes") or [])[:3]],
               "verdicts": verdicts, "lessonsAdded": added, "lessonsRemoved": removed, "summary": str(obj.get("summary") or "")[:800]}
        hub.review_add(rec, at=now)
        ok_v = [v for v in verdicts if v["applied"]]
        line = (f"poziom nauki {ex['base']}→{new} · werdyktów {len(ok_v)}"
                + (" (" + ", ".join(f"{v['id']} {v['verdict']}" for v in ok_v[:4]) + ")" if ok_v else "")
                + f" · wnioski +{len(added)}/−{len(removed)}")
        hub.note(AGENT, "przegląd", f"{line}. {rec['summary']}", at=now)
        hub.event("review", f"Krytyk: {line}", agent=AGENT)
        rec["summary_line"] = line
        return rec

    def status(self) -> dict:
        return {"id": "critic", "state": "on", "doing": self.state["doing"], "since": iso(self.state["since"])}


def _ts(s) -> float:
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    from datetime import datetime
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()


def level_name(cfg: dict, n: int) -> str:
    return aicfg.level(cfg, n)["name"]
