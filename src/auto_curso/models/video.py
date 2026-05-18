from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from auto_curso.models.progress import PlaybackProgress


@dataclass
class Video:
    id: UUID
    course_id: UUID
    relative_path: str
    file_name: str
    sort_order: int
    file_size_bytes: int
    duration_seconds: float | None = None


@dataclass
class ScannedVideoFile:
    relative_path: str
    file_name: str
    file_size_bytes: int


@dataclass
class VideoWithProgress:
    video: Video
    progress: PlaybackProgress | None
    course_folder_path: str

    @property
    def full_path(self) -> str:
        return str(Path(self.course_folder_path) / self.video.relative_path)

    @property
    def progress_percent(self) -> float:
        if self.progress and self.progress.is_completed:
            return 100.0
        return self.progress.watched_percent if self.progress else 0.0

    @property
    def is_completed(self) -> bool:
        return bool(self.progress and self.progress.is_completed)
