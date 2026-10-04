# IA 4 — instrukcja projektu

**Wersja:** 1.15
**Data:** 4 października 2026
**Aktualny etap:** 🟨 Etap 2 — Poszukiwanie strategii i 🟨 Etap 3 — Paper trading (sygnały na żywo, wirtualny inwestor). Etap 1 (baza danych) zamknięty 30.09.2026; automat zbierający świece działa dalej bez końca. Poszukiwanie wstrzymane 3.10.2026 (`search_closed: true`) — zostaje 60 aktywnych strategii. Od 4.10.2026 moduł EURUSD zbiera świece 5-minutowe (sekcja 4b).

Ten plik jest jedynym źródłem prawdy i zbiorem żelaznych zasad projektu. Jeśli kod, arkusz albo telemetria się z nim rozjeżdżają, obowiązuje ten plik, a rozbieżność trzeba naprawić.

---

## 1. Cel

1. **Baza świec 1h w Firestore** (Etap 1, działa stale): kompletna, rośnie każdego dnia sesyjnego, ma stały format.
2. **Poszukiwanie strategii** (Etap 2): program w Pythonie na Macu, uruchamiany w dowolnych momentach, bez końca przelicza kopię lokalną bazy i szuka powtarzalnych sygnałów long i short opartych na średnich kroczących. Liczy się jakość, nie liczba strategii: strategia ma trafiać w TP, a nie zarabiać na samym trzymaniu pozycji w hossie. Każda zapisana strategia jest regułą opisaną na sztywno (sekcja 8), tak żeby inny system mógł ją odtworzyć świeca po świecy.
3. **Paper trading** (Etap 3): sygnały strategii na żywo i wirtualny inwestor w Apps Script, po każdej zamkniętej świecy (sekcja 11a).
4. **Weryfikacja na nowych spółkach:** grupa doubleProof (20 spółek), której system nigdy nie widzi przy szukaniu — do sprawdzania strategii przez człowieka (sekcja 6a).
5. **Moduł EURUSD:** osobna baza świec 5-minutowych kursu EURUSD (sekcja 4b). Na razie tylko zbieranie danych.

Historia wcześniejszych prac (strategie S1/S2, backtesty, etapy 0–5) jest w historii gita do wersji 0.47.

---

## 2. Żelazne zasady

1. **Firestore jest jedynym źródłem danych.** Kopia na Macu (`ia4-research/data/`) to tylko kopia robocza — można ją skasować i odtworzyć. Python nigdy nie pobiera świec z Yahoo i nigdy nie pisze do Firestore.
2. **Baza tylko rośnie.** Zapisujemy wyłącznie zamknięte świece. Niczego nie kasujemy. Wolno przepisać sesję tylko danymi pobranymi ponownie z Yahoo (nocne odświeżenie, „Uzupełnij ostatni miesiąc”).
3. **Format bazy (sekcja 4) jest stały.** Każda jego zmiana wymaga najpierw zmiany tej instrukcji, zgody człowieka i opisu migracji istniejących danych.
4. **Skarbiec = najstarsze 800 świec każdego instrumentu** (sekcja 6). Poszukiwanie nigdy nie widzi wyników skarbca. Skarbiec otwiera wyłącznie bramka skarbca, dla strategii, która przeszła wszystkie sita grupy głównej. Każde otwarcie jest liczone i zapisywane.
5. **Sekrety nigdy nie trafiają do repozytorium:** klucz serwisowy Firebase (`~/.ia4/serviceAccount.json`) i token GitHub (Script Properties → `GITHUB_TOKEN`).
6. **System jest minimalny.** Nowa funkcja, arkusz, plik czy dziennik pojawia się tylko za zgodą człowieka i najpierw jako zmiana tej instrukcji.
7. **Współpraca z Claude:**
   - na początku rozmowy Claude pobiera repozytorium `github.com/miszyszka/IA4.git`, czyta ten plik (branch `main`), `telemetry/state.json` (branch `main`) oraz `research/status.json` i `research/log.jsonl` (branch `research`),
   - Claude przygotowuje zmiany jako commit w pliku `.bundle` (wysyła go w rozmowie, użytkownik zapisuje w `~/Downloads`) i podaje gotowe polecenia terminala do wypchnięcia (sekcja 12); lokalna kopia `~/Desktop/IA4` aktualizuje się przez `git pull`,
   - każdą zmianę Claude sprawdza przed wysłaniem: `selftest`, test zgodności (sekcja 11a), składnia plików `.gs`, symulacja zmienionej logiki,
   - pracę wykraczającą poza tę instrukcję albo pomysł na jej zmianę Claude najpierw proponuje i czeka na zgodę,
   - Claude nie ma dostępu do arkusza ani edytora Apps Script: użytkownik ręcznie wkleja zmienione pliki `.gs` do Apps Script i robi `git pull` na Macu.
8. **Jedna wersja dla całego projektu.** Ten sam numer w nagłówku tej instrukcji, w nagłówku każdego pliku `.gs`, w `CONFIG.VERSION` (`Code.gs`) i w `ia4-research/` (`ia4/__init__.py`). Zmiana znacząca (logika, zasada, format, etap) podbija wersję i dostaje wpis w sekcji 13. Drobne poprawki — tylko opis w commicie. (`appsscript.json` nie nosi wersji — JSON nie ma komentarzy.)
9. **Strategia to reguła, nie kod.** Każda zapisana strategia jest pełną regułą w języku `ia4-rule/1` (sekcja 8): linie, sygnał, filtry, SL, TP, FC, limit czasu — wszystko liczbami, bez parametrów domyślnych. Definicje z sekcji 8 zmienia się tylko razem z nową wersją języka (`ia4-rule/2`); stare strategie zachowują swoją wersję.
10. **Symulacja jest zawsze pesymistyczna** (sekcja 8.6). Strategie (poszukiwanie, weryfikacja, backtest doubleProof) liczone są bez kosztów transakcyjnych, każda reguła na wszystkich hipotezach SL × TP naraz. Koszt transakcyjny (`COST_PCT` = 0,005% wartości pozycji przy wejściu i przy wyjściu) liczą tylko wirtualny inwestor (11a) i backtest portfela (6b).
11. **Wyniki poszukiwania żyją na branchu `research`** (sekcja 10). Python nie pisze do `main`; `main` to kod, ta instrukcja i telemetria automatu.
12. **Jeden język reguł, dwie implementacje.** Reguły liczy Python (`ia4/lab`, backtest) i JavaScript (`PaperEngine.gs`, na żywo). Każda zmiana definicji z sekcji 8 musi trafić do obu naraz, a test zgodności (`ia4-research/tests/`, sekcja 11a) musi dać 0 rozbieżności.
13. **Mediana trzymania.** Każdy wynik strategii albo portfela (arkusze, pliki wyników) podaje medianę świec w pozycji: świeca wyjścia − świeca wejścia + 1.

---

## 3. Architektura

```
Yahoo ──(Apps Script, co minutę)──▶ Firestore ──(ia4.sync)──▶ Mac: ia4-research/data/*.parquet
                  │                                                     │
                  ├──▶ arkusz STATS                                     ▼
                  ├──▶ GitHub main: telemetry/state.json      python -m ia4.lab (bez końca)
                  │                                                     │
                  ├──◀ arkusz RESEARCH ◀──(Research.gs, co 30 min)──── GitHub research: research/*
                  └──▶ po każdej świecy: Paper.gs (Firestore → pamięć _IA4_DANE → sygnały, inwestor)
Yahoo EURUSD=X ──(Fx.gs, w tym samym triggerze)──▶ Firestore fx/EURUSD (moduł EURUSD, sekcja 4b)
```

| Plik | Rola |
|---|---|
| `Code.gs` | automat: listy instrumentów, zbieranie na żywo (szybka ścieżka po zamknięciu świecy), nocne odświeżenie, liczenie bazy, pobieranie historii doubleProof, zapis do Firestore, arkusz STATS, menu, triggery |
| `Fx.gs` | moduł EURUSD: świece 5 min z Yahoo → Firestore `fx/EURUSD`, opóźnienia w STATS (sekcja 4b) |
| `Telemetry.gs` | stan zbierania → `telemetry/state.json` w GitHub (branch `main`) |
| `Research.gs` | branch `research` (`status.json`, `log.jsonl`, `strategies.jsonl`, `doubleproof.json`, `backtest-doubleproof.json`) → arkusze RESEARCH, STRATEGIE, STRATEGIE DOUBLEPROOF i BACKTEST DOUBLEPROOF |
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

Osobny moduł: na razie **tylko zbiera** świece 5-minutowe kursu EURUSD. Nie bierze udziału w poszukiwaniu, weryfikacji, paper tradingu ani w kopii na Macu. Obowiązują go zasady 2.1–2.3 (Firestore jedynym źródłem, baza tylko rośnie, format stały).

- **Źródło:** Yahoo `EURUSD=X`, `interval=5m`. Yahoo trzyma świece 5 min tylko 60 dni wstecz, więc historia zaczyna się 59 dni przed startem modułu i rośnie od tego dnia. Ceny Yahoo dla walut są orientacyjne; wolumen Yahoo podaje zawsze 0 — nie jest zapisywany.
- **Świeca:** 5 minut, opisana czasem początku w UTC (wielokrotność 5 min). Zapisujemy tylko świece zamknięte. Ceny zaokrąglone do 6 miejsc.
- **Format w Firestore:**
  ```
  fx/EURUSD/days/{RRRR-MM-DD}     jeden dokument na dzień UTC
    symbol ("EURUSD"), date, bars (liczba świec), t [] (minuta dnia UTC początku świecy: 0, 5, … 1435),
    o [], h [], l [], c [], updatedAt          (tablice równoległe)
  fx/EURUSD                       podsumowanie: symbol, yahoo ("EURUSD=X"), interval ("5m"),
                                  lastDate, lastTime (HH:MM UTC), lastClose, liveUpdatedAt
  ```
- **Kiedy:** w każdym uruchomieniu `runCollector` (co minutę) i co 10 s w szybkiej ścieżce akcji — jeden trigger dla całego automatu (dzienny limit czasu triggerów). Yahoo jest pytane tylko wtedy, gdy powinna już być zamknięta świeca nowsza niż ostatnia zapisana (+5 s), i tylko w godzinach rynku walutowego: niedziela 17:00 – piątek 17:00 czasu Nowego Jorku (z zapasem). Pobranie od początku dnia UTC ostatniej zapisanej świecy; dokument dnia z nową świecą przepisywany w całości.
- **Historia:** przy pierwszym uruchomieniu jedno pobranie ostatnich 59 dni (po błędzie — ponowienie co 30 min).
- **Dzienne odświeżenie:** raz na dobę po 00:20 UTC cały wczorajszy dzień od nowa (łapie poprawki i braki Yahoo).
- **Opóźnienie świecy** = chwila potwierdzenia zapisu w Firestore − zamknięcie świecy (początek + 5 min). Zależy od sekundy, w której startuje trigger (0–60 s) i od Yahoo. **Brakujące świece** = przerwy dłuższe niż 5 min w obrębie dnia (bez przerwy weekendowej).
- **STATS** (3 wiersze bloku stanu): ostatnia świeca (UTC i PL, close); opóźnienie ostatniej świecy oraz dziś (UTC): mediana, 90. percentyl, maksimum; dziś: świec, brakujących, wczoraj (po odświeżeniu), od kiedy baza. Telemetria: pole `fx`.
- Stan: Script Properties `FX_STATE`. Ręcznie: menu IA 4 → „EURUSD — pobierz teraz”.

**Raz w roku (grudzień):** dopisać święta NYSE na kolejny rok do `US_MARKET_HOLIDAYS` w `Code.gs` oraz święta i sesje skrócone do `ia4-research/ia4/lab/check.py`.

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
- arkusz STRATEGIE DOUBLEPROOF (sekcja 11).

**Jednorazowy backtest (`ia4/lab/backtest_dp.py`):**
- `python -m ia4.lab.backtest_dp` — synchronizacja doubleProof (+ SPY, QQQ), potem wszystkie strategie aktywne liczone dokładnie tak jak w weryfikacji (te same funkcje, te same wyniki na strategię, plus suma wyników %), zapis i push,
- wynik: `research/backtest-doubleproof.json` (branch `research`) — **zapisany raz**: data backtestu, zakres danych, wyniki wszystkich strategii i każdej spółki. Weryfikacja go nie przelicza; istniejący zapis zmienia tylko ponowne uruchomienie z `--force`,
- tylko informacja, jak weryfikacja: nie zmienia strategii ani poszukiwania,
- arkusz BACKTEST DOUBLEPROOF (sekcja 11).

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

Program `python -m ia4.lab` na Macu (sekcje 8–10), wyniki na branchu `research`, podgląd w arkuszu RESEARCH (sekcja 11). Etap trwa bez końca; Claude okresowo przegląda wyniki i proponuje zmiany ustawień w `research/config.json`.

Wdrożony 30.09.2026: triggery `runCollector`, `telemetryHourly`, `researchSync`; `python -m ia4.lab.selftest` kończy się „WYNIK: OK”; branch `research` ma `status.json` i `log.jsonl`; arkusze RESEARCH i STRATEGIE się odświeżają. Siatka zakończona 1.10.2026, od tego czasu adaptacja. **3.10.2026 poszukiwanie wstrzymane** (`search_closed: true` w `research/config.json`): zostaje 60 aktywnych strategii, `python -m ia4.lab` tylko synchronizuje, sprawdza bazę i przelicza weryfikację doubleProof.

### Etap 3 — Paper trading 🟨

Sygnały strategii na żywo i wirtualny inwestor w Apps Script (sekcja 11a). Działa bez Maca, przy każdej zamkniętej świecy. Wdrożony, gdy:
- 3.1 `Paper.gs` i `PaperEngine.gs` są w Apps Script, a pierwsze przeliczenie zbudowało pamięć świec (ukryty arkusz `_IA4_DANE`),
- 3.2 SIGNALS-REALTIME dostaje wiersz po każdej świecy sesji,
- 3.3 VIRTUAL-INVESTOR otwiera i zamyka transakcje dla strategii zaznaczonych „for VI” w arkuszu STRATEGIE.

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

## 11. Arkusze RESEARCH, STRATEGIE, STRATEGIE DOUBLEPROOF, BACKTEST DOUBLEPROOF i BACKTEST PORTFELA (`Research.gs`)

Trigger `researchSync` co 30 min (i menu IA 4 → „🔬 Odśwież RESEARCH teraz”) czyta z GitHub `research/status.json` i `research/log.jsonl` (branch `research`, token `GITHUB_TOKEN`) i przepisuje arkusz RESEARCH:
- stan: ostatni log, czy program liczy (brak logu > 45 min = nie liczy), komputer, etap i postęp siatki, liczniki z 9.6, strategie aktywne, tempo, łączny czas pracy, stan bazy na Macu, kryteria,
- ostatnie 20 aktywnych strategii: id, data, opis, PF grupy głównej, PF na ślepo, PF skarbca, PF ważony, transakcji, skuteczność,
- dziennik: ostatnie 500 wpisów, najnowsze na górze.

Przy tym samym odświeżeniu arkusz **STRATEGIE** dostaje wszystkie strategie aktywne z `research/strategies.jsonl`, od najwyższego PF ważonego: id, grupa, kierunek, opis reguły, SL %, TP %, PF i liczba transakcji grupy głównej, PF i liczba transakcji skarbca, PF ważony, PF wejścia na ślepo, przewaga, **skuteczność = udział transakcji zamkniętych na TP**, udział wyjść na SL / FC / limit czasu, średni wynik % transakcji zamkniętych przez FC, średni wynik % wszystkich transakcji (wszystko z transakcji grupy głównej i skarbca), mediana świec w pozycji (grupa główna, z `doubleproof.json` → `search_hold_median`), data znalezienia. Arkusz jest przepisywany w całości — jedyne, co się w nim zmienia ręcznie, to checkbox „for VI” w ostatniej kolumnie (sekcja 11a), który przetrwa przepisanie. Pełna reguła i statystyki: plik `research/strategies/{id}.json`.

Przy tym samym odświeżeniu arkusz **STRATEGIE DOUBLEPROOF** dostaje dokładnie te same strategie i w tej samej kolejności co STRATEGIE, policzone na doubleProof (`research/doubleproof.json`, sekcja 6a): id, grupa, opis, SL, TP, for VI (podgląd, zmienia się tylko w STRATEGIE), PF ważony z poszukiwania, **PF doubleProof** (zielony ≥ 1,5, żółty 1–1,5, czerwony < 1), transakcji, mediana świec w pozycji, spółek z transakcjami / 20, spółek z PF > 1, okresów z PF > 1 (z 4), PF na ślepo, przewaga, skuteczność (TP), % SL, % FC, % limit, średni wynik FC i transakcji, stan („aktualna”, „mało transakcji (< 10)”, „brak transakcji”, „jeszcze nie przeliczona”, „wynik z czasu, gdy była aktywna”). Tytuł arkusza podaje zakres dat doubleProof i czas przeliczenia. Tylko do odczytu.

Arkusz **BACKTEST DOUBLEPROOF** pokazuje zapisany jednorazowy backtest (`research/backtest-doubleproof.json`, sekcja 6a). Powstaje przy tym samym odświeżeniu, ale tylko gdy pojawi się nowy plik backtestu (czas backtestu pamiętany w Script Properties `BT_DP_AT`) — potem się nie zmienia. Strategie od najwyższego PF doubleProof (mniej niż 10 transakcji — na dole): id, grupa, opis, SL, TP, PF ważony z poszukiwania, PF doubleProof (kolory jak wyżej), transakcji, mediana świec w pozycji, suma wyników %, średni wynik transakcji %, skuteczność (TP), % SL, % FC, % limit, średni wynik FC, PF na ślepo, przewaga, spółek z transakcjami / 20, spółek z PF > 1, okresów z PF > 1, PF w każdym z 4 okresów, a dalej po jednej kolumnie na spółkę doubleProof: suma wyników % (w notatce komórki: liczba transakcji i PF). Tytuł podaje datę backtestu i zakres danych. Tylko do odczytu.

Arkusz **BACKTEST PORTFELA** pokazuje zapisany backtest portfela (`research/portfolio-backtest.json`, sekcja 6b), tworzony tylko przy nowym pliku (Script Properties `BT_PF_AT`): dla każdego wariantu 7 wierszy (grupa główna, skarbiec, doubleProof całość i okresy 1–4) z miarami z 6b, pod spodem pierwszeństwo strategii (miejsce, id, grupa, transakcji i średni wynik na doubleProof, mediana świec w pozycji, szacunek przewagi, waga własnego wyniku, wybrana). Tylko do odczytu.

Przy każdym odświeżeniu `Research.gs` zapisuje też w Script Properties listę strategii aktywnych (`ACTIVE_IDS`) i pierwszeństwo (`PRIORITY`: lista `priority` z backtestu portfela, a bez niego — kolejność wg PF ważonego) — paper trading nie pyta GitHuba przy każdej świecy.

---

## 11a. Paper trading (`Paper.gs`, `PaperEngine.gs`)

**Kiedy:** w szybkiej ścieżce `runCollector` (sekcja 4 p. 1), zaraz po rundzie, w której wszystkie 53 spółki handlowane mają już tę świecę; jeśli którejś brakuje — 3 min po zamknięciu świecy (`WAIT_AFTER_CLOSE_MIN`), bez niej. Bez osobnego triggera. Ręcznie: menu IA 4 → „📈 Paper trading — przelicz teraz”. Pierwsza świeca dnia zamyka się o 10:30 ET (zwykle 16:30 PL), ostatnia o 16:00 ET (22:00 PL).

**Dane:** wyłącznie z Firestore. Pamięć robocza = ostatnie 1800 świec każdego z 55 instrumentów w ukrytym arkuszu `_IA4_DANE` (JSON pocięty na komórki; obok stan inwestora). Pierwsze zbudowanie: ok. 19 tys. odczytów (raz). Potem przy każdej świecy sesje od ostatniej daty w pamięci (ok. 140 odczytów), raz dziennie 7 dni wstecz (łapie nocne odświeżenie). Pamięć można skasować (usunąć arkusz `_IA4_DANE`) — odbuduje się, ale razem z nią znika stan inwestora.

**Strategie:** aktywne (lista `ACTIVE_IDS` w Script Properties, zapisuje ją `Research.gs`; bez niej — `research/strategies.jsonl`) + zaznaczone „for VI” w arkuszu STRATEGIE. Reguła o danym ID pobierana raz z `research/strategies/` albo `research/archive/` i pamiętana.

**Obliczenia:** `PaperEngine.gs` = sekcja 8 w JavaScript, te same wzory i ta sama kolejność zdarzeń. Średnie okienkowe (WMA, HMA, VWMA) liczone tylko dla końcówki serii (ostatnie 64 świece i świece otwartych pozycji) — te same wartości, mniej pracy. EMA, DEMA, TEMA, KAMA, ZLEMA liczone od początku pamięci (1800 świec; różnica wobec liczenia od początku bazy jest pomijalna). Cecha `since` liczy pełne serie.

**Kolejność na każdej nowej świecy K** (świece po kolei, najwyżej 21 naraz przy nadrabianiu; spółka, której świeca K dotarła dopiero po przeliczeniu, nie dostaje sygnału na tej świecy — jej pozycje są prowadzone dalej normalnie):
1. pozycje inwestora — każda świeca instrumentu po ostatniej obsłużonej: wejście (open świecy po sygnale), potem luka SL/TP → FC → SL → TP → limit (8.6), na koniec FC na zamknięciu,
2. sygnały wszystkich strategii na świecy K na 53 spółkach,
3. inwestor otwiera pozycję „oczekuje” dla sygnału strategii z jego listy, jeśli **spółka nie ma żadnej otwartej ani oczekującej pozycji** (dowolnej strategii) — najwyżej jedna pozycja na spółkę; przy kilku sygnałach na tej samej spółce i świecy wygrywa strategia z najwyższym pierwszeństwem (`PRIORITY`, sekcja 6b; strategia spoza listy — na końcu, potem wg ID).
4. Kolejność zapisu: SIGNALS-REALTIME i VIRTUAL-INVESTOR, potem pamięć `_IA4_DANE`. Czasy: tabela świec w STATS (4a).

**SIGNALS-REALTIME:** wiersz na każdą przeliczoną świecę, najnowsze na górze: data, numer świecy, zamknięcie (PL), liczba sygnałów, potem pary kolumn ID strategii + ticker. Najwyżej 3000 wierszy.

**VIRTUAL-INVESTOR:**
- **wybór strategii: checkbox „for VI” w ostatniej kolumnie arkusza STRATEGIE, bez limitu liczby.** Zaznaczenia są zapamiętywane w Script Properties (`VI_IDS`), bo STRATEGIE jest przepisywany w całości; strategia zaznaczona, która wypadła z aktywnych, zostaje na dole STRATEGIE z dopiskiem „(archiwum)” i dalej działa, dopóki nie odznaczysz. Odznaczenie nie zamyka otwartych pozycji, tylko blokuje nowe. Pierwsze użycie (wersja 1.10) przejmuje ID wpisane ręcznie w VIRTUAL-INVESTOR,
- A4:B23 — podgląd listy „for VI” (pierwsze 19 + „… i N więcej”), tylko do odczytu,
- statystyki (D4:E20): kapitał 100 000 $, stawka 100 $ na transakcję, stan konta = kapitał + wynik zamkniętych, wynik zamkniętych $ i % kapitału, wynik otwartych $, stan konta gdyby teraz zamknąć wszystko, wynik całkowity %, wolna gotówka, liczba pozycji, wyjścia TP/SL/FC/limit, skuteczność (TP), średni wynik zamkniętej, mediana świec w pozycji (zamknięte), koszty transakcyjne $,
- transakcje od wiersza 28: nr, strategia, ticker, kierunek, sygnał, wejście, cena wejścia, SL, TP, status (oczekuje / otwarta / zamknięta), ostatnia świeca, cena aktualna, wynik % i $, wyjście, cena wyjścia, powód, świec w pozycji. Otwarte na górze.
- Wynik % jak w 8.6 p. 6 minus koszt: 2 × `COST_PCT` (0,005% przy wejściu i 0,005% przy wyjściu) — dla pozycji otwartych od wersji 1.15 (starsze bez kosztu); wynik $ = 100 $ × wynik %. Pozycje otwarte pokazują wynik netto (po obu kosztach).

**Test zgodności** (po każdej zmianie sekcji 8, `PaperEngine.gs` albo `ia4/lab`):
```bash
cd ia4-research && python tests/parity_dump.py /tmp/ia4_parity.json && node tests/parity.js /tmp/ia4_parity.json
```
Wynik musi brzmieć „rozbieżności: sygnały 0, transakcje 0”.

---

## 12. Wdrożenie i uruchamianie

### Apps Script — skład

Pliki: `Code.gs`, `Telemetry.gs`, `Research.gs`, `PaperEngine.gs`, `Paper.gs`, `Fx.gs` (+ manifest `appsscript.json`). Triggery (zakłada je „⚙️ Konfiguruj i włącz automat”): `runCollector` co minutę, `telemetryHourly` co godzinę, `researchSync` co 30 min. Script Properties: `GITHUB_TOKEN` (menu „Ustaw token GitHub”) oraz stan automatu (`LIVE_STATE`, `BACKFILL_DP`, `VI_IDS`, `PAPER_LAST_KEY`, `BT_DP_AT`, `BT_PF_AT`, `CANDLE_LOG`, `FX_STATE`, `ACTIVE_IDS`, `PRIORITY` i inne — nie edytować). Arkusze: STATS, RESEARCH, STRATEGIE, STRATEGIE DOUBLEPROOF, BACKTEST DOUBLEPROOF, BACKTEST PORTFELA, SIGNALS-REALTIME, VIRTUAL-INVESTOR, ukryty `_IA4_DANE`.

### Aktualizacja do nowej wersji

1. Wypchnięcie pakietu `.bundle` (polecenia niżej).
2. Apps Script: podmienić pliki `.gs` zmienione w pakiecie (Claude podaje listę) — najprościej zawsze wszystkie sześć; nowy plik dodać przez „+ → Skrypt” z tą samą nazwą. Zapisać, odświeżyć arkusz.
3. „⚙️ Konfiguruj i włącz automat” — tylko gdy zmieniła się lista instrumentów, układ STATS albo triggery (Claude o tym mówi). Konfiguruj odtwarza STATS, triggery i `system/universe` oraz uzupełnia ostatni miesiąc (ok. 2500 zapisów).
4. Mac: `cd ~/Desktop/IA4 && git pull`; `pip install -r requirements.txt`, gdy zmieniły się zależności; zatrzymać program (Ctrl+C) i uruchomić ponownie, gdy zmienił się kod Pythona.

### Mac — na co dzień

```bash
# raz: skrót ia4 (4 procesy = ok. połowa mocy M2, Mac się nie przegrzewa)
echo "alias ia4='cd ~/Desktop/IA4/ia4-research && source .venv/bin/activate && python -m ia4.lab --workers 4'" >> ~/.zshrc
source ~/.zshrc

ia4                 # liczy do Ctrl+C (zapisuje stan i wysyła log przed końcem)
ia4 --hours 4       # liczy 4 godziny
python -m ia4.lab.verify   # tylko przeliczenie strategii na doubleProof (bez szukania)
python -m ia4.lab.backtest_dp   # jednorazowy backtest na doubleProof → arkusz BACKTEST DOUBLEPROOF
python -m ia4.lab.portfolio     # jednorazowy backtest portfela → arkusz BACKTEST PORTFELA + pierwszeństwo w VI
```

Opcje: `--hours N`, `--workers N` (domyślnie rdzenie − 1), `--check` (tylko synchronizacja i kontrola bazy), `--no-sync`, `--no-push`. Program można przerwać w dowolnym momencie — wznawia od ostatniego punktu (twarde zamknięcie traci najwyżej 30 min pracy; strategie są wysyłane od razu). Test silnika: `python -m ia4.lab.selftest`.

### Limity Firestore (plan Spark: 20 000 zapisów i 50 000 odczytów na dzień)

| Część | Zapisy | Odczyty |
|---|---|---|
| zbieranie na żywo (75 instrumentów, 7 świec) | ok. 1100 / dzień | — |
| moduł EURUSD (świeca 5 min: dokument dnia + podsumowanie) | ok. 580 / dzień (rynek otwarty), historia ok. 60 raz | — |
| nocne odświeżenie + liczenie bazy | ok. 550 / noc | ok. 150 / noc |
| historia doubleProof (do zakończenia) | najwyżej 8000 / dzień | — |
| „Konfiguruj” / „Uzupełnij ostatni miesiąc” | ok. 2500 / raz | — |
| paper trading | — | pierwsze zbudowanie pamięci ok. 19 000 (raz), potem ok. 150 / świecę + ok. 650 raz dziennie |
| Mac: `ia4.sync` przyrostowo | — | kilkaset / start |
| Mac: odświeżanie doubleProof w `ia4.lab` | — | ok. 250 / godzinę pracy |
| Mac: pierwsza synchronizacja nowych instrumentów (doubleProof) | — | ok. 10 000 (raz) |
| Mac: `ia4.sync --full` | — | ok. 48 000 — nie łączyć tego samego dnia z innymi dużymi odczytami |

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
