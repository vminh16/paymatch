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
)


class FindingSubmission(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    bot_id: Annotated[str, Field(min_length=1)]
    bot_version: Annotated[int, Field(ge=1)]
    skill_version: Annotated[int, Field(ge=1)]
    prompt_hash: Annotated[str, Field(min_length=1)]
    severity_reported: severity_schema.Severity
    reason_codes: Annotated[list[reason_code_schema.ReasonCode], Field(min_length=1)]
    reason: Annotated[
        str,
        Field(
            description='Giải thích tự do của bot (≤ 1000 ký tự); core bọc thành UntrustedText và không gửi cho điều phối.',
            max_length=1000,
        ),
    ]
    evidence: list[evidence_ref_schema.EvidenceRef]
    provenance: provenance_schema.Provenance
    proposed_channel: channel_schema.Channel | None = None
    proposed_pay_on: local_date_schema.LocalDate | None = None
