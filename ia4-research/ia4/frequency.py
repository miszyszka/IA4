"""
IA 4 — częstość sygnałów S1 na okresie odkrywania (Etap 1, kryterium 1.3).
Wersja projektu: 0.36 (2026-09-28) — musi zgadzać się z IA4_INSTRUKCJA.md

Dla każdego z 286 sygnałów: ile razy odpala i w ilu różnych dniach, osobno w
grupie głównej (AAPL, TSLA, NVDA) i kontrolnej (50 spółek). SPY i QQQ to tło
rynku — nie są handlowane, więc nie wchodzą do żadnej grupy (dla H7 SPY jest
tylko punktem odniesienia).

To JEDYNE, co Etap 1 wolno policzyć na prawdziwych danych (1.1): częstość nie
mówi nic o tym, co było potem. Moduł celowo nie importuje silnika transakcji
(`engine.py`) — test `tests/test_frequency.py` tego pilnuje.

Sygnał, który w grupie głównej odpala w mniej niż 30 różnych dniach, dostaje
status „za rzadki” (1.1, D16a) — zostaje w katalogu i w liczniku prób (5.7),
ale nie idzie do Etapu 2. Kontrolne (BASE) zostają kontrolne.

    python -m ia4.frequency          # zapisuje ../s1/frequency.json
    python -m ia4.catalog            # potem: katalog wczytuje częstość i statusy

Wynik trafia do `s1/frequency.json` z hashem definicji katalogu. `catalog.py`
dołącza częstość tylko wtedy, gdy hash się zgadza — częstość policzona dla
innych definicji nie może się po cichu przykleić do nowych.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import bars, catalog, config, data, signals

MIN_DAYS_MAIN = 30          # 1.1 / D16a
OUT = catalog.repo_root() / "s1" / "frequency.json"


def count(cat: dict, frames: dict, spy, groups: dict, progress=print) -> dict:
    """
    frames: {symbol: DataFrame świec (okres odkrywania)}; spy: DataFrame SPY albo None;
    groups: {"main": [...], "control": [...]}.  Zwraca {id: {grupa: {signals, days}}}.
    """
    sigs = cat["signals"]
    acc = {s["id"]: {g: {"signals": 0, "days": set()} for g in groups} for s in sigs}
    for g, syms in groups.items():
        for sym in syms:
            if sym not in frames:
                continue
            t0 = time.time()
            B = bars.prepare(frames[sym], market=spy)
            for s in sigs:
                m = signals.mask(s, B)
                if m.any():
                    a = acc[s["id"]][g]
                    a["signals"] += int(m.sum())
                    a["days"].update(B.date[m].tolist())
            progress(f"  {sym:6s} ({g}): {B.n} świec, {time.time() - t0:.1f} s")
    return {i: {g: {"signals": v["signals"], "days": len(v["days"])} for g, v in d.items()}
            for i, d in acc.items()}


def build(cat: dict, counts: dict, groups: dict, period_end: str) -> dict:
    rows = {}
    for s in cat["signals"]:
        c = counts[s["id"]]
        status = s["status"]
        if status == "aktywny" and c["main"]["days"] < MIN_DAYS_MAIN:
            status = "za rzadki"
        rows[s["id"]] = {"code": s["code"], "main": c["main"], "control": c["control"], "status": status}
    return {
        "meta": {
            "definitions_hash": cat["meta"]["definitions_hash"],
            "period": "discovery",
            "period_end_exclusive": period_end,
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "min_days_main": MIN_DAYS_MAIN,
            "groups": groups,
            "signals_rare": sum(1 for r in rows.values() if r["status"] == "za rzadki"),
            "note": "Częstość (1.1): ile razy sygnał odpala i w ilu różnych dniach. Żadnego wyniku transakcji.",
        },
        "signals": rows,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Częstość sygnałów S1 na okresie odkrywania (kryterium 1.3).")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)

    cat = catalog.build(with_frequency=False)
    u = config.universe()
    groups = {"main": list(u["main"]), "control": list(u["proof"])}
    v = config.vault()
    print(f"Częstość {cat['meta']['signals']} sygnałów, okres odkrywania (< {v.discovery_end_exclusive}), "
          f"{len(groups['main'])} + {len(groups['control'])} spółek")
    syms = groups["main"] + groups["control"]
    frames = {s: data.load(s) for s in syms}                   # domyślnie: tylko odkrywanie (5.1)
    spy = data.load("SPY")
    counts = count(cat, frames, spy, groups)
    out = build(cat, counts, groups, v.discovery_end_exclusive)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    m = out["meta"]
    print(f"Zapisano {a.out}: za rzadkich {m['signals_rare']} (grupa główna < {MIN_DAYS_MAIN} dni).")
    print("Teraz: python -m ia4.catalog — dołączy częstość i statusy do s1/catalog.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
