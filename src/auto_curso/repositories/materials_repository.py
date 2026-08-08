from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from auto_curso.db.connection import get_connection
from auto_curso.models.material import UploadedMaterial


class MaterialsRepository:
    def list_for_video(self, video_id: UUID) -> list[UploadedMaterial]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT Id, VideoId, FileName, StoredName, MimeType, SizeBytes, UploadedAt
                FROM VideoMaterials WHERE VideoId = ? ORDER BY UploadedAt
                """,
                (str(video_id),),
            ).fetchall()
        return [_read_material(r) for r in rows]

    def get(self, material_id: UUID) -> UploadedMaterial | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT Id, VideoId, FileName, StoredName, MimeType, SizeBytes, UploadedAt
                FROM VideoMaterials WHERE Id = ?
                """,
                (str(material_id),),
            ).fetchone()
        return _read_material(row) if row else None

    def add(
        self, video_id: UUID, file_name: str, stored_name: str, mime_type: str, size_bytes: int
    ) -> UploadedMaterial:
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

    def delete(self, material_id: UUID) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM VideoMaterials WHERE Id = ?", (str(material_id),))


def _read_material(row) -> UploadedMaterial:
    return UploadedMaterial(
        id=UUID(row[0]),
        video_id=UUID(row[1]),
        file_name=row[2],
        stored_name=row[3],
        mime_type=row[4],
        size_bytes=row[5],
        uploaded_at=datetime.fromisoformat(row[6]),
    )
