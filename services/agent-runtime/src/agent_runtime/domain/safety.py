"""Pure safety rules, prompt framing, provenance blocks, brief grounding, and fallback builders."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from decimal import Decimal as PyDecimal, InvalidOperation
from typing import Any

from paymatch_contracts.internal import (
    BriefSubmission,
    EvidenceRef,
    FindingForSupervisor,
    Kind1,
    Provenance,
    ReasonCode,
    Severity,
    ToolDefinition,
)
from paymatch_contracts.schemas.channel_schema import Channel as SchemaChannel
from paymatch_contracts.schemas.evidence_ref_schema import (
    EvidenceRef as SchemaEvidenceRef,
    Kind as SchemaEvidenceKind,
)
from paymatch_contracts.schemas.finding_submission_schema import FindingSubmission
from paymatch_contracts.schemas.provenance_schema import Provenance as SchemaProvenance
from paymatch_contracts.schemas.reason_code_schema import ReasonCode as SchemaReasonCode
from paymatch_contracts.schemas.severity_schema import Severity as SchemaSeverity

from .models import BotFindingOutput, RecordedToolCall, SupervisorBriefOutput

# Supervisor must NEVER hold tools returning untrusted seller/vendor free text
# (docs/03-agents/agent-runtime.md §4 #3, docs/05-api/internal-api.md §1).
SUPERVISOR_FORBIDDEN_TOOLS: frozenset[str] = frozenset(
    {"inbox", "chat_messages", "invoices"}
)

# Per-bot owned reason codes per docs/03-agents/agent-runtime.md §5a.
BOT_OWNED_REASON_CODES: dict[str, frozenset[ReasonCode]] = {
    "procurement": frozenset(
        {
            ReasonCode.OK,
            ReasonCode.PRICE_ABOVE_CONTRACT,
            ReasonCode.PACK_SIZE_CHANGED,
        }
    ),
    "accounts-payable": frozenset(
        {
            ReasonCode.OK,
            ReasonCode.QUANTITY_ABOVE_NORM,
            ReasonCode.NO_GOODS_RECEIPT,
            ReasonCode.DUPLICATE_INVOICE,
        }
    ),
    "fraud-control": frozenset(
        {
            ReasonCode.OK,
            ReasonCode.PAYEE_CHANGE_REQUEST,
            ReasonCode.PERSONAL_ACCOUNT,
            ReasonCode.HIDDEN_INSTRUCTION,
            ReasonCode.URGENCY_PRESSURE,
            ReasonCode.CROSS_ALERT_HIT,
            ReasonCode.OFFICIAL_FRAUD_LIST,
        }
    ),
    "tax": frozenset(
        {
            ReasonCode.OK,
            ReasonCode.TAX_RISK_LIST,
            ReasonCode.MST_INACTIVE,
            ReasonCode.INVOICE_NOT_FOUND_ON_PORTAL,
            ReasonCode.VAT_DEDUCTION_RISK,
        }
    ),
    "branch-operations": frozenset(
        {
            ReasonCode.OK,
            ReasonCode.UTILITY_OUT_OF_RANGE,
        }
    ),
    "treasury": frozenset(
        {
            ReasonCode.OK,
            ReasonCode.OVER_LIMIT,
            ReasonCode.LOW_BALANCE,
        }
    ),
}

# Red reason codes per docs/03-agents/agent-runtime.md §5a.
RED_REASON_CODES: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.DUPLICATE_INVOICE,
        ReasonCode.PAYEE_CHANGE_REQUEST,
        ReasonCode.PERSONAL_ACCOUNT,
        ReasonCode.HIDDEN_INSTRUCTION,
        ReasonCode.OFFICIAL_FRAUD_LIST,
        ReasonCode.TAX_RISK_LIST,
        ReasonCode.MST_INACTIVE,
        ReasonCode.INVOICE_NOT_FOUND_ON_PORTAL,
    }
)

# Valid backing tool_ids that can substantiate each red reason code.
RED_CODE_BACKING_TOOLS: dict[ReasonCode, frozenset[str]] = {
    ReasonCode.DUPLICATE_INVOICE: frozenset({"invoices", "payables_ledger"}),
    ReasonCode.PAYEE_CHANGE_REQUEST: frozenset(
        {"invoices", "inbox", "chat_messages", "vendor_registry"}
    ),
    ReasonCode.PERSONAL_ACCOUNT: frozenset(
        {"invoices", "inbox", "chat_messages", "vendor_registry"}
    ),
    ReasonCode.HIDDEN_INSTRUCTION: frozenset({"invoices", "inbox", "chat_messages"}),
    ReasonCode.OFFICIAL_FRAUD_LIST: frozenset({"official_fraud_list"}),
    ReasonCode.TAX_RISK_LIST: frozenset({"tax_risk_list", "einvoice_portal"}),
    ReasonCode.MST_INACTIVE: frozenset({"tax_id_lookup"}),
    ReasonCode.INVOICE_NOT_FOUND_ON_PORTAL: frozenset({"einvoice_portal"}),
}

_DELIMITER_TAG_RE = re.compile(
    r"</?(?:tool_result|untrusted_data|system_instruction|system|assistant)\b[^>]*>",
    flags=re.IGNORECASE,
)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", flags=re.DOTALL)

# Monetary amount patterns in Vietnamese/numeric briefs (e.g., "22.400.000 đ", "26,5 triệu", "30tr", "1000 VND")
_VND_EXPLICIT_RE = re.compile(
    r"(?<![A-Za-z0-9_])(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(?:đồng|vnđ|vnd|đ)(?![A-Za-zÀ-ỹ0-9_])",
    flags=re.IGNORECASE,
)
_VND_MILLION_RE = re.compile(
    r"(?<![A-Za-z0-9_])(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)(?![A-Za-zÀ-ỹ0-9_])",
    flags=re.IGNORECASE,
)
_VND_THOUSAND_RE = re.compile(
    r"(?<![A-Za-z0-9_])(\d+(?:[.,]\d+)?)\s*(?:nghìn|ngàn|k)(?=\s*(?:đ|vnd|vnđ|/|$|[\s,.;:)\]]))",
    flags=re.IGNORECASE,
)


def is_forbidden_supervisor_tool(tool_id: str, default_provenance: Provenance | None = None) -> bool:
    """Return True if a tool is forbidden for the supervisor."""
    if tool_id in SUPERVISOR_FORBIDDEN_TOOLS:
        return True
    if default_provenance == Provenance.untrusted:
        return True
    return False


def filter_supervisor_tools(tools: Sequence[ToolDefinition]) -> list[ToolDefinition]:
    """Defense-in-depth: strip any untrusted or forbidden tool from supervisor tool grants."""
    return [
        t
        for t in tools
        if not is_forbidden_supervisor_tool(t.tool_id, t.default_provenance)
    ]


def compute_prompt_hash(*parts: str) -> str:
    """Compute traceable sha256 prompt hash (prompts-and-skills.md §3)."""
    combined = "\n\n".join(part.strip() for part in parts if part)
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def escape_untrusted_delimiters(text: str) -> str:
    """Neutralize tag-escape spoofing inside data payloads while keeping text inspectable."""
    return _DELIMITER_TAG_RE.sub(lambda m: m.group(0).replace("<", "[TAG:").replace(">", "]"), text)


def format_tool_result_block(
    tool_id: str,
    provenance: Provenance | str,
    evidence_ref: str,
    payload: dict[str, Any],
) -> str:
    """Wrap tool output in a provenance-labelled data block (prompts-and-skills.md §1)."""
    prov = provenance.value if isinstance(provenance, Provenance) else str(provenance)
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    safe_body = escape_untrusted_delimiters(serialized)
    return (
        f'<tool_result tool_id="{tool_id}" provenance="{prov}" evidence_ref="{evidence_ref}">\n'
        f"{safe_body}\n"
        f"</tool_result>"
    )


def assemble_bot_system_prompt(
    safety_frame: str,
    bot_id: str,
    bot_name: str,
    bot_description: str,
    skill_mds: Sequence[str],
) -> str:
    """Assemble prompt in exact spec order: safety frame -> role -> skills (prompts-and-skills.md §1)."""
    role_block = (
        f"# Vai trò: {bot_name} (`{bot_id}`)\n"
        f"{bot_description.strip()}"
    )
    sections = [safety_frame.strip(), role_block]
    for md in skill_mds:
        cleaned = strip_yaml_frontmatter(md).strip()
        if cleaned:
            sections.append(cleaned)
    return "\n\n---\n\n".join(sections)


def strip_yaml_frontmatter(markdown: str) -> str:
    """Strip leading YAML frontmatter (`--- ... ---`) from a skill markdown file."""
    if not markdown.startswith("---"):
        return markdown
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return markdown
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "\n".join(lines[idx + 1 :]).lstrip("\n")
    return markdown


def parse_json_object(raw_text: str) -> dict[str, Any]:
    """Parse a JSON object from raw LLM text or a fenced ```json block."""
    text = raw_text.strip()
    if not text:
        raise ValueError("Empty LLM response")
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_FENCE_RE.search(text)
        if not match:
            raise ValueError(f"LLM response is not valid JSON: {text[:200]!r}") from None
        loaded = json.loads(match.group(1))
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected JSON object, got {type(loaded).__name__}")
    return loaded


def parse_bot_finding_output(raw_text: str) -> BotFindingOutput:
    """Strictly parse and validate specialist bot JSON output."""
    obj = parse_json_object(raw_text)
    return BotFindingOutput.model_validate(obj)


def parse_supervisor_brief_output(raw_text: str) -> SupervisorBriefOutput:
    """Strictly parse and validate supervisor brief JSON output."""
    obj = parse_json_object(raw_text)
    return SupervisorBriefOutput.model_validate(obj)


def sanitize_finding_for_supervisor(finding: FindingForSupervisor) -> dict[str, Any]:
    """Return ONLY the structured FindingForSupervisor fields (never `reason` or untrusted prose)."""
    return {
        "finding_id": finding.finding_id,
        "bot_id": finding.bot_id,
        "severity": finding.severity.value,
        "reason_codes": [code.value for code in finding.reason_codes],
        "evidence": [ev.model_dump(mode="json") for ev in finding.evidence],
    }


def effective_provenance(
    reported: Provenance,
    tool_calls: Sequence[RecordedToolCall],
) -> Provenance:
    """If any tool call returned untrusted data, Finding.provenance MUST be untrusted."""
    if reported == Provenance.untrusted:
        return Provenance.untrusted
    for call in tool_calls:
        if call.provenance == Provenance.untrusted:
            return Provenance.untrusted
    return Provenance.trusted


def enforce_error_yellow_floor(
    output: BotFindingOutput,
    tool_calls: Sequence[RecordedToolCall],
) -> BotFindingOutput:
    """Invariant #9: if any tool returned an error, bot output can NEVER be green."""
    errors = [c for c in tool_calls if c.error_code is not None]
    if not errors:
        return output
    severity = output.severity_reported
    reason_codes = list(output.reason_codes)
    reason = output.reason
    if severity == Severity.green:
        severity = Severity.yellow
    if reason_codes == [ReasonCode.OK]:
        reason_codes = [ReasonCode.CUSTOM]
    error_summary = "; ".join(f"{e.tool_id}:{e.error_code}" for e in errors)
    if error_summary not in reason:
        suffix = f" [Lỗi tool: {error_summary}]"
        reason = (reason[: max(0, 1000 - len(suffix))] + suffix)[:1000]
    return BotFindingOutput(
        severity_reported=severity,
        reason_codes=reason_codes,
        reason=reason,
        evidence=output.evidence,
        provenance=output.provenance,
        proposed_channel=output.proposed_channel,
        proposed_pay_on=output.proposed_pay_on,
    )


def _to_schema_evidence(ev: EvidenceRef) -> SchemaEvidenceRef:
    return SchemaEvidenceRef(
        kind=SchemaEvidenceKind(ev.kind.value),
        ref_id=ev.ref_id,
        tool_call_id=ev.tool_call_id,
    )


def _dedupe_codes(codes: Iterable[ReasonCode]) -> list[ReasonCode]:
    seen: set[ReasonCode] = set()
    out: list[ReasonCode] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def build_finding_submission(
    *,
    bot_id: str,
    bot_version: int,
    skill_version: int,
    prompt_hash: str,
    output: BotFindingOutput,
    tool_calls: Sequence[RecordedToolCall],
) -> FindingSubmission:
    """Convert validated BotFindingOutput into contract FindingSubmission with safety floors.

    Enforces:
    1. Drops reason codes the bot does not own (per docs/03-agents/agent-runtime.md §5a).
    2. Deterministic floor: positive `official_fraud_list` (`listed == true`) forces
       `OFFICIAL_FRAUD_LIST` (`red`) with cited `tool_call` evidence even if the LLM says OK.
    3. Keeps only evidence referencing real `tool_call_id`s from this bot's `tool_calls`.
    4. Requires valid backing evidence for every red reason code; drops unsubstantiated red codes.
    5. Fails closed to yellow `BOT_INVALID_OUTPUT` if dropping invalid codes leaves nothing valid.
    6. Enforces yellow floor whenever any tool call errored (including 403 / local denial).
    """
    guarded = enforce_error_yellow_floor(output, tool_calls)
    severity = guarded.severity_reported
    reason = guarded.reason

    # Map valid recorded tool_call_ids -> tool_id
    tcl_to_tool: dict[str, str] = {
        call.tool_call_id: call.tool_id
        for call in tool_calls
        if call.tool_call_id is not None
    }

    # Keep only evidence owned by this bot's recorded tool calls
    valid_evidence: list[EvidenceRef] = [
        ev for ev in guarded.evidence if ev.tool_call_id in tcl_to_tool
    ]

    # 1. Filter to reason codes owned by this bot (system bots per agent-runtime.md §5a)
    owned = BOT_OWNED_REASON_CODES.get(bot_id)
    original_codes = _dedupe_codes(guarded.reason_codes)
    dropped_any = False
    if owned is not None:
        # Allow CUSTOM only if introduced by enforce_error_yellow_floor for a tool error
        has_tool_error = any(c.error_code is not None for c in tool_calls)
        allowed = owned | ({ReasonCode.CUSTOM} if has_tool_error else set())
        kept_codes = [c for c in original_codes if c in allowed]
        if len(kept_codes) < len(original_codes):
            dropped_any = True
    else:
        kept_codes = list(original_codes)

    # 2. Deterministic floor: positive official_fraud_list forces OFFICIAL_FRAUD_LIST (red)
    for call in tool_calls:
        if (
            call.tool_id == "official_fraud_list"
            and call.error_code is None
            and call.data.get("listed") is True
            and call.tool_call_id is not None
        ):
            if ReasonCode.OFFICIAL_FRAUD_LIST not in kept_codes:
                kept_codes.append(ReasonCode.OFFICIAL_FRAUD_LIST)
            severity = Severity.red
            if not any(ev.tool_call_id == call.tool_call_id for ev in valid_evidence):
                valid_evidence.append(
                    EvidenceRef(
                        kind=Kind1.tool_call,
                        ref_id=call.tool_call_id,
                        tool_call_id=call.tool_call_id,
                    )
                )
            if "SIMO" not in reason and "official_fraud_list" not in reason:
                note = " [Xác nhận trùng danh sách gian lận chính thức SIMO (official_fraud_list).]"
                reason = (reason[: max(0, 1000 - len(note))] + note)[:1000]

    # 3. Require valid backing evidence for every red reason code
    verified_codes: list[ReasonCode] = []
    for rc in kept_codes:
        if rc in RED_REASON_CODES:
            backing_tools = RED_CODE_BACKING_TOOLS.get(rc)
            has_backing = any(
                (backing_tools is None or tcl_to_tool.get(ev.tool_call_id) in backing_tools)
                for ev in valid_evidence
            )
            if not has_backing:
                dropped_any = True
                continue
        verified_codes.append(rc)

    # Drop OK when non-OK codes are present
    non_ok = [c for c in verified_codes if c != ReasonCode.OK]
    if non_ok:
        verified_codes = non_ok

    # Fail closed if dropping unowned/unevidenced codes left nothing valid
    if not verified_codes:
        verified_codes = [ReasonCode.BOT_INVALID_OUTPUT]
        severity = Severity.yellow
        note = " [Mã lý do không hợp lệ hoặc thiếu bằng chứng hợp lệ cho mã đỏ.]"
        reason = (reason[: max(0, 1000 - len(note))] + note)[:1000]
    elif dropped_any and verified_codes == [ReasonCode.OK]:
        # Never downgrade an invalid non-OK claim to green/OK
        verified_codes = [ReasonCode.BOT_INVALID_OUTPUT]
        severity = Severity.yellow
        note = " [Đã loại mã lý do ngoài phạm vi hoặc thiếu bằng chứng.]"
        reason = (reason[: max(0, 1000 - len(note))] + note)[:1000]

    # Sync severity floor with surviving reason codes
    if any(c in RED_REASON_CODES for c in verified_codes):
        severity = Severity.red
    elif any(c != ReasonCode.OK for c in verified_codes) and severity == Severity.green:
        severity = Severity.yellow
    elif not any(c in RED_REASON_CODES for c in verified_codes) and severity == Severity.red:
        severity = Severity.yellow

    prov = effective_provenance(guarded.provenance, tool_calls)
    return FindingSubmission(
        bot_id=bot_id,
        bot_version=bot_version,
        skill_version=skill_version,
        prompt_hash=prompt_hash,
        severity_reported=SchemaSeverity(severity.value),
        reason_codes=[SchemaReasonCode(rc.value) for rc in verified_codes],
        reason=reason[:1000],
        evidence=[_to_schema_evidence(ev) for ev in valid_evidence],
        provenance=SchemaProvenance(prov.value),
        proposed_channel=(
            SchemaChannel(guarded.proposed_channel.value)
            if guarded.proposed_channel is not None
            else None
        ),
        proposed_pay_on=guarded.proposed_pay_on,
    )


def build_error_finding_submission(
    *,
    bot_id: str,
    bot_version: int,
    skill_version: int,
    prompt_hash: str,
    reason_code: ReasonCode,
    reason: str,
    tool_calls: Sequence[RecordedToolCall] = (),
    include_evidence: bool = True,
) -> FindingSubmission:
    """Build a yellow FindingSubmission for BOT_TIMEOUT / BOT_INVALID_OUTPUT / runtime error.

    When `include_evidence=False` (used when deadline hits before prefetch completes),
    submits `evidence=[]` so core exempts the fail-closed error Finding from the prefetch check.
    """
    evidence: list[SchemaEvidenceRef] = []
    if include_evidence:
        for call in tool_calls:
            if call.tool_call_id and call.tool_call_id.startswith("tcl_"):
                evidence.append(
                    SchemaEvidenceRef(
                        kind=SchemaEvidenceKind.tool_call,
                        ref_id=call.tool_call_id,
                        tool_call_id=call.tool_call_id,
                    )
                )
    prov = effective_provenance(Provenance.trusted, tool_calls)
    return FindingSubmission(
        bot_id=bot_id,
        bot_version=bot_version,
        skill_version=skill_version,
        prompt_hash=prompt_hash,
        severity_reported=SchemaSeverity.yellow,
        reason_codes=[SchemaReasonCode(reason_code.value)],
        reason=reason[:1000],
        evidence=evidence,
        provenance=SchemaProvenance(prov.value),
        proposed_channel=None,
        proposed_pay_on=None,
    )


def _parse_scaled_decimal(raw: str, multiplier: int) -> int | None:
    normalized = raw.replace(",", ".")
    try:
        val = PyDecimal(normalized) * multiplier
    except InvalidOperation:
        return None
    return int(val.to_integral_value())


def extract_monetary_amounts_vnd(text: str) -> list[int]:
    """Extract monetary VND amounts mentioned in a brief line."""
    amounts: list[int] = []
    for match in _VND_EXPLICIT_RE.finditer(text):
        digits = match.group(1).replace(".", "").replace(",", "")
        if digits.isdigit():
            amounts.append(int(digits))
    for match in _VND_MILLION_RE.finditer(text):
        parsed = _parse_scaled_decimal(match.group(1), 1_000_000)
        if parsed is not None:
            amounts.append(parsed)
    for match in _VND_THOUSAND_RE.finditer(text):
        parsed = _parse_scaled_decimal(match.group(1), 1_000)
        if parsed is not None:
            amounts.append(parsed)
    return amounts


def _walk_trusted_ints(obj: Any, out: set[int]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, int):
        out.add(abs(obj))
        out.add(obj)
        return
    if isinstance(obj, dict):
        # Never extract numbers from nested untrusted blocks
        if obj.get("provenance") == "untrusted":
            return
        for k, v in obj.items():
            if k == "untrusted":
                continue
            _walk_trusted_ints(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _walk_trusted_ints(item, out)


def collect_trusted_amounts_by_tool_call(
    tool_calls: Sequence[RecordedToolCall],
) -> dict[str, set[int]]:
    """Collect integer amounts from trusted, error-free supervisor tool calls keyed by tool_call_id."""
    by_tcl: dict[str, set[int]] = {}
    for call in tool_calls:
        if (
            call.provenance != Provenance.trusted
            or call.error_code is not None
            or call.tool_call_id is None
        ):
            continue
        nums: set[int] = set()
        _walk_trusted_ints(call.data, nums)
        by_tcl[call.tool_call_id] = nums
    return by_tcl


def validate_brief_grounding(
    brief: SupervisorBriefOutput,
    *,
    findings: Sequence[FindingForSupervisor],
    supervisor_tool_calls: Sequence[RecordedToolCall],
) -> SupervisorBriefOutput:
    """Verify every citation and monetary statement in chief-accountant's brief is grounded.

    - Every `cited_evidence[].tool_call_id` must exist in `findings[].evidence` or in a
      trusted, error-free supervisor tool call.
    - Every monetary VND statement in `brief.lines` must match an integer amount from a
      trusted supervisor tool call whose `tool_call_id` is explicitly cited in `brief.cited_evidence`.
    """
    finding_tcls = {ev.tool_call_id for f in findings for ev in f.evidence}
    trusted_amounts_by_tcl = collect_trusted_amounts_by_tool_call(supervisor_tool_calls)
    valid_tcls = finding_tcls | set(trusted_amounts_by_tcl.keys())

    for ev in brief.cited_evidence:
        if ev.tool_call_id not in valid_tcls:
            raise ValueError(f"Brief cites unknown or untrusted tool_call_id: {ev.tool_call_id}")

    cited_tcls = {ev.tool_call_id for ev in brief.cited_evidence}
    cited_trusted_amounts: set[int] = set()
    for tcl_id in cited_tcls:
        cited_trusted_amounts |= trusted_amounts_by_tcl.get(tcl_id, set())

    for line in brief.lines:
        for amt in extract_monetary_amounts_vnd(line):
            if amt not in cited_trusted_amounts:
                raise ValueError(
                    f"Brief contains uncited or conflicting monetary amount {amt} VND in line: {line!r}"
                )

    return brief


def build_fallback_brief(
    *,
    invoice_id: str,
    invoice_type: str,
    findings: Iterable[FindingForSupervisor],
    model: str,
    prompt_hash: str,
) -> BriefSubmission:
    """Build a deterministic ≤ 5-line Vietnamese brief strictly from FindingForSupervisor data."""
    finding_list = list(findings)
    lines: list[str] = [
        f"Kết quả kiểm tra hóa đơn {invoice_id} (loại {invoice_type}): đã nhận {len(finding_list)} báo cáo bot."[:200]
    ]
    cited: list[EvidenceRef] = []
    seen_ev: set[tuple[str, str, str]] = set()
    flagged_bots: list[str] = []

    for f in finding_list:
        codes = ", ".join(c.value for c in f.reason_codes)
        if f.severity != Severity.green or any(c != ReasonCode.OK for c in f.reason_codes):
            flagged_bots.append(f"{f.bot_id} ({f.severity.value}: {codes})")
        for ev in f.evidence:
            key = (ev.kind.value, ev.ref_id, ev.tool_call_id)
            if key not in seen_ev:
                seen_ev.add(key)
                cited.append(
                    EvidenceRef(
                        kind=Kind1(ev.kind.value),
                        ref_id=ev.ref_id,
                        tool_call_id=ev.tool_call_id,
                    )
                )

    if flagged_bots:
        for item in flagged_bots[:3]:
            lines.append(f"Cảnh báo từ {item}."[:200])
        lines.append("Đề xuất Chủ chuỗi xem xét chi tiết trước khi phê duyệt thanh toán."[:200])
    else:
        lines.append("Các bot đã chạy không ghi nhận bất thường."[:200])

    return BriefSubmission(
        lines=lines[:5],
        cited_evidence=cited,
        model=model,
        prompt_hash=prompt_hash,
    )
