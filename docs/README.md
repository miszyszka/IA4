# docs/ — strona IA4 (konsola systemu)

**Wersja projektu: 1.37 (2026-10-13)** · zasady: `IA4_INSTRUKCJA.md`, sekcja 11b

Adres: https://miszyszka.github.io/IA4/ (GitHub Pages z brancha `main`, folder `/docs`).
Każdy `git push` na `main` publikuje stronę w ok. minutę. Bez buildu i bez bibliotek: zwykłe
pliki HTML, CSS i moduły JavaScript.

```
index.html            szkielet: bramka hasła, nagłówek z zakładkami, magistrala, miejsca na widoki
css/ia4.css           wygląd (kolory w :root), układ, wersja telefonu (@media max-width 760px)
css/fonts.css         kroje pisma z fonts/ (Chakra Petch, IBM Plex Mono — licencja OFL)
js/core.js            źródła danych (SOURCES), odświeżanie, formaty dat i liczb, godziny rynków, bramka hasła
js/health.js          „czy system żyje”: stan ogniw magistrali (Yahoo → Apps Script → Firestore → GitHub → Mac FX → Mac AI → strona)
js/chart.js           wykresy SVG: prognoza FX, mini-wykres, krzywa wyniku
js/main.js            start: bramka, zakładki (#system, #inwestor, #fx, #ai; klawisze 1–4), zegary, magistrala
js/views/system.js    zakładka System
js/views/investor.js  zakładka Inwestor (+ renderInvestor — wspólne z przyszłym inwestorem FX)
js/views/fx.js        zakładka FX
js/views/ai.js        zakładka AI — AI Investor na Macu (ai-live/status.json, instrukcja 11c.11)
```

## Jak dodać zakładkę

1. `js/views/nazwa.js`:
   ```js
   import { store } from "../core.js";
   export default {
     id: "nazwa", title: "nazwa",
     render(el, changed) { el.innerHTML = `<div class="grid"><div class="pane c12"><h2>tytuł</h2>…</div></div>`; },
     tick(el) { /* co sekundę, opcjonalnie: liczniki czasu */ },
   };
   ```
2. `js/main.js` — import i dopisanie do `VIEWS`.
3. `index.html` — link w `<nav class="tabs">` i `<section class="view" id="view-nazwa" data-view="nazwa" hidden>`.

## Jak dodać źródło danych

Wpis w `SOURCES` (`js/core.js`): gałąź i ścieżka pliku w repo, co ile sekund. Pliki godzinowe —
przez `raw.githubusercontent.com` (bez limitu, do ok. 5 min opóźnienia); pliki „na żywo” — `api: true`
(API GitHub z ETag; odpowiedź „bez zmian” nie zużywa limitu 60 zapytań na godzinę). Widok czyta
`store.get("id")`; brak pliku = `null`.

## Klocki wyglądu

- `.pane` + `<h2>` — panel z tytułem w ramce; szerokość `c3` … `c12` (siatka 12 kolumn),
- `.reads` / `.read` (`.k` etykieta, `.v` wartość, `.s` opis) — odczyty,
- `.tbl` w `.tbl-wrap` (`.scroll` — z przewijaniem), `.num` — liczby do prawej,
- `.log` — strumień zdarzeń, `.tape` — taśma świec, `.matrix` / `.cell` — siatka instrumentów,
- `.led ok|warn|bad|off` — lampka stanu, `.up` / `.down` — kierunek, `.desk-only` — ukryte na telefonie,
- `data-ts="ms"` (wiek) i `data-cd="ms"` (odliczanie) — odświeżane co sekundę przez `tick`.

## Hasło

Bramka w przeglądarce: w `core.js` jest tylko skrót PBKDF2-SHA256 hasła (150 000 iteracji),
odblokowanie pamiętane 30 dni. Dane na stronie pochodzą z publicznego repo, więc bramka nie chroni
samych danych. Zmiana hasła: nowy skrót (`node -e "console.log(require('crypto').pbkdf2Sync('NOWE','ia4/gate/v1',150000,32,'sha256').toString('hex'))"`)
w `GATE.hash`.

## Podgląd lokalny

```bash
cd ~/Desktop/IA4/docs && python3 -m http.server 8000     # http://localhost:8000 (moduły ES nie działają z file://)
```
