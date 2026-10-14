"""
IA 4 — branch `ai-live`: stan AI Investor na żywo (instrukcja, sekcja 11c.11).
Wersja projektu: 1.40 (2026-10-14) — musi zgadzać się z IA4_INSTRUKCJA.md

`status.json` — zawsze jeden commit, force push (ten sam mechanizm co `fx-live`, ia4/fx/live.py:
LiveRepo). Sygnał życia co 5 min i od razu po zdarzeniu (nie częściej niż co 20 s). Plik bez NaN.
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
    {"id": "investor", "name": "Agent-Investor", "step": "AI-2", "role": "decyzje po każdej rundzie świec"},
    {"id": "maker", "name": "Strategy-Maker", "step": "AI-3", "role": "hipotezy i backtesty w wolnym czasie"},
    {"id": "manager", "name": "Strategy-Manager", "step": "AI-4", "role": "przegląd, cele, wnioski"},
]


def agents(sup) -> list[dict]:
    w = getattr(sup, "agent", None)
    out = []
    for a in AGENTS:
        if a["id"] == "investor" and w is not None:
            st = w.inv.status()
            q = w.pending()
            out.append(dict(a, state="on", note=st["doing"] + (f" · w kolejce {q}" if q else ""), since=st["since"],
                            llm=st.get("llm"), rounds=w.done))
        else:
            out.append(dict(a, state="off", note=f"nieaktywny — od kroku {a['step']}"))
    return out


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
    if stopped:
        doc["stoppedAt"] = iso(now)
    return doc
