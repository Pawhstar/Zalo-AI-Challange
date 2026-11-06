"""Period resolution (rulebook §2).

All matching runs on the accent-folded, lower-cased question: questions are
often typed without diacritics or with typos ('thangs', 'hnay', 'tuan trc').

Main entry: parse_time(q, as_of) -> TimeSpec
    main     : Period the question is about
    compare  : Period it is compared with ('so với tháng trước', 'cùng kỳ'), or None
    months   : list of month Periods for 'N tháng liên tiếp ...' questions, or None
    until    : True for status questions ('đến hết ngày X', 'tính đến hôm nay')
    explicit : True when the question named a period at all
"""
import os, re, math
import pandas as pd

from .fold import fold, normq

# ---------------------------------------------------------------- rounding

def round_money(x):
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return int(math.floor(f + 0.5 + 1e-9))

def round2(x):
    """Round to 2 decimals, half away from zero (avoids float artefacts)."""
    f = float(x)
    sign = -1 if f < 0 else 1
    return sign * math.floor(abs(f) * 100 + 0.5 + 1e-9) / 100

def round_half_up_money(x):
    """Money averages round to the dong, .5 rounds up."""
    return int(math.floor(float(x) + 0.5 + 1e-9))

def math_floor(x):
    return math.floor(x)

# ---------------------------------------------------------------- Period

class Period:
    __slots__ = ("start", "end")

    def __init__(self, start, end):
        self.start = pd.Timestamp(start).normalize()
        self.end = pd.Timestamp(end).normalize()

    def __repr__(self):
        return f"Period({self.start.date()}..{self.end.date()})"

    def __eq__(self, o):
        return isinstance(o, Period) and self.start == o.start and self.end == o.end

    def __iter__(self):                       # allows  s, e = period
        yield self.start
        yield self.end

    @property
    def days(self):
        return (self.end - self.start).days + 1

    def clip(self, hi):
        hi = pd.Timestamp(hi).normalize()
        return Period(self.start, min(self.end, hi))


def prev_period(start, end):
    """The period immediately before [start, end] of the same length."""
    length = (end - start).days + 1
    p_end = start - pd.Timedelta(days=1)
    p_start = p_end - pd.Timedelta(days=length - 1)
    return p_start, p_end

def month_period(m, y):
    s = pd.Timestamp(int(y), int(m), 1)
    return Period(s, s + pd.offsets.MonthEnd(0))

def quarter_period(q, y):
    s = pd.Timestamp(int(y), (int(q) - 1) * 3 + 1, 1)
    return Period(s, s + pd.DateOffset(months=3) - pd.Timedelta(days=1))

def year_period(y):
    return Period(pd.Timestamp(int(y), 1, 1), pd.Timestamp(int(y), 12, 31))

def week_start(ts):
    ts = pd.Timestamp(ts).normalize()
    return ts - pd.Timedelta(days=ts.weekday())

def _shift_years(ts, n):
    ts = pd.Timestamp(ts)
    try:
        return ts.replace(year=ts.year + n)
    except ValueError:                        # 29/02 -> 28/02
        return ts.replace(year=ts.year + n, day=28)

# ---------------------------------------------------------------- calendar

_cal_cache = {}
_CAL_PATH = None

def set_calendar(path):
    global _CAL_PATH
    _CAL_PATH = path

def _calendar_df():
    p = _CAL_PATH or os.environ.get("CALENDAR_CSV")
    if p is None or not os.path.exists(p):
        return None
    if p not in _cal_cache:
        _cal_cache[p] = pd.read_csv(p)
    return _cal_cache[p]

def tet_period(year, calendar_df=None):
    """Tết năm Y: solar day of 23 tháng Chạp (lunar Y-1) .. end of mùng 10
    tháng Giêng (lunar Y), inclusive."""
    cal = calendar_df if calendar_df is not None else _calendar_df()
    if cal is None:
        return None
    leap = cal["lunar_leap"].astype(str).str.lower().isin(["true", "1"]) \
        if "lunar_leap" in cal.columns else False
    c = cal[~leap] if not isinstance(leap, bool) else cal
    a = c[(c["lunar_month"] == 12) & (c["lunar_day"] == 23) & (c["lunar_year"] == year - 1)]
    b = c[(c["lunar_month"] == 1) & (c["lunar_day"] == 10) & (c["lunar_year"] == year)]
    if len(a) == 0 or len(b) == 0:
        return None
    return Period(a.iloc[0]["date"], b.iloc[0]["date"])

# ---------------------------------------------------------------- parsing

_Y = r"((?:19|20)\d\d)"
_DMY = r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})(?:\s*[/\-.]\s*" + _Y + r")?"


class TimeSpec:
    __slots__ = ("main", "compare", "months", "until", "explicit", "kind")

    def __init__(self, main=None, compare=None, months=None, until=False,
                 explicit=False, kind=""):
        self.main, self.compare, self.months = main, compare, months
        self.until, self.explicit, self.kind = until, explicit, kind

    def __repr__(self):
        return (f"TimeSpec(main={self.main}, compare={self.compare}, months={self.months}, "
                f"until={self.until}, kind={self.kind})")


def _date(d, m, y, as_of):
    """dd/mm[/yyyy]; without a year: this year unless after today (rulebook §2)."""
    yy = int(y) if y else as_of.year
    try:
        ts = pd.Timestamp(yy, int(m), int(d))
    except ValueError:
        return None
    if not y and ts > as_of:
        ts = _shift_years(ts, -1)
    return ts


def _month_of(m, y, as_of):
    """'tháng M' without a year: this year unless after today, then last year."""
    m = int(m)
    if not 1 <= m <= 12:
        return None
    if y:
        return month_period(m, int(y))
    yy = as_of.year if pd.Timestamp(as_of.year, m, 1) <= as_of else as_of.year - 1
    return month_period(m, yy)


def _quarter_of(q, y, as_of):
    q = int(q)
    if not 1 <= q <= 4:
        return None
    if y:
        return quarter_period(q, int(y))
    yy = as_of.year if pd.Timestamp(as_of.year, (q - 1) * 3 + 1, 1) <= as_of else as_of.year - 1
    return quarter_period(q, yy)


def _yy(m):
    """'3/26' -> '3/2026'. Only when the second number cannot be a month
    (13..39), so a day/month like '5/06' is left alone."""
    a, b = int(m.group(1)), int(m.group(2))
    if 1 <= a <= 12 and 13 <= b <= 39:
        return f"{a}/20{b:02d}"
    return m.group(0)


def _norm_text(q):
    s = normq(q)
    # common typos / shorthands
    s = re.sub(r"\bthangs\b", "thang", s)
    # month written with its year, glued or dashed: 'th4/2026', 't8/2025',
    # 'th 3/26', '7-2026' -> 'thang 4/2026' ...
    s = re.sub(r"(?<![\d/])(\d{1,2})\s*-\s*((?:19|20)\d\d)(?![\d/])", r"\1/\2", s)
    s = re.sub(r"(?<![\d/])(\d{1,2})\s*/\s*(\d{2})(?![\d/])", _yy, s)
    s = re.sub(r"\b(?:th|t)\s*(?=\d{1,2}\s*/\s*(?:19|20)\d\d(?![\d/]))", "thang ", s)
    # a bare 'M/YYYY' (not part of 'd/m/yyyy') is a month
    s = re.sub(r"(?<![\d/])(?<!quy )(?<!tuan )(?<!q)\b(\d{1,2})\s*/\s*((?:19|20)\d\d)(?![\d/])",
               lambda m: f"thang {m.group(1)}/{m.group(2)}" if 1 <= int(m.group(1)) <= 12 else m.group(0), s)
    s = re.sub(r"\bthang\s+thang\b", "thang", s)
    s = re.sub(r"\bq\s*([1-4])\s*/\s*((?:19|20)\d\d)\b", r"quy \1/\2", s)       # 'Q1/2026'
    # 'so vs', 'so dới', 'so vói' (typos of 'so với') -> 'so voi'
    s = re.sub(r"\bso\s+(vs|doi|voi|vo|vooi|voii)\b", "so voi", s)
    # 'cùng tháng năm trước' = the same month a year earlier
    s = re.sub(r"\bcung thang (cua )?nam (truoc|ngoai|roi)\b", "cung ky nam truoc", s)
    # central-Vietnam 'ni' = 'này' ('tháng ni', 'bữa ni', 'năm ni', 'tuần ni')
    s = re.sub(r"\b(thang|bua|nam|tuan|quy|hom)\s+ni\b", r"\1 nay", s)
    s = re.sub(r"\bth\b(?=\s*(\d|nay|truoc|trc))", "thang", s)
    s = re.sub(r"\b(hnay|hom nayf?|bua nay|ngay hom nay)\b", "hom nay", s)
    s = re.sub(r"\b(hqua|hom wa|bua qua|bua hom qua)\b", "hom qua", s)
    s = re.sub(r"\b(trc|truoc|roi|vua roi|vua qua)\b", "truoc", s)
    s = re.sub(r"\bnam ngoai\b", "nam truoc", s)
    return s


def _relative(s, as_of):
    """Single relative phrase -> (Period, kind) or None."""
    T = as_of
    # 'từ đầu tháng/năm/tuần ... đến hôm nay' starts win over the 'hôm nay' end
    if re.search(r"\b(tu )?dau thang\b", s):
        return Period(pd.Timestamp(T.year, T.month, 1), T), "month_td"
    if re.search(r"\b(tu )?dau nam\b|\btu (ngay )?1/1\b", s):
        return Period(pd.Timestamp(T.year, 1, 1), T), "year_td"
    if re.search(r"\b(tu )?dau tuan\b", s):
        return Period(week_start(T), T), "week_td"
    if re.search(r"\b(tu )?dau quy\b", s):
        q = (T.month - 1) // 3 + 1
        return quarter_period(q, T.year).clip(T), "quarter_td"
    m = re.search(r"(\d+)\s*ngay\s*(gan nhat|gan day|qua|vua qua|truoc|cuoi)", s)
    if m:
        n = int(m.group(1))
        return Period(T - pd.Timedelta(days=n - 1), T), "ndays"
    m = re.search(r"(\d+)\s*tuan\s*(gan nhat|qua|truoc)", s)
    if m:
        n = int(m.group(1))
        return Period(T - pd.Timedelta(days=7 * n - 1), T), "ndays"
    if re.search(r"\bhom kia\b", s):
        d = T - pd.Timedelta(days=2)
        return Period(d, d), "day"
    if re.search(r"\bhom qua\b", s):
        d = T - pd.Timedelta(days=1)
        return Period(d, d), "day"
    if re.search(r"\bhom nay\b", s):
        return Period(T, T), "day"
    if re.search(r"\btuan (truoc|tr)\b|\btuan roi\b", s):
        ws = week_start(T)
        return Period(ws - pd.Timedelta(days=7), ws - pd.Timedelta(days=1)), "week"
    if re.search(r"\btuan nay\b", s):
        return Period(week_start(T), T), "week_td"
    if re.search(r"\bthang (truoc|roi)\b", s):
        pm = T - pd.DateOffset(months=1)
        return month_period(pm.month, pm.year), "month"
    if re.search(r"\b(thang nay|dau thang|tu dau thang)\b", s):
        return Period(pd.Timestamp(T.year, T.month, 1), T), "month_td"
    if re.search(r"\bquy (truoc|roi)\b", s):
        q = (T.month - 1) // 3 + 1
        return (quarter_period(4, T.year - 1) if q == 1 else quarter_period(q - 1, T.year)), "quarter"
    if re.search(r"\bquy nay\b", s):
        q = (T.month - 1) // 3 + 1
        return quarter_period(q, T.year).clip(T), "quarter_td"
    if re.search(r"\b(tu dau nam|dau nam (den|toi)|tu ngay 1/1\b|tu 1/1\b|nam nay)\b", s):
        return Period(pd.Timestamp(T.year, 1, 1), T), "year_td"
    if re.search(r"\bnam truoc\b", s) and not re.search(r"cung ky", s):
        return year_period(T.year - 1), "year"
    return None


def _tet(s, as_of):
    if not re.search(r"\btet\b", s):
        return None
    m = re.search(r"tet\s*(?:nam\s*)?" + _Y, s)
    y = int(m.group(1)) if m else None
    if y is None:
        # the most recent Tết that has started by today
        for yy in (as_of.year, as_of.year - 1):
            t = tet_period(yy)
            if t is not None and t.start <= as_of:
                y = yy
                break
    t = tet_period(y) if y else None
    return t


_CMP_SPLIT = re.compile(r"\b(so voi|hon hay kem|tang hay giam|tang hay la giam|tang/giam|hon/kem|"
                        r"cung ky|so cung ky|len hay xuong|cao hay thap|"
                        r"so (?=(?:thang|tuan|quy|nam) (?:lien )?(?:truoc|roi|ngoai)\b))")


def parse_time(q, as_of):
    """Main period from the part of the question before a comparison phrase
    ('tháng này so với tháng trước' is about this month); comparison period
    from the whole question."""
    T = pd.Timestamp(as_of).normalize()
    s = _norm_text(q)
    m = _CMP_SPLIT.search(s)
    if m and m.start() > 0:
        left = s[:m.start()]
        spec = _parse_main(left, T)
        if spec.kind == "default":
            spec = _parse_main(s, T)
    else:
        spec = _parse_main(s, T)
    if spec.compare is None:
        spec.compare = _compare(s, spec, T)
    return spec


def _parse_main(s, T):
    spec = TimeSpec()

    # ---- 'đến hết ngày X' / 'tính đến hôm nay': status at the end of a day
    m = re.search(r"(den het|tinh den|cho den|den cuoi|tinh toi|toi het|cuoi)\s*(ngay\s*)?" + _DMY, s)
    until_day = None
    if m:
        until_day = _date(m.group(3), m.group(4), m.group(5), T)
    elif re.search(r"(tinh den|den het|cuoi ngay|toi gio|hien tai|bay gio|hien con|con lai|"
                    r"dang con|con bao nhieu|con no|con ton)", s) \
            and re.search(r"\b(hom nay|hien tai|bay gio|toi gio|hien con|con)\b", s):
        until_day = T
    if until_day is not None and re.search(r"\btu\s*(ngay\s*\d|\d|dau|thang|hom|tuan)", s):
        until_day = None                       # 'từ X đến hết Y' is a range, not a status
    if until_day is not None:
        spec.until = True

    # ---- enumerated months: '6/2025 → 7/2025 → 8/2025'
    mm = [(int(a), int(b)) for a, b in
          re.findall(r"(?<![\d/])(\d{1,2})\s*/\s*((?:19|20)\d\d)(?![\d/])", s)]
    mm = [x for x in mm if 1 <= x[0] <= 12]
    if len(mm) >= 3 or (len(mm) == 2 and re.search(r"lien tiep|lan luot|xu huong|moi thang|tung thang", s)):
        seen = []
        for x in mm:
            if x not in seen:
                seen.append(x)
        spec.months = [month_period(m_, y_) for m_, y_ in seen]
        spec.main = Period(min(p.start for p in spec.months), max(p.end for p in spec.months))
        spec.explicit, spec.kind = True, "months"

    # ---- explicit ranges: 'từ X đến (hết) Y'
    m = None if spec.main is not None else re.search(r"tu\s*(?:ngay\s*)?" + _DMY + r"\s*(?:den|toi|-)\s*(?:het\s*)?(?:ngay\s*)?" + _DMY, s)
    if m:
        a = _date(m.group(1), m.group(2), m.group(3) or m.group(6), T)
        b = _date(m.group(4), m.group(5), m.group(6) or m.group(3), T)
        if a is not None and b is not None:
            spec.main, spec.explicit, spec.kind = Period(a, b), True, "range"
    if spec.main is None:
        m = re.search(r"tu\s*(?:ngay\s*)?" + _DMY + r"\s*(?:den|toi)\s*(?:het\s*)?(hom nay|nay)", s)
        if m:
            a = _date(m.group(1), m.group(2), m.group(3), T)
            if a is not None:
                spec.main, spec.explicit, spec.kind = Period(a, T), True, "range"
    if spec.main is None:
        m = re.search(r"(?:tu\s*)?thang\s*(\d{1,2})(?:\s*(?:/|nam|-)\s*" + _Y + r")?\s*(?:den|toi|-)\s*"
                      r"(?:het\s*)?thang\s*(\d{1,2})(?:\s*(?:/|nam|-)\s*" + _Y + r")?", s)
        if m:
            y2 = m.group(4) or m.group(2)
            y1 = m.group(2) or m.group(4)
            a = _month_of(m.group(1), y1, T)
            b = _month_of(m.group(3), y2, T)
            if a is not None and b is not None and a.start <= b.start:
                spec.main, spec.explicit, spec.kind = Period(a.start, b.end), True, "months"
                spec.months = _months_between(a, b)

    # ---- 'N tháng liên tiếp / liền nhau kết thúc ở tháng M/Y'
    m = re.search(r"(\d+)\s*thang\s*(lien tiep|lien nhau|lien|gan nhat|gan day)", s)
    if m:
        n = int(m.group(1))
        m2 = re.search(r"(?:ket thuc|den|toi|cuoi)\s*(?:o|vao|la)?\s*thang\s*(\d{1,2})"
                       r"(?:\s*(?:/|nam|-)\s*" + _Y + r")?", s)
        m3 = re.search(r"(?:bat dau|tu)\s*(?:o|vao|la)?\s*thang\s*(\d{1,2})(?:\s*(?:/|nam|-)\s*" + _Y + r")?", s)
        if m2:
            last = _month_of(m2.group(1), m2.group(2), T)
            first = None
        elif m3:
            first = _month_of(m3.group(1), m3.group(2), T)
            last = None
        else:                                   # the last N months up to this month
            last = month_period(T.month, T.year)
            first = None
        if last is not None:
            months = [last]
            for _ in range(n - 1):
                p = months[0].start - pd.DateOffset(months=1)
                months.insert(0, month_period(p.month, p.year))
        else:
            months = [first]
            for _ in range(n - 1):
                p = months[-1].start + pd.DateOffset(months=1)
                months.append(month_period(p.month, p.year))
        spec.months = months
        spec.main, spec.explicit, spec.kind = Period(months[0].start, months[-1].end), True, "months"

    # ---- single explicit periods
    if spec.main is None:
        m = re.search(r"quy\s*(\d)(?:\s*(?:/|nam|-)\s*" + _Y + r")?", s)
        if m and not re.search(r"quy\s*\d\s*\d", s):
            p = _quarter_of(m.group(1), m.group(2), T)
            if p is not None:
                spec.main, spec.explicit, spec.kind = p, True, "quarter"
    if spec.main is None:
        m = re.search(r"thang\s*(\d{1,2})(?:\s*(?:/|nam|-)\s*" + _Y + r")?(?!\s*/\s*\d{1,2}\b)", s)
        if m:
            p = _month_of(m.group(1), m.group(2), T)
            if p is not None:
                spec.main, spec.explicit, spec.kind = p, True, "month"
    if spec.main is None and until_day is None:
        m = re.search(r"(?:ngay\s*)?\b" + _DMY, s)
        if m and (m.group(3) or re.search(r"ngay\s*\d", s)):
            d = _date(m.group(1), m.group(2), m.group(3), T)
            if d is not None:
                spec.main, spec.explicit, spec.kind = Period(d, d), True, "day"
    if spec.main is None:
        m = re.search(r"\bnam\s*" + _Y, s)
        if m:
            spec.main, spec.explicit, spec.kind = year_period(m.group(1)), True, "year"
    if spec.main is None:
        t = _tet(s, T)
        if t is not None:
            spec.main, spec.explicit, spec.kind = t, True, "tet"
            if re.search(r"truoc tet", s):
                spec.compare = Period(t.start - pd.Timedelta(days=t.days), t.start - pd.Timedelta(days=1))
    if spec.main is None:
        r = _relative(s, T)
        if r is not None:
            spec.main, spec.kind = r
            spec.explicit = True

    if until_day is not None and (spec.main is None or spec.kind == "day"):
        spec.main = Period(pd.Timestamp("2000-01-01"), until_day)
        spec.kind = "until"
    if spec.main is None:
        spec.main, spec.kind = Period(T, T), "default"

    return spec


def _months_between(a, b):
    out, cur = [], a.start
    while cur <= b.start:
        out.append(month_period(cur.month, cur.year))
        cur = cur + pd.DateOffset(months=1)
    return out


def _compare(s, spec, T):
    p, kind = spec.main, spec.kind
    if p is None:
        return None
    m = re.search(r"cung ky\s*(cua\s*)?(thang|tuan|quy|nam)?", s)
    if m:
        unit = m.group(2)
        if unit == "thang":
            k = "month_td" if kind in ("month_td", "month") else kind
            if kind == "month":
                pm = p.start - pd.DateOffset(months=1)
                return month_period(pm.month, pm.year)
            return previous_of(p, k, T)
        if unit == "tuan":
            return Period(p.start - pd.Timedelta(days=7), p.end - pd.Timedelta(days=7))
        if unit == "quy":
            return previous_of(p, "quarter_td" if kind == "quarter_td" else "quarter", T)
        return Period(_shift_years(p.start, -1), _shift_years(p.end, -1))
    # explicit second period: 'so với tháng M/Y', 'so với quý Q/Y'
    m = re.search(r"\bso(?: voi)?\s*thang\s*(\d{1,2})(?:\s*(?:/|nam|-)\s*" + _Y + r")?", s)
    if m:
        q = _month_of(m.group(1), m.group(2), T)
        if q is not None:
            return q
    m = re.search(r"so voi\s*quy\s*(\d)(?:\s*(?:/|nam|-)\s*" + _Y + r")?", s)
    if m:
        q = _quarter_of(m.group(1), m.group(2), T)
        if q is not None:
            return q
    if not re.search(r"so voi|hon hay kem|tang hay giam|tang giam|chenh lech|thay doi|tang truong|"
                     r"tang bao nhieu|giam bao nhieu|hon bao nhieu|kem bao nhieu|ky truoc|lien truoc|"
                     r"tang/giam|hon/kem|tang hay la giam|len hay xuong|cao hay thap|"
                     r"\bso (thang|tuan|quy|nam) (lien )?(truoc|roi|ngoai)\b|(thang|tuan|quy|nam) truoc do\b", s):
        return None
    return previous_of(p, kind, T)


def previous_of(p, kind, T):
    """The comparison period 'kỳ trước' of a main period (rulebook §2)."""
    if kind in ("month_td",):
        pm = p.start - pd.DateOffset(months=1)
        last = (pm + pd.offsets.MonthEnd(0)).day
        return Period(pm, pd.Timestamp(pm.year, pm.month, min(p.end.day, last)))
    if kind == "month":
        pm = p.start - pd.DateOffset(months=1)
        return month_period(pm.month, pm.year)
    if kind in ("quarter", "quarter_td"):
        s0 = p.start - pd.DateOffset(months=3)
        if kind == "quarter":
            return quarter_period((s0.month - 1) // 3 + 1, s0.year)
        return Period(s0, s0 + pd.Timedelta(days=p.days - 1))
    if kind in ("year", "year_td"):
        return Period(_shift_years(p.start, -1), _shift_years(p.end, -1))
    if kind in ("week", "week_td"):
        return Period(p.start - pd.Timedelta(days=7), p.end - pd.Timedelta(days=7))
    s0, e0 = prev_period(p.start, p.end)
    return Period(s0, e0)

# ---------------------------------------------------------------- legacy API

def resolve_relative(q, as_of):
    r = _relative(_norm_text(q), pd.Timestamp(as_of).normalize())
    return r[0] if r else None

def resolve_period(q, as_of):
    spec = parse_time(q, as_of)
    return None if spec.kind == "default" else spec.main
