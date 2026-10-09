# IA 4 — przewodnik: co jest gdzie, jak czytać, jakie wnioski

**Wersja projektu: 1.20 (2026-10-09)** · zasady techniczne: `IA4_INSTRUKCJA.md`

## 1. Co działa samo

Nic nie musisz uruchamiać. Apps Script co minutę:
- zbiera świece 1h z 75 spółek (zapis ok. 30–40 s po zamknięciu świecy),
- liczy sygnały 60 strategii i prowadzi wirtualnego inwestora (ok. +0:45 po zamknięciu świecy),
- zbiera świece 5 min EURUSD (na razie tylko zbiera).

Mac jest potrzebny tylko do jednorazowych przeliczeń, kiedy Claude o to poprosi.

## 2. Arkusze

| Arkusz | Po co | Jak często patrzeć |
|---|---|---|
| **VIRTUAL-INVESTOR** | wynik strategii na żywo — **najważniejszy** | raz dziennie / raz w tygodniu |
| **STRATEGIE** | lista strategii: wynik w backteście i na żywo, wybór „for VI” | raz w tygodniu |
| **STATS** | czy automat działa i jak szybko | gdy coś wygląda dziwnie |
| **FX** | EURUSD: jeden wiersz na dzień — oczekiwanych, zapisanych, uśrednionych | gdy chcesz sprawdzić EURUSD |
| SIGNALS-REALTIME | które strategie dały sygnał na której świecy | podgląd, niepotrzebny do decyzji |
| BACKTEST PORTFELA | jednorazowy raport, z którego wzięły się obecne ustawienia | przeczytać raz; można usunąć |
| `_IA4_DANE` (ukryty) | pamięć świec i stan inwestora | nie ruszać |

## 3. STATS — czy wszystko działa

U góry blok stanu. Dobrze, gdy:
- **Status = OK**, obok „✓ automat żyje”,
- **Czas pracy automatu dziś** wynosi wyraźnie poniżej 90 min (limit Google; zwykle 25–35 min),
- **Nocne odświeżenie** pokazuje wczorajszą sesję,
- **EURUSD — opóźnienie**: mediana ok. +0:20–0:30.

Pod spodem jest tabela świec: 7 wierszy na dzień, czasy od zamknięcia świecy.
- „75 spółek zapisane” ok. **+0:35**, „Arkusze SIGNALS i VI gotowe” ok. **+0:45** to stan normalny.
- +3:00 zdarza się, gdy Yahoo spóźni się z jedną spółką (widać ją w kolumnie „Brakujące / błędy”).
- Jeśli +3:00 lub więcej pojawia się w większości wierszy przez kilka dni, napisz do Claude.

## 3a. FX — EURUSD

Jeden wiersz na dzień (UTC): **oczekiwanych świec**, **zapisanych świec**, **w tym uśrednionych**.
- Wiersz pojawia się po zakończeniu dnia, gdy system go sprawdzi (w nocy, do ok. 04:30 czasu polskiego). Dzisiejszego dnia jeszcze nie ma.
- Pełny dzień ma **288** świec, piątek 252, niedziela 36, sobota 0. Rynek walutowy działa od niedzieli 23:00 do piątku 23:00 czasu polskiego; zimą piątek ma 264, a niedziela 24 świece.
- **Zapisanych zawsze = oczekiwanych.** Czego Yahoo nie odda po 3 próbach, to jest uśredniane. Uśrednione świece są oznaczone w bazie i przy analizie można je pominąć.
- Kilka uśrednionych świec dziennie jest normalne. Dziesiątki przez kilka dni z rzędu oznaczają problem po stronie Yahoo; napisz wtedy do Claude.
- Czy EURUSD zbiera się na bieżąco: STATS, wiersze „EURUSD 5m”.

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
