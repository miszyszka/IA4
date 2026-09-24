# IA 4 — środowisko badawcze (Python, Mac)

**Wersja projektu: 0.16 (2026-09-24) — musi zgadzać się z `IA4_INSTRUKCJA.md`

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

Klucz **nigdy nie trafia do repozytorium** (zasada 2.6 i 6.5) — `config.py`
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

Pierwsze uruchomienie ściąga wszystko (~30 tys. świec przy komplecie
instrumentów, kilka minut). Kolejne pobierają **tylko przyrosty** — manifest
w `data/_manifest.json` pamięta ostatnią datę każdego instrumentu.

```bash
python -m ia4.sync              # przyrostowo (codzienne użycie)
python -m ia4.sync AAPL TSLA    # wybrane instrumenty
python -m ia4.sync --full       # od nowa, z pominięciem manifestu
```

## 4. Sprawdzian kryterium 0.9

```bash
python verify.py
```

Wypisze tabelę instrumentów w układzie takim jak w arkuszu PROJEKT plus
kontrole spójności. Żeby porównać automatycznie: skopiuj tabelę instrumentów
z arkusza PROJEKT do pliku `audyt.tsv` i uruchom

```bash
python verify.py --audit audyt.tsv
```

Kod wyjścia 0 = wszystko się zgadza, 1 = są rozbieżności do wyjaśnienia.

## 5. Wczytywanie danych do badań

```python
from ia4 import data

df = data.load("AAPL")                    # okres badawczy — DOMYŚLNIE
df = data.load(["AAPL", "TSLA", "NVDA"])  # kilka instrumentów
df = data.load()                          # wszystkie instrumenty
```

Kolumny: `symbol, date, slot (1–7), o, h, l, c, v`.

`v` to wolumen (decyzja D12). Świece zebrane przed wersją 0.8 mają tam 0 —
przy liczeniu parametrów opartych na wolumenie trzeba te sesje pominąć albo
dociągnąć historię ponownie.

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

## 6. Co dalej

| Etap | Co powstaje w tym folderze |
|---|---|
| 1 | `ia4/signals.py` — katalog S1, `ia4/engine.py` — silnik backtestu |
| 2 | `ia4/backtest.py` — liczenie 24 000 strategii, eksport do S1_WYNIKI |
| 3 | `ia4/features.py` — ~1000 parametrów, `ia4/model.py` — PT, eksport drzew do JSON |

---

## Struktura

```
ia4-research/
├── README.md            ten plik
├── requirements.txt     zależności
├── verify.py            sprawdzian kryterium 0.9
├── .gitignore           data/ i klucze nigdy do repo
├── ia4/
│   ├── config.py        klucz, granice skarbca i listy instrumentów z Firestore
│   ├── sync.py          Firestore → parquet, tylko przyrosty
│   └── data.py          wczytywanie z wymuszoną granicą skarbca
└── data/                pamięć podręczna (poza gitem)
    ├── _manifest.json
    └── {SYMBOL}.parquet
```
