from __future__ import annotations

from datetime import datetime
from uuid import UUID

from auto_curso.db.connection import get_connection
from auto_curso.models.progress import PlaybackProgress


class ProgressRepository:
    def get_for_course(self, course_id: UUID) -> dict[UUID, PlaybackProgress]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT p.VideoId, p.PositionSeconds, p.IsCompleted, p.WatchedPercent, p.LastWatchedAt
                FROM PlaybackProgress p
                INNER JOIN Videos v ON v.Id = p.VideoId
                WHERE v.CourseId = ? AND v.DeletedAt IS NULL
                """,
                (str(course_id),),
            ).fetchall()
        return {UUID(row[0]): _read_progress(row) for row in rows}

    def get(self, video_id: UUID) -> PlaybackProgress | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT VideoId, PositionSeconds, IsCompleted, WatchedPercent, LastWatchedAt
                FROM PlaybackProgress WHERE VideoId = ?
                """,
                (str(video_id),),
            ).fetchone()
        return _read_progress(row) if row else None

    def save(self, progress: PlaybackProgress) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO PlaybackProgress (VideoId, PositionSeconds, IsCompleted, WatchedPercent, LastWatchedAt)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(VideoId) DO UPDATE SET
                    PositionSeconds = excluded.PositionSeconds,
                    IsCompleted = excluded.IsCompleted,
                    WatchedPercent = excluded.WatchedPercent,
                    LastWatchedAt = excluded.LastWatchedAt
                """,
                (
                    str(progress.video_id),
                    progress.position_seconds,
                    1 if progress.is_completed else 0,
                    progress.watched_percent,
                    progress.last_watched_at.isoformat(),
                ),
            )

    def get_most_recent_in_progress(self) -> PlaybackProgress | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT VideoId, PositionSeconds, IsCompleted, WatchedPercent, LastWatchedAt
                FROM PlaybackProgress
                WHERE IsCompleted = 0 AND PositionSeconds > 0
                ORDER BY LastWatchedAt DESC LIMIT 1
                """
            ).fetchone()
        return _read_progress(row) if row else None

    def get_completed_count(self, course_id: UUID) -> int:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM PlaybackProgress p
                INNER JOIN Videos v ON v.Id = p.VideoId
                WHERE v.CourseId = ? AND p.IsCompleted = 1 AND v.DeletedAt IS NULL
                """,
                (str(course_id),),
            ).fetchone()
        return int(row[0]) if row else 0

    def delete_orphans(self, course_id: UUID, valid_video_ids: list[UUID]) -> None:
        with get_connection() as conn:
            if not valid_video_ids:
                conn.execute(
                    """
                    DELETE FROM PlaybackProgress WHERE VideoId IN (
                        SELECT Id FROM Videos WHERE CourseId = ?
                    )
                    """,
                    (str(course_id),),
                )
                return
            placeholders = ", ".join("?" * len(valid_video_ids))
            params = [str(course_id)] + [str(vid) for vid in valid_video_ids]
            conn.execute(
                f"""
                DELETE FROM PlaybackProgress WHERE VideoId IN (
                    SELECT Id FROM Videos WHERE CourseId = ?
                ) AND VideoId NOT IN ({placeholders})
                """,
                params,
            )


def _read_progress(row) -> PlaybackProgress:
    return PlaybackProgress(
        video_id=UUID(row[0]),
        position_seconds=row[1],
        is_completed=bool(row[2]),
        watched_percent=row[3],
        last_watched_at=datetime.fromisoformat(row[4]),
    )
