"""
IA 4 — wywołania lokalnego modelu językowego (Ollama) dla agentów (instrukcja, sekcja 8).
Wersja projektu: 1.52 (2026-10-20) — musi zgadzać się z IA4_INSTRUKCJA.md

  • odpowiedź wyłącznie JSON zgodny ze schematem (Ollama `format`), sprawdzana jeszcze raz w kodzie,
  • odpowiedź niezgodna → najwyżej `llm_retries` ponowień z listą błędów, potem „brak decyzji”,
  • `num_ctx` ustawiany jawnie (domyślne 2048 ucina kontekst bez ostrzeżenia); ostrzeżenie, gdy brief
    zbliża się do limitu,
  • jeden model naraz (dyspozytor i tak uruchamia jednego agenta naraz; blokada zostaje jako bezpiecznik),
  • każde wywołanie zapisane (pełny prompt i odpowiedź w hubie, skrót SHA-1, czas, tokeny).
"""

from __future__ import annotations

import hashlib
import heapq
import itertools
import json
import threading
import time
import urllib.error
import urllib.request

from . import ollama

PRIORITY = {"investor": 0, "critic": 1, "researcher": 2}


class PriorityLock:
    """Jeden model naraz; czekający z najniższym numerem pierwszeństwa wchodzą pierwsi."""

    def __init__(self):
        self._cv = threading.Condition()
        self._busy = False
        self._q: list = []
        self._n = itertools.count()

    def acquire(self, prio: int) -> None:
        with self._cv:
            me = (prio, next(self._n))
            heapq.heappush(self._q, me)
            while self._busy or self._q[0] != me:
                self._cv.wait()
            heapq.heappop(self._q)
            self._busy = True

    def release(self) -> None:
        with self._cv:
            self._busy = False
            self._cv.notify_all()

    def waiting(self) -> int:
        with self._cv:
            return len(self._q)


LOCK = PriorityLock()


def http_post(path: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(ollama.HOST + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class LLM:
    def __init__(self, cfg: dict, record=None, post=None, lock: PriorityLock = LOCK):
        self.cfg, self.record, self.post, self.lock = cfg, record, post, lock
        self.last: dict = {}                      # ostatnie wywołanie (dowolny agent)
        self.last_by: dict = {}                   # ostatnie wywołanie każdego agenta
        self.calls, self.sec_total = 0, 0.0       # liczniki dla dziennika pracy agentów

    def ask(self, agent: str, system: str, user: str, schema: dict, check, temperature: float) -> tuple[dict | None, dict]:
        """Zwraca (odpowiedź po sprawdzeniu albo None, meta). `check(obj) → lista błędów` (pusta = dobrze)."""
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        meta = {"agent": agent, "attempts": 0, "sec": 0.0, "errors": [], "promptTokens": None, "evalTokens": None}
        self.lock.acquire(PRIORITY.get(agent, 9))
        try:
            for attempt in range(1 + int(self.cfg["llm_retries"])):
                meta["attempts"] = attempt + 1
                t0 = time.time()
                content, err, resp = None, None, {}
                try:
                    resp = (self.post or http_post)("/api/chat", {
                        "model": self.cfg["model"], "messages": msgs, "format": schema, "stream": False,
                        "keep_alive": "30m",
                        "options": {"num_ctx": int(self.cfg["num_ctx"]), "temperature": float(temperature)},
                    }, float(self.cfg["llm_timeout_sec"]))
                    content = (resp.get("message") or {}).get("content", "")
                except (urllib.error.URLError, OSError, ValueError) as e:
                    err = f"Ollama: {type(e).__name__}: {e}"
                sec = time.time() - t0
                meta["sec"] += sec
                self.calls += 1
                self.sec_total += sec
                pt, et = resp.get("prompt_eval_count"), resp.get("eval_count")
                meta["promptTokens"], meta["evalTokens"] = pt, et
                obj, errors = None, []
                if err:
                    errors = [err]
                else:
                    try:
                        obj = json.loads(content)
                        errors = list(check(obj))
                    except ValueError as e:
                        errors = [f"to nie jest poprawny JSON ({e})"]
                if pt and pt >= int(self.cfg["num_ctx"]) - 64:
                    errors.append(f"brief zajął {pt} z {self.cfg['num_ctx']} tokenów — kontekst mógł zostać ucięty")
                if self.record:
                    self.record(agent=agent, model=self.cfg["model"], ok=not errors, err="; ".join(errors)[:1000], sec=sec,
                                prompt_tokens=pt, eval_tokens=et, prompt=system + "\n\n" + "\n\n".join(m["content"] for m in msgs[1:]),
                                response=content or "")
                meta["errors"] = errors
                self.last = {"agent": agent, "at": time.time(), "sec": round(sec, 1), "promptTokens": pt, "evalTokens": et,
                             "ok": not errors}
                self.last_by[agent] = self.last
                if obj is not None and not [e for e in errors if not e.startswith("brief zajął")]:
                    return obj, meta
                if err:                                   # model niedostępny — ponawianie nic nie da
                    break
                msgs = msgs[:2] + [{"role": "assistant", "content": content or ""},
                                   {"role": "user", "content": "Odpowiedź ma błędy:\n- " + "\n- ".join(errors[:12]) +
                                    "\nOdpowiedz jeszcze raz — cały JSON zgodny ze schematem, bez tych błędów."}]
            return (obj if obj is not None and isinstance(obj, dict) else None), meta
        finally:
            self.lock.release()


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()
