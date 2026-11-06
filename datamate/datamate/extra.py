"""Question kinds the older router sent to its 'revenue' fallback.

  * trap: a judgement the books cannot hold (khó tính, lễ phép, thân thiện,
    trung thực, quý mến...) -> unanswerable (rulebook §7)
  * top customer by number of orders ('khách nào mua nhiều đơn nhất')
    (rulebook §1 số đơn, §3 xác định khách)
  * number of items present in at least N orders ('có mặt trong ít nhất N
    đơn', 'từ N đơn trở lên')
  * the month with the highest / lowest revenue among the months asked

Each answer carries its own tag 'x:<kind>:<type>'.
"""
import re
import pandas as pd

from datamate.fold import fold, normq
from datamate.periods import parse_time, Period, month_period

# personal judgements no sales book records. 'nhiệt tình' is left out on
# purpose: it may also be asked as a synonym of 'chăm chỉ' (most working days)
_TRAIT = (r"kho tinh|le phep|chu dao|quy men|than thien|trung thuc|vui ve|lich su|"
          r"de thuong|tot bung|hien lanh|tu te|de chiu|dang tin|chat luong tot|chat luong nhat|"
          r"phuc vu .*(tot|than thien)|ngon nhat")


def _has_codes(O):
    return "customer_id" in O.columns and (O["customer_id"].fillna("").astype(str) != "").mean() > 0.05


def _named(O):
    """Orders of identified customers (rulebook §3: walk-ins are no customer)."""
    O = O[~O.get("walk_in", pd.Series(False, index=O.index)).fillna(False).astype(bool)]
    if _has_codes(O):
        O = O[O["customer_id"].fillna("").astype(str) != ""]
        key = O["customer_id"].astype(str)
    else:
        O = O[O["customer"].fillna("").astype(str) != ""]
        key = O["customer"].astype(str)
    return O, key


def try_trap(b, q, as_of):
    """Runs before every other module: a judgement no book records."""
    if re.search(_TRAIT, normq(q)):
        return "unanswerable", {"reason": "the data records no such judgement"}, "x:trait:unanswerable"
    return None


def try_answer(b, q, as_of):
    qn = normq(q)
    O = b.orders
    if len(O) == 0:
        return None
    ts = parse_time(q, as_of)
    if ts.kind in ("default", "until") or ts.main is None:
        return None
    T = pd.Timestamp(as_of).normalize()
    p = ts.main.clip(T)
    day = pd.to_datetime(O["date"], errors="coerce").dt.normalize()
    X = O[(day >= p.start) & (day <= p.end) & O["is_valid"].fillna(False).astype(bool)]

    # ---- customer with the most orders
    if re.search(r"(khach|ai)\b.*\bnhieu (don|lan)( hang)?( mua)? nhat|mua nhieu (don|lan) nhat", qn) and \
            not re.search(r"tien|doanh thu|dthu|huy", qn):
        if "customer" not in O.columns:
            return None
        Y, key = _named(X)
        if len(Y) == 0:
            Y0, _ = _named(O)
            if len(Y0) == 0:
                return "unanswerable", {"reason": "the shop records no customers"}, "x:top_cust_orders:unanswerable"
            return None
        cnt = Y.groupby(key)["order_id"].nunique()
        best = cnt.max()
        top = sorted(k for k, v in cnt.items() if v == best)[0]
        name = Y.loc[key == top, "customer"].iloc[0] if _has_codes(Y) else top
        return "string", name, "x:top_cust_orders:string"

    # ---- items present in at least N orders
    m = re.search(r"(?:it nhat|tu)\s*(\d+)\s*(?:don|hoa don|bill)(?:\s*hang)?(?:\s*khac nhau)?(?:\s*tro len)?", qn)
    if m and re.search(r"mat hang|san pham|\bmon\b|\bhang\b", qn) and \
            re.search(r"co mat|xuat hien|nam trong|gop mat|duoc mua|duoc goi|\bgoi\b|\bo\b|\btrong\b", qn) and \
            re.search(r"bao nhieu|may|bnhiu|dem|so (mat hang|san pham|mon)", qn):
        n = int(m.group(1))
        if re.search(r"(?:it nhat|tu)\s*" + m.group(1), qn) is None:
            return None
        L = b.lines
        if len(L) == 0:
            return None
        ld = pd.to_datetime(L["date"], errors="coerce").dt.normalize()
        Z = L[(ld >= p.start) & (ld <= p.end) & L["valid"].fillna(False).astype(bool)]
        if "non_goods" in Z.columns:
            Z = Z[~Z["non_goods"].fillna(False).astype(bool)]
        Z = Z[~Z["item"].fillna("").astype(str).map(fold).str.startswith("phi phuc vu")]
        Z = Z[Z["item"].fillna("").astype(str) != ""]
        per = Z.groupby("item")["order_id"].nunique()
        return "number", int((per >= n).sum()), "x:items_min_orders:number"

    # ---- month with the highest / lowest revenue
    if re.search(r"thang nao", qn) and re.search(r"(cao|nhieu|thap|it)( tien)? nhat", qn):
        from datamate import metrics
        months = ts.months or []
        if not months:
            months = []
            s = pd.Timestamp(p.start.year, p.start.month, 1)
            while s <= p.end:
                months.append(month_period(s.month, s.year))
                s = s + pd.DateOffset(months=1)
        if len(months) < 2:
            return None
        vals = [(metrics.total_revenue(b, Period(mp.start, min(mp.end, T))), mp.start) for mp in months]
        low = re.search(r"(thap|it)( tien)? nhat", qn)
        best = min(vals, key=lambda x: (x[0], x[1])) if low else max(vals, key=lambda x: (x[0], -x[1].value))
        return "date", best[1].strftime("%Y-%m"), "x:best_month:date"
    return None
