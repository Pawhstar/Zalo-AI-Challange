"""Build datamate/policy.json: tags answered on the test set.
usage: python make_policy.py dump_raw.jsonl THR MIN_N"""
import json, sys, collections

from _console import setup_io

setup_io()
dump, thr, min_n = sys.argv[1], float(sys.argv[2]), int(sys.argv[3])
s = collections.defaultdict(lambda: [0, 0])
for l in open(dump, encoding="utf-8"):
    r = json.loads(l)
    s[r["tag"]][0 if r["ok"] else 1] += 1
trusted = sorted(t for t, (c, w) in s.items() if t and c + w >= min_n and c / (c + w) >= thr)
# tags train never routes to (industries absent from train) can only be
# trusted through the hand-built rule tests (tools/rule_tests.py); a tag train
# has seen is decided by train alone
import os as _os
_rt = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "rule_tests_passed.json")
from_rules = []
if _os.path.exists(_rt):
    for t in json.load(open(_rt, encoding="utf-8")).get("passed", []):
        if t in trusted:
            continue
        if t not in s:
            from_rules.append(t)                 # train never routes here
        else:
            c, w = s[t]
            # too few train answers for the CV threshold: the rule tests decide,
            # but only when train has not seen it fail even once
            if c + w < min_n and w == 0:
                from_rules.append(t)
trusted = sorted(set(trusted) | set(from_rules))
out = {"rule": f"tags with train accuracy >= {thr} over >= {min_n} answers "
               f"(threshold chosen by leave-one-shop-family-out CV); tags unseen on "
               f"train are trusted only when every rule test routed to them passes",
       "trusted": trusted,
       "from_rule_tests": sorted(from_rules),
       "train_stats": {t: {"correct": c, "wrong": w} for t, (c, w) in sorted(s.items()) if t}}
# repo root (folder holding Train/ and datamate/); override with DATAMATE_ROOT
ROOT = _os.environ.get("DATAMATE_ROOT") or _os.path.dirname(_os.path.dirname(
    _os.path.dirname(_os.path.abspath(__file__)))).replace("\\", "/")
p = ROOT + "/datamate/datamate/policy.json"
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(trusted), "trusted tags ->", p, f"({len(from_rules)} from rule tests)")
