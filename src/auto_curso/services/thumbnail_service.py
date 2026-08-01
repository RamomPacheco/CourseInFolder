from __future__ import annotations

from collections import deque
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink

from auto_curso.constants import get_data_dir
from auto_curso.models.video import VideoWithProgress

_THUMB_SIZE = QSize(160, 90)
_SEEK_MS = 1000
_MIN_SEEK_MS = 200
_TIMEOUT_MS = 5000


def get_thumbnail_dir() -> Path:
    thumb_dir = get_data_dir() / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    return thumb_dir


def thumbnail_path_for(video_id: UUID, file_size_bytes: int) -> Path:
    return get_thumbnail_dir() / f"{video_id}_{file_size_bytes}.jpg"


class ThumbnailService(QObject):
    """Gera miniaturas de vídeos em segundo plano, uma de cada vez, com cache em disco.

    Usa um QMediaPlayer/QVideoSink dedicado (sem widget visível), separado do
    player de reprodução real, para nunca competir por recursos com um vídeo
    que o usuário esteja assistindo de verdade.
    """

    thumbnail_ready = Signal(object, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._queue: deque[tuple[UUID, str, int]] = deque()
        self._queued_ids: set[UUID] = set()
        self._current: tuple[UUID, str, int] | None = None
        self._seek_done = False
        self._playback_active = False

        self._player = QMediaPlayer(self)
        self._sink = QVideoSink(self)
        self._player.setVideoSink(self._sink)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.errorOccurred.connect(self._on_error)

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(lambda: self._finish_current(success=False))

    def notify_playing(self, is_playing: bool) -> None:
        self._playback_active = is_playing
        if not is_playing:
            self._maybe_start_next()

    def request_many(self, videos: list[VideoWithProgress]) -> None:
        for video in videos:
            video_id = video.video.id
            size = video.video.file_size_bytes
            if video_id in self._queued_ids or (
                self._current is not None and self._current[0] == video_id
            ):
                continue
            cache_path = thumbnail_path_for(video_id, size)
            if cache_path.exists():
                self.thumbnail_ready.emit(video_id, str(cache_path))
                continue
            self._queued_ids.add(video_id)
            self._queue.append((video_id, video.full_path, size))
        self._maybe_start_next()

    def _maybe_start_next(self) -> None:
        if self._current is not None or self._playback_active or not self._queue:
            return
        self._current = self._queue.popleft()
        video_id, path, _size = self._current
        self._queued_ids.discard(video_id)
        self._seek_done = False
        self._timeout_timer.start(_TIMEOUT_MS)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    def _on_error(self, *_args: object) -> None:
        self._finish_current(success=False)

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if self._current is None:
            return
        if status in (
            QMediaPlayer.MediaStatus.InvalidMedia,
            QMediaPlayer.MediaStatus.NoMedia,
        ):
            self._finish_current(success=False)
        elif status == QMediaPlayer.MediaStatus.EndOfMedia and not self._seek_done:
            self._seek_done = True
            self._capture_frame()

    def _on_position_changed(self, position_ms: int) -> None:
        if self._current is None or self._seek_done:
            return
        duration_ms = self._player.duration()
        target = min(_SEEK_MS, duration_ms // 10) if duration_ms > 0 else _SEEK_MS
        target = max(target, _MIN_SEEK_MS)
        if position_ms >= target:
            self._seek_done = True
            self._capture_frame()

    def _capture_frame(self) -> None:
        frame = self._sink.videoFrame()
        if not frame.isValid():
            self._finish_current(success=False)
            return
        image: QImage = frame.toImage()
        if image.isNull():
            self._finish_current(success=False)
            return

        thumb = image.scaled(
            _THUMB_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        video_id, _path, size = self._current
        cache_path = thumbnail_path_for(video_id, size)
        if thumb.save(str(cache_path), "JPG", 80):
            self._finish_current(success=True, thumbnail_path=cache_path)
        else:
            self._finish_current(success=False)

    def _finish_current(self, success: bool, thumbnail_path: Path | None = None) -> None:
        if self._current is None:
            return
        video_id, _path, _size = self._current
        self._timeout_timer.stop()
        self._player.stop()
        self._current = None
        if success and thumbnail_path is not None:
            self.thumbnail_ready.emit(video_id, str(thumbnail_path))
        # Adia o próximo item para depois do QMediaPlayer terminar de
        # descarregar a mídia atual — trocar a fonte na mesma volta do
        # event loop pode gerar erro espúrio de abertura no backend FFmpeg.
        QTimer.singleShot(0, self._maybe_start_next)
