from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from auto_curso.constants import get_manual_video_dir
from auto_curso.models.progress import PlaybackProgress


@dataclass
class Video:
    """Uma aula da playlist de um curso.

    Pode vir do scan automático da pasta do curso (`is_manual=False`,
    `relative_path` aponta pro arquivo real) ou ter sido anexada
    avulsamente pelo usuário (`is_manual=True`, arquivo guardado fora da
    pasta do curso, em `manual_stored_name`).
    """

    id: UUID
    course_id: UUID
    relative_path: str
    file_name: str
    sort_order: int
    file_size_bytes: int
    duration_seconds: float | None = None
    display_title: str | None = None
    is_manual: bool = False
    manual_stored_name: str | None = None

    @property
    def display_name(self) -> str:
        """Retorna o nome a exibir na interface.

        Returns:
            str: O título de exibição definido pelo usuário
                (`display_title`), ou o nome original do arquivo
                (`file_name`) quando não há título customizado.
        """
        return self.display_title or self.file_name


@dataclass
class ScannedVideoFile:
    """Um arquivo de vídeo (ou material) encontrado ao escanear a pasta de um curso."""

    relative_path: str
    file_name: str
    file_size_bytes: int


@dataclass
class VideoWithProgress:
    """Combina uma aula com seu progresso de reprodução, pronta para responder à API."""

    video: Video
    progress: PlaybackProgress | None
    course_folder_path: str

    @property
    def full_path(self) -> str:
        """Resolve o caminho absoluto do arquivo de vídeo no disco.

        Cálculo de caminho puro — não verifica se o arquivo existe nem
        toca o sistema de arquivos.

        Returns:
            str: Caminho do vídeo avulso (dentro da pasta de dados do
                app) quando `video.is_manual` é verdadeiro; caso
                contrário, caminho do arquivo dentro da pasta real do
                curso (`course_folder_path` + `video.relative_path`).
        """
        if self.video.is_manual:
            return str(get_manual_video_dir(self.video.course_id, self.video.id) / self.video.manual_stored_name)
        return str(Path(self.course_folder_path) / self.video.relative_path)

    @property
    def progress_percent(self) -> float:
        """Calcula o percentual assistido da aula.

        Returns:
            float: 100.0 quando a aula está marcada como concluída;
                caso contrário, o percentual assistido salvo em
                `progress`, ou 0.0 se ainda não há progresso registrado.
        """
        if self.progress and self.progress.is_completed:
            return 100.0
        return self.progress.watched_percent if self.progress else 0.0

    @property
    def is_completed(self) -> bool:
        """Indica se a aula está marcada como concluída.

        Returns:
            bool: True se existe progresso registrado e ele está
                marcado como concluído; False caso contrário.
        """
        return bool(self.progress and self.progress.is_completed)
