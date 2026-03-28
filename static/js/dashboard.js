    // ── TOAST ────────────────────────────────────────────────────
    function showToast(message, type = 'info', duration = 4200) {
      const container = document.getElementById('toastContainer');
      if (!container) return;
      const toast = document.createElement('div');
      toast.className = `toast ${type}`;
      toast.setAttribute('role', 'alert');
      const msg = document.createElement('span');
      msg.textContent = message;
      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'toast-close';
      closeBtn.setAttribute('aria-label', 'Dismiss');
      closeBtn.textContent = '×';
      closeBtn.onclick = () => dismissToast(toast);
      toast.appendChild(msg);
      toast.appendChild(closeBtn);
      container.appendChild(toast);
      if (duration > 0) setTimeout(() => dismissToast(toast), duration);
    }
    function dismissToast(toast) {
      if (!toast || toast.classList.contains('exit')) return;
      toast.classList.add('exit');
      toast.addEventListener('animationend', () => toast.remove(), { once: true });
    }

    // ── DARK MODE ────────────────────────────────────────────────
    const SUN_SVG  = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;
    const MOON_SVG = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;

    function applyTheme(theme) {
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem('mpv2-theme', theme);
      const btn   = document.getElementById('themeToggle');
      const label = document.getElementById('themeLabel');
      if (btn) {
        const svg = btn.querySelector('svg');
        if (svg) { const t = document.createElement('span'); t.innerHTML = theme === 'dark' ? SUN_SVG : MOON_SVG; svg.replaceWith(t.firstChild); }
      }
      if (label) label.textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
    }

    (function initTheme() {
      const saved = localStorage.getItem('mpv2-theme');
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      const theme = saved || (prefersDark ? 'dark' : 'light');
      if (theme === 'dark') applyTheme('dark');
    })();

    document.getElementById('themeToggle')?.addEventListener('click', () => {
      const cur = document.documentElement.getAttribute('data-theme');
      applyTheme(cur === 'dark' ? 'light' : 'dark');
    });

    // ── SKELETON ─────────────────────────────────────────────────
    function renderQueueSkeleton() {
      const root = document.getElementById('jobQueue');
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
            <div class="skeleton-row"><div class="skeleton-line w-42"></div></div>
          </div>
        </div>`;
    }

    // ── JOB QUEUE ────────────────────────────────────────────────
    let viewerSlides = [];
    let viewerIndex  = 0;
    let _prevJobStatuses = {};

    function statusTone(status) {
      if (status === "completed") return "ok";
      if (status === "failed")    return "warn";
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
        empty.textContent = "No background jobs are running. Start a generation job and its progress will appear here.";
        queueRoot.appendChild(empty);
        return;
      }
      const activeJobs   = jobs.filter((j) => j.is_active);
      const archivedJobs = jobs.filter((j) => !j.is_active);
      if (!activeJobs.length) {
        const empty = document.createElement("div");
        empty.className = "empty-state";
        empty.textContent = "No generation is running right now. Recent history is tucked below so this panel stays readable.";
        queueRoot.appendChild(empty);
      }
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
        if (job.status === "completed" && job.draft_id) {
          const link = document.createElement("a");
          link.className = "job-link";
          link.href = "#drafts";
          link.textContent = "Open draft library";
          meta.appendChild(link);
        } else if (job.status === "failed" && job.error) {
          const errSpan = document.createElement("span");
          errSpan.className = "chip warn";
          errSpan.textContent = job.error;
          meta.appendChild(errSpan);
        }
        card.appendChild(head);
        card.appendChild(copy);
        card.appendChild(progressWrap);
        card.appendChild(meta);
        list.appendChild(card);
      });
      if (activeJobs.length) queueRoot.appendChild(list);
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
          const t = document.createElement("strong");
          t.textContent = job.topic || "Recent generation job";
          const m = document.createElement("p");
          m.className = "compact-note";
          m.textContent = `${job.profile_nickname || "CardNews"} · ${job.format || "carousel"} · ${job.status || "completed"}`;
          const c = document.createElement("p");
          c.className = "compact-note";
          c.textContent = job.message || job.error || "Finished";
          row.appendChild(t); row.appendChild(m); row.appendChild(c);
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
          const prev = _prevJobStatuses[job.id];
          if (prev && prev !== job.status) {
            if (job.status === 'completed') showToast(`"${job.topic || 'Job'}" 생성 완료.`, 'success');
            if (job.status === 'failed')    showToast(`생성 실패: ${job.error || '알 수 없는 오류'}`, 'error');
          }
          _prevJobStatuses[job.id] = job.status;
        });
        renderJobs(jobs);
      } catch (_e) {}
    }

    // ── VIEWER ───────────────────────────────────────────────────
    function renderViewer() {
      const viewerImage   = document.getElementById("viewerImage");
      const viewerCount   = document.getElementById("viewerCount");
      const viewerSidebar = document.getElementById("viewerSidebar");
      const prevBtn = document.getElementById("viewerPrev");
      const nextBtn = document.getElementById("viewerNext");
      viewerImage.src = viewerSlides[viewerIndex] || "";
      viewerCount.textContent = viewerSlides.length ? `Slide ${viewerIndex + 1} / ${viewerSlides.length}` : "";
      if (prevBtn) prevBtn.disabled = viewerIndex === 0;
      if (nextBtn) nextBtn.disabled = viewerIndex === viewerSlides.length - 1;
      viewerSidebar.innerHTML = "";
      viewerSlides.forEach((slide, index) => {
        const btn = document.createElement("button");
        btn.type = "button";
        if (index === viewerIndex) btn.classList.add("is-active");
        btn.onclick = () => { viewerIndex = index; renderViewer(); };
        const img = document.createElement("img");
        img.src = slide; img.alt = `Slide ${index + 1}`;
        btn.appendChild(img);
        viewerSidebar.appendChild(btn);
      });
    }
    function openViewer(element, index = 0) {
      const slides = JSON.parse(element.dataset.slides || "[]");
      if (!slides.length) return;
      viewerSlides = slides;
      viewerIndex  = index;
      document.getElementById("viewerTitle").textContent = element.dataset.topic || "CardNews Preview";
      document.getElementById("viewerModal").classList.add("is-open");
      document.body.style.overflow = "hidden";
      renderViewer();
    }
    function viewerNav(dir) {
      const n = viewerIndex + dir;
      if (n >= 0 && n < viewerSlides.length) { viewerIndex = n; renderViewer(); }
    }
    function closeViewer(event) {
      if (event && event.target !== document.getElementById("viewerModal")) return;
      document.getElementById("viewerModal").classList.remove("is-open");
      document.body.style.overflow = "";
    }
    document.addEventListener("keydown", (e) => {
      const modal = document.getElementById("viewerModal");
      if (!modal.classList.contains("is-open")) return;
      if (e.key === "Escape") closeViewer();
      if (e.key === "ArrowRight" && viewerIndex < viewerSlides.length - 1) { viewerIndex += 1; renderViewer(); }
      if (e.key === "ArrowLeft"  && viewerIndex > 0)                        { viewerIndex -= 1; renderViewer(); }
    });

    // ── DRAFT FILTER ─────────────────────────────────────────────
    document.getElementById('draftFilterBar')?.addEventListener('click', (e) => {
      const chip = e.target.closest('.filter-chip');
      if (!chip) return;
      const filter = chip.dataset.filter;
      document.querySelectorAll('#draftFilterBar .filter-chip').forEach(c => c.classList.remove('is-active'));
      chip.classList.add('is-active');
      document.querySelectorAll('#draftList [data-status], .compact-draft-list [data-status]').forEach(row => {
        if (filter === 'all') {
          row.hidden = false;
        } else if (filter === 'pending') {
          row.hidden = row.dataset.status === 'approved' || row.dataset.status === 'published';
        } else {
          row.hidden = row.dataset.status !== filter;
        }
      });
    });

    // ── INIT ─────────────────────────────────────────────────────
    renderQueueSkeleton();

    const initialJobsNode = document.getElementById("initialJobsData");
    if (initialJobsNode) {
      try { renderJobs(JSON.parse(initialJobsNode.textContent || "[]")); }
      catch (_e) { renderJobs([]); }
    }

    const generateForm   = document.getElementById("generateForm");
    const generateButton = document.getElementById("generateButton");
    if (generateForm && generateButton) {
      generateForm.addEventListener("submit", () => {
        generateButton.disabled = true;
        generateButton.textContent = "Queueing...";
      });
    }

    const flashNode = document.getElementById('flashData');
    if (flashNode) {
      try {
        const flash = JSON.parse(flashNode.textContent || '{}');
        if (flash.notice) showToast(flash.notice, 'success');
        if (flash.error)  showToast(flash.error,  'error');
      } catch (_e) {}
    }

    pollJobs();
    window.setInterval(pollJobs, 2500);
