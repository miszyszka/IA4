# IA 4 — instrukcja projektu

**Wersja:** 1.57 · **Data:** 21 października 2026

Ten plik jest jedynym źródłem prawdy i zbiorem żelaznych zasad projektu. Jest celowo krótki: zasady, liczby ważne dla człowieka, stan. Jeśli kod, arkusz albo telemetria rozjeżdżają się z tym plikiem — obowiązuje ten plik, a rozbieżność trzeba naprawić.

- **Szczegóły techniczne** (wzory, formaty pól, kolejność zdarzeń) opisuje kod — on jest implementacją wzorcową — oraz pełna instrukcja 1.40 w `archiwum/IA4_INSTRUKCJA-1.40.md`. Numery sekcji w komentarzach kodu sprzed 1.41 (np. „8.6”, „4c.6”, „11c.7”) prowadzą do tamtego pliku. Przy sprzeczności wygrywa ten plik.
- **Jak czytać stronę i arkusze:** `PRZEWODNIK.md` (i opisy „?” na stronie).

---

## 0. Stan na dziś i otwarte kroki

| Etap | Stan |
|---|---|
| 1. Baza akcji 1h (75 spółek) | ✅ działa bez końca |
| 2. Poszukiwanie strategii | ⏸ wstrzymane od 3.10.2026 — 60 aktywnych strategii |
| 3. Paper trading (mechaniczny inwestor) | 🟨 działa od 6.10.2026; 1.53: Powrót.v2 Investor (FX, paper, 100 $, maile z sygnałami) — od wdrożenia `PowrotV2.gs` |
| 4. FX 1h: zbieranie 10 par + BTC i prognoza rozkładu | 🟨 zbieranie działa; prognoza H-002 — kierunek bez przewagi; 1.49–1.57: badania FX-SHORT-NY, FX-POWRÓT, FX-ODKRYWCA, FX-POWRÓT v2 i v3 (sekcja 7b, informacyjne); 1.52: 10 par fx1h_double_proof — historia do pobrania |
| 5. Strona IA4 | 🟨 działa, rozwijana na prośbę |
| 6. AI Investor — agenci na Macu | 🟨 1.41: zespół agentów (Inwestor, Krytyk, Badacz), tryb nauki |
| Baza świec dobowych (pełna historia) | ✅ 75/75 od 15.10.2026 (najstarsza świeca 1970-01-02), aktualizacja codziennie po sesji |

**Otwarte kroki** (Claude odhacza je na podstawie telemetrii i branchy):
1. **Wdrożenie 1.41–1.42:** wypchnąć pakiety; Apps Script — podmienić 7 plików `.gs` (zmienia się tylko numer wersji; 15.10.2026 telemetria: `1.38`); Mac — `git pull`, `python -m ia4.ai.selftest` („WYNIK: OK”), ponownie `ia4 start`.
2. **AI, pierwsza doba 1.41:** panel „praca agentów” — zajętość ≥ 70%, Inwestor wchodzi w transakcje (pierwsza transakcja z notatką, SL i TP zamyka krok AI-2), Krytyk pisze przeglądy, Badacz zapisuje hipotezy.
3. **Badania wielodniowe (1.45):** One-Day (1.35–1.44) — bez przewagi po spreadzie: pojedyncze reguły, portfel walk-forward, siła ruchu (po dużym dniu ruch ok. 2,5 × większy, po konsolidacji — mniejszy; long + short naraz nie zarabia). Teraz pozycje kilkudniowe (sekcja 7a). Mac: `python -m ia4.swtrend`, `python -m ia4.swrsi`, `python -m ia4.swserie`, `python -m ia4.swportfel`, `python -m ia4.swrowna` → `SWING-*.xlsx`; przegląd z Claude: liczba strategii spełniających warunek na tle placebo, ✓ na doubleProof, mapa dP obok mapy 53 spółek.
4. **Badania FX (1.49–1.52):** Mac — `python -m ia4.fxshort --selftest`, `python -m ia4.fxpowrot --selftest` i `python -m ia4.fxodkrywca --selftest` („WYNIK: OK”), potem `python -m ia4.fxshort` → `FX-SHORT-NY.xlsx` i `python -m ia4.fxpowrot` → `FX-POWROT.xlsx` (powtórzenie liczb Claude na świeższej kopii fx1h), a `python -m ia4.fxodkrywca` (ok. 3 h) → `FX-ODKRYWCA.xlsx` tylko jako potwierdzenie wniosku 1.51 (otwarcie skarbca na Macu zapisuje się w jego dzienniku); decyzja człowieka: czy test na żywo (papier albo demo XTB) przez ≥ 30 transakcji bez zmiany parametrów — kandydat: FX-POWRÓT v2 (sekcja 7b), najpierw doubleProof.
4a. **doubleProof FX (1.52):** ✅ Apps Script 1.53 wdrożony, historia 21/21 (20.10.2026) — teraz Mac; automat pobrał historię 10 par fx1h_double_proof (jedna para na wolne uruchomienie, ok. 5 200 zapisów Firestore jednorazowo; postęp: STATS „historia N/21”, arkusz FX — nowe kolumny). Potem Mac — `python -m ia4.fxpowrot2 --selftest`, `python -m ia4.fxpowrot2` → `FX-POWROT-V2.xlsx` z arkuszem DOUBLEPROOF (test jednorazowy, otwarcie zapisane); przegląd z Claude.
4d. **Powrót.v2 — analiza strat i „razem” (1.57):** Mac — `python -m ia4.fxpowrot3 --selftest`, potem raz `python -m ia4.fxpowrot3 --double-proof` → `FX-POWROT-V3.xlsx` (arkusz DOUBLEPROOF: czy efekt „razem” powtarza się na 10 nowych parach); decyzja człowieka: oznaczenie „wieloparowy / samotny” w mailach i arkuszu Powrót.v2.Investor, ewentualnie wielkość pozycji (sekcja 7b).
4c. **Historia Powrót.v2 na stronie (1.55):** Mac — `python -m ia4.fxpowrot2 --strona` (raz, potem przy każdym `python -m ia4.fxpowrot2`) → strona FX → Powrót.v2 → historia / galeria.
4b. **Powrót.v2 Investor (1.53):** Apps Script — podmienić wszystkie pliki `.gs`, dodać nowy `PowrotV2.gs` („+ → Skrypt”) i podmienić manifest `appsscript.json` (Ustawienia projektu → „Pokaż plik manifestu”; nowy zakres: wysyłanie poczty); zapisać, w arkuszu menu **IA 4 → 📧 Powrót.v2 — mail testowy** (Google prosi o zgodę na pocztę), potem **📉 Powrót.v2 — przelicz teraz** (powstaje zakładka **Powrót.v2.Investor**; inwestor liczy od tej chwili, 100 $). Sprawdzić: mail testowy doszedł, na stronie FX → Powrót.v2 są wykresy 10 par. Pierwszy sygnał — średnio za 2–3 dni.
5. **Do potwierdzenia przez człowieka:** usunięcie starej bazy EURUSD 5 min (menu „🗑 FX — usuń stare świece EURUSD 5 min”); zamknięcie FX-7 (arkusz OKOLICZNOSCI_FX ma kolumny H-001 i H-002).
6. **Później, tylko za zgodą:** strategie i wirtualny inwestor FX z prognozy (gdy dowiedzie przewagi kierunku; Powrót.v2 Investor — sekcja 7b — to osobny paper trading jednej strategii, decyzja człowieka z 20.10.2026); bramka sejfu AI dla hipotez; cechy pisane przez model w piaskownicy.

---

## 1. Cel

IA 4 **zbiera świece** z Yahoo do Firestore (Apps Script, bez Maca), **liczy na nich** (Python na Macu) i **pokazuje wyniki** (strona IA4, arkusz Google). Szukamy przewagi na rynku, która przetrwa uczciwy test — a nie wyników, które wyglądają dobrze tylko na danych, na których ich szukano.

| Filar | Co robi | Gdzie |
|---|---|---|
| **A. Akcje** | baza świec 1h 75 spółek → strategie `ia4-rule/1` → sygnały na żywo i mechaniczny inwestor (100 $ na transakcję) | Apps Script + Mac (`ia4.lab`) |
| **B. FX** | świece 1h 10 par walutowych + BTC → prognoza rozkładu na 48 świec | Apps Script + Mac (`ia4.fx`) |
| **C. Strona IA4** | konsola: czy system żyje, wyniki, prognoza, agenci | GitHub Pages (`docs/`) |
| **D. AI Investor** | agenci na lokalnym modelu językowym: papierowy portfel 100 000 $, hipotezy, krytyka, nauka na błędach | Mac (`ia4 start`, `ia4.ai`) |

---

## 2. Żelazne zasady

1. **Firestore jest jedynym źródłem danych.** Kopia na Macu jest robocza — można ją skasować i odtworzyć. Python nigdy nie pobiera świec z Yahoo i nigdy nie pisze do Firestore.
2. **Baza tylko rośnie.** Zapisujemy wyłącznie zamknięte świece, niczego nie kasujemy. Wolno przepisać dane tylko danymi pobranymi ponownie z Yahoo. Jedyny wyjątek: świeca FX, której Yahoo nie oddało po 3 próbach, jest uśredniana — zawsze oznaczona (`fillT`).
3. **Format bazy jest stały.** Zmiana formatu = najpierw zmiana tej instrukcji, zgoda człowieka i opis migracji.
4. **Uczciwy test.** Wynik na danych, na których szukano, jest zawyżony. Liczą się: dane, których poszukiwanie nigdy nie widziało (skarbiec, doubleProof, sejf AI) i wynik na żywo. Skarbiec i sejf otwiera tylko bramka w kodzie; każde otwarcie jest liczone i zapisywane.
5. **Symulacja jest zawsze pesymistyczna:** wejście po open następnej świecy, przy SL i TP w tej samej świecy — zawsze SL, luka na otwarciu bez premii. Koszty liczą: mechaniczny inwestor, backtest portfela, wszystko w AI Investor i wszystkie badania One-Day i wielodniowe — **spread 0,3% wartości pozycji, raz na transakcję** (wejście i wyjście razem; decyzja człowieka z 16.10.2026; przeliczenia z `--cost 0.6` liczyły go podwójnie). Badania FX (sekcja 7b) — spread w pipsach raz na transakcję: EUR/USD 1,1 pipsa (zrzut XTB, decyzja człowieka z 19.10.2026), pozostałe pary — tabela kosztów AI (`fx_spread_pips`) × 1,1 / 0,8.
6. **Ocena z niepewnością.** Każdy wynik podaje liczbę transakcji, średni wynik z przedziałem 95% i medianę świec w pozycji. Żadnego werdyktu przed 30 transakcjami.
7. **Strategia to reguła, nie kod.** Reguła `ia4-rule/1` jest opisana liczbami (linie, sygnał, filtry, SL, TP, FC, limit). Liczy ją Python (`ia4/lab`) i JavaScript (`PaperEngine.gs`); każda zmiana definicji trafia do obu naraz, a test zgodności musi dać 0 rozbieżności.
8. **Katalog okoliczności FX (`fx-cond/2`) jest nienaruszalny;** prognoza FX zawsze jako rozkład (stożek, zakres, P(wzrost)) z wynikiem sprawdzianu słowami — nigdy sama linia.
9. **LLM myśli, Python liczy.** W AI Investor każda liczba pochodzi z kodu; model odpowiada wyłącznie JSON-em zgodnym ze schematem; limity ryzyka egzekwuje kod; kod napisany przez model nie jest uruchamiany (model wybiera tylko z menu klocków).
10. **Agenci uczą się przez działanie, ryzyko pilnuje kod.** Portfel AI jest papierowy; brak transakcji niczego nie uczy. Śmiałość reguluje poziom nauki (sekcja 8), a granice — twarde limity w kodzie.
11. **Sekrety nigdy nie trafiają do repozytorium:** klucz Firebase (`~/.ia4/serviceAccount.json`), token GitHub (Script Properties → `GITHUB_TOKEN`).
12. **Gdzie kto pisze.** `main` — kod, ta instrukcja, `telemetry/` (Apps Script), strona `docs/`; wyniki Pythona — wyłącznie własne branche (`research`, `fx`, `fx-live`, `ai`, `ai-live`). Python nie pisze do `main`.
13. **Jedna wersja dla całego projektu:** ten plik, nagłówki `.gs` i `CONFIG.VERSION`, `ia4/__init__.py`, strona (`VERSION` w `docs/js/core.js`). Zmiana zasady, formatu, etapu albo liczby z tej instrukcji podbija wersję i dostaje wpis w sekcji 11; drobne poprawki — tylko opis w commicie.
14. **System jest minimalny.** Nowa funkcja, arkusz, plik czy etap — tylko za zgodą człowieka i najpierw jako zmiana tej instrukcji.

---

## 3. Jak działa system

```
Yahoo ──(Apps Script, trigger co minutę)──▶ Firestore ──▶ Mac: kopia lokalna ──▶ ia4.lab · ia4.fx · ia4.ai
             │                                                                        │
             ├──▶ arkusz Google (STATS, FX, STRATEGIE, SIGNALS-REALTIME, VIRTUAL-INVESTOR, Powrót.v2.Investor …) · mail z sygnałami Powrót.v2
             └──▶ GitHub main: telemetry/ ──┐              GitHub research · fx · fx-live · ai · ai-live ◀──┘
                                            └──────▶ strona IA4 (przeglądarka, tylko odczyt) ◀──────┘
```

| Miejsce | Zawartość | Kto pisze |
|---|---|---|
| Firestore | `stocks`, `proof`, `context`, `doubleProof` (świece 1h akcji), `daily` (świece dobowe), `fx1h` (FX), `system/*` | Apps Script |
| branch `main` | kod (`*.gs`, `ia4-research/`), instrukcja, `PRZEWODNIK.md`, `telemetry/state.json`, `telemetry/vi.json`, `telemetry/pv2.json`, strona `docs/` | Claude (pakiety), Apps Script (`telemetry/`) |
| branch `research` | strategie, dziennik poszukiwania, doubleProof, backtest portfela | Mac (`ia4.lab`) |
| branch `fx`, `fx-live` | katalog okoliczności i ratingi; historia Powrót.v2 dla strony `fx/pv2/` (od 1.55); prognoza na żywo `forecast.json` | Mac (`ia4.fx`, `ia4.fxpowrot2`) |
| branch `ai`, `ai-live` | historia AI (transakcje, decyzje, hipotezy, przeglądy, praca agentów); stan na żywo `status.json` | Mac (`ia4.ai`) |
| Mac `~/Desktop/IA4/` | repo, kopie lokalne w `ia4-research/data/`, pliki Excel (`AI-INVESTOR.xlsx`, `ONE-DAY-*.xlsx`, `SWING-*.xlsx`) | Mac |

**Pliki Apps Script:** `Code.gs` (zbieranie, STATS, menu, triggery) · `Daily.gs` (świece dobowe) · `Fx.gs` (FX 1h) · `Research.gs` (arkusz STRATEGIE) · `Paper.gs` + `PaperEngine.gs` (sygnały i mechaniczny inwestor) · `PowrotV2.gs` (Powrót.v2 Investor: FX paper trading, maile, `telemetry/pv2.json`; od 1.53) · `Telemetry.gs` (telemetria na GitHub). Manifest `appsscript.json` (zakresy, w tym wysyłanie poczty od 1.53). Triggery: `runCollector` co minutę, `telemetryHourly` co godzinę, `researchSync` co 30 min.
**Python** (`ia4-research/ia4/`): `sync.py`, `daily.py` (kopie), `lab/` (reguły), `fx/` (prognoza), `ai/` (agenci), `oneday.py`, `odsearch.py`, `odport.py`, `odbreak.py` (badania One-Day), `swing.py`, `swtrend.py`, `swrsi.py`, `swserie.py`, `swportfel.py`, `swrowna.py` (badania wielodniowe), `fxshort.py`, `fxpowrot.py`, `fxodkrywca.py`, `fxpowrot2.py`, `fxpowrot3.py` (badania FX, sekcja 7b).

---

## 4. Dane

**Instrumenty (75 akcji):** główne 3 (AAPL, TSLA, NVDA) i kontrolne 50 — razem **53 handlowane**; tło rynku SPY, QQQ (tylko filtry); **doubleProof 20** (AMD, INTC, QCOM, CSCO, ADBE, LRCX, C, MS, SCHW, COP, OXY, SLB, BA, GE, UBER, F, GM, COST, BMY, CMCSA) — poszukiwanie nigdy ich nie widzi, służą wyłącznie do uczciwej weryfikacji. Listy: `CONFIG` w `Code.gs` i `system/universe`.

**FX (21):** EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD, USDCHF, NZDUSD, EURJPY, GBPJPY, EURGBP oraz BTCUSD; **fx1h_double_proof 10** (od 1.52: EURCHF, EURAUD, EURCAD, GBPCHF, GBPAUD, AUDNZD, AUDJPY, CADJPY, CHFJPY, NZDJPY) — zbierane tak samo (Yahoo → Firestore `fx1h`), ale prognoza FX, badania i agenci AI ich nie wczytują (`python -m ia4.fx.sync` kopiuje je lokalnie; `sync()` w programach — bez nich); służą wyłącznie do jednorazowego sprawdzianu strategii zamrożonej wcześniej. Wolumenu FX nie ma (Yahoo podaje 0). Lista: `Fx.gs` i `ia4/fx/instruments.py` (zmiana — w obu naraz).

**Świece:**
- akcje 1h — sesja regularna NYSE, 7 świec na dzień (świeca 7 — pół godziny; sesja skrócona — 4), historia od września 2024 (granica Yahoo ~730 dni). Wolumen 0 = „Yahoo nie podał”.
- FX 1h — czas początku w UTC; pary walutowe od niedzieli 17:00 do piątku 17:00 czasu Nowego Jorku, BTC 24/7; historia 728 dni.
- dobowe — pełna historia z Yahoo wszystkich 75 akcji, ceny skorygowane o splity, bez dywidend.

**Aktualizacja:** na żywo ok. 30–40 s po zamknięciu świecy; nocne odświeżenie przepisuje ostatnie ~5 sesji; dzień FX kontrolowany do 3 razy, potem braki uśrednione; świece dobowe raz na dzień sesyjny.

**Limity:** Firestore (plan Spark) 20 000 zapisów i 50 000 odczytów dziennie; Apps Script 90 min pracy triggerów dziennie (widać w STATS i na stronie). `python -m ia4.sync --full` zużywa ~48 000 odczytów — tylko w razie awarii kopii.

---

## 5. Strategie akcji i mechaniczny inwestor (Etapy 2–3)

- **Reguła `ia4-rule/1`:** 1–3 średnie kroczące, sygnał (`cross`, `converge`, `turn`, `revert`, `ribbon`, `pcross`), 0–2 filtry, SL i TP 1–10%, limit świec, wyjście FC.
- **Poszukiwanie** (`python -m ia4.lab`, wstrzymane): sita (m.in. ≥ 30 transakcji, PF ≥ 1,5, przewaga nad wejściem na ślepo ≥ 1,2, stabilność), na końcu bramka **skarbca** (najstarsze 800 świec każdej spółki); najwyżej 5 strategii w każdej z 12 grup → 60. Weryfikacja na doubleProof i backtest portfela — tylko informacja i pierwszeństwo strategii.
- **Mechaniczny inwestor** (`Paper.gs`, po każdej świecy, bez Maca): wchodzi w każdy sygnał strategii zaznaczonych „for VI” w arkuszu STRATEGIE, 100 $ na transakcję, 1 pozycja na spółkę, koszt 0,005% przy wejściu i wyjściu. Wynik: arkusz VIRTUAL-INVESTOR, `telemetry/vi.json`, zakładka Inwestor.
- **Test zgodności** po każdej zmianie reguł: `python tests/parity_dump.py /tmp/p.json && node tests/parity.js /tmp/p.json` → „rozbieżności: sygnały 0, transakcje 0”.

---

## 6. FX — prognoza rozkładu (Etap 4)

- Kurs walut jest bliski błądzeniu losowemu: **kierunek ≈ rzut monetą, zakres ruchu da się przewidzieć.** Dlatego prognoza to rozkład na 48 świec 1h: stożek 50% i 80%, oczekiwany zakres, P(wzrost), 3 prawdziwe scenariusze z historii. Linia środkowa odchyla się tylko o tyle, o ile sprawdzian na danych niewidzianych potwierdził przewagę (inaczej jest płaska).
- **Katalog `fx-cond/2`** — 1000 okoliczności (500 par lustrzanych), skalibrowany raz, nienaruszalny; **rating 1–100** — przewaga nad „cena się nie zmieni”, walk-forward.
- **Sprawdzian** w każdym przeliczeniu: Brier < 0,245 = przewaga kierunku (0,25 = moneta); stożek 80% trafny przy pokryciu 75–85%.
- Programy: `python -m ia4.fx.research` (ręcznie → branch `fx`), prognoza na żywo — wewnątrz `ia4 start` (osobny `python -m ia4.fx.live` tylko bez AI). Stan: H-001 i H-002 — kierunek bez przewagi, stożek trafny.

---

## 7. Badania One-Day i wielodniowe (informacyjne)

Transakcja trwa jeden dzień (open → close). `ia4.oneday` — kaskady i portfel OD-080: bilans ujemny. `ia4.odsearch` — reguły rosnące równo: **20 okresów kalendarza, najwyżej 3 stratne** (decyzje człowieka z 14.10.2026; przypadek daje ok. 20 takich reguł, więc rozstrzygają potwierdzenie na doubleProof i placebo), zawsze co najmniej jeden portfel short. Na 2 latach świec 1h — brak stabilnej przewagi; następny krok — baza dobowa od 2000 r. Wyniki niczego nie zmieniają bez zgody człowieka.

**Spread (od 1.42, decyzja człowieka z 15.10.2026; od 1.45 — raz na transakcję we wszystkich badaniach, decyzja z 16.10.2026):** każda transakcja płaci **0,3%** stawki (wejście i wyjście razem; `--cost`, domyślnie 0,3). Wynik transakcji = ruch open → close w kierunku pozycji − 0,3; warunek okresów, punkt odniesienia (wejście każdego dnia), placebo i portfele liczone są netto, arkusz pokazuje obok średnią brutto. Skutek: reguły z tysiącami małych transakcji spadają pod zero — zostają rzadkie sytuacje z dużym ruchem. Dlatego siatka ma bardziej skrajne setupy (6–7 świec z rzędu, korpus ≥ 3r, spadek / wzrost 5 sesji ≥ 4r i 10 sesji ≥ 5r, RSI(2) < 2 / > 98) i filtr **zmienności bezwzględnej** (r ≥ 2%, 3%, 4% — spread jest stały w %, więc relatywnie tańszy przy dużych ruchach): razem 60 setupów × 234 kombinacje filtrów × 2 kierunki = 28 080 reguł kierunkowych + 600 neutralnych (neutralne płacą spread na obu nogach). Potwierdzenie ✓ na doubleProof wymaga teraz także dodatniego wyniku netto po spreadzie. Gdy żadna reguła nie spełnia warunku, plik i tak pokazuje najlepszy long (#1) i najlepszy short (S1) z uwagą „nie spełnia warunku” i powodem.

**Portfel strategii wybieranych krok po kroku w czasie — `ia4.odport` (od 1.43, decyzja człowieka z 15.10.2026, po wyniku 1.42: przy spreadzie 0,6% żadna pojedyncza reguła nie spełniła warunku):**
1. **Poszukiwanie szersze, z przycinaniem:** kierunek + setup (82: dotychczasowe + ruchy w procentach bezwzględnych — korpus i zmiana wczoraj ≥ 3/5/8%, zmiana 3 sesji ≥ 8/12%, słabość / siła względem SPY ≥ 3/5 pkt proc., roczny dołek / szczyt) + **do 3 filtrów** z różnych grup (33: dotychczasowe + r ≥ 5%, szeroka wyprzedaż / szeroki wzrost rynku wczoraj — ≥ 80% / ≤ 20% spółek spadkowych, SPY wczoraj ≤ −1,5% / ≤ −3% / ≥ +1,5%, zmienność SPY ≥ 1,5% / 2,5%, pierwsze 3 i ostatnie 2 sesje miesiąca, sesja przed świętem). Kombinacja z < 30 transakcjami nie jest rozwijana (filtr tylko zmniejsza liczbę transakcji) — ok. 450 tys. reguł. Dla każdej reguły — wyniki netto **rok po roku** (53 spółki). Pojedyncza reguła może być rzadka.
2. **Wybór co rok (walk-forward):** na początku każdego roku — **wyłącznie na danych sprzed tego roku** — najwyżej 20 reguł: ≥ 30 transakcji, suma netto > 0, t-stat dziennych wyników ≥ 3, dodatnie ≥ 60% lat z transakcjami, najwyżej 2 reguły z tego samego setupu i kierunku. Pierwszy rok portfela — po 5 latach historii. Każdy dzień portfela jest grany regułami wybranymi bez wiedzy o nim, więc wynik portfela jest w całości **poza próbą**.
3. **Portfel:** głosy wybranych reguł sumowane w każdej spółce i dniu (long +1, short −1), pozycja = znak sumy, jedna transakcja na spółkę i dzień, spread od każdej.
4. **Ocena portfela:** **20 okresów, najwyżej 3 stratne** — warunek człowieka, teraz na całym portfelu; rok po roku (z liczbą kandydatów i najlepszym t w historii); doubleProof (te same wybory, 20 spółek); placebo (cały proces z losowym znakiem dni); portfel 10 000 $ (5% na transakcję). Arkusz REGUŁY (pełna próba) — tylko do wglądu, zawyżony.
Test na syntetycznej historii 2000–2026 bez przewagi (spread 0,6%): żadna reguła nie przeszła wyboru w żadnym roku — 0 transakcji; z zaszytą przewagą: portfel spełnia warunek, doubleProof dodatni, placebo nie.

**Siła ruchu po konsolidacji i long + short naraz — `ia4.odbreak` (od 1.44, hipoteza człowieka z 15.10.2026: kierunku nie da się przewidzieć, siłę — może):**
- **Jednostka R** = normalna dynamika spółki: średni zakres dnia (H − L)/open ze 100 poprzednich sesji — każda spółka liczona względem siebie.
- **Analiza:** 35 stanów przed open (z punktem odniesienia „każdy dzień”) (konsolidacja 3/5/10/20 sesji o średnim zakresie < 0,5/0,7/0,85 R, ciasny przedział 5/10/20 sesji, najciaśniejsze 10%/20% w roku danej spółki, dni wewnętrzne, NR4, NR7, połączenia; dla kontrastu rozruszany rynek i duży zakres wczoraj) → ruch dnia w R: zakres, największe oddalenie od open, |close − open|, oddalenie w 3 sesje, P(oddalenie ≥ 0,5/1/1,5/2 R), „piła” (obie strony ≥ 0,5 R); wzrost wobec wszystkich dni; arkusz SPÓŁKI — R i wzrost dla każdej spółki.
- **Strategie:** stan × SL 0,25/0,5/0,75/1 R × TP 2 albo 3 × SL × sposób wejścia: **LS — long i short naraz na open** (decyzja człowieka; spread od każdej nogi) oraz porównawczo **BO — wybicie zleceniami buy-stop / sell-stop** s od open (jedno anuluje drugie, SL na open, spread raz). Zawsze w ciągu dnia; kolejność ruchów w świecy dobowej nieznana → zawsze najgorszy wariant (zasada 5): LS — dzień sięgnął obu SL = −2s; BO — po wejściu cena była po drugiej stronie open = SL.
- **Ocena:** 20 okresów / ≤ 3 stratne, część A (< 2013) i B (≥ 2013) obie > 0, doubleProof (t ≥ próg Bonferroniego), placebo — stan przesunięty w czasie o ≥ 252 sesje (ta sama częstość, zero związku z dniem); portfele 10 000 $ najlepszej LS i BO.


### 7a. Badania wielodniowe (informacyjne, od 1.45)

Decyzja człowieka z 16.10.2026: po One-Day pozycje mogą trwać kilka sesji. Wspólny silnik `ia4/swing.py`: baza dobowa od 2000 r. (75 instrumentów), wejście po open sesji po sygnale, SL i TP pesymistycznie (zasada 5: SL i TP w tej samej świecy → SL, luka przez SL → open, luka przez TP → TP), **spread 0,3% raz na transakcję**, jedna pozycja na spółkę naraz. **Portfel 10 000 $ z dźwignią:** depozyt pozycji = 10% stanu portfela (wycena po poprzednim close), wartość = depozyt × dźwignia; brak wolnego depozytu → stawki dnia mniejsze; obsunięcie z wyceny dziennej; ≤ 10% kapitału = upadłość (rachunek nie schodzi poniżej 0). **Bez kosztu nocnego (swap CFD)** — przy dźwigni i pozycjach wielodniowych to realny koszt, do doliczenia przed decyzją.

- **`ia4.swtrend` — strategie jednokierunkowe z SL i TP** (zadanie człowieka: okoliczności towarzyszące wybiciom — trend ze średnich, konwergencja wyznaczająca poziomy, wybicie w górę / w dół). 40 setupów (20 par lustrzanych: szczyt / dołek 10, 20, 55, 252 sesji, wybicie z ciasnego przedziału i po konsolidacji, ściśnięcie Bollingera, konwergencja SMA10/20/50, dzień wewnętrzny, NR7, duży dzień ≥ 2 / 3 R, luka ≥ 1 R, przecięcia SMA20/50, SMA50/200 i ceny z SMA200, korekta w trendzie, seria wzrostów ze szczytem, duży dzień po konsolidacji) × 13 filtrów (cena / SMA50 wobec SMA200, nachylenie SMA200, SPY wobec SMA200, R ≥ 2% / 3%, siła względem SPY) × long / short × SL 0,5–2 R × TP 1–3 × SL × najwyżej 1 / 3 / 5 / 10 sesji = **49 920 strategii**. Warunek (53 spółki): ≥ 30 transakcji, suma netto > 0, 20 okresów — ≤ 3 stratne i ≤ 4 puste, część A (< 2013) i B dodatnie, **lepiej niż wejście na ślepo** (ten sam kierunek i wyjście każdego dnia — inaczej long wygrywa samym wzrostem rynku); ✓ na doubleProof — t przewagi nad ślepym ≥ próg Bonferroniego; placebo — warunki przesunięte w czasie o ≥ 252 sesje.
- **`ia4.swrsi` — reguła człowieka, liczona raz bez zmiany parametrów:** RSI(3) zamyka się < 22, EMA(100) wyżej niż 5 sesji wcześniej, close ≥ 1% pod 10-sesyjnym VWAP → kupno po open następnej sesji, wyjście po close, gdy RSI(3) > 55, jedna pozycja naraz. Portfel QQQ (cała kwota w pozycji 1:1 i cała kwota jako depozyt 1:5), ta sama reguła na każdej spółce osobno i wspólny portfel wszystkich spółek.
- **`ia4.swserie` — mapa serii świec:** wejście po open sesji po dokładnie N świecach spadkowych (close < open; N = 4 … najdłuższa seria), wyjście po close 1., 2. albo 3. sesji, long i short; dla porównania seria świec wzrostowych. W każdej komórce liczba transakcji i końcowy % portfela 10 000 $ na **dźwigni 1:5**; osobna mapa dla 20 spółek doubleProof.

- **`ia4.swportfel` — portfel jednej komórki mapy** (zadanie człowieka z 17.10.2026, domyślnie): po dokładnie 7 świecach spadkowych long po open 8. sesji, wyjście po close 3. sesji pozycji (10.), spread 0,3% raz, dźwignia 1:5, wszystkie 73 spółki (53 + doubleProof), portfel od 2000 r. (`--n`, `--hold`, `--short`, `--lev` — inne komórki). Arkusze: PODSUMOWANIE (wynik, CAGR, najgłębsze obsunięcia, wyniki wg położenia wobec SMA200 / SMA50, nachylenia SMA200, głębokości spadku serii w R, grupy spółek, dekady), KAPITAŁ (stan portfela dzień po dniu i obsunięcie — dwa wykresy), OBSUNIĘCIA (każde ≥ 2%: szczyt, dno, odrobienie), ROK PO ROKU, TRANSAKCJE, ZDARZENIA (każda seria: SMA50/100/200 i odległość ceny od nich, nachylenie SMA200, spadek serii w % i w R spółki — R ze 100 sesji przed serią — najgłębszy punkt w trakcie pozycji, wynik transakcji, czy weszła do portfela). Średnie i R liczone z pełnej historii bazy.
- **Warunki i limit pozycji w `ia4.swportfel` (od 1.47, decyzja człowieka z 17.10.2026 po analizie zdarzeń):** `--min-n` (seria co najmniej n świec — wejście w pierwszym dniu serii, w którym spełnione są wszystkie warunki, jedno wejście na serię), `--min-drop` (spadek serii ≥ x%), `--rynek` (słaby rynek: SPY w czasie serii ≤ −3% albo SPY pod SMA200), `--max-poz` (najwięcej pozycji naraz; przy nadmiarze sygnałów najpierw najgłębszy spadek serii). **Propozycja** (`--propozycja`): ≥ 5 świec, spadek ≥ 10%, słaby rynek, 5 sesji, bez SL, najwyżej 5 pozycji, 1:5. Arkusz ANALIZA: cechy serii (spadek %, w R, SPY w serii, R spółki, RSI(14), cena wobec SMA50 / SMA200) w 5 przedziałach z progami z lat 2000–2012 i wynik w latach < 2000, 2000–2012, ≥ 2013 oraz porównanie warunków — na wszystkich seriach (odrzuconym — wynik hipotetyczny); PODSUMOWANIE: wrażliwość wyniku na dźwignię (1:1–1:5) × limit pozycji (3 / 5 / 10 / bez); ZDARZENIA: także serie odrzucone z powodem.
- **`ia4.swrowna` — strategia RÓWNA (od 1.48, cel człowieka z 17.10.2026: krzywa kapitału konsekwentnie w górę, w bessie bez strat, małe obsunięcia, bez przeuczenia).** Wniosek z badań: zysk kupowania paniki to głównie odbicie całego rynku (SPY w 5 sesji po sygnale średnio +0,8–1,9%), więc zawsze przechodzi przez krach; zabezpieczenie shortem SPY zabiera zysk, SL i stop czasowy go zmniejszają. Równą krzywą daje kupowanie spadków **tylko przy rosnącym trendzie rynku**. Dwie części: (1) QQQ — reguła RSI(3) z `ia4.swrsi` bez zmian, wartość pozycji = min(3, 25% / zmienność QQQ z 20 sesji) × stan portfela; (2) spółki (73) — ≥ 5 świec spadkowych, spadek serii ≥ 10%, tylko gdy EMA100 SPY wyżej niż 5 sesji wcześniej; 5 sesji, bez SL, 20% stanu portfela na pozycję, najwyżej 5 naraz. Rachunek CFD 1:5 (depozyt = wartość / 5), `--skala` mnoży pozycje. Arkusze: PODSUMOWANIE (całość, części osobno, wynik w czasie każdej bessy S&P 500), KAPITAŁ (wykresy), OBSUNIĘCIA, ROK PO ROKU (zysk każdej części), TRANSAKCJE, SYGNAŁY SPÓŁEK, ODPORNOŚĆ (sąsiednie ustawienia, części osobno, spółki 53 / doubleProof, wynik transakcji w okresach). `swing.portfolio`: wielkość pozycji `size` w transakcji i limit pozycji na etykietę (`max_by_label`).

**Wyniki z 16.10.2026** (Claude, kopia bazy dobowej do 14.10.2026): *swtrend* — warunek spełnia 19 z 49 920, placebo 13 → poziom przypadku; wszystkie to long „po załamaniu” (wybicie w dół z dnia wewnętrznego / NR7 / dołka 55–252 sesji, SL 2 R, TP 3 × SL, 5–10 sesji) — wybicia w kierunku ruchu i każdy short tracą; ✓ jedna (long po NR7 w dół w bessie SPY): portfel 1:1 +71% w 25 lat przy obsunięciu 51%, 1:5 — upadłość w 2008. *swrsi* — QQQ: 209 transakcji, 76% zyskownych, śr. +0,57% netto, PF 2,34; portfel 1:1 +215% (obsunięcie 14%; kup i trzymaj +658%), 1:5 +13 884% (obsunięcie 64%, bez kosztu nocnego); na spółkach słabiej (47 z 74 ze średnią > 0, wspólny portfel 1:1 +44% przy obsunięciu 45%, 1:5 — upadłość w 2020). *swserie* — długie serie spadków dają lekkie odbicie (long po 7 spadkach, 3 sesje: +531% na 53 spółkach, ale +10% na doubleProof, sąsiednie komórki słabe), krótkie serie (4–6) przy tysiącach transakcji — spread × dźwignia → upadłość; serie wzrostów — strata w obie strony. Wyniki niczego nie zmieniają bez zgody człowieka. *swportfel* (17.10.2026): 1370 serii / transakcji (1364 w portfelu), 51% zyskownych, śr. +0,36% netto (+1,78% depozytu przy 1:5); portfel 10 000 $ → 60 804 $ (+508%, CAGR 7%), największe obsunięcie 54% (szczyt 2010-04, dno 2011-08, odrobione dopiero 2020-03; wcześniej −50% 2001-06 → 2008-10); zysk przychodzi skokami w kilku latach (2009 +52%, 2019 +39%, 2020 +39%, 2022 +35%, 2025 +49%, 2026 +63%), pomiędzy — długie okresy strat; cena pod SMA200 śr. +0,59%, nad SMA200 −0,04%; SMA200 spadająca +0,80%, rosnąca −0,02%; doubleProof +0,13%; dekada 2010–2019 ≈ 0. *Analiza zdarzeń i propozycja* (17.10.2026): zarabia kapitulacja — duży spadek serii w % (≥ 10–12%), słaby rynek, wysoka zmienność spółki (R ≥ 3–4%); bez znaczenia: dzień tygodnia, wolumen, luka na otwarciu, spadek w R. Wejście limitem poniżej open albo po potwierdzeniu (nad szczytem świecy) — gorsze niż po open; SL szkodzi; dłuższe trzymanie (5 sesji) lepsze niż 1–3. Propozycja od 2000 r.: 938 serii spełnia warunki, śr. +1,77% netto, 58% zyskownych; z limitem 5 pozycji 681 transakcji, portfel 1:5 +732% przy obsunięciu 79% (2001 → 2009) — o obsunięciu decyduje dźwignia, nie limit (1:2 — ok. 35–39%). Na wszystkich seriach ≥ 5 świec warunek „spadek ≥ 10% i słaby rynek”: przed 2000 +3,70%, 2000–2012 +2,76%, od 2013 +0,66%, doubleProof +1,50%. Zastrzeżenie: 73 spółki to te, które przetrwały — kupowanie spadków wygląda lepiej niż w rzeczywistości. *RÓWNA* (17.10.2026, od 2000 r.): 10 000 $ → 130 509 $, CAGR 10,1%, największe obsunięcie 24,6% (08.2023 → 09.2024 — spadki półprzewodników; odrobione 02.2026), R² krzywej 0,97, 4 lata stratne (najgorszy −8,7%); w bessach: 2000–02 +0,6%, 2007–09 −2,7%, 2020 −4,6%, 2022 −2,1%; skala 1,5: CAGR 14,9%, obsunięcie 35%. Sąsiednie ustawienia (cel zmienności 20–30%, spółki 10–30% na pozycję, max 3–10) — CAGR 8,7–11,4%, obsunięcie 19–32%; bez filtru trendu bessa 2007–09 −28%. Wynik transakcji z filtrem trendu dodatni w latach 1980–1999, 2000–2012 i od 2013; same spółki doubleProof — słabo dodatnie (CAGR 1,8%).

### 7b. FX — short po gwałtownym wzroście (informacyjne, od 1.49)

Zadanie człowieka z 19.10.2026: krótkotrwałe wzrosty kończą się gwałtowną zieloną świecą, po której przychodzi korekta — szukać **tylko shortów** na 10 parach walutowych (bez BTC), szczególnie EUR/USD; dostępne świece podzielone na **20 okresów** — najmniej stratnych, największa średnia / mediana, najmniejsze obsunięcie, dużo transakcji i duży zysk; Excel z kapitałem **1000 $ na dźwigni 1:30**. `ia4/fxshort.py`, świece 1h z kopii fx1h, wejście po open świecy po sygnale, rozliczenie pesymistyczne (zasada 5), spread w pipsach (zasada 5), jedna pozycja na parę.

- **Etap 1 — szerokie przeszukanie (7,6 mln reguł):** 102 sygnały wzrostu (świeca ≥ k ATR i ≥ x%, wzrost N świec w ATR i w %, kulminacja: wzrost + duża świeca, odległość od EMA20 / EMA50, RSI(2/3/14), seria zielonych, nowy szczyt z dużą świecą, potwierdzenie pierwszą czerwoną świecą, górny knot) × 24 filtry trendu dłuższej średniej (SMA100 / 200 / 500: nie rośnie mocno, płaska, spada, cena pod średnią) × 4 okna godzin × 810 wyjść (SL 0,5–5 ATR / nad szczytem świecy / bez × TP 0,5–3 ATR / 50% / 100% korpusu / bez × 1–48 świec). Wszystkie pary razem i EUR/USD osobno. Uczciwy test: **placebo** (sygnały przesunięte w czasie o ≥ 1500 świec, osobno na każdej parze), połowy danych osobno, **wybór chronologiczny** (najlepsza reguła 1. roku sprawdzona na 2. roku).
- **Etap 2:** zawężona siatka wokół rodziny, która przeszła etap 1 (28 sygnałów × 7 filtrów × 7 okien godzin × 810 wyjść), 3 placebo.
- **Strategia FX-SHORT-NY (stałe):** wzrost w ostatnich 6 świecach ≥ 3,1 × ATR(100), świeca sygnału zaczyna się 11:00–16:00 UTC, SMA500 niżej niż 24 świece wcześniej → short po open następnej świecy; SL 3 ATR, TP 0,75 ATR, najwyżej 8 świec.
- **Rachunek:** 1000 $, 1:30; depozyt pozycji = część salda (domyślnie 20% → wartość 6 × saldo), jednostki w dół do 0,01 lota, brak wolnego depozytu → pozycja mniejsza albo pominięta, stop out przy poziomie depozytu < 50% (wycena co godzinę po najgorszej cenie świecy); koszt nocny tylko w wariantach (3% rocznie — szacunek, nie dane XTB). Arkusz TRANSAKCJE liczy saldo formułami (zmiana żółtych komórek przelicza wykres), Python liczy to samo. Arkusze: PODSUMOWANIE, TRANSAKCJE, KAPITAŁ, OKRESY, PARY, WARIANTY, ODPORNOŚĆ, UCZCIWY TEST, HIPOTEZA, RANKING, EURUSD → `FX-SHORT-NY.xlsx`.

**Wyniki z 19.10.2026** (Claude, kopia fx1h 2024-10-13 – 2026-10-16, 12 598 świec na parę): *hipoteza w czystej postaci* — strata: short po każdej świecy ≥ 1–3 ATR / ≥ 0,1–0,2% albo wzroście 3–12 świec, bez filtrów, traci po spreadzie prawie przy każdym wyjściu (na 1h FX częściej trwa kontynuacja). *Etap 1:* warunek (≥ 300 transakcji, ≤ 3 stratne okresy z 20) spełnia 56 reguł na wszystkich parach wobec 5 i 1 na placebo (≤ 4 stratne: 318 wobec 10 i 3) — sygnał wzrostu niesie informację; sam EUR/USD (≥ 60 transakcji) — 7477 wobec 10 293 i 6663 na placebo, czyli poziom przypadku (za mało transakcji na jedną parę). Korekta działa tylko razem: wzrost w sesji Londyn + Nowy Jork (11–16 UTC) i spadająca SMA500 (lustro wniosku RÓWNA); wzrosty o 6–9 UTC i po 17 UTC trwają dalej; SL ≤ 1 ATR — strata, 3–5 ATR i bez SL — podobnie (jak w akcjach: „SL szkodzi”). *Etap 2:* warunek spełnia 273 reguł wobec 0–1 na placebo. *FX-SHORT-NY* (w próbie): 423 transakcje, średnio +0,031% (t = 5,2), mediana +0,065%, trafne 82%, PF 1,91, 2 okresy stratne z 20, 9 z 10 par na plusie (EUR/GBP −), 1. połowa +7,1%, 2. połowa +5,9% (1:1); 1000 $ przy 1:30: depozyt 20% → 2054 $ (obsunięcie 10,5%; z kosztem nocnym 3% — 1934 $), 10% → 1395 $ (5,0%), 33% → 2953 $ (15,7%), cały depozyt w jednej pozycji → 4449 $ (27,6%, 154 sygnały pominięte); stop out — nigdy. Sam EUR/USD: 58 transakcji, +0,016% — za mało na werdykt. *Zastrzeżenie:* reguła wybrana tylko na 1. roku zarobiła w 2. roku +0,85% (1:1, 120 transakcji, +0,007% na transakcję; przy 1:30 i 20% — +4,6%), wobec +39% FX-SHORT-NY w tym samym roku; placebo w tym teście −2 do −10%. Przewaga najpewniej istnieje, ale na żywo będzie dużo mniejsza niż w próbie; sygnały wypadają w godzinach danych z USA (12:30, 14:00 UTC — szerszy spread), świece Yahoo EUR/USD mają rozdzielczość ok. 1,3 pipsa, 2 lata to jeden reżim (słabnący dolar). Wyniki niczego nie zmieniają bez zgody człowieka.

**FX-POWRÓT (od 1.50, pomysł człowieka z 20.10.2026):** po wybiciu cena często wraca do ceny sprzed gwałtownych świec — TP na tej cenie, a wejście nie na gwałtownej świecy, tylko po sygnale zawrócenia. `ia4/fxpowrot.py`, te same dane, koszty, rozliczenie i rachunek co FX-SHORT-NY; jedna transakcja na impuls.
- **Zdarzenie:** *impuls* — wzrost N świec (1, 2, 3, 4, 6, 8, 12) ≥ k × √N × ATR(100), k = 1 / 1,25 / 1,5 / 2; *baza* — zamknięcie świecy przed impulsem albo najniższy punkt impulsu; *szczyt* — najwyższy punkt od impulsu do sygnału; *zawrócenie* — pierwszy z 11 sygnałów (pierwsza czerwona świeca, czerwona ≥ 0,5 / 1 ATR, zamknięcie pod dołkiem poprzedniej świecy / świecy szczytu, objęcie bessy, dwie czerwone, cofnięcie ≥ 24% / 38% wzrostu, górny knot ≥ 50% świecy, zamknięcie pod EMA10) w ciągu 3 / 6 / 12 świec, albo „natychmiast” dla porównania; impuls wygasa, gdy kurs wrócił do bazy albo minęło okno.
- **Wyjścia:** TP = szczyt − f × (szczyt − baza), f = 0,5 / 0,75 / 1 (cena sprzed wzrostu) / 1,25 albo bez TP; SL nad szczytem (+0,1 / 0,5 / 1 ATR), od wejścia (1 / 2 / 3 ATR) albo bez; 6–96 świec. Filtry: SMA500, godzina świecy sygnału, odległość wejścia od bazy ≥ 0,5 / 1 / 2 ATR. Razem ok. 8,9 mln reguł; placebo — te same transakcje z tym samym „nawiasem” (baza, szczyt, TP, SL w ATR) w losowym czasie; wybór chronologiczny.
- **Strategia FX-POWRÓT (stałe):** świeca zamyka się ≥ 2 ATR(100) wyżej niż poprzednia; pierwsza czerwona świeca w ciągu 3 świec, świeca sygnału 7–16 UTC → short po open (open ≥ 0,5 ATR nad bazą); TP w połowie drogi od szczytu do ceny sprzed wzrostu; bez SL; najwyżej 96 świec. Arkusze jak FX-SHORT-NY oraz POWRÓT DO BAZY → `FX-POWROT.xlsx`.

**Wyniki FX-POWRÓT z 20.10.2026** (Claude, ta sama kopia fx1h): *jak często cena wraca* — po świecy ≥ 2 ATR do bazy w ciągu 96 świec w 71% przypadków, ale w 80% najpierw przebija szczyt o 0,5 ATR (w ciągu doby), a przed nowym szczytem — tylko 24%; dlatego short z SL nad szczytem traci, a TP dokładnie na cenie sprzed wzrostu daje +0,033% na transakcję przy 9 stratnych okresach z 20 (1. połowa na minusie). *Działa połowa drogi:* FX-POWRÓT — 363 transakcje, średnio +0,064% (t = 7,0), mediana +0,065%, trafne 90%, PF 3,6, 2 stratne okresy z 20, obie połowy i wszystkie 10 par na plusie, najgorsza transakcja −1,37%, mediana 2 świece w pozycji; płaskowyż: świeca ≥ 1,75–3 ATR i okno 1–3 świec — t 5,6–8,6; wejście od razu po świecy — t 2,4; impuls z 3–12 świec — słabo; każdy SL obniża wynik (SL nad szczytem — strata, 6–8 ATR od wejścia — ok. połowa zysku). 1000 $ przy 1:30: depozyt 20% → 3634 $ (obsunięcie 21%; z kosztem nocnym 3% — 3204 $), 10% → 1825 $ (10%), 33% → 7651 $ (35%); stop out — nigdy. Sam EUR/USD: 53 transakcje, +0,062%, 94% trafnych. *Uczciwy test:* liczba reguł spełniających warunek okresów nie odróżnia od przypadku (765 wobec 7–769 na 11 placebo — zależy od trendu walut), ale najlepsze t 8,1 wobec 2,8–5,6 na placebo, reguł z t ≥ 5: 45 wobec 0–6; reguła wybrana wyłącznie na 1. roku (wzrost 3 świec, cofnięcie 38%, TP 50%, bez SL) zarobiła w 2. roku +12,7% przy 1:30 i 20% (FX-POWRÓT w tym roku w próbie +77%; FX-SHORT-NY w tym teście +4,6%). Przewaga mocniejsza niż FX-SHORT-NY, na żywo spodziewana dużo mniejsza niż na krzywej; ryzyka: brak SL i do 4 dni w pozycji (koszt nocny, luka weekendowa). Wyniki niczego nie zmieniają bez zgody człowieka.


**FX-ODKRYWCA (od 1.51, zadanie człowieka z 20.10.2026):** zamiast pojedynczych pomysłów — algorytm przelicza miliony sygnałów i wyjść, wybiera serię 100 najlepszych strategii **wyłącznie na roku 1** (do 15.10.2025) wg 4 kryteriów człowieka (wzrost, liczba wystąpień, obsunięcie, konsekwencja) i raz przelicza je w **skarbcu** (rok 2). `ia4/fxodkrywca.py`, te same dane, spread i rozliczenie co FX-SHORT-NY.

- **Przeszukanie:** 92 cechy świecy 1h (ruch, kształt, położenie w zakresie, średnie, oscylatory, zmienność, sesje, siła walut, BTC, kalendarz) → 700 warunków „cecha ≤ / ≥ próg” (progi z kwantyli roku 1) → wejście = 1–4 warunki naraz, long albo short → 267 wyjść (SL / TP w ATR, limit świec, stop kroczący, cel EMA20, koniec sesji NY). Etapy 1–2 — wszystkie kombinacje 1–2 warunków; 3–4 — najlepsze + jeden warunek, szerokość wg budżetu `--godziny` (domyślnie 3 h, wszystkie rdzenie). Pula: ≥ 30 transakcji, zysk, PF ≥ 1,15, t ≥ 2, ≥ 6 z 10 okresów na plusie. Ocena = średnia percentyli 4 kryteriów; seria — bez powtórzeń wejścia, ≤ 50% wspólnych transakcji. Druga seria tylko z wyjściami z SL. Rzadkie strategie (od 30 transakcji) grają razem: portfel 10 / 25 / 50 / 100 strategii naraz, 1000 $, 1:30.
- **Uczciwy test (zasada 4):** obie serie i grupy porównawcze (100 losowych z puli, 100 najlepszych wg t, losowe wg liczby warunków) są zamrażane przed otwarciem skarbca; każde otwarcie — `data/fxodkrywca/skarbiec.jsonl` i arkusz SKARBIEC. Arkusze → `FX-ODKRYWCA.xlsx` (PRZEWODNIK.md).

**Wyniki FX-ODKRYWCA z 20.10.2026** (Claude, chmura, 2 rdzenie, 40 min; ta sama kopia fx1h): policzono 1,0 mld reguł (3,8 mln reguł wejścia × 267 wyjść), w puli 7,8 mln. *Seria 100:* w roku 1 wszystkie 100 na plusie, średnio +13,7% na strategię (t do 42 — prawie same shorty bez SL z TP 1 ATR); w skarbcu 10 ze 100 na plusie, średnio −3,5%, −0,026% na transakcję. *Porównanie w skarbcu:* 100 losowych z puli −1,8%, 100 najlepszych wg t −0,3%, seria z SL −7,0% (20 na plusie) — **wybór na roku 1 nie przenosi się na rok 2** (korelacja rang ocena ↔ skarbiec 0,03), a strata na transakcję ≈ spread, czyli przewaga przed kosztami ≈ 0. Portfel 1000 $, 1:30, 5% depozytu: rok 1 — 7 133 $ (10 strategii) do 722 000 $ (100); skarbiec — 727 $ (−27%) do 246 $ (−75%). *Zastrzeżenia:* skarbiec w chmurze otwarto 3 razy (2 testy, 1 pełny); cechy projektował Claude po obejrzeniu obu lat (1.49–1.50); czysty sprawdzian to dopiero świece po 16.10.2026. Wniosek: ślepe przeszukiwanie na roku 1h FX nie daje przewagi — wąskie hipotezy człowieka (FX-POWRÓT) wypadły lepiej. Żadnej strategii nie wolno wybierać z wyników skarbca. Wyniki niczego nie zmieniają bez zgody człowieka.


**FX-POWRÓT v2 i doubleProof FX (od 1.52, pytanie człowieka z 20.10.2026):** skąd biorą się stratne transakcje FX-POWRÓT i czy da się je uciąć (np. krótszym czasem trzymania, skoro zyskowne zamykają się szybko); potem sprawdzian na 10 nowych parach. `ia4/fxpowrot2.py`, wejście bez zmian.

- **Wyniki analizy z 20.10.2026** (Claude, 10 par, 363 transakcje v1): stratnych 35 — 16 to limit 96 świec (−8,8% z −9,0% wszystkich strat; kurs nie wrócił), 19 to TP trafiony od razu, ale cel bliżej niż spread (pewna strata ok. −0,01%). Zyskowne: mediana 2 świece, ale transakcje trzymane 13–48 świec też wygrywają w 97–100%. **Cięcie czasem szkodzi:** po k świecach trzymanie do końca jest średnio lepsze od zamknięcia (k = 6: +0,04% wobec −0,18%; k = 24: −0,05% wobec −0,29%; przewaga trzymania znika dopiero ok. 60 świec); limit 6 / 12 / 24 / 48 świec daje t −0,4 / 1,0 / 2,7 / 5,9 wobec 7,0. Nie pomagają też: SL 2–6 ATR, stop na wejściu, zamykanie przed weekendem, cel ≤ 1–2 ATR, wyjście warunkowe. Długie transakcje to te z daleką bazą (wejście ≥ 3,5 ATR nad bazą) — ale tam jest też największy średni zysk; żadna cecha wejścia nie odcina ich bez straty zysku.
- **v2 (zamrożona 20.10.2026, przed pobraniem par doubleProof):** jak FX-POWRÓT, ale bez transakcji, gdy do TP < 1 × spread, i najwyżej 60 świec. W próbie: 345 transakcji, średnio +0,066% (t = 7,6), trafne 94%, najgorsza −1,20%, 1 stratny okres z 20; 1000 $, 1:30, 20% → 3591 $ (obsunięcie 18%; v1: 3636 $, 21%). To niemal ten sam wynik co v1 — zmiana porządkowa, nie nowa przewaga.
- **doubleProof FX:** v1 i v2 raz na 10 parach fx1h_double_proof (spread — szacunek dla XTB, 1,9–3,6 pipsa, do potwierdzenia zrzutem). **Warunek zaliczenia v2 ustalony przed testem: ≥ 30 transakcji, średnia netto > 0, t ≥ 2.** Każde otwarcie — `data/fxpowrot2/doubleproof.jsonl` i arkusz DOUBLEPROOF. Nowe pary to krzyżówki walut z badania (np. EUR/CHF ≈ EUR/USD × USD/CHF) — test niezależny w danych, ale nie w walutach. Arkusze → `FX-POWROT-V2.xlsx` (PRZEWODNIK.md). Wyniki niczego nie zmieniają bez zgody człowieka.


**Powrót.v2 Investor (od 1.53, decyzja człowieka z 20.10.2026):** paper trading strategii v2 w Apps Script (`PowrotV2.gs`), od chwili wdrożenia, 100 $. Reguły — dokładnie v2 (powyżej), te same funkcje liczy test zgodności z Pythonem: `python tests/pv2_parity_dump.py /tmp/pv2.json && node tests/pv2_parity.js /tmp/pv2.json` → „rozbieżności: 0” (20.10.2026: 345 = 345 transakcji) i test pracy na żywo `node tests/pv2_live.js /tmp/pv2.json` → „WYNIK: OK” (krok po każdej świecy = symulacja; 5 miesięcy: 71 = 71 transakcji, 100 $ → 124,80 $).
- **Kiedy:** po każdej nowej świecy 1h dziesięciu par (Fx.gs → `pv2IfDue_`), ok. 1 min po zamknięciu świecy. Świece — ostatnie 820 każdej pary w ukrytym arkuszu `_PV2_DANE` (Firestore `fx1h`, 3 dni na parę przy każdym kroku); sygnały sprzed przerwy w pracy nie są nadrabiane.
- **Rachunek:** żółte komórki u góry zakładki **Powrót.v2.Investor**: kapitał startowy (100 $), depozyt na pozycję (20% salda), dźwignia (1:30), adres i włączniki maili, inwestor aktywny. Wartość pozycji = depozyt × dźwignia, bez zaokrąglania do 0,01 lota (przy 100 $ pozycja ok. 0,006–0,008 lota — mail ostrzega, ile depozytu wymagałoby 0,01 lota XTB); jedna pozycja na parę; stop out < 50% depozytu. Log transakcji jak VIRTUAL-INVESTOR (otwarte i oczekujące na górze). Menu: przelicz teraz, mail testowy, zacznij od nowa.
- **Maile** (`MailApp`, na adres z arkusza; domyślnie konto właściciela): **uprzedzenie** (od 1.54; „UWAGA … możliwy sygnał o HH:00” — gdy po gwałtownym wzroście świeca, która właśnie się zaczęła, może dać sygnał: domyślnie 15 min po zamknięciu poprzedniej świecy, z przedziałem zamknięcia, przy którym sygnał powstanie, i ceną z Yahoo w tej chwili; na historii 10 par każda z 345 transakcji miała uprzedzenie, a sygnałem kończy się ok. 36% uprzedzeń, ok. 10 na tydzień; włącznik i minuty w żółtych komórkach), **sygnał** po zamknięciu świecy (para, SHORT, TP, depozyt, wartość i lot, termin limitu), **anuluj** (gdy na otwarciu następnej świecy wejście przestało spełniać warunki), **zamknij** (limit 60 świec albo stop out); przy TP — tylko po włączeniu. Kurs w mailu to zamknięcie świecy sygnału; inwestor liczy wejście po open następnej świecy (jak Python).
- **Częściowe zamknięcie (pytanie człowieka z 20.10.2026, Claude, 10 par, wejścia v2):** 50% na TP, reszta z celem 2–5 × odległość TP i SL na wejściu (limit 60–240 świec). Wynik zależy od tego, co było pierwsze w świecy z TP — szczyt (powrót do wejścia) czy dołek; świeca 1h tego nie mówi. Rozliczenie pesymistyczne (zasada 5: SL i TP w jednej świecy — SL): średnio +0,028 do +0,035% na transakcję (v2: +0,066%), reszta wraca do wejścia w 80–86%. Przy założeniu drogi świecy (czerwona: otwarcie → szczyt → dołek, zielona: otwarcie → dołek → szczyt): +0,064 do +0,075%, ale t 6,4–7,2 (v2: 7,6), trafne 88–93% (v2: 94%), mediana 4–8 świec w pozycji (v2: 2). Wniosek: brak pewnej przewagi, wg zasady 5 — gorzej; v2 bez zmian.
- **Strona:** od 1.55 trzy tryby — **przegląd** (na żywo, jak w 1.53), **historia** (wykres wybranej pary po całych 2 latach: przeciąganie, kółko, przybliżenie, pasek całości ze znacznikami transakcji, „‹ transakcja ›”, filtr: wszystkie / stratne / zyskowne / limit czasu / inwestor, tabela — kliknięcie przewija wykres) i **galeria** (każda transakcja z filtra na własnym wykresie, sortowanie, „pokaż w historii”). Pełną historię zapisuje Mac: `python -m ia4.fxpowrot2 --strona` (świece 10 par i wszystkie transakcje v2 → branch `fx`, `fx/pv2/`; robi to też zwykłe `python -m ia4.fxpowrot2`); nowsze świece i transakcje dokłada `telemetry/pv2.json`. Dawniej: `telemetry/pv2.json` (ostatnie 300 świec każdej pary, pozycje, symulacja tych samych reguł na tych świecach) → FX → Powrót.v2. To paper trading do obserwacji, nie zalecenie; ocena — nie przed 30 transakcjami (zasada 6).


**FX-POWRÓT v3 — analiza strat i ulepszeń (od 1.57, pytanie człowieka z 21.10.2026):** `ia4/fxpowrot3.py`, te same dane i rozliczenie co v2; reguły v2 bez zmian.

- **Stratne (Claude, 21.10.2026, 10 par, 345 transakcji):** 21 (6%), wszystkie po limicie 60 świec. Ok. 25 cech wejścia (wybicie z zakresu, trend, zmienność, kształt impulsu, ruch tej samej waluty na innych parach, godzina, dzień) ich nie odróżnia; częściej tracą sygnały późne (2.–3. świeca) i z dalekim celem — ale dalekie cele zarabiają najwięcej (górna ćwiartka +0,15% na transakcję).
- **Sygnał „razem”** (w tej samej świecy sygnał daje też inna para z tą samą walutą — cała waluta zawraca): +0,10% na transakcję, 5 strat na 181 (najgorsza −0,65%); samotny: +0,03%, 16 strat na 164. Oba lata (razem +0,13% / +0,07%, samotne +0,03% / +0,03%), permutacja p < 0,0001, na zdarzeniach (transakcje powiązane walutą jako jedna) p = 0,0003. **Na rachunku v2 zostaje najlepsza:** samotne są dodatnie i wypadają w innym czasie; „tylko razem” daje mniej zysku przy tym samym obsunięciu (18,6% przy depozycie 20% — 2–3.04.2025, cła w USA, kilka shortów przeciw dolarowi naraz, potem wszystkie TP). Limit pozycji na walutę zmniejsza obsunięcie i zysk po równo.
- **Warianty:** wyjście przy zamknięciu nad szczytem / nowym impulsie, luźniejsze wejście — gorzej; limit 0,2–0,3 ATR nad otwarciem — t 8,1–8,3 przy o 12–17% mniejszej liczbie transakcji; sygnał tylko na 1. świecy — 0 stratnych okresów, o 1/3 mniej transakcji. Dokładanie jednostki przy + 2 ATR — najlepszy rachunek w próbie (zysk / obsunięcie 26,6 wobec 15,2), ale to uśrednianie bez SL: ryzyko podwójnej straty, gdy kurs nie wróci — tylko po doubleProof i za zgodą człowieka.
- **doubleProof v3** (`--double-proof`, otwarcia w `data/fxpowrot3/doubleproof.jsonl`; warunki ustalone 21.10.2026): efekt — średnio „razem” > samotne (każda grupa ≥ 15 transakcji); v3 „tylko razem” — ≥ 30 transakcji, średnia > 0, t ≥ 2. Arkusze → `FX-POWROT-V3.xlsx` (PRZEWODNIK.md). Wyniki niczego nie zmieniają bez zgody człowieka.

---

## 8. AI Investor — zespół agentów (Etap 6)

Działa tylko na Macu, gdy uruchomiono **`ia4 start`** (albo dwuklik `IA4-start.command`). Model: Ollama `qwen2.5:14b` (lokalnie, `num_ctx` 8192). Agenci tylko czytają Firestore.

### 8.1 Dyspozytor — jeden agent naraz, bez przerwy

Laptop ma jeden model i ograniczoną pamięć, więc **w każdej chwili pracuje najwyżej jeden agent**. Dyspozytor wybiera następne zadanie w kolejności:

1. **Agent-Investor** — runda po każdej nowej świecy (akcje: po każdej świecy sesji; FX: co godzinę). Nowa świeca czeka najwyżej na koniec bieżącego zadania.
2. **Krytyk** — przegląd po 4 rundach Inwestora z modelem albo po 60 min (gdy coś się wydarzyło), od razu przy ≥ 3 hipotezach „do oceny”.
3. **Badacz** — w każdym pozostałym czasie, z przerwą 20 s między cyklami (Air nie ma wentylatora).

Każde zadanie jest zapisywane (agent, zadanie, start, czas, czas modelu, wynik) — strona pokazuje, jak często i jak długo pracują agenci (panel „praca agentów”).

### 8.2 Agent-Investor — tryb nauki

- Papierowy portfel **100 000 $**: 53 spółki handlowane, 10 par walutowych, BTC; long i short. Decyzja na świecy t → wykonanie po open następnej świecy; świece z czasu, gdy Mac był wyłączony, służą tylko do rozliczenia pozycji.
- **Model jest wołany w każdej rundzie**, także bez kandydatów. Kandydaci (kod): sygnały 60 strategii z playbooka, sygnały hipotez Badacza w „próbie”, prognoza FX z udowodnioną przewagą. Inwestor decyduje `enter` / `skip` (pominięcie — z konkretnym powodem), zarządza pozycjami (`hold`, `close`, zacieśnienie SL) i zgłasza **własne pomysły** — każdy z ceną SL i TP, limitem świec i **hipotezą** (co ta transakcja sprawdza).
- **Poziom nauki 0–3** (ustawia Krytyk, start 1):

  | Poziom | Własne pomysły na rundę | Mnożnik ryzyka własnego pomysłu | Wymagane wejście |
  |---|---|---|---|
  | 0 ostrożnie | 1 | 0,25 | — |
  | 1 normalnie | 2 | 0,25 | — |
  | 2 śmielej | 2 | 0,35 | — |
  | 3 nauka wymuszona | 3 | 0,5 | co najmniej 1 w rundzie |

  **Automat bierności:** 6 rund z rzędu bez wejścia → poziom co najmniej 2; 12 → poziom 3.
- **Ryzyko — limity egzekwowane przez kod:**

  | Limit | Wartość |
  |---|---|
  | ryzyko na transakcję (strata na SL z kosztami) | 0,5% stanu konta × mnożnik (strategia „wybrana” 1,0, pozostałe 0,5; hipoteza w próbie 0,25, zatwierdzona 0,5; prognoza FX 0,5; własny pomysł wg poziomu nauki) |
  | pozycje otwarte i oczekujące | najwyżej 12; 1 na instrument |
  | wartość pozycji | akcje i BTC ≤ 20% stanu konta, para walutowa ≤ 50%; ekspozycja brutto ≤ 200% |
  | budżet ryzyka | 6% stanu konta; własne pomysły łącznie ≤ 2% |
  | stop dzienny | wynik doby UTC ≤ −2% → bez nowych wejść do końca doby |
  | obsunięcie od szczytu | ≥ 10% → ryzyko o połowę; ≥ 20% → bez nowych wejść do decyzji człowieka (`ai/config.json` → `halt_ack`) |

  Własny pomysł: SL co najmniej 1 × ATR14, TP/SL od 1:3 do 3:1, limit 1–120 świec. SL wolno tylko zacieśniać.
- **Koszty** (wynik zawsze netto): akcje 0,005% przy wejściu i wyjściu; pary walutowe — spread 0,8–2,5 pipsa na transakcję; BTC 0,05% przy wejściu i wyjściu.

### 8.3 Krytyk — weryfikacja i nauka

Brief (kod): rundy, wejścia i pominięcia, **wynik pominiętych kandydatów** (księga cieni: każdy kandydat bez limitów), własne pomysły z hipotezami i wynikiem, kalibracja pewności, hipotezy Badacza „do oceny” i „w próbie”, wnioski. Krytyk odpowiada: poziom nauki (kod zmienia go najwyżej o 1 na przegląd), uwagi dla Inwestora i Badacza (po 3), werdykty hipotez, wnioski do dodania i usunięcia (najwyżej 50 aktywnych). Kod sprawdza werdykty: „próba” tylko dla „do oceny” i najwyżej 6 naraz; „zatwierdzona” albo „wycofana” — dopiero po **20 transakcjach na żywo**, zatwierdzenie tylko przy średniej > 0.

### 8.4 Badacz — hipotezy z klocków

- Model proponuje 1–3 hipotezy: rynek (FX albo akcje), kierunek, **1–3 warunki „cecha op wartość” wyłącznie z menu** (zmiany ceny w ATR, korpus, RSI, odległość i nachylenie średnich, położenie w zakresie, reżim zmienności, seria świec, godzina, dzień tygodnia, numer świecy) i wyjście w wielokrotnościach ATR14 (SL, TP, limit 2–120 świec). Brief podaje typowe wartości każdej cechy i wyniki poprzednich hipotez — Badacz uczy się na nich.
- Python liczy hipotezę na historii: pesymistycznie (zasada 5), **z kosztami**, w 4 częściach kalendarza, obok wejścia na ślepo (każda świeca, to samo wyjście). **Sito kodu:** ≥ 60 transakcji, średni wynik netto > 0 i lepszy niż na ślepo, PF ≥ 1,15, t ≥ 2,0, dodatni wynik w ≥ 3 z 4 części. Powtórzona hipoteza nie jest liczona drugi raz.
- **Droga hipotezy:** odrzucona przez kod → **do oceny** → Krytyk: **próba** (Inwestor dostaje jej sygnały na żywo, mnożnik 0,25) / odrzucona / do poprawy → po 20 transakcjach na żywo: **zatwierdzona** (mnożnik 0,5) albo **wycofana**; kod sam wycofuje po 30 transakcjach ze średnią ≤ 0.
- **Sejf AI:** Badacz nigdy nie widzi 20 spółek doubleProof ani świec FX sprzed 2025-04-01 (odcinane przed liczeniem). Przy setkach prób część wyników „do oceny” to przypadek — prawdziwym testem jest próba na żywo.

### 8.5 Ocena i zapis

- **Punkty odniesienia** (po każdej rundzie): wszyscy kandydaci (cienie), losowy wybór (200 losowań), mechaniczny inwestor, SPY kup i trzymaj; kalibracja pewności. Werdykt dopiero po 30 transakcjach.
- **Hub** `ia4-research/data/ai/hub.sqlite` — pamięć robocza; **branch `ai`** — trwała historia (transakcje, decyzje, cienie, hipotezy, przeglądy, praca agentów, wnioski, playbook); pusty hub odtwarza się z brancha sam. **`ai-live/status.json`** — stan na żywo dla strony. **`~/Desktop/IA4/AI-INVESTOR.xlsx`** — transakcje, decyzje, portfel, dziennik, playbook, hipotezy, przeglądy.
- Ustawienia: `ia4/ai/config.py` (wartości z tej sekcji); nadpisania tylko w `ai/config.json` na branchu `ai` — zmienia człowiek z Claude.
- Przy działającym `ia4 start` nie uruchamia się osobno `ia4.lab`, `ia4.fx.research` ani `ia4.fx.live` (pamięć Maca; blokada w kodzie).

---

## 9. Strona IA4

`https://miszyszka.github.io/IA4/` — GitHub Pages z `main/docs`, bez buildu i bibliotek, hasło w przeglądarce (bramka nie chroni danych — wszystkie są w publicznym repo, więc nigdy żadnych sekretów w danych strony). Zakładki: **System** (czy działa zbieranie), **Inwestor** (mechaniczny inwestor), **FX** (prognoza; przycisk **Powrót.v2** — wykres każdej z 10 par z transakcjami inwestora i symulacji, `#fx/powrot`), **AI** (agenci: praca agentów, portfel, Krytyk, Badacz). Pasek „magistrala” pokazuje każde ogniwo drogi danych z wiekiem ostatniego znaku życia. Każdy panel ma opis „?”, nagłówek — przycisk „przewodnik”. Teksty nie są ucinane — zawijają się. Jak dodać zakładkę albo źródło: `docs/README.md`.

---

## 10. Praca z Claude, wdrożenie, uruchamianie

**Claude na początku rozmowy** pobiera repo, czyta ten plik i `telemetry/state.json`, a w razie potrzeby: `research/status.json`, `ai-live/status.json`, końcówki `ai/reviews.jsonl` i `ai/decisions.jsonl`, `fx/runs.jsonl`. Potem sprawdza otwarte kroki (sekcja 0).

**Claude przygotowuje zmiany** jako commit w pliku `.bundle` (zapisany w `~/Downloads`), sprawdzone przed wysłaniem (selftesty, test zgodności, składnia `.gs`, zrzuty strony), i podaje polecenia:

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

Pracę wykraczającą poza tę instrukcję albo zmianę instrukcji Claude najpierw proponuje i czeka na zgodę. Claude nie ma dostępu do arkusza ani edytora Apps Script.

**Aktualizacja Apps Script:** podmienić pliki `.gs` z pakietu (najprościej wszystkie 8; nowy plik: „+ → Skrypt”) i — gdy się zmienił — manifest `appsscript.json`, zapisać. „⚙️ Konfiguruj i włącz automat” — tylko gdy Claude o to poprosi (zmiana listy instrumentów, STATS albo triggerów).

**Mac — polecenia** (`cd ~/Desktop/IA4/ia4-research && source .venv/bin/activate`):

```bash
ia4 start                          # agenci AI + prognoza FX (Ctrl+C kończy); noc: laptop otwarty, na zasilaczu
python -m ia4.ai.selftest          # test agentów — „WYNIK: OK”
python -m ia4.ai.replay            # test silnika portfela na historii
python -m ia4.lab.selftest         # test silnika reguł
python -m ia4.fx.selftest          # test modułu FX
python -m ia4.fx.research          # przeliczenie okoliczności FX (ręcznie, bez ia4 start)
python -m ia4.daily                # kopia świec dobowych
python -m ia4.odsearch [--source daily]   # badania One-Day — pojedyncze reguły
python -m ia4.odport                # badania One-Day — portfel strategii walk-forward (10–20 min)
python -m ia4.odbreak               # badania One-Day — siła ruchu po konsolidacji, long + short naraz
python -m ia4.swtrend               # badania wielodniowe — strategie jednokierunkowe z SL i TP (ok. 6 min)
python -m ia4.swrsi                 # badania wielodniowe — strategia RSI(3) / EMA100 / VWAP10: QQQ i wszystkie spółki
python -m ia4.swserie               # badania wielodniowe — mapa: wejście po serii świec, 1/2/3 sesje, 1:5
python -m ia4.swportfel             # badania wielodniowe — portfel: long po 7 świecach spadkowych, 3 sesje, 1:5 (--n, --hold)
python -m ia4.swportfel --propozycja   # ≥ 5 spadków, spadek ≥ 10%, słaby rynek, 5 sesji, max 5 pozycji (--min-n, --min-drop, --rynek, --max-poz)
python -m ia4.swrowna               # strategia RÓWNA: QQQ RSI(3) wg zmienności + kapitulacja spółek tylko w trendzie (--skala 1.5)
python -m ia4.fxshort               # FX: short po gwałtownym wzroście — przeszukanie, placebo, FX-SHORT-NY, 1000 $ na 1:30 (--depozyt 0.33)
python -m ia4.fxpowrot              # FX: impuls → zawrócenie → TP w stronę ceny sprzed wzrostu — 8,9 mln reguł, placebo, FX-POWRÓT
python -m ia4.fxodkrywca            # FX: poszukiwanie na 1. roku → seria 100 → skarbiec (2. rok) → FX-ODKRYWCA.xlsx; ok. 3 h (--godziny)
python -m ia4.fxpowrot2             # FX-POWRÓT v2: analiza strat + doubleProof na 10 nowych parach → FX-POWROT-V2.xlsx
python -m ia4.fxpowrot3             # FX-POWRÓT v3: stratne transakcje, sygnał „razem”, warianty, rachunek → FX-POWROT-V3.xlsx (--double-proof)
```

`ia4` to funkcja w `~/.zshrc`: `function ia4 { cd ~/Desktop/IA4/ia4-research && source .venv/bin/activate && if [ "$1" = start ]; then shift; python -m ia4.ai "$@"; else python -m ia4.lab --workers 4 "$@"; fi; }`

---

## 11. Dziennik zmian

Starsze wpisy: `archiwum/IA4_INSTRUKCJA-1.40.md`, sekcja 13, i historia gita.

| Wersja | Data | Zmiana |
|---|---|---|
| 1.57 | 2026-10-21 | **FX-POWRÓT v3 — analiza strat** (`ia4/fxpowrot3.py`, sekcja 7b; pytanie człowieka z 21.10.2026): cechy stratnych transakcji, sygnał „razem” (inna para z tą samą walutą w tej samej świecy) na transakcjach i zdarzeniach, warianty (unieważnienie, dokładanie, limit, luźniejsze wejście), rachunek przy tym samym ryzyku, największe obsunięcie, doubleProof v3 → `FX-POWROT-V3.xlsx`. Reguły v2 i Powrót.v2 Investor bez zmian. Usunięty `ia4/fxkanal.py` (1.56). README, `PRZEWODNIK.md`. Pozostałe pliki — tylko numer wersji. |
| 1.56 | 2026-10-21 | FX-KANAŁ (`ia4/fxkanal.py`): short przy górnej / long przy dolnej linii kanału — 5,64 mln reguł; kanał rysowany na gotowym wykresie zna przyszłość, liczony na żywo nie daje przewagi przenoszącej się na rok 2 (stabilnych reguł 130 wobec 37–40 na placebo, wybór na roku 1 w roku 2 na minusie). Wycofane w 1.57 na prośbę człowieka (21.10.2026). |
| 1.55 | 2026-10-21 | **Powrót.v2 na stronie — historia i galeria** (sekcja 7b; prośba człowieka z 21.10.2026): przewijanie wykresów po całych 2 latach, filtr transakcji (m.in. wszystkie stratne), galeria — każda transakcja na własnym wykresie (`docs/js/views/pv2hist.js`). Python: `fxpowrot2.publish_history` / `--strona` — świece 10 par i wszystkie transakcje v2 na branch `fx` (`fx/pv2/`). README. Pozostałe pliki — tylko numer wersji. |
| 1.54 | 2026-10-20 | **Powrót.v2 — uprzedzenie** (sekcja 7b; prośba człowieka z 20.10.2026): mail „UWAGA … możliwy sygnał” ok. 15 min po zamknięciu świecy, gdy następna świeca może dać sygnał (`pv2_armed_`, `pv2_alertsDue_`; lista w Script Properties `PV2_ALERTS`), dwie nowe żółte komórki (włącznik, minuty) — arkusz z 1.53 przestawia się sam. Analiza częściowego zamknięcia (50% na TP, reszta 2–5 × TP, SL na wejściu) — v2 bez zmian. `tests/pv2_live.js` sprawdza też uprzedzenia. Pozostałe pliki — tylko numer wersji. |
| 1.53 | 2026-10-20 | **Powrót.v2 Investor** (sekcja 7b; decyzja człowieka z 20.10.2026): nowy plik `PowrotV2.gs` — paper trading FX-POWRÓT v2 od wdrożenia (100 $, parametry w żółtych komórkach zakładki **Powrót.v2.Investor**, log transakcji), maile z sygnałem / anulowaniem / zamknięciem (zakres `script.send_mail` w `appsscript.json`), `telemetry/pv2.json`; menu (3 pozycje); `Fx.gs` woła `pv2IfDue_`. Testy `tests/pv2_parity_dump.py` + `pv2_parity.js`, `tests/pv2_live.js`. Strona: FX → przycisk **Powrót.v2** (`docs/js/views/pv2.js`, źródło `pv2`). `PRZEWODNIK.md`. Pozostałe pliki — tylko numer wersji. |
| 1.52 | 2026-10-20 | **FX-POWRÓT v2** (`ia4/fxpowrot2.py`, sekcja 7b; pytanie człowieka z 20.10.2026): analiza stratnych transakcji (czas trzymania, ok. 40 wariantów wyjścia, cechy wejścia), v2 zamrożona, warunek doubleProof → `FX-POWROT-V2.xlsx`. **fx1h_double_proof** (sekcja 4): 10 nowych par w `Fx.gs` i `ia4/fx/instruments.py` (arkusz FX dopisuje kolumny zamiast czyścić); `ia4.fx.sync.sync()` domyślnie bez nich (prognoza, badania, agenci AI), `python -m ia4.fx.sync` kopiuje wszystkie. `PRZEWODNIK.md`, README. Pozostałe pliki — tylko numer wersji. |
| 1.51 | 2026-10-20 | **FX-ODKRYWCA** (`ia4/fxodkrywca.py`, sekcja 7b; zadanie człowieka z 20.10.2026): automatyczne przeszukanie (92 cechy, 700 warunków, 1–4 naraz, long i short, 267 wyjść) wyłącznie na roku 1, seria 100 wg 4 kryteriów i seria z SL, grupy porównawcze, zamrożenie przed skarbcem z dziennikiem otwarć, portfel wielu strategii 1000 $ na 1:30 → `FX-ODKRYWCA.xlsx`; wynik: wybór nie przenosi się na rok 2. `.gitignore` — pliki `FX-*.xlsx`. `PRZEWODNIK.md`, README. Pozostałe pliki — tylko numer wersji. |
| 1.50 | 2026-10-20 | **FX-POWRÓT** (`ia4/fxpowrot.py`, sekcja 7b; pomysł człowieka z 20.10.2026): impuls → sygnał zawrócenia → short z TP w stronę ceny sprzed wzrostu; 8,9 mln reguł, placebo z tym samym nawiasem w losowym czasie, wybór chronologiczny, statystyka powrotów do bazy, strategia FX-POWRÓT, rachunek 1000 $ na 1:30 → `FX-POWROT.xlsx`. `fxshort.simulate`: limit straty z kolumny transakcji (`cap`). `PRZEWODNIK.md`, README. Pozostałe pliki — tylko numer wersji. |
| 1.49 | 2026-10-19 | **FX — short po gwałtownym wzroście** (`ia4/fxshort.py`, sekcja 7b; zadanie człowieka z 19.10.2026): przeszukanie 7,6 mln reguł shortów na 10 parach (20 okresów, placebo, wybór chronologiczny), zawężona siatka, strategia FX-SHORT-NY, rachunek 1000 $ na 1:30 z formułami w arkuszu → `FX-SHORT-NY.xlsx`. Zasada 5 — spread FX w pipsach (EUR/USD 1,1 ze zrzutu XTB). `PRZEWODNIK.md` — opis pliku. Pozostałe pliki — tylko numer wersji. |
| 1.48 | 2026-10-17 | **Strategia RÓWNA** (`ia4/swrowna.py`, sekcja 7a; cel człowieka z 17.10.2026 — równa krzywa kapitału, bez strat w bessie): QQQ RSI(3) z wielkością pozycji wg zmienności + kapitulacja spółek tylko przy rosnącej EMA100 SPY; arkusze z wynikiem w bessach, częściami osobno i odpornością → `SWING-ROWNA.xlsx`. `swing.portfolio`: `size` w transakcji, `max_by_label`. Pozostałe pliki — tylko numer wersji. |
| 1.47 | 2026-10-17 | `ia4.swportfel` — **warunki z analizy zdarzeń i limit pozycji** (sekcja 7a; decyzja człowieka z 17.10.2026): `--min-n`, `--min-drop`, `--rynek`, `--max-poz`, `--propozycja` (≥ 5 spadków, spadek ≥ 10%, słaby rynek, 5 sesji, max 5 pozycji, 1:5) → `SWING-PORTFEL-PROPOZYCJA.xlsx`; arkusz ANALIZA (cechy serii w przedziałach, sprawdzian na latach < 2000 i ≥ 2013), wrażliwość dźwignia × limit pozycji, serie odrzucone w ZDARZENIA. `swing.portfolio`: limit pozycji naraz (`max_pos`, pierwszeństwo `prio`) i lista pominiętych sygnałów. Pozostałe pliki — tylko numer wersji. |
| 1.46 | 2026-10-17 | **Portfel jednej komórki mapy serii świec** (`ia4/swportfel.py`, sekcja 7a; zadanie człowieka z 17.10.2026): long po 7 świecach spadkowych na 8. sesji, 3 sesje, 1:5, 73 spółki; wykres kapitału i obsunięcia, lista obsunięć, lista wszystkich serii ze średnimi SMA50/100/200, spadkiem w R i wynikiem transakcji → `SWING-PORTFEL-7.xlsx`. `swing.portfolio` zapisuje pomniejszenie stawki transakcji. Pozostałe pliki — tylko numer wersji (także `requirements.txt` i `IA4-start.command`, pominięte w 1.45). |
| 1.45 | 2026-10-16 | **Spread 0,3% raz na transakcję we wszystkich badaniach** (decyzja człowieka z 16.10.2026; zasada 5, sekcja 7 — `--cost` domyślnie 0,3, polecenia bez `--cost 0.6`). **Badania wielodniowe** (sekcja 7a, decyzja człowieka z 16.10.2026): wspólny silnik `ia4/swing.py` (SL / TP pesymistycznie, portfel z dźwignią, depozyt 10%); `ia4/swtrend.py` — 49 920 strategii jednokierunkowych z SL i TP towarzyszących wybiciom, przewaga nad wejściem na ślepo, 20 okresów, doubleProof, placebo → `SWING-TREND.xlsx`; `ia4/swrsi.py` — reguła RSI(3) / EMA100 / VWAP10: portfel QQQ 1:1 i 1:5, każda spółka, wspólny portfel → `SWING-RSI3.xlsx`; `ia4/swserie.py` — mapa wejść po N świecach spadkowych / wzrostowych, 1/2/3 sesje, long i short, 1:5, mapa doubleProof → `SWING-SERIE.xlsx`. Pozostałe pliki — tylko numer wersji. |
| 1.44 | 2026-10-15 | One-Day — **siła ruchu po konsolidacji** (`ia4/odbreak.py`, sekcja 7; hipoteza człowieka z 15.10.2026): analiza ruchu dnia w jednostkach R (normalna dynamika każdej spółki) po 35 stanach konsolidacji / ekspansji; strategie **long + short naraz** z TP 2 albo 3 × SL i porównawczo wybicie zleceniami oczekującymi; rozliczenie pesymistyczne ze świec dobowych; 20 okresów, część A/B, doubleProof, placebo przesunięte w czasie, portfele 10 000 $; plik `ONE-DAY-WYBICIA.xlsx`. |
| 1.43 | 2026-10-15 | One-Day — **portfel strategii wybieranych krok po kroku w czasie** (`ia4/odport.py`, sekcja 7; decyzja człowieka z 15.10.2026): 82 setupy × do 3 filtrów (33) z przycinaniem — ok. 450 tys. reguł, wyniki rok po roku; co rok wybór do 20 reguł tylko na danych sprzed tego roku; portfel z głosów reguł; ocena portfela: 20 okresów / ≤ 3 stratne, doubleProof, placebo, 10 000 $; plik `ONE-DAY-PORTFEL.xlsx`. `odsearch.py`: zmienność SPY w cechach. |
| 1.42 | 2026-10-15 | One-Day (`ia4.odsearch`, sekcja 7; decyzja człowieka z 15.10.2026): **spread 0,3% na każdą transakcję** (`--cost`), wszystkie wyniki, warunek okresów, baza, placebo i portfele netto, kolumna „brutto”; skrajniejsze setupy i filtr zmienności bezwzględnej (r ≥ 2/3/4%) — 28 080 reguł kierunkowych; ✓ na doubleProof wymaga też wyniku netto > 0; zapasowe portfele #1 (long) i S1 (short) z uwagą, gdy nic nie spełnia warunku. Zasada 5 — koszty także w One-Day. Baza dobowa kompletna (75/75). Pozostałe pliki — tylko numer wersji. |
| 1.41 | 2026-10-14 | **Instrukcja-esencja** (decyzja człowieka): pełny tekst 1.40 przeniesiony do `archiwum/` jako opis techniczny, nowy krótki `PRZEWODNIK.md`. **AI — zespół agentów** (decyzja człowieka: Inwestor nie wchodził w transakcje — w 23 rundach 2 kandydatów, oba pominięte, a w rundach FX model nie był wołany): dyspozytor — jeden agent naraz, bez przerwy, każde zadanie mierzone (`agent_runs`, `ai/runs.jsonl`); **Inwestor w trybie nauki** (model w każdej rundzie, własne pomysły z hipotezą, budżet własnych pomysłów 0,6% → 2%, poziomy nauki 0–3, automat bierności); **Krytyk** (przeglądy, poziom nauki, werdykty, wnioski — wersja 1 kroku AI-4); **Badacz** (hipotezy z menu cech, liczone z kosztami walk-forward, sito, próba na żywo — wersja 1 kroku AI-3; język `ia4-hyp/1` z 1.32 zastąpiony menu cech). Strona: panel „praca agentów” (oś 24 h, rytm, czasy), panele Krytyk i Badacz, opisy „?” przy każdym panelu, przewodnik w nagłówku, teksty zawijane zamiast ucinanych. Apps Script — tylko numer wersji. |
| 1.40 | 2026-10-14 | One-Day: warunek — najwyżej 3 stratne okresy z 20 (`--max-losing`). |
| 1.39 | 2026-10-14 | One-Day: 20 okresów, baza dobowa od 2000 r., zawsze co najmniej jeden portfel short. |
| 1.38 | 2026-10-13 | Baza świec dobowych z pełną historią (`Daily.gs`, `ia4/daily.py`), poszukiwanie One-Day na bazie dobowej, reguły neutralne wobec rynku, potwierdzenie doubleProof bez rynku z progiem Bonferroniego. |
| 1.37 | 2026-10-13 | Poszukiwanie stabilnych strategii One-Day (warunek 10 okresów, doubleProof, placebo). |
