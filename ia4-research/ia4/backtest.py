"""
IA 4 — backtest S1 (Etap 2, instrukcja 2.1–2.3).
Wersja projektu: 0.40 (2026-09-28) — musi zgadzać się z IA4_INSTRUKCJA.md

Liczy każdą strategię z zamrożonego katalogu S1 (sygnał × kierunek × SL × TP)
na okresie ODKRYWANIA (5.1 — poletko zostaje na jedno sprawdzenie listy S2,
kryterium 2.2), osobno dla grupy głównej i kontrolnej (5.6), i zapisuje
`s1-backtest/results.csv` — jeden wiersz na strategię, dla arkusza S1-BACKTEST.

Kolejność dla jednej strategii (D29 — szczegóły i uzasadnienia w instrukcji):
  1. H według D5 (z TP), przebieg na grupie KONTROLNEJ → rozkład czasu do TP.
  2. D10: H = 90. percentyl czasu do TP (min. 10 wyjść na TP; inaczej zostaje D5).
     H wyznaczane tylko z grupy kontrolnej, żeby grupa główna była od tego
     wyboru niezależna i dalej mogła potwierdzać wynik (5.6, D16b).
  3. Przebieg z tym H na obu grupach: portfel chronologiczny (2.1) — każdy
     instrument jedna pozycja naraz (pkt 8), różne instrumenty równocześnie.
  4. Transakcje z powodem END (dane skończyły się przed SL/TP/H — w praktyce
     te otwarte tuż przed granicą odkrywania) są usuwane z wyników: to
     purging z 5.9. Ich liczba jest osobną kolumną.
  5. Wejście losowe (5.3): ta sama strategia wyjścia i ten sam H, wejście na
     otwarciu KAŻDEJ świecy każdego instrumentu grupy, bez pkt 8; przewaga =
     ekspektancja − ekspektancja losowa.
  6. Istotność (5.10, D16c): blokowy bootstrap po TYGODNIACH wejścia
     (tydzień ISO), jednostronny test „przewaga > 0”, B = 2000, ziarno stałe.
     FDR Benjaminiego–Hochberga (10%) na wyniku grupy kontrolnej, liczony na
     wszystkich 57 200 próbach z licznika (5.7) — niepoliczone mają p = 1.

Zero progów i filtrów w wyniku (2.2): kolumna `d16_abcd` jest tylko
podpowiedzią dla wyboru S2 (2.4) — zaznaczenie robi użytkownik.

    python3 -m ia4.backtest              # pełny przebieg (kilka–kilkanaście minut)
    python3 -m ia4.backtest --limit 5    # próba na 5 sygnałach, bez zapisu do repo
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import bars, catalog, engine, nyse, signals
from .engine import COST_PCT, Engine, h_default, one_position, resolve_grid

OUT_DIR = catalog.repo_root() / "s1-backtest"
BOOT_B = 2000
SEED = 20260928
H_QUANTILE = 0.90            # D10
MIN_TP_FOR_H = 10            # D10: mniej wyjść na TP → zostaje H z D5
FDR_Q = 0.10                 # D16c
AMBIG_MAX_PCT = 20.0         # 5.4
MIN_NET_PCT = 0.05           # 5.11 / D16d
GROUPS = {"main": "gl", "control": "kontr"}
REASON_NAMES = {0: "sl", 1: "tp", 2: "czas"}


@dataclass
class Inst:
    symbol: str
    group: str
    B: bars.Bars
    eng: Engine
    tord: np.ndarray          # porządek czasowy świec wspólny dla wszystkich instrumentów
    week: np.ndarray          # numer tygodnia ISO (indeks w całym okresie)
    rising: bool              # D13: spółka rosnąca w okresie (C ostatnie > C pierwsze)


def prepare(frames: dict, spy, groups: dict) -> tuple[list[Inst], list]:
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
            out.append(Inst(s, g, B, Engine(B), tord, week, bool(B.c[-1] > B.c[0])))
    return out, weeks


def h_matrix_default(eng: Engine) -> np.ndarray:
    return np.array([[h_default(tp) for tp in eng.tp_grid] for _ in eng.sl_grid], dtype=np.int64)


class Baseline:
    """Wejście losowe (5.3): średni wynik wejścia w każdą świecę, per (grupa, kierunek, H)."""

    def __init__(self, insts: list[Inst]):
        self.insts = insts
        self._c: dict = {}

    def grid(self, group: str, direction: str, H: int) -> np.ndarray:
        key = (group, direction, H)
        if key not in self._c:
            tot, cnt = None, None
            for it in self.insts:
                if it.group != group:
                    continue
                Hm = np.full((len(it.eng.sl_grid), len(it.eng.tp_grid)), H, dtype=np.int64)
                g = resolve_grid(it.eng, np.arange(it.B.n), direction, Hm)
                ok = g.reason != 3
                s = np.where(ok, g.ret, 0.0).sum(axis=0)
                c = ok.sum(axis=0)
                tot = s if tot is None else tot + s
                cnt = c if cnt is None else cnt + c
            self._c[key] = (tot / np.maximum(cnt, 1)) * 100.0 if tot is not None else None
        return self._c[key]


def _entries(sig: dict, it: Inst) -> np.ndarray:
    t = np.flatnonzero(signals.mask(sig, it.B))
    e = signals.entry_index(sig, t)
    return e[e < it.B.n]


def _choose_h(sig, insts, entries, direction, Hdef) -> tuple[np.ndarray, np.ndarray]:
    """D10: H = 90. percentyl czasu do TP w grupie kontrolnej (przebieg z H z D5)."""
    S, T = Hdef.shape
    tp_bars: list[list[np.ndarray]] = [[[] for _ in range(T)] for _ in range(S)]
    for it, e in zip(insts, entries):
        if it.group != "control" or len(e) == 0:
            continue
        g = resolve_grid(it.eng, e, direction, Hdef)
        for i in range(S):
            for j in range(T):
                k = one_position(e, g.exit[:, i, j])
                r = g.reason[k, i, j]
                tp_bars[i][j].append((g.exit[k, i, j] - e[k] + 1)[r == 1])
    H = Hdef.copy()
    src = np.zeros_like(Hdef, dtype=bool)
    for i in range(S):
        for j in range(T):
            x = np.concatenate(tp_bars[i][j]) if tp_bars[i][j] else np.array([])
            if len(x) >= MIN_TP_FOR_H:
                H[i, j] = int(min(Hdef[i, j], max(1, np.quantile(x, H_QUANTILE, method="higher"))))
                src[i, j] = True
    return H, src


def _collect(sig, insts, entries, direction, H) -> dict:
    """Transakcje każdej strategii (i, j) w każdej grupie — portfel chronologiczny (2.1)."""
    S, T = H.shape
    acc = {(g, i, j): [] for g in GROUPS for i in range(S) for j in range(T)}
    for it, e in zip(insts, entries):
        if len(e) == 0:
            continue
        g = resolve_grid(it.eng, e, direction, H)
        for i in range(S):
            for j in range(T):
                k = one_position(e, g.exit[:, i, j])
                x = g.exit[k, i, j]
                ek = e[k]
                acc[(it.group, i, j)].append({
                    "ret": g.ret[k, i, j] * 100.0, "reason": g.reason[k, i, j],
                    "amb": g.ambiguous[k, i, j], "bars": x - ek + 1,
                    "e_ord": it.tord[ek], "x_ord": it.tord[x], "e_date": it.B.date[ek],
                    "week": it.week[ek], "rising": np.full(len(k), it.rising),
                })
    out = {}
    for key, parts in acc.items():
        if parts:
            out[key] = {f: np.concatenate([p[f] for p in parts]) for f in parts[0]}
        else:
            out[key] = None
    return out


def max_concurrent(e_ord: np.ndarray, x_ord: np.ndarray) -> int:
    """Najwięcej pozycji otwartych naraz (2.1): przedziały [wejście, wyjście] włącznie."""
    if len(e_ord) == 0:
        return 0
    t = np.concatenate([e_ord, x_ord + 1])
    d = np.concatenate([np.ones(len(e_ord), int), -np.ones(len(x_ord), int)])
    order = np.lexsort((d, t))               # przy tym samym czasie najpierw zamknięcia
    return int(np.max(np.cumsum(d[order])))


def metrics(tr: dict | None, rnd: float, n_weeks: int) -> tuple[dict, np.ndarray, np.ndarray]:
    """Kolumny 2.2 dla jednej strategii w jednej grupie + tygodniowe sumy do bootstrapu."""
    S = np.zeros(n_weeks)
    N = np.zeros(n_weeks)
    if tr is None:
        return {"transakcji": 0, "end_usuniete": 0}, S, N
    end = tr["reason"] == 3
    keep = ~end
    t = {k: v[keep] for k, v in tr.items()}
    n = int(keep.sum())
    m: dict = {"transakcji": n, "end_usuniete": int(end.sum())}
    if n == 0:
        return m, S, N
    r = t["ret"]
    pos, neg = r[r > 0], r[r < 0]
    order = np.argsort(t["x_ord"], kind="stable")
    cum = np.concatenate([[0.0], np.cumsum(r[order])])
    exp = float(r.mean())
    m.update({
        "dni": int(len(np.unique(t["e_date"]))),
        "skutecznosc": float((r > 0).mean() * 100),
        "ekspektancja": exp,
        "ekspektancja_netto": exp - COST_PCT,
        "pf": float(pos.sum() / -neg.sum()) if len(neg) and neg.sum() < 0 else (math.inf if len(pos) else 0.0),
        "sr_zysk": float(pos.mean()) if len(pos) else 0.0,
        "sr_strata": float(neg.mean()) if len(neg) else 0.0,
        "obsuniecie": float(np.max(np.maximum.accumulate(cum) - cum)),
        "max_jednoczesnie": max_concurrent(t["e_ord"], t["x_ord"]),
        "pct_wieloznacznych": float(t["amb"].mean() * 100),
        "losowe": float(rnd),
        "przewaga": exp - float(rnd),
    })
    for code, name in REASON_NAMES.items():
        sel = t["reason"] == code
        m[f"pct_{name}"] = float(sel.mean() * 100)
        m[f"med_trzymania_{name}"] = float(np.median(t["bars"][sel])) if sel.any() else None
    for flag, name in ((True, "rosnace"), (False, "spadajace")):
        sel = t["rising"] == flag
        m[f"eksp_{name}"] = float(r[sel].mean()) if sel.any() else None
        m[f"transakcji_{name}"] = int(sel.sum())
    S = np.bincount(t["week"], weights=r, minlength=n_weeks).astype(float)
    N = np.bincount(t["week"], minlength=n_weeks).astype(float)
    return m, S, N


def bootstrap_p(S: np.ndarray, N: np.ndarray, rnd: np.ndarray, B: int = BOOT_B, seed: int = SEED,
                chunk: int = 2000) -> np.ndarray:
    """
    Blokowy bootstrap po tygodniach (5.10): losujemy W tygodni ze zwracaniem, średnia =
    Σ zwrotów / Σ transakcji z wylosowanych tygodni. Test jednostronny H0: przewaga ≤ 0,
    rozkład wycentrowany: p = (1 + #{m* − m̂ ≥ m̂ − losowe}) / (B + 1).
    S, N: [K × W]; rnd: [K]. Te same losowania dla wszystkich strategii (porównywalność).
    """
    K, W = S.shape
    rng = np.random.default_rng(seed)
    C = rng.multinomial(W, np.full(W, 1.0 / W), size=B).astype(float)      # [B × W]
    p = np.ones(K)
    ntot = N.sum(axis=1)
    mhat = np.where(ntot > 0, S.sum(axis=1) / np.maximum(ntot, 1), np.nan)
    for a in range(0, K, chunk):
        b = min(K, a + chunk)
        num = C @ S[a:b].T
        den = C @ N[a:b].T
        with np.errstate(invalid="ignore", divide="ignore"):
            mstar = num / den                                              # [B × k]
        dev = mstar - mhat[a:b][None, :]
        edge = (mhat[a:b] - rnd[a:b])[None, :]
        cnt = np.nansum(dev >= edge, axis=0)
        p[a:b] = (1 + cnt) / (B + 1)
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


def strategy_id(code: str, d: str, sl, tp, H: int) -> str:
    return f"{code}__{d}__SL{catalog.code_num(sl)}_TP{catalog.code_num(tp)}_H{H}"


def run(cat: dict, frames: dict, spy, groups: dict, boot: int = BOOT_B, seed: int = SEED,
        limit: int | None = None, progress=print) -> tuple[pd.DataFrame, dict]:
    t0 = time.time()
    insts, weeks = prepare(frames, spy, groups)
    W = len(weeks)
    base = Baseline(insts)
    todo = [s for s in cat["signals"] if s["status"] in ("aktywny", "kontrolny")]
    if limit:
        todo = todo[:limit]
    sl_grid, tp_grid = insts[0].eng.sl_grid, insts[0].eng.tp_grid
    Hdef = h_matrix_default(insts[0].eng)
    rows, S_rows, N_rows, rnd_rows = [], [], [], []
    for n_sig, sig in enumerate(todo, 1):
        entries = [_entries(sig, it) for it in insts]
        for d in ("L", "S"):
            H, from_d10 = _choose_h(sig, insts, entries, d, Hdef)
            tr = _collect(sig, insts, entries, d, H)
            for i, sl in enumerate(sl_grid):
                for j, tp in enumerate(tp_grid):
                    h = int(H[i, j])
                    row = {"id": strategy_id(sig["code"], d, sl, tp, h), "sygnal": sig["id"], "kod": sig["code"],
                           "kategoria": sig["category"], "rodzina": sig["family"], "status": sig["status"],
                           "kierunek": d, "sl": sl, "tp": tp, "h": h, "h_zrodlo": "D10" if from_d10[i, j] else "D5",
                           "para": sig.get("paired_with") or ""}
                    for g, pre in GROUPS.items():
                        rnd = float(base.grid(g, d, h)[i, j])
                        m, Sw, Nw = metrics(tr[(g, i, j)], rnd, W)
                        row.update({f"{pre}_{k}": v for k, v in m.items()})
                        S_rows.append(Sw)
                        N_rows.append(Nw)
                        rnd_rows.append(rnd)
                    rows.append(row)
        if n_sig % 10 == 0 or n_sig == len(todo):
            el = time.time() - t0
            progress(f"  {n_sig}/{len(todo)} sygnałów, {el / 60:.1f} min (zostało ok. "
                     f"{el / n_sig * (len(todo) - n_sig) / 60:.1f} min)")

    df = pd.DataFrame(rows)
    # --- istotność (5.10) i FDR (5.7, D16c) ---
    p = bootstrap_p(np.array(S_rows), np.array(N_rows), np.array(rnd_rows), boot, seed)
    df["gl_p_bootstrap"] = p[0::2]
    df["kontr_p_bootstrap"] = p[1::2]
    m_total = int(cat["meta"]["strategies"])
    df["kontr_q_fdr"] = bh_qvalues(df["kontr_p_bootstrap"].to_numpy(), m_total)
    df["fdr_10"] = df["kontr_q_fdr"] <= FDR_Q

    # --- kolumny wspólne (2.2) ---
    key = df.set_index(["kod", "kierunek", "sl", "tp"])["kontr_ekspektancja"]
    opp = {"L": "S", "S": "L"}
    df["kontr_eksp_kierunek_przeciwny"] = [key.get((k, opp[d], s, t)) for k, d, s, t in
                                           zip(df["kod"], df["kierunek"], df["sl"], df["tp"])]
    df["para_kontr_ekspektancja"] = [key.get((pp, d, s, t)) if pp else None for pp, d, s, t in
                                     zip(df["para"], df["kierunek"], df["sl"], df["tp"])]
    df["roznica_gl_kontr"] = df["gl_ekspektancja"] - df["kontr_ekspektancja"]
    df["przewaga_w_obu"] = (df["gl_przewaga"] > 0) & (df["kontr_przewaga"] > 0)
    df["niewiarygodna_5_4"] = (df[["gl_pct_wieloznacznych", "kontr_pct_wieloznacznych"]].max(axis=1)
                               > AMBIG_MAX_PCT)
    df["d16_abcd"] = ((df["gl_transakcji"] >= 100) & (df["kontr_transakcji"] >= 300)
                      & (df["gl_dni"] >= 30) & (df["kontr_dni"] >= 30)
                      & df["przewaga_w_obu"] & df["fdr_10"]
                      & (df["gl_ekspektancja_netto"] >= MIN_NET_PCT) & (df["kontr_ekspektancja_netto"] >= MIN_NET_PCT))
    df = df[_column_order(df)]
    meta = {
        "catalog_version": cat["meta"]["catalog_version"],
        "catalog_hash": cat["meta"]["content_hash"],
        "frozen_at": cat["meta"].get("frozen_at"),
        "period": "discovery",
        "groups": {g: [it.symbol for it in insts if it.group == g] for g in GROUPS},
        "strategies_computed": int(len(df)),
        "strategies_in_counter": m_total,
        "bootstrap": {"B": boot, "seed": seed, "block": "tydzień ISO wejścia", "weeks": W},
        "h_rule": f"D10: kwantyl {H_QUANTILE} czasu do TP w grupie kontrolnej, min. {MIN_TP_FOR_H} wyjść na TP",
        "cost_pct": COST_PCT,
        "fdr_q": FDR_Q,
        "d16_abcd": int(df["d16_abcd"].sum()),
        "fdr_10": int(df["fdr_10"].sum()),
        "runtime_min": round((time.time() - t0) / 60, 1),
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "limit": limit,
    }
    return df, meta


def _column_order(df: pd.DataFrame) -> list[str]:
    head = ["id", "sygnal", "kod", "kategoria", "rodzina", "status", "kierunek", "sl", "tp", "h", "h_zrodlo"]
    per = ["transakcji", "dni", "skutecznosc", "ekspektancja", "ekspektancja_netto", "pf", "sr_zysk",
           "sr_strata", "obsuniecie", "max_jednoczesnie", "med_trzymania_sl", "med_trzymania_tp",
           "med_trzymania_czas", "pct_sl", "pct_tp", "pct_czas", "pct_wieloznacznych", "losowe", "przewaga",
           "p_bootstrap", "eksp_rosnace", "transakcji_rosnace", "eksp_spadajace", "transakcji_spadajace",
           "end_usuniete"]
    cols = head + [f"{pre}_{c}" for pre in GROUPS.values() for c in per]
    cols += ["kontr_q_fdr", "fdr_10", "przewaga_w_obu", "roznica_gl_kontr", "kontr_eksp_kierunek_przeciwny",
             "para", "para_kontr_ekspektancja", "niewiarygodna_5_4", "d16_abcd"]
    for c in cols:
        if c not in df:
            df[c] = None
    return cols


def write(df: pd.DataFrame, meta: dict, out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "results.csv", index=False, float_format="%.4f")
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (out_dir / "runs.jsonl").open("a", encoding="utf-8") as f:       # 5.7: każdy przebieg zapisany
        f.write(json.dumps({k: meta[k] for k in ("computed_at", "catalog_hash", "strategies_computed",
                                                    "runtime_min", "d16_abcd")}, ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    from . import config, data
    ap = argparse.ArgumentParser(description="Etap 2: backtest wszystkich strategii S1 (okres odkrywania).")
    ap.add_argument("--limit", type=int, default=None, help="tylko N pierwszych sygnałów (próba, bez zapisu)")
    ap.add_argument("--boot", type=int, default=BOOT_B)
    a = ap.parse_args(argv)

    cat = json.loads((catalog.repo_root() / "s1" / "catalog.json").read_text(encoding="utf-8"))
    if not cat["meta"].get("frozen_at"):
        print("Katalog S1 nie jest zamrożony (1.5) — Etap 2 liczy tylko zamrożony katalog.")
        return 1
    fresh = catalog.build()
    if fresh["meta"]["content_hash"] != cat["meta"]["content_hash"]:
        print("s1/catalog.json nie zgadza się z kodem katalogu — najpierw python3 -m ia4.catalog.")
        return 1
    u = config.universe()
    groups = {"main": list(u["main"]), "control": list(u["proof"])}
    print(f"Etap 2: katalog {cat['meta']['catalog_version']} ({cat['meta']['content_hash']}), okres odkrywania, "
          f"{len(groups['main'])} + {len(groups['control'])} spółek")
    frames = {s: data.load(s) for s in groups["main"] + groups["control"]}     # tylko odkrywanie (5.1)
    spy = data.load("SPY")
    df, meta = run(cat, frames, spy, groups, boot=a.boot, limit=a.limit)
    if a.limit:
        print(df.head(20).to_string())
        print(json.dumps(meta, ensure_ascii=False, indent=1))
        print("Próba (--limit): nic nie zapisano.")
        return 0
    write(df, meta)
    print(f"Zapisano {OUT_DIR / 'results.csv'}: {len(df)} strategii, {meta['runtime_min']} min; "
          f"FDR 10%: {meta['fdr_10']}, D16 a–d: {meta['d16_abcd']}")
    print("Teraz: git add s1-backtest && git commit && git push, potem w arkuszu: Wczytaj wyniki S1-BACKTEST.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
