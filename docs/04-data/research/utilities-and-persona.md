# Nghiên cứu dữ liệu: Điện, Nước (TP.HCM) và Quy mô Persona F&B

Ngày thu thập (`retrieved_on`): **2026-11-26**  
Phạm vi: Nhiệm vụ B — đối chiếu biểu giá điện kinh doanh & bố cục hóa đơn EVNHCMC, biểu giá nước kinh doanh SAWACO 2026 & bố cục hóa đơn nước, định cỡ persona chuỗi F&B nhỏ theo NĐ 80/2021/NĐ-CP, và thiết kế hình dạng dòng dữ liệu cho `utility_bills` / `utility_readings`.

---

## Tóm tắt trạng thái từng hạng mục

| Hạng mục | Trạng thái | Độ tin cậy | Tóm tắt ngắn |
|---|---|---|---|
| **1a. Biểu giá điện kinh doanh (`QĐ 2892/QĐ-BCT`) & khung giờ (`QĐ 963/QĐ-BCT`)** | ✅ Đã xác minh | **Cao** (văn bản gốc ký số của Bộ Công Thương & cổng EVN) | Khớp 100% các con số trong `sources.md §2` (`3.089 / 1.880 / 5.313` đ/kWh hạ áp ≤ 1 kV; `2.829 / 1.577 / 4.924` đ/kWh trung áp > 1 kV; chưa gồm VAT). Xác minh thêm ngưỡng bắt buộc công tơ 3 giá (`≥ 2.000 kWh/tháng` hoặc TBA `≥ 25 kVA` theo `TT 60/2025/TT-BCT`) và thuế suất VAT điện **8%** năm 2026 (`NĐ 174/2025/NĐ-CP`). |
| **1b. Bố cục hóa đơn tiền điện kinh doanh EVNHCMC & kWh điển hình quán cà phê** | 🟡 Xác minh một phần | **Cao** cho bố cục bản thể hiện PDF/bảng kê (mẫu công bố trên `chinhphu.vn` & `evn.com.vn`); **Thấp–Trung bình** cho kWh quán cà phê (nguồn thứ cấp); **Chưa có** file `.xml` thật của EVNHCMC | Hóa đơn EVNHCMC gồm **2 phần ký số**: mặt Hóa đơn GTGT chỉ ghi **1 dòng tổng kWh**, cột `DGia` để trống (`-`) khi nhiều khung giờ, tham chiếu `SBKe`; chi tiết công tơ, hệ số nhân, `CHỈ SỐ MỚI`, `CHỈ SỐ CŨ`, kWh theo BT/CD/TD nằm ở **Bảng kê chi tiết**. Quán cà phê nhỏ có máy lạnh ước tính ~`900–1.300 kWh/tháng` (nguồn thứ cấp). |
| **2a. Giá nước kinh doanh TP.HCM năm 2026 (SAWACO & công ty thành viên)** | ✅ Đã xác minh | **Cao** (thông báo dấu đỏ `3698/TB-CNBT-KDDVKH` của Cấp nước Bến Thành – SAWACO & các QĐ của UBND TP.HCM) | Nhóm **Kinh doanh dịch vụ** áp dụng từ `01/01/2026–31/12/2026`: nước sạch **`21.300` đ/m³** (`QĐ 25/2019/QĐ-UBND`, `QĐ 728/QĐ-TCT-KDDVKH`) + VAT **5%** (`1.065` đ) + giá dịch vụ thoát nước **30%** = **`6.390` đ/m³** (`QĐ 17/2021/QĐ-UBND`, thay cho phí BVMT 10%) + VAT DVTN **8%** (`511,2` → hiển thị `511` đ theo `NĐ 174/2025/NĐ-CP`) = **`29.266` đ/m³**. |
| **2b. Bố cục hóa đơn tiền nước SAWACO & m³ điển hình quán cà phê** | 🟡 Xác minh một phần | **Trung bình–Cao** cho cấu trúc chỉ tiêu cổng HĐĐT SAWACO; **Thấp–Trung bình** cho m³ quán cà phê (nguồn thứ cấp); **Chưa có** file `.xml` thật | Phát hành **01 Hóa đơn GTGT duy nhất** bởi Công ty CP Cấp nước khu vực (không phải công ty mẹ SAWACO), tách **2 dòng thuế suất khác nhau** (`5%` cho nước sạch và `8%` cho dịch vụ thoát nước), định danh bằng `Số Danh Bộ` 11 chữ số. Quán cà phê nhỏ–vừa dùng ~`15–35 m³/tháng` (`24 m³ ≈ 702.389 đ`, khớp sát kịch bản ~700 nghìn và rò ống gấp 6 lần = `144 m³ ≈ 4,21 triệu đ` trong BRD §14). |
| **3. Ngưỡng DNNVV (`NĐ 80/2021/NĐ-CP`) & Định cỡ Persona chuỗi F&B** | 🟡 Xác minh một phần | **Cao** cho ngưỡng pháp lý (`NĐ 80/2021/NĐ-CP`), khảo sát ngành (`iPOS/VIRAC`, `MoMo [M3]`); **Thấp** cho số NCC & số HĐ/tháng (không có thống kê công khai, chỉ suy từ mô hình vận hành) | Thương mại – dịch vụ theo Điều 5 `NĐ 80/2021`: Siêu nhỏ (`≤ 10` LĐ BHXH & doanh thu `≤ 10 tỷ` hoặc vốn `≤ 3 tỷ`); Nhỏ (`≤ 50` LĐ BHXH & doanh thu `≤ 100 tỷ` hoặc vốn `≤ 50 tỷ`); Vừa (`≤ 100` LĐ BHXH & doanh thu `≤ 300 tỷ` hoặc vốn `≤ 100 tỷ`). **Khuyến nghị:** giữ **chuỗi 5 quán** (nâng doanh thu lên **12–15 tỷ/năm** để chắc chắn thuộc **DN nhỏ**, ~20–25 NCC, ~200 HĐ/tháng, chi ~350–450 triệu/tháng) thay vì 15 quán + bếp trung tâm cho bản v1 (03/12/2026). |

---

## 1. Điện kinh doanh (EVN / EVNHCMC)

### 1.1. Kết quả nghiên cứu (`findings`)

#### a) Đối chiếu văn bản gốc `QĐ 2892/QĐ-BCT` và `QĐ 963/QĐ-BCT`

1. **Văn bản biểu giá bán lẻ điện hiện hành:**
   - **Quyết định số `2892/QĐ-BCT`** ngày **31/10/2026** của Bộ trưởng Bộ Công Thương (Thứ trưởng Trương Thanh Hoài ký số ngày `31/10/2026 16:50:05`), có hiệu lực áp dụng từ ngày **01/11/2026** (Điều 3).
   - Mức giá bán lẻ điện bình quân (Điều 2): **`2.159,9037` đồng/kWh** (chưa bao gồm thuế GTGT), giảm 2% so với mức liền trước.
   - Cơ cấu nhóm khách hàng bám theo **Quyết định số `14/2025/QĐ-TTg`** ngày 29/05/2025 của Thủ tướng Chính phủ (thay thế QĐ 28/2014/QĐ-TTg) và **Thông tư số `60/2025/TT-BCT`** ngày 02/12/2025 của Bộ Công Thương. Trong đó, mục **3. Giá bán lẻ điện cho kinh doanh** tại Phụ lục (trang 3–4 bản ký số) tách thành 3 phân nhóm, mỗi phân nhóm chỉ còn **2 cấp điện áp** (`từ trung áp trở lên (trên 01 kV)` và `hạ áp đến 01 kV` — không còn tách `> 22 kV` và `6–22 kV` như cơ cấu cũ):

| Mục trong Phụ lục `QĐ 2892/QĐ-BCT` | Cấp điện áp | Giờ bình thường (đ/kWh) | Giờ thấp điểm (đ/kWh) | Giờ cao điểm (đ/kWh) | Đối chiếu `sources.md §2` |
|---|---|---:|---:|---:|---|
| **3.1. Cơ sở lưu trú du lịch** | Trung áp trở lên (`> 01 kV`) | 1.814 | 1.166 | 3.348 | Chưa liệt kê (không áp cho F&B) |
| **3.1. Cơ sở lưu trú du lịch** | Hạ áp (`≤ 01 kV`) | 1.966 | 1.274 | 3.586 | Chưa liệt kê (không áp cho F&B) |
| **3.2. Sạc xe điện** | Trung áp trở lên (`> 01 kV`) | 2.549 | 1.534 | 3.758 | Chưa liệt kê (không áp cho F&B) |
| **3.2. Sạc xe điện** | Hạ áp (`≤ 01 kV`) | 2.700 | 1.620 | 4.212 | Chưa liệt kê (không áp cho F&B) |
| **3.3. Kinh doanh khác** *(nhóm của quán F&B, văn phòng, bếp trung tâm thương mại)* | **Trung áp trở lên (`> 01 kV`)** | **2.829** | **1.577** | **4.924** | ✅ **Khớp chính xác 100%** |
| **3.3. Kinh doanh khác** *(quán F&B đấu nối trực tiếp lưới hạ áp 220V/380V)* | **Hạ áp (`≤ 01 kV`)** | **3.089** | **1.880** | **5.313** | ✅ **Khớp chính xác 100%** |

   - *Lưu ý nhỏ về tên gọi:* Văn bản gốc ghi mục 3.3 là **"Giá bán lẻ điện cho kinh doanh khác"** (`sources.md §2` đang ghi `"các hoạt động kinh doanh khác"` — ý nghĩa tương đương nhưng nên sửa theo đúng câu chữ Phụ lục QĐ 2892). Ngoài ra, mục **7.2** của Phụ lục quy định giá bán buôn điện cho đơn vị bán lẻ điện tại **tổ hợp thương mại – dịch vụ – sinh hoạt** (`2.929 / 1.782 / 5.037` đ/kWh); nếu một chi nhánh F&B thuê mặt bằng trong trung tâm thương mại và mua điện lại qua ban quản lý tòa nhà (đơn vị bán lẻ điện có giấy phép) thay vì ký hợp đồng trực tiếp với EVNHCMC, người bán trên hóa đơn sẽ là công ty quản lý tòa nhà nhưng trần giá bán lẻ cho khách thuê kinh doanh vẫn theo mục 3.3.2.

2. **Khung giờ sử dụng điện trong ngày (`QĐ 963/QĐ-BCT`):**
   - Đối chiếu trực tiếp bản ký số **Quyết định số `963/QĐ-BCT`** ngày **22/04/2026** của Bộ trưởng Bộ Công Thương (Thứ trưởng Nguyễn Hoàng Long ký, hiệu lực từ ngày `22/04/2026`, Điều 1 & Điều 3):
     - **Giờ cao điểm (`peak`):** Thứ Hai đến Thứ Bảy từ **`17h30` đến `22h30`** (`05 giờ/ngày`). **Chủ nhật: không có giờ cao điểm.** → Khớp 100% với `sources.md §2`.
     - **Giờ bình thường (`normal`):** Thứ Hai đến Thứ Bảy từ **`06h00` đến `17h30`** và từ **`22h30` đến `24h00`** (`13 giờ/ngày`); Chủ nhật từ **`06h00` đến `24h00`** (`18 giờ/ngày`).
     - **Giờ thấp điểm (`off_peak`):** Tất cả các ngày trong tuần (Thứ Hai đến Chủ nhật) từ **`00h00` đến `06h00`** (`06 giờ/ngày`). → Khớp 100% với `sources.md §2`.

3. **Khi nào quán áp dụng 3 khung giờ (TOU) vs 1 giá (`Thông tư 60/2025/TT-BCT`):**
   - Theo **khoản 3 Điều 5 Thông tư số `60/2025/TT-BCT`** ngày 02/12/2025 của Bộ Công Thương (được EVN trích dẫn chính thức kèm QĐ 963/QĐ-BCT): khách hàng mua điện mục đích sản xuất, kinh doanh **bắt buộc** áp dụng giá 3 khung giờ khi được cấp điện qua máy biến áp chuyên dùng **`≥ 25 kVA`** **hoặc** có sản lượng điện sử dụng trung bình 3 tháng liên tục **`≥ 2.000 kWh/tháng`**.
   - Hệ quả cho `sim-world`:
     - Quán nhỏ (`< 2.000 kWh/tháng`) nếu dùng **công tơ 1 giá** (chưa đăng ký 3 giá) sẽ tính toàn bộ kWh theo **1 dòng đơn giá giờ bình thường = `3.089` đ/kWh**.
     - Quán lớn / bếp trung tâm (`≥ 2.000 kWh/tháng`) hoặc quán ở TP.HCM đã lắp công tơ điện tử đo xa đa biểu giá theo hợp đồng kinh doanh sẽ tính theo **3 khung giờ** (`3.089 / 5.313 / 1.880` đ/kWh). Bộ sinh `sim-world` nên hỗ trợ cả hai trường hợp (hoặc thống nhất công tơ điện tử 3 giá cho các quán tại TP.HCM, vì EVNHCMC đã phủ công tơ điện tử đo xa).

4. **Thuế suất GTGT (VAT) tiền điện năm 2026:**
   - Theo **Nghị quyết số `204/2025/QH15`** ngày 17/06/2025 của Quốc hội và **Nghị định số `174/2025/NĐ-CP`** ngày 30/06/2025 của Chính phủ, mức giảm 2% thuế GTGT (từ `10%` xuống **`8%`**) áp dụng liên tục từ `01/07/2025` đến hết ngày **`31/12/2026`**. Điện thương phẩm không thuộc danh mục hàng hóa dịch vụ bị loại trừ, nên mọi hóa đơn tiền điện phát hành trong tháng 11–12/2026 áp dụng `TSuat = "8%"`.

#### b) Bố cục và dòng hàng trên Hóa đơn điện tử tiền điện kinh doanh của EVNHCMC

Đối chiếu trực tiếp ảnh chụp **Mẫu Hóa đơn GTGT điện tử ngoài mục đích sinh hoạt** và **Mẫu Bảng kê chi tiết hóa đơn tiền điện ngoài sinh hoạt** của EVNHCMC do Báo Điện tử Chính phủ TP.HCM (`tphcm.chinhphu.vn`) và Tập đoàn Điện lực Việt Nam (`evn.com.vn`) công bố khi chuyển sang chuẩn NĐ 123/2020 & TT 78/2021, kết hợp đối chiếu cây thẻ XML trong `QĐ 1271/QĐ-CT`:

1. **Cấu trúc 2 tài liệu điện tử ký số đi kèm nhau:**
   - **Phần 1 — Hóa đơn giá trị gia tăng (`VAT INVOICE`):**
     - **Người bán (`NBan`):** Không phải công ty mẹ EVNHCMC đứng tên trực tiếp mà là **Chi nhánh Tổng công ty Điện lực TP.HCM TNHH – Công ty Điện lực khu vực** (ví dụ: *Chi nhánh Tổng công ty Điện lực TP.HCM TNHH - Công ty Điện lực Sài Gòn*, MST chi nhánh 13 chữ số `0300951119-001`; MST trụ sở chính EVNHCMC là `0300951119`).
     - **Tổ chức cung cấp giải pháp HĐĐT (`MSTTCGP`):** Công ty Viễn thông Điện lực và Công nghệ thông tin – EVN (EVNICT, phần mềm CMIS), `MSTTCGP = "0100100079-010"`.
     - **Ký hiệu hóa đơn (`KHMSHDon` + `KHHDon`):** Hóa đơn điện thuộc diện **HĐĐT không có mã của cơ quan thuế** (khoản 2 Điều 9 NĐ 123/2020), nên ký tự thứ 2 là `K`. Ví dụ trên mẫu thật của PC Sài Gòn: `KHMSHDon = "1"`, `KHHDon = "K26TSG"` (năm 2026; mẫu năm 2022 là `1K22TSG`, PC Thanh Trì Hà Nội là `1K22TCA`). Vì không có mã CQT nên thẻ `MCCQT` không có.
     - **Bảng hàng hóa dịch vụ (`DSHHDVu/HHDVu`) trên mặt Hóa đơn GTGT:** Chỉ hiển thị **01 dòng gộp duy nhất** cho toàn kỳ:
       - `STT = 1`, `TChat = 1` (lưu ý: Phụ lục XV của `QĐ 1271/QĐ-CT` trang 317 chỉ quy định `TChat = 5` / `TTHHDTrung` cho 3 nhóm: ô tô–mô tô, vận tải, vận tải trên nền tảng TMĐT; **không** áp `TChat = 5` cho điện/nước).
       - `THHDVu`: `"Điện tiêu thụ tháng MM năm YYYY từ ngày DD/MM/YYYY đến ngày DD/MM/YYYY"` kèm dòng diễn giải `"(kèm theo bảng kê số <SBKe> ngày DD tháng MM năm YYYY)"` (ứng với thẻ `TTChung/SBKe` và `TTChung/NBKe` trong QĐ 1271).
       - `DVTinh`: `"kWh"`.
       - `SLuong`: **Tổng sản lượng kWh** của tất cả khung giờ cộng lại.
       - **`DGia`: ĐỂ TRỐNG (`-` / `null` trong XML)** khi hóa đơn có nhiều đơn giá (bậc thang hoặc 3 khung giờ TOU)! **Phát hiện quan trọng cho module `ingest`:** `einvoice-xml.md §4` hiện ghi kiểm tra số học `SLuong × DGia − STCKhau = ThTien` cho mọi dòng; quy tắc này sẽ báo lỗi giả (`AMOUNT_MISMATCH`) trên hóa đơn điện thực tế của EVN vì QĐ 1271 chỉ quy định `DGia` là *"Bắt buộc (Nếu có)"* và EVN bỏ trống `DGia` trên mặt hóa đơn GTGT khi có bảng kê kèm theo (`SBKe`).
       - `ThTien`: Tổng tiền điện chưa thuế GTGT.
       - Phần tổng hợp (`TToan`): `TgTCThue` (Cộng tiền hàng), `TSuat = "8%"`, `TgTThue` (Tiền thuế GTGT = `round(TgTCThue × 8%)`), `TgTTTBSo` (Tổng cộng tiền thanh toán), `TgTTTBChu`.
   - **Phần 2 — Bảng kê chi tiết hóa đơn tiền điện (ký số bởi cùng Công ty Điện lực khu vực):**
     - **Định danh & thông tin hợp đồng:**
       - `Số bảng kê` (9 chữ số trên mẫu EVNHCMC, khớp `SBKe` trên mặt hóa đơn GTGT), kèm tham chiếu `(kèm theo hóa đơn số <SHDon> ngày DD tháng MM năm YYYY)`.
       - **`Mã khách hàng` (`customer_code`):** tại TP.HCM (EVNHCMC) gồm **13 ký tự bắt đầu bằng `PE`** (`PE` + 2 chữ số mã Công ty Điện lực khu vực + 9 chữ số, ví dụ `PE0100XXXXXXX`; tại các tỉnh miền Nam EVNSPC bắt đầu bằng `PB`, Hà Nội `PD`, miền Bắc `PA`, miền Trung `PC`).
       - **Hai địa chỉ tách biệt:** `Địa chỉ` (trụ sở pháp nhân trên đăng ký thuế của chuỗi) và **`Địa chỉ sử dụng điện`** (địa chỉ mặt bằng quán thực tế đặt công tơ — đây là trường tin cậy nhất để ánh xạ hóa đơn điện về đúng `store_id`, cùng với `customer_code` đã đăng ký trong `core.utility_accounts`).
       - `Mục đích sử dụng điện`: ghi tỷ lệ % cho từng khung giờ, ví dụ `100 % Kinh doanh - Giờ bình thường`, `100 % Kinh doanh - Giờ cao điểm`, `100 % Kinh doanh - Giờ thấp điểm` (nếu một công tơ dùng chung cả sinh hoạt và kinh doanh thì chia tỷ lệ % tương ứng).
       - `Cấp điện áp sử dụng`: ví dụ `Dưới 380V` (thuộc bậc hạ áp đến 01 kV).
       - `Kỳ hóa đơn`: định dạng `"Tháng MM/YYYY (N ngày từ DD/MM/YYYY đến DD/MM/YYYY)"`. `Hạn thanh toán`: `DD/MM/YYYY` (thường 7 ngày kể từ ngày phát hành).
     - **Bảng 1 — `TÌNH HÌNH SỬ DỤNG ĐIỆN CỦA KHÁCH HÀNG`:**
       - Bảng điện năng tác dụng (`kWh`): các cột theo đúng thứ tự từ trái sang phải trên mẫu EVNHCMC là:  
         `CÔNG TƠ ĐO ĐẾM` (dòng đầu in số seri công tơ, các dòng dưới in `Khung giờ bình thường`, `Khung giờ cao điểm`, `Khung giờ thấp điểm`) | `HỆ SỐ NHÂN` (`1` với công tơ trực tiếp hạ áp; `> 1` nếu qua biến dòng TI ở trạm/bếp công suất lớn) | **`CHỈ SỐ MỚI`** *(lưu ý: cột Chỉ số mới đứng trước cột Chỉ số cũ)* | **`CHỈ SỐ CŨ`** | `ĐIỆN TIÊU THỤ (kWh)` (`= (Chỉ số mới − Chỉ số cũ) × Hệ số nhân`), kết thúc bằng dòng `Tổng: <tổng kWh>`.
       - Bảng điện năng phản kháng (`kVArh`, xuất hiện trên mẫu ngoài sinh hoạt dùng công tơ 3 pha): `CÔNG TƠ ĐO ĐẾM` | `HỆ SỐ NHÂN` | `CHỈ SỐ MỚI` | `CHỈ SỐ CŨ` | `ĐIỆN NĂNG PHẢN KHÁNG (kVArh)` và dòng chỉ số `SLVC/SLHC`, `HỆ SỐ COSFI`, `HỆ SỐ K %` (với quán cà phê hạ áp công suất cực đại `< 40 kW`, `HỆ SỐ K % = 0`, không phát sinh tiền công suất phản kháng).
     - **Bảng 2 — `TỔNG SỐ TIỀN THANH TOÁN`:**
       - Cột: `KHUNG GIỜ MUA ĐIỆN` | `ĐƠN GIÁ (đồng/kWh)` | `SẢN LƯỢNG (kWh)` | `THÀNH TIỀN (đồng)` (từng dòng cho Bình thường, Cao điểm, Thấp điểm + dòng `Tổng`).
       - Khối tổng kết cuối bảng: `Tổng điện năng tiêu thụ (kWh)` → `Tổng tiền điện chưa thuế (đồng)` → `Thuế suất GTGT` (`8%`) → `Thuế GTGT (đồng)` → `Tổng cộng tiền thanh toán (đồng)` → `Bằng chữ`.

#### c) Sản lượng điện tiêu thụ điển hình (`kWh/tháng`) của một quán cà phê nhỏ

> **Cảnh báo nguồn:** Không có báo cáo thống kê chính thức nào của EVN, Bộ Công Thương hay Cục Thống kê công bố định mức `kWh/tháng` riêng cho loại hình quán cà phê. Các khoảng số dưới đây được tổng hợp từ **nguồn thứ cấp** (bài tính toán phụ tải thiết bị ngành điện mặt trời / tư vấn mở quán F&B) để làm tham chiếu khoảng giá trị cho `sim-world`, **không phải số liệu thống kê chính thức**:

| Quy mô điểm bán | Thiết bị chính | Khoảng `kWh/tháng` (tham khảo thứ cấp) | Ước tính tiền điện/tháng theo `QĐ 2892` + VAT `8%` | Áp dụng công tơ theo `TT 60/2025/TT-BCT` |
|---|---|---:|---:|---|
| Kiosk / Take-away nhỏ (< 20 m², không máy lạnh hoặc 1 máy lạnh nhỏ) | Máy pha 1 group, máy xay, tủ mát nhỏ, đèn, quạt | **400 – 700 kWh** | ~1,4 – 2,6 triệu đ | Dưới 2.000 kWh (1 giá `3.089` đ hoặc 3 giá nếu đã lắp công tơ điện tử TOU) |
| **Quán cà phê nhỏ có chỗ ngồi (20 – 40 m², mở 07:00–22:00)** | Máy pha 1–2 group (2,5–3,4 kW), máy xay, máy sinh tố, tủ mát 24/24, 1–2 máy lạnh chạy 8–12h/ngày, đèn, Wi-Fi | **900 – 1.300 kWh** (~30–43 kWh/ngày) | **~3,4 – 5,0 triệu đ** | Dưới 2.000 kWh (1 giá hoặc 3 giá) |
| **Quán cà phê vừa trong chuỗi (50 – 100 m², mở 07:00–22:30)** | Máy pha 2 group, máy làm đá, tủ mát bánh + tủ đông nhỏ, 2–3 máy lạnh chạy 14h/ngày | **1.400 – 2.500 kWh** | **~5,2 – 9,5 triệu đ** | Từ `2.000 kWh/tháng` (3 tháng liên tục) **bắt buộc 3 giá** |
| Bếp trung tâm / kho lạnh sơ chế | Lò nướng, bếp công nghiệp, tủ đông/mát công nghiệp | **Chưa xác minh** (chưa có nguồn công khai đáng tin cậy) | — | Thường ≥ 2.000 kWh/tháng (bắt buộc 3 giá) |

*Tỷ trọng kWh theo khung giờ cho quán mở cửa `07:00–22:00` (suy luận kỹ thuật từ lịch vận hành + `QĐ 963/QĐ-BCT`, đánh dấu là giả định mô phỏng):*
- `off_peak` (`00:00–06:00`, chỉ tủ mát/tủ đông + camera/router chạy nền): ~**5% – 8%** tổng kWh.
- `peak` (`17:30–22:00` Thứ Hai – Thứ Bảy = 26 ngày × 4,5h; Chủ nhật = 0h): ~**22% – 28%** tổng kWh.
- `normal` (`06:00–17:30` T2–T7 + cả ngày Chủ nhật `06:00–22:00`): ~**65% – 72%** tổng kWh.  
→ Đơn giá bình quân gia quyền chưa thuế rơi vào khoảng **`3.550 – 3.700` đ/kWh** (~`3.830 – 4.000` đ/kWh sau VAT 8%).

### 1.2. Bảng nguồn (`sources`) — Mục 1

| Nguồn (`url`) | Đơn vị phát hành (`publisher`) | Ngày văn bản / đăng (`date`) | Ngày truy cập (`retrieved_on`) | Phân loại |
|---|---|---|---|---|
| https://www.evn.com.vn/userfile/User/tcdl/files/2026/11/1_QD-BCT_2026_2892-20261104131123509.pdf | Bộ Công Thương (lưu trữ trên cổng chính thức EVN) | 2026-10-31 | 2026-11-26 | Chính thức (PDF ký số `QĐ 2892/QĐ-BCT`) |
| https://vpubnd.daklak.gov.vn/CMS/Content/VanBan/2026/11.2026/2892-Q%C4%90-BCT.pdf | Bộ Công Thương (đăng tải trên Cổng VP UBND tỉnh Đắk Lắk) | 2026-10-31 | 2026-11-26 | Chính thức (PDF ký số `QĐ 2892/QĐ-BCT`, đã đọc toàn văn 7 trang) |
| https://www.evn.com.vn/d/vi-VN/news/Quyet-dinh-so-2892QD-BCT-ngay-31102026-cua-Bo-Cong-Thuong-quy-dinh-ve-gia-ban-dien-60-3566-510199 | Tập đoàn Điện lực Việt Nam (EVN) | 2026-11-04 | 2026-11-26 | Chính thức |
| https://www.evn.com.vn/d/vi-VN/news/EVN-thong-tin-ve-viec-thuc-hien-chinh-sach-gia-dien-tu-ngay-1112026-60-3557-510202 | Tập đoàn Điện lực Việt Nam (EVN) | 2026-11-04 | 2026-11-26 | Chính thức |
| https://www.evn.com.vn/userfile/User/minhhanh/files/2026/4/1_QD-BCT_2026_963_30f7a-20260423202657276.pdf | Bộ Công Thương (lưu trữ trên cổng chính thức EVN) | 2026-04-22 | 2026-11-26 | Chính thức (PDF ký số `QĐ 963/QĐ-BCT`, đã đọc toàn văn) |
| https://www.evn.com.vn/d/vi-VN/news/Quyet-dinh-so-963QD-BCT-ve-khung-gio-cao-diem-thap-diem-va-gio-binh-thuong-cua-he-thong-dien-quoc-gia--60-134-507803 | Tập đoàn Điện lực Việt Nam (EVN) | 2026-04-23 | 2026-11-26 | Chính thức (dẫn cả khoản 3 Điều 5 `TT 60/2025/TT-BCT`) |
| https://vanban.chinhphu.vn/?pageid=27160&docid=216125 | Cổng Thông tin điện tử Chính phủ | 2025-12-02 | 2026-11-26 | Chính thức (`Thông tư 60/2025/TT-BCT`) |
| https://vanban.chinhphu.vn/?pageid=27160&docid=214310 | Cổng Thông tin điện tử Chính phủ | 2025-06-30 | 2026-11-26 | Chính thức (`Nghị định 174/2025/NĐ-CP` giảm VAT 8% đến 31/12/2026) |
| https://tphcm.chinhphu.vn/evnhcmc-thay-doi-mau-hoa-don-tien-dien-tu-ngay-1-7-2022-101220701162704798.htm | Báo Điện tử Chính phủ – Chuyên trang TP.HCM | 2022-07-01 | 2026-11-26 | Chính thức (có ảnh mẫu Hóa đơn GTGT & Bảng kê ngoài sinh hoạt của EVNHCMC) |
| https://www.evn.com.vn/d6/news/Tu-ngay-172022-EVN-trien-khai-ap-dung-mau-hoa-don-dien-tu-theo-quy-dinh-cua-Bo-Tai-chinh-0-12-30769.aspx | Tập đoàn Điện lực Việt Nam (EVN) | 2022-07-01 | 2026-11-26 | Chính thức (mẫu HĐĐT EVN theo QĐ 1450 / NĐ 123, `MSTTCGP` của EVNICT) |
| `docs/04-data/references/QD-1271-QD-CT-2025.pdf` | Cục Thuế | 2025-05-30 | 2026-11-26 | Chính thức (đã lưu sẵn trong repo; đối chiếu `SBKe`, `DGia`, Phụ lục XV) |
| https://vietnamsolar.vn/ (qua tóm tắt tìm kiếm các bài tính phụ tải điện quán cà phê nhỏ) | Vietnam Solar & các trang tư vấn F&B | Không ghi rõ | 2026-11-26 | **Thứ cấp** (chỉ dùng tham khảo khoảng 400–2.000 kWh/tháng) |

### 1.3. Khoảng trống còn lại (`gaps remaining`) — Mục 1

1. **Chưa có file `.xml` gốc thực tế của EVNHCMC** (mới có ảnh chụp bản thể hiện PDF chính thức của Hóa đơn GTGT + Bảng kê chi tiết ngoài sinh hoạt). Chưa xác minh được trong file XML thực tế của EVNHCMC (CMIS / EVNICT) các thông số công tơ và bảng kê được đóng gói vào các cặp `TTKhac/TTin {TTruong, KDLieu, DLieu}` với tên `TTruong` chính xác là gì, hay bảng kê tách thành một file XML/PDF riêng ngoài file XML hóa đơn GTGT.
2. **Chưa xác minh** EVNHCMC đã chuyển `PBan` từ `2.0.0` (QĐ 1450) sang `2.1.0` (QĐ 1271) ở kỳ tháng 11/2026 chưa (`einvoice-xml.md §1` đã thiết kế ingest nhận cả hai).
3. **Sản lượng kWh của bếp trung tâm** không có nguồn công khai; sản lượng kWh của quán cà phê nhỏ chỉ có nguồn thứ cấp.

### 1.4. Đề xuất chỉnh sửa tài liệu hiện có (chỉ đề xuất, không tự sửa)

- **`docs/04-data/README.md` (bảng Tình trạng mẫu thật):**
  - Dòng *"Biểu giá điện kinh doanh"*: cập nhật trạng thái thành `✅ Đã đối chiếu văn bản gốc QĐ 2892/QĐ-BCT & QĐ 963/QĐ-BCT`; gợi ý tải bản gốc `2892-QD-BCT.pdf` và `963-QD-BCT.pdf` từ `evn.com.vn` lưu vào `docs/04-data/references/`.
  - Dòng *"Hóa đơn tiền điện, tiền nước: bố cục"*: đổi từ `❌ Chưa có` sang `🟡 Có mẫu bản thể hiện PDF/bảng kê chính thức (EVNHCMC, SAWACO); còn thiếu file XML thật`.
- **`docs/04-data/sources.md §2`:**
  - Thay nguồn Báo SGGP bằng link văn bản gốc ký số `QĐ 2892/QĐ-BCT` (ngày 31/10/2026) và `QĐ 963/QĐ-BCT` (ngày 22/04/2026) trên `evn.com.vn`.
  - Sửa tên nhóm thành **"Giá bán lẻ điện cho kinh doanh khác" (mục 3.3 Phụ lục QĐ 2892/QĐ-BCT)**; ghi rõ khung giờ bình thường (`06:00–17:30` và `22:30–24:00` T2–T7; `06:00–24:00` Chủ nhật), thuế suất VAT **8%** năm 2026 (`NĐ 174/2025/NĐ-CP`), và điều kiện công tơ 3 giá (`≥ 2.000 kWh/tháng` hoặc TBA `≥ 25 kVA` theo khoản 3 Điều 5 `TT 60/2025/TT-BCT`).
- **`docs/04-data/einvoice-xml.md §4` (dòng 135 — kiểm tra số học của `ingest`):**
  - Sửa quy tắc `SLuong × DGia − STCKhau = ThTien` thành: **chỉ kiểm tích `SLuong × DGia` khi `DGia` có mặt (`DGia != null`)**; khi hóa đơn có `SBKe` (như hóa đơn tiền điện nhiều khung giờ/bậc thang của EVN) mà `DGia` để trống thì kiểm tổng `Σ ThTien` ở mức dòng/thuế suất và đối chiếu chi tiết qua `readings` của `/sim/bills` (hoặc bảng kê).

---

## 2. Nước kinh doanh tại TP.HCM (SAWACO và công ty thành viên)

### 2.1. Kết quả nghiên cứu (`findings`)

#### a) Biểu giá nước sạch & dịch vụ thoát nước kinh doanh TP.HCM năm 2026

Đối chiếu trực tiếp văn bản dấu đỏ **Thông báo số `3698/TB-CNBT-KDDVKH`** ngày **23/12/2025** (đăng tải ngày `26/12/2025`) của **Công ty Cổ phần Cấp nước Bến Thành** (đơn vị thành viên Tổng Công ty Cấp nước Sài Gòn – TNHH MTV / SAWACO) về *"Đơn giá nước sạch, dịch vụ thoát nước và xử lý nước thải từ ngày 01/01/2026 đến 31/12/2026"*:

1. **Hệ thống căn cứ pháp lý đang có hiệu lực trong năm 2026 tại TP.HCM:**
   - **Quyết định số `25/2019/QĐ-UBND`** ngày **24/10/2019** của UBND TP.HCM ban hành giá nước sinh hoạt trên địa bàn TP.HCM lộ trình 2019–2022 (được sửa đổi, bổ sung một số điều bởi `QĐ 02/2022/QĐ-UBND`). Tính đến năm 2026, UBND TP.HCM chưa ban hành lộ trình tăng giá nước sạch mới nên mức giá cột năm 2022 vẫn giữ nguyên sang năm 2025 và **2026**.
   - **Quyết định số `728/QĐ-TCT-KDDVKH`** ngày **05/11/2019** của Tổng Công ty Cấp nước Sài Gòn TNHH MTV (SAWACO) ban hành đơn giá tiêu thụ nước sạch cho cơ quan hành chính sự nghiệp, đoàn thể, đơn vị sản xuất và **đơn vị kinh doanh, dịch vụ** trên địa bàn TP.HCM lộ trình 2019–2022 *(đây là văn bản trực tiếp quy định con số `21.300 đ/m³` cho kinh doanh dịch vụ và `12.100 đ/m³` cho sản xuất)*.
   - **Quyết định số `17/2021/QĐ-UBND`** ngày **01/06/2021** của UBND TP.HCM ban hành **giá dịch vụ thoát nước và xử lý nước thải** trên địa bàn TP.HCM lộ trình 2022–2025: tỷ lệ thu trên đơn giá nước sạch chưa thuế tăng từ `15%` (2022) → `20%` (2023) → `25%` (2024) → đạt mức đỉnh lộ trình **`30%` từ năm 2025 và tiếp tục áp dụng mức `30%` trong suốt năm 2026**. SAWACO và các công ty cấp nước thành viên thu hộ khoản này trên cùng hóa đơn tiền nước.
   - **Khoản 2 Điều 1 Nghị định số `174/2025/NĐ-CP`** ngày **30/06/2025** của Chính phủ: dịch vụ thoát nước và xử lý nước thải (vốn chịu thuế suất chuẩn `10%`) được giảm 2% xuống còn **`8%`** đến hết ngày `31/12/2026`; riêng **nước sạch** vốn thuộc đối tượng chịu thuế suất ưu đãi **`5%`** theo Luật Thuế GTGT nên giữ nguyên **`5%`**.

2. **Phân biệt "Giá dịch vụ thoát nước" và "Phí bảo vệ môi trường đối với nước thải":**
   - Tại khu vực đô thị TP.HCM thuộc mạng lưới SAWACO áp dụng `QĐ 17/2021/QĐ-UBND`, khách hàng nộp **Giá dịch vụ thoát nước và xử lý nước thải (30% đơn giá nước sạch, là giá dịch vụ nên chịu thuế GTGT 8%)** và **không thu trùng Phí bảo vệ môi trường 10%** (trên cổng tra cứu HĐĐT của SAWACO vẫn có trường `PhiBVMT` nhưng nhận giá trị `0` ở các danh bộ đã thu giá dịch vụ thoát nước).

3. **Bảng tổng hợp đơn giá áp dụng từ `01/01/2026` đến `31/12/2026` (trích đúng Thông báo `3698/TB-CNBT-KDDVKH`):**

| Đối tượng sử dụng nước | Đơn giá nước sạch (đ/m³) | Thuế GTGT nước sạch (`5%`) | Đơn giá DV thoát nước (`30%`) | Thuế GTGT DV thoát nước (`8%`) | Tổng thanh toán (đ/m³) |
|---|---:|---:|---:|---:|---:|
| Sinh hoạt đến 4 m³/người/tháng (hộ dân cư) | 6.700 | 335 | 2.010 | 161 | 9.206 |
| Sinh hoạt trên 4 m³ đến 6 m³/người/tháng | 12.900 | 645 | 3.870 | 310 | 17.725 |
| Sinh hoạt trên 6 m³/người/tháng | 14.400 | 720 | 4.320 | 346 | 19.786 |
| Cơ quan hành chính sự nghiệp | 13.000 | 650 | 3.900 | 312 | 17.862 |
| **Đơn vị sản xuất** *(tham khảo nếu bếp trung tâm đăng ký mã SX)* | **12.100** | **605** | **3.630** | **290** | **16.625** |
| **Kinh doanh dịch vụ** *(áp dụng cho mọi quán F&B — không chia bậc thang)* | **21.300** | **1.065** | **6.390** | **511** *(chính xác `511,2`)* | **29.266** |

> **Lưu ý số học quan trọng cho `ingest` và `sim-world`:**  
> Ở dòng **Kinh doanh dịch vụ**, `6.390 × 8% = 511,2` đồng/m³. Bảng thông báo đơn giá 1 m³ của SAWACO làm tròn hiển thị thành `511` đồng (`21.300 + 1.065 + 6.390 + 511 = 29.266`). Tuy nhiên, trên Hóa đơn GTGT điện tử theo `QĐ 1271/QĐ-CT`, tiền thuế tính trên **tổng thành tiền của dòng thuế suất 8%**: `TThue_8 = round((SLuong × 6.390) × 0,08)`. Ví dụ với `24 m³`: `ThTien_DVTN = 24 × 6.390 = 153.360 đ`, `TThue_8 = round(153.360 × 0,08) = round(12.268,8) = 12.269 đ` → tổng thanh toán hóa đơn là **`702.389` đồng** (chênh `+5` đồng so với `24 × 29.266 = 702.384` đồng). Bộ sinh `sim-world` và `ingest` bắt buộc phải tính theo công thức từng dòng thuế suất (`round(ThTien × TSuat)`), **không** lấy `SLuong × 29.266`.

#### b) Bố cục Hóa đơn điện tử tiền nước của hệ thống SAWACO

Đối chiếu giao diện cổng tra cứu HĐĐT chính thức của các công ty cổ phần cấp nước thuộc SAWACO (`cskhphuhoatan.sawaco.com.vn`, `benthanh.sawaco.com.vn`, `cskh.sawaco.com.vn`):

1. **Đơn vị phát hành (`NBan`):**
   - Tại TP.HCM, khách hàng ký hợp đồng và nhận hóa đơn từ **Công ty Cổ phần Cấp nước phụ trách địa bàn quận/huyện** (công ty con/liên kết của SAWACO), mỗi đơn vị có **MST 10 chữ số riêng** và ký hiệu hóa đơn riêng:
     - Quận 1, Quận 3: *Công ty CP Cấp nước Bến Thành* (`MST: 0304789925`)
     - Bình Thạnh, Phú Nhuận, một phần Gò Vấp: *Công ty CP Cấp nước Gia Định* (`MST: 0304806225`)
     - Quận 5, 6, 8, Bình Tân (một phần): *Công ty CP Cấp nước Chợ Lớn* (`MST: 0304797806`)
     - Quận 10, 11, Tân Phú (một phần): *Công ty CP Cấp nước Phú Hòa Tân* (`MST: 0304796249`)
     - Tân Bình, Tân Phú: *Công ty CP Cấp nước Tân Hòa* (`MST: 0310350068`)
     - TP. Thủ Đức: *Công ty CP Cấp nước Thủ Đức* (`MST: 0304803601`)
     - Quận 12, Gò Vấp, Hóc Môn: *Công ty CP Cấp nước Trung An* (`MST: 0310350082`)
     - Quận 4, Quận 7, Nhà Bè: *Công ty CP Cấp nước Nhà Bè* (`MST: 0304789298`)
   - *Hệ quả thực tế cho chuỗi F&B nhiều quận ở TP.HCM:* Khác với tiền điện (mọi chi nhánh đều thuộc các Công ty Điện lực chi nhánh của cùng pháp nhân EVNHCMC `0300951119-xxx`), một chuỗi 5–15 quán rải qua nhiều quận sẽ có **3–6 nhà cung cấp nước khác nhau trong `vendor_registry`** (mỗi Công ty CP Cấp nước một MST và một tài khoản ngân hàng riêng)! *(Nhớ quy tắc của đội: trong `sim-world` vẫn sinh tên và MST giả theo tiền tố riêng của dự án, nhưng mô phỏng đúng cấu trúc nhiều đơn vị cấp nước hoặc 1–2 đơn vị cấp nước khu vực).*

2. **Số lượng hóa đơn & dòng hàng (`DSHHDVu/HHDVu`):**
   - Phát hành **01 Hóa đơn GTGT điện tử duy nhất** cho mỗi kỳ (không tách 2 hóa đơn riêng), không có mã CQT (`KHHDon` dạng `K26Txx`, ghép `1K26Txx`).
   - Do nước sạch chịu VAT `5%` còn dịch vụ thoát nước chịu VAT `8%`, trên cùng một Hóa đơn GTGT có **02 dòng `HHDVu`** với đầy đủ `SLuong`, `DGia`, `ThTien`, `TSuat`:
     - **Dòng 1:** `Tiền nước sạch` — `DVTinh = "m3"`, `SLuong = <m3>`, `DGia = 21300`, `ThTien = SLuong × 21300`, `TSuat = "5%"`.
     - **Dòng 2:** `Tiền dịch vụ thoát nước và xử lý nước thải` — `DVTinh = "m3"`, `SLuong = <m3>`, `DGia = 6390`, `ThTien = SLuong × 6390`, `TSuat = "8%"`.
   - Phần tổng hợp thuế suất `TToan/THTTLTSuat` có **02 thẻ `LTSuat`** riêng biệt: một thẻ cho `TSuat = "5%"` và một thẻ cho `TSuat = "8%"`, cộng thành `TgTCThue`, `TgTThue` và `TgTTTBSo`.

3. **Các trường nghiệp vụ ngành nước trên hóa đơn / giấy báo:**
   - **`Số Danh Bộ` (`SDB` / `Danh bạ`):** chuỗi **11 chữ số** (ví dụ `0110XXXXXXX`), đóng vai trò `customer_code` cố định của đồng hồ nước.
   - **`Mã giá biểu` (`GB` / `MGB`):** ký hiệu đối tượng giá (ví dụ `KD` hoặc mã số `31`/`32`/`33` cho kinh doanh dịch vụ); **`Định mức` (`DM`):** bằng `0` hoặc bỏ trống đối với khách hàng kinh doanh dịch vụ (vì toàn bộ sản lượng áp một mức giá `21.300 đ/m³`, không chia bậc theo nhân khẩu).
   - **`Kỳ` (`Ky`):** `MM/YYYY`, kèm mốc đọc số `Từ ngày DD/MM/YYYY đến ngày DD/MM/YYYY` và hạn thanh toán trong vòng **7 ngày**.
   - **Chỉ số đồng hồ:** `Chỉ số cũ` (`CSC` / `CScu`), `Chỉ số mới` (`CSM` / `CSmoi`), `Tiêu thụ` / `Lượng nước tiêu thụ (LNTT)` tính bằng `m³` nguyên dương (`= CSM − CSC`; đồng hồ nước thương mại thông thường đọc trực tiếp `m³`, hệ số nhân = `1`).
   - *Lưu ý vận hành cổng tra cứu:* Một số công ty cấp nước thành viên (như Cấp nước Bến Thành) gửi **Giấy báo tiền nước** trước để thanh toán và chỉ mở tải Hóa đơn GTGT điện tử trên cổng web sau khi đã gạch nợ, hoặc gửi qua kênh thanh toán hóa đơn liên kết (MoMo Bill Pay) — hoàn toàn khớp với thiết kế kênh vào `GET /sim/bills` (`xml_attachment_id | null`) trong `sim-world-api.md §3`!

#### c) Lượng nước tiêu thụ điển hình (`m³/tháng`) của một quán cà phê

> **Cảnh báo nguồn:** Cũng như điện năng, không có số liệu thống kê nhà nước cho lượng nước tiêu thụ riêng của quán cà phê; các khoảng dưới đây lấy từ **nguồn thứ cấp** (hướng dẫn vận hành F&B), nhưng khi nhân với đơn giá chính thức `29.266 đ/m³` của SAWACO năm 2026 lại **khớp chính xác tuyệt đối** với con số minh họa trong BRD hiện tại của PayMatch:

| Quy mô điểm bán | Nhu cầu dùng nước chính | Khoảng `m³/tháng` (tham khảo thứ cấp) | Tiền nước + DVTN + VAT năm 2026 (`~29.266 đ/m³`) | Đối chiếu kịch bản BRD §3.1 & §14 |
|---|---|---:|---:|---|
| Quán nhỏ / Take-away (< 30 chỗ, dùng ly nhựa/giấy mang đi là chính) | Pha chế, tráng dụng cụ, lau sàn, WC nhân viên | **5 – 15 m³** | ~146.000 – 439.000 đ | — |
| **Quán cà phê quy mô vừa trong chuỗi (50 – 100 m², 50–150 khách/ngày)** | Máy pha xả rửa group liên tục, máy lọc nước RO (có tỷ lệ nước thải RO), rửa ly thủy tinh tại chỗ, làm đá (nếu tự làm), WC khách | **15 – 35 m³** *(điển hình ~22–25 m³)* | **~439.000 – 1.024.000 đ** *(tại `24 m³` = **`702.389 đ`**)* | ✅ **Khớp sát con số "~700 nghìn/tháng" bình thường trong BRD §3.1!** |
| **Ca bất thường: Rò ống ngầm / kẹt phao bồn cầu tại quán** | Rò rỉ liên tục 24/24 (~0,16 m³/giờ thêm vào mức nền) | **~140 – 145 m³** *(tại `144 m³` = gấp đúng 6× mức 24 m³)* | **~4,10 – 4,24 triệu đ** *(tại `144 m³` = **`4.214.333 đ`**)* | ✅ **Khớp sát kịch bản "Tiền nước quán 3: 4,2 triệu, gấp 6 lần bình thường" (BRD §14)!** |
| Quán lớn / sân vườn (> 200 khách/ngày, có đồ ăn, tưới cây) | Pha chế, sơ chế, rửa chén bát, tưới cây, WC đông khách | **40 – 70+ m³** | ~1,17 – 2,05+ triệu đ | — |
| Bếp trung tâm | Sơ chế rau thịt, nấu sốt, vệ sinh xưởng | **Chưa xác minh** | — | — |

### 2.2. Bảng nguồn (`sources`) — Mục 2

| Nguồn (`url`) | Đơn vị phát hành (`publisher`) | Ngày văn bản / đăng (`date`) | Ngày truy cập (`retrieved_on`) | Phân loại |
|---|---|---|---|---|
| https://benthanh.sawaco.com.vn/images/th_ng_b_o_gi_n_c_n_m_2026.pdf | Công ty CP Cấp nước Bến Thành – SAWACO | 2025-12-23 | 2026-11-26 | Chính thức (PDF ký đóng dấu đỏ `3698/TB-CNBT-KDDVKH`, đã đọc toàn văn) |
| https://benthanh.sawaco.com.vn/dich-vu-khach-hang/khach-hang-can-biet/don-gia-nuoc-sach-dich-vu-thoat-nuoc-va-xu-ly-nuoc-thai-tu-ngay-01012026-den-31122026..html | Công ty CP Cấp nước Bến Thành – SAWACO | 2025-12-26 | 2026-11-26 | Chính thức |
| https://congbao.hochiminhcity.gov.vn/cong-bao/van-ban/quyet-dinh/so/17-2021-qd-ubnd/ngay/01-06-2021/44393 | Công báo TP. Hồ Chí Minh (UBND TP.HCM) | 2021-06-01 | 2026-11-26 | Chính thức (`Quyết định 17/2021/QĐ-UBND` lộ trình giá DVTN 30%) |
| https://sawaco.com.vn/post-detail/tien-dich-vu-xu-ly-nuoc-thai-va-thoat-nuoc-tang-deu-moi-nam-5-231219154405 | Tổng Công ty Cấp nước Sài Gòn (SAWACO) | 2023-12-19 | 2026-11-26 | Chính thức |
| https://cskhphuhoatan.sawaco.com.vn/hoa-don-dien-tu-tien-nuoc | Công ty CP Cấp nước Phú Hòa Tân – SAWACO | Đang vận hành 2026 | 2026-11-26 | Chính thức (cấu trúc trường tra cứu HĐĐT tiền nước `Ky`, `GB`, `DM`, `CScu`, `CSmoi`, `Tieuthu`, `Giaban`, `Thue`, `PhiBVMT`, `TienDVTN`, `ThueDVTN`) |
| http://benthanh.sawaco.com.vn/tin-tuc/hoat-dong-san-xuat-kinh-doanh/huong-dan-tra-cuu-hoa-don-dien-tu.html | Công ty CP Cấp nước Bến Thành – SAWACO | 2017-09-28 (cổng đang vận hành) | 2026-11-26 | Chính thức (quy trình tra cứu theo Danh bộ 11 số, quản lý nhiều đồng hồ cho DN) |
| https://vanban.chinhphu.vn/?pageid=27160&docid=214310 | Cổng Thông tin điện tử Chính phủ | 2025-06-30 | 2026-11-26 | Chính thức (`NĐ 174/2025/NĐ-CP` giảm VAT DVTN còn 8%) |
| https://www.dienmayxanh.com/ và https://zalopay.vn/ (qua tóm tắt tìm kiếm hướng dẫn chi phí nước quán cà phê) | Điện Máy Xanh / ZaloPay Blog | Không ghi rõ | 2026-11-26 | **Thứ cấp** (chỉ dùng tham khảo khoảng `5–35 m³/tháng`) |

### 2.3. Khoảng trống còn lại (`gaps remaining`) — Mục 2

1. **Chưa có file `.xml` hoặc ảnh chụp mặt Hóa đơn GTGT tiền nước thật của một điểm kinh doanh thuộc SAWACO** (cổng `hoadon.capnuocbenthanh.com` và `hddt.sawaco.com.vn` yêu cầu mã tra cứu/danh bộ đã thanh toán). Cần xác nhận bằng 1 file XML thật xem mã `Danh bộ` 11 số được đặt ở thẻ `NMua/MKHang` hay trong `TTKhac`.
2. **Văn bản gốc `QĐ 25/2019/QĐ-UBND` trên `www.congbao.hochiminhcity.gov.vn` gặp lỗi SSL hostname mismatch** khi truy cập tự động bằng script (`www.congbao...` vs `congbao...`), tuy nhiên toàn bộ số hiệu, ngày ban hành và biểu giá đã được xác minh chéo đầy đủ từ Thông báo dấu đỏ `3698/TB-CNBT-KDDVKH` của SAWACO Bến Thành.

### 2.4. Đề xuất chỉnh sửa tài liệu hiện có (chỉ đề xuất, không tự sửa)

- **`docs/04-data/README.md`:**
  - Dòng *"Giá nước kinh doanh"*: cập nhật từ `❌ Chưa tìm được` thành `✅ Có biểu giá chính thức 2026 (QĐ 25/2019/QĐ-UBND, QĐ 728/QĐ-TCT-KDDVKH, QĐ 17/2021/QĐ-UBND, TB 3698/TB-CNBT-KDDVKH)`. Gợi ý lưu file `th_ng_b_o_gi_n_c_n_m_2026.pdf` vào `docs/04-data/references/`.
- **`docs/04-data/sources.md`:**
  - Thêm mục **§2b. Biểu giá nước kinh doanh TP.HCM (SAWACO 2026)** ngay sau §2 Biểu giá điện, ghi rõ 2 dòng trên hóa đơn (`Nước sạch: 21.300 đ/m³, VAT 5%` và `Dịch vụ thoát nước & XLNT: 6.390 đ/m³ = 30%, VAT 8%`), tổng `29.266 đ/m³`, định dạng `Danh bộ` 11 chữ số, và xóa dòng *"Chưa tìm thấy biểu giá SAWACO 2026"* ở bảng §6.

---

## 3. Quy mô Persona chuỗi F&B nhỏ và Ngưỡng pháp lý `NĐ 80/2021/NĐ-CP`

### 3.1. Kết quả nghiên cứu (`findings`)

#### a) Ngưỡng xác định Doanh nghiệp nhỏ và vừa theo `NĐ 80/2021/NĐ-CP` (lĩnh vực Thương mại và Dịch vụ)

Đối chiếu trực tiếp văn bản gốc ký số **Nghị định số `80/2021/NĐ-CP`** ngày **26/08/2021** của Chính phủ (có hiệu lực từ `15/10/2021`, Phó Thủ tướng Lê Minh Khái ký, trang 4–6 bản `80.signed_01.pdf` trên `datafiles.chinhphu.vn`):

- Theo **Điều 6**, lĩnh vực hoạt động xác định theo ngành nghề kinh doanh chính đã đăng ký; hoạt động chuỗi cà phê – ăn uống (mã ngành VSIC `5610` / `5630`) thuộc lĩnh vực **Thương mại và dịch vụ**. *(Lưu ý: ngay cả khi chuỗi có 1 bếp trung tâm sơ chế nội bộ phục vụ chính chuỗi cửa hàng của mình thì ngành kinh doanh chính tạo doanh thu vẫn là dịch vụ ăn uống — Thương mại và dịch vụ).*
- Theo **Điều 5, Điều 7, Điều 8, Điều 9**, doanh nghiệp phải thỏa **đồng thời** tiêu chí lao động (**số lao động có tham gia BHXH bình quân năm** = tổng số lao động đóng BHXH của 12 tháng chia 12, không tính nhân viên thời vụ/part-time không thuộc diện đóng BHXH bắt buộc) **và một trong hai** tiêu chí tài chính (tổng doanh thu năm trước liền kề trên BCTC **hoặc** tổng nguồn vốn cuối năm trên Bảng cân đối kế toán):

| Phân loại (Điều 5 `NĐ 80/2021/NĐ-CP` — Thương mại & Dịch vụ) | Lao động tham gia BHXH bình quân năm | Tổng doanh thu của năm | **HOẶC** Tổng nguồn vốn của năm | Điều kiện loại trừ |
|---|---:|---:|---:|---|
| **1. Doanh nghiệp siêu nhỏ** (khoản 1) | **≤ 10 người** | **≤ 10 tỷ đồng** | **≤ 3 tỷ đồng** | — |
| **2. Doanh nghiệp nhỏ** (khoản 2) | **≤ 50 người** | **≤ 100 tỷ đồng** | **≤ 50 tỷ đồng** | Không phải là DN siêu nhỏ theo khoản 1 |
| **3. Doanh nghiệp vừa** (khoản 3) | **≤ 100 người** | **≤ 300 tỷ đồng** | **≤ 100 tỷ đồng** | Không phải là DN siêu nhỏ, DN nhỏ theo khoản 1, khoản 2 |

**Hệ quả pháp lý quan trọng khi soi vào hai phương án persona hiện tại:**
- **Persona BRD hiện tại (5 quán, doanh thu ~8 tỷ/năm):** Nếu chuỗi chỉ đóng BHXH cho `≤ 10` nhân sự cơ hữu (ví dụ 1 kế toán + 5 quản lý quán + 3–4 pha chế trưởng, phần còn lại là sinh viên làm theo giờ không đóng BHXH) thì với doanh thu `8 tỷ ≤ 10 tỷ`, doanh nghiệp này bị xếp vào **Doanh nghiệp siêu nhỏ**, chưa đạt ngưỡng **Doanh nghiệp nhỏ**! Chỉ cần nâng doanh thu giả lập lên **12–15 tỷ/năm** (~200–250 triệu/quán/tháng) và `15–25` lao động BHXH thì chuỗi 5 quán nằm **chính giữa phân khúc Doanh nghiệp nhỏ**.
- **Persona đề xuất trong `persona.md` (15 quán + 1 bếp trung tâm, chi mua hàng ~1,5–2,5 tỷ/tháng):** Với tỷ lệ chi phí nguyên liệu F&B ~30% doanh thu, doanh thu chuỗi tương ứng khoảng **54–90 tỷ/năm** (< 100 tỷ). Nếu số lao động đóng BHXH `≤ 50` người → **Doanh nghiệp nhỏ** (sát trần trên); nếu đóng BHXH cho `51–100` người (rất dễ xảy ra khi có 16 quản lý điểm + đội bếp trung tâm + văn phòng + ca trưởng 15 quán) → bước sang **Doanh nghiệp vừa**.

#### b) Số liệu công khai về vận hành chuỗi F&B nhỏ tại Việt Nam (5–15 cửa hàng)

1. **Quy mô thị trường, cơ cấu chi phí và sự phân hóa theo quy mô (nguồn khảo sát ngành chính thống — `iPOS.vn × Nestlé × VIRAC`, `n = 3.001` DN F&B, công bố `08/04/2026` trên VCCI):**
   - Toàn ngành F&B Việt Nam năm 2025 có khoảng **329.500 cửa hàng**, doanh thu **726.500 tỷ đồng** (+5,5%); dự báo năm 2026 đạt **333.600 cửa hàng** và **760.000 tỷ đồng**.
   - Áp lực chi phí đầu vào rất lớn: **69,38%** doanh nghiệp chịu tác động trực tiếp từ giá nguyên vật liệu tăng mạnh; **44,8%** doanh nghiệp F&B có chi phí nguyên vật liệu chiếm **từ 30% giá bán trở lên** và **6,2%** vượt 50% (BRD `[D1]`). Đồng thời, hóa đơn điện tử và đối chiếu thuế trở thành tiêu chuẩn bắt buộc.
   - Phân hóa theo quy mô: nhóm cửa hàng nhỏ lẻ gặp khó khăn nhất (chỉ **18,03%** tăng trưởng, **16,63%** sụt giảm mạnh), trong khi **nhóm quy mô trung bình** đạt sự cân bằng tốt nhất (**32,95%** tăng trưởng, chỉ **6,89%** giảm mạnh) và **nhóm thương hiệu chuỗi nhiều cửa hàng** duy trì ổn định cao (**40,74%** giữ vững doanh thu, **26,67%** tăng trưởng).

2. **Thực trạng kế toán & vận hành thủ công của SME trên hệ sinh thái MoMo (nguồn chính thức `MoMo`, `11/07/2025`, `[M3]`):**
   - Khảo sát của MoMo trên **203 doanh nghiệp nhỏ** cho thấy phần đông vẫn **quản lý đơn hàng, kho, kế toán và dòng tiền thủ công**, thiếu công cụ và kỹ năng sử dụng phần mềm quản lý bán hàng, hóa đơn điện tử, kế toán, dẫn tới dễ lệch số liệu và khó tiếp cận tín dụng.
   - Tuyên bố định vị của MoMo hướng tới nhóm **doanh nghiệp siêu nhỏ và nhỏ** (*"từ một cửa hàng tạp hóa hay một công ty vài chục nhân sự"*), lộ trình 3 bước: QR/loa nhận tiền → POS & kho → hóa đơn điện tử, kế toán & tín dụng dựa trên dòng tiền giao dịch.

3. **Doanh thu bình quân mỗi quán, bộ máy kế toán, số NCC và số hóa đơn/tháng:**
   - **Doanh thu/quán/tháng (nguồn thứ cấp — tổng hợp phân tích ngành F&B trên iPOS / CafeF):** quán cà phê vừa và nhỏ tại đô thị lớn thường đạt **80 – 200 triệu đồng/tháng/quán**; mô hình chuỗi chuẩn có mặt bằng tốt đạt **250 – 500 triệu đồng/tháng/quán** (các chuỗi lớn đầu ngành như Highlands đạt trung bình > 26 triệu/ngày ≈ 780 triệu/tháng).
   - **Nhân sự kế toán theo số cửa hàng (nguồn thứ cấp — hướng dẫn nghiệp vụ kế toán nhà hàng/chuỗi của iGlobal, MISA CukCuk):**
     - Chuỗi **5 cửa hàng**: thường chỉ có **1 – 3 nhân sự kế toán** (phổ biến là 1 kế toán thuế bán thời gian/dịch vụ + 1 kế toán nội bộ kiêm công nợ, chủ chuỗi trực tiếp duyệt chi).
     - Chuỗi **10 cửa hàng**: cần **4 – 6 kế toán** tách phần hành (tổng hợp, doanh thu đa kênh, kho – định lượng, công nợ – thanh toán, tiền lương).
     - Chuỗi **15 cửa hàng + bếp trung tâm**: thường cần **7 – 10 kế toán** (vì bếp trung tâm phát sinh kế toán giá thành sản xuất bán thành phẩm, định mức hao hụt sơ chế và phiếu điều chuyển kho nội bộ giữa bếp trung tâm ↔ 15 quán).
   - **Số lượng nhà cung cấp (NCC) và số lượng hóa đơn đầu vào/tháng:** **Chưa xác minh được số thống kê công khai** (không có báo cáo nào của GSO, VCCI hay iPOS công bố phân phối số NCC hay số HĐĐT đầu vào/tháng của chuỗi 5–15 quán). Mọi con số về số NCC và số hóa đơn/tháng trong cả BRD (~200 HĐ/tháng) lẫn `persona.md` (~45 NCC, ~550 HĐ/tháng) đều phải được ghi nhận minh bạch là **ước tính mô hình hóa từ tần suất giao hàng (operational modeling assumption)**, không phải số thống kê điều tra.

#### c) So sánh và Khuyến nghị chốt Persona: **5 quán (BRD, tinh chỉnh nhẹ)** vs **15 quán + bếp trung tâm (`persona.md`)**

| Tiêu chí đánh giá | Phương án A: **5 quán cà phê & bánh nhẹ** *(BRD tinh chỉnh doanh thu lên 12–14 tỷ/năm)* | Phương án B: **15 quán + 1 bếp trung tâm** *(`persona.md` hiện tại)* | Bên phù hợp hơn cho PayMatch v1 |
|---|---|---|---|
| **Phân loại theo Điều 5 `NĐ 80/2021/NĐ-CP`** | ~18–25 LĐ đóng BHXH (tổng ~45–60 nhân sự tính cả part-time), doanh thu **12–14 tỷ/năm** → **Doanh nghiệp nhỏ** chuẩn xác | ~50–80 LĐ đóng BHXH (tổng ~150–200 nhân sự), doanh thu **54–90 tỷ/năm** → Sát trần trên DN nhỏ hoặc sang **DN vừa** | **Phương án A** (đúng trọng tâm DN nhỏ) |
| **Độ chân thực với khách hàng MoMo Doanh Nghiệp `[M3]`** | Công ty vài chục nhân sự, chủ chuỗi tự duyệt chi, 1 kế toán bán thời gian/nội bộ, dùng ví/tài khoản MoMo Doanh Nghiệp làm nguồn chi chính (A1) | Doanh thu 60–90 tỷ/năm + bếp sản xuất trung tâm ngoài đời thường đã có phòng kế toán 7–10 người, dùng ERP (MISA AMIS/SAP B1) và ủy nhiệm chi lô qua ngân hàng thay vì giữ 2 tỷ/tháng trên ví MoMo | **Phương án A** |
| **Tương thích trần tự chi nền tảng `D9` (`30tr/HĐ`, `50tr/ngày`) & `TT 53/2026`** | Chi qua PayMatch ~**360–450 triệu/tháng** (~**12–15 triệu/ngày**): ngày thường ~80% hóa đơn 🟢 tự chi mượt mà đúng mục tiêu `problem-definition.md §6a`; ngày nhập sỉ dồn đợt (ví dụ cà phê 26,5tr + sữa 31tr = 57,5tr) **vẫn chạm trần 50tr/ngày** để demo `OVER_LIMIT` & duyệt `bulk` | Chi **50–80 triệu/ngày** → **ngày nào cũng lố trần cứng 50 triệu/ngày (`D9`)**, khiến chế độ `auto_pay` bị kẹt hằng ngày cho cả hóa đơn xanh; nếu nâng `D9` lên 100tr/ngày sẽ chạm ngưỡng rủi ro cao của **Thông tư 53/2026/TT-NHNN** (`> 50tr/lần`, `> 100tr/ngày`) | **Phương án A** |
| **Lý do tồn tại của đội 6 AI Agent** | ~**20–25 NCC** (cà phê, sữa, trà, si-rô, đá, bánh tươi giao thẳng 5 quán, bao bì in logo, hóa chất, bảo trì, điện EVNHCMC, 2–3 công ty cấp nước SAWACO, SaaS) và **~200 HĐ/tháng (~7 HĐ/ngày)**. Với 1 kế toán part-time và chủ chuỗi bận vận hành, kiểm 6 mặt/hóa đơn tốn ~35–45 giờ/tháng → hoàn toàn quá tải nếu làm tay, nhưng kết quả cuối ngày gọn trong 1–2 ca vàng/đỏ đúng `problem-definition.md §6a` | ~45 NCC, ~550 HĐ/tháng (~18 HĐ/ngày). Nổi bật tính năng `bulk approval`, nhưng chỉ 1 chủ chuỗi duy nhất được duyệt (`D4`) mà không cho kế toán trưởng duyệt phụ sẽ hơi khiên cưỡng ở quy mô 16 điểm | **Cả hai đều chứng minh được giá trị agent**, nhưng **Phương án A** khớp tự nhiên với `D4` ("chỉ chủ chuỗi duyệt") |
| **Đủ kịch bản cho cả 6 bot (`procurement`, `ap`, `branch-ops`, `fraud`, `tax`, `treasury`)?** | **Đủ 100%:** 5 quán khác nhau vẫn có giao thẳng từng quán / giao thiếu (`ap`), tráo quy cách thùng cốc 800 vs 1.000 (`procurement`), 5 công tơ điện + 5 đồng hồ nước so nền 12 tháng & doanh thu QR MoMo từng quán (`branch-ops`), mỗi tháng thử 1–2 NCC nguyên liệu mới để kích hoạt `escrow` D7, Zalo đổi TK, cảnh báo chéo D8 (`fraud`, `tax`), chạm trần ngày khi trùng đợt nhập (`treasury`) | Thêm trường hợp bếp trung tâm có nền điện nước riêng, nhưng không tạo thêm cơ chế kỹ thuật mới nào trong v1 | **Ngang nhau về độ phủ tính năng v1** |
| **Chi phí đồng bộ tài liệu trước hạn `03/12/2026` (còn 7 ngày)** | **Bằng 0** đối với kiến trúc & quy trình: khớp sẵn `PayMatch_BRD_v1.0.md` (§1, §5.1, §14), `problem-definition.md` (§5 D4, D9, §6a "~200 hóa đơn/tháng"), `architecture.md` (§1 "Chuỗi 5 quán có 1 kế toán bán thời gian"), `payment-gate.md`. Chỉ cần sửa doanh thu chị Lan từ `8 tỷ` → `12 tỷ/năm` để vượt ngưỡng siêu nhỏ | Phải sửa đồng loạt BRD, `problem-definition.md`, `architecture.md`, `payment-gate.md` và cân nhắc lại trần `D9` | **Phương án A vượt trội** |

> **KHUYẾN NGHỊ CHỐT:**  
> **Chọn Phương án A — Chuỗi 5 quán cà phê & bánh nhẹ tại TP.HCM (ví dụ ở Quận 1, Quận 3, Bình Thạnh, Quận 10, Phú Nhuận), nâng nhẹ doanh thu từ 8 tỷ lên `12–14 tỷ đồng/năm` (~200–230 triệu/quán/tháng), `~18–22` lao động đóng BHXH (trong tổng ~45 nhân sự cả part-time), `1` kế toán nội bộ/bán thời gian + `5` cửa hàng trưởng, `~22` nhà cung cấp (mỗi tháng phát sinh 1–2 NCC chào hàng mới), `~200` hóa đơn đầu vào/tháng (`~7` HĐ/ngày), tổng chi qua PayMatch `~380–450 triệu/tháng` (`~13–15 triệu/ngày`, ngày cao điểm nhập hàng theo lô lên tới `55–65 triệu/ngày`).**  
>  
> *Phương án dự phòng (nếu đội nhất quyết muốn nhấn mạnh bài toán quá tải duyệt tay trên 10 HĐ/ngày):* tối đa dừng ở **8 quán (không mở bếp trung tâm sản xuất), doanh thu ~22 tỷ/năm, 2 kế toán, ~30 NCC, ~320 HĐ/tháng (~11 HĐ/ngày), chi ~25–30 triệu/ngày** — tuyệt đối tránh đẩy chi tiêu trung bình ngày vượt trần tự chi `50 triệu/ngày` (D9).

**Bảng ước tính cơ cấu `~200 hóa đơn/tháng` cho Persona 5 quán (ghi rõ là giả định mô hình vận hành cho `sim-world`):**

| Nhóm chi phí | Quy tắc giao hàng & xuất HĐĐT | Công thức ước tính | Số HĐ/tháng | Giá trị điển hình/HĐ |
|---|---|---|---:|---:|
| Nguyên liệu giao thẳng từng quán (sữa tươi thanh trùng, đá viên sạch, bánh ngọt/trái cây tươi) | Giao 2–3 lần/tuần; NCC xuất HĐĐT theo tuần hoặc theo đợt giao cho từng điểm nhận | 5 quán × 3 NCC × ~2,5 HĐ/tháng | **~115** *(hoặc ~38 nếu gộp tuần, phần còn lại từ giao lẻ)* → chuẩn hóa: 5 quán × 3 NCC × 2 lần/tuần = **~120** | 1,2 – 6,5 triệu đ |
| Nguyên liệu pha chế & bao bì nhập lô (cà phê hạt rang, trà, si-rô, bột, sữa đặc, cốc nhựa/giấy, nắp, ống hút, túi) | Đặt theo lô 1–2 lần/tháng từ ~10 NCC chuyên biệt (khớp kịch bản cà phê 26,5tr, sữa hộp 31tr, cốc nhựa 22,4tr ở BRD §14) | 10 NCC × ~3,5 HĐ/tháng | **~35** | 8,0 – 32,0 triệu đ |
| Hóa đơn tiền điện (`EVNHCMC`) | 5 quán × 1 kỳ/tháng | 5 × 1 | **5** | 3,5 – 6,5 triệu đ |
| Hóa đơn tiền nước (`SAWACO` — 2–3 Công ty CP Cấp nước khu vực) | 5 quán × 1 kỳ/tháng | 5 × 1 | **5** | 0,6 – 1,0 triệu đ *(ca rò ống: 4,2 triệu đ)* |
| Internet, phần mềm POS/kế toán/SaaS, vệ sinh, bảo trì máy pha & máy lạnh, mua lẻ có HĐĐT | Định kỳ tháng + phát sinh sự vụ | 5 quán × internet + ~20 HĐ phần mềm/bảo trì/vật tư | **~30 – 35** | 0,3 – 12,0 triệu đ |
| **Tổng cộng** | | | **~195 – 200 HĐ/tháng** | **Tổng ~380 – 450 triệu/tháng** |

### 3.2. Bảng nguồn (`sources`) — Mục 3

| Nguồn (`url`) | Đơn vị phát hành (`publisher`) | Ngày văn bản / đăng (`date`) | Ngày truy cập (`retrieved_on`) | Phân loại |
|---|---|---|---|---|
| https://datafiles.chinhphu.vn/cpp/files/vbpq/2021/08/80.signed_01.pdf | Chính phủ (Cổng TTĐT Chính phủ) | 2021-08-26 | 2026-11-26 | Chính thức (PDF ký số `Nghị định 80/2021/NĐ-CP`, Điều 5–9 trang 4–6) |
| https://vanban.chinhphu.vn/default.aspx?pageid=27160&docid=203941 | Cổng Thông tin điện tử Chính phủ | 2021-08-26 | 2026-11-26 | Chính thức |
| https://vcci.com.vn/tin-tuc/thi-truong-fb-viet-nam-2026-huong-toi-doanh-thu-760000-ty-dong-quy-mo-333600-cua-hang | Liên đoàn Thương mại và Công nghiệp Việt Nam (VCCI) dẫn Báo cáo iPOS.vn × Nestlé × VIRAC (`n = 3.001` DN) | 2026-04-09 | 2026-11-26 | Chính thức / Báo cáo khảo sát ngành có kiểm định |
| https://www.vcci.com.vn/tin-tuc/doanh-nghiep-fb-nen-lam-gi-truoc-ap-luc-gia-nguyen-lieu-dat-do | VCCI dẫn báo cáo iPOS.vn (đã có ở BRD `[D1]`) | 2025–2026 | 2026-11-26 | Chính thức / Báo cáo khảo sát ngành (`44,8%` DN có food cost `≥ 30%`) |
| https://www.momo.vn/tin-tuc/thong-cao-bao-chi/bo-giai-phap-tai-chinh-tu-momo-giup-tieu-thuong-7891 | Tập đoàn Công nghệ Tài chính MoMo | 2025-07-11 | 2026-11-26 | Chính thức (khảo sát `203` DN nhỏ về vận hành/kế toán thủ công `[M3]`) |
| https://thoibaonganhang.vn/giai-phap-tai-chinh-so-toan-dien-cho-tieu-thuong-167188.html | Thời báo Ngân hàng (cơ quan ngôn luận NHNN) | 2025-07-12 | 2026-11-26 | Chính thức / Báo ngành ngân hàng |
| https://iglobal.com.vn/ke-toan-nha-hang-quan-an-huong-dan-chi-tiet-danh-cho-chu-kinh-doanh-fb-2026/ | iGlobal | 2026 | 2026-11-26 | **Thứ cấp** (tham khảo quy mô nhân sự kế toán theo chuỗi 5 / 10 / 15 quán) |
| https://www.cukcuk.vn/8061/ke-toan-nha-hang/ | MISA CukCuk | Không ghi rõ | 2026-11-26 | **Thứ cấp** (tham khảo nghiệp vụ kế toán chuỗi F&B) |

### 3.3. Khoảng trống còn lại (`gaps remaining`) — Mục 3

1. **Số lượng NCC và số hóa đơn đầu vào/tháng của chuỗi F&B 5–15 quán:** không tồn tại thống kê công khai; đội nên kiểm chứng nhanh bằng phỏng vấn 2–3 chủ chuỗi/kế toán F&B thật (đúng như BRD §12 đã ghi chú) và ghi rõ trong docs đây là giả định mô hình hóa.
2. **Hạn mức số dư và hạn mức giao dịch/ngày của tài khoản MoMo Doanh Nghiệp thực tế** (ngoài ngưỡng pháp lý TT 53/2026): chưa xác minh từ biểu phí/hợp đồng merchant của MoMo Doanh Nghiệp.

### 3.4. Đề xuất chỉnh sửa tài liệu hiện có (chỉ đề xuất, không tự sửa)

- **`docs/04-data/persona.md`:**
  - Bổ sung bảng ngưỡng Điều 5 `NĐ 80/2021/NĐ-CP` (dẫn link `vanban.chinhphu.vn` thay vì `luatvietnam.vn`).
  - Nếu đội đồng thuận theo khuyến nghị trên: cập nhật `persona.md` về **Chuỗi 5 quán cà phê & bánh nhẹ tại TP.HCM** (doanh thu `12–14 tỷ/năm`, `~20` LĐ BHXH, `1` kế toán bán thời gian/nội bộ, `~22` NCC, `~200` HĐ/tháng, chi `~380–450 triệu/tháng`) để khớp hoàn toàn với BRD, `problem-definition.md`, `architecture.md` và trần tự chi `D9` (`30tr/HĐ`, `50tr/ngày`).
- **`docs/01-requirements/PayMatch_BRD_v1.0.md` (§5.1 dòng 111):**
  - Chỉnh chi tiết *"doanh thu khoảng 8 tỷ/năm"* thành *"doanh thu khoảng 12 tỷ/năm (~200 triệu/quán/tháng, thuộc nhóm doanh nghiệp nhỏ theo NĐ 80/2021/NĐ-CP)"* để tránh rơi vào ngưỡng doanh nghiệp siêu nhỏ (`≤ 10 tỷ/năm` nếu `≤ 10` lao động BHXH).

---

## 4. Thiết kế hình dạng dữ liệu cho `utility_bills`, `utility_readings` và `/sim/bills`

Phần này chuyển hóa trực tiếp bố cục mẫu thật của **EVNHCMC** (Hóa đơn GTGT + Bảng kê chi tiết 3 giá / 1 giá) và **SAWACO** (Hóa đơn GTGT 2 dòng thuế suất 5% và 8%) thành cấu trúc dữ liệu chuẩn cho `core` (`utility_accounts`, `utility_readings`, tool `utility_bills` / `utility_baseline`) và `sim-world` (`GET /sim/bills`, XML đính kèm).

### 4.1. Ánh xạ hai tầng: Mặt Hóa đơn GTGT XML (`invoices` / `invoice_lines`) vs Chỉ số chi tiết (`utility_readings` / `utility_bills`)

| Khía cạnh | Điện kinh doanh 3 giá (`EVNHCMC`) | Điện kinh doanh 1 giá (`< 2.000 kWh`, công tơ 1 giá) | Nước kinh doanh dịch vụ (`SAWACO` — các CP Cấp nước) |
|---|---|---|---|
| `provider_kind` | `electricity` | `electricity` | `water` |
| `customer_code` (mẫu định dạng) | `PE` + 11 chữ số (`13` ký tự, ví dụ `PE01000123456`) | `PE` + 11 chữ số (`13` ký tự) | `11` chữ số Danh bộ (ví dụ `01103800123`) |
| `KHHDon` (mẫu 2026) | Không mã CQT: `K26Txx` (ghép `1K26TSG`) | Không mã CQT: `K26Txx` | Không mã CQT: `K26Txx` (ghép `1K26TBT`) |
| Số dòng `HHDVu` trên mặt XML GTGT | **01 dòng gộp**: `DVTinh = "kWh"`, `SLuong = total_kwh`, **`DGia = null`**, `ThTien = subtotal_vnd`, `TSuat = "8%"`, có `SBKe`/`NBKe` | **01 dòng**: `DVTinh = "kWh"`, `SLuong = total_kwh`, `DGia = 3089`, `ThTien = subtotal_vnd`, `TSuat = "8%"` | **02 dòng tách thuế suất**:<br>• Dòng 1: Nước sạch (`DVTinh = "m3"`, `DGia = 21300`, `TSuat = "5%"`)<br>• Dòng 2: DV thoát nước & XLNT (`DVTinh = "m3"`, `DGia = 6390`, `TSuat = "8%"`) |
| Phần chi tiết chỉ số & khung giờ nằm ở đâu? | Nằm ở **Bảng kê chi tiết** (`readings` của `/sim/bills` → lưu vào `core.utility_readings`) | Cùng 1 dòng chỉ số (`time_band = "all_day"`) | Nằm ở phần đầu hóa đơn/giấy báo (`CSC`, `CSM`, `LNTT`) → lưu vào `core.utility_readings` |

### 4.2. Bảng cấu trúc trường của `utility_accounts` và `utility_bills` (header kỳ hóa đơn)

| Bảng / Đối tượng | Tên trường (`field`) | Kiểu | Bắt buộc | Nguồn trên chứng từ thật & Ghi chú nghiệp vụ |
|---|---|---|---|---|
| `utility_accounts` | `utility_account_id` | `string` (UUID/ID) | Có | Khóa chính nội bộ PayMatch |
| `utility_accounts` | `tenant_id`, `store_id` | `string` | Có | Chi nhánh/quán gắn công tơ hoặc đồng hồ nước (`Địa chỉ sử dụng điện` / `Địa chỉ dùng nước`) |
| `utility_accounts` | `vendor_id` | `string` | Có | Trỏ tới NCC điện/nước đã xác minh trong `vendors` |
| `utility_accounts` | `utility_type` | `'electricity' \| 'water'` | Có | Khớp `provider` trong `GET /sim/bills` |
| `utility_accounts` | `customer_code` | `string` | Có | Mã KH `PE...` (13 ký tự) hoặc Số Danh Bộ (11 chữ số); dùng để khớp tự động hóa đơn về đúng `store_id` |
| `utility_accounts` | `tariff_code` | `string` | Có | Điện: `'KD_HA_AP_TOU'` hoặc `'KD_HA_AP_1GIA'` (`QĐ 2892` mục 3.3.2); Nước: `'KD_DV_HCM'` (`MGB = 31/32/33`) |
| `utility_accounts` | `voltage_or_meter_spec` | `string \| null` | Không | Điện: `'under_380v'` (`Dưới 380V`); Nước: cỡ đồng hồ `'15mm'` / `'25mm'` |
| `utility_bills` / `utility_readings` (kỳ) | `reading_id` / `bill_id` | `string` | Có | Khóa bản ghi kỳ điện/nước; trỏ `invoice_id` (nếu đã có hóa đơn XML/PDF) |
| `utility_bills` | `utility_account_id`, `store_id` | `string` | Có | Liên kết tài khoản điện/nước và chi nhánh |
| `utility_bills` | `billing_period` | `string` (`YYYY-MM`) | Có | Kỳ hóa đơn chuẩn hóa (từ `"Tháng 11/2026"` hoặc `"11/2026"`) |
| `utility_bills` | `period_start`, `period_end` | `date` (`YYYY-MM-DD`) | Có | `"từ ngày ... đến ngày ..."` (dùng để chuẩn hóa tiêu thụ theo ngày `usage / days` nếu kỳ đọc lệch 28 vs 33 ngày!) |
| `utility_bills` | `billing_days` | `integer` | Có | `period_end - period_start` (hoặc số ngày in trên bảng kê EVNHCMC, thường `28–32` ngày) |
| `utility_bills` | `due_date` | `date` | Có | `Hạn thanh toán` (~7 ngày sau ngày lập hóa đơn) |
| `utility_bills` | `statement_no` | `string \| null` | Không | `Số bảng kê` (`SBKe` trên hóa đơn điện EVNHCMC; `null` với nước) |
| `utility_bills` | `total_usage` | `numeric(12,2)` | Có | Tổng `kWh` hoặc tổng `m³` trong kỳ (dùng cho `utility_baseline` so 12 tháng trước và so `momo_revenue`) |
| `utility_bills` | `usage_unit` | `'kWh' \| 'm3'` | Có | Đơn vị đo lường vật lý |
| `utility_bills` | `subtotal_vnd` | `bigint` | Có | Tổng tiền chưa thuế GTGT (đồng) |
| `utility_bills` | `vat_total_vnd` | `bigint` | Có | Tổng tiền thuế GTGT (đồng) |
| `utility_bills` | `total_vnd` | `bigint` | Có | Tổng thanh toán = `subtotal_vnd + vat_total_vnd` |

### 4.3. Bảng dòng chi tiết (`utility_line_items` — dùng chung cho `utility_readings.lines` và `utility_bills.lines`)

Mỗi kỳ hóa đơn điện hoặc nước tách thành các dòng có cấu trúc đồng nhất dưới đây để **code** kiểm tra công thức `(new_index - old_index) × multiplier = usage` và `round(usage × unit_price_vnd) = amount_vnd`:

| `utility_type` | `line_code` | Tên hiển thị trên hóa đơn/bảng kê (`description_vi`) | `meter_serial` | `time_band` | `old_index` | `new_index` | `multiplier` | `usage` | `unit` | `unit_price_vnd` | `amount_vnd` | `vat_rate_pct` | `vat_amount_vnd` | Ví dụ mẫu khớp số thật 2026 |
|---|---|---|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---|
| `electricity` (3 giá TOU) | `ELEC_TOU_NORMAL` | Điện kinh doanh hạ áp – Khung giờ bình thường | `'17179320'` | `'normal'` | `14200` | `15040` | `1` | `840` | `'kWh'` | `3089` | `2594760` | `8` | *(tính gộp ở mức thuế suất 8%: `344117`)* | Quán cà phê 35 m² (`1.200 kWh/tháng`): tổng chưa thuế `4.301.460 đ`, VAT 8% `344.117 đ`, **tổng trả `4.645.577 đ`** |
| `electricity` (3 giá TOU) | `ELEC_TOU_PEAK` | Điện kinh doanh hạ áp – Khung giờ cao điểm | `'17179320'` | `'peak'` | `5100` | `5400` | `1` | `300` | `'kWh'` | `5313` | `1593900` | `8` | *(gộp trên)* | *(như trên — 17:30–22:30 T2–T7)* |
| `electricity` (3 giá TOU) | `ELEC_TOU_OFFPEAK` | Điện kinh doanh hạ áp – Khung giờ thấp điểm | `'17179320'` | `'off_peak'` | `1820` | `1880` | `1` | `60` | `'kWh'` | `1880` | `112800` | `8` | *(gộp trên)* | *(như trên — 00:00–06:00 chạy tủ mát/đông)* |
| `electricity` *(tùy chọn)* | `ELEC_REACTIVE_INFO` | Điện năng phản kháng (`cosφ ≥ 0,9`, `K% = 0`) | `'17179320'` | `null` | `358` | `380` | `1` | `22` | `'kVArh'` | `0` | `0` | `8` | `0` | Chỉ ghi nhận thông tin nếu mô phỏng công tơ 3 pha; quán `< 40 kW` luôn `amount_vnd = 0` |
| `electricity` (1 giá `< 2.000 kWh`) | `ELEC_SINGLE_NORMAL` | Điện kinh doanh hạ áp – Công tơ 1 giá (toàn thời gian) | `'19486377'` | `'all_day'` | `6200` | `7300` | `1` | `1100` | `'kWh'` | `3089` | `3397900` | `8` | `271832` | Quán nhỏ công tơ 1 giá: tổng trả **`3.669.732 đ`** |
| `water` (SAWACO KD-DV) | `WATER_SUPPLY_BIZ` | Tiền nước sạch (Kinh doanh dịch vụ) | `'WM0301123'` | `null` | `612` | `636` | `1` | `24` | `'m3'` | `21300` | `511200` | `5` | `25560` | Quán bình thường `24 m³`: cộng dòng DVTN bên dưới → **tổng trả `702.389 đ`** (~700 nghìn BRD §3.1) |
| `water` (SAWACO KD-DV) | `WASTEWATER_SERVICE_30PCT` | Tiền dịch vụ thoát nước và xử lý nước thải (30% giá nước sạch) | `'WM0301123'` | `null` | `null` *(dùng lại `usage` dòng nước sạch)* | `null` | `1` | `24` | `'m3'` | `6390` | `153360` | `8` | `12269` | `153.360 × 8% = 12.268,8 → 12.269 đ`. Ca rò ống `144 m³` (6×): `3.067.200 + 153.360 + 920.160 + 73.613` = **`4.214.333 đ`** (~4,2 triệu BRD §14) |

### 4.4. Bất biến kiểm tra bằng code trên `utility_bills` / `utility_readings` (gợi ý cho `ingest` và `utility_baseline`)

1. **Khớp chỉ số công tơ / đồng hồ:** với mọi dòng có `old_index` và `new_index`: `(new_index - old_index) × multiplier == usage` (`new_index >= old_index`, trừ trường hợp thay/quay vòng công tơ phải có cờ ghi chú).
2. **Khớp đơn giá biểu giá nhà nước:** với tài khoản hạ áp kinh doanh tại TP.HCM kỳ từ `01/11/2026` đến `31/12/2026`, đơn giá trên bảng kê phải khớp bảng hằng cấu hình (`3089 / 5313 / 1880` đ/kWh cho điện; `21300` và `6390` đ/m³ cho nước); thuế suất khớp `8%` (điện, thoát nước) và `5%` (nước sạch).
3. **Chuẩn hóa theo số ngày kỳ đọc (`billing_days`) khi tính `utility_baseline`:** kỳ ghi điện/nước thực tế có thể dao động từ `27` đến `34` ngày (hoặc gộp kỳ khi đổi lịch ghi chỉ số, như mẫu thật EVNHCMC có kỳ 42 ngày). Do đó `utility_baseline` nên so sánh cả **`total_usage` theo kỳ** lẫn **mức tiêu thụ bình quân ngày (`daily_usage = total_usage / billing_days`)** kết hợp doanh thu QR MoMo cùng kỳ để tránh báo nhầm `UTILITY_OUT_OF_RANGE` chỉ vì kỳ ghi dài ngày hơn bình thường.
