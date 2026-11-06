"""Build datamate/policy.json: tags answered on the test set.
usage: python make_policy.py dump_raw.jsonl THR MIN_N"""
import json, sys, collections
dump, thr, min_n = sys.argv[1], float(sys.argv[2]), int(sys.argv[3])
s = collections.defaultdict(lambda: [0, 0])
for l in open(dump, encoding="utf-8"):
    r = json.loads(l)
    s[r["tag"]][0 if r["ok"] else 1] += 1
trusted = sorted(t for t, (c, w) in s.items() if t and c + w >= min_n and c / (c + w) >= thr)
out = {"rule": f"tags with train accuracy >= {thr} over >= {min_n} answers "
               f"(threshold chosen by leave-one-shop-family-out CV)",
       "trusted": trusted,
       "train_stats": {t: {"correct": c, "wrong": w} for t, (c, w) in sorted(s.items()) if t}}
p = r"C:/Users/start/Downloads/Zalo-AI-Challange/datamate/datamate/policy.json"
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(trusted), "trusted tags ->", p)
