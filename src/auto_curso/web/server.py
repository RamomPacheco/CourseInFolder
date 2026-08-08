from __future__ import annotations

import mimetypes
import re
import threading
import webbrowser
from pathlib import Path, PurePosixPath
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from auto_curso.db.schema import initialize_database
from auto_curso.helpers import format_seconds
from auto_curso.repositories.course_repository import CourseRepository
from auto_curso.repositories.notes_repository import NotesRepository
from auto_curso.repositories.progress_repository import ProgressRepository
from auto_curso.services.course_service import CourseService

HOST = "127.0.0.1"
PORT = 8765
CHUNK_SIZE = 1024 * 1024
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Video Learning Tracker")

course_repo = CourseRepository()
progress_repo = ProgressRepository()
notes_repo = NotesRepository()
course_service = CourseService(course_repo, progress_repo, notes_repo=notes_repo)


class AddCourseBody(BaseModel):
    folder_path: str


class ProgressBody(BaseModel):
    position_seconds: float
    duration_seconds: float | None = None


class CompletedBody(BaseModel):
    completed: bool


class NoteBody(BaseModel):
    time_seconds: float
    text: str


class CourseNoteBody(BaseModel):
    text: str


def _course_summary_json(summary) -> dict:
    return {
        "id": str(summary.course.id),
        "name": summary.course.name,
        "folder_path": summary.course.folder_path,
        "added_at": summary.course.added_at.isoformat(),
        "total_videos": summary.total_videos,
        "completed_videos": summary.completed_videos,
        "progress_percent": summary.progress_percent,
    }


def _module_of(relative_path: str) -> str | None:
    parent = PurePosixPath(relative_path).parent
    return None if str(parent) == "." else str(parent)


def _video_json(vwp, favorites: set[UUID] | None = None) -> dict:
    return {
        "id": str(vwp.video.id),
        "file_name": vwp.video.file_name,
        "relative_path": vwp.video.relative_path,
        "module": _module_of(vwp.video.relative_path),
        "sort_order": vwp.video.sort_order,
        "duration_seconds": vwp.video.duration_seconds,
        "duration_label": format_seconds(vwp.video.duration_seconds or 0),
        "position_seconds": vwp.progress.position_seconds if vwp.progress else 0.0,
        "watched_percent": vwp.progress_percent,
        "is_completed": vwp.is_completed,
        "is_favorite": vwp.video.id in favorites if favorites is not None else False,
    }


@app.get("/api/courses")
def list_courses() -> list[dict]:
    return [_course_summary_json(s) for s in course_service.get_course_summaries()]


@app.post("/api/courses")
def add_course(body: AddCourseBody) -> dict:
    try:
        summary = course_service.add_course(body.folder_path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _course_summary_json(summary)


@app.post("/api/courses/{course_id}/refresh")
def refresh_course(course_id: UUID) -> dict:
    try:
        summary = course_service.refresh_course(course_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _course_summary_json(summary)


@app.delete("/api/courses/{course_id}")
def remove_course(course_id: UUID) -> dict:
    course_service.remove_course(course_id)
    return {"ok": True}


@app.get("/api/courses/{course_id}/videos")
def list_videos(course_id: UUID) -> list[dict]:
    try:
        videos = course_service.get_videos_with_progress(course_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    favorites = course_service.get_favorites(course_id)
    return [_video_json(v, favorites) for v in videos]


@app.get("/api/continue-watching")
def continue_watching() -> dict | None:
    result = course_service.get_continue_watching()
    if result is None:
        return None
    vwp, course = result
    data = _video_json(vwp)
    data["course_id"] = str(course.id)
    data["course_name"] = course.name
    return data


@app.post("/api/videos/{video_id}/progress")
def save_progress(video_id: UUID, body: ProgressBody) -> dict:
    try:
        progress = course_service.save_progress(
            video_id, body.position_seconds, body.duration_seconds
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "position_seconds": progress.position_seconds,
        "watched_percent": progress.watched_percent,
        "is_completed": progress.is_completed,
    }


@app.post("/api/videos/{video_id}/completed")
def set_completed(video_id: UUID, body: CompletedBody) -> dict:
    progress = course_service.set_video_completed(video_id, body.completed)
    return {
        "position_seconds": progress.position_seconds,
        "watched_percent": progress.watched_percent,
        "is_completed": progress.is_completed,
    }


@app.get("/api/videos/{video_id}/stream")
def stream_video(video_id: UUID, request: Request):
    video = course_repo.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado.")
    course = course_repo.get_by_id(video.course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

    full_path = Path(course.folder_path) / video.relative_path
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo de vídeo não encontrado.")

    file_size = full_path.stat().st_size
    media_type = mimetypes.guess_type(str(full_path))[0] or "application/octet-stream"
    range_header = request.headers.get("range")

    start, end = 0, file_size - 1
    status_code = 200
    if range_header:
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else file_size - 1
            end = min(end, file_size - 1)
            status_code = 206

    length = end - start + 1

    def iterfile():
        with open(full_path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {"Accept-Ranges": "bytes", "Content-Length": str(length)}
    if status_code == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    return StreamingResponse(
        iterfile(), status_code=status_code, media_type=media_type, headers=headers
    )


@app.post("/api/videos/{video_id}/favorite")
def toggle_favorite(video_id: UUID) -> dict:
    is_favorite = course_service.toggle_favorite(video_id)
    return {"is_favorite": is_favorite}


@app.get("/api/videos/{video_id}/notes")
def list_notes(video_id: UUID) -> list[dict]:
    notes = course_service.get_video_notes(video_id)
    return [
        {
            "id": str(n.id),
            "time_seconds": n.time_seconds,
            "time_label": format_seconds(n.time_seconds),
            "text": n.text,
        }
        for n in notes
    ]


@app.post("/api/videos/{video_id}/notes")
def add_note(video_id: UUID, body: NoteBody) -> dict:
    note = course_service.add_video_note(video_id, body.time_seconds, body.text)
    return {
        "id": str(note.id),
        "time_seconds": note.time_seconds,
        "time_label": format_seconds(note.time_seconds),
        "text": note.text,
    }


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: UUID) -> dict:
    course_service.delete_video_note(note_id)
    return {"ok": True}


@app.get("/api/courses/{course_id}/notes")
def get_course_note(course_id: UUID) -> dict:
    return {"text": course_service.get_course_note(course_id)}


@app.put("/api/courses/{course_id}/notes")
def save_course_note(course_id: UUID, body: CourseNoteBody) -> dict:
    course_service.save_course_note(course_id, body.text)
    return {"ok": True}


@app.get("/api/courses/{course_id}/materials")
def list_materials(course_id: UUID) -> list[dict]:
    try:
        materials = course_service.get_materials(course_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [
        {"name": m.file_name, "relative_path": m.relative_path, "size_bytes": m.file_size_bytes}
        for m in materials
    ]


@app.get("/api/courses/{course_id}/materials/download")
def download_material(course_id: UUID, path: str):
    course = course_repo.get_by_id(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

    root = Path(course.folder_path).resolve()
    full_path = (root / path).resolve()
    if root not in full_path.parents or not full_path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    return FileResponse(full_path, filename=full_path.name)


@app.get("/api/browse")
def browse(path: str | None = None) -> dict:
    base = Path(path).expanduser() if path else Path.home()
    try:
        base = base.resolve()
    except OSError:
        base = Path.home().resolve()
    if not base.is_dir():
        base = Path.home().resolve()

    entries = []
    try:
        for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            if child.name.startswith("."):
                continue
            try:
                if child.is_dir():
                    entries.append({"name": child.name, "path": str(child)})
            except OSError:
                continue
    except PermissionError:
        pass

    parent = str(base.parent) if base.parent != base else None
    return {"path": str(base), "parent": parent, "entries": entries}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


def main() -> None:
    import os
    import uvicorn

    initialize_database()
    if os.environ.get("AUTO_CURSO_OPEN_BROWSER", "1") != "0":
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
