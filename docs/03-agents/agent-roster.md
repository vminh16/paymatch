# Đội agent (6 vai)

Trạng thái: **Đã chốt (v0.4, 26/11/2026)**: điều phối là agent ReAct, bot chuyên môn là tool của nó. Danh sách tool khớp [tools.md](tools.md); bot bắt buộc theo loại hóa đơn ở [agent-lifecycle-and-memory.md](agent-lifecycle-and-memory.md). Nguồn: đối chiếu 5 nỗi đau trong BRD với công việc thật của phòng kế toán (xem [domain-notes](../research/domain-notes.md)).

| # | Bot ID | Agent | Vai ngoài đời | Nỗi đau | Checklist nghề (skill) | Tool (chỉ-đọc) | Không được làm |
|---|---|---|---|---|---|---|---|
| 0 | `chief-accountant` | **Kế toán trưởng** (agent điều phối ReAct) | Kế toán trưởng | 5 | Nhận việc (điều tra hóa đơn, hỏi đáp, báo cáo), tự chọn gọi bot chuyên môn và tool thống kê; viết tờ trình 5 dòng hoặc câu trả lời có trích dẫn. Màu do **code** gộp, bot bắt buộc do code ép (agent-runtime.md §4) | `ask_<bot>`, tool thống kê/tra cứu trusted | Đọc nguyên văn nội dung người bán; chi tiền; hành động có tác dụng phụ; tự chấm màu |
| 1 | `procurement` | **Thu mua** | Chuyên viên thu mua | 1 | Đơn giá theo hợp đồng khung; quy cách đóng gói (shrinkflation); so lịch sử giá | `invoices`, `vendor_contracts`, `price_check`, `price_history` | Sửa hợp đồng |
| 2 | `accounts-payable` | **Công nợ phải trả** | Kế toán công nợ | 1, 5 | Đối chiếu 3 chứng từ (đơn đặt hàng ↔ phiếu nhập ↔ hóa đơn); số lượng vượt định mức; trùng thanh toán; công nợ còn lại; hạn trả | `invoices`, `purchase_orders`, `goods_receipts`, `three_way_match`, `payables_ledger` | Trả tiền |
| 3 | `fraud-control` | **Chống gian lận & dữ liệu NCC** | Kiểm soát vendor master | 2 | Yêu cầu đổi tài khoản; gọi lại số đã lưu (không dùng số trong tin nhắn); TK cá nhân vs công ty; chiêu hối thúc/giả danh; câu lệnh giấu; cảnh báo chéo | `inbox`, `chat_messages`, `vendor_registry`, `cross_alerts` | Sửa danh bạ NCC (chỉ mở yêu cầu xác minh cho người) |
| 4 | `tax` | **Thuế** | Kế toán thuế | 3 | HĐ tồn tại trên cổng HĐĐT; trạng thái MST (03, 06); DS doanh nghiệp rủi ro; HĐ ≥ 5 triệu phải chuyển khoản vào TK người bán mới được khấu trừ VAT (NĐ 181/2025) | `invoices`, `vendor_registry`, `einvoice_portal`, `tax_id_lookup`, `tax_risk_list` | Kết luận gian lận (việc của #3) |
| 5 | `branch-operations` | **Vận hành chi nhánh** | Quản lý vận hành | 4 | Điện nước so 12 tháng **và** so doanh thu/số ly của quán trong tháng | `utility_bills`, `utility_baseline`, `momo_revenue` | — |
| 6 | `treasury` | **Thủ quỹ** | Thủ quỹ / treasury | 5 | Số dư; hạn trả; hạn mức ngày; đề xuất kênh trả (lệnh chi / thẻ ảo / cọc tạm giữ); xếp lịch trả theo hạn (không gom giao dịch) | `account_balance`, `spending_limits`, `payables_ledger`, `purchase_orders`, `goods_receipts`, `payment_policy_preview` | **Phát lệnh trả** — chỉ đề xuất; Gate quyết |

Người thật: chủ chuỗi (duyệt, ký mandate, gỡ khóa 🔴), kế toán (xem, chuẩn bị, gọi lại xác minh NCC; không duyệt), quản lý quán (xác nhận nhận hàng → `goods_receipts`), nhân viên rủi ro MoMo (cảnh báo chéo, kill switch).

## Thanh toán: không phải agent

Việc "đi thanh toán" chia làm hai nửa:
- **Đề xuất** (kênh nào, lúc nào) → Thủ quỹ (agent). Một hóa đơn = một giao dịch.
- **Thực thi** (kiểm điều kiện, phát token, ghi sổ) → **Payment Gate (code)**.

Kế toán trưởng không chi tiền. Lý do ở [architecture.md mục 9](../02-architecture/architecture.md#9-quyết-định-đã-chốt-và-lý-do).

## Kịch bản BRD mục 14 → agent bắt lỗi

| Hóa đơn | Agent báo | Mức |
|---|---|---|
| Cà phê hạt 26,5tr | tất cả xanh | 🟢 |
| Sữa 31tr, Zalo gửi TK mới | Chống gian lận (`PAYEE_CHANGE_REQUEST`); Thủ quỹ (`OVER_LIMIT`) | 🔴 → gỡ bằng F12 (gọi lại số trong hợp đồng) |
| Cốc nhựa 800 cái/thùng | Thu mua (+21,7%/cái) | 🟡 |
| Si-rô NCC mới | Chống gian lận (TK cá nhân, câu lệnh giấu); Thuế (DN rủi ro; mất khấu trừ VAT nếu trả TK cá nhân) | 🔴 → chỉ escrow vào TK công ty `escrow_only` (F7) hoặc Từ chối |
| Phần mềm 12tr | Thu mua (đúng hợp đồng), các bot khác xanh; Thủ quỹ đề xuất thẻ ảo | 🟢 |
| Nước quán 3, 4,2tr | Vận hành (≈6× trung vị, doanh thu không tăng) | 🟡 |
| Bẫy cuối: thẻ ảo bị dùng ở nơi khác | sim-world từ chối (F8) | indicator → console |
| Bẫy cuối: MoMo gắn cảnh báo chéo người bán si-rô | hóa đơn chưa chi của cửa hàng khác bị đánh giá lại, cửa hàng được thông báo (F3) | 🟡 bắt buộc xác minh |
