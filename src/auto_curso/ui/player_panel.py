from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from auto_curso.models.video import VideoWithProgress

from auto_curso.helpers import format_seconds
from auto_curso.services.playback_service import PlaybackService
from auto_curso.ui import theme as t
from auto_curso.ui.seek_bar import SeekBarController
from auto_curso.ui.timeline_slider import TimelineSlider


class PlayerPanel(QFrame):
    """Painel de vídeo à direita (modo janela)."""

    def __init__(self, playback: PlaybackService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("player")
        self.setMinimumWidth(t.PLAYER_MIN_WIDTH)
        self._playback = playback
        self._duration = 1.0
        self._resume_marker_sec = 0.0
        self._on_enter_fullscreen: Callable[[], None] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self._title = QLabel("Nenhum vídeo selecionado")
        font = self._title.font()
        font.setBold(True)
        self._title.setFont(font)
        header.addWidget(self._title, stretch=1)

        self._fullscreen_btn = QPushButton("⛶")
        self._fullscreen_btn.setToolTip("Tela cheia (F11)")
        self._fullscreen_btn.setFixedSize(36, 36)
        self._fullscreen_btn.clicked.connect(self._request_fullscreen)
        header.addWidget(self._fullscreen_btn)
        layout.addLayout(header)

        self._video_container = QWidget()
        self._video_container.setStyleSheet(
            "background-color: black; border-radius: 8px;"
        )
        container_layout = QVBoxLayout(self._video_container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        self._video_widget = QVideoWidget()
        self._video_widget.setMinimumHeight(280)
        container_layout.addWidget(self._video_widget)
        playback.attach_video_widget(self._video_widget)
        layout.addWidget(self._video_container, stretch=1)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._play_btn = QPushButton("▶")
        self._play_btn.setObjectName("accent")
        self._play_btn.setFixedSize(40, 40)
        self._play_btn.clicked.connect(self._playback.toggle_play_pause)
        controls.addWidget(self._play_btn)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setObjectName("muted")
        self._time_label.setFixedWidth(110)

        self._seek = TimelineSlider(Qt.Orientation.Horizontal)
        self._seek_bar = SeekBarController(
            self._seek,
            playback,
            on_time_preview=self._time_label.setText,
        )
        controls.addWidget(self._seek, stretch=1)
        controls.addWidget(self._time_label)

        back_btn = QPushButton("-10s")
        back_btn.clicked.connect(lambda: playback.seek_relative(-10))
        controls.addWidget(back_btn)

        fwd_btn = QPushButton("+10s")
        fwd_btn.clicked.connect(lambda: playback.seek_relative(10))
        controls.addWidget(fwd_btn)

        self._rate = QComboBox()
        self._rate.addItems(["1x", "1.25x", "1.5x"])
        self._rate.setFixedWidth(72)
        self._rate.currentTextChanged.connect(self._on_rate_changed)
        controls.addWidget(self._rate)

        layout.addLayout(controls)

    @property
    def video_widget(self) -> QVideoWidget:
        return self._video_widget

    @property
    def video_container(self) -> QWidget:
        return self._video_container

    def set_fullscreen_handler(self, handler: Callable[[], None]) -> None:
        self._on_enter_fullscreen = handler

    def restore_video_widget(self) -> None:
        layout = self._video_container.layout()
        if self._video_widget.parent() is not self._video_container:
            self._video_widget.setParent(self._video_container)
            layout.addWidget(self._video_widget)
        self._playback.attach_video_widget(self._video_widget)
        self._video_widget.show()

    def set_now_playing(self, title: str) -> None:
        self._title.setText(title)

    def set_resume_marker(self, video: VideoWithProgress | None) -> None:
        self._resume_marker_sec = 0.0
        if (
            video
            and video.progress
            and not video.progress.is_completed
            and video.progress.position_seconds > 0
        ):
            self._resume_marker_sec = video.progress.position_seconds
        self._apply_bookmark(self._duration)

    def _apply_bookmark(self, duration: float) -> None:
        if self._resume_marker_sec > 0 and duration > 0:
            self._seek_bar.set_bookmark(self._resume_marker_sec, duration)
        else:
            self._seek_bar.clear_bookmark()

    def update_state(self, position: float, duration: float, is_playing: bool) -> None:
        self._duration = max(0.001, duration)
        self._play_btn.setText("⏸" if is_playing else "▶")
        if not self._seek_bar.is_seeking:
            self._time_label.setText(
                f"{format_seconds(position)} / {format_seconds(duration)}"
            )
            self._apply_bookmark(duration)
            self._seek_bar.set_position(position, duration)

    def _request_fullscreen(self) -> None:
        if self._on_enter_fullscreen:
            self._on_enter_fullscreen()

    def _on_rate_changed(self, value: str) -> None:
        rates = {"1x": 1.0, "1.25x": 1.25, "1.5x": 1.5}
        self._playback.set_playback_rate(rates.get(value, 1.0))
