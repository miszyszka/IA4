# telemetry/

**Wersja projektu: 1.23 (2026-10-09)**

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
fx                 moduł EURUSD: ostatnia świeca i zapis, opóźnienia (s) dziś, brakujące, wczoraj, kolejka kontroli dni (instrukcja 4b)
vi                 wirtualny inwestor: od kiedy, zamkniętych, otwartych, średni wynik, przedział 95%, wynik $
```
