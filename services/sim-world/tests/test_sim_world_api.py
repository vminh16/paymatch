"""Comprehensive API, auth, behavior, and OpenAPI contract tests for sim-world."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from jwt.algorithms import OKPAlgorithm
from openapi_spec_validator import validate as validate_openapi_spec
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from sim_world.app import create_app
from sim_world.config import Settings
from sim_world.webhooks import WebhookDispatcher

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_DIR = REPO_ROOT / "services" / "sim-world" / "data" / "demo"
OPENAPI_PATH = REPO_ROOT / "contracts" / "openapi" / "sim-world.yaml"

CORE_KEY = "test-core-secret"
GATE_KEY = "test-gate-secret"
WEBHOOK_KEY = "test-webhook-secret"

CORE_HEADERS = {"X-Service-Key": CORE_KEY}
GATE_HEADERS = {"X-Service-Key": GATE_KEY}


@pytest.fixture(scope="module")
def openapi_spec() -> dict[str, Any]:
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    validate_openapi_spec(spec)
    return spec


@pytest.fixture(scope="module")
def schema_validator(openapi_spec: dict[str, Any]):
    """Validate response payloads against schemas defined in contracts/openapi/sim-world.yaml."""
    root_uri = "urn:paymatch:sim-world"
    resource = Resource.from_contents(openapi_spec, default_specification=DRAFT202012)
    registry = Registry().with_resource(root_uri, resource)

    def _validate(
        path_template: str,
        method: str,
        status_code: int,
        payload: Any,
        content_type: str = "application/json",
    ) -> None:
        op = openapi_spec["paths"][path_template][method.lower()]
        resp_spec = op["responses"][str(status_code)]
        if "$ref" in resp_spec:
            ref_name = resp_spec["$ref"].split("/")[-1]
            resp_spec = openapi_spec["components"]["responses"][ref_name]
        schema = resp_spec["content"][content_type]["schema"]
        validator = Draft202012Validator(
            {"$ref": f"{root_uri}#/paths/{path_template.replace('~', '~0').replace('/', '~1')}/{method.lower()}/responses/{status_code}/content/{content_type.replace('/', '~1')}/schema"}
            if "$ref" not in op["responses"][str(status_code)]
            else schema,
            registry=registry,
        )
        errors = list(validator.iter_errors(payload))
        assert not errors, f"Schema validation failed for {method} {path_template} {status_code}: {errors}"

    return _validate


@pytest.fixture
def demo_ids() -> dict[str, Any]:
    identity = json.loads((DEMO_DIR / "identity.json").read_text(encoding="utf-8"))
    wallets = json.loads((DEMO_DIR / "wallets.json").read_text(encoding="utf-8"))
    chat = json.loads((DEMO_DIR / "chat.json").read_text(encoding="utf-8"))
    rev = json.loads((DEMO_DIR / "revenue.json").read_text(encoding="utf-8"))
    scenarios = {
        s["template_id"]: s
        for s in json.loads((DEMO_DIR / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    }
    return {
        "owner_user": identity["merchant_users"][0],
        "staff_user": identity["staff_users"][0],
        "demo_otp": identity["demo_otp"],
        "primary_wallet": wallets["wallets"][0],
        "first_ext_acct": wallets["external_bank_accounts"][0],
        "failure_accts": {
            a["simulate_failure"]: a
            for a in wallets["external_bank_accounts"]
            if a.get("simulate_failure")
        },
        "first_thread": chat["threads"][0],
        "first_revenue": rev["revenues"][0],
        "scenarios": scenarios,
    }


def _make_client(*, demo_mode: bool = True, dispatcher: WebhookDispatcher | None = None) -> TestClient:
    settings = Settings(
        data_dir=REPO_ROOT / "services" / "sim-world" / "data",
        default_dataset="demo",
        default_seed=42,
        demo_mode=demo_mode,
        core_service_key=CORE_KEY,
        gate_service_key=GATE_KEY,
        core_internal_url=None,
        webhook_service_key=WEBHOOK_KEY,
    )
    app = create_app(settings, webhook_dispatcher=dispatcher)
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    return _make_client(demo_mode=True)


# --- Contract & System ---


def test_openapi_spec_is_valid_and_matches_all_mounted_routes(openapi_spec: dict[str, Any], client: TestClient) -> None:
    app_schema = client.app.openapi()
    mounted = {
        (path, method.lower())
        for path, ops in app_schema["paths"].items()
        for method in ops
        if method.lower() in {"get", "post", "patch", "delete", "put"}
    }
    documented = {
        (path, method.lower())
        for path, ops in openapi_spec["paths"].items()
        for method in ops
        if method.lower() in {"get", "post", "patch", "delete", "put"}
    }
    assert mounted == documented


def test_loader_does_not_require_core_seed(tmp_path: Path) -> None:
    """sim-world loads demo/*.json, inbox/, bills/ and never touches core_seed/."""
    import shutil

    target = tmp_path / "demo_no_core"
    shutil.copytree(DEMO_DIR, target, ignore=shutil.ignore_patterns("core_seed"))
    assert not (target / "core_seed").exists()

    settings = Settings(
        data_dir=tmp_path,
        default_dataset="demo_no_core",
        default_seed=42,
        demo_mode=True,
        core_service_key=CORE_KEY,
        gate_service_key=GATE_KEY,
    )
    app = create_app(settings)
    c = TestClient(app)
    r = c.get("/sim/readyz")
    assert r.status_code == 200
    assert r.json()["dataset"] == "demo_no_core"


def test_healthz_and_readyz(client: TestClient, schema_validator) -> None:
    r_health = client.get("/sim/healthz")
    assert r_health.status_code == 200
    assert "X-Request-Id" in r_health.headers
    schema_validator("/sim/healthz", "get", 200, r_health.json())

    r_ready = client.get("/sim/readyz")
    assert r_ready.status_code == 200
    body = r_ready.json()
    assert body["status"] == "ready"
    assert body["dataset"] == "demo"
    schema_validator("/sim/readyz", "get", 200, body)


# --- Authentication & DEMO_MODE ---


def test_service_key_required_and_role_enforced(demo_ids: dict[str, Any], schema_validator) -> None:
    strict_client = _make_client(demo_mode=False)
    wallet_id = demo_ids["primary_wallet"]["wallet_id"]

    # Missing key -> 401 RFC 9457 everywhere (including identity/scenario when DEMO_MODE=false)
    for method, url in [
        ("get", "/sim/identity/.well-known/jwks.json"),
        ("get", "/sim/scenario/clock"),
        ("get", f"/sim/rails/wallets/{wallet_id}"),
        ("get", "/sim/inbox/messages?mailbox=hoadon@laxanh-fnb.example"),
        ("get", "/sim/tax/taxpayers/0999010001"),
    ]:
        r = getattr(strict_client, method)(url)
        assert r.status_code == 401, (method, url, r.text)
        assert r.headers["content-type"].startswith("application/problem+json")
        assert r.json()["code"] == "UNAUTHENTICATED"

    # Bad key -> 401
    r_bad = strict_client.get(
        f"/sim/rails/wallets/{wallet_id}",
        headers={"X-Service-Key": "wrong-key"},
    )
    assert r_bad.status_code == 401
    assert r_bad.json()["code"] == "UNAUTHENTICATED"

    # Core key cannot call gate-only endpoints -> 403
    r_core_to_gate = strict_client.post(
        "/sim/rails/transfers",
        headers=CORE_HEADERS,
        json={
            "idempotency_key": "k1",
            "from_wallet_id": wallet_id,
            "to": {
                "bank_code": "VNMB01",
                "account_number": "990010000001",
                "account_name": "CONG TY TNHH CA PHE RANG MOC TAY NGUYEN",
            },
            "amount_vnd": 1000,
            "memo": "test",
        },
    )
    assert r_core_to_gate.status_code == 403
    assert r_core_to_gate.json()["code"] == "FORBIDDEN"

    # Gate key cannot call core-only endpoints -> 403
    r_gate_to_core = strict_client.get(
        "/sim/inbox/messages?mailbox=hoadon@laxanh-fnb.example",
        headers=GATE_HEADERS,
    )
    assert r_gate_to_core.status_code == 403
    assert r_gate_to_core.json()["code"] == "FORBIDDEN"

    # In DEMO_MODE=true, /sim/identity/* and /sim/scenario* are open without key,
    # while /sim/inbox/* and /sim/rails/* still require X-Service-Key.
    demo_client = _make_client(demo_mode=True)
    assert demo_client.get("/sim/identity/.well-known/jwks.json").status_code == 200
    assert demo_client.get("/sim/scenario/clock").status_code == 200
    assert demo_client.get("/sim/scenario/catalog").status_code == 200
    assert demo_client.get(f"/sim/rails/wallets/{wallet_id}").status_code == 401
    assert demo_client.get("/sim/inbox/messages?mailbox=hoadon@laxanh-fnb.example").status_code == 401


# --- Identity ---


def test_identity_jwks_tokens_and_step_up_flow(
    client: TestClient,
    demo_ids: dict[str, Any],
    schema_validator,
) -> None:
    r_jwks = client.get("/sim/identity/.well-known/jwks.json")
    assert r_jwks.status_code == 200
    jwks = r_jwks.json()
    schema_validator("/sim/identity/.well-known/jwks.json", "get", 200, jwks)
    pub_key = OKPAlgorithm.from_jwk(json.dumps(jwks["keys"][0]))

    # Merchant token
    owner = demo_ids["owner_user"]
    r_mt = client.post("/sim/identity/merchant-tokens", json={"user_id": owner["user_id"]})
    assert r_mt.status_code == 200
    schema_validator("/sim/identity/merchant-tokens", "post", 200, r_mt.json())
    momo_token = r_mt.json()["momo_token"]
    m_claims = jwt.decode(momo_token, pub_key, algorithms=["EdDSA"], audience="paymatch")
    assert m_claims["sub"] == owner["user_id"]
    assert m_claims["tenant_id"] == owner["tenant_id"]
    assert m_claims["role"] == "owner"

    # Staff token (and verify seeded staff_roles match console-api.md)
    identity = json.loads((DEMO_DIR / "identity.json").read_text(encoding="utf-8"))
    all_staff_roles = {r for s in identity["staff_users"] for r in s["staff_roles"]}
    assert all_staff_roles == {"risk_analyst", "risk_lead", "support_agent", "platform_admin"}

    staff = demo_ids["staff_user"]
    r_st = client.post("/sim/identity/staff-tokens", json={"staff_id": staff["staff_id"]})
    assert r_st.status_code == 200
    schema_validator("/sim/identity/staff-tokens", "post", 200, r_st.json())
    s_claims = jwt.decode(
        r_st.json()["sso_token"],
        pub_key,
        algorithms=["EdDSA"],
        audience="paymatch-console",
    )
    assert s_claims["sub"] == staff["staff_id"]
    assert s_claims["staff_roles"] == staff["staff_roles"]

    # Step-up challenge -> verify
    action_hash = hashlib.sha256(b"approve:inv_123").hexdigest()
    r_ch = client.post(
        "/sim/identity/step-up-challenges",
        json={"momo_token": momo_token, "action_hash": action_hash},
    )
    assert r_ch.status_code == 200
    ch = r_ch.json()
    schema_validator("/sim/identity/step-up-challenges", "post", 200, ch)
    assert ch["challenge_id"].startswith("chl_")
    assert ch["demo_otp"] == demo_ids["demo_otp"]

    # Wrong OTP -> 403
    r_wrong = client.post(
        f"/sim/identity/step-up-challenges/{ch['challenge_id']}:verify",
        json={"otp": "000000"},
    )
    assert r_wrong.status_code == 403
    assert r_wrong.json()["code"] == "STEP_UP_INVALID"

    # Right OTP -> 200 auth_proof JWT
    r_ok = client.post(
        f"/sim/identity/step-up-challenges/{ch['challenge_id']}:verify",
        json={"otp": demo_ids["demo_otp"]},
    )
    assert r_ok.status_code == 200
    schema_validator("/sim/identity/step-up-challenges/{challenge_id}:verify", "post", 200, r_ok.json())
    proof_claims = jwt.decode(
        r_ok.json()["auth_proof"],
        pub_key,
        algorithms=["EdDSA"],
        audience="paymatch",
    )
    assert proof_claims["sub"] == owner["user_id"]
    assert proof_claims["action_hash"] == action_hash
    assert proof_claims["amr"] == ["otp"]
    assert proof_claims["exp"] - proof_claims["iat"] == 300
    assert "jti" in proof_claims

    # Re-verify same challenge -> 409 INVALID_STATE
    r_dup = client.post(
        f"/sim/identity/step-up-challenges/{ch['challenge_id']}:verify",
        json={"otp": demo_ids["demo_otp"]},
    )
    assert r_dup.status_code == 409
    assert r_dup.json()["code"] == "INVALID_STATE"


# --- Rails: Transfers, Wallets, Cards, Escrows ---


def test_transfers_idempotency_and_failure_codes(
    client: TestClient,
    demo_ids: dict[str, Any],
    schema_validator,
) -> None:
    wallet = demo_ids["primary_wallet"]
    wallet_id = wallet["wallet_id"]
    initial_balance = wallet["balance_vnd"]
    acct = demo_ids["first_ext_acct"]

    r_w0 = client.get(f"/sim/rails/wallets/{wallet_id}", headers=CORE_HEADERS)
    assert r_w0.status_code == 200
    assert r_w0.json()["balance_vnd"] == initial_balance
    schema_validator("/sim/rails/wallets/{wallet_id}", "get", 200, r_w0.json())

    transfer_body = {
        "idempotency_key": "pi_coffee_001",
        "from_wallet_id": wallet_id,
        "to": {
            "bank_code": acct["bank_code"],
            "account_number": acct["account_number"],
            "account_name": acct["account_name"],
        },
        "amount_vnd": 26_500_000,
        "memo": "0999010001 · 1C26TTN · 00001425",
    }
    r1 = client.post("/sim/rails/transfers", headers=GATE_HEADERS, json=transfer_body)
    assert r1.status_code == 200
    t1 = r1.json()
    assert t1["status"] == "settled"
    assert t1["failure_code"] is None
    assert t1["settled_at"] is not None
    schema_validator("/sim/rails/transfers", "post", 200, t1)

    # Same idempotency_key -> identical result, NO double debit
    r2 = client.post("/sim/rails/transfers", headers=GATE_HEADERS, json=transfer_body)
    assert r2.status_code == 200
    assert r2.json() == t1

    r_w1 = client.get(f"/sim/rails/wallets/{wallet_id}", headers=CORE_HEADERS)
    assert r_w1.json()["balance_vnd"] == initial_balance - 26_500_000

    # GET transfer status by key
    r_get = client.get("/sim/rails/transfers/pi_coffee_001", headers=GATE_HEADERS)
    assert r_get.status_code == 200
    assert r_get.json() == t1
    schema_validator("/sim/rails/transfers/{idempotency_key}", "get", 200, r_get.json())

    # Same key with different payload -> 409 IDEMPOTENCY_KEY_REUSED
    diff_body = {**transfer_body, "amount_vnd": 100_000}
    r_conflict = client.post("/sim/rails/transfers", headers=GATE_HEADERS, json=diff_body)
    assert r_conflict.status_code == 409
    assert r_conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

    # Simulated failure accounts do not debit wallet
    bal_before_fail = client.get(f"/sim/rails/wallets/{wallet_id}", headers=CORE_HEADERS).json()["balance_vnd"]
    for code, fail_acct in demo_ids["failure_accts"].items():
        rf = client.post(
            "/sim/rails/transfers",
            headers=GATE_HEADERS,
            json={
                "idempotency_key": f"pi_fail_{code}",
                "from_wallet_id": wallet_id,
                "to": {
                    "bank_code": fail_acct["bank_code"],
                    "account_number": fail_acct["account_number"],
                    "account_name": fail_acct["account_name"],
                },
                "amount_vnd": 500_000,
                "memo": f"test {code}",
            },
        )
        assert rf.status_code == 200
        body = rf.json()
        assert body["status"] == "failed"
        assert body["failure_code"] == code
        assert body["settled_at"] is None
        schema_validator("/sim/rails/transfers", "post", 200, body)
    bal_after_fail = client.get(f"/sim/rails/wallets/{wallet_id}", headers=CORE_HEADERS).json()["balance_vnd"]
    assert bal_after_fail == bal_before_fail


def test_virtual_card_single_use_wrong_merchant_decline_and_webhook(
    demo_ids: dict[str, Any],
    schema_validator,
) -> None:
    wallet_id = demo_ids["primary_wallet"]["wallet_id"]
    initial_balance = demo_ids["primary_wallet"]["balance_vnd"]

    # 1. Without CORE_INTERNAL_URL: declines recorded in scenario state and skipped HTTP
    c_local = _make_client(demo_mode=True)
    r_card = c_local.post(
        "/sim/rails/cards",
        headers=GATE_HEADERS,
        json={
            "idempotency_key": "pi_pos_001",
            "from_wallet_id": wallet_id,
            "merchant_id": "mrc_pos_cloud_01",
            "amount_vnd": 12_000_000,
            "single_use": True,
        },
    )
    assert r_card.status_code == 200
    card = r_card.json()
    assert card["status"] == "captured"
    schema_validator("/sim/rails/cards", "post", 200, card)

    # Idempotent card issue -> no double debit
    r_card_dup = c_local.post(
        "/sim/rails/cards",
        headers=GATE_HEADERS,
        json={
            "idempotency_key": "pi_pos_001",
            "from_wallet_id": wallet_id,
            "merchant_id": "mrc_pos_cloud_01",
            "amount_vnd": 12_000_000,
            "single_use": True,
        },
    )
    assert r_card_dup.status_code == 200
    assert r_card_dup.json() == card
    assert (
        c_local.get(f"/sim/rails/wallets/{wallet_id}", headers=CORE_HEADERS).json()["balance_vnd"]
        == initial_balance - 12_000_000
    )

    # Wrong merchant swipe -> declined wrong_merchant + webhook recorded
    r_wrong = c_local.post(
        f"/sim/scenario/cards/{card['card_id']}:swipe",
        json={"merchant_id": "mrc_unknown_99", "amount_vnd": 12_000_000},
    )
    assert r_wrong.status_code == 200
    assert r_wrong.json() == {"approved": False, "reason": "wrong_merchant"}
    schema_validator("/sim/scenario/cards/{card_id}:swipe", "post", 200, r_wrong.json())

    # Second swipe at original merchant -> declined already_used (single-use)
    r_reuse = c_local.post(
        f"/sim/scenario/cards/{card['card_id']}:swipe",
        json={"merchant_id": "mrc_pos_cloud_01", "amount_vnd": 12_000_000},
    )
    assert r_reuse.status_code == 200
    assert r_reuse.json() == {"approved": False, "reason": "already_used"}
    schema_validator("/sim/scenario/cards/{card_id}:swipe", "post", 200, r_reuse.json())

    # GET card detail shows 1 capture + 2 declined attempts
    r_detail = c_local.get(f"/sim/rails/cards/{card['card_id']}", headers=GATE_HEADERS)
    assert r_detail.status_code == 200
    detail = r_detail.json()
    assert detail["status"] == "captured"
    assert len(detail["captures"]) == 1
    assert [d["reason"] for d in detail["declined_attempts"]] == ["wrong_merchant", "already_used"]
    schema_validator("/sim/rails/cards/{card_id}", "get", 200, detail)

    # Scenario state records both webhooks (delivered=False because CORE_INTERNAL_URL unset)
    r_state = c_local.get("/sim/scenario/state")
    assert r_state.status_code == 200
    state = r_state.json()
    schema_validator("/sim/scenario/state", "get", 200, state)
    card_wh = [w for w in state["webhooks"] if w["type"] == "card.authorization_declined"]
    assert len(card_wh) == 2
    assert card_wh[0]["data"] == {
        "card_id": card["card_id"],
        "merchant_id": "mrc_unknown_99",
        "reason": "wrong_merchant",
    }
    assert card_wh[0]["delivered"] is False

    # 2. With CORE_INTERNAL_URL configured: webhook is POSTed to /webhooks/rails
    received: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append((str(request.url), dict(request.headers), json.loads(request.content)))
        return httpx.Response(204)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "http://internal-api:8003/internal",
        service_key=WEBHOOK_KEY,
        client_factory=lambda: mock_client,
        sleep_fn=lambda _: None,
    )
    c_hook = _make_client(demo_mode=True, dispatcher=dispatcher)
    c2 = c_hook.post(
        "/sim/rails/cards",
        headers=GATE_HEADERS,
        json={
            "idempotency_key": "pi_pos_002",
            "from_wallet_id": wallet_id,
            "merchant_id": "mrc_pos_cloud_01",
            "amount_vnd": 12_000_000,
        },
    ).json()
    c_hook.post(
        f"/sim/scenario/cards/{c2['card_id']}:swipe",
        json={"merchant_id": "mrc_unknown_99", "amount_vnd": 12_000_000},
    )
    assert len(received) == 1
    url, hdrs, body = received[0]
    assert url == "http://internal-api:8003/internal/webhooks/rails"
    assert hdrs["x-service-key"] == WEBHOOK_KEY
    assert body["type"] == "card.authorization_declined"
    assert body["data"] == {
        "card_id": c2["card_id"],
        "merchant_id": "mrc_unknown_99",
        "reason": "wrong_merchant",
    }
    hook_state = c_hook.get("/sim/scenario/state").json()
    assert hook_state["webhooks"][0]["delivered"] is True


def test_escrows_hold_release_and_refund(
    client: TestClient,
    demo_ids: dict[str, Any],
    schema_validator,
) -> None:
    wallet_id = demo_ids["primary_wallet"]["wallet_id"]
    start_balance = demo_ids["primary_wallet"]["balance_vnd"]
    acct = demo_ids["first_ext_acct"]

    # Escrow 1: hold -> release
    r_e1 = client.post(
        "/sim/rails/escrows",
        headers=GATE_HEADERS,
        json={
            "idempotency_key": "esc_001",
            "from_wallet_id": wallet_id,
            "to": {
                "bank_code": acct["bank_code"],
                "account_number": acct["account_number"],
                "account_name": acct["account_name"],
            },
            "amount_vnd": 8_800_000,
            "expires_on": "2026-12-10",
        },
    )
    assert r_e1.status_code == 200
    e1 = r_e1.json()
    assert e1["status"] == "held"
    schema_validator("/sim/rails/escrows", "post", 200, e1)
    assert (
        client.get(f"/sim/rails/wallets/{wallet_id}", headers=CORE_HEADERS).json()["balance_vnd"]
        == start_balance - 8_800_000
    )

    r_rel = client.post(
        f"/sim/rails/escrows/{e1['rail_escrow_id']}:release",
        headers=GATE_HEADERS,
        json={"idempotency_key": "rel_001"},
    )
    assert r_rel.status_code == 200
    assert r_rel.json() == {"status": "released"}
    schema_validator("/sim/rails/escrows/{rail_escrow_id}:release", "post", 200, r_rel.json())

    # Idempotent release
    assert (
        client.post(
            f"/sim/rails/escrows/{e1['rail_escrow_id']}:release",
            headers=GATE_HEADERS,
            json={"idempotency_key": "rel_001"},
        ).status_code
        == 200
    )

    # Refunding an already-released escrow -> 409 INVALID_STATE
    r_bad_ref = client.post(
        f"/sim/rails/escrows/{e1['rail_escrow_id']}:refund",
        headers=GATE_HEADERS,
        json={"idempotency_key": "ref_after_rel"},
    )
    assert r_bad_ref.status_code == 409

    # Escrow 2: hold -> refund restores balance
    r_e2 = client.post(
        "/sim/rails/escrows",
        headers=GATE_HEADERS,
        json={
            "idempotency_key": "esc_002",
            "from_wallet_id": wallet_id,
            "to": {
                "bank_code": acct["bank_code"],
                "account_number": acct["account_number"],
                "account_name": acct["account_name"],
            },
            "amount_vnd": 5_000_000,
            "expires_on": "2026-12-10",
        },
    )
    e2 = r_e2.json()
    r_ref = client.post(
        f"/sim/rails/escrows/{e2['rail_escrow_id']}:refund",
        headers=GATE_HEADERS,
        json={"idempotency_key": "ref_002"},
    )
    assert r_ref.status_code == 200
    assert r_ref.json() == {"status": "refunded"}
    schema_validator("/sim/rails/escrows/{rail_escrow_id}:refund", "post", 200, r_ref.json())
    assert (
        client.get(f"/sim/rails/wallets/{wallet_id}", headers=CORE_HEADERS).json()["balance_vnd"]
        == start_balance - 8_800_000
    )


# --- Inbox, Attachments, Bills, Chat, Scenario Send ---


def test_invoices_send_brd01_attachment_bytes_and_bills_and_chat(
    client: TestClient,
    demo_ids: dict[str, Any],
    schema_validator,
) -> None:
    # Send BRD_01_COFFEE_26M5 and confirm inbox has exact XML attachment bytes
    r_send = client.post(
        "/sim/scenario/invoices:send",
        json={"template_id": "BRD_01_COFFEE_26M5"},
    )
    assert r_send.status_code == 200
    send_body = r_send.json()
    schema_validator("/sim/scenario/invoices:send", "post", 200, send_body)
    brd01_msg_id = send_body["message_id"]

    r_inbox = client.get(
        "/sim/inbox/messages",
        headers=CORE_HEADERS,
        params={"mailbox": "hoadon@laxanh-fnb.example"},
    )
    assert r_inbox.status_code == 200
    inbox_page = r_inbox.json()
    schema_validator("/sim/inbox/messages", "get", 200, inbox_page)
    brd01_msg = next(m for m in inbox_page["items"] if m["message_id"] == brd01_msg_id)
    att = brd01_msg["attachments"][0]
    assert att["filename"] == "1C26TTN_00001425.xml"

    r_att = client.get(
        f"/sim/inbox/messages/{brd01_msg_id}/attachments/{att['attachment_id']}",
        headers=CORE_HEADERS,
    )
    assert r_att.status_code == 200
    expected_xml = (DEMO_DIR / "inbox" / "attachments" / "1C26TTN_00001425.xml").read_bytes()
    assert r_att.content == expected_xml
    assert att["size"] == len(expected_xml)

    # Pagination + from filter on inbox
    r_from = client.get(
        "/sim/inbox/messages",
        headers=CORE_HEADERS,
        params={"mailbox": "hoadon@laxanh-fnb.example", "from": "ketoan@caphetaynguyen.example"},
    )
    assert r_from.status_code == 200
    assert len(r_from.json()["items"]) == 1

    # Send BRD_02_MILK_31M_ZALO_PAYEE -> delivers both inbox email and Zalo scam chat message
    r_brd02 = client.post(
        "/sim/scenario/invoices:send",
        json={"template_id": "BRD_02_MILK_31M_ZALO_PAYEE"},
    )
    assert r_brd02.status_code == 200
    brd02 = r_brd02.json()
    schema_validator("/sim/scenario/invoices:send", "post", 200, brd02)
    assert brd02["message_id"] is not None
    assert len(brd02["chat_message_ids"]) == 1

    # Send EDGE_BULK_OVER_DAILY -> delivers 3 emails
    r_bulk = client.post(
        "/sim/scenario/invoices:send",
        json={"template_id": "EDGE_BULK_OVER_DAILY"},
    )
    assert r_bulk.status_code == 200
    assert len(r_bulk.json()["extra_message_ids"]) == 2

    # Send BRD_06_WATER_STORE3_4M2 -> delivers utility bill + byte-exact XML
    r_brd06 = client.post(
        "/sim/scenario/invoices:send",
        json={"template_id": "BRD_06_WATER_STORE3_4M2"},
    )
    assert r_brd06.status_code == 200
    bill_id = r_brd06.json()["bill_id"]
    schema_validator("/sim/scenario/invoices:send", "post", 200, r_brd06.json())

    r_bills = client.get(
        "/sim/bills",
        headers=CORE_HEADERS,
        params={"wallet_id": demo_ids["primary_wallet"]["wallet_id"]},
    )
    assert r_bills.status_code == 200
    bills_page = r_bills.json()
    schema_validator("/sim/bills", "get", 200, bills_page)
    assert any(b["bill_id"] == bill_id for b in bills_page["items"])

    r_doc = client.get(f"/sim/bills/{bill_id}/document", headers=CORE_HEADERS)
    assert r_doc.status_code == 200
    expected_bill_xml = (DEMO_DIR / "bills" / "documents" / "water_sto03_2026-11.xml").read_bytes()
    assert r_doc.content == expected_bill_xml

    # Chat threads, messages, and scenario injection
    thr = demo_ids["first_thread"]
    r_threads = client.get(
        "/sim/chat/threads",
        headers=CORE_HEADERS,
        params={"tenant_ref": thr["tenant_ref"], "counterparty_phone": thr["counterparty_phone"]},
    )
    assert r_threads.status_code == 200
    schema_validator("/sim/chat/threads", "get", 200, r_threads.json())
    assert len(r_threads.json()) == 1

    r_inject = client.post(
        "/sim/scenario/chat-messages",
        json={"thread_id": thr["thread_id"], "text": "Chị chuyển gấp qua STK mới giúp em nhé!"},
    )
    assert r_inject.status_code == 200
    schema_validator("/sim/scenario/chat-messages", "post", 200, r_inject.json())

    r_msgs = client.get(
        f"/sim/chat/threads/{thr['thread_id']}/messages",
        headers=CORE_HEADERS,
    )
    assert r_msgs.status_code == 200
    schema_validator("/sim/chat/threads/{thread_id}/messages", "get", 200, r_msgs.json())
    assert any("STK mới" in m["text"] for m in r_msgs.json())


# --- Official Lookups ---


def test_official_lookups_einvoice_tax_simo_revenue(
    client: TestClient,
    demo_ids: dict[str, Any],
    schema_validator,
) -> None:
    # Einvoice portal: leading zeros normalized ("1425" == "00001425")
    for num in ("00001425", "1425"):
        r_e = client.get(
            "/sim/einvoice/invoices",
            headers=CORE_HEADERS,
            params={"seller_tax_id": "0999010001", "symbol": "1C26TTN", "number": num},
        )
        assert r_e.status_code == 200
        body = r_e.json()
        assert body["found"] is True
        assert body["invoice_status_code"] == 1
        assert body["processing_status_code"] == 5
        assert body["total_vnd"] == 26_500_000
        schema_validator("/sim/einvoice/invoices", "get", 200, body)

    # Einvoice portal: negative adjustment invoice with related_invoice
    r_neg = client.get(
        "/sim/einvoice/invoices",
        headers=CORE_HEADERS,
        params={"seller_tax_id": "0999010001", "symbol": "1C26TTN", "number": "1430"},
    )
    assert r_neg.status_code == 200
    assert r_neg.json()["total_vnd"] == -1_620_000
    assert r_neg.json()["related_invoice"] is not None
    schema_validator("/sim/einvoice/invoices", "get", 200, r_neg.json())

    # Einvoice portal: not found
    r_nf = client.get(
        "/sim/einvoice/invoices",
        headers=CORE_HEADERS,
        params={"seller_tax_id": "0999999999", "symbol": "1C26ZZZ", "number": "9999"},
    )
    assert r_nf.status_code == 200
    assert r_nf.json()["found"] is False
    schema_validator("/sim/einvoice/invoices", "get", 200, r_nf.json())

    # Taxpayers
    r_tp = client.get("/sim/tax/taxpayers/0999010001", headers=CORE_HEADERS)
    assert r_tp.status_code == 200
    assert r_tp.json()["status_code"] == "00"
    schema_validator("/sim/tax/taxpayers/{tax_id}", "get", 200, r_tp.json())

    r_tp_404 = client.get("/sim/tax/taxpayers/0999999999", headers=CORE_HEADERS)
    assert r_tp_404.status_code == 404
    assert r_tp_404.json()["code"] == "NOT_FOUND"

    # Tax risk list
    r_risk_yes = client.get("/sim/tax/risk-list/0999090001", headers=CORE_HEADERS)
    assert r_risk_yes.status_code == 200
    assert r_risk_yes.json()["listed"] is True
    schema_validator("/sim/tax/risk-list/{tax_id}", "get", 200, r_risk_yes.json())

    r_risk_no = client.get("/sim/tax/risk-list/0999010001", headers=CORE_HEADERS)
    assert r_risk_no.status_code == 200
    assert r_risk_no.json() == {"listed": False, "list_name": None, "listed_on": None}
    schema_validator("/sim/tax/risk-list/{tax_id}", "get", 200, r_risk_no.json())

    # SIMO indicators
    listed_hash = hashlib.sha256(b"VNMB03:998855667788").hexdigest()
    r_simo_yes = client.get(
        "/sim/simo/indicators:check",
        headers=CORE_HEADERS,
        params={"kind": "account_hash", "value_hash": listed_hash},
    )
    assert r_simo_yes.status_code == 200
    assert r_simo_yes.json() == {"listed": True, "list_ref": "SIMO-2026-00991"}
    schema_validator("/sim/simo/indicators:check", "get", 200, r_simo_yes.json())

    r_simo_no = client.get(
        "/sim/simo/indicators:check",
        headers=CORE_HEADERS,
        params={"kind": "tax_id", "value_hash": "0" * 64},
    )
    assert r_simo_no.status_code == 200
    assert r_simo_no.json() == {"listed": False, "list_ref": None}
    schema_validator("/sim/simo/indicators:check", "get", 200, r_simo_no.json())

    # Revenue
    rev = demo_ids["first_revenue"]
    r_rev = client.get(
        "/sim/revenue",
        headers=CORE_HEADERS,
        params={
            "wallet_id": rev["wallet_id"],
            "store_ref": rev["store_ref"],
            "month": rev["month"],
        },
    )
    assert r_rev.status_code == 200
    assert r_rev.json() == {
        "revenue_vnd": rev["revenue_vnd"],
        "transaction_count": rev["transaction_count"],
    }
    schema_validator("/sim/revenue", "get", 200, r_rev.json())


# --- Scenario Catalog, Clock Advance, Reset ---


def test_scenario_catalog_clock_advance_and_reset_reloads_state(
    client: TestClient,
    demo_ids: dict[str, Any],
    schema_validator,
) -> None:
    r_cat = client.get("/sim/scenario/catalog")
    assert r_cat.status_code == 200
    cat = r_cat.json()
    assert len(cat) == 49
    schema_validator("/sim/scenario/catalog", "get", 200, cat)

    # Clock starts at manifest base_clock
    r_clk0 = client.get("/sim/scenario/clock")
    assert r_clk0.status_code == 200
    assert r_clk0.json() == {"now": "2026-11-26T08:00:00+07:00"}
    schema_validator("/sim/scenario/clock", "get", 200, r_clk0.json())

    # Advance clock forward
    r_adv = client.post(
        "/sim/scenario/clock:advance",
        json={"to": "2026-11-27T10:30:00+07:00"},
    )
    assert r_adv.status_code == 200
    assert r_adv.json() == {"now": "2026-11-27T10:30:00+07:00"}
    schema_validator("/sim/scenario/clock:advance", "post", 200, r_adv.json())

    # Backward clock rejected with 400 VALIDATION_FAILED
    r_back = client.post(
        "/sim/scenario/clock:advance",
        json={"to": "2026-11-26T09:00:00+07:00"},
    )
    assert r_back.status_code == 400
    assert r_back.json()["code"] == "VALIDATION_FAILED"

    # Mutate wallet + inbox + cards
    wallet_id = demo_ids["primary_wallet"]["wallet_id"]
    initial_balance = demo_ids["primary_wallet"]["balance_vnd"]
    client.post(
        "/sim/rails/cards",
        headers=GATE_HEADERS,
        json={
            "idempotency_key": "pi_reset_card",
            "from_wallet_id": wallet_id,
            "merchant_id": "mrc_pos_cloud_01",
            "amount_vnd": 10_000_000,
        },
    )
    client.post("/sim/scenario/invoices:send", json={"template_id": "BRD_03_CUPS_SHRINKFLATION"})
    assert (
        client.get(f"/sim/rails/wallets/{wallet_id}", headers=CORE_HEADERS).json()["balance_vnd"]
        == initial_balance - 10_000_000
    )

    # Reset reloads clean state
    r_reset = client.post("/sim/scenario:reset", json={"dataset": "demo", "seed": 42})
    assert r_reset.status_code == 200
    schema_validator("/sim/scenario:reset", "post", 200, r_reset.json())

    assert client.get("/sim/scenario/clock").json() == {"now": "2026-11-26T08:00:00+07:00"}
    assert (
        client.get(f"/sim/rails/wallets/{wallet_id}", headers=CORE_HEADERS).json()["balance_vnd"]
        == initial_balance
    )
    state_after = client.get("/sim/scenario/state").json()
    assert state_after["cards"] == []
    assert state_after["webhooks"] == []
    assert state_after["inbox_count"] == 5
