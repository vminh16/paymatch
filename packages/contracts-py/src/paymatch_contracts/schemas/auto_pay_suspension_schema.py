# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import reason_code_schema, timestamp_schema


class AutoPaySuspension(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    vendor_id: Annotated[str, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    reason_codes: Annotated[list[reason_code_schema.ReasonCode], Field(min_length=1)]
    source_invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    suspended_at: timestamp_schema.Timestamp
    lifted_at: timestamp_schema.Timestamp | None
    lifted_by: Annotated[str | None, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')]
