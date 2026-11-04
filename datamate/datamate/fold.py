"""Accent folding shared by the router and the period resolver.

Vietnamese questions in this dataset are frequently written without diacritics
("doanh thu hqua", "ban duoc bao nhieu tien"), so every text match runs on the
folded form.
"""
import re
import unicodedata


def fold(s):
    """Lowercase, strip diacritics, collapse whitespace. Keeps digits/letters."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFC", str(s)).lower()
    s = "".join(ch for ch in unicodedata.normalize("NFD", s)
                if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "d")
    return re.sub(r"\s+", " ", s).strip()


def fold_list(lst):
    return [fold(x) for x in lst]
