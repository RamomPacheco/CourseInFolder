from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from auto_curso.ui.pane_frame import CollapsedRail, PaneFrame

_SETTINGS_ORG = "auto_curso"
_SETTINGS_APP = "VideoLearningTracker"
_DEFAULT_SIZES = [260, 520, 420]
_MIN_SIZES = [180, 280, 320]


class SplitWorkspace(QWidget):
    """Três colunas redimensionáveis (arrastar divisores) com ocultar/mostrar."""

    PANE_COURSES = "courses"
    PANE_VIDEOS = "videos"
    PANE_PLAYER = "player"

    def __init__(
        self,
        courses_widget: QWidget,
        videos_widget: QWidget,
        player_widget: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)

        self._courses_pane = PaneFrame("Cursos", courses_widget)
        self._videos_pane = PaneFrame("Vídeos", videos_widget)
        self._player_pane = PaneFrame("Player", player_widget)

        self._panes: dict[str, PaneFrame] = {
            self.PANE_COURSES: self._courses_pane,
            self.PANE_VIDEOS: self._videos_pane,
            self.PANE_PLAYER: self._player_pane,
        }
        self._columns: dict[str, QWidget] = {}
        self._rails: dict[str, CollapsedRail] = {}
        self._saved_sizes: dict[str, int] = {}
        self._visible: dict[str, bool] = {
            self.PANE_COURSES: True,
            self.PANE_VIDEOS: True,
            self.PANE_PLAYER: True,
        }

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 6, 8, 6)
        toolbar.setSpacing(6)

        self._btn_courses = QPushButton("Cursos")
        self._btn_courses.setCheckable(True)
        self._btn_courses.setChecked(True)
        self._btn_courses.clicked.connect(
            lambda checked: self._toggle_from_toolbar(self.PANE_COURSES, checked)
        )

        self._btn_videos = QPushButton("Vídeos")
        self._btn_videos.setCheckable(True)
        self._btn_videos.setChecked(True)
        self._btn_videos.clicked.connect(
            lambda checked: self._toggle_from_toolbar(self.PANE_VIDEOS, checked)
        )

        self._btn_player = QPushButton("Player")
        self._btn_player.setCheckable(True)
        self._btn_player.setChecked(True)
        self._btn_player.clicked.connect(
            lambda checked: self._toggle_from_toolbar(self.PANE_PLAYER, checked)
        )

        toolbar.addWidget(self._btn_courses)
        toolbar.addWidget(self._btn_videos)
        toolbar.addWidget(self._btn_player)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setObjectName("mainSplitter")
        self._splitter.setHandleWidth(6)
        self._splitter.setChildrenCollapsible(False)

        for key, pane in self._panes.items():
            column, rail = self._wrap_column(pane)
            self._columns[key] = column
            self._rails[key] = rail
            rail.expand_requested.connect(lambda k=key: self.show_pane(k))
            pane.visibility_changed.connect(
                lambda visible, k=key: self._on_pane_visibility(k, visible)
            )
            self._splitter.addWidget(column)

        layout.addWidget(self._splitter, stretch=1)

        self._courses_pane.setMinimumWidth(_MIN_SIZES[0])
        self._videos_pane.setMinimumWidth(_MIN_SIZES[1])
        self._player_pane.setMinimumWidth(_MIN_SIZES[2])

        self._restore_layout()

    def _wrap_column(self, pane: PaneFrame) -> tuple[QWidget, CollapsedRail]:
        column = QWidget()
        row = QHBoxLayout(column)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        rail = CollapsedRail(pane._title_text)
        rail.hide()
        row.addWidget(rail)
        row.addWidget(pane, stretch=1)
        return column, rail

    def hide_pane(self, key: str) -> None:
        if not self._visible.get(key, True):
            return
        idx = self._pane_index(key)
        sizes = self._splitter.sizes()
        if idx < len(sizes):
            self._saved_sizes[key] = max(sizes[idx], _MIN_SIZES[idx])

        self._visible[key] = False
        if self._panes[key].isVisible():
            self._panes[key].hide()
        self._rails[key].show()

        new_sizes = self._splitter.sizes()
        if idx < len(new_sizes):
            freed = new_sizes[idx] - 32
            new_sizes[idx] = 32
            if freed > 0:
                target = self._next_visible_index(idx, 1, len(new_sizes))
                if target is None:
                    target = self._next_visible_index(idx, -1, len(new_sizes))
                if target is not None:
                    new_sizes[target] += freed
            self._splitter.setSizes(new_sizes)

        self._sync_toolbar_buttons()
        self._persist_layout()

    def show_pane(self, key: str) -> None:
        if self._visible.get(key, True):
            return
        self._visible[key] = True
        self._rails[key].hide()
        self._panes[key].show_pane()

        idx = self._pane_index(key)
        sizes = self._splitter.sizes()
        restore = self._saved_sizes.get(key, _DEFAULT_SIZES[idx])
        if idx < len(sizes):
            sizes[idx] = max(restore, _MIN_SIZES[idx])
            self._splitter.setSizes(sizes)

        self._sync_toolbar_buttons()
        self._persist_layout()

    def _toggle_from_toolbar(self, key: str, checked: bool) -> None:
        if checked:
            self.show_pane(key)
        else:
            self.hide_pane(key)

    def _on_pane_visibility(self, key: str, visible: bool) -> None:
        if visible:
            self.show_pane(key)
        else:
            self.hide_pane(key)

    def _pane_index(self, key: str) -> int:
        order = [self.PANE_COURSES, self.PANE_VIDEOS, self.PANE_PLAYER]
        return order.index(key)

    def _next_visible_index(self, idx: int, step: int, count: int) -> int | None:
        order = [self.PANE_COURSES, self.PANE_VIDEOS, self.PANE_PLAYER]
        i = idx + step
        while 0 <= i < count:
            if self._visible.get(order[i], True):
                return i
            i += step
        return None

    def _sync_toolbar_buttons(self) -> None:
        for key, btn in (
            (self.PANE_COURSES, self._btn_courses),
            (self.PANE_VIDEOS, self._btn_videos),
            (self.PANE_PLAYER, self._btn_player),
        ):
            btn.blockSignals(True)
            btn.setChecked(self._visible[key])
            btn.blockSignals(False)

    def _persist_layout(self) -> None:
        self._settings.setValue("splitter/sizes", self._splitter.sizes())
        for key in self._panes:
            self._settings.setValue(f"pane/{key}/visible", self._visible[key])

    def _restore_layout(self) -> None:
        sizes = self._settings.value("splitter/sizes")
        if sizes and len(sizes) == 3:
            restored = [max(int(s), _MIN_SIZES[i]) for i, s in enumerate(sizes)]
            self._splitter.setSizes(restored)
        else:
            self._splitter.setSizes(_DEFAULT_SIZES)

        for key in self._panes:
            visible = self._settings.value(f"pane/{key}/visible", True)
            if visible is False or str(visible).lower() == "false":
                self._visible[key] = True
                self.hide_pane(key)

        idx = self._pane_index(self.PANE_VIDEOS)
        sizes = self._splitter.sizes()
        if self._visible[self.PANE_VIDEOS] and idx < len(sizes) and sizes[idx] < _MIN_SIZES[1]:
            sizes[idx] = _DEFAULT_SIZES[1]
            self._splitter.setSizes(sizes)

        self._sync_toolbar_buttons()

    def persist_on_close(self) -> None:
        self._persist_layout()
