"use strict";

const state = {
  courses: [],
  currentCourseId: null,
  currentCourse: null,
  videos: [],
  filter: "all",
  currentVideoId: null,
  browsePath: null,
  searchTerm: "",
  saveTimer: null,
  activeTab: "notes",
  courseNoteTimer: null,
  videoSearchTerm: "",
  videoPage: 0,
};

const el = (id) => document.getElementById(id);

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function showToast(message) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3200);
}

function formatSeconds(total) {
  if (total == null || Number.isNaN(total) || total < 0) return "--:--";
  total = Math.floor(total);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function showView(name) {
  el("view-library").classList.toggle("hidden", name !== "library");
  el("view-player").classList.toggle("hidden", name !== "player");
}

/* ───────────────── secure delete: confirm modal + undo toast ─────────────────
   Mandatory 3-layer flow for every delete in the app:
   1) red confirm modal naming the item, 2) checkbox gate on the final button,
   3) undo toast after a soft-delete, with a 30s server-side grace period
   before the item is hard-deleted for good. No caller may bypass this. */

let confirmDeleteState = null;

function showConfirmDelete(itemName, onConfirmDelete, onUndo) {
  confirmDeleteState = { onConfirmDelete, onUndo, itemName };
  el("confirm-delete-message").textContent =
    `Essa ação não poderá ser desfeita. O item "${itemName}" será permanentemente removido.`;
  el("confirm-delete-checkbox").checked = false;
  el("confirm-delete-confirm").disabled = true;
  el("confirm-delete-dialog").classList.remove("hidden");
}

el("confirm-delete-checkbox").addEventListener("change", (e) => {
  el("confirm-delete-confirm").disabled = !e.target.checked;
});
el("confirm-delete-cancel").addEventListener("click", () => {
  el("confirm-delete-dialog").classList.add("hidden");
  confirmDeleteState = null;
});
el("confirm-delete-confirm").addEventListener("click", async () => {
  if (!confirmDeleteState) return;
  const { onConfirmDelete, onUndo, itemName } = confirmDeleteState;
  const btn = el("confirm-delete-confirm");
  btn.disabled = true;
  try {
    await onConfirmDelete();
    el("confirm-delete-dialog").classList.add("hidden");
    confirmDeleteState = null;
    showUndoToast(`"${itemName}" excluído com sucesso`, onUndo);
  } catch (e) {
    showToast(e.message);
    btn.disabled = false;
  }
});

function showUndoToast(message, onUndo) {
  const toast = document.createElement("div");
  toast.className = "toast undo-toast";
  const text = document.createElement("span");
  text.textContent = message;
  toast.appendChild(text);
  if (onUndo) {
    const undoBtn = document.createElement("button");
    undoBtn.textContent = "Desfazer";
    undoBtn.addEventListener("click", async () => {
      toast.remove();
      try {
        await onUndo();
        showToast("Restaurado.");
      } catch (e) {
        showToast(e.message);
      }
    });
    toast.appendChild(undoBtn);
  }
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

/* ───────────────── library view ───────────────── */

async function loadLibrary() {
  showView("library");
  const [courses, continuing] = await Promise.all([
    api("/api/courses"),
    api("/api/continue-watching"),
  ]);
  state.courses = courses;
  renderContinueWatching(continuing);
  renderCourseGrid();
}

function renderContinueWatching(item) {
  const wrap = el("continue-watching-wrap");
  wrap.innerHTML = "";
  if (!item) return;

  const h = document.createElement("h2");
  h.className = "section-title";
  h.textContent = "Continuar assistindo";
  wrap.appendChild(h);

  const row = document.createElement("div");
  row.className = "continue-row";
  const card = document.createElement("div");
  card.className = "card elev-sm continue-card";
  card.innerHTML = `
    <div class="continue-thumb"><i class="ph-fill ph-play-circle"></i></div>
    <div class="continue-body">
      <div class="card-meta">${escapeHtml(item.course_name)}</div>
      <div class="card-title">${escapeHtml(item.file_name)}</div>
      <div class="progress-bar thin"><span style="width:${item.watched_percent}%"></span></div>
    </div>`;
  card.addEventListener("click", () => openCourse(item.course_id, item.id));
  row.appendChild(card);
  wrap.appendChild(row);
}

function renderCourseGrid() {
  const grid = el("course-grid");
  grid.innerHTML = "";
  const term = state.searchTerm.trim().toLowerCase();
  const filtered = state.courses.filter((c) => c.name.toLowerCase().includes(term));

  if (filtered.length === 0) {
    grid.innerHTML = `<div class="empty-state">${
      state.courses.length === 0
        ? "Nenhum curso ainda. Clique em “Adicionar curso” para começar."
        : "Nenhum curso corresponde à busca."
    }</div>`;
    return;
  }

  for (const c of filtered) {
    const card = document.createElement("div");
    card.className = "card course-card elev-sm";
    const iconHtml = c.cover_url
      ? `<img class="course-icon course-icon-img" src="${c.cover_url}" />`
      : `<div class="course-icon"><i class="ph ph-folder-open"></i></div>`;
    card.innerHTML = `
      <div class="course-card-actions">
        <i class="ph ph-pencil-simple" title="Editar curso"></i>
        <i class="ph ph-trash" title="Excluir curso"></i>
      </div>
      <div class="course-card-head">
        ${iconHtml}
        <div style="min-width:0;">
          <div class="card-title">${escapeHtml(c.name)}</div>
          <div class="card-meta">Pasta local</div>
        </div>
      </div>
      ${c.description ? `<div class="card-body course-description">${escapeHtml(c.description)}</div>` : ""}
      <div class="card-body">${c.completed_videos} de ${c.total_videos} aulas concluídas</div>
      <div class="progress-bar"><span style="width:${c.progress_percent}%"></span></div>`;
    card.addEventListener("click", () => openCourse(c.id));
    card.querySelector(".ph-pencil-simple").addEventListener("click", (e) => {
      e.stopPropagation();
      openCourseEditDialog(c);
    });
    card.querySelector(".ph-trash").addEventListener("click", (e) => {
      e.stopPropagation();
      deleteCourseFlow(c, { fromPlayerView: false });
    });
    grid.appendChild(card);
  }
}

el("search-input").addEventListener("input", (e) => {
  state.searchTerm = e.target.value;
  renderCourseGrid();
});
el("brand-link").addEventListener("click", () => {
  stopPlayer();
  loadLibrary().catch((e) => showToast(e.message));
});

/* ───────────────── player view: course sidebar ───────────────── */

async function openCourse(courseId, autoplayVideoId) {
  let course = state.courses.find((c) => c.id === courseId);
  if (!course) {
    state.courses = await api("/api/courses");
    course = state.courses.find((c) => c.id === courseId);
  }
  state.currentCourseId = courseId;
  state.currentCourse = course;
  state.filter = "all";
  state.videoSearchTerm = "";
  state.videoPage = 0;
  el("video-search-input").value = "";
  document.querySelectorAll(".filter-btn").forEach((b) => b.classList.toggle("active", b.dataset.filter === "all"));

  showView("player");
  stopPlayer();
  renderCourseHeader();
  await loadVideos();

  const target = autoplayVideoId
    ? state.videos.find((v) => v.id === autoplayVideoId)
    : state.videos.find((v) => !v.is_completed) || state.videos[0];
  if (target) loadVideoIntoPlayer(target);
}

function renderCourseHeader() {
  const c = state.currentCourse;
  el("course-title").textContent = c.name;
  el("course-meta").textContent = `Pasta local · ${c.completed_videos}/${c.total_videos} aulas`;
  el("course-progress-bar").style.width = `${c.progress_percent}%`;
}

async function loadVideos() {
  state.videos = await api(`/api/courses/${state.currentCourseId}/videos`);
  renderSidebarList();
}

function getFilteredVideos() {
  return state.videos.filter((v) => {
    if (state.filter === "pending") return !v.is_completed;
    if (state.filter === "completed") return v.is_completed;
    return true;
  });
}

const SIDEBAR_PAGE_SIZE = 60;

function getVisibleVideos() {
  const term = state.videoSearchTerm.trim().toLowerCase();
  const filtered = getFilteredVideos();
  if (!term) return filtered;
  return filtered.filter((v) => (v.display_name || v.file_name).toLowerCase().includes(term));
}

function renderSidebarList() {
  const list = el("sidebar-list");
  list.innerHTML = "";
  const visible = getVisibleVideos();

  if (visible.length === 0) {
    list.innerHTML = `<div class="empty-state">Nenhuma aula encontrada.</div>`;
    el("sidebar-pagination").innerHTML = "";
    updateNavButtons();
    return;
  }

  const totalPages = Math.max(1, Math.ceil(visible.length / SIDEBAR_PAGE_SIZE));
  state.videoPage = Math.min(state.videoPage, totalPages - 1);
  const pageItems = visible.slice(
    state.videoPage * SIDEBAR_PAGE_SIZE,
    (state.videoPage + 1) * SIDEBAR_PAGE_SIZE
  );

  const groups = new Map();
  for (const v of pageItems) {
    const key = v.module || "";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(v);
  }

  for (const [module, items] of groups) {
    if (module) {
      const label = document.createElement("div");
      label.className = "sidebar-module";
      label.textContent = module;
      list.appendChild(label);
    }
    for (const v of items) {
      list.appendChild(renderSidebarItem(v));
    }
  }

  renderSidebarPagination(visible.length, totalPages);
  updateNavButtons();
}

function renderSidebarPagination(total, totalPages) {
  const pag = el("sidebar-pagination");
  if (totalPages <= 1) {
    pag.innerHTML = "";
    return;
  }
  pag.innerHTML = `
    <button id="sidebar-page-prev">‹ Anterior</button>
    <span>${state.videoPage + 1} / ${totalPages} · ${total} aulas</span>
    <button id="sidebar-page-next">Próxima ›</button>
  `;
  const prevBtn = pag.querySelector("#sidebar-page-prev");
  const nextBtn = pag.querySelector("#sidebar-page-next");
  prevBtn.disabled = state.videoPage === 0;
  nextBtn.disabled = state.videoPage >= totalPages - 1;
  prevBtn.addEventListener("click", () => {
    state.videoPage--;
    renderSidebarList();
  });
  nextBtn.addEventListener("click", () => {
    state.videoPage++;
    renderSidebarList();
  });
}

el("video-search-input").addEventListener("input", (e) => {
  state.videoSearchTerm = e.target.value;
  state.videoPage = 0;
  renderSidebarList();
});

/* ───────────────── video CRUD: add avulso / edit / delete ───────────────── */

el("add-video-btn").addEventListener("click", () => {
  el("video-add-file").value = "";
  el("video-add-error").classList.add("hidden");
  el("video-add-progress").classList.add("hidden");
  el("video-add-dialog").classList.remove("hidden");
});
el("video-add-cancel").addEventListener("click", () => {
  el("video-add-dialog").classList.add("hidden");
});
el("video-add-save").addEventListener("click", async () => {
  const file = el("video-add-file").files[0];
  const errEl = el("video-add-error");
  errEl.classList.add("hidden");
  if (!file) {
    errEl.textContent = "Selecione um arquivo de vídeo.";
    errEl.classList.remove("hidden");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  el("video-add-progress").classList.remove("hidden");
  el("video-add-save").disabled = true;
  try {
    const res = await fetch(`/api/courses/${state.currentCourseId}/videos`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || res.statusText);
    }
    el("video-add-dialog").classList.add("hidden");
    await loadVideos();
    showToast("Vídeo anexado à playlist.");
  } catch (e) {
    errEl.textContent = e.message;
    errEl.classList.remove("hidden");
  } finally {
    el("video-add-progress").classList.add("hidden");
    el("video-add-save").disabled = false;
  }
});

let videoEditTargetId = null;

function openVideoEditDialog(v) {
  videoEditTargetId = v.id;
  el("video-edit-title").value = v.display_title || "";
  el("video-edit-title").placeholder = v.file_name;
  el("video-edit-order").value = v.sort_order;
  el("video-edit-error").classList.add("hidden");
  el("video-edit-dialog").classList.remove("hidden");
}
el("video-edit-cancel").addEventListener("click", () => {
  el("video-edit-dialog").classList.add("hidden");
});
el("video-edit-save").addEventListener("click", async () => {
  const displayTitle = el("video-edit-title").value.trim() || null;
  const sortOrder = el("video-edit-order").value === "" ? null : parseInt(el("video-edit-order").value, 10);
  try {
    await api(`/api/videos/${videoEditTargetId}`, {
      method: "PUT",
      body: JSON.stringify({ display_title: displayTitle, sort_order: sortOrder }),
    });
    el("video-edit-dialog").classList.add("hidden");
    await loadVideos();
    showToast("Aula atualizada.");
  } catch (e) {
    el("video-edit-error").textContent = e.message;
    el("video-edit-error").classList.remove("hidden");
  }
});

function deleteVideoFlow(v) {
  const wasCurrent = v.id === state.currentVideoId;
  showConfirmDelete(
    v.display_name || v.file_name,
    async () => {
      await api(`/api/videos/${v.id}`, { method: "DELETE" });
      if (wasCurrent) stopPlayer();
      await loadVideos();
      const updated = await api("/api/courses");
      state.courses = updated;
      const c = updated.find((c) => c.id === state.currentCourseId);
      if (c) { state.currentCourse = c; renderCourseHeader(); }
    },
    async () => {
      await api(`/api/videos/${v.id}/restore`, { method: "POST" });
      await loadVideos();
    }
  );
}

function updateNavButtons() {
  const list = getFilteredVideos();
  const idx = list.findIndex((v) => v.id === state.currentVideoId);
  const noPrev = idx <= 0;
  const noNext = idx === -1 || idx >= list.length - 1;
  el("prev-video-btn").disabled = noPrev;
  el("next-video-btn").disabled = noNext;
  el("fs-prev-btn").disabled = noPrev;
  el("fs-next-btn").disabled = noNext;
}

function renderSidebarItem(v) {
  const row = document.createElement("div");
  const isActive = v.id === state.currentVideoId;
  row.className = "sidebar-item" + (v.is_completed ? " completed" : "") + (isActive ? " active" : "");

  const checkClass = v.is_completed ? "ph-fill ph-check-circle" : isActive ? "ph ph-play-circle" : "ph ph-circle";
  const pct = Math.round(v.watched_percent || 0);
  const durationLabel = v.duration_label + (pct > 0 && pct < 100 ? ` · ${pct}%` : "");

  row.innerHTML = `
    <i class="check-icon ${checkClass}"></i>
    <div class="sidebar-item-info">
      <div class="sidebar-item-name">${escapeHtml(v.display_name || v.file_name)}${v.is_manual ? ' <i class="ph ph-link-simple" title="Vídeo avulso" style="font-size:11px;"></i>' : ""}</div>
      <div class="sidebar-item-duration">${durationLabel}</div>
    </div>
    <i class="fav-icon ${v.is_favorite ? "ph-fill ph-star active" : "ph ph-star"}"></i>
    <div class="sidebar-item-actions">
      <i class="ph ph-pencil-simple" title="Editar aula"></i>
      <i class="ph ph-trash" title="Excluir aula"></i>
    </div>
  `;
  row.addEventListener("click", () => loadVideoIntoPlayer(v));
  row.querySelector(".fav-icon").addEventListener("click", (e) => {
    e.stopPropagation();
    toggleFavorite(v.id);
  });
  row.querySelector(".ph-pencil-simple").addEventListener("click", (e) => {
    e.stopPropagation();
    openVideoEditDialog(v);
  });
  row.querySelector(".sidebar-item-actions .ph-trash").addEventListener("click", (e) => {
    e.stopPropagation();
    deleteVideoFlow(v);
  });
  return row;
}

async function toggleFavorite(videoId) {
  const result = await api(`/api/videos/${videoId}/favorite`, { method: "POST" });
  const v = state.videos.find((v) => v.id === videoId);
  if (v) v.is_favorite = result.is_favorite;
  renderSidebarList();
}

document.querySelectorAll(".filter-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.filter = btn.dataset.filter;
    state.videoPage = 0;
    document.querySelectorAll(".filter-btn").forEach((b) => b.classList.toggle("active", b === btn));
    renderSidebarList();
  });
});

el("back-btn").addEventListener("click", () => {
  stopPlayer();
  loadLibrary().catch((e) => showToast(e.message));
});

el("refresh-course-btn").addEventListener("click", async () => {
  try {
    state.currentCourse = await api(`/api/courses/${state.currentCourseId}/refresh`, { method: "POST" });
    renderCourseHeader();
    await loadVideos();
    showToast("Curso atualizado.");
  } catch (e) {
    showToast(e.message);
  }
});

el("edit-course-btn").addEventListener("click", () => {
  openCourseEditDialog(state.currentCourse);
});

el("remove-course-btn").addEventListener("click", () => {
  deleteCourseFlow(state.currentCourse, { fromPlayerView: true });
});

function deleteCourseFlow(course, { fromPlayerView }) {
  showConfirmDelete(
    course.name,
    async () => {
      await api(`/api/courses/${course.id}`, { method: "DELETE" });
      if (fromPlayerView) stopPlayer();
      await loadLibrary();
    },
    async () => {
      await api(`/api/courses/${course.id}/restore`, { method: "POST" });
      await loadLibrary();
    }
  );
}

/* ───────────────── course edit (name / description / cover) ───────────────── */

let courseEditTargetId = null;
let courseEditCoverFile = null;

function openCourseEditDialog(course) {
  courseEditTargetId = course.id;
  courseEditCoverFile = null;
  el("course-edit-title").textContent = `Editar curso — ${course.name}`;
  el("course-edit-name").value = course.name;
  el("course-edit-description").value = course.description || "";
  el("course-edit-error").classList.add("hidden");
  el("course-edit-cover-input").value = "";
  if (course.cover_url) {
    el("course-edit-cover-preview").src = `${course.cover_url}?t=${Date.now()}`;
    el("course-edit-cover-preview").classList.remove("hidden");
    el("course-edit-cover-empty").classList.add("hidden");
  } else {
    el("course-edit-cover-preview").classList.add("hidden");
    el("course-edit-cover-empty").classList.remove("hidden");
  }
  el("course-edit-dialog").classList.remove("hidden");
}

el("course-edit-cover-input").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  courseEditCoverFile = file;
  const reader = new FileReader();
  reader.onload = () => {
    el("course-edit-cover-preview").src = reader.result;
    el("course-edit-cover-preview").classList.remove("hidden");
    el("course-edit-cover-empty").classList.add("hidden");
  };
  reader.readAsDataURL(file);
});

el("course-edit-cancel").addEventListener("click", () => {
  el("course-edit-dialog").classList.add("hidden");
});

el("course-edit-save").addEventListener("click", async () => {
  const name = el("course-edit-name").value.trim();
  const description = el("course-edit-description").value.trim();
  const errEl = el("course-edit-error");
  errEl.classList.add("hidden");
  if (!name) {
    errEl.textContent = "Nome é obrigatório.";
    errEl.classList.remove("hidden");
    return;
  }
  try {
    await api(`/api/courses/${courseEditTargetId}`, {
      method: "PUT",
      body: JSON.stringify({ name, description: description || null }),
    });
    if (courseEditCoverFile) {
      const formData = new FormData();
      formData.append("file", courseEditCoverFile);
      const res = await fetch(`/api/courses/${courseEditTargetId}/cover`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || res.statusText);
      }
    }
    el("course-edit-dialog").classList.add("hidden");
    showToast("Curso atualizado.");

    const courses = await api("/api/courses");
    state.courses = courses;
    if (!el("view-library").classList.contains("hidden")) {
      renderCourseGrid();
    } else if (state.currentCourseId === courseEditTargetId) {
      state.currentCourse = courses.find((c) => c.id === courseEditTargetId);
      renderCourseHeader();
    }
  } catch (e) {
    errEl.textContent = e.message;
    errEl.classList.remove("hidden");
  }
});

/* ───────────────── player ───────────────── */

function stopPlayer() {
  const video = el("player-video");
  video.pause();
  video.removeAttribute("src");
  video.load();
  video.classList.add("hidden");
  el("player-empty").classList.remove("hidden");
  state.currentVideoId = null;
  clearInterval(state.saveTimer);
  el("player-video-title").textContent = "";
  el("time-label").textContent = "--:-- / --:--";
  el("seek-range").value = 0;
  el("player-surface").classList.remove("is-mini");
  el("prev-video-btn").disabled = true;
  el("next-video-btn").disabled = true;
  el("fs-prev-btn").disabled = true;
  el("fs-next-btn").disabled = true;
  syncPlayIcon(video);
}

/* Icon is always derived from the real video state (videoEl.paused) instead
   of being set optimistically — browsers don't reliably fire a matching
   play/pause event when a play() request gets interrupted (AbortError), which
   used to leave the icon showing the wrong symbol. */
function syncPlayIcon(videoEl) {
  const cls = videoEl.paused ? "ph-fill ph-play" : "ph-fill ph-pause";
  el("play-icon").className = cls;
  el("fs-play-icon").className = cls;
}

function togglePlayback(videoEl) {
  if (videoEl.paused) {
    videoEl.play().catch(() => syncPlayIcon(videoEl));
  } else {
    videoEl.pause();
  }
}

/* Sticky player + floating mini-player: the surface sticks to the top of
   .player-main while scrolling its own content (controls/tabs/notes). Once
   scrolled far enough that the sentinel above it leaves .player-main's
   viewport, it detaches into a fixed corner mini-player instead. */
let miniPlayerObserver = null;

function setupMiniPlayerObserver() {
  if (miniPlayerObserver) return;
  const surface = el("player-surface");
  const sentinel = el("player-surface-sentinel");
  miniPlayerObserver = new IntersectionObserver(
    (entries) => {
      const entry = entries[entries.length - 1];
      if (!state.currentVideoId) {
        surface.classList.remove("is-mini");
        return;
      }
      surface.classList.toggle("is-mini", !entry.isIntersecting);
    },
    { root: el("player-main"), threshold: 0 }
  );
  miniPlayerObserver.observe(sentinel);
}

el("mini-restore-btn").addEventListener("click", (e) => {
  e.stopPropagation();
  el("player-surface").classList.remove("is-mini");
  el("player-surface-sentinel").scrollIntoView({ behavior: "smooth", block: "start" });
});

function loadVideoIntoPlayer(v) {
  const videoEl = el("player-video");
  clearInterval(state.saveTimer);
  state.currentVideoId = v.id;

  el("player-empty").classList.add("hidden");
  videoEl.classList.remove("hidden");
  el("player-video-title").textContent = v.file_name;
  updateCompleteButton(v.is_completed);

  videoEl.src = `/api/videos/${v.id}/stream`;
  videoEl.playbackRate = parseFloat(el("speed-select").value);
  syncPlayIcon(videoEl);
  videoEl.onloadedmetadata = () => {
    if (!v.is_completed && v.position_seconds > 0) {
      videoEl.currentTime = v.position_seconds;
    }
    el("seek-range").max = videoEl.duration || 0;
    el("fs-seek-range").max = videoEl.duration || 0;
  };
  videoEl.ontimeupdate = () => {
    const timeText = `${formatSeconds(videoEl.currentTime)} / ${formatSeconds(videoEl.duration)}`;
    el("seek-range").value = videoEl.currentTime;
    el("time-label").textContent = timeText;
    el("note-time-label").textContent = `em ${formatSeconds(videoEl.currentTime)}`;
    el("fs-seek-range").value = videoEl.currentTime;
    el("fs-time-label").textContent = timeText;
  };
  videoEl.onclick = () => togglePlayback(videoEl);
  videoEl.onplay = () => syncPlayIcon(videoEl);
  videoEl.onpause = () => { syncPlayIcon(videoEl); saveProgress(videoEl); };
  videoEl.onended = () => { syncPlayIcon(videoEl); saveProgress(videoEl); };

  state.saveTimer = setInterval(() => {
    if (!videoEl.paused) saveProgress(videoEl);
  }, 4000);

  loadNotes(v.id);
  if (state.activeTab === "materials") loadMaterials();
  renderSidebarList();
}

async function saveProgress(videoEl) {
  const videoId = state.currentVideoId;
  if (!videoId || !videoEl.duration) return;
  try {
    const result = await api(`/api/videos/${videoId}/progress`, {
      method: "POST",
      body: JSON.stringify({
        position_seconds: videoEl.currentTime,
        duration_seconds: videoEl.duration,
      }),
    });
    const v = state.videos.find((v) => v.id === videoId);
    if (v) {
      v.position_seconds = result.position_seconds;
      v.watched_percent = result.watched_percent;
      const wasCompleted = v.is_completed;
      v.is_completed = result.is_completed;
      renderSidebarList();
      if (wasCompleted !== v.is_completed) updateCompleteButton(v.is_completed);
    }
  } catch (_) {}
}

function updateCompleteButton(isCompleted) {
  const btn = el("complete-btn");
  btn.classList.toggle("btn-secondary", isCompleted);
  btn.classList.toggle("btn-ghost", !isCompleted);
  btn.innerHTML = isCompleted
    ? '<i class="ph ph-check-circle"></i> Concluída'
    : '<i class="ph ph-check-circle"></i> Marcar como concluída';
}

function goToPrevVideo() {
  const list = getFilteredVideos();
  const idx = list.findIndex((v) => v.id === state.currentVideoId);
  if (idx > 0) loadVideoIntoPlayer(list[idx - 1]);
}
function goToNextVideo() {
  const list = getFilteredVideos();
  const idx = list.findIndex((v) => v.id === state.currentVideoId);
  if (idx !== -1 && idx < list.length - 1) loadVideoIntoPlayer(list[idx + 1]);
}

el("play-btn").addEventListener("click", () => {
  togglePlayback(el("player-video"));
});
el("prev-video-btn").addEventListener("click", goToPrevVideo);
el("next-video-btn").addEventListener("click", goToNextVideo);
el("skip-back-btn").addEventListener("click", () => {
  const videoEl = el("player-video");
  videoEl.currentTime = Math.max(0, videoEl.currentTime - 10);
});
el("skip-fwd-btn").addEventListener("click", () => {
  const videoEl = el("player-video");
  videoEl.currentTime = Math.min(videoEl.duration || Infinity, videoEl.currentTime + 10);
});
el("seek-range").addEventListener("input", (e) => {
  el("player-video").currentTime = parseFloat(e.target.value);
});
el("speed-select").addEventListener("change", (e) => {
  el("player-video").playbackRate = parseFloat(e.target.value);
});
el("fullscreen-btn").addEventListener("click", () => {
  const surface = el("player-surface");
  if (!document.fullscreenElement) surface.requestFullscreen?.().catch(() => {});
  else document.exitFullscreen?.();
});

/* ───────── fullscreen overlay controls (auto-hide on inactivity) ───────── */
const FS_IDLE_DELAY_MS = 2500;
let fsIdleTimer = null;
let fsNotePopoverOpen = false;

function isPlayerFullscreen() {
  return document.fullscreenElement === el("player-surface");
}

function resetFsIdleTimer() {
  const surface = el("player-surface");
  surface.classList.remove("fs-idle");
  clearTimeout(fsIdleTimer);
  if (!isPlayerFullscreen() || fsNotePopoverOpen) return;
  fsIdleTimer = setTimeout(() => {
    if (isPlayerFullscreen() && !fsNotePopoverOpen) surface.classList.add("fs-idle");
  }, FS_IDLE_DELAY_MS);
}

function openFsNotePopover() {
  const videoEl = el("player-video");
  if (!state.currentVideoId) return;
  fsNotePopoverOpen = true;
  el("fs-note-time").dataset.seconds = videoEl.currentTime;
  el("fs-note-time").textContent = formatSeconds(videoEl.currentTime);
  el("fs-note-input").value = "";
  el("fs-note-popover").classList.remove("hidden");
  resetFsIdleTimer();
  el("fs-note-input").focus();
}

function closeFsNotePopover() {
  fsNotePopoverOpen = false;
  el("fs-note-popover").classList.add("hidden");
  resetFsIdleTimer();
}

el("fs-play-btn").addEventListener("click", () => togglePlayback(el("player-video")));
el("fs-prev-btn").addEventListener("click", goToPrevVideo);
el("fs-next-btn").addEventListener("click", goToNextVideo);
el("fs-seek-range").addEventListener("input", (e) => {
  el("player-video").currentTime = parseFloat(e.target.value);
});
el("fs-speed-select").addEventListener("change", (e) => {
  const rate = parseFloat(e.target.value);
  el("player-video").playbackRate = rate;
  el("speed-select").value = e.target.value;
});
el("speed-select").addEventListener("change", (e) => {
  el("fs-speed-select").value = e.target.value;
});
el("fs-exit-btn").addEventListener("click", () => document.exitFullscreen?.());

el("fs-note-btn").addEventListener("click", () => {
  if (fsNotePopoverOpen) closeFsNotePopover();
  else openFsNotePopover();
});
el("fs-note-save-btn").addEventListener("click", async () => {
  const text = el("fs-note-input").value.trim();
  const seconds = parseFloat(el("fs-note-time").dataset.seconds || "0");
  await saveNoteAt(seconds, text);
  closeFsNotePopover();
});
el("fs-note-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") el("fs-note-save-btn").click();
  else if (e.key === "Escape") closeFsNotePopover();
});

document.addEventListener("fullscreenchange", () => {
  if (isPlayerFullscreen()) {
    resetFsIdleTimer();
  } else {
    clearTimeout(fsIdleTimer);
    el("player-surface").classList.remove("fs-idle");
    closeFsNotePopover();
  }
});
["mousemove", "mousedown", "keydown", "touchstart"].forEach((evt) => {
  el("player-surface").addEventListener(evt, () => {
    if (isPlayerFullscreen()) resetFsIdleTimer();
  });
});
el("complete-btn").addEventListener("click", async () => {
  if (!state.currentVideoId) return;
  const v = state.videos.find((v) => v.id === state.currentVideoId);
  if (!v) return;
  const result = await api(`/api/videos/${v.id}/completed`, {
    method: "POST",
    body: JSON.stringify({ completed: !v.is_completed }),
  });
  v.is_completed = result.is_completed;
  v.position_seconds = result.position_seconds;
  v.watched_percent = result.watched_percent;
  updateCompleteButton(v.is_completed);
  renderSidebarList();
  const courses = await api("/api/courses");
  const updated = courses.find((c) => c.id === state.currentCourseId);
  if (updated) { state.currentCourse = updated; renderCourseHeader(); }
});

document.addEventListener("keydown", (e) => {
  if (el("view-player").classList.contains("hidden")) return;
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea") return;
  const videoEl = el("player-video");
  if (e.code === "Space") { e.preventDefault(); el("play-btn").click(); }
  else if (e.code === "ArrowLeft") { videoEl.currentTime = Math.max(0, videoEl.currentTime - 10); }
  else if (e.code === "ArrowRight") { videoEl.currentTime = Math.min(videoEl.duration || Infinity, videoEl.currentTime + 10); }
  else if (e.key.toLowerCase() === "f") { el("fullscreen-btn").click(); }
});

/* ───────────────── tabs: notes / course notes / materials ───────────────── */

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.activeTab = btn.dataset.tab;
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
    el("tab-notes").classList.toggle("hidden", state.activeTab !== "notes");
    el("tab-course-notes").classList.toggle("hidden", state.activeTab !== "course-notes");
    el("tab-materials").classList.toggle("hidden", state.activeTab !== "materials");
    if (state.activeTab === "course-notes") loadCourseNote();
    if (state.activeTab === "materials") loadMaterials();
  });
});

async function loadNotes(videoId) {
  const notes = await api(`/api/videos/${videoId}/notes`);
  const list = el("notes-list");
  list.innerHTML = "";
  if (notes.length === 0) {
    list.innerHTML = `<div class="empty-state">Nenhuma anotação ainda nesta aula.</div>`;
    return;
  }
  for (const n of notes) {
    list.appendChild(renderNoteRow(n, videoId));
  }
}

function renderNoteRow(n, videoId) {
  const row = document.createElement("div");
  row.className = "note-row";
  row.innerHTML = `
    <button class="tag tag-accent">${n.time_label}</button>
    <div class="note-row-text">${escapeHtml(n.text)}</div>
    <div class="row-actions">
      <i class="ph ph-pencil-simple" title="Editar"></i>
      <i class="ph ph-trash" title="Excluir"></i>
    </div>`;
  row.querySelector(".tag").addEventListener("click", () => {
    el("player-video").currentTime = n.time_seconds;
  });
  row.querySelector(".ph-pencil-simple").addEventListener("click", () => {
    row.innerHTML = `
      <button class="tag tag-accent">${n.time_label}</button>
      <div class="inline-edit-row">
        <textarea class="input note-edit-textarea" style="min-height:60px;">${escapeHtml(n.text)}</textarea>
      </div>
      <div class="row-actions">
        <i class="ph ph-check" title="Salvar"></i>
        <i class="ph ph-x" title="Cancelar"></i>
      </div>`;
    row.querySelector(".tag").addEventListener("click", () => {
      el("player-video").currentTime = n.time_seconds;
    });
    row.querySelector(".ph-check").addEventListener("click", async () => {
      const newText = row.querySelector(".note-edit-textarea").value.trim();
      if (!newText) return;
      try {
        await api(`/api/notes/${n.id}`, { method: "PUT", body: JSON.stringify({ text: newText }) });
        loadNotes(videoId);
      } catch (e) {
        showToast(e.message);
      }
    });
    row.querySelector(".ph-x").addEventListener("click", () => loadNotes(videoId));
  });
  row.querySelector(".row-actions .ph-trash").addEventListener("click", () => {
    showConfirmDelete(
      `anotação em ${n.time_label}`,
      async () => {
        await api(`/api/notes/${n.id}`, { method: "DELETE" });
        loadNotes(videoId);
      },
      async () => {
        await api(`/api/notes/${n.id}/restore`, { method: "POST" });
        loadNotes(videoId);
      }
    );
  });
  return row;
}

async function saveNoteAt(timeSeconds, text) {
  if (!text || !state.currentVideoId) return;
  await api(`/api/videos/${state.currentVideoId}/notes`, {
    method: "POST",
    body: JSON.stringify({ time_seconds: timeSeconds, text }),
  });
  loadNotes(state.currentVideoId);
}

el("add-note-btn").addEventListener("click", async () => {
  const input = el("note-input");
  const text = input.value.trim();
  await saveNoteAt(el("player-video").currentTime, text);
  input.value = "";
});
el("note-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") el("add-note-btn").click();
});

async function loadCourseNote() {
  const data = await api(`/api/courses/${state.currentCourseId}/notes`);
  el("course-note-textarea").value = data.text;
}
el("course-note-textarea").addEventListener("input", (e) => {
  clearTimeout(state.courseNoteTimer);
  const text = e.target.value;
  const courseId = state.currentCourseId;
  state.courseNoteTimer = setTimeout(() => {
    api(`/api/courses/${courseId}/notes`, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }).catch(() => {});
  }, 500);
});

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function materialIconClass(name, mimeType) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  if (mimeType?.startsWith("image/") || ["png", "jpg", "jpeg", "gif", "webp"].includes(ext)) return "ph ph-image";
  if (mimeType?.startsWith("audio/") || ["mp3", "wav", "m4a", "ogg", "flac", "aac"].includes(ext)) return "ph ph-file-audio";
  if (ext === "pdf") return "ph ph-file-pdf";
  return "ph ph-file";
}

async function loadMaterials() {
  const [videoMaterials, courseMaterials] = await Promise.all([
    state.currentVideoId ? api(`/api/videos/${state.currentVideoId}/materials`) : Promise.resolve([]),
    api(`/api/courses/${state.currentCourseId}/materials`),
  ]);
  el("materials-count").textContent = videoMaterials.length + courseMaterials.length;
  renderVideoMaterials(videoMaterials);
  renderCourseMaterials(courseMaterials);
}

function renderVideoMaterials(materials) {
  const list = el("video-materials-list");
  list.innerHTML = "";
  if (materials.length === 0) {
    list.innerHTML = `<div class="empty-state">Nenhum arquivo anexado a esta aula.</div>`;
    return;
  }
  for (const m of materials) {
    list.appendChild(renderVideoMaterialRow(m));
  }
}

function renderVideoMaterialRow(m) {
  const row = document.createElement("div");
  row.className = "material-row";
  row.innerHTML = `
    <i class="${materialIconClass(m.file_name, m.mime_type)}"></i>
    <div class="material-row-name">${escapeHtml(m.file_name)}</div>
    <span class="text-muted" style="font-size:11px;">${formatBytes(m.size_bytes)}</span>
    <a href="/api/materials/${m.id}/download" title="Baixar"><i class="ph ph-download-simple"></i></a>
    <i class="ph ph-pencil-simple" title="Renomear"></i>
    <i class="ph ph-trash" title="Remover"></i>`;
  row.querySelector(".ph-pencil-simple").addEventListener("click", () => {
    const nameEl = row.querySelector(".material-row-name");
    nameEl.outerHTML = `<input class="input material-rename-input" style="flex:1;min-height:28px;padding:2px 6px;" value="${escapeHtml(m.file_name)}" />`;
    const input = row.querySelector(".material-rename-input");
    input.focus();
    input.select();
    let saved = false;
    const save = async () => {
      if (saved) return;
      saved = true;
      const newName = input.value.trim();
      if (!newName || newName === m.file_name) {
        loadMaterials();
        return;
      }
      try {
        await api(`/api/materials/${m.id}`, { method: "PUT", body: JSON.stringify({ file_name: newName }) });
        loadMaterials();
      } catch (e) {
        showToast(e.message);
      }
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") save();
      if (e.key === "Escape") {
        saved = true;
        loadMaterials();
      }
    });
    input.addEventListener("blur", save);
  });
  row.querySelector(".ph-trash").addEventListener("click", () => {
    showConfirmDelete(
      m.file_name,
      async () => {
        await api(`/api/materials/${m.id}`, { method: "DELETE" });
        loadMaterials();
      },
      async () => {
        await api(`/api/materials/${m.id}/restore`, { method: "POST" });
        loadMaterials();
      }
    );
  });
  return row;
}

function renderCourseMaterials(materials) {
  const list = el("materials-list");
  list.innerHTML = "";
  if (materials.length === 0) {
    list.innerHTML = `<div class="empty-state">Nenhum material encontrado nesta pasta.</div>`;
    return;
  }
  for (const m of materials) {
    const a = document.createElement("a");
    a.className = "material-row";
    a.href = `/api/courses/${state.currentCourseId}/materials/download?path=${encodeURIComponent(m.relative_path)}`;
    a.innerHTML = `
      <i class="${materialIconClass(m.name)}"></i>
      <div class="material-row-name">${escapeHtml(m.name)}</div>
      <i class="ph ph-download-simple"></i>`;
    list.appendChild(a);
  }
}

el("material-upload-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file || !state.currentVideoId) return;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await fetch(`/api/videos/${state.currentVideoId}/materials`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || res.statusText);
    }
    loadMaterials();
    showToast("Material anexado.");
  } catch (err) {
    showToast(err.message);
  }
});

/* ───────────────── add course / folder browser ───────────────── */

el("add-course-btn").addEventListener("click", () => openBrowseDialog());
el("browse-cancel-btn").addEventListener("click", () => el("browse-dialog").classList.add("hidden"));

async function openBrowseDialog() {
  el("browse-dialog").classList.remove("hidden");
  el("browse-manual-path").value = "";
  await browseTo(state.browsePath);
}

async function browseTo(path) {
  const query = path ? `?path=${encodeURIComponent(path)}` : "";
  const data = await api(`/api/browse${query}`);
  state.browsePath = data.path;
  el("browse-path").textContent = data.path;
  el("browse-manual-path").value = data.path;

  const list = el("browse-list");
  list.innerHTML = "";

  if (data.parent) {
    const li = document.createElement("li");
    li.innerHTML = `<button><i class="ph ph-arrow-up"></i> ..</button>`;
    li.querySelector("button").addEventListener("click", () => browseTo(data.parent));
    list.appendChild(li);
  }

  for (const entry of data.entries) {
    const li = document.createElement("li");
    li.innerHTML = `<button><i class="ph ph-folder"></i>${escapeHtml(entry.name)}</button>`;
    li.querySelector("button").addEventListener("click", () => browseTo(entry.path));
    list.appendChild(li);
  }
}

el("browse-manual-path").addEventListener("keydown", (e) => {
  if (e.key === "Enter") browseTo(el("browse-manual-path").value);
});

el("browse-select-btn").addEventListener("click", async () => {
  const folderPath = el("browse-manual-path").value || state.browsePath;
  try {
    await api("/api/courses", {
      method: "POST",
      body: JSON.stringify({ folder_path: folderPath }),
    });
    el("browse-dialog").classList.add("hidden");
    await loadLibrary();
    showToast("Curso adicionado.");
  } catch (e) {
    showToast(e.message);
  }
});

setupMiniPlayerObserver();

/* ───────────────── resizable sidebar ───────────────── */

(() => {
  const handle = el("sidebar-resize-handle");
  const layout = document.querySelector(".player-layout");
  const MIN_WIDTH = 220;
  const MAX_WIDTH = 560;
  let dragging = false;

  const setWidth = (px) => {
    const clamped = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, px));
    document.documentElement.style.setProperty("--sidebar-width", `${clamped}px`);
  };
  const onMove = (e) => {
    if (!dragging) return;
    setWidth(e.clientX - layout.getBoundingClientRect().left);
  };
  const stopDragging = () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove("dragging");
    layout.classList.remove("resizing");
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", stopDragging);
  };

  handle.addEventListener("mousedown", (e) => {
    e.preventDefault();
    dragging = true;
    handle.classList.add("dragging");
    layout.classList.add("resizing");
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", stopDragging);
  });
})();

loadLibrary().catch((e) => showToast(e.message));
