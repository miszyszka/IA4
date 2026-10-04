"""
IA 4 — wyniki poszukiwania na branchu `research` w GitHub.
Wersja projektu: 1.15 (2026-10-04) — musi zgadzać się z IA4_INSTRUKCJA.md

Wyniki mają osobny branch, żeby commity co 30 minut nie mieszały się
z `main` (kod, instrukcja, telemetria z Apps Script). Python trzyma własny
klon tego brancha w ia4-research/research-repo/ (poza gitem głównego repo).
Uprawnienia do push: te same, co zwykły `git push` na tym Macu.

Układ brancha (instrukcja, sekcja 10):
  research/config.json          ustawienia poszukiwania (zmienia Claude / człowiek)
  research/status.json          ostatni stan (co 30 min)
  research/log.jsonl            dziennik co 30 min — czyta go Research.gs
  research/checkpoint.json      punkt wznowienia
  research/vault.jsonl          każde otwarcie skarbca i jego wynik
  research/strategies/S-*.json  zapisane strategie
  research/strategies.jsonl     indeks strategii
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

BRANCH = "research"
README = """# IA 4 — wyniki poszukiwania strategii (branch `research`)

Ten branch zapisuje wyłącznie program `python -m ia4.lab` z Maca.
Zasady, format reguł i znaczenie plików: `IA4_INSTRUKCJA.md` na branchu `main`.
Ręcznie zmienia się tylko `research/config.json`.
"""


def _git(cwd: Path, *args, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


class ResultsRepo:
    def __init__(self, root: Path, push: bool = True):
        self.root = root                      # ia4-research/research-repo
        self.dir = root / "research"
        self.push_enabled = push
        self.last_error = ""

    # ------------------------------------------------------------ przygotowanie
    def _origin(self) -> str:
        main_repo = self.root.parent.parent        # …/IA4 (repo główne)
        r = _git(main_repo, "remote", "get-url", "origin", check=False)
        if r.returncode != 0:
            raise RuntimeError("Nie znaleziono adresu origin repozytorium IA4 (git remote get-url origin).")
        return r.stdout.strip()

    def ensure(self) -> None:
        if (self.root / ".git").exists():
            self.pull()
            self.dir.mkdir(parents=True, exist_ok=True)
            return
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.push_enabled:
            _git(self.root, "init", "-q", "-b", BRANCH)
            self.dir.mkdir(parents=True, exist_ok=True)
            return
        url = self._origin()
        _git(self.root, "init", "-q")
        _git(self.root, "remote", "add", "origin", url)
        fetched = _git(self.root, "fetch", "-q", "origin", BRANCH, check=False).returncode == 0
        if fetched:
            _git(self.root, "checkout", "-q", "-b", BRANCH, f"origin/{BRANCH}")
            _git(self.root, "branch", "-q", "--set-upstream-to", f"origin/{BRANCH}")
        else:                                        # pierwszy raz — nowy, pusty branch
            _git(self.root, "checkout", "-q", "--orphan", BRANCH)
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / "README.md").write_text(README, encoding="utf-8")
            self.commit_push("research: nowy branch wyników")
        self.dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ git
    def pull(self) -> None:
        if not self.push_enabled:
            return
        r = _git(self.root, "pull", "-q", "--rebase", "--autostash", "origin", BRANCH, check=False)
        if r.returncode != 0:
            self.last_error = r.stderr.strip()[:300]
            _git(self.root, "rebase", "--abort", check=False)

    def commit_push(self, message: str) -> bool:
        _git(self.root, "add", "-A", check=False)
        if _git(self.root, "diff", "--cached", "--quiet", check=False).returncode == 0:
            return True                               # nic nowego
        ident = []
        if not _git(self.root, "config", "user.email", check=False).stdout.strip():
            ident = ["-c", "user.name=IA4 lab", "-c", "user.email=ia4-lab@users.noreply.github.com"]
        _git(self.root, *ident, "commit", "-q", "-m", message, check=False)
        if not self.push_enabled:
            return True
        for attempt in range(4):
            r = _git(self.root, "push", "-q", "-u", "origin", BRANCH, check=False)
            if r.returncode == 0:
                self.last_error = ""
                return True
            self.last_error = r.stderr.strip()[:300]
            self.pull()
            time.sleep(5 * (attempt + 1))
        return False

    # ------------------------------------------------------------ pliki
    def read_json(self, name: str, default=None):
        p = self.dir / name
        if not p.exists():
            return default
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default

    def write_json(self, name: str, obj) -> None:
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def append_jsonl(self, name: str, obj) -> None:
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
