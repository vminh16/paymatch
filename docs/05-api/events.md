# Sự kiện và SSE

Trạng thái: **v0.2 (26/11/2026)**, đã sửa theo review. Mỗi sự kiện có một file `contracts/events/<type>.schema.json`.

## 1. Envelope và giao nhận

```yaml
Event:
  event_id: string          # evt_ + ULID; người nhận khử trùng theo trường này
  type: string              # noun.past_tense
  schema_version: integer
  occurred_at: Timestamp
  tenant_id: string | null  # null với sự kiện toàn mạng
  trace_id: string | null
  data: object
```

**Transactional outbox**: bên ghi lưu sự kiện cùng transaction với thay đổi dữ liệu; `core-worker` xử lý **ít nhất một lần**, theo thứ tự trong cùng `tenant_id` của **từng** outbox. Hai outbox không có thứ tự với nhau, nên:

- **Mọi lần đổi trạng thái hóa đơn là compare-and-set** từ trạng thái mong đợi (`UPDATE … WHERE status = :from`). Không khớp → bỏ qua, ghi log. Không handler nào "khôi phục trạng thái trước đó".
- Mỗi trạng thái đích có đúng một bên ghi (bảng §2, cột "Trạng thái hóa đơn").

| Outbox | Ghi bởi | Đọc bởi |
|---|---|---|
| `core.outbox` | merchant-api, console-api (role `staff` chỉ có quyền `INSERT` vào bảng này), internal-api, core-worker | core-worker |
| `ledger.outbox` | gate | core-worker (chỉ-đọc schema `ledger`) |

## 2. Danh mục

| Type | Phát bởi | `data` | Trạng thái hóa đơn (CAS) | Việc khác của core-worker |
|---|---|---|---|---|
| `invoice.ingested` | core ingest | `{invoice_id, source, invoice_type, duplicate_of \| null}` (`duplicate_of` chỉ xuất hiện khi file khác `sha256` trùng khóa qua `email`/`bill_pay`/`scenario`; upload trùng trả `409` không lưu và không phát sự kiện; cùng `sha256` là no-op, không phát lại sự kiện) | — (ingest tạo hóa đơn ở `investigating` và job `queued` trong cùng transaction) | — |
| `job.progressed` | internal-api | `{job_id, task_type, attempt, type, step?, bot_id?, tool_id?, severity?, reason_code?, at}` (không mang chữ) | — | đẩy SSE job |
| `message.completed` | internal-api | `{conversation_id, message_id, job_id, status}` | — | đẩy SSE tenant cho người hỏi |
| `job.completed` | internal-api | `{job_id, task_type, invoice_id?, final_severity?, reason_codes?}` | — (internal-api đã ghi trong `:complete`) | QT-03 → `auto_pay_suspensions`; nếu `auto_pay_eligible` → tạo approval `mandate` rồi CAS `auto_pay_eligible → approved`; có mã chống gian lận → `indicator.flagged` |
| `invoice.status_changed` | core | `{invoice_id, from, to, severity}` | — | đẩy SSE tenant; `to = approved` mà chưa có lịch → đặt `scheduled_for` = `proposed_pay_on` của treasury hoặc hạn trả, CAS `approved → scheduled` |
| `approval.created` / `approval.superseded` | core | `{approval_id, invoice_id \| null, purchase_order_id \| null, method, reason?}` | — | audit |
| `goods_receipt.confirmed` | core | `{goods_receipt_id, purchase_order_id}` | hóa đơn gắn PO đang chờ `NO_GOODS_RECEIPT`: CAS `pending_approval → investigating` + job mới | nếu PO có escrow `held` và hóa đơn giải ngân đã có approval `channel = escrow` → `POST /gate/escrows/{id}:release` |
| `vendor_account.changed` | core | `{vendor_id, vendor_account_id, status, retired_account_id \| null}` | chỉ khi `status = verified`: hóa đơn `blocked` vì `PAYEE_CHANGE_REQUEST` của NCC → CAS `blocked → investigating` + job mới | — |
| `indicator.flagged` | core | `{indicators: [{kind, value_hash}], reason_codes, source: finding \| rail, source_ref}` (`source_ref` là mã mờ, không phải id hóa đơn/Finding) | — | tạo/gộp `alert` |
| `cross_alert.published` | console-api | `{cross_alert_id, indicators: [{kind, value_hash}], reason_codes}` | ở mọi tenant khác, hóa đơn khớp: thêm Finding hệ thống `CROSS_ALERT_HIT`; `approved`/`scheduled`/`auto_pay_eligible`/`pending_approval` → CAS sang `pending_approval` và approval → `superseded`. `new`/`investigating` không cần làm gì: kiểm tra hệ thống lúc `:complete` sẽ bắt | intent `authorized` → `POST /gate/intents/{id}:cancel {reason: CROSS_ALERT}`; `notification.created` |
| `cross_alert.withdrawn` | console-api | `{cross_alert_id}` | — | — |
| `hard_block.applied` | console-api | `{hard_block_id, indicators: [{kind, value_hash}]}` | hóa đơn chưa chi khớp → Finding hệ thống `OFFICIAL_FRAUD_LIST`, CAS sang `blocked`, approval → `superseded` | cancel intent `authorized` |
| `kill_switch.engaged` / `kill_switch.released` | console-api | `{kill_switch_id, scope, target_id}` | — | read model, thông báo |
| `payment.authorized` | gate | `{payment_intent_id, invoice_id, amount_vnd, channel}` | CAS `scheduled → paying` | — |
| `payment.executed` | gate | `{payment_intent_id, invoice_id, rail_txn_id, settled_at}` | CAS `paying → paid` | approval → `consumed` |
| `payment.failed` | gate | `{payment_intent_id, invoice_id, failure_code}` | CAS `paying → payment_failed`, rồi `payment_failed → pending_approval` | approval → `superseded` (cần duyệt lại); `notification.created` |
| `payment.denied` | gate | `{payment_intent_id, invoice_id, gate_reasons}` | CAS từ `scheduled`/`paying`: có `BLOCKED_INVOICE` hoặc `OFFICIAL_FRAUD_LIST` → `blocked`; còn lại → `pending_approval` | approval → `superseded`; `notification.created` |
| `payment.expired` | gate | `{payment_intent_id, invoice_id, reason}` | `AUTHORIZATION_TIMEOUT`: CAS `paying → scheduled` (lượt sau chi lại). `CROSS_ALERT`, `INVOICE_REINVESTIGATED`, `OWNER_CANCELLED`: **không đổi** (bên hủy đã ghi trạng thái) | — |
| `payment.stuck` | gate | `{payment_intent_id, invoice_id, executing_since}` | — | cảnh báo vận hành |
| `escrow.held` | gate | `{escrow_id, purchase_order_id, source_invoice_id \| null}` | `source_invoice_id`: CAS `blocked → escrow_held` | — |
| `escrow.released` | gate | `{escrow_id, release_invoice_id, source_invoice_id \| null}` | `release_invoice_id`: CAS sang `paid`. `source_invoice_id` khác hóa đơn giải ngân: CAS `escrow_held → rejected` (ghi chú "thay bằng hóa đơn giải ngân") | approval → `consumed` |
| `escrow.refunded` | gate | `{escrow_id, source_invoice_id \| null, reason}` | `source_invoice_id`: CAS `escrow_held → rejected` | `notification.created` |
| `escrow.failed` | gate | `{escrow_id, failure_code}` | `source_invoice_id` giữ `blocked` | approval → `superseded`; `notification.created` |
| `notification.created` | core | `{notification_id, kind, user_ids}` | — | đẩy SSE tenant |
| `bot.status_changed` | core | `{bot_id, version, from, to}` | — | audit |

Hết hạn cọc chỉ có **một** nguồn kích hoạt: core-worker thấy `expires_on` đã qua → `POST /gate/escrows/{id}:refund {reason: EXPIRED}`. PO bị hủy (`POST /m/purchase-orders/{id}:cancel`) → `:refund {reason: ORDER_CANCELLED}`.

## 3. SSE

```
event: bot.finished
id: evt_01JD…               # = event_id; client gửi lại qua Last-Event-ID khi nối lại
data: {"job_id":"job_…","bot_id":"procurement","severity":"yellow","at":"2026-11-26T09:15:04+07:00"}
```

| Luồng | Sự kiện | Kết thúc |
|---|---|---|
| `GET /m/jobs/{job_id}/events` | `supervisor.step`, `bot.started`, `bot.tool_called`, `bot.finished`, `bot.failed`, `answer.delta` (chỉ hỏi đáp), `job.completed` | sau `job.completed` |
| `GET /m/events` | `invoice.status_changed`, `notification.created`, `payment.updated` (loại riêng của SSE, gộp mọi `payment.*` thành `{invoice_id, payment_intent_id, status}`) | không; `: keep-alive` mỗi 15 s |

Xác thực: `EventSource` của trình duyệt không gửi được header, nên frontend dùng SSE qua `fetch` (thư viện `@microsoft/fetch-event-source`) để gửi `Authorization: Bearer`. Không đưa token vào query string. Store manager chỉ nhận sự kiện của hóa đơn thuộc quán mình.

SSE chỉ mang id, trạng thái, màu, mã lý do; **không có chữ `untrusted`**, trừ `answer.delta` (chữ câu trả lời đang viết, client hiển thị như untrusted và thay bằng bản đã kiểm khi `job.completed`). Server giữ sự kiện 10 phút để phát lại theo `Last-Event-ID`; quá hạn → `event: resync`, client tải lại bằng REST.
