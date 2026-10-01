"""
IA 4 — przestrzeń strategii: siatka, losowanie, mutacje, sąsiedzi, opisy.
Wersja projektu: 1.2 (2026-10-01) — musi zgadzać się z IA4_INSTRUKCJA.md

Reguły budowane tutaj NIE mają jeszcze SL/TP — każdą symulujemy na całej
siatce SL × TP naraz (instrukcja, sekcja 8.6), a SL/TP dopisujemy dopiero
przy zapisie strategii.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import random

import numpy as np

from . import rules
from .data import BASE_FEATURES

LINE_FEATS_THRESHOLDS = {
    "zAB": [-3.0, -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 3.0],
    "slopeA": [-2.0, -1.0, -0.5, -0.2, 0.0, 0.2, 0.5, 1.0, 2.0],
    "since": [3, 5, 7, 10, 14, 21, 35, 50, 70, 100],
}
FIXED_THRESHOLDS = {"slot": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5], "dow": [1.5, 2.5, 3.5, 4.5]}


def _round(x: float) -> float:
    if x == 0 or not np.isfinite(x):
        return 0.0
    return float(f"{x:.3g}")


def thresholds(m) -> dict:
    """Progi filtrów: percentyle 10–90 cech bazowych w grupie głównej (bez skarbca)."""
    out = {}
    g = m.zone > 0
    for f in BASE_FEATURES:
        if f in FIXED_THRESHOLDS:
            out[f] = FIXED_THRESHOLDS[f]
            continue
        x = m.feat[f][g]
        x = x[np.isfinite(x)]
        if x.size < 100:
            continue
        q = sorted({_round(v) for v in np.percentile(x, [10, 20, 30, 40, 50, 60, 70, 80, 90])})
        out[f] = q
    out.update(LINE_FEATS_THRESHOLDS)
    return out


def _line(ma, n):
    return {"ma": ma, "n": int(n)}


def fc_options(kind: str, reexpand_n: int = 2) -> list:
    if kind == "converge":
        re = {"kind": "reexpand", "n": reexpand_n}
        return [[re], [re, {"kind": "cross_back"}]]
    back = {"cross": "cross_back", "revert": "cross_back", "ribbon": "cross_back",
            "turn": "turn_back", "pcross": "pcross_back"}[kind]
    return [[], [{"kind": back}]]


def base_rule(direction, lines, signal, fc, max_bars, filters=None) -> dict:
    return {"schema": rules.SCHEMA, "direction": direction, "lines": lines, "signal": signal,
            "filters": filters or [], "exit": {"max_bars": max_bars, "fc": fc}}


# ---------------------------------------------------------------- siatka
def grid_iter(cfg: dict):
    """Pełna, deterministyczna siatka: 1) cena × linia, 2) pary linii, 3) wachlarze 3 linii."""
    T, P = cfg["ma_types"], cfg["coarse_periods"]
    MB = cfg["grid_max_bars"]
    paused = set(cfg.get("paused_kinds", []))
    dirs = ("long", "short")
    if "pcross" not in paused:
        for ma, p, d, mb in itertools.product(T, P, dirs, MB):
            for fc in fc_options("pcross"):
                yield base_rule(d, {"A": _line(ma, p)}, {"kind": "pcross"}, fc, mb)
    for pa, pb in itertools.combinations(P, 2):
        for ta, tb in itertools.product(T, T):
            L = {"A": _line(ta, pa), "B": _line(tb, pb)}
            for d, mb in itertools.product(dirs, MB):
                if "cross" not in paused:
                    for fc in fc_options("cross"):
                        yield base_rule(d, L, {"kind": "cross"}, fc, mb)
                if "converge" not in paused:
                    for g, s in cfg["grid_converge"]:
                        yield base_rule(d, L, {"kind": "converge", "grow": g, "shrink": s},
                                        fc_options("converge", cfg["grid_reexpand_n"])[0], mb)
                if "revert" not in paused:
                    for k in cfg["grid_revert_k"]:
                        for fc in fc_options("revert"):
                            yield base_rule(d, L, {"kind": "revert", "k": float(k)}, fc, mb)
                if "turn" not in paused:
                    for pos in ("below", "above"):
                        for fc in fc_options("turn"):
                            yield base_rule(d, L, {"kind": "turn", "pos": pos}, fc, mb)
    if "ribbon" not in paused:
        for t in T:
            for pa, pb, pc in itertools.combinations(P, 3):
                L = {"A": _line(t, pa), "B": _line(t, pb), "C": _line(t, pc)}
                for d, mb in itertools.product(dirs, MB):
                    for fc in fc_options("ribbon"):
                        yield base_rule(d, L, {"kind": "ribbon"}, fc, mb)


def grid_signature(cfg: dict) -> str:
    keys = ("ma_types", "coarse_periods", "grid_max_bars", "grid_converge", "grid_revert_k",
            "grid_reexpand_n", "paused_kinds")
    raw = json.dumps({k: cfg.get(k) for k in keys}, sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def grid_total(cfg: dict) -> int:
    return sum(1 for _ in grid_iter(cfg))


# ---------------------------------------------------------------- losowanie i mutacje
def _periods(rng, k, lo, hi):
    return sorted(rng.sample(range(lo, hi + 1), k))


def random_rule(rng: random.Random, cfg: dict, th: dict) -> dict:
    kinds = [k for k in rules.SIGNAL_KINDS if k not in set(cfg.get("paused_kinds", []))]
    kind = rng.choice(kinds)
    lo, hi = cfg["period_min"], cfg["period_max"]
    T = cfg["ma_types"]
    nl = 1 if kind == "pcross" else 3 if kind == "ribbon" else 2
    ps = _periods(rng, nl, lo, hi)
    L = {name: _line(rng.choice(T), p) for name, p in zip("ABC", ps)}
    if kind == "converge":
        sig = {"kind": kind, "grow": rng.randint(2, 6), "shrink": rng.randint(1, 4)}
    elif kind == "revert":
        sig = {"kind": kind, "k": rng.choice([0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0])}
    elif kind == "turn":
        sig = {"kind": kind, "pos": rng.choice(["below", "above", "any"])}
    else:
        sig = {"kind": kind}
    fc = rng.choice(fc_options(kind, rng.choice([1, 2, 3])))
    r = base_rule(rng.choice(["long", "short"]), L, sig, fc, rng.choice(cfg["max_bars_options"]))
    nf = rng.choices([0, 1, 2], weights=[4, 4, 2])[0]
    for _ in range(min(nf, cfg["max_filters"])):
        add_filter(r, rng, th)
    return r


def _feats_for(rule, th):
    has_b = "B" in rule["lines"]
    return [f for f in th if has_b or f not in ("zAB", "since")]


def add_filter(rule, rng, th):
    used = {f["f"] for f in rule["filters"]}
    opts = [f for f in _feats_for(rule, th) if f not in used]
    if not opts:
        return
    f = rng.choice(opts)
    rule["filters"].append({"f": f, "op": rng.choice([">", "<"]), "x": rng.choice(th[f])})
    rule["filters"].sort(key=lambda x: x["f"])


def valid(rule, cfg) -> bool:
    ps = [v["n"] for v in rule["lines"].values()]
    if any(p < cfg["period_min"] or p > cfg["period_max"] for p in ps):
        return False
    if len(ps) > cfg["max_lines"] or len(rule["filters"]) > cfg["max_filters"]:
        return False
    names = sorted(rule["lines"])
    order = [rule["lines"][n]["n"] for n in names]
    if order != sorted(order) or len(set(order)) != len(order):
        # linie w kolejności A (najszybsza) < B < C; ta sama długość tylko przy różnych typach
        if not (len(order) == 2 and order[0] == order[1]
                and rule["lines"]["A"]["ma"] != rule["lines"]["B"]["ma"]):
            return False
    return True


def mutate(parent: dict, rng: random.Random, cfg: dict, th: dict) -> dict:
    r = copy.deepcopy(parent)
    kind = r["signal"]["kind"]
    ops = ["period", "period", "type", "exit", "filter_add", "filter_tweak", "filter_remove", "param"]
    for _ in range(rng.choice([1, 1, 2])):
        op = rng.choice(ops)
        if op == "period":
            name = rng.choice(sorted(r["lines"]))
            p = r["lines"][name]["n"]
            step = max(1, round(0.15 * p))
            r["lines"][name]["n"] = int(p + rng.randint(-step, step) or rng.choice([-1, 1]))
        elif op == "type":
            name = rng.choice(sorted(r["lines"]))
            r["lines"][name]["ma"] = rng.choice(cfg["ma_types"])
        elif op == "exit":
            if rng.random() < 0.5:
                r["exit"]["max_bars"] = rng.choice(cfg["max_bars_options"])
            else:
                n_re = next((f.get("n", 2) for f in r["exit"]["fc"] if f["kind"] == "reexpand"), 2)
                if kind == "converge" and rng.random() < 0.5:
                    n_re = max(1, min(5, n_re + rng.choice([-1, 1])))
                r["exit"]["fc"] = rng.choice(fc_options(kind, n_re))
        elif op == "filter_add" and len(r["filters"]) < cfg["max_filters"]:
            add_filter(r, rng, th)
        elif op == "filter_tweak" and r["filters"]:
            f = rng.choice(r["filters"])
            vals = th.get(f["f"], [f["x"]])
            if rng.random() < 0.25:
                f["op"] = "<" if f["op"] == ">" else ">"
            else:
                i = int(np.argmin([abs(v - f["x"]) for v in vals]))
                f["x"] = vals[max(0, min(len(vals) - 1, i + rng.choice([-1, 1])))]
        elif op == "filter_remove" and r["filters"]:
            r["filters"].pop(rng.randrange(len(r["filters"])))
        elif op == "param":
            s = r["signal"]
            if kind == "converge":
                key = rng.choice(["grow", "shrink"])
                s[key] = max(1, min(8, s[key] + rng.choice([-1, 1])))
            elif kind == "revert":
                s["k"] = round(max(0.5, min(4.0, s["k"] + rng.choice([-0.25, 0.25]))), 2)
            elif kind == "turn":
                s["pos"] = rng.choice(["below", "above", "any"])
    return r


# ---------------------------------------------------------------- sąsiedzi i rodziny
def neighbors(rule: dict, cfg: dict, th: dict, rng: random.Random) -> list:
    """Reguły różniące się JEDNYM parametrem o mały krok (±10% okresu, sąsiedni próg…)."""
    out = []
    for name in sorted(rule["lines"]):
        p = rule["lines"][name]["n"]
        step = max(1, round(0.1 * p))
        for dp in (-step, step):
            r = copy.deepcopy(rule)
            r["lines"][name]["n"] = p + dp
            if valid(r, cfg):
                out.append(r)
    s = rule["signal"]
    if s["kind"] == "converge":
        for key in ("grow", "shrink"):
            for dv in (-1, 1):
                r = copy.deepcopy(rule)
                r["signal"][key] = s[key] + dv
                if r["signal"][key] >= 1:
                    out.append(r)
    if s["kind"] == "revert":
        for dv in (-0.25, 0.25):
            r = copy.deepcopy(rule)
            r["signal"]["k"] = round(s["k"] + dv, 2)
            if r["signal"]["k"] > 0:
                out.append(r)
    for i, f in enumerate(rule["filters"]):
        vals = th.get(f["f"], [])
        if not vals:
            continue
        j = int(np.argmin([abs(v - f["x"]) for v in vals]))
        for dj in (-1, 1):
            if 0 <= j + dj < len(vals) and vals[j + dj] != f["x"]:
                r = copy.deepcopy(rule)
                r["filters"][i]["x"] = vals[j + dj]
                out.append(r)
    if len(out) > cfg["max_param_neighbors"]:
        out = rng.sample(out, cfg["max_param_neighbors"])
    return out


def family(rule: dict) -> str:
    """Wszystko, co nie jest liczbą: rodzaj, kierunek, typy średnich, FC, limit, cechy filtrów."""
    s = rule["signal"]
    parts = [s["kind"], rule["direction"], s.get("pos", ""),
             ",".join(f"{k}:{v['ma']}" for k, v in sorted(rule["lines"].items())),
             ",".join(sorted(f["kind"] for f in rule["exit"].get("fc", []))),
             str(rule["exit"].get("max_bars")),
             ",".join(f"{f['f']}{f['op']}" for f in rule["filters"])]
    return "|".join(parts)


def _swiec(n: int) -> str:
    if n == 1:
        return "świecę"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "świece"
    return "świec"


def group(rule: dict) -> str:
    """Grupa strategii (limit max_per_group): rodzaj sygnału, kierunek, cechy filtrów z operatorem.
    Okresy, typy średnich, FC, limit czasu i SL/TP NIE tworzą nowej grupy."""
    feats = ",".join(sorted(f"{f['f']}{f['op']}" for f in rule.get("filters", [])))
    return f"{rule['signal']['kind']}|{rule['direction']}|{feats}"


# ---------------------------------------------------------------- opis słowny
_FEAT_PL = {
    "ret7": "zmiana ceny z 7 świec (%)", "ret35": "zmiana ceny z 35 świec (%)",
    "vrel": "wolumen / średni wolumen 35 świec", "atrp": "ATR14 w % ceny",
    "atrrank": "percentyl zmienności (350 świec)", "rsi": "RSI14", "slot": "numer świecy w sesji",
    "dow": "dzień tygodnia (1 = pn)", "gap": "luka otwarcia sesji (%)",
    "d5": "cena vs średnia 5 zamknięć dziennych (%)", "d20": "cena vs średnia 20 zamknięć dziennych (%)",
    "spy35": "SPY vs EMA35 (w ATR)", "spy140": "SPY vs EMA140 (w ATR)",
    "qqq35": "QQQ vs EMA35 (w ATR)", "qqq140": "QQQ vs EMA140 (w ATR)",
    "zAB": "odchylenie A−B (w ATR)", "slopeA": "nachylenie A z 3 świec (w ATR)",
    "since": "świec od ostatniego przecięcia A/B",
}


def describe(rule: dict) -> str:
    L = {k: f"{v['ma']}{v['n']}" for k, v in rule["lines"].items()}
    s = rule["signal"]
    long = rule["direction"] == "long"
    k = s["kind"]
    if k == "cross":
        txt = f"{L['A']} przecina {L['B']} {'w górę' if long else 'w dół'}"
    elif k == "converge":
        txt = (f"{L['A']} {'pod' if long else 'nad'} {L['B']}: odległość rosła {s['grow']} {_swiec(s['grow'])}, "
               f"potem malała {s['shrink']} — zapowiedź przecięcia")
    elif k == "turn":
        pos = {"below": f", {L['A']} pod {L.get('B', '')}", "above": f", {L['A']} nad {L.get('B', '')}",
               "any": ""}[s.get("pos", "any")]
        txt = f"{L['A']} zawraca {'w górę' if long else 'w dół'}{pos}"
    elif k == "revert":
        txt = (f"odchylenie {L['A']}−{L['B']} wraca zza {'−' if long else '+'}{s['k']} ATR")
    elif k == "ribbon":
        txt = f"układ {L['A']} {'>' if long else '<'} {L['B']} {'>' if long else '<'} {L['C']} właśnie powstał"
    else:
        txt = f"cena przecina {L['A']} {'w górę' if long else 'w dół'}"
    parts = [f"{'LONG' if long else 'SHORT'}: {txt}"]
    for f in rule["filters"]:
        parts.append(f"filtr: {_FEAT_PL.get(f['f'], f['f'])} {f['op']} {f['x']}")
    ex = rule["exit"]
    if "sl" in ex:
        parts.append(f"SL {ex['sl']}% / TP {ex['tp']}%")
    fcs = []
    for fc in ex.get("fc", []):
        fcs.append({"reexpand": f"ponowne rozejście ({fc.get('n', 2)} {_swiec(fc.get('n', 2))})", "cross_back": "przecięcie odwrotne",
                    "turn_back": "zawrócenie A", "pcross_back": "cena wraca przez A"}[fc["kind"]])
    if fcs:
        parts.append("FC: " + ", ".join(fcs))
    if ex.get("max_bars"):
        parts.append(f"limit {ex['max_bars']} {_swiec(ex['max_bars'])}")
    return " · ".join(parts)
