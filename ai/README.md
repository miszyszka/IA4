# IA 4 — AI Investor (branch `ai`)

Ten branch zapisuje wyłącznie Python z Maca (`ia4 start`). Zasady: `IA4_INSTRUKCJA.md` na branchu `main`, sekcja 11c.
Ręcznie (człowiek z Claude) zmienia się tylko `ai/config.json` — nadpisania limitów i ustawień (klucze: `ia4/ai/config.py`).

- `ai/trades.jsonl` — zamknięta transakcja Agent-Investora = wiersz (wejście, wyjście, powód, wynik netto, koszty, notatki, pewność)
- `ai/decisions.jsonl` — runda = wiersz (kandydaci, decyzje modelu z notatkami, odrzucenia przez kod, notatka rundy)
- `ai/shadow.jsonl` — zamknięty cień (każdy kandydat bez limitów — punkt odniesienia „wszyscy kandydaci”)
- `ai/state.json` — otwarte i oczekujące pozycje, szczyt stanu konta, liczniki (odtworzenie huba)
- `ai/playbook.json` — strategie, których Inwestor może używać, ze statusem i wynikami na żywo
- `ai/benchmarks.json` — punkty odniesienia (11c.10)
- `ai/lessons.json` — aktywne wnioski
- `ai/config.json` — nadpisania ustawień
