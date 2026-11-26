# generated — do not edit

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

type Tool = Annotated[str, Field(pattern='^[a-z][a-z0-9_]*$')]


type StoreId = Annotated[str, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]


class CapabilityTokenClaims(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    iss: Literal['core']
    aud: Literal['internal-api']
    sub: Annotated[
        str,
        Field(
            description="'supervisor' cho điều phối chief-accountant hoặc '<bot_id>' cho bot chuyên môn.",
            min_length=1,
        ),
    ]
    tenant_id: Annotated[str, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    invoice_id: Annotated[
        str | None,
        Field(
            description='Null đối với job question hoặc report không gắn hóa đơn.',
            pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$',
        ),
    ]
    attempt: Annotated[int, Field(ge=1)]
    worker_id: Annotated[str, Field(min_length=1)]
    bot_version: Annotated[
        int | None, Field(description="Null khi sub = 'supervisor'.", ge=1)
    ]
    tools: list[Tool]
    store_ids: Annotated[
        list[StoreId] | None,
        Field(
            description='Giới hạn danh sách quán cho hội thoại/báo cáo của store_manager.'
        ),
    ] = None
    exp: Annotated[int, Field(ge=0)]
    jti: Annotated[str, Field(min_length=1)]
