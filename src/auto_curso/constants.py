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
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".local" / "share"
    data_dir = base / "auto_curso"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_database_path() -> Path:
    return get_data_dir() / "data.db"


def get_course_materials_dir(course_id) -> Path:
    return get_data_dir() / "materials" / str(course_id)


def get_video_materials_dir(course_id, video_id) -> Path:
    d = get_course_materials_dir(course_id) / str(video_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_course_manual_videos_dir(course_id) -> Path:
    return get_data_dir() / "manual_videos" / str(course_id)


def get_manual_video_dir(course_id, video_id) -> Path:
    d = get_course_manual_videos_dir(course_id) / str(video_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_course_cover_dir(course_id) -> Path:
    d = get_data_dir() / "covers" / str(course_id)
    d.mkdir(parents=True, exist_ok=True)
    return d
