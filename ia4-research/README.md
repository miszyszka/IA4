# IA 4 — Python na Macu: kopia bazy i poszukiwanie strategii

**Wersja projektu: 1.47 (2026-10-17)** — musi zgadzać się z `IA4_INSTRUKCJA.md`

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

Skrót: funkcja `ia4` w `~/.zshrc` — `ia4` uruchamia poszukiwanie, `ia4 start` — AI Investor (niżej).
w `~/.zshrc` — potem wystarczy `ia4`.

Poszukiwanie używa tylko spółek głównych i kontrolnych. Grupa **doubleProof** (20 spółek)
jest synchronizowana, ale nigdy nie bierze udziału w szukaniu — służy do ręcznej
weryfikacji strategii (instrukcja, sekcja 6a).

## Weryfikacja na doubleProof

`python -m ia4.lab` sam przelicza strategie aktywne na 20 spółkach doubleProof (przy starcie
i co 30 min, gdy zmieniły się strategie albo dane) i zapisuje `research/doubleproof.json`.
Ręcznie, bez szukania: `python -m ia4.lab.verify`. Wynik w arkuszu STRATEGIE DOUBLEPROOF.

Jednorazowo (wyniki zapisane raz, nowe tylko z `--force`):
- `python -m ia4.lab.backtest_dp` — backtest strategii aktywnych na doubleProof → arkusz BACKTEST DOUBLEPROOF,
- `python -m ia4.lab.portfolio` — backtest portfela (wirtualny inwestor na historii) → arkusz BACKTEST PORTFELA i pierwszeństwo strategii w wirtualnym inwestorze (instrukcja, sekcja 6b).

## Test One-Day (instrukcja, sekcja 6c)

```bash
python -m ia4.oneday --selftest   # dane syntetyczne — musi być „WYNIK: OK”
python -m ia4.oneday              # synchronizacja (gdy nie działa `ia4 start`), 100 strategii × 75 instrumentów
                                  # → ~/Desktop/IA4/ONE-DAY-STRATEGY.xlsx (poza gitem)
python -m ia4.oneday --no-sync    # tylko kopia lokalna
python -m ia4.oneday --portfolio OD-080 OD-034 --capital 10000   # arkusze PORTFEL (domyślnie OD-080, 10 000 $)
```

## Poszukiwanie stabilnych strategii One-Day (instrukcja, sekcja 6d)

```bash
python -m ia4.odsearch --selftest   # „WYNIK: OK”
python -m ia4.odsearch              # kierunkowe (28 080) i neutralne (600), spread 0,3%/transakcję, 20 okresów, ≤ 3 stratne, doubleProof, placebo
                                    # → ~/Desktop/IA4/ONE-DAY-SEARCH.xlsx (poza gitem)
python -m ia4.daily                 # kopia lokalna bazy świec dobowych (sekcja 4d) → data/daily/
python -m ia4.odsearch --source daily   # to samo od 2000 r. → ONE-DAY-SEARCH-DAILY.xlsx
python -m ia4.odport --selftest     # portfel strategii walk-forward — „WYNIK: OK”
python -m ia4.odport                # ok. 450 tys. reguł, wybór co rok, portfel, doubleProof, placebo → ONE-DAY-PORTFEL.xlsx
python -m ia4.odbreak --selftest    # siła ruchu po konsolidacji — „WYNIK: OK”
python -m ia4.odbreak               # analiza wybić + strategie long + short naraz → ONE-DAY-WYBICIA.xlsx
node tests/daily.js                 # test Daily.gs (Apps Script) w Node — „WYNIK: OK”
```

Spread: **0,3% wartości pozycji raz na transakcję** (wejście + wyjście razem) — domyślnie wszędzie, bez `--cost`
(decyzja człowieka z 16.10.2026).

## Badania wielodniowe (instrukcja, sekcja 7a)

Pozycja może trwać dłużej niż jedną sesję. Wspólny silnik: `ia4/swing.py` (baza dobowa od 2000 r., SL / TP
pesymistycznie, spread 0,3% raz, portfel 10 000 $ z dźwignią, depozyt 10% stanu na pozycję).

```bash
python -m ia4.swtrend --selftest    # „WYNIK: OK”
python -m ia4.swtrend               # 49 920 strategii jednokierunkowych z SL i TP (wybicia, trend, konwergencja),
                                    # 20 okresów, doubleProof, placebo — ok. 6 min → ~/Desktop/IA4/SWING-TREND.xlsx
python -m ia4.swrsi --selftest      # „WYNIK: OK”
python -m ia4.swrsi                 # RSI(3) < 22, EMA100 rośnie, close ≥ 1% pod VWAP10, wyjście RSI(3) > 55:
                                    # portfel QQQ (1:1 i 1:5) i wszystkie spółki → ~/Desktop/IA4/SWING-RSI3.xlsx
python -m ia4.swserie --selftest    # „WYNIK: OK”
python -m ia4.swserie               # mapa: wejście po N świecach spadkowych / wzrostowych, 1/2/3 sesje,
                                    # long i short, 1:5 → ~/Desktop/IA4/SWING-SERIE.xlsx
python -m ia4.swportfel --selftest  # „WYNIK: OK”
python -m ia4.swportfel             # portfel: long po 7 świecach spadkowych, 3 sesje, 1:5, 73 spółki — wykres kapitału,
                                    # obsunięcia, lista serii → ~/Desktop/IA4/SWING-PORTFEL-7.xlsx (--n 6 --hold 2 — inna komórka)
python -m ia4.swportfel --propozycja   # ≥ 5 spadków, spadek ≥ 10%, słaby rynek, 5 sesji, max 5 pozycji, 1:5
                                    # → SWING-PORTFEL-PROPOZYCJA.xlsx (+ arkusz ANALIZA); własne: --min-n --min-drop --rynek --max-poz
```

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

## AI Investor — `ia4 start` (instrukcja, sekcja 8, Etap 6)

Nadzorca utrzymuje kopię lokalną akcji i FX na bieżąco z Firestore, liczy w sobie prognozę FX (zamiast osobnego
`python -m ia4.fx.live`) i publikuje stan na branch `ai-live` → strona IA4, zakładka AI. Od AI-2 (1.34) po każdej
świecy akcji i co godzinę na FX rundę robi **Agent-Investor**: portfel 100 000 $ (papier), decyzje modelu z notatką,
SL i TP → branch `ai`, `~/Desktop/IA4/AI-INVESTOR.xlsx`, zakładka AI. Od 1.41 dyspozytor uruchamia agentów po kolei
(jeden naraz, bez przerwy): Inwestor (tryb nauki) po świecy, Krytyk co kilka rund, Badacz (hipotezy liczone na historii)
w pozostałym czasie; każde zadanie widać w panelu „praca agentów” na stronie i w `ai/runs.jsonl`.

Raz: Ollama z modelem (`ollama pull qwen2.5:14b`), `pip install -r requirements.txt` (openpyxl) i funkcja w
`~/.zshrc` (zastępuje dawny alias `ia4`; zapis `function ia4 { … }`, bo zsh rozwija alias przed `ia4() { … }`):

```bash
unalias ia4 2>/dev/null; sed -i '' '/^alias ia4=/d' ~/.zshrc
function ia4 { cd ~/Desktop/IA4/ia4-research && source .venv/bin/activate && if [ "$1" = start ]; then shift; python -m ia4.ai "$@"; else python -m ia4.lab --workers 4 "$@"; fi; }
```

Potem `source ~/.zshrc` (albo nowe okno terminala) i:

```bash
python -m ia4.ai.selftest   # test na danych syntetycznych (ok. 1 min) — „WYNIK: OK”
python -m ia4.ai.replay     # test silnika portfela na 20 ostatnich sesjach kopii lokalnej (bez modelu, nic nie zapisuje)
ia4 start                   # albo dwuklik IA4-start.command (można go skopiować na Pulpit); Ctrl+C kończy
ia4 start --no-llm-check    # bez sprawdzania Ollamy (rundy bez modelu = „brak decyzji”)
python -m ia4.ai.restore    # hub od nowa z brancha `ai` (gdy zginął data/ai/hub.sqlite; przy pustym hubie start robi to sam)
ia4 start --no-push         # test bez GitHub
```

Przy działającym `ia4 start` nie uruchamiaj osobno `ia4.fx.live`, `ia4.fx.research` ani `ia4.lab` — odmówią
startu (pamięć 16 GB zajmie model językowy). Noc: laptop otwarty i na zasilaczu. Hub (pamięć agentów, wszystkie
decyzje, pełne prompty modelu): `data/ai/hub.sqlite`, poza gitem; klony branchy `ai-repo/`, `ai-live-repo/`.
Ustawienia (limity, model, ścieżka Excela) nadpisuje `ai/config.json` na branchu `ai` — klucze: `ia4/ai/config.py`.

## Prognoza FX 1h — 10 par walutowych + BTC/USD (instrukcja, sekcje 4b i 4c)

```bash
source .venv/bin/activate
python -m ia4.fx.selftest            # test modułu na danych syntetycznych (ok. 3 min) — musi być „WYNIK: OK”
python -m ia4.fx.sync                # kopia świec 1h (11 instrumentów) → data/fx1h/{ID}.parquet (przyrostowo)
python -m ia4.fx.catalog             # kalibracja PRÓBNA 1000 okoliczności → data/fx1h/catalog-preview.csv
python -m ia4.fx.catalog --commit    # kalibracja WŁAŚCIWA → fx/conditions.json na branchu fx — tylko raz
python -m ia4.fx.research            # przeliczenie (ok. 3 min): ratingi, sprawdzian rozkładu, model na żywo → branch fx
python -m ia4.fx.live                # prognoza na żywo co 30 s → branch fx-live → https://miszyszka.github.io/IA4/
```

Podgląd ostatniego przeliczenia: `data/fx1h/ratings-preview.csv`. Wystąpienia jednej okoliczności
(czas + 48 przyszłych zmian w jednostkach ATR100): `from ia4.fx.research import load_occurrences; load_occurrences("FX-0001", "EURUSD")`.
Stara kopia EURUSD 5 min (`data/fx/`) jest usuwana przy pierwszej synchronizacji 1.27.

Po `--commit` katalog okoliczności jest nienaruszalny (zasada 14): kolejne wywołanie odmawia.
Klony branchy: `fx-repo/` i `fx-live-repo/` (poza gitem). Dashboard (GitHub Pages z brancha `fx`) pokazuje, czy Mac jest połączony.
