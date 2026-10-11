# IA 4 — przewodnik: co jest gdzie, jak czytać, jakie wnioski

**Wersja projektu: 1.28 (2026-10-11)** · zasady techniczne: `IA4_INSTRUKCJA.md`

## 1. Co działa samo

Nic nie musisz uruchamiać. Apps Script co minutę:
- zbiera świece 1h z 75 spółek (zapis ok. 30–40 s po zamknięciu świecy),
- liczy sygnały 60 strategii i prowadzi wirtualnego inwestora (ok. +0:45 po zamknięciu świecy),
- zbiera świece 1h 10 par walutowych i Bitcoina (zapis zwykle ok. 20 s – 3 min po zamknięciu świecy).

Mac jest potrzebny tylko do jednorazowych przeliczeń, kiedy Claude o to poprosi.

**Wszystko na jednej stronie:** https://miszyszka.github.io/IA4/ (hasło znasz; przeglądarka pamięta je 30 dni).
- **System** — czy wszystko żyje. Pasek u góry pokazuje drogę danych: Yahoo → Apps Script → Firestore → GitHub → Mac → strona; przy każdym ogniwie lampka i „ile minut temu” był ostatni znak życia. Zielone = w porządku, żółte = opóźnienie, czerwone = coś stoi, szare = teraz nie dotyczy (np. Mac wyłączony, giełda zamknięta). Napis w rogu „system żyje” = automat i GitHub odezwały się w ciągu 80 min.
- **Inwestor** — wynik wirtualnego inwestora, otwarte pozycje (gdzie jest cena między SL i TP), strategie, transakcje, spółki, sygnały.
- **FX** — prognoza 11 instrumentów i „spływ świec”: każda kratka to jedna świeca 1h; migająca ramka = świeca spóźniona.
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
