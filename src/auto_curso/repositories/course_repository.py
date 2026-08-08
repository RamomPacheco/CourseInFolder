from __future__ import annotations

from datetime import datetime
from uuid import UUID

from auto_curso.db.connection import get_connection
from auto_curso.models.course import Course
from auto_curso.models.video import Video


class CourseRepository:
    def get_all(self) -> list[Course]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT Id, Name, FolderPath, AddedAt FROM Courses ORDER BY AddedAt DESC"
            ).fetchall()
        return [_read_course(r) for r in rows]

    def get_by_id(self, course_id: UUID) -> Course | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT Id, Name, FolderPath, AddedAt FROM Courses WHERE Id = ?",
                (str(course_id),),
            ).fetchone()
        return _read_course(row) if row else None

    def get_by_folder_path(self, folder_path: str) -> Course | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT Id, Name, FolderPath, AddedAt FROM Courses WHERE FolderPath = ?",
                (folder_path,),
            ).fetchone()
        return _read_course(row) if row else None

    def add(self, course: Course) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO Courses (Id, Name, FolderPath, AddedAt) VALUES (?, ?, ?, ?)",
                (
                    str(course.id),
                    course.name,
                    course.folder_path,
                    course.added_at.isoformat(),
                ),
            )

    def delete(self, course_id: UUID) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM Courses WHERE Id = ?", (str(course_id),))

    def get_videos(self, course_id: UUID) -> list[Video]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT Id, CourseId, RelativePath, FileName, SortOrder, FileSizeBytes, DurationSeconds
                FROM Videos WHERE CourseId = ? ORDER BY SortOrder
                """,
                (str(course_id),),
            ).fetchall()
        return [_read_video(r) for r in rows]

    def sync_videos(self, course_id: UUID, videos: list[Video]) -> None:
        with get_connection() as conn:
            existing = {
                r[0]
                for r in conn.execute(
                    "SELECT RelativePath FROM Videos WHERE CourseId = ?",
                    (str(course_id),),
                ).fetchall()
            }
            new_paths = {v.relative_path for v in videos}
            for path in existing - new_paths:
                conn.execute(
                    "DELETE FROM Videos WHERE CourseId = ? AND RelativePath = ?",
                    (str(course_id), path),
                )
            for video in videos:
                conn.execute(
                    """
                    INSERT INTO Videos (Id, CourseId, RelativePath, FileName, SortOrder, FileSizeBytes, DurationSeconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(CourseId, RelativePath) DO UPDATE SET
                        FileName = excluded.FileName,
                        SortOrder = excluded.SortOrder,
                        FileSizeBytes = excluded.FileSizeBytes,
                        DurationSeconds = COALESCE(excluded.DurationSeconds, Videos.DurationSeconds)
                    """,
                    (
                        str(video.id),
                        str(course_id),
                        video.relative_path,
                        video.file_name,
                        video.sort_order,
                        video.file_size_bytes,
                        video.duration_seconds,
                    ),
                )

    def get_video(self, video_id: UUID) -> Video | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT Id, CourseId, RelativePath, FileName, SortOrder, FileSizeBytes, DurationSeconds
                FROM Videos WHERE Id = ?
                """,
                (str(video_id),),
            ).fetchone()
        return _read_video(row) if row else None

    def update_video_duration(self, video_id: UUID, duration_seconds: float) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE Videos SET DurationSeconds = ? WHERE Id = ?",
                (duration_seconds, str(video_id)),
            )


def _read_course(row) -> Course:
    return Course(
        id=UUID(row[0]),
        name=row[1],
        folder_path=row[2],
        added_at=datetime.fromisoformat(row[3]),
    )


def _read_video(row) -> Video:
    return Video(
        id=UUID(row[0]),
        course_id=UUID(row[1]),
        relative_path=row[2],
        file_name=row[3],
        sort_order=row[4],
        file_size_bytes=row[5],
        duration_seconds=row[6],
    )
