from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from auto_curso.constants import (
    COMPLETION_THRESHOLD,
    MAX_UPLOAD_SIZE_BYTES,
    UPLOAD_EXTENSIONS,
    get_course_materials_dir,
    get_video_materials_dir,
)
from auto_curso.models.course import Course, CourseSummary
from auto_curso.models.material import UploadedMaterial
from auto_curso.models.note import VideoNote
from auto_curso.models.progress import PlaybackProgress
from auto_curso.models.video import ScannedVideoFile, Video, VideoWithProgress
from auto_curso.repositories.course_repository import CourseRepository
from auto_curso.repositories.materials_repository import MaterialsRepository
from auto_curso.repositories.notes_repository import NotesRepository
from auto_curso.repositories.progress_repository import ProgressRepository
from auto_curso.services.folder_scanner import FolderScanner


class CourseService:
    def __init__(
        self,
        course_repo: CourseRepository | None = None,
        progress_repo: ProgressRepository | None = None,
        scanner: FolderScanner | None = None,
        notes_repo: NotesRepository | None = None,
        uploads_repo: MaterialsRepository | None = None,
    ) -> None:
        self._courses = course_repo or CourseRepository()
        self._progress = progress_repo or ProgressRepository()
        self._scanner = scanner or FolderScanner()
        self._notes = notes_repo or NotesRepository()
        self._uploads = uploads_repo or MaterialsRepository()

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
        shutil.rmtree(get_course_materials_dir(course_id), ignore_errors=True)

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

        existing = self._progress.get(video_id)
        if existing and existing.is_completed:
            # Rewatching a finished video always starts at position 0, so a normal
            # autosave would otherwise recompute a tiny position/duration ratio and
            # un-complete it. Only the explicit toggle (set_video_completed) may do that.
            return existing

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

    def get_favorites(self, course_id: UUID) -> set[UUID]:
        return self._notes.get_favorites_for_course(course_id)

    def toggle_favorite(self, video_id: UUID) -> bool:
        return self._notes.toggle_favorite(video_id)

    def get_video_notes(self, video_id: UUID) -> list[VideoNote]:
        return self._notes.list_for_video(video_id)

    def add_video_note(self, video_id: UUID, time_seconds: float, text: str) -> VideoNote:
        return self._notes.add(video_id, time_seconds, text)

    def delete_video_note(self, note_id: UUID) -> None:
        self._notes.delete(note_id)

    def get_course_note(self, course_id: UUID) -> str:
        return self._notes.get_course_note(course_id)

    def save_course_note(self, course_id: UUID, text: str) -> None:
        self._notes.save_course_note(course_id, text)

    def get_materials(self, course_id: UUID) -> list[ScannedVideoFile]:
        course = self._courses.get_by_id(course_id)
        if course is None:
            raise ValueError("Curso não encontrado.")
        return self._scanner.scan_materials(course.folder_path)

    def list_video_materials(self, video_id: UUID) -> list[UploadedMaterial]:
        return self._uploads.list_for_video(video_id)

    def add_video_material(
        self, video_id: UUID, file_name: str, data: bytes, mime_type: str
    ) -> UploadedMaterial:
        video = self._courses.get_video(video_id)
        if video is None:
            raise ValueError("Vídeo não encontrado.")

        extension = Path(file_name).suffix.lower()
        if extension not in UPLOAD_EXTENSIONS:
            raise ValueError(
                f"Tipo de arquivo não suportado ({extension or 'sem extensão'}). "
                "Envie imagem, áudio ou PDF."
            )
        if len(data) > MAX_UPLOAD_SIZE_BYTES:
            raise ValueError("Arquivo muito grande (máximo 50 MB).")

        stored_name = f"{uuid4()}{extension}"
        target_dir = get_video_materials_dir(video.course_id, video_id)
        (target_dir / stored_name).write_bytes(data)

        return self._uploads.add(video_id, file_name, stored_name, mime_type, len(data))

    def delete_video_material(self, material_id: UUID) -> None:
        material = self._uploads.get(material_id)
        if material is None:
            return
        self._uploads.delete(material_id)
        video = self._courses.get_video(material.video_id)
        if video is not None:
            path = get_video_materials_dir(video.course_id, material.video_id) / material.stored_name
            path.unlink(missing_ok=True)

    def get_video_material_path(self, material_id: UUID) -> tuple[UploadedMaterial, Path] | None:
        material = self._uploads.get(material_id)
        if material is None:
            return None
        video = self._courses.get_video(material.video_id)
        if video is None:
            return None
        path = get_video_materials_dir(video.course_id, material.video_id) / material.stored_name
        return material, path

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
