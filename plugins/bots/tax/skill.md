---
skill_id: tax_checklist
version: 1
prefetch:
  - invoices
  - vendor_registry
  - einvoice_portal
---
# Kiểm tra tuân thủ thuế và hóa đơn điện tử

## Khi nào dùng
Dùng cho hóa đơn hàng hóa (`goods`), phần mềm (`software`), và hóa đơn điện nước (`utility`) khi cần kiểm tra tính hợp pháp của hóa đơn điện tử trên cổng Tổng cục Thuế, tình trạng hoạt động của MST người bán, danh sách doanh nghiệp rủi ro cao về thuế và điều kiện khấu trừ thuế GTGT (VAT).

## Dữ liệu cần (tool)
- `invoices` (prefetch): `seller_tax_id`, `symbol`, `number`, `total_vnd`, `tax_authority_code`, `related_invoice`, `untrusted.seller_bank_account`, `document.document_id`.
- `vendor_registry` (prefetch): trạng thái NCC và tài khoản ngân hàng doanh nghiệp đã xác minh (`accounts`).
- `einvoice_portal` (prefetch): trạng thái cổng HĐĐT gồm `found`, `invoice_status_code` (`tthai` 1–6), `processing_status_code` (`ttxly` 0–8), `illegal_flag` (`bhphap`), `tax_authority_code`, `total_vnd`, `related_invoice`.
- `tax_id_lookup`: tra cứu trạng thái MST người bán (10 mã chính thức theo TT 90/2026: `"00"`, `"01"`, `"02"`, `"03"`, `"04"`, `"05"`, `"06"`, `"07"`, `"09"`, `"10"`; không có `"08"`).
- `tax_risk_list`: kiểm tra MST người bán có thuộc danh sách doanh nghiệp rủi ro cao về thuế hay không.

## Các bước
1. Lấy `seller_tax_id` từ kết quả `invoices`, gọi song song `tax_id_lookup(tax_id=seller_tax_id)` và `tax_risk_list(tax_id=seller_tax_id)`.
2. Đối chiếu kết quả `einvoice_portal`:
   - Hợp lệ (`OK`): `found == true`, `invoice_status_code ∈ {1, 2, 3}`, `processing_status_code ∈ {5, 6, 7, 8}`, `illegal_flag == false`.
   - `found == false` hoặc `processing_status_code ∈ {2, 4}` hoặc `invoice_status_code ∈ {4, 6}` (đã thay thế/hủy) → `INVOICE_NOT_FOUND_ON_PORTAL` (`red`).
   - `illegal_flag == true` (`bhphap == 1`) → `TAX_RISK_LIST` (`red`).
   - `invoice_status_code == 5` (đã bị điều chỉnh) hoặc `processing_status_code ∈ {0, 1, 3}` (đang chờ CQT tiếp nhận/kiểm tra cấp mã) → `VAT_DEDUCTION_RISK` (`yellow`).
3. Đối chiếu `tax_id_lookup.status_code`:
   - `"00"` → hoạt động bình thường (`OK`).
   - `"01"`, `"03"`, `"05"`, `"06"`, `"07"` → `MST_INACTIVE` (`red`).
   - `"04"`, `"09"`, `"10"` (hoặc `"02"` có lệch địa chỉ) → `VAT_DEDUCTION_RISK` (`yellow`).
4. Đối chiếu `tax_risk_list`: nếu `listed == true` → `TAX_RISK_LIST` (`red`).
5. Kiểm tra điều kiện khấu trừ VAT (NĐ 181/2025): hóa đơn có `total_vnd >= 5.000.000 đ` nhưng chưa có tài khoản doanh nghiệp `verified` trong `vendor_registry` hoặc bị yêu cầu trả vào tài khoản cá nhân / hóa đơn điều chỉnh âm cần kẹp chứng từ gốc → `VAT_DEDUCTION_RISK` (`yellow`).

## Cách kiểm chứng
- Không kết luận gian lận (việc của `fraud-control`); chỉ đánh giá tuân thủ thuế, MST, cổng HĐĐT và khấu trừ VAT.
- Mọi mã lý do đều phải trích dẫn `tool_call_id` của `einvoice_portal`, `tax_id_lookup`, `tax_risk_list` hoặc `invoices`.
- Nếu mọi kiểm tra thuế đều hợp lệ và không có rủi ro VAT → trả `severity_reported = "green"`, `reason_codes = ["OK"]`.

## Trả về (reason_codes dùng được)
- `OK` (`green`): hóa đơn hợp lệ trên cổng HĐĐT, MST hoạt động bình thường (`00`), không trong danh sách rủi ro, đủ điều kiện khấu trừ VAT.
- `VAT_DEDUCTION_RISK` (`yellow`): rủi ro không được khấu trừ VAT (HĐ ≥ 5 triệu thiếu chứng từ chuyển khoản vào TK công ty, MST mã `04`/`09`/`10`, HĐ chờ cấp mã `ttxly ∈ {0,1,3}`, hoặc HĐ bị điều chỉnh `tthai = 5`).
- `TAX_RISK_LIST` (`red`): MST nằm trong danh sách doanh nghiệp rủi ro thuế hoặc HĐ bị CQT gắn cờ bất hợp pháp (`illegal_flag = true`).
- `MST_INACTIVE` (`red`): MST ngừng hoạt động, tạm ngừng, bỏ địa chỉ hoặc chờ phá sản (`status_code ∈ {"01","03","05","06","07"}`).
- `INVOICE_NOT_FOUND_ON_PORTAL` (`red`): không tìm thấy HĐ trên cổng HĐĐT, bị từ chối cấp mã (`ttxly ∈ {2,4}`), hoặc HĐ đã bị thay thế/hủy (`tthai ∈ {4,6}`).

## Khi nào báo đỏ
Báo đỏ (`severity_reported = "red"`) ngay khi phát sinh `TAX_RISK_LIST`, `MST_INACTIVE`, hoặc `INVOICE_NOT_FOUND_ON_PORTAL`.
