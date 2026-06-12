(() => {
  const storageKey = "project_workspace_sidebar_collapsed";
  const app = document.querySelector(".ops-shell-app");
  const button = document.querySelector(".ops-shell-collapse-btn");
  if (!app) return;

  if (localStorage.getItem(storageKey) === "1") app.classList.add("sidebar-collapsed");

  const syncLabel = () => {
    const label = button?.querySelector("span");
    if (label) label.textContent = app.classList.contains("sidebar-collapsed") ? "展开菜单" : "收起菜单";
  };
  syncLabel();
  button?.addEventListener("click", () => {
    const collapsed = app.classList.toggle("sidebar-collapsed");
    localStorage.setItem(storageKey, collapsed ? "1" : "0");
    syncLabel();
  });

  // Project context is URL-owned so links remain shareable and every module reads the same target.
  const current = new URLSearchParams(location.search);
  const keys = ["env_key", "channel_id", "platform", "version_name", "version_code", "release_order_id"];
  document.querySelectorAll('a[href^="/admin/projects/"]').forEach((link) => {
    const url = new URL(link.href, location.origin);
    keys.forEach((key) => {
      if (!url.searchParams.has(key) && current.get(key)) url.searchParams.set(key, current.get(key));
    });
    link.href = `${url.pathname}${url.search}${url.hash}`;
  });
})();
