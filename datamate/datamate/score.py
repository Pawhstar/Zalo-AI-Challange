"""Exact ZAC 2026 scorer. Implements the official per-question matching:
type equality, value matching with per-type rules, string normalization
(NFC, lowercase, non-alnum->space, diacritics kept), alias sets,
table column/row matching, list ordering. No partial credit.
"""
import unicodedata, re

def norm_str(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFC", str(s))
    s = s.lower()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch.isspace():
            out.append(" ")
        else:
            out.append(" ")
    return re.sub(r"\s+", " ", "".join(out)).strip()

def norm_cell(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return _num(v)
    return norm_str(v)

def _num(v):
    # numbers match absolutely (float noise ignored): compare rounded to 9dp
    return round(float(v), 9)

def names_equal(a, b):
    na, nb = norm_str(a), norm_str(b)
    if na == nb:
        return True
    return False

def table_match(ans_table, ref_table):
    """columns matched by normalized name (fallback position); rows matched as a SET:
    name cell string rule, numeric cells number rule."""
    acols = [norm_str(c) for c in ans_table.get("columns", [])]
    rcols = [norm_str(c) for c in ref_table.get("columns", [])]
    if acols != rcols:
        # by position
        colmap = list(range(len(rcols)))
        if len(acols) != len(rcols):
            return False
    else:
        colmap = list(range(len(rcols)))
    def norm_row(row, cmap):
        return [norm_cell(c) for c in row]
    arows = [norm_row(r, colmap) for r in ans_table.get("rows", [])]
    rrows = [norm_row(r, colmap) for r in ref_table.get("rows", [])]
    if len(arows) != len(rrows):
        return False
    # set match: each ref row must equal some ans row
    used = [False] * len(arows)
    for rr in rrows:
        found = -1
        for i, ar in enumerate(arows):
            if not used[i] and ar == rr:
                found = i
                break
        if found < 0:
            return False
        used[found] = True
    return True

def list_match(ans_list, ref_list, aliases):
    """position by position; strings compared against reference's accepted forms."""
    if len(ans_list) != len(ref_list):
        return False
    for a, r in zip(ans_list, ref_list):
        if isinstance(r, str) or isinstance(a, str):
            al = aliases.get(id(r), [r])
            ok = False
            for accepted in al:
                if names_equal(a, accepted) or (isinstance(a, (int, float)) and not isinstance(a, bool) and abs(_num(a) - _num(accepted)) < 1e-6 if isinstance(accepted, (int, float)) else False):
                    ok = True
                    break
            if isinstance(a, str) or isinstance(r, str):
                if not ok:
                    return False
        else:
            if _num(a) != _num(r):
                return False
    return True

def value_match(type_, ans, ref, aliases, norm_ans=None, norm_ref=None):
    if type_ in ("number", "percent"):
        if isinstance(ans, bool) or isinstance(ref, bool):
            return False
        if norm_ref is None:
            return abs(_num(ans) - _num(ref)) < 1e-6
        # for percent: rounded to 2dp per rules
        return abs(round(float(ans), 2) - round(float(ref), 2)) < 1e-9
    if type_ == "boolean":
        return isinstance(ans, bool) and isinstance(ref, bool) and ans == ref
    if type_ in ("string", "date"):
        if not isinstance(ans, str) or not isinstance(ref, str):
            return False
        al = aliases.get(id(ref), [ref])
        for accepted in al:
            if norm_ans is not None:
                if norm_ans == norm_str(accepted):
                    return True
            elif names_equal(ans, accepted):
                return True
        return False
    if type_ == "list":
        if not isinstance(ans, list) or not isinstance(ref, list):
            return False
        return list_match(ans, ref, aliases)
    if type_ == "table":
        if not isinstance(ans, dict) or not isinstance(ref, dict):
            return False
        return table_match(ans, ref)
    if type_ == "unanswerable":
        return ref == "unanswerable"
    return False

def score_question(pred, ref, aliases, norm_by_ref=None):
    """pred: dict from submission line (id/type/answer) or None (abstain).
    ref: dict from answers.jsonl. Returns +1, 0, -1.
    Note: giving any answer to an unanswerable question counts as wrong (-1);
    unanswerable only correct if reference is unanswerable. Abstain is 0 everywhere.
    """
    rtype = ref.get("type")
    if pred is None:
        return 0
    ptype = pred.get("type")
    if ptype == "abstain":
        return 0
    if ptype == "unanswerable":
        if rtype == "unanswerable":
            return 1
        return -1
    if ptype != rtype:
        return -1
    if rtype == "unanswerable":
        return 1
    alias_map = {}
    if ref.get("alias"):
        rid = id(ref["answer"])
        alias_map[rid] = list(ref["alias"]) + [ref["answer"]]
    na = norm_by_ref.get(rtype, {}).get(id(ref["answer"])) if norm_by_ref else None
    ok = value_match(rtype, pred.get("answer"), ref["answer"], alias_map)
    return 1 if ok else -1

def penalized_accuracy(preds, refs, aliases_from_refs=True):
    """preds: {id: dict|None}. refs: list of answer dicts with id."""
    byid = {r["id"]: r for r in refs}
    pts = 0
    for qid, pred in preds.items():
        ref = byid.get(qid)
        if ref is None:
            continue
        # build alias map keyed by id(ref["answer"])
        amap = {}
        key = id(ref["answer"])
        forms = [ref["answer"]] + (ref.get("alias") or [])
        amap[key] = forms
        pts += score_question(pred, ref, amap)
    return pts
