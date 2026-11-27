# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import evidence_ref_schema, reason_code_schema, severity_schema


class FindingForSupervisor(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    finding_id: Annotated[str, Field(pattern='^fnd_[0-9A-HJKMNP-TV-Z]{26}$')]
    bot_id: Annotated[str, Field(min_length=1)]
    severity: severity_schema.Severity
    reason_codes: Annotated[list[reason_code_schema.ReasonCode], Field(min_length=1)]
    evidence: list[evidence_ref_schema.EvidenceRef]
