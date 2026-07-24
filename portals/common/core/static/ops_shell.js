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
  if (shellSearch) {
    let timer = null;
    shellSearch.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        document.dispatchEvent(new CustomEvent("pm-shell-search", { detail: { query: shellSearch.value.trim() } }));
      }, 200);
    });
    shellSearch.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const q = shellSearch.value.trim();
      if (!q) return;
      window.location.href = "/admin/search?q=" + encodeURIComponent(q);
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
