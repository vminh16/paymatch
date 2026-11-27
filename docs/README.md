# PayMatch — Tài liệu thiết kế

Phòng kế toán ảo gồm nhiều AI agent chuyên môn hóa theo nghề, hỗ trợ duyệt chi an toàn cho chuỗi cửa hàng nhỏ trên MoMo Doanh Nghiệp.

| Thư mục | Nội dung |
|---|---|
| [01-requirements/problem-definition.md](01-requirements/problem-definition.md) | **Đọc đầu tiên**: đầu vào, bài toán, đầu ra, quyết định nghiệp vụ đã chốt |
| [01-requirements/PayMatch_BRD_v1.0.md](01-requirements/PayMatch_BRD_v1.0.md) | BRD gốc (v1.0, 25/11/2026) |
| [02-architecture/architecture.md](02-architecture/architecture.md) | 4 mặt phẳng, 3 service, ranh giới tin cậy, console MoMo, quyết định đã chốt |
| [02-architecture/flows.md](02-architecture/flows.md) | Trạng thái hóa đơn và các luồng F1–F12 |
| [02-architecture/data-model.md](02-architecture/data-model.md) | Schema DB, bảng chính, những gì không lưu trong Postgres |
| [02-architecture/payment-gate.md](02-architecture/payment-gate.md) | Ba lớp luật, mandate, approval gắn intent, payment intent hai pha, API |
| [02-architecture/repo-and-testing.md](02-architecture/repo-and-testing.md) | Cấu trúc repo, phân công, chiến lược test, test bất biến, scale |
| [03-agents/agent-roster.md](03-agents/agent-roster.md) | Kế toán trưởng điều phối + 6 agent chuyên môn: vai, checklist, tool, giới hạn quyền |
| [03-agents/agent-runtime.md](03-agents/agent-runtime.md) | Agent điều phối ReAct theo loại việc, rào chắn code, Finding, mã lý do, LangGraph |
| [03-agents/tools.md](03-agents/tools.md) | Tool nằm ở đâu, đường gọi, nguyên tắc, danh mục tool v1 |
| [03-agents/prompts-and-skills.md](03-agents/prompts-and-skills.md) | Ba lớp prompt, cấu trúc skill, truy vết version |
| [03-agents/agent-lifecycle-and-memory.md](03-agents/agent-lifecycle-and-memory.md) | Vòng đời bot (bắt buộc, archive; lộ trình: shadow), memory (lộ trình) |
| [03-agents/bot-manifest.md](03-agents/bot-manifest.md) | Hợp đồng để người dùng tự thêm bot |
| [04-data/README.md](04-data/README.md) | Dữ liệu: mẫu thật trước, sinh sau; định dạng XML hóa đơn (QĐ 1233), nguồn số liệu, persona, đặc tả bộ dữ liệu sim-world |
| [05-api/README.md](05-api/README.md) | API contract: cổng, ai gọi ai, quy ước, lỗi, từng API, sự kiện, ma trận phủ luồng |
| [research/references.md](research/references.md) | Paper và hệ thống tham khảo, ý dùng cho sản phẩm |
| [research/domain-notes.md](research/domain-notes.md) | Nghiệp vụ kế toán phải trả, thuế VN |
| [glossary.md](glossary.md) | Thuật ngữ |

Quy ước: quyết định mới hoặc thay đổi quyết định cũ → cập nhật mục "Quyết định đã chốt" trong architecture.md, ghi ngày.
