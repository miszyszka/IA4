"""
IA 4 — FX-research: wystąpienia, profile, ratingi i sprawdzian okoliczności na świecach 1h
11 instrumentów (instrukcja, sekcje 4c.4–4c.8).
Wersja projektu: 1.39 (2026-10-14) — musi zgadzać się z IA4_INSTRUKCJA.md

  python -m ia4.fx.research              # synchronizacja, przeliczenie od zera, zapis i push na branch fx
  python -m ia4.fx.research --no-sync    # bez Firestore (kopia lokalna)
  python -m ia4.fx.research --no-push    # bez GitHub (wynik tylko lokalnie)

Tylko ręcznie. Każde uruchomienie liczy WSZYSTKO od nowa na całej kopii lokalnej — katalog
okoliczności jest stały (fx/conditions.json), zmieniają się tylko dane.

PULA (4c.4): świece wszystkich instrumentów w jednej tablicy (bloki instrumentów jeden po drugim).
Zmiany ceny w jednostkach zmienności: r_k = (c[t+k] − c[t]) / ATR100[t] — porównywalne między
parami walutowymi i BTC. Części walk-forward wyznacza KALENDARZ (wspólny dla wszystkich
instrumentów), bo pary walutowe poruszają się razem — podział po indeksie świec przeciekałby
przyszłość z jednej pary do drugiej.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import catalog as cat
from . import instruments as fi
from . import series as sr

H = 48                     # horyzont: 48 świec 1h
FOLDS = 5                  # 4c.5: walk-forward — kalendarz w 5 równych częściach, ocena na częściach 2–5
SPLIT_CHECK = 0.70         # 4c.7: sprawdzian — ratingi z 0–70% kalendarza, zapytania na 70–100%
SHRINK = 20                # 4c.5: S* = S · n / (n + 20)
RATING_FULL = 0.05         # 4c.5: S* = 0,05 → rating 100
MIN_TRAIN = 30             # 4c.5: część z mniejszą liczbą wystąpień uczących — pomijana
MIN_IND = 5                # 4c.5: mniej niezależnych wystąpień w ocenie → rating 1
NEVER = np.iinfo(np.int64).max


# ===========================================================================
#  Pula instrumentów
# ===========================================================================
class Pool:
    """Wszystkie instrumenty w jednej tablicy świec. Kolumny: inst (nr instrumentu), time, c, filled,
    U100, U12 (ATR w cenie), R (T × 48, zmiany w jednostkach ATR100), tk (T × 48, czas świecy t+k;
    NEVER, gdy jej nie ma), ok (świeca może być wystąpieniem), el (liczy się do częstości), M (N × T)."""

    def __init__(self, dfs: dict, conds: list[dict]):
        self.syms = list(dfs)
        self.groups = [fi.group_of(s) for s in self.syms]
        parts = {k: [] for k in ("inst", "time", "c", "filled", "U100", "U12", "R", "tk", "ok", "el", "M")}
        self.start, self.end = [], []
        o = 0
        for j, s in enumerate(self.syms):
            df = dfs[s]
            Sp, Sm = sr.pair_of(df, s, self.groups[j])
            n = Sp.n
            self.start.append(o)
            self.end.append(o + n)
            o += n
            parts["inst"].append(np.full(n, j, dtype=np.int16))
            parts["time"].append(Sp.time)
            parts["c"].append(Sp.c)
            parts["filled"].append(Sp.filled)
            parts["U100"].append(Sp.U)
            parts["U12"].append(Sp.U12)
            R, tk = future_changes(Sp.c, Sp.filled, Sp.time, Sp.U)
            parts["R"].append(R)
            parts["tk"].append(tk)
            parts["ok"].append(occurrence_ok(Sp.time, Sp.filled, self.groups[j]))
            parts["el"].append(cat.eligible(Sp))
            parts["M"].append(cat.evaluate(conds, Sp, Sm))
        for k, v in parts.items():
            setattr(self, k, np.concatenate(v, axis=1 if k == "M" else 0))
        self.T = self.time.size
        self.last = np.array(self.end) - 1                          # ostatnia świeca każdego instrumentu

    def edges(self, end_time: int | None = None, folds: int = FOLDS) -> list[int]:
        t0 = int(self.time.min())
        t1 = int(self.time.max()) + 1 if end_time is None else int(end_time)
        return [t0 + (t1 - t0) * j // folds for j in range(folds + 1)]

    def time_at(self, frac: float) -> int:
        t0, t1 = int(self.time.min()), int(self.time.max()) + 1
        return t0 + int(frac * (t1 - t0))


def future_changes(c, filled, time_, U):
    """R[t, k−1] = (c[t+k] − c[t]) / U[t] (jednostki ATR100), k = 1…48; NaN, gdy świeca t+k nie istnieje
    albo jest uśredniona. tk[t, k−1] = czas świecy t+k (NEVER, gdy jej nie ma)."""
    T = c.size
    R = np.full((T, H), np.nan, dtype=np.float64)
    tk = np.full((T, H), NEVER, dtype=np.int64)
    with np.errstate(invalid="ignore", divide="ignore"):
        for k in range(1, H + 1):
            if k >= T:
                break
            d = (c[k:] - c[:-k]) / U[:-k]
            d[filled[k:]] = np.nan
            R[: T - k, k - 1] = d
            tk[: T - k, k - 1] = time_[k:]
    return R, tk


def occurrence_ok(time_, filled, group) -> np.ndarray:
    """Świeca może być wystąpieniem: po rozgrzewce, nie uśredniona, w oknie t … t+48 bez przerwy (4c.1)."""
    T = time_.size
    gap = sr.gap_after(time_, group).astype(np.int64)
    cs = np.concatenate([[0], np.cumsum(gap)])
    end = np.minimum(np.arange(T) + H, T - 1)
    has_gap = (cs[end] - cs[np.arange(T)]) > 0
    ok = ~filled & ~has_gap
    ok[: sr.WARMUP] = False
    return ok


def n_independent(idx: np.ndarray, inst: np.ndarray) -> int:
    """Wystąpienia wybierane od najstarszego tak, że każde kolejne tego samego instrumentu jest
    ≥ 48 świec po poprzednim wybranym; suma po instrumentach."""
    n, last, cur = 0, -10 ** 9, -1
    for t, j in zip(idx.tolist(), inst[idx].tolist()):
        if j != cur:
            cur, last = j, -10 ** 9
        if t - last >= H:
            n += 1
            last = t
    return n


# ===========================================================================
#  Profil i rating jednej okoliczności
# ===========================================================================
def profile(R: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Średnia zmiana (ATR100) dla k = 1…48 z wystąpień idx (NaN, gdy dla k nie ma żadnej)."""
    if idx.size == 0:
        return np.full(H, np.nan)
    x = R[idx]
    cnt = np.isfinite(x).sum(0)
    s = np.nansum(x, 0)
    return np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)


def rate(P: Pool, idx: np.ndarray, end_time: int | None = None) -> dict:
    """4c.5 — walk-forward po kalendarzu [początek, end_time): 5 równych części; dla części j = 2…5
    profil uczący z wystąpień, których okno (świeca t+48) kończy się przed jej początkiem; ocena na
    wystąpieniach części j, zmiany tylko świec przed jej końcem. Błędy sumowane po częściach."""
    edges = P.edges(end_time=end_time)
    ec = e0 = 0.0
    n_ind = tr_n = ev_n = 0
    t_idx, end_idx = P.time[idx], P.tk[idx, H - 1]
    for j in range(1, FOLDS):
        a, b = edges[j], edges[j + 1]
        tr = idx[end_idx < a]
        ev = idx[(t_idx >= a) & (t_idx < b)]
        if tr.size < MIN_TRAIN or ev.size == 0:
            continue
        prof = profile(P.R, tr)
        r = P.R[ev].copy()
        r[P.tk[ev] >= b] = np.nan                                  # nie zaglądamy za koniec części
        use = np.isfinite(r) & np.isfinite(prof)[None, :]
        e0 += np.abs(r[use]).sum()
        ec += np.abs((r - prof[None, :])[use]).sum()
        n_ind += n_independent(ev, P.inst)
        tr_n, ev_n = max(tr_n, int(tr.size)), ev_n + int(ev.size)
    out = {"train_n": tr_n, "eval_n": ev_n, "eval_ind": int(n_ind), "S": 0.0, "Sstar": 0.0, "rating": 1}
    if e0 <= 0:
        return out
    S = 1.0 - ec / e0
    Ss = S * n_ind / (n_ind + SHRINK)
    out["S"], out["Sstar"] = float(S), float(Ss)
    if Ss > 0 and n_ind >= MIN_IND:
        out["rating"] = int(1 + round(99 * min(Ss / RATING_FULL, 1.0)))
    return out


# ===========================================================================
#  Środek prognozy (4c.6) i ratingi bez zaglądania w przyszłość (4c.7)
# ===========================================================================
def forecast_from(active: np.ndarray, ratings: np.ndarray, profiles: np.ndarray):
    """Średnia profili okoliczności prawdziwych ważona ratingiem (ATR100). active: (N,) albo (T, N)."""
    a = np.atleast_2d(active).astype(np.float64) * ratings[None, :]
    P0 = np.nan_to_num(profiles, nan=0.0)
    Pm = np.isfinite(profiles).astype(np.float64)
    num, den = a @ P0, a @ Pm
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den > 0, num / den, np.nan)
    return out[0] if np.ndim(active) == 1 else out


def model_until(P: Pool, end_time: int):
    """Ratingi (walk-forward, 4c.5) i profile wyłącznie z okien, które kończą się przed end_time."""
    N = P.M.shape[0]
    rat = np.ones(N)
    prof = np.full((N, H), np.nan)
    for i in range(N):
        idx = np.flatnonzero(P.M[i] & P.ok)
        rat[i] = rate(P, idx, end_time)["rating"]
        prof[i] = profile(P.R, idx[P.tk[idx, H - 1] < end_time])
    return rat, prof


# ===========================================================================
#  Przeliczenie całości
# ===========================================================================
def run(dfs: dict, conds: list[dict], log=print) -> dict:
    from . import scenario as sc
    t0 = time.time()
    P = Pool(dfs, conds)
    log(f"  okoliczności policzone: {len(conds)} × {P.T} świec, {len(P.syms)} instrumentów ({time.time() - t0:.1f} s)")
    rows, profiles, ratings = [], np.full((len(conds), H), np.nan), np.ones(len(conds))
    for i, cd in enumerate(conds):
        idx = np.flatnonzero(P.M[i] & P.ok)
        rt = rate(P, idx)
        profiles[i] = profile(P.R, idx)
        ratings[i] = rt["rating"]
        cov = float(P.M[i][P.el].mean()) if P.el.any() else 0.0
        per = [float(P.M[i, P.start[j]:P.end[j]][P.el[P.start[j]:P.end[j]]].mean())
               for j in range(len(P.syms)) if P.el[P.start[j]:P.end[j]].any()]
        rows.append({"id": cd["id"], "rating": rt["rating"], "n": int(idx.size), "n_ind": int(n_independent(idx, P.inst)),
                     "train_n": rt["train_n"], "eval_n": rt["eval_n"], "eval_ind": rt["eval_ind"],
                     "S": round(rt["S"], 5), "Sstar": round(rt["Sstar"], 5), "coverage": round(cov, 4),
                     "covInstMin": round(min(per), 4) if per else None, "covInstMax": round(max(per), 4) if per else None,
                     "flag": "" if cat.RANGE[0] <= cov <= cat.RANGE[1] else "częstość poza zakresem",
                     "profile": [None if not np.isfinite(v) else round(float(v), 4) for v in profiles[i]]})
    log(f"  wystąpienia, profile i ratingi ({time.time() - t0:.1f} s)")

    t70 = P.time_at(SPLIT_CHECK)
    rat70, prof70 = model_until(P, t70)                              # sprawdzian: tylko przeszłość
    PM = np.full((P.T, H), np.nan)
    late = np.flatnonzero(P.time >= t70)
    PM[late] = forecast_from(P.M[:, late].T, rat70, prof70)
    check = sc.check(sc.Engine(P, rat70), PM, start_frac=SPLIT_CHECK)
    log(f"  sprawdzian prognozy rozkładu: {check.get('queries', 0)} zapytań ({time.time() - t0:.1f} s)")
    last = {}
    if check.get("model"):
        mdl = check["model"]
        eng = sc.Engine(P, ratings)
        for j, s in enumerate(P.syms):
            t = int(P.last[j])
            a = eng.select(t, int(P.time[t]) + 1, mdl["method"])
            if a.size < 10:
                continue
            paths = eng.paths(t, a)
            center = sc.center_of(mdl, paths, forecast_from(P.M[:, t], ratings, profiles))
            d = sc.distribution(paths, center, mdl["f"])
            u = float(P.U100[t])
            last[s] = {"time": iso(P.time[t]), "close": float(P.c[t]), "active": int(P.M[:, t].sum()),
                       "center48": round(u * float(d["center"][-1]), 6), "q10_48": round(u * float(d["q"][10][-1]), 6),
                       "q90_48": round(u * float(d["q"][90][-1]), 6), "range": round(u * d["range"], 6),
                       "pUp48": round(float(d["pUp"][-1]), 3)}
    return {"rows": rows, "scenario": check, "last": last, "pool": P}


# ===========================================================================
#  Zapis
# ===========================================================================
def iso(t) -> str:
    return datetime.fromtimestamp(int(t), timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def data_info(P: Pool) -> dict:
    inst = [{"id": s, "group": P.groups[j], "candles": int(P.end[j] - P.start[j]),
             "from": iso(P.time[P.start[j]]), "to": iso(P.time[P.end[j] - 1])} for j, s in enumerate(P.syms)]
    return {"interval": "1h", "from": min(i["from"] for i in inst), "to": max(i["to"] for i in inst),
            "candles": int(P.T), "instruments": inst}


def documents(res: dict, conds_doc: dict, run_id: str) -> tuple[dict, dict]:
    from .. import __version__
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    P = res["pool"]
    data = data_info(P)
    rating_cfg = {"method": "walk-forward (kalendarz)", "folds": FOLDS, "shrink": SHRINK, "full": RATING_FULL,
                  "minTrain": MIN_TRAIN, "minInd": MIN_IND, "horizon": H, "unit": "ATR100"}
    sc_ = res["scenario"] or {}
    mdl = sc_.get("model") or {}
    best = (sc_.get("methods") or {}).get(mdl.get("method"), {}).get("B") or {}
    ratings_doc = {"run": run_id, "at": now, "version": __version__, "catalog": conds_doc["catalog"],
                   "data": data, "rating": rating_cfg, "scenario": sc_, "lastCandle": res["last"],
                   "conditions": res["rows"]}
    pin = {m: ((sc_.get("methods") or {}).get(m, {}).get("B") or {}).get("pinball48") for m in ("analogi", "pora", "całość")}
    run_line = {"run": run_id, "at": now, "version": __version__, "data": {k: data[k] for k in ("interval", "from", "to", "candles")},
                "instruments": len(P.syms),
                "scenario": {"model": mdl.get("method"), "f": mdl.get("f"), "lambda": mdl.get("lambda"), "center": mdl.get("center"),
                             "cov80_48": best.get("cov80_48"), "brier48": best.get("brier48"),
                             "rangeErr": best.get("rangeErr"), "pinball48": pin},
                "r": [[r["rating"], r["n"], round(100 * r["coverage"], 1)] for r in res["rows"]]}
    return ratings_doc, run_line


def write_ratings(path, doc: dict) -> None:
    """ratings.json czytelny i zwięzły: nagłówek z wcięciami, jedna okoliczność = jedna linia."""
    head = {k: v for k, v in doc.items() if k != "conditions"}
    body = ",\n".join("    " + json.dumps(c, ensure_ascii=False, separators=(",", ":")) for c in doc["conditions"])
    text = json.dumps(head, indent=2, ensure_ascii=False)[:-2] + ',\n  "conditions": [\n' + body + "\n  ]\n}\n"
    json.loads(text)                                   # kontrola poprawności
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def save_local(res: dict, conds: list[dict], run_id: str) -> None:
    """data/fx1h/occurrences.npz — macierz okoliczności (bity), pula i zmiany; ratings-preview.csv — podgląd."""
    from .sync import FX_DIR
    P = res["pool"]
    FX_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(FX_DIR / "occurrences.npz", run=run_id, ids=np.array([c["id"] for c in conds]),
                        syms=np.array(P.syms), inst=P.inst, time=P.time, close=P.c, U100=P.U100, ok=P.ok,
                        R=P.R.astype(np.float32), M=np.packbits(P.M, axis=1), T=P.T)
    with open(FX_DIR / "ratings-preview.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ID", "Kierunek", "Rodzina", "Okoliczność", "Rating", "Wystąpień", "Niezależnych",
                    "Przewaga S %", "Częstość %", "Częstość min. na instrumencie %", "Częstość maks. na instrumencie %",
                    "Uwagi", "Profil k=12 (ATR100)", "Profil k=48 (ATR100)"])
        fmt = lambda v: "" if v is None else f"{v}".replace(".", ",")
        pc = lambda v: "" if v is None else f"{100 * v:.1f}".replace(".", ",")
        for c, r in zip(conds, res["rows"]):
            p = r["profile"]
            w.writerow([c["id"], c["dir"], c["familyName"], c["desc"], r["rating"], r["n"], r["n_ind"],
                        f"{100 * r['S']:.2f}".replace(".", ","), pc(r["coverage"]), pc(r["covInstMin"]), pc(r["covInstMax"]),
                        r["flag"], fmt(p[11]), fmt(p[47])])


def load_occurrences(cond_id: str, symbol: str | None = None) -> pd.DataFrame:
    """Wystąpienia okoliczności z ostatniego przeliczenia — „ID → wystąpienie → 48 przyszłych zmian” (4c.4):
    instrument, czas, zamknięcie, ATR100 i k1…k48 w jednostkach ATR100 (× ATR100 = zmiana ceny)."""
    from .sync import FX_DIR
    z = np.load(FX_DIR / "occurrences.npz")
    i = int(np.flatnonzero(z["ids"] == cond_id)[0])
    row = np.unpackbits(z["M"][i])[: int(z["T"])].astype(bool)
    idx = np.flatnonzero(row & z["ok"])
    if symbol:
        idx = idx[z["syms"][z["inst"][idx]] == symbol]
    df = pd.DataFrame(z["R"][idx], columns=[f"k{k}" for k in range(1, H + 1)])
    df.insert(0, "U100", z["U100"][idx])
    df.insert(0, "close", z["close"][idx])
    df.insert(0, "time", pd.to_datetime(z["time"][idx], unit="s", utc=True))
    df.insert(0, "symbol", z["syms"][z["inst"][idx]])
    return df


def summary(res: dict, conds: list[dict], log=print) -> None:
    rows = res["rows"]
    rt = np.array([r["rating"] for r in rows])
    log(f"\n  ratingi: 1 → {int((rt == 1).sum())}, 2–20 → {int(((rt > 1) & (rt <= 20)).sum())}, "
        f"21–50 → {int(((rt > 20) & (rt <= 50)).sum())}, 51–100 → {int((rt > 50).sum())}")
    log(f"  częstość poza 10–50%: {sum(1 for r in rows if r['flag'])}")
    top = sorted(range(len(rows)), key=lambda i: (-rows[i]["rating"], -rows[i]["S"]))[:15]
    log("\n  najwyższe ratingi:")
    for i in top:
        r = rows[i]
        log(f"    {r['id']} {r['rating']:3d}/{r['n']:<6d} S {100*r['S']:5.2f}%  {conds[i]['desc']}")
    sc_ = res["scenario"] or {}
    log(f"\n  sprawdzian prognozy rozkładu (walk-forward po kalendarzu: kalibracja 70–85%, ocena 85–100%, "
        f"{sc_.get('queries', 0)} zapytań):")
    log("    metoda     pinball k=12 / k=48   pokrycie 80% k=12 / k=48   Brier k=12 / k=48   błąd zakresu   środek λ")
    for m, v in (sc_.get("methods") or {}).items():
        B = v.get("B")
        if B:
            log(f"    {m:9s}  {B['pinball12']:6.3f} / {B['pinball48']:6.3f}     {100*B['cov80_12']:4.0f}% / {100*B['cov80_48']:4.0f}%"
                f"            {B['brier12']:.3f} / {B['brier48']:.3f}      {100*(B['rangeErr'] or 0):4.0f}%       {v['live']['lambda']}")
    mdl = sc_.get("model")
    if mdl:
        from .scenario import verdict
        B = sc_["methods"][mdl["method"]]["B"]
        vd = verdict(B)
        cs = sc_["methods"][mdl["method"]].get("centers") or {}
        log("    środek — kandydaci (λ z części A, przewaga nad „bez zmiany” w części B): " + ", ".join(
            f"{k} λ {v['lambda']} → {100*v['centerS']:+.1f}%" for k, v in cs.items() if v.get("centerS") is not None))
        log(f"    → na żywo: {mdl['method']} (szerokość ×{mdl['f']}, środek λ = {mdl['lambda']}, {mdl.get('center', 'profile')}); "
            f"kierunek: {vd['direction']}; {vd['cone']}")
        log("    na instrument (ocena, pokrycie 80% / Brier k=48): " + ", ".join(
            f"{s} {100*x['cov80_48']:.0f}%/{x['brier48']:.3f}" for s, x in (B.get("inst") or {}).items()))
    for s, L in (res.get("last") or {}).items():
        pip = fi.INFO.get(s, {"pip": 1})["pip"]
        u = "pips" if fi.group_of(s) == "fx" else "USD"
        log(f"  {s}: środek +48 h {L['center48']/pip:+.1f} {u}, 80% w [{L['q10_48']/pip:+.1f}, {L['q90_48']/pip:+.1f}], "
            f"zakres 48 h {L['range']/pip:.1f} {u}, P(wzrost) {100*L['pUp48']:.0f}%")


def main() -> None:
    from .store import fx_repo
    from .sync import load_all, sync

    ap = argparse.ArgumentParser(description="FX-research — przeliczenie okoliczności FX 1h (4c.8)")
    ap.add_argument("--no-sync", action="store_true", help="bez synchronizacji z Firestore")
    ap.add_argument("--no-push", action="store_true", help="bez zapisu na GitHub")
    a = ap.parse_args()
    from ..ai.lock import guard
    guard("python -m ia4.fx.research")       # do ok. 3 GB pamięci — nie razem z modelem językowym (11c.2)

    print("IA 4 — FX-research (świece 1h)\n")
    repo = fx_repo(push=not a.no_push)
    repo.ensure()
    doc = cat.load_conditions(repo.root)
    if not doc:
        print(f"Brak fx/conditions.json ({cat.CATALOG}) na branchu fx — najpierw kalibracja: python -m ia4.fx.catalog --commit")
        sys.exit(1)
    conds = doc["conditions"]
    dfs = load_all() if a.no_sync else sync()
    runs_path = repo.dir / "runs.jsonl"
    n_runs = sum(1 for _ in runs_path.open(encoding="utf-8")) if runs_path.exists() else 0
    run_id = f"H-{n_runs + 1:03d}"
    print(f"\n  przeliczenie {run_id}, katalog {doc['catalog']} ({len(conds)} okoliczności)")
    res = run(dfs, conds)
    summary(res, conds)
    ratings_doc, run_line = documents(res, doc, run_id)
    save_local(res, conds, run_id)
    write_ratings(repo.dir / "ratings.json", ratings_doc)
    repo.append_jsonl("runs.jsonl", run_line)
    ok = repo.commit_push(f"fx: przeliczenie {run_id} ({res['pool'].T} świec, {len(res['pool'].syms)} instrumentów)")
    print("\n  lokalnie: data/fx1h/ratings-preview.csv, data/fx1h/occurrences.npz")
    if a.no_push:
        print("  zapisano w fx-repo/fx/ (bez push)")
    else:
        print("  zapisano na branchu fx: fx/ratings.json, fx/runs.jsonl" if ok else f"  ! push nieudany: {repo.last_error}")


if __name__ == "__main__":
    main()
