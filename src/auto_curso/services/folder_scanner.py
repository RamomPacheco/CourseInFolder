from __future__ import annotations

import os
from pathlib import Path

from natsort import natsorted

from auto_curso.constants import VIDEO_EXTENSIONS
from auto_curso.models.video import ScannedVideoFile


class FolderScanner:
    def scan(self, folder_path: str) -> list[ScannedVideoFile]:
        root = Path(folder_path).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Pasta não encontrada: {root}")

        files: list[ScannedVideoFile] = []
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                path = Path(dirpath) / name
                if path.suffix.lower() not in VIDEO_EXTENSIONS:
                    continue
                try:
                    stat = path.stat()
                    relative = path.relative_to(root).as_posix()
                    files.append(
                        ScannedVideoFile(
                            relative_path=relative,
                            file_name=path.name,
                            file_size_bytes=stat.st_size,
                        )
                    )
                except OSError:
                    continue

        return natsorted(files, key=lambda f: f.relative_path)
