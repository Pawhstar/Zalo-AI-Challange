"""Leave-one-family-out evaluation of the abstain policy.

A family = shops exported in the same format (same set of file names after
stripping numbers / year suffixes). For each held-out family, trust the tags
whose accuracy on the OTHER families is >= thr with >= min_n answers, and
score the held-out family with that policy."""
import json, os, re, collections, itertools, sys

from _console import setup_io

setup_io()

import os as _os
# repo root (folder holding Train/ and datamate/); override with DATAMATE_ROOT
ROOT = _os.environ.get("DATAMATE_ROOT") or _os.path.dirname(_os.path.dirname(
    _os.path.dirname(_os.path.abspath(__file__)))).replace("\\", "/")
ROOT = ROOT + "/Train/train/data"
rows = [json.loads(l) for l in open(sys.argv[1] if len(sys.argv) > 1 else "dump_raw.jsonl", encoding="utf-8")]


def family(bid):
    fs = sorted({re.sub(r"(_\d+|_20\d\d|\d+)", "", os.path.splitext(f)[0]).lower()
                 for f in os.listdir(os.path.join(ROOT, bid)) if not f.endswith(".md")})
    return "|".join(fs)


fam = {b: family(b) for b in sorted({r["business"] for r in rows})}
groups = collections.defaultdict(list)
for b, f in fam.items():
    groups[f].append(b)
print(f"{len(groups)} families:")
for f, bs in groups.items():
    print(f"  {bs}  <- {f[:90]}")


def stats(rs):
    s = collections.defaultdict(lambda: [0, 0])
    for r in rs:
        s[r["tag"]][0 if r["ok"] else 1] += 1
    return s


def policy_from(rs, thr, min_n):
    return {t for t, (c, w) in stats(rs).items() if c + w >= min_n and c / (c + w) >= thr}


def score(rs, trusted):
    c = w = 0
    for r in rs:
        if r["tag"] in trusted:
            if r["ok"]:
                c += 1
            else:
                w += 1
    return c, w


fams = list(groups)
N = len(rows)
best = None
print("\nthr  min_n   held-out correct  wrong   PA      (in-sample PA)")
for thr, min_n in itertools.product([0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9], [3, 5, 8, 12, 20]):
    C = W = 0
    for f in fams:
        held = [r for r in rows if fam[r["business"]] == f]
        rest = [r for r in rows if fam[r["business"]] != f]
        c, w = score(held, policy_from(rest, thr, min_n))
        C += c
        W += w
    ci, wi = score(rows, policy_from(rows, thr, min_n))
    pa = (C - W) / N
    print(f"{thr:.2f} {min_n:5d}   {C:6d}  {W:6d}   {pa:+.4f}  ({(ci - wi) / N:+.4f})")
    if best is None or pa > best[0]:
        best = (pa, thr, min_n)
print("\nbest held-out:", best)

# per-family breakdown of the best policy
pa, thr, min_n = best
print("\nper family (held-out):")
for f in fams:
    held = [r for r in rows if fam[r["business"]] == f]
    rest = [r for r in rows if fam[r["business"]] != f]
    c, w = score(held, policy_from(rest, thr, min_n))
    print(f"  {groups[f]}: n={len(held)} correct {c} wrong {w} PA {(c - w) / len(held):+.3f}")

# the current hand-made policy, held-out style is not defined; show raw tags
st = stats(rows)
print("\ntags by volume:")
for t, (c, w) in sorted(st.items(), key=lambda kv: -sum(kv[1]))[:60]:
    print(f"  {t:60s} {c:4d}/{c + w:4d}  {c / (c + w):.2f}")
