"""In-memory FakePaymentRail supporting success, failures, timeouts, and conflicts."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from gate.domain.rules import VN_TZ
from gate.ids import new_id
from gate.ports.rail import (
    RailCardResult,
    RailConflictError,
    RailEscrowActionResult,
    RailEscrowHoldResult,
    RailNotFoundError,
    RailTimeoutError,
    RailTransferResult,
)


class FakePaymentRail:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.transfers: dict[str, tuple[tuple[Any, ...], RailTransferResult]] = {}
        self.cards: dict[str, tuple[tuple[Any, ...], RailCardResult]] = {}
        self.cards_by_id: dict[str, RailCardResult] = {}
        self.escrows: dict[str, tuple[tuple[Any, ...], RailEscrowHoldResult]] = {}
        self.escrows_by_id: dict[str, str] = {}  # rail_escrow_id -> status
        self.transfer_calls: list[dict[str, Any]] = []
        self.card_calls: list[dict[str, Any]] = []
        self.escrow_calls: list[dict[str, Any]] = []

        # Programmable fault injection
        self.fail_next_transfer_code: str | None = None
        self.timeout_next_transfer: bool = False
        self.timeout_get_transfer: bool = False
        self.fail_next_card_code: str | None = None
        self.timeout_next_card: bool = False
        self.issue_card_without_capture: bool = False
        self.timeout_next_escrow: bool = False
        self.timeout_next_release: bool = False
        self.fail_next_escrow_code: str | None = None
        self.now_fn = lambda: datetime(2026, 11, 26, 8, 32, 0, tzinfo=VN_TZ)

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
    ) -> RailTransferResult:
        fp = (from_wallet_id, bank_code, account_number, account_name, amount_vnd, memo)
        with self._lock:
            self.transfer_calls.append(
                {
                    "idempotency_key": idempotency_key,
                    "from_wallet_id": from_wallet_id,
                    "bank_code": bank_code,
                    "account_number": account_number,
                    "account_name": account_name,
                    "amount_vnd": amount_vnd,
                    "memo": memo,
                }
            )
            if self.timeout_next_transfer:
                self.timeout_next_transfer = False
                raise RailTimeoutError("Simulated transfer timeout")

            if idempotency_key in self.transfers:
                prev_fp, prev_res = self.transfers[idempotency_key]
                if prev_fp != fp:
                    raise RailConflictError("Transfer payload mismatch")
                return prev_res

            rtx_id = new_id("rtx")
            if self.fail_next_transfer_code is not None:
                code = self.fail_next_transfer_code
                self.fail_next_transfer_code = None
                res = RailTransferResult(
                    rail_txn_id=rtx_id,
                    status="failed",
                    failure_code=code,
                    settled_at=None,
                    raw_response={"rail_txn_id": rtx_id, "status": "failed", "failure_code": code},
                )
            else:
                ts = self.now_fn()
                res = RailTransferResult(
                    rail_txn_id=rtx_id,
                    status="settled",
                    failure_code=None,
                    settled_at=ts,
                    raw_response={
                        "rail_txn_id": rtx_id,
                        "status": "settled",
                        "settled_at": ts.isoformat(),
                    },
                )
            self.transfers[idempotency_key] = (fp, res)
            return res

    def get_transfer(self, idempotency_key: str) -> RailTransferResult:
        with self._lock:
            if self.timeout_get_transfer:
                raise RailTimeoutError("Simulated transfer poll timeout")
            if idempotency_key not in self.transfers:
                raise RailNotFoundError(f"Unknown transfer {idempotency_key}")
            return self.transfers[idempotency_key][1]

    def create_card(
        self,
        *,
        idempotency_key: str,
        from_wallet_id: str,
        merchant_id: str,
        amount_vnd: int,
        single_use: bool = True,
    ) -> RailCardResult:
        fp = (from_wallet_id, merchant_id, amount_vnd, single_use)
        with self._lock:
            self.card_calls.append(
                {
                    "idempotency_key": idempotency_key,
                    "from_wallet_id": from_wallet_id,
                    "merchant_id": merchant_id,
                    "amount_vnd": amount_vnd,
                    "single_use": single_use,
                }
            )
            if self.timeout_next_card:
                self.timeout_next_card = False
                raise RailTimeoutError("Simulated card timeout")

            if idempotency_key in self.cards:
                prev_fp, prev_res = self.cards[idempotency_key]
                if prev_fp != fp:
                    raise RailConflictError("Card payload mismatch")
                return prev_res

            if self.fail_next_card_code is not None:
                code = self.fail_next_card_code
                self.fail_next_card_code = None
                return RailCardResult(
                    card_id=None,
                    status="failed",
                    failure_code=code,
                    raw_response={"code": code},
                )

            card_id = new_id("crd")
            status = "issued" if self.issue_card_without_capture else "captured"
            self.issue_card_without_capture = False
            res = RailCardResult(
                card_id=card_id,
                last4="4821",
                status=status,
                raw_response={"card_id": card_id, "last4": "4821", "status": status},
            )
            self.cards[idempotency_key] = (fp, res)
            self.cards_by_id[card_id] = res
            return res

    def get_card(self, card_id: str) -> RailCardResult:
        with self._lock:
            if card_id not in self.cards_by_id:
                raise RailNotFoundError(f"Unknown card {card_id}")
            return self.cards_by_id[card_id]

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
    ) -> RailEscrowHoldResult:
        fp = (from_wallet_id, bank_code, account_number, account_name, amount_vnd, expires_on)
        with self._lock:
            self.escrow_calls.append(
                {
                    "op": "hold",
                    "idempotency_key": idempotency_key,
                    "from_wallet_id": from_wallet_id,
                    "bank_code": bank_code,
                    "account_number": account_number,
                    "account_name": account_name,
                    "amount_vnd": amount_vnd,
                    "expires_on": expires_on,
                }
            )
            if self.timeout_next_escrow:
                self.timeout_next_escrow = False
                raise RailTimeoutError("Simulated escrow hold timeout")

            if idempotency_key in self.escrows:
                prev_fp, prev_res = self.escrows[idempotency_key]
                if prev_fp != fp:
                    raise RailConflictError("Escrow payload mismatch")
                return prev_res

            if self.fail_next_escrow_code is not None:
                code = self.fail_next_escrow_code
                self.fail_next_escrow_code = None
                return RailEscrowHoldResult(
                    rail_escrow_id=None,
                    status="failed",
                    failure_code=code,
                    raw_response={"code": code},
                )

            rail_esc_id = new_id("resc")
            res = RailEscrowHoldResult(
                rail_escrow_id=rail_esc_id,
                status="held",
                raw_response={"rail_escrow_id": rail_esc_id, "status": "held"},
            )
            self.escrows[idempotency_key] = (fp, res)
            self.escrows_by_id[rail_esc_id] = "held"
            return res

    def release_escrow(
        self,
        *,
        rail_escrow_id: str,
        idempotency_key: str,
    ) -> RailEscrowActionResult:
        with self._lock:
            self.escrow_calls.append(
                {"op": "release", "rail_escrow_id": rail_escrow_id, "idempotency_key": idempotency_key}
            )
            if self.timeout_next_release:
                self.timeout_next_release = False
                raise RailTimeoutError("Simulated escrow release timeout")
            if rail_escrow_id not in self.escrows_by_id:
                return RailEscrowActionResult(status="failed", failure_code="NOT_FOUND")
            self.escrows_by_id[rail_escrow_id] = "released"
            return RailEscrowActionResult(status="released", raw_response={"status": "released"})

    def refund_escrow(
        self,
        *,
        rail_escrow_id: str,
        idempotency_key: str,
    ) -> RailEscrowActionResult:
        with self._lock:
            self.escrow_calls.append(
                {"op": "refund", "rail_escrow_id": rail_escrow_id, "idempotency_key": idempotency_key}
            )
            if rail_escrow_id not in self.escrows_by_id:
                return RailEscrowActionResult(status="failed", failure_code="NOT_FOUND")
            self.escrows_by_id[rail_escrow_id] = "refunded"
            return RailEscrowActionResult(status="refunded", raw_response={"status": "refunded"})
