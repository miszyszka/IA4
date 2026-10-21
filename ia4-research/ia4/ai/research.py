"""
IA 4 — Badacz: hipotezy z klocków, liczone przez Python (instrukcja, sekcja 8 — „Badacz”).
Wersja projektu: 1.59 (2026-10-21) — musi zgadzać się z IA4_INSTRUKCJA.md

Cykl (w wolnym czasie dyspozytora):
  1. brief (kod): menu cech z typowymi wartościami (kwantyle), ostatnie hipotezy z wynikami, uwagi Krytyka,
  2. model proponuje 1–3 hipotezy w JSON — tylko z menu (warunki „cecha op wartość”, wyjście w ATR14),
  3. kod liczy każdą na historii: wejście po open następnej świecy, SL/TP od ceny wejścia w ATR14, limit świec,
     SL przed TP, luka na otwarciu — pesymistycznie, zawsze z kosztami; 4 części kalendarza; wejście na ślepo
     (każda świeca, to samo wyjście) jako punkt odniesienia,
  4. sito kodu → „do oceny” (ocenia Krytyk) albo „odrzucona przez kod”.
Hipoteza „próba” daje na żywo kandydatów Inwestorowi (mały mnożnik ryzyka) — prawdziwy sprawdzian.

Sejf AI (zasada 17): doubleProof nie jest wczytywany (Badacz dostaje tylko 53 spółki handlowane), świece FX
sprzed `fx_research_from` są odcinane, zanim cokolwiek się policzy. Kod pisany przez model nie jest uruchamiany —
model wybiera tylko z menu (zasada 16).
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from numba import njit

from ..fx import instruments as fi
from ..lab import indicators as ind

AGENT = "researcher"
WARMUP = 210                      # świec rozgrzewki (SMA200 + zapas)
OPS = (">", "<")

FEATURES = {
    "ret1": "zmiana ceny z 1 świecy, w ATR14",
    "ret3": "zmiana ceny z 3 świec, w ATR14",
    "ret6": "zmiana ceny z 6 świec, w ATR14",
    "ret12": "zmiana ceny z 12 świec, w ATR14",
    "ret24": "zmiana ceny z 24 świec, w ATR14",
    "body": "korpus ostatniej świecy (close − open), w ATR14",
    "range": "zakres ostatniej świecy (high − low), w ATR14",
    "rsi14": "RSI 14 (0–100)",
    "rsi2": "RSI 2 (0–100) — bardzo krótkie wykupienie/wyprzedanie",
    "dist_sma20": "odległość ceny od SMA20, w ATR14",
    "dist_sma50": "odległość ceny od SMA50, w ATR14",
    "dist_sma200": "odległość ceny od SMA200, w ATR14",
    "slope_sma20": "nachylenie SMA20 z 5 świec, w ATR14",
    "slope_sma50": "nachylenie SMA50 z 5 świec, w ATR14",
    "stoch14": "położenie close w zakresie 14 świec (0 = dołek, 1 = szczyt)",
    "stoch50": "położenie close w zakresie 50 świec (0 = dołek, 1 = szczyt)",
    "vol_ratio": "ATR14 / ATR100 — zmienność teraz wobec typowej (>1 = rynek nerwowy)",
    "streak": "seria świec tego samego koloru: +n zielonych, −n czerwonych z rzędu",
    "hour": "godzina UTC początku świecy (0–23)",
    "dow": "dzień tygodnia UTC (1 = poniedziałek … 7 = niedziela)",
    "slot": "numer świecy w sesji NYSE 1–7 (tylko akcje)",
}


def _shift(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan)
    out[n:] = x[:-n]
    return out


def features(o, h, l, c, to, kind: str, k=None) -> tuple[dict, np.ndarray]:
    """Wszystkie cechy jednej serii — tylko ze świec ≤ t. Zwraca (cechy, ATR14)."""
    a = ind.atr(h, l, c, 14)
    a100 = ind.atr(h, l, c, 100)
    au = np.where(a > 0, a, np.nan)
    F = {}
    for n in (1, 3, 6, 12, 24):
        F[f"ret{n}"] = (c - _shift(c, n)) / au
    F["body"] = (c - o) / au
    F["range"] = (h - l) / au
    F["rsi14"] = ind.rsi(c, 14)
    F["rsi2"] = ind.rsi(c, 2)
    for n in (20, 50, 200):
        F[f"dist_sma{n}"] = (c - ind.sma(c, n)) / au
    for n in (20, 50):
        s = ind.sma(c, n)
        F[f"slope_sma{n}"] = (s - _shift(s, 5)) / au
    for n in (14, 50):
        hh = pd.Series(h).rolling(n).max().to_numpy()
        ll = pd.Series(l).rolling(n).min().to_numpy()
        rg = hh - ll
        F[f"stoch{n}"] = np.where(rg > 0, (c - ll) / np.where(rg > 0, rg, 1), np.nan)
    F["vol_ratio"] = a / np.where(a100 > 0, a100, np.nan)
    F["streak"] = _streak(np.sign(c - o))
    F["hour"] = np.floor((to % 86400) / 3600)
    F["dow"] = (np.floor(to / 86400) + 3) % 7 + 1
    F["slot"] = (np.asarray(k) % 10).astype(float) if kind == "stock" and k is not None else np.full(c.size, np.nan)
    return F, a


@njit(cache=True)
def _streak(sg):
    out = np.zeros(sg.size)
    run = 0.0
    for i in range(sg.size):
        if sg[i] > 0:
            run = run + 1 if run > 0 else 1.0
        elif sg[i] < 0:
            run = run - 1 if run < 0 else -1.0
        else:
            run = 0.0
        out[i] = run
    return out


@njit(cache=True)
def _sim(o, h, l, c, atr, mask, side, sl_atr, tp_atr, max_bars, cost_pct, start):
    """Transakcje jednej serii: (świeca wejścia, świeca wyjścia, wynik netto %, powód 0 TP / 1 SL / 2 LIMIT)."""
    n = c.size
    E = np.empty(n, np.int64)
    X = np.empty(n, np.int64)
    R = np.empty(n)
    W = np.empty(n, np.int64)
    m = 0
    busy = -1
    for t in range(start, n - 1):
        if not mask[t] or t <= busy or not (atr[t] > 0):
            continue
        e = t + 1
        P = o[e]
        sl = P - side * sl_atr * atr[t]
        tp = P + side * tp_atr * atr[t]
        if side > 0 and sl <= 0:
            continue
        x, why, j_out = -1.0, -1, -1
        last = min(n - 1, e + max_bars - 1)
        for j in range(e, last + 1):
            if j > e:                                           # luka na otwarciu
                if side * (o[j] - sl) <= 0:
                    x, why, j_out = o[j], 1, j
                    break
                if side * (o[j] - tp) >= 0:
                    x, why, j_out = tp, 0, j
                    break
            lo_hit = l[j] <= sl if side > 0 else h[j] >= sl
            tp_hit = h[j] >= tp if side > 0 else l[j] <= tp
            if lo_hit:
                x, why, j_out = sl, 1, j
                break
            if tp_hit:
                x, why, j_out = tp, 0, j
                break
            if j == e + max_bars - 1:
                x, why, j_out = c[j], 2, j
                break
        if why < 0:                                             # koniec danych — transakcja anulowana
            break
        E[m], X[m], W[m] = e, j_out, why
        R[m] = side * (x / P - 1.0) * 100.0 - cost_pct * (1.0 + x / P) / 2.0     # ½ kosztu przy wejściu, ½ przy wyjściu
        m += 1
        busy = j_out
    return E[:m], X[:m], R[:m], W[:m]


def cost_pct(cfg: dict, inst: str, kind: str, px: float) -> float:
    """Koszt całej transakcji (wejście + wyjście) w % wartości — jak 11c.6 w silniku portfela."""
    if kind == "stock":
        return 2 * cfg["cost_stock_pct"]
    if kind == "crypto":
        return 2 * cfg["cost_crypto_pct"]
    pip = fi.INFO.get(inst, {"pip": 0.0001})["pip"]
    return float(cfg["fx_spread_pips"].get(inst, 2.0)) * pip / px * 100.0


def ts(s: str) -> float:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()


# ===========================================================================
#  Pracownia: cechy wszystkich instrumentów (bez sejfu)
# ===========================================================================
class Lab:
    def __init__(self, prices, stocks: list[str], cfg: dict, built_at: float | None = None):
        self.cfg = cfg
        cut = ts(cfg["fx_research_from"])
        self.M: dict[str, dict] = {"fx": {}, "stocks": {}}
        for inst, s in prices.S.items():
            mk = "stocks" if s.kind == "stock" else "fx"
            if mk == "stocks" and inst not in stocks:
                continue                                          # SPY/QQQ — tło, doubleProof — nigdy (sejf)
            i0 = 0 if mk == "stocks" else int(np.searchsorted(s.to, cut))    # sejf FX odcięty przed liczeniem
            if s.n - i0 < WARMUP + 50:
                continue
            sl = slice(i0, s.n)
            o, h, l, c, to, k = (np.ascontiguousarray(x[sl], dtype=float) for x in (s.o, s.h, s.l, s.c, s.to, s.k))
            F, a = features(o, h, l, c, to, s.kind, k)
            self.M[mk][inst] = {"kind": s.kind, "o": o, "h": h, "l": l, "c": c, "to": to, "atr": a, "F": F,
                                "cost": cost_pct(cfg, inst, s.kind, float(np.nanmedian(c[-500:])))}
        self.Q: dict[str, dict] = {}
        self.span: dict[str, tuple] = {}
        for mk, D in self.M.items():
            if not D:
                continue
            q = {}
            for f in FEATURES:
                v = np.concatenate([d["F"][f][WARMUP:] for d in D.values()])
                v = v[np.isfinite(v)]
                if v.size:
                    q[f] = [float(x) for x in np.percentile(v, [10, 25, 50, 75, 90])]
            self.Q[mk] = q
            self.span[mk] = (min(float(d["to"][WARMUP]) for d in D.values()), max(float(d["to"][-1]) for d in D.values()))
        self.built_at = built_at or time.time()
        self._blind: dict = {}

    def instruments(self, market: str) -> list[str]:
        return sorted(self.M.get(market, {}))

    # ------------------------------------------------------------ ocena hipotezy
    def mask(self, d: dict, conds: list[dict]) -> np.ndarray:
        m = np.ones(d["c"].size, bool)
        for x in conds:
            v = d["F"][x["feature"]]
            with np.errstate(invalid="ignore"):
                m &= (v > x["value"]) if x["op"] == ">" else (v < x["value"])
        return m

    def run(self, h: dict, conds=None) -> list[tuple]:
        """Lista transakcji (instrument, czas wejścia, wynik netto %, powód, świec)."""
        side = 1 if h["direction"] == "long" else -1
        out = []
        for inst in self._insts(h):
            d = self.M[h["market"]][inst]
            mk = self.mask(d, h["conditions"] if conds is None else conds)
            E, X, R, W = _sim(d["o"], d["h"], d["l"], d["c"], d["atr"], mk, side, float(h["sl_atr"]), float(h["tp_atr"]),
                              int(h["max_bars"]), d["cost"], WARMUP)
            out += [(inst, float(d["to"][e]), float(r), int(w), int(x - e + 1)) for e, x, r, w in zip(E, X, R, W)]
        return out

    def _insts(self, h: dict) -> list[str]:
        have = self.M.get(h["market"], {})
        if h.get("instruments") in (None, "all", []):
            return sorted(have)
        return [i for i in h["instruments"] if i in have]

    def blind(self, h: dict) -> dict:
        key = (h["market"], h["direction"], float(h["sl_atr"]), float(h["tp_atr"]), int(h["max_bars"]), tuple(self._insts(h)))
        if key not in self._blind:
            self._blind[key] = summary(self.run(h, conds=[]), self.span.get(h["market"]))
        return self._blind[key]

    def evaluate(self, h: dict) -> dict:
        res = summary(self.run(h), self.span.get(h["market"]))
        b = self.blind(h)
        res["blind"] = {"n": b["n"], "avg": b["avg"]}
        res["edge"] = None if res["avg"] is None or b["avg"] is None else res["avg"] - b["avg"]
        return res


def summary(trades: list[tuple], span) -> dict:
    n = len(trades)
    if not n:
        return {"n": 0, "avg": None, "ci95": None, "t": None, "pf": None, "win": None, "hold": None, "parts": [],
                "exits": {}, "insts": 0}
    r = np.array([x[2] for x in trades])
    sd = float(r.std(ddof=1)) if n > 1 else 0.0
    pos, neg = float(r[r > 0].sum()), float(-r[r < 0].sum())
    parts = []
    if span:
        t0, t1 = span
        edges = np.linspace(t0, t1 + 1, 5)
        tt = np.array([x[1] for x in trades])
        for i in range(4):
            sel = r[(tt >= edges[i]) & (tt < edges[i + 1])]
            parts.append({"n": int(sel.size), "avg": float(sel.mean()) if sel.size else None})
    w = np.array([x[3] for x in trades])
    return {"n": n, "avg": float(r.mean()), "ci95": 2 * sd / math.sqrt(n) if n > 1 else None,
            "t": float(r.mean() / sd * math.sqrt(n)) if sd > 0 else None, "pf": round(pos / neg, 3) if neg > 0 else 99.0,
            "win": float((r > 0).mean()), "hold": float(np.median([x[4] for x in trades])), "parts": parts,
            "exits": {"TP": int((w == 0).sum()), "SL": int((w == 1).sum()), "LIMIT": int((w == 2).sum())},
            "insts": len({x[0] for x in trades})}


def sieve(res: dict, cfg: dict) -> list[str]:
    """Powody odrzucenia przez kod (pusta lista = „do oceny” przez Krytyka)."""
    s, why = cfg["hyp_sieve"], []
    if res["n"] < s["n_min"]:
        why.append(f"transakcji {res['n']} < {s['n_min']}")
    if res["avg"] is None or res["avg"] <= 0:
        why.append("średni wynik netto ≤ 0")
    if res.get("edge") is not None and res["edge"] <= 0:
        why.append("nie lepsza niż wejście na ślepo")
    if (res.get("pf") or 0) < s["pf_min"]:
        why.append(f"PF {res.get('pf') or 0:.2f} < {s['pf_min']}")
    if (res.get("t") or 0) < s["t_min"]:
        why.append(f"t {res.get('t') or 0:.2f} < {s['t_min']}")
    ok_parts = sum(1 for p in res.get("parts") or [] if p["n"] >= 5 and (p["avg"] or 0) > 0)
    if ok_parts < s["parts_ok"]:
        why.append(f"dodatnich części {ok_parts}/4 < {s['parts_ok']}")
    return why


def describe(h: dict) -> str:
    ins = "wszystkie" if h.get("instruments") in (None, "all", []) else ", ".join(h["instruments"][:6])
    cond = " i ".join(f"{x['feature']} {x['op']} {x['value']:g}" for x in h["conditions"])
    mk = "akcje" if h["market"] == "stocks" else "FX"
    return (f"{h['direction'].upper()} {mk} ({ins}) gdy {cond} · SL {h['sl_atr']:g} ATR / TP {h['tp_atr']:g} ATR / "
            f"limit {int(h['max_bars'])} świec")


def canon(h: dict) -> str:
    k = {x: h[x] for x in ("market", "direction", "conditions", "sl_atr", "tp_atr", "max_bars")}
    k["instruments"] = "all" if h.get("instruments") in (None, "all", []) else sorted(h["instruments"])
    return hashlib.sha1(json.dumps(k, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]


# ===========================================================================
#  Sygnały na żywo (hipotezy „próba” i „zatwierdzona”)
# ===========================================================================
def live_candidates(hyps: list[dict], prices, market: str, key: int, cfg: dict, holding) -> tuple[list[dict], list[str]]:
    """Kandydaci z hipotez na świecy `key` rynku `market` (tylko instrumenty, których ostatnia świeca to `key`)."""
    out, skipped = [], []
    hs = [h for h in hyps if h["status"] in ("próba", "zatwierdzona") and h["market"] == market]
    if not hs:
        return out, skipped
    cache: dict[str, tuple] = {}
    for h in sorted(hs, key=lambda h: h["id"]):
        side = 1 if h["direction"] == "long" else -1
        for inst, s in prices.S.items():
            if ("stocks" if s.kind == "stock" else "fx") != market:
                continue
            if h.get("instruments") not in (None, "all", []) and inst not in h["instruments"]:
                continue
            last = prices.last(inst)
            if last is None or last[0] != key:
                continue
            if inst not in cache:
                n = prices._n(s)
                a = max(0, n - 700)
                F, atr = features(*(np.ascontiguousarray(x[a:n], dtype=float) for x in (s.o, s.h, s.l, s.c, s.to)), s.kind, s.k[a:n])
                cache[inst] = ({f: v[-1] for f, v in F.items()}, float(atr[-1]))
            F, atr = cache[inst]
            if not (atr > 0) or not all(np.isfinite(F[x["feature"]]) and ((F[x["feature"]] > x["value"]) if x["op"] == ">" else
                                                                           (F[x["feature"]] < x["value"])) for x in h["conditions"]):
                continue
            if holding(inst):
                skipped.append(f"{inst} ({h['id']}) — pozycja już otwarta")
                continue
            px = float(last[1])
            kind = "proba" if h["status"] == "próba" else "hip_zatwierdzona"
            out.append({"inst": inst, "side": side, "basis": h["id"], "basis_kind": kind, "mult": cfg["mult"][kind],
                        "sl": 100 * h["sl_atr"] * atr / px, "tp": 100 * h["tp_atr"] * atr / px, "max_bars": int(h["max_bars"]),
                        "has_fc": False, "px": px, "atrp": 100 * atr / px, "s": None, "h": h, "k": int(last[0]), "also": []})
    return out, skipped


# ===========================================================================
#  Agent: brief → model → kod
# ===========================================================================
SYSTEM = """Jesteś Badacz w systemie IA 4. Wysuwasz hipotezy handlowe, a Python liczy je na historii (z kosztami, pesymistycznie). Uczysz się na wynikach poprzednich hipotez.

Zasady:
1. Hipoteza = rynek (fx albo stocks) + kierunek + 1–3 warunki „cecha op wartość” wyłącznie z MENU CECH + wyjście: sl_atr i tp_atr (wielokrotności ATR14 od ceny wejścia, TP/SL od 1:3 do 3:1), max_bars (2–120). Wejście zawsze po open następnej świecy.
2. Wartości progów wybieraj z typowych wartości cechy (kwantyle w MENU) — warunek prawdziwy zbyt rzadko da za mało transakcji (sito wymaga co najmniej tylu, ile podano).
3. Każda hipoteza ma pomysł: 1–2 zdania po polsku, jaki mechanizm rynku sprawdza (np. odwrócenie po wybiciu, kontynuacja trendu, pora dnia).
4. Ucz się: nie powtarzaj odrzuconych hipotez; rozwijaj obiecujące (zmień jeden element); bierz pod uwagę uwagi Krytyka. Różnicuj rynki, kierunki i rodzaje pomysłów.
5. Nie wymyślaj liczb wyników — policzy je kod.
Odpowiadasz wyłącznie JSON-em zgodnym ze schematem."""

SCHEMA = {
    "type": "object",
    "properties": {
        "hypotheses": {"type": "array", "items": {"type": "object", "properties": {
            "market": {"type": "string", "enum": ["fx", "stocks"]},
            "direction": {"type": "string", "enum": ["long", "short"]},
            "instruments": {"type": "array", "items": {"type": "string"}},
            "conditions": {"type": "array", "items": {"type": "object", "properties": {
                "feature": {"type": "string"}, "op": {"type": "string", "enum": list(OPS)}, "value": {"type": "number"}},
                "required": ["feature", "op", "value"]}},
            "sl_atr": {"type": "number"}, "tp_atr": {"type": "number"}, "max_bars": {"type": "integer"},
            "idea": {"type": "string"}},
            "required": ["market", "direction", "instruments", "conditions", "sl_atr", "tp_atr", "max_bars", "idea"]}},
        "note": {"type": "string"},
    },
    "required": ["hypotheses", "note"],
}


def check_hyp(h: dict, lab: Lab | None) -> list[str]:
    err = []
    if not isinstance(h, dict):
        return ["hipoteza nie jest obiektem"]
    mk = h.get("market")
    if mk not in ("fx", "stocks"):
        return [f"market {mk!r} — tylko fx albo stocks"]
    conds = h.get("conditions") or []
    if not 1 <= len(conds) <= 3:
        err.append("warunków musi być 1–3")
    for x in conds:
        f = x.get("feature") if isinstance(x, dict) else None
        if f not in FEATURES or (f == "slot" and mk != "stocks"):
            err.append(f"nieznana cecha {f!r} dla rynku {mk}")
        if isinstance(x, dict) and x.get("op") not in OPS:
            err.append(f"op {x.get('op')!r} — tylko > albo <")
        if isinstance(x, dict) and not isinstance(x.get("value"), (int, float)):
            err.append(f"wartość warunku {f} nie jest liczbą")
    try:
        sl, tp, mb = float(h.get("sl_atr")), float(h.get("tp_atr")), int(h.get("max_bars"))
        if not (0.3 <= sl <= 6):
            err.append(f"sl_atr {sl:g} poza 0,3–6")
        if not (0.3 <= tp <= 10):
            err.append(f"tp_atr {tp:g} poza 0,3–10")
        if sl > 0 and not (1 / 3 - 1e-9 <= tp / sl <= 3 + 1e-9):
            err.append(f"TP/SL {tp / sl:.2f} poza 1:3…3:1")
        if not (2 <= mb <= 120):
            err.append(f"max_bars {mb} poza 2–120")
    except (TypeError, ValueError):
        err.append("sl_atr, tp_atr i max_bars muszą być liczbami")
    ins = h.get("instruments")
    if ins not in (None, "all", []) and lab is not None:
        bad = [i for i in ins if i not in lab.M.get(mk, {})]
        if bad:
            err.append(f"instrumenty spoza rynku {mk}: {', '.join(map(str, bad[:5]))} (pusta lista = wszystkie)")
    return err


class Researcher:
    def __init__(self, cfg: dict, hub, llm, data, clock=time.time, log=print):
        self.cfg, self.hub, self.llm, self.data, self.clock, self.log = cfg, hub, llm, data, clock, log
        self.lab: Lab | None = None
        self.state = {"state": "on", "doing": "czeka na wolny czas", "since": clock()}
        self.fail_until = 0.0
        self.cycles = 0

    def _set(self, doing: str) -> None:
        self.state = {"state": "on", "doing": doing, "since": self.clock()}

    def ready(self) -> bool:
        return bool(self.cfg.get("research_on", True)) and self.clock() >= self.fail_until and \
            self.hub.hyp_count("do oceny") < int(self.cfg["hyp_queue_max"])

    def ensure_lab(self) -> Lab:
        age = self.clock() - (self.lab.built_at if self.lab else 0)
        if self.lab is None or age > 3600 * float(self.cfg["research_refresh_hours"]):
            self._set("przygotowuje dane (cechy wszystkich instrumentów)")
            prices, _, _ = self.data.get(False)
            self.lab = Lab(prices, self.data.traded, self.cfg, built_at=self.clock())
        return self.lab

    def brief(self, lab: Lab) -> str:
        L = ["MENU CECH (typowe wartości: p10 / p25 / mediana / p75 / p90):"]
        for mk in ("fx", "stocks"):
            if mk not in lab.Q:
                continue
            a, b = lab.span[mk]
            L.append(f"— rynek {mk}: {len(lab.M[mk])} instrumentów ({', '.join(lab.instruments(mk)[:11])}{'…' if len(lab.M[mk]) > 11 else ''}), "
                     f"dane {datetime.fromtimestamp(a, timezone.utc):%Y-%m-%d} – {datetime.fromtimestamp(b, timezone.utc):%Y-%m-%d}")
            for f, d in FEATURES.items():
                q = lab.Q[mk].get(f)
                if q:
                    L.append(f"  {f}: {d} · " + " / ".join(f"{x:.3g}" for x in q))
        s = self.cfg["hyp_sieve"]
        L.append(f"SITO KODU: ≥ {s['n_min']} transakcji, średni wynik netto > 0 i lepszy niż wejście na ślepo, PF ≥ {s['pf_min']}, "
                 f"t ≥ {s['t_min']}, dodatni wynik w ≥ {s['parts_ok']} z 4 części kalendarza.")
        c = self.hub.hyp_counts()
        L.append(f"LICZNIKI: sprawdzonych {sum(c.values())} · " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())))
        rv = self.hub.reviews(1)
        if rv and rv[0].get("researcher_notes"):
            L.append("UWAGI KRYTYKA DLA CIEBIE:")
            L += [f"- {x}" for x in rv[0]["researcher_notes"]]
        hs = self.hub.hypotheses(14)
        L.append("OSTATNIE HIPOTEZY (od najnowszej):" if hs else "OSTATNIE HIPOTEZY: brak — zacznij od prostych pomysłów na obu rynkach.")
        for h in hs:
            L.append(f"{h['id']} [{h['status']}] {describe(h)} → {res_line(h.get('result'))}" +
                     (f" · Krytyk: {h['verdict_note'][:160]}" if h.get("verdict_note") else "") +
                     (f" · sito: {'; '.join(h['why'][:2])}" if h.get("why") else ""))
        best = self.hub.hyp_best(5)
        if best:
            L.append("NAJLEPSZE DOTĄD (t-stat):")
            L += [f"{h['id']} [{h['status']}] {describe(h)} → {res_line(h.get('result'))}" for h in best]
        L.append("Zaproponuj 1–3 nowe hipotezy.")
        return "\n".join(L)

    def cycle(self) -> dict:
        lab = self.ensure_lab()
        self._set("myśli: nowe hipotezy")
        text = self.brief(lab)
        obj, meta = self.llm.ask(AGENT, SYSTEM, text, SCHEMA, lambda o: self._check(o, lab), float(self.cfg["temperature_researcher"]))
        self.cycles += 1
        if not isinstance(obj, dict):
            self.fail_until = self.clock() + 600
            self._set("czeka (model niedostępny — ponowi za 10 min)")
            return {"ok": False, "summary": "brak odpowiedzi modelu: " + "; ".join((meta.get("errors") or ["?"])[:1]), "meta": meta}
        made = []
        for h in (obj.get("hypotheses") or [])[:3]:
            if check_hyp(h, lab):
                continue
            h = {k: h[k] for k in ("market", "direction", "instruments", "conditions", "sl_atr", "tp_atr", "max_bars", "idea")}
            ins = h["instruments"]
            h["instruments"] = "all" if ins in (None, "all", []) or not isinstance(ins, list) else [str(i).upper().replace("/", "") for i in ins]
            h["conditions"] = [{"feature": x["feature"], "op": x["op"], "value": float(x["value"])} for x in h["conditions"]]
            sig = canon(h)
            old = self.hub.hyp_by_sig(sig)
            if old:
                made.append(f"{old['id']} (powtórka — pominięta)")
                continue
            self._set(f"liczy hipotezę: {describe(h)[:90]}")
            t0 = time.time()
            res = lab.evaluate(h)
            why = sieve(res, self.cfg)
            h.update({"sig": sig, "result": res, "why": why, "status": "odrzucona przez kod" if why else "do oceny",
                      "at": self.clock(), "calcSec": round(time.time() - t0, 2), "note": str(obj.get("note") or "")[:400]})
            hid = self.hub.hyp_add(h)
            made.append(f"{hid} {h['status']} ({res_line(res)})")
            if not why:                                  # odrzucone przez sito — tylko w panelu Badacza, nie w dzienniku
                self.hub.event("hypothesis", f"{hid} {describe(h)[:120]} → {h['status']} · {res_line(res)}", agent=AGENT)
        self._set("czeka na wolny czas")
        return {"ok": True, "summary": "; ".join(made) or "brak poprawnych hipotez", "meta": meta}

    def _check(self, obj, lab) -> list[str]:
        if not isinstance(obj, dict) or not isinstance(obj.get("hypotheses"), list) or not obj["hypotheses"]:
            return ["hypotheses — lista 1–3 hipotez"]
        err = []
        for i, h in enumerate(obj["hypotheses"][:3]):
            err += [f"hipoteza {i + 1}: {e}" for e in check_hyp(h, lab)]
        return err

    def status(self) -> dict:
        return {"id": "researcher", "state": "on", "doing": self.state["doing"], "since": _iso(self.state["since"])}


def res_line(r: dict | None) -> str:
    if not r or not r.get("n"):
        return "0 transakcji"
    f = lambda x, d=2: "—" if x is None else f"{x:+.{d}f}"
    parts = "/".join("·" if p["avg"] is None else ("+" if p["avg"] > 0 else "−") for p in r.get("parts") or [])
    return (f"{r['n']} transakcji, śr. {f(r['avg'])}% netto (na ślepo {f((r.get('blind') or {}).get('avg'))}%), "
            f"PF {r.get('pf') or 0:.2f}, t {f(r.get('t'))}, części {parts}, mediana {r.get('hold') or 0:.0f} świec")


def _iso(t):
    return None if t is None else datetime.fromtimestamp(float(t), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def auto_withdraw(hub, closed_positions, cfg: dict) -> list[str]:
    """Kod wycofuje hipotezę na żywo, gdy po ≥ hyp_withdraw_n transakcjach Inwestora średni wynik netto ≤ 0."""
    out = []
    for h in hub.hypotheses(500, statuses=("próba", "zatwierdzona")):
        r = [p.ret_net_pct for p in closed_positions if p.basis == h["id"]]
        if len(r) >= int(cfg["hyp_withdraw_n"]) and float(np.mean(r)) <= 0:
            hub.hyp_update(h["id"], status="wycofana", verdict_note=f"kod: {len(r)} transakcji, śr. {np.mean(r):+.2f}% netto")
            out.append(h["id"])
    return out
