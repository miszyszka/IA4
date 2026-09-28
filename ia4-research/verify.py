#!/usr/bin/env python3
"""
IA 4 — sprawdzian kryterium 0.9.
Wersja projektu: 0.31 (2026-09-28) — musi zgadzać się z IA4_INSTRUKCJA.md

Kryterium 0.9 brzmi: „Python wczytuje dane wszystkich instrumentów, liczby
zgadzają się z audytem". Ten skrypt wypisuje tabelę w tym samym układzie,
co tabela instrumentów w arkuszu PROJEKT, żeby dało się je porównać wiersz
po wierszu — i sam sprawdza to, co da się sprawdzić bez arkusza.

    python verify.py                    # tabela + kontrole + porównanie z audytem z telemetrii
    python verify.py --audit audyt.tsv  # porównanie z tabelą wklejoną ręcznie z arkusza
    python verify.py --no-telemetry     # bez porównania z audytem

Porównanie z audytem (od 0.30) jest automatyczne: tabela instrumentów z
ostatniego pełnego audytu leży w telemetry/state.json (to samo repozytorium),
więc nie trzeba jej kopiować z arkusza. Porównujemy tylko zakres dat, który
audyt widział (od „first” do „last” każdego instrumentu) — sesje dopisane po
audycie nie są rozbieżnością.

Dodatkowo (0.30) dwie kontrole, bez których nie da się zacząć Etapu 1b:
  · WOLUMEN (D12) — czy dopisywanie wolumenu doszło do końca: sesje bez
    wolumenu w okresie badawczym. Sesje na samym początku historii, do których
    Yahoo już nie sięga (~730 dni), zostają z v = 0 na zawsze — są wypisane
    osobno i nie blokują kryterium; dziura w środku historii blokuje.
  · SKOKI CENY > 15% (D11) — ta sama reguła co audyt. Skok ~50–90% to prawie
    na pewno split albo niezgodne dostosowanie ceny przez Yahoo, nie rynek.

Skrypt czyta pliki parquet bezpośrednio — nie przez data.load — więc nie
liczy się jako zajrzenie na poletko ani do skarbca: liczy tylko kompletność
danych, żadnego wyniku (5.1, 1.1).

Format pliku --audit: skopiowana z arkusza PROJEKT tabela instrumentów
(kolumny: Spółka, Grupa, Sesji, Świec, Zakres, Luk), rozdzielona tabulatorami.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from ia4 import config, data, sync

JUMP_PCT = 15.0          # próg skoku ceny — jak w audycie Apps Script (D11)
SPLIT_LIKE_PCT = 40.0    # powyżej: prawie na pewno split/artefakt, nie ruch rynku
MAX_LEAD_NO_VOLUME = 20  # sesji bez wolumenu na początku historii, które tłumaczy horyzont Yahoo
TELEMETRY_PATH = config.RESEARCH_DIR.parent / "telemetry" / "state.json"
TELEMETRY_URL = "https://raw.githubusercontent.com/miszyszka/IA4/main/telemetry/state.json"


# ---------------------------------------------------------------------------
#  Wolumen (D12) i skoki ceny (D11) — z plików parquet, bez data.load
# ---------------------------------------------------------------------------
def volume_report(symbols: list[str], research_end_exclusive: str) -> pd.DataFrame:
    """
    Na instrument, w okresie badawczym (odkrywanie + poletko):
      bez_wol_pocz  sesje bez wolumenu PRZED pierwszą sesją z wolumenem
                    (horyzont Yahoo — informacyjnie),
      bez_wol_srod  sesje bez wolumenu PO niej (dziura — blokuje 1b),
      wol_od        pierwsza sesja z wolumenem,
      swiec_v0      pojedyncze świece z v = 0 w sesjach, które wolumen mają.
    """
    rows = []
    for s in symbols:
        p = sync.parquet_path(s)
        if not p.exists():
            continue
        d = pd.read_parquet(p)
        d = d[d["date"] < research_end_exclusive]
        if d.empty:
            continue
        per = d.groupby("date")["v"].agg(lambda x: int((x > 0).sum())).sort_index()
        with_vol = per[per > 0]
        first = with_vol.index[0] if len(with_vol) else ""
        if first:
            lead = int((per.index < first).sum())
            mid_dates = per[(per.index > first) & (per == 0)].index.tolist()
        else:
            lead, mid_dates = len(per), []
        in_vol_sessions = d[d["date"].isin(with_vol.index)]
        rows.append({
            "symbol": s,
            "wol_od": first,
            "bez_wol_pocz": lead,
            "bez_wol_srod": len(mid_dates),
            "przyklad_dziury": ", ".join(mid_dates[:3]),
            "swiec_v0": int((in_vol_sessions["v"] == 0).sum()),
        })
    return pd.DataFrame(rows)


def price_jumps(symbols: list[str]) -> pd.DataFrame:
    """Skoki zamknięcie → następne otwarcie/zamknięcie powyżej JUMP_PCT, cała historia."""
    out = []
    for s in symbols:
        p = sync.parquet_path(s)
        if not p.exists():
            continue
        d = pd.read_parquet(p).sort_values(["date", "slot"]).reset_index(drop=True)
        prev_c = d["c"].shift(1)
        for col in ("o", "c"):
            pct = (d[col] / prev_c - 1.0) * 100.0
            hit = d[pct.abs() > JUMP_PCT]
            for i, r in hit.iterrows():
                out.append({"symbol": s, "date": r["date"], "slot": int(r["slot"]),
                            "z": float(prev_c.iloc[i]), "na": float(r[col]),
                            "pct": round(float(pct.iloc[i]), 1), "gdzie": col})
    df = pd.DataFrame(out, columns=["symbol", "date", "slot", "z", "na", "pct", "gdzie"])
    # otwarcie i zamknięcie tej samej świecy to zwykle ten sam skok — zostaw jeden wpis
    return df.drop_duplicates(subset=["symbol", "date", "slot"], keep="first").reset_index(drop=True)


# ---------------------------------------------------------------------------
#  Audyt z telemetrii (kryterium 0.9 bez kopiowania tabeli z arkusza)
# ---------------------------------------------------------------------------
def load_telemetry(path: Path = TELEMETRY_PATH) -> dict | None:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        import urllib.request
        with urllib.request.urlopen(TELEMETRY_URL, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # brak sieci — porównanie po prostu się nie odbędzie
        print(f"(nie udało się pobrać telemetrii: {e})")
        return None


def compare_with_telemetry(symbols: list[str], tel: dict) -> tuple[list[str], str]:
    """Sesje i świece w zakresie dat, który widział ostatni pełny audyt."""
    inst = ((tel.get("data") or {}).get("instruments") or {})
    items = {r["symbol"]: r for r in inst.get("items", [])}
    at = inst.get("countedAt", "?")
    out = []
    for s in symbols:
        a = items.get(s)
        if not a:
            out.append(f"{s}: brak w tabeli audytu (telemetria z {at})")
            continue
        p = sync.parquet_path(s)
        if not p.exists():
            continue
        d = pd.read_parquet(p)
        d = d[(d["date"] >= a["first"]) & (d["date"] <= a["last"])]
        ses, cand = int(d["date"].nunique()), int(len(d))
        if ses != int(a["sessions"]) or cand != int(a["candles"]):
            out.append(f"{s}: {a['first']} – {a['last']}: Python {ses} sesji / {cand} świec, "
                       f"audyt {a['sessions']} / {a['candles']}")
    return out, at


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
    ap.add_argument("--telemetry", help="ścieżka do telemetry/state.json (domyślnie z klonu repo)")
    ap.add_argument("--no-telemetry", action="store_true", help="bez porównania z audytem z telemetrii")
    a = ap.parse_args()

    v = config.vault()
    print(f"IA 4 — sprawdzian 0.9 (instrukcja w Firestore: v{v.instruction_version}, etap {v.stage})")
    print(f"Okres badawczy: do {v.research_end} · skarbiec: {v.vault_start} – {v.vault_end}")
    print()

    cov = data.coverage()
    print(cov.to_string(index=False))
    print()

    problems = consistency_checks(cov)
    notes: list[str] = []
    symbols = cov[cov["sesji"] > 0]["symbol"].tolist()

    # --- porównanie z audytem ---
    if a.audit:
        problems += compare_with_audit(cov, a.audit)
    if not a.no_telemetry:
        tel = load_telemetry(Path(a.telemetry) if a.telemetry else TELEMETRY_PATH)
        if tel:
            diffs, at = compare_with_telemetry(symbols, tel)
            print(f"Porównanie z pełnym audytem z {at}: "
                  f"{'zgodne' if not diffs else f'{len(diffs)} rozbieżności'}")
            problems += diffs

    # --- wolumen (D12) ---
    vol = volume_report(symbols, v.vault_start)
    if not vol.empty:
        none = vol[vol["wol_od"] == ""]
        holes = vol[vol["bez_wol_srod"] > 0]
        has = vol[vol["wol_od"] != ""]
        # Granica Yahoo (~730 dni) względem początku historii (2024-09) to ok. 10 sesji.
        # Dużo więcej = dopisywanie nie doszło do granicy, a nie horyzont Yahoo.
        long_lead = has[has["bez_wol_pocz"] > MAX_LEAD_NO_VOLUME]
        lead = has[(has["bez_wol_pocz"] > 0) & (has["bez_wol_pocz"] <= MAX_LEAD_NO_VOLUME)]
        bad = len(set(none["symbol"]) | set(holes["symbol"]) | set(long_lead["symbol"]))
        print(f"\nWolumen w okresie badawczym (D12): pełny w {len(vol) - bad}/{len(vol)} instrumentach")
        if len(none):
            problems.append(f"Brak wolumenu w całym okresie badawczym: {', '.join(none['symbol'])}")
        if len(long_lead):
            problems.append("Ponad {} sesji bez wolumenu na początku historii (dopisywanie nie doszło do "
                            "granicy Yahoo): {}".format(MAX_LEAD_NO_VOLUME, ", ".join(
                                f"{r.symbol} (wolumen od {r.wol_od})" for r in long_lead.itertuples())))
        if len(holes):
            print(holes[["symbol", "wol_od", "bez_wol_srod", "przyklad_dziury"]].to_string(index=False))
            problems.append(f"Sesje bez wolumenu w środku historii: {', '.join(holes['symbol'])} — "
                            "dopisywanie wolumenu nie skończone albo kopia lokalna nieaktualna "
                            "(python -m ia4.sync)")
        if len(lead):
            notes.append(f"Początek historii bez wolumenu (horyzont Yahoo ~730 dni, nie do odzyskania): "
                         f"do {lead['bez_wol_pocz'].max()} sesji na instrument, wolumen od "
                         f"{lead['wol_od'].min()} – {lead['wol_od'].max()}. Sygnały z „Wol.” ich nie użyją (1.3).")
        zeros = int(vol["swiec_v0"].sum())
        if zeros:
            notes.append(f"Pojedyncze świece z v = 0 w sesjach z wolumenem: {zeros} (informacyjnie).")

    # --- skoki ceny (D11) ---
    jumps = price_jumps(symbols)
    if not jumps.empty:
        print(f"\nSkoki ceny > {JUMP_PCT:.0f}% (D11): {len(jumps)}")
        print(jumps.to_string(index=False))
        big = jumps[jumps["pct"].abs() >= SPLIT_LIKE_PCT]
        if len(big):
            problems.append("Skoki ≥ {:.0f}% — prawie na pewno split albo artefakt Yahoo, sesja musi trafić "
                            "na listę splitów przed Etapem 1b (D11): {}".format(
                                SPLIT_LIKE_PCT, ", ".join(f"{r.symbol} {r.date}" for r in big.itertuples())))
        notes.append("Każdy skok z listy trzeba ocenić (split czy wynik kwartalny) — D11.")

    total_sessions = int(cov["sesji"].sum())
    total_candles = int(cov["swiec"].sum())
    print(f"Razem: {len(cov)} instrumentów, {total_sessions} sesji, {total_candles} świec.")

    if notes:
        print("\nINFORMACYJNIE:")
        for n_ in notes:
            print(f"  · {n_}")

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
