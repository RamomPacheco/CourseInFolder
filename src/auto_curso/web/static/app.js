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
    card.innerHTML = `
      <div class="course-card-head">
        <div class="course-icon"><i class="ph ph-folder-open"></i></div>
        <div style="min-width:0;">
          <div class="card-title">${escapeHtml(c.name)}</div>
          <div class="card-meta">Pasta local</div>
        </div>
      </div>
      <div class="card-body">${c.completed_videos} de ${c.total_videos} aulas concluídas</div>
      <div class="progress-bar"><span style="width:${c.progress_percent}%"></span></div>`;
    card.addEventListener("click", () => openCourse(c.id));
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

function renderSidebarList() {
  const list = el("sidebar-list");
  list.innerHTML = "";
  const filtered = state.videos.filter((v) => {
    if (state.filter === "pending") return !v.is_completed;
    if (state.filter === "completed") return v.is_completed;
    return true;
  });

  const groups = new Map();
  for (const v of filtered) {
    const key = v.module || "";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(v);
  }

  if (filtered.length === 0) {
    list.innerHTML = `<div class="empty-state">Nenhuma aula nesta lista.</div>`;
    return;
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
      <div class="sidebar-item-name">${escapeHtml(v.file_name)}</div>
      <div class="sidebar-item-duration">${durationLabel}</div>
    </div>
    <i class="fav-icon ${v.is_favorite ? "ph-fill ph-star active" : "ph ph-star"}"></i>
  `;
  row.addEventListener("click", () => loadVideoIntoPlayer(v));
  row.querySelector(".fav-icon").addEventListener("click", (e) => {
    e.stopPropagation();
    toggleFavorite(v.id);
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

el("remove-course-btn").addEventListener("click", async () => {
  if (!confirm(`Remover "${state.currentCourse.name}" da biblioteca? Os arquivos não são apagados.`)) return;
  await api(`/api/courses/${state.currentCourseId}`, { method: "DELETE" });
  stopPlayer();
  await loadLibrary();
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
}

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
  videoEl.onloadedmetadata = () => {
    if (!v.is_completed && v.position_seconds > 0) {
      videoEl.currentTime = v.position_seconds;
    }
    el("seek-range").max = videoEl.duration || 0;
  };
  videoEl.ontimeupdate = () => {
    el("seek-range").value = videoEl.currentTime;
    el("time-label").textContent = `${formatSeconds(videoEl.currentTime)} / ${formatSeconds(videoEl.duration)}`;
    el("note-time-label").textContent = `em ${formatSeconds(videoEl.currentTime)}`;
  };
  videoEl.onclick = () => {
    if (videoEl.paused) videoEl.play().catch(() => {});
    else videoEl.pause();
  };
  videoEl.onplay = () => el("play-icon").className = "ph-fill ph-pause";
  videoEl.onpause = () => { el("play-icon").className = "ph-fill ph-play"; saveProgress(videoEl); };
  videoEl.onended = () => saveProgress(videoEl);

  state.saveTimer = setInterval(() => {
    if (!videoEl.paused) saveProgress(videoEl);
  }, 4000);

  loadNotes(v.id);
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

el("play-btn").addEventListener("click", () => {
  const videoEl = el("player-video");
  if (videoEl.paused) videoEl.play().catch(() => {});
  else videoEl.pause();
});
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
    const row = document.createElement("div");
    row.className = "note-row";
    row.innerHTML = `
      <button class="tag tag-accent">${n.time_label}</button>
      <div class="note-row-text">${escapeHtml(n.text)}</div>
      <i class="ph ph-trash"></i>`;
    row.querySelector(".tag").addEventListener("click", () => {
      el("player-video").currentTime = n.time_seconds;
    });
    row.querySelector(".ph-trash").addEventListener("click", async () => {
      await api(`/api/notes/${n.id}`, { method: "DELETE" });
      loadNotes(videoId);
    });
    list.appendChild(row);
  }
}

el("add-note-btn").addEventListener("click", async () => {
  const input = el("note-input");
  const text = input.value.trim();
  if (!text || !state.currentVideoId) return;
  await api(`/api/videos/${state.currentVideoId}/notes`, {
    method: "POST",
    body: JSON.stringify({ time_seconds: el("player-video").currentTime, text }),
  });
  input.value = "";
  loadNotes(state.currentVideoId);
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

async function loadMaterials() {
  const materials = await api(`/api/courses/${state.currentCourseId}/materials`);
  el("materials-count").textContent = materials.length;
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
      <i class="ph ph-file"></i>
      <div class="material-row-name">${escapeHtml(m.name)}</div>
      <i class="ph ph-download-simple"></i>`;
    list.appendChild(a);
  }
}

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

loadLibrary().catch((e) => showToast(e.message));
