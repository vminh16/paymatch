# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import (
    approval_created_schema,
    cross_alert_published_schema,
    invoice_status_changed_schema,
)


class TaskType(StrEnum):
    investigate_invoice = 'investigate_invoice'
    question = 'question'
    report = 'report'


class JobCompletedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    task_type: TaskType
    invoice_id: Annotated[str | None, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )
    final_severity: invoice_status_changed_schema.Severity | None = None
    reason_codes: list[cross_alert_published_schema.ReasonCode] | None = None


class JobCompletedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['job.completed']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[JobCompletedData, Field(title='JobCompletedData')]
