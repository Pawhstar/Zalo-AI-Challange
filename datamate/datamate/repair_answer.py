"""Answers specific to motorbike repair books (rulebook public §6, Sửa xe).

Rules applied (see repair.py for how the book is loaded):
  * one book row = one ticket = one visit ('lượt xe'), warranty tickets included;
    ticket and visit counts (shop or mechanic) include warranty tickets
  * average per ticket divides by the PAID tickets (warranty excluded)
  * visits for a job = tickets whose 'Làm gì' cell has that job, warranty
    tickets excluded; plain 'nhớt' is engine oil (not gear oil), plain 'ruột'
    is a new tube (not a patch); 'sửa điện' excludes bulbs and batteries
  * models that differ only in case or abbreviation are one model; number of
    bikes = number of distinct plates, warranty-only visits included
  * busiest mechanic = most visits (warranty included); hardest-working =
    most working days; best-selling = most revenue
  * warranty rate = warranty tickets dated in the period / paid tickets in it
  * regular bikes = plates with >= 2 PAID tickets in the period
  * commission = mechanic's rate x total ticket amount in the month
Every answer returns its own tag 'rep:<kind>:<type>'.
"""
import re
import numpy as np
import pandas as pd

from datamate.fold import fold, normq
from datamate.periods import parse_time, round_money, round2, round_half_up_money

# canonical job -> full-match pattern on one folded job fragment
JOBS = [
    ("bao_duong", r"bao duong( xe)?|bd|bdtq"),
    ("rua_xe", r"rua( xe)?"),
    ("kim_phun", r"(rua|ve sinh|vs) kim phun"),
    ("lam_noi", r"lam noi|(ve sinh|vs) noi"),
    ("sua_dien", r"sua dien|lam dien"),
    ("bong_den", r"(thay )?bong den|den pha"),
    ("ac_quy", r"(thay )?ac quy|(thay )?binh( gs)?"),
    ("nhot_lap", r"(thay )?(nhot|dau) (lap|hop so)|lap"),
    ("nhot_may", r"(thay )?nhot( (castrol( power1)?|motul( ga)?|shell( 1l)?|hang|honda|may))?"
                 r"|castrol|motul|shell( 1l)?"),
    ("va", r"va( xe| ruot)?"),
    ("thay_ruot", r"(thay )?ruot( xe)?"),
    ("vo", r"(thay )?vo( xe| casumina)?"),
    ("phanh_truoc", r"(ma phanh|bo( thang)?) truoc"),
    ("phanh_sau", r"(ma phanh|bo( thang)?) sau"),
    ("loc_gio", r"(thay )?loc gio"),
    ("sen", r"(chinh|can|tang) sen"),
    ("bugi", r"(thay )?bu ?gi"),
    ("curoa", r"(day )?cu ?roa"),
    ("nhong_sen_dia", r"nhong sen dia|nsd|bo nhong xich"),
    ("nuoc_mat", r"(thay )?nuoc (lam )?mat"),
]
_JOBS = [(k, re.compile(r"^(?:" + p + r")$")) for k, p in JOBS]

# question phrase -> canonical job (folded question text)
_ASK = [
    ("sua_dien", r"sua dien|lam dien"),
    ("nhot_lap", r"(dau|nhot) (lap|hop so)"),
    ("va", r"\bva (ruot|xe|lop)|\bva\b"),
    ("thay_ruot", r"thay ruot"),
    ("nhot_may", r"thay nhot|nhot may"),
    ("bao_duong", r"bao duong"),
    ("rua_xe", r"rua xe"),
    ("kim_phun", r"kim phun"),
    ("lam_noi", r"lam noi|ve sinh noi"),
    ("bong_den", r"bong den|den pha"),
    ("ac_quy", r"ac quy"),
    ("vo", r"thay vo|vo xe"),
    ("loc_gio", r"loc gio"),
    ("bugi", r"bu ?gi"),
    ("curoa", r"cu ?roa"),
    ("nhong_sen_dia", r"nhong sen dia|nhong xich"),
    ("nuoc_mat", r"nuoc (lam )?mat"),
]


def split_jobs(cell):
    """'vá, má phanh trước + rửa và bugi' -> canonical job set. Split on the
    ACCENTED text: folded, 'và' (and) and 'vá' (patch) are both 'va'."""
    out = set()
    if not cell:
        return out
    for part in re.split(r"\s*(?:,|\+|;|&|\bvà\b)\s*", str(cell)):
        f = re.sub(r"\s+", " ", fold(part)).strip()
        if not f:
            continue
        for k, rx in _JOBS:
            if rx.match(f):
                out.add(k)
                break
    return out


_WEEKDAY = {"hai": 0, "2": 0, "ba": 1, "3": 1, "tu": 2, "4": 2, "nam": 3, "5": 3,
            "sau": 4, "6": 4, "bay": 5, "7": 5}


def _ctx(b):
    O = b.orders
    if len(O) == 0 or "plate" not in O.columns:
        return None
    c = getattr(b, "_rep_ctx", None)
    if c is None:
        O = O.copy()
        O["day"] = pd.to_datetime(O["date"], errors="coerce").dt.normalize()
        O["jobset"] = O["jobs"].map(split_jobs)
        O["paid"] = ~O["warranty"].astype(bool)
        O["mkey"] = O["model_raw"].map(lambda s: re.sub(r"\s+", "", fold(s)))
        c = {"O": O, "staff": getattr(b, "repair_staff", pd.DataFrame(columns=["name", "rate"]))}
        b._rep_ctx = c
    return c


def _mechanic_in(qn, c):
    """Mechanic named in the question (full name, accents optional)."""
    names = list(c["staff"]["name"]) or sorted(set(c["O"]["employee"]))
    hits = [n for n in names if fold(n) and re.search(r"\b" + re.escape(fold(n)) + r"\b", qn)]
    return hits[0] if len(hits) == 1 else None


def _model_in(qn, c):
    """Model named in the question: any spelling of the model group, matched
    as whole words with spaces optional ('SH Mode' / 'shmode')."""
    O = c["O"]
    best = None
    for raw, grp in zip(O["model_raw"], O["model"]):
        f = fold(raw)
        if len(re.sub(r"\s+", "", f)) < 2:
            continue
        pat = r"\b" + r"\s*".join(re.escape(ch) for ch in f.replace(" ", "")) + r"\b"
        if re.search(pat, qn):
            if best is None or len(f) > len(best[0]):
                best = (f, grp)
    return best[1] if best else None


def _job_in(qn):
    for k, p in _ASK:
        if re.search(p, qn):
            return k
    return None


def _rank(s, ascending=False):
    """Series value -> sorted index; ties by name (no codes in a repair book)."""
    df = pd.DataFrame({"k": s.index, "v": s.values})
    df = df.sort_values(["v", "k"], ascending=[ascending, True])
    return list(df["k"])


def try_answer(b, q, as_of):
    c = _ctx(b)
    if c is None:
        return None
    qn = normq(q)
    # names are matched on the plainly folded text: normq drops a trailing
    # 'r'/'s'/'x' it takes for a telex key ('Air Blade' -> 'ai blade')
    qf = re.sub(r"\s+", " ", re.sub(r"[?!,;]", " ", fold(q))).strip()
    ts = parse_time(q, as_of)
    if ts.kind in ("default", "until") or ts.main is None:
        return None
    T = pd.Timestamp(as_of).normalize()
    p = ts.main.clip(T)
    O = c["O"]
    X = O[(O["day"] >= p.start) & (O["day"] <= p.end)]
    mech = _mechanic_in(qf, c) or _mechanic_in(qn, c)
    many = re.search(r"\bbang\b|tung tho|moi tho|cac tho|moi nguoi|xep", qn)
    top = re.search(r"nhat\b", qn) and re.search(r"\btho (nao|mo|gi)\b|\bai\b|tho nhan|tho lam", qn)

    # ---- commission (README: rate x ticket total in the month)
    if re.search(r"hoa hong|hue hong", qn):
        st = c["staff"]
        if not len(st) or st["rate"].isna().all():
            return None
        rev = X.groupby("employee")["revenue"].sum()
        com = {n: round_money(float(r) / 100.0 * float(rev.get(n, 0.0)))
               for n, r in zip(st["name"], st["rate"]) if pd.notna(r)}
        s = pd.Series(com)
        if many:
            rows = [[n, int(s[n])] for n in _rank(s)]
            return "table", {"columns": ["tho", "hoa_hong"], "rows": rows}, "rep:commission:table"
        if top:
            return "string", _rank(s)[0], "rep:commission_top:string"
        if mech:
            return "number", int(com.get(mech, 0)), "rep:commission:number"
        return None

    # ---- warranty rate and counts
    if re.search(r"bao hanh", qn):
        n_w = int((~X["paid"]).sum())
        if re.search(r"%|phan tram|ti le|chiem", qn):
            n_p = int(X["paid"].sum())
            if n_p == 0:
                return None
            return "percent", round2(100.0 * n_w / n_p), "rep:warranty_rate:percent"
        if re.search(r"bao nhieu|may|bnhiu|dem|so (phieu|luot)", qn) and \
                re.search(r"phieu|luot|xe", qn) and not re.search(r"khong tinh|tru|bo (xe|phieu)", qn):
            return "number", n_w, "rep:warranty_count:number"

    # ---- average per weekday ('trung bình mỗi thứ Tư mấy lượt xe')
    # the weekday may come before or after 'trung bình' ('các ngày thứ 3 tháng
    # này trung bình một ngày ...'); 'thu tien' (collect money) never matches
    m = re.search(r"\bthu\s*(hai|ba|tu|nam|sau|bay|[2-7])\b", qn)
    if m and re.search(r"trung binh|binh quan", qn) and re.search(r"luot|phieu|xe", qn):
        wd = _WEEKDAY[m.group(1)]
        days = pd.date_range(p.start, p.end)
        nd = int((days.weekday == wd).sum())
        if nd == 0:
            return None
        n = int((X["day"].dt.weekday == wd).sum())
        return "number", round2(n / nd), "rep:avg_weekday:number"

    # ---- average per ticket: paid tickets only
    if re.search(r"binh quan|trung binh", qn) and re.search(r"phieu|luot", qn):
        Y = X[X["paid"]]
        if len(Y) == 0:
            return None
        return "number", round_half_up_money(Y["revenue"].sum() / len(Y)), "rep:avg_ticket:number"

    # ---- regular bikes: >= N paid tickets in the period
    m = re.search(r"tu (\d+) lan tro len|(\d+) lan tro len", qn)
    if re.search(r"khach quen", qn) or m:
        n = int(m.group(1) or m.group(2)) if m else 2
        cnt = X[X["paid"]].groupby("plate").size()
        return "number", int((cnt >= n).sum()), "rep:regulars:number"

    # ---- model that brought in the most money
    if re.search(r"dong xe", qn) and re.search(r"nhieu tien|doanh thu|dthu|tien sua", qn) and \
            re.search(r"nhat\b", qn):
        s = X.groupby("model")["revenue"].sum()
        if len(s) == 0:
            return None
        return "string", _rank(s)[0], "rep:top_model_money:string"

    # ---- distinct bikes of a model
    model = _model_in(qf, c)
    if model and re.search(r"khac nhau|moi xe tinh|bao nhieu (chiec )?xe|bn chiec|may chiec|bao nhieu chiec", qn):
        return "number", int(X.loc[X["model"] == model, "plate"].nunique()), "rep:model_bikes:number"

    # ---- visits for a job (warranty tickets excluded)
    job = _job_in(qn)
    if job and re.search(r"luot|phieu|bao nhieu xe|may xe|bnhiu|bao nhieu", qn):
        Y = X[X["paid"]]
        return "number", int(Y["jobset"].map(lambda s: job in s).sum()), "rep:job_visits:number"

    # ---- top mechanic
    if top:
        # 'nhiệt tình' is not mapped: it may be a judgement (unanswerable)
        # rather than 'chăm chỉ'; a wrong answer costs more than an abstain
        if re.search(r"cham chi|sieng nang|nhieu ngay", qn):
            s = X.groupby("employee")["day"].nunique()
            kind = "rep:top_mech_days:string"
        elif re.search(r"tien|dthu|doanh thu|ban", qn):
            s = X.groupby("employee")["revenue"].sum()
            kind = "rep:top_mech_money:string"
        elif re.search(r"luot|phieu|xe", qn):
            s = X.groupby("employee").size()
            kind = "rep:top_mech_visits:string"
        else:
            return None
        if len(s) == 0:
            return None
        return "string", _rank(s)[0], kind

    # ---- one mechanic: visits or money
    if mech:
        Y = X[X["employee"] == mech]
        # 'tiền các phiếu thợ X làm' asks money although it names tickets
        if re.search(r"\btien\b|dthu|doanh thu|\bban\b|cong lai", qn):
            return "number", round_money(Y["revenue"].sum()), "rep:mech_money:number"
        if re.search(r"luot|phieu", qn):
            return "number", int(len(Y)), "rep:mech_visits:number"
        return None

    # ---- ticket count for the shop (warranty included)
    if re.search(r"(bao nhieu|may|bnhiu|dem|len) (phieu|luot)|(phieu|luot)( sua)?( xe)? (duoc )?(bao nhieu|may|bnhiu)", qn):
        return "number", int(len(X)), "rep:tickets:number"
    return None
