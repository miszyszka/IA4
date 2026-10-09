"""
IA 4 — test modułu prognozy EURUSD na danych syntetycznych (bez Firestore i GitHub).
Wersja projektu: 1.25 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

  python -m ia4.fx.selftest

Sprawdza:
  1. lustro — każda okoliczność `−` na serii zwykłej = jej para `+` na serii odbitej,
     a pary `+`/`−` mają dokładnie odbite wartości cech (wielkości antysymetryczne),
  2. brak zaglądania w przyszłość — okoliczności liczone na skróconej serii dają
     te same wartości na wspólnych świecach,
  3. kalibracja — dokładnie 500 par, każda okoliczność w 10–50%, ID i pary poprawne,
  4. powtarzalność — druga kalibracja na tych samych danych daje ten sam katalog,
  5. synchronizacja — dokument dnia w formacie 4b → tabela świec (z fillT), scalanie dni,
  6. FX-research — wystąpienia i profile = liczenie ręczne, rating i sprawdzian nie zaglądają
     w przyszłość, zasiany sygnał jest wykryty, czysty szum nie daje przewagi,
  7. FX-real-time — symulacja piątku wieczór → niedziela (atrapa Firestore i zegara): każda świeca
     wykryta, 2 odczyty na świecę, zero odczytów przy zamkniętym rynku, prognoza nie wychodzi poza
     zamknięcie, prognoza na żywo = prognoza z pełnego przeliczenia.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import catalog as cat
from . import research as rs
from . import series as sr
from .sync import doc_to_frame, merge_days

NY = ZoneInfo("America/New_York")


def market_open(ts: int) -> bool:
    d = datetime.fromtimestamp(ts, timezone.utc).astimezone(NY)
    wd, m = d.isoweekday(), d.hour * 60 + d.minute       # 1 = pon … 7 = nd
    if wd == 6:
        return False
    if wd == 7:
        return m >= 17 * 60
    if wd == 5:
        return m < 17 * 60
    return True


def synthetic(days: int = 63, seed: int = 7, trend: float = 0.15) -> pd.DataFrame:
    """EURUSD-podobna seria 5 min: zmienna zmienność, sezonowość w ciągu doby, trendy, braki uśrednione."""
    rng = np.random.default_rng(seed)
    start = int(datetime(2026, 8, 7, tzinfo=timezone.utc).timestamp())
    ts = [t for t in range(start, start + days * 86400, 300) if market_open(t)]
    n = len(ts)
    hour = (np.array(ts) // 3600) % 24
    season = 0.6 + 0.8 * np.exp(-((hour - 14) / 4.0) ** 2)            # Londyn/NY aktywniejsze
    vol = np.empty(n)
    v = 1.0
    for i in range(n):
        v = 0.98 * v + 0.02 * 1.0 + 0.08 * abs(rng.standard_normal()) - 0.064
        vol[i] = max(v, 0.3)
    drift = np.repeat(rng.normal(0, trend, n // 600 + 1), 600)[:n]     # zmienne trendy (pips/świecę); 0 = czysty szum
    step = (drift + rng.standard_t(5, n) * 2.2 * season * vol) * sr.PIP
    c = 1.17 + np.cumsum(step)
    o = np.concatenate([[c[0] - step[0]], c[:-1]])
    wig = np.abs(rng.normal(0, 1.2, (2, n))) * season * vol * sr.PIP
    h = np.maximum(o, c) + wig[0]
    l = np.minimum(o, c) - wig[1]
    filled = rng.random(n) < 0.003
    r6 = lambda x: np.round(x, 6)
    return pd.DataFrame({"time": np.array(ts, dtype=np.int64), "o": r6(o), "h": r6(h), "l": r6(l),
                         "c": r6(c), "filled": filled})


def planted(seed: int = 5, thr: float = 6.0, drift: float = 0.35, span: int = 24) -> pd.DataFrame:
    """Czysty szum + zasiany sygnał: po zmianie > 6 pips w 6 świecach cena dryfuje 0,35 pipsa na świecę
    w tę samą stronę przez 24 świece (lustrzanie dla spadku)."""
    df = synthetic(seed=seed, trend=0.0)
    c = df["c"].to_numpy()
    step = np.diff(c, prepend=c[0])
    add = np.zeros(c.size)
    out = c.copy()
    for i in range(1, c.size):
        out[i] = out[i - 1] + step[i] + add[i]
        if i >= 6:
            ch = (out[i] - out[i - 6]) / sr.PIP
            if abs(ch) > thr:
                add[i + 1: i + 1 + span] = np.sign(ch) * drift * sr.PIP
    sh = out - c
    df["c"] = df["c"] + sh
    df["o"] = df["o"] + np.concatenate([[0.0], sh[:-1]])
    df["h"] = np.maximum(df["h"] + sh, np.maximum(df["o"], df["c"]))
    df["l"] = np.minimum(df["l"] + sh, np.minimum(df["o"], df["c"]))
    return df


def live_check() -> bool:
    import json
    import tempfile
    from pathlib import Path
    from . import live as lv
    full = synthetic(days=66, seed=9)
    cut = int(datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc).timestamp())       # piątek 18:00 UTC
    hist = full[full["time"] < cut].reset_index(drop=True)
    conds = cat.calibrate(*sr.pair_of(hist), log=lambda *a: None)
    root = Path(tempfile.mkdtemp()) / "fx-repo"
    (root / "fx").mkdir(parents=True)
    (root / "fx" / "conditions.json").write_text(json.dumps(cat.document(conds, hist, "selftest")), encoding="utf-8")
    res = rs.run(hist, conds, log=lambda *a: None)
    rs.write_ratings(root / "fx" / "ratings.json", rs.documents(res, {"catalog": cat.CATALOG}, "R-001")[0])
    model = lv.Model(root)

    class Src:
        def __init__(s):
            s.reads, s.now, s.closed_reads = 0, 0, 0
        def _vis(s):
            return full[full["time"] + 300 + 21 <= s.now]
        def _count(s):
            s.reads += 1
            s.closed_reads += 0 if lv.market_open_now(s.now) else 1
        def last_time(s):
            s._count()
            return int(s._vis()["time"].iloc[-1])
        def days(s, dates):
            v, out = s._vis(), {}
            for d in dates:
                s._count()
                t0 = int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp())
                out[d] = v[(v["time"] >= t0) & (v["time"] < t0 + 86400)].reset_index(drop=True)
            return out

    class Out:
        def __init__(s):
            s.docs, s.last_error = [], ""
        def publish(s, d):
            s.docs.append(d)
            return True

    src, out, clock = Src(), Out(), {"t": cut + 60}
    def now():
        src.now = clock["t"]
        return clock["t"]
    L = lv.Live(hist, model, src, out, clock=now, log=lambda *a: None)
    L.recompute(now())
    end = int(datetime(2026, 10, 11, 22, 30, tzinfo=timezone.utc).timestamp())      # niedziela 22:30 UTC
    weekend = (int(datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc).timestamp()),
               int(datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc).timestamp()))
    new, lags = 0, []
    while clock["t"] < end:
        if weekend[0] <= clock["t"] < weekend[1]:          # środek weekendu — przeskok (nic się nie dzieje)
            clock["t"] = weekend[1]
        if L.step():
            new += 1
            lags.append(clock["t"] - (L.last_t + 300))
        clock["t"] += 30
    exp = full[(full["time"] >= cut) & (full["time"] + 300 + 21 <= end)]
    good = check("każda świeca wykryta, ok. 30 s po zamknięciu",
                 new == len(exp) and L.last_t == int(exp["time"].iloc[-1]) and max(lags) <= 31,
                 f"{new} z {len(exp)}, opóźnienie ≤ {max(lags)} s")
    good &= check("ok. 2 odczyty na świecę; przy zamkniętym rynku tylko ostatnia świeca piątku",
                  2 * len(exp) <= src.reads <= 2 * len(exp) + 3 and src.closed_reads <= 2, f"odczytów {src.reads}, przy zamkniętym {src.closed_reads}, oczekiwanych {2 * len(exp)}")
    fri = [d for d in out.docs if d.get("lastCandle", "").startswith("2026-10-09T20:")]
    lim = int(datetime(2026, 10, 9, 21, 0, tzinfo=timezone.utc).timestamp())
    good &= check("prognoza kończy się na zamknięciu rynku (pt 21:00 UTC)",
                  bool(fri) and all(f[0] < lim for d in fri for f in d["forecast"]) and fri[-1]["forecast"] == [])
    Sp, Sm = sr.pair_of(L.df)                          # prognoza na żywo = to samo z pełnego przeliczenia
    M = cat.evaluate(model.conds, Sp, Sm)
    ref = rs.forecast_from(M[:, -1], model.ratings, model.profiles)
    got = lv.compute(L.df, model)["forecast"]
    c = float(L.df["c"].iloc[-1])
    good &= check("prognoza na żywo = przeliczenie od zera",
                  all(abs(p - round(c + sr.PIP * ref[i], 6)) < 1e-9 for i, (_, p) in enumerate(got)), f"{len(got)} punktów")
    return good


def check(name: str, ok: bool, info: str = "") -> bool:
    print(f"  {'✓' if ok else '✗'} {name}{(' — ' + info) if info else ''}")
    return ok


def main() -> None:
    print("IA 4 — selftest modułu prognozy EURUSD (dane syntetyczne)\n")
    ok = True
    df = synthetic()
    print(f"  seria: {len(df)} świec, {int(df['filled'].sum())} uśrednionych, przerw: "
          f"{int(sr.gap_after(df['time'].to_numpy()).sum())}")

    # 5. synchronizacja — dokument dnia
    day = "2026-08-11"
    t0 = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
    part = df[(df["time"] >= t0) & (df["time"] < t0 + 86400)]
    doc = {"date": day, "t": [int((t - t0) // 60) for t in part["time"]],
           "o": part["o"].tolist(), "h": part["h"].tolist(), "l": part["l"].tolist(), "c": part["c"].tolist(),
           "fillT": [int((t - t0) // 60) for t in part["time"][part["filled"]]]}
    back = doc_to_frame(doc)
    ok &= check("dokument dnia → świece", back.reset_index(drop=True).equals(part.reset_index(drop=True)),
                f"{len(back)} świec")
    broken = df.copy()
    broken.loc[broken["time"].between(t0, t0 + 86399), "c"] += 0.01
    merged = merge_days(broken[broken["time"] < t0 + 86400 * 2], {day: back})
    ok &= check("scalanie: dzień z Firestore zastępuje dzień lokalny",
                merged.reset_index(drop=True).equals(df[df["time"] < t0 + 86400 * 2].reset_index(drop=True)))

    # 3. kalibracja
    Sp, Sm = sr.pair_of(df)
    t = time.time()
    conds = cat.calibrate(Sp, Sm, log=lambda *a: print(*a))
    print(f"  kalibracja: {time.time() - t:.1f} s")
    cov = np.array([c["coverage"] for c in conds])
    ok &= check("1000 okoliczności = 500 par", len(conds) == 1000 and
                sum(c["dir"] == "+" for c in conds) == 500 and sum(c["dir"] == "−" for c in conds) == 500)
    ok &= check("każda okoliczność w 10–50%", bool(((cov >= 0.10) & (cov <= 0.50)).all()),
                f"{100*cov.min():.1f}–{100*cov.max():.1f}%, średnio {100*cov.mean():.1f}%")
    ids_ok = all(c["id"] == f"FX-{i+1:04d}" for i, c in enumerate(conds))
    pair_ok = all(conds[i]["pair"] == conds[i + 1]["id"] and conds[i + 1]["pair"] == conds[i]["id"] and
                  conds[i]["dir"] == "+" and conds[i + 1]["dir"] == "−" for i in range(0, 1000, 2))
    ok &= check("ID FX-0001…FX-1000 i pary (nieparzysty `+`, parzysty `−`)", ids_ok and pair_ok)
    for name, q, npairs, lo, mu, hi in cat.family_summary(conds):
        print(f"      {name:46s} limit {q:3d}  par {npairs:3d}   {100*lo:4.1f}–{100*hi:4.1f}%")

    # 1. lustro
    M = cat.evaluate(conds, Sp, Sm)
    Sp2, Sm2 = sr.pair_of(df)                       # świeże serie — bez wspólnej pamięci
    mirror = [dict(c, dir="+" if c["dir"] == "−" else "−") for c in conds]
    M2 = cat.evaluate(mirror, Sm2, Sp2)             # zamienione strony = ta sama macierz
    ok &= check("lustro: strona `−` = cecha na serii odbitej", bool((M == M2).all()))
    worst = 0.0
    for kind, p in {(c["kind"], tuple(sorted(c["p"].items()))) for c in conds}:
        if cat.KINDS[kind][1] or kind.startswith("combo") or kind == "dist_high" or \
                (kind == "prev_day" and dict(p)["ref"] != "close"):
            continue        # całkowite, warunkowe i maksimum↔minimum — lustro nie jest zmianą znaku
        fp, fm = cat.feature(Sp, kind, dict(p)), cat.feature(Sm, kind, dict(p))
        both = np.isfinite(fp) & np.isfinite(fm)
        if both.any():
            err = np.abs(fp[both] + fm[both]) - 1e-6 * np.abs(fp[both])
            worst = max(worst, float(err.max()))
        worst = max(worst, float((np.isfinite(fp) != np.isfinite(fm)).sum()))
    ok &= check("lustro: cechy ciągłe antysymetryczne f(odbita) = −f", worst < 1e-9, f"największy błąd {worst:.1e}")

    # 2. brak zaglądania w przyszłość
    cut = len(df) - 777
    Sp3, Sm3 = sr.pair_of(df.iloc[:cut])
    M3 = cat.evaluate(conds, Sp3, Sm3)
    diff = int((M3 != M[:, :cut]).sum())
    ok &= check("brak zaglądania w przyszłość (seria skrócona o 777 świec)", diff == 0, f"różnic: {diff}")

    # 4. powtarzalność
    conds2 = cat.calibrate(*sr.pair_of(df), log=lambda *a: None)
    same = [(c["id"], c["kind"], c["p"], c["theta"]) for c in conds] == \
           [(c["id"], c["kind"], c["p"], c["theta"]) for c in conds2]
    ok &= check("powtarzalność kalibracji", same)

    # 6. FX-research
    print("  FX-research:")
    res = rs.run(df, conds, log=lambda *a: None)
    R, okm = res["R"], rs.occurrence_ok(Sp.time, Sp.filled)
    good = True
    for i in (0, 333, 777, 999):                    # liczenie ręczne, pętlami
        idx = [t for t in range(len(df)) if M[i, t] and t >= sr.WARMUP and not Sp.filled[t]
               and not any(Sp.time[u + 1] - Sp.time[u] > sr.GAP_SEC for u in range(t, min(t + 48, len(df) - 1)))]
        prof = []
        for k in range(1, 49):
            v = [(Sp.c[t + k] - Sp.c[t]) / sr.PIP for t in idx if t + k < len(df) and not Sp.filled[t + k]]
            prof.append(sum(v) / len(v) if v else None)
        row = res["rows"][i]
        good &= row["n"] == len(idx) and all((a is None and b is None) or abs(a - b) < 0.006
                                            for a, b in zip(prof, row["profile"]))
    ok &= check("wystąpienia i profile = liczenie ręczne (4 okoliczności)", good)
    T = len(df)
    s70 = int(rs.SPLIT_CHECK * T)
    rat1, prof1 = rs.check_model(M, R, okm, s70)
    R2 = R.copy()
    R2[:] = np.where(np.arange(T)[:, None] + np.arange(1, 49)[None, :] >= s70, R2 + 37.0, R2)  # zmiana przyszłości
    rat2, prof2 = rs.check_model(M, R2, okm, s70)
    ok &= check("sprawdzian: ratingi i profile nie widzą świec po 70%",
                bool((rat1 == rat2).all() and np.array_equal(np.isnan(prof1), np.isnan(prof2))
                     and np.allclose(np.nan_to_num(prof1), np.nan_to_num(prof2))))
    for name, data in (("czysty szum", synthetic(seed=21, trend=0.0)), ("zasiany sygnał", planted())):
        cs = cat.calibrate(*sr.pair_of(data), log=lambda *a: None)
        rr = rs.run(data, cs, log=lambda *a: None)
        rt = np.array([r["rating"] for r in rr["rows"]])
        S = rr["check"]["S"]["all"]
        info = (f"ratingi > 50: {int((rt > 50).sum())}, sprawdzian: przewaga {100*S:.2f}%, "
                f"kierunek k=12 {100*rr['check']['hit']['12']:.1f}%")
        if name == "czysty szum":
            ok &= check("czysty szum: brak przewagi", S < 0.005 and (rt > 50).sum() <= 10, info)
        else:
            ok &= check("zasiany sygnał: wykryty", S > 0.02 and (rt > 50).sum() >= 100, info)

    # 7. FX-real-time
    print("  FX-real-time:")
    ok &= live_check()

    print("\nWYNIK:", "OK" if ok else "BŁĄD")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
