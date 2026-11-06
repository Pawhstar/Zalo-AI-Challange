"""Purchases (rulebook §5): receipt value in a period, average purchase price
of an item, top supplier.

Receipts come either as one table (a hand-kept book: one row per purchased
line with the receipt code, date, supplier, item...) or as a receipt header
table plus a receipt-line table joined by the receipt code (PN..).
"""
import re
import numpy as np
import pandas as pd

from datamate.fold import fold, normq
from datamate.periods import parse_time, round_money


def _build(b):
    c = getattr(b, "_pur_ctx", "x")
    if c != "x":
        return c
    from datamate.loader import col, col_ex, norm, parse_num, _id_columns, _readme_roles, classify_status
    idmap = getattr(b, "_item_name_by_id", {}) or {}
    names = set(b.items["item"]) if len(b.items) else set()
    sales = getattr(b, "sales_sheets", set())
    headers, details = [], []
    for name, h in b._iter_tables(skip=sales):
        ids = _id_columns(h)
        rr = _readme_roles(h)
        c_rid = col(h, "receipt_id")
        if c_rid is None:
            pn = [k for k, v in ids.items() if v == "PN"]
            c_rid = pn[0] if pn else None
        if c_rid is None:
            continue
        if any(v == "ORD" for v in ids.values()):      # a sales table that mentions receipts
            continue
        c_item = col(h, "recv_item") or col(h, "item_name")
        c_iid = col(h, "item_id")
        if c_iid is None:
            sp = [k for k, v in ids.items() if v == "SP"]
            c_iid = sp[0] if sp else None
        c_qty = col(h, "recv_qty") or col(h, "qty")
        c_date = col(h, "recv_date") or col(h, "date")
        if c_date is None:
            for cn in h.columns:
                if re.search(r"ngay|thoigian|nhapkho|date", re.sub(r"[^a-z]", "", fold(cn))) and \
                        not re.search(r"han|hsd|sinh", fold(cn)):
                    c_date = cn
                    break
        if (c_item or c_iid) and c_qty:
            details.append((name, h, c_rid, c_item, c_iid, c_qty, c_date))
        elif c_date:
            headers.append((name, h, c_rid, c_date))
    if not details:
        b._pur_ctx = None
        return None
    # the line table with the most rows
    name, h, c_rid, c_item, c_iid, c_qty, c_date = max(details, key=lambda d: len(d[1]))
    L = pd.DataFrame()
    L["receipt"] = h[c_rid].map(norm)
    item = h[c_item].map(norm) if c_item else pd.Series("", index=h.index)
    if c_iid:
        by_id = h[c_iid].map(norm).map(idmap)
        item = item.where(item.isin(names) | by_id.isna(), by_id)
    L["item"] = item
    L["qty"] = h[c_qty].map(parse_num)
    c_unit = col(h, "unit")
    L["unit"] = h[c_unit].map(norm) if c_unit else ""
    c_price = col(h, "recv_price") or col(h, "unit_price")
    L["price"] = h[c_price].map(parse_num) if c_price else np.nan
    c_amt = col(h, "recv_amt")
    if c_amt is None and _readme_roles(h) is None:
        c_amt = col(h, "line_amt")
    L["amount"] = h[c_amt].map(parse_num) if c_amt else np.nan
    L["amount"] = L["amount"].where(L["amount"].notna(), L["qty"] * L["price"])
    L["date"] = b._dates(h, c_date, None) if c_date else pd.NaT
    c_sup = col(h, "supplier")
    L["supplier"] = h[c_sup].map(norm) if c_sup else ""
    c_st = col(h, "status")
    L["status"] = h[c_st].map(classify_status) if c_st else ""
    c_tot = col(h, "recv_total")
    L["rtotal"] = h[c_tot].map(parse_num) if c_tot else np.nan
    # header table: date, supplier, status, receipt total
    hdr = [x for x in headers if x[0] != name]
    if hdr:
        hn, hh, h_rid, h_date = max(hdr, key=lambda d: hh_overlap(d, L))
        H = pd.DataFrame({"receipt": hh[h_rid].map(norm)})
        H["date"] = b._dates(hh, h_date, None)
        c_sup = col(hh, "supplier")
        H["supplier"] = hh[c_sup].map(norm) if c_sup else ""
        c_st = col(hh, "status")
        H["status"] = hh[c_st].map(classify_status) if c_st else ""
        c_tot = col(hh, "recv_total")
        if c_tot is None:
            for cn in hh.columns:
                k = re.sub(r"[^a-z]", "", fold(cn))
                if re.search(r"tong|cantra|giatri|thanhtien", k):
                    c_tot = cn
                    break
        H["rtotal"] = hh[c_tot].map(parse_num) if c_tot else np.nan
        H = H.drop_duplicates("receipt").set_index("receipt")
        for k in ("date", "supplier", "status", "rtotal"):
            v = L["receipt"].map(H[k])
            if k == "date":
                L[k] = pd.to_datetime(L[k], errors="coerce")
                L[k] = L[k].where(L[k].notna(), v)
            else:
                cur = L[k]
                empty = cur.isna() | (cur.astype(str) == "")
                L[k] = cur.where(~empty, v)
    L["day"] = pd.to_datetime(L["date"], errors="coerce").dt.normalize()
    L["supplier"] = L["supplier"].map(lambda s: _supplier_name(b, s))
    L["cancelled"] = L["status"].astype(str) == "cancelled"
    b._pur_ctx = L
    return L


def hh_overlap(d, L):
    try:
        return d[1][d[2]].isin(set(L["receipt"])).mean()
    except Exception:
        return 0


def _supplier_name(b, s):
    m = getattr(b, "_sup_names", None)
    if m is None:
        from datamate.loader import col, norm, _id_columns
        m = {}
        for name, h in b._iter_tables():
            ids = _id_columns(h)
            ncc = [k for k, v in ids.items() if v == "NCC"]
            if not ncc or len(ids) > 1:
                continue
            for cn in h.columns:
                if cn in ncc:
                    continue
                vals = h[cn].dropna().astype(str)
                if len(vals) and vals.str.contains(r"[A-Za-zÀ-ỹ]{2,}\s").mean() > 0.8:
                    m.update(dict(zip(h[ncc[0]].map(norm), h[cn].map(norm))))
                    break
        b._sup_names = m
    return m.get(s, s)


def try_answer(b, q, as_of):
    qn = normq(q)
    if not re.search(r"\bnhap|nha cung cap", qn):
        return None
    if re.search(r"tru|chenh|ban ra|so ban", qn):
        return None
    L = _build(b)
    T = pd.Timestamp(as_of).normalize()
    ts = parse_time(q, as_of)
    if L is None:
        return None
    if ts.kind in ("default", "until"):
        return None
    p = ts.main.clip(T)
    X = L[(L["day"] >= p.start) & (L["day"] <= p.end) & ~L["cancelled"]]
    dmin, dmax = L["day"].min(), L["day"].max()
    if pd.isna(dmin) or p.end < dmin or p.start > min(dmax, T):
        return "unanswerable", {"reason": "period outside purchase data"}

    # average purchase price of one item, per purchase unit
    if re.search(r"binh quan|trung binh", qn):
        from datamate.intents import _extract_item_name
        it = _extract_item_name(q, b, fold(q))
        if not it:
            return None
        Y = X[X["item"] == it]
        m = re.search(r"(mot|1|moi)\s+([a-z0-9]+)", qn)
        unit = m.group(2) if m else None
        if unit and (Y["unit"].map(fold) == unit).any():
            Y = Y[Y["unit"].map(fold) == unit]
        if len(Y) == 0 or Y["qty"].sum() == 0:
            return None
        return "number", round_money(Y["amount"].sum() / Y["qty"].sum())

    # top supplier
    if re.search(r"nha cung cap", qn) and re.search(r"nao|ai", qn):
        Y = X[X["supplier"].astype(str) != ""]
        if len(Y) == 0:
            return None
        if re.search(r"nhieu phieu|so phieu|chinh", qn) and not re.search(r"tien", qn):
            g = Y.groupby("supplier")["receipt"].nunique()
        else:
            g = _receipt_values(Y).groupby("supplier")["value"].sum()
        g = g.sort_index().sort_values(ascending=False, kind="stable")
        return "string", g.index[0]

    # total purchase value
    if re.search(r"tien|gia tri|bao nhieu", qn) and not re.search(r"\b(so luong|may|bao nhieu)\s+(hop|thung|goi|chai|cai|vien|kg|bao|cay)\b", qn):
        return "number", round_money(_receipt_values(X)["value"].sum())
    return None


def _receipt_values(X):
    """Value per receipt: the receipt total when the shop records one, else the
    sum of its lines."""
    g = X.groupby("receipt").agg(value=("amount", "sum"), rtotal=("rtotal", "first"),
                                 supplier=("supplier", "first"))
    g["value"] = g["rtotal"].where(g["rtotal"].notna(), g["value"])
    return g
