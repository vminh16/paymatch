"""Shared test constants and factory helpers for payment-gate tests."""

from __future__ import annotations

import json
import pathlib
from datetime import datetime
from typing import Any

import jsonschema
from referencing import Registry, Resource

from gate.domain.hashing import compute_escrow_intent_hash, compute_invoice_intent_hash
from gate.domain.models import (
    ApprovalSnapshot,
    BulkApprovableRule,
    ChannelRule,
    InvoiceSnapshot,
    MandateSnapshot,
    PurchaseOrderSnapshot,
    VendorAccountSnapshot,
    VendorSnapshot,
    VerificationRecord,
)
from gate.domain.rules import VN_TZ

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMAS_DIR = ROOT / "contracts" / "schemas"
EVENTS_DIR = ROOT / "contracts" / "events"

# Deterministic valid Crockford Base32 IDs (matching contract regexes)
TENANT_A = "ten_01M88D3C06B97Y4G0S9W8BVKNG"
TENANT_B = "ten_01M88AXX2KPMD46VQQTDDH040J"
WALLET_A = "wal_01M88AWF62TJ28TZPAQDR9KT4H"
STORE_01 = "sto_01M8890N9Y7RRHWTHDZPHWM785"
USER_OWNER = "usr_01M885AXP309SER6BAC46N5FJT"

VENDOR_COFFEE = "ven_01M88CGAPGH0KRTMDHYVB4JF3C"
ACC_COFFEE = "vac_01M885170DEVTBBKXKDK90DBAS"

VENDOR_POS = "ven_01M88EEW45VVABHHJ1TRXJQM4V"
ACC_POS_CARD = "vac_01M886BQPPTZR4D9H21Q5CM9PT"

VENDOR_CUPS = "ven_01M8876N5RKZ3A9GRME2NFSMH0"
ACC_CUPS = "vac_01M883RZCB3B6Y8WG7WQVC1BBY"

VENDOR_SYRUP = "ven_01M88SYRVP0000000000000001"
ACC_SYRUP_ESCROW = "vac_01M88SYRVPESCR0W0000000001"

INV_COFFEE = "inv_01M8808XXD8017SJ9NTGTNC48Y"
INV_COFFEE_2 = "inv_01M8808XXD8017SJ9NTGTNC48Z"
INV_CUPS = "inv_01M882P8NTCDKGE2KVFMBTS5RK"
INV_POS = "inv_01M88P0S000000000000000001"
INV_SYRUP = "inv_01M883YAYXMNBVDV7CSN4MH4C4"

JOB_01 = "job_01M882G20CAMSQWE8SVGP02RHD"
JOB_02 = "job_01M882G20CAMSQWE8SVGP02RHE"

APV_01 = "apv_01M885AXP309SER6BAC46N5FJT"
APV_02 = "apv_01M883BRJ9DP97B91S0CMK8PZJ"
APV_ESC_CREATE = "apv_01M88ESCR0WCREATE000000001"
APV_ESC_CREATE_2 = "apv_01M88ESCR0WCREATE000000002"
APV_ESC_RELEASE = "apv_01M88ESCR0WRE1EASE00000001"

PO_01 = "po_01M886F6SP0ZHE2X89GQ1TRJSP"
GRN_01 = "grn_01M88AR4Z4F0HA2R6KPFXBFX7S"
GRN_OTHER = "grn_01M88AR4Z4F0HA2R6KPFXBFX7T"

DOC_SHA_COFFEE = "a" * 64
DOC_SHA_CUPS = "7bd877246110eed1e0a0e70cc74ab73739ea96a2cfd558102668d2f425de9995"
DOC_SHA_SYRUP = "4631d65520ef4af697f97229a23e8b8d3d0f68910c71a3e6f19b6d18be4b2cfb"

NOW_VN = datetime(2026, 11, 26, 8, 30, 0, tzinfo=VN_TZ)

SERVICE_KEYS = {
    "merchant-api": "key-merchant-api",
    "core-worker": "key-core-worker",
    "internal-api": "key-internal-api",
    "console-api": "key-console-api",
}


def make_default_mandate(
    *,
    tenant_id: str = TENANT_A,
    mode: str = "auto_pay",
    per_invoice_vnd: int = 30_000_000,
    per_day_vnd: int = 50_000_000,
    auto_pay_vendor_ids: frozenset[str] | None = None,
    window_start: str = "07:00",
    window_end: str = "22:00",
) -> MandateSnapshot:
    return MandateSnapshot(
        mandate_id="man_01M88C0Z95W938KHTM1EWXVCHQ",
        tenant_id=tenant_id,
        version=1,
        mode=mode,
        per_invoice_vnd=per_invoice_vnd,
        per_day_vnd=per_day_vnd,
        auto_pay_vendor_ids=(
            auto_pay_vendor_ids
            if auto_pay_vendor_ids is not None
            else frozenset({VENDOR_COFFEE, VENDOR_POS})
        ),
        channel_rules=(ChannelRule(invoice_type="software", channel="virtual_card"),),
        bulk_approvable=(
            BulkApprovableRule(reason_codes=("NON_XML_SOURCE",), max_amount_vnd=2_000_000),
        ),
        auto_pay_window_start=window_start,
        auto_pay_window_end=window_end,
    )


def make_coffee_vendor() -> tuple[VendorSnapshot, VendorAccountSnapshot]:
    vendor = VendorSnapshot(
        vendor_id=VENDOR_COFFEE,
        tenant_id=TENANT_A,
        name="CÔNG TY TNHH CÀ PHÊ RANG MỘC TÂY NGUYÊN",
        tax_id="0999010001",
        phone_on_file="0280001001",
        status="active",
    )
    account = VendorAccountSnapshot(
        vendor_account_id=ACC_COFFEE,
        vendor_id=VENDOR_COFFEE,
        tenant_id=TENANT_A,
        kind="bank_account",
        bank_code="VNMB01",
        bank_name="Ngân hàng Mẫu Á Châu",
        account_number="990010000001",
        merchant_id=None,
        account_name="CONG TY TNHH CA PHE RANG MOC TAY NGUYEN",
        status="verified",
    )
    return vendor, account


def make_pos_vendor() -> tuple[VendorSnapshot, VendorAccountSnapshot]:
    vendor = VendorSnapshot(
        vendor_id=VENDOR_POS,
        tenant_id=TENANT_A,
        name="CÔNG TY TNHH PHẦN MỀM BÁN HÀNG SAO VIỆT",
        tax_id="0999010032",
        phone_on_file="0280001032",
        status="active",
    )
    account = VendorAccountSnapshot(
        vendor_account_id=ACC_POS_CARD,
        vendor_id=VENDOR_POS,
        tenant_id=TENANT_A,
        kind="card_merchant",
        bank_code=None,
        bank_name=None,
        account_number=None,
        merchant_id="mrc_pos_cloud_01",
        account_name="CONG TY TNHH PHAN MEM BAN HANG SAO VIET",
        status="verified",
    )
    return vendor, account


def make_syrup_escrow_vendor() -> tuple[VendorSnapshot, VendorAccountSnapshot, PurchaseOrderSnapshot]:
    vendor = VendorSnapshot(
        vendor_id=VENDOR_SYRUP,
        tenant_id=TENANT_A,
        name="CÔNG TY TNHH THƯƠNG MẠI NGÂN HÀ MẪU",
        tax_id="0999090001",
        phone_on_file="0280009001",
        status="active",
    )
    account = VendorAccountSnapshot(
        vendor_account_id=ACC_SYRUP_ESCROW,
        vendor_id=VENDOR_SYRUP,
        tenant_id=TENANT_A,
        kind="bank_account",
        bank_code="VNMB02",
        bank_name="Ngân hàng Mẫu Nam Việt",
        account_number="990090000002",
        merchant_id=None,
        account_name="CONG TY TNHH THUONG MAI NGAN HA MAU",
        status="escrow_only",
    )
    po = PurchaseOrderSnapshot(
        purchase_order_id=PO_01,
        tenant_id=TENANT_A,
        vendor_id=VENDOR_SYRUP,
        store_id=STORE_01,
        total_vnd=8_800_000,
        status="open",
    )
    return vendor, account, po


def make_coffee_invoice(
    *,
    invoice_id: str = INV_COFFEE,
    amount_vnd: int = 26_500_000,
    status: str = "scheduled",
    severity: str | None = "green",
    reason_codes: tuple[str, ...] = ("OK",),
    purchase_order_id: str | None = None,
) -> InvoiceSnapshot:
    return InvoiceSnapshot(
        invoice_id=invoice_id,
        tenant_id=TENANT_A,
        vendor_id=VENDOR_COFFEE,
        purchase_order_id=purchase_order_id,
        seller_tax_id="0999010001",
        symbol="1C26TTN",
        number="00001425",
        invoice_type="goods",
        total_vnd=amount_vnd,
        status=status,
        severity=severity,
        reason_codes=reason_codes,
        document_sha256=DOC_SHA_COFFEE,
    )


def make_approval_for_invoice(
    invoice: InvoiceSnapshot,
    *,
    approval_id: str = APV_01,
    payee_account_id: str = ACC_COFFEE,
    channel: str = "bank_transfer",
    method: str = "mandate",
    status: str = "active",
    job_id: str | None = JOB_01,
    verification: VerificationRecord | None = None,
    intent_hash: str | None = None,
) -> ApprovalSnapshot:
    assert invoice.total_vnd is not None
    ih = intent_hash or compute_invoice_intent_hash(
        invoice_id=invoice.invoice_id,
        document_sha256=invoice.document_sha256,
        payee_account_id=payee_account_id,
        amount_vnd=invoice.total_vnd,
        channel=channel,
    )
    return ApprovalSnapshot(
        approval_id=approval_id,
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.invoice_id,
        purchase_order_id=None,
        source_invoice_id=None,
        job_id=job_id,
        status=status,
        method=method,
        amount_vnd=invoice.total_vnd,
        payee_account_id=payee_account_id,
        channel=channel,
        intent_hash=ih,
        approver_user_id=None if method == "mandate" else USER_OWNER,
        mandate_version=1,
        verification=verification,
    )


def make_escrow_create_approval(
    po: PurchaseOrderSnapshot,
    *,
    approval_id: str = APV_ESC_CREATE,
    payee_account_id: str = ACC_SYRUP_ESCROW,
    amount_vnd: int | None = None,
    source_invoice_id: str | None = INV_SYRUP,
    status: str = "active",
    verification: VerificationRecord | None = None,
) -> ApprovalSnapshot:
    amt = amount_vnd if amount_vnd is not None else po.total_vnd
    ih = compute_escrow_intent_hash(
        purchase_order_id=po.purchase_order_id,
        payee_account_id=payee_account_id,
        amount_vnd=amt,
    )
    return ApprovalSnapshot(
        approval_id=approval_id,
        tenant_id=po.tenant_id,
        invoice_id=None,
        purchase_order_id=po.purchase_order_id,
        source_invoice_id=source_invoice_id,
        job_id=None,
        status=status,
        method="single",
        amount_vnd=amt,
        payee_account_id=payee_account_id,
        channel="escrow",
        intent_hash=ih,
        approver_user_id=USER_OWNER,
        verification=verification,
    )


def validate_outbox_event_against_contract(event_row: dict[str, Any]) -> None:
    """Validate an outbox row envelope + data against contracts/events/<type>.schema.json."""
    ev_type = event_row["type"]
    schema_path = EVENTS_DIR / f"{ev_type}.schema.json"
    assert schema_path.is_file(), f"No event contract for {ev_type}"

    resources: list[tuple[str, Resource]] = []
    for p in sorted(SCHEMAS_DIR.glob("*.schema.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        res = Resource.from_contents(s)
        resources.append((p.resolve().as_uri(), res))
        if "$id" in s:
            resources.append((s["$id"], res))
    for p in sorted(EVENTS_DIR.glob("*.schema.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        res = Resource.from_contents(s)
        resources.append((p.resolve().as_uri(), res))
        if "$id" in s:
            resources.append((s["$id"], res))
    registry = Registry().with_resources(resources)

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    envelope = {
        "event_id": event_row["event_id"],
        "type": event_row["type"],
        "schema_version": event_row["schema_version"],
        "occurred_at": (
            event_row["occurred_at"].isoformat()
            if hasattr(event_row["occurred_at"], "isoformat")
            else event_row["occurred_at"]
        ),
        "tenant_id": event_row["tenant_id"],
        "trace_id": event_row["trace_id"],
        "data": event_row["data"],
    }
    validator = jsonschema.Draft202012Validator(
        schema,
        registry=registry,
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
    )
    errors = list(validator.iter_errors(envelope))
    assert not errors, f"Event {ev_type} failed contract schema: {[e.message for e in errors]}"
