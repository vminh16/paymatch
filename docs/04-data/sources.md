# Nguồn số liệu thật

Trạng thái: **Đã thu thập và xác minh các nguồn chính (26/11/2026); còn một số mẫu XML chuyên biệt và báo giá B2B cần bổ sung.**

## 1. Quy tắc thu thập

- **Lấy số, không chép bài.** Chỉ lấy tên hàng, quy cách, đơn vị, giá, ngày. Không chép nguyên văn bài báo hay mô tả sản phẩm.
- **Crawl lịch sự:** đọc `robots.txt` và điều khoản trước; một lần chụp (snapshot), tốc độ thấp; ghi `source_url` và `retrieved_on` cho từng dòng.
- **Không đưa công ty thật vào kịch bản gian lận.** Tên công ty, thương hiệu trong dữ liệu sinh, số tài khoản và MST trong `sim-world` đều là giả. Tiền tố MST giả đã chốt là **`0999XXXXXX`** (xem [sim-world-dataset.md](sim-world-dataset.md)).
- **Không dữ liệu cá nhân.** Chứng từ thật phải xóa tên, MST, địa chỉ, SĐT, số TK, mã khách hàng trước khi commit.
- Bản gốc mẫu thật lưu ở `references/` (và `research/claude/einvoice-samples/`) không sửa. Bộ dữ liệu đã sinh cho demo lưu ở `services/sim-world/data/` theo đặc tả [sim-world-dataset.md](sim-world-dataset.md).

## 2. Biểu giá điện và bố cục hóa đơn EVN

**Trạng thái:** ✅ **Đã xác minh** trực tiếp trên văn bản gốc ký số và khớp 3 nguồn độc lập (chi tiết tại [research/utilities-and-persona.md §1](research/utilities-and-persona.md#1-điện-kinh-doanh-evn--evnhcmc) và [research/claude/report.md §2](research/claude/report.md#2-điện)).

- **Văn bản gốc:**
  - **QĐ 2892/QĐ-BCT** ngày **31/10/2026** của Bộ Công Thương, hiệu lực từ **01/11/2026** (bản PDF ký số trên [evn.com.vn](https://www.evn.com.vn/userfile/User/tcdl/files/2026/11/1_QD-BCT_2026_2892-20261104131123509.pdf) và [vpubnd.daklak.gov.vn](https://vpubnd.daklak.gov.vn/CMS/Content/VanBan/2026/11.2026/2892-Q%C4%90-BCT.pdf)).
  - **QĐ 1305/QĐ-EVN** ngày **30/10/2026** của EVN (giá bán lẻ điện bình quân `2.159,9037` đ/kWh chưa VAT, giảm 2%).
  - **QĐ 963/QĐ-BCT** ngày **22/04/2026** của Bộ Công Thương về khung giờ ([PDF ký số trên evn.com.vn](https://www.evn.com.vn/userfile/User/minhhanh/files/2026/4/1_QD-BCT_2026_963_30f7a-20260423202657276.pdf)) và **TT 60/2025/TT-BCT** ngày 02/12/2025 (khoản 3 Điều 5 về ngưỡng bắt buộc công tơ 3 giá).
  - Đối chiếu chéo 3 nguồn độc lập: [Tạp chí Công Thương](https://tapchicongthuong.vn/gia-ban-le-dien-binh-quan-giam-2--tu-ngay-1-11-2026-562569.htm), [Báo SGGP (05/11/2026)](https://www.sggp.org.vn/chi-tiet-gia-ban-le-dien-ap-dung-tu-ngay-1-11-2026-post880092.html), [Người Quan Sát](https://nguoiquansat.vn/thong-tin-moi-nhat-ve-gia-ban-le-dien-sinh-hoat-theo-5-bac-326059.html).

Giá bán lẻ điện mục **3.3 — "Giá bán lẻ điện cho kinh doanh khác"** (nhóm áp dụng cho quán F&B và bếp trung tâm thương mại), đồng/kWh, **chưa gồm VAT**:

| Cấp điện áp | Bình thường | Thấp điểm | Cao điểm |
|---|---:|---:|---:|
| Trung áp trở lên (`> 01 kV`) | 2.829 | 1.577 | 4.924 |
| **Hạ áp (`≤ 01 kV`)** *(quán F&B)* | **3.089** | **1.880** | **5.313** |

- **Thuế suất VAT năm 2026:** **`8%`** (giảm 2% từ 10% theo NQ `204/2025/QH15` và NĐ `174/2025/NĐ-CP`, áp dụng đến hết `31/12/2026`).
- **Khung giờ (`QĐ 963/QĐ-BCT`):**
  - **Cao điểm (`peak`):** `17:30–22:30` thứ Hai đến thứ Bảy (**Chủ nhật không có cao điểm**).
  - **Thấp điểm (`off_peak`):** `00:00–06:00` mọi ngày.
  - **Bình thường (`normal`):** `06:00–17:30` và `22:30–24:00` thứ Hai đến thứ Bảy; `06:00–24:00` Chủ nhật.
- **Công tơ 3 giá vs 1 giá (`TT 60/2025/TT-BCT`):** khách hàng kinh doanh **bắt buộc** 3 giá khi dùng bình quân 3 tháng `≥ 2.000 kWh/tháng` hoặc trạm biến áp `≥ 25 kVA`; dưới ngưỡng dùng 1 giá (`3.089` đ/kWh) hoặc 3 giá nếu đã lắp công tơ điện tử TOU.
- **Bố cục hóa đơn EVNHCMC (từ mẫu công bố trên `tphcm.chinhphu.vn` & `evn.com.vn`):**
  - Gồm **2 tài liệu ký số đi kèm**: (1) **Mặt Hóa đơn GTGT** (không mã CQT, ký hiệu dạng `1K26Txx`, người bán là Chi nhánh Công ty Điện lực khu vực có MST đuôi `-NNN`) chỉ hiển thị **01 dòng gộp tổng kWh**, **`DGia` để trống (`null`)** khi nhiều khung giờ, có `SBKe`/`NBKe`, thuế suất `8%`; (2) **Bảng kê chi tiết** ghi `Mã khách hàng` 13 ký tự bắt đầu bằng `PE` (`PE` + 11 chữ số), tách riêng `Địa chỉ` trụ sở và `Địa chỉ sử dụng điện` (ánh xạ về `store_id`), cột `CHỈ SỐ MỚI` trước `CHỈ SỐ CŨ`, hệ số nhân và chi tiết 3 khung giờ.
  - EVNSPC/EVNHCMC hỗ trợ gom theo dõi hóa đơn nhiều điểm trên cùng tài khoản doanh nghiệp (VB `4901/EVN-KDMBĐ`).
  - *Còn thiếu:* chưa có file `.xml` sản xuất thật của EVNHCMC; kWh/tháng của quán cà phê (tham khảo thứ cấp ~`900–2.500 kWh/tháng` tùy diện tích; bếp trung tâm chưa có nguồn công khai).

## 2b. Biểu giá nước kinh doanh TP.HCM (SAWACO 2026) và bố cục hóa đơn nước

**Trạng thái:** ✅ **Đã xác minh biểu giá 2026** qua văn bản dấu đỏ **Thông báo số `3698/TB-CNBT-KDDVKH`** ngày `23/12/2025` của Công ty CP Cấp nước Bến Thành – SAWACO ([PDF chính thức](https://benthanh.sawaco.com.vn/images/th_ng_b_o_gi_n_c_n_m_2026.pdf)) và cổng CSKH SAWACO (chi tiết tại [research/utilities-and-persona.md §2](research/utilities-and-persona.md#2-nước-kinh-doanh-tại-tphcm-sawaco-và-công-ty-thành-viên) và [research/claude/report.md §3](research/claude/report.md#3-nước)).

- **Căn cứ & hiệu lực 2026:** giữ nguyên đơn giá năm 2025 cho cả giai đoạn `01/01/2026–31/12/2026` theo `QĐ 25/2019/QĐ-UBND`, `QĐ 728/QĐ-TCT-KDDVKH` (SAWACO), `QĐ 17/2021/QĐ-UBND` (lộ trình giá dịch vụ thoát nước đạt trần 30% từ 2025, thay cho phí BVMT 10%) và `NĐ 174/2025/NĐ-CP` (giảm VAT dịch vụ thoát nước từ 10% xuống 8% đến `31/12/2026`).

Bảng giá nhóm **Kinh doanh dịch vụ** (mọi quán F&B, không chia bậc thang; tham khảo thêm nhóm **Sản xuất** nếu bếp trung tâm đăng ký mã SX):

| Đối tượng | Nước sạch (đ/m³) | VAT nước sạch (`5%`) | DV thoát nước (`30%`) | VAT thoát nước (`8%`) | Tổng thanh toán tham khảo (đ/m³) |
|---|---:|---:|---:|---:|---:|
| **Kinh doanh dịch vụ** *(quán F&B)* | **21.300** | **1.065** | **6.390** | **511** *(chính xác `511,2`)* | **29.266** |
| Sản xuất *(tham khảo bếp trung tâm)* | 12.100 | 605 | 3.630 | 290 | 16.625 |

- **Lưu ý số học:** thuế GTGT tính trên **tổng thành tiền của từng dòng thuế suất** rồi làm tròn đến đồng: `TThue_5 = round(m3 × 21.300 × 0,05)`, `TThue_8 = round(m3 × 6.390 × 0,08)` (ví dụ `24 m³` → `702.389 đ`; ca rò ống `144 m³` → `4.214.333 đ`, khớp kịch bản BRD §14). Không nhân phẳng `m3 × 29.266`.
- **Bố cục hóa đơn nước SAWACO:**
  - Phát hành **01 Hóa đơn GTGT không mã (`1K26Txx`) duy nhất** cho mỗi kỳ, tách **02 dòng `HHDVu` với 2 thuế suất khác nhau** (`5%` cho tiền nước sạch, `8%` cho tiền dịch vụ thoát nước và xử lý nước thải) và 2 thẻ `LTSuat` tương ứng.
  - Định danh đồng hồ bằng **Số Danh Bộ 11 chữ số** (`customer_code`), kèm `Chỉ số cũ`, `Chỉ số mới`, `Tiêu thụ (m³)`, `Mã giá biểu` (`GB`).
  - **Nhiều đơn vị cấp nước trong cùng chuỗi:** tại TP.HCM mỗi khu vực quận/huyện thuộc một Công ty CP Cấp nước thành viên SAWACO độc lập (MST 10 số và tài khoản ngân hàng riêng: Bến Thành, Gia Định, Chợ Lớn, Phú Hòa Tân, Tân Hòa, Thủ Đức, Trung An, Nhà Bè). Chuỗi 16 điểm rải nhiều quận sẽ có nhiều NCC nước trong `vendor_registry` (sim-world dùng tên và MST giả nhưng giữ cấu trúc nhiều công ty cấp nước khu vực).
  - *Còn thiếu:* chưa có file `.xml` sản xuất thật của SAWACO; m³/tháng của quán cà phê chỉ có nguồn thứ cấp (~`15–35 m³/tháng` cho quán 50–100 m²).

## 3. Giá hàng hóa (nguyên liệu và bao bì)

**Trạng thái:** ✅ **Đã thu thập 144 dòng giá thật** từ các nguồn truy cập hợp lệ theo `robots.txt` trong 2 tệp CSV:
- [references/prices-2026-11.csv](references/prices-2026-11.csv): **95 dòng, 18 nhóm hàng** (`retail` 68, `wholesale` 14, `quote` 13) — xem phân tích tại [research/prices-and-scams.md §1](research/prices-and-scams.md#1-hạng-mục-1-giá-nguyên-liệu-và-bao-bì-chuỗi-cà-phê--trà-sữa-prices-2026-11csv).
- [research/claude/prices-2026-11.csv](research/claude/prices-2026-11.csv): **49 dòng, 14 nhóm hàng** (`retail` 37 Kingfoodmart, `wholesale` 12 MM online) — xem phân tích tại [research/claude/report.md §4](research/claude/report.md#4-giá-nguyên-liệu-và-bao-bì).

**Khả năng truy cập thực tế của các nguồn giá:**

| Nguồn | Dùng cho | Trạng thái (`26/11/2026`) |
|---|---|---|
| `kamereo.vn` (B2B HoReCa) | Giá sỉ B2B (hiển thị cả **chưa VAT** và sau VAT): sữa đặc thùng, chanh/nông sản | ✅ Truy cập hợp lệ (`Crawl-delay: 10`) |
| `vinbar.vn`, `dvpmarket.com` | Kho sỉ/lẻ nguyên liệu & bao bì pha chế TP.HCM (cà phê, sữa, trà, si-rô, trân châu, ly, nắp) | ✅ Truy cập hợp lệ |
| `kingfoodmart.com` | Giá bán lẻ + biến thể thùng/lốc qua JSON nhúng `__NEXT_DATA__` | ✅ Truy cập hợp lệ |
| `online.mmvietnam.com` (MM Mega Market online) | Giá kênh sỉ/HoReCa qua GraphQL công khai (`regular_price` là **giá chưa VAT 8%**) | ✅ Truy cập hợp lệ |
| `cooponline.vn`, `coffeetree.vn` | Giá siêu thị (lẻ & thùng) và cà phê hạt rang mộc | ✅ Truy cập hợp lệ (`cooponline.vn` có thể timeout từ một số môi trường) |
| `innhanhmientrung.com`, `queenpack.com.vn` | Bảng báo giá sỉ (`quote`) ly nhựa PP/PET thùng 1.000 cái, nắp, hộp giấy kraft | ✅ Truy cập hợp lệ |
| `bachhoaxanh.com` | Siêu thị bán lẻ | ❌ `403 Forbidden` / `robots.txt` chặn `/sp/*` — bỏ qua |
| `mmpro.vn`, `nuocdahongphuc.com` | Kênh B2B cần đăng nhập / đá viên bao 20kg để "Liên hệ" | 🟡 Ẩn giá (đá 20kg chỉ có khoảng tham khảo thị trường `25.000–35.000 đ/bao 20kg`) |
| Báo giá hợp đồng công nợ B2B thật của NCC | Hình dạng hợp đồng khung (công nợ 15–30 ngày, chiết khấu cuối kỳ) | ❌ Chưa có; dùng quy cách thật từ 2 CSV trên để dựng `vendor_contracts` |

**Tỷ lệ giá sỉ so với giá lẻ (thay thế giả định cũ `0,80–0,90` bằng số đo thực theo nhóm hàng):**

| Nhóm hàng | Tỷ lệ giá thùng / B2B so với giá lẻ | Bằng chứng đo ngày `26/11/2026` |
|---|---|---|
| **FMCG thương hiệu mạnh** (sữa đặc, sữa tươi, đường đóng gói) | **`0,91–0,99×` giá lẻ** (chênh chỉ 0,5%–9%) | Sữa tươi thùng giảm 5–7% (`Vinbar`, `Kingfoodmart`); sữa đặc thùng giảm 0,5%–1,4%; sữa đặc thùng `Kamereo` sau VAT gần ngang giá lẻ siêu thị |
| **Nguyên liệu pha chế & bao bì theo bao/thùng lớn** (bột béo 25kg, matcha 500g, ly nhựa thùng 1.000 cái) | **`0,70–0,90×` giá lẻ chia nhỏ** | Bột béo bao 25kg `0,895×`; matcha gói 500g `0,692×`; ly PP 700ml thùng 1.000 cái `0,828×` |
| **Cà phê hạt rang mộc xưởng sỉ** | Xưởng sỉ Robusta `95.000–165.000 đ/kg` vs đóng gói lẻ `280.000–309.000 đ/kg` | Khảo sát thị trường sỉ vs bảng giá `Coffee Tree`/`Vinbar` |

*Lưu ý quy đổi VAT khi sinh XML:* Giá `retail` siêu thị đã gồm VAT (`8%` hoặc `10%`), còn giá `kamereo.vn` và `regular_price` trên `online.mmvietnam.com` là **chưa VAT**. Trường `HHDVu/DGia` trên XML luôn là đơn giá **chưa VAT** (`round(price_vnd / (1 + vat_rate))` với dòng đã gồm VAT).

**Mẫu CSV chuẩn** (đã bổ sung cột `price_kind`: `retail | wholesale | quote`):

```csv
category,product_name,pack_spec,unit,price_vnd,price_kind,source_url,retrieved_on
```

## 4. Tin nhắn và email lừa đảo

**Trạng thái:** ✅ **Đã thu thập** (26/11/2026) từ hơn 20 cảnh báo công khai của Bộ Công an, Công an địa phương (Hà Nội, Hải Phòng, Quảng Ninh, Ninh Bình, Phú Thọ, Thái Nguyên, Lâm Đồng), NHNN / Thời báo Ngân hàng, ngân hàng thương mại (Vietcombank/SIMO, Agribank, Techcombank, VPBank), MoMo, ZaloPay và Cục Thuế.

- [research/prices-and-scams.md §2](research/prices-and-scams.md#2-hạng-mục-2-thủ-đoạn-lừa-đảo-thanh-toán-nhà-cung-cấp--câu-lệnh-giấu-ttkhac): 8 mẫu thủ đoạn có cấu trúc (`P01`–`P08`: BEC đổi TK, chiếm Zalo sale NCC, bẫy đặt cọc NCC mới vào TK cá nhân, công ty "ma" xuất HĐ khống, giả danh thuế/HĐĐT, giả CEO/Deepfake, giả thu hộ điện nước gửi QR, biên lai chuyển nhầm giả), template hư cấu và **12 mẫu prompt injection hư cấu (`PI_01`–`PI_12`)**.
- [research/claude/report.md §5](research/claude/report.md#5-thủ-đoạn-lừa-đảo-nhắm-vào-thanh-toán-ncc): 8 mẫu thủ đoạn (`P1`–`P8`), 5 template (`T1`–`T5`) và **10 mẫu prompt injection hư cấu (`I1`–`I10`)** (gồm ký tự zero-width, Base64, thoát thẻ XML, tràn 500 ký tự, dụ link OTP).
- Tổng cộng **22 mẫu prompt injection hư cấu** đưa vào danh mục kịch bản tại [sim-world-dataset.md](sim-world-dataset.md). Không sao chép nguyên văn tin nhắn thật; toàn bộ tên, MST và STK trong template đều giả lập.

## 5. Không dùng ở v1

- [MC-OCR 2021](https://github.com/manhph2211/MC-OCR/blob/main/README.md) (2.436 ảnh hóa đơn bán lẻ) và [Viet-Receipt-VQA](https://huggingface.co/datasets/5CD-AI/Viet-Receipt-VQA/blob/main/README.md): chỉ cần khi làm đọc ảnh/PDF (lộ trình).

## 6. Còn thiếu, cần team bổ sung (khi có điều kiện)

| Việc | Ghi chú |
|---|---|
| 1 file XML hóa đơn đầu vào F&B thật, 1 file `PBan 2.1.1`/XAdES, 1 file có `TTCKTMai`/`DSLPhi` ≠ 0 | Đã có 10 file XML thật chung ở `research/claude/einvoice-samples/`; xem [einvoice-xml.md §5](einvoice-xml.md#5-mẫu-thật-hiện-có-và-khoảng-trống-còn-thiếu) |
| 1 file XML thật của EVNHCMC (điện) và 1 file XML thật của SAWACO (nước) | Biểu giá 2026 và bố cục bản thể hiện PDF/bảng kê đã xác minh; file XML giúp chốt tên `TTruong` chứa mã KH / danh bộ |
| 1 báo giá hợp đồng công nợ B2B thật (đã xóa tên) và đơn giá cố định đá viên bao 20kg / cốt bánh tươi giao sỉ | Đã có 144 dòng giá thật từ 2 CSV; đá 20kg mới có khoảng giá tham khảo `25.000–35.000 đ/bao` |
| Tên cột gốc trong file Excel danh sách DN rủi ro từ `tracuuhoadon.gdt.gov.vn/dnrrvp.html` | Cổng bị lỗi chuỗi CA trung gian trên container; mở trình duyệt lấy tên cột mẫu (không cần lưu MST thật) |
