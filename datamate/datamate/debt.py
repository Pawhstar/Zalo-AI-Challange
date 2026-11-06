"""Customer debt (rulebook §4).

Debt of an order at the end of day X = what the customer must pay for the whole
order (after order-level discount, including delivery fee) minus every payment
for that order dated up to X. Cancelled orders do not count; returned orders
still count while unpaid. COD orders and marketplace orders are never debt.
Age of a debt = days from the order date (an order placed today is 0 days old).

Repayments in a period ('trả nợ', 'thu nợ') = payments made AFTER the purchase
day, dated in the period, for orders that were left unpaid on the purchase day.
New debt in a period ('nợ thêm', 'mua chịu thêm') = the unpaid part at the end
of the purchase day of orders placed in the period.
"""
import re
import numpy as np
import pandas as pd

from datamate.fold import fold, normq
from datamate.periods import parse_time, Period, round_money


def _orders(b):
    c = getattr(b, "_debt_ctx", None)
    if c is not None:
        return c
    O = b.orders.copy()
    P = b.payments.copy() if len(b.payments) else pd.DataFrame()
    if len(O) == 0 or len(P) == 0 or "order_id" not in P.columns or (P["order_id"] == "").all():
        b._debt_ctx = None
        return None
    O["day"] = pd.to_datetime(O["date"], errors="coerce").dt.normalize()
    tot = O["order_total"] if "order_total" in O.columns else pd.Series(np.nan, index=O.index)
    if tot.isna().all():
        goods = O.get("header_goods", O.get("order_goods"))
        disc = O.get("order_discount", 0)
        fee = O.get("delivery_fee", 0)
        tot = pd.to_numeric(goods, errors="coerce").fillna(0) \
            - pd.to_numeric(disc, errors="coerce").fillna(0) + pd.to_numeric(fee, errors="coerce").fillna(0)
    O["total"] = pd.to_numeric(tot, errors="coerce")
    pm = O["payment_method"].map(fold) if "payment_method" in O.columns else pd.Series("", index=O.index)
    ch = O["channel"].map(fold) if "channel" in O.columns else pd.Series("", index=O.index)
    excl = pm.str.contains(r"\bcod\b|giao hang thu tien", regex=True) | \
        ch.str.contains(r"\bsan\b|tmdt|shopee|lazada|tiktok|marketplace", regex=True)
    O = O[(O["status"] != "cancelled") & ~excl & O["total"].notna()].copy()
    P = P[P["order_id"].isin(O["order_id"])].copy()
    P["day"] = pd.to_datetime(P["date"], errors="coerce").dt.normalize()
    P["amount"] = pd.to_numeric(P["amount"], errors="coerce").fillna(0)
    od = O.set_index("order_id")["day"]
    P["oday"] = P["order_id"].map(od)
    same = P[P["day"] <= P["oday"]].groupby("order_id")["amount"].sum()
    O["paid_day0"] = O["order_id"].map(same).fillna(0)
    O["unpaid_day0"] = (O["total"] - O["paid_day0"]).clip(lower=0)
    c = {"O": O, "P": P}
    b._debt_ctx = c
    return c


def debt_at(b, X):
    """DataFrame of orders with debt > 0 at the end of day X: order_id,
    customer, walk_in, day, debt."""
    c = _orders(b)
    if c is None:
        return None
    X = pd.Timestamp(X).normalize()
    O = c["O"][c["O"]["day"] <= X].copy()
    P = c["P"][c["P"]["day"] <= X]
    paid = P.groupby("order_id")["amount"].sum()
    O["debt"] = O["total"] - O["order_id"].map(paid).fillna(0)
    O = O[O["debt"] > 0.5]
    O["age"] = (X - O["day"]).dt.days
    return O


def _cust_key(O):
    w = O["walk_in"].fillna(False).astype(bool) if "walk_in" in O.columns else pd.Series(False, index=O.index)
    if "customer_id" in O.columns and (O["customer_id"].fillna("") != "").mean() > 0.05:
        k = O["customer_id"].fillna("").astype(str)
    else:
        k = O["customer"].fillna("").map(fold)
    return k.where(~w & (k != ""), None)


def _display(O, keys):
    """Display name per customer key: the name written on its orders."""
    names = O.assign(_k=keys).dropna(subset=["_k"]).groupby("_k")["customer"].agg(
        lambda s: s.value_counts().index[0])
    return names


def try_answer(b, q, as_of):
    qn = normq(q)
    if not re.search(r"\bno\b|con thieu|chua tra|cong no|mua chiu|tra bot|thu hoi", qn):
        return None
    c = _orders(b)
    if c is None:
        if len(b.orders) and re.search(r"\bno\b|cong no", qn):
            return None
        return None
    T = pd.Timestamp(as_of).normalize()
    ts = parse_time(q, as_of)

    # ---- repayments / new debt in a period
    pay_q = re.search(r"tra no|thu no|tra bot no|thu hoi|tra bot|khach tra no", qn)
    new_q = re.search(r"no them|ghi no them|mua chiu them|ghi no", qn)
    if (pay_q or new_q) and ts.kind not in ("until", "default"):
        p = ts.main.clip(T)
        O, P = c["O"], c["P"]
        cust = _named_customer(b, q, O)
        Od = O[O["unpaid_day0"] > 0.5]
        if cust is not None:
            Od = Od[_cust_key(Od) == cust]
        Pp = P[P["order_id"].isin(Od["order_id"]) & (P["day"] > P["oday"]) &
               (P["day"] >= p.start) & (P["day"] <= p.end)]
        repaid = round_money(Pp["amount"].sum())
        On = Od[(Od["day"] >= p.start) & (Od["day"] <= p.end)]
        new = round_money(On["unpaid_day0"].sum())
        if pay_q and new_q:
            # order asked: 'nợ thêm ... và trả nợ ...'
            return "list", ([new, repaid] if qn.find("them") < qn.find("tra") else [repaid, new])
        return "number", (repaid if pay_q else new)

    # ---- status at the end of a day
    X = ts.main.end if ts.kind == "until" else (T if ts.kind == "default" else None)
    if X is None:
        return None
    X = min(pd.Timestamp(X), T)
    D = debt_at(b, X)
    if D is None:
        return None
    keys = _cust_key(D)

    m = re.search(r"(0|khong)\s*[-–]\s*(\d+).*?(\d+)\s*[-–]\s*(\d+).*?(tren|qua|hon)\s*(\d+)", qn)
    if m and re.search(r"tuoi no|nhom", qn):
        a1, a2, b1, b2, c1 = int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(4)), int(m.group(6))
        b_lo, b_hi = int(m.group(3)), int(m.group(4))
        v1 = D[(D["age"] >= 0) & (D["age"] <= a1)]["debt"].sum()
        v2 = D[(D["age"] >= b_lo) & (D["age"] <= b_hi)]["debt"].sum()
        v3 = D[D["age"] > c1]["debt"].sum()
        return "list", [round_money(v1), round_money(v2), round_money(v3)]
    m = re.search(r"(qua|hon|tren)\s*(\d+)\s*ngay", qn)
    if m:
        n = int(m.group(2))
        return "number", round_money(D[D["age"] > n]["debt"].sum())
    m = re.search(r"(top\s*(\d+)|(\d+)\s*khach)", qn)
    if m and re.search(r"nhieu nhat|lon nhat|cao nhat|top", qn):
        k = int(m.group(2) or m.group(3))
        g = D.assign(_k=keys).dropna(subset=["_k"]).groupby("_k")["debt"].sum()
        g = g[g > 0.5]
        names = _display(D, keys)
        g = g.sort_index().sort_values(ascending=False, kind="stable").head(k)
        rows = [[names.get(i, i), round_money(v)] for i, v in g.items()]
        return "table", {"columns": ["khach_hang", "so_tien_no"], "rows": rows}
    if re.search(r"(bao nhieu|may|so)\s*khach|khach .*chua tra het", qn):
        g = D.assign(_k=keys).dropna(subset=["_k"]).groupby("_k")["debt"].sum()
        return "number", int((g > 0.5).sum())
    cust = _named_customer(b, q, D)
    if cust is not None:
        return "number", round_money(D[keys == cust]["debt"].sum())
    if re.search(r"tong|bao nhieu|con no|con thieu", qn):
        return "number", round_money(D["debt"].sum())
    return None


def _named_customer(b, q, O):
    qf = fold(q)
    keys = _cust_key(O)
    best = None
    for k, nm in zip(keys, O["customer"]):
        if k is None or not nm:
            continue
        nf = fold(nm)
        if len(nf) >= 5 and nf in qf and (best is None or len(nf) > len(best[1])):
            best = (k, nf)
    return best[0] if best else None
