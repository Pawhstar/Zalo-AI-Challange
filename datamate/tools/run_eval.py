import sys, os, builtins
ROOT = r"C:/Users/start/Downloads/Zalo-AI-Challange"
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
