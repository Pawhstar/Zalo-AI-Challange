"""Pharmacy lot & expiry queries (rulebook §6 'Nhà thuốc').

Rulebook §6:
  * Lots expiring within the next N days (as of day D): lots with remaining
    stock > 0 whose expiry date falls in [D, D + N] (inclusive).
  * Capital tied up in expiring lots ('tiền vốn'): value of the remaining
    quantity of each expiring lot, valued at that specific lot's purchase price
    converted to the base unit (not average cost).
  * Nearest-expiry lot of a medicine ('lô gần hết hạn nhất'): among lots of that
    medicine with remaining stock > 0 that have not yet expired as of D
    (expiry >= D), the earliest expiry date.
  * Listing items by expiry (rulebook §9): ordered by each item's earliest
    expiry date within the window ascending, then by item code ascending.
  * If a business has no lot/expiry records, lot/expiry questions are
    unanswerable (rulebook §7).

Tag format: 'lot:<kind>:<type>'.
"""
import re
import numpy as np
import pandas as pd

from datamate.fold import fold, normq
from datamate.periods import round_money
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
    c = getattr(b, "_lot_ctx", None)
    if c is not None:
        return c

    # Quick check whether any sheet has lot/expiry columns
    has_lot_sheet = False
    for _, raw in b.sheets.items():
        hkeys = set(_header_keys(raw))
        if hkeys & {"ma lo", "malo", "lo"} and hkeys & {"han su dung", "hansudung", "hsd"}:
            has_lot_sheet = True
            break

    if not has_lot_sheet:
        c = {"has_lots": False}
        b._lot_ctx = c
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

    po_date = {}
    po_valid = {}
    lot_amount = {}
    lot_def_sheets = []
    lot_sale_sheets = []

    for tname, raw in b.sheets.items():
        hkeys = _header_keys(raw)
        hset = set(hkeys)

        is_master_item = (
            bool(hset & {"ma sku", "masku", "ma hang hoa", "mahanghoa", "ma sp", "masp", "ma mon", "mamon", "ma san pham", "masanpham"})
            and bool(hset & {"ten san pham", "tensanpham", "ten goi", "tengoi", "mon", "ten hang", "tenhang", "san pham", "sanpham"})
            and (isinstance(raw, pd.DataFrame) and len(raw) <= 500 or isinstance(raw, list) and len(raw) <= 505)
        )
        is_po_hdr = bool(hset & {"ma don nhap", "madonnhap", "ma phieu nhap", "maphieunhap", "so phieu", "sophieu"}) and bool(
            hset & {"ngay nhap", "ngaynhap", "ngay nhap kho", "ngaynhapkho"}
        )
        is_sotay = ("lo" in hset and "thanh tien" in hset)
        is_lot_def = (
            bool(hset & {"ma lo", "malo", "lo"})
            and bool(hset & {"han su dung", "hansudung", "hsd"})
            and bool(hset & {"so luong nhap", "soluongnhap", "sl nhap quy doi", "slnhapquydoi", "sl nhap dvt co ban"})
            and bool(hset & {"ma sku", "masku", "ma hang hoa", "mahanghoa", "ma mon", "mamon"})
        )
        is_lot_sale = (
            bool(hset & {"ma lo", "malo", "lo"})
            and bool(hset & {"ma don hang", "madonhang", "ma hoa don", "mahoadon"})
            and bool(hset & {"so luong", "soluong", "sl quy doi", "slquydoi", "sl quy ra le"})
        )

        if not (is_master_item or is_po_hdr or is_sotay or is_lot_def or is_lot_sale):
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

        if is_po_hdr:
            c_po = next((cols[k] for k in cols if k in ("ma don nhap", "madonnhap", "ma phieu nhap", "maphieunhap", "so phieu", "sophieu")), None)
            c_dt = next((cols[k] for k in cols if k in ("ngay nhap", "ngaynhap", "ngay nhap kho", "ngaynhapkho")), None)
            c_st = next((cols[k] for k in cols if k in ("tinh trang", "tinhtrang", "trang thai", "trangthai")), None)
            if c_po and c_dt:
                for _, r in h.iterrows():
                    pid = str(r[c_po]).strip()
                    d = loader.parse_date(r[c_dt])
                    if pid and not pd.isna(d):
                        po_date[pid] = pd.Timestamp(d).normalize()
                    if pid and c_st:
                        st = loader.classify_status(r[c_st])
                        po_valid[pid] = (st != "cancelled")

        if is_sotay:
            c_lo = cols["lo"]
            c_tt = cols["thanh tien"]
            for _, r in h.iterrows():
                lid = str(r[c_lo]).strip()
                tt = loader.parse_num(r[c_tt])
                if lid and not pd.isna(tt):
                    lot_amount[lid] = float(tt)

        if is_lot_def:
            lot_def_sheets.append((h, cols))

        if is_lot_sale:
            lot_sale_sheets.append((h, cols))

    lots = {}
    for h, cols in lot_def_sheets:
        c_lo = next((cols[k] for k in cols if k in ("ma lo", "malo", "lo")), None)
        c_exp = next((cols[k] for k in cols if k in ("han su dung", "hansudung", "hsd")), None)
        c_qty = next((cols[k] for k in cols if k in ("so luong nhap", "soluongnhap", "sl nhap quy doi", "slnhapquydoi", "sl nhap dvt co ban")), None)
        c_id = next((cols[k] for k in cols if k in ("ma sku", "masku", "ma hang hoa", "mahanghoa", "ma mon", "mamon")), None)
        c_po = next((cols[k] for k in cols if k in ("ma don nhap", "madonnhap", "ma phieu nhap", "maphieunhap")), None)
        c_cost = next((cols[k] for k in cols if k in ("don gia nhap", "dongianhap")), None)
        for _, r in h.iterrows():
            lid = str(r[c_lo]).strip()
            if not lid or lid.lower() == "nan":
                continue
            pid = str(r[c_po]).strip() if c_po else ""
            if pid in po_valid and not po_valid[pid]:
                continue
            exp = loader.parse_date(r[c_exp])
            if pd.isna(exp):
                continue
            exp = pd.Timestamp(exp).normalize()
            qin = loader.parse_num(r[c_qty])
            if pd.isna(qin):
                continue
            iid = str(r[c_id]).strip()
            nm = id_to_name.get(iid, iid)
            ucost = loader.parse_num(r[c_cost]) if c_cost else np.nan
            if pd.isna(ucost) and lid in lot_amount and qin > 0:
                ucost = lot_amount[lid] / float(qin)
            lots[lid] = {
                "lot_id": lid,
                "item_id": iid,
                "item": nm,
                "item_key": _ikey(nm),
                "expiry": exp,
                "qty_in": float(qin),
                "unit_cost": float(ucost) if not pd.isna(ucost) else np.nan,
                "po_date": po_date.get(pid, pd.Timestamp.min),
            }

    if not lots:
        c = {"has_lots": False}
        b._lot_ctx = c
        return c

    # Map order_id -> order_date for non-cancelled orders
    O = b.orders
    ord_date = {}
    if len(O):
        od = pd.to_datetime(O["date"], errors="coerce").dt.normalize()
        statuses = O["status"] if "status" in O.columns else [""] * len(O)
        for oid, d, st in zip(O["order_id"], od, statuses):
            if pd.isna(d):
                continue
            if loader.classify_status(st) != "cancelled":
                ord_date[str(oid).strip()] = d

    # Pre-aggregate lot sales by (lot_id, order_date)
    sales_rows = []
    for h, cols in lot_sale_sheets:
        c_lo = next((cols[k] for k in cols if k in ("ma lo", "malo", "lo")), None)
        c_oid = next((cols[k] for k in cols if k in ("ma don hang", "madonhang", "ma hoa don", "mahoadon")), None)
        c_q = next((cols[k] for k in cols if k in ("so luong", "soluong", "sl quy doi", "slquydoi", "sl quy ra le")), None)
        c_ret = next((cols[k] for k in cols if k in ("so luong tra", "soluongtra", "sl tra quy doi", "sltraquydoi", "sl tra dvt co ban")), None)
        lids = h[c_lo].astype(str).str.strip()
        oids = h[c_oid].astype(str).str.strip()
        qs_val = pd.to_numeric(h[c_q], errors="coerce").fillna(0.0)
        qret_val = pd.to_numeric(h[c_ret], errors="coerce").fillna(0.0) if c_ret else pd.Series(0.0, index=h.index)
        net_q = qs_val - qret_val
        odates = oids.map(ord_date)
        valid_mask = odates.notna() & lids.isin(lots) & (net_q != 0)
        if valid_mask.any():
            sub = pd.DataFrame({
                "lot_id": lids[valid_mask],
                "day": odates[valid_mask],
                "net_q": net_q[valid_mask],
            })
            sales_rows.append(sub.groupby(["lot_id", "day"], as_index=False)["net_q"].sum())

    sales_df = pd.concat(sales_rows, ignore_index=True) if sales_rows else pd.DataFrame(columns=["lot_id", "day", "net_q"])

    candidates = []
    for k, nm in key_to_name.items():
        if len(k) >= 2:
            iid = key_to_id.get(k, "")
            canon_nm = id_to_name.get(iid, nm) if iid else nm
            candidates.append((k, canon_nm, iid))
    candidates.sort(key=lambda x: len(x[0]), reverse=True)

    c = {
        "has_lots": True,
        "lots": lots,
        "sales_df": sales_df,
        "candidates": candidates,
    }
    b._lot_ctx = c
    return c


def _lots_as_of(c, T):
    s = c["sales_df"]
    if len(s):
        sold = s[s["day"] <= T].groupby("lot_id")["net_q"].sum().to_dict()
    else:
        sold = {}
    out = []
    for lid, info in c["lots"].items():
        if info["po_date"] > T:
            continue
        rem = info["qty_in"] - sold.get(lid, 0.0)
        if rem > 1e-6:
            d = dict(info)
            d["rem"] = rem
            out.append(d)
    return out


def _match_item(c, q):
    qf = _ikey(q)
    for k, nm, iid in c["candidates"]:
        if re.search(r"(^|\s)" + re.escape(k) + r"(\s|$)", qf):
            return nm, iid, k
    return None, "", ""


def try_answer(b, q, as_of):
    qn = normq(q)
    # Trigger only on lot/expiry questions
    is_nearest = bool(re.search(r"gan het han nhat|het han som nhat|date gan nhat", qn))
    is_expiring = bool(
        re.search(
            r"het han trong\s*\d+\s*(?:ngay|thang)|sap het han|lo con ton.*han dung|"
            r"lo hang con ton.*het han|con lo ton.*het han|co han dung tu|han dung tu",
            qn,
        )
    )
    if not (is_nearest or is_expiring):
        return None

    c = _ctx(b)
    if not c.get("has_lots"):
        return "unanswerable", {"reason": "the shop records no lot expiry data"}, "lot:no_data:unanswerable"

    T = pd.Timestamp(as_of).normalize()
    active_lots = _lots_as_of(c, T)

    if is_nearest:
        item, item_id, item_key = _match_item(c, q)
        if not item:
            return None
        matching = [
            v for v in active_lots
            if ((item_id and v["item_id"] == item_id) or v["item_key"] == item_key) and v["expiry"] >= T
        ]
        if not matching:
            return None
        matching.sort(key=lambda x: x["expiry"])
        return "date", matching[0]["expiry"].strftime("%Y-%m-%d"), "lot:nearest_expiry:date"

    # Determine expiry window [D_start, D_end]
    D_start = T
    D_end = None
    qf = fold(q)
    # Explicit "từ dd/mm/yyyy đến (hết) (ngày) dd/mm/yyyy" or "(dd/mm/yyyy - dd/mm/yyyy)"
    m_rng = re.search(
        r"(?:tu\s+(?:ngay\s+)?|[\(\[])(\d{1,2})[/\-.](\d{1,2})[/\-.](20\d{2})\s*(?:den(?:\s+het)?(?:\s+ngay)?|toi(?:\s+het)?(?:\s+ngay)?|[-–])\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](20\d{2})",
        qf,
    )
    if m_rng:
        try:
            D_start = pd.Timestamp(int(m_rng.group(3)), int(m_rng.group(2)), int(m_rng.group(1))).normalize()
            D_end = pd.Timestamp(int(m_rng.group(6)), int(m_rng.group(5)), int(m_rng.group(4))).normalize()
        except ValueError:
            D_end = None

    if D_end is None:
        m_until = re.search(
            r"(?:tu\s+nay\s+)?(?:den|toi)(?:\s+het)?(?:\s+ngay)?\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](20\d{2})",
            qf,
        )
        if m_until and re.search(r"het han.*(?:den|toi)", qf):
            try:
                D_end = pd.Timestamp(int(m_until.group(3)), int(m_until.group(2)), int(m_until.group(1))).normalize()
            except ValueError:
                D_end = None

    if D_end is None:
        m_n = re.search(r"trong\s*(?:vong\s*)?(\d+)\s*ngay\s*(?:toi|sap toi|tiep theo)?", qn)
        if m_n:
            N = int(m_n.group(1))
            D_end = D_start + pd.Timedelta(days=N)
        else:
            m_m = re.search(r"trong\s*(?:vong\s*)?(\d+)\s*thang\s*(?:toi|sap toi|tiep theo)?", qn)
            if m_m:
                N = int(m_m.group(1)) * 30
                D_end = D_start + pd.Timedelta(days=N)

    if D_end is None:
        return None

    exp_lots = [v for v in active_lots if D_start <= v["expiry"] <= D_end]

    if re.search(r"tien von|gia tri von|von dang nam|bao nhieu tien|bnhiu tien", qn):
        cap = round_money(sum(v["rem"] * v["unit_cost"] for v in exp_lots if not np.isnan(v["unit_cost"])))
        return "number", cap, "lot:expiring_capital:number"

    if re.search(r"(?:co\s+)?(?:may|bao nhieu|so)\s+lo\b", qn):
        return "number", int(len(exp_lots)), "lot:expiring_count:number"

    if re.search(r"(?:co\s+)?(?:may|bao nhieu|so)\s+(?:mat hang|san pham|thuoc|hang)\b", qn):
        return "number", int(len({v["item_id"] or v["item"] for v in exp_lots})), "lot:expiring_count:number"

    # Otherwise list of items ordered by (min_expiry_in_window, item_id)
    by_item = {}
    for v in exp_lots:
        it = v["item"]
        iid = v["item_id"]
        if it not in by_item or v["expiry"] < by_item[it][0]:
            by_item[it] = (v["expiry"], iid)
    ordered = [k for k, _ in sorted(by_item.items(), key=lambda kv: (kv[1][0], kv[1][1]))]
    return "list", ordered, "lot:expiring_items:list"
