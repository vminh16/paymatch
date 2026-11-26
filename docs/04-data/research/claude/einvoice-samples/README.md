# Mẫu XML hóa đơn điện tử thật, đã làm sạch (Claude baseline)

Ngày lấy: **26/11/2026**. Người lấy: worker Claude (task_7a6a7ccb20b0).

## Nguồn và cách chọn

- Tìm bằng GitHub code search (`gh search code "MSTTCGP" --extension xml`, `"TgTTTBSo"`), ra 194 file trong 15 repo công khai. Tải về một thư mục tạm, không lưu bản gốc vào repo.
- Chọn 10 file **thật**: có chữ ký số thật, `DLHDon Id` là GUID hoặc mã giao dịch, `MCCQT` 34 ký tự bắt đầu bằng `00`, `TTKhac` mang tên trường riêng của từng nhà cung cấp. Mỗi file từ một `MSTTCGP` khác nhau nếu được.
- File **tự viết** (fixture) chỉ đọc để so sánh, không đưa vào đây: `ngoquangthanhphu/vn-einvoice/test/fixtures/*`, `Bunmeooo/Invoice-hub/sample_invoice.xml`, `yeshan-jun/xml-viewer-thue/examples/sample-invoice.xml`, chuỗi XML trong `ROYCE-8425/tt78-xml-invoice-parser/test.mjs`, `tanod-labs/tanod-tools/.../vn-hoadon-tdiep-dieuchinh.xml`. Xem report.md §1.
- Tên file gốc trên GitHub chứa MST và tên người bán. Vì vậy bảng dưới chỉ ghi repo, commit và thư mục. Muốn tìm lại file gốc thì lọc theo `KHHDon` và ngày lập trong thư mục đó.

## Đã thay gì (mọi file)

Dùng một script tạm, đọc file theo từng thẻ và chỉ sửa giá trị, không định dạng lại. Sau đó kiểm bằng parser: thứ tự thẻ và namespace giữ nguyên ở cả 10 file, không còn giá trị gốc nào của các thẻ nhạy cảm.

| Thẻ / vùng | Thay bằng |
|---|---|
| `NBan/Ten`, `NMua/Ten` | `CÔNG TY TNHH NGƯỜI BÁN MẪU` / `CÔNG TY TNHH NGƯỜI MUA MẪU` |
| `NBan/MST`, `NMua/MST` | `0000000001` / `0000000002`. Giữ độ dài, giữ đuôi `-001` nếu MST gốc là đơn vị phụ thuộc (`XXXXXXXXXX-NNN`). MST người mua 12 số giữ 12 số |
| `DChi`, `DCDDKDoanh` | `Số 1 Đường Mẫu, Phường Mẫu, TP. Hồ Chí Minh` |
| `SDThoai`, `Fax`, `DCTDTu`, `Website`, `STKNHang`, `TNHang`, `HVTNMHang`, `MKHang` | giá trị mẫu (`0280000000`, `mau@example.com`, `0000000000`, `Ngân hàng Mẫu`…) |
| `MCCQT` | giữ độ dài và 2 ký tự đầu (`00`). Mã máy tính tiền giữ phần `M<loại>-<năm>-`, còn lại thành `0` |
| `SHDon` | giữ độ dài, thành `0…01`. `SHDCLQuan` thành `0…02` |
| `GChu`, `THHDVu` | che các dãy từ 5 chữ số trở lên (số hợp đồng, số vận đơn). `s03`: đổi tên thương hiệu trong tên hàng thành `ThuongHieuMau`. `s14`: che mã hợp đồng |
| `TTKhac/TTin/DLieu` | giữ nếu `KDLieu` là numeric hoặc tên trường là cờ/số tiền (`ProdType`, `IsSum`, `VATRate`…). Còn lại (mã tra cứu, địa chỉ, số TK, tên người đại diện, biển số xe…) thành `[đã thay]` |
| `DLQRCode`, `Fkey`, `QRCodeDataTemVe` | `[đã thay]` |
| `DSCKS` | `SignatureValue`, `DigestValue`, `X509Certificate`, `X509SerialNumber` thành `[đã xóa]`. `X509SubjectName` thành `CN=NGUOI KY MAU, O=CONG TY MAU`. Giữ `SigningTime`, thuật toán, cấu trúc `Reference`. **Chữ ký sẽ không còn hợp lệ, đây là điều bình thường** |
| Thuộc tính `Id` và `URI="#…"`, `Target="#…"` trỏ tới nó | `ID1`, `ID2`… (giá trị gốc có thể là mã tra cứu) |
| `<?xml-stylesheet … ?>` | che dãy số ≥ 9 chữ số trong URL XSLT (URL gốc chứa MST người bán) |

Giữ nguyên: thứ tự thẻ, namespace, `PBan`, `MSTTCGP`, `KHMSHDon`, `KHHDon`, `NLap`, mọi số tiền, `TSuat`, `TChat`, tên trường `TTruong`.

## Danh sách

`MSTTCGP` → tên nhà cung cấp: MISA 0101243150, Viettel 0100109106, BKAV 0101360697 chỉ lấy từ bảng ánh xạ trong mã nguồn `Bunmeooo/Invoice-hub/parser.py` (nguồn thứ cấp, **chưa xác minh** trên danh sách tổ chức cung cấp dịch vụ HĐĐT của Cục Thuế). Các MST còn lại: **chưa xác minh**.

| File | KHMSHDon / KHHDon | Loại | PBan | NLap | MSTTCGP (nhà cung cấp) | Điểm đáng chú ý | Nguồn (repo @ commit, thư mục) |
|---|---|---|---|---|---|---|---|
| `s02-gtgt-coma-…0107732197.xml` | 1 / C25TNA | GTGT **có mã** | 2.0.1 | 2025-02-28 | 0107732197 (chưa xác minh) | MST người bán có đuôi đơn vị phụ thuộc (`0000000001-001` sau khi làm sạch). `SHDon` 4 chữ số, không đệm 0. `TTKhac` dòng hàng tiếng Việt có dấu ("Thành tiền sau thuế"). DSCKS: NBan + CQT | [huynqsisvn/SISMAC2024](https://github.com/huynqsisvn/SISMAC2024) @ 4425c98b5be2, `SISMAC2024_GOC/Prog/Hddv/` |
| `s03-gtgt-coma-khuyenmai-…0101243150.xml` | 1 / C25TYH | GTGT có mã, hàng khuyến mại | 2.0.1 | 2025-03-13 | 0101243150 (MISA) | `HTTToan` = "Hàng khuyến mãi không thu tiền", `TSuat` = `KHAC:0.00%`, dòng `TChat=4`. **Số TK và tên ngân hàng người bán nằm trong `NBan/TTKhac`** (`SellerBankAccount`, `SellerBankName`), không chỉ trong `STKNHang` | cùng repo, cùng thư mục |
| `s04-gtgt-khongma-xangdau-…0305795054.xml` | 1 / K25TKV | GTGT **không mã** | 2.0.1 | 2025-01-02 | 0305795054 (chưa xác minh) | Có thẻ `<MCCQT/>` rỗng. `DGia` 4 chữ số thập phân (17272.7273), `SLuong` 3 chữ số. **`SLuong × DGia` lệch `ThTien` 3 đồng**. `DSLPhi` đứng trước `THTTLTSuat` | cùng repo, cùng thư mục |
| `s05-ve-maytinhtien-…0401486901.xml` | 5 / C25MHT | Vé xe khách, **khởi tạo từ máy tính tiền** | 2.1.0 | 2025-08-14 | 0401486901 (chưa xác minh) | `MCCQT` 23 ký tự dạng `M5-25-…`. `TChat=5` + `TTHHDTrung` đứng đầu `HHDVu`. Không có `Signature` trong `DSCKS` (bản lưu chưa ký). Thẻ lạ `QRCodeDataTemVe` ở gốc | cùng repo, cùng thư mục |
| `s07-gtgt-khongma-xangdau-…0100684378.xml` | 1 / K26TAN | GTGT không mã, xăng dầu | 2.1.0 | 2026-10-03 | 0100684378 (chưa xác minh) | Không có thẻ `MCCQT`. `TSuat` = `KKKNT`. **`TSuat` đứng trước `ThTien`** trong `HHDVu`. **`SLuong × DGia` lệch `ThTien` 108 đồng** (khách trả tròn 1.000.000 đ). Thẻ `Fkey` ở gốc. `NBan/TTKhac` có `MDDKDoanh` (mã cửa hàng xăng) | [Nhh124/Petrolimex_Invoice_Tool](https://github.com/Nhh124/Petrolimex_Invoice_Tool) @ b504bb22f8dd, `invoices_xml/` |
| `s09-gtgt-C-thieuMCCQT-…0302712571.xml` | 1 / C26TSE | Ký hiệu **C** (có mã) nhưng `MCCQT` rỗng | 2.1.0 | 2026-05-30 | 0302712571 (một danh bạ ghi là Mắt Bão, chưa xác minh) | Bản người bán lưu trước khi CQT cấp mã. Ingest phải coi đây là hóa đơn chưa hoàn tất. Thuộc tính `Target` không có `#` | [phamtuyennasani/RenewLogictics](https://github.com/phamtuyennasani/RenewLogictics) @ f3bfc8fd69ac, `public_html/uploads/einvoices/2026/05/` |
| `s10-gtgt-coma-…0101360697.xml` | 1 / C24TAB | GTGT có mã | 2.0.1 | 2024-06-21 | 0101360697 (BKAV) | `KDLieu` viết hoa `String` (Phụ lục III QĐ 1233 cũng viết `String`, QĐ 1271 viết thường). **Số TK người bán nằm trong `TTChung/TTKhac`** (`BankAccount`, `BankName`). DSCKS: thứ tự `NBan, NMua, CCKSKhac, CQT` | [sonkate/extract_xml](https://github.com/sonkate/extract_xml) @ 9d80c47175d6, `uploads/extracted/` |
| `s12-gtgt-khongma-…0100109106.xml` | 1 / K24TVA | GTGT không mã | 2.0.1 | 2024-05-13 | 0100109106 (Viettel) | **`TThue` nằm trong `HHDVu`** (ngoài chuẩn). `THTTLTSuat` liệt kê đủ 5 thuế suất kể cả dòng 0. `NMua/MST` rỗng (bán lẻ). `SHDon` 6 chữ số | [nlnhat285/ant-man](https://github.com/nlnhat285/ant-man) @ 75ae4f186dfc, thư mục gốc |
| `s13-banhang-dieuchinh-…0106713804.xml` | 2 / C25THN | Hóa đơn bán hàng **điều chỉnh giảm** (`TCHDon=2`) | 2.1.0 | 2025-10-04 | 0106713804 (URL XSLT trỏ tới một miền `hilo.com.vn`, chưa xác minh) | `ThTien` và `TgTTTBSo` **âm** (-1.692.000), `SLuong=0`, `DGia=0`. Không có `TgTCThue`/`TgTThue` (hóa đơn bán hàng). Có `HDDCKPTQuan=0` (cờ khu phi thuế quan của hóa đơn bán hàng, QĐ 1233 mục b). Có `<?xml-stylesheet?>` | [nghoang1009/Dungeon-Crawler](https://github.com/nghoang1009/Dungeon-Crawler) @ f2c27d5078cc, `spite/` |
| `s14-gtgt-thaythe-…0100727825.xml` | 1 / C25TAA | GTGT **thay thế** (`TCHDon=1`) | 2.1.0 | 2025-12-04 | 0100727825 (chưa xác minh) | `THDon` chứa ký hiệu thay vì tên hóa đơn (ngoài chuẩn). `SHDon`/`SHDCLQuan` 2 chữ số, không đệm 0. `TTHHDTrung` nằm sau `TTKhac` trong `HHDVu`. `GChu` theo mẫu "thay thế cho hóa đơn số…, ký hiệu…, ngày…". Ký bằng `rsa-sha1` | [ithumanmi/FinDeck_Backend](https://github.com/ithumanmi/FinDeck_Backend) @ dfe31ca9a6fb, `FileSource/` |

## Dùng thế nào

- Đây là **hình dạng thật** để bộ sinh sim-world bám theo và để viết test ingest (thứ tự thẻ thay đổi, `TTKhac` ở 6 vị trí, số lẻ, số âm, thẻ ngoài chuẩn).
- Không dùng số tiền hay ngày ở đây làm dữ liệu kịch bản.
- Chưa có mẫu nào theo `PBan` 2.1.1 / XAdES (QĐ 1233/QĐ-CT, 27/08/2026). Xem report.md §1.
