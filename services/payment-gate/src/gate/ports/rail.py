"""PaymentRail port interface and typed rail outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol


class RailTimeoutError(Exception):
    """Raised when the payment rail does not respond in time (outcome UNKNOWN — never mark failed)."""


class RailConflictError(Exception):
    """Raised when the rail reports 409 IDEMPOTENCY_KEY_REUSED (payload mismatch)."""


class RailNotFoundError(Exception):
    """Raised when a polled transfer/card/escrow does not exist on the rail (404)."""


@dataclass(frozen=True, slots=True)
class RailTransferResult:
    rail_txn_id: str | None
    status: Literal["settled", "failed"]
    failure_code: str | None = None
    settled_at: datetime | None = None
    raw_response: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class RailCardResult:
    card_id: str | None
    status: Literal["issued", "captured", "failed"]
    last4: str | None = None
    failure_code: str | None = None
    raw_response: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class RailEscrowHoldResult:
    rail_escrow_id: str | None
    status: Literal["held", "failed"]
    failure_code: str | None = None
    raw_response: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class RailEscrowActionResult:
    status: Literal["released", "refunded", "failed"]
    failure_code: str | None = None
    raw_response: dict[str, Any] | None = None


class PaymentRail(Protocol):
    def create_transfer(
        self,
        *,
        idempotency_key: str,
        from_wallet_id: str,
        bank_code: str,
        account_number: str,
        account_name: str,
        amount_vnd: int,
        memo: str,
    ) -> RailTransferResult: ...

    def get_transfer(self, idempotency_key: str) -> RailTransferResult: ...

    def create_card(
        self,
        *,
        idempotency_key: str,
        from_wallet_id: str,
        merchant_id: str,
        amount_vnd: int,
        single_use: bool = True,
    ) -> RailCardResult: ...

    def get_card(self, card_id: str) -> RailCardResult: ...

    def create_escrow(
        self,
        *,
        idempotency_key: str,
        from_wallet_id: str,
        bank_code: str,
        account_number: str,
        account_name: str,
        amount_vnd: int,
        expires_on: str,
    ) -> RailEscrowHoldResult: ...

    def release_escrow(
        self,
        *,
        rail_escrow_id: str,
        idempotency_key: str,
    ) -> RailEscrowActionResult: ...

    def refund_escrow(
        self,
        *,
        rail_escrow_id: str,
        idempotency_key: str,
    ) -> RailEscrowActionResult: ...
