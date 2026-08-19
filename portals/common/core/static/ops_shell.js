(() => {
  const app = document.querySelector(".ops-shell-app");
  if (!app) return;
  const projectId = app.dataset.projectId || "";
  const pageKey = app.dataset.page || "";
  const contextKeys = ["env_key", "channel_id", "platform", "version_name", "version_code", "release_order_id"];
  const current = new URLSearchParams(location.search);
  const storageKey = "project_workspace_sidebar_collapsed";
  const favoriteKey = `pm_page_favorite_${projectId}_${pageKey}`;
  const collapse = document.querySelector(".ops-shell-collapse-btn");
  if (localStorage.getItem(storageKey) === "1") app.classList.add("sidebar-collapsed");
  collapse?.addEventListener("click", () => {
    const collapsed = app.classList.toggle("sidebar-collapsed");
    localStorage.setItem(storageKey, collapsed ? "1" : "0");
  });
  document.querySelectorAll('a[href^="/admin/projects/"]').forEach((link) => {
    const url = new URL(link.href, location.origin);
    contextKeys.forEach((key) => {
      if (!url.searchParams.has(key) && current.get(key)) url.searchParams.set(key, current.get(key));
    });
    link.href = `${url.pathname}${url.search}${url.hash}`;
  });
  const trigger = document.querySelector("[data-context-trigger]");
  const menu = document.querySelector("[data-context-menu]");
  const projectsHost = document.querySelector("[data-context-projects]");
  const switchProject = (nextProject) => {
    const parts = location.pathname.split("/");
    const projectIndex = parts.indexOf("projects") + 1;
    if (projectIndex <= 0 || !nextProject) return;
    parts[projectIndex] = nextProject;
    const params = new URLSearchParams(location.search);
    params.delete("env_key");
    const query = params.toString();
    location.href = `${parts.join("/")}${query ? `?${query}` : ""}`;
  };
  const loadContextMenu = async () => {
    if (!projectsHost || projectsHost.dataset.loaded) return;
    projectsHost.dataset.loaded = "1";
    try {
      const response = await fetch("/api/projects/context-catalog");
      const payload = await response.json();
      const projects = payload.data || [];
      projectsHost.innerHTML = projects.map((item) => `<button class="ops-context-option ${item.project_id===projectId?"active":""}" data-project="${item.project_id}">${item.project_name}</button>`).join("");
      projectsHost.querySelectorAll("[data-project]").forEach((button) => button.addEventListener("click", () => switchProject(button.dataset.project)));
    } catch (_) {
      projectsHost.innerHTML = '<span class="ops-context-option">项目列表加载失败</span>';
    }
  };
  trigger?.addEventListener("click", async (event) => {
    event.stopPropagation();
    const open = menu.hidden;
    menu.hidden = !open;
    trigger.setAttribute("aria-expanded", String(open));
    if (open) await loadContextMenu();
  });
  document.addEventListener("click", (event) => {
    if (menu && !menu.hidden && !menu.contains(event.target) && !trigger.contains(event.target)) {
      menu.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
    }
  });

  const shellSearch = document.querySelector("[data-shell-search]");
  const shellSearchDropdown = document.querySelector("[data-shell-search-dropdown]");
  const categoryLabels = {
    project: "项目",
    release_order: "发布单",
    version: "版本",
    doc: "文档",
    task: "任务",
    user: "用户",
  };
  const renderSearchDropdown = (hits, query) => {
    if (!shellSearchDropdown) return;
    if (!query || !hits.length) {
      shellSearchDropdown.hidden = true;
      shellSearchDropdown.innerHTML = "";
      return;
    }
    shellSearchDropdown.innerHTML = hits.map((item) => {
      const label = categoryLabels[item.category] || item.category || "结果";
      const title = item.title || item.name || item.id || "";
      const meta = item.project_id ? `<span>${item.project_id}</span>` : `<span>${label}</span>`;
      return `<a class="ops-shell-search-hit" href="${item.link}"><strong>${title}</strong>${meta}</a>`;
    }).join("") + `<a class="ops-shell-search-more" href="/admin/search?q=${encodeURIComponent(query)}">查看全部结果</a>`;
    shellSearchDropdown.hidden = false;
  };
  if (shellSearch) {
    let timer = null;
    let requestSeq = 0;
    shellSearch.addEventListener("input", () => {
      clearTimeout(timer);
      const query = shellSearch.value.trim();
      document.dispatchEvent(new CustomEvent("pm-shell-search", { detail: { query } }));
      timer = setTimeout(async () => {
        if (!query) {
          renderSearchDropdown([], "");
          return;
        }
        const seq = ++requestSeq;
        try {
          const response = await fetch(`/api/admin/search?q=${encodeURIComponent(query)}`);
          const payload = await response.json();
          if (seq !== requestSeq) return;
          renderSearchDropdown(payload.hits || [], query);
        } catch (_) {
          if (seq === requestSeq) renderSearchDropdown([], query);
        }
      }, 220);
    });
    shellSearch.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const q = shellSearch.value.trim();
      if (!q) return;
      window.location.href = "/admin/search?q=" + encodeURIComponent(q);
    });
    shellSearch.addEventListener("focus", () => {
      if (shellSearch.value.trim()) shellSearch.dispatchEvent(new Event("input"));
    });
    document.addEventListener("click", (event) => {
      if (!shellSearchDropdown || shellSearchDropdown.hidden) return;
      if (shellSearchDropdown.contains(event.target) || shellSearch.contains(event.target)) return;
      shellSearchDropdown.hidden = true;
    });
  }

  const fav = window.PmUserFavorites;
  document.querySelectorAll(".pm-page-star").forEach((button) => {
    const key = button.dataset.favoriteKey || favoriteKey;
    const sync = () => {
      const active = fav
        ? fav.isPageFavorite(projectId, pageKey) || localStorage.getItem(key) === "1"
        : localStorage.getItem(key) === "1";
      button.classList.toggle("is-favorite", active);
    };
    sync();
    button.addEventListener("click", async () => {
      if (fav) {
        try {
          await fav.togglePageFavorite(projectId, pageKey);
        } catch (_) {
          const next = localStorage.getItem(key) === "1" ? "0" : "1";
          localStorage.setItem(key, next);
        }
      } else {
        const next = localStorage.getItem(key) === "1" ? "0" : "1";
        localStorage.setItem(key, next);
      }
      sync();
    });
    document.addEventListener("pm-favorites-changed", sync);
  });
})();
