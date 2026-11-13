# Chạy pipeline

Hướng dẫn setup, dữ liệu và thứ tự chạy nằm trong [README gốc](../README.md).

- Chuẩn bị PDF/chunk: `python -m src.run prepare`.
- Kiểm tra dữ liệu: `python -m src.run validate`.
- Retrieval: `dev` → `select` → `test`.
- Tổng hợp nhãn thủ công: `python -m src.run audit`.

Các lệnh trên chạy từ `starter/` bằng Python của `.venv`.
PostgreSQL + pgvector dùng Compose có sẵn; dừng nhưng giữ dữ liệu bằng
`docker compose -p day6_student_starter stop`. Không xóa volume để xử lý lỗi.
