# IA 4 — przewodnik: co jest gdzie i jak to czytać

**Wersja projektu: 1.49 (2026-10-19)** · zasady: `IA4_INSTRUKCJA.md` · na stronie te same opisy są pod „?” w rogu każdego panelu

## 1. Co działa samo, a co wymaga Maca

- **Samo (Apps Script, bez Maca):** zbieranie świec 75 spółek i 11 instrumentów FX, sygnały 60 strategii, mechaniczny inwestor, telemetria dla strony.
- **Mac (`ia4 start`):** agenci AI (Inwestor, Krytyk, Badacz) i prognoza FX na żywo. Pracują tylko, gdy Mac jest włączony; noc — laptop otwarty i na zasilaczu.

## 2. Strona IA4 — https://miszyszka.github.io/IA4/

**Magistrala** (pasek pod nagłówkiem): droga danych Yahoo → Apps Script → Firestore → GitHub → Mac → strona. Każde ogniwo ma lampkę i wiek ostatniego znaku życia. Zielone — w normie, żółte — spóźnia się, czerwone — przestało działać, szare — teraz nie pracuje z planu (noc, weekend, Mac wyłączony).

| Zakładka | Co tam jest | Na co patrzeć |
|---|---|---|
| **1 System** | stan składników, strumień zdarzeń, parametry dnia, ostatnia świeca akcji, siatka spółek, źródła danych | Apps Script i GitHub zielone; błędy dziś = 0; czas pracy automatu < 75% limitu 90 min; brak ostrzeżenia o wersji |
| **2 Inwestor** | mechaniczny inwestor z Apps Script (100 $ na każdy sygnał strategii „for VI”): wynik, krzywa, pozycje, transakcje, spółki | średni wynik transakcji z przedziałem 95% — dopóki przedział obejmuje zero, nie wiadomo, czy strategie zarabiają |
| **3 FX** | prognoza 48 h dla 11 instrumentów: stożek 50% i 80%, P(wzrost), scenariusze, spływ świec | kierunek walut to zwykle rzut monetą — prognoza mówi, jak DALEKO cena może się ruszyć, nie w którą stronę |
| **4 AI** | agenci na Macu: praca agentów, portfel, Krytyk, pozycje, ostatnia runda, punkty odniesienia, Badacz, transakcje, dziennik | czy agenci pracują (zajęci 70–95%), czy Inwestor wchodzi w transakcje, co mówi Krytyk |

**Zakładka AI, od góry:**
- **praca agentów** — kto pracuje teraz, oś 24 h (kreska = zadanie; czerwona = błąd), rytm („co ile”), średni czas zadania. Agenci pracują po kolei, zawsze jeden naraz: Inwestor po każdej świecy, Krytyk co kilka rund, Badacz cały wolny czas.
- **portfel** — papierowe 100 000 $. Ryzyko otwarte (budżet 6%), obsunięcie od szczytu (10% → kod zmniejsza ryzyko, 20% → wstrzymuje wejścia do Twojej decyzji), **poziom nauki 0–3** (jak śmiało Inwestor wchodzi).
- **Krytyk** — ostatni przegląd: poziom nauki i dlaczego, uwagi dla Inwestora i Badacza, werdykty hipotez.
- **pozycje / ostatnia runda** — każda decyzja z notatką „dlaczego”; własny pomysł — z hipotezą. „→ odrzucone przez kod” = limity ryzyka nie pozwoliły.
- **punkty odniesienia** — czy Inwestor jest lepszy niż: wejście we wszystkich kandydatów, losowy wybór, mechaniczny inwestor, SPY. Werdykt po 30 transakcjach.
- **Badacz · hipotezy** — droga hipotezy: odrzucona przez kod → do oceny → próba (handlowana na żywo małym ryzykiem) → zatwierdzona / wycofana. „na ślepo” = wynik wchodzenia w każdą świecę; hipoteza musi być lepsza. Przy setkach prób część dobrych wyników to przypadek — liczy się próba na żywo.

**Kolory:** zielony i czerwony — kierunek i stan; bursztyn — wyróżnienia; cyjan — prognozy; fiolet — Badacz.

## 3. Arkusz Google i pliki Excel

| Gdzie | Co |
|---|---|
| STATS | stan automatu i czasy każdej świecy (od zamknięcia do zapisu i sygnałów) |
| FX | dzień × instrument: zapisanych/oczekiwanych świec; żółte = były uśrednione |
| OKOLICZNOSCI_FX | 1000 okoliczności FX z ratingiem w każdym przeliczeniu |
| STRATEGIE | 60 strategii: wyniki na doubleProof, na żywo i z poszukiwania; checkbox „for VI” — jedyne pole do zmiany ręcznie |
| SIGNALS-REALTIME, VIRTUAL-INVESTOR | sygnały po każdej świecy i transakcje mechanicznego inwestora |
| `~/Desktop/IA4/AI-INVESTOR.xlsx` | AI: transakcje z notatkami, decyzje, portfel, dziennik, playbook, hipotezy, przeglądy Krytyka |
| `~/Desktop/IA4/ONE-DAY-*.xlsx` | badania One-Day (informacyjne); jak czytać arkusze — `archiwum/PRZEWODNIK-1.40.md`, sekcje 3d–3e. Od 1.42 `ONE-DAY-SEARCH*.xlsx` liczy **spread 0,3% na transakcję** (od 1.45: raz na transakcję, wszędzie): „śr. wynik netto” to wynik po spreadzie, „brutto” — przed; liczy się netto |
| `~/Desktop/IA4/ONE-DAY-WYBICIA.xlsx` | siła ruchu po konsolidacji (od 1.44): **ANALIZA** — po jakim stanie dzień rusza się mocniej niż zwykle (kolumna „wzrost”: zielony > 1,1, czerwony < 0,9), w jednostkach R (typowy ruch danej spółki); **SPÓŁKI** — R każdej spółki i wzrost po wybranych stanach; **STRATEGIE** — long + short naraz (LS) i wybicie zleceniami (BO) z TP 2–3 × SL, 20 okresów kolorami; **PORTFEL LS / BO** — 10 000 $ |
| `~/Desktop/IA4/ONE-DAY-PORTFEL.xlsx` | portfel strategii wybieranych co rok tylko na przeszłości (od 1.43): **PODSUMOWANIE** — wynik portfela na 53 spółkach, doubleProof i placebo, 20 okresów (zielony / czerwony); **ROK PO ROKU** — ile reguł było kandydatami i ile wybrano, wynik każdego roku; **STRATEGIE W PORTFELU** — które reguły grały w danym roku; **REGUŁY (pełna próba)** — tylko do wglądu (zawyżone); **PORTFEL WF** — 10 000 $ transakcja po transakcji |
| `~/Desktop/IA4/SWING-TREND.xlsx` | strategie wielodniowe jednokierunkowe z SL i TP (od 1.45): **OPIS** — ile z 49 920 strategii spełnia warunek, a ile placebo (przypadek); **STRATEGIE** — reguły, które spełniają warunek: wynik netto, przewaga nad wejściem na ślepo, 20 okresów kolorami, doubleProof (✓ = potwierdzona); **SETUPY** — najlepsza strategia każdego setupu w każdą stronę (także te, które nie przeszły); **PORTFEL …** — 10 000 $ na dźwigni 1:5 transakcja po transakcji |
| `~/Desktop/IA4/SWING-RSI3.xlsx` | strategia RSI(3) / EMA100 / VWAP10 (od 1.45): **QQQ 1-1 / 1-5** — portfel 10 000 $ rok po roku i transakcja po transakcji; **SPÓŁKI** — ta sama reguła na każdej spółce osobno (obok kup i trzymaj); **WSZYSTKIE 1-1 / 1-5** — wspólny portfel wszystkich spółek |
| `~/Desktop/IA4/SWING-SERIE.xlsx` | mapa serii świec (od 1.45): **MAPA** — wiersz N = wejście po N świecach spadkowych (niżej: wzrostowych), kolumny — 1/2/3 sesje, long i short; w komórce liczba transakcji i końcowy % portfela 10 000 $ na dźwigni 1:5 (zielony — zysk, czerwony — strata, ✗ — upadłość); **MAPA dP** — to samo na 20 spółkach doubleProof (sprawdzian); **SZCZEGÓŁY**, **SPÓŁKI** — więcej liczb |
| `~/Desktop/IA4/SWING-PORTFEL-7.xlsx` | portfel „po 7 świecach spadkowych long na 3 sesje, 1:5” (od 1.46): **PODSUMOWANIE** — wynik, obsunięcia, wyniki wg położenia ceny wobec SMA200 / SMA50 i wg głębokości spadku; **KAPITAŁ** — wykres stanu portfela i obsunięcia; **OBSUNIĘCIA** — od kiedy, jak głęboko, kiedy odrobione; **ZDARZENIA** — każda seria 7 spadków ze średnimi, spadkiem w R i wynikiem transakcji (filtr w nagłówku) |
| `~/Desktop/IA4/SWING-PORTFEL-PROPOZYCJA.xlsx` | propozycja z analizy (od 1.47): ≥ 5 spadków, spadek ≥ 10%, słaby rynek, 5 sesji, max 5 pozycji. Te same arkusze co wyżej oraz **ANALIZA** — jak cechy serii (wielkość spadku, rynek, zmienność, RSI, średnie) zmieniają wynik w trzech okresach (zielony — zysk); w **PODSUMOWANIE** tabela „wrażliwość” — ten sam zestaw transakcji przy dźwigni 1:1–1:5 i limicie 3 / 5 / 10 / bez; w **ZDARZENIA** także serie odrzucone (kolumna „Warunki”, powód w „Uwagi”) |
| `~/Desktop/IA4/SWING-ROWNA.xlsx` | strategia RÓWNA (od 1.48): kupowanie spadków tylko przy rosnącym trendzie — QQQ (reguła RSI(3), pozycja wg zmienności) + kapitulacja spółek. **PODSUMOWANIE** — wynik, obsunięcia, wynik w czasie każdej bessy (cel: blisko zera), części osobno; **KAPITAŁ** — wykres całości i części; **ROK PO ROKU** — ile zarobiła każda część; **SYGNAŁY SPÓŁEK** — także odrzucone (brak trendu, limit); **ODPORNOŚĆ** — czy wynik trzyma się przy sąsiednich ustawieniach |
| `~/Desktop/IA4/FX-SHORT-NY.xlsx` | FX — short po gwałtownym wzroście (od 1.49, informacyjne): **PODSUMOWANIE** — reguła i wynik; **TRANSAKCJE** — każda transakcja, a u góry **żółte komórki** (kapitał, dźwignia, depozyt na pozycję, koszt nocny) — po zmianie przeliczają się saldo, wykresy i okresy; **KAPITAŁ** — saldo dzień po dniu i obsunięcie; **OKRESY** — 20 części (stratne na czerwono w wykresie); **WARIANTY** — 1000 $ przy różnym depozycie (5–100%); **ODPORNOŚĆ** — sąsiednie ustawienia i godzina sygnału (zielony — zysk); **UCZCIWY TEST** — placebo, połowy danych, reguła wybrana na 1. roku sprawdzona na 2. (to jest realistyczne oczekiwanie); **HIPOTEZA** — short po każdej dużej świecy bez filtrów; **RANKING** — najlepsze z przeszukania (zawyżone); **EURUSD** — sama para |

## 4. Jak oceniać wyniki

1. **Nigdy po jednym dniu ani kilku transakcjach.** Średni wynik transakcji z przedziałem 95% i co najmniej 30 transakcji.
2. **Wyniki z danych, na których szukano, są zawyżone.** Uczciwe: doubleProof, sejf AI, wynik na żywo.
3. **Codziennie (1 min):** magistrala zielona? Zakładka AI — agenci pracują i Inwestor wchodzi w transakcje?
4. **Raz w tygodniu:** średnie z przedziałem 95% (Inwestor, AI), hipotezy w próbie, przeglądy Krytyka — i rozmowa z Claude o tym, co dalej.
