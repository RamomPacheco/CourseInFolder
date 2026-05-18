from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from PySide6.QtCore import QThreadPool, QTimer, QUrl, QRunnable
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget

from auto_curso.constants import (
    COMPLETION_THRESHOLD,
    POSITION_SAVE_DEBOUNCE_MS,
    UI_UPDATE_INTERVAL_MS,
)
from auto_curso.models.progress import PlaybackProgress
from auto_curso.models.video import VideoWithProgress
from auto_curso.repositories.course_repository import CourseRepository
from auto_curso.repositories.progress_repository import ProgressRepository


@dataclass
class PlaybackState:
    position_seconds: float
    duration_seconds: float
    is_playing: bool
    watched_percent: float


class _SaveProgressTask(QRunnable):
    def __init__(self, repo: ProgressRepository, progress: PlaybackProgress) -> None:
        super().__init__()
        self._repo = repo
        self._progress = progress

    def run(self) -> None:
        self._repo.save(self._progress)


class PlaybackService:
    """Reprodução via QMediaPlayer (multimídia nativa do Qt)."""

    def __init__(
        self,
        progress_repo: ProgressRepository | None = None,
        course_repo: CourseRepository | None = None,
    ) -> None:
        self._progress = progress_repo or ProgressRepository()
        self._courses = course_repo or CourseRepository()
        self._player = QMediaPlayer()
        self._audio = QAudioOutput()
        self._player.setAudioOutput(self._audio)
        self._video_widget: QVideoWidget | None = None
        self._current: VideoWithProgress | None = None
        self._duration_ms = 0
        self._is_seeking = False
        self._scrubbing = False
        self._loading = False
        self._disposed = False
        self._awaiting_resume = False
        self._resume_at_ms = 0
        self._last_saved_signature: tuple | None = None

        self.on_state_changed: Callable[[PlaybackState], None] | None = None
        self.on_completed: Callable[[], None] | None = None
        self.on_progress_persisted: Callable[[], None] | None = None

        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(POSITION_SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self._save_debounced)

        self._ui_timer = QTimer()
        self._ui_timer.setInterval(UI_UPDATE_INTERVAL_MS)
        self._ui_timer.timeout.connect(self._notify_state)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

    @property
    def player(self) -> QMediaPlayer:
        return self._player

    @property
    def video_widget(self) -> QVideoWidget | None:
        return self._video_widget

    @property
    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    @property
    def has_media(self) -> bool:
        return self._current is not None

    @property
    def position_seconds(self) -> float:
        return self._player.position() / 1000.0

    @property
    def duration_seconds(self) -> float:
        return self._duration_ms / 1000.0 if self._duration_ms > 0 else 0.0

    @property
    def current_video(self) -> VideoWithProgress | None:
        return self._current

    def attach_video_widget(self, widget: QVideoWidget) -> None:
        self._video_widget = widget
        self._player.setVideoOutput(widget)

    def flush_save(self) -> None:
        self._save_timer.stop()
        self._persist_progress(sync=True)

    def load_video(self, video: VideoWithProgress) -> None:
        if self._video_widget is None:
            raise RuntimeError("Player não vinculado à janela.")

        self._loading = True
        self._ui_timer.stop()
        self._save_timer.stop()

        if self._current is not None:
            self._persist_progress(sync=False)

        if video.progress is None:
            stored = self._progress.get(video.video.id)
            if stored is not None:
                video.progress = stored

        self._current = video
        self._duration_ms = int((video.video.duration_seconds or 0) * 1000)
        self._awaiting_resume = False
        self._resume_at_ms = 0
        self._last_saved_signature = None

        if video.progress and not video.progress.is_completed:
            self._resume_at_ms = int(round(video.progress.position_seconds * 1000))
            self._awaiting_resume = self._resume_at_ms > 0

        self._player.stop()
        path = video.full_path.replace("\\", "/")
        self._player.setSource(QUrl.fromLocalFile(path))

        if not self._awaiting_resume:
            self._player.play()
            self._ui_timer.start()

        self._notify_state()
        self._loading = False

    def play(self) -> None:
        self._player.play()
        self._ui_timer.start()
        self._notify_state()

    def pause(self) -> None:
        self._player.pause()
        self._ui_timer.stop()
        self.flush_save()
        self._notify_state()

    def toggle_play_pause(self) -> None:
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def set_scrubbing(self, active: bool) -> None:
        self._scrubbing = active
        if active:
            self._ui_timer.stop()
        elif self.is_playing:
            self._ui_timer.start()
        if not active:
            self._schedule_save()

    def seek(self, position_seconds: float, preview_only: bool = False) -> None:
        duration_ms = self._duration_ms or self._player.duration()
        max_sec = duration_ms / 1000.0 if duration_ms > 0 else position_seconds
        clamped = max(0.0, min(position_seconds, max_sec))

        if preview_only:
            return

        self._is_seeking = True
        self._player.setPosition(int(round(clamped * 1000)))
        self._is_seeking = False
        if not self._scrubbing:
            self._schedule_save()
            self._notify_state()

    def seek_relative(self, delta_seconds: float) -> None:
        self.seek(self.position_seconds + delta_seconds)

    def set_playback_rate(self, rate: float) -> None:
        self._player.setPlaybackRate(rate)

    def _build_progress(self) -> PlaybackProgress | None:
        if self._current is None or self._disposed:
            return None

        position_ms = max(0, self._player.position())
        position = position_ms / 1000.0

        duration_ms = self._duration_ms or self._player.duration()
        if duration_ms <= 0 and self._current.video.duration_seconds:
            duration_ms = int(self._current.video.duration_seconds * 1000)

        if duration_ms > 0:
            duration = duration_ms / 1000.0
            percent = min(100.0, position / duration * 100)
            is_completed = position / duration >= COMPLETION_THRESHOLD
        else:
            if position_ms <= 0:
                return None
            percent = self._current.progress.watched_percent if self._current.progress else 0.0
            is_completed = False

        if is_completed:
            percent = 100.0
            position = 0.0

        return PlaybackProgress(
            video_id=self._current.video.id,
            position_seconds=0.0 if is_completed else position,
            is_completed=is_completed,
            watched_percent=percent,
            last_watched_at=datetime.now(timezone.utc),
        )

    def _persist_progress(self, sync: bool = False) -> None:
        progress = self._build_progress()
        if progress is None:
            return

        signature = (
            progress.video_id,
            round(progress.position_seconds, 1),
            progress.is_completed,
        )
        if signature == self._last_saved_signature and not sync:
            return

        self._last_saved_signature = signature
        self._current.progress = progress

        if duration_ms := self._duration_ms or self._player.duration():
            if self._current.video.duration_seconds is None and duration_ms > 0:
                self._current.video.duration_seconds = duration_ms / 1000.0
                if sync:
                    self._courses.update_video_duration(
                        self._current.video.id, duration_ms / 1000.0
                    )
                else:
                    vid = self._current.video.id
                    dur = duration_ms / 1000.0
                    QThreadPool.globalInstance().start(
                        _UpdateDurationTask(self._courses, vid, dur)
                    )

        if sync:
            self._progress.save(progress)
            if self.on_progress_persisted:
                self.on_progress_persisted()
        else:
            QThreadPool.globalInstance().start(
                _SaveProgressTask(self._progress, progress)
            )

        if progress.is_completed and self.on_completed:
            QTimer.singleShot(0, self.on_completed)

    def _save_debounced(self) -> None:
        self._persist_progress(sync=False)

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._ui_timer.stop()
        self._save_timer.stop()
        self.flush_save()
        self._player.stop()

    def _apply_resume(self) -> None:
        if not self._awaiting_resume or self._resume_at_ms <= 0:
            return
        self._player.setPosition(self._resume_at_ms)
        self._awaiting_resume = False
        self._player.play()
        self._ui_timer.start()

    def _on_position_changed(self, _position_ms: int) -> None:
        if self._is_seeking or self._scrubbing or self._loading:
            return
        self._schedule_save()

    def _on_duration_changed(self, duration_ms: int) -> None:
        if duration_ms > 0:
            self._duration_ms = duration_ms
            if self._current:
                self._current.video.duration_seconds = duration_ms / 1000.0
        if self._awaiting_resume:
            self._apply_resume()
        self._notify_state()

    def _on_playback_state_changed(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            if not self._scrubbing and not self._loading:
                self._ui_timer.start()
        else:
            self._ui_timer.stop()
            if state in (
                QMediaPlayer.PlaybackState.PausedState,
                QMediaPlayer.PlaybackState.StoppedState,
            ):
                self.flush_save()
        self._notify_state()

    def _on_media_status_changed(self, status) -> None:
        if self._awaiting_resume and status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self._apply_resume()
            return

        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._duration_ms = self._player.duration() or self._duration_ms
            self.flush_save()
            self._notify_state()

    def _schedule_save(self) -> None:
        self._save_timer.start()

    def _notify_state(self) -> None:
        if self._disposed or not self.on_state_changed or self._scrubbing:
            return
        duration_ms = self._duration_ms or self._player.duration()
        duration = duration_ms / 1000.0 if duration_ms > 0 else 0.0
        position = self.position_seconds
        percent = min(100.0, position / duration * 100) if duration > 0 else 0.0
        self.on_state_changed(
            PlaybackState(
                position_seconds=position,
                duration_seconds=duration,
                is_playing=self.is_playing,
                watched_percent=percent,
            )
        )


class _UpdateDurationTask(QRunnable):
    def __init__(self, repo: CourseRepository, video_id, duration: float) -> None:
        super().__init__()
        self._repo = repo
        self._video_id = video_id
        self._duration = duration

    def run(self) -> None:
        self._repo.update_video_duration(self._video_id, self._duration)
