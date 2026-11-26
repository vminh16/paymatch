"""Pure safety rules, prompt framing, provenance blocks, and fallback builders."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
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

_DELIMITER_TAG_RE = re.compile(
    r"</?(?:tool_result|untrusted_data|system_instruction|system|assistant)\b[^>]*>",
    flags=re.IGNORECASE,
)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", flags=re.DOTALL)


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


def build_finding_submission(
    *,
    bot_id: str,
    bot_version: int,
    skill_version: int,
    prompt_hash: str,
    output: BotFindingOutput,
    tool_calls: Sequence[RecordedToolCall],
) -> FindingSubmission:
    """Convert validated BotFindingOutput into contract FindingSubmission with safety floors."""
    guarded = enforce_error_yellow_floor(output, tool_calls)
    prov = effective_provenance(guarded.provenance, tool_calls)
    return FindingSubmission(
        bot_id=bot_id,
        bot_version=bot_version,
        skill_version=skill_version,
        prompt_hash=prompt_hash,
        severity_reported=SchemaSeverity(guarded.severity_reported.value),
        reason_codes=[SchemaReasonCode(rc.value) for rc in guarded.reason_codes],
        reason=guarded.reason[:1000],
        evidence=[_to_schema_evidence(ev) for ev in guarded.evidence],
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
) -> FindingSubmission:
    """Build a yellow FindingSubmission for BOT_TIMEOUT / BOT_INVALID_OUTPUT / runtime error."""
    evidence: list[SchemaEvidenceRef] = []
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
