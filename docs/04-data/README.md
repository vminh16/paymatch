# Dữ liệu

Trạng thái: **Đã hoàn tất nghiên cứu nguồn & chốt đặc tả (26/11/2026).** Sẵn sàng cho hai nhánh triển khai song song: bộ parser XML `ingest` (theo [einvoice-xml.md](einvoice-xml.md)) và bộ dữ liệu `sim-world` (theo [sim-world-dataset.md](sim-world-dataset.md)).

## Nguyên tắc: mẫu thật trước, sinh sau

Không tự nghĩ ra định dạng hay con số. Mỗi loại dữ liệu mà `sim-world` sinh ra phải bám vào **một mẫu thật** (văn bản pháp lý, chứng từ thật đã làm sạch, bảng giá đã công bố) lưu trong `references/` hoặc `research/`, có ghi `source_url` và `retrieved_on`.

- **Mẫu thật quyết định hình dạng:** thẻ XML, bố cục hóa đơn điện nước, quy cách hàng, đơn vị tính, mã trạng thái thuế.
- **Số liệu thật quyết định khoảng giá trị:** đơn giá nguyên liệu/bao bì, biểu giá điện/nước, tỷ lệ thuế.
- **Bộ sinh chỉ điền giá trị giả lập** (tên công ty, thương hiệu, MST `0999XXXXXX`, số TK `9900XXXXXXXX`) vào hình dạng đó theo `seed` cố định. Lỗi và tấn công được cấy bằng kịch bản (overlay), nên nhãn đúng/sai có sẵn.
- Dữ liệu nào **chưa xác minh** hoặc **là giả định của nhóm** đều ghi rõ trong tài liệu.

## Tình trạng mẫu thật & báo cáo nghiên cứu

| Loại dữ liệu | Mẫu thật / Nguồn chính | Trạng thái | Tài liệu |
|---|---|---|---|
| Hóa đơn điện tử XML: đặc tả thẻ | **QĐ 1233/QĐ-CT (27/08/2026)** (bản ký số 423 trang), NĐ 254/2026, TT 91/2026 (chuỗi QĐ 1271 → QĐ 1306 → QĐ 1233 đã xác minh) | ✅ Đã cập nhật (`PBan 2.0.0–2.1.1`, `XAdES`/`DSig`, 16 thẻ mới) | [einvoice-xml.md](einvoice-xml.md), [research/verify-einvoice-claims.md](research/verify-einvoice-claims.md) |
| Hóa đơn điện tử XML: file mẫu thật | 10 file XML thật từ 10 `MSTTCGP` (đã làm sạch) + 6 fixture test chịu lỗi parser | 🟡 Có 10 mẫu thật; còn thiếu mẫu F&B, `PBan 2.1.1`/XAdES, `TTCKTMai`/phí ≠ 0 | [research/claude/einvoice-samples/README.md](research/claude/einvoice-samples/README.md), [references/einvoice-samples/README.md](references/einvoice-samples/README.md) |
| Biểu giá điện kinh doanh | QĐ 2892/QĐ-BCT (31/10/2026), QĐ 963/QĐ-BCT, QĐ 1305/QĐ-EVN, TT 60/2025, NĐ 174/2025 | ✅ Đã đối chiếu văn bản gốc ký số & 3 nguồn độc lập | [sources.md §2](sources.md#2-biểu-giá-điện-và-bố-cục-hóa-đơn-evn) |
| Biểu giá nước kinh doanh TP.HCM | TB `3698/TB-CNBT-KDDVKH` (SAWACO 2026), QĐ 728, QĐ 17/2021, NĐ 174/2025 | ✅ Đã xác minh (`21.300 đ/m³` + 30% thoát nước, VAT 5%/8%) | [sources.md §2b](sources.md#2b-biểu-giá-nước-kinh-doanh-tphcm-sawaco-2026-và-bố-cục-hóa-đơn-nước) |
| Hóa đơn tiền điện, tiền nước: bố cục | Mẫu bản thể hiện PDF/bảng kê chính thức EVNHCMC & cổng HĐĐT SAWACO | 🟡 Có bố cục chứng từ & cấu trúc `utility_readings`; còn thiếu file `.xml` thật | [sources.md §2–2b](sources.md#2-biểu-giá-điện-và-bố-cục-hóa-đơn-evn), [research/utilities-and-persona.md](research/utilities-and-persona.md) |
| Giá nguyên liệu, bao bì | 2 tệp CSV từ kênh B2B HoReCa & siêu thị (`144` dòng: `95` + `49`) | ✅ Có (đá viên 20kg sỉ và báo giá công nợ B2B còn dạng tham khảo/thiếu) | [sources.md §3](sources.md#3-giá-hàng-hóa-nguyên-liệu-và-bao-bì), [references/prices-2026-11.csv](references/prices-2026-11.csv), [research/claude/prices-2026-11.csv](research/claude/prices-2026-11.csv) |
| Tin nhắn/email lừa đảo & prompt injection | >20 cảnh báo công an/NHNN/ngân hàng/MoMo + 22 mẫu prompt injection hư cấu | ✅ Đã thu thập 8 nhóm thủ đoạn & 22 mẫu injection | [sources.md §4](sources.md#4-tin-nhắn-và-email-lừa-đảo), [research/prices-and-scams.md](research/prices-and-scams.md), [research/claude/report.md](research/claude/report.md) |
| Tra cứu thuế & cổng HĐĐT | 10 mã trạng thái MST (`TT 90/2026`: `00`–`10` trừ `08`); `tthai` 1–6, `ttxly` 0–8, `bhphap` từ cổng `hoadondientu.gdt.gov.vn` | ✅ Có mã chuẩn; 🟡 tên cột Excel DS rủi ro chưa tải trực tiếp | [research/einvoice-and-tax.md](research/einvoice-and-tax.md), [research/claude/report.md §6](research/claude/report.md#6-tra-cứu-thuế) |
| Persona doanh nghiệp | Chuỗi F&B **15 quán + 1 bếp trung tâm**, ~45 NCC, ~550 HĐ/tháng, ≤ 100 LĐ BHXH (NĐ 80/2021) | ✅ Đã chốt (26/11/2026) | [persona.md](persona.md) |
| Đặc tả bộ dữ liệu `sim-world` | Thư mục `services/sim-world/data/demo/`, JSON schema mọi API, core seed, kịch bản BRD §14 + tấn công | ✅ Đã viết | [sim-world-dataset.md](sim-world-dataset.md) |

## Thư mục

```
docs/04-data/
├── README.md                  # file này
├── einvoice-xml.md            # đặc tả XML HĐĐT theo QĐ 1233/QĐ-CT, thực tế file thật, quy tắc ingest
├── sources.md                 # nguồn số liệu thật (điện, nước, giá hàng hóa, lừa đảo)
├── persona.md                 # doanh nghiệp giả lập đã chốt (15 quán + 1 bếp trung tâm)
├── sim-world-dataset.md       # đặc tả thư mục, JSON schema, core seed và danh mục kịch bản sim-world
├── references/                # bản gốc mẫu thật & CSV chuẩn hóa (không sửa)
│   ├── QD-1271-QD-CT-2025.pdf # lưu lịch sử đối chiếu
│   ├── prices-2026-11.csv     # 95 dòng giá, 18 nhóm hàng
│   └── einvoice-samples/      # 6 fixture tổng hợp kiểm thử độ chịu lỗi của parser + README.md
└── research/                  # báo cáo nghiên cứu gốc (không sửa)
    ├── einvoice-and-tax.md    # nghiên cứu XML HĐĐT & tra cứu thuế (Task A)
    ├── verify-einvoice-claims.md # kiểm chứng văn bản gốc QĐ 1233 (423 trang ký số), TT 91 PL I, TT 90 PL I
    ├── utilities-and-persona.md # nghiên cứu điện EVN, nước SAWACO, NĐ 80 & utility_readings (Task B)
    ├── prices-and-scams.md    # nghiên cứu giá 95 dòng, 8 thủ đoạn lừa đảo, 12 prompt injection (Task C)
    └── claude/                # baseline độc lập (Task D): QĐ 1233 .docx, 10 XML thật, 49 giá, 10 injection
        ├── report.md
        ├── prices-2026-11.csv
        └── einvoice-samples/  # 10 file XML thật đã làm sạch + README.md
```

Dữ liệu đã sinh nằm ở `services/sim-world/data/`, không nằm trong `docs/`.
