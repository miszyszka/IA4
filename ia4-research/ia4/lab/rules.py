"""
IA 4 — reguła strategii: linie → sygnał → filtry → wyjście (instrukcja, sekcja 8).
Wersja projektu: 1.26 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

To jest implementacja wzorcowa języka reguł `ia4-rule/1`. Każdy zapisany plik
strategii da się odtworzyć tym kodem (albo dowolnym innym, który trzyma się
definicji z instrukcji) — świeca po świecy, bez zgadywania.

Przykład reguły:
{
  "schema": "ia4-rule/1",
  "direction": "long",
  "lines":   {"A": {"ma": "EMA", "n": 21}, "B": {"ma": "SMA", "n": 60}},
  "signal":  {"kind": "converge", "grow": 3, "shrink": 2},
  "filters": [{"f": "rsi", "op": "<", "x": 45.0}],
  "exit":    {"sl": 3, "tp": 5, "max_bars": 35,
              "fc": [{"kind": "reexpand", "n": 2}]}
}
"""

from __future__ import annotations

import hashlib
import json

import numpy as np

from .data import BASE_FEATURES, LINE_FEATURES, Market
from . import sim

SCHEMA = "ia4-rule/1"
SIGNAL_KINDS = ("cross", "converge", "turn", "revert", "ribbon", "pcross")
FC_KINDS = ("reexpand", "cross_back", "turn_back", "pcross_back")


# ---------------------------------------------------------------- narzędzia
def _sh(x: np.ndarray, k: int) -> np.ndarray:
    """x przesunięte o k świec wstecz (x[t−k]); początek = NaN."""
    out = np.full_like(x, np.nan, dtype=float)
    if k < x.size:
        out[k:] = x[:-k] if k else x
    return out


def _pos(m: Market) -> np.ndarray:
    """Numer świecy od początku odcinka instrumentu (0, 1, 2…)."""
    p = m.feat.get("_pos")
    if p is None:
        p = np.empty(m.n, dtype=np.int64)
        for a, b in zip(m.seg_start, m.seg_end):
            p[a:b] = np.arange(b - a)
        m.feat["_pos"] = p
    return p


def _seg_end_of(m: Market) -> np.ndarray:
    s = m.feat.get("_segend")
    if s is None:
        s = np.empty(m.n, dtype=np.int64)
        for a, b in zip(m.seg_start, m.seg_end):
            s[a:b] = b
        m.feat["_segend"] = s
    return s


def _next_true(mask: np.ndarray, m: Market) -> np.ndarray:
    """nxt[i] = najmniejsze j ≥ i w tym samym instrumencie, gdzie mask[j]; brak → BIG."""
    out = np.full(m.n, sim.BIG, dtype=np.int64)
    for a, b in zip(m.seg_start, m.seg_end):
        idx = np.flatnonzero(mask[a:b]) + a
        if idx.size == 0:
            continue
        pos = np.searchsorted(idx, np.arange(a, b))
        valid = pos < idx.size
        out[a:b][valid] = idx[pos[valid]]
    return out


def lines_of(rule: dict, m: Market) -> dict:
    return {k: m.line(v["ma"], v["n"]) for k, v in rule["lines"].items()}


def _growing(ad: np.ndarray) -> np.ndarray:
    """krok i rośnie: |d[i]| > |d[i−1]| (oba skończone)."""
    return ad > _sh(ad, 1)


def _shrinking(ad: np.ndarray) -> np.ndarray:
    return ad < _sh(ad, 1)


def _all_true(mask: np.ndarray, start: int, count: int) -> np.ndarray:
    """out[t] = mask[t−start] & mask[t−start−1] & … (count kolejnych)."""
    out = np.ones(mask.size, dtype=bool)
    for k in range(start, start + count):
        s = _sh(mask.astype(float), k)
        out &= s == 1.0
    return out


# ---------------------------------------------------------------- sygnał
def signal_mask(rule: dict, m: Market, L: dict | None = None) -> np.ndarray:
    """Maska świec sygnału (sygnał na zamknięciu świecy t)."""
    L = L or lines_of(rule, m)
    sig = rule["signal"]
    kind = sig["kind"]
    long = rule["direction"] == "long"
    A = L["A"]
    need = 3                                   # ile świec wstecz używa reguła
    with np.errstate(invalid="ignore"):
        if kind == "cross":
            d = A - L["B"]
            d1 = _sh(d, 1)
            mask = (d1 <= 0) & (d > 0) if long else (d1 >= 0) & (d < 0)
        elif kind == "converge":
            g, s = int(sig["grow"]), int(sig["shrink"])
            d = A - L["B"]
            ad = np.abs(d)
            side = d < 0 if long else d > 0
            mask = (_all_true(_shrinking(ad), 0, s) & _all_true(_growing(ad), s, g)
                    & _all_true(side, 0, g + s + 1))
            need = g + s + 2
        elif kind == "turn":
            a1, a2 = _sh(A, 1), _sh(A, 2)
            mask = (A > a1) & (a1 <= a2) if long else (A < a1) & (a1 >= a2)
            pos = sig.get("pos", "any")
            if pos == "below":
                mask &= A < L["B"]
            elif pos == "above":
                mask &= A > L["B"]
            elif pos != "any":
                raise ValueError(f"turn.pos: {pos}")
        elif kind == "revert":
            k = float(sig["k"])
            z = (A - L["B"]) / m.feat["atr"]
            z1 = _sh(z, 1)
            mask = (z1 <= -k) & (z > -k) if long else (z1 >= k) & (z < k)
        elif kind == "ribbon":
            B, C = L["B"], L["C"]
            fin = np.isfinite(A) & np.isfinite(B) & np.isfinite(C)
            now = (A > B) & (B > C) if long else (A < B) & (B < C)
            before = _sh(now.astype(float), 1) == 1.0
            fin1 = _sh(fin.astype(float), 1) == 1.0
            mask = now & fin & fin1 & ~before
        elif kind == "pcross":
            c1, a1 = _sh(m.c, 1), _sh(A, 1)
            mask = (c1 <= a1) & (m.c > A) if long else (c1 >= a1) & (m.c < A)
        else:
            raise ValueError(f"nieznany sygnał: {kind}")
    return mask & (_pos(m) >= need)


# ---------------------------------------------------------------- filtry
def feature(name: str, m: Market, L: dict) -> np.ndarray:
    if name in BASE_FEATURES:
        return m.feat[name]
    A = L["A"]
    with np.errstate(invalid="ignore", divide="ignore"):
        if name == "zAB":
            return (A - L["B"]) / m.feat["atr"]
        if name == "slopeA":
            return (A - _sh(A, 3)) / m.feat["atr"]
        if name == "since":
            d = A - L["B"]
            d1 = _sh(d, 1)
            cross = ((d1 <= 0) & (d > 0)) | ((d1 >= 0) & (d < 0))
            cross &= _pos(m) >= 1
            out = np.full(m.n, np.nan)
            for a, b in zip(m.seg_start, m.seg_end):
                idx = np.flatnonzero(cross[a:b])
                if idx.size == 0:
                    continue
                t = np.arange(b - a)
                k = np.searchsorted(idx, t, side="right") - 1
                ok = k >= 0
                out[a:b][ok] = t[ok] - idx[k[ok]]
            return out
    raise ValueError(f"nieznana cecha: {name}")


def filter_mask(rule: dict, m: Market, L: dict) -> np.ndarray:
    mask = np.ones(m.n, dtype=bool)
    for f in rule.get("filters", []):
        x = feature(f["f"], m, L)
        with np.errstate(invalid="ignore"):
            if f["op"] == ">":
                mask &= x > f["x"]
            elif f["op"] == "<":
                mask &= x < f["x"]
            else:
                raise ValueError(f"operator filtra: {f['op']}")
    return mask


# ---------------------------------------------------------------- FC
def fc_bars(rule: dict, m: Market, L: dict, sig_t: np.ndarray) -> np.ndarray:
    """Dla każdego sygnału: świeca f ≥ e (e = t+1), na której zamknięciu zachodzi FC; −1 = brak."""
    out = np.full(sig_t.size, sim.BIG, dtype=np.int64)
    fcs = rule["exit"].get("fc", []) or []
    if not fcs or sig_t.size == 0:
        return np.full(sig_t.size, -1, dtype=np.int64)
    long = rule["direction"] == "long"
    e = np.minimum(sig_t + 1, m.n - 1)
    A = L["A"]
    ok = _pos(m) >= 3
    with np.errstate(invalid="ignore"):
        for fc in fcs:
            kind = fc["kind"]
            if kind == "reexpand":
                r = int(fc.get("n", 2))
                d = A - L["B"]
                ad = np.abs(d)
                side = d < 0 if long else d > 0
                re = _all_true(_growing(ad), 0, r) & _all_true(side, 0, r + 1) & ok
                crossed = (d > 0 if long else d < 0) & ok     # przecięcie nastąpiło
                nre = _next_true(re, m)[e]
                ncr = _next_true(crossed, m)[e]
                cand = np.where(nre < ncr, nre, sim.BIG)
            elif kind == "cross_back":
                d = A - L["B"]
                d1 = _sh(d, 1)
                mk = ((d1 >= 0) & (d < 0) if long else (d1 <= 0) & (d > 0)) & ok
                cand = _next_true(mk, m)[e]
            elif kind == "turn_back":
                a1, a2 = _sh(A, 1), _sh(A, 2)
                mk = ((A < a1) & (a1 >= a2) if long else (A > a1) & (a1 <= a2)) & ok
                cand = _next_true(mk, m)[e]
            elif kind == "pcross_back":
                c1, a1 = _sh(m.c, 1), _sh(A, 1)
                mk = ((c1 >= a1) & (m.c < A) if long else (c1 <= a1) & (m.c > A)) & ok
                cand = _next_true(mk, m)[e]
            else:
                raise ValueError(f"nieznany FC: {kind}")
            out = np.minimum(out, cand)
    return np.where(out >= sim.BIG, -1, out)


# ---------------------------------------------------------------- całość
def entries(rule: dict, m: Market, L: dict | None = None):
    """Świece sygnału (po filtrach, z miejscem na wejście) i świece FC."""
    L = L or lines_of(rule, m)
    mask = signal_mask(rule, m, L) & filter_mask(rule, m, L)
    sig_t = np.flatnonzero(mask)
    sig_t = sig_t[sig_t + 1 < _seg_end_of(m)[sig_t]]
    return sig_t.astype(np.int64), fc_bars(rule, m, L, sig_t), L


def run(rule: dict, m: Market, sl_grid, tp_grid, rec=(-1, -1)):
    """Symulacja reguły na wszystkich kombinacjach SL × TP."""
    sig_t, fcb, _ = entries(rule, m)
    direction = 1 if rule["direction"] == "long" else -1
    mb = rule["exit"].get("max_bars") or 0
    return sim.simulate(m.o, m.h, m.l, m.c, m.zone, _seg_end_of(m), sig_t, fcb, direction,
                        np.asarray(sl_grid, float), np.asarray(tp_grid, float), int(mb),
                        int(rec[0]), int(rec[1]))


def canonical(rule: dict) -> str:
    r = {k: rule[k] for k in ("schema", "direction", "lines", "signal", "filters", "exit") if k in rule}
    return json.dumps(r, sort_keys=True, separators=(",", ":"))


def rule_id(rule: dict) -> str:
    return "S-" + hashlib.sha1(canonical(rule).encode()).hexdigest()[:10]


def signal_key(rule: dict) -> str:
    """Identyfikator reguły bez SL/TP (ta sama maska sygnałów i FC)."""
    r = json.loads(canonical(rule))
    r["exit"] = {k: v for k, v in r["exit"].items() if k not in ("sl", "tp")}
    return hashlib.sha1(json.dumps(r, sort_keys=True).encode()).hexdigest()[:16]
