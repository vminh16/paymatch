"""FastAPI HTTP API, caller auth matrix, poller, and sim-world adapter tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import httpx
import yaml
from fastapi.testclient import TestClient

from gate.adapters.fakes import FakeClock, FakePaymentRail, InMemoryCoreReadStore, InMemoryLedgerStore
from gate.adapters.http import create_app
from gate.adapters.sim_world import SimWorldClock, SimWorldPaymentRail
from gate.application.poller import GateBackgroundPoller
from gate.config import Settings
from gate.domain.hashing import hash_tax_id_indicator
from gate.domain.models import (
    GoodsReceiptSnapshot,
    InvoiceSnapshot,
    KillSwitchSnapshot,
    PolicyState,
)
from gate.ports.rail import RailConflictError
from paymatch_contracts.gate import IntentGateDeniedProblem

from gate_fixtures import (
    ACC_COFFEE,
    ACC_POS_CARD,
    ACC_SYRUP_ESCROW,
    APV_01,
    APV_02,
    APV_ESC_CREATE,
    APV_ESC_CREATE_2,
    APV_ESC_RELEASE,
    DOC_SHA_SYRUP,
    GRN_01,
    INV_COFFEE,
    INV_POS,
    INV_SYRUP,
    JOB_01,
    NOW_VN,
    PO_01,
    ROOT,
    SERVICE_KEYS,
    STORE_01,
    TENANT_A,
    TENANT_B,
    VENDOR_COFFEE,
    VENDOR_POS,
    VENDOR_SYRUP,
    WALLET_A,
    make_approval_for_invoice,
    make_coffee_invoice,
    make_coffee_vendor,
    make_default_mandate,
    make_escrow_create_approval,
    make_pos_vendor,
    make_syrup_escrow_vendor,
    validate_outbox_event_against_contract,
)


def _make_test_env():
    read_store = InMemoryCoreReadStore()
    ledger_store = InMemoryLedgerStore()
    rail = FakePaymentRail()
    clock = FakeClock(NOW_VN)
    rail.now_fn = clock.now

    read_store.tenant_wallets[TENANT_A] = WALLET_A
    read_store.mandates[TENANT_A] = make_default_mandate()

    coffee_vendor, coffee_acc = make_coffee_vendor()
    read_store.vendors[(TENANT_A, coffee_vendor.vendor_id)] = coffee_vendor
    read_store.vendor_accounts[(TENANT_A, coffee_acc.vendor_account_id)] = coffee_acc

    pos_vendor, pos_acc = make_pos_vendor()
    read_store.vendors[(TENANT_A, pos_vendor.vendor_id)] = pos_vendor
    read_store.vendor_accounts[(TENANT_A, pos_acc.vendor_account_id)] = pos_acc

    syrup_vendor, syrup_acc, po = make_syrup_escrow_vendor()
    read_store.vendors[(TENANT_A, syrup_vendor.vendor_id)] = syrup_vendor
    read_store.vendor_accounts[(TENANT_A, syrup_acc.vendor_account_id)] = syrup_acc
    read_store.purchase_orders[po.purchase_order_id] = po
    read_store.goods_receipts[GRN_01] = GoodsReceiptSnapshot(
        goods_receipt_id=GRN_01,
        tenant_id=TENANT_A,
        purchase_order_id=po.purchase_order_id,
        store_id=STORE_01,
    )

    coffee_inv = make_coffee_invoice()
    read_store.invoices[coffee_inv.invoice_id] = coffee_inv
    read_store.latest_jobs[(TENANT_A, coffee_inv.invoice_id)] = JOB_01
    read_store.approvals[APV_01] = make_approval_for_invoice(
        coffee_inv, approval_id=APV_01, method="mandate"
    )

    settings = Settings(
        port=8100,
        database_url="",
        sim_url="http://sim-world.test/sim",
        sim_gate_service_key="sim-gate-key",
        demo_mode=True,
        merchant_api_service_key=SERVICE_KEYS["merchant-api"],
        core_worker_service_key=SERVICE_KEYS["core-worker"],
        internal_api_service_key=SERVICE_KEYS["internal-api"],
        console_api_service_key=SERVICE_KEYS["console-api"],
        enable_background_poller=False,
    )
    app = create_app(
        settings=settings,
        read_store=read_store,
        ledger_store=ledger_store,
        rail=rail,
        clock=clock,
    )
    client = TestClient(app)
    poller: GateBackgroundPoller = app.state.poller
    return client, read_store, ledger_store, rail, clock, poller


def _hdr(caller: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"X-Service-Key": SERVICE_KEYS[caller]}
    if extra:
        headers.update(extra)
    return headers


def test_openapi_routes_match_gate_yaml():
    client, *_ = _make_test_env()
    spec = yaml.safe_load((ROOT / "contracts" / "openapi" / "gate.yaml").read_text())
    expected = set()
    for path, methods in spec["paths"].items():
        for m in methods:
            if m in {"get", "post", "patch", "put", "delete"}:
                expected.add((m.upper(), path))
    mounted = set()
    for path, methods in client.app.openapi()["paths"].items():
        if path.startswith("/gate/"):
            for m in methods:
                if m in {"get", "post", "patch", "put", "delete"}:
                    mounted.add((m.upper(), path))
    assert expected == mounted


def test_healthz_readyz_and_caller_auth_matrix():
    client, read_store, *_ = _make_test_env()

    # Probes require no X-Service-Key
    r = client.get("/gate/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert "X-Request-Id" in r.headers

    r = client.get("/gate/readyz")
    assert r.status_code == 200 and r.json() == {"status": "ready"}

    # Missing / invalid key -> 401
    r = client.post("/gate/evaluate", json={"invoice_id": INV_COFFEE})
    assert r.status_code == 401 and r.json()["code"] == "UNAUTHENTICATED"

    r = client.post(
        "/gate/evaluate",
        json={"invoice_id": INV_COFFEE},
        headers={"X-Service-Key": "wrong-key"},
    )
    assert r.status_code == 401 and r.json()["code"] == "UNAUTHENTICATED"

    # Matrix enforcement
    assert (
        client.post(
            "/gate/intents",
            json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
            headers=_hdr("merchant-api"),
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/gate/intents",
            json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
            headers=_hdr("internal-api"),
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/gate/evaluate",
            json={"invoice_id": INV_COFFEE},
            headers=_hdr("console-api"),
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/gate/budgets/{TENANT_A}/2026-11-26",
            headers=_hdr("merchant-api"),
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/gate/budgets/{TENANT_A}/2026-11-26",
            headers=_hdr("internal-api"),
        ).status_code
        == 200
    )

    # Create intent as core-worker -> 201, then check console-api ticket enforcement
    created = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers=_hdr("core-worker"),
    )
    assert created.status_code == 201
    pi_id = created.json()["payment_intent_id"]

    # console-api without X-Ticket-Id -> 403 TICKET_REQUIRED
    r_no_ticket = client.get(f"/gate/intents/{pi_id}", headers=_hdr("console-api"))
    assert r_no_ticket.status_code == 403
    assert r_no_ticket.json()["code"] == "TICKET_REQUIRED"

    # console-api with X-Ticket-Id -> 200
    r_ticket = client.get(
        f"/gate/intents/{pi_id}",
        headers=_hdr("console-api", {"X-Ticket-Id": "TKT-2026-001"}),
    )
    assert r_ticket.status_code == 200

    # Tenant mismatch -> 403 TENANT_MISMATCH
    r_tm = client.post(
        "/gate/evaluate",
        json={"invoice_id": INV_COFFEE, "tenant_id": TENANT_B},
        headers=_hdr("merchant-api"),
    )
    assert r_tm.status_code == 403 and r_tm.json()["code"] == "TENANT_MISMATCH"

    # Policy unavailable -> readyz 503 & evaluate 503 (fail-closed)
    read_store.policy_state = PolicyState(available=False)
    assert client.get("/gate/readyz").status_code == 503
    r_fail_closed = client.post(
        "/gate/evaluate",
        json={"invoice_id": INV_COFFEE},
        headers=_hdr("merchant-api"),
    )
    assert r_fail_closed.status_code == 503
    assert r_fail_closed.json()["code"] == "UPSTREAM_UNAVAILABLE"


def test_two_phase_intent_lifecycle_bank_transfer_and_virtual_card():
    client, read_store, ledger_store, rail, clock, _ = _make_test_env()

    # Phase 1: create intent -> 201 authorized, budget reserved
    r1 = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers=_hdr("core-worker", {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}),
    )
    assert r1.status_code == 201
    pi = r1.json()
    assert pi["status"] == "authorized"
    assert pi["transfer_memo"] == "0999010001 · 1C26TTN · 00001425"

    # Idempotent retry of POST /gate/intents -> 200 with same intent
    r1_dup = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers=_hdr("core-worker"),
    )
    assert r1_dup.status_code == 200
    assert r1_dup.json()["payment_intent_id"] == pi["payment_intent_id"]

    # Budget shows 26.5M reserved
    b1 = client.get(f"/gate/budgets/{TENANT_A}/2026-11-26", headers=_hdr("core-worker")).json()
    assert b1["auto_pay_reserved_vnd"] == 26_500_000
    assert b1["auto_pay_used_vnd"] == 0
    assert b1["auto_pay_limit_vnd"] == 50_000_000

    # Phase 2: execute -> 200 settled, rail called once with idempotency_key=payment_intent_id
    r2 = client.post(
        f"/gate/intents/{pi['payment_intent_id']}:execute",
        json={},
        headers=_hdr("core-worker"),
    )
    assert r2.status_code == 200
    settled = r2.json()
    assert settled["status"] == "settled"
    assert settled["rail"]["rail_txn_id"] is not None
    assert len(rail.transfer_calls) == 1
    assert rail.transfer_calls[0]["idempotency_key"] == pi["payment_intent_id"]
    assert rail.transfer_calls[0]["account_number"] == "990010000001"

    # Budget moved from reserved -> used + total_paid
    b2 = client.get(f"/gate/budgets/{TENANT_A}/2026-11-26", headers=_hdr("core-worker")).json()
    assert b2["auto_pay_reserved_vnd"] == 0
    assert b2["auto_pay_used_vnd"] == 26_500_000
    assert b2["total_paid_vnd"] == 26_500_000

    # Virtual card flow (software invoice)
    pos_inv = InvoiceSnapshot(
        invoice_id=INV_POS,
        tenant_id=TENANT_A,
        vendor_id=VENDOR_POS,
        purchase_order_id=None,
        seller_tax_id="0999010032",
        symbol="1C26TSV",
        number="00000112",
        invoice_type="software",
        total_vnd=12_000_000,
        status="scheduled",
        severity="green",
        reason_codes=("OK",),
        document_sha256="b" * 64,
    )
    read_store.invoices[INV_POS] = pos_inv
    read_store.latest_jobs[(TENANT_A, INV_POS)] = JOB_01
    read_store.approvals[APV_02] = make_approval_for_invoice(
        pos_inv,
        approval_id=APV_02,
        payee_account_id=ACC_POS_CARD,
        channel="virtual_card",
        method="mandate",
    )

    rc1 = client.post(
        "/gate/intents",
        json={"invoice_id": INV_POS, "approval_id": APV_02},
        headers=_hdr("core-worker"),
    )
    assert rc1.status_code == 201 and rc1.json()["channel"] == "virtual_card"
    rc2 = client.post(
        f"/gate/intents/{rc1.json()['payment_intent_id']}:execute",
        json={},
        headers=_hdr("core-worker"),
    )
    assert rc2.status_code == 200 and rc2.json()["status"] == "settled"
    assert len(rail.card_calls) == 1
    assert rail.card_calls[0]["merchant_id"] == "mrc_pos_cloud_01"

    # List intents filtered by tenant_id & status
    listed = client.get(
        f"/gate/intents?tenant_id={TENANT_A}&status=settled",
        headers=_hdr("merchant-api"),
    )
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 2

    # Every outbox event validates against contracts/events/*.schema.json
    for ev in ledger_store.outbox:
        validate_outbox_event_against_contract(ev)


def test_invariant_rail_rejects_records_failed_never_paid():
    client, _, ledger_store, rail, _, _ = _make_test_env()
    rail.fail_next_transfer_code = "INSUFFICIENT_FUNDS"

    pi_id = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers=_hdr("core-worker"),
    ).json()["payment_intent_id"]

    r = client.post(
        f"/gate/intents/{pi_id}:execute",
        json={},
        headers=_hdr("core-worker"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed"
    assert body["rail"]["failure_code"] == "INSUFFICIENT_FUNDS"

    # Ledger has `failed`, NEVER `settled`
    assert [e["entry_type"] for e in ledger_store.ledger_entries] == ["failed"]
    # Auto-pay budget reservation released
    b = client.get(f"/gate/budgets/{TENANT_A}/2026-11-26", headers=_hdr("core-worker")).json()
    assert b["auto_pay_reserved_vnd"] == 0 and b["auto_pay_used_vnd"] == 0
    assert any(ev["type"] == "payment.failed" for ev in ledger_store.outbox)
    for ev in ledger_store.outbox:
        validate_outbox_event_against_contract(ev)


def test_reevaluate_at_execute_blocks_new_cross_alert_and_kill_switch():
    client, read_store, ledger_store, rail, _, _ = _make_test_env()

    # Authorize cleanly in Phase 1
    pi_id = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers=_hdr("core-worker"),
    ).json()["payment_intent_id"]

    # Between phase 1 and phase 2, cross alert is published for seller tax_id!
    read_store.cross_alerts.add(("tax_id", hash_tax_id_indicator("0999010001")))

    r = client.post(
        f"/gate/intents/{pi_id}:execute",
        json={},
        headers=_hdr("core-worker"),
    )
    assert r.status_code == 422
    problem = IntentGateDeniedProblem.model_validate(r.json())
    assert problem.code == "GATE_DENIED"
    assert any(gr.code.value == "CROSS_ALERT_UNVERIFIED" for gr in problem.gate_reasons)
    assert problem.payment_intent.status == "denied"
    assert len(rail.transfer_calls) == 0  # Rail was NEVER called!
    # Reserved budget released
    b = client.get(f"/gate/budgets/{TENANT_A}/2026-11-26", headers=_hdr("core-worker")).json()
    assert b["auto_pay_reserved_vnd"] == 0

    # Now test kill switch engaged -> 423 KILL_SWITCH_ACTIVE
    read_store.cross_alerts.clear()
    read_store.policy_state = replace(
        read_store.policy_state,
        kill_switches=(
            KillSwitchSnapshot(kill_switch_id="ksw_01", scope="auto_pay_global", target_id=None),
        ),
    )
    r_ks = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers=_hdr("core-worker"),
    )
    assert r_ks.status_code == 423
    assert r_ks.json()["code"] == "KILL_SWITCH_ACTIVE"
    for ev in ledger_store.outbox:
        validate_outbox_event_against_contract(ev)


def test_cancel_authorized_intent_and_409_when_executing():
    client, _, ledger_store, rail, _, _ = _make_test_env()
    pi_id = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers=_hdr("core-worker"),
    ).json()["payment_intent_id"]

    rc = client.post(
        f"/gate/intents/{pi_id}:cancel",
        json={"reason": "CROSS_ALERT"},
        headers=_hdr("core-worker"),
    )
    assert rc.status_code == 200
    assert rc.json()["status"] == "expired"
    b = client.get(f"/gate/budgets/{TENANT_A}/2026-11-26", headers=_hdr("core-worker")).json()
    assert b["auto_pay_reserved_vnd"] == 0

    # Re-create, then timeout on execute so it stays executing -> cancel returns 409 INVALID_STATE
    rail.timeout_next_transfer = True
    pi2 = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers=_hdr("core-worker"),
    ).json()["payment_intent_id"]
    re = client.post(f"/gate/intents/{pi2}:execute", json={}, headers=_hdr("core-worker"))
    assert re.status_code == 200 and re.json()["status"] == "executing"

    rc2 = client.post(
        f"/gate/intents/{pi2}:cancel",
        json={"reason": "OWNER_CANCELLED"},
        headers=_hdr("core-worker"),
    )
    assert rc2.status_code == 409 and rc2.json()["code"] == "INVALID_STATE"
    for ev in ledger_store.outbox:
        validate_outbox_event_against_contract(ev)


def test_background_poller_expires_after_15m_never_marks_unknown_failed_and_stuck_after_24h():
    client, _, ledger_store, rail, clock, poller = _make_test_env()

    # 1. Authorized intent > 15 min -> expired (AUTHORIZATION_TIMEOUT)
    pi1 = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers=_hdr("core-worker"),
    ).json()["payment_intent_id"]
    clock.advance(minutes=16)
    summary = poller.run_once()
    assert summary.expired_intents == 1
    assert ledger_store.intents[pi1].status.value == "expired"

    # 2. Executing intent with unknown rail status: stays executing, emits payment.stuck after 24h!
    rail.timeout_next_transfer = True
    rail.timeout_get_transfer = True
    pi2 = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers=_hdr("core-worker"),
    ).json()["payment_intent_id"]
    client.post(f"/gate/intents/{pi2}:execute", json={}, headers=_hdr("core-worker"))

    clock.advance(hours=2)
    s_early = poller.run_once()
    assert s_early.failed_intents == 0 and s_early.stuck_notified == 0
    assert ledger_store.intents[pi2].status.value == "executing"

    clock.advance(hours=23)  # Total 25h > 24h
    s_stuck = poller.run_once()
    assert s_stuck.failed_intents == 0
    assert s_stuck.stuck_notified == 1
    assert ledger_store.intents[pi2].status.value == "executing"
    # Second tick does NOT duplicate payment.stuck
    s_stuck_again = poller.run_once()
    assert s_stuck_again.stuck_notified == 0
    assert sum(1 for ev in ledger_store.outbox if ev["type"] == "payment.stuck") == 1

    for ev in ledger_store.outbox:
        validate_outbox_event_against_contract(ev)


def test_escrow_full_lifecycle_including_pending_poll_release_and_refund():
    client, read_store, ledger_store, rail, clock, poller = _make_test_env()
    po = read_store.purchase_orders[PO_01]
    create_apv = make_escrow_create_approval(po, approval_id=APV_ESC_CREATE)
    read_store.approvals[APV_ESC_CREATE] = create_apv

    # Preview escrow via /gate/evaluate
    ev = client.post(
        "/gate/evaluate",
        json={
            "purchase_order_id": PO_01,
            "vendor_account_id": ACC_SYRUP_ESCROW,
            "amount_vnd": 8_800_000,
        },
        headers=_hdr("merchant-api"),
    )
    assert ev.status_code == 200
    assert ev.json()["decision"] == "REQUIRE_APPROVAL"
    assert ev.json()["channel"] == "escrow"

    # Create escrow when rail times out -> stays `pending`, poller reconciles to `held`
    rail.timeout_next_escrow = True
    r_esc = client.post(
        "/gate/escrows",
        json={"approval_id": APV_ESC_CREATE, "expires_on": "2026-12-10"},
        headers=_hdr("merchant-api"),
    )
    assert r_esc.status_code == 201
    esc_id = r_esc.json()["escrow_id"]
    assert r_esc.json()["status"] == "pending"

    tick = poller.run_once()
    assert tick.held_escrows == 1
    r_get = client.get(f"/gate/escrows/{esc_id}", headers=_hdr("core-worker"))
    assert r_get.status_code == 200 and r_get.json()["status"] == "held"

    # Setup delivery invoice + escrow approval for release
    rel_inv = InvoiceSnapshot(
        invoice_id=INV_SYRUP,
        tenant_id=TENANT_A,
        vendor_id=VENDOR_SYRUP,
        purchase_order_id=PO_01,
        seller_tax_id="0999090001",
        symbol="1C26TSR",
        number="00000001",
        invoice_type="goods",
        total_vnd=8_800_000,
        status="escrow_held",
        severity="yellow",
        reason_codes=("VAT_DEDUCTION_RISK",),
        document_sha256=DOC_SHA_SYRUP,
    )
    read_store.invoices[INV_SYRUP] = rel_inv
    read_store.latest_jobs[(TENANT_A, INV_SYRUP)] = JOB_01
    read_store.approvals[APV_ESC_RELEASE] = make_approval_for_invoice(
        rel_inv,
        approval_id=APV_ESC_RELEASE,
        payee_account_id=ACC_SYRUP_ESCROW,
        channel="escrow",
        method="single",
    )

    # Release with non-existent GRN -> 422 GATE_DENIED with ESCROW_MISMATCH (B1)
    r_bad_rel = client.post(
        f"/gate/escrows/{esc_id}:release",
        json={"approval_id": APV_ESC_RELEASE, "goods_receipt_id": "grn_01M88M1SS1NG00000000000001"},
        headers=_hdr("core-worker"),
    )
    assert r_bad_rel.status_code == 422 and r_bad_rel.json()["code"] == "GATE_DENIED"
    assert any(gr["code"] == "ESCROW_MISMATCH" for gr in r_bad_rel.json()["gate_reasons"])

    # Release with valid GRN -> 200 released
    r_rel = client.post(
        f"/gate/escrows/{esc_id}:release",
        json={"approval_id": APV_ESC_RELEASE, "goods_receipt_id": GRN_01},
        headers=_hdr("core-worker"),
    )
    assert r_rel.status_code == 200
    assert r_rel.json()["status"] == "released"
    assert r_rel.json()["release_invoice_id"] == INV_SYRUP
    assert r_rel.json()["goods_receipt_id"] == GRN_01

    # B2: Re-POST with the SAME approval_id returns 200 with the ORIGINAL released escrow!
    r_reuse = client.post(
        "/gate/escrows",
        json={"approval_id": APV_ESC_CREATE, "expires_on": "2026-12-10"},
        headers=_hdr("merchant-api"),
    )
    assert r_reuse.status_code == 200
    assert r_reuse.json()["escrow_id"] == esc_id
    assert r_reuse.json()["status"] == "released"

    # Refund already-released escrow -> 409 INVALID_STATE
    r_ref_bad = client.post(
        f"/gate/escrows/{esc_id}:refund",
        json={"reason": "EXPIRED"},
        headers=_hdr("core-worker"),
    )
    assert r_ref_bad.status_code == 409

    # B2: A new escrow requires a NEW approval_id -> 201 held, then refund -> 200 refunded
    read_store.approvals[APV_ESC_CREATE_2] = make_escrow_create_approval(
        po, approval_id=APV_ESC_CREATE_2
    )
    r_esc2 = client.post(
        "/gate/escrows",
        json={"approval_id": APV_ESC_CREATE_2, "expires_on": "2026-12-10"},
        headers=_hdr("merchant-api"),
    )
    assert r_esc2.status_code == 201 and r_esc2.json()["status"] == "held"
    esc2_id = r_esc2.json()["escrow_id"]
    r_ref = client.post(
        f"/gate/escrows/{esc2_id}:refund",
        json={"reason": "ORDER_CANCELLED"},
        headers=_hdr("core-worker"),
    )
    assert r_ref.status_code == 200 and r_ref.json()["status"] == "refunded"

    # B2: Re-POST with APV_ESC_CREATE_2 after refund returns 200 with the refunded escrow!
    r_reuse_ref = client.post(
        "/gate/escrows",
        json={"approval_id": APV_ESC_CREATE_2, "expires_on": "2026-12-10"},
        headers=_hdr("merchant-api"),
    )
    assert r_reuse_ref.status_code == 200
    assert r_reuse_ref.json()["escrow_id"] == esc2_id
    assert r_reuse_ref.json()["status"] == "refunded"

    # I1: Safe integer upper bound rejected with 400 VALIDATION_FAILED
    r_overflow = client.post(
        "/gate/evaluate",
        json={
            "purchase_order_id": PO_01,
            "vendor_account_id": ACC_SYRUP_ESCROW,
            "amount_vnd": 9_007_199_254_740_992,
        },
        headers=_hdr("merchant-api"),
    )
    assert r_overflow.status_code == 400 and r_overflow.json()["code"] == "VALIDATION_FAILED"

    for ev_row in ledger_store.outbox:
        validate_outbox_event_against_contract(ev_row)


def test_x_allowed_callers_matrix_from_gate_yaml_enforced():
    """Verify every operation's x-allowed-callers in gate.yaml rejects all non-listed callers with 403."""
    client, *_ = _make_test_env()
    spec = yaml.safe_load((ROOT / "contracts" / "openapi" / "gate.yaml").read_text())
    all_callers = set(SERVICE_KEYS.keys())

    sample_paths = {
        "/gate/evaluate": ("POST", "/gate/evaluate", {"invoice_id": INV_COFFEE}),
        "/gate/budgets/{tenant_id}/{date}": ("GET", f"/gate/budgets/{TENANT_A}/2026-11-26", None),
        "/gate/intents": ("POST", "/gate/intents", {"invoice_id": INV_COFFEE, "approval_id": APV_01}),
        "/gate/intents_get": ("GET", f"/gate/intents?tenant_id={TENANT_A}", None),
        "/gate/intents/{payment_intent_id}": ("GET", "/gate/intents/pi_01M88557BXGABQA8KPG2382VH5", None),
        "/gate/intents/{payment_intent_id}:execute": ("POST", "/gate/intents/pi_01M88557BXGABQA8KPG2382VH5:execute", {}),
        "/gate/intents/{payment_intent_id}:cancel": ("POST", "/gate/intents/pi_01M88557BXGABQA8KPG2382VH5:cancel", {"reason": "OWNER_CANCELLED"}),
        "/gate/escrows": ("POST", "/gate/escrows", {"approval_id": APV_ESC_CREATE, "expires_on": "2026-12-10"}),
        "/gate/escrows/{escrow_id}": ("GET", "/gate/escrows/esc_01M88A6SAP3R27VDQ55VAKCF0P", None),
        "/gate/escrows/{escrow_id}:release": ("POST", "/gate/escrows/esc_01M88A6SAP3R27VDQ55VAKCF0P:release", {"approval_id": APV_ESC_RELEASE, "goods_receipt_id": GRN_01}),
        "/gate/escrows/{escrow_id}:refund": ("POST", "/gate/escrows/esc_01M88A6SAP3R27VDQ55VAKCF0P:refund", {"reason": "EXPIRED"}),
    }

    for path, path_item in spec["paths"].items():
        for method, op in path_item.items():
            if method not in {"get", "post"} or "x-allowed-callers" not in op:
                continue
            allowed = set(op["x-allowed-callers"])
            forbidden = all_callers - allowed
            key = "/gate/intents_get" if (path == "/gate/intents" and method == "get") else path
            req_method, req_url, body = sample_paths[key]
            for caller in forbidden:
                resp = client.request(req_method, req_url, json=body, headers=_hdr(caller))
                assert resp.status_code == 403, f"{caller} should get 403 on {req_method} {path}, got {resp.status_code}"
                assert resp.json()["code"] == "FORBIDDEN"


def test_sim_world_rail_and_clock_adapters():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Service-Key") == "sim-gate-key"
        if request.url.path == "/sim/scenario/clock":
            return httpx.Response(200, json={"now": "2026-11-26T09:15:00+07:00"})
        if request.url.path == "/sim/rails/transfers" and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "rail_txn_id": "rtx_01M88H11Y0WR367CGNZZH603T5",
                    "status": "settled",
                    "failure_code": None,
                    "settled_at": "2026-11-26T09:15:00+07:00",
                },
            )
        if request.url.path == "/sim/rails/cards" and request.method == "POST":
            return httpx.Response(
                409,
                json={"code": "IDEMPOTENCY_KEY_REUSED", "detail": "mismatch"},
            )
        return httpx.Response(404, json={"code": "NOT_FOUND"})

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    clock = SimWorldClock(sim_url="http://sim/sim", service_key="sim-gate-key", client=mock_client)
    assert clock.today_vn() == date(2026, 11, 26)
    assert clock.now().hour == 9

    rail = SimWorldPaymentRail(
        sim_url="http://sim/sim", service_key="sim-gate-key", client=mock_client
    )
    tr = rail.create_transfer(
        idempotency_key="pi_01",
        from_wallet_id=WALLET_A,
        bank_code="VNMB01",
        account_number="990010000001",
        account_name="TEST",
        amount_vnd=1000,
        memo="memo",
    )
    assert tr.status == "settled" and tr.rail_txn_id == "rtx_01M88H11Y0WR367CGNZZH603T5"

    try:
        rail.create_card(
            idempotency_key="pi_02",
            from_wallet_id=WALLET_A,
            merchant_id="mrc_1",
            amount_vnd=1000,
        )
        raise AssertionError("Expected RailConflictError")
    except RailConflictError:
        pass
