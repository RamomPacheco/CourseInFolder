from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Course:
    id: UUID
    name: str
    folder_path: str
    added_at: datetime
    description: str | None = None
    cover_stored_name: str | None = None


@dataclass
class CourseSummary:
    course: Course
    total_videos: int
    completed_videos: int

    @property
    def progress_percent(self) -> float:
        if self.total_videos == 0:
            return 0.0
        return self.completed_videos / self.total_videos * 100
