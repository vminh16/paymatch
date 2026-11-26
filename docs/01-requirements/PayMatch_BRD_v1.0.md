# PayMatch — Khớp rồi mới chi
## Tài liệu Yêu cầu Nghiệp vụ (BRD) · Phiên bản 1.0

**Kế toán AI duyệt chi cho chuỗi cửa hàng nhỏ trên MoMo Doanh Nghiệp**

| Mục | Nội dung |
|---|---|
| Tên sản phẩm | **PayMatch** (tên tiếng Việt: *Khớp rồi mới chi*) |
| Cuộc thi | Imagine the Future Workspace (Human Centered. AI Powered) |
| Phiên bản | 1.0, ngày 25/11/2026 |
| Trạng thái | Bản dự thảo để đội rà soát |
| Chủ đề cuộc thi | Trợ lý AI (thanh toán, quản lý tài chính) + Chống lừa đảo |

---

## 1. Tóm tắt

**Vấn đề:** chủ chuỗi cửa hàng nhỏ phải tự duyệt khoảng 200 hóa đơn nhà cung cấp mỗi tháng. Tiền có thể mất theo năm cách: bị tính đắt ngầm, chuyển nhầm cho kẻ gian, mua của công ty rủi ro thuế, tiền điện nước bị trừ vô tội vạ, và mất thời gian đối soát thủ công.

**Giải pháp:** PayMatch là một kế toán AI chạy trên MoMo Doanh Nghiệp. AI đọc hóa đơn, so với hợp đồng, soát người nhận tiền, rồi gom tất cả thành vài dòng cần chủ chuỗi quyết. Tiền chỉ được trả khi **mọi thứ khớp**. Lệnh trả do một khóa an toàn bằng code phát ra, không phải do AI.

**Giá trị:**
- Chủ chuỗi: ít mất tiền hơn, ít thời gian hơn.
- MoMo: giữ dòng tiền của merchant trong hệ sinh thái, phát hiện kẻ gian trên toàn mạng lưới, có dữ liệu sạch để cho vay vốn nhập hàng.

**Một câu:** *AI kiểm tra từng hóa đơn; tiền chỉ đi khi khớp; cái gì lạ thì giữ lại cho chủ quyết.*

---

## 2. Bối cảnh

- Ngành F&B Việt Nam đang chịu áp lực chi phí lớn:
  - 44,8% doanh nghiệp F&B có chi phí nguyên liệu từ 30% giá bán trở lên; 6,2% vượt 50% [D1];
  - 69,38% doanh nghiệp chịu áp lực trực tiếp từ giá nguyên liệu tăng [D2];
  - một số nguyên liệu tăng 30–40% trong năm 2025 [D3];
  - hơn 50.000 cửa hàng ăn uống đóng cửa trong năm 2025 [D4].
- Doanh nghiệp nhỏ vẫn làm thủ công: MoMo khảo sát 203 doanh nghiệp nhỏ và thấy phần lớn vẫn quản lý đơn hàng, kho, kế toán và tài chính thủ công [M3].
- Quản lý thuế ngày càng dựa trên dữ liệu: hóa đơn điện tử phủ rộng, kể cả hộ kinh doanh doanh thu từ 1 tỷ/năm từ 01/7/2026 [L4]; cơ quan thuế đối chiếu hóa đơn với dòng tiền ngân hàng [D7].
- Nhiều quán đã nhận tiền khách qua QR MoMo, và doanh thu về MoMo Doanh Nghiệp ngay sau khi khách quét mã [M1].

---

## 3. Vấn đề cần giải quyết

### 3.1. Năm nỗi đau

**Nỗi đau 1: bị tính đắt ngầm.**
- **Chuyện gì xảy ra:** nhà cung cấp nhích đơn giá vài phần trăm, hoặc **đổi quy cách đóng gói** mà giữ gần như nguyên giá. Ví dụ: thùng cốc từ 1.000 cái xuống 800 cái.
- **Vì sao khó phát hiện:** mỗi nhà cung cấp ghi tên hàng một kiểu; kế toán phải so tay với hợp đồng; nhìn tổng tiền thì tưởng còn rẻ hơn.
- **Thiệt hại (minh họa):** 20 thùng cốc giá 1.120.000đ/thùng 800 cái, tức 1.400đ/cái, trong khi hợp đồng là 1.150đ/cái. Chuỗi trả thừa **4.000.000đ mỗi đợt**, khoảng **8 triệu/tháng** nếu nhập 2 đợt.

**Nỗi đau 2: chuyển nhầm cho kẻ gian.**
- **Chuyện gì xảy ra:** Zalo hoặc email của nhà cung cấp quen, thậm chí của chính chủ quán, bị chiếm. Kẻ gian nhắn: "Tài khoản công ty đang lỗi, chuyển gấp vào số này."
- **Bằng chứng:** có vụ Zalo của lãnh đạo bị chiếm rồi gửi QR giả để nhân viên chuyển tiền [D6]; ngân hàng cảnh báo các dấu hiệu như đổi thông tin thanh toán đột ngột, chuyển từ tài khoản doanh nghiệp sang tài khoản cá nhân [D5]. Trên thế giới, 74% doanh nghiệp Mỹ gặp lừa đảo qua email doanh nghiệp (BEC) trong năm 2025 [D8].
- **Thiệt hại:** cả một khoản thanh toán, thường hàng chục triệu, gần như không đòi lại được.

**Nỗi đau 3: mua của công ty "ma" hoặc rủi ro thuế.**
- **Chuyện gì xảy ra:** người bán mới chào giá rẻ bất thường, đòi cọc vào tài khoản cá nhân; hoặc nhà cung cấp nằm trong danh sách doanh nghiệp rủi ro về thuế và hóa đơn.
- **Bằng chứng:** danh sách doanh nghiệp rủi ro cao về thuế và hóa đơn đã có hơn 6.042 đơn vị [D9]; hóa đơn từ những nơi này có thể bị loại khỏi chi phí được trừ, làm tăng thuế phải nộp [D10].
- **Thiệt hại:** mất tiền cọc, **và** có thể bị loại chi phí khi quyết toán thuế.

**Nỗi đau 4: tiền điện nước bị trừ vô tội vạ.**
- **Chuyện gì xảy ra:** bật trả tự động thì hóa đơn nào cũng bị trừ. Đặt hạn mức cố định thì hoặc chặn nhầm tháng cao điểm, hoặc vẫn lọt tháng bất thường.
- **Thiệt hại (minh họa):** quán 3 rò ống, tiền nước 4,2 triệu thay vì khoảng 700 nghìn; vừa mất 3,5 triệu, vừa không ai biết để đi sửa.

**Nỗi đau 5: mất thời gian và dễ sai.**
- **Chuyện gì xảy ra:** mỗi lần nhập hàng kéo theo hàng loạt việc: kiểm đơn, đối soát giao nhận, lưu chứng từ, tổng hợp chi phí [D11]. Chủ chuỗi phải duyệt chi vào buổi tối cuối tuần.
- **Thiệt hại:** mất vài giờ mỗi tuần; người làm mệt thì dễ bỏ sót đúng những lỗi ở nỗi đau 1–4.

### 3.2. Nguyên nhân gốc rễ

1. **Thông tin nằm rải rác:** hóa đơn ở email, hợp đồng ở file, tài khoản nhà cung cấp ở Zalo, tiền ở MoMo và ngân hàng. Không có nơi nào **ghép chúng lại trước khi trả tiền**.
2. **Kiểm tra dựa vào người:** người mệt, người vội, người tin tin nhắn quen.
3. **Công cụ hiện có kiểm tra sau, không chặn trước:** phần mềm kế toán kiểm hóa đơn để kê khai thuế, tức là sau khi tiền đã đi (mục 3.3).

### 3.3. Vì sao các giải pháp hiện có chưa đủ

| Giải pháp hiện có | Làm được gì | Còn thiếu gì |
|---|---|---|
| Phần mềm kế toán (MISA AMIS, meInvoice) | Cảnh báo nhà cung cấp rủi ro thuế [C1]; cảnh báo hóa đơn vượt định mức chi phí [C2] | Kiểm tra **sau** khi hóa đơn về để kê khai thuế; không đứng ở cổng chi tiền, không chặn được lệnh chuyển khoản |
| Trả tự động của ngân hàng hay ví | Trả đúng hạn, có thể đặt hạn mức cố định | Hạn mức cố định không hiểu bối cảnh của từng quán, từng tháng |
| Ngân hàng cảnh báo tài khoản đáng ngờ | Cảnh báo tài khoản đã bị báo cáo lừa đảo | Không biết tài khoản đó có phải của nhà cung cấp của bạn không; không so với hợp đồng |
| Kế toán làm tay | Linh hoạt | Chậm, mệt, dễ sai, dễ bị lừa bởi tin nhắn quen |

### 3.4. Vì sao là lúc này
- **Dữ liệu đã có sẵn dạng máy đọc được:** hóa đơn điện tử XML.
- **Có khung pháp lý cho AI thanh toán:** Thông tư 53/2026 có hiệu lực từ 15/11/2026, đặt ngưỡng rủi ro cao cho khách tổ chức khi AI tự thanh toán là trên 50 triệu/lần và trên 100 triệu/ngày [L1].
- **AI đã đủ tốt để đọc và khớp hàng hóa** mà không cần huấn luyện riêng [P1], nhưng **vẫn có thể bị lừa** [P7, P8]. Đây đúng là lúc cần một sản phẩm biết dùng AI một cách an toàn.

---

## 4. Mục tiêu và chỉ số thành công

| Mục tiêu nghiệp vụ | Chỉ số | Mục tiêu trong demo / thử nghiệm |
|---|---|---|
| MT1. Không trả tiền sai | Số khoản trả sai thực sự bị trừ tiền (sai người, sai số tiền, vượt hạn mức) | **0** trên bộ ca thử |
| MT2. Bắt được tính đắt ngầm | Tỷ lệ bắt đúng lỗi tráo quy cách, nhích giá | ≥ 90% trên bộ ca thử |
| MT3. Chặn lừa đảo thanh toán | Tỷ lệ chặn đúng ca đổi tài khoản, cọc tài khoản cá nhân, câu lệnh giấu | 100% không bị trả tiền; ≥ 90% được gắn đúng lý do |
| MT4. Không làm phiền vô ích | Tỷ lệ hỏi thừa hoặc chặn nhầm hóa đơn đúng | ≤ 10% |
| MT5. Tiết kiệm thời gian | Số dòng chủ chuỗi phải tự xem trên tổng số hóa đơn | Từ 100% xuống chỉ còn các dòng vàng/đỏ. Thời gian thực tế đo bằng thử nghiệm với 3–5 người |
| MT6. Bảo vệ cả mạng lưới | Thời gian từ khi phát hiện kẻ gian ở một cửa hàng đến khi cửa hàng khác được cảnh báo | Ngay khi nhân viên MoMo bấm cảnh báo chéo |

*Các mục tiêu này đo trên dữ liệu mô phỏng và bộ ca thử của đội, chưa phải số liệu vận hành thật.*

---

## 5. Người dùng và các bên liên quan

### 5.1. Người dùng chính: chủ chuỗi cửa hàng

**Chị Lan, 34 tuổi** (hư cấu), đồng sáng lập chuỗi 5 quán cà phê ở TP.HCM, doanh thu khoảng 8 tỷ/năm, có một kế toán bán thời gian.
- **Muốn:** trả đúng, trả nhanh, không bị lừa, không mất buổi tối cuối tuần.
- **Sợ:** chuyển nhầm cho kẻ gian; bị nhà cung cấp "ăn gian"; giao việc cho AI rồi AI tự tiêu tiền.
- **Mức công nghệ:** dùng thạo app điện thoại, không rành kế toán.

### 5.2. Các vai khác

| Vai | Là ai | Dùng PayMatch để làm gì |
|---|---|---|
| Kế toán | Nhân viên bán thời gian của chuỗi | Xem kết quả đối soát, xử lý các dòng vàng, lưu chứng từ |
| Quản lý quán | Quản lý từng chi nhánh | Xác nhận đã nhận đủ hàng (để giải ngân cọc tạm giữ) |
| **Nhân viên rủi ro MoMo** | Đội quản trị rủi ro merchant | Xem luồng cảnh báo toàn mạng lưới, bấm cảnh báo chéo, ngắt khẩn cấp |
| CSKH MoMo | Đội chăm sóc khách hàng | Tra lại bằng chứng của một khoản chi khi có khiếu nại |
| Nhà cung cấp | Bên nhận tiền | Không dùng app; được hưởng lợi vì được trả đúng hạn, đúng tài khoản |

### 5.3. Đội rủi ro của MoMo làm việc khác đi thế nào
- **Hôm nay:** xử lý khiếu nại **sau khi** merchant đã mất tiền.
- **Với PayMatch:** thấy kẻ gian **trước khi** tiền đi, trên hàng nghìn cửa hàng cùng lúc. Một lần phát hiện bảo vệ được mọi cửa hàng khác.

Đây là phần "Future Workspace" của đề tài: AI làm việc đọc và kiểm tra; con người chuyển sang làm việc quyết định và giám sát.

---

## 6. Phạm vi

### 6.1. Trong phạm vi
- Các khoản chi định kỳ của chuỗi: nguyên liệu, bao bì, điện nước, phần mềm.
- Hóa đơn điện tử dạng XML; hóa đơn ảnh hoặc PDF ở chế độ dự phòng.
- Duyệt chi, tự chi trong hạn mức, cọc tạm giữ cho người bán mới.
- Console cho nhân viên rủi ro MoMo.

### 6.2. Ngoài phạm vi
- Chuyển tiền thật (demo chạy trên sổ sandbox).
- Kê khai thuế, thay phần mềm kế toán.
- Nhắn Zalo, gọi điện hay mặc cả với nhà cung cấp.
- Tự đăng nhập cổng thuế (để ở lộ trình, làm qua đối tác hóa đơn điện tử).
- Chặn lừa đảo qua cuộc gọi, mã độc trên điện thoại.

---

## 7. Quy trình hiện tại và quy trình mới

### 7.1. Hiện tại (AS-IS)
1. Hóa đơn về rải rác qua email, Zalo, cổng hóa đơn.
2. Kế toán mở từng hóa đơn, so tay với hợp đồng và phiếu nhập kho.
3. Kiểm tra tài khoản nhận tiền chủ yếu bằng mắt, nhiều khi tin tin nhắn Zalo.
4. Lập danh sách chi, gửi chủ chuỗi duyệt cuối tuần.
5. Chuyển khoản từng khoản.
6. Điện nước trả tự động, không ai so với các tháng trước.

### 7.2. Với PayMatch (TO-BE)
1. Hóa đơn **tự về** PayMatch: email nhận hóa đơn riêng của chuỗi, cổng hóa đơn của cơ quan thuế, hóa đơn điện nước từ dịch vụ thanh toán hóa đơn của MoMo.
2. AI đọc từng hóa đơn, so với hợp đồng, soát người nhận, so điện nước với 12 tháng trước.
3. Mọi hóa đơn được xếp vào 🟢 khớp hết / 🟡 có điểm lạ / 🔴 nguy hiểm, kèm lý do.
4. 🟢 dưới hạn mức thì **tự trả** (nếu chủ chuỗi bật chế độ này); 🟡 và 🔴 chờ chủ chuỗi quyết.
5. Khóa an toàn bằng code phát **lệnh trả dùng một lần** cho đúng hóa đơn, đúng tài khoản.
6. Mọi khoản chi đều gắn với một hóa đơn, một hợp đồng, một người duyệt, nên tra lại được.

**Dữ liệu chỉ nhập một lần lúc bắt đầu:** hợp đồng khung (giá, quy cách) và danh sách nhà cung cấp kèm tài khoản đã xác minh.

---

## 8. Sản phẩm làm được gì: tính năng chính

### TN1 — Đọc hóa đơn và so với hợp đồng
- **AI làm:** đọc tên hàng ghi tự do, nhận ra đó là mặt hàng nào trong hợp đồng, tách quy cách (thùng bao nhiêu cái, chai bao nhiêu ml).
- **Code làm:** quy về giá của một cái, so với hợp đồng, đối chiếu lại mọi con số trên file XML gốc.
- **Giải quyết:** nỗi đau 1 (bị tính đắt ngầm), nỗi đau 5 (đối soát thủ công).

### TN2 — Soát người nhận tiền và tin nhắn lạ
- **AI làm:** đọc ghi chú, email, tin nhắn đi kèm; nhận ra chiêu hối thúc, đổi tài khoản, đòi cọc vào tài khoản cá nhân, câu lệnh giấu dành cho AI.
- **Code làm:** chỉ chấp nhận tài khoản **đã xác minh từ trước** và khớp mã số thuế; tra danh sách doanh nghiệp rủi ro.
- **Giải quyết:** nỗi đau 2 (chuyển nhầm cho kẻ gian), nỗi đau 3 (công ty rủi ro).

### TN3 — Canh hóa đơn điện nước
- **Code làm:** tính khoảng bình thường của từng quán từ 12 tháng trước.
- **AI làm:** viết một câu dễ hiểu khi có bất thường, ví dụ: "Tiền nước quán 3 tháng này gấp khoảng 6 lần bình thường, có thể bị rò ống."
- **Giải quyết:** nỗi đau 4.

### TN4 — Trợ lý duyệt chi
- **AI làm:** gom mọi hóa đơn thành ba màu; mỗi dòng vàng/đỏ có một câu lý do và **chỉ thẳng vào dòng sai trên hóa đơn gốc**.
- **Chủ chuỗi làm:** bấm "Duyệt" hoặc "Từ chối".
- **Giải quyết:** nỗi đau 5; giữ con người là người quyết định cuối cùng.

### TN5 — Khóa an toàn và cách trả tiền an toàn (không phải AI)
- Lệnh trả chỉ phát khi khớp hợp đồng, đúng tài khoản đã xác minh, trong ngân sách và hạn mức.
- Ba cách trả:
  - **lệnh chi một lần** (mặc định);
  - **thẻ ảo một lần** (cho dịch vụ online);
  - **cọc tạm giữ** qua ngân hàng đối tác (cho người bán mới; nhận đủ hàng mới giải ngân).
- **Giải quyết:** dù AI có bị lừa, kẻ gian cũng không lấy được tiền ngoài đúng một hóa đơn đã duyệt.

### TN6 — Console cho nhân viên rủi ro MoMo
- Luồng cảnh báo đỏ trên toàn mạng lưới; **cảnh báo chéo** sang các cửa hàng khác; tra bằng chứng khi có khiếu nại; nút ngắt khẩn cấp.
- **Giải quyết:** một kẻ gian bị phát hiện ở một nơi thì cả mạng lưới được bảo vệ.

---

## 9. Yêu cầu nghiệp vụ

| Mã | Yêu cầu | Ưu tiên | Nỗi đau |
|---|---|---|---|
| BR-01 | Hệ thống phải tự nhận hóa đơn từ email nhận hóa đơn riêng của chuỗi và từ file XML tải lên | Bắt buộc | 5 |
| BR-02 | Hệ thống phải nhận ra mặt hàng trên hóa đơn tương ứng với mặt hàng nào trong hợp đồng, kể cả khi tên ghi khác nhau | Bắt buộc | 1 |
| BR-03 | Hệ thống phải quy mọi mặt hàng về giá của một đơn vị và báo lệch so với hợp đồng | Bắt buộc | 1 |
| BR-04 | Hệ thống chỉ được trả vào tài khoản đã xác minh và khớp mã số thuế của nhà cung cấp | Bắt buộc | 2 |
| BR-05 | Tin nhắn, email hay ghi chú **không bao giờ** được làm thay đổi tài khoản nhận tiền | Bắt buộc | 2 |
| BR-06 | Hệ thống phải gắn cờ người bán đòi cọc vào tài khoản cá nhân, và chỉ cho phép trả qua cọc tạm giữ | Bắt buộc | 2, 3 |
| BR-07 | Hệ thống phải tra nhà cung cấp trong danh sách doanh nghiệp rủi ro về thuế và hóa đơn | Bắt buộc | 3 |
| BR-08 | Hệ thống phải so hóa đơn điện nước với khoảng bình thường 12 tháng của đúng chi nhánh | Bắt buộc | 4 |
| BR-09 | Mọi hóa đơn phải được xếp xanh/vàng/đỏ, kèm lý do và vị trí lỗi trên hóa đơn gốc | Bắt buộc | 5 |
| BR-10 | Chủ chuỗi phải có 3 chế độ: chỉ đối soát / hỏi trước khi chi / tự chi hóa đơn quen | Bắt buộc | 5 |
| BR-11 | Mỗi lệnh trả chỉ dùng được một lần, cho đúng một hóa đơn và đúng người nhận | Bắt buộc | 2 |
| BR-12 | Nhân viên rủi ro MoMo phải gắn được cảnh báo chéo và ngắt khẩn cấp | Bắt buộc | 2, 3 |
| BR-13 | Mọi khoản chi phải tra ngược được: khoản chi → hóa đơn → hợp đồng → người duyệt | Bắt buộc | 3, 5 |
| BR-14 | Hệ thống nên đọc được hóa đơn ảnh hoặc PDF khi không có XML, và luôn gắn cờ vàng cho loại này | Nên có | 5 |
| BR-15 | Hệ thống nên đồng bộ hóa đơn mua vào từ cổng của cơ quan thuế | Lộ trình | 3, 5 |

---

## 10. Quy tắc nghiệp vụ

| Mã | Quy tắc |
|---|---|
| QT-01 | **Tự chi** chỉ khi: khớp 100% hợp đồng, đúng tài khoản đã xác minh, ≤ 30 triệu/hóa đơn, ≤ 50 triệu/ngày. Mức này thấp hơn ngưỡng rủi ro cao của Thông tư 53/2026 cho khách tổ chức [L1] |
| QT-02 | Điện nước chỉ tự chi khi nằm trong khoảng bình thường 12 tháng của chi nhánh đó |
| QT-03 | **Tự hạ quyền** về "hỏi trước khi chi" ngay khi: nhà cung cấp đổi tài khoản; đơn giá hoặc quy cách lệch; số lượng vượt định mức; hóa đơn trùng; nhà cung cấp rủi ro; có câu lệnh giấu; điện nước vượt khoảng; MoMo phát cảnh báo chéo |
| QT-04 | AI **không bao giờ** tự nới quyền, tự thêm nhà cung cấp hay tài khoản mới |
| QT-05 | Khoản mua không có hóa đơn: chỉ ghi nhận và nhắc lập bảng kê, không tự chi |
| QT-06 | Bật chế độ tự chi phải xác thực mạnh (sinh trắc học + một bước khác), theo yêu cầu của Thông tư 53 với thỏa thuận ký điện tử [L2] |
| QT-07 | Cảnh báo chéo chỉ buộc xác minh thêm; chặn cứng chỉ theo danh sách chính thức |

---

## 11. Yêu cầu phi chức năng (viết dễ hiểu)

| Nhóm | Yêu cầu |
|---|---|
| An toàn | Nội dung từ người bán chỉ là dữ liệu, không bao giờ thành lệnh; phần AI đọc hóa đơn không có quyền trả tiền |
| Chính xác | Mọi con số tiền do code tính, không do AI |
| Dễ dùng | Chủ chuỗi chỉ cần hiểu ba màu và hai nút; thẻ duyệt có 5 dòng |
| Tốc độ | Xử lý một đợt hóa đơn trong khoảng 30 giây, có hiển thị tiến trình |
| Minh bạch | Mỗi quyết định có lý do và bằng chứng gốc |
| Bảo mật dữ liệu | Demo chỉ dùng dữ liệu giả lập; khi triển khai thật phải tuân thủ Luật Bảo vệ dữ liệu cá nhân |
| Ổn định khi chấm | Không dùng hạ tầng bị "ngủ"; có model dự phòng và nút reset |

---

## 12. Giả định, ràng buộc, phụ thuộc

**Giả định (cần kiểm chứng bằng phỏng vấn 5–8 chủ chuỗi hoặc kế toán):**
- A1. Đa số hóa đơn cà phê, sữa, bao bì có XML **trước** lúc trả tiền.
- A2. Chủ chuỗi sẵn sàng cho tự chi các hóa đơn khớp 100% dưới 30 triệu.
- A3. Một phần doanh thu đang về MoMo Doanh Nghiệp.

**Ràng buộc:**
- Hạn nộp bài ngày 03/12/2026 (cần đối chiếu lại thể lệ).
- Không có quyền truy cập hệ thống thanh toán thật, nên dùng sandbox.

**Phụ thuộc:**
- Ngân hàng đối tác vận hành cọc tạm giữ.
- Danh sách doanh nghiệp rủi ro công khai của cơ quan thuế.
- Hạn mức chi của tài khoản MoMo Doanh Nghiệp (cần kiểm tra).

---

## 13. Rủi ro

| Rủi ro | Ảnh hưởng | Cách giảm |
|---|---|---|
| Hóa đơn không về trước lúc trả tiền | Ít hóa đơn được tự động hóa | Chọn nhóm hàng có hóa đơn; ảnh hoặc PDF thì gắn cờ vàng |
| AI đọc sai hoặc bị lừa | Đề xuất sai | Khóa an toàn bằng code; con người duyệt mọi dòng vàng/đỏ |
| Báo nhầm nhiều, gây phiền | Người dùng tắt app | Mục tiêu hỏi thừa ≤ 10%; điều chỉnh ngưỡng theo ca thử |
| Bị hỏi "sao không để MISA hay ngân hàng làm?" | Mất điểm khác biệt | MISA kiểm tra sau để kê khai; PayMatch chặn trước ở cổng chi; tiền của merchant đã nằm ở MoMo |
| Cọc tạm giữ vướng pháp lý | Khó triển khai thật | Ngân hàng đối tác vận hành; ghi rõ cần kiểm tra |

---

## 14. Kịch bản minh họa: một tuần của chị Lan

| Hóa đơn | PayMatch phát hiện | Kết quả |
|---|---|---|
| Cà phê hạt, 26,5 triệu | Đúng giá, đúng tài khoản | 🟢 Tự trả |
| Sữa, 31 triệu | Zalo người bán gửi số tài khoản mới | 🔴 Giữ lại, nhắc gọi lại số trong hợp đồng |
| Cốc nhựa, 22,4 triệu | Thùng 800 cái thay vì 1.000 cái, đắt hơn 21,7% | 🟡 Hỏi chị Lan |
| Si-rô người bán mới | Đòi cọc vào tài khoản cá nhân, công ty rủi ro, có câu lệnh giấu cho AI | 🔴 Chặn, chỉ cho phép cọc tạm giữ |
| Phần mềm bán hàng, 12 triệu | Đúng hợp đồng | 🟢 Tự trả bằng thẻ ảo một lần |
| Tiền nước quán 3, 4,2 triệu | Gấp khoảng 6 lần bình thường | 🟡 Giữ lại, báo có thể rò nước |

**Bẫy cuối:** số thẻ ảo bị đánh cắp và dùng thử ở nơi khác, nên bị từ chối. Nhân viên rủi ro MoMo gắn cảnh báo chéo cho người bán si-rô; một nhà hàng khác vừa bị người này đòi cọc được cảnh báo ngay.

---

## Phụ lục A — Cách làm kỹ thuật dựa trên nghiên cứu có sẵn

| Tính năng | Kỹ thuật | Nghiên cứu tham khảo | Ý chính dùng cho sản phẩm |
|---|---|---|---|
| TN1 khớp hàng hóa | Khớp thực thể bằng LLM | EDBT 2025 [P1]; VLDB 2021 [P2] | LLM khớp tốt mà không cần huấn luyện riêng |
| TN1 tính đơn giá | LLM đọc, code tính | ICML 2023 [P3] | LLM hay sai phép tính, nên giao cho code |
| TN1 ảnh/PDF | Đọc tài liệu không cần OCR | ECCV 2022 [P4] | Có mô hình mở sẵn cho hóa đơn, biên lai |
| TN2 câu lệnh giấu | Tách lệnh và dữ liệu | AISec @ CCS 2023 [P5]; USENIX Security 2025 [P6] | Dữ liệu từ bên ngoài không bao giờ thành lệnh |
| TN5 khóa an toàn | Đánh giá agent trước tấn công | ACL 2024 [P7]; NeurIPS 2024 [P8] | AI vẫn bị lừa một phần số lần, nên bắt buộc có khóa cứng |
| TN2 chiêu thao túng | Phân loại kỹ thuật tâm lý trong lừa đảo | EMNLP 2025 [P9] | Bộ nhãn sẵn để dựng dấu hiệu và ca thử |
| TN4 thẻ duyệt | Thiết kế để người dùng không tin AI mù quáng | CHI 2021 [P10] | Giải thích làm người dùng dễ tin cả khi AI sai, nên phải chỉ vào bằng chứng gốc |

**Cách đo:** dựng khoảng 36 ca thử theo cách của [P7, P8]. So sánh 3 cấu hình: một AI tự làm tất cả / thêm khóa cứng / sản phẩm đầy đủ.

## Phụ lục B — Giải thích thuật ngữ

| Thuật ngữ | Nghĩa đơn giản |
|---|---|
| Hóa đơn XML | File hóa đơn điện tử dạng máy đọc được, có giá trị pháp lý |
| Đối soát | So hóa đơn với hợp đồng và hàng đã nhận |
| Quy cách | Cách đóng gói: thùng bao nhiêu cái, chai bao nhiêu ml |
| Cọc tạm giữ | Tiền cọc nằm ở ngân hàng; nhận đủ hàng mới chuyển cho người bán |
| Thẻ ảo một lần | Số thẻ chỉ dùng được một lần, cho đúng một người bán, đúng số tiền |
| Câu lệnh giấu (prompt injection) | Câu kẻ gian giấu trong hóa đơn để lừa AI làm theo |
| Cảnh báo chéo | Phát hiện kẻ gian ở một cửa hàng thì cảnh báo cho mọi cửa hàng khác |
| Tự hạ quyền | Gặp điều bất thường thì app tự chuyển về chế độ hỏi người dùng |

## Phụ lục C — Nguồn

**Dữ liệu và thị trường**
- D1. VCCI dẫn báo cáo iPOS.vn — https://www.vcci.com.vn/tin-tuc/doanh-nghiep-fb-nen-lam-gi-truoc-ap-luc-gia-nguyen-lieu-dat-do
- D2. Báo Pháp luật VN — https://doanhnhan.baophapluat.vn/quy-mo-726-500-ty-dong-nganh-f-b-buoc-vao-chu-ky-thanh-loc-khoc-liet-ve-nang-luc-quan-tri.html
- D3. The Leader — https://theleader.vn/ap-luc-chi-phi-tai-dinh-hinh-cuoc-choi-nganh-fb-d45302.html
- D4. Đại biểu Nhân dân — https://daibieunhandan.vn/print/10401740.html
- D5. Báo Đầu tư, cảnh báo của Agribank — https://baodautu.vn/agribank-canh-bao-doanh-nghiep-ve-giao-dich-lua-dao-qua-email-d84153.html
- D6. CafeF, Zalo bị chiếm gửi QR giả — https://cafef.vn/tat-ca-nguoi-dan-co-zalo-chu-y-thong-bao-moi-nhat-tu-cong-an-188261106152317416.chn
- D7. VnEconomy, đối chiếu hóa đơn với dòng tiền — https://vneconomy.vn/doi-chieu-du-lieu-hoa-don-dien-tu-voi-dong-tien-ngan-hang-ho-kinh-doanh-kho-khai-man.htm
- D8. AFP 2026 Payments Fraud and Control Survey (doanh nghiệp Mỹ) — https://www.financialprofessionals.org/about/learn-more/press-releases/Details/over-75-percent-of-us-firms-experienced-payments-fraud-in-2025-while-ai-adoption-for-fraud-mitigation-lags
- D9. MISA AMIS, danh sách doanh nghiệp rủi ro — https://amis.misa.vn/295073/danh-sach-doanh-nghiep-rui-ro-cao-ve-thue-hoa-don/
- D10. MISA meInvoice, hệ quả bị loại chi phí — https://www.meinvoice.vn/?p=19785
- D11. VietNamNet, nhập hàng F&B (bài có dáng PR, chỉ dùng định tính) — https://vietnamnet.vn/loi-giai-cho-bai-toan-nhap-hang-cua-quan-an-nha-hang-2486103.html

**MoMo**
- M1. Doanh thu về MoMo ngay sau khi khách quét mã — https://www.momo.vn/tin-tuc/thong-bao/momo-doanh-nghiep-cap-nhat-thoi-gian-thanh-toan-3981
- M2. Giấy phép ví điện tử, thu hộ chi hộ, cổng thanh toán — https://momo.vn/momo-mot-troi-deal
- M3. Khảo sát 203 SME; chiến lược Thanh toán – Vận hành – Tín dụng — https://www.momo.vn/tin-tuc/thong-cao-bao-chi/bo-giai-phap-tai-chinh-tu-momo-giup-tieu-thuong-7891

**Pháp lý** (cần đối chiếu văn bản gốc)
- L1. Thông tư 53/2026/TT-NHNN — https://cafef.vn/ai-trong-ngan-hang-phai-tuan-thu-nhung-quy-dinh-gi-188261116174446259.chn
- L2. Thông tư 53/2026, thỏa thuận ký điện tử — https://luatvietnam.vn/legal-updates/circular-no-53-2026-tt-nhnn-ai-automated-payments-for-individual-customers-must-not-exceed-vnd-100-million-per-day-892-113479-article.html
- L3. Thông tư 25/2025/TT-NHNN (tài khoản đúng tên tổ chức, hộ kinh doanh)
- L4. Nghị định 254/2026/NĐ-CP (hóa đơn điện tử từ 01/7/2026)

**Đối thủ**
- C1. MISA AMIS, cảnh báo nhà cung cấp rủi ro — https://helpact.misa.vn/?p=32001
- C2. MISA meInvoice, cảnh báo hóa đơn vượt định mức — https://www.meinvoice.vn/?p=24391

**Nghiên cứu**
- P1. Peeters et al., Entity Matching using LLMs, EDBT 2025 — https://arxiv.org/abs/2310.11244
- P2. Li et al., Ditto, VLDB 2021 — https://arxiv.org/abs/2004.00584
- P3. Gao et al., PAL, ICML 2023 — https://proceedings.mlr.press/v202/gao23f.html
- P4. Kim et al., Donut, ECCV 2022 — https://github.com/clovaai/donut
- P5. Greshake et al., Indirect Prompt Injection, AISec @ ACM CCS 2023 — https://arxiv.org/abs/2302.12173 (cần xác nhận lại hội nghị)
- P6. Chen et al., StruQ, USENIX Security 2025 — https://www.usenix.org/conference/usenixsecurity25/presentation/chen-sizhe
- P7. Zhan et al., InjecAgent, ACL 2024 Findings — https://aclanthology.org/2024.findings-acl.624
- P8. Debenedetti et al., AgentDojo, NeurIPS 2024 — https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract.html
- P9. Ma et al., PsyScam, EMNLP 2025 Findings — https://preview.aclanthology.org/dashboard/2025.findings-emnlp.675
- P10. Bansal et al., CHI 2021 — https://doi.org/10.1145/3411764.3445717
