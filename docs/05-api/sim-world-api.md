# sim-world API (`/sim/*`, cổng 8200)

Trạng thái: **v0.2 (26/11/2026)**. Chỉ là **giả lập**: dữ liệu nạp từ JSON, không nối hệ thống thật nào; giữ API đủ gọn để demo chạy. File OpenAPI: `contracts/openapi/sim-world.yaml`. Chỉ chạy ở demo/test. Mỗi nhóm dưới đây là **một adapter** phía core/gate; triển khai thật thay adapter bằng hệ thống thật, giữ nguyên port.

Xác thực: `X-Service-Key` (khóa riêng cho core và cho gate). Ngoại lệ: `/sim/identity/*` và `/sim/scenario/*` mở cho trình duyệt khi `DEMO_MODE=true` (bảng điều khiển demo và màn hình OTP giả).

Dữ liệu nạp từ `services/sim-world/data/` vào bộ nhớ; `POST /sim/scenario:reset` nạp lại. Mọi tenant/NCC/TK/MST trong sim-world đều giả (xem [docs/04-data/README.md](../04-data/README.md) và đặc tả bộ dữ liệu [docs/04-data/sim-world-dataset.md](../04-data/sim-world-dataset.md)).

## 1. Định danh: `/sim/identity` (thay MoMo ID và SSO nhân viên)

| Method | Path | Ai gọi | Body → Kết quả |
|---|---|---|---|
| GET | `/sim/identity/.well-known/jwks.json` | core | khóa công khai để kiểm `momo_token`, `sso_token`, `auth_proof` |
| POST | `/sim/identity/merchant-tokens` | trình duyệt (demo) | `{user_id}` (người dùng seed) → `{momo_token}` |
| POST | `/sim/identity/staff-tokens` | trình duyệt (demo) | `{staff_id}` → `{sso_token}` |
| POST | `/sim/identity/step-up-challenges` | trình duyệt | `{momo_token, action_hash}` → `{challenge_id, expires_at, demo_otp}` (`demo_otp` chỉ có ở demo; ngoài đời gửi qua app) |
| POST | `/sim/identity/step-up-challenges/{challenge_id}:verify` | trình duyệt | `{otp}` → `{auth_proof}` (JWT: `sub`, `action_hash`, `jti`, `exp` = 5 phút, `amr: ["otp"]`) |

## 2. Hạ tầng thanh toán: `/sim/rails` (chỉ Gate gọi, trừ `wallets`)

| Method | Path | Ai gọi | Body → Kết quả |
|---|---|---|---|
| POST | `/sim/rails/transfers` | gate | `{idempotency_key, from_wallet_id, to: {bank_code, account_number, account_name}, amount_vnd, memo}` → `{rail_txn_id, status: settled \| failed, failure_code: INSUFFICIENT_FUNDS \| ACCOUNT_NOT_FOUND \| NAME_MISMATCH \| RAIL_DOWN \| null, settled_at}`. Cùng key → cùng kết quả |
| GET | `/sim/rails/transfers/{idempotency_key}` | gate | trạng thái (dùng khi timeout) |
| POST | `/sim/rails/cards` | gate | `{idempotency_key, from_wallet_id, merchant_id, amount_vnd, single_use: true}` → `{card_id, last4, status: issued \| captured}` |
| GET | `/sim/rails/cards/{card_id}` | gate | `{card_id, status: issued \| captured \| declined_attempts, captures: [..]}` |
| POST | `/sim/rails/escrows` | gate | `{idempotency_key, from_wallet_id, to: {...}, amount_vnd, expires_on}` → `{rail_escrow_id, status: held}` |
| POST | `/sim/rails/escrows/{rail_escrow_id}:release` | gate | `{idempotency_key}` → `{status: released}` |
| POST | `/sim/rails/escrows/{rail_escrow_id}:refund` | gate | `{idempotency_key}` → `{status: refunded}` |
| GET | `/sim/rails/wallets/{wallet_id}` | core (tool `account_balance`, `/m/wallet`) | `{wallet_id, balance_vnd, as_of}` |

Sự kiện phía rail (thẻ bị quẹt sai, chuyển khoản xong) được sim-world đẩy về `POST /internal/webhooks/rails`.

## 3. Nguồn hóa đơn

| Method | Path | Ai gọi | Body → Kết quả |
|---|---|---|---|
| GET | `/sim/inbox/messages` | core-worker (nhận hóa đơn), tool `inbox` | `?mailbox=<địa chỉ nhận hóa đơn của tenant>&after=<cursor>&from=?` → `{items: [{message_id, from, subject, body_text, received_at, attachments: [{attachment_id, filename, content_type, size}]}], next_cursor}` |
| GET | `/sim/inbox/messages/{message_id}/attachments/{attachment_id}` | core-worker | byte gốc của file (XML/PDF) |
| GET | `/sim/bills` | core-worker | `?wallet_id=&after=<cursor>` → hóa đơn điện nước mới: `{items: [{bill_id, provider: electricity \| water, customer_code, store_ref, period, amount_vnd, readings: {...}, xml_attachment_id \| null}], next_cursor}` |
| GET | `/sim/bills/{bill_id}/document` | core-worker | XML hóa đơn điện nước (nếu có) |

## 4. Tin nhắn: `/sim/chat` (thay Zalo)

| Method | Path | Ai gọi | Kết quả |
|---|---|---|---|
| GET | `/sim/chat/threads` | tool `chat_messages` | `?tenant_ref=&counterparty_phone=?` → `[{thread_id, counterparty_name, counterparty_phone}]` |
| GET | `/sim/chat/threads/{thread_id}/messages` | tool `chat_messages` | `?since=` → `[{message_id, from: tenant \| counterparty, text, sent_at}]` |

## 5. Tra cứu chính thức

| Method | Path | Ai gọi | Kết quả |
|---|---|---|---|
| GET | `/sim/einvoice/invoices` | tool `einvoice_portal` | `?seller_tax_id=&symbol=&number=` (chuẩn hóa `number` theo số nguyên) → `{found: boolean, invoice_status_code: 1..6 \| null, invoice_status_label: string \| null, processing_status_code: 0..8 \| null, processing_status_label: string \| null, illegal_flag: boolean \| null, tax_authority_code: string \| null, total_vnd: MoneyVnd \| null, related_invoice: {symbol, number, issued_on} \| null}` |
| GET | `/sim/tax/taxpayers/{tax_id}` | tool `tax_id_lookup` | `{tax_id, name, status_code: "00" \| "01" \| "02" \| "03" \| "04" \| "05" \| "06" \| "07" \| "09" \| "10", status_label, status_reason_code: string \| null, address}`; không có → `404` |
| GET | `/sim/tax/risk-list/{tax_id}` | tool `tax_risk_list` | `{listed: boolean, list_name \| null, listed_on \| null}` |
| GET | `/sim/simo/indicators:check` | tool `official_fraud_list`, console-api (`propose_hard_block`) | `?kind=account_hash \| phone \| tax_id&value_hash=` → `{listed: boolean, list_ref \| null}` |
| GET | `/sim/revenue` | tool `momo_revenue` | `?wallet_id=&store_ref=&month=YYYY-MM` → `{revenue_vnd, transaction_count}` |

**Danh mục mã tra cứu thuế dùng trong `/sim/tax` và `/sim/einvoice`** (đồng bộ từ `TT 90/2026/TT-BTC` và cổng live `hoadondientu.gdt.gov.vn`, xem [tools.md §4a](../03-agents/tools.md#4a-quy-ước-tra-cứu-thuế-tax_id_lookup-einvoice_portal-tax_risk_list)):

- **10 mã `status_code` MST (`tracuunnt.gdt.gov.vn`, Phụ lục I `TT 90/2026` — không có mã `"08"`, `"08"` là `status_reason_code` *"Đã phá sản"* dưới trạng thái `"01"`):**
  - `"00"` Đang hoạt động · `"01"` Ngừng hoạt động, đã chấm dứt hiệu lực MST · `"02"` Đã chuyển CQT quản lý · `"03"` Ngừng hoạt động, chưa chấm dứt hiệu lực MST · `"04"` Hết hiệu lực *(trước đây: HKD/cá nhân KD chưa đủ thông tin ĐKT)* · `"05"` Tạm ngừng hoạt động, kinh doanh · `"06"` Không hoạt động tại địa chỉ đã đăng ký · `"07"` Chờ làm thủ tục phá sản · `"09"` Chờ xác minh tình trạng hoạt động tại địa chỉ đã đăng ký · `"10"` MST chờ cập nhật số định danh cá nhân.
- **6 mã `invoice_status_code` (`tthai` trên `hoadondientu.gdt.gov.vn`):** `1` Hóa đơn mới · `2` Hóa đơn thay thế · `3` Hóa đơn điều chỉnh · `4` Hóa đơn đã bị thay thế · `5` Hóa đơn đã bị điều chỉnh · `6` Hóa đơn đã bị hủy.
- **9 mã `processing_status_code` (`ttxly` trên `hoadondientu.gdt.gov.vn`):** `0` Cục Thuế đã nhận · `1` Đang kiểm tra điều kiện cấp mã · `2` CQT từ chối HĐ từng lần phát sinh · `3` Đủ điều kiện cấp mã · `4` Không đủ điều kiện cấp mã · `5` Đã cấp mã hóa đơn · `6` Cục Thuế đã nhận không mã · `7` Đã kiểm tra định kỳ HĐĐT không mã · `8` Cục Thuế đã nhận HĐ có mã từ máy tính tiền.
- **`illegal_flag` (`bhphap == 1`):** `true` nếu hóa đơn bị CQT gắn cờ `"Bất hợp pháp"`.

## 6. Điều khiển demo: `/sim/scenario`

| Method | Path | Body → Kết quả |
|---|---|---|
| POST | `/sim/scenario:reset` | `{dataset: string, seed: integer}` → `{loaded_at, counts}` |
| GET | `/sim/scenario/state` | đồng hồ, số tin trong hộp thư, ví, thẻ |
| GET | `/sim/scenario/catalog` | `[{template_id, title, expected_severity, expected_reason_codes}]` (6 kịch bản BRD §14, Bẫy cuối, ca tấn công) |
| POST | `/sim/scenario/invoices:send` | `{template_id, overrides?}` → `{message_id \| bill_id}`. Đặt email kèm XML vào hộp thư, hoặc thêm hóa đơn điện nước |
| POST | `/sim/scenario/chat-messages` | `{thread_id, text}` → tin nhắn từ phía NCC (ví dụ "đổi TK") |
| POST | `/sim/scenario/cards/{card_id}:swipe` | `{merchant_id, amount_vnd}` → `{approved: boolean, reason}`. Sai merchant/lần hai → từ chối + webhook `card.authorization_declined` |
| GET | `/sim/scenario/clock` | `{now: Timestamp}` |
| POST | `/sim/scenario/clock:advance` | `{to: Timestamp}` → `{now}`. Ở `DEMO_MODE`, port `Clock` của core và gate đọc giờ từ đây để lịch chi chạy được trong buổi demo |
