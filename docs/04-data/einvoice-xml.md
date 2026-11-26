# Hóa đơn điện tử XML

Trạng thái: **Đã cập nhật theo chuẩn hiện hành QĐ 1233/QĐ-CT (27/08/2026) và đối chiếu 10 file XML thật đã làm sạch (26/11/2026).** Bộ parser `ingest` (`services/core`) và bộ sinh dữ liệu `sim-world` bám trực tiếp tài liệu này.

## 1. Văn bản pháp lý và lộ trình chuyển tiếp

| Hạng mục | Nội dung |
|---|---|
| **Chuẩn hiện hành** | **QĐ 1233/QĐ-CT** ngày **27/08/2026** của Cục trưởng Cục Thuế: *Quy định về thành phần chứa dữ liệu nghiệp vụ hóa đơn, chứng từ điện tử và phương thức truyền nhận với cơ quan thuế*. Hiệu lực kể từ ngày ký. Đối chiếu trực tiếp trên bản Quy định **423 trang ký số** bởi Cục Thuế (`28/08/2026 10:29:35+07:00`, sha256 `9efe003ce2f5a485…`, [PDF ký số](https://laphoadon.htinvoice.vn/DownloadFile/QD%201233_Quy%20dinh%20chuan%20DL%20HD%20CT%20.pdf)); bảng đối chiếu chi tiết tại [research/verify-einvoice-claims.md](research/verify-einvoice-claims.md). |
| **Căn cứ pháp lý** | Luật Quản lý thuế số `108/2025/QH15`, **NĐ 254/2026/NĐ-CP** (30/06/2026, hiệu lực 01/07/2026 — [vanban.chinhphu.vn](https://vanban.chinhphu.vn/?pageid=27160&docid=218689) / [254-ndcp.signed.pdf](https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/7/254-ndcp.signed.pdf)), **TT 91/2026/TT-BTC** (30/06/2026, hiệu lực 01/07/2026, thay TT 32/2025/TT-BTC — [vanban.chinhphu.vn](https://vanban.chinhphu.vn/?pageid=27160&docid=219006) / [91-btc.signed.pdf](https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/7/91-btc.signed.pdf)), NĐ 23/2025/NĐ-CP và TT 15/2025/TT-BKHCN (chữ ký điện tử). |
| **Phiên bản thông điệp (`PBan`)** | **`2.1.1`** theo QĐ 1233/QĐ-CT (trang 7 & trang 95 bản PDF ký số). |
| **Chuỗi lịch sử văn bản (đã xác minh)** | `QĐ 635/QĐ-TCT` (2020) → `QĐ 1450/QĐ-TCT` (07/10/2021, `PBan 2.0.0`) → `QĐ 1510/QĐ-TCT` (21/09/2022, `PBan 2.0.1`) → `QĐ 1271/QĐ-CT` (30/05/2025, `PBan 2.1.0`, lưu lịch sử tại [references/QD-1271-QD-CT-2025.pdf](references/QD-1271-QD-CT-2025.pdf), sha256 `25ffb73b…2969`) → `QĐ 1306/QĐ-CT` (13/06/2025, thay thế QĐ 1271) → **`QĐ 1233/QĐ-CT`** (27/08/2026, `PBan 2.1.1`, Điều 2 thay thế QĐ 1306/QĐ-CT). |

**Lộ trình chuyển tiếp (Điều 2 QĐ 1233/QĐ-CT):**
- **Phiên bản `PBan`:** CQT hoàn thành nâng cấp trước `01/01/2027`; tiếp nhận song song **`2.1.0` đến hết ngày `31/12/2026`**.
- **Chữ ký số:** chuyển từ XMLDSig (`DSig`) sang **XAdES (`ETSI EN 319 132-1 V1.2.1`)**; CQT hoàn thành nâng cấp trước `10/04/2027` và tiếp nhận song song **`DSig` đến hết ngày `09/04/2027`**.
- **Yêu cầu cho bộ `ingest` PayMatch:** Ngày demo `03/12/2026` nằm trong giai đoạn chuyển tiếp, đồng thời doanh nghiệp vẫn lưu trữ và nhận hóa đơn từ nhiều TCGP nâng cấp không đồng đều. Do đó **`ingest` bắt buộc chấp nhận `PBan` ∈ `{"2.0.0", "2.0.1", "2.1.0", "2.1.1"}`** và chấp nhận cả chữ ký `DSig` lẫn `XAdES` (nếu `PBan` khác 4 giá trị này trả `422 XML_UNPARSEABLE`).

## 2. Quy định chung (QĐ 1233/QĐ-CT)

- **Đặt tên & bảng mã:** UTF-8; tên thẻ viết liền không dấu, chữ cái đầu mỗi từ viết hoa (ví dụ Dữ liệu hóa đơn → `DLHDon`).
- **Định dạng số & quy tắc làm tròn:** dấu `.` ngăn phần thập phân, độ dài `21,6` = tối đa 21 chữ số trong đó tối đa 6 chữ số thập phân (parser đọc bằng kiểu `Decimal`, không ép `float`, từ chối số không hợp lệ hoặc không hữu hạn bằng `422 XML_UNPARSEABLE`). File thật đôi khi ghi thừa chữ số `0` sau dấu phẩy vượt 6 chữ số thập phân (ví dụ mẫu `s13` ghi `SLuong`/`DGia` = `0.000000000`): khi định dạng ra chuỗi `Decimal` (`SLuong`, `DGia`, `TLCKhau`), parser chuyển giá trị `0` thành `"0"` và cắt các chữ số `0` thừa ở cuối phần thập phân (cùng dấu `.` thừa) trước khi đối chiếu mẫu `Decimal` (`schemas.md §1`, tối đa 6 chữ số thập phân); nếu còn chữ số khác `0` sau vị trí thập phân thứ 6, parser domain **không tự làm tròn hay cắt bớt** (giữ nguyên độ chính xác `Decimal`, và chuỗi kết quả sẽ không khớp mẫu `Decimal` 6 chữ số ở tầng kiểm tra schema/API). Theo **QĐ 1233 Phần I mục IV.2a**, các trường tổng và tiền bằng `VND` (`ThTien`, `STCKhau`, `TgTCThue`, `TGTKCThue`, `TgTThue`, `TTCKTMai`, `TGTKhac`, `TgTTTBSo`, `LTSuat/{ThTien, TThue}`) được **làm tròn đến đơn vị đồng (`ROUND_HALF_UP`)**.
- **Ngày giờ:** Ngày `YYYY-MM-DD`; ngày giờ `YYYY-MM-DDThh:mm:ss`, múi giờ `GMT+7`.
- **Mã của cơ quan thuế (`MCCQT`):**
  - Hóa đơn có mã thông thường (`C`): chuỗi **34 ký tự** (thường bắt đầu bằng `00`).
  - Hóa đơn khởi tạo từ **máy tính tiền** (`KHHDon` vị trí 4 = `M`): chuỗi **23 ký tự** dạng `M<loại 1–9>-<YY>-<5 ký tự CQT cấp>-<11 chữ số>` (ví dụ `M2-26-A1B2C-00001234567`).
  - Hóa đơn không mã (`K`): không có hoặc thẻ rỗng.
- **Chữ ký số (`DSCKS`):** các nhóm `NBan`, `NMua`, `CQT`, `CCKSKhac`. Theo QĐ 1233 Phần I mục IV.4 (trang 5–6): mật mã RSA, hàm băm SHA-256/384/512 theo chuẩn **ETSI EN 319 132-1 V1.2.1 (XAdES)**; `SigningTime` nằm tại `ds:Signature/ds:Object/xades:QualifyingProperties/xades:SignedProperties/xades:SignedSignatureProperties/xades:SigningTime`, kèm ràng buộc chứng thư `xades:SigningCertificate/xades:Cert/{xades:CertDigest, xades:IssuerSerial}` (ở XMLDSig cũ nằm tại `Signature/Object/SignatureProperties/SignatureProperty/SigningTime`). Chuyển tiếp `DSig` đến hết `09/04/2027`.
- **Mã QR (`DLQRCode`, tối đa 512 ký tự):** theo QĐ 1233 là chuỗi dạng **TLV theo TCCS 04:2024/NHNN** (QĐ 2525/QĐ-NHNN):
  - Trường thanh toán EMV/VietQR: `26-xx` / `38-xx` (đơn vị chấp nhận thanh toán / thông tin tài khoản nhận tiền), `54` (số tiền).
  - **Trường `99`** (thông tin tra cứu hóa đơn): `99-01` MST người bán (bỏ dấu `-`), `99-02` `KHMSHDon`, `99-03` `KHHDon`, `99-04` `SHDon`, `99-05` `NLap` (`YYYYMMDD`), `99-06` `TgTTTBSo`.
- **`TTKhac`:** xuất hiện ở **6 vị trí** (`TTChung`, `NBan`, `NMua`, `HHDVu`, `TToan`, `DLHDon`), gồm các `TTin {TTruong, KDLieu, DLieu}` với `DLieu` tối đa **500 ký tự**. Toàn bộ là **chữ người bán tự viết (`untrusted`)**.
- **Phong bì gói thông điệp (`TDiep`):** khi truyền qua T-VAN hoặc tải từ hệ thống CQT, `<HDon>` có thể bọc trong `<TDiep><TTChung>…</TTChung><DLieu><HDon>…</HDon></DLieu></TDiep>` (QĐ 1233 Phần I mục IV.5). Một số phần mềm còn bọc `<HDon><DLieu><DLHDon>…</DLHDon></DLieu></HDon>`. Parser tìm node có `local-name() == "HDon"` và tự mở lớp `<DLieu>` nếu có.

## 3. Cây thẻ hóa đơn GTGT (QĐ 1233/QĐ-CT)

Bắt buộc: **B**. Bắt buộc nếu có: **B?**. Không bắt buộc: **–**. Đối chiếu bản ký số QĐ 1233 (trang 95–110) với QĐ 1271: thêm **16 thẻ/nhóm thẻ mới** đánh dấu *(QĐ 1233)*, **0 thẻ bị xóa hoặc đổi tên**, 57 thẻ dùng chung giữ nguyên độ dài tối đa.

```
[TDiep/DLieu/] HDon
├── DLHDon  (@Id)
│   ├── TTChung                          thông tin chung
│   │   ├── PBan        6    B   phiên bản: 2.1.1 (ingest nhận 2.0.0, 2.0.1, 2.1.0, 2.1.1)
│   │   ├── THDon       100  B   tên hóa đơn ("Hóa đơn giá trị gia tăng")
│   │   ├── KHMSHDon    1    B   ký hiệu mẫu số (1–9, Phụ lục II)
│   │   ├── KHHDon      6    B   ký hiệu hóa đơn (6 ký tự, Phụ lục I TT 91/2026)
│   │   ├── SHDon       8    B?  số hóa đơn (kiểu số, 1–8 chữ số)
│   │   ├── MHSo        20   B?  mã hồ sơ (hóa đơn cấp mã theo từng lần)
│   │   ├── NLap             B   ngày lập (YYYY-MM-DD)
│   │   ├── HDCTTChinh  1    B   1 = cho thuê tài chính, 0 = không
│   │   ├── SBKe, NBKe       B?  số/ngày bảng kê kèm theo
│   │   ├── DVTTe       3    B   đơn vị tiền tệ (VND)
│   │   ├── TGia        7,2  B   tỷ giá (trừ khi VND)
│   │   ├── HTTToan     50   B   hình thức thanh toán (chữ tự do, untrusted)
│   │   ├── MSTTCGP     14   B   MST tổ chức cung cấp giải pháp hóa đơn
│   │   ├── MSTDVNUNLHDon, TDVNUNLHDon, DCDVNUNLHDon   B?  đơn vị nhận ủy nhiệm lập
│   │   ├── TTHDLQuan                    hóa đơn liên quan (điều chỉnh/thay thế/CKTM)
│   │   │   ├── TCHDon       1    B   1 thay thế, 2 điều chỉnh, 3 thay thế nhiều, 4 điều chỉnh nhiều, 5 CKTM
│   │   │   ├── MSTCLQuan    14   B?  (QĐ 1233) MST liên quan khi chia/tách/sáp nhập/hợp nhất (đặt ngay sau TCHDon)
│   │   │   ├── LHDCLQuan    1    B?  loại hóa đơn liên quan (1–5, PL VI; trừ lý do 1,2,3,9,10,12 PL XVII)
│   │   │   ├── KHMSHDCLQuan 11   B?  ký hiệu mẫu số HĐ liên quan (tối đa 11 cho mẫu cũ NĐ 51)
│   │   │   ├── KHHDCLQuan   8    B?  ký hiệu HĐ liên quan (tối đa 8)
│   │   │   ├── SHDCLQuan    8    B?  số HĐ liên quan
│   │   │   ├── NLHDCLQuan        B?  ngày lập HĐ liên quan (YYYY-MM-DD)
│   │   │   ├── LDDCTThe     2    B?  (QĐ 1233) mã lý do điều chỉnh/thay thế (1..14 PL XVII; B khi TCHDon=1,2; đặt ngay trước GChu)
│   │   │   ├── GChu         255  –   ghi chú (đứng trước SBKCLQuan/NBKCLQuan trong chuẩn)
│   │   │   ├── SBKCLQuan    50   B?  số bảng kê (bắt buộc khi TCHDon = 3 hoặc 4)
│   │   │   └── NBKCLQuan         B?  ngày bảng kê (bắt buộc khi TCHDon = 3 hoặc 4)
│   │   └── TTKhac
│   ├── NDHDon                           nội dung hóa đơn
│   │   ├── NBan                         người bán
│   │   │   ├── Ten 400 B · MST 14 B · DChi 400 B
│   │   │   ├── SDThoai 20, DCTDTu 50           –
│   │   │   ├── STKNHang 30, TNHang 400         –   số TK, tên ngân hàng (đứng trước Fax/Website trong chuẩn)
│   │   │   ├── Fax 20, Website 100             –
│   │   │   ├── MCHang, TCHang                  –   mã/tên cửa hàng
│   │   │   ├── TCQDGBTSan 400, DCCQDGBTSan 400, MSTCQDGBTSan 14   –   (QĐ 1233) cơ quan bán đấu giá tài sản
│   │   │   ├── MDDKDoanh 14, TDDKDoanh 400, DCDDKDoanh 400        B?  (QĐ 1233) địa điểm kinh doanh (B với xăng dầu)
│   │   │   └── TTKhac
│   │   ├── NMua                         người mua
│   │   │   ├── Ten, MST, MDVQHNSach 7, DChi    B?
│   │   │   ├── MKHang, SDThoai                 –
│   │   │   ├── CCCDan 12, SHChieu 20           B?
│   │   │   ├── DCTDTu, HVTNMHang               –   (QĐ 1233: HVTNMHang ghi "Bán cho người tiêu dùng" khi không có TT người mua)
│   │   │   ├── STKNHang, TNHang                –
│   │   │   ├── MTinh 2, TTinh 50, MXa 5, TXa 50   B?  (QĐ 1233, QĐ 19/2025/QĐ-TTg; B với LHHDTrung = 1)
│   │   │   ├── SDDTCNNgoai 50                  –   (QĐ 1233) số định danh tổ chức nước ngoài
│   │   │   ├── MQTNMua 2, QTNMua 50            B?  (QĐ 1233, PL XIX) mã/quốc tịch người mua là người nước ngoài
│   │   │   └── TTKhac
│   │   ├── DSHHDVu                      (không bắt buộc nếu là HĐ điều chỉnh thông tin không đổi hàng hóa)
│   │   │   └── HHDVu  (lặp, mỗi dòng hàng một thẻ)
│   │   │       ├── TChat   1    B   tính chất (1–5, Phụ lục IV)
│   │   │       ├── STT     4    –
│   │   │       ├── MHHDVu  50   B?  mã hàng
│   │   │       ├── THHDVu  500  B   tên hàng
│   │   │       ├── DVTinh  50   B?  đơn vị tính
│   │   │       ├── SLuong  21,6 B?  · DGia 21,6 B?
│   │   │       ├── TLCKhau 6,4  – · STCKhau 21,6 –   chiết khấu theo dòng
│   │   │       ├── ThTien  21,6 B   thành tiền chưa thuế (trừ TChat = 4)
│   │   │       ├── TSuat   11   B?  thuế suất (Phụ lục V)
│   │   │       ├── TTHHDTrung/TTin/{LHHDTrung, TTruong, DLieu}   B nếu TChat = 5 (QĐ 1233: LHHDTrung=1 gồm 17 trường, =2 thêm DDi/DDen/THHVChuyen, mới =4 TTTDat/TTTSGLTDat)
│   │   │       └── TTKhac
│   │   └── TToan                        thanh toán (không bắt buộc nếu là HĐ điều chỉnh thông tin không đổi tiền)
│   │       ├── THTTLTSuat/LTSuat (lặp theo thuế suất): TSuat, ThTien B, TThue B?
│   │       ├── TgTCThue  B   tổng tiền chưa thuế (vắng ở hóa đơn bán hàng KHMSHDon = 2)
│   │       ├── TGTKCThue –   tổng giảm trừ không chịu thuế
│   │       ├── TgTThue   B   tổng tiền thuế (vắng ở hóa đơn bán hàng KHMSHDon = 2)
│   │       ├── DSLPhi/LPhi: TLPhi, TPhi   B?  phí, lệ phí
│   │       ├── TTCKTMai  B?  tổng chiết khấu thương mại
│   │       ├── TGTKhac   –   tổng giảm trừ khác
│   │       ├── TgTTTBSo  B   tổng thanh toán bằng số
│   │       ├── TgTTTBChu B   tổng thanh toán bằng chữ (255)
│   │       └── TTKhac
│   └── TTKhac
├── DSHDGiay/DLHDGiay   B?  (QĐ 1233) hóa đơn giấy/NĐ 51/04 bị thay thế (KHMSHDon 11, KHHDon 8, SHDon 7, NBan, NMua, TToan)
├── DLQRCode            512 –   mã QR TLV theo TCCS 04:2024/NHNN (trường thanh toán 26-xx/38-xx, 54 và trường tra cứu 99)
├── MCCQT               B?  chỉ hóa đơn có mã (34 ký tự) hoặc máy tính tiền (23 ký tự)
└── DSCKS               NBan · NMua · CQT · CCKSKhac (QĐ 1233: ds:Signature/ds:Object/xades:QualifyingProperties chuẩn XAdES ETSI EN 319 132-1 V1.2.1; DSig song song đến 09/04/2027)
```

*Ghi chú hóa đơn bán hàng (`KHMSHDon = 2`, QĐ 1233 mục b):* có thêm thẻ `TTChung/HDDCKPTQuan` (`0`/`1`, cờ khu phi thuế quan) và **không có** `THTTLTSuat`, `TgTCThue`, `TgTThue` — chỉ có `TgTTTBSo`.

**Danh mục giá trị (xác minh từ bản ký số QĐ 1233/QĐ-CT & Phụ lục I `91-btc.signed.pdf`):**

| Thẻ | Giá trị chuẩn |
|---|---|
| `KHMSHDon` | `1` GTGT · `2` bán hàng · `3` bán tài sản công · `4` hàng dự trữ quốc gia · `5` tem/vé/thẻ/phiếu thu · `6` phiếu xuất kho · **`7`** hóa đơn thương mại điện tử · **`8`** HĐĐT GTGT tích hợp biên lai thu thuế, phí, lệ phí · **`9`** HĐĐT bán hàng tích hợp biên lai (Phụ lục II) |
| `KHHDon` (6 ký tự, PL I TT 91/2026) | `[1][2–3][4][5–6]`:<br>• Ký tự 1: `C` (có mã CQT) \| `K` (không mã CQT; **không có `M`** ở vị trí 1)<br>• Ký tự 2–3: 2 chữ số cuối năm lập (ví dụ `26` cho 2026)<br>• Ký tự 4: **10 chữ cái** `T` (DN/tổ chức/HKD đăng ký CQT) · `D` (tài sản công, dự trữ QG, HĐĐT đặc thù) · `L` (CQT cấp từng lần) · `M` (khởi tạo từ máy tính tiền) · `N` (PXK vận chuyển nội bộ) · `B` (PXK gửi bán đại lý) · `G` (tem/vé/thẻ GTGT) · `H` (tem/vé/thẻ bán hàng) · **`X`** (hóa đơn thương mại điện tử) · **`F`** (HĐ GTGT kiêm tờ khai hoàn thuế)<br>• Ký tự 5–6: 2 chữ cái do người bán tự xác định theo nhu cầu quản lý (`YY` nếu không phân loại riêng; PL I trang 35 **không** giới hạn tập 20 chữ cái loại trừ như biên lai điện tử ở PL II).<br>• Regex chuẩn theo luật: `^[CK]\d{2}[TDLMNBGHXF][A-Z]{2}$` |
| `TChat` | `1` hàng hóa, dịch vụ · `2` khuyến mại · `3` chiết khấu thương mại · `4` ghi chú/diễn giải · `5` hàng hóa đặc trưng (Phụ lục IV) |
| `TSuat` | `0%` · `5%` · `8%` · `10%` · `KCT` · `KKKNT` · `KHAC:AB.CD%` hoặc `KHAC` · **`CTTC`** (cho thuê tài chính) · **`KTPVDC`** (không thuộc phạm vi điều chỉnh của Luật thuế) · **`KTGTT`** (không tính vào giá tính thuế GTGT) (Phụ lục V) |
| `KDLieu` (`TTKhac`) | QĐ 1233 PL III: `String` · `Numeric` · `dateTime` · `Date` (file thật dùng cả chữ thường `string`/`numeric`/`date` và viết hoa → parser so không phân biệt hoa thường) |
| `LHDCLQuan` | `1` theo NĐ 123/NĐ 70 · `2` mã xác thực cũ (QĐ 1209/2660) · `3` theo NĐ 51/04 · `4` đặt in theo NĐ 123 · **`5` theo NĐ 254/2026** (Phụ lục VI) |
| `LDDCTThe` | Mã 2 chữ số (Phụ lục XVII QĐ 1233, bắt buộc khi `TCHDon` = `1` hoặc `2`): ví dụ `4` chiết khấu thương mại, `5` trả lại hàng, `13` điều chỉnh/thay thế HĐ lập sai, `14` thay thế HĐ máy tính tiền lập sai |

## 3a. Thực tế trong file thật

Đối chiếu trực tiếp **10 file XML thật đã làm sạch** từ 10 `MSTTCGP` khác nhau ([research/claude/einvoice-samples/](research/claude/einvoice-samples/README.md)), 6 fixture kiểm thử parser ([references/einvoice-samples/](references/einvoice-samples/README.md)) và mẫu EVNHCMC/SAWACO ([research/utilities-and-persona.md](research/utilities-and-persona.md)) cho thấy bộ `ingest` **bắt buộc xử lý 10 đặc thù thực tế sau**:

1. **Không có default namespace trên `<HDon>` — bắt buộc parse theo `local-name()`:** Cả 10 file thật đều không khai báo `xmlns` mặc định trên `<HDon>`; chỉ `<Signature>` dùng `xmlns="http://www.w3.org/2000/09/xmldsig#"` (từ QĐ 1233 thêm namespace XAdES). Một số phần mềm/fixture có UTF-8 BOM (`\uFEFF`), prefix (`<inv:HDon>`, `<ds:Signature>`), hoặc default namespace lạ. Parser phải bỏ BOM và luôn truy xuất theo `local-name()`.
2. **Thứ tự thẻ con không cố định giữa các TCGP:** File thật có `TSuat` đứng trước `ThTien` (xăng dầu `s07`), `DSLPhi` đứng trước `THTTLTSuat` (`s04`), `THTTLTSuat` đứng đầu hoặc sau `TgTThue`, `TTHHDTrung` đứng đầu (`s05`) hoặc cuối `HHDVu` (`s14`), `DSCKS` có thứ tự `NBan, NMua, CCKSKhac, CQT` (`s10`). Không được parse theo chỉ số vị trí.
3. **`TTKhac` xuất hiện ở cả 6 cấp với tên `TTruong` tùy biến theo TCGP:** `TTChung`, `NBan`, `NMua`, `HHDVu`, `TToan`, `DLHDon`. `TTruong` có thể là tiếng Anh (MISA: `SellerBankAccount`, `SellerBankName`, `InvoiceTemplateID`; BKAV: `BankAccount`, `BankName`), tiếng Việt có dấu (`"Thành tiền sau thuế"`, `"Mã tra cứu"`), mã ngắn (`Extra1`, `Fkey`, `MDDKDoanh`), hoặc thậm chí trùng tên thẻ chuẩn (`TgTTTBSo` nằm trong `TTKhac`). Parser phải thu thập đủ `TTKhac` ở mọi cấp (kèm ngữ cảnh cấp cha để tách `NBan` khỏi `NMua`) và không để `TTruong` ghi đè thẻ chuẩn.
4. **Thẻ ngoài chuẩn xuất hiện trong file thật:** `<Fkey>` và `<QRCodeDataTemVe>` đặt trực tiếp ở gốc `<HDon>` (`s05`, `s07`), `<TThue>` đặt thẳng trong `<HHDVu>` (Viettel `s12`), `<THDon>` đôi khi chứa ký hiệu thay vì tên hóa đơn (`s14`). Parser phải bỏ qua an toàn các thẻ ngoài chuẩn, không crash.
5. **`SHDon` không luôn đệm số `0`:** File thật có `SHDon` dài 2, 4, 6, 7 hoặc 8 chữ số (ví dụ `"42"`, `"1234"`, `"00001234"`). Lưu chuỗi gốc để hiển thị, nhưng chuẩn hóa về số nguyên cho khóa chống trùng (§4).
6. **`MST` có thể có đuôi `-NNN` (14 ký tự):** Đơn vị phụ thuộc/chi nhánh có dạng `XXXXXXXXXX-NNN` (ví dụ `0300951119-001` của PC Sài Gòn, mẫu `s02` sau khi làm sạch có `0000000001-001`). `NMua/MST` có thể rỗng (bán lẻ) hoặc 12 chữ số (CCCD). Luôn đọc `MST` là chuỗi (`string`) để giữ số `0` đầu và giữ nguyên đuôi `-NNN`.
7. **`MCCQT` rỗng trên hóa đơn `K` và bản lưu chưa cấp mã của hóa đơn `C`:** Hóa đơn không mã (`K`) có thể không có thẻ `MCCQT` hoặc có `<MCCQT/>` rỗng (`s04`, `s07`). Hóa đơn có mã (`C`) do người bán lưu trước khi CQT cấp mã cũng có `<MCCQT/>` rỗng (`s09`) → `ingest` ghi `tax_authority_code = null` và không từ chối parse (bot `tax` đối chiếu cổng HĐĐT để phát hiện hóa đơn chưa cấp mã).
8. **Số âm trên hóa đơn điều chỉnh giảm & thẻ tùy chọn trên điều chỉnh thông tin:** Khi `TTHDLQuan/TCHDon` ∈ `{2, 4}` (điều chỉnh), các trường tiền (`ThTien`, `TgTCThue`, `TgTThue`, `TgTTTBSo`) có thể mang **dấu âm (`-`)**, và `SLuong = 0`, `DGia = 0` (mẫu `s13`). Hóa đơn điều chỉnh thông tin có thể không có `DSHHDVu` và/hoặc `TToan`. Parser phải cho phép số âm khi `TCHDon ∈ {2, 4}` và không crash khi thiếu `DSHHDVu`/`TToan`.
9. **Hóa đơn bán hàng (`KHMSHDon = 2`) không có `TgTCThue` / `TgTThue`:** Chỉ có `TgTTTBSo` (và thẻ chuẩn `HDDCKPTQuan`, xem mẫu `s13`). Bộ `ingest` đặt `subtotal_vnd = total_vnd`, `vat_total_vnd = 0`, `vat_breakdown = []` và bỏ qua kiểm tra `TgTCThue + TgTThue = TgTTTBSo`.
10. **Hóa đơn tiền điện EVN có `DGia` rỗng kèm `SBKe`:** Mặt Hóa đơn GTGT điện kinh doanh 3 giá của EVNHCMC chỉ có 1 dòng gộp `SLuong = tổng kWh`, **`DGia` để trống (`null`)**, `ThTien = tổng tiền chưa thuế`, tham chiếu `TTChung/SBKe` (chi tiết 3 khung giờ nằm ở bảng kê / `utility_readings`). Parser phải bỏ qua kiểm tích `SLuong × DGia` khi `DGia` hoặc `SLuong` rỗng.

*Lưu ý phụ về dữ liệu số & chữ ký trong file thật:* số tiền có thể viết kèm phần thập phân thừa như `4564815.000000` (parse bằng `Decimal`, kiểm tra nguyên đồng sau làm tròn); 8/21 chữ ký trong mẫu thật cũ vẫn dùng `rsa-sha1`/`sha1` hoặc không kèm `Signature` trong `DSCKS`.

## 4. Ánh xạ sang PayMatch và quy tắc kiểm tra `ingest`

Tên trường PayMatch bám đúng [05-api/schemas.md §2](../05-api/schemas.md#2-hóa-đơn). Theo quy tắc tách số và chữ ([tools.md §3](../03-agents/tools.md#3-nguyên-tắc-thiết-kế)): trường số/mã do code parse là `trusted`; mọi chữ do người bán tự viết là `untrusted`.

| PayMatch (`invoices`, `invoice_lines`) | Thẻ XML nguồn | Provenance |
|---|---|---|
| `seller_tax_id` | `NBan/MST` (giữ nguyên chuỗi, gồm số `0` đầu và đuôi `-NNN` nếu có) | trusted (đối chiếu `tax_id_lookup`) |
| `symbol` | `KHMSHDon` + `KHHDon` (viết hoa, bỏ khoảng trắng, ví dụ `"1C26TAA"`) | trusted |
| `number` | `SHDon` (lưu chuỗi gốc để hiển thị) | trusted |
| **Khóa chống trùng** | `(NBan/MST nguyên bản, KHMSHDon+KHHDon, int(SHDon))` — xem quy tắc chuẩn hóa bên dưới | trusted |
| `issued_on` | `NLap` | trusted |
| `buyer_tax_id` | `NMua/MST` (đối chiếu MST của tenant) | trusted |
| `store_hint` | `NMua/DChi`, `NMua/TTKhac` | **untrusted**, chỉ là gợi ý quán nhận hàng |
| `lines[].kind` | `HHDVu/TChat` (`1..5` → `goods_service \| promotion \| trade_discount \| note \| special_goods`) | trusted |
| `lines[].item_code`, `name`, `unit` | `MHHDVu`, `THHDVu`, `DVTinh` | **untrusted** (bot `procurement` ánh xạ sang SKU) |
| `lines[].quantity`, `unit_price`, `discount_vnd`, `amount_vnd`, `vat_rate` | `SLuong`, `DGia`, `STCKhau`, `ThTien`, `TSuat` | trusted |
| `subtotal_vnd`, `vat_total_vnd`, `total_vnd` | `TgTCThue`, `TgTThue`, `TgTTTBSo` (với `KHMSHDon = 2`: `subtotal_vnd = total_vnd`, `vat_total_vnd = 0`) | trusted |
| `vat_breakdown[]` | `THTTLTSuat/LTSuat/{TSuat, ThTien, TThue}` | trusted |
| `bank_account_on_invoice` (`untrusted.seller_bank_account` + danh sách TK trích được) | Trích từ **cả 3 nguồn** (bỏ trùng):<br>1. `NBan/STKNHang` + `NBan/TNHang`;<br>2. Mọi `TTKhac/TTin` (trừ `NMua/TTKhac`) có `TTruong` biểu thị STK người bán (không phân biệt hoa thường/dấu, ví dụ MISA `SellerBankAccount`/`SellerBankName`, BKAV `BankAccount`/`BankName`, `STK`, `SoTaiKhoan`, `STKNHang`, `TaiKhoanNganHang`);<br>3. Các trường thanh toán trong `DLQRCode` (TLV `26-xx`/`38-xx` chuẩn EMV/VietQR) nếu có chứa STK nhận tiền. | **untrusted**. **Không bao giờ dùng làm payee**; Gate chỉ trả vào TK `verified` (hoặc `escrow_only`) trong `vendor_registry`. Bất kỳ STK nào khác TK đã lưu trong registry (và chưa có xác minh F12) đều là tín hiệu đỏ `PAYEE_CHANGE_REQUEST` |
| `untrusted.payment_terms`, `untrusted.other_info` | `HTTToan` và toàn bộ `TTKhac` ở cả 6 cấp (`TTChung`, `NBan`, `NMua`, `HHDVu`, `TToan`, `DLHDon`) | **untrusted** (`fraud-control` quét `HIDDEN_INSTRUCTION` ở cả `TTKhac` và `HHDVu[TChat=4]/THHDVu`) |
| `tax_authority_code` | `MCCQT` (`null` nếu vắng hoặc rỗng) | trusted (đối chiếu `einvoice_portal`) |
| `einvoice_provider_tax_id` | `MSTTCGP` | trusted |
| `related_invoice` | `TTHDLQuan/{TCHDon, MSTCLQuan, LDDCTThe, LHDCLQuan, KHMSHDCLQuan, KHHDCLQuan, SHDCLQuan, NLHDCLQuan, SBKCLQuan, NBKCLQuan, GChu}` | trusted (`GChu` là `untrusted`). Hóa đơn thay thế/điều chỉnh đi luồng đối chiếu hóa đơn gốc |

### Idempotency theo `sha256` và chuẩn hóa khóa chống trùng

1. **Idempotency theo `(tenant_id, sha256)` (chạy TRƯỚC bước chống trùng):**
   - Trước khi kiểm khóa nghiệp vụ, `ingest` đối chiếu `sha256` của file gốc trong `invoice_documents` theo `tenant_id`.
   - Nếu đúng cùng file (`sha256`) đã được nạp cho tenant đó (ví dụ `core-worker` poll lại cùng email ở chế độ at-least-once hoặc người dùng tải lại đúng nguyên file): **`ingest` là no-op** và trả về hóa đơn đã tồn tại — **không** tạo bản ghi trùng, **không** gắn `DUPLICATE_INVOICE`, **không** phát `invoice.ingested` và **không** kích hoạt tự hạ quyền QT-03.
2. **Khóa chống trùng (Duplicate Key Normalization — chỉ áp khi `sha256` khác):**
   Trong phạm vi một `tenant_id`, một **file khác (`sha256` khác)** có cùng bộ 3 dưới đây mới là hóa đơn trùng (`DUPLICATE_INVOICE`):
   ```
   (seller_tax_id_norm, symbol_norm, number_norm)
   ```
   - `seller_tax_id_norm = NBan/MST.strip()` — **giữ nguyên số `0` đầu và giữ nguyên đuôi `-NNN`** (vì chi nhánh `-001` có dải số hóa đơn riêng, độc lập với trụ sở chính).
   - `symbol_norm = KHMSHDon.strip() + KHHDon.strip().upper()`.
   - `number_norm = str(int(SHDon.strip()))` — **chuẩn hóa `SHDon` về số nguyên** (ví dụ `"00001234"` và `"1234"` cùng chuẩn hóa thành `"1234"` và bị phát hiện trùng; nếu `SHDon` chứa ký tự không phải chữ số thì fallback `SHDon.strip()`).
   - **Xử lý hỗn hợp theo kênh vào:** qua `email`/`bill_pay` lưu hóa đơn với `duplicate_of = existing_invoice_id` + Finding đỏ `DUPLICATE_INVOICE` (giữ tín hiệu gian lận); qua `POST /m/invoices:upload` trả `409 DUPLICATE_INVOICE` kèm `existing_invoice_id` và **không lưu**.

### Quy tắc kiểm tra số học của `ingest` (code xác định, không phải LLM)

Bộ `ingest` chạy 3 tầng kiểm tra bằng `Decimal` (không dùng số thực nhị phân `float`):

1. **Tầng 1 — Cấp dòng hàng (`HHDVu`):**
   - **Điều kiện bỏ qua** (đặt `line.arithmetic_ok = true`, không báo lỗi):
     - `TChat ∈ {2, 4}` (khuyến mại hoặc ghi chú/diễn giải); hoặc
     - `SLuong` rỗng/`null` **hoặc** `DGia` rỗng/`null` (ví dụ hóa đơn tiền điện EVN có `SBKe` kèm theo); hoặc
     - Hóa đơn điều chỉnh (`TTHDLQuan/TCHDon ∈ {2, 4}`) có `SLuong == 0` và `DGia == 0` với `ThTien != 0` (ví dụ mẫu thật `s13` điều chỉnh giảm thành tiền).
   - **Công thức kiểm tra** cho các dòng còn lại (`TChat ∈ {1, 3, 5}` có đủ `SLuong`, `DGia`, `ThTien`):
     - `discount = STCKhau` nếu có; nếu không có `STCKhau` nhưng có `TLCKhau` thì `discount = SLuong × DGia × TLCKhau / 100`; ngược lại `0`.
     - `expected = SLuong × DGia − discount`.
     - **Ngưỡng sai số (tolerance):** `|expected − ThTien| ≤ max(1 đồng, 0,05% × |ThTien|)`.
       *(Căn cứ thực nghiệm từ 10 mẫu thật: hóa đơn xăng dầu thật bán theo tiền tròn rồi tính ngược số lít, hoặc đơn giá chưa thuế suy từ giá có thuế, lệch tới 108 đ trên 1.000.000 đ ≈ 0,011%. Ngưỡng `max(1 đ, 0,05% × |ThTien|)` tránh báo nhầm trên hóa đơn thật nhưng vẫn bắt sai lệch tính toán thực sự.)*
     - Vượt ngưỡng → đặt `line.arithmetic_ok = false` và ghi lỗi số học.

2. **Tầng 2 — Cấp tổng hợp thuế suất (`THTTLTSuat/LTSuat`):**
   - Áp dụng khi `THTTLTSuat` có mặt (bỏ qua trên hóa đơn bán hàng `KHMSHDon = 2` hoặc hóa đơn điều chỉnh không có `TToan`).
   - Với mỗi `LTSuat`:
     - Nếu `TSuat` là tỷ lệ phần trăm hợp lệ (`0%`, `5%`, `8%`, `10%`, `KHAC:AB.CD%`) và `TThue` có mặt: `|round(LTSuat/ThTien × rate) − LTSuat/TThue| ≤ 1 đồng`.
     - Khi có `DSHHDVu` và không có chiết khấu tổng `TTCKTMai`/dòng `TChat = 3` gây khác biệt cách cộng giữa các TCGP: `|Σ ThTien(dòng thuộc TSuat) − LTSuat/ThTien| ≤ 1 đồng`.
   - Tổng các `LTSuat` so với tổng hóa đơn:
     - `|Σ LTSuat/ThTien − TgTCThue| ≤ 1 đồng`
     - `|Σ LTSuat/TThue − TgTThue| ≤ 1 đồng` (khi `TgTThue` có mặt).

3. **Tầng 3 — Cấp tổng hóa đơn (`TToan`):**
   - Nếu `TToan` vắng mặt trên hóa đơn điều chỉnh thông tin (`TCHDon ∈ {2, 4}`): hợp lệ, bỏ qua.
   - Nếu `KHMSHDon = 2` (hóa đơn bán hàng, không có `TgTCThue`/`TgTThue`): khi có `DSHHDVu` và không có `TTCKTMai`/`DSLPhi`/`TGTKhac`, kiểm `|Σ ThTien − TgTTTBSo| ≤ 1 đồng`.
   - **Mọi mẫu hóa đơn khác `KHMSHDon = 2`** (gồm hóa đơn GTGT `KHMSHDon = 1` và các mẫu có tách thuế GTGT khác như `KHMSHDon = 5` tem/vé — ví dụ mẫu thật [s05-ve-maytinhtien-pban210-msttcgp0401486901.xml](research/claude/einvoice-samples/s05-ve-maytinhtien-pban210-msttcgp0401486901.xml)):
     - Bắt buộc có cả `TgTCThue` và `TgTThue` (thiếu một trong hai → ghi lỗi số học `AMOUNT_MISMATCH`).
     - **Khi không có chiết khấu tổng/phí/giảm trừ** (`TTCKTMai`, `TGTKCThue`, `TGTKhac`, `Σ DSLPhi/LPhi/TPhi` đều vắng hoặc bằng `0`):
       - Kiểm **chính xác tuyệt đối đến đồng** (`sai số = 0`, đã xác minh khớp 14/14 file thật có tổng được đọc trong quá trình nghiên cứu, trong đó 10 file đã làm sạch được lưu trong repo):
         `TgTCThue + TgTThue == TgTTTBSo`.
     - **Khi có chiết khấu tổng, phí hoặc giảm trừ khác 0** *(công thức đầy đủ: **chưa xác minh** trên file XML sản xuất thật do chưa có mẫu `TTCKTMai`/`DSLPhi`/`TGTKhac` ≠ 0)*:
       - Do các TCGP khác nhau ở việc `TgTCThue` đã trừ `TTCKTMai` hay chưa, chấp nhận khớp **một trong hai nhánh** với sai số `≤ 1 đồng`:
         - Nhánh A (`TTCKTMai` đã được trừ vào `TgTCThue`): `|TgTCThue + TgTThue + Σ TPhi − TGTKCThue − TGTKhac − TgTTTBSo| ≤ 1`.
         - Nhánh B (`TTCKTMai` chưa được trừ vào `TgTCThue`, chỉ áp khi `TTCKTMai > 0`): `|TgTCThue − TTCKTMai + TgTThue + Σ TPhi − TGTKCThue − TGTKhac − TgTTTBSo| ≤ 1`.

### Ánh xạ lỗi `ingest` sang `ReasonCode` hiện có

Chỉ dùng các mã lý do đã chốt tại [agent-runtime.md §5a](../03-agents/agent-runtime.md#5a-danh-mục-mã-lý-do-nguồn-sự-thật):

| Tình huống tại bước `ingest` | Hành động & `ReasonCode` | Mức |
|---|---|---|
| Đúng cùng file đã nạp cho tenant (`(tenant_id, sha256)` đã tồn tại) | **No-op** (trả về hóa đơn đã có; không tạo bản ghi mới, không gắn `DUPLICATE_INVOICE`, không phát `invoice.ingested`) | — |
| Sai XML cú pháp / không thấy node `HDon` / `PBan` ngoài `{2.0.0, 2.0.1, 2.1.0, 2.1.1}` / `DVTTe ≠ "VND"` / thiếu trường định danh tối thiểu (`NBan/MST`, `KHMSHDon`, `KHHDon`, `SHDon`, hoặc thiếu `TgTTTBSo` khi không phải HĐ điều chỉnh thông tin) | Từ chối nhận (`422 XML_UNPARSEABLE`) | — |
| Vi phạm bất kỳ quy tắc số học nào ở Tầng 1, Tầng 2 hoặc Tầng 3 | Lưu hóa đơn + Finding `bot_id = ingest`: **`AMOUNT_MISMATCH`** (không chặn nhận) | 🟡 vàng |
| File khác (`sha256` khác) trùng khóa chống trùng `(NBan/MST, KHMSHDon+KHHDon, int(SHDon))` trong cùng tenant | Qua hộp thư/bill pay: lưu hóa đơn với `duplicate_of` + Finding `ingest`: **`DUPLICATE_INVOICE`**. Qua `POST /m/invoices:upload`: trả `409 DUPLICATE_INVOICE` kèm `existing_invoice_id`, **không lưu** | 🔴 đỏ |
| `NBan/MST` chưa có trong `vendor_registry` của tenant | Lưu hóa đơn + Finding `ingest`: **`UNKNOWN_VENDOR`** | 🟡 vàng |
| Đầu vào là PDF/ảnh không có XML | Lưu hóa đơn + Finding `ingest`: **`NON_XML_SOURCE`** | 🟡 vàng |

*(Lưu ý: kiểm tra `bank_account_on_invoice` khác `vendor_registry` tạo mã đỏ `PAYEE_CHANGE_REQUEST` do `fraud-control` và kiểm tra hệ thống lúc `:complete` thực hiện theo [internal-api.md §4](../05-api/internal-api.md#4-kiểm-tra-hệ-thống-lúc-complete-điều-tra-hóa-đơn).)*

## 5. Mẫu thật hiện có và khoảng trống còn thiếu

**Đã có:**
- **10 file XML hóa đơn thật đã làm sạch** từ 10 `MSTTCGP` khác nhau (gồm hóa đơn GTGT có mã `C`, không mã `K`, máy tính tiền `M`, điều chỉnh giảm âm `TCHDon = 2`, thay thế `TCHDon = 1`, hóa đơn `C` thiếu `MCCQT`, MISA, BKAV, Viettel…) lưu tại [research/claude/einvoice-samples/](research/claude/einvoice-samples/README.md).
- **6 fixture tổng hợp/viết tay** từ các repo mã nguồn mở (đã kiểm tra và xác nhận cả 4 repo trong danh sách ban đầu — `vn-einvoice`, `Invoice-hub`, `tt78-xml-invoice-parser`, `xml-viewer-thue` — đều là fixture tự viết) lưu tại [references/einvoice-samples/](references/einvoice-samples/README.md), dùng riêng để kiểm thử độ chịu lỗi của parser (UTF-8 BOM, prefix `inv:`, default namespace, bọc `HDon/DLieu/DLHDon`, thẻ lệch chuẩn).

**Vẫn còn thiếu (ưu tiên bổ sung khi team có điều kiện):**
1. Một file XML **hóa đơn đầu vào ngành F&B thật** (sữa, cà phê, nguyên liệu pha chế hoặc bao bì).
2. Một file XML thật theo **`PBan = 2.1.1` và chữ ký `XAdES`** (theo QĐ 1233/QĐ-CT).
3. Một file XML thật có **`TTCKTMai` ≠ 0** và/hoặc **`DSLPhi` / `TGTKhac` ≠ 0** để xác minh dứt điểm công thức tổng `TgTTTBSo` theo từng TCGP.
4. Một file XML thật của **EVNHCMC** (tiền điện) và **SAWACO** (tiền nước) để xác minh tên trường `TTKhac` chứa mã khách hàng/danh bộ.

**Quy trình làm sạch khi bổ sung file thật mới vào `references/einvoice-samples/`:**
1. Giữ nguyên cấu trúc, thứ tự thẻ, namespace, `PBan`, `MSTTCGP`, `KHMSHDon`, `KHHDon`, `NLap`, số tiền, `TSuat`, `TChat`, tên `TTruong`.
2. Thay toàn bộ giá trị nhận diện (`Ten`, `MST`, `DChi`, `SDThoai`, `STKNHang`, `MCCQT`, `SHDon`, `DLQRCode`, nội dung nhạy cảm trong `TTKhac`, chứng thư/giá trị chữ ký trong `DSCKS` — chữ ký hỏng là bình thường).
3. Ghi rõ ngành hàng, loại hóa đơn và các phần đã thay trong `README.md`.

Cổng [hoadondientu.gdt.gov.vn](https://hoadondientu.gdt.gov.vn/) có chức năng "Đọc hóa đơn XML" để kiểm tra chéo cấu trúc file XML do `sim-world` sinh ra.
