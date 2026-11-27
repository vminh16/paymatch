# Các luồng nghiệp vụ

Trạng thái: **Đã chốt (v0.3, 26/11/2026)**. Bám [problem-definition.md](../01-requirements/problem-definition.md) D1–D9. Mỗi luồng v1 có ít nhất một test end-to-end (xem [repo-and-testing.md](repo-and-testing.md)). Luồng đánh dấu *(lộ trình)* chưa làm trong v1.

## Trạng thái hóa đơn

```
new ──► investigating ──► auto_pay_eligible ──────────────┐
                      ├──► pending_approval ──► approved ─┼──► scheduled ──► paying ──► paid
                      └──► blocked (🔴) ──(gỡ nguyên nhân)─┘                       └──► payment_failed ──► pending_approval
investigating ──(tổng ≤ 0 và 🟢/🟡: HĐ điều chỉnh giảm / chiết khấu / 0 đ)──► no_payment_due   (không chi; 🔴 vẫn blocked)
pending_approval | blocked ──► rejected
approved | scheduled | auto_pay_eligible ──(cảnh báo chéo mới, D8)──► pending_approval (approval cũ bị thay)
approved | scheduled | pending_approval | blocked | payment_failed ──(điều tra lại)──► investigating
approved | scheduled ──(chủ chuỗi hủy chi)──► pending_approval
paying ──(Gate từ chối lúc execute)──► pending_approval | blocked
paying ──(token quá hạn)──► scheduled
blocked ──(chọn escrow, D7)──► escrow_held ──(duyệt kênh escrow + phiếu nhập → giải ngân)──► paid
escrow_held ──(hoàn cọc / thay bằng hóa đơn giao hàng khác)──► rejected
```

Mỗi lần đổi trạng thái là compare-and-set, mỗi trạng thái đích có một bên ghi; bảng đầy đủ ở [05-api/events.md](../05-api/events.md). Mọi lần đổi trạng thái khỏi `approved`/`scheduled` làm approval cũ thành `superseded`: phải duyệt lại.

## F1. Hóa đơn → điều tra → duyệt → chi

```
email kèm XML HĐĐT về hộp thư hóa đơn (demo: sim-world /scenario gửi) / tải XML lên / MoMo bill pay
  ──► core ingest: lưu file gốc (hash) → parse XML → kiểm tổng, chống trùng (MST bán + ký hiệu + số), NCC đã biết?
      → invoices + invoice_lines; thân email gắn kèm (untrusted); lỗi → Finding `ingest` → tạo job
agent-worker claim ──► plan (bot bắt buộc + bot khớp trigger) ──► các bot chạy song song ──► Finding
  ──► gộp màu (code) ──► tờ trình; core đẩy tiến trình qua GET /m/jobs/{id}/events (SSE)
core: invoice.status = auto_pay_eligible (🟢) | pending_approval (🟡) | blocked (🔴)
chủ chuỗi Duyệt (từng hóa đơn, hoặc duyệt hàng loạt) ──► core tạo một approval cho MỖI hóa đơn
      {invoice_id, intent_hash, approver, method: single|bulk|mandate, at}
chủ chuỗi Từ chối (sai giá/quy cách) ──► soạn sẵn yêu cầu NCC xuất hóa đơn điều chỉnh → rejected
Thủ quỹ đề xuất ngày chi (theo hạn trả) → invoice.scheduled_for; chủ chuỗi có thể chọn "trả ngay"
core-worker đến ngày ──► gate POST /intents ──► POST /intents/{id}:execute  (chi tiết: payment-gate.md)
gate: đọc lại invoice, payee từ danh bạ NCC, mandate, policy, cảnh báo chéo, hạn mức ngày (khóa dòng)
      → token một lần → ledger (unique invoice_id)
      → sim-world /rails/transfers (hoặc /rails/cards) → kết quả → outbox payment.executed | payment.failed
core: invoice.status = paid | payment_failed; audit
```

Mục tiêu tốc độ: từ lúc tạo job đến khi có màu ≈ 30 giây (ngân sách mỗi bot 20 giây, các bot chạy song song; brief 5 giây). UI hiện tiến trình theo từng bot.

## F2. Tự chi

Như F1, ở bước 🟢 core kiểm mandate (chế độ tự chi, NCC trong danh sách, trong hạn mức mandate, và trong trần policy nền tảng 30 triệu/HĐ, 50 triệu/ngày) rồi tạo approval `method = mandate`. Gate kiểm lại toàn bộ (không tin core).

**Tự hạ quyền (QT-03)**: bất kỳ mã lý do nào trong danh sách QT-03 (`PAYEE_CHANGE_REQUEST`, `PRICE_ABOVE_CONTRACT`, `PACK_SIZE_CHANGED`, `QUANTITY_ABOVE_NORM`, `DUPLICATE_INVOICE`, `TAX_RISK_LIST`, `HIDDEN_INSTRUCTION`, `UTILITY_OUT_OF_RANGE`, `CROSS_ALERT_HIT`) xuất hiện → hóa đơn đó không được tự chi, **và** NCC đó bị tạm đưa ra khỏi `auto_pay_vendors` cho tới khi chủ chuỗi bật lại. Mandate không đổi version; danh sách tạm loại lưu riêng (`auto_pay_suspensions`).

## F3. Cảnh báo chéo (MT6, D6, D8)

```
Cửa hàng A: Finding 🔴 PERSONAL_ACCOUNT + HIDDEN_INSTRUCTION
  → outbox indicator.flagged {account_hash, tax_id, phone, reason_codes}
     (phone: phone_on_file của registry VÀ NBan/SDThoai trên XML; số trên XML chỉ được băm làm indicator, không bao giờ là số gọi lại)
core-worker (risk): tạo alert vào hàng chờ console
chuyên viên MoMo xác nhận → cross_alert.published (1 người)
core-worker:
  - tìm hóa đơn CHƯA CHI của mọi tenant khác khớp indicator (pending_approval, auto_pay_eligible, approved, scheduled)
    → thêm Finding hệ thống CROSS_ALERT_HIT (🟡, bắt buộc xác minh) → approved/scheduled quay về investigating → pending_approval
  - thông báo cho cửa hàng bị ảnh hưởng
Cửa hàng B (hóa đơn mới): bot fraud-control gọi tool cross_alerts → khớp → 🟡 CROSS_ALERT_HIT
Gate lúc execute: indicator khớp cảnh báo chéo mà approval chưa ghi xác minh → DENY
Duyệt hóa đơn có CROSS_ALERT_HIT: chủ chuỗi phải xác nhận "đã gọi số lưu sẵn để xác minh" (ghi vào approval)
```

Chặn cứng chỉ khi indicator khớp danh sách chính thức (SIMO giả lập) → `OFFICIAL_FRAUD_LIST` 🔴.

## F4. Kill switch

Chuyên viên MoMo **bật** ngay (1 người, ghi lý do) → `control.policies` cập nhật → Gate đọc ở mỗi lần execute → chặn. **Gỡ** cần maker-checker (người đề xuất ≠ người duyệt). Gate không đọc được policy → từ chối (fail-closed). Phạm vi: indicator · cửa hàng · bot · tool · tắt tự chi toàn mạng.

## F5. Tạo bot (v1: qua form)

```
Form: chủ chuỗi điền name, description, skill, chọn tool (chỉ trong registry ∩ tool_grants), triggers
  → manifest draft → pending_review → core validate (schema, tool, reason codes) → chủ chuỗi duyệt → active
```

*(lộ trình)* Tạo qua chat (LLM soạn manifest nháp, cùng đường duyệt); chia sẻ template → MoMo duyệt → marketplace; shadow mode.

## F6. CSKH tra bằng chứng

CSKH nhập mã ticket → console-api trả chuỗi: giao dịch → hóa đơn (file gốc) → **hợp đồng / dòng hợp đồng đã đối chiếu** → Finding (+ tool_calls, trace) → approval → token. PII che mặc định; mọi lần xem ghi `access_log`.

## F7. Cọc tạm giữ cho NCC mới (D7)

```
NCC mới đòi cọc (hóa đơn/tin nhắn) → 🔴 (PERSONAL_ACCOUNT …) → cách gỡ duy nhất: escrow
chủ chuỗi nhập TK CÔNG TY của NCC (đúng tên + MST, không phải TK cá nhân)
  → vendor_accounts.status = escrow_only (xác thực mạnh, ghi bằng chứng)
chủ chuỗi tạo/chọn purchase_order → Gate POST /escrows {purchase_order_id, vendor_account_id, amount}
  → sim-world /rails/escrow: held
hóa đơn giao hàng của NCC về → điều tra → chủ chuỗi duyệt hóa đơn đó (kênh escrow)
quản lý quán xác nhận nhận đủ hàng (goods_receipt)
  → core-worker Gate /escrows/{id}:release {approval_id, goods_receipt_id} → released; hóa đơn giao hàng → paid
quá hạn không giao hàng → refunded
```

TK `escrow_only` không bao giờ nhận chuyển khoản thường. Muốn nâng lên `verified` phải qua F12 sau khi đã giao dịch thành công.

## F8. Thẻ ảo bị dùng sai

Thẻ ảo gắn {merchant, số tiền, một lần}. Demo: `POST /sim/scenario/cards/{card_id}:swipe` cho kẻ gian quẹt thẻ ở merchant khác hoặc lần thứ hai → sim-world từ chối, gửi webhook `card.authorization_declined` → `indicator.flagged {card_id, merchant_id}` → alert trên console MoMo.

## F9. Điện nước

Hóa đơn điện nước về từ dịch vụ thanh toán hóa đơn của MoMo (hoặc `/scenario`) → ingest như F1 với `invoice_type = utility` → bot `branch-operations` (so 12 tháng + doanh thu quán) + `treasury` → như F1/F2.

## F10. Đối soát ledger với rail *(lộ trình)*

`core-worker` định kỳ so ledger của Gate với sổ của rail. Lệch → `reconciliation.mismatch` → cảnh báo console.

## F11. Khoản chi không có hóa đơn (QT-05)

Kế toán/chủ chuỗi ghi nhận khoản chi (số tiền, người nhận, lý do) → `expense_records` → **không chi qua PayMatch** → nhắc lập bảng kê hằng tháng. Ngoại lệ duy nhất: cọc qua escrow (F7).

## F12. Thêm/đổi tài khoản NCC (BR-05, QT-04)

```
yêu cầu đổi TK (từ hóa đơn/tin nhắn → PAYEE_CHANGE_REQUEST, hoặc kế toán nhập)
  → vendor_verifications: pending
  → kế toán/chủ chuỗi gọi lại SĐT đã lưu sẵn trong danh bạ (không dùng số trong tin nhắn), ghi kết quả
  → chủ chuỗi xác thực mạnh để duyệt → vendor_accounts cập nhật (TK cũ giữ lịch sử)
  → các hóa đơn blocked vì PAYEE_CHANGE_REQUEST của NCC đó → investigating
```

TK phải đúng tên tổ chức và khớp MST. Agent không bao giờ tạo hay sửa bản ghi ở đây (QT-04).
