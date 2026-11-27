# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import Field

type SignedMoneyVnd = Annotated[
    int,
    Field(
        description='Số tiền VND có dấu (integer trong khoảng safe integer [-9007199254740991, 9007199254740991], đơn vị đồng; có thể âm trên hóa đơn điều chỉnh TCHDon 2/4).',
        ge=-9007199254740991,
        le=9007199254740991,
        title='SignedMoneyVnd',
    ),
]
