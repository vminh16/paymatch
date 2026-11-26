---
skill_id: branch_operations_checklist
version: 1
prefetch:
  - utility_bills
  - utility_baseline
---
# Kiểm tra vận hành chi nhánh (điện nước theo nền 12 tháng & doanh thu)

## Khi nào dùng
Dùng cho mọi hóa đơn điện, nước (`invoice_type = utility`) của các quán và bếp trung tâm để phát hiện rò rỉ nước, hỏng thiết bị điện hoặc sai chỉ số công tơ so với nền tiêu thụ 12 tháng và mức hoạt động kinh doanh thực tế của quán.

## Dữ liệu cần (tool)
- `utility_bills` (prefetch): danh sách kỳ hóa đơn điện/nước gần nhất (tối đa 12 tháng), gồm `reading_id`, `store_id`, `utility_type`, `billing_period`, `total_usage`, `usage_unit`, `total_vnd`.
- `utility_baseline` (prefetch): kết quả code tính toán nền 12 tháng: `median_usage`, `normal_min_usage`, `normal_max_usage`, `median_amount_vnd`, `current_usage`, `current_amount_vnd`, `ratio_to_median`, `out_of_range`, `reading_ids`.
- `momo_revenue`: tra doanh thu QR MoMo và số giao dịch (`revenue_vnd`, `transaction_count`) của `store_id` theo tháng (`month = YYYY-MM`) để đối chiếu xem tiêu thụ tăng có đi cùng tăng doanh thu/số ly hay không.

## Các bước
1. Xem kết quả `utility_baseline`: kiểm tra cờ `out_of_range`, `ratio_to_median`, `current_usage` vs `median_usage`, và `current_amount_vnd` vs `median_amount_vnd`.
2. Nếu `out_of_range == true` (hoặc tỷ lệ tăng đáng kể), gọi `momo_revenue` cho `store_id` và kỳ `billing_period` hiện tại (cũng như tháng trước nếu cần) để đối chiếu doanh thu và lượng khách.
3. Tổng hợp giải thích rõ ràng bằng số liệu do `utility_baseline` và `momo_revenue` trả về (ví dụ: sản lượng tăng gấp mấy lần trung vị, doanh thu quán có tăng tương ứng hay không).
4. Đính kèm `evidence` trỏ về `utility_reading` (`urd_...`) và `tool_call` (`tcl_...`) tương ứng.

## Cách kiểm chứng
- Nếu `utility_baseline.out_of_range == true` → bắt buộc gắn `UTILITY_OUT_OF_RANGE` (`yellow`), nêu rõ kết quả đối chiếu `momo_revenue`.
- Nếu `utility_baseline.out_of_range == false` và không có lỗi tool → trả `severity_reported = "green"`, `reason_codes = ["OK"]`.
- Không tự tính lại trung vị hoặc tự đặt ngưỡng ngoài `utility_baseline`.

## Trả về (reason_codes dùng được)
- `OK` (`green`): mức tiêu thụ điện/nước nằm trong khoảng bình thường 12 tháng của chi nhánh.
- `UTILITY_OUT_OF_RANGE` (`yellow`): mức tiêu thụ hoặc số tiền điện/nước vượt khoảng bình thường 12 tháng, cần quản lý chi nhánh kiểm tra rò rỉ hoặc công tơ.

## Khi nào báo đỏ
Bot `branch-operations` không phát hành mã đỏ; bất thường điện/nước ở mức `yellow` (`UTILITY_OUT_OF_RANGE`) để Chủ chuỗi và quản lý chi nhánh xác minh trước khi thanh toán.
