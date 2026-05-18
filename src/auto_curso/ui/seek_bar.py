from __future__ import annotations

from typing import Callable

from auto_curso.helpers import format_seconds
from auto_curso.services.playback_service import PlaybackService
from auto_curso.ui.timeline_slider import TimelineSlider


class SeekBarController:
    """Timeline: arraste atualiza só a prévia; seek real ao soltar."""

    def __init__(
        self,
        slider: TimelineSlider,
        playback: PlaybackService,
        on_time_preview: Callable[[str], None] | None = None,
    ) -> None:
        self._slider = slider
        self._playback = playback
        self._on_time_preview = on_time_preview
        self._duration = 1.0
        self._user_seeking = False
        self._pending_position: float | None = None
        self._bookmark_seconds = 0.0

        slider.setMinimum(0)
        slider.setMaximum(1000)
        slider.setTracking(True)
        slider.setPageStep(50)
        slider.sliderPressed.connect(self._on_pressed)
        slider.sliderMoved.connect(self._on_moved)
        slider.sliderReleased.connect(self._on_released)
        slider.valueChanged.connect(self._on_value_changed)

    @property
    def is_seeking(self) -> bool:
        return self._user_seeking

    def set_bookmark(self, position_seconds: float, duration_seconds: float) -> None:
        self._bookmark_seconds = max(0.0, position_seconds)
        if duration_seconds > 0:
            self._slider.set_bookmark(position_seconds, duration_seconds)
        elif position_seconds <= 0:
            self._slider.clear_bookmark()

    def clear_bookmark(self) -> None:
        self._bookmark_seconds = 0.0
        self._slider.clear_bookmark()

    def set_position(self, position: float, duration: float) -> None:
        if self._user_seeking:
            return
        self._duration = max(0.001, duration)
        if self._bookmark_seconds > 0:
            self._slider.set_bookmark(self._bookmark_seconds, self._duration)
        value = int(position / self._duration * 1000)
        self._slider.blockSignals(True)
        self._slider.setValue(min(1000, max(0, value)))
        self._slider.blockSignals(False)

    def _position_from_value(self, value: int) -> float:
        return (value / 1000.0) * self._duration

    def _preview_time(self, position: float) -> None:
        if self._on_time_preview:
            self._on_time_preview(
                f"{format_seconds(position)} / {format_seconds(self._duration)}"
            )

    def _on_pressed(self) -> None:
        self._user_seeking = True
        self._playback.set_scrubbing(True)

    def _on_moved(self, value: int) -> None:
        pos = self._position_from_value(value)
        self._pending_position = pos
        self._preview_time(pos)

    def _on_released(self) -> None:
        pos = self._pending_position
        if pos is None:
            pos = self._position_from_value(self._slider.value())
        self._playback.set_scrubbing(False)
        self._playback.seek(pos)
        self._playback.flush_save()
        self._user_seeking = False
        self._pending_position = None
        self._preview_time(pos)

    def _on_value_changed(self, value: int) -> None:
        if self._slider.isSliderDown() and not self._user_seeking:
            self._on_pressed()
        if not self._user_seeking:
            return
        pos = self._position_from_value(value)
        self._pending_position = pos
        self._preview_time(pos)
