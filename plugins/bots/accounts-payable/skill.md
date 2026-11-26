---
skill_id: accounts_payable_checklist
version: 1
prefetch:
  - invoices
  - three_way_match
  - payables_ledger
---
# Kiểm tra công nợ phải trả (đối chiếu 3 chiều & chống trùng)

## Khi nào dùng
Dùng cho mọi hóa đơn hàng hóa (`goods`) để đối chiếu 3 chứng từ (đơn đặt hàng PO ↔ phiếu nhập kho GRN ↔ hóa đơn), phát hiện giao thiếu hàng, thiếu phiếu nhập kho hoặc hóa đơn trùng trong sổ công nợ.

## Dữ liệu cần (tool)
- `invoices` (prefetch): thông tin hóa đơn hiện tại (`symbol`, `number`, `seller_tax_id`, `total_vnd`, `lines`, `duplicate_of`).
- `three_way_match` (prefetch): kết quả code đối chiếu `matched`, `missing_goods_receipt`, `quantity_above_norm`, `purchase_order_id`, `goods_receipt_ids`, và chi tiết từng dòng `lines`.
- `payables_ledger` (prefetch): sổ công nợ hiện tại của NCC để kiểm tra trùng số hóa đơn/ký hiệu hoặc đã thanh toán trước đó.
- `purchase_orders`: tra chi tiết PO khi cần kiểm tra thêm trạng thái đơn đặt hàng hoặc dòng đặt.
- `goods_receipts`: tra chi tiết phiếu nhập kho khi cần đối chiếu số lượng thực nhận tại quán hoặc bếp trung tâm.

## Các bước
1. Kiểm tra kết quả `three_way_match`: xem cờ `matched`, `missing_goods_receipt`, `quantity_above_norm`, `purchase_order_id`, `goods_receipt_ids`.
2. Nếu thiếu chi tiết về PO hoặc phiếu nhập kho, gọi thêm `purchase_orders` và `goods_receipts` với `purchase_order_id` hoặc `vendor_id`.
3. Rà soát `payables_ledger` và trường `duplicate_of` trên `invoices` để phát hiện hóa đơn trùng `(seller_tax_id, symbol, int(number))` hoặc khoản đã chi.
4. Trích dẫn bằng chứng (`purchase_order`, `goods_receipt`, `invoice_line`, hoặc `tool_call`) kèm đúng `tool_call_id`.

## Cách kiểm chứng
- Nếu `duplicate_of` khác `null` hoặc sổ công nợ `payables_ledger` có bản ghi trùng hóa đơn khác `invoice_id` đã tồn tại/đã thanh toán → gắn `DUPLICATE_INVOICE` (`red`).
- Nếu `three_way_match.missing_goods_receipt == true` → gắn `NO_GOODS_RECEIPT` (`yellow`).
- Nếu `three_way_match.quantity_above_norm == true` (số lượng hóa đơn vượt số lượng thực nhận trên GRN hoặc PO) → gắn `QUANTITY_ABOVE_NORM` (`yellow`).
- Nếu `three_way_match.matched == true`, không trùng công nợ, và không có lỗi tool → trả `severity_reported = "green"`, `reason_codes = ["OK"]`.

## Trả về (reason_codes dùng được)
- `OK` (`green`): khớp 3 chứng từ (PO, GRN, hóa đơn) và không trùng thanh toán.
- `QUANTITY_ABOVE_NORM` (`yellow`): số lượng trên hóa đơn vượt số lượng thực nhận hoặc định mức PO.
- `NO_GOODS_RECEIPT` (`yellow`): chưa có phiếu nhập kho xác nhận nhận hàng cho hóa đơn.
- `DUPLICATE_INVOICE` (`red`): hóa đơn trùng với hóa đơn đã ghi nhận hoặc đã thanh toán trong sổ công nợ.

## Khi nào báo đỏ
Báo đỏ (`severity_reported = "red"`) ngay khi phát hiện `DUPLICATE_INVOICE`. Không bao giờ bỏ qua cờ `missing_goods_receipt` hay `quantity_above_norm` do `three_way_match` trả về.
