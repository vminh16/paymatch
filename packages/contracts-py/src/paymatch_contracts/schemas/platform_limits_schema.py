# generated — do not edit

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from . import money_vnd_schema, timestamp_schema


class PlatformLimits(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    auto_pay_per_invoice_vnd: money_vnd_schema.MoneyVnd
    auto_pay_per_day_vnd: money_vnd_schema.MoneyVnd
    updated_at: timestamp_schema.Timestamp
