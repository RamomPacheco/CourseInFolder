"use strict";

const state = {
  courses: [],
  currentCourseId: null,
  currentCourseName: "",
  videos: [],
  filter: "all",
  currentVideoId: null,
  browsePath: null,
  searchTerm: "",
  saveTimer: null,
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
  setTimeout(() => toast.remove(), 3500);
}

function formatSeconds(total) {
  total = Math.max(0, Math.floor(total || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/* ───────────────── library view ───────────────── */

async function loadLibrary() {
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

  const card = document.createElement("div");
  card.className = "card continue-card elev-sm";
  card.innerHTML = `
    <div class="continue-thumb">
      <svg class="icon" style="width:28px;height:28px;color:var(--color-accent-100)" viewBox="0 0 24 24"><path d="M8 6v12l10-6-10-6Z" stroke-linejoin="round"/></svg>
    </div>
    <div class="continue-info">
      <div class="card-kicker">${escapeHtml(item.course_name)}</div>
      <div class="card-title">${escapeHtml(item.file_name)}</div>
      <div class="progress-bar"><span style="width:${item.watched_percent}%"></span></div>
    </div>`;
  card.addEventListener("click", () => openCourse(item.course_id, item.id));
  wrap.appendChild(card);
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
      <div class="card-title">${escapeHtml(c.name)}</div>
      <div class="card-meta">${c.completed_videos} de ${c.total_videos} aulas concluídas</div>
      <div class="progress-bar"><span style="width:${c.progress_percent}%"></span></div>`;
    card.addEventListener("click", () => openCourse(c.id));
    grid.appendChild(card);
  }
}

el("search-input").addEventListener("input", (e) => {
  state.searchTerm = e.target.value;
  renderCourseGrid();
});

/* ───────────────── course view ───────────────── */

async function openCourse(courseId, autoplayVideoId) {
  const course = state.courses.find((c) => c.id === courseId) || (await refreshOneCourse(courseId));
  state.currentCourseId = courseId;
  state.currentCourseName = course.name;
  state.filter = "all";
  document.querySelectorAll("#filter-seg button").forEach((b) => b.classList.toggle("active", b.dataset.filter === "all"));

  el("course-title").textContent = course.name;
  el("view-library").classList.add("hidden");
  el("view-course").classList.remove("hidden");
  stopPlayer();

  await loadVideos();
  if (autoplayVideoId) {
    const v = state.videos.find((v) => v.id === autoplayVideoId);
    if (v) loadVideoIntoPlayer(v);
  }
}

async function refreshOneCourse(courseId) {
  const list = await api("/api/courses");
  state.courses = list;
  return list.find((c) => c.id === courseId);
}

async function loadVideos() {
  state.videos = await api(`/api/courses/${state.currentCourseId}/videos`);
  renderVideoTable();
}

function renderVideoTable() {
  const tbody = el("video-tbody");
  tbody.innerHTML = "";
  const filtered = state.videos.filter((v) => {
    if (state.filter === "pending") return !v.is_completed;
    if (state.filter === "done") return v.is_completed;
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" class="empty-state">Nenhum vídeo nesta lista.</td></tr>`;
    return;
  }

  for (const v of filtered) {
    const tr = document.createElement("tr");
    tr.className = "video-row" + (v.id === state.currentVideoId ? " playing" : "");
    tr.innerHTML = `
      <td><input type="checkbox" ${v.is_completed ? "checked" : ""} data-video-id="${v.id}" /></td>
      <td class="video-name">${escapeHtml(v.file_name)}</td>
      <td>${v.duration_label}</td>
      <td class="video-progress"><div class="progress-bar"><span style="width:${v.watched_percent}%"></span></div></td>
    `;
    tr.querySelector("td.video-name").addEventListener("click", () => loadVideoIntoPlayer(v));
    tr.querySelector(".video-progress").addEventListener("click", () => loadVideoIntoPlayer(v));
    tr.querySelector("input[type=checkbox]").addEventListener("click", (e) => e.stopPropagation());
    tr.querySelector("input[type=checkbox]").addEventListener("change", (e) => toggleCompleted(v.id, e.target.checked));
    tbody.appendChild(tr);
  }
}

document.querySelectorAll("#filter-seg button").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.filter = btn.dataset.filter;
    document.querySelectorAll("#filter-seg button").forEach((b) => b.classList.toggle("active", b === btn));
    renderVideoTable();
  });
});

el("back-btn").addEventListener("click", async () => {
  stopPlayer();
  el("view-course").classList.add("hidden");
  el("view-library").classList.remove("hidden");
  await loadLibrary();
});

el("refresh-course-btn").addEventListener("click", async () => {
  try {
    await api(`/api/courses/${state.currentCourseId}/refresh`, { method: "POST" });
    await loadVideos();
    showToast("Curso atualizado.");
  } catch (e) {
    showToast(e.message);
  }
});

el("remove-course-btn").addEventListener("click", async () => {
  if (!confirm(`Remover "${state.currentCourseName}" da biblioteca? Os arquivos não são apagados.`)) return;
  await api(`/api/courses/${state.currentCourseId}`, { method: "DELETE" });
  stopPlayer();
  el("view-course").classList.add("hidden");
  el("view-library").classList.remove("hidden");
  await loadLibrary();
});

async function toggleCompleted(videoId, completed) {
  await api(`/api/videos/${videoId}/completed`, {
    method: "POST",
    body: JSON.stringify({ completed }),
  });
  await loadVideos();
  refreshOneCourse(state.currentCourseId).then((c) => {
    if (c) Object.assign(state.courses.find((x) => x.id === c.id) || {}, c);
  });
}

/* ───────────────── player ───────────────── */

function stopPlayer() {
  const video = el("player-video");
  video.pause();
  video.removeAttribute("src");
  video.load();
  state.currentVideoId = null;
  clearInterval(state.saveTimer);
  el("player-empty").classList.remove("hidden");
  el("player-video-wrap").classList.add("hidden");
  el("player-title").textContent = "";
}

function loadVideoIntoPlayer(v) {
  const videoEl = el("player-video");
  clearInterval(state.saveTimer);
  state.currentVideoId = v.id;

  el("player-empty").classList.add("hidden");
  el("player-video-wrap").classList.remove("hidden");
  el("player-title").textContent = v.file_name;

  videoEl.src = `/api/videos/${v.id}/stream`;
  videoEl.onloadedmetadata = () => {
    if (!v.is_completed && v.position_seconds > 0) {
      videoEl.currentTime = v.position_seconds;
    }
    videoEl.play().catch(() => {});
  };

  videoEl.onpause = () => saveProgress(videoEl);
  videoEl.onended = () => saveProgress(videoEl);
  state.saveTimer = setInterval(() => {
    if (!videoEl.paused) saveProgress(videoEl);
  }, 4000);

  renderVideoTable();
}

async function saveProgress(videoEl) {
  if (!state.currentVideoId || !videoEl.duration) return;
  try {
    const result = await api(`/api/videos/${state.currentVideoId}/progress`, {
      method: "POST",
      body: JSON.stringify({
        position_seconds: videoEl.currentTime,
        duration_seconds: videoEl.duration,
      }),
    });
    const v = state.videos.find((v) => v.id === state.currentVideoId);
    if (v) {
      v.position_seconds = result.position_seconds;
      v.watched_percent = result.watched_percent;
      v.is_completed = result.is_completed;
      renderVideoTable();
    }
  } catch (_) {}
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
    li.innerHTML = `<button>&uarr; ..</button>`;
    li.querySelector("button").addEventListener("click", () => browseTo(data.parent));
    list.appendChild(li);
  }

  for (const entry of data.entries) {
    const li = document.createElement("li");
    li.innerHTML = `<button><svg class="icon" viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" stroke-linejoin="round"/></svg>${escapeHtml(entry.name)}</button>`;
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

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

loadLibrary().catch((e) => showToast(e.message));
