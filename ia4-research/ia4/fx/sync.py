"""
IA 4 — kopia lokalna świec EURUSD 5 min (instrukcja, sekcja 4c.1).
Wersja projektu: 1.23 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

Firestore fx/EURUSD/days/{RRRR-MM-DD} (format: sekcja 4b) → data/fx/EURUSD.parquet
  kolumny: time (początek świecy, sekundy UTC), o, h, l, c, filled (świeca z fillT)

Przyrostowo: tylko dokumenty dni z `updatedAt` nowszym niż poprzednia synchronizacja
(minus zapas 30 min) — zwykle 1–3 odczyty. Pierwszy raz: wszystkie dni (ok. 1 odczyt
na dzień bazy). Dokument dnia jest w całości źródłem prawdy dla swojego dnia: jego
świece zastępują wszystkie lokalne świece tego dnia.

  python -m ia4.fx.sync          # przyrostowo
  python -m ia4.fx.sync --full   # od nowa
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .. import config

FX_DIR = config.CACHE_DIR / "fx"
PARQUET = FX_DIR / "EURUSD.parquet"
MANIFEST = FX_DIR / "_manifest.json"
COLLECTION = "fx/EURUSD/days"
UPDATED_MARGIN_MIN = 30
COLUMNS = ["time", "o", "h", "l", "c", "filled"]


def load() -> pd.DataFrame:
    """Świece EURUSD z kopii lokalnej, posortowane po czasie."""
    if not PARQUET.exists():
        raise FileNotFoundError(f"Brak kopii lokalnej {PARQUET} — uruchom: python -m ia4.fx.sync")
    return pd.read_parquet(PARQUET)


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}


def _day_start(date: str) -> int:
    return int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp())


def doc_to_frame(d: dict) -> pd.DataFrame:
    """Dokument dnia (słownik pól) → tabela świec. Tablice równoległe; przy różnej
    długości bierzemy wspólny prefiks (lepiej stracić świecę niż pomylić czas)."""
    date = d.get("date")
    t0 = _day_start(date)
    tt, o, h, l, c = (list(d.get(k) or []) for k in ("t", "o", "h", "l", "c"))
    n = min(len(tt), len(o), len(h), len(l), len(c))
    if n < len(tt):
        print(f"  ! {date}: tablice różnej długości, biorę {n} z {len(tt)}")
    fill = {int(m) for m in (d.get("fillT") or [])}
    rows = [(t0 + int(tt[i]) * 60, float(o[i]), float(h[i]), float(l[i]), float(c[i]), int(tt[i]) in fill)
            for i in range(n)]
    return pd.DataFrame(rows, columns=COLUMNS)


def merge_days(old: pd.DataFrame | None, days: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Świece z pobranych dni zastępują lokalne świece tych samych dni UTC."""
    parts = []
    if old is not None and len(old):
        day_of = pd.to_datetime(old["time"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
        parts.append(old[~day_of.isin(set(days))])
    parts += [df for df in days.values() if len(df)]
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.concat(parts, ignore_index=True)
    df = df.drop_duplicates(subset=["time"], keep="last").sort_values("time").reset_index(drop=True)
    df["time"] = df["time"].astype(np.int64)
    df["filled"] = df["filled"].astype(bool)
    return df


def sync(full: bool = False, quiet: bool = False) -> pd.DataFrame:
    """Synchronizacja przyrostowa. Zwraca całą kopię lokalną."""
    from ..sync import _where

    log = (lambda *a: None) if quiet else print
    m = _manifest()
    started = datetime.now(timezone.utc)          # PRZED pobraniem — nic nie umknie
    old = pd.read_parquet(PARQUET) if (PARQUET.exists() and not full) else None
    ref = config.client().collection(COLLECTION)
    since = None
    if old is not None and m.get("synced_at"):
        since = datetime.fromisoformat(m["synced_at"]) - timedelta(minutes=UPDATED_MARGIN_MIN)
    stream = ref.stream() if since is None else _where(ref, "updatedAt", ">", since).stream()
    days, reads = {}, 0
    for doc in stream:
        reads += 1
        d = doc.to_dict()
        if d.get("date"):
            days[d["date"]] = doc_to_frame(d)
    df = merge_days(old, days)
    FX_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PARQUET, index=False)
    first = datetime.fromtimestamp(int(df["time"].iloc[0]), timezone.utc).isoformat() if len(df) else ""
    last = datetime.fromtimestamp(int(df["time"].iloc[-1]), timezone.utc).isoformat() if len(df) else ""
    m = {"synced_at": started.isoformat(), "candles": int(len(df)), "filled": int(df["filled"].sum()) if len(df) else 0,
         "first": first, "last": last, "days": len(set(pd.to_datetime(df["time"], unit="s", utc=True)
                                                        .dt.strftime("%Y-%m-%d"))) if len(df) else 0}
    MANIFEST.write_text(json.dumps(m, indent=2), encoding="utf-8")
    log(f"EURUSD: {'pełne pobranie' if since is None else 'przyrost'} — {reads} odczytów Firestore, "
        f"zmienione dni: {', '.join(sorted(days)) or 'brak'}; w kopii {m['candles']} świec "
        f"({m['filled']} uśrednionych), {first[:16]} – {last[:16]} UTC")
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description="Firestore fx/EURUSD → data/fx/EURUSD.parquet")
    ap.add_argument("--full", action="store_true", help="pobierz wszystkie dni od nowa")
    sync(full=ap.parse_args().full)


if __name__ == "__main__":
    main()
