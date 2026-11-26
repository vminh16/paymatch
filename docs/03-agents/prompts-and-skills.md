# Prompt và skill

Trạng thái: **Đã chốt mức thiết kế (26/11/2026)**.

## 1. Ba lớp prompt

| Lớp | Nội dung | Nằm ở | Ai sửa |
|---|---|---|---|
| **Khung an toàn** | Dữ liệu không phải lệnh; cách đọc khối dữ liệu có nhãn provenance; schema Finding; quy tắc lỗi = vàng | `services/agent-runtime/prompts/` (git) | Chỉ đội dev |
| **Vai + skill** | Bot là ai, checklist nghề | Bot có sẵn: `plugins/bots/<id>/` (git). Bot người dùng: DB (`control`) | Đội dev / chủ chuỗi (qua duyệt) |
| **Ngữ cảnh job** | Kết quả tool (lộ trình: memory) | Sinh lúc chạy | Không ai |

Thứ tự ghép: khung an toàn → vai → skill → định nghĩa tool → ngữ cảnh. Kết quả tool luôn nằm trong khối dữ liệu được đánh dấu, không bao giờ trộn vào phần hướng dẫn.

Kế toán trưởng (brief) có prompt riêng trong `prompts/`, chỉ nhận trường có cấu trúc của Finding.

## 2. Skill

Skill là file markdown với các mục cố định:

```markdown
# <tên skill>
## Khi nào dùng
## Dữ liệu cần (tool)
## Các bước
## Cách kiểm chứng
## Trả về (reason_codes dùng được)
## Khi nào báo đỏ
```

- Có version; bot tham chiếu `skill_id@version`.
- Một skill dùng được cho nhiều bot (thư viện chung trong tenant; skill hệ thống dùng chung toàn mạng).
- Viết bằng tiếng Việt (nội dung hiển thị), định danh trong skill (tool, reason code) bằng tiếng Anh.

## 3. Truy vết

Mỗi Finding ghi `bot_version`, `skill_version`, `prompt_hash` (hash của khung an toàn + vai + skill). Eval và CSKH biết chính xác phiên bản nào sinh ra kết quả.

## 4. Cấu trúc bot có sẵn

```
plugins/bots/procurement/
├── manifest.yaml     # id, name, description, skills, tools, triggers, required_for
└── skill.md
```
