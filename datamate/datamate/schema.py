"""README-driven column roles.

Every business README lists its columns as
    ## Cột trong `File.xlsx`[, sheet `Sheet`]
    - **<column header>**: <description>
The column headers are deliberately scrambled across shops ("Tên SP", "Số CT",
"ID SP"...), but the descriptions come from a small, fixed vocabulary
("mã đơn", "thành tiền sau giảm", "số lượng đã đổi ra đơn vị cơ bản"...).
Mapping descriptions -> roles is therefore far more reliable than guessing from
header names; the header-name vocabulary in loader.COL is only the fallback for
shops whose README has no column section.
"""
import re

from datamate.fold import fold


def _key(s):
    """Accent-insensitive, punctuation-free key (same as loader._akey)."""
    return re.sub(r"[^a-z0-9]", "", fold(s))


# (regex on the folded description, roles). First match wins, so the more
# specific descriptions come first.
_RULES = [
    (r"^cot trong", []),
    (r"so thu tu dong", ["line_no"]),
    (r"so thu tu don", ["order_id"]),
    (r"^(ma don|so hoa don|ma hoa don)", ["order_id", "pay_oid"]),
    (r"^ma phieu nhap", ["receipt_id"]),
    (r"^ma phieu thu", ["pay_id"]),
    (r"^ma phieu tra", ["return_id"]),
    (r"^(ma hang|ma sku|ma san pham)", ["item_id"]),
    (r"^ma khach", ["cust_id"]),
    (r"^(ma nha cung cap|nha cung cap)", ["supplier"]),
    (r"^(ma nhan vien|nhan vien|tho lam|ho ten tho)", ["employee"]),
    (r"^ten khach", ["cust_name"]),
    (r"^(ten hang|hang ban|ten mon|ten san pham)", ["item_name", "recv_item"]),
    (r"^ten$", ["_name"]),
    (r"so luong da doi ra don vi co ban|so luong ban lay tu lo"
     r"|so luong nhap \(don vi co ban\)", ["qty_base"]),
    (r"^so luong khach tra lai", ["return_qty"]),
    (r"^so luong nhap", ["recv_qty", "qty"]),
    (r"^so luong", ["qty", "recv_qty"]),
    (r"^don vi co ban", ["base_unit", "unit"]),
    (r"^don vi lon", ["big_unit"]),
    (r"^(don vi tinh|don vi nhap)", ["unit"]),
    (r"^he so", ["factor"]),
    (r"^thoi diem dat don", ["_datetime", "hour"]),
    (r"^ngay ban", ["date"]),
    (r"^gio dat don", ["hour"]),
    (r"^ngay nhap", ["recv_date"]),
    (r"^thoi diem thu", ["pay_date"]),
    (r"^ngay giao", ["ship_date"]),
    (r"^ngay bat dau ap dung", ["price_date"]),
    (r"^han su dung", ["expiry"]),
    (r"^han thanh toan", ["due_date"]),
    (r"^gia nhap", ["recv_price"]),
    (r"^don gia", ["unit_price", "recv_price"]),
    (r"^(thanh tien sau giam|thanh tien cua dong)", ["line_amt"]),
    (r"^tien nhap cua ca dong", ["recv_amt"]),
    (r"^(tong tien phieu|tong tien cua ca phieu|tong tien ca phieu)", ["recv_total"]),
    (r"^trang thai phieu nhap", ["status"]),
    (r"^trang thai don", ["status"]),
    (r"^ghi chu cua don; (don huy|don khach tra)", ["status"]),
    (r"^(giam gia cua ca don|tien bot cho ca don)", ["order_disc"]),
    (r"^tien giam cua ca dong", ["line_disc"]),
    (r"^giam gia$", ["line_disc", "order_disc"]),
    (r"^(tong tien hang|tien hang cua don)", ["order_goods"]),
    (r"^(tong tien don|so khach phai tra cho ca don|khach can tra cho ca don"
     r"|so tien khach tra cho ca don)", ["order_total"]),
    (r"^(da thanh toan|khach da tra cho ca don)", ["paid"]),
    (r"con no", ["debt"]),
    (r"^kenh ban", ["channel"]),
    (r"^hinh thuc thanh toan", ["pay_method"]),
    (r"^gia von", ["cost", "cost_item"]),
    (r"^gia ban", ["sale_item"]),
    (r"^nhom hang", ["group"]),
    # a customer group is never an item group: 'nhóm khách' only maps to
    # cust_group (it used to also claim 'group', so an invoice table carrying
    # both columns could read the customer group as the item group)
    (r"^nhom khach", ["cust_group"]),
    (r"^ton kho", ["stock_qty"]),
    (r"^so tien$", ["pay_amt"]),
    (r"^so lo", ["lot"]),
    (r"^phi giao", ["delivery"]),
    (r"^hoat chat", ["ingredient"]),
    (r"^thuoc ke don", ["rx"]),
    (r"^ghi chu", ["note"]),
]
_RULES = [(re.compile(p), r) for p, r in _RULES]


def desc_roles(desc):
    d = fold(desc)
    for rx, roles in _RULES:
        if rx.search(d):
            return list(roles)
    return []


_SECTION = re.compile(r"^#+\s*Cột trong\s+`([^`]+)`(?:\s*,\s*sheet\s+`([^`]+)`)?", re.I)
_ITEM = re.compile(r"^-\s+\*\*(.+?)\*\*\s*:\s*(.*)$")


def parse_readme(readme):
    """-> list of sections: {"file", "sheet", "cols": {header_key: (header, desc)}}."""
    out, cur = [], None
    for line in (readme or "").splitlines():
        line = line.rstrip()
        m = _SECTION.match(line.strip())
        if m:
            cur = {"file": m.group(1), "sheet": m.group(2), "cols": {}}
            out.append(cur)
            continue
        if line.startswith("#"):
            cur = None
            continue
        if cur is None:
            continue
        m = _ITEM.match(line.strip())
        if m:
            cur["cols"][_key(m.group(1))] = (m.group(1), m.group(2))
    return [s for s in out if s["cols"]]


def roles_for(sections, columns, table_name=""):
    """role -> [column, ...] for a table, from the README section whose columns
    best overlap the table's. Returns None when no section fits."""
    keys = {_key(c): c for c in columns}
    # A section fits a table when (nearly) all the columns it documents are in
    # the table; READMEs often skip a table's empty or irrelevant columns.
    best, best_score = None, 0.0
    for s in sections:
        n = len(set(s["cols"]) & set(keys))
        if n < 2 or n < 0.8 * len(s["cols"]):
            continue
        score = n + n / len(s["cols"])
        if score > best_score:
            best, best_score = s, score
    if best is None:
        return None
    roles = {}
    descs = {}
    for k, c in keys.items():
        if k not in best["cols"]:
            continue
        desc = best["cols"][k][1]
        descs[c] = fold(desc)
        for r in desc_roles(desc):
            roles.setdefault(r, []).append(c)
    # "tên" is the item name in a product list, the customer name in a customer list
    if "_name" in roles:
        tgt = "cust_master" if ("cust_id" in roles and "item_id" not in roles) else "item_name"
        for c in roles.pop("_name"):
            roles.setdefault(tgt, []).append(c)
            if tgt == "item_name":
                roles.setdefault("recv_item", []).append(c)
    # order date: a plain sale date wins over an order timestamp
    if "_datetime" in roles:
        dt = roles.pop("_datetime")
        if "date" not in roles:
            roles["date"] = dt
    return roles
