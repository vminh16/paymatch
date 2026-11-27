# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import (
    approval_created_schema,
    cross_alert_published_schema,
    invoice_status_changed_schema,
    job_completed_schema,
)


class Type(StrEnum):
    supervisor_step = 'supervisor.step'
    bot_started = 'bot.started'
    bot_tool_called = 'bot.tool_called'
    bot_finished = 'bot.finished'
    bot_failed = 'bot.failed'
    answer_delta = 'answer.delta'


class JobProgressedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    task_type: job_completed_schema.TaskType
    attempt: Annotated[int, Field(ge=1)]
    type: Type
    step: Annotated[int | None, Field(ge=1)] = None
    bot_id: str | None = None
    tool_id: str | None = None
    severity: invoice_status_changed_schema.Severity | None = None
    reason_code: cross_alert_published_schema.ReasonCode | None = None
    text_delta: Annotated[
        str | None,
        Field(
            description="Chỉ được phép (và bắt buộc dạng chuỗi) khi type = 'answer.delta'."
        ),
    ] = None
    at: approval_created_schema.Timestamp


class JobProgressedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['job.progressed']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[JobProgressedData, Field(title='JobProgressedData')]
