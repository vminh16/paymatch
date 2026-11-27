# Doanh nghiệp giả lập (persona)

Trạng thái: **Đã chốt (26/11/2026)**. Thay thế các con số quy mô ở BRD §5.1 (bản gốc [PayMatch_BRD_v1.0.md](../01-requirements/PayMatch_BRD_v1.0.md) giữ nguyên không sửa). Đã đồng bộ sang [problem-definition.md](../01-requirements/problem-definition.md) và [architecture.md](../02-architecture/architecture.md) (§1, §9).

## 1. Vì sao mở rộng

Chuỗi 5 quán cà phê có quá ít hóa đơn và quá ít NCC: chủ quán tự xem hết được, nên một đội agent không có lý do tồn tại. Cần một doanh nghiệp đủ lớn để duyệt tay từng hóa đơn không còn khả thi, nhưng vẫn thuộc nhóm doanh nghiệp nhỏ và vừa (DNNVV) dùng MoMo Doanh Nghiệp.

## 2. Quy mô đã chốt

| Hạng mục | Giá trị chốt |
|---|---|
| Loại hình | Chuỗi F&B: **15 quán** cà phê, trà, đồ ăn nhẹ ở TP.HCM + **1 bếp trung tâm** (sơ chế, nấu sốt, làm bánh) |
| Quy mô pháp lý | **Doanh nghiệp vừa** theo Điều 5 [NĐ 80/2021/NĐ-CP](https://datafiles.chinhphu.vn/cpp/files/vbpq/2021/08/80.signed_01.pdf) (lĩnh vực Thương mại và dịch vụ; doanh thu ước tính ~54–90 tỷ/năm ≤ 300 tỷ) |
| Lao động có BHXH | **≤ 100 người** bình quân năm (mô phỏng ~85–95 lao động có BHXH gồm văn phòng, quản lý 16 điểm, bếp trung tâm, ca trưởng; phần còn lại là nhân sự bán thời gian không thuộc diện đóng BHXH bắt buộc → giữ chuỗi trong ngưỡng DN vừa theo NĐ 80/2021) |
| Người dùng | 1 chủ chuỗi (duy nhất được duyệt, D4), 2 kế toán, 15 quản lý quán, 1 quản lý bếp trung tâm |
| Nhà cung cấp | **~45 NCC**, mỗi tháng thêm 2–3 NCC mới *(giả định của nhóm, không có số liệu thống kê công khai)* |
| Hóa đơn đầu vào | **~550 hóa đơn/tháng (~18 hóa đơn/ngày)** *(giả định của nhóm, không có nguồn công khai; xem bảng phân bổ bên dưới)* |
| Chi tiêu qua PayMatch | ~1,5–2,5 tỷ/tháng, tức **~50–80 triệu/ngày** |
| Trần tự chi nền tảng (D9) | **Giữ nguyên 30 triệu/HĐ, 50 triệu/ngày**; phần chi 50–80 triệu/ngày vượt trần ngày đi qua duyệt hàng loạt (`bulk`) hoặc duyệt từng hóa đơn (`single`) |

**Ngưỡng phân loại DNNVV theo Điều 5 NĐ 80/2021/NĐ-CP (lĩnh vực Thương mại và dịch vụ)** — thỏa đồng thời tiêu chí lao động BHXH bình quân năm **VÀ** một trong hai tiêu chí tài chính (doanh thu năm **HOẶC** tổng nguồn vốn):

| Quy mô | Lao động tham gia BHXH bình quân năm | Tổng doanh thu của năm | hoặc Tổng nguồn vốn |
|---|---:|---:|---:|
| Siêu nhỏ | ≤ 10 người | ≤ 10 tỷ đồng | ≤ 3 tỷ đồng |
| Nhỏ | ≤ 50 người | ≤ 100 tỷ đồng | ≤ 50 tỷ đồng |
| **Vừa** *(persona PayMatch)* | **≤ 100 người** | **≤ 300 tỷ đồng** | **≤ 100 tỷ đồng** |

**Ước tính hóa đơn mỗi tháng** *(giả định mô hình vận hành của nhóm, không có nguồn thống kê công khai)*:

| Nguồn | Cách tính | Số hóa đơn |
|---|---|---:|
| Bếp trung tâm: thịt, rau tươi | 10 NCC × 3 lần/tuần | ~130 |
| Hàng khô, nguyên liệu pha chế, bao bì | 15 NCC × hằng tuần | ~60 |
| Giao thẳng tới quán: sữa, đá, bánh mì | 15 quán × 2 NCC × ~10 lần | ~300 |
| Điện, nước | 16 địa điểm × 2 | ~32 |
| Phần mềm, mặt bằng, bảo trì, marketing | Phát sinh định kỳ & sự vụ | ~30 |
| **Tổng** | | **~550** |

## 3. Bài toán thêm gì cho từng agent

| Agent | Tình huống mới |
|---|---|
| `procurement`, `accounts-payable` | Hàng giao về bếp trung tâm hay giao thẳng quán thì người xác nhận phiếu nhập khác nhau. Có giao thiếu. Cùng NCC nhưng giá khác nhau theo điểm giao |
| `branch-operations` | Điện nước của 16 điểm; bếp trung tâm có mức nền riêng. So với doanh thu MoMo của từng quán |
| `fraud-control` | Nhiều NCC, có NCC mới mỗi tháng: đổi TK, NCC giả, cảnh báo chéo, escrow (D7) xảy ra thường xuyên |
| `treasury` | Chi 50–80 triệu/ngày **vượt trần tự chi 50 triệu/ngày (D9)**: phần dư phải đi duyệt hàng loạt (`bulk`) hoặc duyệt từng hóa đơn (`single`) |
| Chủ chuỗi | ~550 hóa đơn/tháng (~18/ngày) không thể duyệt từng cái: mandate tự chi + duyệt hàng loạt cuối ngày + chỉ đọc kỹ 3–5 hóa đơn vàng/đỏ mỗi ngày |

## 4. Quyết định đã chốt

- **Chốt persona 15 quán + 1 bếp trung tâm** (~45 NCC, ~550 HĐ/tháng, ≤ 100 lao động có BHXH) cho toàn bộ thiết kế và dữ liệu `sim-world` ([sim-world-dataset.md](sim-world-dataset.md)).
- **Giữ nguyên trần tự chi nền tảng D9** (30 triệu/HĐ, 50 triệu/ngày); phần chi 50–80 triệu/ngày vượt trần đi qua duyệt hàng loạt hoặc duyệt từng hóa đơn.
- **Kịch bản BRD §14** (cà phê 26,5 triệu tự chi, sữa 31 triệu, cốc nhựa 22,4 triệu, si-rô NCC mới, phần mềm 12 triệu, tiền nước quán 3 4,2 triệu, Bẫy cuối) giữ nguyên hoàn toàn trong ngữ cảnh chuỗi 16 điểm. Khi demo trực tiếp có thể chiếu lát cắt ngắn (ví dụ cụm quán + bếp trung tâm trong 1 tuần) để chạy gọn.
