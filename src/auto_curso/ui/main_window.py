from __future__ import annotations

import time
from typing import Callable
from uuid import UUID

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
)

from auto_curso.constants import COMPLETION_THRESHOLD
from auto_curso.debug_log import debug_log
from auto_curso.models.course import CourseSummary
from auto_curso.models.video import VideoWithProgress
from auto_curso.services.course_service import CourseService
from auto_curso.services.playback_service import PlaybackService, PlaybackState
from auto_curso.ui import theme as t
from auto_curso.ui.course_sidebar import CourseSidebar
from auto_curso.ui.fullscreen_overlay import FullscreenOverlay
from auto_curso.ui.player_panel import PlayerPanel
from auto_curso.ui.split_workspace import SplitWorkspace
from auto_curso.ui.video_list import VideoListPanel


class _Worker(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.finished.emit(self._fn())
        except Exception as exc:
            self.error.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(
        self,
        course_service: CourseService,
        playback_service: PlaybackService,
    ) -> None:
        super().__init__()
        self._courses = course_service
        self._playback = playback_service
        self._summaries: dict[UUID, CourseSummary] = {}
        self._all_videos: list[VideoWithProgress] = []
        self._filtered_videos: list[VideoWithProgress] = []
        self._selected_video: VideoWithProgress | None = None
        self._workers: list[_Worker] = []
        self._fullscreen: FullscreenOverlay | None = None
        self._last_list_progress_update = 0.0

        self.setWindowTitle("Video Learning Tracker")
        self.resize(t.WINDOW_WIDTH, t.WINDOW_HEIGHT)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(t.STYLESHEET)

        self._sidebar = CourseSidebar(
            on_add_course=self._add_course,
            on_course_selected=self._on_course_selected,
        )
        self._video_list = VideoListPanel(on_video_double_click=self._play_video)
        self._video_list.set_toolbar_callbacks(
            on_refresh=self._refresh_course,
            on_remove=self._remove_course,
            on_filter=self._apply_filter,
            on_completion_changed=self._set_video_completed,
        )
        self._player = PlayerPanel(playback_service)
        self._player.set_fullscreen_handler(self._enter_fullscreen)

        self._workspace = SplitWorkspace(
            courses_widget=self._sidebar,
            videos_widget=self._video_list,
            player_widget=self._player,
        )
        self.setCentralWidget(self._workspace)

        self._playback.on_state_changed = self._on_playback_state
        self._playback.on_completed = self._on_playback_completed
        self._playback.on_progress_persisted = self._update_resume_markers

        self._load_courses()

    @property
    def _is_fullscreen(self) -> bool:
        return self._fullscreen is not None

    def closeEvent(self, event) -> None:
        if self._fullscreen:
            self._exit_fullscreen()
        self._workspace.persist_on_close()
        self._playback.flush_save()
        self._playback.dispose()
        for w in self._workers:
            w.quit()
            w.wait(2000)
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_F11:
            if self._is_fullscreen:
                self._exit_fullscreen()
            else:
                self._enter_fullscreen()
            event.accept()
            return
        if self._is_fullscreen:
            super().keyPressEvent(event)
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

    def _enter_fullscreen(self) -> None:
        if self._fullscreen:
            return
        self._fullscreen = FullscreenOverlay(
            playback=self._playback,
            video_widget=self._player.video_widget,
            on_exit=self._exit_fullscreen,
            on_play_video=self._play_video,
            on_completion_changed=self._set_video_completed,
        )
        if self._selected_video:
            self._fullscreen.set_title(self._selected_video.video.file_name)
        self._fullscreen.set_videos(self._filtered_videos)
        self._update_resume_markers()
        self._fullscreen.open()

    def _exit_fullscreen(self) -> None:
        if not self._fullscreen:
            return
        self._playback.flush_save()
        overlay = self._fullscreen
        self._fullscreen = None
        overlay.close_overlay()
        self._player.restore_video_widget()
        self.show()
        self.activateWindow()

    def _load_courses(self) -> None:
        self._run_async(self._courses.get_course_summaries, self._apply_courses)

    def _apply_courses(self, summaries: list[CourseSummary]) -> None:
        self._summaries = {s.course.id: s for s in summaries}
        self._sidebar.set_courses(summaries)
        if summaries:
            self._status(f"{len(summaries)} curso(s) carregado(s).")
            self._sidebar.select_course(summaries[0].course.id)
        else:
            self._status("Adicione uma pasta de vídeos para começar.")

    def _add_course(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Selecionar pasta do curso")
        if path:
            self._run_async(
                lambda: self._courses.add_course(path),
                self._on_course_added,
            )

    def _on_course_added(self, summary: CourseSummary) -> None:
        self._summaries[summary.course.id] = summary
        summaries = list(self._summaries.values())
        self._sidebar.set_courses(summaries)
        self._sidebar.select_course(summary.course.id)
        self._status(
            f'Curso "{summary.course.name}" adicionado com {summary.total_videos} vídeo(s).'
        )

    def _on_course_selected(self, course_id: UUID | None) -> None:
        if course_id is None:
            self._video_list.set_course_title(None)
            self._video_list.set_videos([])
            self._filtered_videos = []
            return
        summary = self._summaries.get(course_id)
        self._video_list.set_course_title(summary.course.name if summary else "?")
        self._load_videos_for_course(course_id)

    def _load_videos_for_course(self, course_id: UUID) -> None:
        self._status("Carregando vídeos...")
        self._run_async(
            lambda cid=course_id: self._courses.get_videos_with_progress(cid),
            lambda videos, cid=course_id: self._apply_videos(videos, cid),
        )

    def _apply_videos(self, videos: list[VideoWithProgress], course_id: UUID) -> None:
        if self._sidebar.get_selected_id() != course_id:
            return
        self._all_videos = videos
        self._apply_filter(self._video_list.get_filter())

    def _apply_filter(self, filter_name: str) -> None:
        if filter_name == "Pendentes":
            filtered = [v for v in self._all_videos if not v.is_completed]
        elif filter_name == "Concluídos":
            filtered = [v for v in self._all_videos if v.is_completed]
        else:
            filtered = self._all_videos

        self._filtered_videos = filtered
        self._video_list.set_videos(filtered)
        if self._fullscreen:
            self._fullscreen.set_videos(filtered)

        course_id = self._sidebar.get_selected_id()
        if course_id and (summary := self._summaries.get(course_id)):
            if filtered:
                self._status(f'{len(filtered)} vídeo(s) no curso "{summary.course.name}".')
            else:
                self._status("Nenhum vídeo neste filtro.")

    def _refresh_course(self) -> None:
        course_id = self._sidebar.get_selected_id()
        if not course_id:
            return

        def work():
            summary = self._courses.refresh_course(course_id)
            videos = self._courses.get_videos_with_progress(course_id)
            return summary, videos

        def done(result):
            summary, videos = result
            self._summaries[course_id] = summary
            self._sidebar.update_course(summary)
            self._all_videos = videos
            self._apply_filter(self._video_list.get_filter())
            self._status(f"Curso atualizado: {summary.total_videos} vídeo(s).")

        self._run_async(work, done)

    def _remove_course(self) -> None:
        course_id = self._sidebar.get_selected_id()
        if not course_id:
            return
        summary = self._summaries.get(course_id)
        name = summary.course.name if summary else "?"
        if (
            QMessageBox.question(
                self,
                "Remover curso",
                f'Remover o curso "{name}"?',
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        def work():
            self._courses.remove_course(course_id)
            return course_id

        def done(removed_id):
            self._summaries.pop(removed_id, None)
            self._sidebar.remove_course(removed_id)
            self._sidebar.set_courses(list(self._summaries.values()))
            self._status("Curso removido.")

        self._run_async(work, done)

    def _set_video_completed(self, video: VideoWithProgress, completed: bool) -> None:
        course_id = self._sidebar.get_selected_id()
        if not course_id:
            return

        # region agent log
        debug_log(
            "main_window.py:_set_video_completed",
            "toggle manual",
            {
                "video": video.video.file_name,
                "completed": completed,
                "model_completed_before": video.is_completed,
                "watched_pct": (
                    video.progress.watched_percent if video.progress else None
                ),
                "is_selected": bool(
                    self._selected_video
                    and self._selected_video.video.id == video.video.id
                ),
            },
            hypothesis_id="H1",
            run_id="post-fix",
        )
        # endregion

        progress = self._courses.set_video_completed(video.video.id, completed)
        video.progress = progress

        for item in self._all_videos:
            if item.video.id == video.video.id:
                item.progress = progress
                break

        if self._selected_video and self._selected_video.video.id == video.video.id:
            self._selected_video.progress = progress

        if (
            not completed
            and self._selected_video
            and self._selected_video.video.id == video.video.id
            and self._playback.has_media
        ):
            duration = self._playback.duration_seconds
            if duration > 0:
                threshold = duration * COMPLETION_THRESHOLD
                if self._playback.position_seconds >= threshold:
                    self._playback.seek(max(0.0, threshold - 1.0))
                    self._playback.flush_save()

        summary = self._courses.get_course_summary(course_id)
        self._summaries[course_id] = summary
        self._sidebar.update_course(summary)
        self._apply_filter(self._video_list.get_filter())

        if self._fullscreen:
            self._fullscreen.set_videos(self._filtered_videos)

        label = "marcado como concluído" if completed else "marcado como pendente"
        self._status(f'"{video.video.file_name}" {label}.')

    def _play_video(self, video: VideoWithProgress) -> None:
        self._selected_video = video
        self._player.set_now_playing(video.video.file_name)
        self._update_resume_markers()
        if self._fullscreen:
            self._fullscreen.set_title(video.video.file_name)
        try:
            self._playback.load_video(video)
            self._status(f"Reproduzindo: {video.video.file_name}")
        except Exception as exc:
            self._status(f"Erro ao reproduzir: {exc}")

    def _update_resume_markers(self) -> None:
        video = self._selected_video
        self._player.set_resume_marker(video)
        if self._fullscreen:
            self._fullscreen.set_resume_marker(video)

    def _on_playback_state(self, state: PlaybackState) -> None:
        self._player.update_state(
            state.position_seconds,
            state.duration_seconds,
            state.is_playing,
        )
        if self._fullscreen:
            self._fullscreen.update_state(
                state.position_seconds,
                state.duration_seconds,
                state.is_playing,
            )
        if not self._selected_video:
            return

        now = time.monotonic()
        is_completed = self._selected_video.is_completed
        # region agent log
        if state.watched_percent >= COMPLETION_THRESHOLD * 100 and not is_completed:
            debug_log(
                "main_window.py:_on_playback_state",
                "pct alto mas modelo pendente (sem override UI)",
                {
                    "video": self._selected_video.video.file_name,
                    "watched_percent": round(state.watched_percent, 1),
                    "model_completed": is_completed,
                },
                hypothesis_id="H1",
                run_id="post-fix",
            )
        # endregion
        if is_completed or (now - self._last_list_progress_update) >= 2.0:
            self._last_list_progress_update = now
            percent = 100.0 if is_completed else state.watched_percent
            self._video_list.update_video_progress(
                self._selected_video.video.id,
                percent,
                is_completed,
            )
            if self._fullscreen:
                self._fullscreen.update_progress(
                    self._selected_video.video.id,
                    percent,
                    is_completed,
                )

    def _on_playback_completed(self) -> None:
        self._update_resume_markers()
        course_id = self._sidebar.get_selected_id()
        if course_id and self._selected_video:
            try:
                if self._selected_video.progress:
                    self._selected_video.progress.is_completed = True
                    self._selected_video.progress.watched_percent = 100.0
                summary = self._courses.get_course_summary(course_id)
                self._summaries[course_id] = summary
                self._sidebar.update_course(summary)
                self._video_list.update_video_progress(
                    self._selected_video.video.id, 100.0, True
                )
                if self._fullscreen:
                    self._fullscreen.update_progress(
                        self._selected_video.video.id, 100.0, True
                    )
            except Exception:
                pass
        self._status("Vídeo concluído!")

    def _status(self, message: str) -> None:
        self._video_list.set_status(message)

    def _run_async(self, fn: Callable[[], object], on_success: Callable[[object], None]) -> None:
        worker = _Worker(fn)
        self._workers.append(worker)

        def cleanup() -> None:
            if worker in self._workers:
                self._workers.remove(worker)

        worker.finished.connect(on_success)
        worker.finished.connect(cleanup)
        worker.error.connect(lambda msg: (self._status(str(msg)), cleanup()))
        worker.start()
