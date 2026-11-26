-- 003_control_and_risk_tables.sql
-- Control and risk schemas per docs/02-architecture/data-model.md.

CREATE TABLE IF NOT EXISTS control.tools (
    tool_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    input_schema JSONB NOT NULL,
    output_schema JSONB NOT NULL,
    default_provenance TEXT NOT NULL CHECK (default_provenance IN ('trusted', 'untrusted')),
    scope TEXT NOT NULL DEFAULT 'tenant',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS control.tool_grants (
    grant_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES core.tenants(tenant_id),
    tool_id TEXT NOT NULL REFERENCES control.tools(tool_id),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, tool_id)
);
CREATE INDEX IF NOT EXISTS idx_tool_grants_tenant ON control.tool_grants(tenant_id);

-- System bots use tenant_id = '' and scope = 'system'; tenant bots use tenant_id = ten_... and scope = 'tenant'.
CREATE TABLE IF NOT EXISTS control.bot_definitions (
    bot_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL CHECK (scope IN ('system', 'tenant')),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    archived BOOLEAN NOT NULL DEFAULT FALSE,
    active_version INT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (bot_id, tenant_id)
);

CREATE TABLE IF NOT EXISTS control.bot_versions (
    bot_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT '',
    version INT NOT NULL CHECK (version >= 1),
    status TEXT NOT NULL CHECK (status IN ('draft', 'pending_review', 'active', 'disabled', 'archived')),
    manifest JSONB NOT NULL,
    prefetch TEXT[] NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by TEXT NULL,
    PRIMARY KEY (bot_id, tenant_id, version),
    FOREIGN KEY (bot_id, tenant_id) REFERENCES control.bot_definitions(bot_id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS control.skills (
    skill_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('system', 'tenant')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (skill_id, tenant_id)
);

CREATE TABLE IF NOT EXISTS control.skill_versions (
    skill_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT '',
    version INT NOT NULL CHECK (version >= 1),
    content_md TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (skill_id, tenant_id, version),
    FOREIGN KEY (skill_id, tenant_id) REFERENCES control.skills(skill_id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS control.policies (
    policy_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('platform_limits', 'kill_switch')),
    scope TEXT NULL CHECK (scope IS NULL OR scope IN ('indicator', 'tenant', 'bot', 'tool', 'auto_pay_global')),
    target_id TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'engaged', 'released')),
    value JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason TEXT NULL,
    engaged_by TEXT NULL,
    engaged_at TIMESTAMPTZ NULL,
    released_by TEXT NULL,
    released_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_policies_kind_status ON control.policies(kind, status);

CREATE TABLE IF NOT EXISTS control.model_configs (
    purpose TEXT PRIMARY KEY CHECK (purpose IN ('bot', 'brief')),
    primary_model TEXT NOT NULL,
    fallback_model TEXT NOT NULL,
    max_tokens INT NOT NULL CHECK (max_tokens >= 1),
    timeout_s INT NOT NULL CHECK (timeout_s >= 1),
    version INT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS control.staff_users (
    staff_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS control.staff_roles (
    staff_id TEXT NOT NULL REFERENCES control.staff_users(staff_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    PRIMARY KEY (staff_id, role)
);

-- Risk schema tables
CREATE TABLE IF NOT EXISTS risk.indicators (
    indicator_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('account_hash', 'tax_id', 'phone', 'card_id', 'merchant_id')),
    value_hash TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    flags_count INT NOT NULL DEFAULT 1,
    UNIQUE (kind, value_hash)
);
CREATE INDEX IF NOT EXISTS idx_risk_indicators_kind_val ON risk.indicators(kind, value_hash);

CREATE TABLE IF NOT EXISTS risk.alerts (
    alert_id TEXT PRIMARY KEY,
    indicator_ids TEXT[] NOT NULL,
    reason_codes TEXT[] NOT NULL DEFAULT '{}',
    source TEXT NOT NULL CHECK (source IN ('finding', 'rail', 'simo')),
    source_refs TEXT[] NOT NULL DEFAULT '{}',
    source_tenant_count INT NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'assigned', 'dismissed', 'escalated')),
    assignee TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS risk.cases (
    case_id TEXT PRIMARY KEY,
    alert_ids TEXT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    summary TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS risk.case_actions (
    action_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES risk.cases(case_id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('note', 'propose_hard_block', 'propose_cross_alert_withdrawal')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    maker TEXT NOT NULL,
    checker TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('proposed', 'approved', 'rejected', 'applied')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS risk.hard_blocks (
    hard_block_id TEXT PRIMARY KEY,
    indicator_kind TEXT NULL CHECK (indicator_kind IS NULL OR indicator_kind IN ('account_hash', 'tax_id', 'phone', 'card_id', 'merchant_id')),
    value_hash TEXT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'lifted')),
    indicator_ids TEXT[] NOT NULL DEFAULT '{}',
    list_ref TEXT NOT NULL DEFAULT '',
    case_action_id TEXT NULL REFERENCES risk.case_actions(action_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_risk_hard_blocks_lookup ON risk.hard_blocks(indicator_kind, value_hash) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS risk.cross_alerts (
    cross_alert_id TEXT PRIMARY KEY,
    indicator_kind TEXT NULL CHECK (indicator_kind IS NULL OR indicator_kind IN ('account_hash', 'tax_id', 'phone', 'card_id', 'merchant_id')),
    value_hash TEXT NULL,
    indicator_ids TEXT[] NOT NULL DEFAULT '{}',
    reason_codes TEXT[] NOT NULL DEFAULT '{}',
    published_by TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('published', 'withdrawn')),
    affected_invoice_count INT NOT NULL DEFAULT 0,
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    withdrawn_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_risk_cross_alerts_lookup ON risk.cross_alerts(indicator_kind, value_hash) WHERE status = 'published';

CREATE TABLE IF NOT EXISTS risk.access_log (
    log_id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    staff_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    accessed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
