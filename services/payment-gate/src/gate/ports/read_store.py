"""Read-only port for reading core, control, and risk schemas."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from gate.domain.models import (
    ApprovalSnapshot,
    GoodsReceiptSnapshot,
    IndicatorRef,
    InvoiceSnapshot,
    MandateSnapshot,
    PolicyState,
    PurchaseOrderSnapshot,
    RiskSignals,
    VendorAccountSnapshot,
    VendorSnapshot,
)


class CoreReadStore(Protocol):
    def check_required_relations(self) -> bool:
        """Verify all required core/control/risk relations are readable."""
        ...

    def get_tenant_wallet_id(self, tenant_id: str) -> str | None: ...

    def is_tenant_owner(self, tenant_id: str, user_id: str) -> bool: ...

    def get_invoice(self, invoice_id: str) -> InvoiceSnapshot | None: ...

    def get_vendor(self, tenant_id: str, vendor_id: str) -> VendorSnapshot | None: ...

    def get_vendor_by_tax_id(self, tenant_id: str, tax_id: str) -> VendorSnapshot | None: ...

    def list_vendor_accounts(
        self, tenant_id: str, vendor_id: str
    ) -> tuple[VendorAccountSnapshot, ...]: ...

    def get_vendor_account(
        self, tenant_id: str, vendor_account_id: str
    ) -> VendorAccountSnapshot | None: ...

    def get_latest_mandate(self, tenant_id: str) -> MandateSnapshot | None: ...

    def is_vendor_suspended(self, tenant_id: str, vendor_id: str) -> bool: ...

    def get_approval(self, approval_id: str) -> ApprovalSnapshot | None: ...

    def get_latest_completed_job_id(self, tenant_id: str, invoice_id: str) -> str | None: ...

    def get_purchase_order(self, purchase_order_id: str) -> PurchaseOrderSnapshot | None: ...

    def get_goods_receipt(self, goods_receipt_id: str) -> GoodsReceiptSnapshot | None: ...

    def load_policy_state(self) -> PolicyState:
        """Read PlatformLimits and engaged KillSwitches from control.policies (fail-closed)."""
        ...

    def check_risk_signals(self, indicators: Sequence[IndicatorRef]) -> RiskSignals:
        """Query risk.indicators, risk.hard_blocks, risk.cross_alerts.

        MUST raise PolicyUnavailableError if any required risk table is unreadable (B6 fail-closed).
        """
        ...
