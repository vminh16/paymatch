"""Contract-faithful fake core internal-api backed by httpx.MockTransport for tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
from paymatch_contracts.internal import (
    BotSessionGrant,
    BotSkillContent,
    ClaimedJobResponse,
    CompleteJobRequest,
    EvidenceRef,
    FailJobRequest,
    FindingForSupervisor,
    InvestigateSessionContext,
    InvoiceType,
    JobHeartbeatRequest,
    JobProgressEventItem,
    JobProgressRequest,
    JobSessionResponse,
    Kind1,
    OpenJobSessionRequest,
    Provenance,
    ReasonCode,
    RenewedCapabilityToken,
    SessionBudget,
    Severity,
    SkippedBotItem,
    SupervisorSessionGrant,
    TaskType,
    ToolDefinition,
)
from paymatch_contracts.schemas.finding_submission_schema import FindingSubmission

from agent_runtime.plugins.loader import load_all_system_bot_plugins

# Monotonic floor/ceiling table per docs/03-agents/agent-runtime.md §5a
REASON_CODE_FLOOR: dict[ReasonCode, Severity] = {
    ReasonCode.OK: Severity.green,
    ReasonCode.PRICE_ABOVE_CONTRACT: Severity.yellow,
    ReasonCode.PACK_SIZE_CHANGED: Severity.yellow,
    ReasonCode.QUANTITY_ABOVE_NORM: Severity.yellow,
    ReasonCode.NO_GOODS_RECEIPT: Severity.yellow,
    ReasonCode.DUPLICATE_INVOICE: Severity.red,
    ReasonCode.PAYEE_CHANGE_REQUEST: Severity.red,
    ReasonCode.PERSONAL_ACCOUNT: Severity.red,
    ReasonCode.HIDDEN_INSTRUCTION: Severity.red,
    ReasonCode.URGENCY_PRESSURE: Severity.yellow,
    ReasonCode.CROSS_ALERT_HIT: Severity.yellow,
    ReasonCode.OFFICIAL_FRAUD_LIST: Severity.red,
    ReasonCode.TAX_RISK_LIST: Severity.red,
    ReasonCode.MST_INACTIVE: Severity.red,
    ReasonCode.INVOICE_NOT_FOUND_ON_PORTAL: Severity.red,
    ReasonCode.VAT_DEDUCTION_RISK: Severity.yellow,
    ReasonCode.UTILITY_OUT_OF_RANGE: Severity.yellow,
    ReasonCode.OVER_LIMIT: Severity.yellow,
    ReasonCode.LOW_BALANCE: Severity.yellow,
    ReasonCode.NON_XML_SOURCE: Severity.yellow,
    ReasonCode.AMOUNT_MISMATCH: Severity.yellow,
    ReasonCode.UNKNOWN_VENDOR: Severity.yellow,
    ReasonCode.BOT_TIMEOUT: Severity.yellow,
    ReasonCode.BOT_INVALID_OUTPUT: Severity.yellow,
    ReasonCode.BOT_NOT_RUN: Severity.yellow,
    ReasonCode.BOT_DISABLED: Severity.yellow,
    ReasonCode.CUSTOM: Severity.yellow,
}

_PREFETCH_EXEMPT_CODES: frozenset[ReasonCode] = frozenset(
    {ReasonCode.BOT_TIMEOUT, ReasonCode.BOT_INVALID_OUTPUT}
)

_SEV_RANK = {Severity.green: 0, Severity.yellow: 1, Severity.red: 2}
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def make_ulid(prefix: str, seed_num: int) -> str:
    """Deterministic Crockford Base32 ID matching contract regex `^<prefix>_[0-9A-HJKMNP-TV-Z]{26}$`."""
    chars = []
    n = seed_num
    for _ in range(26):
        chars.append(_CROCKFORD[n % 32])
        n //= 32
    return f"{prefix}_{''.join(reversed(chars))}"


def make_deterministic_ulid(prefix: str, key: str) -> str:
    """Deterministic Crockford Base32 ID derived from a string key (parallel-safe)."""
    digest = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:16], "big")
    return make_ulid(prefix, digest)


def apply_finding_floor(severity_reported: Severity, reason_codes: list[ReasonCode]) -> Severity:
    """Compute Finding severity after code floors and CROSS_ALERT_HIT ceiling."""
    sev = severity_reported
    for rc in reason_codes:
        floor = REASON_CODE_FLOOR[rc]
        if _SEV_RANK[floor] > _SEV_RANK[sev]:
            sev = floor
    if set(reason_codes) == {ReasonCode.CROSS_ALERT_HIT}:
        return Severity.yellow
    return sev


def compute_final_severity(findings: list[FindingForSupervisor]) -> Severity:
    """Monotonic worst-severity aggregation across all findings."""
    worst = Severity.green
    for f in findings:
        if _SEV_RANK[f.severity] > _SEV_RANK[worst]:
            worst = f.severity
    return worst


@dataclass
class TokenRecord:
    holder: str
    job_id: str
    attempt: int
    tools: list[str]


@dataclass
class RecordedServerToolCall:
    job_id: str
    attempt: int
    holder: str
    tool_id: str
    tool_call_id: str
    serialized_data: str


@dataclass
class JobFixture:
    job_id: str
    tenant_id: str
    invoice_id: str
    invoice_type: InvoiceType
    task_type: TaskType = TaskType.investigate_invoice
    attempt: int = 1
    budget_seconds: int = 30
    budget_max_steps: int = 12
    active_bot_ids: list[str] | None = None
    required_bot_ids: list[str] | None = None
    skipped: list[SkippedBotItem] = field(default_factory=list)
    supervisor_tools: list[ToolDefinition] = field(default_factory=list)
    tool_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    tool_provenance: dict[str, Provenance] = field(default_factory=dict)
    tool_errors: dict[str, tuple[str, str]] = field(default_factory=dict)
    bot_token_tools_override: dict[str, list[str]] = field(default_factory=dict)
    invoke_tool_403_tools: set[str] = field(default_factory=set)
    pre_findings: list[FindingForSupervisor] = field(default_factory=list)
    kill_switched_tools: set[str] = field(default_factory=set)
    transient_500_tools: dict[str, int] = field(default_factory=dict)
    tool_delay_s: dict[str, float] = field(default_factory=dict)
    subject_override: dict[str, Any] | None = None


class FakeInternalApiServer:
    """In-memory fake core internal-api speaking real HTTP via async httpx.MockTransport.

    Enforces contract semantics like core:
    - Strict separation of ServiceKeyAuth vs CapabilityBearerAuth.
    - Lease checking -> 409 LEASE_LOST.
    - Prefetch completion on POST /findings (with exact 1f69ce8 fail-closed exemption:
      reason_codes <= {BOT_TIMEOUT, BOT_INVALID_OUTPUT} and evidence == []).
    - Evidence ownership on POST /findings (every evidence[].tool_call_id belongs to
      (job_id, attempt, bot_id) and ref_id matches tool_call_id or appears in its output).
    """

    def __init__(self, service_key: str = "test-service-key") -> None:
        self.service_key = service_key
        self._plugins = load_all_system_bot_plugins()
        self._queue: deque[JobFixture] = deque()
        self._jobs: dict[str, JobFixture] = {}
        self._leases: dict[str, tuple[str, int]] = {}
        self._tokens: dict[str, TokenRecord] = {}
        self._token_seq = 0
        self._per_holder_tool_seq: dict[tuple[str, str, str], int] = {}
        self._fnd_seq = 100

        # Server-side tool call audit log & session prefetch table for core-like enforcement
        self._server_tool_calls: dict[str, RecordedServerToolCall] = {}
        self._called_tools_by_holder: dict[tuple[str, int, str], set[str]] = {}
        self._required_prefetch: dict[tuple[str, str], list[str]] = {}

        # Recorded audit state for assertions
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.progress_events: list[JobProgressEventItem] = []
        self.heartbeats: list[JobHeartbeatRequest] = []
        self.submitted_findings: dict[str, list[FindingSubmission]] = {}
        self.stored_findings_for_sup: dict[str, list[FindingForSupervisor]] = {}
        self.completed_jobs: dict[str, dict[str, Any]] = {}
        self.failed_jobs: dict[str, list[FailJobRequest]] = {}
        self.tool_invocations: list[tuple[str, str, dict[str, Any], str]] = []

        # Fault injection knobs
        self.revoke_lease_after_heartbeats: int | None = None
        self.fail_tool_on_409_lease_lost: bool = False
        self.fail_claim_503_remaining: int = 0
        self.fail_open_session_503_remaining: int = 0
        self.fail_heartbeat_503_remaining: int = 0

    def enqueue_job(self, fixture: JobFixture) -> None:
        self._jobs[fixture.job_id] = fixture
        self._queue.append(fixture)

    def revoke_lease(self, job_id: str) -> None:
        self._leases.pop(job_id, None)

    def make_httpx_client(self, base_url: str = "http://internal-api.test") -> httpx.AsyncClient:
        transport = httpx.MockTransport(self._handle_request)
        return httpx.AsyncClient(base_url=base_url, transport=transport)

    def _next_token(self, holder: str, job_id: str, attempt: int, tools: list[str]) -> str:
        self._token_seq += 1
        tok = f"cap_{job_id}_{holder}_a{attempt}_v{self._token_seq}"
        self._tokens[tok] = TokenRecord(holder=holder, job_id=job_id, attempt=attempt, tools=tools)
        return tok

    def _problem(self, status: int, code: str, detail: str) -> httpx.Response:
        return httpx.Response(
            status,
            headers={"Content-Type": "application/problem+json"},
            json={
                "type": f"https://paymatch.dev/problems/{code.lower().replace('_', '-')}",
                "title": code,
                "status": status,
                "code": code,
                "detail": detail,
            },
        )

    def _check_service_auth(self, request: httpx.Request) -> httpx.Response | None:
        if "authorization" in request.headers:
            return self._problem(400, "VALIDATION_FAILED", "Mixed auth headers forbidden")
        if request.headers.get("x-service-key") != self.service_key:
            return self._problem(401, "UNAUTHENTICATED", "Invalid X-Service-Key")
        return None

    def _check_capability_auth(self, request: httpx.Request) -> TokenRecord | httpx.Response:
        if "x-service-key" in request.headers:
            return self._problem(400, "VALIDATION_FAILED", "Mixed auth headers forbidden")
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return self._problem(401, "UNAUTHENTICATED", "Missing Bearer capability token")
        token = auth[len("Bearer ") :]
        rec = self._tokens.get(token)
        if rec is None:
            return self._problem(401, "TOKEN_EXPIRED", "Unknown or expired token")
        lease = self._leases.get(rec.job_id)
        if lease is None or lease[1] != rec.attempt:
            return self._problem(409, "LEASE_LOST", "Lease lost for capability token")
        return rec

    def _check_lease(self, job_id: str, worker_id: str, attempt: int) -> httpx.Response | None:
        lease = self._leases.get(job_id)
        if lease != (worker_id, attempt):
            return self._problem(409, "LEASE_LOST", f"Lease mismatch for {job_id}")
        return None

    async def _handle_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method.upper()
        self.requests.append((method, path, dict(request.headers)))
        body = json.loads(request.content.decode("utf-8")) if request.content else {}

        if method == "POST" and path == "/internal/jobs:claim":
            return self._handle_claim(request, body)
        if method == "GET" and path == "/internal/model-configs":
            return self._handle_model_configs(request)
        if method == "GET" and path == "/internal/tools":
            return self._handle_list_tools(request)

        m_invoke = re.fullmatch(r"/internal/tools/([a-z][a-z0-9_]*):invoke", path)
        if method == "POST" and m_invoke:
            return await self._handle_invoke_tool(request, m_invoke.group(1), body)

        m_session = re.fullmatch(r"/internal/jobs/(job_[0-9A-HJKMNP-TV-Z]{26})/session", path)
        if method == "POST" and m_session:
            return self._handle_session(request, m_session.group(1), body)

        m_hb = re.fullmatch(r"/internal/jobs/(job_[0-9A-HJKMNP-TV-Z]{26})/heartbeat", path)
        if method == "POST" and m_hb:
            return self._handle_heartbeat(request, m_hb.group(1), body)

        m_prog = re.fullmatch(r"/internal/jobs/(job_[0-9A-HJKMNP-TV-Z]{26})/progress", path)
        if method == "POST" and m_prog:
            return self._handle_progress(request, m_prog.group(1), body)

        m_find = re.fullmatch(r"/internal/jobs/(job_[0-9A-HJKMNP-TV-Z]{26})/findings", path)
        if method == "POST" and m_find:
            return self._handle_submit_finding(request, m_find.group(1), body)

        m_comp = re.fullmatch(r"/internal/jobs/(job_[0-9A-HJKMNP-TV-Z]{26}):complete", path)
        if method == "POST" and m_comp:
            return self._handle_complete(request, m_comp.group(1), body)

        m_fail = re.fullmatch(r"/internal/jobs/(job_[0-9A-HJKMNP-TV-Z]{26}):fail", path)
        if method == "POST" and m_fail:
            return self._handle_fail(request, m_fail.group(1), body)

        return self._problem(404, "NOT_FOUND", f"Unknown route {method} {path}")

    def _handle_claim(self, request: httpx.Request, body: dict[str, Any]) -> httpx.Response:
        err = self._check_service_auth(request)
        if err is not None:
            return err
        if self.fail_claim_503_remaining > 0:
            self.fail_claim_503_remaining -= 1
            return self._problem(503, "UPSTREAM_UNAVAILABLE", "Temporary 503 on jobs:claim")
        if not self._queue:
            return httpx.Response(204)
        fix = self._queue.popleft()
        worker_id = body["worker_id"]
        self._leases[fix.job_id] = (worker_id, fix.attempt)
        self.submitted_findings.setdefault(fix.job_id, [])
        self.stored_findings_for_sup.setdefault(fix.job_id, list(fix.pre_findings))
        subject = fix.subject_override or {"invoice_id": fix.invoice_id}
        resp = ClaimedJobResponse.model_validate(
            {
                "job_id": fix.job_id,
                "task_type": fix.task_type.value,
                "tenant_id": fix.tenant_id,
                "attempt": fix.attempt,
                "lease_expires_at": "2026-11-26T08:30:00+07:00",
                "subject": subject,
            }
        )
        return httpx.Response(200, json=resp.model_dump(mode="json"))

    def _handle_model_configs(self, request: httpx.Request) -> httpx.Response:
        err = self._check_service_auth(request)
        if err is not None:
            return err
        return httpx.Response(
            200,
            json=[
                {
                    "purpose": "bot",
                    "primary_model": "demo-replay-v1",
                    "fallback_model": "demo-replay-fallback-v1",
                    "max_tokens": 2048,
                    "timeout_s": 20,
                    "etag": '"mcfg_bot:v1"',
                },
                {
                    "purpose": "brief",
                    "primary_model": "demo-replay-v1",
                    "fallback_model": "demo-replay-fallback-v1",
                    "max_tokens": 1024,
                    "timeout_s": 10,
                    "etag": '"mcfg_brief:v1"',
                },
            ],
        )

    def _handle_session(
        self, request: httpx.Request, job_id: str, body: dict[str, Any]
    ) -> httpx.Response:
        err = self._check_service_auth(request)
        if err is not None:
            return err
        req = OpenJobSessionRequest.model_validate(body)
        lease_err = self._check_lease(job_id, req.worker_id, req.attempt)
        if lease_err is not None:
            return lease_err
        if self.fail_open_session_503_remaining > 0:
            self.fail_open_session_503_remaining -= 1
            return self._problem(503, "UPSTREAM_UNAVAILABLE", "Temporary 503 on open_session")

        fix = self._jobs[job_id]
        skipped_ids = {s.bot_id for s in fix.skipped}

        if fix.active_bot_ids is not None:
            bot_ids = list(fix.active_bot_ids)
        else:
            bot_ids = [
                bot_id
                for bot_id, plug in sorted(self._plugins.items())
                if fix.invoice_type in plug.manifest.triggers.invoice_types
                and bot_id not in skipped_ids
            ]

        if fix.required_bot_ids is not None:
            required_ids = list(fix.required_bot_ids)
        else:
            required_ids = [
                bot_id
                for bot_id, plug in sorted(self._plugins.items())
                if plug.manifest.required_for and fix.invoice_type in plug.manifest.required_for
            ]

        exp = datetime(2026, 11, 26, 8, 30, 0, tzinfo=timezone.utc)
        sup_tool_ids = [t.tool_id for t in fix.supervisor_tools]
        sup_tok = self._next_token("supervisor", job_id, req.attempt, sup_tool_ids)

        bot_grants: list[BotSessionGrant] = []
        for bid in bot_ids:
            plug = self._plugins[bid]
            granted_tools = fix.bot_token_tools_override.get(bid, list(plug.manifest.tools))
            btok = self._next_token(bid, job_id, req.attempt, granted_tools)
            prefetch_list = list(plug.skill.prefetch)
            self._required_prefetch[(job_id, bid)] = prefetch_list
            bot_grants.append(
                BotSessionGrant(
                    bot_id=bid,
                    bot_version=1,
                    description=plug.manifest.description,
                    manifest=plug.manifest,
                    skills=[
                        BotSkillContent(
                            skill_id=plug.skill.skill_id,
                            version=plug.skill.version,
                            content_md=plug.skill.content_md,
                        )
                    ],
                    prefetch=prefetch_list,
                    capability_token=btok,
                    token_exp=exp,
                )
            )

        session = JobSessionResponse(
            budget=SessionBudget(seconds=fix.budget_seconds, max_steps=fix.budget_max_steps),
            supervisor=SupervisorSessionGrant(
                capability_token=sup_tok,
                token_exp=exp,
                tools=list(fix.supervisor_tools),
            ),
            bots=bot_grants,
            required_bot_ids=required_ids,
            skipped=list(fix.skipped),
            context=InvestigateSessionContext(
                invoice_id=fix.invoice_id,
                invoice_type=fix.invoice_type,
            ),
        )
        return httpx.Response(200, json=session.model_dump(mode="json"))

    def _handle_heartbeat(
        self, request: httpx.Request, job_id: str, body: dict[str, Any]
    ) -> httpx.Response:
        err = self._check_service_auth(request)
        if err is not None:
            return err
        req = JobHeartbeatRequest.model_validate(body)
        lease_err = self._check_lease(job_id, req.worker_id, req.attempt)
        if lease_err is not None:
            return lease_err
        self.heartbeats.append(req)
        if self.fail_heartbeat_503_remaining > 0:
            self.fail_heartbeat_503_remaining -= 1
            return self._problem(503, "UPSTREAM_UNAVAILABLE", "Temporary 503 on heartbeat")
        if (
            self.revoke_lease_after_heartbeats is not None
            and len(self.heartbeats) >= self.revoke_lease_after_heartbeats
        ):
            self.revoke_lease(job_id)
            return self._problem(409, "LEASE_LOST", "Lease revoked on heartbeat")

        exp = datetime(2026, 11, 26, 8, 35, 0, tzinfo=timezone.utc)
        holders: dict[str, list[str]] = {}
        for rec in list(self._tokens.values()):
            if rec.job_id == job_id and rec.attempt == req.attempt:
                holders[rec.holder] = rec.tools
        renewed = [
            RenewedCapabilityToken(
                holder=h,
                capability_token=self._next_token(h, job_id, req.attempt, tools),
                token_exp=exp,
            )
            for h, tools in sorted(holders.items())
        ]
        return httpx.Response(
            200,
            json={
                "lease_expires_at": exp.isoformat(),
                "tokens": [r.model_dump(mode="json") for r in renewed],
            },
        )

    def _handle_progress(
        self, request: httpx.Request, job_id: str, body: dict[str, Any]
    ) -> httpx.Response:
        err = self._check_service_auth(request)
        if err is not None:
            return err
        req = JobProgressRequest.model_validate(body)
        lease_err = self._check_lease(job_id, req.worker_id, req.attempt)
        if lease_err is not None:
            return lease_err
        self.progress_events.extend(req.events)
        return httpx.Response(204)

    def _handle_list_tools(self, request: httpx.Request) -> httpx.Response:
        rec = self._check_capability_auth(request)
        if isinstance(rec, httpx.Response):
            return rec
        fix = self._jobs[rec.job_id]
        defs = [
            ToolDefinition(
                tool_id=tid,
                description=f"Tool {tid}",
                input_schema={"type": "object", "properties": {}},
                output_schema={"type": "object", "properties": {}},
                default_provenance=fix.tool_provenance.get(tid, Provenance.trusted),
                scope="tenant",
            ).model_dump(mode="json")
            for tid in rec.tools
        ]
        return httpx.Response(200, json=defs)

    async def _handle_invoke_tool(
        self, request: httpx.Request, tool_id: str, body: dict[str, Any]
    ) -> httpx.Response:
        rec = self._check_capability_auth(request)
        if isinstance(rec, httpx.Response):
            return rec
        if self.fail_tool_on_409_lease_lost:
            self.revoke_lease(rec.job_id)
            return self._problem(409, "LEASE_LOST", "Lease lost during tool invoke")

        fix = self._jobs[rec.job_id]
        delay = fix.tool_delay_s.get(tool_id, 0.0)
        if delay > 0:
            await asyncio.sleep(delay)

        raw_tok = request.headers["authorization"][len("Bearer ") :]
        self.tool_invocations.append((rec.holder, tool_id, body.get("input", {}), raw_tok))

        if tool_id not in rec.tools or tool_id in fix.invoke_tool_403_tools:
            return self._problem(
                403,
                "TOOL_NOT_GRANTED",
                f"Tool '{tool_id}' is not granted to holder '{rec.holder}'",
            )
        if tool_id in fix.kill_switched_tools:
            return self._problem(423, "KILL_SWITCH_ACTIVE", f"Kill switch active for {tool_id}")
        if fix.transient_500_tools.get(tool_id, 0) > 0:
            fix.transient_500_tools[tool_id] -= 1
            return self._problem(503, "UPSTREAM_UNAVAILABLE", "Transient 503")

        seq_key = (rec.job_id, rec.holder, tool_id)
        call_num = self._per_holder_tool_seq.get(seq_key, 0) + 1
        self._per_holder_tool_seq[seq_key] = call_num
        tcl_id = make_deterministic_ulid("tcl", f"{rec.job_id}:{rec.holder}:{tool_id}:{call_num}")
        prov = fix.tool_provenance.get(
            tool_id,
            Provenance.untrusted if tool_id in {"invoices", "inbox", "chat_messages"} else Provenance.trusted,
        )

        # Record tool call for prefetch & evidence ownership enforcement
        self._called_tools_by_holder.setdefault((rec.job_id, rec.attempt, rec.holder), set()).add(tool_id)

        if tool_id in fix.tool_errors:
            code, detail = fix.tool_errors[tool_id]
            self._server_tool_calls[tcl_id] = RecordedServerToolCall(
                job_id=rec.job_id,
                attempt=rec.attempt,
                holder=rec.holder,
                tool_id=tool_id,
                tool_call_id=tcl_id,
                serialized_data="{}",
            )
            return httpx.Response(
                200,
                json={
                    "data": {},
                    "provenance": prov.value,
                    "evidence_ref": tcl_id,
                    "error": {"code": code, "detail": detail},
                },
            )
        data = fix.tool_outputs.get(tool_id, {})
        self._server_tool_calls[tcl_id] = RecordedServerToolCall(
            job_id=rec.job_id,
            attempt=rec.attempt,
            holder=rec.holder,
            tool_id=tool_id,
            tool_call_id=tcl_id,
            serialized_data=json.dumps(data, ensure_ascii=False),
        )
        return httpx.Response(
            200,
            json={
                "data": data,
                "provenance": prov.value,
                "evidence_ref": tcl_id,
                "error": None,
            },
        )

    def _handle_submit_finding(
        self, request: httpx.Request, job_id: str, body: dict[str, Any]
    ) -> httpx.Response:
        rec = self._check_capability_auth(request)
        if isinstance(rec, httpx.Response):
            return rec
        if rec.job_id != job_id:
            return self._problem(403, "FORBIDDEN", "Token job_id mismatch")
        sub = FindingSubmission.model_validate(body)
        if sub.bot_id != rec.holder:
            return self._problem(403, "FORBIDDEN", "bot_id does not match capability token sub")

        rc_list = [ReasonCode(c.value) for c in sub.reason_codes]

        # Enforce evidence ownership like core (core-internal.yaml §submitFinding):
        # every evidence[].tool_call_id must belong to (job_id, attempt, bot_id), and
        # ref_id must equal tool_call_id (for kind=tool_call) or appear in that tool_call's output.
        for ev in sub.evidence:
            call_rec = self._server_tool_calls.get(ev.tool_call_id)
            if call_rec is None:
                return self._problem(
                    400,
                    "VALIDATION_FAILED",
                    f"Unknown evidence tool_call_id={ev.tool_call_id}",
                )
            if (call_rec.job_id, call_rec.attempt, call_rec.holder) != (
                job_id,
                rec.attempt,
                rec.holder,
            ):
                return self._problem(
                    400,
                    "VALIDATION_FAILED",
                    f"Evidence tool_call_id={ev.tool_call_id} not owned by ({job_id}, {rec.attempt}, {rec.holder})",
                )
            if ev.kind.value == "tool_call":
                if ev.ref_id != ev.tool_call_id:
                    return self._problem(
                        400,
                        "VALIDATION_FAILED",
                        f"tool_call evidence ref_id={ev.ref_id} must match tool_call_id={ev.tool_call_id}",
                    )
            elif ev.ref_id not in call_rec.serialized_data:
                return self._problem(
                    400,
                    "VALIDATION_FAILED",
                    f"Evidence ref_id={ev.ref_id} not found in output of {ev.tool_call_id}",
                )

        # Enforce prefetch completion per contract 1f69ce8:
        # Exempt ONLY when reason_codes <= {BOT_TIMEOUT, BOT_INVALID_OUTPUT} AND evidence == [].
        is_fail_closed_exempt = (
            set(rc_list) <= _PREFETCH_EXEMPT_CODES and len(sub.evidence) == 0
        )
        if not is_fail_closed_exempt:
            required = set(self._required_prefetch.get((job_id, rec.holder), []))
            called = self._called_tools_by_holder.get((job_id, rec.attempt, rec.holder), set())
            missing = sorted(required - called)
            if missing:
                return self._problem(
                    400,
                    "VALIDATION_FAILED",
                    f"Missing required prefetch tool(s) for {rec.holder}: {missing}",
                )

        self.submitted_findings.setdefault(job_id, []).append(sub)
        fnd_id = make_deterministic_ulid("fnd", f"{job_id}:{sub.bot_id}")
        sev = apply_finding_floor(Severity(sub.severity_reported.value), rc_list)
        ev_list = [
            EvidenceRef(
                kind=Kind1(e.kind.value),
                ref_id=e.ref_id,
                tool_call_id=e.tool_call_id,
            )
            for e in sub.evidence
        ]
        # FindingForSupervisor strictly omits `reason`!
        sup_finding = FindingForSupervisor(
            finding_id=fnd_id,
            bot_id=sub.bot_id,
            severity=sev,
            reason_codes=rc_list,
            evidence=ev_list,
        )
        stored = self.stored_findings_for_sup.setdefault(job_id, [])
        stored[:] = [f for f in stored if f.bot_id != sub.bot_id]
        stored.append(sup_finding)
        return httpx.Response(201, json=sup_finding.model_dump(mode="json"))

    def _handle_complete(
        self, request: httpx.Request, job_id: str, body: dict[str, Any]
    ) -> httpx.Response:
        err = self._check_service_auth(request)
        if err is not None:
            return err
        req = CompleteJobRequest.model_validate(body)
        lease_err = self._check_lease(job_id, req.worker_id, req.attempt)
        if lease_err is not None:
            return lease_err

        fix = self._jobs[job_id]
        if fix.task_type in (TaskType.question, TaskType.report):
            self.completed_jobs[job_id] = {
                "raw_body": body,
                "request": req,
                "status": "completed",
            }
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "message_id": make_ulid("cmg", 9001),
                    "unverified_values": [],
                },
            )

        stored = list(self.stored_findings_for_sup.get(job_id, []))
        ran_bots = {f.bot_id for f in stored}
        skipped_ids = {s.bot_id for s in fix.skipped}

        if fix.required_bot_ids is not None:
            required_ids = list(fix.required_bot_ids)
        else:
            required_ids = [
                bot_id
                for bot_id, plug in sorted(self._plugins.items())
                if plug.manifest.required_for and fix.invoice_type in plug.manifest.required_for
            ]

        for req_bot in required_ids:
            if req_bot not in ran_bots:
                self._fnd_seq += 1
                rc = ReasonCode.BOT_DISABLED if req_bot in skipped_ids else ReasonCode.BOT_NOT_RUN
                stored.append(
                    FindingForSupervisor(
                        finding_id=make_ulid("fnd", self._fnd_seq),
                        bot_id=req_bot,
                        severity=Severity.yellow,
                        reason_codes=[rc],
                        evidence=[],
                    )
                )

        self.stored_findings_for_sup[job_id] = stored
        final_sev = compute_final_severity(stored)
        inv_status = {
            Severity.green: "auto_pay_eligible",
            Severity.yellow: "pending_approval",
            Severity.red: "blocked",
        }[final_sev]

        all_reason_codes: list[ReasonCode] = []
        for f in stored:
            for c in f.reason_codes:
                if c != ReasonCode.OK and c not in all_reason_codes:
                    all_reason_codes.append(c)
        if not all_reason_codes:
            all_reason_codes = [ReasonCode.OK]

        self.completed_jobs[job_id] = {
            "raw_body": body,
            "request": req,
            "findings": stored,
            "final_severity": final_sev,
            "invoice_status": inv_status,
            "reason_codes": all_reason_codes,
        }
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "final_severity": final_sev.value,
                "invoice_status": inv_status,
            },
        )

    def _handle_fail(
        self, request: httpx.Request, job_id: str, body: dict[str, Any]
    ) -> httpx.Response:
        err = self._check_service_auth(request)
        if err is not None:
            return err
        req = FailJobRequest.model_validate(body)
        lease_err = self._check_lease(job_id, req.worker_id, req.attempt)
        if lease_err is not None:
            return lease_err
        self.failed_jobs.setdefault(job_id, []).append(req)
        return httpx.Response(200, json={"will_retry": req.attempt < 2})
