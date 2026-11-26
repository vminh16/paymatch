"""Serializers mapping domain records to generated paymatch_contracts Pydantic v2 models."""

from __future__ import annotations

from paymatch_contracts import Escrow as EscrowContract
from paymatch_contracts.gate import (
    EvaluateResponse,
    GateReason,
    PaymentIntent,
    PaymentIntentPage,
    PaymentIntentRail,
)

from gate.domain.models import (
    EscrowRecord,
    EvaluationResult,
    GateReasonItem,
    PaymentIntentRecord,
)


def to_gate_reason(item: GateReasonItem) -> GateReason:
    return GateReason(code=item.code, layer=item.layer, detail=item.detail)


def to_evaluate_response(res: EvaluationResult) -> EvaluateResponse:
    return EvaluateResponse(
        decision=res.decision,
        allowed_methods=list(res.allowed_methods),
        verification_required=res.verification_required,
        intent_hash=res.intent_hash,
        payee_account_id=res.payee_account_id,
        amount_vnd=res.amount_vnd,
        channel=res.channel,
        reasons=[to_gate_reason(r) for r in res.reasons],
        evaluated_at=res.evaluated_at,
    )


def to_payment_intent(rec: PaymentIntentRecord) -> PaymentIntent:
    return PaymentIntent(
        payment_intent_id=rec.payment_intent_id,
        tenant_id=rec.tenant_id,
        invoice_id=rec.invoice_id,
        purchase_order_id=rec.purchase_order_id,
        intent_hash=rec.intent_hash,
        approval_id=rec.approval_id,
        payee_account_id=rec.payee_account_id,
        channel=rec.channel,
        amount_vnd=rec.amount_vnd,
        status=rec.status,
        gate_reasons=[to_gate_reason(r) for r in rec.gate_reasons],
        rail=PaymentIntentRail(
            rail_txn_id=rec.rail_txn_id,
            failure_code=rec.failure_code,
        ),
        transfer_memo=rec.transfer_memo,
        authorized_at=rec.authorized_at,
        executed_at=rec.executed_at,
        settled_at=rec.settled_at,
        expires_at=rec.expires_at,
        created_at=rec.created_at,
    )


def to_payment_intent_page(
    items: list[PaymentIntentRecord], next_cursor: str | None
) -> PaymentIntentPage:
    return PaymentIntentPage(
        items=[to_payment_intent(i) for i in items],
        next_cursor=next_cursor,
    )


def to_escrow(rec: EscrowRecord) -> EscrowContract:
    return EscrowContract.model_validate(
        {
            "escrow_id": rec.escrow_id,
            "purchase_order_id": rec.purchase_order_id,
            "vendor_account_id": rec.vendor_account_id,
            "amount_vnd": rec.amount_vnd,
            "status": rec.status.value,
            "source_invoice_id": rec.source_invoice_id,
            "release_invoice_id": rec.release_invoice_id,
            "goods_receipt_id": rec.goods_receipt_id,
            "expires_on": rec.expires_on.isoformat(),
            "created_at": rec.created_at.isoformat(),
            "released_at": rec.released_at.isoformat() if rec.released_at else None,
            "refunded_at": rec.refunded_at.isoformat() if rec.refunded_at else None,
        }
    )
