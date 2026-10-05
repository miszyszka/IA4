# telemetry/

**Wersja projektu: 1.16 (2026-10-05)**

`state.json` — najnowszy stan zbierania danych. Zapisuje go `Telemetry.gs`
z Apps Script (co godzinę, tylko gdy coś się zmieniło). Nie edytuj ręcznie.

```
version, stage     wersja projektu i bieżący etap
collector          triggery, ostatnie uruchomienie, ostatni zapis, liczniki dnia, ostatni błąd
nightly            ostatnie nocne odświeżenie (data sesji, liczba świec)
base               łączna liczba świec w Firestore (liczona po nocnym odświeżeniu)
doubleProofHistory postęp pobierania historii doubleProof (instrukcja, sekcja 4 p. 5)
instruments        dla każdego: grupa, ostatnia świeca, close, liczba świec, pierwsza data, status
lastCandle         ostatnia świeca z tabeli STATS: czasy od zamknięcia (s), zapisanych, brakujące, rundy, czasy etapów (ms)
fx                 moduł EURUSD: ostatnia świeca, opóźnienia (s) dziś, brakujące, od kiedy baza (instrukcja 4b)
```
