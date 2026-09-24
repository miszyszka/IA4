#!/usr/bin/env python3
"""
IA 4 — sprawdzian kryterium 0.9.
Wersja projektu: 0.19 (2026-09-24) — musi zgadzać się z IA4_INSTRUKCJA.md

Kryterium 0.9 brzmi: „Python wczytuje dane wszystkich instrumentów, liczby
zgadzają się z audytem". Ten skrypt wypisuje tabelę w tym samym układzie,
co tabela instrumentów w arkuszu PROJEKT, żeby dało się je porównać wiersz
po wierszu — i sam sprawdza to, co da się sprawdzić bez arkusza.

    python verify.py                    # tabela + kontrole spójności
    python verify.py --audit audyt.tsv  # dodatkowo porównanie z wklejoną tabelą

Format pliku --audit: skopiowana z arkusza PROJEKT tabela instrumentów
(kolumny: Spółka, Grupa, Sesji, Świec, Zakres, Luk), rozdzielona tabulatorami.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from ia4 import config, data


def consistency_checks(cov: pd.DataFrame) -> list[str]:
    """Kontrole, które nie wymagają arkusza — same z siebie wyłapują kłopoty."""
    problems = []
    v = config.vault()
    u = config.universe()

    empty = cov[cov["sesji"] == 0]["symbol"].tolist()
    if empty:
        problems.append(f"Bez danych lokalnych: {', '.join(empty)} — uruchom python -m ia4.sync")

    # Instrument z historią krótszą niż okres badawczy nie nadaje się do
    # Etapów 1–3: cała jego historia leży w skarbcu albo po nim.
    short = cov[(cov["sesji"] > 0) & (cov["od"] >= v.vault_start)]["symbol"].tolist()
    if short:
        problems.append(
            f"Historia zaczyna się dopiero w skarbcu (bezużyteczne w Etapach 1–3): {', '.join(short)}")

    thin = cov[(cov["sesji"] > 0) & (cov["sesji"] < 100)]["symbol"].tolist()
    if thin:
        problems.append(f"Mniej niż 100 sesji: {', '.join(thin)}")

    if u["proof_failed"]:
        problems.append(f"Proof.gs oznaczył jako nieudane: {', '.join(u['proof_failed'])}")
    if u["proof_partial"]:
        problems.append(f"Proof.gs oznaczył jako niepełne: {', '.join(u['proof_partial'])}")

    missing = [s for s in config.all_symbols() if s not in set(cov["symbol"])]
    if missing:
        problems.append(f"W system/universe, ale bez wiersza tutaj: {', '.join(missing)}")

    return problems


def compare_with_audit(cov: pd.DataFrame, path: str) -> list[str]:
    """Porównanie z tabelą instrumentów wklejoną z arkusza PROJEKT."""
    try:
        aud = pd.read_csv(path, sep="\t")
    except Exception as e:
        return [f"Nie udało się wczytać {path}: {e}"]

    aud.columns = [c.strip().lower() for c in aud.columns]
    col = {"spółka": "symbol", "spolka": "symbol", "sesji": "sesji", "świec": "swiec", "swiec": "swiec"}
    aud = aud.rename(columns={c: col.get(c, c) for c in aud.columns})
    if "symbol" not in aud.columns:
        return [f"{path}: nie znalazłem kolumny „Spółka”"]

    merged = cov.merge(aud, on="symbol", how="outer", suffixes=("_py", "_arkusz"))
    out = []
    for _, r in merged.iterrows():
        for field in ("sesji", "swiec"):
            a, b = r.get(f"{field}_py"), r.get(f"{field}_arkusz")
            if pd.notna(a) and pd.notna(b) and int(a) != int(b):
                out.append(f"{r['symbol']}: {field} — Python {int(a)}, arkusz {int(b)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", help="plik TSV z tabelą instrumentów z arkusza PROJEKT")
    a = ap.parse_args()

    v = config.vault()
    print(f"IA 4 — sprawdzian 0.9 (instrukcja w Firestore: v{v.instruction_version}, etap {v.stage})")
    print(f"Okres badawczy: do {v.research_end} · skarbiec: {v.vault_start} – {v.vault_end}")
    print()

    cov = data.coverage()
    print(cov.to_string(index=False))
    print()

    problems = consistency_checks(cov)
    if a.audit:
        problems += compare_with_audit(cov, a.audit)

    total_sessions = int(cov["sesji"].sum())
    total_candles = int(cov["swiec"].sum())
    print(f"Razem: {len(cov)} instrumentów, {total_sessions} sesji, {total_candles} świec.")

    if problems:
        print("\nDO SPRAWDZENIA:")
        for p in problems:
            print(f"  · {p}")
        print("\nKryterium 0.9 NIE jest jeszcze spełnione.")
        return 1

    print("\nWszystko się zgadza — kryterium 0.9 można zaznaczyć w arkuszu PROJEKT.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
