"""
IA 4 — branch `ai-live`: stan AI Investor na żywo (instrukcja, sekcja 8).
Wersja projektu: 1.47 (2026-10-17) — musi zgadzać się z IA4_INSTRUKCJA.md

`status.json` — zawsze jeden commit, force push (ten sam mechanizm co `fx-live`, ia4/fx/live.py:
LiveRepo). Sygnał życia co 5 min, po zdarzeniu Inwestora najpóźniej po 20 s, po pracy Krytyka i Badacza najpóźniej po 2 min.
Plik bez NaN. Od 1.41: blok `work` (kto pracuje teraz, ostatnie zadania, statystyka 24 h), `research` (hipotezy)
i `critic` (poziom nauki, ostatni przegląd).
Czyta go zakładka AI strony IA4.
"""

from __future__ import annotations

import os
import platform
import socket
import subprocess

from ..fx.live import LiveRepo
from .feed import flow, iso

AGENTS = [
    {"id": "investor", "name": "Agent-Investor", "role": "decyzje po każdej świecy: wejścia, pozycje, własne pomysły"},
    {"id": "critic", "name": "Krytyk", "role": "przegląd co kilka rund: poziom nauki, uwagi, werdykty hipotez"},
    {"id": "researcher", "name": "Badacz", "role": "w wolnym czasie: hipotezy liczone na historii"},
]


def agents(sup) -> list[dict]:
    w = getattr(sup, "agent", None)
    out = []
    for a in AGENTS:
        obj = None if w is None else {"investor": w.inv, "critic": w.critic, "researcher": w.researcher}[a["id"]]
        if obj is None:
            out.append(dict(a, state="off", note="wyłączony"))
            continue
        st = obj.status()
        cur = w.now_doing()
        working = bool(cur and cur["agent"] == a["id"])
        q = w.pending() if a["id"] == "investor" else 0
        out.append(dict(a, state="work" if working else "on", note=st["doing"] + (f" · w kolejce {q}" if q else ""), since=st["since"],
                        llm=getattr(w.inv.llm, "last_by", {}).get(a["id"]), rounds=w.done if a["id"] == "investor" else None))
    return out


TL_AGENTS = ["investor", "critic", "researcher", "system"]


def work_view(sup, now: float) -> dict | None:
    """Praca agentów: teraz, ostatnie zadania, statystyka 24 h (strona: panel „praca agentów”)."""
    w = getattr(sup, "agent", None)
    if w is None:
        return None
    hub = sup.hub
    rows = hub.agent_runs(3000, since=now - 86400)
    stats = {}
    for r in rows:
        s = stats.setdefault(r["agent"], {"n": 0, "sec": 0.0, "llmSec": 0.0, "max": 0.0, "fail": 0, "last": None})
        s["n"] += 1
        s["sec"] += r["sec"] or 0
        s["llmSec"] += r["llm_sec"] or 0
        s["max"] = max(s["max"], r["sec"] or 0)
        s["fail"] += 0 if r["ok"] else 1
        s["last"] = max(s["last"] or 0, r["end"] or 0)
    since = max(now - 86400, getattr(sup, "started_at", now - 86400))
    span = max(1.0, now - since)
    for k, s in stats.items():
        s["avg"] = round(s["sec"] / s["n"], 1)
        s["busyPct"] = round(100 * s["sec"] / span, 1)
        s["last"] = iso(s["last"])
        s["sec"], s["llmSec"], s["max"] = round(s["sec"]), round(s["llmSec"]), round(s["max"], 1)
    busy = sum(r["sec"] or 0 for r in rows if (r["end"] or 0) >= since)
    cur = w.now_doing()
    return {
        "now": cur and {"agent": cur["agent"], "task": cur["task"], "since": iso(cur["since"])},
        "queue": w.pending(),
        "busyPct": round(min(100.0, 100 * busy / span), 1), "spanSec": round(span),
        "stats": stats,
        "runs": [{"agent": r["agent"], "task": r["task"], "start": iso(r["start"]), "sec": round(r["sec"] or 0, 1),
                  "llmSec": round(r["llm_sec"] or 0, 1), "ok": bool(r["ok"]), "summary": (r["summary"] or "")[:220]}
                 for r in rows[:60]],
        # oś 24 h: [agent, start w s od `from`, czas s, 1/0 = ok/błąd] — wszystkie zadania doby, zwięźle
        "timeline": {"from": iso(now - 86400), "agents": TL_AGENTS,
                     "runs": [[TL_AGENTS.index(r["agent"]) if r["agent"] in TL_AGENTS else 3, int(r["start"] - (now - 86400)),
                               int(round(r["sec"] or 0)), int(bool(r["ok"]))] for r in reversed(rows)]},
    }


def research_view(hub, inv=None) -> dict:
    from .research import describe
    c = hub.hyp_counts()
    closed = inv.main.closed() if inv is not None else []

    def row(h):
        r = h.get("result") or {}
        live = [p.ret_net_pct for p in closed if p.basis == h["id"]]
        return {"id": h["id"], "status": h["status"], "market": h["market"], "dir": h["direction"], "desc": describe(h),
                "idea": (h.get("idea") or "")[:240], "n": r.get("n"), "avg": r.get("avg"), "blind": (r.get("blind") or {}).get("avg"),
                "pf": r.get("pf"), "t": r.get("t"), "parts": [p.get("avg") for p in r.get("parts") or []],
                "why": (h.get("why") or [])[:2], "verdict": h.get("verdict_note"), "at": iso(h.get("at")),
                "live": {"n": len(live), "avg": (sum(live) / len(live)) if live else None}}
    return {"counts": c, "total": sum(c.values()),
            "recent": [row(h) for h in hub.hypotheses(25)],
            "live": [row(h) for h in hub.hypotheses(20, statuses=("próba", "zatwierdzona"))],
            "best": [row(h) for h in hub.hyp_best(8)]}


def critic_view(hub, inv) -> dict:
    ex = inv.explore()
    rv = hub.reviews(3)
    return {"explore": {k: ex[k] for k in ("level", "name", "base", "by", "reason", "passive", "floor", "auto", "own", "own_mult",
                                            "min_enter")},
            "reviews": [{"at": iso(x["at"]), "explore": x.get("explore"), "reason": x.get("exploreReason"),
                         "summary": x.get("summary"), "investorNotes": x.get("investor_notes"),
                         "researcherNotes": x.get("researcher_notes"), "verdicts": x.get("verdicts"),
                         "lessonsAdded": len(x.get("lessonsAdded") or []), "lessonsRemoved": len(x.get("lessonsRemoved") or [])}
                        for x in rv]}


def bench_view(b: dict | None) -> dict | None:
    if not b:
        return None
    return {k: b.get(k) for k in ("investor", "own", "all", "random", "mechanical", "spy", "calibration", "verdict", "investorR")}


def equity_curve(hub, n: int = 300) -> list:
    """[czas, stan konta] — najwyżej n punktów (co k-ty), ostatni zawsze."""
    rows = hub.equity_series(20000)
    if not rows:
        return []
    step = max(1, len(rows) // n)
    pick = rows[::step]
    if pick[-1] is not rows[-1]:
        pick.append(rows[-1])
    return [[iso(r["at"]), round(r["equity"], 2)] for r in pick]


class AiLiveRepo(LiveRepo):
    BRANCH = "ai-live"
    FILE = "status.json"


def machine() -> dict:
    out = {"cpus": os.cpu_count(), "system": platform.platform(terse=True)}
    try:
        out["load"] = [round(x, 2) for x in os.getloadavg()]
    except OSError:
        pass
    try:
        if platform.system() == "Darwin":
            out["memGB"] = round(int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
                                                    timeout=3).stdout.strip()) / 2**30)
        else:
            out["memGB"] = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return out


def document(sup, now: float, stopped: bool = False) -> dict:
    """Stan nadzorcy → status.json. `sup` — obiekt z polami: version, step, started_at, ollama, stocks, fx,
    fx_note, fx_ratings, hub, reads_today()."""
    from . import ollama
    ol = dict(sup.ollama or {})
    if ol.get("running") and not stopped:
        ol["loaded"] = ollama.loaded()
    doc = {
        "version": sup.version, "step": sup.step, "host": socket.gethostname(),
        "aliveAt": iso(now), "startedAt": iso(sup.started_at),
        "ollama": ol, "machine": machine(),
        "feed": {"stocks": sup.stocks.status() if sup.stocks else None,
                 "fx": sup.fx.status() if sup.fx else None,
                 "readsToday": sup.reads_today()},
        "fxForecast": {"on": bool(sup.fx_ratings), "ratings": sup.fx_ratings, "note": sup.fx_note},
        "agents": agents(sup),
        "flow": {"stocks": flow(sup.hub, "stocks", 14), "fx": flow(sup.hub, "fx", 24)},
        "events": [{"at": iso(e["at"]), "kind": e["kind"], "agent": e["agent"], "text": e["text"]} for e in sup.hub.events(40)],
    }
    inv = getattr(getattr(sup, "agent", None), "inv", None)
    if inv is not None and inv.public:
        pub = inv.public
        doc["investor"] = {k: pub.get(k) for k in ("startedAt", "capital", "portfolio", "positions", "lastRound")}
        doc["investor"]["bench"] = bench_view(pub.get("bench"))
        doc["investor"]["equity"] = equity_curve(sup.hub)
        doc["investor"]["notes"] = [{"at": iso(n["at"]), "agent": n["agent"], "kind": n["kind"], "text": n["text"][:700]}
                                    for n in sup.hub.notes(30)]
        doc["work"] = work_view(sup, now)
        doc["research"] = research_view(sup.hub, inv)
        doc["critic"] = critic_view(sup.hub, inv)
    if stopped:
        doc["stoppedAt"] = iso(now)
    return doc
