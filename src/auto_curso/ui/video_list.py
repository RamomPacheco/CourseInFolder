from __future__ import annotations

from typing import Callable
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from auto_curso.debug_log import debug_log
from auto_curso.helpers import format_seconds
from auto_curso.models.video import VideoWithProgress


class VideoListPanel(QWidget):
    _COL_CHECK = 0
    _COL_TITLE = 1
    _COL_DURATION = 2
    _COL_PROGRESS = 3

    def __init__(
        self,
        on_video_double_click: Callable[[VideoWithProgress], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._play_callback = on_video_double_click
        self._completion_callback: Callable[[VideoWithProgress, bool], None] | None = None
        self._videos: list[VideoWithProgress] = []
        self._row_to_video: dict[int, VideoWithProgress] = {}
        self._updating_checks = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 12)
        layout.setSpacing(8)

        self._title = QLabel("Selecione um curso")
        self._title.setObjectName("title")
        layout.addWidget(self._title)

        self._status = QLabel("Adicione uma pasta de vídeos para começar.")
        self._status.setObjectName("muted")
        layout.addWidget(self._status)

        toolbar = QHBoxLayout()
        toolbar.addStretch()
        self._remove_btn = QPushButton("Remover")
        self._refresh_btn = QPushButton("Atualizar")
        self._filter = QComboBox()
        self._filter.addItems(["Todos", "Pendentes", "Concluídos"])
        toolbar.addWidget(self._filter)
        toolbar.addWidget(self._refresh_btn)
        toolbar.addWidget(self._remove_btn)
        layout.addLayout(toolbar)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["", "Vídeo", "Duração", "Progresso"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self._COL_TITLE, header.ResizeMode.Stretch)
        self._table.setColumnWidth(self._COL_CHECK, 40)
        self._table.setColumnWidth(self._COL_DURATION, 80)
        self._table.setColumnWidth(self._COL_PROGRESS, 200)
        self._table.cellDoubleClicked.connect(self._handle_double_click)
        self._table.cellChanged.connect(self._on_cell_changed)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self._table, stretch=1)

    def set_toolbar_callbacks(
        self,
        on_refresh: Callable[[], None],
        on_remove: Callable[[], None],
        on_filter: Callable[[str], None],
        on_completion_changed: Callable[[VideoWithProgress, bool], None] | None = None,
    ) -> None:
        self._completion_callback = on_completion_changed
        self._refresh_btn.clicked.connect(on_refresh)
        self._remove_btn.clicked.connect(on_remove)
        self._filter.currentTextChanged.connect(on_filter)

    def set_course_title(self, name: str | None) -> None:
        self._title.setText(name or "Selecione um curso")

    def set_status(self, message: str) -> None:
        self._status.setText(message)

    def get_filter(self) -> str:
        return self._filter.currentText()

    def set_videos(self, videos: list[VideoWithProgress]) -> None:
        self._videos = videos
        self._row_to_video.clear()
        self._table.setUpdatesEnabled(False)
        self._table.blockSignals(True)
        self._table.setRowCount(len(videos))

        for row, video in enumerate(videos):
            check = QTableWidgetItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            check.setCheckState(
                Qt.CheckState.Checked
                if video.is_completed
                else Qt.CheckState.Unchecked
            )
            check.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, self._COL_CHECK, check)

            duration = video.video.duration_seconds
            duration_text = format_seconds(duration) if duration else "—"
            progress_text = self._progress_label(video)

            title_item = QTableWidgetItem(video.video.file_name)
            self._table.setItem(row, self._COL_TITLE, title_item)
            self._table.setItem(row, self._COL_DURATION, QTableWidgetItem(duration_text))
            self._table.setItem(row, self._COL_PROGRESS, QTableWidgetItem(progress_text))
            self._row_to_video[row] = video

        self._table.blockSignals(False)
        self._table.setUpdatesEnabled(True)
        self._table.viewport().update()

    def update_video_progress(self, video_id: UUID, percent: float, is_completed: bool) -> None:
        for row, video in self._row_to_video.items():
            if video.video.id != video_id:
                continue
            self._updating_checks = True
            check = self._table.item(row, self._COL_CHECK)
            if check:
                check.setCheckState(
                    Qt.CheckState.Checked
                    if is_completed
                    else Qt.CheckState.Unchecked
                )
            if video.progress:
                video.progress.watched_percent = percent
                video.progress.is_completed = is_completed
            self._table.item(row, self._COL_PROGRESS).setText(self._progress_label(video))
            self._updating_checks = False
            break

    def _progress_label(self, video: VideoWithProgress) -> str:
        if video.is_completed:
            return "Concluído"
        if video.progress and video.progress.position_seconds > 0:
            stopped = format_seconds(video.progress.position_seconds)
            return f"{video.progress_percent:.0f}% · parou em {stopped}"
        return f"{video.progress_percent:.0f}%"

    def _on_cell_changed(self, row: int, column: int) -> None:
        if column != self._COL_CHECK or self._updating_checks:
            return
        video = self._row_to_video.get(row)
        if not video or not self._completion_callback:
            return
        check = self._table.item(row, self._COL_CHECK)
        if not check:
            return
        completed = check.checkState() == Qt.CheckState.Checked
        # region agent log
        debug_log(
            "video_list.py:_on_cell_changed",
            "checkbox clicada",
            {
                "row": row,
                "completed": completed,
                "model_completed": video.is_completed,
            },
            hypothesis_id="H2",
            run_id="post-fix",
        )
        # endregion
        self._completion_callback(video, completed)

    def _handle_double_click(self, row: int, col: int) -> None:
        if col == self._COL_CHECK:
            return
        video = self._row_to_video.get(row)
        if video:
            self._play_callback(video)
