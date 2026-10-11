"""
IA 4 — wyniki modułu prognozy FX 1h (10 par + BTC/USD) na branchu `fx` (instrukcja, sekcja 4c.12).
Wersja projektu: 1.29 (2026-10-11) — musi zgadzać się z IA4_INSTRUKCJA.md

Klon brancha w ia4-research/fx-repo/ (poza gitem głównego repo), te same
uprawnienia do push co zwykły `git push` na tym Macu. Mechanika git — wspólna
z poszukiwaniem (ia4.lab.store.ResultsRepo). Branch `fx-live` — ia4/fx/live.py (LiveRepo).
"""

from __future__ import annotations

from pathlib import Path

from ..lab.store import ResultsRepo

RESEARCH_DIR = Path(__file__).resolve().parent.parent.parent
README = """# IA 4 — prognoza FX 1h: 10 par walutowych + BTC/USD (branch `fx`)

Ten branch zapisuje wyłącznie Python z Maca. Zasady i znaczenie plików:
`IA4_INSTRUKCJA.md` na branchu `main`, sekcja 4c.

- `fx/conditions.json` — katalog okoliczności `fx-cond/2` (świece 1h, wszystkie instrumenty) z progami; zapisany raz
  (`python -m ia4.fx.catalog --commit`), potem nienaruszalny (zasada 14)
- `fx/ratings.json` — ostatnie przeliczenie (`python -m ia4.fx.research`): rating, wystąpienia,
  przewaga, częstość i profil 48 świec każdej okoliczności, sprawdzian systemu
- `fx/runs.jsonl` — wiersz na każde przeliczenie (H-001, H-002, …) → arkusz OKOLICZNOSCI_FX
- `fx/archive/fx-cond-1-5m/` — archiwum katalogu `fx-cond/1` (EURUSD 5 min, 1.21–1.26), tylko do wglądu
- `index.html`, `.nojekyll` — dawny dashboard (do 1.27); od 1.28 strona IA4 jest w `docs/` na branchu `main`
"""


def fx_repo(push: bool = True) -> ResultsRepo:
    """Klon brancha `fx`; pliki w podfolderze `fx/`."""
    return ResultsRepo(RESEARCH_DIR / "fx-repo", push=push, branch="fx", subdir="fx", readme=README)
