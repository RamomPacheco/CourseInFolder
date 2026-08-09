from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from auto_curso.db.connection import get_connection
from auto_curso.models.course import Course
from auto_curso.models.video import Video

_COURSE_COLUMNS = "Id, Name, FolderPath, AddedAt, Description, CoverStoredName"
_VIDEO_COLUMNS = (
    "Id, CourseId, RelativePath, FileName, SortOrder, FileSizeBytes, DurationSeconds, "
    "IsManual, ManualStoredName, DisplayTitle"
)


class CourseRepository:
    def get_all(self) -> list[Course]:
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_COURSE_COLUMNS} FROM Courses WHERE DeletedAt IS NULL ORDER BY AddedAt DESC"
            ).fetchall()
        return [_read_course(r) for r in rows]

    def get_by_id(self, course_id: UUID, include_deleted: bool = False) -> Course | None:
        clause = "" if include_deleted else "AND DeletedAt IS NULL"
        with get_connection() as conn:
            row = conn.execute(
                f"SELECT {_COURSE_COLUMNS} FROM Courses WHERE Id = ? {clause}",
                (str(course_id),),
            ).fetchone()
        return _read_course(row) if row else None

    def get_by_folder_path(self, folder_path: str) -> Course | None:
        with get_connection() as conn:
            row = conn.execute(
                f"SELECT {_COURSE_COLUMNS} FROM Courses WHERE FolderPath = ? AND DeletedAt IS NULL",
                (folder_path,),
            ).fetchone()
        return _read_course(row) if row else None

    def add(self, course: Course) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO Courses (Id, Name, FolderPath, AddedAt) VALUES (?, ?, ?, ?)",
                (str(course.id), course.name, course.folder_path, course.added_at.isoformat()),
            )

    def update(self, course_id: UUID, name: str, description: str | None) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE Courses SET Name = ?, Description = ? WHERE Id = ?",
                (name, description, str(course_id)),
            )

    def set_cover(self, course_id: UUID, stored_name: str | None) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE Courses SET CoverStoredName = ? WHERE Id = ?",
                (stored_name, str(course_id)),
            )

    def soft_delete(self, course_id: UUID) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE Courses SET DeletedAt = ? WHERE Id = ?",
                (datetime.now(timezone.utc).isoformat(), str(course_id)),
            )

    def restore(self, course_id: UUID) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE Courses SET DeletedAt = NULL WHERE Id = ?", (str(course_id),))

    def get_expired_soft_deleted(self, cutoff_iso: str) -> list[Course]:
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_COURSE_COLUMNS} FROM Courses WHERE DeletedAt IS NOT NULL AND DeletedAt < ?",
                (cutoff_iso,),
            ).fetchall()
        return [_read_course(r) for r in rows]

    def hard_delete(self, course_id: UUID) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM Courses WHERE Id = ?", (str(course_id),))

    def get_videos(self, course_id: UUID) -> list[Video]:
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_VIDEO_COLUMNS} FROM Videos WHERE CourseId = ? AND DeletedAt IS NULL ORDER BY SortOrder",
                (str(course_id),),
            ).fetchall()
        return [_read_video(r) for r in rows]

    def sync_videos(self, course_id: UUID, videos: list[Video]) -> None:
        with get_connection() as conn:
            existing = {
                r[0]
                for r in conn.execute(
                    "SELECT RelativePath FROM Videos WHERE CourseId = ? AND IsManual = 0",
                    (str(course_id),),
                ).fetchall()
            }
            new_paths = {v.relative_path for v in videos}
            for path in existing - new_paths:
                conn.execute(
                    "DELETE FROM Videos WHERE CourseId = ? AND RelativePath = ? AND IsManual = 0",
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

    def get_video(self, video_id: UUID, include_deleted: bool = False) -> Video | None:
        clause = "" if include_deleted else "AND DeletedAt IS NULL"
        with get_connection() as conn:
            row = conn.execute(
                f"SELECT {_VIDEO_COLUMNS} FROM Videos WHERE Id = ? {clause}",
                (str(video_id),),
            ).fetchone()
        return _read_video(row) if row else None

    def update_video_duration(self, video_id: UUID, duration_seconds: float) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE Videos SET DurationSeconds = ? WHERE Id = ?",
                (duration_seconds, str(video_id)),
            )

    def update_video(self, video_id: UUID, display_title: str | None, sort_order: int | None) -> None:
        with get_connection() as conn:
            if sort_order is None:
                conn.execute(
                    "UPDATE Videos SET DisplayTitle = ? WHERE Id = ?",
                    (display_title, str(video_id)),
                )
            else:
                conn.execute(
                    "UPDATE Videos SET DisplayTitle = ?, SortOrder = ? WHERE Id = ?",
                    (display_title, sort_order, str(video_id)),
                )

    def add_manual_video(self, video: Video) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO Videos
                    (Id, CourseId, RelativePath, FileName, SortOrder, FileSizeBytes, DurationSeconds,
                     IsManual, ManualStoredName, DisplayTitle)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    str(video.id),
                    str(video.course_id),
                    video.relative_path,
                    video.file_name,
                    video.sort_order,
                    video.file_size_bytes,
                    video.duration_seconds,
                    video.manual_stored_name,
                    video.display_title,
                ),
            )

    def get_next_sort_order(self, course_id: UUID) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(SortOrder), -1) + 1 FROM Videos WHERE CourseId = ?",
                (str(course_id),),
            ).fetchone()
        return int(row[0])

    def soft_delete_video(self, video_id: UUID) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE Videos SET DeletedAt = ? WHERE Id = ?",
                (datetime.now(timezone.utc).isoformat(), str(video_id)),
            )

    def restore_video(self, video_id: UUID) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE Videos SET DeletedAt = NULL WHERE Id = ?", (str(video_id),))

    def get_expired_soft_deleted_videos(self, cutoff_iso: str) -> list[Video]:
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_VIDEO_COLUMNS} FROM Videos WHERE DeletedAt IS NOT NULL AND DeletedAt < ?",
                (cutoff_iso,),
            ).fetchall()
        return [_read_video(r) for r in rows]

    def hard_delete_video(self, video_id: UUID) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM Videos WHERE Id = ?", (str(video_id),))

    def add_excluded_path(self, course_id: UUID, relative_path: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO ExcludedVideoPaths (CourseId, RelativePath) VALUES (?, ?)",
                (str(course_id), relative_path),
            )

    def get_excluded_paths(self, course_id: UUID) -> set[str]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT RelativePath FROM ExcludedVideoPaths WHERE CourseId = ?",
                (str(course_id),),
            ).fetchall()
        return {r[0] for r in rows}


def _read_course(row) -> Course:
    return Course(
        id=UUID(row[0]),
        name=row[1],
        folder_path=row[2],
        added_at=datetime.fromisoformat(row[3]),
        description=row[4],
        cover_stored_name=row[5],
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
        is_manual=bool(row[7]),
        manual_stored_name=row[8],
        display_title=row[9],
    )
