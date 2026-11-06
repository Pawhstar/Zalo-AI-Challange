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


_TYPO = {"cuwar": "cua", "hown": "hon", "nhiu": "nhieu", "bnhiu": "bao nhieu", "bn": "bao nhieu",
         "bnhieu": "bao nhieu", "dc": "duoc", "dk": "duoc", "ko": "khong", "k": "khong",
         "dthu": "doanh thu", "sl": "so luong", "trc": "truoc", "hnay": "hom nay",
         "hqua": "hom qua", "z": "vay", "sp": "san pham", "tb": "trung binh"}


def _detelex(w):
    """Undo stray telex keystrokes left in folded words: 'cungf' -> 'cung',
    'nhieeu' -> 'nhieu', 'thangs' -> 'thang', 'vaayj' -> 'vay'."""
    if not w.isalpha() or len(w) < 3:
        return w
    if w[-1] in "fsrxj" and w[-2] in "aeiouynghmcpt":
        w = w[:-1]
    w = re.sub(r"([aeo])\1", r"\1", w)
    w = re.sub(r"(?<=[^aeiou])w(?=[a-z])", "", w)          # 'cuwa' -> 'cua'
    w = w.replace("ow", "o").replace("uw", "u").replace("aw", "a")
    return w


def normq(s):
    """Folded question text with telex typos and common shorthands normalised.
    Used for intent and period matching (never for names)."""
    s = fold(s)
    s = re.sub(r"[?!;]|,(?=\s)|,$", " ", s)
    words = []
    for w in s.split():
        w = _detelex(w)
        words.append(_TYPO.get(w, w))
    return re.sub(r"\s+", " ", " ".join(words)).strip()


def fold_list(lst):
    return [fold(x) for x in lst]
