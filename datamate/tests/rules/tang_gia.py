"""Rulebook §5 'Hiệu ứng tăng giá':
  * Lần tăng giá = ngày D giá mới cao hơn giá liền trước (theo bảng giá);
    tăng lên cùng một giá nhiều lần thì lấy lần đầu.
  * So số lượng (quy về đơn vị cơ bản) N ngày kể từ D (tính cả D: [D, D+N-1])
    với N ngày ngay trước D ([D-N, D-1]); bỏ đơn huỷ và đơn trả.
"""

README = """# Dữ liệu rule_test – Hiệu ứng tăng giá

Cửa hàng tạp hoá / nhà thuốc có bảng lịch sử giá, bảng quy đổi đơn vị và bảng đơn bán hàng.

## File
- `DuLieu.xlsx` (xlsx)

## Quy ước
- Dữ liệu có đến hết 30/04/2026.
- Đơn vị cơ bản của Nước tăng lực Red Bull 250ml là `lon` (1 lốc = 6 lon, 1 thùng = 24 lon).
- Đơn vị cơ bản của Siro ho Prospan chai 100ml là `chai`.
- Bỏ đơn Đã hủy và Trả hàng khi tính số lượng bán.
"""

SAN_PHAM = [
    ["ma_sp", "Món", "Đơn vị", "Giá", "Phân loại"],
    ["SP01", "Nước tăng lực Red Bull 250ml", "lon", 13000, "Nước giải khát"],
    ["SP02", "Siro ho Prospan chai 100ml", "chai", 95000, "Thuốc ho"],
]

QUY_DOI = [
    ["Mã SP", "Tên hàng", "Đơn vị", "Hệ số quy đổi", "Đơn vị cơ bản"],
    ["SP01", "Nước tăng lực Red Bull 250ml", "lon", 1, "lon"],
    ["SP01", "Nước tăng lực Red Bull 250ml", "lốc", 6, "lon"],
    ["SP01", "Nước tăng lực Red Bull 250ml", "thùng", 24, "lon"],
    ["SP02", "Siro ho Prospan chai 100ml", "chai", 1, "chai"],
]

# SP01 increases to 13000 on 10/03/2026 (first time), drops to 12500 on 20/03/2026,
# and increases to 13000 again on 01/04/2026 -> first increase to 13000 is 10/03/2026.
BANG_GIA = [
    ["Mã sản phẩm", "Sản phẩm", "Ngày áp dụng", "Giá cũ", "Giá mới"],
    ["SP01", "Nước tăng lực Red Bull 250ml", "01/01/2026", None, 12000],
    ["SP01", "Nước tăng lực Red Bull 250ml", "10/03/2026", 12000, 13000],
    ["SP01", "Nước tăng lực Red Bull 250ml", "20/03/2026", 13000, 12500],
    ["SP01", "Nước tăng lực Red Bull 250ml", "01/04/2026", 12500, 13000],
    ["SP02", "Siro ho Prospan chai 100ml", "01/01/2026", None, 90000],
    ["SP02", "Siro ho Prospan chai 100ml", "15/03/2026", 90000, 95000],
]

# Sales for SP01 around D = 10/03/2026 (7-day window):
#   Before [03/03..09/03]: ORD01 (04/03, 4 lon) + ORD02 (06/03, 1 lốc = 6 lon) = 10 lon
#                          ORD03 (08/03, 10 lon, Đã hủy) -> excluded
#   After  [10/03..16/03]: ORD04 (10/03, 5 lon) + ORD05 (12/03, 10 lon) = 15 lon
#                          ORD06 (14/03, 5 lon, Trả hàng) -> excluded
#   Change = (15 - 10) / 10 = +50.0%
#
# Sales for SP02 around D = 15/03/2026:
#   7-day window:
#     Before [08/03..14/03]: ORD07 (09/03, 5 chai) + ORD08 (13/03, 3 chai) = 8 chai
#     After  [15/03..21/03]: ORD09 (15/03, 2 chai) + ORD10 (18/03, 4 chai) = 6 chai
#     Change = (6 - 8) / 8 = -25.0%
#   14-day window:
#     Before [01/03..14/03]: 8 chai
#     After  [15/03..28/03]: 6 + ORD11 (25/03, 6 chai) = 12 chai
#     Change = (12 - 8) / 8 = +50.0%
DON_HANG = [
    ["Mã hóa đơn", "Ngày bán", "Khách hàng", "Trạng thái", "Mã SP", "Tên hàng", "Đơn vị", "Số lượng", "SL quy đổi", "Đơn giá", "Thành tiền"],
    ["ORD01", "04/03/2026", "Khách lẻ", "Hoàn thành", "SP01", "Nước tăng lực Red Bull 250ml", "lon", 4, 4, 12000, 48000],
    ["ORD02", "06/03/2026", "Khách lẻ", "Hoàn thành", "SP01", "Nước tăng lực Red Bull 250ml", "lốc", 1, 6, 72000, 72000],
    ["ORD03", "08/03/2026", "Khách lẻ", "Đã hủy", "SP01", "Nước tăng lực Red Bull 250ml", "lon", 10, 10, 12000, 120000],
    ["ORD04", "10/03/2026", "Khách lẻ", "Hoàn thành", "SP01", "Nước tăng lực Red Bull 250ml", "lon", 5, 5, 13000, 65000],
    ["ORD05", "12/03/2026", "Khách lẻ", "Hoàn thành", "SP01", "Nước tăng lực Red Bull 250ml", "lon", 10, 10, 13000, 130000],
    ["ORD06", "14/03/2026", "Khách lẻ", "Trả hàng", "SP01", "Nước tăng lực Red Bull 250ml", "lon", 5, 5, 13000, 65000],
    ["ORD07", "09/03/2026", "Khách lẻ", "Hoàn thành", "SP02", "Siro ho Prospan chai 100ml", "chai", 5, 5, 90000, 450000],
    ["ORD08", "13/03/2026", "Khách lẻ", "Hoàn thành", "SP02", "Siro ho Prospan chai 100ml", "chai", 3, 3, 90000, 270000],
    ["ORD09", "15/03/2026", "Khách lẻ", "Hoàn thành", "SP02", "Siro ho Prospan chai 100ml", "chai", 2, 2, 95000, 190000],
    ["ORD10", "18/03/2026", "Khách lẻ", "Hoàn thành", "SP02", "Siro ho Prospan chai 100ml", "chai", 4, 4, 95000, 380000],
    ["ORD11", "25/03/2026", "Khách lẻ", "Hoàn thành", "SP02", "Siro ho Prospan chai 100ml", "chai", 6, 6, 95000, 570000],
]

A = "2026-04-30"

CASES = [
    {
        "name": "hiệu ứng tăng giá: nêu ngày hoặc tra bảng giá, quy đổi ĐVT cơ bản, bỏ đơn huỷ/trả",
        "readme": README,
        "files": {
            "DuLieu.xlsx": {
                "SanPham": SAN_PHAM,
                "QuyDoi": QUY_DOI,
                "BangGia": BANG_GIA,
                "DonHang": DON_HANG,
            }
        },
        "questions": [
            # 1. Explicit date D = 10/03/2026 with unit conversion (lốc -> lon) and cancelled/returned orders excluded
            (
                "Từ ngày 10/03/2026, Nước tăng lực Red Bull 250ml tăng giá lên 13.000đ. So 7 ngày kể từ ngày 10/03/2026 với 7 ngày ngay trước đó, số lon bán ra thay đổi bao nhiêu phần trăm?",
                A,
                "percent",
                50.0,
            ),
            # 2. Implicit date D looked up from BangGia (first time reaching 13.000đ is 10/03/2026, not 01/04/2026)
            (
                "Nước tăng lực Red Bull 250ml tăng giá lên 13.000đ: so 7 ngày kể từ ngày tăng với 7 ngày ngay trước thì số lon bán ra tăng hay giảm bao nhiêu %?",
                A,
                "percent",
                50.0,
            ),
            # 3. Explicit date D = 15/03/2026 with decrease (-25.0%)
            (
                "Siro ho Prospan chai 100ml đổi giá từ 90.000đ lên 95.000đ vào ngày 15/03/2026. 7 ngày kể từ ngày đó bán được nhiều hay ít hơn 7 ngày liền trước bao nhiêu %, tính theo chai?",
                A,
                "percent",
                -25.0,
            ),
            # 4. Implicit date D looked up from BangGia for Siro ho Prospan (14-day window -> +50.0%)
            (
                "Kể từ khi Siro ho Prospan chai 100ml lên giá 95.000 đồng/chai, 14 ngày đầu bán được nhiều hay ít hơn 14 ngày liền trước đó bao nhiêu phần trăm, tính theo số chai?",
                A,
                "percent",
                50.0,
            ),
        ],
    }
]
