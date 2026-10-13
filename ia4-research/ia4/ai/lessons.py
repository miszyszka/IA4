"""
IA 4 — wnioski startowe AI Investor (instrukcja, sekcja 11c.5): destylowana wiedza z historii projektu.
Wersja projektu: 1.37 (2026-10-13) — musi zgadzać się z IA4_INSTRUKCJA.md

Zasiewane raz, gdy hub nie ma żadnych wniosków (autor „Claude”). Od kroku AI-4 listę prowadzi
Strategy-Manager (najwyżej `lessons_max` aktywnych).
"""

SEED = [
    "Wyniki z danych, na których szukano strategii (grupa główna, skarbiec), są zawyżone — uczciwą miarą są doubleProof (spółki, których poszukiwanie nie widziało) i wynik na żywo (6a, 6b).",
    "W wersji 1.1 z 1292 „strategii” większość okazała się jednym pomysłem „kup spadek w hossie” (1.2) — kilka podobnych sygnałów na tej samej spółce to jedna informacja, nie kilka.",
    "Kierunek kursów walut na świecach 1h to rzut monetą (H-001, H-002: Brier 0,25), za to zakres ruchu i zmienność są przewidywalne — prognoza FX mówi, gdzie leży szum (SL/TP, wielkość), a nie w którą stronę.",
    "Kilkanaście transakcji to za mało na wniosek: średni wynik oceniaj zawsze z przedziałem 95% i liczbą transakcji (PRZEWODNIK, sekcja 4).",
    "Mechaniczny inwestor (Apps Script) wchodzi w każdy sygnał strategii „for VI”. Wartość Agent-Investora to wybór i zarządzanie — porównanie z losowym wyborem spośród tych samych kandydatów pokaże, czy coś wnosi.",
    "SL, TP i limit świec strategii zostały dobrane na historii razem z regułą — nie poprawiaj ich na wyczucie; SL zacieśniaj tylko z konkretnego powodu (np. wyraźny zysk, nadchodzący koniec sesji).",
    "Strategie z FC często kończą się wcześnie na FC z wynikiem bliskim zera — oceniaj strategię po średniej wszystkich transakcji, nie po pojedynczym wyjściu.",
    "Decyzja na ostatniej świecy sesji NYSE (16:00 ET) wykona się dopiero na otwarciu następnej sesji — luka nocna może przeskoczyć SL (wyjście po cenie otwarcia, strata większa niż SL).",
    "Koszty akcji są małe (ok. 0,01% za transakcję), ale na FX spread (0,8–2,5 pipsa) zjada ruchy rzędu kilku pipsów — małe cele na FX rzadko się opłacają.",
    "Pewność 50 to moneta. Wysoka pewność bez mocnych liczb w briefie (dużo transakcji na doubleProof, dodatni wynik na żywo) to sygnał nadmiernej pewności siebie — kod mierzy kalibrację.",
]
