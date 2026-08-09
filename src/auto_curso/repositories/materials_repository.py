from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from auto_curso.db.connection import get_connection
from auto_curso.models.material import UploadedMaterial

_MATERIAL_COLUMNS = "Id, VideoId, FileName, StoredName, MimeType, SizeBytes, UploadedAt"


class MaterialsRepository:
    """Acesso a dados de materiais (imagem/áudio/PDF) anexados a vídeos (SQLite)."""

    def list_for_video(self, video_id: UUID) -> list[UploadedMaterial]:
        """Lista os materiais ativos anexados a um vídeo, na ordem de upload.

        Args:
            video_id (UUID): Identificador do vídeo.

        Returns:
            list[UploadedMaterial]: Materiais com `DeletedAt IS NULL`, ordenados por `UploadedAt`.
        """
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_MATERIAL_COLUMNS} FROM VideoMaterials WHERE VideoId = ? AND DeletedAt IS NULL ORDER BY UploadedAt",
                (str(video_id),),
            ).fetchall()
        return [_read_material(r) for r in rows]

    def get(self, material_id: UUID, include_deleted: bool = False) -> UploadedMaterial | None:
        """Busca um material pelo id.

        Args:
            material_id (UUID): Identificador do material.
            include_deleted (bool): Quando True, também retorna
                materiais em período de soft-delete.

        Returns:
            UploadedMaterial | None: O material encontrado, ou None se
                não existir (ou estiver excluído e `include_deleted`
                for False).
        """
        clause = "" if include_deleted else "AND DeletedAt IS NULL"
        with get_connection() as conn:
            row = conn.execute(
                f"SELECT {_MATERIAL_COLUMNS} FROM VideoMaterials WHERE Id = ? {clause}",
                (str(material_id),),
            ).fetchone()
        return _read_material(row) if row else None

    def add(
        self, video_id: UUID, file_name: str, stored_name: str, mime_type: str, size_bytes: int
    ) -> UploadedMaterial:
        """Registra um material recém-enviado.

        Args:
            video_id (UUID): Identificador do vídeo dono do material.
            file_name (str): Nome original do arquivo, exibido na interface.
            stored_name (str): Nome do arquivo salvo em disco
                (`get_video_materials_dir(course_id, video_id)`).
            mime_type (str): Tipo MIME informado no upload.
            size_bytes (int): Tamanho do arquivo em bytes.

        Returns:
            UploadedMaterial: O material recém-criado.
        """
        material = UploadedMaterial(
            id=uuid4(),
            video_id=video_id,
            file_name=file_name,
            stored_name=stored_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            uploaded_at=datetime.now(timezone.utc),
        )
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO VideoMaterials
                    (Id, VideoId, FileName, StoredName, MimeType, SizeBytes, UploadedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(material.id),
                    str(video_id),
                    file_name,
                    stored_name,
                    mime_type,
                    size_bytes,
                    material.uploaded_at.isoformat(),
                ),
            )
        return material

    def rename(self, material_id: UUID, file_name: str) -> None:
        """Renomeia o nome de exibição de um material.

        Args:
            material_id (UUID): Identificador do material.
            file_name (str): Novo nome de exibição.
        """
        with get_connection() as conn:
            conn.execute(
                "UPDATE VideoMaterials SET FileName = ? WHERE Id = ?", (file_name, str(material_id))
            )

    def soft_delete(self, material_id: UUID) -> None:
        """Marca um material como excluído (soft-delete), sem removê-lo do banco.

        Args:
            material_id (UUID): Identificador do material.
        """
        with get_connection() as conn:
            conn.execute(
                "UPDATE VideoMaterials SET DeletedAt = ? WHERE Id = ?",
                (datetime.now(timezone.utc).isoformat(), str(material_id)),
            )

    def restore(self, material_id: UUID) -> None:
        """Reverte o soft-delete de um material (usado pelo botão "Desfazer").

        Args:
            material_id (UUID): Identificador do material.
        """
        with get_connection() as conn:
            conn.execute("UPDATE VideoMaterials SET DeletedAt = NULL WHERE Id = ?", (str(material_id),))

    def get_expired_soft_deleted(self, cutoff_iso: str) -> list[UploadedMaterial]:
        """Lista materiais cujo período de graça do soft-delete já expirou.

        Args:
            cutoff_iso (str): Instante (ISO 8601) além do qual o
                soft-delete é considerado expirado.

        Returns:
            list[UploadedMaterial]: Materiais com `DeletedAt` preenchido
                e anterior a `cutoff_iso`, prontos para exclusão
                definitiva (registro e arquivo em disco) pela purga.
        """
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_MATERIAL_COLUMNS} FROM VideoMaterials WHERE DeletedAt IS NOT NULL AND DeletedAt < ?",
                (cutoff_iso,),
            ).fetchall()
        return [_read_material(r) for r in rows]

    def hard_delete(self, material_id: UUID) -> None:
        """Remove um material definitivamente do banco.

        Não apaga o arquivo em disco — isso é responsabilidade de quem
        chama este método (a purga usa `stored_name` antes de chamá-lo).

        Args:
            material_id (UUID): Identificador do material.
        """
        with get_connection() as conn:
            conn.execute("DELETE FROM VideoMaterials WHERE Id = ?", (str(material_id),))


def _read_material(row) -> UploadedMaterial:
    """Converte uma linha de `VideoMaterials` (na ordem de `_MATERIAL_COLUMNS`) em um `UploadedMaterial`."""
    return UploadedMaterial(
        id=UUID(row[0]),
        video_id=UUID(row[1]),
        file_name=row[2],
        stored_name=row[3],
        mime_type=row[4],
        size_bytes=row[5],
        uploaded_at=datetime.fromisoformat(row[6]),
    )
