# Repo, test và scale

Trạng thái: **Đã chốt (26/11/2026)**.

## 1. Cấu trúc repo (monorepo, uv workspace)

```
paymatch/
├── docs/
├── contracts/                    # NGUỒN SỰ THẬT — sửa ở đây trước, code sau
│   ├── openapi/core-merchant.yaml    # /m/*
│   ├── openapi/core-console.yaml     # /console/*
│   ├── openapi/core-internal.yaml    # /internal/* (claim job, tools, findings, manifests)
│   ├── openapi/gate.yaml             # evaluate, intents, execute, escrows
│   ├── openapi/sim-world.yaml        # identity, rails, inbox, bills, chat, tax, simo, scenario
│   ├── schemas/                      # finding, bot-manifest, tool-result, capability-token
│   └── events/                       # indicator.flagged, payment.executed, cross_alert.published, ...
├── packages/
│   ├── contracts-py/             # model sinh từ contracts/ (không sửa tay)
│   └── paymatch-hashing/         # intent_hash, payload_hash, action_hash (RFC 8785 + sha256), test vector ở contracts/test-vectors/
├── services/
│   ├── core/
│   │   ├── src/core/{ingest,merchant,risk,control,tools}/{domain,application,adapters}/
│   │   ├── src/core/entrypoints/{merchant_api,console_api,internal_api,worker}.py
│   │   ├── migrations/           # schema core, risk, control
│   │   └── tests/
│   ├── agent-runtime/
│   │   ├── src/agent_runtime/{session,supervisor,bots,tools,llm,plugins}/
│   │   └── tests/
│   ├── payment-gate/
│   │   ├── src/gate/{domain,application,adapters}/
│   │   ├── migrations/           # schema ledger
│   │   └── tests/
│   └── sim-world/                # chỉ demo/test: /rails, /simo, /einvoice, /tax-id, /inbox, /chat, /scenario
│       ├── src/sim_world/
│       └── data/                 # XML HĐĐT mẫu + JSON kịch bản (BRD mục 14 + ca tấn công)
├── plugins/bots/<id>/{manifest.yaml,skill.md}   # 6 bot có sẵn
├── eval/                         # 36 ca × 3 cấu hình, cassette LLM
├── tests/architecture/           # test ranh giới import giữa service (đã có)
├── tests/e2e/                    # các luồng v1 (F1–F9, F11, F12) trên docker compose
├── infra/docker-compose.yml      # postgres, core (4 tiến trình), agent-worker, gate, sim-world, otel collector
├── pyproject.toml                # uv workspace
└── Makefile                      # up · down · reset · test · test-e2e · eval · contracts
```

Quy tắc phụ thuộc (có test kiểm tra import):
- `services/*` chỉ import `packages/*`; **không** import lẫn nhau.
- `domain/` không import `adapters/`.
- `agent-runtime` không có driver Postgres trong dependency.

## 2. Phân công gợi ý (3 người)

| Người | Sở hữu | Ghi chú |
|---|---|---|
| A | `services/core` (merchant, risk, control, tools) + console-api | Nhiều endpoint nhất |
| B | `services/agent-runtime` + `plugins/bots` + `eval` | Chất lượng agent |
| C | `services/payment-gate` + `services/sim-world` + `infra` + `tests/e2e` | An toàn tiền + dữ liệu demo |

`contracts/` là sở hữu chung: đổi contract cần người còn lại xem.

## 3. Chiến lược test

| Tầng | Chạy | Ví dụ | Khi nào |
|---|---|---|---|
| **Unit domain** | pytest, không I/O | parse XML HĐĐT (tổng, trùng, dòng hàng); gộp Finding; quy tắc Gate (hạn mức, mandate, QT-03); state machine hóa đơn/escrow/case | Mọi commit |
| **Bất biến** | pytest + DB test | xem mục 4 | Mọi commit |
| **Contract** | Schemathesis trên OpenAPI; validate event/Finding theo JSON Schema | API trả đúng schema; input sai bị chặn | Mọi commit |
| **Agent (logic)** | FakeLLM viết sẵn kịch bản | điều phối bỏ sót bot bắt buộc → vàng `BOT_NOT_RUN`; timeout → vàng; output sai schema → vàng; tool ngoài token → 403; điều phối xin tool `inbox` → bị từ chối | Mọi commit |
| **Agent (hành vi)** | Replay cassette | 6 ca BRD mục 14 ra đúng màu và đúng `reason_codes` | Mọi commit |
| **E2E** | docker compose | F1–F9, F11, F12; đủ 6 kịch bản + Bẫy cuối của BRD mục 14 | Trước khi merge vào main |
| **Eval** | LLM live, 36 ca điều tra × 3 cấu hình (1 agent / + khóa cứng / đầy đủ) + ~20 câu hỏi đáp có đáp án số | MT1–MT6; hỏi đáp: đúng số, có trích dẫn, không lộ quán khác | Tay, trước demo |

## 4. Test bất biến (bắt buộc, không được skip)

| # | Bất biến | Test |
|---|---|---|
| 1 | Bot là ranh giới quyền | gọi tool không có trong capability token → 403; token hết hạn → 401; token job A đọc job B → 403 |
| 2 | Không agent nào chi tiền | `agent-runtime` không có biến môi trường DB; không có route tới gate trong network compose; import Postgres trong agent-runtime → fail |
| 3 | Payee từ danh bạ | hóa đơn/tin nhắn chứa số TK khác → ledger vẫn ghi TK danh bạ hoặc từ chối |
| 5 | Gộp đơn điệu | property test: thêm Finding bất kỳ không bao giờ làm mức nhẹ đi |
| 4 | Bot không nói chuyện trực tiếp | capability token không có tool nào trỏ tới bot khác; agent-runtime không có route giữa các bot (một bot chỉ nhận ToolResult và trả Finding) |
| 7 | Tiền do code tính | Finding chứa số tiền khác số do tool tính → bị bỏ qua; Gate chỉ dùng số trong `invoices` |
| — | Mức sàn theo mã lý do | bot ghi `HIDDEN_INSTRUCTION` kèm severity xanh → kết quả vẫn đỏ; `CROSS_ALERT_HIT` đơn lẻ → vàng |
| — | 🔴 không chi | hóa đơn `blocked` → Gate DENY kể cả có approval |
| — | Không chi số ≤ 0 | hóa đơn tổng âm hoặc 0 đ (kể cả có approval) → Gate DENY `NON_POSITIVE_AMOUNT`; core đặt `no_payment_due`, không vào hàng chờ duyệt |
| — | Cảnh báo chéo sau duyệt | hóa đơn `scheduled` + cross_alert.published → quay về `investigating`; Gate DENY nếu approval không có xác minh |
| — | Escrow | TK `escrow_only` nhận chuyển khoản thường → DENY; giải ngân thiếu phiếu nhập → DENY |
| — | Trần nền tảng | mandate đặt 40 triệu/HĐ → tự chi vẫn chặn ở 30 triệu |
| 9 | Lỗi = vàng | bot crash/timeout/sai schema → mức ≥ vàng |
| 10 | Gate fail-closed | policy không đọc được → từ chối |
| — | Gate chỉ ra lệnh | rail từ chối (sim-world trả lỗi) → ledger ghi `failed`, không ghi `paid` |
| — | Đối soát *(lộ trình, F10)* | tạo lệch giả giữa ledger và rail → có `reconciliation.mismatch` |
| — | Approval cũ | điều tra lại / chi thất bại / cảnh báo chéo → approval `superseded`; Gate từ chối approval không `active` hoặc không thuộc job mới nhất |
| — | Lease | token và Finding của attempt cũ → `409 LEASE_LOST` |
| — | Kiểm tra hệ thống | runtime nộp `OK` cho mọi bot, hóa đơn có cảnh báo chéo / TK lạ → vẫn vàng/đỏ |
| — | Hỏi đáp chỉ-đọc | không tool nào trong phiên `question` có tác dụng phụ; câu trả lời có số không có trong tool_call → số bị gỡ; store manager hỏi quán khác → 0 kết quả |
| 6 | Điều phối không đọc untrusted | token điều phối không chứa `inbox`/`chat_messages`; kết quả `ask_<bot>` không có `reason` |
| 11 | Chi tối đa một lần | 2 lệnh execute song song cùng invoice → đúng 1 dòng ledger |
| — | Hạn mức ngày | 2 hóa đơn 30tr tự chi song song cùng ngày → chỉ 1 được chi (khóa dòng ngân sách ngày) |
| — | RLS | role merchant tenant A truy vấn hóa đơn tenant B → 0 dòng |
| — | Console | role staff đọc bảng hóa đơn trực tiếp → bị từ chối |

## 5. Scale

| Điểm nghẽn | Cách xử lý |
|---|---|
| Gọi LLM (chậm, đắt, giới hạn rate) | Thêm `agent-worker`; ngân sách LLM toàn hệ thống; giới hạn đồng thời theo tenant; cache/replay |
| Job queue | Postgres `SKIP LOCKED` + lease; đủ cho hàng nghìn job/phút; thay bằng queue riêng khi cần mà không đổi contract `/internal/jobs` |
| API merchant | `merchant-api` không trạng thái, scale ngang |
| Console đọc nặng | Read model do `core-worker` dựng từ event; không đụng luồng duyệt chi |
| Gate | Một writer cho ledger; khóa theo (tenant, ngày) cho hạn mức; idempotency theo invoice |
| Dữ liệu lớn | Mọi bảng có `tenant_id`; sau này phân vùng theo tenant hoặc tách `risk` thành DB riêng (đã chỉ giao tiếp qua event) |

## 6. CI

`make test` = lint + type check + unit + bất biến + contract + agent (fake/replay). Test DB (bất biến của Gate) tự bật Postgres 16 bằng `testcontainers`, nên máy chạy `make test` (kể cả CI) **phải có Docker**. `make test-e2e` trước merge vào main. `make eval` chạy tay. Không có test gọi LLM live trong CI.

## 7. Quy ước đặt tên

- **Mọi định danh trong contract, code, DB, event, manifest đều bằng tiếng Anh**: field, enum, tên tool, bot ID, trạng thái, tên bảng, tên event.
- Tiếng Việt chỉ nằm ở **giá trị hiển thị** (`name`, `description` của bot, nội dung `skill.md`, chuỗi UI, `reason` cho người đọc) và trong docs.
- Kiểu viết: field/enum value/tool/bảng `snake_case`; mã lý do `UPPER_SNAKE_CASE`; bot ID `kebab-case`; event `noun.past_tense` (`payment.executed`).

| Khái niệm | Định danh |
|---|---|
| Mức xanh/vàng/đỏ | `severity: green \| yellow \| red` |
| Mã lý do / lý do / bằng chứng / nhãn nguồn | `reason_codes`, `reason`, `evidence`, `provenance` |
| Kênh trả: lệnh chi / thẻ ảo / cọc tạm giữ | `bank_transfer`, `virtual_card`, `escrow` |
| Trạng thái hóa đơn | `new`, `investigating`, `pending_approval`, `auto_pay_eligible`, `blocked`, `approved`, `scheduled`, `paying`, `paid`, `payment_failed`, `escrow_held`, `no_payment_due`, `rejected` |
| Trạng thái TK NCC | `verified`, `escrow_only`, `retired` |
| Trạng thái bot | `draft`, `pending_review`, `active`, `disabled`, `archived` (lộ trình: `shadow`) |
| Trạng thái cọc | `held`, `released`, `refunded` |
| Tool | xem danh mục ở [tools.md](../03-agents/tools.md) (nguồn sự thật) |
| Mã lý do | xem [agent-runtime.md mục 5a](../03-agents/agent-runtime.md) (nguồn sự thật) |
| Bot | `chief-accountant`, `procurement`, `accounts-payable`, `fraud-control`, `tax`, `branch-operations`, `treasury` |
| Loại hóa đơn | `invoice_type`: `goods`, `utility`, `software`, ... |
| Indicator | `account_hash`, `tax_id`, `phone`, `card_id`, `merchant_id` |
