# IA 4 — przewodnik: co jest gdzie i jak to czytać

**Wersja projektu: 1.42 (2026-10-15)** · zasady: `IA4_INSTRUKCJA.md` · na stronie te same opisy są pod „?” w rogu każdego panelu

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
| `~/Desktop/IA4/ONE-DAY-*.xlsx` | badania One-Day (informacyjne); jak czytać arkusze — `archiwum/PRZEWODNIK-1.40.md`, sekcje 3d–3e. Od 1.42 `ONE-DAY-SEARCH*.xlsx` liczy **spread 0,3% na transakcję**: „śr. wynik netto” to wynik po spreadzie, „brutto” — przed; liczy się netto |

## 4. Jak oceniać wyniki

1. **Nigdy po jednym dniu ani kilku transakcjach.** Średni wynik transakcji z przedziałem 95% i co najmniej 30 transakcji.
2. **Wyniki z danych, na których szukano, są zawyżone.** Uczciwe: doubleProof, sejf AI, wynik na żywo.
3. **Codziennie (1 min):** magistrala zielona? Zakładka AI — agenci pracują i Inwestor wchodzi w transakcje?
4. **Raz w tygodniu:** średnie z przedziałem 95% (Inwestor, AI), hipotezy w próbie, przeglądy Krytyka — i rozmowa z Claude o tym, co dalej.
