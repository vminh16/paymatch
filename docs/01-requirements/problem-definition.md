# Định nghĩa bài toán

Trạng thái: **Đã chốt (26/11/2026)**. Mọi thiết kế phải đối chiếu với tài liệu này; thay đổi ở đây cần cả đội đồng ý.

> **Cập nhật persona (26/11/2026):** Persona đã chốt ở [docs/04-data/persona.md](../04-data/persona.md) (chuỗi 15 quán + 1 bếp trung tâm, ~45 NCC, ~550 hóa đơn/tháng, ≤ 100 lao động có BHXH) **thay thế các con số quy mô ở BRD §5.1**; bản gốc [PayMatch_BRD_v1.0.md](PayMatch_BRD_v1.0.md) giữ nguyên làm tài liệu lịch sử.

## 1. Bài toán

**Trước khi tiền rời tài khoản, trả lời: hóa đơn này có nên trả không, trả bao nhiêu, cho ai, qua kênh nào — kèm bằng chứng cho mỗi câu trả lời — và con người chỉ phải xem những khoản đáng ngờ.**

Là **kiểm soát trước khi chi**, kèm trợ lý hỏi đáp chỉ-đọc trên chính dữ liệu đó. Không phải: làm sổ sách, kê khai thuế, bot OCR, công cụ nhắn tin với nhà cung cấp.

## 2. Đầu vào

| Nhóm | Gồm | Khi nào | Tin cậy |
|---|---|---|---|
| ① **Hóa đơn** (kích hoạt hệ thống) | XML HĐĐT qua email nhận hóa đơn / tải lên; hóa đơn điện nước từ MoMo; ảnh-PDF khi không có XML (luôn ≥ vàng) | Mỗi lần NCC gửi | Số: tin được (code parse). Chữ: **untrusted** |
| ② **Dữ liệu gốc** | Danh bạ NCC (TK đã xác minh, SĐT lưu sẵn), hợp đồng khung (mặt hàng, quy cách, đơn giá), danh sách quán, mandate | Nhập một lần; sửa có kiểm soát | Tin được |
| ③ **Dữ liệu vận hành** | Đơn đặt hàng, phiếu nhập (quản lý quán xác nhận), sổ công nợ, điện nước 12 tháng, doanh thu MoMo theo quán, số dư | Hằng ngày | Tin được |
| ④ **Ngữ cảnh bên ngoài** | Email, Zalo của người bán; ghi chú trên hóa đơn | Đi kèm hóa đơn | **Untrusted** |
| ⑤ **Tra cứu chính thức** | Cổng HĐĐT, trạng thái MST, DS doanh nghiệp rủi ro, SIMO, cảnh báo chéo MoMo | Bot tra khi điều tra | Tin được |
| ⑥ **Con người** | Chủ chuỗi duyệt/từ chối; quản lý quán xác nhận nhận hàng; nhân viên MoMo xử lý case | Khi được hỏi | Tin được |

## 3. Xử lý

```
① hóa đơn ──► ingest (code) ──► 6 bot điều tra bằng ②③④⑤ ──► gộp màu (code)
          ──► 🟢 + mandate cho phép ──► Gate ──► chi
          ──► 🟡/🔴 ──► chủ chuỗi quyết ──► Gate ──► chi / không chi
```

## 4. Đầu ra

| Cho ai | Đầu ra |
|---|---|
| Chủ chuỗi, kế toán, quản lý quán | **Hỏi đáp** về hóa đơn, chi tiêu, NCC, hàng chờ (chỉ-đọc, có trích dẫn số liệu). Chủ chuỗi thêm: mỗi hóa đơn: màu + mã lý do + tờ trình 5 dòng chỉ vào dòng sai trên chứng từ gốc; hàng chờ chỉ gồm vàng/đỏ; cảnh báo phụ (gọi lại xác minh NCC, nghi rò nước); nội dung soạn sẵn yêu cầu NCC xuất hóa đơn điều chỉnh |
| Tiền | **Đúng một giao dịch cho một hóa đơn**, đúng người nhận trong danh bạ, đúng số tiền trên hóa đơn, đúng kênh — hoặc không chi |
| Kế toán / kiểm toán | Truy ngược: giao dịch → hóa đơn → hợp đồng → Finding → người duyệt |
| MoMo | Cảnh báo/case toàn mạng, cảnh báo chéo, bằng chứng cho CSKH, báo cáo SIMO, chỉ số chất lượng bot, lệch đối soát |

## 5. Quyết định nghiệp vụ đã chốt

| # | Quyết định | Lý do |
|---|---|---|
| D1 | **Đơn vị quyết định là từng hóa đơn**: mỗi hóa đơn có tối đa **một bản ghi duyệt đang hiệu lực**, gắn với lần điều tra mới nhất (điều tra lại → duyệt lại). **Không có nghĩa là người phải bấm từng hóa đơn** — xem mục 6a | Mỗi Finding, tờ trình, bằng chứng, giao dịch gắn với một hóa đơn |
| D2 | **Chi theo từng hóa đơn: 1 hóa đơn = 1 payment intent = 1 giao dịch.** Không gom lô trong v1. Nội dung chuyển khoản ghi `MST người bán · ký hiệu · số hóa đơn` | Xem mục 6 |
| D3 | **Chỉ hai lựa chọn với hóa đơn có vấn đề: "Duyệt" (trả đúng số trên hóa đơn) hoặc "Từ chối"**. Từ chối vì sai giá/quy cách → hệ thống soạn sẵn nội dung yêu cầu NCC xuất **hóa đơn điều chỉnh**, chủ chuỗi tự gửi. Không có "trả theo giá hợp đồng" | Trả khác số trên hóa đơn làm lệch chứng từ; sai hóa đơn thì người bán phải điều chỉnh |
| D4 | **Chỉ chủ chuỗi duyệt** (một người duyệt cho mỗi hóa đơn). Kế toán xem và chuẩn bị, không duyệt | Bám persona; giữ Gate đơn giản |
| D5 | **🔴 = bị khóa cho tới khi gỡ được nguyên nhân.** Không có nút "duyệt đè". Mỗi mã lý do đỏ có đúng một cách gỡ (mục 6b); gỡ xong → điều tra lại → duyệt từng hóa đơn như 🟡 | BR-05; BRD mục 14 |
| D6 | **Cảnh báo chéo = 🟡 + bắt buộc xác minh**, không phải 🔴. Chỉ danh sách chính thức (SIMO, DS rủi ro thuế) mới chặn cứng | QT-07 |
| D7 | **Cọc cho NCC mới chỉ qua escrow, vào TK công ty đã đăng ký ở trạng thái `escrow_only`**; cọc gắn với **đơn đặt hàng**; giải ngân khi có phiếu nhập + hóa đơn khớp. TK cá nhân không bao giờ vào danh bạ | BR-06; kịch bản si-rô |
| D8 | **Khi MoMo gắn cảnh báo chéo**: đánh giá lại mọi hóa đơn chưa chi của các cửa hàng khác khớp indicator, thông báo cho cửa hàng; Gate kiểm cảnh báo chéo lần nữa ngay lúc chi | MT6; "Bẫy cuối" |
| D9 | **Trần 30 triệu/HĐ, 50 triệu/ngày cho tự chi là policy nền tảng**, mandate chỉ được đặt thấp hơn | QT-01 |

## 6a. Hàng trăm hóa đơn thì duyệt thế nào

Một chuỗi 15 quán + 1 bếp trung tâm phát sinh **~550 hóa đơn/tháng (~18 hóa đơn/ngày)** (giả định của nhóm, không có nguồn công khai; xem [persona.md](../04-data/persona.md)). Mỗi hóa đơn được duyệt bằng **một trong ba cách**, nhưng luôn sinh **một bản ghi duyệt riêng** gắn đúng intent của hóa đơn đó:

| Cách duyệt | Áp cho | Người làm gì |
|---|---|---|
| **Tự động theo mandate** | 🟢 trong chế độ tự chi, trong hạn mức (≤ 30 triệu/HĐ, ≤ 50 triệu/ngày theo D9) | Không làm gì; nhận tóm tắt cuối ngày |
| **Duyệt hàng loạt** | 🟢 trong chế độ "hỏi trước khi chi" hoặc 🟢 vượt trần ngày D9 (khi tổng chi 50–80 triệu/ngày); 🟡 có **mã lý do nhẹ** do chủ chuỗi chọn sẵn (ví dụ `NON_XML_SOURCE` dưới 2 triệu) | Xem danh sách gộp theo NCC/lý do → một lần xác thực → hệ thống tạo N bản ghi duyệt, mỗi bản ký vào intent của một hóa đơn |
| **Duyệt từng hóa đơn** | 🟡 còn lại; 🔴 sau khi đã gỡ nguyên nhân (mục 6b) | Đọc tờ trình 5 dòng, bấm Duyệt/Từ chối |

Kỳ vọng: với ~18 hóa đơn/ngày, nếu ~80% hóa đơn xanh (`18 × 80% = 14,4 HĐ/ngày`) và tỷ lệ báo nhầm ≤ 10% (MT4): số hóa đơn vàng/đỏ thực là `18 × (1 − 80%) = 3,6 HĐ/ngày`, cộng tối đa `14,4 × 10% ≈ 1,4 HĐ/ngày` báo nhầm trên nhóm xanh → tổng là `3,6 + 1,4 = 5,0` (**khoảng 4–5 hóa đơn/ngày**; trừ phần nhỏ vàng nhẹ duyệt hàng loạt thì chủ chuỗi đọc kỹ khoảng **3–5 hóa đơn/ngày**). Phần hóa đơn xanh trong trần D9 tự chi theo mandate; phần xanh vượt trần ngày gom vào một lần duyệt hàng loạt cuối ngày.

Quy tắc an toàn của duyệt hàng loạt:
- 🔴 **không bao giờ** vào duyệt hàng loạt.
- Danh sách 🟡 được duyệt hàng loạt là cấu hình trong mandate (chủ chuỗi chọn mã lý do + ngưỡng tiền), không phải AI chọn.
- Hóa đơn thay đổi sau khi vào danh sách → intent hash đổi → bị loại khỏi lần duyệt đó.
- Hàng chờ gom theo **NCC** và **mã lý do** để một lần nhìn thấy cùng một loại vấn đề (ví dụ 5 hóa đơn cùng NCC cùng tăng giá).

## 6b. Gỡ khóa 🔴

| Mã lý do đỏ | Cách gỡ | Kết quả |
|---|---|---|
| `PAYEE_CHANGE_REQUEST` | Luồng đổi TK NCC (F12): gọi lại số đã lưu, ghi bằng chứng, chủ chuỗi xác thực mạnh → cập nhật danh bạ | Điều tra lại hóa đơn |
| `PERSONAL_ACCOUNT`, `HIDDEN_INSTRUCTION`, `TAX_RISK_LIST`, `MST_INACTIVE` (NCC mới / người bán lạ) | Chỉ cho phép **escrow** vào TK công ty `escrow_only` (F7), kèm cảnh báo rủi ro khấu trừ VAT; hoặc Từ chối | Không bao giờ chuyển thẳng |
| `OFFICIAL_FRAUD_LIST` (SIMO), `DUPLICATE_INVOICE` | Không gỡ được | Chỉ Từ chối |
| `OVER_LIMIT` | Không phải đỏ: 🟡, duyệt từng hóa đơn | — |

## 6c. Phạm vi v1 (trước 03/12/2026)

| Làm trong v1 | Để lộ trình (giữ thiết kế trong docs) |
|---|---|
| Ingest XML; 6 bot; Gate (3 kênh, mandate, duyệt từng/hàng loạt); sim-world | Ingest ảnh/PDF bằng model đọc tài liệu (v1: nhận file, gắn `NON_XML_SOURCE`, không trích tự động) |
| Bot người dùng tạo **qua form**, manifest + duyệt, kiến trúc plugin | Tạo bot qua chat; marketplace template; shadow mode |
| Console MoMo: luồng cảnh báo, case đơn giản, cảnh báo chéo (1 người), kill switch (1 người bật, 2 người gỡ), tra bằng chứng có mã ticket | Gom cụm, chấm điểm, đồ thị thực thể, báo cáo SIMO, RBAC đầy đủ, break-glass |
| Frontend: hàng chờ duyệt + thẻ duyệt 5 dòng; **hỏi đáp cơ bản với trợ lý**; console tối thiểu; nút reset demo | Memory của bot; đối soát ledger với rail (F10) |
| Eval 36 ca × 3 cấu hình; `merchant-api`/`console-api`/`internal-api` là ba container cùng image | Scale ngang từng tiến trình theo tải |

## 6. Vì sao chi theo từng hóa đơn (D2)

Ngoài đời, kế toán có hai cách: trả từng hóa đơn theo hạn, hoặc gom nhiều hóa đơn của một NCC trả một lần theo kỳ đối chiếu công nợ. Với PayMatch, trả từng hóa đơn tốt hơn vì:

- **Minh bạch:** nhìn một giao dịch là biết ngay nó trả cho hóa đơn nào; không cần bảng phân bổ.
- **Dễ kiểm soát:** một hóa đơn bị đỏ không kéo cả lô dừng lại; từ chối/hoàn một khoản không ảnh hưởng khoản khác.
- **Thuế:** hóa đơn ≥ 5 triệu cần chứng từ thanh toán không dùng tiền mặt để khấu trừ VAT (NĐ 181/2025); một giao dịch khớp một hóa đơn là chứng từ rõ nhất.
- **An toàn:** đúng BR-11 (mỗi lệnh trả dùng một lần cho đúng một hóa đơn và đúng người nhận); idempotency theo `invoice_id`.
- **Đối soát:** khớp 1–1 giữa ledger, rail và hóa đơn.

Thủ quỹ vẫn **xếp lịch** (trả theo hạn, ưu tiên theo số dư) nhưng không gộp giao dịch. Gom lô theo NCC để ở lộ trình nếu phí chuyển khoản hoặc số lượng giao dịch thành vấn đề; khi đó mỗi dòng trong lô vẫn phải gắn một hóa đơn.

## 7. Giả định (chưa xác nhận, dùng mặc định theo BRD)

- A1. Nguồn tiền là số dư MoMo Doanh Nghiệp của chuỗi.
- A2. Phạm vi chi: nhà cung cấp (nguyên liệu, bao bì), điện nước, phần mềm. Không gồm lương, tiền thuê mặt bằng.
- A3. Chi không có hóa đơn: chỉ ghi nhận, không tự chi (QT-05). Ngoại lệ duy nhất: **cọc cho người bán mới qua cọc tạm giữ**, giải ngân khi nhận đủ hàng.
- A4. Đa số hóa đơn nguyên liệu, bao bì có XML trước lúc trả tiền (BRD A1, cần phỏng vấn kiểm chứng).
