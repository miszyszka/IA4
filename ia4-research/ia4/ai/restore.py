"""
IA 4 — odtworzenie huba AI Investor z brancha `ai` (instrukcja, sekcja 11c.1 p. 8).
Wersja projektu: 1.57 (2026-10-21) — musi zgadzać się z IA4_INSTRUKCJA.md

  python -m ia4.ai.restore     # tylko do pustego huba i przy zatrzymanym `ia4 start`
"""

from .store import main

if __name__ == "__main__":
    main()
