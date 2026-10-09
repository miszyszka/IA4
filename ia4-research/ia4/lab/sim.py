"""
IA 4 — symulacja transakcji (zasady: IA4_INSTRUKCJA.md, sekcja 8.6).
Wersja projektu: 1.21 (2026-10-09) — musi zgadzać się z IA4_INSTRUKCJA.md

Jeden przebieg liczy KAŻDĄ kombinację SL × TP naraz (domyślnie 1–10% × 1–10%).

Zasady pesymistyczne:
  • wejście: open świecy następnej po świecy sygnału,
  • w obrębie jednej świecy najpierw sprawdzany jest SL, potem TP,
  • luka przez SL na otwarciu → wyjście po cenie otwarcia (strata większa niż SL),
  • luka przez TP na otwarciu → wyjście po poziomie TP (bez premii za lukę),
  • FC (force close) wykryty na zamknięciu świecy f → wyjście po open świecy f+1,
  • limit czasu L świec → wyjście po close świecy e+L−1 (transakcja „nierozstrzygnięta”),
  • brak jakiegokolwiek wyjścia do końca danych → transakcja anulowana (nie liczona),
  • jedna pozycja naraz na instrument: sygnał w trakcie pozycji jest pomijany.

Kolejność zdarzeń w świecy j: [luka SL/TP na otwarciu] → [FC na otwarciu] →
[SL w trakcie] → [TP w trakcie] → [limit czasu na zamknięciu].
"""

from __future__ import annotations

import numpy as np
from numba import njit

# Kolumny statystyk w tablicy wyników [sl, tp, strefa, STAT]
N, WINS, GW, GL, NSL, NTP, NFC, NTIME, SUMRET, NCANCEL = range(10)
N_STATS = 10
N_ZONES = 5          # 0 = skarbiec, 1–4 = okresy grupy głównej

K_CANCEL, K_SL, K_TP, K_FC, K_TIME = 0, 1, 2, 3, 4
BIG = 1 << 60


@njit(cache=True)
def simulate(o, h, l, c, zone, seg_end_of, sig_t, fc_bar, direction,
             sl_pct, tp_pct, max_bars, rec_a, rec_b):
    """
    sig_t      — indeksy świec sygnału (rosnąco),
    fc_bar     — dla każdego sygnału świeca f, na której zamknięciu zachodzi FC, albo −1,
    direction  — +1 long, −1 short,
    max_bars   — limit czasu (0 = brak),
    rec_a/b    — która kombinacja (sl, tp) ma zwrócić listę transakcji (−1 = żadna).
    Zwraca: stats[n_sl, n_tp, 5, 10] oraz transakcje wybranej kombinacji.
    """
    ns = sig_t.size
    nsl = sl_pct.size
    ntp = tp_pct.size
    sl_bar = np.full((ns, nsl), BIG, dtype=np.int64)
    sl_px = np.zeros((ns, nsl))
    sl_gap = np.zeros((ns, nsl), dtype=np.bool_)
    tp_bar = np.full((ns, ntp), BIG, dtype=np.int64)
    tp_px = np.zeros((ns, ntp))
    tp_gap = np.zeros((ns, ntp), dtype=np.bool_)
    fx_arr = np.full(ns, BIG, dtype=np.int64)
    tb_arr = np.full(ns, BIG, dtype=np.int64)
    entry = np.zeros(ns)

    # --- krok 1: dla każdego sygnału pierwsze dotknięcie każdego poziomu SL i TP
    for i in range(ns):
        t = sig_t[i]
        e = t + 1
        end = seg_end_of[t] - 1           # ostatnia świeca tego instrumentu
        if e > end:
            continue
        p = o[e]
        entry[i] = p
        fx = BIG
        if fc_bar[i] >= 0 and fc_bar[i] + 1 <= end:
            fx = fc_bar[i] + 1
        fx_arr[i] = fx
        tb = BIG
        if max_bars > 0 and e + max_bars - 1 <= end:
            tb = e + max_bars - 1
        tb_arr[i] = tb
        last = min(end, fx, tb)
        left = nsl + ntp
        for j in range(e, last + 1):
            if j > e:                                   # luka na otwarciu
                for k in range(nsl):
                    if sl_bar[i, k] == BIG:
                        lev = p * (1.0 - direction * sl_pct[k] / 100.0)
                        if (direction > 0 and o[j] <= lev) or (direction < 0 and o[j] >= lev):
                            sl_bar[i, k] = j
                            sl_px[i, k] = o[j]
                            sl_gap[i, k] = True
                            left -= 1
                for k in range(ntp):
                    if tp_bar[i, k] == BIG:
                        lev = p * (1.0 + direction * tp_pct[k] / 100.0)
                        if (direction > 0 and o[j] >= lev) or (direction < 0 and o[j] <= lev):
                            tp_bar[i, k] = j
                            tp_px[i, k] = lev
                            tp_gap[i, k] = True
                            left -= 1
            if j == fx:                                 # FC na otwarciu — koniec
                break
            for k in range(nsl):                        # w trakcie świecy
                if sl_bar[i, k] == BIG:
                    lev = p * (1.0 - direction * sl_pct[k] / 100.0)
                    if (direction > 0 and l[j] <= lev) or (direction < 0 and h[j] >= lev):
                        sl_bar[i, k] = j
                        sl_px[i, k] = lev
                        left -= 1
            for k in range(ntp):
                if tp_bar[i, k] == BIG:
                    lev = p * (1.0 + direction * tp_pct[k] / 100.0)
                    if (direction > 0 and h[j] >= lev) or (direction < 0 and l[j] <= lev):
                        tp_bar[i, k] = j
                        tp_px[i, k] = lev
                        left -= 1
            if left == 0:
                break

    # --- krok 2: dla każdej kombinacji (sl, tp) po kolei, jedna pozycja naraz
    stats = np.zeros((nsl, ntp, 5, 10))
    rec_n = 0
    rec = np.zeros((ns, 6))            # t, e, wyjście, zwrot %, rodzaj, strefa
    for a in range(nsl):
        for b in range(ntp):
            busy_until = -1
            for i in range(ns):
                t = sig_t[i]
                e = t + 1
                if e > seg_end_of[t] - 1 or t < busy_until:
                    continue
                p = entry[i]
                # zdarzenie = (świeca, priorytet); wygrywa najwcześniejsze:
                # 0 luka SL/TP na otwarciu, 1 FC na otwarciu, 2 SL w trakcie,
                # 3 TP w trakcie, 4 limit czasu na zamknięciu
                best_bar = BIG
                best_pri = 9
                kind = K_CANCEL
                px = 0.0
                sb = sl_bar[i, a]
                if sb < BIG:
                    best_bar = sb
                    best_pri = 0 if sl_gap[i, a] else 2
                    kind = K_SL
                    px = sl_px[i, a]
                tpb = tp_bar[i, b]
                if tpb < BIG:
                    pri = 0 if tp_gap[i, b] else 3
                    if tpb < best_bar or (tpb == best_bar and pri < best_pri):
                        best_bar = tpb
                        best_pri = pri
                        kind = K_TP
                        px = tp_px[i, b]
                fx = fx_arr[i]
                if fx < BIG and (fx < best_bar or (fx == best_bar and 1 < best_pri)):
                    best_bar = fx
                    best_pri = 1
                    kind = K_FC
                    px = o[fx]
                tb = tb_arr[i]
                if tb < BIG and (tb < best_bar or (tb == best_bar and 4 < best_pri)):
                    best_bar = tb
                    best_pri = 4
                    kind = K_TIME
                    px = c[tb]
                z = zone[e]
                if kind == K_CANCEL:
                    stats[a, b, z, NCANCEL] += 1
                    busy_until = seg_end_of[t]
                    continue
                if direction > 0:
                    r = (px / p - 1.0) * 100.0
                else:
                    r = (p - px) / p * 100.0
                busy_until = best_bar
                stats[a, b, z, N] += 1
                stats[a, b, z, SUMRET] += r
                if r > 0:
                    stats[a, b, z, WINS] += 1
                    stats[a, b, z, GW] += r
                else:
                    stats[a, b, z, GL] -= r
                if kind == K_SL:
                    stats[a, b, z, NSL] += 1
                elif kind == K_TP:
                    stats[a, b, z, NTP] += 1
                elif kind == K_FC:
                    stats[a, b, z, NFC] += 1
                else:
                    stats[a, b, z, NTIME] += 1
                if a == rec_a and b == rec_b:
                    rec[rec_n, 0] = t
                    rec[rec_n, 1] = e
                    rec[rec_n, 2] = best_bar
                    rec[rec_n, 3] = r
                    rec[rec_n, 4] = kind
                    rec[rec_n, 5] = z
                    rec_n += 1
    return stats, rec[:rec_n]


def profit_factor(gw, gl):
    """PF = zyski / straty. Bez strat i z zyskiem → 99 (umowny sufit)."""
    gw = np.asarray(gw, float)
    gl = np.asarray(gl, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        pf = np.where(gl > 0, gw / np.where(gl > 0, gl, 1.0), np.where(gw > 0, 99.0, 0.0))
    return np.minimum(pf, 99.0)
