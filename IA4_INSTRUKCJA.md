# IA 4 — instrukcja projektu

**Wersja:** 1.47 · **Data:** 17 października 2026

Ten plik jest jedynym źródłem prawdy i zbiorem żelaznych zasad projektu. Jest celowo krótki: zasady, liczby ważne dla człowieka, stan. Jeśli kod, arkusz albo telemetria rozjeżdżają się z tym plikiem — obowiązuje ten plik, a rozbieżność trzeba naprawić.

- **Szczegóły techniczne** (wzory, formaty pól, kolejność zdarzeń) opisuje kod — on jest implementacją wzorcową — oraz pełna instrukcja 1.40 w `archiwum/IA4_INSTRUKCJA-1.40.md`. Numery sekcji w komentarzach kodu sprzed 1.41 (np. „8.6”, „4c.6”, „11c.7”) prowadzą do tamtego pliku. Przy sprzeczności wygrywa ten plik.
- **Jak czytać stronę i arkusze:** `PRZEWODNIK.md` (i opisy „?” na stronie).

---

## 0. Stan na dziś i otwarte kroki

| Etap | Stan |
|---|---|
| 1. Baza akcji 1h (75 spółek) | ✅ działa bez końca |
| 2. Poszukiwanie strategii | ⏸ wstrzymane od 3.10.2026 — 60 aktywnych strategii |
| 3. Paper trading (mechaniczny inwestor) | 🟨 działa od 6.10.2026 |
| 4. FX 1h: zbieranie 10 par + BTC i prognoza rozkładu | 🟨 zbieranie działa; prognoza H-002 — kierunek bez przewagi |
| 5. Strona IA4 | 🟨 działa, rozwijana na prośbę |
| 6. AI Investor — agenci na Macu | 🟨 1.41: zespół agentów (Inwestor, Krytyk, Badacz), tryb nauki |
| Baza świec dobowych (pełna historia) | ✅ 75/75 od 15.10.2026 (najstarsza świeca 1970-01-02), aktualizacja codziennie po sesji |

**Otwarte kroki** (Claude odhacza je na podstawie telemetrii i branchy):
1. **Wdrożenie 1.41–1.42:** wypchnąć pakiety; Apps Script — podmienić 7 plików `.gs` (zmienia się tylko numer wersji; 15.10.2026 telemetria: `1.38`); Mac — `git pull`, `python -m ia4.ai.selftest` („WYNIK: OK”), ponownie `ia4 start`.
2. **AI, pierwsza doba 1.41:** panel „praca agentów” — zajętość ≥ 70%, Inwestor wchodzi w transakcje (pierwsza transakcja z notatką, SL i TP zamyka krok AI-2), Krytyk pisze przeglądy, Badacz zapisuje hipotezy.
3. **Badania wielodniowe (1.45):** One-Day (1.35–1.44) — bez przewagi po spreadzie: pojedyncze reguły, portfel walk-forward, siła ruchu (po dużym dniu ruch ok. 2,5 × większy, po konsolidacji — mniejszy; long + short naraz nie zarabia). Teraz pozycje kilkudniowe (sekcja 7a). Mac: `python -m ia4.swtrend`, `python -m ia4.swrsi`, `python -m ia4.swserie`, `python -m ia4.swportfel` → `SWING-*.xlsx`; przegląd z Claude: liczba strategii spełniających warunek na tle placebo, ✓ na doubleProof, mapa dP obok mapy 53 spółek.
4. **Do potwierdzenia przez człowieka:** usunięcie starej bazy EURUSD 5 min (menu „🗑 FX — usuń stare świece EURUSD 5 min”); zamknięcie FX-7 (arkusz OKOLICZNOSCI_FX ma kolumny H-001 i H-002).
5. **Później, tylko za zgodą:** strategie i wirtualny inwestor FX (gdy prognoza dowiedzie przewagi kierunku); bramka sejfu AI dla hipotez; cechy pisane przez model w piaskownicy.

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
5. **Symulacja jest zawsze pesymistyczna:** wejście po open następnej świecy, przy SL i TP w tej samej świecy — zawsze SL, luka na otwarciu bez premii. Koszty liczą: mechaniczny inwestor, backtest portfela, wszystko w AI Investor i wszystkie badania One-Day i wielodniowe — **spread 0,3% wartości pozycji, raz na transakcję** (wejście i wyjście razem; decyzja człowieka z 16.10.2026; przeliczenia z `--cost 0.6` liczyły go podwójnie).
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
             ├──▶ arkusz Google (STATS, FX, STRATEGIE, SIGNALS-REALTIME, VIRTUAL-INVESTOR …)
             └──▶ GitHub main: telemetry/ ──┐              GitHub research · fx · fx-live · ai · ai-live ◀──┘
                                            └──────▶ strona IA4 (przeglądarka, tylko odczyt) ◀──────┘
```

| Miejsce | Zawartość | Kto pisze |
|---|---|---|
| Firestore | `stocks`, `proof`, `context`, `doubleProof` (świece 1h akcji), `daily` (świece dobowe), `fx1h` (FX), `system/*` | Apps Script |
| branch `main` | kod (`*.gs`, `ia4-research/`), instrukcja, `PRZEWODNIK.md`, `telemetry/state.json`, `telemetry/vi.json`, strona `docs/` | Claude (pakiety), Apps Script (`telemetry/`) |
| branch `research` | strategie, dziennik poszukiwania, doubleProof, backtest portfela | Mac (`ia4.lab`) |
| branch `fx`, `fx-live` | katalog okoliczności i ratingi; prognoza na żywo `forecast.json` | Mac (`ia4.fx`) |
| branch `ai`, `ai-live` | historia AI (transakcje, decyzje, hipotezy, przeglądy, praca agentów); stan na żywo `status.json` | Mac (`ia4.ai`) |
| Mac `~/Desktop/IA4/` | repo, kopie lokalne w `ia4-research/data/`, pliki Excel (`AI-INVESTOR.xlsx`, `ONE-DAY-*.xlsx`, `SWING-*.xlsx`) | Mac |

**Pliki Apps Script:** `Code.gs` (zbieranie, STATS, menu, triggery) · `Daily.gs` (świece dobowe) · `Fx.gs` (FX 1h) · `Research.gs` (arkusz STRATEGIE) · `Paper.gs` + `PaperEngine.gs` (sygnały i mechaniczny inwestor) · `Telemetry.gs` (telemetria na GitHub). Triggery: `runCollector` co minutę, `telemetryHourly` co godzinę, `researchSync` co 30 min.
**Python** (`ia4-research/ia4/`): `sync.py`, `daily.py` (kopie), `lab/` (reguły), `fx/` (prognoza), `ai/` (agenci), `oneday.py`, `odsearch.py`, `odport.py`, `odbreak.py` (badania One-Day), `swing.py`, `swtrend.py`, `swrsi.py`, `swserie.py`, `swportfel.py` (badania wielodniowe).

---

## 4. Dane

**Instrumenty (75 akcji):** główne 3 (AAPL, TSLA, NVDA) i kontrolne 50 — razem **53 handlowane**; tło rynku SPY, QQQ (tylko filtry); **doubleProof 20** (AMD, INTC, QCOM, CSCO, ADBE, LRCX, C, MS, SCHW, COP, OXY, SLB, BA, GE, UBER, F, GM, COST, BMY, CMCSA) — poszukiwanie nigdy ich nie widzi, służą wyłącznie do uczciwej weryfikacji. Listy: `CONFIG` w `Code.gs` i `system/universe`.

**FX (11):** EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD, USDCHF, NZDUSD, EURJPY, GBPJPY, EURGBP oraz BTCUSD. Lista: `Fx.gs` i `ia4/fx/instruments.py` (zmiana — w obu naraz).

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

**Wyniki z 16.10.2026** (Claude, kopia bazy dobowej do 14.10.2026): *swtrend* — warunek spełnia 19 z 49 920, placebo 13 → poziom przypadku; wszystkie to long „po załamaniu” (wybicie w dół z dnia wewnętrznego / NR7 / dołka 55–252 sesji, SL 2 R, TP 3 × SL, 5–10 sesji) — wybicia w kierunku ruchu i każdy short tracą; ✓ jedna (long po NR7 w dół w bessie SPY): portfel 1:1 +71% w 25 lat przy obsunięciu 51%, 1:5 — upadłość w 2008. *swrsi* — QQQ: 209 transakcji, 76% zyskownych, śr. +0,57% netto, PF 2,34; portfel 1:1 +215% (obsunięcie 14%; kup i trzymaj +658%), 1:5 +13 884% (obsunięcie 64%, bez kosztu nocnego); na spółkach słabiej (47 z 74 ze średnią > 0, wspólny portfel 1:1 +44% przy obsunięciu 45%, 1:5 — upadłość w 2020). *swserie* — długie serie spadków dają lekkie odbicie (long po 7 spadkach, 3 sesje: +531% na 53 spółkach, ale +10% na doubleProof, sąsiednie komórki słabe), krótkie serie (4–6) przy tysiącach transakcji — spread × dźwignia → upadłość; serie wzrostów — strata w obie strony. Wyniki niczego nie zmieniają bez zgody człowieka. *swportfel* (17.10.2026): 1370 serii / transakcji (1364 w portfelu), 51% zyskownych, śr. +0,36% netto (+1,78% depozytu przy 1:5); portfel 10 000 $ → 60 804 $ (+508%, CAGR 7%), największe obsunięcie 54% (szczyt 2010-04, dno 2011-08, odrobione dopiero 2020-03; wcześniej −50% 2001-06 → 2008-10); zysk przychodzi skokami w kilku latach (2009 +52%, 2019 +39%, 2020 +39%, 2022 +35%, 2025 +49%, 2026 +63%), pomiędzy — długie okresy strat; cena pod SMA200 śr. +0,59%, nad SMA200 −0,04%; SMA200 spadająca +0,80%, rosnąca −0,02%; doubleProof +0,13%; dekada 2010–2019 ≈ 0. *Analiza zdarzeń i propozycja* (17.10.2026): zarabia kapitulacja — duży spadek serii w % (≥ 10–12%), słaby rynek, wysoka zmienność spółki (R ≥ 3–4%); bez znaczenia: dzień tygodnia, wolumen, luka na otwarciu, spadek w R. Wejście limitem poniżej open albo po potwierdzeniu (nad szczytem świecy) — gorsze niż po open; SL szkodzi; dłuższe trzymanie (5 sesji) lepsze niż 1–3. Propozycja od 2000 r.: 938 serii spełnia warunki, śr. +1,77% netto, 58% zyskownych; z limitem 5 pozycji 681 transakcji, portfel 1:5 +732% przy obsunięciu 79% (2001 → 2009) — o obsunięciu decyduje dźwignia, nie limit (1:2 — ok. 35–39%). Na wszystkich seriach ≥ 5 świec warunek „spadek ≥ 10% i słaby rynek”: przed 2000 +3,70%, 2000–2012 +2,76%, od 2013 +0,66%, doubleProof +1,50%. Zastrzeżenie: 73 spółki to te, które przetrwały — kupowanie spadków wygląda lepiej niż w rzeczywistości.

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

`https://miszyszka.github.io/IA4/` — GitHub Pages z `main/docs`, bez buildu i bibliotek, hasło w przeglądarce (bramka nie chroni danych — wszystkie są w publicznym repo, więc nigdy żadnych sekretów w danych strony). Zakładki: **System** (czy działa zbieranie), **Inwestor** (mechaniczny inwestor), **FX** (prognoza), **AI** (agenci: praca agentów, portfel, Krytyk, Badacz). Pasek „magistrala” pokazuje każde ogniwo drogi danych z wiekiem ostatniego znaku życia. Każdy panel ma opis „?”, nagłówek — przycisk „przewodnik”. Teksty nie są ucinane — zawijają się. Jak dodać zakładkę albo źródło: `docs/README.md`.

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

**Aktualizacja Apps Script:** podmienić pliki `.gs` z pakietu (najprościej wszystkie 7; nowy plik: „+ → Skrypt”), zapisać. „⚙️ Konfiguruj i włącz automat” — tylko gdy Claude o to poprosi (zmiana listy instrumentów, STATS albo triggerów).

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
```

`ia4` to funkcja w `~/.zshrc`: `function ia4 { cd ~/Desktop/IA4/ia4-research && source .venv/bin/activate && if [ "$1" = start ]; then shift; python -m ia4.ai "$@"; else python -m ia4.lab --workers 4 "$@"; fi; }`

---

## 11. Dziennik zmian

Starsze wpisy: `archiwum/IA4_INSTRUKCJA-1.40.md`, sekcja 13, i historia gita.

| Wersja | Data | Zmiana |
|---|---|---|
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
