"""Validate a submission.jsonl against the official format rules."""
import json, sys, re, collections

from _console import setup_io

setup_io()
sub, qfile = sys.argv[1], sys.argv[2]
qids = [json.loads(l)["id"] for l in open(qfile, encoding="utf-8") if l.strip()]
types = collections.Counter()
bad = []
seen = set()
for i, line in enumerate(open(sub, encoding="utf-8")):
    d = json.loads(line)
    t = d.get("type")
    types[t] += 1
    seen.add(d.get("id"))
    a = d.get("answer")
    err = None
    if t in ("number", "percent"):
        if not isinstance(a, (int, float)) or isinstance(a, bool):
            err = "non-numeric"
    elif t == "date":
        if not (isinstance(a, str) and re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", a)):
            err = "bad date"
    elif t == "boolean":
        if not isinstance(a, bool):
            err = "bad bool"
    elif t == "string":
        if not isinstance(a, str):
            err = "bad string"
    elif t == "list":
        if not isinstance(a, list):
            err = "bad list"
    elif t == "table":
        if not (isinstance(a, dict) and isinstance(a.get("columns"), list) and isinstance(a.get("rows"), list)):
            err = "bad table"
    elif t == "unanswerable":
        if "reason" in d and not isinstance(d["reason"], str):
            err = "reason not str"
    elif t != "abstain":
        err = "unknown type"
    if err:
        bad.append((i, err, line.strip()[:120]))
missing = [q for q in qids if q not in seen]
print("lines", sum(types.values()), "questions", len(qids), "missing", len(missing))
print("types", dict(types))
print("format errors", len(bad))
for b in bad[:10]:
    print("  ", b)
