# Schema dùng chung

Trạng thái: **v0.2 (26/11/2026)**, đã sửa theo review. Mỗi mục ở đây thành một file `contracts/schemas/<name>.schema.json` (JSON Schema 2020-12); OpenAPI tham chiếu bằng `$ref`. Ký hiệu: `?` = có thể vắng, `| null` = có thể null.

## 1. Kiểu nền

```yaml
MoneyVnd: integer            # đồng, 0 <= x <= 9007199254740991 (2^53 - 1, safe integer cho JSON/JS/JCS)
SignedMoneyVnd: integer      # đồng, -9007199254740991 <= x <= 9007199254740991 (chỉ dùng cho hóa đơn điều chỉnh TCHDon 2/4)
Decimal: string              # pattern ^-?\d{1,15}(\.\d{1,6})?$; parser cắt chữ số 0 thừa cuối phần thập phân (vd 0.000000000 → "0") trước khi kiểm mẫu; chữ số khác 0 sau vị trí thứ 6 được giữ nguyên ở parser domain (không tự làm tròn/cắt) và sẽ không khớp mẫu này ở tầng schema/API
Timestamp: string            # RFC 3339, có offset
LocalDate: string            # YYYY-MM-DD, giờ Việt Nam
Severity: green | yellow | red
Provenance: trusted | untrusted
Channel: bank_transfer | virtual_card | escrow
InvoiceType: goods | utility | software      # mở rộng được; bot manifest chỉ dùng giá trị đã đăng ký
ReasonCode: string           # UPPER_SNAKE_CASE, danh mục ở agent-runtime.md §5a; GET /m/reason-codes trả bảng hiện hành

UntrustedText:               # mọi chữ do người bán viết hoặc do LLM viết sau khi đọc dữ liệu bẩn
  text: string
  provenance: untrusted      # hằng số; frontend escape, không render HTML/Markdown
  source: invoice_xml | email_body | chat_message | bot_reason | ocr
```

Quy tắc: **không có trường số tiền nào được đọc từ `UntrustedText`**. Số TK ngân hàng xuất hiện trong chữ hoặc trong XML (`NBan/STKNHang`, `TTKhac` chứa STK người bán, hoặc trường thanh toán của `DLQRCode`) chỉ nằm trong `untrusted` và chỉ để so sánh.

## 2. Hóa đơn

```yaml
InvoiceStatus: new | investigating | auto_pay_eligible | pending_approval | blocked | approved
             | scheduled | paying | paid | payment_failed | escrow_held | rejected

InvoiceSource: email | upload | bill_pay | scenario

InvoiceSummary:                       # dòng trong danh sách, hàng chờ
  invoice_id, store_id | null, vendor_id | null
  vendor_name: string | null          # CHỈ từ vendor registry; null khi NCC chưa có (UI hiện untrusted.seller_name)
  seller_tax_id: string
  symbol: string                      # KHMSHDon + KHHDon, ví dụ "1C26TAA"
  number: string                      # SHDon
  issued_on: LocalDate | null         # null với PDF/ảnh chưa nhập tay
  invoice_type: InvoiceType
  total_vnd: SignedMoneyVnd | null    # null với PDF/ảnh chưa nhập tay; chưa có thì không duyệt được; có thể âm ở HĐ điều chỉnh (TCHDon 2/4)
  status: InvoiceStatus
  severity: Severity | null           # null khi chưa điều tra xong
  reason_codes: [ReasonCode]
  verification_required: boolean     # có CROSS_ALERT_HIT
  due_on: LocalDate | null
  scheduled_for: LocalDate | null
  updated_at: Timestamp

Invoice: InvoiceSummary +
  source: InvoiceSource
  duplicate_of: string | null         # file khác sha256 trùng khóa qua email/bill_pay/scenario (lưu kèm Finding đỏ DUPLICATE_INVOICE; upload trùng trả 409 không lưu)
  manual_fields: {entered_by, entered_at} | null   # có khi số liệu được nhập tay (PDF/ảnh, NON_XML_SOURCE)
  document: {document_id, format: xml | pdf | image, sha256, received_at}
  buyer_tax_id: string
  currency: VND                       # v1 chỉ nhận VND; khác → XML_UNPARSEABLE
  subtotal_vnd, vat_total_vnd, total_vnd: SignedMoneyVnd | null   # TgTCThue, TgTThue, TgTTTBSo; null với PDF/ảnh chưa nhập tay; có thể âm ở HĐ điều chỉnh
  vat_breakdown: [{vat_rate: string, taxable_vnd: SignedMoneyVnd, vat_vnd: SignedMoneyVnd}]   # LTSuat; vat_rate theo PL V: "8%", "KCT"...
  tax_authority_code: string | null   # MCCQT
  einvoice_provider_tax_id: string | null   # MSTTCGP
  related_invoice: {relation: replace | adjust | replace_multiple | adjust_multiple | trade_discount, symbol, number, issued_on} | null   # TTHDLQuan (TCHDon 1..5)
  lines: [InvoiceLine]
  untrusted:                          # tách khỏi phần số
    seller_name: UntrustedText        # NBan/Ten (đối chiếu registry riêng)
    seller_address: UntrustedText
    seller_bank_account: {number: string, bank_name: string} | null   # trích từ NBan/STKNHang+TNHang, TTKhac chứa STK người bán, hoặc DLQRCode — KHÔNG BAO GIỜ là payee
    payment_terms: UntrustedText | null        # HTTToan
    other_info: [{field: string, value: UntrustedText}]   # mọi TTKhac
    messages: [{message_id, channel: email | chat, received_at, body: UntrustedText}]   # thân email kèm theo
  brief: Brief | null
  findings_summary: [{bot_id, severity, reason_codes}]
  approval: ApprovalSummary | null
  payment: {payment_intent_id, status: PaymentIntentStatus, channel, settled_at | null} | null
  escrow: {escrow_id, status: EscrowStatus} | null
  allowed_actions: [approve | reject | schedule | pay_now | cancel_payment | reinvestigate | enter_manual_fields | create_escrow | open_account_change]   # do core tính theo trạng thái + vai
  etag: string

InvoiceLine:
  line_id, position: integer          # STT
  kind: goods_service | promotion | trade_discount | note | special_goods   # TChat 1..5
  item_code: UntrustedText | null     # MHHDVu
  name: UntrustedText                 # THHDVu
  unit: UntrustedText | null          # DVTinh
  quantity: Decimal | null            # SLuong
  unit_price: Decimal | null          # DGia
  discount_vnd: SignedMoneyVnd | null # STCKhau
  amount_vnd: SignedMoneyVnd | null   # ThTien (null khi kind = note; có thể âm ở HĐ điều chỉnh)
  vat_rate: string | null             # TSuat
  arithmetic_ok: boolean              # code kiểm quantity × unit_price − discount = amount
```

## 3. Điều tra

```yaml
JobStatus: queued | running | completed | failed
TaskType: investigate_invoice | question | report
Job:
  job_id, task_type: TaskType, tenant_id
  subject: {invoice_id} | {conversation_id, message_id} | {report_id}
  status: JobStatus
  attempt: integer
  bots_called: [{bot_id, bot_version, times: integer}]
  bot_states: [{bot_id, state: pending | running | done | failed | timeout, severity | null}]
  created_at, started_at | null, completed_at | null

Finding:
  finding_id, job_id, attempt, bot_id, bot_version, skill_version, prompt_hash
  severity: Severity                  # sau khi core áp mức sàn/trần (severity_reported giữ giá trị bot gửi)
  severity_reported: Severity
  reason_codes: [ReasonCode]          # ít nhất 1; "OK" khi xanh
  reason: UntrustedText               # source = bot_reason
  evidence: [EvidenceRef]
  provenance: Provenance              # nhãn của dữ liệu dẫn tới kết luận; có untrusted nào → untrusted
  proposed_channel: Channel | null    # chỉ treasury
  proposed_pay_on: LocalDate | null   # chỉ treasury
  created_at

EvidenceRef:                          # core kiểm: ref_id đúng mẫu id và xuất hiện trong output của tool_call_id
  kind: invoice_line | invoice_document | message | contract_item | purchase_order | goods_receipt
      | tool_call | vendor_account | utility_reading
  ref_id: string                      # pattern ^(lin|doc|msg|itm|po|grn|tcl|vac|urd)_[0-9A-HJKMNP-TV-Z]{26}$
  tool_call_id: string                # bắt buộc; tool_call cùng job, attempt, bot

FindingSubmission:                    # agent-runtime gửi; core tự điền finding_id, severity (sau sàn), created_at
  bot_id, bot_version, skill_version, prompt_hash
  severity_reported: Severity
  reason_codes, reason: string, evidence, provenance, proposed_channel?, proposed_pay_on?

FindingForSupervisor: {finding_id, bot_id, severity, reason_codes, evidence}   # bản gửi lại cho điều phối: không có reason, không có chữ
FactKey: string              # enum do registry sở hữu (contracts/schemas/fact-key.schema.json), ánh xạ các chỉ số/mã từ tools.md và agent-roster.md
BotAnswer: {bot_id, facts: [{key: FactKey, value: string | number, tool_call_id, verified: boolean}], reason_codes}   # value chuỗi chỉ chấp nhận từ trường output có provenance = trusted

Brief:                                # tờ trình 5 dòng của chief-accountant
  brief_id, job_id
  lines: [UntrustedText]              # tối đa 5 dòng × 200 ký tự; LLM viết nên vẫn là untrusted khi hiển thị
  cited_evidence: [EvidenceRef]
  model: string, prompt_hash: string
```

## 4. Duyệt và chi

```yaml
ApprovalMethod: single | bulk | mandate

# Cách tính hash (core, Gate, client dùng chung gói chuẩn `paymatch_hashing` ở packages/paymatch-hashing;
#   vector kiểm thử chuẩn tại contracts/test-vectors/hashing.json)
#   canonical = JSON Canonicalization Scheme (RFC 8785, không dùng số thực float, từ chối mọi số nguyên ngoài
#               khoảng safe integer [-9007199254740991, 9007199254740991]); hash = sha256 UTF-8, hex chữ thường
#   chuẩn hóa Timestamp trong payload băm: mọi trường Timestamp đem băm phải đổi về UTC dạng
#               `YYYY-MM-DDTHH:MM:SSZ` (bỏ phần thập phân giây) trước khi JCS/SHA-256 (vd `+07:00`, `+00:00`, `Z`, `.000Z`
#               biểu diễn cùng giây UTC cho cùng một hash)
#   intent_hash (hóa đơn) = H({"v":1,"kind":"invoice","invoice_id","document_sha256","payee_account_id","amount_vnd","channel"})
#                           (payee_account_id = null chỉ khi Gate DENY và NCC chưa có TK trong registry)
#   intent_hash (cọc)     = H({"v":1,"kind":"escrow","purchase_order_id","payee_account_id","amount_vnd","channel":"escrow"})
#   payload_hash (duyệt)  = H({"intent_hash", "verification": Verification | null})
#                           (khi verification != null, đối tượng luôn đủ 4 khóa {"called_phone_on_file","result","note","at"};
#                            nếu vắng note thì chuẩn hóa thành "note": null; trường `at` được chuẩn hóa về UTC
#                            `YYYY-MM-DDTHH:MM:SSZ` (bỏ phần thập phân giây) trước khi băm; approval-preview tính sẵn
#                            với verification = null, còn khi có verification thì client/core tính lại với Verification đã nhập)
#   payload_hash (batch)  = H({"preview_id", "items": [[invoice_id, intent_hash], …] sắp tăng dần theo invoice_id (UTF-16 code unit)})
#   action_hash           = H({"v":1,"action","resource_id","payload_hash"})
#                           (action snake_case: approve_invoice | approve_batch | create_escrow | sign_mandate
#                            | create_vendor | change_vendor_phone | approve_vendor_verification
#                            | activate_vendor_contract | lift_auto_pay_suspension | approve_bot)

ApprovalPreview:                      # GET /m/invoices/{id}/approval-preview
  invoice_id
  job_id: string                      # job điều tra mà người duyệt đang xem
  intent_hash: string                 # xem "Cách tính hash" dưới
  payee: {vendor_account_id, bank_name: string | null, account_number_masked: string | null, merchant_id: string | null, account_name} | null   # từ registry, không từ hóa đơn; null chỉ khi gate_decision = DENY và chưa có TK trong registry; merchant_id có khi kind = card_merchant
  amount_vnd: MoneyVnd                # = invoice.total_vnd (D3)
  channel: Channel
  gate_decision: ALLOW | REQUIRE_APPROVAL | DENY
  allowed_methods: [single | bulk]
  verification_required: boolean
  phone_on_file_masked: string | null # chỉ khác null khi verification_required = true; SĐT lấy từ registry
  gate_reasons: [GateReason]
  action_hash: string                 # đưa vào step-up challenge
  expires_at: Timestamp               # 5 phút; sau đó xem trước lại

Verification:                         # bắt buộc khi verification_required
  called_phone_on_file: true          # phải là true; số do core lấy từ registry, client không gửi số
  result: confirmed | not_reachable | denied_by_vendor   # chỉ confirmed mới duyệt được
  note: string?
  at: Timestamp

Approval:                             # mỗi hóa đơn có nhiều bản ghi theo thời gian, tối đa MỘT bản active
  approval_id
  invoice_id: string | null           # null với cọc
  purchase_order_id: string | null    # chỉ cọc (tạo escrow)
  source_invoice_id: string | null    # chỉ cọc: hóa đơn 🔴 dẫn tới cọc
  job_id: string | null               # job điều tra mà người duyệt đã xem; Gate đòi = job hoàn tất mới nhất
  status: active | superseded | consumed
  amount_vnd: MoneyVnd, payee_account_id: string, channel: Channel   # Gate đọc từ đây, không từ request
  intent_hash
  approver_user_id: string | null     # null khi method = mandate
  method: ApprovalMethod
  mandate_version: integer | null
  bulk_batch_id: string | null
  verification: Verification | null
  auth_proof_jti: string | null       # id của auth_proof đã dùng
  created_at, superseded_at | null, superseded_reason: NEW_JOB | NEW_SYSTEM_FINDING | PAYMENT_FAILED | PAYMENT_DENIED | OWNER_CANCELLED | null
ApprovalSummary: {approval_id, method, status, approver_user_id, created_at}
# Core đặt approval active → superseded khi: job mới hoàn tất cho hóa đơn, có Finding hệ thống mới, payment.failed,
# payment.denied, chủ chuỗi hủy chi. Core đặt → consumed khi payment.executed / escrow.released.

ApprovalBatchPreview: {preview_id, mandate_version, action_hash, items: [{invoice_id, intent_hash, eligible, excluded_reason, amount_vnd}], eligible_total_vnd, expires_at}
ApprovalBatch:
  batch_id, preview_id, mandate_version, created_by, created_at
  items: [{invoice_id, intent_hash, result: approved | excluded, excluded_reason: ExclusionCode | null, approval_id | null}]
ExclusionCode: INTENT_HASH_MISMATCH | NOT_BULK_APPROVABLE | INVALID_STATE | VERIFICATION_REQUIRED | GATE_DENIED

GateReason:
  code: string                        # BLOCKED_INVOICE | PAYEE_NOT_VERIFIED | ABOVE_PER_INVOICE_LIMIT | ABOVE_DAILY_LIMIT
                                      # | CROSS_ALERT_UNVERIFIED | OFFICIAL_FRAUD_LIST | KILL_SWITCH | POLICY_UNAVAILABLE
                                      # | CHANNEL_NOT_ALLOWED | ALREADY_PAID | OUTSIDE_TIME_WINDOW | MANDATE_NOT_AUTO_PAY
                                      # | VENDOR_NOT_IN_AUTO_PAY | VENDOR_SUSPENDED | APPROVAL_MISSING | APPROVAL_STALE
                                      # | ESCROW_MISMATCH
  layer: hard_rule | platform_policy | mandate
  detail: string                      # trusted (do Gate viết)

PaymentIntentStatus: created | authorized | executing | settled | failed | expired | denied
PaymentIntent:
  payment_intent_id, tenant_id
  invoice_id: string | null           # null với escrow
  purchase_order_id: string | null    # chỉ escrow
  intent_hash, approval_id
  payee_account_id, channel, amount_vnd
  status: PaymentIntentStatus
  gate_reasons: [GateReason]          # khi denied/failed
  rail: {rail_txn_id: string | null, failure_code: string | null}
  transfer_memo: string               # "MST · ký hiệu · số" (D2)
  authorized_at, executed_at, settled_at, expires_at: Timestamp | null
  created_at

EscrowStatus: pending | held | released | refunded | failed
Escrow:
  escrow_id, purchase_order_id, vendor_account_id, amount_vnd
  status: EscrowStatus
  source_invoice_id: string | null
  release_invoice_id: string | null, goods_receipt_id: string | null
  expires_on: LocalDate
  created_at, released_at | null, refunded_at | null
```

## 5. Mandate

```yaml
MandateMode: review_only | ask_first | auto_pay
Mandate:
  mandate_id, version: integer
  mode: MandateMode
  limits: {per_invoice_vnd: MoneyVnd, per_day_vnd: MoneyVnd}     # <= platform ceiling, kiểm khi lưu
  auto_pay_vendor_ids: [string]
  channel_rules: [{invoice_type: InvoiceType, channel: Channel}]
  bulk_approvable: [{reason_codes: [ReasonCode], max_amount_vnd: MoneyVnd}]   # không được chứa mã đỏ
  auto_pay_window: {start: "HH:MM", end: "HH:MM"}                  # giờ VN
  signed: {by_user_id, method: string, auth_proof_jti, at: Timestamp}
  created_at
PlatformLimits: {auto_pay_per_invoice_vnd: 30000000, auto_pay_per_day_vnd: 50000000, updated_at}
AutoPaySuspension: {vendor_id, reason_codes: [ReasonCode], source_invoice_id, suspended_at, lifted_at | null, lifted_by | null}
```

## 6. Dữ liệu gốc

```yaml
Vendor: {vendor_id, name, tax_id, phone_on_file_masked, status: active | inactive, created_at}
VendorAccountStatus: verified | escrow_only | retired
VendorAccount: {vendor_account_id, vendor_id, kind: bank_account | card_merchant, bank_code | null, bank_name | null, account_number_masked | null, merchant_id | null, account_name, status: VendorAccountStatus, verified_at | null}
# Điện nước: nhà cung cấp điện/nước là một Vendor có TK verified; chi bằng bank_transfer, memo có mã khách hàng.
VendorVerification:
  verification_id, vendor_id
  target_status: verified | escrow_only
  proposed_account: {bank_code, account_number, account_name}     # chỉ hiện đủ cho owner/accountant
  origin: {kind: invoice | message | manual, ref_id: string | null}
  callback: {called_phone_on_file: boolean, result: confirmed | not_reachable | denied_by_vendor, by_user_id, at} | null
  status: pending | approved | rejected
  decided_by | null, decided_at | null
VendorContract: {contract_id, vendor_id, status: draft | active | ended, valid_from, valid_to | null, items: [ContractItem], activated_by | null}   # tool chỉ đọc hợp đồng active
ContractItem: {item_id, sku, name, base_unit, pack_spec: string, pack_qty: Decimal, unit_price: Decimal, vat_rate}   # unit_price = giá một pack_spec, chưa VAT; giá/base_unit = unit_price / pack_qty
PurchaseOrder: {purchase_order_id, vendor_id, store_id, lines: [{sku, quantity: Decimal, unit_price: Decimal}], total_vnd, status: open | received | closed | cancelled, created_by, created_at}   # lines theo đơn vị pack_spec, unit_price = giá hợp đồng chưa VAT; total_vnd GỒM VAT (so được với tổng hóa đơn và amount của escrow)
AdjustmentRequest: {adjustment_request_id, invoice_id, to_vendor_id, channel_hint: email | chat, subject, body, cited_lines: [line_id]}   # code điền mẫu, trusted
GoodsReceipt: {goods_receipt_id, purchase_order_id, store_id, lines: [{sku, quantity_received: Decimal}], confirmed_by, confirmed_at}
ExpenseRecord: {expense_id, store_id | null, amount_vnd, payee_name, reason, spent_on: LocalDate, recorded_by, created_at}
Store: {store_id, name, kind: outlet | central_kitchen, address}
User: {user_id, name, role: owner | accountant | store_manager, store_ids: [string]}
```

## 7. Bot, skill, tool

```yaml
BotStatus: draft | pending_review | active | disabled | archived   # theo từng version; bot có active_version và tối đa một version draft/pending_review
BotManifest:                          # = contracts/schemas/bot-manifest.schema.json
  id: string                          # kebab-case
  name: string, description: string   # tiếng Việt, hiển thị
  skills: [string]                    # "skill_id@version"
  tools: [string]                     # tool_id trong registry ∩ tool_grants
  task_types: [TaskType]              # mặc định [investigate_invoice]
  triggers: {invoice_types: [InvoiceType]}
  required_for: [InvoiceType]         # chỉ bot system đặt được
Bot: {bot_id, scope: system | tenant, enabled: boolean, archived: boolean, active_version: integer | null, versions: [BotVersion], updated_at}
BotVersion: {version, status: BotStatus, manifest: BotManifest, created_by, created_at, reviewed_by | null}
ReasonCodeInfo: {code, floor_severity: Severity, ceiling_severity: Severity | null, qt03: boolean, description}
ModelConfig: {purpose: bot | brief, primary_model, fallback_model, max_tokens, timeout_s, etag}
BotValidationError: {field, code: TOOL_NOT_IN_REGISTRY | TOOL_NOT_GRANTED | UNKNOWN_REASON_CODE | UNKNOWN_INVOICE_TYPE | SKILL_NOT_FOUND | REQUIRED_FOR_NOT_ALLOWED}
Skill: {skill_id, name, version: integer, content_md: string, scope: system | tenant, created_at}

ToolDefinition:                       # GET /internal/tools, GET /m/tools (không có handler)
  tool_id: string                     # snake_case
  description: string                 # cho LLM
  input_schema: JSONSchema
  output_schema: JSONSchema
  default_provenance: Provenance
  scope: tenant

ToolResult:
  data: object                        # theo output_schema
  provenance: Provenance              # với tool trả cả số và chữ: phần chữ nằm trong data.untrusted và nhãn chung là untrusted
  evidence_ref: string                # = tool_call_id
  error: {code: UPSTREAM_UNAVAILABLE | UPSTREAM_TIMEOUT | NOT_FOUND | INVALID_INPUT, detail} | null

CapabilityTokenClaims:                # JWT ký bởi core (EdDSA), chỉ internal-api kiểm; phân biệt oneOf theo loại sub
  iss: core, aud: internal-api
  sub: "supervisor" | "<bot_id>"      # khớp holder ở /heartbeat
  tenant_id, job_id
  invoice_id: string | null           # null với job question / report
  attempt: integer, worker_id: string  # token của attempt cũ bị từ chối
  bot_version: integer | null         # sub = "supervisor" → bắt buộc null; sub = "<bot_id>" → bắt buộc integer >= 1
  tools: [tool_id]                    # sub = "supervisor" → cấm chứa tool untrusted (inbox, chat_messages, invoices)
  store_ids?: [string] | null         # giới hạn quán cho hội thoại/báo cáo của store_manager
  iat?: integer                       # Unix epoch giây; thời hạn tối đa exp - iat <= 120 s
  exp: integer                        # <= iat + 120 s và <= now + 120 s (gia hạn qua heartbeat)
  jti
```

## 8. Rủi ro (console)

```yaml
IndicatorKind: account_hash | tax_id | phone | card_id | merchant_id
IndicatorRef: {kind: IndicatorKind, value_hash: string}   # value_hash khớp ^[0-9a-f]{64}$ (SHA-256 hex chữ thường); dùng chung trong indicator.flagged, cross_alert.published, hard_block.applied
Indicator: {indicator_id, kind: IndicatorKind, value_hash: string, first_seen_at, flags_count: integer}   # value thật không lưu với account/phone
Alert: {alert_id, indicator_ids: [string], reason_codes, source: finding | rail | simo, source_tenant_count: integer, status: open | assigned | dismissed | escalated, assignee: string | null, created_at}
Case: {case_id, alert_ids, status: open | closed, summary: string, created_by, created_at}
CaseActionType: note | propose_hard_block | propose_cross_alert_withdrawal
CaseAction: {action_id, case_id, type: CaseActionType, payload, maker, checker | null, status: proposed | approved | rejected | applied, created_at, decided_at | null}
#   payload theo type: note {text} · propose_hard_block {indicator_ids, list_ref} · propose_cross_alert_withdrawal {cross_alert_id}
HardBlock: {hard_block_id, indicator_ids, list_ref, case_action_id, applied_at}   # bảng risk.hard_blocks, Gate đọc
CrossAlert: {cross_alert_id, indicator_ids, reason_codes, published_by, status: published | withdrawn, affected_invoice_count: integer, published_at, withdrawn_at | null}
KillSwitchScope: indicator | tenant | bot | tool | auto_pay_global
KillSwitch: {kill_switch_id, scope: KillSwitchScope, target_id: string | null, reason, engaged_by, engaged_at, status: engaged | released, released_at | null}
KillSwitchReleaseRequest: {request_id, kill_switch_id, maker, checker | null, status: proposed | approved | rejected, created_at, decided_at | null}
EvidenceChain:                        # F6, PII che mặc định
  ticket_id, tenant_ref
  payment_intent: PaymentIntent | null
  invoice: Invoice (đã che)           # tên NCC, MST giữ; số TK, SĐT che
  contract_items_matched: [ContractItem]
  findings: [Finding]
  tool_calls: [{tool_call_id, tool_id, bot_id, provenance, at}]
  trace_id: string
  approval: Approval | null
```

## 9. Hội thoại và báo cáo

```yaml
Conversation: {conversation_id, user_id, title, context: {invoice_id?} | null, status: open | archived, created_at, updated_at}
Message:
  message_id, conversation_id
  role: user | assistant
  text: string                        # role=user: trusted; role=assistant: hiển thị như UntrustedText
  status: pending | completed | failed   # chỉ assistant
  citations: [{tool_call_id, values: [string]}]
  unverified_values: [string]         # số core đã gỡ vì không có nguồn
  tables: [{title, columns: [string], rows: [[string | number]], tool_call_id}]
  proposed_actions: [ProposedAction]
  job_id: string | null
  created_at
ProposedAction:                       # UI hiện thành nút; bấm vẫn đi qua endpoint thường, kể cả step-up
  kind: open_invoice | open_approval_queue | preview_bulk_approval | open_vendor | open_account_change | reinvestigate_invoice
  target_ids: [string]                # core kiểm thuộc tenant và quán của người hỏi
  label: string                       # code sinh từ kind, không phải LLM
Report: {report_id, kind, from, to, status: pending | completed | failed, message: Message | null, created_at}
```

## 10. Thông báo

```yaml
NotificationKind: cross_alert_affected | payment_failed | daily_summary | verification_needed | bot_review_needed | escrow_expiring
Notification: {notification_id, kind, invoice_ids: [string], title: string, body: string, read_at: Timestamp | null, created_at}
# title/body sinh từ mẫu cố định trong code theo kind; không chèn chữ untrusted
```
