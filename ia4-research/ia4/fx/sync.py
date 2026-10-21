"""
IA 4 — kopia lokalna świec FX 1h (instrukcja, sekcja 4c.1).
Wersja projektu: 1.59 (2026-10-21) — musi zgadzać się z IA4_INSTRUKCJA.md

Firestore fx1h/{SYMBOL}/days/{RRRR-MM-DD} (format: sekcja 4b) → data/fx1h/{SYMBOL}.parquet
  kolumny: time (początek świecy, sekundy UTC), o, h, l, c, filled (świeca z fillT)

Przyrostowo: dla każdego instrumentu tylko dokumenty dni z `updatedAt` nowszym niż poprzednia
synchronizacja (minus zapas 30 min) — zwykle 1–3 odczyty na instrument. Pierwszy raz: wszystkie
dni (ok. 1 odczyt na dzień, ok. 7000 dla 11 instrumentów). Dokument dnia jest w całości źródłem
prawdy dla swojego dnia: jego świece zastępują wszystkie lokalne świece tego dnia.
Lista instrumentów: system/fx1h (pisze Fx.gs), bez Firestore — ia4/fx/instruments.py.

  python -m ia4.fx.sync          # przyrostowo
  python -m ia4.fx.sync --full   # od nowa
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .. import config
from . import instruments as fi

FX_DIR = config.CACHE_DIR / "fx1h"
LEGACY_DIR = config.CACHE_DIR / "fx"           # kopia EURUSD 5 min (1.20–1.26) — usuwana
MANIFEST = FX_DIR / "_manifest.json"
COLLECTION = "fx1h"
STATUS_DOC = "system/fx1h"
UPDATED_MARGIN_MIN = 30
COLUMNS = ["time", "o", "h", "l", "c", "filled"]


def parquet_path(sym: str):
    return FX_DIR / f"{sym}.parquet"


def load(sym: str) -> pd.DataFrame:
    """Świece jednego instrumentu z kopii lokalnej, posortowane po czasie."""
    p = parquet_path(sym)
    if not p.exists():
        raise FileNotFoundError(f"Brak kopii lokalnej {p} — uruchom: python -m ia4.fx.sync")
    return pd.read_parquet(p)


def load_all(symbols=None) -> dict[str, pd.DataFrame]:
    out = {}
    for s in symbols or fi.IDS:
        if parquet_path(s).exists():
            out[s] = load(s)
    if not out:
        raise FileNotFoundError(f"Brak kopii lokalnej w {FX_DIR} — uruchom: python -m ia4.fx.sync")
    return out


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
        print(f"  ! {d.get('symbol')} {date}: tablice różnej długości, biorę {n} z {len(tt)}")
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


def symbols(proof: bool = False) -> list[str]:
    """Instrumenty z system/fx1h (Fx.gs); bez dokumentu — lista z instruments.py.
    proof=False — bez grupy fx1h_double_proof (prognoza, badania i agenci AI jej nie widzą; instrukcja 4b)."""
    out = None
    try:
        d = config.client().document(STATUS_DOC).get()
        if d.exists and d.to_dict().get("symbols"):
            out = list(d.to_dict()["symbols"])
    except Exception as e:                                   # bez Firestore — lista zapasowa
        print(f"  ! {STATUS_DOC}: {type(e).__name__}: {e} — lista z instruments.py")
    out = out or list(fi.ALL_IDS)
    return out if proof else [s for s in out if s not in fi.DOUBLE_PROOF]


def remove_legacy(log=print) -> None:
    """Kopia EURUSD 5 min (data/fx/, wersje 1.20–1.26) — baza 5 min usunięta 10.10.2026 (instrukcja 4b)."""
    if LEGACY_DIR.exists():
        files = [p.name for p in LEGACY_DIR.iterdir()]
        shutil.rmtree(LEGACY_DIR)
        log(f"  usunięto starą kopię EURUSD 5 min: data/fx/ ({', '.join(files) or 'pusty'})")


def sync_symbol(sym: str, m: dict, full: bool = False, log=print) -> pd.DataFrame:
    from ..sync import _where
    e = m.get(sym, {})
    started = datetime.now(timezone.utc)                     # PRZED pobraniem — nic nie umknie
    path = parquet_path(sym)
    old = pd.read_parquet(path) if (path.exists() and not full) else None
    ref = config.client().collection(f"{COLLECTION}/{sym}/days")
    since = None
    if old is not None and e.get("synced_at"):
        since = datetime.fromisoformat(e["synced_at"]) - timedelta(minutes=UPDATED_MARGIN_MIN)
    stream = ref.stream() if since is None else _where(ref, "updatedAt", ">", since).stream()
    days, reads = {}, 0
    for doc in stream:
        reads += 1
        d = doc.to_dict()
        if d.get("date"):
            days[d["date"]] = doc_to_frame(d)
    df = merge_days(old, days)
    FX_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    iso = lambda t: datetime.fromtimestamp(int(t), timezone.utc).isoformat()
    m[sym] = {"synced_at": started.isoformat(), "candles": int(len(df)),
              "filled": int(df["filled"].sum()) if len(df) else 0,
              "first": iso(df["time"].iloc[0]) if len(df) else "", "last": iso(df["time"].iloc[-1]) if len(df) else ""}
    log(f"  {sym:7s} {'pełne' if since is None else 'przyrost'}: {reads:4d} odczytów, w kopii {len(df):6d} świec "
        f"({m[sym]['filled']} uśrednionych), {m[sym]['first'][:16]} – {m[sym]['last'][:16]} UTC")
    return df


def sync(full: bool = False, quiet: bool = False, syms=None, proof: bool = False) -> dict[str, pd.DataFrame]:
    """Synchronizacja przyrostowa instrumentów (domyślnie bez fx1h_double_proof). Zwraca kopię lokalną tych instrumentów."""
    log = (lambda *a: None) if quiet else print
    remove_legacy(log)
    m = _manifest()
    out = {}
    for s in syms or symbols(proof):
        try:
            out[s] = sync_symbol(s, m, full, log)
        except Exception as e:                               # jeden instrument nie zatrzymuje reszty
            print(f"  ! {s}: {type(e).__name__}: {e}")
            if parquet_path(s).exists():
                out[s] = load(s)
        FX_DIR.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(m, indent=2), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Firestore fx1h → data/fx1h/*.parquet")
    ap.add_argument("--full", action="store_true", help="pobierz wszystkie dni od nowa")
    print("IA 4 — kopia lokalna FX 1h (z parami fx1h_double_proof — tylko kopia; badania ich nie wczytują)\n")
    sync(full=ap.parse_args().full, proof=True)


if __name__ == "__main__":
    main()
