# Thuật ngữ

| Thuật ngữ | Nghĩa trong PayMatch |
|---|---|
| Agent / bot | Một vai nghề trong phòng kế toán ảo; có skill, tool và giới hạn quyền riêng |
| Kế toán trưởng | Agent điều phối ReAct (privileged): nhận việc, gọi bot chuyên môn như tool; không đọc nội dung thô từ người bán |
| Loại việc (`task_type`) | `investigate_invoice`, `question`, `report`; mỗi loại có tool, ngân sách, điều kiện hoàn tất riêng |
| Điều kiện hoàn tất | Luật code kiểm khi agent kết thúc (ví dụ đủ Finding của bot bắt buộc), thay cho luồng viết cứng |
| Skill | Checklist nghề viết bằng chữ, dùng lại được |
| Routine | Sự kiện kích hoạt đội agent (hóa đơn về, lịch điện nước) |
| Tool registry | Danh sách tool chỉ-đọc (đọc DB core hoặc sim-world); bot chỉ dùng tool có trong capability token |
| `escrow_only` | Trạng thái TK công ty của NCC mới: chỉ được nhận tiền qua cọc tạm giữ |
| Gỡ khóa 🔴 | Xử lý đúng nguyên nhân của mã lý do đỏ (xác minh TK, chuyển sang escrow) rồi điều tra lại |
| Thế giới giả lập | Dữ liệu JSON thay cho nguồn vào thật |
| Finding | Kết quả có cấu trúc của một bot: mức, lý do, bằng chứng, nhãn nguồn |
| Nhãn nguồn gốc | `trusted` (chủ chuỗi, danh bạ đã xác minh) / `untrusted` (nội dung từ người bán, tin nhắn) |
| Mandate | Ủy quyền chủ chuỗi ký: chế độ chi, hạn mức, NCC được tự chi |
| Payment Gate (Khóa chi) | Code kiểm điều kiện và phát token trả một lần; không phải AI |
| Đối chiếu 3 chứng từ | Đơn đặt hàng ↔ phiếu nhập kho ↔ hóa đơn |
| Gọi lại xác minh | Gọi số NCC đã lưu sẵn, không dùng số trong tin nhắn yêu cầu đổi TK |
| Cọc tạm giữ | Tiền cọc nằm ở ngân hàng; nhận đủ hàng mới giải ngân |
| Cảnh báo chéo | MoMo gắn cờ kẻ gian phát hiện ở một cửa hàng cho mọi cửa hàng khác |
