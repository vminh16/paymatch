# Hợp đồng bot (để người dùng tự thêm bot)

Trạng thái: **Đã chốt (26/11/2026)**. Tham khảo khái niệm Bot / Skill / Routine / Template của Grok Bot; định dạng dưới đây là của PayMatch (Grok không công bố manifest).

## Manifest

```yaml
bot:
  id: frozen-goods-inspector
  name: Kiểm hàng đông lạnh
  description: Soát nhiệt độ giao hàng và hạn dùng cho thịt, hải sản
  skills: [frozen_goods_checklist]        # hướng dẫn nghề bằng chữ: khi nào dùng, các bước, cách kiểm chứng, trả gì
  tools: [goods_receipts, delivery_temperature]   # CHỈ chọn từ tool registry (tất cả chỉ-đọc)
  task_types: [investigate_invoice, question]   # việc nào điều phối được gọi bot này
  triggers:
    invoice_types: [meat, seafood]
  status: pending_review                # pending_review → active sau khi chủ chuỗi duyệt
```

## Output bắt buộc: `Finding`

Định nghĩa đầy đủ ở [agent-runtime.md mục 5](agent-runtime.md#5-finding-hợp-đồng). Tóm tắt:

```yaml
Finding:
  bot_id: string
  severity: green | yellow | red
  reason_codes: [enum]           # Kế toán trưởng (LLM) chỉ đọc trường này
  reason: string              # chữ cho người đọc — luôn coi là untrusted
  evidence: [ref]          # id dòng hóa đơn / tin nhắn / bản ghi gốc
  provenance: trusted | untrusted # nhãn nguồn gốc của dữ liệu dẫn tới kết luận
```

Bot người dùng chỉ dùng `reason_codes` có sẵn hoặc `CUSTOM` (luôn tối thiểu vàng).

## Quy tắc

1. Tool chỉ chọn từ registry; **không cắm tool/MCP mới** (v1).
2. v1 tạo bot qua **form** (lộ trình: qua chat, cùng manifest và cùng đường duyệt). Manifest vào `pending_review`; chủ chuỗi duyệt mới chạy.
3. Bot **không nhắn trực tiếp** bot khác. Bot active tự thành tool `ask_<bot_id>` của Kế toán trưởng; bot nộp `Finding` (điều tra) hoặc `BotAnswer` (hỏi đáp) về core, core lọc rồi mới trả cho điều phối; gộp màu do code.
4. Bot chỉ có thể làm mức **nặng hơn** (gộp = mức nặng nhất). Bot dở/bị lừa tối đa gây báo nhầm, không gây mất tiền.
5. Chất lượng bot đo bằng tỷ lệ báo nhầm (MT4) trên bộ ca thử.
6. *(Lộ trình)* Bot có thể chia sẻ dưới dạng **template** (manifest + skill, không kèm dữ liệu).
