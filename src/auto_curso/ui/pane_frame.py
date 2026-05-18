from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from auto_curso.ui import theme as t


class PaneFrame(QFrame):
    """Painel com título e botão para ocultar (canto superior direito)."""

    visibility_changed = Signal(bool)

    def __init__(self, title: str, content: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title_text = title
        self._content = content
        self._visible = True

        self.setObjectName("paneFrame")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("paneHeader")
        header.setFixedHeight(36)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 4, 8, 4)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("paneTitle")
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        self._hide_btn = QPushButton("◀")
        self._hide_btn.setFixedSize(28, 28)
        self._hide_btn.setToolTip(f"Ocultar painel «{title}»")
        self._hide_btn.clicked.connect(self.hide_pane)
        header_layout.addWidget(self._hide_btn)

        layout.addWidget(header)
        layout.addWidget(content, stretch=1)

    def hide_pane(self) -> None:
        if not self._visible:
            return
        self._visible = False
        self.hide()
        self.visibility_changed.emit(False)

    def show_pane(self) -> None:
        if self._visible:
            return
        self._visible = True
        self.setVisible(True)
        self.visibility_changed.emit(True)

    def is_pane_visible(self) -> bool:
        return self._visible


class CollapsedRail(QFrame):
    """Faixa estreita com botão para reexibir um painel oculto."""

    expand_requested = Signal()

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(32)
        self.setObjectName("collapsedRail")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)

        btn = QPushButton("▶")
        btn.setFixedSize(24, 48)
        btn.setToolTip(f"Mostrar «{title}»")
        btn.clicked.connect(self.expand_requested.emit)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
