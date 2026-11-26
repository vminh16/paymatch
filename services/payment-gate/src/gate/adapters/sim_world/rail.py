"""PaymentRail adapter targeting sim-world (/sim/rails/*) with strict schema validation (B3).

CRITICAL (B3):
  - ONLY an explicit schema-valid rail outcome for the original operation finalizes as `failed`.
  - HTTP 401/403/400/404/409(IDEMPOTENCY_KEY_REUSED)/5xx, network errors, timeouts, and
    malformed responses ALWAYS raise RailAmbiguousError so Gate keeps the claim & budget
    reservation and alerts after the stuck threshold.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from gate.ports.rail import (
    RailAmbiguousError,
    RailCardResult,
    RailConflictError,
    RailEscrowActionResult,
    RailEscrowHoldResult,
    RailNotFoundError,
    RailTimeoutError,
    RailTransferResult,
)

# Strict Pydantic models matching contracts/openapi/sim-world.yaml /sim/rails/* response schemas.


class _SimTransferResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rail_txn_id: str
    status: Literal["settled", "failed"]
    failure_code: Literal[
        "INSUFFICIENT_FUNDS", "ACCOUNT_NOT_FOUND", "NAME_MISMATCH", "RAIL_DOWN"
    ] | None = None
    settled_at: datetime | None = None


class _SimCreateCardResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    card_id: str
    last4: str
    status: Literal["issued", "captured"]


class _SimCardDetailResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    card_id: str
    status: Literal["issued", "captured"]


class _SimCreateEscrowResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rail_escrow_id: str
    status: Literal["held"]


class _SimEscrowActionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: Literal["released", "refunded"]


class _SimProblem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str
    title: str = ""
    detail: str = ""


def _parse_json_or_ambiguous(resp: httpx.Response, label: str) -> dict[str, Any]:
    try:
        data = resp.json()
    except Exception as exc:
        raise RailAmbiguousError(f"Malformed JSON from rail on {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise RailAmbiguousError(f"Expected JSON object from rail on {label}.")
    return data


def _is_explicit_insufficient_balance(resp: httpx.Response) -> bool:
    """Only sim-world's explicit 409 INVALID_STATE for insufficient wallet balance is a non-ambiguous rejection."""
    if resp.status_code != 409:
        return False
    try:
        prob = _SimProblem.model_validate(resp.json())
    except Exception:
        return False
    if prob.code == "IDEMPOTENCY_KEY_REUSED":
        raise RailConflictError("Rail reported 409 IDEMPOTENCY_KEY_REUSED (ambiguous).")
    text = f"{prob.title} {prob.detail}".lower()
    return prob.code == "INVALID_STATE" and ("insufficient" in text and "balance" in text)


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

    def _request(
        self, method: str, path: str, json_body: dict[str, Any] | None = None
    ) -> httpx.Response:
        url = f"{self._base_url}{path}"
        try:
            return self._client.request(method, url, json=json_body, headers=self._headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise RailTimeoutError(
                f"Rail request {method} {path} timed out or failed: {exc}"
            ) from exc

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
        if resp.status_code != 200:
            if resp.status_code == 409:
                try:
                    prob = _SimProblem.model_validate(resp.json())
                    if prob.code == "IDEMPOTENCY_KEY_REUSED":
                        raise RailConflictError("Transfer idempotency_key reused with different payload.")
                except RailConflictError:
                    raise
                except Exception:
                    pass
            raise RailAmbiguousError(
                f"Ambiguous HTTP {resp.status_code} from POST /rails/transfers; keeping executing."
            )

        raw = _parse_json_or_ambiguous(resp, "POST /rails/transfers")
        try:
            parsed = _SimTransferResponse.model_validate(raw)
        except ValidationError as exc:
            raise RailAmbiguousError(f"Invalid TransferResponse schema from rail: {exc}") from exc

        if parsed.status == "failed" and not parsed.failure_code:
            raise RailAmbiguousError("Rail returned failed transfer without explicit failure_code.")
        return RailTransferResult(
            rail_txn_id=parsed.rail_txn_id,
            status=parsed.status,
            failure_code=parsed.failure_code,
            settled_at=parsed.settled_at,
            raw_response=raw,
        )

    def get_transfer(self, idempotency_key: str) -> RailTransferResult:
        resp = self._request("GET", f"/rails/transfers/{idempotency_key}")
        if resp.status_code == 404:
            raise RailNotFoundError(f"Transfer '{idempotency_key}' not found on rail.")
        if resp.status_code != 200:
            raise RailAmbiguousError(
                f"Ambiguous HTTP {resp.status_code} from GET /rails/transfers/{idempotency_key}."
            )
        raw = _parse_json_or_ambiguous(resp, "GET /rails/transfers")
        try:
            parsed = _SimTransferResponse.model_validate(raw)
        except ValidationError as exc:
            raise RailAmbiguousError(f"Invalid TransferResponse schema on GET: {exc}") from exc
        if parsed.status == "failed" and not parsed.failure_code:
            raise RailAmbiguousError("Rail returned failed transfer without explicit failure_code.")
        return RailTransferResult(
            rail_txn_id=parsed.rail_txn_id,
            status=parsed.status,
            failure_code=parsed.failure_code,
            settled_at=parsed.settled_at,
            raw_response=raw,
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
        if resp.status_code != 200:
            if _is_explicit_insufficient_balance(resp):
                return RailCardResult(
                    card_id=None,
                    status="failed",
                    failure_code="INSUFFICIENT_FUNDS",
                    raw_response=resp.json(),
                )
            raise RailAmbiguousError(
                f"Ambiguous HTTP {resp.status_code} from POST /rails/cards; keeping executing."
            )

        raw = _parse_json_or_ambiguous(resp, "POST /rails/cards")
        try:
            parsed = _SimCreateCardResponse.model_validate(raw)
        except ValidationError as exc:
            raise RailAmbiguousError(f"Invalid CreateCardResponse schema from rail: {exc}") from exc
        return RailCardResult(
            card_id=parsed.card_id,
            last4=parsed.last4,
            status=parsed.status,
            raw_response=raw,
        )

    def get_card(self, card_id: str) -> RailCardResult:
        resp = self._request("GET", f"/rails/cards/{card_id}")
        if resp.status_code == 404:
            raise RailNotFoundError(f"Card '{card_id}' not found on rail.")
        if resp.status_code != 200:
            raise RailAmbiguousError(
                f"Ambiguous HTTP {resp.status_code} from GET /rails/cards/{card_id}."
            )
        raw = _parse_json_or_ambiguous(resp, "GET /rails/cards")
        try:
            parsed = _SimCardDetailResponse.model_validate(raw)
        except ValidationError as exc:
            raise RailAmbiguousError(f"Invalid CardDetailResponse schema from rail: {exc}") from exc
        return RailCardResult(
            card_id=parsed.card_id,
            status=parsed.status,
            raw_response=raw,
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
        if resp.status_code != 200:
            if _is_explicit_insufficient_balance(resp):
                return RailEscrowHoldResult(
                    rail_escrow_id=None,
                    status="failed",
                    failure_code="INSUFFICIENT_FUNDS",
                    raw_response=resp.json(),
                )
            raise RailAmbiguousError(
                f"Ambiguous HTTP {resp.status_code} from POST /rails/escrows; keeping pending."
            )

        raw = _parse_json_or_ambiguous(resp, "POST /rails/escrows")
        try:
            parsed = _SimCreateEscrowResponse.model_validate(raw)
        except ValidationError as exc:
            raise RailAmbiguousError(f"Invalid CreateEscrowResponse schema from rail: {exc}") from exc
        return RailEscrowHoldResult(
            rail_escrow_id=parsed.rail_escrow_id,
            status=parsed.status,
            raw_response=raw,
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
        if resp.status_code != 200:
            raise RailAmbiguousError(
                f"Ambiguous HTTP {resp.status_code} from POST /rails/escrows/{rail_escrow_id}:release."
            )
        raw = _parse_json_or_ambiguous(resp, "POST /rails/escrows:release")
        try:
            parsed = _SimEscrowActionResponse.model_validate(raw)
        except ValidationError as exc:
            raise RailAmbiguousError(f"Invalid EscrowActionResponse schema on release: {exc}") from exc
        if parsed.status != "released":
            raise RailAmbiguousError(f"Unexpected status '{parsed.status}' on escrow release.")
        return RailEscrowActionResult(status="released", raw_response=raw)

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
        if resp.status_code != 200:
            raise RailAmbiguousError(
                f"Ambiguous HTTP {resp.status_code} from POST /rails/escrows/{rail_escrow_id}:refund."
            )
        raw = _parse_json_or_ambiguous(resp, "POST /rails/escrows:refund")
        try:
            parsed = _SimEscrowActionResponse.model_validate(raw)
        except ValidationError as exc:
            raise RailAmbiguousError(f"Invalid EscrowActionResponse schema on refund: {exc}") from exc
        if parsed.status != "refunded":
            raise RailAmbiguousError(f"Unexpected status '{parsed.status}' on escrow refund.")
        return RailEscrowActionResult(status="refunded", raw_response=raw)
