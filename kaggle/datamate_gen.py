# DataMate — sinh dữ liệu SFT bằng rejection sampling trên Kaggle.
# Chạy trong notebook: exec(open("/kaggle/working/datamate_gen.py").read())
import os, glob, json, sqlite3, re, unicodedata, signal, time
import pandas as pd, numpy as np
import torch

# ---------- 1. Dữ liệu ----------
hits = glob.glob("/kaggle/input/**/questions.jsonl", recursive=True)
hits = [h for h in hits if os.path.exists(os.path.join(os.path.dirname(h), "answers.jsonl"))]
assert hits, "Không thấy questions.jsonl + answers.jsonl trong /kaggle/input"
ROOT = os.path.dirname(hits[0])
print("ROOT =", ROOT)

def read_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

Q = read_jsonl(f"{ROOT}/questions.jsonl")
A = {a["id"]: a for a in read_jsonl(f"{ROOT}/answers.jsonl")}
RULEBOOK = open(f"{ROOT}/rulebook.md", encoding="utf-8").read()
CAL = pd.read_csv(f"{ROOT}/calendar.csv")
print(len(Q), "câu hỏi,", len(A), "đáp án")

# ---------- 2. Model ----------
# Qwen3-14B lượng tử 8-bit (Q8): ~15 GB, chia đều 2 GPU T4. Bản 16-bit gốc được nén 8-bit lúc nạp.
MODEL_TAG = "Qwen3-14B-Q8"
import warnings
warnings.filterwarnings("ignore")
if "model" in globals() and globals().get("_LOADED_TAG") != MODEL_TAG:
    raise RuntimeError("Kernel đang giữ model cũ (4-bit). Vào Run -> Restart & clear cell outputs, "
                       "chạy !pip install -q unsloth, rồi chạy lại ô này.")
if "model" not in globals():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-14B")
    model = AutoModelForCausalLM.from_pretrained(
        "Qwen/Qwen3-14B",
        quantization_config=BitsAndBytesConfig(load_in_8bit=True),
        device_map="auto",                                   # tự chia lớp ra 2 GPU
        max_memory={0: "13GiB", 1: "13GiB"},                 # chừa chỗ cho KV cache
        torch_dtype=torch.float16,                           # T4 không có bfloat16
    )
    model.eval()
    _LOADED_TAG = MODEL_TAG
    print("Đã nạp", MODEL_TAG, "| chia GPU:", sorted(set(map(str, model.hf_device_map.values()))))
model.generation_config.max_length = None

# ---------- 3. Đọc shop ----------
_RE_TR1 = re.compile(r"^(-?\d+)tr(\d{0,3})$")            # 4tr300 -> 4.300.000
_RE_TR2 = re.compile(r"^(-?\d+(?:[.,]\d+)?)tr$")           # 5,477tr -> 5.477.000
_RE_K = re.compile(r"^(-?\d+(?:[.,]\d+)?)k$")              # 20k -> 20.000
_RE_COMMA_TH = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$") # 1,301,900 / 45,000.0000
_RE_DOT_TH = re.compile(r"^-?\d{1,3}(\.\d{3})+(,\d+)?$")   # 15.000 / 1.234,5
_RE_PLAIN = re.compile(r"^-?\d+([.,]\d+)?$")
_RE_DATE = re.compile(r"^(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}|\d{4}-\d{1,2}-\d{1,2}|\d{1,2} thg \d{1,2},? \d{4})"
                      r"([ T]\d{1,2}:\d{2}(:\d{2})?)?$", re.I)

def parse_num(v):
    """Chuỗi tiền/số kiểu VN -> float; None nếu không phải số."""
    if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip().lower().replace(" ", "")
    for suf in ("vnđ", "vnd", "đ", "₫"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    if not s or re.fullmatch(r"0\d+", s):     # số điện thoại, mã có số 0 đầu: không phải số
        return None
    m = _RE_TR1.match(s)
    if m:
        return float(m.group(1)) * 1e6 + float(m.group(2).ljust(3, "0") or 0) * 1e3
    m = _RE_TR2.match(s)
    if m:
        return float(m.group(1).replace(",", ".")) * 1e6
    m = _RE_K.match(s)
    if m:
        return float(m.group(1).replace(",", ".")) * 1e3
    if _RE_COMMA_TH.match(s):
        return float(s.replace(",", ""))
    if _RE_DOT_TH.match(s):
        return float(s.replace(".", "").replace(",", "."))
    if _RE_PLAIN.match(s):
        return float(s.replace(",", "."))
    return None

_RE_QTY_UNIT = re.compile(r"^(-?\d+(?:[.,]\d+)?)\s*([^\d\s].*)?$")

def clean_df(df, year_hint=None):
    """Đổi cột chữ chứa tiền/số -> số, cột chữ chứa ngày -> datetime. Không đụng cột khác.
    year_hint: năm lấy từ tên sheet, dùng cho ngày không ghi năm (vd '12/1')."""
    df = df.copy()
    for c in list(df.columns):
        col = df[c]
        if year_hint and not (pd.api.types.is_numeric_dtype(col) or pd.api.types.is_datetime64_any_dtype(col)):
            col = col.map(lambda x: f"{x.strip()}/{year_hint}"
                          if isinstance(x, str) and re.fullmatch(r"\d{1,2}/\d{1,2}", x.strip()) else x)
        if (pd.api.types.is_numeric_dtype(col) or pd.api.types.is_datetime64_any_dtype(col)
                or pd.api.types.is_bool_dtype(col)):
            continue
        nn = col.dropna()
        nn = nn[nn.astype(str).str.strip() != ""]
        if len(nn) == 0:
            continue
        name = str(c).lower()
        if any(w in name for w in ("ngày", "ngay", "date", "hạn", "sinh nhật")):
            # Excel lưu ngày dạng số serial (45658) lẫn với chữ: đổi số serial -> yyyy-mm-dd
            def _serial(x):
                try:
                    f = float(str(x).strip())
                except ValueError:
                    return x
                if 20000 <= f <= 80000:
                    return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=f)).strftime("%Y-%m-%d %H:%M:%S")
                return x
            col = col.map(lambda x: _serial(x) if pd.notna(x) else x)
            nn = col.dropna()
            nn = nn[nn.astype(str).str.strip() != ""]
        strs = nn.astype(str).str.strip()
        # ngày
        if strs.str.match(_RE_DATE).mean() >= 0.9:
            s2 = col.astype(str).str.strip().str.replace(r"(\d{1,2}) thg (\d{1,2}),? (\d{4})", r"\3-\2-\1", regex=True)
            iso = s2.str.match(r"^\d{4}-")
            parsed = pd.Series(pd.NaT, index=col.index, dtype="datetime64[ns]")
            if iso.any():
                parsed[iso] = pd.to_datetime(s2[iso], errors="coerce", format="mixed")
            if (~iso).any():
                parsed[~iso] = pd.to_datetime(s2[~iso], errors="coerce", dayfirst=True, format="mixed")
            if parsed[nn.index].notna().mean() >= 0.9:
                df[c] = parsed
                continue
        # số / tiền
        vals = nn.map(parse_num)
        if vals.notna().mean() >= 0.95 and not all(isinstance(x, (int, float)) for x in nn):
            df[c] = col.map(lambda x: parse_num(x) if pd.notna(x) and str(x).strip() != "" else np.nan)
            if df[c].dropna().apply(float.is_integer).all():
                df[c] = df[c].astype("Int64")
            continue
        # số lượng kèm đơn vị ("5 cuộn", "1 m3", "2"): giữ cột gốc, thêm cột số và cột đơn vị
        m = strs.str.match(_RE_QTY_UNIT)
        has_unit = strs.str.contains(r"\d\s*[^\d\s,.]")
        if m.mean() >= 0.95 and has_unit.any() and (~has_unit).any() and strs.str.len().max() <= 20:
            ext = col.astype(str).str.strip().str.extract(_RE_QTY_UNIT)
            df[f"{c} (số)"] = pd.to_numeric(ext[0].str.replace(",", "."), errors="coerce")
            df[f"{c} (đơn vị ghi kèm)"] = ext[1].where(col.notna())
    return df

def fix_header(raw):
    """Sheet Excel có dòng tiêu đề/ghi chú phía trên: tìm dòng header thật."""
    raw = raw.dropna(how="all").dropna(axis=1, how="all")
    if raw.empty:
        return raw
    width = raw.notna().sum(axis=1).max()
    for i in range(min(15, len(raw))):
        row = raw.iloc[i]
        nn = row.dropna()
        if len(nn) >= max(2, 0.6 * width) and all(isinstance(x, str) for x in nn):
            cols, seen = [], {}
            for j, x in enumerate(row):
                name = str(x).strip() if pd.notna(x) else f"col{j}"
                if name in seen:
                    seen[name] += 1
                    name = f"{name}.{seen[name]}"
                else:
                    seen[name] = 0
                cols.append(name)
            df = raw.iloc[i + 1:].copy()
            df.columns = cols
            return df.reset_index(drop=True)
    raw = raw.copy()
    raw.columns = [f"col{j}" for j in range(raw.shape[1])]
    return raw.reset_index(drop=True)

def load_shop(bid):
    d = f"{ROOT}/data/{bid}"
    tables = {}
    for p in sorted(glob.glob(f"{d}/*")):
        n = os.path.basename(p)
        try:
            if n.endswith(".csv"):
                tables[n] = clean_df(pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[""]))
            elif n.endswith(".xlsx"):
                for sh, raw in pd.read_excel(p, sheet_name=None, header=None).items():
                    y = re.search(r"(20\d\d)", str(sh))
                    tables[f"{n}|{sh}"] = clean_df(fix_header(raw), y.group(1) if y else None)
            elif n.endswith((".sqlite", ".db")):
                con = sqlite3.connect(p)
                for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                    tables[f"{n}|{t}"] = clean_df(pd.read_sql(f'SELECT * FROM "{t}"', con))
                con.close()
        except Exception as e:
            print("  lỗi đọc", n, e)
    readme = open(f"{d}/README.md", encoding="utf-8").read()
    tables = merge_same(tables)
    return {k: add_status_cols(v, k) for k, v in tables.items()}, readme

def data_range(tables, readme):
    """Khoảng ngày có dữ liệu bán hàng của shop (để nhận ra câu unanswerable)."""
    m = re.search(r"có đến hết (\d{1,2}/\d{1,2}/\d{4})", readme)
    lo = None
    for k, df in tables.items():
        if "_tính_doanh_thu" in df.columns:
            for c in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[c]) and df[c].notna().any():
                    v = df[c].min()
                    lo = v if lo is None or v < lo else lo
    hi = pd.to_datetime(m.group(1), dayfirst=True) if m else None
    return lo, hi

def _nname(c):
    """Tên cột -> dạng so khớp: tách CamelCase, bỏ dấu, '_' -> ' '."""
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(c))
    return unaccent(s.replace("_", " "))

_STATUS_COL = re.compile(r"trang thai|tinh trang|status|ket qua|xu ly|ghi chu tt|tt don")
_NOTE_COL = re.compile(r"ghi chu|note|dien giai")
_ORDER_ID = re.compile(r"ma (don|hoa don|hd|phieu|chung tu|bill|giao dich|gd)\b|^so hd|order|^ma$|invoice")
_SKIP_TABLE = re.compile(r"nhap|khach|san pham|hang hoa|danh muc|chi phi|thuoc|nhan vien|nha cung cap|lo hang|the kho")

def canon_status(v):
    """Quy mọi cách ghi trạng thái về 4 trạng thái của RULEBOOK §8."""
    if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "":
        return None
    s = unaccent(v)
    if re.search(r"dang giao|dang van chuyen|dang gui|shipping|delivering|dang xu ly|processing|cho giao|cho lay", s):
        return "đang giao"
    if re.search(r"\bhuy\b|cancel|khong giao duoc|that bai|fail|bom hang", s):
        return "huỷ"
    if re.search(r"tra hang|tra lai|doi tra|hoan hang|hoan tra|tra ve|return|refund|^tra$", s):
        return "trả hàng"
    return "hoàn thành"

def add_status_cols(df, table_name=""):
    """Thêm '_trạng_thái_chuẩn' và '_tính_doanh_thu' (đơn không huỷ, không có dòng trả) cho bảng bán hàng."""
    tn = _nname(table_name)
    if _SKIP_TABLE.search(tn) and not re.search(r"hoa don|don hang|ban hang|so ban|giao dich", tn):
        return df
    cols = [c for c in df.columns if _STATUS_COL.search(_nname(c)) and not pd.api.types.is_numeric_dtype(df[c])]
    from_note = False
    if not cols:
        notes = [c for c in df.columns if _NOTE_COL.search(_nname(c)) and not pd.api.types.is_numeric_dtype(df[c])]
        if not notes:
            return df
        cols, from_note = notes[:1], True
    c = cols[0]
    st = df[c].map(canon_status)
    if from_note:                                  # §8: ghi chú không nhắc trạng thái = hoàn thành
        st = df[c].map(lambda v: canon_status(v) if canon_status(v) in ("huỷ", "trả hàng", "đang giao") else "hoàn thành")
    if not st.isin(["huỷ", "trả hàng", "đang giao"]).any():
        return df                                  # không phải cột trạng thái đơn
    ids = [x for x in df.columns if _ORDER_ID.search(_nname(x)) and not str(x).startswith("_")]
    df = df.copy()
    if ids:
        oid = df[ids[0]]
        has_id = oid.notna()
        st2 = st.copy()
        st2[has_id] = st[has_id].groupby(oid[has_id]).transform(lambda s: s.ffill().bfill())  # ô trống = giống dòng đầu đơn
        st = st2.fillna("hoàn thành")
        isbad = st.isin(["huỷ", "trả hàng"])
        bad = isbad.copy()
        bad[has_id] = isbad[has_id].groupby(oid[has_id]).transform("any")
        bad = bad.astype(bool)
        df["_trạng_thái_chuẩn"] = st
        df["_tính_doanh_thu"] = ~bad
    else:
        st = st.fillna("hoàn thành")
        df["_trạng_thái_chuẩn"] = st
        df["_tính_doanh_thu"] = ~st.isin(["huỷ", "trả hàng"])
    return df

def merge_same(tables):
    """Gộp các bảng cùng cột (mỗi tháng một sheet, file tách _1/_2) thành một bảng, thêm cột '_nguồn'."""
    groups = {}
    for k, df in tables.items():
        groups.setdefault(tuple(map(str, df.columns)), []).append(k)
    out = {}
    for sig, keys in groups.items():
        if len(keys) == 1:
            out[keys[0]] = tables[keys[0]]
            continue
        prefix = os.path.commonprefix(keys).rstrip("_|.- 0123456789")
        name = f"{prefix or keys[0]}* (gộp {len(keys)} bảng)"
        parts = []
        for k in keys:
            t = tables[k].copy()
            t["_nguồn"] = k
            parts.append(t)
        out[name] = pd.concat(parts, ignore_index=True)
    return out

def _col_info(df):
    lines = []
    for c in df.columns:
        s = df[c]
        kind = ("datetime" if pd.api.types.is_datetime64_any_dtype(s) else
                "số" if pd.api.types.is_numeric_dtype(s) else "chữ")
        info = f"    - {c!r} ({kind})"
        if kind == "chữ":
            u = s.dropna().astype(str).unique()
            if 0 < len(u) <= 15:
                info += f" giá trị: {list(u)}"
        elif kind == "datetime" and s.notna().any():
            info += f" từ {s.min()} đến {s.max()}"
        lines.append(info)
    return "\n".join(lines)

def describe(tables):
    parts, seen = [], {}
    for k, df in tables.items():
        sig = tuple(map(str, df.columns))
        if sig in seen:
            parts.append(f"- tables[{k!r}]: {len(df)} dòng, cùng cột với tables[{seen[sig]!r}]")
            continue
        seen[sig] = k
        parts.append(f"- tables[{k!r}]: {len(df)} dòng\n  Cột:\n{_col_info(df)}\n  3 dòng đầu:\n"
                     f"{df.head(3).to_string(max_colwidth=25)}")
    return "\n\n".join(parts)

# ---------- 4. Prompt + sinh code + chạy ----------
SYSTEM = """Bạn là chuyên viên phân tích dữ liệu bán hàng. Viết code Python (pandas) trả lời câu hỏi.
- Có sẵn: `tables` (dict tên bảng -> DataFrame), `TODAY` (pd.Timestamp hôm nay), `calendar` (DataFrame lịch âm dương), `pd`, `np`.
- Dữ liệu ĐÃ được làm sạch: cột ghi (datetime) là kiểu datetime64, so sánh bằng `.dt.date`, `.dt.normalize()` hoặc pd.Timestamp; cột ghi (số) đã là số (không cần bỏ dấu phẩy, chữ đ). Không tự đổi kiểu lại.
- So sánh trạng thái, tên hàng theo đúng các giá trị liệt kê ở mục Cột (chú ý hoa thường, dấu).
- Ô trống ở các dòng sau của cùng một đơn nghĩa là giống dòng đầu: dùng ffill khi cần.
- Không đọc file. Cuối code gán `result = {"type": ..., "answer": ...}`; số tiền là int (round), phần trăm làm tròn 2 chữ số.
- type thuộc: number, percent, date, boolean, string, list, table, unanswerable. Đúng format trong RULEBOOK mục 9.
- Áp dụng đúng luật trong RULEBOOK.
- Có sẵn hàm `unaccent(s)`: bỏ dấu + chữ thường, dùng để tìm tên hàng/khách gần đúng.
- Có sẵn hàm kỳ thời gian, ĐÃ tính theo TODAY và RULEBOOK — LUÔN dùng, không tự tính:
    day(0) hôm nay, day(-1) hôm qua; last_n_days(n); week_range(0) tuần này, week_range(-1) tuần trước;
    month_range() tháng này, month_range(2025, 7) tháng 7/2025; quarter_range(2025, 4) quý 4/2025; year_to_date().
    Mỗi hàm trả (start, end). Lọc: df[in_range(df['cột ngày'], start, end)].
- TRẠNG THÁI ĐƠN ĐÃ CHUẨN HOÁ SẴN — LUÔN dùng, KHÔNG tự lọc cột trạng thái gốc:
    '_trạng_thái_chuẩn' ∈ {'hoàn thành','huỷ','trả hàng','đang giao'};
    '_tính_doanh_thu' = True nếu đơn được tính doanh thu/số đơn (không huỷ, không có dòng trả hàng — đã xét cả đơn).
    Bảng chi tiết không có cột này thì nối với bảng đơn qua mã đơn rồi dùng '_tính_doanh_thu' của bảng đơn.
- Các hàm day, week_range, month_range... là hàm thường, gọi trực tiếp (không phải calendar.week_range).
- Bảng có tên kết thúc bằng "(gộp N bảng)" là nhiều sheet/file cùng cột đã gộp sẵn: dùng bảng gộp, không tự ghép sheet.

LỖI HAY GẶP — PHẢI TRÁNH:
1. Đọc đúng kỳ thời gian. "quý Q/Y" = 3 tháng (Q1: T1–T3, Q2: T4–T6, Q3: T7–T9, Q4: T10–T12), KHÔNG phải tháng Q.
   "hôm qua/hqua" = TODAY - 1 ngày; "hôm nay/bữa nay/nay" = TODAY. Luôn lọc đúng kỳ câu hỏi nói, không bỏ bước lọc ngày.
2. Câu hỏi hay viết tắt, không dấu: dthu/dt = doanh thu, bn/bao nhiu = bao nhiêu, sl = số lượng, dc/đc = được, ko/k = không.
3. "Số đơn" = số MÃ ĐƠN khác nhau (nunique), không phải số dòng.
4. Trạng thái tính theo ĐƠN: đơn có bất kỳ dòng huỷ/trả hàng thì bỏ CẢ đơn (lấy tập mã đơn bị loại rồi loại theo mã).
   Dùng đúng giá trị trạng thái có trong dữ liệu (xem mục Cột), không tự đặt 'huỷ'/'trả hàng'.
5. type đúng với câu hỏi: hỏi "bao nhiêu tiền/đơn/cái" là number; chỉ dùng percent khi câu hỏi hỏi %, tỉ lệ, tăng trưởng.
6. Giá bán một đơn vị cơ bản: dòng bán theo đơn vị lớn thì đơn giá / (số lượng quy đổi / số lượng).
7. Tên hàng trong câu hỏi có thể khác cách viết: so khớp bằng unaccent trước khi kết luận không có.
   Chỉ trả unanswerable khi dữ liệu thật sự không có loại thông tin cần, hoặc kỳ hỏi nằm hoàn toàn ngoài dữ liệu.
8. Tháng 2 có 28 hoặc 29 ngày: dùng month_range, không tự gõ ngày cuối tháng.
9. pandas mới KHÔNG có DataFrame.append: dùng pd.concat([...]).
10. Trước khi tính, kiểm tra kỳ hỏi có nằm trong khoảng ngày có dữ liệu không (xem 'từ ... đến ...' ở mục Cột, README).
    Kỳ nằm HOÀN TOÀN ngoài dữ liệu, hoặc shop không ghi loại thông tin cần (vd. không có tồn kho, giá vốn) -> unanswerable.
11. Lọc trạng thái CHỈ bằng các giá trị liệt kê ở mục Cột; giá trị không có trong danh sách là sai.
12. Bảng đơn (header) và bảng chi tiết (dòng hàng) nối qua mã đơn. Doanh thu = tổng thành tiền dòng hàng (RULEBOOK §1).

13. Không viết số có số 0 ở đầu (07, 01): dùng pd.Timestamp(2025, 7, 1) hoặc chuỗi '2025-07-01'.

Mở đầu code bằng 3 dòng comment: KỲ: <ngày bắt đầu → ngày kết thúc>; ĐẠI LƯỢNG: <cần tính gì>; TYPE: <type>.
Sau đó viết code NGẮN GỌN: KHÔNG thêm comment nào khác, KHÔNG import (pd, np đã có), KHÔNG giải thích ngoài khối code.
Chỉ trả về đúng một khối ```python```."""

def build_messages(q, readme, schema, rng=(None, None)):
    lo, hi = rng
    rng_txt = (f"KHOẢNG DỮ LIỆU BÁN HÀNG CỦA SHOP: từ {lo.date() if lo is not None else '?'} "
               f"đến {hi.date() if hi is not None else '?'}. Kỳ hỏi nằm hoàn toàn ngoài khoảng này -> unanswerable.")
    user = (f"# RULEBOOK\n{RULEBOOK}\n\n# README của shop\n{readme}\n\n# Các bảng\n{schema}\n\n{rng_txt}\n\n"
            f"# Câu hỏi\nHôm nay: {q['as_of_date']}\n{q['question']}")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]

def gen(messages, max_new=1200):
    text = tokenizer.apply_chat_template(messages, tokenize=False,
                                         add_generation_prompt=True, enable_thinking=False)
    inp = tokenizer(text, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        out = model.generate(**inp, max_new_tokens=max_new, do_sample=False)
    return tokenizer.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True), inp["input_ids"].shape[1]

def gen_batch(list_msgs, max_new=1200):
    """Sinh cho nhiều prompt cùng lúc (GPU gần như không chậm thêm). Hết bộ nhớ thì tự chia đôi."""
    if len(list_msgs) == 1:
        o, n = gen(list_msgs[0], max_new)
        return [o], [n]
    texts = [tokenizer.apply_chat_template(m, tokenize=False, add_generation_prompt=True,
                                           enable_thinking=False) for m in list_msgs]
    tokenizer.padding_side = "left"
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    try:
        enc = tokenizer(texts, return_tensors="pt", padding=True).to(model.device)
        with torch.inference_mode():
            out = model.generate(**enc, max_new_tokens=max_new, do_sample=False,
                                 pad_token_id=tokenizer.pad_token_id)
    except torch.cuda.OutOfMemoryError:
        del enc
        torch.cuda.empty_cache()
        h = len(list_msgs) // 2
        print(f"   (hết bộ nhớ với {len(list_msgs)} câu, chia đôi)")
        a, na = gen_batch(list_msgs[:h], max_new)
        b, nb = gen_batch(list_msgs[h:], max_new)
        return a + b, na + nb
    L = enc["input_ids"].shape[1]
    outs = [tokenizer.decode(o[L:], skip_special_tokens=True) for o in out]
    return outs, [int(x) for x in enc["attention_mask"].sum(1)]

def extract_code(s):
    m = re.search(r"```python\s*\n(.*?)```", s, re.S)
    return m.group(1) if m else None

# ---- Hàm kỳ thời gian có sẵn cho model (trả về (start, end) là pd.Timestamp 00:00, gồm cả 2 đầu) ----
def make_period_helpers(today):
    T = pd.Timestamp(today).normalize()
    def day(offset=0):                       # day(0)=hôm nay, day(-1)=hôm qua
        d = T + pd.Timedelta(days=offset); return d, d
    def last_n_days(n):                      # n ngày gần nhất, kể cả hôm nay
        return T - pd.Timedelta(days=n - 1), T
    def week_range(offset=0):                # 0 = tuần này (thứ Hai -> hôm nay), -1 = tuần trước (T2 -> CN)
        s = T - pd.Timedelta(days=T.weekday()) + pd.Timedelta(weeks=offset)
        return s, (T if offset == 0 else s + pd.Timedelta(days=6))
    def month_range(year=None, month=None):  # không truyền = tháng này (ngày 1 -> hôm nay)
        if year is None:
            return T.replace(day=1), T
        s = pd.Timestamp(year=year, month=month, day=1)
        return s, s + pd.offsets.MonthEnd(0)
    def quarter_range(year, q):              # quý theo dương lịch
        s = pd.Timestamp(year=year, month=3 * q - 2, day=1)
        return s, s + pd.offsets.QuarterEnd(0)
    def year_to_date():
        return T.replace(month=1, day=1), T
    def in_range(series, start, end):        # lọc cột datetime theo ngày, gồm cả start và end
        d = pd.to_datetime(series).dt.normalize()
        return (d >= start) & (d <= end)
    return dict(day=day, last_n_days=last_n_days, week_range=week_range, month_range=month_range,
                quarter_range=quarter_range, year_to_date=year_to_date, in_range=in_range)

def unaccent(s):
    s = unicodedata.normalize("NFD", str(s).replace("đ", "d").replace("Đ", "D"))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return " ".join(s.lower().split())

def looks_bad(res, err):
    """Kết quả đáng ngờ -> cho model thử lại."""
    if err:
        return f"Code bị lỗi: {err}"
    if not isinstance(res, dict) or "type" not in res:
        return "Code không gán biến result đúng dạng {'type': ..., 'answer': ...}."
    a = res.get("answer")
    if res["type"] != "unanswerable" and (a is None or (isinstance(a, (int, float)) and a == 0)
                                          or (hasattr(a, "__len__") and len(a) == 0)):
        return (f"Kết quả là {a!r} — rất có thể bước lọc đang ra bảng rỗng (sai giá trị trạng thái, "
                f"sai kỳ, sai tên hàng). Hãy kiểm tra lại từng bước lọc.")
    return None

class Timeout(Exception):
    pass

def _alarm(*_):
    raise Timeout()

def run(code, tables, today, timeout=20):
    env = {"tables": {k: v.copy() for k, v in tables.items()}, "TODAY": pd.Timestamp(today),
           "calendar": CAL.copy(), "pd": pd, "np": np, "unaccent": unaccent,
           **make_period_helpers(today)}
    has_alarm = hasattr(signal, "SIGALRM")          # Linux (Kaggle) có, Windows không
    if has_alarm:
        signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(timeout)
    try:
        exec(code, env)
        return env.get("result"), None
    except Exception as e:
        return None, repr(e)[:300]
    finally:
        if has_alarm:
            signal.alarm(0)

# ---------- 5. Chấm theo luật BTC ----------
def norm(s):
    s = unicodedata.normalize("NFC", str(s)).lower()
    s = re.sub(r"[^\w\s]|_", " ", s)
    return " ".join(s.split())

def eq_val(p, g, alias=()):
    if isinstance(g, bool):
        return isinstance(p, (bool, np.bool_)) and bool(p) == g
    if isinstance(g, (int, float)):
        try:
            return abs(float(p) - float(g)) < 1e-6
        except Exception:
            return False
    if isinstance(g, str):
        return norm(p) in {norm(x) for x in [g, *alias]}
    return p == g

def correct(pred, gold):
    if not isinstance(pred, dict) or pred.get("type") != gold["type"]:
        return False
    t, p, g, al = gold["type"], pred.get("answer"), gold["answer"], gold.get("alias") or []
    if t == "unanswerable":
        return True
    if t == "percent":
        try:
            return round(float(p), 2) == round(float(g), 2)
        except Exception:
            return False
    if t == "list":
        return isinstance(p, (list, tuple)) and len(p) == len(g) and all(eq_val(x, y, al) for x, y in zip(p, g))
    if t == "table":
        try:
            key = lambda r: tuple(norm(x) if isinstance(x, str) else round(float(x), 2) for x in r)
            return sorted(map(key, p["rows"])) == sorted(map(key, g["rows"]))
        except Exception:
            return False
    return eq_val(p, g, al)

# ---------- 6. Vòng lặp ----------
VAL_SHOPS = {"biz_126", "biz_127", "biz_128", "biz_129", "biz_130"}
OUT = "/kaggle/working/sft_raw_q8.jsonl"

import random
_SHOP = {}

def get_shop(bid):
    if bid not in _SHOP:
        _SHOP.clear()                      # chỉ giữ 1 shop trong RAM
        tables, readme = load_shop(bid)
        _SHOP[bid] = (tables, readme, describe(tables), data_range(tables, readme))
    return _SHOP[bid]

def solve(q, max_retry=1):
    """Sinh code, chạy; nếu lỗi / kết quả rỗng thì gửi lỗi lại cho model sửa (không dùng đáp án)."""
    tables, readme, schema, rng = get_shop(q["business_id"])
    msgs = build_messages(q, readme, schema, rng)
    attempts = []
    for k in range(max_retry + 1):
        out, ntok = gen(msgs)
        code = extract_code(out)
        res, err = run(code, tables, q["as_of_date"]) if code else (None, "không có khối ```python```")
        attempts.append({"code": code, "pred": res, "err": err})
        bad = looks_bad(res, err)
        if not bad or k == max_retry:
            break
        msgs = msgs + [{"role": "assistant", "content": out},
                       {"role": "user", "content": bad + " Viết lại toàn bộ code đã sửa."}]
    return attempts, ntok

def solve_many(qs, max_retry=1):
    """Như solve() nhưng chạy nhiều câu CÙNG SHOP một lượt; câu cần sửa được gom lại sửa chung."""
    tables, readme, schema, rng = get_shop(qs[0]["business_id"])
    msgs = [build_messages(q, readme, schema, rng) for q in qs]
    attempts = [[] for _ in qs]
    ntoks = [0] * len(qs)
    active = list(range(len(qs)))
    for k in range(max_retry + 1):
        outs, ns = gen_batch([msgs[i] for i in active])
        nxt = []
        for i, out, n in zip(active, outs, ns):
            ntoks[i] = n
            code = extract_code(out)
            res, err = run(code, tables, qs[i]["as_of_date"]) if code else (None, "không có khối ```python```")
            attempts[i].append({"code": code, "pred": res, "err": err})
            bad = looks_bad(res, err)
            if bad and k < max_retry:
                msgs[i] = msgs[i] + [{"role": "assistant", "content": out},
                                     {"role": "user", "content": bad + " Viết lại toàn bộ code đã sửa."}]
                nxt.append(i)
        active = nxt
        if not active:
            break
    return attempts, ntoks

def run_batch(limit=200, seed=0, max_retry=1, batch=4):
    """batch = số câu (cùng shop) cho model làm cùng lúc. Hết bộ nhớ GPU thì giảm xuống 2."""
    pool = [q for q in Q if q["business_id"] not in VAL_SHOPS]
    random.Random(seed).shuffle(pool)                       # lấy ngẫu nhiên nhiều shop
    done = {json.loads(l)["id"] for l in open(OUT, encoding="utf-8")} if os.path.exists(OUT) else set()
    todo = sorted([q for q in pool if q["id"] not in done][:limit], key=lambda q: q["business_id"])
    groups = []
    for q in todo:                                          # nhóm theo shop, mỗi nhóm <= batch câu
        if groups and groups[-1][0]["business_id"] == q["business_id"] and len(groups[-1]) < batch:
            groups[-1].append(q)
        else:
            groups.append([q])
    n = n_ok = 0
    t_all = time.time()
    with open(OUT, "a", encoding="utf-8") as f:
        for g in groups:
            t0 = time.time()
            all_attempts, ntoks = solve_many(g, max_retry)
            dt = (time.time() - t0) / len(g)
            for q, attempts, ntok in zip(g, all_attempts, ntoks):
                last = attempts[-1]
                ok = correct(last["pred"], A[q["id"]])
                n += 1
                n_ok += ok
                f.write(json.dumps({"id": q["id"], "business_id": q["business_id"], "ok": ok,
                                    "code": last["code"], "pred": last["pred"], "err": last["err"],
                                    "n_attempts": len(attempts), "attempts": attempts, "prompt_tokens": ntok},
                                   ensure_ascii=False, default=str) + "\n")
                f.flush()
                print(f"{n:3d} {q['id']} {q['business_id']} tok={ntok} try={len(attempts)} ok={ok} "
                      f"~{dt:.0f}s/câu acc={n_ok/n:.1%}"
                      + (f" err={str(last['err'])[:80]}" if last["err"] else ""))
    print(f"XONG {n} câu, đúng {n_ok} ({n_ok/max(n,1):.1%}), trung bình {(time.time()-t_all)/max(n,1):.0f}s/câu")

def show_wrong(path=None, k=10):
    """In các câu sai gần nhất để xem lỗi."""
    r = [json.loads(l) for l in open(path or OUT, encoding="utf-8")]
    QD = {q["id"]: q for q in Q}
    print(len(r), "câu, đúng", sum(x["ok"] for x in r))
    for x in [x for x in r if not x["ok"]][-k:]:
        g = A[x["id"]]
        print("=" * 80)
        print("Q   :", QD[x["id"]]["question"], "| hôm nay:", QD[x["id"]]["as_of_date"], "|", x["business_id"])
        print("GOLD:", g["type"], g["answer"])
        print("PRED:", x["pred"])
        print("ERR :", x["err"])
        print("CODE:\n" + (x["code"] or "(không có code)"))

print("Sẵn sàng. run_batch(20) để thử, show_wrong() để xem câu sai.")
