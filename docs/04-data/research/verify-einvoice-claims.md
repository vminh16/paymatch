# Kiểm chứng độc lập các khẳng định trong `einvoice-and-tax.md` (§2a–2d, §3a)

- **Ngày kiểm chứng (`retrieved_on`):** `2026-11-26`
- **Đối tượng kiểm chứng:** Các khẳng định của worker Neon trong [einvoice-and-tax.md](einvoice-and-tax.md) (§2a–2d và §3a).
- **Phương pháp:** Tải và đọc trực tiếp văn bản gốc ký số từ Cổng TTĐT Chính phủ (`vanban.chinhphu.vn` / `datafiles.chinhphu.vn`) và bản PDF ký số 423 trang của `QĐ 1233/QĐ-CT` (`Ký bởi: CỤC THUẾ, Thời gian ký: 28/08/2026 10:29:35+07:00`), đồng thời đối chiếu trực tiếp từng thẻ XML hóa đơn GTGT giữa `QĐ 1233/QĐ-CT` (27/08/2026) và `QĐ 1271/QĐ-CT` (30/05/2025, `docs/04-data/references/QD-1271-QD-CT-2025.pdf`).

---

## Bảng tổng hợp kết luận từng khẳng định (`Verdicts`)

| Mã | Khẳng định của Neon trong `einvoice-and-tax.md` | Kết luận | Tóm tắt bằng chứng gốc & đính chính/bổ sung |
|---|---|---|---|
| **1a** | `QĐ 1271/QĐ-CT` (30/05/2025) bị thay thế bởi `QĐ 1306/QĐ-CT` (13/06/2025), sau đó bị thay thế bởi `QĐ 1233/QĐ-CT` (27/08/2026) dưới `NĐ 254/2026/NĐ-CP` và `TT 91/2026/TT-BTC` | **CONFIRMED** | Xác minh trực tiếp `NĐ 254/2026/NĐ-CP` (`254-ndcp.signed.pdf`), `TT 91/2026/TT-BTC` (`91-btc.signed.pdf`), bản Quy định 423 trang ký số của `QĐ 1233/QĐ-CT` (`28/08/2026 10:29:35+07:00`), và Điều 2 của `QĐ 1233/QĐ-CT` & `QĐ 1306/QĐ-CT` (lưu ý: trang bìa 2 trang của Quyết định `1233/QĐ-CT` chưa được đăng bản PDF ký số trên `gdt.gov.vn`/`vanban.chinhphu.vn`, chỉ có văn bản trích dẫn trên `dulieuphapluat.vn` & `ketoanbaoloc.com`). |
| **1b** | `PBan = 2.1.1` được tiếp nhận song song với `2.1.0` đến hết `31/12/2026` | **CONFIRMED** | `PBan = 2.1.1` (độ dài `6`, bắt buộc) xác minh trực tiếp trong PDF ký số `QĐ 1233/QĐ-CT` (trang 7 và trang 95). Mốc chuyển tiếp song song `2.1.0`/`2.1.1` đến hết `31/12/2026` (hoàn thành trước `01/01/2027`) nằm tại Điều 2 `QĐ 1233/QĐ-CT`. |
| **1c** | Bổ sung thẻ mới `MSTCLQuan` trong `TTHDLQuan` | **CONFIRMED** *(nhưng Neon bỏ sót 16 thẻ GTGT mới khác & 3 mã `TSuat` mới)* | Xác minh trực tiếp `MSTCLQuan` (chuỗi, tối đa `14`, đặt ngay sau `TCHDon`) tại trang 97–98 PDF ký số `QĐ 1233/QĐ-CT`. Tuy nhiên `QĐ 1233/QĐ-CT` bổ sung thêm nhiều thẻ quan trọng khác như `LDDCTThe`, `MDDKDoanh`/`TDDKDoanh`/`DCDDKDoanh`, `MTinh`/`TTinh`/`MXa`/`TXa`, `MQTNMua`/`QTNMua`/`SDDTCNNgoai`, `LHDCLQuan = 5`, `TSuat` thêm `CTTC`/`KTPVDC`/`KTGTT` (xem Mục 1.2). |
| **1d** | Chữ ký số chuyển sang chuẩn `XAdES`, tiếp nhận song song `DSig` đến hết `09/04/2027` | **CONFIRMED** | Chuẩn `XAdES` (`ETSI EN 319 132-1 V1.2.1`, `xades:QualifyingProperties`/`xades:SignedProperties`/`xades:SigningTime`/`xades:SigningCertificate`) xác minh trực tiếp tại Phần I mục IV.4 (trang 5–6) và phần `DSCKS` (trang 110) của PDF ký số `QĐ 1233/QĐ-CT`. Mốc `DSig` đến hết `09/04/2027` (hoàn thành trước `10/04/2027`) nằm tại Điều 2 `QĐ 1233/QĐ-CT`. |
| **2a** | `KHHDon` ký tự thứ 4 gồm **10 chữ cái** (`T, D, L, M, N, B, G, H, X, F`) | **CONFIRMED** | Đọc trực tiếp ảnh scan bản ký số `91-btc.signed.pdf` (`TT 91/2026/TT-BTC`, Phụ lục I, Mục 2, trang 34–35): liệt kê đúng 10 chữ cái `T, D, L, M, N, B, G, H, X, F` (`X`: hóa đơn thương mại điện tử; `F`: hóa đơn GTGT kiêm tờ khai hoàn thuế). Bổ sung làm rõ cho khoảng trống của Neon: 2 ký tự cuối (vị trí 5–6) chỉ quy định *"là chữ viết do người bán tự xác định"* (hoặc `YY`), **không** ghi danh sách loại trừ 20 chữ cái như đối với biên lai điện tử (Phụ lục II, trang 38). |
| **2b** | `KHMSHDon` bổ sung thêm `7, 8, 9` | **CONFIRMED** | Xác minh kép trực tiếp từ cả `91-btc.signed.pdf` (Phụ lục I, Mục 1, trang 34) và PDF ký số `QĐ 1233/QĐ-CT` (Phụ lục II, Mục 1): `7` = Hóa đơn thương mại điện tử; `8` = HĐĐT GTGT tích hợp biên lai thu thuế, phí, lệ phí; `9` = HĐĐT bán hàng tích hợp biên lai thu thuế, phí, lệ phí. |
| **3** | Danh mục trạng thái MST gồm 10 mã `00, 01, 02, 03, 04, 05, 06, 07, 09, 10` (không có `08`) theo `TT 86/2024/TT-BTC` và `TT 90/2026/TT-BTC` | **CONFIRMED** *(kèm 1 lưu ý quan trọng về mã `04`)* | Đọc trực tiếp file gốc Bộ Tài chính `1.1.PL1-Trạng thái MST.doc` trong `90-btc.rar` (`vanban.chinhphu.vn`, `docid=218839`) và Báo Điện tử Chính phủ (`14/09/2026`): đúng 10 mã `00, 01, 02, 03, 04, 05, 06, 07, 09, 10`, không có trạng thái `08` (`08` là mã lý do *"Đã phá sản"* thuộc trạng thái `01`). **Điểm bổ sung quan trọng Neon chưa ghi nhận:** trong Phụ lục I gốc của `TT 90/2026/TT-BTC`, riêng trạng thái **`04`** được ghi chú trực tiếp là **`"Hết hiệu lực"`** và không còn mã lý do con. |

---

## 1. Kiểm chứng Khẳng định 1 (`QĐ 1306/QĐ-CT`, `QĐ 1233/QĐ-CT`, `PBan 2.1.1`, `MSTCLQuan`, `XAdES`) & Bảng diff XML chi tiết `QĐ 1233` vs `QĐ 1271`

### 1.1. Bằng chứng văn bản gốc

- **Bản PDF ký số của Quy định kèm theo `QĐ 1233/QĐ-CT`:** Tải được toàn văn **423 trang** (`sha256: 9efe003ce2f5a485...`, chữ ký số `Ký bởi: CỤC THUẾ`, `Thời gian ký: 28/08/2026 10:29:35+07:00`, tiêu đề: *"QUY ĐỊNH Về thành phần chứa dữ liệu nghiệp vụ hóa đơn điện tử, chứng từ điện tử và phương thức truyền nhận với cơ quan thuế — Ban hành kèm theo Quyết định số 1233/QĐ-CT ngày 27 tháng 8 năm 2026 của Cục trưởng Cục Thuế"*).
- **Căn cứ pháp lý trong Phần I mục I–III (trang 1–3) của `QĐ 1233/QĐ-CT`:** Dẫn chiếu trực tiếp `Luật Quản lý thuế số 108/2025/QH15`, `Nghị định 254/2026/NĐ-CP` (30/06/2026), `Thông tư 91/2026/TT-BTC` (30/06/2026), `Nghị định 23/2025/NĐ-CP` (21/02/2025 về chữ ký điện tử) và `Thông tư 15/2025/TT-BKHCN` (yêu cầu kỹ thuật phần mềm ký số).
- **Điều 2 Quyết định `1233/QĐ-CT` (27/08/2026, Phó Cục trưởng Mai Sơn ký — trích từ `dulieuphapluat.vn` và `ketoanbaoloc.com`, chưa có bản PDF ký số riêng cho 2 trang Quyết định trên cổng Cục Thuế):**
  - Có hiệu lực kể từ ngày ký (`27/08/2026`), **thay thế Quyết định số `1306/QĐ-CT` ngày 13/06/2025** của Cục trưởng Cục Thuế.
  - Lộ trình chuyển tiếp: hệ thống thông tin quản lý thuế nâng cấp hoàn thành trước `01/01/2027`, tiếp nhận song song phiên bản `2.1.0` và `2.1.1` (**`2.1.0` đến hết ngày `31/12/2026`**); hệ thống ký số nâng cấp hoàn thành trước `10/04/2027`, tiếp nhận song song `DSig` và `XAdES` (**`DSig` đến hết ngày `09/04/2027`**).
- **Chữ ký số `XAdES` trong Phần I mục IV.4 (trang 5–6) của `QĐ 1233/QĐ-CT`:**
  - Quy định chuẩn chữ ký số cho XML là **`ETSI EN 319 132-1 V1.2.1`** (XAdES), mật mã RSA, hàm băm `SHA-256` / `SHA-384` / `SHA-512`.
  - Thẻ thời điểm ký đổi vị trí từ `Signature/Object/SignatureProperties/SignatureProperty/SigningTime` (`QĐ 1271`) sang **`ds:Signature/ds:Object/xades:QualifyingProperties/xades:SignedProperties/xades:SignedSignatureProperties/xades:SigningTime`** (có thuộc tính `Target="#<Signature/@Id>"` trên `xades:QualifyingProperties`, một thẻ `Reference` trỏ tới `#<SignedProperties/@Id>`, và bắt buộc ràng buộc chứng thư qua `xades:SigningCertificate/xades:Cert/{xades:CertDigest, xades:IssuerSerial}`).

### 1.2. Danh sách đầy đủ các thay đổi XML Hóa đơn GTGT giữa `QĐ 1233/QĐ-CT` (27/08/2026) và `QĐ 1271/QĐ-CT` (30/05/2025)

Đối chiếu trực tiếp bảng thẻ **Hóa đơn GTGT** (`QĐ 1271` trang 89–100 vs `QĐ 1233` trang 95–110) và các Phụ lục kèm theo:

#### a) Thẻ XML thêm mới trong `HDon\DLHDon` (Hóa đơn GTGT)

| Nhánh cha trong `HDon\DLHDon` | Tên thẻ mới (`QĐ 1233`) | Độ dài tối đa | Kiểu dữ liệu | Ràng buộc & Ý nghĩa |
|---|---|---:|---|---|
| `TTChung\TTHDLQuan` | **`MSTCLQuan`** | `14` | Chuỗi | **Bắt buộc** khi lập HĐ điều chỉnh/thay thế cho HĐ đã lập của đơn vị bị chia, tách, sáp nhập, hợp nhất. Đặt ngay sau `TCHDon`. |
| `TTChung\TTHDLQuan` | **`LDDCTThe`** | `2` | Số | **Bắt buộc** khi điều chỉnh/thay thế cho 1 hóa đơn (mã `1..14` tại **Phụ lục XVII** mới — ví dụ `4`: chiết khấu thương mại, `5`: trả lại hàng hóa, `13`: điều chỉnh/thay thế HĐ lập sai, `14`: thay thế HĐ MTT lập sai). Đặt ngay trước `GChu`. |
| `NDHDon\NBan` | **`TCQDGBTSan`** | `400` | Chuỗi | Không bắt buộc — Tên cơ quan được giao bán đấu giá tài sản (Điểm 3 Phụ lục NĐ 254). |
| `NDHDon\NBan` | **`DCCQDGBTSan`** | `400` | Chuỗi | Không bắt buộc — Địa chỉ cơ quan được giao bán đấu giá tài sản. |
| `NDHDon\NBan` | **`MSTCQDGBTSan`** | `14` | Chuỗi | Không bắt buộc — MST cơ quan được giao bán đấu giá tài sản. |
| `NDHDon\NBan` | **`MDDKDoanh`** | `14` | Chuỗi | Bắt buộc đối với DN có mã địa điểm kinh doanh xăng dầu — Mã địa điểm kinh doanh. |
| `NDHDon\NBan` | **`TDDKDoanh`** | `400` | Chuỗi | Không bắt buộc — Tên địa điểm kinh doanh. |
| `NDHDon\NBan` | **`DCDDKDoanh`** | `400` | Chuỗi | Bắt buộc đối với DN có nhiều địa điểm kinh doanh xăng dầu — Địa chỉ địa điểm kinh doanh. |
| `NDHDon\NMua` | **`MTinh`** | `2` | Chuỗi | Bắt buộc với hàng hóa đặc trưng 1 (`LHHDTrung = 1`) — Mã tỉnh/TP theo QĐ 19/2025/QĐ-TTg. |
| `NDHDon\NMua` | **`TTinh`** | `50` | Chuỗi | Bắt buộc với `LHHDTrung = 1` — Tên tỉnh/TP. |
| `NDHDon\NMua` | **`MXa`** | `5` | Chuỗi | Bắt buộc (nếu có / với `LHHDTrung = 1`) — Mã xã/phường theo QĐ 19/2025/QĐ-TTg. |
| `NDHDon\NMua` | **`TXa`** | `50` | Chuỗi | Bắt buộc với `LHHDTrung = 1` — Tên xã/phường. |
| `NDHDon\NMua` | **`SDDTCNNgoai`** | `50` | Chuỗi | Không bắt buộc — Số định danh tổ chức nước ngoài. |
| `NDHDon\NMua` | **`MQTNMua`** | `2` | Chuỗi | Bắt buộc khi người mua là người nước ngoài cung cấp thông tin — Mã quốc tịch người mua (Phụ lục XIX). |
| `NDHDon\NMua` | **`QTNMua`** | `50` | Chuỗi | Bắt buộc khi người mua là người nước ngoài cung cấp thông tin — Quốc tịch của người mua (Phụ lục XIX). |
| `HDon` (ngang cấp `DLHDon`) | **`DSHDGiay\DLHDGiay`** | *(nhóm thẻ)* | Nhóm | Khối mới chứa thông tin hóa đơn giấy theo NĐ 51/2010, NĐ 04/2014 bị thay thế (bên trong có `KHMSHDon` tối đa `11`, `KHHDon` tối đa `8`, `SHDon` tối đa `7`, `NBan`, `NMua`, `TToan`). |
| `HDon\DSCKS\*` | **`ds:Signature\ds:Object\xades:QualifyingProperties`** | *(nhóm thẻ)* | XAdES | Cấu trúc chữ ký số nâng cao `XAdES` (`ETSI EN 319 132-1 V1.2.1`) thay cho `SignatureProperties/SignatureProperty/SigningTime` cũ. |

#### b) Thẻ bị xóa / đổi tên / thay đổi độ dài / thay đổi giá trị danh mục (`Enum`)

- **Thẻ bị xóa hoặc đổi tên trong `HDon\DLHDon` (Hóa đơn GTGT):** **KHÔNG CÓ** (0 thẻ bị xóa, 0 thẻ bị đổi tên).
- **Thay đổi độ dài tối đa trên 57 thẻ dùng chung của `HDon\DLHDon`:** **KHÔNG CÓ** (`PBan=6`, `KHMSHDon=1`, `KHHDon=6`, `SHDon=8`, `MST=14`, `SLuong/DGia/ThTien/TgTCThue/TgTThue/TgTTTBSo=21,6`, `TSuat=11`, `MCCQT=34` đều giữ nguyên độ dài; các giá trị `KHMSHDon=11`, `KHHDon=8`, `SHDon=7` chỉ xuất hiện ở khối mới `HDon\DSHDGiay\DLHDGiay`).
- **Thay đổi giá trị cố định & Danh mục (`Phụ lục`):**
  1. **`PBan`:** Đổi từ `"2.1.0"` sang **`"2.1.1"`**.
  2. **Phụ lục II (`KHMSHDon`):** Thêm **`7`**, **`8`**, **`9`** (tổng 9 loại thay vì 6).
  3. **Phụ lục III (`KDLieu` trong `TTKhac`):** Đổi cách viết hoa ở 3/4 giá trị từ `string, numeric, dateTime, date` (`QĐ 1271`) sang **`String, Numeric, dateTime, Date`** (`QĐ 1233`) → bộ ingest **bắt buộc** so sánh `KDLieu` không phân biệt hoa/thường (`case-insensitive`).
  4. **Phụ lục V (`TSuat`):** Thêm **3 mã mới** ngoài 7 mã cũ (`0%`, `5%`, `8%`, `10%`, `KCT`, `KKKNT`, `KHAC:AB.CD%`/`KHAC`):
     - **`CTTC`**: Thuế suất của hóa đơn cho thuê tài chính;
     - **`KTPVDC`**: Không thuộc phạm vi điều chỉnh của Luật thuế;
     - **`KTGTT`**: Không tính vào giá tính thuế GTGT.
  5. **Phụ lục VI (`LHDCLQuan`):** Thêm giá trị **`5`** = **`Hóa đơn điện tử theo Nghị định 254/2026/NĐ-CP`** (giá trị `1` vẫn là NĐ 123/2020 & NĐ 70/2025).
  6. **Phụ lục XV (`LHHDTrung` trong `HHDVu\TTHHDTrung`):**
     - `LHHDTrung = 1` (ô tô, mô tô): mở rộng từ **2 trường** (`SKhung`, `SMay`) lên **17 trường** (`SKhung`, `SMay`, `LTSan`, `TTTSan`, `XXu`, `SGCNATKThuat`, `SSPKTCLXXuong`, `MNSXuat`, `TLTSDKy`, `NSXuat`, `TTMai`, `TNHieu`, `KLXe`, `TTLVHCSuat`, `TTai`, `SCNgoi`, `SBKSoat`).
     - `LHHDTrung = 2` (dịch vụ vận chuyển): bổ sung thêm `DDi` (Điểm đi), `DDen` (Điểm đến), `THHVChuyen` (Tên hàng hóa vận chuyển) ngoài `BKSPTVChuyen`.
     - Thêm mới **`LHHDTrung = 4`** (*Hàng hóa phải đăng ký quyền sử dụng, quyền sở hữu*: `TTTDat`, `TTTSGLTDat`).
  7. **Ràng buộc mới trên `TTHDLQuan`:** Các thẻ `LHDCLQuan`, `KHMSHDCLQuan`, `KHHDCLQuan`, `SHDCLQuan`, `NLHDCLQuan` bổ sung ngoại lệ *"Trừ trường hợp lý do 1, 2, 3, 9, 10, 12 tại Phụ lục XVII Quy định này"*.
  8. **Bổ sung 4 Phụ lục mới:** `Phụ lục XVI` (Danh mục đơn vị tiền tệ), `Phụ lục XVII` (14 mã lý do điều chỉnh/thay thế cho `LDDCTThe`), `Phụ lục XVIII` (Danh mục nhóm ngành nghề), `Phụ lục XIX` (Danh mục mã quốc tịch/nước sản xuất).

---

## 2. Kiểm chứng Khẳng định 2 (`KHHDon` 10 chữ cái vị trí 4 & `KHMSHDon` thêm `7, 8, 9`)

- **Kết luận:** **CONFIRMED** cho cả hai vế.
- **Bằng chứng gốc trực tiếp:** Đọc ảnh scan bản ký số chính thức **`91-btc.signed.pdf`** (`Thông tư số 91/2026/TT-BTC` ngày 30/06/2026 của Bộ trưởng Bộ Tài chính, hiệu lực `01/07/2026`, lưu trên `datafiles.chinhphu.vn`, trang **34–36** — **Phụ lục I: KÝ HIỆU MẪU, KÝ HIỆU HÓA ĐƠN**):
  1. **Mục 1 (trang 34) — Ký hiệu mẫu số hóa đơn (`KHMSHDon`):** Quy định đúng 9 số từ `1` đến `9`, trong đó:
     - `Số 7`: Phản ánh hóa đơn thương mại điện tử;
     - `Số 8`: Phản ánh loại hóa đơn điện tử giá trị gia tăng tích hợp biên lai thu thuế, phí, lệ phí;
     - `Số 9`: Phản ánh loại hóa đơn điện tử bán hàng tích hợp biên lai thu thuế, phí, lệ phí.
  2. **Mục 2 (trang 34–35) — Sáu ký tự hóa đơn điện tử (`KHHDon`):**
     - Ký tự 1: `C` (có mã CQT) hoặc `K` (không có mã CQT).
     - Ký tự 2–3: 2 chữ số Ả-rập thể hiện năm lập (ví dụ `26` cho năm 2026).
     - **Ký tự 4:** Đúng **10 chữ cái**: **`T, D, L, M, N, B, G, H, X, F`**, trong đó `+ Chữ X: Áp dụng đối với hóa đơn thương mại điện tử;` và `+ Chữ F: Áp dụng đối với hóa đơn giá trị gia tăng kiêm tờ khai hoàn thuế.`
     - **Ký tự 5–6 (làm rõ khoảng trống mà Neon để "chưa xác minh"):** Trang 35 `91-btc.signed.pdf` ghi nguyên văn: *"Hai ký tự cuối là chữ viết do người bán tự xác định căn cứ theo nhu cầu quản lý... Trường hợp không có nhu cầu quản lý thì sử dụng hai ký tự YY."* — văn bản **không** giới hạn 20 chữ cái cho `KHHDon` của hóa đơn (tập 20 chữ cái `A,B,C,D,E,G,H,K,L,M,N,P,Q,R,S,T,U,V,X,Y` chỉ áp cho **biên lai điện tử** tại Phụ lục II, trang 38). Vì văn bản quy định *"là chữ viết"*, regex nghiêm ngặt cho `KHHDon` là `^[CK]\d{2}[TDLMNBGHXF][A-Z]{2}$` (regex `[A-Z0-9]{2}` của Neon hơi rộng hơn luật ở 2 ký tự cuối).

---

## 3. Kiểm chứng Khẳng định 3 (10 mã trạng thái MST `00..10`, không có `08` dưới `TT 86/2024` và `TT 90/2026`)

- **Kết luận:** **CONFIRMED** (có **1 lưu ý nghiệp vụ quan trọng** về mã `04` dưới `TT 90/2026/TT-BTC`).
- **Bằng chứng gốc trực tiếp:** Giải nén và đọc nguyên văn tệp **`1.1.PL1-Trạng thái MST.doc`** trong gói đính kèm chính thức `90-btc.rar` của **`Thông tư số 90/2026/TT-BTC`** (ban hành `30/06/2026`, hiệu lực `01/07/2026`, thay thế `TT 86/2024/TT-BTC`) trên `vanban.chinhphu.vn` (`docid=218839`), đối chiếu với bài đăng ngày `14/09/2026` trên `baochinhphu.vn`:
  - Danh mục có đúng **10 mã trạng thái cấp 1:** **`00, 01, 02, 03, 04, 05, 06, 07, 09, 10`**.
  - **Không tồn tại mã trạng thái `08`:** Mã `08` chỉ xuất hiện ở cột **`Mã lý do`** (*"Đã phá sản"*) trực thuộc trạng thái `01`.
  - **Chi tiết quan trọng mà `einvoice-and-tax.md` chưa ghi nhận:** Trong Phụ lục I gốc của `TT 90/2026/TT-BTC`, dòng trạng thái **`04`** (*"NNT đang hoạt động (áp dụng cho hộ kinh doanh, cá nhân kinh doanh chưa đủ thông tin đăng ký thuế)"*) được ghi rõ ở cột nội dung là **`"Hết hiệu lực"`** và không còn mã lý do con nào (do quy định đồng bộ số định danh cá nhân thay MST đã có hiệu lực).
  - Các mã lý do chính đã xác minh trực tiếp từ file gốc `TT 90/2026/TT-BTC`:
    - `00`: `01` (Chưa đi vào hoạt động), `02` (Đang hoạt động), `03` (Cá nhân chưa phát sinh nghĩa vụ thuế).
    - `01`: `03` (Tổ chức lại), `04` (Cá nhân chết/mất tích), `07` (Giải thể/chấm dứt), `08` (Đã phá sản), `18` (Tổ chức khác/HKD/CNKD), `21` (HKD chuyển lên DNNVV).
    - `02`: `01` (Đã hoàn thành thủ tục nơi đi, chờ nơi đến).
    - `03`: `03`, `04`, `07`, `11`, `12`, `13`, `15`, `17`, `19`, `21` (đang làm thủ tục chấm dứt / bị thu hồi giấy phép / cưỡng chế nợ thuế).
    - `04`: *(Hết hiệu lực)*.
    - `05`: `01` (Tạm ngừng trong thời hạn được chấp thuận).
    - `06`: `03`, `07`, `09` (CQT ban hành Thông báo không hoạt động tại địa chỉ đã đăng ký), `12`, `13`, `17` (đơn vị phụ thuộc có đơn vị chủ quản bị trạng thái `06`).
    - `07`: `01` (Tòa án ban hành QĐ mở thủ tục phá sản).
    - `09`: `01`..`07` (đúng đủ 7 lý do cảnh báo sớm như Neon mô tả).
    - `10`: `01` (Chưa khớp CSDLQGDC).

---

## 4. Bảng nguồn kiểm chứng (`sources`)

| URL | Đơn vị phát hành (`publisher`) | Ngày văn bản / đăng (`date`) | `retrieved_on` | Vai trò kiểm chứng |
|---|---|---|---|---|
| https://laphoadon.htinvoice.vn/DownloadFile/QD%201233_Quy%20dinh%20chuan%20DL%20HD%20CT%20.pdf | Cục Thuế (bản PDF Quy định 423 trang ký số `28/08/2026 10:29:35+07:00`, lưu trữ bởi HTInvoice) | 2026-08-27 | 2026-11-26 | **Primary** — đối chiếu toàn bộ thẻ XML GTGT `QĐ 1233`, `PBan 2.1.1`, `MSTCLQuan`, `LDDCTThe`, `XAdES`, Phụ lục II–XIX |
| `docs/04-data/references/QD-1271-QD-CT-2025.pdf` | Cục Thuế (lưu cục bộ trong repo) | 2025-05-30 | 2026-11-26 | **Primary** — mốc so sánh diff XML với `QĐ 1233/QĐ-CT` |
| https://vanban.chinhphu.vn/?pageid=27160&docid=219006 và https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/7/91-btc.signed.pdf | Cổng TTĐT Chính phủ (`Thông tư 91/2026/TT-BTC`, bản PDF ký số 97 trang) | 2026-06-30 | 2026-11-26 | **Primary** — xác minh trực tiếp Phụ lục I (`KHMSHDon` 1–9, `KHHDon` 10 chữ cái `T,D,L,M,N,B,G,H,X,F`, quy tắc ký tự 5–6) |
| https://vanban.chinhphu.vn/?pageid=27160&docid=218689 và https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/7/254-ndcp.signed.pdf | Cổng TTĐT Chính phủ (`Nghị định 254/2026/NĐ-CP`, bản PDF ký số 55 trang) | 2026-06-30 | 2026-11-26 | **Primary** — xác minh văn bản gốc thay thế NĐ 123/2020 & NĐ 70/2025 |
| https://vanban.chinhphu.vn/?pageid=27160&docid=218839 và https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/7/90-btc.rar | Cổng TTĐT Chính phủ (`Thông tư 90/2026/TT-BTC`, file `1.1.PL1-Trạng thái MST.doc`) | 2026-06-30 | 2026-11-26 | **Primary** — xác minh toàn bộ 10 mã trạng thái MST (`00..10`, không có `08`), mã lý do và trạng thái `"Hết hiệu lực"` của mã `04` |
| https://vanban.chinhphu.vn/?pageid=27160&docid=212208 và https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/01/86-btc.pdf | Cổng TTĐT Chính phủ (`Thông tư 86/2024/TT-BTC`) | 2024-12-23 | 2026-11-26 | **Primary** — văn bản tiền nhiệm của `TT 90/2026/TT-BTC` |
| https://baochinhphu.vn/10-trang-thai-ma-so-thue-can-biet-102260915153506424.htm | Báo Điện tử Chính phủ | 2026-09-14 | 2026-11-26 | **Primary / Báo Chính phủ** — xác minh chéo 10 mã trạng thái MST |
| https://dulieuphapluat.vn/van-ban/thue-phi-le-phi-van-ban/quyet-dinh-1233qd-ct-nam-2026-ve-quy-dinh-thanh-phan-chua-du-lieu-nghiep-vu-hoa-don-chung-tu-dien-tu-va-phuong-thuc-truyen-nhan-voi-co-quan-thue-do-cuc-truong-cuc-thue-ban-hanh-1840173.html | Dữ liệu Pháp luật (trích toàn văn 3 Điều của Quyết định `1233/QĐ-CT`) | 2026-08-27 | 2026-11-26 | **Secondary** — xác minh nguyên văn Điều 2 (`1306/QĐ-CT`, `31/12/2026`, `09/04/2027`) do chưa có PDF ký số 2 trang bìa trên `gdt.gov.vn` |
| https://ketoanbaoloc.com/van-ban-phap-luat/qd-1233-qd-ct | Kế toán Bảo Lộc | 2026-10-24 | 2026-11-26 | **Secondary** — đối chiếu chéo Điều 2 `QĐ 1233/QĐ-CT` và ghi nhận Cục Thuế chưa đăng bản gốc lên cổng công khai |

---

## 5. Đề xuất bổ sung cho `docs/04-data/einvoice-xml.md` và `einvoice-and-tax.md` (chỉ đề xuất, không tự sửa)

1. Cập nhật bảng thẻ `Hóa đơn GTGT` trong `einvoice-xml.md` theo toàn bộ diff `QĐ 1233/QĐ-CT` ở Mục 1.2: ngoài `PBan=2.1.1` và `MSTCLQuan`, bổ sung **`LDDCTThe`**, nhóm **`MDDKDoanh`/`TDDKDoanh`/`DCDDKDoanh`**, **`MTinh`/`TTinh`/`MXa`/`TXa`**, **`LHDCLQuan=5`**, **`TSuat` thêm `CTTC`, `KTPVDC`, `KTGTT`**, và chuẩn ký **`XAdES` (`xades:SigningTime`)**; đồng thời parse `KDLieu` không phân biệt hoa/thường (`String`/`string`).
2. Trong `einvoice-and-tax.md §2a`: đóng khoảng trống ký tự 5–6 của `KHHDon` (đã xác minh từ `91-btc.signed.pdf` trang 35) và cân nhắc siết regex chuẩn thành `^[CK]\d{2}[TDLMNBGHXF][A-Z]{2}$`.
3. Trong `einvoice-and-tax.md §3a`: bổ sung ghi chú **`04` đã `"Hết hiệu lực"`** theo Phụ lục I gốc `TT 90/2026/TT-BTC`.
4. Có thể tải và lưu trực tiếp bản PDF ký số 423 trang `QĐ 1233/QĐ-CT` vào `docs/04-data/references/` (đặt cạnh `QD-1271-QD-CT-2025.pdf`) nếu đội muốn nâng chuẩn tham chiếu lên `2.1.1`.
