"""
IA 4 — test zgodności SmaKrzyz.gs (Apps Script) z Pythonem: SMA42/SMA23 „zawsze w pozycji” (tabela SMA-KRZYŻ, komórka 42/23).
Wersja projektu: 1.60 (2026-10-21)

    python tests/sma_check_dump.py /tmp/sma.json && node tests/sma_check.js /tmp/sma.json
→ „rozbieżności: 0”. Świece 10 par z kopii fx1h; transakcje liczone w Pythonie (pandas rolling) i w JS (sma_batch_).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ia4 import fxpowrot2 as F2, fxshort as fs  # noqa: E402
from ia4.fx import sync as fxs  # noqa: E402

A, B = 42, 23


def trades(p, d, sp):
    o, c = d.o.values, d.c.values
    a, b = pd.Series(c).rolling(A).mean().values, pd.Series(c).rolling(B).mean().values
    dirs = np.where(a > b, 1, np.where(a < b, -1, 0))
    out, cur, want = [], None, 0
    for j in range(max(A, 1), len(c)):
        if want and (cur is None or cur[0] != want):
            if cur is not None:
                out.append([p, cur[1], j, cur[0] * (o[j] - cur[2]) / cur[2] * 100 - sp / cur[2] * 100])
            cur = (want, j, o[j])
        if dirs[j]:
            want = int(dirs[j])
    return out


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp/sma.json'
    doc = {'spread': fs.spreads(), 'frames': {}, 'trades': []}
    for p in fs.PAIRS:
        d = fxs.load(p).sort_values('time').reset_index(drop=True)
        doc['frames'][p] = [[int(t), float(o), float(h), float(l), float(c), int(f)] for t, o, h, l, c, f in d[['time', 'o', 'h', 'l', 'c', 'filled']].values]
        doc['trades'] += trades(p, d, fs.spreads()[p] * F2.pip_of(p))
    Path(out).write_text(json.dumps(doc))
    print(f'{out}: {len(doc["trades"])} zamkniętych transakcji, 10 par')
