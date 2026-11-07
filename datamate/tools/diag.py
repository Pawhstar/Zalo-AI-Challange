"""Label-free consistency checks of the loader on any split.

usage: python diag.py public_test [shop ...] [--rebuild]

Every check reports only DATA inconsistencies (never answers). The checks map
onto rulebook sections so a finding points at the rule it can break:

  M0  no sales table found at all                       (§1)
  M1  line revenue != the file's own order total/goods  (§1 doanh thu một đơn)
  M2  order status not classified into the 4 states     (§1, §8 trạng thái)
  M3  item without base unit / conversion factor        (§10 đơn vị cơ bản)
  M4  one customer written several ways                 (§3 xác định khách)
  M5  hour missing although a source hour column exists  (§2 ca, §3 giờ cao điểm)
  M6  dates outside the range the README declares       (§7 kỳ ngoài dữ liệu)
  M7  non-goods rows (voucher / points / fee) kept       (§1, §6 mẹ và bé)
  M8  one item written under several spellings          (§8 cách ghi tên)
  M9  orders with no line rows                           (§1 doanh thu một đơn)
  M10 duplicate rows inside one order                    (§8 dòng trùng)

Each finding prints its evidence (numbers) and the number of the shop's public
questions whose topic the finding can affect, so the table ranks by impact.
No answers and no labels are read.
"""
import sys, os, re, json, pickle
import pandas as pd

from _console import setup_io

setup_io()

import os as _os
# repo root (folder holding Train/ and datamate/); override with DATAMATE_ROOT
ROOT = _os.environ.get("DATAMATE_ROOT") or _os.path.dirname(_os.path.dirname(
    _os.path.dirname(_os.path.abspath(__file__)))).replace("\\", "/")
sys.path.insert(0, ROOT + "/datamate")
from datamate.loader import Business, col_ex, fold

split = sys.argv[1]
base = f"{ROOT}/Train/{split}/data"
cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bizcache_" + split)
os.makedirs(cache, exist_ok=True)
pos = [a for a in sys.argv[2:] if not a.startswith("--")]
rebuild = "--rebuild" in sys.argv
shops = pos or sorted(os.listdir(base))

# Topic keywords, matched against the folded (accent-free) question text.
TOPICS = {
    "revenue":  [r"doanh thu", r"tien ban", r"ban duoc bao nhieu (tien|dong|tri[eê]u)"],
    "qty":      [r"so luong", r"ban duoc bao nhieu"],
    "top":      [r"\bnhat\b", r"nhi?u nhat", r"nhi?u (lan|l[ưu]t)", r"gieo (gi[ơi]i|nhi[ơe]u|t[ơo]t)",
                  r"dat (nhi[ơe]u|t[ơi])", r"m[ặa]t h[ạa]ng", r"nh[âa]n vi[êe]n", r"kh[áa]ch"],
    "orders":   [r"so don", r"bao nhieu don", r"don hang"],
    "cust":     [r"kh[áa]ch"],
    "stock":    [r"ton kho", r"h[ạà]ng c[òo]n", r"c[òo]n t[ơo]n", r"h[ạà]t"],
    "debt":     [r"\bno\b", r"cong no", r"thu no", r"tra no", r"t[ươ]i no", r"n[ơo]i", r"tr[ảa] g[óo]p"],
    "purchase": [r"phieu nhap", r"nha cung cap", r"nhap hang", r"tien nhap", r"sl nhap",
                  r"nha nhap", r"nha phieu", r"hang nhap"],
    "time":     [r"ca (s[ạa]ng|chi[ơe]u)", r"gi[ơo] (cao|n[ơa]o|dat)", r"khung gi[ơo]",
                  r"cao (d[ịi]m|n[ơo])", r"th[ơi] di[ơe]m (dat|s[ạa]ng|chi[ơe]u)"],
    "exp":      [r"h[ạà]n d[ưu]ng", r"h[ạà]t (g[ạa]i|r[ơu]i)", r"he[ơu]t (gi[ạa]|h[ạà]n)",
                  r"h[ạà]t (n[ơa]o|tr[ơu]c|s[ơu])", r"l[ơo] ", r"g[ạà]i t[ơa]ng"],
    "ship":     [r"d[ơo]t (giao|s[ơu])", r"nhi[ơu]u d[ơo]t", r"nhi[ơu]u lan", r"phi (giao|ship)"],
    "warranty": [r"bao (hanh|d[ạa]m|tri[ơu])", r"xe (khach quen|toi|t[ơi]|den)"],
    "walkin":   [r"kh[áa]ch (le|l[ơe]|vang lai|kh[ơo]ng (l[ưu]u|ghi|n[ơo]i))"],
    "employee": [r"nhan vien", r"th[ơo] ", r"ch[ạa]m (chi|c[ơo])"],
    "profit":   [r"loi nhuan", r"gia von", r"l[ãa]i g[ộp]p"],
}
_COMPILED = {t: [re.compile(p, re.I) for p in ps] for t, ps in TOPICS.items()}

# which topics each check can damage
CHECK_TOPICS = {
    "M0": ["revenue", "qty", "top", "orders", "cust", "stock", "debt", "purchase",
           "time", "exp", "ship", "warranty", "walkin", "employee", "profit"],
    "M1": ["revenue", "top", "profit"],
    "M2": ["revenue", "orders", "top", "cust", "profit"],
    "M3": ["qty", "top"],
    "M4": ["cust", "top"],
    "M5": ["time"],
    "M6": ["revenue", "orders", "qty", "top"],
    "M7": ["revenue", "top", "qty"],
    "M8": ["top", "qty"],
    "M9": ["revenue", "orders", "top"],
    "M10": ["revenue", "qty", "orders", "top"],
    "M11": ["qty", "top"],
    "M12": ["cust", "top"],
}

_WALKIN = {"khach le", "le", "khach vang lai", "vang lai", "khach"}


def _person_key(name):
    """Rulebook §3 key for a customer name written on an order: names that
    differ only in how they are written are the same customer; a different
    letter or a different digit is a different customer. Digits are compared
    as a digit sequence, so '0327988481' and '0327 988 481' match."""
    s = fold(name)
    s = re.sub(r"[\(\)\[\]\-\.,:;'\"]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    digits = re.sub(r"\D", "", s)
    letters = re.sub(r"\s+", " ", re.sub(r"\d", "", s)).strip()
    # a name that carries a phone number and one that does not are different
    return letters + "|" + digits


def load_business(bid):
    p = os.path.join(cache, bid + ".pkl")
    if os.path.exists(p) and not rebuild:
        return pickle.load(open(p, "rb"))
    b = Business(bid, f"{base}/{bid}")
    pickle.dump(b, open(p, "wb"))
    return b


def readme_end_date(b):
    for pat in (r"c[ơo] (d[ơe]n|h[ơe]t) h[ơe]t (\d{1,2}/\d{1,2}/\d{4})",
                r"d[ơu] li[ơu]u (t[ơi]|d[ơe]n) (\d{1,2}/\d{1,2}/\d{4})"):
        m = re.search(pat, b.readme)
        if m:
            return pd.to_datetime(m.group(2), dayfirst=True).date()
    return None


# ---------------------------------------------------------------- checks

def check_m0_no_data(b):
    if len(b.orders) == 0 and len(b.lines) == 0:
        files = [f for f in os.listdir(b.path) if not f.lower().endswith(".md")]
        return [("M0", f"no orders and no lines loaded from {len(files)} files: {files[:5]}")]
    return []


def check_m1_revenue(b):
    """Line revenue vs the file's own per-order goods/total column."""
    O = b.orders
    if len(O) == 0:
        return []
    out = []
    for colname, label in (("header_goods", "header-goods"), ("order_goods", "order-goods")):
        if colname not in O.columns or not O[colname].notna().any():
            continue
        g = O[O[colname].notna()]
        if "line_revenue" not in g.columns:
            continue
        both = pd.concat([g["line_revenue"], g[colname]], axis=1).dropna()
        if len(both) == 0:
            continue
        diff = (both.iloc[:, 0] - both.iloc[:, 1]).abs()
        tol = both.iloc[:, 1].abs() * 0.01 + 1.0
        bad = int((diff > tol).sum())
        if bad:
            out.append(("M1", f"{bad}/{len(both)} orders: line-revenue != {label} "
                              f"(sum {both.iloc[:, 0].sum():,.0f} vs {both.iloc[:, 1].sum():,.0f})"))
        else:
            out.append(("M1", f"0 mismatch: line-revenue == {label} on {len(both)} orders"))
    return out


def check_m2_status(b):
    """Order status not classified into the four rulebook states.

    Rulebook §8: a book with no status column keeps the status in the note
    column, and a blank note then means 'completed'. So a blank note is not a
    finding; only note text the classifier does not recognise is."""
    O = b.orders
    if len(O) == 0:
        return []
    st = O["status"].fillna("").astype(str)
    unk = int((st == "").sum())
    if not unk:
        return [("M2", "all orders classified")]
    raw = O["status_raw"].fillna("").astype(str) if "status_raw" in O.columns else \
        pd.Series("", index=O.index)
    nonblank = raw[raw != ""]
    if len(nonblank) == 0:
        return [("M2", f"{unk}/{len(O)} orders have no status; the source records no status either"
                      " (blank note = completed, rulebook §8)")]
    bad = {}
    for v, n in nonblank.value_counts().items():
        from datamate.loader import classify_status
        if classify_status(v) == "":
            bad[v] = int(n)
    if not bad:
        return [("M2", f"{unk}/{len(O)} orders have no status but every note is recognised"
                      " (blank note = completed, rulebook §8)")]
    top = sorted(bad.items(), key=lambda kv: -kv[1])[:4]
    return [("M2", f"{sum(bad.values())} orders carry a note the classifier does not recognise: "
                   + ", ".join(f"{v!r}x{n}" for v, n in top))]


def check_m3_units(b):
    out = []
    I = b.items
    if len(I) == 0:
        return out
    bu = I["base_unit"].fillna("").astype(str)
    missing = int((bu == "").sum())
    if missing:
        out.append(("M3", f"{missing}/{len(I)} catalog items have no base unit"))
    L = b.lines
    if len(L) and len(b.units):
        factors = {fold(u) for u in b.units["unit"]}
        distinct = {u for u in L["unit"].fillna("").astype(str) if u}
        miss = sorted(distinct - factors)
        if miss:
            out.append(("M3", f"{len(miss)} distinct line units lack a conversion factor: {miss[:6]}"))
    return out


def check_m4_customers(b):
    """Customer identity: rulebook §3.

    A shop WITH customer codes: each code is one customer, and two codes with
    the same name are two different customers - nothing to merge. A shop
    WITHOUT codes: the name on the order identifies the customer, and two
    names that differ only in how they are written are the same customer.
    The loader groups by the raw name, so spellings that differ only by
    punctuation, spaces inside the phone number, letter case or accents are
    counted as different customers."""
    O = b.orders
    if len(O) == 0 or "customer" not in O.columns:
        return []
    has_code = "customer_id" in O.columns and \
        (O["customer_id"].fillna("").astype(str) != "").mean() > 0.05
    if has_code:
        return []                      # codes decide identity: nothing to merge
    names = O["customer"].fillna("").astype(str)
    names = names[names != ""]
    f = names.map(fold)
    names = names[~f.isin(_WALKIN)]
    # names that are just numbers are a column mis-mapping, not a spelling issue
    notnum = ~names.map(lambda s: re.fullmatch(r"[0-9.,\s]+", s) is not None)
    names = names[notnum]
    if len(names) == 0:
        return [("M4", "no customer names at all (NO codes)")]
    df = pd.DataFrame({"raw": names})
    df["k"] = df["raw"].map(_person_key)
    n_raw = df["raw"].nunique()
    n_person = df["k"].nunique()
    multi = df.groupby("k")["raw"].nunique()
    multi = multi[multi > 1]
    if n_raw == n_person:
        return [("M4", f"{n_raw} distinct customers, all written consistently (NO codes)")]
    ex = []
    for k in list(multi.index)[:2]:
        variants = sorted(set(df.loc[df["k"] == k, "raw"]))
        ex.append(" / ".join(variants[:3]))
    return [("M4", f"{n_raw} written customer names collapse to {n_person} people (NO codes); "
                   f"{len(multi)} people have >1 spelling, e.g. " + " ; ".join(ex))]


def print_customer_pairs(bid):
    """Print the customer names that are merged and the near-duplicates that
    are NOT merged, so a human can check the normalisation key."""
    b = load_business(bid)
    O = b.orders
    if len(O) == 0 or "customer" not in O.columns:
        return
    has_code = "customer_id" in O.columns and \
        (O["customer_id"].fillna("").astype(str) != "").mean() > 0.05
    print(f"\n=== {bid}: customer name pairs "
          f"({'HAS codes - nothing merged' if has_code else 'NO codes'})")
    names = O["customer"].fillna("").astype(str)
    names = names[names != ""]
    f = names.map(fold)
    names = names[~f.isin(_WALKIN)]
    names = names[~names.map(lambda s: re.fullmatch(r"[0-9.,\s]+", s) is not None)]
    if len(names) == 0:
        print("  (no names)")
        return
    df = pd.DataFrame({"raw": names})
    df["k"] = df["raw"].map(_person_key)
    g = df.groupby("k")["raw"].unique()
    merged = [(k, sorted(v)) for k, v in g.items() if len(v) > 1]
    print(f"-- MERGED pairs (same key, different spelling): {len(merged)} groups")
    for k, v in merged[:10]:
        print("   " + "  ||  ".join(v))
    # near-duplicates that are NOT merged: same letters, different digits
    print("-- NEAR-DUPES NOT merged (same letters, different digits):")
    letters = df["k"].str.split("|").str[0]
    buckets = {}
    for i, l in enumerate(letters):
        buckets.setdefault(l, set()).add(df["k"].iloc[i])
    n = 0
    for l, keys in buckets.items():
        if len(keys) > 1 and n < 10:
            variants = sorted({raw for k in keys for raw in
                               df.loc[df["k"] == k, "raw"].unique()})
            print("   " + "  ||  ".join(variants[:4]))
            n += 1
    if n == 0:
        print("   (none)")


def check_m5_hour(b):
    L = b.lines
    has_col = any(col_ex(h, "hour", []) is not None for _, h in b._iter_tables())
    if not has_col or len(L) == 0 or "hour" not in L.columns:
        return []
    miss = L["hour"].isna().mean()
    if miss > 0.05:
        return [("M5", f"{miss:.0%} of lines have no hour although a source hour column exists")]
    return []


def check_m6_dates(b):
    O = b.orders
    if len(O) == 0:
        return []
    end = readme_end_date(b)
    d = pd.to_datetime(O["date"], errors="coerce").dropna()
    if len(d) == 0:
        return [("M6", "no parsable dates at all")]
    out = []
    if end is not None:
        maxd = d.max().date()
        if maxd > end:
            out.append(("M6", f"latest order {maxd} is after the README end {end}"))
    return out


def check_m7_nongoods(b):
    L = b.lines
    if len(L) == 0 or "non_goods" not in L.columns:
        return []
    n = int(L["non_goods"].sum())
    if not n:
        return []
    kinds = sorted({str(x) for x in L.loc[L["non_goods"], "item"]})[:6]
    return [("M7", f"{n} non-goods rows still present as lines: {kinds}")]


def check_m8_spellings(b):
    L = b.lines
    if len(L) == 0:
        return []
    names = L["item"].fillna("").astype(str)
    names = names[names != ""]
    key = names.map(lambda x: re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", fold(x))).strip())
    g = pd.DataFrame({"k": key, "s": names}).groupby(["k", "s"]).size()
    cnt = g.groupby(level=0).size()
    multi = cnt[cnt > 1]
    if not len(multi):
        return []
    ex = []
    for k in list(multi.index)[:2]:
        ex.append(" / ".join(sorted({s for _, s in g.loc[k].index})[:2]))
    return [("M8", f"{len(multi)} items written under >1 spelling: " + " ; ".join(ex))]


def check_m9_orders_without_lines(b):
    """Valid orders that carry no line revenue at all."""
    O, L = b.orders, b.lines
    if len(O) == 0 or len(L) == 0 or "line_revenue" not in O.columns:
        return []
    miss = O["line_revenue"].isna() & O["is_valid"]
    n = int(miss.sum())
    if not n:
        return []
    oid = set(O.loc[miss, "order_id"])
    rows = int(L["order_id"].isin(oid).sum())
    return [("M9", f"{n}/{len(O)} valid orders have no line revenue ({rows} line rows for them)")]


def check_m10_duplicate_rows(b):
    L = b.lines
    if len(L) == 0:
        return []
    cols = [c for c in ("order_id", "item", "qty", "line_amount", "unit_price") if c in L.columns]
    if len(cols) < 3:
        return []
    L2 = L[cols].astype(object).where(L[cols].notna(), "")
    key = L2.apply(lambda r: "|".join(str(x) for x in r), axis=1)
    dup = int(key.duplicated().sum())
    if dup:
        return [("M10", f"{dup} rows duplicate another row of the same order in every field")]
    return []


def check_m11_conversion(b):
    """A conversion table whose factor ends up on the base unit.

    schema.py maps the README description 'đơn vị quy đổi' to the role
    big_unit, but _build_units only looks for a plain 'unit' column, so the
    factor of '1 hộp = 6 cái' is attached to 'cái' instead of to 'hộp'. No line
    can then be converted to its base unit, and the loader leaves qty_base
    equal to the raw quantity."""
    from datamate.loader import _readme_roles, col_ex
    out = []
    L = b.lines
    for name, h in b._iter_tables():
        rr = _readme_roles(h)
        if not rr or not rr.get("big_unit") or not rr.get("factor"):
            continue
        if col_ex(h, "line_amt", []) is not None or col_ex(h, "order_id", []) is not None:
            continue                                    # a sales table, not a conversion table
        # the big-unit and base-unit COLUMNS; the factor belongs to the big unit
        big_col = rr["big_unit"][0]
        base_col = (rr.get("base_unit") or [None])[0]
        unit_col = (rr.get("unit") or [None])[0]
        # 'unit' resolved to the base-unit column: the factor is attached to
        # the wrong unit (the base unit instead of the big unit)
        if not unit_col or unit_col != base_col or base_col == big_col:
            continue
        items = set()
        for c in ("item_name", "recv_item"):
            if rr.get(c):
                items |= {str(x).strip() for x in h[rr[c][0]].dropna()}
        if not items or len(L) == 0:
            continue
        big_vals = {fold(str(x).strip()) for x in h[big_col].dropna()}
        sub = L[L["item"].isin(items)]
        if not len(sub):
            continue
        big_lines = sub[sub["unit"].fillna("").astype(str).map(fold).isin(big_vals)]
        if not len(big_lines):
            continue
        # the quantity was not converted: qty_base is the raw quantity
        same = (big_lines["qty_base"].fillna(-1) - big_lines["qty"]).abs() < 1e-9
        n_same = int(same.sum())
        out.append(("M11", f"conversion table {name.split('::')[-1]}: factor is attached to the base "
                           f"unit {base_col!r} instead of the big unit {big_col!r}; "
                           f"{n_same}/{len(big_lines)} big-unit lines keep the unconverted quantity"))
    return out


def check_m12_customer_column(b):
    """The customer column holds numbers instead of names.

    A mis-mapped column (a money or quantity column picked up as cust_name)
    makes every customer ranking meaningless."""
    O = b.orders
    if len(O) == 0 or "customer" not in O.columns:
        return []
    names = O["customer"].fillna("").astype(str)
    names = names[names != ""]
    if not len(names):
        return []
    numeric = names.map(lambda s: re.fullmatch(r"[0-9.,\s]+", s) is not None)
    if numeric.mean() > 0.5:
        return [("M12", f"{numeric.mean():.0%} of the customer column is plain numbers "
                       f"({names[numeric].iloc[0]!r} ...) - a column is mis-mapped")]
    return []


CHECKS = [
    ("M0", check_m0_no_data),
    ("M1", check_m1_revenue),
    ("M2", check_m2_status),
    ("M3", check_m3_units),
    ("M4", check_m4_customers),
    ("M5", check_m5_hour),
    ("M6", check_m6_dates),
    ("M7", check_m7_nongoods),
    ("M8", check_m8_spellings),
    ("M9", check_m9_orders_without_lines),
    ("M10", check_m10_duplicate_rows),
    ("M11", check_m11_conversion),
    ("M12", check_m12_customer_column),
]


def main():
    questions_by_shop = {}
    qfile = f"{ROOT}/Train/{split}/questions.jsonl"
    if os.path.exists(qfile):
        with open(qfile, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                q = json.loads(line)
                questions_by_shop.setdefault(q["business_id"], []).append(q)

    rows = []
    for bid in shops:
        b = load_business(bid)
        qs = questions_by_shop.get(bid, [])
        folded = [re.sub(r"\s+", " ", fold(q["question"])).strip() for q in qs]
        for tag, fn in CHECKS:
            for t, msg in fn(b):
                imp = 0
                for topic in CHECK_TOPICS[tag]:
                    pats = _COMPILED[topic]
                    imp += sum(1 for txt in folded if any(p.search(txt) for p in pats))
                # a question touching several affected topics counts once
                rows.append((bid, tag, msg, imp, len(qs)))
    rows.sort(key=lambda r: (-r[3], r[0], r[1]))
    print(f"{'shop':9} {'check':5} {'evidence':72} impact")
    print("-" * 110)
    for bid, tag, msg, imp, nq in rows:
        print(f"{bid:9} {tag:5} {msg[:70]:72} {imp}/{nq}")
    if not rows:
        print("(no findings)")
    if "--pairs" in sys.argv:
        for bid in shops:
            print_customer_pairs(bid)


if __name__ == "__main__":
    main()
