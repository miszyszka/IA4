#!/usr/bin/env python3
"""
IA 4 — sprawdzian kryterium 0.9.
Wersja projektu: 0.47 (2026-09-29) — musi zgadzać się z IA4_INSTRUKCJA.md

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

„PRZED PRACĄ" (0.33): sekcja na początku wyjścia, zanim cokolwiek innego —
czy kopia lokalna (manifest `ia4.sync`) jest nowsza niż ostatni audyt Apps
Script z telemetrii, i co telemetria pokazuje jako otwarte luki (w tym
ZERO_WOLUMEN, L32). Celowo BEZ ŻADNEGO zapytania do Firestore — telemetria
przychodzi z pliku w repo (albo, gdy go nie ma lokalnie, z jego surowej
kopii na GitHubie — nadal nie z Firestore) — dokładnie po to, żeby dało się
to sprawdzać często bez zużywania dziennego limitu odczytów/zapisów.

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
SPLITS_PATH = config.RESEARCH_DIR.parent / "s1" / "splits.json"


def load_splits() -> set[tuple[str, str]]:
    """
    Sesje już potwierdzone jako split i wpisane do s1/splits.json (D24).
    Zwraca zbiór (symbol, date) — do wykluczenia z blokady ≥40% w main():
    bez tego kryterium 0.9 nigdy by się nie domknęło, bo KAŻDY prawdziwy
    split (nawet już rozpoznany i wpisany na listę) dalej wygląda jak skok
    ceny ≥40% w surowych danych Yahoo (0.34 — wykryte przy pierwszym pełnym
    przebiegu 0.9, gdzie NFLX z listy splits.json i tak blokował).
    """
    if not SPLITS_PATH.exists():
        return set()
    d = json.loads(SPLITS_PATH.read_text(encoding="utf-8"))
    return {(s["symbol"], s["date"]) for s in d.get("splits", [])}


def split_unlisted_jumps(big: pd.DataFrame, splits: set[tuple[str, str]]) -> tuple[pd.DataFrame, int]:
    """Rozdziela skoki ≥ SPLIT_LIKE_PCT na (nierozpoznane, ile już na liście splitów)."""
    if big.empty:
        return big, 0
    unlisted = big[~big.apply(lambda r: (r["symbol"], r["date"]) in splits, axis=1)]
    return unlisted, len(big) - len(unlisted)


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


def compare_with_telemetry(symbols: list[str], tel: dict) -> tuple[list[str], list[str], str]:
    """
    Sesje i świece w zakresie dat, który widział ostatni pełny audyt.
    Zwraca (problems, info, at):
      problems — Python ma MNIEJ niż audyt widział wtedy — prawdziwa rozbieżność
                 (utrata danych), blokuje kryterium 0.9.
      info     — Python ma WIĘCEJ niż audyt — oczekiwane, gdy automat łatania
                 (BRAK_SWIEC/ZERO_WOLUMEN) uzupełnił luki PO tym audycie, zanim
                 zrobiono tę synchronizację (0.34, zaobserwowane przy pierwszym
                 pełnym przebiegu 0.9: 9 instrumentów miało więcej świec niż
                 audyt z 2026-09-26, bo łatanie w międzyczasie je dograło) —
                 nie blokuje, tylko informuje.
    """
    inst = ((tel.get("data") or {}).get("instruments") or {})
    items = {r["symbol"]: r for r in inst.get("items", [])}
    at = inst.get("countedAt", "?")
    problems, info = [], []
    for s in symbols:
        a = items.get(s)
        if not a:
            problems.append(f"{s}: brak w tabeli audytu (telemetria z {at})")
            continue
        p = sync.parquet_path(s)
        if not p.exists():
            continue
        d = pd.read_parquet(p)
        d = d[(d["date"] >= a["first"]) & (d["date"] <= a["last"])]
        ses, cand = int(d["date"].nunique()), int(len(d))
        if ses < int(a["sessions"]) or cand < int(a["candles"]):
            problems.append(f"{s}: {a['first']} – {a['last']}: Python {ses} sesji / {cand} świec, "
                            f"audyt {a['sessions']} / {a['candles']} — Python ma MNIEJ niż audyt")
        elif ses > int(a["sessions"]) or cand > int(a["candles"]):
            info.append(f"{s}: Python {ses} sesji / {cand} świec, audyt {a['sessions']} / {a['candles']} "
                        f"— łatanie uzupełniło luki po audycie z {at}")
    return problems, info, at


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


def preflight_freshness(tel: dict) -> list[str]:
    """
    Sprawdzian „przed pracą" (0.33) — bez żadnego zapytania do Firestore:
    tylko manifest lokalnej synchronizacji (`ia4.sync`) i telemetria już
    ściągnięta z GitHuba (`load_telemetry` — plik z repo albo, w ostateczności,
    jego surowa kopia na GitHubie; nigdy Firestore).

    Odpowiada na dwa pytania z 0.33: czy kopia lokalna jest z ostatniej
    synchronizacji nowsza niż ostatni pełny/nocny audyt (czyli „nie
    przegapiłem nic nowego w Firebase"), i czy telemetria pokazuje świeże
    luki typu ZERO_WOLUMEN/BRAK_SWIEC (czyli „coś czeka na złatanie, zanim
    zaufam tym danym"). Zwraca listę linii do wypisania — nic nie pobiera.
    """
    out = []
    manifest = sync.load_manifest()
    synced_ats = [e.get("synced_at") for e in manifest.values() if e.get("synced_at")]
    last_sync = max(synced_ats) if synced_ats else None
    audit = (tel.get("data") or {}).get("audit") or {}
    full_at, nightly_at = audit.get("fullAt"), audit.get("nightlyAt")
    last_audit = max([x for x in (full_at, nightly_at) if x], default=None)

    if last_sync is None:
        out.append("Brak lokalnej synchronizacji (manifest pusty) — uruchom python -m ia4.sync.")
    elif last_audit and last_sync < last_audit:
        out.append(f"Kopia lokalna zsynchronizowana {last_sync}, ostatni audyt Apps Script "
                    f"{last_audit} — jest nowszy. Odśwież: python -m ia4.sync.")
    else:
        out.append(f"Kopia lokalna zsynchronizowana {last_sync or '?'} "
                    f"(ostatni audyt: {last_audit or '?'}) — aktualna, nic nie trzeba pobierać.")

    gaps = (tel.get("data") or {}).get("gaps") or {}
    by_type = gaps.get("byType") or {}
    if by_type:
        parts = ", ".join(f"{k}: {v}" for k, v in sorted(by_type.items()))
        out.append(f"Luki wg telemetrii (razem {gaps.get('total', '?')}, "
                    f"nowych {gaps.get('new', '?')}): {parts}.")
        zero_vol = by_type.get("ZERO_WOLUMEN")
        if zero_vol:
            out.append(f"  → ZERO_WOLUMEN: {zero_vol} — automat w tle (Code.gs) już próbuje je "
                       f"załatać (L32); jeśli po python -m ia4.sync nadal widać v=0 w świeżych "
                       f"sesjach, to normalne, dopóki telemetria nie pokaże ich jako zaakceptowanych.")
    return out


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
            print("PRZED PRACĄ (0.33 — bez odczytów Firestore):")
            for line in preflight_freshness(tel):
                print(f"  · {line}")
            print()
            diffs, more_info, at = compare_with_telemetry(symbols, tel)
            print(f"Porównanie z pełnym audytem z {at}: "
                  f"{'zgodne' if not diffs else f'{len(diffs)} rozbieżności'}")
            problems += diffs
            if more_info:
                notes.append(f"{len(more_info)} instrument(ów) ma więcej sesji/świec niż audyt z {at} — "
                             "łatanie luk uzupełniło je w międzyczasie (nieblokujące):")
                notes.extend(f"  {line}" for line in more_info)

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
        # Sesja już wpisana do s1/splits.json (D24) jest ROZPOZNANYM splitem —
        # nadal wygląda jak skok ≥40% w surowych danych Yahoo (to nie usuwa
        # samej ceny), więc bez tego wykluczenia kryterium 0.9 nigdy by się
        # nie domknęło: każdy potwierdzony split blokowałby się sam na zawsze.
        unlisted, listed = split_unlisted_jumps(big, load_splits())
        if listed:
            notes.append(f"{listed} skok(ów) ≥{SPLIT_LIKE_PCT:.0f}% już na liście splitów "
                         f"(s1/splits.json, D24) — nie blokuje.")
        if len(unlisted):
            problems.append("Skoki ≥ {:.0f}% — prawie na pewno split albo artefakt Yahoo, sesja musi trafić "
                            "na listę splitów przed Etapem 1b (D11): {}".format(
                                SPLIT_LIKE_PCT, ", ".join(f"{r.symbol} {r.date}" for r in unlisted.itertuples())))
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
