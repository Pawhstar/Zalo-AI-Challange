"""Normalize each business's messy files into a canonical model.

Canonical tables:
  orders   : order_id, date, status, customer, customer_id, employee, channel,
             payment_method, hour, order_goods, order_discount, order_total,
             paid, debt, delivery_fee, revenue, is_valid
  lines    : order_id, date, status, customer, customer_id, employee, channel,
             payment_method, item, item_id, qty, unit, unit_price,
             line_discount, line_amount, qty_base, base_unit, cost_price,
             revenue, valid
  items    : item, item_id, base_unit, cost, sale_price, group
  units    : item, unit, factor, base_unit
  stock    : item, qty, unit
  purchases / purchase_lines / payments / customers

Detection is structural and generic (no per-business hardcoding): every table in
the business is tried as (order-header, order-detail), (flat lines), (per-month
sheet set) or (flat orders); each candidate is built and scored; the best wins.
"""
import os, re, glob, sqlite3, unicodedata
import pandas as pd
import numpy as np

# ---------------------------------------------------------------- primitives

def norm(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFC", str(s))
    return re.sub(r"\s+", " ", s).strip()

def lower(s):
    return norm(s).lower()

def _akey(s):
    """Accent-insensitive, punctuation-free lowercase key for column matching."""
    s = lower(s)
    s = "".join(ch for ch in unicodedata.normalize("NFD", s)
                if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s)

_NUM_RE = re.compile(r"-?[\d.,]+")

def parse_num(v):
    """'55.000đ' -> 55000.0 ; '45,000.0000' -> 45000 ; '55k' -> 55000 ; '' -> nan"""
    if v is None:
        return np.nan
    if isinstance(v, bool):
        return np.nan
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v)
    s = norm(str(v))
    if s == "" or s.lower() in ("nan", "none", "nat"):
        return np.nan
    s = s.replace("đ", "").replace("₫", "").replace("d", "").strip()
    low = s.lower()
    mult = 1.0
    if low.endswith("k"):
        mult, s = 1000.0, s[:-1]
    elif low.endswith("tr"):
        mult, s = 1_000_000.0, s[:-2]
    elif low.endswith("t"):
        mult, s = 1_000_000_000.0, s[:-1]
    elif low.endswith("ng"):
        mult, s = 1000.0, s[:-3]
    s = s.replace(" ", "")
    if s.count(",") and s.count("."):
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(",") == 1:
        head, tail = s.split(",")
        if len(tail) == 3 and head.lstrip("-").isdigit():
            s = head + tail
        else:
            s = s.replace(",", ".")
    elif s.count(",") > 1:
        s = s.replace(",", "")
    try:
        return float(s) * mult
    except ValueError:
        return np.nan

_EXCEL_EPOCH = pd.Timestamp("1899-12-30")

def parse_date(v):
    """Timestamp or NaT. Handles datetime, dd/mm/yyyy, yyyy-mm-dd, Excel serial,
    '1 thg 6 2025', 'Tháng 02 2025'."""
    if v is None:
        return pd.NaT
    if isinstance(v, pd.Timestamp):
        return v
    if isinstance(v, (np.datetime64,)):
        return pd.Timestamp(v)
    if isinstance(v, (int, float, np.integer, np.floating)):
        n = float(v)
        if 20000 < n < 80000:
            return _EXCEL_EPOCH + pd.Timedelta(days=n)
        if 1900 < n < 2100:
            return pd.Timestamp(int(n), 1, 1)
        return pd.NaT
    s = norm(str(v))
    if s == "" or s.lower() in ("nan", "nat", "none"):
        return pd.NaT
    if re.fullmatch(r"\d{5}(\.\d+)?", s):
        return _EXCEL_EPOCH + pd.Timedelta(days=float(s))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}([ T].*)?", s):
        return pd.Timestamp(s[:10])
    if re.fullmatch(r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}", s):
        d, m, y = re.split(r"[/\-.]", s)
        try:
            return pd.Timestamp(int(y), int(m), int(d))
        except ValueError:
            return pd.NaT
    if re.fullmatch(r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2}", s):
        d, m, y = re.split(r"[/\-.]", s)
        yy = int(y); yy = 2000 + yy if yy < 70 else 1900 + yy
        try:
            return pd.Timestamp(yy, int(m), int(d))
        except ValueError:
            return pd.NaT
    m = re.match(r"^(\d{1,2})\s*thg\s*(\d{1,2})\s*(\d{4})$", s, re.I)
    if m:
        try:
            return pd.Timestamp(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return pd.NaT
    m = re.match(r"^thg\s*(\d{1,2})\s*(\d{4})$", s, re.I)
    if m:
        try:
            return pd.Timestamp(int(m.group(2)), int(m.group(1)), 1)
        except ValueError:
            return pd.NaT
    if re.fullmatch(r"\d{4}-\d{1,2}", s):
        y, m = s.split("-")
        return pd.Timestamp(int(y), int(m), 1)
    try:
        return pd.Timestamp(s)
    except Exception:
        return pd.NaT

# ---------------------------------------------------------------- status

CANCEL_TOK = ["đã hủy", "da huy", "hủy", "huy", "huỷ", "cancel", "bị hủy", "bi huy",
              "hủy đơn", "đơn hủy"]
RETURN_TOK = ["trả hàng", "tra hang", "hoàn trả", "hoan tra", "hoàn lại", "hoan lai",
              "return", "refund", "đổi trả", "doi tra", "trả lại", "tra lai",
              "hoàn hàng", "hoan hang", "trả 1 phần", "tra 1 phan", "huỷ hàng",
              "huy hang", "hủy hàng"]
DONE_TOK = ["hoàn thành", "hoan thanh", "hoàn tất", "hoan tat", "thành công",
            "thanh cong", "giao thành công", "completed", "complete", "done",
            "xong", "đã xong", "da xong", "thanh cong"]
SHIP_TOK = ["đang giao", "dang giao", "đang vận chuyển", "dang van chuyen",
            "shipping", "giao hàng", "đơn giao", "chờ giao", "cho giao",
            "đang xử lý", "dang xu ly", "chờ xử lý", "cho xu ly", "đang làm",
            "sắp giao", "sap giao", "đang chuẩn bị", "chuẩn bị giao", "chuan bi giao"]

def classify_status(v):
    """-> 'done' | 'cancelled' | 'returned' | 'shipping' | '' (unknown)."""
    s = lower(v)
    if s == "":
        return ""
    for t in RETURN_TOK:
        if t in s:
            return "returned"
    for t in CANCEL_TOK:
        if t in s:
            return "cancelled"
    for t in SHIP_TOK:
        if t in s:
            return "shipping"
    for t in DONE_TOK:
        if t in s:
            return "done"
    return ""

# ---------------------------------------------------------------- column vocab

COL = {
    "order_id":  ["mã hóa đơn", "mã hoa don", "mã đơn hàng", "ma don hang", "mã bill",
                  "ma bill", "mã gd", "ma gd", "mã hđ", "ma hd", "số hóa đơn",
                  "so hoa don", "mã chứng từ", "ma chung tu", "mã phiếu", "ma phieu",
                  "bill id", "id đơn", "id don", "số đơn", "so don"],
    "date":      ["ngày đặt hàng", "ngay dat hang", "ngày đặt", "ngay dat",
                  "ngày giao dịch", "ngay giao dich", "thời gian lập", "thoi gian lap",
                  "ngày bán", "ngay ban", "ngày giao dịch", "ngày mua", "ngay mua",
                  "ngày tháng", "ngay thang", "ngày", "ngay", "thời gian", "thoi gian",
                  "ngày tạo", "ngay tao"],
    "status":    ["trạng thái đơn hàng", "trang thai don hang", "trạng thái",
                  "trang thai", "tình trạng", "tinh trang", "xử lý", "xu ly",
                  "ghi chú tt", "kết quả", "ket qua", "status", "ghi chú", "ghi chu"],
    "cust_name": ["tên khách hàng", "ten khach hang", "tên khách", "ten khach",
                  "khách hàng", "khach hang", "đối tác", "doi tac", "bên mua",
                  "ben mua", "khách", "khach", "tên người mua"],
    "cust_id":   ["mã khách hàng", "ma khach hang", "mã kh", "ma kh", "số kh", "so kh",
                  "mã khách", "ma khach", "khách hàng id"],
    "item_name": ["tên hàng hóa", "ten hang hoa", "tên hàng", "ten hang", "tên món",
                  "ten mon", "mặt hàng", "mat hang", "tên sản phẩm", "ten san pham",
                  "nội dung", "noi dung", "sản phẩm", "san pham", "hàng", "hang",
                  "product", "tên gói", "tên hàng hóa"],
    "item_id":   ["mã hàng hóa", "ma hang hoa", "mã hàng", "ma hang", "mã sku", "ma sku",
                  "sku", "mã barcode", "ma barcode", "id sp", "mã sản phẩm"],
    "qty":       ["số lượng sản phẩm", "so luong san pham", "số lượng", "so luong",
                  "sl bán", "sl ban", "sl", "số lượng lẻ", "so luong le", "sluong"],
    "unit":      ["đơn vị tính", "don vi tinh", "đơn vị", "don vi", "dvt", "unit",
                  "đơn vị gốc", "don vi goc"],
    "unit_price":["đơn giá", "don gia", "giá bán", "gia ban", "giá lẻ", "gia le",
                  "giá đơn vị", "gia don vi"],
    "line_disc": ["giảm giá", "giam gia", "chiết khấu", "chiet khau"],
    "line_amt":  ["thành tiền", "thanh tien", "trị giá", "tri gia", "tổng tiền",
                  "tong tien", "tổng", "tong", "tiền", "tien", "giá trị hàng",
                  "gia tri hang"],
    "qty_base":  ["số lượng quy đổi", "so luong quy doi", "sl quy đổi", "sl quy doi",
                  "quy ra đv lẻ", "quy ra dv le", "số lượng lẻ", "so luong le",
                  "số lượng quy đổi (đvt cơ bản)", "số lượng (đvt cơ bản)"],
    "cost":      ["giá vốn", "gia von", "giá vốn lúc bán", "gia von luc ban"],
    "hour":      ["giờ", "gio"],
    "employee":  ["người bán", "nguoi ban", "mã nhân viên", "nhan vien", "nhân viên",
                  "nhân viên bán", "thợ", "người giao", "mã thợ"],
    "channel":   ["kênh bán", "kenh ban", "bán qua", "ban qua", "kênh"],
    "pay_method":["phương thức thanh toán", "phuong thuc thanh toan", "phương thức tt",
                  "phuong thuc tt", "phương thức", "phuong thuc"],
    "order_goods":["tổng tiền hàng", "tong tien hang", "tiền hàng", "tien hang",
                   "giá trị hàng", "gia tri hang"],
    "order_disc": ["giảm giá", "giam gia", "chiết khấu", "chiet khau"],
    "order_total":["tổng sau giảm giá", "tong sau giam gia", "tổng bill", "tong bill",
                   "tổng thanh toán", "tong thanh toan", "tổng", "tong", "tiền"],
    "paid":      ["khách đã trả", "khach da tra", "đã thu", "da thu", "khách trả",
                  "khach tra", "tiền đã trả"],
    "debt":      ["còn nợ", "con no", "còn phải thu", "chưa trả", "chua tra", "nợ", "no"],
    "delivery":  ["phí vận chuyển", "phi van chuyen", "phí giao hàng", "phi giao hang",
                  "phí ship", "phi ship", "phí giao"],
    "base_unit": ["đơn vị cơ bản", "don vi co ban", "đơn vị gốc", "don vi goc",
                  "đv nhập", "dv nhap", "đv lẻ", "dv le", "đơn vị nhỏ", "đv nhỏ"],
    "factor":    ["tỉ lệ quy đổi", "ti le quy doi", "hệ số quy đổi", "heso quydoi",
                  "hệ số", "he so", "quy đổi", "quy doi"],
    "cost_item": ["giá vốn", "gia von"],
    "sale_item": ["giá bán", "gia ban", "giá", "gia"],
    "group":     ["nhóm hàng", "nhom hang", "nhóm hàng hóa", "nhom hang hoa",
                  "loại hàng hóa", "loai hang hoa", "danh mục", "danh muc",
                  "nhóm khách hàng", "nhom khach hang", "đối tượng kh", "loại hình khách",
                  "loai hinh khach"],
    "stock_qty": ["tồn cuối kỳ", "ton cuoi ky", "tồn cuối", "ton cuoi", "tồn thực",
                  "ton thuc", "tồn", "ton"],
    "receipt_id":["số phiếu", "so phieu", "mã nhập hàng", "ma nhap hang",
                  "mã đơn nhập", "ma don nhap", "mã phiếu nhập", "ma phieu nhap",
                  "mã nhập", "ma nhap"],
    "recv_date": ["ngày nhập", "ngay nhap", "ngày phiếu", "thời gian"],
    "recv_amt":  ["thành tiền", "tổng giá trị nhập", "tong gia tri nhap", "cần trả ncc",
                  "can tra ncc", "tiền"],
    "supplier":  ["nhà cung cấp", "nha cung cap", "mã ncc", "ma ncc", "supplier"],
    "recv_item": ["tên mặt hàng", "ten mat hang", "tên hàng", "ten hang", "product",
                  "mặt hàng", "tên sản phẩm"],
    "recv_qty":  ["sl nhập", "số lượng", "so luong", "sl"],
    "recv_price":["giá nhập", "gia nhap", "đơn giá", "don gia"],
    "lot":       ["lô", "ma lo", "mã lô", "ma lo", "lô hàng"],
    "expiry":    ["hạn sử dụng", "han su dung", "hạn sd", "han sd"],
    "pay_date":  ["thời gian thu", "thoi gian thu", "ngày thu", "ngay thu",
                  "ngày giao dịch", "ngày"],
    "pay_amt":   ["giá trị", "gia tri", "số tiền thu", "so tien thu", "tiền", "tien",
                  "số tiền"],
    "pay_oid":   ["số hđ", "so hd", "mã hóa đơn", "ma hoa don", "mã bill", "ma bill"],
    "cust_master":["tên khách hàng", "ten khach hang", "tên khách", "ten khach"],
}

def find_col(df, *names):
    """Substring match on accent-stripped keys; first candidate name wins."""
    if df is None or len(df.columns) == 0:
        return None
    keys = [(c, _akey(c)) for c in df.columns]
    for n in names:
        k = _akey(n)
        if not k:
            continue
        for c, kk in keys:
            if k == kk:
                return c
    for n in names:
        k = _akey(n)
        if not k:
            continue
        for c, kk in keys:
            if k in kk:
                return c
    return None

def col(df, role):
    """Find the column for a semantic role."""
    names = COL.get(role)
    if not names:
        return None
    return find_col(df, *names)

def col_ex(df, role, exclude=()):
    """Find a column for a role, skipping columns already claimed."""
    names = COL.get(role)
    if not names:
        return None
    excl = {_akey(e) for e in exclude}
    keys = [(c, _akey(c)) for c in df.columns]
    for n in names:
        k = _akey(n)
        if not k:
            continue
        for c, kk in keys:
            if kk in excl:
                continue
            if k == kk:
                return c
    for n in names:
        k = _akey(n)
        if not k:
            continue
        for c, kk in keys:
            if kk in excl:
                continue
            if k in kk:
                return c
    return None

# ---------------------------------------------------------------- file readers

def read_any(path):
    ext = os.path.splitext(path)[1].lower()
    out = {}
    if ext == ".csv":
        df = None
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                df = pd.read_csv(path, encoding=enc, dtype=object,
                                 keep_default_na=False, header=None)
                break
            except UnicodeDecodeError:
                continue
        if df is None:
            df = pd.read_csv(path, encoding="latin-1", dtype=object,
                             keep_default_na=False, header=None)
        out["__main__"] = df
        return out
    if ext == ".xlsx":
        xl = pd.ExcelFile(path)
        for sh in xl.sheet_names:
            out[sh] = pd.read_excel(path, sheet_name=sh, header=None, dtype=object)
        return out
    if ext == ".sqlite":
        con = sqlite3.connect(path)
        try:
            for (t,) in con.execute("select name from sqlite_master where type='table'"):
                out[t] = pd.read_sql(f'select * from "{t}"', con)
        finally:
            con.close()
        return out
    return out

def find_header_row(df, max_scan=14):
    """Row index that looks like a real header (most filled cells, not a banner)."""
    best, best_score = None, -1
    n = min(len(df), max_scan)
    for i in range(n):
        row = df.iloc[i].tolist()
        cells = [norm(c) for c in row]
        filled = [c for c in cells if c != "" and c.lower() != "nan"]
        if len(filled) < 2:
            continue
        if len(filled) <= 2 and len(filled[0]) > 25:
            continue
        score = len(filled)
        if score > best_score:
            best, best_score = i, score
    return best if best is not None else 0

def df_from_sheet(raw):
    """Raw sheet (header=None) -> DataFrame with a real header row."""
    hdr = find_header_row(raw)
    df = raw.iloc[hdr:].copy()
    cols, seen = [], {}
    for i, c in enumerate(df.iloc[0].tolist()):
        n = norm(c) if norm(c) else f"col{i}"
        if n in seen:
            seen[n] += 1
            n = f"{n}_{seen[n]}"
        else:
            seen[n] = 0
        cols.append(n)
    df.columns = cols
    df = df.iloc[1:].reset_index(drop=True)
    if len(df.columns):
        first = df.iloc[:, 0].astype(str)
        df = df[~first.isin(["", "nan", "NaN", "None", "NaT"])]
    df = df.reset_index(drop=True)
    df = df.replace({"": None, "nan": None, "NaN": None, "None": None, "NaT": None})
    keep = [c for c in df.columns if df[c].notna().any()]
    return df[keep]

# ---------------------------------------------------------------- period helpers

def _sheet_period(name):
    """(year, month) implied by a sheet name, or None."""
    k = _akey(name)
    m = re.search(r"t(\d{1,2})[_\- ]?(\d{4})", k)
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.search(r"(\d{1,2})[_\- ](\d{4})", k)
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.search(r"thang(\d{1,2})(\d{4})", k)
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.search(r"(\d{4})[_\- ](\d{1,2})[_\- ](\d{1,2})", k)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,2})[_\- ](\d{1,2})[_\- ](\d{4})", k)
    if m:
        return int(m.group(3)), int(m.group(2))
    return None

# ---------------------------------------------------------------- business

class Business:
    def __init__(self, biz_id, path):
        self.id = biz_id
        self.path = path
        self.sheets = {}           # key -> raw DataFrame (header=None)
        self.readme = ""
        rp = os.path.join(path, "README.md")
        if os.path.exists(rp):
            with open(rp, encoding="utf-8") as f:
                self.readme = f.read()
        for fn in sorted(os.listdir(path)):
            if not fn.lower().endswith((".csv", ".xlsx", ".sqlite")):
                continue
            try:
                for sh, df in read_any(os.path.join(path, fn)).items():
                    key = fn if fn.lower().endswith((".csv", ".sqlite")) else f"{fn}::{sh}"
                    self.sheets[key] = df
            except Exception:
                pass
        self._build()

    # -------------------------------------------------- build
    def _build(self):
        self.orders = pd.DataFrame()
        self.lines = pd.DataFrame()
        self.items = pd.DataFrame()
        self.units = pd.DataFrame()
        self.stock = pd.DataFrame()
        self.purchases = pd.DataFrame()
        self.purchase_lines = pd.DataFrame()
        self.payments = pd.DataFrame()
        self.customers = pd.DataFrame()
        self.sales_sheets = set()
        self._frames = {}

        self._build_items()
        self._build_units()
        self._build_stock()
        self._build_sales()
        self._build_purchases()
        self._build_payments()
        self._build_customers()

    # -------------------------------------------------- items / units / stock
    def _iter_tables(self, skip=()):
        for name, raw in self.sheets.items():
            if name in skip:
                continue
            if not isinstance(raw, pd.DataFrame):
                continue
            if name not in self._frames:
                self._frames[name] = df_from_sheet(raw)
            yield name, self._frames[name]

    def _build_items(self):
        best = None
        for name, h in self._iter_tables():
            if len(h) < 2:
                continue
            c_name = col(h, "item_name")
            if not c_name:
                continue
            c_id = col_ex(h, "item_id", [c_name])
            c_base = col_ex(h, "base_unit", [c_name])
            c_cost = col_ex(h, "cost_item", [c_name])
            c_price = col_ex(h, "sale_item", [c_name])
            c_grp = col_ex(h, "group", [c_name])
            if not (c_cost or c_price or c_base):
                continue
            t = pd.DataFrame()
            t["item"] = h[c_name].map(norm)
            t["item_id"] = h[c_id].map(norm) if c_id else ""
            t["base_unit"] = h[c_base].map(norm) if c_base else ""
            t["cost"] = h[c_cost].map(parse_num) if c_cost else np.nan
            t["sale_price"] = h[c_price].map(parse_num) if c_price else np.nan
            t["group"] = h[c_grp].map(norm) if c_grp else ""
            t = t[t["item"] != ""]
            # prefer the table with the most distinct items
            if best is None or len(t) > len(best[1]):
                best = (name, t)
        if best is not None:
            self.items = best[1].drop_duplicates(subset=["item"], keep="first").reset_index(drop=True)
            # fill missing base units from the README conversion table
            readme_base = self._parse_readme_units()
            self._readme_base_unit = readme_base
            if readme_base:
                miss = self.items["base_unit"].isna() | (self.items["base_unit"] == "")
                if miss.any():
                    self.items.loc[miss, "base_unit"] = \
                        self.items.loc[miss, "item"].map(readme_base).fillna("")
            self._item_name_by_id = {}
            if "item_id" in self.items:
                m = self.items[self.items["item_id"] != ""]
                self._item_name_by_id = dict(zip(m["item_id"], m["item"]))
            self._item_by_name = dict(zip(self.items["item"], self.items.index))
        else:
            self._item_name_by_id = {}
            self._item_by_name = {}

    def _build_units(self):
        best = None
        for name, h in self._iter_tables():
            if len(h) < 2:
                continue
            c_name = col(h, "item_name")
            c_rate = col(h, "factor")
            if not (c_name and c_rate):
                continue
            # A conversion table lists items with a rate; a sales-detail table
            # carries a "số lượng quy đổi" column that also matches the factor
            # role. Reject any table that is itself a sales/lines table.
            if col(h, "line_amt") or col(h, "order_id") or col(h, "status"):
                continue
            c_unit = col_ex(h, "unit", [c_name])
            c_base = col_ex(h, "base_unit", [c_name, c_unit] if c_unit else [c_name])
            t = pd.DataFrame()
            t["item"] = h[c_name].map(norm)
            t["unit"] = h[c_unit].map(norm) if c_unit else ""
            t["factor"] = h[c_rate].map(parse_num)
            t["base_unit"] = h[c_base].map(norm) if c_base else ""
            t = t[(t["factor"].notna()) & (t["factor"] > 0)]
            # a genuine conversion table is small
            if len(t) > 20000:
                continue
            if len(t) and (best is None or len(t) > len(best[1])):
                best = (name, t)
        self.units = best[1] if best else pd.DataFrame()
        self._unit_factor = {}
        if len(self.units):
            for item, unit, factor in zip(self.units["item"], self.units["unit"],
                                          self.units["factor"]):
                self._unit_factor[(item, unit)] = float(factor)
        # units named in the README ("1 bao = 5 kg" rules)
        readme_units = set()
        for m in re.finditer(r"1\s+(\S+)\s*=\s*\d+(?:\.\d+)?\s+(\S+)", self.readme):
            readme_units.add(m.group(1))
            readme_units.add(m.group(2))
        if len(self.units) == 0 and readme_units:
            self.units = pd.DataFrame(
                {"item": "", "unit": sorted(readme_units), "factor": 1.0,
                 "base_unit": ""})
        self._readme_units = sorted(readme_units)

    def _parse_readme_units(self):
        """README lines look like 'Gạo ST25: 1 bao = 5 kg'. The base unit of an
        item is the unit that only ever appears as a conversion target."""
        item_units = {}
        cur = None
        for line in self.readme.splitlines():
            line = line.strip()
            if not line.startswith("-") and ":" in line:
                head = line.split(":")[0].strip()
                if head and not head.startswith("Dữ liệu") and not head.startswith("Quy"):
                    cur = head
            m = re.search(r"1\s+(\S+)\s*=\s*\d+(?:\.\d+)?\s+(\S+)", line)
            if m and cur:
                src, dst = m.group(1), m.group(2)
                d = item_units.setdefault(cur, {"src": set(), "dst": set()})
                d["src"].add(src)
                d["dst"].add(dst)
        out = {}
        for item, d in item_units.items():
            targets = d["dst"] - d["src"]
            if targets:
                out[item] = sorted(targets)[0]
            elif d["dst"]:
                out[item] = sorted(d["dst"])[0]
        return out

    def _build_stock(self):
        best = None
        for name, h in self._iter_tables():
            if len(h) < 2:
                continue
            c_name = col(h, "item_name")
            c_qty = col(h, "stock_qty")
            if not (c_name and c_qty):
                continue
            c_u = col_ex(h, "unit", [c_name])
            t = pd.DataFrame()
            t["item"] = h[c_name].map(norm)
            t["qty"] = h[c_qty].map(parse_num)
            t["unit"] = h[c_u].map(norm) if c_u else ""
            t = t[t["item"] != ""]
            if best is None or len(t) > len(best[1]):
                best = (name, t)
        self.stock = best[1] if best else pd.DataFrame()

    # -------------------------------------------------- sales
    def _build_sales(self):
        cands = []
        cands.append(self._try_pos_pair())
        cands.append(self._try_sheet_set())
        cands.append(self._try_flat_lines())
        cands.append(self._try_flat_orders())
        scored = []
        for c in cands:
            if c is None:
                continue
            lines, orders, sheets = c
            if lines is None or len(lines) == 0:
                continue
            s = self._score(lines, orders)
            scored.append((s, lines, orders, sheets))
        if not scored:
            return
        scored.sort(key=lambda x: -x[0])
        _, lines, orders, sheets = scored[0]
        self.lines = lines
        self.orders = orders
        self.sales_sheets = sheets
        self._post_orders()

    def _post_orders(self):
        """Add the derived columns every builder relies on: is_valid, revenue,
        n_lines, and fill order revenue from lines when missing."""
        O = self.orders
        if len(O) == 0:
            O = O.copy()
            if "is_valid" not in O.columns:
                O["is_valid"] = True
            if "revenue" not in O.columns:
                O["revenue"] = pd.NA
            self.orders = O
            return
        if "status" in O.columns:
            O["is_valid"] = ~O["status"].isin(["cancelled", "returned"])
        else:
            O["is_valid"] = True
        if "status_raw" not in O.columns:
            O["status_raw"] = ""
        L = self.lines
        if len(L):
            g = L[L.get("valid", pd.Series(True, index=L.index)).fillna(True)
                    ] if "valid" in L.columns else L
            rev = L[L["valid"]].groupby("order_id")["revenue"].sum()
            cnt = L[L["valid"]].groupby("order_id")["order_id"].count()
            O["line_revenue"] = O["order_id"].map(rev)
            O["n_lines"] = O["order_id"].map(cnt).fillna(0)
            if "revenue" not in O.columns or O["revenue"].isna().all():
                O["revenue"] = O["line_revenue"]
            if "order_goods" in O.columns and O["order_goods"].isna().all():
                O["order_goods"] = O["line_revenue"]
        else:
            O["line_revenue"] = pd.NA
            O["n_lines"] = 0
        if "revenue" not in O.columns:
            O["revenue"] = pd.NA
        if "order_goods" in O.columns and O["order_goods"].notna().any() \
                and (O["revenue"].isna().all() or not O["order_goods"].equals(O["revenue"])):
            O["revenue"] = O["order_goods"]
        self.orders = O

    def _score(self, lines, orders):
        """Heuristic quality score for a candidate sales model."""
        if lines is None or len(lines) == 0:
            return -1
        s = 0.0
        s += 10 * min(1.0, lines["date"].notna().mean())
        s += 5 * min(1.0, lines["revenue"].notna().mean())
        n_items = lines["item"].nunique()
        s += 5 * min(1.0, n_items / 20.0)
        s += 5 * min(1.0, len(lines) / 200.0)
        if orders is not None and len(orders):
            s += 5 * min(1.0, orders["date"].notna().mean())
            s += 3 * min(1.0, orders["order_id"].nunique() / 50.0)
        # a table with a date column but all-NaT dates is a bad sign
        if lines["date"].notna().sum() == 0:
            s -= 50
        return s

    # -- strategy A: order-header table + order-detail table
    def _try_pos_pair(self):
        tabs = []
        for name, h in self._iter_tables():
            if len(h) < 2:
                continue
            tabs.append((name, h))
        headers, details = [], []
        detail_lines = {}          # name -> built lines (built once)
        for name, h in tabs:
            c_oid = col(h, "order_id")
            c_date = col(h, "date")
            c_item = col(h, "item_name")
            c_qty = col(h, "qty")
            c_amt = col(h, "line_amt")
            if not c_oid:
                continue
            is_detail = bool(c_item) and (bool(c_qty) or bool(c_amt))
            is_header = bool(c_date) and (col(h, "status") is not None
                                          or col(h, "cust_name") is not None
                                          or col(h, "order_goods") is not None
                                          or col(h, "order_total") is not None)
            if is_detail:
                details.append((name, h, c_oid))
            if is_header and not is_detail:
                headers.append((name, h, c_oid, c_date))
        best = None
        for hn, hh, ho, hd in headers:
            hdr_orders = self._orders_from_header(hn, hh, ho, hd)
            if hdr_orders is None or len(hdr_orders) == 0:
                continue
            for dn, dh, do in details:
                if dn not in detail_lines:
                    L = self._lines_from_detail(dn, dh, do)
                    if L is not None and len(L):
                        L = self._finish_lines(L)
                    detail_lines[dn] = L
                lines = detail_lines[dn]
                if lines is None or len(lines) == 0:
                    continue
                orders = self._merge_header(lines, hdr_orders)
                s = self._score(lines, orders)
                if best is None or s > best[0]:
                    best = (s, lines, orders, {hn, dn})
        if best is None:
            return None
        return best[1], best[2], best[3]

    def _merge_header(self, lines, hdr_orders):
        """Attach header attributes to the detail lines and rebuild the orders."""
        keys = ["order_id", "date", "status", "customer", "customer_id", "employee",
                "channel", "payment_method", "hour"]
        H = hdr_orders.copy()
        for c in keys:
            if c not in H.columns:
                H[c] = "" if c != "date" else pd.NaT
        H = H.drop_duplicates(subset=["order_id"], keep="first")
        money = [c for c in ("order_goods", "order_discount", "order_total",
                             "paid", "debt", "delivery_fee") if c in hdr_orders.columns]
        L = lines.merge(H[keys + money], on="order_id", how="left",
                        suffixes=("", "_h"))
        for c in keys:
            if c + "_h" in L.columns:
                L[c] = L[c].where(L[c].notna() & (L[c] != ""), L[c + "_h"])
                L = L.drop(columns=[c + "_h"])
        if "status" in L.columns and "status_raw" in L.columns:
            ls = L["status_raw"].map(classify_status)
            L["status"] = np.where(ls != "", ls, L["status"])
        L["valid"] = ~L["status"].isin(["cancelled", "returned"])
        g = L.groupby("order_id", sort=False)
        O = pd.DataFrame(index=g.size().index)
        O["order_id"] = O.index
        for c in ("date", "status", "customer", "customer_id", "employee",
                  "channel", "payment_method", "hour"):
            if c in L.columns:
                O[c] = g[c].first()
        O["status_raw"] = O.get("status_raw", "")
        O["order_goods"] = g["line_amount"].sum()
        O["order_discount"] = np.nan
        O["order_total"] = np.nan
        O["paid"] = np.nan
        O["debt"] = np.nan
        O["delivery_fee"] = np.nan
        return O.reset_index(drop=True)

    def _lines_from_detail(self, name, h, c_oid):
        c_item = col(h, "item_name")
        c_iid = col_ex(h, "item_id", [c_item] if c_item else [])
        c_qty = col(h, "qty")
        c_amt = col(h, "line_amt")
        c_price = col_ex(h, "unit_price", [c_item] if c_item else [])
        if not (c_qty or c_amt):
            return None
        per = _sheet_period(name)
        L = pd.DataFrame()
        L["order_id"] = h[c_oid].map(norm)
        L["date"] = self._dates(h, col(h, "date"), per)
        L["item"] = h[c_item].map(norm) if c_item else ""
        L["item_id"] = h[c_iid].map(norm) if c_iid else ""
        L["qty"] = h[c_qty].map(parse_num) if c_qty else np.nan
        L["unit"] = h[col(h, "unit")].map(norm) if col(h, "unit") else ""
        L["unit_price"] = h[c_price].map(parse_num) if c_price else np.nan
        L["line_discount"] = h[col(h, "line_disc")].map(parse_num) if col(h, "line_disc") else np.nan
        L["line_amount"] = h[c_amt].map(parse_num) if c_amt else np.nan
        L["qty_base"] = h[col(h, "qty_base")].map(parse_num) if col(h, "qty_base") else np.nan
        L["cost_price"] = h[col(h, "cost")].map(parse_num) if col(h, "cost") else np.nan
        return L

    def _orders_from_header(self, name, h, c_oid, c_date):
        per = _sheet_period(name)
        O = pd.DataFrame()
        O["order_id"] = h[c_oid].map(norm)
        O["date"] = self._dates(h, c_date, per)
        c_stat = col(h, "status")
        O["status_raw"] = h[c_stat].map(norm) if c_stat else ""
        O["status"] = O["status_raw"].map(classify_status)
        c_c = col(h, "cust_name")
        O["customer"] = h[c_c].map(norm) if c_c else ""
        c_cid = col_ex(h, "cust_id", [c_c] if c_c else [])
        O["customer_id"] = h[c_cid].map(norm) if c_cid else ""
        c_e = col(h, "employee")
        O["employee"] = h[c_e].map(norm) if c_e else ""
        c_ch = col(h, "channel")
        O["channel"] = h[c_ch].map(norm) if c_ch else ""
        c_pm = col(h, "pay_method")
        O["payment_method"] = h[c_pm].map(norm) if c_pm else ""
        c_h = col(h, "hour")
        O["hour"] = self._hours(h[c_h]) if c_h else np.nan
        for role, out in (("order_goods", "order_goods"), ("order_disc", "order_discount"),
                          ("order_total", "order_total"), ("paid", "paid"),
                          ("debt", "debt"), ("delivery", "delivery_fee")):
            c = col(h, role)
            O[out] = h[c].map(parse_num) if c else np.nan
        return O

    # -- strategy B: per-month sheet sets of order lines
    def _try_sheet_set(self):
        groups = []
        for name, raw in self.sheets.items():
            per = _sheet_period(name)
            if not per:
                continue
            h = df_from_sheet(raw)
            if len(h) < 3:
                continue
            if not (col(h, "item_name") and (col(h, "qty") or col(h, "line_amt"))):
                continue
            groups.append((name, h, per))
        if len({p for _, _, p in groups}) < 2:
            return None
        frames = []
        for name, h, per in groups:
            g = h.copy()
            g["_per"] = [per] * len(g)
            frames.append(g)
        allh = pd.concat(frames, ignore_index=True)
        c_oid = col(allh, "order_id")
        if not c_oid:
            return None
        L = pd.DataFrame()
        L["order_id"] = allh[c_oid].map(norm)
        L["date"] = self._dates(allh, col(allh, "date"), None, per_col="_per")
        c_item = col(allh, "item_name")
        L["item"] = allh[c_item].map(norm) if c_item else ""
        c_iid = col_ex(allh, "item_id", [c_item] if c_item else [])
        L["item_id"] = allh[c_iid].map(norm) if c_iid else ""
        c_qty = col(allh, "qty")
        L["qty"] = allh[c_qty].map(parse_num) if c_qty else np.nan
        c_u = col(allh, "unit")
        L["unit"] = allh[c_u].map(norm) if c_u else ""
        c_p = col(allh, "unit_price")
        L["unit_price"] = allh[c_p].map(parse_num) if c_p else np.nan
        L["line_discount"] = np.nan
        c_a = col(allh, "line_amt")
        L["line_amount"] = allh[c_a].map(parse_num) if c_a else np.nan
        c_qb = col(allh, "qty_base")
        L["qty_base"] = allh[c_qb].map(parse_num) if c_qb else np.nan
        L["cost_price"] = np.nan
        self._add_line_attrs(allh, L, c_item)
        L = self._finish_lines(L)
        if len(L) == 0:
            return None
        orders = self._orders_from_lines(L)
        return L, orders, {n for n, _, _ in groups}

    # -- strategy C: one flat table of order lines
    def _try_flat_lines(self):
        best = None
        for name, h in self._iter_tables():
            if len(h) < 5:
                continue
            c_item = col(h, "item_name")
            if not c_item:
                continue
            c_qty = col(h, "qty")
            c_amt = col(h, "line_amt")
            if not (c_qty or c_amt):
                continue
            per = _sheet_period(name)
            L = pd.DataFrame()
            c_oid = col(h, "order_id")
            L["order_id"] = h[c_oid].map(norm) if c_oid else h.index.map(lambda i: f"R{i}")
            L["date"] = self._dates(h, col(h, "date"), per)
            L["item"] = h[c_item].map(norm)
            c_iid = col_ex(h, "item_id", [c_item])
            L["item_id"] = h[c_iid].map(norm) if c_iid else ""
            L["qty"] = h[c_qty].map(parse_num) if c_qty else np.nan
            c_u = col(h, "unit")
            L["unit"] = h[c_u].map(norm) if c_u else ""
            c_p = col(h, "unit_price")
            L["unit_price"] = h[c_p].map(parse_num) if c_p else np.nan
            c_d = col(h, "line_disc")
            L["line_discount"] = h[c_d].map(parse_num) if c_d else np.nan
            L["line_amount"] = h[c_amt].map(parse_num) if c_amt else np.nan
            c_qb = col(h, "qty_base")
            L["qty_base"] = h[c_qb].map(parse_num) if c_qb else np.nan
            L["cost_price"] = np.nan
            self._add_line_attrs(h, L, c_item)
            L = self._finish_lines(L)
            if len(L) == 0:
                continue
            orders = self._orders_from_lines(L)
            s = self._score(L, orders)
            if best is None or s > best[0]:
                best = (s, L, orders, {name})
        if best is None:
            return None
        return best[1], best[2], best[3]

    def _add_line_attrs(self, h, L, c_item):
        """Copy the order-level attributes a line table may carry."""
        def grab(role, out, exclude=()):
            c = col_ex(h, role, [c_item] + list(exclude))
            if c is not None:
                L[out] = h[c].map(norm)
            return c
        c_stat = grab("status", "status_raw")
        if "status" not in L.columns:
            L["status"] = L["status_raw"].map(classify_status) if c_stat else ""
        grab("cust_name", "customer")
        c_cid = grab("cust_id", "customer_id")
        grab("employee", "employee")
        grab("channel", "channel")
        grab("pay_method", "payment_method")
        c_h = col_ex(h, "hour", [c_item])
        if c_h is not None:
            L["hour"] = self._hours(h[c_h])
        # discount/paid/debt columns sometimes sit on the line table
        return c_stat

    # -- strategy D: one flat table of orders
    def _try_flat_orders(self):
        best = None
        for name, h in self._iter_tables():
            if len(h) < 5:
                continue
            c_oid = col(h, "order_id")
            c_date = col(h, "date")
            if not (c_oid and c_date):
                continue
            per = _sheet_period(name)
            O = pd.DataFrame()
            O["order_id"] = h[c_oid].map(norm)
            O["date"] = self._dates(h, c_date, per)
            c_stat = col(h, "status")
            O["status_raw"] = h[c_stat].map(norm) if c_stat else ""
            O["status"] = O["status_raw"].map(classify_status)
            c_c = col(h, "cust_name")
            O["customer"] = h[c_c].map(norm) if c_c else ""
            O["customer_id"] = ""
            O["employee"] = ""
            O["channel"] = ""
            O["payment_method"] = ""
            O["hour"] = np.nan
            for role, out in (("order_goods", "order_goods"), ("order_disc", "order_discount"),
                              ("order_total", "order_total"), ("paid", "paid"),
                              ("debt", "debt"), ("delivery", "delivery_fee")):
                c = col(h, role)
                O[out] = h[c].map(parse_num) if c else np.nan
            L = pd.DataFrame()
            s = self._score(pd.DataFrame({"date": O["date"], "revenue": O.get("order_goods"),
                                          "item": [""] * len(O)}), O)
            if best is None or s > best[0]:
                best = (s, L, O, {name})
        if best is None:
            return None
        return best[1], best[2], best[3]

    # -------------------------------------------------- line finishing
    def _finish_lines(self, L):
        """Attach order-level attributes from the lines themselves and derive
        revenue / valid / qty_base."""
        if len(L) == 0:
            return L
        c_stat = find_col(L, *COL["status"])
        if c_stat is not None and "status" not in L.columns:
            L["status_raw"] = L[c_stat].map(norm)
            L["status"] = L["status_raw"].map(classify_status)
        if "status" not in L.columns:
            L["status_raw"] = ""
            L["status"] = ""
        c_cust = find_col(L, *COL["cust_name"])
        if c_cust is not None and "customer" not in L.columns:
            L["customer"] = L[c_cust].map(norm)
        if "customer" not in L.columns:
            L["customer"] = ""
        c_cid = find_col(L, *COL["cust_id"])
        if c_cid is not None and "customer_id" not in L.columns:
            L["customer_id"] = L[c_cid].map(norm)
        if "customer_id" not in L.columns:
            L["customer_id"] = ""
        c_emp = find_col(L, *COL["employee"])
        if c_emp is not None and "employee" not in L.columns:
            L["employee"] = L[c_emp].map(norm)
        if "employee" not in L.columns:
            L["employee"] = ""
        c_ch = find_col(L, *COL["channel"])
        if c_ch is not None and "channel" not in L.columns:
            L["channel"] = L[c_ch].map(norm)
        if "channel" not in L.columns:
            L["channel"] = ""
        c_pm = find_col(L, *COL["pay_method"])
        if c_pm is not None and "payment_method" not in L.columns:
            L["payment_method"] = L[c_pm].map(norm)
        if "payment_method" not in L.columns:
            L["payment_method"] = ""
        c_h = find_col(L, *COL["hour"])
        if c_h is not None and "hour" not in L.columns:
            L["hour"] = self._hours(L[c_h])
        if "hour" not in L.columns:
            L["hour"] = np.nan

        # item name from item_id when only the id is present
        if self.items is not None and len(self.items) and "item_id" in L.columns:
            need = L["item"] == ""
            if need.any() and getattr(self, "_item_name_by_id", None):
                L.loc[need, "item"] = L.loc[need, "item_id"].map(self._item_name_by_id).fillna("")

        L["revenue"] = L["line_amount"]
        if "unit_price" in L.columns:
            L["revenue"] = L["revenue"].fillna(L["qty"] * L["unit_price"])
        L["revenue"] = pd.to_numeric(L["revenue"], errors="coerce")
        L["valid"] = ~L["status"].isin(["cancelled", "returned"])
        # base quantity: prefer the file's own converted column
        if "qty_base" not in L.columns:
            L["qty_base"] = np.nan
        L["qty_base"] = pd.to_numeric(L["qty_base"], errors="coerce")
        if L["qty_base"].isna().all():
            L["qty_base"] = L["qty"]
        return L

    def _orders_from_lines(self, L):
        g = L.groupby("order_id", sort=False)
        O = pd.DataFrame(index=g.size().index)
        O["order_id"] = O.index
        for c in ("date", "status", "customer", "customer_id", "employee",
                  "channel", "payment_method", "hour"):
            if c in L.columns:
                O[c] = g[c].first()
        O["status_raw"] = O.get("status_raw", "")
        O["order_goods"] = g["line_amount"].sum()
        O["order_discount"] = np.nan
        O["order_total"] = np.nan
        O["paid"] = np.nan
        O["debt"] = np.nan
        O["delivery_fee"] = np.nan
        return O.reset_index(drop=True)

    # -------------------------------------------------- helpers
    def _dates(self, h, c_date, per, per_col=None):
        if not c_date:
            if per_col and per_col in h.columns:
                return pd.to_datetime(
                    [f"{y}-{m:02d}-01" for y, m in h[per_col]], errors="coerce")
            return pd.Series(pd.NaT, index=h.index)
        vals = h[c_date].tolist()
        if per_col and per_col in h.columns:
            pers = h[per_col].tolist()
        else:
            pers = [per] * len(vals)
        out = []
        for v, p in zip(vals, pers):
            out.append(self._one_date(v, p))
        return pd.Series(out, index=h.index)

    def _one_date(self, v, per):
        s = norm(str(v))
        if s == "" or s.lower() in ("nan", "none", "nat"):
            if per:
                try:
                    return pd.Timestamp(per[0], per[1], 1)
                except ValueError:
                    return pd.NaT
            return pd.NaT
        if re.fullmatch(r"\d{5}", s):
            return parse_date(s)
        d = parse_date(s)
        if pd.isna(d) and per:
            y = per[0]
            m = re.fullmatch(r"\d{1,2}[/\-.]\d{1,2}", s)
            if m:
                a, b = re.split(r"[/\-.]", s)
                try:
                    d = pd.Timestamp(int(y), int(b), int(a))
                except ValueError:
                    d = pd.NaT
            elif re.fullmatch(r"\d{1,2}", s):
                try:
                    d = pd.Timestamp(int(y), int(per[1]), int(s))
                except ValueError:
                    d = pd.NaT
            elif re.fullmatch(r"\d{1,2}[/\-.]\d{1,2}", s):
                pass
        if pd.isna(d) and per:
            try:
                d = pd.Timestamp(per[0], per[1], 1)
            except ValueError:
                pass
        return d

    def _hours(self, series):
        if series is None:
            return np.nan
        hh = series.astype(str).str.extract(r"(\d{1,2}):")[0]
        return pd.to_numeric(hh, errors="coerce")

    # -------------------------------------------------- purchases
    def _build_purchases(self):
        best = None
        for name, h in self._iter_tables(skip=self.sales_sheets):
            if len(h) < 2:
                continue
            c_item = col(h, "recv_item")
            if not c_item:
                continue
            c_qty = col(h, "recv_qty")
            c_amt = col(h, "recv_amt")
            c_date = col(h, "recv_date")
            if not (c_qty or c_amt):
                continue
            per = _sheet_period(name)
            t = pd.DataFrame()
            c_rid = col(h, "receipt_id")
            t["receipt_id"] = h[c_rid].map(norm) if c_rid else h.index.map(lambda i: f"RC{i}")
            t["date"] = self._dates(h, c_date, per)
            c_stat = col(h, "status")
            t["status_raw"] = h[c_stat].map(norm) if c_stat else ""
            t["status"] = t["status_raw"].map(classify_status)
            c_sup = col(h, "supplier")
            t["supplier"] = h[c_sup].map(norm) if c_sup else ""
            t["item"] = h[c_item].map(norm)
            t["qty"] = h[c_qty].map(parse_num) if c_qty else np.nan
            c_u = col(h, "unit")
            t["unit"] = h[c_u].map(norm) if c_u else ""
            c_p = col(h, "recv_price")
            t["price"] = h[c_p].map(parse_num) if c_p else np.nan
            t["amount"] = h[c_amt].map(parse_num) if c_amt else np.nan
            c_lot = col(h, "lot")
            t["lot"] = h[c_lot].map(norm) if c_lot else ""
            c_exp = col(h, "expiry")
            t["expiry"] = h[c_exp].map(parse_date) if c_exp else pd.NaT
            if best is None or len(t) > len(best[1]):
                best = (name, t)
        if best is None:
            return
        PL = best[1]
        self.purchase_lines = PL
        hdr = PL.groupby("receipt_id", sort=False).agg(
            date=("date", "first"), status=("status", "first"),
            supplier=("supplier", "first"), amount=("amount", "max")).reset_index()
        self.purchases = hdr

    # -------------------------------------------------- payments
    def _build_payments(self):
        best = None
        for name, h in self._iter_tables(skip=self.sales_sheets):
            if len(h) < 2:
                continue
            c_date = col(h, "pay_date")
            c_amt = col(h, "pay_amt")
            if not (c_date and c_amt):
                continue
            lkeys = " ".join(_akey(c) for c in h.columns)
            k = _akey(name)
            looks_pay = ("giatri" in lkeys or "sotienthu" in lkeys or "giatrih" in lkeys
                         or "quy" in k or "thanhtoan" in k or "phieuthu" in k
                         or "thuhien" in k or "cash" in k)
            if not looks_pay:
                continue
            per = _sheet_period(name)
            t = pd.DataFrame()
            t["date"] = self._dates(h, c_date, per)
            t["amount"] = h[c_amt].map(parse_num)
            c_oid = col(h, "pay_oid")
            t["order_id"] = h[c_oid].map(norm) if c_oid else ""
            c_m = col(h, "pay_method")
            t["method"] = h[c_m].map(norm) if c_m else ""
            if best is None or len(t) > len(best[1]):
                best = (name, t)
        self.payments = best[1] if best else pd.DataFrame()

    # -------------------------------------------------- customers
    def _build_customers(self):
        best = None
        for name, h in self._iter_tables():
            if len(h) < 2:
                continue
            c_name = col(h, "cust_master")
            if not c_name:
                continue
            c_id = col_ex(h, "cust_id", [c_name])
            c_grp = col_ex(h, "group", [c_name])
            t = pd.DataFrame()
            t["name"] = h[c_name].map(norm)
            t["customer_id"] = h[c_id].map(norm) if c_id else ""
            t["group"] = h[c_grp].map(norm) if c_grp else ""
            t = t[t["name"] != ""]
            if best is None or len(t) > len(best[1]):
                best = (name, t)
        self.customers = best[1] if best else pd.DataFrame()
