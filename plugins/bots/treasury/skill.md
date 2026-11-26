---
skill_id: treasury_checklist
version: 1
prefetch:
  - account_balance
  - spending_limits
  - payment_policy_preview
---
# Kiểm tra ngân quỹ và đề xuất phương án thanh toán

## Khi nào dùng
Bắt buộc cho mọi loại hóa đơn (`goods`, `software`, `utility`) để kiểm tra số dư ví MoMo Doanh Nghiệp, hạn mức tự chi theo hóa đơn và theo ngày, chạy thử chính sách Payment Gate (`payment_policy_preview`), và đề xuất kênh thanh toán (`proposed_channel`) cùng ngày dự kiến chi (`proposed_pay_on`).

## Dữ liệu cần (tool)
- `account_balance` (prefetch): số dư khả dụng hiện tại của ví (`wallet_id`, `balance_vnd`, `as_of`).
- `spending_limits` (prefetch): `mandate` hiện hành, trần nền tảng `platform_limits` (`auto_pay_per_invoice_vnd`, `auto_pay_per_day_vnd`), và ngân sách đã dùng trong ngày `daily_budget`.
- `payment_policy_preview` (prefetch): chạy thử luật Payment Gate không tác dụng phụ (`decision`, `allowed_methods`, `amount_vnd`, `channel`, `reasons`).
- `payables_ledger`: xem hạn thanh toán (`due_on`) và các khoản đến hạn khác để đề xuất `proposed_pay_on` hợp lý (mỗi hóa đơn = một giao dịch, không gom lệnh).
- `purchase_orders`, `goods_receipts`: đối chiếu PO/GRN khi đề xuất kênh `escrow` cho NCC mới.

## Các bước
1. Kiểm tra `payment_policy_preview`: ghi nhận `amount_vnd`, `channel`, `decision`, và danh sách `reasons` (`GateReason`).
2. So sánh `amount_vnd` với `account_balance.balance_vnd`: nếu số dư nhỏ hơn số tiền hóa đơn → gắn `LOW_BALANCE`.
3. Kiểm tra trần hạn mức từ `spending_limits` và `payment_policy_preview.reasons`:
   - Nếu `reasons` chứa `ABOVE_PER_INVOICE_LIMIT` hoặc `ABOVE_DAILY_LIMIT`, hoặc `amount_vnd` vượt hạn mức hiệu lực `min(mandate.limits, platform_limits)` → gắn `OVER_LIMIT`.
4. Nếu cần ngày đến hạn hoặc kiểm tra PO/GRN cho cọc tạm giữ (`escrow`), gọi thêm `payables_ledger` (và `purchase_orders`/`goods_receipts` khi cần).
5. Đề xuất `proposed_channel` (lấy theo `payment_policy_preview.channel`, ví dụ `virtual_card` cho phần mềm POS, `escrow` nếu NCC mới dùng TK `escrow_only`, `bank_transfer` cho chuyển khoản thường) và `proposed_pay_on` (dạng `YYYY-MM-DD`, không gom nhiều hóa đơn thành một lệnh chi).

## Cách kiểm chứng
- Thủ quỹ **chỉ đề xuất**, tuyệt đối không phát lệnh chi tiền; Payment Gate thực thi sau khi có phê duyệt hoặc mandate hợp lệ.
- Mọi con số tiền và quyết định hạn mức phải lấy đúng từ `account_balance`, `spending_limits`, `payment_policy_preview`.
- Nếu đủ số dư và nằm trong hạn mức (không có `LOW_BALANCE`, `OVER_LIMIT`) → trả `severity_reported = "green"`, `reason_codes = ["OK"]` kèm `proposed_channel` và `proposed_pay_on`.

## Trả về (reason_codes dùng được)
- `OK` (`green`): đủ số dư và nằm trong hạn mức chi cho phép.
- `OVER_LIMIT` (`yellow`): số tiền hóa đơn vượt hạn mức mỗi hóa đơn hoặc hạn mức tự chi trong ngày theo mandate/nền tảng, cần Chủ chuỗi duyệt.
- `LOW_BALANCE` (`yellow`): số dư ví MoMo Doanh Nghiệp hiện không đủ để thanh toán hóa đơn này.

## Khi nào báo đỏ
Bot `treasury` không phát hành mã đỏ độc lập (`OVER_LIMIT` và `LOW_BALANCE` ở mức `yellow`). Mọi quyết định chặn cứng (`DENY`) do Payment Gate thực thi bằng code.
