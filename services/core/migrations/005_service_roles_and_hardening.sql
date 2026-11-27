-- 005_service_roles_and_hardening.sql
-- Hardening for B1 (least-privilege non-superuser login roles + narrow SECURITY DEFINER claim),
-- B2 (outbox receipt table), I4 (payment intent linkage), I5 (tightened grants & composite FKs),
-- and I7 (server-tracked approval preview records).

-- ---------------------------------------------------------------------------
-- 1. New tables: outbox_receipts (B2), payment_intent_links (I4), approval_previews (I7)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS core.outbox_receipts (
    source TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source, event_id)
);

CREATE TABLE IF NOT EXISTS core.payment_intent_links (
    payment_intent_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    invoice_id TEXT NOT NULL REFERENCES core.invoices(invoice_id),
    approval_id TEXT NOT NULL REFERENCES core.approvals(approval_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payment_intent_links_inv
    ON core.payment_intent_links(tenant_id, invoice_id, created_at DESC);

CREATE TABLE IF NOT EXISTS core.approval_previews (
    preview_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    invoice_id TEXT NOT NULL REFERENCES core.invoices(invoice_id),
    user_id TEXT NOT NULL REFERENCES core.users(user_id),
    job_id TEXT NOT NULL REFERENCES core.jobs(job_id),
    intent_hash TEXT NOT NULL,
    action_hash TEXT NOT NULL,
    verification_required BOOLEAN NOT NULL,
    invoice_version INT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_approval_previews_lookup
    ON core.approval_previews(tenant_id, invoice_id, user_id, expires_at DESC);

-- Enable & force RLS on new tenant-scoped tables
ALTER TABLE core.payment_intent_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.payment_intent_links FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS merchant_tenant_isolation ON core.payment_intent_links;
CREATE POLICY merchant_tenant_isolation ON core.payment_intent_links
    FOR ALL TO merchant
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

ALTER TABLE core.approval_previews ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.approval_previews FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS merchant_tenant_isolation ON core.approval_previews;
CREATE POLICY merchant_tenant_isolation ON core.approval_previews
    FOR ALL TO merchant
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- ---------------------------------------------------------------------------
-- 2. Tenant-keyed composite unique constraints & FKs (I5)
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_invoice_documents_tenant_doc') THEN
        ALTER TABLE core.invoice_documents ADD CONSTRAINT uq_invoice_documents_tenant_doc UNIQUE (tenant_id, document_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_invoices_tenant_inv') THEN
        ALTER TABLE core.invoices ADD CONSTRAINT uq_invoices_tenant_inv UNIQUE (tenant_id, invoice_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_vendors_tenant_vendor') THEN
        ALTER TABLE core.vendors ADD CONSTRAINT uq_vendors_tenant_vendor UNIQUE (tenant_id, vendor_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_stores_tenant_store') THEN
        ALTER TABLE core.stores ADD CONSTRAINT uq_stores_tenant_store UNIQUE (tenant_id, store_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_purchase_orders_tenant_po') THEN
        ALTER TABLE core.purchase_orders ADD CONSTRAINT uq_purchase_orders_tenant_po UNIQUE (tenant_id, purchase_order_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_jobs_tenant_job') THEN
        ALTER TABLE core.jobs ADD CONSTRAINT uq_jobs_tenant_job UNIQUE (tenant_id, job_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_approvals_tenant_apv') THEN
        ALTER TABLE core.approvals ADD CONSTRAINT uq_approvals_tenant_apv UNIQUE (tenant_id, approval_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_invoices_tenant_doc') THEN
        ALTER TABLE core.invoices
            ADD CONSTRAINT fk_invoices_tenant_doc
            FOREIGN KEY (tenant_id, document_id) REFERENCES core.invoice_documents(tenant_id, document_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_invoice_lines_tenant_inv') THEN
        ALTER TABLE core.invoice_lines
            ADD CONSTRAINT fk_invoice_lines_tenant_inv
            FOREIGN KEY (tenant_id, invoice_id) REFERENCES core.invoices(tenant_id, invoice_id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_findings_tenant_inv') THEN
        ALTER TABLE core.findings
            ADD CONSTRAINT fk_findings_tenant_inv
            FOREIGN KEY (tenant_id, invoice_id) REFERENCES core.invoices(tenant_id, invoice_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_approvals_tenant_inv') THEN
        ALTER TABLE core.approvals
            ADD CONSTRAINT fk_approvals_tenant_inv
            FOREIGN KEY (tenant_id, invoice_id) REFERENCES core.invoices(tenant_id, invoice_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_goods_receipts_tenant_po') THEN
        ALTER TABLE core.goods_receipts
            ADD CONSTRAINT fk_goods_receipts_tenant_po
            FOREIGN KEY (tenant_id, purchase_order_id) REFERENCES core.purchase_orders(tenant_id, purchase_order_id);
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 3. Non-superuser login roles per service process (B1)
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'merchant_api') THEN
        CREATE ROLE merchant_api LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD 'merchant_api_dev';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'internal_api') THEN
        CREATE ROLE internal_api LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD 'internal_api_dev';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'worker') THEN
        CREATE ROLE worker LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD 'worker_dev';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'migrator') THEN
        CREATE ROLE migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS PASSWORD 'migrator_dev';
    END IF;
END
$$;

GRANT merchant TO merchant_api;
GRANT merchant TO internal_api;

-- Migrator owns core/control/risk objects (still NOSUPERUSER) so it can migrate and run demo reset
DO $$
DECLARE
    obj RECORD;
BEGIN
    FOR obj IN
        SELECT schemaname, tablename FROM pg_tables WHERE schemaname IN ('core', 'control', 'risk')
    LOOP
        EXECUTE format('ALTER TABLE %I.%I OWNER TO migrator;', obj.schemaname, obj.tablename);
    END LOOP;
    FOR obj IN
        SELECT schemaname, sequencename FROM pg_sequences WHERE schemaname IN ('core', 'control', 'risk')
    LOOP
        EXECUTE format('ALTER SEQUENCE %I.%I OWNER TO migrator;', obj.schemaname, obj.sequencename);
    END LOOP;
END
$$;
GRANT ALL ON SCHEMA core, control, risk TO migrator;
GRANT ALL ON ALL TABLES IN SCHEMA core, control, risk TO migrator;
GRANT ALL ON ALL SEQUENCES IN SCHEMA core, control, risk TO migrator;

-- ---------------------------------------------------------------------------
-- 4. Narrow SECURITY DEFINER functions for cross-tenant internal-api operations (B1)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION core.claim_next_job(
    p_worker_id TEXT,
    p_allowed_types TEXT[],
    p_lease_until TIMESTAMPTZ,
    p_now TIMESTAMPTZ,
    p_max_concurrent INT
)
RETURNS TABLE (
    job_id TEXT,
    task_type TEXT,
    tenant_id TEXT,
    attempt INT,
    lease_expires_at TIMESTAMPTZ,
    subject JSONB
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = core, pg_catalog
AS $$
DECLARE
    v_job_id TEXT;
BEGIN
    SELECT j.job_id INTO v_job_id
    FROM core.jobs j
    WHERE j.task_type = ANY(p_allowed_types)
      AND (
        j.status = 'queued'
        OR (j.status = 'running' AND j.lease_expires_at < p_now)
      )
      AND (
        SELECT COUNT(*) FROM core.jobs r
        WHERE r.tenant_id = j.tenant_id
          AND r.status = 'running'
          AND r.lease_expires_at >= p_now
      ) < p_max_concurrent
    ORDER BY
      CASE j.task_type
        WHEN 'question' THEN 0
        WHEN 'investigate_invoice' THEN 1
        ELSE 2
      END ASC,
      j.created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1;

    IF v_job_id IS NULL THEN
        RETURN;
    END IF;

    RETURN QUERY
    UPDATE core.jobs j
    SET status = 'running',
        attempt = j.attempt + 1,
        worker_id = p_worker_id,
        lease_expires_at = p_lease_until,
        started_at = COALESCE(j.started_at, p_now),
        updated_at = p_now
    WHERE j.job_id = v_job_id
    RETURNING j.job_id, j.task_type, j.tenant_id, j.attempt, j.lease_expires_at, j.subject;
END;
$$;

CREATE OR REPLACE FUNCTION core.lookup_job_tenant(p_job_id TEXT)
RETURNS TEXT
LANGUAGE sql
SECURITY DEFINER
SET search_path = core, pg_catalog
AS $$
    SELECT tenant_id FROM core.jobs WHERE job_id = p_job_id;
$$;

CREATE OR REPLACE FUNCTION core.receive_rails_webhook_event(
    p_event_id TEXT,
    p_event_type TEXT,
    p_occurred_at TIMESTAMPTZ,
    p_data JSONB,
    p_now TIMESTAMPTZ,
    p_outbox_event_id TEXT,
    p_trace_id TEXT,
    p_outbox_data JSONB
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = core, pg_catalog
AS $$
DECLARE
    v_inserted TEXT;
BEGIN
    INSERT INTO core.webhook_events (event_id, event_type, occurred_at, data, received_at)
    VALUES (p_event_id, p_event_type, p_occurred_at, p_data, p_now)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id INTO v_inserted;

    IF v_inserted IS NULL THEN
        RETURN FALSE;
    END IF;

    IF p_outbox_data IS NOT NULL THEN
        INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
        VALUES (p_outbox_event_id, 'indicator.flagged', 1, p_now, NULL, p_trace_id, p_outbox_data);
    END IF;

    RETURN TRUE;
END;
$$;

ALTER FUNCTION core.claim_next_job(TEXT, TEXT[], TIMESTAMPTZ, TIMESTAMPTZ, INT) OWNER TO migrator;
ALTER FUNCTION core.lookup_job_tenant(TEXT) OWNER TO migrator;
ALTER FUNCTION core.receive_rails_webhook_event(TEXT, TEXT, TIMESTAMPTZ, JSONB, TIMESTAMPTZ, TEXT, TEXT, JSONB) OWNER TO migrator;

REVOKE ALL ON FUNCTION core.claim_next_job(TEXT, TEXT[], TIMESTAMPTZ, TIMESTAMPTZ, INT) FROM PUBLIC;
REVOKE ALL ON FUNCTION core.lookup_job_tenant(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION core.receive_rails_webhook_event(TEXT, TEXT, TIMESTAMPTZ, JSONB, TIMESTAMPTZ, TEXT, TEXT, JSONB) FROM PUBLIC;

GRANT USAGE ON SCHEMA core, control TO internal_api;
GRANT EXECUTE ON FUNCTION core.claim_next_job(TEXT, TEXT[], TIMESTAMPTZ, TIMESTAMPTZ, INT) TO internal_api;
GRANT EXECUTE ON FUNCTION core.lookup_job_tenant(TEXT) TO internal_api;
GRANT EXECUTE ON FUNCTION core.receive_rails_webhook_event(TEXT, TEXT, TIMESTAMPTZ, JSONB, TIMESTAMPTZ, TEXT, TEXT, JSONB) TO internal_api;
GRANT SELECT ON control.model_configs TO internal_api;

-- ---------------------------------------------------------------------------
-- 5. Tighten grants for merchant, staff, gate, and worker (I5)
-- ---------------------------------------------------------------------------

-- Revoke mutable grants from merchant on immutable / append-only / internal-only tables
REVOKE ALL ON core.webhook_events, core.outbox_cursors, core.processed_events, core.outbox_receipts FROM merchant;
REVOKE UPDATE, DELETE ON
    core.invoice_documents,
    core.audit_events,
    core.used_auth_proofs,
    core.outbox,
    core.sse_events,
    core.tool_calls,
    core.bot_answers,
    core.briefs
FROM merchant;

-- Grant append-only SELECT/INSERT on new merchant-accessible tables
GRANT SELECT, INSERT ON core.approval_previews, core.payment_intent_links TO merchant;

-- Restrict outbox INSERT RLS policies to producer-owned event types
DROP POLICY IF EXISTS staff_outbox_insert ON core.outbox;
CREATE POLICY staff_outbox_insert ON core.outbox
    FOR INSERT TO staff
    WITH CHECK (
        type IN (
            'cross_alert.published',
            'cross_alert.withdrawn',
            'hard_block.applied',
            'hard_block.lifted',
            'policy.updated',
            'kill_switch.updated'
        )
    );

DROP POLICY IF EXISTS merchant_outbox_insert ON core.outbox;
CREATE POLICY merchant_outbox_insert ON core.outbox
    FOR INSERT TO merchant
    WITH CHECK (
        type IN (
            'invoice.ingested',
            'invoice.status_changed',
            'job.progressed',
            'job.completed',
            'approval.created',
            'approval.superseded',
            'notification.created',
            'indicator.flagged'
        )
        AND (
            tenant_id = current_setting('app.tenant_id', true)
            OR (type = 'indicator.flagged' AND tenant_id IS NULL)
        )
    );

-- Narrow gate column grants: no raw_bytes from invoice_documents, no reason/evidence from findings
REVOKE SELECT ON core.invoice_documents, core.findings FROM gate;
GRANT SELECT (document_id, tenant_id, format, sha256, content_type, filename, received_at)
    ON core.invoice_documents TO gate;
GRANT SELECT (finding_id, tenant_id, job_id, invoice_id, attempt, bot_id, severity, reason_codes, superseded, created_at)
    ON core.findings TO gate;

-- Least-privilege grants & explicit RLS policies for `worker` role
GRANT USAGE ON SCHEMA core, control, risk TO worker;
GRANT SELECT ON
    core.tenants,
    core.stores,
    core.users,
    core.vendors,
    core.vendor_accounts,
    core.vendor_verifications,
    core.vendor_contracts,
    core.contract_items,
    core.purchase_orders,
    core.goods_receipts,
    core.payables,
    core.expense_records,
    core.utility_accounts,
    core.mandates,
    core.briefs,
    core.bot_answers,
    core.tool_calls,
    core.webhook_events
TO worker;
GRANT SELECT, INSERT ON
    core.invoice_documents,
    core.invoice_lines,
    core.invoice_messages,
    core.utility_readings,
    core.findings,
    core.notifications,
    core.outbox,
    core.outbox_receipts,
    core.sse_events,
    core.audit_events,
    core.payment_intent_links
TO worker;
GRANT SELECT, INSERT, UPDATE ON
    core.invoices,
    core.jobs,
    core.approvals,
    core.auto_pay_suspensions,
    core.poll_cursors
TO worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO worker;

GRANT SELECT ON control.policies, control.tools, control.tool_grants, control.bot_definitions, control.bot_versions, control.model_configs TO worker;
GRANT SELECT, INSERT, UPDATE ON risk.indicators, risk.alerts, risk.cross_alerts TO worker;
GRANT SELECT ON risk.hard_blocks TO worker;

-- Worker RLS policies on RLS-enabled core/control tables it reads/writes
DO $$
DECLARE
    tbl TEXT;
    worker_core_tables TEXT[] := ARRAY[
        'tenants',
        'stores',
        'users',
        'vendors',
        'vendor_accounts',
        'vendor_verifications',
        'vendor_contracts',
        'contract_items',
        'invoice_documents',
        'invoices',
        'invoice_lines',
        'invoice_messages',
        'purchase_orders',
        'goods_receipts',
        'payables',
        'expense_records',
        'utility_accounts',
        'utility_readings',
        'jobs',
        'tool_calls',
        'findings',
        'bot_answers',
        'briefs',
        'mandates',
        'auto_pay_suspensions',
        'approvals',
        'notifications',
        'poll_cursors',
        'outbox',
        'sse_events',
        'audit_events',
        'payment_intent_links'
    ];
BEGIN
    FOREACH tbl IN ARRAY worker_core_tables LOOP
        EXECUTE format('DROP POLICY IF EXISTS worker_access ON core.%I;', tbl);
        EXECUTE format('CREATE POLICY worker_access ON core.%I FOR ALL TO worker USING (true) WITH CHECK (true);', tbl);
    END LOOP;
END
$$;

DROP POLICY IF EXISTS worker_outbox_insert_guard ON core.outbox;
DROP POLICY IF EXISTS worker_access ON core.outbox;
CREATE POLICY worker_outbox_select ON core.outbox FOR SELECT TO worker USING (true);
CREATE POLICY worker_outbox_insert ON core.outbox
    FOR INSERT TO worker
    WITH CHECK (
        type IN (
            'invoice.ingested',
            'invoice.status_changed',
            'approval.created',
            'approval.superseded',
            'notification.created',
            'indicator.flagged'
        )
    );

DO $$
DECLARE
    tbl TEXT;
    worker_ctrl_tables TEXT[] := ARRAY['bot_definitions', 'bot_versions', 'tool_grants'];
BEGIN
    FOREACH tbl IN ARRAY worker_ctrl_tables LOOP
        EXECUTE format('DROP POLICY IF EXISTS worker_read ON control.%I;', tbl);
        EXECUTE format('CREATE POLICY worker_read ON control.%I FOR SELECT TO worker USING (true);', tbl);
    END LOOP;
END
$$;

-- Revoke broad ledger grants from merchant; grant ONLY worker read-only on ledger.outbox (+ payment_intents if present)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'ledger') THEN
        EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA ledger FROM merchant';
        EXECUTE 'REVOKE USAGE ON SCHEMA ledger FROM merchant';
        EXECUTE 'GRANT USAGE ON SCHEMA ledger TO worker';
        IF to_regclass('ledger.outbox') IS NOT NULL THEN
            EXECUTE 'GRANT SELECT ON ledger.outbox TO worker';
        END IF;
        IF to_regclass('ledger.payment_intents') IS NOT NULL THEN
            EXECUTE 'GRANT SELECT ON ledger.payment_intents TO worker';
        END IF;
    END IF;
END
$$;
