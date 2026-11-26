-- 004_rls_and_grants.sql
-- Row-Level Security by tenant_id for role `merchant`, and least-privilege grants for `merchant` and `staff`.

-- Helper: enable & force RLS on every tenant-scoped business table in core.
DO $$
DECLARE
    tbl TEXT;
    core_tenant_tables TEXT[] := ARRAY[
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
        'adjustment_requests',
        'notifications',
        'used_auth_proofs',
        'idempotency_keys',
        'poll_cursors',
        'audit_events',
        'sse_events'
    ];
BEGIN
    FOREACH tbl IN ARRAY core_tenant_tables LOOP
        EXECUTE format('ALTER TABLE core.%I ENABLE ROW LEVEL SECURITY;', tbl);
        EXECUTE format('ALTER TABLE core.%I FORCE ROW LEVEL SECURITY;', tbl);
        EXECUTE format('DROP POLICY IF EXISTS merchant_tenant_isolation ON core.%I;', tbl);
        EXECUTE format(
            'CREATE POLICY merchant_tenant_isolation ON core.%I FOR ALL TO merchant USING (tenant_id = current_setting(''app.tenant_id'', true)) WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true));',
            tbl
        );
    END LOOP;
END
$$;

-- core.outbox: merchant can insert/select only own tenant rows (or network-wide indicator.flagged inserts with tenant_id IS NULL)
ALTER TABLE core.outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.outbox FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS merchant_outbox_select ON core.outbox;
CREATE POLICY merchant_outbox_select ON core.outbox
    FOR SELECT TO merchant
    USING (tenant_id = current_setting('app.tenant_id', true));
DROP POLICY IF EXISTS merchant_outbox_insert ON core.outbox;
CREATE POLICY merchant_outbox_insert ON core.outbox
    FOR INSERT TO merchant
    WITH CHECK (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true));
DROP POLICY IF EXISTS staff_outbox_insert ON core.outbox;
CREATE POLICY staff_outbox_insert ON core.outbox
    FOR INSERT TO staff
    WITH CHECK (true);

-- control tenant-scoped tables: merchant can read system rows (tenant_id = '') + own tenant rows, write only own tenant rows.
DO $$
DECLARE
    tbl TEXT;
    control_tables TEXT[] := ARRAY[
        'bot_definitions',
        'bot_versions',
        'skills',
        'skill_versions'
    ];
BEGIN
    FOREACH tbl IN ARRAY control_tables LOOP
        EXECUTE format('ALTER TABLE control.%I ENABLE ROW LEVEL SECURITY;', tbl);
        EXECUTE format('ALTER TABLE control.%I FORCE ROW LEVEL SECURITY;', tbl);
        EXECUTE format('DROP POLICY IF EXISTS merchant_read_sys_or_own ON control.%I;', tbl);
        EXECUTE format(
            'CREATE POLICY merchant_read_sys_or_own ON control.%I FOR SELECT TO merchant USING (tenant_id = '''' OR tenant_id = current_setting(''app.tenant_id'', true));',
            tbl
        );
        EXECUTE format('DROP POLICY IF EXISTS merchant_write_own ON control.%I;', tbl);
        EXECUTE format(
            'CREATE POLICY merchant_write_own ON control.%I FOR INSERT TO merchant WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true) AND tenant_id <> '''');',
            tbl
        );
        EXECUTE format('DROP POLICY IF EXISTS merchant_update_own ON control.%I;', tbl);
        EXECUTE format(
            'CREATE POLICY merchant_update_own ON control.%I FOR UPDATE TO merchant USING (tenant_id = current_setting(''app.tenant_id'', true) AND tenant_id <> '''') WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true) AND tenant_id <> '''');',
            tbl
        );
    END LOOP;
END
$$;

ALTER TABLE control.tool_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE control.tool_grants FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS merchant_tool_grants_select ON control.tool_grants;
CREATE POLICY merchant_tool_grants_select ON control.tool_grants
    FOR SELECT TO merchant
    USING (tenant_id = current_setting('app.tenant_id', true));

-- Revoke default PUBLIC access on all schemas/tables
REVOKE ALL ON SCHEMA core, risk, control FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA core, risk, control FROM PUBLIC;

-- Grants for `merchant` role
GRANT USAGE ON SCHEMA core, control, risk TO merchant;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA core TO merchant;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO merchant;
GRANT SELECT ON control.tools, control.tool_grants, control.policies, control.model_configs TO merchant;
GRANT SELECT, INSERT, UPDATE ON control.bot_definitions, control.bot_versions, control.skills, control.skill_versions TO merchant;
-- merchant can read published cross_alerts, hard_blocks, indicators (only hashes, no other tenant data)
GRANT SELECT ON risk.indicators, risk.cross_alerts, risk.hard_blocks TO merchant;

-- Grants for `staff` role (console-api): read/write risk and control, ONLY INSERT on core.outbox, NO read on core.invoices!
GRANT USAGE ON SCHEMA risk, control, core TO staff;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA risk TO staff;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA control TO staff;
GRANT INSERT ON core.outbox TO staff;
GRANT USAGE, SELECT ON SEQUENCE core.outbox_seq_seq TO staff;

-- Grants & read-only RLS policies for `gate` role (payment-gate reads core/control/risk read-only)
GRANT USAGE ON SCHEMA core, control, risk TO gate;
GRANT SELECT ON
    core.tenants,
    core.invoices,
    core.invoice_documents,
    core.approvals,
    core.vendor_accounts,
    core.vendors,
    core.mandates,
    core.auto_pay_suspensions,
    core.purchase_orders,
    core.goods_receipts,
    core.jobs,
    core.findings
TO gate;
GRANT SELECT ON control.policies TO gate;
GRANT SELECT ON risk.indicators, risk.hard_blocks, risk.cross_alerts TO gate;

DO $$
DECLARE
    tbl TEXT;
    gate_core_tables TEXT[] := ARRAY[
        'tenants',
        'invoices',
        'invoice_documents',
        'approvals',
        'vendor_accounts',
        'vendors',
        'mandates',
        'auto_pay_suspensions',
        'purchase_orders',
        'goods_receipts',
        'jobs',
        'findings'
    ];
BEGIN
    FOREACH tbl IN ARRAY gate_core_tables LOOP
        EXECUTE format('DROP POLICY IF EXISTS gate_readonly ON core.%I;', tbl);
        EXECUTE format('CREATE POLICY gate_readonly ON core.%I FOR SELECT TO gate USING (true);', tbl);
    END LOOP;
END
$$;

-- Conditional read-only grant on schema ledger if gate migration has already created it
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'ledger') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA ledger TO merchant';
        EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA ledger TO merchant';
    END IF;
END
$$;
