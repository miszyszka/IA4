# telemetry/

**Wersja projektu: 0.25 (2026-09-26)**

Ten katalog wypełnia się sam — nic tu nie edytuj ręcznie.

| Plik | Co zawiera |
|---|---|
| `state.json` | najnowszy stan systemu IA 4 |
| `history/RRRR-MM-DD.json` | migawka z danego dnia (nadpisywana w ciągu dnia) |

Zapisuje je `Telemetry.gs` z Google Apps Script przez GitHub Contents API —
tylko wtedy, gdy treść faktycznie się zmieniła, z odstępem minimum 10 minut.

## Co jest w środku

```
meta         wersja instrukcji, czas wygenerowania
project      etap, statusy etapów 0–5, kryteria ukończenia z wynikami, skarbiec
data         daty audytów, luki (typ, spółka, data, status, komentarz), instrumenty
collector    stan każdej spółki w automacie, błędy, status Firestore
jobs         postęp: historia, spółki kontrolne, dopisywanie wolumenu, triggery
log          ostatnie 80 wpisów dziennika zdarzeń
```

## Po co

Claude widzi wyłącznie to repozytorium — nie ma dostępu do arkusza ani do
edytora Apps Script. Bez tego pliku każda rozmowa zaczynała się od ręcznego
wklejania podsumowania. Teraz wystarczy: „zobacz telemetrię".
