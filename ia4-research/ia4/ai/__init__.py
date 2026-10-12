"""IA 4 — AI Investor: trzej agenci na Macu (Etap 6, instrukcja, sekcja 11c). Wersja projektu: 1.34 (2026-10-12).

  python -m ia4.ai              # nadzorca — to samo co `ia4 start` i dwuklik IA4-start.command (11c.3)
  python -m ia4.ai.selftest     # test na danych syntetycznych — „WYNIK: OK”
  python -m ia4.ai.replay       # test silnika portfela na historii (kopia lokalna, bez modelu)
  python -m ia4.ai.restore      # hub od nowa z brancha `ai`

AI-1: nadzorca, blokada, feed akcji i FX, hub, `ai-live/status.json`. AI-2: Agent-Investor (silnik portfela,
playbook 60 strategii, model językowy, branch `ai`, AI-INVESTOR.xlsx, punkty odniesienia). Maker i Manager — AI-3, AI-4.
"""

STEP = "AI-2"
