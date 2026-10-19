"""
IA 4 — blokada `ia4 start` (instrukcja, sekcja 11c.2–11c.3).
Wersja projektu: 1.49 (2026-10-19) — musi zgadzać się z IA4_INSTRUKCJA.md

Dopóki działa `ia4 start`, plik data/ai/ia4-start.lock trzyma jego PID. Programy, które nie mogą
działać równolegle — `ia4.fx.research` i `ia4.lab` (pamięć 16 GB zajmuje model językowy) oraz
`ia4.fx.live` (prognoza FX liczy się wewnątrz nadzorcy) — wołają guard() i kończą się z komunikatem.
Blokada po twardym przerwaniu (PID już nie żyje) jest nieważna.
"""

from __future__ import annotations

import atexit
import json
import os
import socket
import subprocess
import time
from pathlib import Path

from .. import config

LOCK = config.CACHE_DIR / "ai" / "ia4-start.lock"
CONFLICTS = {                                   # fragment polecenia → nazwa dla człowieka
    "-m ia4.fx.live": "python -m ia4.fx.live",
    "-m ia4.fx.research": "python -m ia4.fx.research",
    "-m ia4.lab": "python -m ia4.lab",
}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def holder(path: Path = LOCK) -> dict | None:
    """Kto trzyma blokadę (pid, host, startedAt) — None, gdy nikt albo blokada nieważna."""
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    pid = int(d.get("pid") or 0)
    if not pid or d.get("host") != socket.gethostname() or not _alive(pid) or pid == os.getpid():
        return None
    return d


def guard(program: str, path: Path = LOCK) -> None:
    h = holder(path)
    if h:
        raise SystemExit(f"Działa `ia4 start` (PID {h['pid']}, od {h.get('startedAt', '?')}). Zatrzymaj go (Ctrl+C), "
                         f"zanim uruchomisz {program} — instrukcja 11c.2.")


def acquire(path: Path = LOCK) -> None:
    h = holder(path)
    if h:
        raise SystemExit(f"`ia4 start` już działa (PID {h['pid']}, od {h.get('startedAt', '?')}) — drugi raz nie ruszam.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": os.getpid(), "host": socket.gethostname(),
                                "startedAt": time.strftime("%Y-%m-%d %H:%M:%S")}), encoding="utf-8")
    atexit.register(release, path)


def release(path: Path = LOCK) -> None:
    try:
        if json.loads(path.read_text(encoding="utf-8")).get("pid") == os.getpid():
            path.unlink()
    except (OSError, ValueError):
        pass


def others_running() -> list[str]:
    """Programy IA4, które kolidują z `ia4 start` i właśnie działają (ps)."""
    try:
        out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) < 2 or int(parts[0]) == os.getpid():
            continue
        for frag, name in CONFLICTS.items():
            if frag in parts[1] and "python" in parts[1] and name not in found:
                found.append(name)
    return found
