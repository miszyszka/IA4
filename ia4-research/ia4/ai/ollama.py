"""
IA 4 — lokalny model językowy przez Ollamę (instrukcja, sekcja 11c.2).
Wersja projektu: 1.35 (2026-10-12) — musi zgadzać się z IA4_INSTRUKCJA.md

Krok AI-1: tylko sprawdzenie przy starcie i stan do status.json (wersja Ollamy, model, digest,
model w pamięci). Wywołania modelu — od AI-2 (num_ctx 8192 jawnie, kolejka z pierwszeństwem).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request

from .. import config

HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if not HOST.startswith("http"):
    HOST = "http://" + HOST
MODEL = "qwen2.5:14b"
NUM_CTX = 8192
LOG = config.CACHE_DIR / "ai" / "ollama-serve.log"


def _get(path: str, timeout: float = 3.0) -> dict | None:
    try:
        with urllib.request.urlopen(HOST + path, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _start_server(log=print) -> bool:
    """`ollama serve` w tle (gdy aplikacja Ollama nie działa). True — serwer odpowiada."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, OLLAMA_NUM_PARALLEL="1")
    try:
        with LOG.open("a") as f:
            subprocess.Popen(["ollama", "serve"], stdout=f, stderr=subprocess.STDOUT, env=env, start_new_session=True)
    except OSError:
        log("  ! nie znalazłem polecenia `ollama` — zainstaluj Ollamę (ollama.com) albo uruchom aplikację Ollama")
        return False
    for _ in range(40):
        time.sleep(0.5)
        if _get("/api/version"):
            return True
    return False


def check(start: bool = True, log=print) -> dict:
    """Stan Ollamy i modelu: running, version, model, present, digest, sizeGB, loaded, started."""
    out = {"model": MODEL, "numCtx": NUM_CTX, "running": False, "present": False, "started": False}
    v = _get("/api/version")
    if v is None and start:
        log("  Ollama nie odpowiada — uruchamiam `ollama serve` w tle…")
        out["started"] = _start_server(log)
        v = _get("/api/version")
    if v is None:
        return out
    out["running"], out["version"] = True, v.get("version")
    tags = _get("/api/tags") or {}
    for m in tags.get("models") or []:
        if m.get("name") == MODEL or m.get("model") == MODEL:
            out.update(present=True, digest=(m.get("digest") or "")[:12], sizeGB=round((m.get("size") or 0) / 1e9, 1),
                       quant=(m.get("details") or {}).get("quantization_level"))
    out["loaded"] = loaded()
    return out


def loaded() -> list[dict]:
    """Modele w pamięci (/api/ps): nazwa i rozmiar w GB."""
    ps = _get("/api/ps", timeout=2.0) or {}
    return [{"name": m.get("name"), "sizeGB": round((m.get("size") or 0) / 1e9, 1)} for m in ps.get("models") or []]


def problem(info: dict) -> str | None:
    """Komunikat dla człowieka, gdy model jest niedostępny; None — wszystko w porządku."""
    if not info.get("running"):
        return ("Ollama nie działa. Uruchom aplikację Ollama (albo w terminalu `ollama serve`) i spróbuj ponownie.\n"
                "Bez modelu: python -m ia4.ai --no-llm-check (w kroku AI-1 model nie jest jeszcze używany).")
    if not info.get("present"):
        return f"Brak modelu {MODEL} w Ollamie. Pobierz go: ollama pull {MODEL}"
    return None
