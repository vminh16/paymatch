# Thiết kế tool

Trạng thái: **Đã chốt mức thiết kế (26/11/2026)**.

## 1. Nằm ở đâu

Tool nằm trong **core, module `tools/`**. Code là nguồn sự thật; registry được sinh từ code và đồng bộ vào `control.tools` để cấp quyền và hiển thị.

```python
@tool(id="price_check", provenance="trusted", scope="tenant")
def price_check(inp: PriceCheckIn, ctx: ToolContext) -> PriceCheckOut:
    # code tính đơn giá/đơn vị và so hợp đồng; LLM không tự tính
    ...
```

Mỗi tool gồm: `id`, mô tả cho LLM, schema input/output (contract), `provenance` mặc định của dữ liệu trả về, `scope` (luôn giới hạn trong tenant của job), handler gọi port (`Repo` hoặc adapter sim-world).

## 2. Đường gọi

```
agent-runtime ── GET /internal/tools (Bearer capability token) → định nghĩa các tool có trong token
              ── POST /internal/tools/{id}:invoke (Bearer capability token)
core: kiểm token (tenant, job, bot, tool, hạn) → chạy handler (chỉ-đọc) → lưu tool_calls → trả kết quả
```

Mọi tool trả cùng một dạng:

```yaml
ToolResult:
  data: object                 # theo schema output của tool
  provenance: trusted | untrusted
  evidence_ref: string         # id bản ghi tool_calls, dùng trong Finding.evidence
  error: {code, detail} | null # nguồn dữ liệu lỗi; bot ghi vàng
```

Đặc tả đầy đủ endpoint, danh mục tool kèm nguồn, mức sàn từ output tool: [05-api/internal-api.md](../05-api/internal-api.md).

## 3. Nguyên tắc thiết kế

- **Theo nghiệp vụ, không theo bảng DB.** Có `three_way_match`, `price_check`; không có `query_table`.
- **Tính toán do tool làm.** Đơn giá/đơn vị, chênh lệch %, khoảng bình thường điện nước, tổng tiền: tool trả con số đã tính. Bot chỉ diễn giải.
- **Chỉ-đọc, không ngoại lệ.** Không tool nào ghi DB, gửi tin, hay gọi Gate.
- **Tách số và chữ.** Trường số (do code parse) và trường chữ do người bán viết được trả ở hai phần riêng; phần chữ luôn `untrusted`.
- **Không SQL tự do.** Tool thống kê nhận tham số (khoảng ngày, quán, NCC, nhóm theo); code chạy truy vấn đã viết sẵn.
- **Điều phối không có tool trả chữ untrusted.** `inbox`, `chat_messages`, phần chữ của `invoices` chỉ cấp cho bot chuyên môn.
- **Kết quả gọn.** Trả đúng thứ bot cần cho checklist, kèm `evidence_ref`, không trả nguyên bảng.

## 4. Danh mục tool v1

| Tool | Dùng bởi | Trả về | Provenance |
|---|---|---|---|
| `invoices` | procurement, accounts-payable, tax | hóa đơn chuẩn hóa: phần số + phần chữ | số: trusted, chữ: untrusted |
| `vendor_contracts` | procurement | mặt hàng, quy cách, đơn giá hợp đồng | trusted |
| `price_check` | procurement | đơn giá/đơn vị trên hóa đơn vs hợp đồng, chênh lệch % (bot chỉ ánh xạ dòng hàng → sku; quy cách lấy từ hợp đồng và do code parse từ hóa đơn) | trusted |
| `official_fraud_list` | fraud-control | TK/SĐT/MST của hóa đơn có trong danh sách chính thức (SIMO) | trusted |
| `price_history` | procurement | giá các lần mua trước | trusted |
| `purchase_orders`, `goods_receipts`, `payables_ledger` | accounts-payable, treasury | chứng từ liên quan | trusted |
| `three_way_match` | accounts-payable | kết quả đối chiếu PO ↔ phiếu nhập ↔ hóa đơn | trusted |
| `inbox`, `chat_messages` | fraud-control | thư/tin nhắn liên quan hóa đơn hoặc NCC | **untrusted** |
| `vendor_registry` | fraud-control, tax | NCC, TK đã xác minh, SĐT lưu sẵn | trusted |
| `cross_alerts` | fraud-control | indicator khớp cảnh báo chéo | trusted |
| `einvoice_portal`, `tax_id_lookup`, `tax_risk_list` | tax | kết quả tra cổng HĐĐT (`tthai` 1–6, `ttxly` 0–8, `bhphap`), 10 mã trạng thái MST (`TT 90/2026`: `00`–`10` trừ `08`), có trong DS doanh nghiệp rủi ro | trusted |
| `utility_bills`, `utility_baseline` | branch-operations | hóa đơn điện nước; khoảng bình thường 12 tháng | trusted |
| `momo_revenue` | branch-operations | doanh thu/số giao dịch theo quán, theo tháng | trusted |
| `account_balance`, `spending_limits`, `payment_policy_preview` | treasury | số dư; hạn mức; **chạy thử Gate không tác dụng phụ** | trusted |
| `invoice_search`, `invoice_explain`, `spending_summary`, `vendor_stats`, `price_trend`, `queue_status`, `utility_summary`, `payment_history` | chief-accountant (hỏi đáp, báo cáo), bot chuyên môn | thống kê, tra cứu bằng truy vấn viết sẵn có tham số; số do code tính | trusted |
| `ask_<bot_id>` | chief-accountant | gọi một bot chuyên môn (sinh tự động từ manifest bot active); trả kết quả có cấu trúc, không có chữ tự do | trusted (đã lọc) |
| `bot_memory` *(lộ trình)* | mọi bot | memory của bot đó trong tenant | theo bản ghi |

`price_check` nhận ánh xạ do bot đề xuất (dòng hàng → sku); quy cách và mọi con số do code lấy/tính. Ánh xạ là việc AI, con số là việc code.

## 4a. Quy ước tra cứu thuế (`tax_id_lookup`, `einvoice_portal`, `tax_risk_list`)

Các tool thuế trả đúng tập mã chính thức của Cục Thuế (khớp [sim-world-api.md §5](../05-api/sim-world-api.md#5-tra-cứu-chính-thức) và [internal-api.md §2–§3](../05-api/internal-api.md)). Ánh xạ sang `ReasonCode` **chỉ dùng các mã hiện có tại [agent-runtime.md §5a](agent-runtime.md#5a-danh-mục-mã-lý-do-nguồn-sự-thật)**; không tự thêm mã mới vào v1.

### 1. `tax_id_lookup` — 10 mã trạng thái MST (`TT 90/2026/TT-BTC`, Phụ lục I)

Xác minh từ tệp gốc `1.1.PL1-Trạng thái MST.doc` trong [90-btc.rar (vanban.chinhphu.vn)](https://vanban.chinhphu.vn/?pageid=27160&docid=218839): hệ thống có đúng **10 mã** (`"00"`, `"01"`, `"02"`, `"03"`, `"04"`, `"05"`, `"06"`, `"07"`, `"09"`, `"10"`); **không tồn tại mã trạng thái `"08"`** (`"08"` là `status_reason_code` *"Đã phá sản"* nằm dưới trạng thái `"01"`). Riêng mã `"04"` được ghi trực tiếp là **`"Hết hiệu lực"`** trong Phụ lục I `TT 90/2026/TT-BTC` (không còn mã lý do con).

| `status_code` | Tên trạng thái chính thức | Ánh xạ `ReasonCode` v1 | Ghi chú xử lý |
|---|---|---|---|
| `"00"` | NNT đã được cấp MST / Đang hoạt động | `OK` | Kiểm tra thêm `status_reason_code` (`02` đang hoạt động bình thường) |
| `"01"` | Ngừng hoạt động và đã hoàn thành thủ tục chấm dứt hiệu lực MST | `MST_INACTIVE` (🔴) | Chặn nếu ngày lập HĐ `NLap` sau ngày chấm dứt hiệu lực MST (gồm giải thể `07`, phá sản `08`) |
| `"02"` | Đã chuyển cơ quan thuế quản lý (chờ nơi đến nhận) | `OK` *(hoặc `VAT_DEDUCTION_RISK` 🟡 nếu địa chỉ trên HĐ lệch)* | Ghi chú trong `reason` để kế toán đối chiếu địa chỉ mới |
| `"03"` | Ngừng hoạt động nhưng chưa hoàn thành thủ tục chấm dứt hiệu lực MST | `MST_INACTIVE` (🔴) | Rủi ro hóa đơn đầu vào rất cao |
| `"04"` | **Hết hiệu lực** *(trước đây: HKD/cá nhân KD chưa đủ thông tin ĐKT)* | `VAT_DEDUCTION_RISK` (🟡) | Không dùng cho hồ sơ mới dưới `TT 90/2026`; nếu gặp ở dữ liệu cũ cần xác minh lại tư cách NCC |
| `"05"` | Tạm ngừng hoạt động, kinh doanh | `MST_INACTIVE` (🔴) | Không được xuất HĐ trong kỳ tạm ngừng |
| `"06"` | Không hoạt động tại địa chỉ đã đăng ký ("bỏ địa chỉ") | `MST_INACTIVE` (🔴) | Tín hiệu gian lận/hóa đơn không hợp pháp hàng đầu |
| `"07"` | Chờ làm thủ tục phá sản | `MST_INACTIVE` (🔴) | Chặn chi / rà soát công nợ |
| `"09"` | Chờ xác minh tình trạng hoạt động tại địa chỉ đã đăng ký | `VAT_DEDUCTION_RISK` (🟡) | Cảnh báo sớm nguy cơ chuyển sang `"06"`, cần xác minh NCC |
| `"10"` | MST chờ cập nhật thông tin số định danh cá nhân | `VAT_DEDUCTION_RISK` (🟡) | Áp cho cá nhân/HKD chưa đồng bộ CCCD |

### 2. `einvoice_portal` — Mã cổng HĐĐT (`hoadondientu.gdt.gov.vn`)

Trả `found`, `invoice_status_code` (`tthai` `1`–`6`), `processing_status_code` (`ttxly` `0`–`8`), `illegal_flag` (`bhphap == 1`), `tax_authority_code`, `total_vnd`, `related_invoice`:

| Điều kiện output của `einvoice_portal` | Ánh xạ `ReasonCode` v1 | Ý nghĩa |
|---|---|---|
| `found == true`, `invoice_status_code ∈ {1, 2, 3}`, `processing_status_code ∈ {5, 6, 7, 8}`, `illegal_flag == false` | `OK` | Hóa đơn mới / thay thế / điều chỉnh hợp lệ (đã cấp mã `5`, nhận không mã `6`/`7`, hoặc MTT `8`) |
| `found == false` hoặc `processing_status_code ∈ {2, 4}` | `INVOICE_NOT_FOUND_ON_PORTAL` (🔴) | Không tìm thấy trên cổng, CQT từ chối từng lần (`2`), hoặc không đủ điều kiện cấp mã (`4`) |
| `invoice_status_code ∈ {4, 6}` | `INVOICE_NOT_FOUND_ON_PORTAL` (🔴) | Hóa đơn đã bị thay thế (`4`) hoặc đã bị hủy (`6`) — không còn hiệu lực thanh toán |
| `illegal_flag == true` (`bhphap == 1`) | `TAX_RISK_LIST` (🔴) | Hóa đơn bị CQT gắn cờ `"Bất hợp pháp"` |
| `invoice_status_code == 5` hoặc `processing_status_code ∈ {0, 1, 3}` | `VAT_DEDUCTION_RISK` (🟡) | Đã bị điều chỉnh (`5`, cần kẹp HĐ điều chỉnh `related_invoice`), hoặc CQT mới tiếp nhận/đang kiểm tra cấp mã (`0`, `1`, `3`, chưa hoàn tất) |

### 3. `tax_risk_list`

- `listed == true` → `TAX_RISK_LIST` (🔴, theo bảng mức sàn `agent-runtime.md §5a`).

### Đề xuất chưa áp dụng (không thêm vào `ReasonCode` v1)

Các mã sau có thể giúp phân tách sắc nét hơn nhưng **chưa thêm** vào `agent-runtime.md §5a` để giữ ổn định contract v1 (hiện đang ánh xạ tạm về mã hiện có ở hai bảng trên):
- `MST_VERIFICATION_PENDING` (🟡): tách riêng trạng thái MST `"09"` (chờ xác minh địa chỉ), `"04"`, `"10"`, `"02"` khỏi `VAT_DEDUCTION_RISK`.
- `INVOICE_CANCELLED_OR_REPLACED` (🔴): tách riêng `tthai ∈ {4, 6}` khỏi `INVOICE_NOT_FOUND_ON_PORTAL`.
- `ILLEGAL_INVOICE` (🔴): tách riêng cờ hóa đơn bất hợp pháp `bhphap == 1` khỏi `TAX_RISK_LIST` (cấp doanh nghiệp).
- `INVOICE_PENDING_TAX_CODE` (🟡): tách riêng hóa đơn đang chờ CQT cấp mã (`ttxly ∈ {0, 1, 3}` hoặc hóa đơn `C` có `MCCQT` rỗng) khỏi `VAT_DEDUCTION_RISK`.

## 5. Thêm tool mới

Chỉ đội dev thêm (v1 không cho người dùng cắm tool). Thêm tool = viết handler + schema + test, deploy core; registry tự đồng bộ; bật cho tenant qua `tool_grants`.
