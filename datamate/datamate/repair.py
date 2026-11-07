"""Motorbike repair books (rulebook public §6, Sửa xe).

A repair book has one row per visit (one ticket, 'phiếu'): date, the bike
(model and plate written in one cell), what was done (several jobs in one
cell), the mechanic (written by nickname), the ticket total and a note. There
is no ticket code and no customer. A ticket noted 'bảo hành' with amount 0 is a
warranty return: it is a ticket and a visit, but brings no money.

build(b) turns such a book into the canonical model so the shared answer
modules work on it: one order per ticket (revenue = ticket total, employee =
the mechanic's full name) and one line per ticket whose item is the bike model.
Extra columns on the orders (plate, model, jobs, warranty) feed the
repair-specific answers in repair_answer.py.

Nothing here is specific to one shop: columns are found from the README
descriptions, mechanics are matched to the staff list by their given name, and
model spellings are merged when the same plate was written with both
('AB' / 'Air Blade', 'Vision' / 'Vision 110').
"""
import re
import numpy as np
import pandas as pd

from datamate.fold import fold

PLATE = re.compile(r"\b\d{2}[A-Z]{1,2}\d?\s*-\s*\d{3}\.?\d{2}\b")

# README description keyword -> role (folded text)
_DESC = [("vehicle", r"bien so|dong xe"), ("jobs", r"viec|lam gi|cong viec"),
         ("mechanic", r"\btho\b"), ("amount", r"tong tien|tien ca phieu|tien"),
         ("date", r"^ngay"), ("note", r"ghi chu")]
_HEAD = {"vehicle": r"^xe$|bien so", "jobs": r"lam gi|cong viec", "mechanic": r"^tho",
         "amount": r"^tien|thanh tien|tong tien", "date": r"^ngay", "note": r"ghi chu"}


def _roles(b, h):
    """role -> column of a candidate repair table."""
    from datamate import schema
    out = {}
    secs = getattr(b, "_readme_sections", []) or []
    keys = {schema._key(c): c for c in h.columns}
    best = None
    for s in secs:
        n = len(set(s["cols"]) & set(keys))
        if n >= 3 and (best is None or n > best[0]):
            best = (n, s)
    if best:
        for k, (hdr, desc) in best[1]["cols"].items():
            if k not in keys:
                continue
            d = fold(desc)
            for role, pat in _DESC:
                if role not in out and re.search(pat, d):
                    out[role] = keys[k]
                    break
    for role, pat in _HEAD.items():
        if role not in out:
            for c in h.columns:
                if re.search(pat, fold(c)) and c not in out.values():
                    out[role] = c
                    break
    return out


def _staff(b):
    """Full names of the mechanics and their commission rate, from a staff list
    ('Họ tên', 'Hoa hồng (%)')."""
    from datamate.loader import parse_num, norm
    for name, h in b._iter_tables():
        cn = next((c for c in h.columns if re.search(r"ho ten|ten tho|ho va ten", fold(c))), None)
        if cn is None:
            continue
        cr = next((c for c in h.columns if re.search(r"hoa hong|hue hong|% ", fold(c))), None)
        t = pd.DataFrame({"name": h[cn].map(norm)})
        t["rate"] = h[cr].map(parse_num) if cr else np.nan
        t = t[t["name"] != ""]
        if len(t):
            return t.reset_index(drop=True)
    return pd.DataFrame(columns=["name", "rate"])


def mechanic_map(raw_names, staff):
    """nickname -> full name. 'A.Đức', 'a Đức', 'anh Đức', 'Đức' -> the staff
    member whose given name (last word) is Đức; unmatched or ambiguous names
    keep their own spelling."""
    given = {}
    for full in staff["name"]:
        g = fold(full).split()[-1] if fold(full) else ""
        given.setdefault(g, []).append(full)
    out = {}
    for r in set(raw_names):
        s = fold(r)
        s = re.sub(r"^(anh|chi|a|c|em|e)[\s.]+", "", s).strip()
        g = s.split()[-1] if s else ""
        cands = given.get(g, [])
        if len(cands) == 1:
            out[r] = cands[0]
        else:
            # a full name written out ('Lương Chi Đức') matches itself
            full = [f for f in staff["name"] if fold(f) == s]
            out[r] = full[0] if full else r
    return out


def model_groups(plates, models):
    """Merge model spellings written for the same plate (union-find), then
    represent each group by its most frequent spelling."""
    key = [re.sub(r"\s+", "", fold(m)) for m in models]
    par = {}

    def find(x):
        par.setdefault(x, x)
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    by_plate = {}
    for p, k in zip(plates, key):
        if k:
            find(k)
            if p:
                by_plate.setdefault(p, set()).add(k)
    for ks in by_plate.values():
        ks = sorted(ks)
        for k in ks[1:]:
            par[find(k)] = find(ks[0])
    counts = {}
    for m, k in zip(models, key):
        if k:
            counts.setdefault(find(k), {}).setdefault(m, 0)
            counts[find(k)][m] += 1
    rep = {g: max(c.items(), key=lambda kv: (kv[1], kv[0]))[0] for g, c in counts.items()}
    return [rep.get(find(k), m) if k else m for m, k in zip(models, key)]


def build(b):
    """(orders, lines) for a repair book, or None when the shop has none."""
    from datamate.loader import parse_num, parse_date, norm
    best = None
    for name, h in b._iter_tables():
        if len(h) < 5:
            continue
        r = _roles(b, h)
        if not all(k in r for k in ("vehicle", "jobs", "amount", "date")):
            continue
        veh = h[r["vehicle"]].fillna("").astype(str)
        hit = veh.str.contains(PLATE).mean()
        if hit < 0.8:
            continue
        if best is None or len(h) > len(best[1]):
            best = (name, h, r)
    if best is None:
        return None
    name, h, r = best
    h = h[h[r["vehicle"]].fillna("").astype(str).str.contains(PLATE)].reset_index(drop=True)
    veh = h[r["vehicle"]].astype(str).map(norm)
    plate = veh.str.extract("(" + PLATE.pattern + ")")[0].fillna("")
    plate = plate.str.replace(r"\s+", "", regex=True).str.replace(".", "", regex=False).str.upper()
    model_raw = [norm(PLATE.sub("", v)) for v in veh]
    staff = _staff(b)
    mech_raw = h[r["mechanic"]].map(norm) if "mechanic" in r else pd.Series("", index=h.index)
    mmap = mechanic_map(mech_raw, staff) if len(staff) else {}
    note = h[r["note"]].map(norm) if "note" in r else pd.Series("", index=h.index)
    O = pd.DataFrame()
    O["order_id"] = [f"P{i + 1:06d}" for i in range(len(h))]
    O["date"] = pd.to_datetime(h[r["date"]].map(parse_date), errors="coerce").dt.normalize()
    O["status"] = "done"
    O["status_raw"] = ""
    O["customer"] = ""
    O["customer_id"] = ""
    O["employee"] = mech_raw.map(lambda x: mmap.get(x, x))
    O["employee_raw"] = mech_raw.values
    O["channel"] = ""
    O["payment_method"] = ""
    O["hour"] = np.nan
    amt = pd.to_numeric(h[r["amount"]].map(parse_num), errors="coerce")
    O["order_goods"] = amt.values
    O["order_discount"] = np.nan
    O["order_total"] = amt.values
    O["paid"] = np.nan
    O["debt"] = np.nan
    O["delivery_fee"] = np.nan
    O["plate"] = plate.values
    O["model"] = model_groups(list(plate), model_raw)
    O["model_raw"] = model_raw
    O["jobs"] = h[r["jobs"]].map(norm).values
    O["note"] = note.values
    O["warranty"] = note.map(lambda s: bool(re.search(r"bao hanh", fold(s)))).values
    O["walk_in"] = True
    O["is_valid"] = True
    O["revenue"] = O["order_goods"]
    O["line_revenue"] = O["order_goods"]
    O["n_lines"] = 1
    L = pd.DataFrame({
        "order_id": O["order_id"], "date": O["date"], "item": O["model"], "item_id": "",
        "qty": 1.0, "unit": "lượt", "unit_price": O["order_goods"], "line_discount": np.nan,
        "line_amount": O["order_goods"], "qty_base": 1.0, "cost_price": np.nan,
        "status_raw": "", "status": "done", "customer": "", "customer_id": "",
        "employee": O["employee"], "channel": "", "payment_method": "", "hour": np.nan,
        "valid": True, "revenue": O["order_goods"], "non_goods": False})
    b.repair_staff = staff
    return L, O, {name}
