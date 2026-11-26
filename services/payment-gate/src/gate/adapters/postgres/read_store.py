"""Read-only Postgres adapter for cross-schema queries against `core`, `control`, and `risk`.

================================================================================
DOCUMENTED READ-ONLY CROSS-SCHEMA CONTRACT (owned by `core`; Gate ONLY SELECTs)
================================================================================

Schema `core`:
  - core.tenants(
      tenant_id TEXT PRIMARY KEY,
      wallet_id TEXT NOT NULL
    )
  - core.invoices(
      invoice_id TEXT PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      store_id TEXT NULL,
      vendor_id TEXT NULL,
      purchase_order_id TEXT NULL,
      seller_tax_id TEXT NOT NULL,
      symbol TEXT NOT NULL,
      number TEXT NOT NULL,
      invoice_type TEXT NOT NULL,
      total_vnd BIGINT NULL,
      status TEXT NOT NULL,
      severity TEXT NULL,
      reason_codes JSONB/TEXT[] NOT NULL,
      document_sha256 TEXT NOT NULL
    )
  - core.vendors(
      vendor_id TEXT PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      name TEXT NOT NULL,
      tax_id TEXT NOT NULL,
      phone_on_file TEXT NULL,
      status TEXT NOT NULL
    )
  - core.vendor_accounts(
      vendor_account_id TEXT PRIMARY KEY,
      vendor_id TEXT NOT NULL,
      tenant_id TEXT NOT NULL,
      kind TEXT NOT NULL,              -- 'bank_account' | 'card_merchant'
      bank_code TEXT NULL,
      bank_name TEXT NULL,
      account_number TEXT NULL,
      merchant_id TEXT NULL,
      account_name TEXT NOT NULL,
      status TEXT NOT NULL             -- 'verified' | 'escrow_only' | 'retired'
    )
  - core.mandates(
      mandate_id TEXT PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      version INT NOT NULL,
      mode TEXT NOT NULL,              -- 'review_only' | 'ask_first' | 'auto_pay'
      limits JSONB NOT NULL,           -- {"per_invoice_vnd": int, "per_day_vnd": int}
      auto_pay_vendor_ids JSONB NOT NULL,   -- [vendor_id, ...]
      channel_rules JSONB NOT NULL,         -- [{"invoice_type": str, "channel": str}, ...]
      bulk_approvable JSONB NOT NULL,       -- [{"reason_codes": [str], "max_amount_vnd": int}, ...]
      auto_pay_window JSONB NOT NULL        -- {"start": "HH:MM", "end": "HH:MM"}
    )
  - core.auto_pay_suspensions(
      tenant_id TEXT NOT NULL,
      vendor_id TEXT NOT NULL,
      lifted_at TIMESTAMPTZ NULL
    )
  - core.approvals(
      approval_id TEXT PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      invoice_id TEXT NULL,
      purchase_order_id TEXT NULL,
      source_invoice_id TEXT NULL,
      job_id TEXT NULL,
      status TEXT NOT NULL,            -- 'active' | 'superseded' | 'consumed'
      method TEXT NOT NULL,            -- 'single' | 'bulk' | 'mandate'
      amount_vnd BIGINT NOT NULL,
      payee_account_id TEXT NOT NULL,
      channel TEXT NOT NULL,
      intent_hash TEXT NOT NULL,
      approver_user_id TEXT NULL,
      mandate_version INT NULL,
      bulk_batch_id TEXT NULL,
      verification JSONB NULL          -- {"called_phone_on_file": bool, "result": str, "note": str|null, "at": str}
    )
  - core.jobs(
      job_id TEXT PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      task_type TEXT NOT NULL,         -- 'investigate_invoice'
      invoice_id TEXT NULL,
      status TEXT NOT NULL,            -- 'completed'
      completed_at TIMESTAMPTZ NULL
    )
  - core.purchase_orders(
      purchase_order_id TEXT PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      vendor_id TEXT NOT NULL,
      store_id TEXT NOT NULL,
      total_vnd BIGINT NOT NULL,
      status TEXT NOT NULL
    )
  - core.goods_receipts(
      goods_receipt_id TEXT PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      purchase_order_id TEXT NOT NULL,
      store_id TEXT NOT NULL
    )

Schema `control`:
  - control.policies(
      policy_id TEXT PRIMARY KEY,
      kind TEXT NOT NULL CHECK (kind IN ('platform_limits', 'kill_switch')),
      scope TEXT NULL,                 -- KillSwitchScope
      target_id TEXT NULL,
      value JSONB NOT NULL DEFAULT '{}'::jsonb,
      status TEXT NOT NULL,            -- platform_limits: 'active'; kill_switch: 'engaged'|'released'
      engaged_by TEXT NULL,
      released_by TEXT NULL,
      updated_at TIMESTAMPTZ NOT NULL
    )

Schema `risk`:
  - risk.indicators(
      indicator_id TEXT PRIMARY KEY,
      kind TEXT NOT NULL,
      value_hash TEXT NOT NULL
    )
  - risk.hard_blocks(
      hard_block_id TEXT PRIMARY KEY,
      indicator_kind TEXT NOT NULL,
      value_hash TEXT NOT NULL,
      status TEXT NOT NULL,            -- 'active' | 'lifted'
      created_at TIMESTAMPTZ NOT NULL
    )
  - risk.cross_alerts(
      cross_alert_id TEXT PRIMARY KEY,
      indicator_kind TEXT NOT NULL,
      value_hash TEXT NOT NULL,
      status TEXT NOT NULL,            -- 'published' | 'withdrawn'
      published_at TIMESTAMPTZ NOT NULL
    )

Fail-closed invariant (#10):
  Any Postgres error or missing active `platform_limits` row in `control.policies`
  causes `load_policy_state()` to return `PolicyState(available=False)`.
================================================================================
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import psycopg
from psycopg.rows import dict_row

from gate.domain.models import (
    ApprovalSnapshot,
    BulkApprovableRule,
    ChannelRule,
    GoodsReceiptSnapshot,
    IndicatorRef,
    InvoiceSnapshot,
    KillSwitchSnapshot,
    MandateSnapshot,
    PlatformLimitsSnapshot,
    PolicyState,
    PurchaseOrderSnapshot,
    RiskSignals,
    VendorAccountSnapshot,
    VendorSnapshot,
    VerificationRecord,
)


def _as_str_tuple(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, (list, tuple)):
        return tuple(str(x) for x in raw)
    return ()


class PostgresCoreReadStore:
    """Read-only Postgres adapter reading core, control, and risk schemas."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(
            self._conninfo,
            row_factory=dict_row,
            autocommit=True,
            options="-c default_transaction_read_only=on",
        )

    def ping(self) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    cur.fetchone()
            return True
        except Exception:
            return False

    def get_tenant_wallet_id(self, tenant_id: str) -> str | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT wallet_id FROM core.tenants WHERE tenant_id = %s;",
                    (tenant_id,),
                )
                row = cur.fetchone()
                return str(row["wallet_id"]) if row else None

    def get_invoice(self, invoice_id: str) -> InvoiceSnapshot | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        invoice_id,
                        tenant_id,
                        vendor_id,
                        purchase_order_id,
                        seller_tax_id,
                        symbol,
                        number,
                        invoice_type,
                        total_vnd,
                        status,
                        severity,
                        reason_codes,
                        document_sha256
                    FROM core.invoices
                    WHERE invoice_id = %s;
                    """,
                    (invoice_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return InvoiceSnapshot(
                    invoice_id=row["invoice_id"],
                    tenant_id=row["tenant_id"],
                    vendor_id=row["vendor_id"],
                    purchase_order_id=row["purchase_order_id"],
                    seller_tax_id=row["seller_tax_id"],
                    symbol=row["symbol"],
                    number=row["number"],
                    invoice_type=row["invoice_type"],
                    total_vnd=int(row["total_vnd"]) if row["total_vnd"] is not None else None,
                    status=row["status"],
                    severity=row["severity"],
                    reason_codes=_as_str_tuple(row["reason_codes"]),
                    document_sha256=row["document_sha256"],
                )

    def get_vendor(self, tenant_id: str, vendor_id: str) -> VendorSnapshot | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT vendor_id, tenant_id, name, tax_id, phone_on_file, status
                    FROM core.vendors
                    WHERE tenant_id = %s AND vendor_id = %s;
                    """,
                    (tenant_id, vendor_id),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return VendorSnapshot(
                    vendor_id=row["vendor_id"],
                    tenant_id=row["tenant_id"],
                    name=row["name"],
                    tax_id=row["tax_id"],
                    phone_on_file=row["phone_on_file"],
                    status=row["status"],
                )

    def get_vendor_by_tax_id(self, tenant_id: str, tax_id: str) -> VendorSnapshot | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT vendor_id, tenant_id, name, tax_id, phone_on_file, status
                    FROM core.vendors
                    WHERE tenant_id = %s AND tax_id = %s
                    ORDER BY vendor_id ASC
                    LIMIT 1;
                    """,
                    (tenant_id, tax_id),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return VendorSnapshot(
                    vendor_id=row["vendor_id"],
                    tenant_id=row["tenant_id"],
                    name=row["name"],
                    tax_id=row["tax_id"],
                    phone_on_file=row["phone_on_file"],
                    status=row["status"],
                )

    def list_vendor_accounts(
        self, tenant_id: str, vendor_id: str
    ) -> tuple[VendorAccountSnapshot, ...]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        vendor_account_id,
                        vendor_id,
                        tenant_id,
                        kind,
                        bank_code,
                        bank_name,
                        account_number,
                        merchant_id,
                        account_name,
                        status
                    FROM core.vendor_accounts
                    WHERE tenant_id = %s AND vendor_id = %s
                    ORDER BY vendor_account_id ASC;
                    """,
                    (tenant_id, vendor_id),
                )
                rows = cur.fetchall()
                return tuple(
                    VendorAccountSnapshot(
                        vendor_account_id=r["vendor_account_id"],
                        vendor_id=r["vendor_id"],
                        tenant_id=r["tenant_id"],
                        kind=r["kind"],
                        bank_code=r["bank_code"],
                        bank_name=r["bank_name"],
                        account_number=r["account_number"],
                        merchant_id=r["merchant_id"],
                        account_name=r["account_name"],
                        status=r["status"],
                    )
                    for r in rows
                )

    def get_vendor_account(
        self, tenant_id: str, vendor_account_id: str
    ) -> VendorAccountSnapshot | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        vendor_account_id,
                        vendor_id,
                        tenant_id,
                        kind,
                        bank_code,
                        bank_name,
                        account_number,
                        merchant_id,
                        account_name,
                        status
                    FROM core.vendor_accounts
                    WHERE tenant_id = %s AND vendor_account_id = %s;
                    """,
                    (tenant_id, vendor_account_id),
                )
                r = cur.fetchone()
                if r is None:
                    return None
                return VendorAccountSnapshot(
                    vendor_account_id=r["vendor_account_id"],
                    vendor_id=r["vendor_id"],
                    tenant_id=r["tenant_id"],
                    kind=r["kind"],
                    bank_code=r["bank_code"],
                    bank_name=r["bank_name"],
                    account_number=r["account_number"],
                    merchant_id=r["merchant_id"],
                    account_name=r["account_name"],
                    status=r["status"],
                )

    def get_latest_mandate(self, tenant_id: str) -> MandateSnapshot | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        mandate_id,
                        tenant_id,
                        version,
                        mode,
                        limits,
                        auto_pay_vendor_ids,
                        channel_rules,
                        bulk_approvable,
                        auto_pay_window
                    FROM core.mandates
                    WHERE tenant_id = %s
                    ORDER BY version DESC
                    LIMIT 1;
                    """,
                    (tenant_id,),
                )
                r = cur.fetchone()
                if r is None:
                    return None
                limits = r["limits"] or {}
                window = r["auto_pay_window"] or {}
                channel_rules = tuple(
                    ChannelRule(
                        invoice_type=str(cr["invoice_type"]),
                        channel=str(cr["channel"]),
                    )
                    for cr in (r["channel_rules"] or [])
                )
                bulk_rules = tuple(
                    BulkApprovableRule(
                        reason_codes=tuple(str(c) for c in br.get("reason_codes", ())),
                        max_amount_vnd=int(br["max_amount_vnd"]),
                    )
                    for br in (r["bulk_approvable"] or [])
                )
                return MandateSnapshot(
                    mandate_id=r["mandate_id"],
                    tenant_id=r["tenant_id"],
                    version=int(r["version"]),
                    mode=r["mode"],
                    per_invoice_vnd=int(limits["per_invoice_vnd"]),
                    per_day_vnd=int(limits["per_day_vnd"]),
                    auto_pay_vendor_ids=frozenset(str(v) for v in (r["auto_pay_vendor_ids"] or ())),
                    channel_rules=channel_rules,
                    bulk_approvable=bulk_rules,
                    auto_pay_window_start=str(window.get("start", "00:00")),
                    auto_pay_window_end=str(window.get("end", "23:59")),
                )

    def is_vendor_suspended(self, tenant_id: str, vendor_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM core.auto_pay_suspensions
                    WHERE tenant_id = %s AND vendor_id = %s AND lifted_at IS NULL
                    LIMIT 1;
                    """,
                    (tenant_id, vendor_id),
                )
                return cur.fetchone() is not None

    def get_approval(self, approval_id: str) -> ApprovalSnapshot | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        approval_id,
                        tenant_id,
                        invoice_id,
                        purchase_order_id,
                        source_invoice_id,
                        job_id,
                        status,
                        method,
                        amount_vnd,
                        payee_account_id,
                        channel,
                        intent_hash,
                        approver_user_id,
                        mandate_version,
                        bulk_batch_id,
                        verification
                    FROM core.approvals
                    WHERE approval_id = %s;
                    """,
                    (approval_id,),
                )
                r = cur.fetchone()
                if r is None:
                    return None
                ver_raw = r["verification"]
                verification = (
                    VerificationRecord(
                        called_phone_on_file=bool(ver_raw.get("called_phone_on_file")),
                        result=str(ver_raw.get("result", "")),
                        note=ver_raw.get("note"),
                        at=ver_raw.get("at"),
                    )
                    if isinstance(ver_raw, dict)
                    else None
                )
                return ApprovalSnapshot(
                    approval_id=r["approval_id"],
                    tenant_id=r["tenant_id"],
                    invoice_id=r["invoice_id"],
                    purchase_order_id=r["purchase_order_id"],
                    source_invoice_id=r["source_invoice_id"],
                    job_id=r["job_id"],
                    status=r["status"],
                    method=r["method"],
                    amount_vnd=int(r["amount_vnd"]),
                    payee_account_id=r["payee_account_id"],
                    channel=r["channel"],
                    intent_hash=r["intent_hash"],
                    approver_user_id=r["approver_user_id"],
                    mandate_version=int(r["mandate_version"]) if r["mandate_version"] is not None else None,
                    bulk_batch_id=r["bulk_batch_id"],
                    verification=verification,
                )

    def get_latest_completed_job_id(self, tenant_id: str, invoice_id: str) -> str | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT job_id
                    FROM core.jobs
                    WHERE tenant_id = %s
                      AND invoice_id = %s
                      AND task_type = 'investigate_invoice'
                      AND status = 'completed'
                    ORDER BY completed_at DESC NULLS LAST, job_id DESC
                    LIMIT 1;
                    """,
                    (tenant_id, invoice_id),
                )
                r = cur.fetchone()
                return str(r["job_id"]) if r else None

    def get_purchase_order(self, purchase_order_id: str) -> PurchaseOrderSnapshot | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT purchase_order_id, tenant_id, vendor_id, store_id, total_vnd, status
                    FROM core.purchase_orders
                    WHERE purchase_order_id = %s;
                    """,
                    (purchase_order_id,),
                )
                r = cur.fetchone()
                if r is None:
                    return None
                return PurchaseOrderSnapshot(
                    purchase_order_id=r["purchase_order_id"],
                    tenant_id=r["tenant_id"],
                    vendor_id=r["vendor_id"],
                    store_id=r["store_id"],
                    total_vnd=int(r["total_vnd"]),
                    status=r["status"],
                )

    def get_goods_receipt(self, goods_receipt_id: str) -> GoodsReceiptSnapshot | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT goods_receipt_id, tenant_id, purchase_order_id, store_id
                    FROM core.goods_receipts
                    WHERE goods_receipt_id = %s;
                    """,
                    (goods_receipt_id,),
                )
                r = cur.fetchone()
                if r is None:
                    return None
                return GoodsReceiptSnapshot(
                    goods_receipt_id=r["goods_receipt_id"],
                    tenant_id=r["tenant_id"],
                    purchase_order_id=r["purchase_order_id"],
                    store_id=r["store_id"],
                )

    def load_policy_state(self) -> PolicyState:
        """Read PlatformLimits and engaged KillSwitches from control.policies (fail-closed)."""
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT policy_id, kind, scope, target_id, value, status
                        FROM control.policies
                        WHERE (kind = 'platform_limits' AND status = 'active')
                           OR (kind = 'kill_switch' AND status = 'engaged')
                        ORDER BY updated_at DESC;
                        """
                    )
                    rows = cur.fetchall()
        except Exception:
            return PolicyState(available=False)

        platform_limits: PlatformLimitsSnapshot | None = None
        kill_switches: list[KillSwitchSnapshot] = []
        for r in rows:
            val = r["value"] if isinstance(r["value"], dict) else {}
            if r["kind"] == "platform_limits" and platform_limits is None:
                if (
                    "auto_pay_per_invoice_vnd" not in val
                    or "auto_pay_per_day_vnd" not in val
                ):
                    return PolicyState(available=False)
                platform_limits = PlatformLimitsSnapshot(
                    auto_pay_per_invoice_vnd=int(val["auto_pay_per_invoice_vnd"]),
                    auto_pay_per_day_vnd=int(val["auto_pay_per_day_vnd"]),
                )
            elif r["kind"] == "kill_switch":
                kill_switches.append(
                    KillSwitchSnapshot(
                        kill_switch_id=r["policy_id"],
                        scope=str(r["scope"] or ""),
                        target_id=r["target_id"],
                        indicator_kind=val.get("indicator_kind"),
                        value_hash=val.get("value_hash"),
                        reason=str(val.get("reason", "")),
                    )
                )

        if platform_limits is None:
            return PolicyState(available=False)

        return PolicyState(
            available=True,
            platform_limits=platform_limits,
            kill_switches=tuple(kill_switches),
        )

    def check_risk_signals(self, indicators: Sequence[IndicatorRef]) -> RiskSignals:
        if not indicators:
            return RiskSignals()

        pairs = [(ind.kind, ind.value_hash.lower()) for ind in indicators]
        kinds = [p[0] for p in pairs]
        hashes = [p[1] for p in pairs]

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT hb.indicator_kind, hb.value_hash
                    FROM risk.hard_blocks AS hb
                    JOIN unnest(%s::text[], %s::text[]) AS q(kind, value_hash)
                      ON hb.indicator_kind = q.kind
                     AND lower(hb.value_hash) = q.value_hash
                    WHERE hb.status = 'active';
                    """,
                    (kinds, hashes),
                )
                hard_hits = tuple(
                    IndicatorRef(kind=r["indicator_kind"], value_hash=r["value_hash"].lower())
                    for r in cur.fetchall()
                )

                cur.execute(
                    """
                    SELECT DISTINCT ca.indicator_kind, ca.value_hash
                    FROM risk.cross_alerts AS ca
                    JOIN unnest(%s::text[], %s::text[]) AS q(kind, value_hash)
                      ON ca.indicator_kind = q.kind
                     AND lower(ca.value_hash) = q.value_hash
                    WHERE ca.status = 'published';
                    """,
                    (kinds, hashes),
                )
                cross_hits = tuple(
                    IndicatorRef(kind=r["indicator_kind"], value_hash=r["value_hash"].lower())
                    for r in cur.fetchall()
                )

                matched_ids: set[str] = set()
                try:
                    cur.execute(
                        """
                        SELECT ind.indicator_id
                        FROM risk.indicators AS ind
                        JOIN unnest(%s::text[], %s::text[]) AS q(kind, value_hash)
                          ON ind.kind = q.kind
                         AND lower(ind.value_hash) = q.value_hash;
                        """,
                        (kinds, hashes),
                    )
                    matched_ids = {str(r["indicator_id"]) for r in cur.fetchall()}
                except psycopg.errors.UndefinedTable:
                    # risk.indicators is optional if kill switches store value_hash directly.
                    pass

        return RiskSignals(
            hard_block_hits=hard_hits,
            cross_alert_hits=cross_hits,
            matched_indicator_ids=frozenset(matched_ids),
        )
