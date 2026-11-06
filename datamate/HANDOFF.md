# DataMate — bàn giao & kế hoạch (cập nhật 06/11/2026)

Tài liệu này gói lại toàn bộ phiên làm việc: luật thi, hiện trạng, lịch sử điểm,
cách chạy, các bài học, và kế hoạch tiếp theo. Đọc file này trước khi làm tiếp.

## 1. Luật thi (tóm tắt những gì ảnh hưởng thiết kế)

- Input: `questions.jsonl` (id, business_id, question, as_of_date), `data/<shop>/` (csv/xlsx/sqlite + README.md),
  `rulebook.md`, `calendar.csv`. **Rulebook khác nhau giữa các split** — luôn đọc rulebook của split đang chạy.
- Chấm: đúng **+1**, sai **−1**, abstain/thiếu dòng **0**. Sai type/format = sai. PA = (đúng − sai)/N.
  ⇒ Trả lời khi không chắc là lỗ vốn. Abstain là công cụ chính.
- Format từng type: rulebook §9 (`number` số nguyên VND, `percent` là số %, `date` "YYYY-MM-DD"/"YYYY-MM", `table` columns+rows…).
- Nộp solution (Docker, offline, `predict.sh` đọc `/data` ghi `/result/submission.jsonl` + log từng câu): **hạn 16/11 23:59**.
  Private test: 20–23/11, **có loại shop không có trong train/public**.
- Giới hạn: tổng < 6B tham số, LLM < 5B, context ≤ 16K, **≤ 30 s/câu**, 1×A30, deterministic.
  Cấm gán nhãn public/private test để train/tune. Public: 5 lượt nộp/ngày.
- Ảnh "Technical requirements" về zaic_tools/state.json/ASR thuộc track LifeMate, không phải DataMate.

## 2. Hiện trạng code (`datamate/`)

| File | Vai trò |
|---|---|
| `datamate/loader.py` | chuẩn hoá file của shop → orders / lines / items / units / stock / payments / customers |
| `datamate/schema.py` | map cột theo **mô tả trong README** (đáng tin hơn tên cột bị xáo) |
| `datamate/periods.py` | biểu thức thời gian rulebook §2 (`parse_time` → main / compare / months / until) |
| `datamate/query.py` | câu bán hàng: bộ lọc × đại lượng × dạng trả lời |
| `datamate/debt.py` | công nợ §4 · `datamate/purchases.py` nhập hàng §5 |
| `datamate/intents.py`, `metrics.py`, phần `_dispatch` trong `engine.py` | router từ khoá cũ (chỉ dùng cho intent được tin) |
| `datamate/engine.py` | `raw_answer` (đáp án + **tag** loại câu) và `answer` (chính sách abstain) |
| `datamate/policy.json` | danh sách tag được trả lời — **sinh tự động**, không sửa tay |
| `datamate/predict.py`, `predict.sh`, `Dockerfile`, `requirements.txt` | suy luận + đóng gói |
| `tools/` | công cụ phát triển (xem §4) |

Thư viện đã đo với: Python 3.12, pandas 3.1.1, numpy 2.5.4, openpyxl 3.1.5 (đã ghim).

## 3. Lịch sử điểm

| Mốc | Train PA (CV bỏ nhóm shop) | Public PA | Ghi chú |
|---|---|---|---|
| Ban đầu (code có sẵn) | −0,58 (không CV) | — | 644/3000 đúng |
| Sửa loader | −0,12 (không CV) | — | 1338 đúng |
| periods + query/debt/purchases | +0,33 (không abstain) | — | 1988 đúng |
| + abstain (danh sách tay) = **v1** | +0,52 | **−0,107** | ~183 đúng / 290 sai |
| mã đơn trống ô gộp + policy từ CV = **v2** | +0,61 | **−0,016** | ~213 / 229 |
| gộp tên món viết khác + bỏ dòng voucher/ship = **v3** | +0,65 | **+0,052** | ~247 / 195 |

Khoảng cách train ↔ public vẫn rất lớn: train trả lời đúng ~95% câu đã trả lời, public chỉ ~56%.
Nguyên nhân chính đã tìm được đều là **loader đọc sai dữ liệu shop lạ**, không phải chính sách abstain.

## 4. Cách chạy

```bash
# suy luận (giống hệt Docker)
DATA_DIR=/path/to/public_test RESULT_DIR=./result ./predict.sh
# kiểm tra format file nộp
python tools/check_sub.py result/submission.jsonl /path/to/public_test/questions.jsonl
# đánh giá nhanh trên train (cache pickle các shop; --rebuild sau khi sửa loader)
DATAMATE_RAW=1 python tools/fasteval.py --rebuild --dump dump_raw.jsonl   # không abstain, có tag
python tools/cv.py dump_raw.jsonl                                          # CV bỏ từng nhóm shop, chọn ngưỡng
python tools/make_policy.py dump_raw.jsonl 0.5 5                           # ghi datamate/policy.json
python tools/fasteval.py                                                   # điểm có abstain
python tools/diag.py public_test                                           # kiểm tra nhất quán loader, không cần nhãn
```
Các script trong `tools/` có đường dẫn cứng tới `C:/Users/start/Downloads/Zalo-AI-Challange` — sửa biến `ROOT` nếu chuyển máy.

## 5. Bài học

1. Cột phải map theo **mô tả README**, tên cột bị xáo có chủ đích.
2. Lỗi lớn nhất luôn ở loader: dòng tiếp theo để trống mã đơn (ô gộp), tên món nhiều cách viết, dòng không phải hàng
   (Voucher / Dùng điểm / Phí ship / Phí phục vụ), trả hàng ghi ở bảng phụ (lô, phiếu trả), dòng trùng trong cùng đơn.
3. Mọi ngưỡng/danh sách tin cậy phải chọn bằng **CV bỏ nhóm shop**, không phải trên toàn train.
4. Chỉ kiểm tra public bằng tính nhất quán dữ liệu (`tools/diag.py`), không đọc đáp án/không gán nhãn.
5. Viết code bằng file/Edit, không nhúng regex `\b` qua shell (bị biến thành ký tự backspace).

## 6. Kế hoạch tiến tới PA 1.0

PA 1.0 nghĩa là trả lời đúng **mọi** câu, kể cả câu unanswerable — với dữ liệu bẩn và loại shop mới ở private
thì không thực tế. Mục tiêu dưới đây chia theo nấc; mỗi nấc chỉ nhận thay đổi nếu CV bỏ nhóm shop tăng.

### Nấc A — đưa public lên ≥ 0,30 (trước 16/11)
Ưu tiên theo số câu public đang trả lời sai hoặc bỏ trống:
1. **Độ chính xác của câu đang trả lời (public ~56%)**: chạy `tools/diag.py` mở rộng — so tổng doanh thu
   tính từ dòng hàng với cột tổng đơn/tiền hàng của chính file, kiểm tra trạng thái không nhận ra, đơn vị cơ bản
   thiếu, tên khách. Mỗi chênh lệch là một lỗi loader cần sửa (cách đã tìm ra lỗi ô gộp và tên món).
2. **Shop ngành riêng ở public** (đang bỏ trống gần hết): sửa xe (dev_012 — loader chưa đọc được: không có mã phiếu,
   mỗi dòng một phiếu, "Làm gì" nhiều việc một ô, thợ theo tên gọi), điện thoại (dev_011, dev_014 — sheet "Ghi tắt",
   thu máy cũ, trả góp, bảo hành, dòng máy/hãng), mẹ và bé (dev_013 — header 2 dòng, voucher/điểm, size/số sữa),
   nhà hàng (bàn, phí phục vụ). Viết theo luật §6 của rulebook public.
3. **Các nhóm câu chưa có module** (sai/bỏ trống nhiều trên train): tồn kho tại một ngày (thẻ kho / nhập − bán),
   hàng hết hạn & lô gần hết hạn, giao nhiều đợt, hiệu ứng tăng giá, hàng ế, câu có/không (`boolean`),
   tăng/giảm liên tục, xếp hạng "nào … nhất" qua `query.py` thay router cũ, đếm khách đã mua.
4. Đọc Excel nhanh hơn (shop lớn mất 54 s để load) — đọc trước toàn shop rồi mới trả lời để không câu nào vượt 30 s.

### Nấc B — chống overfit cho private (loại shop mới)
5. Thay router từ khoá bằng **LLM nhỏ (< 5B, ví dụ Qwen 3–4B) làm bộ trích slot**: câu hỏi → JSON
   {đại lượng, bộ lọc, kỳ, dạng trả lời}; phần tính toán vẫn là các hàm deterministic đã có. Sinh dữ liệu huấn luyện
   slot từ train (đã có đáp án) và câu tổng hợp; không dùng public/private. Decode greedy, cố định seed.
6. Abstain theo **độ tin cậy**: chỉ trả lời khi slot do LLM và do luật cho cùng kết quả (hoặc xác suất cao).
7. Loader tổng quát hơn cho shop lạ: nhận dạng vai trò cột bằng mô tả README + giá trị (mã, ngày, tiền), không phụ thuộc
   danh sách tên cột.

### Nấc C — hướng tới 1.0 (dài hạn, ngoài khung cuộc thi)
8. Bộ kiểm thử theo từng điều luật rulebook (mỗi điều một test với dữ liệu nhỏ dựng tay).
9. Kiểm tra chéo hai đường tính (từ dòng hàng và từ bảng đơn) trước khi trả lời; lệch thì abstain.

### Lịch đề xuất
| Ngày | Việc |
|---|---|
| 07–09/11 | Nấc A.1 + A.3 (lỗi loader còn lại, module thiếu), mỗi ngày nộp 1–2 bản public |
| 10–12/11 | Nấc A.2 (4 ngành riêng), A.4 |
| 13–14/11 | Nấc B.5–6 nếu kịp; nếu không, giữ bản rule-based, siết policy |
| 15/11 | Build Docker trên máy có Docker, so output với `predict.sh` local (phải giống hệt), README |
| 16/11 | Nộp solution (Docker + checksum + link Drive) |

## 7. Việc cần lưu ý ngay
- Commit `1144efc` ("?") đã đưa `Train.zip`, `Train/train.zip`, `train+public_test.zip` (~1,5 GB) và
  `__pycache__` vào git. **Đừng push** nhánh này: GitHub từ chối file > 100 MB, và luật thi cấm phát tán dữ liệu.
  Nên gỡ các file đó khỏi lịch sử (ví dụ `git reset --soft d3978e3`/`58bdf24` rồi commit lại không kèm zip) và thêm
  `*.zip`, `__pycache__/`, `Train/` vào `.gitignore`.
- Lượt nộp public ngày 06/11: đã dùng 3/5 (v1, v2, v3). File nộp ở `submissions/`.
