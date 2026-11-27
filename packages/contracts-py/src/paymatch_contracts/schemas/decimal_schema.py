# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import Field

type Decimal = Annotated[
    str,
    Field(
        description='Chuỗi thập phân tối đa 6 chữ số sau dấu chấm (số lượng, đơn giá, tỷ lệ theo QĐ 1233).',
        pattern='^-?\\d{1,15}(\\.\\d{1,6})?$',
        title='Decimal',
    ),
]
