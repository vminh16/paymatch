# Mô hình dữ liệu

Trạng thái: **Đã chốt mức thiết kế (26/11/2026)**. Cột chi tiết chốt khi viết migration.

## 1. Nguyên tắc

- **Core chỉ lưu những gì PayMatch sở hữu.** Dữ liệu của hệ thống bên ngoài (thuế, SIMO, email, Zalo, doanh thu MoMo) đọc qua tool, không sao chép thành bảng nghiệp vụ.
- **Mọi lần gọi tool được lưu làm bằng chứng** (`tool_calls`): input, output, provenance, thời điểm. Tra lại sau 3 tháng vẫn thấy đúng thứ bot đã thấy.
- **File gốc bất biến**: hóa đơn gốc lưu kèm hash; bản ghi chuẩn hóa trỏ về file gốc.
- **Mỗi schema có đúng một service được ghi.** Mọi bảng nghiệp vụ có `tenant_id`; RLS bắt buộc với role `merchant`.
- **Không xóa cứng** dữ liệu nghiệp vụ: dùng trạng thái (`archived`, `disabled`) hoặc bản ghi bù.
- **Có version** cho thứ được tham chiếu về sau: mandate, bot, skill, policy.

## 2. Schema

### `core` (ghi: core)

| Nhóm | Bảng | Ghi chú |
|---|---|---|
| Tổ chức | `tenants`, `stores`, `users` | `stores` = chi nhánh/quán; `users.role`: `owner \| accountant \| store_manager` (chỉ `owner` duyệt, D4) |
| Nhà cung cấp | `vendors`, `vendor_accounts`, `vendor_verifications` | `vendor_accounts.status`: `verified \| escrow_only \| retired` (D7); TK + SĐT lưu sẵn; mọi thay đổi TK qua `vendor_verifications` (ai đề xuất, ai duyệt, đã gọi lại số nào) |
| Hợp đồng | `vendor_contracts`, `contract_items` | sku, đơn vị cơ sở, quy cách, đơn giá/đơn vị; `status: draft \| active \| ended`, chỉ chủ chuỗi kích hoạt |
| Hóa đơn | `invoice_documents`, `invoices`, `invoice_lines`, `invoice_messages` | `invoice_documents`: file gốc + sha256 + định dạng; `invoice_messages`: thân email/ghi chú đi kèm (untrusted); khóa chống trùng `(seller_tax_id, symbol, number)` |
| Chứng từ | `purchase_orders`, `goods_receipts`, `payables`, `expense_records` | phiếu nhập do quản lý quán xác nhận; `expense_records` = khoản chi không hóa đơn (QT-05, chỉ ghi nhận) |
| Điện nước | `utility_accounts`, `utility_readings` | lịch sử theo quán |
| Điều tra | `jobs`, `tool_calls`, `findings`, `bot_answers`, `briefs` | `jobs` có `task_type`, lease, attempt; `findings` ghi `bot_version`, `skill_version`, `prompt_hash` |
| Duyệt | `mandates`, `auto_pay_suspensions`, `approvals` | `mandates` có version, ký bằng xác thực mạnh; `approvals` nhiều dòng theo thời gian, tối đa một dòng `active` cho mỗi hóa đơn (cọc: theo PO, `invoice_id` null); có `status`, `job_id`, `amount_vnd`, `payee_account_id`, `channel`; `intent_hash`, `method: single \| bulk \| mandate`, `bulk_batch_id`, `verification`; `auto_pay_suspensions`: NCC tạm loại khỏi tự chi (QT-03) |
| Hội thoại | `conversations`, `conversation_messages`, `reports` | câu trả lời lưu kèm `citations`, `unverified_values`, `proposed_actions`; theo người dùng |
| Memory *(lộ trình)* | `bot_memories`, `memory_proposals` | xem [agent-lifecycle-and-memory.md](../03-agents/agent-lifecycle-and-memory.md) |
| Hạ tầng | `outbox`, `audit_events` | `audit_events` chỉ ghi thêm; role `staff` chỉ có `INSERT` trên `outbox` |

### `control` (ghi: core — console-api, hệ thống; merchant-api chỉ ghi bot/skill của tenant mình, RLS)

| Bảng | Ghi chú |
|---|---|
| `tools` | registry, đồng bộ từ code (id, mô tả, schema in/out, provenance, scope) |
| `tool_grants` | tool nào bật cho tenant nào |
| `bot_definitions`, `bot_versions` | scope `system \| tenant` (lộ trình: `marketplace`); trạng thái vòng đời; `required_for` |
| `skills`, `skill_versions` | nội dung markdown có version |
| `policies` | policy nền tảng + kill switch (phạm vi, người đề xuất, người duyệt) |
| `model_configs` | model chính, dự phòng, giới hạn |
| `staff_users`, `staff_roles` | RBAC console |

### `risk` (ghi: core qua console-api và core-worker)

`indicators` (`account_hash`, `tax_id`, `phone`, `card_id`, `merchant_id`) · `hard_blocks` (Gate đọc) · `alerts` · `cases` · `case_actions` (maker-checker) · `cross_alerts` · `access_log` · bảng read model cho console.

### `ledger` (ghi: chỉ payment-gate)

`payment_intents` (state machine, `intent_hash`; unique `invoice_id` **chỉ trên** `authorized | executing | settled`, và một `ledger_entries` settled cho mỗi hóa đơn; escrow gắn `purchase_order_id`) · `payment_tokens` (dùng một lần) · `ledger_entries` (chỉ ghi thêm) · `escrows` · `daily_budgets` (khóa dòng theo tenant + ngày) · `rail_transactions` (tham chiếu phía rail) · `outbox` (sự kiện `payment.*`, `escrow.*`; core-worker đọc) · `reconciliations` *(lộ trình)*.

## 3. Không lưu trong Postgres

| Dữ liệu | Ở đâu |
|---|---|
| Trace agent (OpenTelemetry) | OTel collector |
| Dữ liệu thế giới bên ngoài | sim-world (bộ nhớ, nạp từ JSON) |
| Prompt khung an toàn | git (`services/agent-runtime/prompts/`) |
| Skill/manifest bot có sẵn | git (`plugins/bots/`), đồng bộ vào `control` khi khởi động |
