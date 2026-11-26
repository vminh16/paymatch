# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import Field

type SignedMoneyVnd = Annotated[
    int,
    Field(
        description='Số tiền VND có dấu (integer, đơn vị đồng; có thể âm trên hóa đơn điều chỉnh TCHDon 2/4).',
        title='SignedMoneyVnd',
    ),
]
