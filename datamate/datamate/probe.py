"""Quick probe: load a business, dump canonical tables, answer a sample question."""
import sys, os, json, time
sys.path.insert(0, "/home/felliner/datamate")
from datamate.loader import Business
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)

ROOT = "/home/felliner/Documents/Train/train"

def load(bid, cache={}):
    if bid not in cache:
        cache[bid] = Business(bid, os.path.join(ROOT, "data", bid))
    return cache[bid]

if __name__ == "__main__":
    bid = sys.argv[1] if len(sys.argv) > 1 else "biz_101"
    t = time.time()
    b = load(bid)
    print(f"loaded {bid} in {time.time()-t:.1f}s")
    print("orders:", b.orders.shape, "lines:", b.lines.shape,
          "items:", b.items.shape, "units:", b.units.shape,
          "stock:", b.stock.shape, "purch:", b.purchases.shape,
          "purlines:", b.purchase_lines.shape, "pay:", b.payments.shape)
    print("\n--- ORDERS ---"); print(b.orders.head(4).to_string())
    print("\n--- LINES ---"); print(b.lines.head(4).to_string())
    if len(b.items): print("\n--- ITEMS ---"); print(b.items.head(4).to_string())
    if len(b.units): print("\n--- UNITS ---"); print(b.units.head(6).to_string())
