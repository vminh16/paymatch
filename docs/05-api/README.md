# API contract

Trạng thái: **Bản thiết kế v0.2 (26/11/2026)**, đã sửa theo review của Opus 5.5. Đây là đặc tả bằng chữ để viết `contracts/openapi/*.yaml`, `contracts/schemas/`, `contracts/events/`. Khi YAML đã có, YAML là nguồn sự thật và tài liệu này chỉ giải thích.

| File | Nội dung |
|---|---|
| [README.md](README.md) | Cổng, ai gọi ai, quy ước chung, lỗi, ma trận phủ luồng |
| [schemas.md](schemas.md) | Đối tượng dùng chung (Invoice, Finding, Approval, PaymentIntent…) |
| [merchant-api.md](merchant-api.md) | `/m/*`: app chủ chuỗi, kế toán, quản lý quán |
| [console-api.md](console-api.md) | `/console/*`: nhân viên MoMo |
| [internal-api.md](internal-api.md) | `/internal/*`: agent-runtime và webhook từ sim-world |
| [gate-api.md](gate-api.md) | Payment Gate |
| [sim-world-api.md](sim-world-api.md) | Thế giới giả lập: định danh, rail, hộp thư, thuế, SIMO, kịch bản |
| [events.md](events.md) | Sự kiện outbox và luồng SSE |

## 1. Tiến trình và cổng

Mỗi tiến trình có **đúng một cổng** và **đúng một tiền tố đường dẫn**. Không có cổng nào phục vụ hai tiền tố. v1 chạy `merchant-api`, `console-api`, `internal-api` thành **ba container cùng image `core`**, chỉ khác lệnh khởi động. Tách như vậy từ đầu để console và internal không bao giờ lộ ra cùng cổng với merchant.

| Tiến trình | Image | Cổng (container và máy dev) | Tiền tố | Mạng | Ai được gọi |
|---|---|---|---|---|---|
| `merchant-api` | core | **8001** | `/m` | public (qua gateway MoMo) | `web-merchant` |
| `console-api` | core | **8002** | `/console` | chỉ mạng nội bộ MoMo | `web-console` |
| `internal-api` | core | **8003** | `/internal` | chỉ mạng service | `agent-worker`, `sim-world` (webhook) |
| `core-worker` | core | — (metrics **9101**) | — | — | không nhận request |
| `agent-worker` | agent-runtime | — (metrics **9102**) | — | — | không nhận request |
| `gate` | payment-gate | **8100** | `/gate` | chỉ mạng service | `merchant-api`, `core-worker`, `console-api` (chỉ đọc) |
| `sim-world` | sim-world | **8200** | `/sim` | chỉ mạng service (demo: cả trình duyệt bảng điều khiển kịch bản) | `core-*`, `gate`, `web-*` (chỉ `/sim/identity` và `/sim/scenario`) |
| `web-merchant` | apps/merchant | **5173** | — | public | trình duyệt |
| `web-console` | apps/console | **5174** | — | nội bộ | trình duyệt |
| `postgres` | postgres:16 | **5432** | — | chỉ mạng service | core-*, gate |
| `otel-collector` | otel | **4317** (gRPC), **4318** (HTTP) | — | chỉ mạng service | mọi service |

Mọi tiến trình HTTP có `GET /<tiền tố>/healthz` (sống) và `GET /<tiền tố>/readyz` (đã nối DB/phụ thuộc), ví dụ `GET /gate/healthz`. Worker không có tiền tố: `GET /healthz`, `GET /readyz`, `GET /metrics` trên cổng metrics.

Biến môi trường chỉ địa chỉ (một biến cho mỗi đích, không suy đoán):

| Biến | Giá trị dev | Ai dùng |
|---|---|---|
| `CORE_INTERNAL_URL` | `http://internal-api:8003/internal` | agent-worker, sim-world |
| `GATE_URL` | `http://gate:8100/gate` | merchant-api, core-worker, internal-api (tool treasury), console-api |
| `SIM_URL` | `http://sim-world:8200/sim` | core-*, gate |
| `DATABASE_URL` | `postgresql://…@postgres:5432/paymatch` | core-*, gate. **agent-worker và sim-world không có biến này** |

## 2. Ai gọi ai

```
web-merchant ──► merchant-api ──► gate (/evaluate; /escrows; GET intents, escrows)
                     │       └──► sim (/identity JWKS; /rails/wallets; /scenario:reset ở demo)
web-merchant ──► sim (/identity: lấy momo_token, step-up OTP — chỉ demo)
web-console ───► console-api ──► gate (GET /intents/{id}, chỉ trong handler tra bằng chứng có ticket)
                     └──► sim (/identity JWKS; /simo khi đề xuất hard block)
agent-worker ──► internal-api ──► (tool handler) ──► sim (/einvoice, /tax, /simo, /inbox, /chat, /revenue, /rails/wallets)
                                              └──► gate (/evaluate, /budgets) cho tool treasury
core-worker ───► gate (/intents, :execute, :cancel, /escrows/{id}:release, :refund); đọc ledger.outbox
            └──► sim (/inbox, /bills: lấy hóa đơn mới; /scenario/clock ở chế độ demo)
gate ──────────► sim (/rails/*; /scenario/clock ở chế độ demo)
sim-world ─────► internal-api (/internal/webhooks/rails: sự kiện thẻ bị từ chối)
```

Những đường **không tồn tại** (có test kiểm): agent-worker → gate; agent-worker → postgres; agent-worker → sim; gate → core API; sim-world → postgres; web-* → internal-api hoặc gate.

Gate **đọc thẳng** DB schema `core`, `control`, `risk` (chỉ-đọc) để tự đọc lại hóa đơn, approval, danh bạ, mandate, policy. Vì vậy request vào Gate chỉ mang **id**, không mang số TK hay số tiền để Gate tin.

## 3. Quy ước chung

| Mục | Quy ước |
|---|---|
| Định dạng | JSON UTF-8, `snake_case`. Upload dùng `multipart/form-data` |
| Kiểu đường dẫn | Tài nguyên số nhiều (`/invoices/{invoice_id}`). Hành động không phải CRUD dùng **custom method** `POST …/{id}:verb` (`:approve`, `:execute`). Không dùng `PUT`; sửa một phần dùng `PATCH` (JSON Merge Patch) |
| ID | Chuỗi có tiền tố + ULID: `ten_`, `sto_`, `usr_`, `grt_` (tool grant), `itm_` (dòng hợp đồng), `wal_` (ví), `adj_` (yêu cầu điều chỉnh), `pvw_` (preview duyệt hàng loạt), `cnv_` (hội thoại), `cmg_` (tin nhắn hội thoại), `rpt_` (báo cáo), `hbk_` (hard block), `msg_`, `urd_` (chỉ số điện nước), `stf_`, `inv_`, `doc_`, `lin_`, `job_`, `fnd_`, `brf_`, `apv_`, `abt_`, `man_`, `ven_`, `vac_`, `vvf_`, `ctr_`, `po_`, `grn_`, `exp_`, `bot_` (bot tenant; bot hệ thống dùng id `kebab-case`), `skl_`, `tcl_`, `pi_`, `esc_`, `ind_`, `alr_`, `cas_`, `cac_`, `cxa_`, `ksw_`, `ksr_`, `ntf_`, `evt_`, `chl_` |
| Tiền | `integer`, đơn vị **VND** (đồng), tên trường hậu tố `_vnd`. Không dùng số thực cho tiền |
| Số lượng, đơn giá, tỷ lệ | **chuỗi thập phân** (`"12.500000"`), tối đa 6 chữ số thập phân như XML gốc (QĐ 1233) |
| Thời gian | RFC 3339 có múi giờ (`2026-11-26T09:15:00+07:00`). Ngày: `YYYY-MM-DD`, hiểu theo giờ Việt Nam |
| Phân trang | `?limit=` (mặc định 50, tối đa 200) và `?cursor=`. Trả `{items: [...], next_cursor: string \| null}` |
| Lọc | tham số query trùng tên trường; nhiều giá trị lặp tham số (`?status=blocked&status=pending_approval`) |
| Idempotency | Mọi `POST` có tác dụng phụ trên `/m` và `/console` **bắt buộc** header `Idempotency-Key` (≤ 64 ký tự). Cùng key + cùng body → trả lại kết quả cũ; cùng key + body khác → `409 IDEMPOTENCY_KEY_REUSED`. Lưu 24 giờ. `/internal` dùng khóa nghiệp vụ `(job_id, attempt, bot_id)`, webhook dùng `event_id`, Gate dùng `invoice_id`/`purchase_order_id`; các đường này không đòi header |
| Phiên bản | Không đặt version trong URL. Chỉ thêm trường/endpoint (thay đổi tương thích). Thay đổi phá vỡ = endpoint mới; ghi vào `info.version` của OpenAPI |
| Tương tranh | Tài nguyên sửa được trả `ETag`; `PATCH`/hành động trên nó nhận `If-Match`, sai → `412 PRECONDITION_FAILED`. Riêng duyệt chi dùng `intent_hash` (mạnh hơn ETag) |
| Truy vết | Mọi request mang `traceparent` (W3C). Mọi response có `X-Request-Id` |
| Hiển thị | Trường chữ đến từ người bán hoặc do LLM viết có hậu tố hoặc nằm trong đối tượng đánh dấu `untrusted` (xem schemas.md §1). Frontend luôn escape, không render HTML/Markdown từ các trường này |

## 4. Xác thực

| Bên gọi → đích | Cơ chế | Header |
|---|---|---|
| web-merchant → merchant-api | JWT phiên do core cấp sau khi đổi token MoMo (demo: sim `/identity`) | `Authorization: Bearer <session_jwt>` |
| Hành động nhạy cảm (duyệt, ký mandate, đổi TK NCC, tạo cọc, bật lại tự chi, duyệt bot) | **Xác thực mạnh từng lần**: `auth_proof` là JWT ngắn hạn (5 phút, dùng một lần) do bên định danh ký, gắn `action_hash` của đúng hành động | trường `auth_proof` trong body |
| web-console → console-api | JWT nhân viên (SSO; demo: sim `/identity`), claim `staff_roles` | `Authorization: Bearer <staff_jwt>` |
| CSKH tra bằng chứng | thêm mã ticket | `X-Ticket-Id` |
| service → service | khóa service theo cặp (v1), mTLS (lộ trình) | `X-Service-Key` |
| agent-worker → `/internal/tools/*`, `/internal/jobs/{id}/findings` | **capability token** của đúng một bot trong đúng một job | `Authorization: Bearer <capability_token>` |

`action_hash` tính theo RFC 8785 + sha256, công thức ở [schemas.md §4](schemas.md#4-duyệt-và-chi); một hàm duy nhất trong `paymatch_contracts` (và bản TypeScript sinh cùng test vector). Với duyệt chi, `payload_hash` phủ `intent_hash` và `verification`, nên một `auth_proof` không dùng lại được cho hóa đơn khác, số tiền khác hay lời khai xác minh khác.

## 5. Lỗi

Mọi lỗi trả `application/problem+json` (RFC 9457) có thêm `code` (enum ổn định, frontend dựa vào đây) và `errors[]` khi sai dữ liệu vào:

```json
{"type": "https://paymatch.dev/problems/intent-hash-mismatch", "title": "Invoice changed since preview",
 "status": 409, "code": "INTENT_HASH_MISMATCH", "detail": "…", "instance": "/m/invoices/inv_…:approve",
 "errors": [{"field": "intent_hash", "code": "stale"}]}
```

| HTTP | `code` | Khi nào |
|---|---|---|
| 400 | `VALIDATION_FAILED` | Sai schema, sai enum |
| 401 | `UNAUTHENTICATED`, `TOKEN_EXPIRED` | Thiếu/sai/hết hạn token |
| 403 | `FORBIDDEN`, `ROLE_NOT_ALLOWED`, `TOOL_NOT_GRANTED`, `TENANT_MISMATCH`, `TICKET_REQUIRED` | Có danh tính nhưng không có quyền |
| 403 | `STEP_UP_REQUIRED`, `STEP_UP_INVALID` | Thiếu hoặc sai `auth_proof` |
| 404 | `NOT_FOUND` | Không có, **hoặc thuộc tenant khác** (không tiết lộ tồn tại) |
| 409 | `INVALID_STATE` | Hành động không hợp lệ ở trạng thái hiện tại (kèm `current_status`) |
| 409 | `INTENT_HASH_MISMATCH` | Hóa đơn/payee/số tiền/kênh đã đổi sau lúc xem trước |
| 409 | `DUPLICATE_INVOICE` | Upload file khác (`sha256` khác) trùng khóa `(MST bán, ký hiệu, int(số))`; không lưu, kèm `existing_invoice_id` (upload đúng cùng `sha256` là no-op trả hóa đơn đã có; qua `email`/`bill_pay` lưu kèm `duplicate_of` + Finding đỏ) |
| 409 | `IDEMPOTENCY_KEY_REUSED`, `LEASE_LOST`, `MAKER_CHECKER_VIOLATION` | |
| 412 | `PRECONDITION_FAILED` | `If-Match` sai |
| 422 | `GATE_DENIED` | Gate từ chối; kèm `gate_reasons[]` |
| 422 | `MANDATE_ABOVE_PLATFORM_CEILING`, `BOT_MANIFEST_INVALID`, `XML_UNPARSEABLE` | Dữ liệu đúng schema nhưng sai nghiệp vụ |
| 423 | `KILL_SWITCH_ACTIVE` | Bị kill switch chặn |
| 429 | `RATE_LIMITED` | Kèm `Retry-After` |
| 502/503/504 | `UPSTREAM_UNAVAILABLE`, `UPSTREAM_TIMEOUT` | Gate/sim không trả lời. Với `/gate/evaluate`: không cho duyệt. Với `:execute`: **kết quả chưa biết**, tra `GET /gate/intents/{id}`, không gọi lại mù |

## 6. Thời gian chờ và thử lại

| Lời gọi | Timeout | Thử lại |
|---|---|---|
| tool invoke (agent → internal-api) | 5 s | runtime thử lại 1 lần nếu 5xx, trong ngân sách 20 s của bot |
| internal-api → sim | 3 s | không; lỗi → `ToolResult.error`, bot ghi vàng |
| merchant-api → gate `/evaluate` | 2 s | không; lỗi → UI báo "không xem trước được", không cho bấm Duyệt |
| core-worker → gate `:execute` | 10 s | không thử lại `:execute` mù; nếu timeout thì `GET /gate/intents/{id}` để biết trạng thái |
| gate → sim `/rails/*` | 5 s | cùng `idempotency_key` = `intent_id`; timeout → intent giữ `executing`, gate hỏi lại `GET /sim/rails/transfers/{key}` |
| webhook sim → internal-api | 3 s | sim thử lại 3 lần, lùi dần; core xử lý idempotent theo `event_id` |

## 7. Ma trận phủ luồng

| Luồng | Endpoint / sự kiện |
|---|---|
| F1 nhận hóa đơn | core-worker `GET /sim/inbox/messages` · `POST /m/invoices:upload` · `GET /sim/bills` → `invoice.ingested` (hóa đơn `investigating` + job `queued`) · PDF/ảnh: `PATCH /m/invoices/{id}/manual-fields` |
| F1 điều tra | `POST /internal/jobs:claim` · `POST /internal/jobs/{id}/session` · `GET /internal/tools` · `POST /internal/tools/{tool_id}:invoke` · `POST /internal/jobs/{id}/progress` · `POST /internal/jobs/{id}/findings` · `POST /internal/jobs/{id}:complete` → `job.completed`, `invoice.status_changed` · SSE `GET /m/jobs/{id}/events` |
| F1 xem, duyệt, từ chối | `GET /m/approval-queue` · `GET /m/invoices/{id}` · `GET /m/invoices/{id}/approval-preview` · `POST /sim/identity/step-up-challenges` (+`:verify`) · `POST /m/invoices/{id}:approve` · `POST /m/invoices/{id}:reject` · `GET /m/invoices/{id}/adjustment-request` |
| F1 lịch chi, chi | `POST /m/invoices/{id}:schedule` · `POST /m/invoices/{id}:pay-now` · `POST /m/invoices/{id}:cancel-payment` · core-worker `POST /gate/intents` · `POST /gate/intents/{id}:execute` · gate `POST /sim/rails/transfers` hoặc `/sim/rails/cards` → `payment.executed` / `payment.failed` / `payment.denied` / `payment.expired`; vòng nền gate cho `executing` |
| Hỏi đáp, báo cáo (v1) | `POST /m/conversations` · `POST /m/conversations/{id}/messages` → job `question` → `POST /internal/jobs/{id}/session` · tool thống kê · `POST /internal/jobs/{id}/bot-answers` · `:complete {answer}` → `message.completed` · SSE `GET /m/jobs/{id}/events` (`answer.delta`) · `POST /m/reports` |
| F2 tự chi, QT-03 | core-worker tạo approval `mandate` · `GET /m/auto-pay-suspensions` · `POST /m/auto-pay-suspensions/{vendor_id}:lift` · `GET /m/summaries/daily` |
| Duyệt hàng loạt (§6a) | `POST /m/approval-batches:preview` · `POST /m/approval-batches` · `GET /m/approval-batches/{id}` |
| Mandate | `GET /m/mandate` · `GET /m/mandates` · `POST /m/mandates` · `GET /m/platform-limits` |
| F3 cảnh báo chéo | `indicator.flagged` · `GET /console/alerts` · `POST /console/cross-alerts` → `cross_alert.published` → core-worker đánh giá lại + `POST /gate/intents/{id}:cancel` cho intent đã authorized · `notification.created` · `GET /m/notifications` · duyệt có `verification` |
| Chặn cứng | `POST /console/cases/{id}/actions` (`propose_hard_block`) · `POST /console/case-actions/{id}:approve` → `risk.hard_blocks`, `hard_block.applied` |
| F4 kill switch | `POST /console/kill-switches` · `POST /console/kill-switches/{id}/release-requests` · `POST /console/kill-switch-release-requests/{id}:approve` → `kill_switch.engaged`/`released` |
| F5 tạo bot | `GET /m/tools` · `GET /m/reason-codes` · `POST /m/skills` · `POST /m/bots` · `POST /m/bots/{id}/versions` · `POST /m/bots/{id}:submit` · `:approve` · `:disable` · `:enable` · `:archive` |
| F6 CSKH | `GET /console/evidence` (+`X-Ticket-Id`) · `GET /console/evidence/documents/{document_id}` · `GET /console/access-log` |
| F7 escrow | `POST /m/vendors/{id}/account-changes` (`target_status=escrow_only`) · `POST /m/purchase-orders` · `GET /m/purchase-orders/{id}/escrow-preview` · `POST /m/escrows` → `POST /gate/escrows` → `POST /sim/rails/escrows` → `escrow.held` · hóa đơn giao hàng: `:approve` (kênh escrow) · `POST /m/goods-receipts` → core-worker `POST /gate/escrows/{id}:release` → `escrow.released` · hết hạn / `POST /m/purchase-orders/{id}:cancel` → `:refund` |
| F8 thẻ ảo bị dùng sai | `POST /sim/scenario/cards/{card_id}:swipe` → `POST /internal/webhooks/rails` → `indicator.flagged` → alert console |
| F9 điện nước | core-worker `GET /sim/bills` → như F1 |
| F11 chi không hóa đơn | `POST /m/expense-records` · `GET /m/expense-records` |
| Dữ liệu gốc | `POST /m/vendors` (step-up) · `POST /m/vendors/{id}:change-phone` (step-up) · `POST /m/vendor-contracts` · `POST /m/vendor-contracts/{id}:activate` (step-up) |
| F12 đổi TK NCC | `POST /m/vendors/{id}/account-changes` · `POST /m/vendor-verifications/{id}:record-callback` · `:approve` · `:reject` → `vendor_account.changed` → hóa đơn bị khóa vì `PAYEE_CHANGE_REQUEST` quay về `investigating` |
| Demo | `POST /sim/scenario:reset` · `POST /sim/scenario/invoices:send` · `POST /sim/scenario/clock:advance` · `POST /m/demo:reset` (chỉ khi `DEMO_MODE=true`) |

## 8. Chạy mock server cho frontend

Frontend (`apps/merchant`) có thể chạy trực tiếp trên OpenAPI contract mà chưa cần backend:

```bash
make mock
```

Lệnh này chạy Prism (`npx @stoplight/prism-cli mock -p 8001 contracts/openapi/core-merchant.yaml`) trên cổng **8001** (prefix `/m`), trả về các `examples` lấy từ bộ dữ liệu demo `services/sim-world/data/demo/` (hàng chờ duyệt, hóa đơn xanh cà phê, hóa đơn vàng cốc nhựa shrinkflation, hóa đơn đỏ si-rô NCC mới…).

- Chọn example cụ thể bằng header Prism: `Prefer: example=<tên_example>` (ví dụ `Prefer: example=yellow_cups_shrinkflation` hoặc `Prefer: example=red_syrup_new_vendor_fraud` trên `GET /m/invoices/{invoice_id}`), hoặc chọn mã lỗi bằng `Prefer: code=409`.
- **Giới hạn SSE:** hai endpoint `GET /m/jobs/{job_id}/events` và `GET /m/events` được khai báo đầy đủ tên sự kiện và cấu trúc `data` trong `core-merchant.yaml`, nhưng Prism không hỗ trợ giữ kết nối stream `text/event-stream` (chỉ trả một response mẫu tĩnh rồi đóng). Trong lúc phát triển trên mock, frontend nên tạm fallback sang **polling** (`GET /m/jobs/{job_id}` cho tiến trình điều tra, `GET /m/approval-queue` / `GET /m/invoices` / `GET /m/notifications` cho hàng chờ) hoặc dùng một bộ phát sự kiện cục bộ (mock `EventSource`/MSW) bật theo biến môi trường phía client, sau đó nối lại `@microsoft/fetch-event-source` khi chạy cùng `merchant-api` thật.
