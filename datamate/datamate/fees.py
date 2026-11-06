"""Order-level money rows that are not goods (rulebook public §6, Mẹ và bé).

Some books write, right after the goods lines of an invoice, rows that are not
goods: 'Voucher' (discount of the invoice, negative amount), 'Dùng <n> điểm'
(loyalty points spent, negative amount) and 'Phí ship' (delivery fee). The
loader flags them non_goods and keeps them out of revenue.

Questions about them ('voucher giảm cho khách bao nhiêu', 'khách dùng điểm trừ
được bao nhiêu', 'phí ship bao nhiêu') are answered as a POSITIVE amount,
summed by the invoice date, over invoices that are neither cancelled nor
returned.
"""
import re
import pandas as pd

from datamate.fold import fold, normq
from datamate.periods import parse_time, round_money

# (kind, question pattern, row pattern) on folded text
_KINDS = [
    # normq strips a trailing telex key, turning 'voucher' into 'vouche'
    ("voucher", r"vouche|ma giam gia", r"^(voucher|ma giam gia)"),
    ("points", r"(dung|tru|doi) (\w+ )?diem|diem (thanh vien|tich luy)", r"^(dung|tru) \d+ diem"),
    ("ship", r"phi (ship|giao( hang)?)|tien ship", r"^(phi ship|phi giao( hang)?|ship)"),
]


def _kind(qn):
    hits = [k for k, qp, _ in _KINDS if re.search(qp, qn)]
    return hits[0] if len(hits) == 1 else None


def try_answer(b, q, as_of):
    L = b.lines
    if len(L) == 0 or "non_goods" not in L.columns or not L["non_goods"].any():
        return None
    qn = normq(q)
    kind = _kind(qn)
    if kind is None:
        return None
    # only money questions ('bao nhiêu tiền', 'tổng', 'được bao nhiêu')
    if not re.search(r"bao nhieu|tong|het bao|duoc bao|la bao", qn):
        return None
    ts = parse_time(q, as_of)
    if ts.kind in ("default", "until") or ts.main is None:
        return None                          # period not understood: do not guess
    T = pd.Timestamp(as_of).normalize()
    p = ts.main.clip(T)
    row_pat = dict((k, rp) for k, _, rp in _KINDS)[kind]
    X = L[L["non_goods"]]
    X = X[X["item"].fillna("").astype(str).map(fold).str.match(row_pat)]
    if len(X) == 0:
        return None
    day = pd.to_datetime(X["date"], errors="coerce").dt.normalize()
    X = X[(day >= p.start) & (day <= p.end) & X["valid"].fillna(False).astype(bool)]
    amt = pd.to_numeric(X["line_amount"], errors="coerce").fillna(0)
    return "number", round_money(abs(amt.sum())), f"fee:{kind}:number"
