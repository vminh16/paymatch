# Payment Gate

Trạng thái: **Đã chốt mức thiết kế (26/11/2026)**. Bám [problem-definition.md](../01-requirements/problem-definition.md) D1–D9.

## 1. Vai trò

Gate là **code, không phải agent**. Gate là nơi duy nhất ra lệnh chi; sim-world (sau này là MoMo/ngân hàng thật) mới giữ và chuyển tiền. Agent không bao giờ duyệt; "người duyệt" chỉ có thể là **chủ chuỗi** (từng hóa đơn hoặc hàng loạt) hoặc **mandate** chủ chuỗi đã ký.

## 2. Ba lớp luật

```
① Luật cứng (code, không cấu hình được)
   - payee chỉ từ vendor registry, khớp MST:
       chuyển khoản / thẻ ảo → TK `verified`; escrow → TK `verified` hoặc `escrow_only`
   - mỗi hóa đơn chi tối đa một lần (unique invoice_id); mỗi PO tối đa một escrow đang mở
   - approval phải khớp intent_hash hiện tại
   - hóa đơn `blocked` (🔴) không bao giờ ALLOW
   - hóa đơn gắn PO đang có escrow `held` chỉ chi bằng giải ngân escrow
   - indicator trong `risk.hard_blocks` → DENY
   - indicator khớp cảnh báo chéo mà approval không ghi xác minh → DENY (D8)
   - indicator khớp danh sách chính thức (SIMO) → DENY
   - kill switch; fail-closed khi không đọc được policy
② Policy nền tảng có TRẦN cho tự chi: 30 triệu/HĐ, 50 triệu/ngày (D9, QT-01); mandate chỉ đặt thấp hơn
② Policy nền tảng (MoMo, dữ liệu)          ┐
③ Mandate của chủ chuỗi (dữ liệu, version) ┘  gộp: luật CHẶT NHẤT thắng
```

**Loại luật viết bằng code, luật cụ thể là dữ liệu.** Loại điều kiện v1: `severity`, `reason_codes`, `amount`, `vendor`, `invoice_type`, `channel`, `time_window`, `daily_total`. Ví dụ mandate:

```yaml
mandate:
  version: 3
  mode: auto_pay            # review_only | ask_first | auto_pay
  limits: {per_invoice_vnd: 30000000, per_day_vnd: 50000000}   # bằng hoặc thấp hơn trần nền tảng
  auto_pay_vendor_ids: [ven_coffee_01, ven_pos_software]
  channel_rules:
    - {invoice_type: software, channel: virtual_card}
  bulk_approvable:
    - {reason_codes: [NON_XML_SOURCE], max_amount_vnd: 2000000}
  auto_pay_window: {start: "07:00", end: "22:00"}
  signed: {by: owner, method: biometric+otp, at: …}
```

Kết quả đánh giá luôn là một trong ba, kèm lý do:

| Kết quả | Nghĩa |
|---|---|
| `ALLOW` | Đủ điều kiện, có approval hợp lệ (single / bulk / mandate) |
| `REQUIRE_APPROVAL(method)` | Cần chủ chuỗi duyệt `single` hoặc được phép `bulk` |
| `DENY` | Vi phạm luật cứng/policy/kill switch |

Thêm luật chỉ làm chặt hơn (giống gộp Finding). Thêm loại điều kiện mới = sửa code Gate + test. Khi cần biểu đạt phức tạp hơn, thay bộ đánh giá bằng Cedar/OPA mà không đổi contract.

## 3. Approval gắn vào intent

```
intent_hash = hash(invoice_id, invoice_document.sha256, payee_account_id, amount, channel)   # cách băm: 05-api/schemas.md §4
approval = {invoice_id, job_id, status: active|superseded|consumed, intent_hash, amount_vnd, payee_account_id, channel,
            approver, method: single|bulk|mandate, mandate_version?, bulk_batch_id?,
            verification?: {called_phone_on_file, result, at},   # bắt buộc khi có CROSS_ALERT_HIT
            auth_proof, at}
```

- Gate chỉ nhận approval `active` của **job hoàn tất mới nhất**. Điều tra lại, Finding hệ thống mới, chi thất bại, Gate từ chối, chủ chuỗi hủy → approval `superseded`, phải duyệt lại.

- Hóa đơn, payee hay số tiền đổi sau khi duyệt → hash đổi → approval vô hiệu (chống "ký giao dịch nhưng không ký quyết định").
- Duyệt hàng loạt: một lần xác thực, sinh **một approval cho mỗi hóa đơn**, cùng `bulk_batch_id`.
- Tự chi: approval do core tạo với `method = mandate`; Gate kiểm lại toàn bộ, không tin core.
- Escrow (D7) không có hóa đơn lúc tạo: intent gắn `purchase_order_id`, `intent_hash = hash(purchase_order_id, vendor_account_id, amount, 'escrow')`; giải ngân yêu cầu `goods_receipt` + hóa đơn khớp PO.

## 4. Payment intent: hai pha

```
created ──► authorized ──► executing ──► settled
   │           │ (giữ chỗ daily_budget,     │
   │           │  phát token một lần)       ├──► failed   (trả lại ngân sách)
   └──► denied └──► expired (quá hạn, trả lại ngân sách)
```

- `authorized`: khóa dòng `daily_budgets (tenant, ngày)`, trừ tạm; phát `payment_token` dùng một lần.
- Core gọi `POST /intents` vào ngày `scheduled_for` (hoặc ngay khi chủ chuỗi chọn "trả ngay").
- `executing`: gọi `PaymentRail` (sim-world `/rails/transfers` | `/rails/cards` | `/rails/escrow`) với idempotency key = `intent_id`.
- `settled`/`failed`: ghi `ledger_entries` (chỉ ghi thêm) + outbox `payment.executed` / `payment.failed`.
- Nội dung chuyển khoản: `MST người bán · ký hiệu · số hóa đơn` (D2).

## 5. API

Đặc tả đầy đủ (đường dẫn có tiền tố `/gate`, thêm `:cancel`, `/escrows/{id}:refund`, `/budgets`): [05-api/gate-api.md](../05-api/gate-api.md). Bảng dưới là tóm tắt.

| Endpoint | Gọi bởi | Tác dụng |
|---|---|---|
| `POST /evaluate` | core, tool `payment_policy_preview` | **Chạy thử**, không tác dụng phụ: trả ALLOW / REQUIRE_APPROVAL / DENY + lý do |
| `POST /intents` | core | Tạo intent từ approval; Gate tự đọc lại invoice, payee, mandate, policy |
| `POST /intents/{id}:execute` | core | Chạy hai pha |
| `POST /escrows` | core (chủ chuỗi chọn escrow cho NCC mới) | Tạo cọc `held` |
| `POST /escrows/{id}:release` | core (đã có phiếu nhập + hóa đơn khớp PO) | Giải ngân cọc |
| `GET /intents/{id}` | core, console | Trạng thái |

`/evaluate` cho phép Thủ quỹ hiểu ràng buộc mà không có quyền chi, và cho UI hiện "khoản này cần duyệt thế nào" trước khi chủ chuỗi bấm.

## 6. Kênh trả

`PaymentRail` là port; mỗi kênh một adapter: `bank_transfer`, `virtual_card` (gắn merchant + số tiền + một lần), `escrow` (giữ → giải ngân / hoàn). Thêm kênh mới = thêm adapter; Gate kiểm kênh có được policy cho phép.
