import sys, os, builtins
import os as _os
# repo root (folder holding Train/ and datamate/); override with DATAMATE_ROOT
ROOT = _os.environ.get("DATAMATE_ROOT") or _os.path.dirname(_os.path.dirname(
    _os.path.dirname(_os.path.abspath(__file__)))).replace("\\", "/")
sys.path.insert(0, ROOT + "/datamate")
os.environ["CALENDAR_CSV"] = ROOT + "/Train/train/calendar.csv"
_open = builtins.open
def uopen(f, mode="r", *a, **k):
    if "b" not in mode and "encoding" not in k: k["encoding"] = "utf-8"
    return _open(f, mode, *a, **k)
builtins.open = uopen
from datamate import evaluate
evaluate.BASE = ROOT + "/Train"
evaluate.run(dump=os.path.join(os.path.dirname(__file__), "dump.jsonl"), verbose=1)
