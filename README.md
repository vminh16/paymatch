# PayMatch — Khớp rồi mới chi

Phòng kế toán ảo gồm nhiều AI agent chuyên môn hóa theo nghề, kiểm soát trước khi chi cho chuỗi cửa hàng nhỏ trên MoMo Doanh Nghiệp.

- Bắt đầu đọc: [docs/01-requirements/problem-definition.md](docs/01-requirements/problem-definition.md)
- Quy tắc cho AI agent khi code: [AGENTS.md](AGENTS.md)
- Mục lục tài liệu: [docs/README.md](docs/README.md)
- Cấu trúc repo, test, quy ước đặt tên: [docs/02-architecture/repo-and-testing.md](docs/02-architecture/repo-and-testing.md)

```bash
make install   # uv sync toàn workspace
make test
```

> Lưu ý Postgres local (`docker compose`): `infra/init-gate-role.sql` chỉ chạy khi khởi tạo volume Postgres mới; nếu đã có volume cũ, chạy `docker compose down -v` trước khi `up`.
