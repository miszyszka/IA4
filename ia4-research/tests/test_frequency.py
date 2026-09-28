"""
Częstość sygnałów (kryterium 1.3) i jej dołączanie do katalogu. Wersja projektu: 0.40 (2026-09-28).

    python tests/test_frequency.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from _bars import doji, frame, run
from ia4 import catalog, frequency

ROOT = Path(__file__).resolve().parents[1]


def test_frequency_never_touches_trade_engine():
    """1.1: w Etapie 1 żadnego wyniku transakcji — moduł częstości nie ładuje silnika."""
    code = "import sys; import ia4.frequency; print('ia4.engine' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False", out.stdout + out.stderr


def test_count_signals_and_distinct_days_per_group():
    # 3 sesje; BASE_OPEN odpala na ostatniej świecy każdej sesji, poza ostatnią (brak wejścia)
    sig = {"id": "S001", "code": "BASE_OPEN", "params": {"type": "BASE", "when": "session_open"},
           "warmup_bars": 7, "entry": "NEXT_OPEN", "volume": False, "status": "kontrolny"}
    drop = {"id": "S002", "code": "DROP", "params": {"type": "DROP", "n": 1, "pct": 1},
            "warmup_bars": 2, "entry": "NEXT_OPEN", "volume": False, "status": "aktywny"}
    cat = {"signals": [sig, drop], "meta": {"definitions_hash": "abc"}}
    rows = [doji(100)] * 21
    rows[9] = doji(98.9)                                  # spadek ≥ 1% na t=9 (2. sesja)
    frames = {"AAA": frame(rows, symbol="AAA"), "BBB": frame([doji(100)] * 21, symbol="BBB")}
    groups = {"main": ["AAA"], "control": ["BBB"]}
    c = frequency.count(cat, frames, None, groups, progress=lambda *_: None)
    assert c["S001"]["main"] == {"signals": 2, "days": 2}
    assert c["S001"]["control"] == {"signals": 2, "days": 2}
    assert c["S002"]["main"] == {"signals": 1, "days": 1} and c["S002"]["control"]["signals"] == 0
    out = frequency.build(cat, c, groups, "2025-10-01")
    assert out["signals"]["S002"]["status"] == "za rzadki"      # 1 dzień < 30
    assert out["signals"]["S001"]["status"] == "kontrolny"      # kontrolne zostają kontrolne
    assert out["meta"]["definitions_hash"] == "abc"


def test_catalog_attaches_frequency_only_for_same_definitions():
    base = catalog.build(with_frequency=False)
    h = base["meta"]["definitions_hash"]
    sigs = {s["id"]: {"code": s["code"], "main": {"signals": 50, "days": 40},
                      "control": {"signals": 900, "days": 200}, "status": s["status"]} for s in base["signals"]}
    sigs["S001"] = dict(sigs["S001"], main={"signals": 5, "days": 4}, status="za rzadki")
    freq = {"meta": {"definitions_hash": h, "period": "discovery", "period_end_exclusive": "2025-10-01",
                     "computed_at": "2026-09-28T00:00:00+00:00", "min_days_main": 30}, "signals": sigs}
    old = catalog.FREQUENCY_PATH
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "frequency.json"
        p.write_text(json.dumps(freq), encoding="utf-8")
        try:
            catalog.FREQUENCY_PATH = p
            cat = catalog.build()
            s1 = cat["signals"][0]
            assert s1["status"] == "za rzadki" and s1["frequency"]["days"] == 4
            assert cat["meta"]["signals_rare"] == 1 and cat["meta"]["frequency"]["computed_at"]
            assert cat["meta"]["definitions_hash"] == h and cat["meta"]["content_hash"] != base["meta"]["content_hash"]
            freq["meta"]["definitions_hash"] = "inny"
            p.write_text(json.dumps(freq), encoding="utf-8")
            cat = catalog.build()
            assert cat["signals"][0]["frequency"] is None and cat["meta"]["signals_rare"] == 0
        finally:
            catalog.FREQUENCY_PATH = old


if __name__ == "__main__":
    raise SystemExit(run(dict(globals())))
