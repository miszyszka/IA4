# IA 4 — przewodnik: co jest gdzie, jak czytać, jakie wnioski

**Wersja projektu: 1.39 (2026-10-14)** · zasady techniczne: `IA4_INSTRUKCJA.md`

## 1. Co działa samo

Nic nie musisz uruchamiać. Apps Script co minutę:
- zbiera świece 1h z 75 spółek (zapis ok. 30–40 s po zamknięciu świecy),
- liczy sygnały 60 strategii i prowadzi wirtualnego inwestora (ok. +0:45 po zamknięciu świecy),
- zbiera świece 1h 10 par walutowych i Bitcoina (zapis zwykle ok. 20 s – 3 min po zamknięciu świecy).

Mac jest potrzebny do jednorazowych przeliczeń, kiedy Claude o to poprosi, oraz do **AI Investora** (`ia4 start`, sekcja 3c) — agenci pracują tylko wtedy, gdy Mac jest włączony.

**Wszystko na jednej stronie:** https://miszyszka.github.io/IA4/ (hasło znasz; przeglądarka pamięta je 30 dni).
- **System** — czy wszystko żyje. Pasek u góry pokazuje drogę danych: Yahoo → Apps Script → Firestore → GitHub → Mac → strona; przy każdym ogniwie lampka i „ile minut temu” był ostatni znak życia. Zielone = w porządku, żółte = opóźnienie, czerwone = coś stoi, szare = teraz nie dotyczy (np. Mac wyłączony, giełda zamknięta). Napis w rogu „system żyje” = automat i GitHub odezwały się w ciągu 80 min.
- **Inwestor** — wynik wirtualnego inwestora, otwarte pozycje (gdzie jest cena między SL i TP), strategie, transakcje, spółki, sygnały.
- **FX** — prognoza 11 instrumentów i „spływ świec”: każda kratka to jedna świeca 1h; migająca ramka = świeca spóźniona.
- **AI** — AI Investor na Macu: czy działa, portfel Agent-Investora, pozycje z notatką „dlaczego”, ostatnia runda decyzji, porównanie z punktami odniesienia (sekcja 3c).
- Na telefonie strona pokazuje głównie stan i podstawowe liczby; tabele są na komputerze.

## 2. Arkusze

| Arkusz | Po co | Jak często patrzeć |
|---|---|---|
| **VIRTUAL-INVESTOR** | wynik strategii na żywo — **najważniejszy** | raz dziennie / raz w tygodniu |
| **STRATEGIE** | lista strategii: wynik w backteście i na żywo, wybór „for VI” | raz w tygodniu |
| **STATS** | czy automat działa i jak szybko | gdy coś wygląda dziwnie |
| **FX** | 10 par walutowych + BTC: wiersz na dzień, kolumna na instrument — zapisanych/oczekiwanych świec | gdy chcesz sprawdzić dane FX |
| SIGNALS-REALTIME | które strategie dały sygnał na której świecy | podgląd, niepotrzebny do decyzji |
| BACKTEST PORTFELA | jednorazowy raport, z którego wzięły się obecne ustawienia | przeczytać raz; można usunąć |
| `_IA4_DANE` (ukryty) | pamięć świec i stan inwestora | nie ruszać |

## 3. STATS — czy wszystko działa

U góry blok stanu. Dobrze, gdy:
- **Status = OK**, obok „✓ automat żyje”,
- **Czas pracy automatu dziś** wynosi wyraźnie poniżej 90 min (limit Google; zwykle 25–35 min),
- **Nocne odświeżenie** pokazuje wczorajszą sesję,
- **FX 1h — opóźnienie**: mediana ok. +0:30–3:00 (zależy, jak szybko Yahoo domknie świecę), **FX 1h — dziś / historia**: „historia 11/11”.

Pod spodem jest tabela świec: 7 wierszy na dzień, czasy od zamknięcia świecy.
- „75 spółek zapisane” ok. **+0:35**, „Arkusze SIGNALS i VI gotowe” ok. **+0:45** to stan normalny.
- +3:00 zdarza się, gdy Yahoo spóźni się z jedną spółką (widać ją w kolumnie „Brakujące / błędy”).
- Jeśli +3:00 lub więcej pojawia się w większości wierszy przez kilka dni, napisz do Claude.

## 3a. FX — 10 par walutowych i Bitcoin (świece 1h)

Instrumenty: EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD, USDCHF, NZDUSD, EURJPY, GBPJPY, EURGBP i BTCUSD.
Jeden wiersz na dzień (UTC), jedna kolumna na instrument: **zapisanych/oczekiwanych** świec, np. `24/24`.
- Komórka pojawia się po zakończeniu dnia, gdy system go sprawdzi (w nocy, zwykle do ok. 04:30 czasu polskiego). Dzisiejszego dnia jeszcze nie ma.
- Pary walutowe: pełny dzień ma **24** świece, piątek 21 (zimą 22), niedziela 3 (zimą 2), sobota — `—` (rynek zamknięty od piątku 23:00 do niedzieli 23:00 czasu polskiego). BTC: zawsze 24.
- **Zapisanych zawsze = oczekiwanych.** Czego Yahoo nie odda po 3 próbach, to jest uśredniane — wtedy w nawiasie liczba uśrednionych, np. `24/24 (1)`, a komórka jest żółta. Uśrednione świece nie są używane w prognozie.
- Pojedyncze uśrednione świece są normalne. Wiele żółtych komórek przez kilka dni z rzędu oznacza problem po stronie Yahoo; napisz wtedy do Claude.
- Historia (2 lata wstecz) pobiera się sama po wdrożeniu 1.27 w kilkanaście minut. Starą bazę EURUSD 5 min usuwasz raz z menu „🗑 FX — usuń stare świece EURUSD 5 min”.

## 3b. Prognoza FX — strona (zakładka FX) i OKOLICZNOSCI_FX

**Strona, zakładka FX:** https://miszyszka.github.io/IA4/#fx — prognoza na żywo tylko, gdy na Macu chodzi `python -m ia4.fx.live`
(Terminal: `cd ~/Desktop/IA4/ia4-research && source .venv/bin/activate && python -m ia4.fx.live`; Ctrl+C kończy).
Po lewej lista 11 instrumentów (przy nazwie P(wzrost) za 48 świec); strona pamięta ostatnio wybrany.

Prognoza na **48 świec 1h** (pary walutowe — 48 godzin handlu, weekend pomijany; BTC — 48 godzin) to **rozkład, nie jedna linia** — bo jedna uśredniona linia zawsze wychodzi prawie pozioma:
- **Stożek** (niebieskie pasma): ciemny — gdzie cena była w 50% podobnych przypadków, jasny — w 80%. Szeroki stożek = spodziewane duże wahania, wąski = spokój.
- **Scenariusze** (cienkie linie zielona / szara / czerwona): prawdziwe 48-godzinne ścieżki ceny z najbardziej podobnych chwil w historii (czasem innej pary walutowej — w nawiasie), przeliczone na dzisiejszą zmienność — tak realnie wyglądają skoki i wahania. To przykłady, nie przepowiednia.
- **Oczekiwany zakres 48 h**: o ile pipsów (BTC: dolarów) typowo rozjedzie się maksimum i minimum.
- **Kierunek**: P(wzrost) i ile z 80 podobnych chwil skończyło się wzrostem. Werdykt „brak przewagi (jak rzut monetą)” = nie traktuj tego jako sygnału.
- **Linia środkowa** odchyla się od ceny tylko wtedy, gdy sprawdzian udowodnił, że to pomaga. Płaska linia = model uczciwie mówi „kierunku nie wiem”.
- **Sprawdzian**: „stożek 78%” przy celu 80% = stożek trafny. Brier poniżej 0,245 = przewaga w kierunku; 0,25 = moneta. Obok wynik tego jednego instrumentu.
- Zielone „Mac połączony” — prognoza świeża; czerwone — widzisz ostatnią prognozę (wyblakłą).

**Arkusz OKOLICZNOSCI_FX:** 1000 okoliczności, w kolumnach kolejne przeliczenia: `rating/wystąpienia`; nad nimi model na żywo,
trafność stożka, Brier i błąd zakresu każdego przeliczenia.
- Nowa kolumna po `python -m ia4.fx.research` na Macu (ręcznie, np. raz w tygodniu; ok. 3 min). FX-real-time sam weźmie nowy model. Przeliczenia na świecach 1h mają ID `H-001`, `H-002`, … (dawne `R-…` z 5 min są w archiwum).
- Patrz, czy te same okoliczności trzymają wysoki rating w kolejnych kolumnach i czy Brier zaczyna schodzić poniżej 0,245.
- Szara komórka = okoliczność wypadła poza 10–50% świec — tylko informacja.

## 3c. AI Investor — zakładka AI i plik AI-INVESTOR.xlsx

**Uruchamianie:** w Terminalu `ia4 start` (albo dwuklik `IA4-start.command`). Okno zostaw otwarte; Ctrl+C kończy (jeśli Inwestor właśnie myśli — poczeka do końca rundy, najwyżej 3 min). Na noc: laptop otwarty i na zasilaczu.

**Agent-Investor** prowadzi własny, papierowy portfel **100 000 $** na 53 spółkach, 10 parach walutowych i BTC. Po każdej świecy akcji (16:30–22:00) i co godzinę na FX:
1. kod rozlicza pozycje (SL, TP, FC, limit — jak w backteście) i wybiera **kandydatów**: sygnały 60 strategii na tej świecy, najwyżej 12, w kolejności pierwszeństwa;
2. model językowy (`qwen2.5:14b`) decyduje „wchodzę / pomijam”, może zamknąć albo zacieśnić SL otwartej pozycji, czasem zgłosić własny pomysł — **każda decyzja ma notatkę „dlaczego” i pewność 0–100**;
3. kod liczy wielkość pozycji i pilnuje limitów; pozycja wchodzi na otwarciu następnej świecy.

Różnica wobec mechanicznego inwestora (sekcja 4): tu stawka zależy od ryzyka — strata na SL to ok. **0,5% stanu konta (ok. 500 $)**, połowa tego dla strategii spoza „wybranych”, ćwierć dla własnych pomysłów. Dlatego wynik w dolarach jest tu realny, a nie symboliczny.

**Na stronie (zakładka AI):**
- **portfel**: stan konta, wynik zrealizowany i otwarty, średni wynik transakcji, ryzyko otwarte (budżet 6%), obsunięcie; czerwony napis = blokada (stop dzienny −2% albo zatrzymanie przy obsunięciu 20%),
- **pozycje**: gdzie jest cena między SL i TP, ile świec, pewność i notatka — kliknij notatkę, żeby rozwinąć,
- **ostatnia runda**: każda decyzja z notatką i skutkiem; „odrzucone przez kod” = model chciał, ale limit nie pozwolił,
- **punkty odniesienia**: czy Inwestor wybiera lepiej niż „wszyscy kandydaci” (cienie) i niż losowy wybór (percentyl; ≥ 97,5 = lepiej niż przypadek), mechaniczny inwestor, SPY,
- **dziennik**: zdarzenia nadzorcy i notatki Inwestora na bieżąco.

**Plik `~/Desktop/IA4/AI-INVESTOR.xlsx`** (przepisywany po każdej rundzie; jeśli masz go otwartego — zamknij i otwórz ponownie, żeby zobaczyć nowy stan):
- PODSUMOWANIE — liczby portfela i punkty odniesienia,
- TRANSAKCJE — każda pozycja: wejście, SL, TP, wielkość, ryzyko, notatka „dlaczego”, wyjście i wynik netto,
- DECYZJE — każda decyzja modelu (też pominięcia i odrzucenia przez kod),
- PORTFEL, DZIENNIK, PLAYBOOK (strategie z wynikami), HIPOTEZY i PRZEGLĄDY (od kolejnych kroków).
Chcesz go w Arkuszach Google — przenieś ścieżkę do folderu Dysku Google (Claude zmieni `xlsx_path`).

**Jak oceniać:** tak jak sekcja 4 — średni wynik transakcji z przedziałem 95%. **Przed 30 zamkniętymi transakcjami nie ma werdyktu.** Najważniejsze pytanie to nie „czy zarabia”, tylko „czy wybór modelu jest lepszy niż losowy” (percentyl) — inaczej wystarczyłby mechaniczny inwestor.

## 3d. Test One-Day — plik ONE-DAY-STRATEGY.xlsx

**Uruchamianie (raz, kiedy chcesz):** w Terminalu `cd ~/Desktop/IA4/ia4-research && source .venv/bin/activate && python -m ia4.oneday`. Liczy kilka sekund i zapisuje `~/Desktop/IA4/ONE-DAY-STRATEGY.xlsx` (każde uruchomienie przepisuje plik — zamknij go wcześniej w Excelu).

**O co chodzi:** 100 prostych strategii na **świecach dobowych** (cała sesja = jedna świeca). Każda transakcja otwiera się rano i zamyka na koniec tego samego dnia. Po serii N świec spadkowych gramy na wzrost (po wzrostowych — na spadek), a gdy dzień znów jest stratny, następnego dnia gramy większą kwotą — aż do pierwszego zysku. Każda spółka ma osobne 100 000 $. Szczegóły i lista strategii: instrukcja, sekcja 6c, oraz arkusz OPIS w pliku.

**Jak czytać arkusz ONE-DAY-STRATEGY:**
- wiersz = strategia (OD-001…OD-100, opis słowny), kolumna = spółka (4 kolumny: transakcje, zyskowne, wynik %, obsunięcie %); „· dP” — spółki doubleProof,
- żółte kolumny na początku — **podsumowanie wszystkich spółek**: patrz najpierw na **medianę wyniku %** i „spółek na plusie” — średnia bywa ciągnięta przez jedną spółkę,
- **obsunięcie %** — o ile najgłębiej spadł kapitał od swojego szczytu; przy podwajaniu stawek to ono pokazuje prawdziwe ryzyko,
- czerwony pogrubiony wynik = **upadłość** (kapitał spadł do 10 000 $),
- porównuj zawsze z **OD-099 / OD-100** (long / short codziennie bez żadnej reguły): strategia, która nie bije OD-099, tylko jedzie na hossie.

**Arkusz PORTFEL OD-080** — co by było, gdyby jeden inwestor z **10 000 $** grał tę strategię na wszystkich 73 spółkach naraz. Wiersz = jedna transakcja (dzień, spółka, która to świeca w serii, stawka, zysk/strata, zarobiony % i stan portfela po niej). Na górze podsumowanie. Uwaga „stawki dnia ×0,6” znaczy: tego dnia sygnałów było tyle, że suma stawek przekroczyłaby portfel, więc wszystkie zmniejszono — bez pożyczania pieniędzy. Inną strategię dodasz poleceniem `python -m ia4.oneday --portfolio OD-080 OD-034`.

**Wniosek do zapamiętania:** zwiększanie stawki po stracie nie zmienia tego, czy pojedynczy dzień jest „na plusie” — zamienia wiele drobnych zysków na rzadkie, duże straty. Ważne są: obsunięcie, upadłości, wynik na doubleProof i wariant z filtrem SMA50 (blok C), który w bessie przestaje dawać sygnały long.

## 3e. Poszukiwanie stabilnych strategii — pliki ONE-DAY-SEARCH.xlsx i ONE-DAY-SEARCH-DAILY.xlsx

**Uruchamianie:** `cd ~/Desktop/IA4/ia4-research && source .venv/bin/activate`, potem:
- `python -m ia4.odsearch` — na świecach z ostatnich ok. 2 lat (ok. 1 min) → `ONE-DAY-SEARCH.xlsx`,
- `python -m ia4.daily` i `python -m ia4.odsearch --source daily` — na historii od 2000 r. (ok. 2–4 min) → `ONE-DAY-SEARCH-DAILY.xlsx`. Najpierw automat musi pobrać historię (niżej).

Zamknij wcześniej plik w Excelu / Numbers. Mac bez programu do `.xlsx`: przeciągnij plik na Dysk Google (otworzy się w Arkuszach) albo zainstaluj darmowe Numbers.

**O co chodzi:** program sprawdza ok. 17 300 prostych reguł „wejdź rano, wyjdź wieczorem”. Dwie rodziny:
- **kierunkowe** — np. „long po 2 spadkowych świecach, gdy cena nad SMA50, w poniedziałek”,
- **neutralne** — każdego dnia kupujemy k spółek, które np. wczoraj najmocniej spadły, i sprzedajemy k, które najmocniej wzrosły (albo odwrotnie). Tyle samo long i short, więc wynik prawie nie zależy od tego, czy rynek rośnie, czy spada.

Zostają tylko reguły, które w **20 kolejnych okresach** były stratne **najwyżej raz**. Program szuka tylko na 53 spółkach handlowanych; 20 spółek doubleProof służy do sprawdzenia.

**Jak czytać arkusze WYNIKI i WYNIKI NEUTRALNE:**
- 20 kolorowych kolumn okresów — zielony = okres na plusie, czerwony = na minusie, szary = za mało transakcji,
- **dP potwierdzona ✓** — reguła zarabia także na spółkach, których program nie widział, i to po odjęciu ruchu całego rynku; próg jest wysoki (przy 200 regułach t ≥ 3,5), bo inaczej przypadek dawałby ✓; reguły bez ✓ traktuj jak przypadek,
- **nadwyżka nad bazą** — o ile reguła jest lepsza od kupowania (albo sprzedawania) każdego dnia; około 0 = reguła tylko płynie z rynkiem,
- arkusz **OPIS → Placebo** — ile reguł „przeszłoby” z czystego przypadku na tych samych danych; jeśli prawdziwych ✓ jest tyle co w placebo, nic nie znaleźliśmy,
- arkusze **PORTFEL #1–#3** (kierunkowe), **S1** (najlepszy short — zawsze jest przynajmniej jeden; jeśli w nagłówku jest „UWAGA: nie spełnia warunku”, to tylko porównanie) i **N1–N2** (neutralne) — jak rósłby portfel 10 000 $, transakcja po transakcji.

**Baza świec dobowych (od 1.38):** automat w Apps Script sam pobiera pełną historię świec dobowych wszystkich 75 instrumentów — porcjami po 6, tylko poza sesją (wieczorem, w nocy, w weekend), razem ok. 13 porcji. Postęp: plik `telemetry/state.json` na GitHubie (https://github.com/miszyszka/IA4/blob/main/telemetry/state.json), pole `daily` → `history` (np. `42/75`; odświeżany ok. co godzinę), albo komunikat po menu „📅 Świece dobowe — porcja historii teraz”. Strona IA4 tego jeszcze nie pokazuje. Potem raz na dzień sesyjny, wieczorem, dopisuje nowy dzień. Ręcznie: menu IA 4 → „📅 Świece dobowe — porcja historii teraz”.

## 4. VIRTUAL-INVESTOR — jak czytać wynik

Stawka to 100 $ na transakcję przy kapitale 100 000 $, więc **„% kapitału” zawsze będzie bardzo małe**. To nie jest miara, na którą patrzysz. Patrz na trzy liczby:

1. **Transakcji zamkniętych**: ile już jest danych.
2. **Średni wynik zamkniętej (%)**: ile średnio zarabia jedna transakcja, po kosztach.
3. **Średni wynik zamkniętej — przedział 95%**: zakres, w którym prawdopodobnie leży prawdziwa średnia.

**Czego się spodziewać** (backtest na spółkach doubleProof, których system nie widział przy szukaniu):
- średnio **+0,4…+0,6% na transakcję**,
- skuteczność (TP) **ok. 35–38%** (większość transakcji kończy FC, mniej więcej na zero),
- mediana **ok. 9 świec** w pozycji (ok. 1,5 dnia),
- **ok. 3–4 nowe transakcje na sesję** (jedna pozycja na spółkę).

**Wnioski według liczby zamkniętych transakcji:**

| Zamkniętych | Co możesz powiedzieć |
|---|---|
| < 100 | jeszcze nic — za mało danych; pojedyncze dni i strategie to szum |
| 100–300 | tylko czy coś jest wyraźnie zepsute: jeśli **cały przedział 95% jest poniżej 0** → napisz do Claude |
| ≥ 300 (ok. 3–4 miesiące) | **cały przedział powyżej 0** → system zarabia na żywo; średnia ok. +0,5% → zgodnie z backtestem; średnia < +0,2% → działa słabiej niż backtest, do przeglądu z Claude |

Dla orientacji: przy 100 transakcjach przedział ma szerokość ok. ±0,8 pkt proc., przy 300 ok. ±0,5, przy 1000 ok. ±0,25.

## 5. STRATEGIE — jak czytać

Kolejność wierszy to **pierwszeństwo**. Gdy kilka strategii daje sygnał na tej samej spółce, inwestor bierze tę wyżej.

- **Wybrana ✓**: strategia z szacunkiem przewagi ≥ 0,40% na transakcję (52 z 60). Tylko te powinny mieć zaznaczone „for VI”.
- **Kolumny niebieskie (doubleProof)**: wynik w backteście na nowych spółkach. Uczciwy, ale z małej próby (zwykle 20–50 transakcji), więc pojedyncze PF bardzo się wahają.
- **Szacunek przewagi %**: wynik doubleProof „ściągnięty” do średniej wszystkich strategii. To ostrożniejsza liczba niż PF.
- **Kolumny żółte (VI)**: wynik tej strategii na żywo.
- **Kolumny fioletowe (poszukiwanie: grupa główna i skarbiec)**: wynik na danych, na których strategie były szukane i wybierane. Jest mocno zawyżony (PF ważony średnio ok. 4,7, a na nowych spółkach ok. 1,4), więc nie decyduj na jego podstawie. Przydaje się do porównania: duży spadek od poszukiwania do doubleProof oznacza strategię dopasowaną do przeszłości.

**Kiedy odznaczyć strategię:** dopiero gdy ma **co najmniej 30 zamkniętych transakcji na żywo** i średni wynik wyraźnie poniżej zera (np. < −1%). Pojedyncza strategia robi ok. 1–2 transakcje w miesiącu, więc to sprawa na wiele miesięcy. Wcześniej decyduj na poziomie całego portfela (punkt 4).

## 6. Co zrobić teraz (jednorazowo, po wdrożeniu 1.16)

1. Menu **IA 4 → „✅ for VI = strategie wybrane w backteście portfela”**: zamiast dzisiejszych 114 zaznaczonych zostanie 52.
2. Menu **IA 4 → „🔄 Wirtualny inwestor — zacznij od nowa”**: stare pozycje pochodzą z innych zasad (114 strategii, bez kosztów, bez limitu), więc statystyki zaczną się od czystego stanu.
3. **Usuń arkusze**: RESEARCH, STRATEGIE DOUBLEPROOF, BACKTEST DOUBLEPROOF (prawy klik na zakładkę → Usuń). Nic z nich nie trzeba przepisywać: wyniki doubleProof są teraz w STRATEGIE, a pełne pliki zostają na GitHubie (branch `research`). Jeśli chcesz pamiątkę, przed usunięciem zrób Plik → Pobierz → PDF.
4. BACKTEST PORTFELA przeczytaj raz (wnioski w punkcie 7), potem możesz go usunąć. Nie wróci, dopóki nie zrobimy nowego backtestu.

## 7. Wnioski z backtestu portfela (zapamiętaj)

- **Cały portfel ma przewagę**: na nowych spółkach PF ok. 1,4, plus w każdym z 4 okresów. Pojedyncze strategie są jednak trudne do odróżnienia od siebie, bo ich wyniki się nie powtarzają z okresu na okres.
- **Long jest mocniejszy niż short.** Shorty na nowych spółkach dawały mało, a w dwóch okresach traciły. Stąd plan poszukiwania strategii SHORT z SL/TP w ATR.
- **Stawka według SL nie pomogła** (gorszy PF), więc zostaje stałe 100 $.
- **Limit 1 pozycji na spółkę** zmniejsza liczbę transakcji o ok. 40% i zysk w $ mniej więcej o połowę, a obsunięcia prawie nie zmniejsza. Jest ustawiony, bo tak zdecydowaliśmy; zmiana to jedna liczba (`MAX_PER_TICKER`).
- **Grupa główna i skarbiec są zawyżone** (PF 3–4,7), bo na nich strategie były wybierane. Uczciwy obraz daje doubleProof, a teraz także wynik na żywo.

## 8. Kiedy pisać do Claude

- Status BŁĄD przez kilka godzin, „⚠ brak uruchomień”, czas pracy automatu > 70 min.
- Po ok. 300 zamkniętych transakcjach: przegląd wyników na żywo.
- Gdy chcesz wznowić poszukiwanie (strategie SHORT z SL/TP w ATR).
- AI Investor: czerwony napis blokady w zakładce AI, „brak decyzji modelu” w kilku rundach z rzędu, po ok. 30 zamkniętych transakcjach (pierwsza ocena) albo gdy notatki Inwestora wyglądają na bezsensowne.
