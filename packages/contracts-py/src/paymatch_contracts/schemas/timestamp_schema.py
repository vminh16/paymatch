# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import AwareDatetime, Field

type Timestamp = Annotated[
    AwareDatetime,
    Field(
        description='Thời điểm RFC 3339 có múi giờ (ví dụ 2026-11-26T09:15:00+07:00).',
        title='Timestamp',
    ),
]
