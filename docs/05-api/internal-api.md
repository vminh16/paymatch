# Internal API (`/internal/*`, cổng 8003)

Trạng thái: **v0.3 (26/11/2026)**: agent điều phối ReAct theo loại việc; đã sửa theo review. File OpenAPI: `contracts/openapi/core-internal.yaml`. Chỉ mạng service. Không dùng header `Idempotency-Key`; khóa nghiệp vụ là `(job_id, attempt, bot_id)`.

Hai loại xác thực, **không bao giờ trộn**:

| Nhóm | Header | Ai |
|---|---|---|
| Job (claim, session, heartbeat, progress, complete, fail) | `X-Service-Key` của agent-worker + `worker_id`, `attempt` trong body | agent-worker |
| Tool, nộp Finding/BotAnswer | `Authorization: Bearer <capability_token>` | agent-worker, nhân danh **điều phối** hoặc **một** bot trong **một** lần chạy |
| Webhook | `X-Service-Key` của sim-world | sim-world |

**Kiểm lease ở mọi lời gọi của job**: `(job_id, attempt, worker_id)` phải là lease đang giữ; sai → `409 LEASE_LOST` và worker dừng job. Capability token mang `attempt`; token của lần chạy cũ bị từ chối dù còn hạn.

## 1. Vòng đời job

Mọi việc của agent là một **job** có `task_type` (`investigate_invoice` · `question` · `report`, xem [agent-runtime.md §2](../03-agents/agent-runtime.md#2-loại-việc)). Không có plan cố định: core chỉ mở phiên (cấp token, nói bot và tool nào được phép), agent điều phối ReAct tự quyết gọi gì; core kiểm **điều kiện hoàn tất** lúc kết thúc.

```
agent-worker                                    internal-api (core)
  POST /internal/jobs:claim ─────────────────►  job queued (hàng đợi theo task_type), lease 120 s, attempt += 1
  POST /internal/jobs/{id}/session ──────────►  token điều phối + token từng bot được phép, tool, ngân sách,
                                         ◄────  bot bắt buộc (nếu điều tra), ngữ cảnh (hóa đơn / lịch sử hội thoại)
  vòng ReAct của chief-accountant:
    POST /internal/tools/{tool_id}:invoke (token điều phối: tool thống kê, tra cứu trusted)
    ask_<bot> → vòng ReAct của bot:
        POST /internal/tools/{tool_id}:invoke (token bot)
        POST /internal/jobs/{id}/findings  hoặc  /bot-answers (token bot) ─► core kiểm, trả bản đã lọc cho điều phối
  POST /internal/jobs/{id}/progress   (service key)
  POST /internal/jobs/{id}/heartbeat  (mỗi 30 s)
  POST /internal/jobs/{id}:complete ─────────►  core kiểm điều kiện hoàn tất, gộp màu / kiểm trích dẫn, ghi kết quả
```

| Method | Path | Body → Kết quả |
|---|---|---|
| POST | `/internal/jobs:claim` | `{worker_id, task_types?: [..]}` → `200 {job_id, task_type, tenant_id, attempt, lease_expires_at, subject: {invoice_id} \| {conversation_id, message_id} \| {report_kind, period}}` hoặc `204`. `SKIP LOCKED`; `question` ưu tiên trước; giới hạn đồng thời theo tenant |
| POST | `/internal/jobs/{job_id}/session` | `{worker_id, attempt}` → `{budget: {seconds, max_steps}, supervisor: {capability_token, token_exp, tools: [ToolDefinition]}, bots: [{bot_id, bot_version, description, manifest, skills, prefetch, capability_token, token_exp}], required_bot_ids: [..], skipped: [{bot_id, reason: KILL_SWITCH \| DISABLED}], context}`. `bots` = bot active của tenant có `task_types` chứa loại việc này (điều tra: thêm lọc trigger theo loại hóa đơn), trừ kill switch. `context`: điều tra → `{invoice_id, invoice_type}` (không có chữ untrusted); hỏi đáp → `{messages: [{role, text_trusted}]}` (câu hỏi của người dùng, các câu trả lời trước), `user: {role, store_ids}`. Gọi lại trong cùng attempt → cùng nội dung, token mới |
| POST | `/internal/jobs/{job_id}/heartbeat` | `{worker_id, attempt}` → `{lease_expires_at, tokens: [{holder: supervisor \| <bot_id>, capability_token, token_exp}]}` |
| POST | `/internal/jobs/{job_id}/progress` | `{worker_id, attempt, events: [{type: supervisor.step \| bot.started \| bot.tool_called \| bot.finished \| bot.failed \| answer.delta, bot_id?, tool_id?, text_delta?, at}]}` → `204`. `answer.delta` chỉ dùng cho hỏi đáp (luồng chữ của câu trả lời, hiển thị như untrusted) |
| POST | `/internal/jobs/{job_id}/findings` | token bot (chỉ `investigate_invoice`); body `FindingSubmission` → `201 FindingForSupervisor {finding_id, bot_id, severity, reason_codes, evidence}` (đã áp mức sàn, **đã bỏ `reason`**). Kiểm: `bot_id` = `sub` của token; mọi `evidence[].tool_call_id` thuộc cùng job, attempt, bot; `ref_id` đúng mẫu và có trong output tool_call; đã gọi đủ `prefetch`; `reason` ≤ 1000 ký tự. Một bot được gọi nhiều lần trong job → Finding sau thay Finding trước (giữ lịch sử). Job đã xong → `409 INVALID_STATE` |
| POST | `/internal/jobs/{job_id}/bot-answers` | token bot (`question`, `report`); body `{bot_id, facts: [{key, value: string \| number, tool_call_id}], reason_codes: [ReasonCode]}` → `201 BotAnswer` (core kiểm mỗi `value` có trong output của `tool_call_id`, gỡ fact không khớp) |
| POST | `/internal/jobs/{job_id}:complete` | `{worker_id, attempt, result}` → `200 {status, …}`. `result` theo loại việc: **điều tra** `{brief: {lines ≤ 5 × 200 ký tự, cited_evidence, model, prompt_hash}}` → core: thêm vàng `BOT_NOT_RUN` cho bot bắt buộc chưa có Finding, `BOT_DISABLED` cho bot bắt buộc trong `skipped`; chạy kiểm tra hệ thống (§4); gộp màu; ghi trạng thái hóa đơn bằng CAS từ `investigating` ([bảng](merchant-api.md#2-hóa-đơn)); trả `{final_severity, invoice_status}`. **Hỏi đáp / báo cáo** `{answer: {text, citations: [{tool_call_id, values: [string]}], tables?: [{columns, rows, tool_call_id}], proposed_actions: [ProposedAction]}}` → core kiểm trích dẫn (con số không có trong tool_call được trích → gỡ, gắn cờ `unverified`), kiểm `proposed_actions` là loại hợp lệ và thuộc tenant/quán của người hỏi; lưu thành tin nhắn trả lời |
| POST | `/internal/jobs/{job_id}:fail` | `{worker_id, attempt, error_code, detail}` → `200 {will_retry}`. Tối đa 2 attempt; hết lượt: điều tra → hoàn tất như `:complete` không có brief (bot bắt buộc thiếu thành vàng); hỏi đáp → tin nhắn trả lời "chưa trả lời được" |
| GET | `/internal/model-configs` | → `[ModelConfig]` |

Token **điều phối** không bao giờ có tool trả chữ `untrusted` (`inbox`, `chat_messages`, `invoices` phần chữ); core từ chối cấp nếu cấu hình sai. Token **bot** chỉ có tool trong manifest của bot ∩ tool cho phép của loại việc.

## 2. Tool

| Method | Path | Body → Kết quả |
|---|---|---|
| GET | `/internal/tools` | token bot → `[ToolDefinition]` của tool trong token |
| POST | `/internal/tools/{tool_id}:invoke` | token bot; `{input}` → `200 ToolResult`. Kiểm lại kill switch (tenant, bot, tool) ở **mỗi** lần gọi → `423 KILL_SWITCH_ACTIVE`. Input sai schema → `400`. Nguồn dữ liệu lỗi → `200` với `ToolResult.error` (bot ghi vàng) |

Tool chỉ-đọc, chỉ dữ liệu của `tenant_id` trong token, và với dữ liệu gắn hóa đơn thì chỉ của `invoice_id` trong token hoặc NCC của nó. Mọi lần gọi ghi `tool_calls` (input, output, provenance, attempt).

**Danh mục tool v1 và nguồn** (bổ sung được khi phát triển, xem [tools.md](../03-agents/tools.md)):

| Tool | Input | Nguồn | Provenance |
|---|---|---|---|
| `invoices` | `{}` (hóa đơn của job) hoặc `{invoice_ids}` cùng NCC | DB `core` | số trusted, `untrusted.*` untrusted |
| `vendor_contracts` | `{vendor_id?}` | DB `core`, chỉ hợp đồng `active` | trusted |
| `price_check` | `{mappings: [{line_id, sku}]}` | DB `core`. **Quy cách lấy từ `ContractItem.pack_qty`**, số trong hóa đơn do code parse từ `DVTinh`/tên hàng; LLM chỉ chọn `sku`. Trả `{line_id, sku, unit_price_invoice, unit_price_contract, delta_pct, pack_qty_contract, pack_qty_parsed \| null}` | trusted |
| `price_history` | `{sku, months ≤ 12}` | DB `core` | trusted |
| `purchase_orders`, `goods_receipts`, `payables_ledger` | `{vendor_id?, purchase_order_id?}` | DB `core` | trusted |
| `three_way_match` | `{}` | DB `core` (code đối chiếu) | trusted |
| `inbox` | `{since?}` (thư từ địa chỉ của NCC) | `GET /sim/inbox/messages` | **untrusted** |
| `chat_messages` | `{since?}` | `GET /sim/chat/threads`, `…/messages` | **untrusted** |
| `vendor_registry` | `{}` (NCC của hóa đơn) | DB `core`: TK `verified`/`escrow_only`, SĐT lưu sẵn (che), **các lần xác minh đã duyệt** (để không báo lại yêu cầu đổi TK đã xử lý ở F12) | trusted |
| `cross_alerts` | `{}` | DB `risk` (indicator của hóa đơn) | trusted |
| `official_fraud_list` | `{}` | `GET /sim/simo/indicators:check` cho TK, SĐT, MST của hóa đơn | trusted |
| `einvoice_portal` | `{}` | `GET /sim/einvoice/invoices` | trusted |
| `tax_id_lookup` | `{tax_id}` | `GET /sim/tax/taxpayers/{tax_id}` | trusted |
| `tax_risk_list` | `{tax_id}` | `GET /sim/tax/risk-list/{tax_id}` | trusted |
| `utility_bills`, `utility_baseline` | `{store_id?, months ≤ 12}` | DB `core` (code tính trung vị, khoảng bình thường) | trusted |
| `momo_revenue` | `{store_id, month}` | `GET /sim/revenue` | trusted |
| `account_balance` | `{}` | `GET /sim/rails/wallets/{wallet_id}` | trusted |
| `spending_limits` | `{}` | mandate + `PlatformLimits` + `GET /gate/budgets/{tenant_id}/{date}` | trusted |
| `payment_policy_preview` | `{}` | `POST /gate/evaluate` (không tác dụng phụ) | trusted |

**Tool thống kê, tra cứu cho hỏi đáp** (điều phối và bot dùng được; truy vấn viết sẵn, chỉ tham số; lọc theo `store_ids` của người hỏi):

| Tool | Input | Trả về |
|---|---|---|
| `invoice_search` | `{status?, severity?, vendor_id?, store_id?, reason_code?, issued_from?, issued_to?, limit ≤ 50}` | danh sách hóa đơn (chỉ phần số + id, tên NCC từ registry) |
| `invoice_explain` | `{invoice_id}` | màu, mã lý do, Finding (không có `reason`), trạng thái, lịch chi |
| `spending_summary` | `{from, to, group_by: vendor \| store \| invoice_type \| month, store_id?}` | tổng chi, số hóa đơn theo nhóm |
| `vendor_stats` | `{vendor_id, months ≤ 12}` | số hóa đơn, tổng tiền, số lần vượt giá hợp đồng, số lần vàng/đỏ |
| `price_trend` | `{sku, months ≤ 12}` | đơn giá/đơn vị theo tháng, so hợp đồng |
| `queue_status` | `{}` | số hóa đơn theo trạng thái, tổng tiền chờ duyệt, hạn trả gần nhất |
| `utility_summary` | `{store_id?, months ≤ 12}` | điện nước theo quán, so khoảng bình thường |
| `payment_history` | `{from, to, vendor_id?}` | các lần chi (ngày, số tiền, kênh, hóa đơn) |

Mọi số trong các tool này do code tính; tool trả `ToolResult` trusted.

## 3. Mức sàn từ output tool

Khi nhận Finding, core xem các tool_call **trusted** của bot đó trong attempt này và tự thêm mã lý do, bất kể bot viết gì:

| Output tool | Mã thêm |
|---|---|
| `price_check.delta_pct > 0` ở dòng nào đó | `PRICE_ABOVE_CONTRACT` |
| `pack_qty_parsed` khác `pack_qty_contract`, hoặc không parse được | `PACK_SIZE_CHANGED` |
| `three_way_match` báo vượt số lượng / thiếu phiếu nhập | `QUANTITY_ABOVE_NORM` / `NO_GOODS_RECEIPT` |
| `utility_baseline` ngoài khoảng bình thường | `UTILITY_OUT_OF_RANGE` |

Bot không gọi tool nào mà báo `OK` thì vẫn bị chặn bởi luật `prefetch` (§1) và kiểm tra hệ thống (§4).

## 4. Kiểm tra hệ thống lúc `:complete` (điều tra hóa đơn)

Core tự kiểm bằng **dữ liệu đã có trong DB**, không gọi ra ngoài, nên agent-runtime bị chiếm cũng không làm hóa đơn xanh được và không thêm độ trễ:

| Kiểm tra | Mã nếu trúng |
|---|---|
| indicator của hóa đơn khớp `risk.cross_alerts` đang `published` (bắt cả cảnh báo chéo phát hành trong lúc job chạy) | `CROSS_ALERT_HIT` (vàng, bắt buộc xác minh) |
| indicator khớp `risk.hard_blocks` | `OFFICIAL_FRAUD_LIST` (đỏ) |
| TK trên hóa đơn (`NBan/STKNHang`) có mà không trùng TK `verified` nào của NCC, và không có xác minh đã duyệt cho TK đó | `PAYEE_CHANGE_REQUEST` (đỏ) |

Tra SIMO và danh sách rủi ro thuế vẫn do bot `fraud-control` và `tax` làm qua tool (dữ liệu giả lập của sim-world).

## 5. Webhook từ sim-world

| Method | Path | Body → Kết quả |
|---|---|---|
| POST | `/internal/webhooks/rails` | `{event_id, type: card.authorization_declined \| transfer.settled \| transfer.failed, occurred_at, data}` → `204`. Idempotent theo `event_id`. `card.authorization_declined {card_id, merchant_id, reason: wrong_merchant \| already_used \| over_amount}` → core phát `indicator.flagged` (F8). `transfer.*` chỉ để đối soát; trạng thái chi do Gate quyết |

Hộp thư và hóa đơn điện nước **không dùng webhook**: core-worker hỏi định kỳ (2 s ở demo), như đọc IMAP thật.
