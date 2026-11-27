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

```bash
cp .env.example .env   # tùy chọn: khóa dev mặc định đã có sẵn trong compose
make up                # postgres → core-migrate (migration + seed demo) → sim-world, gate, merchant-api, internal-api, core-worker, agent-worker
```

> Lưu ý Postgres local (`docker compose`): `infra/init-gate-role.sql` chỉ chạy khi khởi tạo volume Postgres mới; nếu đã có volume cũ, chạy `docker compose down -v` trước khi `up`. Mỗi lần `up`, `core-migrate` nạp lại seed demo của core; `down -v` để xóa sạch cả ledger của Gate.
>
> agent-worker hiện chạy `LLM_MODE=replay` với một cassette (`LLM_CASSETTE_PATH`): hóa đơn không có trong cassette sẽ ra vàng. Cần adapter LLM thật để chạy đủ kịch bản (xem agent-runtime.md §7).
