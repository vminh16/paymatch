# Hóa đơn điện tử XML

Trạng thái: **Định dạng đã trích từ văn bản gốc. Chưa có file thật để đối chiếu.**

## 1. Văn bản gốc

| | |
|---|---|
| Văn bản | **QĐ 1271/QĐ-CT** ngày 30/05/2025 của Cục trưởng Cục Thuế: Quy định về thành phần chứa dữ liệu nghiệp vụ hóa đơn, chứng từ điện tử và phương thức truyền nhận với cơ quan thuế. Hiệu lực từ ngày ký |
| Căn cứ | NĐ 123/2020/NĐ-CP, NĐ 70/2025/NĐ-CP, TT 78/2021/TT-BTC |
| Bản lưu | [references/QD-1271-QD-CT-2025.pdf](references/QD-1271-QD-CT-2025.pdf), sha256 `25ffb73b…2969`, tải từ cdn.thuvienphapluat.vn ngày 26/11/2026 |
| Phần dùng | Phần I mục IV (quy định chung), Phần II mục II khoản 1–2a (hóa đơn GTGT, trang in 85–98), Phụ lục II–VI |

Các bản trước là QĐ 635/2020 và QĐ 1450/2021; hầu hết bài hướng dẫn trên mạng vẫn dẫn QĐ 1450, nên dùng QĐ 1271 làm chuẩn. **Phiên bản thông điệp `PBan` = `2.1.0`**. Hóa đơn cũ có thể còn `2.0.0`; ingest nhận cả hai.

Chưa kiểm: có văn bản nào sau 30/05/2025 sửa QĐ 1271 không (NĐ 254, TT 91 được nhắc trên một số trang tổng hợp).

## 2. Quy định chung

- Tên thẻ viết liền, không dấu, chữ cái đầu mỗi từ viết hoa (ví dụ Dữ liệu hóa đơn → `DLHDon`).
- Số: dấu `.` ngăn phần thập phân, tối đa 6 chữ số thập phân. Độ dài `21,6` = tối đa 21 chữ số, trong đó 6 chữ số thập phân.
- Ngày: `YYYY-MM-DD`. Ngày giờ: `YYYY-MM-DDThh:mm:ss`. Múi giờ GMT+7.
- Mã của cơ quan thuế (`MCCQT`): chuỗi 34 ký tự, chỉ có ở hóa đơn có mã. Hóa đơn khởi tạo từ máy tính tiền: 23 ký tự dạng `M2-25-A1B2C-00001234567`.
- Chữ ký số theo XML Signature (`DSCKS`): `NBan` (người bán), `NMua`, `CQT`, `CCKSKhac`.
- `TTKhac` (thông tin khác, tối đa 500 ký tự) đặt được ở nhiều chỗ, gồm các `TTin` {`TTruong`, `KDLieu`, `DLieu`}. Đây là **phần chữ do người bán tự viết**.

## 3. Cây thẻ hóa đơn GTGT

Bắt buộc: **B**. Bắt buộc nếu có: **B?**. Không bắt buộc: **–**.

```
HDon
├── DLHDon
│   ├── TTChung                      thông tin chung
│   │   ├── PBan        6    B   phiên bản, = 2.1.0
│   │   ├── THDon       100  B   tên hóa đơn ("Hóa đơn giá trị gia tăng")
│   │   ├── KHMSHDon    1    B   ký hiệu mẫu số (Phụ lục II: 1 = GTGT)
│   │   ├── KHHDon      6    B   ký hiệu hóa đơn
│   │   ├── SHDon       8    B?  số hóa đơn
│   │   ├── MHSo        20   B?  mã hồ sơ (hóa đơn cấp mã theo từng lần)
│   │   ├── NLap             B   ngày lập
│   │   ├── HDCTTChinh  1    B   1 = cho thuê tài chính, 0 = không
│   │   ├── SBKe, NBKe       B?  số/ngày bảng kê kèm theo
│   │   ├── DVTTe       3    B   đơn vị tiền tệ (VND)
│   │   ├── TGia        7,2  B   tỷ giá (trừ khi VND)
│   │   ├── HTTToan     50   B   hình thức thanh toán (chữ tự do)
│   │   ├── MSTTCGP     14   B   MST tổ chức cung cấp giải pháp hóa đơn
│   │   ├── MSTDVNUNLHDon, TDVNUNLHDon, DCDVNUNLHDon   B?  đơn vị nhận ủy nhiệm lập
│   │   ├── TTHDLQuan                hóa đơn liên quan (điều chỉnh/thay thế)
│   │   │   ├── TCHDon  1    B   1 thay thế, 2 điều chỉnh, 3 thay thế nhiều, 4 điều chỉnh nhiều, 5 chiết khấu TM
│   │   │   ├── LHDCLQuan, KHMSHDCLQuan, KHHDCLQuan, SHDCLQuan, NLHDCLQuan   B?
│   │   │   ├── SBKCLQuan, NBKCLQuan   B?
│   │   │   └── GChu    255  –
│   │   └── TTKhac
│   ├── NDHDon                       nội dung hóa đơn
│   │   ├── NBan                     người bán
│   │   │   ├── Ten 400 B · MST 14 B · DChi 400 B
│   │   │   ├── MCHang, TCHang       –   mã/tên cửa hàng
│   │   │   ├── SDThoai 20, DCTDTu 50, Fax, Website   –
│   │   │   ├── STKNHang 30, TNHang 400   –   số TK, tên ngân hàng người bán
│   │   │   └── TTKhac
│   │   ├── NMua                     người mua
│   │   │   ├── Ten, MST, DChi       B?
│   │   │   ├── MDVQHNSach 7, CCCDan 12, SHChieu 20   B?
│   │   │   ├── MKHang, SDThoai, DCTDTu, HVTNMHang, STKNHang, TNHang   –
│   │   │   └── TTKhac
│   │   ├── DSHHDVu
│   │   │   └── HHDVu  (lặp, mỗi dòng hàng một thẻ)
│   │   │       ├── TChat   1    B   tính chất (Phụ lục IV)
│   │   │       ├── STT     4    –
│   │   │       ├── MHHDVu  50   B?  mã hàng
│   │   │       ├── THHDVu  500  B   tên hàng
│   │   │       ├── DVTinh  50   B?  đơn vị tính
│   │   │       ├── SLuong  21,6 B?  · DGia 21,6 B?
│   │   │       ├── TLCKhau 6,4  – · STCKhau 21,6 –   chiết khấu theo dòng
│   │   │       ├── ThTien  21,6 B   thành tiền chưa thuế (trừ TChat = 4)
│   │   │       ├── TSuat   11   B?  thuế suất (Phụ lục V)
│   │   │       ├── TTHHDTrung       B nếu TChat = 5 (hàng hóa đặc trưng)
│   │   │       └── TTKhac
│   │   └── TToan                    thanh toán
│   │       ├── THTTLTSuat/LTSuat (lặp theo thuế suất): TSuat, ThTien B, TThue B?
│   │       ├── TgTCThue  B   tổng tiền chưa thuế
│   │       ├── TGTKCThue –   tổng giảm trừ không chịu thuế
│   │       ├── TgTThue   B   tổng tiền thuế
│   │       ├── DSLPhi/LPhi: TLPhi, TPhi   B?  phí, lệ phí
│   │       ├── TTCKTMai  B?  tổng chiết khấu thương mại
│   │       ├── TGTKhac   –   tổng giảm trừ khác
│   │       ├── TgTTTBSo  B   tổng thanh toán bằng số
│   │       ├── TgTTTBChu B   tổng thanh toán bằng chữ (255)
│   │       └── TTKhac
│   └── TTKhac
├── DLQRCode   512  –
├── MCCQT           chỉ hóa đơn có mã
└── DSCKS          NBan · NMua · CQT · CCKSKhac
```

**Danh mục giá trị**

| Thẻ | Giá trị (Phụ lục) |
|---|---|
| `KHMSHDon` | 1 GTGT · 2 bán hàng · 3 bán tài sản công · 4 hàng dự trữ quốc gia · 5 tem/vé/thẻ/phiếu thu · 6 phiếu xuất kho (PL II) |
| `TChat` | 1 hàng hóa, dịch vụ · 2 khuyến mại · 3 chiết khấu thương mại · 4 ghi chú/diễn giải · 5 hàng hóa đặc trưng (PL IV) |
| `TSuat` | `0%` · `5%` · `8%` · `10%` · `KCT` · `KKKNT` · `KHAC:AB.CD%` hoặc `KHAC` (PL V) |
| `KDLieu` trong `TTKhac` | `string` · `numeric` · `dateTime` · `date` (PL III) |
| `LHDCLQuan` | 1 theo NĐ 123/NĐ 70 · 2 có mã xác thực cũ · 3 theo NĐ 51/04 · 4 đặt in theo NĐ 123 (PL VI) |

Cấu trúc 6 ký tự của `KHHDon` không có trong phần đã trích của QĐ 1271. Văn bản dẫn chiếu khoản 1 Điều 4 TT 78/2021, cần đọc TT 78 để chốt.

Văn bản **không có file XML ví dụ hoàn chỉnh**, chỉ có bảng thẻ. Vì vậy vẫn cần file thật (mục 5).

## 4. Ánh xạ sang PayMatch

Tên cột bên trái là dự kiến, chốt khi viết migration. Theo quy tắc "tách số và chữ" ([tools.md §3](../03-agents/tools.md)): trường số và mã do code parse là `trusted`; mọi chữ người bán tự viết là `untrusted`.

| PayMatch (`invoices`, `invoice_lines`) | Thẻ XML | Provenance |
|---|---|---|
| `seller_tax_id` | `NBan/MST` | trusted (đối chiếu `tax_id_lookup`) |
| `symbol` | `KHMSHDon` + `KHHDon` | trusted |
| `number` | `SHDon` | trusted |
| khóa chống trùng | `(NBan/MST, KHMSHDon+KHHDon, SHDon)` | |
| `issued_on` | `NLap` | trusted |
| `buyer_tax_id` | `NMua/MST` (phải là MST của tenant) | trusted |
| `store_hint` | `NMua/DChi`, `NMua/TTKhac` | **untrusted**, chỉ là gợi ý quán nhận hàng |
| `lines[].kind` | `HHDVu/TChat` | trusted |
| `lines[].sku_text`, `name`, `unit` | `MHHDVu`, `THHDVu`, `DVTinh` | **untrusted** (bot procurement ánh xạ sang sku) |
| `lines[].qty`, `unit_price`, `amount`, `vat_rate` | `SLuong`, `DGia`, `ThTien`, `TSuat` | trusted |
| `subtotal`, `vat_total`, `total` | `TgTCThue`, `TgTThue`, `TgTTTBSo` | trusted |
| `bank_account_on_invoice` | `NBan/STKNHang`, `NBan/TNHang` | **untrusted**. Không bao giờ là payee; Gate chỉ trả vào TK `verified` trong vendor registry. Nếu khác TK đã lưu thì đó là tín hiệu cho fraud-control |
| `payment_terms_text` | `HTTToan`, mọi `TTKhac` | **untrusted** |
| `tax_authority_code` | `MCCQT` | trusted (đối chiếu `einvoice_portal`) |
| `einvoice_provider_tax_id` | `MSTTCGP` | trusted |
| `related_invoice` | `TTHDLQuan/*` | trusted. Hóa đơn điều chỉnh/thay thế đi luồng riêng |

**Kiểm tra số học ingest phải làm** (code, không phải LLM):
- `SLuong × DGia − STCKhau = ThTien` mỗi dòng (sai số làm tròn ≤ 1 đồng).
- Σ `ThTien` theo thuế suất = `LTSuat/ThTien`; `TThue` = `ThTien × TSuat`.
- `TgTCThue + TgTThue` khớp `TgTTTBSo` sau khi tính chiết khấu, giảm trừ, phí. Văn bản không ghi công thức này; chốt thứ tự cộng trừ khi có file thật.
- Sai thì gắn reason code ở bước ingest, không chặn nhận hóa đơn.

## 5. File thật còn thiếu

Cần **2–3 file XML hóa đơn đầu vào thật** mà một thành viên team (hoặc công ty quen) đã nhận, ưu tiên mỗi file từ một nhà cung cấp giải pháp khác nhau (`MSTTCGP` khác nhau), vì mỗi bên có thể khác nhau ở `TTKhac`, cách lồng `DLieu`, namespace, chữ ký.

Khi đưa vào `references/einvoice-samples/`:
1. Giữ nguyên cấu trúc, thứ tự thẻ, namespace, `PBan`, `MSTTCGP`.
2. Thay giá trị nhận diện: `Ten`, `MST`, `DChi`, `SDThoai`, `STKNHang`, `MCCQT`, `SHDon`, nội dung `DSCKS` (chữ ký sẽ hỏng, bình thường).
3. Ghi vào `references/einvoice-samples/README.md`: ngành hàng người bán, loại hóa đơn (có mã/không mã), đã thay những gì.

Nguồn mở đã tìm thấy nhưng **chưa mở được** từ môi trường này (GitHub chặn kết nối). Team tải tay rồi kiểm tra xem file là thật hay tự viết:
- [ngoquangthanhphu/vn-einvoice](https://github.com/ngoquangthanhphu/vn-einvoice): parser TT78, fixture tự viết; ghi chú có bên lồng `DLHDon` trong `DLieu`
- [Bunmeooo/Invoice-hub](https://github.com/Bunmeooo/Invoice-hub): có `sample_invoice.xml`
- [ROYCE-8425/tt78-xml-invoice-parser](https://github.com/ROYCE-8425/tt78-xml-invoice-parser): xử lý lỗi namespace prefix, số 0 đầu
- [yeshan-jun/xml-viewer-thue](https://github.com/yeshan-jun/xml-viewer-thue): có file mẫu đi kèm

Cổng [hoadondientu.gdt.gov.vn](https://hoadondientu.gdt.gov.vn/) có chức năng "Đọc hóa đơn XML" để kiểm file sinh ra có hợp lệ về cấu trúc không.
