"""
IA 4 — prognoza rozkładu EURUSD: scenariusze z historii (instrukcja, sekcje 4c.0, 4c.6, 4c.7).
Wersja projektu: 1.26 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

Zamiast jednej uśrednionej linii: K = 80 prawdziwych 48-świecowych ścieżek ceny z historii,
z momentów podobnych do obecnego, przeskalowanych do dzisiejszej zmienności.
  • środek   = λ × średnia profili okoliczności prawdziwych ważona ratingiem (4c.6),
  • ścieżki* = środek + f × (ścieżka − mediana ścieżek) — kształt i rozrzut z historii,
               położenie ze środka, szerokość skalibrowana,
  • z ścieżek*: stożek (kwantyle 10/25/75/90%), P(wzrost), oczekiwany zakres 4 h
    i 3 przykładowe scenariusze (spadkowy / boczny / wzrostowy).

Metody doboru momentów (pula: ta sama pora dnia ±1 h UTC, okno przyszłości w całości znane):
  • „pora”    — najnowsze momenty z puli,
  • „analogi” — momenty najbardziej podobne pod względem okoliczności prawdziwych
                (Jaccard ważony ratingiem).
Kolejne wybrane momenty są od siebie oddalone o ≥ 12 świec (nie 80 kopii tej samej godziny).
Szerokość stożka f i siłę środka λ kalibruje sprawdzian (walk-forward), on też wybiera metodę.
"""

from __future__ import annotations

import numpy as np

from .research import H

K = 80                    # ścieżek w zestawie
SPACING = 12              # najmniejszy odstęp między wybranymi momentami (świec)
HOUR_WINDOW = 1           # pula: ta sama godzina UTC ±1
SCALE_CLIP = (1 / 3, 3.0)
QUANT = (0.10, 0.25, 0.75, 0.90)
METHODS = ("analogi", "pora")
SCEN = ((0.2, "spadkowy"), (0.5, "boczny"), (0.8, "wzrostowy"))


class Engine:
    """Wszystko, co potrzebne do doboru scenariuszy na całej serii."""

    def __init__(self, time, R, ok, M, ratings, U100, U12):
        self.time = np.asarray(time, dtype=np.int64)
        self.R = R
        self.T = R.shape[0]
        self.hour = (self.time // 3600) % 24
        vol = np.asarray(U100) * np.asarray(U12)
        self.vol = np.where(np.isfinite(vol) & (vol > 0), vol, np.nan)
        full = np.isfinite(R[:, H - 1])
        self.cand = ok & np.isfinite(self.vol) & full     # moment z kompletną, znaną przyszłością
        self.A = M.T.astype(np.float32)                    # T × N (okoliczności prawdziwe)
        self.w = np.asarray(ratings, dtype=np.float32)
        self.size = self.A @ self.w                        # suma wag okoliczności prawdziwych na świecy

    # ------------------------------------------------------------------ pula i dobór
    def pool(self, t: int, end: int) -> np.ndarray:
        """Kandydaci dla świecy t, gdy znane są świece < end: przyszłość kandydata (48 świec) < end."""
        lim = max(end - H, 0)
        c = np.flatnonzero(self.cand[:lim])
        dh = np.abs(self.hour[c] - self.hour[t])
        dh = np.minimum(dh, 24 - dh)
        return c[dh <= HOUR_WINDOW]

    def similarity(self, t: int, pool: np.ndarray) -> np.ndarray:
        inter = self.A[pool] @ (self.A[t] * self.w)
        union = self.size[t] + self.size[pool] - inter
        return np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0)

    @staticmethod
    def spaced(order: np.ndarray, k: int = K, spacing: int = SPACING) -> np.ndarray:
        out = []
        for c in order:
            if all(abs(c - x) >= spacing for x in out):
                out.append(int(c))
                if len(out) == k:
                    break
        return np.array(out, dtype=np.int64)

    def select(self, t: int, end: int, method: str, sim: np.ndarray | None = None) -> np.ndarray:
        pool = self.pool(t, end)
        if pool.size == 0:
            return pool
        if method == "pora":
            order = pool[::-1]                                   # najnowsze najpierw
        elif method == "analogi":
            s = self.similarity(t, pool) if sim is None else sim[pool]
            order = pool[np.lexsort((-pool, -s))]                # podobieństwo, przy remisie nowsze
        elif method == "całość":                                 # punkt odniesienia: bez pory dnia
            order = np.flatnonzero(self.cand[:max(end - H, 0)])[::-1]
        else:
            raise ValueError(method)
        return self.spaced(order)

    def paths(self, t: int, a: np.ndarray) -> np.ndarray:
        """Ścieżki zmian (pipsy) wybranych momentów w skali zmienności świecy t."""
        sc = np.sqrt(self.vol[t] / self.vol[a])
        sc = np.clip(np.nan_to_num(sc, nan=1.0), *SCALE_CLIP)
        return self.R[a] * sc[:, None]


# ======================================================================= rozkład
def adjusted(P: np.ndarray, center: np.ndarray, f: float) -> np.ndarray:
    """Ścieżki* = środek + f · (ścieżka − mediana ścieżek)."""
    return center[None, :] + f * (P - np.nanmedian(P, axis=0)[None, :])


def distribution(P: np.ndarray, center: np.ndarray, f: float) -> dict:
    """Z ścieżek P (K × 48, pipsy) i środka — stożek, P(wzrost), zakres. Wszystko w pipsach od ceny teraz."""
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


def check(engine: Engine, PM: np.ndarray, start_frac: float = 0.70, split_frac: float = 0.85, max_q: int = 1500,
          methods=("analogi", "pora", "całość")) -> dict:
    """Walk-forward (4c.7). Zapytania = świece-kandydaci z ostatnich 30% serii (co n-ta, najwyżej max_q);
    każde widzi tylko przeszłość (przyszłość wybranych ścieżek kończy się przed świecą zapytania).
    PM — średnia profili ważona ratingiem dla każdej świecy (T × 48), policzona bez danych z ostatnich 30%.
    Część A (70–85%) — kalibracja λ (siła środka) i f (szerokość: pokrycie 80% = 80%); część B (85–100%) — ocena.
    Model na żywo: metoda z niższym pinball (k = 12 + 48) w części B; λ i f na żywo — z A + B,
    ale λ = 0, gdy środek w części B nie był lepszy niż „bez zmiany” (centerS ≤ 0)."""
    T = engine.T
    s0 = int(start_frac * T)
    q_all = np.flatnonzero(engine.cand[s0:]) + s0
    if q_all.size == 0:
        return {"queries": 0}
    step = max(1, int(np.ceil(q_all.size / max_q)))
    Q = q_all[::step]
    split = int(split_frac * T)
    raw = {m: [] for m in methods}
    for i0 in range(0, Q.size, 256):                     # podobieństwa paczkami
        Qc = Q[i0:i0 + 256]
        Sim = None
        if "analogi" in methods:
            inter = (engine.A[Qc] * engine.w) @ engine.A.T
            union = engine.size[Qc][:, None] + engine.size[None, :] - inter
            Sim = np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0)
        for j, t in enumerate(Qc):
            pm = np.nan_to_num(PM[t], nan=0.0)
            for m in methods:
                a = engine.select(int(t), int(t) + 1, m, None if Sim is None else Sim[j])
                if a.size < 10:
                    continue
                raw[m].append((int(t), engine.paths(int(t), a), pm))
    F = np.round(np.arange(0.70, 2.001, 0.05), 2)
    L = tuple(np.round(np.arange(0.0, 3.001, 0.25), 2))

    def fit(items):
        if not items:
            return 1.0, 0.0
        lam = float(min(L, key=lambda l: sum(np.nansum(np.abs(engine.R[t] - l * pm)) for t, P, pm in items)))
        def cov(f):
            c = []
            for t, P, pm in items:
                X = adjusted(P[:, (11, 47)], lam * pm[[11, 47]], f)
                y = engine.R[t, [11, 47]]
                lo, hi = np.nanquantile(X, 0.10, axis=0), np.nanquantile(X, 0.90, axis=0)
                c.extend(((lo <= y) & (y <= hi))[np.isfinite(y)])
            return np.mean(c)
        f = float(min(F, key=lambda x: abs(cov(x) - 0.80)))
        return f, lam

    def score(items, f, lam):
        if not items:
            return None
        pin = {12: [], 48: []}
        cov80, cov50, brier = {12: [], 48: []}, [], {12: [], 48: []}
        rng_err, num, den = [], 0.0, 0.0
        for t, P, pm in items:
            y = engine.R[t]
            d = distribution(P, lam * pm, f)
            for k in (12, 48):
                if not np.isfinite(y[k - 1]):              # świeca uśredniona — pomijamy
                    continue
                qs = {a: d["q"][a][k - 1] for a in d["q"]}
                pin[k].append(_pinball(y[k - 1], qs, float(np.nanmedian(d["X"][:, k - 1]))))
                cov80[k].append(qs[10] <= y[k - 1] <= qs[90])
                brier[k].append((d["pUp"][k - 1] - float(y[k - 1] > 0)) ** 2)
            if np.isfinite(y[H - 1]):
                cov50.append(d["q"][25][H - 1] <= y[H - 1] <= d["q"][75][H - 1])
            path = np.concatenate([[0.0], y])
            real = float(np.nanmax(path) - np.nanmin(path))
            if real > 0:
                rng_err.append(abs(d["range"] - real) / real)
            num += np.nansum(np.abs(y - d["center"]))
            den += np.nansum(np.abs(y))
        r = lambda x: round(float(x), 4)
        return {"n": len(items), "pinball12": r(np.mean(pin[12])), "pinball48": r(np.mean(pin[48])),
                "cov80_12": r(np.mean(cov80[12])), "cov80_48": r(np.mean(cov80[48])), "cov50_48": r(np.mean(cov50)),
                "brier12": r(np.mean(brier[12])), "brier48": r(np.mean(brier[48])),
                "rangeErr": r(np.median(rng_err)) if rng_err else None,
                "centerS": r(1 - num / den) if den > 0 else None}

    out = {"queries": int(Q.size), "every": int(step), "splitAt": int(split), "methods": {}}
    for m in methods:
        A_ = [x for x in raw[m] if x[0] < split]
        B_ = [x for x in raw[m] if x[0] >= split]
        f, lam = fit(A_)
        fa, la = fit(A_ + B_)
        B = score(B_, f, lam)
        center_test = B["centerS"] if B else None          # test środka z λ z części A
        if not B or B["centerS"] is None or B["centerS"] <= 0:
            la = 0.0                                   # środek bez przewagi w ocenie (B) — na żywo płaski (4c.7)
            if B and lam != 0:
                B = score(B_, f, 0.0)                  # ocena stożka w konfiguracji, która idzie na żywo
        if B:
            B["centerS_A"] = center_test
        out["methods"][m] = {"fitA": {"f": f, "lambda": lam}, "B": B, "live": {"f": fa, "lambda": la}}
    cand = [m for m in ("analogi", "pora") if out["methods"].get(m, {}).get("B")]
    if cand:
        best = min(cand, key=lambda m: (out["methods"][m]["B"]["pinball12"] + out["methods"][m]["B"]["pinball48"],
                                        0 if m == "pora" else 1))
        out["model"] = {"method": best, **out["methods"][best]["live"], "K": K, "hourWindow": HOUR_WINDOW,
                        "spacing": SPACING}
    return out


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
