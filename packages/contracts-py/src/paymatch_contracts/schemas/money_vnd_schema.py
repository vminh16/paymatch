# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import Field

type MoneyVnd = Annotated[
    int,
    Field(
        description='Số tiền VND không âm (integer, đơn vị đồng).',
        ge=0,
        title='MoneyVnd',
    ),
]
