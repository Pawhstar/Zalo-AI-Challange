"""Compositional sales queries: filters x measure x answer shape.

A question is read as slots:
    period(s)  : periods.parse_time (main, compare, list of months)
    filters    : item, item group, size (M/L), shift (ca sáng/chiều), customer
                 group, payment method, sales channel, employee, prescription
                 drugs, active ingredient
    measure    : revenue | number of orders | quantity in a unit | average
                 order value | days / orders over a threshold | buyers
    shape      : value | share of the whole shop (%) | change vs a comparison
                 period (% or amount) | one value per month | two filters side
                 by side | filter vs baseline filter (%)

try_answer() returns (type, value) when every part of the question is
understood, otherwise None so the caller can fall back to other handlers.
"""
import re
import numpy as np
import pandas as pd

from datamate.fold import fold, normq
from datamate.periods import parse_time, Period, round_money, round2, round_half_up_money

# words that mean the question is about something this module does not handle
_OUT_OF_SCOPE = re.compile(
    r"\b(no|cong no|con thieu|chua tra|mua chiu|tra no|thu no|tuoi no|nhap|nha cung cap|ton|"
    r"trong kho|het hang|het han|han dung|giao(?! dich)|dot|chuyen hang|xe cho|tang gia|len gia|"
    r"giam gia|gia ban|gia von|lai gop|lai rong|loi nhat|lai nhat|loi nhuan|bi e|hang e|ban e|"
    r"khong ban|ban cham|nao|ai|bao hanh|tra gop|thu may|voucher|tich diem|dung diem|diem tich|"
    r"phi ship|phi giao|huy|tra hang|tra lai|lo hang|chi phi|ban chay|hot nhat|"
    r"cao nhat|thap nhat|nhieu nhat|it nhat|gio cao diem|co phai|dung khong|"
    r"tang lien tuc|giam lien tuc|trung thanh|sop|doi y|ua chuong|cham chi|dat khach|"
    r"thanh vien|dang ky|dia chi|so dien thoai|sinh nhat|tuoi|gioi tinh|quy men|khen|"
    r"le phep|luong|danh gia|yeu thich|hai long|gia trung binh|gia nhap)\b")

# ---------------------------------------------------------------- context

def _ctx(b):
    c = getattr(b, "_qctx", None)
    if c is not None:
        return c
    c = {}
    L = b.lines.copy() if len(b.lines) else pd.DataFrame()
    O = b.orders.copy() if len(b.orders) else pd.DataFrame()
    if len(O):
        O["day"] = pd.to_datetime(O["date"], errors="coerce").dt.normalize()
        if "revenue" not in O.columns:
            O["revenue"] = np.nan
    if len(L):
        L["day"] = pd.to_datetime(L["date"], errors="coerce").dt.normalize()
        # item attributes from the item list
        I = b.items
        grp, base = {}, {}
        if len(I):
            for nm, iid, g, bu in zip(I["item"], I.get("item_id", [""] * len(I)),
                                      I.get("group", [""] * len(I)), I.get("base_unit", [""] * len(I))):
                if nm:
                    grp[nm] = g
                    base[nm] = bu
        L["group"] = L["item"].map(grp).fillna("")
        bu = L["item"].map(base)
        if "base_unit" in L.columns:
            bu = bu.where(bu.notna() & (bu != ""), L["base_unit"])
        L["base_unit_i"] = bu.fillna("")
        # sale unit of a line whose quantity was not converted counts as base
        readme_base = getattr(b, "_readme_base_unit", {}) or {}
        miss = L["base_unit_i"] == ""
        if miss.any():
            L.loc[miss, "base_unit_i"] = L.loc[miss, "item"].map(readme_base).fillna(L.loc[miss, "unit"])
        L["size"] = L["item"].astype(str).str.extract(r"\(\s*([MLSml])\s*\)\s*$")[0].str.upper().fillna("")
        rx, ingr = _drug_info(b)
        L["rx"] = L["item"].map(rx)
        L["ingredient"] = L["item"].map(ingr)
        L["is_fee"] = L["item"].map(lambda s: fold(s).startswith("phi phuc vu"))
    # customer group per order
    cg = _customer_groups(b)
    if len(O):
        # the group written on the order itself (invoice column 'Nhóm khách
        # hàng') wins; otherwise look the customer up in the customer list
        own = O["cust_group"].fillna("").astype(str) if "cust_group" in O.columns \
            else pd.Series("", index=O.index)
        own = own.where(~own.str.strip().str.lower().isin(["nan", "none", "nat"]), "")
        if cg:
            key = O["customer_id"].fillna("").astype(str) if "customer_id" in O.columns else None
            g = key.map(cg) if key is not None else pd.Series(np.nan, index=O.index)
            g2 = O["customer"].map(lambda s: cg.get(fold(s))) if "customer" in O.columns else None
            if g2 is not None:
                g = g.where(g.notna(), g2)
            O["cust_group"] = own.where(own != "", g.fillna(""))
        else:
            O["cust_group"] = own
        cg = dict(cg)
        for v in O["cust_group"].unique():
            if v:
                cg.setdefault("__order__" + fold(v), v)
        if "walk_in" in O.columns:
            O.loc[O["walk_in"].fillna(False).astype(bool), "cust_group"] = ""
    c["L"], c["O"] = L, O
    c["factors"] = {(fold(i), fold(u)): f for (i, u), f in
                    (getattr(b, "_unit_factor", {}) or {}).items() if i and u}
    dates = O["day"].dropna() if len(O) else pd.Series(dtype="datetime64[ns]")
    c["dmin"] = dates.min() if len(dates) else None
    c["dmax"] = dates.max() if len(dates) else None
    groups = sorted({g for g in (b.items["group"] if len(b.items) and "group" in b.items else []) if g},
                    key=lambda s: -len(fold(s)))
    c["groups"] = groups
    c["cust_groups"] = sorted({v for v in cg.values() if v}, key=lambda s: -len(fold(s))) if cg else []
    b._qctx = c
    return c


def _drug_info(b):
    """item name -> prescription flag / active ingredient, from the drug list."""
    from datamate.loader import col, _readme_roles, _akey, norm
    rx, ingr = {}, {}
    idmap = getattr(b, "_item_name_by_id", {}) or {}
    names = set(b.items["item"]) if len(b.items) else set()
    for name, h in b._iter_tables():
        rr = _readme_roles(h)
        c_rx = c_in = None
        if rr:
            c_rx = (rr.get("rx") or [None])[0]
            c_in = (rr.get("ingredient") or [None])[0]
        for cname in h.columns:
            k = _akey(cname)
            if c_rx is None and ("kedon" in k or "bantheodon" in k):
                c_rx = cname
            if c_in is None and ("hoatchat" in k or "thanhphanchinh" in k):
                c_in = cname
        if c_rx is None and c_in is None:
            continue
        c_id = col(h, "item_id")
        c_nm = col(h, "item_name")
        for _, r in h.iterrows():
            nm = None
            if c_nm is not None and norm(r[c_nm]) in names:
                nm = norm(r[c_nm])
            elif c_id is not None:
                nm = idmap.get(norm(r[c_id]))
            if not nm:
                continue
            if c_rx is not None:
                v = fold(r[c_rx])
                rx[nm] = v in ("true", "1", "co", "x", "yes", "1.0", "ke don")
            if c_in is not None and r[c_in] is not None and str(r[c_in]).strip() not in ("", "nan", "None"):
                ingr[nm] = norm(r[c_in])
    return rx, ingr


def _customer_groups(b):
    C = b.customers
    out = {}
    if len(C) == 0 or "group" not in C.columns:
        return out
    for cid, nm, g in zip(C["customer_id"], C["name"], C["group"]):
        if not g:
            continue
        if cid:
            out[str(cid)] = g
        if nm:
            out[fold(nm)] = g
    return out

# ---------------------------------------------------------------- slots

_PAY = [("cash", r"tien mat|\btm\b|\bcash\b"), ("transfer", r"chuyen khoan|\bck\b|transfer|ngan hang"),
        ("ewallet", r"vi dien tu|\bvi\b|ewallet|momo|zalopay|e-wallet"), ("cod", r"\bcod\b|giao hang thu tien"),
        ("debt", r"ghi no|\bdebt\b")]
_CHAN = [("store", r"tai quay|tai tiem|tai cua hang|tai quan|truc tiep|\bstore\b|offline"),
         ("zalo", r"zalo"), ("phone", r"dien thoai|\bphone\b|goi dien"),
         ("marketplace", r"\bsan\b|tmdt|shopee|lazada|tiktok|marketplace|thuong mai dien tu"),
         ("facebook", r"facebook|\bfb\b|fanpage"), ("web", r"website|\bweb\b"),
         ("app", r"grab|shopeefood|baemin|gojek|app giao")]


def _canon(v, table):
    s = fold(v)
    for key, pat in table:
        if re.search(pat, s):
            return key
    return s


def _mentions(qn, table):
    """Filter values mentioned in the question, in the order they appear."""
    hits = []
    for key, pat in table:
        for m in re.finditer(pat, qn):
            hits.append((m.start(), key))
    hits.sort()
    out = []
    for _, k in hits:
        if k not in out:
            out.append(k)
    return out


def _threshold(qn):
    """'từ 9.800.000 đồng trở lên', '≥ 53.000.000', 'trên 500k' -> (value, inclusive)."""
    m = re.search(r"(tu|>=|≥|dat|it nhat|toi thieu|tren|qua|hon|lon hon|>)\s*([\d.,]+)\s*"
                  r"(trieu|tr|nghin|ngan|k|d|dong|vnd)?", qn)
    if not m:
        return None
    from datamate.loader import parse_num
    raw = m.group(2)
    unit = m.group(3) or ""
    v = parse_num(raw + ({"trieu": "tr", "tr": "tr", "nghin": "k", "ngan": "k", "k": "k"}.get(unit, "")))
    if v is None or pd.isna(v):
        return None
    incl = m.group(1) in ("tu", ">=", "≥", "dat", "it nhat", "toi thieu") or "tro len" in qn
    if m.group(1) in ("tren", "qua", "hon", "lon hon", ">") and "tro len" not in qn:
        incl = False
    return float(v), incl


def _parse(b, q, as_of):
    qn = normq(q)
    c = _ctx(b)
    S = {"qn": qn}
    # ---- filters
    F = {}
    # item group ('nhóm X' / 'các mặt hàng nhóm X'), not customer groups
    for g in c["groups"]:
        gf = fold(g)
        if re.search(r"\bnhom\s*(hang\s*)?(hoa\s*)?" + re.escape(gf) + r"\b", qn) or \
                re.search(r"\b(hang|mat hang|mon|do uong|thuoc)\s*" + re.escape(gf) + r"\b", qn):
            F["group"] = g
            break
    for g in c["cust_groups"]:
        gf = fold(g)
        if re.search(r"(khach|nhom)\s*(hang\s*)?(nhom\s*|thuoc nhom\s*)?" + re.escape(gf) + r"\b", qn):
            F["cust_group"] = g
            break
    if "group" not in F and re.search(r"\bnhom\b", qn) and "cust_group" not in F:
        S["unknown_group"] = True
    m = re.search(r"size\s*(m|l|s)\b|\(\s*(m|l)\s*\)", qn)
    if m and not S.get("item"):
        F["size"] = (m.group(1) or m.group(2)).upper()
    shifts = [m.group(1) for m in re.finditer(r"\bca (sang|chieu|toi)\b", qn)]
    if shifts:
        F["shift"] = shifts
    if re.search(r"ke don", qn):
        F["rx"] = not re.search(r"(khong|hong|hok|ko|ngoai|tru)\s*(thuoc\s*)?ke don|"
                                r"tru\s*thuoc ke don", qn)
        if re.search(r"tru thuoc ke don ra|ngoai thuoc ke don", qn):
            F["rx"] = False
    m = re.search(r"hoat chat\s+(.+?)\s+(thang|tuan|quy|nam|hom|ngay|tu|trong|ban|thu|da|co|la|\d)", qn + " ")
    if m:
        F["ingredient"] = m.group(1).strip()
    pays = _mentions(qn, _PAY)
    if pays and re.search(r"tra bang|thanh toan|hinh thuc|bang tien|tra qua|\btm\b|tien mat|chuyen khoan|cod|vi dien tu", qn):
        F["pay"] = pays
    chans = _mentions(qn, _CHAN)
    if chans and re.search(r"ban qua|ban tai|qua kenh|kenh|tai quay|ban truc tiep|dat qua|don qua", qn):
        F["channel"] = chans
    m = re.search(r"\bnv\s*0*(\d+)\b|nhan vien (?:ma )?([a-z]{0,3}\d+)", qn)
    if m:
        F["employee"] = m.group(0)
    elif re.search(r"\bnhan vien\b", qn):
        S["unknown_employee"] = True
    # named item (longest name of the shop's items found in the question)
    from datamate.intents import _extract_item_name
    it = _extract_item_name(q, b, fold(q))
    if it:
        F["item"] = it
        F.pop("size", None)
        F.pop("group", None)
    S["filters"] = F

    # ---- measure
    if re.search(r"(bao nhieu|may|so|dem|co)\s*ngay\b.*(tu|>=|≥|dat|tren|it nhat)\s*[\d.,]+", qn):
        S["measure"] = "days_over"
    elif re.search(r"(bao nhieu|may|so|dem)\s*(so\s*)?don(\s*hang)?\b.*(tu|>=|≥|dat|tren|it nhat)\s*[\d.,]+", qn):
        S["measure"] = "orders_over"
    elif re.search(r"khach mua tu (\d+) don", qn):
        S["measure"] = "buyers_min_orders"
    elif re.search(r"trung binh (mot|moi|tren mot|1)\s*(don|bill|hoa don)|gia tri trung binh|binh quan (mot|moi) don|"
                   r"(mot|moi) don trung binh", qn):
        S["measure"] = "aov"
    elif re.search(r"\b(may|bao nhieu|so|dem|tong so)\s*(so\s*)?(don|bill|hoa don|phieu)\b|so luong don", qn):
        S["measure"] = "orders"
    elif re.search(r"\b(bao nhieu|may|so|tong so)\s*khach\b", qn):
        S["measure"] = "buyers"
    else:
        unit = _unit_in(b, qn)
        if unit and not re.search(r"tien|doanh thu", qn):
            S["measure"], S["unit"] = "qty", unit
        elif re.search(r"tien|doanh thu|thu ve|thu duoc|ban duoc|ban dc|ban ra|mang ve", qn):
            S["measure"] = "revenue"
    # ---- shape
    if re.search(r"chiem|ti trong|ty trong|dong gop|phan cua|bang bao nhieu (phan tram|%)|"
                 r"tren tong|trong tong", qn) and re.search(r"%|phan tram|ti trong|ty trong|ti le", qn):
        S["shape"] = "share"
    elif S["filters"].get("shift") and len(S["filters"]["shift"]) >= 2 or \
            (len(S["filters"].get("pay", [])) >= 2) or (len(S["filters"].get("channel", [])) >= 2):
        if re.search(r"hon hay kem|tang hay giam|chenh|so voi", qn) and re.search(r"%|phan tram", qn):
            S["shape"] = "vs_pct"
        elif re.search(r"hon hay kem|chenh|hon bao nhieu|kem bao nhieu", qn):
            S["shape"] = "vs_diff"
        else:
            S["shape"] = "pair"
    else:
        S["shape"] = "value"
    return S


def _unit_in(b, qn):
    """'bao nhiêu ly', 'số lon', 'mấy viên' -> the unit, if the shop uses it."""
    units = set()
    if len(b.lines):
        units |= {fold(u) for u in b.lines["unit"].dropna().unique() if u}
    if len(b.items) and "base_unit" in b.items:
        units |= {fold(u) for u in b.items["base_unit"].dropna().unique() if u}
    for u in sorted(units, key=len, reverse=True):
        if not u or u in ("bao",) and re.search(r"bao nhieu", qn) and not re.search(r"(may|so|nhieu)\s*bao\b", qn):
            continue
        if re.search(r"(bao nhieu|may|so|tong so|tong cong)\s*" + re.escape(u) + r"\b", qn):
            return u
    return None

# ---------------------------------------------------------------- compute

def _apply_filters(c, F, p, as_of, valid=True):
    """Lines (or orders, for shops without lines) of the period after filters."""
    end = min(p.end, pd.Timestamp(as_of).normalize())
    L, O = c["L"], c["O"]
    use_lines = len(L) > 0
    if use_lines:
        X = L[(L["day"] >= p.start) & (L["day"] <= end)]
        if valid:
            X = X[X["valid"]]
    else:
        X = O[(O["day"] >= p.start) & (O["day"] <= end)]
        if valid:
            X = X[X["is_valid"]]
    if F.get("item"):
        if not use_lines:
            return None
        X = X[X["item"] == F["item"]]
    if F.get("group"):
        if not use_lines:
            return None
        X = X[X["group"].map(fold) == fold(F["group"])]
    if F.get("size"):
        if not use_lines:
            return None
        X = X[X["size"] == F["size"]]
    if "rx" in F:
        if not use_lines or X["rx"].isna().all() and c["L"]["rx"].isna().all():
            return None
        X = X[X["rx"].fillna(False).astype(bool) == F["rx"]]
    if F.get("ingredient"):
        if not use_lines:
            return None
        X = X[X["ingredient"].map(lambda s: fold(s) if isinstance(s, str) else "") == F["ingredient"]]
    if F.get("cust_group"):
        og = O.set_index("order_id")["cust_group"] if len(O) else None
        if og is None:
            return None
        g = X["order_id"].map(og) if use_lines else X["cust_group"]
        X = X[g.map(fold) == fold(F["cust_group"])]
    if F.get("employee"):
        e = F["employee"]
        m = re.search(r"(\d+)", e)
        col = X["employee"].fillna("").astype(str) if "employee" in X.columns else None
        if col is None or (col == "").all():
            return None
        X = X[col.str.extract(r"(\d+)")[0].fillna("-1").astype(int) == int(m.group(1))]
    return X


def _hour_of(X, c):
    if "hour" in X.columns and X["hour"].notna().any():
        return X["hour"]
    return None


def _by_shift(X, shift, c):
    h = _hour_of(X, c)
    if h is None:
        return None
    lo, hi = {"sang": (6, 13), "chieu": (14, 21), "toi": (18, 23)}[shift]
    return X[(h >= lo) & (h <= hi)]


def _by_attr(X, key, values, table, c):
    if key not in X.columns or X[key].fillna("").astype(str).eq("").all():
        return None
    v = X[key].map(lambda s: _canon(s, table))
    return X[v.isin(values)]


def _measure(X, S, c, use_lines):
    m = S["measure"]
    if X is None:
        return None
    if m == "revenue":
        return round_money(X["revenue"].fillna(0).sum())
    if m == "orders":
        return int(X["order_id"].nunique())
    if m == "qty":
        u = S["unit"]
        if not use_lines:
            return None
        F = S["filters"]
        if F.get("item"):
            q = X["qty_base"].where(X["qty_base"].notna(), X["qty"]).sum()
            LI = c["L"][c["L"]["item"] == F["item"]]
            base = fold(LI["base_unit_i"].iloc[0]) if len(LI) else ""
            if u != base:
                f = c["factors"].get((fold(F["item"]), u))
                if not f:
                    return None
                q = q / f
            return int(round(q)) if abs(q - round(q)) < 1e-9 else round2(q)
        Y = X[X["base_unit_i"].map(fold) == u]
        if len(Y) == 0:
            Y = X[X["unit"].map(fold) == u]
            return round2(Y["qty"].sum()) if len(Y) else 0
        q = Y["qty_base"].where(Y["qty_base"].notna(), Y["qty"])
        v = q.sum()
        return int(round(v)) if abs(v - round(v)) < 1e-9 else round2(v)
    if m == "aov":
        n = X["order_id"].nunique()
        if n == 0:
            return None
        return round_half_up_money(X["revenue"].fillna(0).sum() / n)
    if m == "buyers":
        O = c["O"]
        ids = X["order_id"].unique()
        Y = O[O["order_id"].isin(ids)]
        Y = Y[~Y.get("walk_in", pd.Series(False, index=Y.index)).fillna(False).astype(bool)]
        return int(Y["customer"].nunique())
    return None


def _value(b, S, p, as_of, filt=None):
    c = _ctx(b)
    F = dict(S["filters"])
    if filt:
        F.update(filt)
    X = _apply_filters(c, F, p, as_of)
    if X is None:
        return None
    use_lines = len(c["L"]) > 0
    if F.get("shift"):
        sh = F["shift"]
        if isinstance(sh, list):
            if len(sh) != 1:
                return None
            sh = sh[0]
        X = _by_shift(X, sh, c)
    for key, table, fk in (("payment_method", _PAY, "pay"), ("channel", _CHAN, "channel")):
        if F.get(fk):
            vals = F[fk] if isinstance(F[fk], list) else [F[fk]]
            if len(vals) != 1:
                return None
            X = _by_attr(X, key, vals, table, c)
    if X is None:
        return None
    return _measure(X, S, c, use_lines)


def _in_data(c, p, as_of):
    if c["dmin"] is None:
        return False
    hi = min(c["dmax"], pd.Timestamp(as_of).normalize())
    return not (p.end < c["dmin"] or p.start > hi)


LAST = {}

_RESID = (r"\bkhach (hang )?(nu|nam(?!\s*(nay|truoc|ngoai|sau|roi|\d))|o|tai|ben|quan|phuong|duong|dia chi|que)\b"
          r"|\bduong [a-z]+ [a-z]+|\bdia chi\b"
          r"|\b(bao nhieu|bnhiu|bao nheiu|nhieu|tat ca|tong cong)\s+(ly|coc|cai|chiec|hop|chai|lon|goi|thung|bich|"
          r"tui|kg|vi|vien|suat|to|dia|lit|cuon|tam|dien thoai)\b"
          r"|\bmay (ly|coc|cai|chiec|hop|chai|lon|goi|thung|bich|tui|kg|vi|vien|suat|to|lit|cuon|tam)\b"
          r"|\b(bao nhieu|bnhiu) may [a-z]|\bban (ra|duoc|dc) may (chiec|may|dien thoai)\b"
          r"|cat hang|nhap hang|lay hang|nhap ve|tien nhap|tien von|gia von|\bloi\b|\blai gop\b"
          r"|khach (phai|can) tra|thu may cu|tien coc|dat coc")


def _residual(q, qn):
    """A total-revenue reading of a question that still names something the
    router did not turn into a filter: a customer trait or address, a count
    of units, purchases, profit, an item name written after 'bán'."""
    if re.search(_RESID, qn):
        return True
    # 'bán Canh chua cá tràu được bao nhiêu tiền': a capitalised name after bán
    if re.search(r"\b(bán|ban)\s+(?!(được|đc|dc|ra|hàng|hang)\b)[A-ZĐÂĂÊÔƠƯÁÀẢÃẠÉÈÍÌÓÒÚÙÝ][^\s,?]*(\s+[^\s,?]+){0,6}?\s+(được|đc|dc|ra)\b", q):
        return True
    m = re.search(r"\b(mặt hàng|sản phẩm|món|sp|mat hang|san pham|mon)\s+\S", q, re.I)
    return bool(m) and not re.search(r"(mặt hàng|sản phẩm|món|sp|mat hang|san pham|mon)\s+(nào|nao|gì|gi)\b", q, re.I)


def tag_of(r):
    """Coarse category of the last answered question, for evaluation and the
    abstain policy: measure, answer shape, filter kinds, comparison."""
    S, ts = LAST.get("S"), LAST.get("ts")
    if not S or r is None:
        return None
    parts = [S.get("measure", "?"), S.get("shape", "?")]
    F = S.get("filters", {})
    parts.append("+".join(sorted(F)) or "nofilter")
    if not F and LAST.get("q") and S.get("measure") in ("revenue", "aov", "orders")             and _residual(LAST["q"], normq(LAST["q"])):
        parts.append("resid")
    if ts is not None:
        if ts.months:
            parts.append("months")
        elif ts.compare is not None:
            parts.append("cmp")
    parts.append(r[0])
    return "q:" + ":".join(parts)


def try_answer(b, q, as_of):
    LAST.clear()
    r = _try_answer(b, q, as_of)
    LAST["q"] = q
    return r


def _try_answer(b, q, as_of):
    qn = normq(q)
    if _OUT_OF_SCOPE.search(qn):
        return None
    c = _ctx(b)
    if len(c["O"]) == 0:
        return None
    S = _parse(b, q, as_of)
    LAST["S"] = S
    if "measure" not in S or S.get("unknown_group") or S.get("unknown_employee"):
        return None
    ts = parse_time(q, as_of)
    LAST["ts"] = ts
    if ts.kind in ("default", "until"):
        return None
    F = S["filters"]

    # ---- special measures
    if S["measure"] == "days_over":
        th = _threshold(qn)
        if th is None or not _in_data(c, ts.main, as_of):
            return None
        X = _apply_filters(c, F, ts.main, as_of)
        if X is None:
            return None
        daily = X.groupby("day")["revenue"].sum()
        v = int((daily >= th[0]).sum()) if th[1] else int((daily > th[0]).sum())
        return "number", v
    if S["measure"] == "orders_over":
        th = _threshold(qn)
        if th is None or not _in_data(c, ts.main, as_of):
            return None
        X = _apply_filters(c, F, ts.main, as_of)
        if X is None:
            return None
        per = X.groupby("order_id")["revenue"].sum()
        v = int((per >= th[0]).sum()) if th[1] else int((per > th[0]).sum())
        return "number", v
    if S["measure"] == "buyers_min_orders":
        m = re.search(r"khach mua tu (\d+) don", qn)
        n = int(m.group(1))
        if not _in_data(c, ts.main, as_of):
            return None
        X = _apply_filters(c, F, ts.main, as_of)
        O = c["O"]
        Y = O[O["order_id"].isin(X["order_id"].unique())]
        Y = Y[~Y.get("walk_in", pd.Series(False, index=Y.index)).fillna(False).astype(bool)]
        cnt = Y.groupby("customer")["order_id"].nunique()
        if len(cnt) == 0 or not re.search(r"%|phan tram", qn):
            return None
        return "percent", round2(100.0 * (cnt >= n).sum() / len(cnt))

    # ---- one value per month
    if ts.months and re.search(r"moi thang|tung thang|lien tiep|lien nhau|lan luot|liet ke|theo thu tu", qn) \
            and not re.search(r"cao nhat|thap nhat|nhieu nhat|it nhat|nao|co phai", qn):
        vals = []
        for mp in ts.months:
            if not _in_data(c, mp, as_of):
                return "unanswerable", {"reason": "month outside data"}
            vals.append(_value(b, S, mp, as_of))
        if any(v is None for v in vals):
            return None
        return "list", vals

    if not _in_data(c, ts.main, as_of):
        return "unanswerable", {"reason": "period outside the shop's data"}

    shape = S["shape"]
    if shape == "share":
        part = _value(b, S, ts.main, as_of)
        S2 = dict(S)
        S2["filters"] = {}
        whole = _value(b, S2, ts.main, as_of)
        if part is None or not whole:
            return None
        return "percent", round2(100.0 * part / whole)

    if shape in ("pair", "vs_pct", "vs_diff"):
        key = "shift" if len(F.get("shift", [])) >= 2 else "pay" if len(F.get("pay", [])) >= 2 else "channel"
        vals = F[key]
        if len(vals) != 2:
            return None
        v = [_value(b, S, ts.main, as_of, {key: [x]}) for x in vals]
        if any(x is None for x in v):
            return None
        if shape == "pair":
            return "list", v
        # 'ca chiều hơn hay kém ca sáng': the baseline is the one after 'so với'/'kém'
        a, base = v[0], v[1]
        if key == "shift" and "sang" in vals:
            a, base = v[vals.index("chieu")] if "chieu" in vals else v[0], v[vals.index("sang")]
        if shape == "vs_diff":
            return "number", round_money(a - base) if S["measure"] in ("revenue", "aov") else a - base
        if not base:
            return None
        return "percent", round2(100.0 * (a - base) / base)

    if ts.compare is not None:
        cur = _value(b, S, ts.main, as_of)
        if not _in_data(c, ts.compare, as_of):
            return "unanswerable", {"reason": "comparison period outside data"}
        prev = _value(b, S, ts.compare, as_of)
        if cur is None or prev is None:
            return None
        if re.search(r"%|phan tram|ti le", qn):
            if not prev:
                return None
            return "percent", round2(100.0 * (cur - prev) / prev)
        if re.search(r"bao nhieu|may|chenh", qn):
            d = cur - prev
            return "number", round_money(d) if isinstance(d, float) else d
        return None

    v = _value(b, S, ts.main, as_of)
    if v is None:
        return None
    return "number", v
