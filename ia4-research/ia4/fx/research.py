"""
IA 4 — FX-research: wystąpienia, profile, ratingi i sprawdzian okoliczności EURUSD
(instrukcja, sekcje 4c.4–4c.8).
Wersja projektu: 1.26 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

  python -m ia4.fx.research              # synchronizacja, przeliczenie od zera, zapis i push na branch fx
  python -m ia4.fx.research --no-sync    # bez Firestore (kopia lokalna)
  python -m ia4.fx.research --no-push    # bez GitHub (wynik tylko lokalnie)

Tylko ręcznie. Każde uruchomienie liczy WSZYSTKO od nowa na całej kopii lokalnej
— katalog okoliczności jest stały (fx/conditions.json), zmieniają się tylko dane.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone

import numpy as np
from numba import njit

from . import catalog as cat
from . import series as sr
from .series import PIP

H = 48                     # horyzont: 48 świec (4 godziny)
FOLDS = 5                  # 4c.5: walk-forward — seria w 5 równych częściach, ocena na częściach 2–5
SPLIT_CHECK = 0.70         # 4c.7: sprawdzian — ratingi z 0–70%, zapytania (scenariusze) na 70–100%
SHRINK = 20                # 4c.5: S* = S · n / (n + 20)
RATING_FULL = 0.05         # 4c.5: S* = 0,05 → rating 100
MIN_TRAIN = 30             # 4c.5: mniej wystąpień w części uczącej → rating 1
MIN_IND = 5                # 4c.5: mniej niezależnych wystąpień w części oceny → rating 1


# ===========================================================================
#  Dane: przyszłe zmiany i świece, które mogą być wystąpieniem (4c.4)
# ===========================================================================
def future_changes(c: np.ndarray, filled: np.ndarray) -> np.ndarray:
    """R[t, k−1] = (c[t+k] − c[t]) / pips dla k = 1…48; NaN, gdy świeca t+k nie istnieje
    albo jest uśredniona."""
    T = c.size
    R = np.full((T, H), np.nan, dtype=np.float64)
    for k in range(1, H + 1):
        if k >= T:
            break
        d = (c[k:] - c[:-k]) / PIP
        d[filled[k:]] = np.nan
        R[: T - k, k - 1] = d
    return R


def occurrence_ok(time_: np.ndarray, filled: np.ndarray) -> np.ndarray:
    """Świeca może być wystąpieniem: po rozgrzewce, nie uśredniona, w oknie t … t+48 bez przerwy."""
    T = time_.size
    gap = sr.gap_after(time_).astype(np.int64)            # przerwa między i a i+1
    cs = np.concatenate([[0], np.cumsum(gap)])
    end = np.minimum(np.arange(T) + H, T - 1)             # okno kończy się na ostatniej istniejącej świecy
    has_gap = (cs[end] - cs[np.arange(T)]) > 0            # przerwy między t a end
    ok = ~filled & ~has_gap
    ok[: sr.WARMUP] = False
    return ok


@njit(cache=True)
def n_independent(idx):
    """Wystąpienia wybierane od najstarszego, każde ≥ 48 świec po poprzednim wybranym."""
    n = 0
    last = -10 ** 9
    for t in idx:
        if t - last >= 48:
            n += 1
            last = t
    return n


# ===========================================================================
#  Profil i rating jednej okoliczności
# ===========================================================================
def profile(R: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Średnia zmiana dla k = 1…48 z wystąpień idx (NaN, gdy dla k nie ma żadnej)."""
    if idx.size == 0:
        return np.full(H, np.nan)
    with np.errstate(invalid="ignore"):
        x = R[idx]
        cnt = np.isfinite(x).sum(0)
        s = np.nansum(x, 0)
        return np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)


def rate(R: np.ndarray, idx: np.ndarray, end: int) -> dict:
    """4c.5 — walk-forward na świecach [0, end): seria dzielona na FOLDS równych części; dla części
    j = 2…FOLDS profil uczący z wystąpień, których okno kończy się przed jej początkiem, ocena na
    wystąpieniach części j (zmiany tylko do jej końca). Błędy sumowane po wszystkich częściach."""
    edges = [int(end * j / FOLDS) for j in range(FOLDS + 1)]
    ec = e0 = 0.0
    n_ind = tr_n = ev_n = 0
    k = np.arange(1, H + 1)[None, :]
    for j in range(1, FOLDS):
        a, b = edges[j], edges[j + 1]
        tr = idx[idx + H < a]
        ev = idx[(idx >= a) & (idx < b)]
        if tr.size < MIN_TRAIN or ev.size == 0:
            continue
        P = profile(R, tr)
        r = R[ev].copy()
        r[(ev[:, None] + k) >= b] = np.nan                     # nie zaglądamy za koniec części
        use = np.isfinite(r) & np.isfinite(P)[None, :]
        e0 += np.abs(r[use]).sum()
        ec += np.abs((r - P[None, :])[use]).sum()
        n_ind += n_independent(ev)
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
    """Średnia profili okoliczności prawdziwych ważona ratingiem (pipsy). active: (N,) albo (T, N)."""
    a = np.atleast_2d(active).astype(np.float64) * ratings[None, :]
    P0 = np.nan_to_num(profiles, nan=0.0)
    Pm = np.isfinite(profiles).astype(np.float64)
    num, den = a @ P0, a @ Pm
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den > 0, num / den, np.nan)
    return out[0] if np.ndim(active) == 1 else out


def model_until(M: np.ndarray, R: np.ndarray, ok: np.ndarray, end: int):
    """Ratingi (walk-forward, 4c.5) i profile policzone wyłącznie ze świec, których okna kończą się przed `end`."""
    rat = np.ones(M.shape[0])
    prof = np.full((M.shape[0], H), np.nan)
    for i in range(M.shape[0]):
        idx = np.flatnonzero(M[i] & ok)
        rat[i] = rate(R, idx, end)["rating"]
        prof[i] = profile(R, idx[idx + H < end])
    return rat, prof


# ===========================================================================
#  Przeliczenie całości
# ===========================================================================
def run(df, conds: list[dict], log=print) -> dict:
    from . import scenario as sc
    from ..lab import indicators as ind
    t0 = time.time()
    Sp, Sm = sr.pair_of(df)
    M = cat.evaluate(conds, Sp, Sm)
    c, filled, tm = Sp.c, Sp.filled, Sp.time
    R = future_changes(c, filled)
    ok = occurrence_ok(tm, filled)
    el = cat.eligible(Sp)
    T = c.size
    log(f"  okoliczności policzone: {len(conds)} × {T} świec ({time.time() - t0:.1f} s)")

    rows, occ_ptr, occ_t = [], [0], []
    ratings = np.ones(len(conds))
    profiles = np.full((len(conds), H), np.nan)
    for i, cd in enumerate(conds):
        idx = np.flatnonzero(M[i] & ok)
        rt = rate(R, idx, T)
        prof = profile(R, idx)
        profiles[i] = prof
        ratings[i] = rt["rating"]
        cov = float(M[i][el].mean()) if el.any() else 0.0
        rows.append({"id": cd["id"], "rating": rt["rating"], "n": int(idx.size), "n_ind": int(n_independent(idx)),
                     "train_n": rt["train_n"], "eval_n": rt["eval_n"], "eval_ind": rt["eval_ind"],
                     "S": round(rt["S"], 5), "Sstar": round(rt["Sstar"], 5), "coverage": round(cov, 4),
                     "flag": "" if cat.RANGE[0] <= cov <= cat.RANGE[1] else "częstość poza zakresem",
                     "profile": [None if not np.isfinite(v) else round(float(v), 2) for v in prof]})
        occ_t.append(idx.astype(np.int32))
        occ_ptr.append(occ_ptr[-1] + idx.size)
    log(f"  wystąpienia, profile i ratingi ({time.time() - t0:.1f} s)")

    U100, U12 = Sp.U, ind.atr(Sp.h, Sp.l, Sp.c, 12)
    s70 = int(sc_split() * T)
    rat70, prof70 = model_until(M, R, ok, s70)                       # sprawdzian: tylko przeszłość
    PM = np.full((T, H), np.nan)
    PM[s70:] = forecast_from(M[:, s70:].T, rat70, prof70)
    check = sc.check(sc.Engine(tm, R, ok, M, rat70, U100, U12), PM, start_frac=sc_split())
    log(f"  sprawdzian prognozy rozkładu: {check.get('queries', 0)} zapytań ({time.time() - t0:.1f} s)")
    last = None
    if check.get("model"):
        mdl = check["model"]
        eng = sc.Engine(tm, R, ok, M, ratings, U100, U12)
        a = eng.select(T - 1, T, mdl["method"])
        if a.size >= 10:
            center = mdl["lambda"] * np.nan_to_num(forecast_from(M[:, -1], ratings, profiles), nan=0.0)
            d = sc.distribution(eng.paths(T - 1, a), center, mdl["f"])
            last = {"center48": round(float(d["center"][-1]), 2), "q10_48": round(float(d["q"][10][-1]), 2),
                    "q90_48": round(float(d["q"][90][-1]), 2), "range": round(d["range"], 1)}
    return {"rows": rows, "scenario": check, "last": last, "M_last": M[:, -1], "R": R,
            "occ_ptr": np.array(occ_ptr, dtype=np.int64), "occ_t": np.concatenate(occ_t) if occ_t else np.zeros(0, np.int32),
            "time": tm, "c": c, "candles": T}


def sc_split() -> float:
    return SPLIT_CHECK


# ===========================================================================
#  Zapis
# ===========================================================================
def iso(t: int) -> str:
    return datetime.fromtimestamp(int(t), timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def documents(res: dict, conds_doc: dict, run_id: str) -> tuple[dict, dict]:
    from .. import __version__
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tm = res["time"]
    data = {"from": iso(tm[0]), "to": iso(tm[-1]), "candles": int(res["candles"])}
    rating_cfg = {"method": "walk-forward", "folds": FOLDS,  "shrink": SHRINK, "full": RATING_FULL, "minTrain": MIN_TRAIN,
                  "minInd": MIN_IND, "horizon": H}
    sc_ = res["scenario"] or {}
    mdl = sc_.get("model") or {}
    best = (sc_.get("methods") or {}).get(mdl.get("method"), {}).get("B") or {}
    ratings_doc = {"run": run_id, "at": now, "version": __version__, "catalog": conds_doc["catalog"],
                   "data": data, "rating": rating_cfg, "scenario": sc_,
                   "lastCandle": {"time": iso(tm[-1]), "close": float(res["c"][-1]),
                                  "active": int(res["M_last"].sum()), "forecast": res["last"]},
                   "conditions": res["rows"]}
    pin = {m: ((sc_.get("methods") or {}).get(m, {}).get("B") or {}).get("pinball48") for m in ("analogi", "pora", "całość")}
    run_line = {"run": run_id, "at": now, "version": __version__, "data": data,
                "scenario": {"model": mdl.get("method"), "f": mdl.get("f"), "lambda": mdl.get("lambda"),
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
    from .sync import FX_DIR
    FX_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(FX_DIR / "occurrences.npz", run=run_id, ids=np.array([c["id"] for c in conds]),
                        time=res["time"], R=res["R"].astype(np.float32),
                        occ_ptr=res["occ_ptr"], occ_t=res["occ_t"])
    with open(FX_DIR / "ratings-preview.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ID", "Kierunek", "Rodzina", "Okoliczność", "Rating", "Wystąpień", "Niezależnych",
                    "Przewaga S %", "Częstość %", "Uwagi", "Profil k=12 (pips)", "Profil k=48 (pips)"])
        for c, r in zip(conds, res["rows"]):
            p = r["profile"]
            fmt = lambda v: "" if v is None else f"{v}".replace(".", ",")
            w.writerow([c["id"], c["dir"], c["familyName"], c["desc"], r["rating"], r["n"], r["n_ind"],
                        f"{100 * r['S']:.2f}".replace(".", ","), f"{100 * r['coverage']:.1f}".replace(".", ","),
                        r["flag"], fmt(p[11]), fmt(p[47])])


def load_occurrences(cond_id: str):
    """Wystąpienia jednej okoliczności z ostatniego przeliczenia: tabela (czas świecy, k = 1…48 w pipsach)
    + średnia — struktura „ID → wystąpienie → 48 przyszłych zmian” (4c.4)."""
    import pandas as pd
    from .sync import FX_DIR
    z = np.load(FX_DIR / "occurrences.npz")
    i = int(np.flatnonzero(z["ids"] == cond_id)[0])
    t = z["occ_t"][z["occ_ptr"][i]: z["occ_ptr"][i + 1]]
    df = pd.DataFrame(z["R"][t], columns=[f"k{k}" for k in range(1, H + 1)])
    df.insert(0, "time", pd.to_datetime(z["time"][t], unit="s", utc=True))
    return df


def summary(res: dict, conds: list[dict], log=print) -> None:
    rows = res["rows"]
    rt = np.array([r["rating"] for r in rows])
    log(f"\n  ratingi: 1 → {int((rt == 1).sum())}, 2–20 → {int(((rt > 1) & (rt <= 20)).sum())}, "
        f"21–50 → {int(((rt > 20) & (rt <= 50)).sum())}, 51–100 → {int((rt > 50).sum())}")
    flags = sum(1 for r in rows if r["flag"])
    log(f"  częstość poza 10–50%: {flags}")
    top = sorted(range(len(rows)), key=lambda i: (-rows[i]["rating"], -rows[i]["S"]))[:15]
    log("\n  najwyższe ratingi:")
    for i in top:
        r = rows[i]
        log(f"    {r['id']} {r['rating']:3d}/{r['n']:<5d} S {100*r['S']:5.2f}%  {conds[i]['desc']}")
    sc_ = res["scenario"] or {}
    log(f"\n  sprawdzian prognozy rozkładu (walk-forward: kalibracja 70–85%, ocena 85–100% serii, "
        f"{sc_.get('queries', 0)} zapytań co {sc_.get('every', '?')} świece):")
    log("    metoda     pinball k=12 / k=48   pokrycie 80% k=12 / k=48   Brier k=48   błąd zakresu   środek λ")
    for m, v in (sc_.get("methods") or {}).items():
        B = v.get("B")
        if B:
            log(f"    {m:9s}  {B['pinball12']:6.3f} / {B['pinball48']:6.3f}     {100*B['cov80_12']:4.0f}% / {100*B['cov80_48']:4.0f}%"
                f"               {B['brier48']:.4f}       {100*(B['rangeErr'] or 0):4.0f}%       {v['live']['lambda']}")
    mdl = sc_.get("model")
    if mdl:
        from .scenario import verdict
        vd = verdict(sc_["methods"][mdl["method"]]["B"])
        log(f"    → na żywo: {mdl['method']} (szerokość ×{mdl['f']}, środek λ = {mdl['lambda']}); "
            f"kierunek: {vd['direction']}; {vd['cone']}")
    if res.get("last"):
        L = res["last"]
        log(f"  z ostatniej świecy: środek +4 h {L['center48']:+.1f} pips, 80% w [{L['q10_48']:+.1f}, {L['q90_48']:+.1f}], "
            f"oczekiwany zakres 4 h {L['range']:.1f} pips")


def main() -> None:
    from .store import fx_repo
    from .sync import load, sync

    ap = argparse.ArgumentParser(description="FX-research — przeliczenie okoliczności EURUSD (4c.8)")
    ap.add_argument("--no-sync", action="store_true", help="bez synchronizacji z Firestore")
    ap.add_argument("--no-push", action="store_true", help="bez zapisu na GitHub")
    a = ap.parse_args()

    print("IA 4 — FX-research\n")
    repo = fx_repo(push=not a.no_push)
    repo.ensure()
    doc = cat.load_conditions(repo.root)
    if not doc:
        print("Brak fx/conditions.json na branchu fx — najpierw kalibracja: python -m ia4.fx.catalog --commit")
        sys.exit(1)
    conds = doc["conditions"]
    from .live import publish_dashboard
    if publish_dashboard(repo):
        print("  dashboard zaktualizowany na branchu fx (index.html)")
    df = load() if a.no_sync else sync()
    runs_path = repo.dir / "runs.jsonl"
    n_runs = sum(1 for _ in runs_path.open(encoding="utf-8")) if runs_path.exists() else 0
    run_id = f"R-{n_runs + 1:03d}"
    print(f"  przeliczenie {run_id}, katalog {doc['catalog']} ({len(conds)} okoliczności)")
    res = run(df, conds)
    summary(res, conds)
    ratings_doc, run_line = documents(res, doc, run_id)
    save_local(res, conds, run_id)
    write_ratings(repo.dir / "ratings.json", ratings_doc)
    repo.append_jsonl("runs.jsonl", run_line)
    ok = repo.commit_push(f"fx: przeliczenie {run_id} ({res['candles']} świec)")
    print(f"\n  lokalnie: data/fx/ratings-preview.csv, data/fx/occurrences.npz")
    if a.no_push:
        print(f"  zapisano w fx-repo/fx/ (bez push)")
    else:
        print("  zapisano na branchu fx: fx/ratings.json, fx/runs.jsonl" if ok else f"  ! push nieudany: {repo.last_error}")


if __name__ == "__main__":
    main()
