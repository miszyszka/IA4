"""
IA 4 — synchronizacja Firestore → lokalny parquet.
Wersja projektu: 0.25 (2026-09-26) — musi zgadzać się z IA4_INSTRUKCJA.md

Po co w ogóle kopia lokalna: backtest w Etapie 2 czyta te same świece dziesiątki
tysięcy razy (24 000 strategii). Czytanie ich za każdym razem z Firestore
przekroczyłoby dzienny darmowy limit odczytów po kilku minutach pracy i byłoby
setki razy wolniejsze niż plik na dysku. Firestore zostaje jedynym źródłem
prawdy (sekcja 3 instrukcji) — parquet to tylko jego pamięć podręczna.

JAK TO DZIAŁA: pierwsze uruchomienie ściąga CAŁOŚĆ. Każde kolejne pyta tylko
o ostatnie RECHECK_DAYS (14) dni — nie o całą historię. Manifest pamięta
ostatnią datę każdego instrumentu, więc codzienna synchronizacja to kilkanaście
do kilkudziesięciu świec na instrument zamiast 30 tysięcy.

Dlaczego 14 dni, a nie „tylko nowsze niż ostatnia": Apps Script dopisuje świece
także WSTECZ (łatanie luk, dopisywanie wolumenu D12). Zapytanie „tylko nowsze"
nigdy by tego nie zobaczyło i zostawiłoby w kopii lokalnej dziurę nie do
zamknięcia. Pełne odświeżenie: python -m ia4.sync --full

DWA FORMATY W FIRESTORE (sekcja 4 instrukcji):
  stocks/{SYMBOL}/candles/{data}_{nr}   spółki główne — dokument na świecę
  proof/{SYMBOL}/sessions/{data}        kontrolne    — sesja w jednym dokumencie
  context/{ID}/sessions/{data}          tło rynku    — jak wyżej, ID bez „^"

Oba sprowadzamy do jednej, płaskiej tabeli:
  symbol, date, slot (1–7), o, h, l, c, v (wolumen, decyzja D12)

Uruchomienie:
  python -m ia4.sync             # przyrostowo, wszystkie instrumenty
  python -m ia4.sync --full      # od nowa, ignorując manifest
  python -m ia4.sync AAPL TSLA   # wybrane instrumenty
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from . import config

COLUMNS = ["symbol", "date", "slot", "o", "h", "l", "c", "v"]
GROUP_COLLECTION = {"main": "stocks", "proof": "proof", "context": "context"}

# Ile ostatnich dni sprawdzamy ponownie przy każdej synchronizacji.
#
# Pytanie wyłącznie o sesje NOWSZE niż ostatnia posiadana (date > last_date)
# jest najtańsze, ale ma dziurę: automat w Apps Script dopisuje świece
# WSTECZ — łatanie luk uzupełnia stare sesje, a dopisywanie wolumenu (D12)
# nadpisuje świece sprzed miesięcy. Takie uzupełnienie ma datę starszą niż
# last_date, więc zapytanie „tylko nowsze" nigdy by go nie zobaczyło i kopia
# lokalna zostałaby z dziurą, której nic już nie zamknie.
#
# 14 dni to to samo okno, co nocny audyt w Apps Script (PROJECT.NIGHTLY_DAYS)
# — czyli dokładnie zakres, w którym dane jeszcze się ruszają. Starsze sesje
# są już ustabilizowane; gdyby trzeba było je odświeżyć (np. po wykryciu
# splitu), służy do tego „python -m ia4.sync --full".
RECHECK_DAYS = 14


def _since_for(last_date: str | None) -> str | None:
    """Od której daty (wyłącznie) pytać Firestore: cofka o RECHECK_DAYS."""
    if not last_date:
        return None
    from datetime import date, timedelta

    try:
        d = date.fromisoformat(last_date) - timedelta(days=RECHECK_DAYS)
    except ValueError:      # nietypowy zapis daty w manifeście — bezpieczniej pobrać całość
        return None
    return d.isoformat()


# ---------------------------------------------------------------------------
#  Manifest — co już mamy lokalnie
# ---------------------------------------------------------------------------
def load_manifest() -> dict:
    if config.MANIFEST_PATH.exists():
        return json.loads(config.MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}


def save_manifest(m: dict) -> None:
    config.MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.MANIFEST_PATH.write_text(json.dumps(m, indent=2, sort_keys=True), encoding="utf-8")


def parquet_path(symbol: str) -> Path:
    return config.CACHE_DIR / f"{config.fs_id(symbol)}.parquet"


# ---------------------------------------------------------------------------
#  Odczyt z Firestore
# ---------------------------------------------------------------------------
def _fetch_sessions(symbol: str, since: str | None) -> pd.DataFrame:
    """Format sesyjny: jeden dokument = jedna sesja z tablicami slots/o/h/l/c."""
    coll = GROUP_COLLECTION[config.group_of(symbol)]
    ref = config.client().collection(f"{coll}/{config.fs_id(symbol)}/sessions")
    query = ref.order_by("date")
    if since:
        query = query.where("date", ">", since)

    rows = []
    for doc in query.stream():
        d = doc.to_dict()
        slots = d.get("slots") or []
        o, h, l, c = d.get("o") or [], d.get("h") or [], d.get("l") or [], d.get("c") or []
        # Wolumen doszedł w wersji 0.8 — starsze sesje go nie mają (D12).
        vol = d.get("v") or []
        # Tablice są równoległe (sekcja 4 instrukcji). Gdyby któraś była krótsza,
        # bierzemy tylko wspólny prefiks — lepiej stracić świecę niż wpisać
        # do badań cenę z innej godziny.
        n = min(len(slots), len(o), len(h), len(l), len(c))
        if n < len(slots):
            print(f"  ! {symbol} {d.get('date')}: tablice różnej długości, biorę {n} z {len(slots)}")
        for i in range(n):
            rows.append((symbol, d.get("date"), int(slots[i]), o[i], h[i], l[i], c[i],
                         int(vol[i]) if i < len(vol) and vol[i] is not None else 0))
    return pd.DataFrame(rows, columns=COLUMNS)


def _fetch_candles(symbol: str, since: str | None) -> pd.DataFrame:
    """Format świecowy (spółki główne): jeden dokument = jedna świeca."""
    ref = config.client().collection(f"stocks/{config.fs_id(symbol)}/candles")
    query = ref.order_by("date")
    if since:
        query = query.where("date", ">", since)

    rows = []
    for doc in query.stream():
        d = doc.to_dict()
        rows.append((symbol, d.get("date"), int(d.get("slot")),
                     d.get("open"), d.get("high"), d.get("low"), d.get("close"),
                     int(d.get("volume") or 0)))
    return pd.DataFrame(rows, columns=COLUMNS)


def fetch(symbol: str, since: str | None) -> pd.DataFrame:
    if config.group_of(symbol) == "main":
        return _fetch_candles(symbol, since)
    return _fetch_sessions(symbol, since)


# ---------------------------------------------------------------------------
#  Synchronizacja
# ---------------------------------------------------------------------------
def sync_symbol(symbol: str, manifest: dict, full: bool = False) -> dict:
    path = parquet_path(symbol)
    last_date = None if full else manifest.get(symbol, {}).get("last_date")
    since = _since_for(last_date)

    new = fetch(symbol, since)

    had = 0
    if path.exists() and not full:
        old = pd.read_parquet(path)
        had = len(old)
        # Świeże wiersze idą PO starych, a niżej drop_duplicates(keep="last")
        # zostawia właśnie je — dzięki temu ponowne pobranie ostatnich 14 dni
        # nadpisuje to, co mieliśmy (np. świecę, która dostała wolumen), zamiast
        # tworzyć duplikat.
        df = pd.concat([old, new], ignore_index=True) if not new.empty else old
    else:
        df = new

    if df.empty:
        print(f"  {symbol}: brak danych")
        return {"sessions": 0, "candles": 0, "first": "", "last": "", "added": 0}

    # Świeca jest jednoznacznie opisana przez (date, slot); duplikaty mogą
    # powstać, gdy ta sama sesja przyszła i z historii, i z automatu bieżącego.
    before = len(df)
    df = df.drop_duplicates(subset=["date", "slot"], keep="last")
    df = df.sort_values(["date", "slot"]).reset_index(drop=True)
    dups = before - len(df)

    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)

    stats = {
        "sessions": int(df["date"].nunique()),
        "candles": int(len(df)),
        "first": str(df["date"].iloc[0]),
        "last": str(df["date"].iloc[-1]),
        # Realny przyrost, a nie liczba pobranych wierszy: przy oknie 14 dni
        # większość pobranych świec to te, które już mieliśmy.
        "added": int(len(df)) - had,
        "refreshed": int(len(new)) - (int(len(df)) - had),
    }
    manifest[symbol] = {"last_date": stats["last"], **stats}
    extra = f", duplikatów usuniętych: {dups}" if dups else ""
    seen = f", sprawdzono ponownie {stats['refreshed']}" if stats["refreshed"] > 0 else ""
    print(f"  {symbol}: +{stats['added']} świec → {stats['candles']} w {stats['sessions']} sesjach "
          f"({stats['first']} – {stats['last']}){seen}{extra}")
    return stats


def sync(symbols: list[str] | None = None, full: bool = False) -> dict:
    v = config.vault()
    print(f"IA 4 — synchronizacja danych (instrukcja v{v.instruction_version}, etap {v.stage})")
    print(f"Okres badawczy: do {v.research_end} · skarbiec: {v.vault_start} – {v.vault_end} "
          f"({'OTWARTY' if v.vault_opened else 'zamknięty'})")
    print()

    symbols = symbols or config.all_symbols()
    manifest = load_manifest()
    for s in symbols:
        try:
            sync_symbol(s, manifest, full=full)
        except Exception as e:  # jeden instrument nie może zatrzymać reszty
            print(f"  ! {s}: {type(e).__name__}: {e}", file=sys.stderr)
        save_manifest(manifest)  # zapis po każdym — przerwanie nie gubi postępu
    print(f"\nGotowe. Manifest: {config.MANIFEST_PATH}")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Synchronizacja Firestore → parquet")
    ap.add_argument("symbols", nargs="*", help="instrumenty (domyślnie: wszystkie)")
    ap.add_argument("--full", action="store_true", help="pobierz od nowa, ignorując manifest")
    a = ap.parse_args()
    sync(a.symbols or None, full=a.full)


if __name__ == "__main__":
    main()
