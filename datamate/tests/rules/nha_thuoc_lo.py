"""Rulebook §6 'Nhà thuốc' (và §9 thứ tự sắp xếp, §7 không trả lời được):
  * Hàng hết hạn trong N ngày tới (tại hôm nay D): lô còn tồn có hạn dùng từ D
    đến hết D + N.
  * Tiền vốn nằm ở các lô sắp hết hạn: tính theo phần còn tồn của từng lô nhân
    với đơn giá nhập quy về đơn vị cơ bản của chính lô đó (không tính theo giá
    vốn bình quân).
  * Lô gần hết hạn nhất của một thuốc: trong các lô còn tồn và chưa quá hạn tại
    hôm nay (HSD >= D), lấy hạn dùng sớm nhất.
  * Liệt kê mặt hàng sắp hết hạn: sắp theo hạn sớm nhất của mặt hàng trong
    khoảng, cùng hạn thì theo mã mặt hàng.
  * Nếu cửa hàng không có sổ theo dõi lô và hạn dùng thì trả về unanswerable.
"""

README_LOT = """# Dữ liệu rule_test – Nhà thuốc (Lô & Hạn dùng)

Nhà thuốc quản lý nhập hàng và bán hàng theo lô, có hạn sử dụng cho từng lô.

## File
- `NhaThuoc.xlsx` (xlsx)

## Quy ước
- Dữ liệu có đến hết 01/06/2026.
- Số lượng trong bảng lô và bảng chi tiết đơn theo lô đều đã quy về đơn vị cơ bản.
- Bỏ phiếu nhập Đã hủy và đơn bán Đã hủy; trừ lại số lượng khách trả (`SLTraQuyDoi`).
"""

SAN_PHAM = [
    ["MaHangHoa", "TenGoi", "DonViCoSo", "GiaBanLe", "GiaVonHang", "DanhMuc"],
    ["SP01", "Panadol Extra hộp 15 vỉ x 12 viên", "viên", 1500, 1200, "giảm đau hạ sốt"],
    ["SP02", "Siro ho Prospan chai 100ml", "chai", 95000, 75000, "ho cảm cúm"],
    ["SP03", "Oresol 245 DHG hộp 20 gói", "gói", 2000, 1600, "tiêu hoá"],
]

PHIEU_NHAP = [
    ["MaPhieuNhap", "NgayNhapKho", "TinhTrang", "TongGiaTriNhap"],
    ["PN01", "01/05/2026", "Hoàn thành", 370000],
    ["PN02", "10/05/2026", "Hoàn thành", 2286000],
    ["PN03", "15/05/2026", "Đã hủy", 2100000],
]

# Remaining quantities as of D = 01/06/2026:
#   L01 (SP01, HSD 20/06/2026, cost 1000): in 100, sold (40 - 10 returned) = 30 -> rem = 70, cap = 70,000
#   L02 (SP01, HSD 15/12/2026, cost 1100): in 200, sold 0                       -> rem = 200, cap = 220,000
#   L03 (SP01, HSD 10/06/2026, cost 1000): in 50,  sold 50                      -> rem = 0 (out of stock)
#   L04 (SP02, HSD 15/06/2026, cost 70000): in 20, sold 5 (ORD03 cancelled)     -> rem = 15, cap = 1,050,000
#   L05 (SP02, HSD 20/05/2026, cost 68000): in 10, sold 0                       -> rem = 10 (already expired < 01/06/2026)
#   L06 (SP03, HSD 10/07/2026, cost 1500): in 100, sold 20                      -> rem = 80, cap = 120,000
#   L07 (SP03, HSD 20/06/2026, cost 1400): in 40,  sold 10                      -> rem = 30, cap = 42,000
#   L08 (SP02, HSD 05/06/2026, cost 70000): in 30, from cancelled PN03          -> ignored
LO_HANG = [
    ["MaLo", "MaPhieuNhap", "MaHangHoa", "HanSuDung", "SLNhapQuyDoi", "DonGiaNhap"],
    ["L01", "PN01", "SP01", "2026-06-20", 100, 1000],
    ["L02", "PN01", "SP01", "2026-12-15", 200, 1100],
    ["L03", "PN01", "SP01", "2026-06-10", 50, 1000],
    ["L04", "PN02", "SP02", "2026-06-15", 20, 70000],
    ["L05", "PN02", "SP02", "2026-05-20", 10, 68000],
    ["L06", "PN02", "SP03", "2026-07-10", 100, 1500],
    ["L07", "PN02", "SP03", "2026-06-20", 40, 1400],
    ["L08", "PN03", "SP02", "2026-06-05", 30, 70000],
]

HOA_DON = [
    ["MaHoaDon", "NgayBan", "KhachHang", "TrangThai", "TongTien"],
    ["ORD01", "05/05/2026", "Khách lẻ", "Hoàn thành", 120000],
    ["ORD02", "12/05/2026", "Khách lẻ", "Hoàn thành", 535000],
    ["ORD03", "18/05/2026", "Khách lẻ", "Đã hủy", 475000],
]

CHI_TIET_HOA_DON = [
    ["MaHoaDon", "MaHangHoa", "TenGoi", "DonVi", "SoLuong", "DonGia", "ThanhTien"],
    ["ORD01", "SP01", "Panadol Extra hộp 15 vỉ x 12 viên", "viên", 80, 1500, 120000],
    ["ORD02", "SP02", "Siro ho Prospan chai 100ml", "chai", 5, 95000, 475000],
    ["ORD02", "SP03", "Oresol 245 DHG hộp 20 gói", "gói", 30, 2000, 60000],
    ["ORD03", "SP02", "Siro ho Prospan chai 100ml", "chai", 5, 95000, 475000],
]

CHI_TIET_DON_LO = [
    ["MaHoaDon", "SoThuTu", "MaLo", "SLQuyDoi", "SLTraQuyDoi"],
    ["ORD01", 1, "L03", 50, 0],
    ["ORD01", 2, "L01", 40, 10],
    ["ORD02", 1, "L04", 5, 0],
    ["ORD02", 2, "L06", 20, 0],
    ["ORD02", 3, "L07", 10, 0],
    ["ORD03", 1, "L04", 5, 0],
]

README_NO_LOT = """# Dữ liệu rule_test – Cửa hàng không theo dõi lô

Cửa hàng chỉ lưu danh mục hàng và hóa đơn bán, không có bảng lô hay hạn sử dụng.

## File
- `BanHang.xlsx` (xlsx)
"""

A = "2026-06-01"

CASES = [
    {
        "name": "nhà thuốc: lô gần hết hạn nhất, tiền vốn lô sắp hết hạn, danh sách & số lượng lô/mặt hàng hết hạn",
        "readme": README_LOT,
        "files": {
            "NhaThuoc.xlsx": {
                "SanPham": SAN_PHAM,
                "PhieuNhap": PHIEU_NHAP,
                "LoHang": LO_HANG,
                "HoaDon": HOA_DON,
                "ChiTietHoaDon": CHI_TIET_HOA_DON,
                "ChiTietDonLo": CHI_TIET_DON_LO,
            }
        },
        "questions": [
            # --- tag: lot:nearest_expiry:date (3 questions) ---
            (
                "Tính đến hết ngày 01/06/2026, lô Panadol Extra hộp 15 vỉ x 12 viên gần hết hạn nhất có hạn dùng ngày nào?",
                A,
                "date",
                "2026-06-20",
            ),
            (
                "Lô Siro ho Prospan chai 100ml gần hết hạn nhất có hạn dùng là ngày mấy?",
                A,
                "date",
                "2026-06-15",
            ),
            (
                "Cho hỏi tới ngày 01/06/2026, lô Oresol 245 DHG hộp 20 gói gần hết hạn nhất có hạn dùng ngày nào?",
                A,
                "date",
                "2026-06-20",
            ),
            # --- tag: lot:expiring_capital:number (3 questions) ---
            (
                "Tính đến hết ngày 01/06/2026, tiền vốn đang nằm ở các lô còn tồn có hạn dùng từ 01/06/2026 đến hết 01/07/2026 là bao nhiêu?",
                A,
                "number",
                1162000,
            ),
            (
                "Tiền vốn đang nằm ở các lô còn tồn sắp hết hạn trong 60 ngày tới, tức hạn dùng từ 01/06/2026 đến hết 31/07/2026, là bao nhiêu tiền?",
                A,
                "number",
                1282000,
            ),
            (
                "Tại ngày 01/06/2026, các lô còn tồn hết hạn trong 15 ngày tới (từ 01/06/2026 đến hết 16/06/2026) có tổng tiền vốn là bao nhiêu?",
                A,
                "number",
                1050000,
            ),
            # --- tag: lot:expiring_items:list (3 questions) ---
            (
                "Tính tới hết ngày 01/06/2026, hàng nào hết hạn trong 15 ngày tới, từ 01/06/2026 đến hết 16/06/2026, mà hiện vẫn còn tồn kho?",
                A,
                "list",
                ["Siro ho Prospan chai 100ml"],
            ),
            (
                "Những sản phẩm nào đang còn hàng có hạn dùng từ 01/06/2026 đến hết 01/07/2026?",
                A,
                "list",
                [
                    "Siro ho Prospan chai 100ml",
                    "Panadol Extra hộp 15 vỉ x 12 viên",
                    "Oresol 245 DHG hộp 20 gói",
                ],
            ),
            (
                "Tính đến hết ngày 01/06/2026, những mặt hàng nào còn lô tồn sắp hết hạn trong 60 ngày tới (01/06/2026 - 31/07/2026)?",
                A,
                "list",
                [
                    "Siro ho Prospan chai 100ml",
                    "Panadol Extra hộp 15 vỉ x 12 viên",
                    "Oresol 245 DHG hộp 20 gói",
                ],
            ),
            # --- tag: lot:expiring_count:number (3 questions) ---
            (
                "Theo tồn kho ngày 01/06/2026, có mấy lô hàng còn tồn sẽ hết hạn từ nay đến hết ngày 01/07/2026?",
                A,
                "number",
                3,
            ),
            (
                "Tính đến hết ngày 01/06/2026, có bao nhiêu lô hàng còn tồn sẽ hết hạn trong 60 ngày tới, tức hạn dùng từ 01/06/2026 đến hết 31/07/2026?",
                A,
                "number",
                4,
            ),
            (
                "Tính đến hết ngày 01/06/2026, có mấy mặt hàng còn lô tồn sắp hết hạn trong 15 ngày tới, tức hạn dùng từ 01/06/2026 đến hết 16/06/2026?",
                A,
                "number",
                1,
            ),
        ],
    },
    {
        "name": "cửa hàng không có dữ liệu lô/hạn dùng -> unanswerable",
        "readme": README_NO_LOT,
        "files": {
            "BanHang.xlsx": {
                "SanPham": SAN_PHAM,
                "HoaDon": HOA_DON,
                "ChiTietHoaDon": CHI_TIET_HOA_DON,
            }
        },
        "questions": [
            # --- tag: lot:no_data:unanswerable (3 questions) ---
            (
                "Những sản phẩm nào đang còn hàng có hạn dùng từ 01/06/2026 đến hết 01/07/2026?",
                A,
                "unanswerable",
                None,
            ),
            (
                "Hàng nào hết hạn trong 30 ngày tới, từ 01/06/2026 đến hết 01/07/2026, mà hiện vẫn còn tồn kho?",
                A,
                "unanswerable",
                None,
            ),
            (
                "Lô Siro ho Prospan chai 100ml gần hết hạn nhất có hạn dùng ngày nào?",
                A,
                "unanswerable",
                None,
            ),
        ],
    },
]
