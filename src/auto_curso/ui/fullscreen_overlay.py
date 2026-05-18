from __future__ import annotations

from typing import Callable
from uuid import UUID

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from auto_curso.helpers import format_seconds
from auto_curso.models.video import VideoWithProgress
from auto_curso.services.playback_service import PlaybackService
from auto_curso.ui import theme as t
from auto_curso.ui.seek_bar import SeekBarController
from auto_curso.ui.timeline_slider import TimelineSlider

_HIDE_MS = 2500


class FullscreenOverlay(QWidget):
    """Tela cheia com timeline auto-oculta e lista de vídeos à direita."""

    def __init__(
        self,
        playback: PlaybackService,
        video_widget: QVideoWidget,
        on_exit: Callable[[], None],
        on_play_video: Callable[[VideoWithProgress], None],
        on_completion_changed: Callable[[VideoWithProgress, bool], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._playback = playback
        self._video_widget = video_widget
        self._on_exit = on_exit
        self._on_play_video = on_play_video
        self._on_completion_changed = on_completion_changed
        self._videos: list[VideoWithProgress] = []
        self._row_to_video: dict[int, VideoWithProgress] = {}
        self._duration = 1.0
        self._resume_marker_sec = 0.0
        self._controls_visible = True
        self._updating_checks = False

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setStyleSheet(f"background-color: black; color: {t.TEXT_PRIMARY};")

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._video_area = QWidget()
        self._video_area.setMouseTracking(True)
        self._video_area.setStyleSheet("background-color: black;")
        video_layout = QVBoxLayout(self._video_area)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(0)

        self._video_container = QWidget()
        self._video_container.setMouseTracking(True)
        container_layout = QVBoxLayout(self._video_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.addWidget(self._video_container, stretch=1)

        self._exit_btn = QPushButton("⤢")
        self._exit_btn.setToolTip("Sair da tela cheia (F11)")
        self._exit_btn.setFixedSize(44, 44)
        self._exit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._exit_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: rgba(0, 0, 0, 160);
                color: white;
                border: none;
                border-radius: 22px;
                font-size: 20px;
            }}
            QPushButton:hover {{
                background-color: {t.ACCENT};
            }}
            """
        )
        self._exit_btn.clicked.connect(self._exit)
        self._exit_btn.setParent(self._video_area)
        self._exit_btn.raise_()

        self._controls = QWidget(self._video_area)
        self._controls.setMouseTracking(True)
        self._controls.setStyleSheet(
            "background-color: rgba(13, 13, 20, 210); border-top: 1px solid #2A2A3E;"
        )
        controls_layout = QVBoxLayout(self._controls)
        controls_layout.setContentsMargins(20, 12, 20, 16)
        controls_layout.setSpacing(10)

        self._fs_title = QLabel("")
        self._fs_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        controls_layout.addWidget(self._fs_title)

        row = QHBoxLayout()
        row.setSpacing(10)

        self._play_btn = QPushButton("▶")
        self._play_btn.setObjectName("accent")
        self._play_btn.setFixedSize(40, 40)
        self._play_btn.clicked.connect(self._playback.toggle_play_pause)
        row.addWidget(self._play_btn)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setFixedWidth(110)
        self._time_label.setStyleSheet(f"color: {t.TEXT_SECONDARY};")

        self._seek = TimelineSlider(Qt.Orientation.Horizontal)
        self._seek_bar = SeekBarController(
            self._seek,
            playback,
            on_time_preview=self._time_label.setText,
        )
        row.addWidget(self._seek, stretch=1)
        row.addWidget(self._time_label)

        for text, delta in (("-10s", -10), ("+10s", 10)):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _, d=delta: self._playback.seek_relative(d))
            row.addWidget(btn)

        controls_layout.addLayout(row)
        video_layout.addWidget(self._controls)

        root.addWidget(self._video_area, stretch=1)

        self._sidebar = QFrame()
        self._sidebar.setFixedWidth(300)
        self._sidebar.setStyleSheet(
            f"background-color: {t.BG_SIDEBAR}; border-left: 1px solid {t.BORDER};"
        )
        sidebar_layout = QVBoxLayout(self._sidebar)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)

        header = QHBoxLayout()
        header.addWidget(QLabel("Vídeos"))
        header.addStretch()
        self._hide_list_btn = QPushButton("◀")
        self._hide_list_btn.setFixedSize(32, 32)
        self._hide_list_btn.setToolTip("Ocultar lista")
        self._hide_list_btn.clicked.connect(self._toggle_sidebar)
        header.addWidget(self._hide_list_btn)
        sidebar_layout.addLayout(header)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_list_double_click)
        self._list.itemChanged.connect(self._on_list_item_changed)
        sidebar_layout.addWidget(self._list)

        self._show_list_btn = QPushButton("▶")
        self._show_list_btn.setFixedSize(36, 72)
        self._show_list_btn.setToolTip("Mostrar lista de vídeos")
        self._show_list_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: rgba(0, 0, 0, 160);
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }}
            QPushButton:hover {{ background-color: {t.ACCENT}; }}
            """
        )
        self._show_list_btn.clicked.connect(self._toggle_sidebar)
        self._show_list_btn.setParent(self._video_area)
        self._show_list_btn.hide()

        root.addWidget(self._sidebar)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_controls)

        self._sidebar_visible = True

    def open(self) -> None:
        self._video_widget.setParent(self._video_container)
        self._video_container.layout().addWidget(self._video_widget)
        self._playback.attach_video_widget(self._video_widget)
        self.showFullScreen()
        self._position_overlays()
        self._show_controls()

    def close_overlay(self) -> None:
        self._hide_timer.stop()
        self.hide()
        self.deleteLater()

    def set_title(self, title: str) -> None:
        self._fs_title.setText(title)

    def set_videos(self, videos: list[VideoWithProgress]) -> None:
        self._videos = videos
        self._row_to_video.clear()
        self._list.blockSignals(True)
        self._list.clear()
        for row, video in enumerate(videos):
            item = QListWidgetItem(self._list_label(video))
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
            )
            item.setCheckState(
                Qt.CheckState.Checked
                if video.is_completed
                else Qt.CheckState.Unchecked
            )
            self._list.addItem(item)
            self._row_to_video[row] = video
        self._list.blockSignals(False)

    def update_progress(self, video_id: UUID, percent: float, is_completed: bool) -> None:
        for row, video in self._row_to_video.items():
            if video.video.id != video_id:
                continue
            if video.progress:
                video.progress.watched_percent = percent
                video.progress.is_completed = is_completed
            item = self._list.item(row)
            if not item:
                break
            self._updating_checks = True
            item.setCheckState(
                Qt.CheckState.Checked
                if is_completed
                else Qt.CheckState.Unchecked
            )
            item.setText(self._list_label(video))
            self._updating_checks = False
            break

    @staticmethod
    def _list_label(video: VideoWithProgress) -> str:
        if video.is_completed:
            return video.video.file_name
        if video.progress and video.progress.position_seconds > 0:
            stopped = format_seconds(video.progress.position_seconds)
            return f"{video.video.file_name}  ({video.progress_percent:.0f}% · {stopped})"
        return f"{video.video.file_name}  ({video.progress_percent:.0f}%)"

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

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_overlays()

    def mouseMoveEvent(self, event) -> None:
        self._show_controls()
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
            self._exit()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Space:
            self._playback.toggle_play_pause()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Left:
            self._playback.seek_relative(-10)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Right:
            self._playback.seek_relative(10)
            event.accept()
            return
        super().keyPressEvent(event)

    def _position_overlays(self) -> None:
        w, h = self._video_area.width(), self._video_area.height()
        self._exit_btn.move(max(12, w - 56), 12)
        ctrl_h = self._controls.sizeHint().height()
        self._controls.setGeometry(0, max(0, h - ctrl_h), w, ctrl_h)
        if not self._sidebar_visible:
            self._show_list_btn.move(max(0, w - 40), h // 2 - 36)

    def _show_controls(self) -> None:
        if not self._controls_visible:
            self._controls.show()
            self._exit_btn.show()
            self._controls_visible = True
        self._hide_timer.start(_HIDE_MS)

    def _hide_controls(self) -> None:
        self._controls.hide()
        self._exit_btn.hide()
        self._controls_visible = False

    def _toggle_sidebar(self) -> None:
        self._sidebar_visible = not self._sidebar_visible
        self._sidebar.setVisible(self._sidebar_visible)
        self._show_list_btn.setVisible(not self._sidebar_visible)
        self._hide_list_btn.setText("◀")
        if not self._sidebar_visible:
            self._position_overlays()

    def _exit(self) -> None:
        self._on_exit()

    def _on_list_double_click(self, item: QListWidgetItem) -> None:
        row = self._list.row(item)
        video = self._row_to_video.get(row)
        if video:
            self._on_play_video(video)

    def _on_list_item_changed(self, item: QListWidgetItem) -> None:
        if self._updating_checks:
            return
        row = self._list.row(item)
        video = self._row_to_video.get(row)
        if not video or not self._on_completion_changed:
            return
        completed = item.checkState() == Qt.CheckState.Checked
        self._on_completion_changed(video, completed)
