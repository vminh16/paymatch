-- 002_core_tables.sql
-- Core schema tables per docs/02-architecture/data-model.md and docs/05-api/schemas.md.

CREATE TABLE IF NOT EXISTS core.tenants (
    tenant_id TEXT PRIMARY KEY,
    wallet_id TEXT NOT NULL,
    tax_id TEXT NOT NULL,
    name TEXT NOT NULL,
    short_name TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    mailbox TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS core.stores (
    store_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('outlet', 'central_kitchen')),
    district TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_stores_tenant ON core.stores(tenant_id);

CREATE TABLE IF NOT EXISTS core.users (
    user_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    name TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL CHECK (role IN ('owner', 'accountant', 'store_manager')),
    store_ids TEXT[] NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON core.users(tenant_id);

CREATE TABLE IF NOT EXISTS core.vendors (
    vendor_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    name TEXT NOT NULL,
    tax_id TEXT NOT NULL,
    phone_on_file TEXT NOT NULL DEFAULT '',
    phone_on_file_masked TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'dry_packaging',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, tax_id)
);
CREATE INDEX IF NOT EXISTS idx_vendors_tenant_tax ON core.vendors(tenant_id, tax_id);

CREATE TABLE IF NOT EXISTS core.vendor_accounts (
    vendor_account_id TEXT PRIMARY KEY,
    vendor_id TEXT NOT NULL REFERENCES core.vendors(vendor_id),
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    kind TEXT NOT NULL CHECK (kind IN ('bank_account', 'card_merchant')),
    bank_code TEXT NULL,
    bank_name TEXT NULL,
    account_number TEXT NULL,
    account_number_masked TEXT NULL,
    merchant_id TEXT NULL,
    account_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verified', 'escrow_only', 'retired')),
    verified_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_vendor_accounts_tenant_vendor ON core.vendor_accounts(tenant_id, vendor_id);

CREATE TABLE IF NOT EXISTS core.vendor_verifications (
    verification_id TEXT PRIMARY KEY,
    vendor_id TEXT NOT NULL REFERENCES core.vendors(vendor_id),
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    vendor_account_id TEXT NULL REFERENCES core.vendor_accounts(vendor_account_id),
    target_status TEXT NOT NULL CHECK (target_status IN ('verified', 'escrow_only')),
    proposed_account JSONB NOT NULL,
    origin JSONB NOT NULL,
    callback JSONB NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    decided_by TEXT NULL,
    decided_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_vendor_verifications_tenant_vendor ON core.vendor_verifications(tenant_id, vendor_id);

CREATE TABLE IF NOT EXISTS core.vendor_contracts (
    contract_id TEXT PRIMARY KEY,
    vendor_id TEXT NOT NULL REFERENCES core.vendors(vendor_id),
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'ended')),
    valid_from DATE NOT NULL,
    valid_to DATE NULL,
    activated_by TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_vendor_contracts_tenant_vendor ON core.vendor_contracts(tenant_id, vendor_id);

CREATE TABLE IF NOT EXISTS core.contract_items (
    item_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL REFERENCES core.vendor_contracts(contract_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    base_unit TEXT NOT NULL,
    pack_spec TEXT NOT NULL,
    pack_qty TEXT NOT NULL,
    unit_price TEXT NOT NULL,
    vat_rate TEXT NOT NULL,
    price_source_ref TEXT NULL
);
CREATE INDEX IF NOT EXISTS idx_contract_items_tenant_contract ON core.contract_items(tenant_id, contract_id);
CREATE INDEX IF NOT EXISTS idx_contract_items_tenant_sku ON core.contract_items(tenant_id, sku);

CREATE TABLE IF NOT EXISTS core.invoice_documents (
    document_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    format TEXT NOT NULL CHECK (format IN ('xml', 'pdf', 'image')),
    sha256 TEXT NOT NULL,
    raw_bytes BYTEA NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'application/xml',
    filename TEXT NOT NULL DEFAULT '',
    received_at TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, sha256)
);
CREATE INDEX IF NOT EXISTS idx_invoice_documents_tenant ON core.invoice_documents(tenant_id);

CREATE TABLE IF NOT EXISTS core.invoices (
    invoice_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    document_id TEXT NOT NULL REFERENCES core.invoice_documents(document_id),
    document_sha256 TEXT NOT NULL DEFAULT '',
    store_id TEXT NULL REFERENCES core.stores(store_id),
    vendor_id TEXT NULL REFERENCES core.vendors(vendor_id),
    seller_tax_id TEXT NOT NULL DEFAULT '',
    buyer_tax_id TEXT NOT NULL DEFAULT '',
    symbol TEXT NOT NULL DEFAULT '',
    number TEXT NOT NULL DEFAULT '',
    number_norm TEXT NOT NULL DEFAULT '',
    issued_on DATE NULL,
    invoice_type TEXT NOT NULL CHECK (invoice_type IN ('goods', 'utility', 'software')),
    source TEXT NOT NULL CHECK (source IN ('email', 'upload', 'bill_pay', 'scenario')),
    currency TEXT NOT NULL DEFAULT 'VND',
    subtotal_vnd BIGINT NULL,
    vat_total_vnd BIGINT NULL,
    total_vnd BIGINT NULL,
    vat_breakdown JSONB NOT NULL DEFAULT '[]'::jsonb,
    tax_authority_code TEXT NULL,
    einvoice_provider_tax_id TEXT NULL,
    related_invoice JSONB NULL,
    untrusted JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (status IN (
        'new', 'investigating', 'auto_pay_eligible', 'pending_approval',
        'blocked', 'approved', 'scheduled', 'paying', 'paid',
        'payment_failed', 'escrow_held', 'rejected'
    )),
    severity TEXT NULL CHECK (severity IS NULL OR severity IN ('green', 'yellow', 'red')),
    reason_codes TEXT[] NOT NULL DEFAULT '{}',
    verification_required BOOLEAN NOT NULL DEFAULT FALSE,
    duplicate_of TEXT NULL REFERENCES core.invoices(invoice_id),
    manual_fields JSONB NULL,
    due_on DATE NULL,
    scheduled_for DATE NULL,
    purchase_order_id TEXT NULL,
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_invoices_tenant_status ON core.invoices(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_invoices_tenant_dupkey ON core.invoices(tenant_id, seller_tax_id, symbol, number_norm);
CREATE INDEX IF NOT EXISTS idx_invoices_tenant_vendor ON core.invoices(tenant_id, vendor_id);

CREATE TABLE IF NOT EXISTS core.invoice_lines (
    line_id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL REFERENCES core.invoices(invoice_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    position INT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('goods_service', 'promotion', 'trade_discount', 'note', 'special_goods')),
    item_code JSONB NULL,
    name JSONB NOT NULL,
    unit JSONB NULL,
    quantity TEXT NULL,
    unit_price TEXT NULL,
    discount_vnd BIGINT NULL,
    amount_vnd BIGINT NULL,
    vat_rate TEXT NULL,
    arithmetic_ok BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_invoice_lines_tenant_invoice ON core.invoice_lines(tenant_id, invoice_id);

CREATE TABLE IF NOT EXISTS core.invoice_messages (
    message_id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL REFERENCES core.invoices(invoice_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    channel TEXT NOT NULL CHECK (channel IN ('email', 'chat')),
    external_message_id TEXT NULL,
    from_address TEXT NULL,
    subject TEXT NULL,
    body JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invoice_messages_tenant_invoice ON core.invoice_messages(tenant_id, invoice_id);

CREATE TABLE IF NOT EXISTS core.purchase_orders (
    purchase_order_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    vendor_id TEXT NOT NULL REFERENCES core.vendors(vendor_id),
    store_id TEXT NOT NULL REFERENCES core.stores(store_id),
    lines JSONB NOT NULL,
    total_vnd BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'received', 'closed', 'cancelled')),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_tenant_vendor ON core.purchase_orders(tenant_id, vendor_id);

CREATE TABLE IF NOT EXISTS core.goods_receipts (
    goods_receipt_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    purchase_order_id TEXT NOT NULL REFERENCES core.purchase_orders(purchase_order_id),
    store_id TEXT NOT NULL REFERENCES core.stores(store_id),
    lines JSONB NOT NULL,
    confirmed_by TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_goods_receipts_tenant_po ON core.goods_receipts(tenant_id, purchase_order_id);

CREATE TABLE IF NOT EXISTS core.payables (
    invoice_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    vendor_id TEXT NULL REFERENCES core.vendors(vendor_id),
    symbol TEXT NOT NULL,
    number TEXT NOT NULL,
    issued_on DATE NULL,
    due_on DATE NULL,
    amount_vnd BIGINT NOT NULL,
    status TEXT NOT NULL,
    paid_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_payables_tenant_vendor ON core.payables(tenant_id, vendor_id);

CREATE TABLE IF NOT EXISTS core.expense_records (
    expense_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    store_id TEXT NULL REFERENCES core.stores(store_id),
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd >= 0),
    payee_name TEXT NOT NULL,
    reason TEXT NOT NULL,
    spent_on DATE NOT NULL,
    recorded_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_expense_records_tenant ON core.expense_records(tenant_id);

CREATE TABLE IF NOT EXISTS core.utility_accounts (
    utility_account_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    store_id TEXT NOT NULL REFERENCES core.stores(store_id),
    vendor_id TEXT NOT NULL REFERENCES core.vendors(vendor_id),
    utility_type TEXT NOT NULL CHECK (utility_type IN ('electricity', 'water')),
    customer_code TEXT NOT NULL,
    tariff_code TEXT NOT NULL DEFAULT '',
    voltage_or_meter_spec TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_utility_accounts_tenant_store ON core.utility_accounts(tenant_id, store_id);

CREATE TABLE IF NOT EXISTS core.utility_readings (
    reading_id TEXT PRIMARY KEY,
    utility_account_id TEXT NOT NULL REFERENCES core.utility_accounts(utility_account_id),
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    store_id TEXT NOT NULL REFERENCES core.stores(store_id),
    utility_type TEXT NOT NULL CHECK (utility_type IN ('electricity', 'water')),
    billing_period TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    billing_days INT NOT NULL DEFAULT 30,
    due_date DATE NULL,
    statement_no TEXT NULL,
    total_usage TEXT NOT NULL,
    usage_unit TEXT NOT NULL,
    subtotal_vnd BIGINT NOT NULL,
    vat_total_vnd BIGINT NOT NULL,
    total_vnd BIGINT NOT NULL,
    lines JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_utility_readings_tenant_store_type ON core.utility_readings(tenant_id, store_id, utility_type, billing_period);

CREATE TABLE IF NOT EXISTS core.jobs (
    job_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    task_type TEXT NOT NULL CHECK (task_type IN ('investigate_invoice', 'question', 'report')),
    subject JSONB NOT NULL,
    invoice_id TEXT NULL REFERENCES core.invoices(invoice_id),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    attempt INT NOT NULL DEFAULT 0,
    worker_id TEXT NULL,
    lease_expires_at TIMESTAMPTZ NULL,
    bots_called JSONB NOT NULL DEFAULT '[]'::jsonb,
    bot_states JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_bot_ids TEXT[] NOT NULL DEFAULT '{}',
    skipped_bots JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_error JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_jobs_claim ON core.jobs(status, task_type, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_tenant_invoice ON core.jobs(tenant_id, invoice_id, created_at DESC);

CREATE TABLE IF NOT EXISTS core.tool_calls (
    tool_call_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    job_id TEXT NOT NULL REFERENCES core.jobs(job_id),
    attempt INT NOT NULL,
    bot_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    input JSONB NOT NULL,
    output JSONB NOT NULL,
    provenance TEXT NOT NULL CHECK (provenance IN ('trusted', 'untrusted')),
    error JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_job_attempt_bot ON core.tool_calls(tenant_id, job_id, attempt, bot_id);

CREATE TABLE IF NOT EXISTS core.findings (
    finding_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    job_id TEXT NULL REFERENCES core.jobs(job_id),
    invoice_id TEXT NOT NULL REFERENCES core.invoices(invoice_id),
    attempt INT NOT NULL DEFAULT 0,
    bot_id TEXT NOT NULL,
    bot_version INT NOT NULL DEFAULT 1,
    skill_version INT NOT NULL DEFAULT 1,
    prompt_hash TEXT NOT NULL DEFAULT 'system',
    severity TEXT NOT NULL CHECK (severity IN ('green', 'yellow', 'red')),
    severity_reported TEXT NOT NULL CHECK (severity_reported IN ('green', 'yellow', 'red')),
    reason_codes TEXT[] NOT NULL,
    reason JSONB NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    provenance TEXT NOT NULL CHECK (provenance IN ('trusted', 'untrusted')),
    proposed_channel TEXT NULL CHECK (proposed_channel IS NULL OR proposed_channel IN ('bank_transfer', 'virtual_card', 'escrow')),
    proposed_pay_on DATE NULL,
    superseded BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_findings_tenant_job ON core.findings(tenant_id, job_id);
CREATE INDEX IF NOT EXISTS idx_findings_tenant_invoice ON core.findings(tenant_id, invoice_id);

CREATE TABLE IF NOT EXISTS core.bot_answers (
    bot_answer_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    job_id TEXT NOT NULL REFERENCES core.jobs(job_id),
    attempt INT NOT NULL,
    bot_id TEXT NOT NULL,
    facts JSONB NOT NULL,
    reason_codes TEXT[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bot_answers_tenant_job ON core.bot_answers(tenant_id, job_id);

CREATE TABLE IF NOT EXISTS core.briefs (
    brief_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    job_id TEXT NOT NULL REFERENCES core.jobs(job_id),
    invoice_id TEXT NOT NULL REFERENCES core.invoices(invoice_id),
    lines JSONB NOT NULL,
    cited_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    model TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_briefs_tenant_invoice ON core.briefs(tenant_id, invoice_id, created_at DESC);

CREATE TABLE IF NOT EXISTS core.mandates (
    mandate_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    version INT NOT NULL CHECK (version >= 1),
    mode TEXT NOT NULL CHECK (mode IN ('review_only', 'ask_first', 'auto_pay')),
    limits JSONB NOT NULL,
    auto_pay_vendor_ids TEXT[] NOT NULL DEFAULT '{}',
    channel_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    bulk_approvable JSONB NOT NULL DEFAULT '[]'::jsonb,
    auto_pay_window JSONB NOT NULL,
    signed JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, version)
);
CREATE INDEX IF NOT EXISTS idx_mandates_tenant_ver ON core.mandates(tenant_id, version DESC);

CREATE TABLE IF NOT EXISTS core.auto_pay_suspensions (
    suspension_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    vendor_id TEXT NOT NULL REFERENCES core.vendors(vendor_id),
    reason_codes TEXT[] NOT NULL,
    source_invoice_id TEXT NOT NULL REFERENCES core.invoices(invoice_id),
    suspended_at TIMESTAMPTZ NOT NULL,
    lifted_at TIMESTAMPTZ NULL,
    lifted_by TEXT NULL
);
CREATE INDEX IF NOT EXISTS idx_auto_pay_suspensions_active ON core.auto_pay_suspensions(tenant_id, vendor_id) WHERE lifted_at IS NULL;

CREATE TABLE IF NOT EXISTS core.approvals (
    approval_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    invoice_id TEXT NULL REFERENCES core.invoices(invoice_id),
    purchase_order_id TEXT NULL REFERENCES core.purchase_orders(purchase_order_id),
    source_invoice_id TEXT NULL REFERENCES core.invoices(invoice_id),
    job_id TEXT NULL REFERENCES core.jobs(job_id),
    status TEXT NOT NULL CHECK (status IN ('active', 'superseded', 'consumed')),
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd >= 0),
    payee_account_id TEXT NOT NULL REFERENCES core.vendor_accounts(vendor_account_id),
    channel TEXT NOT NULL CHECK (channel IN ('bank_transfer', 'virtual_card', 'escrow')),
    intent_hash TEXT NOT NULL,
    approver_user_id TEXT NULL,
    method TEXT NOT NULL CHECK (method IN ('single', 'bulk', 'mandate')),
    mandate_version INT NULL,
    bulk_batch_id TEXT NULL,
    verification JSONB NULL,
    auth_proof_jti TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at TIMESTAMPTZ NULL,
    superseded_reason TEXT NULL CHECK (
        superseded_reason IS NULL OR superseded_reason IN (
            'NEW_JOB', 'NEW_SYSTEM_FINDING', 'PAYMENT_FAILED', 'PAYMENT_DENIED', 'OWNER_CANCELLED'
        )
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_approvals_active_invoice
    ON core.approvals(invoice_id)
    WHERE status = 'active' AND invoice_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_approvals_tenant_invoice ON core.approvals(tenant_id, invoice_id, created_at DESC);

CREATE TABLE IF NOT EXISTS core.adjustment_requests (
    adjustment_request_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    invoice_id TEXT NOT NULL REFERENCES core.invoices(invoice_id),
    to_vendor_id TEXT NULL REFERENCES core.vendors(vendor_id),
    channel_hint TEXT NOT NULL CHECK (channel_hint IN ('email', 'chat')),
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    cited_lines TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_adjustment_requests_tenant_invoice ON core.adjustment_requests(tenant_id, invoice_id);

CREATE TABLE IF NOT EXISTS core.notifications (
    notification_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    user_ids TEXT[] NOT NULL DEFAULT '{}',
    kind TEXT NOT NULL CHECK (kind IN (
        'cross_alert_affected', 'payment_failed', 'daily_summary',
        'verification_needed', 'bot_review_needed', 'escrow_expiring'
    )),
    invoice_ids TEXT[] NOT NULL DEFAULT '{}',
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    read_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notifications_tenant ON core.notifications(tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS core.used_auth_proofs (
    jti TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    user_id TEXT NOT NULL,
    action_hash TEXT NOT NULL,
    used_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.idempotency_keys (
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status_code INT NOT NULL,
    response_body JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, method, path, idempotency_key)
);

CREATE TABLE IF NOT EXISTS core.webhook_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    data JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.poll_cursors (
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    source TEXT NOT NULL,
    cursor TEXT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, source)
);

-- Outbox table matching Event envelope in docs/05-api/events.md §1 (shared shape with ledger.outbox)
CREATE TABLE IF NOT EXISTS core.outbox (
    seq BIGSERIAL,
    event_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    schema_version INT NOT NULL DEFAULT 1,
    occurred_at TIMESTAMPTZ NOT NULL,
    tenant_id TEXT NULL,
    trace_id TEXT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_core_outbox_tenant_seq ON core.outbox(tenant_id, seq);
CREATE INDEX IF NOT EXISTS idx_core_outbox_seq ON core.outbox(seq);

CREATE TABLE IF NOT EXISTS core.outbox_cursors (
    outbox_name TEXT PRIMARY KEY,
    last_seq BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.processed_events (
    event_id TEXT PRIMARY KEY,
    outbox_name TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.audit_events (
    audit_id TEXT PRIMARY KEY,
    tenant_id TEXT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_events_tenant ON core.audit_events(tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS core.sse_events (
    seq BIGSERIAL,
    event_id TEXT PRIMARY KEY,
    stream_type TEXT NOT NULL CHECK (stream_type IN ('job', 'tenant')),
    stream_key TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    store_id TEXT NULL,
    event_type TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sse_events_stream ON core.sse_events(stream_type, stream_key, seq);
