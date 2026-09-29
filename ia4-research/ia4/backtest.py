"""
IA 4 — backtest S1 (Etap 2, instrukcja 2.1–2.3; sposób liczenia: D29 → D30, D31 → D32).
Wersja projektu: 0.45 (2026-09-29) — musi zgadzać się z IA4_INSTRUKCJA.md

Liczy strategie z zamrożonego katalogu S1 na okresie ODKRYWANIA (5.1 — poletko
i skarbiec nietknięte), osobno dla grupy głównej i kontrolnej (5.6), i zapisuje
`s1-backtest/results.csv` — jeden wiersz na strategię, dla arkusza S1-BACKTEST.

D32 (2026-09-29, trzeci przebieg — zmienia w D31 tylko trzy rzeczy):
  - siatka SL: 1, 2, 3, 4, 5%; siatka TP bez zmian: 1, 2, 3% (15 par);
  - czwarty tryb pozycji: "10" — najwyżej 10 pozycji naraz na jednej spółce;
  - bez kosztów transakcyjnych (5.5: wynik główny bez kosztów). Przewaga i p
    się od tego nie zmieniają — koszt odejmowano tak samo od strategii i od
    wejścia losowego — przesuwają się tylko ekspektancja, skuteczność i wynik $.
    Próg 5.11 (ekspektancja PO kosztach ≥ 0,05%) sprawdza się przy wyborze S2.

D31 (2026-09-29, drugi przebieg — uproszczenie na życzenie użytkownika):
  - siatka SL i TP: 1%, 2%, 3% (9 par), H stałe z D5: TP 1% → 14 świec,
    2% → 35, 3% → 70;
  - trzy tryby pozycji na jednej spółce (kolumna `tryb`):
      "1"     — jedna pozycja naraz (kontrakt silnika pkt 8, jak w przebiegu 1),
      "5"     — najwyżej 5 pozycji tej strategii naraz na jednej spółce,
      "nowy"  — bez limitu, ale wejście tylko na NOWYM sygnale: na świecy, w której
                sygnał pojawia się po świecy bez sygnału (poziomowe sygnały, np.
                „zamknięcie pod wstęgą”, nie dokładają wejść świeca po świecy);
  - portfel: 100 000 $ na start, każda transakcja za 10 $, bez limitu gotówki
    (może zejść poniżej zera — na kredyt); koszt 0,05% za transakcję (5.5)
    wliczony we WSZYSTKIE wyniki (skuteczność, ekspektancja, wynik portfela);
  - transakcje otwarte na końcu okresu zamykane po zamknięciu ostatniej świecy
    (30.09.2025) i wliczane — nie usuwane (ceny wyłącznie z odkrywania);
  - wejście losowe (5.3): wejście na otwarciu każdej świecy, te same SL/TP/H,
    po kosztach; przewaga = ekspektancja − losowe;
  - D30: p z tygodniowego bootstrapu blokowego (B = 2000) przez przybliżenie
    normalne: z = przewaga / błąd standardowy z bootstrapu, p = 1 − Φ(z).
    FDR Benjaminiego–Hochberga (10%) na p grupy kontrolnej, liczony na
    wszystkich próbach z licznika 5.7 (57 200 z przebiegu 1 + ten przebieg).

    python3 -m ia4.backtest --limit 3    # próba na 3 sygnałach, nic nie zapisuje
    python3 -m ia4.backtest              # całość
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
import sys
import time
import warnings
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import bars, catalog, nyse, signals
from .engine import Engine, h_default, one_position, resolve_grid

OUT_DIR = catalog.repo_root() / "s1-backtest"
SL_GRID = [1, 2, 3, 4, 5]            # D32
TP_GRID = [1, 2, 3]                  # D31
MODES = ["1", "5", "10", "nowy"]     # D32
LIMITS = {"5": 5, "10": 10}          # tryby z limitem pozycji naraz na jednej spółce
COST = 0.0                           # D32: bez kosztów (5.5); przebieg 2 liczył 0,05
START_CAPITAL = 100_000.0            # D31: tylko informacyjnie — brak limitu gotówki
STAKE = 10.0                         # D31: $ na transakcję
BOOT_B = 2000
SEED = 20260928
FDR_Q = 0.10
PRIOR_TRIALS = 68_270                # licznik 5.7 przed tym przebiegiem (57 200 + 11 070 z przebiegu 2)
GROUPS = {"main": "gl", "control": "kontr"}


@dataclass
class Inst:
    symbol: str
    group: str
    B: bars.Bars
    eng: Engine
    tord: np.ndarray          # wspólny porządek czasowy świec
    week: np.ndarray          # numer tygodnia ISO w okresie


def prepare(frames: dict, spy, groups: dict) -> tuple[list[Inst], int]:
    weeks = sorted({date.fromisoformat(d).isocalendar()[:2] for df in frames.values() for d in df["date"].unique()})
    widx = {w: i for i, w in enumerate(weeks)}
    out = []
    for g, syms in groups.items():
        for s in syms:
            if s not in frames or frames[s].empty:
                continue
            B = bars.prepare(frames[s], market=spy)
            tord = np.array([nyse.ordinal(d) for d in B.date]) * 8 + B.slot
            week = np.array([widx[date.fromisoformat(d).isocalendar()[:2]] for d in B.date])
            out.append(Inst(s, g, B, Engine(B, sl_grid=SL_GRID, tp_grid=TP_GRID), tord, week))
    return out, len(weeks)


def h_matrix() -> np.ndarray:
    """D5 (D31): H zależy tylko od TP. Wiersze = SL, kolumny = TP."""
    return np.array([[h_default(tp) for tp in TP_GRID] for _ in SL_GRID], dtype=np.int64)


def random_baseline(insts: list[Inst], H: np.ndarray) -> dict:
    """5.3: średni wynik [%] (minus COST) wejścia w każdą świecę, per (grupa, kierunek) → macierz SL × TP."""
    out = {}
    for g in GROUPS:
        for d in ("L", "S"):
            tot = np.zeros(H.shape)
            cnt = 0
            for it in insts:
                if it.group != g:
                    continue
                r = resolve_grid(it.eng, np.arange(it.B.n), d, H)
                tot += r.ret.sum(axis=0)
                cnt += r.ret.shape[0]
            out[(g, d)] = (tot / max(cnt, 1)) * 100.0 - COST
    return out


def limit_positions(entries: np.ndarray, exits: np.ndarray, k: int) -> np.ndarray:
    """Najwyżej k pozycji naraz na jednej spółce: pozycja zajmuje świece [wejście, wyjście]."""
    open_exits: list[int] = []
    keep = []
    for idx, (e, x) in enumerate(zip(entries.tolist(), exits.tolist())):
        while open_exits and open_exits[0] < e:
            heapq.heappop(open_exits)
        if len(open_exits) < k:
            heapq.heappush(open_exits, x)
            keep.append(idx)
    return np.array(keep, dtype=np.int64)


def new_signal_only(mask: np.ndarray) -> np.ndarray:
    """Tryb „nowy”: sygnał na t, a na t−1 go nie było."""
    prev = np.zeros_like(mask)
    prev[1:] = mask[:-1]
    return mask & ~prev


def _entries(mask: np.ndarray, sig: dict, n: int) -> np.ndarray:
    e = signals.entry_index(sig, np.flatnonzero(mask))
    return e[e < n]


def _collect(sig: dict, insts: list[Inst], H: np.ndarray) -> dict:
    """Transakcje każdej strategii (tryb, kierunek, SL, TP) w każdej grupie — portfel chronologiczny."""
    acc: dict = {}
    for it in insts:
        m = signals.mask(sig, it.B)
        ent = {"1": _entries(m, sig, it.B.n), "nowy": _entries(new_signal_only(m), sig, it.B.n)}
        for mode in LIMITS:
            ent[mode] = ent["1"]
        for d in ("L", "S"):
            res = {}
            for key in ("1", "nowy"):
                if len(ent[key]):
                    res[key] = resolve_grid(it.eng, ent[key], d, H)
            for mode in MODES:
                src = "nowy" if mode == "nowy" else "1"
                if src not in res:
                    continue
                r, e = res[src], ent[src]
                for i in range(len(SL_GRID)):
                    for j in range(len(TP_GRID)):
                        x = r.exit[:, i, j]
                        if mode == "1":
                            k = one_position(e, x)
                        elif mode in LIMITS:
                            k = limit_positions(e, x, LIMITS[mode])
                        else:
                            k = np.arange(len(e))
                        acc.setdefault((it.group, mode, d, i, j), []).append({
                            "ret": r.ret[k, i, j] * 100.0 - COST,
                            "reason": r.reason[k, i, j],
                            "e_ord": it.tord[e[k]], "x_ord": it.tord[x[k]], "week": it.week[e[k]],
                        })
    return {key: {f: np.concatenate([p[f] for p in parts]) for f in parts[0]} for key, parts in acc.items()}


def max_concurrent(e_ord: np.ndarray, x_ord: np.ndarray) -> int:
    """Najwięcej pozycji otwartych naraz: przedziały [wejście, wyjście] włącznie."""
    if len(e_ord) == 0:
        return 0
    t = np.concatenate([e_ord, x_ord + 1])
    d = np.concatenate([np.ones(len(e_ord), int), -np.ones(len(x_ord), int)])
    order = np.lexsort((d, t))
    return int(np.max(np.cumsum(d[order])))


def metrics(tr: dict | None, rnd: float, n_weeks: int) -> tuple[dict, np.ndarray, np.ndarray]:
    """Kolumny D31 dla jednej strategii w jednej grupie (wyniki minus COST — w D32 zero)."""
    S, N = np.zeros(n_weeks), np.zeros(n_weeks)
    if tr is None or len(tr["ret"]) == 0:
        return {"transakcji": 0, "skutecznosc": None, "ekspektancja": None, "pct_czas": None,
                "max_otwartych": 0, "wynik_portfela": 0.0, "przewaga": None}, S, N
    r = tr["ret"]
    m = {
        "transakcji": int(len(r)),
        "skutecznosc": float((r > 0).mean() * 100),
        "ekspektancja": float(r.mean()),
        "pct_czas": float((tr["reason"] >= 2).mean() * 100),       # czas albo koniec okresu
        "max_otwartych": max_concurrent(tr["e_ord"], tr["x_ord"]),
        "wynik_portfela": float(r.sum() / 100.0 * STAKE),
        "przewaga": float(r.mean() - rnd),
    }
    S = np.bincount(tr["week"], weights=r, minlength=n_weeks).astype(float)
    N = np.bincount(tr["week"], minlength=n_weeks).astype(float)
    return m, S, N


def bootstrap_p(S: np.ndarray, N: np.ndarray, rnd: np.ndarray, B: int = BOOT_B, seed: int = SEED,
                chunk: int = 2000) -> np.ndarray:
    """
    D30: blokowy bootstrap po tygodniach (5.10) daje błąd standardowy średniej; p z
    przybliżenia normalnego, jednostronnie dla H0: przewaga ≤ 0. W przeciwieństwie
    do liczenia trafień w B losowaniach (D29, najmniejsze p = 1/(B+1)) pozwala na p
    na tyle małe, żeby kontrola wielu testów w ogóle mogła coś przepuścić (L36).
    """
    K, W = S.shape
    rng = np.random.default_rng(seed)
    C = rng.multinomial(W, np.full(W, 1.0 / W), size=B).astype(float)
    ntot = N.sum(axis=1)
    mhat = np.where(ntot > 0, S.sum(axis=1) / np.maximum(ntot, 1), np.nan)
    se = np.full(K, np.nan)
    for a in range(0, K, chunk):
        b = min(K, a + chunk)
        with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)          # strategie bez transakcji
            mstar = (C @ S[a:b].T) / (C @ N[a:b].T)
            se[a:b] = np.nanstd(mstar, axis=0, ddof=1)
    z = (mhat - rnd) / se
    p = np.array([0.5 * math.erfc(v / math.sqrt(2)) if np.isfinite(v) else 1.0 for v in z])
    p[~(ntot > 0)] = 1.0
    return p


def bh_qvalues(p: np.ndarray, m_total: int) -> np.ndarray:
    """Benjamini–Hochberg; m_total = wszystkie próby z licznika (niepoliczone mają p = 1)."""
    n = len(p)
    if n == 0:
        return p
    order = np.argsort(p)
    q = p[order] * m_total / np.arange(1, n + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(q, 1.0)
    return out


def strategy_id(code: str, d: str, sl, tp, H: int, mode: str) -> str:
    return f"{code}__{d}__SL{catalog.code_num(sl)}_TP{catalog.code_num(tp)}_H{H}__{mode}"


COLUMNS = (["id", "sygnal", "kategoria", "kierunek", "sl", "tp", "h", "sl_rowne_tp", "tryb"]
           + [f"{pre}_{c}" for pre in GROUPS.values() for c in
              ("transakcji", "skutecznosc", "ekspektancja", "pct_czas", "max_otwartych", "wynik_portfela", "przewaga")]
           + ["kontr_q_fdr"])


def run(cat: dict, frames: dict, spy, groups: dict, boot: int = BOOT_B, seed: int = SEED,
        limit: int | None = None, progress=print) -> tuple[pd.DataFrame, dict]:
    t0 = time.time()
    insts, W = prepare(frames, spy, groups)
    H = h_matrix()
    rnd = random_baseline(insts, H)
    todo = [s for s in cat["signals"] if s["status"] in ("aktywny", "kontrolny")]
    if limit:
        todo = todo[:limit]
    rows, S_k, N_k, R_k = [], [], [], []
    for n_sig, sig in enumerate(todo, 1):
        tr = _collect(sig, insts, H)
        for mode in MODES:
            for d in ("L", "S"):
                for i, sl in enumerate(SL_GRID):
                    for j, tp in enumerate(TP_GRID):
                        h = int(H[i, j])
                        row = {"id": strategy_id(sig["code"], d, sl, tp, h, mode), "sygnal": sig["code"],
                               "kategoria": sig["category"], "kierunek": d, "sl": sl, "tp": tp, "h": h,
                               "sl_rowne_tp": sl == tp, "tryb": mode}
                        for g, pre in GROUPS.items():
                            r0 = float(rnd[(g, d)][i, j])
                            m, Sw, Nw = metrics(tr.get((g, mode, d, i, j)), r0, W)
                            row.update({f"{pre}_{k}": v for k, v in m.items()})
                            if g == "control":
                                S_k.append(Sw); N_k.append(Nw); R_k.append(r0)
                        rows.append(row)
        if n_sig % 10 == 0 or n_sig == len(todo):
            el = time.time() - t0
            progress(f"  {n_sig}/{len(todo)} sygnałów, {el / 60:.1f} min "
                     f"(zostało ok. {el / n_sig * (len(todo) - n_sig) / 60:.1f} min)")
    df = pd.DataFrame(rows)
    p = bootstrap_p(np.array(S_k), np.array(N_k), np.array(R_k), boot, seed)
    m_total = PRIOR_TRIALS + len(df)
    df["kontr_q_fdr"] = bh_qvalues(p, m_total)
    df = df[COLUMNS]
    meta = {
        "catalog_version": cat["meta"]["catalog_version"], "catalog_hash": cat["meta"]["content_hash"],
        "period": "discovery", "decisions": ["D30", "D31", "D32"],
        "groups": {g: [it.symbol for it in insts if it.group == g] for g in GROUPS},
        "sl_grid_pct": SL_GRID, "tp_grid_pct": TP_GRID, "h_rule": "D5: TP 1% → 14, 2% → 35, 3% → 70 świec",
        "modes": MODES, "mode_limits": LIMITS,
        "start_capital_usd": START_CAPITAL, "stake_usd": STAKE, "cost_pct": COST,
        "strategies_computed": int(len(df)), "trials_counter_after": m_total,
        "bootstrap": {"B": boot, "seed": seed, "block": "tydzień ISO wejścia", "weeks": W,
                      "p": "D30: przybliżenie normalne, z = przewaga / SE z bootstrapu"},
        "fdr_q": FDR_Q, "fdr_pass": int((df["kontr_q_fdr"] <= FDR_Q).sum()),
        "runtime_min": round((time.time() - t0) / 60, 1),
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "limit": limit,
    }
    return df, meta


def write(df: pd.DataFrame, meta: dict, out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "results.csv", index=False, float_format="%.4f")
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (out_dir / "runs.jsonl").open("a", encoding="utf-8") as f:      # 5.7: każdy przebieg zapisany
        f.write(json.dumps({k: meta[k] for k in ("computed_at", "catalog_hash", "decisions", "strategies_computed",
                                                    "trials_counter_after", "fdr_pass", "runtime_min")},
                           ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    from . import config, data
    ap = argparse.ArgumentParser(description="Etap 2: backtest strategii S1 (okres odkrywania, D32).")
    ap.add_argument("--limit", type=int, default=None, help="tylko N pierwszych sygnałów (próba, bez zapisu)")
    ap.add_argument("--boot", type=int, default=BOOT_B)
    a = ap.parse_args(argv)
    cat = json.loads((catalog.repo_root() / "s1" / "catalog.json").read_text(encoding="utf-8"))
    if not cat["meta"].get("frozen_at"):
        print("Katalog S1 nie jest zamrożony (1.5) — Etap 2 liczy tylko zamrożony katalog.")
        return 1
    if catalog.build()["meta"]["content_hash"] != cat["meta"]["content_hash"]:
        print("s1/catalog.json nie zgadza się z kodem katalogu — najpierw python3 -m ia4.catalog.")
        return 1
    u = config.universe()
    groups = {"main": list(u["main"]), "control": list(u["proof"])}
    print(f"Etap 2 (D32): katalog {cat['meta']['catalog_version']} ({cat['meta']['content_hash']}), "
          f"okres odkrywania, {len(groups['main'])} + {len(groups['control'])} spółek")
    frames = {s: data.load(s) for s in groups["main"] + groups["control"]}    # tylko odkrywanie (5.1)
    spy = data.load("SPY")
    df, meta = run(cat, frames, spy, groups, boot=a.boot, limit=a.limit)
    if a.limit:
        print(df.head(20).to_string())
        print(json.dumps({k: v for k, v in meta.items() if k != "groups"}, ensure_ascii=False, indent=1))
        print("Próba (--limit): nic nie zapisano.")
        return 0
    write(df, meta)
    print(f"Zapisano {OUT_DIR / 'results.csv'}: {len(df)} strategii, {meta['runtime_min']} min; "
          f"FDR 10%: {meta['fdr_pass']}")
    print("Teraz: cd .. && git add s1-backtest && git commit -m 'Backtest S1 D32' && git push, "
          "potem w arkuszu: Wczytaj wyniki S1-BACKTEST.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
