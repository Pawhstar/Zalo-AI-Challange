"""Label-free consistency checks of the loader on any split."""
import sys, os, re, pickle
import pandas as pd
import os as _os
# repo root (folder holding Train/ and datamate/); override with DATAMATE_ROOT
ROOT = _os.environ.get("DATAMATE_ROOT") or _os.path.dirname(_os.path.dirname(
    _os.path.dirname(_os.path.abspath(__file__)))).replace("\\", "/")
sys.path.insert(0, ROOT + "/datamate")
from datamate.loader import Business
split = sys.argv[1]
base = f"{ROOT}/Train/{split}/data"
cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bizcache_" + split)
os.makedirs(cache, exist_ok=True)
for bid in (sys.argv[2:] or sorted(os.listdir(base))):
    p = os.path.join(cache, bid + ".pkl")
    if os.path.exists(p) and "--rebuild" not in sys.argv:
        b = pickle.load(open(p, "rb"))
    else:
        b = Business(bid, f"{base}/{bid}")
        pickle.dump(b, open(p, "wb"))
    m = re.search(r"có đến hết (\d{1,2}/\d{1,2}/\d{4})", b.readme)
    readme_end = pd.to_datetime(m.group(1), dayfirst=True).date() if m else None
    O, L = b.orders, b.lines
    out = [bid]
    if len(O):
        d = pd.to_datetime(O["date"], errors="coerce")
        out.append(f"orders {len(O)} dates {d.min().date() if d.notna().any() else None}..{d.max().date() if d.notna().any() else None} (README {readme_end})")
        out.append(f"NaTdate {d.isna().mean():.1%}")
        st = O["status"].value_counts(normalize=True)
        out.append(f"status unknown {st.get('', 0):.1%} canc {st.get('cancelled', 0):.1%} ret {st.get('returned', 0):.1%}")
        if "walk_in" in O:
            out.append(f"walkin {O['walk_in'].mean():.0%}")
        if "header_goods" in O.columns and O["header_goods"].notna().any() and len(L):
            X = O[O["header_goods"].notna()]
            diff = (X["order_goods"] - X["header_goods"]).abs() > 1
            out.append(f"line-vs-header goods mismatch {diff.mean():.1%}")
    else:
        out.append("NO ORDERS")
    if len(L):
        out.append(f"lines {len(L)} item-empty {(L['item'] == '').mean():.1%} rev-NaN {L['revenue'].isna().mean():.1%}"
                   f" qty-NaN {L['qty'].isna().mean():.1%} neg-qty {(pd.to_numeric(L['qty'], errors='coerce') < 0).mean():.1%}"
                   f" items {L['item'].nunique()} (catalog {len(b.items)})")
        if "hour" in L:
            out.append(f"hour-NaN {L['hour'].isna().mean():.0%}")
    print(" | ".join(out), flush=True)
