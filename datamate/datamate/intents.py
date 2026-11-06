"""Question -> intent router.

Questions are frequently typed without Vietnamese diacritics ("doanh thu hqua",
"ban duoc bao nhieu tien"), so all matching happens on an accent-folded,
lower-cased form of the question. Pattern lists stay readable in accented form
and are folded once at import time.
"""
import re
from datamate.periods import resolve_period, month_period, quarter_period, Period
from datamate.fold import fold, fold_list


# ---------------------------------------------------------------- helpers

def _has(s, *words):
    return any(w in s for w in words)


def _num_patterns(q):
    """Top-k mentions in the question."""
    for pat in (r"top\s*(\d+)", r"liet ke\s*(\d+)", r"(\d+)\s*(?:mat hang|hang|san pham|mon|khach|hoa don|don)\s*(?:ban chay nhat|dat nhat|chi tieu nhieu nhat|gia tri cao nhat|nhieu tien nhat)"):
        m = re.search(pat, q)
        if m:
            return int(m.group(1))
    # '3 mặt hàng nào bán chạy nhất', '5 khách nào mua nhiều tiền nhất'
    m = re.search(r"(?<![\d/.,])(\d{1,2})\s+(?:mat hang|san pham|mon|khach( hang)?|nhan vien|tho)"
                  r"\s+(?:nao|gi|mo|chi)\b.*\bnhat\b", q)
    if m and 2 <= int(m.group(1)) <= 20:
        return int(m.group(1))
    return None


def _extract_item_name(q, b, qf):
    """Find a product name mentioned in the question, matched against the
    business's item list (accent-insensitive, longest match wins)."""
    if b is None:
        return None
    items = []
    if len(b.items):
        items += list(b.items["item"])
    if len(b.lines):
        items += list(b.lines["item"])
    seen, uniq = set(), []
    for i in items:
        if i and i not in seen:
            seen.add(i)
            uniq.append(i)
    best = None
    for it in uniq:
        il = fold(it)
        if len(il) < 3:
            continue
        if il in qf:
            if best is None or len(il) > len(best[0]):
                best = (il, it)
    return best[1] if best else None


def _extract_customer(q, b, qf):
    names = set()
    if b is not None and len(b.orders):
        names |= {n for n in b.orders["customer"] if n}
    if b is not None and len(b.customers):
        names |= {n for n in b.customers["name"] if n}
    best = None
    for n in names:
        nl = fold(n)
        if len(nl) < 3:
            continue
        if nl in qf:
            if best is None or len(nl) > len(best[0]):
                best = (nl, n)
    return best[1] if best else None


def _extract_unit(q, b, qf):
    """Units actually asked about. The word 'bao' is ambiguous: it is the unit
    'pack/bag' but also the word in 'bao nhiêu' (how much), so 'bao' is only
    treated as a unit when it is NOT followed by 'nhiều/nhiu'."""
    units = set()
    if b is not None and len(b.units):
        units |= {u for u in b.units["unit"] if u}
    if b is not None and len(b.lines):
        units |= {u for u in b.lines["unit"] if u}
    if b is not None and len(b.items):
        units |= {u for u in b.items["base_unit"] if u}
    if getattr(b, "_readme_units", None):
        units |= set(b._readme_units)
    bao_nhiều = ("bao nhieu" in qf) or ("bao nhiêu" in qf)
    best = None
    for u in units:
        ul = fold(u)
        if len(ul) < 2:
            continue
        if ul == "bao" and bao_nhiều:
            continue
        if re.search(r"\b" + re.escape(ul) + r"\b", qf):
            if best is None or len(ul) > len(best[0]):
                best = (ul, u)
    return best[1] if best else None


def _extract_employee(q, b, qf):
    m = re.search(r"(?:nhan vien|ma nv|tho|nv)\s*(?:ma\s*)?([a-z]*\d+[a-z]*)", qf)
    return m.group(1) if m else None


# ---------------------------------------------------------------- keyword sets
# (accent-folded at import)

K = {
    "revenue": fold_list([
        "doanh thu", "dthu", "tien hang", "tien ban", "thu duoc bao nhieu",
        "ban duoc bao nhieu tien", "ban duoc tong cong bao nhieu tien",
        "cua hang ban duoc", "ban duoc nhieu tien", "tien thu duoc",
        "doanh thu cua cua hang", "tong doanh thu", "thu tien"]),
    "avg_order": fold_list([
        "trung binh", "binh quan", "moi don", "tren mot don", "mot don",
        "gia tri trung binh mot don", "doanh thu binh quan", "trung binh moi don"]),
    "growth": fold_list([
        "tang hay giam", "hon hay kem", "tang hay la giam", "tang hay giam may phan tram",
        "tang truong", "so voi thang truoc", "so voi ky truoc", "so voi thang lien truoc",
        "so voi thang lien truoc", "so voi nam truoc", "so voi cung ky",
        "so voi thang", "tang bao nhieu %", "phan tram so voi", "% so voi"]),
    "diff": fold_list([
        "hon bao nhieu", "chenh lech", "tang bao nhieu", "giam bao nhieu",
        "hon/kem", "chenh lech bao nhieu", "hieu bao nhieu", "chieu cao hon"]),
    "cancel": fold_list(["huy", "hủy", "hủy đơn", "hủy hàng", "bi huy", "cancel"]),
    "cancel_pct": fold_list(["ti le", "%", "phan tram", "bao nhieu %", "ti le don huy"]),
    "order_count": fold_list([
        "so don", "don hang", "may don", "bao nhieu don", "dem so don", "so bill",
        "so phieu", "bill", "hoa don", "so luong don"]),
    "n_orders": fold_list(["so don", "may don", "bao nhieu don", "dem so don",
                            "so bill", "so phieu"]),
    "best_day": fold_list([
        "ngay nao", "ngay nao do", "ngay nao ban duoc nhieu tien nhat",
        "ngay co doanh thu cao nhat", "doanh thu cao nhat", "ban duoc nhieu tien nhat",
        "ngay nao ban dat nhat", "ngay nao ban dc nhieu tien nhat",
        "ngay nao cua hang ban duoc nhieu tien nhat", "ngay ban dat nhat",
        "ngay nao co nhieu don nhat", "ngay nao ban duoc nhieu don nhat"]),
    "best_day_rev": fold_list([
        "nhieu tien nhat", "doanh thu cao nhat", "cao nhat", "nhieu nhat",
        "dat nhat", "ban nhieu tien nhat"]),
    "best_day_ord": fold_list(["nhieu don nhat", "don nhieu nhat", "nhieu don"]),
    "peak_hour": fold_list(["gio cao diem", "khung gio", "khung mot gio", "gio nao"]),
    "best_seller": fold_list([
        "ban chay", "ban duoc nhieu nhat", "ban nhieu nhat", "hot nhat", "ban chay nhat",
        "chay nhat", "mat hang nao ban", "hang nao chay nhat", "ban nhieu nhat",
        "duoc ua chuong nhat", "hang nao ban chay"]),
    "most_profitable": fold_list(["loi nhat", "lai nhat", "bien loi nhuan"]),
    "employee": fold_list(["nhan vien", "tho", "nv", "nguoi ban"]),
    "best_employee": fold_list([
        "ban gioi nhat", "nhieu tien nhat", "cham chi nhat", "nhieu ngay lam viec nhat",
        "lam nhieu nhat", "ban duoc nhieu tien nhat"]),
    "customer": fold_list(["khach"]),
    "top_customer": fold_list([
        "chi tieu nhieu nhat", "nhieu tien nhat", "mua nhieu nhat", "mua nhieu tien nhat",
        "khach mua nhieu tien nhat", "khach chi tieu nhieu nhat"]),
    "loyal": fold_list(["trung thanh nhat", "trung thanh"]),
    "big_spender": fold_list(["sop nhat"]),
    "changed_mind": fold_list(["doi y nhat", "hay doi y"]),
    "stock": fold_list(["ton kho", "con ton", "ton ", "giao hang ton"]),
    "stock_value": fold_list(["gia tri", "ton kho", "gia tri ton"]),
    "out_of_stock": fold_list(["het hang", "het hang cuoi ngay"]),
    "purchase": fold_list(["nhap hang", "phieu nhap", "nhap kho"]),
    "purchase_value": fold_list([
        "gia tri", "tong tien nhap", "tien nhap", "bao nhieu tien", "tong gia tri"]),
    "purchase_minus_sales": fold_list(["chenh", "nhap tru ban", "nhap truoc ban"]),
    "supplier": fold_list(["nha cung cap"]),
    "debt": fold_list([
        "cong no", "con no", "khach no", "tuoi no", "no phai thu", "tong cong no"]),
    "payments": fold_list(["tra no", "thu no", "no them", "thu duoc no"]),
    "profit": fold_list(["lai gop", "lai rong", "bien loi nhuan", "loi nhuan"]),
    "net_profit": fold_list(["lai rong", "loi nhuan rong"]),
    "qty_unit": fold_list(["ban duoc bao nhieu", "ban duoc tong cong bao nhieu"]),
    "price_on_day": fold_list(["gia ban", "gia ban mot", "gia bao nhieu",
                               "gia la bao nhieu", "bao nhieu mot", "ban mot"]),
    "avg_purchase_price": fold_list(["gia nhap binh quan", "gia von binh quan",
                                      "gia nhap binh qua"]),
    "delivery_rounds": fold_list(["giao nhieu dot", "so dot giao", "so dot"]),
    "expiring": fold_list(["het han"]),
    "prescription": fold_list(["ke don"]),
    "ingredient": fold_list(["hoat chat"]),
    "warranty": fold_list(["bao hanh"]),
    "special_sales": fold_list(["thu may cu", "tra gop"]),
    "voucher": fold_list(["voucher", "phi ship", "giam voucher"]),
    "monotonic": fold_list(["tang lien tuc", "giam lien tuc"]),
    "boolean": fold_list(["co phai", "co khong", "dung khong", "co khong"]),
    "customer_bought": fold_list(["khach da mua", "khach mua", "khach hang da mua"]),
    "payment_method": fold_list(["theo hinh thuc", "hinh thuc thanh toan",
                                  "tien mat", "chuyen khoan", "cod"]),
    "customer_group": fold_list(["nhom khach", "theo nhom"]),
    "paid_cash_shift": fold_list(["bao cao tien mat theo ca", "theo ca"]),
}

# intents that need a period but no explicit month are relative -> resolved later


def classify(q, as_of, b=None):
    """Return (intent, params dict).

    Order matters: more specific patterns are tested first, so a question that
    mentions both a metric word and a qualifier ("doanh thu ... tăng hay giảm")
    lands on the qualifier.
    """
    qf = fold(q)
    p = {"q": q, "as_of": as_of, "ql": qf}

    item = _extract_item_name(q, b, qf)
    cust = _extract_customer(q, b, qf)
    unit = _extract_unit(q, b, qf)
    emp = _extract_employee(q, b, qf)
    topk = _num_patterns(qf)
    if item:
        p["item"] = item
    if cust:
        p["customer"] = cust
    if unit:
        p["unit"] = unit
    if emp:
        p["employee"] = emp
    if topk:
        p["topk"] = topk

    # ---- monotonic series
    if _has(qf, *K["monotonic"]):
        p["metric"] = "monotonic_growth"
        return "monotonic", p

    # ---- growth / difference (these also contain revenue words)
    if _has(qf, *K["growth"]):
        p["metric"] = "rev_growth_pct"
        return "rev_growth_pct", p
    if _has(qf, *K["diff"]):
        p["metric"] = "rev_diff"
        return "rev_diff", p

    # ---- best day (also mentions 'doanh thu')
    if _has(qf, *K["best_day"]):
        p["metric"] = "best_day"
        p["by"] = "orders" if (_has(qf, *K["best_day_ord"])
                               and not _has(qf, "nhieu tien nhat")) else "revenue"
        return "best_day", p

    # ---- cancelled orders (mentions 'đơn')
    if _has(qf, *K["cancel"]):
        if _has(qf, *K["cancel_pct"]):
            p["metric"] = "cancel_rate"
            return "cancel_rate", p
        p["metric"] = "n_orders_cancelled"
        return "n_orders_cancelled", p

    # ---- order counts (mentions 'đơn' too)
    if _has(qf, *K["n_orders"]) and not _has(qf, "hang nao", "mat hang nao"):
        p["metric"] = "n_orders_valid"
        return "n_orders_valid", p

    # ---- customer rankings
    if _has(qf, *K["customer"]):
        if _has(qf, *K["loyal"]):
            p["metric"] = "most_loyal"
            return "most_loyal", p
        if _has(qf, *K["big_spender"]):
            p["metric"] = "biggest_spender_avg"
            return "biggest_spender_avg", p
        if _has(qf, *K["changed_mind"]):
            p["metric"] = "most_changed_mind"
            return "most_changed_mind", p
        if _has(qf, *K["customer_bought"]):
            p["metric"] = "n_customers_bought"
            return "n_customers_bought", p
        if _has(qf, *K["top_customer"]):
            p["metric"] = "top_customers"
            if topk and topk > 1:
                return "top_customers", p
            return "top_customer", p

    # ---- employee ranking
    if _has(qf, *K["employee"]) and _has(qf, *K["best_employee"]):
        p["metric"] = "best_employee"
        return "best_employee", p

    # ---- best seller / most profitable (may mention revenue)
    if _has(qf, *K["best_seller"]):
        p["metric"] = "best_seller"
        if topk and topk > 1:
            return "top_sellers", p
        return "best_seller", p
    if _has(qf, *K["most_profitable"]):
        p["metric"] = "most_profitable"
        if topk and topk > 1:
            return "top_profitable", p
        return "most_profitable", p

    # ---- quantity of a named item in a unit ("bán ra bao nhiu kg Nếp", "số kg X")
    # Fires when the question names BOTH an item and a data-unit, asks a quantity
    # ("bao nhiu" / "may" / "số" / "bán ra"), and is NOT about money ("tiền"/"doanh thu").
    if item and unit:
        money = _has(qf, "tien", "doanh thu", "dthu", "gia ban", "thu ve", "thu duoc")
        qtyword = _has(qf, "bao nhiu", "may", "số", "so ", "ban ra", "ban dc",
                        "ban duoc", "ban duoc tong cong", "ban dc tong cong")
        if qtyword and not money:
            p["metric"] = "qty_of_item"
            return "qty_of_item", p

    # ---- unit price on a specific day ("giá bán ... ngày 25/09/2025")
    if _has(qf, *K["price_on_day"]) and _has(qf, "ngay"):
        p["metric"] = "price_on_day"
        return "price_on_day", p

    # ---- revenue
    if _has(qf, *K["revenue"]):
        if _has(qf, *K["avg_order"]):
            p["metric"] = "avg_order_value"
            return "avg_order_value", p
        if _has(qf, *K["payment_method"]):
            p["metric"] = "revenue"
            p["group_by"] = "payment_method"
            return "revenue_grouped", p
        if _has(qf, *K["customer_group"]):
            p["metric"] = "revenue"
            p["group_by"] = "customer_group"
            return "revenue_grouped", p
        p["metric"] = "revenue"
        return "revenue", p

    # ---- quantity by unit (no item named)
    if _has(qf, *K["qty_unit"]) and unit:
        p["metric"] = "qty_by_unit"
        return "qty_by_unit", p

    # ---- peak hour
    if _has(qf, *K["peak_hour"]):
        p["metric"] = "peak_hour"
        return "peak_hour", p

    # ---- stock / purchase / debt / profit
    if _has(qf, *K["purchase"]):
        if _has(qf, *K["purchase_minus_sales"]):
            p["metric"] = "purchase_minus_sales"
            return "purchase_minus_sales", p
        if _has(qf, "gia tri", "tong tien nhap", "tien nhap", "nhap duoc bao nhieu tien"):
            p["metric"] = "purchase_value"
            return "purchase_value", p
        p["metric"] = "purchase_qty"
        return "purchase_qty", p

    if _has(qf, *K["supplier"]):
        p["metric"] = "top_supplier"
        return "top_supplier", p

    if _has(qf, *K["stock"]):
        if _has(qf, *K["out_of_stock"]):
            p["metric"] = "out_of_stock"
            return "out_of_stock", p
        if _has(qf, "gia tri"):
            p["metric"] = "stock_value"
            return "stock_value", p
        p["metric"] = "stock_qty"
        return "stock_qty", p

    if _has(qf, *K["debt"]):
        p["metric"] = "debt"
        return "debt", p

    if _has(qf, *K["payments"]):
        p["metric"] = "payments_collected"
        return "payments_collected", p

    if _has(qf, *K["profit"]):
        if _has(qf, *K["net_profit"]):
            p["metric"] = "net_profit_month"
            return "net_profit_month", p
        p["metric"] = "gross_profit"
        return "gross_profit", p

    if _has(qf, *K["avg_purchase_price"]):
        p["metric"] = "avg_purchase_price"
        return "avg_purchase_price", p

    if _has(qf, *K["delivery_rounds"]):
        p["metric"] = "delivery_rounds"
        return "delivery_rounds", p

    if _has(qf, *K["expiring"]):
        p["metric"] = "expiring_stock"
        return "expiring_stock", p

    if _has(qf, *K["prescription"]):
        p["metric"] = "prescription_ratio"
        return "prescription_ratio", p

    if _has(qf, *K["ingredient"]):
        p["metric"] = "revenue_by_ingredient"
        return "revenue_by_ingredient", p

    if _has(qf, *K["warranty"]):
        p["metric"] = "warranty_rate"
        return "warranty_rate", p

    if _has(qf, *K["special_sales"]):
        p["metric"] = "special_sales"
        return "special_sales", p

    if _has(qf, *K["voucher"]):
        p["metric"] = "voucher"
        return "voucher", p

    p["metric"] = "revenue"
    return "revenue", p
