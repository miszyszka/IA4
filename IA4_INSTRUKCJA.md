# IA 4 — instrukcja projektu

**Wersja:** 0.22
**Data:** 25 września 2026
**Aktualny etap:** 🟨 Etap 0 — 0A wdrożone; trwa pełne pobieranie historii po naprawie L13, przegląd 53 luk i budowa środowiska Pythona (0B)

Ten plik jest jedynym źródłem prawdy o tym, jak pracujemy nad projektem. Stan bieżący (który etap, co zrobione, jakie luki) jest widoczny na żywo w arkuszu **PROJEKT** i w podsumowaniu w **STATS**. Jeśli plik i arkusz się rozjeżdżają, obowiązuje ten plik, a rozbieżność trzeba zapisać jako lukę.

---

## 1. Cel projektu

Znaleźć sygnały wejścia w transakcje na świecach godzinowych, które mają **realną, powtarzalną przewagę** — potwierdzoną poza danymi, na których je znaleziono — a następnie sprawdzić je w działaniu na żywo, najpierw jako monitor sygnałów, potem jako wirtualny inwestor.

Miara sukcesu nie jest najwyzszy zysk w backtescie, tylko przewaga, ktora przetrwa cztery sprawdziany: spolki kontrolne, poletko, skarbiec danych i dane na zywo.

### Czego konkretnie szukamy

Koncowym produktem ma byc **regula zero-jedynkowa**: po zamknieciu swiecy godzinowej system odpowiada „wchodzic" albo „nie wchodzic", bez uznaniowosci. Regula sklada sie z trzech czesci:

1. **sygnal** - warunek na cenie i wolumenie, ktory odpala sie sam (katalog S1 -> lista S2),
2. **rating PT** - liczba 1-100 mowiaca, czy akurat to wystapienie sygnalu jest warte zachodu (Etap 3),
3. **zasady wyjscia** - SL, TP i limit czasu, ustalone razem z sygnalem, nie dobierane pozniej.

Wejscie nastepuje wtedy i tylko wtedy, gdy sygnal odpalil **i** PT jest powyzej progu. Zadnego „wyglada dobrze", zadnego dobierania wielkosci pozycji pod przeczucie.

### Kiedy uznamy, ze sie udalo

Do handlu prawdziwymi pieniedzmi kwalifikuje sie regula, ktora **jednoczesnie**:

- ma dodatnia ekspektancje po kosztach z zapasem (5.11) w grupie glownej **i** kontrolnej osobno,
- przetrwala poletko i skarbiec bez strojenia miedzy jednym a drugim (5.1),
- daje wystarczajaco duzo sygnalow, zeby mialo to sens - propozycja progu: **min. 50 transakcji rocznie** na instrument przy trzech spolkach glownych,
- w Etapie 5 (paper trading) osiagnela wynik **mieszczacy sie w przedziale przewidzianym przez backtest**, na min. 100 transakcjach.

Ostatni punkt jest wazniejszy, niz wyglada: chodzi o **zgodnosc z przewidywaniem**, nie o sam zysk. Strategia, ktora w backtescie dawala 0,2% na transakcje, a na zywo daje 0,8%, jest tak samo podejrzana jak ta, ktora daje -0,1% - w obu wypadkach model nie rozumie tego, co sie dzieje.

### Czego NIE szukamy

Zeby nie tracic czasu: nie szukamy prognozy ceny, nie budujemy portfela optymalnego, nie zajmujemy sie wielkoscia pozycji ani dzwignia, nie handlujemy niczym poza tymi trzema spolkami. Grupa kontrolna sluzy **wylacznie do sprawdzania**, czy przewaga jest prawdziwa - nie handlujemy nia.

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

8. **Telemetria zamiast wklejania.** Stan systemu (etap, kryteria, luki, błędy, postęp zadań, dziennik) jest publikowany automatycznie do `telemetry/state.json` w repozytorium. Na początku rozmowy o kodzie Claude czyta ten plik zamiast prosić o wklejenie podsumowania z arkusza. Jeśli plik jest starszy niż kilka godzin, warto poprosić o „Wyślij stan do GitHub teraz" albo sprawdzić, czy trigger telemetrii działa.

---

## 3. Architektura

| Warstwa | Narzędzie | Rola | Etapy |
|---|---|---|---|
| Zbieranie danych | Google Apps Script | świece 1h na żywo i historia | stale |
| Magazyn danych | Firestore | **jedyne** źródło danych świecowych | wszystkie |
| Badania | Python na Macu | katalog S1, backtest, parametry towarzyszące, model PT — wynik (S2, PT) commitowany do GitHub (D18) | 1–3 |
| Monitoring | arkusze STATS i PROJEKT | stan systemu, etapów i luk | wszystkie |
| Sygnały na żywo | Apps Script, zaraz po dopisaniu świecy (D2) | wykrywanie sygnałów S3 co godzinę | 4 |
| Paper trading | Apps Script + arkusz | wirtualny inwestor | 5 |
| Podgląd | dashboard HTML | wykresy 3 spółek głównych | — |

**Dlaczego badania w Pythonie już od Etapu 1, a nie od 3:** nowy katalog to ok. 24 000 strategii x 53 instrumenty. Apps Script ma limit 6 minut na uruchomienie i liczyłby to wiele godzin w partiach. Python na Macu policzy to w minutach. Apps Script zostaje przy tym, w czym jest dobry: praca na żywo, bez włączonego komputera.

### Pliki

| Plik | Rola | Los |
|---|---|---|
| `Code.gs` | automat biezacy, 53 instrumenty, STATS | zostaje |
| `History.gs` | historia 3 spółek głównych | zostaje |
| `Proof.gs` | historia 50 spółek kontrolnych i tła rynku (SPY, QQQ) | zostaje |
| `Project.gs` | arkusz PROJEKT, skarbiec, audyt danych, sprzątanie | od Etapu 0 |
| `Telemetry.gs` | stan systemu → Firestore i GitHub | od wersji 0.12 |
| `Investor.gs` | arkusz `Transaction LOG` — wspólny log transakcji wszystkich inwestorów | od wersji 0.13 |
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

### 3.1 Dwa magazyny danych — i dlaczego nie jeden (D18)

Świece i strategie/PT mają inną naturę, więc żyją w różnych miejscach:

| | Firestore | GitHub |
|---|---|---|
| Co | świece 1h, stan systemu, telemetria, inwestorzy (D17) | strategie S2, model PT, historia jego wersji |
| Jak się zmienia | co godzinę, bez przerwy, przez cały dzień handlowy | skokowo — raz na zamknięcie Etapu 2, potem przy każdym udoskonaleniu modelu PT |
| Czy potrzebny nasłuch na żywo | tak — zamknięcie świecy ma być sygnałem (Etap 4), dashboard i przyszły silnik inwestora (D17) muszą wiedzieć **natychmiast** | nie — Apps Script sprawdza raz na godzinę, czy jest nowsza wersja |
| Czy potrzebne wersjonowanie | nie — nikogo nie interesuje „poprzednia" świeca | tak — które strategie przeszły do S2, jaka wersja modelu PT dała jaki wynik |
| Limit dzienny | 50 000 odczytów / 20 000 zapisów (Spark) | 5000 zapytań/h (REST API), brak limitu na rozmiar repo w praktyce |

GitHub nie ma odpowiednika `onSnapshot` — sprawdzenie „czy coś się zmieniło" wymaga odpytywania, a zapis pliku to zawsze cała jego zawartość na nowo (nie da się dopisać jednej świecy). Dla strumienia świec na żywo to fatalny wybór; dla strategii, które zmieniają się rzadko i którym zależy na historii zmian, to naturalne środowisko — dokładnie to, czym Git jest.

**Pliki w repozytorium (`ia4-research/` commituje je z Maca, w miarę postępu Etapów 2–3):**

```
s2/strategies.json      lista S2 zamknięta na koniec Etapu 2: id, parametry, wynik backtestu,
                         wynik na skarbcu (po jego otwarciu), ocena, czy wybrana
pt/model.json           aktualne drzewa modelu PT (eksport z Etapu 3, zgodnie z D2):
                         wersja, data, próg PT, lista ~50 użytych parametrów, drzewa jako JSON
pt/history/RRRR-MM-DD_wersja.json
                         poprzednie wersje modelu — do porównań, gdy przeszukiwanie (Etap 3)
                         znajdzie lepszą zależność
```

**Jak Apps Script z tego korzysta.** `Code.gs` pobiera `pt/model.json` przez zwykłe, tanie `GET` (np. `raw.githubusercontent.com`, bez tokenu — repo jest publiczne) — raz na godzinę, sprawdzając wpierw commit hash, żeby nie ściągać pliku bez potrzeby. Model liczy się **lokalnie w Apps Script**, na świeżej świecy, zaraz po jej zapisaniu (Etap 4). Firestore w ogóle nie uczestniczy w tym zadaniu — zero dodatkowych odczytów.

**Kierunek przepływu jest jednostronny i świadomy:** Python na Macu **pisze** do GitHub (ma do tego token z prawem zapisu, tak jak Claude), Apps Script tylko **czyta** (bez tokenu, publiczny odczyt). Żadna strona nie musi rozwiązywać konfliktów zapisu, bo tylko jedna strona zapisuje.

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

  | Okres | Daty | Kto uzywa | Ile razy wolno zajrzec |
  |---|---|---|---|
  | **odkrywanie** | do 2025-09-30 | Etapy 1-3: szukanie sygnalow, strojenie, uczenie modelu | bez ograniczen |
  | **poletko** | 2025-10-01 - 2026-03-22 | sprawdzian po kazdym etapie | raz na etap |
  | **skarbiec** | 2026-03-23 - 2026-09-22 | jednorazowy sprawdzian koncowy | raz w calym projekcie |
  | **dane na zywo** | od 2026-09-23 | Etapy 4-5 | na biezaco |

  **Dlaczego trzy okresy, a nie dwa.** W pierwotnym planie skarbiec byl jedynym sprawdzianem poza danymi, na ktorych szukamy. To znaczy, ze przez caly Etap 1, 2 i 3 - tygodnie pracy - nie mielibysmy zadnego sygnalu, czy idziemy w dobrym kierunku, a pierwsza informacja zwrotna przyszlaby dopiero na koncu, gdy juz nie ma jak zareagowac. Poletko to tania przymiarka: po kazdym etapie sprawdzamy na nim wynik raz, i jesli przewaga znika, wiemy o tym od razu, zanim zbudujemy na niej kolejne pietro.

  Poletko nie zastepuje skarbca. Po kilku uzyciach (raz na etap) przestaje byc czyste - dobieranie decyzji pod jego wynik to to samo przeuczenie, tylko wolniejsze. Dlatego liczba zajrzen jest zapisana w arkuszu PROJEKT, a skarbiec pozostaje nietkniety do samego konca.

  Granice są zapisane w `Project.gs` (stała `PROJECT`) i w Firestore (`system/project`). Python czyta je z Firestore, nie z kodu.
- Skarbiec to **ciągły blok czasu**, nie losowe świece. Losowe świece przeciekałyby, bo sąsiednie świece dzielą wskaźniki i nakładające się transakcje.
- Etapy 1, 2 i 3 ucza sie i stroja **wylacznie na okresie odkrywania**. Poletko sluzy do sprawdzenia gotowego wyniku etapu, nie do strojenia.
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

### 5.7 Liczba testow

Przy ~24 000 strategii kilkaset wyglada swietnie czystym przypadkiem. **Konkretnie: przy progu "99. percentyl" spodziewamy sie okolo 240 strategii, ktore przejda wylacznie dzieki szczesciu.** Sam wysoki percentyl nie jest wiec zadnym filtrem - to jest najczestszy sposob, w jaki takie projekty same siebie oszukuja.

Obowiazuja trzy rzeczy naraz:

1. **Kontrola odsetka falszywych odkryc (FDR, metoda Benjamniego-Hochberga)** zamiast progu na pojedynczej strategii. Ustalamy z gory, jaki odsetek wybranych strategii godzimy sie miec falszywych (propozycja: 10%), i procedura sama wyznacza prog p-wartosci dla calego zestawu 24 000 testow. To jest wlasciwe narzedzie: Bonferroni przy tej liczbie testow wymagalby p < 2,1x10^-6, czego przy kilkuset transakcjach nie da sie osiagnac nawet przy prawdziwej przewadze.
2. **Licznik prób.** Kazda policzona konfiguracja - lacznie z tymi odrzuconymi po drodze i z przebiegami Etapu 3 - jest zapisywana. Bez tej liczby nie da sie policzyc poprawki. Etap 3 potrafi wykonac miliony prob w ciagu kilku dni i to one, a nie 24 000 z Etapu 2, decyduja o skali problemu.
3. **Potwierdzenie na poletku (5.1).** Poprawka statystyczna mowi, czy wynik moglby powstac przypadkiem na tych samych danych. Poletko mowi, czy utrzymuje sie na innych. Strategia musi przejsc oba sprawdziany.

### 5.8 Zapisy na żywo tylko dopisywane

Sygnały z Etapu 4 i transakcje z Etapu 5 są wyłącznie dopisywane, nigdy poprawiane wstecz. Błędy koryguje się nowym wpisem z adnotacją.

### 5.9 Odstep miedzy uczeniem a sprawdzianem

Transakcja otwarta blisko konca okresu uczenia trwa jeszcze H swiec i konczy sie juz w okresie sprawdzianu. Jej wynik zalezy od tych samych ruchow ceny, ktore sprawdzian ma oceniac - to jest przeciek, ktory potrafi zamienic zerowa przewage w pozornie swietna.

Dlatego przy kazdym podziale danych (walidacja kroczaca, poletko, skarbiec):
- **usuwamy z okresu uczenia** wszystkie transakcje, ktore koncza sie po jego granicy (*purging*),
- **odrzucamy poczatek okresu sprawdzianu** o dlugosci H swiec (*embargo*), zeby zadna transakcja uczaca w niego nie siegala.

Przy H = 70 swiec to 10 sesji po kazdej stronie granicy. Kosztuje kilka procent danych i jest tego warte.

### 5.10 Efektywna liczba obserwacji

Liczba wierszy w tabeli transakcji nie jest liczba niezaleznych obserwacji, i roznica jest tu bardzo duza:
- transakcja trwajaca H swiec **nakłada sie** na kolejne sygnaly tej samej spolki,
- **53 instrumenty reaguja na ten sam ruch rynku** w tej samej godzinie - 53 transakcje z jednego poranka to blizej jednej obserwacji niz pieciu dziesieciu.

Skutek: zwykle testy istotnosci, ktore zakladaja niezaleznosc, pokaza przewage tam, gdzie jej nie ma. Dlatego istotnosc liczymy **blokowym bootstrapem po czasie** (losujemy cale dni albo tygodnie, nie pojedyncze transakcje), a liczbe transakcji raportujemy razem z liczba **roznych dni**, w ktorych wystapily. Strategia z 500 transakcjami w 20 dniach jest czyms innym niz 500 transakcji w 300 dniach - i tylko ta druga cos znaczy.

### 5.11 Minimalna przewaga, ktora ma sens

Przewaga istotna statystycznie i przewaga oplacalna to dwie rozne rzeczy. Przy TP 0,5% i koszcie 0,05% (5.5) sam koszt zjada 10% zysku brutto, a do tego dochodzi poslizg przy wejsciu po cenie otwarcia nastepnej swiecy.

Dlatego strategia przechodzi dalej tylko wtedy, gdy **ekspektancja po kosztach jest dodatnia z zapasem**, nie tylko rozna od zera. Propozycja progu do potwierdzenia przed Etapem 2: ekspektancja po kosztach >= 0,05% na transakcje (czyli drugie tyle, co koszt). Strategia, ktora po kosztach daje 0,01% na transakcje, jest statystycznie moze i prawdziwa, ale handlowo bezwartosciowa - a kazda taka w zestawie rozcienczna te, ktore cos wnosza.

### 5.12 Co, jesli nic nie wyjdzie

To jest realny i powazny scenariusz, nie formalnosc: **wiekszosc takich poszukiwan nie znajduje trwalej przewagi**, i plan musi z gory powiedziec, co wtedy, zeby w tamtym momencie nie kusilo zlamanie zasady 5.1.

Dopuszczalne po nieudanym sprawdzianie na skarbcu:
- opisac, co nie zadzialalo, i zamknac projekt w tej formie,
- zaczac **nowy** projekt z nowym skarbcem, na nowych danych zebranych po tej dacie - czyli zaplacic za kolejna probe czasem, uczciwie,
- uzyc wynikow jako filtra negatywnego (wiemy, ktore hipotezy nie dzialaja) i handlowac dalej bez nich.

Niedopuszczalne: poprawienie modelu i ponowny sprawdzian na tym samym skarbcu. Drugi sprawdzian na tych samych danych nie jest sprawdzianem - to jest strojenie, tylko wolniejsze.

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
- **Limit czasu H**: wartosc wyjsciowa wedlug D5 (TP <= 1% -> 14 swiec, <= 2,5% -> 35, <= 5% -> 70), ale **H nie jest przeszukiwany jak SL/TP** (D10). Po policzeniu backtestu H jest wyznaczany z rozkladu czasu do celu (90. percentyl) i strategia liczona ponownie z ta jedna wartoscia. Dzieki temu H wynika z danych, a nie mnozy liczby testow.
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
- spolek kontrolnych na plusie z 50,
- **wynik osobno dla spolek rosnacych i spadajacych w okresie badawczym (D13)** - jesli przewaga jest tylko u rosnacych, to nie jest przewaga sygnalu, tylko dryfu,
- porównanie z wariantem przeciwnego kierunku,
- wskaźnik istotności z uwzględnieniem liczby testów (5.7).

Wynik trafia do arkusza **S2**. Użytkownik wybiera strategie do dalszej pracy, zaznaczając je w arkuszu. Claude proponuje filtry i ranking, ale nie wybiera za użytkownika.

**Czym jest arkusz S2.** Jeden wiersz = jedna strategia. Kolumny: `id_strategii`, parametry (sygnał, kierunek, SL, TP, H), wynik backtestu na okresie badawczym, wynik na skarbcu (wypełniany dopiero po jego otwarciu w Etapie 3), ocena Claude i pole wyboru „bierzemy". Strategie zaznaczone tu i tylko one przechodzą dalej. **Zamknięcie Etapu 2 zamyka listę S2** — po tym momencie jej skład się nie zmienia, bo inaczej Etap 3 liczyłby transakcje strategii, które dopiero co dołożyliśmy po obejrzeniu wyników. Zamknięta lista trafia do repozytorium jako `s2/strategies.json` (D18) — to ona, nie arkusz, jest wersją, z której korzysta Etap 3 i Apps Script.

**Kryteria ukonczenia:** wszystkie strategie policzone; **lista S2 sprawdzona raz na poletku** (5.1) - strategie, ktore tam traca przewage, wypadaja przed zamknieciem listy; lista zatwierdzona przez uzytkownika i zapisana (arkusz + `s2/strategies.json` w repozytorium, D18); w tym pliku zapisane kryteria, ktorymi sie kierowano, razem z liczba policzonych konfiguracji (5.7).

### Etap 3 — Parametry towarzyszące i rating PT → S3 ⬜

**Cel:** dla każdego sygnału S2 ocenić, w jakim kontekście działa, i nadać mu rating PT od 1 do 100.

**Czym jest arkusz S3.** Tu wiersz to **pojedyncza transakcja**, nie strategia. Każda strategia z zamkniętej listy S2 przechodzi backtest i zapisuje do S3 wszystkie swoje historyczne wejścia. Kolumny: `id_strategii`, `id_transakcji`, data i godzina wejścia, kierunek, cena wejścia i wyjścia, powód wyjścia (SL / TP / limit czasu), wynik, `rating_PT` policzony dla tej transakcji, oraz **`wieloznaczna`** — czy w świecy dało się osiągnąć i stop, i cel, więc wynik wynika z ostrożnego założenia „stop pierwszy" (5.4), a nie z danych. Udział takich transakcji jest osobną kolumną podsumowania, bo przy ciasnych SL/TP potrafi zdominować wynik.

**S3 musi dać się przeliczyć od nowa jednym poleceniem.** Baza warunków wyznaczających PT będzie się zmieniać w miarę, jak model szuka lepszych zależności; wtedy zmieniają się wszystkie ratingi. Dlatego S3 nie jest zapisem historycznym, tylko wynikiem, który za każdym razem powstaje na nowo z tych samych danych i bieżącej wersji modelu. Wersja modelu i data przeliczenia są zapisane w nagłówku arkusza.

**Czym jest rating PT.** PT to **liczba 1–100 przypisana pojedynczemu sygnałowi w chwili jego powstania** — percentyl przewidywanej jakości transakcji na tle wszystkich sygnałów tej samej strategii. 1 oznacza najgorszy procent sygnałów, 100 najlepszy. PT nie ocenia strategii (to robi S2), tylko **konkretne wystąpienie sygnału w konkretnym kontekście rynkowym**: ten sam sygnał DROP_N3 może mieć PT 20 w jednych warunkach i PT 85 w innych. Model liczący PT bierze parametry towarzyszące z chwili sygnału i zwraca przewidywaną jakość; próg PT decyduje, czy wchodzimy w transakcję.

**Zbior danych do uczenia:** kazda historyczna transakcja S2 z **okresu odkrywania** to jeden wiersz: parametry towarzyszace policzone w chwili sygnalu + wynik transakcji.

**Ile danych naprawde mamy - i co z tego wynika.** Okres odkrywania to ~260 sesji, czyli ~1800 swiec na instrument. Typowy sygnal odpala na ~5% swiec:

| Zbior | Transakcji | Obserwacji na 1 ceche przy 1000 cech |
|---|---|---|
| same 3 spolki glowne | ~270 | 0,3 |
| wszystkie 53 instrumenty | ~4800 | 4,8 |

Regula kciuka mowi o minimum 10-20 obserwacji na ceche. **Uczenie modelu o 1000 cechach na samych spolkach glownych jest z gory skazane na przeuczenie** - model nauczy sie szumu i pokaze swietny wynik, ktory rozsypie sie na poletku. Stad dwie wiazace decyzje:

1. **Model PT uczy sie na wszystkich 53 instrumentach naraz**, nie osobno na kazdym i nie tylko na glownych. Spolka wchodzi do modelu jako cecha (sektor, zmiennosc, kapitalizacja), a nie jako osobny model. Kontrola z 5.6 przenosi sie na sprawdzian: model uczony na wszystkich musi dzialac w obu grupach osobno.
2. **Cechy redukujemy przed uczeniem, nie w jego trakcie.** ~1000 parametrow to material na przesiew (punkt 1 metody), nie na wejscie modelu. Do modelu trafia najwyzej ~50, a **wybor tych 50 jest czescia procedury walidacji** - jesli wybierzemy je patrzac na cale dane, a potem sprawdzimy model walidacja kroczaca, to sprawdzian jest juz skazony. Wybor cech musi odbywac sie wewnatrz kazdego okna uczenia osobno (walidacja zagniezdzona).

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
11. Szerokosc rynku z naszych 53 instrumentow — ile jest powyżej średnich, ile spadło dziś, średni zwrot grupy.
12. Kontekst sygnału — ile razy wystąpił ostatnio, czas od poprzedniego, czy inne sygnały S2 odpaliły jednocześnie.

**Skala obliczeń.** Etap 3 nie jest jednym przebiegiem, tylko **ciągłym przeszukiwaniem**: model liczy się na Macu godzinami albo dniami, przechodząc kolejne kombinacje parametrów, okna czasowe i progi, i zapisuje najlepsze znalezione zależności wraz z datą i wynikiem walidacji. Każdy kolejny przebieg startuje od zapisanego stanu i próbuje go poprawić. Dlatego kod Etapu 3 musi od początku: zapisywać postęp na dysk po każdej rundzie (przerwanie nie może kasować pracy), logować każdą sprawdzoną konfigurację z wynikiem, żeby dało się odtworzyć, ile prób wykonano (5.7), i nigdy nie dotykać skarbca (`data.load` pilnuje tego programowo).

**Metoda:**
1. **Przesiew pojedynczych parametrów** — dla każdego parametru: jak zmienia się skuteczność w jego przedziałach, na ilu transakcjach, czy efekt powtarza się w obu grupach spółek i w kolejnych okresach czasu. Wynik: czytelna lista w stylu „80% transakcji zakończonych stopem wypadło przy cenie poniżej SMA(140)”.
2. **Model zależności** — zespół drzew decyzyjnych (gradient boosting). Robi dokładnie to, co opisałeś jako sieć zależności: bierze najbardziej obiecujący parametr, dzieli po nim dane, a w każdej części szuka kolejnego. Sieć neuronowa nie jest tu dobrym wyborem: przy kilku tysiącach transakcji i tysiącu parametrów przeuczy się niemal na pewno, a drzewa radzą sobie z takimi danymi lepiej i dają się zinterpretować.
3. **Walidacja kroczaca** w okresie odkrywania - model uczony na starszych danych, sprawdzany na nowszych, kilka razy z przesunieciem. Obowiazkowo z purging i embargo (5.9) oraz z wyborem cech wewnatrz kazdego okna (patrz wyzej). Wynik raportujemy jako rozrzut miedzy oknami, nie srednia: model, ktory dziala swietnie w trzech oknach i fatalnie w dwoch, jest gorszy niz rowny, choc srednia moze byc ta sama.
4. **PT 1–100** = percentyl przewidywanej jakości transakcji (1 — najgorszy 1% sygnałów, 100 — najlepszy).
5. **Prog PT** dobierany na walidacji kroczacej. Raportujemy tez, ile transakcji zostaje po odcieciu - prog, ktory przepuszcza 5% sygnalow, moze dac swietna ekspektancje na 30 transakcjach rocznie i byc bezuzyteczny w praktyce.
6. **Sprawdzian na poletku** (5.1) - raz, po ustaleniu modelu i progu. Jesli przewaga tu znika, wracamy do pracy bez otwierania skarbca.
7. **Jednorazowy sprawdzian na skarbcu** (5.1) - dopiero gdy poletko potwierdzilo.

**Ograniczenie z decyzji D2:** model PT będzie liczony w Apps Script, zaraz po dopisaniu świecy. Dlatego ostateczny model musi być przenośny:
- przesiew obejmuje ~1000 parametrów, ale model używa najwyżej ~50,
- drzewa są eksportowane z Pythona jako JSON i wykonywane w Apps Script,
- każdy parametr jest liczony identycznie w obu językach — test zgodności na tych samych świecach jest częścią kryteriów ukończenia.

**Model żyje w repozytorium, nie w Firestore (D18):** `ia4-research` commituje go jako `pt/model.json`, a poprzednie wersje trafiają do `pt/history/` — Etap 3 to ciągłe przeszukiwanie (sekcja opisana wyżej), więc model będzie się zmieniał wielokrotnie i każda zmiana zasługuje na własny commit. Apps Script czyta `pt/model.json` raz na godzinę, licząc PT lokalnie na świeżej świecy — zero dodatkowych odczytów Firestore na to zadanie.

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

**Wielu inwestorów naraz.** Nie jeden portfel, tylko dowolna liczba niezależnych — każdy z własnym zestawem strategii S2, własnym progiem PT i własnymi limitami. Dzięki temu porównanie „co by było, gdyby" dzieje się na tych samych danych i w tym samym czasie, zamiast po kolei. Ustawienia każdego inwestora (zakładka w dashboardzie):

| Ustawienie | Rola |
|---|---|
| kapitał początkowy | punkt odniesienia dla wyniku |
| kapitał na transakcję | ile wchodzi w jedną pozycję |
| maks. pozycji na jednej świecy | ile sygnałów z tej samej świecy wolno przyjąć |
| maks. otwartych pozycji | ile pozycji może żyć jednocześnie |
| strategie S2 | lista wyboru — kilka strategii naraz |
| najniższy dopuszczalny PT | sygnały poniżej progu są pomijane |

**Statystyki odrzuceń są równie ważne jak wynik.** Każdy inwestor liczy osobno, ile sygnałów odrzucił z powodu limitu na świecę, limitu otwartych pozycji i progu PT. Wysoki odsetek odrzuceń znaczy, że wynik nie pochodzi ze strategii, tylko z tego, które sygnały akurat zmieściły się w limitach — a to zupełnie inna informacja niż „strategia działa". Do tego średnie dzienne: ile sygnałów, ile transakcji, jaki wynik.

**Log w arkuszu.** Wszystkie transakcje wszystkich inwestorów trafiają do jednego arkusza `Transaction LOG` (`Investor.gs`), z kolumną `inwestor` do filtrowania. Powielone transakcje między inwestorami o podobnych ustawieniach są oczekiwane — filtrowanie po jednym inwestorze rozwiązuje to w Excelu. Kolumny obejmują parametry wejścia i wyjścia, PT sygnału, próg inwestora, powód wyjścia, `wieloznaczna` (5.4) oraz biegnącą skuteczność i ekspektancję.

**Jak dlugo i po czym poznamy wynik.** Paper trading trwa do uzbierania **min. 100 transakcji** (przy spodziewanej czestosci sygnalow to kilka miesiecy) - wczesniejsze wnioski nie maja podstaw. Wynik oceniamy przez **zgodnosc z przewidywaniem backtestu**, nie przez sam zysk: liczymy przedzial ufnosci ekspektancji z backtestu i sprawdzamy, czy wynik na zywo sie w nim miesci. Wynik znaczaco lepszy od przewidywanego traktujemy jako ostrzezenie, nie sukces - najczestsza przyczyna jest blad w liczeniu, a nie nadzwyczajna przewaga.

Do ustalenia na poczatku etapu: priorytet przy wielu sygnalach naraz (propozycja: wyzszy PT pierwszy), zachowanie przy kolejnym sygnale na tej samej spolce, koszty.

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

**Telemetria — pełny stan systemu dla Claude.** `Telemetry.gs` zbiera w jeden dokument JSON wszystko, co Claude musiałby inaczej dostać wklejone ręcznie: etap i kryteria (liczone tą samą funkcją co arkusz PROJEKT, więc nie mogą się rozjechać), pełną listę luk ze statusami i komentarzami, tabelę instrumentów z ostatniego audytu, stan każdej spółki w automacie, błędy, postęp pobierania historii i dopisywania wolumenu, listę triggerów oraz ostatnie 80 wpisów dziennika. Dokument trafia do `system/telemetry` w Firestore (źródło prawdy, czyta go też dashboard) i do repozytorium jako `telemetry/state.json` plus dzienna migawka `telemetry/history/RRRR-MM-DD.json`.

Wysyłka idzie **z Apps Script do GitHub**, a nie odwrotnie. Rozważaliśmy automat w repozytorium odpytujący Firestore co 10 minut; ma trzy wady, których to rozwiązanie nie ma: wymagałby drugiej kopii klucza serwisowego Firebase jako sekretu GitHuba (wbrew 6.5), zadania cykliczne na GitHubie potrafią spóźniać się kilkanaście minut lub zostać pominięte, a odpytywanie zużywałoby odczyty Firestore także wtedy, gdy nic się nie zmieniło. Apps Script wie, kiedy coś się zmieniło, więc wysyła tylko wtedy — porównuje sumę kontrolną **treści** dokumentu (z pominięciem czasu wygenerowania i czasu ostatniego przebiegu — inaczej każda godzina wyglądałaby jak zmiana) i pomija wysyłkę, gdy nic się nie zmieniło, z minimalnym odstępem 10 minut. Token GitHub leży w Script Properties pod kluczem `GITHUB_TOKEN`, ustawiany z menu; **nigdy nie trafia do repozytorium ani do arkusza**.

Menu: IA 4 → Projekt → **Wyślij stan do GitHub teraz** / **Ustaw token GitHub** / **Włącz telemetrię co godzinę**.

**Dopisywanie wolumenu do starej historii** (D12): świece zebrane przed wersją 0.8 nie mają wolumenu. Zamiast pobierać wszystko od nowa (~37 000 zapisów, czyli dwa dni ponad dzienny limit Firestore), automat uzupełnia je sam. W przebiegach, w których nie ma nic do zebrania, cofa się po historii każdego instrumentu oknami po 60 dni i zapisuje te same świece ponownie — tym razem z wolumenem. Kolejność jak w `liveSymbols_()`: najpierw trzy spółki główne. Dzienny budżet 3000 dokumentów pilnuje, żeby uzupełnianie nigdy nie zabrało limitu bieżącym świecom; całość zajmuje ok. dwóch tygodni bez niczyjej uwagi. Luki mają pierwszeństwo — wolumen dopisuje się dopiero, gdy nie ma nic do załatania. Postęp: menu IA 4 → Projekt → **Postęp dopisywania wolumenu**.

**Blokada po wyczerpaniu limitu.** Pierwszy błąd 429 z Firestore zapala blokadę na resztę doby pacyficznej (limit resetuje się o północy czasu pacyficznego, ok. 9:00 w Polsce). Zadania w tle — dopisywanie wolumenu, łatanie luk, zapis telemetrii do Firestore — same się wtedy wstrzymują, bez logowania. Do wersji 0.18 każde z nich próbowało dalej co kilka minut do końca doby, zapełniając dziennik identycznymi komunikatami, przez które nie było widać prawdziwych zdarzeń. **Zbieranie świec na żywo nie jest blokowane** — to najważniejsze zadanie systemu i ma próbować do skutku. Blokada zdejmuje się sama przy pierwszym udanym zapisie następnego dnia, a telemetria wprost pokazuje ten stan (pole `collector.quota`), żeby nie mylić go z awarią.

**Ochrona limitu odczytów Firestore (50 000 dziennie, ten sam limit co przy zapisach).** Do wersji 0.15 dashboard subskrybował całe kolekcje świec bez ograniczenia — jedno otwarcie strony czytało pełną historię trzech spółek głównych (dziś ~10 800 odczytów za jedno wejście), a każda zmiana zakresu czy powrót po zerwanym połączeniu powtarzał to od nowa. Dwie zmiany to naprawiają:
- **Dashboard** czyta tylko tyle świec, ile potrzeba: 8 najnowszych na spółkę na stronie startowej (do statystyk dnia), a na Wykresach i u Inwestorów — tyle, ile odpowiada wybranemu zakresowi (60 świec dla tygodnia, do 4000 dla „Całości"), z nasłuchem odłączanym przy zmianie zakresu czy zejściu z widoku. Redukcja: ponad 99% dla zwykłego otwarcia strony.
- **Pełny audyt** (jedyne zadanie po stronie Apps Script czytające dużo — cała historia każdego instrumentu) ma budżet dzienny 35 000 odczytów, żeby zostawić miejsce dla dashboardu i innych zadań. Po wyczerpaniu wstrzymuje się i kończy następnego dnia, nie tracąc postępu. Uruchomienie go drugi raz tego samego dnia wymaga potwierdzenia — sam algorytm już raz ostrzega.

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
| L12 | Kryteria etapów i status decyzji są w dwóch miejscach: ten plik oraz `STAGES`/`DECISIONS` w `Project.gs` | mogą się rozjechać — realny przypadek w 0.21: D4–D6 dostały ✅ w wersji 0.7 (2026-09-23), ale twarda kopia w `DECISIONS` przez dwa dni nadal pokazywała w arkuszu PROJEKT „🔸 domyślna — potwierdzić przed Etapem 1” | przy każdej nowej wersji instrukcji aktualizujemy oba; w razie rozjazdu obowiązuje ten plik (zasada z nagłówka) |
| L13 | „Uzupełnij najnowsze” kasowało stan i przełączało tryb na `refresh`, a „Pobierz historię” po cichu go kontynuowała | 26 nowych spółek kontrolnych i tło rynku miały po 5–28 sesji zamiast ~500, bez ostrzeżenia w STATS (flaga „niepełna historia” nie działa w trybie `refresh`) | naprawione w 0.5: `startProof()` odrzuca stan spoza trybu `full`. Dane nie ucierpiały — Firestore tylko dopisuje |
| L14 | 26 spółek kontrolnych i tło rynku nadal mają historię krótszą niż okres badawczy | nie nadają się do Etapów 1–3, bo cała ich historia leży w skarbcu albo po nim | pełne pobranie po wdrożeniu 0.5; `verify.py` wypisuje takie instrumenty osobno |
| L19 | Dashboard subskrybował całe kolekcje świec bez ograniczenia | jedno otwarcie strony czytało pełną historię (~10 800 odczytów), grożąc wyczerpaniem dziennego limitu Firestore przy zwykłym korzystaniu | naprawione w 0.15: ograniczone zapytania (limit zależny od zakresu) zamiast całej kolekcji, nasłuch odłączany przy zmianie widoku |
| L18 | Historia sprzed wersji 0.8 nie ma wolumenu, a przepisanie jej to ~37 000 zapisów przy limicie 20 000 dziennie | przez ok. dwa tygodnie część historii ma wolumen, a część nie — parametry wolumenowe policzone w tym czasie byłyby liczone na niepełnych danych | automat dopisuje wolumen sam, 3000 dokumentów dziennie, najpierw spółki główne; nie liczyć parametrów wolumenowych, dopóki menu „Postęp dopisywania wolumenu" nie pokaże, że skończone |
| L20 | `patchOneGap_` uznawał łatanie za sukces, gdy Yahoo zwróci cokolwiek — nie sprawdzał, czy to były brakujące świece | trwałe luki (np. przerwa Yahoo z L3) były "łatane" w kółko co 10 minut w nieskończoność, bo te same istniejące świece zawsze wracały; dziennik zdarzeń zapychał się identycznymi wpisami | naprawione w 0.17: `patchOneGap_` porównuje zwrócone numery świec z brakującymi (`gained`); po 3 próbach bez postępu luka jest automatycznie zapisywana jako `zaakceptowana` w `_AUDYT_DECYZJE` z komentarzem, i znika z kolejki |
| L15 | Historia z Yahoo sięga ~730 dni, więc nowo dodane instrumenty nigdy nie dogonią tych z 2024 r. | grupa kontrolna ma dwa pokolenia: ~506 sesji i tyle, ile zdążyło się zebrać | jeśli po pełnym pobraniu różnica zostanie, zapisać ją jako świadomy kompromis i uwzględniać przy wymogu 5.6 |

| L21 | Trwający pełny audyt był nieodróżnialny od zepsutego: `audit.fullAt` aktualizuje się dopiero po ostatnim symbolu, więc przez cały przebieg (dziesiątki minut przy 55 instrumentach) wszystkie widoki pokazywały datę poprzedniego audytu, a kryterium 0.6 liczyło luki z niedokończonego przebiegu | fałszywy alarm „audyt nie zapisuje daty" i mylące liczby luk w trakcie audytu; realne ryzyko, że ktoś zacznie naprawiać działający kod | naprawione w 0.20: `auditProgress_()` w `Project.gs`, postęp widoczny w kryteriach 0.5 i 0.6, w arkuszu PROJEKT i w telemetrii (`jobs.fullAudit`) |

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
| D17 | Gdzie żyją inwestorzy | Ustawienia inwestorów przenoszą się z przeglądarki do Firestore (`investors/{id}`), a silnik działa w Apps Script: po zapisaniu każdej świecy godzinowej automat przechodzi po aktywnych inwestorach, czyta ich ustawienia i otwarte pozycje, sprawdza sygnały S3 i ich PT, zamyka pozycje, które w minionej świecy dotknęły SL albo TP, i otwiera nowe w granicach limitów. Dashboard przestaje być miejscem, gdzie cokolwiek się liczy — tylko pokazuje. Wdrożenie: Etap 5. | ✅ przyjęta |
| D18 | Gdzie żyją strategie S2 i model PT | Firestore ma darmowy dzienny limit (50 000 odczytów, 20 000 zapisów) i żadnego wersjonowania — dwie rzeczy, które akurat świecom nie przeszkadzają (płyną bez przerwy, nikt nie musi widzieć „poprzedniej wersji" świecy), ale strategiom i modelowi PT bardzo. Podział: **świece i wszystko na żywo zostają w Firestore** (nasłuch w czasie rzeczywistym, którego Git nie ma; opisane niżej w sekcji 3.1). **Strategie S2 i model PT przenoszą się do repozytorium GitHub** jako pliki JSON — tam, gdzie i tak mają trafić zgodnie z D2 (eksport modelu PT do Apps Script). Szczegóły w sekcji 3.1. | ✅ przyjęta |
| D16 | Prog „przewagi" | **Zmieniony w 0.19** - poprzednia wersja (99. percentyl) przepuszczalaby ~240 strategii czystym przypadkiem przy 24 000 testow. Obowiazuja teraz jednoczesnie: (a) **minimum 100 transakcji w grupie glownej i 300 w kontrolnej**, rozlozonych na **min. 30 roznych dni** (5.10); (b) przewaga nad wejsciem losowym dodatnia **w obu grupach osobno**; (c) istotnosc liczona **blokowym bootstrapem** i przepuszczona przez **kontrole FDR na poziomie 10%** dla calego zestawu testow (5.7); (d) **ekspektancja po kosztach >= 0,05% na transakcje** (5.11); (e) **potwierdzenie na poletku** - przewaga utrzymuje sie na danych, ktorych strojenie nie widzialo. Strategia musi spelnic wszystkie piec. | ✅ przyjęta |

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
| 0.7 | 2026-09-23 | VIX usunięty z projektu (D8). Dashboard przepisany: nawigacja Start / Wykresy / Strategie / Inwestor, bez paska danych na dole. Automat łapie świecę w ciągu minuty od zamknięcia (ponowienia co 30 s) i sam łata luki w wolnych przebiegach. Katalog 84 sygnałów bazowych wyciągnięty z arkusza do `S1_KATALOG_BAZOWY.md`. D4–D6 przyjęte, nowe decyzje D8–D16 z krytycznego przeglądu. Luka L17 (wycofana w 0.18 — patrz niżej). |
| 0.8 | 2026-09-23 | Decyzje D9–D16 rozstrzygnięte. **Wolumen zbierany** (D12): pole `volume` w świecach głównych, tablica `v` w sesjach, kolumna `v` w parquet. Próg wykrywania splitu obniżony 30% → 15% (D11). Tryb szybki czeka tylko na 3 spółki główne (D15). Wolumen jako rodzina parametrów w Etapie 3, Etap 3 opisany jako ciągłe, wielodniowe przeszukiwanie z zapisem postępu. |
| 0.9 | 2026-09-23 | Ponowne pobranie całej historii, żeby wszystkie świece miały wolumen (D12). `History.gs`: data startu 2026-09-02 → 2026-09-23 (trzy tygodnie wypadały z zakresu), tempo 2 dni co 10 min → 5 dni co 5 min. Opisany porządek i budżet zapisów przy pełnym pobraniu. Luka L18. |
| 1.0 | 2026-09-24 | **Baza wyczyszczona i pobierana od zera**, żeby cała historia miała wolumen (D12). Nowa funkcja `resetAfterWipe()` i pozycja menu — zeruje stan pobierania po ręcznym skasowaniu bazy w konsoli Firebase (bez tego automat uznaje, że wszystko już ma). Okres 2026-09-09 – 2026-09-23 świadomie porzucony: zostanie pobrany razem z resztą historii. |
| 0.10 | 2026-09-23 | (numeracja dwuczłonowa — 0.10 następuje po 0.9.) Zamiast ręcznego pobrania historii od nowa: automat **sam dopisuje wolumen** do starych świec w wolnych przebiegach, oknami po 60 dni, z dziennym budżetem 3000 dokumentów. Stare dane zostają — zapis nadpisuje je tymi samymi cenami plus wolumenem, a sesje, których Yahoo już nie zwraca, pozostają nietknięte. Menu: postęp i reset. |
| 0.11 | 2026-09-24 | Naprawa błędu z wersji 0.10: `patchOneGap_` i `volfillIfIdle_` nie ustawiały `symbol` na obiekcie świecy przed zapisem spółek głównych, więc `candleFields_` dostawał puste pole i Firestore odrzucał zapis (HTTP 400 „type unset"). Widoczne w STATS jako np. „AAPL 2026-01-30: …". Żadne dane nie zginęły — nieudany zapis nie przesuwa kursora, więc próby same się powtórzą teraz poprawnie. |
| 0.12 | 2026-09-24 | Nowy plik `Telemetry.gs`: pełny stan systemu do `system/telemetry` w Firestore i do `telemetry/state.json` w repozytorium (plus dzienne migawki), wysyłany przy zmianie treści, nie w odstępach. Zasada 2.8. Doprecyzowana metodologia: czym jest arkusz **S2** (wiersz = strategia), arkusz **S3** (wiersz = transakcja, przeliczalny od nowa po zmianie modelu, z kolumną transakcji wieloznacznych) i czym jest **rating PT** (1–100 dla pojedynczego wystąpienia sygnału, nie dla strategii). |
| 0.13 | 2026-09-24 | Dashboard: zakładka Inwestorzy przepisana na **wielu niezależnych inwestorów** — własne ustawienia (kapitał, kapitał na transakcję, limit na świecę, limit otwartych, wybór strategii S2, próg PT), zmiana nazwy, start/stop osobno dla każdego. Statystyki odrzuceń z trzech powodów i średnie dzienne. Uproszczony wykres trzech spółek znormalizowany do procentu ze znacznikami wejść i wyjść. Nowy `Investor.gs`: arkusz `Transaction LOG` wspólny dla wszystkich inwestorów, zasilany z Firestore. Etap 5 opisany na nowo. |
| 0.14 | 2026-09-24 | Poprawki znalezione dzięki telemetrii: tabela instrumentów czytana z `st.audit.stats` zamiast `st.stats` (była pusta), nowa funkcja `cleanupRemovedSymbols()` usuwająca pozostałości po instrumentach wyrzuconych z projektu — wpis w stanie automatu, luki w audycie i miejsce w kolejce wolumenu (dotyczy VIX, D8). Decyzja D17: ustawienia inwestorów przenoszone z przeglądarki do Firestore. |
| 0.15 | 2026-09-24 | Ochrona przed przekroczeniem dziennego limitu 50 000 odczytów Firestore (przyczyna dzisiejszego przekroczenia widocznego w konsoli Firebase). Dashboard: skończone zapytania zamiast subskrypcji całych kolekcji — 8 świec dla strony startowej, zależny od zakresu limit dla Wykresów i Inwestorów, odłączanie nasłuchu przy zmianie widoku. Pełny audyt: dzienny budżet 35 000 odczytów z bezpiecznym wstrzymaniem i ochroną przed przypadkowym drugim uruchomieniem tego samego dnia. Luka L19. |
| 0.16 | 2026-09-24 | Decyzja D18: strategie S2 i model PT trafiają do repozytorium (`s2/strategies.json`, `pt/model.json`, `pt/history/`) zamiast Firestore — nowa sekcja 3.1 tłumaczy podział (świece na żywo potrzebują nasłuchu, którego Git nie ma; strategie/PT zmieniają się rzadko i chcą wersjonowania, którego nie ma Firestore). Dashboard: lista S2 czytana z GitHub (`fetch` raz na godzinę) zamiast z kolekcji Firestore. |
| 0.17 | 2026-09-24 | Naprawa nieskończonej pętli w łataniu luk (L20): `patchOneGap_` teraz sprawdza, czy zwrócone świece faktycznie wypełniają brak, zamiast uznawać za sukces każdy niepusty wynik z Yahoo. Po `PATCH_MAX_RETRIES` (3) próbach bez postępu luka jest automatycznie zapisywana jako zaakceptowana, z komentarzem, i znika z kolejki łatania — bez udziału człowieka. Naprawdę załatane luki są od razu usuwane z arkusza `_AUDYT`, nie czekają do następnego audytu. |
| 0.18 | 2026-09-24 | Przegląd fundamentów. **Blokada po wyczerpaniu limitu Firestore** — pierwszy 429 wstrzymuje zadania w tle do resetu i loguje raz zamiast w kółko (to samo co L20, ale dla limitu zamiast łatania). **Uzupełniona lista kluczy czyszczonych przy „Wyzeruj stan"** — brakowało siedmiu stanów dodanych w 0.10–0.18, więc po wyczyszczeniu bazy system wierzyłby w nieistniejący postęp. **Wycofana luka L17** — sesje skrócone są liczone poprawnie przez `slotsInSession_()`; zgłoszenie wynikało z błędu w mojej symulacji, nie z kodu. Sprawdzona zgodność nazw pól między Apps Script, Pythonem i dashboardem oraz kompletność handlerów triggerów i pozycji menu. |
| 0.22 | 2026-09-25 | **Okno 14 dni w synchronizacji Pythona.** `sync.py` pytało wyłącznie o sesje nowsze niż ostatnia posiadana (`date > last_date`), co pomijało świece dopisywane WSTECZ — łatanie luk i dopisywanie wolumenu (D12) uzupełniają sesje starsze niż ostatnia, więc kopia lokalna zostawałaby z dziurą, której kolejne synchronizacje nigdy by nie zamknęły. Nowa stała `RECHECK_DAYS = 14` (to samo okno co nocny audyt): pierwsze uruchomienie ściąga całość, każde kolejne sprawdza ostatnie 14 dni i nadpisuje to, co się zmieniło. Statystyka rozróżnia realny przyrost od świec sprawdzonych ponownie. Wyrównane wersje w `ia4-research/` (były 0.19, a `requirements.txt` 1.0 — rozjazd L12). |
| 0.21 | 2026-09-25 | **Naprawa rozjazdu L12 dla decyzji.** `DECISIONS` w `Project.gs` — twarda kopia tabeli z sekcji 9 — nie zostało zaktualizowane, gdy D4–D6 dostały ✅ w wersji 0.7: arkusz PROJEKT przez dwa dni pokazywał je jako „🔸 domyślna — potwierdzić przed Etapem 1”, mimo że w tym pliku były już przyjęte. Naprawione: `DECISIONS` zgodne z sekcją 9. L12 rozszerzone o ten przypadek. |
| 0.20 | 2026-09-25 | **Widoczność trwającego pełnego audytu.** Pełny audyt idzie symbol po symbolu co minutę i ustawia `audit.fullAt` dopiero po ostatnim — przez cały przebieg arkusz PROJEKT, kryterium 0.5 i telemetria pokazywały datę **poprzedniego** audytu, co wygląda identycznie jak zepsuty zapis daty (w tej sesji doprowadziło to do wstępnej, błędnej diagnozy „audyt nie zapisuje daty" — sprawdzenie kodu przed naprawą pokazało, że sam audyt działa poprawnie, brakowało wyłącznie widoczności postępu). Nowa funkcja `auditProgress_()` w `Project.gs` jako jedno źródło prawdy o postępie; kryterium 0.5 pokazuje `audyt w toku: X/Y (SYMBOL)` razem z datą poprzedniego, kryterium 0.6 nie ocenia luk, dopóki audyt trwa (wcześniej liczyło luki z niedokończonego przebiegu jako wynik), wiersz „Pełny audyt" w arkuszu PROJEKT pokazuje `W TOKU X/Y`. `Telemetry.gs`: nowy blok `jobs.fullAudit` (running, index, total, current, startedAt, lastError, zużyte odczyty wobec budżetu). Luka L21. |
| 0.19 | 2026-09-24 | **Przebudowa metodologii, zeby projekt mial realna szanse znalezc prawdziwa przewage.** Okres badawczy podzielony na **odkrywanie** (do 2025-09-30) i **poletko** (2025-10-01 - 2026-03-22) - tania informacja zwrotna po kazdym etapie, zanim otworzymy skarbiec; wczesniej skarbiec byl jedynym sprawdzianem i pierwsza informacja przyszlaby za pozno. **D16 przepisane**: poprzedni prog (99. percentyl) przepuszczalby ~240 strategii czystym przypadkiem przy 24 000 testow - teraz kontrola FDR, blokowy bootstrap, minimum roznych dni, prog oplacalnosci i potwierdzenie na poletku. Nowe zasady: **5.9** purging i embargo przy podzialach danych, **5.10** efektywna liczba obserwacji (nakladajace sie transakcje i 53 instrumenty reagujace na ten sam ruch), **5.11** minimalna przewaga ekonomiczna, **5.12** co zrobic, jesli skarbiec nie potwierdzi. **Etap 3**: model PT uczy sie na wszystkich 53 instrumentach (na samych glownych 1000 cech na ~270 transakcji = pewne przeuczenie), wybor cech wewnatrz walidacji. Sekcja 1 mowi wprost, czego szukamy i po czym poznamy sukces. Poprawione niespojnosci: 24 -> 50 spolek kontrolnych, 27 -> 53 instrumenty, S2 do GitHub nie Firestore, H wedlug D10. |

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
| 2026-09-23 23:47 | `c4fdbf3` | `Project.gs`, `Code.gs`, `IA4_INSTRUKCJA.md` + wersje | Wersja 0.9.1 (opisana wtedy blednie jako 1.0; numeracja jest dwuczlonowa, 0.10 nastepuje po 0.9): `resetAfterWipe()` + menu, przygotowanie do pobrania całej historii od zera z wolumenem. |
| 2026-09-23 23:49 | `3f9573a` | `Code.gs`, `IA4_INSTRUKCJA.md` + wersje | Wersja 0.10: samoczynne dopisywanie wolumenu do starej historii z dziennym budżetem zapisów. |
| 2026-09-24 10:11 | `d27ae75` | `Code.gs`, `IA4_INSTRUKCJA.md` + wersje | Wersja 0.11: naprawa brakującego `symbol` w łataniu luk i dopisywaniu wolumenu (HTTP 400 „type unset"). |
| 2026-09-24 14:32 | `6237caa` | `Telemetry.gs` (nowy), `Code.gs`, `IA4_INSTRUKCJA.md` + wersje | Wersja 0.12: telemetria stanu systemu do Firestore i GitHub, metodologia S2/S3/PT. |
| 2026-09-24 14:46 | `ae3339b` | `ia4-dashboard.html`, `Investor.gs` (nowy), `Code.gs`, `IA4_INSTRUKCJA.md` | Wersja 0.13: wielu inwestorów w dashboardzie, arkusz Transaction LOG. |
| 2026-09-24 14:55 | `a878cc1` | `Telemetry.gs`, `Project.gs`, `Code.gs`, `IA4_INSTRUKCJA.md` | Wersja 0.14: poprawki z telemetrii, sprzątanie po VIX, D17. |
| 2026-09-24 15:12 | `2538dee` | `ia4-dashboard.html`, `Project.gs`, `IA4_INSTRUKCJA.md` | Wersja 0.15: ochrona limitu odczytów Firestore — dashboard i pełny audyt. |
| 2026-09-24 15:23 | `738c7f7` | `ia4-dashboard.html`, `IA4_INSTRUKCJA.md` | Wersja 0.16: D18, sekcja 3.1, S2 z GitHub w dashboardzie. |
| 2026-09-24 15:27 | `617a9e5` | `Code.gs`, `IA4_INSTRUKCJA.md` | Wersja 0.17: naprawa L20 - pętla łatania luk. |
| 2026-09-24 20:48 | `09ed4b7` | `IA4_INSTRUKCJA.md`, `Project.gs`, `ia4-research/*` | Wersja 0.19: przebudowa metodologii - poletko, FDR, purging, ochrona poletka w kodzie.
| 2026-09-25 13:05 | `f0126ef` | `Project.gs`, `Telemetry.gs`, `Code.gs`, `History.gs`, `Proof.gs`, `Investor.gs`, `ia4-dashboard.html`, `IA4_INSTRUKCJA.md` | Wersja 0.20: widoczność trwającego pełnego audytu — `auditProgress_()`, postęp w kryteriach 0.5/0.6, w arkuszu PROJEKT i w telemetrii (`jobs.fullAudit`). Luka L21. |
| 2026-09-25 13:35 | `ce19228` | `Project.gs`, `IA4_INSTRUKCJA.md` | Wersja 0.21: naprawa `DECISIONS` w `Project.gs` — D4–D6 pokazywały w arkuszu PROJEKT nieaktualny status sprzed 0.7, mimo że w instrukcji są ✅ od dawna. L12 rozszerzone. |
| 2026-09-25 14:05 | `(uzupełnić)` | `ia4-research/ia4/sync.py`, `ia4-research/` (wersje), `IA4_INSTRUKCJA.md` + wersje | Wersja 0.22: okno RECHECK_DAYS=14 w synchronizacji Pythona (łapie świece dopisywane wstecz), wyrównanie wersji w folderze badawczym. |
