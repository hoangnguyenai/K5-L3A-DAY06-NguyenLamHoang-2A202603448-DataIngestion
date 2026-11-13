# Data Ingestion — Nguyễn Lâm Hoàng

Bài cá nhân Day 06: so sánh ba cách chuẩn bị dữ liệu cho truy xuất vector.
Corpus là **35 trang nội dung** của *Think Python, 2nd Edition, Version 2.4.1*,
Allen B. Downey. PDF gốc có 244 trang; chỉ ingest các trang vật lý
23–29, 31–37, 39–49 và 61–70. Không tính bìa, mục lục hoặc trang trống.

Nguồn: [trang tác giả](https://greenteapress.com/wp/think-python-2e/),
[PDF](https://greenteapress.com/thinkpython2/thinkpython2.pdf).
Giấy phép [CC BY-NC 3.0](https://creativecommons.org/licenses/by-nc/3.0/):
ghi công, dùng cho bài học phi thương mại. Giữ nguyên PDF và thông báo giấy phép.

## Chuẩn bị dữ liệu, chưa cần Docker

Chạy PowerShell từ thư mục dự án:

```powershell
cd starter
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-prepare.txt
.\.venv\Scripts\python.exe -m src.run prepare
.\.venv\Scripts\python.exe -m src.run validate
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Nếu đã có môi trường ảo thì bỏ lệnh tạo lại. PDF gốc được nộp kèm tại
`data/raw/think-python-2e/thinkpython2.pdf`; nguồn tải và SHA-256 nằm trong manifest.

Manifest ghi nguồn, quyền, trang vật lý/trang in, số ký tự và SHA-256.
Văn bản/chunk được tạo lại ở đường dẫn cố định; không tạo ảnh hay thư mục mỗi lần chạy.
Chúng ở máy local và được Git bỏ qua. PDF trích xuất có thể dính từ và giữ gạch nối
cuối dòng; benchmark cần được đối chiếu với PDF trước khi chạy retrieval.

## Chạy với PostgreSQL + pgvector

Mở Docker Desktop và đợi Engine sẵn sàng, sau đó từ `starter/`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
docker compose -p day6_student_starter up -d --wait
.\.venv\Scripts\python.exe scripts/check_setup.py
.\.venv\Scripts\python.exe -m src.run dev
.\.venv\Scripts\python.exe -m src.run select
.\.venv\Scripts\python.exe -m src.run test
```

Chỉ copy `.env` nếu chưa có để tránh ghi đè. Lần đầu tải model cần mạng và dung lượng;
model chạy CPU local, không cần API key. Dùng
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 chiều,
cùng revision và xử lý query/document. Revision, phiên bản thư viện, token bị cắt,
thời gian và chi phí được ghi khi chạy. PostgreSQL dùng cổng local 55433;
pgvector cosine search dạng exact, có lưu bền vững và filter JSONB.

A: 500 ký tự, overlap 50. B: ưu tiên ranh giới đoạn/dòng, tối đa 500 ký tự.
C dùng chunk B và chỉ thêm filter `chapter` khi câu hỏi nêu rõ.
Nạp lại thay snapshot của từng cấu hình trong transaction, xóa chunk cũ;
code kiểm tra số lượng không đổi qua hai lần nạp và các kết nối mới.

20 câu: 15 dev thuộc chương 1/2/3, 5 test thuộc chương 5; 4 câu filter,
gồm 1 test. Tiêu chí chọn và cách tính theo [protocol](benchmark/protocol.md).
`select` chốt lựa chọn trên dev trước test. Không sửa cấu hình theo điểm test
rồi báo đó là holdout độc lập.

## Kết quả và bài nộp

- `data/manifest.json`: bản kê corpus; `configs/strategies.json`: cấu hình.
- `benchmark/questions.jsonl`: câu hỏi, split, đáp án, trang và evidence.
- `artifacts/experiment_log.csv`: giả thuyết và điểm thực tế sau khi chạy.
- `results/preparation/`: thống kê chuẩn bị và log trích xuất.
- Sau retrieval: `results/dev/`, `results/test/` có top-3 trace, metric và run log;
  `artifacts/selection.json` lưu lựa chọn đã chốt.
- Sau test: điền score, reason trong `results/audit.csv`, rồi chạy
  `.\.venv\Scripts\python.exe -m src.run audit`. Chấm coherence, metadata,
  grounding và filter theo GUIDE; không lấy Hit@3 thay nhãn thủ công.
- [Báo cáo cá nhân](report/individual/2A202603448_NguyenLamHoang.md).

**Trạng thái hiện tại:** đã chạy model local, PostgreSQL + pgvector và đủ A/B/C.
Dev Hit@3: A 7/15, B/C 6/15; chọn A trước test. Test literal Hit@3: cả ba 3/5.
Đã kiểm tra nạp lại không trùng, xóa chunk cũ và lưu bền vững qua restart container.
Kết quả ở `results/dev/`, `results/test/`, `results/storage_check.json`.

`results/audit.csv` có 93 dòng đánh giá kèm điểm và lý do, có AI hỗ trợ.
Tổng hợp ở `results/audit_summary.json`.
Thang điểm theo GUIDE: coherence và grounding 0/1/2; metadata và filter 0/1.
Khi sửa điểm hoặc lý do, tổng hợp lại bằng `python -m src.run audit` từ `starter/`.
`results/drafts/` là bản nháp local, được Git bỏ qua.
Q19 có bằng chứng tương đương ở trang 65 ngoài gold ban đầu trang 66: audit chấm
grounding mức 2, còn bảng retrieval giữ điểm tự động theo gold ban đầu.

Phân tích lỗi lưu tại `results/analysis.json`; minh chứng kiểm tra lưu trữ tại
`results/storage_check.json`. Pipeline tự kiểm tra số chunk qua hai lần nạp.

Các lệnh dev/select/test phía trên dành cho lần chạy sạch. Bản repo có kết quả sẵn
sẽ chủ động chặn ghi đè test/selection. Để tái lập toàn luồng, dùng bản sao repo và
cất `results/dev/`, `results/test/`, `results/audit.csv`, `artifacts/selection.json`
ra ngoài bản sao trước khi chạy; giữ nguyên benchmark, cấu hình và mã nguồn.
Lần chạy lại là kiểm tra tái lập, không coi là một bộ test độc lập mới.

Không push môi trường ảo, model cache, dữ liệu trung gian hoặc secret.
Các kết quả retrieval/audit là minh chứng của bài nộp.

Đề bài và tiêu chí: [GUIDE](GUIDE.md), [BENCHMARK](BENCHMARK.md),
[RUBRIC](RUBRIC.md), [RULES](RULES.md), [SUBMISSION](SUBMISSION.md).
