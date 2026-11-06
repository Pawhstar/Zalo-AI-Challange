"""Turn (question, business) into a typed answer. Deterministic path only:
intents.classify -> period resolution -> metrics -> typed answer."""
import re
import pandas as pd
import numpy as np

from datamate.periods import (Period, resolve_period, month_period, quarter_period,
                     round_money, round2, prev_period)
import datamate.metrics as M
import datamate.intents as intents
import datamate.query as query
import datamate.debt as debt
import datamate.purchases as purchases

# ---------------------------------------------------------------- period glue

def period_for(q, as_of, b=None):
    """Resolve the question's period, honouring explicit month/year mentions."""
    ql = q.lower()
    m = re.search(r"(?:tháng|thang)\s*(\d{1,2})\s*(?:/|năm|nam|-)\s*(\d{4})", ql)
    if m:
        return month_period(int(m.group(1)), int(m.group(2)))
    m = re.search(r"(?:quý|quy)\s*(\d)\s*(?:/|năm|nam|-)\s*(\d{4})", ql)
    if m:
        return quarter_period(int(m.group(1)), int(m.group(2)))
    return resolve_period(ql, as_of)

# ---------------------------------------------------------------- helpers

def _lines_in(b, p, valid=True):
    L = b.lines
    if len(L) == 0:
        return L
    L = L[(L["date"] >= p.start) & (L["date"] <= p.end)]
    return L[L["valid"]] if valid else L

def _orders_in(b, p, valid=True):
    O = b.orders
    if len(O) == 0:
        return O
    O = O[(O["date"] >= p.start) & (O["date"] <= p.end)]
    return O[O["is_valid"]] if valid else O

def _revenue_of(O, L):
    """Revenue for a set of orders: prefer order-level goods amount."""
    if len(O) == 0:
        return 0.0
    if "order_goods" in O.columns and O["order_goods"].notna().any():
        return round_money(O["order_goods"].fillna(0).sum())
    if len(L):
        return round_money(L["revenue"].fillna(0).sum())
    return round_money(O["revenue"].fillna(0).sum())

# ---------------------------------------------------------------- answer

_last_src = ""
_last_tag = None


def raw_answer(b, q, as_of):
    """(type, value, tag) before the abstain policy. tag names the route and
    question category ('q:revenue:value:group:number', 'debt:number', 'e:best_day')."""
    global _last_src, _last_tag
    for name, mod in (("debt", debt), ("pur", purchases), ("q", query)):
        try:
            r = mod.try_answer(b, q, as_of)
        except Exception:
            r = None
        if r is not None:
            _last_src = "q"
            tag = query.tag_of(r) if name == "q" else f"{name}:{r[0]}"
            _last_tag = tag
            return r[0], r[1], tag
    _last_src = "e"
    intent, p = intents.classify(q, as_of, b)
    metric = p.get("metric", "revenue")
    per = period_for(q, as_of, b)
    if per is None:
        per = Period(pd.Timestamp(as_of), pd.Timestamp(as_of))
    # records dated after 'today' have not happened yet (rulebook)
    per = Period(per.start, min(per.end, pd.Timestamp(as_of).normalize()))
    try:
        t, v = _dispatch(b, q, as_of, intent, metric, p, per)
    except Exception:
        t, v = "unanswerable", {"reason": "crash"}
    tag = f"e:{intent}:{t}"
    _last_tag = tag
    return t, v, tag


def _policy():
    global _POLICY
    if _POLICY is None:
        import json, os
        p = os.path.join(os.path.dirname(__file__), "policy.json")
        _POLICY = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"trusted": []}
        _POLICY["trusted"] = set(_POLICY.get("trusted", []))
    return _POLICY

_POLICY = None


def answer(b, q, as_of):
    """Returns (type, value). A wrong answer costs -1 and an abstain 0, so only
    question categories (tags) whose held-out accuracy across shop families
    is clearly above 50% are answered (policy.json, built by cross-validation);
    the rest abstain. DATAMATE_RAW=1 disables the policy (evaluation)."""
    import os
    t, v, tag = raw_answer(b, q, as_of)
    if os.environ.get("DATAMATE_RAW") == "1":
        return t, v
    if tag not in _policy()["trusted"]:
        return "abstain", None
    return t, v


def _dispatch(b, q, as_of, intent, metric, p, per):
    qn = p["ql"]
    item = p.get("item")
    cust = p.get("customer")
    unit = p.get("unit")

    # ---------------- revenue family
    if intent in ("revenue", "revenue_grouped"):
        O = _orders_in(b, per)
        L = _lines_in(b, per)
        if intent == "revenue_grouped":
            gb = p.get("group_by")
            if gb == "payment_method":
                if len(O) == 0 or "payment_method" not in O.columns:
                    return "unanswerable", {"reason": "no payment method column"}
                grp = O.groupby(O["payment_method"])["revenue"].sum()
                grp = grp[grp > 0]
                if len(grp) == 0:
                    return "number", 0
                return "number", round_money(grp.max())
            return "unanswerable", {"reason": "customer group not derivable"}
        if item:
            L2 = L[L["item"] == item]
            if len(L2) == 0:
                return "number", 0
            return "number", round_money(L2["revenue"].fillna(0).sum())
        return "number", _revenue_of(O, L)

    if intent == "avg_order_value":
        O = _orders_in(b, per)
        if len(O) == 0:
            return "unanswerable", {"reason": "no orders in period"}
        rev = O["revenue"].dropna()
        if len(rev) == 0:
            return "unanswerable", {"reason": "no revenue"}
        return "number", int(np.floor(rev.sum() / len(rev) + 0.5))

    if intent == "rev_growth_pct":
        cur = _period_revenue(b, per)
        prev = _previous_period_revenue(b, per, qn)
        if prev is None or prev == 0:
            return "unanswerable", {"reason": "no comparable previous period"}
        return "percent", round2(100.0 * (cur - prev) / prev)

    if intent == "rev_diff":
        cur = _period_revenue(b, per)
        prev = _previous_period_revenue(b, per, qn)
        if prev is None:
            return "unanswerable", {"reason": "no comparable previous period"}
        return "number", round_money(cur - prev)

    # ---------------- order counts
    if intent == "n_orders_valid":
        O = _orders_in(b, per)
        if len(O) == 0:
            return "unanswerable", {"reason": "no orders in period"}
        if item:
            L = _lines_in(b, per)
            L = L[L["item"] == item]
            return "number", int(L["order_id"].nunique())
        return "number", int(O["order_id"].nunique())

    if intent == "n_orders_cancelled":
        O = _orders_in(b, per, valid=False)
        if len(O) == 0:
            return "unanswerable", {"reason": "no orders in period"}
        canc = O[O["status"] == "cancelled"]
        return "number", int(canc["order_id"].nunique())

    if intent == "cancel_rate":
        O = _orders_in(b, per, valid=False)
        if len(O) == 0:
            return "unanswerable", {"reason": "no orders in period"}
        total = O["order_id"].nunique()
        canc = O[O["status"] == "cancelled"]["order_id"].nunique()
        if total == 0:
            return "unanswerable", {"reason": "no orders"}
        return "percent", round2(100.0 * canc / total)

    if intent == "n_customers_bought":
        O = _orders_in(b, per)
        if len(O) == 0:
            return "unanswerable", {"reason": "no orders in period"}
        c = O[~O["customer"].str.contains("khách lẻ", case=False, na=False)]
        if c.empty:
            c = O
        return "number", int(c["customer"].nunique())

    # ---------------- rankings
    if intent == "best_day":
        O = _orders_in(b, per) if p.get("by") != "orders" else _orders_in(b, per, valid=False)
        if len(O) == 0:
            return "unanswerable", {"reason": "no orders in period"}
        if p.get("by") == "orders":
            g = O.groupby(O["date"].dt.date)["order_id"].nunique()
        else:
            g = O.groupby(O["date"].dt.date)["revenue"].sum()
        if len(g) == 0:
            return "unanswerable", {"reason": "no data"}
        return "date", g.idxmax().isoformat()

    if intent == "peak_hour":
        O = _orders_in(b, per)
        if len(O) == 0 or "hour" not in O.columns or O["hour"].isna().all():
            return "unanswerable", {"reason": "no hour data"}
        g = O.groupby(O["hour"].astype(int))["order_id"].nunique()
        if len(g) == 0:
            return "unanswerable", {"reason": "no data"}
        return "number", int(g.idxmax())

    if intent in ("best_seller", "top_sellers"):
        L = _lines_in(b, per)
        if len(L) == 0:
            return "unanswerable", {"reason": "no sales in period"}
        if item:
            return "number", round2(L[L["item"] == item]["qty_base"].sum())
        g = L.groupby("item")["qty_base"].sum().sort_values(ascending=False)
        if len(g) == 0:
            return "unanswerable", {"reason": "no data"}
        if intent == "best_seller":
            return "string", g.index[0]
        return "list", g.index.tolist()[:p.get("topk", 3)]

    if intent in ("most_profitable", "top_profitable"):
        L = _lines_in(b, per)
        if len(L) == 0 or L["cost_price"].isna().all():
            return "unanswerable", {"reason": "no cost data"}
        L = L.copy()
        L["profit"] = L["revenue"].fillna(0) - L["cost_price"].fillna(0) * L["qty"].fillna(0)
        g = L.groupby("item")["profit"].sum().sort_values(ascending=False)
        if len(g) == 0:
            return "unanswerable", {"reason": "no data"}
        if intent == "most_profitable":
            return "string", g.index[0]
        return "list", g.index.tolist()[:p.get("topk", 3)]

    if intent == "most_ordered_item":
        L = _lines_in(b, per)
        if len(L) == 0:
            return "unanswerable", {"reason": "no sales in period"}
        g = L.groupby("item")["order_id"].nunique().sort_values(ascending=False)
        if len(g) == 0:
            return "unanswerable", {"reason": "no data"}
        return "string", g.index[0]

    if intent in ("top_customer", "top_customers"):
        O = _orders_in(b, per)
        if len(O) == 0:
            return "unanswerable", {"reason": "no orders in period"}
        c = O[~O["customer"].str.contains("khách lẻ", case=False, na=False)]
        if c.empty:
            c = O
        g = c.groupby("customer")["revenue"].sum().sort_values(ascending=False)
        if len(g) == 0:
            return "unanswerable", {"reason": "no customers"}
        if intent == "top_customer":
            return "string", g.index[0]
        return "list", g.index.tolist()[:p.get("topk", 3)]

    if intent == "most_loyal":
        O = _orders_in(b, per)
        if len(O) == 0:
            return "unanswerable", {"reason": "no orders"}
        c = O[~O["customer"].str.contains("khách lẻ", case=False, na=False)]
        g = c.groupby("customer")["date"].nunique().sort_values(ascending=False)
        if len(g) == 0:
            return "unanswerable", {"reason": "no customers"}
        return "string", g.index[0]

    if intent == "biggest_spender_avg":
        O = _orders_in(b, per)
        if len(O) == 0:
            return "unanswerable", {"reason": "no orders"}
        c = O[~O["customer"].str.contains("khách lẻ", case=False, na=False)]
        g = c.groupby("customer").agg(rev=("revenue", "sum"), n=("order_id", "nunique"))
        g = g[g["n"] >= 3]
        if len(g) == 0:
            return "unanswerable", {"reason": "no customer with 3+ orders"}
        g["avg"] = g["rev"] / g["n"]
        return "string", g["avg"].idxmax()

    if intent == "most_changed_mind":
        O = _orders_in(b, per, valid=False)
        if len(O) == 0:
            return "unanswerable", {"reason": "no orders"}
        c = O[~O["customer"].str.contains("khách lẻ", case=False, na=False)]
        g = c[c["status"] == "cancelled"].groupby("customer")["order_id"].nunique() \
            .sort_values(ascending=False)
        if len(g) == 0:
            return "unanswerable", {"reason": "no cancelled orders"}
        return "string", g.index[0]

    if intent == "best_employee":
        O = _orders_in(b, per)
        if len(O) == 0 or "employee" not in O.columns:
            return "unanswerable", {"reason": "no employee data"}
        e = O[O["employee"].astype(str) != ""]
        if len(e) == 0:
            return "unanswerable", {"reason": "no employee data"}
        g = e.groupby("employee")["revenue"].sum().sort_values(ascending=False)
        return "string", g.index[0]

    # ---------------- quantity of a named item in its unit
    if intent == "qty_of_item":
        L = _lines_in(b, per)
        if len(L) == 0:
            return "unanswerable", {"reason": "no sales in period"}
        if not item:
            return "unanswerable", {"reason": "no item specified"}
        L2 = L[L["item"] == item]
        if len(L2) == 0:
            return "number", 0
        return "number", round2(L2["qty_base"].sum())

    # ---------------- quantity by unit
    if intent == "qty_by_unit":
        if not unit:
            return "unanswerable", {"reason": "no unit specified"}
        L = _lines_in(b, per)
        if len(L) == 0:
            return "unanswerable", {"reason": "no sales in period"}
        if "base_unit" in L.columns and L["base_unit"].notna().any():
            L2 = L[L["base_unit"] == unit]
        elif len(b.items):
            base = dict(zip(b.items["item"], b.items["base_unit"]))
            L2 = L[L["item"].map(base) == unit]
        else:
            L2 = L[L["unit"] == unit]
        if len(L2) == 0:
            return "number", 0
        return "number", round2(L2["qty_base"].sum())

    # ---------------- unit price on a day
    if intent == "price_on_day":
        L = _lines_in(b, per, valid=False)
        if len(L) == 0:
            return "unanswerable", {"reason": "no sales on that day"}
        if item:
            L2 = L[L["item"] == item]
            if len(L2) == 0:
                return "number", 0
        else:
            L2 = L
        L2 = L2.copy()
        # price per sale unit, before the line discount
        price = L2["unit_price"].fillna(0).copy()
        if "line_discount" in L2.columns:
            q = L2["qty"].fillna(0).replace(0, pd.NA)
            price = price + (L2["line_discount"].fillna(0) / q).fillna(0)
        # The question may ask for the price of one sale unit ('một gói') or
        # per base unit ('bao nhiêu kg'). When a unit is named and it differs
        # from the sale unit, convert by the sale-unit -> base-unit factor.
        if unit and len(L2) and unit != L2["unit"].iloc[0]:
            factor = pd.Series(1.0, index=L2.index)
            if "qty" in L2.columns and L2["qty_base"].notna().any():
                f = L2["qty_base"] / L2["qty"].replace(0, pd.NA)
                factor = f.fillna(1.0)
            price = price / factor
        val = price.mean()
        if pd.isna(val):
            return "unanswerable", {"reason": "no price data"}
        return "number", round_money(val)

    # ---------------- stock / purchase
    if intent == "stock_value":
        v = M.stock_value(b, per)
        if v is None:
            return "unanswerable", {"reason": "no stock data"}
        return "number", v

    if intent == "stock_qty":
        if len(b.stock) == 0:
            return "unanswerable", {"reason": "no stock data"}
        if not item:
            return "unanswerable", {"reason": "no item specified"}
        S = b.stock[b.stock["item"] == item]
        if len(S) == 0:
            return "unanswerable", {"reason": "item not in stock table"}
        return "number", round2(S["qty"].sum())

    if intent == "purchase_value":
        v = M.purchase_value(b, per)
        if v is None:
            return "unanswerable", {"reason": "no purchase data"}
        return "number", v

    if intent == "purchase_qty":
        v = M.purchase_qty(b, per)
        if v is None:
            return "unanswerable", {"reason": "no purchase data"}
        return "number", v

    if intent == "top_supplier":
        P = b.purchases
        if len(P) == 0:
            return "unanswerable", {"reason": "no purchase data"}
        P = P[(P["date"] >= per.start) & (P["date"] <= per.end)]
        P = P[P["status"] != "cancelled"]
        P = P[P["supplier"].astype(str) != ""]
        if len(P) == 0:
            return "unanswerable", {"reason": "no purchases in period"}
        if "nhiều nhất" in qn or "nhieu nhat" in qn or "chính" in qn or "chinh" in qn:
            g = P.groupby("supplier").size().sort_values(ascending=False)
        else:
            g = P.groupby("supplier")["amount"].sum().sort_values(ascending=False)
        return "string", g.index[0]

    # ---------------- debt
    if intent == "debt":
        v = M.debt_total(b, per)
        if v is None:
            return "unanswerable", {"reason": "no debt data"}
        return "number", v

    if intent == "payments_collected":
        v = M.payments_collected(b, per)
        if v is None:
            return "unanswerable", {"reason": "no payment data"}
        return "number", v

    # ---------------- profit
    if intent == "gross_profit":
        v = M.gross_profit(b, per)
        if v is None:
            return "unanswerable", {"reason": "no cost data"}
        return "number", v

    # ---------------- quantity by unit
    if intent == "qty_by_unit":
        if not unit:
            return "unanswerable", {"reason": "no unit specified"}
        v = M.qty_by_unit(b, per, unit)
        if v is None:
            return "unanswerable", {"reason": "no data"}
        return "number", v

    return "unanswerable", {"reason": f"intent {intent} not implemented"}


def _period_revenue(b, per):
    O = _orders_in(b, per)
    L = _lines_in(b, per)
    return _revenue_of(O, L)

def _previous_period_revenue(b, per, qn):
    """The comparison period for growth questions."""
    if "tháng trước" in qn or "thang truoc" in qn or "kỳ trước" in qn or "ky truoc" in qn:
        prev = per.start - pd.DateOffset(months=1)
        return _period_revenue(b, month_period(prev.month, prev.year))
    m = re.search(r"(?:so với|so voi)\s*(?:tháng|thang)\s*(\d{1,2})\s*(?:/|năm|nam|-)\s*(\d{4})", qn)
    if m:
        return _period_revenue(b, month_period(int(m.group(1)), int(m.group(2))))
    prev = per.start - pd.DateOffset(months=1)
    return _period_revenue(b, month_period(prev.month, prev.year))
