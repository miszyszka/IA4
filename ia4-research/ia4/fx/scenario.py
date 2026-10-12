"""
IA 4 — prognoza rozkładu FX 1h: scenariusze z historii (instrukcja, sekcje 4c.0, 4c.6, 4c.7).
Wersja projektu: 1.35 (2026-10-12) — musi zgadzać się z IA4_INSTRUKCJA.md

Zamiast jednej uśrednionej linii: K = 80 prawdziwych 48-świecowych ścieżek ceny z historii,
z chwil podobnych do obecnej, w jednostkach zmienności (ATR100) i przeskalowanych do
dzisiejszego reżimu zmienności (ATR12 / ATR100).
  • środek   = λ × średnia profili okoliczności prawdziwych ważona ratingiem (4c.6),
  • ścieżki* = środek + f × (ścieżka − mediana ścieżek) — kształt i rozrzut z historii,
               położenie ze środka, szerokość skalibrowana,
  • z ścieżek*: stożek (kwantyle 10/25/75/90%), P(wzrost), oczekiwany zakres 48 h
    i 3 przykładowe scenariusze (spadkowy / boczny / wzrostowy).

Metody doboru chwil (okno przyszłości chwili w całości znane przed świecą prognozy, ta sama
godzina UTC ±1 h):
  • „pora”    — ten sam instrument, najnowsze chwile,
  • „analogi” — wszystkie instrumenty tej samej grupy (10 par walutowych razem, BTC osobno),
                chwile najbardziej podobne pod względem okoliczności prawdziwych (Jaccard ważony ratingiem),
  • „całość”  — punkt odniesienia w sprawdzianie: ten sam instrument, dowolna godzina, najnowsze.
Wybrane chwile są od siebie oddalone o ≥ 12 h w kalendarzu (także między instrumentami —
EURUSD i GBPUSD w tej samej godzinie to prawie ta sama informacja).
Szerokość f i siłę środka λ kalibruje sprawdzian (walk-forward), on też wybiera metodę.
"""

from __future__ import annotations

import numpy as np

H = 48
K = 80                    # ścieżek w zestawie
SPACING_H = 12            # najmniejszy odstęp między wybranymi chwilami (godziny kalendarza)
HOUR_WINDOW = 1           # pula: ta sama godzina UTC ±1
SCALE_CLIP = (1 / 3, 3.0)
QUANT = (0.10, 0.25, 0.75, 0.90)
SCEN = ((0.2, "spadkowy"), (0.5, "boczny"), (0.8, "wzrostowy"))
CHUNK = 20000
CENTER_MIN = 0.01         # środek na żywo tylko, gdy w części B jest ≥ 1% lepszy niż „bez zmiany” (4c.7)


class Engine:
    """Dobór scenariuszy na puli instrumentów (research.Pool)."""

    def __init__(self, P, ratings):
        self.P = P
        self.R, self.time, self.inst, self.T = P.R, P.time, P.inst, P.T
        self.hour = (P.time // 3600) % 24
        gcode = {g: i for i, g in enumerate(sorted(set(P.groups)))}
        self.gid = np.array([gcode[P.groups[j]] for j in range(len(P.syms))], dtype=np.int16)[P.inst]
        with np.errstate(invalid="ignore", divide="ignore"):
            rho = P.U12 / P.U100
        self.rho = np.where(np.isfinite(rho) & (rho > 0), rho, np.nan)
        self.cand = P.ok & np.isfinite(P.R[:, H - 1]) & np.isfinite(self.rho)
        self.end = P.tk[:, H - 1]                                  # czas ostatniej świecy okna
        self.A = np.ascontiguousarray(P.M.T)                        # T × N (bool)
        self.w = np.asarray(ratings, dtype=np.float32)
        self.size = np.zeros(self.T, dtype=np.float32)              # suma wag okoliczności prawdziwych
        for i in range(0, self.T, CHUNK):
            self.size[i:i + CHUNK] = self.A[i:i + CHUNK].astype(np.float32) @ self.w

    # ------------------------------------------------------------------ pula i dobór
    def hour_ok(self, t: int) -> np.ndarray:
        dh = np.abs(self.hour - self.hour[t])
        return np.minimum(dh, 24 - dh) <= HOUR_WINDOW

    def pool(self, t: int, limit: int, method: str) -> np.ndarray:
        """Kandydaci dla świecy t, gdy znane są świece przed chwilą `limit` (okno chwili kończy się wcześniej)."""
        c = self.cand & (self.end < limit)
        if method == "pora":
            c &= (self.inst == self.inst[t]) & self.hour_ok(t)
        elif method == "analogi":
            c &= (self.gid == self.gid[t]) & self.hour_ok(t)
        elif method == "całość":
            c &= self.inst == self.inst[t]
        else:
            raise ValueError(method)
        return np.flatnonzero(c)

    def similarity(self, t: int, rows: np.ndarray) -> np.ndarray:
        q = self.A[t].astype(np.float32) * self.w
        out = np.empty(rows.size, dtype=np.float32)
        for i in range(0, rows.size, CHUNK):
            r = rows[i:i + CHUNK]
            inter = self.A[r].astype(np.float32) @ q
            union = self.size[t] + self.size[r] - inter
            out[i:i + CHUNK] = np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0)
        return out

    def spaced(self, order: np.ndarray) -> np.ndarray:
        import bisect
        out, times = [], []
        gap = SPACING_H * 3600
        tm = self.time
        for c in order.tolist():
            tc = int(tm[c])
            i = bisect.bisect_left(times, tc)
            if (i < len(times) and times[i] - tc < gap) or (i > 0 and tc - times[i - 1] < gap):
                continue
            times.insert(i, tc)
            out.append(c)
            if len(out) == K:
                break
        return np.array(out, dtype=np.int64)

    def select(self, t: int, limit: int, method: str, sim: tuple | None = None) -> np.ndarray:
        """sim = (rows, wartości) — podobieństwa policzone wcześniej dla posortowanych rows ⊇ pula."""
        pool = self.pool(t, limit, method)
        if pool.size == 0:
            return pool
        if method == "analogi":
            if sim is None:
                s = self.similarity(t, pool)
            else:
                rows, vals = sim
                s = vals[np.searchsorted(rows, pool)]
            order = pool[np.lexsort((-self.time[pool], -s))]      # podobieństwo, przy remisie nowsze
        else:
            order = pool[np.argsort(-self.time[pool], kind="stable")]   # najnowsze najpierw
        return self.spaced(order)

    def paths(self, t: int, a: np.ndarray) -> np.ndarray:
        """Ścieżki zmian (ATR100) wybranych chwil w reżimie zmienności świecy t."""
        sc = np.sqrt(self.rho[t] / self.rho[a])
        sc = np.clip(np.nan_to_num(sc, nan=1.0), *SCALE_CLIP)
        return self.R[a] * sc[:, None]


# ======================================================================= rozkład
def adjusted(P: np.ndarray, center: np.ndarray, f: float) -> np.ndarray:
    """Ścieżki* = środek + f · (ścieżka − mediana ścieżek)."""
    return center[None, :] + f * (P - np.nanmedian(P, axis=0)[None, :])


def distribution(P: np.ndarray, center: np.ndarray, f: float) -> dict:
    """Z ścieżek P (K × 48, ATR100) i środka — stożek, P(wzrost), zakres. Wszystko w ATR100 od ceny teraz."""
    X = adjusted(P, center, f)
    q = {int(100 * a): np.nanquantile(X, a, axis=0) for a in QUANT}
    cum = np.concatenate([np.zeros((X.shape[0], 1)), X], axis=1)
    hi, lo = np.nanmax(cum, axis=1), np.nanmin(cum, axis=1)
    return {"center": center, "q": q, "pUp": (X > 0).mean(axis=0), "X": X,
            "high": float(np.nanmedian(hi)), "low": float(np.nanmedian(lo)), "range": float(np.nanmedian(hi - lo))}


def scenarios(X: np.ndarray, a: np.ndarray) -> list[tuple[str, int, np.ndarray]]:
    """3 ścieżki* (prawdziwe ścieżki z historii, przesunięte o środek): najbliższe 20., 50. i 80.
    percentyla zmiany po 48 świecach."""
    end = X[:, H - 1]
    out = []
    for p, name in SCEN:
        target = np.nanquantile(end, p)
        i = int(np.nanargmin(np.abs(end - target)))
        out.append((name, int(a[i]), X[i]))
    return out


# ======================================================================= sprawdzian (4c.7)
def _pinball(y, qs: dict, center) -> float:
    vals = []
    for a, q in ((0.10, qs[10]), (0.25, qs[25]), (0.5, center), (0.75, qs[75]), (0.90, qs[90])):  # y skończone
        e = y - q
        vals.append(a * e if e >= 0 else (a - 1) * e)
    return float(np.mean(vals))


def check(engine: Engine, PM: np.ndarray, start_frac: float = 0.70, split_frac: float = 0.85, max_q: int = 2000,
          methods=("analogi", "pora", "całość")) -> dict:
    """Walk-forward (4c.7) po kalendarzu. Zapytania = świece-kandydaci wszystkich instrumentów z ostatnich 30%
    kalendarza (co n-ta, najwyżej max_q); każde widzi tylko przeszłość (okna wybranych chwil kończą się przed
    świecą zapytania). PM — średnia profili ważona ratingiem (T × 48), bez danych z ostatnich 30%.
    Część A (70–85%) — kalibracja λ (siła środka) i f (szerokość: pokrycie 80% = 80%); część B (85–100%) — ocena,
    także osobno dla każdego instrumentu. Model na żywo: metoda z niższym pinball (k = 12 + 48) w części B;
    λ i f na żywo — z A + B, ale λ = 0, gdy środek w części B nie był o co najmniej CENTER_MIN lepszy
    niż „bez zmiany” (zasada 15)."""
    P = engine.P
    t_start, t_split = P.time_at(start_frac), P.time_at(split_frac)
    q_all = np.flatnonzero(engine.cand & (engine.time >= t_start))
    if q_all.size == 0:
        return {"queries": 0}
    step = max(1, int(np.ceil(q_all.size / max_q)))
    Q = q_all[::step]
    raw = {m: [] for m in methods}
    for h in range(24):                                        # podobieństwa: jedna paczka na godzinę UTC
        Qh = Q[engine.hour[Q] == h]
        if not Qh.size:
            continue
        sims = {}
        if "analogi" in methods:
            dh = np.abs(engine.hour - h)
            rows = np.flatnonzero(engine.cand & (np.minimum(dh, 24 - dh) <= HOUR_WINDOW))
            # macierz podobieństw (zapytania × rows), kawałkami po CHUNK wierszy rows
            S = np.empty((Qh.size, rows.size), dtype=np.float32)
            Aq = engine.A[Qh].astype(np.float32) * engine.w[None, :]
            for i0 in range(0, rows.size, CHUNK):
                r = rows[i0:i0 + CHUNK]
                inter = Aq @ engine.A[r].astype(np.float32).T
                union = engine.size[Qh][:, None] + engine.size[r][None, :] - inter
                S[:, i0:i0 + r.size] = np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0)
            for j, t in enumerate(Qh.tolist()):
                sims[t] = (rows, S[j])
        for t in Qh.tolist():
            pm = np.nan_to_num(PM[t], nan=0.0)
            limit = int(engine.time[t])
            for m in methods:
                a = engine.select(t, limit, m, sims.get(t) if m == "analogi" else None)
                if a.size < 10:
                    continue
                raw[m].append((t, engine.paths(t, a), pm))
    F = np.round(np.arange(0.70, 2.001, 0.05), 2)
    L = tuple(np.round(np.arange(0.0, 3.001, 0.25), 2))

    def fit(items):
        if not items:
            return 1.0, 0.0
        lam = float(min(L, key=lambda l: sum(np.nansum(np.abs(engine.R[t] - l * pm)) for t, X, pm in items)))
        # kwantyle ścieżek* = środek + f · kwantyl(ścieżka − mediana) — liczone raz, potem tylko × f
        cols = [11, 47]
        Y = np.array([engine.R[t, cols] for t, X, pm in items])
        C = np.array([lam * pm[cols] for t, X, pm in items])
        Dv = np.array([np.nanquantile(X[:, cols] - np.nanmedian(X[:, cols], axis=0), (0.10, 0.90), axis=0)
                       for t, X, pm in items])                    # n × 2 (kwantyl) × 2 (k)
        ok = np.isfinite(Y)
        def cov(f):
            lo, hi = C + f * Dv[:, 0, :], C + f * Dv[:, 1, :]
            return float(((lo <= Y) & (Y <= hi))[ok].mean())
        f = float(min(F, key=lambda x: abs(cov(x) - 0.80)))
        return f, lam

    def score(items, f, lam, per_inst=True):
        if not items:
            return None
        pin = {12: [], 48: []}
        cov80, cov50, brier = {12: [], 48: []}, [], {12: [], 48: []}
        rng_err, num, den = [], 0.0, 0.0
        inst = {}
        for t, X, pm in items:
            y = engine.R[t]
            d = distribution(X, lam * pm, f)
            s = P.syms[int(engine.inst[t])]
            st = inst.setdefault(s, {"n": 0, "c80": [], "br": [], "re": []})
            st["n"] += 1
            for k in (12, 48):
                if not np.isfinite(y[k - 1]):              # świeca uśredniona — pomijamy
                    continue
                qs = {a: d["q"][a][k - 1] for a in d["q"]}
                pin[k].append(_pinball(y[k - 1], qs, float(np.nanmedian(d["X"][:, k - 1]))))
                inside = qs[10] <= y[k - 1] <= qs[90]
                b = (d["pUp"][k - 1] - float(y[k - 1] > 0)) ** 2
                cov80[k].append(inside)
                brier[k].append(b)
                if k == 48:
                    st["c80"].append(inside)
                    st["br"].append(b)
            if np.isfinite(y[H - 1]):
                cov50.append(d["q"][25][H - 1] <= y[H - 1] <= d["q"][75][H - 1])
            path = np.concatenate([[0.0], y])
            real = float(np.nanmax(path) - np.nanmin(path))
            if real > 0:
                rng_err.append(abs(d["range"] - real) / real)
                st["re"].append(abs(d["range"] - real) / real)
            num += np.nansum(np.abs(y - d["center"]))
            den += np.nansum(np.abs(y))
        r = lambda x: round(float(x), 4)
        out = {"n": len(items), "pinball12": r(np.mean(pin[12])), "pinball48": r(np.mean(pin[48])),
               "cov80_12": r(np.mean(cov80[12])), "cov80_48": r(np.mean(cov80[48])), "cov50_48": r(np.mean(cov50)),
               "brier12": r(np.mean(brier[12])), "brier48": r(np.mean(brier[48])),
               "rangeErr": r(np.median(rng_err)) if rng_err else None,
               "centerS": r(1 - num / den) if den > 0 else None}
        if per_inst:
            out["inst"] = {s: {"n": v["n"], "cov80_48": r(np.mean(v["c80"])) if v["c80"] else None,
                               "brier48": r(np.mean(v["br"])) if v["br"] else None,
                               "rangeErr": r(np.median(v["re"])) if v["re"] else None}
                           for s, v in sorted(inst.items(), key=lambda kv: P.syms.index(kv[0]))}
        return out

    out = {"queries": int(Q.size), "every": int(step), "splitAt": int(t_split), "methods": {}}
    def variant(A_, B_):
        f, lam = fit(A_)
        fa, la = fit(A_ + B_)
        B = score(B_, f, lam)
        return f, lam, fa, la, B, (B["centerS"] if B else None)

    for m in methods:
        A_ = [x for x in raw[m] if engine.time[x[0]] < t_split]
        B_ = [x for x in raw[m] if engine.time[x[0]] >= t_split]
        # dwa kandydaci na środek (od 1.31): średnia profili okoliczności ("profile") i mediana ścieżek
        # z podobnych chwil ("analog") — każdy z λ z części A, oceniony na części B
        med = lambda X: np.nan_to_num(np.nanmedian(X, axis=0), nan=0.0)
        V = {"profile": variant(A_, B_),
             "analog": variant([(t, X, med(X)) for t, X, pm in A_], [(t, X, med(X)) for t, X, pm in B_])}
        ok = {k: v for k, v in V.items() if v[4] and v[5] is not None and v[5] >= CENTER_MIN}
        src = max(ok, key=lambda k: ok[k][5]) if ok else "profile"
        f, lam, fa, la, B, center_test = V[src]
        if not ok:
            la = 0.0                                   # środek bez udowodnionej przewagi (B) — na żywo płaski (4c.7)
            if B and lam != 0:
                B = score(B_, f, 0.0)                  # ocena stożka w konfiguracji, która idzie na żywo
        if B:
            B["centerS_A"] = center_test
        out["methods"][m] = {"fitA": {"f": f, "lambda": lam}, "B": B, "live": {"f": fa, "lambda": la, "center": src},
                             "centers": {k: {"lambda": v[1], "centerS": v[5]} for k, v in V.items()}}
    cand = [m for m in ("analogi", "pora") if out["methods"].get(m, {}).get("B")]
    if cand:
        best = min(cand, key=lambda m: (out["methods"][m]["B"]["pinball12"] + out["methods"][m]["B"]["pinball48"],
                                        0 if m == "pora" else 1))
        out["model"] = {"method": best, **out["methods"][best]["live"], "K": K, "hourWindow": HOUR_WINDOW,
                        "spacingHours": SPACING_H}
    return out


def center_of(mdl: dict, paths: np.ndarray, profile_mean: np.ndarray) -> np.ndarray:
    """Środek na żywo: λ × (średnia profili albo mediana ścieżek analogów — wybór sprawdzianu, 4c.6 p. 4)."""
    base = np.nanmedian(paths, axis=0) if mdl.get("center") == "analog" else profile_mean
    return mdl["lambda"] * np.nan_to_num(base, nan=0.0)


def verdict(B: dict | None) -> dict:
    """Ocena słowna wyniku sprawdzianu (część B) — dla dashboardu i konsoli."""
    if not B:
        return {"direction": "brak danych", "cone": "brak danych"}
    br = min(B["brier12"], B["brier48"])
    direction = ("przewaga nad rzutem monetą" if br < 0.245 else
                 "brak przewagi (jak rzut monetą)")
    c = B["cov80_48"]
    cone = ("stożek trafny" if 0.75 <= c <= 0.85 else
            "stożek za wąski" if c < 0.75 else "stożek za szeroki")
    return {"direction": direction, "cone": cone}
