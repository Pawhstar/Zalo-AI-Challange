"""Phone shops (rulebook §6 'Cửa hàng điện thoại').

A hand-kept phone book has a 'Ghi tắt' sheet giving every item a full name and
a kind (máy mới, máy cũ, phụ kiện). Questions there ask things the generic
router reads as revenue: how many phones were sold, what customers had to pay
after the discount and the trade-in, how much the shop paid for trade-ins.

  * dòng máy = the item name before its '…GB' capacity, else the whole name
  * hãng = first word of the name; 'iPhone' is Apple
  * khách phải trả = order total after discount and trade-in (column Khách
    trả; checked equal to goods − bớt − thu máy cũ on the shops seen)
  * every figure counts only valid orders (not cancelled, not returned)

Each answer carries its own tag 'ph:<kind>:<type>'.
"""
import re
import numpy as np
import pandas as pd

from datamate.fold import fold, normq
from datamate.periods import parse_time
from datamate import loader

PHONE_KINDS = {"may moi", "may cu"}


def _key(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", fold(str(s)))).strip()


def _half_up(x):
    return int(np.floor(x + 0.5))


def dong_may(name):
    m = re.match(r"^(.*?)\s+\d+\s*GB\b", str(name), re.I)
    return m.group(1).strip() if m else str(name).strip()


def hang(name):
    w = str(name).split()
    if not w:
        return ""
    return "Apple" if fold(w[0]) == "iphone" else w[0]


def _book(b):
    if hasattr(b, "_phone_book"):
        return b._phone_book
    b._phone_book = None
    I = b.items
    if len(I) == 0 or "group" not in I.columns or len(b.lines) == 0:
        return None
    kinds = {_key(g) for g in I["group"].fillna("") if g}
    if not ({"may moi", "phu kien"} <= kinds):
        return None
    kind = {it: _key(g) for it, g in zip(I["item"], I["group"].fillna(""))}
    L = b.lines.copy()
    L["kind"] = L["item"].map(kind).fillna("")
    O = b.orders.set_index("order_id")
    L["ok"] = L["order_id"].map(O["is_valid"]).fillna(False).astype(bool)
    L["day"] = pd.to_datetime(L["date"], errors="coerce").dt.normalize()
    L["dong"] = L["item"].map(dong_may)
    L["hang"] = L["item"].map(hang)
    L["q"] = pd.to_numeric(L["qty_base"], errors="coerce").fillna(pd.to_numeric(L["qty"], errors="coerce")).fillna(0)
    L["rev"] = pd.to_numeric(L["revenue"], errors="coerce").fillna(0)
    # order-level money read straight from the sales sheets
    frames = []
    for name, raw in b.sheets.items():
        if fold(name).endswith("ghi tat"):
            continue
        h = loader.df_from_sheet(raw)
        cols = {_key(c): c for c in h.columns}
        if "stt" in cols and "khach tra" in cols and ("hang" in cols or "ten hang" in cols):
            frames.append(h)
    per = pd.DataFrame(index=O.index)
    per["bot"] = 0.0
    per["thu"] = 0.0
    per["kt"] = np.nan
    if frames:
        h = pd.concat(frames, ignore_index=True)
        cols = {_key(c): c for c in h.columns}
        stt = pd.to_numeric(h[cols["stt"]], errors="coerce").ffill()
        h = h[stt.notna()].copy()
        h["_o"] = stt[stt.notna()].astype(int).astype(str)
        def mx(c):
            return h.groupby("_o")[c].apply(lambda s: s.map(loader.parse_num).max())
        per["kt"] = mx(cols["khach tra"]).reindex(per.index)
        if "bot" in cols:
            per["bot"] = mx(cols["bot"]).reindex(per.index).fillna(0)
        if "thu may cu" in cols:
            per["thu"] = mx(cols["thu may cu"]).reindex(per.index).fillna(0)
    # a separate trade-in book: price paid, deducted from sales order STT
    for name, raw in b.sheets.items():
        h = loader.df_from_sheet(raw)
        cols = {_key(c): c for c in h.columns}
        c_stt = next((c for k, c in cols.items() if "stt so ban" in k or k.startswith("tru vao")), None)
        c_gia = cols.get("gia thu")
        if c_stt and c_gia:
            s = pd.to_numeric(h[c_stt], errors="coerce")
            v = h[c_gia].map(loader.parse_num)
            t = pd.DataFrame({"o": s, "v": v}).dropna()
            t["o"] = t["o"].astype(int).astype(str)
            add = t.groupby("o")["v"].sum().reindex(per.index).fillna(0)
            per["thu"] = per["thu"] + add
    goods = L.groupby("order_id")["line_amount"].sum().reindex(per.index).fillna(0)
    per["kt"] = per["kt"].fillna(goods - per["bot"] - per["thu"])
    per["day"] = pd.to_datetime(O["date"], errors="coerce").dt.normalize()
    per["ok"] = O["is_valid"].fillna(False).astype(bool)
    b._phone_book = {"L": L, "O": per, "items": list(I["item"]),
                     "dongs": sorted({dong_may(i) for i, k in kind.items() if k in PHONE_KINDS}, key=len, reverse=True),
                     "hangs": sorted({hang(i) for i, k in kind.items() if k in PHONE_KINDS})}
    return b._phone_book


def _named_item(bk, qk):
    """Longest full item name written in the question."""
    best = None
    for it in bk["items"]:
        k = _key(it)
        if k and re.search(r"(^|\s)" + re.escape(k) + r"(\s|$)", qk) and (best is None or len(k) > len(_key(best))):
            best = it
    return best


def _synonym_item(bk, qk):
    """An item named with a synonym for its first word(s): 'Cốc sạc nhanh 20W
    Type-C' for 'Củ sạc nhanh 20W Type-C', 'Kệ điện thoại để bàn' for 'Giá đỡ
    điện thoại để bàn'. The longest name tail (at least 3 words, without the
    first word) found in the question wins; ties between items -> none."""
    best, best_n = [], 0
    for it in bk["items"]:
        w = _key(it).split()
        for n in range(len(w) - 1, 2, -1):
            tail = " ".join(w[-n:])
            if re.search(r"(^|\s)" + re.escape(tail) + r"(\s|$)", qk):
                if n > best_n:
                    best, best_n = [it], n
                elif n == best_n:
                    best.append(it)
                break
    return best[0] if len(best) == 1 else None


def _named_dong(bk, qk):
    for d in bk["dongs"]:
        k = _key(d)
        if re.search(r"(^|\s)" + re.escape(k) + r"(\s|$)", qk):
            return d
    return None


def _named_hang(bk, qk):
    for hname in bk["hangs"]:
        k = _key(hname)
        if re.search(r"(^|\s)(may |dien thoai )?" + re.escape(k) + r"(\s|$)", qk):
            return hname
    if re.search(r"\bapple\b", qk):
        return "Apple"
    return None


def _kind_filter(qn):
    if re.search(r"\b(may|dien thoai|dt) cu\b", qn) and not re.search(r"may moi", qn):
        return {"may cu"}
    if re.search(r"\bmay moi\b", qn) and not re.search(r"may cu", qn):
        return {"may moi"}
    return set(PHONE_KINDS)


def try_answer(b, q, as_of):
    bk = _book(b)
    if bk is None:
        return None
    qn = normq(q)
    qk = _key(q)
    from datamate import phone_books
    r = phone_books.try_answer(b, bk, q, as_of)
    if r is not None:
        return r
    # left to other modules: debt, installments, warranty, price effects
    if re.search(r"\bno\b|cong no|tra gop|(tien|ky|han|da|chua|dot) gop|\bgop (thang|ky|tien)|qua han|bao hanh|tang gia|loi nhieu|lai gop|\bloi\b", qn):
        return None
    ts = parse_time(q, as_of)
    if ts.kind in ("default", "until") or ts.main is None or ts.compare is not None:
        return None
    T = pd.Timestamp(as_of).normalize()
    p = ts.main.clip(T)
    L, O = bk["L"], bk["O"]
    Lp = L[L["ok"] & (L["day"] >= p.start) & (L["day"] <= p.end)]
    Op = O[O["ok"] & (O["day"] >= p.start) & (O["day"] <= p.end)]
    if len(L[(L["day"] >= p.start) & (L["day"] <= p.end)]) == 0:
        return None

    # ---- what customers had to pay (after discount and trade-in)
    if re.search(r"khach (phai|can) tra|phai tra", qn) and not re.search(r"\b(con|thieu|chua|no)\b", qn):
        if len(Op) == 0:
            return None
        if re.search(r"trung binh|binh quan|moi don|1 don|mot don", qn):
            return "number", _half_up(Op["kt"].mean()), "ph:pay_avg:number"
        return "number", _half_up(Op["kt"].sum()), "ph:pay:number"

    # ---- trade-ins ('thu máy cũ' deducted from orders)
    if re.search(r"thu (mua )?(lai )?may cu|may cu thu lai|thu lai may cu", qn) and \
            not re.search(r"khach phai tra|phai tra", qn):
        if re.search(r"%|phan tram|ti le|chiem", qn) and re.search(r"\b(don|dh|hoa don)\b", qn):
            if len(Op) == 0:
                return None
            return "percent", round(100.0 * (Op["thu"] > 0).sum() / len(Op), 2), "ph:tradein_share:percent"
        if re.search(r"bao nhieu|bnhiu|nhieu|may|tong|cong|het", qn):
            return "number", _half_up(Op["thu"].sum()), "ph:tradein:number"
        return None

    phones = Lp[Lp["kind"].isin(PHONE_KINDS)]

    # ---- average price of one phone
    if re.search(r"trung binh|binh quan", qn) and \
            re.search(r"(moi|1|mot) (may|chiec|dien thoai|dt)\b|moi may", qn):
        P = phones[phones["kind"].isin(_kind_filter(qn))]
        if P["q"].sum() <= 0:
            return None
        return "number", _half_up(P["rev"].sum() / P["q"].sum()), "ph:phone_avg_price:number"

    # ---- top k phone lines by phones sold
    if re.search(r"dong may", qn) and re.search(r"nhieu (may|chiec)|ban chay|nhieu nhat", qn):
        m = re.search(r"(?:top\s*)?(\d+)\s*dong may|top\s*(\d+)", qn)
        k = int(m.group(1) or m.group(2)) if m else 1
        P = phones[phones["kind"].isin(_kind_filter(qn))]
        s = P.groupby("dong")["q"].sum()
        if len(s) == 0:
            return None
        order = sorted(s.items(), key=lambda kv: (-kv[1], kv[0]))
        if m:
            return "list", [d for d, _ in order[:k]], "ph:top_dong:list"
        return "string", order[0][0], "ph:top_dong:string"

    # ---- shares
    if re.search(r"chiem|%|phan tram|ti trong", qn):
        h = _named_hang(bk, qk)
        if h and re.search(r"so may|may ban|so chiec|chiec", qn):
            tot = phones["q"].sum()
            if tot <= 0:
                return None
            return "percent", round(100.0 * phones.loc[phones["hang"] == h, "q"].sum() / tot, 2), "ph:hang_share:percent"
        if re.search(r"may moi", qn) and re.search(r"tien|dthu|doanh thu", qn) and \
                re.search(r"(tien|dthu|doanh thu) (ban )?may", qn):
            tot = phones["rev"].sum()
            if tot <= 0:
                return None
            return "percent", round(100.0 * phones.loc[phones["kind"] == "may moi", "rev"].sum() / tot, 2), \
                "ph:new_share:percent"
        return None

    # ---- group revenue ('nhóm máy mới bán được bao nhiêu tiền')
    gm = re.search(r"\bnhom (may moi|may cu|phu kien)\b", qn)
    if gm and re.search(r"tien|dthu|doanh thu", qn) and not re.search(r"nhieu (may|chiec)|nao", qn):
        return "number", _half_up(Lp.loc[Lp["kind"] == gm.group(1), "rev"].sum()), "ph:group_rev:number"

    # ---- best seller inside one kind
    if gm and re.search(r"(mat hang|san pham|may|hang) nao|\bsp nao", qn) and \
            re.search(r"nhieu (may|chiec|cai)? ?nhat|ban chay", qn):
        P = Lp[Lp["kind"] == gm.group(1)]
        s = P.groupby("item")["q"].sum()
        if len(s) == 0:
            return None
        return "string", sorted(s.items(), key=lambda kv: (-kv[1], kv[0]))[0][0], "ph:group_best:string"

    # ---- revenue of one item named with a synonym (exact names: query)
    if re.search(r"tien|dthu|doanh thu|thu ve", qn) and not re.search(r"nhom|khach|\bdon\b|chiem|%", qn)             and _named_item(bk, qk) is None:
        it = _synonym_item(bk, qk)
        if it is not None:
            return "number", _half_up(Lp.loc[Lp["item"] == it, "rev"].sum()), "ph:item_rev_syn:number"

    # ---- how many units sold
    count = re.search(r"\b(may|bao nhieu|bnhiu|nhieu|tong cong|tat ca)\s+(chiec|may|cai|dien thoai)\b"
                      r"|\b(chiec|cai)\b.*\b(may|bao nhieu|bnhiu)\b|\bmay chiec\b", qn)
    if count and not re.search(r"\btien\b|dthu|doanh thu|\bdon\b", qn):
        it = _named_item(bk, qk)
        if it is not None:
            return "number", _num(Lp.loc[Lp["item"] == it, "q"].sum()), "ph:item_qty:number"
        it = _synonym_item(bk, qk)
        if it is not None:
            return "number", _num(Lp.loc[Lp["item"] == it, "q"].sum()), "ph:item_qty_syn:number"
        d = _named_dong(bk, qk)
        if d is not None:
            return "number", _num(phones.loc[phones["dong"] == d, "q"].sum()), "ph:dong_qty:number"
        h = _named_hang(bk, qk)
        if h is not None:
            return "number", _num(phones.loc[phones["hang"] == h, "q"].sum()), "ph:hang_qty:number"
        if re.search(r"\bcai\b", qn) and not re.search(r"may|dien thoai|\bdt\b", qn.replace("may cai", "")):
            return None
        P = phones[phones["kind"].isin(_kind_filter(qn))]
        return "number", _num(P["q"].sum()), "ph:phone_qty:number"
    return None


def _num(x):
    x = float(x)
    return int(x) if x == int(x) else round(x, 2)
