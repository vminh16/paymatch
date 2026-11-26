# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import evidence_ref_schema, untrusted_text_schema


class Brief(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    brief_id: Annotated[str, Field(pattern='^brf_[0-9A-HJKMNP-TV-Z]{26}$')]
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    lines: Annotated[list[untrusted_text_schema.UntrustedText], Field(max_length=5)]
    cited_evidence: list[evidence_ref_schema.EvidenceRef]
    model: str
    prompt_hash: str
