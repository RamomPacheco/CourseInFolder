from __future__ import annotations

from typing import Callable
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from auto_curso.models.course import CourseSummary
from auto_curso.ui import theme as t


class CourseSidebar(QFrame):
    def __init__(
        self,
        on_add_course: Callable[[], None],
        on_course_selected: Callable[[UUID | None], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setMinimumWidth(180)
        self._on_course_selected = on_course_selected
        self._cards: dict[UUID, _CourseCard] = {}
        self._selected_id: UUID | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Cursos")
        title.setObjectName("title")
        layout.addWidget(title)

        add_btn = QPushButton("+ Adicionar curso")
        add_btn.setObjectName("accent")
        add_btn.clicked.connect(on_add_course)
        layout.addWidget(add_btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(8)
        self._scroll_layout.addStretch()
        scroll.setWidget(self._scroll_content)
        layout.addWidget(scroll, stretch=1)

    def set_courses(self, summaries: list[CourseSummary]) -> None:
        while self._scroll_layout.count() > 1:
            item = self._scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        for summary in summaries:
            card = _CourseCard(summary, self._select_course)
            self._scroll_layout.insertWidget(self._scroll_layout.count() - 1, card)
            self._cards[summary.course.id] = card

        if not summaries:
            self._selected_id = None
            self._on_course_selected(None)

    def update_course(self, summary: CourseSummary) -> None:
        card = self._cards.get(summary.course.id)
        if card:
            card.update_summary(summary)

    def select_course(self, course_id: UUID) -> None:
        self._select_course(course_id)

    def remove_course(self, course_id: UUID) -> None:
        card = self._cards.pop(course_id, None)
        if card:
            self._scroll_layout.removeWidget(card)
            card.deleteLater()
        if self._selected_id == course_id:
            self._selected_id = None

    def get_selected_id(self) -> UUID | None:
        return self._selected_id

    def _select_course(self, course_id: UUID) -> None:
        self._selected_id = course_id
        for cid, card in self._cards.items():
            card.set_selected(cid == course_id)
        self._on_course_selected(course_id)


class _CourseCard(QFrame):
    def __init__(
        self,
        summary: CourseSummary,
        on_click: Callable[[UUID], None],
    ) -> None:
        super().__init__()
        self.setObjectName("courseCard")
        self.setProperty("selected", False)
        self._course_id = summary.course.id
        self._on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        self._name = QLabel(summary.course.name)
        self._name.setWordWrap(True)
        font = self._name.font()
        font.setBold(True)
        self._name.setFont(font)
        layout.addWidget(self._name)

        self._progress_text = QLabel(self._label(summary))
        self._progress_text.setObjectName("muted")
        layout.addWidget(self._progress_text)

        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setMaximum(100)
        self._bar.setValue(int(summary.progress_percent))
        layout.addWidget(self._bar)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self._course_id)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def update_summary(self, summary: CourseSummary) -> None:
        self._progress_text.setText(self._label(summary))
        self._bar.setValue(int(summary.progress_percent))

    @staticmethod
    def _label(summary: CourseSummary) -> str:
        if summary.total_videos == 0:
            return "Nenhum vídeo"
        return f"{summary.completed_videos}/{summary.total_videos} concluídos"
