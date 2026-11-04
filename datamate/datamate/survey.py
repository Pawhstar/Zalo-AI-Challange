"""Load every business and report canonical table shapes + date coverage."""
import sys, os, time, json
sys.path.insert(0, "/home/felliner/datamate")
from datamate.loader import Business
import pandas as pd

ROOT = "/home/felliner/Documents/Train/train/data"

rows = []
for bid in sorted(os.listdir(ROOT)):
    t = time.time()
    try:
        b = Business(bid, os.path.join(ROOT, bid))
    except Exception as e:
        rows.append((bid, "ERROR", str(e)[:60], "", "", "", ""))
        continue
    dt = ""
    if len(b.orders) and b.orders["date"].notna().any():
        dt = f"{b.orders['date'].min().date()}..{b.orders['date'].max().date()}"
    st = b.orders["status"].value_counts().to_dict() if len(b.orders) else {}
    rows.append((bid,
                 f"{len(b.orders)}o/{len(b.lines)}l",
                 f"{len(b.items)}i/{len(b.units)}u/{len(b.stock)}s",
                 f"{len(b.purchases)}p/{len(b.purchase_lines)}pl/{len(b.payments)}py",
                 dt, str(st), f"{time.time()-t:.1f}s"))
    print(f"{bid:10s} {rows[-1][1]:18s} {rows[-1][2]:18s} {rows[-1][3]:22s} {rows[-1][4]:26s} {rows[-1][6]}")

print("\n=== summary ===")
for r in rows:
    print(f"{r[0]:10s} {r[1]:18s} {r[2]:18s} {r[3]:22s} {r[4]:26s} {r[5][:40]:42s} {r[6]}")
