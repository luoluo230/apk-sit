(() => {
  const SCOPE_KEYS = ["env_key", "channel_id", "platform", "version_id", "release_order_id"];
  const DISPLAY_KEYS = ["version_name", "version_code"];

  const normalizeScope = (raw = {}) => {
    const out = {};
    SCOPE_KEYS.forEach((key) => {
      const val = String(raw[key] ?? "").trim();
      if (val) out[key] = key === "platform" ? val.toLowerCase() : val;
    });
    DISPLAY_KEYS.forEach((key) => {
      const val = String(raw[key] ?? "").trim();
      if (val) out[key] = val;
    });
    return out;
  };

  const parseQuery = (search = location.search) => {
    const params = new URLSearchParams(search);
    const scope = {};
    [...SCOPE_KEYS, ...DISPLAY_KEYS, "hint", "error", "from"].forEach((key) => {
      const val = params.get(key);
      if (val) scope[key] = val;
    });
    return normalizeScope(scope);
  };

  const buildQuery = (scope = {}, extra = {}) => {
    const merged = normalizeScope({ ...scope, ...extra });
    const params = new URLSearchParams();
    SCOPE_KEYS.forEach((key) => {
      if (merged[key]) params.set(key, merged[key]);
    });
    DISPLAY_KEYS.forEach((key) => {
      if (merged[key]) params.set(key, merged[key]);
    });
    Object.entries(extra).forEach(([key, val]) => {
      if (!SCOPE_KEYS.includes(key) && !DISPLAY_KEYS.includes(key) && val != null && String(val).trim()) {
        params.set(key, String(val));
      }
    });
    const qs = params.toString();
    return qs ? `?${qs}` : "";
  };

  const href = (path, scope = {}, extra = {}) => `${path}${buildQuery(scope, extra)}`;

  const releaseConsoleHref = (projectId, scope = {}, extra = {}) =>
    href(`/admin/projects/${encodeURIComponent(projectId)}/versions`, scope, extra);

  const versionsStartReleaseHref = (projectId, versionId, scope = {}) =>
    releaseConsoleHref(projectId, { ...scope, version_id: versionId }, { action: "edit_release" });

  const versionsPageHref = (projectId, scope = {}, extra = {}) =>
    href(`/admin/projects/${encodeURIComponent(projectId)}/versions`, scope, extra);

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const rowPrimaryBtnClass = (primary = {}) => {
    const action = String(primary.action || "");
    if (action === "continue_release" || action === "view_build") return "version-btn compact release";
    if (primary.api_action === "quick_build" || action === "trigger_build") return "version-btn compact build";
    if (action === "configure_pipeline" || action === "edit_plan") return "version-btn compact build";
    return "version-btn compact neutral";
  };

  const renderPrimaryAction = (primary = {}, { variant = "matrix" } = {}) => {
    if (!primary || !primary.label) return "";
    const cls = variant === "row" ? rowPrimaryBtnClass(primary) : "matrix-btn primary";
    if (primary.api_action === "quick_build" && primary.version_id) {
      return `<button class="${cls}" type="button" data-quick-build="${esc(primary.version_id)}">${esc(primary.label)}</button>`;
    }
    if (primary.href) {
      return `<a class="${cls}" href="${esc(primary.href)}">${esc(primary.label)}</a>`;
    }
    return `<button class="${cls}" type="button" disabled title="${esc(primary.reason || "")}">${esc(primary.label)}</button>`;
  };

  const topologyDrawerHref = (projectId, scope = {}) => {
    const envKey = scope.env_key || "development";
    return href(`/admin/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(envKey)}`, scope, { open_topology_drawer: "1" });
  };

  const renderMatrixActions = (actions = {}, links = {}, scope = {}, projectId = "") => {
    const primary = actions.primary || {};
    const secondary = actions.secondary || [];
    const buildHistory = links.build_history || href(`/admin/projects/${projectId}/build-history`, scope, { scoped: "1" });
    const versionsHref = links.versions || href(`/admin/projects/${projectId}/versions`, scope);
    const topologyHref = topologyDrawerHref(projectId, scope);
    const downloadHref = primary.version_id || scope.version_id
      ? href(`/admin/projects/${projectId}/versions`, scope, { download_vc: scope.version_id })
      : "";
    const moreItems = [];
    secondary.forEach((item) => {
      if (item.api_action === "rebuild" && item.release_order_id) {
        moreItems.push(`<button class="matrix-menu-item" type="button" data-rebuild-order="${esc(item.release_order_id)}" data-version-id="${esc(item.version_id || scope.version_id || "")}">${esc(item.label)}</button>`);
      } else if (item.api_action === "quick_build" && item.version_id) {
        moreItems.push(`<button class="matrix-menu-item" type="button" data-quick-build="${esc(item.version_id)}">${esc(item.label)}</button>`);
      } else if (item.href) {
        moreItems.push(`<a class="matrix-menu-item" href="${esc(item.href)}">${esc(item.label)}</a>`);
      }
    });
    if (downloadHref) moreItems.push(`<a class="matrix-menu-item" href="${esc(downloadHref)}">下载</a>`);
    moreItems.push(`<a class="matrix-menu-item" href="${esc(versionsHref)}">版本代码</a>`);
    moreItems.push(`<a class="matrix-menu-item" href="${esc(topologyHref)}">拓扑</a>`);
    const moreId = `matrix-more-${esc(scope.version_id || scope.channel_id || "")}-${esc(scope.platform || "")}`;
    const moreHtml = moreItems.length
      ? `<div class="matrix-more-wrap"><button class="matrix-btn" type="button" data-toggle-matrix-more="${esc(moreId)}" aria-expanded="false">更多 ▾</button><div class="matrix-more-menu" id="${esc(moreId)}" hidden>${moreItems.join("")}</div></div>`
      : "";
    return `${renderPrimaryAction(primary, { variant: "matrix" })}<a class="matrix-btn" href="${esc(buildHistory)}">构建产物</a>${moreHtml}`;
  };

  const renderRowActions = (actions = {}, links = {}, scope = {}, projectId = "") => {
    const primary = actions.primary || {};
    const secondary = actions.secondary || [];
    const buildHistory = links.build_history || href(`/admin/projects/${projectId}/build-history`, scope, { scoped: "1" });
    const moreId = `vc-more-${esc(scope.version_id || "")}`;
    const moreItems = [];
    secondary.forEach((item) => {
      if (item.action === "build_history") {
        moreItems.push(`<a href="${esc(item.href || buildHistory)}">${esc(item.label)}</a>`);
      } else if (item.api_action === "rebuild" && item.release_order_id) {
        moreItems.push(`<button class="version-action-link" type="button" data-rebuild-order="${esc(item.release_order_id)}" data-version-id="${esc(item.version_id || scope.version_id || "")}">${esc(item.label)}</button>`);
      } else if (item.api_action === "quick_build" && item.version_id) {
        moreItems.push(`<button class="version-action-link" type="button" data-quick-build="${esc(item.version_id)}">${esc(item.label)}</button>`);
      } else if (item.href) {
        moreItems.push(`<a href="${esc(item.href)}">${esc(item.label)}</a>`);
      }
    });
    moreItems.push(`<button class="version-action-link" type="button" data-download-apk="${esc(scope.version_id || "")}">查看产物</button>`);
    const downloadBtn = scope.artifact_ready && scope.version_id
      ? `<button class="version-btn compact neutral" type="button" data-download-apk="${esc(scope.version_id)}">下载</button>`
      : "";
    return `<div class="version-row-actions">
      ${downloadBtn}
      ${renderPrimaryAction(primary, { variant: "row" })}
      <div class="version-action-more-menu">
        <button class="version-action-more" type="button" data-toggle-vc-more="${esc(moreId)}" aria-label="更多操作" aria-expanded="false"><img src="/static/project_ui/svg/action_more.svg" alt=""></button>
        <div class="version-row-more-dropdown" id="${esc(moreId)}">${moreItems.join("")}</div>
      </div>
    </div>`;
  };

  const bindQuickBuild = (root, { projectId, request, onSuccess, onError } = {}) => {
    if (!root || !projectId || typeof request !== "function") return;
    root.addEventListener("click", async (event) => {
      const rebuildBtn = event.target.closest("[data-rebuild-order]");
      if (rebuildBtn) {
        event.preventDefault();
        event.stopPropagation();
        const orderId = rebuildBtn.getAttribute("data-rebuild-order") || "";
        if (!orderId) return;
        rebuildBtn.disabled = true;
        try {
          const result = await request(`/api/projects/${encodeURIComponent(projectId)}/release-orders/${encodeURIComponent(orderId)}/build`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: "{}",
          });
          const order = result.data || result;
          if (typeof onSuccess === "function") onSuccess(order, rebuildBtn.getAttribute("data-version-id") || "");
        } catch (error) {
          if (typeof onError === "function") onError(error, rebuildBtn.getAttribute("data-version-id") || "");
        } finally {
          rebuildBtn.disabled = false;
        }
        return;
      }
      const btn = event.target.closest("[data-quick-build]");
      if (!btn) return;
      event.preventDefault();
      event.stopPropagation();
      const versionId = btn.getAttribute("data-quick-build") || "";
      if (!versionId) return;
      const buttons = root.querySelectorAll(`[data-quick-build="${versionId}"]`);
      buttons.forEach((node) => { node.disabled = true; });
      try {
        const result = await request(`/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}/quick-build`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
        const order = result.data || result;
        if (typeof onSuccess === "function") onSuccess(order, versionId);
      } catch (error) {
        if (typeof onError === "function") onError(error, versionId);
      } finally {
        buttons.forEach((node) => { node.disabled = false; });
      }
    });
  };

  const bindMatrixMoreMenus = (root) => {
    if (!root) return;
    root.addEventListener("click", (event) => {
      const toggle = event.target.closest("[data-toggle-matrix-more]");
      if (!toggle) return;
      event.preventDefault();
      event.stopPropagation();
      const menuId = toggle.getAttribute("data-toggle-matrix-more") || "";
      const menu = menuId ? document.getElementById(menuId) : null;
      if (!menu) return;
      const open = !menu.hidden;
      root.querySelectorAll(".matrix-more-menu").forEach((node) => { node.hidden = true; });
      root.querySelectorAll("[data-toggle-matrix-more]").forEach((node) => node.setAttribute("aria-expanded", "false"));
      if (!open) {
        menu.hidden = false;
        toggle.setAttribute("aria-expanded", "true");
      }
    });
    document.addEventListener("click", () => {
      root.querySelectorAll(".matrix-more-menu").forEach((node) => { node.hidden = true; });
      root.querySelectorAll("[data-toggle-matrix-more]").forEach((node) => node.setAttribute("aria-expanded", "false"));
    });
  };

  const renderCardVersionEntry = (projectId, envKey, channelId, platform = "") => {
    const url = versionsPageHref(projectId, { env_key: envKey, channel_id: channelId, platform });
    return `<a class="matrix-btn version" href="${esc(url)}">版本</a>`;
  };

  const renderChannelVersionsEntry = (projectId, envKey, channelId, platform = "") =>
    renderCardVersionEntry(projectId, envKey, channelId, platform);

  const renderChannelJourneyActions = (projectId, envKey, channelId) =>
    renderCardVersionEntry(projectId, envKey, channelId);

  const channelJourneyHref = (projectId, envKey, channelId, kind = "build", platform = "", versionId = "") => {
    const params = new URLSearchParams({
      env_key: envKey,
      channel_id: channelId,
      platform: platform || "",
      action: kind === "release" ? "edit_release" : "create_vc",
    });
    if (versionId) params.set("version_id", versionId);
    return `/admin/projects/${encodeURIComponent(projectId)}/versions?${params.toString()}`;
  };

  window.DeliveryScope = {
    SCOPE_KEYS,
    DISPLAY_KEYS,
    normalizeScope,
    parseQuery,
    buildQuery,
    href,
    versionsStartReleaseHref,
    versionsPageHref,
    renderPrimaryAction,
    renderMatrixActions,
    renderRowActions,
    renderCardVersionEntry,
    renderChannelVersionsEntry,
    renderChannelJourneyActions,
    channelJourneyHref,
    releaseConsoleHref,
    topologyDrawerHref,
    bindQuickBuild,
    bindMatrixMoreMenus,
    esc,
  };
})();
