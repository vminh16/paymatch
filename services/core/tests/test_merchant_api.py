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
from core.persistence.db import Database
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

    def issue_momo_token(self, user_id: str, tenant_id: str) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                "iss": "sim-world",
                "aud": "paymatch",
                "sub": user_id,
                "tenant_id": tenant_id,
                "token_use": "momo_token",
                "iat": now,
                "exp": now + 3600,
                "jti": new_id("jti"),
            },
            self._priv,
            algorithm="EdDSA",
            headers={"kid": self.kid},
        )

    def issue_auth_proof(self, user_id: str, ah: str, *, jti: str | None = None) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                "iss": "sim-world",
                "aud": "paymatch",
                "sub": user_id,
                "action_hash": ah,
                "jti": jti or new_id("jti"),
                "iat": now,
                "exp": now + 300,
                "amr": ["otp"],
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
    seeded_db: Database, fixed_clock: FixedClock
) -> None:
    idp = FakeIdentityProvider()
    gate = StubGate(db=seeded_db)
    cfg = CoreSettings(database_url=seeded_db.dsn, demo_mode=True, seed_dir=DEMO_SEED_DIR)
    app = create_merchant_app(
        cfg,
        db=seeded_db,
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
def test_demo_reset_not_mounted_when_demo_mode_false(seeded_db: Database, fixed_clock: FixedClock) -> None:
    idp = FakeIdentityProvider()
    cfg = CoreSettings(database_url=seeded_db.dsn, demo_mode=False)
    app = create_merchant_app(
        cfg,
        db=seeded_db,
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
