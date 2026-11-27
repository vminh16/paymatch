# Kiến trúc PayMatch

Trạng thái: **Đã chốt (v0.3, 26/11/2026)**. Phạm vi v1 ở [problem-definition.md mục 6c](../01-requirements/problem-definition.md). Thay đổi phải cập nhật tài liệu này (mục 9).

Tài liệu liên quan: [problem-definition.md](../01-requirements/problem-definition.md) (đọc trước) · [flows.md](flows.md) (các luồng) · [data-model.md](data-model.md) · [payment-gate.md](payment-gate.md) · [repo-and-testing.md](repo-and-testing.md) (repo, test, scale) · [agent-runtime.md](../03-agents/agent-runtime.md) (thiết kế agent) · [agent-roster.md](../03-agents/agent-roster.md) · [bot-manifest.md](../03-agents/bot-manifest.md)

## 1. Bối cảnh

Chuỗi F&B 15 quán + 1 bếp trung tâm (~45 NCC, ~550 hóa đơn/tháng, ≤ 100 lao động có BHXH; xem [persona.md](../04-data/persona.md)) có 1 chủ chuỗi, 2 kế toán, 15 quản lý quán và 1 quản lý bếp trung tâm, nhưng vẫn phải gánh việc của khoảng 6 vai trong một phòng tài chính. PayMatch là **phòng kế toán ảo**: mỗi agent là một vai nghề thật, mang checklist nghề, tool và giới hạn quyền của vai đó. Phía MoMo có **console** để giám sát rủi ro toàn mạng lưới và quản trị bot.

Một câu: *AI điều tra, tổng hợp và trả lời; người quyết; code chi tiền.*

## 2. Bốn mặt phẳng (logic)

| Mặt phẳng | Chủ | Nội dung |
|---|---|---|
| **Merchant plane** (data plane) | Từng cửa hàng (tenant) | Hóa đơn, 6 bot + Kế toán trưởng điều phối, Finding, thẻ duyệt, mandate, hỏi đáp |
| **Risk intelligence plane** | MoMo | Indicator (TK băm, MST, SĐT, thẻ, merchant), hàng chờ cảnh báo, case, cảnh báo chéo, tra SIMO giả lập. Lộ trình: gom cụm, điểm rủi ro, đồ thị thực thể, báo cáo SIMO |
| **Control plane** | MoMo | Tenant, tool registry, duyệt template bot, policy & kill switch, cấu hình model, RBAC nhân viên |
| **Payment plane** | Payment Gate | Kiểm mandate/policy, token một lần, ledger |

Merchant plane chỉ gửi **indicator** sang risk plane (qua outbox), **không gửi nội dung hóa đơn**. Cửa hàng khác chỉ thấy "TK này bị gắn cờ trên mạng lưới MoMo", không thấy cửa hàng nào gắn.

### Đầu vào: hóa đơn điện tử

Đầu vào chính của hệ thống là **hóa đơn**. Mọi job đều bắt đầu từ một hóa đơn; các nguồn khác (hợp đồng, đơn hàng, phiếu nhập, tin nhắn, tra cứu thuế…) chỉ là ngữ cảnh để bot điều tra.

| Kênh vào (BR-01, BR-14, BR-15) | Định dạng | Ghi chú |
|---|---|---|
| Email nhận hóa đơn riêng của chuỗi | XML hóa đơn điện tử đính kèm (+ PDF bản thể hiện) | Thân email là nội dung **untrusted** đi kèm, gắn vào hóa đơn |
| Tải lên | XML | |
| Dịch vụ thanh toán hóa đơn của MoMo | Hóa đơn điện, nước | `invoice_type = utility` |
| Ảnh / PDF không có XML | Trích bằng model đọc tài liệu | **Luôn tối thiểu vàng** (`NON_XML_SOURCE`) |
| Cổng HĐĐT của cơ quan thuế | XML | Lộ trình (BR-15) |

Module **`ingest`** (code xác định, không phải agent):
1. Lưu **file gốc bất biến** (hash SHA-256) — mọi bằng chứng trỏ về đây.
2. Parse XML theo định dạng HĐĐT (người bán: tên, MST, TK nếu có; ký hiệu, số, ngày; dòng hàng: tên, đơn vị, số lượng, đơn giá, thành tiền, thuế suất; tổng tiền). Định dạng cụ thể đối chiếu với file XML mẫu thật trước khi code.
3. Kiểm tra bằng code: **idempotency theo `(tenant_id, sha256)` chạy trước** — nếu đúng cùng file đã nạp cho tenant rồi (ví dụ `core-worker` poll lại hộp thư kiểu at-least-once) thì là no-op trả về hóa đơn đã có, không tạo hóa đơn trùng hay `DUPLICATE_INVOICE`; kế đến kiểm tổng các dòng = tổng tiền ([einvoice-xml.md §4](../04-data/einvoice-xml.md#4-ánh-xạ-sang-paymatch-và-quy-tắc-kiểm-tra-ingest)); chống trùng theo `(MST người bán, ký hiệu, int(số))` cho **file khác (`sha256` khác)** (`email`/`bill_pay`: lưu kèm `duplicate_of` + Finding đỏ `DUPLICATE_INVOICE`; `upload`: trả `409 DUPLICATE_INVOICE` kèm `existing_invoice_id`, không lưu); kiểm người bán có trong vendor registry chưa. Lỗi giữ lại → Finding hệ thống `bot_id = ingest` (`AMOUNT_MISMATCH`, `DUPLICATE_INVOICE`, `UNKNOWN_VENDOR`).
4. Lưu `invoices` + `invoice_lines` đã chuẩn hóa, phân loại `invoice_type`, tạo job.

Nhãn nguồn: **số** do code parse từ XML được dùng để tính tiền; **chữ** do người bán viết (tên hàng, ghi chú, thân email) luôn là `untrusted` — đây là chỗ câu lệnh giấu có thể nằm. Số TK trên hóa đơn (nếu có) **chỉ dùng để so** với vendor registry, không bao giờ để trả tiền.

Việc của AI với hóa đơn không phải OCR: bot `procurement` khớp tên hàng ghi tự do với mặt hàng trong hợp đồng và tách quy cách; code tính đơn giá/cái; các bot khác điều tra người nhận, thuế, chứng từ quanh hóa đơn đó.

## 3. Service và tiến trình (vật lý)

Kiểu **service-based architecture**: vài service thô theo miền, một Postgres chia schema, mỗi schema đúng **một** service được ghi.

| Image | Tiến trình | Mở ra | Auth | Quyền DB |
|---|---|---|---|---|
| `core` | `merchant-api` (`/m/*`) | Public | MoMo Doanh Nghiệp | role `merchant`: ghi `core` và bot tenant trong `control` (`bot_definitions`, `bot_versions`, `skills`), **RLS bắt buộc theo tenant** |
| `core` | `console-api` (`/console/*`) | **Chỉ mạng nội bộ** | SSO nhân viên + RBAC | role `staff`: đọc/ghi `risk`, `control`; **không đọc thẳng bảng hóa đơn** (chỉ qua endpoint tra bằng chứng có mã ticket, ghi log) |
| `core` | `internal-api` (`/internal/*`) | Chỉ mạng service | mTLS/khóa service + **capability token** theo job | role `merchant` (RLS) |
| `core` | `core-worker` | — | — | outbox, tạo alert, đánh giá lại khi có cảnh báo chéo (F3), chạy lịch chi (`scheduled_for`), read model console |
| `agent-runtime` | `agent-worker` (scale ngang) | Không mở cổng | gọi `internal-api` | **Không có credential DB** |
| `payment-gate` | `gate` | Chỉ mạng service | khóa service | ghi `ledger` (chỉ mình nó); đọc `core`, `control`, `risk` |
| `sim-world` | `sim-world` (chỉ demo/test) | Chỉ mạng service | khóa service | **Không dùng Postgres**; dữ liệu JSON nạp vào bộ nhớ, reset = nạp lại |

`sim-world` giả lập **thế giới bên ngoài**: hạ tầng thanh toán (`/rails`: chuyển tiền, thẻ ảo, cọc tạm giữ), **hộp thư nhận hóa đơn (email + XML HĐĐT)**, dịch vụ thanh toán hóa đơn điện nước, SIMO, cổng HĐĐT, tra cứu MST, Zalo, doanh thu MoMo, và `/scenario` để điều khiển demo (đẩy hóa đơn, kẻ gian quẹt thẻ, reset). Gate chỉ **ra lệnh** qua port `PaymentRail`; sim-world mới **giữ và chuyển tiền**. Triển khai thật: thay adapter bằng MoMo/ngân hàng/thuế thật, bỏ sim-world.

Ghi chú: `merchant-api`, `console-api`, `internal-api` là cùng một codebase, khác router được mount. Ngay từ v1 chạy thành **ba container cùng image**, mỗi cái một cổng và một tiền tố (8001 `/m`, 8002 `/console`, 8003 `/internal`), để console và internal không bao giờ lộ chung cổng với merchant. Cổng và hợp đồng API: [05-api/README.md](../05-api/README.md).

```
            web merchant            web console (nội bộ)
                 │                         │
           merchant-api              console-api
                 └──────── core (modules: ingest · merchant · risk · control · tools) ────────┐
                              │  internal-api                                         │
       claim job / tools / Finding (capability token)                         Postgres
                              │                                         schema core · risk · control
                        agent-runtime ──► LLM provider (+ dự phòng, + replay)      schema ledger
                                                                                     ▲
  chủ chuỗi Duyệt ──► core ──► payment-gate (/intents, :execute) ───────────────────┘
                                      │ PaymentRail                tools ──► ToolProvider
                                      ▼                                      ▼
                                   sim-world  (/rails · /simo · /einvoice · /inbox · /chat · /scenario)
```

## 4. Bên trong mỗi service: hexagonal

```
domain/        thuần Python, không I/O: quy tắc Gate, gộp Finding, state machine, tính tiền
application/   use case: nhận hóa đơn, chạy job, duyệt, chi, mở case, gắn cảnh báo chéo
ports/         interface: Repo, ToolProvider, LLM, Clock, SIMO, Ledger
adapters/      http (FastAPI), postgres, llm (theo provider, chưa chốt + replay), sim-world, simo-fake
```

Domain không import adapter. Mọi test nghiệp vụ chạy trên domain + adapter giả, không cần DB hay LLM.

## 5. Ranh giới tin cậy (bất biến — mỗi điều có test, xem repo-and-testing.md)

1. **Bot là ranh giới quyền.** Bot chỉ gọi tool có trong capability token của job; ngoài danh sách → 403. Toàn bộ tool chỉ-đọc.
2. **Không agent nào chi tiền.** agent-runtime không có credential DB, không gọi được Gate. Chỉ core gọi Gate sau khi có duyệt hoặc mandate tự chi.
3. **Tài khoản nhận tiền chỉ lấy từ danh bạ NCC đã xác minh** — Gate tự đọc lại, không nhận số TK từ request.
4. **Bot không nói chuyện trực tiếp với nhau.** Chỉ nộp Finding cho core.
5. **Gộp đơn điệu bằng code:** mức cuối = mức nặng nhất. LLM không quyết màu.
6. **Kế toán trưởng (LLM) không đọc nội dung không đáng tin:** chỉ đọc trường có cấu trúc của Finding (`severity`, `reason_codes`, `evidence`), không đọc `reason` tự do.
7. **Mọi con số tiền do code tính** từ dữ liệu gốc.
8. **Memory chỉ là gợi ý**, chỉ được tăng mức nghi ngờ.
9. **Lỗi = vàng, không bao giờ xanh:** bot lỗi, quá thời gian, output sai schema, thiếu bot bắt buộc → Finding vàng.
10. **Gate fail-closed:** không đọc được policy/kill switch → không chi.
11. **Mỗi hóa đơn chi tối đa một lần:** ràng buộc duy nhất trong DB ledger.

## 6. Mandate và chế độ chi

Theo tinh thần AP2: chủ chuỗi ký **mandate** (chế độ: chỉ đối soát / hỏi trước khi chi / tự chi; ≤ 30 triệu/HĐ, ≤ 50 triệu/ngày; danh sách NCC được tự chi). Bật tự chi cần xác thực mạnh (QT-06). Không có "Always allow" cho thanh toán. Tự hạ quyền theo QT-03. Kill switch của MoMo là policy flag Gate đọc.

## 7. Console MoMo

| Vai | Việc | Cơ chế |
|---|---|---|
| Chuyên viên rủi ro | Hàng chờ cảnh báo, case, gắn cảnh báo chéo, bật kill switch | v1: hàng chờ theo thời gian, case đơn giản. Lộ trình: điểm rủi ro, gom cụm, đồ thị |
| Trưởng nhóm rủi ro | Duyệt gỡ kill switch, duyệt chặn cứng | Maker-checker (người đề xuất ≠ người duyệt) |
| CSKH | Tra bằng chứng khi khiếu nại | Mã ticket bắt buộc; ghi log mọi lần xem; che PII mặc định. Lộ trình: break-glass |
| Quản trị nền tảng | Quản lý tool registry, tắt bot | Chỉ số chất lượng bot. Lộ trình: duyệt template marketplace |
| Tuân thủ *(lộ trình)* | Chỉ đọc audit, báo cáo SIMO | Audit chỉ-ghi-thêm |

| Hành động | Hệ quả | Quyền |
|---|---|---|
| Cảnh báo chéo | Mềm: hóa đơn chưa chi của cửa hàng khác được đánh giá lại, ra 🟡 bắt buộc xác minh (F3) | 1 chuyên viên |
| Chặn cứng | Chỉ theo danh sách chính thức (SIMO, thuế) | Maker-checker |
| Kill switch (indicator / cửa hàng / bot / tool / tắt tự chi toàn mạng) | Gate chặn | **Bật: 1 người** (khẩn cấp). **Gỡ: maker-checker** |

Quan sát agent: mỗi job sinh trace theo OpenTelemetry GenAI (`invoke_agent`, `execute_tool`); console xem được "bot nào, tool nào, bằng chứng gì" cho mọi quyết định.

## 8. Ngoài phạm vi

- Phạm vi v1 và danh sách lộ trình: [problem-definition.md mục 6c](../01-requirements/problem-definition.md).
- Không làm: người dùng cắm tool/MCP mới; bot nhắn trực tiếp nhau; nguồn vào thật (chỉ adapter giả lập); agent phía MoMo.
- Frontend v1 (hàng chờ duyệt, thẻ duyệt 5 dòng, console tối thiểu, nút reset) trong phạm vi; thiết kế UI bàn riêng.

## 9. Quyết định đã chốt và lý do

| Ngày | Quyết định | Lý do |
|---|---|---|
| 26/11/2026 | Multi-agent **chuyên môn hóa theo vai nghề**, 6 vai (Thu mua và Công nợ tách riêng) | Chủ chuỗi gánh việc của cả phòng tài chính; bài toán chia song song được (Kim et al. 2025) |
| 26/11/2026 | Có **Kế toán trưởng** điều phối trung tâm | Điều phối trung tâm chặn lỗi lan 4,4× so với 17,2× (Kim et al. 2025) |
| 26/11/2026 | **Thanh toán không do agent nào thực hiện**; Thủ quỹ chỉ đề xuất; Payment Gate (code) thực thi | Tách bạch nhiệm vụ (người duyệt ≠ người chi); AP2 tách payment mandate khỏi agent |
| 26/11/2026 | **Bot là ranh giới quyền**; tool chỉ chọn trong registry chỉ-đọc | Ngược Grok Bot (dùng tài khoản làm ranh giới, bot chung credential) |
| 26/11/2026 | **Bot không nhắn trực tiếp nhau** (chỉ qua Kế toán trưởng, sau khi core lọc); nhãn nguồn gốc theo mọi Finding | *Can CaMeLs Talk?* (2026) |
| 26/11/2026 | **Gộp = mức nặng nhất**, bằng code | Tranh luận có thể hội tụ sai mà tự tin (Du et al. 2024) |
| 26/11/2026 | Tạo bot qua **form** (v1) hoặc chat (lộ trình), cùng manifest, chủ chuỗi duyệt | Không bot nào tự cấp tool |
| 26/11/2026 | **Thế giới giả lập** thay nguồn vào thật | Demo sandbox; agent điều tra qua tool |
| 26/11/2026 | Không "Always allow" cho thanh toán | QT-06 |
| 26/11/2026 | **4 mặt phẳng**; risk plane chỉ nhận indicator | Bảo vệ dữ liệu; mô hình chia sẻ tín hiệu bằng định danh băm của các consortium chống gian lận |
| 26/11/2026 | **Service-based architecture**: 3 image nghiệp vụ (`core`, `agent-runtime`, `payment-gate`) + `sim-world` cho demo/test, 1 Postgres chia schema, mỗi schema một chủ ghi | Đội 3 người; tách theo ranh giới tin cậy và kiểu tải, không tách theo bot (Richards & Ford; Fowler MonolithFirst) |
| 26/11/2026 | **agent-runtime không có credential DB**; chỉ gọi `internal-api` bằng capability token theo job | Hạ tầng đảm bảo "bot là ranh giới quyền"; agent bị chiếm chỉ đọc được một job trong vài phút |
| 26/11/2026 | Console là tiến trình riêng của `core`, chỉ mạng nội bộ, DB role riêng | Lỗi phía merchant không chạm chức năng xem chéo nhiều cửa hàng |
| 26/11/2026 | Finding có `reason_codes` (enum) tách khỏi `reason` (chữ tự do, untrusted); Kế toán trưởng LLM chỉ đọc enum | `reason` do bot viết sau khi đọc dữ liệu bẩn, có thể mang câu lệnh giấu |
| 26/11/2026 | Lỗi bot = vàng; Gate fail-closed | An toàn trước tiện lợi |
| 26/11/2026 | **sim-world** là service riêng giả lập mọi hệ thống bên ngoài, kể cả hạ tầng thanh toán | Gate gọi rail qua HTTP như gọi MoMo thật; đổi sang hệ thật chỉ đổi adapter; test E2E và demo điều khiển qua `/scenario` |
| 26/11/2026 | **Đối soát** định kỳ ledger của Gate với sổ của rail | Hai sổ có thể lệch (mất callback, trừ sai); lệch → cảnh báo console |
| 26/11/2026 | **Đầu vào là hóa đơn điện tử** (XML qua email/tải lên/MoMo bill pay; ảnh-PDF luôn vàng); module `ingest` bằng code parse, kiểm tổng, chống trùng, lưu file gốc bất biến | Bám BR-01, BR-14; tách việc parse (code, xác định) khỏi việc hiểu (agent) |
| 26/11/2026 | 🔴 = khóa tới khi gỡ nguyên nhân; cảnh báo chéo = 🟡 bắt buộc xác minh; escrow cho NCC mới vào TK `escrow_only`, gắn PO; cảnh báo chéo đánh giá lại hóa đơn chưa chi; trần 30/50tr là policy nền tảng (D5–D9) | Rà soát drift BRD: kịch bản si-rô và Bẫy cuối phải chạy được; QT-01, QT-07 |
| 26/11/2026 | Kill switch: bật 1 người, gỡ 2 người | BR-12 "ngắt khẩn cấp" |
| 26/11/2026 | Ngân sách bot 20 giây, job ≈ 30 giây, tiến trình qua SSE | NFR tốc độ |
| 26/11/2026 | Cắt phạm vi v1: memory, marketplace, shadow, tạo bot qua chat, gom cụm/đồ thị/SIMO report, đối soát rail để lộ trình | Hạn 03/12, đội 3 người; dành công cho frontend |
| 26/11/2026 | ~~Workflow song song cố định ở ngoài~~ → **Agent điều phối ReAct theo loại việc** (`investigate_invoice`, `question`, `report`); bot chuyên môn là tool (agents-as-tools); an toàn bằng rào chắn code: bot bắt buộc là điều kiện hoàn tất, màu do code, điều phối không đọc chữ untrusted, không tool hành động, số phải có trích dẫn. LangGraph, trace OpenTelemetry | Không tối ưu cho một use case: người dùng còn hỏi đáp, thống kê; thêm việc mới = thêm cấu hình, không thêm graph ([agent-runtime.md](../03-agents/agent-runtime.md)) |
| 26/11/2026 | **v1 có hỏi đáp cơ bản** (hội thoại chỉ-đọc, tool thống kê viết sẵn, đề xuất hành động thành nút) | Yêu cầu của đội; giữ tính linh hoạt của sản phẩm |
| 26/11/2026 | **sim-world chỉ là giả lập gọn**: Gate và kiểm tra hệ thống chỉ đọc DB, không gọi SIMO/CSKH/tra MST | Không cần thật tới mức gọi hệ thống ngoài; bớt độ trễ và chỗ hỏng |
| 26/11/2026 | **Làm data trước, skill sau**: bộ dữ liệu sim-world + bộ ca thử có nhãn là đặc tả của agent | Skill chỉ viết đúng khi biết tool trả gì và đáp án đúng là gì |
| 26/11/2026 | **Model/provider LLM cho agent: chưa chốt**, thảo luận sau. Code chỉ gọi port `LLM`; model chọn qua `ModelConfig`/env; test dùng Replay | Chưa đủ dữ liệu eval để chọn; giữ đổi model = đổi cấu hình |
| 26/11/2026 | Contract-first: OpenAPI + JSON Schema trong `contracts/` | Đội dùng AI agent để code; contract là thứ giữ các service độc lập và sinh test tự động |
| 26/11/2026 | **Một tiến trình = một cổng = một tiền tố** (thay cho "v1 chạy chung một `core-api`"); Gate không gọi API core, báo kết quả qua `ledger.outbox`; core tự gộp màu khi job hoàn tất (runtime chỉ gửi Finding và tờ trình) | Tránh nhập nhằng cổng; console không lộ ra public; agent-runtime bị chiếm cũng không quyết được màu ([05-api](../05-api/README.md)) |
| 26/11/2026 | Chốt persona **chuỗi F&B 15 quán + 1 bếp trung tâm** (~45 NCC, ~550 HĐ/tháng — giả định của nhóm; ≤ 100 lao động có BHXH, thuộc DN vừa theo NĐ 80/2021), thay thế số liệu BRD §5.1; **giữ nguyên trần tự chi D9** (30 triệu/HĐ, 50 triệu/ngày) | Quy mô 5 quán quá nhỏ để chứng minh cần đội agent; 16 điểm tạo đủ tình huống giao thẳng vs bếp trung tâm, điện nước nhiều điểm và duyệt hàng loạt cho phần chi 50–80 triệu/ngày vượt trần ngày, vẫn nằm trong ngưỡng DNNVV ([persona.md](../04-data/persona.md)) |
| 26/11/2026 | Cập nhật chuẩn XML HĐĐT sang **QĐ 1233/QĐ-CT (27/08/2026)** (NĐ 254/2026, TT 91/2026); bộ `ingest` nhận `PBan` ∈ `{2.0.0, 2.0.1, 2.1.0, 2.1.1}`, parse theo `local-name()` và trích STK người bán từ `NBan/STKNHang`, `TTKhac`, `DLQRCode` (tất cả `untrusted`) | QĐ 1271 đã hết hiệu lực; ngày demo 03/12/2026 nằm trong giai đoạn chuyển tiếp `2.1.0`/`2.1.1` (đến 31/12/2026) và `DSig`/`XAdES` (đến 09/04/2027); 10 mẫu thật cho thấy STK và thứ tự thẻ lệch giữa các TCGP ([einvoice-xml.md](../04-data/einvoice-xml.md)) |
| 26/11/2026 | Đồng bộ enum tra cứu thuế của `sim-world` và tool `tax` theo mã thật của Cục Thuế: 10 mã trạng thái MST (`TT 90/2026`: `00`–`10`, không có `08`) và mã cổng HĐĐT (`tthai` `1`–`6`, `ttxly` `0`–`8`, `bhphap`) | Tránh enum tự đặt (`valid/replaced/...`) lệch cổng thật; giữ thống nhất giữa `sim-world`, `internal-api`, tool `tax` và bộ dữ liệu demo ([sim-world-api.md](../05-api/sim-world-api.md)) |
| 26/11/2026 | **Idempotency theo `(tenant_id, sha256)` chạy trước bước chống trùng** trong `ingest` (cùng file → no-op trả hóa đơn đã có; chỉ file khác `sha256` trùng `(MST, ký hiệu, int(số))` mới là `DUPLICATE_INVOICE`) và **chính sách trùng hỗn hợp** (`upload` trả `409` không lưu; `email`/`bill_pay` lưu kèm `duplicate_of` + Finding đỏ) | Polling hộp thư kiểu at-least-once không được biến thành tín hiệu gian lận `DUPLICATE_INVOICE` hay kích hoạt tự hạ quyền `auto_pay_suspensions` (QT-03); đồng thời `upload` báo lỗi ngay còn `email`/`bill_pay` giữ dấu vết gian lận bên ngoài ([einvoice-xml.md §4](../04-data/einvoice-xml.md), [merchant-api.md §2](../05-api/merchant-api.md)) |
| 27/11/2026 | **Kỳ điện nước đang xét không nằm trong baseline của chính nó**: `utility_readings` seed là 12 tháng *trước* kỳ hóa đơn mới (`2025-11`..`2026-10`), kỳ `2026-11` chỉ có ở `bills.json` (một hóa đơn/tài khoản). **PO ghi giá hợp đồng** (chưa VAT), `total_vnd` gồm VAT. **TRAP_02** dùng công ty bình phong của Tenant B (MST khác, TK công ty `verified`, có PO/GRN) chỉ chung **SĐT** với người bán si-rô BRD_04 | Poller bỏ qua hóa đơn có kỳ đã tồn tại nên ca rò nước BRD_06 không bao giờ được ghi; PO chép giá hóa đơn che mất lệch giá/quy cách; TRAP_02 cũ cùng MST nằm trong `tax_risk_list` nên đã đỏ (`blocked`) trước cảnh báo, F3 không kéo về được |
| 27/11/2026 | **Siết chặt bất biến Escrow & Payment Gate**: giải ngân cọc bắt buộc `approved amount_vnd == escrow.amount_vnd` và `approved payee_account_id == escrow.vendor_account_id` kèm đánh giá lại `intent_hash` + toàn bộ policy (lệch → `422 GATE_DENIED` với `ESCROW_MISMATCH`); một `approval_id` cấp vốn tối đa một escrow vĩnh viễn (`UNIQUE approval_id → escrow_id`, gọi lại trả cọc gốc ở mọi trạng thái, sau hoàn/thất bại phải có approval mới); hết hạn ủy quyền `AUTHORIZATION_TIMEOUT` chỉ ủy quyền lại nếu approval còn `active` và chưa hết hạn, ngược lại CAS về `pending_approval`; idempotency rail cho thẻ/cọc dùng lại `POST` cùng key + cùng body và khóa giải ngân/hoàn theo thao tác (`rel_<escrow_id>`, `ref_<escrow_id>`) | Chặn giải ngân sai số tiền/tài khoản trên rail không hỗ trợ giải ngân một phần, chặn tái sử dụng một approval cho nhiều lần giữ cọc, đồng bộ hành vi timeout giữa `gate-api.md` và `events.md`, và đảm bảo tra cứu trạng thái rail an toàn khi timeout ([payment-gate.md](payment-gate.md), [gate-api.md](../05-api/gate-api.md), [events.md](../05-api/events.md), [sim-world-api.md](../05-api/sim-world-api.md)) |
| 27/11/2026 | **Siết chặt ranh giới điều phối & token năng lực**: `BotAnswer.facts[].key` bắt buộc thuộc enum `FactKey` do registry sở hữu và giá trị chuỗi chỉ nhận từ trường `provenance = trusted`; `QuestionHistoryMessage` với `role = assistant` chỉ mang `{message_id, citations}` (không chữ tự do); `CapabilityTokenClaims` tách `oneOf` theo `sub` (`supervisor` bắt buộc `bot_version = null` và cấm `inbox`/`chat_messages`/`invoices`, bot bắt buộc `bot_version >= 1`, `exp - iat <= 120 s`); `gate.yaml` khai báo ma trận quyền gọi `x-allowed-callers` cho từng operation | Ngăn buôn lậu prompt/chữ `untrusted` qua key/value của `BotAnswer` hay lịch sử hội thoại sang `chief-accountant`, và biểu diễn bất biến ranh giới quyền bằng schema máy đọc được ([internal-api.md](../05-api/internal-api.md), [gate-api.md](../05-api/gate-api.md), [schemas.md](../05-api/schemas.md)) |
| 27/11/2026 | **Chuẩn hóa số nguyên an toàn, mốc thời gian băm và phân biệt schema hợp đồng**: giới hạn mọi số tiền VND trong `[-9007199254740991, 9007199254740991]` (`MoneyVnd` từ `0`) và `paymatch-hashing` từ chối số nguyên ngoài ngưỡng; chuẩn hóa mọi `Timestamp` trong payload băm về UTC `YYYY-MM-DDTHH:MM:SSZ` (bỏ phần thập phân giây, gồm `verification.at`); dùng chung `IndicatorRef` (`value_hash` đúng 64 ký tự hex) ở mọi sự kiện rủi ro; tách `oneOf` theo `type` cho webhook rail, ràng buộc `if/then` cho `EvaluateResponse` (`ALLOW` bắt buộc `payee_account_id != null`), `IntentGateDeniedProblem` (kèm `payment_intent` `denied`) và `job.progressed` (`text_delta` chỉ khi `type = answer.delta`) | Đảm bảo Python và TypeScript sinh cùng một hash RFC 8785 không lệch độ chính xác hay định dạng múi giờ, và kiểm chứng được các điều kiện ràng buộc bằng JSON Schema + test âm ([schemas.md](../05-api/schemas.md), [events.md](../05-api/events.md)) |
| 27/11/2026 | Finding lỗi fail-closed (`BOT_TIMEOUT`/`BOT_INVALID_OUTPUT`, `evidence` rỗng) được miễn kiểm `prefetch` khi nộp, core áp sàn vàng | Bot hết giờ trước khi kịp prefetch vẫn để lại Finding vàng thay vì làm cả job `:fail` ([internal-api.md](../05-api/internal-api.md)) |
| 27/11/2026 | **Không chi số tiền ≤ 0**: Gate có luật cứng `NON_POSITIVE_AMOUNT` (DENY cho intent hóa đơn, tạo cọc, giải ngân); core đặt trạng thái mới `no_payment_due` cho hóa đơn tổng ≤ 0 ở 🟢/🟡 (🔴 vẫn `blocked`). v1 không tự trừ số điều chỉnh vào hóa đơn khác | Hóa đơn điều chỉnh giảm (`EDGE_XML_ADJUST_NEG`, −1.620.000 đ) không phải khoản phải trả; không có luật thì nó vào hàng chờ chi với số âm, có thể làm sai hạn mức ngày hoặc chuyển ngược chiều. Tự trừ cần sổ "NCC nợ lại" và biên bản bù trừ, để lộ trình |
| 27/11/2026 | **Client không tự tính hash**: `action_hash` luôn lấy từ endpoint xem trước của core; thêm `POST /m/invoices/{id}/approval-preview {verification}` cho duyệt có gọi lại xác minh | Chỉ một bản cài đặt JCS/SHA-256 (`paymatch-hashing`), tránh hai bản Python/TypeScript lệch nhau; màn TRAP_02 không phụ thuộc thư viện băm phía trình duyệt |
| 27/11/2026 | `fraud-control` được cấp thêm tool `invoices` và `official_fraud_list` | Bảng mã lý do đã giao cho bot này `HIDDEN_INSTRUCTION` (câu lệnh giấu trong chữ hóa đơn) và `OFFICIAL_FRAUD_LIST` (SIMO); thiếu hai tool thì bot không có dữ liệu để sinh mã |
| 27/11/2026 | **Runtime không bao giờ hạ mã đỏ do bot đánh giá nội dung** vì trích dẫn sai; chỉ bỏ mã đỏ do tool trusted quyết định khi output âm | Trích dẫn lệch một ký tự từng làm `HIDDEN_INSTRUCTION` rơi xuống vàng (duyệt được). Báo nhầm chỉ khóa một hóa đơn, gỡ theo 6b |
| 27/11/2026 | **Khóa API LLM theo từng bot** qua env `LLM_API_KEY_<BOT_ID>`, mặc định `LLM_API_KEY` (chỗ chờ, provider chưa chốt) | Tách hạn mức/chi phí và thu hồi riêng từng bot; khóa chỉ ở env của `agent-worker` |
