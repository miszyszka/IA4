"""
IA 4 — FX-POWRÓT v3: analiza stratnych transakcji Powrót.v2 i pomysłów na ulepszenie (instrukcja, sekcja 7b).
Wersja projektu: 1.57 (2026-10-21) — musi zgadzać się z IA4_INSTRUKCJA.md

Pytanie człowieka (21.10.2026): czy da się wyłapać stratne transakcje na poziomie strategii, czy jest coś, o czym nie
pomyśleliśmy, i czy da się wzmocnić zyskowne?

  * STRATNE i CECHY — każda stratna transakcja v2 i ok. 30 cech wejścia (impuls, świeca, odległości, wybicie zakresu,
    trend, zmienność, godzina, dzień, siła walut, ruch tej samej waluty na innych parach…): straty vs zyski, ćwiartki.
  * RAZEM — sygnał „wieloparowy”: w tej samej świecy sygnał Powrót daje także inna para z tą samą walutą (ruch całej
    waluty, który zawraca naraz). Porównanie z sygnałami samotnymi — na transakcjach i na zdarzeniach (transakcje w tej
    samej świecy ze wspólną walutą = jedno zdarzenie, bo są ze sobą powiązane), w każdym roku osobno, test permutacyjny.
  * WARIANTY — wyjście przy unieważnieniu (zamknięcie nad szczytem, nowy impuls), dokładanie przy ruchu przeciw,
    wejście zleceniem limit nad otwarciem, 2 pozycje na parę, luźniejsze / ostrzejsze wejście, tylko „razem”.
  * RACHUNEK — warianty wielkości pozycji przy tym samym ryzyku (1000 $, 1:30, depozyt 10–60%): zysk / obsunięcie;
    największe obsunięcie — skąd się bierze; limit pozycji na walutę.
  * DOUBLEPROOF (--double-proof) — czy efekt „razem” i warianty v3 powtarzają się na 10 parach fx1h_double_proof
    (warunki ustalone przed testem; otwarcia w data/fxpowrot3/doubleproof.jsonl).

    python -m ia4.fxpowrot3                  # kilka minut → ~/Desktop/IA4/FX-POWROT-V3.xlsx
    python -m ia4.fxpowrot3 --double-proof   # + sprawdzian na 10 nowych parach (otwarcie zapisane)
    python -m ia4.fxpowrot3 --selftest       # „WYNIK: OK”
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numba as nb
import numpy as np
import pandas as pd

from . import __version__, config
from . import fxpowrot as fp
from . import fxpowrot2 as F2
from . import fxshort as fs
from .fxshort import PAIRS

OUT_DIR = config.RESEARCH_DIR / 'data' / 'fxpowrot3'
GRANICA = pd.Timestamp('2025-10-15')
CUR = ['EUR', 'USD', 'JPY', 'GBP', 'AUD', 'CAD', 'CHF', 'NZD']
DP_CRIT = dict(min_n=30, t=2.0)          # warunek doubleProof dla v3 „razem” (ustalony przed testem, 21.10.2026)


def share(a, b):
    return a[:3] in b or a[3:] in b


# ---------------------------------------------------------------- zdarzenia z parametrami i symulacja wariantów

def events(R, k=2.0, W=3, hours=(7, 16)):
    out = []
    for p in R.pairs:
        F = R.F[p]
        J, B, P, S0 = fp.gen_trades(F['o'], F['h'], F['l'], F['c'], F['atr'], F['run1'], k, 1, 0, 1, W, F['ema10'], F['valid'], fs.WARMUP)
        A = F['atr'][J]
        m = (F['hour'][J] >= hours[0]) & (F['hour'][J] <= hours[1])
        out.append(pd.DataFrame(dict(para=p, j=J[m], B=B[m], P=P[m], A=A[m], s0=S0[m], t=R.t[J[m]])))
    return pd.concat(out, ignore_index=True)


def mark_together(E, others=None):
    """razem = w tej samej świecy (ten sam czas) sygnał na innej parze z tą samą walutą (others — dodatkowe zdarzenia, np. z drugiej grupy par)."""
    allE = E if others is None else pd.concat([E[['para', 't']], others[['para', 't']]])
    by = allE.groupby('t').para.apply(list).to_dict()
    E = E.copy()
    E['grupa'] = [sum(share(p, q) for q in by.get(t, []) if q != p) for p, t in zip(E.para, E.t)]
    E['razem'] = E.grupa >= 1
    return E


@nb.njit(cache=True)
def sim1(o, h, l, c, run, J, B, P, A, sp, f, H, mintp, inv_close, inv_imp, add_at, add_max, lim_x):
    """Short po open (albo limit open + lim_x·ATR, tylko w świecy wejścia). Wyjście przy unieważnieniu (inv_close: close > szczyt
    + x ATR; inv_imp: nowy impuls), dokładanie jednostek co add_at ATR (najwyżej add_max). Wynik % na jednostkę bazową."""
    n = o.size; nt = J.size
    res = np.full(nt, np.nan); nb_ = np.zeros(nt, np.int64); why = np.full(nt, -1, np.int64); units = np.ones(nt)
    for t in range(nt):
        e0 = J[t] + 1
        if e0 + H > n:
            continue
        TP = P[t] - f * (P[t] - B[t]); a = A[t]
        en = o[e0]
        if lim_x > 0:
            if h[e0] < en + lim_x * a:
                continue
            en = en + lim_x * a
        if en - TP < mintp * sp or en - TP < 0.1 * a:
            continue
        u = 1.0; avg = en; added = 0; ex = np.nan; w = -1; k = 0
        for j in range(e0, e0 + H):
            k = j - e0 + 1
            if (j > e0 and o[j] <= TP) or l[j] <= TP:
                ex = TP; w = 0; break
            while add_at > 0 and added < add_max and h[j] >= en + add_at * a * (added + 1):
                avg = (avg * u + en + add_at * a * (added + 1)) / (u + 1); u += 1; added += 1
            if inv_close > 0 and c[j] > P[t] + inv_close * a:
                ex = c[j]; w = 2; break
            if inv_imp and j > e0 and run[j] >= 2.0:
                ex = c[j]; w = 3; break
            if k == H:
                ex = c[j]; w = 1
        res[t] = u * (avg - ex) / avg * 100.0 - u * sp / avg * 100.0
        nb_[t] = k; why[t] = w; units[t] = u
    return res, nb_, why, units


def simulate(R, E, f=0.5, H=60, mintp=1.0, inv_close=0.0, inv_imp=False, add_at=0.0, add_max=0, lim_x=0.0, maxpos=1, spread=None):
    parts = []
    for p in R.pairs:
        q = E[E.para == p]
        if not len(q):
            continue
        F = R.F[p]
        r, x, w, u = sim1(F['o'], F['h'], F['l'], F['c'], np.nan_to_num(F['run1']), q.j.values.astype(np.int64), q.B.values, q.P.values,
                          q.A.values, R.spread[p] * F2.pip_of(p), f, H, mintp, inv_close, inv_imp, add_at, add_max, lim_x)
        d = q.assign(wynik=r, swiece=x, powod=w, jedn=u)
        d = d[~np.isnan(d.wynik)]
        keep = np.zeros(len(d), bool); ends = []
        for i, (jj, xx) in enumerate(zip(d.j.values, d.swiece.values)):
            ends = [e for e in ends if e >= jj]
            if len(ends) < maxpos:
                keep[i] = True; ends.append(jj + xx)
        parts.append(d[keep])
    if not parts:
        return pd.DataFrame(columns=list(E.columns) + ['wynik', 'swiece', 'powod', 'jedn', 'okres'])
    D = pd.concat(parts).sort_values(['j', 'para']).reset_index(drop=True)
    D['t'] = pd.to_datetime(R.t[D.j.values], unit='s'); D['okres'] = R.per[D.j.values] + 1
    return D


def stats(D, w=None, label=''):
    if not len(D):
        return dict(wariant=label, n=0)
    v = D.wynik.values * (1 if w is None else w)
    per = pd.Series(v).groupby(D.okres.values).sum().reindex(range(1, 21), fill_value=0)
    y1 = (pd.to_datetime(D.t) < GRANICA).values
    sd = v.std(ddof=1) if len(v) > 1 else 0
    return dict(wariant=label, n=len(v), srednia=v.mean(), suma=v.sum(), t=v.mean() / sd * np.sqrt(len(v)) if sd > 0 else 0, trafne=(D.wynik.values > 0).mean(),
                najgorsza=v.min(), stratne=int((D.wynik.values <= 0).sum()), okresy_stratne=int((per < 0).sum()), rok1=v[y1].sum(), rok2=v[~y1].sum(),
                sr_rok1=v[y1].mean() if y1.any() else np.nan, sr_rok2=v[~y1].mean() if (~y1).any() else np.nan)


# ---------------------------------------------------------------- cechy stratnych

def strength(R):
    n = R.n; S = {c: np.zeros(n) for c in CUR}; cnt = {c: np.zeros(n) for c in CUR}
    for p in R.pairs:
        r = np.nan_to_num(R.F[p]['run1']); b, q = p[:3], p[3:]
        S[b] += r; cnt[b] += 1; S[q] -= r; cnt[q] += 1
    return {c: S[c] / np.maximum(cnt[c], 1) for c in CUR}


FEATS = [('czekanie', 'świece od impulsu do sygnału'), ('do_bazy', 'wejście − baza (ATR)'), ('cel_atr', 'odległość do TP (ATR)'),
         ('zakres', 'szczyt − baza (ATR)'), ('impuls', 'świeca impulsu (ATR)'), ('knot_impulsu', 'górny knot impulsu (część zakresu)'),
         ('czerwona', 'czerwona świeca sygnału (ATR)'), ('od_szczytu', 'szczyt − wejście (ATR)'), ('nowy_szczyt120', 'impuls ponad szczyt 120 świec (ATR)'),
         ('nowy_szczyt480', 'impuls ponad szczyt 480 świec (ATR)'), ('ruch24', 'ruch 24 świec przed (ATR)'), ('ruch120', 'ruch 120 świec przed (ATR)'),
         ('ruch480', 'ruch 480 świec przed (ATR)'), ('nachyl500', 'nachylenie SMA500'), ('zmiennosc', 'ATR100 / ATR500'), ('impulsy_120', 'impulsy w 120 świecach przed'),
         ('szerokie', 'inne pary z ruchem ≥ 1,5 ATR w świecy impulsu'), ('inne_kwotowana', 'waluta kwotowana na innych parach (ATR)'),
         ('inne_bazowa', 'waluta bazowa na innych parach (ATR)'), ('godz_impulsu', 'godzina impulsu (UTC)'), ('dzien', 'dzień tygodnia'),
         ('spread_atr', 'spread / ATR'), ('grupa', 'inne pary z tą walutą z sygnałem w tej świecy')]


def features(R, D):
    S = strength(R)
    run_all = np.vstack([np.nan_to_num(R.F[p]['run1']) for p in R.pairs])
    rows = []
    for r in D.itertuples():
        p = r.para; F = R.F[p]; j = int(r.j); s0 = int(r.s0); e0 = j + 1; A = r.A
        o, h, l, c = F['o'], F['h'], F['l'], F['c']
        en = o[e0]; rng = h[s0] - l[s0]; b, q = p[:3], p[3:]

        def cur_move(cur):
            v = [(1 if pp.startswith(cur) else -1) * run_all[k, s0] for k, pp in enumerate(R.pairs) if pp != p and cur in pp]
            return float(np.mean(v)) if v else 0.0
        hi = lambda N: (h[s0] - h[max(0, s0 - N):s0].max()) / A
        rows.append(dict(impuls=F['run1'][s0], knot_impulsu=(h[s0] - c[s0]) / rng if rng > 0 else 0.0, czekanie=j - s0,
                         do_bazy=(en - r.B) / A, od_szczytu=(r.P - en) / A, zakres=(r.P - r.B) / A, cel_atr=(en - (r.P - 0.5 * (r.P - r.B))) / A,
                         nowy_szczyt120=hi(120), nowy_szczyt480=hi(480), ruch24=(c[s0 - 1] - c[max(0, s0 - 25)]) / A,
                         ruch120=(c[s0 - 1] - c[max(0, s0 - 121)]) / A, ruch480=(c[s0 - 1] - c[max(0, s0 - 481)]) / A,
                         nachyl500=F['slope500'][j], zmiennosc=F['atr'][j] / F['atr500'][j], impulsy_120=int((F['run1'][max(0, s0 - 120):s0] >= 2.0).sum()),
                         szerokie=int((np.abs(np.delete(run_all[:, s0], R.pairs.index(p))) >= 1.5).sum()), inne_kwotowana=cur_move(q), inne_bazowa=cur_move(b),
                         godz_impulsu=int(F['hour'][s0]), dzien=int(pd.Timestamp(int(R.t[s0]), unit='s').dayofweek), czerwona=(o[j] - c[j]) / A,
                         spread_atr=R.spread[p] * F2.pip_of(p) / A))
    X = pd.concat([D.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    X['strata'] = X.wynik <= 0
    X['rok'] = np.where(pd.to_datetime(X.t) < GRANICA, 1, 2)
    return X


def feature_table(X):
    from scipy.stats import mannwhitneyu
    rows = []
    for f, opis in FEATS:
        a, b = X.loc[X.strata, f], X.loc[~X.strata, f]
        p = mannwhitneyu(a, b).pvalue if len(a) and len(b) else np.nan
        q = pd.qcut(X[f].rank(method='first'), 4, labels=False)
        g = X.groupby(q).agg(sr=('wynik', 'mean'), st=('strata', 'sum'))
        rows.append(dict(cecha=opis, strat_med=a.median(), zysk_med=b.median(), p=p, **{f'q{k + 1}': g.sr.iloc[k] for k in range(4)},
                         **{f's{k + 1}': int(g.st.iloc[k]) for k in range(4)}))
    return pd.DataFrame(rows).sort_values('p').reset_index(drop=True)


# ---------------------------------------------------------------- zdarzenia walutowe (transakcje powiązane)

def event_ids(X):
    """Transakcje z tej samej świecy sygnału, połączone wspólną walutą → jedno zdarzenie."""
    ev = np.zeros(len(X), int); nid = 0
    for j, g in X.groupby('j'):
        idx = list(g.index); par = {i: i for i in idx}

        def fnd(a):
            while par[a] != a:
                a = par[a]
            return a
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                if share(X.at[idx[a], 'para'], X.at[idx[b], 'para']):
                    par[fnd(idx[a])] = fnd(idx[b])
        roots = {}
        for i in idx:
            r = fnd(i)
            if r not in roots:
                roots[r] = nid; nid += 1
            ev[X.index.get_loc(i)] = roots[r]
    return ev


def together_tables(X, seed=1):
    from scipy.stats import mannwhitneyu, ttest_ind
    T = []
    for nm, m in [('razem (inna para z tą walutą — sygnał w tej świecy)', X.razem), ('samotne', ~X.razem)]:
        for y in (0, 1, 2):
            mm = m & ((X.rok == y) if y else True)
            w = X.wynik[mm]
            T.append(dict(grupa=nm, rok='oba' if not y else str(y), n=len(w), srednia=w.mean(), suma=w.sum(), stratne=int((w <= 0).sum()),
                          najgorsza=w.min(), t=w.mean() / w.std() * np.sqrt(len(w)) if len(w) > 1 else np.nan))
    rng = np.random.default_rng(seed); w = X.wynik.values; g = X.razem.values; yr = X.rok.values
    d0 = w[g].mean() - w[~g].mean(); cnt = 0
    for _ in range(10000):
        gg = g.copy()
        for y in (1, 2):
            mm = yr == y; gg[mm] = rng.permutation(g[mm])
        cnt += (w[gg].mean() - w[~gg].mean()) >= d0
    X = X.copy(); X['zdarzenie'] = event_ids(X)
    G = X.groupby('zdarzenie').agg(n=('wynik', 'size'), sr=('wynik', 'mean'), suma=('wynik', 'sum'), razem=('razem', 'max'), rok=('rok', 'first'))
    a, b = G[G.n >= 2].sr, G[G.n == 1].sr
    ev = dict(roznica=d0, p_perm=cnt / 10000, zdarzen=len(G), wieloparowe=int((G.n >= 2).sum()), sr_wielo=a.mean(), sr_pojed=b.mean(),
              p_zdarzenia=ttest_ind(a, b, equal_var=False).pvalue if len(a) > 1 and len(b) > 1 else np.nan,
              p_mw=mannwhitneyu(a, b).pvalue if len(a) and len(b) else np.nan,
              t_zdarzenia_v2=G.suma.mean() / G.suma.std() * np.sqrt(len(G)),
              t_zdarzenia_razem=G[G.razem].suma.mean() / G[G.razem].suma.std() * np.sqrt(G.razem.sum()) if G.razem.sum() > 1 else np.nan)
    P = X.groupby([X.para, X.razem]).wynik.agg(['size', 'mean']).unstack(1)
    return pd.DataFrame(T), ev, P, X


# ---------------------------------------------------------------- rachunek (1000 $, 1:30)

def konto(R, D, f=0.20, lev=30.0, start=1000.0, mult=None, add=0.0, cap=99):
    """Jedna pozycja na parę, depozyt = f × mnożnik × saldo; add — dokładanie jednostki, gdy szczyt świecy ≥ wejście + add·ATR;
    cap — najwięcej otwartych pozycji z tą samą walutą bazową / kwotowaną po tej samej stronie."""
    mult = np.ones(len(D)) if mult is None else mult
    cash = start; open_ = {}; eq = np.full(R.n, np.nan); by = {}; skipped = 0; nadd = 0
    for k, r in enumerate(D.itertuples()):
        by.setdefault(int(r.j) + 1, []).append((r, mult[k]))
    for j in range(R.n):
        for r, mu in by.get(j, []):
            if r.para in open_ or mu <= 0:
                continue
            if sum(1 for p in open_ if p[:3] == r.para[:3]) >= cap or sum(1 for p in open_ if p[3:] == r.para[3:]) >= cap:
                skipped += 1; continue
            used = sum(sum(u[0] for u in q['u']) for q in open_.values()); m = min(f * mu * cash, cash - used)
            if m <= 0:
                continue
            F = R.F[r.para]; en = F['o'][j]; TP = r.P - 0.5 * (r.P - r.B)
            ex = TP if int(r.powod) == 0 else F['c'][j + int(r.swiece) - 1]
            open_[r.para] = dict(u=[(m, en)], j1=j + int(r.swiece) - 1, ex=ex, lvl=en + add * r.A, added=False, sp=R.spread[r.para] * F2.pip_of(r.para))
        for p, q in open_.items():
            if add > 0 and not q['added'] and j < q['j1'] and R.F[p]['h'][j] >= q['lvl']:
                used = sum(sum(u[0] for u in qq['u']) for qq in open_.values()); m = min(f * cash, cash - used)
                if m > 0:
                    q['u'].append((m, q['lvl'])); q['added'] = True; nadd += 1
        for p in list(open_):
            q = open_[p]
            if q['j1'] <= j:
                cash += sum(m * lev * ((e - q['ex']) / e - q['sp'] / e) for m, e in q['u']); del open_[p]
        eq[j] = cash + sum(sum(m * lev * (e - R.F[p]['c'][j]) / e for m, e in q['u']) for p, q in open_.items())
    cv = pd.Series(eq, index=pd.to_datetime(R.t, unit='s')).ffill().fillna(start)
    pk = cv.cummax(); dd = (pk - cv) / pk
    i = int(dd.values.argmax()); i0 = int(cv.values[:i + 1].argmax())
    return dict(koniec=float(cv.iloc[-1]), zysk_pct=float(cv.iloc[-1] / start * 100 - 100), obs=float(dd.max() * 100), szczyt=cv.index[i0], dolek=cv.index[i],
                pominiete=skipped, dolozone=nadd), cv.resample('D').last().dropna()


# ---------------------------------------------------------------- całość

def compute(R, log=print, Rdp=None) -> dict:
    t0 = time.time()
    O = dict(od=pd.Timestamp(int(R.t[0]), unit='s'), do=pd.Timestamp(int(R.t[-1]), unit='s'), swiec=R.n)
    E = mark_together(events(R))
    D = simulate(R, E)
    log(f'Powrót.v2: {len(D)} transakcji, stratnych {int((D.wynik <= 0).sum())}')
    X = features(R, D)
    O['X'] = X
    O['cechy'] = feature_table(X)
    O['razem_tab'], O['razem_ev'], O['razem_pary'], X2 = together_tables(X)
    O['X'] = X2
    log(f"Razem: {O['razem_ev']['sr_wielo']:+.3f}% na transakcję w zdarzeniu wieloparowym wobec {O['razem_ev']['sr_pojed']:+.3f}% (p permutacji "
        f"{O['razem_ev']['p_perm']:.4f}, zdarzenia p {O['razem_ev']['p_zdarzenia']:.4f})")
    # warianty
    V = [stats(D, label='v2 (obecna)')]
    V += [stats(simulate(R, E, inv_close=x), label=f'wyjście, gdy zamknięcie > szczyt + {x:g} ATR'.replace('.', ',')) for x in (0.5, 1.0, 2.0, 3.0)]
    V.append(stats(simulate(R, E, inv_imp=True), label='wyjście po nowym impulsie w pozycji'))
    for a_ in (1.0, 2.0, 3.0):
        Dd = simulate(R, E, add_at=a_, add_max=1)
        V.append(dict(stats(Dd, label=f'dokładanie 1 jednostki przy + {a_:g} ATR'.replace('.', ',')), jednostki=Dd.jedn.mean()))
    for lx in (0.1, 0.2, 0.3):
        V.append(stats(simulate(R, E, lim_x=lx), label=f'wejście zleceniem limit: open + {lx:g} ATR (ta sama świeca)'.replace('.', ',')))
    V.append(stats(simulate(R, E, maxpos=2), label='do 2 pozycji na parę'))
    V.append(stats(simulate(R, E, mintp=2.0), label='TP ≥ 2 × spread'))
    for k, W, hrs, nm in [(2.0, 1, (7, 16), 'sygnał tylko na 1. świecy po impulsie'), (2.0, 2, (7, 16), 'sygnał do 2. świecy po impulsie'),
                          (1.75, 3, (7, 16), 'impuls ≥ 1,75 ATR'), (2.0, 3, (6, 18), 'godziny 6–18 UTC'), (2.0, 3, (0, 23), 'wszystkie godziny')]:
        V.append(stats(simulate(R, mark_together(events(R, k, W, hrs))), label=nm))
    O['v3_razem'] = simulate(R, E[E.razem])
    V.append(stats(O['v3_razem'], label='v3: tylko sygnały „razem”'))
    V.append(stats(simulate(R, E[~E.razem]), label='tylko sygnały samotne'))
    O['warianty'] = pd.DataFrame(V)
    # rachunek przy tym samym ryzyku
    raz = X2.razem.values; nev = X2.groupby('zdarzenie').para.transform('size').values
    Xs = X2.sort_values(['j', 'para']).reset_index(drop=True)
    raz_s = Xs.razem.values; nev_s = Xs.groupby('zdarzenie').para.transform('size').values
    acc = []
    variants = [('v2 (obecna)', None, 0.0, 99), ('v3: tylko „razem”', np.where(raz_s, 1.0, 0.0), 0.0, 99),
                ('v3: tylko „razem”, stawka dzielona na zdarzenie', np.where(raz_s, 1.0 / nev_s, 0.0), 0.0, 99),
                ('samotne ×0,5, razem ×1,5', np.where(raz_s, 1.5, 0.5), 0.0, 99), ('v2 + dokładanie przy + 2 ATR', None, 2.0, 99),
                ('v2 + najwyżej 2 pozycje na walutę po tej samej stronie', None, 0.0, 2), ('v2 + najwyżej 1 pozycja na walutę', None, 0.0, 1)]
    O['krzywe'] = {}
    for nm, mu, add, cap in variants:
        for f in (0.10, 0.20, 0.30, 0.45):
            st, cv = konto(R, Xs, f=f, mult=mu, add=add, cap=cap)
            acc.append(dict(wariant=nm, f=f, **st, zysk_do_obs=st['zysk_pct'] / st['obs'] if st['obs'] > 0 else np.nan))
            if abs(f - 0.20) < 1e-9:
                O['krzywe'][nm] = cv
    O['rachunek'] = pd.DataFrame(acc)
    st, _ = konto(R, Xs, f=0.20)
    O['obsuniecie'] = st
    w = Xs[(pd.to_datetime(R.t[(Xs.j + Xs.swiece).clip(upper=R.n - 1).values], unit='s') >= st['szczyt']) & (pd.to_datetime(Xs.t) <= st['dolek'])]
    O['obs_transakcje'] = w
    if Rdp is not None:
        O['dp'] = double_proof(R, Rdp, log)
    O['czas_min'] = (time.time() - t0) / 60
    return O


def double_proof(R, Rdp, log=print):
    """Efekt „razem” i v3 na 10 parach fx1h_double_proof. Partnerzy „razem” — sygnały na wszystkich 20 parach (ten sam czas)."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    logp = OUT_DIR / 'doubleproof.jsonl'
    n_old = sum(1 for _ in logp.open(encoding='utf-8')) if logp.exists() else 0
    with logp.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(dict(otwarcie=n_old + 1, czas=datetime.now(timezone.utc).isoformat(timespec='seconds'), wersja=__version__,
                                 do=str(pd.Timestamp(int(Rdp.t[-1]), unit='s'))), ensure_ascii=False) + '\n')
    Eb = events(R); Ed = mark_together(events(Rdp), others=Eb)
    D = simulate(Rdp, Ed)
    D['rok'] = np.where(pd.to_datetime(D.t) < GRANICA, 1, 2)
    a, b = D[D.razem], D[~D.razem]
    s_all, s_r, s_s = stats(D, label='v2 na nowych parach'), stats(a, label='razem'), stats(b, label='samotne')
    v3 = simulate(Rdp, Ed[Ed.razem]); s3 = stats(v3, label='v3: tylko „razem”')
    ok_eff = len(a) >= 15 and len(b) >= 15 and a.wynik.mean() > b.wynik.mean()
    ok_v3 = s3['n'] >= DP_CRIT['min_n'] and s3['srednia'] > 0 and s3['t'] >= DP_CRIT['t']
    log(f"doubleProof v3 (otwarcie nr {n_old + 1}): razem {a.wynik.mean():+.3f}% (n {len(a)}) vs samotne {b.wynik.mean():+.3f}% (n {len(b)}) → "
        f"{'efekt potwierdzony' if ok_eff else 'efekt NIE potwierdzony'}; v3: {s3['n']} transakcji, t {s3.get('t', 0):.1f} → {'ZALICZONY' if ok_v3 else 'NIE zaliczony'}")
    return dict(otwarcie=n_old + 1, tab=pd.DataFrame([s_all, s_r, s_s, s3]), ok_eff=ok_eff, ok_v3=ok_v3, D=D)


# ---------------------------------------------------------------- Excel

def write_xlsx(O: dict, path: Path, wnioski=None) -> Path:
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
    PCT = '0.0%'; PCT3 = '0.000%'; USD = '#,##0 [$$-409]'; DT = 'yyyy-mm-dd hh:mm'; DD = 'yyyy-mm-dd'
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
        ws.row_dimensions[r].height = 40

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

    SC = [('n', 'Transakcje', '0'), ('srednia', 'Średnio %', PCT3), ('suma', 'Suma %', PCT), ('t', 't', '0.0'), ('trafne', 'Trafne', PCT),
          ('najgorsza', 'Najgorsza %', PCT3), ('stratne', 'Stratne', '0'), ('okresy_stratne', 'Okresy stratne / 20', '0'), ('rok1', 'Rok 1 %', PCT),
          ('rok2', 'Rok 2 %', PCT), ('sr_rok1', 'Rok 1: średnio', PCT3), ('sr_rok2', 'Rok 2: średnio', PCT3)]

    def srow(ws, r, c, s, fill=None):
        for k, (key, _, fm) in enumerate(SC):
            v = s.get(key)
            if v is not None and fm in (PCT, PCT3) and key != 'trafne' and isinstance(v, (int, float, np.floating)) and np.isfinite(v): v = v / 100
            put(ws, r, c + k, v, fmt=fm, fill=fill)

    # PODSUMOWANIE
    ws = sheet('PODSUMOWANIE', first=True)
    ws.column_dimensions['A'].width = 120
    ws['A1'] = 'FX-POWRÓT v3 — skąd straty Powrót.v2 i co może je ograniczyć'; ws['A1'].font = fT
    ws['A2'] = (f"IA4 {__version__} · badanie informacyjne · 10 par 1h: {O['od']:%Y-%m-%d} – {O['do']:%Y-%m-%d} · policzono {pd.Timestamp.now():%Y-%m-%d %H:%M}")
    ws['A2'].font = fS
    put(ws, 4, 1, 'WNIOSKI' if wnioski else 'ARKUSZE', fH, fill=HDR)
    txt = wnioski or ['STRATNE, CECHY — co wyróżnia stratne transakcje.', 'RAZEM — sygnał wieloparowy vs samotny.', 'WARIANTY — pomysły na ulepszenie (na transakcję).',
                      'RACHUNEK — warianty przy tym samym ryzyku (najważniejsze).', 'OBSUNIĘCIE — skąd największy spadek salda.']
    for k, s_ in enumerate(txt):
        x = ws.cell(5 + k, 1, s_); x.font = fN; x.alignment = WR; ws.row_dimensions[5 + k].height = 58 if wnioski else 16

    X = O['X']
    ws = sheet('STRATNE')
    ws['A1'] = f"STRATNE — {int(X.strata.sum())} transakcji v2 z wynikiem ≤ 0 (wszystkie: wyjście po limicie 60 świec albo TP o wartości spreadu)"; ws['A1'].font = fT
    cols = [('para', 'Para', None, 9), ('t', 'Sygnał (UTC)', DT, 16), ('wynik', 'Wynik %', PCT3, 9), ('swiece', 'Świec', '0', 6), ('razem', 'Razem (1) / samotny (0)', '0', 10),
            ('grupa', 'Inne pary z tą walutą — sygnał', '0', 10), ('czekanie', 'Czekanie (św.)', '0', 8), ('do_bazy', 'Wejście − baza (ATR)', '0.00', 9),
            ('cel_atr', 'Do TP (ATR)', '0.00', 8), ('impuls', 'Impuls (ATR)', '0.00', 8), ('nowy_szczyt120', 'Ponad szczyt 120 (ATR)', '0.0', 9),
            ('ruch120', 'Ruch 120 przed (ATR)', '0.0', 9), ('szerokie', 'Pary z ruchem ≥ 1,5 ATR', '0', 9), ('godz_impulsu', 'Godz. impulsu', '0', 7)]
    hdr(ws, 3, 1, [c[1] for c in cols], [c[3] for c in cols])
    for k, v in enumerate(X[X.strata].sort_values('wynik').itertuples()):
        for c, (key, _, fm, _) in enumerate(cols):
            val = getattr(v, key)
            if key == 'wynik': val = val / 100
            put(ws, 4 + k, 1 + c, val, fmt=fm, fill=(GOOD if (key == 'razem' and val) else None))
    ws.freeze_panes = 'A4'

    ws = sheet('CECHY')
    ws['A1'] = 'CECHY — stratne vs zyskowne (od najmniejszego p) i średni wynik w ćwiartkach cechy'; ws['A1'].font = fT
    note(ws, 2, 1, 'p — test Manna-Whitneya (stratne vs zyskowne); przy ok. 20 cechach p < 0,05 zdarza się przypadkiem. Ćwiartki: Q1 — najmniejsze wartości. „Stratne Qn” — ile strat w ćwiartce.', 14, 30)
    hdr(ws, 4, 1, ['Cecha', 'Mediana — stratne', 'Mediana — zyskowne', 'p', 'Q1: średnio %', 'Q2', 'Q3', 'Q4', 'Stratne Q1', 'Q2', 'Q3', 'Q4'],
        [46, 11, 11, 8, 10, 10, 10, 10, 8, 8, 8, 8])
    for k, v in enumerate(O['cechy'].itertuples()):
        for c, (val, fm) in enumerate([(v.cecha, None), (v.strat_med, '0.00'), (v.zysk_med, '0.00'), (v.p, '0.000'), (v.q1 / 100, PCT3), (v.q2 / 100, PCT3),
                                       (v.q3 / 100, PCT3), (v.q4 / 100, PCT3), (v.s1, '0'), (v.s2, '0'), (v.s3, '0'), (v.s4, '0')]):
            put(ws, 5 + k, 1 + c, val, fmt=fm, fill=SEL if (c == 3 and v.p < 0.05) else None)

    ws = sheet('RAZEM')
    ev = O['razem_ev']
    ws['A1'] = 'RAZEM — sygnał wieloparowy (cała waluta zawraca naraz) vs samotny (jedna para)'; ws['A1'].font = fT
    note(ws, 2, 1, '„Razem” = w tej samej świecy sygnał Powrót daje też inna para z tą samą walutą (np. EURUSD i GBPUSD — dolar). Sprawdzane bez podglądania: tylko sygnały '
                   'z tej samej świecy, znane w chwili wejścia. Transakcje jednego zdarzenia są ze sobą powiązane — dlatego też test na zdarzeniach.', 10, 44)
    hdr(ws, 4, 1, ['Grupa', 'Rok', 'Transakcje', 'Średnio %', 'Suma %', 'Stratne', 'Najgorsza %', 't'], [52, 7, 11, 11, 10, 9, 11, 8])
    for k, v in enumerate(O['razem_tab'].itertuples()):
        for c, (val, fm) in enumerate([(v.grupa, None), (v.rok, None), (v.n, '0'), (v.srednia / 100, PCT3), (v.suma / 100, PCT), (v.stratne, '0'),
                                       (v.najgorsza / 100, PCT3), (v.t, '0.0')]):
            put(ws, 5 + k, 1 + c, val, fmt=fm, fill=GOOD if v.grupa.startswith('razem') else None)
    r = 13
    for k, (lab, val, fm) in enumerate([('Różnica średnich (razem − samotne), pkt %', ev['roznica'], '0.000'), ('p — permutacja w obrębie roku', ev['p_perm'], '0.0000'),
                                        ('Zdarzeń (transakcje powiązane walutą = jedno)', ev['zdarzen'], '0'), ('…w tym wieloparowych', ev['wieloparowe'], '0'),
                                        ('Średnio na transakcję: zdarzenie wieloparowe', ev['sr_wielo'], '0.000'), ('Średnio: zdarzenie jednej pary', ev['sr_pojed'], '0.000'),
                                        ('p — test t na zdarzeniach', ev['p_zdarzenia'], '0.0000'), ('p — Mann-Whitney na zdarzeniach', ev['p_mw'], '0.0000'),
                                        ('t na zdarzeniach: v2', ev['t_zdarzenia_v2'], '0.0'), ('t na zdarzeniach: tylko razem', ev['t_zdarzenia_razem'], '0.0')]):
        put(ws, r + k, 1, lab, fB, fill=GRY); put(ws, r + k, 2, val, fmt=fm)
    r += 12
    hdr(ws, r, 1, ['Para', 'Samotne: n', 'Samotne: średnio %', 'Razem: n', 'Razem: średnio %'], [52, 11, 13, 11, 13])
    P = O['razem_pary']
    for k, (p, row) in enumerate(P.iterrows()):
        vals = [(p, None), (row[('size', False)], '0'), (row[('mean', False)] / 100, PCT3), (row[('size', True)], '0'), (row[('mean', True)] / 100, PCT3)]
        for c, (val, fm) in enumerate(vals):
            put(ws, r + 1 + k, 1 + c, val, fmt=fm)

    ws = sheet('WARIANTY')
    ws['A1'] = 'WARIANTY — pomysły na ulepszenie (wynik na transakcję, bez dźwigni, w próbie)'; ws['A1'].font = fT
    note(ws, 2, 1, 'Zielone t = wyższe niż v2. Uwaga: lepszy wynik na transakcję nie musi znaczyć lepszego rachunku — patrz RACHUNEK. „Dokładanie”: wynik na jednostkę bazową '
                   '(z dołożoną jednostką transakcja jest większa).', 14, 30)
    hdr(ws, 4, 1, ['Wariant'] + [x[1] for x in SC] + ['Średnio jednostek'], [52] + [10] * (len(SC) + 1))
    W = O['warianty']; t0_ = W.t.iloc[0]
    for k, v in enumerate(W.to_dict('records')):
        put(ws, 5 + k, 1, v['wariant'], fB if k == 0 else fN, fill=SEL if k == 0 else None)
        srow(ws, 5 + k, 2, v)
        put(ws, 5 + k, 2 + len(SC), v.get('jednostki'), fmt='0.00')
        ws.cell(5 + k, 5).fill = GOOD if (v.get('t') or 0) > t0_ + 1e-9 else PatternFill()

    ws = sheet('RACHUNEK')
    ws['A1'] = 'RACHUNEK — 1000 $, 1:30, depozyt 10–45% salda na pozycję: zysk wobec największego obsunięcia'; ws['A1'].font = fT
    note(ws, 2, 1, 'Porównuj warianty przy podobnym obsunięciu (kolumna „Obsunięcie”) — wtedy widać, czy zmiana daje więcej zysku za to samo ryzyko. Ostatnia kolumna: zysk % / obsunięcie %.', 10, 30)
    hdr(ws, 4, 1, ['Wariant', 'Depozyt', 'Saldo końcowe', 'Zysk', 'Obsunięcie', 'Zysk / obsunięcie', 'Najgłębiej', 'Pominięte', 'Dołożone'], [52, 9, 12, 10, 11, 11, 17, 10, 10])
    best = O['rachunek'].groupby('f').zysk_do_obs.transform('max')
    for k, v in enumerate(O['rachunek'].itertuples()):
        for c, (val, fm) in enumerate([(v.wariant, None), (v.f, '0%'), (v.koniec, USD), (v.zysk_pct / 100, PCT), (-v.obs / 100, PCT), (v.zysk_do_obs, '0.0'),
                                       (v.dolek, DT), (v.pominiete, '0'), (v.dolozone, '0')]):
            put(ws, 5 + k, 1 + c, val, fmt=fm, fill=GOOD if (c == 5 and abs(v.zysk_do_obs - best.iloc[k]) < 1e-9) else None)
    cv = pd.DataFrame(O['krzywe'])
    r0 = 7 + len(O['rachunek'])
    hdr(ws, r0, 1, ['Dzień'] + list(cv.columns))
    for k, (d, row) in enumerate(cv.iterrows()):
        put(ws, r0 + 1 + k, 1, d, fmt=DD)
        for q, c_ in enumerate(cv.columns): put(ws, r0 + 1 + k, 2 + q, round(float(row[c_]), 2), fmt=USD)
    ch = LineChart(); ch.title = 'Saldo przy depozycie 20%'; ch.height = 11; ch.width = 26
    ch.y_axis.crossAx = 500; ch.x_axis = DateAxis(crossAx=100); ch.x_axis.number_format = 'yyyy-mm'; ch.x_axis.majorTimeUnit = 'months'
    ch.x_axis.delete = False; ch.y_axis.delete = False
    ch.add_data(Reference(ws, min_col=2, max_col=1 + len(cv.columns), min_row=r0, max_row=r0 + len(cv)), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=r0 + 1, max_row=r0 + len(cv))); ch.legend.position = 'b'
    ws.add_chart(ch, 'K4')

    ws = sheet('OBSUNIĘCIE')
    st = O['obsuniecie']
    ws['A1'] = f"OBSUNIĘCIE — największy spadek salda v2 (depozyt 20%): {st['obs']:.1f}% od {st['szczyt']:%Y-%m-%d %H:%M} do {st['dolek']:%Y-%m-%d %H:%M} UTC"; ws['A1'].font = fT
    note(ws, 2, 1, 'Transakcje otwarte w tym czasie. Kilka pozycji na jedną walutę naraz = jeden zakład na walutę; spadek liczony po cenie na koniec każdej godziny (pozycje mogły potem odrobić).', 10, 30)
    hdr(ws, 4, 1, ['Para', 'Sygnał (UTC)', 'Wynik końcowy %', 'Świec', 'Razem'], [10, 17, 13, 8, 8])
    for k, v in enumerate(O['obs_transakcje'].itertuples()):
        for c, (val, fm) in enumerate([(v.para, None), (v.t, DT), (v.wynik / 100, PCT3), (v.swiece, '0'), (int(v.razem), '0')]):
            put(ws, 5 + k, 1 + c, val, fmt=fm)

    if O.get('dp'):
        dp = O['dp']
        ws = sheet('DOUBLEPROOF')
        ws['A1'] = f"DOUBLEPROOF v3 — 10 par fx1h_double_proof (otwarcie nr {dp['otwarcie']})"; ws['A1'].font = fT
        note(ws, 2, 1, f"Warunki ustalone przed testem (21.10.2026): efekt — średnio razem > samotne (każda grupa ≥ 15 transakcji); v3 „razem” — ≥ {DP_CRIT['min_n']} transakcji, "
                       f"średnia > 0, t ≥ {DP_CRIT['t']:g}. Partnerzy „razem” — sygnały na wszystkich 20 parach.", 12, 30)
        put(ws, 4, 1, ('EFEKT POTWIERDZONY' if dp['ok_eff'] else 'EFEKT NIE POTWIERDZONY') + ' · ' + ('v3 ZALICZONA' if dp['ok_v3'] else 'v3 NIE ZALICZONA'), fB,
            fill=GOOD if dp['ok_eff'] and dp['ok_v3'] else BAD)
        hdr(ws, 6, 1, ['Grupa'] + [x[1] for x in SC], [40] + [10] * len(SC))
        for k, v in enumerate(dp['tab'].to_dict('records')):
            put(ws, 7 + k, 1, v['wariant'], fB); srow(ws, 7 + k, 2, v)
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


# ---------------------------------------------------------------- uruchomienie

def run(no_sync=False, out=None, double=False, log=print, keep=None, wnioski=None) -> Path:
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
    path = write_xlsx(O, out or (config.RESEARCH_DIR.parent / 'FX-POWROT-V3.xlsx'), wnioski=wnioski)
    log(f'Zapisano: {path}  ({(time.time() - t0) / 60:.1f} min)')
    return path


def selftest() -> bool:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  {'✓' if cond else '✗'} {name}")
        ok &= bool(cond)

    E = pd.DataFrame(dict(para=['EURUSD', 'GBPUSD', 'EURJPY', 'AUDNZD', 'USDCAD'], t=[100, 100, 100, 200, 300]))
    M = mark_together(E)
    check('razem: EURUSD i GBPUSD (USD) oraz EURJPY (EUR) w tej samej świecy; AUDNZD sam; USDCAD w innej świecy', list(M.razem) == [True, True, True, False, False])
    M2 = mark_together(E.iloc[3:], others=pd.DataFrame(dict(para=['NZDUSD'], t=[200])))
    check('razem z drugiej grupy par (AUDNZD + NZDUSD)', list(M2.razem) == [True, False])
    X = pd.DataFrame(dict(j=[5, 5, 5, 9], para=['EURUSD', 'GBPUSD', 'AUDNZD', 'EURUSD']))
    ev = event_ids(X)
    check('zdarzenia: EURUSD + GBPUSD jedno, AUDNZD osobno, inna świeca osobno', ev[0] == ev[1] and len({ev[0], ev[2], ev[3]}) == 3)
    n = 30
    o = np.full(n, 1.01); h = np.full(n, 1.011); l = np.full(n, 1.009); c = np.full(n, 1.01); run = np.zeros(n)
    h2 = h.copy(); h2[3] = 1.016; l2 = l.copy(); l2[6] = 1.004
    r, x, w, u = sim1(o, h2, l2, c, run, np.array([0]), np.array([0.98]), np.array([1.03]), np.array([0.002]), 0.0001, 0.5, 20, 1.0, 0.0, False, 2.0, 1, 0.0)
    avg = (1.01 + 1.014) / 2
    check('dokładanie przy + 2 ATR (1,014): 2 jednostki do TP 1,005', u[0] == 2 and abs(r[0] - 2 * ((avg - 1.005) / avg * 100 - 0.0001 / avg * 100)) < 1e-9)
    r, x, w, u = sim1(o, h, l2, c, run, np.array([0]), np.array([0.98]), np.array([1.03]), np.array([0.002]), 0.0001, 0.5, 20, 1.0, 0.0, False, 0.0, 0, 1.0)
    check('limit open + 1 ATR (1,012) — szczyt świecy wejścia 1,011 → brak transakcji', np.isnan(r[0]))
    r, x, w, u = sim1(o, h, l2, c, run, np.array([0]), np.array([0.98]), np.array([1.03]), np.array([0.002]), 0.0001, 0.5, 20, 1.0, 0.0, False, 0.0, 0, 0.25)
    check('limit open + 0,25 ATR (1,0105) dotknięty → wejście 1,0105, TP 1,005', abs(r[0] - ((1.0105 - 1.005) / 1.0105 * 100 - 0.0001 / 1.0105 * 100)) < 1e-9)
    print('\nWYNIK: OK' if ok else '\nWYNIK: BŁĄD')
    return ok


def main():
    ap = argparse.ArgumentParser(description='FX-POWRÓT v3 — analiza strat Powrót.v2 i ulepszeń')
    ap.add_argument('--bez-sync', action='store_true')
    ap.add_argument('--double-proof', action='store_true', help='+ sprawdzian na 10 parach fx1h_double_proof (otwarcie zapisane)')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    print(f'IA 4 {__version__} — FX-POWRÓT v3\n')
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    run(no_sync=a.bez_sync, double=a.double_proof)


if __name__ == '__main__':
    main()
