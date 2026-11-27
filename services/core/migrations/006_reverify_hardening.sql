-- 006_reverify_hardening.sql
-- Fixes from Codex re-verification of 0e68457:
-- - I1: Backfill core.outbox_receipts from core.processed_events so upgrades never replay acknowledged events.
-- - I4: Per-tenant advisory lock in core.claim_next_job and DB now() comparison for leases.
-- - I5: Composite tenant FKs on payment_intent_links and approval_previews.
-- - I7: Fix staff outbox policy to contracted kill_switch.engaged / kill_switch.released;
--       dedicated narrow core.truncate_for_demo_reset() and demo_reset role (no migrator DSN for merchant-api).
-- - B4: Conditional ledger grants + ALTER DEFAULT PRIVILEGES for worker.
-- - Nits: expired approval_previews index & DELETE grant; catalog-first search_path = pg_catalog, core, pg_temp.

-- ---------------------------------------------------------------------------
-- 1. I1: Backfill outbox_receipts from historical core.processed_events
-- ---------------------------------------------------------------------------
INSERT INTO core.outbox_receipts (source, event_id, processed_at)
SELECT outbox_name, event_id, processed_at
FROM core.processed_events
ON CONFLICT (source, event_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. I5: Tenant-keyed composite FKs on payment_intent_links & approval_previews
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_payment_intent_links_tenant_inv') THEN
        ALTER TABLE core.payment_intent_links
            ADD CONSTRAINT fk_payment_intent_links_tenant_inv
            FOREIGN KEY (tenant_id, invoice_id) REFERENCES core.invoices(tenant_id, invoice_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_payment_intent_links_tenant_apv') THEN
        ALTER TABLE core.payment_intent_links
            ADD CONSTRAINT fk_payment_intent_links_tenant_apv
            FOREIGN KEY (tenant_id, approval_id) REFERENCES core.approvals(tenant_id, approval_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_approval_previews_tenant_inv') THEN
        ALTER TABLE core.approval_previews
            ADD CONSTRAINT fk_approval_previews_tenant_inv
            FOREIGN KEY (tenant_id, invoice_id) REFERENCES core.invoices(tenant_id, invoice_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_approval_previews_tenant_job') THEN
        ALTER TABLE core.approval_previews
            ADD CONSTRAINT fk_approval_previews_tenant_job
            FOREIGN KEY (tenant_id, job_id) REFERENCES core.jobs(tenant_id, job_id);
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 3. Nit 1: Expired approval_previews index & prune privileges
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_approval_previews_expires_at
    ON core.approval_previews(expires_at);
GRANT DELETE ON core.approval_previews TO merchant, worker;
GRANT SELECT ON core.approval_previews TO worker;
DROP POLICY IF EXISTS worker_access ON core.approval_previews;
CREATE POLICY worker_access ON core.approval_previews
    FOR ALL TO worker
    USING (true)
    WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- 4. I7: Fix staff outbox INSERT RLS policy to contracted event names (events.md §2)
-- ---------------------------------------------------------------------------
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
            'kill_switch.engaged',
            'kill_switch.released'
        )
    );

-- ---------------------------------------------------------------------------
-- 5. I4 & Nit 2: Harden SECURITY DEFINER functions (catalog-first search_path,
--    DB now() lease comparison, per-tenant advisory lock for claim concurrency)
-- ---------------------------------------------------------------------------
DROP FUNCTION IF EXISTS core.claim_next_job(TEXT, TEXT[], TIMESTAMPTZ, TIMESTAMPTZ, INT);

CREATE OR REPLACE FUNCTION core.claim_next_job(
    p_worker_id TEXT,
    p_allowed_types TEXT[],
    p_lease_seconds INT,
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
SET search_path = pg_catalog, core, pg_temp
AS $$
DECLARE
    v_now TIMESTAMPTZ := clock_timestamp();
    v_lease_until TIMESTAMPTZ := v_now + make_interval(secs => GREATEST(p_lease_seconds, 1));
    v_cand RECORD;
    v_running INT;
    v_locked_id TEXT;
BEGIN
    FOR v_cand IN
        SELECT j.job_id, j.tenant_id
        FROM core.jobs j
        WHERE j.task_type = ANY(p_allowed_types)
          AND (
            j.status = 'queued'
            OR (j.status = 'running' AND j.lease_expires_at < v_now)
          )
        ORDER BY
          CASE j.task_type
            WHEN 'question' THEN 0
            WHEN 'investigate_invoice' THEN 1
            ELSE 2
          END ASC,
          j.created_at ASC
        LIMIT 50
    LOOP
        -- Serialize concurrent claims per tenant so max_concurrent cannot be exceeded (I4)
        PERFORM pg_advisory_xact_lock(hashtextextended('paymatch:claim:' || v_cand.tenant_id, 0));

        SELECT COUNT(*) INTO v_running
        FROM core.jobs r
        WHERE r.tenant_id = v_cand.tenant_id
          AND r.status = 'running'
          AND r.lease_expires_at >= v_now;

        IF v_running >= p_max_concurrent THEN
            CONTINUE;
        END IF;

        SELECT j.job_id INTO v_locked_id
        FROM core.jobs j
        WHERE j.job_id = v_cand.job_id
          AND (
            j.status = 'queued'
            OR (j.status = 'running' AND j.lease_expires_at < v_now)
          )
        FOR UPDATE SKIP LOCKED;

        IF v_locked_id IS NULL THEN
            CONTINUE;
        END IF;

        RETURN QUERY
        UPDATE core.jobs j
        SET status = 'running',
            attempt = j.attempt + 1,
            worker_id = p_worker_id,
            lease_expires_at = v_lease_until,
            started_at = COALESCE(j.started_at, v_now),
            updated_at = v_now
        WHERE j.job_id = v_locked_id
        RETURNING j.job_id, j.task_type, j.tenant_id, j.attempt, j.lease_expires_at, j.subject;
        RETURN;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION core.lookup_job_tenant(p_job_id TEXT)
RETURNS TEXT
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, core, pg_temp
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
SET search_path = pg_catalog, core, pg_temp
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

ALTER FUNCTION core.claim_next_job(TEXT, TEXT[], INT, INT) OWNER TO migrator;
ALTER FUNCTION core.lookup_job_tenant(TEXT) OWNER TO migrator;
ALTER FUNCTION core.receive_rails_webhook_event(TEXT, TEXT, TIMESTAMPTZ, JSONB, TIMESTAMPTZ, TEXT, TEXT, JSONB) OWNER TO migrator;

REVOKE ALL ON FUNCTION core.claim_next_job(TEXT, TEXT[], INT, INT) FROM PUBLIC;
REVOKE ALL ON FUNCTION core.lookup_job_tenant(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION core.receive_rails_webhook_event(TEXT, TEXT, TIMESTAMPTZ, JSONB, TIMESTAMPTZ, TEXT, TEXT, JSONB) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION core.claim_next_job(TEXT, TEXT[], INT, INT) TO internal_api;
GRANT EXECUTE ON FUNCTION core.lookup_job_tenant(TEXT) TO internal_api;
GRANT EXECUTE ON FUNCTION core.receive_rails_webhook_event(TEXT, TEXT, TIMESTAMPTZ, JSONB, TIMESTAMPTZ, TEXT, TEXT, JSONB) TO internal_api;

-- ---------------------------------------------------------------------------
-- 6. I7: Narrow demo_reset role & SECURITY DEFINER truncate function (no migrator DSN for merchant-api)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'demo_reset') THEN
        CREATE ROLE demo_reset LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS PASSWORD 'demo_reset_dev';
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION core.truncate_for_demo_reset()
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, core, control, risk, pg_temp
AS $$
BEGIN
    TRUNCATE TABLE
        core.sse_events,
        core.audit_events,
        core.outbox_receipts,
        core.processed_events,
        core.outbox_cursors,
        core.outbox,
        core.poll_cursors,
        core.webhook_events,
        core.idempotency_keys,
        core.used_auth_proofs,
        core.approval_previews,
        core.payment_intent_links,
        core.notifications,
        core.adjustment_requests,
        core.approvals,
        core.auto_pay_suspensions,
        core.mandates,
        core.briefs,
        core.bot_answers,
        core.findings,
        core.tool_calls,
        core.jobs,
        core.utility_readings,
        core.utility_accounts,
        core.expense_records,
        core.payables,
        core.goods_receipts,
        core.purchase_orders,
        core.invoice_messages,
        core.invoice_lines,
        core.invoices,
        core.invoice_documents,
        core.contract_items,
        core.vendor_contracts,
        core.vendor_verifications,
        core.vendor_accounts,
        core.vendors,
        core.users,
        core.stores,
        core.tenants,
        control.tool_grants,
        control.bot_versions,
        control.bot_definitions,
        control.skill_versions,
        control.skills,
        control.policies,
        control.model_configs,
        control.staff_roles,
        control.staff_users,
        control.tools,
        risk.access_log,
        risk.cross_alerts,
        risk.hard_blocks,
        risk.case_actions,
        risk.cases,
        risk.alerts,
        risk.indicators
    RESTART IDENTITY CASCADE;
END;
$$;

ALTER FUNCTION core.truncate_for_demo_reset() OWNER TO migrator;
REVOKE ALL ON FUNCTION core.truncate_for_demo_reset() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION core.truncate_for_demo_reset() TO demo_reset, migrator;

-- demo_reset gets ONLY data-seeding DML (no DDL, no DROP/ALTER, no direct TRUNCATE)
GRANT USAGE ON SCHEMA core, control, risk TO demo_reset;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA core, control, risk TO demo_reset;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core, control, risk TO demo_reset;

-- ---------------------------------------------------------------------------
-- 7. B4: Conditional ledger grants & default privileges for worker
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'ledger') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA ledger TO worker';
        EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA ledger TO worker';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA ledger GRANT SELECT ON TABLES TO worker';
    END IF;
END
$$;
ALTER DEFAULT PRIVILEGES FOR ROLE migrator IN SCHEMA core GRANT SELECT ON TABLES TO worker;
