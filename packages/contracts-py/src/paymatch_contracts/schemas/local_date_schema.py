# generated — do not edit

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import Field

type LocalDate = Annotated[
    date,
    Field(
        description='Ngày theo giờ Việt Nam, định dạng YYYY-MM-DD.', title='LocalDate'
    ),
]
