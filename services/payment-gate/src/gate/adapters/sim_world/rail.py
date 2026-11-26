"""PaymentRail adapter targeting sim-world (/sim/rails/*)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from gate.ports.rail import (
    RailCardResult,
    RailConflictError,
    RailEscrowActionResult,
    RailEscrowHoldResult,
    RailNotFoundError,
    RailTimeoutError,
    RailTransferResult,
)


def _extract_error_code(resp: httpx.Response, default: str) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict) and data.get("code"):
            return str(data["code"])
    except Exception:
        pass
    return default


class SimWorldPaymentRail:
    """HTTP adapter to sim-world /sim/rails/* (idempotency_key = intent_id or escrow_id)."""

    def __init__(
        self,
        *,
        sim_url: str,
        service_key: str,
        timeout_seconds: float = 5.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = sim_url.rstrip("/")
        self._headers = {"X-Service-Key": service_key} if service_key else {}
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def _request(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> httpx.Response:
        url = f"{self._base_url}{path}"
        try:
            return self._client.request(method, url, json=json_body, headers=self._headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise RailTimeoutError(f"Rail request {method} {path} timed out or failed: {exc}") from exc

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
        resp = self._request(
            "POST",
            "/rails/transfers",
            {
                "idempotency_key": idempotency_key,
                "from_wallet_id": from_wallet_id,
                "to": {
                    "bank_code": bank_code,
                    "account_number": account_number,
                    "account_name": account_name,
                },
                "amount_vnd": amount_vnd,
                "memo": memo,
            },
        )
        if resp.status_code == 409 and _extract_error_code(resp, "") == "IDEMPOTENCY_KEY_REUSED":
            raise RailConflictError("Transfer idempotency_key reused with different payload.")
        if resp.status_code >= 500:
            raise RailTimeoutError(f"Rail returned HTTP {resp.status_code}; transfer outcome unknown.")
        if resp.status_code >= 400:
            return RailTransferResult(
                rail_txn_id=None,
                status="failed",
                failure_code=_extract_error_code(resp, f"HTTP_{resp.status_code}"),
                raw_response=resp.json() if resp.content else None,
            )
        data = resp.json()
        settled_at = (
            datetime.fromisoformat(data["settled_at"]) if data.get("settled_at") else None
        )
        return RailTransferResult(
            rail_txn_id=data.get("rail_txn_id"),
            status="settled" if data.get("status") == "settled" else "failed",
            failure_code=data.get("failure_code"),
            settled_at=settled_at,
            raw_response=data,
        )

    def get_transfer(self, idempotency_key: str) -> RailTransferResult:
        resp = self._request("GET", f"/rails/transfers/{idempotency_key}")
        if resp.status_code == 404:
            raise RailNotFoundError(f"Transfer '{idempotency_key}' not found on rail.")
        if resp.status_code >= 500:
            raise RailTimeoutError(f"Rail returned HTTP {resp.status_code} on transfer lookup.")
        data = resp.json()
        settled_at = (
            datetime.fromisoformat(data["settled_at"]) if data.get("settled_at") else None
        )
        return RailTransferResult(
            rail_txn_id=data.get("rail_txn_id"),
            status="settled" if data.get("status") == "settled" else "failed",
            failure_code=data.get("failure_code"),
            settled_at=settled_at,
            raw_response=data,
        )

    def create_card(
        self,
        *,
        idempotency_key: str,
        from_wallet_id: str,
        merchant_id: str,
        amount_vnd: int,
        single_use: bool = True,
    ) -> RailCardResult:
        resp = self._request(
            "POST",
            "/rails/cards",
            {
                "idempotency_key": idempotency_key,
                "from_wallet_id": from_wallet_id,
                "merchant_id": merchant_id,
                "amount_vnd": amount_vnd,
                "single_use": single_use,
            },
        )
        if resp.status_code == 409:
            code = _extract_error_code(resp, "INVALID_STATE")
            if code == "IDEMPOTENCY_KEY_REUSED":
                raise RailConflictError("Card idempotency_key reused with different payload.")
            return RailCardResult(
                card_id=None,
                status="failed",
                failure_code="INSUFFICIENT_FUNDS" if code == "INVALID_STATE" else code,
                raw_response=resp.json() if resp.content else None,
            )
        if resp.status_code >= 500:
            raise RailTimeoutError(f"Rail returned HTTP {resp.status_code}; card outcome unknown.")
        if resp.status_code >= 400:
            return RailCardResult(
                card_id=None,
                status="failed",
                failure_code=_extract_error_code(resp, f"HTTP_{resp.status_code}"),
                raw_response=resp.json() if resp.content else None,
            )
        data = resp.json()
        return RailCardResult(
            card_id=data.get("card_id"),
            last4=data.get("last4"),
            status="captured" if data.get("status") == "captured" else "issued",
            raw_response=data,
        )

    def get_card(self, card_id: str) -> RailCardResult:
        resp = self._request("GET", f"/rails/cards/{card_id}")
        if resp.status_code == 404:
            raise RailNotFoundError(f"Card '{card_id}' not found on rail.")
        if resp.status_code >= 500:
            raise RailTimeoutError(f"Rail returned HTTP {resp.status_code} on card lookup.")
        data = resp.json()
        return RailCardResult(
            card_id=data.get("card_id"),
            status="captured" if data.get("status") == "captured" else "issued",
            raw_response=data,
        )

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
        resp = self._request(
            "POST",
            "/rails/escrows",
            {
                "idempotency_key": idempotency_key,
                "from_wallet_id": from_wallet_id,
                "to": {
                    "bank_code": bank_code,
                    "account_number": account_number,
                    "account_name": account_name,
                },
                "amount_vnd": amount_vnd,
                "expires_on": expires_on,
            },
        )
        if resp.status_code == 409:
            code = _extract_error_code(resp, "INVALID_STATE")
            if code == "IDEMPOTENCY_KEY_REUSED":
                raise RailConflictError("Escrow idempotency_key reused with different payload.")
            return RailEscrowHoldResult(
                rail_escrow_id=None,
                status="failed",
                failure_code="INSUFFICIENT_FUNDS" if code == "INVALID_STATE" else code,
                raw_response=resp.json() if resp.content else None,
            )
        if resp.status_code >= 500:
            raise RailTimeoutError(f"Rail returned HTTP {resp.status_code}; escrow hold unknown.")
        if resp.status_code >= 400:
            return RailEscrowHoldResult(
                rail_escrow_id=None,
                status="failed",
                failure_code=_extract_error_code(resp, f"HTTP_{resp.status_code}"),
                raw_response=resp.json() if resp.content else None,
            )
        data = resp.json()
        return RailEscrowHoldResult(
            rail_escrow_id=data.get("rail_escrow_id"),
            status="held",
            raw_response=data,
        )

    def release_escrow(
        self,
        *,
        rail_escrow_id: str,
        idempotency_key: str,
    ) -> RailEscrowActionResult:
        resp = self._request(
            "POST",
            f"/rails/escrows/{rail_escrow_id}:release",
            {"idempotency_key": idempotency_key},
        )
        if resp.status_code >= 500:
            raise RailTimeoutError(f"Rail returned HTTP {resp.status_code} on escrow release.")
        if resp.status_code >= 400:
            return RailEscrowActionResult(
                status="failed",
                failure_code=_extract_error_code(resp, f"HTTP_{resp.status_code}"),
                raw_response=resp.json() if resp.content else None,
            )
        return RailEscrowActionResult(status="released", raw_response=resp.json())

    def refund_escrow(
        self,
        *,
        rail_escrow_id: str,
        idempotency_key: str,
    ) -> RailEscrowActionResult:
        resp = self._request(
            "POST",
            f"/rails/escrows/{rail_escrow_id}:refund",
            {"idempotency_key": idempotency_key},
        )
        if resp.status_code >= 500:
            raise RailTimeoutError(f"Rail returned HTTP {resp.status_code} on escrow refund.")
        if resp.status_code >= 400:
            return RailEscrowActionResult(
                status="failed",
                failure_code=_extract_error_code(resp, f"HTTP_{resp.status_code}"),
                raw_response=resp.json() if resp.content else None,
            )
        return RailEscrowActionResult(status="refunded", raw_response=resp.json())
