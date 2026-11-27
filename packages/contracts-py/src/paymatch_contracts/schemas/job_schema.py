# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import job_status_schema, severity_schema, task_type_schema, timestamp_schema


class InvoiceJobSubject(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]


class QuestionJobSubject(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    conversation_id: Annotated[str, Field(pattern='^cnv_[0-9A-HJKMNP-TV-Z]{26}$')]
    message_id: Annotated[str, Field(pattern='^cmg_[0-9A-HJKMNP-TV-Z]{26}$')]


class ReportJobSubject(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    report_id: Annotated[str, Field(pattern='^rpt_[0-9A-HJKMNP-TV-Z]{26}$')]


class BotCallSummary(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    bot_id: str
    bot_version: Annotated[int, Field(ge=1)]
    times: Annotated[int, Field(ge=1)]


class State(StrEnum):
    pending = 'pending'
    running = 'running'
    done = 'done'
    failed = 'failed'
    timeout = 'timeout'


class BotState(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    bot_id: str
    state: State
    severity: severity_schema.Severity | None


class Job(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    task_type: task_type_schema.TaskType
    tenant_id: Annotated[str, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    subject: InvoiceJobSubject | QuestionJobSubject | ReportJobSubject
    status: job_status_schema.JobStatus
    attempt: Annotated[int, Field(ge=1)]
    bots_called: list[BotCallSummary]
    bot_states: list[BotState]
    created_at: timestamp_schema.Timestamp
    started_at: timestamp_schema.Timestamp | None
    completed_at: timestamp_schema.Timestamp | None
