# IA 4 — instrukcja projektu

**Wersja:** 1.0
**Data:** 30 września 2026
**Aktualny etap:** 🟨 Etap 1 — Baza danych. System działa od tygodni; zostało wdrożenie wersji 1.0 w Apps Script (sekcja 8) i jedna noc potwierdzająca, że nowy automat działa.

Ten plik jest jedynym źródłem prawdy i zbiorem żelaznych zasad projektu. Jeśli kod, arkusz albo telemetria się z nim rozjeżdżają, obowiązuje ten plik, a rozbieżność trzeba naprawić.

---

## 1. Cel

**Jedyny cel projektu na dziś: budować i utrzymywać bazę świec 1h w Firestore.** Baza ma być kompletna, rosnąć każdego dnia sesyjnego i mieć stały, prosty format, żeby w Etapie 2 można ją było łatwo przeliczać w Pythonie na Macu.

Wszystko, co nie służy temu celowi (strategie, backtesty, poletko, rating, inwestorzy, dashboard, audyty luk), zostało usunięte w wersji 1.0. Historia tych prac jest w historii gita do wersji 0.47.

---

## 2. Żelazne zasady

1. **Firestore jest jedynym źródłem danych.** Kopia na Macu (`ia4-research/data/`) to tylko kopia robocza — można ją skasować i odtworzyć.
2. **Baza tylko rośnie.** Zapisujemy wyłącznie zamknięte świece. Niczego nie kasujemy. Wolno przepisać sesję tylko danymi pobranymi ponownie z Yahoo (nocne odświeżenie, „Uzupełnij ostatni miesiąc”).
3. **Format bazy (sekcja 4) jest stały.** Każda jego zmiana wymaga najpierw zmiany tej instrukcji, zgody człowieka i opisu migracji istniejących danych.
4. **Skarbiec = najstarsze 800 świec każdego instrumentu** (sekcja 6). W Etapie 2 nie wolno go używać do szukania, strojenia ani oceny czegokolwiek — do czasu jednorazowego sprawdzianu końcowego.
5. **Sekrety nigdy nie trafiają do repozytorium:** klucz serwisowy Firebase (`~/.ia4/serviceAccount.json`) i token GitHub (Script Properties → `GITHUB_TOKEN`).
6. **System jest minimalny.** Nowa funkcja, arkusz, plik czy dziennik pojawia się tylko za zgodą człowieka i najpierw jako zmiana tej instrukcji.
7. **Współpraca z Claude:**
   - na początku rozmowy Claude pobiera repozytorium `github.com/miszyszka/IA4.git` (branch `main`), czyta ten plik i `telemetry/state.json`,
   - każdą zmianę Claude commituje i pushuje w tej samej turze; bez klucza — prosi o niego,
   - pracę wykraczającą poza tę instrukcję albo pomysł na jej zmianę Claude najpierw proponuje i czeka na zgodę,
   - Claude nie ma dostępu do arkusza ani edytora Apps Script: użytkownik ręcznie wkleja zmienione pliki `.gs` do Apps Script i robi `git pull` na Macu.
8. **Jedna wersja dla całego projektu.** Ten sam numer w nagłówku tej instrukcji, w nagłówku każdego pliku `.gs`, w `CONFIG.VERSION` (`Code.gs`) i w `ia4-research/`. Zmiana znacząca (logika, zasada, format, etap) podbija wersję i dostaje wpis w sekcji 9. Drobne poprawki — tylko opis w commicie. (`appsscript.json` nie nosi wersji — JSON nie ma komentarzy.)

---

## 3. Architektura

```
Yahoo Finance ──(Apps Script, co minutę)──▶ Firestore ──(python -m ia4.sync)──▶ Mac: ia4-research/data/*.parquet
                        │
                        ├──▶ arkusz STATS (stan automatu)
                        └──▶ GitHub: telemetry/state.json (co godzinę, gdy coś się zmieniło)
```

| Plik | Rola |
|---|---|
| `Code.gs` | cały automat: listy instrumentów, zbieranie na żywo, nocne odświeżenie, liczenie bazy, zapis do Firestore, arkusz STATS, menu, jednorazowe sprzątanie po 1.0 |
| `Telemetry.gs` | stan zbierania → `telemetry/state.json` w GitHub |
| `appsscript.json` | uprawnienia Apps Script |
| `ia4-research/ia4/sync.py` | Firestore → lokalne pliki parquet, tylko przyrosty |
| `ia4-research/ia4/config.py` | klucz serwisowy (poza repo), listy instrumentów z Firestore |
| `ia4-research/README.md` | instalacja i użycie synchronizacji |
| `telemetry/state.json` | stan systemu, generowany — nie edytować |
| `IA4_INSTRUKCJA.md` | ten plik |

---

## 4. Baza danych

### Instrumenty (55)

| Grupa | Kolekcja | Instrumenty |
|---|---|---|
| główne (3) | `stocks` | AAPL, TSLA, NVDA |
| kontrolne (50) | `proof` | DELL, AMAT, PLTR, ORCL, XOM, V, WMT, JPM, MU, META, AVGO, MSFT, GOOGL, JNJ, MA, ABBV, BAC, CVX, MRK, PG, HD, PM, WFC, CRM, CAT, HON, UNP, RTX, AMZN, MCD, NKE, SBUX, T, VZ, NFLX, DIS, UNH, LLY, PFE, MDT, PLD, AMT, LIN, FCX, NEE, DUK, GS, AXP, KO, PEP |
| tło rynku (2) | `context` | SPY, QQQ |

Nazwy grup i kolekcji są historyczne; zostają, żeby nie przenosić danych. Listy są w `Code.gs` (`CONFIG`) i w Firestore (`system/universe`).

### Świeca

Świece 1h sesji regularnej NYSE, bez pre/after-market. Sesja ma 7 świec, numerowanych 1–7:

| nr | ET | PL (zwykle) |
|---|---|---|
| 1–6 | 9:30–10:30 … 14:30–15:30 | 15:30–16:30 … 20:30–21:30 |
| 7 | 15:30–16:00 (pół godziny) | 21:30–22:00 |

Sesja skrócona (np. 13:00 ET) ma 4 świece. Ceny zaokrąglone do 4 miejsc. Wolumen `0` znaczy „Yahoo nie podał”, nie „brak obrotu”. Dni bez sesji (weekendy, `US_MARKET_HOLIDAYS` w `Code.gs`) nigdy nie trafiają do bazy.

### Format w Firestore

```
stocks/{SYMBOL}/candles/{data}_{nr}    spółki główne — jeden dokument na świecę
  symbol, date (RRRR-MM-DD), slot (1–7), label, startPL, startET,
  open, high, low, close, volume, candleTime, source, updatedAt
stocks/{SYMBOL}                        podsumowanie: lastDate, lastSlot, lastLabel, lastClose, updatedAt

proof/{SYMBOL}/sessions/{data}         kontrolne — cała sesja w jednym dokumencie
context/{SYMBOL}/sessions/{data}       tło rynku — ten sam format
  symbol, date, bars (liczba świec), slots [1..7], o [], h [], l [], c [], v [],
  startPL, firstCandleTime, updatedAt
  (tablice slots/o/h/l/c/v są równoległe: element i = świeca nr slots[i])
proof/{SYMBOL}, context/{SYMBOL}       podsumowanie: lastDate, liveUpdatedAt (+ pola z pobierania historii)

system/universe                        listy instrumentów: live, proof, context
system/status                          ostatni zapis automatu, wersja
```

`updatedAt` zmienia się przy każdym zapisie dokumentu — po nim synchronizacja w Pythonie rozpoznaje, co się zmieniło od poprzedniego razu.

### Zakres

Historia od połowy września 2024 (granica Yahoo: ok. 730 dni wstecz dla świec 1h — starszych danych nie da się już pobrać), ok. 3500 świec na instrument na koniec września 2026. Każdy dzień sesyjny dokłada 7 świec na instrument.

### Jak baza jest aktualizowana (`Code.gs`)

1. **Na żywo.** Trigger `runCollector` co minutę. Po zamknięciu każdej świecy automat pobiera z Yahoo ostatnie 5 dni i zapisuje tylko nowe, zamknięte świece. Tuż po zamknięciu ponawia co 30 s, aż spółki główne dostaną świecę. Pamięć „co już zapisane” przesuwa się dopiero po potwierdzeniu zapisu przez Firestore.
2. **Nocne odświeżenie.** Raz na dzień sesyjny, 45 min po zamknięciu, automat przepisuje ostatnie ~5 sesji wszystkich instrumentów (~400 dokumentów). Świeca brakująca z powodu awarii wraca sama tej samej nocy. Nieudane odświeżenie jest ponawiane co 30 min.
3. **Liczenie bazy.** Po nocnym odświeżeniu automat liczy świece i pierwszą datę każdego instrumentu (zapytania agregujące, ~110 odczytów) — widać to w STATS i w `telemetry/state.json`.
4. **Ręcznie:** menu IA 4 → „Uzupełnij ostatni miesiąc” (po dłuższej przerwie automatu), „Nocne odświeżenie teraz”.

Limit Firestore (plan Spark): 20 000 zapisów i 50 000 odczytów dziennie. Normalny dzień to ok. 1200 zapisów.

**Raz w roku (grudzień):** dopisać święta NYSE na kolejny rok do `US_MARKET_HOLIDAYS` w `Code.gs`.

---

## 5. Kopia lokalna na Macu (`ia4-research/`)

```bash
cd ia4-research && source .venv/bin/activate
python -m ia4.sync            # przyrostowo: nowe sesje + wszystko przepisane od ostatniego razu
python -m ia4.sync --full     # od nowa (~37 000 odczytów — najwyżej raz dziennie)
```

Wynik: `data/{SYMBOL}.parquet`, jedna tabela na instrument, kolumny `symbol, date, slot (1–7), o, h, l, c, v`, posortowana po `(date, slot)`; `data/_manifest.json` pamięta stan synchronizacji. Oba formaty Firestore sprowadzone do tej samej tabeli. W kodzie: `from ia4.sync import load; df = load("AAPL")`. Instalacja i klucz: `ia4-research/README.md`.

---

## 6. Skarbiec — najstarsze 800 świec

- **Definicja:** dla każdego instrumentu osobno — jego 800 najwcześniejszych świec w bazie, w kolejności `(date, slot)`. Dla spółek z pełną historią to mniej więcej wrzesień 2024 – luty 2025.
- **Dlaczego z początku, a nie z końca:** Yahoo nie oddaje danych starszych niż ~730 dni, więc baza nigdy nie urośnie wstecz — najstarsze 800 świec to zbiór stały na zawsze. Wszystko po nim to baza badawcza, która rośnie każdego dnia i z czasem daje coraz szersze pole do badań.
- **Zasada:** w Etapie 2 skarbiec jest wyłączony z szukania, strojenia i oceny. Otwiera się go raz, do jednego sprawdzianu końcowego. Porażka na skarbcu jest wynikiem, nie błędem do poprawienia.
- **Egzekwowanie:** kod Etapu 2 wczytujący dane musi sam odcinać skarbiec (zasada wymuszona kodem, nie pamięcią). Baza i synchronizacja przechowują wszystko bez podziału.

---

## 7. Etapy

Status: ⬜ nie rozpoczęty · 🟨 w toku · ✅ zakończony

### Etap 1 — Baza danych 🟨

Ukończony, gdy:
- 1.1 wersja 1.0 wklejona do Apps Script i „Sprzątanie po wersji 1.0” wykonane (sekcja 8),
- 1.2 w Apps Script są tylko `Code.gs`, `Telemetry.gs`, `appsscript.json`; triggery tylko `runCollector` i `telemetryHourly`,
- 1.3 po pierwszej nocy `telemetry/state.json` pokazuje nocne odświeżenie i liczbę świec każdego instrumentu,
- 1.4 `python -m ia4.sync` na Macu działa na wersji 1.0.

Po ukończeniu Etap 1 nie kończy pracy — automat działa dalej bez końca.

### Etap 2 — Przeliczanie danych na Macu ⬜

Zakres do ustalenia. Pracuje na kopii lokalnej z `ia4.sync`, z wyłączonym skarbcem (sekcja 6).

---

## 8. Wdrożenie wersji 1.0 (jednorazowo)

1. W edytorze Apps Script **usuń pliki:** `Project.gs`, `Proof.gs`, `History.gs`, `Investor.gs`, `Catalog.gs`, `Backtest.gs`.
2. **Podmień** treść `Code.gs` i `Telemetry.gs` na wersję z GitHub. Zapisz.
3. Odśwież arkusz → menu **IA 4 → 🧹 Sprzątanie po wersji 1.0 (raz)**. Usuwa stare arkusze (PROJEKT, _AUDYT, _AUDYT_DECYZJE, S1, S1-BACKTEST, Transaction LOG), stare triggery i właściwości skryptu, dokumenty `system/project`, `system/history`, `system/telemetry`; potem sam robi „Konfiguruj” (nowy STATS, triggery, `system/universe`, uzupełnienie miesiąca). **Świec nie rusza.** Token GitHub zostaje.
4. Menu IA 4 → **📡 Wyślij stan do GitHub teraz** — `telemetry/state.json` przyjmie nowy, krótki format.
5. Na Macu: `git pull`. W `ia4-research/` zostaje folder `data/` z dotychczasową kopią — działa dalej bez zmian.

Dokumenty inwestorów z Firestore (jeśli istnieją) i stare pliki w `ia4-research/` spoza repo (np. wyniki backtestów) nie są ruszane — można je usunąć ręcznie. Po zamknięciu Etapu 1 tę sekcję i funkcję `cleanupLegacy` w `Code.gs` można usunąć.

---

## 9. Dziennik zmian

| Wersja | Data | Zmiana |
|---|---|---|
| 1.0 | 2026-09-30 | Nowe założenia: jedynym celem jest baza danych. Usunięte strategie S1/S2, backtesty, poletko, stary skarbiec, etapy 0–5, audyt i łatanie luk, dopisywanie wolumenu, pobieranie historii, inwestorzy, dashboard i cały Python poza synchronizacją. Zbieranie w jednym pliku `Code.gs` + nocne odświeżenie ostatnich 5 sesji i liczenie bazy. Telemetria skrócona do stanu bazy. Skarbiec = najstarsze 800 świec. Instrukcja przepisana od zera. |
| ≤ 0.47 | do 2026-09-29 | Poprzedni projekt (strategie, backtesty, etapy 0–5) — w historii gita. |
