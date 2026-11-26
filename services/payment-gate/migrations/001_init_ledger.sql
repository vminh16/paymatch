-- Migration 001: Initialize schema `ledger` owned exclusively by payment-gate.
-- See docs/02-architecture/data-model.md §2 (ledger) and docs/05-api/events.md §1.

CREATE SCHEMA IF NOT EXISTS ledger;

CREATE TABLE IF NOT EXISTS ledger.schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Two-phase payment intents (created -> authorized -> executing -> settled|failed, or denied/expired).
CREATE TABLE IF NOT EXISTS ledger.payment_intents (
    payment_intent_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    invoice_id TEXT NULL,
    purchase_order_id TEXT NULL,
    intent_hash TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    approval_method TEXT NOT NULL CHECK (approval_method IN ('single', 'bulk', 'mandate')),
    budget_date DATE NULL,
    payee_account_id TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('bank_transfer', 'virtual_card', 'escrow')),
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd >= 0),
    status TEXT NOT NULL CHECK (
        status IN ('created', 'authorized', 'executing', 'settled', 'failed', 'expired', 'denied')
    ),
    gate_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    rail_txn_id TEXT NULL,
    failure_code TEXT NULL,
    transfer_memo TEXT NOT NULL,
    authorized_at TIMESTAMPTZ NULL,
    executed_at TIMESTAMPTZ NULL,
    settled_at TIMESTAMPTZ NULL,
    expires_at TIMESTAMPTZ NULL,
    stuck_notified_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL
);

-- Hard invariant (#11): at most ONE active/settled intent per invoice.
-- Failed, denied, and expired intents do not block a subsequent re-approved attempt.
CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_intents_active_invoice
    ON ledger.payment_intents (invoice_id)
    WHERE invoice_id IS NOT NULL AND status IN ('authorized', 'executing', 'settled');

CREATE INDEX IF NOT EXISTS idx_payment_intents_tenant_created
    ON ledger.payment_intents (tenant_id, created_at DESC, payment_intent_id DESC);

CREATE INDEX IF NOT EXISTS idx_payment_intents_invoice
    ON ledger.payment_intents (tenant_id, invoice_id)
    WHERE invoice_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_payment_intents_status_expires
    ON ledger.payment_intents (status, expires_at)
    WHERE status = 'authorized';

CREATE INDEX IF NOT EXISTS idx_payment_intents_status_executing
    ON ledger.payment_intents (status, executed_at)
    WHERE status = 'executing';

-- Single-use payment authorization tokens issued in phase 1 and consumed on phase 2 execute.
CREATE TABLE IF NOT EXISTS ledger.payment_tokens (
    token_id TEXT PRIMARY KEY,
    payment_intent_id TEXT NOT NULL UNIQUE REFERENCES ledger.payment_intents(payment_intent_id),
    tenant_id TEXT NOT NULL,
    intent_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('issued', 'consumed', 'revoked', 'expired')),
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ NULL
);

-- Escrow holds bound to a purchase order (F7).
CREATE TABLE IF NOT EXISTS ledger.escrows (
    escrow_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    purchase_order_id TEXT NOT NULL,
    vendor_account_id TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd >= 0),
    status TEXT NOT NULL CHECK (status IN ('pending', 'held', 'released', 'refunded', 'failed')),
    source_invoice_id TEXT NULL,
    release_invoice_id TEXT NULL,
    release_approval_id TEXT NULL,
    goods_receipt_id TEXT NULL,
    rail_escrow_id TEXT NULL,
    failure_code TEXT NULL,
    expires_on DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    released_at TIMESTAMPTZ NULL,
    refunded_at TIMESTAMPTZ NULL
);

-- Hard rule: at most ONE open (pending or held) escrow per purchase order.
CREATE UNIQUE INDEX IF NOT EXISTS uq_escrows_open_po
    ON ledger.escrows (purchase_order_id)
    WHERE status IN ('pending', 'held');

CREATE INDEX IF NOT EXISTS idx_escrows_tenant_po
    ON ledger.escrows (tenant_id, purchase_order_id);

CREATE INDEX IF NOT EXISTS idx_escrows_pending
    ON ledger.escrows (status, created_at)
    WHERE status = 'pending';

-- Append-only financial ledger. Never updated or deleted.
CREATE TABLE IF NOT EXISTS ledger.ledger_entries (
    entry_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    payment_intent_id TEXT NULL REFERENCES ledger.payment_intents(payment_intent_id),
    escrow_id TEXT NULL REFERENCES ledger.escrows(escrow_id),
    invoice_id TEXT NULL,
    purchase_order_id TEXT NULL,
    payee_account_id TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('bank_transfer', 'virtual_card', 'escrow')),
    entry_type TEXT NOT NULL CHECK (
        entry_type IN (
            'settled',
            'failed',
            'escrow_held',
            'escrow_released',
            'escrow_refunded',
            'escrow_failed'
        )
    ),
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd >= 0),
    rail_txn_id TEXT NULL,
    failure_code TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

-- Hard invariant (#11): at most ONE settled ledger entry per invoice.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_entries_settled_invoice
    ON ledger.ledger_entries (invoice_id)
    WHERE invoice_id IS NOT NULL AND entry_type IN ('settled', 'escrow_released');

CREATE INDEX IF NOT EXISTS idx_ledger_entries_tenant_created
    ON ledger.ledger_entries (tenant_id, created_at DESC);

CREATE OR REPLACE FUNCTION ledger.prevent_ledger_entry_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'ledger.ledger_entries is append-only; % is forbidden', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ledger_entries_append_only ON ledger.ledger_entries;
CREATE TRIGGER trg_ledger_entries_append_only
    BEFORE UPDATE OR DELETE ON ledger.ledger_entries
    FOR EACH ROW EXECUTE FUNCTION ledger.prevent_ledger_entry_mutation();

-- Per-tenant, per-Vietnam-date daily budget row locked with SELECT ... FOR UPDATE.
CREATE TABLE IF NOT EXISTS ledger.daily_budgets (
    tenant_id TEXT NOT NULL,
    budget_date DATE NOT NULL,
    auto_pay_used_vnd BIGINT NOT NULL DEFAULT 0 CHECK (auto_pay_used_vnd >= 0),
    auto_pay_reserved_vnd BIGINT NOT NULL DEFAULT 0 CHECK (auto_pay_reserved_vnd >= 0),
    total_paid_vnd BIGINT NOT NULL DEFAULT 0 CHECK (total_paid_vnd >= 0),
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, budget_date)
);

-- Rail call journal with exact idempotent request payload for background polling.
CREATE TABLE IF NOT EXISTS ledger.rail_transactions (
    rail_tx_pk TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    payment_intent_id TEXT NULL REFERENCES ledger.payment_intents(payment_intent_id),
    escrow_id TEXT NULL REFERENCES ledger.escrows(escrow_id),
    channel TEXT NOT NULL CHECK (channel IN ('bank_transfer', 'virtual_card', 'escrow')),
    operation TEXT NOT NULL CHECK (
        operation IN ('transfer', 'card', 'escrow_hold', 'escrow_release', 'escrow_refund')
    ),
    idempotency_key TEXT NOT NULL UNIQUE,
    rail_ref_id TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'settled', 'failed', 'held', 'released', 'refunded')
    ),
    failure_code TEXT NULL,
    request_payload JSONB NOT NULL,
    response_payload JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rail_transactions_intent
    ON ledger.rail_transactions (payment_intent_id)
    WHERE payment_intent_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_rail_transactions_escrow
    ON ledger.rail_transactions (escrow_id)
    WHERE escrow_id IS NOT NULL;

-- Transactional outbox (identical shape to core.outbox; read-only for core-worker).
-- Gate does not create cursor tables here; core owns its own outbox cursor.
CREATE TABLE IF NOT EXISTS ledger.outbox (
    seq BIGSERIAL NOT NULL,
    event_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    schema_version INT NOT NULL DEFAULT 1,
    occurred_at TIMESTAMPTZ NOT NULL,
    tenant_id TEXT NULL,
    trace_id TEXT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ledger_outbox_tenant_seq
    ON ledger.outbox (tenant_id, seq);
