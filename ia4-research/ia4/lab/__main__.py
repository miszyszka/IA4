"""
IA 4 — poszukiwanie strategii na Macu (Etap 2).
Wersja projektu: 1.19 (2026-10-08) — musi zgadzać się z IA4_INSTRUKCJA.md

Uruchomienie (w folderze ia4-research/, z aktywnym .venv):
  python -m ia4.lab                 # liczy bez końca (Ctrl+C — zapisuje stan i kończy)
  python -m ia4.lab --hours 6       # liczy 6 godzin
  python -m ia4.lab --check         # tylko synchronizacja i kontrola bazy
  python -m ia4.lab --no-push       # bez wysyłania do GitHub (test)
  python -m ia4.lab --workers 4     # liczba procesów (domyślnie rdzenie − 1)

Kolejność przy każdym starcie (instrukcja, sekcja 9.1):
  1. caffeinate — Mac nie zaśnie, dopóki program działa,
  2. synchronizacja Firestore → kopia lokalna (python -m ia4.sync, przyrostowo),
  3. kontrola kompletności bazy (wynik w logu; braki łata automat w Apps Script),
  4. pobranie brancha `research` (config.json, punkt wznowienia),
  5. poszukiwanie od miejsca, w którym skończył poprzedni przebieg.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from .. import __version__
from .. import config as base_config
from . import check, data, search, settings, store, verify


def _traded_symbols() -> list[str]:
    """Spółki główne + kontrolne. Z Firestore (system/universe), a bez sieci — z plików parquet.
    doubleProof nigdy nie bierze udziału w poszukiwaniu (instrukcja, sekcja 6a)."""
    try:
        u = base_config.universe()
        return u["main"] + u["proof"]
    except Exception as e:
        import json
        man = {}
        if base_config.MANIFEST_PATH.exists():
            man = json.loads(base_config.MANIFEST_PATH.read_text(encoding="utf-8"))
        files = sorted(p.stem for p in base_config.CACHE_DIR.glob("*.parquet"))
        syms = [s for s in files if s not in data.CONTEXT
                and s not in base_config.DOUBLE_PROOF_FALLBACK
                and man.get(s, {}).get("group", "proof") in ("main", "proof")]
        print(f"  ! Firestore niedostępny ({type(e).__name__}) — biorę listę z plików: {len(syms)} instrumentów")
        return syms


def main() -> int:
    ap = argparse.ArgumentParser(description="IA 4 — poszukiwanie strategii")
    ap.add_argument("--hours", type=float, default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--check", action="store_true", help="tylko synchronizacja i kontrola bazy")
    ap.add_argument("--no-sync", action="store_true", help="bez synchronizacji z Firestore")
    ap.add_argument("--no-push", action="store_true", help="bez wysyłania wyników do GitHub")
    a = ap.parse_args()

    print(f"IA 4 — poszukiwanie strategii (wersja {__version__})\n")
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["caffeinate", "-dims", "-w", str(os.getpid())])
            print("caffeinate: Mac nie zaśnie, dopóki program działa.")
        except OSError:
            print("  ! caffeinate niedostępny — Mac może zasnąć.")

    if not a.no_sync:
        try:
            from .. import sync
            sync.sync()
        except Exception as e:
            print(f"  ! Synchronizacja nieudana ({type(e).__name__}: {e}) — pracuję na kopii lokalnej.")

    traded = _traded_symbols()
    rep = check.check(base_config.CACHE_DIR, traded + list(data.CONTEXT))
    print("\n" + check.describe(rep))
    for s, it in rep["items"].items():
        if it.get("error") or it.get("missing_n") or it.get("incomplete_n"):
            print(f"  {s}: {it.get('error', '')}brakujących sesji {it.get('missing_n', 0)} "
                  f"{it.get('missing', '')}, niepełnych {it.get('incomplete_n', 0)}")
    if a.check:
        return 0

    repo = store.ResultsRepo(base_config.RESEARCH_DIR / "research-repo", push=not a.no_push)
    repo.ensure()
    if settings.merged(repo.read_json("config.json")).get("search_closed"):
        print("\nPoszukiwanie zamknięte (search_closed w research/config.json) — "
              "nie szukam; przeliczam tylko weryfikację doubleProof.")
        if verify.run(repo, verify.load_dp_market(base_config.CACHE_DIR), force=False):
            repo.commit_push("research: doubleProof — weryfikacja strategii aktywnych")
        return 0
    print("\nWczytuję dane…")
    m = data.load_local(traded, base_config.CACHE_DIR)
    print(f"  {len(m.symbols)} instrumentów, {m.n:,} świec, skarbiec: {data.VAULT_BARS} najstarszych "
          f"świec każdego; okresy grupy głównej: {m.fold_dates}".replace(",", " "))
    dp = verify.load_dp_market(base_config.CACHE_DIR)
    if dp is not None:
        print(f"  doubleProof (tylko weryfikacja): {len(dp.symbols)} spółek, {dp.n:,} świec".replace(",", " "))
    lab = search.Lab(m, repo, base_config.CACHE_DIR, m.symbols, data.VAULT_BARS,
                     base_config.RESEARCH_DIR / "state", rep, workers=a.workers, hours=a.hours,
                     dp_market=dp)
    lab.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
