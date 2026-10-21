"""
IA 4 — FX-SPRINT: sprint 10 $ → cel w ≤ N dni na sygnałach Powrót.v2 (instrukcja, sekcja 7b; informacyjne, od 1.59).
Wersja projektu: 1.60 (2026-10-21) — musi zgadzać się z IA4_INSTRUKCJA.md

Zadanie człowieka (21.10.2026): sprint — z 10 $ zrobić w krótkim czasie 100 $; po sukcesie wypłata 90 $ i start od 10 $,
saldo 0 → dopłata 10 $; sprint najwyżej 2 tygodnie, jeden naraz; ≥ 85% udanych przy ≥ 40 sprintach w roku; rok 1 →
100 najlepszych → sprawdzian na roku 2 → wersja o najbardziej zbliżonych wynikach. Cel 10 × jest arytmetycznie
nieosiągalny (85% × 100 $ = średnio +75 $ na sprint z 10 $, czyli ok. 7% ruchu ceny co 2 tygodnie bez dźwigni —
Powrót.v2 daje ok. 0,5%); decyzja człowieka z 21.10.2026: „największy cel przy 85%” — szukamy, jak duży cel jest realny.

  * Sygnały — Powrót.v2 bez zmian (jedyna strategia, która przeszła doubleProof): short po open świecy po sygnale,
    TP = szczyt − 0,5 × (szczyt − baza), bez SL, najwyżej 60 świec, jedna pozycja na parę. Filtr do wyboru: wszystkie /
    „razem” (inna para z tą walutą daje sygnał w tej samej świecy, 1.57) / sygnał na 1. świecy po impulsie (1.57).
  * Sprint — zaczyna się przy pierwszym sygnale po poprzednim sprincie, start 10 $; depozyt pozycji = f × saldo
    (wartość = 30 × depozyt), najwyżej wolny depozyt; sukces — saldo (wycena na zamknięciu świecy) ≥ cel → wszystko
    zamknięte; porażka — stop out (poziom depozytu < 50% po najgorszej cenie świecy, saldo nie spada poniżej 0) albo
    koniec limitu dni (zamknięcie po cenie zamknięcia). Każdy sprint zaczyna od 10 $: nadwyżka — wypłata, brak — dopłata
    (sukces: wypłata 10 × (cel − 1) $, saldo 0: dopłata 10 $).
  * Rozliczenie jak w badaniach FX: spread w pipsach raz na transakcję, dźwignia 1:30, wynik jak w rachunku v2/v3,
    jednostki bez zaokrąglania do 0,01 lota (10 $ to za mało na minimalną pozycję XTB — ok. 35–45 $ depozytu).
  * Wybór (rok 1 do 15.10.2025, rok 2 od): wersje z ≥ 85% i ≥ 40 sprintami na rok w roku 1 → 100 najlepszych (największy
    cel, potem skuteczność, potem zysk netto) → rok 2; wybrana: największy cel spełniający warunki w obu latach, przy
    remisie najmniejsza różnica skuteczności między latami.
  * DOUBLEPROOF (--double-proof) — wybrana wersja na 10 parach fx1h_double_proof (warunki ustalone przed testem;
    otwarcia w data/fxsprint/doubleproof.jsonl).

    python -m ia4.fxsprint                  # ok. minuty → ~/Desktop/IA4/FX-SPRINT.xlsx
    python -m ia4.fxsprint --double-proof   # + sprawdzian na 10 nowych parach (otwarcie zapisane)
    python -m ia4.fxsprint --selftest       # „WYNIK: OK”
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numba as nb
import numpy as np
import pandas as pd

from . import __version__, config
from . import fxpowrot2 as F2
from . import fxpowrot3 as F3
from . import fxshort as fs
from .fxshort import PAIRS

OUT_DIR = config.RESEARCH_DIR / 'data' / 'fxsprint'
GRANICA = F3.GRANICA
START, LEV, STOP_OUT = 10.0, 30.0, 0.5
CRIT = dict(sukces=85.0, na_rok=40.0)                  # warunki człowieka (21.10.2026)
DP_CRIT = dict(sukces=85.0, na_rok=40.0, netto=0.0)    # warunek doubleProof (ustalony przed testem, 21.10.2026)
CELE = (1.01, 1.02, 1.03, 1.04, 1.05, 1.06, 1.07, 1.08, 1.10, 1.12, 1.15, 1.20, 1.25, 1.30, 1.40, 1.50, 1.75, 2.0, 2.5, 3.0, 5.0, 10.0)
DEPOZYT = (0.10, 0.20, 0.25, 0.33, 0.50, 0.75, 1.00)
DNI = (1, 2, 3, 5, 7, 10, 14)
FILTRY = ('wszystkie', 'razem', '1. świeca')
TOP = 100
WYNIK = {1: 'sukces', 2: 'stop-out', 3: 'czas', 4: 'koniec danych'}
YEAR = 365.25 * 86400


# ---------------------------------------------------------------- sygnały i transakcje Powrót.v2

def signals(R, filtr, others=None):
    """Zdarzenia Powrót.v2: wszystkie / razem (others — sygnały drugiej grupy par jako partnerzy) / 1. świeca po impulsie."""
    if filtr == '1. świeca':
        return F3.events(R, 2.0, 1)
    E = F3.mark_together(F3.events(R), others=others)
    return E[E.razem] if filtr == 'razem' else E


def trades(R, E):
    """Każde zdarzenie z własnym wyjściem v2 (TP albo 60 świec); jednej pozycji na parę pilnuje sprint."""
    rows = []
    for k, p in enumerate(R.pairs):
        q = E[E.para == p]
        if not len(q):
            continue
        F = R.F[p]; sp = R.spread[p] * F2.pip_of(p)
        r, x, w, _ = F3.sim1(F['o'], F['h'], F['l'], F['c'], np.nan_to_num(F['run1']), q.j.values.astype(np.int64), q.B.values, q.P.values,
                             q.A.values, sp, 0.5, 60, 1.0, 0.0, False, 0.0, 0, 0.0)
        ok = ~np.isnan(r)
        if not ok.any():
            continue
        J = q.j.values[ok].astype(np.int64); j1 = J + x[ok].astype(np.int64)
        TP = q.P.values[ok] - 0.5 * (q.P.values[ok] - q.B.values[ok])
        rows.append(pd.DataFrame(dict(para=p, k=k, j=J, ej=J + 1, ej1=j1, en=F['o'][J + 1], ex=np.where(w[ok] == 0, TP, F['c'][j1]), sp=sp, wynik=r[ok])))
    cols = ['para', 'k', 'j', 'ej', 'ej1', 'en', 'ex', 'sp', 'wynik']
    return (pd.concat(rows) if rows else pd.DataFrame(columns=cols)).sort_values(['ej', 'k']).reset_index(drop=True)


def matrices(R):
    return tuple(np.ascontiguousarray(np.column_stack([R.F[p][x] for p in R.pairs]).astype(np.float64)) for x in ('o', 'h', 'c'))


# ---------------------------------------------------------------- silnik sprintu

@nb.njit(cache=True)
def sprint_run(T, O, H, C, ej, ek, ej1, ex, sp, f, cel, dsec, lev, so, start):
    """Kolejne sprinty (jeden naraz). Kod wyniku: 1 sukces, 2 stop out, 3 koniec limitu dni, 4 koniec danych."""
    n = T.size; ne = ej.size; P = O.shape[1]
    s0 = np.empty(ne, np.int64); s1 = np.empty(ne, np.int64); code = np.empty(ne, np.int64)
    bal = np.empty(ne); ntr = np.empty(ne, np.int64); peak = np.empty(ne)
    act = np.zeros(P, np.bool_); m = np.zeros(P); en = np.zeros(P); pj1 = np.zeros(P, np.int64); pex = np.zeros(P); psp = np.zeros(P)
    i = 0; ns = 0
    while i < ne and ns < ne:
        j0 = ej[i]
        if j0 >= n:
            break
        cash = start; eqp = start; nt = 0; cd = 4; b = start; pk = start
        for p in range(P):
            act[p] = False
        j = j0
        while j < n:
            while i < ne and ej[i] == j:                      # wejścia po open tej świecy
                p = ek[i]
                if not act[p]:
                    used = 0.0
                    for q in range(P):
                        if act[q]:
                            used += m[q]
                    mm = min(f * eqp, eqp - used)
                    if mm > 1e-9:
                        act[p] = True; m[p] = mm; en[p] = O[j, p]; pj1[p] = ej1[i]; pex[p] = ex[i]; psp[p] = sp[i]; nt += 1
                i += 1
            used = 0.0; worst = cash                           # stop out po najgorszej cenie świecy (przed TP — pesymistycznie)
            for q in range(P):
                if act[q]:
                    used += m[q]; worst += m[q] * lev * ((en[q] - H[j, q]) / en[q] - psp[q] / en[q])
            if used > 0.0 and worst < so * used:
                cd = 2; b = max(worst, 0.0); break
            for q in range(P):                                 # wyjścia v2 (TP / 60 świec)
                if act[q] and pj1[q] <= j:
                    cash += m[q] * lev * ((en[q] - pex[q]) / en[q] - psp[q] / en[q]); act[q] = False
            eq = cash
            for q in range(P):
                if act[q]:
                    eq += m[q] * lev * ((en[q] - C[j, q]) / en[q] - psp[q] / en[q])
            if eq > pk:
                pk = eq
            if eq >= cel * start:
                cd = 1; b = eq; break
            if T[j] + 3600 - T[j0] >= dsec:
                cd = 3; b = eq; break
            eqp = eq; b = eq; j += 1
        if j >= n:
            j = n - 1
        s0[ns] = j0; s1[ns] = j; code[ns] = cd; bal[ns] = b; ntr[ns] = nt; peak[ns] = pk; ns += 1
        if cd == 4:
            break
        while i < ne and ej[i] <= j:
            i += 1
    return s0[:ns], s1[:ns], code[:ns], bal[:ns], ntr[:ns], peak[:ns]


class Market:
    """Siatka czasu, macierze cen i transakcje każdego filtra — liczone raz."""

    def __init__(self, R, trades_by_filter: dict):
        self.R = R; self.T = R.t.astype(np.int64); self.O, self.H, self.C = matrices(R)
        self.tr = trades_by_filter
        t_first = int(R.t[min(fs.WARMUP, R.n - 1)]); t_end = int(R.t[-1]) + 3600; g = int(GRANICA.timestamp())
        self.g = g; self.t_first = t_first; self.t_end = t_end
        self.L = {1: max(g - t_first, 1) / YEAR, 2: max(t_end - g, 1) / YEAR, 0: max(t_end - t_first, 1) / YEAR}

    def run(self, filtr, f, dni, cel):
        tr = self.tr[filtr]
        if not len(tr):
            return pd.DataFrame(columns=['j0', 'j1', 'kod', 'saldo', 'transakcji', 'szczyt'])
        r = sprint_run(self.T, self.O, self.H, self.C, tr.ej.values.astype(np.int64), tr.k.values.astype(np.int64), tr.ej1.values.astype(np.int64),
                       tr.ex.values.astype(np.float64), tr.sp.values.astype(np.float64), float(f), float(cel), int(dni * 86400), LEV, STOP_OUT, START)
        return pd.DataFrame(dict(j0=r[0], j1=r[1], kod=r[2], saldo=r[3], transakcji=r[4], szczyt=r[5]))


def metrics(S, mk: Market, year=0):
    """Wyniki sprintów z danego roku (po dacie startu; 0 — cały okres). Sprint urwany końcem danych się nie liczy."""
    S = S[S.kod != 4]
    if year:
        ts = mk.T[S.j0.values]
        S = S[(ts < mk.g) if year == 1 else (ts >= mk.g)]
    n = len(S); L = mk.L[year]
    if not n:
        return dict(n=0, na_rok=0.0, sukces=np.nan, stop=np.nan, czas=np.nan, netto=0.0, wyplaty=0.0, doplaty=0.0, sr_dni=np.nan, seria=0, dolek=0.0,
                    sr_tr=np.nan, szczyt_x=np.nan)
    k = S.kod.values; b = S.saldo.values; net = b - START
    cum = np.r_[0.0, np.cumsum(net)]; dolek = float((np.maximum.accumulate(cum) - cum).max())
    fail = k != 1; seria = 0; cur = 0
    for x in fail:
        cur = cur + 1 if x else 0; seria = max(seria, cur)
    dni = (mk.T[S.j1.values] + 3600 - mk.T[S.j0.values]) / 86400
    return dict(n=n, na_rok=n / L, sukces=(k == 1).mean() * 100, stop=(k == 2).mean() * 100, czas=(k == 3).mean() * 100, netto=float(net.sum()),
                wyplaty=float(np.maximum(net, 0).sum()), doplaty=float(np.maximum(-net, 0).sum()), sr_dni=float(dni.mean()), seria=int(seria), dolek=dolek,
                sr_tr=float(S.transakcji.mean()), szczyt_x=float(S.szczyt.max() / START))


def grid(mk: Market, log=print):
    rows = []; t0 = time.time()
    for filtr in FILTRY:
        for f in DEPOZYT:
            for d in DNI:
                for c in CELE:
                    S = mk.run(filtr, f, d, c)
                    m1, m2 = metrics(S, mk, 1), metrics(S, mk, 2)
                    rows.append(dict(filtr=filtr, f=f, dni=d, cel=c, **{f'{k}1': v for k, v in m1.items()}, **{f'{k}2': v for k, v in m2.items()}))
    G = pd.DataFrame(rows)
    for y in (1, 2):
        G[f'ok{y}'] = (G[f'sukces{y}'] >= CRIT['sukces']) & (G[f'na_rok{y}'] >= CRIT['na_rok'])
    G['d_sukces'] = (G.sukces1 - G.sukces2).abs()
    G['d_na_rok'] = (G.na_rok1 - G.na_rok2).abs() / G.na_rok1.where(G.na_rok1 > 0) * 100
    log(f'Siatka: {len(G)} wersji sprintu ({len(FILTRY)} filtry × {len(DEPOZYT)} depozytów × {len(DNI)} limitów dni × {len(CELE)} celów), {time.time() - t0:.0f} s')
    return G


def select(G):
    """Rok 1 → 100 najlepszych (cel, skuteczność, zysk netto) → rok 2 → wybrana (największy cel w obu latach, najmniejsza różnica)."""
    Q = G[G.ok1].sort_values(['cel', 'sukces1', 'netto1'], ascending=[False, False, False])
    top = Q.head(TOP).copy(); top.insert(0, 'miejsce', np.arange(1, len(top) + 1))
    best = None; zdane = False
    if len(top):
        P2 = top[top.ok2].sort_values(['cel', 'd_sukces', 'd_na_rok', 'netto2'], ascending=[False, True, True, False])
        if len(P2):
            best = P2.iloc[0]; zdane = True
        else:
            best = top.sort_values(['d_sukces', 'cel'], ascending=[True, False]).iloc[0]
    top['wybrana'] = False
    if best is not None:
        top.loc[best.name, 'wybrana'] = True
    return top, best, zdane


def best_map(G):
    """Dla każdego filtra i celu — wersja z najwyższą skutecznością w roku 1 (wśród ≥ 40 sprintów na rok) i jej rok 2."""
    rows = []
    for (filtr, c), g in G.groupby(['filtr', 'cel'], sort=False):
        q = g[g.na_rok1 >= CRIT['na_rok']]
        if not len(q):
            rows.append(dict(filtr=filtr, cel=c, szczyt=max(g.szczyt_x1.max(), g.szczyt_x2.max()))); continue
        b = q.sort_values(['sukces1', 'netto1'], ascending=False).iloc[0]
        rows.append(dict(filtr=filtr, cel=c, f=b.f, dni=b.dni, sukces1=b.sukces1, sukces2=b.sukces2, na_rok1=b.na_rok1, na_rok2=b.na_rok2,
                         netto1=b.netto1, netto2=b.netto2, szczyt=max(g.szczyt_x1.max(), g.szczyt_x2.max())))
    return pd.DataFrame(rows)


def continuous(mk: Market, filtr, f):
    """Te same sygnały i depozyt bez celu i limitu dni: jeden rachunek od 10 $ (po stop oucie dopłata i dalej)."""
    S = mk.run(filtr, f, 10 ** 6, 1e18)
    return dict(saldo=float(S.saldo.iloc[-1]) if len(S) else START, stop_outy=int((S.kod == 2).sum()), wplaty=START * len(S),
                netto=float(S.saldo.sum() - START * len(S)))


def max_adverse(R, tr):
    """Najgłębszy ruch ceny przeciw pozycji (szczyt świecy ponad wejście, %) w czasie transakcji."""
    return float(max(((R.F[r.para]['h'][r.ej:r.ej1 + 1].max() - r.en) / r.en * 100 for r in tr.itertuples()), default=0.0))


def v2_move_14d(mk: Market):
    """Średni wynik Powrót.v2 (bez dźwigni, suma % transakcji) na 14 dni — do arkusza CEL ×10."""
    D = F3.simulate(mk.R, F3.events(mk.R))
    return float(D.wynik.sum() / ((mk.t_end - mk.t_first) / 86400 / 14)), len(D)


# ---------------------------------------------------------------- doubleProof

def double_proof(R, Rdp, best, log=print):
    """Wybrana wersja sprintu na 10 parach fx1h_double_proof; partnerzy „razem” — sygnały na wszystkich 20 parach."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    logp = OUT_DIR / 'doubleproof.jsonl'
    n_old = sum(1 for _ in logp.open(encoding='utf-8')) if logp.exists() else 0
    cfg = dict(filtr=best.filtr, f=float(best.f), dni=int(best.dni), cel=float(best.cel))
    with logp.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(dict(otwarcie=n_old + 1, czas=datetime.now(timezone.utc).isoformat(timespec='seconds'), wersja=__version__,
                                 do=str(pd.Timestamp(int(Rdp.t[-1]), unit='s')), sprint=cfg), ensure_ascii=False) + '\n')
    Ed = signals(Rdp, best.filtr, others=F3.events(R))
    mk = Market(Rdp, {best.filtr: trades(Rdp, Ed)})
    S = mk.run(best.filtr, best.f, best.dni, best.cel)
    m0, m1, m2 = metrics(S, mk, 0), metrics(S, mk, 1), metrics(S, mk, 2)
    ok = m0['n'] > 0 and m0['sukces'] >= DP_CRIT['sukces'] and m0['na_rok'] >= DP_CRIT['na_rok'] and m0['netto'] > DP_CRIT['netto']
    log(f"doubleProof sprintu (otwarcie nr {n_old + 1}): {m0['n']} sprintów ({m0['na_rok']:.0f} na rok), skuteczność {m0['sukces']:.1f}%, "
        f"netto {m0['netto']:+.2f} $ → {'ZALICZONY' if ok else 'NIE zaliczony'}")
    return dict(otwarcie=n_old + 1, cfg=cfg, m=(m0, m1, m2), ok=ok)


# ---------------------------------------------------------------- całość

def compute(R, log=print, Rdp=None) -> dict:
    t0 = time.time()
    E = F3.mark_together(F3.events(R))
    tr = {'wszystkie': trades(R, E), 'razem': trades(R, E[E.razem]), '1. świeca': trades(R, F3.events(R, 2.0, 1))}
    mk = Market(R, tr)
    log('Sygnały Powrót.v2: ' + ', '.join(f'{k} {len(v)}' for k, v in tr.items()))
    G = grid(mk, log)
    top, best, zdane = select(G)
    O = dict(od=pd.Timestamp(mk.t_first, unit='s'), do=pd.Timestamp(mk.t_end, unit='s'), lata=mk.L, G=G, top=top, best=best, zdane=zdane, mapa=best_map(G))
    O['ruch14'], O['v2_n'] = v2_move_14d(mk)
    O['mae'] = max_adverse(R, tr['wszystkie'])
    O['x10'] = G[G.cel == 10.0][['sukces1', 'sukces2']].max().to_dict()
    O['szczyt_max'] = float(np.nanmax(np.r_[G.szczyt_x1.values, G.szczyt_x2.values]))
    O['max_cel_r1'] = float(G[G.ok1].cel.max()) if G.ok1.any() else None
    O['max_cel_oba'] = float(G[G.ok1 & G.ok2].cel.max()) if (G.ok1 & G.ok2).any() else None
    if best is not None:
        S = mk.run(best.filtr, best.f, best.dni, best.cel)
        S = S[S.kod != 4].copy()
        S['start'] = pd.to_datetime(mk.T[S.j0.values], unit='s'); S['koniec'] = pd.to_datetime(mk.T[S.j1.values] + 3600, unit='s')
        S['rok'] = np.where(mk.T[S.j0.values] < mk.g, 1, 2); S['wynik'] = S.kod.map(WYNIK)
        O['sprinty'] = S.reset_index(drop=True)
        O['ciagly'] = continuous(mk, best.filtr, best.f)
        log(f"Wybrana: {best.filtr}, depozyt {best.f:.0%}, ≤ {best.dni} dni, cel ×{best.cel:g} ({START * best.cel:.2f} $) — rok 1: {best.sukces1:.1f}% "
            f"({best.na_rok1:.0f}/rok), rok 2: {best.sukces2:.1f}% ({best.na_rok2:.0f}/rok){'' if zdane else ' — rok 2 NIE spełnia warunków'}")
    else:
        log('Żadna wersja nie spełnia 85% i ≥ 40 sprintów na rok w roku 1')
    log(f"Cel ×10: najwyższa skuteczność rok 1 {O['x10'].get('sukces1', 0):.1f}%, rok 2 {O['x10'].get('sukces2', 0):.1f}%; najwyżej w jakimkolwiek "
        f"sprincie: ×{O['szczyt_max']:.2f}")
    if Rdp is not None and best is not None:
        O['dp'] = double_proof(R, Rdp, best, log)
    O['czas_min'] = (time.time() - t0) / 60
    return O


def pl(s: str) -> str:
    """Przecinek dziesiętny w tekście dla człowieka (1.03 → 1,03)."""
    return re.sub(r'(?<=\d)\.(?=\d)', ',', s)


def conclusions(O) -> list:
    return [pl(x) for x in _conclusions(O)]


def _conclusions(O) -> list:
    b = O['best']; L = []
    L.append(f"Cel 10 × w ≤ 14 dni: najlepsza wersja ma {O['x10'].get('sukces1', 0):.1f}% udanych w roku 1 i {O['x10'].get('sukces2', 0):.1f}% w roku 2; "
             f"najwyżej, do jakiego doszedł jakikolwiek sprint w {len(O['G'])} wersjach: ×{O['szczyt_max']:.2f}. Arytmetyka — arkusz CEL ×10.")
    if b is None:
        L.append('Żadna wersja nie spełnia warunków człowieka (≥ 85% udanych, ≥ 40 sprintów na rok) w roku 1.')
        return L
    L.append(f"Największy cel z ≥ 85% i ≥ 40 sprintami na rok w roku 1: ×{O['max_cel_r1']:g} ({START * O['max_cel_r1']:.2f} $); w obu latach: "
             + (f"×{O['max_cel_oba']:g} ({START * O['max_cel_oba']:.2f} $)." if O['max_cel_oba'] else 'żaden.'))
    L.append(f"Wybrana (spośród {len(O['top'])} najlepszych z roku 1, sprawdzonych na roku 2): sygnały {b.filtr}, depozyt {b.f:.0%} salda na pozycję, ≤ {b.dni} dni, "
             f"cel ×{b.cel:g} (10 $ → {START * b.cel:.2f} $). Rok 1: {b.sukces1:.1f}% udanych, sprintów na rok {b.na_rok1:.0f}, netto {b.netto1:+.2f} $; "
             f"rok 2: {b.sukces2:.1f}%, na rok {b.na_rok2:.0f}, netto {b.netto2:+.2f} $." + ('' if O['zdane'] else ' Rok 2 NIE spełnia warunków — to najbliższa z setki.'))
    so = (1 - STOP_OUT) / (b.f * LEV) * 100
    L.append(f"Ryzyko: depozyt {b.f:.0%} salda na pozycję → ruch ceny o ok. {so:.2f}% przeciw pozycji to stop out (połowa salda sprintu). Najgłębszy ruch przeciw "
             f"jakiejkolwiek transakcji Powrót.v2 w tych 2 latach: {O['mae']:.2f}% — stop outu nie było, ale zapas jest mały.")
    c = O.get('ciagly')
    if c:
        L.append(f"Te same sygnały i depozyt bez sprintów (jeden rachunek od 10 $, zyski zostają): saldo końcowe {c['saldo']:.2f} $, stop outów {c['stop_outy']}. "
                 'Sprint nie tworzy przewagi — zamienia procent składany na częste, małe wypłaty.')
    L.append('Zarządzanie kapitałem nie zmienia średniego wyniku; duży cel = rzadki sukces, częsty sukces = mały cel. 10 $ nie wystarcza na 0,01 lota w XTB '
             '(ok. 35–45 $ depozytu) — wyniki w $ skalują się liniowo ze startem (np. 100 $ → 10 × więcej).')
    if O.get('dp'):
        d = O['dp']; m0 = d['m'][0]
        L.append(f"doubleProof (10 nowych par, otwarcie nr {d['otwarcie']}): {m0['n']} sprintów, {m0['na_rok']:.0f} na rok, {m0['sukces']:.1f}% udanych, "
                 f"netto {m0['netto']:+.2f} $ → {'ZALICZONY' if d['ok'] else 'NIE zaliczony'}.")
    return L


# ---------------------------------------------------------------- Excel

def write_xlsx(O: dict, path: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.chart import LineChart, Reference
    from openpyxl.chart.axis import DateAxis
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter as CL

    FN = 'Arial'
    fN = Font(name=FN, size=10); fB = Font(name=FN, size=10, bold=True); fT = Font(name=FN, size=14, bold=True)
    fH = Font(name=FN, size=10, bold=True, color='FFFFFF'); fS = Font(name=FN, size=9, italic=True, color='555555')
    HDR = PatternFill('solid', fgColor='1F3A5F'); GRY = PatternFill('solid', fgColor='EEF2F7'); SEL = PatternFill('solid', fgColor='FFF2CC')
    GOOD = PatternFill('solid', fgColor='E2F0D9'); BAD = PatternFill('solid', fgColor='FBE5D6')
    thin = Side(style='thin', color='BFBFBF'); BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
    WR = Alignment(wrap_text=True, vertical='top')
    PCT = '0.0%'; USD = '#,##0.00 [$$-409]'; DT = 'yyyy-mm-dd hh:mm'; DD = 'yyyy-mm-dd'
    wb = Workbook()

    def sheet(name, first=False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = name; ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = 'landscape'; ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
        return ws

    def hdr(ws, r, c, names, widths=None):
        for k, nm in enumerate(names):
            x = ws.cell(r, c + k, nm); x.font = fH; x.fill = HDR; x.border = BOX
            x.alignment = Alignment(wrap_text=True, vertical='center', horizontal='center')
        for k, w in enumerate(widths or []):
            if w: ws.column_dimensions[CL(c + k)].width = w
        ws.row_dimensions[r].height = 42

    def put(ws, r, c, v, font=fN, fmt=None, fill=None):
        if isinstance(v, np.floating): v = float(v)
        if isinstance(v, (np.integer, np.bool_)): v = int(v)
        if isinstance(v, float) and not np.isfinite(v): v = None
        if isinstance(v, pd.Timestamp): v = v.to_pydatetime()
        x = ws.cell(r, c, v); x.font = font; x.border = BOX
        if fmt: x.number_format = fmt
        if fill: x.fill = fill
        return x

    def note(ws, r, c, text, span=10, h=None):
        x = ws.cell(r, c, text); x.font = fS; x.alignment = WR
        if span > 1: ws.merge_cells(start_row=r, start_column=c, end_row=r, end_column=c + span - 1)
        if h: ws.row_dimensions[r].height = h

    def pct(v):
        return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else v / 100

    b = O['best']; S = O.get('sprinty')

    # SPRINTY (pierwszy w kodzie, bo PODSUMOWANIE liczy z niego formułami)
    wsP = sheet('PODSUMOWANIE', first=True)
    wsS = sheet('SPRINTY')
    r0 = 5; nS = 0 if S is None else len(S); rE = r0 + max(nS, 1) - 1
    if S is not None:
        wsS['A1'] = pl(f"SPRINTY — wybrana wersja: {b.filtr}, depozyt {b.f:.0%}, ≤ {b.dni} dni, cel ×{b.cel:g}"); wsS['A1'].font = fT
        put(wsS, 2, 1, 'Start sprintu ($)', fB, fill=GRY); put(wsS, 2, 2, START, fmt=USD)
        note(wsS, 2, 3, 'Saldo końcowe — z symulacji (wycena na zamknięciu świecy, stop out po najgorszej cenie). Każdy sprint zaczyna od 10 $: nadwyżka to wypłata, '
                        'brak — dopłata. Rok — według daty startu (rok 2 od 15.10.2025).', 9, 30)
        hdr(wsS, 4, 1, ['Nr', 'Rok', 'Start (UTC)', 'Koniec (UTC)', 'Dni', 'Transakcji', 'Wynik', 'Saldo końcowe', 'Wypłata', 'Dopłata', 'Netto narastająco',
                        'Najwyżej w sprincie'], [6, 6, 17, 17, 7, 10, 11, 13, 11, 11, 14, 13])
        for k, v in enumerate(S.itertuples()):
            r = r0 + k
            put(wsS, r, 1, k + 1); put(wsS, r, 2, int(v.rok)); put(wsS, r, 3, v.start, fmt=DT); put(wsS, r, 4, v.koniec, fmt=DT)
            put(wsS, r, 5, f'=D{r}-C{r}', fmt='0.0'); put(wsS, r, 6, int(v.transakcji))
            put(wsS, r, 7, v.wynik, fill=GOOD if v.kod == 1 else BAD); put(wsS, r, 8, round(float(v.saldo), 4), fmt=USD)
            put(wsS, r, 9, f'=MAX(H{r}-$B$2,0)', fmt=USD); put(wsS, r, 10, f'=MAX($B$2-H{r},0)', fmt=USD)
            put(wsS, r, 11, f'=I{r}-J{r}' if k == 0 else f'=K{r - 1}+I{r}-J{r}', fmt=USD); put(wsS, r, 12, round(float(v.szczyt), 4), fmt=USD)
        wsS.freeze_panes = 'A5'

    # PODSUMOWANIE
    ws = wsP
    for col, w in zip('ABCD', (46, 22, 15, 15)):
        ws.column_dimensions[col].width = w
    ws['A1'] = 'FX-SPRINT — 10 $ → cel w ≤ N dni na sygnałach Powrót.v2'; ws['A1'].font = fT
    ws['A2'] = (f"IA4 {__version__} · badanie informacyjne · 10 par 1h, sygnały od {O['od']:%Y-%m-%d} do {O['do']:%Y-%m-%d} · rok 1 do {GRANICA:%Y-%m-%d}, rok 2 od · "
                f"policzono {pd.Timestamp.now():%Y-%m-%d %H:%M}"); ws['A2'].font = fS
    put(ws, 4, 1, 'WNIOSKI', fH, fill=HDR)
    txt = conclusions(O)
    for k, s_ in enumerate(txt):
        x = ws.cell(5 + k, 1, s_); x.font = fN; x.alignment = WR
        ws.merge_cells(start_row=5 + k, start_column=1, end_row=5 + k, end_column=4); ws.row_dimensions[5 + k].height = 44
    r = 6 + len(txt)
    if b is not None:
        put(ws, r, 1, 'WYBRANA WERSJA', fH, fill=HDR); r += 1
        for lab, val, fm in [('Sygnały', f'Powrót.v2 — {b.filtr}', None), ('Depozyt na pozycję (część salda)', float(b.f), '0%'),
                             ('Wartość pozycji (× saldo)', float(b.f) * LEV, '0.0'), ('Limit sprintu (dni kalendarzowe)', int(b.dni), '0'),
                             ('Cel (× start)', float(b.cel), '0.00'), ('Cel ($)', START * float(b.cel), USD), ('Start sprintu ($)', START, USD),
                             ('Dźwignia', f'1:{LEV:g}', None), ('Stop out (poziom depozytu)', STOP_OUT, '0%')]:
            put(ws, r, 1, lab, fB, fill=GRY); put(ws, r, 2, val, fmt=fm); r += 1
        r += 1
        hdr(ws, r, 1, ['Wynik (formuły z arkusza SPRINTY)', 'Rok 1', 'Rok 2', 'Oba lata']); rh = r; r += 1
        rng = lambda c: f'SPRINTY!${c}${r0}:${c}${rE}'   # noqa: E731
        Ly = {1: O['lata'][1], 2: O['lata'][2], 0: O['lata'][0]}
        lines = [('Długość okresu (lata)', lambda y, c: round(Ly[y], 4), '0.00'),
                 ('Sprintów', lambda y, c: f'=COUNTIFS({rng("B")},{y})' if y else f'=COUNTA({rng("G")})', '0'),
                 ('Sprintów na rok', lambda y, c: f'={c}{rh + 2}/{c}{rh + 1}', '0.0'),
                 ('Udanych', lambda y, c: f'=COUNTIFS({rng("B")},{y},{rng("G")},"sukces")' if y else f'=COUNTIFS({rng("G")},"sukces")', '0'),
                 ('Skuteczność', lambda y, c: f'=IF({c}{rh + 2}>0,{c}{rh + 4}/{c}{rh + 2},0)', PCT),
                 ('Stop out', lambda y, c: f'=COUNTIFS({rng("B")},{y},{rng("G")},"stop-out")' if y else f'=COUNTIFS({rng("G")},"stop-out")', '0'),
                 ('Koniec limitu dni', lambda y, c: f'=COUNTIFS({rng("B")},{y},{rng("G")},"czas")' if y else f'=COUNTIFS({rng("G")},"czas")', '0'),
                 ('Wypłaty ($)', lambda y, c: f'=SUMIFS({rng("I")},{rng("B")},{y})' if y else f'=SUM({rng("I")})', USD),
                 ('Dopłaty ($)', lambda y, c: f'=SUMIFS({rng("J")},{rng("B")},{y})' if y else f'=SUM({rng("J")})', USD),
                 ('Netto: wypłaty − dopłaty ($)', lambda y, c: f'={c}{rh + 8}-{c}{rh + 9}', USD),
                 ('Średnio dni na sprint', lambda y, c: f'=IFERROR(AVERAGEIFS({rng("E")},{rng("B")},{y}),0)' if y else f'=IFERROR(AVERAGE({rng("E")}),0)', '0.0'),
                 ('Spełnia warunki (≥ 85%, ≥ 40 na rok)', lambda y, c: f'=IF(AND({c}{rh + 5}>=0.85,{c}{rh + 3}>=40),"TAK","NIE")', None)]
        for k, (lab, fn, fm) in enumerate(lines):
            put(ws, r + k, 1, lab, fB, fill=GRY)
            for q, (y, c) in enumerate([(1, 'B'), (2, 'C'), (0, 'D')]):
                put(ws, r + k, 2 + q, fn(y, c) if S is not None and len(S) else None, fmt=fm)
        r += len(lines) + 1
        c_ = O.get('ciagly')
        if c_:
            put(ws, r, 1, 'Bez sprintów: te same sygnały i depozyt, jeden rachunek od 10 $', fB, fill=GRY); put(ws, r, 2, c_['saldo'], fmt=USD)
            put(ws, r, 3, f"stop outów: {c_['stop_outy']}"); r += 2
        if S is not None and len(S):
            ch = LineChart(); ch.title = 'Netto narastająco: wypłaty − dopłaty ($)'; ch.height = 9; ch.width = 22
            ch.y_axis.crossAx = 500; ch.x_axis = DateAxis(crossAx=100); ch.x_axis.number_format = 'yyyy-mm'; ch.x_axis.majorTimeUnit = 'months'
            ch.x_axis.delete = False; ch.y_axis.delete = False; ch.legend = None
            ch.add_data(Reference(wsS, min_col=11, min_row=r0 - 1, max_row=rE), titles_from_data=True)
            ch.set_categories(Reference(wsS, min_col=4, min_row=r0, max_row=rE))
            ws.add_chart(ch, f'A{r}')

    # TOP100
    ws = sheet('TOP100')
    nt_ = len(O['top'])
    ws['A1'] = (f"TOP100 — {nt_} najlepszych wersji z roku 1 (≥ 85% udanych, ≥ 40 sprintów na rok; kolejność: cel, skuteczność, netto) i ich rok 2"
                + (f" — warunki roku 1 spełnia tylko {nt_} z {len(O['G'])}" if nt_ < TOP else '')); ws['A1'].font = fT
    note(ws, 2, 1, 'Żółty wiersz — wybrana: największy cel spełniający warunki także w roku 2, przy remisie najmniejsza różnica skuteczności. Zielone/czerwone „Rok 2 spełnia”. '
                   'Netto = wypłaty − dopłaty w danym roku (start każdego sprintu 10 $).', 16, 30)
    cols = [('miejsce', 'Miejsce', '0', 8), ('filtr', 'Sygnały', None, 11), ('f', 'Depozyt', '0%', 8), ('dni', 'Limit dni', '0', 7), ('cel', 'Cel ×', '0.00', 7),
            ('cel_usd', 'Cel $', USD, 9), ('na_rok1', 'R1: sprintów / rok', '0.0', 9), ('sukces1', 'R1: skuteczność', PCT, 10), ('stop1', 'R1: stop out', PCT, 9),
            ('netto1', 'R1: netto $', USD, 10), ('na_rok2', 'R2: sprintów / rok', '0.0', 9), ('sukces2', 'R2: skuteczność', PCT, 10), ('stop2', 'R2: stop out', PCT, 9),
            ('netto2', 'R2: netto $', USD, 10), ('d_sukces', 'Różnica skuteczności (pkt %)', '0.0', 11), ('ok2', 'Rok 2 spełnia', None, 9)]
    hdr(ws, 4, 1, [c[1] for c in cols], [c[3] for c in cols])
    for k, v in enumerate(O['top'].to_dict('records')):
        v['cel_usd'] = START * v['cel']
        for c, (key, _, fm, _) in enumerate(cols):
            val = v[key]
            if key in ('sukces1', 'stop1', 'sukces2', 'stop2'): val = pct(val)
            if key == 'ok2': val = 'TAK' if val else 'NIE'
            fill = SEL if v['wybrana'] else ((GOOD if v['ok2'] else BAD) if key == 'ok2' else None)
            put(ws, 5 + k, 1 + c, val, fB if v['wybrana'] else fN, fmt=fm, fill=fill)
    ws.freeze_panes = 'A5'

    # MAPA
    ws = sheet('MAPA')
    ws['A1'] = 'MAPA — dla każdego celu: najlepsza skuteczność w roku 1 (wśród wersji z ≥ 40 sprintami na rok) i ta sama wersja w roku 2'; ws['A1'].font = fT
    note(ws, 2, 1, 'Zielone — ≥ 85% udanych. „Najwyżej w sprincie” — do ilu × startu doszedł najlepszy sprint tego celu (dowolna wersja, oba lata). '
                   'Im większy cel, tym rzadszy sukces — to cena każdego sprintu, nie słabość jednej wersji.', 12, 30)
    cols = [('filtr', 'Sygnały', None, 11), ('cel', 'Cel ×', '0.00', 7), ('cel_usd', 'Cel $', USD, 9), ('f', 'Depozyt', '0%', 8), ('dni', 'Limit dni', '0', 7),
            ('sukces1', 'R1: skuteczność', PCT, 10), ('sukces2', 'R2: skuteczność', PCT, 10), ('na_rok1', 'R1: sprintów / rok', '0.0', 9),
            ('na_rok2', 'R2: sprintów / rok', '0.0', 9), ('netto1', 'R1: netto $', USD, 10), ('netto2', 'R2: netto $', USD, 10), ('szczyt', 'Najwyżej w sprincie (×)', '0.00', 10)]
    hdr(ws, 4, 1, [c[1] for c in cols], [c[3] for c in cols])
    for k, v in enumerate(O['mapa'].to_dict('records')):
        v['cel_usd'] = START * v['cel']
        for c, (key, _, fm, _) in enumerate(cols):
            val = v.get(key)
            fill = None
            if key in ('sukces1', 'sukces2'):
                fill = GOOD if (val is not None and np.isfinite(val) and val >= CRIT['sukces']) else None; val = pct(val)
            put(ws, 5 + k, 1 + c, val, fmt=fm, fill=fill)
    ws.freeze_panes = 'A5'

    # CEL ×10 — arytmetyka (formuły)
    ws = sheet('CEL ×10')
    ws.column_dimensions['A'].width = 70; ws.column_dimensions['B'].width = 16; ws.column_dimensions['C'].width = 70
    ws['A1'] = 'CEL ×10 — dlaczego 10 $ → 100 $ w 2 tygodnie przy 85% udanych jest niemożliwe przy 1:30'; ws['A1'].font = fT
    rows = [('Start sprintu ($)', START, USD, 'zadanie człowieka'), ('Cel ($)', 100.0, USD, 'zadanie człowieka'), ('Wymagana skuteczność', 0.85, PCT, 'zadanie człowieka'),
            ('Średnie saldo na końcu sprintu — co najmniej ($)', '=B5*B6', USD, 'udane kończą na celu, nieudane na ≥ 0 $'),
            ('Średni zysk na sprint — co najmniej ($)', '=B7-B4', USD, 'zasady sprintu nie zmieniają średniej: tylko przewaga × wielkość pozycji'),
            ('Dźwignia (wartość pozycji ≤ × saldo)', LEV, '0', 'jak zawsze w badaniach FX'),
            ('Wymagany średni ruch ceny na korzyść w sprincie, bez dźwigni', '=LN(B7/B4)/B9', '0.0%', 'przy stale pełnej dźwigni i doliczaniu zysków'),
            ('Powrót.v2: średni wynik na 14 dni, bez dźwigni (suma % transakcji)', O['ruch14'] / 100, '0.00%',
             f"z danych: {O['v2_n']} transakcji na 10 parach, {O['od']:%Y-%m-%d} – {O['do']:%Y-%m-%d}"),
            ('Ile razy za mało', '=B10/B11', '0.0', 'potrzebna przewaga / przewaga jedynej strategii, która przeszła doubleProof'),
            ('Cel ×10: najwyższa skuteczność w roku 1 (wszystkie wersje)', pct(O['x10'].get('sukces1', 0.0)), PCT, f"{len(O['G'])} wersji sprintu"),
            ('Cel ×10: najwyższa skuteczność w roku 2', pct(O['x10'].get('sukces2', 0.0)), PCT, ''),
            ('Najwyżej, do jakiego doszedł jakikolwiek sprint (× start)', O['szczyt_max'], '0.00', 'wszystkie wersje, oba lata')]
    hdr(ws, 3, 1, ['Wielkość', 'Wartość', 'Skąd'])
    for k, (lab, val, fm, src) in enumerate(rows):
        put(ws, 4 + k, 1, lab, fB, fill=GRY); put(ws, 4 + k, 2, val, fmt=fm); put(ws, 4 + k, 3, src)
    note(ws, 5 + len(rows), 1, 'Średnia nie zależy od reguł sprintu: wypłata 90 $ po sukcesie i dopłata 10 $ po porażce tylko przestawiają wyniki w czasie. Żeby 85% sprintów '
                              'kończyło się na 100 $, przeciętny sprint musiałby zarabiać +75 $ z 10 $. Przy 1:30 pozycja jest najwyżej 30 × saldo, więc sygnały musiałyby dawać '
                              'średnio kilka procent ruchu ceny na naszą korzyść co dwa tygodnie — kilkanaście razy więcej niż Powrót.v2. Reguły wybrane z roku 1 pod taki cel '
                              'byłyby dopasowaniem do historii, które rok 2 obala (FX-ODKRYWCA, FX-KANAŁ).', 3, 76)

    # UZASADNIENIE
    ws = sheet('UZASADNIENIE')
    ws.column_dimensions['A'].width = 130
    ws['A1'] = 'UZASADNIENIE — skąd taka budowa sprintu (wnioski z dotychczasowych badań, instrukcja sekcja 7b)'; ws['A1'].font = fT
    why = ['Sygnały: Powrót.v2 bez zmian — jedyna strategia FX, która przeszła doubleProof (1.52) i działa jako Powrót.v2 Investor (1.53).',
           'Bez SL i bez limitu czasu w transakcji: SL, wyjście po czasie i przy unieważnieniu psują wynik (1.52, 1.57). Jedyne „SL” sprintu to stop out i limit dni.',
           'Całe pozycje: zamykanie połowy na TP i reszta dalej nie jest odporne (1.54).',
           'Filtr „razem” do wyboru: sygnał, gdy inna para z tą samą walutą zawraca w tej samej świecy, jest mocniejszy na transakcję (1.57; p permutacji < 0,001).',
           'Filtr „1. świeca” do wyboru: sygnał na pierwszej świecy po impulsie — 0 stratnych okresów, o 1/3 mniej transakcji (1.57).',
           'Bez dokładania do pozycji: najlepszy stosunek zysku do obsunięcia w próbie, ale ryzyko martyngałowe (1.57). W sprincie wzrost daje depozyt jako część salda.',
           'Bez innych sygnałów: FX-SHORT-NY, FX-ODKRYWCA (miliony reguł), FX-KANAŁ i prognoza kierunku H-002 nie mają przewagi przenoszącej się na kolejny rok.',
           'Wybór uczciwy: tylko rok 1 wybiera, rok 2 sprawdza, 10 nowych par (doubleProof) — raz, z zapisem otwarcia.',
           'Zarządzanie kapitałem nie tworzy przewagi: przy tych samych sygnałach duży cel oznacza rzadki sukces, a częsty sukces — mały cel.']
    for k, s_ in enumerate(why):
        x = ws.cell(3 + k, 1, f'{k + 1}. {s_}'); x.font = fN; x.alignment = WR; ws.row_dimensions[3 + k].height = 30

    # WSZYSTKIE
    ws = sheet('WSZYSTKIE')
    ws['A1'] = f"WSZYSTKIE — {len(O['G'])} wersji sprintu (filtr w nagłówkach)"; ws['A1'].font = fT
    cols = [('filtr', 'Sygnały', None, 11), ('f', 'Depozyt', '0%', 8), ('dni', 'Limit dni', '0', 7), ('cel', 'Cel ×', '0.00', 7),
            ('n1', 'R1: sprintów', '0', 8), ('na_rok1', 'R1: na rok', '0.0', 8), ('sukces1', 'R1: skuteczność', PCT, 10), ('stop1', 'R1: stop out', PCT, 9),
            ('czas1', 'R1: koniec dni', PCT, 9), ('netto1', 'R1: netto $', USD, 10), ('dolek1', 'R1: najgłębiej $', USD, 10), ('seria1', 'R1: porażek z rzędu', '0', 9),
            ('sr_dni1', 'R1: dni', '0.0', 7), ('n2', 'R2: sprintów', '0', 8), ('na_rok2', 'R2: na rok', '0.0', 8), ('sukces2', 'R2: skuteczność', PCT, 10),
            ('stop2', 'R2: stop out', PCT, 9), ('czas2', 'R2: koniec dni', PCT, 9), ('netto2', 'R2: netto $', USD, 10), ('dolek2', 'R2: najgłębiej $', USD, 10),
            ('seria2', 'R2: porażek z rzędu', '0', 9), ('sr_dni2', 'R2: dni', '0.0', 7), ('ok1', 'R1 spełnia', None, 8), ('ok2', 'R2 spełnia', None, 8)]
    hdr(ws, 3, 1, [c[1] for c in cols], [c[3] for c in cols])
    for k, v in enumerate(O['G'].to_dict('records')):
        for c, (key, _, fm, _) in enumerate(cols):
            val = v[key]
            if key in ('sukces1', 'stop1', 'czas1', 'sukces2', 'stop2', 'czas2'): val = pct(val)
            if key in ('ok1', 'ok2'): val = 'TAK' if val else 'NIE'
            put(ws, 4 + k, 1 + c, val, fmt=fm)
    ws.auto_filter.ref = f'A3:{CL(len(cols))}{3 + len(O["G"])}'; ws.freeze_panes = 'E4'

    if O.get('dp'):
        dp = O['dp']; cfg = dp['cfg']
        ws = sheet('DOUBLEPROOF')
        ws.column_dimensions['A'].width = 34
        ws['A1'] = f"DOUBLEPROOF — wybrana wersja sprintu na 10 parach fx1h_double_proof (otwarcie nr {dp['otwarcie']})"; ws['A1'].font = fT
        note(ws, 2, 1, pl(f"Warunek ustalony przed testem (21.10.2026): cały okres — ≥ {DP_CRIT['sukces']:g}% udanych, ≥ {DP_CRIT['na_rok']:g} sprintów na rok, netto > 0 $. "
                       f"Wersja: {cfg['filtr']}, depozyt {cfg['f']:.0%}, ≤ {cfg['dni']} dni, cel ×{cfg['cel']:g}. Spread tych par — szacunek dla XTB (sekcja 7b)."), 8, 30)
        put(ws, 4, 1, 'ZALICZONY' if dp['ok'] else 'NIE ZALICZONY', fB, fill=GOOD if dp['ok'] else BAD)
        hdr(ws, 6, 1, ['Wynik', 'Cały okres', 'Rok 1', 'Rok 2'], [34, 12, 12, 12])
        for k, (lab, key, fm) in enumerate([('Sprintów', 'n', '0'), ('Sprintów na rok', 'na_rok', '0.0'), ('Skuteczność', 'sukces', PCT), ('Stop out', 'stop', PCT),
                                            ('Netto ($)', 'netto', USD), ('Najgłębiej ($)', 'dolek', USD), ('Porażek z rzędu', 'seria', '0')]):
            put(ws, 7 + k, 1, lab, fB, fill=GRY)
            for q, m in enumerate(dp['m']):
                val = m[key]
                if key in ('sukces', 'stop'): val = pct(val)
                put(ws, 7 + k, 2 + q, val, fmt=fm)
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


# ---------------------------------------------------------------- uruchomienie

def run(no_sync=False, out=None, double=False, log=print, keep=None) -> Path:
    t0 = time.time()
    from .fx import sync as fxs
    if not no_sync:
        log('Kopia fx1h — odświeżenie (python -m ia4.fx.sync)')
        fxs.sync(quiet=True, syms=list(PAIRS) + (list(F2.DP_PAIRS) if double else []))
    frames = {p: fxs.load(p) for p in PAIRS}
    R = F2.Rynek(frames, PAIRS, fs.spreads())
    Rdp = None
    if double:
        dpf = {p: fxs.load(p) for p in F2.DP_PAIRS if fxs.parquet_path(p).exists()}
        if len(dpf) == len(F2.DP_PAIRS):
            allf = dict(frames); allf.update(dpf)
            Rdp = F2.Rynek(allf, F2.DP_PAIRS, F2.DP_SPREAD)
        else:
            log('doubleProof: brak kopii części par — pomijam')
    O = compute(R, log=log, Rdp=Rdp)
    if keep is not None:
        keep.update(O)
    path = write_xlsx(O, out or (config.RESEARCH_DIR.parent / 'FX-SPRINT.xlsx'))
    log(f'Zapisano: {path}  ({(time.time() - t0) / 60:.1f} min)')
    return path


def selftest() -> bool:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  {'✓' if cond else '✗'} {name}")
        ok &= bool(cond)

    n = 400; T = (np.arange(n, dtype=np.int64) * 3600)
    O = np.full((n, 2), 1.0); H = np.full((n, 2), 1.001); C = np.full((n, 2), 1.0)
    one = lambda a: np.array(a, np.int64)   # noqa: E731
    # 1) jedna transakcja: wejście 1,0 w świecy 10, TP 0,99 w świecy 12 → +1% × 30 = +30% salda − spread
    s0, s1, k, bal, nt, pk = sprint_run(T, O, H, C, one([10]), one([0]), one([12]), np.array([0.99]), np.array([0.0001]), 1.0, 1.2, 14 * 86400, 30.0, 0.5, 10.0)
    exp = 10 + 10 * 30 * (0.01 - 0.0001)
    check('TP +1% przy depozycie 100% i 1:30 → saldo 12,97 $, cel ×1,2 osiągnięty w świecy TP', k[0] == 1 and s1[0] == 12 and abs(bal[0] - exp) < 1e-9)
    # 2) stop out: szczyt świecy 11 = 1,02 → strata 60% depozytu przy 100% salda → poziom depozytu 40% < 50%
    H2 = H.copy(); H2[11, 0] = 1.02
    s0, s1, k, bal, nt, pk = sprint_run(T, O, H2, C, one([10]), one([0]), one([12]), np.array([0.99]), np.array([0.0001]), 1.0, 1.2, 14 * 86400, 30.0, 0.5, 10.0)
    check('szczyt +2% przy pełnym depozycie → stop out w świecy 11 (przed TP), saldo ok. 3,97 $', k[0] == 2 and s1[0] == 11 and abs(bal[0] - (10 - 300 * 0.0201)) < 1e-9)
    # 3) limit dni: brak TP przez 60 świec, limit 1 dzień → koniec po 24 świecach od startu
    s0, s1, k, bal, nt, pk = sprint_run(T, O, H, C, one([10]), one([0]), one([70]), np.array([1.0]), np.array([0.0001]), 0.5, 1.2, 86400, 30.0, 0.5, 10.0)
    check('limit 1 dzień → sprint kończy się w 24. świecy (porażka „czas”), saldo = 10 $ − spread', k[0] == 3 and s1[0] == 33 and abs(bal[0] - (10 - 150 * 0.0001)) < 1e-9)
    # 4) jeden sprint naraz, depozyt 50%: dwie pary w jednym sprincie, trzecia transakcja w trakcie — pominięta, następny sprint po końcu
    s0, s1, k, bal, nt, pk = sprint_run(T, O, H, C, one([10, 11, 11, 50]), one([0, 1, 0, 1]), one([12, 13, 13, 52]), np.array([0.99, 0.99, 0.99, 0.99]),
                                        np.zeros(4), 0.5, 1.29, 14 * 86400, 30.0, 0.5, 10.0)
    check('depozyt 50%: druga para w tym samym sprincie, druga pozycja na tej samej parze pominięta', nt[0] == 2 and k[0] == 1 and s1[0] == 13)
    check('następny sprint startuje od 10 $ przy pierwszym sygnale po końcu poprzedniego', len(s0) == 2 and s0[1] == 50)
    # 5) koniec danych — sprint niedokończony oznaczony kodem 4
    s0, s1, k, bal, nt, pk = sprint_run(T, O, H, C, one([390]), one([0]), one([399]), np.array([1.0]), np.zeros(1), 1.0, 1.2, 14 * 86400, 30.0, 0.5, 10.0)
    check('sprint urwany końcem danych → kod 4 (nie liczy się do wyników)', k[0] == 4)
    # 6) wybór: rok 1 → top, rok 2 → największy cel spełniający warunki w obu latach
    G = pd.DataFrame(dict(filtr='wszystkie', f=1.0, dni=5, cel=[1.05, 1.04, 1.03], sukces1=[90.0, 92.0, 95.0], na_rok1=[50.0, 50.0, 60.0], netto1=[1.0, 1.0, 1.0],
                          sukces2=[80.0, 88.0, 94.0], na_rok2=[50.0, 50.0, 60.0], netto2=[1.0, 1.0, 1.0]))
    G['ok1'] = (G.sukces1 >= 85) & (G.na_rok1 >= 40); G['ok2'] = (G.sukces2 >= 85) & (G.na_rok2 >= 40)
    G['d_sukces'] = (G.sukces1 - G.sukces2).abs(); G['d_na_rok'] = 0.0
    top, best, zdane = select(G)
    check('wybór: cel ×1,05 odpada w roku 2 → wybrana ×1,04', zdane and abs(best.cel - 1.04) < 1e-12 and list(top.miejsce) == [1, 2, 3])
    print('\nWYNIK: OK' if ok else '\nWYNIK: BŁĄD')
    return ok


def main():
    ap = argparse.ArgumentParser(description='FX-SPRINT — sprint 10 $ → cel na sygnałach Powrót.v2')
    ap.add_argument('--bez-sync', action='store_true')
    ap.add_argument('--double-proof', action='store_true', help='+ sprawdzian wybranej wersji na 10 parach fx1h_double_proof (otwarcie zapisane)')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    print(f'IA 4 {__version__} — FX-SPRINT\n')
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    run(no_sync=a.bez_sync, double=a.double_proof)


if __name__ == '__main__':
    main()
