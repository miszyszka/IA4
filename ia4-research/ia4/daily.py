"""
IA 4 — kopia lokalna bazy świec dobowych (instrukcja, sekcja 4d).
Wersja projektu: 1.50 (2026-10-20) — musi zgadzać się z IA4_INSTRUKCJA.md

Firestore daily/{SYMBOL}/years/{RRRR} (tablice d, o, h, l, c, v; pisze Daily.gs) → data/daily/{SYMBOL}.parquet
  kolumny: date (RRRR-MM-DD), o, h, l, c, v — posortowane po dacie.

Lista instrumentów i stan historii: system/daily (jeden odczyt). Przyrostowo: tylko dokumenty lat
z `updatedAt` nowszym niż poprzednia synchronizacja (minus 30 min) — zwykle 1 odczyt na instrument
(bieżący rok). Dokument roku jest w całości źródłem prawdy dla swojego roku: zastępuje lokalnie cały rok.
Pierwszy raz: wszystkie lata (ok. 1 odczyt na rok instrumentu, łącznie kilka tysięcy).
Python nigdy nie pisze do Firestore (zasada 1).

  python -m ia4.daily            # przyrostowo
  python -m ia4.daily --full     # od nowa
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import config

DAILY_DIR = config.CACHE_DIR / "daily"
MANIFEST = DAILY_DIR / "_manifest.json"
COLLECTION = "daily"
STATUS_DOC = "system/daily"
UPDATED_MARGIN_MIN = 30
COLUMNS = ["date", "o", "h", "l", "c", "v"]


def parquet_path(sym: str):
    return DAILY_DIR / f"{config.fs_id(sym)}.parquet"


def load(sym: str) -> pd.DataFrame:
    p = parquet_path(sym)
    if not p.exists():
        raise FileNotFoundError(f"Brak kopii świec dobowych {p} — uruchom: python -m ia4.daily")
    return pd.read_parquet(p)


def local_symbols() -> list[str]:
    if not MANIFEST.exists():
        return []
    return [s for s in json.loads(MANIFEST.read_text()) if parquet_path(s).exists()]


def parse_year(d: dict) -> pd.DataFrame:
    """Dokument roku → wiersze; tablice różnej długości → wspólny prefiks (lepiej stracić dzień niż przesunąć ceny)."""
    cols = [d.get(k) or [] for k in ("d", "o", "h", "l", "c", "v")]
    n = min(len(x) for x in cols[:5])
    v = cols[5] + [0] * max(0, n - len(cols[5]))
    return pd.DataFrame({"date": cols[0][:n], "o": cols[1][:n], "h": cols[2][:n], "l": cols[3][:n],
                         "c": cols[4][:n], "v": [int(x or 0) for x in v[:n]]}, columns=COLUMNS)


def merge_years(old: pd.DataFrame | None, years: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Lata z Firestore zastępują w całości te same lata kopii lokalnej."""
    parts = []
    if old is not None and not old.empty:
        keep = ~old["date"].str[:4].astype(int).isin(list(years))
        parts.append(old[keep])
    parts += [df for df in years.values() if not df.empty]
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.concat(parts, ignore_index=True)
    return df.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


def status() -> dict:
    doc = config.client().document(STATUS_DOC).get()
    if not doc.exists:
        raise RuntimeError("Brak system/daily w Firestore — historia świec dobowych jeszcze się nie zaczęła "
                           "(Apps Script 1.38, wolne uruchomienia poza sesją albo menu „📅 porcja historii”).")
    d = doc.to_dict()
    syms = d.get("symbols") or []
    hist = d.get("hist") or []
    return {"symbols": syms, "hist": {s: bool(hist[i]) if i < len(hist) else False for i, s in enumerate(syms)},
            "first": dict(zip(syms, d.get("first") or [])), "last": dict(zip(syms, d.get("last") or [])),
            "updated": d.get("updated", ""), "version": d.get("version", "")}


def sync(full: bool = False, quiet: bool = False) -> dict:
    from .sync import _where
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    st = status()
    man = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    ready = [s for s in st["symbols"] if st["hist"].get(s)]
    if not quiet:
        print(f"IA 4 — świece dobowe: historia w Firestore {len(ready)}/{len(st['symbols'])}, "
              f"ostatnia aktualizacja {st['updated'] or '—'}")
    reads = 1
    for sym in ready:
        started = datetime.now(timezone.utc)
        e = man.get(sym, {})
        since = None
        if not full and e.get("synced_at") and parquet_path(sym).exists():
            since = datetime.fromisoformat(e["synced_at"]) - timedelta(minutes=UPDATED_MARGIN_MIN)
        ref = config.client().collection(f"{COLLECTION}/{config.fs_id(sym)}/years")
        docs = list(ref.stream() if since is None else _where(ref, "updatedAt", ">", since).stream())
        reads += max(1, len(docs))
        if not docs and since is not None:
            e["synced_at"] = started.isoformat()
            man[sym] = e
            continue
        years = {int(d.id): parse_year(d.to_dict()) for d in docs}
        old = None if since is None or not parquet_path(sym).exists() else pd.read_parquet(parquet_path(sym))
        df = merge_years(old, years)
        df.to_parquet(parquet_path(sym), index=False)
        man[sym] = {"synced_at": started.isoformat(), "first": str(df["date"].iloc[0]) if len(df) else "",
                    "last": str(df["date"].iloc[-1]) if len(df) else "", "n": int(len(df)), "years_read": len(docs)}
        if not quiet and docs:
            print(f"  {sym}: {len(docs)} lat → {len(df)} świec ({man[sym]['first']} – {man[sym]['last']})")
        MANIFEST.write_text(json.dumps(man, indent=1))
    MANIFEST.write_text(json.dumps(man, indent=1))
    if not quiet:
        print(f"Gotowe: {len(ready)} instrumentów w data/daily/, odczytów Firestore ok. {reads}.")
    return {"ready": len(ready), "total": len(st["symbols"]), "reads": reads}


def main() -> None:
    ap = argparse.ArgumentParser(description="Świece dobowe: Firestore daily/ → data/daily/ (instrukcja 4d)")
    ap.add_argument("--full", action="store_true", help="pobierz wszystko od nowa")
    a = ap.parse_args()
    sync(full=a.full)


if __name__ == "__main__":
    main()
