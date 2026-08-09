from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class PlaybackProgress:
    """Progresso de reprodução salvo para um vídeo (posição, conclusão, percentual assistido)."""

    video_id: UUID
    position_seconds: float
    is_completed: bool
    watched_percent: float
    last_watched_at: datetime
