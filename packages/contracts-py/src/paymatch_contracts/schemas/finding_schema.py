# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import (
    channel_schema,
    evidence_ref_schema,
    local_date_schema,
    provenance_schema,
    reason_code_schema,
    severity_schema,
    timestamp_schema,
    untrusted_text_schema,
)


class Finding(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    finding_id: Annotated[str, Field(pattern='^fnd_[0-9A-HJKMNP-TV-Z]{26}$')]
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    attempt: Annotated[int, Field(ge=1)]
    bot_id: str
    bot_version: Annotated[int, Field(ge=1)]
    skill_version: Annotated[int, Field(ge=1)]
    prompt_hash: str
    severity: severity_schema.Severity
    severity_reported: severity_schema.Severity
    reason_codes: Annotated[list[reason_code_schema.ReasonCode], Field(min_length=1)]
    reason: untrusted_text_schema.UntrustedText
    evidence: list[evidence_ref_schema.EvidenceRef]
    provenance: provenance_schema.Provenance
    proposed_channel: channel_schema.Channel | None
    proposed_pay_on: local_date_schema.LocalDate | None
    created_at: timestamp_schema.Timestamp
