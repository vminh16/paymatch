# generated — do not edit

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

type Tool = Annotated[str, Field(pattern='^[a-z][a-z0-9_]*$')]


type StoreId = Annotated[str, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]


class SupervisorCapabilityTokenConstraints(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    iss: Literal['core']
    aud: Literal['internal-api']
    sub: Annotated[
        Literal['supervisor'],
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
        None,
        Field(
            description="Bắt buộc null khi sub = 'supervisor'; bắt buộc integer >= 1 khi sub là '<bot_id>'."
        ),
    ]
    tools: Annotated[
        list[Tool],
        Field(
            description='Danh sách tool được cấp. Token supervisor không bao giờ chứa tool untrusted (inbox, chat_messages, invoices).'
        ),
    ]
    store_ids: Annotated[
        list[StoreId] | None,
        Field(
            description='Giới hạn danh sách quán cho hội thoại/báo cáo của store_manager.'
        ),
    ] = None
    iat: Annotated[
        int | None,
        Field(
            description='Thời điểm phát hành (Unix epoch giây); bắt buộc exp - iat <= 120.',
            ge=0,
        ),
    ] = None
    exp: Annotated[
        int,
        Field(
            description='Thời điểm hết hạn (Unix epoch giây); tối đa 120 s kể từ iat (exp - iat <= 120 và exp <= now + 120 s).',
            ge=0,
        ),
    ]
    jti: Annotated[str, Field(min_length=1)]


class BotCapabilityTokenConstraints(BaseModel):
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
        int,
        Field(
            description="Bắt buộc null khi sub = 'supervisor'; bắt buộc integer >= 1 khi sub là '<bot_id>'.",
            ge=1,
        ),
    ]
    tools: Annotated[
        list[Tool],
        Field(
            description='Danh sách tool được cấp. Token supervisor không bao giờ chứa tool untrusted (inbox, chat_messages, invoices).'
        ),
    ]
    store_ids: Annotated[
        list[StoreId] | None,
        Field(
            description='Giới hạn danh sách quán cho hội thoại/báo cáo của store_manager.'
        ),
    ] = None
    iat: Annotated[
        int | None,
        Field(
            description='Thời điểm phát hành (Unix epoch giây); bắt buộc exp - iat <= 120.',
            ge=0,
        ),
    ] = None
    exp: Annotated[
        int,
        Field(
            description='Thời điểm hết hạn (Unix epoch giây); tối đa 120 s kể từ iat (exp - iat <= 120 và exp <= now + 120 s).',
            ge=0,
        ),
    ]
    jti: Annotated[str, Field(min_length=1)]


type CapabilityTokenClaims = Annotated[
    SupervisorCapabilityTokenConstraints | BotCapabilityTokenConstraints,
    Field(
        description='Claims của capability JWT (EdDSA) do core ký cho điều phối (supervisor) hoặc một bot trong một attempt của job. Thời hạn tối đa 120 s (exp - iat <= 120).',
        title='CapabilityTokenClaims',
    ),
]
