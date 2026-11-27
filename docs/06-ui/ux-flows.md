# Đề xuất Luồng UX & Màn hình v1 cho PayMatch

> **Trạng thái:** Tài liệu tham chiếu kỹ thuật–nghiệp vụ (*evidence-backed UX reference*), đối chiếu trực tiếp với [problem-definition.md](../01-requirements/problem-definition.md), [flows.md](../02-architecture/flows.md), [merchant-api.md](../05-api/merchant-api.md), [console-api.md](../05-api/console-api.md), [events.md](../05-api/events.md), [schemas.md](../05-api/schemas.md), [sim-world-dataset.md](../04-data/sim-world-dataset.md) và file hợp đồng hiện có `contracts/openapi/core-merchant.yaml` (v0.1.0). Không sửa `contracts/`; mọi khoảng trống hợp đồng được gom thành đề xuất ở **Mục 8**.
>
> **Mức ràng buộc.** Chỉ 5 bất biến dưới đây là bắt buộc (đến từ spec an toàn, đổi phải sửa spec trước). Mọi thứ còn lại (bố cục, component, chữ hiển thị, màu, hiệu ứng, chu kỳ polling, thứ tự màn hình, wireframe) là **gợi ý**, FE tinh chỉnh tự do khi dựng. Số cụ thể trong wireframe chỉ để minh họa từ bộ dữ liệu demo; UI luôn hiển thị số API trả về, không chép số từ tài liệu này. Thời gian/ngân sách bot, số bot bắt buộc và hạn mức đọc từ API/spec, không viết cứng ở client.
>
> 1. **Người nhận và SĐT gọi xác minh chỉ lấy từ danh bạ** (`ApprovalPreview.payee`, `phone_on_file_masked`), không bao giờ từ hóa đơn, email hay Zalo ([F12](../02-architecture/flows.md)). STK/SĐT trong tin nhắn chỉ được hiện ở khung `untrusted`.
> 2. **Mọi số tiền, đơn giá, % lệch, màu do backend tính**; UI chỉ định dạng (kể cả không tự nhân VAT). Giá hợp đồng và `price_check` là giá **chưa VAT** ([schemas.md](../05-api/schemas.md) `ContractItem`).
> 3. **🔴 không có nút duyệt đè** (D5); nút Duyệt chỉ bật khi `gate_decision = REQUIRE_APPROVAL` và preview còn hạn.
> 4. **`UntrustedText` chỉ render text thuần** (§1.1).
> 5. **Đọc lỗi theo `code` rồi `errors[].code`** ([README §5](../05-api/README.md)): ví dụ `409 INVALID_STATE` + `MANDATE_REVIEW_ONLY`.

## 1. Kiến trúc thông tin (Information Architecture) & Nguyên tắc nền

### 1.1. Stack & Quy tắc an toàn hiển thị bắt buộc

| Thành phần | Lựa chọn cố định | Quy tắc áp dụng cho PayMatch |
|---|---|---|
| **Framework & Data** | `React + Vite`, `TanStack Query` | Cache theo khóa `['invoice', invoiceId]`, `['approval-queue', groupBy]`, `['job', jobId]`; tự `invalidateQueries` khi nhận sự kiện SSE trên `GET /m/events`. |
| **SSE Transport** | `@microsoft/fetch-event-source` | Gửi `Authorization: Bearer <session_jwt>` và `Last-Event-ID`; **tuyệt đối không truyền JWT trên query string** ([events.md §3](../05-api/events.md#3-sse)). Khi chạy `make mock` (Prism), tự fallback sang polling `GET /m/jobs/{job_id}` mỗi `1500ms`. |
| **UI & Animation** | `shadcn/ui`, `Tailwind CSS`, `Motion` | Mobile-first (`390×844`) cho `owner` (Chị Lan) duyệt buổi tối; tự mở rộng thành bố cục 2–3 cột (`1440×900`) cho `accountant` và `web-console`. |
| **Định dạng tiền & số** | `Intl.NumberFormat('vi-VN')` | Tiền là `integer` (`_vnd`), hiển thị `22.400.000 đ` + `tabular-nums` + dòng **Bằng chữ** ở màn hình xác nhận chi. Số lượng/đơn giá là chuỗi `Decimal`. |
| **Ranh giới `UntrustedText`** | Component `<UntrustedTextBlock />` | Mọi trường kiểu `UntrustedText` hoặc nằm trong `Invoice.untrusted` chỉ render text thuần (React auto-escape), **cấm `dangerouslySetInnerHTML` / Markdown / link bấm được**, có viền/nhãn phân biệt rõ với dữ liệu `trusted` từ `vendor_registry` và `Payment Gate`. |

### 1.2. Cấu trúc 2 ứng dụng + Thanh điều khiển Demo

> **Chưa chốt:** sơ đồ dưới theo bảng cổng ở [README §1](../05-api/README.md) (`apps/merchant` + `apps/console`). Nhóm đang cân nhắc gộp thành một app; khi chốt, ghi vào [architecture.md §9](../02-architecture/architecture.md) rồi sửa README và mục này.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ [D0] DEMO SCENARIO TOOLBAR (chỉ hiện khi DEMO_MODE=true · phím tắt Alt+D)              │
│ Chuyển vai 1 chạm (Chị Lan · Kế toán · Quản lý Quán 3 · Chuỗi B · MoMo Risk)           │
│ + Bắn 49 kịch bản (/sim/scenario/invoices:send, :swipe, clock:advance) + Reset Demo    │
└───────────────────────────────┬────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┴───────────────────────────┐
        ▼                                                   ▼
┌───────────────────────────────────────────┐   ┌────────────────────────────────────────┐
│ apps/merchant (:5173 → /m/* :8001)        │   │ apps/console (:5174 → /console/* :8002)│
├───────────────────────────────────────────┤   ├────────────────────────────────────────┤
│ • [M1] Hàng chờ duyệt & Tóm tắt ngày      │   │ • [C1] Luồng Cảnh báo & Case (RA, RL)  │
│   ├─ Duyệt hàng loạt [M6] (Sheet/Modal)   │   │   ├─ Phát Cảnh báo chéo 1 chạm (F3)    │
│   └─ Chi tiết HĐ & Thẻ duyệt 5 dòng [M2]  │   │   └─ Đề xuất Hard Block SIMO (2 người) │
│       ├─ Tab 1: 6 Bot Live SSE [M2.1]     │   │ • [C2] Kill Switch (Bật 1 / Gỡ 2 người)│
│       ├─ Tab 2: Đối chiếu HĐ↔HĐK/PO/Nước  │   │ • [C3] Tra bằng chứng CSKH (X-Ticket-Id│
│       ├─ Tab 3: Email/Zalo & Untrusted    │   │        + chuỗi 6 mắt xích, che PII)    │
│       ├─ Tab 4: XML/PDF gốc & Thuế        │   │ • [C4] Quản trị Bot & Model (PA - gọn) │
│       ├─ Modal Step-up Duyệt [M3]         │   └────────────────────────────────────────┘
│       ├─ Modal Từ chối + Mẫu điều chỉnh[M4]
│       └─ Wizard Gỡ khóa Đỏ (F12 / F7) [M5]│
│ • [M7] Danh sách toàn bộ Hóa đơn & Tải lên│
│ • [M8] Mandate, Hạn mức & Tạm ngưng QT-03 │
│ • [M9] Phiếu nhập kho GRN (cho Quản lý quán│
│ • [M10] Ngăn kéo Hỏi đáp Kế toán trưởng   │
└───────────────────────────────────────────┘
```

### 1.3. Phân quyền hiển thị theo vai trò (`role` / `staff_roles`)

| Màn hình / Thao tác | `owner` (Chị Lan) | `accountant` | `store_manager` | `risk_analyst` (`RA`) | `risk_lead` (`RL`) | `support_agent` (`CS`) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Xem Hàng chờ duyệt (`/m/approval-queue`), Findings, Tờ trình 5 dòng | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Bấm **Duyệt** / **Duyệt lô** / **Từ chối** / **Ký Mandate** / **Tạo Escrow** | ✅ *(Step-up)* | ❌ *(Khóa nút)* | ❌ | ❌ | ❌ | ❌ |
| Tải lên HĐ, nhập tay PDF, ghi nhận gọi lại `record-callback` (`F12`) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Xem HĐ thuộc quán mình & xác nhận Phiếu nhập kho (`POST /m/goods-receipts`) | ✅ *(16 điểm)* | ✅ *(Chỉ xem)* | ✅ *(1 điểm)* | ❌ | ❌ | ❌ |
| Hỏi đáp trợ lý (`/m/conversations`) | ✅ *(Toàn chuỗi)* | ✅ *(Toàn chuỗi)* | ✅ *(Chỉ quán mình)* | ❌ | ❌ | ❌ |
| Phát `CrossAlert` (`1 người`), bật `KillSwitch` (`1 người`), mở `Case` | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| Duyệt `propose_hard_block` & duyệt gỡ `KillSwitch` (`Checker ≠ Maker`) | ❌ | ❌ | ❌ | ❌ *(Chỉ đề xuất)* | ✅ *(Checker)* | ❌ |
| Tra `EvidenceChain` (bắt buộc nhập `X-Ticket-Id`, PII che `***`) | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |

---

## 2. Đặc tả từng màn hình v1 (Ánh xạ `shadcn/ui`, API & SSE)

| Mã & Tên màn hình | Mục tiêu chính | Thành phần `shadcn/ui` & `Motion` | Endpoint đọc/ghi (`merchant-api` / `console-api`) | Sự kiện SSE tự cập nhật |
|---|---|---|---|---|
| **M1. Hàng chờ duyệt & Tóm tắt ngày** (`ApprovalQueuePage`) | Cho Chị Lan thấy trong 3 giây: bao nhiêu khoản xanh đã tự trả êm, bao nhiêu khoản 🟡/🔴 cần quyết, gom theo NCC hoặc lý do. | `Card` (4 ô KPI đầu ngày), `Alert` (banner NCC bị tạm ngưng tự chi QT-03), `Tabs` (`vendor` \| `reason_code`), `Accordion`, `Badge`, `Checkbox` (chọn lô), `Button`, `Motion layoutId`. | `GET /m/approval-queue?group_by=`, `GET /m/summaries/daily` *(P)*, `GET /m/wallet` *(P)*, `GET /m/auto-pay-suspensions` *(P)*, `GET /m/notifications?unread=true`. | `GET /m/events`: `invoice.status_changed`, `payment.updated`, `notification.created` → làm mới hàng chờ + hiện `Sonner` toast. |
| **M2. Chi tiết Hóa đơn & Thẻ duyệt 5 dòng** (`InvoiceReviewWorkspace`) | Đọc tờ trình 5 dòng, kiểm đối chiếu gốc và ra quyết định trong 15 giây mà không chuyển trang. | Desktop: `ResizablePanelGroup` (Trái: Thẻ duyệt + Gate; Phải: `Tabs` bằng chứng). Mobile: `ScrollArea` + thanh đáy dính (`sticky bottom bar`) + `Drawer` bằng chứng. | `GET /m/invoices/{invoice_id}`, `GET /m/invoices/{invoice_id}/findings`, `GET /m/invoices/{invoice_id}/approval-preview` *(chỉ `owner`)*, `GET /m/invoices/{invoice_id}/document` *(P)*. | `GET /m/jobs/{job_id}/events` (khi `status = investigating`); `GET /m/events` (`payment.updated`, `invoice.status_changed`). |
| **M3. Xác thực mạnh & Xác minh gọi lại** (`StepUpApprovalDialog`) | Hiển thị cam kết chi cuối cùng từ `Payment Gate`, thu xác nhận gọi lại (nếu có `CROSS_ALERT_HIT`) và ký `auth_proof` gắn `action_hash`. | `Dialog` (desktop) / `Drawer` (mobile), `RadioGroup` (kết quả gọi lại), `InputOTP` (6 ô `demo_otp`), `Switch` (*"Chi ngay hôm nay"*), `Alert`. | `POST /sim/identity/step-up-challenges` → `:verify` → `POST /m/invoices/{invoice_id}:approve` (kèm `Idempotency-Key`) → tùy chọn `POST /m/invoices/{invoice_id}:pay-now` *(P)*. | Sau `:pay-now`, lắng nghe `payment.updated` (`executing` → `settled` \| `failed`) để đổi sang màn hình biên lai xanh. |
| **M4. Từ chối & Mẫu yêu cầu điều chỉnh** (`RejectInvoiceDialog`) | Từ chối đúng mã lý do và trao ngay văn bản chuẩn do **code** điền số liệu để chủ chuỗi gửi NCC xuất HĐ điều chỉnh (`D3`). | `Dialog`, `Select` (`reason_code`), `Textarea` (`note`), `Card` (khung văn bản `AdjustmentRequest`), `Button` (`Copy` + phản hồi `Sonner`). | `POST /m/invoices/{invoice_id}:reject`, `GET /m/invoices/{invoice_id}/adjustment-request`. | `invoice.status_changed` (`to: "rejected"`). |
| **M5. Gỡ khóa Đỏ 🔴 (`F12` Đổi TK & `F7` Cọc `Escrow`)** (`UnblockRedSheet`) | Cung cấp đúng **một đường gỡ an toàn** cho từng mã đỏ có thể gỡ (`D5`, `§6b`), chặn tuyệt đối chuyển khoản thẳng. | `Sheet`, Stepper 3 bước, `Form`, `Input`, `Select`, `Alert` đỏ cảnh báo VAT NĐ 181/2025, `InputOTP` step-up. | **F12:** `POST /m/vendors/{id}/account-changes` *(P)* → `:record-callback` *(P)* → `:approve` *(P)*.<br>**F7:** `POST /m/vendors` *(P)* → `account-changes (escrow_only)` *(P)* → `POST /m/purchase-orders` *(P)* → `escrow-preview` *(P)* → `POST /m/escrows` *(P)*. | `vendor_account.changed` → HĐ tự quay về `investigating`; `escrow.held` → HĐ sang `escrow_held`. |
| **M6. Duyệt hàng loạt** (`BulkApprovalDrawer`) | Duyệt 1 lần cho nhóm HĐ xanh ở `ask_first`, xanh vượt trần ngày 50tr (`EDGE_BULK_OVER_DAILY`), hoặc vàng nhẹ (`EDGE_NON_XML_PDF_SMALL` ≤ 2tr). | `Drawer`, `Table` (tách 2 nhóm `Đủ điều kiện` vs `Bị loại khỏi lô`), `Badge` (`ExclusionCode`), `InputOTP`. | `POST /m/approval-batches:preview` *(P)* → step-up với `action_hash` của lô → `POST /m/approval-batches` *(P)*. | `invoice.status_changed` cho từng HĐ trong lô. |
| **M7. Danh sách Hóa đơn & Tải lên** (`InvoicesListPage`) | Tra cứu toàn bộ hóa đơn (kể cả 🟢 đã `paid`), lọc đa chiều và tải file XML/PDF/ảnh thử nghiệm. | `Table`, `Command` / bộ lọc Popover (`status`, `severity`, `invoice_type`, `reason_code`), `Dialog` kéo-thả upload file. | `GET /m/invoices`, `POST /m/invoices:upload`, `PATCH /m/invoices/{id}/manual-fields` *(P)*. | `invoice.status_changed`. |
| **M8. Mandate & Tạm ngưng QT-03** (`MandatePage`) | Cài đặt 3 chế độ (`review_only` / `ask_first` / `auto_pay`), hạn mức ≤ trần 30tr/50tr và bật lại NCC bị treo tự chi. | `RadioGroup` (3 chế độ), `Slider` / `Input` có vạch khóa trần nền tảng, `MultiSelect` NCC, `Table` `AutoPaySuspension`. | `GET /m/platform-limits` *(P)*, `GET /m/mandate` *(P)*, `POST /m/mandates` *(P, step-up)*, `GET /m/auto-pay-suspensions` *(P)*, `POST /m/auto-pay-suspensions/{vendor_id}:lift` *(P)*. | — |
| **M10. Ngăn kéo Hỏi đáp Kế toán trưởng** (`AssistantSheet`) | Hỏi đáp chỉ-đọc về chi tiêu, NCC, hóa đơn kèm bảng số liệu trích dẫn `tool_call` và nút hành động gợi ý. | `Sheet` trượt phải, bong bóng chat, `Table` kết quả, `Badge` `[Nguồn: tool_call]`, `Button` cho `ProposedAction`. | `POST /m/conversations` *(P)*, `POST /m/conversations/{id}/messages` *(P)*, `GET /m/conversations/{id}` *(P)*. | `GET /m/jobs/{job_id}/events`: `answer.delta` (streaming nháp) → `job.completed` (tải lại bản đã kiểm số). |
| **C1–C3. MoMo Console tối thiểu** (`ConsoleApp`) | Giám sát cảnh báo đỏ toàn mạng, phát cảnh báo chéo 1 chạm, bật/gỡ Kill Switch và tra bằng chứng CSKH có ticket. | `Tabs` (`Cảnh báo & Cảnh báo chéo` \| `Kill Switch` \| `Tra bằng chứng CSKH`), `Table`, `Badge`, `Dialog` xác nhận khẩn cấp, `Input` mã `X-Ticket-Id`. | `GET /console/alerts`, `GET /console/alerts/{id}`, `POST /console/cross-alerts`, `POST /console/cases`, `POST /console/kill-switches`, `POST /console/kill-switches/{id}/release-requests`, `GET /console/evidence` *(tất cả chưa có OpenAPI YAML — xem Mục 8)*. | Polling `2000ms` (hoặc đề xuất `GET /console/events` ở Mục 8). |

*(Ký hiệu `*(P)*`: đã có trong đặc tả `docs/05-api/*.md` nhưng chưa khai báo trong `contracts/openapi/core-merchant.yaml` v0.1.0 — xem đầy đủ ở Mục 8).*

---

## 3. Thẻ duyệt 5 dòng (`ApprovalCard`) — Ba trạng thái Xanh / Vàng / Đỏ

### 3.1. Cấu trúc cố định của Thẻ duyệt

Mỗi thẻ duyệt tuân thủ nghiêm ngặt quy tắc **tối đa 5 dòng tờ trình (`Brief.lines`, mỗi dòng ≤ 200 ký tự)** cộng phần **Header định danh `trusted`** và **Khung đối chiếu `ApprovalPreview` từ Payment Gate**:
- **Header (dữ liệu `trusted` + code parse):** Huy hiệu màu (`severity` do code tính) · Tên NCC từ `vendor_registry` (nếu `null` thì ghi rõ `NCC chưa đăng ký · MST ...` và để tên trên XML ở dòng phụ có nhãn `untrusted`) · Ký hiệu/Số HĐ · Tổng tiền `total_vnd` (`tabular-nums`) · Hạn trả `due_on`.
- **Thân 5 dòng (`Brief.lines` — `UntrustedText`, escape thuần):**
  1. *Dòng 1 — Tóm tắt hóa đơn & kết luận mức độ.*
  2. *Dòng 2 — Phát hiện chính về giá / quy cách / gian lận / điện nước.*
  3. *Dòng 3 — Kết quả đối chiếu PO, phiếu nhập kho & cổng Thuế/MST.*
  4. *Dòng 4 — Kết quả kiểm tra tài khoản thụ hưởng & tín hiệu mạng lưới.*
  5. *Dòng 5 — Hành động đề xuất cụ thể.*
- **Dải chip bằng chứng (`Brief.cited_evidence`):** `[Dòng HĐ #1]` · `[Hợp đồng #CUP-PP500]` · `[Phiếu nhập Bếp TT]` · `[Tin nhắn Zalo]` — bấm vào mở/cuộn tới đúng chứng từ gốc và tô sáng dòng đó.
- **Chân thẻ (do `Payment Gate` & `allowed_actions` quyết định, không do LLM):** Khung người nhận `ApprovalPreview.payee` + 2 nút hành động tương ứng trạng thái.

### 3.2. Wireframe trạng thái 🟡 VÀNG — Cần chủ chuỗi quyết (`BRD_03_CUPS_SHRINKFLATION`)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [🟡 CẦN XEM XÉT]  PACK_SIZE_CHANGED · PRICE_ABOVE_CONTRACT     Hạn: 03/12    │
│ CÔNG TY TNHH BAO BÌ NHỰA XANH VIỆT (MST: 0999010003 · Đã xác minh)           │
│ HĐĐT: 1C26TNX · Số 00000744 · Giao: Bếp Trung Tâm            22.400.000 đ    │
├──────────────────────────────────────────────────────────────────────────────┤
│ TỜ TRÌNH KẾ TOÁN TRƯỞNG (5 dòng · [Nhãn: Tổng hợp tự động, bấm chip để soi]) │
│  1. HĐ 1C26TNX/00000744 (40 thùng ly PP 500ml) tổng 22.400.000 đ cần duyệt. │
│  2. Quy cách giảm từ 1.000 cái/thùng (hợp đồng) xuống 800 cái/thùng — đơn    │
│     giá chưa VAT tăng từ 532 đ/cái lên 648 đ/cái (+21,74%).                  │
│  3. Khớp 3 chiều PO & phiếu nhập 40 thùng tại Bếp TT; MST & mã CQT hợp lệ.   │
│  4. TK trên HĐ khớp TK danh bạ ****0003 (NH Mẫu Nam Việt); không đổi TK.     │
│  5. Đề xuất: Từ chối để yêu cầu HĐ điều chỉnh, hoặc Duyệt nếu đã thỏa thuận. │
│                                                                              │
│  Bằng chứng gốc: [📄 Dòng HĐ #1] [📑 Hợp đồng 532đ/cái] [📦 Phiếu nhập 40th]│
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌─ SO SÁNH NHANH DO CODE TÍNH (Trusted · chưa VAT) ────────────────────────┐ │
│ │ Hợp đồng khung: Thùng 1.000 cái · 532.407 đ/thùng  =>  532,41 đ / cái    │ │
│ │ Hóa đơn này:    Thùng   800 cái · 518.519 đ/thùng  =>  648,15 đ / cái (+21,7%)
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ NGƯỜI NHẬN TỪ DANH BẠ (Gate REQUIRE_APPROVAL · Kênh: Chuyển khoản 1-1):      │
│ 🏦 CONG TY TNHH BAO BI NHUA XANH VIET · NH Mẫu Nam Việt · ****0003          │
│                                                                              │
│  [ ✕ Từ chối & Lấy mẫu điều chỉnh ]          [ ✓ Duyệt chi 22.400.000 đ → ]  │
└──────────────────────────────────────────────────────────────────────────────┘
```

> **Biến thể 🟡 có `CROSS_ALERT_HIT` (`verification_required = true`, kịch bản `TRAP_02`):** Giữa khung Người nhận và nút Duyệt chèn thêm hộp cảnh báo cam `⚠️ CẢNH BÁO CHÉO MẠNG LƯỚI MOMO: Bắt buộc gọi xác minh qua SĐT lưu sẵn 0900***001 trước khi mở khóa nút Duyệt` (SĐT lấy từ `phone_on_file_masked` của NCC trong danh bạ Chuỗi B).

### 3.3. Wireframe trạng thái 🔴 ĐỎ — Bị khóa cứng, không có nút Duyệt đè (`BRD_04_SYRUP_NEW_VENDOR_FRAUD`)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [🔴 ĐÃ CHẶN CỨNG]  HIDDEN_INSTRUCTION · PERSONAL_ACCOUNT · TAX_RISK_LIST     │
│ ⚠️ NCC chưa có trong danh bạ · MST: 0999090001                               │
│ Tên ghi trên XML [Untrusted]: CÔNG TY TNHH PHÂN PHỐI NGUYÊN LIỆU Á CHÂU MẪU  │
│ HĐĐT: 1C26TAC · Số 00000088                                   8.800.000 đ    │
├──────────────────────────────────────────────────────────────────────────────┤
│ TỜ TRÌNH KẾ TOÁN TRƯỞNG (5 dòng)                                             │
│  1. ĐÃ CHẶN (ĐỎ): HĐ 1C26TAC/00000088 tổng 8.800.000 đ từ MST lạ 0999090001. │
│  2. Phát hiện câu lệnh giấu (prompt injection) trong NBan/TTKhac nhằm lừa AI.│
│  3. Email & chat đòi chuyển cọc vào TK cá nhân TRAN THI HANH (998800011100). │
│  4. MST nằm trong DS rủi ro thuế cao (CV-9901); chi ≥ 5tr vào TK cá nhân mất │
│     quyền khấu trừ VAT (NĐ 181/2025).                                        │
│  5. Không thể chi trực tiếp. Chỉ Từ chối hoặc đặt cọc Escrow vào TK công ty. │
│                                                                              │
│  Bằng chứng: [🛡️ Xem câu lệnh giấu TTKhac] [💬 Tin nhắn đòi cọc] [🏛️ Rủi ro] │
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌─ RÀO CHẮN DỮ LIỆU BẨN & PAYMENT GATE: DENY (hard_rule) ─────────────────┐ │
│ │ • TK ghi kèm tin nhắn [Untrusted]: 998800011100 · TRAN THI HANH (Cá nhân)│ │
│ │ • TK trong danh bạ [Trusted]:      CHƯA CÓ — Gate chặn mọi lệnh chuyển   │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│  🔒 Hóa đơn Đỏ không có nút Duyệt đè (Quy tắc D5).                           │
│  [ ✕ Từ chối hóa đơn ]           [ 🛡️ Giao dịch thử qua Cọc tạm giữ (F7) ]  │
└──────────────────────────────────────────────────────────────────────────────┘
```

*(Với `BRD_02` Sữa 31tr bị khóa do `PAYEE_CHANGE_REQUEST`, nút bên phải tự đổi thành `[ 📞 Xác minh đổi TK qua SĐT lưu sẵn 0280***002 (F12) ]`. Số này là `phone_on_file` của NCC sữa trong danh bạ, **không phải** số Zalo `0900***233` vừa nhắn đổi TK: đó chính là kênh kẻ gian đang chiếm, gọi vào đó là xác minh với kẻ gian. Với `SCAM_SIMO_HARD_BLOCK` hoặc `DUPLICATE_INVOICE`, ẩn hoàn toàn nút gỡ — chỉ còn nút `[ ✕ Từ chối hóa đơn ]`).*

### 3.4. Wireframe trạng thái 🟢 XANH — Đã tự chi theo Mandate (`BRD_01` / `BRD_05`)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [🟢 KHỚP HẾT · ĐÃ TỰ CHI]  OK · Mandate v1 (≤ 30tr/HĐ)       08:06 26/11    │
│ CÔNG TY TNHH CÀ PHÊ RANG MỘC TÂY NGUYÊN (MST: 0999010001 · Tự chi bật)       │
│ HĐĐT: 1C26TTN · Số 00001425 · Giao: Bếp Trung Tâm            26.500.000 đ    │
├──────────────────────────────────────────────────────────────────────────────┤
│  1. HĐ 1C26TTN/00001425 (90 kg Robusta Đắk Nông) đạt mức xanh trên cả 5 bot. │
│  2. Đơn giá 272.633,74 đ/kg (chưa VAT) & quy cách gói 1kg khớp hợp đồng.    │
│  3. Khớp 3 chiều PO & phiếu nhập kho 90 kg tại Bếp Trung Tâm; mã CQT hợp lệ.│
│  4. TK nhận khớp TK đã xác minh ****0001 (NH Mẫu Á Châu); không có rủi ro.   │
│  5. Đã tự động thanh toán theo Mandate v1 · Mã lệnh Gate: pi_01M88557...     │
├──────────────────────────────────────────────────────────────────────────────┤
│ ✓ ĐÃ TẤT TOÁN 1-1 · Kênh: Chuyển khoản · Nội dung: 0999010001 · 1C26TTN · 1425│
│   [ 🔍 Xem chuỗi kiểm toán (HĐ → Hợp đồng → Finding → Mandate → Giao dịch) ] │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Màn hình Điều tra trực tiếp qua SSE (`LiveInvestigationView`)

### 4.1. Ánh xạ sự kiện `GET /m/jobs/{job_id}/events` sang UI & `Motion`

| Sự kiện SSE | Payload `data` | Cập nhật trạng thái UI & Hiệu ứng `Motion` |
|---|---|---|
| *(Mở trang)* | `GET /m/jobs/{job_id}` | Khởi tạo cây điều phối và thẻ bot từ `Job.bot_states` (không viết cứng số bot). Bot bắt buộc theo `invoice_type` ở [agent-lifecycle-and-memory.md](../03-agents/agent-lifecycle-and-memory.md): hiện `goods` 5 bot, `utility` chỉ `branch-operations` + `treasury`; bot khác chỉ hiện khi điều phối thật sự gọi. Nối `@microsoft/fetch-event-source` kèm `Last-Event-ID`. |
| `supervisor.step` | `{job_id, step, at}` | Nút trung tâm **Kế toán trưởng (`chief-accountant`)** sáng nhịp xung (`pulse`), tăng bộ đếm `Bước điều phối #step/12`. |
| `bot.started` | `{job_id, bot_id, at}` | Thẻ bot tương ứng chuyển từ `pending` (viền xám) sang `running` (viền xanh dương nhấp nháy, đồng hồ đếm giây; mốc ngân sách lấy theo [agent-runtime.md §2](../03-agents/agent-runtime.md), hiện `investigate_invoice` 30 s, không viết cứng ở client). |
| `bot.tool_called` | `{job_id, bot_id, tool_id, at}` | Thêm chip công cụ trượt mượt (`AnimatePresence`) vào chân thẻ bot bằng tên tiếng Việt dễ hiểu: `price_check` → *"Đang tính đơn giá cơ sở vs hợp đồng"*, `einvoice_portal` → *"Tra cổng HĐĐT Tổng cục Thuế"*, `chat_messages` → *"Quét luồng tin nhắn NCC"*. **Không hiển thị chữ `untrusted` trên SSE**. |
| `bot.finished` | `{job_id, bot_id, severity, at}` | Khóa thời gian chạy, đổi huy hiệu thẻ bot sang `🟢 OK` / `🟡 Chú ý` / `🔴 Chặn`; thu gọn danh sách tool thành số đếm `Đã kiểm 3 nguồn`. |
| `bot.failed` | `{job_id, bot_id, reason_code, at}` | Thẻ bot đổi sang **🟡 Vàng an toàn** (`BOT_TIMEOUT` / `BOT_INVALID_OUTPUT`), hiển thị rõ chú thích *"Bot quá hạn/lỗi → hệ thống tự nâng lên mức Vàng (Bất biến #9)"*. |
| `job.completed` | `{job_id, task_type, invoice_id, final_severity, reason_codes, at}` | Thanh gộp màu bằng **Code** chạy hiệu ứng hội tụ (`max(severity)`), đóng luồng SSE và gọi song song `GET /m/invoices/{id}` + `GET /m/invoices/{id}/findings` + `GET /m/invoices/{id}/approval-preview` để trượt mở **Thẻ duyệt 5 dòng**. |
| `resync` | `{reason: "cursor_expired"}` | Tự gọi `GET /m/jobs/{job_id}` đồng bộ lại toàn bộ `bot_states` mà không báo lỗi làm giật màn hình. |

### 4.2. Wireframe Sơ đồ Điều tra trực tiếp (Đang chạy ở giây thứ 11)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ⚡ PHÒNG KẾ TOÁN AI ĐANG ĐIỀU TRA HÓA ĐƠN 1C26TAC/00000088        ⏱ 11,4s   │
│   [Kế toán trưởng điều phối · Bước 2/12 · Không đọc dữ liệu bẩn trực tiếp]   │
├───────────────────────┬──────────────────────────┬───────────────────────────┤
│ 1. THU MUA            │ 2. CÔNG NỢ PHẢI TRẢ      │ 3. CHỐNG GIAN LẬN         │
│ [🟢 Xong · 4,2s]      │ [🟡 Xong · 5,8s]         │ [🔵 Đang quét... · 11,1s] │
│ ✓ vendor_contracts    │ ✓ purchase_orders        │ ✓ vendor_registry         │
│ ✓ price_check         │ ✓ goods_receipts         │ ✓ inbox                   │
│                       │ → Thiếu phiếu nhập kho   │ ⟳ chat_messages (Zalo)... │
├───────────────────────┼──────────────────────────┼───────────────────────────┤
│ 4. THUẾ               │ 5. VẬN HÀNH CHI NHÁNH    │ 6. THỦ QUỸ (Chỉ đề xuất)  │
│ [🔴 Xong · 6,5s]      │ [⚪ Không kích hoạt]     │ [🔵 Đang tính... · 3,0s]  │
│ ✓ einvoice_portal     │ (Chỉ chạy cho hóa đơn    │ ✓ account_balance         │
│ ✓ tax_risk_list       │  điện / nước chi nhánh)  │ ⟳ payment_policy_preview  │
│ → Trúng DS rủi ro CQT │                          │                           │
├───────────────────────┴──────────────────────────┴───────────────────────────┤
│ Khóa gộp màu bằng Code (Monotonic Max): Tạm tính ≥ [🔴 ĐỎ] · Đang chờ 2 bot │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Luồng Duyệt → Kết quả Payment Gate, Escrow & Chặn cứng

### 5.1. Sơ đồ luồng từ lúc bấm Duyệt đến kết quả thực thi của `Payment Gate`

```
Chủ chuỗi mở HĐ 🟡 ──► GET /approval-preview (Core hỏi Gate /evaluate, timeout 2s)
  ├── 503 UPSTREAM_UNAVAILABLE ──► Khóa nút Duyệt (Fail-closed) + Banner thử lại
  ├── gate_decision = DENY     ──► Khóa nút Duyệt + Hiện lý do GateReason (layer)
  └── gate_decision = REQUIRE_APPROVAL (hiệu lực 5 phút, kèm intent_hash & action_hash)
        │
        ▼ (Bấm "Duyệt chi")
  Mở StepUpApprovalDialog:
  1. Nếu verification_required = true (CROSS_ALERT_HIT):
     Bắt buộc tích "Đã gọi SĐT lưu sẵn 0900***001 → NCC xác nhận đúng (confirmed)" (số từ phone_on_file_masked)
     (Nếu chọn not_reachable / denied_by_vendor → chỉ mở nút "Từ chối")
  2. Hiển thị: Số tiền + Bằng chữ + TK danh bạ (****0003) + Nội dung CK chuẩn D2
  3. Gọi /sim/identity/step-up-challenges {momo_token, action_hash}
     → Điền nhanh / nhập OTP (demo_otp: 123456) → :verify → nhận auth_proof (JWT 1 lần)
  4. POST /m/invoices/{id}:approve {intent_hash, job_id, auth_proof, verification}
     ├── 409 INTENT_HASH_MISMATCH → Báo "HĐ vừa có cập nhật mới", tự tải lại preview
     ├── 422 GATE_DENIED          → Hiện danh sách gate_reasons[], chuyển trạng thái
     ├── 423 KILL_SWITCH_ACTIVE   → Banner đỏ "MoMo đang tạm khóa khẩn cấp"
     └── 200 OK (status = approved)
           ├── Mặc định: hiện lịch chi đề xuất (scheduled_for) + nút [Hủy lịch chi]
           └── Bật "Chi ngay": gọi POST /m/invoices/{id}:pay-now → chờ SSE payment.updated
                 ├── status = settled ──► Biên lai Xanh + mã giao dịch / thẻ ảo 1 lần
                 └── status = failed  ──► Cảnh báo Vàng (INSUFFICIENT_FUNDS / RAIL_DOWN),
                                          approval cũ thành superseded, cho duyệt lại
```

### 5.2. Bảng trạng thái UI cho `Escrow` (`F7`) và `Hard-Block` (`D5`, `D6`)

| Tình huống | Trạng thái `Invoice` / `Escrow` | Những gì UI hiển thị | Thao tác được phép trên UI |
|---|---|---|---|
| **Đỏ có thể gỡ bằng đổi TK (`BRD_02` Sữa 31tr)** | `invoice: blocked` (`PAYEE_CHANGE_REQUEST`) | Thẻ đỏ chỉ rõ xung đột giữa TK Zalo cá nhân (`998812345601`) và TK công ty đã lưu; hiện SĐT lưu sẵn `phone_on_file_masked`. | `Mở xác minh đổi TK (F12)` (gọi SĐT lưu sẵn → `record-callback` → `owner` step-up `:approve` → tự điều tra lại) hoặc `Từ chối`. |
| **Đỏ từ NCC mới / rủi ro (`BRD_04` Si-rô 8,8tr)** | `invoice: blocked` (`UNKNOWN_VENDOR`, `PERSONAL_ACCOUNT`, `TAX_RISK_LIST`, `HIDDEN_INSTRUCTION`) | Chặn chuyển thẳng; cảnh báo rủi ro mất khấu trừ VAT nếu trả TK cá nhân; mở nút sang luồng cọc an toàn. | `Đặt cọc tạm giữ (F7)`: nhập **TK công ty** đúng tên + MST (`target_status = escrow_only`; nhập TK cá nhân bị chặn `422 VALIDATION_FAILED`, `errors[].code = PERSONAL_ACCOUNT_NOT_ALLOWED`) → gắn `PO` → khóa cọc hoặc `Từ chối`. |
| **Đang giữ tiền cọc tạm giữ (`F7` giữa kỳ)** | `invoice: escrow_held`, `escrow: held` | Thanh tiến trình **3 bước của Cọc tạm giữ**: `[✓ 1. Đã khóa tiền tại NH đối tác]` → `[⏳ 2. Duyệt HĐ giao hàng (kênh escrow)]` → `[⏳ 3. Quản lý quán/bếp xác nhận Phiếu nhập kho (GRN)]` + ngày hết hạn `expires_on`. | Quản lý quán/bếp bấm `Xác nhận nhận đủ hàng (POST /m/goods-receipts)`; Chủ chuỗi bấm `Duyệt HĐ giao hàng` → đủ cả 2 thì Gate tự giải ngân (`released` / `paid`), quá hạn tự hoàn (`refunded`). |
| **Chặn cứng không thể gỡ (`SIMO` / Trùng HĐ)** | `invoice: blocked` (`OFFICIAL_FRAUD_LIST` hoặc `DUPLICATE_INVOICE`) | Khung khiên đỏ sẫm **"CHẶN CỨNG THEO DANH SÁCH CHÍNH THỨC / HÓA ĐƠN TRÙNG"** (với trùng HĐ có link mở `duplicate_of` gốc để đối chiếu). | **Chỉ duy nhất nút `Từ chối hóa đơn`** (ẩn mọi wizard F7/F12). |
| **Cảnh báo chéo sau khi đã duyệt (`D8`, `TRAP_02`)** | Đang `approved`/`scheduled` → tự lùi về `pending_approval` (`verification_required: true`) | Banner vàng cam đầu thẻ: *"Phê duyệt trước đó đã hết hiệu lực (`superseded`) do chỉ báo vừa bị gắn Cảnh báo chéo trên mạng lưới MoMo."* | Bắt buộc gọi `phone_on_file_masked` + ký duyệt lại có `verification`. |

---

## 6. Trạng thái Rỗng, Đang tải và Xử lý lỗi (`Empty / Loading / Error States`)

| Màn hình / Tình huống | Trạng thái | Thiết kế hiển thị cụ thể trên UI |
|---|---|---|
| **Hàng chờ duyệt (`M1`) trống** | `Empty` (`groups: []`) | Minh họa khiên xanh + dòng chữ: *"Không có hóa đơn vàng/đỏ nào chờ chị Lan quyết. Hôm nay đã tự động thanh toán X hóa đơn xanh (tổng Y đ) trong hạn mức an toàn."* + nút `Xem lịch sử đã chi`. |
| **Đang tải danh sách / chi tiết** | `Loading` | Dùng `Skeleton` đúng kích thước 5 dòng của `ApprovalCard` và dải 6 ô bot (tránh nhảy bố cục `CLS = 0`). |
| **Đang điều tra (`investigating`)** | `Streaming` | Khóa khu vực nút `Duyệt` bằng dải trạng thái `Đang chờ các bot bắt buộc hoàn tất kiểm tra...`, tự bung `LiveInvestigationView` ngay phía trên. |
| **Upload trùng đúng file (`200`) vs khác file cùng số HĐ (`409 DUPLICATE_INVOICE`)** | `Idempotent` / `Error 409` | • `200`: Toast thông tin *"File này đã có trên hệ thống — đang mở hóa đơn hiện có."*<br>• `409`: `Alert` đỏ kèm nút **`Mở hóa đơn gốc (existing_invoice_id)`** để so sánh vì sao cùng ký hiệu/số mà nội dung byte khác nhau. |
| **Upload XML hỏng cấu trúc (`422 XML_UNPARSEABLE`)** | `Error 422` | Báo rõ *"File XML không đúng chuẩn HĐĐT QĐ 1233/QĐ-CT hoặc khác đơn vị VND — hệ thống không lưu."* Gợi ý tải lại đúng bản gốc XML từ NCC. |
| **Upload PDF / ảnh (`NON_XML_SOURCE`)** | `Pending Input` | Hóa đơn có `total_vnd = null`; khóa nút Duyệt, hiện form gọn `Nhập số liệu kiểm tra từ PDF` (`PATCH /manual-fields`) và báo trước hóa đơn này luôn giữ mức ≥ 🟡 Vàng. |
| **Gate không phản hồi (`503 UPSTREAM_UNAVAILABLE`)** | `Fail-Closed` | Khóa cứng nút `Duyệt`, hiện hộp xám–đỏ: *"Không kết nối được Khóa an toàn Payment Gate (timeout 2s). Theo nguyên tắc an toàn fail-closed, tạm khóa duyệt chi."* + nút `Kiểm tra lại`. |
| **Hóa đơn đổi dữ liệu lúc đang mở modal (`409 INTENT_HASH_MISMATCH`)** | `Stale Preview` | Đóng hộp OTP, hiện thông báo *"Kết quả điều tra của hóa đơn vừa được cập nhật. Hệ thống đã tải lại bản mới nhất để bạn xem trước khi ký."* |
| **Mandate đang ở `review_only` (`409 INVALID_STATE`, `errors[].code = MANDATE_REVIEW_ONLY`)** | `Policy Info` | Ẩn/khóa nút `Duyệt chi qua PayMatch`, đổi nhãn thành *"Chế độ Chỉ đối soát: Chị tự chuyển khoản bên ngoài sau khi xem kết quả"* + link sang cài đặt `Mandate`. |
| **Vi phạm 2 người trên Console (`409 MAKER_CHECKER_VIOLATION`)** | `Error 409` | Trên `web-console`, nếu cùng `staff_id` vừa tạo đề xuất gỡ `KillSwitch` / `HardBlock` vừa bấm duyệt: khóa nút `Approve` ngay trên client kèm tooltip *"Cần Trưởng nhóm Rủi ro (RL) khác người đề xuất phê duyệt."* |
| **Thiếu mã ticket CSKH (`403 TICKET_REQUIRED`)** | `Guard` | Nút `Tra cứu bằng chứng` trên tab CSKH bị `disabled` cho tới khi ô `Mã Ticket khiếu nại` có giá trị (định dạng ticket chưa chốt trong [console-api.md §5](../05-api/console-api.md); FE chỉ chặn ô rỗng, để backend kiểm định dạng), ghi rõ *"Mọi lượt xem đều lưu nhật ký kiểm toán `access_log`."* |

---

## 7. Kịch bản Demo 3 phút (Khai thác tinh hoa từ 49 kịch bản `sim-world`)

> **Bối cảnh sân khấu:** 2 thành viên (1 người dẫn chuyện — **Speaker**, 1 người điều khiển chuột — **Driver**). Trước giờ lên sân khấu đã bấm `Reset Demo` (`POST /m/demo:reset`) để nạp sạch seed Chuỗi Lá Xanh (15 quán + 1 bếp trung tâm) và Chuỗi Bếp Phố Xanh (Tenant B).

| Mốc giờ | Kịch bản `sim-world` sử dụng | Thao tác của Driver trên màn hình | Lời dẫn ngắn gọn của Speaker & Điểm "Wow" chấm điểm |
|---|---|---|---|
| **0:00 – 0:25**<br>*(25s)*<br>**Mở màn & Tự chi êm** | `BRD_01_COFFEE_26M5` (🟢 26,5tr) + `BRD_05_POS_SOFTWARE_12M` (🟢 12tr thẻ ảo) | Mở **M1 Hàng chờ duyệt** của Chị Lan. Chỉ vào thanh KPI đầu ngày (`2 HĐ xanh 38,5tr đã tự chi`, `còn 3 HĐ vàng/đỏ cần xem`), mở nhanh 3 giây biên lai `BRD_05` cấp thẻ ảo 1 lần. | *"Chuỗi F&B 16 điểm nhận 550 hóa đơn/tháng. Với PayMatch trên MoMo Doanh Nghiệp, cà phê 26,5 triệu và phần mềm POS 12 triệu khớp 100% hợp đồng đã tự trả bằng lệnh chi 1-1 và thẻ ảo 1 lần. Chị Lan không tốn một giây nào cho hóa đơn đúng."* |
| **0:25 – 1:05**<br>*(40s)*<br>**Bắt đắt ngầm & Rò nước** | `BRD_03_CUPS_SHRINKFLATION` (🟡 22,4tr) + `BRD_06_WATER_STORE3_4M2` (🟡 4,21tr) | 1) Bấm vào thẻ 🟡 **Cốc nhựa 22,4tr**: chỉ ô Diff `1.000 → 800 cái/thùng (+21,74%/cái)` trên Thẻ duyệt 5 dòng → bấm `Từ chối` → hiện ngay **Mẫu yêu cầu HĐ điều chỉnh** → bấm `Sao chép`.<br>2) Lướt nhanh thẻ 🟡 **Nước Quán 3**: thấy biểu đồ `144 m³ (6× trung vị 24 m³)` trong khi doanh thu QR MoMo đi ngang. | *"Cái khó bắt nhất là ăn gian quy cách: giá thùng gồm VAT giảm nhẹ từ 575k xuống 560k, nhưng rút ruột từ 1.000 xuống 800 cái — đắt hơn 21,7%! Bot Thu mua đọc quy cách, code tính đơn giá từng cái, bấm Từ chối có sẵn công văn đòi điều chỉnh. Cạnh đó, tiền nước Quán 3 vọt gấp 6 lần dù doanh thu QR MoMo không tăng — báo ngay nghi rò ống nước!"* |
| **1:05 – 2:00**<br>*(55s)*<br>**Live 6 Bot & Chặn Prompt Injection + Đổi TK** | `BRD_04_SYRUP_NEW_VENDOR_FRAUD` (🔴 8,8tr, `PI_01`/`PI_03`) + nhắc nhanh `BRD_02_MILK_31M_ZALO_PAYEE` (🔴 31tr) | Từ `Demo Toolbar (Alt+D)`, bắn trực tiếp kịch bản **`BRD_04` Si-rô NCC mới** (hoặc mở lại live replay `15s`) → mở **M2.1 Sơ đồ 6 Bot SSE** đang chạy song song → nhảy ra kết quả **🔴 ĐÃ CHẶN CỨNG**. Bấm chip `[🛡️ Xem câu lệnh giấu TTKhac]` làm sáng dòng lệnh lừa AI trong XML; chỉ vào nút `Duyệt` đã biến mất, chỉ mở hướng `Cọc tạm giữ (F7)` vào TK công ty. | *"Xem 6 kế toán AI làm việc trực tiếp khi hóa đơn si-rô mới vừa rơi vào hộp thư! Kẻ gian vừa đòi cọc vào TK cá nhân, vừa nhét câu lệnh giấu ngay trong thẻ `<TTKhac>` của XML bảo AI bỏ qua kiểm tra và chấm Xanh. Vô ích: Kế toán trưởng không đọc chữ bẩn, `fraud-control` bắt sống `HIDDEN_INSTRUCTION`, `tax` phát hiện DN rủi ro thuế, và `Payment Gate` bằng code khóa cứng — không có nút duyệt đè!"* |
| **2:00 – 2:45**<br>*(45s)*<br>**Cao trào Bẫy cuối trên toàn mạng MoMo** | `TRAP_01_CARD_MISUSE` + `TRAP_02_CROSS_ALERT_TENANT_B` (`F3`, `F8`) | Chuyển sang chế độ **Split-Screen**: Trái = **MoMo Risk Console (`C1`)**, Phải = **App Chuỗi B — Bếp Phố Xanh**. 1) Bấm nút giả lập kẻ gian quẹt trộm thẻ ảo POS ở merchant lạ (`TRAP_01`) → bị từ chối, nảy cảnh báo trên Console. 2) Chuyên viên MoMo chọn cảnh báo người bán si-rô BRD_04 (`0999090001`) → bấm **`Phát cảnh báo chéo`** theo indicator SĐT `0900***001`. Ngay lập tức bên phải (Chuỗi B), hóa đơn si-rô của NCC `0999090013` (công ty khác, giấy tờ sạch, nhưng dùng chung SĐT với người bán BRD_04) tự nhảy sang **🟡 `CROSS_ALERT_HIT` — Bắt buộc gọi xác minh SĐT lưu sẵn**! | *"Và đây là lý do PayMatch phải nằm trên MoMo: kẻ gian lấy số thẻ ảo quẹt ở nơi khác lập tức bị từ chối. Khi chuyên viên rủi ro MoMo bấm Cảnh báo chéo cho người bán si-rô lừa đảo, ngay cả công ty bình phong khác tên, khác MST nhưng chung số điện thoại cũng bị lộ: mọi cửa hàng khác trên mạng lưới như Chuỗi Bếp Phố Xanh được thu hồi lệnh duyệt cũ và buộc xác minh lại trước khi tiền kịp rời ví!"* |
| **2:45 – 3:00**<br>*(15s)*<br>**Chốt hạ quy mô & an toàn** | *(Tổng kết trên màn hình)* | Quay lại màn hình chính sạch gọn, mở nhanh ngăn `Mandate` (`30tr/HĐ · 50tr/ngày`) + câu khẩu hiệu. | *"AI đọc và điều tra; con người chỉ quyết vài ca lạ; khóa an toàn bằng code mới được chi tiền. PayMatch — Khớp rồi mới chi!"* |

> **Kịch bản dự phòng hỏi–đáp giám khảo (Q&A 1 chạm từ `Demo Toolbar`):**
> - Giám khảo hỏi *"Nếu cả ngày có 20 hóa đơn vượt trần 50 triệu/ngày thì bấm từng cái à?"* → Bắn `EDGE_BULK_OVER_DAILY`, mở `BulkApprovalDrawer` ký 1 lần cho lô hợp lệ.
> - Giám khảo hỏi *"Kẻ gian tráo STK trong mã QR của XML thì sao?"* → Bắn `SCAM_TK_IN_DLQRCODE`, chỉ rõ PayMatch trích cả `DLQRCode` vào vùng `untrusted` và chỉ trả tiền vào `vendor_registry`.
> - Giám khảo hỏi *"Muốn khóa khẩn cấp cả mạng lưới thì sao?"* → Qua tab `Kill Switch` trên Console bật `auto_pay_global` (1 người bật, 2 người gỡ).

---

## 8. Đề xuất bổ sung Hợp đồng API (`Contract Gaps` — KHÔNG sửa `contracts/` trong bước này)

Theo đúng quy tắc *Contract-first* trong `AGENTS.md`, dưới đây là danh sách đầy đủ mọi điểm mà giao diện v1 cần nhưng **chưa có trong `contracts/` hiện hành**, chia làm 2 nhóm để đội thống nhất trước khi sửa `contracts/` và chạy `make contracts`.

### 8.1. Nhóm A — Khoảng trống giữa `contracts/` hiện tại (slice v0.1.0) và đặc tả `docs/05-api/*.md` (v0.2)

| # | Thiếu trong `contracts/` hiện tại | Đã có đặc tả chữ tại | Màn hình bị ảnh hưởng nếu chưa thêm vào `contracts/` | Mức ưu tiên cho Demo 03/12 |
|---:|---|---|---|---|
| **A1** | Chưa có file **`contracts/openapi/core-console.yaml`** | [console-api.md](../05-api/console-api.md) §1–§6 | Toàn bộ `web-console`: danh sách `alerts`, phát `cross-alerts` (`TRAP_02`), bật/gỡ `kill-switches`, tra `evidence` CSKH không chạy được Prism mock và chưa sinh được type. | **P0 (Bắt buộc cho Bẫy cuối)** |
| **A2** | Thiếu **`POST /m/invoices/{invoice_id}:pay-now`**, `:schedule`, `:cancel-payment`, `:reinvestigate` trong `core-merchant.yaml` | [merchant-api.md](../05-api/merchant-api.md) §2 | Sau khi chủ chuỗi bấm `Duyệt` trên demo, không kích hoạt được lệnh **Chi ngay (`:pay-now`)** để thấy `Payment Gate` chuyển sang `paid` ngay trên sân khấu mà phải tua đồng hồ. | **P0 (Bắt buộc)** |
| **A3** | Thiếu **`GET /m/invoices/{invoice_id}/document`** và **`GET /m/invoices/{invoice_id}/jobs`** trong `core-merchant.yaml` | [merchant-api.md](../05-api/merchant-api.md) §2 | Tab xem file XML/PDF gốc (kèm header `Digest: sha-256=...`) và tra `job_id` của hóa đơn đang `investigating` để nối SSE. | **P0 (Bắt buộc)** |
| **A4** | Thiếu **`GET /m/summaries/daily`** và **`GET /m/wallet`** trong `core-merchant.yaml` | [merchant-api.md](../05-api/merchant-api.md) §4, §7 | Thanh KPI đầu ngày trên `M1` (*"Đã tự chi X HĐ · Số dư ví 350.000.000 đ"*) không có nguồn dữ liệu tổng hợp. | **P1 (Rất nên có)** |
| **A5** | Thiếu nhóm **Duyệt hàng loạt** (`POST /m/approval-batches:preview`, `POST /m/approval-batches`, `GET /m/approval-batches/{id}`) | [merchant-api.md](../05-api/merchant-api.md) §4 | Màn hình `M6 BulkApprovalDrawer` (chứng minh khả năng xử lý 550 HĐ/tháng và ca `EDGE_BULK_OVER_DAILY`). | **P1 (Rất nên có)** |
| **A6** | Thiếu nhóm **Gỡ khóa Đỏ `F12` & `F7`** (`/m/vendors*`, `/m/vendor-verifications*`, `/m/purchase-orders*`, `/m/goods-receipts*`, `/m/escrows*`, `GET /m/stores`) | [merchant-api.md](../05-api/merchant-api.md) §6–§8 | Nếu demo chỉ dừng ở bước "Chặn đỏ" thì chưa cần; nếu muốn bấm trọn vẹn wizard tạo `Escrow` (`BRD_04`) hoặc `record-callback` (`BRD_02`) thì phải thêm. | **P1 (Nên có)** |
| **A7** | Thiếu nhóm **Hỏi đáp trợ lý & Mandate** (`/m/conversations*`, `/m/reports*`, `/m/mandate*`, `/m/platform-limits`, `/m/auto-pay-suspensions*`, `POST /m/notifications/{id}:read`) | [merchant-api.md](../05-api/merchant-api.md) §3a, §5, §10 | Ngăn kéo Hỏi đáp Kế toán trưởng (`M10`) và trang cấu hình Mandate (`M8`) thuộc phạm vi v1 ([problem-definition.md §6c](../01-requirements/problem-definition.md#6c-phạm-vi-v1-trước-03122026)). | **P1 (Trong v1)** |
| **A8** | `contracts/events/` mới chỉ có `.gitkeep` (chưa có `*.schema.json`) | [events.md](../05-api/events.md) §1–§2 | Chưa validate tự động schema sự kiện outbox/SSE ở tầng contract test. | **P2** |

### 8.2. Nhóm B — Đề xuất bổ sung trường / endpoint mới (Chưa có trong cả `docs/05-api/` lẫn `contracts/`)

| # | Vấn đề thực tế khi dựng UI trên schema hiện tại | Tệp bị ảnh hưởng (nếu đội chốt) | Đề xuất cụ thể (nhỏ nhất, giữ nguyên bất biến kiến trúc) |
|---:|---|---|---|
| **B1** | **Không biết `job_id` để mở SSE khi hóa đơn về từ hộp thư/`scenario`:** Khi `/sim/scenario/invoices:send` đẩy HĐ mới, client chỉ nhận SSE `invoice.status_changed {invoice_id, to: "investigating"}`; gọi `GET /m/invoices/{id}` lúc đang chạy thì `brief = null` nên không có `brief.job_id`. | `invoice-summary.schema.json`, `core-merchant.yaml` (`TenantSseEventData`) | Thêm **`latest_job_id: string \| null`** vào `InvoiceSummary` (và vào payload SSE `invoice.status_changed`) để frontend nối ngay `GET /m/jobs/{latest_job_id}/events` trong 0 lượt gọi phụ. |
| **B2** | **Thiếu dữ liệu gốc `trusted` để vẽ ô Diff Hợp đồng & Biểu đồ Điện nước 12 tháng:** `Finding.evidence` trả `ref_id` dạng `itm_...`, `urd_...`, nhưng `merchant-api` không có endpoint nào đọc `utility_reading` 12 tháng hay `momo_revenue` của quán để vẽ biểu đồ rò nước Quán 3 (`144 m³` vs `24 m³`), và nếu chỉ đọc `Finding.reason` thì vi phạm nguyên tắc không tin số trong `UntrustedText`. | `merchant-api.md` §2, `schemas.md` §2–§3 | Thêm trường tùy chọn **`comparison_context` (`trusted`, do code đóng gói)** trên `GET /m/invoices/{id}` (hoặc endpoint `GET /m/invoices/{id}/evidence-context`) gồm: `matched_contract_items[]` (`pack_qty`, `unit_price`, `computed_base_unit_price`), `three_way_summary` (`po_qty`, `grn_qty`, `invoice_qty`), và `utility_context` (`median_12m_usage`, `monthly_series: [{month, usage, amount_vnd, revenue_vnd}]`). |
| **B3** | **Thiếu thông tin thẻ ảo & mã giao dịch trong `Invoice.payment` cho `BRD_05` & `TRAP_01`:** `invoice.schema.json` hiện chỉ có `payment: {payment_intent_id, status, channel, settled_at}` — thiếu `rail_txn_id`, `transfer_memo`, `failure_code` và đặc biệt thiếu `card_id` / `last4` để demo cảnh quẹt trộm thẻ ảo `TRAP_01_CARD_MISUSE`. | `invoice.schema.json`, `schemas.md` §2 | Mở rộng `Invoice.payment` thêm: `rail_txn_id: string \| null`, `transfer_memo: string \| null`, `failure_code: string \| null`, `virtual_card: {card_id: string, last4: string} \| null`. |
| **B4** | **Thiếu tên hiển thị ở danh sách khi `vendor_id = null` (`BRD_04`):** Trong `InvoiceSummary`, `vendor_name` là `null` với NCC mới; chú thích trong `schemas.md` bảo *"UI hiện `untrusted.seller_name`"*, nhưng `InvoiceSummary` **không có** trường `untrusted.seller_name` (chỉ `Invoice` chi tiết mới có). | `invoice-summary.schema.json`, `schemas.md` §2 | Thêm **`untrusted_seller_name: UntrustedText \| null`** vào `InvoiceSummary` để dòng danh sách hiện được tên người bán trên XML kèm badge `[Chưa xác minh]`. |
| **B5** | **Thiếu `store_name` trên `InvoiceSummary`:** Danh sách hóa đơn của chuỗi 16 điểm chỉ có `store_id: "sto_01M88..."`, gây bất tiện khi `GET /m/stores` chưa nằm trong slice đầu hoặc khi render nhanh thẻ thông báo. | `invoice-summary.schema.json`, `schemas.md` §2 | Thêm **`store_name: string \| null`** (`trusted`, lấy từ bảng `stores`) vào `InvoiceSummary`, đồng thời đưa `GET /m/stores` vào `core-merchant.yaml`. |
| **B6** | **Thiếu `phone_on_file_masked` trên thẻ khóa Đỏ `PAYEE_CHANGE_REQUEST` (`BRD_02`):** `ApprovalPreview.phone_on_file_masked` hiện chỉ khác `null` khi `verification_required = true` (`CROSS_ALERT_HIT`), trong khi `BRD_02` bị khóa đỏ (`verification_required = false`) lại rất cần hiện ngay SĐT lưu sẵn trên hợp đồng để nhắc chủ chuỗi gọi kiểm tra. | `approval-preview.schema.json`, `schemas.md` §4 | Cho phép `ApprovalPreview.phone_on_file_masked` trả giá trị từ `vendor_registry` bất cứ khi nào hóa đơn có `vendor_id != null` và dính mã `CROSS_ALERT_HIT`, `PAYEE_CHANGE_REQUEST` hoặc `PERSONAL_ACCOUNT`. |
| **B7** | **Thiếu vị trí thẻ XML/QR nơi trích xuất STK lạ (`SCAM_TK_IN_TTKHAC`, `SCAM_TK_IN_DLQRCODE`):** `Invoice.untrusted.seller_bank_account` chỉ có `{number, bank_name}` mà chưa cho biết nó nằm ở `NBan/STKNHang`, `TTKhac` hay ẩn trong `DLQRCode`. | `invoice.schema.json`, `schemas.md` §2 | Thêm **`origin_path: UntrustedText \| string`** (ví dụ `"NBan/TTKhac/SellerBankAccount"` hoặc `"DLQRCode[38]"`) vào `Invoice.untrusted.seller_bank_account` để UI tô sáng đúng vị trí gài bẫy. |
| **B8** | **Chưa có SSE cho `web-console` khi trình diễn song song 2 màn hình:** `console-api.md` chưa có endpoint stream sự kiện cho cảnh báo mới (`TRAP_01` thẻ ảo bị quẹt sai hoặc `BRD_04` đẩy `indicator.flagged`). | `console-api.md`, `events.md` | Ngắn hạn cho v1: quy ước `web-console` dùng `TanStack Query` `refetchInterval: 2000` trên `GET /console/alerts` khi mở màn hình demo; hoặc thêm `GET /console/events` (SSE cho `alert.created`, `cross_alert.published`, `kill_switch.engaged`). |
