# IA 4 — instrukcja projektu

**Wersja:** 1.30
**Data:** 11 października 2026
**Aktualny etap:** ✅ Etap 1 — baza akcji (działa bez końca) · 🟨 Etap 2 — poszukiwanie strategii (wstrzymane od 3.10.2026, 60 aktywnych strategii) · 🟨 Etap 3 — paper trading i wirtualny inwestor akcji · 🟨 Etap 4 — FX na świecach 1h: zbieranie 10 par + BTC (od 1.27) i prognoza rozkładu (krok FX-7: kalibracja `fx-cond/2` i H-001 do zrobienia) · 🟨 Etap 5 — strona IA4 `https://miszyszka.github.io/IA4/` (od 1.28). Mapa całości i lista otwartych kroków: sekcja 0. Jak czytać arkusze i stronę: `PRZEWODNIK.md`.

Ten plik jest jedynym źródłem prawdy i zbiorem żelaznych zasad projektu. Jeśli kod, arkusz albo telemetria się z nim rozjeżdżają, obowiązuje ten plik, a rozbieżność trzeba naprawić.

---

## 0. Mapa projektu i stan na dziś (czytać najpierw)

IA 4 to system, który **zbiera świece z Yahoo do Firestore** (Apps Script, bez Maca), **liczy na nich** (Python na Macu) i **pokazuje wyniki** (arkusz Google i strona IA4). Trzy filary:

| Filar | Co robi | Gdzie działa | Sekcje |
|---|---|---|---|
| **A. Akcje i wirtualny inwestor** | baza świec 1h 75 spółek (NYSE) → poszukiwanie strategii `ia4-rule/1` (wstrzymane, 60 aktywnych) → sygnały na żywo i wirtualny inwestor (paper trading, 100 $ na transakcję) | zbieranie, sygnały, inwestor: Apps Script (`Code.gs`, `Paper.gs`, `PaperEngine.gs`); poszukiwanie, weryfikacja doubleProof, backtesty: Mac (`ia4.lab`) | 4, 4a, 6–11a |
| **B. FX** — dwa programy na jednych danych | **B1 zbieranie:** świece 1h 10 par walutowych + BTC/USD → `fx1h` w Firestore (Apps Script, `Fx.gs`, od 1.27). **B2 prognoza:** 1000 okoliczności z ratingiem i prognoza rozkładu 48 świec (stożek, zakres, P(wzrost), scenariusze) — FX-research (ręcznie) i FX-real-time (co 30 s) na Macu | B1: Apps Script; B2: Mac (`ia4.fx`) | 4b, 4c |
| **C. Strona IA4** | konsola systemu na GitHub Pages: System (czy żyje), Inwestor, FX; hasło; wersja na telefon | przeglądarka; dane tylko z publicznego repo | 11b |

**Przepływ danych:** Yahoo → Apps Script (trigger co minutę) → Firestore → (a) Mac: kopia lokalna → wyniki na branche `research`, `fx`, `fx-live`; (b) Apps Script: arkusze i `telemetry/` na `main` → strona IA4 czyta wszystkie branche. Python nigdy nie pisze do Firestore ani do `main` (zasady 1, 11).

**Gdzie co leży:**

| Miejsce | Zawartość | Kto pisze |
|---|---|---|
| Firestore | `stocks`, `proof`, `context`, `doubleProof` (akcje, 4), `fx1h` + `system/fx1h` (FX, 4b), `system/universe`, `system/status` | Apps Script |
| branch `main` | kod (`*.gs`, `ia4-research/`), ta instrukcja, `PRZEWODNIK.md`, `telemetry/state.json`, `telemetry/vi.json`, strona `docs/` | Claude (pakiety `.bundle`), Apps Script (`telemetry/`) |
| branch `research` | strategie, dziennik poszukiwania, doubleProof, backtest portfela (10) | Mac (`ia4.lab`) |
| branch `fx` | katalog okoliczności, ratingi, przeliczenia FX-research, archiwum `fx-cond/1` (4c.12) | Mac (`ia4.fx`) |
| branch `fx-live` | `forecast.json` — prognoza na żywo (4c.9) | Mac (FX-real-time) |
| arkusz Google | STATS, FX, OKOLICZNOSCI_FX, STRATEGIE, BACKTEST PORTFELA, SIGNALS-REALTIME, VIRTUAL-INVESTOR, `_IA4_DANE` | Apps Script |
| Mac `ia4-research/data/` | kopie lokalne (akcje `*.parquet`, FX `fx1h/`) — robocze, do odtworzenia | Mac |

**Historia w skrócie:** 1.0–1.1 baza akcji i poszukiwanie · 1.2–1.14 sita, skarbiec, doubleProof, paper trading (1.8), poszukiwanie wstrzymane (1.14) · 1.15–1.19 szybka ścieżka, wirtualny inwestor z kosztami, backtest portfela, moduł EURUSD 5 min · 1.20–1.26 prognoza EURUSD 5 min (katalog `fx-cond/1`, ratingi, dashboard, prognoza rozkładu) · 1.27 FX na świecach 1h, 11 instrumentów, wszystko liczone od nowa · 1.28 strona IA4 i `telemetry/vi.json` · 1.29 porządek instrukcji (ta sekcja) · 1.30 kalibracja FX: warunek częstości na pojedynczym instrumencie. Szczegóły: sekcja 13.

**Otwarte kroki (stan 11.10.2026)** — do odhaczenia przez Claude na podstawie telemetrii i branchy:
1. Apps Script w wersji 1.29 (`telemetry/state.json` → `version`) — podmienić wszystkie pliki `.gs` po każdym pakiecie (sekcja 12).
2. Historia FX 1h: `state.json` → `fx.history` = `11/11` (11.10.2026 13:13: `10/11`).
3. Stara baza EURUSD 5 min usunięta z menu „🗑 FX — usuń stare świece EURUSD 5 min” (dopiero po pkt 2; nieodwracalne, 4b).
4. GitHub Pages przestawione na `main` / `/docs` (11b) — do tej chwili pod adresem strony jest dawny dashboard z brancha `fx`.
5. `telemetry/vi.json` pojawia się po pierwszej świecy sesji po wdrożeniu 1.28+ (11b).
6. Mac: `git pull`, `python -m ia4.fx.selftest`, `python -m ia4.fx.sync`, kalibracja próbna `python -m ia4.fx.catalog` (pierwsza próba 11.10.2026 → poprawka 1.30, potrzebna druga próba) → przegląd `data/fx1h/catalog-preview.csv` z Claude → `python -m ia4.fx.catalog --commit` (raz, zasada 14) → `python -m ia4.fx.research` (H-001) → `python -m ia4.fx.live` (krok FX-7, sekcja 7).
7. Później, tylko za zgodą człowieka: strategie FX i wirtualny inwestor FX (`telemetry/fx-vi.json`, krok FX-8, sekcja 7).

---

## 1. Cel

1. **Baza świec 1h w Firestore** (Etap 1, działa stale): kompletna, rośnie każdego dnia sesyjnego, ma stały format.
2. **Poszukiwanie strategii** (Etap 2): program w Pythonie na Macu, uruchamiany w dowolnych momentach, bez końca przelicza kopię lokalną bazy i szuka powtarzalnych sygnałów long i short opartych na średnich kroczących. Liczy się jakość, nie liczba strategii: strategia ma trafiać w TP, a nie zarabiać na samym trzymaniu pozycji w hossie. Każda zapisana strategia jest regułą opisaną na sztywno (sekcja 8), tak żeby inny system mógł ją odtworzyć świeca po świecy.
3. **Paper trading** (Etap 3): sygnały strategii na żywo i wirtualny inwestor w Apps Script, po każdej zamkniętej świecy (sekcja 11a).
4. **Weryfikacja na nowych spółkach:** grupa doubleProof (20 spółek), której system nigdy nie widzi przy szukaniu — do sprawdzania strategii przez człowieka (sekcja 6a).
5. **Moduł FX 1h:** osobna baza świec godzinowych 10 najczęściej handlowanych par walutowych i Bitcoina (sekcja 4b).
6. **Prognoza FX** (Etap 4): co może się stać z kursem każdego z 11 instrumentów w ciągu 48 świec 1h — rozkład z prawdziwych historycznych ścieżek (stożek, oczekiwany zakres, prawdopodobieństwo wzrostu, scenariusze) i 1000 okoliczności z ratingiem; przeliczenie na Macu, prognoza na żywo i zakładka FX strony IA4 (sekcje 4c, 11b).

Historia wcześniejszych prac (strategie S1/S2, backtesty, etapy 0–5) jest w historii gita do wersji 0.47.

---

## 2. Żelazne zasady

1. **Firestore jest jedynym źródłem danych.** Kopia na Macu (`ia4-research/data/`) to tylko kopia robocza — można ją skasować i odtworzyć. Python nigdy nie pobiera świec z Yahoo i nigdy nie pisze do Firestore.
2. **Baza tylko rośnie.** Zapisujemy wyłącznie zamknięte świece. Niczego nie kasujemy. Wolno przepisać sesję tylko danymi pobranymi ponownie z Yahoo (nocne odświeżenie, „Uzupełnij ostatni miesiąc”). Jedyny wyjątek: moduł FX uzupełnia świece, których Yahoo nie oddało po 3 próbach, uśrednieniem — zawsze oznaczonym w dokumencie (`fillT`, sekcja 4b). Jedyne skasowanie danych w historii projektu: stara baza EURUSD 5 min (`fx/EURUSD`, wersje 1.15–1.26) — decyzja człowieka z 10.10.2026 przy przejściu na świece 1h, wykonywana ręcznie z menu z potwierdzeniem (4b).
3. **Format bazy (sekcja 4) jest stały.** Każda jego zmiana wymaga najpierw zmiany tej instrukcji, zgody człowieka i opisu migracji istniejących danych.
4. **Skarbiec = najstarsze 800 świec każdego instrumentu** (sekcja 6). Poszukiwanie nigdy nie widzi wyników skarbca. Skarbiec otwiera wyłącznie bramka skarbca, dla strategii, która przeszła wszystkie sita grupy głównej. Każde otwarcie jest liczone i zapisywane.
5. **Sekrety nigdy nie trafiają do repozytorium:** klucz serwisowy Firebase (`~/.ia4/serviceAccount.json`) i token GitHub (Script Properties → `GITHUB_TOKEN`).
6. **System jest minimalny.** Nowa funkcja, arkusz, plik czy dziennik pojawia się tylko za zgodą człowieka i najpierw jako zmiana tej instrukcji.
7. **Współpraca z Claude:**
   - na początku rozmowy Claude pobiera repozytorium `github.com/miszyszka/IA4.git`, czyta ten plik (branch `main`), `telemetry/state.json` (branch `main`) oraz `research/status.json` i `research/log.jsonl` (branch `research`), a gdy istnieją — `telemetry/vi.json` (branch `main`), `fx/runs.jsonl` (branch `fx`) i `forecast.json` (branch `fx-live`); potem sprawdza listę otwartych kroków w sekcji 0 i aktualizuje ją w kolejnym pakiecie,
   - Claude przygotowuje zmiany jako commit w pliku `.bundle` (wysyła go w rozmowie, użytkownik zapisuje w `~/Downloads`) i podaje gotowe polecenia terminala do wypchnięcia (sekcja 12); lokalna kopia `~/Desktop/IA4` aktualizuje się przez `git pull`,
   - każdą zmianę Claude sprawdza przed wysłaniem: `selftest`, test zgodności (sekcja 11a), składnia plików `.gs`, symulacja zmienionej logiki,
   - pracę wykraczającą poza tę instrukcję albo pomysł na jej zmianę Claude najpierw proponuje i czeka na zgodę,
   - Claude nie ma dostępu do arkusza ani edytora Apps Script: użytkownik ręcznie wkleja zmienione pliki `.gs` do Apps Script i robi `git pull` na Macu.
8. **Jedna wersja dla całego projektu.** Ten sam numer w nagłówku tej instrukcji, w nagłówku każdego pliku `.gs`, w `CONFIG.VERSION` (`Code.gs`), w `ia4-research/` (`ia4/__init__.py`) i w stronie (`docs/`, `VERSION` w `js/core.js`). Zmiana znacząca (logika, zasada, format, etap) podbija wersję i dostaje wpis w sekcji 13. Drobne poprawki — tylko opis w commicie. (`appsscript.json` nie nosi wersji — JSON nie ma komentarzy.)
9. **Strategia to reguła, nie kod.** Każda zapisana strategia jest pełną regułą w języku `ia4-rule/1` (sekcja 8): linie, sygnał, filtry, SL, TP, FC, limit czasu — wszystko liczbami, bez parametrów domyślnych. Definicje z sekcji 8 zmienia się tylko razem z nową wersją języka (`ia4-rule/2`); stare strategie zachowują swoją wersję.
10. **Symulacja jest zawsze pesymistyczna** (sekcja 8.6). Strategie (poszukiwanie, weryfikacja, backtest doubleProof) liczone są bez kosztów transakcyjnych, każda reguła na wszystkich hipotezach SL × TP naraz. Koszt transakcyjny (`COST_PCT` = 0,005% wartości pozycji przy wejściu i przy wyjściu) liczą tylko wirtualny inwestor (11a) i backtest portfela (6b).
11. **Wyniki poszukiwania żyją na branchu `research`** (sekcja 10), wyniki prognozy FX — na branchach `fx` i `fx-live` (sekcja 4c.12). Python nie pisze do `main`; `main` to kod, ta instrukcja, telemetria automatu (`telemetry/`) i strona IA4 (`docs/`, sekcja 11b).
12. **Jeden język reguł, dwie implementacje.** Reguły liczy Python (`ia4/lab`, backtest) i JavaScript (`PaperEngine.gs`, na żywo). Każda zmiana definicji z sekcji 8 musi trafić do obu naraz, a test zgodności (`ia4-research/tests/`, sekcja 11a) musi dać 0 rozbieżności.
13. **Mediana trzymania.** Każdy wynik strategii albo portfela (arkusze, pliki wyników) podaje medianę świec w pozycji: świeca wyjścia − świeca wejścia + 1.
14. **Katalog okoliczności FX jest nienaruszalny.** Po jednorazowej kalibracji (sekcja 4c.2) ID, definicje i progi okoliczności nigdy się nie zmieniają; nowy katalog powstaje tylko jako nowa wersja (`fx-cond/3`), za zgodą człowieka. Obowiązuje `fx-cond/2` (świece 1h, od 1.27); `fx-cond/1` (EURUSD 5 min) — tylko w archiwum (4c.2).
15. **Prognoza zawsze z niepewnością i dowodem.** Prognoza FX pokazuje rozkład (stożek, zakres, P(wzrost)), nigdy samą linię. Linia środkowa odchyla się od ceny bieżącej tylko w takim stopniu, w jakim sprawdzian na danych niewidzianych przez model (4c.7) potwierdził jej przewagę; strona IA4 zawsze pokazuje wynik sprawdzianu słowami.

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
Yahoo 10 par + BTC (1h) ──(Fx.gs, w tym samym triggerze)──▶ Firestore fx1h/*, system/fx1h (moduł FX, sekcja 4b) ──▶ arkusz FX
Firestore fx1h ──(ia4.fx.sync)──▶ Mac: data/fx1h/ ──▶ ia4.fx.research (ręcznie) ──▶ GitHub fx: ratingi, index.html ──▶ arkusz OKOLICZNOSCI_FX
                                                  └──▶ ia4.fx.live (co 30 s) ──▶ GitHub fx-live: forecast.json
GitHub main: telemetry/state.json, telemetry/vi.json · research · fx · fx-live ──(przeglądarka, tylko odczyt)──▶ strona IA4: GitHub Pages z main/docs (sekcja 11b)
```

| Plik | Rola |
|---|---|
| `Code.gs` | automat: listy instrumentów, zbieranie na żywo (szybka ścieżka po zamknięciu świecy), nocne odświeżenie, liczenie bazy, pobieranie historii doubleProof, zapis do Firestore, arkusz STATS, menu, triggery |
| `Fx.gs` | moduł FX 1h: świece 1h 10 par walutowych i BTC z Yahoo → Firestore `fx1h`, arkusz FX, opóźnienia w STATS (sekcja 4b); arkusz OKOLICZNOSCI_FX (4c.11) |
| `Telemetry.gs` | stan zbierania → `telemetry/state.json`, stan wirtualnego inwestora → `telemetry/vi.json` w GitHub (branch `main`) |
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
| `telemetry/vi.json` | wirtualny inwestor dla strony IA4 (pozycje, transakcje, strategie, sygnały), generowany po każdej świecy — nie edytować (11b) |
| `docs/` | strona IA4 — konsola systemu na GitHub Pages: `index.html`, `css/`, `js/` (moduły bez buildu), `fonts/`, `README.md` — jak rozwijać (sekcja 11b) |
| `IA4_INSTRUKCJA.md` | ten plik |
| `ia4-research/ia4/fx/` | prognoza FX 1h (sekcja 4c): `instruments.py` (lista 11 instrumentów i godziny rynku — kopia z `Fx.gs`), `sync.py` (Firestore `fx1h` → `data/fx1h/`), `series.py` (seria, lustro, wskaźniki 4c.3; średnie, ATR, RSI z `ia4/lab/indicators.py`), `catalog.py` (okoliczności `fx-cond/2`, kalibracja na puli instrumentów), `selftest.py` i `synth.py` (dane syntetyczne do testów), `research.py` (pula, wystąpienia, profile, ratingi walk-forward, środek prognozy), `scenario.py` (prognoza rozkładu i jej sprawdzian, 4c.6–4c.7), `live.py` (prognoza na żywo), `store.py` (branche `fx` i `fx-live`), `dashboard/index.html` |
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
4. **Ręcznie:** menu IA 4 → „Uzupełnij ostatni miesiąc” (po dłuższej przerwie automatu), „Nocne odświeżenie teraz”, „Historia doubleProof — jedna porcja teraz”, „💱 FX 1h — pobierz teraz” (sekcja 4b).
5. **Historia doubleProof (jednorazowo, sama się kończy).** Raz na godzinę, w wolnym przebiegu `runCollector`, jedna porcja: dla każdej spółki doubleProof bez pełnej historii kolejne 60 dni wstecz (Yahoo `period1/period2`, okna od północy do północy UTC — sesja nigdy nie jest dzielona). Zaczyna od wczoraj, kończy na granicy Yahoo (728 dni wstecz albo odpowiedź Yahoo „poza zakresem 730 dni”). Ok. 840 zapisów na porcję, ok. 10 tys. łącznie; najwyżej 8000 zapisów dziennie, więc całość trwa ok. 12–13 godzin pracy rozłożonych na 1–2 dni. Stan: Script Properties `BACKFILL_DP`, postęp w STATS („Historia doubleProof”) i w `telemetry/state.json` (`doubleProofHistory`). Dzisiejsze i ostatnie sesje zapisują zbieranie na żywo i nocne odświeżenie, jak dla pozostałych instrumentów.

Limity Firestore (plan Spark): 20 000 zapisów i 50 000 odczytów dziennie — zużycie wszystkich części systemu: sekcja 12, „Limity Firestore”.

### 4a. Arkusz STATS

Przepisywany przy każdym uruchomieniu automatu. Układ oznacza znacznik w komórce A2 (`stats-1.15`); inny znacznik albo brak arkusza — arkusz buduje się sam od nowa.

**Blok stanu** (od wiersza 3): status (OK / BŁĄD), ostatnie uruchomienie (PL, z watchdogiem „brak uruchomień > 15 min”), ostatnia akcja, czas w Nowym Jorku, sesja USA, trigger, **czas pracy automatu dziś** (suma czasu wszystkich uruchomień — limit Google dla konta Gmail to 90 min triggerów dziennie), zapisanych świec dziś, błędów dziś, ostatni błąd, nocne odświeżenie, świec w bazie, 3 wiersze modułu FX 1h (sekcja 4b).

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

### 4b. Moduł FX 1h (`Fx.gs`)

Osobny moduł: **zbiera** świece godzinowe 10 najczęściej handlowanych par walutowych i Bitcoina. Nie bierze udziału w poszukiwaniu, weryfikacji ani paper tradingu. Kopię na Macu i prognozę ma osobny moduł prognozy (sekcja 4c). Obowiązują go zasady 2.1–2.3 z jednym wyjątkiem (uśrednione świece, niżej). Od 1.27 zastępuje dawną bazę EURUSD 5 min (`fx/EURUSD`, wersje 1.15–1.26), którą usuwa się z menu (decyzja człowieka z 10.10.2026, zasada 2.2).

- **Instrumenty (11)** — kolejność = kolumny arkusza FX. Lista jest w `Fx.gs` (`FX.INSTRUMENTS`) i w `ia4-research/ia4/fx/instruments.py`; zmiana listy = zmiana tej instrukcji i obu plików naraz.

  | ID | Yahoo (zapasowy) | Grupa | Pips | Miejsc |
  |---|---|---|---|---|
  | EURUSD | `EURUSD=X` | fx | 0,0001 | 6 |
  | USDJPY | `JPY=X` (`USDJPY=X`) | fx | 0,01 | 4 |
  | GBPUSD | `GBPUSD=X` | fx | 0,0001 | 6 |
  | AUDUSD | `AUDUSD=X` | fx | 0,0001 | 6 |
  | USDCAD | `CAD=X` (`USDCAD=X`) | fx | 0,0001 | 6 |
  | USDCHF | `CHF=X` (`USDCHF=X`) | fx | 0,0001 | 6 |
  | NZDUSD | `NZDUSD=X` | fx | 0,0001 | 6 |
  | EURJPY | `EURJPY=X` | fx | 0,01 | 4 |
  | GBPJPY | `GBPJPY=X` | fx | 0,01 | 4 |
  | EURGBP | `EURGBP=X` | fx | 0,0001 | 6 |
  | BTCUSD | `BTC-USD` | crypto | 1 USD | 2 |

  Dobór (10.10.2026): 7 par „głównych” (każda z USD — razem większość światowego obrotu walutami według badania BIS 2025) i 3 najpłynniejsze pary krzyżowe (EURJPY, GBPJPY, EURGBP). Pominięte: USD/CNY (kurs sterowany, handel w ograniczonych godzinach) i USD/HKD (kurs sztywny) — mało informacji o ruchach rynku. Bitcoin jako osobna grupa (`crypto`): handel 24/7, inna zmienność. Symbol zapasowy — gdy Yahoo nie odpowie na podstawowy, ponowienie przez drugi serwer Yahoo pyta o zapasowy.
- **Źródło:** Yahoo, `interval=1h`. Yahoo trzyma świece 1h ok. 730 dni wstecz, więc historia zaczyna się 728 dni przed startem modułu (pierwszy dzień bazy może być niepełny). Ceny Yahoo dla walut są orientacyjne; wolumen nie jest zapisywany.
- **Świeca:** 1 godzina, opisana czasem początku w UTC (pełna godzina). Zapisujemy tylko świece zamknięte. Ceny zaokrąglone do liczby miejsc z tabeli. Wpisy Yahoo poza godzinami rynku są pomijane.
- **Godziny rynku:** pary walutowe — od niedzieli 17:00 do piątku 17:00 czasu Nowego Jorku; BTC — zawsze. **Oczekiwane świece dnia (UTC)** = świece, których początek wypada w tych godzinach: pary walutowe pon.–czw. **24**, piątek 21 (latem; zimą 22), niedziela 3 (zimą 2), sobota 0; BTC — 24 każdego dnia. Weekend nie jest brakiem.
- **Format w Firestore:**
  ```
  fx1h/{SYMBOL}/days/{RRRR-MM-DD}   jeden dokument na instrument i dzień UTC
    symbol, date, interval ("1h"), bars (świec razem, z uśrednionymi),
    t [] (minuta dnia UTC początku świecy: 0, 60, … 1380), o [], h [], l [], c []   (tablice równoległe),
    expected (oczekiwanych), missing (brakujących), filled (uśrednionych),
    fillT [] (minuty świec uśrednionych — NIE pochodzą z Yahoo), tries (próby kontroli),
    status ("dzień trwa", "do kontroli", "braki — próba n z 3", "kompletny",
            "uzupełniony: N świec uśrednionych", "historia: uzupełniony: N świec uśrednionych",
            "brak danych z Yahoo — nie da się uśrednić (brak świec obok)", "weekend — brak handlu",
            "pierwszy dzień bazy — od HH:MM UTC"), updatedAt
  fx1h/{SYMBOL}                     podsumowanie: symbol, yahoo, group, interval, pip, digits,
                                    historyFirstDate, historyAt, historyBars, updatedAt
  system/fx1h                       interval, symbols [] (lista instrumentów), groups {ID: grupa},
                                    last {ID: początek ostatniej świecy}, lastClose {ID: zamknięcie}, updatedAt
  ```
  Soboty par walutowych nie mają dokumentów. `system/fx1h` to jeden dokument dla Maca: z niego FX-real-time wie, które instrumenty mają nową świecę (4c.9).
- **Historia (jednorazowo, sama się kończy):** w wolnym uruchomieniu `runCollector` (gdy automat nie zbiera akcji, nocnego odświeżenia ani historii doubleProof) jeden instrument: całe 728 dni jednym zapytaniem Yahoo, zapis wszystkich dni (ok. 640 dokumentów na instrument, ok. 7000 łącznie). Dni starsze niż wczoraj — braki od razu uśrednione (Yahoo właśnie oddało wszystko, co ma; status „historia: uzupełniony…”), wczoraj — zwykła kontrola, dziś — „dzień trwa”. Nieudana próba — kolejna za 30 min. Cała historia: ok. 11 uruchomień (kilkanaście minut). Instrument bez historii nie jest zbierany na żywo.
- **Na żywo:** w każdym uruchomieniu `runCollector` (co minutę) i co 10 s w szybkiej ścieżce akcji — jeden trigger dla całego automatu (dzienny limit czasu triggerów). Instrument jest pobierany, gdy powinna już być zamknięta świeca nowsza niż ostatnia zapisana (zamknięcie + 20 s; pary walutowe tylko w godzinach rynku). Wszystkie takie instrumenty jednym `fetchAll`, każdy od początku dnia UTC ostatniej zapisanej świecy; dokument dnia z nową świecą przepisywany w całości (status „dzień trwa”), potem `system/fx1h` — wszystko w jednym zapisie. Spóźniona świeca: próba w każdym uruchomieniu przez 10 min od zamknięcia, potem co 10 min.
- **Kontrola zakończonego dnia:** od 00:20 UTC wczorajszy dzień każdego instrumentu trafia do kolejki (`FX1H_CHECK`; sobota par walutowych — nie). **Próba** = świece z Firestore + cały dzień pobrany z Yahoo na nowo (z zapasem ±1 h; świeże z Yahoo wygrywają) → braki liczone od nowa. Do **3 prób co 60 min**; najwyżej 11 par (instrument, dzień) na jedno uruchomienie.
  - brak braków → „kompletny”,
  - po 3 próbach z brakami → **uśrednienie wszystkich braków** — każdy dzień kończy się kompletny (zapisanych = oczekiwanych); „brak danych z Yahoo — nie da się uśrednić” tylko wtedy, gdy przed i po brakującej świecy nie ma żadnej świecy,
  - pierwszy dzień bazy (zaczyna się w połowie — granica historii Yahoo): oczekiwane świece liczone od jego pierwszej świecy,
  - dni starsze niż 726 dni (Yahoo ich już nie odda) — od razu uśrednienie,
  - dzień z wynikiem końcowym wypada z kolejki i nie jest już zmieniany.
- **Uśrednienie** (interpolacja liniowa): dla brakującej świecy t — najbliższa świeca przed (P) i po (N), także z sąsiedniego dnia. Cena biegnie liniowo od zamknięcia P do otwarcia N: open = wartość w chwili t, close = w chwili t + 1 h, high/low = większa/mniejsza z nich. Tylko P albo tylko N — świeca płaska na tej cenie. Świece uśrednione są zawsze w `fillT`; analiza (4c) nie używa ich jako wystąpień ani wyników.
- **Opóźnienie świecy** = chwila potwierdzenia zapisu w Firestore − zamknięcie świecy (początek + 1 h).
- **Arkusz FX — jeden wiersz na dzień UTC** (najnowszy na górze, także soboty), kolumny: data, dzień tygodnia i po jednej kolumnie na instrument: **`zapisanych/oczekiwanych`**, np. `24/24`, a gdy były uśrednione — `24/24 (1)` (komórka żółta); `—` = dzień bez handlu (sobota par walutowych). Komórka pojawia się, gdy historia albo kontrola zakończy dzień (zwykle 00:20–02:20 UTC następnego dnia), i już się nie zmienia. Dzień, który trwa albo czeka na kolejną próbę, nie ma jeszcze komórki. Czy zbieranie działa i opóźnienia — STATS.
- **STATS** (3 wiersze bloku stanu): „FX 1h — ostatnia świeca” (najnowsza świeca, ile instrumentów aktualnych), „FX 1h — opóźnienie” (ostatni zapis, opóźnienie, mediana i 90% opóźnień dziś), „FX 1h — dziś / historia” (świece i braki dziś, wczoraj skontrolowanych i uśrednionych, historia N/11 od daty, kolejka kontroli). Telemetria: pole `fx` (4a, `telemetry/README.md`).
- Stan: Script Properties `FX1H_STATE`, `FX1H_CHECK`. Ręcznie: menu IA 4 → „💱 FX 1h — pobierz teraz” (świece na żywo i jedna porcja historii, jeśli trwa), „💱 FX 1h — przelicz arkusz FX” (arkusz od nowa z Firestore — ok. 1 odczyt na dokument dnia, ok. 7000; dni niekompletne i dni z handlem bez dokumentu trafiają do kontroli), „🗑 FX — usuń stare świece EURUSD 5 min” (jednorazowo, z potwierdzeniem: kasuje `fx/EURUSD/days/*`, `fx/EURUSD` oraz `FX_STATE`, `FX_CHECK` — ok. 65 odczytów i 66 zapisów; nieodwracalne).

### 4c. Prognoza FX 1h (`ia4-research/ia4/fx/`, Etap 4)

Cel: **co może się stać z kursem każdego z 11 instrumentów (4b) w ciągu 48 kolejnych świec 1h** — rozkład możliwych ścieżek ze statystyki historycznych świec i „okoliczności” (4c.0). Pary walutowe liczą 48 świec w godzinach rynku (weekend pomijany), BTC — 48 godzin. Dwa programy w Pythonie na Macu — **FX-research** (tylko ręcznie) i **FX-real-time** (gdy Mac jest włączony) — oraz dashboard na GitHub Pages i arkusz OKOLICZNOSCI_FX. Moduł tylko czyta Firestore (zasada 2.1) i nie wpływa na zbieranie (4b), poszukiwanie strategii ani paper trading.

#### 4c.0 Zasada: rozkład, nie jedna linia

Kurs walutowy jest bardzo bliski błądzeniu losowemu: średnia z setek historycznych scenariuszy zawsze wychodzi blisko zera, więc jedna „uśredniona” linia jest prawie pozioma — i to jest poprawny wynik, nie błąd. Doświadczony trader nie pyta „jaka będzie linia”, tylko: **w jakim zakresie się poruszymy, z jakim prawdopodobieństwem w którą stronę i jak wyglądały najbardziej podobne sytuacje** — z ich skokami i wahaniami.

Badanie na EURUSD 5 min (przeliczenie R-001, 13 080 świec, 9.10.2026 — dane usunięte w 1.27): kierunek ≈ rzut monetą (Brier ≈ 0,25–0,27), za to **zakres i rozrzut dało się przewidzieć** — pora dnia i zmienność zmniejszały błąd prognozy zakresu z 47% do 27–29%; bez skalowania zmiennością stożek 80% obejmował tylko 55% przypadków. Na świecach 1h i 11 instrumentach odpowiedź trzeba sprawdzić od nowa — daje ją sprawdzian (4c.7) w każdym przeliczeniu.

Dlatego prognoza to **rozkład** (4c.6): stożek 50% i 80%, oczekiwany zakres 48 h, P(wzrost), 3 prawdziwe scenariusze z historii i linia środkowa, która odchyla się tylko o tyle, o ile sprawdzian potwierdził jej przewagę (zasada 15). Okoliczności i ratingi (4c.2–4c.5) dają środek prognozy i dobór analogów, a sprawdzian przy każdym przeliczeniu mierzy, czy wnoszą coś ponad porę dnia.

Dlaczego 1h i 11 instrumentów (1.27): przy 5 min 48 świec to tylko 4 h, a 60 dni historii Yahoo dawało ok. 60 niezależnych 4-godzinnych okien. Przy 1h historia sięga 2 lat (ok. 12 000 świec na parę), a 11 instrumentów razem — ok. 140 000 świec; wszystkie wielkości są w jednostkach zmienności (ATR100), więc statystyki różnych par można łączyć.

#### 4c.1 Dane

- **Kopia lokalna:** `python -m ia4.fx.sync` (oba programy wołają ją przy starcie) → `ia4-research/data/fx1h/{SYMBOL}.parquet`: kolumny `time` (początek świecy, sekundy UTC), `o, h, l, c`, `filled` (świeca z `fillT` — uśredniona), posortowane po `time`; stan w `data/fx1h/_manifest.json` (dla każdego instrumentu najnowsze `updatedAt`). Lista instrumentów z `system/fx1h` (bez Firestore — `instruments.py`). Przyrostowo: tylko dokumenty dni z `updatedAt` nowszym niż w manifeście (minus 30 min zapasu; zwykle 1–3 odczyty na instrument); pierwszy raz — wszystkie dni (ok. 7000 odczytów); `--full` — od nowa. Dokument dnia zastępuje wszystkie lokalne świece swojego dnia. Stara kopia EURUSD 5 min (`data/fx/`) jest usuwana przy pierwszej synchronizacji.
- **Seria:** wszystkie świece instrumentu w kolejności czasu; `t` to indeks w serii (jak w sekcji 8 — przez noce i weekendy bez przerwy w indeksie). Wskaźniki liczone na całej serii, także na świecach uśrednionych.
- **Przerwa:** między kolejnymi świecami serii brakuje co najmniej jednej oczekiwanej świecy rynku (4b). Weekend par walutowych nie jest przerwą.
- **Pips** (tylko do wyświetlania): 0,0001 (pary z USD, EURGBP), 0,01 (pary z JPY), 1 USD (BTC). Obliczenia — w jednostkach ATR100 (4c.3).
- **Pula:** FX-research i FX-real-time łączą wszystkie instrumenty w jedną tablicę świec (bloki instrumentów jeden po drugim). Wskaźniki i okoliczności zawsze liczone osobno na serii każdego instrumentu.

#### 4c.2 Okoliczności (katalog `fx-cond/2`)

- **Okoliczność** = warunek prawda/fałsz na świecy `t`, liczony wyłącznie ze świec ≤ `t` (o, h, l, c) tego samego instrumentu. Wartość, której nie da się policzyć, daje fałsz (jak w sekcji 8).
- **1000 okoliczności = 500 par lustrzanych.** Każda ma kierunek: `+` (wzrost, wysoka cena) albo `−` (spadek, niska cena). Para to ten sam warunek odbity: ceny i różnice ze znakiem przeciwnym, ten sam próg. ID `FX-0001` … `FX-1000`; para = kolejne numery, nieparzysty `+`, parzysty `−`.
- Każda okoliczność ma: rodzinę, opis słowny po polsku, definicję formalną (rodzaj + wszystkie parametry liczbami) i próg. **Ten sam katalog i te same progi dla wszystkich 11 instrumentów** — dlatego wszystkie cechy są bezwymiarowe (jednostki ATR100, %, liczby świec).
- **Wskaźniki:** wzory z sekcji 8.2 (SMA, EMA, WMA, HMA, DEMA, TEMA, KAMA, ZLEMA, ATR, RSI — w module FX także z innymi okresami niż 14) oraz wskaźniki z tabeli 4c.3. VWMA nie jest używana (brak wolumenu).
- **Kalibracja tylko raz** — `python -m ia4.fx.catalog --commit` (krok FX-7; odmawia, gdy `fx/conditions.json` z `fx-cond/2` już jest na branchu `fx`): próg każdej pary dobierany na puli wszystkich instrumentów (świece po rozgrzewce, bez uśrednionych) tak, żeby okoliczność była prawdziwa na 15%, 25% albo 40% świec puli (cel kandydata), a każda z dwóch okoliczności pary — w przedziale 10–50% puli; próg zaokrąglony. Szczegóły: 4c.3. Zapis w `fx/conditions.json`: katalog, progi, data kalibracji, zakres danych (każdy instrument: liczba świec, od–do), częstość każdej okoliczności w puli oraz najniższa i najwyższa częstość na pojedynczym instrumencie (`covInstMin`, `covInstMax` — tylko informacja).
- **Katalog jest nienaruszalny** (zasada 14): po kalibracji ID, definicje i progi nigdy się nie zmieniają, okoliczności nie są dodawane ani usuwane — dzięki temu ratingi kolejnych przeliczeń (na większej ilości danych) są porównywalne. Każde przeliczenie liczy częstość w puli; okoliczność poza 10–50% dostaje znacznik „częstość poza zakresem” i nic więcej. Nowy katalog — tylko jako `fx-cond/3`, za zgodą człowieka.
- **`fx-cond/1`** (EURUSD 5 min, skalibrowany 9.10.2026, przeliczenia R-001…) zostaje tylko w archiwum brancha `fx` (`fx/archive/fx-cond-1-5m/`, 4c.12) — kod 1.27 go nie liczy (dane 5 min usunięte).

#### 4c.3 Rodziny okoliczności i wskaźniki (`ia4/fx/catalog.py`, `ia4/fx/series.py`)

**Zasady wspólne:**
- Okoliczność = **cecha f** (liczba na świecy `t`, tylko ze świec ≤ `t`) i warunek **f ≥ próg**. Cecha jest zbudowana tak, że duża wartość = wzrost / wysoka cena. Okoliczność `+` liczy f na serii zwykłej, jej para `−` — tę samą f na **serii odbitej** (`o' = −o`, `c' = −c`, `h' = −l`, `l' = −h`), z tym samym progiem. Wszystkie wielkości są różnicowe i bezwymiarowe, więc odbicie jest dokładne: np. SMA(−c) = −SMA(c), RSI(−c) = 100 − RSI(c), maksimum ↔ minimum.
- Wartość niepoliczalna (NaN) → warunek fałszywy. Wskaźniki na całej serii instrumentu od pierwszej świecy.
- **U** = ATR(100) Wildera (8.2) — jednostka zmienności; „[ATR100]” w opisie = wartość podzielona przez U.
- **Średnie** (MA): SMA, EMA, WMA, HMA, DEMA, TEMA, KAMA, ZLEMA — wzory 8.2; okresy (`PER`) 9, 20, 24, 50, 100, 120, 200 (24 = doba, 120 = tydzień rynku walutowego).
- **Rozgrzewka** = pierwsze 1000 świec serii każdego instrumentu (ok. 6 tygodni): nie są wystąpieniami i nie liczą się do częstości (najdłuższe wskaźniki: TEMA200 — 600 świec, ekstremum z 480 świec).
- Częstość = udział świec spełniających warunek wśród świec puli po rozgrzewce, bez uśrednionych.
- Opis każdej okoliczności po polsku generuje kod; strona `−` opisuje tę samą wielkość „≤ −próg” (albo minimum zamiast maksimum, czerwone zamiast zielonych).
- **Pary średnich:** mieszane (`X_PAIRS`): EMA9–EMA24, EMA24–EMA50, SMA24–SMA50, EMA38–KAMA103, SMA50–SMA200, HMA24–EMA50, DEMA24–SMA100, EMA100–EMA200, WMA9–SMA38, KAMA20–KAMA100; tego samego typu (`MA_PAIRS`): każda MA × okresy (9,24), (9,50), (20,50), (24,100), (50,100), (50,200), (100,200), (24,120).

**Rodziny** (kolejność, nazwa, limit par, cechy):

| # | Rodzina | Limit | Cechy f (rodzaj: wzór; parametry) |
|---|---|---|---|
| 1 | Zmiana ceny (ATR100) | 35 | `chg_u`: (c[t] − c[t−n]) / U; n = 1, 2, 3, 4, 6, 8, 12, 16, 24, 36, 48, 72, 96, 120, 240 |
| 2 | Kierunkowość ruchu i korpusów | 20 | `er_signed`: (c[t] − c[t−n]) / Σ\|Δc\| z n świec (0, gdy mianownik 0); n = 6, 9, 12, 18, 24, 36, 48, 72, 96, 120, 240 · `body_er`: Σ(c−o) / Σ\|c−o\| z n świec; n = 6, 12, 24, 48, 96 |
| 3 | Kolory świec | 25 | `green_cnt`: liczba świec z c > o wśród ostatnich n; n = 4, 6, 8, 10, 12, 16, 24, 36, 48, 72, 100, 120 |
| 4 | Serie świec i położenie zamknięcia | 15 | `streak_green`: długość bieżącej serii świec c > o · `hhhl_streak`: seria świec z h > h[t−1] i l > l[t−1] · `clv`: średnia z n świec ((c−l) − (h−c)) / (h−l) (0, gdy h = l); n = 1, 3, 6, 12, 24, 48 |
| 5 | Cena a średnia krocząca | 50 | `px_vs_ma`: (c − MA_n) / U; każda MA × każdy okres `PER` |
| 6 | Nachylenie średniej | 40 | `ma_slope`: (MA_n[t] − MA_n[t−k]) / U; k = 3, 12; każda MA × każdy okres `PER` |
| 7 | Rozstaw dwóch średnich | 50 | `ma_spread`: (MA1 − MA2) / U; pary mieszane i pary tego samego typu (wyżej) |
| 8 | Przecięcia średnich i ceny | 40 | `ma_cross`: −(świec od przecięcia MA1 w górę przez MA2), tylko gdy MA1 > MA2 (inaczej NaN); pary mieszane; wariant „pod prąd”: liczą się tylko przecięcia, gdy MA2 spadała (MA2[t] − MA2[t−6] < 0) · `px_cross`: −(świec od przecięcia ceny w górę przez MA), tylko gdy c > MA; EMA24, SMA50, KAMA100, EMA200, SMA120, HMA50, DEMA100, TEMA200, ZLEMA38 |
| 9 | Dynamika rozstawu średnich | 40 | `spread_pattern`: d = MA1 − MA2 > 0; seria = kolejne świece, na których d rośnie (albo maleje); zmiana 0 przerywa serię. „fade”: długość bieżącej serii spadków d, gdy poprzedzała ją seria wzrostów ≥ j; „grow”: odwrotnie; j = 2, 3, 5; pary mieszane + EMA, SMA, KAMA × (9,50), (24,100), (50,200) |
| 10 | Położenie w zakresie (stochastic) | 30 | `stoch`: (c − LL_n) / (HH_n − LL_n) − 0,5, HH/LL = maksimum h / minimum l z n świec (0, gdy zakres 0); n = 12, 18, 24, 36, 48, 72, 120, 240 · `stoch_sm`: średnia z s wartości `stoch`; (n, s) = (24,3), (48,6), (120,12), (240,24) |
| 11 | Wybicia i odległość od ekstremum | 25 | `breakout`: −(świec od ostatniego c > HH_n poprzednich n świec); n = 12, 24, 36, 48, 72, 120, 240, 480 · `dist_high`: −(HH_n − c) / U; n = 12, 24, 48, 120, 240, 480 |
| 12 | RSI | 25 | `rsi`: RSI_n − 50 (Wilder, 8.2); n = 5, 7, 9, 14, 21, 30, 50, 100 · `rsi_slope`: RSI_n[t] − RSI_n[t−k]; (n, k) = (14,3), (14,6), (14,12), (7,3), (7,6), (30,6), (30,12) |
| 13 | Odchylenie od średniej (Bollinger) | 25 | `boll_z`: (c − SMA_n) / σ_n, σ = odchylenie standardowe populacji c z n świec (0, gdy σ = 0); n = 10, 12, 20, 24, 30, 50, 75, 100, 120, 200 · `z_slope`: z[t] − z[t−k]; (n, k) = (20,3), (20,6), (50,6), (50,12), (100,12) |
| 14 | MACD | 25 | linia = EMA_f − EMA_s, sygnał = EMA_g(linia), histogram = linia − sygnał; `macd` część „hist”: histogram / U, „line”: linia / U, „hist_slope”: (hist[t] − hist[t−3]) / U; (f, s, g) = (12,26,9), (6,13,5), (24,52,18), (48,104,36), (5,35,5) |
| 15 | Knoty świec | 15 | `wick`: Σ(dolny knot − górny knot) z n świec / (n · U); dolny = min(o,c) − l, górny = h − max(o,c); n = 1, 3, 6, 12, 24, 48 |
| 16 | Doba, tydzień, poprzednia doba | 15 | segment: doba UTC, doba handlowa (od 17:00 Nowy Jork), tydzień handlowy (od niedzieli 17:00 Nowy Jork) · `sess_chg_u`: (c − otwarcie pierwszej świecy segmentu) / U · `day_pos`: (c − min l) / (max h − min l) − 0,5 od początku segmentu · `prev_day`: (c − zamknięcie / maksimum / minimum poprzedniej doby handlowej) / U |
| 17 | Trend i korekta | 25 | trend: c > MA (EMA200, SMA120, KAMA100, EMA100), inaczej NaN · `combo_dip`: (MA_k − c) / U tylko gdy c < MA_k (MA_k = EMA24, EMA9, SMA50, EMA50) · `combo_pull`: −(c[t] − c[t−m]) / U, m = 3, 6, 12 · `combo_rsi`: 50 − RSI14 · `combo_stoch`: −`stoch`(24); cele częstości 15% i 12% |

**Kalibracja** (`python -m ia4.fx.catalog --commit`, raz):
1. Kandydaci w stałej kolejności: rodziny 1→17; w rodzinie najpierw wszystkie cechy z celem częstości 25%, potem 15%, potem 40% (rodzina 17: 15%, potem 12%).
2. Próg kandydata: wartości f ze strony `+` i `−` wszystkich instrumentów razem (po rozgrzewce, bez uśrednionych), próg = wartość, powyżej której leży udział równy celowi; zaokrąglenie do 2 cyfr znaczących, a dla cech całkowitych (liczby świec) — do liczby całkowitej dającej udział najbliższy celowi. Kandydat przepada, gdy którakolwiek strona wypada w puli poza 10–50%, **gdy na którymkolwiek pojedynczym instrumencie którakolwiek strona jest prawdziwa na mniej niż 1% albo więcej niż 80% jego świec** (od 1.30: taka cecha rozpoznaje instrument — sposób, w jaki Yahoo buduje świece danej pary — a nie sytuację rynkową; w kalibracji próbnej 11.10.2026 dotyczyło to 12 par z rodzin „Knoty świec” i „Serie świec i położenie zamknięcia”, np. 0,1% / 97,9%) albo ten sam warunek (rodzaj, parametry, próg) już był.
3. Wybór: kandydaci po kolei, w granicach limitu rodziny, jeśli korelacja (phi, na co 3. świecy puli) ze stroną `+` każdej już wybranej okoliczności ≤ 0,85; potem drugi przebieg z progiem 0,95. Gdy par jest mniej niż 500, brakujące miejsca dostają kolejne rodziny po jednym kandydacie (0,85 → 0,95 → bez progu).
4. ID w kolejności rodzin, a w rodzinie — kolejności wyboru; para = `FX-(2i−1)` `+` i `FX-(2i)` `−`.
5. Zapis `fx/conditions.json` (4c.12) — każda okoliczność: ID, para, kierunek, rodzina, rodzaj, parametry, próg, cel, częstość przy kalibracji (pula, min. i maks. na instrumencie), opis. Przed zapisem pliki `fx-cond/1` przenoszone do archiwum (4c.12).

Kalibracja próbna (`python -m ia4.fx.catalog`, bez `--commit`) robi to samo, ale zapisuje tylko lokalny podgląd `data/fx1h/catalog-preview.csv` (otwiera się w Numbers/Excel; kolumny częstości na każdym instrumencie) i nic nie wysyła. Czas: ok. 15 s, pamięć ok. 0,7 GB. Test na danych syntetycznych: `python -m ia4.fx.selftest` — lustro, brak zaglądania w przyszłość, 1000 okoliczności w 10–50%, powtarzalność, synchronizacja, godziny rynku; wynik musi brzmieć „WYNIK: OK”.

#### 4c.4 Wystąpienia i profil

- **Wystąpienie** okoliczności = każda świeca `t` instrumentu po rozgrzewce (4c.3), na której okoliczność jest prawdziwa, jeśli świeca `t` nie jest uśredniona i w oknie `t … t+48` (świece serii) nie ma przerwy (4c.1).
- Dla wystąpienia zapisujemy zmiany ceny **w jednostkach zmienności**: `r_k = (c[t+k] − c[t]) / ATR100[t]`, k = 1…48 (świece serii — dla par walutowych przez weekend). Zmiany nie ma, gdy świeca `t+k` jeszcze nie istnieje (koniec danych) albo jest uśredniona. Zmiana w cenie = `r_k × ATR100[t]`.
- **Profil** okoliczności = dla każdego k średnia `r_k` ze wszystkich wystąpień wszystkich instrumentów, które ją mają (48 liczb, ATR100), oraz liczba wystąpień.
- **Niezależne wystąpienia** `n_ind` = w każdym instrumencie wystąpienia wybierane od najstarszego tak, że każde kolejne jest co najmniej 48 świec po poprzednim wybranym; suma po instrumentach.
- Lokalnie (poza gitem): `data/fx1h/occurrences.npz` — macierz okoliczności × świece puli (bity), instrument, czas, zamknięcie, ATR100 i zmiany `R[t, k]` każdej świecy (ta sama informacja co „ID → wystąpienie → 48 zmian”, bez powielania liczb); przepisywany przy każdym przeliczeniu. W kodzie: `from ia4.fx.research import load_occurrences; load_occurrences("FX-0001", "EURUSD")` — tabela: instrument, czas wystąpienia, zamknięcie, ATR100, `k1…k48` (bez instrumentu — wszystkie). Na GitHub trafiają tylko profile.

#### 4c.5 Rating 1–100

Rating mówi, o ile profil okoliczności przewidywał przyszłość lepiej niż prognoza „cena się nie zmieni”, **sprawdzone poza próbą metodą walk-forward** (kolejne okresy oceniane profilem policzonym wyłącznie z przeszłości):

1. **Kalendarz** (od najstarszej do najnowszej świecy puli) dzielony na **5 równych części** — wspólnych dla wszystkich instrumentów (pary walutowe poruszają się razem; podział po indeksie świec przeciekałby przyszłość z jednej pary do drugiej). Wystąpienie należy do części swojej świecy `t`.
2. Dla każdej części j = 2…5: **profil uczący** `P_k` = profil z wystąpień, których okno kończy się przed początkiem części j (świeca `t + 48` przed początkiem); część z mniej niż 30 takimi wystąpieniami jest pomijana.
3. Dla każdego wystąpienia części j i każdego k, dla którego świeca `t + k` leży jeszcze w części j: błąd okoliczności `|r_k − P_k|`, błąd „bez zmiany” `|r_k|`.
4. **Przewaga** `S = 1 − Σ błąd okoliczności / Σ błąd „bez zmiany”` — sumy po wszystkich ocenianych częściach, wystąpieniach i k.
5. Ściągnięcie przy małej liczbie danych: `S* = S · n / (n + 20)`, gdzie n = suma `n_ind` ocenianych części.
6. **Rating** = 1, gdy `S* ≤ 0` albo n < 5; w pozostałych przypadkach `1 + round(99 · min(S* / RATING_FULL; 1))`, `RATING_FULL` = 0,05 (błąd o 5% mniejszy niż „bez zmiany” daje 100). Skala jest stała, więc ratingi z różnych przeliczeń można porównywać.

Dlaczego walk-forward, a nie jeden podział 70/30: ocena obejmuje 80% danych zamiast 30%. Na czystym szumie daje mniej przypadkowych ratingów, a zasiany sygnał wykrywa tak samo (selftest).

**Profil publikowany** (do prognozy na żywo) = profil ze wszystkich wystąpień całej historii.

#### 4c.6 Prognoza rozkładu (`ia4/fx/scenario.py`)

Na ostatniej zamkniętej świecy `t` każdego instrumentu (ten sam kod w FX-research i FX-real-time):

1. **Pula** — świece-kandydaci `a` z historii: mogą być wystąpieniem (4c.4), mają zmianę po 48 świecach, ich okno 48 świec kończy się przed `t` (w kalendarzu), policzalna zmienność.
2. **Dobór K = 80 momentów** jedną z metod (wybiera ją sprawdzian, 4c.7):
   - `pora` — ten sam instrument, ta sama godzina UTC ±1 h co `t`, najnowsze momenty,
   - `analogi` — wszystkie instrumenty tej samej grupy (10 par walutowych razem, BTC osobno), ta sama godzina UTC ±1 h, momenty najbardziej podobne pod względem okoliczności prawdziwych: Jaccard ważony ratingiem, `Σ rating (wspólne) / Σ rating (suma zbiorów)`; przy remisie nowsze.
   Wybrane momenty są od siebie oddalone o ≥ 12 h w kalendarzu — także między instrumentami (EURUSD i GBPUSD o tej samej godzinie to prawie ta sama informacja).
3. **Ścieżki** — 48 zmian `r_k` każdego momentu (ATR100, 4c.4) przeskalowane do dzisiejszego reżimu zmienności: `× √(ρ[t] / ρ[a])`, ρ = ATR12 / ATR100 (ATR Wildera, 8.2), mnożnik ograniczony do 1/3…3.
4. **Środek** = `λ × (średnia profili okoliczności prawdziwych na t ważona ratingiem)`: dla k = 1…48 `Σ(rating_i · profil_i[k]) / Σ rating_i` po okolicznościach prawdziwych, które mają `profil_i[k]`. λ ustala sprawdzian; λ = 0 → środek płaski na cenie bieżącej.
5. **Ścieżki*** = `środek + f × (ścieżka − mediana ścieżek)` — kształt i rozrzut z historii, położenie ze środka, szerokość skalibrowana `f` (4c.7).
6. Z 80 ścieżek*: **stożek** = kwantyle 10%, 25%, 75%, 90% dla każdego k; **P(wzrost)** k = 12 i 48 = udział ścieżek* powyżej ceny bieżącej (z liczbą: „w 80 podobnych chwilach wzrost: N”); **oczekiwany zakres 48 h** = mediana (maks. − min.) ścieżek* od ceny bieżącej, z typowym maksimum i minimum; **3 scenariusze** = ścieżki* najbliższe 20., 50. i 80. percentyla zmiany po 48 świecach (spadkowy, boczny, wzrostowy), każda z datą i instrumentem historycznego momentu (świeca uśredniona w środku ścieżki — interpolacja między sąsiadami).
7. Ceny = cena bieżąca + `ATR100[t] ×` wartość. Czasy 48 świec prognozy — kolejne świece w godzinach rynku (pary walutowe: weekend pomijany, jak w danych; BTC: kolejne godziny).

#### 4c.7 Sprawdzian prognozy rozkładu

Każde przeliczenie FX-research sprawdza prognozę bez zaglądania w przyszłość (walk-forward, po kalendarzu):
- **Zapytania**: świece-kandydaci wszystkich instrumentów z ostatnich 30% kalendarza, co n-ta (najwyżej 2000). Ścieżki dla zapytania `t` tylko z momentów, których okno kończy się przed `t`. Ratingi i profile do środka i do podobieństwa — wyłącznie z okien kończących się przed granicą 70% (4c.5).
- **Metody**: `analogi`, `pora` i punkt odniesienia `całość` (ten sam instrument, dowolna godzina, najnowsze momenty).
- **Część A** (70–85% kalendarza) — kalibracja: λ ∈ {0; 0,25; …; 3} minimalizujące Σ|r_k − λ·średnia profili|, potem f ∈ {0,70; 0,75; …; 2,00} tak, żeby przedział 10–90% obejmował 80% wyników (k = 12 i 48).
- **Część B** (85–100%) — ocena z λ i f z części A: pinball (średnia straty kwantylowej dla 10/25/50/75/90%) k = 12 i 48, pokrycie przedziału 80% (k = 12, 48) i 50% (k = 48), Brier P(wzrost) k = 12 i 48 (0,25 = rzut monetą), błąd prognozy zakresu 48 h (mediana |prognoza − wynik| / wynik), przewaga środka nad „bez zmiany” (`centerS`); dodatkowo dla każdego instrumentu osobno: pokrycie 80% k = 48, Brier k = 48, błąd zakresu (`inst`).
- **Model na żywo**: metoda (`analogi` albo `pora`) z niższą sumą pinball k = 12 + 48 w części B (remis → `pora`); f i λ na żywo dopasowane na A + B, ale **λ = 0, gdy środek w części B nie był co najmniej o 1% lepszy niż „bez zmiany”** (`centerS < 0,01`, zasada 15); wtedy część B jest oceniana jeszcze raz z λ = 0 (tak, jak pójdzie na żywo).
- **Werdykt słowny**: kierunek — „przewaga nad rzutem monetą”, gdy Brier k = 12 albo 48 < 0,245, inaczej „brak przewagi (jak rzut monetą)”; stożek — „trafny” przy pokryciu 80% w 75–85%, inaczej „za wąski” / „za szeroki”.
- Test (`selftest`): czysty szum → λ = 0, Brier k = 48 ≥ 0,245, pokrycie 80% w 72–88%; zasiany sygnał → λ ≥ 0,5, Brier k = 48 < 0,24, środek z przewagą > 1%.
- Czas: ok. 2–3 min na 11 instrumentów × 2 lata (test pełnej skali na danych syntetycznych: 142 000 świec — 136 s).

#### 4c.8 FX-research — `python -m ia4.fx.research`

Tylko ręcznie. Kolejno: synchronizacja (4c.1) → klon brancha `fx` w `ia4-research/fx-repo/` → katalog `fx-cond/2` z `fx/conditions.json` (bez niego program kończy się komunikatem — najpierw kalibracja, 4c.2) → pula, wszystkie wystąpienia i profile od zera (4c.4) → ratingi (4c.5) → sprawdzian prognozy rozkładu i wybór modelu na żywo (4c.7) → prognoza z ostatniej świecy każdego instrumentu → zapis i push na branch `fx`: `fx/ratings.json` (jedna okoliczność = jedna linia; w nagłówku: dane każdego instrumentu, `scenario` — wyniki wszystkich metod, model na żywo z f i λ, `lastCandle` — prognoza z ostatniej świecy każdego instrumentu), dopisany wiersz `fx/runs.jsonl`. Lokalnie: `data/fx1h/occurrences.npz` (4c.4) i podgląd `data/fx1h/ratings-preview.csv` (rating, wystąpienia, przewaga, częstość w puli i na instrumentach, profil dla k = 12 i 48 — do obejrzenia przed arkuszem OKOLICZNOSCI_FX). Każde przeliczenie na świecach 1h ma ID `H-001`, `H-002`, … (`R-…` — archiwum 5 min). Opcje: `--no-sync`, `--no-push`. Konsola: dane każdego instrumentu, rozkład ratingów, najwyższe ratingi, tabela sprawdzianu (metoda × pinball, pokrycie, Brier, błąd zakresu, λ), wyniki części B na każdym instrumencie, model na żywo z werdyktem, prognoza z ostatniej świecy. Czas: ok. 3 min, pamięć do ok. 3 GB.

#### 4c.9 FX-real-time — `python -m ia4.fx.live`

- **Start:** `caffeinate` (Mac nie zaśnie, dopóki program działa), klon brancha `fx` i katalog, ratingi, profile i model na żywo (metoda, f, λ — 4c.7) z `fx-repo/fx/` (bez `fx-cond/2` albo bez `ratings.json` ze sprawdzianem rozkładu program się nie uruchamia — najpierw kalibracja i FX-research), synchronizacja (4c.1), prognoza na ostatniej świecy każdego instrumentu, publikacja.
- **Pętla co 30 s:**
  - na świecę instrumentu czekamy dopiero od jej zamknięcia + 60 s (Fx.gs zapisuje zwykle 20–180 s po zamknięciu); pary walutowe poza godzinami rynku (4b) nie mają czego szukać — przy zamkniętym rynku program pyta tylko o BTC (raz na godzinę),
  - gdy któryś instrument czeka: 1 odczyt `system/fx1h`; instrumenty z nowszą świecą — odczyt ich dokumentów dni (zwykle 1, przy zmianie doby UTC 2), nowe świece do kopii lokalnej, prognoza rozkładu wszystkich instrumentów (4c.6, ten sam kod co FX-research; ok. 4 s), publikacja; instrumenty nadal bez świecy — kolejna próba za 30 s, a po 15 min spóźnienia co 5 min,
  - co 2 min sygnał życia (`aliveAt`) — także bez nowej świecy i przy zamkniętym rynku,
  - gdy `fx-repo/fx/ratings.json` się zmienił (nowe przeliczenie FX-research w trakcie pracy) — przy następnej świecy program bierze nowe ratingi,
  - błąd sieci albo Firestore nie zatrzymuje programu — próba w kolejnym obrocie.
- **Ctrl+C:** ostatnia publikacja z `stoppedAt` — strona IA4 (zakładka FX) pokazuje „program zatrzymany”.
- **Publikacja:** `forecast.json` na branchu `fx-live` — zawsze jeden commit bez historii (force push), klon w `ia4-research/fx-live-repo/`; plik bez NaN (wartości niepoliczalne → `null`). Zawartość: `version`, `interval` ("1h"), `horizon` (48), `aliveAt`, `generatedAt`, `stoppedAt` (po Ctrl+C), `ratings` (ID przeliczenia, data), `model` (metoda, f, λ, K, okno godzin, odstęp), `check` (wyniki części B: pokrycie 80% k = 12/48, pokrycie 50%, Brier k = 12/48, błąd zakresu, pinball k = 48, `centerS`), `verdict` (kierunek, stożek — słowami), `firestoreReadsToday` i `instruments` — dla każdego: `id`, `name`, `group`, `pip`, `digits`, `lastCandle`, `lastClose`, `atr100`, `marketOpen`, `candles` (ostatnie 48 świec: początek, o, h, l, c), `times` (początki 48 świec prognozy), `check` (część B tego instrumentu), `K`, `center`, `q10`, `q25`, `q75`, `q90` (ceny), `pUp` i `upCount` (k = 12, 48), `range` (typowe maksimum, minimum, zakres w cenie), `scenarios` (3 × nazwa, data i instrument historycznego momentu, ścieżka cen), `forecastPips` (środek k = 12, 48 w pipsach), liczba okoliczności prawdziwych, suma ich ratingów i 5 z nich o najwyższym ratingu.
- **Firestore:** ok. 1 + (liczba instrumentów z nową świecą) odczytów na godzinę — ok. 12 / godzinę, ok. 290 / pełny dzień roboczy, w weekend ok. 50 (sam BTC) (symulacja w `selftest`).
- **GitHub:** ok. 31 publikacji na godzinę (sygnał życia + świece) — wszystkie na `fx-live`, nie wpływają na stronę.

#### 4c.10 Prognoza na stronie IA4 (zakładka FX)

Od 1.28 prognozę pokazuje zakładka **FX** strony IA4 (sekcja 11b) — dawny osobny dashboard z brancha `fx` (`ia4-research/ia4/fx/dashboard/`, 1.25–1.27) został usunięty, a FX-research i FX-real-time już nic nie kopiują na branch `fx`. Zawartość zakładki: sekcja 11b. Zasady prezentacji bez zmian: rozkład, nie jedna linia (4c.0, zasada 15), kolor kierunku tylko przy udowodnionej przewadze, wynik sprawdzianu słowami, wyblakła prognoza, gdy Mac nie jest połączony.

#### 4c.11 Arkusz OKOLICZNOSCI_FX (`Fx.gs`)

- Wypełnia go Apps Script (`Fx.gs`) w triggerze `researchSync` (co 30 min) i z menu IA 4 → „💱 FX — odśwież OKOLICZNOSCI_FX teraz”. Co 30 min jedno małe zapytanie o ostatni commit brancha `fx`; `fx/conditions.json` i `fx/runs.jsonl` (token `GITHUB_TOKEN`) są pobierane, a arkusz przebudowany w całości tylko wtedy, gdy commit się zmienił albo arkusz ma inny układ (znacznik w G1 inny niż `okol-3`). Stan: Script Properties `FX_RUNS` (commit, liczba przeliczeń).
- **Układ:** wiersz 1 — opis katalogu (`fx-cond/2`, świece 1h, liczba instrumentów) i znacznik `okol-3` (G1); wiersze 2–8 — nagłówki przeliczeń (etykiety w kolumnie G): ID przeliczenia, data (PL), liczba świec (wszystkich instrumentów), model na żywo (metoda i λ środka), trafność stożka 80% (cel 80%), Brier k = 48 (0,25 = moneta), błąd prognozy zakresu 48 h — wszystko z części B sprawdzianu (4c.7); wiersz 9 — nagłówki kolumn; od wiersza 10 — okoliczności w kolejności ID (1000 wierszy).
- **Kolumny A–G:** ID, rodzina, kierunek, para, opis, próg, częstość przy kalibracji % (pula).
- **Kolumny od H:** jedno przeliczenie FX-research = jedna kolumna (najstarsze z lewej). Komórka `rating/wystąpienia` jako tekst, np. `41/3440` (wystąpienia z całej historii wszystkich instrumentów); okoliczność z częstością poza 10–50% w tym przeliczeniu — komórka szara.
- Arkusz tylko do odczytu — ręczne zmiany znikają przy następnym przebudowaniu. Przy pierwszym przeliczeniu `H-001` arkusz buduje się od nowa (nowy katalog i znacznik `okol-3`); kolumny `R-…` z 5 min nie wracają.

#### 4c.12 Branche `fx` i `fx-live`

Pisze je wyłącznie Python z Maca.

```
fx (FX-research):
  index.html, .nojekyll   dawny dashboard (1.25–1.27) — od 1.28 nieużywany (strona IA4: main/docs, 11b)
  fx/README.md
  fx/conditions.json  katalog fx-cond/2 z progami — zapisuje go raz `python -m ia4.fx.catalog --commit`, nienaruszalny
  fx/ratings.json     ostatnie przeliczenie: dla każdej okoliczności rating, wystąpienia, n_ind, S, częstość
                      (pula, min./maks. na instrumencie), znacznik, profil (48, ATR100); w nagłówku dane instrumentów,
                      `scenario` — sprawdzian rozkładu i model na żywo (4c.7), `lastCandle`
  fx/runs.jsonl       wiersz na każde przeliczenie (H-001, …): ID, czas, wersja, zakres danych, liczba świec i instrumentów,
                      `scenario` (model, f, λ, pokrycie 80%, Brier k=48, błąd zakresu, pinball k=48 metod),
                      rating / wystąpienia / częstość każdej okoliczności
  fx/archive/fx-cond-1-5m/   conditions.json, ratings.json, runs.jsonl katalogu fx-cond/1 (EURUSD 5 min, 1.21–1.26) —
                      przeniesione przy kalibracji fx-cond/2, tylko do wglądu

fx-live (FX-real-time, zawsze jeden commit, force push):
  forecast.json       stan na żywo (4c.9) — czyta go strona IA4 (zakładka FX)
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
- 3.3 VIRTUAL-INVESTOR otwiera i zamyka transakcje dla strategii zaznaczonych „for VI” w arkuszu STRATEGIE,
- 3.4 (od 1.28) `telemetry/vi.json` jest aktualizowany po każdej świecy, a zakładka Inwestor strony IA4 pokazuje pozycje i transakcje.

Stan 11.10.2026: działa od 6.10.2026 (`state.json` → `vi`: 11 zamkniętych, 19 otwartych). Wynik oceniamy po medianie i przedziale 95% średniego wyniku transakcji, nie po dniach (PRZEWODNIK, sekcja 4).

### Etap 4 — Prognoza FX 🟨

Prognoza 48 świec 1h dla 10 par walutowych i BTC/USD (sekcje 4b i 4c). Kolejne kroki — każdy zamyka się zgodą człowieka:
- **FX-0 … FX-6** (1.20–1.26) — prognoza EURUSD na świecach 5 min: instrukcja, synchronizacja, katalog `fx-cond/1` (skalibrowany 9.10.2026), FX-research (przeliczenia R-…), arkusz OKOLICZNOSCI_FX, FX-real-time i dashboard, prognoza rozkładu (scenariusze, stożek, sprawdzian). Zamknięte; dane 5 min usunięte w 1.27, wyniki w archiwum brancha `fx`.
- **FX-7** — przejście na świece 1h i 11 instrumentów (1.27): `Fx.gs` zbiera `fx1h` (historia 728 dni, na żywo, kontrola dni, arkusz FX z kolumną na instrument), kopia `data/fx1h/`, katalog `fx-cond/2` (cechy bezwymiarowe, kalibracja na puli), pula instrumentów w FX-research (zmiany w ATR100, części walk-forward po kalendarzu, analogi w grupie), prognoza i dashboard dla wszystkich instrumentów (zakładki), nagłówki OKOLICZNOSCI_FX (`okol-3`) — kod gotowy w 1.27. Kolejność: (1) pliki `.gs` w Apps Script — historia pobiera się sama w kilkanaście minut (STATS „FX 1h — dziś / historia” = 11/11); (2) menu „🗑 FX — usuń stare świece EURUSD 5 min”; (3) Mac: `python -m ia4.fx.selftest`, `python -m ia4.fx.sync`, kalibracja próbna `python -m ia4.fx.catalog` (przegląd `catalog-preview.csv` z Claude), potem `--commit`; (4) `python -m ia4.fx.research` → `H-001`; (5) `python -m ia4.fx.live`. Zamknięty, gdy `fx/conditions.json` z `fx-cond/2` i przeliczenie `H-001` są na branchu `fx`, arkusz OKOLICZNOSCI_FX ma kolumnę H-001, a strona IA4 (zakładka FX) pokazuje stożek każdego instrumentu i „Mac połączony”.

- **FX-8** ⬜ — strategie FX i wirtualny inwestor FX: tylko gdy FX-research pokaże udowodnioną przewagę (sprawdzian 4c.7: Brier < 0,245 na kilku przeliczeniach z rzędu). Wtedy Claude proponuje osobną sekcję instrukcji: język reguł FX, symulację, plik `telemetry/fx-vi.json` w formacie `vi.json` (strona ma na niego gotowe miejsce, 11b). Nic z tego nie powstaje bez zgody człowieka.

Wdrożony, gdy: arkusz FX ma kompletne dni wszystkich 11 instrumentów, `fx/conditions.json` (`fx-cond/2`) jest na branchu `fx` (1000 okoliczności, każda w 10–50% puli przy kalibracji), FX-research zapisało przeliczenie ze sprawdzianem rozkładu, arkusz OKOLICZNOSCI_FX ma jego kolumnę z modelem na żywo, a strona IA4 (zakładka FX) pokazuje stożek, scenariusze i status Maca.

### Etap 5 — Strona IA4 🟨

Konsola systemu na GitHub Pages (sekcja 11b), rozwijana zakładka po zakładce na prośbę człowieka. Wdrożony, gdy: Pages pokazuje `main` / `/docs`, bramka hasła działa, zakładka System pokazuje zielone ogniwa Apps Script i GitHub, zakładka Inwestor — pozycje z `vi.json`, zakładka FX — stożek z `forecast.json`. Kolejne zakładki i źródła: `docs/README.md`; każdy nowy plik danych dla strony — najpierw zmiana instrukcji i zgoda (zasada 6).

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
- Po każdym przeliczeniu: wyniki każdej strategii (`VI_BY_STRAT` → STRATEGIE), podsumowanie (`VI_SUMMARY` → telemetria, pole `vi`), pełny stan dla strony — `telemetry/vi.json` (pozycje, transakcje, krzywa, strategie, sygnały ostatnich 35 świec z `sigLog`; format: 11b) i od razu `telemetry/state.json`. Strona IA4, zakładka Inwestor, pokazuje to samo co VIRTUAL-INVESTOR.
- Wynik % jak w 8.6 p. 6 minus koszt: 2 × `COST_PCT` (0,005% przy wejściu i 0,005% przy wyjściu) — dla pozycji otwartych od wersji 1.15 (starsze bez kosztu); wynik $ = 100 $ × wynik %. Pozycje otwarte pokazują wynik netto (po obu kosztach).

**Test zgodności** (po każdej zmianie sekcji 8, `PaperEngine.gs` albo `ia4/lab`):
```bash
cd ia4-research && python tests/parity_dump.py /tmp/ia4_parity.json && node tests/parity.js /tmp/ia4_parity.json
```
Wynik musi brzmieć „rozbieżności: sygnały 0, transakcje 0”.

---

## 11b. Strona IA4 — konsola systemu (`docs/`)

Jedna strona dla człowieka, którą można rozwijać zakładka po zakładce: **czy system żyje, co przyszło, co policzono**. Tylko czyta pliki z publicznego repo — niczego nie zapisuje, nie dotyka Firestore ani arkuszy.

- **Adres:** `https://miszyszka.github.io/IA4/` — GitHub Pages z brancha `main`, folder `/docs` (jednorazowo: GitHub → Settings → Pages → Source: Deploy from a branch → `main`, `/docs`). Każdy push na `main` publikuje stronę w ok. minutę.
- **Kod:** zwykłe pliki bez buildu i bez zewnętrznych bibliotek (moduły ES): `index.html`, `css/ia4.css`, `css/fonts.css` + `fonts/` (Chakra Petch, IBM Plex Mono — licencja OFL, hostowane w repo), `js/core.js` (źródła, odświeżanie, formaty, godziny rynków, bramka), `js/health.js` (stan ogniw), `js/chart.js` (wykresy SVG), `js/main.js` (zakładki, zegary, magistrala), `js/views/*.js` (po pliku na zakładkę). Jak dodać zakładkę albo źródło: `docs/README.md`.
- **Hasło:** bramka w przeglądarce. W kodzie tylko skrót PBKDF2-SHA256 (150 000 iteracji) — samego hasła nie ma w repo ani w tej instrukcji (zna je człowiek); odblokowanie pamiętane w przeglądarce 30 dni, przycisk „wyloguj”. **Bramka nie chroni danych**: wszystkie pliki, które czyta strona, są w publicznym repo (zasada 5 — żadnych sekretów w danych strony).
- **Źródła** (odświeżane tylko przy otwartej karcie): `telemetry/state.json` i `telemetry/vi.json` (co 60 s), `forecast.json` z `fx-live` (co 30 s, API GitHub z ETag), `research/strategies.jsonl`, `research/status.json`, `fx/runs.jsonl` (co 15 min), lista commitów `main` (co 3 min, API), `telemetry/fx-vi.json` (przyszły inwestor FX; brak pliku = panel „nieaktywny”). Pliki godzinowe — przez `raw.githubusercontent.com` (bez limitu, do ok. 5 min opóźnienia); przy limicie API strona przechodzi na 10 min na raw.
- **Wygląd:** konsola terminala — ciemne tło, panele z tytułem w ramce, fosfor bursztynowy dla interakcji, cyjan dla prognoz, zieleń i czerwień tylko dla kierunku i stanu. Klawisze 1–3 przełączają zakładki, adres zakładki w `#`.
- **Magistrala** (pasek pod nagłówkiem, na każdej zakładce): ogniwa przepływu danych **Yahoo → Apps Script → Firestore → GitHub → Mac (FX-real-time) → ta strona**; każde z lampką (zielona / żółta / czerwona / szara = nie dotyczy teraz), wiekiem ostatniego znaku życia tykającym co sekundę i paskiem „ile z typowego odstępu minęło”; ogniwo z nowym znakiem życia błyska. Znacznik w nagłówku: „system żyje”, gdy Apps Script i GitHub dały znak w ciągu 80 min.
- **Zakładka System:** stan składników (automat, zbieranie akcji i FX, paper trading, telemetria, nocne odświeżenie, FX-real-time, FX-research, poszukiwanie, strona — ostatni znak życia, rytm, szczegóły, odliczanie do następnej świecy); **strumień zdarzeń** (`tail -f`: commity, świece akcji i FX, transakcje i sygnały inwestora, przeliczenia — nowe podświetlone); parametry (wersja — ostrzeżenie, gdy Apps Script ma inną niż strona; czas pracy automatu wobec limitu 90 min; uruchomienia, świece i błędy dziś; świece w bazie; ostatni błąd); spływ ostatniej świecy akcji (kiedy który etap był gotowy, od zamknięcia); siatka wszystkich instrumentów; stan źródeł danych.
- **Zakładka Inwestor:** odczyty (wynik zrealizowany i niezrealizowany $, średni wynik z przedziałem 95%, skuteczność TP i wyjścia, mediana świec, koszty, od kiedy), krzywa wyniku, sygnały z ostatnich świec, otwarte pozycje (z położeniem ceny między SL i TP), strategie (filtry „for VI” / „z wynikiem na żywo” / wszystkie, wyszukiwarka, sortowanie: PF z poszukiwania, $ na żywo, pierwszeństwo), zamknięte transakcje, spółki (pozycje, sygnały, wynik). Zanim pojawi się `vi.json` — samo podsumowanie z `state.json`.
- **Zakładka FX:** stan Maca, rynku, model na żywo, sprawdzian, ratingi; lista 11 instrumentów (mini-wykres 48 świec, zamknięcie, P(wzrost)); wykres wybranego instrumentu z prognozą rozkładu i odczytami (jak dawny dashboard, 4c.10); **spływ świec 1h** — po komórce na świecę z ostatnich 24 godzin rynku, ramka dla świecy, która trwa, migająca ramka dla spóźnionej, godzina i wiek ostatniej świecy, odliczanie do następnej (świece z `state.json` nowsze niż prognoza też są widoczne); scenariusze i okoliczności o najwyższym ratingu; przeliczenia FX-research (`fx/runs.jsonl`); **wirtualny inwestor FX** — miejsce zarezerwowane: gdy powstaną strategie FX, Apps Script będzie wysyłał `telemetry/fx-vi.json` w formacie `vi.json` i panel pokaże go tym samym widokiem co inwestora akcji (format i powstanie pliku — dopiero za zgodą człowieka, nowa wersja instrukcji).
- **Telefon** (szerokość ≤ 760 px): przede wszystkim stan — na zakładce System magistrala w pionie i składniki z wiekiem; na pozostałych magistrala zwinięta do siatki lampek; odczyty po dwa w rzędzie; tabele szczegółowe (strategie, transakcje, siatki, przeliczenia, źródła) ukryte; wykres FX z 24 świecami wstecz.
- **`telemetry/vi.json`** (pisze `Telemetry.gs`, woła go `Paper.gs` po każdym przeliczeniu świecy i po „zacznij od nowa”; commit tylko przy zmianie treści — `VI_HASH`): `version`, `generatedAt`, `lastCandleKey` / `lastCandlePL`, `since`, `capital`, `stake`, `costPct`, `maxPerTicker`, `summary` (closed, open, pending, avgPct, ci95Pct, realizedUsd, unrealizedUsd, tpShare, exits TP/SL/FC/LIMIT, medianBars, costsUsd), `open` (każda pozycja otwarta i oczekująca: nr, strategia, spółka, kierunek, status, sygnał, wejście, SL/TP % i ceny, cena teraz, wynik % i $, świece), `closed` (ostatnie 150, od najnowszej: wejście, wyjście, powód, wynik % i $, świece), `equity` (skumulowany $ po każdej zamkniętej, najwyżej 2000 punktów), `strategies` (aktywne i „for VI”: opis, for VI, pierwszeństwo, zamknięte, otwarte, średni wynik, skuteczność, $), `signals` (ostatnie 35 świec: chwila, klucz, lista [strategia, spółka]). Wszystko pochodzi ze stanu inwestora (11a) — nic nie jest liczone na nowo. Ostatnie sygnały: `sigLog` w stanie inwestora (`_IA4_DANE`). Po świecy `Paper.gs` wysyła też od razu `state.json` (najwyżej raz na 10 min), żeby strona widziała świeżą świecę.

---

## 12. Wdrożenie i uruchamianie

### Apps Script — skład

Pliki: `Code.gs`, `Telemetry.gs`, `Research.gs`, `PaperEngine.gs`, `Paper.gs`, `Fx.gs` (+ manifest `appsscript.json`). Triggery (zakłada je „⚙️ Konfiguruj i włącz automat”): `runCollector` co minutę, `telemetryHourly` co godzinę, `researchSync` co 30 min (STRATEGIE, BACKTEST PORTFELA, OKOLICZNOSCI_FX). Script Properties: `GITHUB_TOKEN` (menu „Ustaw token GitHub”) oraz stan automatu (`LIVE_STATE`, `BACKFILL_DP`, `VI_IDS`, `PAPER_LAST_KEY`, `BT_DP_AT`, `BT_PF_AT`, `CANDLE_LOG`, `FX1H_STATE`, `FX1H_CHECK`, `FX_RUNS`, `ACTIVE_IDS`, `PRIORITY`, `VI_BY_STRAT`, `VI_SUMMARY`, `VI_HASH`, `TELEMETRY_HASH` i inne — nie edytować). Arkusze: STATS, FX, OKOLICZNOSCI_FX (od FX-3), STRATEGIE, BACKTEST PORTFELA, SIGNALS-REALTIME, VIRTUAL-INVESTOR, ukryty `_IA4_DANE`.

### Aktualizacja do nowej wersji

1. Wypchnięcie pakietu `.bundle` (polecenia niżej).
2. Apps Script: podmienić pliki `.gs` zmienione w pakiecie (Claude podaje listę) — najprościej zawsze wszystkie sześć; nowy plik dodać przez „+ → Skrypt” z tą samą nazwą. Zapisać, odświeżyć arkusz.
3. „⚙️ Konfiguruj i włącz automat” — tylko gdy zmieniła się lista instrumentów, układ STATS albo triggery (Claude o tym mówi). Konfiguruj odtwarza STATS, triggery i `system/universe` oraz uzupełnia ostatni miesiąc (ok. 2500 zapisów).
4. Strona IA4 (`docs/`) aktualizuje się sama po pushu — nic do zrobienia.
5. Mac: `cd ~/Desktop/IA4 && git pull`; `pip install -r requirements.txt`, gdy zmieniły się zależności; zatrzymać program (Ctrl+C) i uruchomić ponownie, gdy zmienił się kod Pythona.

### Mac — na co dzień

Przy wstrzymanym poszukiwaniu Mac **nie jest potrzebny na co dzień** — zbieranie, sygnały i wirtualny inwestor działają w Apps Script. Mac tylko do jednorazowych przeliczeń:

```bash
cd ~/Desktop/IA4/ia4-research && source .venv/bin/activate
python -m ia4.lab.backtest_dp --force   # backtest strategii na doubleProof → kolumny doubleProof w STRATEGIE
python -m ia4.lab.portfolio --force     # backtest portfela → BACKTEST PORTFELA, pierwszeństwo, „wybrane”
python -m ia4.lab.selftest              # test silnika
```

Prognoza FX 1h (sekcja 4c) — Mac włączony, gdy używasz zakładki FX strony IA4:

```bash
cd ~/Desktop/IA4/ia4-research && source .venv/bin/activate
python -m ia4.fx.selftest              # test modułu na danych syntetycznych (ok. 3 min) — „WYNIK: OK”
python -m ia4.fx.sync                  # kopia świec 1h 11 instrumentów → data/fx1h/ (oba programy robią to same)
python -m ia4.fx.catalog               # kalibracja próbna → data/fx1h/catalog-preview.csv (nic nie wysyła)
python -m ia4.fx.catalog --commit      # kalibracja właściwa → fx/conditions.json (RAZ, zasada 14)
python -m ia4.fx.research              # ręcznie: przeliczenie wszystkich okoliczności i ratingów → branch fx
python -m ia4.fx.live                  # prognoza na żywo co 30 s → branch fx-live → strona IA4, zakładka FX (Ctrl+C kończy)
```

Poszukiwanie (gdy zostanie wznowione, `search_closed: false`): `python -m ia4.lab --workers 4` (alias `ia4`); opcje: `--hours N`, `--workers N`, `--check`, `--no-sync`, `--no-push`.

### Limity Firestore (plan Spark: 20 000 zapisów i 50 000 odczytów na dzień)

| Część | Zapisy | Odczyty |
|---|---|---|
| zbieranie na żywo (75 instrumentów, 7 świec) | ok. 1100 / dzień | — |
| moduł FX 1h (świeca: dokumenty dni instrumentów z nową świecą + `system/fx1h`; kontrola dni) | ok. 290 / dzień roboczy, w weekend ok. 50 (BTC) + ok. 11 / dzień kontroli; historia ok. 7000 raz; usunięcie bazy 5 min ok. 66 raz | ok. 11 / dzień (kontrola); „przelicz arkusz FX” ok. 7000; usunięcie bazy 5 min ok. 65 raz |
| nocne odświeżenie + liczenie bazy | ok. 550 / noc | ok. 150 / noc |
| historia doubleProof (do zakończenia) | najwyżej 8000 / dzień | — |
| „Konfiguruj” / „Uzupełnij ostatni miesiąc” | ok. 2500 / raz | — |
| paper trading | — | pierwsze zbudowanie pamięci ok. 19 000 (raz), potem ok. 150 / świecę + ok. 650 raz dziennie |
| Mac: `ia4.sync` przyrostowo | — | kilkaset / start |
| Mac: odświeżanie doubleProof w `ia4.lab` | — | ok. 250 / godzinę pracy |
| Mac: pierwsza synchronizacja nowych instrumentów (doubleProof) | — | ok. 10 000 (raz) |
| Mac: `ia4.sync --full` | — | ok. 48 000 — nie łączyć tego samego dnia z innymi dużymi odczytami |
| Mac: `ia4.fx.sync` (FX-research, start FX-real-time) | — | pierwszy raz ok. 7000 (wszystkie dni 11 instrumentów), potem ok. 1–3 na instrument / start |
| Mac: FX-real-time | — | ok. 12 / godzinę: ok. 290 / pełny dzień roboczy, w weekend ok. 50 (BTC) |

### Limity Apps Script (konto Gmail)

Łączny czas triggerów: 90 min dziennie; jedno uruchomienie: 6 min; `UrlFetchApp`: 20 000 zapytań dziennie. Zużycie czasu widać w STATS („Czas pracy automatu dziś”). Zapytania: Yahoo akcje ok. 75 × 7 + ponowienia brakujących + nocne odświeżenie (ok. 700 / dzień), Yahoo FX 1h ok. 270 / dzień (jedno zapytanie na instrument i świecę; więcej, gdy Yahoo się spóźnia), historia FX 11 zapytań raz, Firestore i GitHub — kilkaset.

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
| 1.30 | 2026-10-11 | Kalibracja `fx-cond/2` (4c.3 p. 2, przed pierwszym `--commit`, za zgodą człowieka): kandydat przepada także, gdy na którymkolwiek instrumencie częstość którejkolwiek strony < 1% albo > 80% (`INST_RANGE` w `catalog.py`). Przegląd próbnej kalibracji z 11.10.2026: 12 par (knoty, położenie zamknięcia) rozpoznawało instrument zamiast rynku (0,1–97,9%). |
| 1.29 | 2026-10-11 | Porządek instrukcji, żeby nowa rozmowa wiedziała wszystko: nowa sekcja 0 (mapa trzech filarów — akcje i wirtualny inwestor, FX: zbieranie + prognoza, strona; przepływ danych; gdzie co leży; historia wersji w skrócie; lista otwartych kroków), nagłówek „Aktualny etap” ze wszystkimi etapami, zasada 7 (czytanie `vi.json` i listy otwartych kroków), zasada 8 (wersja także w `docs/`), 11a (`vi.json`), Etap 3 (stan), krok FX-8 (plan inwestora FX, tylko za zgodą), nowy Etap 5 — strona IA4. `Telemetry.gs`: etap w telemetrii zgodny z nagłówkiem. Bez zmian logiki. |
| 1.28 | 2026-10-11 | Strona IA4 — konsola systemu (nowa sekcja 11b): GitHub Pages z `main/docs` zamiast dashboardu z brancha `fx`, moduły bez buildu (`docs/README.md` — jak rozwijać), bramka hasła (tylko skrót PBKDF2 w kodzie; dane nadal publiczne), zakładki System (magistrala Yahoo → Apps Script → Firestore → GitHub → Mac → strona z wiekiem każdego ogniwa, stan składników, strumień zdarzeń, parametry, spływ świecy akcji, instrumenty, źródła), Inwestor (wyniki, krzywa, pozycje z SL–TP, strategie z filtrami, transakcje, spółki, sygnały) i FX (prognoza 11 instrumentów, spływ świec 1h, scenariusze, przeliczenia, miejsce na inwestora FX), wersja telefonu nastawiona na stan. Nowy plik `telemetry/vi.json` (`Telemetry.gs`, wysyła go `Paper.gs` po każdej świecy; `sigLog` w stanie inwestora) i `state.json` od razu po świecy. Python: FX-research i FX-real-time nie kopiują już dashboardu na branch `fx` (`ia4/fx/dashboard/` usunięty, 4c.10). |
| 1.27 | 2026-10-10 | Krok FX-7 — świece 1h i 11 instrumentów zamiast EURUSD 5 min (decyzja człowieka z 10.10.2026): `Fx.gs` od nowa — kolekcja `fx1h/{ID}/days` + `system/fx1h`, 10 par walutowych (EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD, USDCHF, NZDUSD, EURJPY, GBPJPY, EURGBP) i BTCUSD (4b, uzasadnienie doboru), historia 728 dni jednym zapytaniem na instrument, na żywo wszystkie instrumenty jednym `fetchAll`, kontrola dni i uśrednienie jak dotąd, arkusz FX z kolumną na instrument (`24/24 (1)`), STATS „FX 1h”, menu „usuń stare świece EURUSD 5 min” (zasada 2.2 — jedyne skasowanie danych, z potwierdzeniem), Script Properties `FX1H_STATE`, `FX1H_CHECK`. Python: `instruments.py`, `sync.py` → `data/fx1h/`, katalog `fx-cond/2` (cechy bezwymiarowe w ATR100, okresy 9/20/24/50/100/120/200, kalibracja na puli wszystkich instrumentów, `covInstMin/Max`), `fx-cond/1` do `fx/archive/fx-cond-1-5m/` (zasada 14: nowy katalog → `fx-cond/3`); FX-research na puli instrumentów: zmiany w ATR100, części walk-forward po kalendarzu, `n_ind` na instrument, ID przeliczeń `H-…`; scenariusze: `pora` w instrumencie, `analogi` w grupie (pary razem, BTC osobno), odstęp ≥ 12 h w kalendarzu, skalowanie √(ρt/ρa), ρ = ATR12/ATR100, λ > 0 tylko przy przewadze środka ≥ 1%, wyniki części B na każdym instrumencie; horyzont 48 świec w godzinach rynku; `forecast.json` z listą `instruments` (bez NaN); dashboard z zakładkami instrumentów; OKOLICZNOSCI_FX `okol-3`. Nowy `synth.py`, selftest od nowa (ok. 3 min). Wszystko liczone od nowa (kalibracja, H-001). |
| 1.26 | 2026-10-09 | Kroki FX-5 i FX-6 — prognoza rozkładu zamiast jednej uśrednionej linii (4c.0, zasada 15): badanie na danych R-001 (kierunek ≈ rzut monetą, zakres i rozrzut przewidywalne dzięki porze dnia i zmienności); `scenario.py` — 80 prawdziwych ścieżek z historii (pora dnia ±1 h, metoda `pora` albo `analogi` z Jaccardem ważonym ratingiem, odstęp ≥ 12 świec, skalowanie √(ATR100·ATR12)), środek = λ × średnia profili ważona ratingiem, stożek 10/25/75/90%, P(wzrost), oczekiwany zakres 4 h, 3 scenariusze; sprawdzian walk-forward 70–85% kalibracja / 85–100% ocena (pinball, pokrycie, Brier, błąd zakresu), wybór modelu, λ = 0 bez przewagi środka (4c.7); `forecast.json`, dashboard i nagłówki OKOLICZNOSCI_FX (`okol-2`) na nowo; stary sprawdzian średniej (`check`) zastąpiony przez `scenario`. |
| 1.25 | 2026-10-09 | Krok FX-4: `python -m ia4.fx.live` — prognoza na żywo (pętla 30 s, ok. 2 odczyty Firestore na świecę, zero przy zamkniętym rynku, sygnał życia co 2 min, `stoppedAt` po Ctrl+C), `forecast.json` na branchu `fx-live` (jeden commit); dashboard `index.html` na GitHub Pages z brancha `fx` (status Maca, rynek, wykres 48 + 48, kafelki, top 5 okoliczności), kopiowany przez FX-research i FX-real-time. Selftest: symulacja piątek → niedziela. PRZEWODNIK: sekcja o prognozie. |
| 1.24 | 2026-10-09 | Krok FX-3: arkusz OKOLICZNOSCI_FX (`Fx.gs`, 4c.11) — katalog i kolumna `rating/wystąpienia` na każde przeliczenie, odświeżany w `researchSync` tylko po nowym commicie brancha `fx` (`FX_RUNS`), menu „💱 EURUSD — odśwież OKOLICZNOSCI_FX teraz”. 4c.3: wiersz 17 opisuje rodzinę „Trend i korekta” tak, jak skalibrowano `fx-cond/1` (kod 1.21); poprawka z 1.22 obowiązuje dopiero dla `fx-cond/2`. |
| 1.23 | 2026-10-09 | Krok FX-2: `python -m ia4.fx.research` — wystąpienia, profile, ratingi, sprawdzian, zapis `fx/ratings.json` i `fx/runs.jsonl`, lokalnie `occurrences.npz` i `ratings-preview.csv`. Rating (4c.5) metodą walk-forward na 5 częściach zamiast jednego podziału 70/30 (mniej przypadkowych ratingów przy tej samej wykrywalności); sprawdzian (4c.7) z ratingami walk-forward na pierwszych 70% i wskazówką, jak go czytać. Selftest: zgodność z liczeniem ręcznym, brak zaglądania w przyszłość, zasiany sygnał, czysty szum. |
| 1.22 | 2026-10-09 | Przegląd kalibracji próbnej na prawdziwych danych: rodzina 17 „Trend i korekta” — nowa cecha `combo_dip` (cena nad średnią długą, ale pod krótką), `combo_pull` tylko m = 3, 6, cele 15% i 12% zamiast 25/15/40% (wcześniej „korekta” wypadała na medianie, np. „zmiana ≤ +4 pips”). |
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
