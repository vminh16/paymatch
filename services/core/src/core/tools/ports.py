"""Ports for external tool backends (sim-world and payment-gate)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class UpstreamToolError(Exception):
    """Raised by adapters when an external service times out or fails (mapped to ToolResult.error)."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        partial_output: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code  # UPSTREAM_TIMEOUT | UPSTREAM_UNAVAILABLE | NOT_FOUND
        self.detail = detail
        self.partial_output = partial_output


class SimWorldToolPort(Protocol):
    def get_inbox_messages(
        self, *, mailbox: str, from_address: str | None = None, since: str | None = None
    ) -> list[dict[str, Any]]: ...

    def get_chat_threads(
        self, *, tenant_ref: str, counterparty_phone: str | None = None
    ) -> list[dict[str, Any]]: ...

    def get_chat_messages(
        self, *, thread_id: str, since: str | None = None
    ) -> list[dict[str, Any]]: ...

    def check_simo_indicator(self, *, kind: str, value_hash: str) -> dict[str, Any]: ...

    def lookup_einvoice_portal(
        self, *, seller_tax_id: str, symbol: str, number: str
    ) -> dict[str, Any]: ...

    def lookup_taxpayer(self, *, tax_id: str) -> dict[str, Any] | None: ...

    def lookup_tax_risk_list(self, *, tax_id: str) -> dict[str, Any]: ...

    def get_momo_revenue(self, *, wallet_id: str, store_ref: str, month: str) -> dict[str, Any]: ...

    def get_wallet_balance(self, *, wallet_id: str) -> dict[str, Any]: ...

    def reset_scenario(self, *, dataset: str = "demo", seed: int = 42) -> dict[str, Any]: ...


@dataclass(frozen=True)
class GateEvaluation:
    decision: str  # ALLOW | REQUIRE_APPROVAL | DENY
    allowed_methods: list[str]
    verification_required: bool
    intent_hash: str
    payee_account_id: str | None
    amount_vnd: int
    channel: str
    reasons: list[dict[str, Any]]
    evaluated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "allowed_methods": self.allowed_methods,
            "verification_required": self.verification_required,
            "intent_hash": self.intent_hash,
            "payee_account_id": self.payee_account_id,
            "amount_vnd": self.amount_vnd,
            "channel": self.channel,
            "reasons": self.reasons,
            "evaluated_at": self.evaluated_at,
        }


class GateClientPort(Protocol):
    def evaluate_invoice(self, *, invoice_id: str, tenant_id: str) -> GateEvaluation: ...

    def get_daily_budget(self, *, tenant_id: str, date_str: str) -> dict[str, Any]: ...

    def create_intent(self, *, invoice_id: str, approval_id: str) -> dict[str, Any]: ...

    def execute_intent(self, *, payment_intent_id: str) -> dict[str, Any]: ...

    def cancel_intent(self, *, payment_intent_id: str, reason: str) -> dict[str, Any]: ...

    def list_intents(
        self, *, tenant_id: str, invoice_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]: ...
