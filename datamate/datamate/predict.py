"""Inference entry point.

    python -m datamate.predict --data /data --out /result

Reads <data>/questions.jsonl, <data>/data/<business_id>/..., <data>/calendar.csv
and writes
    <out>/submission.jsonl     one line per question: {"id", "type", "answer"}
    <out>/logs/<id>.json       per-question log: question, answer, timings, route
    <out>/logs/run.log         run summary

Fully offline and deterministic: no model, no randomness, no network.
Every question gets a line; anything that fails is written as an abstain.
"""
import argparse, json, os, sys, time, traceback, math

import numpy as np
import pandas as pd

from datamate import engine, periods
from datamate.loader import Business

VALID_TYPES = {"number", "percent", "date", "boolean", "string", "list", "table"}


def _py(v):
    """numpy / pandas scalars -> plain JSON values."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        v = float(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return int(v) if v.is_integer() else v
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (pd.Timestamp,)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, (list, tuple)):
        return [_py(x) for x in v]
    if isinstance(v, dict):
        return {k: _py(x) for k, x in v.items()}
    return v


def to_line(qid, t, v):
    """Engine result -> one submission record in the official format."""
    if t == "abstain" or t is None:
        return {"id": qid, "type": "abstain"}
    if t == "unanswerable":
        reason = v.get("reason") if isinstance(v, dict) else None
        rec = {"id": qid, "type": "unanswerable"}
        if isinstance(reason, str):
            rec["reason"] = reason
        return rec
    if t not in VALID_TYPES:
        return {"id": qid, "type": "abstain"}
    v = _py(v)
    ok = {
        "number": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool),
        "percent": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool),
        "date": lambda x: isinstance(x, str),
        "boolean": lambda x: isinstance(x, bool),
        "string": lambda x: isinstance(x, str) and x.strip() != "",
        "list": lambda x: isinstance(x, list) and all(e is not None for e in x),
        "table": lambda x: isinstance(x, dict) and "columns" in x and "rows" in x,
    }[t](v)
    if not ok:
        return {"id": qid, "type": "abstain"}
    if t == "percent":
        v = round(float(v), 2)
    return {"id": qid, "type": t, "answer": v}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="/data")
    ap.add_argument("--out", default="/result")
    a = ap.parse_args(argv)

    qpath = os.path.join(a.data, "questions.jsonl")
    cal = os.path.join(a.data, "calendar.csv")
    if os.path.exists(cal):
        periods.set_calendar(cal)
    os.makedirs(os.path.join(a.out, "logs"), exist_ok=True)

    qs = [json.loads(l) for l in open(qpath, encoding="utf-8") if l.strip()]
    order = {q["id"]: i for i, q in enumerate(qs)}
    by_biz = {}
    for q in qs:
        by_biz.setdefault(q["business_id"], []).append(q)

    results = {}
    run_log = open(os.path.join(a.out, "logs", "run.log"), "w", encoding="utf-8")
    t_all = time.time()
    for bid, group in by_biz.items():
        t0 = time.time()
        b, err = None, None
        try:
            b = Business(bid, os.path.join(a.data, "data", bid))
        except Exception:
            err = traceback.format_exc()
        load_s = time.time() - t0
        run_log.write(f"{bid}: loaded in {load_s:.1f}s, {len(group)} questions"
                      + (f"\n{err}" if err else "") + "\n")
        run_log.flush()
        for q in group:
            t1 = time.time()
            route, tb = "", None
            if b is None:
                t, v = "abstain", None
                route = "load_failed"
            else:
                try:
                    t, v = engine.answer(b, q["question"], q["as_of_date"])
                    route = getattr(engine, "_last_src", "")
                except Exception:
                    t, v, tb = "abstain", None, traceback.format_exc()
                    route = "crash"
            rec = to_line(q["id"], t, v)
            results[q["id"]] = rec
            el = time.time() - t1
            log = {"id": q["id"], "business_id": bid, "question": q["question"],
                   "as_of_date": q["as_of_date"], "final": rec, "route": route,
                   "elapsed_s": round(el, 4), "business_load_s": round(load_s, 2)}
            if tb:
                log["traceback"] = tb
            with open(os.path.join(a.out, "logs", f"{q['id']}.json"), "w", encoding="utf-8") as f:
                json.dump(log, f, ensure_ascii=False, default=str)
    with open(os.path.join(a.out, "submission.jsonl"), "w", encoding="utf-8") as f:
        for q in sorted(qs, key=lambda q: order[q["id"]]):
            f.write(json.dumps(results.get(q["id"], {"id": q["id"], "type": "abstain"}),
                               ensure_ascii=False) + "\n")
    n = len(qs)
    n_abs = sum(1 for r in results.values() if r["type"] == "abstain")
    run_log.write(f"done: {n} questions in {time.time()-t_all:.1f}s, abstain {n_abs}\n")
    run_log.close()
    print(f"wrote {n} answers ({n_abs} abstain) to {os.path.join(a.out, 'submission.jsonl')}")


if __name__ == "__main__":
    sys.exit(main())
