from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from auto_curso.constants import get_manual_video_dir
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
    display_title: str | None = None
    is_manual: bool = False
    manual_stored_name: str | None = None

    @property
    def display_name(self) -> str:
        return self.display_title or self.file_name


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
        if self.video.is_manual:
            return str(get_manual_video_dir(self.video.course_id, self.video.id) / self.video.manual_stored_name)
        return str(Path(self.course_folder_path) / self.video.relative_path)

    @property
    def progress_percent(self) -> float:
        if self.progress and self.progress.is_completed:
            return 100.0
        return self.progress.watched_percent if self.progress else 0.0

    @property
    def is_completed(self) -> bool:
        return bool(self.progress and self.progress.is_completed)
