"""
IA 4 — jednorazowy backtest strategii aktywnych na doubleProof (instrukcja, sekcja 6a).
Wersja projektu: 1.25 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

Liczy wszystkie strategie aktywne (research/strategies/) na 20 spółkach doubleProof —
tym samym silnikiem i tak samo jak weryfikacja (verify.evaluate) — i zapisuje wynik RAZ
w research/backtest-doubleproof.json na branchu `research`. Plik się potem nie zmienia
(w przeciwieństwie do doubleproof.json, który weryfikacja przelicza co godzinę), więc
arkusz BACKTEST DOUBLEPROOF pokazuje zapisane wyniki z chwili backtestu.

Uruchomienie (w ia4-research/, z aktywnym .venv):
  python -m ia4.lab.backtest_dp            # synchronizacja, backtest, zapis, push
  python -m ia4.lab.backtest_dp --force    # nadpisuje istniejący zapis (nowy backtest)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .. import __version__
from .. import config as base_config
from . import verify

RESULT_FILE = "backtest-doubleproof.json"


def run(repo, m, log=print) -> dict | None:
    """Backtest wszystkich strategii aktywnych na wczytanym rynku doubleProof. Zwraca zapisany plik."""
    if m is None:
        log("Brak danych doubleProof na Macu (python -m ia4.sync) — backtest pominięty.")
        return None
    recs = verify._active_records(repo.dir)
    if not recs:
        log("Brak strategii aktywnych w research/strategies/ — backtest pominięty.")
        return None
    cache: dict = {}
    results, errors = [], []
    for rec in recs:
        try:
            r = verify.evaluate(rec, m, cache)
        except Exception as e:                                    # zła reguła nie zatrzymuje reszty
            errors.append({"id": rec.get("id"), "error": f"{type(e).__name__}: {e}"})
            log(f"  ✗ {rec.get('id')} — {type(e).__name__}: {e}")
            continue
        r["sum_ret_pct"] = round(r["avg_ret_pct"] * r["trades"], 3)
        results.append(r)
    results.sort(key=lambda r: (r["trades"] < 10, -r["pf"], -r["trades"]))
    now = datetime.now(timezone.utc)
    payload = {
        "version": __version__,
        "kind": "jednorazowy backtest strategii aktywnych na doubleProof",
        "createdAt": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "createdAtPL": now.astimezone(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M"),
        "strategies": len(recs),
        "data": {"instruments": len(m.symbols), "symbols": m.symbols, "candles": int(m.n),
                 "first_date": int(m.date.min()), "last_date": int(m.last_date), "folds": m.fold_dates},
        "results": results,
        "errors": errors,
    }
    repo.write_json(RESULT_FILE, payload)
    good = sum(1 for r in results if r["trades"] and r["pf"] >= 1.5)
    bad = sum(1 for r in results if r["trades"] and r["pf"] < 1)
    log(f"Backtest: {len(results)} strategii na {len(m.symbols)} spółkach doubleProof "
        f"({payload['data']['first_date']}–{payload['data']['last_date']}, {m.n} świec): "
        f"PF ≥ 1,5 — {good}, PF < 1 — {bad}, błędów {len(errors)}.")
    return payload


def main() -> int:
    import argparse
    from . import store
    ap = argparse.ArgumentParser(description="IA 4 — jednorazowy backtest strategii aktywnych na doubleProof")
    ap.add_argument("--force", action="store_true", help="nadpisz istniejący zapis backtestu")
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    print(f"IA 4 — jednorazowy backtest na doubleProof (wersja {__version__})\n")
    repo = store.ResultsRepo(base_config.RESEARCH_DIR / "research-repo", push=not a.no_push)
    repo.ensure()
    old = repo.read_json(RESULT_FILE)
    if old and not a.force:
        print(f"Backtest już zapisany ({old.get('createdAtPL')}, {old.get('strategies')} strategii) — "
              f"nic nie zmieniam. Nowy backtest: --force.")
        return 0
    m = verify.refresh(base_config.CACHE_DIR, sync_first=not a.no_sync)
    payload = run(repo, m)
    if payload is None:
        return 1
    repo.commit_push(f"research: jednorazowy backtest doubleProof — {len(payload['results'])} strategii")
    print("Gotowe. Arkusz BACKTEST DOUBLEPROOF odświeży się przy najbliższym researchSync "
          "(albo menu IA 4 → „Odśwież RESEARCH teraz”).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
