from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class UploadedMaterial:
    id: UUID
    video_id: UUID
    file_name: str
    stored_name: str
    mime_type: str
    size_bytes: int
    uploaded_at: datetime
