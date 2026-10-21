"""
IA 4 — test zgodności PowrotV2.gs (Apps Script) z Pythonem (ia4.fxpowrot2, V2). Wersja projektu: 1.60 (2026-10-21)

    python tests/pv2_parity_dump.py /tmp/pv2.json && node tests/pv2_parity.js /tmp/pv2.json
→ „rozbieżności: 0”. Świece 10 par z kopii fx1h (wspólna siatka czasu jak w Pythonie) i transakcje v2 z Pythona.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ia4 import fxpowrot2 as F, fxshort as fs  # noqa: E402
from ia4.fx import sync as fxs  # noqa: E402

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp/pv2.json'
    R = F.Rynek({p: fxs.load(p) for p in fs.PAIRS}, fs.PAIRS, fs.spreads())
    D = F.simulate(R, F.events(R), **F.V2)
    doc = {'warmup': fs.WARMUP, 'spread': R.spread, 'frames': {}, 'trades': []}
    for p in fs.PAIRS:
        X = R.F[p]
        doc['frames'][p] = [[int(t), float(o), float(h), float(l), float(c), int(f)] for t, o, h, l, c, f in
                            zip(X['t'], X['o'], X['h'], X['l'], X['c'], X['filled'])]
    doc['trades'] = [[r.para, int(r.j), int(r.swiece), float(r.wynik)] for r in D.itertuples()]
    Path(out).write_text(json.dumps(doc))
    print(f'{out}: {len(D)} transakcji v2, {R.n} świec × {len(fs.PAIRS)} par')
