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
    """Acesso a dados de Cursos e Vídeos (SQLite), incluindo o ciclo de soft-delete."""

    def get_all(self) -> list[Course]:
        """Lista todos os cursos ativos (não excluídos), do mais recente para o mais antigo.

        Returns:
            list[Course]: Cursos com `DeletedAt IS NULL`, ordenados por `AddedAt` decrescente.
        """
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_COURSE_COLUMNS} FROM Courses WHERE DeletedAt IS NULL ORDER BY AddedAt DESC"
            ).fetchall()
        return [_read_course(r) for r in rows]

    def get_by_id(self, course_id: UUID, include_deleted: bool = False) -> Course | None:
        """Busca um curso pelo id.

        Args:
            course_id (UUID): Identificador do curso.
            include_deleted (bool): Quando True, também retorna cursos
                em período de soft-delete (usado pela purga e pelo restore).

        Returns:
            Course | None: O curso encontrado, ou None se não existir
                (ou estiver excluído e `include_deleted` for False).
        """
        clause = "" if include_deleted else "AND DeletedAt IS NULL"
        with get_connection() as conn:
            row = conn.execute(
                f"SELECT {_COURSE_COLUMNS} FROM Courses WHERE Id = ? {clause}",
                (str(course_id),),
            ).fetchone()
        return _read_course(row) if row else None

    def get_by_folder_path(self, folder_path: str) -> Course | None:
        """Busca um curso ativo pelo caminho da pasta local.

        Args:
            folder_path (str): Caminho absoluto normalizado da pasta.

        Returns:
            Course | None: O curso cadastrado nessa pasta, ou None se
                nenhum curso ativo usar esse caminho.
        """
        with get_connection() as conn:
            row = conn.execute(
                f"SELECT {_COURSE_COLUMNS} FROM Courses WHERE FolderPath = ? AND DeletedAt IS NULL",
                (folder_path,),
            ).fetchone()
        return _read_course(row) if row else None

    def add(self, course: Course) -> None:
        """Insere um novo curso.

        Args:
            course (Course): Curso a cadastrar (id, name, folder_path e
                added_at já preenchidos pelo chamador).
        """
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO Courses (Id, Name, FolderPath, AddedAt) VALUES (?, ?, ?, ?)",
                (str(course.id), course.name, course.folder_path, course.added_at.isoformat()),
            )

    def update(self, course_id: UUID, name: str, description: str | None) -> None:
        """Atualiza nome e descrição de um curso.

        Args:
            course_id (UUID): Identificador do curso.
            name (str): Novo nome de exibição.
            description (str | None): Nova descrição, ou None para limpá-la.
        """
        with get_connection() as conn:
            conn.execute(
                "UPDATE Courses SET Name = ?, Description = ? WHERE Id = ?",
                (name, description, str(course_id)),
            )

    def set_cover(self, course_id: UUID, stored_name: str | None) -> None:
        """Define (ou remove) o nome do arquivo de capa de um curso.

        Args:
            course_id (UUID): Identificador do curso.
            stored_name (str | None): Nome do arquivo salvo em
                `get_course_cover_dir(course_id)`, ou None para remover a capa.
        """
        with get_connection() as conn:
            conn.execute(
                "UPDATE Courses SET CoverStoredName = ? WHERE Id = ?",
                (stored_name, str(course_id)),
            )

    def soft_delete(self, course_id: UUID) -> None:
        """Marca um curso como excluído (soft-delete), sem removê-lo do banco.

        Args:
            course_id (UUID): Identificador do curso.
        """
        with get_connection() as conn:
            conn.execute(
                "UPDATE Courses SET DeletedAt = ? WHERE Id = ?",
                (datetime.now(timezone.utc).isoformat(), str(course_id)),
            )

    def restore(self, course_id: UUID) -> None:
        """Reverte o soft-delete de um curso (usado pelo botão "Desfazer").

        Args:
            course_id (UUID): Identificador do curso.
        """
        with get_connection() as conn:
            conn.execute("UPDATE Courses SET DeletedAt = NULL WHERE Id = ?", (str(course_id),))

    def get_expired_soft_deleted(self, cutoff_iso: str) -> list[Course]:
        """Lista cursos cujo período de graça do soft-delete já expirou.

        Args:
            cutoff_iso (str): Instante (ISO 8601) além do qual o
                soft-delete é considerado expirado; normalmente
                `agora - SOFT_DELETE_GRACE_SECONDS`.

        Returns:
            list[Course]: Cursos com `DeletedAt` preenchido e anterior
                a `cutoff_iso`, prontos para exclusão definitiva pela purga.
        """
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_COURSE_COLUMNS} FROM Courses WHERE DeletedAt IS NOT NULL AND DeletedAt < ?",
                (cutoff_iso,),
            ).fetchall()
        return [_read_course(r) for r in rows]

    def hard_delete(self, course_id: UUID) -> None:
        """Remove um curso definitivamente do banco (cascata via FK para vídeos e afins).

        Args:
            course_id (UUID): Identificador do curso.
        """
        with get_connection() as conn:
            conn.execute("DELETE FROM Courses WHERE Id = ?", (str(course_id),))

    def get_videos(self, course_id: UUID) -> list[Video]:
        """Lista as aulas ativas de um curso, na ordem da playlist.

        Args:
            course_id (UUID): Identificador do curso.

        Returns:
            list[Video]: Vídeos com `DeletedAt IS NULL`, ordenados por `SortOrder`.
        """
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_VIDEO_COLUMNS} FROM Videos WHERE CourseId = ? AND DeletedAt IS NULL ORDER BY SortOrder",
                (str(course_id),),
            ).fetchall()
        return [_read_video(r) for r in rows]

    def sync_videos(self, course_id: UUID, videos: list[Video]) -> None:
        """Sincroniza os vídeos escaneados da pasta com o banco.

        Remove do banco os vídeos escaneados (`IsManual = 0`) cujo
        caminho relativo não aparece mais em `videos`, e insere ou
        atualiza (via upsert) os demais. Vídeos avulsos (`IsManual = 1`)
        nunca são tocados por este método.

        Args:
            course_id (UUID): Identificador do curso.
            videos (list[Video]): Vídeos resultantes do scan mais
                recente da pasta do curso.
        """
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
        """Busca uma aula pelo id.

        Args:
            video_id (UUID): Identificador do vídeo.
            include_deleted (bool): Quando True, também retorna vídeos
                em período de soft-delete (usado pela purga e pelo restore).

        Returns:
            Video | None: O vídeo encontrado, ou None se não existir
                (ou estiver excluído e `include_deleted` for False).
        """
        clause = "" if include_deleted else "AND DeletedAt IS NULL"
        with get_connection() as conn:
            row = conn.execute(
                f"SELECT {_VIDEO_COLUMNS} FROM Videos WHERE Id = ? {clause}",
                (str(video_id),),
            ).fetchone()
        return _read_video(row) if row else None

    def update_video_duration(self, video_id: UUID, duration_seconds: float) -> None:
        """Grava a duração de um vídeo, descoberta na primeira reprodução.

        Args:
            video_id (UUID): Identificador do vídeo.
            duration_seconds (float): Duração total em segundos.
        """
        with get_connection() as conn:
            conn.execute(
                "UPDATE Videos SET DurationSeconds = ? WHERE Id = ?",
                (duration_seconds, str(video_id)),
            )

    def update_video(self, video_id: UUID, display_title: str | None, sort_order: int | None) -> None:
        """Atualiza o título de exibição e, opcionalmente, a posição de uma aula na playlist.

        Args:
            video_id (UUID): Identificador do vídeo.
            display_title (str | None): Novo título de exibição, ou
                None para voltar a usar o nome original do arquivo.
            sort_order (int | None): Nova posição na playlist, ou None
                para manter a posição atual.
        """
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
        """Insere uma aula avulsa (anexada fora do scan da pasta).

        Args:
            video (Video): Vídeo com `is_manual=True` e
                `manual_stored_name` já preenchidos.
        """
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
        """Calcula a próxima posição livre no final da playlist de um curso.

        Args:
            course_id (UUID): Identificador do curso.

        Returns:
            int: Um a mais que o maior `SortOrder` existente, ou 0 se o curso ainda não tem vídeos.
        """
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(SortOrder), -1) + 1 FROM Videos WHERE CourseId = ?",
                (str(course_id),),
            ).fetchone()
        return int(row[0])

    def soft_delete_video(self, video_id: UUID) -> None:
        """Marca uma aula como excluída (soft-delete), sem removê-la do banco.

        Args:
            video_id (UUID): Identificador do vídeo.
        """
        with get_connection() as conn:
            conn.execute(
                "UPDATE Videos SET DeletedAt = ? WHERE Id = ?",
                (datetime.now(timezone.utc).isoformat(), str(video_id)),
            )

    def restore_video(self, video_id: UUID) -> None:
        """Reverte o soft-delete de uma aula (usado pelo botão "Desfazer").

        Args:
            video_id (UUID): Identificador do vídeo.
        """
        with get_connection() as conn:
            conn.execute("UPDATE Videos SET DeletedAt = NULL WHERE Id = ?", (str(video_id),))

    def get_expired_soft_deleted_videos(self, cutoff_iso: str) -> list[Video]:
        """Lista aulas cujo período de graça do soft-delete já expirou.

        Args:
            cutoff_iso (str): Instante (ISO 8601) além do qual o
                soft-delete é considerado expirado.

        Returns:
            list[Video]: Vídeos com `DeletedAt` preenchido e anterior
                a `cutoff_iso`, prontos para exclusão definitiva pela purga.
        """
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_VIDEO_COLUMNS} FROM Videos WHERE DeletedAt IS NOT NULL AND DeletedAt < ?",
                (cutoff_iso,),
            ).fetchall()
        return [_read_video(r) for r in rows]

    def hard_delete_video(self, video_id: UUID) -> None:
        """Remove uma aula definitivamente do banco (cascata via FK para progresso, notas e materiais).

        Args:
            video_id (UUID): Identificador do vídeo.
        """
        with get_connection() as conn:
            conn.execute("DELETE FROM Videos WHERE Id = ?", (str(video_id),))

    def add_excluded_path(self, course_id: UUID, relative_path: str) -> None:
        """Marca um caminho de arquivo como excluído permanentemente da playlist.

        Usado quando uma aula escaneada da pasta é excluída pelo
        usuário, para que o próximo "Atualizar" (rescan) não a
        readicione automaticamente.

        Args:
            course_id (UUID): Identificador do curso.
            relative_path (str): Caminho relativo do arquivo dentro da
                pasta do curso.
        """
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO ExcludedVideoPaths (CourseId, RelativePath) VALUES (?, ?)",
                (str(course_id), relative_path),
            )

    def get_excluded_paths(self, course_id: UUID) -> set[str]:
        """Lista os caminhos relativos permanentemente excluídos da playlist de um curso.

        Args:
            course_id (UUID): Identificador do curso.

        Returns:
            set[str]: Caminhos relativos a ignorar em futuros scans da pasta.
        """
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT RelativePath FROM ExcludedVideoPaths WHERE CourseId = ?",
                (str(course_id),),
            ).fetchall()
        return {r[0] for r in rows}


def _read_course(row) -> Course:
    """Converte uma linha de `Courses` (na ordem de `_COURSE_COLUMNS`) em um `Course`."""
    return Course(
        id=UUID(row[0]),
        name=row[1],
        folder_path=row[2],
        added_at=datetime.fromisoformat(row[3]),
        description=row[4],
        cover_stored_name=row[5],
    )


def _read_video(row) -> Video:
    """Converte uma linha de `Videos` (na ordem de `_VIDEO_COLUMNS`) em um `Video`."""
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
