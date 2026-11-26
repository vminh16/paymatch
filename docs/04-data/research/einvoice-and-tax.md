# Nghiên cứu định dạng XML hóa đơn điện tử GTGT & Tra cứu thuế (Task A)

- **Ngày thực hiện (`retrieved_on`):** `2026-11-26`
- **Phạm vi:** (1) Mẫu XML hóa đơn GTGT thực tế & đặc thù nhà cung cấp (TCGP), đối chiếu cây thẻ trong [../einvoice-xml.md](../einvoice-xml.md); (2) Cấu trúc `KHHDon`, tình trạng hiệu lực `QĐ 1271/QĐ-CT` sau 30/05/2025, thứ tự tính toán `TgTTTBSo`, cấu trúc hóa đơn điều chỉnh/thay thế `TTHDLQuan`; (3) Tra cứu thuế (`tracuunnt.gdt.gov.vn`, danh sách doanh nghiệp rủi ro cao về thuế/hóa đơn, `hoadondientu.gdt.gov.vn`).
- **Thư mục mẫu XML đã lưu:** [../references/einvoice-samples/](../references/einvoice-samples/) (kèm [README.md](../references/einvoice-samples/README.md)).

## Tóm tắt trạng thái theo từng mục

| Mục | Nội dung | Trạng thái | Độ tin cậy |
|---|---|---|---|
| **1** | File XML hóa đơn GTGT thật & đối chiếu cây thẻ `einvoice-xml.md` | 🟡 Partial | Cao về đặc thù parser & đối chiếu `QĐ 1271`; **thiếu 2–3 file XML sản xuất thật** từ các TCGP |
| **2a** | Cấu trúc 6 ký tự `KHHDon` (TT 78/2021 → TT 32/2025 → TT 91/2026) | ✅ Verified | Cao (văn bản pháp luật + `hoadondientu.gdt.gov.vn`) |
| **2b** | Hiệu lực `QĐ 1271/QĐ-CT` sau 30/05/2025 (`QĐ 1306`, `QĐ 1233`, `NĐ 254/2026`, `TT 91/2026`) | ✅ Verified (toàn văn PDF `QĐ 1233` 🟡 chưa tải trực tiếp) | Cao về hiệu lực & mốc chuyển tiếp (`vanban.chinhphu.vn`, `hoadondientu.gdt.gov.vn`, M-Invoice) |
| **2c** | Thứ tự số học ra `TgTTTBSo` (chiết khấu thương mại, phí/lệ phí, giảm trừ) | 🟡 Partial | Trung bình–Cao về công thức chung; **chưa xác minh trên file XML sản xuất thật có chiết khấu/phí** quy ước dấu `TChat=3` và `TTCKTMai` theo từng TCGP |
| **2d** | Cấu trúc hóa đơn điều chỉnh / thay thế (`TTHDLQuan`) | ✅ Verified | Cao (`QĐ 1271` PDF gốc + `hoadondientu.gdt.gov.vn` JS + `odoo/odoo l10n_vn_edi_viettel`) |
| **3a** | Mã trạng thái MST trên `tracuunnt.gdt.gov.vn` (`00`–`10`, không có `08`) | ✅ Verified | Cao (Báo Điện tử Chính phủ `14/09/2026`, `TT 86/2024/TT-BTC`, `TT 90/2026/TT-BTC`) |
| **3b** | Danh sách doanh nghiệp rủi ro cao về thuế/hóa đơn | 🟡 Partial | Trung bình (chủ yếu nguồn thứ cấp & công văn; chưa tải trực tiếp file Excel mẫu từ `gdt.gov.vn`/`tracuuhoadon.gdt.gov.vn` do lỗi SSL intermediate CA) |
| **3c** | Kết quả trả về của `hoadondientu.gdt.gov.vn` (`tthai`, `ttxly`, `tchat`, `bhphap`, tra cứu công khai) | ✅ Verified | Rất cao (trích xuất trực tiếp từ bundle JS chính thức trên `hoadondientu.gdt.gov.vn` ngày `2026-11-26`) |

---

## Mục 1. File XML hóa đơn GTGT & đối chiếu cây thẻ `einvoice-xml.md`

### 1.1. Kết quả kiểm tra các kho mã nguồn mở & cổng nhà cung cấp

Đã kiểm tra toàn bộ 4 repo được giao, mở rộng tìm kiếm thêm 4 repo hóa đơn điện tử Việt Nam khác trên GitHub (`dieutx/hddt-downloader-windows`, `BinhPhan75/hoadondientu`, `tranhoangtu-it/peppol-ubl-einvoice-parser`, `odoo/odoo` module `l10n_vn_edi_viettel`) và kiểm tra tài liệu công khai của 6 nhà cung cấp giải pháp (MISA meInvoice, Viettel S-Invoice, VNPT Invoice, BKAV eHoadon, EasyInvoice/Softdreams, M-Invoice).

**Phát hiện quan trọng:** **0/8 repo công khai chứa file XML hóa đơn sản xuất thật** (xuất trực tiếp từ CQT/TCGP có đủ `MSTTCGP` thật, chữ ký số `DSCKS` đầy đủ `NBan` + `CQT` với `X509Certificate`/`SignatureValue`, và `MCCQT` 34 ký tự). Các repo xử lý hóa đơn thật đều cấm commit file XML khách hàng thật vì lý do bảo mật dữ liệu thuế (ví dụ `BinhPhan75/hoadondientu/docs/matbao-xml-lookup.md` và `dieutx/hddt-downloader-windows/docs/HAR_ANALYSIS.md`). Cổng tra cứu của 6 TCGP đều yêu cầu mã tra cứu/tài khoản doanh nghiệp để tải file XML thật.

Tuy nhiên, **8 fixture XML tổng hợp/viết tay** từ các repo trên cùng mã nguồn parser sản xuất của `dieutx/hddt-downloader-windows`, `BinhPhan75/hoadondientu` và `Bunmeooo/Invoice-hub` đã làm rõ hàng loạt sai lệch thực tế và đặc thù theo từng TCGP:

| Nguồn & File | Thật hay viết tay | `MSTTCGP` | `DSCKS` | `MCCQT` | Namespace | `PBan` | Lồng `TTKhac`/`DLieu` & đặc thù |
|---|---|---|---|---|---|---|---|
| `ngoquangthanhphu/vn-einvoice` :: `test/fixtures/invoice-vat.xml` (lưu: `vn-einvoice-vat.xml`) | Viết tay / tổng hợp (MST giả `0100000001`, `0300000002`) | Không | Không | Có (giả 32 ký tự hex, thuộc tính `Id="data"`, đặt dưới `HDon`) | Không | `2.0.1` | `<DLHDon Id="data">`; có thẻ thừa `<MauSo>1</MauSo>`; `<DVTTe>` bị lồng sai thành `<DVTTe><Ma>VND</Ma><Ten>...</Ten></DVTTe>` thay vì text `VND`. |
| `ngoquangthanhphu/vn-einvoice` :: `test/fixtures/invoice-cash-register.xml` (lưu: `vn-einvoice-cash-register.xml`) | Viết tay / tổng hợp (`0400000003`) | Không | Không | Có (giả 32 ký tự hex — **sai định dạng MTT** chuẩn 23 ký tự `M1-26-...`) | Không | `2.0.1` | Bọc `<DLHDon>` trong `<HDon><DLieu><DLHDon>`; `KHHDon=C26MAA`; các thẻ `NMua` rỗng; `<DVTTe><Ma>/<Ten>` lồng sai. |
| `Bunmeooo/Invoice-hub` :: `sample_invoice.xml` (lưu bản đã làm sạch: `invoice-hub-sample-sanitized.xml`) | Viết tay (bản gốc dùng tên & MST DN thật, không phải file xuất từ TCGP) | Không | Không | Không | Không | `2.0.0` | Nhiều thẻ sai chuẩn QĐ 1450/1271: `<KHMHDon>` (thiếu `S`), `<DSHangHoa>` (thay cho `DSHHDVu`), `<TThue>` đặt thẳng trong `<HHDVu>`, `<TgTTToan>` (thay cho `TgTTTBSo`), thiếu `TChat`, `TgTTTBChu`. |
| `ROYCE-8425/tt78-xml-invoice-parser` :: inline `test.mjs` (lưu: `tt78-parser-ns-prefix.xml`) | Viết tay / tổng hợp tối giản (`Cong ty A`/`B`) | Không | Không | Không | Prefix `xmlns:inv="http://example.vn"` trên `<inv:HDon>` | Không | Có UTF-8 BOM `\uFEFF` đầu file; `SHDon=00001234` và `MST` giữ số `0` đầu; thiếu `PBan`, `THDon`, `DVTTe`, `HTTToan`, `TgTTTBChu`. |
| `yeshan-jun/xml-viewer-thue` :: `examples/sample-invoice.xml` (lưu: `xml-viewer-thue-sample.xml`) | Viết tay / tổng hợp (`0101234567`, `0312345678`) | Không | Có khung giả `<DSCKS><NBan><Signature>` (chỉ có `SignatureMethod` và `X509SubjectName`, thiếu `Reference`, `DigestValue`, `SignatureValue`, `X509Certificate`, `SigningTime`) | Không | `xmlns="http://www.w3.org/2000/09/xmldsig#"` trên `<Signature>` | `2.1.0` | Thiếu `HDCTTChinh`, `MSTTCGP`, `TChat`, `THTTLTSuat`, `TgTTTBChu`. |
| `dieutx/hddt-downloader-windows` :: `tests/fixtures/sample-invoice.xml` (lưu: `hddt-downloader-sample.xml`) | Viết tay / tổng hợp (`0101111111`, `0302222222`) | Giả (`0100000000`) | Không | Giả (`ABC123`), **đặt sai vị trí** bên trong `<DLHDon>` thay vì trực thuộc `<HDon>` | Default `xmlns="urn:example:invoice"` trên `<HDon>` | Không | `<DLHDon Id="INV-001">`; `KHHDon=C26TABC` (**7 ký tự — sai chuẩn 6 ký tự**); `<TThue>` đặt thẳng trong `<HHDVu>`; thiếu `PBan`, `THDon`, `HTTToan`, `TChat`. |
| `tranhoangtu-it/peppol-ubl-einvoice-parser` :: inline `VN_GDT_XML` trong `test/parser.test.js` | Viết tay / tổng hợp (`0316889900`, `0109887766`) | Không | Không | Không | Không | `2.0.1` | `<DLHDon Id="ID1">`; có `<THTTLTSuat><LTSuat>`; thiếu `THDon`, `MSTTCGP`, `TChat`, `TgTTTBChu`. |
| `BinhPhan75/hoadondientu` :: inline `SAMPLE_MISA_XML` & `SAMPLE_VIETTEL_XML` trong `examples/demo.ts` | Viết tay / tổng hợp minh họa driver | `0101243150` (MISA), `0100109106` (Viettel) | Không | Không | Không | `2.0.0` | **Bỏ qua cả `<DLHDon>` và `<NDHDon>`** (`<HDon><TTChung>...<NBan>...`); `KHHDon=1C24TGT` (gộp nhầm `KHMSHDon` vào `KHHDon`); `NLap` dùng `dateTime` thay vì `date`; `<TTKhac><TTin>` thiếu `<KDLieu>`. |

### 1.2. Đặc thù thực tế theo nhà cung cấp giải pháp (`MSTTCGP` & `TTKhac` & cấu trúc)

Tổng hợp từ mã nguồn sản xuất của các công cụ đọc XML tải trực tiếp từ `hoadondientu.gdt.gov.vn` (`dieutx/hddt-downloader-windows/src/LinkTraCuu.ps1`, `src/XmlParser.ps1`; `BinhPhan75/hoadondientu/src/services/invoice-engine/drivers/*.ts`; `Bunmeooo/Invoice-hub/parser.py`; `ngoquangthanhphu/vn-einvoice/src/parser.ts`; `ROYCE-8425/tt78-xml-invoice-parser/index.mjs`):

| Nhà cung cấp giải pháp (TCGP) | `MSTTCGP` xác minh | Trường `TTKhac/TTin/TTruong` (hoặc thuộc tính) chứa mã tra cứu | Đặc thù / Lưu ý khi parse |
|---|---|---|---|
| **MISA meInvoice** | `0101243150` (CTCP MISA) | `TransactionID`, `Mã tra cứu`, `MaTraCuu`, `MTCuu`, `LookupCode` | Cổng tra cứu: `https://www.meinvoice.vn/tra-cuu/`. `TTKhac` thường gắn ở `DLHDon/TTKhac` hoặc `TTChung/TTKhac`. |
| **Viettel S-Invoice** | `0100109106` (Tập đoàn Viettel) | `Mã số bí mật`, `reservationCode`, `ReservationCode`, `MaBiMat` | Cổng chung `https://vinvoice.viettel.vn/utilities/invoice-search`; một số doanh nghiệp lớn (VETC, VDTC) có cổng riêng dù chung `MSTTCGP`. |
| **VNPT Invoice** | `0100684378` (Tập đoàn VNPT) *(lưu ý: `0100686209` là MobiFone, nhưng một số repo cộng đồng như `Bunmeooo/parser.py` và `BinhPhan75/VnptDriver.ts` gán nhầm `0100686209` cho VNPT)* | `Fkey` (trong `TTKhac`), hoặc dùng trực tiếp `MCCQT` | Cổng tra cứu theo từng cụm (`portaltool-miennam.vnpt-invoice.com.vn` hoặc cổng riêng từng DN như Petrolimex, Vingroup). |
| **BKAV eHoadon** | `0101360697` (CTCP BKAV) | Thuộc tính `Id` của thẻ `<DLHDon Id="...">` (`InvoiceGUID`); đôi khi `TTKhac`: `Mã nhận hóa đơn`, `Mã tra cứu` | URL tra cứu ghép trực tiếp: `https://van.ehoadon.vn/Lookup?InvoiceGUID=<DLHDon/@Id>`. |
| **EasyInvoice (Softdreams)** | `0105987432` (CTCP ĐT CN & TM Softdreams — xác minh trong `dieutx/LinkTraCuu.ps1`; `Bunmeooo/parser.py` ghi `0311226265` — chưa xác minh chéo) | `Fkey`, `Ikey`, `Mã tra cứu`, `MaTraCuu` | Cổng chung `https://tracuu.easyinvoice.vn/Search/Index` và cổng theo MST người bán `https://<mst>hd.easyinvoice.com.vn/Search/Index`. |
| **M-Invoice** | `0106026495` (và chi nhánh `0106026495-001`) | `Mã tra cứu`, `Số bảo mật`, `SoBaoMat`, `CheckCode` | Cổng tra cứu: `https://tracuuhoadon.minvoice.com.vn/single/invoice`. |

**Các biến thể cấu trúc XML thực tế mà bộ ingest PayMatch phải xử lý:**
1. **Lớp vỏ gói thông điệp (`TDiep/DLieu`):** Theo `QĐ 1271/QĐ-CT` Phần I mục IV.5 (trang 7–9), khi truyền nhận với CQT, `<HDon>` nằm trong `<TDiep><DLieu><HDon>...</HDon></DLieu></TDiep>`. Ngoài ra `ngoquangthanhphu/vn-einvoice` ghi nhận trường hợp `<HDon><DLieu><DLHDon>...</DLHDon></DLieu></HDon>`. Parser cần tìm node có `local-name() == 'HDon'` và cho phép `<DLHDon>` nằm trực tiếp dưới `HDon` hoặc dưới `HDon/DLieu`.
2. **Namespace & UTF-8 BOM:** File có thể có BOM `\uFEFF`, default namespace (`xmlns="..."`), prefix (`<inv:HDon>`, `<ds:Signature>`), và chữ ký dùng `xmlns="http://www.w3.org/2000/09/xmldsig#"`. Parser **bắt buộc** bỏ BOM và truy vấn theo `local-name()` (tách phần sau `:` hoặc `{uri}`), không match tên thẻ có prefix cố định.
3. **Tiền thuế & thành tiền có thuế theo từng dòng hàng:** Trong chuẩn `QĐ 1271`, `<HHDVu>` **không có** thẻ con `<TThue>` hay `<THTienCoVAT>`. Thực tế các TCGP nhét thông tin này vào `<HHDVu><TTKhac><TTin>` với nhiều tên `TTruong` khác nhau (xác minh trong `dieutx/LinkTraCuu.ps1` & `XmlParser.ps1`): `TThueVAT`, `Tiền thuế`, `VATAmount`, `TongTien_Thue`, `Tiền thuế dòng (Tiền thuế GTGT)`, `TienThueGTGT`, `ThueGTGT`; và `THTienCoVAT`, `Thành tiền có thuế`, `Amount`, `TongTien_CoThue`, `ThanhTienCoVAT`.
4. **Giữ nguyên số `0` ở đầu & định dạng số:** `SHDon` (ví dụ `00001234`), `MST` (ví dụ `0101243150`), `KHMSHDon` phải luôn parse dạng `string`, không ép sang integer. Dù chuẩn `QĐ 1271` quy định dấu `.` ngăn phần thập phân, parser thực tế (`dieutx/XmlParser.ps1`, `Bunmeooo/parser.py`) vẫn xử lý dự phòng dấu `,` ở file cũ/lệch chuẩn.
5. **Chữ ký số & `DLHDon/@Id`:** `DSCKS/NBan/Signature` ký lên `#<DLHDon/@Id>` (và `Signature/Object`); `DSCKS/CQT/Signature` ký lên `DLHDon`, `MCCQT` và `Signature/Object`. Thời điểm ký nằm ở `Signature/Object/SignatureProperties/SignatureProperty/SigningTime` (`QĐ 1271` trang 6–7, 100).

### 1.3. Đối chiếu từng điểm sai lệch với cây thẻ trong `docs/04-data/einvoice-xml.md`

So sánh trực tiếp cây thẻ ở [../einvoice-xml.md §3](../einvoice-xml.md#3-cây-thẻ-hóa-đơn-gtgt) với **bản gốc `QD-1271-QD-CT-2025.pdf` (trang 88–100)**, **QĐ 1233/QĐ-CT (27/08/2026)** và **mã nguồn `hoadondientu.gdt.gov.vn` (module `70234`)**:

| Vị trí trong `einvoice-xml.md` | Nội dung hiện tại trong `einvoice-xml.md` | Thực tế theo `QĐ 1271` PDF / `QĐ 1233` / GDT | Mức độ ảnh hưởng |
|---|---|---|---|
| `§1` (dòng 14) `PBan` | `2.1.0`; cũ `2.0.0` | Thiếu **`2.0.1`** (QĐ 1510/QĐ-TCT, vẫn phổ biến) và **`2.1.1`** (QĐ 1233/QĐ-CT từ 27/08/2026, song song với `2.1.0` đến 31/12/2026). | Cao — ingest phải nhận `2.0.0`, `2.0.1`, `2.1.0`, `2.1.1`. |
| `§3` `TTChung/TTHDLQuan` (dòng 51–53) | Liệt kê `SBKCLQuan, NBKCLQuan` trước `GChu`; không có `MSTCLQuan` | Trong `QĐ 1271` PDF (trang 93–94), thứ tự đúng là **`GChu` đứng TRƯỚC `SBKCLQuan`, `NBKCLQuan`**. Trong `QĐ 1233/QĐ-CT`, bổ sung thẻ **`MSTCLQuan`** bên trong `TTHDLQuan`. Ngoài ra `KHMSHDCLQuan` dài tối đa **11**, `KHHDCLQuan` tối đa **8**, `SHDCLQuan` tối đa **8**. | Trung bình (quan trọng khi sinh XML chuẩn theo XSD/thứ tự thẻ). |
| `§3` `NDHDon/NBan` (dòng 59–60) | Liệt kê `SDThoai, DCTDTu, Fax, Website` rồi mới tới `STKNHang, TNHang` | Trong `QĐ 1271` PDF (trang 94), thứ tự đúng là **`STKNHang`, `TNHang` đứng TRƯỚC `Fax`, `Website`**. | Trung bình (ảnh hưởng thứ tự thẻ khi sim-world sinh XML). |
| `§3` `NDHDon/NMua` (dòng 63–65) | Nhóm `Ten, MST, DChi` → `MDVQHNSach, CCCDan, SHChieu` → `MKHang, SDThoai, ...` | Trong `QĐ 1271` PDF (trang 95), thứ tự đúng là: `Ten, MST, MDVQHNSach, DChi, MKHang, SDThoai, CCCDan, SHChieu, DCTDTu, HVTNMHang, STKNHang, TNHang, TTKhac`. | Trung bình (ảnh hưởng thứ tự thẻ khi sinh XML). |
| `§3` `HHDVu/TTHHDTrung` (dòng 78) | Chỉ ghi tên thẻ `TTHHDTrung` | Trong `QĐ 1271` PDF (trang 97, Phụ lục XV trang 316), cấu trúc con là `TTHHDTrung/TTin/{LHHDTrung (1), TTruong (20), DLieu (200)}`. Trên `PBan=2.1.1` (`hoadondientu.gdt.gov.vn` module `70234`), `LHHDTrung=1` (ô tô/mô tô) mở rộng từ 2 trường (`SKhung, SMay`) lên 17 trường. | Thấp với F&B (ít gặp `TChat=5`), nhưng nên ghi đúng để parser không lỗi. |
| `§3` `DSHHDVu` & `TToan` (dòng 67, 80) | Không ghi điều kiện tùy chọn | `QĐ 1271` PDF (trang 96, 98) ghi rõ: `DSHHDVu` **không bắt buộc** nếu hóa đơn điều chỉnh không điều chỉnh hàng hóa; `TToan` **không bắt buộc** nếu hóa đơn điều chỉnh không làm thay đổi thông tin thanh toán. | Cao — parser không được crash khi thiếu `DSHHDVu`/`TToan` trên hóa đơn điều chỉnh thông tin. |
| `§3` Danh mục `KHMSHDon` (dòng 101) | Chỉ liệt kê `1`–`6` | Theo `NĐ 70/2025`, `TT 32/2025`, `TT 91/2026` và `hoadondientu.gdt.gov.vn` JS (`er`), có thêm **`7`** (Hóa đơn thương mại), **`8`** (HĐĐT GTGT tích hợp biên lai thu thuế, phí, lệ phí), **`9`** (HĐĐT bán hàng tích hợp biên lai). | Trung bình — giúp nhận diện đúng hóa đơn thương mại/tích hợp biên lai. |
| `§3` Bọc `TDiep/DLieu` | Không nhắc trong cây thẻ | File tải từ cổng CQT hoặc kênh T-VAN có thể bọc `<TDiep><TTChung>...</TTChung><DLieu><HDon>...</HDon></DLieu></TDiep>` (QĐ 1271 trang 7–9). | Cao — parser ingest phải unwrap `TDiep/DLieu` nếu có. |

### 1.4. Nguồn (Mục 1)

| URL | Publisher | Ngày tài liệu | `retrieved_on` |
|---|---|---|---|
| `docs/04-data/references/QD-1271-QD-CT-2025.pdf` (lưu cục bộ, bản gốc Cục Thuế) | Cục Thuế (Bộ Tài chính) | 2025-05-30 | 2026-11-26 |
| https://github.com/ngoquangthanhphu/vn-einvoice | GitHub (`ngoquangthanhphu`) | 2026-10-22 | 2026-11-26 |
| https://github.com/Bunmeooo/Invoice-hub | GitHub (`Bunmeooo`) | 2026-08-27 | 2026-11-26 |
| https://github.com/ROYCE-8425/tt78-xml-invoice-parser | GitHub (`ROYCE-8425`) | 2026-11-18 | 2026-11-26 |
| https://github.com/yeshan-jun/xml-viewer-thue | GitHub (`yeshan-jun`) | 2026-08-07 | 2026-11-26 |
| https://github.com/dieutx/hddt-downloader-windows | GitHub (`dieutx`) | 2026-11-10 | 2026-11-26 |
| https://github.com/BinhPhan75/hoadondientu | GitHub (`BinhPhan75`) | 2026-11-23 | 2026-11-26 |
| https://github.com/tranhoangtu-it/peppol-ubl-einvoice-parser | GitHub (`tranhoangtu-it`) | 2026-11-22 | 2026-11-26 |
| https://hoadondientu.gdt.gov.vn/ (`/_next/static/chunks/pages/_app-755f01fff0623a8a.js`) | Cục Thuế (Cổng HĐĐT chính thức) | 2026 (live) | 2026-11-26 |

### 1.5. Khoảng trống còn lại & Đề xuất chỉnh sửa docs (Mục 1)

- **Khoảng trống:** Vẫn thiếu **2–3 file XML hóa đơn GTGT sản xuất thật** (đã xóa thông tin nhận diện) từ các TCGP khác nhau (ưu tiên MISA `0101243150`, Viettel `0100109106`, VNPT `0100684378` hoặc EasyInvoice `0105987432`) để xác minh 100% cấu trúc `DSCKS` thực tế, `TTKhac` thực tế, và trường hợp có chiết khấu/phí. Ngoài ra, chưa xác minh chéo MST `0311226265` trong `Bunmeooo/parser.py` so với `0105987432` (Softdreams/EasyInvoice).
- **Đề xuất sửa `docs/04-data/einvoice-xml.md` (chỉ đề xuất, chưa sửa):**
  1. Cập nhật `§1` cho phép `PBan` nhận cả `2.0.0`, `2.0.1`, `2.1.0`, `2.1.1`.
  2. Chỉnh lại thứ tự thẻ trong `§3` cho đúng `QĐ 1271` (`TTHDLQuan`: `GChu` trước `SBKCLQuan`/`NBKCLQuan`, thêm ghi chú `MSTCLQuan` theo `QĐ 1233`; `NBan`: `STKNHang`/`TNHang` trước `Fax`/`Website`; `NMua`: đúng thứ tự 13 thẻ).
  3. Ghi chú rõ `DSHHDVu` và `TToan` là tùy chọn trên hóa đơn điều chỉnh thông tin; bổ sung `KHMSHDon` `7`, `8`, `9` và lớp bọc `TDiep/DLieu`.
  4. Cập nhật `§5`: các repo GitHub mở được đã xác minh toàn bộ là fixture viết tay/tổng hợp (đã lưu vào `references/einvoice-samples/`), vẫn cần team cung cấp 2–3 file XML đầu vào thật.

---

## Mục 2. Bốn câu hỏi pháp lý & kỹ thuật về hóa đơn điện tử

### 2a. Cấu trúc 6 ký tự của `KHHDon` (TT 78/2021 → TT 32/2025 → TT 91/2026)

**Kết quả:**
Trong XML, ký hiệu mẫu số (`KHMSHDon`, 1 chữ số) và ký hiệu hóa đơn (`KHHDon`, 6 ký tự) là **2 thẻ tách riêng** (trên bản thể hiện PDF thường ghép liền 7 ký tự, ví dụ `1C26TAA`).

Theo **Khoản 1 Điều 4 Thông tư 78/2021/TT-BTC** (đã được thay thế bởi **Thông tư 32/2025/TT-BTC** hiệu lực 01/06/2025, và tiếp tục được thay thế bởi **Thông tư 91/2026/TT-BTC** ban hành 30/06/2026, hiệu lực 01/07/2026 — Điều 4 & Phụ lục I), nhóm **6 ký tự `KHHDon`** có cấu trúc `[Vị trí 1][Vị trí 2–3][Vị trí 4][Vị trí 5–6]`:

1. **Ký tự thứ 1 (1 chữ cái — hình thức có mã/không mã):**
   - `C`: Hóa đơn điện tử **có mã** của cơ quan thuế.
   - `K`: Hóa đơn điện tử **không có mã** của cơ quan thuế.
2. **Ký tự thứ 2 và thứ 3 (2 chữ số Ả-rập — năm lập hóa đơn):**
   - Hai chữ số cuối của năm dương lịch lập hóa đơn (ví dụ: năm 2025 là `25`, năm 2026 là `26`).
3. **Ký tự thứ 4 (1 chữ cái — loại hóa đơn điện tử sử dụng):**
   - **8 chữ cái gốc theo TT 78/2021/TT-BTC:**
     - `T`: Hóa đơn điện tử do doanh nghiệp, tổ chức, hộ, cá nhân kinh doanh đăng ký sử dụng với CQT.
     - `D`: Hóa đơn bán tài sản công, hóa đơn bán hàng dự trữ quốc gia, hoặc hóa đơn điện tử đặc thù không nhất thiết có một số tiêu thức do DN/tổ chức đăng ký sử dụng.
     - `L`: Hóa đơn điện tử của CQT cấp theo từng lần phát sinh.
     - `M`: Hóa đơn điện tử được khởi tạo từ **máy tính tiền**.
     - `N`: Phiếu xuất kho kiêm vận chuyển nội bộ điện tử.
     - `B`: Phiếu xuất kho hàng gửi bán đại lý điện tử.
     - `G`: Tem, vé, thẻ điện tử là hóa đơn GTGT.
     - `H`: Tem, vé, thẻ điện tử là hóa đơn bán hàng.
   - **Bổ sung từ 01/06/2025 (TT 32/2025/TT-BTC):**
     - `X`: **Hóa đơn thương mại điện tử** (thường đi với `KHMSHDon = 7`, ví dụ `7K26XAA`).
   - **Bổ sung từ 01/07/2026 (TT 91/2026/TT-BTC, Phụ lục I):**
     - `F`: **Hóa đơn giá trị gia tăng kiêm tờ khai hoàn thuế**.
4. **Ký tự thứ 5 và thứ 6 (2 ký tự — quản lý nội bộ của người bán):**
   - Gồm 2 chữ cái in hoa do người bán tự chọn theo nhu cầu quản lý (nếu không có nhu cầu quản lý riêng thì thể hiện là `YY`). *(Lưu ý: danh sách chính xác 20 chữ cái loại trừ F, J, W, Z trong TT 78/2021 và việc TT 91/2026 có thay đổi tập ký tự vị trí 5–6 hay không hiện chưa đối chiếu được toàn văn OCR của Phụ lục I TT 91/2026 → đánh dấu "chưa xác minh" về tập ký tự chính xác của vị trí 5–6 dưới TT 91/2026).*

**Regex đề xuất cho ingest (chấp nhận mọi hóa đơn hợp lệ đến 2026):** `^[CK]\d{2}[TDLMNBGHXF][A-Z0-9]{2}$` (với hóa đơn GTGT B2B thông thường của nhà cung cấp F&B sẽ rơi vào `^[CK]\d{2}[TM][A-Z]{2}$`).

**Nguồn (2a):**

| URL | Publisher | Ngày tài liệu | `retrieved_on` |
|---|---|---|---|
| https://vanban.chinhphu.vn/?pageid=27160&docid=219006 | Cổng TTĐT Chính phủ (`Thông tư 91/2026/TT-BTC`, đính kèm `91-btc.signed.pdf`) | 2026-06-30 | 2026-11-26 |
| https://vbpl.vn/en/van-ban/chi-tiet/thong-tu-so-91-2026-tt-btc-quy-dinh-mot-so-dieu-cua-luat-quan-ly-thue-va-nghi-dinh-so-254-2026-nd-cp-cua-chinh-phu-quy-dinh-chi-tiet-mot-so-dieu-va-bien-phap-de-to-chuc-huong-dan-thi-hanh-luat-quan-ly-thue-so-108-2025-qh15-ve-hoa-don-dien-tu-chung-tu-dien-tu--8741d070-8037-11f1-8cce-cd2715c99e42 | Cơ sở dữ liệu quốc gia về văn bản pháp luật (VBPL) | 2026-06-30 | 2026-11-26 |
| https://thuvienphapluat.vn/van-ban/Thue-Phi-Le-Phi/Thong-tu-91-2026-TT-BTC-huong-dan-Luat-Quan-ly-thue-va-Nghi-dinh-254-2026-ND-CP-699151.aspx | Thư viện Pháp luật | 2026-06-30 | 2026-11-26 |
| https://ihoadon.vn/hddt/hoa-don-dien-tu-tai-thong-tu-91-2026-tt-btc.html | EFY iHoadon (nguồn thứ cấp / nhà cung cấp TCGP) | 2026-07 | 2026-11-26 |
| https://thuvienphapluat.vn/hoi-dap-phap-luat/toan-bo-ky-hieu-hoa-don-dien-tu-theo-thong-tu-782021ttbtc-moi-nhat-2024-138019419.html | Thư viện Pháp luật (tóm tắt Điều 4 TT 78/2021) | 2024 | 2026-11-26 |

- **Độ tin cậy:** Cao (✅ Verified cho 10 chữ cái vị trí 4 và toàn bộ cấu trúc 6 ký tự; 🟡 chưa xác minh tập ký tự loại trừ chính xác ở vị trí 5–6 trong bản PDF scan `91-btc.signed.pdf`).
- **Đề xuất sửa `docs/04-data/einvoice-xml.md`:** Bổ sung bảng giải mã 6 ký tự `KHHDon` (đủ 10 chữ cái `T, D, L, M, N, B, G, H, X, F`) vào `§3`, xóa dòng *"Cấu trúc 6 ký tự của `KHHDon` không có... cần đọc TT 78 để chốt"*.

---

### 2b. `QĐ 1271/QĐ-CT` (30/05/2025) có bị sửa đổi hay thay thế sau 30/05/2025 không?

**Kết quả:** **CÓ — `QĐ 1271/QĐ-CT` ĐÃ HẾT HIỆU LỰC TOÀN BỘ**, đã bị thay thế liên tiếp **2 lần** trong giai đoạn 2025–2026:

```
NĐ 123/2020 + TT 78/2021
  ├── QĐ 1450/QĐ-TCT (07/10/2021, PBan 2.0.0)
  └── QĐ 1510/QĐ-TCT (21/09/2022, PBan 2.0.1)
        ↓
NĐ 70/2025/NĐ-CP (20/03/2025, hiệu lực 01/06/2025) + TT 32/2025/TT-BTC (31/05/2025, hiệu lực 01/06/2025)
  ├── QĐ 1271/QĐ-CT (30/05/2025, PBan 2.1.0)  ← [HẾT HIỆU LỰC sau 14 ngày]
  └── QĐ 1306/QĐ-CT (13/06/2025, PBan 2.1.0)  ← [thay thế QĐ 1271; nay ĐÃ HẾT HIỆU LỰC]
        ↓
Luật Quản lý thuế số 108/2025/QH15 + NĐ 254/2026/NĐ-CP (30/06/2026, hiệu lực 01/07/2026)
  + TT 91/2026/TT-BTC (30/06/2026, hiệu lực 01/07/2026, thay thế TT 32/2025)
  └── QĐ 1233/QĐ-CT (27/08/2026, hiệu lực từ ngày ký) ← [ĐANG CÓ HIỆU LỰC, thay thế QĐ 1306/QĐ-CT]
```

**Các thay đổi kỹ thuật đã xác minh của `QĐ 1233/QĐ-CT` (27/08/2026) và lộ trình chuyển tiếp:**
1. **Phiên bản thông điệp `PBan`:** Giới thiệu phiên bản **`2.1.1`**. Hệ thống thông tin quản lý thuế tiếp nhận **song song `2.1.0` và `2.1.1`** trong thời gian chuyển tiếp; **`2.1.0` được tiếp nhận đến hết ngày `31/12/2026`** (hoàn thành nâng cấp trước `01/01/2027`). *(Lưu ý cho demo PayMatch `03/12/2026`: rơi đúng vào giai đoạn chuyển tiếp song song `2.1.0` và `2.1.1`!)*
2. **Chuẩn chữ ký số:** Chuyển đổi từ **DSig (`XMLDSig`) sang `XAdES`**; hệ thống tiếp nhận song song `DSig` đến hết ngày **`09/04/2027`** (hoàn thành nâng cấp trước `10/04/2027`).
3. **Thay đổi thẻ XML đã xác minh:**
   - Bổ sung thẻ **`MSTCLQuan`** bên trong `TTHDLQuan` (bắt buộc khi lập hóa đơn điều chỉnh/thay thế cho hóa đơn đã lập của đơn vị bị chia, tách, sáp nhập, hợp nhất).
   - Mở rộng `TTHHDTrung` cho `LHHDTrung = 1` (xe ô tô/mô tô) trên phiên bản `2.1.1` từ 2 trường (`SKhung, SMay`) lên **17 trường** (xác minh trực tiếp từ `hoadondientu.gdt.gov.vn` module `70234`).
   - Dẫn chiếu pháp lý cập nhật sang điểm 8 Phụ lục `NĐ 254/2026/NĐ-CP` (đơn vị tiền tệ) và Điều 10 & khoản 2 Điều 24 `TT 91/2026/TT-BTC` (xử lý hóa đơn có sai sót).
   - Định dạng số (`tối đa 21 chữ số, phần thập phân tối đa 6 chữ số`), ngày (`YYYY-MM-DD`), ngày giờ (`YYYY-MM-DDThh:mm:ss`, `GMT+7`), encoding (`UTF-8`) giữ nguyên so với `QĐ 1271`.

**Nguồn (2b):**

| URL | Publisher | Ngày tài liệu | `retrieved_on` |
|---|---|---|---|
| https://vanban.chinhphu.vn/?pageid=27160&docid=218689 | Cổng TTĐT Chính phủ (`Nghị định 254/2026/NĐ-CP`, đính kèm `254-ndcp.signed.pdf`) | 2026-06-30 | 2026-11-26 |
| https://vanban.chinhphu.vn/?pageid=27160&docid=219006 | Cổng TTĐT Chính phủ (`Thông tư 91/2026/TT-BTC`, đính kèm `91-btc.signed.pdf`) | 2026-06-30 | 2026-11-26 |
| https://minvoice.vn/quyet-dinh-1233-qd-ct-quy-dinh-moi-ve-du-lieu-hoa-don-chung-tu-dien-tu/ | M-Invoice (TCGP — phân tích chi tiết `QĐ 1233/QĐ-CT`) | 2026-09-10 | 2026-11-26 |
| https://thuvienphapluat.vn/van-ban/Thue-Phi-Le-Phi/Quyet-dinh-1233-QD-CT-2026-thanh-phan-chua-du-lieu-nghiep-vu-hoa-don-chung-tu-dien-tu-722644.aspx | Thư viện Pháp luật | 2026-08-27 | 2026-11-26 |
| https://thuvienphapluat.vn/ma-so-thue/phap-luat-thue/quyet-dinh-1233qdct-quy-dinh-ve-thanh-phan-chua-du-lieu-nghiep-vu-hoa-don-dien-tu-nhu-the-nao-230755.html | Thư viện Pháp luật | 2026-09 | 2026-11-26 |
| https://thuvienphapluat.vn/van-ban/Thue-Phi-Le-Phi/Quyet-dinh-1306-QD-CT-2025-thanh-phan-chua-du-lieu-nghiep-vu-hoa-don-chung-tu-dien-tu-664897.aspx | Thư viện Pháp luật (`QĐ 1306/QĐ-CT`) | 2025-06-13 | 2026-11-26 |
| https://hoadondientu.gdt.gov.vn/ (`/_next/static/chunks/pages/_app-755f01fff0623a8a.js`, module `70234`) | Cục Thuế (xác nhận live `V210="2.1.0"`, `V211="2.1.1"`) | 2026 (live) | 2026-11-26 |

- **Khoảng trống:** Toàn văn PDF của `QĐ 1233/QĐ-CT` (27/08/2026) chưa tải về kho `references/` nên **chưa đối chiếu từng dòng toàn bộ bảng thẻ GTGT của `QĐ 1233` với `QĐ 1271`** ngoài các điểm đã xác minh ở trên (`PBan=2.1.1`, `MSTCLQuan`, `TTHHDTrung`, lộ trình `XAdES`).
- **Đề xuất sửa `docs/04-data/einvoice-xml.md` & `docs/04-data/README.md`:** Cập nhật `§1` của `einvoice-xml.md` để ghi rõ `QĐ 1271/QĐ-CT` đã bị thay thế bởi `QĐ 1306/QĐ-CT` (13/06/2025) rồi `QĐ 1233/QĐ-CT` (27/08/2026) theo `NĐ 254/2026/NĐ-CP` và `TT 91/2026/TT-BTC`; thêm mốc `PBan=2.1.0`/`2.1.1` (chuyển tiếp đến 31/12/2026) và khuyến nghị tải PDF `QĐ 1233/QĐ-CT` vào `references/` nếu team cần chuẩn hóa lên `2.1.1`.

---

### 2c. Thứ tự số học ra `TgTTTBSo` (chiết khấu thương mại, phí/lệ phí, giảm trừ)

**Kết quả:**
1. **Trong văn bản gốc (`QD-1271-QD-CT-2025.pdf` trang 96–99):** Văn bản chỉ định nghĩa từng thẻ trong `<HHDVu>` và `<TToan>` mà **không in một công thức đại số tổng quát** cho `TgTTTBSo`. Các thẻ tiền trong `<TToan>` theo đúng thứ tự xuất hiện:
   - `THTTLTSuat/LTSuat`: `{TSuat, ThTien, TThue}` (tổng hợp theo từng thuế suất)
   - `TgTCThue`: Tổng tiền chưa thuế (Bắt buộc)
   - `TGTKCThue`: Tổng giảm trừ không chịu thuế (Không bắt buộc)
   - `TgTThue`: Tổng tiền thuế (Bắt buộc)
   - `DSLPhi/LPhi`: `{TLPhi, TPhi}` (phí, lệ phí — Bắt buộc nếu có)
   - `TTCKTMai`: Tổng tiền chiết khấu thương mại (Bắt buộc nếu có)
   - `TGTKhac`: Tổng giảm trừ khác (Không bắt buộc)
   - `TgTTTBSo`: Tổng tiền thanh toán bằng số (Bắt buộc)
   - `TgTTTBChu`: Tổng tiền thanh toán bằng chữ (Bắt buộc)

2. **Công thức chuẩn được ghi nhận từ tài liệu giải pháp & hướng dẫn kỹ thuật (Thư viện Pháp luật, CaseLaw, MISA, Viettel/Odoo):**
   - **Cấp dòng hàng (`TChat = 1`):**
     $$\text{ThTien}_i = \text{SLuong}_i \times \text{DGia}_i - \text{STCKhau}_i$$
     (trong đó nếu có chiết khấu theo tỷ lệ: $\text{STCKhau}_i = \text{SLuong}_i \times \text{DGia}_i \times \text{TLCKhau}_i / 100$; dòng `TChat = 2` khuyến mại có `ThTien = 0`; dòng `TChat = 4` ghi chú không có `ThTien`).
   - **Cấp tổng hợp thuế suất (`LTSuat`):**
     $$\text{LTSuat/ThTien}_r = \sum_{i \in r} \text{ThTien}_i \quad ; \quad \text{LTSuat/TThue}_r = \text{LTSuat/ThTien}_r \times r$$
   - **Cấp hóa đơn (`TToan`):**
     - Trường hợp hóa đơn thường không có chiết khấu tổng, phí hay giảm trừ đặc biệt:
       $$\text{TgTTTBSo} = \text{TgTCThue} + \text{TgTThue}$$
     - Trường hợp có chiết khấu thương mại toàn hóa đơn (`TTCKTMai`), phí/lệ phí (`TPhi`), giảm trừ (`TGTKCThue`, `TGTKhac`):
       $$\text{TgTTTBSo} = \text{TgTCThue} - \text{TTCKTMai} + \text{TgTThue} + \sum \text{TPhi} - \text{TGTKCThue} - \text{TGTKhac}$$
       *(Lưu ý: xác minh trong mã nguồn `hoadondientu.gdt.gov.vn` `_app-755f01fff0623a8a.js` cho thấy `TGTKCThue` và `TGTKhac` là các trường điều kiện đặc thù; trên hóa đơn GTGT thương mại thông thường gần như luôn vắng mặt hoặc bằng 0).*

3. **CẢNH BÁO NGHIỆP VỤ QUAN TRỌNG — 3 cách thể hiện chiết khấu thương mại trên XML thực tế:**
   - **Cách 1 (Chiết khấu trực tiếp theo dòng, `TChat = 1` có `TLCKhau`/`STCKhau`):** `ThTien` của từng dòng **đã trừ `STCKhau`**, nên `TgTCThue` cũng đã là giá sau chiết khấu. Một số TCGP vẫn điền `TTCKTMai = Σ STCKhau` để hiển thị dòng tổng chiết khấu, nhưng lúc này **không được trừ `TTCKTMai` lần thứ hai** khỏi `TgTCThue + TgTThue`.
   - **Cách 2 (Chiết khấu tách thành dòng riêng, `TChat = 3`):** Dòng hàng có `<TChat>3</TChat>`. Theo mã nguồn tích hợp chính thức Viettel S-Invoice của Odoo (`odoo/odoo/addons/l10n_vn_edi_viettel/models/account_move.py` dòng 569, 600–606), dòng chiết khấu (`selection = 3`) gửi số **dương** (`abs(...)`) để S-Invoice tự trừ; trong khi nhiều phần mềm kế toán khác (MISA/VNPT theo hướng dẫn nghiệp vụ) xuất `ThTien` dương hoặc âm tùy mẫu, rồi tổng hợp vào `TTCKTMai`.
   - **Cách 3 (Hóa đơn chiết khấu thương mại cuối kỳ/theo sản lượng):** Lập hóa đơn riêng có `TTHDLQuan/TCHDon = 5` kèm bảng kê `SBKe`/`NBKe` (`QĐ 1271` trang 90, 92).

**Hệ quả thiết kế cho bộ kiểm tra số học ở bước ingest PayMatch:**
Vì chưa có bộ file XML sản xuất thật chứa đủ các tình huống `TTCKTMai` + `TChat=3` + `DSLPhi` từ MISA/Viettel/VNPT/EasyInvoice để chốt 1 công thức duy nhất cho mọi TCGP, bộ ingest nên kiểm tra theo 2 nhánh (với sai số làm tròn $\le 1\text{đ}$ hoặc ngưỡng cấu hình):
- Nhánh A (`TTCKTMai` đã được trừ vào `TgTCThue`): `TgTTTBSo ≈ TgTCThue + TgTThue + ΣTPhi - TGTKCThue - TGTKhac`
- Nhánh B (`TTCKTMai` chưa được trừ vào `TgTCThue`): `TgTTTBSo ≈ TgTCThue - TTCKTMai + TgTThue + ΣTPhi - TGTKCThue - TGTKhac` (chỉ chấp nhận khi `TTCKTMai > 0` và `Σ ThTien(TChat=1) ≈ TgTCThue`).

**Nguồn (2c):**

| URL | Publisher | Ngày tài liệu | `retrieved_on` |
|---|---|---|---|
| `docs/04-data/references/QD-1271-QD-CT-2025.pdf` (trang 96–99) | Cục Thuế | 2025-05-30 | 2026-11-26 |
| https://github.com/odoo/odoo/blob/master/addons/l10n_vn_edi_viettel/models/account_move.py | Odoo SA (tích hợp chính thức Viettel S-Invoice) | 2026 | 2026-11-26 |
| https://amis.misa.vn/40617/hoa-don-chiet-khau-thuong-mai/ | MISA AMIS (TCGP — hướng dẫn nghiệp vụ hóa đơn CKTM) | 2025–2026 | 2026-11-26 |
| https://thuvienphapluat.vn/van-ban/Thue-Phi-Le-Phi/Quyet-dinh-1450-QD-TCT-2021-thanh-phan-chua-du-lieu-nghiep-vu-hoa-don-dien-tu-490526.aspx | Thư viện Pháp luật (`QĐ 1450/QĐ-TCT`) | 2021-10-07 | 2026-11-26 |
| https://hoadondientu.gdt.gov.vn/ (`/_next/static/chunks/pages/_app-755f01fff0623a8a.js`) | Cục Thuế | 2026 (live) | 2026-11-26 |

- **Khoảng trống:** **Chưa xác minh** trên file XML sản xuất thật có chiết khấu thương mại (`TChat=3` và `TTCKTMai > 0`) và phí (`DSLPhi/LPhi/TPhi > 0`) của từng TCGP (MISA, Viettel, VNPT, EasyInvoice) xem `TgTCThue` đã trừ `TTCKTMai` hay chưa.
- **Đề xuất sửa `docs/04-data/einvoice-xml.md`:** Bổ sung lưu ý 2 nhánh kiểm tra `TTCKTMai` và 3 cách thể hiện chiết khấu thương mại vào mục "Kiểm tra số học ingest phải làm" ở `§4`.

---

### 2d. Hóa đơn điều chỉnh / thay thế (`TTHDLQuan`) trông như thế nào?

**Kết quả:**
Theo `QD-1271-QD-CT-2025.pdf` (trang 92–94, 96, 98; Phụ lục VI trang 304) và cập nhật tại `QĐ 1233/QĐ-CT` (27/08/2026):

1. **Vị trí & cây thẻ `TTHDLQuan` (nằm trong `HDon/DLHDon/TTChung/TTHDLQuan`):**
   ```xml
   <TTHDLQuan>
     <TCHDon>2</TCHDon>                   <!-- 1: Thay thế, 2: Điều chỉnh, 3: Thay thế nhiều HĐ, 4: Điều chỉnh nhiều HĐ, 5: CKTM -->
     <!-- <MSTCLQuan>...</MSTCLQuan> -->  <!-- Mới từ QĐ 1233/QĐ-CT: bắt buộc nếu HĐ gốc thuộc đơn vị chia/tách/sáp nhập/hợp nhất -->
     <LHDCLQuan>1</LHDCLQuan>             <!-- Phụ lục VI: 1=NĐ 123/70, 2=mã xác thực QĐ 1209/2660, 3=NĐ 51/04, 4=đặt in NĐ 123 -->
     <KHMSHDCLQuan>1</KHMSHDCLQuan>       <!-- Tối đa 11 ký tự (1 ký tự cho NĐ 123/70/254; tối đa 11 cho NĐ 51) -->
     <KHHDCLQuan>C26TAA</KHHDCLQuan>      <!-- Tối đa 8 ký tự -->
     <SHDCLQuan>00000123</SHDCLQuan>      <!-- Tối đa 8 ký tự -->
     <NLHDCLQuan>2026-10-15</NLHDCLQuan>  <!-- YYYY-MM-DD -->
     <GChu>Điều chỉnh giảm đơn giá...</GChu> <!-- Tối đa 255 ký tự, không bắt buộc -->
     <!-- Nếu TCHDon = 3 hoặc 4 (điều chỉnh/thay thế nhiều hóa đơn, theo K13 Đ1 NĐ 70/2025): -->
     <!-- <SBKCLQuan>BK-01/2026</SBKCLQuan> -->
     <!-- <NBKCLQuan>2026-11-01</NBKCLQuan> -->
   </TTHDLQuan>
   ```
   - Khi `TCHDon` là `1` hoặc `2` (thay thế/điều chỉnh **1 hóa đơn**): các thẻ `LHDCLQuan`, `KHMSHDCLQuan`, `KHHDCLQuan`, `SHDCLQuan`, `NLHDCLQuan` là **Bắt buộc**.
   - Khi `TCHDon` là `3` hoặc `4` (thay thế/điều chỉnh **nhiều hóa đơn**): các thẻ `SBKCLQuan` (tối đa 50 ký tự) và `NBKCLQuan` (`YYYY-MM-DD`) là **Bắt buộc**.
   - Lưu ý lỗi kỹ thuật hay gặp (MISA meInvoice ghi nhận): nếu gửi thẻ `<TTHDLQuan>` rỗng hoặc `<TCHDon>` sai tập giá trị, CQT từ chối cấp mã với lỗi `[20001]- HDon/DLHDon/TTChung/TTHDLQuan/TCHDon: phải có giá trị hợp lệ`.

2. **Quy ước dấu & cấu trúc phần thân (`NDHDon`) giữa 3 loại nghiệp vụ:**
   - **Hóa đơn thay thế (`TCHDon = 1`):** Chứa đầy đủ toàn bộ giá trị mới (số dương) thay cho hóa đơn gốc. Hóa đơn gốc trên `hoadondientu.gdt.gov.vn` chuyển sang `tthai = 4` (*"Hóa đơn đã bị thay thế"*); hóa đơn mới có `tthai = 2` (*"Hóa đơn thay thế"*).
   - **Hóa đơn điều chỉnh giá trị (`TCHDon = 2`):**
     - Điều chỉnh **tăng**: ghi **số dương** (`SLuong`, `DGia`, `ThTien`, `TgTCThue`, `TgTThue`, `TgTTTBSo` > 0).
     - Điều chỉnh **giảm**: ghi **dấu âm (`-`)** đúng với phần chênh lệch giảm (nguyên tắc xuyên suốt từ điểm e khoản 1 Điều 7 TT 78/2021 → NĐ 70/2025 → NĐ 254/2026 & TT 91/2026). Xác minh trực tiếp trên giao diện `hoadondientu.gdt.gov.vn` (`1121-c1db58774eef5d85.js`: `getColor=(e,t)=>3===e.tchat&&e[t]?e[t]>0?"#11C73A":"#EA3033":""` — tô xanh số dương, tô đỏ số âm khi `tchat=3`) và mã nguồn Odoo Viettel S-Invoice (`account_move.py` L574, L635–636).
     - Hóa đơn gốc vẫn giữ nguyên hiệu lực nhưng mang trạng thái `tthai = 5` (*"Hóa đơn đã bị điều chỉnh"*), phải kẹp chung với hóa đơn điều chỉnh (`tthai = 3`).
   - **Hóa đơn điều chỉnh thông tin (không đổi tiền/hàng):** `QĐ 1271` (trang 96, 98) cho phép **không bắt buộc** `<DSHHDVu>` và `<TToan>` (hoặc chỉ có dòng `TChat = 4` ghi chú/diễn giải). Ngoài ra, theo điểm a khoản 1 Điều 10 **TT 91/2026/TT-BTC**, trường hợp sai số tiền bằng chữ (`TgTTTBChu`) hoặc nội dung khác mà **không sai MST, số tiền bằng số, thuế suất** thì chỉ cần thông báo cho người mua + nộp `04/SS-HĐĐT`, không phải lập hóa đơn điều chỉnh/thay thế.

**Nguồn (2d):**

| URL | Publisher | Ngày tài liệu | `retrieved_on` |
|---|---|---|---|
| `docs/04-data/references/QD-1271-QD-CT-2025.pdf` (trang 92–94, 96, 98, 304) | Cục Thuế | 2025-05-30 | 2026-11-26 |
| https://thuvienphapluat.vn/van-ban/Thue-Phi-Le-Phi/Quyet-dinh-1233-QD-CT-2026-thanh-phan-chua-du-lieu-nghiep-vu-hoa-don-chung-tu-dien-tu-722644.aspx | Thư viện Pháp luật (xác nhận `MSTCLQuan` trong `TTHDLQuan`) | 2026-08-27 | 2026-11-26 |
| https://hoadondientu.gdt.gov.vn/ (`/_next/static/chunks/1121-c1db58774eef5d85.js`) | Cục Thuế | 2026 (live) | 2026-11-26 |
| https://github.com/odoo/odoo/blob/master/addons/l10n_vn_edi_viettel/models/account_move.py | Odoo SA (Viettel S-Invoice) | 2026 | 2026-11-26 |
| https://ihoadon.vn/hddt/hoa-don-dien-tu-tai-thong-tu-91-2026-tt-btc.html | EFY iHoadon (tóm tắt Điều 10 TT 91/2026) | 2026-07 | 2026-11-26 |

- **Khoảng trống:** Chưa có file XML sản xuất thật của một hóa đơn điều chỉnh giảm (có dấu `-`) và một hóa đơn thay thế để lưu vào `references/einvoice-samples/`.
- **Đề xuất sửa `docs/04-data/einvoice-xml.md`:** Sửa thứ tự `GChu` trước `SBKCLQuan`/`NBKCLQuan`, thêm `MSTCLQuan` (QĐ 1233), và ghi rõ quy ước dấu âm (`-`) trên hóa đơn điều chỉnh giảm để bộ ingest không reject số âm khi `TTHDLQuan/TCHDon` là `2` hoặc `4`.

---

## Mục 3. Tra cứu thuế (`tracuunnt`, rủi ro cao, `hoadondientu`)

### 3a. Ý nghĩa toàn bộ mã trạng thái MST trên `tracuunnt.gdt.gov.vn`

**Kết quả:**
Khung pháp lý đăng ký thuế hiện hành đã đi qua chuỗi: `TT 105/2020/TT-BTC` → `TT 86/2024/TT-BTC` (23/12/2024, hiệu lực 06/02/2025) → **`TT 90/2026/TT-BTC`** (30/06/2026, hiệu lực 01/07/2026, thay thế TT 86/2024). Theo **Phụ lục I** của cả `TT 86/2024/TT-BTC` và `TT 90/2026/TT-BTC` (được Báo Điện tử Chính phủ đăng tải chính thức ngày 14/09/2026), hệ thống có đúng **10 mã trạng thái MST (`00, 01, 02, 03, 04, 05, 06, 07, 09, 10`) — KHÔNG CÓ mã trạng thái `08`**.

> **Lưu ý tránh nhầm lẫn phổ biến:** Một số bài blog nhầm `08` là một mã trạng thái ("Đã phá sản"). Thực tế trong Phụ lục I `TT 86/2024/TT-BTC`, **`08` là mã lý do** nằm dưới **trạng thái `01`** (cùng với lý do `07` Giải thể/chấm dứt hoạt động), **không phải mã trạng thái cấp 1**.

| Mã trạng thái | Tên trạng thái chính thức (`TT 90/2026` & `TT 86/2024`, Phụ lục I) | Mã lý do chi tiết (tiêu biểu) & Ý nghĩa | Khuyến nghị hành động cho PayMatch (`fraud-control` / `accounts-payable`) |
|---|---|---|---|
| **`00`** | **NNT đã được cấp MST / Đang hoạt động** | Lý do `01`: Chưa đi vào hoạt động; `02`: Đang hoạt động SXKD bình thường; `03`: Cá nhân chưa phát sinh nghĩa vụ thuế. | **Xanh (cho phép)** nếu lý do `02` (hoặc không có cờ rủi ro khác). |
| **`01`** | **NNT ngừng hoạt động và đã hoàn thành thủ tục chấm dứt hiệu lực MST** | Lý do `01`: Đã đóng MST; `03`: Chia/tách/sáp nhập/hợp nhất; `04`: Cá nhân chết/mất tích; `07`: Giải thể/chấm dứt hoạt động; `08`: Đã phá sản. MST hết hiệu lực, không được xuất HĐ mới. | **Đỏ (chặn chi)** nếu ngày lập HĐ (`NLap`) sau ngày chấm dứt hiệu lực MST. |
| **`02`** | **NNT đã chuyển cơ quan thuế quản lý (chờ CQT nơi đến nhận)** | Đang trong quá trình chuyển trụ sở sang địa bàn CQT khác. | **Vàng (cảnh báo / kiểm tra thêm)** — kiểm tra địa chỉ mới trên HĐ và hợp đồng. |
| **`03`** | **NNT ngừng hoạt động nhưng chưa hoàn thành thủ tục chấm dứt hiệu lực MST** | Đã ngừng hoạt động thực tế nhưng chưa đóng MST (thường nợ thuế hoặc đang giải thể dở dang). | **Đỏ (chặn chi)** — rủi ro thuế đầu vào rất cao. |
| **`04`** | **NNT đang hoạt động (áp dụng cho hộ, cá nhân kinh doanh chưa đủ thông tin đăng ký thuế)** | Hộ/cá nhân kinh doanh đang hoạt động nhưng hồ sơ ĐKT chưa hoàn thiện. | **Vàng (kiểm tra thêm)** — xác minh tư cách NCC (lưu ý HKD thường dùng hóa đơn bán hàng `KHMSHDon=2`, không phải GTGT). |
| **`05`** | **NNT tạm ngừng hoạt động, kinh doanh** | Đã đăng ký tạm ngừng kinh doanh có thời hạn với CQT/ĐKKD; **không được xuất hóa đơn** trong thời gian tạm ngừng. | **Đỏ (chặn chi)** nếu `NLap` rơi vào giai đoạn tạm ngừng. |
| **`06`** | **NNT không hoạt động tại địa chỉ đã đăng ký** | CQT xác minh thực tế không còn hoạt động tại trụ sở ("bỏ địa chỉ / bỏ trốn"); hóa đơn bị khóa/rủi ro đặc biệt. | **Đỏ (chặn chi ngay lập tức)** — tín hiệu gian lận/hóa đơn không hợp pháp hàng đầu. |
| **`07`** | **NNT chờ làm thủ tục phá sản** | Tòa án đã ban hành quyết định mở thủ tục phá sản gửi CQT. | **Đỏ (chặn chi / leo thang duyệt tay)** — rủi ro công nợ & hóa đơn. |
| *(không có `08`)* | *(Không tồn tại mã trạng thái `08`)* | *(`08` chỉ là mã lý do "Đã phá sản" thuộc trạng thái `01`)* | — |
| **`09`** | **NNT chờ xác minh tình trạng hoạt động tại địa chỉ đã đăng ký** | Cảnh báo sớm gồm 7 mã lý do (`01`: không nộp tờ khai sau 2 lần đôn đốc; `02`: thư CQT bị bưu điện trả lại; `03`/`04`: tin báo/văn bản cơ quan có thẩm quyền; `05`/`06`/`07`: phân loại rủi ro khi đăng ký HĐĐT/ĐKDN/ĐKT). | **Vàng → Đỏ (tạm giữ / escrow & xác minh NCC)** — rủi ro sắp chuyển sang `06`. |
| **`10`** | **Mã số thuế chờ cập nhật thông tin số định danh cá nhân** | Áp dụng cho cá nhân/đại diện HKD chưa đồng bộ CCCD/VNeID với dữ liệu thuế. | **Vàng (kiểm tra thêm)** đối với NCC là cá nhân/hộ kinh doanh. |

**Ghi nhận kỹ thuật về truy cập `tracuunnt.gdt.gov.vn`:** Khi thử kết nối HTTPS từ môi trường Linux container này (`curl https://tracuunnt.gdt.gov.vn/tcnnt/mstdn.jsp`), gặp lỗi `curl: (60) SSL certificate problem: unable to get local issuer certificate` (máy chủ không gửi đủ chuỗi chứng thư trung gian CA Việt Nam trong trust store Linux mặc định — không phải chặn IP). Tích hợp thực tế (hoặc adapter kiểm thử) cần nạp chuỗi CA trung gian hợp lệ của đơn vị cấp chứng thư.

**Nguồn (3a):**

| URL | Publisher | Ngày tài liệu | `retrieved_on` |
|---|---|---|---|
| https://baochinhphu.vn/10-trang-thai-ma-so-thue-can-biet-102260915153506424.htm | Báo Điện tử Chính phủ (dẫn Phụ lục I `TT 90/2026/TT-BTC`) | 2026-09-14 | 2026-11-26 |
| https://vanban.chinhphu.vn/?pageid=27160&docid=212208 | Cổng TTĐT Chính phủ (`Thông tư 86/2024/TT-BTC`, đính kèm `86-btc.pdf`) | 2024-12-23 | 2026-11-26 |
| https://thoibaotaichinhvietnam.vn/10-trang-thai-ma-so-thue-nguoi-nop-thue-can-luu-y-203660.html | Thời báo Tài chính Việt Nam (Bộ Tài chính) | 2026 | 2026-11-26 |
| https://thuvienphapluat.vn/banan/tin-tuc/tai-ve-phu-luc-thong-tu-862024tt-btc-ve-dang-ky-thue-tu-nam-2025-13111.html | Thư viện Pháp luật (Phụ lục I `TT 86/2024/TT-BTC`, mã lý do) | 2025 | 2026-11-26 |

- **Khoảng trống:** Bản PDF `86-btc.pdf` trên `vanban.chinhphu.vn` là file scan ảnh và chưa tải được toàn văn PDF của `TT 90/2026/TT-BTC` để kiểm tra toàn bộ bảng **mã lý do** chi tiết dưới từng trạng thái của `TT 90/2026` (mã trạng thái cấp 1 `00–10` đã xác minh đầy đủ qua Báo Điện tử Chính phủ).

---

### 3b. Danh sách "doanh nghiệp rủi ro cao về thuế/hóa đơn"

**Kết quả:**
1. **Ai công bố & kênh tra cứu:**
   - **Không tồn tại một API công khai hay một danh sách đen đơn lẻ cố định toàn quốc.** Dữ liệu được công bố qua 2 lớp:
     - **Cục Thuế** (trước 2025 là Tổng cục Thuế) ban hành các công văn rà soát toàn quốc kèm phụ lục danh sách MST (điển hình: **Công văn `1798/TCT-TTKT`** ngày 16/05/2023 công bố 524 DN rủi ro về hóa đơn; **Công văn `3385/TCT-TTKT`** bổ sung; cùng các đợt phối hợp với Cơ quan Công an).
     - **Cục Thuế / Chi cục Thuế địa phương** (Hà Nội, TP.HCM, Bình Dương, Thái Nguyên, v.v.) định kỳ đăng tải quyết định/thông báo danh sách DN rủi ro cao, DN bỏ địa chỉ kinh doanh hoặc thuộc diện rà soát hóa đơn không hợp pháp.
   - **Hai cổng tra cứu chính thống của cơ quan thuế** (theo hướng dẫn của BKAV, MISA, Fast):
     - Cổng TTĐT Cục Thuế: `https://www.gdt.gov.vn/wps/portal/home/dnrrvt` (chọn tỉnh/TP để tải thông báo & danh sách).
     - Cổng tra cứu hóa đơn: `https://tracuuhoadon.gdt.gov.vn/dnrrvp.html` (mục *"Danh sách doanh nghiệp rủi ro, vi phạm"*, lọc theo cơ quan thuế quản lý / MST và kết xuất Excel).
   - **Cơ sở tiêu chí rủi ro:** Bộ chỉ số tiêu chí đánh giá rủi ro về hóa đơn theo **Quyết định `78/QĐ-TCT`**, **Công văn `1873/TCT-TTKT`**, và các tiêu chí quản lý rủi ro mới được luật hóa trong `NĐ 70/2025/NĐ-CP`, `NĐ 254/2026/NĐ-CP`, `TT 91/2026/TT-BTC` (ví dụ: thay đổi người đại diện pháp luật/địa chỉ nhiều lần trong 12 tháng, doanh thu tăng đột biến không tương xứng tài sản/nhân sự, thuế GTGT nộp rất thấp so với doanh thu, người đại diện từng đứng tên DN bỏ địa chỉ trạng thái `06`).
2. **Các trường thông tin thường có trong danh sách công bố** *(tổng hợp từ nguồn thứ cấp BKAV, MISA, Fast, VietValues — chưa tải được file Excel gốc trực tiếp do lỗi SSL intermediate CA với `gdt.gov.vn` và `tracuuhoadon.gdt.gov.vn`)*:
   - `Mã số thuế (MST)`
   - `Tên doanh nghiệp / NNT`
   - `Cơ quan thuế quản lý`
   - `Số văn bản / Quyết định / Công văn công bố` (và ngày ban hành)
   - `Trạng thái hoạt động / Thời điểm phát sinh rủi ro` hoặc `Ghi chú / Lý do rủi ro` (tùy đợt công bố địa phương, có thể kèm địa chỉ đăng ký).
3. **Chu kỳ cập nhật:**
   - **Không có một chu kỳ cố định thống nhất toàn quốc** (như hằng ngày hay hằng tuần). Danh sách được cập nhật **liên tục theo từng đợt rà soát, chuyên án, quý/tháng** hoặc khi có thông báo mới từ từng Cục Thuế/Chi cục Thuế địa phương và cơ quan Công an. Trong thực tế, các phần mềm kế toán/HĐĐT (MISA, Fast, Bkav) tổng hợp thủ công hoặc bán tự động các công văn/Excel từ nhiều địa phương thành danh sách cảnh báo nội bộ (lên tới vài nghìn MST).
   - Ngoài danh sách cấp doanh nghiệp, ngay trên `hoadondientu.gdt.gov.vn`, từng hóa đơn còn có cờ **`bhphap = 1` (`"Bất hợp pháp"`)** do hệ thống CQT gắn trực tiếp (xác minh tại Mục 3c).

**Nguồn (3b):**

| URL | Publisher | Ngày tài liệu | `retrieved_on` |
|---|---|---|---|
| https://www.bkav.com/ehoadon/huong-dan/-/chi-tiet-huong-dan/2202/huong-dan-tra-cuu-danh-sach-doanh-nghiep-rui-ro-ve-thue | BKAV eHoadon (nguồn thứ cấp — hướng dẫn 2 URL tra cứu GDT) | 2024–2025 | 2026-11-26 |
| https://vietvalues.com/van-ban/thue/cv-17982023tctttkt-ve-ds-524-dn-co-rui-ro-ve-hoa-don-20523 | VietValues (nguồn thứ cấp — `CV 1798/TCT-TTKT` 16/05/2023) | 2023-05-16 | 2026-11-26 |
| https://vanban.chinhphu.vn/?pageid=27160&docid=218689 | Cổng TTĐT Chính phủ (`NĐ 254/2026/NĐ-CP`) | 2026-06-30 | 2026-11-26 |
| https://vanban.chinhphu.vn/?pageid=27160&docid=219006 | Cổng TTĐT Chính phủ (`TT 91/2026/TT-BTC`) | 2026-06-30 | 2026-11-26 |

- **Khoảng trống:** Không truy cập trực tiếp được `https://www.gdt.gov.vn/wps/portal/home/dnrrvt` và `https://tracuuhoadon.gdt.gov.vn/dnrrvp.html` từ môi trường này (lỗi `curl (60) SSL certificate problem: unable to get local issuer certificate`), nên **tên cột chính xác trong file Excel kết xuất từ `dnrrvp.html` là "chưa xác minh" trực tiếp**. Cần team mở bằng trình duyệt thực và chụp tên cột của 1 file Excel mẫu (không cần lưu MST thật) để chốt schema cho `sim-world`.

---

### 3c. Kết quả `hoadondientu.gdt.gov.vn` trả về khi tra cứu hóa đơn

**Kết quả (xác minh trực tiếp từ mã nguồn frontend live của `https://hoadondientu.gdt.gov.vn/` ngày `2026-11-26`):**

#### 1. Luồng tra cứu công khai (không cần đăng nhập, có CAPTCHA)
Người dùng nhập `nbmst` (MST người bán), loại hóa đơn (`khmshdon`), `khhdon`, `shdon`, tổng tiền thanh toán (`tgtttbso`), tổng tiền thuế (`tgtthue`). Theo module `92301` trong `_app-755f01fff0623a8a.js`, cổng trả về:
- **Không tìm thấy:**
  > `"Không tồn tại hóa đơn có thông tin trùng khớp với các thông tin tổ chức, cá nhân tìm kiếm."`
- **Tìm thấy:**
  > `"Tồn tại hóa đơn có thông tin trùng khớp với các thông tin tổ chức, cá nhân tìm kiếm."`
  kèm theo:
  - Kết quả kiểm tra (`kqcht`, nếu có);
  - `"Trạng thái xử lý hoá đơn: <nhãn ttxly>"` (hiển thị từ bảng `ttxly` dưới đây);
  - Thông tin thông báo rà soát (`01/TB-RSĐT`) hoặc thông báo sai sót (`04/SS-HĐĐT`), gồm tính chất thông báo (`1: Huỷ`, `2: Điều chỉnh`, `3: Thay thế`, `4: Giải trình`) và kết quả tiếp nhận của CQT (`Cán bộ thuế đang xử lý` / `Cơ quan thuế tiếp nhận` / `Cơ quan thuế không tiếp nhận`).

#### 2. Luồng tra cứu có đăng nhập / API (`query/invoices/purchase`, `query/invoices/sold`, `sco-query/invoices/...`, `query/invoices/detail`)
Các trường trạng thái chuẩn trả về cho mỗi bản ghi hóa đơn:

**a) `tthai` — Trạng thái hóa đơn** (trích nguyên văn từ `_app-755f01fff0623a8a.js` & `1121-c1db58774eef5d85.js`):

| Giá trị `tthai` | Nhãn hiển thị trên bảng UI (`en`) | Nhãn trên bản in (`ei`, module `92301`) | Ý nghĩa cho PayMatch |
|---|---|---|---|
| `1` | `Hóa đơn mới` | `Hoá đơn mới` | Hóa đơn gốc đang có hiệu lực |
| `2` | `Hóa đơn thay thế` | `Hoá đơn thay thế` | Hóa đơn mới thay cho HĐ gốc có sai sót |
| `3` | `Hóa đơn điều chỉnh` | `Hoá đơn điều chỉnh` | Hóa đơn điều chỉnh tăng/giảm/thông tin cho HĐ gốc |
| `4` | `Hóa đơn đã bị thay thế` | `Hoá đơn đã bị thay thế` | **Không còn hiệu lực** — chặn thanh toán, trỏ sang HĐ thay thế |
| `5` | `Hóa đơn đã bị điều chỉnh` | `Hoá đơn đã bị điều chỉnh` | Phải đối chiếu kèm HĐ điều chỉnh liên quan (`hdonLquan`) |
| `6` | `Hóa đơn đã bị hủy` | `Hoá đơn đã bị xoá/huỷ bỏ` | **Không còn hiệu lực** — chặn thanh toán |

**b) `ttxly` — Kết quả xử lý / kiểm tra của Cơ quan Thuế** (trích nguyên văn từ module `70234`, biến `W` với `N = "Cục Thuế"`):

| Giá trị `ttxly` | Nhãn chính thức trên `hoadondientu.gdt.gov.vn` (2026) | Ghi chú |
|---|---|---|
| `0` | `Cục Thuế đã nhận` | *(Trước 2025: "Tổng cục Thuế đã nhận")* |
| `1` | `Đang tiến hành kiểm tra điều kiện cấp mã` | Đang xử lý, chưa có mã CQT |
| `2` | `CQT từ chối hóa đơn theo từng lần phát sinh` | **Không hợp lệ** |
| `3` | `Hóa đơn đủ điều kiện cấp mã` | Chờ cấp mã |
| `4` | `Hóa đơn không đủ điều kiện cấp mã` | **Không hợp lệ** |
| `5` | `Đã cấp mã hóa đơn` | **Hợp lệ** (HĐĐT có mã CQT) |
| `6` | `Cục Thuế đã nhận không mã` | **Hợp lệ** (HĐĐT không có mã CQT) |
| `7` | `Đã kiểm tra định kỳ HĐĐT không có mã` | **Hợp lệ** (HĐĐT không mã đã qua kiểm tra định kỳ) |
| `8` | `Cục Thuế đã nhận hóa đơn có mã khởi tạo từ máy tính tiền` | **Hợp lệ** (HĐĐT khởi tạo từ MTT) |

**c) `tchat` — Tính chất hóa đơn** (trích từ module `70234`, biến `eu`):

| Giá trị `tchat` | Định danh trong GDT JS | Ý nghĩa |
|---|---|---|
| `1` | `ORIGINAL` | Hóa đơn gốc |
| `2` | `REPLACEMENT` | Hóa đơn thay thế |
| `3` | `ADJUSTMENT` | Hóa đơn điều chỉnh |
| `4` | `TRADE_DISCOUNT` | Hóa đơn chiết khấu thương mại (UI nối thêm `"(Hóa đơn chiết khấu thương mại)"` sau nhãn `tthai`) |
| `5` | `REPLACEMENT_MULTIPLE` | Thay thế nhiều hóa đơn |
| `6` | `ADJUSTMENT_MULTIPLE` | Điều chỉnh nhiều hóa đơn |

**d) Các trường kiểm soát bổ sung rất quan trọng cho `fraud-control`:**
- **`bhphap`** (*Kết quả kiểm tra hóa đơn*): `1` → `"Bất hợp pháp"` (`1121-c1db58774eef5d85.js`). Nếu `bhphap == 1` → **Đỏ (chặn chi ngay)**.
- **`hdonLquan`**: thông tin hóa đơn liên quan (mẫu số, ký hiệu, số, ngày) khi `tthai` là `2, 3, 4, 5`.
- **Giới hạn kỹ thuật API GDT** (từ `dieutx/hddt-downloader-windows/docs/HAR_ANALYSIS.md`, kiểm tra ngày `28/10/2026`): endpoint `sco-query` (hóa đơn máy tính tiền) giới hạn khoảng ngày tìm kiếm tối đa 10 ngày và yêu cầu CAPTCHA từng trang; kích thước trang `size=50` trả HTTP 200 còn `size=100` trả HTTP 500; endpoint `query/invoices/detail` tra theo khóa `(nbmst, khmshdon, khhdon, shdon)`.

**Nguồn (3c):**

| URL | Publisher | Ngày tài liệu | `retrieved_on` |
|---|---|---|---|
| https://hoadondientu.gdt.gov.vn/ (`/_next/static/chunks/pages/_app-755f01fff0623a8a.js`, modules `70234` & `92301`) | Cục Thuế (Cổng HĐĐT chính thức) | 2026 (live) | 2026-11-26 |
| https://hoadondientu.gdt.gov.vn/ (`/_next/static/chunks/1121-c1db58774eef5d85.js`) | Cục Thuế (Cổng HĐĐT chính thức) | 2026 (live) | 2026-11-26 |
| https://github.com/dieutx/hddt-downloader-windows/blob/main/docs/HAR_ANALYSIS.md | GitHub (`dieutx`) | 2026-10-28 | 2026-11-26 |
| https://github.com/dieutx/hddt-downloader-windows/blob/main/src/LinkTraCuu.ps1 | GitHub (`dieutx`) | 2026-11-10 | 2026-11-26 |

- **Khoảng trống:** Không có khoảng trống về tập mã trạng thái `tthai`, `ttxly`, `tchat`, `bhphap` (đã xác minh 100% trực tiếp từ bundle JS live của `hoadondientu.gdt.gov.vn`). Mẫu payload JSON thực tế của một bản ghi trả về từ `query/invoices/detail` không thể gọi trực tiếp vì cần tài khoản NNT + CAPTCHA.

---

## Tổng hợp đề xuất chỉnh sửa cho các tài liệu hiện có (chỉ đề xuất, không áp dụng)

1. **`docs/04-data/einvoice-xml.md`:**
   - **§1:** Cập nhật tình trạng pháp lý: `QĐ 1271/QĐ-CT` (30/05/2025) đã bị thay thế bởi `QĐ 1306/QĐ-CT` (13/06/2025), rồi **`QĐ 1233/QĐ-CT` (27/08/2026)** (căn cứ `NĐ 254/2026/NĐ-CP` và `TT 91/2026/TT-BTC`). Cập nhật `PBan` hỗ trợ `2.0.0`, `2.0.1`, `2.1.0`, `2.1.1` (chuyển tiếp `2.1.0` đến hết 31/12/2026; ký số `DSig` → `XAdES` đến hết 09/04/2027).
   - **§3:** Chỉnh đúng thứ tự thẻ theo `QĐ 1271` PDF (`TTHDLQuan`: `GChu` trước `SBKCLQuan`/`NBKCLQuan`, thêm `MSTCLQuan` từ `QĐ 1233`; `NBan`: `STKNHang`/`TNHang` trước `Fax`/`Website`; `NMua`: đúng thứ tự 13 thẻ); ghi rõ `DSHHDVu` và `TToan` tùy chọn cho hóa đơn điều chỉnh thông tin; thêm `KHMSHDon` `7, 8, 9`; bổ sung cấu trúc 6 ký tự `KHHDon` (đủ 10 chữ cái `T, D, L, M, N, B, G, H, X, F`) và cấu trúc gói `TDiep/DLieu/HDon`.
   - **§4:** Mở rộng quy tắc kiểm tra số học để xử lý dấu âm trên hóa đơn điều chỉnh giảm (`TCHDon` = `2`/`4`) và 2 nhánh chiết khấu thương mại (`TTCKTMai` đã hoặc chưa trừ trong `TgTCThue`), kèm quy tắc đọc `TThue`/`THTienCoVAT` trong `HHDVu/TTKhac` nếu cần.
   - **§5:** Cập nhật trạng thái 4 repo GitHub đã kiểm tra (tất cả đều là fixture tổng hợp/viết tay, đã lưu 6 mẫu vào `references/einvoice-samples/`), giữ yêu cầu team cung cấp 2–3 file XML sản xuất thật từ các TCGP khác nhau (đặc biệt có chiết khấu/phí và hóa đơn điều chỉnh/thay thế).
2. **`docs/04-data/README.md`:**
   - Cập nhật bảng "Tình trạng mẫu thật": thêm dòng tham chiếu `docs/04-data/research/einvoice-and-tax.md` và `docs/04-data/references/einvoice-samples/` (🟡 đã có fixture tổng hợp kiểm thử parser + enum tra cứu thuế chính thức; vẫn thiếu file XML sản xuất thật và PDF `QĐ 1233/QĐ-CT`).
3. **Tài liệu `sim-world` / tool `tax_id_lookup` & `einvoice_portal` (khi đối chiếu thiết kế):**
   - `tax_id_lookup` dùng đúng 10 mã trạng thái `TT 90/2026/TT-BTC` (`00, 01, 02, 03, 04, 05, 06, 07, 09, 10` — không sinh mã `08`), đặc biệt dùng `06`, `03`, `05`, `01`, `09` cho các kịch bản kiểm soát rủi ro.
   - `einvoice_portal` dùng đúng enum live của `hoadondientu.gdt.gov.vn`: `tthai` (`1..6`), `ttxly` (`0..8`), `tchat` (`1..6`), và bổ sung trường `bhphap` (`0`/`1` — hóa đơn bất hợp pháp).
