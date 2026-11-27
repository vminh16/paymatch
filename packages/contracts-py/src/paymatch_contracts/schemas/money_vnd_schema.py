# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import Field

type MoneyVnd = Annotated[
    int,
    Field(
        description='Số tiền VND không âm (integer trong khoảng safe integer [0, 9007199254740991], đơn vị đồng).',
        ge=0,
        le=9007199254740991,
        title='MoneyVnd',
    ),
]
