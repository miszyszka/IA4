"""
IA 4 — test zgodności silnika JS (PaperEngine.gs) z Pythonem (ia4.lab).
Wersja projektu: 1.15 (2026-10-04) — musi zgadzać się z IA4_INSTRUKCJA.md

Uruchomienie (w ia4-research/, potrzebny Node.js):
  python tests/parity_dump.py /tmp/ia4_parity.json
  node tests/parity.js /tmp/ia4_parity.json        # musi być: rozbieżności 0 i 0
Dane syntetyczne, 140 reguł (7 wzorcowych + losowe z filtrami).
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json, random, numpy as np, sys
from ia4.lab import selftest, data, rules, space, settings
frames = selftest.synthetic(n_inst=4, sessions=420, seed=11)
traded=[f"X{i}" for i in range(4)]
m = data.load_market(frames, traded, vault_bars=800)
cfg = settings.merged({})
th = space.thresholds(m)
rng = random.Random(5)
R = []
for r in selftest.RULES:
    r = json.loads(json.dumps(r)); r["schema"]=rules.SCHEMA; R.append(r)
while len(R) < 140:
    r = space.random_rule(rng, cfg, th)
    if not space.valid(r, cfg): continue
    if rng.random()<0.7 and len(r["filters"])<2: space.add_filter(r, rng, th)
    R.append(r)
for r in R:
    r["exit"]["sl"] = rng.choice([1,2,3,5]); r["exit"]["tp"] = rng.choice([1,2,3,5,8])
out = {"frames": {s: frames[s][["date","slot","o","h","l","c","v"]].assign(date=lambda d: d.date.str.replace("-","").astype(int)).values.tolist() for s in traded+["SPY","QQQ"]},
       "traded": traded, "rules": [], "seg": [[int(a),int(b)] for a,b in zip(m.seg_start,m.seg_end)]}
for r in R:
    mask = rules.signal_mask(r, m) & rules.filter_mask(r, m, rules.lines_of(r, m))
    _, rec = rules.run(r, m, [r["exit"]["sl"]], [r["exit"]["tp"]], rec=(0,0))
    out["rules"].append({"rule": r, "mask": np.flatnonzero(mask).tolist(),
        "trades": [[int(x[0]), int(x[2]), round(float(x[3]),9), int(x[4])] for x in rec]})
json.dump(out, open(sys.argv[1],"w"))
print(len(R), sum(len(x["mask"]) for x in out["rules"]), sum(len(x["trades"]) for x in out["rules"]))
