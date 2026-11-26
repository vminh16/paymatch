"""FastAPI process for internal-api (port 8003, prefix /internal) per contracts/openapi/core-internal.yaml."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import psycopg
import uvicorn
from fastapi import Depends, FastAPI, Header, Request, Response
from psycopg.types.json import Jsonb

from core.merchant.application.serializers import fmt_ts
from core.persistence.db import Database
from core.persistence.default_bots import SUPERVISOR_TRUSTED_TOOLS, UNTRUSTED_TEXT_TOOLS
from core.persistence.job_lease import (
    claim_next_job,
    lock_active_job_lease,
    lookup_job_tenant,
    renew_job_lease,
    verify_active_job_lease_readonly,
)
from core.risk.domain.aggregation import (
    FindingInput,
    aggregate_findings,
    carry_forward_prior_red_evidence,
    check_required_bots,
    compute_finding_severity,
    determine_post_investigation_status,
    evaluate_mandatory_prefetch_coverage,
    evaluate_system_checks,
    evaluate_tool_call_floors,
    extract_tool_floor_reason_codes,
    normalize_reason_codes,
)
from core.shared.clock import Clock, SimWorldClock, SystemClock
from core.shared.config import CoreSettings
from core.shared.errors import ProblemError, install_error_handlers
from core.shared.hashing import hash_card_id_indicator, hash_merchant_id_indicator
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


# Explicit allowlist of trusted string fields per tool for BotAnswer string facts (I6)
TRUSTED_BOT_ANSWER_STRING_FIELDS: dict[str, frozenset[str]] = {
    "account_balance": frozenset({"as_of", "wallet_id"}),
    "spending_limits": frozenset({"mode", "mandate_id", "date", "updated_at"}),
    "payment_policy_preview": frozenset({"decision", "channel", "payee_account_id", "evaluated_at"}),
    "vendor_registry": frozenset({"vendor_id", "vendor_account_id", "status", "tax_id"}),
    "tax_id_lookup": frozenset({"status_code", "status_reason_code", "tax_id"}),
    "tax_risk_list": frozenset({"listed_on"}),
    "einvoice_portal": frozenset({"tax_authority_code"}),
    "payables_ledger": frozenset({"invoice_id", "vendor_id", "due_on", "issued_on", "status"}),
    "price_check": frozenset({"line_id", "sku", "contract_item_id"}),
    "three_way_match": frozenset({"purchase_order_id", "goods_receipt_id"}),
    "utility_baseline": frozenset({"utility_type", "store_id"}),
    "cross_alerts": frozenset({"cross_alert_id", "indicator_kind"}),
    "official_fraud_list": frozenset({"list_ref"}),
    "invoice_search": frozenset({"invoice_id", "vendor_id", "store_id", "status", "severity", "due_on", "issued_on", "invoice_type"}),
    "invoice_explain": frozenset({"invoice_id", "vendor_id", "store_id", "status", "severity", "due_on", "issued_on", "invoice_type"}),
    "queue_status": frozenset({"nearest_due_on"}),
}


def _ref_in_json(obj: Any, needle: str) -> bool:
    """Exact typed evidence ID match inside tool output JSON (I6: no substring matching)."""
    if isinstance(obj, str):
        return obj == needle
    if isinstance(obj, dict):
        return any(_ref_in_json(v, needle) for v in obj.values())
    if isinstance(obj, list):
        return any(_ref_in_json(v, needle) for v in obj)
    return False


def _allowlisted_string_in_json(
    obj: Any,
    needle: str,
    *,
    allowed_keys: frozenset[str],
    current_key: str | None = None,
) -> bool:
    """Match a string fact ONLY under an explicitly allowlisted trusted field name (I6)."""
    if isinstance(obj, str):
        if current_key not in allowed_keys:
            return False
        if obj == needle:
            return True
        # Allow YYYY-MM-DD date prefix of an allowlisted ISO timestamp field
        if len(needle) == 10 and obj.startswith(needle) and len(obj) > 10 and obj[10] == "T":
            return True
        return False
    if isinstance(obj, dict):
        if obj.get("provenance") == "untrusted":
            return False
        for k, v in obj.items():
            if k == "untrusted":
                continue
            if _allowlisted_string_in_json(v, needle, allowed_keys=allowed_keys, current_key=k):
                return True
        return False
    if isinstance(obj, list):
        return any(
            _allowlisted_string_in_json(v, needle, allowed_keys=allowed_keys, current_key=current_key)
            for v in obj
        )
    return False


def _value_in_json(obj: Any, needle: str | int | float, *, trusted_only: bool = False) -> bool:
    """Check if needle appears in obj. Exact match for strings and numbers (I6)."""
    if isinstance(obj, bool):
        return False
    if isinstance(obj, (int, float)):
        if isinstance(needle, (int, float)) and not isinstance(needle, bool):
            return float(obj) == float(needle)
        return str(obj) == str(needle)
    if isinstance(obj, str):
        needle_str = str(needle)
        return obj == needle_str
    if isinstance(obj, dict):
        if trusted_only and obj.get("provenance") == "untrusted":
            return False
        for k, v in obj.items():
            if trusted_only and k == "untrusted":
                continue
            if _value_in_json(v, needle, trusted_only=trusted_only):
                return True
        return False
    if isinstance(obj, list):
        return any(_value_in_json(v, needle, trusted_only=trusted_only) for v in obj)
    return False


def _sanitize_question_history(raw_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """B3: pass user messages with text_trusted and assistant messages as structured {message_id, citations} only."""
    sanitized: list[dict[str, Any]] = []
    for m in raw_messages:
        role = m.get("role")
        if role == "user":
            sanitized.append({"role": "user", "text_trusted": m.get("text_trusted", "")})
        elif role == "assistant":
            sanitized.append(
                {
                    "role": "assistant",
                    "message_id": m.get("message_id", ""),
                    "citations": list(m.get("citations") or []),
                }
            )
    return sanitized


def _build_session_payload(
    conn: psycopg.Connection,
    *,
    job: dict[str, Any],
    keys: Ed25519KeyManager,
    now: datetime,
    sec_now: datetime | None = None,
    ttl_seconds: int = 120,
) -> tuple[dict[str, Any], list[str], list[dict[str, str]]]:
    """Compute supervisor & bot capability grants, required_bot_ids, skipped bots, and context."""
    tid = job["tenant_id"]
    task_type = job["task_type"]
    subject = job["subject"]
    invoice_id = subject.get("invoice_id") if task_type == "investigate_invoice" else None
    invoice_type: str | None = None
    token_now = sec_now or now

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
            "messages": _sanitize_question_history(subject.get("messages", [])),
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

    now_ts = int(token_now.timestamp())
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

    # B3: Existing non-superseded findings for THIS attempt ONLY (plus ingest findings for this invoice)
    current_attempt = int(job["attempt"])
    existing_findings = conn.execute(
        """
        SELECT * FROM core.findings
        WHERE tenant_id = %s AND invoice_id = %s AND superseded = FALSE
          AND ((job_id = %s AND attempt = %s) OR bot_id = 'ingest')
        ORDER BY created_at ASC
        """,
        (tid, invoice_id, job_id, current_attempt),
    ).fetchall()

    submitted_bot_ids = {f["bot_id"] for f in existing_findings if f["bot_id"] not in {"ingest", "system"}}
    required_bot_ids = list(job.get("required_bot_ids") or [])
    skipped_bot_ids = [s["bot_id"] for s in (job.get("skipped_bots") or [])]

    # Load active bot manifests for required-bot inference and mandatory prefetch checking (B3, I1)
    sys_bots = conn.execute(
        """
        SELECT d.bot_id, v.manifest, v.prefetch, v.version
        FROM control.bot_definitions d
        JOIN control.bot_versions v
          ON v.bot_id = d.bot_id AND v.tenant_id = d.tenant_id AND v.version = d.active_version
        WHERE d.scope = 'system' AND d.tenant_id = '' AND d.archived = FALSE
        """
    ).fetchall()
    if not required_bot_ids:
        for sb in sys_bots:
            if inv["invoice_type"] in (sb["manifest"].get("required_for") or []):
                required_bot_ids.append(sb["bot_id"])

    prefetch_by_bot: dict[str, list[str]] = {}
    for sb in sys_bots:
        if sb["bot_id"] in required_bot_ids:
            prefetch_by_bot[sb["bot_id"]] = list(sb["prefetch"] or [])
    # If a submitted finding ran a specific bot_version, use that exact version's prefetch list
    for f in existing_findings:
        bid = f["bot_id"]
        if bid in required_bot_ids:
            bv = conn.execute(
                """
                SELECT prefetch FROM control.bot_versions
                WHERE bot_id = %s AND version = %s AND (tenant_id = '' OR tenant_id = %s)
                ORDER BY (tenant_id = %s) DESC LIMIT 1
                """,
                (bid, f["bot_version"], tid, tid),
            ).fetchone()
            if bv is not None:
                prefetch_by_bot[bid] = list(bv["prefetch"] or [])

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
                SELECT 1 FROM risk.cross_alerts ca
                LEFT JOIN risk.indicators i ON i.indicator_id = ANY(ca.indicator_ids)
                WHERE ca.status = 'published'
                  AND (
                    (ca.indicator_kind = %s AND ca.value_hash = %s)
                    OR (i.kind = %s AND i.value_hash = %s)
                  )
                LIMIT 1
                """,
                (kind, val_hash, kind, val_hash),
            ).fetchone()
            if ca is not None:
                has_cross_alert = True
        if not has_hard_block:
            hb = conn.execute(
                """
                SELECT 1 FROM risk.hard_blocks hb
                LEFT JOIN risk.indicators i ON i.indicator_id = ANY(hb.indicator_ids)
                WHERE hb.status = 'active'
                  AND (
                    (hb.indicator_kind = %s AND hb.value_hash = %s)
                    OR (i.kind = %s AND i.value_hash = %s)
                  )
                LIMIT 1
                """,
                (kind, val_hash, kind, val_hash),
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

    # Tool-output floors across ALL tool_calls of this job attempt (covers bots that timed out,
    # failed, submitted no Finding, or submitted only BOT_TIMEOUT/BOT_INVALID_OUTPUT)
    attempt_tool_calls = conn.execute(
        """
        SELECT tool_call_id, bot_id, tool_id, output, error
        FROM core.tool_calls
        WHERE tenant_id = %s AND job_id = %s AND attempt = %s
        ORDER BY created_at ASC
        """,
        (tid, job_id, current_attempt),
    ).fetchall()
    covered_codes = {
        c for f in existing_findings for c in (f["reason_codes"] or [])
    } | {
        c for sp in sys_specs for c in sp.reason_codes
    }
    tool_floor_specs = evaluate_tool_call_floors(
        attempt_tool_calls,
        existing_reason_codes=covered_codes,
    )

    # B3: Mandatory prefetch success coverage on the current attempt (errored/empty/revoked -> yellow floor)
    prefetch_cov_specs = evaluate_mandatory_prefetch_coverage(
        required_prefetch_by_bot=prefetch_by_bot,
        attempt_tool_calls=attempt_tool_calls,
        skipped_bot_ids=skipped_bot_ids,
    )

    # B3: Carry forward confirmed red evidence from earlier attempts of this job
    prior_red_specs = []
    if current_attempt > 1:
        prior_findings = conn.execute(
            """
            SELECT severity, severity_reported, reason_codes
            FROM core.findings
            WHERE tenant_id = %s AND job_id = %s AND attempt > 0 AND attempt < %s
            ORDER BY created_at ASC
            """,
            (tid, job_id, current_attempt),
        ).fetchall()
        prior_tool_calls = conn.execute(
            """
            SELECT tool_call_id, bot_id, tool_id, output, error
            FROM core.tool_calls
            WHERE tenant_id = %s AND job_id = %s AND attempt < %s
            ORDER BY created_at ASC
            """,
            (tid, job_id, current_attempt),
        ).fetchall()
        covered_with_current_floors = covered_codes | {
            c for sp in tool_floor_specs for c in sp.reason_codes
        }
        prior_red_specs = carry_forward_prior_red_evidence(
            prior_findings=prior_findings,
            prior_tool_calls=prior_tool_calls,
            current_reason_codes=covered_with_current_floors,
        )

    new_sys_findings = [
        *missing_bot_specs,
        *sys_specs,
        *tool_floor_specs,
        *prefetch_cov_specs,
        *prior_red_specs,
    ]

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
        "SELECT value FROM control.policies WHERE kind = 'platform_limits' AND status = 'active' LIMIT 1"
    ).fetchone()
    # Nit 2: missing platform_limits policy -> not eligible for auto-pay (0 ceiling)
    platform_per_inv = (
        int((pol["value"] or {}).get("auto_pay_per_invoice_vnd", 0)) if pol is not None else 0
    )

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
                    %s, %s, %s, 'trusted', %s
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
                    Jsonb(list(sp.evidence)),
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
    security_clock: Clock | None = None,
) -> FastAPI:
    cfg = settings or CoreSettings.from_env()
    database = db or Database(cfg.database_url)
    sim_adapter = sim_world or HttpSimWorldAdapter(cfg.sim_url, cfg.sim_core_service_key)
    gate_adapter = gate_client or HttpGateAdapter(cfg.gate_url, cfg.gate_core_service_key)
    cap_keys = capability_keys or Ed25519KeyManager(cfg.capability_signing_key_pem)
    clk = clock or (
        SimWorldClock(cfg.sim_url, cfg.sim_core_service_key) if cfg.demo_mode else SystemClock()
    )
    # I2: wall clock for security (JWT iat/exp) and job leases; business clock for schedules/business dates
    sec_clk = security_clock or SystemClock()

    app = FastAPI(title="PayMatch Core Internal API", version="0.1.0")
    install_error_handlers(app)

    app.state.settings = cfg
    app.state.db = database
    app.state.sim_world = sim_adapter
    app.state.gate = gate_adapter
    app.state.cap_keys = cap_keys
    app.state.clock = clk
    app.state.security_clock = sec_clk

    # ---- Auth dependencies (strictly separated, NEVER mixed; I2 rejects empty configured keys) ----

    def require_agent_service_key(
        x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    ) -> str:
        expected = cfg.internal_agent_service_key
        if not expected:
            raise ProblemError(
                503,
                "SERVICE_MISCONFIGURED",
                "Agent service key not configured",
                "INTERNAL_AGENT_SERVICE_KEY chưa được cấu hình.",
            )
        if not x_service_key:
            raise ProblemError(401, "UNAUTHENTICATED", "Authentication required", "Thiếu header X-Service-Key.")
        if not hmac.compare_digest(x_service_key, expected):
            raise ProblemError(403, "FORBIDDEN", "Invalid service key", "X-Service-Key không hợp lệ cho agent-worker.")
        return "agent-worker"

    def require_webhook_service_key(
        x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    ) -> str:
        expected = cfg.internal_sim_webhook_key
        if not expected:
            raise ProblemError(
                503,
                "SERVICE_MISCONFIGURED",
                "Webhook service key not configured",
                "SIM_WEBHOOK_SERVICE_KEY chưa được cấu hình.",
            )
        if not x_service_key:
            raise ProblemError(401, "UNAUTHENTICATED", "Authentication required", "Thiếu header X-Service-Key.")
        if not hmac.compare_digest(x_service_key, expected):
            raise ProblemError(403, "FORBIDDEN", "Invalid service key", "X-Service-Key không hợp lệ cho sim-world.")
        return "sim-world"

    def require_capability_claims(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> dict[str, Any]:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise ProblemError(401, "UNAUTHENTICATED", "Missing capability token", "Thiếu Bearer capability token.")
        token = authorization[7:].strip()
        now_ts = int(sec_clk.now().timestamp())
        claims = cap_keys.verify(
            token,
            audience="internal-api",
            issuer="core",
            now_ts=now_ts,
        )
        # I1: strictly validate required capability claims & TTL cap (exp <= now + 120 even if iat absent)
        if "exp" not in claims or not isinstance(claims["exp"], int):
            raise ProblemError(401, "UNAUTHENTICATED", "Missing exp claim", "Capability token thiếu exp.")
        exp_ts = int(claims["exp"])
        if exp_ts > now_ts + 120:
            raise ProblemError(
                401,
                "UNAUTHENTICATED",
                "Capability token TTL too long",
                "Capability token có exp vượt quá 120 giây so với thời điểm hiện tại.",
            )
        if "iat" in claims:
            if not isinstance(claims["iat"], int):
                raise ProblemError(401, "UNAUTHENTICATED", "Invalid iat claim", "iat phải là số nguyên.")
            iat_ts = int(claims["iat"])
            if iat_ts > now_ts + 5:
                raise ProblemError(401, "UNAUTHENTICATED", "Token not yet valid", "Capability token chưa có hiệu lực.")
            if (exp_ts - iat_ts) > 120:
                raise ProblemError(
                    401,
                    "UNAUTHENTICATED",
                    "Capability token TTL too long",
                    "Capability token vượt quá thời hạn tối đa 120 giây (exp - iat > 120).",
                )
        sub = claims.get("sub")
        bot_ver = claims.get("bot_version")
        if (
            not isinstance(sub, str)
            or not sub
            or not isinstance(claims.get("tenant_id"), str)
            or not claims["tenant_id"]
            or not isinstance(claims.get("job_id"), str)
            or not claims["job_id"]
            or not isinstance(claims.get("worker_id"), str)
            or not claims["worker_id"]
            or not isinstance(claims.get("attempt"), int)
            or int(claims["attempt"]) < 1
            or not isinstance(claims.get("tools"), list)
        ):
            raise ProblemError(401, "UNAUTHENTICATED", "Invalid capability claims", "Thiếu claim bắt buộc trong capability token.")
        if sub == "supervisor" and bot_ver is not None:
            raise ProblemError(401, "UNAUTHENTICATED", "Invalid supervisor token", "Token supervisor phải có bot_version=null.")
        if sub != "supervisor" and (not isinstance(bot_ver, int) or bot_ver < 1):
            raise ProblemError(401, "UNAUTHENTICATED", "Invalid bot token", "Token bot phải có bot_version >= 1.")
        return claims

    def _resolve_job_tenant(job_id: str) -> str:
        with database.connect() as conn:
            return lookup_job_tenant(conn, job_id)

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
        # I2: job leases use wall clock (security_clock); B1: narrow SECURITY DEFINER claim function
        sec_now = sec_clk.now()
        lease_until = sec_now + timedelta(seconds=cfg.job_lease_seconds)
        allowed_types = (
            [t.value for t in body.task_types]
            if body.task_types
            else ["question", "investigate_invoice", "report"]
        )

        with database.connect() as conn:
            with conn.transaction():
                updated = claim_next_job(
                    conn,
                    worker_id=body.worker_id,
                    allowed_types=allowed_types,
                    lease_until=lease_until,
                    now=sec_now,
                    max_concurrent_per_tenant=cfg.max_concurrent_jobs_per_tenant,
                )
                if updated is None:
                    return Response(status_code=204)

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
        biz_now = clk.now()
        sec_now = sec_clk.now()
        tid = _resolve_job_tenant(job_id)
        with database.connect(role="merchant", tenant_id=tid) as conn:
            with conn.transaction():
                job = lock_active_job_lease(
                    conn,
                    job_id=job_id,
                    tenant_id=tid,
                    worker_id=body.worker_id,
                    attempt=body.attempt,
                    now=sec_now,
                )
                payload, required_bot_ids, skipped = _build_session_payload(
                    conn,
                    job=job,
                    keys=cap_keys,
                    now=biz_now,
                    sec_now=sec_now,
                    ttl_seconds=min(cfg.job_lease_seconds, 120),
                )
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
                    WHERE tenant_id = %s AND job_id = %s
                    """,
                    (required_bot_ids, Jsonb(skipped), Jsonb(bot_states), sec_now, tid, job_id),
                )
        return payload

    @app.post("/internal/jobs/{job_id}/heartbeat")
    def heartbeat_job(
        job_id: str,
        body: internal_models.JobHeartbeatRequest,
        _caller: str = Depends(require_agent_service_key),
    ) -> dict[str, Any]:
        biz_now = clk.now()
        sec_now = sec_clk.now()
        new_lease = sec_now + timedelta(seconds=cfg.job_lease_seconds)
        tid = _resolve_job_tenant(job_id)
        with database.connect(role="merchant", tenant_id=tid) as conn:
            with conn.transaction():
                # B6: atomic guarded UPDATE by job_id + tenant_id + running + worker_id + attempt + lease_expires_at >= sec_now
                job = renew_job_lease(
                    conn,
                    job_id=job_id,
                    tenant_id=tid,
                    worker_id=body.worker_id,
                    attempt=body.attempt,
                    now=sec_now,
                    new_lease=new_lease,
                )
                session_payload, _, _ = _build_session_payload(
                    conn,
                    job=job,
                    keys=cap_keys,
                    now=biz_now,
                    sec_now=sec_now,
                    ttl_seconds=min(cfg.job_lease_seconds, 120),
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
        sec_now = sec_clk.now()
        trace_id = _extract_trace_id(traceparent)
        tid = _resolve_job_tenant(job_id)
        with database.connect(role="merchant", tenant_id=tid) as conn:
            with conn.transaction():
                # B6: lock active job lease inside the SAME transaction as progress writes
                job = lock_active_job_lease(
                    conn,
                    job_id=job_id,
                    tenant_id=tid,
                    worker_id=body.worker_id,
                    attempt=body.attempt,
                    now=sec_now,
                )
                bot_states = {s["bot_id"]: dict(s) for s in (job.get("bot_states") or [])}
                bots_called = {c["bot_id"]: dict(c) for c in (job.get("bots_called") or [])}
                for ev in body.events:
                    ev_type = ev.type.value
                    if ev_type == "answer.delta":
                        if job["task_type"] != "question":
                            raise ProblemError(
                                400,
                                "VALIDATION_FAILED",
                                "Invalid progress event",
                                "Sự kiện answer.delta chỉ hợp lệ cho job question.",
                            )
                        if ev.text_delta is None:
                            raise ProblemError(
                                400,
                                "VALIDATION_FAILED",
                                "Missing text_delta",
                                "Sự kiện answer.delta bắt buộc có text_delta.",
                            )
                    elif ev.text_delta is not None:
                        raise ProblemError(
                            400,
                            "VALIDATION_FAILED",
                            "Unexpected text_delta",
                            "text_delta chỉ được phép với sự kiện answer.delta.",
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
                    if ev_type == "answer.delta" and ev.text_delta is not None:
                        outbox_data["text_delta"] = ev.text_delta
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
        sec_now = sec_clk.now()
        # Invariant #1: token bound to exact job, bot, and bot_version (I1)
        if claims.get("job_id") != job_id:
            raise ProblemError(403, "FORBIDDEN", "Job mismatch", "Capability token không thuộc job này.")
        if claims.get("sub") == "supervisor" or claims.get("sub") != body.bot_id:
            raise ProblemError(403, "FORBIDDEN", "Bot mismatch", "bot_id phải khớp sub trong capability token.")
        if int(claims.get("bot_version") or 0) != int(body.bot_version):
            raise ProblemError(
                403,
                "FORBIDDEN",
                "Bot version mismatch",
                "bot_version phải khớp bot_version đã ký trong capability token.",
            )

        tid = claims["tenant_id"]
        attempt = int(claims["attempt"])
        with database.connect(role="merchant", tenant_id=tid) as conn:
            with conn.transaction():
                # B6: lock active job lease inside the SAME transaction as finding persistence
                job = lock_active_job_lease(
                    conn,
                    job_id=job_id,
                    tenant_id=tid,
                    worker_id=claims["worker_id"],
                    attempt=attempt,
                    now=sec_now,
                )
                if job["task_type"] != "investigate_invoice":
                    raise ProblemError(409, "INVALID_STATE", "Wrong task type", "Findings chỉ áp dụng cho investigate_invoice.")
                if _is_kill_switch_active(conn, tenant_id=tid, bot_id=body.bot_id):
                    raise ProblemError(423, "KILL_SWITCH_ACTIVE", "Kill switch active", "Bot hoặc tenant đang bị chặn.")

                # Fetch all tool calls made by this bot in this attempt
                tcs = conn.execute(
                    """
                    SELECT tool_call_id, tool_id, output, provenance, error
                    FROM core.tool_calls
                    WHERE tenant_id = %s AND job_id = %s AND attempt = %s AND bot_id = %s
                    """,
                    (tid, job_id, attempt, body.bot_id),
                ).fetchall()
                tc_by_id = {tc["tool_call_id"]: tc for tc in tcs}
                called_tool_ids = {tc["tool_id"] for tc in tcs}

                # I1: Resolve exact signed bot_version manifest; fail closed if unknown
                bot_ver = conn.execute(
                    """
                    SELECT prefetch FROM control.bot_versions
                    WHERE bot_id = %s AND version = %s AND (tenant_id = '' OR tenant_id = %s)
                    ORDER BY (tenant_id = %s) DESC LIMIT 1
                    """,
                    (body.bot_id, body.bot_version, tid, tid),
                ).fetchone()
                if bot_ver is None:
                    raise ProblemError(
                        400,
                        "VALIDATION_FAILED",
                        "Unknown bot version",
                        f"Không tìm thấy manifest cho bot '{body.bot_id}' phiên bản {body.bot_version}.",
                    )

                # I1 & B3: Do NOT intersect mandatory prefetch with token tools; treat revoked/errored/empty as fail-closed
                required_prefetch = list(bot_ver["prefetch"] or [])
                granted_set = set(claims.get("tools") or [])
                submitted_codes = [c.value for c in body.reason_codes]
                is_prefetch_exempt = (
                    len(submitted_codes) > 0
                    and set(submitted_codes) <= {"BOT_TIMEOUT", "BOT_INVALID_OUTPUT"}
                    and len(body.evidence) == 0
                )
                ungranted_prefetch = [p for p in required_prefetch if p not in granted_set]
                missing_prefetch = [
                    p for p in required_prefetch if p not in called_tool_ids and p not in ungranted_prefetch
                ]
                if missing_prefetch and not is_prefetch_exempt:
                    raise ProblemError(
                        400,
                        "VALIDATION_FAILED",
                        "Missing prefetch tools",
                        f"Bot '{body.bot_id}' chưa gọi đủ tool prefetch: {missing_prefetch}.",
                        errors=[{"field": "prefetch", "code": "missing", "detail": ", ".join(missing_prefetch)}],
                    )

                # B3: Any revoked, errored, or empty mandatory prefetch forces at least yellow floor
                prefetch_fail_codes: list[str] = []
                if ungranted_prefetch:
                    prefetch_fail_codes.append("BOT_DISABLED")
                for p in required_prefetch:
                    if p in ungranted_prefetch or p in missing_prefetch:
                        continue
                    p_calls = [tc for tc in tcs if tc["tool_id"] == p]
                    succeeded = any((tc["error"] is None) and bool(tc["output"]) for tc in p_calls)
                    if not succeeded:
                        had_timeout = any(
                            isinstance(tc.get("error"), dict) and tc["error"].get("code") == "UPSTREAM_TIMEOUT"
                            for tc in p_calls
                        )
                        prefetch_fail_codes.append("BOT_TIMEOUT" if had_timeout else "BOT_NOT_RUN")

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

                # Apply tool-output floor (internal-api.md §3), prefetch failure floor (B3), and reason-code floor/ceiling
                tool_floor_codes = extract_tool_floor_reason_codes(tcs)
                merged_codes = normalize_reason_codes(
                    [*submitted_codes, *tool_floor_codes, *prefetch_fail_codes]
                )
                final_sev = compute_finding_severity(body.severity_reported.value, merged_codes)

                # Enforce provenance: if any tool call was untrusted or bot reported untrusted -> untrusted
                provenance = body.provenance.value
                if any(tc["provenance"] == "untrusted" for tc in tcs):
                    provenance = "untrusted"

                finding_id = new_id("fnd")
                evidence_dicts = [e.model_dump(mode="json") for e in body.evidence]

                # Supersede earlier finding from the same bot in THIS attempt (keeping history)
                conn.execute(
                    """
                    UPDATE core.findings
                    SET superseded = TRUE
                    WHERE tenant_id = %s AND job_id = %s AND attempt = %s AND bot_id = %s AND superseded = FALSE
                    """,
                    (tid, job_id, attempt, body.bot_id),
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
                        tid,
                        job_id,
                        job["invoice_id"],
                        attempt,
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
        sec_now = sec_clk.now()
        if claims.get("job_id") != job_id:
            raise ProblemError(403, "FORBIDDEN", "Job mismatch", "Capability token không thuộc job này.")
        if claims.get("sub") == "supervisor" or claims.get("sub") != body.bot_id:
            raise ProblemError(403, "FORBIDDEN", "Bot mismatch", "bot_id phải khớp sub trong capability token.")

        tid = claims["tenant_id"]
        attempt = int(claims["attempt"])
        with database.connect(role="merchant", tenant_id=tid) as conn:
            with conn.transaction():
                # B6: atomic lease lock in same transaction as bot_answers write
                job = lock_active_job_lease(
                    conn,
                    job_id=job_id,
                    tenant_id=tid,
                    worker_id=claims["worker_id"],
                    attempt=attempt,
                    now=sec_now,
                )
                if job["task_type"] not in {"question", "report"}:
                    raise ProblemError(409, "INVALID_STATE", "Wrong task type", "bot-answers chỉ áp dụng cho question/report.")
                tcs = conn.execute(
                    """
                    SELECT tool_call_id, tool_id, output, provenance FROM core.tool_calls
                    WHERE tenant_id = %s AND job_id = %s AND attempt = %s AND bot_id = %s
                    """,
                    (tid, job_id, attempt, body.bot_id),
                ).fetchall()
                tc_by_id = {tc["tool_call_id"]: tc for tc in tcs}

                verified_facts = []
                for f in body.facts:
                    tc = tc_by_id.get(f.tool_call_id)
                    if tc is None:
                        continue
                    if isinstance(f.value, str):
                        # B3/I6: string values are accepted ONLY from explicitly allowlisted trusted fields of the cited tool
                        allowed_keys = TRUSTED_BOT_ANSWER_STRING_FIELDS.get(tc["tool_id"], frozenset())
                        ok = (
                            tc["provenance"] == "trusted"
                            and bool(allowed_keys)
                            and _allowlisted_string_in_json(
                                tc["output"], f.value, allowed_keys=allowed_keys
                            )
                        )
                    else:
                        ok = _value_in_json(tc["output"], f.value, trusted_only=False)
                    if ok:
                        verified_facts.append(
                            {
                                "key": f.key.value,
                                "value": f.value,
                                "tool_call_id": f.tool_call_id,
                                "verified": True,
                            }
                        )

                rc_list = [c.value for c in body.reason_codes]
                conn.execute(
                    """
                    INSERT INTO core.bot_answers (bot_answer_id, tenant_id, job_id, attempt, bot_id, facts, reason_codes, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        new_id("ban"),
                        tid,
                        job_id,
                        attempt,
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
        sec_now = sec_clk.now()
        trace_id = _extract_trace_id(traceparent)
        tid = _resolve_job_tenant(job_id)
        with database.connect(role="merchant", tenant_id=tid) as conn:
            with conn.transaction():
                # B6: lock active job lease inside the SAME transaction as completion!
                job = lock_active_job_lease(
                    conn,
                    job_id=job_id,
                    tenant_id=tid,
                    worker_id=body.worker_id,
                    attempt=body.attempt,
                    now=sec_now,
                )
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
                    (tid, job_id, body.attempt),
                ).fetchall()
                tc_by_id = {tc["tool_call_id"]: tc["output"] for tc in tcs}
                unverified: list[str] = []
                for cit in ans.citations:
                    out = tc_by_id.get(cit.tool_call_id)
                    for val in cit.values:
                        if out is None or not _value_in_json(out, val):
                            unverified.append(val)
                conn.execute(
                    "UPDATE core.jobs SET status = 'completed', completed_at = %s, updated_at = %s WHERE tenant_id = %s AND job_id = %s",
                    (now, now, tid, job_id),
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
        sec_now = sec_clk.now()
        trace_id = _extract_trace_id(traceparent)
        tid = _resolve_job_tenant(job_id)
        with database.connect(role="merchant", tenant_id=tid) as conn:
            with conn.transaction():
                # B6: lock active job lease inside the SAME transaction as fail/retry!
                job = lock_active_job_lease(
                    conn,
                    job_id=job_id,
                    tenant_id=tid,
                    worker_id=body.worker_id,
                    attempt=body.attempt,
                    now=sec_now,
                )
                err_payload = {"error_code": body.error_code, "detail": body.detail}
                if job["attempt"] < 2:
                    conn.execute(
                        """
                        UPDATE core.jobs
                        SET status = 'queued', worker_id = NULL, lease_expires_at = NULL,
                            last_error = %s, updated_at = %s
                        WHERE tenant_id = %s AND job_id = %s
                        """,
                        (Jsonb(err_payload), now, tid, job_id),
                    )
                    return {"will_retry": True}

                # Exhausted retries: investigate_invoice completes without brief (missing bots -> yellow BOT_NOT_RUN; tool floors -> red)
                if job["task_type"] == "investigate_invoice":
                    conn.execute(
                        "UPDATE core.jobs SET last_error = %s, updated_at = %s WHERE tenant_id = %s AND job_id = %s",
                        (Jsonb(err_payload), now, tid, job_id),
                    )
                    _complete_investigation_job(
                        conn, job=job, brief_submission=None, now=now, trace_id=trace_id
                    )
                else:
                    conn.execute(
                        """
                        UPDATE core.jobs
                        SET status = 'failed', last_error = %s, completed_at = %s, updated_at = %s
                        WHERE tenant_id = %s AND job_id = %s
                        """,
                        (Jsonb(err_payload), now, now, tid, job_id),
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

    # ---- Tools (CapabilityBearerAuth, B1 tenant RLS + B6 lease fencing) ----

    @app.get("/internal/tools")
    def list_granted_tools(
        claims: dict[str, Any] = Depends(require_capability_claims),
    ) -> list[dict[str, Any]]:
        sec_now = sec_clk.now()
        tid = claims["tenant_id"]
        with database.connect(role="merchant", tenant_id=tid) as conn:
            verify_active_job_lease_readonly(
                conn,
                job_id=claims["job_id"],
                tenant_id=tid,
                worker_id=claims["worker_id"],
                attempt=int(claims["attempt"]),
                now=sec_now,
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
        sec_now = sec_clk.now()
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

        tid = claims["tenant_id"]
        attempt = int(claims["attempt"])
        worker_id = claims["worker_id"]
        job_id = claims["job_id"]
        bot_id = claims["sub"]

        with database.connect(role="merchant", tenant_id=tid) as conn:
            verify_active_job_lease_readonly(
                conn,
                job_id=job_id,
                tenant_id=tid,
                worker_id=worker_id,
                attempt=attempt,
                now=sec_now,
            )
            if _is_kill_switch_active(
                conn,
                tenant_id=tid,
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
                tenant_id=tid,
                job_id=job_id,
                attempt=attempt,
                bot_id=bot_id,
                invoice_id=claims.get("invoice_id"),
                store_ids=claims.get("store_ids"),
            )

            def _fence_lease(write_conn: psycopg.Connection) -> None:
                lock_active_job_lease(
                    write_conn,
                    job_id=job_id,
                    tenant_id=tid,
                    worker_id=worker_id,
                    attempt=attempt,
                    now=sec_clk.now(),
                )

            return invoke_tool(
                conn,
                tool_id=tool_id,
                raw_input=body.input,
                ctx=ctx,
                sim_world=sim_adapter,
                gate_client=gate_adapter,
                clock=clk,
                lease_guard=_fence_lease,
                utility_outlier_ratio=Decimal(cfg.utility_outlier_ratio),
            )

    # ---- Rails webhook from sim-world (ServiceKeyAuth, B1 narrow SECURITY DEFINER) ----

    @app.post("/internal/webhooks/rails", status_code=204)
    def receive_rails_webhook(
        body: internal_models.RailsWebhookRequest,
        traceparent: str | None = Header(default=None),
        _caller: str = Depends(require_webhook_service_key),
    ) -> Response:
        now = clk.now()
        trace_id = _extract_trace_id(traceparent)
        data_dict = body.data.model_dump(mode="json")
        ev_type = body.type

        outbox_evt_id: str | None = None
        outbox_data: dict[str, Any] | None = None
        if ev_type == "card.authorization_declined":
            card_hash = hash_card_id_indicator(data_dict["card_id"])
            merchant_hash = hash_merchant_id_indicator(data_dict["merchant_id"])
            opaque_ref = "srf_" + hashlib.sha256(body.event_id.encode("utf-8")).hexdigest()[:16]
            outbox_evt_id = new_id("evt")
            outbox_data = {
                "indicators": [
                    {"kind": "card_id", "value_hash": card_hash},
                    {"kind": "merchant_id", "value_hash": merchant_hash},
                ],
                "reason_codes": ["OFFICIAL_FRAUD_LIST"],
                "source": "rail",
                "source_ref": opaque_ref,
            }

        with database.connect() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    SELECT core.receive_rails_webhook_event(%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        body.event_id,
                        ev_type,
                        body.occurred_at,
                        Jsonb(data_dict),
                        now,
                        outbox_evt_id,
                        trace_id,
                        Jsonb(outbox_data) if outbox_data is not None else None,
                    ),
                )
        return Response(status_code=204)

    return app


def main() -> None:
    cfg = CoreSettings.from_env()
    uvicorn.run(create_internal_app(cfg), host="0.0.0.0", port=cfg.internal_port)


if __name__ == "__main__":
    main()
