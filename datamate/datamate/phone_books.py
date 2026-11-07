"""Side books of a hand-kept phone shop (rulebook §4 and §6 'Cửa hàng điện thoại').

  * sổ góp: one contract per sales STT. First row: purchase date, customer,
    Giá (whole order), Trả trước, Số kỳ, Góp/tháng, Hạn góp (day of month);
    later rows: Ngày góp, Đã góp. Instalment k (k = 1..n) is due on that day of
    the k-th month after the purchase month. A due date before the asked day
    that is not fully paid is overdue; one due on the asked day is not.
  * sổ nợ: one debt per sales STT ('Ghi chú: STT n'). First row: purchase
    date, customer, Nợ (left after paying at purchase); payments in Đã trả /
    Ngày trả, the first on the first row.
  * sổ bảo hành: one row per visit (Ngày nhận, Máy = dòng máy, IMEI).

Debt questions cover both books (rulebook §6: an instalment contract is a debt).
Tags 'pb:<kind>:<type>'.
"""
import re
import calendar
import numpy as np
import pandas as pd

from datamate.fold import fold, normq
from datamate.periods import parse_time
from datamate import loader


def _key(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", fold(str(s)))).strip()


def _cols(h):
    return {_key(c): c for c in h.columns}


def _date(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return pd.NaT
    if isinstance(v, (int, float, np.integer, np.floating)):
        if 20000 < float(v) < 80000:
            return pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(v))
        return pd.NaT
    if isinstance(v, (pd.Timestamp,)) or hasattr(v, "year"):
        return pd.Timestamp(v).normalize()
    s = str(v).strip()
    if re.fullmatch(r"\d{5}(\.0)?", s):
        return _date(float(s))
    d = pd.to_datetime(s, dayfirst=True, errors="coerce")
    return d.normalize() if not pd.isna(d) else pd.NaT


def _add_months(d, k, day):
    y, m = d.year + (d.month - 1 + k) // 12, (d.month - 1 + k) % 12 + 1
    return pd.Timestamp(y, m, min(int(day), calendar.monthrange(y, m)[1]))


def _half_up(x):
    return int(np.floor(x + 0.5))


def books(b):
    if hasattr(b, "_phone_side"):
        return b._phone_side
    out = {"gop": None, "no": None, "bh": None}
    for name, raw in b.sheets.items():
        h = loader.df_from_sheet(raw)
        c = _cols(h)
        if "so ky" in c and "gop thang" in c and "da gop" in c:
            out["gop"] = _gop(h, c)
        elif "no" in c and "da tra" in c and "ngay tra" in c:
            out["no"] = _no(h, c)
        elif "ngay nhan" in c and "imei" in c:
            w = pd.DataFrame({"day": h[c["ngay nhan"]].map(_date),
                              "may": h[c["may"]].fillna("").astype(str).str.strip() if "may" in c else "",
                              "imei": h[c["imei"]].map(_imei)})
            out["bh"] = w[w["day"].notna()].reset_index(drop=True)
    b._phone_side = out
    return out


def _imei(v):
    s = str(v).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s if s and s.lower() != "nan" else ""


def _gop(h, c):
    stt = pd.to_numeric(h[c["stt"]], errors="coerce").ffill() if "stt" in c else None
    rows = []
    cur = None
    for i in range(len(h)):
        r = h.iloc[i]
        first = isinstance(r.get(c["khach"]), str) and r.get(c["khach"]).strip() != "" if "khach" in c else False
        if first:
            cur = {"stt": None if stt is None else stt.iloc[i], "buy": _date(r[c["ngay"]]),
                   "cust": str(r[c["khach"]]).strip(),
                   "price": loader.parse_num(r[c["gia"]]), "pre": loader.parse_num(r[c["tra truoc"]]),
                   "n": int(loader.parse_num(r[c["so ky"]])), "g": loader.parse_num(r[c["gop thang"]]),
                   "due_day": int(loader.parse_num(r[c["han gop ngay"]])), "pays": []}
            rows.append(cur)
        if cur is None:
            continue
        d, a = _date(r[c["ngay gop"]]), loader.parse_num(r[c["da gop"]])
        if not pd.isna(d) and a is not None and not np.isnan(a):
            cur["pays"].append((d, a))
    for k in rows:
        k["due"] = [_add_months(k["buy"], j, k["due_day"]) for j in range(1, k["n"] + 1)]
    return [k for k in rows if not pd.isna(k["buy"])]


def _no(h, c):
    rows, cur = [], None
    for i in range(len(h)):
        r = h.iloc[i]
        cust = r.get(c["khach"]) if "khach" in c else None
        if isinstance(cust, str) and cust.strip():
            cur = {"buy": _date(r[c["ngay"]]), "cust": cust.strip(), "debt": loader.parse_num(r[c["no"]]), "pays": []}
            rows.append(cur)
        if cur is None:
            continue
        d, a = _date(r[c["ngay tra"]]), loader.parse_num(r[c["da tra"]])
        if not pd.isna(d) and a is not None and not np.isnan(a):
            cur["pays"].append((d, a))
    return [k for k in rows if not pd.isna(k["buy"])]


def _paid(k, X):
    return sum(a for d, a in k["pays"] if d <= X)


def _gop_left(k, X):
    return max(0.0, k["n"] * k["g"] - _paid(k, X))


def _gop_overdue(k, X):
    due = sum(1 for d in k["due"] if d < X)
    return max(0.0, due * k["g"] - _paid(k, X))


def _no_left(k, X):
    return max(0.0, k["debt"] - _paid(k, X))


def _who(kk, qk):
    """Contracts of the customer named in the question (longest name found)."""
    names = sorted({k["cust"] for k in kk}, key=len, reverse=True)
    for nm in names:
        if re.search(r"(^|\s)" + re.escape(_key(nm)) + r"(\s|$)", qk):
            return nm
    return None


def _ask_day(q, as_of):
    T = pd.Timestamp(as_of).normalize()
    ts = parse_time(q, as_of)
    if ts.main is None:
        return T
    return min(ts.main.end.normalize(), T) if ts.kind in ("until", "day", "default") else None


def try_answer(b, bk, q, as_of):
    qn = normq(q)
    qk = _key(q)
    B = books(b)
    gop, no, bh = B["gop"], B["no"], B["bh"]
    T = pd.Timestamp(as_of).normalize()

    # ---------------- instalments
    if gop is not None and re.search(r"\bgop\b|tra gop", qn):
        X = _ask_day(q, as_of)
        if X is None:
            return None
        kk = [k for k in gop if k["buy"] <= X]
        nm = _who(kk, qk)
        if re.search(r"khach .*\bgop\b|\bgop\b", qn) and nm is None and re.search(r"\bkhach\s+[A-ZĐ]", q):
            return None                                    # a customer we cannot find
        sel = [k for k in kk if k["cust"] == nm] if nm else kk
        # instalments due so far (the asked day included)
        if nm and re.search(r"(toi han|den han) may ky|may ky", qn):
            return "number", sum(1 for k in sel for d in k["due"] if d <= X), "pb:gop_due_count:number"
        if re.search(r"qua han|cham gop|tre han|tre gop", qn):
            if re.search(r"(may|bao nhieu|bnhiu|bao nhiu|mi) (khach|nguoi)|\bmay ngui\b|\bmi nguoi\b", qn):
                who = {k["cust"] for k in sel if _gop_overdue(k, X) > 0}
                return "number", len(who), "pb:gop_overdue_cust:number"
            if re.search(r"tien|bao nhieu|bnhiu|tong", qn):
                return "number", _half_up(sum(_gop_overdue(k, X) for k in sel)), "pb:gop_overdue:number"
            return None
        if re.search(r"chua gop|con lai|con thieu|chua tra|chua dong|con no", qn):
            return "number", _half_up(sum(_gop_left(k, X) for k in sel)), \
                "pb:gop_left_cust:number" if nm else "pb:gop_left:number"
        return None

    # ---------------- debts (sổ nợ + sổ góp)
    if (no is not None or gop is not None) and re.search(r"\bno\b|cong no|mua chiu|con thieu", qn) and \
            not re.search(r"nha cung cap|ncc|tra hang", qn):
        X = _ask_day(q, as_of)
        if X is None:
            return None
        debts = [(k["cust"], _no_left(k, X), k["buy"]) for k in (no or []) if k["buy"] <= X]
        debts += [(k["cust"], _gop_left(k, X), k["buy"]) for k in (gop or []) if k["buy"] <= X]
        debts = [d for d in debts if d[1] > 0]
        if re.search(r"tuoi no", qn):
            return None
        if re.search(r"(may|bao nhieu|bnhiu) khach", qn):
            return "number", len({loader.person_key(c) for c, _, _ in debts}), "pb:debt_cust:number"
        if re.search(r"tong|bao nhieu|bnhiu|tien", qn) and not re.search(r"\bkhach\s+[A-ZĐ]", q):
            return "number", _half_up(sum(v for _, v, _ in debts)), "pb:debt_total:number"
        return None

    # ---------------- warranty visits
    if bh is not None and re.search(r"bao hanh", qn):
        ts = parse_time(q, as_of)
        # machines sold in a month that came back by the asked day
        m = re.search(r"may ban (ra )?(trong )?thang", qn)
        if m and ts.main is not None:
            p = ts.main
            sold = _sold_imeis(b, bk, p)
            back = set(bh.loc[bh["day"] <= T, "imei"])
            return "number", len(sold & back), "pb:bh_back:number"
        if ts.kind in ("default", "until") or ts.main is None:
            return None
        p = ts.main.clip(T)
        W = bh[(bh["day"] >= p.start) & (bh["day"] <= p.end)]
        if re.search(r"dong may nao|may nao|dong nao", qn):
            if len(W) == 0:
                return None
            s = W.groupby("may").size()
            return "string", sorted(s.items(), key=lambda kv: (-kv[1], kv[0]))[0][0], "pb:bh_top_dong:string"
        if re.search(r"%|phan tram|ti le|chiem", qn):
            L = bk["L"]
            ph = L[L["ok"] & L["kind"].isin({"may moi", "may cu"}) & (L["day"] >= p.start) & (L["day"] <= p.end)]
            n = ph["q"].sum()
            if n <= 0:
                return None
            return "percent", round(100.0 * len(W) / n, 2), "pb:bh_rate:percent"
        if re.search(r"luot|bao nhieu|bnhiu|may", qn):
            return "number", int(len(W)), "pb:bh_visits:number"
    return None


def _sold_imeis(b, bk, p):
    """IMEIs of phones sold in valid orders of period p (a 2-phone line lists
    both numbers separated by ' / ')."""
    out = set()
    ok = bk["O"]
    for name, raw in b.sheets.items():
        h = loader.df_from_sheet(raw)
        c = _cols(h)
        if not ("stt" in c and "imei" in c and "khach tra" in c):
            continue
        stt = pd.to_numeric(h[c["stt"]], errors="coerce").ffill()
        day = h[c["ngay"]].map(_date).ffill() if "ngay" in c else None
        for i in range(len(h)):
            v = h.iloc[i][c["imei"]]
            if day is None or pd.isna(stt.iloc[i]):
                continue
            d = day.iloc[i]
            if pd.isna(d) or d < p.start or d > p.end:
                continue
            oid = str(int(stt.iloc[i]))
            if oid in ok.index and not bool(ok.at[oid, "ok"]):
                continue
            for x in re.split(r"\s*/\s*", str(v)):
                x = _imei(x)
                if x:
                    out.add(x)
    return out
