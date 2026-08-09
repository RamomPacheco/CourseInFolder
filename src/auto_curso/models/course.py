from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Course:
    """Curso cadastrado no app: uma pasta local de vídeos mais metadados editáveis pelo usuário."""

    id: UUID
    name: str
    folder_path: str
    added_at: datetime
    description: str | None = None
    cover_stored_name: str | None = None


@dataclass
class CourseSummary:
    """Curso com os totais de aulas já calculados, prontos para exibição na biblioteca."""

    course: Course
    total_videos: int
    completed_videos: int

    @property
    def progress_percent(self) -> float:
        """Calcula o percentual de aulas concluídas do curso.

        Returns:
            float: Percentual de 0 a 100. Retorna 0.0 quando o curso não
                tem nenhuma aula (evita divisão por zero).
        """
        if self.total_videos == 0:
            return 0.0
        return self.completed_videos / self.total_videos * 100
