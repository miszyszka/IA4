"""
IA 4 — wyniki modułu prognozy EURUSD na branchu `fx` (instrukcja, sekcja 4c.12).
Wersja projektu: 1.23 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

Klon brancha w ia4-research/fx-repo/ (poza gitem głównego repo), te same
uprawnienia do push co zwykły `git push` na tym Macu. Mechanika git — wspólna
z poszukiwaniem (ia4.lab.store.ResultsRepo). Branch `fx-live` dojdzie w kroku FX-4.
"""

from __future__ import annotations

from pathlib import Path

from ..lab.store import ResultsRepo

RESEARCH_DIR = Path(__file__).resolve().parent.parent.parent
README = """# IA 4 — prognoza EURUSD (branch `fx`)

Ten branch zapisuje wyłącznie Python z Maca. Zasady i znaczenie plików:
`IA4_INSTRUKCJA.md` na branchu `main`, sekcja 4c.

- `fx/conditions.json` — katalog okoliczności `fx-cond/1` z progami; zapisany raz
  (`python -m ia4.fx.catalog --commit`), potem nienaruszalny (zasada 14)
- `fx/ratings.json` — ostatnie przeliczenie (`python -m ia4.fx.research`): rating, wystąpienia,
  przewaga, częstość i profil 48 świec każdej okoliczności, sprawdzian systemu
- `fx/runs.jsonl` — wiersz na każde przeliczenie (R-001, R-002, …) → arkusz OKOLICZNOSCI_FX
"""


def fx_repo(push: bool = True) -> ResultsRepo:
    """Klon brancha `fx`; pliki w podfolderze `fx/`."""
    return ResultsRepo(RESEARCH_DIR / "fx-repo", push=push, branch="fx", subdir="fx", readme=README)
