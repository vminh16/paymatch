# Nguồn số liệu thật

Trạng thái: **Đang thu thập (26/11/2026)**.

## 1. Quy tắc thu thập

- **Lấy số, không chép bài.** Chỉ lấy tên hàng, quy cách, đơn vị, giá, ngày. Không chép nguyên văn bài báo hay mô tả sản phẩm.
- **Crawl lịch sự**: đọc robots.txt và điều khoản trước; một lần chụp (snapshot), tốc độ thấp; ghi URL và ngày lấy cho từng dòng.
- **Không đưa công ty thật vào kịch bản gian lận.** Tên và MST trong sim-world là giả. MST giả đúng định dạng 10 chữ số nhưng dùng một tiền tố riêng để không trùng doanh nghiệp thật (chốt tiền tố khi viết bộ sinh).
- **Không dữ liệu cá nhân.** Chứng từ thật của team phải xóa tên, MST, địa chỉ, SĐT, số TK, mã khách hàng trước khi commit.
- Bản gốc mẫu thật lưu ở `references/` và không sửa. Số liệu đã chuẩn hóa lưu ở `services/sim-world/data/` (JSON/CSV), mỗi dòng có `source_url`, `retrieved_on`.

## 2. Biểu giá điện

**Văn bản:** QĐ 2892/QĐ-BCT của Bộ Công Thương, áp dụng từ **1/11/2026**. Khung giờ theo QĐ 963/QĐ-BCT ngày 22/4/2026. Giá chưa gồm VAT.

**Nguồn đã đọc:** [Báo SGGP, 05/11/2026](https://www.sggp.org.vn/chi-tiet-gia-ban-le-dien-ap-dung-tu-ngay-1-11-2026-post880092.html). Chưa đối chiếu với văn bản QĐ 2892.

Giá điện cho **"các hoạt động kinh doanh khác"** (nhóm của quán F&B và bếp trung tâm), đồng/kWh:

| Cấp điện áp | Bình thường | Thấp điểm | Cao điểm |
|---|---|---|---|
| Trung áp, trên 1 kV | 2.829 | 1.577 | 4.924 |
| **Hạ áp, đến 1 kV** (quán) | **3.089** | **1.880** | **5.313** |

Khung giờ:
- **Cao điểm:** 17:30–22:30, thứ Hai đến thứ Bảy. Chủ nhật không có cao điểm.
- **Thấp điểm:** 0:00–6:00 mọi ngày.
- **Bình thường:** các giờ còn lại.

Dùng cho: `utility_bills`, `utility_baseline`. Quán mở 7:00–22:00 thì phần lớn điện năng rơi vào giờ bình thường và cao điểm; bộ sinh chia kWh theo giờ mở cửa.

**Hóa đơn tiền điện thật:** chưa có. Cần một hóa đơn EVN của một điểm kinh doanh (xóa mã khách hàng) để lấy bố cục và các dòng (chỉ số cũ/mới, kWh theo khung giờ, thuế).

## 3. Giá hàng hóa

| Nguồn | Dùng cho | Trạng thái |
|---|---|---|
| Trang sản phẩm Bách Hóa Xanh, Kingfoodmart, Co.op Online | Giá bán lẻ: sữa đặc, sữa tươi, đường, cà phê hạt, trà, bột, ly, nắp, ống hút, rau thịt | **Không kết nối được** từ môi trường này (kể cả robots.txt). Team mở bằng trình duyệt thường, ghi tay ~40 mặt hàng vào CSV mẫu |
| MM Mega Market (MM Pro, kênh B2B) | Giá sỉ HoReCa | [Không công khai giá](https://baodautu.vn/mm-mega-market-chinh-phuc-dai-duong-xanh-cua-thi-truong-bang-mo-hinh-ban-buon-da-kenh-d222223.html), cần tài khoản doanh nghiệp. Bỏ qua |
| Báo giá thật của một NCC bao bì / nguyên liệu pha chế | Hình dạng hợp đồng NCC: quy cách, đơn giá theo thùng, điều khoản thanh toán | Chưa có. Nếu team xin được một báo giá thật (xóa tên) thì dùng làm mẫu cho `vendor_contracts` |

Giá sỉ suy từ giá lẻ: **giá lẻ × 0,80–0,90**. Đây là giả định, chưa có nguồn; ghi rõ trong dữ liệu.

CSV mẫu cho ghi tay:

```csv
category,product_name,pack_spec,unit,price_vnd,source_url,retrieved_on
```

## 4. Tin nhắn và email lừa đảo

- Nguồn: bài cảnh báo công khai của công an, ngân hàng, ví điện tử về giả mạo nhà cung cấp, đổi số tài khoản, giả hóa đơn.
- Cách dùng: rút ra **mẫu thủ đoạn** (ai giả ai, lý do đổi TK, mức khẩn cấp, kênh), rồi viết lại thành template. Không chép tin thật.
- Tham khảo văn phong: [bộ 6.599 tin spam SMS tiếng Việt](https://arxiv.org/pdf/1705.04003) (Viettel, Vinaphone).
- Trạng thái: chưa thu thập.

## 5. Không dùng ở v1

- [MC-OCR 2021](https://github.com/manhph2211/MC-OCR/blob/main/README.md) (2.436 ảnh hóa đơn bán lẻ) và [Viet-Receipt-VQA](https://huggingface.co/datasets/5CD-AI/Viet-Receipt-VQA/blob/main/README.md): chỉ cần khi làm đọc ảnh/PDF (lộ trình).

## 6. Còn thiếu, cần team

| Việc | Ai | Ghi chú |
|---|---|---|
| 2–3 file XML hóa đơn đầu vào thật | team | Xem [einvoice-xml.md §5](einvoice-xml.md#5-file-thật-còn-thiếu) |
| 1 hóa đơn tiền điện, 1 hóa đơn tiền nước của điểm kinh doanh | team | Xóa mã khách hàng |
| Giá nước kinh doanh TP.HCM hiện hành | team | Chưa tìm thấy biểu giá SAWACO 2026 |
| ~40 giá mặt hàng ghi tay | team | CSV mẫu ở §3 |
| Đối chiếu bảng giá điện với văn bản QĐ 2892 | team | Hiện chỉ có số từ báo |
