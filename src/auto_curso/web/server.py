from __future__ import annotations

import asyncio
import mimetypes
import re
import shutil
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from auto_curso.constants import (
    MAX_COVER_SIZE_BYTES,
    MAX_UPLOAD_SIZE_BYTES,
    MAX_VIDEO_UPLOAD_SIZE_BYTES,
    PURGE_INTERVAL_SECONDS,
    VIDEO_EXTENSIONS,
    get_course_cover_dir,
    get_manual_video_dir,
)
from auto_curso.db.schema import initialize_database
from auto_curso.helpers import format_seconds
from auto_curso.repositories.course_repository import CourseRepository
from auto_curso.repositories.materials_repository import MaterialsRepository
from auto_curso.repositories.notes_repository import NotesRepository
from auto_curso.repositories.progress_repository import ProgressRepository
from auto_curso.services.course_service import CourseService

HOST = "127.0.0.1"
PORT = 8765
CHUNK_SIZE = 1024 * 1024
STATIC_DIR = Path(__file__).parent / "static"

course_repo = CourseRepository()
progress_repo = ProgressRepository()
notes_repo = NotesRepository()
uploads_repo = MaterialsRepository()
course_service = CourseService(
    course_repo, progress_repo, notes_repo=notes_repo, uploads_repo=uploads_repo
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida do app: garante o banco e roda a purga de soft-deletes em background.

    No startup, cria o banco (se necessário) e dispara uma tarefa
    assíncrona que chama `course_service.purge_expired_soft_deletes()`
    a cada `PURGE_INTERVAL_SECONDS`, até o shutdown, quando a tarefa é
    cancelada de forma limpa.

    Args:
        app (FastAPI): A aplicação FastAPI (exigido pela assinatura do
            gerenciador de contexto de lifespan, não usado diretamente aqui).
    """
    initialize_database()
    stop_event = asyncio.Event()

    async def purge_loop() -> None:
        """Roda a purga de itens soft-deletados em loop até `stop_event` ser sinalizado."""
        while not stop_event.is_set():
            await asyncio.to_thread(course_service.purge_expired_soft_deletes)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=PURGE_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass

    task = asyncio.create_task(purge_loop())
    yield
    stop_event.set()
    task.cancel()


app = FastAPI(title="Video Learning Tracker", lifespan=lifespan)


class AddCourseBody(BaseModel):
    """Corpo de `POST /api/courses`: caminho da pasta local a cadastrar."""

    folder_path: str


class UpdateCourseBody(BaseModel):
    """Corpo de `PUT /api/courses/{course_id}`: novo nome e descrição do curso."""

    name: str
    description: str | None = None


class ProgressBody(BaseModel):
    """Corpo de `POST /api/videos/{video_id}/progress`: posição atual reportada pelo player."""

    position_seconds: float
    duration_seconds: float | None = None


class CompletedBody(BaseModel):
    """Corpo de `POST /api/videos/{video_id}/completed`: novo estado de conclusão."""

    completed: bool


class UpdateVideoBody(BaseModel):
    """Corpo de `PUT /api/videos/{video_id}`: novo título de exibição e/ou posição na playlist."""

    display_title: str | None = None
    sort_order: int | None = None


class NoteBody(BaseModel):
    """Corpo de `POST /api/videos/{video_id}/notes`: nova anotação a criar."""

    time_seconds: float
    text: str


class UpdateNoteBody(BaseModel):
    """Corpo de `PUT /api/notes/{note_id}`: novo texto da anotação."""

    text: str


class CourseNoteBody(BaseModel):
    """Corpo de `PUT /api/courses/{course_id}/notes`: novo texto das notas gerais do curso."""

    text: str


class RenameMaterialBody(BaseModel):
    """Corpo de `PUT /api/materials/{material_id}`: novo nome de exibição do material."""

    file_name: str


def _course_summary_json(summary) -> dict:
    """Serializa um `CourseSummary` para o formato JSON consumido pelo frontend.

    Args:
        summary (CourseSummary): Resumo do curso vindo do serviço.

    Returns:
        dict: Representação JSON-serializável do curso.
    """
    return {
        "id": str(summary.course.id),
        "name": summary.course.name,
        "folder_path": summary.course.folder_path,
        "added_at": summary.course.added_at.isoformat(),
        "description": summary.course.description,
        "cover_url": f"/api/courses/{summary.course.id}/cover" if summary.course.cover_stored_name else None,
        "total_videos": summary.total_videos,
        "completed_videos": summary.completed_videos,
        "progress_percent": summary.progress_percent,
    }


def _module_of(relative_path: str) -> str | None:
    """Deriva o "módulo" (subpasta) de exibição a partir do caminho relativo de um vídeo.

    Args:
        relative_path (str): Caminho relativo do vídeo dentro da pasta do curso.

    Returns:
        str | None: O caminho da subpasta pai, ou None se o vídeo
            estiver na raiz da pasta do curso.
    """
    parent = PurePosixPath(relative_path).parent
    return None if str(parent) == "." else str(parent)


def _video_json(vwp, favorites: set[UUID] | None = None) -> dict:
    """Serializa um `VideoWithProgress` para o formato JSON consumido pelo frontend.

    Args:
        vwp (VideoWithProgress): Vídeo combinado com seu progresso.
        favorites (set[UUID] | None): Ids de vídeos favoritados no
            curso, para calcular `is_favorite`; quando None, o campo
            sempre vem False (usado onde a lista de favoritos não é
            relevante, como no card "Continuar assistindo").

    Returns:
        dict: Representação JSON-serializável do vídeo.
    """
    return {
        "id": str(vwp.video.id),
        "file_name": vwp.video.file_name,
        "display_title": vwp.video.display_title,
        "display_name": vwp.video.display_name,
        "relative_path": vwp.video.relative_path,
        "module": _module_of(vwp.video.relative_path) if not vwp.video.is_manual else None,
        "sort_order": vwp.video.sort_order,
        "is_manual": vwp.video.is_manual,
        "duration_seconds": vwp.video.duration_seconds,
        "duration_label": format_seconds(vwp.video.duration_seconds or 0),
        "position_seconds": vwp.progress.position_seconds if vwp.progress else 0.0,
        "watched_percent": vwp.progress_percent,
        "is_completed": vwp.is_completed,
        "is_favorite": vwp.video.id in favorites if favorites is not None else False,
    }


@app.get("/api/courses")
def list_courses() -> list[dict]:
    """Lista todos os cursos ativos da biblioteca.

    Returns:
        list[dict]: Um resumo por curso ativo.
    """
    return [_course_summary_json(s) for s in course_service.get_course_summaries()]


@app.post("/api/courses")
def add_course(body: AddCourseBody) -> dict:
    """Cadastra um novo curso a partir de uma pasta local.

    Args:
        body (AddCourseBody): Caminho da pasta a cadastrar.

    Raises:
        HTTPException: 400 se a pasta não existir ou já estiver cadastrada.

    Returns:
        dict: Resumo do curso recém-criado.
    """
    try:
        summary = course_service.add_course(body.folder_path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _course_summary_json(summary)


@app.put("/api/courses/{course_id}")
def update_course(course_id: UUID, body: UpdateCourseBody) -> dict:
    """Atualiza nome e descrição de um curso.

    Args:
        course_id (UUID): Identificador do curso.
        body (UpdateCourseBody): Novo nome e descrição.

    Raises:
        HTTPException: 400 se o curso não existir ou o nome for vazio.

    Returns:
        dict: Resumo atualizado do curso.
    """
    try:
        summary = course_service.update_course(course_id, body.name, body.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _course_summary_json(summary)


@app.post("/api/courses/{course_id}/cover")
async def upload_course_cover(course_id: UUID, file: UploadFile = File(...)) -> dict:
    """Envia (ou substitui) a imagem de capa de um curso.

    Args:
        course_id (UUID): Identificador do curso.
        file (UploadFile): Arquivo de imagem enviado.

    Raises:
        HTTPException: 400 se a imagem exceder o tamanho máximo, o
            curso não existir, ou a extensão não for suportada.

    Returns:
        dict: `{"ok": True}` em caso de sucesso.
    """
    data = await file.read(MAX_COVER_SIZE_BYTES + 1)
    if len(data) > MAX_COVER_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Imagem muito grande (máximo 10 MB).")
    try:
        course_service.set_course_cover(
            course_id, file.filename or "capa", data, file.content_type or "image/*"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.get("/api/courses/{course_id}/cover")
def get_course_cover(course_id: UUID):
    """Serve o arquivo de imagem de capa de um curso.

    Args:
        course_id (UUID): Identificador do curso.

    Raises:
        HTTPException: 404 se o curso não existir, não tiver capa
            definida, ou o arquivo não estiver mais em disco.

    Returns:
        FileResponse: O arquivo de imagem da capa.
    """
    course = course_repo.get_by_id(course_id)
    if course is None or not course.cover_stored_name:
        raise HTTPException(status_code=404, detail="Sem capa.")
    path = get_course_cover_dir(course_id) / course.cover_stored_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Sem capa.")
    return FileResponse(path)


@app.post("/api/courses/{course_id}/refresh")
def refresh_course(course_id: UUID) -> dict:
    """Reescaneia a pasta de um curso, atualizando sua lista de vídeos.

    Args:
        course_id (UUID): Identificador do curso.

    Raises:
        HTTPException: 404 se o curso não existir ou a pasta não
            existir mais no disco.

    Returns:
        dict: Resumo atualizado do curso.
    """
    try:
        summary = course_service.refresh_course(course_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _course_summary_json(summary)


@app.delete("/api/courses/{course_id}")
def remove_course(course_id: UUID) -> dict:
    """Exclui um curso (soft-delete, reversível dentro do período de graça).

    Args:
        course_id (UUID): Identificador do curso.

    Raises:
        HTTPException: 404 se o curso não existir.

    Returns:
        dict: `{"ok": True}` em caso de sucesso.
    """
    try:
        course_service.soft_delete_course(course_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/courses/{course_id}/restore")
def restore_course(course_id: UUID) -> dict:
    """Desfaz a exclusão de um curso (botão "Desfazer" do toast).

    Args:
        course_id (UUID): Identificador do curso.

    Returns:
        dict: `{"ok": True}`.
    """
    course_service.restore_course(course_id)
    return {"ok": True}


@app.get("/api/courses/{course_id}/videos")
def list_videos(course_id: UUID) -> list[dict]:
    """Lista as aulas de um curso, com progresso e estado de favorito.

    Args:
        course_id (UUID): Identificador do curso.

    Raises:
        HTTPException: 404 se o curso não existir.

    Returns:
        list[dict]: Uma entrada por aula ativa, na ordem da playlist.
    """
    try:
        videos = course_service.get_videos_with_progress(course_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    favorites = course_service.get_favorites(course_id)
    return [_video_json(v, favorites) for v in videos]


@app.post("/api/courses/{course_id}/videos")
async def add_manual_video(course_id: UUID, file: UploadFile = File(...)) -> dict:
    """Anexa uma aula avulsa ao curso, fora do scan automático da pasta.

    Grava o upload em streaming (em blocos de `CHUNK_SIZE`) direto no
    disco, sem carregar o arquivo inteiro na memória, respeitando
    `MAX_VIDEO_UPLOAD_SIZE_BYTES`. Se o upload falhar ou o registro no
    banco não puder ser criado, o diretório parcialmente escrito é removido.

    Args:
        course_id (UUID): Identificador do curso.
        file (UploadFile): Arquivo de vídeo enviado.

    Raises:
        HTTPException: 400 se a extensão não for um vídeo suportado,
            o arquivo exceder o tamanho máximo, ou o curso não existir.

    Returns:
        dict: Identificador e nomes do vídeo recém-anexado.
    """
    extension = Path(file.filename or "").suffix.lower()
    if extension not in VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400, detail=f"Tipo de vídeo não suportado ({extension or 'sem extensão'})."
        )

    video_id = uuid4()
    stored_name = f"video{extension}"
    target_dir = get_manual_video_dir(course_id, video_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / stored_name
    size = 0
    try:
        with open(target_path, "wb") as out:
            while chunk := await file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_VIDEO_UPLOAD_SIZE_BYTES:
                    raise HTTPException(status_code=400, detail="Vídeo muito grande (máximo 4 GB).")
                out.write(chunk)
    except HTTPException:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise

    try:
        video = course_service.add_manual_video(
            course_id, video_id, file.filename or "video", stored_name, size
        )
    except ValueError as exc:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"id": str(video.id), "file_name": video.file_name, "display_name": video.display_name}


@app.put("/api/videos/{video_id}")
def update_video(video_id: UUID, body: UpdateVideoBody) -> dict:
    """Atualiza o título de exibição e/ou a posição de uma aula na playlist.

    Args:
        video_id (UUID): Identificador do vídeo.
        body (UpdateVideoBody): Novo título de exibição e/ou posição.

    Raises:
        HTTPException: 404 se o vídeo não existir.

    Returns:
        dict: Identificador, título e posição atualizados do vídeo.
    """
    try:
        video = course_service.update_video(video_id, body.display_title, body.sort_order)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": str(video.id), "display_title": video.display_title, "sort_order": video.sort_order}


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: UUID) -> dict:
    """Exclui uma aula da playlist (soft-delete, reversível dentro do período de graça).

    Args:
        video_id (UUID): Identificador do vídeo.

    Raises:
        HTTPException: 404 se o vídeo não existir.

    Returns:
        dict: `{"ok": True}` em caso de sucesso.
    """
    try:
        course_service.soft_delete_video(video_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/videos/{video_id}/restore")
def restore_video(video_id: UUID) -> dict:
    """Desfaz a exclusão de uma aula (botão "Desfazer" do toast).

    Args:
        video_id (UUID): Identificador do vídeo.

    Returns:
        dict: `{"ok": True}`.
    """
    course_service.restore_video(video_id)
    return {"ok": True}


@app.get("/api/continue-watching")
def continue_watching() -> dict | None:
    """Busca a aula em andamento mais recente, para o card "Continuar assistindo".

    Returns:
        dict | None: O vídeo (com dados do curso embutidos), ou None
            se não houver nenhuma aula em andamento.
    """
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
    """Salva o progresso de reprodução reportado pelo player (autosave periódico).

    Args:
        video_id (UUID): Identificador do vídeo.
        body (ProgressBody): Posição e duração atuais reportadas pelo player.

    Raises:
        HTTPException: 404 se o vídeo não existir.

    Returns:
        dict: Posição, percentual assistido e estado de conclusão resultantes.
    """
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
    """Marca ou desmarca manualmente uma aula como concluída.

    Args:
        video_id (UUID): Identificador do vídeo.
        body (CompletedBody): Novo estado de conclusão.

    Returns:
        dict: Posição, percentual assistido e estado de conclusão resultantes.
    """
    progress = course_service.set_video_completed(video_id, body.completed)
    return {
        "position_seconds": progress.position_seconds,
        "watched_percent": progress.watched_percent,
        "is_completed": progress.is_completed,
    }


@app.get("/api/videos/{video_id}/stream")
def stream_video(video_id: UUID, request: Request):
    """Transmite o arquivo de vídeo, com suporte a `Range` (necessário para dar seek no player).

    Resolve o caminho do arquivo tanto para vídeos escaneados da pasta
    do curso quanto para vídeos avulsos (guardados na pasta de dados
    do app). Sem cabeçalho `Range`, transmite o arquivo inteiro (200);
    com `Range`, transmite só o trecho pedido (206).

    Args:
        video_id (UUID): Identificador do vídeo.
        request (Request): Requisição HTTP, usada para ler o cabeçalho `Range`.

    Raises:
        HTTPException: 404 se o vídeo, o curso, ou o arquivo em disco não existirem.

    Returns:
        StreamingResponse: O conteúdo do vídeo, inteiro ou parcial.
    """
    video = course_repo.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado.")

    if video.is_manual:
        full_path = get_manual_video_dir(video.course_id, video.id) / video.manual_stored_name
    else:
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
        """Gera os bytes do arquivo a partir de `start`, em blocos de `CHUNK_SIZE`."""
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
    """Alterna o estado de favorito de um vídeo.

    Args:
        video_id (UUID): Identificador do vídeo.

    Returns:
        dict: Novo estado de favorito.
    """
    is_favorite = course_service.toggle_favorite(video_id)
    return {"is_favorite": is_favorite}


@app.get("/api/videos/{video_id}/notes")
def list_notes(video_id: UUID) -> list[dict]:
    """Lista as anotações ativas de um vídeo.

    Args:
        video_id (UUID): Identificador do vídeo.

    Returns:
        list[dict]: Anotações ordenadas pelo instante do vídeo.
    """
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
    """Cria uma anotação amarrada a um instante do vídeo.

    Args:
        video_id (UUID): Identificador do vídeo.
        body (NoteBody): Instante e texto da anotação.

    Returns:
        dict: A anotação recém-criada.
    """
    note = course_service.add_video_note(video_id, body.time_seconds, body.text)
    return {
        "id": str(note.id),
        "time_seconds": note.time_seconds,
        "time_label": format_seconds(note.time_seconds),
        "text": note.text,
    }


@app.put("/api/notes/{note_id}")
def update_note(note_id: UUID, body: UpdateNoteBody) -> dict:
    """Atualiza o texto de uma anotação existente.

    Args:
        note_id (UUID): Identificador da anotação.
        body (UpdateNoteBody): Novo texto.

    Raises:
        HTTPException: 400 se o texto for vazio ou a anotação não existir.

    Returns:
        dict: `{"ok": True}` em caso de sucesso.
    """
    try:
        course_service.update_video_note(note_id, body.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: UUID) -> dict:
    """Exclui uma anotação (soft-delete, reversível dentro do período de graça).

    Args:
        note_id (UUID): Identificador da anotação.

    Raises:
        HTTPException: 404 se a anotação não existir.

    Returns:
        dict: `{"ok": True}` em caso de sucesso.
    """
    try:
        course_service.soft_delete_video_note(note_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/notes/{note_id}/restore")
def restore_note(note_id: UUID) -> dict:
    """Desfaz a exclusão de uma anotação (botão "Desfazer" do toast).

    Args:
        note_id (UUID): Identificador da anotação.

    Returns:
        dict: `{"ok": True}`.
    """
    course_service.restore_video_note(note_id)
    return {"ok": True}


@app.get("/api/courses/{course_id}/notes")
def get_course_note(course_id: UUID) -> dict:
    """Busca o texto de notas gerais de um curso.

    Args:
        course_id (UUID): Identificador do curso.

    Returns:
        dict: O texto salvo (`text`), ou vazio se ainda não houver notas.
    """
    return {"text": course_service.get_course_note(course_id)}


@app.put("/api/courses/{course_id}/notes")
def save_course_note(course_id: UUID, body: CourseNoteBody) -> dict:
    """Cria ou substitui o texto de notas gerais de um curso.

    Args:
        course_id (UUID): Identificador do curso.
        body (CourseNoteBody): Novo texto das notas.

    Returns:
        dict: `{"ok": True}`.
    """
    course_service.save_course_note(course_id, body.text)
    return {"ok": True}


@app.get("/api/courses/{course_id}/materials")
def list_materials(course_id: UUID) -> list[dict]:
    """Escaneia a pasta do curso em busca de materiais (PDF, planilhas, imagens etc).

    Args:
        course_id (UUID): Identificador do curso.

    Raises:
        HTTPException: 404 se o curso não existir.

    Returns:
        list[dict]: Materiais encontrados na pasta do curso.
    """
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
    """Baixa um material encontrado no scan da pasta do curso.

    Valida que `path` resolve para dentro da pasta do curso, para
    impedir directory traversal.

    Args:
        course_id (UUID): Identificador do curso.
        path (str): Caminho relativo do arquivo dentro da pasta do curso.

    Raises:
        HTTPException: 404 se o curso não existir, ou o caminho
            resolvido não estiver dentro da pasta do curso ou não
            corresponder a um arquivo existente.

    Returns:
        FileResponse: O arquivo solicitado.
    """
    course = course_repo.get_by_id(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

    root = Path(course.folder_path).resolve()
    full_path = (root / path).resolve()
    if root not in full_path.parents or not full_path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    return FileResponse(full_path, filename=full_path.name)


def _uploaded_material_json(m) -> dict:
    """Serializa um `UploadedMaterial` para o formato JSON consumido pelo frontend.

    Args:
        m (UploadedMaterial): Material vindo do serviço.

    Returns:
        dict: Representação JSON-serializável do material.
    """
    return {
        "id": str(m.id),
        "file_name": m.file_name,
        "mime_type": m.mime_type,
        "size_bytes": m.size_bytes,
        "uploaded_at": m.uploaded_at.isoformat(),
    }


@app.get("/api/videos/{video_id}/materials")
def list_video_materials(video_id: UUID) -> list[dict]:
    """Lista os materiais ativos anexados manualmente a um vídeo.

    Args:
        video_id (UUID): Identificador do vídeo.

    Returns:
        list[dict]: Materiais enviados pelo usuário para essa aula.
    """
    materials = course_service.list_video_materials(video_id)
    return [_uploaded_material_json(m) for m in materials]


@app.post("/api/videos/{video_id}/materials")
async def upload_video_material(video_id: UUID, file: UploadFile = File(...)) -> dict:
    """Anexa um novo material (imagem, áudio ou PDF) a um vídeo.

    Args:
        video_id (UUID): Identificador do vídeo.
        file (UploadFile): Arquivo enviado.

    Raises:
        HTTPException: 400 se o arquivo exceder o tamanho máximo, o
            vídeo não existir, ou a extensão não for suportada.

    Returns:
        dict: O material recém-anexado.
    """
    data = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    if len(data) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Arquivo muito grande (máximo 50 MB).")
    try:
        material = course_service.add_video_material(
            video_id, file.filename or "arquivo", data, file.content_type or "application/octet-stream"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _uploaded_material_json(material)


@app.put("/api/materials/{material_id}")
def rename_material(material_id: UUID, body: RenameMaterialBody) -> dict:
    """Renomeia o nome de exibição de um material.

    Args:
        material_id (UUID): Identificador do material.
        body (RenameMaterialBody): Novo nome de exibição.

    Raises:
        HTTPException: 400 se o nome for vazio ou o material não existir.

    Returns:
        dict: `{"ok": True}` em caso de sucesso.
    """
    try:
        course_service.rename_video_material(material_id, body.file_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.delete("/api/materials/{material_id}")
def delete_video_material(material_id: UUID) -> dict:
    """Exclui um material (soft-delete, reversível dentro do período de graça).

    Args:
        material_id (UUID): Identificador do material.

    Raises:
        HTTPException: 404 se o material não existir.

    Returns:
        dict: `{"ok": True}` em caso de sucesso.
    """
    try:
        course_service.soft_delete_video_material(material_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/materials/{material_id}/restore")
def restore_video_material(material_id: UUID) -> dict:
    """Desfaz a exclusão de um material (botão "Desfazer" do toast).

    Args:
        material_id (UUID): Identificador do material.

    Returns:
        dict: `{"ok": True}`.
    """
    course_service.restore_video_material(material_id)
    return {"ok": True}


@app.get("/api/materials/{material_id}/download")
def download_video_material(material_id: UUID):
    """Baixa um material anexado manualmente a um vídeo.

    Args:
        material_id (UUID): Identificador do material.

    Raises:
        HTTPException: 404 se o material não existir ou o arquivo não
            estiver mais em disco.

    Returns:
        FileResponse: O arquivo do material.
    """
    result = course_service.get_video_material_path(material_id)
    if result is None or not result[1].is_file():
        raise HTTPException(status_code=404, detail="Material não encontrado.")
    material, path = result
    return FileResponse(path, filename=material.file_name, media_type=material.mime_type)


@app.get("/api/browse")
def browse(path: str | None = None) -> dict:
    """Lista subpastas de um diretório, para o seletor de pasta do "Adicionar curso".

    Sempre recua para a pasta do usuário (`Path.home()`) quando o
    caminho pedido não existir, não for um diretório, ou não puder ser
    resolvido — nunca lança erro para o chamador.

    Args:
        path (str | None): Caminho a listar; None usa a pasta do usuário.

    Returns:
        dict: `path` (caminho atual), `parent` (caminho um nível
            acima, ou None se já estiver na raiz) e `entries` (lista
            de subpastas visíveis, sem contar ocultas).
    """
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
    """Ponto de entrada do app: garante o banco, abre o navegador e sobe o servidor.

    Usado pelo script `auto-curso-web` (ver `pyproject.toml`) e por
    `python -m auto_curso`. Respeita a variável de ambiente
    `AUTO_CURSO_OPEN_BROWSER=0` para não abrir o navegador
    automaticamente (usado pelo lançador de desktop, que abre sua
    própria janela de app).
    """
    import os
    import uvicorn

    initialize_database()
    if os.environ.get("AUTO_CURSO_OPEN_BROWSER", "1") != "0":
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
