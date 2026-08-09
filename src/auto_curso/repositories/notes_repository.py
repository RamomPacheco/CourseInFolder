from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from auto_curso.db.connection import get_connection
from auto_curso.models.note import VideoNote

_NOTE_COLUMNS = "Id, VideoId, TimeSeconds, Text, CreatedAt"


class NotesRepository:
    def list_for_video(self, video_id: UUID) -> list[VideoNote]:
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_NOTE_COLUMNS} FROM VideoNotes WHERE VideoId = ? AND DeletedAt IS NULL ORDER BY TimeSeconds",
                (str(video_id),),
            ).fetchall()
        return [_read_note(r) for r in rows]

    def get(self, note_id: UUID, include_deleted: bool = False) -> VideoNote | None:
        clause = "" if include_deleted else "AND DeletedAt IS NULL"
        with get_connection() as conn:
            row = conn.execute(
                f"SELECT {_NOTE_COLUMNS} FROM VideoNotes WHERE Id = ? {clause}",
                (str(note_id),),
            ).fetchone()
        return _read_note(row) if row else None

    def add(self, video_id: UUID, time_seconds: float, text: str) -> VideoNote:
        note = VideoNote(
            id=uuid4(),
            video_id=video_id,
            time_seconds=time_seconds,
            text=text,
            created_at=datetime.now(),
        )
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO VideoNotes (Id, VideoId, TimeSeconds, Text, CreatedAt)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(note.id), str(video_id), time_seconds, text, note.created_at.isoformat()),
            )
        return note

    def update(self, note_id: UUID, text: str) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE VideoNotes SET Text = ? WHERE Id = ?", (text, str(note_id)))

    def soft_delete(self, note_id: UUID) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE VideoNotes SET DeletedAt = ? WHERE Id = ?",
                (datetime.now(timezone.utc).isoformat(), str(note_id)),
            )

    def restore(self, note_id: UUID) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE VideoNotes SET DeletedAt = NULL WHERE Id = ?", (str(note_id),))

    def get_expired_soft_deleted(self, cutoff_iso: str) -> list[VideoNote]:
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_NOTE_COLUMNS} FROM VideoNotes WHERE DeletedAt IS NOT NULL AND DeletedAt < ?",
                (cutoff_iso,),
            ).fetchall()
        return [_read_note(r) for r in rows]

    def hard_delete(self, note_id: UUID) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM VideoNotes WHERE Id = ?", (str(note_id),))

    def get_course_note(self, course_id: UUID) -> str:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT Text FROM CourseNotes WHERE CourseId = ?", (str(course_id),)
            ).fetchone()
        return row[0] if row else ""

    def save_course_note(self, course_id: UUID, text: str) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO CourseNotes (CourseId, Text) VALUES (?, ?)
                ON CONFLICT(CourseId) DO UPDATE SET Text = excluded.Text
                """,
                (str(course_id), text),
            )

    def get_favorites_for_course(self, course_id: UUID) -> set[UUID]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT f.VideoId FROM VideoFavorites f
                INNER JOIN Videos v ON v.Id = f.VideoId
                WHERE v.CourseId = ?
                """,
                (str(course_id),),
            ).fetchall()
        return {UUID(r[0]) for r in rows}

    def toggle_favorite(self, video_id: UUID) -> bool:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM VideoFavorites WHERE VideoId = ?", (str(video_id),)
            ).fetchone()
            if row:
                conn.execute("DELETE FROM VideoFavorites WHERE VideoId = ?", (str(video_id),))
                return False
            conn.execute("INSERT INTO VideoFavorites (VideoId) VALUES (?)", (str(video_id),))
            return True


def _read_note(row) -> VideoNote:
    return VideoNote(
        id=UUID(row[0]),
        video_id=UUID(row[1]),
        time_seconds=row[2],
        text=row[3],
        created_at=datetime.fromisoformat(row[4]),
    )
