"""
IA 4 — test modułu prognozy FX 1h na danych syntetycznych (bez Firestore i GitHub).
Wersja projektu: 1.58 (2026-10-21) — musi zgadzać się z IA4_INSTRUKCJA.md

  python -m ia4.fx.selftest

Dane: 2 pary walutowe (godziny rynku, weekend) i BTC (24/7), świece 1h, ok. 14 miesięcy (ia4/fx/synth.py).
Sprawdza:
  1. synchronizacja — dokument dnia w formacie 4b → tabela świec (z fillT), scalanie dni,
  2. seria — weekend nie jest przerwą, brak świecy rynku jest; doby i tygodnie handlowe od 17:00 Nowy Jork,
  3. kalibracja — 500 par na puli instrumentów, każda okoliczność w 10–50%, ID i pary, powtarzalność,
  4. lustro i brak zaglądania w przyszłość — na każdym instrumencie,
  5. FX-research — wystąpienia i profile (ATR100) = liczenie ręczne; ratingi, profile i dobór ścieżek
     nie zaglądają w przyszłość (kalendarz); pula: pora = ten instrument, analogi = ta sama grupa,
     odstęp ≥ 12 h; czysty szum → płaski środek i trafny stożek, zasiany sygnał → środek z przewagą,
  6. FX-real-time — symulacja piątek → niedziela (atrapa Firestore i zegara): każda świeca wykryta,
     zero odczytów, gdy nic nie przybywa, prognoza par walutowych przeskakuje weekend (48 świec rynku),
     dane na żywo = pełne pobranie, prognoza = przeliczenie od zera.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import catalog as cat
from . import instruments as fi
from . import research as rs
from . import scenario as sc
from . import series as sr
from . import synth
from .sync import doc_to_frame, merge_days


def check(name: str, ok: bool, info: str = "") -> bool:
    print(f"  {'✓' if ok else '✗'} {name}{(' — ' + info) if info else ''}")
    return bool(ok)


def ts(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


# ======================================================================= 1–2
def test_data() -> bool:
    ok = True
    df = synth.synthetic("EURUSD", days=60)
    day = "2026-09-16"
    t0 = ts(day + "T00:00:00Z")
    part = df[(df["time"] >= t0) & (df["time"] < t0 + 86400)]
    doc = {"date": day, "t": [int((t - t0) // 60) for t in part["time"]], "o": part["o"].tolist(),
           "h": part["h"].tolist(), "l": part["l"].tolist(), "c": part["c"].tolist(),
           "fillT": [int((t - t0) // 60) for t in part["time"][part["filled"]]]}
    back = doc_to_frame(doc)
    ok &= check("dokument dnia (t w minutach: 0, 60, …) → świece 1h", back.reset_index(drop=True).equals(part.reset_index(drop=True)),
                f"{len(back)} świec")
    broken = df.copy()
    broken.loc[broken["time"].between(t0, t0 + 86399), "c"] += 0.01
    merged = merge_days(broken[broken["time"] < t0 + 86400 * 2], {day: back})
    ok &= check("scalanie: dzień z Firestore zastępuje dzień lokalny",
                merged.reset_index(drop=True).equals(df[df["time"] < t0 + 86400 * 2].reset_index(drop=True)))
    t = df["time"].to_numpy()
    g = sr.gap_after(t, "fx")
    hole = np.delete(t, 300)
    ok &= check("przerwa: weekend nie jest przerwą, brak świecy rynku jest", g.sum() == 0 and sr.gap_after(hole, "fx").sum() == 1,
                f"{len(t)} świec, weekendów {int((np.diff(t) > 3600).sum())}")
    wk = sr.day_ids(t, "week")
    starts = pd.to_datetime(t[np.flatnonzero(np.diff(wk)) + 1], unit="s", utc=True).tz_convert("America/New_York")
    ok &= check("tydzień handlowy od niedzieli 17:00 Nowy Jork", all(x.dayofweek == 6 and x.hour == 17 for x in starts),
                f"{len(starts)} tygodni")
    nxt = fi.next_slots("fx", ts("2026-10-09T19:00:00Z"), 3)
    ok &= check("48 świec do przodu: po piątku 20:00 UTC następna w niedzielę 21:00 UTC (czas letni)",
                nxt[1] == ts("2026-10-11T21:00:00Z") and fi.next_slots("crypto", ts("2026-10-09T19:00:00Z"), 2)[1] == ts("2026-10-09T21:00:00Z"))
    return ok


# ======================================================================= 3–4
def test_catalog():
    ok = True
    U = synth.universe("noise")
    pairs = [sr.pair_of(d, s) for s, d in U.items()]
    t = time.time()
    conds = cat.calibrate(pairs, log=lambda *a: print(*a))
    print(f"  kalibracja: {time.time() - t:.1f} s, instrumenty: " + ", ".join(f"{s} {len(d)}" for s, d in U.items()))
    cov = np.array([c["coverage"] for c in conds])
    ok &= check("1000 okoliczności = 500 par", len(conds) == 1000 and sum(c["dir"] == "+" for c in conds) == 500)
    ok &= check("każda okoliczność w 10–50% (pula)", bool(((cov >= 0.10) & (cov <= 0.50)).all()),
                f"{100*cov.min():.1f}–{100*cov.max():.1f}%, średnio {100*cov.mean():.1f}%; na instrumencie "
                f"{100*min(c['covInstMin'] for c in conds):.0f}–{100*max(c['covInstMax'] for c in conds):.0f}%")
    ids_ok = all(c["id"] == f"FX-{i+1:04d}" for i, c in enumerate(conds))
    pair_ok = all(conds[i]["pair"] == conds[i + 1]["id"] and conds[i]["dir"] == "+" and conds[i + 1]["dir"] == "−"
                  for i in range(0, 1000, 2))
    ok &= check("ID FX-0001…FX-1000 i pary (nieparzysty `+`, parzysty `−`)", ids_ok and pair_ok)
    for name, q, npairs, lo, mu, hi in cat.family_summary(conds):
        print(f"      {name:46s} limit {q:3d}  par {npairs:3d}   {100*lo:4.1f}–{100*hi:4.1f}%")
    bad_m = bad_f = 0
    worst = 0.0
    for (s, d), (Sp, Sm) in zip(U.items(), pairs):
        M = cat.evaluate(conds, Sp, Sm)
        Sp2, Sm2 = sr.pair_of(d, s)
        mirror = [dict(c, dir="+" if c["dir"] == "−" else "−") for c in conds]
        bad_m += int((cat.evaluate(mirror, Sm2, Sp2) != M).sum())
        cut = len(d) - 333
        Sp3, Sm3 = sr.pair_of(d.iloc[:cut], s)
        bad_f += int((cat.evaluate(conds, Sp3, Sm3) != M[:, :cut]).sum())
        for kind, p in {(c["kind"], tuple(sorted(c["p"].items()))) for c in conds}:
            if cat.KINDS[kind][1] or kind.startswith("combo") or kind == "dist_high" or \
                    (kind == "prev_day" and dict(p)["ref"] != "close"):
                continue
            fp, fm = cat.feature(Sp, kind, dict(p)), cat.feature(Sm, kind, dict(p))
            both = np.isfinite(fp) & np.isfinite(fm)
            if both.any():
                worst = max(worst, float((np.abs(fp[both] + fm[both]) - 1e-6 * np.abs(fp[both])).max()))
            worst = max(worst, float((np.isfinite(fp) != np.isfinite(fm)).sum()))
    ok &= check("lustro: strona `−` = cecha na serii odbitej (każdy instrument)", bad_m == 0, f"różnic {bad_m}")
    ok &= check("lustro: cechy ciągłe antysymetryczne f(odbita) = −f", worst < 1e-9, f"największy błąd {worst:.1e}")
    ok &= check("brak zaglądania w przyszłość (każda seria skrócona o 333 świece)", bad_f == 0, f"różnic {bad_f}")
    conds2 = cat.calibrate([sr.pair_of(d, s) for s, d in U.items()], log=lambda *a: None)
    ok &= check("powtarzalność kalibracji", [(c["id"], c["kind"], c["p"], c["theta"]) for c in conds] ==
                [(c["id"], c["kind"], c["p"], c["theta"]) for c in conds2])
    return ok, U, conds


# ======================================================================= 5
def test_research(U, conds) -> bool:
    ok = True
    P = rs.Pool(U, conds)
    good = True
    for i in (0, 333, 777, 999):                                  # liczenie ręczne, pętlami
        idx, vals = [], {k: [] for k in range(1, 49)}
        for j, s in enumerate(P.syms):
            d = U[s]
            t_, c_, f_ = d["time"].to_numpy(), d["c"].to_numpy(), d["filled"].to_numpy()
            Sp, _ = sr.pair_of(d, s)
            Uv = Sp.U
            gap = sr.gap_after(t_, fi.group_of(s))
            Mi = P.M[i, P.start[j]:P.end[j]]
            for t in range(len(d)):
                if not Mi[t] or t < sr.WARMUP or f_[t] or gap[t:min(t + 48, len(d) - 1)].any():
                    continue
                idx.append((j, t))
                for k in range(1, 49):
                    if t + k < len(d) and not f_[t + k]:
                        vals[k].append((c_[t + k] - c_[t]) / Uv[t])
        prof = rs.profile(P.R, np.flatnonzero(P.M[i] & P.ok))
        man = np.array([np.mean(vals[k]) if vals[k] else np.nan for k in range(1, 49)])
        good &= len(idx) == int((P.M[i] & P.ok).sum()) and np.allclose(prof, man, equal_nan=True)
    ok &= check("wystąpienia i profile (ATR100) = liczenie ręczne (4 okoliczności, 3 instrumenty)", good)
    t70 = P.time_at(rs.SPLIT_CHECK)
    rat1, prof1 = rs.model_until(P, t70)
    R0 = P.R.copy()
    P.R = np.where(P.tk >= t70, P.R + 37.0, P.R)                  # zmiana przyszłości (po granicy w kalendarzu)
    rat2, prof2 = rs.model_until(P, t70)
    P.R = R0
    ok &= check("sprawdzian: ratingi i profile nie widzą świec po 70% kalendarza",
                bool((rat1 == rat2).all() and np.allclose(np.nan_to_num(prof1), np.nan_to_num(prof2))))
    eng = sc.Engine(P, rat1)
    bad = 0
    rng = np.random.default_rng(1)
    for t in rng.choice(np.flatnonzero(eng.cand & (P.time >= t70)), 30, replace=False):
        for m in ("analogi", "pora"):
            a = eng.select(int(t), int(P.time[t]), m)
            dh = np.abs(eng.hour[a] - eng.hour[t])
            tt = np.sort(P.time[a])
            bad += int((eng.end[a] >= P.time[t]).any() or (np.minimum(dh, 24 - dh) > 1).any() or a.size < 10
                       or (np.diff(tt) < 12 * 3600).any())
            if m == "pora":
                bad += int((P.inst[a] != P.inst[t]).any())
            else:
                bad += int((eng.gid[a] != eng.gid[t]).any())
    ok &= check("dobór ścieżek: tylko przeszłość, pora ±1 h, odstęp ≥ 12 h; pora — ten instrument, analogi — ta sama grupa",
                bad == 0, f"błędów {bad}")
    for name, data in (("czysty szum", synth.universe("pure")), ("zasiany sygnał", synth.universe("planted"))):
        cs = cat.calibrate([sr.pair_of(d, s) for s, d in data.items()], log=lambda *a: None)
        rr = rs.run(data, cs, log=lambda *a: None)
        mdl = rr["scenario"]["model"]
        B = rr["scenario"]["methods"][mdl["method"]]["B"]
        info = (f"model {mdl['method']}, λ {mdl['lambda']}, ×{mdl['f']}; ocena: pokrycie 80% {100*B['cov80_48']:.0f}%, "
                f"Brier k=48 {B['brier48']:.3f}, środek {100*B['centerS_A']:+.1f}%")
        if name == "czysty szum":
            ok &= check("czysty szum: płaski środek, trafny stożek",
                        mdl["lambda"] == 0 and B["brier48"] >= 0.245 and 0.72 <= B["cov80_48"] <= 0.88, info)
        else:
            ok &= check("zasiany sygnał: środek wykryty, kierunek lepszy niż moneta",
                        mdl["lambda"] >= 0.5 and B["brier48"] < 0.24 and B["centerS"] > 0.01, info)
    return ok


# ======================================================================= 6
def test_live(U, conds) -> bool:
    from . import live as lv
    cut = ts("2026-10-09T17:00:00Z")                              # piątek 17:00 UTC
    full = {s: synth.synthetic(s, days=440, end="2026-10-12T02:00:00Z", seed=7 + j) for j, s in enumerate(U)}
    hist = {s: d[d["time"] < cut].reset_index(drop=True) for s, d in full.items()}
    root = Path(tempfile.mkdtemp()) / "fx-repo"
    (root / "fx").mkdir(parents=True)
    (root / "fx" / "conditions.json").write_text(json.dumps(cat.document(conds, hist, "selftest")), encoding="utf-8")
    res = rs.run(hist, conds, log=lambda *a: None)
    rs.write_ratings(root / "fx" / "ratings.json", rs.documents(res, {"catalog": cat.CATALOG}, "H-001")[0])
    model = lv.Model(root)

    class Src:
        def __init__(s):
            s.reads, s.now, s.idle_reads = 0, 0, 0
        def _vis(s, sym):
            d = full[sym]
            return d[d["time"] + 3600 + 90 <= s.now]               # Fx.gs zapisuje 90 s po zamknięciu
        def status(s):
            s.reads += 1
            if not L.waiting(s.now):
                s.idle_reads += 1                                 # pytanie, choć żadna świeca nie powinna przybyć
            return {sym: int(s._vis(sym)["time"].iloc[-1]) for sym in full}
        def days(s, sym, dates):
            v, out = s._vis(sym), {}
            for d in dates:
                s.reads += 1
                t0 = ts(d + "T00:00:00Z")
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
    L = lv.Live({s: d.copy() for s, d in hist.items()}, model, src, out, clock=now, log=lambda *a: None)
    L.recompute(now())
    end = ts("2026-10-11T23:30:00Z")
    skip = (ts("2026-10-10T03:00:00Z"), ts("2026-10-11T19:00:00Z"))   # środek weekendu: tylko BTC — przeskok
    new, lags, t_comp = 0, [], 0.0
    while clock["t"] < end:
        if skip[0] <= clock["t"] < skip[1]:
            for s in L.last:                                      # BTC dalej biegnie — dociągamy bez symulacji minut
                L.dfs[s] = full[s][full[s]["time"] + 3600 + 90 <= skip[1]].reset_index(drop=True)
                L.last[s] = int(L.dfs[s]["time"].iloc[-1])
            clock["t"] = skip[1]
        before = dict(L.last)
        t1 = time.time()
        if L.step():
            new += 1
            t_comp = max(t_comp, time.time() - t1)
            for s in L.last:
                if L.last[s] != before[s]:
                    lags.append(clock["t"] - (L.last[s] + 3600))
        clock["t"] += 30
    ok = True
    exp = {s: int(full[s][full[s]["time"] + 3600 + 90 <= end]["time"].iloc[-1]) for s in full}
    ok &= check("każda nowa świeca wykryta (3 instrumenty), ≤ 2 min po zamknięciu",
                L.last == exp and max(lags) <= 120, f"przeliczeń {new}, opóźnienie ≤ {max(lags):.0f} s, przeliczenie ≤ {t_comp:.1f} s")
    ok &= check("odczyty Firestore: 1–2 × system/fx1h + dzień każdego instrumentu z nową świecą; 0, gdy nic nie czeka",
                src.reads <= new * (2 + 2 * len(full)) and src.idle_reads == 0,
                f"{src.reads} odczytów na {new} przeliczeń, zbędnych {src.idle_reads}")
    fri = [d for d in out.docs if d.get("instruments")]
    e = [x for x in fri[-1]["instruments"] if fi.group_of(x["id"]) == "fx"][0]
    t_fx_last = ts("2026-10-09T20:00:00Z")
    sat = [x for x in out.docs if x.get("generatedAt", "").startswith("2026-10-10T0")]
    e_sat = [x for x in sat[-1]["instruments"] if fi.group_of(x["id"]) == "fx"][0] if sat else None
    ok &= check("prognoza par walutowych: 48 świec w godzinach rynku, po piątku — od niedzieli 21:00 UTC",
                e_sat is not None and len(e_sat["times"]) == 48 and e_sat["times"][0] == ts("2026-10-11T21:00:00Z")
                and all(fi.market_open("fx", t)[0] for t in e_sat["times"]) and ts(e_sat["lastCandle"]) == t_fx_last,
                f"{e_sat['id'] if e_sat else '—'}: {e_sat['times'][0] if e_sat else ''}")
    direct = {s: full[s][full[s]["time"] <= L.last[s]].reset_index(drop=True) for s in full}
    same = all(L.dfs[s][["time", "o", "h", "l", "c"]].reset_index(drop=True).equals(direct[s][["time", "o", "h", "l", "c"]]) for s in full)
    a, b = lv.compute(L.dfs, model, clock["t"]), lv.compute(direct, model, clock["t"])
    eq = all(x["q10"] == y["q10"] and x["center"] == y["center"] and len(x["scenarios"]) == 3
             for x, y in zip(a["instruments"], b["instruments"]))
    ok &= check("dane na żywo = pełne pobranie, prognoza = przeliczenie od zera", same and eq,
                ", ".join(f"{x['id']} zakres {x['range']['size']:.5g}" for x in a["instruments"]))
    doc = lv.document({"fc": a, "generatedAt": lv.iso(clock["t"]), "reads": src.reads}, model, clock["t"])
    ok &= check("forecast.json: 3 instrumenty, model, sprawdzian, werdykt", len(doc["instruments"]) == 3 and doc["model"]["method"]
                and "cone" in doc["verdict"], f"{len(json.dumps(doc)) // 1024} KB")
    return ok


def main() -> None:
    print("IA 4 — selftest modułu prognozy FX 1h (dane syntetyczne)\n")
    t0 = time.time()
    ok = test_data()
    ok2, U, conds = test_catalog()
    ok &= ok2
    print("  FX-research:")
    ok &= test_research(U, conds)
    print("  FX-real-time:")
    ok &= test_live(U, conds)
    print(f"\n  czas: {(time.time() - t0) / 60:.1f} min")
    print("WYNIK:", "OK" if ok else "BŁĄD")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
