"""Pure state machine transition guards for PaymentIntent and Escrow."""

from __future__ import annotations

from paymatch_contracts.gate import EscrowStatus, PaymentIntentStatus

from gate.domain.models import InvalidStateTransitionError

_INTENT_TRANSITIONS: dict[PaymentIntentStatus, frozenset[PaymentIntentStatus]] = {
    PaymentIntentStatus.created: frozenset(
        {PaymentIntentStatus.authorized, PaymentIntentStatus.denied}
    ),
    PaymentIntentStatus.authorized: frozenset(
        {
            PaymentIntentStatus.executing,
            PaymentIntentStatus.expired,
            PaymentIntentStatus.denied,
        }
    ),
    PaymentIntentStatus.executing: frozenset(
        {PaymentIntentStatus.settled, PaymentIntentStatus.failed}
    ),
    PaymentIntentStatus.settled: frozenset(),
    PaymentIntentStatus.failed: frozenset(),
    PaymentIntentStatus.expired: frozenset(),
    PaymentIntentStatus.denied: frozenset(),
}

_ESCROW_TRANSITIONS: dict[EscrowStatus, frozenset[EscrowStatus]] = {
    EscrowStatus.pending: frozenset({EscrowStatus.held, EscrowStatus.failed}),
    EscrowStatus.held: frozenset({EscrowStatus.released, EscrowStatus.refunded}),
    EscrowStatus.released: frozenset(),
    EscrowStatus.refunded: frozenset(),
    EscrowStatus.failed: frozenset(),
}


def can_transition_intent(
    current: PaymentIntentStatus, target: PaymentIntentStatus
) -> bool:
    return target in _INTENT_TRANSITIONS[current]


def require_intent_transition(
    current: PaymentIntentStatus, target: PaymentIntentStatus
) -> None:
    if not can_transition_intent(current, target):
        raise InvalidStateTransitionError(
            f"Cannot transition PaymentIntent from '{current.value}' to '{target.value}'.",
            current_status=current.value,
        )


def can_transition_escrow(current: EscrowStatus, target: EscrowStatus) -> bool:
    return target in _ESCROW_TRANSITIONS[current]


def require_escrow_transition(current: EscrowStatus, target: EscrowStatus) -> None:
    if not can_transition_escrow(current, target):
        raise InvalidStateTransitionError(
            f"Cannot transition Escrow from '{current.value}' to '{target.value}'.",
            current_status=current.value,
        )
