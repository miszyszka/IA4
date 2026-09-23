"""
IA 4 — wczytywanie danych do badań.
Wersja projektu: 0.8 (2026-09-23) — musi zgadzać się z IA4_INSTRUKCJA.md

Ten moduł jest jedyną drogą, którą dane trafiają do backtestu — i celowo
utrudnia złamanie zasady 5.1.

DLACZEGO TAK: skarbiec chroni przed oszukiwaniem samego siebie, ale tylko
dopóki nikt do niego nie zajrzy przed czasem. Wystarczy jedno „sprawdzę
szybko, jak to wygląda na nowszych danych" i sprawdzian w Etapie 3 przestaje
cokolwiek znaczyć — a nikt tego potem nie wykryje, bo wynik będzie wyglądał
normalnie. Dlatego domyślnie zwracamy WYŁĄCZNIE okres badawczy, a po dane ze
skarbca trzeba sięgnąć jawnie i świadomie:

    load("AAPL")                        # okres badawczy — domyślnie
    load("AAPL", period="vault")        # rzuci błąd, dopóki skarbiec zamknięty
    load("AAPL", period="live")         # dane po granicy (Etapy 4–5)

Granice pochodzą z Firestore (system/project), nie z tego pliku.
"""

from __future__ import annotations

import pandas as pd

from . import config, sync

PERIODS = ("research", "vault", "live", "all")


class VaultError(RuntimeError):
    """Próba sięgnięcia do skarbca przed Etapem 3."""


def _filter_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    v = config.vault()
    if period == "research":
        return df[df["date"] < v.vault_start]
    if period == "vault":
        return df[(df["date"] >= v.vault_start) & (df["date"] <= v.vault_end)]
    if period == "live":
        return df[df["date"] >= v.live_from]
    return df


def load(
    symbols: str | list[str] | None = None,
    period: str = "research",
    unlock_vault: bool = False,
) -> pd.DataFrame:
    """
    Świece 1h z lokalnej pamięci podręcznej.

    symbols      pojedynczy symbol, lista, albo None = wszystkie
    period       research (domyślnie) | vault | live | all
    unlock_vault świadome potwierdzenie dostępu do skarbca (Etap 3, jeden raz)

    Zwraca: symbol, date, slot, o, h, l, c, v — posortowane po dacie i świecy.
    """
    if period not in PERIODS:
        raise ValueError(f"period musi być jednym z {PERIODS}, jest: {period!r}")

    v = config.vault()
    if period in ("vault", "all") and not unlock_vault:
        raise VaultError(
            f"Próba odczytu skarbca ({v.vault_start} – {v.vault_end}) bez potwierdzenia.\n"
            "Skarbiec otwiera się RAZ, na końcu Etapu 3, do jednego sprawdzianu (zasada 5.1).\n"
            "Jeśli to właśnie ten moment: load(..., period='vault', unlock_vault=True)\n"
            "i zapisz datę otwarcia w arkuszu PROJEKT.\n"
            f"Etap zapisany w Firestore: {v.stage}."
        )
    if period in ("vault", "all") and unlock_vault and v.stage < 3:
        print(f"UWAGA: skarbiec otwierany na etapie {v.stage}, a zasada 5.1 przewiduje Etap 3.")

    if isinstance(symbols, str):
        symbols = [symbols]
    symbols = symbols or config.all_symbols()

    frames = []
    missing = []
    for s in symbols:
        p = sync.parquet_path(s)
        if not p.exists():
            missing.append(s)
            continue
        frames.append(pd.read_parquet(p))

    if missing:
        raise FileNotFoundError(
            f"Brak lokalnych danych dla: {', '.join(missing)}.\n"
            "Uruchom najpierw: python -m ia4.sync"
        )

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=sync.COLUMNS)
    df = _filter_period(df, period)
    return df.sort_values(["symbol", "date", "slot"]).reset_index(drop=True)


def sessions(df: pd.DataFrame) -> pd.DataFrame:
    """Zwija świece do sesji: jedna linia na (symbol, date) z listą świec."""
    return (
        df.groupby(["symbol", "date"])
        .agg(bars=("slot", "count"), o=("o", "first"), h=("h", "max"),
             l=("l", "min"), c=("c", "last"), v=("v", "sum"))
        .reset_index()
    )


def coverage(symbols: list[str] | None = None) -> pd.DataFrame:
    """
    Zakres danych każdego instrumentu — do porównania z tabelą z audytu
    (kryterium 0.9). Liczy CAŁOŚĆ, nie tylko okres badawczy, bo audyt
    w Apps Script też liczy całość.
    """
    symbols = symbols or config.all_symbols()
    rows = []
    for s in symbols:
        p = sync.parquet_path(s)
        if not p.exists():
            rows.append({"symbol": s, "grupa": config.group_of(s), "sesji": 0,
                         "swiec": 0, "od": "", "do": ""})
            continue
        d = pd.read_parquet(p)
        rows.append({
            "symbol": s,
            "grupa": config.group_of(s),
            "sesji": int(d["date"].nunique()),
            "swiec": int(len(d)),
            "od": str(d["date"].min()),
            "do": str(d["date"].max()),
        })
    return pd.DataFrame(rows)
