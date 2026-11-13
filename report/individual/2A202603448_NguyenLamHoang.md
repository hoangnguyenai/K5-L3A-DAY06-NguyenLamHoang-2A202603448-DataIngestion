# Báo cáo Day 06 — Nguyễn Lâm Hoàng

MSSV: 2A202603448 · Lớp: L3A · Ngày chạy: 13/11/2026.

## Dữ liệu và pipeline

Chủ đề: truy xuất kiến thức Python cơ bản từ sách lập trình.

Corpus là *Think Python: How to Think Like a Computer Scientist*, Allen B. Downey,
2nd Edition, Version 2.4.1. [Trang tác giả](https://greenteapress.com/wp/think-python-2e/)
cung cấp PDF theo [CC BY-NC 3.0](https://creativecommons.org/licenses/by-nc/3.0/).
Bài học dùng phi thương mại, giữ nguyên PDF và ghi công tác giả.

PDF có 244 trang vật lý. Chọn **35 trang nội dung**: 23–29 (7 trang), 31–37 (7),
39–49 (11), 61–70 (10). Đây là nội dung giảng giải, glossary và bài tập các chương
1, 2, 3, 5; không tính bìa, mục lục, trang trống hoặc trang chỉ có tài liệu tham khảo.
Trong phạm vi này, số trang in bằng số trang PDF trừ 22.

[Manifest](../../data/manifest.json) ghi nguồn, quyền, ngày lấy, trang, số ký tự và hash.
Sau chuẩn hóa có 76.384 ký tự; mỗi trang từ 1.101 đến 3.092 ký tự. Ngưỡng 1.500 ký tự
trong GUIDE dành cho quy đổi nguồn không phân trang, không áp dụng thay số trang PDF.
PDF SHA-256: `6033000bac3f9268ad75ee041bf8e5d9a3bc8a33bb156399cbd014918cb59f94`.

Pipeline trích từng trang bằng pypdf layout mode, chuẩn hóa Unicode NFKC, bỏ soft
hyphen/NUL và whitespace dư cuối dòng, giữ đoạn và thụt dòng. Log ghi trang PDF 2
rỗng, không thuộc 35 trang được tính. Không có replacement character trong các
trang được chọn. Lỗi dính từ và gạch nối cuối dòng vẫn còn; không OCR hình ảnh,
không tạo câu hỏi phụ thuộc riêng hình vẽ.

Metadata mỗi chunk gồm document_id, source URL, page vật lý; chapter (chuỗi),
chapter_number (số nguyên), version, language và offsets. Chapter lấy từ tiêu đề
chương, version từ bìa, language từ văn bản. Source/page phục vụ truy vết;
chapter là trường lọc để giới hạn phạm vi theo câu hỏi người dùng cung cấp.
Chunk không vượt ranh giới trang.

Embedding: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`,
revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, 384 chiều, CPU local.
Query và document cùng model, cùng bước collapse whitespace, không thêm prompt,
vector chuẩn hóa. Model chỉ nhận tối đa 128 token; văn bản chunk trả về vẫn giữ
đầy đủ, nhưng phần vượt giới hạn không được model nhìn thấy khi tạo embedding.

Môi trường đã chạy: Python 3.14.3, pypdf 6.21.4, fonttools 4.68.0,
Sentence Transformers 5.7.0, Transformers 5.22.2, PyTorch 2.15.0, psycopg 3.3.8.
Database: PostgreSQL 16.16, pgvector 0.8.7, cosine exact search, top-3; filter JSONB
được áp dụng trong SQL trước LIMIT. Không dùng vector giả hay fallback store.

Database dùng Docker volume `day6_student_starter_pg_data`, bảng `day6_chunks`.
Nạp lại thay toàn bộ snapshot từng cấu hình trong transaction, nên xóa được chunk
cũ khi corpus thay đổi. Nạp hai lần giữ nguyên A=185, B=188, C=188.
[Kiểm tra lưu trữ](../../results/storage_check.json) còn xác nhận:
restart container không đổi số chunk; snapshot thử nghiệm dùng vector thật giảm
3→2 và ID cũ biến mất; tìm chính vector đã lưu trả top-1 cosine=1.0.
Dữ liệu thử nghiệm được dọn, không thay các cấu hình A/B/C.

Lệnh chạy từ `starter/` bằng Python của `.venv`: `python -m src.run prepare`,
`python -m src.run validate`, `python -m src.run dev`, `python -m src.run select`,
`python -m src.run test`, rồi `python -m src.run audit` sau khi điền nhãn.
Setup đầy đủ và lưu ý chạy lại xem [README](../../README.md). Chi phí API thực tế
bằng 0; phiên bản và thời gian thực tế lưu ở run.json của từng split.

## Cấu hình và benchmark

| Cấu hình | Chunking | Overlap | Filter |
|---|---|---:|---|
| A | Cửa sổ cố định 500 ký tự | 50 | Không |
| B | Ưu tiên đoạn/dòng, tối đa 500 ký tự; đoạn dài vẫn phải tách | 0 | Không |
| C | Dùng đúng chunk và vector B | 0 | Chapter khi câu hỏi cung cấp |

A–B thay chính sách chunking, bao gồm overlap. B–C chỉ thay áp dụng filter.
[Experiment log](../../artifacts/experiment_log.csv) lưu tham số, giả thuyết và điểm.

[20 câu hỏi](../../benchmark/questions.jsonl) được tạo trước retrieval:
Q01–Q15 dev thuộc chương 1/2/3; Q16–Q20 test thuộc chương 5.
Q03/Q06/Q14/Q16 có chapter rõ trong câu hỏi, trong đó Q16 thuộc test.
Không đưa đáp án hoặc gold source vào query/filter. Câu không có filter dùng
cùng truy xuất B; A/B vẫn có metadata để truy vết.

Evidence được kiểm tra tồn tại trên đúng trang sau chuẩn hóa. Hit chính yêu cầu
một chunk đúng document ID/trang và chứa đủ evidence, chỉ bỏ qua khác biệt whitespace.
Hit@1/Hit@3 báo tử/mẫu; không hợp nhiều chunk để thay định nghĩa chính.

Theo [protocol chốt trước chạy](../../benchmark/protocol.md), chọn bằng dev:
Hit@3 → Hit@1 → ít chunk hơn → thứ tự A/B/C. Chọn **A** lúc 17:53:50 giờ Bangkok,
trước khi test hoàn thành lúc 17:54:40. [Selection](../../artifacts/selection.json)
giữ model revision và hash corpus, benchmark, cấu hình, mã nguồn.
Không đổi cấu hình hoặc chọn lại theo kết quả test.

## Kết quả

Bảng dưới là phép chấm literal evidence ban đầu, giữ nguyên trong trace.

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian ghi vector (s) | Chi phí API |
|---|---|---:|---:|---:|---:|---:|
| A | dev | 3/15 (20,0%) | 7/15 (46,7%) | 185 | 0,515 | 0 |
| B | dev | 2/15 (13,3%) | 6/15 (40,0%) | 188 | 0,190 | 0 |
| C | dev | 2/15 (13,3%) | 6/15 (40,0%) | 188 | 0,190 | 0 |
| A | test | 2/5 (40,0%) | 3/5 (60,0%) | 185 | 0,896 | 0 |
| B | test | 3/5 (60,0%) | 3/5 (60,0%) | 188 | 0,286 | 0 |
| C | test | 3/5 (60,0%) | 3/5 (60,0%) | 188 | 0,207 | 0 |

Thời gian trong bảng trên là lần ghi snapshot đầu của từng cấu hình, không gồm
embedding và lần nạp lại kiểm tra idempotency. Bảng tài nguyên bên dưới tách các
bước này. Chi phí API bằng 0 vì model local; điện và mạng chưa được đo.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---:|---:|---:|---|
| A | 1,0 (10) | 15/15 | 1/1 (test) | 1 / 0 / 4; TB 1,6/2 |
| B | 1,3 (10) | 15/15 | 1/1 (test) | 1 / 0 / 4; TB 1,6/2 |
| C | 1,3 (10) | 15/15 | 1/1 (test) | 1 / 0 / 4; TB 1,6/2 |

Nhãn audit có AI hỗ trợ và được tác giả đồng ý sử dụng. Cách chọn mẫu, thang điểm
và lý do từng nhãn được lưu cùng kết quả để kiểm chứng.

**Đường dẫn trace, nhãn thủ công và cách chọn mẫu:**

- Trace: [dev](../../results/dev/trace.jsonl), [test](../../results/test/trace.jsonl).
- Nhãn và lý do từng trường hợp: [audit.csv](../../results/audit.csv);
  tổng hợp: [audit_summary.json](../../results/audit_summary.json).
- Coherence: cùng 10 midpoint của 10 trang đầu được chọn trong
  [coherence_sample.json](../../artifacts/coherence_sample.json); nếu có nhiều
  chunk phủ vị trí, lấy chunk có start_char nhỏ nhất.
- Grounding: cả 5 câu test của mỗi cấu hình; metadata: từng top-3, tổng 15 bản ghi
  mỗi cấu hình; filter: câu test Q16 của cả A/B/C.

Phương pháp: đọc chunk và top-3 so với câu hỏi, bằng chứng, trang nguồn; dùng
thang GUIDE và ghi lý do, không suy grounding từ Hit@3. Metadata/offsets được
kiểm tra thêm bằng code. Người đề xuất đã thấy gold và kết quả retrieval nên có
nguy cơ thiên lệch.


Có 45 trace dev và 15 trace test, mỗi trace có đủ 3 chunk, score, nguồn/trang,
filter, gold và nhãn tự động: [dev](../../results/dev/trace.jsonl),
[test](../../results/test/trace.jsonl). Điểm tổng hợp và run log nằm cùng thư mục.

| Cấu hình | Chunk | Ký tự tổng; min/mean/max | Token trước cắt | Chunk vượt 128 token |
|---|---:|---|---:|---:|
| A | 185 | 83.884; 55 / 453,4 / 500 | 19.684 | 33/185 |
| B | 188 | 76.384; 34 / 406,3 / 500 | 17.801 | 10/188 |
| C | 188 | như B | 17.801 | 10/188 |

| Cấu hình | Tạo embedding document dev | Ghi vector dev | Retrieval dev trung vị | Retrieval test trung vị |
|---|---:|---:|---:|---:|
| A | 16,521 s | 0,515 s | 36,3 ms | 44,4 ms |
| B | 11,847 s | 0,190 s | 32,3 ms | 31,6 ms |
| C | 0,076 s đọc cache B | 0,190 s | 43,2 ms | 31,8 ms |

Dev toàn luồng 138,029 s, test 37,451 s. Dev gồm lần tải/khởi tạo model đầu tiên;
test dùng cache embedding document. Số liệu một lần chạy, chưa đo lặp hoặc kiểm soát
warm-up/tải máy. Thời gian ghi vector trong bảng là lần nạp đầu; bước nạp lại kiểm
tra idempotency được tính trong thời gian toàn luồng. Không kết luận C tạo vector
nhanh hơn B: C dùng lại vector B. Chi phí API thực tế **0**; chưa đo điện, mạng,
CPU/RAM hoặc kích thước vật lý của database.

## Phân tích và kết luận

**Retrieval.** A hơn B/C đúng 1 câu dev ở Hit@3 nên được chọn theo quy tắc ban đầu.
Test B/C hơn A ở Hit@1, nhưng cả ba có cùng literal Hit@3=3/5. Với 5 câu test,
mỗi câu làm thay đổi 20 điểm phần trăm; chưa đủ để kết luận B/C tốt hơn tổng quát.

**Coherence.** Trên cùng 10 vị trí nguồn, điểm đề xuất của A là 1,0/2,
B/C là 1,3/2. B có một số chunk giữ trọn đoạn hoặc mục glossary, nhưng vẫn có
chunk bị tách giữa ý khi đoạn dài vượt 500 ký tự. Mẫu chỉ gồm 10 vị trí cố định,
nên mức cải thiện này chưa đại diện cho toàn corpus.

**Metadata.** Đối chiếu bằng code trên 45 bản ghi test cho thấy source, document_id,
page, chapter, version, language và offsets đều khớp trang nguồn. Kết quả này chỉ
áp dụng cho 45 bản ghi được kiểm tra. Tỷ lệ top-3 đúng filter:

| Cấu hình | Dev có filter | Test có filter |
|---|---:|---:|
| A | 2/3 | 1/1 |
| B | 1/3 | 1/1 |
| C | 3/3 | 1/1 |

Chapter giúp C loại kết quả sai phạm vi ở Q03/Q06. Tuy vậy, C không tăng Hit@3:
đúng chương chưa đảm bảo đúng đoạn. Metadata chapter cũng không phân biệt được các
mục nhỏ trong cùng chương; source/page vẫn cần để đối chiếu nguyên văn.

**Grounding.** Cả 5 câu test của mỗi cấu hình đã được đưa vào audit, thang 0/1/2.
Q16 không có bằng chứng làm tròn trong top-3. Q17/Q18/Q20 có đoạn hỗ trợ câu trả lời.
Q19 được chấm mức 2 trong audit dựa trên code nhánh dừng countdown ở trang 65:
nhánh n<=0 không gọi đệ quy tiếp. Grounding có 1 câu mức 0, 0 câu mức 1 và
4 câu mức 2 mỗi cấu hình, trung bình 1,6/2.
Grounding ở đây là đủ bằng chứng truy xuất, không phải độ chính xác câu trả lời LLM.

**Tác động chiến lược.** A có overlap nên dùng thêm 7.500 ký tự và 1.883 token
so với B; B nhiều hơn 3 chunk do ngắt đoạn tạo các phần ngắn, dù không overlap.
B vẫn có đoạn bắt đầu/kết thúc giữa ý vì giới hạn 500 ký tự, không đảm bảo coherence.
C cải thiện giới hạn phạm vi trên dev mà không thay chunk hay thêm embedding mới.
Chọn A theo dev, đồng thời ghi nhận chi phí token/truncation cao hơn và lợi thế
Hit@1 test của B/C. Khi mở rộng, cần thử trên dev mới và test mới, không tinh chỉnh
lại bộ test đã xem.

Các trường hợp có thể đối chiếu trực tiếp:

| Câu | Quan sát | Ý nghĩa |
|---|---|---|
| Q08, dev, trang PDF 33 | A không có chunk nào chứa nguyên evidence; B có hit | Cửa sổ/overlap vẫn có thể chia evidence, không chỉ lỗi xếp hạng |
| Q12, dev, trang PDF 40 | B/C có kết quả ở đúng trang nhưng evidence đầy đủ bị tách giữa chunk | Đúng trang chưa đủ hit; chunk theo đoạn vẫn phải cắt đoạn quá dài |
| Q16, test, trang PDF 61 | A trả trang 64/69/66; B/C trả 64/64/66, đều thiếu quy tắc // | Filter đúng chương không sửa được ranking trong chương |
| Q20, test, trang PDF 67 | A trả glossary trang 28 ở top-1, bằng chứng input ở top-2; B/C đúng top-1 | Ví dụ Hit@1 khác Hit@3 |
| Q19, test, gold ban đầu trang 66 | A/B/C tìm được code countdown ở trang 65, nhánh n<=0 không gọi tiếp | Gold thiếu bằng chứng hợp lệ, không nên kết luận mọi literal miss đều là lỗi retrieval |

Ở Q19, gold ban đầu chỉ ghi trang 66, trong khi top-3 có bằng chứng tương đương
ở trang 65. Do phép chấm tự động yêu cầu đúng trang và đủ đoạn gold, Q19 không
được tính hit trong bảng retrieval nhưng được chấm grounding mức 2 khi đọc code.
Các bảng Hit@1/Hit@3 giữ kết quả tự động ban đầu; không chạy lại model hoặc thay
cấu hình sau test. Đây là giới hạn của gold chưa liệt kê hết bằng chứng hợp lệ.
[Phân tích tự động](../../results/analysis.json) phân biệt evidence bị chia chunk
với evidence có trong kho nhưng không lọt top-3; đó là chẩn đoán literal, không
thay việc đọc bằng chứng tương đương.

**Chiến lược chọn và điều kiện áp dụng.** Giữ A là lựa chọn đã chốt trên dev:
Hit@3=7/15 so với 6/15 của B/C. A phù hợp làm baseline đơn giản khi chưa có bộ
tách cấu trúc tài liệu tốt, nhưng phải chấp nhận overlap làm tăng token và các
đoạn bị cắt giữa ý. Nếu ứng dụng bắt buộc giới hạn chương do người dùng cung cấp,
cơ chế filter của C hữu ích để bảo đảm phạm vi; thí nghiệm này chưa chứng minh
C tăng độ chính xác. Không đổi lựa chọn sang B/C chỉ vì Hit@1 test cao hơn.

**Nếu làm lại hoặc mở rộng.** Ưu tiên sửa những lỗi đã quan sát:

- Tách theo câu/đoạn kết hợp ngân sách token để giảm cắt giữa ý và tránh vượt
  giới hạn 128 token; kiểm tra riêng header/footer lặp lại trong PDF.
- Bổ sung đầy đủ các bằng chứng tương đương khi xây gold, như code trang 65 của
  Q19, và nhờ người khác đối chiếu để giảm thiên lệch nhãn.
- Mở rộng corpus và benchmark, thêm câu filter thuộc nhiều chương, tạo dev/test
  mới trước khi thử cấu hình khác. Không dùng lại test đã xem để tuyên bố độc lập.
- Đo thời gian nhiều lần trong cùng điều kiện, tách tải model, tạo embedding,
  ghi database và truy xuất; bổ sung CPU/RAM, dung lượng lưu và chi phí thực tế.

Các cải tiến trên là đề xuất cho lần thử sau, chưa được chạy trong kết quả hiện tại.
