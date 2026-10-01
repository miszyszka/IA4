# IA 4 — Python na Macu: kopia bazy i poszukiwanie strategii

**Wersja projektu: 1.6 (2026-10-01)** — musi zgadzać się z `IA4_INSTRUKCJA.md`

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
python -m ia4.lab --workers 4     # mniej procesów (domyślnie rdzenie − 1)
python -m ia4.lab --no-push       # bez GitHub (test)
```

Przy każdym starcie: `caffeinate` (Mac nie zaśnie), synchronizacja, kontrola bazy,
pobranie `research/config.json` i punktu wznowienia, dalsze liczenie od miejsca,
w którym skończył poprzedni przebieg. Wyniki: branch `research` (klon w
`research-repo/`), lokalna lista przetestowanych reguł: `state/tested.txt`.

## Kopia bazy

```bash
python -m ia4.sync              # przyrostowo (robi to też ia4.lab przy starcie)
python -m ia4.sync AAPL TSLA    # wybrane instrumenty
python -m ia4.sync --full       # od nowa — ok. 37 000 odczytów, najwyżej raz dziennie
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
