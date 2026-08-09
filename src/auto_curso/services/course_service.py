from __future__ import annotations

import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from auto_curso.constants import (
    COMPLETION_THRESHOLD,
    COVER_EXTENSIONS,
    MAX_COVER_SIZE_BYTES,
    MAX_UPLOAD_SIZE_BYTES,
    SOFT_DELETE_GRACE_SECONDS,
    UPLOAD_EXTENSIONS,
    get_course_cover_dir,
    get_course_manual_videos_dir,
    get_course_materials_dir,
    get_manual_video_dir,
    get_video_materials_dir,
)
from auto_curso.models.course import Course, CourseSummary
from auto_curso.models.material import UploadedMaterial
from auto_curso.models.note import VideoNote
from auto_curso.models.progress import PlaybackProgress
from auto_curso.models.video import ScannedVideoFile, Video, VideoWithProgress
from auto_curso.repositories.course_repository import CourseRepository
from auto_curso.repositories.materials_repository import MaterialsRepository
from auto_curso.repositories.notes_repository import NotesRepository
from auto_curso.repositories.progress_repository import ProgressRepository
from auto_curso.services.folder_scanner import FolderScanner


class CourseService:
    """Camada de regras de negócio (use cases) do app: cursos, vídeos, progresso,
    anotações, materiais e o ciclo de exclusão segura (soft-delete + purga).

    Orquestra os repositórios (acesso a dados) e o `FolderScanner`
    (leitura da pasta local); não depende de FastAPI nem de nenhum
    detalhe de transporte HTTP.
    """

    def __init__(
        self,
        course_repo: CourseRepository | None = None,
        progress_repo: ProgressRepository | None = None,
        scanner: FolderScanner | None = None,
        notes_repo: NotesRepository | None = None,
        uploads_repo: MaterialsRepository | None = None,
    ) -> None:
        """Monta o serviço, criando as dependências padrão quando não informadas.

        Args:
            course_repo (CourseRepository | None): Repositório de
                cursos/vídeos. Cria um novo se omitido.
            progress_repo (ProgressRepository | None): Repositório de
                progresso de reprodução. Cria um novo se omitido.
            scanner (FolderScanner | None): Leitor de pasta local. Cria
                um novo se omitido.
            notes_repo (NotesRepository | None): Repositório de
                anotações/notas/favoritos. Cria um novo se omitido.
            uploads_repo (MaterialsRepository | None): Repositório de
                materiais anexados. Cria um novo se omitido.
        """
        self._courses = course_repo or CourseRepository()
        self._progress = progress_repo or ProgressRepository()
        self._scanner = scanner or FolderScanner()
        self._notes = notes_repo or NotesRepository()
        self._uploads = uploads_repo or MaterialsRepository()

    # ───────────────────────── courses ─────────────────────────

    def add_course(self, folder_path: str) -> CourseSummary:
        """Cadastra um novo curso a partir de uma pasta local e escaneia seus vídeos.

        Args:
            folder_path (str): Caminho da pasta com os vídeos do curso.

        Raises:
            FileNotFoundError: Se a pasta não existir.
            ValueError: Se a pasta já estiver cadastrada como curso.

        Returns:
            CourseSummary: Resumo do curso recém-criado, já com a
                contagem de vídeos escaneados.
        """
        normalized = str(Path(folder_path).resolve())
        if not os.path.isdir(normalized):
            raise FileNotFoundError(f"Pasta não encontrada: {normalized}")

        if self._courses.get_by_folder_path(normalized):
            raise ValueError("Esta pasta já está cadastrada como curso.")

        course = Course(
            id=uuid4(),
            name=Path(normalized).name,
            folder_path=normalized,
            added_at=datetime.now(timezone.utc),
        )
        self._courses.add(course)
        self._sync_videos(course)
        return self._build_summary(course)

    def refresh_course(self, course_id: UUID) -> CourseSummary:
        """Reescaneia a pasta de um curso, atualizando sua lista de vídeos.

        Args:
            course_id (UUID): Identificador do curso.

        Raises:
            ValueError: Se o curso não existir.
            FileNotFoundError: Se a pasta do curso não existir mais no disco.

        Returns:
            CourseSummary: Resumo atualizado do curso.
        """
        course = self._courses.get_by_id(course_id)
        if course is None:
            raise ValueError("Curso não encontrado.")
        if not os.path.isdir(course.folder_path):
            raise FileNotFoundError(f"Pasta do curso não encontrada: {course.folder_path}")
        self._sync_videos(course)
        return self._build_summary(course)

    def update_course(self, course_id: UUID, name: str, description: str | None) -> CourseSummary:
        """Atualiza nome e descrição de um curso.

        Args:
            course_id (UUID): Identificador do curso.
            name (str): Novo nome de exibição (não pode ser vazio).
            description (str | None): Nova descrição, ou None para limpá-la.

        Raises:
            ValueError: Se o curso não existir ou o nome for vazio.

        Returns:
            CourseSummary: Resumo atualizado do curso.
        """
        course = self._courses.get_by_id(course_id)
        if course is None:
            raise ValueError("Curso não encontrado.")
        if not name or not name.strip():
            raise ValueError("Nome do curso não pode ser vazio.")
        self._courses.update(course_id, name.strip(), description)
        return self._build_summary(self._courses.get_by_id(course_id))

    def set_course_cover(self, course_id: UUID, file_name: str, data: bytes, mime_type: str) -> str:
        """Define a imagem de capa de um curso, substituindo a anterior.

        Args:
            course_id (UUID): Identificador do curso.
            file_name (str): Nome original do arquivo enviado (usado
                para inferir a extensão).
            data (bytes): Conteúdo binário da imagem.
            mime_type (str): Tipo MIME informado no upload (não usado
                na validação, mantido para futura referência).

        Raises:
            ValueError: Se o curso não existir, a extensão não for
                suportada (`COVER_EXTENSIONS`), ou a imagem exceder
                `MAX_COVER_SIZE_BYTES`.

        Returns:
            str: Nome do arquivo salvo em disco.
        """
        course = self._courses.get_by_id(course_id)
        if course is None:
            raise ValueError("Curso não encontrado.")
        extension = Path(file_name).suffix.lower()
        if extension not in COVER_EXTENSIONS:
            raise ValueError(f"Tipo de imagem não suportado ({extension or 'sem extensão'}).")
        if len(data) > MAX_COVER_SIZE_BYTES:
            raise ValueError("Imagem muito grande (máximo 10 MB).")

        if course.cover_stored_name:
            (get_course_cover_dir(course_id) / course.cover_stored_name).unlink(missing_ok=True)

        stored_name = f"{uuid4()}{extension}"
        cover_dir = get_course_cover_dir(course_id)
        cover_dir.mkdir(parents=True, exist_ok=True)
        (cover_dir / stored_name).write_bytes(data)
        self._courses.set_cover(course_id, stored_name)
        return stored_name

    def soft_delete_course(self, course_id: UUID) -> None:
        """Marca um curso como excluído, iniciando o período de graça antes da exclusão definitiva.

        Args:
            course_id (UUID): Identificador do curso.

        Raises:
            ValueError: Se o curso não existir.
        """
        if self._courses.get_by_id(course_id) is None:
            raise ValueError("Curso não encontrado.")
        self._courses.soft_delete(course_id)

    def restore_course(self, course_id: UUID) -> None:
        """Desfaz a exclusão de um curso, desde que ainda esteja no período de graça.

        Args:
            course_id (UUID): Identificador do curso.
        """
        self._courses.restore(course_id)

    def get_course_summaries(self) -> list[CourseSummary]:
        """Lista todos os cursos ativos com seus totais de aulas.

        Returns:
            list[CourseSummary]: Um resumo por curso ativo.
        """
        return [self._build_summary(c) for c in self._courses.get_all()]

    def get_course_summary(self, course_id: UUID) -> CourseSummary:
        """Busca o resumo de um único curso.

        Args:
            course_id (UUID): Identificador do curso.

        Raises:
            ValueError: Se o curso não existir.

        Returns:
            CourseSummary: Resumo do curso.
        """
        course = self._courses.get_by_id(course_id)
        if course is None:
            raise ValueError("Curso não encontrado.")
        return self._build_summary(course)

    # ───────────────────────── playback progress ─────────────────────────

    def set_video_completed(self, video_id: UUID, completed: bool) -> PlaybackProgress:
        """Marca ou desmarca manualmente uma aula como concluída.

        Ao desmarcar uma aula que estava acima do limiar de conclusão,
        recua o percentual assistido logo abaixo do limiar (em vez de
        zerar), para refletir que o usuário já assistiu quase tudo.

        Args:
            video_id (UUID): Identificador do vídeo.
            completed (bool): Novo estado de conclusão.

        Returns:
            PlaybackProgress: O progresso resultante, já salvo.
        """
        existing = self._progress.get(video_id)
        now = datetime.now(timezone.utc)
        if completed:
            progress = PlaybackProgress(
                video_id=video_id,
                position_seconds=0.0,
                is_completed=True,
                watched_percent=100.0,
                last_watched_at=now,
            )
        elif existing:
            percent = existing.watched_percent
            position = existing.position_seconds
            threshold_pct = COMPLETION_THRESHOLD * 100
            below_pct = (COMPLETION_THRESHOLD - 0.01) * 100
            if percent >= threshold_pct:
                old_pct = max(percent, threshold_pct)
                percent = below_pct
                if position > 0:
                    position = position * (below_pct / old_pct)
            elif percent >= 100:
                percent = 99.0
            progress = PlaybackProgress(
                video_id=video_id,
                position_seconds=position,
                is_completed=False,
                watched_percent=percent,
                last_watched_at=now,
            )
        else:
            progress = PlaybackProgress(
                video_id=video_id,
                position_seconds=0.0,
                is_completed=False,
                watched_percent=0.0,
                last_watched_at=now,
            )
        self._progress.save(progress)
        return progress

    def save_progress(
        self, video_id: UUID, position_seconds: float, duration_seconds: float | None
    ) -> PlaybackProgress:
        """Salva o progresso de reprodução reportado pelo player (autosave periódico).

        Se o vídeo já está marcado como concluído, a chamada é
        ignorada: como reassistir sempre recomeça do zero, um autosave
        normal recalcularia uma proporção posição/duração minúscula e
        desmarcaria a conclusão indevidamente. Só a alternância
        explícita (`set_video_completed`) pode desfazer uma conclusão.

        Args:
            video_id (UUID): Identificador do vídeo.
            position_seconds (float): Posição atual de reprodução, em segundos.
            duration_seconds (float | None): Duração total reportada
                pelo player, usada para gravar `Video.duration_seconds`
                na primeira vez que é conhecida.

        Raises:
            ValueError: Se o vídeo não existir.

        Returns:
            PlaybackProgress: O progresso resultante, já salvo (ou o
                progresso existente, inalterado, se o vídeo já estava concluído).
        """
        video = self._courses.get_video(video_id)
        if video is None:
            raise ValueError("Vídeo não encontrado.")

        existing = self._progress.get(video_id)
        if existing and existing.is_completed:
            return existing

        if duration_seconds and duration_seconds > 0 and video.duration_seconds is None:
            self._courses.update_video_duration(video_id, duration_seconds)

        effective_duration = duration_seconds or video.duration_seconds or 0.0
        if effective_duration > 0:
            percent = min(100.0, position_seconds / effective_duration * 100)
            is_completed = position_seconds / effective_duration >= COMPLETION_THRESHOLD
        else:
            percent = 0.0
            is_completed = False

        progress = PlaybackProgress(
            video_id=video_id,
            position_seconds=0.0 if is_completed else position_seconds,
            is_completed=is_completed,
            watched_percent=100.0 if is_completed else percent,
            last_watched_at=datetime.now(timezone.utc),
        )
        self._progress.save(progress)
        return progress

    def get_continue_watching(self) -> tuple[VideoWithProgress, Course] | None:
        """Busca a aula em andamento mais recente, para o card "Continuar assistindo".

        Returns:
            tuple[VideoWithProgress, Course] | None: O vídeo (com
                progresso) e seu curso, ou None se não houver nenhuma
                aula em andamento — ou se o vídeo/curso associado ao
                progresso mais recente não existir mais.
        """
        progress = self._progress.get_most_recent_in_progress()
        if progress is None:
            return None
        video = self._courses.get_video(progress.video_id)
        if video is None:
            return None
        course = self._courses.get_by_id(video.course_id)
        if course is None:
            return None
        return (
            VideoWithProgress(video=video, progress=progress, course_folder_path=course.folder_path),
            course,
        )

    # ───────────────────────── videos ─────────────────────────

    def get_videos_with_progress(self, course_id: UUID) -> list[VideoWithProgress]:
        """Lista as aulas de um curso já combinadas com seu progresso individual.

        Args:
            course_id (UUID): Identificador do curso.

        Raises:
            ValueError: Se o curso não existir.

        Returns:
            list[VideoWithProgress]: Uma entrada por aula ativa,
                na ordem da playlist.
        """
        course = self._courses.get_by_id(course_id)
        if course is None:
            raise ValueError("Curso não encontrado.")

        videos = self._courses.get_videos(course_id)
        progress_map = self._progress.get_for_course(course_id)
        return [
            VideoWithProgress(
                video=video,
                progress=progress_map.get(video.id),
                course_folder_path=course.folder_path,
            )
            for video in videos
        ]

    def add_manual_video(
        self, course_id: UUID, video_id: UUID, file_name: str, stored_name: str, size_bytes: int
    ) -> Video:
        """Registra uma aula avulsa (arquivo já salvo em disco pelo chamador).

        O arquivo em si já deve ter sido gravado em
        `get_manual_video_dir(course_id, video_id)` antes desta chamada
        (tipicamente pelo endpoint de upload, que faz a gravação em
        streaming); este método só cria o registro no banco.

        Args:
            course_id (UUID): Identificador do curso.
            video_id (UUID): Identificador pré-gerado para o novo vídeo.
            file_name (str): Nome original do arquivo enviado.
            stored_name (str): Nome do arquivo salvo em disco.
            size_bytes (int): Tamanho do arquivo em bytes.

        Raises:
            ValueError: Se o curso não existir.

        Returns:
            Video: O vídeo avulso recém-registrado, já no fim da playlist.
        """
        course = self._courses.get_by_id(course_id)
        if course is None:
            raise ValueError("Curso não encontrado.")
        sort_order = self._courses.get_next_sort_order(course_id)
        video = Video(
            id=video_id,
            course_id=course_id,
            relative_path=f"__manual__/{video_id}",
            file_name=file_name,
            sort_order=sort_order,
            file_size_bytes=size_bytes,
            is_manual=True,
            manual_stored_name=stored_name,
        )
        self._courses.add_manual_video(video)
        return video

    def update_video(
        self, video_id: UUID, display_title: str | None, sort_order: int | None
    ) -> Video:
        """Atualiza o título de exibição e/ou a posição de uma aula na playlist.

        Args:
            video_id (UUID): Identificador do vídeo.
            display_title (str | None): Novo título de exibição, ou
                None para voltar a usar o nome original do arquivo.
            sort_order (int | None): Nova posição na playlist, ou None
                para manter a posição atual.

        Raises:
            ValueError: Se o vídeo não existir.

        Returns:
            Video: O vídeo com os campos atualizados.
        """
        video = self._courses.get_video(video_id)
        if video is None:
            raise ValueError("Vídeo não encontrado.")
        self._courses.update_video(video_id, display_title, sort_order)
        video.display_title = display_title
        if sort_order is not None:
            video.sort_order = sort_order
        return video

    def soft_delete_video(self, video_id: UUID) -> None:
        """Remove uma aula da playlist, iniciando o período de graça antes da exclusão definitiva.

        Args:
            video_id (UUID): Identificador do vídeo.

        Raises:
            ValueError: Se o vídeo não existir.
        """
        if self._courses.get_video(video_id) is None:
            raise ValueError("Vídeo não encontrado.")
        self._courses.soft_delete_video(video_id)

    def restore_video(self, video_id: UUID) -> None:
        """Desfaz a exclusão de uma aula, desde que ainda esteja no período de graça.

        Args:
            video_id (UUID): Identificador do vídeo.
        """
        self._courses.restore_video(video_id)

    # ───────────────────────── favorites ─────────────────────────

    def get_favorites(self, course_id: UUID) -> set[UUID]:
        """Lista os ids de vídeos favoritados dentro de um curso.

        Args:
            course_id (UUID): Identificador do curso.

        Returns:
            set[UUID]: Ids dos vídeos marcados como favoritos.
        """
        return self._notes.get_favorites_for_course(course_id)

    def toggle_favorite(self, video_id: UUID) -> bool:
        """Alterna o estado de favorito de um vídeo.

        Args:
            video_id (UUID): Identificador do vídeo.

        Returns:
            bool: Novo estado após a alternância.
        """
        return self._notes.toggle_favorite(video_id)

    # ───────────────────────── video notes ─────────────────────────

    def get_video_notes(self, video_id: UUID) -> list[VideoNote]:
        """Lista as anotações ativas de um vídeo.

        Args:
            video_id (UUID): Identificador do vídeo.

        Returns:
            list[VideoNote]: Anotações ordenadas pelo instante do vídeo.
        """
        return self._notes.list_for_video(video_id)

    def add_video_note(self, video_id: UUID, time_seconds: float, text: str) -> VideoNote:
        """Cria uma anotação amarrada a um instante do vídeo.

        Args:
            video_id (UUID): Identificador do vídeo.
            time_seconds (float): Instante do vídeo, em segundos.
            text (str): Texto da anotação.

        Returns:
            VideoNote: A anotação recém-criada.
        """
        return self._notes.add(video_id, time_seconds, text)

    def update_video_note(self, note_id: UUID, text: str) -> None:
        """Atualiza o texto de uma anotação existente.

        Args:
            note_id (UUID): Identificador da anotação.
            text (str): Novo texto (não pode ser vazio).

        Raises:
            ValueError: Se o texto for vazio ou a anotação não existir.
        """
        if not text or not text.strip():
            raise ValueError("O texto da anotação não pode ser vazio.")
        if self._notes.get(note_id) is None:
            raise ValueError("Anotação não encontrada.")
        self._notes.update(note_id, text.strip())

    def soft_delete_video_note(self, note_id: UUID) -> None:
        """Exclui uma anotação, iniciando o período de graça antes da exclusão definitiva.

        Args:
            note_id (UUID): Identificador da anotação.

        Raises:
            ValueError: Se a anotação não existir.
        """
        if self._notes.get(note_id) is None:
            raise ValueError("Anotação não encontrada.")
        self._notes.soft_delete(note_id)

    def restore_video_note(self, note_id: UUID) -> None:
        """Desfaz a exclusão de uma anotação, desde que ainda esteja no período de graça.

        Args:
            note_id (UUID): Identificador da anotação.
        """
        self._notes.restore(note_id)

    def get_course_note(self, course_id: UUID) -> str:
        """Busca o texto de notas gerais de um curso.

        Args:
            course_id (UUID): Identificador do curso.

        Returns:
            str: O texto salvo, ou string vazia se ainda não houver notas.
        """
        return self._notes.get_course_note(course_id)

    def save_course_note(self, course_id: UUID, text: str) -> None:
        """Cria ou substitui o texto de notas gerais de um curso.

        Args:
            course_id (UUID): Identificador do curso.
            text (str): Novo texto das notas.
        """
        self._notes.save_course_note(course_id, text)

    # ───────────────────────── materials ─────────────────────────

    def get_materials(self, course_id: UUID) -> list[ScannedVideoFile]:
        """Escaneia a pasta do curso em busca de materiais (PDF, planilhas, imagens etc).

        Args:
            course_id (UUID): Identificador do curso.

        Raises:
            ValueError: Se o curso não existir.

        Returns:
            list[ScannedVideoFile]: Materiais encontrados na pasta do curso.
        """
        course = self._courses.get_by_id(course_id)
        if course is None:
            raise ValueError("Curso não encontrado.")
        return self._scanner.scan_materials(course.folder_path)

    def list_video_materials(self, video_id: UUID) -> list[UploadedMaterial]:
        """Lista os materiais ativos anexados manualmente a um vídeo.

        Args:
            video_id (UUID): Identificador do vídeo.

        Returns:
            list[UploadedMaterial]: Materiais enviados pelo usuário para essa aula.
        """
        return self._uploads.list_for_video(video_id)

    def add_video_material(
        self, video_id: UUID, file_name: str, data: bytes, mime_type: str
    ) -> UploadedMaterial:
        """Anexa um novo material (imagem, áudio ou PDF) a um vídeo.

        Args:
            video_id (UUID): Identificador do vídeo.
            file_name (str): Nome original do arquivo enviado (usado
                para inferir a extensão e exibir na interface).
            data (bytes): Conteúdo binário do arquivo.
            mime_type (str): Tipo MIME informado no upload.

        Raises:
            ValueError: Se o vídeo não existir, a extensão não for
                suportada (`UPLOAD_EXTENSIONS`), ou o arquivo exceder
                `MAX_UPLOAD_SIZE_BYTES`.

        Returns:
            UploadedMaterial: O material recém-anexado.
        """
        video = self._courses.get_video(video_id)
        if video is None:
            raise ValueError("Vídeo não encontrado.")

        extension = Path(file_name).suffix.lower()
        if extension not in UPLOAD_EXTENSIONS:
            raise ValueError(
                f"Tipo de arquivo não suportado ({extension or 'sem extensão'}). "
                "Envie imagem, áudio ou PDF."
            )
        if len(data) > MAX_UPLOAD_SIZE_BYTES:
            raise ValueError("Arquivo muito grande (máximo 50 MB).")

        stored_name = f"{uuid4()}{extension}"
        target_dir = get_video_materials_dir(video.course_id, video_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / stored_name).write_bytes(data)

        return self._uploads.add(video_id, file_name, stored_name, mime_type, len(data))

    def rename_video_material(self, material_id: UUID, file_name: str) -> None:
        """Renomeia o nome de exibição de um material.

        Args:
            material_id (UUID): Identificador do material.
            file_name (str): Novo nome de exibição (não pode ser vazio).

        Raises:
            ValueError: Se o nome for vazio ou o material não existir.
        """
        if not file_name or not file_name.strip():
            raise ValueError("O nome do arquivo não pode ser vazio.")
        if self._uploads.get(material_id) is None:
            raise ValueError("Material não encontrado.")
        self._uploads.rename(material_id, file_name.strip())

    def soft_delete_video_material(self, material_id: UUID) -> None:
        """Exclui um material, iniciando o período de graça antes da exclusão definitiva.

        Args:
            material_id (UUID): Identificador do material.

        Raises:
            ValueError: Se o material não existir.
        """
        if self._uploads.get(material_id) is None:
            raise ValueError("Material não encontrado.")
        self._uploads.soft_delete(material_id)

    def restore_video_material(self, material_id: UUID) -> None:
        """Desfaz a exclusão de um material, desde que ainda esteja no período de graça.

        Args:
            material_id (UUID): Identificador do material.
        """
        self._uploads.restore(material_id)

    def get_video_material_path(self, material_id: UUID) -> tuple[UploadedMaterial, Path] | None:
        """Resolve o registro e o caminho em disco de um material, para download/streaming.

        Args:
            material_id (UUID): Identificador do material.

        Returns:
            tuple[UploadedMaterial, Path] | None: O material e o
                caminho do arquivo em disco, ou None se o material ou
                o vídeo dono dele não existir mais.
        """
        material = self._uploads.get(material_id)
        if material is None:
            return None
        video = self._courses.get_video(material.video_id)
        if video is None:
            return None
        path = get_video_materials_dir(video.course_id, material.video_id) / material.stored_name
        return material, path

    # ───────────────────────── soft-delete purge (called periodically) ─────────────────────────

    def purge_expired_soft_deletes(self) -> None:
        """Efetiva a exclusão definitiva de tudo cujo período de graça já expirou.

        Chamado periodicamente por uma tarefa em background (ver
        `web.server.lifespan`). Para cada entidade com `DeletedAt`
        mais antigo que `SOFT_DELETE_GRACE_SECONDS`: remove o registro
        do banco (o que também apaga, em cascata via FK, os registros
        dependentes) e apaga os arquivos/diretórios correspondentes em
        disco. Processa materiais e vídeos antes de cursos, para poder
        resolver `course_id`/caminhos antes que a cascata de exclusão
        do curso remova os registros filhos.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=SOFT_DELETE_GRACE_SECONDS)
        ).isoformat()

        for material in self._uploads.get_expired_soft_deleted(cutoff):
            video = self._courses.get_video(material.video_id, include_deleted=True)
            if video is not None:
                path = get_video_materials_dir(video.course_id, material.video_id) / material.stored_name
                path.unlink(missing_ok=True)
            self._uploads.hard_delete(material.id)

        for video in self._courses.get_expired_soft_deleted_videos(cutoff):
            if video.is_manual:
                shutil.rmtree(get_manual_video_dir(video.course_id, video.id), ignore_errors=True)
            else:
                self._courses.add_excluded_path(video.course_id, video.relative_path)
            shutil.rmtree(get_video_materials_dir(video.course_id, video.id), ignore_errors=True)
            self._courses.hard_delete_video(video.id)

        for note in self._notes.get_expired_soft_deleted(cutoff):
            self._notes.hard_delete(note.id)

        for course in self._courses.get_expired_soft_deleted(cutoff):
            shutil.rmtree(get_course_materials_dir(course.id), ignore_errors=True)
            shutil.rmtree(get_course_manual_videos_dir(course.id), ignore_errors=True)
            shutil.rmtree(get_course_cover_dir(course.id), ignore_errors=True)
            self._courses.hard_delete(course.id)

    # ───────────────────────── internal ─────────────────────────

    def _sync_videos(self, course: Course) -> None:
        """Reconcilia os vídeos escaneados da pasta com os registros no banco.

        Ignora caminhos marcados como excluídos permanentemente
        (`ExcludedVideoPaths`) e preserva vídeos avulsos (`is_manual`),
        que nunca fazem parte do scan. Vídeos escaneados que já
        existiam no banco mantêm seu id e duração conhecida.

        Args:
            course (Course): Curso a sincronizar.
        """
        scanned = self._scanner.scan(course.folder_path)
        excluded = self._courses.get_excluded_paths(course.id)
        scanned = [f for f in scanned if f.relative_path not in excluded]

        videos = [
            Video(
                id=uuid4(),
                course_id=course.id,
                relative_path=file.relative_path,
                file_name=file.file_name,
                sort_order=index,
                file_size_bytes=file.file_size_bytes,
            )
            for index, file in enumerate(scanned)
        ]

        existing = {v.relative_path: v for v in self._courses.get_videos(course.id) if not v.is_manual}
        for video in videos:
            if old := existing.get(video.relative_path):
                video.id = old.id
                video.duration_seconds = old.duration_seconds

        self._courses.sync_videos(course.id, videos)
        manual_ids = [v.id for v in self._courses.get_videos(course.id) if v.is_manual]
        self._progress.delete_orphans(course.id, [v.id for v in videos] + manual_ids)

    def _build_summary(self, course: Course) -> CourseSummary:
        """Monta o resumo de um curso (totais de vídeos e concluídos).

        Args:
            course (Course): Curso já carregado.

        Returns:
            CourseSummary: Resumo pronto para a API.
        """
        videos = self._courses.get_videos(course.id)
        completed = self._progress.get_completed_count(course.id)
        return CourseSummary(
            course=course,
            total_videos=len(videos),
            completed_videos=completed,
        )
