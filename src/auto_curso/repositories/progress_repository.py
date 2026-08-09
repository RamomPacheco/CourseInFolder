from __future__ import annotations

from datetime import datetime
from uuid import UUID

from auto_curso.db.connection import get_connection
from auto_curso.models.progress import PlaybackProgress


class ProgressRepository:
    """Acesso a dados de progresso de reprodução (SQLite)."""

    def get_for_course(self, course_id: UUID) -> dict[UUID, PlaybackProgress]:
        """Carrega o progresso de todos os vídeos ativos de um curso.

        Args:
            course_id (UUID): Identificador do curso.

        Returns:
            dict[UUID, PlaybackProgress]: Progresso indexado pelo id do
                vídeo. Vídeos sem progresso salvo simplesmente não
                aparecem no dicionário.
        """
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
        """Busca o progresso salvo de um vídeo específico.

        Args:
            video_id (UUID): Identificador do vídeo.

        Returns:
            PlaybackProgress | None: O progresso salvo, ou None se o
                vídeo ainda não foi reproduzido.
        """
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
        """Cria ou substitui (upsert) o progresso salvo de um vídeo.

        Args:
            progress (PlaybackProgress): Progresso a salvar.
        """
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
        """Busca o progresso mais recente de um vídeo iniciado e ainda não concluído.

        Usado para montar o card "Continuar assistindo" da biblioteca.

        Returns:
            PlaybackProgress | None: O progresso mais recentemente
                salvo entre os vídeos com posição maior que zero e não
                concluídos, ou None se não houver nenhum.
        """
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
        """Conta quantos vídeos ativos de um curso estão marcados como concluídos.

        Args:
            course_id (UUID): Identificador do curso.

        Returns:
            int: Número de vídeos concluídos.
        """
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
        """Remove progresso de vídeos que não existem mais no curso.

        Chamado após um rescan da pasta: qualquer progresso associado a
        um vídeo do curso cujo id não esteja em `valid_video_ids` é
        descartado (o arquivo sumiu ou foi renomeado).

        Args:
            course_id (UUID): Identificador do curso.
            valid_video_ids (list[UUID]): Ids de vídeos que devem ser
                preservados. Lista vazia remove todo o progresso do curso.
        """
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
    """Converte uma linha de `PlaybackProgress` em um `PlaybackProgress` (dataclass)."""
    return PlaybackProgress(
        video_id=UUID(row[0]),
        position_seconds=row[1],
        is_completed=bool(row[2]),
        watched_percent=row[3],
        last_watched_at=datetime.fromisoformat(row[4]),
    )
