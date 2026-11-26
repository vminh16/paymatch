# Payment Gate API (`/gate/*`, cổng 8100)

Trạng thái: **v0.2 (26/11/2026)**, đã sửa theo review. File OpenAPI: `contracts/openapi/gate.yaml`. Luật và state machine ở [payment-gate.md](../02-architecture/payment-gate.md).

Mọi endpoint cần `X-Service-Key`, khóa riêng cho từng bên gọi. Endpoint ngoài bảng → `403`. `agent-worker` không có khóa Gate.

| Endpoint | merchant-api | core-worker | internal-api (tool) | console-api |
|---|---|---|---|---|
| `POST /gate/evaluate` | ✓ | ✓ | ✓ | |
| `GET /gate/budgets/{tenant_id}/{date}` | | ✓ | ✓ | |
| `POST /gate/intents`, `:execute`, `:cancel` | | ✓ | | |
| `GET /gate/intents/{id}`, `GET /gate/intents` | ✓ | ✓ | | `GET /gate/intents/{id}` chỉ từ handler tra bằng chứng có ticket |
| `POST /gate/escrows` | ✓ | | | |
| `POST /gate/escrows/{id}:release`, `:refund` | | ✓ | | |
| `GET /gate/escrows/{id}` | ✓ | ✓ | | |

**Gate không tin dữ liệu trong request.** Request chỉ mang id. Gate tự đọc hóa đơn, approval, TK NCC, mandate, policy, kill switch, cảnh báo chéo, hard block từ DB (`core`, `control`, `risk`, chỉ-đọc), **suy ra tenant từ hóa đơn/PO** (request có `tenant_id` khác → `403 TENANT_MISMATCH`), rồi tự tính `intent_hash` theo [schemas.md §4](schemas.md#4-duyệt-và-chi).

## 1. Đánh giá thử

| Method | Path | Body → Kết quả |
|---|---|---|
| POST | `/gate/evaluate` | `{invoice_id}` hoặc (xem trước cọc) `{purchase_order_id, vendor_account_id, amount_vnd}` → `200 {decision: ALLOW \| REQUIRE_APPROVAL \| DENY, allowed_methods: [single \| bulk], verification_required, intent_hash, payee_account_id, amount_vnd, channel, reasons: [GateReason], evaluated_at}`. Không tác dụng phụ. **Kênh do Gate chọn**: hóa đơn có PO đang có escrow `held` → `escrow`; không thì theo `mandate.channel_rules`, mặc định `bank_transfer`. `Finding.proposed_channel` của treasury chỉ để hiển thị |

## 2. Payment intent

| Method | Path | Body → Kết quả |
|---|---|---|
| POST | `/gate/intents` | `{invoice_id, approval_id}` → `201 PaymentIntent (authorized)`, hoặc `422 GATE_DENIED` kèm intent `denied` (lưu để truy vết) và phát `payment.denied`. Gate kiểm approval: `status = active`, `job_id` = job hoàn tất mới nhất của hóa đơn, `intent_hash` khớp, `channel ≠ escrow` (escrow đi qua `:release`); với `bulk` kiểm lại mọi mã lý do nằm trong `bulk_approvable` của mandate **hiện hành**; với `mandate` kiểm lại toàn bộ điều kiện tự chi. Đã có intent `authorized/executing/settled` cho hóa đơn → `200` trả intent đó |
| POST | `/gate/intents/{payment_intent_id}:execute` | `{}` → `200 PaymentIntent` với `settled` \| `failed` \| `executing`. Ngay trước khi gọi rail, Gate **đánh giá lại toàn bộ** từ DB (cảnh báo chéo, hard block, kill switch, trạng thái hóa đơn, approval còn `active`); trượt → intent `denied`, phát `payment.denied`, trả `422 GATE_DENIED`. Đang `executing` → trả trạng thái, không gọi rail lần hai |
| POST | `/gate/intents/{payment_intent_id}:cancel` | `{reason: CROSS_ALERT \| INVOICE_REINVESTIGATED \| OWNER_CANCELLED}` → `PaymentIntent (expired)`, trả ngân sách ngày. Chỉ khi `authorized`; `executing` → `409 INVALID_STATE` (lần đánh giá lại trong `:execute` là chốt chặn cuối) |
| GET | `/gate/intents/{payment_intent_id}` | `PaymentIntent` |
| GET | `/gate/intents` | lọc `invoice_id`, `status` → trang `PaymentIntent` (tenant suy từ khóa service + bên gọi truyền `tenant_id`, Gate chỉ trả intent của tenant đó) |

Ràng buộc DB: **duy nhất một intent ở `authorized/executing/settled` cho mỗi hóa đơn** (partial unique index); **duy nhất một `ledger_entries` loại `settled` cho mỗi hóa đơn**. Intent `failed/denied/expired` không chặn lần chi sau, nhưng lần sau cần approval mới (core đã đặt approval cũ `superseded`).

Core-worker không tạo intent mới cho hóa đơn mà intent gần nhất `denied` cho tới khi trạng thái hóa đơn đổi (handler `payment.denied` đã đưa nó ra khỏi `scheduled`).

## 3. Escrow

| Method | Path | Body → Kết quả |
|---|---|---|
| POST | `/gate/escrows` | `{approval_id, expires_on}` → `201 Escrow` (`held`, hoặc `pending` nếu rail chưa trả lời sau 5 s). Gate đọc PO, TK nhận, số tiền, `source_invoice_id` **từ approval**; kiểm `amount_vnd ≤ PurchaseOrder.total_vnd`, TK `verified`/`escrow_only` thuộc NCC của PO, mỗi PO tối đa một escrow mở |
| POST | `/gate/escrows/{escrow_id}:release` | `{approval_id, goods_receipt_id}` → `Escrow (released)`. `approval_id` là approval của **hóa đơn giải ngân** (chủ chuỗi duyệt hóa đơn đó với `channel = escrow`, F7). Gate kiểm: phiếu nhập thuộc PO; hóa đơn cùng NCC, gắn PO, tổng ≤ cọc; approval `active`. Thiếu → `422 GATE_DENIED` |
| POST | `/gate/escrows/{escrow_id}:refund` | `{reason: EXPIRED \| ORDER_CANCELLED}` → `Escrow (refunded)` |
| GET | `/gate/escrows/{escrow_id}` | `Escrow` |

Luật cứng thêm: hóa đơn của NCC gắn PO đang có escrow `held` **chỉ được chi bằng `:release`**, không qua `/gate/intents`.

## 4. Ngân sách ngày

| Method | Path | Kết quả |
|---|---|---|
| GET | `/gate/budgets/{tenant_id}/{date}` | `{date, auto_pay_used_vnd, auto_pay_reserved_vnd, auto_pay_limit_vnd, total_paid_vnd}`; `auto_pay_limit_vnd` = min(mandate, trần nền tảng) |

## 5. Vòng nền của Gate

Tiến trình `gate` chạy một vòng nền mỗi 10 s:
- intent `executing`: hỏi `GET /sim/rails/transfers/{key}` (hoặc thẻ/escrow); có kết quả → ghi ledger + outbox. Quá 24 giờ chưa có kết quả → giữ `executing`, phát `payment.stuck` để vận hành xử lý tay. **Không bao giờ tự đánh dấu `failed`** khi chưa biết kết quả, vì tiền có thể đã đi.
- intent `authorized` quá 15 phút chưa execute → `expired` (`reason = AUTHORIZATION_TIMEOUT`).
- escrow `pending` → hỏi rail như trên.

## 6. Gate gọi ra ngoài

| Đích | Khi nào |
|---|---|
| `/sim/rails/*` qua port `PaymentRail`, `idempotency_key = payment_intent_id` hoặc `escrow_id` | execute, escrow, vòng nền |
| `GET /sim/scenario/clock` | chỉ khi `DEMO_MODE=true` (port `Clock`) |

Kết quả ghi `ledger_entries` và `ledger.outbox`. Gate **không gọi API của core**; core-worker đọc `ledger.outbox`.

Kênh `virtual_card`: `:execute` gọi `POST /sim/rails/cards` với `merchant_id` của TK NCC (`VendorAccount.kind = card_merchant`). v1 sim-world thu tiền ngay khi phát thẻ cho kịch bản phần mềm nên trả `settled` luôn.
