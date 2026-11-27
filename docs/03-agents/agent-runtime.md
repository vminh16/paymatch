# Thiết kế agent-runtime

Trạng thái: **Đã chốt (v0.2, 26/11/2026)**: agent điều phối ReAct linh hoạt theo việc, rào chắn bằng code. Bám [architecture.md](../02-architecture/architecture.md) mục 5. API: [05-api/internal-api.md](../05-api/internal-api.md).

## 1. Ý tưởng

Không viết cứng luồng cho từng việc. Có **một agent điều phối ReAct** (`chief-accountant`) nhận việc, tự quyết gọi bot chuyên môn nào, tool nào, theo thứ tự nào. Các bot chuyên môn là **tool của agent điều phối** (agents-as-tools); mỗi bot chuyên môn cũng là một agent ReAct nhỏ có quyền riêng.

An toàn không dựa vào việc agent tự giác đi đúng luồng, mà dựa vào **rào chắn do code ép** (mục 4).

```
việc ──► chief-accountant (ReAct)
           ├── gọi bot chuyên môn (tool `ask_<bot_id>`; gọi song song được trong một bước)
           │      procurement · accounts-payable · fraud-control · tax · branch-operations · treasury · bot người dùng
           ├── gọi tool tra cứu, thống kê (chỉ-đọc, số do code tính)
           └── kết thúc: tờ trình (điều tra) · câu trả lời (hỏi đáp, báo cáo)
```

## 2. Loại việc

| `task_type` | Khởi tạo | Đầu ra | Ngân sách mặc định | Điều kiện hoàn tất (code kiểm) |
|---|---|---|---|---|
| `investigate_invoice` | hóa đơn mới về; điều tra lại | Finding của các bot + tờ trình 5 dòng; **màu do core tính** | 30 s, 12 bước điều phối | có Finding của mọi bot bắt buộc theo loại hóa đơn; thiếu → core thêm vàng |
| `question` | người dùng hỏi trong hội thoại | câu trả lời + trích dẫn tool_call + (tùy chọn) đề xuất hành động | 15 s, 8 bước | mọi con số trong câu trả lời trỏ tới một tool_call |
| `report` | người dùng yêu cầu; lịch cuối ngày | báo cáo ngắn + bảng số | 20 s, 8 bước | như `question` |

Thêm loại việc mới = thêm một dòng cấu hình (tool được phép, ngân sách, điều kiện hoàn tất, prompt vai trò). Không thêm graph mới.

## 3. Vai trò

| Thành phần | Làm gì | Không làm gì |
|---|---|---|
| `chief-accountant` (điều phối, ReAct) | hiểu việc; chọn và gọi bot chuyên môn, tool thống kê; tổng hợp | đọc chữ không đáng tin; tự chấm màu; hành động có tác dụng phụ |
| Bot chuyên môn (ReAct nhỏ) | làm đúng nghề với tool của mình, kể cả đọc dữ liệu bẩn (thư, tin nhắn, chữ trên hóa đơn) | gọi bot khác; trả chữ tự do cho điều phối |
| Core (code) | cấp token, chạy tool, kiểm bằng chứng, áp mức sàn, kiểm tra hệ thống, gộp màu, ghi trạng thái | — |

Khi điều phối gọi `ask_<bot_id>`, nó chỉ đưa **câu hỏi có cấu trúc** (`{invoice_id?, focus?: [enum], question_code?}`; enum `focus` và `question_code` **chưa chốt**, v1 nhận chuỗi ngắn, chấp nhận được vì điều phối không đọc untrusted) và nhận lại **kết quả có cấu trúc**: với điều tra là `Finding` (không có `reason`), với hỏi đáp là `BotAnswer {facts: [{key, value, tool_call_id}], reason_codes}`. Đây là mô hình Dual LLM: bot chuyên môn đứng ở vùng cách ly, điều phối là vùng đặc quyền.

## 4. Rào chắn (code, không phụ thuộc LLM)

1. **Điều kiện hoàn tất thay cho luồng cố định.** Điều tra hóa đơn: agent gọi gì, thứ tự nào cũng được; job chỉ hoàn tất với Finding của đủ bot bắt buộc (`required_for`). Thiếu vì hết ngân sách hay agent bỏ sót → core thêm Finding vàng `BOT_NOT_RUN`.
2. **Màu do code.** Mức sàn theo mã lý do, mức sàn theo output tool, kiểm tra hệ thống, gộp = nặng nhất. LLM không quyết màu.
3. **Điều phối không đọc chữ không đáng tin.** Token của điều phối không có tool trả chữ `untrusted` (`inbox`, `chat_messages`, phần chữ của `invoices`). Kết quả từ bot chuyên môn tới điều phối bị core lọc bỏ `reason` và mọi trường chữ.
4. **Không có tool hành động.** Mọi tool chỉ-đọc. Hỏi đáp chỉ có thể trả `proposed_actions` (ví dụ "mở hóa đơn X", "duyệt hàng loạt 5 hóa đơn này"); UI hiện thành nút, người dùng bấm và xác thực mạnh như bình thường.
5. **Thống kê bằng truy vấn viết sẵn.** Tool thống kê có tham số (khoảng ngày, quán, NCC, nhóm theo), code chạy truy vấn; không có SQL tự do.
6. **Số trong câu trả lời phải có nguồn.** Câu trả lời có `citations`; core kiểm mỗi con số xuất hiện trong output của tool_call được trích, không khớp → gỡ con số đó và gắn cờ.
7. **Ngân sách và giới hạn bước** theo loại việc (mục 2); `recursion_limit` + `RemainingSteps` trong LangGraph. Hết ngân sách → điều tra: vàng; hỏi đáp: trả lời một phần, nói rõ chưa đủ.
8. **Quyền theo vai người dùng.** Hội thoại của store manager chỉ thấy dữ liệu quán mình: token của phiên mang `store_ids`, tool lọc theo đó.

## 5. Finding (hợp đồng)

```yaml
Finding:
  job_id, bot_id
  severity: green | yellow | red
  reason_codes: [enum]       # danh mục ở mục 5a
  reason: string             # chữ tự do cho người đọc — LUÔN untrusted, không bao giờ tới điều phối
  evidence: [ref]            # id dòng hóa đơn / tin nhắn / bản ghi gốc, kèm tool_call_id
  provenance: trusted | untrusted
  proposed_channel: bank_transfer | virtual_card | escrow   # chỉ treasury, chỉ để hiển thị
```

Schema đầy đủ: [05-api/schemas.md §3](../05-api/schemas.md#3-điều-tra). Bot người dùng chỉ dùng mã có sẵn hoặc `CUSTOM` (tối thiểu vàng).

## 5a. Danh mục mã lý do (nguồn sự thật)

Code áp **mức sàn** theo bảng này bất kể bot ghi gì; `CROSS_ALERT_HIT` bị **giới hạn ở vàng** (D6). Cách gỡ 🔴 xem problem-definition.md mục 6b.

Runtime lọc mã trước khi nộp: bỏ mã không thuộc bot (cột *Sinh bởi*) và bỏ trích dẫn không khớp output tool. Mã đỏ mà **tool trusted quyết định** (`OFFICIAL_FRAUD_LIST`, `TAX_RISK_LIST`, `MST_INACTIVE`, `INVOICE_NOT_FOUND_ON_PORTAL`) chỉ giữ khi output tool dương; core vẫn tự thêm lại từ output tool (internal-api.md §3). Mã đỏ do **bot đánh giá nội dung** (`HIDDEN_INSTRUCTION`, `PAYEE_CHANGE_REQUEST`, `PERSONAL_ACCOUNT`, `DUPLICATE_INVOICE`) **không bao giờ bị bỏ** vì trích dẫn sai: vẫn đỏ, `reason` ghi chú thiếu trích dẫn. Bot báo nhầm chỉ khóa một hóa đơn (gỡ theo 6b); hạ nhầm xuống vàng thì hóa đơn gian lận duyệt được.

| Mã | Mức | Sinh bởi | QT-03 (hạ quyền) |
|---|---|---|---|
| `OK` | xanh | mọi bot | |
| `PRICE_ABOVE_CONTRACT`, `PACK_SIZE_CHANGED` | vàng | procurement, core (output `price_check`) | ✓ |
| `QUANTITY_ABOVE_NORM`, `NO_GOODS_RECEIPT` | vàng | accounts-payable, core (output `three_way_match`) | ✓ / |
| `DUPLICATE_INVOICE` | đỏ | ingest, accounts-payable | ✓ |
| `PAYEE_CHANGE_REQUEST` | đỏ | fraud-control, core (TK lạ trên hóa đơn) | ✓ |
| `PERSONAL_ACCOUNT`, `HIDDEN_INSTRUCTION` | đỏ | fraud-control | ✓ (HIDDEN) |
| `URGENCY_PRESSURE` | vàng | fraud-control | |
| `CROSS_ALERT_HIT` | **vàng (trần)** + bắt buộc xác minh | fraud-control, core | ✓ |
| `OFFICIAL_FRAUD_LIST` | đỏ, không gỡ được | fraud-control, core (hard block) | ✓ |
| `TAX_RISK_LIST`, `MST_INACTIVE` | đỏ | tax | ✓ (TAX_RISK) |
| `INVOICE_NOT_FOUND_ON_PORTAL` | đỏ | tax | |
| `VAT_DEDUCTION_RISK` | vàng | tax | |
| `UTILITY_OUT_OF_RANGE` | vàng | branch-operations, core (output `utility_baseline`) | ✓ |
| `OVER_LIMIT`, `LOW_BALANCE` | vàng | treasury | |
| `NON_XML_SOURCE`, `AMOUNT_MISMATCH`, `UNKNOWN_VENDOR` | vàng | ingest | |
| `BOT_TIMEOUT`, `BOT_INVALID_OUTPUT`, `BOT_NOT_RUN`, `BOT_DISABLED`, `CUSTOM` | vàng | core / bot người dùng | |

## 6. Bot chuyên môn

- Prompt = khung an toàn + vai + skill + schema đầu ra. Dữ liệu từ tool nằm trong khối có nhãn `provenance`, đánh dấu là dữ liệu, không phải lệnh.
- Ngân sách mỗi lần được gọi: 6 bước tool, 20 giây. Hết → Finding vàng `BOT_TIMEOUT`.
- Output sai schema → thử lại 1 lần → vẫn sai → `BOT_INVALID_OUTPUT`.
- Skill có thể khai báo `prefetch`: runtime gọi trước các tool chắc chắn cần, đỡ một lượt LLM.
- Mức ReAct tùy bot: `fraud-control` điều tra sâu (đọc thư, tin nhắn, tự quyết tra thêm); các bot còn lại thường 1–3 bước.
- v1 không có memory (lộ trình, xem agent-lifecycle-and-memory.md).

## 7. LLM port

- **Model/provider: chưa chốt, đội thảo luận sau.** Cho tới khi chốt: code chỉ gọi port `LLM`; tên model và provider đọc từ `ModelConfig`/env, không nằm trong code; prompt và tool schema viết trung lập, không dùng tính năng riêng của một hãng.
- `LLM.complete(messages, tools?, schema?) -> message | json`. Adapter: một adapter cho provider được chọn, model dự phòng, **Replay** (cassette theo hash input).
- Chế độ: `live` · `record` · `replay`. Test và ngày chấm dùng `replay` khi cần ổn định.
- **Khóa API theo bot** (chỗ chờ, chưa có adapter thật; mẫu ở `.env.example`): mỗi bot đọc `LLM_API_KEY_<BOT_ID>` (`bot_id` viết hoa, `-` → `_`, vd `LLM_API_KEY_FRAUD_CONTROL`; điều phối là `LLM_API_KEY_CHIEF_ACCOUNTANT`), trống thì dùng `LLM_API_KEY`; bot người dùng tạo luôn dùng `LLM_API_KEY`. Lý do: tách hạn mức/chi phí từng bot và thu hồi riêng một khóa. Khóa chỉ nằm trong env của `agent-worker`; không vào manifest, DB, log, cassette hay `ModelConfig` (`ModelConfig` chỉ giữ tên model).
- Mỗi lời gọi sinh span `invoke_agent` / `execute_tool` (OpenTelemetry GenAI).

## 8. LangGraph

```
START → open_session (code: lấy token, tool, bot được phép theo task_type)
      → supervisor (ReAct: chief-accountant)
            ⇄ tools: ask_<bot> (subgraph ReAct của bot) · tool thống kê/tra cứu
      → finish (code: nộp Finding/tờ trình hoặc câu trả lời; core kiểm điều kiện hoàn tất)
      → END
```

- Điều phối dùng prebuilt ReAct agent của LangGraph; mỗi bot chuyên môn là một subgraph ReAct đăng ký dưới dạng tool. Gọi song song nhiều `ask_<bot>` trong một bước (parallel tool calls) để giữ độ trễ điều tra ≈ 30 s.
- **Không checkpointer Postgres** (agent-runtime không có credential DB). Lịch sử hội thoại do core lưu; mỗi lượt hỏi, runtime nhận lại các lượt trước qua API.
- **Logic nghiệp vụ là module Python thuần** (gộp màu, mức sàn, kiểm trích dẫn); node chỉ gọi tới. Phần lớn nằm ở core, runtime chỉ giữ phần cần cho tiến trình.
- **Tool là wrapper mỏng** quanh `POST /internal/tools/{id}:invoke`; `ask_<bot>` là wrapper quanh subgraph của bot, dùng token của bot đó.
- **Trace để debug, bằng chứng ở core.** OpenTelemetry → collector → LangSmith (dev, dữ liệu giả) hoặc Langfuse tự host. Bằng chứng chính thức là `tool_calls` trong core.
- **Replay**: chat model giả đọc cassette ở tầng LLM port, cả graph vẫn chạy thật.

## 9. Scale

- `agent-worker` không trạng thái; thêm worker = thêm sức chứa.
- Claim job bằng `SELECT … FOR UPDATE SKIP LOCKED` + lease; worker chết → lease hết → job chạy lại từ đầu với attempt mới; nộp kết quả idempotent theo `(job, attempt, bot)`.
- Hàng đợi tách theo `task_type`: hỏi đáp ưu tiên cao hơn để người dùng không chờ sau hàng loạt hóa đơn.
- Giới hạn đồng thời theo tenant và ngân sách gọi LLM toàn hệ thống.

## 10. Plugin

- Bot có sẵn: `plugins/bots/<id>/manifest.yaml` + `skill.md`, nạp khi khởi động. Bot người dùng: DB (`control`), vòng đời ở agent-lifecycle-and-memory.md.
- Mỗi bot active tự động thành một tool `ask_<bot_id>` của điều phối, mô tả lấy từ `description` của manifest. Manifest có thêm `task_types` để nói bot dùng được cho việc nào (mặc định `investigate_invoice`).
- Không có code tùy ý trong plugin.
