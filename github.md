repo: RamomPacheco/CourseInFolder
branch: master
## Last sync
date: 2026-08-08T15:38:16Z

### Updated in this project
- Built CourseVault.dc.html: web prototype modeled on the Python app's domain (Course = folder, Video = file with progress/duration, 95% auto-complete threshold, refresh/rescan, Todos/Pendentes/Concluídos filters).
- Added web-only capabilities beyond the source app: File System Access API folder picker (with demo-mode fallback), per-video timestamped notes, per-course notes, favorites, playback speed, materials tab, "continuar assistindo" dashboard, search.

## Screen map
| Project screen | Repo files |
| --- | --- |
| Library grid + continue watching | src/auto_curso/models/course.py, services/course_service.py (CourseSummary/progress_percent) |
| Player sidebar (filters, favorites, refresh) | src/auto_curso/ui/course_sidebar.py, ui/video_list.py, services/course_service.py (refresh_course, set_video_completed) |
| Video player controls (seek, speed) | src/auto_curso/ui/player_panel.py, ui/seek_bar.py, ui/timeline_slider.py, constants.py (COMPLETION_THRESHOLD), helpers.py (format_seconds) |
| Progress/completion model | src/auto_curso/models/progress.py, models/video.py |
