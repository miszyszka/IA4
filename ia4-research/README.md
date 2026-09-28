# IA 4 — środowisko badawcze (Python, Mac)

**Wersja projektu: 0.40 (2026-09-28) — musi zgadzać się z `IA4_INSTRUKCJA.md`

Etap 0B. Ten folder robi jedną rzecz: ściąga świece z Firestore na dysk i daje
do nich dostęp tak, żeby nie dało się przypadkiem zajrzeć do skarbca.

Firestore zostaje **jedynym źródłem prawdy** (sekcja 3 instrukcji). Pliki
parquet w `data/` to tylko pamięć podręczna — można je skasować i odtworzyć.

---

## 1. Instalacja (raz)

Python 3.11+ (sprawdź `python3 --version`; na nowszych macOS jest w komplecie,
inaczej `brew install python@3.12`).

```bash
cd ~/Desktop/IA4/ia4-research        # albo gdzie trzymasz repo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Przy każdej kolejnej sesji wystarczy `source .venv/bin/activate`.

## 2. Klucz serwisowy Firebase (raz)

Klucz **nigdy nie trafia do repozytorium** (zasada 2.6 i Etap 0, pkt 5) — `config.py`
sprawdza to i odmawia startu, gdyby leżał w środku folderu.

1. Konsola Firebase → projekt `ia-4-ff7af` → ⚙ Ustawienia projektu → **Konta usługi**
2. **Wygeneruj nowy klucz prywatny** → pobierze się plik `.json`
3. Zapisz go poza repozytorium:

```bash
mkdir -p ~/.ia4
mv ~/Downloads/ia-4-ff7af-*.json ~/.ia4/serviceAccount.json
chmod 600 ~/.ia4/serviceAccount.json
```

Inna lokalizacja: ustaw `export IA4_FIREBASE_KEY=/ścieżka/do/klucza.json`
(najlepiej w `~/.zshrc`).

## 3. Pierwsze pobranie danych

```bash
python -m ia4.sync
```

Pierwsze uruchomienie ściąga wszystko (~190 tys. świec, ok. **37 000 odczytów
Firestore** — trzy czwarte dziennego darmowego limitu 50 000, więc **najwyżej
raz dziennie**). Kolejne pobierają **tylko przyrosty**: nowe sesje z ostatnich
14 dni oraz każdy dokument, który Apps Script przepisał od poprzedniej
synchronizacji (pole `updatedAt`) — także sesje sprzed roku, do których
dopisano wolumen albo załatano lukę. Manifest w `data/_manifest.json` pamięta
datę synchronizacji każdego instrumentu; manifest sprzed wersji 0.30 (bez tej
daty) wymusza jednorazowo pełne pobranie.

**Kiedy pierwsze pobranie:** dopiero gdy menu IA 4 → Projekt → „Postęp
dopisywania wolumenu” pokaże koniec (D12). Wcześniej kopia miałaby dziury
w wolumenie, a pełne pobranie trzeba by powtórzyć.

```bash
python -m ia4.sync              # przyrostowo (codzienne użycie)
python -m ia4.sync AAPL TSLA    # wybrane instrumenty
python -m ia4.sync --full       # od nowa, z pominięciem manifestu
```

## 4. Sprawdzian kryterium 0.9

```bash
python verify.py
```

Wypisze tabelę instrumentów w układzie takim jak w arkuszu PROJEKT i sam
sprawdzi:

- **„PRZED PRACĄ" (0.33)** — pierwsza sekcja wyjścia, zanim cokolwiek innego:
  czy kopia lokalna (manifest `ia4.sync`) jest nowsza niż ostatni audyt Apps
  Script z telemetrii (czyli czy w Firebase mogło pojawić się coś nowego,
  czego jeszcze nie ma lokalnie), i co telemetria pokazuje jako otwarte luki
  (w tym `ZERO_WOLUMEN`, L32 — świece z wolumenem 0, których automat w tle
  jeszcze nie złatał). **Bez żadnego zapytania do Firestore** — tylko lokalny
  manifest i telemetria już ściągnięta z GitHuba — więc można to sprawdzać
  dowolnie często bez zużywania dziennego limitu,
- **zgodność z pełnym audytem** — tabelę instrumentów z audytu bierze
  z `telemetry/state.json` (w klonie repozytorium, a gdy go nie ma — z GitHub);
  porównuje tylko zakres dat, który widział audyt, więc sesje dopisane później
  nie są rozbieżnością. Nie trzeba niczego kopiować z arkusza (stary sposób
  `python verify.py --audit audyt.tsv` nadal działa),
- **wolumen (D12)** — sesje bez wolumenu w okresie badawczym; kilka sesji na
  samym początku historii (poza zasięgiem Yahoo, ~730 dni) jest wypisanych
  informacyjnie, dziura w środku historii blokuje kryterium,
- **skoki ceny > 15% (D11)** — do oceny „split czy wynik kwartalny”; skok
  ≥ 40% blokuje kryterium, dopóki sesja nie trafi na listę splitów,
- instrumenty bez danych, z historią zaczynającą się w skarbcu, poniżej
  100 sesji, oznaczone przez `Proof.gs` jako niepełne lub nieudane.

Skrypt czyta pliki parquet bezpośrednio, więc nie liczy się jako zajrzenie
na poletko. Kod wyjścia 0 = wszystko się zgadza, 1 = są rozbieżności do
wyjaśnienia.

Testy potoku danych (bez Firestore, na atrapie):

```bash
python tests/test_data_pipeline.py
```

## 5. Wczytywanie danych do badań

```python
from ia4 import data

df = data.load("AAPL")                    # OKRES ODKRYWANIA - domyslnie
df = data.load(["AAPL", "TSLA", "NVDA"])  # kilka instrumentów
df = data.load()                          # wszystkie instrumenty
```

Kolumny: `symbol, date, slot (1–7), o, h, l, c, v`.

`v` to wolumen (decyzja D12). Automat dopisał go do całej historii, do
której Yahoo jeszcze sięga; najstarsze sesje (poza ~730 dniami) zostają z 0 —
sygnały z warunkiem wolumenu ich nie używają (instrukcja 1.3).

**Okresy (5.1):** `discovery` (domyślny, uczenie), `plot` (poletko — sprawdzian
raz na etap, wymaga podania powodu i jest logowany), `research` (odkrywanie +
poletko łącznie — **od 0.30 też wymaga powodu i też jest liczony jako zajrzenie
na poletko**), `vault` (skarbiec, raz w projekcie), `live`.

```python
data.load("AAPL", period="plot", plot_reason="Etap 2: lista S2 po filtrach")
```

**Skarbiec jest zamknięty programowo.** `data.load()` domyślnie zwraca tylko
okres badawczy, a próba sięgnięcia po skarbiec kończy się wyjątkiem:

```python
data.load("AAPL", period="vault")
# VaultError: Próba odczytu skarbca (2026-03-23 – 2026-09-22) bez potwierdzenia.
```

Otwarcie wymaga świadomego `unlock_vault=True` — raz, na końcu Etapu 3,
z zapisaniem daty w arkuszu PROJEKT (zasada 5.1). To nie jest formalność:
zajrzenie do skarbca wcześniej unieważnia jedyny niezależny sprawdzian,
jaki ma ten projekt, i nikt tego potem nie wykryje po samym wyniku.

## 6. Etap 1 — silnik i częstość sygnałów

Silnik (`signals.py`, `engine.py`) jest sprawdzany **wyłącznie na sztucznych
świecach** — w Etapie 1 nie wolno policzyć żadnego wyniku transakcji (1.1):

```bash
python3 tests/test_signals.py    # każda rodzina sygnałów + rozgrzewka, dziury, split, wolumen
python3 tests/test_engine.py     # SL/TP, luki, wieloznaczność, H, END, pkt 8 + porównanie z dosłownym kontraktem
python3 tests/test_nyse.py       # kalendarz = ten sam co w Apps Script
```

Jedyne, co Etap 1 liczy na prawdziwych danych, to **częstość** (kryterium 1.3) —
dopiero po końcu dopisywania wolumenu (D12) i świeżym `python3 -m ia4.sync`:

```bash
python3 -m ia4.frequency         # okres odkrywania → ../s1/frequency.json (ok. 1 min)
python3 -m ia4.catalog           # dołącza częstość, nadaje status „za rzadki” (< 30 dni w grupie głównej)
```

Potem oba pliki do repozytorium i w arkuszu: IA 4 → Projekt → „Wczytaj katalog S1
z GitHub”. Kolejność zamknięcia całego etapu: instrukcja 1.7, „Zamknięcie Etapu 1”.

## 7. Etap 2 — backtest S1

Dopiero po potwierdzeniu D29 (instrukcja, sekcja 9):

```bash
python3 -m ia4.backtest --limit 3   # próba na 3 sygnałach, nic nie zapisuje
python3 -m ia4.backtest             # całość: 41 000 strategii, ok. 15–25 min
cd .. && git add s1-backtest && git commit -m "Backtest S1" && git push
```

Potem w arkuszu: IA 4 → Projekt → „Wczytaj wyniki S1-BACKTEST z GitHub”.
Liczone tylko na okresie odkrywania — poletko raz, na gotowej liście S2 (2.4).

## 8. Co dalej

| Etap | Co powstaje w tym folderze |
|---|---|
| 1 | `ia4/catalog.py` — katalog S1 (gotowe, 1a); `ia4/indicators.py` — wskaźniki (0.32); `ia4/signals.py`, `ia4/engine.py`, `ia4/bars.py`, `ia4/nyse.py` — silnik (gotowe, 0.36); `ia4/frequency.py` — częstość (1.3) |
| 2 | symulacja portfela 57 200 strategii (2.1), eksport do `s1-backtest/results.csv` → arkusz S1-BACKTEST (2.3) |
| 3 | `ia4/features.py` — ~1000 parametrów, `ia4/model.py` — PT, eksport drzew do JSON |

---

## Struktura

```
ia4-research/
├── README.md            ten plik
├── requirements.txt     zależności
├── verify.py            sprawdzian kryterium 0.9 (audyt, wolumen, skoki ceny)
├── .gitignore           data/ i klucze nigdy do repo
├── ia4/
│   ├── config.py        klucz, granice skarbca i listy instrumentów z Firestore
│   ├── sync.py          Firestore → parquet, tylko przyrosty (także przepisane wstecz)
│   ├── data.py          wczytywanie z wymuszoną granicą skarbca i licznikiem poletka
│   ├── catalog.py       katalog S1 → s1/catalog.json (Etap 1a); dołącza częstość
│   ├── indicators.py    wskaźniki z 1.3 — nie czyta danych (Etap 1b, D25)
│   ├── nyse.py          kalendarz sesji (święta, sesje skrócone) = listy z Apps Script
│   ├── bars.py          świece instrumentu: dziury (D27), odcinki między splitami (D24), SPY
│   ├── signals.py       286 sygnałów S1 + warunki ważności z kontraktu silnika
│   ├── engine.py        transakcje: SL/TP/H, luki, wieloznaczność, koszty, LONG/SHORT
│   ├── frequency.py     częstość sygnałów na okresie odkrywania (1.3) → s1/frequency.json
│   └── backtest.py      Etap 2: wszystkie strategie S1, obie grupy → s1-backtest/results.csv
├── tests/
│   ├── _bars.py               sztuczne świece dla testów
│   ├── test_catalog.py        katalog S1
│   ├── test_indicators.py     wskaźniki, na ręcznie policzonych przykładach
│   ├── test_signals.py        każda rodzina sygnałów + warunki ważności
│   ├── test_engine.py         silnik transakcji
│   ├── test_nyse.py           kalendarz zgodny z Apps Script
│   ├── test_frequency.py      częstość i jej dołączanie do katalogu
│   ├── test_backtest.py       portfel, metryki 2.2, D10, bootstrap, FDR
│   └── test_data_pipeline.py  sync, data, verify na atrapie Firestore
└── data/                pamięć podręczna (poza gitem)
    ├── _manifest.json
    └── {SYMBOL}.parquet
```
