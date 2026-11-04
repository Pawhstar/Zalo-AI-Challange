"""Period resolution (rulebook §2).

All matching is done on an accent-folded, lower-cased question, because the
questions are frequently written without Vietnamese diacritics.
"""
import os, re
import pandas as pd

from .fold import fold

def round_money(x):
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return int(round(f + 1e-9))

def round2(x):
    return round(float(x) + 1e-12, 2)

def round_half_up_money(x):
    """Money averages round to the dong, .5 rounds up."""
    return int(math_floor(x + 0.5))

def math_floor(x):
    import math
    return math.floor(x)

def prev_period(start, end):
    """The period immediately before [start,end] of the same length."""
    length = (end - start).days + 1
    p_end = start - pd.Timedelta(days=1)
    p_start = p_end - pd.Timedelta(days=length - 1)
    return p_start, p_end

class Period:
    __slots__ = ("start", "end")
    def __init__(self, start, end):
        self.start = pd.Timestamp(start)
        self.end = pd.Timestamp(end)
    def __repr__(self):
        return f"Period({self.start.date()}..{self.end.date()})"
    def __eq__(self, o):
        return isinstance(o, Period) and self.start == o.start and self.end == o.end

def month_period(m, y):
    s = pd.Timestamp(y, m, 1)
    e = s + pd.offsets.MonthEnd(0)
    return Period(s, e)

def quarter_period(q, y):
    m0 = (q - 1) * 3 + 1
    s = pd.Timestamp(y, m0, 1)
    e = s + pd.offsets.MonthEnd(q - 1)
    return Period(s, e)

def week_start(ts):
    return ts - pd.Timedelta(days=ts.weekday())

def year_period(y):
    return Period(pd.Timestamp(y, 1, 1), pd.Timestamp(y, 12, 31))

# ---------------------------------------------------------------- calendar

_cal_cache = {}
def _calendar_df():
    p = os.environ.get("CALENDAR_CSV")
    if p is None:
        for cand in ("/home/felliner/Documents/Train/train/calendar.csv",
                     "/home/felliner/Documents/Train/public_test/calendar.csv"):
            if os.path.exists(cand):
                p = cand
                break
    if p is None:
        return None
    if p not in _cal_cache:
        _cal_cache[p] = pd.read_csv(p)
    return _cal_cache[p]

def tet_period(year, calendar_df=None):
    """Tết năm Y window: solar day of 23 tháng Chạp (lunar Y-1) .. end of the
    solar day of mùng 10 tháng Giêng (lunar Y), inclusive."""
    cal = calendar_df if calendar_df is not None else _calendar_df()
    if cal is None:
        return None
    start_row = cal[(cal["lunar_month"] == 12) & (cal["lunar_day"] == 23)
                    & (cal["lunar_year"] == year - 1)]
    end_row = cal[(cal["lunar_month"] == 1) & (cal["lunar_day"] == 10)
                  & (cal["lunar_year"] == year)]
    if len(start_row) == 0 or len(end_row) == 0:
        return None
    s = pd.Timestamp(start_row.iloc[0]["date"])
    e = pd.Timestamp(end_row.iloc[0]["date"])
    return Period(s, e)

# ---------------------------------------------------------------- resolution

def resolve_relative(q, as_of):
    """Relative time phrases -> Period."""
    s = fold(q)
    as_of = pd.Timestamp(as_of)

    m = re.search(r"(\d+)\s*ngay\s*(truoc|gan nhat|lien truoc)", s)
    if m and "gan nhat" in s:
        n = int(m.group(1))
        return Period(as_of - pd.Timedelta(days=n - 1), as_of)

    if "hom nay" in s or "ngay nay" in s or "hnay" in s:
        return Period(as_of, as_of)
    if "hom qua" in s or "hqua" in s or "qua hom" in s:
        return Period(as_of - pd.Timedelta(days=1), as_of - pd.Timedelta(days=1))
    if "2 hom qua" in s or "hai hom qua" in s:
        return Period(as_of - pd.Timedelta(days=2), as_of - pd.Timedelta(days=2))

    if "tuan truoc" in s or "tuan roi" in s:
        ws = week_start(as_of)
        return Period(ws - pd.Timedelta(days=7), ws - pd.Timedelta(days=1))
    if "tuan nay" in s:
        ws = week_start(as_of)
        return Period(ws, as_of)
    if "tuan" in s and "thang" not in s:
        ws = week_start(as_of)
        return Period(ws, as_of)

    if "thang truoc" in s:
        pm = as_of - pd.DateOffset(months=1)
        return month_period(pm.month, pm.year)
    if "thang nay" in s:
        return Period(pd.Timestamp(as_of.year, as_of.month, 1), as_of)

    if "quy truoc" in s:
        q_ = ((as_of.month - 1) // 3) + 1
        if q_ == 1:
            return quarter_period(4, as_of.year - 1)
        return quarter_period(q_ - 1, as_of.year)
    if "quy nay" in s:
        q_ = (as_of.month - 1) // 3 + 1
        s_, e_ = quarter_period(q_, as_of.year)
        return Period(s_, min(e_, as_of))

    if "tu dau nam" in s or "tu nam nay" in s:
        return Period(pd.Timestamp(as_of.year, 1, 1), as_of)

    if "tet" in s:
        m = re.search(r"tet\s*(\d{4})", s)
        yy = int(m.group(1)) if m else as_of.year
        t = tet_period(yy)
        if t is not None:
            return t
    return None

def resolve_period(q, as_of):
    """Full period resolution. Understands 'tháng M/Y', 'tháng M' (of as_of year
    or the previous one if in the future), 'quý Q/Y', an explicit day, 'năm Y',
    'Tết năm Y', and all the relative phrases."""
    s = fold(q)
    as_of = pd.Timestamp(as_of)

    # explicit month + year. 'thangs' is a common typo for 'tháng'.
    m = re.search(r"thangs?\s*(\d{1,2})\s*(?:/|nam|-)\s*(\d{4})", s)
    if m:
        return month_period(int(m.group(1)), int(m.group(2)))
    # explicit quarter + year
    m = re.search(r"quys?\s*(\d)\s*(?:/|nam|-)\s*(\d{4})", s)
    if m:
        return quarter_period(int(m.group(1)), int(m.group(2)))
    # explicit day
    m = re.search(r"ngay\s*(\d{1,2})\s*/\s*(\d{1,2})\s*(?:/\s*(\d{4}))?", s)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        yy = int(m.group(3)) if m.group(3) else as_of.year
        try:
            ts = pd.Timestamp(yy, mo, d)
        except ValueError:
            return None
        return Period(ts, ts)
    # year
    m = re.search(r"nam\s*(\d{4})", s)
    if m and "thang" not in s and "quy" not in s:
        return year_period(int(m.group(1)))

    # relative phrases (before bare 'thang M' so 'tháng này' wins)
    rel = resolve_relative(s, as_of)
    if rel is not None:
        return rel

    # bare month, with or without a year ('thangs' typo tolerated)
    m = re.search(r"thangs?\s*(\d{1,2})", s)
    if m:
        mm = int(m.group(1))
        if mm < 1 or mm > 12:
            return None
        target = pd.Timestamp(as_of.year, mm, 1)
        if target > as_of:
            target = target - pd.DateOffset(years=1)
        s_, e_ = month_period(target.month, target.year)
        if target == pd.Timestamp(as_of.year, as_of.month, 1):
            return Period(s_, as_of)          # 'tháng này' -> month to date
        return Period(s_, e_)
    # bare quarter
    m = re.search(r"quy\s*(\d)", s)
    if m:
        qn = int(m.group(1))
        if qn < 1 or qn > 4:
            return None
        target = pd.Timestamp(as_of.year, (qn - 1) * 3 + 1, 1)
        if target > as_of:
            return quarter_period(qn, as_of.year - 1)
        s_, e_ = quarter_period(qn, as_of.year)
        return Period(s_, min(e_, as_of))
    return None
