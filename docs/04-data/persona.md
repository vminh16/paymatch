# Doanh nghiệp giả lập (persona)

Trạng thái: **Đề xuất, chưa chốt (26/11/2026)**. Khi chốt phải sửa theo: persona trong BRD và [problem-definition.md](../01-requirements/problem-definition.md), mandate mẫu trong [payment-gate.md](../02-architecture/payment-gate.md), con số của bộ eval.

## 1. Vì sao mở rộng

Chuỗi 5 quán cà phê có quá ít hóa đơn và quá ít NCC: chủ quán tự xem hết được, nên một đội agent không có lý do tồn tại. Cần một SME đủ lớn để duyệt tay từng hóa đơn không còn khả thi, nhưng vẫn là doanh nghiệp nhỏ dùng MoMo Doanh Nghiệp.

## 2. Đề xuất

| | |
|---|---|
| Loại hình | Chuỗi F&B: 15 quán cà phê, trà, đồ ăn nhẹ ở TP.HCM + 1 bếp trung tâm (sơ chế, nấu sốt, làm bánh) |
| Quy mô pháp lý | DN nhỏ/vừa theo [NĐ 80/2021](https://luatvietnam.vn/doanh-nghiep/nghi-dinh-80-2021-nd-cp-208340-d1.html) (chưa kiểm ngưỡng doanh thu) |
| Người dùng | 1 chủ chuỗi (duy nhất được duyệt, D4), 2 kế toán, 15 quản lý quán, 1 quản lý bếp trung tâm |
| Nhà cung cấp | ~45, mỗi tháng thêm 2–3 NCC mới |
| Hóa đơn đầu vào | **~550/tháng** (ước tính, xem dưới) |
| Chi tiêu | ~1,5–2,5 tỷ/tháng, tức 50–80 triệu/ngày |

**Ước tính hóa đơn mỗi tháng** (không có nguồn công khai cho con số này; là giả định):

| Nguồn | Cách tính | Số hóa đơn |
|---|---|---|
| Bếp trung tâm: thịt, rau tươi | 10 NCC × 3 lần/tuần | ~130 |
| Hàng khô, bao bì | 15 NCC × hằng tuần | ~60 |
| Giao thẳng tới quán: sữa, đá, bánh mì | 15 quán × 2 NCC × ~10 lần | ~300 |
| Điện, nước | 16 địa điểm × 2 | ~32 |
| Phần mềm, mặt bằng, bảo trì, marketing | | ~30 |
| **Tổng** | | **~550** |

## 3. Bài toán thêm gì cho từng agent

| Agent | Tình huống mới |
|---|---|
| procurement, accounts-payable | Hàng giao về bếp trung tâm hay giao thẳng quán thì người xác nhận phiếu nhập khác nhau. Có giao thiếu. Cùng NCC nhưng giá khác nhau theo điểm giao |
| branch-operations | Điện nước của 16 điểm; bếp trung tâm có mức nền riêng. So với doanh thu MoMo của từng quán |
| fraud-control | Nhiều NCC, có NCC mới mỗi tháng: đổi TK, NCC giả, cảnh báo chéo, escrow (D7) xảy ra thường xuyên |
| treasury | Chi 50–80 triệu/ngày **vượt trần tự chi 50 triệu/ngày (D9)**: phần dư phải đi duyệt hàng loạt |
| chủ chuỗi | 550 hóa đơn/tháng thì không duyệt từng cái được: mandate + bulk + chỉ xem đỏ/vàng |

## 4. Cần chốt

- Có lấy persona này không.
- Giữ trần tự chi 30 triệu/HĐ, 50 triệu/ngày (D9), hay đổi theo quy mô mới.
- Kịch bản BRD §14 (cà phê 26,5 triệu tự chi) vẫn dùng được với trần hiện tại.
