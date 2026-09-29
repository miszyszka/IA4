"""
IA 4 — backtest S1, przebieg 4: okoliczności, rating, lepsza połowa, zmienna stawka (D34).
Wersja projektu: 0.47 (2026-09-29) — musi zgadzać się z IA4_INSTRUKCJA.md

Dla każdej strategii (sygnał × kierunek × SL × TP × tryb):

  1. liczy wszystkie transakcje na okresie odkrywania, wszystkie spółki razem
     (D34e: główne i kontrolne w jednym worku),
  2. dla każdej transakcji zapisuje 231 okoliczności (`ia4/okolicznosci.py`)
     z ostatniej ZAMKNIĘTEJ świecy przed wejściem,
  3. każdej okoliczności nadaje rating 0–100 = odsetek TP wśród transakcji,
     w których miała daną wartość (0 = zawsze SL, 100 = zawsze TP, 50 = nic nie
     wnosi). Osobno dla wartości TAK i NIE. Przy mniej niż `MIN_OBS`
     obserwacjach rating wynosi 50 — za mało danych, żeby cokolwiek twierdzić,
  4. każdej transakcji daje ocenę = średnią z ratingów tych okoliczności, które
     dało się dla niej policzyć (wartość TAK bierze rating TAK, NIE — rating NIE),
  5. zostawia LEPSZĄ POŁOWĘ transakcji według tej oceny i liczy wynik jeszcze raz,
     tak jakby strategia wchodziła tylko w nie,
  6. stawka nie jest stała: od 10 $ przy najsłabszej ocenie w tej połowie do
     100 $ przy najlepszej (liniowo).

**Rating jest liczony z tych samych transakcji, które potem są filtrowane** —
świadoma decyzja użytkownika (D34, 2026-09-29), mimo luki L38. To znaczy, że
kolumny `f_*` są z definicji zawyżone i NIE są oszacowaniem przyszłego wyniku;
są miarą tego, ile da się wycisnąć z okoliczności, gdy zna się wynik. Kolumny
`b_*` (przed filtrem) to jedyne liczby w tym pliku, które da się porównywać
z przebiegiem 3. Sprawdzian na niewidzianych danych jest dopiero przed nami —
patrz L37 i L38.

    python3 -m ia4.przebieg4 --limit 3   # próba na 3 sygnałach, nic nie zapisuje
    python3 -m ia4.przebieg4             # całość: 24 600 strategii
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
from .backtest import (BOOT_B, LIMITS, MODES, SEED, SL_GRID, START_CAPITAL, TP_GRID,
                       bh_qvalues, bootstrap_p, h_matrix, limit_positions, max_concurrent,
                       new_signal_only, strategy_id)
from .engine import Engine, one_position, resolve_grid

OUT_DIR = catalog.repo_root() / "s1-backtest"
STAWKA_MIN = 10.0            # D34: najsłabsza ocena w wybranej połowie
STAWKA_MAX = 100.0           # D34: najlepsza ocena
MIN_OBS = 10                 # mniej obserwacji = rating 50 (nic nie wiadomo)
NEUTRAL = 50.0
COST = 0.0                   # D32: bez kosztów
FDR_Q = 0.10
PRIOR_TRIALS = 92_870        # licznik 5.7 po przebiegu 3


class Inst:
    __slots__ = ("symbol", "grupa", "B", "eng", "tord", "week", "off", "poletko")

    def __init__(self, symbol, grupa, B, eng, tord, week, off):
        self.symbol, self.grupa, self.B, self.eng = symbol, grupa, B, eng
        self.tord, self.week, self.off = tord, week, off


def prepare(frames: dict, spy, groups: dict, progress=print) -> tuple[list[Inst], int, np.ndarray, np.ndarray]:
    """Świece, silniki i macierze okoliczności wszystkich instrumentów, sklejone w jedną tablicę.

    Wiersz 0 sklejonej tablicy jest pusty (same „nie do policzenia") i służy za
    zaślepkę dla transakcji, przed którymi nie ma zamkniętej świecy.
    """
    weeks = sorted({date.fromisoformat(d).isocalendar()[:2] for df in frames.values() for d in df["date"].unique()})
    widx = {w: i for i, w in enumerate(weeks)}
    M = len(okolicznosci.DEFS)
    vals = [np.zeros((1, M), dtype=bool)]
    dfns = [np.zeros((1, M), dtype=bool)]
    out, off = [], 1
    for g, syms in groups.items():
        for s in syms:
            if s not in frames or frames[s].empty:
                continue
            B = bars.prepare(frames[s], market=spy)
            v, d = okolicznosci.evaluate(B)
            vals.append(v)
            dfns.append(d)
            tord = np.array([nyse.ordinal(x) for x in B.date]) * 8 + B.slot
            week = np.array([widx[date.fromisoformat(x).isocalendar()[:2]] for x in B.date])
            out.append(Inst(s, g, B, Engine(B, sl_grid=SL_GRID, tp_grid=TP_GRID), tord, week, off))
            off += B.n
            if len(out) % 10 == 0:
                progress(f"  okoliczności: {len(out)} instrumentów")
    return out, len(weeks), np.vstack(vals), np.vstack(dfns)


def okol_row(it: Inst, e: np.ndarray) -> np.ndarray:
    """Wiersz okoliczności dla wejścia na świecy e: ostatnia ZAMKNIĘTA świeca, czyli e−1.

    Dla wejścia NEXT_OPEN to dokładnie świeca sygnału. Dla SESSION_OPEN (wejście
    na otwarciu świecy sygnału) to świeca wcześniejsza — inaczej okoliczność
    liczona z zamknięcia tej samej świecy znałaby przyszłość.
    """
    prev = e - 1
    start = it.B.seg_start[e]                       # początek odcinka między splitami
    ok = (prev >= start) & ~it.B.hole_before[e]
    return np.where(ok, it.off + prev, 0)


def random_baseline(insts: list[Inst], H: np.ndarray) -> dict:
    """5.3: średni wynik [%] wejścia w każdą świecę, per kierunek (wszystkie spółki razem)."""
    out = {}
    for d in ("L", "S"):
        tot, cnt = np.zeros(H.shape), 0
        for it in insts:
            r = resolve_grid(it.eng, np.arange(it.B.n), d, H)
            tot += r.ret.sum(axis=0)
            cnt += r.ret.shape[0]
        out[d] = (tot / max(cnt, 1)) * 100.0 - COST
    return out


def collect(sig: dict, insts: list[Inst], H: np.ndarray) -> dict:
    """Transakcje strategii, wszystkie spółki razem; zapisane też wiersze okoliczności."""
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
        glowna = it.grupa == "main"
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
                            "e_ord": it.tord[e[k]], "x_ord": it.tord[x[k]], "week": it.week[e[k]],
                            "glowna": np.full(len(k), glowna),
                        })
    return {key: {f: np.concatenate([p[f] for p in parts]) for f in parts[0]} for key, parts in acc.items()}


def ratingi(Vf: np.ndarray, F: np.ndarray, reason: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Rating każdej okoliczności, osobno dla wartości TAK i NIE.

    rating = 100 × TP / (TP + SL) wśród transakcji, w których okoliczność miała
    tę wartość. Wyjścia z limitu czasu (TIME, END) nie są ani TP, ani SL, więc
    nie wchodzą do mianownika. Mniej niż MIN_OBS obserwacji → 50.
    Zwraca też liczbę obserwacji (TAK), żeby dało się odsiać ratingi „z niczego".
    """
    tp = (reason == 1).astype(np.float32)
    sl = (reason == 0).astype(np.float32)
    t_tak, s_tak = Vf.T @ tp, Vf.T @ sl
    t_nie, s_nie = F.T @ tp, F.T @ sl
    n_tak, n_nie = t_tak + s_tak, t_nie + s_nie
    with np.errstate(invalid="ignore", divide="ignore"):
        r_tak = np.where(n_tak >= MIN_OBS, 100.0 * t_tak / np.maximum(n_tak, 1), NEUTRAL)
        r_nie = np.where(n_nie >= MIN_OBS, 100.0 * t_nie / np.maximum(n_nie, 1), NEUTRAL)
    return r_tak.astype(np.float32), r_nie.astype(np.float32), n_tak + n_nie


def oceny(Vf: np.ndarray, F: np.ndarray, r_tak: np.ndarray, r_nie: np.ndarray) -> np.ndarray:
    """Ocena transakcji = średnia z ratingów okoliczności, które dało się dla niej policzyć."""
    suma = Vf @ r_tak + F @ r_nie
    ile = (Vf + F).sum(axis=1)
    return np.where(ile > 0, suma / np.maximum(ile, 1), NEUTRAL)


def stawki(ocena: np.ndarray) -> np.ndarray:
    """D34: od STAWKA_MIN przy najsłabszej ocenie w zestawie do STAWKA_MAX przy najlepszej."""
    lo, hi = float(ocena.min()), float(ocena.max())
    if hi - lo < 1e-9:
        return np.full(len(ocena), STAWKA_MIN)
    return STAWKA_MIN + (STAWKA_MAX - STAWKA_MIN) * (ocena - lo) / (hi - lo)


def _metryki(ret, reason, e_ord, x_ord, rnd, stake) -> dict:
    if len(ret) == 0:
        return {"transakcji": 0, "skutecznosc": None, "ekspektancja": None, "pct_czas": None,
                "max_otwartych": 0, "wynik_portfela": 0.0, "przewaga": None}
    return {"transakcji": int(len(ret)),
            "skutecznosc": float((ret > 0).mean() * 100),
            "ekspektancja": float(ret.mean()),
            "pct_czas": float((reason >= 2).mean() * 100),
            "max_otwartych": max_concurrent(e_ord, x_ord),
            "wynik_portfela": float((ret / 100.0 * stake).sum()),
            "przewaga": float(ret.mean() - rnd)}


COLUMNS = (
    ["id", "sygnal", "kategoria", "kierunek", "sl", "tp", "h", "sl_rowne_tp", "tryb"]
    + [f"b_{c}" for c in ("transakcji", "skutecznosc", "ekspektancja", "pct_czas",
                          "max_otwartych", "wynik_portfela", "przewaga")]
    + [f"f_{c}" for c in ("transakcji", "skutecznosc", "ekspektancja", "pct_czas",
                          "max_otwartych", "wynik_portfela", "przewaga")]
    + ["f_srednia_stawka", "f_kapital", "f_zysk_na_100", "f_poprawa_skutecznosci", "f_poprawa_ekspektancji"]
    + ["ok_policzalnych", "ok_mocnych", "ok_prog_polowy", "ok_rozrzut",
       "ok_najlepsza", "ok_najlepsza_rating", "ok_najgorsza", "ok_najgorsza_rating"]
    + ["f_eksp_glowne", "f_eksp_kontrolne", "f_p", "f_q_fdr"]
)


def strategia(tr: dict, VAL: np.ndarray, DFN: np.ndarray, rnd: float, W: int
              ) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Kolumny jednej strategii + tygodniowe sumy wyniku po filtrze (do bootstrapu) + ratingi."""
    M = len(okolicznosci.DEFS)
    S, N = np.zeros(W), np.zeros(W)
    pusta = ({c: None for c in COLUMNS if c not in ("b_transakcji", "f_transakcji", "b_max_otwartych",
                                                    "f_max_otwartych", "b_wynik_portfela", "f_wynik_portfela")}
             | {"b_transakcji": 0, "f_transakcji": 0, "b_max_otwartych": 0, "f_max_otwartych": 0,
                "b_wynik_portfela": 0.0, "f_wynik_portfela": 0.0})
    if tr is None or len(tr["ret"]) == 0:
        return pusta, S, N, np.full(M, NEUTRAL, np.float32), np.full(M, NEUTRAL, np.float32)

    ret, reason, rows = tr["ret"], tr["reason"], tr["row"]
    V, D = VAL[rows], DFN[rows]
    Vf = V.astype(np.float32)                      # raz, używane i przy ratingu, i przy ocenie
    F = (D & ~V).astype(np.float32)
    r_tak, r_nie, n_obs = ratingi(Vf, F, reason)
    oc = oceny(Vf, F, r_tak, r_nie)

    baza = _metryki(ret, reason, tr["e_ord"], tr["x_ord"], rnd, np.full(len(ret), 10.0))

    n_keep = max(1, len(oc) // 2)                       # D34: lepsza POŁOWA
    keep = np.argsort(-oc, kind="stable")[:n_keep]
    keep.sort()
    prog = float(oc[keep].min())
    st = stawki(oc[keep])
    filtr = _metryki(ret[keep], reason[keep], tr["e_ord"][keep], tr["x_ord"][keep], rnd, st)

    wkl = ret[keep] / 100.0 * st
    S = np.bincount(tr["week"][keep], weights=wkl / st.mean(), minlength=W).astype(float)
    N = np.bincount(tr["week"][keep], minlength=W).astype(float)

    mocne = r_tak.copy()
    mocne[n_obs < MIN_OBS] = NEUTRAL
    best, worst = int(np.argmax(mocne)), int(np.argmin(mocne))
    g = tr["glowna"][keep]
    row = {f"b_{k}": v for k, v in baza.items()}
    row |= {f"f_{k}": v for k, v in filtr.items()}
    row |= {
        "f_srednia_stawka": float(st.mean()),
        "f_kapital": float(st.sum()),
        "f_zysk_na_100": float(filtr["wynik_portfela"] / st.sum() * 100) if st.sum() else None,
        "f_poprawa_skutecznosci": (None if baza["skutecznosc"] is None
                                   else float(filtr["skutecznosc"] - baza["skutecznosc"])),
        "f_poprawa_ekspektancji": (None if baza["ekspektancja"] is None
                                   else float(filtr["ekspektancja"] - baza["ekspektancja"])),
        "ok_policzalnych": int((D.sum(axis=0) > 0).sum()),
        "ok_mocnych": int((np.abs(mocne - NEUTRAL) >= 15).sum()),
        "ok_prog_polowy": prog,
        "ok_rozrzut": float(mocne.std()),
        "ok_najlepsza": okolicznosci.IDS[best], "ok_najlepsza_rating": float(mocne[best]),
        "ok_najgorsza": okolicznosci.IDS[worst], "ok_najgorsza_rating": float(mocne[worst]),
        "f_eksp_glowne": float(ret[keep][g].mean()) if g.any() else None,
        "f_eksp_kontrolne": float(ret[keep][~g].mean()) if (~g).any() else None,
    }
    return row, S, N, r_tak, r_nie


def run(cat: dict, frames: dict, spy, groups: dict, boot: int = BOOT_B, seed: int = SEED,
        limit: int | None = None, progress=print) -> tuple[pd.DataFrame, dict, dict]:
    t0 = time.time()
    insts, W, VAL, DFN = prepare(frames, spy, groups, progress)
    H = h_matrix()
    rnd = random_baseline(insts, H)
    todo = [s for s in cat["signals"] if s["status"] in ("aktywny", "kontrolny")]
    if limit:
        todo = todo[:limit]
    rows, Sk, Nk, Rk, RT, RN = [], [], [], [], [], []
    for n_sig, sig in enumerate(todo, 1):
        tr = collect(sig, insts, H)
        for mode in MODES:
            for d in ("L", "S"):
                for i, sl in enumerate(SL_GRID):
                    for j, tp in enumerate(TP_GRID):
                        h = int(H[i, j])
                        r0 = float(rnd[d][i, j])
                        row, Sw, Nw, rt, rn = strategia(tr.get((mode, d, i, j)), VAL, DFN, r0, W)
                        row |= {"id": strategy_id(sig["code"], d, sl, tp, h, mode), "sygnal": sig["code"],
                                "kategoria": sig["category"], "kierunek": d, "sl": sl, "tp": tp, "h": h,
                                "sl_rowne_tp": sl == tp, "tryb": mode}
                        rows.append(row)
                        Sk.append(Sw); Nk.append(Nw); Rk.append(r0)
                        RT.append(rt); RN.append(rn)
        if n_sig % 5 == 0 or n_sig == len(todo):
            el = time.time() - t0
            progress(f"  {n_sig}/{len(todo)} sygnałów, {el / 60:.1f} min "
                     f"(zostało ok. {el / n_sig * (len(todo) - n_sig) / 60:.1f} min)")
    df = pd.DataFrame(rows)
    p = bootstrap_p(np.array(Sk), np.array(Nk), np.array(Rk), boot, seed)
    m_total = PRIOR_TRIALS + len(df)
    df["f_p"] = p
    df["f_q_fdr"] = bh_qvalues(p, m_total)
    df = df[COLUMNS]
    meta = {
        "przebieg": 4, "decisions": ["D30", "D32", "D34"],
        "catalog_version": cat["meta"]["catalog_version"], "catalog_hash": cat["meta"]["content_hash"],
        "okolicznosci_version": okolicznosci.OKOL_VERSION, "okolicznosci_liczba": len(okolicznosci.DEFS),
        "period": "discovery", "grupy_razem": True,
        "instrumenty": [it.symbol for it in insts],
        "sl_grid_pct": SL_GRID, "tp_grid_pct": TP_GRID, "modes": MODES, "mode_limits": LIMITS,
        "h_rule": "D5: TP 1% → 14, 2% → 35, 3% → 70 świec",
        "rating": {"wzor": "100 × TP / (TP + SL) wśród transakcji z daną wartością okoliczności",
                   "min_obs": MIN_OBS, "neutralny": NEUTRAL,
                   "uwaga": "D34: rating liczony z TYCH SAMYCH transakcji, które potem są filtrowane "
                            "(L38) — kolumny f_* są z definicji zawyżone i nie są prognozą"},
        "filtr": "lepsza połowa transakcji według średniej oceny okoliczności",
        "stawka": {"min_usd": STAWKA_MIN, "max_usd": STAWKA_MAX,
                   "zasada": "liniowo od najsłabszej do najlepszej oceny w wybranej połowie"},
        "start_capital_usd": START_CAPITAL, "cost_pct": COST,
        "strategies_computed": int(len(df)), "trials_counter_after": m_total,
        "bootstrap": {"B": boot, "seed": seed, "block": "tydzień ISO wejścia", "weeks": W},
        "fdr_q": FDR_Q, "fdr_pass": int((df["f_q_fdr"] <= FDR_Q).sum()),
        "runtime_min": round((time.time() - t0) / 60, 1),
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "limit": limit,
    }
    ratingi_out = {"id": df["id"].to_numpy().astype("U"), "okolicznosci": np.array(okolicznosci.IDS, dtype="U"),
                   "rating_tak": np.round(np.vstack(RT)).astype(np.uint8),
                   "rating_nie": np.round(np.vstack(RN)).astype(np.uint8)}
    return df, meta, ratingi_out


def write(df: pd.DataFrame, meta: dict, rat: dict, out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "results.csv", index=False, float_format="%.4f")
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    np.savez_compressed(out_dir / "ratingi.npz", **rat)
    with (out_dir / "runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({k: meta[k] for k in ("computed_at", "przebieg", "catalog_hash", "decisions",
                                                 "okolicznosci_version", "strategies_computed",
                                                 "trials_counter_after", "fdr_pass", "runtime_min")},
                           ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    from . import config, data
    ap = argparse.ArgumentParser(description="Etap 2, przebieg 4: okoliczności i lepsza połowa sygnałów (D34).")
    ap.add_argument("--limit", type=int, default=None, help="tylko N pierwszych sygnałów (próba, bez zapisu)")
    ap.add_argument("--boot", type=int, default=BOOT_B)
    a = ap.parse_args(argv)
    cat = json.loads((catalog.repo_root() / "s1" / "catalog.json").read_text(encoding="utf-8"))
    if not cat["meta"].get("frozen_at"):
        print("Katalog S1 nie jest zamrożony (1.5).")
        return 1
    if catalog.build()["meta"]["content_hash"] != cat["meta"]["content_hash"]:
        print("s1/catalog.json nie zgadza się z kodem katalogu — najpierw python3 -m ia4.catalog.")
        return 1
    ok_path = catalog.repo_root() / "s1" / "okolicznosci.json"
    if [o["id"] for o in json.loads(ok_path.read_text(encoding="utf-8"))["okolicznosci"]] != okolicznosci.IDS:
        print("s1/okolicznosci.json nie zgadza się z kodem — najpierw python3 -m ia4.okolicznosci.")
        return 1
    u = config.universe()
    groups = {"main": list(u["main"]), "control": list(u["proof"])}
    syms = groups["main"] + groups["control"]
    print(f"Etap 2, przebieg 4 (D34): katalog {cat['meta']['catalog_version']} ({cat['meta']['content_hash']}), "
          f"{len(okolicznosci.DEFS)} okoliczności, {len(syms)} spółek razem, okres odkrywania")
    frames = {s: data.load(s) for s in syms}
    spy = data.load("SPY")
    df, meta, rat = run(cat, frames, spy, groups, boot=a.boot, limit=a.limit)
    if a.limit:
        print(df.head(12).to_string())
        print(json.dumps({k: v for k, v in meta.items() if k != "instrumenty"}, ensure_ascii=False, indent=1))
        print("Próba (--limit): nic nie zapisano.")
        return 0
    write(df, meta, rat)
    print(f"Zapisano {OUT_DIR / 'results.csv'}: {len(df)} strategii, {meta['runtime_min']} min; "
          f"FDR 10%: {meta['fdr_pass']}")
    print(f"Ratingi wszystkich okoliczności: {OUT_DIR / 'ratingi.npz'}")
    print("Teraz: cd .. && git add s1-backtest && git commit -m 'Backtest S1 D34' && git push, "
          "potem w arkuszu: Wczytaj wyniki S1-BACKTEST.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
