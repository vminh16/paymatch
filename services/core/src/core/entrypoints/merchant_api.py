"""FastAPI process for merchant-api (port 8001, prefix /m) per contracts/openapi/core-merchant.yaml."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import psycopg
import uvicorn
from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from psycopg.types.json import Jsonb

from core.ingest.application.ingest_invoice import IngestCommand, ingest_invoice
from core.merchant.application.serializers import (
    build_full_invoice,
    build_invoice_summary,
    fmt_ts,
    serialize_approval,
    serialize_finding,
    serialize_job,
)
from core.merchant.domain.adjustment import build_adjustment_request_template
from core.persistence.db import Database
from core.persistence.seeder import load_core_seed
from core.risk.domain.aggregation import REASON_CODE_RULES, SEVERITY_RANK
from core.shared.clock import Clock, SimWorldClock, SystemClock
from core.shared.config import CoreSettings
from core.shared.errors import ProblemError, install_error_handlers
from core.shared.hashing import action_hash, mask_account_number, payload_hash_approval
from core.shared.ids import new_id
from core.shared.jwt_tokens import ALLOWED_STRONG_AMR, Ed25519KeyManager, HttpJwksVerifier, JwksVerifier
from core.tools.adapters.http_gate import HttpGateAdapter
from core.tools.adapters.http_sim_world import HttpSimWorldAdapter
from core.tools.ports import GateClientPort, SimWorldToolPort, UpstreamToolError
from paymatch_contracts import merchant as merchant_models

VN_TZ = timezone(timedelta(hours=7))

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "owner": [
        "invoices:read",
        "invoices:upload",
        "invoices:approve",
        "invoices:reject",
        "approval_queue:read",
        "notifications:read",
        "demo:reset",
    ],
    "accountant": [
        "invoices:read",
        "invoices:upload",
        "approval_queue:read",
        "notifications:read",
    ],
    "store_manager": [
        "invoices:read",
        "notifications:read",
    ],
}


@dataclass(frozen=True)
class SessionPrincipal:
    user_id: str
    tenant_id: str
    role: str
    store_ids: tuple[str, ...]
    name: str


def _extract_trace_id(traceparent: str | None) -> str | None:
    if not traceparent:
        return None
    parts = traceparent.split("-")
    return parts[1] if len(parts) >= 2 and len(parts[1]) == 32 else None


def _hash_request(payload: bytes | str) -> str:
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(raw).hexdigest()


def _check_idempotency(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    method: str,
    path: str,
    key: str | None,
    request_hash: str,
) -> tuple[int, dict[str, Any]] | None:
    if not key or len(key) > 64:
        raise ProblemError(
            400,
            "VALIDATION_FAILED",
            "Missing or invalid Idempotency-Key",
            "Header Idempotency-Key (1..64 ký tự) là bắt buộc cho yêu cầu POST có tác dụng phụ.",
            errors=[{"field": "Idempotency-Key", "code": "required"}],
        )
    row = conn.execute(
        """
        SELECT request_hash, status_code, response_body, created_at
        FROM core.idempotency_keys
        WHERE tenant_id = %s AND method = %s AND path = %s AND idempotency_key = %s
        """,
        (tenant_id, method, path, key),
    ).fetchone()
    if row is None:
        return None
    if row["request_hash"] != request_hash:
        raise ProblemError(
            409,
            "IDEMPOTENCY_KEY_REUSED",
            "Idempotency key reused with different payload",
            "Idempotency-Key đã được dùng cho một yêu cầu khác trong 24 giờ qua.",
        )
    return int(row["status_code"]), dict(row["response_body"])


def _store_idempotency(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    method: str,
    path: str,
    key: str,
    request_hash: str,
    status_code: int,
    response_body: dict[str, Any],
    now: datetime,
) -> None:
    conn.execute(
        """
        INSERT INTO core.idempotency_keys (
            tenant_id, method, path, idempotency_key, request_hash, status_code, response_body, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, method, path, idempotency_key) DO NOTHING
        """,
        (tenant_id, method, path, key, request_hash, status_code, Jsonb(response_body), now),
    )


def _is_bulk_approvable(inv: dict[str, Any], mandate: dict[str, Any] | None) -> bool:
    if mandate is None or mandate.get("mode") == "review_only":
        return False
    if inv.get("verification_required") or inv.get("severity") == "red" or inv.get("status") != "pending_approval":
        return False
    if inv.get("severity") == "green":
        return True
    codes = set(inv.get("reason_codes") or [])
    total = inv.get("total_vnd")
    if total is None:
        return False
    for rule in mandate.get("bulk_approvable") or []:
        allowed_codes = set(rule.get("reason_codes") or [])
        max_amt = int(rule.get("max_amount_vnd", 0))
        if codes and codes <= allowed_codes and total <= max_amt:
            return True
    return False


def create_merchant_app(
    settings: CoreSettings | None = None,
    *,
    db: Database | None = None,
    admin_db: Database | None = None,
    sim_world: SimWorldToolPort | None = None,
    gate_client: GateClientPort | None = None,
    jwks_verifier: JwksVerifier | None = None,
    session_keys: Ed25519KeyManager | None = None,
    clock: Clock | None = None,
    security_clock: Clock | None = None,
) -> FastAPI:
    cfg = settings or CoreSettings.from_env()
    database = db or Database(cfg.database_url)
    admin_database = admin_db or (
        Database(cfg.admin_database_url) if cfg.admin_database_url else database
    )
    sim_adapter = sim_world or HttpSimWorldAdapter(cfg.sim_url, cfg.sim_core_service_key)
    gate_adapter = gate_client or HttpGateAdapter(cfg.gate_url, cfg.gate_core_service_key)
    # I2: wall clock for JWT auth & preview expiry; business clock for business dates/demo data
    sec_clk = security_clock or SystemClock()
    verifier = jwks_verifier or HttpJwksVerifier(
        cfg.sim_url,
        cfg.sim_core_service_key,
        expected_issuer=cfg.identity_jwt_issuer,
        clock=sec_clk,
    )
    sess_keys = session_keys or Ed25519KeyManager(cfg.session_signing_key_pem)
    clk = clock or (
        SimWorldClock(cfg.sim_url, cfg.sim_core_service_key) if cfg.demo_mode else SystemClock()
    )

    app = FastAPI(title="PayMatch Merchant API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)

    app.state.settings = cfg
    app.state.db = database
    app.state.admin_db = admin_database
    app.state.sim_world = sim_adapter
    app.state.gate = gate_adapter
    app.state.jwks_verifier = verifier
    app.state.session_keys = sess_keys
    app.state.clock = clk
    app.state.security_clock = sec_clk

    # ---- Auth dependencies ----

    def require_principal(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> SessionPrincipal:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise ProblemError(
                401,
                "UNAUTHENTICATED",
                "Authentication required",
                "Thiếu hoặc không hợp lệ Authorization Bearer token.",
            )
        token = authorization[7:].strip()
        claims = sess_keys.verify(
            token,
            audience="merchant-api",
            issuer="core",
            now_ts=int(sec_clk.now().timestamp()),
        )
        return SessionPrincipal(
            user_id=claims["sub"],
            tenant_id=claims["tenant_id"],
            role=claims["role"],
            store_ids=tuple(claims.get("store_ids") or []),
            name=claims.get("name", ""),
        )

    def require_roles(*allowed: str):
        def _dep(principal: SessionPrincipal = Depends(require_principal)) -> SessionPrincipal:
            if principal.role not in allowed:
                raise ProblemError(
                    403,
                    "ROLE_NOT_ALLOWED",
                    "Role not allowed",
                    f"Vai trò '{principal.role}' không có quyền thực hiện thao tác này.",
                )
            return principal

        return _dep

    # ---- Probes (no auth) ----

    @app.get("/m/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/m/readyz")
    def readyz() -> dict[str, str]:
        if not database.ping():
            raise ProblemError(503, "UPSTREAM_UNAVAILABLE", "Database unavailable", "Chưa kết nối được Postgres.")
        return {"status": "ready"}

    # ---- Auth ----

    @app.post("/m/auth/session")
    def create_auth_session(body: merchant_models.AuthSessionRequest) -> dict[str, Any]:
        momo_claims = verifier.verify_momo_token(body.momo_token)
        user_id = momo_claims.get("sub")
        tenant_id = momo_claims.get("tenant_id")
        if not user_id or not tenant_id:
            raise ProblemError(401, "UNAUTHENTICATED", "Invalid momo_token", "momo_token thiếu sub hoặc tenant_id.")

        with database.connect(role="merchant", tenant_id=tenant_id) as conn:
            u = conn.execute(
                "SELECT user_id, tenant_id, name, role, store_ids FROM core.users WHERE user_id = %s",
                (user_id,),
            ).fetchone()
        if u is None:
            raise ProblemError(401, "UNAUTHENTICATED", "Unknown user", "Không tìm thấy người dùng trong hệ thống.")

        # I2: wall clock for session JWT iat/exp
        now_ts = int(sec_clk.now().timestamp())
        exp_ts = now_ts + cfg.session_ttl_seconds
        exp_dt = datetime.fromtimestamp(exp_ts, tz=VN_TZ)

        session_jwt = sess_keys.sign(
            {
                "iss": "core",
                "aud": "merchant-api",
                "sub": u["user_id"],
                "tenant_id": u["tenant_id"],
                "role": u["role"],
                "store_ids": list(u["store_ids"]),
                "name": u["name"],
                "iat": now_ts,
                "exp": exp_ts,
                "jti": new_id("jti"),
            }
        )
        return {
            "session_jwt": session_jwt,
            "expires_at": fmt_ts(exp_dt),
            "user": {
                "user_id": u["user_id"],
                "name": u["name"],
                "role": u["role"],
                "store_ids": list(u["store_ids"]),
            },
        }

    @app.get("/m/me")
    def get_me(principal: SessionPrincipal = Depends(require_principal)) -> dict[str, Any]:
        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            t = conn.execute(
                "SELECT tenant_id, name FROM core.tenants WHERE tenant_id = %s",
                (principal.tenant_id,),
            ).fetchone()
        if t is None:
            raise ProblemError(404, "NOT_FOUND", "Tenant not found", "Không tìm thấy tenant.")
        return {
            "user_id": principal.user_id,
            "name": principal.name,
            "role": principal.role,
            "store_ids": list(principal.store_ids),
            "tenant": {"tenant_id": t["tenant_id"], "name": t["name"]},
            "permissions": list(ROLE_PERMISSIONS.get(principal.role, [])),
        }

    # ---- Invoices ----

    @app.get("/m/invoices")
    def list_invoices(
        status: list[str] | None = Query(default=None),
        severity: list[str] | None = Query(default=None),
        vendor_id: str | None = Query(default=None),
        store_id: str | None = Query(default=None),
        reason_code: list[str] | None = Query(default=None),
        invoice_type: list[str] | None = Query(default=None),
        issued_from: date | None = Query(default=None),
        issued_to: date | None = Query(default=None),
        q: str | None = Query(default=None, max_length=64),
        limit: int = Query(default=50, ge=1, le=200),
        cursor: str | None = Query(default=None),
        principal: SessionPrincipal = Depends(require_principal),
    ) -> dict[str, Any]:
        clauses = ["i.tenant_id = %s"]
        params: list[Any] = [principal.tenant_id]

        # Store manager scoping (merchant-api.md §0)
        if principal.role == "store_manager":
            clauses.append("i.store_id IS NOT NULL AND i.store_id = ANY(%s)")
            params.append(list(principal.store_ids))

        if status:
            clauses.append("i.status = ANY(%s)")
            params.append(status)
        if severity:
            clauses.append("i.severity = ANY(%s)")
            params.append(severity)
        if vendor_id:
            clauses.append("i.vendor_id = %s")
            params.append(vendor_id)
        if store_id:
            clauses.append("i.store_id = %s")
            params.append(store_id)
        if reason_code:
            clauses.append("i.reason_codes && %s::text[]")
            params.append(reason_code)
        if invoice_type:
            clauses.append("i.invoice_type = ANY(%s)")
            params.append(invoice_type)
        if issued_from:
            clauses.append("i.issued_on >= %s")
            params.append(issued_from)
        if issued_to:
            clauses.append("i.issued_on <= %s")
            params.append(issued_to)
        if q:
            clauses.append("(i.symbol ILIKE %s OR i.number ILIKE %s)")
            like = f"%{q}%"
            params.extend([like, like])

        offset = int(cursor) if (cursor and cursor.isdigit()) else 0
        params.extend([limit + 1, offset])

        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            rows = conn.execute(
                f"""
                SELECT i.*, v.name AS vendor_name_reg
                FROM core.invoices i
                LEFT JOIN core.vendors v ON v.vendor_id = i.vendor_id
                WHERE {' AND '.join(clauses)}
                ORDER BY i.updated_at DESC, i.invoice_id DESC
                LIMIT %s OFFSET %s
                """,
                params,
            ).fetchall()

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        return {
            "items": [build_invoice_summary(r, vendor_name=r.get("vendor_name_reg")) for r in page_rows],
            "next_cursor": str(offset + limit) if has_more else None,
        }

    @app.post("/m/invoices:upload")
    async def upload_invoice(
        request: Request,
        file: UploadFile = File(...),
        message_text: str | None = Form(default=None, max_length=4000),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        traceparent: str | None = Header(default=None),
        principal: SessionPrincipal = Depends(require_roles("owner", "accountant")),
    ) -> JSONResponse:
        # I10: stream upload in chunks and abort as soon as configured byte limit is exceeded
        buf = bytearray()
        while True:
            chunk = await file.read(65536)
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > cfg.max_invoice_bytes:
                raise ProblemError(
                    413,
                    "PAYLOAD_TOO_LARGE",
                    "Uploaded file exceeds maximum size",
                    f"Kích thước tệp tải lên vượt quá giới hạn cho phép ({cfg.max_invoice_bytes} bytes).",
                )
        raw_bytes = bytes(buf)
        req_hash = _hash_request(raw_bytes + (message_text or "").encode("utf-8"))
        now = clk.now()

        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            cached = _check_idempotency(
                conn,
                tenant_id=principal.tenant_id,
                method="POST",
                path=request.url.path,
                key=idempotency_key,
                request_hash=req_hash,
            )
            if cached is not None:
                code, body = cached
                return JSONResponse(status_code=code, content=body)

            res = ingest_invoice(
                conn,
                IngestCommand(
                    tenant_id=principal.tenant_id,
                    raw_bytes=raw_bytes,
                    filename=file.filename or "upload.xml",
                    content_type=file.content_type or "application/xml",
                    source="upload",
                    message_text=message_text,
                    trace_id=_extract_trace_id(traceparent),
                ),
                clock=clk,
                max_invoice_bytes=cfg.max_invoice_bytes,
                max_xml_elements=cfg.max_xml_elements,
                default_due_days=cfg.default_due_days,
            )
            status_code = 200 if res.already_existed else 202
            resp_body = {
                "invoice_id": res.invoice_id,
                "job_id": res.job_id,
                "status": res.status,
            }
            with conn.transaction():
                _store_idempotency(
                    conn,
                    tenant_id=principal.tenant_id,
                    method="POST",
                    path=request.url.path,
                    key=idempotency_key or "",
                    request_hash=req_hash,
                    status_code=status_code,
                    response_body=resp_body,
                    now=now,
                )
        return JSONResponse(status_code=status_code, content=resp_body)

    @app.get("/m/invoices/{invoice_id}")
    def get_invoice(
        invoice_id: str,
        response: Response,
        principal: SessionPrincipal = Depends(require_principal),
    ) -> dict[str, Any]:
        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            inv = conn.execute(
                "SELECT * FROM core.invoices WHERE tenant_id = %s AND invoice_id = %s",
                (principal.tenant_id, invoice_id),
            ).fetchone()
            if inv is None:
                raise ProblemError(404, "NOT_FOUND", "Invoice not found", "Không tìm thấy hóa đơn.")
            if principal.role == "store_manager" and (
                inv["store_id"] is None or inv["store_id"] not in principal.store_ids
            ):
                raise ProblemError(404, "NOT_FOUND", "Invoice not found", "Không tìm thấy hóa đơn.")
            m = conn.execute(
                "SELECT mode FROM core.mandates WHERE tenant_id = %s ORDER BY version DESC LIMIT 1",
                (principal.tenant_id,),
            ).fetchone()
            full = build_full_invoice(
                conn, inv, role=principal.role, mandate_mode=m["mode"] if m else None
            )
        response.headers["ETag"] = full["etag"]
        return full

    @app.get("/m/invoices/{invoice_id}/findings")
    def get_invoice_findings(
        invoice_id: str,
        job_id: str | None = Query(default=None),
        principal: SessionPrincipal = Depends(require_roles("owner", "accountant")),
    ) -> list[dict[str, Any]]:
        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            inv = conn.execute(
                "SELECT invoice_id FROM core.invoices WHERE tenant_id = %s AND invoice_id = %s",
                (principal.tenant_id, invoice_id),
            ).fetchone()
            if inv is None:
                raise ProblemError(404, "NOT_FOUND", "Invoice not found", "Không tìm thấy hóa đơn.")

            target_job_id = job_id
            if target_job_id is None:
                jrow = conn.execute(
                    """
                    SELECT job_id FROM core.jobs
                    WHERE tenant_id = %s AND invoice_id = %s AND status = 'completed'
                    ORDER BY completed_at DESC NULLS LAST, created_at DESC
                    LIMIT 1
                    """,
                    (principal.tenant_id, invoice_id),
                ).fetchone()
                target_job_id = jrow["job_id"] if jrow else None

            if target_job_id:
                rows = conn.execute(
                    """
                    SELECT * FROM core.findings
                    WHERE tenant_id = %s AND invoice_id = %s
                      AND superseded = FALSE
                      AND (job_id = %s OR bot_id IN ('ingest', 'system'))
                    ORDER BY created_at ASC
                    """,
                    (principal.tenant_id, invoice_id, target_job_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM core.findings
                    WHERE tenant_id = %s AND invoice_id = %s AND superseded = FALSE
                    ORDER BY created_at ASC
                    """,
                    (principal.tenant_id, invoice_id),
                ).fetchall()
        return [serialize_finding(r) for r in rows]

    @app.get("/m/invoices/{invoice_id}/approval-preview")
    def get_approval_preview(
        invoice_id: str,
        principal: SessionPrincipal = Depends(require_roles("owner")),
    ) -> dict[str, Any]:
        now = clk.now()
        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            inv = conn.execute(
                "SELECT * FROM core.invoices WHERE tenant_id = %s AND invoice_id = %s",
                (principal.tenant_id, invoice_id),
            ).fetchone()
            if inv is None:
                raise ProblemError(404, "NOT_FOUND", "Invoice not found", "Không tìm thấy hóa đơn.")

            latest_job = conn.execute(
                """
                SELECT job_id FROM core.jobs
                WHERE tenant_id = %s AND invoice_id = %s AND status = 'completed'
                ORDER BY completed_at DESC NULLS LAST, created_at DESC
                LIMIT 1
                """,
                (principal.tenant_id, invoice_id),
            ).fetchone()
            if latest_job is None:
                raise ProblemError(
                    409,
                    "INVALID_STATE",
                    "Investigation not completed",
                    "Hóa đơn chưa có kết quả điều tra hoàn tất.",
                    current_status=inv["status"],
                )

            try:
                ev = gate_adapter.evaluate_invoice(invoice_id=invoice_id, tenant_id=principal.tenant_id)
            except UpstreamToolError as exc:
                raise ProblemError(
                    503,
                    "UPSTREAM_UNAVAILABLE",
                    "Payment Gate unavailable",
                    f"Không kết nối được Payment Gate để xem trước điều kiện chi: {exc.detail}",
                ) from exc

            payee_obj = None
            if ev.payee_account_id:
                va = conn.execute(
                    """
                    SELECT vendor_account_id, bank_name, account_number_masked, account_number,
                           merchant_id, account_name
                    FROM core.vendor_accounts
                    WHERE tenant_id = %s AND vendor_account_id = %s
                    """,
                    (principal.tenant_id, ev.payee_account_id),
                ).fetchone()
                if va:
                    payee_obj = {
                        "vendor_account_id": va["vendor_account_id"],
                        "bank_name": va["bank_name"],
                        "account_number_masked": va["account_number_masked"]
                        or mask_account_number(va["account_number"]),
                        "merchant_id": va["merchant_id"],
                        "account_name": va["account_name"],
                    }

            phone_masked: str | None = None
            if ev.verification_required and inv.get("vendor_id"):
                v = conn.execute(
                    "SELECT phone_on_file_masked FROM core.vendors WHERE tenant_id = %s AND vendor_id = %s",
                    (principal.tenant_id, inv["vendor_id"]),
                ).fetchone()
                if v:
                    phone_masked = v["phone_on_file_masked"]

        ph = payload_hash_approval(ev.intent_hash, None)
        ah = action_hash("approve_invoice", invoice_id, ph)
        sec_now = sec_clk.now()
        expires_at = sec_now + timedelta(seconds=cfg.approval_preview_ttl_seconds)
        effective_ver_req = bool(ev.verification_required or inv.get("verification_required"))

        # I7: Persist server-tracked approval preview record (bound to version, job, intent_hash, verification, TTL)
        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO core.approval_previews (
                        preview_id, tenant_id, invoice_id, user_id, job_id,
                        intent_hash, action_hash, verification_required, invoice_version, expires_at, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        new_id("prv"),
                        principal.tenant_id,
                        invoice_id,
                        principal.user_id,
                        latest_job["job_id"],
                        ev.intent_hash,
                        ah,
                        effective_ver_req,
                        int(inv["version"]),
                        expires_at,
                        sec_now,
                    ),
                )

        return {
            "invoice_id": invoice_id,
            "job_id": latest_job["job_id"],
            "intent_hash": ev.intent_hash,
            "payee": payee_obj,
            "amount_vnd": ev.amount_vnd,
            "channel": ev.channel,
            "gate_decision": ev.decision,
            "allowed_methods": ev.allowed_methods,
            "verification_required": effective_ver_req,
            "phone_on_file_masked": phone_masked if effective_ver_req else None,
            "gate_reasons": ev.reasons,
            "action_hash": ah,
            "expires_at": fmt_ts(expires_at),
        }

    @app.post("/m/invoices/{invoice_id}:approve")
    def approve_invoice(
        invoice_id: str,
        body: merchant_models.ApproveInvoiceRequest,
        request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        traceparent: str | None = Header(default=None),
        principal: SessionPrincipal = Depends(require_roles("owner")),
    ) -> JSONResponse:
        now = clk.now()
        sec_now = sec_clk.now()
        trace_id = _extract_trace_id(traceparent)
        req_hash = _hash_request(body.model_dump_json())

        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            cached = _check_idempotency(
                conn,
                tenant_id=principal.tenant_id,
                method="POST",
                path=request.url.path,
                key=idempotency_key,
                request_hash=req_hash,
            )
            if cached is not None:
                return JSONResponse(status_code=cached[0], content=cached[1])

            inv = conn.execute(
                "SELECT * FROM core.invoices WHERE tenant_id = %s AND invoice_id = %s",
                (principal.tenant_id, invoice_id),
            ).fetchone()
            if inv is None:
                raise ProblemError(404, "NOT_FOUND", "Invoice not found", "Không tìm thấy hóa đơn.")

            mandate = conn.execute(
                "SELECT version, mode FROM core.mandates WHERE tenant_id = %s ORDER BY version DESC LIMIT 1",
                (principal.tenant_id,),
            ).fetchone()
            if mandate is None or mandate["mode"] == "review_only":
                raise ProblemError(
                    409,
                    "INVALID_STATE",
                    "Action not allowed in current state",
                    "Mandate hiện tại đang ở chế độ review_only; PayMatch chỉ đối soát, không phát lệnh chi.",
                    current_status=inv["status"],
                    errors=[{"field": "mandate", "code": "MANDATE_REVIEW_ONLY"}],
                )

            if inv["status"] not in {"pending_approval", "escrow_held"}:
                raise ProblemError(
                    409,
                    "INVALID_STATE",
                    "Invalid invoice state for approval",
                    f"Không thể duyệt hóa đơn ở trạng thái '{inv['status']}'.",
                    current_status=inv["status"],
                )

            latest_job = conn.execute(
                """
                SELECT job_id FROM core.jobs
                WHERE tenant_id = %s AND invoice_id = %s AND status = 'completed'
                ORDER BY completed_at DESC NULLS LAST, created_at DESC
                LIMIT 1
                """,
                (principal.tenant_id, invoice_id),
            ).fetchone()
            if latest_job is None or latest_job["job_id"] != body.job_id:
                raise ProblemError(
                    409,
                    "INTENT_HASH_MISMATCH",
                    "Invoice changed since preview",
                    "Job điều tra hoàn tất mới nhất đã thay đổi; vui lòng xem trước lại.",
                    errors=[{"field": "job_id", "code": "stale"}],
                )

            try:
                ev = gate_adapter.evaluate_invoice(invoice_id=invoice_id, tenant_id=principal.tenant_id)
            except UpstreamToolError as exc:
                raise ProblemError(
                    503,
                    "UPSTREAM_UNAVAILABLE",
                    "Payment Gate unavailable",
                    f"Không kết nối được Payment Gate: {exc.detail}",
                ) from exc

            if ev.decision == "DENY":
                raise ProblemError(
                    422,
                    "GATE_DENIED",
                    "Payment Gate denied approval",
                    "Payment Gate từ chối cho phép duyệt hóa đơn này.",
                    gate_reasons=ev.reasons,
                )

            # I3: escrow_held can ONLY be approved when channel == 'escrow'
            if inv["status"] == "escrow_held" and ev.channel != "escrow":
                raise ProblemError(
                    409,
                    "INVALID_STATE",
                    "Escrow channel required",
                    "Hóa đơn ở trạng thái escrow_held chỉ được duyệt cho kênh escrow.",
                    current_status=inv["status"],
                )

            if ev.intent_hash != body.intent_hash:
                raise ProblemError(
                    409,
                    "INTENT_HASH_MISMATCH",
                    "Invoice changed since preview",
                    "Dữ liệu hóa đơn, số tiền, người nhận hoặc kênh chi đã thay đổi; vui lòng xem trước lại.",
                    errors=[{"field": "intent_hash", "code": "stale"}],
                )

            # I7: Enforce fresh (<5m) server-issued preview bound to user, job, intent_hash, invoice_version, and verification_required
            effective_ver_req = bool(ev.verification_required or inv.get("verification_required"))
            fresh_preview = conn.execute(
                """
                SELECT preview_id, invoice_version, verification_required
                FROM core.approval_previews
                WHERE tenant_id = %s
                  AND invoice_id = %s
                  AND user_id = %s
                  AND job_id = %s
                  AND intent_hash = %s
                  AND expires_at >= %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (principal.tenant_id, invoice_id, principal.user_id, body.job_id, body.intent_hash, sec_now),
            ).fetchone()
            if (
                fresh_preview is None
                or int(fresh_preview["invoice_version"]) != int(inv["version"])
                or bool(fresh_preview["verification_required"]) != effective_ver_req
            ):
                raise ProblemError(
                    409,
                    "INTENT_HASH_MISMATCH",
                    "Approval preview expired or stale",
                    "Bản xem trước duyệt đã hết hạn hoặc hóa đơn đã cập nhật; vui lòng xem trước lại.",
                    errors=[{"field": "preview", "code": "expired_or_stale"}],
                )

            if effective_ver_req:
                if (
                    body.verification is None
                    or body.verification.called_phone_on_file is not True
                    or body.verification.result.value != "confirmed"
                ):
                    raise ProblemError(
                        400,
                        "VALIDATION_FAILED",
                        "Verification required",
                        "Hóa đơn yêu cầu xác minh gọi lại qua SĐT lưu sẵn với kết quả confirmed.",
                        errors=[{"field": "verification", "code": "required_confirmed"}],
                    )

            # Verify step-up auth_proof (action_hash computed via paymatch_hashing; I7 checks iss/exp/iat/amr)
            ver_dict = body.verification.model_dump(mode="json") if body.verification is not None else None
            expected_ph = payload_hash_approval(body.intent_hash, ver_dict)
            expected_ah = action_hash("approve_invoice", invoice_id, expected_ph)

            proof_claims = verifier.verify_auth_proof(body.auth_proof)
            if proof_claims.get("sub") != principal.user_id:
                raise ProblemError(
                    403, "STEP_UP_INVALID", "Step-up subject mismatch", "auth_proof không thuộc người dùng hiện tại."
                )
            if proof_claims.get("action_hash") != expected_ah:
                raise ProblemError(
                    403, "STEP_UP_INVALID", "Step-up action_hash mismatch", "auth_proof không khớp action_hash của hành động duyệt này."
                )
            amr_val = proof_claims.get("amr")
            if (
                not isinstance(amr_val, list)
                or not amr_val
                or not all(isinstance(x, str) for x in amr_val)
                or not (set(amr_val) & ALLOWED_STRONG_AMR)
            ):
                raise ProblemError(
                    403, "STEP_UP_INVALID", "Missing strong auth factor", "auth_proof thiếu yếu tố xác thực mạnh hợp lệ (amr)."
                )
            proof_jti = proof_claims.get("jti")
            if not proof_jti:
                raise ProblemError(403, "STEP_UP_INVALID", "Missing jti", "auth_proof thiếu jti.")

            if ev.payee_account_id is None:
                raise ProblemError(
                    422, "GATE_DENIED", "Missing verified payee", "Chưa có tài khoản nhận tiền hợp lệ."
                )

            approval_id = new_id("apv")
            next_status = "escrow_held" if inv["status"] == "escrow_held" else "approved"

            with conn.transaction():
                # I3: Lock invoice row and re-verify version, status, latest job, and verification_required under lock
                locked_inv = conn.execute(
                    """
                    SELECT * FROM core.invoices
                    WHERE tenant_id = %s AND invoice_id = %s
                    FOR UPDATE
                    """,
                    (principal.tenant_id, invoice_id),
                ).fetchone()
                if (
                    locked_inv is None
                    or locked_inv["status"] != inv["status"]
                    or int(locked_inv["version"]) != int(inv["version"])
                    or bool(locked_inv["verification_required"]) != bool(inv["verification_required"])
                ):
                    raise ProblemError(
                        409,
                        "INTENT_HASH_MISMATCH",
                        "Concurrent invoice update",
                        "Hóa đơn đã thay đổi đồng thời (ví dụ cảnh báo chéo mới); vui lòng xem trước lại.",
                    )
                latest_job_locked = conn.execute(
                    """
                    SELECT job_id FROM core.jobs
                    WHERE tenant_id = %s AND invoice_id = %s AND status = 'completed'
                    ORDER BY completed_at DESC NULLS LAST, created_at DESC
                    LIMIT 1
                    """,
                    (principal.tenant_id, invoice_id),
                ).fetchone()
                if latest_job_locked is None or latest_job_locked["job_id"] != body.job_id:
                    raise ProblemError(
                        409,
                        "INTENT_HASH_MISMATCH",
                        "Investigation superseded concurrently",
                        "Job điều tra hoàn tất mới nhất đã thay đổi; vui lòng xem trước lại.",
                    )

                # Enforce single-use auth_proof jti
                used = conn.execute(
                    """
                    INSERT INTO core.used_auth_proofs (jti, tenant_id, user_id, action_hash, used_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (jti) DO NOTHING
                    RETURNING jti
                    """,
                    (proof_jti, principal.tenant_id, principal.user_id, expected_ah, now),
                ).fetchone()
                if used is None:
                    raise ProblemError(
                        403, "STEP_UP_INVALID", "Replay of auth_proof", "auth_proof đã được sử dụng trước đó."
                    )

                # Supersede any prior active approval
                conn.execute(
                    """
                    UPDATE core.approvals
                    SET status = 'superseded', superseded_at = %s, superseded_reason = 'NEW_JOB'
                    WHERE tenant_id = %s AND invoice_id = %s AND status = 'active'
                    """,
                    (now, principal.tenant_id, invoice_id),
                )

                apv_row = conn.execute(
                    """
                    INSERT INTO core.approvals (
                        approval_id, tenant_id, invoice_id, job_id, status,
                        amount_vnd, payee_account_id, channel, intent_hash,
                        approver_user_id, method, mandate_version, verification, auth_proof_jti, created_at
                    )
                    VALUES (%s, %s, %s, %s, 'active', %s, %s, %s, %s, %s, 'single', %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        approval_id,
                        principal.tenant_id,
                        invoice_id,
                        body.job_id,
                        ev.amount_vnd,
                        ev.payee_account_id,
                        ev.channel,
                        ev.intent_hash,
                        principal.user_id,
                        mandate["version"],
                        Jsonb(ver_dict) if ver_dict is not None else None,
                        proof_jti,
                        now,
                    ),
                ).fetchone()

                updated_inv = conn.execute(
                    """
                    UPDATE core.invoices
                    SET status = %s, version = version + 1, updated_at = %s
                    WHERE tenant_id = %s AND invoice_id = %s
                      AND status = %s AND version = %s AND verification_required = %s
                    RETURNING *
                    """,
                    (
                        next_status,
                        now,
                        principal.tenant_id,
                        invoice_id,
                        inv["status"],
                        int(inv["version"]),
                        bool(inv["verification_required"]),
                    ),
                ).fetchone()
                if updated_inv is None:
                    raise ProblemError(
                        409, "INVALID_STATE", "Concurrent status change", "Trạng thái hóa đơn đã thay đổi đồng thời."
                    )

                # Outbox: approval.created + invoice.status_changed
                conn.execute(
                    """
                    INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
                    VALUES (%s, 'approval.created', 1, %s, %s, %s, %s)
                    """,
                    (
                        new_id("evt"),
                        now,
                        principal.tenant_id,
                        trace_id,
                        Jsonb(
                            {
                                "approval_id": approval_id,
                                "invoice_id": invoice_id,
                                "purchase_order_id": None,
                                "method": "single",
                                "reason": None,
                            }
                        ),
                    ),
                )

                if next_status != inv["status"]:
                    sc_evt_id = new_id("evt")
                    sc_data = {
                        "invoice_id": invoice_id,
                        "from": inv["status"],
                        "to": next_status,
                        "severity": updated_inv["severity"],
                    }
                    conn.execute(
                        """
                        INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
                        VALUES (%s, 'invoice.status_changed', 1, %s, %s, %s, %s)
                        """,
                        (sc_evt_id, now, principal.tenant_id, trace_id, Jsonb(sc_data)),
                    )
                    conn.execute(
                        """
                        INSERT INTO core.sse_events (event_id, stream_type, stream_key, tenant_id, store_id, event_type, data, created_at)
                        VALUES (%s, 'tenant', %s, %s, %s, 'invoice.status_changed', %s, %s)
                        """,
                        (sc_evt_id, principal.tenant_id, principal.tenant_id, updated_inv.get("store_id"), Jsonb(sc_data), now),
                    )

                vname = None
                if updated_inv.get("vendor_id"):
                    v = conn.execute(
                        "SELECT name FROM core.vendors WHERE tenant_id = %s AND vendor_id = %s",
                        (principal.tenant_id, updated_inv["vendor_id"]),
                    ).fetchone()
                    vname = v["name"] if v else None

                resp_body = {
                    "approval": serialize_approval(apv_row),
                    "invoice": build_invoice_summary(updated_inv, vendor_name=vname),
                }
                _store_idempotency(
                    conn,
                    tenant_id=principal.tenant_id,
                    method="POST",
                    path=request.url.path,
                    key=idempotency_key or "",
                    request_hash=req_hash,
                    status_code=200,
                    response_body=resp_body,
                    now=now,
                )
        return JSONResponse(status_code=200, content=resp_body)

    def _generate_or_load_adjustment_request(
        conn: psycopg.Connection,
        *,
        tenant_id: str,
        inv: dict[str, Any],
        reason_code: str,
        note: str | None,
        now: datetime,
        persist: bool,
    ) -> dict[str, Any] | None:
        existing = conn.execute(
            """
            SELECT adjustment_request_id, invoice_id, to_vendor_id, channel_hint, subject, body, cited_lines
            FROM core.adjustment_requests
            WHERE tenant_id = %s AND invoice_id = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (tenant_id, inv["invoice_id"]),
        ).fetchone()
        if existing and not persist:
            return {
                "adjustment_request_id": existing["adjustment_request_id"],
                "invoice_id": existing["invoice_id"],
                "to_vendor_id": existing["to_vendor_id"],
                "channel_hint": existing["channel_hint"],
                "subject": existing["subject"],
                "body": existing["body"],
                "cited_lines": list(existing["cited_lines"]),
            }

        tenant = conn.execute(
            "SELECT name, short_name FROM core.tenants WHERE tenant_id = %s", (tenant_id,)
        ).fetchone()
        vendor = None
        if inv.get("vendor_id"):
            vendor = conn.execute(
                "SELECT vendor_id, name FROM core.vendors WHERE tenant_id = %s AND vendor_id = %s",
                (tenant_id, inv["vendor_id"]),
            ).fetchone()

        # Pull latest price_check & three_way_match tool_calls for deterministic trusted numbers
        pc_row = conn.execute(
            """
            SELECT tc.output FROM core.tool_calls tc
            JOIN core.jobs j ON j.job_id = tc.job_id
            WHERE tc.tenant_id = %s AND j.invoice_id = %s AND tc.tool_id = 'price_check' AND tc.error IS NULL
            ORDER BY tc.created_at DESC LIMIT 1
            """,
            (tenant_id, inv["invoice_id"]),
        ).fetchone()
        tw_row = conn.execute(
            """
            SELECT tc.output FROM core.tool_calls tc
            JOIN core.jobs j ON j.job_id = tc.job_id
            WHERE tc.tenant_id = %s AND j.invoice_id = %s AND tc.tool_id = 'three_way_match' AND tc.error IS NULL
            ORDER BY tc.created_at DESC LIMIT 1
            """,
            (tenant_id, inv["invoice_id"]),
        ).fetchone()

        adj_id = new_id("adj")
        adj = build_adjustment_request_template(
            adjustment_request_id=adj_id,
            tenant_name=(tenant["short_name"] or tenant["name"]) if tenant else "Chuỗi cửa hàng",
            invoice=inv,
            vendor=vendor,
            reason_code=reason_code,
            price_check_items=(pc_row["output"].get("items", []) if pc_row else []),
            three_way_match=(tw_row["output"] if tw_row else None),
            note=note,
        )
        if persist:
            conn.execute(
                """
                INSERT INTO core.adjustment_requests (
                    adjustment_request_id, tenant_id, invoice_id, to_vendor_id,
                    channel_hint, subject, body, cited_lines, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    adj["adjustment_request_id"],
                    tenant_id,
                    adj["invoice_id"],
                    adj["to_vendor_id"],
                    adj["channel_hint"],
                    adj["subject"],
                    adj["body"],
                    adj["cited_lines"],
                    now,
                ),
            )
        return adj

    @app.post("/m/invoices/{invoice_id}:reject")
    def reject_invoice(
        invoice_id: str,
        body: merchant_models.RejectInvoiceRequest,
        request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        traceparent: str | None = Header(default=None),
        principal: SessionPrincipal = Depends(require_roles("owner")),
    ) -> JSONResponse:
        now = clk.now()
        trace_id = _extract_trace_id(traceparent)
        req_hash = _hash_request(body.model_dump_json())

        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            cached = _check_idempotency(
                conn,
                tenant_id=principal.tenant_id,
                method="POST",
                path=request.url.path,
                key=idempotency_key,
                request_hash=req_hash,
            )
            if cached is not None:
                return JSONResponse(status_code=cached[0], content=cached[1])

            inv = conn.execute(
                "SELECT * FROM core.invoices WHERE tenant_id = %s AND invoice_id = %s",
                (principal.tenant_id, invoice_id),
            ).fetchone()
            if inv is None:
                raise ProblemError(404, "NOT_FOUND", "Invoice not found", "Không tìm thấy hóa đơn.")
            if inv["status"] not in {"pending_approval", "blocked", "approved", "scheduled"}:
                raise ProblemError(
                    409,
                    "INVALID_STATE",
                    "Cannot reject invoice in current state",
                    f"Không thể từ chối hóa đơn ở trạng thái '{inv['status']}'.",
                    current_status=inv["status"],
                )

            # Cancel authorized intents if rejecting from approved/scheduled
            if inv["status"] in {"approved", "scheduled"}:
                try:
                    intents = gate_adapter.list_intents(
                        tenant_id=principal.tenant_id, invoice_id=invoice_id, status="authorized"
                    )
                    for it in intents:
                        gate_adapter.cancel_intent(
                            payment_intent_id=it["payment_intent_id"], reason="OWNER_CANCELLED"
                        )
                except UpstreamToolError:
                    pass

            with conn.transaction():
                conn.execute(
                    """
                    UPDATE core.approvals
                    SET status = 'superseded', superseded_at = %s, superseded_reason = 'OWNER_CANCELLED'
                    WHERE tenant_id = %s AND invoice_id = %s AND status = 'active'
                    """,
                    (now, principal.tenant_id, invoice_id),
                )
                updated_inv = conn.execute(
                    """
                    UPDATE core.invoices
                    SET status = 'rejected', version = version + 1, updated_at = %s
                    WHERE tenant_id = %s AND invoice_id = %s AND status = %s
                    RETURNING *
                    """,
                    (now, principal.tenant_id, invoice_id, inv["status"]),
                ).fetchone()
                if updated_inv is None:
                    raise ProblemError(409, "INVALID_STATE", "Concurrent state change", "Trạng thái hóa đơn đã đổi.")

                adj = None
                if updated_inv.get("vendor_id"):
                    adj = _generate_or_load_adjustment_request(
                        conn,
                        tenant_id=principal.tenant_id,
                        inv=updated_inv,
                        reason_code=body.reason_code.value,
                        note=body.note,
                        now=now,
                        persist=True,
                    )

                sc_evt_id = new_id("evt")
                sc_data = {
                    "invoice_id": invoice_id,
                    "from": inv["status"],
                    "to": "rejected",
                    "severity": updated_inv["severity"],
                }
                conn.execute(
                    """
                    INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
                    VALUES (%s, 'invoice.status_changed', 1, %s, %s, %s, %s)
                    """,
                    (sc_evt_id, now, principal.tenant_id, trace_id, Jsonb(sc_data)),
                )
                conn.execute(
                    """
                    INSERT INTO core.sse_events (event_id, stream_type, stream_key, tenant_id, store_id, event_type, data, created_at)
                    VALUES (%s, 'tenant', %s, %s, %s, 'invoice.status_changed', %s, %s)
                    """,
                    (sc_evt_id, principal.tenant_id, principal.tenant_id, updated_inv.get("store_id"), Jsonb(sc_data), now),
                )

                vname = None
                if updated_inv.get("vendor_id"):
                    v = conn.execute(
                        "SELECT name FROM core.vendors WHERE tenant_id = %s AND vendor_id = %s",
                        (principal.tenant_id, updated_inv["vendor_id"]),
                    ).fetchone()
                    vname = v["name"] if v else None

                resp_body = {
                    "invoice": build_invoice_summary(updated_inv, vendor_name=vname),
                    "adjustment_request": adj,
                }
                _store_idempotency(
                    conn,
                    tenant_id=principal.tenant_id,
                    method="POST",
                    path=request.url.path,
                    key=idempotency_key or "",
                    request_hash=req_hash,
                    status_code=200,
                    response_body=resp_body,
                    now=now,
                )
        return JSONResponse(status_code=200, content=resp_body)

    @app.get("/m/invoices/{invoice_id}/adjustment-request")
    def get_adjustment_request(
        invoice_id: str,
        principal: SessionPrincipal = Depends(require_roles("owner", "accountant")),
    ) -> dict[str, Any]:
        now = clk.now()
        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            inv = conn.execute(
                "SELECT * FROM core.invoices WHERE tenant_id = %s AND invoice_id = %s",
                (principal.tenant_id, invoice_id),
            ).fetchone()
            if inv is None:
                raise ProblemError(404, "NOT_FOUND", "Invoice not found", "Không tìm thấy hóa đơn.")
            primary_rc = (inv.get("reason_codes") or ["OTHER"])[0]
            adj = _generate_or_load_adjustment_request(
                conn,
                tenant_id=principal.tenant_id,
                inv=inv,
                reason_code=primary_rc,
                note=None,
                now=now,
                persist=False,
            )
            assert adj is not None
        return adj

    # ---- Jobs & SSE ----

    @app.get("/m/jobs/{job_id}")
    def get_job(
        job_id: str,
        principal: SessionPrincipal = Depends(require_roles("owner", "accountant")),
    ) -> dict[str, Any]:
        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            row = conn.execute(
                "SELECT * FROM core.jobs WHERE tenant_id = %s AND job_id = %s",
                (principal.tenant_id, job_id),
            ).fetchone()
            if row is None:
                raise ProblemError(404, "NOT_FOUND", "Job not found", "Không tìm thấy job.")
        return serialize_job(row)

    def _format_sse(event_type: str, event_id: str, data: dict[str, Any]) -> str:
        return f"event: {event_type}\nid: {event_id}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @app.get("/m/jobs/{job_id}/events")
    async def stream_job_events(
        job_id: str,
        request: Request,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
        principal: SessionPrincipal = Depends(require_roles("owner", "accountant")),
    ) -> StreamingResponse:
        now = clk.now()
        min_time = now - timedelta(seconds=cfg.sse_replay_window_seconds)
        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            job = conn.execute(
                "SELECT job_id, status FROM core.jobs WHERE tenant_id = %s AND job_id = %s",
                (principal.tenant_id, job_id),
            ).fetchone()
            if job is None:
                raise ProblemError(404, "NOT_FOUND", "Job not found", "Không tìm thấy job.")

            resync_needed = False
            start_seq = 0
            if last_event_id:
                anchor = conn.execute(
                    """
                    SELECT seq, created_at FROM core.sse_events
                    WHERE stream_type = 'job' AND stream_key = %s AND event_id = %s
                    """,
                    (job_id, last_event_id),
                ).fetchone()
                if anchor is None or anchor["created_at"] < min_time:
                    resync_needed = True
                else:
                    start_seq = int(anchor["seq"])

        def _poll_job_batch(after_seq: int) -> tuple[list[dict[str, Any]], str]:
            with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
                evs = conn.execute(
                    """
                    SELECT seq, event_id, event_type, data
                    FROM core.sse_events
                    WHERE stream_type = 'job' AND stream_key = %s AND seq > %s AND created_at >= %s
                    ORDER BY seq ASC
                    """,
                    (job_id, after_seq, min_time),
                ).fetchall()
                jrow = conn.execute(
                    "SELECT status FROM core.jobs WHERE tenant_id = %s AND job_id = %s",
                    (principal.tenant_id, job_id),
                ).fetchone()
                return evs, (jrow["status"] if jrow else "failed")

        async def _gen():
            if resync_needed:
                yield _format_sse("resync", new_id("evt"), {"reason": "cursor_expired"})
                return

            last_seq = start_seq
            last_yield = time.monotonic()
            last_activity = last_yield

            # I9: Tail job SSE live until completion, terminal failure, or client disconnect
            while True:
                batch, status = await asyncio.to_thread(_poll_job_batch, last_seq)
                for ev in batch:
                    last_seq = int(ev["seq"])
                    last_yield = time.monotonic()
                    last_activity = last_yield
                    yield _format_sse(ev["event_type"], ev["event_id"], ev["data"])
                    if ev["event_type"] in {"job.completed", "job.failed"}:
                        return

                if status in {"completed", "failed"}:
                    return
                if await request.is_disconnected():
                    return

                mono_now = time.monotonic()
                if mono_now - last_yield >= cfg.sse_keepalive_interval_s:
                    last_yield = mono_now
                    yield ": keep-alive\n\n"
                if cfg.sse_max_idle_seconds is not None and (mono_now - last_activity) >= cfg.sse_max_idle_seconds:
                    return

                await asyncio.sleep(cfg.sse_poll_interval_s)

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/m/events")
    async def stream_tenant_events(
        request: Request,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
        principal: SessionPrincipal = Depends(require_principal),
    ) -> StreamingResponse:
        now = clk.now()
        min_time = now - timedelta(seconds=cfg.sse_replay_window_seconds)
        resync_needed = False
        start_seq = 0

        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            if last_event_id:
                anchor = conn.execute(
                    """
                    SELECT seq, created_at FROM core.sse_events
                    WHERE stream_type = 'tenant' AND stream_key = %s AND event_id = %s
                    """,
                    (principal.tenant_id, last_event_id),
                ).fetchone()
                if anchor is None or anchor["created_at"] < min_time:
                    resync_needed = True
                else:
                    start_seq = int(anchor["seq"])

        def _poll_tenant_batch(after_seq: int) -> list[dict[str, Any]]:
            with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
                rows = conn.execute(
                    """
                    SELECT seq, event_id, event_type, store_id, data
                    FROM core.sse_events
                    WHERE stream_type = 'tenant' AND stream_key = %s AND seq > %s AND created_at >= %s
                    ORDER BY seq ASC
                    """,
                    (principal.tenant_id, after_seq, min_time),
                ).fetchall()
            out = []
            for r in rows:
                if principal.role == "store_manager":
                    if r["store_id"] is None or r["store_id"] not in principal.store_ids:
                        continue
                out.append(r)
            return out

        async def _gen():
            if resync_needed:
                yield _format_sse("resync", new_id("evt"), {"reason": "cursor_expired"})
                return

            last_seq = start_seq
            last_yield = time.monotonic()
            last_activity = last_yield

            # I9: Tail tenant SSE live with periodic scoped reads and keep-alives until disconnect
            while True:
                batch = await asyncio.to_thread(_poll_tenant_batch, last_seq)
                for ev in batch:
                    last_seq = int(ev["seq"])
                    last_yield = time.monotonic()
                    last_activity = last_yield
                    yield _format_sse(ev["event_type"], ev["event_id"], ev["data"])

                if await request.is_disconnected():
                    return

                mono_now = time.monotonic()
                if mono_now - last_yield >= cfg.sse_keepalive_interval_s:
                    last_yield = mono_now
                    yield ": keep-alive\n\n"
                if cfg.sse_max_idle_seconds is not None and (mono_now - last_activity) >= cfg.sse_max_idle_seconds:
                    return

                await asyncio.sleep(cfg.sse_poll_interval_s)

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ---- Approval Queue ----

    @app.get("/m/approval-queue")
    def get_approval_queue(
        group_by: str = Query(default="vendor", pattern="^(vendor|reason_code)$"),
        principal: SessionPrincipal = Depends(require_roles("owner", "accountant")),
    ) -> dict[str, Any]:
        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            mandate = conn.execute(
                "SELECT * FROM core.mandates WHERE tenant_id = %s ORDER BY version DESC LIMIT 1",
                (principal.tenant_id,),
            ).fetchone()
            rows = conn.execute(
                """
                SELECT i.*, v.name AS vendor_name_reg
                FROM core.invoices i
                LEFT JOIN core.vendors v ON v.vendor_id = i.vendor_id
                WHERE i.tenant_id = %s AND i.status IN ('pending_approval', 'blocked')
                ORDER BY i.updated_at DESC
                """,
                (principal.tenant_id,),
            ).fetchall()

        groups_map: dict[str, dict[str, Any]] = {}
        for r in rows:
            summary = build_invoice_summary(r, vendor_name=r.get("vendor_name_reg"))
            bulk_ok = _is_bulk_approvable(r, mandate)
            if group_by == "vendor":
                if r.get("vendor_id"):
                    key = r["vendor_id"]
                    label = r["vendor_name_reg"] or r["vendor_id"]
                else:
                    key = f"unknown:{r.get('seller_tax_id') or 'none'}"
                    label = f"NCC chưa đăng ký (MST {r.get('seller_tax_id') or 'không rõ'})"
            else:
                # Primary reason code (highest severity floor first)
                codes = list(r.get("reason_codes") or ["OTHER"])
                codes.sort(
                    key=lambda c: SEVERITY_RANK.get(
                        REASON_CODE_RULES[c].floor if c in REASON_CODE_RULES else "yellow", 1
                    ),
                    reverse=True,
                )
                key = codes[0]
                label = REASON_CODE_RULES[key].label_vi if key in REASON_CODE_RULES else key

            grp = groups_map.setdefault(
                key,
                {
                    "key": key,
                    "label": label,
                    "count": 0,
                    "total_vnd": 0,
                    "bulk_approvable_count": 0,
                    "invoices": [],
                },
            )
            grp["count"] += 1
            grp["total_vnd"] += int(r.get("total_vnd") or 0)
            if bulk_ok:
                grp["bulk_approvable_count"] += 1
            grp["invoices"].append(summary)

        groups = sorted(groups_map.values(), key=lambda g: g["total_vnd"], reverse=True)
        return {"groups": groups}

    # ---- Notifications ----

    @app.get("/m/notifications")
    def list_notifications(
        unread: bool | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        cursor: str | None = Query(default=None),
        principal: SessionPrincipal = Depends(require_principal),
    ) -> dict[str, Any]:
        clauses = ["tenant_id = %s", "(array_length(user_ids, 1) IS NULL OR %s = ANY(user_ids))"]
        params: list[Any] = [principal.tenant_id, principal.user_id]
        if unread is True:
            clauses.append("read_at IS NULL")
        elif unread is False:
            clauses.append("read_at IS NOT NULL")

        offset = int(cursor) if (cursor and cursor.isdigit()) else 0
        params.extend([limit + 1, offset])

        with database.connect(role="merchant", tenant_id=principal.tenant_id) as conn:
            rows = conn.execute(
                f"""
                SELECT notification_id, kind, invoice_ids, title, body, read_at, created_at
                FROM core.notifications
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC, notification_id DESC
                LIMIT %s OFFSET %s
                """,
                params,
            ).fetchall()

        has_more = len(rows) > limit
        page = rows[:limit]
        return {
            "items": [
                {
                    "notification_id": r["notification_id"],
                    "kind": r["kind"],
                    "invoice_ids": list(r["invoice_ids"]),
                    "title": r["title"],
                    "body": r["body"],
                    "read_at": fmt_ts(r["read_at"]),
                    "created_at": fmt_ts(r["created_at"]),
                }
                for r in page
            ],
            "next_cursor": str(offset + limit) if has_more else None,
        }

    # ---- Demo Reset (mounted ONLY when DEMO_MODE=true) ----

    if cfg.demo_mode:

        @app.post("/m/demo:reset")
        def reset_demo(
            request: Request,
            body: merchant_models.DemoResetRequest | None = None,
            idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
            principal: SessionPrincipal = Depends(require_roles("owner")),
        ) -> JSONResponse:
            if not idempotency_key or len(idempotency_key) > 64:
                raise ProblemError(
                    400,
                    "VALIDATION_FAILED",
                    "Missing Idempotency-Key",
                    "Header Idempotency-Key là bắt buộc.",
                )
            # Reset DB using dedicated migrator/admin connection (B1: merchant_api login has no TRUNCATE privileges)
            with admin_database.connect() as conn:
                counts = load_core_seed(conn, seed_dir=cfg.seed_dir, reset=True)

            try:
                sim_res = sim_adapter.reset_scenario(dataset="demo", seed=42)
                sim_counts = sim_res.get("counts") or {}
                if "scenarios" in sim_counts:
                    counts["scenarios"] = int(sim_counts["scenarios"])
            except UpstreamToolError as exc:
                raise ProblemError(
                    503,
                    "UPSTREAM_UNAVAILABLE",
                    "sim-world unavailable",
                    f"Không đặt lại được sim-world: {exc.detail}",
                ) from exc

            return JSONResponse(
                status_code=200,
                content={"reset_at": fmt_ts(clk.now()), "counts": counts},
            )

    return app


def main() -> None:
    cfg = CoreSettings.from_env()
    uvicorn.run(create_merchant_app(cfg), host="0.0.0.0", port=cfg.merchant_port)


if __name__ == "__main__":
    main()
