"""Evaluate engine on train with pickled Business objects (loader output cached).
usage: python fasteval.py [--rebuild] [--only biz_101,biz_102] [--dump out.jsonl]"""
import sys, os, json, time, pickle, collections, argparse, importlib
import os as _os
# repo root (folder holding Train/ and datamate/); override with DATAMATE_ROOT
ROOT = _os.environ.get("DATAMATE_ROOT") or _os.path.dirname(_os.path.dirname(
    _os.path.dirname(_os.path.abspath(__file__)))).replace("\\", "/")
sys.path.insert(0, ROOT + "/datamate")
os.environ["CALENDAR_CSV"] = ROOT + "/Train/train/calendar.csv"
from datamate.loader import Business
from datamate import engine, intents
from datamate.evaluate import match

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "bizcache")
os.makedirs(CACHE, exist_ok=True)

ap = argparse.ArgumentParser()
ap.add_argument("--rebuild", action="store_true")
ap.add_argument("--only")
ap.add_argument("--dump", default=os.path.join(HERE, "dump_fast.jsonl"))
a = ap.parse_args()

qs = [json.loads(l) for l in open(ROOT + "/Train/train/questions.jsonl", encoding="utf-8")]
ans = {}
for l in open(ROOT + "/Train/train/answers.jsonl", encoding="utf-8"):
    d = json.loads(l)
    ans[d["id"]] = d
qs.sort(key=lambda q: q["business_id"])
if a.only:
    keep = set(a.only.split(","))
    qs = [q for q in qs if q["business_id"] in keep]


def load(bid):
    p = os.path.join(CACHE, bid + ".pkl")
    if os.path.exists(p) and not a.rebuild:
        with open(p, "rb") as f:
            return pickle.load(f)
    b = Business(bid, ROOT + "/Train/train/data/" + bid)
    for k in ("_qctx",):
        if hasattr(b, k):
            delattr(b, k)
    with open(p, "wb") as f:
        pickle.dump(b, f)
    return b


cache = {}
t0 = time.time()
n_ok = n_wrong = n_abs = 0
by_int = collections.defaultdict(lambda: [0, 0, 0])
rows = []
for q in qs:
    bid = q["business_id"]
    if bid not in cache:
        cache.clear()
        cache[bid] = load(bid)
    b = cache[bid]
    ref = ans[q["id"]]
    rtype = ref["type"]
    try:
        gt, gv = engine.answer(b, q["question"], q["as_of_date"])
    except Exception as e:
        gt, gv = "unanswerable", {"reason": f"crash {e}"}
    src = "q" if getattr(engine, "_last_src", "") == "q" else "e"
    if gt == "abstain":
        ok = None
        n_abs += 1
    elif gt == "unanswerable":
        ok = rtype == "unanswerable"
    else:
        ok = gt == rtype and match(rtype, gv, ref["answer"], ref.get("alias"))
    if ok is True:
        n_ok += 1
    elif ok is False:
        n_wrong += 1
    try:
        it = intents.classify(q["question"], q["as_of_date"], b)[0]
    except Exception:
        it = "?"
    key = ("Q:" if src == "q" else "") + it
    by_int[key][0 if ok else (2 if ok is None else 1)] += 1
    rows.append({"id": q["id"], "business": bid, "intent": key, "type": rtype, "got_type": gt,
                 "ok": ok, "tag": getattr(engine, "_last_tag", None), "got": gv, "ref": ref["answer"], "q": q["question"]})
n = len(qs)
print(f"{n} q in {time.time()-t0:.0f}s  correct {n_ok}  wrong {n_wrong}  abstain {n_abs}  PA {(n_ok-n_wrong)/n:.4f}")
for k, (c, w, ab) in sorted(by_int.items(), key=lambda x: -(x[1][1])):
    if c + w + ab >= 5:
        print(f"  {k:28s} ok {c:4d}  wrong {w:4d}  abst {ab:4d}")
with open(a.dump, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
