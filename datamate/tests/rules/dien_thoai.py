"""Rulebook §6 'Cửa hàng điện thoại' (and §1 for the order rules): a hand-kept
phone book with a 'Ghi tắt' sheet (abbreviation -> full name, kind) and one
sheet per month. The README documents no columns, so the order number must be
read from the repeated STT values.

June 2026, valid orders (STT5 'khách trả lại' is out):
  STT1 IP15 1x18.000.000 + Ốp trong 80.000; bớt 80.000; thu máy cũ 3.000.000 -> KT 15.000.000
  STT2 Sạc 20W 2x250.000                                                      -> KT    500.000
  STT3 A56 1x9.000.000 + Giá đỡ 100.000; bớt 100.000                          -> KT  9.000.000
  STT4 IP13 cũ 1x10.000.000; thu máy cũ 2.000.000                              -> KT  8.000.000
  STT6 Nokia 105 3x700.000 + Ốp trong 80.000                                  -> KT  2.180.000
  STT7 IP13 cũ 1x10.000.000 + Sạc 20W 250.000; bớt 50.000                     -> KT 10.200.000
  revenue (lines, order discount not taken off) = 50.110.000; KT = 44.880.000
  phones: IP15 1, A56 1, IP13 cũ 2, Nokia 3 = 7 (máy mới 5, máy cũ 2)
  phone revenue 49.100.000, of which máy mới 29.100.000
"""

README = """# Dữ liệu rule_test

Cửa hàng điện thoại tự ghi sổ bán hàng trên Excel: sheet `Ghi tắt` và mỗi tháng một sheet.

## File
- `SoBanHang.xlsx` (xlsx)

## Quy ước
- Dữ liệu có đến hết 31/07/2026.
- **Đơn**: các dòng cùng **STT** là một đơn; khách, bớt, khách trả, ghi chú của đơn lặp lại ở mọi dòng của đơn.
- **Đơn khách trả lại**: **Ghi chú** của đơn ghi khách trả lại.
- **Tiền khách trả**: **Khách trả** là số tiền khách trả cho cả đơn, đã bớt và đã trừ tiền thu máy cũ.
- **Ghi tắt, loại hàng**: sheet `Ghi tắt` cho tên đầy đủ và loại hàng (máy mới, máy cũ, phụ kiện) của từng cách ghi tắt.
"""

GHI_TAT = [["Ghi tắt", "Tên hàng", "Loại"],
           ["IP15 128 đen", "iPhone 15 128GB Đen", "máy mới"],
           ["IP13 128 cũ", "iPhone 13 128GB cũ 98%", "máy cũ"],
           ["A56 128 đen", "Samsung Galaxy A56 5G 128GB Đen", "máy mới"],
           ["Nokia 105", "Nokia 105 4G", "máy mới"],
           ["Sạc 20W", "Củ sạc nhanh 20W Type-C", "phụ kiện"],
           ["Ốp trong", "Ốp lưng trong suốt", "phụ kiện"],
           ["Giá đỡ", "Giá đỡ điện thoại để bàn", "phụ kiện"]]

H = ["Ngày", "STT", "Khách", "Hàng", "IMEI", "SL", "Giá", "Thành tiền", "Bớt", "Thu máy cũ", "Khách trả", "Ghi chú"]
T6 = [H,
      ["01/06/2026", 1, "Anh Nam 0901111111", "IP15 128 đen", "351111111111111", 1, "18tr", "18.000.000đ", "80k", "3tr", "15tr", None],
      ["01/06/2026", 1, "Anh Nam 0901111111", "Ốp trong", None, 1, "80k", "80.000đ", "80k", "3tr", "15tr", None],
      ["02/06/2026", 2, "lẻ", "Sạc 20W", None, 2, "250k", "500.000đ", None, None, "500k", None],
      ["03/06/2026", 3, "Chị Mai 0902222222", "A56 128 đen", "352222222222222", 1, "9tr", "9.000.000đ", "100k", None, "9tr", None],
      ["03/06/2026", 3, "Chị Mai 0902222222", "Giá đỡ", None, 1, "100k", "100.000đ", "100k", None, "9tr", None],
      ["05/06/2026", 4, "Anh Bình 0903333333", "IP13 128 cũ", "353333333333333", 1, "10tr", "10.000.000đ", None, "2tr", "8tr", None],
      ["06/06/2026", 5, "Chị Lan 0904444444", "IP15 128 đen", "354444444444444", 1, "18tr", "18.000.000đ", None, None, "18tr",
       "khách trả lại"],
      ["08/06/2026", 6, "lẻ", "Nokia 105", None, 3, "700k", "2.100.000đ", None, None, "2,18tr", None],
      ["08/06/2026", 6, "lẻ", "Ốp trong", None, 1, "80k", "80.000đ", None, None, "2,18tr", None],
      ["10/06/2026", 7, "Anh Tùng 0905555555", "IP13 128 cũ", "355555555555555", 1, "10tr", "10.000.000đ", "50k", None,
       "10,2tr", None],
      ["10/06/2026", 7, "Anh Tùng 0905555555", "Sạc 20W", None, 1, "250k", "250.000đ", "50k", None, "10,2tr", None]]
T7 = [H,
      ["01/07/2026", 8, "lẻ", "Ốp trong", None, 3, "80k", "240.000đ", None, None, "240k", None],
      ["02/07/2026", 9, "Anh Nam 0901111111", "A56 128 đen", "356666666666666 / 357777777777777", 2, "9tr", "18.000.000đ",
       "200k", None, "17,8tr", None],
      ["03/07/2026", 10, "lẻ", "Sạc 20W", None, 1, "250k", "250.000đ", None, None, "250k", None]]

README2 = """# Dữ liệu rule_test

Sổ bán hàng của cửa hàng điện thoại, chủ tiệm tự ghi trên Excel: sheet `Ghi tắt` (cách ghi tắt tên hàng và loại hàng) và sheet `Sổ bán hàng` cả kỳ, mỗi dòng một mặt hàng của một đơn.

## File
- `SoBanHang.xlsx` (xlsx)

## Cột trong `SoBanHang.xlsx`
- **Ngày**: ngày bán
- **STT**: số thứ tự đơn (hoá đơn) trong sổ
- **Khách**: tên khách (khách không lưu: khách lẻ)
- **Hàng**: hàng bán, có thể ghi tắt (tra ở sheet Ghi tắt)
- **IMEI**: IMEI của máy bán (máy mới, máy cũ); phụ kiện để trống
- **SL**: số lượng
- **Giá**: đơn giá một máy / một cái
- **Thành tiền**: thành tiền của dòng
- **Bớt**: tiền bớt cho cả đơn (trống: không bớt)
- **Thu máy cũ**: tiền thu máy cũ của khách, trừ vào tiền đơn (trống: không thu máy)
- **Khách trả**: số tiền khách trả cho cả đơn, đã trừ bớt và thu máy cũ
- **Ghi chú**: ghi chú của đơn; đơn khách trả lại hàng ghi ở đây

## Quy ước
- Dữ liệu có đến hết 31/05/2026.
- **Đơn khách trả lại**: **Ghi chú** của đơn ghi khách trả lại.
- **Ghi tắt, loại hàng**: sheet `Ghi tắt` cho tên đầy đủ và loại hàng (máy mới, máy cũ, phụ kiện) của từng cách ghi tắt.
"""

GHI_TAT2 = GHI_TAT + [["RN14 128 đen", "Xiaomi Redmi Note 14 128GB Đen", "máy mới"],
                      ["IP15 256 đen", "iPhone 15 256GB Đen", "máy mới"]]

# May 2026; S5 'khách mang trả' is out. Later lines of an order leave STT,
# date and customer blank.
#   S1 IP15 256 21tr + Sạc 20W 250k; bớt 250k; thu 5tr -> KT 16tr
#   S2 RN14 5tr; thu 1tr -> KT 4tr          S3 Ốp trong 2x80k -> KT 160k
#   S4 IP13 cũ 10tr + Giá đỡ 100k; bớt 100k -> KT 10tr
#   S6 RN14 2x5tr -> KT 10tr                S7 Nokia 700k + Ốp trong 80k -> KT 780k
#   S8 IP15 128 18tr; thu 4tr -> KT 14tr
#   revenue 65.290.000; KT 54.940.000 over 7 orders; trade-in 10tr in 3 orders
#   phones 7 (RN14 3, iPhone 15 2, IP13 cũ 1, Nokia 1); phone revenue 64.700.000,
#   máy mới 54.700.000; phụ kiện 590.000
SO = [H,
      ["02/05/2026", 1, "lẻ", "IP15 256 đen", "358888888888888", 1, "21tr", "21.000.000", "250k", "5tr", "16tr", None],
      [None, None, None, "Sạc 20W", None, 1, "250k", "250.000", None, None, None, None],
      ["03/05/2026", 2, "Chị Hoa 0906666666", "RN14 128 đen", "359999999999999", 1, "5tr", "5.000.000", None, "1tr", "4tr", None],
      ["04/05/2026", 3, "lẻ", "Ốp trong", None, 2, "80k", "160.000", None, None, "160k", None],
      ["06/05/2026", 4, "Anh Long 0907777777", "IP13 128 cũ", "350000000000001", 1, "10tr", "10.000.000", "100k", None, "10tr", None],
      [None, None, None, "Giá đỡ", None, 1, "100k", "100.000", None, None, None, None],
      ["07/05/2026", 5, "lẻ", "RN14 128 đen", "350000000000002", 1, "5tr", "5.000.000", None, None, "5tr", "khách mang trả"],
      ["09/05/2026", 6, "Chị Hoa 0906666666", "RN14 128 đen", "350000000000003 / 350000000000004", 2, "5tr", "10.000.000",
       None, None, "10tr", None],
      ["12/05/2026", 7, "lẻ", "Nokia 105", None, 1, "700k", "700.000", None, None, "780k", None],
      [None, None, None, "Ốp trong", None, 1, "80k", "80.000", None, None, None, None],
      ["15/05/2026", 8, "Anh Long 0907777777", "IP15 128 đen", "350000000000005", 1, "18tr", "18.000.000", None, "4tr", "14tr",
       None]]

A2 = "2026-05-31"
A = "2026-07-31"

# side books for the June/July sales book above (README3)
#   sổ nợ: N1 03/06 Chị Mai nợ 4tr, trả 1tr 10/06 và 1tr 20/06 (STT 3); N2 10/06 Anh Tùng nợ 2,2tr (STT 7)
#   sổ góp: G1 01/06 Anh Nam (STT 1) giá 15tr, trước 6tr, 3 kỳ x 3tr, hạn ngày 5 -> 05/07, 05/08, 05/09;
#           góp 3tr 04/07, 3tr 10/08
#           G2 05/06 Anh Bình (STT 4) giá 8tr, trước 2tr, 2 kỳ x 3tr, hạn ngày 20 -> 20/07, 20/08; góp 3tr 20/07
#   bảo hành: 15/06 iPhone 15 (3511..), 20/06 iPhone 13 (3533..), 25/06 iPhone 15 (3511..),
#             05/07 iPhone 15 (3544.., the returned STT5 phone), 10/07 Samsung Galaxy A56 5G (3566.., July STT9)
README3 = README.replace("## File\n- `SoBanHang.xlsx` (xlsx)",
                         "## File\n- `SoBanHang.xlsx` (xlsx)\n- `SoNo.xlsx` (xlsx)") + \
    "- **Sổ nợ**: chỉ đơn khách còn nợ sau lúc mua, trừ đơn trả góp. **Nợ** là số còn nợ sau khi trả lúc mua. " \
    "Các lần khách trả sau đó ghi ở **Đã trả**, **Ngày trả**.\n" \
    "- **Sổ góp**: mỗi đơn trả góp có dòng đầu ghi ngày mua, khách, **Giá**, **Trả trước**, **Số kỳ**, " \
    "**Góp/tháng**. Kỳ thứ nhất có hạn vào ngày **Hạn góp (ngày)** của tháng ngay sau tháng mua.\n" \
    "- **Sổ bảo hành**: mỗi lần khách mang máy tới bảo hành một dòng (**Ngày nhận**).\n"
SO_NO = {
    "Sổ nợ": [["Ngày", "Khách", "SĐT", "Nợ", "Đã trả", "Ngày trả", "Ghi chú"],
              ["03/06/2026", "Chị Mai", "0902222222", "4tr", "1tr", "10/06/2026", "STT 3"],
              [None, None, None, None, "1.000.000đ", "20/06/2026", "STT 3"],
              ["10/06/2026", "Anh Tùng", "0905555555", "2,2tr", None, None, "STT 7"]],
    "Trả góp": [["Ngày", "STT", "Khách", "SĐT", "Máy", "Giá", "Trả trước", "Số kỳ", "Góp/tháng", "Hạn góp (ngày)",
                 "Ngày góp", "Đã góp"],
                ["01/06/2026", 1, "Anh Nam", "0901111111", "iPhone 15 128GB Đen", "15tr", "6tr", 3, "3tr", 5,
                 "04/07/2026", "3tr"],
                [None, 1, None, None, None, None, None, None, None, None, "10/08/2026", "3.000.000đ"],
                ["05/06/2026", 4, "Anh Bình", "0903333333", "iPhone 13 128GB cũ 98%", "8tr", "2tr", 2, "3tr", 20,
                 "20/07/2026", "3tr"]],
    "Bảo hành": [["Ngày nhận", "Khách", "SĐT", "Máy", "IMEI", "Ngày mua", "Lỗi", "Xử lý"],
                 ["15/06/2026", "Anh Nam", "0901111111", "iPhone 15", "351111111111111", "01/06/2026", "pin", "sửa"],
                 ["20/06/2026", "Anh Bình", "0903333333", "iPhone 13", "353333333333333", "05/06/2026", "loa", "sửa"],
                 ["25/06/2026", "Anh Nam", "0901111111", "iPhone 15", "351111111111111", "01/06/2026", "pin", "đổi"],
                 ["05/07/2026", "Chị Lan", "0904444444", "iPhone 15", "354444444444444", "06/06/2026", "màn", "sửa"],
                 ["10/07/2026", "Anh Nam", "0901111111", "Samsung Galaxy A56 5G", "356666666666666", "02/07/2026",
                  "sạc", "sửa"]],
}

CASES = [{
    "name": "sổ bán điện thoại: máy, khách phải trả, thu máy cũ",
    "readme": README,
    "files": {"SoBanHang.xlsx": {"Ghi tắt": GHI_TAT, "T6-2026": T6, "T7-2026": T7}},
    "questions": [
        # §1 on the book itself: lines of one STT are one order, STT5 returned
        ("Doanh thu tháng 6/2026 là bao nhiêu?", A, "number", 50110000),
        ("Tháng 6/2026 tiệm bán được bao nhiêu đơn?", A, "number", 6),
        # khách phải trả = Khách trả of valid orders
        ("Tháng 6/2026 tổng tiền khách phải trả là bao nhiêu?", A, "number", 44880000),
        ("Đơn bán 6/2026, trừ tiền bớt với tiền máy cũ thu lại rồi, khách phải trả tổng cộng bao nhiêu?", A, "number", 44880000),
        ("Tháng 7/2026 khách phải trả tổng cộng bao nhiêu?", A, "number", 18290000),
        ("6-2026 trung bình mỗi đơn khách phải trả bao nhiêu, đã trừ bớt và máy cũ?", A, "number", 7480000),
        # trade-ins
        ("Tổng tiền thu máy cũ của khách tháng 6/2026 là bao nhiêu?", A, "number", 5000000),
        ("Tháng 6/2026 bao nhiêu % đơn có thu máy cũ của khách?", A, "percent", 33.33),
        # phones sold
        ("Tháng 6/2026 bán được bao nhiêu máy không tính phụ kiện?", A, "number", 7),
        ("Th6/2026 bán ra mấy chiếc điện thoại cũ?", A, "number", 2),
        ("Máy mới tháng 6/2026 bán được mấy chiếc?", A, "number", 5),
        ("iPhone 13 tháng 6/2026 bán được mấy chiếc?", A, "number", 2),
        ("Tháng 7/2026 bán được bao nhiêu chiếc Samsung Galaxy A56 5G?", A, "number", 2),
        ("Tháng 6/2026 Ốp lưng trong suốt bán được bao nhiêu cái?", A, "number", 2),
        # dòng máy, hãng, shares, averages
        ("Tháng 6/2026, 2 dòng máy nào bán được nhiều máy nhất, xếp từ nhiều đến ít?", A, "list",
         ["Nokia 105 4G", "iPhone 13"]),
        ("Tháng 6/2026 máy Samsung chiếm bao nhiêu % tổng số máy bán ra?", A, "percent", 14.29),
        ("Tháng 6/2026 máy mới chiếm mấy % tiền bán máy?", A, "percent", 59.27),
        ("Tháng 6/2026 không tính phụ kiện, trung bình 1 máy bán được bao nhiêu tiền?", A, "number", 7014286),
        # kinds as item groups
        ("Tháng 6/2026 nhóm phụ kiện bán được bao nhiêu tiền?", A, "number", 1010000),
        ("Tháng 6/2026 nhóm máy mới bán được bao nhiêu tiền?", A, "number", 29100000),
        ("Tháng 6/2026 trong nhóm máy mới, mặt hàng nào bán được nhiều máy nhất?", A, "string", "Nokia 105 4G"),
        # an item named with a synonym of its first word
        ("Tháng 6/2026 bán Cốc sạc nhanh 20W Type-C được bao nhiêu tiền?", A, "number", 750000),
        ("Tháng 6/2026 tiệm bán Kệ điện thoại để bàn được bao nhiêu tiền?", A, "number", 100000),
    ],
}, {
    "name": "sổ bán điện thoại một sheet, dòng sau của đơn để trống STT",
    "readme": README2,
    "files": {"SoBanHang.xlsx": {"Ghi tắt": GHI_TAT2, "Sổ bán hàng": SO}},
    "questions": [
        ("Doanh thu tháng 5/2026 là bao nhiêu?", A2, "number", 65290000),
        ("Tháng 5/2026 có bao nhiêu đơn?", A2, "number", 7),
        ("Khách phải trả hết bao nhiêu tiền trong 5-2026 vậy?", A2, "number", 54940000),
        ("05/2026 tính tiền khách phải trả sau khi trừ bớt và tiền máy cũ thu lại, bình quân một đơn là mấy đồng?", A2,
         "number", 7848571),
        ("Tháng này mỗi đơn khách phải trả trung bình bao nhiêu?", A2, "number", 7848571),
        ("Tháng 5/2026 tiền thu máy cũ đã trừ vào các đơn cộng lại được bao nhiêu?", A2, "number", 10000000),
        ("5-2026 cộng tiền thu máy cũ của khách được bao nhiêu?", A2, "number", 10000000),
        ("Đơn có thu lại máy cũ 5-2026 chiếm mấy % tổng đơn?", A2, "percent", 42.86),
        ("Tháng này bao nhiêu % đơn hàng có thu máy cũ của khách?", A2, "percent", 42.86),
        ("Tháng 5/2026 bán được mấy chiếc điện thoại, gộp cả máy mới với máy cũ?", A2, "number", 7),
        ("Điện thoại cũ tháng 5/2026 bán ra mấy máy?", A2, "number", 1),
        ("Xiaomi Redmi Note 14 tháng này bán được bao nhiêu chiếc?", A2, "number", 3),
        ("Tháng 5/2026 bán được mấy chiếc iPhone 15?", A2, "number", 2),
        ("Tháng 5/2026 Ốp lưng trong suốt bán ra tổng cộng bao nhiêu cái?", A2, "number", 3),
        ("Tháng 5/2026 Củ sạc nhanh 20W Type-C bán ra mấy cái?", A2, "number", 1),
        ("Top 2 dòng máy bán nhiều máy nhất tháng 5/2026, xếp từ cao xuống thấp?", A2, "list",
         ["Xiaomi Redmi Note 14", "iPhone 15"]),
        ("Quý 2/2026, 2 dòng máy nào bán được nhiều máy nhất, xếp từ nhiều đến ít?", A2, "list",
         ["Xiaomi Redmi Note 14", "iPhone 15"]),
        ("T5/2026 máy Xiaomi chiếm bao nhiêu % tổng số máy bán ra?", A2, "percent", 42.86),
        ("Tháng 5/2026 máy Apple chiếm bao nhiêu % số máy bán ra?", A2, "percent", 42.86),
        ("Th5/2026 máy mới chiếm mấy % tiền bán máy?", A2, "percent", 84.54),
        ("Bỏ phụ kiện ra thì doanh thu máy mới tháng này chiếm bao nhiêu % tổng doanh thu máy?", A2, "percent", 84.54),
        ("Tháng này không tính phụ kiện, trung bình 1 máy bán được bao nhiêu tiền?", A2, "number", 9242857),
        ("5-2026 tiệm bán điện thoại, tính cả máy mới lẫn máy cũ, trung bình mỗi máy giá bao nhiêu?", A2, "number", 9242857),
        ("Nhóm phụ kiện 5/2026 bán được bao nhiêu tiền?", A2, "number", 590000),
        ("05/2026 nhóm máy cũ bán được bao nhiêu tiền?", A2, "number", 10000000),
        ("Tháng 5/2026 trong nhóm máy mới, mặt hàng nào bán được nhiều máy nhất?", A2, "string",
         "Xiaomi Redmi Note 14 128GB Đen"),
        ("Tháng 5/2026 trong nhóm máy cũ, mặt hàng nào bán được nhiều máy nhất?", A2, "string", "iPhone 13 128GB cũ 98%"),
        ("Tháng 5/2026 bán Cốc sạc nhanh 20W Type-C được bao nhiêu tiền?", A2, "number", 250000),
        ("Tháng 5/2026 tiệm bán Kệ điện thoại để bàn được bao nhiêu tiền?", A2, "number", 100000),
    ],
}, {
    "name": "sổ nợ, sổ góp, sổ bảo hành của tiệm điện thoại",
    "readme": README3,
    "files": {"SoBanHang.xlsx": {"Ghi tắt": GHI_TAT, "T6-2026": T6, "T7-2026": T7}, "SoNo.xlsx": SO_NO},
    "questions": [
        # instalments left, not-yet-due ones included
        ("Đến hết ngày 31/07/2026, các hợp đồng trả góp còn lại bao nhiêu tiền chưa góp, tính cả kỳ chưa tới hạn?", A,
         "number", 9000000),
        ("Hết ngày 30/06/2026, tổng số tiền góp khách chưa trả, kể cả các kỳ chưa tới hạn, là bao nhiêu?", A,
         "number", 15000000),
        ("Tính tới hôm nay, tiền trả góp khách còn chưa góp là bao nhiêu, tính cả kỳ chưa tới hạn?", "2026-08-15",
         "number", 6000000),
        ("Đến hết hôm nay, khách Anh Nam còn thiếu bao nhiêu tiền góp, tính cả kỳ chưa tới hạn?", "2026-08-15",
         "number", 3000000),
        ("Tới hôm nay, khoản trả góp của khách Anh Bình còn lại bao nhiêu tiền chưa góp, kể cả kỳ chưa tới hạn?", A,
         "number", 3000000),
        ("Đến hết hôm nay, khách Anh Bình còn thiếu bao nhiêu tiền góp, tính cả kỳ chưa tới hạn?", "2026-07-10",
         "number", 6000000),
        # instalments due so far, the asked day included
        ("Hết hôm nay, khách Anh Nam góp tới hạn mấy kỳ rồi, tính luôn kỳ hạn hôm nay?", "2026-08-05", "number", 2),
        ("Tới hôm nay khách Anh Nam tới hạn mấy kỳ góp rồi, tính cả kỳ hạn đúng hôm nay?", "2026-07-04", "number", 0),
        ("Tới hôm nay khách Anh Bình tới hạn mấy kỳ góp rồi, tính cả kỳ hạn đúng hôm nay?", "2026-07-20", "number", 1),
        # overdue: due strictly before the asked day and not fully paid
        ("Tính tới hôm nay, tiền góp quá hạn khách chưa trả là bao nhiêu?", "2026-08-21", "number", 3000000),
        ("Đến hết ngày 07/08/2026, khách còn chưa đóng bao nhiêu tiền thuộc các kỳ góp đã quá hạn?", "2026-08-31",
         "number", 3000000),
        ("Hết ngày 05/08/2026 tiền chậm góp của khách trả góp tổng cộng bao nhiêu?", "2026-08-31", "number", 0),
        ("Tại ngày 21/08/2026 có bao nhiêu khách quá hạn góp?", "2026-08-31", "number", 1),
        ("Đến ngày 07/08/2026 có mấy khách trả góp còn nợ kỳ góp quá hạn?", "2026-08-31", "number", 1),
        ("Hết ngày 05/08/2026 shop có mấy người trả góp còn kỳ quá hạn chưa đóng?", "2026-08-31", "number", 0),
        # debts: both books
        ("Tính tới hết ngày 30/06/2026 tổng tiền khách còn nợ shop là bao nhiêu?", A, "number", 19200000),
        ("Đến hết hôm nay tiền khách còn nợ tổng cộng bao nhiêu?", "2026-06-15", "number", 20200000),
        ("Tổng tiền khách còn nợ đến hết hôm nay là bao nhiêu?", "2026-06-04", "number", 13000000),
        ("Tại ngày 30/06/2026 tiệm còn mấy khách có công nợ?", A, "number", 4),
        ("Đến hết hôm nay tiệm còn bao nhiêu khách có công nợ?", "2026-06-04", "number", 2),
        ("Hết hôm nay có mấy khách còn nợ tiệm?", "2026-06-08", "number", 3),
        # warranty
        ("Tháng 6/2026 tiệm nhận bảo hành bao nhiêu lượt máy?", A, "number", 3),
        ("Quý 3/2026 có mấy lượt khách đem máy tới bảo hành?", A, "number", 2),
        ("Tháng 7/2026 có bao nhiêu lượt bảo hành?", A, "number", 2),
        ("Tháng 6/2026 lượt bảo hành so với số máy bán được chiếm bao nhiêu %?", A, "percent", 42.86),
        ("Quý 3/2026 tỉ lệ bảo hành là bao nhiêu %?", A, "percent", 100.0),
        ("Tháng 7/2026 tỉ lệ bảo hành bao nhiêu phần trăm?", A, "percent", 100.0),
        ("Tháng 6/2026 dòng máy nào có nhiều lượt bảo hành nhất?", A, "string", "iPhone 15"),
        ("Quý 2/2026 dòng máy nào nhiều lượt bảo hành nhất?", A, "string", "iPhone 15"),
        ("Trong tháng 6/2026, dòng máy nào được mang tới bảo hành nhiều lượt nhất?", A, "string", "iPhone 15"),
        ("Máy bán ra tháng 6/2026, tới hôm nay có bao nhiêu máy đã mang lại bảo hành rồi?", A, "number", 2),
        ("Tính đến hôm nay, bao nhiêu máy bán tháng 7/2026 đã được mang tới bảo hành ít nhất một lần?", A, "number", 1),
        ("Máy bán ra tháng 6/2026, tới hôm nay có bao nhiêu máy đã mang lại bảo hành?", "2026-06-30", "number", 2),
    ],
}]
