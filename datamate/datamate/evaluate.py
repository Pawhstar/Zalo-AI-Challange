"""Evaluate the deterministic engine against train/answers.jsonl.

Reports Penalized Accuracy (the official metric) plus a breakdown by intent
and by answer type, so failures point at the next thing to fix.
"""
import os, sys, json, time, argparse, collections
sys.path.insert(0, "/home/felliner/datamate")
from datamate.loader import Business
from datamate import engine, intents
from datamate.score import norm_str

TRAIN = "/home/felliner/Documents/Train/train"
BASE = "/home/felliner/Documents/Train"


def load_split(split="train"):
    root = os.path.join(BASE, split)
    qs = [json.loads(l) for l in open(os.path.join(root, "questions.jsonl"))]
    ap = os.path.join(root, "answers.jsonl")
    ans = {}
    if os.path.exists(ap):
        for l in open(ap):
            d = json.loads(l)
            ans[d["id"]] = d
    return qs, ans, os.path.join(BASE, split, "data")


def match(rtype, got, ref, aliases):
    """Official matching rules."""
    if rtype in ("number", "percent"):
        if isinstance(got, bool) or isinstance(ref, bool):
            return False
        if not isinstance(got, (int, float)):
            return False
        if rtype == "percent":
            return abs(round(float(got), 2) - round(float(ref), 2)) < 1e-9
        return abs(float(got) - float(ref)) < 1e-6
    if rtype == "boolean":
        return isinstance(got, bool) and got == ref
    if rtype in ("string", "date"):
        if not isinstance(got, str):
            return False
        forms = [ref] + list(aliases or [])
        return any(norm_str(got) == norm_str(f) for f in forms)
    if rtype == "list":
        if not isinstance(got, list) or not isinstance(ref, list):
            return False
        if len(got) != len(ref):
            return False
        for g, r in zip(got, ref):
            if isinstance(g, str) or isinstance(r, str):
                forms = [r] + list(aliases or [])
                if not any(norm_str(g) == norm_str(f) for f in forms):
                    return False
            else:
                if abs(float(g) - float(r)) > 1e-6:
                    return False
        return True
    if rtype == "table":
        if not isinstance(got, dict) or not isinstance(ref, dict):
            return False
        if [norm_str(c) for c in got.get("columns", [])] != \
           [norm_str(c) for c in ref.get("columns", [])]:
            return False
        gr = sorted([tuple(str(x) for x in r) for r in got.get("rows", [])])
        rr = sorted([tuple(str(x) for x in r) for r in ref.get("rows", [])])
        return gr == rr
    return False


def run(limit=None, businesses=None, verbose=0, dump=None):
    qs, ans, data_root = load_split("train")
    if businesses:
        qs = [q for q in qs if q["business_id"] in businesses]
    if limit:
        qs = qs[:limit]

    cache = {}
    by_intent = collections.defaultdict(lambda: [0, 0])
    by_type = collections.defaultdict(lambda: [0, 0])
    rows = []
    t0 = time.time()
    n_correct = n_wrong = 0
    for i, q in enumerate(qs):
        bid = q["business_id"]
        if bid not in cache:
            cache[bid] = Business(bid, os.path.join(data_root, bid))
        b = cache[bid]
        ref = ans.get(q["id"])
        rtype = ref.get("type") if ref else "?"
        intent, _ = intents.classify(q["question"], q["as_of_date"], b)
        try:
            got_type, got = engine.answer(b, q["question"], q["as_of_date"])
        except Exception as e:
            got_type, got = "unanswerable", {"reason": str(e)}
        if got_type == "unanswerable":
            ok = (ref is not None and rtype == "unanswerable")
            if not ok:
                n_wrong += 1
        elif ref is None:
            ok = None
        else:
            ok = (got_type == rtype) and match(rtype, got, ref.get("answer"),
                                              ref.get("alias"))
            if ok:
                n_correct += 1
            else:
                n_wrong += 1
        if ok is not None:
            by_intent[intent][1] += 1
            if ok:
                by_intent[intent][0] += 1
            by_type[rtype][1] += 1
            if ok:
                by_type[rtype][0] += 1
        rows.append({"id": q["id"], "business": bid, "intent": intent,
                     "type": rtype, "got_type": got_type, "ok": ok,
                     "got": got, "ref": ref.get("answer") if ref else None,
                     "q": q["question"]})
        if verbose and i % 200 == 0:
            print(f"  .. {i}/{len(qs)} {time.time()-t0:.0f}s", flush=True)

    n = len(qs)
    pa = (n_correct - n_wrong) / n if n else 0
    print(f"\n=== {n} questions in {time.time()-t0:.0f}s")
    print(f"correct {n_correct}  wrong {n_wrong}")
    print(f"Penalized Accuracy = {pa:.4f}")
    print("\n--- by answer type ---")
    for t, (c, tt) in sorted(by_type.items(), key=lambda x: -x[1][1]):
        print(f"  {t:14s} {c:5d}/{tt:5d}  {100*c/tt:6.1f}%")
    print("\n--- by intent (worst first, >=5 samples) ---")
    for it, (c, tt) in sorted(by_intent.items(), key=lambda x: x[1][0]/max(1, x[1][1])):
        if tt >= 5:
            print(f"  {it:24s} {c:5d}/{tt:5d}  {100*c/tt:6.1f}%")
    if dump:
        with open(dump, "w") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        print(f"\nwrote {dump}")
    return pa, rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--businesses", nargs="*")
    ap.add_argument("--verbose", type=int, default=0)
    ap.add_argument("--dump")
    a = ap.parse_args()
    run(a.limit, a.businesses, a.verbose, a.dump)
