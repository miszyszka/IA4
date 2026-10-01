# telemetry/

**Wersja projektu: 1.7 (2026-10-01)**

`state.json` — najnowszy stan zbierania danych. Zapisuje go `Telemetry.gs`
z Apps Script (co godzinę, tylko gdy coś się zmieniło). Nie edytuj ręcznie.

```
version, stage     wersja projektu i bieżący etap
collector          triggery, ostatnie uruchomienie, ostatni zapis, liczniki dnia, ostatni błąd
nightly            ostatnie nocne odświeżenie (data sesji, liczba świec)
base               łączna liczba świec w Firestore (liczona po nocnym odświeżeniu)
instruments        dla każdego: grupa, ostatnia świeca, close, liczba świec, pierwsza data, status
```
