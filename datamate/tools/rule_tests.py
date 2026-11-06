"""Rule tests: hand-built mini shops with hand-computed answers, one case per
rulebook rule. They validate modules for industries the train split does not
contain (rulebook public §6: sửa xe, điện thoại, mẹ và bé), where the CV policy
has no evidence and would abstain forever.

usage: python rule_tests.py            run every case, write rule_tests_passed.json

A tag is "passed" when at least MIN_CASES cases route to it and every one of
them is answered correctly. make_policy.py adds passed tags to the trusted set,
but only tags the train dump never saw: train evidence always wins.

Fixtures live in datamate/tests/rules/*.py; each module defines CASES, a list of
dicts:
    {"name": str,                     # what rule the case checks
     "readme": str,                   # README.md of the mini shop
     "files": {fname: rows},          # rows = list of lists, first row = header
     "questions": [(question, as_of, type, answer), ...]}
Spreadsheet fixtures (.xlsx) take {sheet: rows}. No public or private test data
is used: every number is typed by hand from the rule text.
"""
import sys, os, json, glob, shutil, tempfile, importlib.util, collections, traceback

from _console import setup_io

setup_io()

ROOT = os.environ.get("DATAMATE_ROOT") or os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))).replace("\\", "/")
sys.path.insert(0, ROOT + "/datamate")
os.environ.setdefault("CALENDAR_CSV", ROOT + "/Train/public_test/calendar.csv")
import pandas as pd
from datamate.loader import Business
from datamate import engine
from datamate.evaluate import match

MIN_CASES = 3
HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(ROOT, "datamate", "tests", "rules")
OUT = os.path.join(HERE, "rule_tests_passed.json")


def _write_shop(d, case):
    with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as f:
        f.write(case["readme"])
    for fname, rows in case["files"].items():
        p = os.path.join(d, fname)
        if fname.lower().endswith(".csv"):
            pd.DataFrame(rows[1:], columns=rows[0]).to_csv(p, index=False, encoding="utf-8")
        elif fname.lower().endswith(".xlsx"):
            with pd.ExcelWriter(p) as w:
                for sheet, srows in rows.items():
                    pd.DataFrame(srows[1:], columns=srows[0]).to_excel(w, sheet_name=sheet, index=False)
        else:
            raise ValueError(f"unsupported fixture file {fname}")


def _load_cases():
    cases = []
    for p in sorted(glob.glob(os.path.join(FIXTURES, "*.py"))):
        if os.path.basename(p).startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(os.path.basename(p)[:-3], p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for c in mod.CASES:
            c = dict(c)
            c["module"] = os.path.basename(p)[:-3]
            cases.append(c)
    return cases


def run(verbose=True):
    per_tag = collections.defaultdict(lambda: [0, 0])
    fails = []
    n_ok = n = 0
    for case in _load_cases():
        d = tempfile.mkdtemp(prefix="ruletest_")
        try:
            _write_shop(d, case)
            b = Business("rule_" + case["module"], d)
            for q, as_of, rtype, ref in case["questions"]:
                n += 1
                try:
                    t, v, tag = engine.raw_answer(b, q, as_of)
                except Exception:
                    t, v, tag = "crash", traceback.format_exc(limit=1), "crash"
                if t == "unanswerable":                  # scored like fasteval.py
                    ok = rtype == "unanswerable"
                else:
                    ok = t == rtype and match(rtype, v, ref, None)
                per_tag[tag][0 if ok else 1] += 1
                n_ok += ok
                if not ok:
                    fails.append((case["module"], case["name"], q, rtype, ref, t, v, tag))
        finally:
            shutil.rmtree(d, ignore_errors=True)
    passed = sorted(t for t, (c, w) in per_tag.items()
                    if t and t != "crash" and w == 0 and c >= MIN_CASES)
    json.dump({"min_cases": MIN_CASES, "passed": passed,
               "stats": {t: {"correct": c, "wrong": w} for t, (c, w) in sorted(per_tag.items())}},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if verbose:
        print(f"{n_ok}/{n} rule-test questions correct")
        for t, (c, w) in sorted(per_tag.items()):
            mark = "PASS" if t in passed else "    "
            print(f"  {mark} {t:55} {c} ok / {w} wrong")
        for m, name, q, rt, ref, t, v, tag in fails:
            print(f"  FAIL [{m}] {name}: {q!r}\n       want {rt} {ref!r}, got {t} {v!r} (tag {tag})")
        print(len(passed), "passed tags ->", OUT)
    return passed


if __name__ == "__main__":
    run()
