"""Rulebook §7: a question about something the books do not record (a
personal judgement of a customer, an employee or an item) is unanswerable.
A question that only contains such a word inside a name is not."""

README = """# Dữ liệu rule_test

File Excel xuất từ phần mềm bán hàng. Mỗi dòng một dòng hàng.

## File
- `BanHang.csv` (csv)

## Cột trong `BanHang.csv`
- **Mã đơn hàng**: mã đơn
- **Ngày**: ngày bán
- **Khách hàng**: tên khách (Khách lẻ nếu không lưu)
- **Nhân viên**: nhân viên bán
- **Tên hàng**: tên hàng
- **Số lượng**: số lượng
- **Đơn giá**: đơn giá
- **Thành tiền**: thành tiền sau giảm
- **Trạng thái**: trạng thái đơn

## Quy ước
- Dữ liệu có đến hết 30/06/2026.
"""

ROWS = [["Mã đơn hàng", "Ngày", "Khách hàng", "Nhân viên", "Tên hàng", "Số lượng", "Đơn giá", "Thành tiền", "Trạng thái"],
        ["ORD000001", "02/06/2026", "Chị Lan", "Minh", "Bánh mì ngon", 2, 20000, 40000, "Hoàn thành"],
        ["ORD000002", "03/06/2026", "Anh Hùng", "Minh", "Cà phê sữa", 1, 25000, 25000, "Hoàn thành"],
        ["ORD000003", "03/06/2026", "Chị Lan", "Hoa", "Cà phê sữa", 2, 25000, 50000, "Hoàn thành"],
        ["ORD000004", "05/06/2026", "Khách lẻ", "Hoa", "Bánh mì ngon", 1, 20000, 20000, "Đã huỷ"],
        ["ORD000005", "06/06/2026", "Anh Hùng", "Minh", "Cà phê sữa", 1, 25000, 25000, "Hoàn thành"],
        ["ORD000006", "07/06/2026", "Chị Lan", "Hoa", "Bánh mì ngon", 1, 20000, 20000, "Hoàn thành"]]

A = "2026-06-30"
CASES = [{
    "name": "câu hỏi về phẩm chất không có trong dữ liệu",
    "readme": README,
    "files": {"BanHang.csv": ROWS},
    "questions": [
        ("Tháng 6/2026 khách nào khó tính nhất?", A, "unanswerable", None),
        ("Nhân viên Minh có lễ phép với khách không?", A, "unanswerable", None),
        ("Ai trong cửa hàng được khách quý mến nhất?", A, "unanswerable", None),
        ("Tháng 6/2026 nhân viên nào thân thiện nhất?", A, "unanswerable", None),
        ("Khách hàng trung thực nhất tháng 6/2026 là ai?", A, "unanswerable", None),
        # a word inside an item name is not a judgement
        # ORD000004 huỷ -> ngoài
        ("Doanh thu của Bánh mì ngon tháng 6/2026 là bao nhiêu?", A, "number", 60000),
        ("Doanh thu tháng 6/2026 là bao nhiêu?", A, "number", 160000),
        # most orders: Chị Lan 3 (ORD1, ORD3, ORD6) vs Anh Hùng 2
        ("Tháng 6/2026 khách nào mua nhiều đơn nhất?", A, "string", "Chị Lan"),
        # items in >= 2 valid orders: Cà phê sữa (ORD2, ORD3, ORD5), Bánh mì ngon (ORD1, ORD6)
        ("Tháng 6/2026 có bao nhiêu mặt hàng có mặt trong ít nhất 3 đơn?", A, "number", 1),
        ("Tháng 6/2026 có mấy món xuất hiện trong từ 2 đơn trở lên?", A, "number", 2),
    ],
}]
