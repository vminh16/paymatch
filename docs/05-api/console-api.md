# Console API (`/console/*`, cổng 8002)

Trạng thái: **v0.2 (26/11/2026)**, đã sửa theo review. File OpenAPI: `contracts/openapi/core-console.yaml`. Chỉ mở trong mạng nội bộ MoMo.

Mọi endpoint cần `Authorization: Bearer <staff_jwt>`. Vai nhân viên (`staff_roles`): **RA** = `risk_analyst`, **RL** = `risk_lead`, **CS** = `support_agent`, **PA** = `platform_admin`. Console **không có endpoint nào đọc danh sách hóa đơn của tenant**; chỉ tra bằng chứng theo ticket (§5).

Maker-checker: hành động có cột "Checker" cần người thứ hai có vai RL và `checker ≠ maker`; vi phạm → `409 MAKER_CHECKER_VIOLATION`.

## 1. Phiên

| Method | Path | Vai | Kết quả |
|---|---|---|---|
| POST | `/console/auth/session` | — | `{sso_token}` → `{staff_jwt, expires_at, staff: {staff_id, name, roles}}` (demo: token từ `POST /sim/identity/staff-tokens`) |
| GET | `/console/me` | mọi vai | thông tin nhân viên |

## 2. Cảnh báo và case

| Method | Path | Vai | Body → Kết quả |
|---|---|---|---|
| GET | `/console/alerts` | RA RL | lọc `status`, `source`, `reason_code`, `created_from` → trang `Alert`, sắp theo thời gian (v1) |
| GET | `/console/alerts/{alert_id}` | RA RL | `Alert` + `indicators: [Indicator]` + `occurrences: [{tenant_ref, at, reason_codes}]` (`tenant_ref` là mã ẩn danh, không phải tên cửa hàng) |
| POST | `/console/alerts/{alert_id}:assign` | RA RL | `{assignee_staff_id}` |
| POST | `/console/alerts/{alert_id}:dismiss` | RA RL | `{note}` |
| POST | `/console/cases` | RA RL | `{alert_ids, summary}` → `201 Case` |
| GET | `/console/cases` | RA RL | lọc `status` |
| GET | `/console/cases/{case_id}` | RA RL | `Case` + `actions: [CaseAction]` |
| POST | `/console/cases/{case_id}/actions` | RA RL | `{type: note \| propose_hard_block \| propose_cross_alert_withdrawal, payload}` → `201 CaseAction (proposed; note = applied ngay)` |
| POST | `/console/case-actions/{action_id}:approve` | RL (Checker) | → `CaseAction (applied)` |
| POST | `/console/case-actions/{action_id}:reject` | RL (Checker) | `{note}` |
| POST | `/console/cases/{case_id}:close` | RA RL | `{note}` |

`propose_hard_block` (`payload {indicator_ids, list_ref}`) chỉ hợp lệ khi indicator có trong danh sách chính thức (core tra `GET /sim/simo/indicators:check`); không có → `422 VALIDATION_FAILED code=NOT_ON_OFFICIAL_LIST` (D6). Áp dụng → ghi `risk.hard_blocks` (Gate đọc) và phát `hard_block.applied`.

## 3. Cảnh báo chéo (F3)

| Method | Path | Vai | Body → Kết quả |
|---|---|---|---|
| POST | `/console/cross-alerts` | RA RL (1 người) | `{alert_id, indicator_ids, reason_codes, note}` → `201 CrossAlert (published)`. Phát `cross_alert.published` |
| GET | `/console/cross-alerts` | RA RL | lọc `status` |
| GET | `/console/cross-alerts/{cross_alert_id}` | RA RL | `CrossAlert` + `affected_invoice_count` (số lượng, không có id hóa đơn) |

Gỡ cảnh báo chéo (nới lỏng) đi qua case action `propose_cross_alert_withdrawal` + Checker; khi áp dụng phát `cross_alert.withdrawn`.

## 4. Kill switch (F4)

| Method | Path | Vai | Body → Kết quả |
|---|---|---|---|
| POST | `/console/kill-switches` | RA RL (1 người) | `{scope: KillSwitchScope, target_id, reason}` → `201 KillSwitch (engaged)`. Có hiệu lực ngay: Gate đọc ở mỗi lần đánh giá; core không cấp token cho bot/tool bị tắt ở phiên mới và chặn ở mỗi lần gọi tool |
| GET | `/console/kill-switches` | mọi vai | lọc `status`, `scope` |
| POST | `/console/kill-switches/{kill_switch_id}/release-requests` | RA RL (Maker) | `{reason}` → `201 KillSwitchReleaseRequest (proposed)` |
| POST | `/console/kill-switch-release-requests/{request_id}:approve` | RL (Checker) | → `KillSwitch (released)`, phát `kill_switch.released` |
| POST | `/console/kill-switch-release-requests/{request_id}:reject` | RL (Checker) | `{note}` |

`target_id`: `indicator_id` · `tenant_id` · `bot_id` · `tool_id` · `null` khi `auto_pay_global`.

## 5. Tra bằng chứng cho CSKH (F6)

Mọi endpoint ở đây bắt buộc header `X-Ticket-Id`; thiếu → `403 TICKET_REQUIRED`. v1 không nối hệ thống CSKH: chỉ kiểm định dạng mã ticket và ghi `access_log`. Mỗi lần gọi ghi một dòng `access_log` (ai, ticket, tài nguyên, lúc nào), kể cả khi lỗi.

| Method | Path | Vai | Kết quả |
|---|---|---|---|
| GET | `/console/evidence` | CS RL | đúng **một** trong: `?payment_intent_id=`, `?rail_txn_id=`, `?invoice_ref=<MST bán>:<ký hiệu>:<số>` → `EvidenceChain` (PII che) |
| GET | `/console/evidence/documents/{document_id}` | CS RL | bản **đã che** của file gốc (số TK, SĐT, CCCD, email thay bằng `***`) kèm `sha256` của bản gốc để đối chiếu. Chỉ khi `document_id` nằm trong một `EvidenceChain` đã tra với cùng ticket trong 1 giờ. Xem bản không che: lộ trình (break-glass) |
| GET | `/console/access-log` | RL PA | lọc `staff_id`, `ticket_id`, `from`, `to` |

## 6. Nền tảng

| Method | Path | Vai | Body → Kết quả |
|---|---|---|---|
| GET | `/console/tenants` | PA RL | trang `{tenant_id, name, created_at, mandate_mode}` |
| GET | `/console/tools` | PA | `[ToolDefinition]` + `granted_tenant_count` |
| GET | `/console/tool-grants` | PA | lọc `tenant_id`, `tool_id` |
| POST | `/console/tool-grants` | PA | `{tenant_id, tool_id}` → `201` |
| POST | `/console/tool-grants/{grant_id}:revoke` | PA | `{reason}` → grant `revoked` (không xóa cứng). Bot tenant đang dùng tool → bot `disabled` |
| GET | `/console/bots` | PA | bot hệ thống + thống kê bot tenant theo template |
| GET | `/console/bots/{bot_id}/metrics` | PA | `{window_days, jobs, findings_by_severity, timeout_rate, invalid_output_rate, false_alarm_rate \| null}` |
| GET | `/console/model-configs` | PA | `[{purpose: bot \| brief, primary_model, fallback_model, max_tokens, timeout_s}]` |
| PATCH | `/console/model-configs/{purpose}` | PA | merge patch, `If-Match` bắt buộc |
| GET | `/console/policies` | mọi vai | `PlatformLimits` + kill switch đang bật |
| GET | `/console/jobs/{job_id}/trace` | PA RL | `{trace_id, spans: [{name, bot_id, tool_id, started_at, duration_ms, status}], tool_calls: [{tool_call_id, tool_id, provenance}]}` (không có nội dung dữ liệu) |

Sửa trần nền tảng (`PlatformLimits`) không có trong v1: giá trị nạp từ seed.
