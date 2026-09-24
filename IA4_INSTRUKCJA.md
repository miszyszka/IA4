# IA 4 — instrukcja projektu

**Wersja:** 1.0
**Data:** 24 września 2026
**Aktualny etap:** 🟨 Etap 0 — 0A wdrożone; trwa pełne pobieranie historii po naprawie L13, przegląd 53 luk i budowa środowiska Pythona (0B)

Ten plik jest jedynym źródłem prawdy o tym, jak pracujemy nad projektem. Stan bieżący (który etap, co zrobione, jakie luki) jest widoczny na żywo w arkuszu **PROJEKT** i w podsumowaniu w **STATS**. Jeśli plik i arkusz się rozjeżdżają, obowiązuje ten plik, a rozbieżność trzeba zapisać jako lukę.

---

## 1. Cel projektu

Znaleźć sygnały wejścia w transakcje na świecach godzinowych, które mają **realną, powtarzalną przewagę** — potwierdzoną poza danymi, na których je znaleziono — a następnie sprawdzić je w działaniu na żywo, najpierw jako monitor sygnałów, potem jako wirtualny inwestor.

Miarą sukcesu nie jest najwyższy zysk w backteście, tylko przewaga, która przetrwa trzy sprawdziany: spółki kontrolne, skarbiec danych i dane na żywo.

---

## 2. Zasady współpracy

1. **Ciągłość między rozmowami.** Claude nie pamięta poprzednich rozmów. Na początku każdej nowej rozmowy załącz ten plik (najwygodniej: Projekt w Claude z tym plikiem w wiedzy projektu). Claude zaczyna od sprawdzenia etapu i otwartych decyzji.
2. **Bramki etapów.** Nie przechodzimy do kolejnego etapu, dopóki nie są spełnione kryteria ukończenia bieżącego (sekcja 6) albo świadomie ich nie odroczymy z wpisem do sekcji 8.
3. **Aktualizacja po każdym etapie.** Zakończenie etapu = nowa wersja tego pliku (status, dziennik zmian, nowe luki) + aktualizacja arkusza PROJEKT.
4. **Kod testowany przed przekazaniem.** Każda zmiana w kodzie jest sprawdzana na symulacji przed przekazaniem. Znane ograniczenia trafiają do sekcji 8, a nie są przemilczane.
5. **Żaden wynik bez liczby transakcji.** Każda skuteczność, ekspektancja czy zysk jest podawana razem z *n*.
6. **Repozytorium GitHub jako wspólny zapis kodu.** `github.com/miszyszka/IA4.git`, branch `main`, przechowuje aktualne kopie plików `.gs` (`Code.gs`, `Proof.gs`, `Project.gs`, `History.gs`), `ia4-dashboard.html` i tego pliku instrukcji. Zasady:
   - Claude **nie ma dostępu** do lokalnego folderu na komputerze użytkownika ani do edytora Google Apps Script. Jedyny kanał, przez który Claude czyta i zapisuje kod, to GitHub.
   - Gdy sesja dotyczy zmian w kodzie lub w tym pliku, Claude na początku klonuje/pobiera repozytorium, żeby pracować na aktualnej wersji, zamiast zakładać stan z pamięci rozmowy.
   - Po każdej zmianie w pliku `.gs`, w `ia4-dashboard.html` lub w tej instrukcji, Claude **commituje i pushuje** zmianę do `main` w tej samej turze, w której ją wprowadził — nie zostawia zmian tylko lokalnie w swoim środowisku roboczym.
   - **Użytkownik ręcznie przenosi** każdą zmianę z GitHub do Google Apps Script (wklejenie treści pliku) oraz do swojego lokalnego folderu na komputerze (`git pull`). To nie dzieje się automatycznie w żadną stronę — GitHub jest pośrednikiem, nie systemem, który sam wgrywa kod do Apps Script.
   - Klucz serwisowy Firebase (Etap 0B) **nigdy** nie trafia do tego repozytorium, zgodnie z 6.5.
7. **Dziennik pushów i jednolita wersja.** Każdy push Claude do repozytorium zostawia ślad w tym pliku:
   - **Każdy push** (nawet drobna poprawka) = nowy wiersz w **sekcji 11 — Dziennik pushów**: data i godzina (czas polski), commit, pliki, jednozdaniowy opis. Wiersz powstaje w tej samej turze co push. Commit nie może zawierać własnego hasha, więc hash uzupełnia się zaraz po pushu albo przy najbliższej kolejnej zmianie — data, godzina i opis są zawsze w commicie, którego dotyczą.
   - **Zmiana znacząca** (nowa funkcja, zmiana logiki, nowa zasada, nowy etap) = dodatkowo **podbicie numeru wersji**: nagłówek tego pliku, wpis w sekcji 10 (dziennik zmian) i **ta sama wersja we wszystkich pozostałych plikach**.
   - **Wersja jest jedna dla całego projektu.** Nagłówek `Wersja projektu: X.Y` na początku każdego pliku `.gs` i `ia4-dashboard.html` oraz stała `PROJECT.INSTRUCTION_VERSION` w `Project.gs` muszą zawsze pokazywać tę samą liczbę co nagłówek tej instrukcji. Rozjazd którejkolwiek z nich to luka do naprawy, a nie drobiazg — arkusz PROJEKT pokazuje wersję z kodu i to po niej poznajesz, czy wklejony do Apps Script kod jest aktualny.
   - `appsscript.json` jest wyjątkiem: format JSON nie dopuszcza komentarzy, a Apps Script odrzuca nieznane pola w manifeście, więc ten plik nie nosi numeru wersji.
   - Poprawka niepodbijająca wersji (literówka, komentarz, formatowanie) trafia tylko do dziennika pushów.

---

## 3. Architektura

| Warstwa | Narzędzie | Rola | Etapy |
|---|---|---|---|
| Zbieranie danych | Google Apps Script | świece 1h na żywo i historia | stale |
| Magazyn danych | Firestore | **jedyne** źródło danych świecowych | wszystkie |
| Badania | Python na Macu | katalog S1, backtest, parametry towarzyszące, model PT | 1–3 |
| Monitoring | arkusze STATS i PROJEKT | stan systemu, etapów i luk | wszystkie |
| Sygnały na żywo | Apps Script, zaraz po dopisaniu świecy (D2) | wykrywanie sygnałów S3 co godzinę | 4 |
| Paper trading | Apps Script + arkusz | wirtualny inwestor | 5 |
| Podgląd | dashboard HTML | wykresy 3 spółek głównych | — |

**Dlaczego badania w Pythonie już od Etapu 1, a nie od 3:** nowy katalog to ok. 24 000 strategii × 27 spółek. Apps Script ma limit 6 minut na uruchomienie i liczyłby to wiele godzin w partiach. Python na Macu policzy to w minutach. Apps Script zostaje przy tym, w czym jest dobry: praca na żywo, bez włączonego komputera.

### Pliki

| Plik | Rola | Los |
|---|---|---|
| `Code.gs` | automat bieżący, 27 spółek, STATS | zostaje |
| `History.gs` | historia 3 spółek głównych | zostaje |
| `Proof.gs` | historia 50 spółek kontrolnych i tła rynku (SPY, QQQ) | zostaje |
| `Project.gs` | arkusz PROJEKT, skarbiec, audyt danych, sprzątanie | od Etapu 0 |
| `Strategies.gs`, `Backtest.gs`, `Combo.gs`, `Benchmark.gs` | stary katalog i analizy | usuwane w Etapie 0 (ręcznie w edytorze) |
| `appsscript.json` | uprawnienia | zostaje |
| `ia4-dashboard.html` | podgląd wykresów | zostaje |
| `IA4_INSTRUKCJA.md` | ten plik | aktualizowany co etap |
| `S1_KATALOG_BAZOWY.md` | 84 sygnały bazowe z definicjami i parametrami | punkt wyjścia Etapu 1 |
| `ia4-research/ia4/config.py` | klucz serwisowy, granice skarbca i listy instrumentów czytane z Firestore | od Etapu 0B |
| `ia4-research/ia4/sync.py` | Firestore → parquet, tylko przyrosty | od Etapu 0B |
| `ia4-research/ia4/data.py` | wczytywanie danych z wymuszoną granicą skarbca | od Etapu 0B |
| `ia4-research/verify.py` | sprawdzian kryterium 0.9 wobec audytu | od Etapu 0B |
| `ia4-research/data/` | pamięć podręczna parquet — **poza gitem** | od Etapu 0B |

---

## 4. Dane

### Spółki

- **Główne (3):** AAPL, TSLA, NVDA — na nich szukamy strategii, widoczne w dashboardzie.
- **Kontrolne (50):** sprawdzian, czy strategia działa poza wykresami, na których ją znaleziono. Dobrane pod różnorodność sektorową (poprzednia lista 24 była przechylona w stronę technologii i finansów):
  - pierwotne 24: DELL, AMAT, PLTR, ORCL, XOM, V, WMT, JPM, MU, META, AVGO, MSFT, GOOGL, JNJ, MA, ABBV, BAC, CVX, MRK, PG, HD, PM, WFC, CRM,
  - przemysł: CAT, HON, UNP, RTX,
  - dobra cykliczne: AMZN, MCD, NKE, SBUX,
  - media i telekomunikacja: T, VZ, NFLX, DIS,
  - ochrona zdrowia: UNH, LLY, PFE, MDT,
  - nieruchomości (REIT): PLD, AMT,
  - surowce: LIN, FCX,
  - użyteczność publiczna: NEE, DUK,
  - bankowość inwestycyjna: GS, AXP,
  - dobra pierwszej potrzeby: KO, PEP.
- **Tło rynku (D3):** SPY, QQQ — nie handlujemy nimi, służą jako kontekst w Etapie 3. Zbierane od Etapu 0: historia i na żywo. (VIX usunięty z projektu — D8.)

### Format w Firestore

```
stocks/{SYMBOL}/candles/{data}_{nr}   spółki główne, jedna świeca na dokument
proof/{SYMBOL}/sessions/{data}        spółki kontrolne, cała sesja w jednym dokumencie
context/{SYMBOL}/sessions/{data}      tło rynku, ten sam format
system/status                         ostatni zapis automatu
system/history, system/universe       stan pobierania historii i listy instrumentów
system/project                        etap, wersja instrukcji, granice skarbca
```

Dokument sesji ma pola `symbol, date, bars, slots, o, h, l, c, v, startPL, firstCandleTime, updatedAt`, gdzie `v` to wolumen (D12). Tablice `slots, o, h, l, c, v` są równoległe, a `slots` zawiera numery świec 1–7. Ten sam format zapisuje historia (`Proof.gs`) i automat bieżący (`Code.gs`, funkcja `sessionFields_`).

### Zakres

Yahoo udostępnia świece 1h z ok. 730 dni wstecz. Mamy mniej więcej wrzesień 2024 – wrzesień 2026, czyli ok. 500 sesji i 3500 świec na spółkę.

---

## 5. Żelazne zasady metodologiczne

Te zasady obowiązują w każdym etapie. Złamanie którejś unieważnia wyniki.

### 5.1 Skarbiec danych

- Ostatnie **6 miesięcy** historii to skarbiec (D1). **Granica jest ustalona w Etapie 0, przed stworzeniem jakiejkolwiek strategii:**

  | Okres | Daty | Kto używa |
  |---|---|---|
  | badawczy | do 2026-03-22 włącznie | Etapy 1–3 |
  | skarbiec | 2026-03-23 – 2026-09-22 | tylko jednorazowy sprawdzian w Etapie 3 |
  | dane na żywo | od 2026-09-23 | Etapy 4–5 |

  Granice są zapisane w `Project.gs` (stała `PROJECT`) i w Firestore (`system/project`). Python czyta je z Firestore, nie z kodu.
- Skarbiec to **ciągły blok czasu**, nie losowe świece. Losowe świece przeciekałyby, bo sąsiednie świece dzielą wskaźniki i nakładające się transakcje.
- Etapy 1, 2 i 3 widzą wyłącznie dane sprzed skarbca (**okres badawczy**).
- Skarbiec jest otwierany **raz**, na końcu Etapu 3, do jednego ostatecznego sprawdzianu. Data otwarcia zostaje zapisana w PROJEKT.
- Porażka na skarbcu jest wynikiem, a nie błędem do naprawienia. Nie wolno poprawić modelu i sprawdzić go na skarbcu ponownie.
- Dane nowsze niż granica cięcia (zbierane na żywo) to trzeci, naturalny sprawdzian w Etapach 4–5.

### 5.2 Żadnego zaglądania w przyszłość

- Sygnał i wszystkie parametry towarzyszące liczone są wyłącznie z danych dostępnych po zamknięciu świecy sygnału.
- Wejście następuje po cenie otwarcia następnej świecy (wyjątek: sygnały luki na otwarciu sesji wchodzą po cenie tego otwarcia).

### 5.3 Kontrola dryfu rynku

Każda strategia jest porównywana z **wejściem losowym o tym samym kierunku i tych samych zasadach wyjścia** (średnia z wejścia w każdą świecę okresu badawczego). Przewaga = wynik strategii − wynik wejścia losowego. Wariant short odpowiada na inne pytanie (czy sygnał przewiduje spadek), więc sam w sobie nie wystarcza do usunięcia dryfu.

### 5.4 Wieloznaczność świecy godzinowej

Gdy w jednej świecy osiągalny jest i stop, i cel, dane 1h nie mówią, co było pierwsze. Przyjmujemy stop (wariant ostrożny), ale przy SL/TP 0,5–1% takich transakcji może być dużo, a wynik staje się artefaktem tej reguły. Każda strategia ma kolumnę **% transakcji wieloznacznych**. Strategie z udziałem powyżej 20% są oznaczane jako niewiarygodne.

### 5.5 Koszty

Wynik główny: bez kosztów. Dodatkowa kolumna: ekspektancja przy koszcie **0,05% za transakcję** (tam i z powrotem), bo przy celu 0,5% koszt zjada 10% zysku brutto.

### 5.6 Dwie grupy spółek

Każdy wynik jest liczony osobno dla grupy głównej i kontrolnej. Zależność liczy się jako prawdziwa tylko wtedy, gdy występuje w obu grupach.

### 5.7 Liczba testów

Przy ~24 000 strategii kilkaset wygląda świetnie czystym przypadkiem. Ranking w Etapie 2 uwzględnia, jak dobry wynik da się uzyskać losowo przy tej liczbie prób (rozkład wyników wejść losowych), a nie tylko wynik strategii.

### 5.8 Zapisy na żywo tylko dopisywane

Sygnały z Etapu 4 i transakcje z Etapu 5 są wyłącznie dopisywane, nigdy poprawiane wstecz. Błędy koryguje się nowym wpisem z adnotacją.

---

## 6. Etapy

Status: ⬜ nie rozpoczęty · 🟨 w toku · ✅ zakończony · ⏸ odroczony

### Etap 0 — Porządki i fundamenty 🟨

**Cel:** czysty stan, zaufane dane, zamknięty skarbiec, działający monitoring etapów i środowisko Pythona.

Etap dzielimy na dwie części:
- **0A (Apps Script)** — punkty 1–4 i 6. Kod gotowy: `Project.gs` (nowy), `Code.gs` i `Proof.gs` (zmienione).
- **0B (Python)** — punkt 5 i kryterium 0.9.

1. **Usunięcie starych analiz:** arkusze BACKTEST, KOMBINACJE, KOMBINACJE_LEGENDA, KOMBINACJE_PODOBIENSTWO, BENCHMARK, STRATEGIE, STRATEGIE_LEGENDA oraz ukryte `_BACKTEST_DANE`, `_KOMBINACJE_DANE`, `_KOMBINACJE_TAB`, `_BENCHMARK_DANE`; pliki `Strategies.gs`, `Backtest.gs`, `Combo.gs`, `Benchmark.gs`; ich triggery, stany i pozycje menu.
2. **Audyt danych** — jednorazowy raport i stały mechanizm uruchamiany co noc:
   - brakujące sesje (porównanie z kalendarzem NYSE),
   - brakujące świece w sesjach (poza sesjami skróconymi),
   - duplikaty,
   - skoki ceny powyżej 20% między świecami (podejrzenie splitu akcji),
   - spółki, które przestały się aktualizować.
3. **Wydzielenie skarbca:** granica dat zapisana w `system/project` i w tym pliku.
4. **Arkusz PROJEKT** (sekcja 7) + podsumowanie w STATS.
5. **Środowisko Python** (0B): folder `ia4-research/` — instalacja i użycie opisane w `ia4-research/README.md`. Zawiera:
   - klucz serwisowy Firebase w `~/.ia4/serviceAccount.json`, **poza repozytorium**; `config.py` odmawia startu, gdyby klucz znalazł się wewnątrz folderu projektu,
   - `sync.py` — Firestore → parquet, tylko przyrosty; manifest pamięta ostatnią datę każdego instrumentu, więc codzienne uruchomienie pobiera kilkanaście świec zamiast 30 tysięcy,
   - `data.py` — jedyna droga, którą dane trafiają do backtestu; **domyślnie zwraca wyłącznie okres badawczy**, a sięgnięcie po skarbiec wymaga jawnego `unlock_vault=True` i kończy się wyjątkiem bez niego (zasada 5.1 wymuszona kodem, nie pamięcią),
   - `verify.py` — sprawdzian kryterium 0.9: tabela w układzie arkusza PROJEKT plus kontrole spójności (instrumenty bez danych, z historią zaczynającą się dopiero w skarbcu, poniżej 100 sesji, oznaczone przez `Proof.gs` jako niepełne lub nieudane).
6. Zbieranie SPY i QQQ: historia + na żywo. Musi ruszyć teraz, żeby dane były gotowe na Etap 3.

**Wdrożenie 0A — kolejność:**
1. Podmień `Code.gs` i `Proof.gs`, dodaj `Project.gs`. Usuń w edytorze `Strategies.gs`, `Backtest.gs`, `Combo.gs`, `Benchmark.gs`.
2. Odśwież arkusz → IA 4 → Projekt → **Etap 0: usuń stare analizy**. Usuwa stare arkusze, triggery i stany, tworzy arkusz PROJEKT, zapisuje skarbiec w Firestore, instaluje nocny audyt.
3. IA 4 → **Konfiguruj i włącz automat**. Przebudowuje STATS (30 instrumentów + stan projektu) i uzupełnia ostatni miesiąc, w tym tło rynku.
4. IA 4 → Spółki kontrolne i tło rynku → **Pobierz historię**. Dociąga SPY i QQQ.
5. Po zakończeniu historii: IA 4 → Projekt → **Pełny audyt danych**.
6. W arkuszu PROJEKT przejrzyj luki: każdą albo zgłoś do naprawy, albo oznacz jako `zaakceptowana` z komentarzem.

**Kryteria ukończenia** (w arkuszu PROJEKT, sprawdzane automatycznie poza 0.9):
- 0.1 stare arkusze analiz usunięte,
- 0.2 stare pliki kodu i ich triggery usunięte,
- 0.3 tło rynku: historia pobrana,
- 0.4 tło rynku zbierane na żywo,
- 0.5 pełny audyt wykonany,
- 0.6 każda luka naprawiona albo zaakceptowana,
- 0.7 granica skarbca zapisana w Firestore i w instrukcji,
- 0.8 nocny audyt działa,
- 0.9 Python wczytuje dane wszystkich instrumentów, liczby zgadzają się z audytem (ręcznie, po 0B).

### Etap 1 — Katalog strategii S1 ⬜

**Cel:** pełny, przemyślany katalog hipotez i silnik, który je liczy. *(Proponowany rozdział: Etap 1 = definicje i silnik, Etap 2 = obliczenia i wybór. W pierwotnym planie oba etapy obejmowały liczenie wyników.)*

- **Sygnały:** dotychczasowe 84 (pełna lista z definicjami i parametrami JSON: **`S1_KATALOG_BAZOWY.md`**) plus nowe rodziny, łącznie ok. 120–150. Rodziny bazowe: spadek w N świecach (18), czerwone świece z rzędu (13), odchylenie od średniej (9), wyprzedanie RSI (8), luka spadkowa (6), formacje odwrócenia (6), spadek względem ATR (6), spadek od szczytu (5), spadek od otwarcia sesji (4), wstęga Bollingera (4), duża czerwona świeca (3), spadkowe sesje z rzędu (2). **Uwaga: wszystkie 84 to warianty jednej hipotezy (kupno po spadku) i wszystkie są LONG — patrz decyzja D9.** Nowe pomysły: sygnały z warunkiem wolumenu (kapitulacja = spadek na wolumenie powyżej średniej — D12), wybicia z konsolidacji, zawężenie i rozszerzenie zmienności, sygnały zależne od pory dnia, sygnały wielodniowe, sygnały wzrostowe (lustra spadkowych — kandydaci na short).
- **Kierunek:** każdy sygnał w dwóch wariantach — LONG i SHORT na tych samych zasadach (short: stop powyżej wejścia, cel poniżej).
- **Siatka wyjść:** SL i TP ∈ {0,5; 0,75; 1; 1,25; 1,5; 2; 2,5; 3; 4; 5}%, wszystkie 100 kombinacji. Nic powyżej 5%.
- **Limit czasu H** zależny od celu (propozycja): TP ≤ 1% → 14 świec (2 sesje), TP ≤ 2,5% → 35 (5 sesji), TP ≤ 5% → 70 (10 sesji).
- **Skala:** ~120 sygnałów × 2 kierunki × 100 wyjść ≈ 24 000 strategii.
- **Nazewnictwo:** jak dotąd, z dodanym kierunkiem, np. `DROP_N3_X2__L__SL1_TP1.5_H35`.
- **Zasady portfela i wyjścia:** jak w dotychczasowym silniku (jedna pozycja = 100 $, maks. 3 otwarte na strategię w grupie, stop przed celem w tej samej świecy, luka rozliczana po otwarciu).

**Kryteria ukończenia:** katalog S1 z opisami i parametrami; silnik w Pythonie przechodzi testy zgodności (wyniki kontrolnych przypadków identyczne z ręcznie policzonymi); obliczenie kilku strategii próbnych zgadza się z dotychczasowym silnikiem z Apps Script.

### Etap 2 — Backtest S1 i wybór S2 ⬜

**Cel:** policzyć wszystkie strategie S1 na okresie badawczym i wybrać najwartościowsze.

Kolumny wyniku dla każdej strategii, osobno dla grupy głównej i kontrolnej:
- transakcji, skuteczność, ekspektancja, profit factor, śr. zysk, śr. strata, obsunięcie,
- **mediana trzymania pozycji (w świecach) osobno dla wyjść na stopie, na celu i z limitu czasu,**
- % wyjść na stopie / celu / limicie,
- % transakcji wieloznacznych (5.4),
- ekspektancja po kosztach (5.5),
- wejście losowe i przewaga nad nim (5.3),
- spółek kontrolnych na plusie z 24,
- porównanie z wariantem przeciwnego kierunku,
- wskaźnik istotności z uwzględnieniem liczby testów (5.7).

Wynik trafia do arkusza S1_WYNIKI. Użytkownik wybiera strategie do S2, zaznaczając je w arkuszu. Claude proponuje filtry i ranking, ale nie wybiera za użytkownika.

**Kryteria ukończenia:** wszystkie strategie policzone; lista S2 zatwierdzona przez użytkownika i zapisana (arkusz + Firestore); w tym pliku zapisane kryteria, którymi się kierowano.

### Etap 3 — Parametry towarzyszące i rating PT → S3 ⬜

**Cel:** dla każdego sygnału S2 ocenić, w jakim kontekście działa, i nadać mu rating PT od 1 do 100.

**Zbiór danych:** każda historyczna transakcja S2 z okresu badawczego to jeden wiersz: ~1000 parametrów towarzyszących policzonych w chwili sygnału + wynik transakcji.

**Rodziny parametrów (~1000 łącznie, każda w wielu oknach):**
1. Trend — odległość od SMA/EMA w oknach 5–700 świec, nachylenie średnich.
2. Momentum — RSI w różnych okresach, zwroty w oknach 1–140 świec, stochastyk, MACD.
3. Zmienność — ATR, odchylenie zwrotów, zakres high-low, stosunek zmienności krótkiej do długiej, szerokość wstęgi Bollingera.
4. Pozycja w zakresie — odległość od maksimum i minimum z N świec i N sesji, czas od ostatniego szczytu i dołka.
5. Świece — kształt bieżącej i 1–5 poprzednich, serie kolorów, luki.
6. Sesja — która świeca dnia, ruch i zmienność od otwarcia, luka poranna, wynik poprzedniej sesji, pozycja ceny w zakresie dnia.
7. Kalendarz — dzień tygodnia, koniec miesiąca i kwartału, dzień po święcie.
8. Wielodniowe — zwroty z 1–20 sesji, serie sesji spadkowych i wzrostowych.
9. Rynek (SPY, QQQ) — te same rodziny dla indeksów + siła względna spółki wobec rynku, krocząca beta i korelacja.
10. Wolumen — poziom względem średniej z N świec i N sesji, wolumen względem tej samej świecy dnia w poprzednich sesjach, wolumen świecy sygnału względem poprzedzających, narastający wolumen sesji, wolumen przy spadku kontra przy wzroście.
11. Szerokość rynku z naszych 27 spółek — ile jest powyżej średnich, ile spadło dziś, średni zwrot grupy.
12. Kontekst sygnału — ile razy wystąpił ostatnio, czas od poprzedniego, czy inne sygnały S2 odpaliły jednocześnie.

**Skala obliczeń.** Etap 3 nie jest jednym przebiegiem, tylko **ciągłym przeszukiwaniem**: model liczy się na Macu godzinami albo dniami, przechodząc kolejne kombinacje parametrów, okna czasowe i progi, i zapisuje najlepsze znalezione zależności wraz z datą i wynikiem walidacji. Każdy kolejny przebieg startuje od zapisanego stanu i próbuje go poprawić. Dlatego kod Etapu 3 musi od początku: zapisywać postęp na dysk po każdej rundzie (przerwanie nie może kasować pracy), logować każdą sprawdzoną konfigurację z wynikiem, żeby dało się odtworzyć, ile prób wykonano (5.7), i nigdy nie dotykać skarbca (`data.load` pilnuje tego programowo).

**Metoda:**
1. **Przesiew pojedynczych parametrów** — dla każdego parametru: jak zmienia się skuteczność w jego przedziałach, na ilu transakcjach, czy efekt powtarza się w obu grupach spółek i w kolejnych okresach czasu. Wynik: czytelna lista w stylu „80% transakcji zakończonych stopem wypadło przy cenie poniżej SMA(140)”.
2. **Model zależności** — zespół drzew decyzyjnych (gradient boosting). Robi dokładnie to, co opisałeś jako sieć zależności: bierze najbardziej obiecujący parametr, dzieli po nim dane, a w każdej części szuka kolejnego. Sieć neuronowa nie jest tu dobrym wyborem: przy kilku tysiącach transakcji i tysiącu parametrów przeuczy się niemal na pewno, a drzewa radzą sobie z takimi danymi lepiej i dają się zinterpretować.
3. **Walidacja krocząca** w okresie badawczym — model uczony na starszych danych, sprawdzany na nowszych, kilka razy z przesunięciem.
4. **PT 1–100** = percentyl przewidywanej jakości transakcji (1 — najgorszy 1% sygnałów, 100 — najlepszy).
5. **Próg PT** dobierany na walidacji kroczącej.
6. **Jednorazowy sprawdzian na skarbcu** (5.1).

**Ograniczenie z decyzji D2:** model PT będzie liczony w Apps Script, zaraz po dopisaniu świecy. Dlatego ostateczny model musi być przenośny:
- przesiew obejmuje ~1000 parametrów, ale model używa najwyżej ~50,
- drzewa są eksportowane z Pythona jako JSON i wykonywane w Apps Script,
- każdy parametr jest liczony identycznie w obu językach — test zgodności na tych samych świecach jest częścią kryteriów ukończenia.

**Kryteria ukończenia:** raport najsilniejszych zależności; model PT; próg PT; model przenośny z zaliczonym testem zgodności; wynik skarbca zapisany niezależnie od tego, czy potwierdził przewagę. Sygnały S2 z ratingiem PT stają się S3.

**Warunek sukcesu:** na skarbcu sygnały z PT ≥ progu mają wyższą ekspektancję niż wszystkie sygnały S2 razem, w obu grupach spółek, przy liczbie transakcji wystarczającej do wniosków.

### Etap 4 — Monitor sygnałów na żywo ⬜

- **Moment zamknięcia świecy jest momentem sygnału.** Automat chodzi co minutę; w oknie 5 minut po zamknięciu świecy jedno uruchomienie samo ponawia pytanie do Yahoo co 30 sekund, aż świeca się pojawi (Yahoo publikuje ją z opóźnieniem kilkunastu–kilkudziesięciu sekund). Dzięki temu świeca trafia do bazy zwykle w ciągu minuty od zamknięcia, a nie po 5 minutach.
- **Łatanie luk bez udziału człowieka.** W przebiegach, w których nie ma nic do zebrania (noc, weekend, po sesji), automat bierze luki wykryte przez audyt i dociąga brakujące sesje z Yahoo — po dwie na przebieg, z odstępem, żeby nigdy nie zająć limitu potrzebnego bieżącym świecom. Przerwa w danych spowodowana limitem Firestore albo awarią Yahoo zasklepia się sama.
- Co godzinę, po zamknięciu świecy, system sprawdza sygnały S3 na 3 spółkach głównych i dopisuje je do arkusza SYGNAŁY: czas, spółka, strategia, kierunek, planowane wejście, poziomy SL i TP, PT, czy powyżej progu.
- **Propozycja:** gdy upłynie limit czasu sygnału, system sam dopisuje, jak transakcja by się skończyła. To daje sprawdzian na żywo jeszcze przed paper tradingiem.
- Architektura (D2): automat bieżący w `Code.gs`, zaraz po zapisaniu zamkniętej świecy spółki głównej, liczy sygnały S3 i ich PT na tej świecy i dopisuje je do arkusza. Model PT pochodzi z Pythona (Etap 3) w postaci JSON.

**Kryteria ukończenia:** monitor działa co najmniej 2 tygodnie bez luk; statystyka sygnałów na godzinę i rozkład PT; porównanie wyników na żywo z oczekiwaniami z Etapu 3.

### Etap 5 — Paper trading ⬜

Wirtualny inwestor co godzinę otwiera i zamyka transakcje według ustalonych zasad i zapisuje wszystko w arkuszach: pozycje otwarte, zamknięte, stan portfela. Zasady do ustalenia na początku etapu: kapitał, wielkość pozycji, limit otwartych pozycji, priorytet przy wielu sygnałach naraz (np. według PT), zachowanie przy kolejnym sygnale na tej samej spółce, koszty.

---

## 7. Monitoring etapów

**Arkusz PROJEKT** (menu IA 4 → Projekt → Pokaż / odśwież stan projektu):
- wersja instrukcji, aktualny etap, liczba spełnionych kryteriów,
- tabela etapów 0–5 ze statusem i datami,
- kryteria ukończenia bieżącego etapu: automatyczne (✓/✗ ze szczegółami) i ręczne (pole wyboru),
- skarbiec: okres badawczy, skarbiec, dane na żywo, status i data zapisu w Firestore,
- dane: daty audytów, liczba luk, tabela instrumentów z liczbą sesji, świec i zakresem (z pełnego audytu),
- tabela luk: spółka, typ, data, opis, **status** (`nowa` / `zaakceptowana`) i **komentarz** — oba pola wypełniasz w arkuszu i są zapamiętywane między audytami,
- decyzje.

**Zamykanie etapu:** IA 4 → Projekt → Zamknij bieżący etap. Skrypt odmówi, jeśli któreś kryterium nie jest spełnione, i wypisze które. Po zamknięciu: nowa wersja tej instrukcji.

**STATS** wiersze 18–20: etap projektu, luki w danych, skarbiec. Aktualizowane od razu przy każdej zmianie w PROJEKT i co 5 minut przez automat.

**Dopisywanie wolumenu do starej historii** (D12): świece zebrane przed wersją 0.8 nie mają wolumenu. Zamiast pobierać wszystko od nowa (~37 000 zapisów, czyli dwa dni ponad dzienny limit Firestore), automat uzupełnia je sam. W przebiegach, w których nie ma nic do zebrania, cofa się po historii każdego instrumentu oknami po 60 dni i zapisuje te same świece ponownie — tym razem z wolumenem. Kolejność jak w `liveSymbols_()`: najpierw trzy spółki główne. Dzienny budżet 3000 dokumentów pilnuje, żeby uzupełnianie nigdy nie zabrało limitu bieżącym świecom; całość zajmuje ok. dwóch tygodni bez niczyjej uwagi. Luki mają pierwszeństwo — wolumen dopisuje się dopiero, gdy nie ma nic do załatania. Postęp: menu IA 4 → Projekt → **Postęp dopisywania wolumenu**.

**Audyt danych** szuka: brakujących sesji (wg kalendarza NYSE), brakujących świec (sesje skrócone mają 4), nadmiarowych świec, błędnych świec (high poniżej max(open, close) itp.), duplikatów, skoków ceny powyżej 15% (podejrzenie splitu — D11) i instrumentów, które przestały się aktualizować.
- **pełny** — na żądanie; wszystkie instrumenty, cała historia; ok. 24 000 odczytów Firestore (prawie połowa dziennego darmowego limitu), więc uruchamiaj go rzadko,
- **nocny** — codziennie ok. 23:00; ostatnie 14 dni; kilkaset odczytów.

Stan projektu jest też w `system/project` w Firestore, żeby Python czytał dokładnie tę samą granicę skarbca co Apps Script.

---

## 8. Znane luki i ryzyka

| # | Luka | Skutek | Obsługa |
|---|---|---|---|
| L1 | Wieloznaczność świecy 1h | wyniki ciasnych SL/TP zależą od reguły „stop pierwszy” | kolumna % wieloznacznych, próg 20% (5.4) |
| L2 | Splity akcji | świeca ze splitem wygląda jak głęboki spadek, czyli fałszywie uruchamia sygnały katalogu | próg audytu obniżony do 15%, sesje ze splitem wykluczane z liczenia sygnałów (D11) |
| L3 | Yahoo to nieoficjalne źródło | przerwy, blokady 429 | ponawianie + audyt luk |
| L4 | Historia 1h tylko ~730 dni | ograniczona próba | skarbiec kosztem okresu badawczego — świadomy kompromis |
| L5 | Transakcje nakładają się w czasie | statystyki zawyżają pewność | liczymy Z jako ranking, nie jako test |
| L6 | Grupa kontrolna to duże spółki USA | mimo poszerzenia do 50 i 9 sektorów, część nadal skorelowana | wymóg zgodności w wielu okresach czasu |
| L7 | Dashboard ma własną kopię logiki sygnałów | może rozjechać się z Pythonem | do decyzji po Etapie 1 |
| L8 | Licznik sesji w `proof/{SYMBOL}` nie jest aktualizowany na żywo | kosmetyka | backtest liczy sesje z dokumentów |
| L9 | Kalendarz świąt (`History.gs`) i sesji skróconych (`Project.gs`) kończy się na 2026 | od 2027 audyt i historia źle rozpoznają dni sesji | uzupełnić obie listy na początku każdego roku |
| L10 | Pełny audyt zużywa ~24 000 odczytów Firestore | przy częstym uruchamianiu grozi przekroczeniem limitu 50 000 dziennie | pełny audyt rzadko, na co dzień nocny |
| L12 | Kryteria etapów są w dwóch miejscach: ten plik i `STAGES` w `Project.gs` | mogą się rozjechać | przy każdej nowej wersji instrukcji aktualizujemy oba |
| L13 | „Uzupełnij najnowsze” kasowało stan i przełączało tryb na `refresh`, a „Pobierz historię” po cichu go kontynuowała | 26 nowych spółek kontrolnych i tło rynku miały po 5–28 sesji zamiast ~500, bez ostrzeżenia w STATS (flaga „niepełna historia” nie działa w trybie `refresh`) | naprawione w 0.5: `startProof()` odrzuca stan spoza trybu `full`. Dane nie ucierpiały — Firestore tylko dopisuje |
| L14 | 26 spółek kontrolnych i tło rynku nadal mają historię krótszą niż okres badawczy | nie nadają się do Etapów 1–3, bo cała ich historia leży w skarbcu albo po nim | pełne pobranie po wdrożeniu 0.5; `verify.py` wypisuje takie instrumenty osobno |
| L18 | Historia sprzed wersji 0.8 nie ma wolumenu, a przepisanie jej to ~37 000 zapisów przy limicie 20 000 dziennie | przez ok. dwa tygodnie część historii ma wolumen, a część nie — parametry wolumenowe policzone w tym czasie byłyby liczone na niepełnych danych | automat dopisuje wolumen sam, 3000 dokumentów dziennie, najpierw spółki główne; nie liczyć parametrów wolumenowych, dopóki menu „Postęp dopisywania wolumenu" nie pokaże, że skończone |
| L17 | `expectedSlots_` w dniu sesji skróconej liczy 7 świec zamiast 4 | automat po zamknięciu skróconej sesji dopytuje Yahoo aż do `POLL_AFTER_CLOSE_MIN` zamiast uznać dzień za kompletny; dane są poprawne, marnuje się tylko kilka zapytań | wykryte testem 2026-09-23, niegroźne; poprawić przy najbliższej sesji skróconej (27.11.2026), gdy da się to sprawdzić na żywo |
| L15 | Historia z Yahoo sięga ~730 dni, więc nowo dodane instrumenty nigdy nie dogonią tych z 2024 r. | grupa kontrolna ma dwa pokolenia: ~506 sesji i tyle, ile zdążyło się zebrać | jeśli po pełnym pobraniu różnica zostanie, zapisać ją jako świadomy kompromis i uwzględniać przy wymogu 5.6 |

---

## 9. Otwarte decyzje

| # | Decyzja | Propozycja | Status |
|---|---|---|---|
| D1 | Wielkość skarbca | ostatnie 6 miesięcy: 2026-03-23 – 2026-09-22 | ✅ przyjęta |
| D2 | Gdzie działa Etap 4 | Apps Script, zaraz po dopisaniu świecy; model z Pythona jako JSON | ✅ przyjęta |
| D3 | Tło rynku | SPY, QQQ zbierane od Etapu 0 | ✅ przyjęta |
| D4 | Siatka SL/TP | pełna 10×10 | ✅ przyjęta |
| D5 | Limit czasu H | TP ≤ 1% → 14 świec, ≤ 2,5% → 35, ≤ 5% → 70 jako wartość wyjściowa; docelowo H dobierane statystycznie (patrz D10) | ✅ przyjęta |
| D6 | Koszty | wynik bez kosztów + kolumna z 0,05% | ✅ przyjęta |
| D7 | Usunięcie starego katalogu STRATEGIE | tak, zastąpi go S1 | ✅ przyjęta |
| D8 | VIX w projekcie | usunięty całkowicie: z `Proof.gs`, audytu, rodzin parametrów Etapu 3 i tła rynku. Zostają SPY i QQQ | ✅ przyjęta |

### Decyzje z przeglądu katalogu bazowego — rozstrzygnięte 2026-09-23

| # | Decyzja | Rozstrzygnięcie | Status |
|---|---|---|---|
| D9 | Katalog S1 to jedna hipoteza | Do S1 wchodzą warianty **SHORT** jako pełnoprawne lustra sygnałów spadkowych, nie dodatek. Szukamy wzorców krótkiej sprzedaży na równi z długimi. | ✅ przyjęta |
| D10 | Jak dobierać limit czasu H | H **nie jest przeszukiwany** jak SL/TP. Dla każdej strategii liczymy rozkład czasu do wyjścia osobno dla SL, TP i limitu, a H wyznaczamy jako kwantyl (propozycja: 90. percentyl czasu do TP). Wartości z D5 zostają jako punkt wyjścia. Dzięki temu H wynika z danych, ale nie mnoży liczby testów (5.7). | ✅ przyjęta |
| D11 | Splity generują fałszywe sygnały | Przed Etapem 1: wykryć wszystkie skoki powyżej **15%** (nie 30%), sprawdzić ręcznie, a sesje ze splitem **wykluczyć z liczenia sygnałów**, nie tylko oznaczyć. | ✅ przyjęta |
| D12 | Wolumen | **Zbierany od wersji 0.8.** Pole `volume` w dokumencie świecy spółek głównych, tablica `v` w dokumentach sesji spółek kontrolnych i tła rynku. Wolumen wchodzi do katalogu S1 jako filtr i warunek sygnałów oraz do Etapu 3 jako osobna rodzina parametrów towarzyszących. Świece zebrane wcześniej mają `v = 0` — parametry oparte na wolumenie liczymy dopiero od dnia wdrożenia albo po ponownym pobraniu historii. | ✅ przyjęta |
| D13 | Grupa kontrolna to ocalali | Uznajemy, że dryf ma znaczenie, ale świeca godzinowa i warianty SHORT (D9) znacznie ograniczają wpływ długoterminowego trendu wzrostowego. Zostaje wymóg z 5.3 i raportowanie wyniku osobno dla spółek rosnących i spadających w okresie badawczym. Nie zmieniamy składu grupy kontrolnej. | ✅ przyjęta |
| D14 | Kontrola źródła danych | Ufamy Yahoo. Zostaje audyt braków i skoków; nie dokładamy sum kontrolnych. | ✅ przyjęta |
| D15 | Budżet czasu w Etapie 4 | Zaraz po zamknięciu świecy liczą się **tylko 3 spółki główne** — to na nich powstają sygnały. Spółki kontrolne i tło rynku dociągają się przy kolejnych uruchomieniach. Tryb szybki czeka wyłącznie na AAPL, TSLA i NVDA. | ✅ przyjęta |
| D16 | Próg „przewagi" | Progi ustalone **przed** policzeniem Etapu 2: minimum **100 transakcji** w grupie głównej i **300** w kontrolnej, przewaga nad wejściem losowym dodatnia **w obu grupach**, wynik lepszy niż **99. percentyl** rozkładu wejść losowych przy tej liczbie prób. | ✅ przyjęta |

---

## 10. Dziennik zmian

| Wersja | Data | Zmiana |
|---|---|---|
| 0.1 | 2026-09-22 | Pierwsza wersja: architektura, zasady, etapy 0–5, luki, otwarte decyzje. |
| 0.2 | 2026-09-22 | Decyzje D1–D3 i D7. Daty skarbca. Tło rynku (SPY, QQQ, VIX) w zbieraniu danych. Etap 0 podzielony na 0A i 0B; kod 0A: `Project.gs`, zmiany w `Code.gs` i `Proof.gs`. Ograniczenie przenośności modelu PT w Etapie 3. Opis arkusza PROJEKT i audytu. Luki L9–L12. |
| 0.3 | 2026-09-22 | Literówka WTM → WMT (Walmart). Grupa kontrolna poszerzona z 24 do 50 spółek, dobór pod różnorodność sektorową (9 sektorów). |
| 0.4 | 2026-09-23 | Repozytorium GitHub (`github.com/miszyszka/IA4.git`, branch `main`) jako jedyny kanał, przez który Claude czyta i zapisuje kod — zasada 2.6. Dogonienie pliku do stanu z wersji 0.3 (poprawki WMT i listy 50 spółek nie trafiły wcześniej do repo). Doprecyzowanie w tabeli plików i w L6, że dotyczy 50 spółek kontrolnych, nie 24. |
| 0.5 | 2026-09-23 | Zasada 2.7: dziennik pushów i jedna wersja we wszystkich plikach. Nagłówek `Wersja projektu` w każdym `.gs` i w dashboardzie, `PROJECT.INSTRUCTION_VERSION` podbite z 0.2 na 0.5. Naprawa `startProof()` (tryb `refresh` udawał pełne pobieranie — luka L13). Etap 0B: powstał folder `ia4-research/` z `config.py`, `sync.py`, `data.py`, `verify.py`. Skarbiec wymuszony programowo w `data.load()`. Luki L13–L15. |
| 0.6 | 2026-09-23 | Nowa funkcja `refetchProof()` i pozycja menu „Pobierz ponownie wybrane…” — naprawia skutek L13 bez pełnego resetu. Naprawa L13 potwierdzona: 19 instrumentów dociągnęło pełną historię. Luka L16 (^VIX ma więcej sesji niż reszta). |
| 0.7 | 2026-09-23 | VIX usunięty z projektu (D8). Dashboard przepisany: nawigacja Start / Wykresy / Strategie / Inwestor, bez paska danych na dole. Automat łapie świecę w ciągu minuty od zamknięcia (ponowienia co 30 s) i sam łata luki w wolnych przebiegach. Katalog 84 sygnałów bazowych wyciągnięty z arkusza do `S1_KATALOG_BAZOWY.md`. D4–D6 przyjęte, nowe decyzje D8–D16 z krytycznego przeglądu. Luka L17. |
| 0.8 | 2026-09-23 | Decyzje D9–D16 rozstrzygnięte. **Wolumen zbierany** (D12): pole `volume` w świecach głównych, tablica `v` w sesjach, kolumna `v` w parquet. Próg wykrywania splitu obniżony 30% → 15% (D11). Tryb szybki czeka tylko na 3 spółki główne (D15). Wolumen jako rodzina parametrów w Etapie 3, Etap 3 opisany jako ciągłe, wielodniowe przeszukiwanie z zapisem postępu. |
| 0.9 | 2026-09-23 | Ponowne pobranie całej historii, żeby wszystkie świece miały wolumen (D12). `History.gs`: data startu 2026-09-02 → 2026-09-23 (trzy tygodnie wypadały z zakresu), tempo 2 dni co 10 min → 5 dni co 5 min. Opisany porządek i budżet zapisów przy pełnym pobraniu. Luka L18. |
| 1.0 | 2026-09-24 | **Baza wyczyszczona i pobierana od zera**, żeby cała historia miała wolumen (D12). Nowa funkcja `resetAfterWipe()` i pozycja menu — zeruje stan pobierania po ręcznym skasowaniu bazy w konsoli Firebase (bez tego automat uznaje, że wszystko już ma). Okres 2026-09-09 – 2026-09-23 świadomie porzucony: zostanie pobrany razem z resztą historii. |
| 0.10 | 2026-09-23 | (numeracja dwuczłonowa — 0.10 następuje po 0.9.) Zamiast ręcznego pobrania historii od nowa: automat **sam dopisuje wolumen** do starych świec w wolnych przebiegach, oknami po 60 dni, z dziennym budżetem 3000 dokumentów. Stare dane zostają — zapis nadpisuje je tymi samymi cenami plus wolumenem, a sesje, których Yahoo już nie zwraca, pozostają nietknięte. Menu: postęp i reset. |
| 0.11 | 2026-09-24 | Naprawa błędu z wersji 0.10: `patchOneGap_` i `volfillIfIdle_` nie ustawiały `symbol` na obiekcie świecy przed zapisem spółek głównych, więc `candleFields_` dostawał puste pole i Firestore odrzucał zapis (HTTP 400 „type unset"). Widoczne w STATS jako np. „AAPL 2026-01-30: …". Żadne dane nie zginęły — nieudany zapis nie przesuwa kursora, więc próby same się powtórzą teraz poprawnie. |

---

## 11. Dziennik pushów

Każdy push Claude do `main` zostawia tu wiersz (zasada 2.7). Godziny w czasie polskim.

| Data i godzina | Commit | Pliki | Co |
|---|---|---|---|
| 2026-09-23 17:02 | `d72cf9a` | `IA4_INSTRUKCJA.md` | Wersja 0.4: zasada 2.6 (praca przez GitHub), dogonienie pliku do stanu 0.3 — poprawka WMT i lista 50 spółek kontrolnych. |
| 2026-09-23 17:06 | `93e078b` | — | Scalenie z `appsscript.json` dodanym równolegle przez użytkownika. Bez zmian treści. |
| 2026-09-23 17:11 | `8d198e1` | `Proof.gs` | Naprawa `startProof()`: zapisany stan z trybu `refresh` sprawiał, że „Pobierz historię” po cichu kontynuowało uzupełnianie 40 dni zamiast pełnej historii. Log przy cichym „brak danych” z Yahoo. |
| 2026-09-23 17:21 | `93b461d` | `IA4_INSTRUKCJA.md`, `Code.gs`, `History.gs`, `Proof.gs`, `Project.gs`, `ia4-dashboard.html`, `ia4-research/*` | Wersja 0.5: zasada 2.7, jednolite nagłówki wersji, `INSTRUCTION_VERSION` 0.2 → 0.5, Etap 0B — folder `ia4-research/` (config, sync, data, verify, README), luki L13–L15. |
| 2026-09-23 17:24 | `f7b0e40` | `IA4_INSTRUKCJA.md` | Uzupełnienie hasha poprzedniego pushu i doprecyzowanie zasady 2.7 o kolejności wpisywania hasha. |
| 2026-09-23 22:23 | `af72e4b` | `Proof.gs`, `Code.gs`, `IA4_INSTRUKCJA.md` + wersje | Wersja 0.6: `refetchProof()` + menu „Pobierz ponownie wybrane…”, naprawa skutku L13 dla 10 spółek bez pełnego resetu. Luka L16. |
| 2026-09-23 23:01 | `c4a2f7e` | wszystkie pliki | Wersja 0.7: usunięcie VIX, nowy dashboard, szybkie łapanie świecy + samoczynne łatanie luk, katalog 84 sygnałów, decyzje D8–D16. |
| 2026-09-23 23:33 | `c7bdb70` | `Code.gs`, `Project.gs`, `ia4-research/*`, `IA4_INSTRUKCJA.md` | Wersja 0.8: wolumen (D12), próg splitu 15% (D11), priorytet 3 głównych w trybie szybkim (D15), decyzje D9–D16 rozstrzygnięte. |
| 2026-09-23 23:44 | `b3b1b17` | `History.gs`, `IA4_INSTRUKCJA.md` + wersje | Wersja 0.9: przygotowanie do pełnego pobrania historii z wolumenem — data startu i tempo w `History.gs`, luka L18. |
| 2026-09-23 23:47 | `c4fdbf3` | `Project.gs`, `Code.gs`, `IA4_INSTRUKCJA.md` + wersje | Wersja 1.0: `resetAfterWipe()` + menu, przygotowanie do pobrania całej historii od zera z wolumenem. |
| 2026-09-23 23:49 | `3f9573a` | `Code.gs`, `IA4_INSTRUKCJA.md` + wersje | Wersja 0.10: samoczynne dopisywanie wolumenu do starej historii z dziennym budżetem zapisów. |
| 2026-09-24 10:11 | `d27ae75` | `Code.gs`, `IA4_INSTRUKCJA.md` + wersje | Wersja 0.11: naprawa brakującego `symbol` w łataniu luk i dopisywaniu wolumenu (HTTP 400 „type unset"). |
