"""Rulebook public §6 Mẹ và bé: tiền giảm voucher, tiền giảm nhờ dùng điểm,
phí ship -> số dương, cộng theo ngày của hoá đơn, chỉ hoá đơn không huỷ,
không trả. All data below is invented; answers are computed by hand.

Invoices (HĐ):
  HĐ1 03/05/2026  A 2x100000 | Voucher -20000 | Phí ship 25000          completed
  HĐ2 10/05/2026  B 1x50000  | Dùng 200 điểm -20000                     completed
  HĐ3 15/05/2026  A 1x100000 | Voucher -10000 | Phí ship 30000          Huỷ  -> out
  HĐ4 01/06/2026  B 2x50000  | Voucher -15000 | Dùng 300 điểm -30000 | Phí ship 20000
  HĐ5 02/06/2026  A 1x100000 | Phí ship 25000                          đang giao -> in
  HĐ6 05/06/2026  B 1x50000  | Voucher -5000                           khách trả lại -> out
"""

README = """# Dữ liệu rule_test

Sổ bán hàng tiệm mẹ và bé. Mỗi dòng một mặt hàng khách mua; một hoá đơn nhiều dòng cùng số HĐ. Ngay sau các dòng hàng của một hoá đơn có thể có dòng không phải hàng, chỉ ghi HĐ, tên và TT: "Voucher" (TT ghi số âm), "Dùng <n> điểm" (TT ghi số âm), "Phí ship" (phí giao hàng khách trả thêm).

## File
- `BanHang_2026.xlsx` (xlsx)

## Cột trong `BanHang_2026.xlsx`
- **ĐG**: đơn giá
- **TT**: thành tiền của dòng; Voucher, Dùng điểm ghi số âm (trừ vào hoá đơn), Phí ship ghi phí giao
- **SL**: số lượng (trống ở dòng không phải hàng)
- **ĐVT**: đơn vị tính
- **Tên hàng**: tên hàng; dòng không phải hàng ghi Voucher, Dùng <n> điểm hoặc Phí ship
- **HĐ**: số hoá đơn, ghi ở mọi dòng của hoá đơn kể cả dòng Voucher / Dùng điểm / Phí ship
- **Ngày**: ngày bán (dòng Voucher / Dùng điểm / Phí ship để trống)
- **Khách**: tên khách thành viên (Khách lẻ nếu không lưu); dòng không phải hàng để trống
- **Ghi chú**: ghi chú của đơn; đơn huỷ hoặc đang giao được ghi ở đây, không có cột trạng thái riêng

## Quy ước
- Dữ liệu có đến hết 30/06/2026.
"""

H = ["ĐG", "TT", "SL", "ĐVT", "Tên hàng", "HĐ", "Ngày", "Khách", "Ghi chú"]
N = None
MAY = [H,
       [100000, 200000, 2, "hộp", "Sữa A", "HĐ1", "03/05/2026", "Chị Lan", N],
       [N, -20000, N, N, "Voucher", "HĐ1", N, N, N],
       [N, 25000, N, N, "Phí ship", "HĐ1", N, N, N],
       [50000, 50000, 1, "gói", "Tã B", "HĐ2", "10/05/2026", "Khách lẻ", N],
       [N, -20000, N, N, "Dùng 200 điểm", "HĐ2", N, N, N],
       [100000, 100000, 1, "hộp", "Sữa A", "HĐ3", "15/05/2026", "Chị Mai", "Huỷ"],
       [N, -10000, N, N, "Voucher", "HĐ3", N, N, N],
       [N, 30000, N, N, "Phí ship", "HĐ3", N, N, N]]
JUN = [H,
       [50000, 100000, 2, "gói", "Tã B", "HĐ4", "01/06/2026", "Chị Lan", N],
       [N, -15000, N, N, "Voucher", "HĐ4", N, N, N],
       [N, -30000, N, N, "Dùng 300 điểm", "HĐ4", N, N, N],
       [N, 20000, N, N, "Phí ship", "HĐ4", N, N, N],
       [100000, 100000, 1, "hộp", "Sữa A", "HĐ5", "02/06/2026", "Chị Mai", "đang giao"],
       [N, 25000, N, N, "Phí ship", "HĐ5", N, N, N],
       [50000, 50000, 1, "gói", "Tã B", "HĐ6", "05/06/2026", "Chị Hoa", "khách trả lại"],
       [N, -5000, N, N, "Voucher", "HĐ6", N, N, N]]

CASES = [{
    "name": "voucher / điểm / phí ship cộng theo ngày hoá đơn, bỏ huỷ và trả",
    "readme": README,
    "files": {"BanHang_2026.xlsx": {"T05-2026": MAY, "T06-2026": JUN}},
    "questions": [
        # voucher: HĐ3 huỷ, HĐ6 trả -> ngoài
        ("Tháng 5/2026 voucher giảm cho khách hết bao nhiêu tiền?", "2026-06-30", "number", 20000),
        ("Tháng 6/2026 tiền giảm voucher là bao nhiêu?", "2026-06-30", "number", 15000),
        ("Từ đầu năm tới nay voucher giảm tổng cộng bao nhiêu?", "2026-06-30", "number", 35000),
        # điểm
        ("Tháng 5/2026 khách dùng điểm trừ được bao nhiêu tiền?", "2026-06-30", "number", 20000),
        ("Tháng 6/2026 tiền giảm nhờ dùng điểm là bao nhiêu?", "2026-06-30", "number", 30000),
        ("Tuần trước khách dùng điểm trừ bao nhiêu tiền?", "2026-06-08", "number", 30000),
        # phí ship: HĐ5 đang giao vẫn tính
        ("Tháng 5/2026 tiệm thu phí ship được bao nhiêu tiền?", "2026-06-30", "number", 25000),
        ("Tháng 6/2026 tổng tiền phí ship là bao nhiêu?", "2026-06-30", "number", 45000),
        ("Ngày 01/06/2026 phí ship là bao nhiêu?", "2026-06-30", "number", 20000),
        # doanh thu không gồm voucher/điểm/ship (§1); HĐ6 trả -> ngoài
        ("Doanh thu tháng 6/2026 là bao nhiêu?", "2026-06-30", "number", 200000),
        ("Doanh thu tháng 5/2026 là bao nhiêu?", "2026-06-30", "number", 250000),
    ],
}]
