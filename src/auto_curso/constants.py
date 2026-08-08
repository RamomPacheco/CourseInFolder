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
