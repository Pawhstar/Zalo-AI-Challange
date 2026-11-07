"""Price-increase effect queries (rulebook §5 'Hiệu ứng tăng giá').

Rulebook §5:
  * A price-increase event on day D is when the new price in the price table is
    strictly higher than the immediately preceding price for that item; if the
    item is raised to the same price multiple times, take the first occurrence.
    The question may also state D (and/or the new price) explicitly.
  * Compare the total quantity sold (converted to the item's base unit,
    excluding cancelled and returned orders) in the N days starting from D
    (inclusive: [D, D + N - 1]) against the N days immediately before D
    ([D - N, D - 1]).
  * Return the percentage change rounded to 2 decimal places.

Tag format: 'pe:<kind>:<type>'.
"""
import re
import numpy as np
import pandas as pd

from datamate.fold import fold, normq
from datamate.periods import round2
from datamate import loader


def _ikey(s):
    if s is None:
        return ""
    s = fold(str(s))
    s = re.sub(r"(\d)\s+(ml|mg|g|kg|l)\b", r"\1\2", s)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def _header_keys(raw):
    if isinstance(raw, pd.DataFrame):
        out = [_ikey(c) for c in raw.columns]
        for i in range(min(5, len(raw))):
            out.extend(_ikey(v) for v in raw.iloc[i].values if pd.notna(v))
        return out
    if isinstance(raw, list) and len(raw) > 0:
        out = []
        for row in raw[:5]:
            if isinstance(row, (list, tuple)):
                out.extend(_ikey(x) for x in row if x is not None and str(x).strip() != "")
        return out
    return []


def _ctx(b):
    c = getattr(b, "_pe_ctx", None)
    if c is not None:
        return c

    id_to_name = {}
    key_to_id = {}
    key_to_name = {}

    if len(b.items):
        for _, r in b.items.iterrows():
            nm = str(r.get("item", "")).strip()
            iid = str(r.get("item_id", "")).strip()
            if nm and nm.lower() != "nan":
                k = _ikey(nm)
                key_to_name.setdefault(k, nm)
                if iid and iid.lower() != "nan":
                    id_to_name.setdefault(iid, nm)
                    key_to_id.setdefault(k, iid)

    for k, v in (getattr(b, "_item_name_by_id", {}) or {}).items():
        iid, nm = str(k).strip(), str(v).strip()
        if iid and nm:
            id_to_name.setdefault(iid, nm)
            key_to_id.setdefault(_ikey(nm), iid)

    price_rows = []
    for tname, raw in b.sheets.items():
        hkeys = _header_keys(raw)
        joined = " | ".join(hkeys)
        is_price = ("ngay ap dung" in joined or "ngayapdung" in joined) and (
            "gia moi" in joined or "giamoi" in joined or "giabanle" in joined or "gia ban" in joined
        )
        is_master_item = (
            any(k in hkeys for k in ("ma sku", "masku", "ma hang hoa", "mahanghoa", "ma sp", "masp", "ma mon", "mamon", "ma san pham", "masanpham"))
            and any(k in hkeys for k in ("ten san pham", "tensanpham", "ten goi", "tengoi", "mon", "ten hang", "tenhang", "san pham", "sanpham"))
            and (isinstance(raw, pd.DataFrame) and len(raw) <= 500 or isinstance(raw, list) and len(raw) <= 505)
        )
        if not is_price and not is_master_item:
            continue

        h = loader.df_from_sheet(raw)
        if len(h) == 0:
            continue
        cols = {_ikey(col): col for col in h.columns}

        if is_master_item and len(h) <= 500:
            c_id = next((cols[k] for k in cols if k in ("ma sku", "masku", "ma hang hoa", "mahanghoa", "ma sp", "masp", "ma mon", "mamon", "ma san pham", "masanpham")), None)
            c_nm = next((cols[k] for k in cols if k in ("ten san pham", "tensanpham", "ten goi", "tengoi", "mon", "ten hang", "tenhang", "san pham", "sanpham")), None)
            if c_id and c_nm:
                for _, r in h.iterrows():
                    iid = str(r[c_id]).strip()
                    nm = str(r[c_nm]).strip()
                    if iid and nm and iid.lower() != "nan" and nm.lower() != "nan":
                        id_to_name[iid] = nm
                        k = _ikey(nm)
                        key_to_name[k] = nm
                        key_to_id[k] = iid

        if is_price:
            c_date = next((cols[k] for k in cols if "ngay ap dung" in k or "ngay doi" in k or "ngay tang" in k or k == "ngayapdung"), None)
            c_new = next((cols[k] for k in cols if "gia moi" in k or "giabanle" in k or "gia ban le" in k or "giamoi" in k or "gia ban" in k), None)
            c_old = next((cols[k] for k in cols if "gia cu" in k or "giacu" in k), None)
            c_name = next((cols[k] for k in cols if k in ("ten hang", "tenhang", "san pham", "sanpham", "mat hang", "ten mon", "hang hoa")), None)
            c_id = next((cols[k] for k in cols if k in ("ma san pham", "masanpham", "ma hang hoa", "mahanghoa", "ma hang", "mahang", "ma mon", "mamon", "sku", "ma sku")), None)
            if c_date and c_new:
                for _, r in h.iterrows():
                    d = loader.parse_date(r[c_date])
                    if pd.isna(d):
                        continue
                    d = pd.Timestamp(d).normalize()
                    p_new = loader.parse_num(r[c_new])
                    if pd.isna(p_new):
                        continue
                    p_old = loader.parse_num(r[c_old]) if c_old else np.nan
                    iid = str(r[c_id]).strip() if c_id and not pd.isna(r[c_id]) else ""
                    nm = str(r[c_name]).strip() if c_name and not pd.isna(r[c_name]) else ""
                    ik = _ikey(nm) if nm else _ikey(id_to_name.get(iid, ""))
                    if not iid and ik in key_to_id:
                        iid = key_to_id[ik]
                    price_rows.append((ik, iid, d, float(p_new), None if pd.isna(p_old) else float(p_old)))

    L = b.lines
    if len(L):
        for nm in L["item"].dropna().unique():
            s = str(nm).strip()
            if s:
                k = _ikey(s)
                key_to_name.setdefault(k, s)

    candidates = []
    for k, nm in key_to_name.items():
        if len(k) >= 2:
            iid = key_to_id.get(k, "")
            canon_nm = id_to_name.get(iid, nm) if iid else nm
            candidates.append((k, canon_nm, iid))
    candidates.sort(key=lambda x: len(x[0]), reverse=True)

    c = {
        "candidates": candidates,
        "price_rows": price_rows,
        "L_day": pd.to_datetime(L["date"], errors="coerce").dt.normalize() if len(L) else None,
        "L_ikey": L["item"].fillna("").map(_ikey) if len(L) else None,
        "L_iid": L["item_id"].fillna("").astype(str).str.strip() if len(L) and "item_id" in L.columns else None,
        "L_valid": L["valid"].fillna(False).astype(bool) if len(L) else None,
    }
    b._pe_ctx = c
    return c


def _match_item(c, q):
    qf = _ikey(q)
    for k, nm, iid in c["candidates"]:
        if re.search(r"(^|\s)" + re.escape(k) + r"(\s|$)", qf):
            return nm, iid, k
    return None, "", ""


def _find_increase_date(c, item_id, item_key, target_price, T):
    rows = []
    for ik, iid, d, p_new, p_old in c["price_rows"]:
        if d > T:
            continue
        if (item_id and iid == item_id) or (item_key and ik == item_key):
            rows.append((d, p_new, p_old))
    if not rows:
        return None
    rows.sort(key=lambda x: x[0])
    prev_p = None
    for d, p_new, p_old in rows:
        old_val = p_old if p_old is not None else prev_p
        is_inc = old_val is not None and p_new > old_val
        prev_p = p_new
        if is_inc:
            if target_price is None or abs(p_new - target_price) < 1e-2:
                return d
    return None


def try_answer(b, q, as_of):
    qn = normq(q)
    qf = fold(q)
    if not re.search(r"tang gia|len gia|doi gia|gia moi|dieu chinh gia", qn):
        return None

    m_n = re.search(r"(\d+)\s*ngay\s*(?:dau\s*)?(?:ke tu|sau|tiep theo|dau tien)", qn)
    if not m_n:
        m_n = re.search(r"trong\s*(\d+)\s*ngay\s*ke tu", qn)
    if not m_n:
        m_n = re.search(r"(\d+)\s*ngay\s*ngay\s*truoc|(\d+)\s*ngay\s*lien\s*truoc|(\d+)\s*ngay\s*truoc\s*do", qn)
    if not m_n:
        return None
    N = int(next(g for g in m_n.groups() if g is not None))

    if len(b.lines) == 0:
        return None

    c = _ctx(b)
    item, item_id, item_key = _match_item(c, q)
    if not item:
        return None

    T = pd.Timestamp(as_of).normalize()

    D = None
    m_d = re.search(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](20\d{2})(?!\d)", q)
    if m_d:
        try:
            D = pd.Timestamp(int(m_d.group(3)), int(m_d.group(2)), int(m_d.group(1))).normalize()
        except ValueError:
            D = None
    else:
        m_d2 = re.search(r"(?<!\d)(20\d{2})-(\d{1,2})-(\d{1,2})(?!\d)", q)
        if m_d2:
            try:
                D = pd.Timestamp(int(m_d2.group(1)), int(m_d2.group(2)), int(m_d2.group(3))).normalize()
            except ValueError:
                D = None

    if D is None:
        target_p = None
        for m_p in re.finditer(r"(?:len gia|tang gia len|len|gia moi|muc)\s*([\d.,]+\s*(?:nghin|ngan|k|tr|trieu)?)", qf):
            val = loader.parse_num(m_p.group(1))
            if not pd.isna(val) and val > 100:
                target_p = float(val)
                break
        D = _find_increase_date(c, item_id, item_key, target_p, T)

    if D is None:
        return None

    L = b.lines
    ld = c["L_day"]
    item_mask = c["L_ikey"] == item_key
    if item_id and c["L_iid"] is not None:
        item_mask = item_mask | (c["L_iid"] == item_id)
    mask = c["L_valid"] & item_mask

    after_start = D
    after_end = min(D + pd.Timedelta(days=N - 1), T)
    before_start = D - pd.Timedelta(days=N)
    before_end = D - pd.Timedelta(days=1)

    q_after = L.loc[mask & (ld >= after_start) & (ld <= after_end), "qty_base"].fillna(0).sum()
    q_before = L.loc[mask & (ld >= before_start) & (ld <= before_end), "qty_base"].fillna(0).sum()
    if q_before == 0:
        return None

    pct = round2(100.0 * (q_after - q_before) / q_before)
    return "percent", pct, "pe:change:percent"
