from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from auto_curso.constants import COMPLETION_THRESHOLD
from auto_curso.models.course import Course, CourseSummary
from auto_curso.models.progress import PlaybackProgress
from auto_curso.models.video import Video, VideoWithProgress
from auto_curso.repositories.course_repository import CourseRepository
from auto_curso.repositories.progress_repository import ProgressRepository
from auto_curso.services.folder_scanner import FolderScanner


class CourseService:
    def __init__(
        self,
        course_repo: CourseRepository | None = None,
        progress_repo: ProgressRepository | None = None,
        scanner: FolderScanner | None = None,
    ) -> None:
        self._courses = course_repo or CourseRepository()
        self._progress = progress_repo or ProgressRepository()
        self._scanner = scanner or FolderScanner()

    def add_course(self, folder_path: str) -> CourseSummary:
        normalized = str(Path(folder_path).resolve())
        if not os.path.isdir(normalized):
            raise FileNotFoundError(f"Pasta não encontrada: {normalized}")

        if self._courses.get_by_folder_path(normalized):
            raise ValueError("Esta pasta já está cadastrada como curso.")

        course = Course(
            id=uuid4(),
            name=Path(normalized).name,
            folder_path=normalized,
            added_at=datetime.now(timezone.utc),
        )
        self._courses.add(course)
        self._sync_videos(course)
        return self._build_summary(course)

    def refresh_course(self, course_id: UUID) -> CourseSummary:
        course = self._courses.get_by_id(course_id)
        if course is None:
            raise ValueError("Curso não encontrado.")
        if not os.path.isdir(course.folder_path):
            raise FileNotFoundError(f"Pasta do curso não encontrada: {course.folder_path}")
        self._sync_videos(course)
        return self._build_summary(course)

    def remove_course(self, course_id: UUID) -> None:
        self._courses.delete(course_id)

    def get_course_summaries(self) -> list[CourseSummary]:
        return [self._build_summary(c) for c in self._courses.get_all()]

    def get_course_summary(self, course_id: UUID) -> CourseSummary:
        course = self._courses.get_by_id(course_id)
        if course is None:
            raise ValueError("Curso não encontrado.")
        return self._build_summary(course)

    def set_video_completed(self, video_id: UUID, completed: bool) -> PlaybackProgress:
        existing = self._progress.get(video_id)
        now = datetime.now(timezone.utc)
        if completed:
            progress = PlaybackProgress(
                video_id=video_id,
                position_seconds=0.0,
                is_completed=True,
                watched_percent=100.0,
                last_watched_at=now,
            )
        elif existing:
            percent = existing.watched_percent
            position = existing.position_seconds
            threshold_pct = COMPLETION_THRESHOLD * 100
            below_pct = (COMPLETION_THRESHOLD - 0.01) * 100
            if percent >= threshold_pct:
                old_pct = max(percent, threshold_pct)
                percent = below_pct
                if position > 0:
                    position = position * (below_pct / old_pct)
            elif percent >= 100:
                percent = 99.0
            progress = PlaybackProgress(
                video_id=video_id,
                position_seconds=position,
                is_completed=False,
                watched_percent=percent,
                last_watched_at=now,
            )
        else:
            progress = PlaybackProgress(
                video_id=video_id,
                position_seconds=0.0,
                is_completed=False,
                watched_percent=0.0,
                last_watched_at=now,
            )
        self._progress.save(progress)
        return progress

    def save_progress(
        self, video_id: UUID, position_seconds: float, duration_seconds: float | None
    ) -> PlaybackProgress:
        video = self._courses.get_video(video_id)
        if video is None:
            raise ValueError("Vídeo não encontrado.")

        if duration_seconds and duration_seconds > 0 and video.duration_seconds is None:
            self._courses.update_video_duration(video_id, duration_seconds)

        effective_duration = duration_seconds or video.duration_seconds or 0.0
        if effective_duration > 0:
            percent = min(100.0, position_seconds / effective_duration * 100)
            is_completed = position_seconds / effective_duration >= COMPLETION_THRESHOLD
        else:
            percent = 0.0
            is_completed = False

        progress = PlaybackProgress(
            video_id=video_id,
            position_seconds=0.0 if is_completed else position_seconds,
            is_completed=is_completed,
            watched_percent=100.0 if is_completed else percent,
            last_watched_at=datetime.now(timezone.utc),
        )
        self._progress.save(progress)
        return progress

    def get_continue_watching(self) -> tuple[VideoWithProgress, Course] | None:
        progress = self._progress.get_most_recent_in_progress()
        if progress is None:
            return None
        video = self._courses.get_video(progress.video_id)
        if video is None:
            return None
        course = self._courses.get_by_id(video.course_id)
        if course is None:
            return None
        return (
            VideoWithProgress(video=video, progress=progress, course_folder_path=course.folder_path),
            course,
        )

    def get_videos_with_progress(self, course_id: UUID) -> list[VideoWithProgress]:
        course = self._courses.get_by_id(course_id)
        if course is None:
            raise ValueError("Curso não encontrado.")

        videos = self._courses.get_videos(course_id)
        progress_map = self._progress.get_for_course(course_id)
        return [
            VideoWithProgress(
                video=video,
                progress=progress_map.get(video.id),
                course_folder_path=course.folder_path,
            )
            for video in videos
        ]

    def _sync_videos(self, course: Course) -> None:
        scanned = self._scanner.scan(course.folder_path)
        videos = [
            Video(
                id=uuid4(),
                course_id=course.id,
                relative_path=file.relative_path,
                file_name=file.file_name,
                sort_order=index,
                file_size_bytes=file.file_size_bytes,
            )
            for index, file in enumerate(scanned)
        ]

        existing = {v.relative_path: v for v in self._courses.get_videos(course.id)}
        for video in videos:
            if old := existing.get(video.relative_path):
                video.id = old.id
                video.duration_seconds = old.duration_seconds

        self._courses.sync_videos(course.id, videos)
        self._progress.delete_orphans(course.id, [v.id for v in videos])

    def _build_summary(self, course: Course) -> CourseSummary:
        videos = self._courses.get_videos(course.id)
        completed = self._progress.get_completed_count(course.id)
        return CourseSummary(
            course=course,
            total_videos=len(videos),
            completed_videos=completed,
        )
