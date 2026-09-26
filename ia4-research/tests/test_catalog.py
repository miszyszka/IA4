"""
Testy katalogu S1 (Etap 1a). Wersja projektu: 0.27 (2026-09-26).

Uruchomienie z katalogu ia4-research:
    python -m pytest tests          # jeśli jest pytest
    python tests/test_catalog.py    # bez pytest
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ia4 import catalog as C  # noqa: E402

REPO = C.repo_root()
CAT = C.build()
SIG = CAT["signals"]
BY_CODE = {s["code"]: s for s in SIG}


def test_validate_clean():
    assert C.validate(CAT) == []


def test_counts_match_instruction_1_4():
    # Instrukcja 1.4 / 1.5 i D19: 286 sygnałów, 57 200 strategii.
    expected = {"H1": 168, "H2": 44, "H3": 16, "H4": 12, "H5": 6, "H6": 8, "H7": 8, "H8": 24}
    assert CAT["meta"]["by_category"] == expected
    assert len(SIG) == 286
    assert CAT["meta"]["strategies"] == 57_200
    assert CAT["meta"]["signals_control"] == 2


def test_base_identical_to_markdown():
    md = REPO / "S1_KATALOG_BAZOWY.md"
    if not md.exists():
        print("  (pominięto — brak S1_KATALOG_BAZOWY.md, to nie jest klon repozytorium)")
        return
    rows = []
    for line in md.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\| S\d{3} ", line):
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            rows.append((c[0], c[1].strip("`"), json.loads(c[4].strip("`"))))
    assert len(rows) == 84
    for (sid, code, params), s in zip(rows, SIG[:84]):
        assert (s["id"], s["code"], s["params"]) == (sid, code, params), sid


def test_mirrors_are_one_to_one():
    for i in range(84):
        base, mir = SIG[i], SIG[i + 84]
        assert mir["origin"] == f"lustro {base['id']}"
        assert mir["paired_with"] == base["code"]
        assert mir["event"] == "wzrostowe" and base["event"] == "spadkowe"
        # Liczby lustra są te same (poza progiem RSI, który jest odbity wokół 50).
        bp = {k: v for k, v in base["params"].items() if k not in ("type", "filter", "below", "minRed")}
        mp = {k: v for k, v in mir["params"].items() if k not in ("type", "filter", "above", "minGreen")}
        assert bp == mp, base["code"]
        if "below" in base["params"]:
            assert mir["params"]["above"] == 100 - base["params"]["below"]


def test_volume_pairs_exist_and_share_base():
    for s in SIG:
        if s["category"] == "H8" and s["paired_with"]:
            assert s["paired_with"] in BY_CODE, s["code"]


def test_entry_rules():
    for s in SIG:
        t = s["params"]["type"]
        want = "SESSION_OPEN" if t in ("GAP", "GAPUP") else "NEXT_OPEN"
        assert s["entry"] == want, s["code"]


def test_window_limits():
    for s in SIG:
        assert s["warmup_bars"] <= C.MAX_WARMUP_BARS, s["code"]
        assert s["live_lookback_bars"] >= s["warmup_bars"], s["code"]


def test_definitions_are_unique():
    defs = [s["definition"] for s in SIG]
    dup = {d for d in defs if defs.count(d) > 1}
    assert not dup, dup


def test_saved_file_matches_code():
    """s1/catalog.json musi być dokładnie tym, co generuje kod (D20, przeciw L12)."""
    f = REPO / "s1" / "catalog.json"
    if not f.exists():
        print("  (pominięto — brak s1/catalog.json)")
        return
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert saved == json.loads(json.dumps(CAT, ensure_ascii=False)), \
        "s1/catalog.json nie zgadza się z ia4/catalog.py — uruchom: python -m ia4.catalog"


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"✓ {name}")
        except AssertionError as e:
            failed += 1
            print(f"✗ {name}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} testów zaliczonych")
    sys.exit(1 if failed else 0)
