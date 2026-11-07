"""Rulebook public §6 Sửa xe. All data invented, every answer computed by hand.

Staff: Hà Văn Đạt 30 %, Lê Minh Phúc 20 %, Trần Thị An 25 %.
 #  date          bike                    jobs                       mech     amount  note
 1  04/05 (Mon)   Air Blade 59A1-111.11   bảo dưỡng, vá xe           a Đạt    200000
 2  05/05 (Tue)   AB 59A1-111.11          thay nhớt                  Đạt      100000
 3  05/05 (Tue)   Vision 59B2-222.22      sửa điện, thay bóng đèn    A.Phúc   150000
 4  06/05 (Wed)   vision 110 59B2-222.22  bảo hành                   Phúc          0  bảo hành
 5  12/05 (Tue)   Wave Alpha 59C3-333.33  nhớt láp, ruột             An       120000
 6  13/05 (Wed)   Alpha 59C3-333.33       vá ruột                    a An      30000
 7  20/05 (Wed)   Lead 59D4-444.44        làm điện                   Đạt       80000
 8  20/05 (Wed)   Air Blade 59E5-555.55   rửa xe                     Phúc      50000
 9  01/06 (Mon)   AB 59A1-111.11          bảo hành                   Đạt           0  bảo hành, phiếu 4/5
10  02/06 (Tue)   Lead 59D4-444.44        thay nhớt, nhớt hộp số     An       180000
11  03/06 (Wed)   Lead 59D4-444.44        bóng đèn                   An        40000
12  03/06 (Wed)   Vision 59F6-666.66      sửa điện                   Phúc      90000
Model groups come from shared plates: AB = Air Blade, Vision = vision 110,
Alpha = Wave Alpha.
"""

README = """# Dữ liệu rule_test

Sổ sửa xe chủ tiệm tự ghi trên Excel, mỗi tháng một sheet: mỗi dòng một lượt xe vào sửa (một phiếu), không ghi mã phiếu, không ghi tên khách. Ô Làm gì ghi mọi việc của phiếu. Tiền là tổng cả phiếu. File DanhSachTho.xlsx ghi họ tên, phần trăm hoa hồng các thợ; sổ ghi thợ theo tên gọi. Phiếu ghi chú bảo hành, Tiền 0: xe quay lại bảo hành.

## File
- `SoSuaXe.xlsx` (xlsx)
- `DanhSachTho.xlsx` (xlsx)

## Cột trong `SoSuaXe.xlsx`
- **Ngày**: ngày sửa
- **Xe**: dòng xe và biển số ghi chung một ô
- **Làm gì**: các việc đã làm cho xe, nhiều việc ghi chung một ô
- **Thợ**: thợ làm phiếu, ghi tên gọi
- **Tiền**: tổng tiền cả phiếu
- **Ghi chú**: ghi chú

## Cột trong `DanhSachTho.xlsx`
- **Họ tên**: họ tên thợ
- **Hoa hồng (%)**: phần trăm hoa hồng của thợ, tính trên tổng Tiền các phiếu thợ làm trong tháng

## Quy ước
- Dữ liệu có đến hết 30/06/2026.
"""

H = ["Ngày", "Xe", "Làm gì", "Thợ", "Tiền", "Ghi chú"]
N = None
MAY = [H,
       ["04/05/2026", "Air Blade 59A1-111.11", "bảo dưỡng, vá xe", "a Đạt", 200000, N],
       ["05/05/2026", "AB 59A1-111.11", "thay nhớt", "Đạt", "100.000đ", N],
       ["05/05/2026", "Vision 59B2-222.22", "sửa điện, thay bóng đèn", "A.Phúc", 150000, N],
       ["06/05/2026", "vision 110 59B2-222.22", "bảo hành", "Phúc", 0, "bảo hành"],
       ["12/05/2026", "Wave Alpha 59C3-333.33", "nhớt láp, ruột", "An", 120000, N],
       ["13/05/2026", "Alpha 59C3-333.33", "vá ruột", "a An", 30000, N],
       ["20/05/2026", "Lead 59D4-444.44", "làm điện", "Đạt", 80000, N],
       ["20/05/2026", "Air Blade 59E5-555.55", "rửa xe", "Phúc", 50000, N]]
JUN = [H,
       ["01/06/2026", "AB 59A1-111.11", "bảo hành", "Đạt", 0, "bảo hành, phiếu 4/5"],
       ["02/06/2026", "Lead 59D4-444.44", "thay nhớt + nhớt hộp số", "An", 180000, N],
       ["03/06/2026", "Lead 59D4-444.44", "bóng đèn", "An", 40000, N],
       ["03/06/2026", "Vision 59F6-666.66", "sửa điện", "Phúc", 90000, N]]
STAFF = [["Họ tên", "Hoa hồng (%)"], ["Hà Văn Đạt", 30], ["Lê Minh Phúc", 20], ["Trần Thị An", 25]]

A = "2026-06-30"
T_MAY = {"columns": ["tho", "hoa_hong"],
         "rows": [["Hà Văn Đạt", 114000], ["Lê Minh Phúc", 40000], ["Trần Thị An", 37500]]}
T_JUN = {"columns": ["tho", "hoa_hong"],
         "rows": [["Trần Thị An", 55000], ["Lê Minh Phúc", 18000], ["Hà Văn Đạt", 0]]}
T_YTD = {"columns": ["tho", "hoa_hong"],
         "rows": [["Hà Văn Đạt", 114000], ["Trần Thị An", 92500], ["Lê Minh Phúc", 58000]]}

CASES = [{
    "name": "sổ sửa xe: phiếu, lượt, bảo hành, việc, dòng xe, thợ, hoa hồng",
    "readme": README,
    "files": {"SoSuaXe.xlsx": {"T5-2026": MAY, "T6-2026": JUN},
              "DanhSachTho.xlsx": {"Sheet1": STAFF}},
    "questions": [
        # số phiếu (gồm phiếu bảo hành)
        ("Tháng 5/2026 tiệm có bao nhiêu phiếu sửa xe?", A, "number", 8),
        ("Th6/2026 tiệm lên mấy phiếu?", A, "number", 4),
        ("Từ đầu năm tới nay tiệm được bao nhiêu phiếu sửa?", A, "number", 12),
        # bình quân một phiếu có thu tiền
        ("Tháng 5/2026 bình quân một phiếu có thu tiền là bao nhiêu?", A, "number", 104286),
        ("Th6/2026 không tính phiếu bảo hành, trung bình 1 phiếu bao nhiêu tiền?", A, "number", 103333),
        ("Từ đầu năm tới nay trung bình mỗi phiếu thu bao nhiêu tiền?", A, "number", 104000),
        # bảo hành
        ("Tháng 5/2026 có bao nhiêu phiếu bảo hành?", A, "number", 1),
        ("Th6/2026 bao nhiêu lượt xe quay lại bảo hành?", A, "number", 1),
        ("Từ đầu năm tới nay tiệm nhận mấy phiếu bảo hành?", A, "number", 2),
        ("Tháng 5/2026 phiếu bảo hành chiếm bao nhiêu % số phiếu thu tiền?", A, "percent", 14.29),
        ("Tỉ lệ bảo hành tháng 6/2026 là bao nhiêu %?", A, "percent", 33.33),
        ("Từ đầu năm tới nay tỉ lệ bảo hành bao nhiêu phần trăm?", A, "percent", 20.0),
        # lượt theo việc (bỏ phiếu bảo hành)
        ("Tháng 5/2026 có bao nhiêu lượt xe sửa điện?", A, "number", 2),
        ("Tháng 5/2026 bao nhiêu phiếu có vá ruột xe?", A, "number", 2),
        ("Tháng 6/2026 tiệm thay dầu láp cho bao nhiêu lượt xe?", A, "number", 1),
        ("Tháng 5/2026 có mấy lượt thay ruột?", A, "number", 1),
        # số chiếc xe theo dòng (biển số khác nhau, gồm xe chỉ tới bảo hành)
        ("Tháng 5/2026 có bao nhiêu chiếc Air Blade khác nhau vào tiệm?", A, "number", 2),
        ("Tháng 5/2026 bao nhiêu xe Vision khác nhau tới sửa, mỗi xe tính một lần?", A, "number", 1),
        ("Th6/2026 có mấy chiếc AB khác nhau vô tiệm?", A, "number", 1),
        # xe khách quen: >= 2 phiếu có thu tiền
        ("Tháng 5/2026 có bao nhiêu xe khách quen?", A, "number", 2),
        ("Tháng 6/2026 có mấy chiếc xe vô sửa từ 2 lần trở lên?", A, "number", 1),
        ("Từ đầu năm tới nay có bao nhiêu xe khách quen?", A, "number", 3),
        # dòng xe nhiều tiền nhất
        ("Tháng 5/2026 dòng xe nào đem lại nhiều tiền sửa nhất?", A, "string", "Air Blade"),
        ("Th6/2026 dòng xe mô mang về nhiều tiền nhất?", A, "string", "Lead"),
        ("Từ đầu năm tới nay dòng xe nào cho doanh thu cao nhất?", A, "string", "Air Blade"),
        # thợ
        ("Tháng 5/2026 thợ Lê Minh Phúc làm được bao nhiêu lượt xe?", A, "number", 3),
        ("Tháng 5/2026 thợ Tran Thi An sửa được mấy phiếu?", A, "number", 2),
        ("Th6/2026 thợ Hà Văn Đạt làm bao nhiêu lượt xe?", A, "number", 1),
        ("Tháng 5/2026 thợ Lê Minh Phúc làm ra bao nhiêu tiền?", A, "number", 200000),
        ("Tháng 6/2026 tiền các phiếu thợ Trần Thị An làm cộng lại bao nhiêu?", A, "number", 220000),
        ("Tháng 5/2026 thợ Ha Van Dat lam duoc tong bao nhieu tien?", A, "number", 380000),
        ("Th6/2026 thợ nào làm nhiều lượt xe nhất?", A, "string", "Trần Thị An"),
        ("Tháng 5/2026 thợ nào nhận nhiều phiếu nhất?", A, "string", "Hà Văn Đạt"),
        ("Từ đầu năm tới nay thợ mô làm nhiều lượt xe nhất?", A, "string", "Hà Văn Đạt"),
        ("Tháng 6/2026 ai là thợ chăm chỉ nhất?", A, "string", "Trần Thị An"),
        ("Tháng 5/2026 ai là thợ chăm chỉ nhất?", A, "string", "Hà Văn Đạt"),
        ("Từ đầu năm tới nay ai là thợ siêng năng nhất?", A, "string", "Hà Văn Đạt"),
        ("Tháng 5/2026 thợ nào làm ra nhiều tiền nhất?", A, "string", "Hà Văn Đạt"),
        ("Th6/2026 thợ mô làm ra doanh thu cao nhất?", A, "string", "Trần Thị An"),
        ("Từ đầu năm tới nay thợ nào làm ra nhiều tiền nhất?", A, "string", "Hà Văn Đạt"),
        # hoa hồng
        ("Tháng 5/2026 thợ Lê Minh Phúc lãnh bao nhiêu tiền hoa hồng?", A, "number", 40000),
        ("Tháng 5/2026 thợ Trần Thị An được bao nhiêu hoa hồng?", A, "number", 37500),
        ("Th6/2026 hoa hồng của thợ Hà Văn Đạt là bao nhiêu?", A, "number", 0),
        ("Bảng hoa hồng thợ tháng 5/2026, ai nhiều tiền xếp trên", A, "table", T_MAY),
        ("Hoa hồng từng thợ th6/2026, cho bảng xếp giảm dần", A, "table", T_JUN),
        ("Bảng hoa hồng các thợ từ đầu năm tới nay", A, "table", T_YTD),
        ("Tháng 5/2026 thợ nào hoa hồng cao nhất?", A, "string", "Hà Văn Đạt"),
        ("Th6/2026 thợ mô hoa hồng cao nhất?", A, "string", "Trần Thị An"),
        ("Từ đầu năm tới nay thợ nào được hoa hồng nhiều nhất?", A, "string", "Hà Văn Đạt"),
        # trung bình mỗi ngày thứ X
        ("Tháng 5/2026 trung bình mỗi thứ Tư tiệm sửa mấy lượt xe?", A, "number", 1.0),
        ("Tháng 5/2026 trung bình mỗi thứ 3 có bao nhiêu lượt xe?", A, "number", 0.75),
        ("Th6/2026 trung bình mỗi ngày thứ Tư bao nhiêu lượt xe?", A, "number", 0.5),
        ("Các ngày thứ 3 trong tháng 5/2026 trung bình một ngày có mấy lượt xe?", A, "number", 0.75),
        # 'thu tiền' is not a weekday
        ("Tháng 5/2026 trung bình một phiếu thu tiền được bao nhiêu?", A, "number", 104286),
        # câu chung, đi qua module chung
        ("Doanh thu tháng 5/2026 của tiệm là bao nhiêu?", A, "number", 730000),
        ("Th6/2026 dthu của tiệm ra bao nhiêu?", A, "number", 310000),
    ],
}]
