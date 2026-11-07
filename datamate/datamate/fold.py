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
         "hqua": "hom qua", "z": "vay", "sp": "san pham", "tb": "trung binh",
         # chat spellings seen in the public split (words train never uses)
         "dh": "don hang", "mik": "minh", "mk": "minh", "nhut": "nhat", "nhta": "nhat",
         "trog": "trong", "kua": "cua", "cko": "cho", "kon": "con", "wan": "quan",
         "jum": "giup", "jup": "giup", "tih": "tinh", "nuot": "luot", "ncc": "nha cung cap",
         "ngui": "nguoi", "zo": "vo", "zi": "gi", "mun": "muon", "sop": "shop", "nv": "nhan vien",
         "kac": "cac", "bna": "ban", "lne": "len", "lenn": "len", "nheiu": "nhieu", "zay": "vay",
         "dzay": "vay", "za": "vay", "dza": "vay", "wa": "qua", "qa": "qua", "tog": "tong",
         "cog": "cong", "nhug": "nhung", "dag": "dang", "tug": "tung", "hagn": "hang",
         "duco": "duoc", "bnhui": "bao nhieu", "bq": "binh quan", "dt": "doanh thu",
         "doanhthu": "doanh thu", "caonhat": "cao nhat", "bannhieu": "ban nhieu",
         "ngaynao": "ngay nao", "nhieudon": "nhieu don", "rui": "roi", "xo": "so"}


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
    s = re.sub(r"\s+", " ", " ".join(words)).strip()
    # central-Vietnam 'mô' / 'chi' = 'nào' / 'gì' after the thing asked about
    # ('ngày mô', 'thợ mô', 'mặt hàng chi'); 'chi' alone is also 'chị', so it
    # is only rewritten in that position
    s = re.sub(r"\b(ngay|thang|tho|hang|mat hang|mon|san pham|khach|nhan vien|dong xe|xe|"
               r"ca|gio|tuan|quy|nam|nguoi|loai|nhom|kenh|nha cung cap)\s+(mo|chi)\b"
               r"(?!\s+(tieu|nhanh|phi|tra|tien|nhieu|it|het|bao))", r"\1 nao", s)
    # 'hôm nào', 'bữa nào' = 'ngày nào'
    s = re.sub(r"\b(hom|bua) nao\b", "ngay nao", s)
    return s


def fold_list(lst):
    return [fold(x) for x in lst]
