# generated — do not edit

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    queued = 'queued'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
