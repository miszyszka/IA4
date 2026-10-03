# IA 4 — Python na Macu: kopia bazy i poszukiwanie strategii

**Wersja projektu: 1.14 (2026-10-03)** — musi zgadzać się z `IA4_INSTRUKCJA.md`

Dwie rzeczy:
1. `python -m ia4.sync` — ściąga świece z Firestore na dysk (`data/*.parquet`), przy
   kolejnych uruchomieniach tylko przyrosty. Firestore jest jedynym źródłem prawdy —
   `data/` można skasować i odtworzyć.
2. `python -m ia4.lab` — bez końca szuka strategii na kopii lokalnej i co 30 minut
   wysyła log i wyniki na branch `research` w GitHub (instrukcja, sekcje 8–10).

## Instalacja (raz)

```bash
cd ~/Desktop/IA4/ia4-research
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Klucz serwisowy Firebase (konsola Firebase → projekt `ia-4-ff7af` → Ustawienia
projektu → Konta usługi → Wygeneruj nowy klucz prywatny) zapisz **poza repozytorium**:

```bash
mkdir -p ~/.ia4
mv ~/Downloads/ia-4-ff7af-*.json ~/.ia4/serviceAccount.json
chmod 600 ~/.ia4/serviceAccount.json
```

Inna lokalizacja: `export IA4_FIREBASE_KEY=/ścieżka/do/klucza.json`.

Push na branch `research` używa tego samego dostępu co zwykły `git push` w tym repo.

## Poszukiwanie strategii

```bash
source .venv/bin/activate
python -m ia4.lab.selftest        # test silnika — musi być „WYNIK: OK”
python -m ia4.lab                 # liczy do Ctrl+C (zapisuje stan i wysyła log przed końcem)
python -m ia4.lab --hours 5       # liczy 5 godzin
python -m ia4.lab --check         # tylko synchronizacja i kontrola kompletności bazy
python -m ia4.lab --workers 4     # 4 procesy — ok. połowa mocy M2 (domyślnie rdzenie − 1)
python -m ia4.lab --no-push       # bez GitHub (test)
```

Przy każdym starcie: `caffeinate` (Mac nie zaśnie), synchronizacja, kontrola bazy,
pobranie `research/config.json` i punktu wznowienia, dalsze liczenie od miejsca,
w którym skończył poprzedni przebieg. Wyniki: branch `research` (klon w
`research-repo/`), lokalna lista przetestowanych reguł: `state/tested.txt`.

Skrót (raz): `alias ia4='cd ~/Desktop/IA4/ia4-research && source .venv/bin/activate && python -m ia4.lab --workers 4'`
w `~/.zshrc` — potem wystarczy `ia4`.

Poszukiwanie używa tylko spółek głównych i kontrolnych. Grupa **doubleProof** (20 spółek)
jest synchronizowana, ale nigdy nie bierze udziału w szukaniu — służy do ręcznej
weryfikacji strategii (instrukcja, sekcja 6a).

## Weryfikacja na doubleProof

`python -m ia4.lab` sam przelicza strategie aktywne na 20 spółkach doubleProof (przy starcie
i co 30 min, gdy zmieniły się strategie albo dane) i zapisuje `research/doubleproof.json`.
Ręcznie, bez szukania: `python -m ia4.lab.verify`. Wynik w arkuszu STRATEGIE DOUBLEPROOF.

## Test zgodności z paper tradingiem

Silnik reguł istnieje też w JavaScript (`PaperEngine.gs`). Po każdej zmianie języka reguł:

```bash
python tests/parity_dump.py /tmp/ia4_parity.json && node tests/parity.js /tmp/ia4_parity.json
```

Wynik musi brzmieć „rozbieżności: sygnały 0, transakcje 0” (potrzebny Node.js).

## Kopia bazy

```bash
python -m ia4.sync              # przyrostowo (robi to też ia4.lab przy starcie)
python -m ia4.sync AAPL TSLA    # wybrane instrumenty
python -m ia4.sync --full       # od nowa — ok. 48 000 odczytów (prawie cały dzienny limit)
```

```python
from ia4.sync import load
df = load("AAPL")   # kolumny: symbol, date, slot (1–7), o, h, l, c, v
```

## Odtworzenie zapisanej strategii

```python
import json
from pathlib import Path
from ia4 import config
from ia4.lab import data, rules

s = json.load(open("research-repo/research/strategies/S-xxxxxxxxxx.json"))
m = data.load_local(["AAPL", "TSLA", "NVDA"], config.CACHE_DIR)
sig_t, fc, _ = rules.entries(s["rule"], m)      # świece sygnału i świece FC
```

Format bazy, skarbiec, język reguł i kryteria: `IA4_INSTRUKCJA.md`.
