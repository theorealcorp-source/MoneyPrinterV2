function showToast(message, type = "info", duration = 4200) {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.setAttribute("role", "alert");

  const msg = document.createElement("span");
  msg.textContent = message;

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "toast-close";
  closeBtn.setAttribute("aria-label", "Dismiss");
  closeBtn.textContent = "×";
  closeBtn.onclick = () => dismissToast(toast);

  toast.appendChild(msg);
  toast.appendChild(closeBtn);
  container.appendChild(toast);

  if (duration > 0) {
    window.setTimeout(() => dismissToast(toast), duration);
  }
}

function dismissToast(toast) {
  if (!toast || toast.classList.contains("exit")) return;
  toast.classList.add("exit");
  toast.addEventListener("animationend", () => toast.remove(), { once: true });
}

const PANEL_HASH_MAP = {
  studio: "studio",
  compose: "studio",
  queue: "studio",
  review: "studio",
  drafts: "studio",
  profiles: "profiles",
  settings: "settings",
};

function resolvePanelFromHash(rawHash) {
  const normalized = String(rawHash || "").replace(/^#/, "").trim().toLowerCase();
  return PANEL_HASH_MAP[normalized] || "studio";
}

function activatePanel(panelName, options = {}) {
  const target = panelName || "studio";
  const updateHash = Boolean(options.updateHash);

  document.querySelectorAll("[data-panel]").forEach((panel) => {
    const isActive = panel.dataset.panel === target;
    panel.classList.toggle("is-active", isActive);
  });

  document.querySelectorAll("[data-tab-target]").forEach((trigger) => {
    const isActive = trigger.dataset.tabTarget === target;
    trigger.classList.toggle("is-active", isActive);
    trigger.setAttribute("aria-selected", isActive ? "true" : "false");
  });

  try {
    localStorage.setItem("mpv2-active-panel", target);
  } catch (_error) {
  }

  if (updateHash) {
    const nextHash = `#${target}`;
    if (window.location.hash !== nextHash) {
      history.replaceState(null, "", nextHash);
    }
  }
}

function scrollToHashTarget() {
  const targetId = String(window.location.hash || "").replace(/^#/, "").trim();
  if (!targetId || PANEL_HASH_MAP[targetId] === targetId) return;

  const node = document.getElementById(targetId);
  if (node) {
    node.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function initTabs() {
  const saved = (() => {
    try {
      return localStorage.getItem("mpv2-active-panel") || "";
    } catch (_error) {
      return "";
    }
  })();

  activatePanel(resolvePanelFromHash(window.location.hash || saved));

  document.querySelectorAll("[data-tab-target]").forEach((trigger) => {
    trigger.addEventListener("click", (event) => {
      const href = trigger.getAttribute("href") || "";
      const target = trigger.dataset.tabTarget || "studio";
      activatePanel(target, { updateHash: true });

      if (href.startsWith("#")) {
        const targetId = href.slice(1);
        if (PANEL_HASH_MAP[targetId] === target && targetId !== target) {
          event.preventDefault();
          history.replaceState(null, "", href);
          window.setTimeout(scrollToHashTarget, 0);
        }
      }
    });
  });

  window.addEventListener("hashchange", () => {
    activatePanel(resolvePanelFromHash(window.location.hash));
    scrollToHashTarget();
  });
}

function renderQueueSkeleton() {
  const root = document.getElementById("jobQueue");
  if (!root || root.dataset.loaded) return;

  root.innerHTML = `
    <div class="queue-list">
      <div class="skeleton-card">
        <div class="skeleton-row">
          <div class="skeleton-col">
            <div class="skeleton-line w-28"></div>
            <div class="skeleton-line w-65"></div>
          </div>
          <div class="skeleton-line pill"></div>
        </div>
        <div class="skeleton-line w-100"></div>
        <div class="skeleton-line bar"></div>
        <div class="skeleton-row">
          <div class="skeleton-line w-42"></div>
        </div>
      </div>
    </div>
  `;
}

let viewerSlides = [];
let viewerIndex = 0;
let previousJobStatuses = {};

function statusTone(status) {
  if (status === "completed") return "ok";
  if (status === "failed") return "warn";
  return "muted";
}

function renderJobs(jobs) {
  const queueRoot = document.getElementById("jobQueue");
  if (!queueRoot) return;

  queueRoot.dataset.loaded = "1";
  queueRoot.innerHTML = "";

  if (!jobs.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No background jobs yet. Start a generation from Compose Workspace and progress will appear here.";
    queueRoot.appendChild(empty);
    return;
  }

  const activeJobs = jobs.filter((job) => job.is_active);
  const archivedJobs = jobs.filter((job) => !job.is_active);

  if (!activeJobs.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No generation is running right now. Recent history is tucked below so the queue stays readable.";
    queueRoot.appendChild(empty);
  }

  if (activeJobs.length) {
    const list = document.createElement("div");
    list.className = "queue-list";

    activeJobs.slice(0, 2).forEach((job) => {
      const card = document.createElement("article");
      card.className = "job-card";

      const head = document.createElement("div");
      head.className = "job-head";

      const titleWrap = document.createElement("div");
      const kicker = document.createElement("p");
      kicker.className = "job-kicker";
      kicker.textContent = `${job.profile_nickname || "CardNews"} · ${job.format || "carousel"} · ${job.stage || "queued"}`;

      const title = document.createElement("strong");
      title.textContent = job.topic || "New draft generation";

      titleWrap.appendChild(kicker);
      titleWrap.appendChild(title);

      const pill = document.createElement("span");
      pill.className = `status-pill ${statusTone(job.status)}`;
      pill.textContent = job.status || "queued";

      head.appendChild(titleWrap);
      head.appendChild(pill);

      const copy = document.createElement("p");
      copy.className = "job-copy";
      copy.textContent = job.message || "Waiting for progress update.";

      const progressWrap = document.createElement("div");
      progressWrap.className = "job-progress";

      const progressBar = document.createElement("div");
      progressBar.className = "job-progress-bar";
      progressBar.style.width = `${Math.max(0, Math.min(Number(job.progress || 0), 100))}%`;

      progressWrap.appendChild(progressBar);

      const meta = document.createElement("div");
      meta.className = "job-meta";

      const left = document.createElement("p");
      left.className = "compact-note";
      left.textContent = job.step_current && job.step_total
        ? `Step ${job.step_current} / ${job.step_total} · ${job.progress || 0}%`
        : `${job.progress || 0}% complete`;

      meta.appendChild(left);

      if (job.status === "failed" && job.error) {
        const error = document.createElement("span");
        error.className = "chip warn";
        error.textContent = job.error;
        meta.appendChild(error);
      }

      if (job.status === "completed" && job.draft_id) {
        const link = document.createElement("a");
        link.className = "job-link";
        link.href = "#drafts";
        link.textContent = "Jump to Draft Library";
        meta.appendChild(link);
      }

      card.appendChild(head);
      card.appendChild(copy);
      card.appendChild(progressWrap);
      card.appendChild(meta);
      list.appendChild(card);
    });

    queueRoot.appendChild(list);
  }

  if (archivedJobs.length) {
    const details = document.createElement("details");
    details.className = "queue-history";

    const summary = document.createElement("summary");
    summary.textContent = `Recent History · ${archivedJobs.length}`;
    details.appendChild(summary);

    const historyList = document.createElement("div");
    historyList.className = "queue-history-list";

    archivedJobs.slice(0, 4).forEach((job) => {
      const row = document.createElement("article");
      row.className = "queue-history-row";

      const title = document.createElement("strong");
      title.textContent = job.topic || "Recent generation job";

      const meta = document.createElement("p");
      meta.className = "compact-note";
      meta.textContent = `${job.profile_nickname || "CardNews"} · ${job.format || "carousel"} · ${job.status || "completed"}`;

      const copy = document.createElement("p");
      copy.className = "compact-note";
      copy.textContent = job.message || job.error || "Finished";

      row.appendChild(title);
      row.appendChild(meta);
      row.appendChild(copy);
      historyList.appendChild(row);
    });

    details.appendChild(historyList);
    queueRoot.appendChild(details);
  }
}

async function pollJobs() {
  try {
    const response = await fetch("/api/jobs", { cache: "no-store" });
    if (!response.ok) return;

    const payload = await response.json();
    const jobs = Array.isArray(payload.jobs) ? payload.jobs : [];

    jobs.forEach((job) => {
      const previous = previousJobStatuses[job.id];
      if (previous && previous !== job.status) {
        if (job.status === "completed") {
          showToast(`"${job.topic || "Job"}" finished generating.`, "success");
        }
        if (job.status === "failed") {
          showToast(`Generation failed: ${job.error || "unknown error"}`, "error");
        }
      }
      previousJobStatuses[job.id] = job.status;
    });

    renderJobs(jobs);
  } catch (_error) {
  }
}

function renderViewer() {
  const viewerImage = document.getElementById("viewerImage");
  const viewerCount = document.getElementById("viewerCount");
  const viewerSidebar = document.getElementById("viewerSidebar");
  const prevBtn = document.getElementById("viewerPrev");
  const nextBtn = document.getElementById("viewerNext");

  viewerImage.src = viewerSlides[viewerIndex] || "";
  viewerCount.textContent = viewerSlides.length ? `Slide ${viewerIndex + 1} / ${viewerSlides.length}` : "";

  if (prevBtn) prevBtn.disabled = viewerIndex === 0;
  if (nextBtn) nextBtn.disabled = viewerIndex === viewerSlides.length - 1;

  viewerSidebar.innerHTML = "";
  viewerSlides.forEach((slide, index) => {
    const button = document.createElement("button");
    button.type = "button";
    if (index === viewerIndex) {
      button.classList.add("is-active");
    }
    button.onclick = () => {
      viewerIndex = index;
      renderViewer();
    };

    const image = document.createElement("img");
    image.src = slide;
    image.alt = `Slide ${index + 1}`;

    button.appendChild(image);
    viewerSidebar.appendChild(button);
  });
}

function openViewer(element, index = 0) {
  const slides = JSON.parse(element.dataset.slides || "[]");
  if (!slides.length) return;

  viewerSlides = slides;
  viewerIndex = index;
  document.getElementById("viewerTitle").textContent = element.dataset.topic || "CardNews Preview";
  document.getElementById("viewerModal").classList.add("is-open");
  document.body.style.overflow = "hidden";
  renderViewer();
}

function viewerNav(direction) {
  const nextIndex = viewerIndex + direction;
  if (nextIndex >= 0 && nextIndex < viewerSlides.length) {
    viewerIndex = nextIndex;
    renderViewer();
  }
}

function closeViewer(event) {
  if (event && event.target !== document.getElementById("viewerModal")) return;
  document.getElementById("viewerModal").classList.remove("is-open");
  document.body.style.overflow = "";
}

document.addEventListener("keydown", (event) => {
  const modal = document.getElementById("viewerModal");
  if (!modal || !modal.classList.contains("is-open")) return;

  if (event.key === "Escape") closeViewer();
  if (event.key === "ArrowRight" && viewerIndex < viewerSlides.length - 1) {
    viewerIndex += 1;
    renderViewer();
  }
  if (event.key === "ArrowLeft" && viewerIndex > 0) {
    viewerIndex -= 1;
    renderViewer();
  }
});

function initDraftFilter() {
  const filterBar = document.getElementById("draftFilterBar");
  if (!filterBar) return;

  filterBar.addEventListener("click", (event) => {
    const chip = event.target.closest(".filter-chip");
    if (!chip) return;

    const filter = chip.dataset.filter || "all";

    filterBar.querySelectorAll(".filter-chip").forEach((node) => {
      node.classList.remove("is-active");
    });
    chip.classList.add("is-active");

    document.querySelectorAll("#draftList [data-status], .compact-draft-list [data-status]").forEach((row) => {
      if (filter === "all") {
        row.hidden = false;
        return;
      }
      if (filter === "pending") {
        row.hidden = row.dataset.status === "approved" || row.dataset.status === "published";
        return;
      }
      row.hidden = row.dataset.status !== filter;
    });
  });
}

function initGenerateForm() {
  const generateForm = document.getElementById("generateForm");
  const generateButton = document.getElementById("generateButton");
  if (!generateForm || !generateButton) return;

  generateForm.addEventListener("submit", () => {
    generateButton.disabled = true;
    generateButton.textContent = "Queueing...";
  });
}

function initFlash() {
  const flashNode = document.getElementById("flashData");
  if (!flashNode) return;

  try {
    const flash = JSON.parse(flashNode.textContent || "{}");
    if (flash.notice) showToast(flash.notice, "success");
    if (flash.error) showToast(flash.error, "error");
  } catch (_error) {
  }
}

function initJobs() {
  renderQueueSkeleton();

  const initialJobsNode = document.getElementById("initialJobsData");
  if (initialJobsNode) {
    try {
      renderJobs(JSON.parse(initialJobsNode.textContent || "[]"));
    } catch (_error) {
      renderJobs([]);
    }
  }

  pollJobs();
  window.setInterval(pollJobs, 2500);
}

initTabs();
initDraftFilter();
initGenerateForm();
initFlash();
initJobs();
