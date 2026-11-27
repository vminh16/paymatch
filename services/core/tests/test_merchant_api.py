"""Tests for merchant-api (/m/*) demo slice: auth, upload, detail, approval-preview, step-up :approve, :reject, queue, SSE, notifications, demo:reset."""

from __future__ import annotations

import base64
import pathlib
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from core.entrypoints.internal_api import create_internal_app
from core.entrypoints.merchant_api import create_merchant_app
from core.persistence.db import Database, dsn_for_role
from core.shared.clock import FixedClock
from core.shared.config import CoreSettings
from core.shared.hashing import action_hash, intent_hash_invoice, payload_hash_approval
from core.shared.ids import new_id
from core.shared.jwt_tokens import Ed25519KeyManager, StaticJwksVerifier
from core.tools.ports import GateEvaluation, UpstreamToolError

VN_TZ = timezone(timedelta(hours=7))
DEMO_DATA_DIR = pathlib.Path(__file__).resolve().parents[3] / "services" / "sim-world" / "data" / "demo"
DEMO_SEED_DIR = DEMO_DATA_DIR / "core_seed"

TENANT_A = "ten_01M88D3C06B97Y4G0S9W8BVKNG"
OWNER_A = "usr_01M885AXP309SER6BAC46N5FJT"
ACCOUNTANT_A = "usr_01M88KDM92WAXYR1VPJ05VGKVV"
STORE_MGR_1 = "usr_01M88101X8W8Q8V59W68115B7R"  # we'll look up a real store_manager from DB


class FakeIdentityProvider:
    """Signs momo_token and step-up auth_proof JWTs matching sim-world /sim/identity."""

    def __init__(self) -> None:
        self._priv = Ed25519PrivateKey.generate()
        self._pub = self._priv.public_key()
        raw = self._pub.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self._x = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        self.kid = "test-idp-key-1"

    def jwks(self) -> dict[str, Any]:
        return {
            "keys": [
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "alg": "EdDSA",
                    "use": "sig",
                    "kid": self.kid,
                    "x": self._x,
                }
            ]
        }

    def issue_momo_token(
        self,
        user_id: str,
        tenant_id: str,
        *,
        iss: str = "sim-world",
        now_ts: int | None = None,
        exp_offset: int = 3600,
    ) -> str:
        now = int(time.time()) if now_ts is None else now_ts
        return jwt.encode(
            {
                "iss": iss,
                "aud": "paymatch",
                "sub": user_id,
                "tenant_id": tenant_id,
                "token_use": "momo_token",
                "iat": now,
                "exp": now + exp_offset,
                "jti": new_id("jti"),
            },
            self._priv,
            algorithm="EdDSA",
            headers={"kid": self.kid},
        )

    def issue_auth_proof(
        self,
        user_id: str,
        ah: str,
        *,
        jti: str | None = None,
        iss: str = "sim-world",
        amr: Any = None,
        now_ts: int | None = None,
        exp_offset: int = 300,
    ) -> str:
        now = int(time.time()) if now_ts is None else now_ts
        return jwt.encode(
            {
                "iss": iss,
                "aud": "paymatch",
                "sub": user_id,
                "action_hash": ah,
                "jti": jti or new_id("jti"),
                "iat": now,
                "exp": now + exp_offset,
                "amr": ["otp"] if amr is None else amr,
                "token_use": "auth_proof",
            },
            self._priv,
            algorithm="EdDSA",
            headers={"kid": self.kid},
        )


class StubGate:
    def __init__(
        self,
        *,
        db: Database,
        decision: str = "REQUIRE_APPROVAL",
        verification_required: bool = False,
        unavailable: bool = False,
    ) -> None:
        self._db = db
        self.decision = decision
        self.verification_required = verification_required
        self.unavailable = unavailable
        self.cancelled: list[tuple[str, str]] = []

    def evaluate_invoice(self, *, invoice_id: str, tenant_id: str) -> GateEvaluation:
        if self.unavailable:
            raise UpstreamToolError("UPSTREAM_UNAVAILABLE", "Gate down")
        with self._db.connect() as conn:
            row = conn.execute(
                """
                SELECT i.invoice_id, i.total_vnd, i.vendor_id, i.verification_required, d.sha256
                FROM core.invoices i
                JOIN core.invoice_documents d ON d.document_id = i.document_id
                WHERE i.invoice_id = %s
                """,
                (invoice_id,),
            ).fetchone()
            va = conn.execute(
                """
                SELECT vendor_account_id FROM core.vendor_accounts
                WHERE tenant_id = %s AND vendor_id = %s AND status = 'verified'
                LIMIT 1
                """,
                (tenant_id, row["vendor_id"]),
            ).fetchone()
        payee_id = va["vendor_account_id"] if va else None
        amt = int(row["total_vnd"] or 0)
        ih = intent_hash_invoice(
            invoice_id=invoice_id,
            document_sha256=row["sha256"],
            payee_account_id=payee_id,
            amount_vnd=amt,
            channel="bank_transfer",
        )
        ver_req = self.verification_required or bool(row["verification_required"])
        return GateEvaluation(
            decision=self.decision,
            allowed_methods=["single"],
            verification_required=ver_req,
            intent_hash=ih,
            payee_account_id=payee_id,
            amount_vnd=amt,
            channel="bank_transfer",
            reasons=(
                [{"code": "BLOCKED_INVOICE", "layer": "hard_rule", "detail": "Blocked"}]
                if self.decision == "DENY"
                else []
            ),
            evaluated_at="2026-11-26T09:00:00+07:00",
        )

    def get_daily_budget(self, *, tenant_id: str, date_str: str):
        return {
            "date": date_str,
            "auto_pay_used_vnd": 0,
            "auto_pay_reserved_vnd": 0,
            "auto_pay_limit_vnd": 50_000_000,
            "total_paid_vnd": 0,
        }

    def create_intent(self, *, invoice_id: str, approval_id: str):
        return {"payment_intent_id": new_id("pi"), "status": "authorized"}

    def execute_intent(self, *, payment_intent_id: str):
        return {"payment_intent_id": payment_intent_id, "status": "settled"}

    def cancel_intent(self, *, payment_intent_id: str, reason: str):
        self.cancelled.append((payment_intent_id, reason))
        return {"payment_intent_id": payment_intent_id, "status": "expired"}

    def list_intents(self, *, tenant_id: str, invoice_id: str | None = None, status: str | None = None):
        return []


class StubSim:
    def reset_scenario(self, *, dataset: str = "demo", seed: int = 42):
        return {"loaded_at": "2026-11-26T08:00:00+07:00", "counts": {"scenarios": 49}}

    def __getattr__(self, name: str):
        raise AssertionError(f"Unexpected sim call: {name}")


def _complete_cups_job(db: Database, job_id: str, clock: FixedClock) -> None:
    """Helper: run internal-api job claim -> procurement price_check -> :complete so invoice becomes yellow pending_approval."""
    cfg = CoreSettings(database_url=db.dsn, internal_agent_service_key="k")
    iapp = create_internal_app(cfg, db=db, sim_world=StubSim(), gate_client=StubGate(db=db), clock=clock)
    ic = TestClient(iapp)
    hdr = {"X-Service-Key": "k"}

    claimed = ic.post("/internal/jobs:claim", json={"worker_id": "w1"}, headers=hdr).json()
    assert claimed["job_id"] == job_id
    sess = ic.post(
        f"/internal/jobs/{job_id}/session",
        json={"worker_id": "w1", "attempt": 1},
        headers=hdr,
    ).json()
    proc_tok = next(b["capability_token"] for b in sess["bots"] if b["bot_id"] == "procurement")
    phdr = {"Authorization": f"Bearer {proc_tok}"}

    inv_res = ic.post("/internal/tools/invoices:invoke", json={"input": {}}, headers=phdr).json()
    ic.post("/internal/tools/vendor_contracts:invoke", json={"input": {}}, headers=phdr)
    line_id = inv_res["data"]["invoices"][0]["lines"][0]["line_id"]
    pc = ic.post(
        "/internal/tools/price_check:invoke",
        json={"input": {"mappings": [{"line_id": line_id, "sku": "CUP-PP500-1000"}]}},
        headers=phdr,
    ).json()
    ic.post(
        f"/internal/jobs/{job_id}/findings",
        json={
            "bot_id": "procurement",
            "bot_version": 1,
            "skill_version": 1,
            "prompt_hash": "sha256:p",
            "severity_reported": "yellow",
            "reason_codes": ["PACK_SIZE_CHANGED", "PRICE_ABOVE_CONTRACT"],
            "reason": "800 vs 1000 cái/thùng",
            "evidence": [
                {"kind": "invoice_line", "ref_id": line_id, "tool_call_id": pc["evidence_ref"]}
            ],
            "provenance": "trusted",
        },
        headers=phdr,
    )
    ic.post(
        f"/internal/jobs/{job_id}/progress",
        json={
            "worker_id": "w1",
            "attempt": 1,
            "events": [
                {"type": "bot.finished", "bot_id": "procurement", "severity": "yellow", "at": "2026-11-26T09:00:05+07:00"}
            ],
        },
        headers=hdr,
    )
    comp = ic.post(
        f"/internal/jobs/{job_id}:complete",
        json={
            "worker_id": "w1",
            "attempt": 1,
            "result": {
                "brief": {
                    "lines": ["Cốc nhựa shrinkflation 800 vs 1000 cái."],
                    "cited_evidence": [],
                    "model": "fake",
                    "prompt_hash": "sha256:b",
                }
            },
        },
        headers=hdr,
    )
    assert comp.status_code == 200
    assert comp.json()["final_severity"] == "yellow"
    assert comp.json()["invoice_status"] == "pending_approval"


@pytest.mark.db
def test_merchant_full_demo_slice_upload_preview_approve_reject_queue_sse_and_reset(
    seeded_db: Database,
    merchant_db: Database,
    migrator_db: Database,
    fixed_clock: FixedClock,
) -> None:
    idp = FakeIdentityProvider()
    gate = StubGate(db=seeded_db)
    cfg = CoreSettings(database_url=merchant_db.dsn, demo_mode=True, seed_dir=DEMO_SEED_DIR)
    app = create_merchant_app(
        cfg,
        db=merchant_db,
        admin_db=migrator_db,
        sim_world=StubSim(),
        gate_client=gate,
        jwks_verifier=StaticJwksVerifier(idp.jwks()),
        clock=fixed_clock,
    )
    client = TestClient(app)

    # 1. Session exchange via JWKS
    owner_momo = idp.issue_momo_token(OWNER_A, TENANT_A)
    s_resp = client.post("/m/auth/session", json={"momo_token": owner_momo})
    assert s_resp.status_code == 200
    owner_jwt = s_resp.json()["session_jwt"]
    owner_hdr = {"Authorization": f"Bearer {owner_jwt}"}

    acc_momo = idp.issue_momo_token(ACCOUNTANT_A, TENANT_A)
    acc_jwt = client.post("/m/auth/session", json={"momo_token": acc_momo}).json()["session_jwt"]
    acc_hdr = {"Authorization": f"Bearer {acc_jwt}"}

    me = client.get("/m/me", headers=owner_hdr)
    assert me.status_code == 200
    assert me.json()["role"] == "owner"
    assert "invoices:approve" in me.json()["permissions"]

    # 2. Upload XML (202), replay same sha256 (200 no-op), upload modified same key (409 DUPLICATE_INVOICE)
    cups_xml = (DEMO_DATA_DIR / "inbox/attachments/1C26TNX_00000744.xml").read_bytes()
    up1 = client.post(
        "/m/invoices:upload",
        files={"file": ("1C26TNX_00000744.xml", cups_xml, "application/xml")},
        headers={**owner_hdr, "Idempotency-Key": "idem-up-1"},
    )
    assert up1.status_code == 202
    inv_id = up1.json()["invoice_id"]
    job_id = up1.json()["job_id"]

    up_noop = client.post(
        "/m/invoices:upload",
        files={"file": ("1C26TNX_00000744.xml", cups_xml, "application/xml")},
        headers={**owner_hdr, "Idempotency-Key": "idem-up-2"},
    )
    assert up_noop.status_code == 200
    assert up_noop.json()["invoice_id"] == inv_id

    cups_dup_xml = cups_xml.replace(b"<SHDon>00000744</SHDon>", b"<SHDon>744</SHDon>")
    up_dup = client.post(
        "/m/invoices:upload",
        files={"file": ("dup.xml", cups_dup_xml, "application/xml")},
        headers={**owner_hdr, "Idempotency-Key": "idem-up-3"},
    )
    assert up_dup.status_code == 409
    assert up_dup.json()["code"] == "DUPLICATE_INVOICE"
    assert up_dup.json()["existing_invoice_id"] == inv_id

    # 3. Complete investigation -> yellow pending_approval
    _complete_cups_job(seeded_db, job_id, fixed_clock)

    # 4. Detail + ETag + findings + job + SSE + approval-queue
    det = client.get(f"/m/invoices/{inv_id}", headers=owner_hdr)
    assert det.status_code == 200
    assert "ETag" in det.headers
    assert det.json()["severity"] == "yellow"
    assert det.json()["status"] == "pending_approval"

    fnds = client.get(f"/m/invoices/{inv_id}/findings", headers=acc_hdr)
    assert fnds.status_code == 200
    assert any(f["bot_id"] == "procurement" for f in fnds.json())

    job_resp = client.get(f"/m/jobs/{job_id}", headers=owner_hdr)
    assert job_resp.status_code == 200
    assert job_resp.json()["status"] == "completed"

    sse_resp = client.get(f"/m/jobs/{job_id}/events", headers=owner_hdr)
    assert sse_resp.status_code == 200
    assert "event: bot.finished" in sse_resp.text
    assert "event: job.completed" in sse_resp.text

    q_vendor = client.get("/m/approval-queue?group_by=vendor", headers=owner_hdr)
    assert q_vendor.status_code == 200
    assert q_vendor.json()["groups"][0]["count"] == 1
    assert "BAO BÌ NHỰA XANH VIỆT" in q_vendor.json()["groups"][0]["label"]

    # 5. Approval preview & step-up :approve (accountant denied 403; wrong action_hash denied 403; valid owner succeeds; replay jti denied 403)
    prev = client.get(f"/m/invoices/{inv_id}/approval-preview", headers=owner_hdr)
    assert prev.status_code == 200
    prev_data = prev.json()
    assert prev_data["job_id"] == job_id

    # Accountant cannot approve
    bad_role = client.post(
        f"/m/invoices/{inv_id}:approve",
        json={
            "intent_hash": prev_data["intent_hash"],
            "job_id": job_id,
            "auth_proof": "x",
        },
        headers={**acc_hdr, "Idempotency-Key": "idem-apv-acc"},
    )
    assert bad_role.status_code == 403
    assert bad_role.json()["code"] == "ROLE_NOT_ALLOWED"

    # Owner with valid step-up auth_proof succeeds
    proof = idp.issue_auth_proof(OWNER_A, prev_data["action_hash"], jti="jti_single_use_1")
    apv = client.post(
        f"/m/invoices/{inv_id}:approve",
        json={
            "intent_hash": prev_data["intent_hash"],
            "job_id": job_id,
            "auth_proof": proof,
            "verification": None,
        },
        headers={**owner_hdr, "Idempotency-Key": "idem-apv-1"},
    )
    assert apv.status_code == 200
    assert apv.json()["invoice"]["status"] == "approved"
    assert apv.json()["approval"]["status"] == "active"

    # Same Idempotency-Key returns same 200 response; different body with same key -> 409 IDEMPOTENCY_KEY_REUSED
    apv_idem = client.post(
        f"/m/invoices/{inv_id}:approve",
        json={
            "intent_hash": prev_data["intent_hash"],
            "job_id": job_id,
            "auth_proof": proof,
            "verification": None,
        },
        headers={**owner_hdr, "Idempotency-Key": "idem-apv-1"},
    )
    assert apv_idem.status_code == 200
    assert apv_idem.json()["approval"]["approval_id"] == apv.json()["approval"]["approval_id"]

    # 6. Reject from approved -> rejected + deterministic AdjustmentRequest
    rej = client.post(
        f"/m/invoices/{inv_id}:reject",
        json={"reason_code": "PACK_SIZE_CHANGED", "note": "Giao đúng 1.000 cái/thùng"},
        headers={**owner_hdr, "Idempotency-Key": "idem-rej-1"},
    )
    assert rej.status_code == 200
    assert rej.json()["invoice"]["status"] == "rejected"
    assert rej.json()["adjustment_request"] is not None
    assert "CUP-PP500-1000" in rej.json()["adjustment_request"]["body"]

    adj_get = client.get(f"/m/invoices/{inv_id}/adjustment-request", headers=acc_hdr)
    assert adj_get.status_code == 200
    assert adj_get.json()["adjustment_request_id"] == rej.json()["adjustment_request"]["adjustment_request_id"]

    # 7. Notifications & demo:reset
    ntf = client.get("/m/notifications", headers=owner_hdr)
    assert ntf.status_code == 200
    assert "items" in ntf.json()

    rst = client.post(
        "/m/demo:reset",
        json={},
        headers={**owner_hdr, "Idempotency-Key": "idem-rst-1"},
    )
    assert rst.status_code == 200
    assert rst.json()["counts"]["tenants"] == 2
    assert rst.json()["counts"]["scenarios"] == 49


@pytest.mark.db
def test_demo_reset_not_mounted_when_demo_mode_false(
    seeded_db: Database, merchant_db: Database, fixed_clock: FixedClock
) -> None:
    idp = FakeIdentityProvider()
    cfg = CoreSettings(database_url=merchant_db.dsn, demo_mode=False)
    app = create_merchant_app(
        cfg,
        db=merchant_db,
        sim_world=StubSim(),
        gate_client=StubGate(db=seeded_db),
        jwks_verifier=StaticJwksVerifier(idp.jwks()),
        clock=fixed_clock,
    )
    client = TestClient(app)
    tok = client.post(
        "/m/auth/session", json={"momo_token": idp.issue_momo_token(OWNER_A, TENANT_A)}
    ).json()["session_jwt"]
    r = client.post("/m/demo:reset", json={}, headers={"Authorization": f"Bearer {tok}", "Idempotency-Key": "k1"})
    assert r.status_code == 404


@pytest.mark.db
def test_i9_sse_tails_live_until_job_completed_and_tenant_stream(
    seeded_db: Database,
    merchant_db: Database,
    fixed_clock: FixedClock,
) -> None:
    """I9: /m/jobs/{id}/events stays open while job is running, streams live progress events, and closes on job.completed;
    /m/events tails live tenant events arriving after connection open.
    """
    import threading
    from psycopg.types.json import Jsonb

    idp = FakeIdentityProvider()
    cfg = CoreSettings(
        database_url=merchant_db.dsn,
        demo_mode=False,
        sse_poll_interval_s=0.05,
        sse_keepalive_interval_s=0.15,
        sse_max_idle_seconds=2.0,
    )
    app = create_merchant_app(
        cfg,
        db=merchant_db,
        sim_world=StubSim(),
        gate_client=StubGate(db=seeded_db),
        jwks_verifier=StaticJwksVerifier(idp.jwks()),
        clock=fixed_clock,
    )
    client = TestClient(app)
    owner_jwt = client.post(
        "/m/auth/session", json={"momo_token": idp.issue_momo_token(OWNER_A, TENANT_A)}
    ).json()["session_jwt"]
    owner_hdr = {"Authorization": f"Bearer {owner_jwt}"}

    # Upload invoice -> job is queued/running (NOT completed yet!)
    cups_xml = (DEMO_DATA_DIR / "inbox/attachments/1C26TNX_00000744.xml").read_bytes()
    up = client.post(
        "/m/invoices:upload",
        files={"file": ("1C26TNX_00000744.xml", cups_xml, "application/xml")},
        headers={**owner_hdr, "Idempotency-Key": "idem-sse-live-1"},
    )
    assert up.status_code == 202
    job_id = up.json()["job_id"]
    inv_id = up.json()["invoice_id"]

    # Background thread emits live bot progress + completes the job 0.25s AFTER the SSE stream opens
    def _drive_job_live() -> None:
        time.sleep(0.25)
        _complete_cups_job(seeded_db, job_id, fixed_clock)

    t = threading.Thread(target=_drive_job_live, daemon=True)
    t.start()

    # Open SSE stream BEFORE job finishes -> MUST stay open, receive live bot.finished & job.completed, then close!
    sse_resp = client.get(f"/m/jobs/{job_id}/events", headers=owner_hdr)
    t.join(timeout=10)
    assert sse_resp.status_code == 200
    assert "event: bot.finished" in sse_resp.text
    assert "event: job.completed" in sse_resp.text

    # Also verify /m/events live-tails a new tenant event emitted AFTER connection opens
    def _emit_tenant_event() -> None:
        time.sleep(0.20)
        with seeded_db.connect() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO core.sse_events (
                        event_id, stream_type, stream_key, tenant_id, store_id, event_type, data, created_at
                    )
                    VALUES (%s, 'tenant', %s, %s, NULL, 'notification.created', %s, %s)
                    """,
                    (
                        new_id("evt"),
                        TENANT_A,
                        TENANT_A,
                        Jsonb({"notification_id": new_id("ntf"), "kind": "cross_alert_affected"}),
                        fixed_clock.now(),
                    ),
                )

    t2 = threading.Thread(target=_emit_tenant_event, daemon=True)
    t2.start()
    ten_sse = client.get("/m/events", headers=owner_hdr)
    t2.join(timeout=10)
    assert ten_sse.status_code == 200
    assert "event: notification.created" in ten_sse.text


@pytest.mark.db
def test_i7_i3_i2_i10_auth_proof_preview_expiry_escrow_concurrent_change_and_upload_limit(
    seeded_db: Database,
    merchant_db: Database,
    fixed_clock: FixedClock,
) -> None:
    """I7/I3/I2/I10: verify iss/exp/iat/amr validation, 5m preview TTL, escrow_held channel check,
    concurrent version/verification change rejection, decoupled wall vs business clock, and upload byte limit.
    """
    sec_clock = FixedClock(fixed_clock.now())
    biz_clock = FixedClock(fixed_clock.now() + timedelta(days=30))  # I2: +30 days ahead of wall clock!
    idp = FakeIdentityProvider()
    gate = StubGate(db=seeded_db)
    cfg = CoreSettings(
        database_url=merchant_db.dsn,
        demo_mode=False,
        max_invoice_bytes=200_000,
        approval_preview_ttl_seconds=300,
    )
    app = create_merchant_app(
        cfg,
        db=merchant_db,
        sim_world=StubSim(),
        gate_client=gate,
        jwks_verifier=StaticJwksVerifier(idp.jwks(), expected_issuer="sim-world", clock=sec_clock),
        clock=biz_clock,
        security_clock=sec_clock,
    )
    client = TestClient(app)

    # I2: Session exchange works even when business clock is +30 days ahead of wall/security clock
    sec_ts = int(sec_clock.now().timestamp())
    owner_momo = idp.issue_momo_token(OWNER_A, TENANT_A, now_ts=sec_ts)
    owner_jwt = client.post("/m/auth/session", json={"momo_token": owner_momo}).json()["session_jwt"]
    owner_hdr = {"Authorization": f"Bearer {owner_jwt}"}

    # I7: Wrong issuer on momo_token rejected (401)
    bad_iss_momo = idp.issue_momo_token(OWNER_A, TENANT_A, iss="evil-idp", now_ts=sec_ts)
    assert client.post("/m/auth/session", json={"momo_token": bad_iss_momo}).status_code == 401

    # I10: Oversized upload rejected with 413 PAYLOAD_TOO_LARGE
    huge = b"X" * (cfg.max_invoice_bytes + 1024)
    r_big = client.post(
        "/m/invoices:upload",
        files={"file": ("huge.pdf", huge, "application/pdf")},
        headers={**owner_hdr, "Idempotency-Key": "idem-huge-1"},
    )
    assert r_big.status_code == 413
    assert r_big.json()["code"] == "PAYLOAD_TOO_LARGE"

    # Upload normal cups invoice & complete investigation
    cups_xml = (DEMO_DATA_DIR / "inbox/attachments/1C26TNX_00000744.xml").read_bytes()
    up = client.post(
        "/m/invoices:upload",
        files={"file": ("cups.xml", cups_xml, "application/xml")},
        headers={**owner_hdr, "Idempotency-Key": "idem-cups-i7"},
    ).json()
    inv_id, job_id = up["invoice_id"], up["job_id"]
    _complete_cups_job(seeded_db, job_id, biz_clock)

    # Get preview
    prev = client.get(f"/m/invoices/{inv_id}/approval-preview", headers=owner_hdr).json()
    ah = prev["action_hash"]
    ih = prev["intent_hash"]

    # I7: Reject bad issuer, bogus amr=["none"], string amr="yes", expired auth_proof, wrong subject
    for idx, bad_proof in enumerate(
        [
            idp.issue_auth_proof(OWNER_A, ah, iss="other-idp", now_ts=sec_ts),
            idp.issue_auth_proof(OWNER_A, ah, amr=["none"], now_ts=sec_ts),
            idp.issue_auth_proof(OWNER_A, ah, amr="yes", now_ts=sec_ts),
            idp.issue_auth_proof(OWNER_A, ah, now_ts=sec_ts - 600, exp_offset=300),
            idp.issue_auth_proof(ACCOUNTANT_A, ah, now_ts=sec_ts),
            idp.issue_auth_proof(OWNER_A, "0" * 64, now_ts=sec_ts),
        ]
    ):
        r_bad = client.post(
            f"/m/invoices/{inv_id}:approve",
            json={"intent_hash": ih, "job_id": job_id, "auth_proof": bad_proof},
            headers={**owner_hdr, "Idempotency-Key": f"idem-bad-proof-{idx}"},
        )
        assert r_bad.status_code == 403, f"Case {idx} should fail 403, got {r_bad.status_code}: {r_bad.text}"
        assert r_bad.json()["code"] == "STEP_UP_INVALID"

    # I7: Expire preview (>5 minutes on security_clock) -> 409 INTENT_HASH_MISMATCH
    sec_clock.advance(timedelta(seconds=360))
    sec_ts2 = int(sec_clock.now().timestamp())
    valid_proof_late = idp.issue_auth_proof(OWNER_A, ah, now_ts=sec_ts2)
    r_exp = client.post(
        f"/m/invoices/{inv_id}:approve",
        json={"intent_hash": ih, "job_id": job_id, "auth_proof": valid_proof_late},
        headers={**owner_hdr, "Idempotency-Key": "idem-exp-prev"},
    )
    assert r_exp.status_code == 409
    assert r_exp.json()["code"] == "INTENT_HASH_MISMATCH"

    # I3: Concurrent cross-alert updates invoice version & verification_required (status stays pending_approval!)
    # -> fresh preview taken BEFORE alert is invalidated (409 INTENT_HASH_MISMATCH)!
    prev2 = client.get(f"/m/invoices/{inv_id}/approval-preview", headers=owner_hdr).json()
    with seeded_db.connect() as conn:
        with conn.transaction():
            conn.execute(
                """
                UPDATE core.invoices
                SET verification_required = TRUE, version = version + 1
                WHERE invoice_id = %s
                """,
                (inv_id,),
            )
    proof2 = idp.issue_auth_proof(OWNER_A, prev2["action_hash"], now_ts=sec_ts2)
    r_stale_ver = client.post(
        f"/m/invoices/{inv_id}:approve",
        json={"intent_hash": prev2["intent_hash"], "job_id": job_id, "auth_proof": proof2},
        headers={**owner_hdr, "Idempotency-Key": "idem-stale-ver"},
    )
    assert r_stale_ver.status_code == 409
    assert r_stale_ver.json()["code"] == "INTENT_HASH_MISMATCH"

    # I3: escrow_held invoice CANNOT be approved when Gate channel != 'escrow' -> 409 INVALID_STATE
    with seeded_db.connect() as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE core.invoices SET status = 'escrow_held', verification_required = FALSE WHERE invoice_id = %s",
                (inv_id,),
            )
    prev_esc = client.get(f"/m/invoices/{inv_id}/approval-preview", headers=owner_hdr).json()
    proof_esc = idp.issue_auth_proof(OWNER_A, prev_esc["action_hash"], now_ts=sec_ts2)
    r_esc = client.post(
        f"/m/invoices/{inv_id}:approve",
        json={"intent_hash": prev_esc["intent_hash"], "job_id": job_id, "auth_proof": proof_esc},
        headers={**owner_hdr, "Idempotency-Key": "idem-esc-bad-ch"},
    )
    assert r_esc.status_code == 409
    assert r_esc.json()["code"] == "INVALID_STATE"


@pytest.mark.db
def test_i3_core_only_phone_masked_verification_bound_earlier_proof_and_post_lock_ttl(
    seeded_db: Database,
    merchant_db: Database,
    fixed_clock: FixedClock,
) -> None:
    """I3 & Nit 1: Core-only verification_required returns phone_on_file_masked; earlier proof (iat < preview.created_at)
    is rejected; post-lock preview/proof expiry is rejected; verification-bound approval succeeds and consumes preview once.
    """
    sec_clock = FixedClock(fixed_clock.now())
    idp = FakeIdentityProvider()
    advance_on_eval: dict[str, int] = {"seconds": 0}

    class AdvancingGate(StubGate):
        def evaluate_invoice(self, *, invoice_id: str, tenant_id: str) -> GateEvaluation:
            res = super().evaluate_invoice(invoice_id=invoice_id, tenant_id=tenant_id)
            if advance_on_eval["seconds"] > 0:
                sec_clock.advance(timedelta(seconds=advance_on_eval["seconds"]))
                advance_on_eval["seconds"] = 0
            return res

    gate = AdvancingGate(db=seeded_db)
    cfg = CoreSettings(
        database_url=merchant_db.dsn,
        demo_mode=False,
        approval_preview_ttl_seconds=300,
    )
    app = create_merchant_app(
        cfg,
        db=merchant_db,
        sim_world=StubSim(),
        gate_client=gate,
        jwks_verifier=StaticJwksVerifier(idp.jwks(), expected_issuer="sim-world", clock=sec_clock),
        clock=fixed_clock,
        security_clock=sec_clock,
    )
    client = TestClient(app)
    sec_ts = int(sec_clock.now().timestamp())
    owner_jwt = client.post(
        "/m/auth/session", json={"momo_token": idp.issue_momo_token(OWNER_A, TENANT_A, now_ts=sec_ts)}
    ).json()["session_jwt"]
    owner_hdr = {"Authorization": f"Bearer {owner_jwt}"}

    cups_xml = (DEMO_DATA_DIR / "inbox/attachments/1C26TNX_00000744.xml").read_bytes()
    up = client.post(
        "/m/invoices:upload",
        files={"file": ("cups_i3.xml", cups_xml, "application/xml")},
        headers={**owner_hdr, "Idempotency-Key": "idem-i3-up"},
    ).json()
    inv_id, job_id = up["invoice_id"], up["job_id"]
    _complete_cups_job(seeded_db, job_id, fixed_clock)

    # Set verification_required=True ONLY on Core invoice (StubGate returns verification_required=False!)
    with seeded_db.connect() as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE core.invoices SET verification_required = TRUE WHERE invoice_id = %s",
                (inv_id,),
            )

    # 1. Preview MUST return verification_required=True AND non-null phone_on_file_masked from vendor registry!
    prev1 = client.get(f"/m/invoices/{inv_id}/approval-preview", headers=owner_hdr).json()
    assert prev1["verification_required"] is True
    assert prev1["phone_on_file_masked"] is not None and "*" in prev1["phone_on_file_masked"]
    ih = prev1["intent_hash"]

    ver_payload = {
        "called_phone_on_file": True,
        "result": "confirmed",
        "note": "Đã gọi lại kế toán trưởng NCC",
        "at": "2026-11-26T09:00:00+07:00",
    }
    bound_ah = action_hash("approve_invoice", inv_id, payload_hash_approval(ih, ver_payload))

    # 2. Mint an earlier proof at t0, then advance clock +10s and create a NEWER preview at t1 ->
    #    t0 proof MUST be rejected (403 STEP_UP_INVALID: predates preview)!
    earlier_proof = idp.issue_auth_proof(OWNER_A, bound_ah, now_ts=int(sec_clock.now().timestamp()), exp_offset=600)
    sec_clock.advance(timedelta(seconds=10))
    prev2 = client.get(f"/m/invoices/{inv_id}/approval-preview", headers=owner_hdr).json()
    assert prev2["intent_hash"] == ih

    r_early = client.post(
        f"/m/invoices/{inv_id}:approve",
        json={"intent_hash": ih, "job_id": job_id, "auth_proof": earlier_proof, "verification": ver_payload},
        headers={**owner_hdr, "Idempotency-Key": "idem-i3-early-proof"},
    )
    assert r_early.status_code == 403
    assert r_early.json()["code"] == "STEP_UP_INVALID"

    # 3. Post-lock preview expiry: preview is fresh at request start, Gate evaluation stalls +350s past preview TTL ->
    #    post-lock re-check MUST reject with 409 INTENT_HASH_MISMATCH!
    fresh_proof_slow = idp.issue_auth_proof(OWNER_A, bound_ah, now_ts=int(sec_clock.now().timestamp()), exp_offset=600)
    advance_on_eval["seconds"] = 350
    r_slow_prev = client.post(
        f"/m/invoices/{inv_id}:approve",
        json={"intent_hash": ih, "job_id": job_id, "auth_proof": fresh_proof_slow, "verification": ver_payload},
        headers={**owner_hdr, "Idempotency-Key": "idem-i3-slow-prev"},
    )
    assert r_slow_prev.status_code == 409
    assert r_slow_prev.json()["code"] == "INTENT_HASH_MISMATCH"

    # 4. Isolated post-lock proof expiry: proof is valid BEFORE lock (passes verify_auth_proof), then expires
    #    while waiting on core.invoices FOR UPDATE lock -> post-lock check rejects with 403 STEP_UP_INVALID!
    import threading
    prev3 = client.get(f"/m/invoices/{inv_id}/approval-preview", headers=owner_hdr).json()
    short_proof = idp.issue_auth_proof(OWNER_A, bound_ah, now_ts=int(sec_clock.now().timestamp()), exp_offset=30)
    # Use a verifier that is still valid before lock; hold FOR UPDATE in another connection and advance sec_clock!
    lock_held = threading.Event()
    approve_result: dict[str, Any] = {}

    def _hold_lock_and_expire() -> None:
        with seeded_db.connect() as lconn:
            with lconn.transaction():
                lconn.execute(
                    "SELECT * FROM core.invoices WHERE invoice_id = %s FOR UPDATE",
                    (inv_id,),
                ).fetchone()
                lock_held.set()
                time.sleep(0.25)
                # Advance sec_clock past short_proof's 30s expiry while approve_invoice is waiting on FOR UPDATE!
                sec_clock.advance(timedelta(seconds=60))

    t_lock = threading.Thread(target=_hold_lock_and_expire)
    t_lock.start()
    lock_held.wait(timeout=5)
    r_slow_proof = client.post(
        f"/m/invoices/{inv_id}:approve",
        json={"intent_hash": prev3["intent_hash"], "job_id": job_id, "auth_proof": short_proof, "verification": ver_payload},
        headers={**owner_hdr, "Idempotency-Key": "idem-i3-slow-proof"},
    )
    t_lock.join(timeout=10)
    assert r_slow_proof.status_code == 403
    assert r_slow_proof.json()["code"] == "STEP_UP_INVALID"
    assert "hết hạn" in r_slow_proof.json()["detail"]

    # 4b. Using preview's unverified action_hash when verification_required=True fails 403 STEP_UP_INVALID
    prev4 = client.get(f"/m/invoices/{inv_id}/approval-preview", headers=owner_hdr).json()
    unverified_ah_proof = idp.issue_auth_proof(OWNER_A, prev4["action_hash"], now_ts=int(sec_clock.now().timestamp()), exp_offset=300)
    r_unver_hash = client.post(
        f"/m/invoices/{inv_id}:approve",
        json={"intent_hash": prev4["intent_hash"], "job_id": job_id, "auth_proof": unverified_ah_proof, "verification": ver_payload},
        headers={**owner_hdr, "Idempotency-Key": "idem-i3-unver-hash"},
    )
    assert r_unver_hash.status_code == 403 and r_unver_hash.json()["code"] == "STEP_UP_INVALID"

    # 5. Successful verification-bound approval: fresh preview + fresh proof -> 200 AND preview consumed once!
    good_proof = idp.issue_auth_proof(OWNER_A, bound_ah, now_ts=int(sec_clock.now().timestamp()), exp_offset=300)
    r_ok = client.post(
        f"/m/invoices/{inv_id}:approve",
        json={"intent_hash": prev4["intent_hash"], "job_id": job_id, "auth_proof": good_proof, "verification": ver_payload},
        headers={**owner_hdr, "Idempotency-Key": "idem-i3-ok"},
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["invoice"]["status"] == "approved"
    assert r_ok.json()["approval"]["verification"]["result"] == "confirmed"
    with seeded_db.connect() as conn:
        leftover = conn.execute(
            "SELECT COUNT(*) AS cnt FROM core.approval_previews WHERE invoice_id = %s",
            (inv_id,),
        ).fetchone()["cnt"]
    # Replaced prior previews on refresh AND consumed prev4 on commit -> 0 rows left!
    assert leftover == 0

    # 6. End-to-end non-verification flow using returned preview["action_hash"] directly + sub-second iat precision
    coffee_xml = (DEMO_DATA_DIR / "inbox/attachments/1C26TTN_00001425.xml").read_bytes()
    up2 = client.post(
        "/m/invoices:upload",
        files={"file": ("coffee_i3.xml", coffee_xml, "application/xml")},
        headers={**owner_hdr, "Idempotency-Key": "idem-i3-up2"},
    ).json()
    inv2_id, job2_id = up2["invoice_id"], up2["job_id"]
    _complete_cups_job(seeded_db, job2_id, fixed_clock)
    with seeded_db.connect() as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE core.invoices SET status = 'pending_approval', verification_required = FALSE WHERE invoice_id = %s",
                (inv2_id,),
            )
    # Preview created at sub-second .800
    sec_clock.advance(timedelta(microseconds=800_000))
    prev_nv = client.get(f"/m/invoices/{inv2_id}/approval-preview", headers=owner_hdr).json()
    assert prev_nv["verification_required"] is False
    # Proof issued directly from returned prev_nv["action_hash"] -> succeeds end-to-end!
    proof_nv = idp.issue_auth_proof(OWNER_A, prev_nv["action_hash"], now_ts=int(sec_clock.now().timestamp()), exp_offset=300)
    r_nv = client.post(
        f"/m/invoices/{inv2_id}:approve",
        json={"intent_hash": prev_nv["intent_hash"], "job_id": job2_id, "auth_proof": proof_nv},
        headers={**owner_hdr, "Idempotency-Key": "idem-i3-nv-ok"},
    )
    assert r_nv.status_code == 200
    assert r_nv.json()["invoice"]["status"] == "approved"


@pytest.mark.db
def test_i2_i6_sse_reverse_commit_store_filter_session_expiry_and_asgi_upload_limit(
    seeded_db: Database,
    merchant_db: Database,
    worker_db: Database,
    fixed_clock: FixedClock,
) -> None:
    """I2: tenant SSE delivers reverse-committed lower-seq events, filters store_manager in SQL, closes on session expiry.
    I6: pre-multipart ASGI guard rejects oversized Content-Length & chunked streams with 413; poller forwards parser config.
    """
    import asyncio
    import threading
    from psycopg.types.json import Jsonb
    from core.ingest.application.poller import InboxAttachment, InboxMessage, poll_sources_once

    sec_clock = FixedClock(fixed_clock.now())
    idp = FakeIdentityProvider()
    cfg = CoreSettings(
        database_url=merchant_db.dsn,
        demo_mode=False,
        max_invoice_bytes=200_000,
        session_ttl_seconds=60,
        sse_poll_interval_s=0.05,
        sse_keepalive_interval_s=0.2,
        sse_max_idle_seconds=5.0,
    )
    app = create_merchant_app(
        cfg,
        db=merchant_db,
        sim_world=StubSim(),
        gate_client=StubGate(db=seeded_db),
        jwks_verifier=StaticJwksVerifier(idp.jwks(), expected_issuer="sim-world", clock=sec_clock),
        clock=fixed_clock,
        security_clock=sec_clock,
    )
    client = TestClient(app)
    sec_ts = int(sec_clock.now().timestamp())
    owner_jwt = client.post(
        "/m/auth/session", json={"momo_token": idp.issue_momo_token(OWNER_A, TENANT_A, now_ts=sec_ts)}
    ).json()["session_jwt"]
    owner_hdr = {"Authorization": f"Bearer {owner_jwt}"}

    # --- N5: Default sse_max_idle_seconds is finite (300s) ---
    assert CoreSettings().sse_max_idle_seconds == 300.0

    # --- I6a & N10: Pre-multipart ASGI Content-Length guard rejects BEFORE auth/multipart AND preserves CORS headers! ---
    r_cl = client.post(
        "/m/invoices:upload",
        content=b"not-even-multipart",
        headers={
            "Origin": "http://localhost:5173",
            "Content-Length": str(cfg.max_invoice_bytes + 100_000),
            "Content-Type": "multipart/form-data; boundary=x",
        },
    )
    assert r_cl.status_code == 413
    assert r_cl.json()["code"] == "PAYLOAD_TOO_LARGE"
    assert r_cl.headers.get("access-control-allow-origin") in {"*", "http://localhost:5173"}

    # --- I6b: Pre-multipart ASGI chunked streaming guard (no Content-Length) aborts with 413 BEFORE reading later chunks ---
    async def _run_chunked_asgi() -> tuple[int, int]:
        sent_status = 0
        part_hdr = (
            b'--abc\r\nContent-Disposition: form-data; name="file"; filename="big.pdf"\r\n'
            b"Content-Type: application/pdf\r\n\r\n"
        )
        # 5 chunks (500KB total); guard must abort on chunk 3 (>264KB) leaving chunks 4-5 UNREAD!
        chunks = [
            part_hdr + b"A" * 100_000,
            b"B" * 100_000,
            b"C" * 100_000,
            b"D" * 100_000,
            b"E" * 100_000 + b"\r\n--abc--\r\n",
        ]
        idx = 0

        async def _recv():
            nonlocal idx
            if idx < len(chunks):
                b = chunks[idx]
                idx += 1
                return {"type": "http.request", "body": b, "more_body": idx < len(chunks)}
            return {"type": "http.request", "body": b"", "more_body": False}

        async def _send(msg):
            nonlocal sent_status
            if msg["type"] == "http.response.start":
                sent_status = msg["status"]

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/m/invoices:upload",
            "raw_path": b"/m/invoices:upload",
            "query_string": b"",
            "headers": [
                (b"content-type", b"multipart/form-data; boundary=abc"),
                (b"authorization", f"Bearer {owner_jwt}".encode("ascii")),
            ],
        }
        await app(scope, _recv, _send)
        return sent_status, idx

    st_chunk, chunks_read = asyncio.run(_run_chunked_asgi())
    assert st_chunk == 413
    assert chunks_read == 3, f"Expected middleware to abort on chunk 3 leaving 2 chunks unread, read {chunks_read}"

    # --- I6c: Poller propagates default_due_days and max_xml_elements into ingest_invoice ---
    xml_bytes = (DEMO_DATA_DIR / "inbox/attachments/1C26TTN_00001425.xml").read_bytes()
    with worker_db.connect() as wconn:
        mb_a = wconn.execute("SELECT mailbox FROM core.tenants WHERE tenant_id = %s", (TENANT_A,)).fetchone()["mailbox"]

    class OneMsgSource:
        def list_inbox_messages(self, mailbox: str, after: str | None = None):
            if mailbox != mb_a or after is not None:
                return [], None
            return [
                InboxMessage(
                    message_id="msg_cfg_1",
                    from_address="v@test",
                    subject="Inv",
                    body_text="Body",
                    received_at=fixed_clock.now(),
                    attachments=(
                        InboxAttachment(
                            attachment_id="att_cfg",
                            filename="1C26TTN_00001425.xml",
                            content_type="application/xml",
                            raw_bytes=xml_bytes,
                        ),
                    ),
                )
            ], None

        def list_bills(self, wallet_id: str, after: str | None = None):
            return [], None

        def fetch_bill_document(self, bill_id: str) -> bytes | None:
            return None

    # Tiny max_xml_elements=5 rejects the XML attachment cleanly (0 ingested)
    with worker_db.connect() as wconn:
        res_tiny = poll_sources_once(wconn, OneMsgSource(), clock=fixed_clock, max_xml_elements=5)
        assert res_tiny == []
    # Reset cursor via seeded_db so next poll sees the message with default_due_days=15
    with seeded_db.connect() as sconn:
        with sconn.transaction():
            sconn.execute("DELETE FROM core.poll_cursors WHERE tenant_id = %s", (TENANT_A,))
    with worker_db.connect() as wconn:
        res_ok = poll_sources_once(wconn, OneMsgSource(), clock=fixed_clock, default_due_days=15)
        assert len(res_ok) == 1
        inv_due = wconn.execute(
            "SELECT issued_on, due_on FROM core.invoices WHERE invoice_id = %s",
            (res_ok[0].invoice_id,),
        ).fetchone()
    assert inv_due["due_on"] == inv_due["issued_on"] + timedelta(days=15)

    # --- I2a: Tenant SSE delivers reversed-commit lower-seq event AND closes promptly on session expiry ---
    evt_low = new_id("evt")
    evt_high = new_id("evt")

    def _reversed_commit_and_expire() -> None:
        with seeded_db.connect() as c1, seeded_db.connect() as c2:
            # c1 allocates lower seq N (uncommitted)
            c1.execute(
                """
                INSERT INTO core.sse_events (event_id, stream_type, stream_key, tenant_id, store_id, event_type, data, created_at)
                VALUES (%s, 'tenant', %s, %s, NULL, 'notification.created', %s, %s)
                """,
                (evt_low, TENANT_A, TENANT_A, Jsonb({"tag": "low_seq"}), fixed_clock.now()),
            )
            # c2 allocates higher seq N+1 and commits FIRST
            c2.execute(
                """
                INSERT INTO core.sse_events (event_id, stream_type, stream_key, tenant_id, store_id, event_type, data, created_at)
                VALUES (%s, 'tenant', %s, %s, NULL, 'notification.created', %s, %s)
                """,
                (evt_high, TENANT_A, TENANT_A, Jsonb({"tag": "high_seq"}), fixed_clock.now()),
            )
            c2.commit()
            # Let SSE stream poll and deliver high_seq first
            time.sleep(0.20)
            # Now c1 commits lower seq N!
            c1.commit()
            time.sleep(0.20)
            # Expire session on sec_clock -> stream MUST close promptly instead of waiting 5s!
            sec_clock.advance(timedelta(seconds=120))

    t0 = time.monotonic()
    bg = threading.Thread(target=_reversed_commit_and_expire, daemon=True)
    bg.start()
    sse_resp = client.get("/m/events", headers=owner_hdr)
    bg.join(timeout=10)
    elapsed = time.monotonic() - t0
    assert sse_resp.status_code == 200
    assert evt_high in sse_resp.text
    assert evt_low in sse_resp.text, f"Lower-seq late commit {evt_low} was skipped! Body: {sse_resp.text}"
    assert elapsed < 3.0, f"SSE stream did not close promptly on session expiry (took {elapsed:.2f}s)"

    # --- I2b: Store-manager SQL filtering delivers ONLY assigned store's events ---
    with seeded_db.connect() as conn:
        sm = conn.execute(
            "SELECT user_id, store_ids FROM core.users WHERE tenant_id = %s AND role = 'store_manager' LIMIT 1",
            (TENANT_A,),
        ).fetchone()
        other_store = conn.execute(
            "SELECT store_id FROM core.stores WHERE tenant_id = %s AND NOT (store_id = ANY(%s)) LIMIT 1",
            (TENANT_A, list(sm["store_ids"])),
        ).fetchone()
        ev_mine = new_id("evt")
        ev_other = new_id("evt")
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO core.sse_events (event_id, stream_type, stream_key, tenant_id, store_id, event_type, data, created_at)
                VALUES (%s, 'tenant', %s, %s, %s, 'notification.created', %s, %s),
                       (%s, 'tenant', %s, %s, %s, 'notification.created', %s, %s)
                """,
                (
                    ev_other, TENANT_A, TENANT_A, other_store["store_id"], Jsonb({"tag": "other"}), fixed_clock.now(),
                    ev_mine, TENANT_A, TENANT_A, sm["store_ids"][0], Jsonb({"tag": "mine"}), fixed_clock.now(),
                ),
            )
    sm_ts = int(sec_clock.now().timestamp())
    sm_jwt = client.post(
        "/m/auth/session", json={"momo_token": idp.issue_momo_token(sm["user_id"], TENANT_A, now_ts=sm_ts)}
    ).json()["session_jwt"]

    def _expire_sm() -> None:
        time.sleep(0.25)
        sec_clock.advance(timedelta(seconds=120))

    bg2 = threading.Thread(target=_expire_sm, daemon=True)
    bg2.start()
    sm_sse = client.get("/m/events", headers={"Authorization": f"Bearer {sm_jwt}"})
    bg2.join(timeout=10)
    assert sm_sse.status_code == 200
    assert ev_mine in sm_sse.text
    assert ev_other not in sm_sse.text
