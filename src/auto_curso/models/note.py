from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class VideoNote:
    id: UUID
    video_id: UUID
    time_seconds: float
    text: str
    created_at: datetime
