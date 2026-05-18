from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from auto_curso.db.schema import initialize_database
from auto_curso.services.course_service import CourseService
from auto_curso.services.playback_service import PlaybackService
from auto_curso.ui.main_window import MainWindow


def main() -> None:
    initialize_database()

    app = QApplication(sys.argv)
    app.setApplicationName("Video Learning Tracker")

    course_service = CourseService()
    playback_service = PlaybackService()

    app.aboutToQuit.connect(playback_service.flush_save)

    window = MainWindow(course_service, playback_service)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
