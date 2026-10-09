# IA 4 — instrukcja projektu

**Wersja:** 1.21
**Data:** 9 października 2026
**Aktualny etap:** 🟨 Etap 2 — Poszukiwanie strategii i 🟨 Etap 3 — Paper trading (sygnały na żywo, wirtualny inwestor). Etap 1 (baza danych) zamknięty 30.09.2026; automat zbierający świece działa dalej bez końca. Poszukiwanie wstrzymane 3.10.2026 (`search_closed: true`) — zostaje 60 aktywnych strategii. Od 4.10.2026 moduł EURUSD zbiera świece 5-minutowe (sekcja 4b). 🟨 Etap 4 — prognoza EURUSD na 48 świec 5-minutowych (sekcja 4c), w przygotowaniu. Jak czytać arkusze i wyciągać wnioski: `PRZEWODNIK.md`.

Ten plik jest jedynym źródłem prawdy i zbiorem żelaznych zasad projektu. Jeśli kod, arkusz albo telemetria się z nim rozjeżdżają, obowiązuje ten plik, a rozbieżność trzeba naprawić.

---

## 1. Cel

1. **Baza świec 1h w Firestore** (Etap 1, działa stale): kompletna, rośnie każdego dnia sesyjnego, ma stały format.
2. **Poszukiwanie strategii** (Etap 2): program w Pythonie na Macu, uruchamiany w dowolnych momentach, bez końca przelicza kopię lokalną bazy i szuka powtarzalnych sygnałów long i short opartych na średnich kroczących. Liczy się jakość, nie liczba strategii: strategia ma trafiać w TP, a nie zarabiać na samym trzymaniu pozycji w hossie. Każda zapisana strategia jest regułą opisaną na sztywno (sekcja 8), tak żeby inny system mógł ją odtworzyć świeca po świecy.
3. **Paper trading** (Etap 3): sygnały strategii na żywo i wirtualny inwestor w Apps Script, po każdej zamkniętej świecy (sekcja 11a).
4. **Weryfikacja na nowych spółkach:** grupa doubleProof (20 spółek), której system nigdy nie widzi przy szukaniu — do sprawdzania strategii przez człowieka (sekcja 6a).
5. **Moduł EURUSD:** osobna baza świec 5-minutowych kursu EURUSD (sekcja 4b).
6. **Prognoza EURUSD** (Etap 4): kurs na 48 świec 5-minutowych do przodu ze statystyki 1000 historycznych okoliczności z ratingiem; przeliczenie na Macu, prognoza na żywo i dashboard (sekcja 4c).

Historia wcześniejszych prac (strategie S1/S2, backtesty, etapy 0–5) jest w historii gita do wersji 0.47.

---

## 2. Żelazne zasady

1. **Firestore jest jedynym źródłem danych.** Kopia na Macu (`ia4-research/data/`) to tylko kopia robocza — można ją skasować i odtworzyć. Python nigdy nie pobiera świec z Yahoo i nigdy nie pisze do Firestore.
2. **Baza tylko rośnie.** Zapisujemy wyłącznie zamknięte świece. Niczego nie kasujemy. Wolno przepisać sesję tylko danymi pobranymi ponownie z Yahoo (nocne odświeżenie, „Uzupełnij ostatni miesiąc”). Jedyny wyjątek: moduł EURUSD uzupełnia świece, których Yahoo nie oddało po 3 próbach, uśrednieniem — zawsze oznaczonym w dokumencie (`fillT`, sekcja 4b).
3. **Format bazy (sekcja 4) jest stały.** Każda jego zmiana wymaga najpierw zmiany tej instrukcji, zgody człowieka i opisu migracji istniejących danych.
4. **Skarbiec = najstarsze 800 świec każdego instrumentu** (sekcja 6). Poszukiwanie nigdy nie widzi wyników skarbca. Skarbiec otwiera wyłącznie bramka skarbca, dla strategii, która przeszła wszystkie sita grupy głównej. Każde otwarcie jest liczone i zapisywane.
5. **Sekrety nigdy nie trafiają do repozytorium:** klucz serwisowy Firebase (`~/.ia4/serviceAccount.json`) i token GitHub (Script Properties → `GITHUB_TOKEN`).
6. **System jest minimalny.** Nowa funkcja, arkusz, plik czy dziennik pojawia się tylko za zgodą człowieka i najpierw jako zmiana tej instrukcji.
7. **Współpraca z Claude:**
   - na początku rozmowy Claude pobiera repozytorium `github.com/miszyszka/IA4.git`, czyta ten plik (branch `main`), `telemetry/state.json` (branch `main`) oraz `research/status.json` i `research/log.jsonl` (branch `research`), a gdy istnieją — `fx/runs.jsonl` (branch `fx`) i `forecast.json` (branch `fx-live`),
   - Claude przygotowuje zmiany jako commit w pliku `.bundle` (wysyła go w rozmowie, użytkownik zapisuje w `~/Downloads`) i podaje gotowe polecenia terminala do wypchnięcia (sekcja 12); lokalna kopia `~/Desktop/IA4` aktualizuje się przez `git pull`,
   - każdą zmianę Claude sprawdza przed wysłaniem: `selftest`, test zgodności (sekcja 11a), składnia plików `.gs`, symulacja zmienionej logiki,
   - pracę wykraczającą poza tę instrukcję albo pomysł na jej zmianę Claude najpierw proponuje i czeka na zgodę,
   - Claude nie ma dostępu do arkusza ani edytora Apps Script: użytkownik ręcznie wkleja zmienione pliki `.gs` do Apps Script i robi `git pull` na Macu.
8. **Jedna wersja dla całego projektu.** Ten sam numer w nagłówku tej instrukcji, w nagłówku każdego pliku `.gs`, w `CONFIG.VERSION` (`Code.gs`) i w `ia4-research/` (`ia4/__init__.py`). Zmiana znacząca (logika, zasada, format, etap) podbija wersję i dostaje wpis w sekcji 13. Drobne poprawki — tylko opis w commicie. (`appsscript.json` nie nosi wersji — JSON nie ma komentarzy.)
9. **Strategia to reguła, nie kod.** Każda zapisana strategia jest pełną regułą w języku `ia4-rule/1` (sekcja 8): linie, sygnał, filtry, SL, TP, FC, limit czasu — wszystko liczbami, bez parametrów domyślnych. Definicje z sekcji 8 zmienia się tylko razem z nową wersją języka (`ia4-rule/2`); stare strategie zachowują swoją wersję.
10. **Symulacja jest zawsze pesymistyczna** (sekcja 8.6). Strategie (poszukiwanie, weryfikacja, backtest doubleProof) liczone są bez kosztów transakcyjnych, każda reguła na wszystkich hipotezach SL × TP naraz. Koszt transakcyjny (`COST_PCT` = 0,005% wartości pozycji przy wejściu i przy wyjściu) liczą tylko wirtualny inwestor (11a) i backtest portfela (6b).
11. **Wyniki poszukiwania żyją na branchu `research`** (sekcja 10), wyniki prognozy EURUSD — na branchach `fx` i `fx-live` (sekcja 4c.12). Python nie pisze do `main`; `main` to kod, ta instrukcja i telemetria automatu.
12. **Jeden język reguł, dwie implementacje.** Reguły liczy Python (`ia4/lab`, backtest) i JavaScript (`PaperEngine.gs`, na żywo). Każda zmiana definicji z sekcji 8 musi trafić do obu naraz, a test zgodności (`ia4-research/tests/`, sekcja 11a) musi dać 0 rozbieżności.
13. **Mediana trzymania.** Każdy wynik strategii albo portfela (arkusze, pliki wyników) podaje medianę świec w pozycji: świeca wyjścia − świeca wejścia + 1.
14. **Katalog okoliczności FX jest nienaruszalny.** Po jednorazowej kalibracji (sekcja 4c.2) ID, definicje i progi okoliczności nigdy się nie zmieniają; nowy katalog powstaje tylko jako nowa wersja (`fx-cond/2`) obok starego, za zgodą człowieka.

---

## 3. Architektura

```
Yahoo ──(Apps Script, co minutę)──▶ Firestore ──(ia4.sync)──▶ Mac: ia4-research/data/*.parquet
                  │                                                     │
                  ├──▶ arkusz STATS                                     ▼
                  ├──▶ GitHub main: telemetry/state.json      python -m ia4.lab (bez końca)
                  │                                                     │
                  ├──◀ arkusze STRATEGIE, BACKTEST PORTFELA ◀──(Research.gs, co 30 min)── GitHub research: research/*
                  └──▶ po każdej świecy: Paper.gs (Firestore → pamięć _IA4_DANE → sygnały, inwestor)
Yahoo EURUSD=X ──(Fx.gs, w tym samym triggerze)──▶ Firestore fx/EURUSD (moduł EURUSD, sekcja 4b)
Firestore fx/EURUSD ──(ia4.fx.sync)──▶ Mac: data/fx/ ──▶ ia4.fx.research (ręcznie) ──▶ GitHub fx: ratingi, index.html ──▶ arkusz OKOLICZNOSCI_FX
                                                  └──▶ ia4.fx.live (co 30 s) ──▶ GitHub fx-live: forecast.json ──▶ dashboard (GitHub Pages)
```

| Plik | Rola |
|---|---|
| `Code.gs` | automat: listy instrumentów, zbieranie na żywo (szybka ścieżka po zamknięciu świecy), nocne odświeżenie, liczenie bazy, pobieranie historii doubleProof, zapis do Firestore, arkusz STATS, menu, triggery |
| `Fx.gs` | moduł EURUSD: świece 5 min z Yahoo → Firestore `fx/EURUSD`, opóźnienia w STATS (sekcja 4b) |
| `Telemetry.gs` | stan zbierania → `telemetry/state.json` w GitHub (branch `main`) |
| `Research.gs` | branch `research` (`strategies.jsonl`, `backtest-doubleproof.json`, `portfolio-backtest.json`) → arkusze STRATEGIE i BACKTEST PORTFELA; listy `ACTIVE_IDS` i `PRIORITY` dla paper tradingu |
| `Paper.gs` | paper trading: pamięć świec, sygnały na żywo (SIGNALS-REALTIME), wirtualny inwestor (VIRTUAL-INVESTOR) |
| `PaperEngine.gs` | język reguł `ia4-rule/1` w JavaScript — wierna kopia `indicators/data/rules/sim.py` |
| `ia4-research/tests/` | test zgodności PaperEngine.gs z Pythonem (`parity_dump.py`, `parity.js`) |
| `appsscript.json` | uprawnienia Apps Script |
| `ia4-research/ia4/sync.py` | Firestore → lokalne pliki parquet, tylko przyrosty |
| `ia4-research/ia4/config.py` | klucz serwisowy (poza repo), listy instrumentów z Firestore |
| `ia4-research/ia4/lab/__main__.py` | `python -m ia4.lab` — start: synchronizacja, kontrola bazy, poszukiwanie |
| `ia4-research/ia4/lab/check.py` | kontrola kompletności kopii lokalnej (kalendarz NYSE) |
| `ia4-research/ia4/lab/data.py` | kopia lokalna → tablice świec, strefy (skarbiec, okresy), cechy filtrów |
| `ia4-research/ia4/lab/indicators.py` | średnie kroczące, ATR, RSI (sekcja 8.2) |
| `ia4-research/ia4/lab/rules.py` | język reguł `ia4-rule/1` — implementacja wzorcowa (sekcja 8) |
| `ia4-research/ia4/lab/sim.py` | symulacja transakcji, wszystkie SL × TP naraz (sekcja 8.6) |
| `ia4-research/ia4/lab/space.py` | siatka, losowanie, mutacje, sąsiedzi, opisy słowne reguł |
| `ia4-research/ia4/lab/search.py` | pętla poszukiwania, sita, bramka skarbca, log co 30 min |
| `ia4-research/ia4/lab/worker.py` | obliczenia w procesach roboczych; wyniki skarbca tylko przez bramkę |
| `ia4-research/ia4/lab/store.py` | klon brancha `research` w `ia4-research/research-repo/`, commit + push |
| `ia4-research/ia4/lab/settings.py` | domyślne ustawienia poszukiwania (nadpisuje je `research/config.json`) |
| `ia4-research/ia4/lab/verify.py` | weryfikacja strategii aktywnych na doubleProof → `research/doubleproof.json` (sekcja 6a) |
| `ia4-research/ia4/lab/portfolio.py` | jednorazowy backtest portfela (wirtualny inwestor na historii) → `research/portfolio-backtest.json` (sekcja 6b) |
| `ia4-research/ia4/lab/backtest_dp.py` | jednorazowy backtest strategii aktywnych na doubleProof → `research/backtest-doubleproof.json` (sekcja 6a) |
| `ia4-research/ia4/lab/selftest.py` | test silnika na danych syntetycznych |
| `ia4-research/README.md` | instalacja i użycie |
| `telemetry/state.json` | stan automatu, generowany — nie edytować |
| `IA4_INSTRUKCJA.md` | ten plik |
| `ia4-research/ia4/fx/` | prognoza EURUSD (sekcja 4c): `sync.py` (Firestore → `data/fx/`), `series.py` (seria, lustro, wskaźniki 4c.3; średnie, ATR, RSI z `ia4/lab/indicators.py`), `catalog.py` (okoliczności `fx-cond/1`, kalibracja), `selftest.py`, `research.py` (wystąpienia, profile, ratingi, sprawdzian), `live.py` (prognoza na żywo), `store.py` (branche `fx` i `fx-live`), `dashboard/index.html` |
| `PRZEWODNIK.md` | prosty przewodnik dla człowieka: co jest gdzie, jak czytać, jakie wnioski |

---

## 4. Baza danych

### Instrumenty (75)

| Grupa | Kolekcja | Instrumenty |
|---|---|---|
| główne (3) | `stocks` | AAPL, TSLA, NVDA |
| kontrolne (50) | `proof` | DELL, AMAT, PLTR, ORCL, XOM, V, WMT, JPM, MU, META, AVGO, MSFT, GOOGL, JNJ, MA, ABBV, BAC, CVX, MRK, PG, HD, PM, WFC, CRM, CAT, HON, UNP, RTX, AMZN, MCD, NKE, SBUX, T, VZ, NFLX, DIS, UNH, LLY, PFE, MDT, PLD, AMT, LIN, FCX, NEE, DUK, GS, AXP, KO, PEP |
| tło rynku (2) | `context` | SPY, QQQ |
| doubleProof (20) | `doubleProof` | AMD, INTC, QCOM, CSCO, ADBE, LRCX, C, MS, SCHW, COP, OXY, SLB, BA, GE, UBER, F, GM, COST, BMY, CMCSA |

Nazwy grup i kolekcji są historyczne; zostają, żeby nie przenosić danych. Listy są w `Code.gs` (`CONFIG`) i w Firestore (`system/universe`). W Etapie 2 strategie są wspólne dla wszystkich 53 spółek (główne + kontrolne); SPY i QQQ służą tylko jako filtry tła rynku. doubleProof to 20 innych spółek z S&P 500 o dużym obrocie (półprzewodniki, oprogramowanie, banki, energia, przemysł, motoryzacja, handel, farmacja, media) — wyłącznie do weryfikacji strategii przez człowieka (sekcja 6a).

### Świeca

Świece 1h sesji regularnej NYSE, bez pre/after-market. Sesja ma 7 świec, numerowanych 1–7:

| nr | ET | PL (zwykle) |
|---|---|---|
| 1–6 | 9:30–10:30 … 14:30–15:30 | 15:30–16:30 … 20:30–21:30 |
| 7 | 15:30–16:00 (pół godziny) | 21:30–22:00 |

Sesja skrócona (np. 13:00 ET) ma 4 świece. Ceny zaokrąglone do 4 miejsc. Wolumen `0` znaczy „Yahoo nie podał”, nie „brak obrotu”. Dni bez sesji (weekendy, `US_MARKET_HOLIDAYS` w `Code.gs`) nigdy nie trafiają do bazy.

### Format w Firestore

```
stocks/{SYMBOL}/candles/{data}_{nr}    spółki główne — jeden dokument na świecę
  symbol, date (RRRR-MM-DD), slot (1–7), label, startPL, startET,
  open, high, low, close, volume, candleTime, source, updatedAt
stocks/{SYMBOL}                        podsumowanie: lastDate, lastSlot, lastLabel, lastClose, updatedAt

proof/{SYMBOL}/sessions/{data}         kontrolne — cała sesja w jednym dokumencie
context/{SYMBOL}/sessions/{data}       tło rynku — ten sam format
doubleProof/{SYMBOL}/sessions/{data}   doubleProof — ten sam format
  symbol, date, bars (liczba świec), slots [1..7], o [], h [], l [], c [], v [],
  startPL, firstCandleTime, updatedAt
  (tablice slots/o/h/l/c/v są równoległe: element i = świeca nr slots[i])
proof/{SYMBOL}, context/{SYMBOL}       podsumowanie: lastDate, liveUpdatedAt (+ pola z pobierania historii)
doubleProof/{SYMBOL}                   podsumowanie: lastDate, liveUpdatedAt, historyFirstDate, historyUpdatedAt, historyDone

system/universe                        listy instrumentów: live, proof, context, doubleProof
system/status                          ostatni zapis automatu, wersja
```

`updatedAt` zmienia się przy każdym zapisie dokumentu — po nim synchronizacja w Pythonie rozpoznaje, co się zmieniło od poprzedniego razu.

### Zakres

Historia od połowy września 2024 (granica Yahoo: ok. 730 dni wstecz dla świec 1h — starszych danych nie da się już pobrać), ok. 3500 świec na instrument na koniec września 2026. Każdy dzień sesyjny dokłada 7 świec na instrument.

### Jak baza jest aktualizowana (`Code.gs`)

1. **Na żywo — szybka ścieżka po zamknięciu świecy.** Trigger `runCollector` co minutę.
   - **Czekanie na zamknięcie:** uruchomienie, w którym zamknięcie świecy + 15 s (`FIRST_FETCH_SEC`) wypada w ciągu najbliższych 60 s (`ARM_MAX_SEC`), czeka na tę chwilę (trigger startuje w losowej sekundzie minuty). 15 s to margines, żeby Yahoo domknęło świecę.
   - **Runda:** wszystkie instrumenty bez tej świecy pobierane z Yahoo równolegle (`UrlFetchApp.fetchAll`, paczki po 25, `YAHOO_BATCH`; nieudane — raz przez drugi serwer Yahoo), potem jeden zapis do Firestore (paczki ≤ 400 dokumentów, spółka nigdy nie jest dzielona). Zapisujemy tylko nowe, zamknięte świece. Pamięć „co już zapisane” (`LIVE_STATE`) przesuwa się dopiero po potwierdzeniu zapisu.
   - **Ponowienia:** co 10 s (`POLL_SEC`) runda tylko dla instrumentów, którym brakuje świecy — aż będzie wszystkie 75, najdłużej 4 min od zamknięcia (`FAST_WINDOW_MIN`); całe uruchomienie najwyżej 270 s (`FAST_MAX_RUN_SEC`, limit Apps Script: 6 min). Spóźnione instrumenty dociągają kolejne uruchomienia.
   - **Paper trading** (11a) rusza w tej samej pętli, gdy tylko komplet 53 spółek handlowanych ma świecę.
   - Gdy poprzednie uruchomienie jeszcze pracuje, następne nie czeka na blokadę (1 s) — kończy się od razu.
   - Czasy każdej świecy: tabela świec w STATS (sekcja 4a).
2. **Nocne odświeżenie.** Raz na dzień sesyjny, 45 min po zamknięciu, automat przepisuje ostatnie ~5 sesji wszystkich instrumentów (ok. 550 zapisów). Świeca brakująca z powodu awarii wraca sama tej samej nocy. Nieudane odświeżenie jest ponawiane co 30 min.
3. **Liczenie bazy.** Po nocnym odświeżeniu automat liczy świece i pierwszą datę każdego instrumentu (zapytania agregujące, ok. 150 odczytów) — widać to w STATS i w `telemetry/state.json`.
4. **Ręcznie:** menu IA 4 → „Uzupełnij ostatni miesiąc” (po dłuższej przerwie automatu), „Nocne odświeżenie teraz”, „Historia doubleProof — jedna porcja teraz”, „EURUSD — pobierz teraz”.
5. **Historia doubleProof (jednorazowo, sama się kończy).** Raz na godzinę, w wolnym przebiegu `runCollector`, jedna porcja: dla każdej spółki doubleProof bez pełnej historii kolejne 60 dni wstecz (Yahoo `period1/period2`, okna od północy do północy UTC — sesja nigdy nie jest dzielona). Zaczyna od wczoraj, kończy na granicy Yahoo (728 dni wstecz albo odpowiedź Yahoo „poza zakresem 730 dni”). Ok. 840 zapisów na porcję, ok. 10 tys. łącznie; najwyżej 8000 zapisów dziennie, więc całość trwa ok. 12–13 godzin pracy rozłożonych na 1–2 dni. Stan: Script Properties `BACKFILL_DP`, postęp w STATS („Historia doubleProof”) i w `telemetry/state.json` (`doubleProofHistory`). Dzisiejsze i ostatnie sesje zapisują zbieranie na żywo i nocne odświeżenie, jak dla pozostałych instrumentów.

Limity Firestore (plan Spark): 20 000 zapisów i 50 000 odczytów dziennie — zużycie wszystkich części systemu: sekcja 12, „Limity Firestore”.

### 4a. Arkusz STATS

Przepisywany przy każdym uruchomieniu automatu. Układ oznacza znacznik w komórce A2 (`stats-1.15`); inny znacznik albo brak arkusza — arkusz buduje się sam od nowa.

**Blok stanu** (od wiersza 3): status (OK / BŁĄD), ostatnie uruchomienie (PL, z watchdogiem „brak uruchomień > 15 min”), ostatnia akcja, czas w Nowym Jorku, sesja USA, trigger, **czas pracy automatu dziś** (suma czasu wszystkich uruchomień — limit Google dla konta Gmail to 90 min triggerów dziennie), zapisanych świec dziś, błędów dziś, ostatni błąd, nocne odświeżenie, świec w bazie, 3 wiersze modułu EURUSD (sekcja 4b).

**Tabela świec** (pod blokiem stanu): jeden wiersz na świecę, najnowsze na górze — 7 wierszy na dzień sesyjny (4 w dni skrócone), ostatnie 90 dni. Czasy jako **+m:ss od zamknięcia świecy** (pełna godzina i 30 minut ET; ostatnia świeca — 16:00 ET); wartość ujemna = przed zamknięciem.

| Kolumna | Znaczenie |
|---|---|
| Data, Świeca, Zamknięcie (PL) | która świeca |
| Start automatu | początek pierwszej rundy dla tej świecy |
| 3 główne / 53 spółki / 75 spółek zapisane | chwila, gdy Firestore potwierdził zapis świecy ostatniej spółki z grupy (53 = handlowane, tyle potrzebuje paper trading) |
| Strategie policzone | sygnały wszystkich strategii policzone (11a) |
| Arkusze SIGNALS i VI gotowe | SIGNALS-REALTIME i VIRTUAL-INVESTOR zapisane |
| Świec zapisanych | ile instrumentów ma już tę świecę, np. 75 / 75 |
| Brakujące / błędy | instrumenty bez świecy i liczba nieudanych pobrań |
| Sygnałów · VI otwarto / zamknięto | wynik paper tradingu na tej świecy |
| Rund Yahoo · Czasy etapów (s) | liczba rund i czas etapów: Yahoo, zapis, pamięć (odczyt `_IA4_DANE` + Firestore), sygnały, arkusze, zapis pamięci |

Spółka, której świeca dojdzie w późniejszym uruchomieniu, uzupełnia ten sam wiersz. Bieżący wiersz: Script Properties `CANDLE_LOG`; ostatnia świeca trafia też do telemetrii (`lastCandle`).

### 4b. Moduł EURUSD (`Fx.gs`)

Osobny moduł: **zbiera** świece 5-minutowe kursu EURUSD. Nie bierze udziału w poszukiwaniu, weryfikacji ani paper tradingu. Kopię na Macu i prognozę ma osobny moduł prognozy (sekcja 4c). Obowiązują go zasady 2.1–2.3 z jednym wyjątkiem (uśrednione świece, niżej).

- **Źródło:** Yahoo `EURUSD=X`, `interval=5m`. Yahoo trzyma świece 5 min tylko 60 dni wstecz, więc historia zaczyna się 59 dni przed startem modułu (pierwszy dzień bazy jest niepełny) i rośnie od tego dnia. Ceny Yahoo dla walut są orientacyjne; wolumen Yahoo podaje zawsze 0 — nie jest zapisywany.
- **Świeca:** 5 minut, opisana czasem początku w UTC (wielokrotność 5 min). Zapisujemy tylko świece zamknięte. Ceny zaokrąglone do 6 miejsc.
- **Godziny rynku:** od niedzieli 17:00 do piątku 17:00 czasu Nowego Jorku. **Oczekiwane świece dnia (UTC)** = świece, których początek wypada w tych godzinach: pon.–czw. **288**, piątek 252 (latem; zimą 264), niedziela 36 (zimą 24), sobota 0.
- **Format w Firestore:**
  ```
  fx/EURUSD/days/{RRRR-MM-DD}     jeden dokument na dzień UTC
    symbol ("EURUSD"), date, bars (świec razem, z uśrednionymi),
    t [] (minuta dnia UTC początku świecy: 0, 5, … 1435), o [], h [], l [], c []   (tablice równoległe),
    expected (oczekiwanych), missing (brakujących), filled (uśrednionych),
    fillT [] (minuty świec uśrednionych — NIE pochodzą z Yahoo), tries (próby kontroli),
    status ("dzień trwa", "do kontroli", "braki — próba n z 3", "kompletny",
            "uzupełniony: N świec uśrednionych", "brak danych z Yahoo — nie uzupełniono",
            "pierwszy dzień bazy — od HH:MM UTC"), updatedAt
  fx/EURUSD                       podsumowanie: symbol, yahoo ("EURUSD=X"), interval ("5m"),
                                  lastDate, lastTime (HH:MM UTC), lastClose, liveUpdatedAt
  ```
  Dokumenty sprzed 1.17 nie mają pól `expected`…`status` — pierwsze uruchomienie 1.17 przelicza je w rejestrze (niżej) i planuje kontrolę dni z brakami.
- **Na żywo:** w każdym uruchomieniu `runCollector` (co minutę) i co 10 s w szybkiej ścieżce akcji — jeden trigger dla całego automatu (dzienny limit czasu triggerów). Yahoo jest pytane tylko wtedy, gdy powinna już być zamknięta świeca nowsza niż ostatnia zapisana (+5 s), i tylko w godzinach rynku (z zapasem 5 min). Pobranie od początku dnia UTC ostatniej zapisanej świecy; dokument dnia z nową świecą przepisywany w całości (status „dzień trwa”).
- **Kontrola zakończonego dnia** (zamiast dawnego dziennego odświeżenia): od 00:20 UTC wczorajszy dzień trafia do kolejki (`FX_CHECK`; sobota — nie). **Próba** = świece z Firestore + cały dzień pobrany z Yahoo na nowo (z zapasem ±1 h; świeże z Yahoo wygrywają) → braki liczone od nowa. Do **3 prób co 60 min**; najwyżej 2 dni na jedno uruchomienie.
  - brak braków → „kompletny”,
  - po 3 próbach z brakami → **uśrednienie wszystkich braków** — każdy dzień kończy się kompletny (zapisanych = oczekiwanych); „brak danych z Yahoo — nie da się uśrednić” tylko wtedy, gdy w dniu i godzinę obok nie ma żadnej świecy,
  - pierwszy dzień bazy (zaczyna się w połowie — granica historii Yahoo): oczekiwane świece liczone od jego pierwszej świecy,
  - dni starsze niż 58 dni (Yahoo ich już nie odda) — od razu uśrednienie,
  - dzień z wynikiem końcowym wypada z kolejki i nie jest już zmieniany.
- **Uśrednienie** (interpolacja liniowa): dla brakującej świecy t — najbliższa świeca przed (P) i po (N), także z sąsiedniego dnia. Cena biegnie liniowo od zamknięcia P do otwarcia N: open = wartość w chwili t, close = w chwili t + 5 min, high/low = większa/mniejsza z nich. Tylko P albo tylko N — świeca płaska na tej cenie. Świece uśrednione są zawsze w `fillT`; analiza może je pominąć.
- **Opóźnienie świecy** = chwila potwierdzenia zapisu w Firestore − zamknięcie świecy (początek + 5 min).
- **Arkusz FX — jeden wiersz na dzień** (UTC, najnowszy na górze, także soboty): data, dzień tygodnia, **oczekiwanych świec**, **zapisanych świec**, **w tym uśrednionych**. Wiersz pojawia się, gdy kontrola zakończy dzień (zwykle 00:20–02:20 UTC następnego dnia; sobota — 0 / 0 / 0), i już się nie zmienia. Dzień, który trwa albo czeka na kolejną próbę, nie ma jeszcze wiersza. Czy zbieranie działa i opóźnienia — STATS.
- **STATS** (3 wiersze bloku stanu) i telemetria (pole `fx`: ostatnia świeca i zapis, opóźnienia, wczoraj, kolejka kontroli).
- Stan: Script Properties `FX_STATE`, `FX_CHECK`. Ręcznie: menu IA 4 → „EURUSD — pobierz teraz”, „EURUSD — przelicz arkusz FX” (arkusz od nowa z Firestore, ok. 1 odczyt na dzień bazy; dni niekompletne i dni robocze bez dokumentu trafiają do kontroli).

### 4c. Prognoza EURUSD (`ia4-research/ia4/fx/`, Etap 4)

Cel: prognoza zamknięć EURUSD na **48 świec 5-minutowych do przodu** (4 godziny), liczona ze statystyki historycznych „okoliczności”. Dwa programy w Pythonie na Macu — **FX-research** (tylko ręcznie) i **FX-real-time** (gdy Mac jest włączony) — oraz dashboard na GitHub Pages i arkusz OKOLICZNOSCI_FX. Moduł tylko czyta Firestore (zasada 2.1) i nie wpływa na zbieranie (4b), poszukiwanie strategii ani paper trading.

#### 4c.1 Dane

- **Kopia lokalna:** `python -m ia4.fx.sync` (oba programy wołają ją przy starcie) → `ia4-research/data/fx/EURUSD.parquet`: kolumny `time` (początek świecy, sekundy UTC), `o, h, l, c`, `filled` (świeca z `fillT` — uśredniona), posortowane po `time`; stan w `data/fx/_manifest.json` (najnowsze `updatedAt`). Przyrostowo: tylko dokumenty `fx/EURUSD/days` z `updatedAt` nowszym niż w manifeście (zwykle 1–3 odczyty); pierwszy raz — wszystkie dni (ok. 1 odczyt na dzień bazy); `--full` — od nowa.
- **Seria:** wszystkie świece w kolejności czasu; `t` to indeks w serii (jak w sekcji 8 — przez weekend bez przerwy w indeksie). Wskaźniki liczone na całej serii, także na świecach uśrednionych.
- **Przerwa:** odstęp między kolejnymi świecami serii większy niż 60 min (weekend, awaria bez uzupełnienia).
- **Pips** = 0,0001.

#### 4c.2 Okoliczności (katalog `fx-cond/1`)

- **Okoliczność** = warunek prawda/fałsz na świecy `t`, liczony wyłącznie ze świec ≤ `t` (o, h, l, c). Wartość, której nie da się policzyć, daje fałsz (jak w sekcji 8).
- **1000 okoliczności = 500 par lustrzanych.** Każda ma kierunek: `+` (wzrost, wysoka cena) albo `−` (spadek, niska cena). Para to ten sam warunek odbity: ceny i różnice ze znakiem przeciwnym, ten sam próg. ID `FX-0001` … `FX-1000`; para = kolejne numery, nieparzysty `+`, parzysty `−`.
- Każda okoliczność ma: rodzinę, opis słowny po polsku, definicję formalną (rodzaj + wszystkie parametry liczbami) i próg.
- **Wskaźniki:** wzory z sekcji 8.2 (SMA, EMA, WMA, HMA, DEMA, TEMA, KAMA, ZLEMA, ATR, RSI — w module FX także z innymi okresami niż 14) oraz wskaźniki z tabeli 4c.3. VWMA nie jest używana (EURUSD nie ma wolumenu).
- **Kalibracja tylko raz** — `python -m ia4.fx.catalog --commit` (krok FX-1; odmawia, gdy `fx/conditions.json` już jest na branchu `fx`): próg każdej pary dobierany na danych dostępnych w tej chwili tak, żeby okoliczność była prawdziwa na 15%, 25% albo 40% świec (cel kandydata), a każda z dwóch okoliczności pary — w przedziale 10–50%; próg zaokrąglony. Szczegóły: 4c.3. Zapis w `fx/conditions.json`: katalog, progi, data kalibracji, zakres danych, częstość każdej okoliczności przy kalibracji.
- **Katalog jest nienaruszalny** (zasada 14): po kalibracji ID, definicje i progi nigdy się nie zmieniają, okoliczności nie są dodawane ani usuwane — dzięki temu ratingi kolejnych przeliczeń (na większej ilości danych) są porównywalne. Każde przeliczenie liczy częstość; okoliczność poza 10–50% dostaje znacznik „częstość poza zakresem” i nic więcej. Nowy katalog — tylko jako `fx-cond/2`, za zgodą człowieka, obok starego.

#### 4c.3 Rodziny okoliczności i wskaźniki (`ia4/fx/catalog.py`, `ia4/fx/series.py`)

**Zasady wspólne:**
- Okoliczność = **cecha f** (liczba na świecy `t`, tylko ze świec ≤ `t`) i warunek **f ≥ próg**. Cecha jest zbudowana tak, że duża wartość = wzrost / wysoka cena. Okoliczność `+` liczy f na serii zwykłej, jej para `−` — tę samą f na **serii odbitej** (`o' = −o`, `c' = −c`, `h' = −l`, `l' = −h`), z tym samym progiem. Wszystkie wielkości są różnicowe (pipsy albo jednostki U), więc odbicie jest dokładne: np. SMA(−c) = −SMA(c), RSI(−c) = 100 − RSI(c), maksimum ↔ minimum.
- Wartość niepoliczalna (NaN) → warunek fałszywy. Wskaźniki na całej serii od pierwszej świecy.
- **U** = ATR(100) Wildera (8.2) — jednostka zmienności; „[ATR100]” w opisie = wartość podzielona przez U.
- **Średnie** (MA): SMA, EMA, WMA, HMA, DEMA, TEMA, KAMA, ZLEMA — wzory 8.2; okresy 9, 20, 38, 50, 103, 200, 288 (288 = doba).
- **Rozgrzewka** = pierwsze 1000 świec serii: nie są wystąpieniami i nie liczą się do częstości (najdłuższy wskaźnik, TEMA288, potrzebuje 864 świec).
- Częstość = udział świec spełniających warunek wśród świec serii po rozgrzewce, bez uśrednionych.
- Opis każdej okoliczności po polsku generuje kod; strona `−` opisuje tę samą wielkość „≤ −próg” (albo minimum zamiast maksimum, czerwone zamiast zielonych).

**Rodziny** (kolejność, nazwa, limit par, cechy):

| # | Rodzina | Limit | Cechy f (rodzaj: wzór; parametry) |
|---|---|---|---|
| 1 | Zmiana ceny (pips) | 35 | `chg_pips`: (c[t] − c[t−n]) / pips; n = 1, 2, 3, 4, 6, 9, 12, 18, 24, 36, 48, 72, 96, 144, 288 |
| 2 | Kierunkowość ruchu i korpusów | 20 | `er_signed`: (c[t] − c[t−n]) / Σ\|Δc\| z n świec (0, gdy mianownik 0); n = 6, 9, 12, 18, 24, 36, 48, 72, 96, 144, 288 · `body_er`: Σ(c−o) / Σ\|c−o\| z n świec; n = 6, 12, 24, 48, 96 |
| 3 | Kolory świec | 25 | `green_cnt`: liczba świec z c > o wśród ostatnich n; n = 4, 6, 8, 10, 12, 15, 20, 30, 40, 50, 75, 100 |
| 4 | Serie świec i położenie zamknięcia | 15 | `streak_green`: długość bieżącej serii świec c > o · `hhhl_streak`: seria świec z h > h[t−1] i l > l[t−1] · `clv`: średnia z n świec ((c−l) − (h−c)) / (h−l) (0, gdy h = l); n = 1, 3, 6, 12, 24, 48 |
| 5 | Cena a średnia krocząca | 50 | `px_vs_ma`: (c − MA_n) / U; każda MA × każdy okres |
| 6 | Nachylenie średniej | 40 | `ma_slope`: (MA_n[t] − MA_n[t−k]) / U; k = 3, 12; każda MA × każdy okres |
| 7 | Rozstaw dwóch średnich | 50 | `ma_spread`: (MA1 − MA2) / U; pary mieszane: EMA9–EMA20, EMA20–EMA50, SMA20–SMA50, EMA38–KAMA103, SMA50–SMA200, HMA20–EMA50, DEMA20–SMA103, EMA103–EMA288, WMA9–SMA38, KAMA20–KAMA103; pary tego samego typu: każda MA × okresy (9,20), (9,38), (20,50), (20,103), (38,103), (50,200), (103,288), (20,200) |
| 8 | Przecięcia średnich i ceny | 40 | `ma_cross`: −(świec od przecięcia MA1 w górę przez MA2), tylko gdy MA1 > MA2 (inaczej NaN); pary mieszane z rodziny 7; wariant „pod prąd”: liczą się tylko przecięcia, gdy MA2 spadała (MA2[t] − MA2[t−6] < 0) · `px_cross`: −(świec od przecięcia ceny w górę przez MA), tylko gdy c > MA; EMA20, SMA50, KAMA103, EMA200, SMA288, HMA50, DEMA103, TEMA200, ZLEMA38 |
| 9 | Dynamika rozstawu średnich | 40 | `spread_pattern`: d = MA1 − MA2 > 0; seria = kolejne świece, na których d rośnie (albo maleje); zmiana 0 przerywa serię. „fade”: długość bieżącej serii spadków d, gdy poprzedzała ją seria wzrostów ≥ j; „grow”: odwrotnie; j = 2, 3, 5; pary mieszane z rodziny 7 + EMA, SMA, KAMA × (9,38), (20,103), (50,200) |
| 10 | Położenie w zakresie (stochastic) | 30 | `stoch`: (c − LL_n) / (HH_n − LL_n) − 0,5, HH/LL = maksimum h / minimum l z n świec (0, gdy zakres 0); n = 12, 18, 24, 36, 48, 96, 144, 288 · `stoch_sm`: średnia z s wartości `stoch`; (n, s) = (24,3), (48,6), (96,12), (288,24) |
| 11 | Wybicia i odległość od ekstremum | 25 | `breakout`: −(świec od ostatniego c > HH_n poprzednich n świec); n = 12, 24, 36, 48, 72, 96, 144, 288 · `dist_high`: −(HH_n − c) / U; n = 12, 24, 48, 96, 144, 288 |
| 12 | RSI | 25 | `rsi`: RSI_n − 50 (Wilder, 8.2); n = 5, 7, 9, 14, 21, 30, 50, 100 · `rsi_slope`: RSI_n[t] − RSI_n[t−k]; (n, k) = (14,3), (14,6), (14,12), (7,3), (7,6), (30,6), (30,12) |
| 13 | Odchylenie od średniej (Bollinger) | 25 | `boll_z`: (c − SMA_n) / σ_n, σ = odchylenie standardowe populacji c z n świec (0, gdy σ = 0); n = 10, 12, 20, 30, 50, 75, 100, 150, 200, 288 · `z_slope`: z[t] − z[t−k]; (n, k) = (20,3), (20,6), (50,6), (50,12), (100,12) |
| 14 | MACD | 25 | linia = EMA_f − EMA_s, sygnał = EMA_g(linia), histogram = linia − sygnał; `macd` część „line”: linia / U, „hist”: histogram / U, „hist_slope”: (hist[t] − hist[t−3]) / U; (f, s, g) = (12,26,9), (6,13,5), (24,52,18), (48,104,36), (5,35,5) |
| 15 | Knoty świec | 15 | `wick`: Σ(dolny knot − górny knot) z n świec / (n · U); dolny = min(o,c) − l, górny = h − max(o,c); n = 1, 3, 6, 12, 24, 48 |
| 16 | Doba, tydzień, poprzednia doba | 15 | segment: doba UTC, doba handlowa (od 17:00 Nowy Jork), tydzień (od pierwszej świecy po przerwie) · `sess_chg`: (c − otwarcie pierwszej świecy segmentu) / pips · `sess_chg_u`: to samo / U · `day_pos`: (c − min l) / (max h − min l) − 0,5 od początku segmentu · `prev_day`: (c − zamknięcie / maksimum / minimum poprzedniej doby handlowej) / U |
| 17 | Trend i korekta | 25 | trend: c > MA (EMA200, SMA288, KAMA103, EMA103), inaczej NaN · `combo_pull`: −(c[t] − c[t−m]) / pips, m = 3, 6, 12, 24 · `combo_rsi`: 50 − RSI14 · `combo_stoch`: −`stoch`(24) |

**Kalibracja** (`python -m ia4.fx.catalog --commit`, raz):
1. Kandydaci w stałej kolejności: rodziny 1→17; w rodzinie najpierw wszystkie cechy z celem częstości 25%, potem 15%, potem 40%.
2. Próg kandydata: wartości f ze strony `+` i `−` razem (po rozgrzewce, bez uśrednionych), próg = wartość, powyżej której leży udział równy celowi; zaokrąglenie do 2 cyfr znaczących, a dla cech całkowitych (liczby świec) — do liczby całkowitej dającej udział najbliższy celowi. Kandydat przepada, gdy którakolwiek strona wypada poza 10–50% albo ten sam warunek (rodzaj, parametry, próg) już był.
3. Wybór: kandydaci po kolei, w granicach limitu rodziny, jeśli korelacja (phi) ze stroną `+` każdej już wybranej okoliczności ≤ 0,85; potem drugi przebieg z progiem 0,95. Gdy par jest mniej niż 500, brakujące miejsca dostają kolejne rodziny po jednym kandydacie (0,85 → 0,95 → bez progu).
4. ID w kolejności rodzin, a w rodzinie — kolejności wyboru; para = `FX-(2i−1)` `+` i `FX-(2i)` `−`.
5. Zapis `fx/conditions.json` (4c.12) — każda okoliczność: ID, para, kierunek, rodzina, rodzaj, parametry, próg, cel, częstość przy kalibracji, opis.

Kalibracja próbna (`python -m ia4.fx.catalog`, bez `--commit`) robi to samo, ale zapisuje tylko lokalny podgląd `data/fx/catalog-preview.csv` (otwiera się w Numbers/Excel) i nic nie wysyła. Test na danych syntetycznych: `python -m ia4.fx.selftest` — lustro, brak zaglądania w przyszłość, 1000 okoliczności w 10–50%, powtarzalność, synchronizacja; wynik musi brzmieć „WYNIK: OK”.

#### 4c.4 Wystąpienia i profil

- **Wystąpienie** okoliczności = każda świeca `t` po rozgrzewce (4c.3), na której okoliczność jest prawdziwa, jeśli świeca `t` nie jest uśredniona i w oknie `t … t+48` nie ma przerwy.
- Dla wystąpienia zapisujemy zmiany ceny `r_k = (c[t+k] − c[t]) / 0,0001` (pipsy), k = 1…48. Zmiany nie ma, gdy świeca `t+k` jeszcze nie istnieje (koniec danych) albo jest uśredniona.
- **Profil** okoliczności = dla każdego k średnia `r_k` ze wszystkich wystąpień, które ją mają (48 liczb), oraz liczba wystąpień.
- **Niezależne wystąpienia** `n_ind` = wystąpienia wybierane od najstarszego tak, że każde kolejne jest co najmniej 48 świec po poprzednim wybranym.
- Lokalnie (poza gitem): `data/fx/occurrences.npz` — każde wystąpienie każdej okoliczności (ID, `t`, 48 zmian); przepisywany przy każdym przeliczeniu. Na GitHub trafiają tylko profile.

#### 4c.5 Rating 1–100

Rating mówi, o ile profil okoliczności przewidywał przyszłość lepiej niż prognoza „cena się nie zmieni”, **sprawdzone poza próbą**:

1. Świece serii dzielone w czasie: **część ucząca** = pierwsze 70%, **część oceny** = ostatnie 30%. Wystąpienie należy do części swojej świecy `t`; wystąpienie części uczącej, którego okno sięga do części oceny, jest pomijane.
2. **Profil uczący** `P_k` = profil z wystąpień części uczącej.
3. Dla każdego wystąpienia części oceny i każdego dostępnego k: błąd okoliczności `|r_k − P_k|`, błąd „bez zmiany” `|r_k|`.
4. **Przewaga** `S = 1 − Σ błąd okoliczności / Σ błąd „bez zmiany”` (sumy po wszystkich wystąpieniach i k części oceny).
5. Ściągnięcie przy małej liczbie danych: `S* = S · n / (n + 20)`, gdzie n = `n_ind` części oceny.
6. **Rating** = 1, gdy `S* ≤ 0`, część ucząca ma mniej niż 30 wystąpień albo n < 5; w pozostałych przypadkach `1 + round(99 · min(S* / RATING_FULL; 1))`, `RATING_FULL` = 0,05 (błąd o 5% mniejszy niż „bez zmiany” daje 100). Skala jest stała, więc ratingi z różnych przeliczeń można porównywać.

**Profil publikowany** (do prognozy na żywo) = profil ze wszystkich wystąpień całej historii.

#### 4c.6 Prognoza

Na ostatniej zamkniętej świecy `t`:
- A = okoliczności prawdziwe na `t` (ten sam kod co w backteście),
- dla k = 1…48: `prognoza_k = c[t] + 0,0001 · Σ(rating_i · profil_i[k]) / Σ rating_i` po okolicznościach z A, które mają `profil_i[k]`,
- A puste → brak prognozy,
- prognoza kończy się na zamknięciu rynku (piątek 17:00 Nowy Jork) — świece po zamknięciu nie są pokazywane.

#### 4c.7 Sprawdzian systemu

Każde przeliczenie FX-research sprawdza całą prognozę bez zaglądania w przyszłość: ratingi według 4c.5 policzone tylko na pierwszych 70% serii (część ucząca: pierwsze 50%, część oceny: 50–70%), profile z pierwszych 70%, prognoza (4c.6) na każdej świecy ostatnich 30%, której okno nie ma przerwy. Wynik: przewaga `S` całej prognozy nad „bez zmiany” dla k = 1, 6, 12, 24, 48 i dla wszystkich k razem, trafność kierunku (znak prognozy = znak `r_k`) dla k = 12 i 48, liczba świec. Tylko informacja — nie zmienia ratingów.

#### 4c.8 FX-research — `python -m ia4.fx.research`

Tylko ręcznie. Kolejno: synchronizacja (4c.1) → klon brancha `fx` w `ia4-research/fx-repo/` → katalog z `fx/conditions.json` (bez niego program kończy się komunikatem — najpierw kalibracja, 4c.2) → wszystkie wystąpienia i profile od zera (4c.4) → ratingi (4c.5) → sprawdzian (4c.7) → zapis i push na branch `fx`: `fx/ratings.json`, dopisany wiersz `fx/runs.jsonl`, `index.html` (kopia dashboardu z `ia4/fx/dashboard/`). Każde przeliczenie ma ID `R-001`, `R-002`, … Opcje: `--no-sync`, `--no-push`.

#### 4c.9 FX-real-time — `python -m ia4.fx.live`

- **Start:** synchronizacja (4c.1), profile i ratingi z `fx-repo/fx/ratings.json` (bez tego pliku program się nie uruchamia — najpierw FX-research), prognoza na ostatniej świecy, publikacja.
- **Pętla co 30 s:**
  - poza godzinami rynku (4b) — żadnych odczytów Firestore,
  - gdy minęło zamknięcie świecy nowszej niż ostatnia znana + 20 s: 1 odczyt `fx/EURUSD` (podsumowanie); jeśli `lastTime` jest nowszy — odczyt dokumentu dnia (przy zmianie dnia UTC — dwóch), nowe świece do kopii lokalnej, prognoza, publikacja; jeśli nie — kolejna próba za 30 s,
  - co 2 min sygnał życia (`aliveAt`), także bez nowej świecy i przy zamkniętym rynku,
  - gdy `fx-repo/fx/ratings.json` się zmienił (nowe przeliczenie FX-research w trakcie pracy) — przy następnej świecy program bierze nowe ratingi.
- **Publikacja:** `forecast.json` na branchu `fx-live` — zawsze jeden commit bez historii (force push), klon w `ia4-research/fx-live-repo/`. Zawartość: wersja, `aliveAt`, `generatedAt`, przeliczenie ratingów (ID, data), ostatnie 48 świec (czas, o, h, l, c), prognoza (czas, cena) dla k = 1…48, liczba okoliczności prawdziwych i suma ich ratingów, wynik sprawdzianu (4c.7) z tego przeliczenia.
- **Firestore:** ok. 300–600 odczytów na dzień pracy przy otwartym rynku.

#### 4c.10 Dashboard

- **Adres:** GitHub Pages z brancha `fx` (`index.html`) — `https://miszyszka.github.io/IA4/`. Jednorazowo: GitHub → Settings → Pages → Branch `fx`, folder `/` (repozytorium publiczne).
- Strona co 30 s czyta `forecast.json` z brancha `fx-live` przez API GitHub (zapytania warunkowe, bez tokenu).
- Pokazuje: wykres świecowy ostatnich 48 świec + linię prognozy 48 zamknięć, czasy PL, **status Maca** („połączony”, gdy `aliveAt` jest młodszy niż 5 min; inaczej „Mac offline od …”, a prognoza jest wyszarzona z czasem jej wyliczenia), „rynek zamknięty”, wiek prognozy, liczbę okoliczności prawdziwych, przeliczenie ratingów i wynik sprawdzianu.

#### 4c.11 Arkusz OKOLICZNOSCI_FX (`Fx.gs`)

- Wypełnia go Apps Script w triggerze `researchSync` (co 30 min) z `fx/conditions.json` i `fx/runs.jsonl` (branch `fx`, token `GITHUB_TOKEN`), tylko gdy przybyło przeliczeń (Script Properties `FX_RUNS`).
- **Wiersze:** okoliczności — ID, rodzina, kierunek, para, opis, próg, częstość przy kalibracji %.
- **Kolumny po prawej:** jedno przeliczenie FX-research = jedna kolumna (najstarsze z lewej). Komórka `rating/wystąpienia`, np. `41/344` (wystąpienia z całej historii); okoliczność z częstością poza 10–50% — komórka szara. Nagłówek kolumny: ID przeliczenia, data, liczba świec, przewaga `S` sprawdzianu dla wszystkich k.

#### 4c.12 Branche `fx` i `fx-live`

Pisze je wyłącznie Python z Maca.

```
fx (FX-research):
  index.html          dashboard (kopia ia4-research/ia4/fx/dashboard/index.html)
  fx/README.md
  fx/conditions.json  katalog fx-cond/1 z progami — zapisuje go raz `python -m ia4.fx.catalog --commit`, nienaruszalny
  fx/ratings.json     ostatnie przeliczenie: dla każdej okoliczności rating, wystąpienia, n_ind, S, częstość, znacznik, profil (48)
  fx/runs.jsonl       wiersz na każde przeliczenie: ID, czas, wersja, zakres danych, liczba świec, sprawdzian, rating / wystąpienia / częstość każdej okoliczności

fx-live (FX-real-time, jeden commit, force push):
  forecast.json
```

---

## 5. Kopia lokalna na Macu (`ia4-research/`)

```bash
cd ia4-research && source .venv/bin/activate
python -m ia4.sync            # przyrostowo: nowe sesje + wszystko przepisane od ostatniego razu
python -m ia4.sync --full     # od nowa (~48 000 odczytów = prawie cały dzienny limit — tylko w razie awarii kopii)
```

Wynik: `data/{SYMBOL}.parquet`, jedna tabela na instrument, kolumny `symbol, date, slot (1–7), o, h, l, c, v`, posortowana po `(date, slot)`; `data/_manifest.json` pamięta stan synchronizacji. Oba formaty Firestore sprowadzone do tej samej tabeli. W kodzie: `from ia4.sync import load; df = load("AAPL")`. Instalacja i klucz: `ia4-research/README.md`.

---

## 6. Skarbiec — najstarsze 800 świec

- **Definicja:** dla każdego instrumentu osobno — jego 800 najwcześniejszych świec w bazie, w kolejności `(date, slot)`. Dla spółek z pełną historią to mniej więcej wrzesień 2024 – luty 2025. Wszystko po skarbcu to **grupa główna**.
- **Dlaczego z początku:** Yahoo nie oddaje danych starszych niż ~730 dni, więc baza nigdy nie urośnie wstecz — skarbiec jest stały na zawsze, a grupa główna rośnie każdego dnia.
- **Zasada:** poszukiwanie (siatka, adaptacja, wszystkie sita) widzi wyłącznie wyniki grupy głównej. Skarbiec może być otwierany wielokrotnie — każde otwarcie dotyczy innej strategii i zadaje danym inne pytanie — ale tylko przez bramkę skarbca (sekcja 9.4), dla strategii obiecującej na grupie głównej, która nie jest duplikatem strategii już sprawdzonej w skarbcu. Każde otwarcie jest liczone (`vault_peeks`) i zapisywane w `research/vault.jsonl`, także gdy strategia przepadnie.
- **Egzekwowanie kodem:** procesy robocze zerują wyniki skarbca, zanim oddadzą wynik (`worker.evaluate`). Wyniki skarbca zwraca tylko `worker.open_vault`, wołane wyłącznie przez `Lab._open_vault` w `search.py`.
- **Przypisanie transakcji:** transakcja należy do strefy świecy wejścia. Wskaźniki liczone są na ciągłej serii instrumentu (także przez granicę skarbca).

## 6a. doubleProof — druga grupa kontrolna

- 20 spółek spoza grupy głównej i kontrolnej (sekcja 4), zbierane tak samo jak pozostałe: na żywo, nocne odświeżenie, pełna historia do granicy Yahoo.
- **Poszukiwanie nigdy ich nie używa** — ani grupa główna, ani skarbiec, ani sita. `python -m ia4.lab` bierze tylko `main` + `proof` z `system/universe`; bez Firestore wyklucza doubleProof po liście w `ia4/config.py` i po polu `group` w manifeście synchronizacji.
- Paper trading (sekcja 11a) też ich nie używa.
- Służą do weryfikacji strategii na spółkach, których system nigdy nie widział. Synchronizacja (`python -m ia4.sync`) ściąga je na Maca jak pozostałe instrumenty.

**Weryfikacja (`ia4/lab/verify.py`):**
- strategie aktywne (`research/strategies/`) liczone tym samym silnikiem i na tych samych zasadach (sekcja 8) na wszystkich 20 spółkach doubleProof, bez skarbca — każda transakcja się liczy; instrument z historią krótszą niż 200 świec jest pomijany; SPY/QQQ jak zwykle tylko do filtrów,
- dla każdej strategii: liczba transakcji, mediana świec w pozycji (`hold_median`; obok `search_hold_median` z poszukiwania), PF, PF na ślepo i przewaga (na doubleProof), skuteczność (TP), udziały wyjść SL / FC / limit, średni wynik FC i całej transakcji, PF w 4 okresach (podział historii doubleProof na 4 równe części), liczba spółek z transakcjami i z PF > 1, wyniki każdej spółki, a obok PF ważony z poszukiwania (8.6 p. 11) do porównania,
- **tylko informacja:** wynik nie przyjmuje, nie odrzuca i nie zmienia strategii i nie wraca do poszukiwania,
- kiedy: `python -m ia4.lab` przy starcie, a potem **co godzinę** (`dp_refresh_min` = 60): dociąga z Firestore nowe świece doubleProof (+ SPY, QQQ; ok. 250 odczytów) i przelicza **wszystkie** aktywne strategie na pełnych, aktualnych danych. Przy logach co 30 min pomiędzy odświeżeniami — przelicza tylko, gdy zmienił się zestaw strategii. Ręcznie: `python -m ia4.lab.verify` (synchronizacja + przeliczenie wszystkich + push),
- wynik: `research/doubleproof.json` (branch `research`); wyniki strategii, które wypadły z aktywnych, zostają w pliku z `active: false`,
- od wersji 1.16 bez osobnego arkusza (plik zostaje na branchu `research`).

**Jednorazowy backtest (`ia4/lab/backtest_dp.py`):**
- `python -m ia4.lab.backtest_dp` — synchronizacja doubleProof (+ SPY, QQQ), potem wszystkie strategie aktywne liczone dokładnie tak jak w weryfikacji (te same funkcje, te same wyniki na strategię, plus suma wyników %), zapis i push,
- wynik: `research/backtest-doubleproof.json` (branch `research`) — **zapisany raz**: data backtestu, zakres danych, wyniki wszystkich strategii i każdej spółki. Weryfikacja go nie przelicza; istniejący zapis zmienia tylko ponowne uruchomienie z `--force`,
- tylko informacja, jak weryfikacja: nie zmienia strategii ani poszukiwania,
- wynik każdej strategii pokazuje arkusz STRATEGIE (sekcja 11).

## 6b. Backtest portfela (`ia4/lab/portfolio.py`)

Jednorazowa symulacja wirtualnego inwestora na historii: wszystkie strategie aktywne naraz, na grupie głównej (53 spółki, osobno okresy 1–4 i skarbiec) i na doubleProof (20 spółek, całość i 4 okresy). Tylko informacja — nie zmienia strategii ani poszukiwania.

- **Transakcje:** każda liczona tym samym silnikiem co strategie (8.6), osobno dla każdego sygnału; dla pojedynczej strategii bez limitu wynik jest identyczny z backtestem strategii.
- **Zasady portfela:** limit pozycji na spółkę — brak (każda strategia osobno, jak dawniej) albo 1 (spółka zajęta przez dowolną strategię → sygnał pominięty, jak w 8.6 p. 5); przy kilku sygnałach na tej samej spółce i świecy wygrywa strategia z wyższym pierwszeństwem; koszt `COST_PCT` przy wejściu i przy wyjściu (wynik netto = wynik − 2 × 0,005 pkt proc.); stawka stała 100 $ albo według SL: 100 $ × 5 / SL% (strata na SL ok. 5 $ niezależnie od SL).
- **Szacunek przewagi i pierwszeństwo:** średni wynik transakcji każdej strategii na doubleProof „ściągnięty” do średniej wszystkich strategii (empiryczny Bayes): waga własnego wyniku = τ² / (τ² + σ²/n), gdzie σ — rozrzut pojedynczej transakcji (wszystkie strategie razem), τ² — rozrzut prawdziwych przewag (wariancja średnich strategii minus średnia wariancja losowa, najmniej 0,02), n — transakcje strategii. Kolejność według szacunku = **pierwszeństwo** (`priority`). **Wybrane** = szacunek ≥ 0,40% na transakcję.
- **Warianty:** (1) dziś: wszystkie, bez limitu, 100 $, bez kosztów; (2) wszystkie, 1 na spółkę, koszty; (3) wybrane, 1 na spółkę, koszty; (4) i (5) — jak (2) i (3) ze stawką według SL.
- **Dla każdego wariantu i zbioru:** transakcje, PF (z wyników w $), średni wynik % netto, wynik $, maksymalne obsunięcie $ (krzywa wg świecy wyjścia), wynik / obsunięcie, udziały TP / SL / FC / limit, mediana świec w pozycji, wynik $ long i short, liczba spółek.
- „Wybrane” wybrano według doubleProof, więc ich wynik na doubleProof jest zawyżony — uczciwą ocenę wyboru dają grupa główna i skarbiec.
- **Uruchomienie:** `python -m ia4.lab.portfolio` (synchronizacja, przeliczenie, zapis, push); istniejący zapis zmienia tylko `--force`.
- **Wynik:** `research/portfolio-backtest.json` (branch `research`, zapisany raz) → arkusz BACKTEST PORTFELA (sekcja 11); lista `priority` → pierwszeństwo strategii w wirtualnym inwestorze (11a).

---

## 7. Etapy

Status: ⬜ nie rozpoczęty · 🟨 w toku · ✅ zakończony

### Etap 1 — Baza danych ✅ (zamknięty 30.09.2026)

Wersja 1.0 wdrożona w Apps Script, triggery `runCollector` i `telemetryHourly`, synchronizacja na Macu działa. Automat pracuje dalej bez końca. Pierwsze nocne odświeżenie i liczba świec w bazie pojawią się w `telemetry/state.json` (pola `nightly`, `base`) — jeśli ich nie ma po nocy sesyjnej, to błąd do naprawy.

### Etap 2 — Poszukiwanie strategii 🟨

Program `python -m ia4.lab` na Macu (sekcje 8–10), wyniki na branchu `research` (arkusz RESEARCH usunięty w 1.16 — poszukiwanie wstrzymane). Etap trwa bez końca; Claude okresowo przegląda wyniki i proponuje zmiany ustawień w `research/config.json`.

Wdrożony 30.09.2026: triggery `runCollector`, `telemetryHourly`, `researchSync`; `python -m ia4.lab.selftest` kończy się „WYNIK: OK”; branch `research` ma `status.json` i `log.jsonl`; arkusze RESEARCH i STRATEGIE się odświeżają. Siatka zakończona 1.10.2026, od tego czasu adaptacja. **3.10.2026 poszukiwanie wstrzymane** (`search_closed: true` w `research/config.json`): zostaje 60 aktywnych strategii, `python -m ia4.lab` tylko synchronizuje, sprawdza bazę i przelicza weryfikację doubleProof.

### Etap 3 — Paper trading 🟨

Sygnały strategii na żywo i wirtualny inwestor w Apps Script (sekcja 11a). Działa bez Maca, przy każdej zamkniętej świecy. Wdrożony, gdy:
- 3.1 `Paper.gs` i `PaperEngine.gs` są w Apps Script, a pierwsze przeliczenie zbudowało pamięć świec (ukryty arkusz `_IA4_DANE`),
- 3.2 SIGNALS-REALTIME dostaje wiersz po każdej świecy sesji,
- 3.3 VIRTUAL-INVESTOR otwiera i zamyka transakcje dla strategii zaznaczonych „for VI” w arkuszu STRATEGIE.

### Etap 4 — Prognoza EURUSD 🟨

Prognoza kursu EURUSD na 48 świec 5-minutowych (sekcja 4c). Kolejne kroki — każdy zamyka się zgodą człowieka:
- **FX-0** — ta sekcja instrukcji (wersja 1.20),
- **FX-1** — synchronizacja `fx/EURUSD` → `data/fx/` (`python -m ia4.fx.sync`), katalog 1000 okoliczności (4c.3), kalibracja próbna i właściwa (`python -m ia4.fx.catalog [--commit]`) → `fx/conditions.json`, test `python -m ia4.fx.selftest` — kod gotowy w 1.21; zamknięty, gdy `fx/conditions.json` jest na branchu `fx`,
- **FX-2** — FX-research: wystąpienia, profile, ratingi, sprawdzian → `fx/ratings.json`, `fx/runs.jsonl`,
- **FX-3** — arkusz OKOLICZNOSCI_FX (`Fx.gs`, trigger `researchSync`),
- **FX-4** — FX-real-time i dashboard (GitHub Pages z brancha `fx`, dane z `fx-live`).

Wdrożony, gdy: `fx/conditions.json` jest na branchu `fx` (1000 okoliczności, każda w 10–50% przy kalibracji), FX-research zapisało pierwsze przeliczenie, arkusz OKOLICZNOSCI_FX ma jego kolumnę, a dashboard pokazuje prognozę i status Maca.

---

## 8. Język reguł `ia4-rule/1`

Implementacja wzorcowa: `ia4-research/ia4/lab/rules.py`, `indicators.py`, `sim.py`. Oznaczenia: `t` — indeks świecy w ciągłej serii jednego instrumentu (świece w kolejności `(date, slot)`, przez noce i weekendy bez przerw); `x[t−k]` — wartość k świec wcześniej; `c, o, h, l, v` — close, open, high, low, wolumen. Wartość, której nie da się policzyć (za krótka historia, brak danych), to **brak**; porównanie z brakiem jest zawsze fałszywe.

### 8.1 Struktura reguły

```json
{
  "schema": "ia4-rule/1",
  "direction": "long",
  "lines":   {"A": {"ma": "EMA", "n": 21}, "B": {"ma": "SMA", "n": 60}},
  "signal":  {"kind": "converge", "grow": 3, "shrink": 2},
  "filters": [{"f": "rsi", "op": "<", "x": 45.0}],
  "exit":    {"sl": 3, "tp": 5, "max_bars": 35, "fc": [{"kind": "reexpand", "n": 2}]}
}
```

- `direction`: `long` albo `short`.
- `lines`: 1–3 średnie z ceny close: `A` (najkrótsza), `B`, `C`; okres `n` 5–150. W poszukiwaniu okresy rosną A < B < C (dwie linie mogą mieć ten sam okres tylko przy różnych typach).
- `signal`: rodzaj i parametry sygnału (8.3); sygnał powstaje na zamknięciu świecy `t`.
- `filters`: 0–2 warunki `cecha op próg`, `op` to `>` albo `<` (8.4); wszystkie muszą być spełnione na świecy `t`.
- `exit`: `sl` i `tp` w procentach ceny wejścia (liczby całkowite 1–10), `max_bars` — limit czasu w świecach albo `null`, `fc` — lista warunków force close (8.5), może być pusta.
- Identyfikator strategii: `S-` + pierwsze 10 znaków SHA-1 z kanonicznego JSON reguły (klucze posortowane, bez spacji).

### 8.2 Średnie kroczące i wskaźniki

| Typ | Wzór |
|---|---|
| `SMA` | średnia arytmetyczna `c` z ostatnich n świec |
| `EMA` | `e[t] = e[t−1] + α·(c[t] − e[t−1])`, α = 2/(n+1); start: `e` na n-tej świecy = SMA z pierwszych n |
| `WMA` | średnia ważona liniowo: najnowsza świeca waga n, najstarsza 1 |
| `HMA` | `WMA( 2·WMA(c, ⌊n/2⌋) − WMA(c, n), ⌊√n⌋ )` |
| `DEMA` | `2·E1 − E2`, gdzie E1 = EMA(c, n), E2 = EMA(E1, n) |
| `TEMA` | `3·E1 − 3·E2 + E3`, E3 = EMA(E2, n) |
| `KAMA` | Kaufman: ER = \|c[t] − c[t−n]\| / Σ\|c[i] − c[i−1]\| (n kroków; mianownik 0 → ER = 0), sc = (ER·(2/3 − 2/31) + 2/31)², `k[t] = k[t−1] + sc·(c[t] − k[t−1])`; start: `k` na świecy n−1 = c tej świecy, pierwsza wartość na świecy n |
| `VWMA` | Σ(c·v)/Σv z n świec; wolumen 0 ma wagę 0; Σv = 0 → brak |
| `ZLEMA` | EMA(n) z serii `2·c[t] − c[t−lag]`, lag = ⌊(n−1)/2⌋ |

EMA liczona z serii, która zaczyna się brakami (E2, E3, ZLEMA), startuje od SMA pierwszych n dostępnych wartości.

- **ATR14** (Wilder): TR[0] = h−l, dalej TR = max(h−l, \|h−c[t−1]\|, \|l−c[t−1]\|); start: średnia TR z pierwszych 14 świec, dalej `ATR = (ATR·13 + TR)/14`.
- **RSI14** (Wilder): start ze średnich zysków i strat pierwszych 14 zmian, dalej wygładzanie `(x·13 + nowy)/14`; brak strat → 100.

Wszystko liczone osobno dla każdego instrumentu, na ciągłej serii przez noce i weekendy.

### 8.3 Sygnały (dla `long`; `short` — lustrzanie)

`d = A − B`. Sygnał na świecy `t` wymaga co najmniej 3 wcześniejszych świec instrumentu (`converge`: grow + shrink + 2).

| `kind` | Parametry | Sygnał long na świecy t | Sygnał short |
|---|---|---|---|
| `cross` | — | `d[t−1] ≤ 0` i `d[t] > 0` (A przecina B w górę) | `d[t−1] ≥ 0` i `d[t] < 0` |
| `converge` | `grow` G ≥ 1, `shrink` S ≥ 1 | A pod B (`d < 0`) na świecach t−G−S … t; \|d\| rosło przez G kolejnych kroków, a potem malało przez S kolejnych kroków kończących się na t (krok i rośnie, gdy \|d[i]\| > \|d[i−1]\|) — zapowiedź przecięcia w górę | A nad B, to samo dla \|d\| |
| `turn` | `pos`: `below` / `above` / `any` | A zawraca w górę: `A[t] > A[t−1]` i `A[t−1] ≤ A[t−2]`; `below`: dodatkowo A < B, `above`: A > B | A zawraca w dół: `A[t] < A[t−1]` i `A[t−1] ≥ A[t−2]`; `pos` znaczy to samo |
| `revert` | `k` > 0 | odchylenie wraca: `z = d / ATR14`, `z[t−1] ≤ −k` i `z[t] > −k` | `z[t−1] ≥ k` i `z[t] < k` |
| `ribbon` | — (3 linie) | układ `A > B > C` jest na t, a nie było go na t−1 | układ `A < B < C` nowy na t |
| `pcross` | — (1 linia) | cena przecina A w górę: `c[t−1] ≤ A[t−1]` i `c[t] > A[t]` | `c[t−1] ≥ A[t−1]` i `c[t] < A[t]` |

### 8.4 Cechy filtrów (wartość na świecy t)

| Cecha | Definicja |
|---|---|
| `ret7`, `ret35` | `(c[t]/c[t−n] − 1)·100`, n = 7 lub 35 |
| `vrel` | `v[t]` / średnia dodatnich wolumenów z 35 poprzednich świec; `v[t] = 0` → brak |
| `atrp` | `ATR14/c·100` |
| `atrrank` | percentyl `atrp` wśród ostatnich 350 świec (łącznie z bieżącą): odsetek wartości ≤ bieżącej × 100 |
| `rsi` | RSI14 |
| `slot` | numer świecy w sesji 1–7 |
| `dow` | dzień tygodnia 1–5 (1 = poniedziałek) |
| `gap` | `(open pierwszej świecy sesji / close ostatniej świecy poprzedniej sesji − 1)·100`, ta sama dla całej sesji |
| `d5`, `d20` | `(c[t] / średnia z close ostatnich świec n poprzednich sesji − 1)·100`, n = 5 lub 20 (trend dzienny) |
| `spy35`, `spy140`, `qqq35`, `qqq140` | na serii SPY/QQQ: `(c − EMA_n(c)) / ATR14`, wartość ze świecy o tej samej dacie i numerze; brak takiej świecy → brak |
| `zAB` | `(A − B) / ATR14` (ATR instrumentu) |
| `slopeA` | `(A[t] − A[t−3]) / ATR14` |
| `since` | liczba świec od ostatniego przecięcia A i B w dowolną stronę (warunki jak w `cross`); przecięcie na t → 0; nigdy → brak |

`zAB` i `since` wymagają linii B. Progi w poszukiwaniu: percentyle 10–90 cechy w grupie głównej (3 cyfry znaczące), dla `slot`, `dow`, `zAB`, `slopeA`, `since` — stałe listy z `space.py`. W zapisanej regule próg jest zwykłą liczbą.

### 8.5 Force close (FC)

FC to warunek sprawdzany na zamknięciu każdej świecy f ≥ e (e = świeca wejścia). Gdy zajdzie, pozycja jest zamykana po cenie open świecy f+1. Kilka warunków FC w regule — wygrywa najwcześniejszy.

| `kind` | Warunek dla pozycji long (short — lustrzanie) |
|---|---|
| `reexpand` (`n` = R ≥ 1) | przecięcie jeszcze nie nastąpiło (od świecy e nie było świecy z `d > 0`), A wciąż pod B na świecach f−R … f, a \|d\| rośnie przez R kolejnych kroków kończących się na f — średnie znów się rozchodzą. Po przecięciu warunek wygasa na stałe. Obowiązkowy dla `converge`. |
| `cross_back` | A przecina B w dół: `d[f−1] ≥ 0` i `d[f] < 0` |
| `turn_back` | A zawraca w dół: `A[f] < A[f−1]` i `A[f−1] ≥ A[f−2]` |
| `pcross_back` | cena przecina A w dół: `c[f−1] ≥ A[f−1]` i `c[f] < A[f]` |

### 8.6 Wykonanie i symulacja (zasady pesymistyczne)

1. **Wejście:** open świecy e = t+1 (następnej po sygnale, tego samego instrumentu). Sygnał na ostatniej świecy danych nie otwiera transakcji.
2. **Poziomy:** long: SL = P·(1 − sl/100), TP = P·(1 + tp/100); short odwrotnie; P = cena wejścia.
3. **Kolejność zdarzeń w świecy j ≥ e:**
   1. (tylko j > e) luka na otwarciu: open za SL → wyjście po **cenie otwarcia**; open za TP → wyjście po **poziomie TP** (bez premii za lukę),
   2. FC z zamknięcia świecy j−1 → wyjście po open świecy j,
   3. SL w trakcie świecy (long: low ≤ SL) → wyjście po poziomie SL,
   4. TP w trakcie świecy (long: high ≥ TP) → wyjście po poziomie TP — **gdy SL i TP w tej samej świecy, zawsze SL**,
   5. limit czasu: świeca j = e + max_bars − 1 → wyjście po close (transakcja „nierozstrzygnięta”).
4. **Brak wyjścia do końca danych** → transakcja anulowana (nie liczy się do wyników, jest liczona osobno).
5. **Jedna pozycja naraz** na instrument i strategię; sygnał na świecy t jest pomijany, jeśli t < świeca wyjścia poprzedniej transakcji.
6. **Zwrot:** long `(wyjście/P − 1)·100`, short `(P − wyjście)/P·100`. Koszty = 0.
7. **Wyniki** dla każdej kombinacji SL × TP i każdej strefy (skarbiec, okresy 1–4 grupy głównej): liczba transakcji, zyskownych, suma zysków, suma strat, liczba wyjść SL / TP / FC / limit / anulowanych.
8. **Profit factor (PF)** = suma zysków % / suma strat %; bez strat i z zyskiem → 99 (sufit).
9. **Hipotezy SL × TP:** każda reguła jest symulowana zawsze na pełnej siatce SL 1–10% × TP 1–10% (100 hipotez). Zapisana strategia ma jedną parę SL/TP i pełną macierz PF wszystkich 100 hipotez.
10. **Wejście „na ślepo”** (punkt odniesienia): każda świeca grupy głównej od 150. świecy instrumentu jest sygnałem, ten sam kierunek, SL, TP i limit, bez FC, jedna pozycja naraz. Przewaga strategii = PF strategii / PF wejścia na ślepo przy tym samym SL/TP.
11. **PF ważony (ostateczny PF strategii)** = (n_g · min(PF_g, 10) + n_s · min(PF_s, 10)) / (n_g + n_s), gdzie n_g, PF_g — liczba transakcji i PF grupy głównej, n_s, PF_s — skarbca. Sufit 10 dla każdej części, bo PF bez strat wynosi umownie 99 i przy kilkunastu transakcjach zawyżałby średnią. To on decyduje o przyjęciu strategii (próg `pf_min`) i o kolejności w grupie.
12. **Skuteczność** = udział transakcji zamkniętych na TP (nie: udział zyskownych). Średni wynik % liczony jest też osobno dla każdego rodzaju wyjścia (`stats.exit_avg_ret_pct`: tp, sl, fc, time, all) — widać, czy FC zarabia, czy tylko ucina straty.

---

## 9. Poszukiwanie strategii (`python -m ia4.lab`)

### 9.1 Start (przy każdym uruchomieniu)

1. `caffeinate` — Mac nie zasypia, dopóki program działa.
2. Synchronizacja `ia4.sync` (przyrostowo). Bez sieci — praca na kopii lokalnej, z ostrzeżeniem.
3. Kontrola kompletności (`check.py`): brakujące sesje, sesje niepełne (mniej niż 7 świec, 4 w dni skrócone), instrumenty nieaktualne. Wynik trafia do logu i arkusza. Niczego nie łata — braki uzupełnia automat w Apps Script.
4. Pobranie brancha `research`: `config.json` i punkt wznowienia `checkpoint.json`.
5. Poszukiwanie od miejsca, w którym skończył poprzedni przebieg. Ctrl+C albo `--hours N` — zapis stanu, log i push przed końcem.

### 9.2 Kolejność poszukiwania

1. **Siatka** (deterministyczna, raz): 9 typów średnich × okresy zgrubne `5, 7, 10, 13, 17, 21, 26, 32, 40, 50, 60, 75, 90, 110, 130, 150`, oba kierunki, limit czasu brak / 35 świec:
   - `pcross` (cena × linia), FC: brak / `pcross_back`,
   - pary A < B, wszystkie pary typów: `cross` (FC brak / `cross_back`), `converge` (G, S) = (3,1), (3,2), (5,2) z `reexpand` 2, `revert` k = 1 i 2 (FC brak / `cross_back`), `turn` pos `below`/`above` (FC brak / `turn_back`),
   - `ribbon`: trzy linie tego samego typu, FC brak / `cross_back`.
   Razem ok. 547 tys. reguł, bez filtrów. Postęp (kursor) jest w `checkpoint.json`.
2. **Adaptacja** (bez końca, po siatce): 80% zadań to mutacje rodziców z puli najlepszych reguł (okresy 5–150 co 1, typ średniej, filtry, FC, limit czasu, parametry sygnału), 20% to reguły losowane od zera z pełnej przestrzeni. Pula ma dwie połowy — long i short (po 200 reguł), najwyżej 25 z jednej rodziny (ten sam rodzaj, kierunek, typy średnich, FC, limit, cechy filtrów). Rodzic: kierunek losowany (short z prawdopodobieństwem `short_share` = 0,5), potem najlepszy z 3 losowych z puli tego kierunku. Wynik do puli: najlepsze min(PF, mediana PF sąsiednich SL/TP) wśród hipotez z liczbą transakcji ≥ minimum.
3. Reguła raz przetestowana (ta sama reguła bez SL/TP) nie jest liczona ponownie (`ia4-research/state/tested.txt`).

### 9.3 Sita i kryteria (wartości domyślne; zmienia je `research/config.json`)

| Krok | Warunek | Ustawienie |
|---|---|---|
| 1. Sito grupy główna | dla pary SL/TP: transakcji ≥ 30 **i** PF ≥ 1,5 **i** PF > 1 w ≥ 3 z 4 okresów **i** mediana PF sąsiednich SL/TP (±1 pkt proc.) ≥ 1,2 | `min_trades_main`, `pf_min`, `folds_min_ok`, `pf_sltp_neighbors` |
| 1a. Przewaga | PF / PF wejścia na ślepo (ten sam kierunek, SL, TP, limit) ≥ 1,2 | `pf_edge_min` |
| 1b. Stosunek TP/SL | TP/SL od 1:3 do 3:1 (np. SL 8% / TP 1% odpada) | `tp_sl_ratio` |
| 1c. Wyjścia | transakcje zamknięte limitem czasu ≤ 10% (cel: strategie, które trafiają w TP, a nie zarabiają na samym trzymaniu w hossie); opcjonalnie udział TP ≥ próg (domyślnie 0 = bez progu). Pula rodziców adaptacji bierze tylko hipotezy spełniające ten warunek | `max_time_share`, `min_tp_share` |
| 2. Wybór SL/TP | spośród par, które przeszły sito — najwyższy PF grupy głównej | — |
| 3. Stabilność parametrów | do 12 reguł różniących się jednym parametrem (okres ±10%, grow/shrink ±1, k ±0,25, sąsiedni próg filtra) przy tym samym SL/TP: mediana PF ≥ 1,2 **i** ≥ 60% z PF ≥ 1 — inaczej „niestabilna” | `pf_param_neighbors`, `param_neighbors_share_ok` |
| 3a. Grupa pełna | w grupie strategii (9.5) jest już 5 aktywnych, a PF grupy głównej kandydata nie jest wyższy niż najsłabszej z nich → bez skarbca | `max_per_group` |
| 4. Duplikat | ten sam kierunek i ≥ 50% wspólnych świec wejścia (Jaccard, grupa główna) ze strategią aktywną, zarchiwizowaną albo odrzuconą przez skarbiec → bez skarbca | `dup_jaccard` |
| 5. Skarbiec | transakcji w skarbcu ≥ 10 **i** PF samego skarbca ≥ 1,2 **i** PF ważony (8.6 p. 11) ≥ 1,5 **i** PF grupy głównej ≥ 1,5 **i** limit czasu ≤ 10% wszystkich transakcji (główna + skarbiec) → strategia przyjęta | `min_trades_vault`, `vault_pf_min`, `pf_min` |
| 6. Limit grupy | grupa ma mniej niż 5 aktywnych → zapis; grupa pełna → nowa zastępuje najsłabszą (najniższy PF ważony), jeśli ma wyższy PF ważony, inaczej nie jest zapisywana | `max_per_group` |

Progi są stałe — nie rosną z liczbą prób. Zapisujemy wszystko, co przejdzie; progi zmieniamy po przejrzeniu wyników.

### 9.4 Bramka skarbca

Jedyne miejsce, które otwiera skarbiec: `Lab._open_vault`. Każde otwarcie: licznik `vault_peeks` +1, wpis w `research/vault.jsonl` (reguła, PF grupy głównej, PF na ślepo, PF skarbca, PF łączny, PF ważony, wynik). Strategia odrzucona przez skarbiec trafia na listę odrzuconych; strategie o tych samych transakcjach nie otwierają skarbca ponownie (sito 4).

### 9.5 Zapis strategii, grupy i archiwum

**Grupa strategii** = rodzaj sygnału + kierunek (np. `revert|long`) — 6 rodzajów × 2 kierunki = 12 grup. Filtry, okresy, typy średnich, FC, limit czasu i SL/TP nie tworzą nowej grupy. W każdej grupie jest najwyżej `max_per_group` (5) **aktywnych** strategii — najlepszych wg PF ważonego, czyli łącznie najwyżej 60.

**Archiwum** (`research/archive/S-*.json` + `research/archive.jsonl`): strategia przestaje być aktywna, gdy zastąpi ją lepsza w grupie albo gdy po zmianie progów przestaje spełniać kryteria (przegląd uruchamia się sam przy zmianie progów w `config.json`). Niczego nie kasujemy — plik w archiwum ma dopisane pole `archived` (czas, powód). Zarchiwizowane strategie nadal blokują duplikaty.

Strategia aktywna — `research/strategies/S-*.json`: `id`, `version`, `found_at`, `description` (opis słowny), `rule` (8.1, z `sl`/`tp`), `execution` (8.6), `stats` (grupa główna, skarbiec, łącznie, wejście na ślepo, 4 okresy, rozbicie po numerze świecy wejścia i dniu tygodnia, instrumenty, czas trzymania, statystyka czasu między przecięciami A/B), `sltp_hypotheses` (macierze PF i liczby transakcji 10 × 10), `robustness`, `data`, `search`, `criteria`. `research/strategies.jsonl` to indeks strategii aktywnych, przepisywany w całości przy każdej zmianie. Strategia o tym samym `id` nigdy nie jest zapisywana drugi raz (także po twardym przerwaniu programu). Commit i push od razu po znalezieniu.

### 9.6 Log co 30 minut

`research/status.json` (stan bieżący) i wiersz w `research/log.jsonl`: czas, komputer, etap (siatka %/adaptacja), reguł przetestowanych i przyrost, tempo, obiecujących, otwarć skarbca, zapisanych strategii (sumy i przyrosty), najlepszy wynik puli, stan bazy. Do tego `checkpoint.json`. Commit i push.

Liczniki: `evals` — reguły zasymulowane (każda na 100 hipotezach SL/TP; wliczają się sąsiedzi ze stabilności), `hypotheses` — reguły × hipotezy, `eligible` — przeszły sito 1, `unstable` — odpadły na stabilności parametrów, `promising` — przeszły stabilność, `duplicates`, `vault_peeks`, `accepted` (przyjęte łącznie, także później zarchiwizowane), `rejected_vault`, `group_full` (pominięte, bo grupa pełna), `archived`, `run_minutes`. `status.json` ma też `active_strategies` i `groups` (liczba aktywnych w każdej grupie).

### 9.7 Jak Claude dostosowuje poszukiwanie

Claude czyta `research/status.json` (m.in. `best_candidates`), `log.jsonl`, `vault.jsonl` i strategie, po czym proponuje zmiany w `research/config.json` na branchu `research`. Program wczytuje plik przy starcie i co 30 minut (bez restartu). Klucze: wszystkie z `ia4/lab/settings.py` (`DEFAULTS`), m.in. progi z tabeli 9.3, `coarse_periods`, `ma_types`, `max_bars_options`, `paused_kinds` (wyłączone rodzaje sygnałów), `explore_share`, `pool_size`, `workers`, `search_closed` (`true` = poszukiwanie zamknięte: program przy starcie tylko synchronizuje, sprawdza bazę i przelicza weryfikację doubleProof, nie szuka i nie zmienia strategii; ustawione w czasie pracy — program kończy przy najbliższym logu). Zmiana ustawień siatki zaczyna siatkę od początku (reguły już przetestowane są pomijane). Zmiana progów działa na nowe wyniki; zapisanych strategii nie cofa.

---

## 10. Branch `research`

Pisze go wyłącznie program z Maca (klon w `ia4-research/research-repo/`, poza gitem głównego repo), ręcznie zmienia się tylko `config.json`.

```
research/README.md
research/config.json          nadpisania ustawień
research/status.json          stan bieżący (co 30 min)
research/log.jsonl            dziennik (wiersz co 30 min pracy)
research/checkpoint.json      punkt wznowienia: kursor siatki, pula, liczniki, strategie
research/vault.jsonl          każde otwarcie skarbca
research/strategies/S-*.json  strategie aktywne
research/strategies.jsonl     indeks strategii aktywnych
research/archive/S-*.json     strategie zarchiwizowane (z polem archived)
research/archive.jsonl        dziennik archiwizacji (id, czas, powód)
research/doubleproof.json     strategie przeliczone na doubleProof (sekcja 6a)
research/backtest-doubleproof.json  jednorazowy backtest na doubleProof (sekcja 6a), zapisany raz
research/portfolio-backtest.json    jednorazowy backtest portfela i pierwszeństwo strategii (sekcja 6b), zapisany raz
```

Lokalnie (poza gitem): `ia4-research/state/tested.txt` — reguły już przetestowane.

---

## 11. Arkusze STRATEGIE i BACKTEST PORTFELA (`Research.gs`)

Trigger `researchSync` co 30 min (i menu IA 4 → „🔬 Odśwież STRATEGIE teraz”) czyta z GitHub (branch `research`, token `GITHUB_TOKEN`) `strategies.jsonl`, `backtest-doubleproof.json` i `portfolio-backtest.json`.

**STRATEGIE** — jedyny arkusz o strategiach, przepisywany w całości; wszystkie strategie aktywne w kolejności pierwszeństwa (sekcja 6b), na dole zaznaczone „for VI” spoza aktywnych („(archiwum)”). Kolumny:
- Id (zawsze kolumna A), miejsce (pierwszeństwo), wybrana (✓ = wybrana w backteście portfela), grupa, opis reguły, SL %, TP %,
- **backtest doubleProof** (`backtest-doubleproof.json`): PF (zielony ≥ 1,5, żółty 1–1,5, czerwony < 1), transakcji, średni wynik %, skuteczność (TP), mediana świec w pozycji; **szacunek przewagi %** z backtestu portfela,
- **na żywo** (wirtualny inwestor, `VI_BY_STRAT`, od ostatniego „zacznij od nowa”): zamkniętych, średni wynik % netto, wynik $, otwarte,
- **poszukiwanie** (`strategies.jsonl`, do porównania — zawyżone, bo na tych danych strategie były wybierane): PF i liczba transakcji grupy głównej, PF i liczba transakcji skarbca, PF ważony, skuteczność (TP) i średni wynik % (grupa główna + skarbiec),
- **for VI** — checkbox (jedyne, co się zmienia ręcznie; przetrwa przepisanie, sekcja 11a).

**BACKTEST PORTFELA** — zapisany backtest portfela (sekcja 6b), tworzony tylko przy nowym pliku (Script Properties `BT_PF_AT`); usunięty ręcznie nie wraca do czasu nowego backtestu. Dla każdego wariantu 7 wierszy: doubleProof całość i okresy 1–4 (uczciwy obraz), grupa główna i skarbiec (zawyżone).

Przy każdym odświeżeniu `Research.gs` zapisuje też w Script Properties listę strategii aktywnych (`ACTIVE_IDS`) i pierwszeństwo (`PRIORITY`: lista `priority` z backtestu portfela, a bez niego — kolejność wg PF ważonego) — paper trading nie pyta GitHuba przy każdej świecy.

Usunięte w 1.16: arkusze RESEARCH (poszukiwanie wstrzymane), STRATEGIE DOUBLEPROOF i BACKTEST DOUBLEPROOF (ich dane są w STRATEGIE; pliki zostają na branchu `research`).

---

## 11a. Paper trading (`Paper.gs`, `PaperEngine.gs`)

**Kiedy:** w szybkiej ścieżce `runCollector` (sekcja 4 p. 1), zaraz po rundzie, w której wszystkie 53 spółki handlowane mają już tę świecę; jeśli którejś brakuje — 3 min po zamknięciu świecy (`WAIT_AFTER_CLOSE_MIN`), bez niej. Bez osobnego triggera. Ręcznie: menu IA 4 → „📈 Paper trading — przelicz teraz”. Pierwsza świeca dnia zamyka się o 10:30 ET (zwykle 16:30 PL), ostatnia o 16:00 ET (22:00 PL).

**Dane:** wyłącznie z Firestore. Pamięć robocza = ostatnie 1800 świec każdego z 55 instrumentów w ukrytym arkuszu `_IA4_DANE` (JSON pocięty na komórki; obok stan inwestora). Pierwsze zbudowanie: ok. 19 tys. odczytów (raz). Potem przy każdej świecy sesje od ostatniej daty w pamięci (ok. 140 odczytów), raz dziennie 7 dni wstecz (łapie nocne odświeżenie). Pamięć można skasować (usunąć arkusz `_IA4_DANE`) — odbuduje się, ale razem z nią znika stan inwestora.

**Strategie:** aktywne (lista `ACTIVE_IDS` w Script Properties, zapisuje ją `Research.gs`; bez niej — `research/strategies.jsonl`) + zaznaczone „for VI” w arkuszu STRATEGIE. Reguła o danym ID pobierana raz z `research/strategies/` albo `research/archive/` i pamiętana.

**Obliczenia:** `PaperEngine.gs` = sekcja 8 w JavaScript, te same wzory i ta sama kolejność zdarzeń. Średnie okienkowe (WMA, HMA, VWMA) liczone tylko dla końcówki serii (ostatnie 64 świece i świece otwartych pozycji) — te same wartości, mniej pracy. EMA, DEMA, TEMA, KAMA, ZLEMA liczone od początku pamięci (1800 świec; różnica wobec liczenia od początku bazy jest pomijalna). Cecha `since` liczy pełne serie.

**Kolejność na każdej nowej świecy K** (świece po kolei, najwyżej 21 naraz przy nadrabianiu; spółka, której świeca K dotarła dopiero po przeliczeniu, nie dostaje sygnału na tej świecy — jej pozycje są prowadzone dalej normalnie):
1. pozycje inwestora — każda świeca instrumentu po ostatniej obsłużonej: wejście (open świecy po sygnale), potem luka SL/TP → FC → SL → TP → limit (8.6), na koniec FC na zamknięciu,
2. sygnały wszystkich strategii na świecy K na 53 spółkach,
3. inwestor otwiera pozycję „oczekuje” dla sygnału strategii z jego listy, jeśli spółka ma mniej niż `MAX_PER_TICKER` otwartych/oczekujących pozycji (dowolnych strategii; ustawione: **1**, 0 = bez limitu) i ta strategia nie ma już pozycji na tej spółce; przy kilku sygnałach na tej samej spółce i świecy — w kolejności pierwszeństwa (`PRIORITY`, sekcja 6b; strategia spoza listy — na końcu, potem wg ID).
4. Kolejność zapisu: SIGNALS-REALTIME i VIRTUAL-INVESTOR, potem pamięć `_IA4_DANE`. Czasy: tabela świec w STATS (4a).

**SIGNALS-REALTIME:** wiersz na każdą przeliczoną świecę, najnowsze na górze: data, numer świecy, zamknięcie (PL), liczba sygnałów, potem pary kolumn ID strategii + ticker. Najwyżej 3000 wierszy.

**VIRTUAL-INVESTOR:**
- **wybór strategii: checkbox „for VI” w ostatniej kolumnie arkusza STRATEGIE, bez limitu liczby.** Zaznaczenia są zapamiętywane w Script Properties (`VI_IDS`), bo STRATEGIE jest przepisywany w całości; strategia zaznaczona, która wypadła z aktywnych, zostaje na dole STRATEGIE z dopiskiem „(archiwum)” i dalej działa, dopóki nie odznaczysz. Odznaczenie nie zamyka otwartych pozycji, tylko blokuje nowe. Pierwsze użycie (wersja 1.10) przejmuje ID wpisane ręcznie w VIRTUAL-INVESTOR,
- A4:B23 — podgląd listy „for VI” (pierwsze 19 + „… i N więcej”), tylko do odczytu,
- statystyki (D4:E22): kapitał 100 000 $, stawka 100 $ na transakcję, stan konta = kapitał + wynik zamkniętych, wynik zamkniętych $ i % kapitału, wynik otwartych $, stan konta gdyby teraz zamknąć wszystko, wynik całkowity %, wolna gotówka, liczba pozycji, wyjścia TP/SL/FC/limit, skuteczność (TP), średni wynik zamkniętej, mediana świec w pozycji (zamknięte), koszty transakcyjne $, **średni wynik zamkniętej — przedział 95%** (średnia ± 2 × odchylenie / √n), liczy od (data ostatniego „zacznij od nowa”),
- transakcje od wiersza 28: nr, strategia, ticker, kierunek, sygnał, wejście, cena wejścia, SL, TP, status (oczekuje / otwarta / zamknięta), ostatnia świeca, cena aktualna, wynik % i $, wyjście, cena wyjścia, powód, świec w pozycji. Otwarte na górze.
- **Menu:** „✅ for VI = strategie wybrane w backteście portfela” — zaznacza dokładnie wybrane (✓ w STRATEGIE), resztę odznacza; „🔄 Wirtualny inwestor — zacznij od nowa” — kasuje wszystkie pozycje i statystyki (po potwierdzeniu), sygnały i strategie bez zmian; data startu w `startedAt`.
- Po każdym przeliczeniu: wyniki każdej strategii (`VI_BY_STRAT` → STRATEGIE) i podsumowanie (`VI_SUMMARY` → telemetria, pole `vi`).
- Wynik % jak w 8.6 p. 6 minus koszt: 2 × `COST_PCT` (0,005% przy wejściu i 0,005% przy wyjściu) — dla pozycji otwartych od wersji 1.15 (starsze bez kosztu); wynik $ = 100 $ × wynik %. Pozycje otwarte pokazują wynik netto (po obu kosztach).

**Test zgodności** (po każdej zmianie sekcji 8, `PaperEngine.gs` albo `ia4/lab`):
```bash
cd ia4-research && python tests/parity_dump.py /tmp/ia4_parity.json && node tests/parity.js /tmp/ia4_parity.json
```
Wynik musi brzmieć „rozbieżności: sygnały 0, transakcje 0”.

---

## 12. Wdrożenie i uruchamianie

### Apps Script — skład

Pliki: `Code.gs`, `Telemetry.gs`, `Research.gs`, `PaperEngine.gs`, `Paper.gs`, `Fx.gs` (+ manifest `appsscript.json`). Triggery (zakłada je „⚙️ Konfiguruj i włącz automat”): `runCollector` co minutę, `telemetryHourly` co godzinę, `researchSync` co 30 min. Script Properties: `GITHUB_TOKEN` (menu „Ustaw token GitHub”) oraz stan automatu (`LIVE_STATE`, `BACKFILL_DP`, `VI_IDS`, `PAPER_LAST_KEY`, `BT_DP_AT`, `BT_PF_AT`, `CANDLE_LOG`, `FX_STATE`, `FX_CHECK`, `ACTIVE_IDS`, `PRIORITY`, `VI_BY_STRAT`, `VI_SUMMARY` i inne — nie edytować). Arkusze: STATS, FX, OKOLICZNOSCI_FX (od FX-3), STRATEGIE, BACKTEST PORTFELA, SIGNALS-REALTIME, VIRTUAL-INVESTOR, ukryty `_IA4_DANE`.

### Aktualizacja do nowej wersji

1. Wypchnięcie pakietu `.bundle` (polecenia niżej).
2. Apps Script: podmienić pliki `.gs` zmienione w pakiecie (Claude podaje listę) — najprościej zawsze wszystkie sześć; nowy plik dodać przez „+ → Skrypt” z tą samą nazwą. Zapisać, odświeżyć arkusz.
3. „⚙️ Konfiguruj i włącz automat” — tylko gdy zmieniła się lista instrumentów, układ STATS albo triggery (Claude o tym mówi). Konfiguruj odtwarza STATS, triggery i `system/universe` oraz uzupełnia ostatni miesiąc (ok. 2500 zapisów).
4. Mac: `cd ~/Desktop/IA4 && git pull`; `pip install -r requirements.txt`, gdy zmieniły się zależności; zatrzymać program (Ctrl+C) i uruchomić ponownie, gdy zmienił się kod Pythona.

### Mac — na co dzień

Przy wstrzymanym poszukiwaniu Mac **nie jest potrzebny na co dzień** — zbieranie, sygnały i wirtualny inwestor działają w Apps Script. Mac tylko do jednorazowych przeliczeń:

```bash
cd ~/Desktop/IA4/ia4-research && source .venv/bin/activate
python -m ia4.lab.backtest_dp --force   # backtest strategii na doubleProof → kolumny doubleProof w STRATEGIE
python -m ia4.lab.portfolio --force     # backtest portfela → BACKTEST PORTFELA, pierwszeństwo, „wybrane”
python -m ia4.lab.selftest              # test silnika
```

Prognoza EURUSD (sekcja 4c) — Mac włączony, gdy używasz dashboardu:

```bash
cd ~/Desktop/IA4/ia4-research && source .venv/bin/activate
python -m ia4.fx.selftest              # test modułu na danych syntetycznych — „WYNIK: OK”
python -m ia4.fx.catalog               # kalibracja próbna → data/fx/catalog-preview.csv (nic nie wysyła)
python -m ia4.fx.catalog --commit      # kalibracja właściwa → fx/conditions.json (RAZ, zasada 14)
python -m ia4.fx.research              # ręcznie: przeliczenie wszystkich okoliczności i ratingów → branch fx
python -m ia4.fx.live                  # prognoza na żywo co 30 s → branch fx-live → dashboard (Ctrl+C kończy)
```

Poszukiwanie (gdy zostanie wznowione, `search_closed: false`): `python -m ia4.lab --workers 4` (alias `ia4`); opcje: `--hours N`, `--workers N`, `--check`, `--no-sync`, `--no-push`.

### Limity Firestore (plan Spark: 20 000 zapisów i 50 000 odczytów na dzień)

| Część | Zapisy | Odczyty |
|---|---|---|
| zbieranie na żywo (75 instrumentów, 7 świec) | ok. 1100 / dzień | — |
| moduł EURUSD (świeca 5 min: dokument dnia + podsumowanie; kontrola dnia) | ok. 580 / dzień (rynek otwarty) + do 3 na dzień kontroli, historia ok. 60 raz | do 3 / dzień; „przelicz arkusz FX” ok. 1 na dzień bazy |
| nocne odświeżenie + liczenie bazy | ok. 550 / noc | ok. 150 / noc |
| historia doubleProof (do zakończenia) | najwyżej 8000 / dzień | — |
| „Konfiguruj” / „Uzupełnij ostatni miesiąc” | ok. 2500 / raz | — |
| paper trading | — | pierwsze zbudowanie pamięci ok. 19 000 (raz), potem ok. 150 / świecę + ok. 650 raz dziennie |
| Mac: `ia4.sync` przyrostowo | — | kilkaset / start |
| Mac: odświeżanie doubleProof w `ia4.lab` | — | ok. 250 / godzinę pracy |
| Mac: pierwsza synchronizacja nowych instrumentów (doubleProof) | — | ok. 10 000 (raz) |
| Mac: `ia4.sync --full` | — | ok. 48 000 — nie łączyć tego samego dnia z innymi dużymi odczytami |
| Mac: `ia4.fx.sync` (FX-research, start FX-real-time) | — | pierwszy raz ok. 1 na dzień bazy FX (ok. 60), potem 1–3 / start |
| Mac: FX-real-time | — | ok. 300–600 / dzień pracy przy otwartym rynku; przy zamkniętym 0 |

### Limity Apps Script (konto Gmail)

Łączny czas triggerów: 90 min dziennie; jedno uruchomienie: 6 min; `UrlFetchApp`: 20 000 zapytań dziennie. Zużycie czasu widać w STATS („Czas pracy automatu dziś”). Zapytania: Yahoo akcje ok. 75 × 7 + ponowienia brakujących + nocne odświeżenie (ok. 700 / dzień), Yahoo EURUSD ok. 290 / dzień, Firestore i GitHub — kilkaset.

### Pakiety `.bundle` od Claude

```bash
cd ~/Desktop
rm -rf IA4-push
git clone https://github.com/miszyszka/IA4.git IA4-push
cd IA4-push
git fetch ~/Downloads/IA4-vX.Y.bundle vX.Y
git cherry-pick FETCH_HEAD || { git rm -rq telemetry/history; git -c core.editor=true cherry-pick --continue; }
git log --oneline -2
git push
cd ~/Desktop/IA4 && git pull
```

---

## 13. Dziennik zmian

| Wersja | Data | Zmiana |
|---|---|---|
| 1.21 | 2026-10-09 | Krok FX-1: sekcja 4c.3 uzupełniona (17 rodzin, wzory cech, lustro, U = ATR100, rozgrzewka 1000 świec, procedura kalibracji z celami 15/25/40% i limitem korelacji). Nowe `ia4/fx/sync.py`, `series.py`, `catalog.py`, `store.py`, `selftest.py`; `python -m ia4.fx.catalog` (próbna) i `--commit` (właściwa, raz) zamiast kalibracji przy pierwszym FX-research. `ia4/lab/store.py`: branch jako parametr (bez zmiany działania `ia4.lab`). |
| 1.20 | 2026-10-09 | Etap 4 — prognoza EURUSD (sekcja 4c, na razie sama instrukcja — kod w krokach FX-1…FX-4): kopia `fx/EURUSD` na Macu, katalog 1000 okoliczności w 500 parach lustrzanych kalibrowany raz i nienaruszalny (zasada 14), profile zmian ceny w pipsach na 48 świec, rating 1–100 poza próbą (70/30, skala stała), prognoza ważona ratingiem, sprawdzian systemu; programy `ia4.fx.research` (ręcznie) i `ia4.fx.live` (co 30 s); branche `fx` i `fx-live` (zasada 11); dashboard GitHub Pages ze statusem Maca; arkusz OKOLICZNOSCI_FX. |
| 1.19 | 2026-10-08 | Arkusz STRATEGIE: wróciły wyniki z poszukiwania — PF i transakcje grupy głównej i skarbca, PF ważony, skuteczność i średni wynik (obok doubleProof i wyników na żywo). |
| 1.18 | 2026-10-08 | Arkusz FX: tylko jeden wiersz na zakończony dzień (oczekiwanych, zapisanych, w tym uśrednionych), bez bloku stanu i bez zapisów przy każdej świecy. Każdy dzień kończy się kompletny: uśrednienie wszystkich braków po 3 próbach (bez progu „połowa świec”), pierwszy dzień bazy liczony od jego pierwszej świecy; przy pierwszym uruchomieniu 1.18 dni niekompletne (także dawny „brak danych”) i dni robocze bez dokumentu wracają do kontroli. |
| 1.17 | 2026-10-07 | Moduł EURUSD: oczekiwane świece dnia wg godzin rynku (288 / pt 252 / nd 36 / sob 0); kontrola każdego zakończonego dnia — do 3 prób pobrania braków co 60 min, potem uśrednienie (interpolacja liniowa, oznaczone w `fillT`) — wyjątek w zasadzie 2; nowe pola dokumentu dnia (`expected`, `missing`, `filled`, `fillT`, `tries`, `status`); nowy arkusz FX (czy działa, ostatni zapis, lista wszystkich dni); menu „EURUSD — przelicz arkusz FX”; dzienne odświeżenie wczorajszego dnia zastąpione kontrolą. |
| 1.16 | 2026-10-05 | Uproszczenie: jeden arkusz STRATEGIE (pierwszeństwo, wybrane, backtest doubleProof, szacunek przewagi, wyniki na żywo, for VI); usunięte arkusze RESEARCH, STRATEGIE DOUBLEPROOF, BACKTEST DOUBLEPROOF; BACKTEST PORTFELA bez listy strategii. Wirtualny inwestor: `MAX_PER_TICKER` (1), przedział 95% średniego wyniku, data startu, menu „for VI = wybrane” i „zacznij od nowa”; wyniki strategii na żywo (`VI_BY_STRAT`) i podsumowanie w telemetrii (`vi`). Mac niepotrzebny na co dzień. Nowy `PRZEWODNIK.md`. |
| 1.15 | 2026-10-04 | Szybka ścieżka po zamknięciu świecy: czekanie na zamknięcie (+15 s), równoległe pobieranie z Yahoo, jeden zapis do Firestore na rundę, ponowienia brakujących co 10 s, paper trading od razu po komplecie 53 spółek (najpóźniej 3 min po zamknięciu), lista strategii z Script Properties. STATS: blok stanu + tabela świec z czasami od zamknięcia (sekcja 4a), bez tabeli instrumentów i dziennika; czas pracy automatu. Wirtualny inwestor: najwyżej 1 pozycja na spółkę, pierwszeństwo strategii, koszt 0,005% przy wejściu i wyjściu, mediana świec w pozycji, koszty $. Mediana świec w pozycji we wszystkich wynikach (zasada 13). Backtest portfela `python -m ia4.lab.portfolio` → arkusz BACKTEST PORTFELA (sekcja 6b). Nowy moduł EURUSD 5 min (`Fx.gs`, `fx/EURUSD`, sekcja 4b). |
| 1.14 | 2026-10-03 | Poszukiwanie wstrzymane: nowy klucz `search_closed` w `research/config.json` (ustawiony na `true`) — `ia4.lab` tylko synchronizuje, sprawdza bazę i przelicza weryfikację doubleProof; zostaje 60 aktywnych strategii. Jednorazowy backtest strategii aktywnych na doubleProof: `python -m ia4.lab.backtest_dp` → `research/backtest-doubleproof.json` (zapisany raz) → nowy arkusz BACKTEST DOUBLEPROOF z wynikami każdej strategii i każdej spółki. |
| 1.13 | 2026-10-02 | Weryfikacja doubleProof: co godzinę pracy `ia4.lab` dociąga nowe świece doubleProof z Firestore i przelicza wszystkie aktywne strategie (wcześniej dane wczytywane tylko przy starcie). |
| 1.12 | 2026-10-02 | Weryfikacja strategii aktywnych na doubleProof: `ia4/lab/verify.py` (w `ia4.lab` przy starcie i co 30 min, gdy zmieniły się strategie albo dane; ręcznie `python -m ia4.lab.verify`) → `research/doubleproof.json` → arkusz STRATEGIE DOUBLEPROOF (te same strategie i kolejność co STRATEGIE). Tylko informacja, bez wpływu na poszukiwanie. |
| 1.11 | 2026-10-01 | Przegląd całości. Poprawka: szybkie ponawianie pobrań po zamknięciu świecy liczy czas następnej próby (przy 75 instrumentach groziło przekroczeniem 6 min Apps Script). Instrukcja uporządkowana: cele 3–4, kolejność 8.6 i 9.3, skuteczność (8.6 p. 12), status w STATS, zużycie Firestore przy 75 instrumentach, sekcja 12 (skład Apps Script, aktualizacja, Mac na co dzień z `--workers 4`, limity), etapy 2–3. Telemetria: etap „2 + 3”. |
| 1.10 | 2026-10-01 | Wirtualny inwestor bierze strategie zaznaczone checkboxem „for VI” w arkuszu STRATEGIE (bez limitu) zamiast listy 20 ID w VIRTUAL-INVESTOR; zaznaczenia w `VI_IDS`, zaznaczone nieaktywne zostają w STRATEGIE jako „(archiwum)”. Python: wersje porównywane liczbowo. |
| 1.9 | 2026-10-01 | Nowa kolekcja `doubleProof` (20 spółek S&P 500: AMD, INTC, QCOM, CSCO, ADBE, LRCX, C, MS, SCHW, COP, OXY, SLB, BA, GE, UBER, F, GM, COST, BMY, CMCSA) — zbierana na żywo i w nocnym odświeżeniu, historia pobierana wstecz porcjami co godzinę do granicy Yahoo (sekcja 4 p. 5). Sekcja 6a: doubleProof wyłączona z poszukiwania i paper tradingu, tylko do weryfikacji. STATS: wiersz „Historia doubleProof”; telemetria: `doubleProofHistory`. Python: `system/universe.doubleProof`, grupa w manifeście synchronizacji. |
| 1.8 | 2026-10-01 | Etap 3 — paper trading: `PaperEngine.gs` (język reguł w JS, zgodność z Pythonem 100% w teście 140 reguł / 13 335 sygnałów / 11 962 transakcji), `Paper.gs` (pamięć świec `_IA4_DANE`, krok po każdej świecy w `runCollector`, arkusze SIGNALS-REALTIME i VIRTUAL-INVESTOR, menu „Paper trading — przelicz teraz”), test `ia4-research/tests/`. Zasada 12: jeden język reguł, dwie implementacje. |
| 1.7 | 2026-10-01 | Statystyki strategii: średni wynik % wg rodzaju wyjścia (`stats.exit_avg_ret_pct`: tp, sl, fc, time, all); w arkuszu STRATEGIE kolumny „Śr. wynik FC %” i „Śr. wynik transakcji %”. Przy pierwszym starcie 1.7: przeliczenie statystyk aktywnych strategii (bez liczenia jako otwarcie skarbca), przegląd wg wszystkich kryteriów, nowy dziennik od zera — stare `log.jsonl` i `vault.jsonl` w `research/archive/`, liczniki wyzerowane. |
| 1.6 | 2026-10-01 | Najwyżej 10% transakcji może kończyć się limitem czasu (sito grupy głównej, skarbiec, przegląd zapisanych). Skuteczność w arkuszach = udział wyjść na TP. Nowy próg `min_tp_share` (domyślnie wyłączony). Przegląd strategii przy pierwszym starcie 1.6. |
| 1.5 | 2026-10-01 | Grupa strategii = rodzaj sygnału + kierunek (było: + zestaw filtrów, co dawało 188 grup i 330 aktywnych). Najwyżej 5 w grupie, łącznie najwyżej 60 aktywnych. Przegląd przy pierwszym starcie 1.5 (także dla wersji 1.2–1.4). |
| 1.4 | 2026-10-01 | Ostateczny PF strategii = PF ważony liczbą transakcji grupy głównej i skarbca (sufit 10 na część); decyduje o przyjęciu i kolejności w grupie. Przy pierwszym starcie 1.4 przegląd strategii wg nowego PF. Arkusz STRATEGIE: osobne kolumny SL, TP, transakcji skarbca, PF ważony, udziały wyjść TP/SL/FC/limit. |
| 1.3 | 2026-10-01 | Arkusz STRATEGIE: wszystkie strategie aktywne z wynikami (`Research.gs`, ten sam trigger `researchSync`). |
| 1.2 | 2026-10-01 | Ostrzejsze kryteria po pierwszej dobie (1292 strategie, w większości ta sama „kup spadek w hossie”): przewaga nad wejściem na ślepo ≥ 1,2, PF samego skarbca ≥ 1,2, TP/SL od 1:3 do 3:1, najwyżej 5 aktywnych strategii w grupie (rodzaj sygnału + kierunek + cechy filtrów), archiwum zamiast kasowania, osobne pule rodziców long/short. Poprawka: strategia nie zapisuje się drugi raz po twardym przerwaniu. Przy pierwszym starcie 1.2 program sam wpisuje nowe progi do `config.json` i przenosi niespełniające ich strategie do archiwum (z 1292 zostaje ok. 45). |
| 1.1 | 2026-09-30 | Etap 1 zamknięty. Etap 2 — poszukiwanie strategii: program `python -m ia4.lab` (synchronizacja, kontrola kompletności, siatka i adaptacja, sita, bramka skarbca, log co 30 min, wznawianie), język reguł `ia4-rule/1` (9 typów średnich, 6 rodzajów sygnałów, 18 cech filtrów, 4 rodzaje FC, limit czasu), symulacja pesymistyczna na 100 hipotezach SL × TP, kryterium PF zamiast skuteczności, wejście na ślepo jako punkt odniesienia, duplikaty po wspólnych transakcjach. Skarbiec: wielokrotne otwieranie przez bramkę, tylko dla obiecujących strategii, każde otwarcie liczone. Wyniki na branchu `research`; nowy `Research.gs` i arkusz RESEARCH, trigger `researchSync`. Usunięte jednorazowe sprzątanie po 1.0. |
| 1.0 | 2026-09-30 | Nowe założenia: jedynym celem jest baza danych. Usunięte strategie S1/S2, backtesty, poletko, stary skarbiec, etapy 0–5, audyt i łatanie luk, dopisywanie wolumenu, pobieranie historii, inwestorzy, dashboard i cały Python poza synchronizacją. Zbieranie w jednym pliku `Code.gs` + nocne odświeżenie ostatnich 5 sesji i liczenie bazy. Telemetria skrócona do stanu bazy. Skarbiec = najstarsze 800 świec. Instrukcja przepisana od zera. |
| ≤ 0.47 | do 2026-09-29 | Poprzedni projekt (strategie, backtesty, etapy 0–5) — w historii gita. |
