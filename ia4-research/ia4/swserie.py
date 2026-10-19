"""
IA 4 — mapa: wejście po serii świec spadkowych / wzrostowych, trzymanie 1, 2 albo 3 sesje (instrukcja, sekcja 7a).
Wersja projektu: 1.49 (2026-10-19) — musi zgadzać się z IA4_INSTRUKCJA.md

Zadanie człowieka (16.10.2026): portfele „wejście po N świecach spadkowych” dla N = 4, 5, 6 … (do najdłuższej serii
w danych), pozycja na 1 świecę (open → close następnej sesji), na 2 i na 3 sesje; long i short; zawsze liczba
transakcji i końcowy % portfela ze spreadem na dźwigni 1:5.

  • świeca spadkowa: close < open, wzrostowa: close > open (świeca bez zmiany przerywa serię);
  • sygnał po close sesji, w której seria osiąga DOKŁADNIE N (dłuższa seria to osobny wiersz N+1);
  • wejście po open następnej sesji, wyjście po close sesji 1, 2 albo 3 (bez SL i TP);
  • spread 0,3% wartości pozycji raz na transakcję; jedna pozycja na spółkę naraz;
  • portfel 10 000 $, dźwignia 1:5, depozyt 10% stanu portfela na pozycję (wartość pozycji 50% stanu);
    za mało wolnego depozytu → stawki dnia proporcjonalnie mniejsze; ≤ 10% kapitału → upadłość;
  • mapa dla 53 spółek handlowanych i osobno dla 20 spółek doubleProof (sprawdzian: czy ten sam wzór działa
    na spółkach, których mapa 53 nie widziała); dla porównania także seria świec wzrostowych.

    python -m ia4.swserie              # baza dobowa od 2000 (najpierw python -m ia4.daily); ok. minuty
    python -m ia4.swserie --selftest   # „WYNIK: OK”
Wynik: ~/Desktop/IA4/SWING-SERIE.xlsx (poza gitem).
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

N_MIN = 4
HOLDS = (1, 2, 3)
LEV = 5.0
BLOCKS = (("dn", "po N świecach spadkowych"), ("up", "po N świecach wzrostowych"))


def series(s: sw.Stock) -> dict:
    return {"dn": sw.streak(s.c < s.o), "up": sw.streak(s.c > s.o)}


def cell_trades(D: sw.Data, rows: list[int], ser: dict, block: str, N: int, H: int, d: int) -> list[dict]:
    out = []
    for si in rows:
        s = D.stocks[si]
        st = ser[si][block]
        Q = len(s.c)
        busy = -1
        for q in np.flatnonzero(st == N):
            e, x = q + 1, q + H
            if x >= Q or e <= busy:
                continue
            out.append({"si": si, "qe": int(e), "qx": int(x), "d": d, "pin": float(s.o[e]), "pout": float(s.c[x]), "why": 3})
            busy = x
    return out


def compute(D: sw.Data, rows: list[int], cost: float, lev: float = LEV) -> dict:
    ser = {si: series(D.stocks[si]) for si in rows}
    top = {b: max((int(ser[si][b].max()) for si in rows), default=0) for b, _ in BLOCKS}
    cells, per = {}, []
    for b, _ in BLOCKS:
        for N in range(N_MIN, top[b]):                         # serię N, po której jest jeszcze sesja wejścia
            for H in HOLDS:
                for d in (1, -1):
                    tr = cell_trades(D, rows, ser, b, N, H, d)
                    if not tr:
                        continue
                    net = np.array([d * (t["pout"] / t["pin"] - 1.0) * 100.0 - cost for t in tr])
                    pf = sw.portfolio([dict(t) for t in tr], D, stake_pct=sw.STAKE_PCT, lev=lev, cost=cost, keep_rows=False)
                    pos_years = [v for _, v in pf["years"]]
                    cells[(b, N, H, d)] = {"n": len(tr), "ret": pf["ret"], "ruined": pf["ruined"], "mdd": pf["mdd"],
                                           "avg": float(net.mean()), "win": float((net > 0).mean() * 100),
                                           "sum": float(net.sum()), "cagr": sw.cagr(pf, D), "end": pf["end"],
                                           "years_pos": (sum(v > 0 for v in pos_years), len(pos_years)),
                                           "max_open": pf["max_open"]}
                    bys: dict[int, list] = {}
                    for t, v in zip(tr, net):
                        bys.setdefault(t["si"], []).append(v)
                    for si, vs in bys.items():
                        per.append((D.stocks[si].sym, b, N, H, d, len(vs), float(np.mean(vs)), float(np.sum(vs))))
    return {"cells": cells, "top": top, "per": per, "n_rows": len(rows)}


def run(no_sync: bool = False, out: Path | None = None, since: str | None = sw.DAILY_SINCE, cost: float = sw.COST_PCT,
        lev: float = LEV, data: sw.Data | None = None) -> Path:
    t0 = time.time()
    print(f"IA 4 — mapa serii świec: wejście po N świecach, trzymanie {'/'.join(map(str, HOLDS))} sesje, "
          f"dźwignia 1:{lev:g}, spread {cost:g}% raz na transakcję\n")
    D = data or sw.load(no_sync, since, groups=("main", "proof", "doubleProof"))
    print(f"  {D.note}\n  dane {D.cal[0]} – {D.cal[-1]}, {len(D.stocks)} spółek")
    main = compute(D, D.rows("main", "proof"), cost, lev)
    dp = compute(D, D.rows("doubleProof"), cost, lev)
    best = sorted(main["cells"].items(), key=lambda kv: -kv[1]["ret"])[:5]
    for (b, N, H, d), c in best:
        dc = dp["cells"].get((b, N, H, d))
        print(f"  {'spadkowe' if b == 'dn' else 'wzrostowe'} N={N} · {H} ses. · {'long' if d > 0 else 'short'}: "
              f"{c['n']} transakcji, portfel {c['ret']:+.0f}%{' (upadłość)' if c['ruined'] else ''}, śr. netto {c['avg']:+.2f}% "
              f"| dP: " + (f"{dc['n']} transakcji, {dc['ret']:+.0f}%" if dc else "—"))
    path = out or (config.RESEARCH_DIR.parent / "SWING-SERIE.xlsx")
    write_xlsx(path, D, main, dp, cost, lev)
    print(f"\nGotowe w {time.time() - t0:.0f} s → {path}")
    return path


def _map_sheet(wb, title: str, res: dict, intro: str, lev: float, S):
    from openpyxl.styles import Alignment
    ws = wb.create_sheet(title)
    ws["A1"] = intro
    ws["A1"].font = S.bold
    ws["A2"] = (f"W każdej komórce: liczba transakcji i końcowy wynik % portfela 10 000 $ (dźwignia 1:{lev:g}, spread w cenie). "
                "Kolor: zielony — zysk, czerwony — strata; „✗” — upadłość (≤ 10% kapitału).")
    r = 4
    for b, bname in BLOCKS:
        ws.cell(r, 1, f"Wejście {bname}").font = S.bold
        r += 1
        cols = ["N"]
        for H in HOLDS:
            for d in (1, -1):
                lab = f"{H} {'sesja' if H == 1 else 'sesje'} · {'LONG' if d > 0 else 'SHORT'}"
                cols += [f"{lab}: transakcji", f"{lab}: wynik %"]
        sw.header(ws, r, cols, [6] + [10, 11] * (len(cols) // 2), S, height=48)
        r += 1
        Ns = sorted({N for (bb, N, _, _) in res["cells"] if bb == b})
        for N in Ns:
            ws.cell(r, 1, N).font = S.bold
            j = 2
            for H in HOLDS:
                for d in (1, -1):
                    c = res["cells"].get((b, N, H, d))
                    if c:
                        ws.cell(r, j, c["n"])
                        v = -100.0 if c["ruined"] else round(c["ret"], 1)
                        cell = ws.cell(r, j + 1, f"✗ {v:.0f}" if c["ruined"] else v)
                        cell.fill = sw.heat(v, 100.0)
                        cell.alignment = Alignment(horizontal="right")
                    j += 2
            r += 1
        r += 2
    ws.freeze_panes = "B4"
    return ws


def write_xlsx(path: Path, D, main: dict, dp: dict, cost: float, lev: float) -> Path:
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    S = sw.styles()
    wb = Workbook()
    ws = wb.active
    ws.title = "OPIS"
    lines = [("IA 4 — mapa serii świec", ""), ("Wersja", __version__), ("Wygenerowano", datetime.now().strftime("%Y-%m-%d %H:%M")),
             ("Dane", f"{D.cal[0]} – {D.cal[-1]} (baza dobowa); {D.note}"),
             ("Świeca", "spadkowa: close < open; wzrostowa: close > open; świeca bez zmiany przerywa serię"),
             ("Sygnał", "po close sesji, w której seria osiąga dokładnie N świec (dłuższa seria — wiersz N+1)"),
             ("Transakcja", "wejście po open następnej sesji; wyjście po close 1., 2. albo 3. sesji; bez SL i TP"),
             ("Spread", f"{cost:g}% wartości pozycji raz na transakcję (decyzja człowieka z 16.10.2026)"),
             ("Portfel", f"10 000 $, dźwignia 1:{lev:g}, depozyt {sw.STAKE_PCT:g}% stanu portfela na pozycję "
                         f"(wartość pozycji {sw.STAKE_PCT * lev:g}% stanu); jedna pozycja na spółkę; brak wolnego depozytu → "
                         "stawki dnia mniejsze; ≤ 10% kapitału = upadłość (rachunek nie schodzi poniżej 0)"),
             ("Nie liczone", "koszt nocny (swap) CFD przy pozycjach 2- i 3-sesyjnych; dywidendy"),
             ("Mapy", f"MAPA — {main['n_rows']} spółek handlowanych; MAPA dP — {dp['n_rows']} spółek doubleProof (sprawdzian); "
                      "SZCZEGÓŁY — więcej liczb każdej komórki; SPÓŁKI — wynik każdej spółki w każdej komórce"),
             ("Jak czytać", "Komórek jest ponad sto, więc kilka wygląda dobrze z przypadku. Wzór jest wiarygodny dopiero, gdy "
                            "ta sama komórka (i jej sąsiedzi: N ± 1, inne trzymanie) jest dodatnia także na MAPA dP.")]
    for k, (a, b) in enumerate(lines, start=1):
        ws.cell(k, 1, a)
        ws.cell(k, 2, b)
    ws["A1"].font = S.bold
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 140
    _map_sheet(wb, "MAPA", main, f"Mapa — {main['n_rows']} spółek handlowanych", lev, S)
    _map_sheet(wb, "MAPA dP", dp, f"Mapa — {dp['n_rows']} spółek doubleProof (sprawdzian)", lev, S)

    sz = wb.create_sheet("SZCZEGÓŁY")
    cols = ["Spółki", "Seria", "N", "Sesji w pozycji", "Kierunek", "Transakcji", f"Wynik portfela % (1:{lev:g})", "Upadłość",
            "CAGR %", "Obsunięcie %", "Śr. wynik transakcji netto %", "Zyskownych %", "Suma wyników transakcji %",
            "Lata dodatnie", "Najwięcej pozycji naraz"]
    sw.header(sz, 1, cols, [12, 12, 5, 9, 9, 10, 12, 9, 9, 10, 12, 10, 12, 10, 10], S)
    for name, res in (("53 handlowane", main), ("20 doubleProof", dp)):
        for (b, N, H, d), c in sorted(res["cells"].items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], -kv[0][3])):
            sz.append([name, "spadkowe" if b == "dn" else "wzrostowe", N, H, "long" if d > 0 else "short", c["n"],
                       round(c["ret"], 1), "TAK" if c["ruined"] else "nie", None if c["cagr"] is None else round(c["cagr"], 2),
                       round(c["mdd"], 1), round(c["avg"], 3), round(c["win"], 1), round(c["sum"], 1),
                       f"{c['years_pos'][0]}/{c['years_pos'][1]}", c["max_open"]])
            sz.cell(sz.max_row, 7).fill = S.good if c["ret"] > 0 else S.bad
            sz.cell(sz.max_row, 11).fill = S.good if c["avg"] > 0 else S.bad
    sz.freeze_panes = "F2"
    sz.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{sz.max_row}"

    sp = wb.create_sheet("SPÓŁKI")
    cols = ["Spółka", "Seria", "N", "Sesji w pozycji", "Kierunek", "Transakcji", "Śr. wynik netto %", "Suma wyników %",
            f"Suma × {lev:g} (dźwignia, bez procentu składanego)"]
    sw.header(sp, 1, cols, [9, 11, 5, 9, 9, 10, 11, 11, 14], S)
    for sym, b, N, H, d, n, avg, sm in sorted(main["per"] + dp["per"], key=lambda x: (x[0], x[1], x[2], x[3], -x[4])):
        sp.append([sym, "spadkowe" if b == "dn" else "wzrostowe", N, H, "long" if d > 0 else "short", n, round(avg, 3),
                   round(sm, 2), round(sm * lev, 1)])
    sp.freeze_panes = "B2"
    sp.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{sp.max_row}"
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

    print(f"IA 4 {__version__} — selftest ia4.swserie\n")
    sw.selftest_core(check)
    # 5 spadkowych, potem wzrostowe: N=4 sygnał na 4. świecy (wejście 5.), N=5 na 5. (wejście 6.)
    o = np.array([10, 10, 9.8, 9.6, 9.4, 9.2, 9.0, 9.1, 9.3, 9.5, 9.7, 9.9, 10.1, 10.3, 10.5])
    c = np.array([10, 9.8, 9.6, 9.4, 9.2, 9.0, 9.1, 9.3, 9.5, 9.7, 9.9, 10.1, 10.3, 10.5, 10.7])
    h, l = np.maximum(o, c) + 0.05, np.minimum(o, c) - 0.05
    d = np.array([f"2021-01-{i + 1:02d}" for i in range(len(c))])
    s = sw.Stock("A", "main", d, o, h, l, c, np.ones(len(c)))
    D = sw.finish([s])
    ser = {0: series(s)}
    check("seria spadkowa (świece 1–5)", ser[0]["dn"][:7].tolist(), [0, 1, 2, 3, 4, 5, 0])
    t4 = cell_trades(D, [0], ser, "dn", 4, 1, 1)
    check("N=4, 1 sesja: wejście po open 5. świecy, wyjście po close tej samej", [(t["qe"], t["qx"]) for t in t4], [(5, 5)])
    t5 = cell_trades(D, [0], ser, "dn", 5, 3, 1)
    check("N=5, 3 sesje: wejście 6., wyjście po close 8.", [(t["qe"], t["qx"]) for t in t5], [(6, 8)])
    tu = cell_trades(D, [0], ser, "up", 4, 2, 1)
    check("seria wzrostowa N=4, 2 sesje", [(t["qe"], t["qx"]) for t in tu], [(10, 11)])
    res = compute(D, [0], 0.3, 5.0)
    c4 = res["cells"][("dn", 4, 1, 1)]
    exp = (9.0 / 9.2 - 1) * 100 - 0.3
    check("komórka: wynik portfela = 1:5 × depozyt 10% × wynik netto", round(c4["ret"], 6), round(exp * 5 * 0.10, 6))
    check("short = przeciwny ruch − spread", round(res["cells"][("dn", 4, 1, -1)]["avg"], 6), round(-(9.0 / 9.2 - 1) * 100 - 0.3, 6))
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        s2 = sw.Stock("B", "doubleProof", d, o, h, l, c, np.ones(len(c)))
        p = run(no_sync=True, out=Path(td) / "t.xlsx", data=sw.finish([s, s2]))
        from openpyxl import load_workbook
        wb = load_workbook(p)
        check("arkusze", wb.sheetnames, ["OPIS", "MAPA", "MAPA dP", "SZCZEGÓŁY", "SPÓŁKI"])
    print("\nWYNIK:", "OK" if not fails else f"BŁĘDY ({len(fails)}): " + ", ".join(fails))
    if fails:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Mapa: wejście po serii świec, trzymanie 1/2/3 sesje (instrukcja 7a)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--no-sync", action="store_true", help="bez synchronizacji bazy dobowej")
    ap.add_argument("--since", default=sw.DAILY_SINCE, help="początek danych (domyślnie 2000-01-01)")
    ap.add_argument("--cost", type=float, default=sw.COST_PCT, help="spread %% na transakcję (raz; domyślnie 0,3)")
    ap.add_argument("--lev", type=float, default=LEV, help="dźwignia (domyślnie 5)")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    run(a.no_sync, a.out, a.since, a.cost, a.lev)


if __name__ == "__main__":
    main()
