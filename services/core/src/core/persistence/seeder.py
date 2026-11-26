"""Seed loader reading services/sim-world/data/demo/core_seed/ into Postgres schemas core & control."""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from core.persistence.default_bots import DEFAULT_MODEL_CONFIGS, SYSTEM_BOTS
from core.shared.config import DEFAULT_SEED_DIR
from core.shared.ids import new_id
from core.tools.domain.registry import V1_TOOL_SPECS


def _load_json(seed_dir: pathlib.Path, filename: str) -> dict[str, Any]:
    return json.loads((seed_dir / filename).read_text(encoding="utf-8"))


def truncate_all(conn: psycopg.Connection) -> None:
    """Clear all core, control, and risk data tables for a clean demo reset."""
    conn.execute(
        """
        TRUNCATE TABLE
            core.sse_events,
            core.audit_events,
            core.processed_events,
            core.outbox_cursors,
            core.outbox,
            core.poll_cursors,
            core.webhook_events,
            core.idempotency_keys,
            core.used_auth_proofs,
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
        RESTART IDENTITY CASCADE
        """
    )


def sync_tool_registry(conn: psycopg.Connection) -> int:
    """Sync V1_TOOL_SPECS from code into control.tools (tools.md §1)."""
    for spec in V1_TOOL_SPECS.values():
        defn = spec.to_definition()
        conn.execute(
            """
            INSERT INTO control.tools (tool_id, description, input_schema, output_schema, default_provenance, scope)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tool_id) DO UPDATE SET
                description = EXCLUDED.description,
                input_schema = EXCLUDED.input_schema,
                output_schema = EXCLUDED.output_schema,
                default_provenance = EXCLUDED.default_provenance,
                scope = EXCLUDED.scope,
                updated_at = now()
            """,
            (
                defn["tool_id"],
                defn["description"],
                Jsonb(defn["input_schema"]),
                Jsonb(defn["output_schema"]),
                defn["default_provenance"],
                defn["scope"],
            ),
        )
    return len(V1_TOOL_SPECS)


def seed_system_bots_and_models(conn: psycopg.Connection) -> int:
    """Seed the 6 system bots, their skills, and default model configs."""
    for bot in SYSTEM_BOTS:
        skill = bot["skill"]
        conn.execute(
            """
            INSERT INTO control.skills (skill_id, tenant_id, name, scope)
            VALUES (%s, '', %s, 'system')
            ON CONFLICT (skill_id, tenant_id) DO UPDATE SET name = EXCLUDED.name
            """,
            (skill["skill_id"], skill["name"]),
        )
        conn.execute(
            """
            INSERT INTO control.skill_versions (skill_id, tenant_id, version, content_md)
            VALUES (%s, '', %s, %s)
            ON CONFLICT (skill_id, tenant_id, version) DO UPDATE SET content_md = EXCLUDED.content_md
            """,
            (skill["skill_id"], skill["version"], skill["content_md"]),
        )
        conn.execute(
            """
            INSERT INTO control.bot_definitions (bot_id, tenant_id, scope, enabled, archived, active_version)
            VALUES (%s, '', 'system', TRUE, FALSE, %s)
            ON CONFLICT (bot_id, tenant_id) DO UPDATE SET
                enabled = TRUE,
                archived = FALSE,
                active_version = EXCLUDED.active_version,
                updated_at = now()
            """,
            (bot["bot_id"], bot["version"]),
        )
        conn.execute(
            """
            INSERT INTO control.bot_versions (bot_id, tenant_id, version, status, manifest, prefetch, created_by)
            VALUES (%s, '', %s, 'active', %s, %s, 'system')
            ON CONFLICT (bot_id, tenant_id, version) DO UPDATE SET
                status = 'active',
                manifest = EXCLUDED.manifest,
                prefetch = EXCLUDED.prefetch
            """,
            (bot["bot_id"], bot["version"], Jsonb(bot["manifest"]), bot["prefetch"]),
        )

    for cfg in DEFAULT_MODEL_CONFIGS:
        conn.execute(
            """
            INSERT INTO control.model_configs (purpose, primary_model, fallback_model, max_tokens, timeout_s, version)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (purpose) DO UPDATE SET
                primary_model = EXCLUDED.primary_model,
                fallback_model = EXCLUDED.fallback_model,
                max_tokens = EXCLUDED.max_tokens,
                timeout_s = EXCLUDED.timeout_s,
                version = EXCLUDED.version,
                updated_at = now()
            """,
            (
                cfg["purpose"],
                cfg["primary_model"],
                cfg["fallback_model"],
                cfg["max_tokens"],
                cfg["timeout_s"],
                cfg["version"],
            ),
        )
    return len(SYSTEM_BOTS)


def load_core_seed(
    conn: psycopg.Connection,
    seed_dir: pathlib.Path = DEFAULT_SEED_DIR,
    *,
    reset: bool = True,
) -> dict[str, int]:
    """Load core_seed JSON files into Postgres core & control schemas."""
    tenant_data = _load_json(seed_dir, "tenant_and_stores.json")
    vendor_data = _load_json(seed_dir, "vendors.json")
    ops_data = _load_json(seed_dir, "operations.json")
    platform_data = _load_json(seed_dir, "platform_config.json")

    with conn.transaction():
        if reset:
            truncate_all(conn)

        tool_count = sync_tool_registry(conn)
        bot_count = seed_system_bots_and_models(conn)

        for t in tenant_data["tenants"]:
            conn.execute(
                """
                INSERT INTO core.tenants (tenant_id, wallet_id, tax_id, name, short_name, address, mailbox, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (
                    t["tenant_id"],
                    t["wallet_id"],
                    t["tax_id"],
                    t["name"],
                    t.get("short_name", ""),
                    t.get("address", ""),
                    t["mailbox"],
                    t["created_at"],
                ),
            )

        for s in tenant_data["stores"]:
            conn.execute(
                """
                INSERT INTO core.stores (store_id, tenant_id, name, kind, district, address)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (store_id) DO NOTHING
                """,
                (
                    s["store_id"],
                    s["tenant_id"],
                    s["name"],
                    s["kind"],
                    s.get("district", ""),
                    s.get("address", ""),
                ),
            )

        for u in tenant_data["users"]:
            conn.execute(
                """
                INSERT INTO core.users (user_id, tenant_id, name, email, role, store_ids)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (
                    u["user_id"],
                    u["tenant_id"],
                    u["name"],
                    u.get("email", ""),
                    u["role"],
                    u.get("store_ids", []),
                ),
            )

        for v in vendor_data["vendors"]:
            conn.execute(
                """
                INSERT INTO core.vendors (
                    vendor_id, tenant_id, name, tax_id, phone_on_file, phone_on_file_masked,
                    email, address, category, status, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (vendor_id) DO NOTHING
                """,
                (
                    v["vendor_id"],
                    v["tenant_id"],
                    v["name"],
                    v["tax_id"],
                    v.get("phone_on_file", ""),
                    v.get("phone_on_file_masked", ""),
                    v.get("email", ""),
                    v.get("address", ""),
                    v.get("category", "dry_packaging"),
                    v.get("status", "active"),
                    v["created_at"],
                ),
            )

        for va in vendor_data["vendor_accounts"]:
            conn.execute(
                """
                INSERT INTO core.vendor_accounts (
                    vendor_account_id, vendor_id, tenant_id, kind, bank_code, bank_name,
                    account_number, account_number_masked, merchant_id, account_name, status, verified_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (vendor_account_id) DO NOTHING
                """,
                (
                    va["vendor_account_id"],
                    va["vendor_id"],
                    va["tenant_id"],
                    va["kind"],
                    va.get("bank_code"),
                    va.get("bank_name"),
                    va.get("account_number"),
                    va.get("account_number_masked"),
                    va.get("merchant_id"),
                    va["account_name"],
                    va["status"],
                    va.get("verified_at"),
                ),
            )

        contract_item_count = 0
        for vc in vendor_data["vendor_contracts"]:
            conn.execute(
                """
                INSERT INTO core.vendor_contracts (
                    contract_id, vendor_id, tenant_id, status, valid_from, valid_to, activated_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (contract_id) DO NOTHING
                """,
                (
                    vc["contract_id"],
                    vc["vendor_id"],
                    vc["tenant_id"],
                    vc["status"],
                    vc["valid_from"],
                    vc.get("valid_to"),
                    vc.get("activated_by"),
                ),
            )
            for item in vc.get("items", []):
                conn.execute(
                    """
                    INSERT INTO core.contract_items (
                        item_id, contract_id, tenant_id, sku, name, base_unit,
                        pack_spec, pack_qty, unit_price, vat_rate, price_source_ref
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (item_id) DO NOTHING
                    """,
                    (
                        item["item_id"],
                        vc["contract_id"],
                        vc["tenant_id"],
                        item["sku"],
                        item["name"],
                        item["base_unit"],
                        item["pack_spec"],
                        str(item["pack_qty"]),
                        str(item["unit_price"]),
                        item["vat_rate"],
                        item.get("price_source_ref"),
                    ),
                )
                contract_item_count += 1

        for m in tenant_data["mandates"]:
            conn.execute(
                """
                INSERT INTO core.mandates (
                    mandate_id, tenant_id, version, mode, limits, auto_pay_vendor_ids,
                    channel_rules, bulk_approvable, auto_pay_window, signed, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (mandate_id) DO NOTHING
                """,
                (
                    m["mandate_id"],
                    m["tenant_id"],
                    m["version"],
                    m["mode"],
                    Jsonb(m["limits"]),
                    m.get("auto_pay_vendor_ids", []),
                    Jsonb(m.get("channel_rules", [])),
                    Jsonb(m.get("bulk_approvable", [])),
                    Jsonb(m["auto_pay_window"]),
                    Jsonb(m["signed"]),
                    m["created_at"],
                ),
            )

        for po in ops_data.get("purchase_orders", []):
            conn.execute(
                """
                INSERT INTO core.purchase_orders (
                    purchase_order_id, tenant_id, vendor_id, store_id, lines, total_vnd, status, created_by, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (purchase_order_id) DO NOTHING
                """,
                (
                    po["purchase_order_id"],
                    po["tenant_id"],
                    po["vendor_id"],
                    po["store_id"],
                    Jsonb(po["lines"]),
                    po["total_vnd"],
                    po["status"],
                    po["created_by"],
                    po["created_at"],
                ),
            )

        for grn in ops_data.get("goods_receipts", []):
            conn.execute(
                """
                INSERT INTO core.goods_receipts (
                    goods_receipt_id, tenant_id, purchase_order_id, store_id, lines, confirmed_by, confirmed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (goods_receipt_id) DO NOTHING
                """,
                (
                    grn["goods_receipt_id"],
                    grn["tenant_id"],
                    grn["purchase_order_id"],
                    grn["store_id"],
                    Jsonb(grn["lines"]),
                    grn["confirmed_by"],
                    grn["confirmed_at"],
                ),
            )

        for pay in ops_data.get("payables", []):
            conn.execute(
                """
                INSERT INTO core.payables (
                    invoice_id, tenant_id, vendor_id, symbol, number, issued_on, due_on, amount_vnd, status, paid_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (invoice_id) DO NOTHING
                """,
                (
                    pay["invoice_id"],
                    pay["tenant_id"],
                    pay.get("vendor_id"),
                    pay["symbol"],
                    pay["number"],
                    pay.get("issued_on"),
                    pay.get("due_on"),
                    pay["amount_vnd"],
                    pay["status"],
                    pay.get("paid_at"),
                ),
            )

        for ua in ops_data.get("utility_accounts", []):
            conn.execute(
                """
                INSERT INTO core.utility_accounts (
                    utility_account_id, tenant_id, store_id, vendor_id, utility_type,
                    customer_code, tariff_code, voltage_or_meter_spec
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (utility_account_id) DO NOTHING
                """,
                (
                    ua["utility_account_id"],
                    ua["tenant_id"],
                    ua["store_id"],
                    ua["vendor_id"],
                    ua["utility_type"],
                    ua["customer_code"],
                    ua.get("tariff_code", ""),
                    ua.get("voltage_or_meter_spec", ""),
                ),
            )

        for ur in ops_data.get("utility_readings", []):
            conn.execute(
                """
                INSERT INTO core.utility_readings (
                    reading_id, utility_account_id, tenant_id, store_id, utility_type,
                    billing_period, period_start, period_end, billing_days, due_date,
                    statement_no, total_usage, usage_unit, subtotal_vnd, vat_total_vnd, total_vnd, lines
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (reading_id) DO NOTHING
                """,
                (
                    ur["reading_id"],
                    ur["utility_account_id"],
                    ur["tenant_id"],
                    ur["store_id"],
                    ur["utility_type"],
                    ur["billing_period"],
                    ur["period_start"],
                    ur["period_end"],
                    ur.get("billing_days", 30),
                    ur.get("due_date"),
                    ur.get("statement_no"),
                    str(ur["total_usage"]),
                    ur["usage_unit"],
                    ur["subtotal_vnd"],
                    ur["vat_total_vnd"],
                    ur["total_vnd"],
                    Jsonb(ur.get("lines", [])),
                ),
            )

        # Platform limits policy
        pl = platform_data["platform_limits"]
        conn.execute(
            """
            INSERT INTO control.policies (policy_id, kind, scope, target_id, status, payload, updated_at)
            VALUES ('pol_platform_limits', 'platform_limits', NULL, NULL, 'active', %s, %s)
            ON CONFLICT (policy_id) DO UPDATE SET
                payload = EXCLUDED.payload,
                status = 'active',
                updated_at = EXCLUDED.updated_at
            """,
            (Jsonb(pl), pl["updated_at"]),
        )

        # Tool grants per tenant
        grant_count = 0
        for tg in platform_data.get("tool_grants", []):
            tid = tg["tenant_id"]
            for tool_id in tg.get("tools", []):
                conn.execute(
                    """
                    INSERT INTO control.tool_grants (grant_id, tenant_id, tool_id, enabled)
                    VALUES (%s, %s, %s, TRUE)
                    ON CONFLICT (tenant_id, tool_id) DO UPDATE SET enabled = TRUE
                    """,
                    (new_id("grt"), tid, tool_id),
                )
                grant_count += 1

    return {
        "tenants": len(tenant_data["tenants"]),
        "stores": len(tenant_data["stores"]),
        "users": len(tenant_data["users"]),
        "vendors": len(vendor_data["vendors"]),
        "vendor_accounts": len(vendor_data["vendor_accounts"]),
        "contracts": len(vendor_data["vendor_contracts"]),
        "contract_items": contract_item_count,
        "purchase_orders": len(ops_data.get("purchase_orders", [])),
        "goods_receipts": len(ops_data.get("goods_receipts", [])),
        "utility_accounts": len(ops_data.get("utility_accounts", [])),
        "utility_readings": len(ops_data.get("utility_readings", [])),
        "tools": tool_count,
        "bots": bot_count,
        "tool_grants": grant_count,
    }


def seed_dsn(dsn: str, seed_dir: pathlib.Path = DEFAULT_SEED_DIR, *, reset: bool = True) -> dict[str, int]:
    from core.persistence.migrator import apply_migrations

    with psycopg.connect(dsn) as conn:
        apply_migrations(conn)
        return load_core_seed(conn, seed_dir=seed_dir, reset=reset)


if __name__ == "__main__":
    from core.shared.config import CoreSettings

    cfg = CoreSettings.from_env()
    counts = seed_dsn(cfg.database_url, seed_dir=cfg.seed_dir, reset=True)
    print(json.dumps(counts, indent=2))
    sys.exit(0)
