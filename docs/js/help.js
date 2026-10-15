// IA 4 — opisy paneli („?”) i przewodnik po stronie (instrukcja, sekcja 9; PRZEWODNIK.md).
// Wersja projektu: 1.44 (2026-10-15)
//
// help("klucz") → przycisk „?” w rogu panelu; po kliknięciu opis: co to jest, jak czytać, na co uważać.
// Otwarte opisy pamiętane w przeglądarce — przeżywają odświeżanie danych. Treść = PRZEWODNIK.md (te same zdania).

const H = {
  // ---------------------------------------------------------------- System
  "sys.components": ["Każdy wiersz to część systemu i jej ostatni znak życia.",
    "Zielone — w normie, żółte — spóźnia się, czerwone — przestało działać, szare — teraz nie pracuje z planu (noc, weekend, Mac wyłączony).",
    "Codziennie: Apps Script i GitHub zielone. Mac — tylko gdy go używasz."],
  "sys.stream": ["Wszystko, co się wydarzyło, od najnowszego: commity, świece, transakcje, przeliczenia.",
    "Nowe wiersze błyskają.", "Użyj, gdy chcesz wiedzieć, co działo się w ostatniej godzinie."],
  "sys.params": ["Liczniki dnia automatu (Apps Script).",
    "Najważniejsze: czas pracy wobec limitu Google 90 min dziennie, błędy dziś, wersja.",
    "Uwaga: czas > 75% limitu, błędy > 0, ostrzeżenie o wersji (trzeba wkleić nowe pliki .gs)."],
  "sys.candle": ["Ostatnia świeca akcji: ile czasu po zamknięciu był gotowy każdy etap — pobranie z Yahoo, zapis, sygnały, arkusze.",
    "Typowo całość w 1–2 min.", "Kilka minut lub braki = Yahoo się spóźnia; brakujące spółki dociągają kolejne uruchomienia."],
  "sys.grid": ["Kafelek = spółka: ostatnia cena i numer świecy w sesji.",
    "Ramka przerywana — spółka bez najnowszej świecy; bursztynowa — wirtualny inwestor ma tam pozycję."],
  "sys.sources": ["Pliki, które czyta ta strona, i kiedy się zmieniły.",
    "Czerwone = pliku nie udało się pobrać. Przy limicie GitHub strona sama przechodzi na wolniejszy tryb (do 10 min)."],
  // ---------------------------------------------------------------- Inwestor (Apps Script)
  "vi.hero": ["Mechaniczny wirtualny inwestor z Apps Script: wchodzi w każdy sygnał strategii „for VI”, 100 $ na transakcję, działa bez Maca.",
    "Najważniejsza liczba: średni wynik transakcji z przedziałem 95%.",
    "Dopóki przedział obejmuje zero — nie wiadomo, czy strategie zarabiają. Nie oceniaj po jednym dniu ani przed 30 transakcjami."],
  "vi.curve": ["Łączny wynik $ zamkniętych transakcji w czasie.", "Liczy się kierunek przez tygodnie, nie pojedyncze skoki."],
  "vi.signals": ["Sygnały strategii na ostatnich świecach (strategia → spółka).",
    "Sygnał nie zawsze daje transakcję: na spółce może być już pozycja (limit 1)."],
  "vi.open": ["Otwarte pozycje.", "Pasek SL ─ TP: gdzie jest cena między stop-lossem (lewo) a take-profitem (prawo); kreska = cena wejścia."],
  "vi.closed": ["Zamknięte transakcje z powodem wyjścia:", "TP — cel osiągnięty, SL — stop, FC — sygnał wyjścia strategii, LIMIT — koniec czasu."],
  "vi.stocks": ["Wynik, pozycje i sygnały każdej spółki.", "Pojedyncza spółka z dużym wynikiem to zwykle przypadek — patrz na całość."],
  // ---------------------------------------------------------------- FX
  "fx.hero": ["Prognoza 48 świec 1h: stożek 50% i 80% (gdzie będzie cena z takim prawdopodobieństwem), P(wzrost) i scenariusze.",
    "Kierunek walut to zwykle rzut monetą — linia środkowa jest płaska, dopóki sprawdzian nie dowiedzie przewagi.",
    "Wartość prognozy to ZAKRES ruchu (gdzie leży szum), nie kierunek."],
  "fx.list": ["11 instrumentów: mini-wykres ostatnich 48 świec, cena, P(wzrost). Kliknij, żeby zobaczyć wykres.",
    "P(wzrost) blisko 50% = brak przewagi kierunku."],
  "fx.tape": ["Kratka = godzina. Ramka — świeca trwa, migająca — spóźniona.", "Weekend par walutowych jest pusty — rynek zamknięty."],
  "fx.scen": ["Trzy prawdziwe przebiegi z historii najbardziej podobne do teraz (spadkowy, boczny, wzrostowy).",
    "Pokazują typowe wahania — nie są przepowiednią."],
  "fx.runs": ["Historia przeliczeń FX-research.", "Stożek 80% trafny, gdy obejmuje 75–85% wyników. Brier 0,25 = moneta; poniżej 0,245 — przewaga kierunku."],
  "fx.vi": ["Miejsce na wirtualnego inwestora FX.", "Powstanie dopiero, gdy prognoza dowiedzie przewagi kierunku — i za zgodą człowieka."],
  // ---------------------------------------------------------------- AI
  "ai.hero": ["Czy agenci na Macu działają. „połączony” = znak życia w ciągu 11 min.",
    "Gdy Mac jest wyłączony, wszystko niżej to ostatni znany stan (panele wyblakłe)."],
  "ai.work": ["Kto teraz pracuje, jak często i jak długo. Agenci działają po kolei — zawsze jeden naraz: Inwestor po każdej świecy, Krytyk co kilka rund, Badacz cały wolny czas.",
    "Oś 24 h: kolorowe kreski = praca. „zajęci” 70–95% czasu to dobrze — Mac nie stoi.",
    "Uwaga: długa przerwa przy włączonym Macu albo dużo zadań z błędem (✗) — sprawdź dziennik."],
  "ai.portfolio": ["Papierowy portfel 100 000 $ (akcje i FX), wszystkie liczby liczy kod.",
    "Ryzyko otwarte — suma strat na SL (budżet 6%). Obsunięcie od szczytu: 10% → kod zmniejsza ryzyko, 20% → wstrzymuje wejścia do Twojej decyzji.",
    "Poziom nauki: jak śmiało Inwestor wchodzi (0 ostrożnie … 3 nauka wymuszona)."],
  "ai.curve": ["Stan konta po każdej rundzie, $ od startu.", "W trybie nauki wahania są normalne — oceniaj średnią transakcji, nie krzywą z kilku dni."],
  "ai.positions": ["Otwarte i oczekujące pozycje z notatką „dlaczego” (i hipotezą, gdy to własny pomysł).",
    "Oczekuje = wejdzie po otwarciu następnej świecy. Pasek SL ─ TP jak w zakładce Inwestor."],
  "ai.round": ["Ostatnia decyzja Inwestora: kogo wybrał, kogo pominął i dlaczego.",
    "„→ odrzucone przez kod” — model chciał, ale limity ryzyka nie pozwoliły."],
  "ai.bench": ["Czy Inwestor jest lepszy niż: wejście we wszystkich kandydatów (cienie), losowy wybór, mechaniczny inwestor, SPY.",
    "Werdykt dopiero po 30 zamkniętych transakcjach. Kalibracja: czy deklarowana pewność zgadza się z trafnością."],
  "ai.critic": ["Krytyk sprawdza pracę Inwestora i Badacza: ustawia poziom nauki, pisze uwagi, nadaje werdykty hipotezom, prowadzi wnioski.",
    "Automat bierności sam podnosi poziom, gdy Inwestor długo nie wchodzi.",
    "Uwaga: werdykt „zatwierdzona” kod przyjmie dopiero po 20 transakcjach na żywo z dodatnią średnią."],
  "ai.research": ["Badacz wymyśla hipotezy, Python liczy je na historii (z kosztami, pesymistycznie).",
    "Droga hipotezy: odrzucona przez kod (sito) → do oceny → próba (Inwestor handluje nią małym ryzykiem) → zatwierdzona / wycofana.",
    "„na ślepo” = wynik wchodzenia w każdą świecę z tym samym wyjściem — hipoteza musi być lepsza. Przy setkach prób część dobrych wyników to przypadek: prawdziwy test to próba na żywo."],
  "ai.trades": ["Zamknięte transakcje Inwestora z notatką przy wejściu i wyjściu.", "Podstawa: S-… strategia z playbooka, HP-… hipoteza Badacza, own — własny pomysł."],
  "ai.journal": ["Zdarzenia nadzorcy i notatki wszystkich agentów, od najnowszego.", "Błędy na czerwono."],
  "ai.feed": ["Czy świece z Firestore docierają na Maca.", "Cel: najpóźniej 2 min po zapisie w Firestore."],
  "ai.playbook": ["60 strategii z poszukiwania (Etap 2). Ich sygnały Inwestor dostaje jako kandydatów.",
    "Mnożnik = jaka część pełnego ryzyka transakcji. „dP” — wynik na spółkach doubleProof (uczciwy test)."],
  "ai.lessons": ["Wnioski: wiedza, którą agenci czytają przed każdą decyzją.", "Zaczynał je Claude, teraz prowadzi Krytyk (najwyżej 50)."],
  "ai.flow": ["Spływ świec: zamknięcie → zapis w Firestore → kopia na Macu.", "Opóźnienie > 120 s na żółto."],
};

export const GUIDE = `
<h3>Jak czytać tę stronę</h3>
<ol>
  <li><b>Magistrala</b> (pasek pod nagłówkiem) — droga danych: Yahoo → Apps Script → Firestore → GitHub → Mac → ta strona. Lampka i wiek ostatniego znaku życia każdego ogniwa. Wszystko zielone = system żyje; szare = teraz nie pracuje z planu (noc, weekend, Mac wyłączony).</li>
  <li><b>Zakładki</b> (klawisze 1–4): <b>System</b> — czy działa zbieranie danych · <b>Inwestor</b> — mechaniczny inwestor z Apps Script · <b>FX</b> — prognoza walut · <b>AI</b> — agenci na Macu.</li>
  <li><b>Kolory</b>: zielony i czerwony — kierunek (wzrost/spadek) i stan; bursztyn — wyróżnienia; cyjan — prognozy.</li>
  <li><b>Codziennie (1 min)</b>: magistrala zielona? Zakładka AI: czy agenci pracują (panel „praca agentów”) i czy Inwestor wchodzi w transakcje.</li>
  <li><b>Raz w tygodniu</b>: średni wynik transakcji z przedziałem 95% (Inwestor i AI), hipotezy w próbie, przeglądy Krytyka.</li>
  <li><b>Zasada oceny</b>: nigdy po jednym dniu ani kilku transakcjach — średnia z przedziałem 95% i co najmniej 30 transakcji.</li>
  <li>Każdy panel ma w prawym górnym rogu <b>?</b> — krótki opis: co to jest, jak czytać, na co uważać.</li>
</ol>`;

const KEY = "ia4.help";
let open = new Set();
try { open = new Set(JSON.parse(localStorage.getItem(KEY) || "[]")); } catch (e) { /* bez pamięci */ }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify([...open])); } catch (e) { /* bez pamięci */ } };

export function help(key) {
  const L = H[key];
  if (!L) return "";
  return `<details class="help" data-help="${key}"${open.has(key) ? " open" : ""}><summary title="co to jest?" aria-label="opis panelu">?</summary>` +
    `<div class="help-body">${L.map(x => `<p>${x}</p>`).join("")}</div></details>`;
}

export function initHelp() {
  document.addEventListener("toggle", e => {
    const d = e.target;
    if (!(d instanceof HTMLDetailsElement) || !d.matches("details.help")) return;
    if (d.open) open.add(d.dataset.help); else open.delete(d.dataset.help);
    save();
  }, true);
  const g = document.getElementById("guide"), b = document.getElementById("guideBtn");
  if (!g || !b) return;
  g.innerHTML = GUIDE + `<p class="dim">Pełny opis: PRZEWODNIK.md w repozytorium.</p>`;
  const set = v => { g.hidden = !v; b.setAttribute("aria-pressed", v ? "true" : "false"); try { localStorage.setItem("ia4.guide", v ? "1" : "0"); } catch (e) { /* */ } };
  let first = null;
  try { first = localStorage.getItem("ia4.guide"); } catch (e) { /* */ }
  set(first === null ? true : first === "1");                // za pierwszym razem przewodnik otwarty
  b.addEventListener("click", () => set(g.hidden));
}
