from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygon
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider

_BOOKMARK_COLOR = QColor("#F4D03F")
_BOOKMARK_WIDTH = 3


class TimelineSlider(QSlider):
    """Slider de timeline com marcador da posição salva (onde parou)."""

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None) -> None:
        super().__init__(orientation, parent)
        self._bookmark_ratio = -1.0
        self.setMinimumHeight(22)

    def set_bookmark(self, position_seconds: float, duration_seconds: float) -> None:
        if duration_seconds <= 0 or position_seconds <= 0:
            self.clear_bookmark()
            return
        self._bookmark_ratio = min(1.0, max(0.0, position_seconds / duration_seconds))
        self.setToolTip(
            f"Marcador: parou em {self._format_time(position_seconds)} · "
            "arraste para buscar"
        )
        self.update()

    def clear_bookmark(self) -> None:
        self._bookmark_ratio = -1.0
        self.setToolTip("Arraste ou clique para avançar/retroceder")
        self.update()

    def _groove_rect(self):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        return self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            opt,
            QStyle.SubControl.SC_SliderGroove,
            self,
        )

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._bookmark_ratio < 0:
            return

        groove = self._groove_rect()
        if not groove.isValid() or groove.width() <= 0:
            return

        x = groove.left() + int(self._bookmark_ratio * groove.width())
        top = groove.top() - 2
        bottom = groove.bottom() + 2

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(_BOOKMARK_COLOR, _BOOKMARK_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(x, top, x, bottom)

        painter.setBrush(_BOOKMARK_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(
            QPolygon(
                [
                    QPoint(x - 5, top),
                    QPoint(x + 5, top),
                    QPoint(x, top - 7),
                ]
            )
        )
        painter.end()

    @staticmethod
    def _format_time(seconds: float) -> str:
        total = int(seconds)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
