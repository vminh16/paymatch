# generated — do not edit

from __future__ import annotations

from enum import StrEnum


class InvoiceStatus(StrEnum):
    new = 'new'
    investigating = 'investigating'
    auto_pay_eligible = 'auto_pay_eligible'
    pending_approval = 'pending_approval'
    blocked = 'blocked'
    approved = 'approved'
    scheduled = 'scheduled'
    paying = 'paying'
    paid = 'paid'
    payment_failed = 'payment_failed'
    escrow_held = 'escrow_held'
    rejected = 'rejected'
