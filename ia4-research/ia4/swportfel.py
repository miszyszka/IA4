"""
IA 4 — portfel jednej strategii serii świec: po N świecach spadkowych long na N+1. sesji (instrukcja, sekcja 7a).
Wersja projektu: 1.46 (2026-10-17) — musi zgadzać się z IA4_INSTRUKCJA.md

Zadanie człowieka (17.10.2026), liczone jednorazowo: po 7 świecach spadkowych z rzędu (close < open) wejście
long po open 8. sesji, wyjście po close 3. sesji pozycji (8., 9., 10.); spread 0,3% raz na transakcję, dźwignia
1:5, wszystkie spółki (53 handlowane + 20 doubleProof). Portfel 10 000 $ jak w module `swing` (depozyt 10% stanu
portfela na pozycję, jedna pozycja na spółkę, wycena dzienna, ≤ 10% kapitału = upadłość; bez kosztu nocnego).

Arkusze:
  PODSUMOWANIE — wynik, CAGR, obsunięcie, najgłębsze obsunięcia, wyniki wg położenia wobec SMA200 / SMA50,
                 wg głębokości spadku w R, wg grupy spółek;
  KAPITAŁ      — stan portfela dzień po dniu (wycena po close), szczyt i obsunięcie; dwa wykresy;
  OBSUNIĘCIA   — każde obsunięcie ≥ 2%: od kiedy, dno, ile, kiedy odrobione;
  ROK PO ROKU, TRANSAKCJE (przebieg portfela), ZDARZENIA (każda seria N spadków: średnie SMA50/100/200
  i odległość ceny od nich, spadek % i w R spółki, wynik transakcji, czy weszła do portfela).

    python -m ia4.swportfel                     # domyślnie N = 7, 3 sesje, long, 1:5 (najpierw python -m ia4.daily)
    python -m ia4.swportfel --n 6 --hold 2      # inna komórka mapy SWING-SERIE
    python -m ia4.swportfel --selftest          # „WYNIK: OK”
Wynik: ~/Desktop/IA4/SWING-PORTFEL-<N>.xlsx (poza gitem).
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import __version__, config
from . import swing as sw

N_DEF, HOLD_DEF, LEV_DEF = 7, 3, 5.0
R_DAYS = 100
MAS = (50, 100, 200)
DD_MIN = 2.0                 # obsunięcia od 2% w arkuszu OBSUNIĘCIA


def events(D: sw.Data, rows: list[int], N: int, H: int, d: int, cost: float) -> list[dict]:
    """Każda seria dokładnie N świec spadkowych (sygnał po close N-tej) i transakcja, która z niej wynika."""
    out = []
    for si in rows:
        s = D.stocks[si]
        o, h, l, c = s.o, s.h, s.l, s.c
        Q = len(c)
        st = sw.streak(c < o)
        rng = (h - l) / o * 100.0
        ma = {n: sw.sma(c, n) for n in MAS}
        busy = -1
        for q in np.flatnonzero(st == N):
            q0 = q - N + 1                                       # pierwsza świeca serii
            R = float(rng[max(0, q0 - R_DAYS):q0].mean()) if q0 >= 20 else float("nan")
            drop = (c[q] / o[q0] - 1.0) * 100.0
            ev = {"si": si, "sym": s.sym, "group": s.group, "first": str(s.dates[q0]), "last": str(s.dates[q]),
                  "c": float(c[q]), "drop": drop, "R": R, "dropR": drop / R if R and R > 0 else None,
                  "ma": {n: (float(ma[n][q]) if np.isfinite(ma[n][q]) else None) for n in MAS},
                  "ma200_up": (bool(ma[200][q] > ma[200][q - 20]) if q >= 20 and np.isfinite(ma[200][q - 20]) else None)}
            e, x = q + 1, q + H
            if x >= Q:
                ev["status"] = "brak sesji wyjścia (koniec danych)" if e < Q else "brak sesji wejścia (koniec danych)"
                ev["trade"] = None
            elif e <= busy:
                ev["status"] = "spółka już w pozycji"
                ev["trade"] = None
            else:
                pin, pout = float(o[e]), float(c[x])
                move = d * (pout / pin - 1.0) * 100.0
                worst = (float(l[e:x + 1].min()) / pin - 1.0) * 100.0 if d > 0 else (1.0 - float(h[e:x + 1].max()) / pin) * 100.0
                ev["trade"] = {"si": si, "qe": int(e), "qx": int(x), "d": d, "pin": pin, "pout": pout, "why": 3}
                ev.update({"in": str(s.dates[e]), "out": str(s.dates[x]), "pin": pin, "pout": pout, "move": move,
                           "net": move - cost, "worst": worst, "status": "transakcja"})
                busy = x
            out.append(ev)
    out.sort(key=lambda e: (e["last"], e["sym"]))
    return out


def drawdowns(curve: list[tuple[str, float]], min_pct: float = DD_MIN) -> list[dict]:
    """Obsunięcia z wyceny dziennej: szczyt → dno → odrobienie szczytu (albo trwa)."""
    out = []
    peak_v, peak_d = None, None
    cur = None
    for d, v in curve:
        if peak_v is None or v >= peak_v:
            if cur is not None:
                cur["rec"] = d
                cur["days"] = (np.datetime64(d) - np.datetime64(cur["start"])).astype(int)
                if cur["depth"] >= min_pct:
                    out.append(cur)
                cur = None
            peak_v, peak_d = v, d
            continue
        dd = (peak_v - v) / peak_v * 100.0 if peak_v > 0 else 0.0
        if cur is None:
            cur = {"start": peak_d, "peak": peak_v, "trough": d, "low": v, "depth": dd, "rec": None, "days": None}
        elif dd > cur["depth"]:
            cur.update({"trough": d, "low": v, "depth": dd})
    if cur is not None and cur["depth"] >= min_pct:
        cur["days"] = (np.datetime64(curve[-1][0]) - np.datetime64(cur["start"])).astype(int)
        out.append(cur)
    return out


def groupstats(evs: list[dict], key, labels: list[str], lev: float) -> list[tuple]:
    out = []
    for lab in labels:
        x = np.array([e["net"] for e in evs if e.get("net") is not None and key(e) == lab])
        if len(x):
            out.append((lab, len(x), float((x > 0).mean() * 100), float(x.mean()), float(np.median(x)), float(x.mean() * lev)))
        else:
            out.append((lab, 0, None, None, None, None))
    return out


def run(no_sync: bool = False, out: Path | None = None, since: str | None = sw.DAILY_SINCE, cost: float = sw.COST_PCT,
        N: int = N_DEF, H: int = HOLD_DEF, d: int = 1, lev: float = LEV_DEF, data: sw.Data | None = None) -> Path:
    t0 = time.time()
    side = "long" if d > 0 else "short"
    print(f"IA 4 — portfel: po {N} świecach spadkowych {side} po open {N + 1}. sesji, wyjście po close {H}. sesji pozycji; "
          f"dźwignia 1:{lev:g}, spread {cost:g}% raz na transakcję\n")
    # pełna historia — średnie i R policzone także dla pierwszych serii; zdarzenia i portfel od `since`
    D = data or sw.load(no_sync, None, groups=("main", "proof", "doubleProof"))
    rows = D.rows("main", "proof", "doubleProof")
    print(f"  {D.note}\n  portfel od {since or D.cal[0]} do {D.cal[-1]}, {len(rows)} spółek")
    evs = [e for e in events(D, rows, N, H, d, cost) if not since or e["last"] >= since]
    trades = [e["trade"] for e in evs if e["trade"] is not None]
    pf = sw.portfolio([dict(t) for t in trades], D, lev=lev, cost=cost)
    p1 = sw.portfolio([dict(t) for t in trades], D, lev=1.0, cost=cost, keep_rows=False)
    inpf = {(r["sym"], r["in"]): r for r in pf["rows"]}
    for e in evs:
        r = inpf.get((e["sym"], e.get("in")))
        e["pf"] = r
    dds = drawdowns(pf["curve"])
    net = np.array([e["net"] for e in evs if e.get("net") is not None])
    print(f"  serii {N} spadków: {len(evs)}, transakcji: {len(trades)} (w portfelu {pf['trades']}), "
          f"zyskownych {(net > 0).mean() * 100:.0f}%, śr. netto {net.mean():+.3f}% (× {lev:g} = {net.mean() * lev:+.2f}% depozytu)")
    print(f"  portfel 1:{lev:g}: {pf['ret']:+.1f}% (stan {pf['end']:,.0f} $), największe obsunięcie {pf['mdd']:.1f}%"
          f"{', UPADŁOŚĆ' if pf['ruined'] else ''}; dla porównania 1:1 {p1['ret']:+.1f}% (obsunięcie {p1['mdd']:.1f}%)")
    for x in sorted(dds, key=lambda x: -x["depth"])[:3]:
        print(f"   obsunięcie {x['depth']:.1f}%: szczyt {x['start']} → dno {x['trough']} → "
              + (f"odrobione {x['rec']}" if x["rec"] else "jeszcze nie odrobione"))
    path = out or (config.RESEARCH_DIR.parent / f"SWING-PORTFEL-{N}.xlsx")
    write_xlsx(path, D, evs, pf, p1, dds, N, H, d, lev, cost)
    print(f"\nGotowe w {time.time() - t0:.0f} s → {path}")
    return path


def write_xlsx(path: Path, D, evs, pf, p1, dds, N, H, d, lev, cost) -> Path:
    from openpyxl import Workbook
    from openpyxl.chart import LineChart, Reference
    from openpyxl.utils import get_column_letter
    S = sw.styles()
    side = "long" if d > 0 else "short"
    wb = Workbook()
    ws = wb.active
    ws.title = "PODSUMOWANIE"
    tr = [e for e in evs if e.get("net") is not None]
    net = np.array([e["net"] for e in tr]) if tr else np.zeros(0)
    cg = sw.cagr(pf, D)
    lines = [
        (f"IA 4 — portfel: po {N} świecach spadkowych {side} po open {N + 1}. sesji, wyjście po close {H}. sesji pozycji", ""),
        ("Wersja", __version__), ("Wygenerowano", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Dane", f"zdarzenia i portfel od {evs[0]['last'] if evs else '—'} do {D.cal[-1]} (średnie i R z pełnej historii "
                 f"bazy dobowej, od {D.cal[0]}); {D.note}"),
        ("Spółki", f"{len(D.rows('main', 'proof'))} handlowanych + {len(D.rows('doubleProof'))} doubleProof"),
        ("Świeca spadkowa", "close < open; seria dokładnie N (dłuższa seria nie daje drugiego wejścia — pozycja już trwa)"),
        ("Portfel", f"10 000 $, dźwignia 1:{lev:g}, depozyt {sw.STAKE_PCT:g}% stanu portfela na pozycję (wartość pozycji "
                    f"{sw.STAKE_PCT * lev:g}% stanu); brak wolnego depozytu → stawki dnia mniejsze; jedna pozycja na spółkę"),
        ("Spread", f"{cost:g}% wartości pozycji raz na transakcję; bez kosztu nocnego (swap CFD) i dywidend"),
        ("", ""),
        ("Serii", len(evs)), ("Transakcji w portfelu", pf["trades"]),
        ("Zyskownych %", round(float((net > 0).mean() * 100), 1) if len(net) else None),
        ("Śr. wynik transakcji netto %", round(float(net.mean()), 3) if len(net) else None),
        (f"Śr. wynik na depozycie % (× {lev:g})", round(float(net.mean() * lev), 3) if len(net) else None),
        ("Mediana wyniku netto %", round(float(np.median(net)), 3) if len(net) else None),
        ("Stan końcowy $", round(pf["end"], 2)), ("Wynik portfela %", round(pf["ret"], 1)),
        ("CAGR %", round(cg, 2) if cg is not None else None),
        ("Największe obsunięcie % (wycena dzienna)", round(pf["mdd"], 1)), ("Upadłość", "TAK" if pf["ruined"] else "nie"),
        ("Najwięcej pozycji naraz", pf["max_open"]), ("Dni z pomniejszoną stawką", pf["scaled"]),
        ("Dla porównania 1:1", f"{p1['ret']:+.1f}% (obsunięcie {p1['mdd']:.1f}%)"),
    ]
    for k, (a, b) in enumerate(lines, start=1):
        ws.cell(k, 1, a)
        ws.cell(k, 2, b)
    ws["A1"].font = S.bold
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 16
    for col in "CDEFG":
        ws.column_dimensions[col].width = 14

    r = len(lines) + 2
    ws.cell(r, 1, "Najgłębsze obsunięcia").font = S.bold
    sw.header(ws, r + 1, ["Szczyt (od)", "Dno", "Obsunięcie %", "Odrobione", "Dni od szczytu do odrobienia"], [44, 16, 14, 14, 14], S, 30)
    r += 2
    for x in sorted(dds, key=lambda x: -x["depth"])[:10]:
        ws.append([x["start"], x["trough"], round(x["depth"], 1), x["rec"] or "jeszcze nie", int(x["days"]) if x["days"] is not None else None])
        r += 1

    def table(title, rowsx, r):
        r += 2
        ws.cell(r, 1, title).font = S.bold
        sw.header(ws, r + 1, ["Grupa", "Transakcji", "Zyskownych %", "Śr. netto %", "Mediana netto %", f"Śr. × {lev:g} %"],
                  [44, 16, 14, 14, 14, 14], S, 30)
        r += 2
        for lab, n, w, a, m, al in rowsx:
            ws.cell(r, 1, lab)
            ws.cell(r, 2, n)
            for j, v in enumerate((w, a, m, al), start=3):
                c = ws.cell(r, j, None if v is None else round(v, 3 if j > 3 else 1))
                if j == 4 and v is not None:
                    c.fill = S.good if v > 0 else S.bad
            r += 1
        return r

    def pos(e, n):
        m = e["ma"][n]
        return "brak średniej (za mało sesji)" if m is None else ("cena nad SMA%d" % n if e["c"] > m else "cena pod SMA%d" % n)

    r = table("Wynik wg położenia wobec SMA200", groupstats(tr, lambda e: pos(e, 200), ["cena nad SMA200", "cena pod SMA200",
              "brak średniej (za mało sesji)"], lev), r)
    r = table("Wynik wg nachylenia SMA200 (wobec 20 sesji wcześniej)", groupstats(
        tr, lambda e: "SMA200 rośnie" if e["ma200_up"] else ("SMA200 spada" if e["ma200_up"] is False else "brak"),
        ["SMA200 rośnie", "SMA200 spada", "brak"], lev), r)
    r = table("Wynik wg położenia wobec SMA50", groupstats(tr, lambda e: pos(e, 50), ["cena nad SMA50", "cena pod SMA50"], lev), r)

    def drop_lab(e):
        x = e["dropR"]
        if x is None:
            return "brak R"
        return ("spadek serii > 8 R" if x < -8 else "spadek serii 5–8 R" if x < -5 else
                "spadek serii 3–5 R" if x < -3 else "spadek serii < 3 R")
    r = table("Wynik wg głębokości spadku serii (w R spółki)", groupstats(
        tr, drop_lab, ["spadek serii > 8 R", "spadek serii 5–8 R", "spadek serii 3–5 R", "spadek serii < 3 R"], lev), r)
    gname = {"main": "główne (3)", "proof": "kontrolne (50)", "doubleProof": "doubleProof (20)"}
    r = table("Wynik wg grupy spółek", groupstats(tr, lambda e: gname[e["group"]], list(gname.values()), lev), r)
    dec = sorted({e["in"][:3] + "0–" + e["in"][:3] + "9" for e in tr})
    table("Wynik wg dekady", groupstats(tr, lambda e: e["in"][:3] + "0–" + e["in"][:3] + "9", dec, lev), r)

    # KAPITAŁ + wykresy
    kp = wb.create_sheet("KAPITAŁ")
    sw.header(kp, 1, ["Dzień", f"Stan portfela $ (1:{lev:g})", "Szczyt $", "Obsunięcie %"], [12, 16, 14, 12], S, 30)
    peak = 0.0
    for dday, v in pf["curve"]:
        peak = max(peak, v)
        kp.append([dday, round(v, 2), round(peak, 2), round(-(peak - v) / peak * 100.0 if peak > 0 else 0.0, 2)])
    n = len(pf["curve"])
    if n > 1:
        ch = LineChart()
        ch.title = f"Stan portfela 10 000 $ — po {N} spadkach, {H} sesje, 1:{lev:g} (skala logarytmiczna)"
        ch.y_axis.title = "$"
        ch.y_axis.scaling.logBase = 10
        ch.add_data(Reference(kp, min_col=2, min_row=1, max_row=n + 1), titles_from_data=True)
        ch.set_categories(Reference(kp, min_col=1, min_row=2, max_row=n + 1))
        ch.x_axis.tickLblSkip = max(1, n // 12)
        ch.x_axis.tickMarkSkip = max(1, n // 12)
        ch.legend = None
        ch.height, ch.width = 11, 30
        ch.series[0].graphicalProperties.line.width = 12000
        kp.add_chart(ch, "F2")
        c2 = LineChart()
        c2.title = "Obsunięcie od szczytu %"
        c2.add_data(Reference(kp, min_col=4, min_row=1, max_row=n + 1), titles_from_data=True)
        c2.set_categories(Reference(kp, min_col=1, min_row=2, max_row=n + 1))
        c2.x_axis.tickLblSkip = max(1, n // 12)
        c2.x_axis.tickMarkSkip = max(1, n // 12)
        c2.legend = None
        c2.x_axis.tickLblPos = "low"
        c2.height, c2.width = 8, 30
        c2.series[0].graphicalProperties.line.solidFill = "C0392B"
        c2.series[0].graphicalProperties.line.width = 9000
        kp.add_chart(c2, "F25")
    kp.freeze_panes = "A2"

    ob = wb.create_sheet("OBSUNIĘCIA")
    ob["A1"] = f"Każde obsunięcie portfela ≥ {DD_MIN:g}% (wycena po close): od szczytu do dna i do odrobienia szczytu"
    ob["A1"].font = S.bold
    sw.header(ob, 2, ["Szczyt (od)", "Stan w szczycie $", "Dno", "Stan na dnie $", "Obsunięcie %", "Odrobione",
                      "Dni od szczytu do odrobienia"], [12, 14, 12, 14, 12, 14, 14], S, 30)
    for x in dds:
        ob.append([x["start"], round(x["peak"], 2), x["trough"], round(x["low"], 2), round(x["depth"], 1),
                   x["rec"] or "jeszcze nie", int(x["days"]) if x["days"] is not None else None])
        ob.cell(ob.max_row, 5).fill = S.bad if x["depth"] >= 20 else S.sub
    ob.freeze_panes = "A3"

    yr = wb.create_sheet("ROK PO ROKU")
    sw.header(yr, 1, ["Rok", "Wynik roku %", "Transakcji", "Śr. netto %", "Zyskownych %"], [8, 12, 11, 11, 11], S, 30)
    byy: dict = {}
    for e in tr:
        byy.setdefault(e["in"][:4], []).append(e["net"])
    for y, v in pf["years"]:
        x = np.array(byy.get(y, []))
        yr.append([y, round(v, 2), len(x), round(float(x.mean()), 3) if len(x) else None,
                   round(float((x > 0).mean() * 100), 1) if len(x) else None])
        yr.cell(yr.max_row, 2).fill = S.good if v >= 0 else S.bad

    sw.portfolio_sheet(wb, "TRANSAKCJE", pf, f"Przebieg portfela 10 000 $ — 1:{lev:g}, depozyt {sw.STAKE_PCT:g}% na pozycję", S)

    zd = wb.create_sheet("ZDARZENIA")
    zd["A1"] = (f"Każda seria {N} świec spadkowych z rzędu (close < open). Spadek serii = open 1. świecy → close {N}. świecy; "
                f"R = średni zakres dnia (H − L)/open ze {R_DAYS} sesji przed serią; średnie z zamknięć, stan po close {N}. świecy.")
    zd["A1"].font = S.bold
    cols = ["Nr", "Spółka", "Grupa", "1. świeca serii", f"{N}. świeca (sygnał)", f"Close {N}. świecy",
            "Spadek serii %", "R spółki %", "Spadek w R", "SMA50", "Cena wobec SMA50 %", "SMA100", "Cena wobec SMA100 %",
            "SMA200", "Cena wobec SMA200 %", "SMA200 rośnie (20 sesji)", "Wejście (open)", "Wyjście (close)",
            "Cena wejścia", "Cena wyjścia", "Najgłębiej w trakcie %", "Wynik % (przed spreadem)", "Wynik netto %",
            f"Wynik na depozycie % (× {lev:g})", "W portfelu", "Zysk / strata $ w portfelu", "Uwagi"]
    sw.header(zd, 2, cols, [6, 9, 11, 11, 11, 10, 10, 9, 9, 10, 10, 10, 10, 10, 10, 10, 11, 11, 10, 10, 10, 10, 10, 11, 9, 11, 26], S)
    gshort = {"main": "główna", "proof": "kontrolna", "doubleProof": "doubleProof"}
    for k, e in enumerate(evs, start=1):
        ma = e["ma"]
        dist = {m: ((e["c"] / ma[m] - 1.0) * 100.0 if ma[m] else None) for m in MAS}
        rr = lambda v, p=2: None if v is None or (isinstance(v, float) and np.isnan(v)) else round(v, p)
        p = e.get("pf")
        note = e["status"] if e["status"] != "transakcja" else (
            f"stawka pomniejszona × {p['scale']:.2f}" if p and p.get("scale", 1.0) < 0.999 else ("" if p else "poza portfelem — brak wolnego depozytu"))
        zd.append([k, e["sym"], gshort[e["group"]], e["first"], e["last"], rr(e["c"], 4), rr(e["drop"]), rr(e["R"]),
                   rr(e["dropR"]), rr(ma[50], 4), rr(dist[50]), rr(ma[100], 4), rr(dist[100]), rr(ma[200], 4), rr(dist[200]),
                   None if e["ma200_up"] is None else ("tak" if e["ma200_up"] else "nie"),
                   e.get("in"), e.get("out"), rr(e.get("pin"), 4), rr(e.get("pout"), 4), rr(e.get("worst")),
                   rr(e.get("move"), 3), rr(e.get("net"), 3), rr(e["net"] * lev if e.get("net") is not None else None, 2),
                   "tak" if p else "nie", rr(p["pnl"]) if p else None, note])
        rw = zd.max_row
        if e.get("net") is not None:
            zd.cell(rw, 23).fill = S.good if e["net"] > 0 else S.bad
        for j, m in ((11, 50), (13, 100), (15, 200)):
            if dist[m] is not None:
                zd.cell(rw, j).fill = S.good if dist[m] > 0 else S.bad
    zd.freeze_panes = "C3"
    zd.auto_filter.ref = f"A2:{get_column_letter(len(cols))}{zd.max_row}"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


# ---------------------------------------------------------------------------
def selftest() -> None:
    fails: list[str] = []

    def check(name, got, exp):
        ok = got == exp
        print(f"  {'OK  ' if ok else 'BŁĄD'} {name}: {got}" + ("" if ok else f" (oczekiwano {exp})"))
        if not ok:
            fails.append(name)

    print(f"IA 4 {__version__} — selftest ia4.swportfel\n")
    sw.selftest_core(check)
    # 30 sesji płasko (zakres 1%), potem 7 spadków po 1%, potem 4 wzrosty
    o = [100.0] * 30
    c = [100.2] * 30
    p = 100.0
    for _ in range(7):
        o.append(p), c.append(p * 0.99)
        p *= 0.99
    for _ in range(4):
        o.append(p), c.append(p * 1.01)
        p *= 1.01
    o, c = np.array(o), np.array(c)
    h, l = np.maximum(o, c) * 1.004, np.minimum(o, c) * 0.996
    dts = np.array([str(np.datetime64("2010-01-04") + np.timedelta64(k, "D")) for k in range(len(c))])
    s = sw.Stock("A", "main", dts, o, h, l, c, np.ones(len(c)))
    D = sw.finish([s])
    ev = events(D, [0], 7, 3, 1, 0.3)
    check("jedna seria 7 spadków", len(ev), 1)
    e = ev[0]
    check("sygnał po 7. świecy, wejście 8., wyjście po close 10.", (e["last"], e["in"], e["out"]), (dts[36], dts[37], dts[39]))
    check("spadek serii %", round(e["drop"], 4), round((0.99 ** 7 - 1) * 100, 4))
    check("wynik netto = ruch − spread", round(e["net"], 6), round((c[39] / o[37] - 1) * 100 - 0.3, 6))
    pf = sw.portfolio([dict(e["trade"])], D, lev=5.0)
    check("portfel 1:5, depozyt 10%", round(pf["ret"], 6), round(e["net"] * 5 * 0.10, 6))
    dd = drawdowns([("2020-01-01", 100.0), ("2020-01-02", 90.0), ("2020-01-03", 80.0), ("2020-01-04", 101.0), ("2020-01-05", 99.0)], 0.5)
    check("obsunięcia: głębokość, dno, odrobienie", [(round(x["depth"], 4), x["trough"], x["rec"]) for x in dd],
          [(20.0, "2020-01-03", "2020-01-04"), (round(2 / 101 * 100, 4), "2020-01-05", None)])
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pth = run(no_sync=True, out=Path(td) / "t.xlsx", data=D)
        from openpyxl import load_workbook
        wb = load_workbook(pth)
        check("arkusze", wb.sheetnames, ["PODSUMOWANIE", "KAPITAŁ", "OBSUNIĘCIA", "ROK PO ROKU", "TRANSAKCJE", "ZDARZENIA"])
    print("\nWYNIK:", "OK" if not fails else f"BŁĘDY ({len(fails)}): " + ", ".join(fails))
    if fails:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Portfel: po N świecach spadkowych wejście na N+1. sesji (instrukcja 7a)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--no-sync", action="store_true", help="bez synchronizacji bazy dobowej")
    ap.add_argument("--since", default=sw.DAILY_SINCE, help="początek danych (domyślnie 2000-01-01)")
    ap.add_argument("--cost", type=float, default=sw.COST_PCT, help="spread %% na transakcję (raz; domyślnie 0,3)")
    ap.add_argument("--n", type=int, default=N_DEF, help="liczba świec spadkowych (domyślnie 7)")
    ap.add_argument("--hold", type=int, default=HOLD_DEF, help="sesji w pozycji (domyślnie 3)")
    ap.add_argument("--short", action="store_true", help="short zamiast long")
    ap.add_argument("--lev", type=float, default=LEV_DEF, help="dźwignia (domyślnie 5)")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    run(a.no_sync, a.out, a.since, a.cost, a.n, a.hold, -1 if a.short else 1, a.lev)


if __name__ == "__main__":
    main()
