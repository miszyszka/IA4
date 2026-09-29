"""
IA 4 — sprawdzian poletka dla listy kandydatów S2 (Etap 2, 2.4; decyzja D33).
Wersja projektu: 0.43 (2026-09-29) — musi zgadzać się z IA4_INSTRUKCJA.md

Bierze 50 strategii zamrożonych w `s2/kandydaci.json` i liczy je JEDEN raz na
poletku (2025-10-01 – 2026-03-22, zasada 5.1) dokładnie tym samym sposobem co
przebieg 3 backtestu (D30–D32): bez kosztów, 10 $ na transakcję, ten sam tryb
pozycji, SL/TP/H, wejście losowe (5.3) liczone na świecach poletka.

  - Wejścia tylko na poletku. Wskaźniki rozgrzewają się na odkrywaniu (ta sama
    ciągła seria świec), więc sygnał z pierwszego dnia poletka jest ważny.
  - Transakcje otwarte na końcu poletka zamykane po ostatniej świecy poletka
    (dane kończą się przed skarbcem — skarbca ten moduł nie wczytuje).
  - Kryterium D33 zapisane w `s2/kandydaci.json` PRZED uruchomieniem:
    strategia zostaje, gdy przewaga > 0 i ekspektancja ≥ 0,10% w OBU grupach;
    lista coś znaczy, gdy zostaje ≥ 20 z 50.

Bezpieczniki:
  - `s2/kandydaci.json` musi być zatwierdzony w git i bez lokalnych zmian
    (lista ustalona przed obejrzeniem poletka, nie po);
  - drugi przebieg odmówi, jeśli `s2/poletko_meta.json` już istnieje (5.1);
  - całe poletko wczytane jednym `data.load(..., plot_reason=...)` —
    jeden wpis w `poletko_zajrzenia.jsonl`.

    python3 -m ia4.poletko --sprawdz-odkrywanie   # ten sam kod na odkrywaniu = results.csv (bez poletka)
    python3 -m ia4.poletko                        # sprawdzian poletka, RAZ
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest as BT
from . import catalog

REPO = catalog.repo_root()
S2 = REPO / "s2"
CANDIDATES = S2 / "kandydaci.json"
OUT_CSV = S2 / "poletko.csv"
OUT_META = S2 / "poletko_meta.json"
PLOT_START = "2025-10-01"
PASS_EKSP = 0.10            # D33: ekspektancja bez kosztów ≥ 0,10% (= 0,05% po kosztach, 5.11)
MIN_PASS = 20               # D33: lista coś znaczy od 20 z 50
PLOT_REASON = "Etap 2: jednorazowy sprawdzian 50 kandydatów S2 (D33, s2/kandydaci.json)"
METRICS = ("transakcji", "skutecznosc", "ekspektancja", "przewaga", "wynik_portfela", "max_otwartych")


def load_candidates(path: Path = CANDIDATES) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    ids = "\n".join(s["id"] for s in doc["strategie"])
    if hashlib.sha256(ids.encode()).hexdigest() != doc["meta"]["sha256_ids"]:
        raise ValueError(f"{path.name}: lista strategii nie zgadza się z sha256_ids — ktoś ją zmienił po zamrożeniu.")
    return doc


def git_guard(path: Path = CANDIDATES) -> str | None:
    """Lista musi być w repozytorium i bez lokalnych zmian — zamrożona PRZED poletkiem."""
    rel = str(path.relative_to(REPO))
    try:
        tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "--error-unmatch", rel],
                                 capture_output=True).returncode == 0
        clean = subprocess.run(["git", "-C", str(REPO), "diff", "--quiet", "HEAD", "--", rel],
                               capture_output=True).returncode == 0
    except FileNotFoundError:
        return "brak polecenia git — nie da się potwierdzić, że lista była zamrożona przed poletkiem."
    if not tracked:
        return f"{rel} nie jest zatwierdzony w repozytorium — najpierw git add/commit/push (D33)."
    if not clean:
        return f"{rel} ma niezatwierdzone zmiany — lista kandydatów nie może się zmieniać po zamrożeniu (D33)."
    return None


def window(insts: list, start_date: str | None) -> int:
    """Ustawia pierwszą świecę wejścia (start) i numery tygodni liczone tylko w oknie wejść."""
    lo = start_date or "0000-00-00"
    weeks = sorted({date.fromisoformat(d).isocalendar()[:2] for it in insts for d in it.B.date if d >= lo})
    widx = {w: i for i, w in enumerate(weeks)}
    for it in insts:
        dates = np.asarray(it.B.date)
        it.start = int(np.searchsorted(dates, lo, side="left"))
        it.week = np.array([widx.get(date.fromisoformat(d).isocalendar()[:2], 0) for d in dates])
    return len(weeks)


def evaluate(doc: dict, cat: dict, frames: dict, spy, groups: dict, start_date: str | None,
             boot: int = BT.BOOT_B, seed: int = BT.SEED) -> pd.DataFrame:
    insts, _ = BT.prepare(frames, spy, groups)
    W = window(insts, start_date)
    H = BT.h_matrix()
    rnd = BT.random_baseline(insts, H)
    sigs = {s["code"]: s for s in cat["signals"]}
    cache: dict = {}
    rows, SW, NW, RW = [], {g: [] for g in BT.GROUPS}, {g: [] for g in BT.GROUPS}, {g: [] for g in BT.GROUPS}
    for c in doc["strategie"]:
        if c["sygnal"] not in cache:
            cache[c["sygnal"]] = BT._collect(sigs[c["sygnal"]], insts, H)
        tr = cache[c["sygnal"]]
        i, j = BT.SL_GRID.index(c["sl"]), BT.TP_GRID.index(c["tp"])
        row = {k: c[k] for k in ("nr", "id", "motyw", "kategoria", "kierunek", "sl", "tp", "h", "tryb")}
        for g, pre in BT.GROUPS.items():
            r0 = float(rnd[(g, c["kierunek"])][i, j])
            m, Sw, Nw = BT.metrics(tr.get((g, c["tryb"], c["kierunek"], i, j)), r0, W)
            row.update({f"{pre}_{k}": m[k] for k in METRICS})
            SW[g].append(Sw); NW[g].append(Nw); RW[g].append(r0)
        rows.append(row)
    df = pd.DataFrame(rows)
    for g, pre in BT.GROUPS.items():          # informacyjnie: p z bootstrapu (D30) dla każdej strategii osobno
        df[f"{pre}_p"] = BT.bootstrap_p(np.array(SW[g]), np.array(NW[g]), np.array(RW[g]), boot, seed)
    for pre in BT.GROUPS.values():
        df[f"{pre}_przewaga_odkrywanie"] = [c["odkrywanie"][f"{pre}_przewaga"] for c in doc["strategie"]]
        df[f"{pre}_ekspektancja_odkrywanie"] = [c["odkrywanie"][f"{pre}_ekspektancja"] for c in doc["strategie"]]
    df["zostaje"] = passes(df)
    return df


def passes(df: pd.DataFrame) -> pd.Series:
    """D33: przewaga > 0 i ekspektancja ≥ 0,10% w obu grupach; brak transakcji = nie zostaje."""
    ok = pd.Series(True, index=df.index)
    for pre in BT.GROUPS.values():
        ok &= (df[f"{pre}_transakcji"] > 0)
        ok &= df[f"{pre}_przewaga"].fillna(-1) > 0
        ok &= df[f"{pre}_ekspektancja"].fillna(-1) >= PASS_EKSP
    return ok


def verdict(df: pd.DataFrame) -> dict:
    n = int(df["zostaje"].sum())
    return {"zostaje": n, "z": int(len(df)), "prog": MIN_PASS, "lista_cos_znaczy": n >= MIN_PASS,
            "przewaga_w_obu_grupach": int(((df.gl_przewaga.fillna(-1) > 0) & (df.kontr_przewaga.fillna(-1) > 0)).sum()),
            "wg_motywu": {m: f"{int(g.zostaje.sum())}/{len(g)}" for m, g in df.groupby("motyw")},
            "wniosek": ("Lista przechodzi D33 — strategie, które zostały, idą do s2/strategies.json (2.4)."
                        if n >= MIN_PASS else
                        "Lista NIE przechodzi D33 — wynik zgodny z brakiem przewagi w S1; dalej według 5.12.")}


def compare_with_backtest(df: pd.DataFrame, path: Path = BT.OUT_DIR / "results.csv") -> float:
    """Kontrola: ten sam kod na odkrywaniu musi dać liczby z przebiegu 3."""
    ref = pd.read_csv(path, dtype={"tryb": str}).set_index("id")
    worst = 0.0
    for col in [f"{p}_{k}" for p in BT.GROUPS.values() for k in ("transakcji", "ekspektancja", "przewaga", "wynik_portfela")]:
        a = df.set_index("id")[col].astype(float)
        b = ref.loc[a.index, col].astype(float)
        worst = max(worst, float(np.nanmax(np.abs(a.values - b.values))))
    return worst


def _frames(df: pd.DataFrame, syms: list[str]) -> dict:
    return {s: df[df["symbol"] == s].reset_index(drop=True) for s in syms}


def main(argv=None) -> int:
    from . import config, data
    ap = argparse.ArgumentParser(description="Etap 2: jednorazowy sprawdzian poletka dla s2/kandydaci.json (D33).")
    ap.add_argument("--sprawdz-odkrywanie", action="store_true",
                    help="policz 50 kandydatów na odkrywaniu i porównaj z s1-backtest/results.csv (nie dotyka poletka)")
    a = ap.parse_args(argv)
    doc = load_candidates()
    cat = json.loads((REPO / "s1" / "catalog.json").read_text(encoding="utf-8"))
    if cat["meta"]["content_hash"] != doc["meta"]["zrodlo"]["catalog_hash"]:
        print("Katalog S1 różni się od tego, z którego wybrano kandydatów — przerwane.")
        return 1
    u = config.universe()
    groups = {"main": list(u["main"]), "control": list(u["proof"])}
    syms = groups["main"] + groups["control"]
    t0 = time.time()

    if a.sprawdz_odkrywanie:
        allf = data.load(syms + ["SPY"], period="discovery")
        fr = _frames(allf, syms + ["SPY"])
        df = evaluate(doc, cat, {s: fr[s] for s in syms}, fr["SPY"], groups, None)
        worst = compare_with_backtest(df)
        print(f"Odkrywanie, {len(df)} kandydatów: największa różnica z results.csv = {worst:.5f} "
              f"({(time.time() - t0) / 60:.1f} min)")
        if worst > 1e-3:
            print("RÓŻNICA — nie uruchamiaj poletka, wklej ten wynik Claude.")
            return 1
        print("Zgodne z przebiegiem 3. Można uruchomić sprawdzian poletka: python3 -m ia4.poletko")
        return 0

    if OUT_META.exists():
        print(f"{OUT_META.relative_to(REPO)} już istnieje — poletko w Etapie 2 liczy się RAZ (5.1). Przerwane.")
        return 1
    err = git_guard()
    if err:
        print("Przerwane: " + err)
        return 1
    allf = data.load(syms + ["SPY"], period="research", plot_reason=PLOT_REASON)   # jeden wpis w dzienniku poletka
    fr = _frames(allf, syms + ["SPY"])
    last = str(allf["date"].max())
    df = evaluate(doc, cat, {s: fr[s] for s in syms}, fr["SPY"], groups, PLOT_START)
    v = verdict(df)
    meta = {"decyzja": "D33", "okres": f"{PLOT_START} – {last}", "kandydaci_sha256": doc["meta"]["sha256_ids"],
            "catalog_hash": cat["meta"]["content_hash"], "sposob_liczenia": "przebieg 3 (D30–D32), bez kosztów",
            "prog_ekspektancji": PASS_EKSP, **v,
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "runtime_min": round((time.time() - t0) / 60, 1)}
    S2.mkdir(exist_ok=True)
    df.to_csv(OUT_CSV, index=False, float_format="%.4f")
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Poletko {meta['okres']}: zostaje {v['zostaje']} z {v['z']} (próg {MIN_PASS}); "
          f"przewaga w obu grupach: {v['przewaga_w_obu_grupach']}")
    print("Według motywu: " + ", ".join(f"{k}: {x}" for k, x in v["wg_motywu"].items()))
    print(v["wniosek"])
    print("Teraz: cd .. && git add s2 ia4-research/poletko_zajrzenia.jsonl && "
          "git commit -m 'Poletko Etap 2 (D33)' && git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
