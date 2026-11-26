# Vòng đời agent và memory

Trạng thái: **Đã chốt mức thiết kế (26/11/2026)**.

## 1. Vòng đời bot

```
draft ──► pending_review ──► active ──► disabled ──► archived
              │ (từ chối)          ▲          │
              └──► draft           └──────────┘ (bật lại)
(lộ trình: pending_review ──► shadow ──► active)
```

| Trạng thái | Ý nghĩa |
|---|---|
| `draft` | Đang soạn (v1: form; lộ trình: chat) |
| `pending_review` | Chờ chủ chuỗi duyệt (bot tenant). Lộ trình: quản trị MoMo duyệt template marketplace |
| `shadow` *(lộ trình)* | Chạy và ghi Finding nhưng **không tính vào màu**; đo tỷ lệ báo nhầm (MT4) |
| `active` | Tính vào màu |
| `disabled` | Tạm tắt (tenant tắt, hoặc MoMo kill switch) |
| `archived` | Thay cho xóa; Finding cũ vẫn trỏ được tới version |

- **Không xóa cứng.** "Xóa" = `archived`.
- **Mỗi lần sửa tạo version mới**; job chốt version lúc mở phiên (`/internal/jobs/{id}/session`).
- **Bot bắt buộc**: `required_for: [invoice_type…]`. Tenant không tắt được; chỉ MoMo tắt qua kill switch. v1: `procurement`, `accounts-payable`, `fraud-control`, `tax` bắt buộc với `goods`; `procurement`, `fraud-control`, `tax` bắt buộc với `software` (QT-01: tự chi phải khớp hợp đồng); `branch-operations` bắt buộc với `utility`; `treasury` bắt buộc với mọi loại.
- **Phạm vi**: `system` (6 bot có sẵn), `tenant` (chủ chuỗi tạo qua form). Lộ trình: `marketplace`.
- Bot `system` mới vào `active` sau khi qua eval. *(Lộ trình)* Shadow bắt buộc với bot tenant mới, mặc định 7 ngày hoặc 30 hóa đơn.
- **Validate khi lưu**: tool ⊆ registry ∩ `tool_grants` của tenant; reason codes hợp lệ; triggers hợp lệ.

## 2. Memory *(lộ trình — không có trong v1)*

| Loại | Ví dụ | Lưu ở |
|---|---|---|
| Hội thoại | — | Không có: mỗi job không giữ trạng thái |
| Dữ kiện nghiệp vụ | danh sách quán, giờ mở cửa, hợp đồng | Bảng DB bình thường, **không phải memory** |
| **Memory của bot** | "NCC sữa hay giao thiếu ~5%"; "Quán 3 tháng 6 đông khách vì sự kiện" | `bot_memories` |

`bot_memories`: `tenant_id`, `bot_id`, `subject` (vendor/store/…), `content`, `provenance`, `source_finding_id`, `created_by`, `expires_at`.

**Ghi**
- Bot không ghi trực tiếp (mọi tool chỉ-đọc). Bot đề xuất qua `Finding.memory_proposals`.
- Đề xuất suy ra từ dữ liệu `trusted` → tự lưu.
- Đề xuất suy ra từ dữ liệu `untrusted` → vào `memory_proposals`, **cần người xác nhận** (chống đầu độc memory).
- Chủ chuỗi/kế toán tự thêm ghi chú được.

**Đọc**
- Qua tool `bot_memory`, chỉ-đọc, giới hạn theo bot + tenant.
- Memory chỉ được **tăng** mức nghi ngờ hoặc thêm ngữ cảnh; không bao giờ là nguồn của tài khoản, giá, hay lý do hạ màu.

**Quản lý**
- Có màn hình xem, sửa, xóa memory theo bot; có hạn dùng (mặc định 180 ngày).
- Bot `archived` → memory giữ nguyên để tra cứu, không còn được đọc bởi job mới.
