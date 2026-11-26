# Ghi chú nghiệp vụ

Nguồn chủ yếu là blog thực hành và bài tư vấn thứ cấp; cần đối chiếu văn bản gốc trước khi dùng cho slide hoặc sản phẩm thật.

## Kế toán phải trả (AP)

- **Đối chiếu 3 chứng từ:** đơn đặt hàng ↔ phiếu nhập kho (xác nhận đã nhận hàng) ↔ hóa đơn, trước khi trả tiền.
- Trước khi chi: xác minh người nhận, số TK, số tiền, hạn trả, công nợ còn lại; **kiểm tra khoản đó đã trả chưa**.
- Chứng từ chi: ủy nhiệm chi (chuyển khoản) hoặc phiếu chi (tiền mặt).
- Chuỗi F&B thường có hạn mức ủy quyền duyệt (ví dụ đề nghị ≤ 20 triệu theo ủy quyền).
- Nguồn: https://ketoanleanh.edu.vn/hoi-dap/kiem-soat-chung-tu-thanh-toan · https://helpact.misa.vn/kb/quytrinh-mua-hang/muahang_theodonhang · https://www.corpay.com/resources/blog/accounts-payable-audit

## Tách bạch nhiệm vụ (segregation of duties)

- Không một người nào vừa tạo nhà cung cấp, nhập hóa đơn, duyệt, phát lệnh chi, vừa đối soát ngân hàng. Người vừa tạo NCC vừa được chi là lỗ hổng gian lận.
- Đổi tài khoản NCC: qua quy trình thay đổi có hai người duyệt; ghi log ai đổi, lúc nào, trường nào.
- **Gọi lại xác minh:** không chấp nhận đổi TK qua email/tin nhắn; gọi số NCC đã lưu sẵn từ trước.
- Phân quyền phải nằm trong hệ thống, không chỉ trên giấy.
- → Trong PayMatch: mỗi bot = một vai; bot đọc tin nhắn không sửa được danh bạ; không bot nào chi tiền.
- Nguồn: https://www.corpay.com/resources/blog/segregation-of-duties-accounts-payable · https://www.shopify.com/blog/payment-controls

## Thuế

- **NĐ 181/2025/NĐ-CP (hiệu lực 01/07/2025):** hàng hóa, dịch vụ mua vào **từ 5 triệu đồng (đã gồm VAT)** phải có chứng từ thanh toán không dùng tiền mặt mới được khấu trừ VAT đầu vào; nộp tiền mặt vào TK người bán không tính.
  → Trả vào TK cá nhân không phải của người bán: vừa rủi ro lừa đảo, vừa rủi ro mất khấu trừ VAT.
  Nguồn: https://amis.misa.vn/232183/nghi-dinh-181-2025-nd-cp/ · https://luatvietnam.vn/tin-van-ban-moi/chinh-thuc-hang-hoa-mua-vao-tu-05-trieu-dong-phai-co-chung-tu-thanh-toan-khong-dung-tien-mat-186-102781-article.html · https://kpmg.com/vn/vi/home/phan-tich-chuyen-sau/2025/07/decree-181-and-circular-69-on-value-added-tax.html
- **Tra cứu hóa đơn:** hoadondientu.gdt.gov.vn — nhập MST người bán, loại, ký hiệu (6 ký tự), số hóa đơn.
- **Trạng thái MST người bán:** tracuunnt.gdt.gov.vn — chú ý trạng thái 03 (ngừng hoạt động, chưa chấm dứt MST) và 06 (không hoạt động tại địa chỉ đăng ký). Kế toán hay bỏ qua bước này.
  Nguồn: https://amis.misa.vn/52370/cach-kiem-tra-hoa-don-dien-tu-hop-le/ · https://thuvienphapluat.vn/ma-so-thue/phap-luat-thue/cach-tra-cuu-hoa-don-dau-vao-tren-tong-cuc-thue-chi-tiet-nhat-682296-192294.html
- Danh sách DN rủi ro cao về thuế, hóa đơn: xem BRD [D9], [D10].

## Vận hành chi nhánh

- Điện nước nên so với 12 tháng trước **và** với mức hoạt động của quán (doanh thu/số ly từ MoMo) để phân biệt rò rỉ với đông khách. (Suy luận của đội, chưa có nguồn.)
