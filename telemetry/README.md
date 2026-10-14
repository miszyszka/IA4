# telemetry/

**Wersja projektu: 1.40 (2026-10-14)**

`state.json` — najnowszy stan zbierania danych. Zapisuje go `Telemetry.gs`
z Apps Script (co godzinę i zaraz po świecy sesji, tylko gdy coś się zmieniło). Nie edytuj ręcznie.

`vi.json` — wirtualny inwestor dla strony IA4 (instrukcja, sekcja 11b): podsumowanie, otwarte
pozycje, ostatnie 150 transakcji, krzywa wyniku, strategie, sygnały ostatnich 35 świec. Zapisuje go
`Telemetry.gs` po każdym przeliczeniu świecy w `Paper.gs`, tylko gdy treść się zmieniła.

```
version, stage     wersja projektu i bieżący etap
collector          triggery, ostatnie uruchomienie, ostatni zapis, liczniki dnia, ostatni błąd
nightly            ostatnie nocne odświeżenie (data sesji, liczba świec)
base               łączna liczba świec w Firestore (liczona po nocnym odświeżeniu)
doubleProofHistory postęp pobierania historii doubleProof (instrukcja, sekcja 4 p. 5)
instruments        dla każdego: grupa, ostatnia świeca, close, liczba świec, pierwsza data, status
lastCandle         ostatnia świeca z tabeli STATS: czasy od zamknięcia (s), zapisanych, brakujące, rundy, czasy etapów (ms)
fx                 moduł FX 1h (10 par + BTC, kolekcja fx1h): historia N/11, aktualność, ostatni zapis i opóźnienie (s),
                   dziś (świece, brakujące, mediana/p90/maks. opóźnienia), wczoraj, kolejka kontroli dni, ostatnia świeca każdego instrumentu (instrukcja 4b)
vi                 wirtualny inwestor: od kiedy, zamkniętych, otwartych, średni wynik, przedział 95%, wynik $
```
