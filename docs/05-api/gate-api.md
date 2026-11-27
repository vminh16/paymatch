# Payment Gate API (`/gate/*`, cổng 8100)

Trạng thái: **v0.2 (26/11/2026)**, đã sửa theo review. File OpenAPI: `contracts/openapi/gate.yaml`. Luật và state machine ở [payment-gate.md](../02-architecture/payment-gate.md).

Mọi endpoint nghiệp vụ cần `X-Service-Key`, khóa riêng cho từng bên gọi; endpoint nghiệp vụ ngoài cột của bên gọi trong bảng dưới (được khai báo máy đọc được qua `x-allowed-callers` trên từng operation trong `contracts/openapi/gate.yaml`) → `403`. Riêng probe sống/sẵn sàng `GET /gate/healthz` và `GET /gate/readyz` không cần khóa (theo [README.md §1](README.md#1-tiến-trình-và-cổng)). `agent-worker` không có khóa Gate.

| Endpoint | merchant-api | core-worker | internal-api (tool) | console-api |
|---|---|---|---|---|
| `POST /gate/evaluate` | ✓ | ✓ | ✓ | |
| `GET /gate/budgets/{tenant_id}/{date}` | | ✓ | ✓ | |
| `POST /gate/intents`, `:execute`, `:cancel` | | ✓ | | |
| `GET /gate/intents/{id}`, `GET /gate/intents` | ✓ | ✓ | | `GET /gate/intents/{id}` chỉ từ handler tra bằng chứng có ticket |
| `POST /gate/escrows` | ✓ | | | |
| `POST /gate/escrows/{id}:release`, `:refund` | | ✓ | | |
| `GET /gate/escrows/{id}` | ✓ | ✓ | | |

**Gate không tin dữ liệu trong request.** Request chỉ mang id (cùng `tenant_id?` tùy chọn để đối chiếu chéo). Gate tự đọc hóa đơn, approval, TK NCC, mandate, policy, kill switch, cảnh báo chéo, hard block từ DB (`core`, `control`, `risk`, chỉ-đọc), **suy ra tenant từ hóa đơn/PO** (request có `tenant_id` khác → `403 TENANT_MISMATCH`), rồi tự tính `intent_hash` theo [schemas.md §4](schemas.md#4-duyệt-và-chi).

## 1. Đánh giá thử

| Method | Path | Body → Kết quả |
|---|---|---|
| POST | `/gate/evaluate` | `{invoice_id, tenant_id?}` hoặc (xem trước cọc) `{purchase_order_id, vendor_account_id, amount_vnd, tenant_id?}` → `200 {decision: ALLOW \| REQUIRE_APPROVAL \| DENY, allowed_methods: [single \| bulk], verification_required, intent_hash, payee_account_id: string \| null, amount_vnd, channel, reasons: [GateReason], evaluated_at}` (`payee_account_id` chỉ `null` khi `decision = DENY` và NCC chưa có TK trong registry). Không tác dụng phụ. **Kênh do Gate chọn**: hóa đơn có PO đang có escrow `held` → `escrow`; không thì theo `mandate.channel_rules`, mặc định `bank_transfer`. `Finding.proposed_channel` của treasury chỉ để hiển thị |

## 2. Payment intent

| Method | Path | Body → Kết quả |
|---|---|---|
| POST | `/gate/intents` | `{invoice_id, approval_id}` → `201 PaymentIntent (authorized)`, hoặc `422 GATE_DENIED` kèm intent `denied` (lưu để truy vết) và phát `payment.denied`. Gate kiểm approval: `status = active`, `job_id` = job hoàn tất mới nhất của hóa đơn, `intent_hash` khớp, `channel ≠ escrow` (escrow đi qua `:release`); với `bulk` kiểm lại mọi mã lý do nằm trong `bulk_approvable` của mandate **hiện hành**; với `mandate` kiểm lại toàn bộ điều kiện tự chi. Đã có intent `authorized/executing/settled` cho hóa đơn → `200` trả intent đó |
| POST | `/gate/intents/{payment_intent_id}:execute` | `{}` → `200 PaymentIntent` với `settled` \| `failed` \| `executing`. Ngay trước khi gọi rail, Gate **đánh giá lại toàn bộ** từ DB (cảnh báo chéo, hard block, kill switch, trạng thái hóa đơn, approval còn `active`); trượt → intent `denied`, phát `payment.denied`, trả `422 GATE_DENIED`. Đang `executing` → trả trạng thái, không gọi rail lần hai |
| POST | `/gate/intents/{payment_intent_id}:cancel` | `{reason: CROSS_ALERT \| INVOICE_REINVESTIGATED \| OWNER_CANCELLED}` → `PaymentIntent (expired)`, trả ngân sách ngày. Chỉ khi `authorized`; `executing` → `409 INVALID_STATE` (lần đánh giá lại trong `:execute` là chốt chặn cuối) |
| GET | `/gate/intents/{payment_intent_id}` | `PaymentIntent` |
| GET | `/gate/intents` | `?tenant_id=` (bắt buộc), lọc `invoice_id`, `status` → trang `PaymentIntent` (khóa service xác định bên gọi `merchant-api`/`core-worker`; bên gọi bắt buộc truyền `tenant_id`, Gate chỉ trả intent của tenant đó) |

Ràng buộc DB: **duy nhất một intent ở `authorized/executing/settled` cho mỗi hóa đơn** (partial unique index); **duy nhất một `ledger_entries` loại `settled` cho mỗi hóa đơn**. Intent `failed/denied` không chặn lần chi sau, nhưng lần sau cần approval mới (core đã đặt approval cũ `superseded`). Riêng intent `expired` do `AUTHORIZATION_TIMEOUT`: nếu `approval` của hóa đơn vẫn còn `active` và chưa hết hạn thì core-worker đưa hóa đơn về `scheduled` để ủy quyền lại bằng chính approval đó; ngược lại đặt approval `superseded` (nếu còn `active`) và CAS hóa đơn về `pending_approval` để chủ chuỗi duyệt lại (khớp [events.md §2](events.md#2-danh-mục)).

Core-worker không tạo intent mới cho hóa đơn mà intent gần nhất `denied` cho tới khi trạng thái hóa đơn đổi (handler `payment.denied` đã đưa nó ra khỏi `scheduled`).

## 3. Escrow

| Method | Path | Body → Kết quả |
|---|---|---|
| POST | `/gate/escrows` | `{approval_id, expires_on}` → `201 Escrow` (`held`, hoặc `pending` nếu rail chưa trả lời sau 5 s), hoặc `200 Escrow` nếu `approval_id` đã từng tạo cọc trước đó (trả nguyên bản ghi `Escrow` gốc ở **mọi trạng thái**). Gate đọc PO, TK nhận, số tiền, `source_invoice_id` **từ approval**; kiểm `amount_vnd ≤ PurchaseOrder.total_vnd`, TK `verified`/`escrow_only` thuộc NCC của PO, mỗi PO tối đa một escrow đang mở (`pending`/`held`). **Một `approval_id` chỉ cấp vốn cho tối đa một escrow vĩnh viễn** (`UNIQUE approval_id → escrow_id`); sau khi cọc hết hạn/hoàn (`refunded`) hoặc thất bại (`failed`), tạo cọc mới bắt buộc phải có `approval_id` mới |
| POST | `/gate/escrows/{escrow_id}:release` | `{approval_id, goods_receipt_id}` → `200 Escrow (released)`. `approval_id` là approval `active` của job hoàn tất mới nhất cho **hóa đơn giải ngân** (chủ chuỗi duyệt hóa đơn đó với `channel = escrow`, F7). Gate kiểm lại toàn bộ từ DB: `goods_receipt_id` thuộc đúng PO của cọc; hóa đơn giải ngân cùng NCC, gắn PO, không `blocked`; `intent_hash` của approval khớp bản hiện tại; **số tiền đã duyệt (`approval.amount_vnd`) PHẢI BẰNG số tiền cọc đang giữ (`escrow.amount_vnd`) VÀ tài khoản nhận đã duyệt (`approval.payee_account_id`) PHẢI BẰNG tài khoản của cọc (`escrow.vendor_account_id`)**; đồng thời đánh giá lại đầy đủ policy (kill switch → `423`, `risk.hard_blocks`, `risk.cross_alerts` chưa xác minh gọi lại, SIMO). Sai lệch số tiền / tài khoản / PO / phiếu nhập / hóa đơn so với cọc → `422 GATE_DENIED` với mã `ESCROW_MISMATCH`; trượt approval/policy → `422 GATE_DENIED` (hoặc `423 KILL_SWITCH_ACTIVE`) |
| POST | `/gate/escrows/{escrow_id}:refund` | `{reason: EXPIRED \| ORDER_CANCELLED}` → `200 Escrow (refunded)` |
| GET | `/gate/escrows/{escrow_id}` | `Escrow` |

Ràng buộc DB: **duy nhất một escrow cho mỗi `approval_id`** (`UNIQUE (approval_id)` ánh xạ `approval_id → escrow_id` vĩnh viễn) và **tối đa một escrow đang mở (`pending`/`held`) cho mỗi PO** (partial unique index). Luật cứng thêm: hóa đơn của NCC gắn PO đang có escrow `held` **chỉ được chi bằng `:release`**, không qua `/gate/intents`.

## 4. Ngân sách ngày

| Method | Path | Kết quả |
|---|---|---|
| GET | `/gate/budgets/{tenant_id}/{date}` | `{date, auto_pay_used_vnd, auto_pay_reserved_vnd, auto_pay_limit_vnd, total_paid_vnd}`; `auto_pay_limit_vnd` = min(mandate, trần nền tảng) |

## 5. Vòng nền của Gate

Tiến trình `gate` chạy một vòng nền mỗi 10 s:
- intent `executing`: với `bank_transfer` hỏi `GET /sim/rails/transfers/{payment_intent_id}`; với `virtual_card` gọi lại `POST /sim/rails/cards` với **cùng `idempotency_key` (`payment_intent_id`) và cùng body** (idempotent status lookup); có kết quả → ghi ledger + outbox. Quá 24 giờ chưa có kết quả → giữ `executing`, phát `payment.stuck` để vận hành xử lý tay. **Không bao giờ tự đánh dấu `failed`** khi chưa biết kết quả, vì tiền có thể đã đi.
- intent `authorized` quá 15 phút chưa execute → `expired` (`reason = AUTHORIZATION_TIMEOUT`), phát `payment.expired`. Core-worker chỉ ủy quyền lại nếu approval của hóa đơn vẫn còn `active` và chưa hết hạn; ngược lại CAS hóa đơn về `pending_approval` để duyệt lại.
- escrow `pending` → gọi lại `POST /sim/rails/escrows` với **cùng `idempotency_key` (`escrow_id`) và cùng body** (idempotent status lookup) để nhận trạng thái gốc từ rail.

## 6. Gate gọi ra ngoài

| Đích | Khi nào |
|---|---|
| `/sim/rails/*` qua port `PaymentRail`, với `idempotency_key`: `payment_intent_id` (`pi_…`) cho chuyển khoản/thẻ ảo; `escrow_id` (`esc_…`) cho giữ cọc; `rel_<escrow_id>` cho `:release`; `ref_<escrow_id>` cho `:refund`. Gọi lại `POST` cùng `idempotency_key` và cùng body là cơ chế tra trạng thái cho thẻ ảo và cọc (khớp [sim-world-api.md §2](sim-world-api.md#2-hạ-tầng-thanh-toán-simrails-chỉ-gate-gọi-trừ-wallets)) | execute, escrow, vòng nền |
| `GET /sim/scenario/clock` | chỉ khi `DEMO_MODE=true` (port `Clock`) |

Kết quả ghi `ledger_entries` và `ledger.outbox`. Gate **không gọi API của core**; core-worker đọc `ledger.outbox`.

Kênh `virtual_card`: `:execute` gọi `POST /sim/rails/cards` với `merchant_id` của TK NCC (`VendorAccount.kind = card_merchant`). v1 sim-world thu tiền ngay khi phát thẻ cho kịch bản phần mềm nên trả `settled` luôn.
