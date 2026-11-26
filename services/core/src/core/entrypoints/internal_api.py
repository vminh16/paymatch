"""FastAPI process for internal-api (port 8003, prefix /internal) per contracts/openapi/core-internal.yaml."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
import uvicorn
from fastapi import Depends, FastAPI, Header, Request, Response
from psycopg.types.json import Jsonb

from core.merchant.application.serializers import fmt_ts
from core.persistence.db import Database
from core.persistence.default_bots import SUPERVISOR_TRUSTED_TOOLS, UNTRUSTED_TEXT_TOOLS
from core.risk.domain.aggregation import (
    FindingInput,
    aggregate_findings,
    check_required_bots,
    compute_finding_severity,
    determine_post_investigation_status,
    evaluate_system_checks,
    extract_tool_floor_reason_codes,
    normalize_reason_codes,
)
from core.shared.clock import Clock, SimWorldClock, SystemClock
from core.shared.config import CoreSettings
from core.shared.errors import ProblemError, install_error_handlers
from core.shared.ids import new_id
from core.shared.jwt_tokens import Ed25519KeyManager
from core.tools.adapters.http_gate import HttpGateAdapter
from core.tools.adapters.http_sim_world import HttpSimWorldAdapter
from core.tools.application.executor import (
    ToolContext,
    _collect_invoice_indicator_pairs,
    invoke_tool,
)
from core.tools.domain.registry import V1_TOOL_SPECS
from core.tools.ports import GateClientPort, SimWorldToolPort
from paymatch_contracts import FindingSubmission
from paymatch_contracts import internal as internal_models

VN_TZ = timezone(timedelta(hours=7))

BUDGET_BY_TASK: dict[str, dict[str, int]] = {
    "investigate_invoice": {"seconds": 30, "max_steps": 12},
    "question": {"seconds": 15, "max_steps": 8},
    "report": {"seconds": 20, "max_steps": 8},
}

_EVIDENCE_REF_RE = re.compile(r"^(lin|doc|msg|itm|po|grn|tcl|vac|urd)_[0-9A-HJKMNP-TV-Z]{26}$")


def _extract_trace_id(traceparent: str | None) -> str | None:
    if not traceparent:
        return None
    parts = traceparent.split("-")
    return parts[1] if len(parts) >= 2 and len(parts[1]) == 32 else None


def _is_kill_switch_active(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    bot_id: str | None = None,
    tool_id: str | None = None,
) -> bool:
    rows = conn.execute(
        """
        SELECT scope, target_id FROM control.policies
        WHERE kind = 'kill_switch' AND status = 'engaged'
        """
    ).fetchall()
    for r in rows:
        scope = r["scope"]
        target = r["target_id"]
        if scope == "tenant" and target == tenant_id:
            return True
        if scope == "bot" and bot_id and target == bot_id:
            return True
        if scope == "tool" and tool_id and target == tool_id:
            return True
    return False


def _verify_lease(
    conn: psycopg.Connection,
    *,
    job_id: str,
    worker_id: str,
    attempt: int,
    now: datetime,
    require_running: bool = True,
) -> dict[str, Any]:
    job = conn.execute("SELECT * FROM core.jobs WHERE job_id = %s", (job_id,)).fetchone()
    if job is None:
        raise ProblemError(404, "NOT_FOUND", "Job not found", f"Không tìm thấy job {job_id}.")
    if require_running and job["status"] in {"completed", "failed"}:
        raise ProblemError(
            409,
            "INVALID_STATE",
            "Job already finished",
            f"Job {job_id} đã kết thúc ở trạng thái {job['status']}.",
            current_status=job["status"],
        )
    if (
        job["status"] != "running"
        or job["attempt"] != attempt
        or job["worker_id"] != worker_id
        or (job["lease_expires_at"] is not None and job["lease_expires_at"] < now)
    ):
        raise ProblemError(
            409,
            "LEASE_LOST",
            "Job lease lost",
            f"Lease của ({job_id}, attempt={attempt}, worker_id={worker_id}) không còn hiệu lực.",
        )
    return job


def _ref_in_json(obj: Any, needle: str) -> bool:
    if isinstance(obj, str):
        return obj == needle or needle in obj
    if isinstance(obj, dict):
        return any(_ref_in_json(v, needle) for v in obj.values())
    if isinstance(obj, list):
        return any(_ref_in_json(v, needle) for v in obj)
    return False


def _value_in_json(obj: Any, needle: str | int | float) -> bool:
    needle_str = str(needle)
    if isinstance(obj, bool):
        return False
    if isinstance(obj, (int, float)):
        return str(obj) == needle_str
    if isinstance(obj, str):
        return obj == needle_str or needle_str in obj
    if isinstance(obj, dict):
        return any(_value_in_json(v, needle) for v in obj.values())
    if isinstance(obj, list):
        return any(_value_in_json(v, needle) for v in obj)
    return False


def _build_session_payload(
    conn: psycopg.Connection,
    *,
    job: dict[str, Any],
    keys: Ed25519KeyManager,
    now: datetime,
    ttl_seconds: int = 120,
) -> tuple[dict[str, Any], list[str], list[dict[str, str]]]:
    """Compute supervisor & bot capability grants, required_bot_ids, skipped bots, and context."""
    tid = job["tenant_id"]
    task_type = job["task_type"]
    subject = job["subject"]
    invoice_id = subject.get("invoice_id") if task_type == "investigate_invoice" else None
    invoice_type: str | None = None

    if task_type == "investigate_invoice":
        inv = conn.execute(
            "SELECT invoice_id, invoice_type FROM core.invoices WHERE tenant_id = %s AND invoice_id = %s",
            (tid, invoice_id),
        ).fetchone()
        if inv is None:
            raise ProblemError(404, "NOT_FOUND", "Invoice not found", f"Invoice {invoice_id} not found.")
        invoice_type = inv["invoice_type"]
        context: dict[str, Any] = {"invoice_id": inv["invoice_id"], "invoice_type": invoice_type}
        store_ids_claim = None
    elif task_type == "question":
        context = {
            "messages": subject.get("messages", []),
            "user": subject.get("user", {"role": "owner", "store_ids": []}),
        }
        u_ctx = context["user"]
        store_ids_claim = u_ctx.get("store_ids") if u_ctx.get("role") == "store_manager" else None
    else:
        context = {
            "report_id": subject["report_id"],
            "kind": subject.get("kind", "daily_summary"),
            "from": subject.get("from", now.date().isoformat()),
            "to": subject.get("to", now.date().isoformat()),
            "user": subject.get("user", {"role": "owner", "store_ids": []}),
        }
        u_ctx = context["user"]
        store_ids_claim = u_ctx.get("store_ids") if u_ctx.get("role") == "store_manager" else None

    # Tenant tool grants
    grant_rows = conn.execute(
        "SELECT tool_id FROM control.tool_grants WHERE tenant_id = %s AND enabled = TRUE",
        (tid,),
    ).fetchall()
    granted_tools = {r["tool_id"] for r in grant_rows}

    # Supervisor tools: strictly trusted read-only tools — NEVER untrusted text tools (invariant #6)
    sup_tool_ids = [
        t for t in SUPERVISOR_TRUSTED_TOOLS if t in granted_tools and t not in UNTRUSTED_TEXT_TOOLS
    ]
    assert not (set(sup_tool_ids) & UNTRUSTED_TEXT_TOOLS), "Supervisor must never receive untrusted text tools"

    now_ts = int(now.timestamp())
    sup_token, sup_exp = keys.issue_capability_token(
        sub="supervisor",
        tenant_id=tid,
        job_id=job["job_id"],
        invoice_id=invoice_id,
        attempt=job["attempt"],
        worker_id=job["worker_id"],
        bot_version=None,
        tools=sup_tool_ids,
        store_ids=store_ids_claim,
        ttl_seconds=ttl_seconds,
        now_ts=now_ts,
    )
    sup_exp_iso = datetime.fromtimestamp(sup_exp, tz=VN_TZ).isoformat(timespec="seconds")

    # Active bots (system + tenant)
    bot_rows = conn.execute(
        """
        SELECT d.bot_id, d.scope, d.enabled, d.archived, d.active_version,
               v.manifest, v.prefetch, v.status AS version_status
        FROM control.bot_definitions d
        JOIN control.bot_versions v
          ON v.bot_id = d.bot_id AND v.tenant_id = d.tenant_id AND v.version = d.active_version
        WHERE (d.tenant_id = '' OR d.tenant_id = %s) AND d.archived = FALSE
        ORDER BY d.scope DESC, d.bot_id ASC
        """,
        (tid,),
    ).fetchall()

    bots_out: list[dict[str, Any]] = []
    required_bot_ids: list[str] = []
    skipped: list[dict[str, str]] = []

    for brow in bot_rows:
        manifest = dict(brow["manifest"])
        bot_id = brow["bot_id"]
        bot_task_types = manifest.get("task_types") or ["investigate_invoice"]
        if task_type not in bot_task_types:
            continue

        if task_type == "investigate_invoice" and invoice_type is not None:
            triggers = (manifest.get("triggers") or {}).get("invoice_types") or []
            if invoice_type not in triggers:
                continue
            if brow["scope"] == "system" and invoice_type in (manifest.get("required_for") or []):
                required_bot_ids.append(bot_id)

        if not brow["enabled"] or brow["version_status"] == "disabled":
            skipped.append({"bot_id": bot_id, "reason": "DISABLED"})
            continue

        if _is_kill_switch_active(conn, tenant_id=tid, bot_id=bot_id):
            skipped.append({"bot_id": bot_id, "reason": "KILL_SWITCH"})
            continue

        bot_tools = [
            t for t in manifest.get("tools", []) if t in granted_tools and t in V1_TOOL_SPECS
        ]
        # Invariant #4: never allow any ask_* or bot-to-bot tool in a specialist bot token
        assert all(not t.startswith("ask_") for t in bot_tools)

        # Load skills for this bot
        skills_out = []
        for sref in manifest.get("skills", []):
            if "@" in sref:
                sid, sver_s = sref.rsplit("@", 1)
                sver = int(sver_s)
            else:
                sid, sver = sref, 1
            srow = conn.execute(
                """
                SELECT skill_id, version, content_md FROM control.skill_versions
                WHERE skill_id = %s AND version = %s AND (tenant_id = '' OR tenant_id = %s)
                ORDER BY (tenant_id = %s) DESC LIMIT 1
                """,
                (sid, sver, tid, tid),
            ).fetchone()
            if srow:
                skills_out.append(
                    {
                        "skill_id": srow["skill_id"],
                        "version": srow["version"],
                        "content_md": srow["content_md"],
                    }
                )

        bot_token, bot_exp = keys.issue_capability_token(
            sub=bot_id,
            tenant_id=tid,
            job_id=job["job_id"],
            invoice_id=invoice_id,
            attempt=job["attempt"],
            worker_id=job["worker_id"],
            bot_version=brow["active_version"],
            tools=bot_tools,
            store_ids=store_ids_claim,
            ttl_seconds=ttl_seconds,
            now_ts=now_ts,
        )
        bot_exp_iso = datetime.fromtimestamp(bot_exp, tz=VN_TZ).isoformat(timespec="seconds")

        bots_out.append(
            {
                "bot_id": bot_id,
                "bot_version": brow["active_version"],
                "description": manifest.get("description", ""),
                "manifest": manifest,
                "skills": skills_out,
                "prefetch": [p for p in (brow["prefetch"] or []) if p in bot_tools],
                "capability_token": bot_token,
                "token_exp": bot_exp_iso,
            }
        )

    payload = {
        "budget": BUDGET_BY_TASK[task_type],
        "supervisor": {
            "capability_token": sup_token,
            "token_exp": sup_exp_iso,
            "tools": [V1_TOOL_SPECS[t].to_definition() for t in sup_tool_ids],
        },
        "bots": bots_out,
        "required_bot_ids": required_bot_ids,
        "skipped": skipped,
        "context": context,
    }
    return payload, required_bot_ids, skipped


def _complete_investigation_job(
    conn: psycopg.Connection,
    *,
    job: dict[str, Any],
    brief_submission: dict[str, Any] | None,
    now: datetime,
    trace_id: str | None,
) -> dict[str, Any]:
    """Run required-bot checks, DB system checks (§4), monotone aggregation, CAS invoice status, and outbox."""
    tid = job["tenant_id"]
    job_id = job["job_id"]
    invoice_id = job["invoice_id"]

    inv = conn.execute(
        "SELECT * FROM core.invoices WHERE tenant_id = %s AND invoice_id = %s",
        (tid, invoice_id),
    ).fetchone()
    if inv is None:
        raise ProblemError(404, "NOT_FOUND", "Invoice not found", f"Invoice {invoice_id} not found.")

    # Existing non-superseded findings for this job (and ingest findings for this invoice)
    existing_findings = conn.execute(
        """
        SELECT * FROM core.findings
        WHERE tenant_id = %s AND invoice_id = %s AND superseded = FALSE
          AND (job_id = %s OR bot_id = 'ingest')
        ORDER BY created_at ASC
        """,
        (tid, invoice_id, job_id),
    ).fetchall()

    submitted_bot_ids = {f["bot_id"] for f in existing_findings if f["bot_id"] not in {"ingest", "system"}}
    required_bot_ids = list(job.get("required_bot_ids") or [])
    skipped_bot_ids = [s["bot_id"] for s in (job.get("skipped_bots") or [])]

    # If session wasn't explicitly saved on job (edge case), infer required bots from DB
    if not required_bot_ids:
        sys_bots = conn.execute(
            """
            SELECT d.bot_id, v.manifest FROM control.bot_definitions d
            JOIN control.bot_versions v
              ON v.bot_id = d.bot_id AND v.tenant_id = d.tenant_id AND v.version = d.active_version
            WHERE d.scope = 'system' AND d.tenant_id = '' AND d.archived = FALSE
            """
        ).fetchall()
        for sb in sys_bots:
            if inv["invoice_type"] in (sb["manifest"].get("required_for") or []):
                required_bot_ids.append(sb["bot_id"])

    missing_bot_specs = check_required_bots(
        required_bot_ids=required_bot_ids,
        submitted_bot_ids=submitted_bot_ids,
        skipped_bot_ids=skipped_bot_ids,
    )

    # System checks at :complete (internal-api.md §4) — DB only, no external calls
    pairs = _collect_invoice_indicator_pairs(conn, inv)
    has_cross_alert = False
    has_hard_block = False
    for kind, val_hash in pairs:
        if not has_cross_alert:
            ca = conn.execute(
                """
                SELECT 1 FROM risk.indicators i
                JOIN risk.cross_alerts ca ON i.indicator_id = ANY(ca.indicator_ids)
                WHERE i.kind = %s AND i.value_hash = %s AND ca.status = 'published'
                LIMIT 1
                """,
                (kind, val_hash),
            ).fetchone()
            if ca is not None:
                has_cross_alert = True
        if not has_hard_block:
            hb = conn.execute(
                """
                SELECT 1 FROM risk.indicators i
                JOIN risk.hard_blocks hb ON i.indicator_id = ANY(hb.indicator_ids)
                WHERE i.kind = %s AND i.value_hash = %s
                LIMIT 1
                """,
                (kind, val_hash),
            ).fetchone()
            if hb is not None:
                has_hard_block = True

    untrusted = inv.get("untrusted") or {}
    raw_bas = list(untrusted.get("bank_accounts") or [])
    if not raw_bas and untrusted.get("seller_bank_account"):
        raw_bas = [untrusted["seller_bank_account"]]
    inv_acc_nums = [ba["number"] for ba in raw_bas if isinstance(ba, dict) and ba.get("number")]

    verified_nums: list[str] = []
    approved_verif_nums: list[str] = []
    if inv.get("vendor_id"):
        v_accs = conn.execute(
            """
            SELECT account_number FROM core.vendor_accounts
            WHERE tenant_id = %s AND vendor_id = %s AND status = 'verified' AND account_number IS NOT NULL
            """,
            (tid, inv["vendor_id"]),
        ).fetchall()
        verified_nums = [a["account_number"] for a in v_accs]

        v_verifs = conn.execute(
            """
            SELECT proposed_account->>'account_number' AS acc_num
            FROM core.vendor_verifications
            WHERE tenant_id = %s AND vendor_id = %s AND status = 'approved'
            """,
            (tid, inv["vendor_id"]),
        ).fetchall()
        approved_verif_nums = [v["acc_num"] for v in v_verifs if v["acc_num"]]

    sys_specs = evaluate_system_checks(
        invoice_bank_account_numbers=inv_acc_nums,
        verified_account_numbers=verified_nums,
        approved_verification_account_numbers=approved_verif_nums,
        has_published_cross_alert=has_cross_alert,
        has_hard_block=has_hard_block,
    )

    new_sys_findings = [*missing_bot_specs, *sys_specs]

    # Aggregate ALL findings monotonically (invariant #5)
    finding_inputs: list[FindingInput] = [
        FindingInput(
            severity_reported=f["severity_reported"],
            reason_codes=tuple(f["reason_codes"]),
            severity_computed=f["severity"],
        )
        for f in existing_findings
    ]
    for sp in new_sys_findings:
        finding_inputs.append(
            FindingInput(
                severity_reported=sp.severity,
                reason_codes=sp.reason_codes,
                severity_computed=sp.severity,
            )
        )

    agg = aggregate_findings(finding_inputs)

    # Determine post-investigation status (merchant-api.md §2 table)
    mandate = conn.execute(
        "SELECT * FROM core.mandates WHERE tenant_id = %s ORDER BY version DESC LIMIT 1",
        (tid,),
    ).fetchone()
    pol = conn.execute(
        "SELECT payload FROM control.policies WHERE kind = 'platform_limits' AND status = 'active' LIMIT 1"
    ).fetchone()
    platform_per_inv = int((pol["payload"] if pol else {}).get("auto_pay_per_invoice_vnd", 30_000_000))

    is_suspended = False
    if inv.get("vendor_id"):
        susp = conn.execute(
            """
            SELECT 1 FROM core.auto_pay_suspensions
            WHERE tenant_id = %s AND vendor_id = %s AND lifted_at IS NULL
            LIMIT 1
            """,
            (tid, inv["vendor_id"]),
        ).fetchone()
        is_suspended = susp is not None

    # Also treat QT-03 on THIS invoice as ineligible for auto-pay (already handled because QT-03 codes are >= yellow)
    target_status = determine_post_investigation_status(
        final_severity=agg.final_severity,
        vendor_id=inv.get("vendor_id"),
        total_vnd=inv.get("total_vnd"),
        mandate=mandate,
        platform_per_invoice_vnd=platform_per_inv,
        is_vendor_suspended=is_suspended,
        now_vn=now,
    )

    with conn.transaction():
        for sp in new_sys_findings:
            conn.execute(
                """
                INSERT INTO core.findings (
                    finding_id, tenant_id, job_id, invoice_id, attempt, bot_id,
                    bot_version, skill_version, prompt_hash, severity, severity_reported,
                    reason_codes, reason, evidence, provenance, created_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    1, 1, 'system-check', %s, %s,
                    %s, %s, '[]'::jsonb, 'trusted', %s
                )
                """,
                (
                    new_id("fnd"),
                    tid,
                    job_id,
                    invoice_id,
                    job["attempt"],
                    sp.bot_id,
                    sp.severity,
                    sp.severity,
                    list(sp.reason_codes),
                    Jsonb({"text": sp.reason_text, "provenance": "untrusted", "source": "bot_reason"}),
                    now,
                ),
            )

        if brief_submission is not None:
            brief_lines = [
                {"text": ln, "provenance": "untrusted", "source": "bot_reason"}
                for ln in brief_submission["lines"]
            ]
            conn.execute(
                """
                INSERT INTO core.briefs (
                    brief_id, tenant_id, job_id, invoice_id, lines, cited_evidence, model, prompt_hash, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    new_id("brf"),
                    tid,
                    job_id,
                    invoice_id,
                    Jsonb(brief_lines),
                    Jsonb(brief_submission.get("cited_evidence", [])),
                    brief_submission["model"],
                    brief_submission["prompt_hash"],
                    now,
                ),
            )

        # CAS update invoice from 'investigating' -> target_status
        updated = conn.execute(
            """
            UPDATE core.invoices
            SET status = %s,
                severity = %s,
                reason_codes = %s,
                verification_required = %s,
                version = version + 1,
                updated_at = %s
            WHERE tenant_id = %s AND invoice_id = %s AND status = 'investigating'
            RETURNING status
            """,
            (
                target_status,
                agg.final_severity,
                list(agg.reason_codes),
                agg.verification_required,
                now,
                tid,
                invoice_id,
            ),
        ).fetchone()
        actual_invoice_status = updated["status"] if updated else inv["status"]

        # Supersede any prior active approvals because a new investigation job completed
        superseded_apvs = conn.execute(
            """
            UPDATE core.approvals
            SET status = 'superseded', superseded_at = %s, superseded_reason = 'NEW_JOB'
            WHERE tenant_id = %s AND invoice_id = %s AND status = 'active'
            RETURNING approval_id, purchase_order_id, method
            """,
            (now, tid, invoice_id),
        ).fetchall()
        for apv in superseded_apvs:
            conn.execute(
                """
                INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
                VALUES (%s, 'approval.superseded', 1, %s, %s, %s, %s)
                """,
                (
                    new_id("evt"),
                    now,
                    tid,
                    trace_id,
                    Jsonb(
                        {
                            "approval_id": apv["approval_id"],
                            "invoice_id": invoice_id,
                            "purchase_order_id": apv["purchase_order_id"],
                            "method": apv["method"],
                            "reason": "NEW_JOB",
                        }
                    ),
                ),
            )

        # Complete job
        conn.execute(
            """
            UPDATE core.jobs
            SET status = 'completed', completed_at = %s, updated_at = %s
            WHERE job_id = %s
            """,
            (now, now, job_id),
        )

        # Emit job.completed to outbox + job SSE
        jc_evt_id = new_id("evt")
        jc_data = {
            "job_id": job_id,
            "task_type": "investigate_invoice",
            "invoice_id": invoice_id,
            "final_severity": agg.final_severity,
            "reason_codes": list(agg.reason_codes),
        }
        conn.execute(
            """
            INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
            VALUES (%s, 'job.completed', 1, %s, %s, %s, %s)
            """,
            (jc_evt_id, now, tid, trace_id, Jsonb(jc_data)),
        )
        conn.execute(
            """
            INSERT INTO core.sse_events (event_id, stream_type, stream_key, tenant_id, store_id, event_type, data, created_at)
            VALUES (%s, 'job', %s, %s, %s, 'job.completed', %s, %s)
            """,
            (
                jc_evt_id,
                job_id,
                tid,
                inv.get("store_id"),
                Jsonb({**jc_data, "at": fmt_ts(now)}),
                now,
            ),
        )

        # Emit invoice.status_changed if CAS updated
        if updated is not None:
            sc_evt_id = new_id("evt")
            sc_data = {
                "invoice_id": invoice_id,
                "from": "investigating",
                "to": actual_invoice_status,
                "severity": agg.final_severity,
            }
            conn.execute(
                """
                INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
                VALUES (%s, 'invoice.status_changed', 1, %s, %s, %s, %s)
                """,
                (sc_evt_id, now, tid, trace_id, Jsonb(sc_data)),
            )
            conn.execute(
                """
                INSERT INTO core.sse_events (event_id, stream_type, stream_key, tenant_id, store_id, event_type, data, created_at)
                VALUES (%s, 'tenant', %s, %s, %s, 'invoice.status_changed', %s, %s)
                """,
                (sc_evt_id, tid, tid, inv.get("store_id"), Jsonb(sc_data), now),
            )

    return {
        "status": "completed",
        "final_severity": agg.final_severity,
        "invoice_status": actual_invoice_status,
    }


def create_internal_app(
    settings: CoreSettings | None = None,
    *,
    db: Database | None = None,
    sim_world: SimWorldToolPort | None = None,
    gate_client: GateClientPort | None = None,
    capability_keys: Ed25519KeyManager | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    cfg = settings or CoreSettings.from_env()
    database = db or Database(cfg.database_url)
    sim_adapter = sim_world or HttpSimWorldAdapter(cfg.sim_url, cfg.sim_core_service_key)
    gate_adapter = gate_client or HttpGateAdapter(cfg.gate_url, cfg.gate_core_service_key)
    cap_keys = capability_keys or Ed25519KeyManager(cfg.capability_signing_key_pem)
    clk = clock or (
        SimWorldClock(cfg.sim_url, cfg.sim_core_service_key) if cfg.demo_mode else SystemClock()
    )

    app = FastAPI(title="PayMatch Core Internal API", version="0.1.0")
    install_error_handlers(app)

    app.state.settings = cfg
    app.state.db = database
    app.state.sim_world = sim_adapter
    app.state.gate = gate_adapter
    app.state.cap_keys = cap_keys
    app.state.clock = clk

    # ---- Auth dependencies (strictly separated, NEVER mixed) ----

    def require_agent_service_key(
        x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    ) -> str:
        expected = cfg.internal_agent_service_key
        if not x_service_key:
            raise ProblemError(401, "UNAUTHENTICATED", "Authentication required", "Thiếu header X-Service-Key.")
        if expected and not hmac.compare_digest(x_service_key, expected):
            raise ProblemError(403, "FORBIDDEN", "Invalid service key", "X-Service-Key không hợp lệ cho agent-worker.")
        return "agent-worker"

    def require_webhook_service_key(
        x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    ) -> str:
        expected = cfg.internal_sim_webhook_key
        if not x_service_key:
            raise ProblemError(401, "UNAUTHENTICATED", "Authentication required", "Thiếu header X-Service-Key.")
        if expected and not hmac.compare_digest(x_service_key, expected):
            raise ProblemError(403, "FORBIDDEN", "Invalid service key", "X-Service-Key không hợp lệ cho sim-world.")
        return "sim-world"

    def require_capability_claims(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> dict[str, Any]:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise ProblemError(401, "UNAUTHENTICATED", "Missing capability token", "Thiếu Bearer capability token.")
        token = authorization[7:].strip()
        claims = cap_keys.verify(
            token,
            audience="internal-api",
            issuer="core",
            now_ts=int(clk.now().timestamp()),
        )
        return claims

    # ---- Probes (no auth) ----

    @app.get("/internal/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/internal/readyz")
    def readyz() -> dict[str, str]:
        if not database.ping():
            raise ProblemError(503, "UPSTREAM_UNAVAILABLE", "Database unavailable", "Chưa kết nối được Postgres.")
        return {"status": "ready"}

    # ---- Job lifecycle (ServiceKeyAuth) ----

    @app.post("/internal/jobs:claim")
    def claim_job(
        body: internal_models.ClaimJobRequest,
        _caller: str = Depends(require_agent_service_key),
    ) -> Any:
        now = clk.now()
        lease_until = now + timedelta(seconds=cfg.job_lease_seconds)
        allowed_types = (
            [t.value for t in body.task_types]
            if body.task_types
            else ["question", "investigate_invoice", "report"]
        )

        with database.connect() as conn:
            with conn.transaction():
                # Reclaim expired leases first, then pick highest priority (question > investigate_invoice > report)
                row = conn.execute(
                    """
                    SELECT j.*
                    FROM core.jobs j
                    WHERE j.task_type = ANY(%s)
                      AND (
                        j.status = 'queued'
                        OR (j.status = 'running' AND j.lease_expires_at < %s)
                      )
                      AND (
                        SELECT COUNT(*) FROM core.jobs r
                        WHERE r.tenant_id = j.tenant_id
                          AND r.status = 'running'
                          AND r.lease_expires_at >= %s
                      ) < %s
                    ORDER BY
                      CASE j.task_type
                        WHEN 'question' THEN 0
                        WHEN 'investigate_invoice' THEN 1
                        ELSE 2
                      END ASC,
                      j.created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """,
                    (allowed_types, now, now, cfg.max_concurrent_jobs_per_tenant),
                ).fetchone()
                if row is None:
                    return Response(status_code=204)

                updated = conn.execute(
                    """
                    UPDATE core.jobs
                    SET status = 'running',
                        attempt = attempt + 1,
                        worker_id = %s,
                        lease_expires_at = %s,
                        started_at = COALESCE(started_at, %s),
                        updated_at = %s
                    WHERE job_id = %s
                    RETURNING job_id, task_type, tenant_id, attempt, lease_expires_at, subject
                    """,
                    (body.worker_id, lease_until, now, now, row["job_id"]),
                ).fetchone()

        return {
            "job_id": updated["job_id"],
            "task_type": updated["task_type"],
            "tenant_id": updated["tenant_id"],
            "attempt": updated["attempt"],
            "lease_expires_at": fmt_ts(updated["lease_expires_at"]),
            "subject": updated["subject"],
        }

    @app.post("/internal/jobs/{job_id}/session")
    def open_job_session(
        job_id: str,
        body: internal_models.OpenJobSessionRequest,
        _caller: str = Depends(require_agent_service_key),
    ) -> dict[str, Any]:
        now = clk.now()
        with database.connect() as conn:
            job = _verify_lease(conn, job_id=job_id, worker_id=body.worker_id, attempt=body.attempt, now=now)
            payload, required_bot_ids, skipped = _build_session_payload(
                conn, job=job, keys=cap_keys, now=now, ttl_seconds=min(cfg.job_lease_seconds, 120)
            )
            with conn.transaction():
                bot_states = [
                    {"bot_id": b["bot_id"], "state": "pending", "severity": None}
                    for b in payload["bots"]
                ]
                conn.execute(
                    """
                    UPDATE core.jobs
                    SET required_bot_ids = %s,
                        skipped_bots = %s,
                        bot_states = CASE WHEN jsonb_array_length(bot_states) = 0 THEN %s ELSE bot_states END,
                        updated_at = %s
                    WHERE job_id = %s
                    """,
                    (required_bot_ids, Jsonb(skipped), Jsonb(bot_states), now, job_id),
                )
        return payload

    @app.post("/internal/jobs/{job_id}/heartbeat")
    def heartbeat_job(
        job_id: str,
        body: internal_models.JobHeartbeatRequest,
        _caller: str = Depends(require_agent_service_key),
    ) -> dict[str, Any]:
        now = clk.now()
        new_lease = now + timedelta(seconds=cfg.job_lease_seconds)
        with database.connect() as conn:
            job = _verify_lease(conn, job_id=job_id, worker_id=body.worker_id, attempt=body.attempt, now=now)
            with conn.transaction():
                conn.execute(
                    "UPDATE core.jobs SET lease_expires_at = %s, updated_at = %s WHERE job_id = %s",
                    (new_lease, now, job_id),
                )
            session_payload, _, _ = _build_session_payload(
                conn, job=job, keys=cap_keys, now=now, ttl_seconds=min(cfg.job_lease_seconds, 120)
            )

        tokens = [
            {
                "holder": "supervisor",
                "capability_token": session_payload["supervisor"]["capability_token"],
                "token_exp": session_payload["supervisor"]["token_exp"],
            }
        ]
        for b in session_payload["bots"]:
            tokens.append(
                {
                    "holder": b["bot_id"],
                    "capability_token": b["capability_token"],
                    "token_exp": b["token_exp"],
                }
            )
        return {"lease_expires_at": fmt_ts(new_lease), "tokens": tokens}

    @app.post("/internal/jobs/{job_id}/progress", status_code=204)
    def report_job_progress(
        job_id: str,
        body: internal_models.JobProgressRequest,
        traceparent: str | None = Header(default=None),
        _caller: str = Depends(require_agent_service_key),
    ) -> Response:
        now = clk.now()
        trace_id = _extract_trace_id(traceparent)
        with database.connect() as conn:
            job = _verify_lease(conn, job_id=job_id, worker_id=body.worker_id, attempt=body.attempt, now=now)
            bot_states = {s["bot_id"]: dict(s) for s in (job.get("bot_states") or [])}
            bots_called = {c["bot_id"]: dict(c) for c in (job.get("bots_called") or [])}

            with conn.transaction():
                for ev in body.events:
                    ev_type = ev.type.value
                    if ev_type == "answer.delta" and job["task_type"] != "question":
                        raise ProblemError(
                            400,
                            "VALIDATION_FAILED",
                            "Invalid progress event",
                            "Sự kiện answer.delta chỉ hợp lệ cho job question.",
                        )
                    if ev.bot_id:
                        st = bot_states.setdefault(
                            ev.bot_id, {"bot_id": ev.bot_id, "state": "pending", "severity": None}
                        )
                        if ev_type == "bot.started":
                            st["state"] = "running"
                            bc = bots_called.setdefault(
                                ev.bot_id, {"bot_id": ev.bot_id, "bot_version": 1, "times": 0}
                            )
                            bc["times"] += 1
                        elif ev_type == "bot.finished":
                            st["state"] = "done"
                            st["severity"] = ev.severity.value if ev.severity else st.get("severity")
                        elif ev_type == "bot.failed":
                            st["state"] = (
                                "timeout"
                                if (ev.reason_code and ev.reason_code.value == "BOT_TIMEOUT")
                                else "failed"
                            )

                    evt_id = new_id("evt")
                    at_str = fmt_ts(ev.at)
                    sse_payload: dict[str, Any] = {"job_id": job_id, "at": at_str}
                    if ev_type == "supervisor.step" and ev.step is not None:
                        sse_payload["step"] = ev.step
                    elif ev_type == "bot.started" and ev.bot_id:
                        sse_payload["bot_id"] = ev.bot_id
                    elif ev_type == "bot.tool_called" and ev.bot_id and ev.tool_id:
                        sse_payload["bot_id"] = ev.bot_id
                        sse_payload["tool_id"] = ev.tool_id
                    elif ev_type == "bot.finished" and ev.bot_id and ev.severity:
                        sse_payload["bot_id"] = ev.bot_id
                        sse_payload["severity"] = ev.severity.value
                    elif ev_type == "bot.failed" and ev.bot_id and ev.reason_code:
                        sse_payload["bot_id"] = ev.bot_id
                        sse_payload["reason_code"] = ev.reason_code.value
                    elif ev_type == "answer.delta" and ev.text_delta is not None:
                        sse_payload["text_delta"] = ev.text_delta

                    conn.execute(
                        """
                        INSERT INTO core.sse_events (event_id, stream_type, stream_key, tenant_id, event_type, data, created_at)
                        VALUES (%s, 'job', %s, %s, %s, %s, %s)
                        """,
                        (evt_id, job_id, job["tenant_id"], ev_type, Jsonb(sse_payload), now),
                    )
                    if ev_type != "answer.delta":
                        outbox_data: dict[str, Any] = {
                            "job_id": job_id,
                            "task_type": job["task_type"],
                            "attempt": body.attempt,
                            "type": ev_type,
                            "at": at_str,
                        }
                        if ev.step is not None:
                            outbox_data["step"] = ev.step
                        if ev.bot_id is not None:
                            outbox_data["bot_id"] = ev.bot_id
                        if ev.tool_id is not None:
                            outbox_data["tool_id"] = ev.tool_id
                        if ev.severity is not None:
                            outbox_data["severity"] = ev.severity.value
                        if ev.reason_code is not None:
                            outbox_data["reason_code"] = ev.reason_code.value
                        conn.execute(
                            """
                            INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
                            VALUES (%s, 'job.progressed', 1, %s, %s, %s, %s)
                            """,
                            (evt_id, now, job["tenant_id"], trace_id, Jsonb(outbox_data)),
                        )

                conn.execute(
                    """
                    UPDATE core.jobs
                    SET bot_states = %s, bots_called = %s, updated_at = %s
                    WHERE job_id = %s
                    """,
                    (Jsonb(list(bot_states.values())), Jsonb(list(bots_called.values())), now, job_id),
                )
        return Response(status_code=204)

    # ---- Findings & BotAnswers (CapabilityBearerAuth) ----

    @app.post("/internal/jobs/{job_id}/findings", status_code=201)
    def submit_finding(
        job_id: str,
        body: FindingSubmission,
        claims: dict[str, Any] = Depends(require_capability_claims),
    ) -> dict[str, Any]:
        now = clk.now()
        # Invariant #1: token bound to exact job & bot (supervisor cannot submit specialist findings)
        if claims.get("job_id") != job_id:
            raise ProblemError(403, "FORBIDDEN", "Job mismatch", "Capability token không thuộc job này.")
        if claims.get("sub") == "supervisor" or claims.get("sub") != body.bot_id:
            raise ProblemError(403, "FORBIDDEN", "Bot mismatch", "bot_id phải khớp sub trong capability token.")

        with database.connect() as conn:
            job = _verify_lease(
                conn,
                job_id=job_id,
                worker_id=claims["worker_id"],
                attempt=int(claims["attempt"]),
                now=now,
            )
            if job["task_type"] != "investigate_invoice":
                raise ProblemError(409, "INVALID_STATE", "Wrong task type", "Findings chỉ áp dụng cho investigate_invoice.")
            if _is_kill_switch_active(conn, tenant_id=job["tenant_id"], bot_id=body.bot_id):
                raise ProblemError(423, "KILL_SWITCH_ACTIVE", "Kill switch active", "Bot hoặc tenant đang bị chặn.")

            # Fetch all tool calls made by this bot in this attempt
            tcs = conn.execute(
                """
                SELECT tool_call_id, tool_id, output, provenance, error
                FROM core.tool_calls
                WHERE tenant_id = %s AND job_id = %s AND attempt = %s AND bot_id = %s
                """,
                (job["tenant_id"], job_id, int(claims["attempt"]), body.bot_id),
            ).fetchall()
            tc_by_id = {tc["tool_call_id"]: tc for tc in tcs}
            called_tool_ids = {tc["tool_id"] for tc in tcs}

            # Check prefetch tools were called
            bot_ver = conn.execute(
                """
                SELECT prefetch FROM control.bot_versions
                WHERE bot_id = %s AND version = %s AND (tenant_id = '' OR tenant_id = %s)
                ORDER BY (tenant_id = %s) DESC LIMIT 1
                """,
                (body.bot_id, body.bot_version, job["tenant_id"], job["tenant_id"]),
            ).fetchone()
            required_prefetch = [
                p for p in (bot_ver["prefetch"] if bot_ver else []) if p in (claims.get("tools") or [])
            ]
            # Allow BOT_TIMEOUT / BOT_INVALID_OUTPUT error findings without full prefetch
            submitted_codes = [c.value for c in body.reason_codes]
            is_error_finding = any(c in {"BOT_TIMEOUT", "BOT_INVALID_OUTPUT"} for c in submitted_codes)
            missing_prefetch = [p for p in required_prefetch if p not in called_tool_ids]
            if missing_prefetch and not is_error_finding:
                raise ProblemError(
                    400,
                    "VALIDATION_FAILED",
                    "Missing prefetch tools",
                    f"Bot '{body.bot_id}' chưa gọi đủ tool prefetch: {missing_prefetch}.",
                    errors=[{"field": "prefetch", "code": "missing", "detail": ", ".join(missing_prefetch)}],
                )

            # Validate every evidence item: tool_call_id belongs to (job_id, attempt, bot_id) & ref_id in output
            for idx, ev in enumerate(body.evidence):
                if not _EVIDENCE_REF_RE.fullmatch(ev.ref_id):
                    raise ProblemError(
                        400,
                        "VALIDATION_FAILED",
                        "Invalid evidence ref_id",
                        f"evidence[{idx}].ref_id không đúng mẫu ID.",
                    )
                tc = tc_by_id.get(ev.tool_call_id)
                if tc is None:
                    raise ProblemError(
                        400,
                        "VALIDATION_FAILED",
                        "Invalid evidence tool_call_id",
                        f"evidence[{idx}].tool_call_id '{ev.tool_call_id}' không thuộc (job, attempt, bot) này.",
                        errors=[{"field": f"evidence[{idx}].tool_call_id", "code": "not_found"}],
                    )
                if ev.ref_id != ev.tool_call_id and not _ref_in_json(tc["output"], ev.ref_id):
                    raise ProblemError(
                        400,
                        "VALIDATION_FAILED",
                        "Evidence ref_id not in tool output",
                        f"evidence[{idx}].ref_id '{ev.ref_id}' không xuất hiện trong output của '{ev.tool_call_id}'.",
                        errors=[{"field": f"evidence[{idx}].ref_id", "code": "not_in_output"}],
                    )

            # Apply tool-output floor (internal-api.md §3) and reason-code floor/ceiling (agent-runtime.md §5a)
            tool_floor_codes = extract_tool_floor_reason_codes(tcs)
            merged_codes = normalize_reason_codes([*submitted_codes, *tool_floor_codes])
            final_sev = compute_finding_severity(body.severity_reported.value, merged_codes)

            # Enforce provenance: if any tool call was untrusted or bot reported untrusted -> untrusted
            provenance = body.provenance.value
            if any(tc["provenance"] == "untrusted" for tc in tcs):
                provenance = "untrusted"

            finding_id = new_id("fnd")
            evidence_dicts = [e.model_dump(mode="json") for e in body.evidence]
            with conn.transaction():
                # Supersede earlier finding from the same bot in this job (keeping history)
                conn.execute(
                    """
                    UPDATE core.findings
                    SET superseded = TRUE
                    WHERE tenant_id = %s AND job_id = %s AND bot_id = %s AND superseded = FALSE
                    """,
                    (job["tenant_id"], job_id, body.bot_id),
                )
                conn.execute(
                    """
                    INSERT INTO core.findings (
                        finding_id, tenant_id, job_id, invoice_id, attempt, bot_id,
                        bot_version, skill_version, prompt_hash, severity, severity_reported,
                        reason_codes, reason, evidence, provenance, proposed_channel, proposed_pay_on, created_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        finding_id,
                        job["tenant_id"],
                        job_id,
                        job["invoice_id"],
                        int(claims["attempt"]),
                        body.bot_id,
                        body.bot_version,
                        body.skill_version,
                        body.prompt_hash,
                        final_sev,
                        body.severity_reported.value,
                        merged_codes,
                        Jsonb({"text": body.reason, "provenance": "untrusted", "source": "bot_reason"}),
                        Jsonb(evidence_dicts),
                        provenance,
                        body.proposed_channel.value if body.proposed_channel else None,
                        body.proposed_pay_on,
                        now,
                    ),
                )

        # Invariant #6: FindingForSupervisor MUST NOT contain `reason` or any free text!
        return {
            "finding_id": finding_id,
            "bot_id": body.bot_id,
            "severity": final_sev,
            "reason_codes": merged_codes,
            "evidence": evidence_dicts,
        }

    @app.post("/internal/jobs/{job_id}/bot-answers", status_code=201)
    def submit_bot_answer(
        job_id: str,
        body: internal_models.BotAnswerSubmission,
        claims: dict[str, Any] = Depends(require_capability_claims),
    ) -> dict[str, Any]:
        now = clk.now()
        if claims.get("job_id") != job_id:
            raise ProblemError(403, "FORBIDDEN", "Job mismatch", "Capability token không thuộc job này.")
        if claims.get("sub") == "supervisor" or claims.get("sub") != body.bot_id:
            raise ProblemError(403, "FORBIDDEN", "Bot mismatch", "bot_id phải khớp sub trong capability token.")

        with database.connect() as conn:
            job = _verify_lease(
                conn,
                job_id=job_id,
                worker_id=claims["worker_id"],
                attempt=int(claims["attempt"]),
                now=now,
            )
            if job["task_type"] not in {"question", "report"}:
                raise ProblemError(409, "INVALID_STATE", "Wrong task type", "bot-answers chỉ áp dụng cho question/report.")
            tcs = conn.execute(
                """
                SELECT tool_call_id, output FROM core.tool_calls
                WHERE tenant_id = %s AND job_id = %s AND attempt = %s AND bot_id = %s
                """,
                (job["tenant_id"], job_id, int(claims["attempt"]), body.bot_id),
            ).fetchall()
            tc_by_id = {tc["tool_call_id"]: tc["output"] for tc in tcs}

            verified_facts = []
            for f in body.facts:
                out = tc_by_id.get(f.tool_call_id)
                ok = out is not None and _value_in_json(out, f.value)
                if ok:
                    verified_facts.append(
                        {
                            "key": f.key,
                            "value": f.value,
                            "tool_call_id": f.tool_call_id,
                            "verified": True,
                        }
                    )

            rc_list = [c.value for c in body.reason_codes]
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO core.bot_answers (bot_answer_id, tenant_id, job_id, attempt, bot_id, facts, reason_codes, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        new_id("ban"),
                        job["tenant_id"],
                        job_id,
                        int(claims["attempt"]),
                        body.bot_id,
                        Jsonb(verified_facts),
                        rc_list,
                        now,
                    ),
                )

        return {
            "bot_id": body.bot_id,
            "facts": verified_facts,
            "reason_codes": rc_list,
        }

    # ---- Complete & Fail (ServiceKeyAuth) ----

    @app.post("/internal/jobs/{job_id}:complete")
    def complete_job(
        job_id: str,
        body: internal_models.CompleteJobRequest,
        traceparent: str | None = Header(default=None),
        _caller: str = Depends(require_agent_service_key),
    ) -> dict[str, Any]:
        now = clk.now()
        trace_id = _extract_trace_id(traceparent)
        with database.connect() as conn:
            job = _verify_lease(conn, job_id=job_id, worker_id=body.worker_id, attempt=body.attempt, now=now)
            if job["task_type"] == "investigate_invoice":
                if not isinstance(body.result, internal_models.CompleteInvestigateResult):
                    raise ProblemError(
                        400, "VALIDATION_FAILED", "Expected brief result", "investigate_invoice cần result.brief."
                    )
                brief_dict = body.result.brief.model_dump(mode="json")
                return _complete_investigation_job(
                    conn, job=job, brief_submission=brief_dict, now=now, trace_id=trace_id
                )

            # question / report completion
            if not isinstance(body.result, internal_models.CompleteAnswerResult):
                raise ProblemError(
                    400, "VALIDATION_FAILED", "Expected answer result", "question/report cần result.answer."
                )
            ans = body.result.answer
            tcs = conn.execute(
                "SELECT tool_call_id, output FROM core.tool_calls WHERE tenant_id = %s AND job_id = %s AND attempt = %s",
                (job["tenant_id"], job_id, body.attempt),
            ).fetchall()
            tc_by_id = {tc["tool_call_id"]: tc["output"] for tc in tcs}
            unverified: list[str] = []
            for cit in ans.citations:
                out = tc_by_id.get(cit.tool_call_id)
                for val in cit.values:
                    if out is None or not _value_in_json(out, val):
                        unverified.append(val)
            with conn.transaction():
                conn.execute(
                    "UPDATE core.jobs SET status = 'completed', completed_at = %s, updated_at = %s WHERE job_id = %s",
                    (now, now, job_id),
                )
            msg_id = job["subject"].get("message_id") or new_id("cmg")
            return {
                "status": "completed",
                "message_id": msg_id,
                "unverified_values": unverified,
            }

    @app.post("/internal/jobs/{job_id}:fail")
    def fail_job(
        job_id: str,
        body: internal_models.FailJobRequest,
        traceparent: str | None = Header(default=None),
        _caller: str = Depends(require_agent_service_key),
    ) -> dict[str, bool]:
        now = clk.now()
        trace_id = _extract_trace_id(traceparent)
        with database.connect() as conn:
            job = _verify_lease(conn, job_id=job_id, worker_id=body.worker_id, attempt=body.attempt, now=now)
            err_payload = {"error_code": body.error_code, "detail": body.detail}
            if job["attempt"] < 2:
                with conn.transaction():
                    conn.execute(
                        """
                        UPDATE core.jobs
                        SET status = 'queued', worker_id = NULL, lease_expires_at = NULL,
                            last_error = %s, updated_at = %s
                        WHERE job_id = %s
                        """,
                        (Jsonb(err_payload), now, job_id),
                    )
                return {"will_retry": True}

            # Exhausted retries: investigate_invoice completes without brief (missing bots -> yellow BOT_NOT_RUN)
            if job["task_type"] == "investigate_invoice":
                with conn.transaction():
                    conn.execute(
                        "UPDATE core.jobs SET last_error = %s, updated_at = %s WHERE job_id = %s",
                        (Jsonb(err_payload), now, job_id),
                    )
                _complete_investigation_job(
                    conn, job=job, brief_submission=None, now=now, trace_id=trace_id
                )
            else:
                with conn.transaction():
                    conn.execute(
                        """
                        UPDATE core.jobs
                        SET status = 'failed', last_error = %s, completed_at = %s, updated_at = %s
                        WHERE job_id = %s
                        """,
                        (Jsonb(err_payload), now, now, job_id),
                    )
            return {"will_retry": False}

    # ---- Model configs (ServiceKeyAuth) ----

    @app.get("/internal/model-configs")
    def list_model_configs(
        _caller: str = Depends(require_agent_service_key),
    ) -> list[dict[str, Any]]:
        with database.connect() as conn:
            rows = conn.execute(
                "SELECT purpose, primary_model, fallback_model, max_tokens, timeout_s, version FROM control.model_configs ORDER BY purpose"
            ).fetchall()
        return [
            {
                "purpose": r["purpose"],
                "primary_model": r["primary_model"],
                "fallback_model": r["fallback_model"],
                "max_tokens": r["max_tokens"],
                "timeout_s": r["timeout_s"],
                "etag": f'"mcfg_{r["purpose"]}:v{r["version"]}"',
            }
            for r in rows
        ]

    # ---- Tools (CapabilityBearerAuth) ----

    @app.get("/internal/tools")
    def list_granted_tools(
        claims: dict[str, Any] = Depends(require_capability_claims),
    ) -> list[dict[str, Any]]:
        now = clk.now()
        with database.connect() as conn:
            _verify_lease(
                conn,
                job_id=claims["job_id"],
                worker_id=claims["worker_id"],
                attempt=int(claims["attempt"]),
                now=now,
            )
        return [
            V1_TOOL_SPECS[t].to_definition()
            for t in (claims.get("tools") or [])
            if t in V1_TOOL_SPECS
        ]

    @app.post("/internal/tools/{tool_id}:invoke")
    def invoke_tool_endpoint(
        tool_id: str,
        body: internal_models.ToolInvokeRequest,
        claims: dict[str, Any] = Depends(require_capability_claims),
    ) -> dict[str, Any]:
        now = clk.now()
        # Invariant #1: tool MUST be in capability token's granted tools list -> 403 TOOL_NOT_GRANTED
        granted = claims.get("tools") or []
        if tool_id not in granted:
            raise ProblemError(
                403,
                "TOOL_NOT_GRANTED",
                "Tool not granted in capability token",
                f"Tool '{tool_id}' không nằm trong capability token hiện tại.",
            )
        # Invariant #6 extra belt-and-suspenders: supervisor can never invoke untrusted tools
        if claims.get("sub") == "supervisor" and tool_id in UNTRUSTED_TEXT_TOOLS:
            raise ProblemError(
                403,
                "TOOL_NOT_GRANTED",
                "Untrusted tool denied for supervisor",
                f"Điều phối không bao giờ được gọi tool untrusted '{tool_id}'.",
            )

        with database.connect() as conn:
            _verify_lease(
                conn,
                job_id=claims["job_id"],
                worker_id=claims["worker_id"],
                attempt=int(claims["attempt"]),
                now=now,
            )
            bot_id = claims["sub"]
            if _is_kill_switch_active(
                conn,
                tenant_id=claims["tenant_id"],
                bot_id=None if bot_id == "supervisor" else bot_id,
                tool_id=tool_id,
            ):
                raise ProblemError(
                    423,
                    "KILL_SWITCH_ACTIVE",
                    "Kill switch active",
                    f"Tool '{tool_id}' hoặc bot '{bot_id}' đang bị tạm khóa bởi kill switch.",
                )

            ctx = ToolContext(
                tenant_id=claims["tenant_id"],
                job_id=claims["job_id"],
                attempt=int(claims["attempt"]),
                bot_id=bot_id,
                invoice_id=claims.get("invoice_id"),
                store_ids=claims.get("store_ids"),
            )
            return invoke_tool(
                conn,
                tool_id=tool_id,
                raw_input=body.input,
                ctx=ctx,
                sim_world=sim_adapter,
                gate_client=gate_adapter,
                clock=clk,
            )

    # ---- Rails webhook from sim-world (ServiceKeyAuth) ----

    @app.post("/internal/webhooks/rails", status_code=204)
    def receive_rails_webhook(
        body: internal_models.RailsWebhookRequest,
        traceparent: str | None = Header(default=None),
        _caller: str = Depends(require_webhook_service_key),
    ) -> Response:
        now = clk.now()
        trace_id = _extract_trace_id(traceparent)
        data_dict = body.data.model_dump(mode="json")
        ev_type = body.type.value

        with database.connect() as conn:
            with conn.transaction():
                inserted = conn.execute(
                    """
                    INSERT INTO core.webhook_events (event_id, event_type, occurred_at, data, received_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (event_id) DO NOTHING
                    RETURNING event_id
                    """,
                    (body.event_id, ev_type, body.occurred_at, Jsonb(data_dict), now),
                ).fetchone()
                if inserted is None:
                    # Idempotent replay
                    return Response(status_code=204)

                if ev_type == "card.authorization_declined":
                    card_id = data_dict["card_id"]
                    merchant_id = data_dict["merchant_id"]
                    opaque_ref = "srf_" + hashlib.sha256(body.event_id.encode("utf-8")).hexdigest()[:16]
                    conn.execute(
                        """
                        INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
                        VALUES (%s, 'indicator.flagged', 1, %s, NULL, %s, %s)
                        """,
                        (
                            new_id("evt"),
                            now,
                            trace_id,
                            Jsonb(
                                {
                                    "indicators": [
                                        {"kind": "card_id", "value_hash": card_id},
                                        {"kind": "merchant_id", "value_hash": merchant_id},
                                    ],
                                    "reason_codes": ["OFFICIAL_FRAUD_LIST"],
                                    "source": "rail",
                                    "source_ref": opaque_ref,
                                }
                            ),
                        ),
                    )
        return Response(status_code=204)

    return app


def main() -> None:
    cfg = CoreSettings.from_env()
    uvicorn.run(create_internal_app(cfg), host="0.0.0.0", port=cfg.internal_port)


if __name__ == "__main__":
    main()
