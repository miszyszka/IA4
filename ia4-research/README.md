# IA 4 — kopia lokalna bazy (Python, Mac)

**Wersja projektu: 1.0 (2026-09-30)** — musi zgadzać się z `IA4_INSTRUKCJA.md`

Ten folder robi jedną rzecz: ściąga świece z Firestore na dysk (`data/*.parquet`)
i dociąga przyrosty przy każdym kolejnym uruchomieniu. Firestore jest jedynym
źródłem prawdy — `data/` można skasować i odtworzyć.

## Instalacja (raz)

```bash
cd ~/Desktop/IA4/ia4-research        # albo gdzie trzymasz repo
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

## Użycie

```bash
source .venv/bin/activate
python -m ia4.sync              # przyrostowo (codziennie)
python -m ia4.sync AAPL TSLA    # wybrane instrumenty
python -m ia4.sync --full       # od nowa — ok. 37 000 odczytów, najwyżej raz dziennie
```

W Pythonie:

```python
from ia4.sync import load
df = load("AAPL")   # kolumny: symbol, date, slot (1–7), o, h, l, c, v
```

Format bazy i zasady (w tym skarbiec — najstarsze 800 świec) opisuje
`IA4_INSTRUKCJA.md`.
