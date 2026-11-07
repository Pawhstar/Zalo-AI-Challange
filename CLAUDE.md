# Zalo AI Challenge 2026 — DataMate

Đề bài: trả lời câu hỏi tiếng Việt về dữ liệu bán hàng của từng shop (CSV/Excel/SQLite).
Chấm điểm: đúng +1, sai −1, bỏ trống (abstain) 0. **Trả lời khi không chắc là lỗ điểm.**

**Đọc `datamate/HANDOFF.md` trước khi làm bất cứ việc gì** (luật thi, bản đồ code, lịch sử điểm, kế hoạch).
Rulebook của split đang làm: `Train/public_test/rulebook.md` (khác bản train ở vài điều).

## Hiện trạng (06/11/2026)
- Nhánh làm việc: `datamate-loader-engine`. Code ở `datamate/`, công cụ ở `datamate/tools/`.
- Public leaderboard: v1 −0,107 → v2 −0,016 → **v3 +0,052** (`submissions/submission_public_v3.jsonl`).
- Train, cross-validation bỏ từng nhóm shop: **PA +0,65**. Public chỉ đúng ~56% câu đã trả lời, train ~95% —
  khoảng chênh này là vấn đề số 1, nguyên nhân tìm được đến nay đều là loader đọc sai shop lạ.
- Hạn nộp Docker: **16/11/2026 23:59**. Docker **chưa từng build** (máy cũ không có Docker).

## Việc đầu tiên: tái tạo kết quả, chưa sửa logic
1. Môi trường Python 3.12 với đúng `datamate/requirements.txt` (pandas 3.1.1, numpy 2.5.4, openpyxl 3.1.5).
   Ví dụ: `uv run --no-project --python 3.12 --with-requirements datamate/requirements.txt ...`
2. Chạy `DATA_DIR=Train/public_test RESULT_DIR=<thư mục tạm> bash datamate/predict.sh`, so `submission.jsonl`
   với `submissions/submission_public_v3.jsonl` — **phải giống hệt**. Khác thì tìm nguyên nhân trước.
   Kiểm format: `python datamate/tools/check_sub.py <sub> Train/public_test/questions.jsonl`.
3. Train: `DATAMATE_RAW=1 python -X utf8 datamate/tools/fasteval.py --rebuild --dump dump_raw.jsonl`
   rồi `python datamate/tools/cv.py dump_raw.jsonl` → best held-out ≈ 0,65 (thr 0.5, min_n 5).
   Lần đầu `--rebuild` mất ~15–20 phút (load 30 shop); sau đó dùng cache, ~4 phút.
4. Nếu có Docker: `docker build -t datamate ./datamate`, chạy `--network none` mount `Train/public_test` vào `/data`,
   output phải trùng bước 2. Ghi thời gian load từng shop (`/result/logs/run.log`; giới hạn 30 s/câu).
5. Báo lại kết quả từng bước. Sau đó mới làm Nấc A trong HANDOFF §6.

## Quy trình mỗi thay đổi
1. Sửa code (loader / module trả lời).
2. `fasteval.py --rebuild` (nếu sửa loader) với `DATAMATE_RAW=1` → `cv.py` → chỉ giữ nếu held-out PA tăng.
3. `python datamate/tools/make_policy.py dump_raw.jsonl 0.5 5` để sinh lại `datamate/datamate/policy.json`
   (không sửa tay file này).
4. Chạy `predict.sh` trên public, `check_sub.py`, lưu file nộp vào `submissions/submission_public_vN.jsonl`.
5. Commit (kèm điểm train CV trong message). Người dùng tự nộp lên leaderboard (5 lượt/ngày).

## Luật bắt buộc
- **Không đọc, không gán nhãn đáp án public/private test** (luật thi). Với shop public chỉ được kiểm tra tính nhất quán
  dữ liệu đã load: `python datamate/tools/diag.py public_test`.
- Không commit dữ liệu: `Train/`, `*.zip`, `train+public_test/`, cache `bizcache*/`. Repo GitHub là private;
  không push dữ liệu lên.
- Đáp án phải deterministic, chạy offline, không gọi API ngoài. Nếu thêm LLM: < 5B tham số, context ≤ 16K, greedy.
- Không nhúng regex có `\b` vào lệnh shell (bị biến thành ký tự backspace) — sửa code bằng file/Edit.
- `git filter-branch`/viết lại lịch sử trên nhánh đang checkout sẽ xoá file dữ liệu khỏi đĩa — đừng làm.
- Repo nằm trong OneDrive: nếu git báo lỗi khoá file, tạm dừng đồng bộ OneDrive.
