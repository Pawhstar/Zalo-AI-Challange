"""Metric computation on the canonical model. All money in VND, revenue per
rulebook §1: sum of valid order-line amounts (no cancelled/returned orders,
line amounts already net of line discounts, order-level discounts & VAT &
delivery fee excluded)."""
import pandas as pd
import numpy as np
from datamate.periods import Period, round_money, round2, prev_period

def _orders(b, p, need_status=True, valid_only=False):
    O = b.orders.copy()
    if len(O) == 0:
        return O
    O = O[(O["date"] >= p.start) & (O["date"] <= p.end)]
    if valid_only:
        O = O[O["is_valid"]]
    return O

def _lines(b, p, valid_only=True):
    L = b.lines.copy()
    if len(L) == 0:
        return L
    L = L[(L["date"] >= p.start) & (L["date"] <= p.end)]
    if valid_only:
        L = L[L["valid"]]
    return L

def revenue_orders(b, p):
    """Revenue from orders: goods amount when present, else line sums."""
    O = _orders(b, p, valid_only=True)
    if len(O) == 0:
        return 0.0
    rev = O["revenue"].fillna(0.0).astype(float)
    return round_money(rev.sum())

def revenue_lines(b, p):
    L = _lines(b, p, valid_only=True)
    if len(L) == 0:
        return 0.0
    return round_money(L["revenue"].fillna(0.0).astype(float).sum())

def total_revenue(b, p):
    """Best-guess shop revenue: prefer order-level goods, fallback line-level."""
    O = _orders(b, p, valid_only=True)
    if len(O) and "order_goods" in O.columns and O["order_goods"].notna().any():
        return round_money(O["revenue"].fillna(0.0).sum())
    L = _lines(b, p, valid_only=True)
    if len(L):
        return round_money(L["revenue"].fillna(0.0).sum())
    if len(O) and O["revenue"].notna().any():
        return round_money(O["revenue"].fillna(0.0).sum())
    return 0.0

def n_orders_valid(b, p):
    O = _orders(b, p, valid_only=True)
    return int(O["order_id"].nunique()) if len(O) else 0

def n_orders_all(b, p):
    O = _orders(b, p)
    return int(O["order_id"].nunique()) if len(O) else 0

def n_orders_cancelled(b, p):
    O = _orders(b, p)
    return int(O[O["status"] == "cancelled"]["order_id"].nunique()) if len(O) else 0

def n_orders_returned(b, p):
    O = _orders(b, p)
    return int(O[O["status"] == "returned"]["order_id"].nunique()) if len(O) else 0

def cancel_rate(b, p):
    O = _orders(b, p)
    if len(O) == 0:
        return None
    total = O["order_id"].nunique()
    if total == 0:
        return None
    # count cancelled orders (only 'cancelled'; returned is separate)
    canc = O[O["status"] == "cancelled"]["order_id"].nunique()
    return round2(100.0 * canc / total)

def avg_order_value(b, p):
    from datamate.periods import round_half_up_money
    O = _orders(b, p, valid_only=True)
    if len(O) == 0:
        return None
    rev = O["revenue"].dropna()
    n = len(rev)
    if n == 0:
        return None
    return round_half_up_money(rev.sum() / n)

def rev_growth_pct(b, p):
    cur = total_revenue(b, p)
    ps, pe = prev_period(p.start, p.end)
    Lp = Period(ps, pe)
    prev = total_revenue(b, Lp)
    if prev == 0:
        return None
    return round2(100.0 * (cur - prev) / prev)

def rev_diff(b, p):
    """kỳ hỏi − kỳ so (kỳ trước), in VND."""
    cur = total_revenue(b, p)
    ps, pe = prev_period(p.start, p.end)
    prev = total_revenue(b, Period(ps, pe))
    return round_money(cur - prev)

def best_seller_by_qty(b, p, k=1):
    L = _lines(b, p, valid_only=True)
    if len(L) == 0:
        return None
    q = L.groupby("item")["qty_base"].sum().sort_values(ascending=False)
    return q.index.tolist()[:k]

def best_seller_names(b, p, k=1):
    L = _lines(b, p, valid_only=True)
    if len(L) == 0:
        return []
    q = L.groupby("item")["qty_base"].sum().sort_values(ascending=False)
    return q.index.tolist()[:k]

def revenue_by_item(b, p):
    L = _lines(b, p, valid_only=True)
    if len(L) == 0:
        return pd.Series(dtype=float)
    return L.groupby("item")["revenue"].sum()

def top_customers(b, p, k=3):
    O = _orders(b, p, valid_only=True)
    if len(O) == 0:
        return []
    # exclude walk-in (khách lẻ) per rulebook
    c = O[~O["customer"].str.contains("khách lẻ", case=False, na=False)]
    if c.empty:
        c = O
    g = c.groupby("customer")["revenue"].sum().sort_values(ascending=False)
    return g.index.tolist()[:k]

def best_day(b, p, by="revenue"):
    """Date with max revenue (or orders) in period -> 'YYYY-MM-DD'."""
    if by == "revenue":
        O = _orders(b, p, valid_only=True)
    else:
        O = _orders(b, p)
    if len(O) == 0:
        return None
    g = O.groupby(O["date"].dt.date)
    if by == "revenue":
        s = g["revenue"].sum()
    else:
        s = g["order_id"].nunique()
    return s.idxmax().isoformat()

def gross_profit(b, p):
    L = _lines(b, p, valid_only=True)
    if len(L) == 0:
        return None
    cost = (L["cost_price"].fillna(0) * L["qty"].fillna(0))
    if L["cost_price"].isna().all():
        return None
    return round_money(L["revenue"].fillna(0).sum() - cost.sum())

def purchase_value(b, p):
    P = b.purchases
    if len(P) == 0:
        return None
    P = P[(P["date"] >= p.start) & (P["date"] <= p.end)]
    P = P[P["status"] != "cancelled"]
    amt = P["amount"].dropna()
    if amt.empty:
        return None
    return round_money(amt.sum())

def purchase_qty(b, p):
    P = b.purchase_lines
    if len(P) == 0:
        return None
    P = P[(P["date"] >= p.start) & (P["date"] <= p.end)]
    P = P[P["status"] != "cancelled"]
    return round2(P["qty"].sum())

def debt_total(b, p):
    """Còn nợ as of p.end (rulebook: status at end of day, all data up to then)."""
    O = b.orders
    if len(O) == 0:
        return None
    O = O[O["is_valid"]]
    debt = O["debt"]
    if debt is None or debt.isna().all():
        return None
    return round_money(debt.fillna(0).sum())

def new_debt_in_period(b, p):
    """Nợ thêm: phần tổng đơn chưa trả ngay trong ngày mua, của đơn đặt trong kỳ."""
    O = _orders(b, p)
    O = O[O["is_valid"]]
    if len(O) == 0:
        return 0
    # total bill minus paid same-day; approximated by debt column as of data end
    d = O["debt"].fillna(0).astype(float)
    return round_money(d.sum())

def payments_collected(b, p):
    PY = b.payments
    if len(PY) == 0:
        return None
    PY = PY[(PY["date"] >= p.start) & (PY["date"] <= p.end)]
    return round_money(PY["amount"].fillna(0).sum())

def stock_value(b, p):
    S = b.stock
    if len(S) == 0:
        return None
    I = b.items
    if len(I):
        cost = dict(zip(I["item"], I["cost"]))
    else:
        cost = {}
    S["cost_u"] = S["item"].map(cost)
    S["val"] = S["qty"].fillna(0) * S["cost_u"].fillna(0)
    return round_money(S["val"].sum())

def top_employee(b, p):
    O = _orders(b, p, valid_only=True)
    if len(O) == 0 or O["employee"].isna().all() or (O["employee"].astype(str) == "").all():
        return None
    g = O.groupby("employee")["revenue"].sum().sort_values(ascending=False)
    return g.index[0]

def qty_by_unit(b, p, unit):
    """Bán được bao nhiêu <unit>: qty_base of items whose base unit is `unit`."""
    L = _lines(b, p, valid_only=True)
    I = b.items
    if len(L) == 0:
        return None
    if len(I):
        base = dict(zip(I["item"], I["base_unit"]))
        sub = L[L["item"].map(base) == unit]
    else:
        sub = L
    return round2(sub["qty_base"].sum())
