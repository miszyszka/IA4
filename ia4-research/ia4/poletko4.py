"""
IA 4 — sprawdzian przebiegu 4 na poletku (Etap 2, D35).
Wersja projektu: 0.47 (2026-09-29) — musi zgadzać się z IA4_INSTRUKCJA.md

Odpowiada na jedno pytanie: **czy okoliczności z przebiegu 4 przewidują cokolwiek
na danych, których przy liczeniu ratingu nie było?**

Liczy w JEDNYM przebiegu trzy wersje tej samej strategii na poletku
(2025-10-01 – 2026-03-22), żeby dały się porównać wprost:

  U — okres odkrywania, bez filtra. Punkt odniesienia; te liczby muszą się
      zgadzać z kolumnami `b_*` z przebiegu 4.
  A — poletko, bez filtra. Ile strategia daje sama z siebie na nowych danych.
  B — poletko z filtrem, **rating policzony WYŁĄCZNIE z okresu odkrywania**.
      To jest prawdziwy sprawdzian: okoliczności oceniają transakcje, których
      nigdy nie widziały.
  C — poletko z filtrem, rating policzony z tych samych transakcji poletka
      (tak jak w D34g). Nie jest sprawdzianem — jest podziałką. Różnica
      C − B pokazuje, ile „poprawy" bierze się z samego dopasowania do wyniku.

Wniosek czyta się z B, nie z C. Jeżeli B ≈ A, okoliczności nic nie wnoszą.
Jeżeli B wyraźnie lepsze od A, jest czego szukać dalej.

**To jest drugie zajrzenie na poletko w Etapie 2** (pierwsze: wycofane D33,
luka L37). Zasada 5.1 przewiduje jedno na etap. Modul mówi o tym wprost przy
starcie i wymaga potwierdzenia flagą `--wiem-ze-drugie`.

    python3 -m ia4.poletko4 --limit 3                 # próba, nic nie zapisuje
    python3 -m ia4.poletko4 --wiem-ze-drugie          # sprawdzian, RAZ
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import bars, catalog, nyse, okolicznosci, signals
from .backtest import (BOOT_B, LIMITS, MODES, SEED, SL_GRID, TP_GRID, h_matrix,
                       limit_positions, max_concurrent, new_signal_only, strategy_id)
from .engine import Engine, one_position, resolve_grid
from .przebieg4 import (COST, MIN_OBS, NEUTRAL, STAWKA_MAX, STAWKA_MIN, Inst,
                        okol_row, oceny, ratingi, stawki)

OUT_DIR = catalog.repo_root() / "s2"
OUT_CSV = OUT_DIR / "poletko4.csv"
OUT_META = OUT_DIR / "poletko4_meta.json"
PLOT_REASON = ("Etap 2, D35: sprawdzian przebiegu 4 na poletku — rating okoliczności "
               "z okresu odkrywania zastosowany do transakcji z poletka")

WERSJE = ("U", "A", "B", "C")
METRYKI = ("transakcji", "skutecznosc", "ekspektancja", "pct_czas", "max_otwartych",
           "wynik_portfela", "przewaga", "srednia_stawka")
COLUMNS = (["id", "sygnal", "kategoria", "kierunek", "sl", "tp", "h", "sl_rowne_tp", "tryb"]
           + [f"{w}_{m}" for w in WERSJE for m in METRYKI]
           + ["zysk_filtra_B", "zysk_filtra_C", "iluzja_C_minus_B",
              "ok_mocnych_odkrywanie", "ok_najlepsza_odkrywanie", "ok_najlepsza_rating",
              "B_uczonych_na"])


def prepare(frames: dict, spy, symbols: list[str], plot_start: str,
            progress=print) -> tuple[list[Inst], np.ndarray, np.ndarray]:
    """Świece całego okresu badawczego; `off` wskazuje na sklejone macierze okoliczności."""
    M = len(okolicznosci.DEFS)
    vals, dfns = [np.zeros((1, M), bool)], [np.zeros((1, M), bool)]
    out, off = [], 1
    for s in symbols:
        if s not in frames or frames[s].empty:
            continue
        B = bars.prepare(frames[s], market=spy)
        v, d = okolicznosci.evaluate(B)
        vals.append(v)
        dfns.append(d)
        tord = np.array([nyse.ordinal(x) for x in B.date]) * 8 + B.slot
        it = Inst(s, "razem", B, Engine(B, sl_grid=SL_GRID, tp_grid=TP_GRID), tord, None, off)
        it.poletko = np.asarray(B.date) >= plot_start          # świece poletka
        out.append(it)
        off += B.n
        if len(out) % 10 == 0:
            progress(f"  okoliczności: {len(out)} instrumentów")
    return out, np.vstack(vals), np.vstack(dfns)


def random_baseline(insts: list[Inst], H: np.ndarray, tylko_poletko: bool) -> dict:
    """5.3: średni wynik wejścia w każdą świecę — osobno dla odkrywania i dla poletka."""
    out = {}
    for d in ("L", "S"):
        tot, cnt = np.zeros(H.shape), 0
        for it in insts:
            idx = np.flatnonzero(it.poletko if tylko_poletko else ~it.poletko)
            if not len(idx):
                continue
            r = resolve_grid(it.eng, idx, d, H)
            tot += r.ret.sum(axis=0)
            cnt += r.ret.shape[0]
        out[d] = (tot / max(cnt, 1)) * 100.0 - COST
    return out


def collect(sig: dict, insts: list[Inst], H: np.ndarray, weeks: dict) -> dict:
    """
    Transakcje na CAŁYM okresie badawczym, z limitami pozycji liczonymi ciągle
    (pozycja otwarta w odkrywaniu może przechodzić na poletko — tak działałby
    prawdziwy portfel). Każda transakcja dostaje znacznik `pol`: czy weszła na poletku.
    """
    acc: dict = {}
    for it in insts:
        m = signals.mask(sig, it.B)
        n = it.B.n
        ent = {}
        for key, mm in (("1", m), ("nowy", new_signal_only(m))):
            e = signals.entry_index(sig, np.flatnonzero(mm))
            ent[key] = e[e < n]
        for mode in LIMITS:
            ent[mode] = ent["1"]
        for d in ("L", "S"):
            res = {k: resolve_grid(it.eng, ent[k], d, H) for k in ("1", "nowy") if len(ent[k])}
            for mode in MODES:
                src = "nowy" if mode == "nowy" else "1"
                if src not in res:
                    continue
                r, e = res[src], ent[src]
                rows_all = okol_row(it, e)
                for i in range(len(SL_GRID)):
                    for j in range(len(TP_GRID)):
                        x = r.exit[:, i, j]
                        if mode == "1":
                            k = one_position(e, x)
                        elif mode in LIMITS:
                            k = limit_positions(e, x, LIMITS[mode])
                        else:
                            k = np.arange(len(e))
                        acc.setdefault((mode, d, i, j), []).append({
                            "ret": r.ret[k, i, j] * 100.0 - COST,
                            "reason": r.reason[k, i, j],
                            "row": rows_all[k],
                            "e_ord": it.tord[e[k]], "x_ord": it.tord[x[k]],
                            "pol": it.poletko[e[k]],
                            "x_pol": it.poletko[x[k]],
                            "week": np.array([weeks[it.B.date[t]] for t in e[k]]),
                        })
    return {key: {f: np.concatenate([p[f] for p in parts]) for f in parts[0]} for key, parts in acc.items()}


def _metryki(ret, reason, e_ord, x_ord, rnd, stake) -> dict:
    if len(ret) == 0:
        return {"transakcji": 0, "skutecznosc": None, "ekspektancja": None, "pct_czas": None,
                "max_otwartych": 0, "wynik_portfela": 0.0, "przewaga": None, "srednia_stawka": None}
    return {"transakcji": int(len(ret)), "skutecznosc": float((ret > 0).mean() * 100),
            "ekspektancja": float(ret.mean()), "pct_czas": float((reason >= 2).mean() * 100),
            "max_otwartych": max_concurrent(e_ord, x_ord),
            "wynik_portfela": float((ret / 100.0 * stake).sum()),
            "przewaga": float(ret.mean() - rnd), "srednia_stawka": float(np.mean(stake))}


def _polowa(oc: np.ndarray) -> np.ndarray:
    keep = np.argsort(-oc, kind="stable")[:max(1, len(oc) // 2)]
    keep.sort()
    return keep


def strategia(tr: dict | None, VAL: np.ndarray, DFN: np.ndarray, r_odkr: float, r_pol: float) -> dict:
    """Cztery wersje (U, A, B, C) jednej strategii."""
    pusto = {f"{w}_{m}": (0 if m == "transakcji" or m == "max_otwartych" else
                          (0.0 if m == "wynik_portfela" else None)) for w in WERSJE for m in METRYKI}
    pusto |= {"zysk_filtra_B": None, "zysk_filtra_C": None, "iluzja_C_minus_B": None,
              "ok_mocnych_odkrywanie": 0, "ok_najlepsza_odkrywanie": None, "ok_najlepsza_rating": None,
              "B_uczonych_na": 0}
    if tr is None or len(tr["ret"]) == 0:
        return pusto

    pol = tr["pol"].astype(bool)
    p = pol
    # 5.9 (purging): do nauki ratingu wchodzą tylko transakcje, które CAŁE zmieściły się
    # w odkrywaniu. Transakcja otwarta w odkrywaniu, a zamknięta na poletku, zna już ceny
    # z poletka — trenowanie na niej przeciekałoby do sprawdzianu.
    o = ~pol & ~tr["x_pol"].astype(bool)
    row = dict(pusto)

    def met(mask, rnd, stake, w):
        m = _metryki(tr["ret"][mask], tr["reason"][mask], tr["e_ord"][mask], tr["x_ord"][mask], rnd, stake)
        row.update({f"{w}_{k}": v for k, v in m.items()})
        return m

    u = met(o, r_odkr, np.full(int(o.sum()), 10.0) if o.any() else np.array([10.0]), "U")
    a = met(p, r_pol, np.full(int(p.sum()), 10.0) if p.any() else np.array([10.0]), "A")
    if not p.any():
        return row

    V, D = VAL[tr["row"]], DFN[tr["row"]]
    Vf, F = V.astype(np.float32), (D & ~V).astype(np.float32)

    # B: rating z odkrywania, zastosowany do poletka
    if o.sum() >= 2 * MIN_OBS:
        rt, rn, n_obs = ratingi(Vf[o], F[o], tr["reason"][o])
        oc_p = oceny(Vf[p], F[p], rt, rn)
        keep = _polowa(oc_p)
        idx = np.flatnonzero(p)[keep]
        st = stawki(oc_p[keep])
        b = met(_maska(idx, len(pol)), r_pol, st, "B")
        mocne = rt.copy()
        mocne[n_obs < MIN_OBS] = NEUTRAL
        best = int(np.argmax(mocne))
        row |= {"B_uczonych_na": int(o.sum()),
                "ok_mocnych_odkrywanie": int((np.abs(mocne - NEUTRAL) >= 15).sum()),
                "ok_najlepsza_odkrywanie": okolicznosci.IDS[best],
                "ok_najlepsza_rating": float(mocne[best])}
        row["zysk_filtra_B"] = (None if a["skutecznosc"] is None or b["skutecznosc"] is None
                                else float(b["skutecznosc"] - a["skutecznosc"]))
    # C: rating z samego poletka (D34g) — podziałka, nie sprawdzian
    rt2, rn2, _ = ratingi(Vf[p], F[p], tr["reason"][p])
    oc2 = oceny(Vf[p], F[p], rt2, rn2)
    keep2 = _polowa(oc2)
    idx2 = np.flatnonzero(p)[keep2]
    c = met(_maska(idx2, len(pol)), r_pol, stawki(oc2[keep2]), "C")
    row["zysk_filtra_C"] = (None if a["skutecznosc"] is None or c["skutecznosc"] is None
                            else float(c["skutecznosc"] - a["skutecznosc"]))
    if row["zysk_filtra_B"] is not None and row["zysk_filtra_C"] is not None:
        row["iluzja_C_minus_B"] = row["zysk_filtra_C"] - row["zysk_filtra_B"]
    return row


def _maska(idx: np.ndarray, n: int) -> np.ndarray:
    m = np.zeros(n, dtype=bool)
    m[idx] = True
    return m


def podsumowanie(df: pd.DataFrame) -> dict:
    """Jedna odpowiedź na pytanie „czy okoliczności coś przewidują"."""
    d = df[df.B_transakcji > 0]
    if d.empty:
        return {"strategii": 0}
    return {
        "strategii": int(len(df)),
        "z_transakcjami_na_poletku": int(len(d)),
        "sr_skutecznosc_A_bez_filtra": round(float(d.A_skutecznosc.mean()), 2),
        "sr_skutecznosc_B_filtr_z_odkrywania": round(float(d.B_skutecznosc.mean()), 2),
        "sr_skutecznosc_C_filtr_z_poletka": round(float(d.C_skutecznosc.mean()), 2),
        "sr_zysk_filtra_B_pp": round(float(d.zysk_filtra_B.mean()), 2),
        "sr_zysk_filtra_C_pp": round(float(d.zysk_filtra_C.mean()), 2),
        "sr_iluzja_C_minus_B_pp": round(float(d.iluzja_C_minus_B.mean()), 2),
        "udzial_B_lepsze_od_A_pct": round(float((d.zysk_filtra_B > 0).mean() * 100), 1),
        "sr_ekspektancja_A": round(float(d.A_ekspektancja.mean()), 4),
        "sr_ekspektancja_B": round(float(d.B_ekspektancja.mean()), 4),
        "sr_przewaga_A": round(float(d.A_przewaga.mean()), 4),
        "sr_przewaga_B": round(float(d.B_przewaga.mean()), 4),
        "wniosek": ("Filtr z odkrywania nie przenosi się na poletko — okoliczności nie przewidują "
                    "wyniku na nowych danych (B ≈ A), a cała 'poprawa' z przebiegu 4 to dopasowanie."
                    if float(d.zysk_filtra_B.mean()) < 1.0 else
                    "Filtr z odkrywania daje na poletku poprawę — warto sprawdzić, które okoliczności "
                    "i czy poprawa jest większa niż rozrzut między strategiami."),
    }


def run(cat: dict, frames: dict, spy, symbols: list[str], plot_start: str,
        limit: int | None = None, progress=print) -> tuple[pd.DataFrame, dict]:
    t0 = time.time()
    insts, VAL, DFN = prepare(frames, spy, symbols, plot_start, progress)
    wk = sorted({d for it in insts for d in it.B.date})
    weeks = {d: i for i, d in enumerate(sorted({date.fromisoformat(d).isocalendar()[:2] for d in wk}))}
    weeks = {d: weeks[date.fromisoformat(d).isocalendar()[:2]] for d in wk}
    H = h_matrix()
    r_odkr = random_baseline(insts, H, tylko_poletko=False)
    r_pol = random_baseline(insts, H, tylko_poletko=True)
    todo = [s for s in cat["signals"] if s["status"] in ("aktywny", "kontrolny")]
    if limit:
        todo = todo[:limit]
    rows = []
    for n_sig, sig in enumerate(todo, 1):
        tr = collect(sig, insts, H, weeks)
        for mode in MODES:
            for d in ("L", "S"):
                for i, sl in enumerate(SL_GRID):
                    for j, tp in enumerate(TP_GRID):
                        h = int(H[i, j])
                        row = strategia(tr.get((mode, d, i, j)), VAL, DFN,
                                        float(r_odkr[d][i, j]), float(r_pol[d][i, j]))
                        row |= {"id": strategy_id(sig["code"], d, sl, tp, h, mode), "sygnal": sig["code"],
                                "kategoria": sig["category"], "kierunek": d, "sl": sl, "tp": tp, "h": h,
                                "sl_rowne_tp": sl == tp, "tryb": mode}
                        rows.append(row)
        if n_sig % 5 == 0 or n_sig == len(todo):
            el = time.time() - t0
            progress(f"  {n_sig}/{len(todo)} sygnałów, {el / 60:.1f} min "
                     f"(zostało ok. {el / n_sig * (len(todo) - n_sig) / 60:.1f} min)")
    df = pd.DataFrame(rows)[COLUMNS]
    meta = {"decyzja": "D35", "przebieg": "4 — sprawdzian na poletku",
            "wersje": {"U": "odkrywanie bez filtra (odpowiada b_* z przebiegu 4)",
                       "A": "poletko bez filtra",
                       "B": "poletko, filtr według ratingu Z ODKRYWANIA — właściwy sprawdzian",
                       "C": "poletko, filtr według ratingu z poletka — podziałka (D34g), nie sprawdzian"},
            "catalog_hash": cat["meta"]["content_hash"],
            "okolicznosci_version": okolicznosci.OKOL_VERSION, "okolicznosci_liczba": len(okolicznosci.DEFS),
            "poletko_od": plot_start, "instrumenty": len(insts),
            "purging": "5.9: rating B uczony tylko na transakcjach zamkniętych PRZED poletkiem",
            "stawka": {"min_usd": STAWKA_MIN, "max_usd": STAWKA_MAX}, "cost_pct": COST,
            "zajrzenie_na_poletko": "drugie w Etapie 2 (pierwsze: wycofane D33, L37)",
            "podsumowanie": podsumowanie(df),
            "runtime_min": round((time.time() - t0) / 60, 1),
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "limit": limit}
    return df, meta


def main(argv=None) -> int:
    from . import config, data
    ap = argparse.ArgumentParser(description="Etap 2: sprawdzian przebiegu 4 na poletku (D35).")
    ap.add_argument("--limit", type=int, default=None, help="tylko N pierwszych sygnałów (próba, bez zapisu)")
    ap.add_argument("--wiem-ze-drugie", action="store_true",
                    help="potwierdzenie, że to DRUGIE zajrzenie na poletko w Etapie 2 (5.1, L37)")
    a = ap.parse_args(argv)
    cat = json.loads((catalog.repo_root() / "s1" / "catalog.json").read_text(encoding="utf-8"))
    if catalog.build()["meta"]["content_hash"] != cat["meta"]["content_hash"]:
        print("s1/catalog.json nie zgadza się z kodem — najpierw python3 -m ia4.catalog.")
        return 1
    if not a.limit and not a.wiem_ze_drugie:
        print("To DRUGIE zajrzenie na poletko w Etapie 2 (pierwsze: wycofane D33, luka L37).\n"
              "Zasada 5.1 przewiduje jedno na etap — po tym poletko nie będzie już żadnym\n"
              "sprawdzianem, a jedynym niezależnym testem zostanie skarbiec na końcu Etapu 3.\n"
              "Jeśli to świadoma decyzja: python3 -m ia4.poletko4 --wiem-ze-drugie")
        return 1
    if OUT_META.exists() and not a.limit:
        print(f"{OUT_META.name} już istnieje — ten sprawdzian liczy się raz. Przerwane.")
        return 1
    v = config.vault()
    u = config.universe()
    syms = list(u["main"]) + list(u["proof"])
    print(f"Sprawdzian na poletku ({v.plot_start} – {v.plot_end}), {len(syms)} spółek razem, "
          f"{len(okolicznosci.DEFS)} okoliczności")
    allf = data.load(syms + ["SPY"], period="research", plot_reason=PLOT_REASON)
    frames = {s: allf[allf["symbol"] == s].reset_index(drop=True) for s in syms + ["SPY"]}
    df, meta = run(cat, frames, frames["SPY"], syms, v.plot_start, limit=a.limit)
    if a.limit:
        print(df.head(12).to_string())
        print(json.dumps(meta["podsumowanie"], ensure_ascii=False, indent=1))
        print("Próba (--limit): nic nie zapisano.")
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False, float_format="%.4f")
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    s = meta["podsumowanie"]
    print(f"\nPoletko, {s['z_transakcjami_na_poletku']} strategii z transakcjami:")
    print(f"  bez filtra (A):                  skuteczność {s['sr_skutecznosc_A_bez_filtra']}%")
    print(f"  filtr z odkrywania (B):          skuteczność {s['sr_skutecznosc_B_filtr_z_odkrywania']}%  "
          f"({s['sr_zysk_filtra_B_pp']:+} pp)   ← sprawdzian")
    print(f"  filtr z samego poletka (C):      skuteczność {s['sr_skutecznosc_C_filtr_z_poletka']}%  "
          f"({s['sr_zysk_filtra_C_pp']:+} pp)   ← podziałka, nie wynik")
    print(f"  sama iluzja (C − B):             {s['sr_iluzja_C_minus_B_pp']:+} pp")
    print(f"  B lepsze od A u {s['udzial_B_lepsze_od_A_pct']}% strategii (przypadkiem ok. 50%)")
    print(f"\n{s['wniosek']}")
    print("\nTeraz: cd .. && git add s2 ia4-research/poletko_zajrzenia.jsonl && "
          "git commit -m 'Sprawdzian przebiegu 4 na poletku (D35)' && git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
