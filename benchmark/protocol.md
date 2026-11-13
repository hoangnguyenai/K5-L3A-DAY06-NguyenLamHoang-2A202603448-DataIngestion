# Quy ước thí nghiệm

Chốt trước lần truy xuất đầu tiên: 13/11/2026. Corpus gồm 35 trang PDF của
Think Python 2e v2.4.1, theo `data/manifest.json`.

20 câu trong `questions.jsonl`: Q01–Q15 là dev; Q16–Q20 là test.
Dev thuộc chương 1/2/3; test thuộc chương 5. Câu lọc: Q03, Q06, Q14, Q16.
Filter `chapter` được cung cấp rõ trong câu hỏi trước truy xuất; không suy từ gold.
C có filter khi câu hỏi cung cấp; A/B bỏ qua filter nhưng vẫn giữ cùng metadata.

A: cửa sổ 500 ký tự, overlap 50. B: ưu tiên ranh giới đoạn/dòng, tối đa 500 ký tự,
không overlap. A–B thay cách chia chunk (bao gồm overlap). C dùng đúng chunk B,
chỉ thay việc áp dụng filter. Không chia chunk vượt trang vật lý.

Dùng cùng model multilingual MiniLM, cùng revision, chuẩn hóa vector, PostgreSQL
+ pgvector, cosine exact search, top-3 cho mọi cấu hình. Model chạy CPU local.
Ghi giới hạn token và số chunk/query bị truncation nếu có, không coi phần bị cắt
là đã được embedding đầy đủ. Không dùng vector giả hoặc đổi model khi lỗi.

Chọn cấu hình bằng dev: ưu tiên Hit@3, sau đó Hit@1, sau đó ít chunk hơn; nếu vẫn
bằng thì thứ tự A/B/C. Chạy `select` để lưu lựa chọn và hash dữ liệu/cấu hình.
Sau đó mới chạy test cho cả ba để so sánh, giữ nguyên lựa chọn đã chốt.
Nếu thay đổi sau khi thấy test thì kết quả test cũ không còn là holdout độc lập.

Hit: một chunk có đúng document ID + trang vật lý và chứa đủ evidence_quote,
chấp nhận khác biệt whitespace. Các evidence tương đương cần người đọc xác nhận
và ghi vào alternative_evidence; không tự suy nhãn đúng chỉ vì cùng chủ đề.
Hit@1/Hit@3 báo tử/mẫu riêng dev/test. Bằng chứng bị chia giữa nhiều chunk không
tính hit chính, dù hợp nhiều chunk có thể đủ trả lời.

Evidence được AI hỗ trợ chọn từ văn bản PDF, đã kiểm tra vị trí bằng code.
Học viên cần đối chiếu PDF và đáp án trước lần chạy đầu. Corpus tiếng Anh, câu hỏi
tiếng Việt: đây là bài truy xuất liên ngôn ngữ. Tập nhỏ và các chương liên quan
vẫn có nguy cơ trùng khái niệm; không suy rộng kết luận ra mọi dữ liệu.

Audit sau test: cùng 10 vị trí nguồn trong coherence_sample.json cho mỗi cấu hình;
nếu A có nhiều chunk phủ vị trí thì lấy chunk có start_char nhỏ nhất. Chấm
coherence 0/1/2; grounding 0/1/2 cho cả 5 câu test × 3 cấu hình; metadata 0/1
cho từng top-3; filter 0/1 cho câu có điều kiện (cả 3 kết quả phải tuân thủ).
Ghi lý do và người chấm trong results/audit.csv; không tự điền nhãn từ Hit@3.
Nếu thiếu kết quả top-3 phải ghi nhận, không coi danh sách rỗng là tuân thủ filter.

Người chấm là tác giả bài; ghi rõ mọi hỗ trợ từ AI và nguy cơ thiên lệch. Thang điểm
và yêu cầu đầy đủ theo GUIDE.md, không gọi grounding retrieval là độ đúng của LLM.
