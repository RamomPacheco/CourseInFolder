from __future__ import annotations

import os
import sys
from pathlib import Path

COMPLETION_THRESHOLD = 0.95
POSITION_SAVE_DEBOUNCE_MS = 2000
UI_UPDATE_INTERVAL_MS = 200

VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".avi", ".webm", ".mov", ".wmv", ".m4v", ".flv",
    ".mpeg", ".mpg", ".3gp", ".ogv",
})

MATERIAL_EXTENSIONS = frozenset({
    ".pdf", ".csv", ".txt", ".zip", ".docx", ".pptx", ".xlsx", ".md",
    ".png", ".jpg", ".jpeg",
})

UPLOAD_EXTENSIONS = frozenset({
    ".pdf",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac",
})
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024

COVER_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
MAX_COVER_SIZE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_UPLOAD_SIZE_BYTES = 4 * 1024 * 1024 * 1024

SOFT_DELETE_GRACE_SECONDS = 30
PURGE_INTERVAL_SECONDS = 10


def get_data_dir() -> Path:
    """Retorna o diretório raiz de dados do aplicativo, criando-o se necessário.

    Esta é a única função do módulo que tem efeito colateral de I/O
    intencional: garante que a pasta de dados do app exista antes de
    qualquer conexão com o banco ou escrita de arquivo (materiais, capas,
    vídeos avulsos), já que essas operações falhariam sem o diretório pai.

    Returns:
        Path: Caminho absoluto da pasta de dados (`%APPDATA%/auto_curso`
            no Windows, `~/.local/share/auto_curso` no Linux/macOS).
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".local" / "share"
    data_dir = base / "auto_curso"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_database_path() -> Path:
    """Retorna o caminho do arquivo SQLite do aplicativo.

    Returns:
        Path: Caminho completo para `data.db` dentro da pasta de dados.
    """
    return get_data_dir() / "data.db"


def get_course_materials_dir(course_id) -> Path:
    """Constrói o caminho da pasta que guarda os materiais de um curso.

    Cálculo de caminho puro — não cria o diretório no disco.

    Args:
        course_id: Identificador do curso.

    Returns:
        Path: Caminho da pasta `materials/<course_id>` na pasta de dados.
    """
    return get_data_dir() / "materials" / str(course_id)


def get_video_materials_dir(course_id, video_id) -> Path:
    """Constrói o caminho da pasta de materiais anexados a um vídeo específico.

    Cálculo de caminho puro — não cria o diretório no disco. Quem for
    escrever um arquivo nessa pasta deve garantir sua existência antes
    (`dir_path.mkdir(parents=True, exist_ok=True)`); os pontos de leitura
    e exclusão (streaming, limpeza da purga) toleram normalmente que ela
    ainda não exista.

    Args:
        course_id: Identificador do curso dono do vídeo.
        video_id: Identificador do vídeo.

    Returns:
        Path: Caminho da pasta `materials/<course_id>/<video_id>`.
    """
    return get_course_materials_dir(course_id) / str(video_id)


def get_course_manual_videos_dir(course_id) -> Path:
    """Constrói o caminho da pasta que guarda todos os vídeos avulsos de um curso.

    Cálculo de caminho puro — não cria o diretório no disco.

    Args:
        course_id: Identificador do curso.

    Returns:
        Path: Caminho da pasta `manual_videos/<course_id>`.
    """
    return get_data_dir() / "manual_videos" / str(course_id)


def get_manual_video_dir(course_id, video_id) -> Path:
    """Constrói o caminho da pasta de um vídeo avulso (anexado fora do scan da pasta).

    Cálculo de caminho puro — não cria o diretório no disco (mesmo motivo
    de `get_video_materials_dir`).

    Args:
        course_id: Identificador do curso dono do vídeo.
        video_id: Identificador do vídeo avulso.

    Returns:
        Path: Caminho da pasta `manual_videos/<course_id>/<video_id>`.
    """
    return get_course_manual_videos_dir(course_id) / str(video_id)


def get_course_cover_dir(course_id) -> Path:
    """Constrói o caminho da pasta que guarda a imagem de capa de um curso.

    Cálculo de caminho puro — não cria o diretório no disco (mesmo motivo
    de `get_video_materials_dir`).

    Args:
        course_id: Identificador do curso.

    Returns:
        Path: Caminho da pasta `covers/<course_id>`.
    """
    return get_data_dir() / "covers" / str(course_id)
