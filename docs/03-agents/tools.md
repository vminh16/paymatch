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
| `einvoice_portal`, `tax_id_lookup`, `tax_risk_list` | tax | hóa đơn có tồn tại, trạng thái MST, có trong DS rủi ro | trusted |
| `utility_bills`, `utility_baseline` | branch-operations | hóa đơn điện nước; khoảng bình thường 12 tháng | trusted |
| `momo_revenue` | branch-operations | doanh thu/số giao dịch theo quán, theo tháng | trusted |
| `account_balance`, `spending_limits`, `payment_policy_preview` | treasury | số dư; hạn mức; **chạy thử Gate không tác dụng phụ** | trusted |
| `invoice_search`, `invoice_explain`, `spending_summary`, `vendor_stats`, `price_trend`, `queue_status`, `utility_summary`, `payment_history` | chief-accountant (hỏi đáp, báo cáo), bot chuyên môn | thống kê, tra cứu bằng truy vấn viết sẵn có tham số; số do code tính | trusted |
| `ask_<bot_id>` | chief-accountant | gọi một bot chuyên môn (sinh tự động từ manifest bot active); trả kết quả có cấu trúc, không có chữ tự do | trusted (đã lọc) |
| `bot_memory` *(lộ trình)* | mọi bot | memory của bot đó trong tenant | theo bản ghi |

`price_check` nhận ánh xạ do bot đề xuất (dòng hàng → sku); quy cách và mọi con số do code lấy/tính. Ánh xạ là việc AI, con số là việc code.

## 5. Thêm tool mới

Chỉ đội dev thêm (v1 không cho người dùng cắm tool). Thêm tool = viết handler + schema + test, deploy core; registry tự đồng bộ; bật cho tenant qua `tool_grants`.
