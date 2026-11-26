# Dữ liệu

Trạng thái: **Đang thu thập (26/11/2026)**.

## Nguyên tắc: mẫu thật trước, sinh sau

Không tự nghĩ ra định dạng hay con số. Mỗi loại dữ liệu mà sim-world sinh ra phải bám vào **một mẫu thật** (văn bản pháp lý, chứng từ thật đã xóa thông tin, bảng giá đã công bố) lưu trong [references/](references/), có ghi nguồn và ngày lấy.

- **Mẫu thật quyết định hình dạng**: thẻ XML, bố cục hóa đơn điện nước, quy cách hàng, đơn vị tính.
- **Số liệu thật quyết định khoảng giá trị**: đơn giá, biểu giá điện, tỷ lệ thuế.
- **Bộ sinh chỉ điền giá trị** vào hình dạng đó, theo seed cố định. Lỗi được cấy bằng kịch bản (overlay), nên nhãn đúng/sai có sẵn.
- Dữ liệu nào **chưa có mẫu thật** thì ghi "chưa có" trong bảng dưới, không sinh cho tới khi có.

## Tình trạng mẫu thật

| Loại dữ liệu | Mẫu thật | Trạng thái | Tài liệu |
|---|---|---|---|
| Hóa đơn điện tử XML: định dạng thẻ | QĐ 1271/QĐ-CT ngày 30/05/2025 của Cục Thuế (bản gốc 317 trang) | ✅ Có, đã trích | [einvoice-xml.md](einvoice-xml.md) |
| Hóa đơn điện tử XML: file thật của một công ty | Hóa đơn đầu vào thật team nhận được, xóa MST/tên/số tiền | ❌ Chưa có, cần team cung cấp | [einvoice-xml.md §5](einvoice-xml.md#5-file-thật-còn-thiếu) |
| Biểu giá điện kinh doanh | QĐ 2892/QĐ-BCT, hiệu lực 1/11/2026 | ✅ Có số liệu (từ báo, cần đối chiếu văn bản) | [sources.md §2](sources.md#2-biểu-giá-điện) |
| Hóa đơn tiền điện, tiền nước: bố cục | Hóa đơn EVN/cấp nước thật của một quán, xóa mã KH | ❌ Chưa có | [sources.md](sources.md) |
| Giá nước kinh doanh | Quyết định giá nước của TP.HCM | ❌ Chưa tìm được | [sources.md](sources.md) |
| Giá nguyên liệu, bao bì | Trang sản phẩm siêu thị trực tuyến | ❌ Không truy cập được từ môi trường này | [sources.md §3](sources.md#3-giá-hàng-hóa) |
| Tin nhắn/email lừa đảo | Bài cảnh báo công khai của công an, ngân hàng, ví điện tử | ❌ Chưa thu thập | [sources.md](sources.md) |
| Persona doanh nghiệp | Đề xuất chuỗi F&B 15 quán + bếp trung tâm | 🟡 Đề xuất, chưa chốt | [persona.md](persona.md) |

## Thư mục

```
docs/04-data/
├── README.md            # file này
├── einvoice-xml.md      # cây thẻ XML hóa đơn GTGT theo QĐ 1271, ánh xạ sang mô hình của PayMatch
├── sources.md           # nguồn số liệu thật, quy tắc thu thập
├── persona.md           # doanh nghiệp giả lập (đề xuất)
└── references/          # bản gốc mẫu thật (không sửa)
    └── QD-1271-QD-CT-2025.pdf
```

Dữ liệu đã sinh nằm ở `services/sim-world/data/`, không nằm trong docs.
