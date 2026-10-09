"""
IA 4 — synchronizacja Firestore → lokalna kopia (parquet).
Wersja projektu: 1.20 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

Firestore jest jedynym źródłem prawdy. Pliki w data/ to kopia robocza na Macu —
można je skasować i odtworzyć.

JAK TO DZIAŁA: pierwsze uruchomienie ściąga CAŁOŚĆ. Każde kolejne zadaje dwa
tanie pytania na instrument i skleja odpowiedzi:
  1. sesje z ostatnich RECHECK_DAYS dni — nowe świece,
  2. dokumenty z `updatedAt` późniejszym niż poprzednia synchronizacja — wszystko,
     co Apps Script przepisał (np. nocne odświeżenie ostatnich 5 sesji).
Manifest (data/_manifest.json) pamięta datę ostatniej synchronizacji instrumentu.

KOSZT: pełne pobranie wszystkich instrumentów (75) to ok. 48 000 odczytów Firestore
(prawie cały dzienny darmowy limit 50 000) — najwyżej raz dziennie. Synchronizacja
przyrostowa kosztuje kilkaset odczytów.

DWA FORMATY W FIRESTORE (instrukcja, sekcja 4) sprowadzamy do jednej tabeli
na instrument:  symbol, date, slot (1–7), o, h, l, c, v

Uruchomienie (w folderze ia4-research/):
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
GROUP_COLLECTION = {"main": "stocks", "proof": "proof", "context": "context", "doubleProof": "doubleProof"}

# Ile ostatnich dni pobieramy ponownie przy każdej synchronizacji (nowe świece
# i ewentualne poprawki dnia bieżącego). Przepisania starsze łapie pytanie 2.
RECHECK_DAYS = 14

# Zapas na rozjazd zegarów Apps Script / Mac przy pytaniu o updatedAt.
UPDATED_MARGIN_MIN = 30


def _since_for(last_date: str | None) -> str | None:
    """Od której daty (wyłącznie) pytać Firestore: cofka o RECHECK_DAYS."""
    if not last_date:
        return None
    from datetime import date, timedelta

    try:
        return (date.fromisoformat(last_date) - timedelta(days=RECHECK_DAYS)).isoformat()
    except ValueError:
        return None


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


def load(symbol: str) -> pd.DataFrame:
    """Świece jednego instrumentu z kopii lokalnej, posortowane po (date, slot)."""
    return pd.read_parquet(parquet_path(symbol))


# ---------------------------------------------------------------------------
#  Odczyt z Firestore
# ---------------------------------------------------------------------------
def _where(query, field: str, op: str, value):
    """`where` w składni nowszego klienta Firestore, ze zgodnością wstecz."""
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter
        return query.where(filter=FieldFilter(field, op, value))
    except ImportError:
        return query.where(field, op, value)


def _stream(ref, since: str | None, updated_since):
    """Bez `since` — cała kolekcja. Z `since` — sesje nowsze niż `since`
    ORAZ dokumenty zmienione po `updated_since` (bez order_by: nierówność na
    updatedAt z sortowaniem po dacie wymagałaby indeksu złożonego)."""
    if not since:
        yield from ref.order_by("date").stream()
        return
    seen = set()
    for doc in _where(ref, "date", ">", since).stream():
        seen.add(doc.id)
        yield doc
    if updated_since is not None:
        for doc in _where(ref, "updatedAt", ">", updated_since).stream():
            if doc.id not in seen:
                yield doc


def _fetch_sessions(symbol: str, since: str | None, updated_since=None) -> pd.DataFrame:
    """Format sesyjny: jeden dokument = jedna sesja z równoległymi tablicami."""
    coll = GROUP_COLLECTION[config.group_of(symbol)]
    ref = config.client().collection(f"{coll}/{config.fs_id(symbol)}/sessions")
    rows = []
    for doc in _stream(ref, since, updated_since):
        d = doc.to_dict()
        slots = d.get("slots") or []
        o, h, l, c = d.get("o") or [], d.get("h") or [], d.get("l") or [], d.get("c") or []
        vol = d.get("v") or []
        # Gdyby któraś tablica była krótsza, bierzemy wspólny prefiks —
        # lepiej stracić świecę niż przypisać cenę z innej godziny.
        n = min(len(slots), len(o), len(h), len(l), len(c))
        if n < len(slots):
            print(f"  ! {symbol} {d.get('date')}: tablice różnej długości, biorę {n} z {len(slots)}")
        for i in range(n):
            rows.append((symbol, d.get("date"), int(slots[i]), o[i], h[i], l[i], c[i],
                         int(vol[i]) if i < len(vol) and vol[i] is not None else 0))
    return pd.DataFrame(rows, columns=COLUMNS)


def _fetch_candles(symbol: str, since: str | None, updated_since=None) -> pd.DataFrame:
    """Format świecowy (spółki główne): jeden dokument = jedna świeca."""
    ref = config.client().collection(f"stocks/{config.fs_id(symbol)}/candles")
    rows = []
    for doc in _stream(ref, since, updated_since):
        d = doc.to_dict()
        rows.append((symbol, d.get("date"), int(d.get("slot")),
                     d.get("open"), d.get("high"), d.get("low"), d.get("close"),
                     int(d.get("volume") or 0)))
    return pd.DataFrame(rows, columns=COLUMNS)


def fetch(symbol: str, since: str | None, updated_since=None) -> pd.DataFrame:
    if config.group_of(symbol) == "main":
        return _fetch_candles(symbol, since, updated_since)
    return _fetch_sessions(symbol, since, updated_since)


def _updated_since(entry: dict):
    """Chwila poprzedniej synchronizacji minus zapas; None = brak (wymusza całość)."""
    from datetime import datetime, timedelta

    raw = entry.get("synced_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw) - timedelta(minutes=UPDATED_MARGIN_MIN)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
#  Synchronizacja
# ---------------------------------------------------------------------------
def sync_symbol(symbol: str, manifest: dict, full: bool = False) -> dict:
    from datetime import datetime, timezone

    path = parquet_path(symbol)
    entry = manifest.get(symbol, {})
    updated_since = None if full else _updated_since(entry)
    if updated_since is None or not path.exists():
        full = True
    since = None if full else _since_for(entry.get("last_date"))
    started = datetime.now(timezone.utc)      # PRZED pobraniem — nic nie umknie między pytaniami

    new = fetch(symbol, since, updated_since)

    had = 0
    if path.exists() and not full:
        old = pd.read_parquet(path)
        had = len(old)
        # Świeże wiersze idą PO starych, drop_duplicates(keep="last") zostawia je.
        df = pd.concat([old, new], ignore_index=True) if not new.empty else old
    else:
        df = new

    if df.empty:
        print(f"  {symbol}: brak danych")
        return {"candles": 0, "first": "", "last": "", "added": 0}

    df = (df.drop_duplicates(subset=["date", "slot"], keep="last")
            .sort_values(["date", "slot"]).reset_index(drop=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)

    stats = {
        "sessions": int(df["date"].nunique()),
        "candles": int(len(df)),
        "first": str(df["date"].iloc[0]),
        "last": str(df["date"].iloc[-1]),
        "added": int(len(df)) - had,
    }
    manifest[symbol] = {"last_date": stats["last"], "synced_at": started.isoformat(),
                        "group": config.group_of(symbol), **stats}
    print(f"  {symbol}: +{stats['added']} świec → {stats['candles']} w {stats['sessions']} sesjach "
          f"({stats['first']} – {stats['last']})")
    return stats


def sync(symbols: list[str] | None = None, full: bool = False) -> dict:
    print("IA 4 — synchronizacja Firestore → kopia lokalna\n")
    symbols = symbols or config.all_symbols()
    manifest = load_manifest()

    fulls = [s for s in symbols
             if full or not manifest.get(s, {}).get("synced_at") or not parquet_path(s).exists()]
    if fulls:
        est = sum(3600 if config.group_of(s) == "main" else 520 for s in fulls)
        print(f"Pełne pobranie dla {len(fulls)} instrumentów: ok. {est:,} odczytów Firestore "
              f"(dzienny limit 50 000 — nie powtarzaj tego tego samego dnia).\n".replace(",", " "))
    for s in symbols:
        try:
            sync_symbol(s, manifest, full=full)
        except Exception as e:  # jeden instrument nie zatrzymuje reszty
            print(f"  ! {s}: {type(e).__name__}: {e}", file=sys.stderr)
        save_manifest(manifest)  # zapis po każdym — przerwanie nie gubi postępu
    print(f"\nGotowe. Manifest: {config.MANIFEST_PATH}")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Synchronizacja Firestore → kopia lokalna (parquet)")
    ap.add_argument("symbols", nargs="*", help="instrumenty (domyślnie: wszystkie)")
    ap.add_argument("--full", action="store_true", help="pobierz od nowa, ignorując manifest")
    a = ap.parse_args()
    sync(a.symbols or None, full=a.full)


if __name__ == "__main__":
    main()
