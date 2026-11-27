# Merchant API (`/m/*`, cổng 8001)

Trạng thái: **v0.2 (26/11/2026)**, đã sửa theo review. File OpenAPI: `contracts/openapi/core-merchant.yaml`.

Mọi endpoint cần `Authorization: Bearer <session_jwt>` (trừ `POST /m/auth/session`). Tenant lấy từ token, **không bao giờ** từ đường dẫn hay body. Cột **Vai**: O = owner, A = accountant, S = store_manager. S chỉ thấy hóa đơn, PO, phiếu nhập, sự kiện có `store_id` thuộc quán được gán; hóa đơn chưa gắn quán (`store_id = null`) S không thấy. **Step-up** = body phải có `auth_proof` hợp lệ cho đúng `action_hash` (cách tính ở [schemas.md §4](schemas.md#4-duyệt-và-chi)).

## 1. Phiên và xác thực mạnh

| Method | Path | Vai | Body → Kết quả |
|---|---|---|---|
| POST | `/m/auth/session` | — | `{momo_token}` → `{session_jwt, expires_at, user: User}`. Core kiểm `momo_token` với JWKS của bên định danh (demo: `GET /sim/identity/.well-known/jwks.json`) |
| GET | `/m/me` | O A S | `User` + `tenant {tenant_id, name}` + `permissions[]` |

Luồng step-up (một lần cho mỗi hành động nhạy cảm):
1. Client lấy `action_hash` từ endpoint xem trước tương ứng (approval-preview, batch preview, escrow-preview), hoặc tự tính bằng hàm dùng chung cho mandate, bot, NCC.
2. Client gọi bên định danh `POST /sim/identity/step-up-challenges {momo_token, action_hash}` rồi `:verify {otp}` → `auth_proof`. Ngoài đời đây là SDK sinh trắc/OTP của MoMo; core không giữ OTP.
3. Client gửi `auth_proof` trong body. Core kiểm chữ ký, `sub` = người dùng, `action_hash` = hash core tự tính lại, `amr` có yếu tố mạnh, `jti` chưa dùng, còn hạn.

## 2. Hóa đơn

**Trạng thái sau khi điều tra** (internal-api ghi lúc `:complete`):

| Màu | `auto_pay` (trong hạn mức, NCC trong danh sách, không bị tạm loại, trong khung giờ) | `auto_pay` (ngoài điều kiện) hoặc `ask_first` | `review_only` |
|---|---|---|---|
| 🟢 | `auto_pay_eligible` → core-worker tạo approval `mandate` → `approved` | `pending_approval` (duyệt hàng loạt được) | `pending_approval` |
| 🟡 | `pending_approval` | `pending_approval` | `pending_approval` |
| 🔴 | `blocked` | `blocked` | `blocked` |

`review_only` = PayMatch chỉ đối soát, không phát lệnh chi: `:approve`, `:schedule`, `:pay-now`, duyệt hàng loạt trả `409 INVALID_STATE code=MANDATE_REVIEW_ONLY`; chủ chuỗi tự trả bên ngoài và `:reject`/để nguyên.

| Method | Path | Vai | Body → Kết quả |
|---|---|---|---|
| POST | `/m/invoices:upload` | O A | multipart `file` (XML, PDF, ảnh), `message_text?` → `202 {invoice_id, job_id, status}`. Trước khi tạo mới, ingest kiểm **idempotency theo `(tenant_id, sha256)`**: nếu đúng cùng file đã nạp rồi → no-op, trả lại hóa đơn đã có (không tạo trùng, không gắn `DUPLICATE_INVOICE`). Nếu **file khác (`sha256` khác)** trùng khóa `(MST bán, ký hiệu, int(số))` → trả **`409 DUPLICATE_INVOICE`** kèm `existing_invoice_id`, **không lưu** (riêng kênh `email`/`bill_pay` mới lưu kèm `duplicate_of` và Finding đỏ `DUPLICATE_INVOICE` để giữ tín hiệu gian lận). XML không parse được → `422 XML_UNPARSEABLE`, không lưu. PDF/ảnh → lưu, gắn `NON_XML_SOURCE`, số tiền null cho tới khi nhập tay. Ngược lại ingest tạo hóa đơn (`investigating`) và job (`queued`) trong cùng transaction |
| PATCH | `/m/invoices/{invoice_id}/manual-fields` | O A, `If-Match` | `{seller_tax_id, symbol, number, issued_on, total_vnd, vat_total_vnd, lines?}` → `Invoice`. Chỉ cho hóa đơn có `NON_XML_SOURCE`; ghi `manual_fields.entered_by`; tạo job mới (approval cũ nếu có → `superseded`) |
| GET | `/m/invoices` | O A S | lọc `status`, `severity`, `vendor_id`, `store_id`, `reason_code`, `invoice_type`, `issued_from`, `issued_to`, `q` (ký hiệu/số) → trang `InvoiceSummary` |
| GET | `/m/invoices/{invoice_id}` | O A S | `Invoice` (có `ETag`) |
| GET | `/m/invoices/{invoice_id}/document` | O A | file gốc, đúng byte đã lưu, header `Digest: sha-256=…` |
| GET | `/m/invoices/{invoice_id}/findings` | O A | `[Finding]` của job hoàn tất mới nhất; `?job_id=` cho job cũ |
| GET | `/m/invoices/{invoice_id}/jobs` | O A | `[Job]` (mỗi lần điều tra lại là một job) |
| GET | `/m/invoices/{invoice_id}/approval-preview` | O | `ApprovalPreview` (kèm `job_id` của lần điều tra đang xem). Core gọi `POST /gate/evaluate`. Gate không trả lời → `503 UPSTREAM_UNAVAILABLE`, UI khóa nút Duyệt |
| POST | `/m/invoices/{invoice_id}:approve` | O, step-up | `{intent_hash, job_id, auth_proof, verification?}` → `200 {approval: Approval, invoice: InvoiceSummary}`. Chỉ khi `pending_approval`, hoặc `escrow_held` (hóa đơn 🔴 đã gỡ bằng cọc; chỉ kênh `escrow`). `job_id` khác job hoàn tất mới nhất → `409 INTENT_HASH_MISMATCH` (đã có kết quả điều tra mới). Hóa đơn gắn PO có escrow `held` → approval có `channel = escrow`, core-worker giải ngân khi đủ phiếu nhập. Lỗi khác: `409 INVALID_STATE`; `422 GATE_DENIED`; `403 STEP_UP_REQUIRED`; thiếu `verification` khi bắt buộc hoặc `result ≠ confirmed` → `400 VALIDATION_FAILED` field `verification`. Muốn trả ngay thì gọi `:pay-now` sau khi duyệt |
| POST | `/m/invoices/{invoice_id}:reject` | O | `{reason_code: PRICE_ABOVE_CONTRACT \| PACK_SIZE_CHANGED \| QUANTITY_ABOVE_NORM \| NO_GOODS_RECEIPT \| DUPLICATE_INVOICE \| OTHER, note?}` → `{invoice: InvoiceSummary, adjustment_request: AdjustmentRequest \| null}`. Từ `pending_approval`, `blocked`, `approved`, `scheduled` (hai trạng thái sau: hủy intent `authorized` trước) |
| GET | `/m/invoices/{invoice_id}/adjustment-request` | O A | `AdjustmentRequest`. Nội dung do **code** điền mẫu từ con số tool tính, không do LLM viết. Chủ chuỗi tự gửi (D3) |
| POST | `/m/invoices/{invoice_id}:schedule` | O A | `{scheduled_for: LocalDate}` → `InvoiceSummary`. Chỉ khi `approved` hoặc `scheduled` (đổi lịch) |
| POST | `/m/invoices/{invoice_id}:pay-now` | O | `{}` → `202 InvoiceSummary`. Chỉ khi `approved`/`scheduled`. Core đặt `scheduled_for` = hôm nay; core-worker chi ở lượt kế tiếp (merchant-api không gọi `/gate/intents`). Kết quả qua `GET /m/events` |
| POST | `/m/invoices/{invoice_id}:cancel-payment` | O | `{}` → `InvoiceSummary`. Từ `approved`/`scheduled` → `pending_approval`; approval → `superseded`; intent `authorized` → `POST /gate/intents/{id}:cancel {reason: OWNER_CANCELLED}`. Đang `paying` → `409 INVALID_STATE` |
| POST | `/m/invoices/{invoice_id}:reinvestigate` | O A | `{}` → `202 {job_id}`. Chỉ khi `pending_approval`, `blocked`, `approved`, `scheduled`, `payment_failed`. Hóa đơn → `investigating`, approval → `superseded`, intent `authorized` bị hủy (`INVOICE_REINVESTIGATED`). Gỡ 🔴 qua F12/F7 thì core tự điều tra lại |

`verification` dùng schema `Verification`; client **không gửi số điện thoại**, core hiển thị số lưu sẵn đã che trong `approval-preview`. `verification` nằm trong `payload_hash` của `auth_proof`.

## 3. Tiến trình điều tra

| Method | Path | Vai | Kết quả |
|---|---|---|---|
| GET | `/m/jobs/{job_id}` | O A | `Job` |
| GET | `/m/jobs/{job_id}/events` | O A | **SSE**. Sự kiện: `bot.started`, `bot.tool_called`, `bot.finished`, `bot.failed`, `job.completed`. Hỗ trợ `Last-Event-ID`. Đóng luồng sau `job.completed`. Chi tiết ở [events.md §3](events.md#3-sse) |
| GET | `/m/events` | O A S | **SSE** mức tenant: `invoice.status_changed`, `notification.created`, `payment.updated`. Cho hàng chờ tự cập nhật |

## 3a. Hỏi đáp với trợ lý (v1)

Người dùng hỏi bằng chữ; agent điều phối trả lời bằng dữ liệu của tenant (và chỉ quán của mình với S). Chỉ-đọc: trợ lý **không** duyệt, chi, sửa dữ liệu. Muốn làm gì thì trợ lý đưa `proposed_actions`, UI hiện nút dẫn tới đúng endpoint ở trên (vẫn step-up như thường).

| Method | Path | Vai | Body → Kết quả |
|---|---|---|---|
| POST | `/m/conversations` | O A S | `{title?, context?: {invoice_id?}}` → `201 Conversation` |
| GET | `/m/conversations` | O A S | trang `Conversation` của chính người dùng |
| GET | `/m/conversations/{conversation_id}` | O A S | `Conversation` + `messages: [Message]` |
| POST | `/m/conversations/{conversation_id}/messages` | O A S | `{text ≤ 2000 ký tự}` → `202 {message_id, reply_message_id, job_id}`. Tạo job `question`. Theo dõi câu trả lời qua SSE `GET /m/jobs/{job_id}/events` (`answer.delta`, rồi `job.completed`), sau đó `GET` hội thoại để lấy bản đã kiểm trích dẫn |
| POST | `/m/conversations/{conversation_id}:archive` | O A S | `{}` |
| POST | `/m/reports` | O A | `{kind: daily_summary \| spending_by_vendor \| spending_by_store \| price_changes, from, to}` → `202 {report_id, job_id}`. Job `report` |
| GET | `/m/reports/{report_id}` | O A | `Report` |

Câu hỏi người dùng là `trusted` (người trong tenant viết) nhưng câu trả lời luôn hiển thị như `untrusted` (LLM viết). Con số nào không trỏ được tới tool_call bị core gỡ và đánh dấu `unverified`.

## 4. Hàng chờ và duyệt hàng loạt

| Method | Path | Vai | Body → Kết quả |
|---|---|---|---|
| GET | `/m/approval-queue` | O A | `?group_by=vendor \| reason_code` → `{groups: [{key, label, count, total_vnd, bulk_approvable_count, invoices: [InvoiceSummary]}]}`. Chỉ gồm `pending_approval` và `blocked`. `label` là tên NCC từ registry hoặc tên mã lý do, không lấy chữ từ hóa đơn |
| POST | `/m/approval-batches:preview` | O | `{invoice_ids: [..] }` (≤ 200) → `201 ApprovalBatchPreview` (lưu 5 phút, có `preview_id`, `mandate_version`). Đủ điều kiện = 🟢 ở `ask_first`, hoặc 🟡 mà mọi mã lý do nằm trong `mandate.bulk_approvable` và dưới ngưỡng tiền. 🔴 và hóa đơn cần xác minh luôn bị loại |
| POST | `/m/approval-batches` | O, step-up | `{preview_id, auth_proof}` → `201 ApprovalBatch`. Danh sách duyệt = các mục `eligible` đã lưu trong preview; `action_hash` phủ `preview_id` + danh sách đó. Lúc ghi, core **kiểm lại** từng hóa đơn (hash, trạng thái, mandate còn cùng version); mandate đã đổi → `409 INVALID_STATE code=MANDATE_CHANGED`, xin preview mới. Mỗi approval ghi `mandate_version`; Gate kiểm lại lần nữa. Hóa đơn nào đổi hash từ lúc preview bị `excluded`, các hóa đơn còn lại vẫn duyệt |
| GET | `/m/approval-batches/{batch_id}` | O A | `ApprovalBatch` |
| GET | `/m/summaries/daily` | O A | `?date=` → `{date, auto_paid: {count, total_vnd}, bulk_approved, single_approved, pending: {count, total_vnd}, blocked_count, failed_payments: [InvoiceSummary]}` |

## 5. Mandate và tự chi

| Method | Path | Vai | Body → Kết quả |
|---|---|---|---|
| GET | `/m/platform-limits` | O A | `PlatformLimits` |
| GET | `/m/mandate` | O A | `Mandate` hiện hành, hoặc `404` nếu chưa ký (mặc định `review_only`) |
| GET | `/m/mandates` | O | lịch sử version |
| POST | `/m/mandates` | O, step-up | `{mode, limits, auto_pay_vendor_ids, channel_rules, bulk_approvable, auto_pay_window, auth_proof}` → `201 Mandate` (version mới). Vượt trần → `422 MANDATE_ABOVE_PLATFORM_CEILING`; `bulk_approvable` chứa mã đỏ → `422 VALIDATION_FAILED` |
| GET | `/m/auto-pay-suspensions` | O A | `[AutoPaySuspension]` đang hiệu lực (QT-03) |
| POST | `/m/auto-pay-suspensions/{vendor_id}:lift` | O, step-up | `{auth_proof}` → `AutoPaySuspension` |

## 6. Nhà cung cấp và tài khoản

| Method | Path | Vai | Body → Kết quả |
|---|---|---|---|
| GET | `/m/vendors` | O A | lọc `q`, `status` → trang `Vendor` |
| POST | `/m/vendors` | O, step-up | `{name, tax_id, phone_on_file, auth_proof}` → `201 Vendor` (chưa có TK). Tên/MST do bot `tax` đối chiếu khi điều tra hóa đơn đầu tiên. A soạn sẵn được ở UI nhưng chỉ O ghi |
| POST | `/m/vendors/{vendor_id}:change-phone` | O, step-up | `{phone_on_file, source_note, auth_proof}` → `Vendor`. SĐT lưu sẵn là mốc tin cậy của gọi lại xác minh nên chỉ đổi bằng xác thực mạnh; không bao giờ lấy từ hóa đơn/tin nhắn |
| GET | `/m/vendors/{vendor_id}` | O A | `Vendor` + `accounts: [VendorAccount]` + `contracts: [VendorContract]` |
| POST | `/m/vendors/{vendor_id}/account-changes` | O A | `{target_status: verified \| escrow_only, proposed_account: {bank_code, account_number, account_name}, origin}` → `201 VendorVerification (pending)`. Core kiểm `account_name` khớp tên tổ chức NCC; TK cá nhân → `422 VALIDATION_FAILED code=PERSONAL_ACCOUNT_NOT_ALLOWED` |
| GET | `/m/vendor-verifications` | O A | lọc `status`, `vendor_id` |
| GET | `/m/vendor-verifications/{verification_id}` | O A | `VendorVerification` |
| POST | `/m/vendor-verifications/{verification_id}:record-callback` | O A | `{result: confirmed \| not_reachable \| denied_by_vendor, note?}` → `VendorVerification`. Số đã gọi luôn là `phone_on_file`; client không gửi số. Bắt buộc với `target_status = verified` |
| POST | `/m/vendor-verifications/{verification_id}:approve` | O, step-up | `{auth_proof}` → `{verification, account: VendorAccount}`. `verified` cần callback `confirmed`, TK `verified` cũ chuyển `retired`, hóa đơn `blocked` vì `PAYEE_CHANGE_REQUEST` của NCC → điều tra lại. `escrow_only` cần ghi chú bằng chứng (`origin` + note), **không** đụng TK `verified` hiện có và không gỡ khóa hóa đơn. Phát `vendor_account.changed` |
| POST | `/m/vendor-verifications/{verification_id}:reject` | O | `{note?}` |
| GET | `/m/vendor-contracts` | O A | lọc `vendor_id` |
| POST | `/m/vendor-contracts` | O A | `{vendor_id, valid_from, valid_to?, items: [ContractItem không id]}` → `201 VendorContract (draft)` |
| POST | `/m/vendor-contracts/{contract_id}:activate` | O, step-up | `{auth_proof}` → `VendorContract (active)`. Hợp đồng cũ cùng NCC chồng thời gian → `ended`. Giá hợp đồng là mốc so giá cho tự chi nên chỉ chủ chuỗi kích hoạt |
| GET | `/m/vendor-contracts/{contract_id}` | O A | `VendorContract` |

## 7. Chứng từ vận hành

| Method | Path | Vai | Body → Kết quả |
|---|---|---|---|
| GET | `/m/stores` | O A S | `[Store]` (S chỉ thấy quán của mình) |
| GET | `/m/purchase-orders` | O A S | lọc `vendor_id`, `store_id`, `status` |
| POST | `/m/purchase-orders` | O A S | `{vendor_id, store_id, lines}` → `201 PurchaseOrder`. Core tính `total_vnd` |
| GET | `/m/purchase-orders/{purchase_order_id}` | O A S | `PurchaseOrder` + `goods_receipts` + `invoices` liên quan |
| POST | `/m/purchase-orders/{purchase_order_id}:cancel` | O A | `{reason}` → `PurchaseOrder (cancelled)`. Có escrow `held` → core-worker `:refund {reason: ORDER_CANCELLED}`. Đã có phiếu nhập → `409 INVALID_STATE` |
| POST | `/m/goods-receipts` | S (quán của mình), O | `{purchase_order_id, store_id, lines}` → `201 GoodsReceipt`. Phát `goods_receipt.confirmed`; core-worker kiểm điều kiện giải ngân escrow và điều tra lại hóa đơn đang chờ `NO_GOODS_RECEIPT` |
| GET | `/m/goods-receipts` | O A S | lọc `purchase_order_id`, `store_id` |
| POST | `/m/expense-records` | O A | `{store_id?, amount_vnd, payee_name, reason, spent_on}` → `201 ExpenseRecord`. Không bao giờ sinh lệnh chi (QT-05) |
| GET | `/m/expense-records` | O A | lọc `month=YYYY-MM` → trang + `{month_total_vnd}` để lập bảng kê |
| GET | `/m/wallet` | O A | `{balance_vnd, as_of}` (core đọc `GET /sim/rails/wallets/{wallet_id}`) |

## 8. Cọc tạm giữ (F7)

| Method | Path | Vai | Body → Kết quả |
|---|---|---|---|
| POST | `/m/escrows` | O, step-up | `{purchase_order_id, vendor_account_id, amount_vnd, expires_on, source_invoice_id?, auth_proof}` → `201 Escrow` (`held` hoặc `pending`). `amount_vnd ≤ PO.total_vnd`. `source_invoice_id` = hóa đơn 🔴 dẫn tới cọc; nó chuyển `escrow_held` khi nhận `escrow.held`. Core tạo approval (`purchase_order_id`, `method = single`, `channel = escrow`, số tiền, TK) rồi gọi `POST /gate/escrows {approval_id, expires_on}`. `action_hash` lấy từ `POST /gate/evaluate` dạng escrow, trả qua `GET /m/purchase-orders/{purchase_order_id}/escrow-preview`. `vendor_account_id` phải ở `verified` hoặc `escrow_only` và thuộc NCC của PO |
| GET | `/m/purchase-orders/{purchase_order_id}/escrow-preview` | O | `?vendor_account_id=&amount_vnd=` → `{intent_hash, action_hash, gate_decision, gate_reasons, expires_at}` |
| GET | `/m/escrows` | O A | lọc `status`, `vendor_id` |
| GET | `/m/escrows/{escrow_id}` | O A | `Escrow` |

Giải ngân: khi NCC gửi hóa đơn giao hàng cho PO, hóa đơn đó được điều tra bình thường và chủ chuỗi **duyệt nó** (`:approve`, kênh `escrow`). Khi có cả approval đó và phiếu nhập, core-worker gọi `POST /gate/escrows/{id}:release {approval_id, goods_receipt_id}`; hóa đơn giải ngân → `paid`. Nếu hóa đơn 🔴 ban đầu chính là hóa đơn giao hàng thì nó là hóa đơn giải ngân (sau khi gỡ nguyên nhân bằng escrow, F7); nếu khác, hóa đơn ban đầu → `rejected`. Hoàn cọc: core-worker khi quá `expires_on` hoặc PO bị hủy; hóa đơn ban đầu → `rejected`.

## 9. Bot và skill (F5)

| Method | Path | Vai | Body → Kết quả |
|---|---|---|---|
| GET | `/m/tools` | O A | `[ToolDefinition]` = registry ∩ `tool_grants` của tenant (không có handler) |
| GET | `/m/reason-codes` | O A | `[{code, floor_severity, ceiling_severity \| null, qt03: boolean, description}]` |
| GET | `/m/skills` | O A | skill hệ thống + của tenant |
| POST | `/m/skills` | O A | `{name, content_md}` → `201 Skill (version 1)` |
| POST | `/m/skills/{skill_id}/versions` | O A | `{content_md}` → `201 Skill` |
| GET | `/m/bots` | O A | bot hệ thống + của tenant, kèm `required_for`, trạng thái |
| POST | `/m/bots` | O A | `{manifest: BotManifest}` → `201 Bot (draft)` |
| GET | `/m/bots/{bot_id}` | O A | `Bot` + lịch sử version |
| POST | `/m/bots/{bot_id}/versions` | O A | `{manifest}` → `201 Bot` (version mới ở `draft`; version đang `active` vẫn chạy) |
| POST | `/m/bots/{bot_id}:submit` | O A | `{}` → `Bot (pending_review)` hoặc `422 BOT_MANIFEST_INVALID {errors: [BotValidationError]}` |
| POST | `/m/bots/{bot_id}:approve` | O, step-up | `{version, auth_proof}` → `Bot (active)` |
| POST | `/m/bots/{bot_id}:reject` | O | `{version, note?}` → `Bot (draft)` |
| POST | `/m/bots/{bot_id}:disable` | O | `{}`. Bot bắt buộc (`required_for`) hoặc `scope = system` → `409 INVALID_STATE` |
| POST | `/m/bots/{bot_id}:enable` | O | `{}` |
| POST | `/m/bots/{bot_id}:archive` | O | `{}` (thay cho xóa) |

## 10. Thông báo

| Method | Path | Vai | Kết quả |
|---|---|---|---|
| GET | `/m/notifications` | O A S | lọc `unread=true` → trang `Notification` |
| POST | `/m/notifications/{notification_id}:read` | O A S | `204` |

## 11. Demo

| Method | Path | Điều kiện | Tác dụng |
|---|---|---|---|
| POST | `/m/demo:reset` | `DEMO_MODE=true`, vai O | Xóa dữ liệu tenant demo, nạp lại seed, gọi `POST /sim/scenario:reset`. Ngoài demo endpoint này **không được mount** |
