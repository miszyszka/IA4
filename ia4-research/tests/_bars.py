"""Wspólne sztuczne świece do testów sygnałów i silnika (Etap 1b). Bez danych, bez Firestore."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from ia4 import bars, nyse  # noqa: E402

START = "2025-03-03"   # poniedziałek; do połowy kwietnia 2025 ani świąt, ani sesji skróconych


def days(start: str = START) -> list[str]:
    return [d for d in nyse.trading_days() if d >= start]


def doji(p):
    return (p, p, p, p)


def frame(rows, start=START, symbol="TST", per_session=7, skip=()):
    """
    rows: lista (o, h, l, c) albo (o, h, l, c, v); numery świec i daty nadawane po kolei
    (7 świec na sesję). `skip` — pozycje (numery w rows), których NIE wstawiać (dziury).
    """
    ds = days(start)
    out = []
    for i, r in enumerate(rows):
        if i in skip:
            continue
        o, h, l, c = r[:4]
        v = r[4] if len(r) > 4 else 1000.0
        out.append((symbol, ds[i // per_session], i % per_session + 1, o, h, l, c, v))
    return pd.DataFrame(out, columns=["symbol", "date", "slot", "o", "h", "l", "c", "v"])


def mk(rows, market_rows=None, splits=(), **kw) -> bars.Bars:
    df = frame(rows, **kw)
    mkt = None
    if market_rows is not None:
        mkt = frame(market_rows, symbol="SPY", **{k: v for k, v in kw.items() if k == "start"})
    return bars.prepare(df, splits=list(splits), market=mkt)


def closes(cs, **kw) -> bars.Bars:
    return mk([doji(c) for c in cs], **kw)


def fires(mask) -> list[int]:
    return [int(i) for i, x in enumerate(mask) if x]


def run(tests: dict) -> int:
    failed = 0
    for name, fn in tests.items():
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"✓ {name}")
        except AssertionError as e:
            failed += 1
            print(f"✗ {name}: {e}")
    n = sum(1 for k, v in tests.items() if k.startswith("test_") and callable(v))
    print(f"\n{n - failed}/{n} testów zaliczonych")
    return 1 if failed else 0
