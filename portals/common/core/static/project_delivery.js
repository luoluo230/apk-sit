(() => {
  const DC = window.DeliveryCommon || {};
  const page = document.querySelector("[data-delivery-page]");
  if (!page) return;
  const projectId = page.dataset.projectId;
  const envLabels = {development:"开发环境",testing:"测试环境",staging:"预发环境",production:"生产环境"};
  const statusLabels = DC.statusLabels || {draft:"草稿",building:"构建中",build_failed:"构建失败",artifacts_ready:"产物就绪",prechecking:"预检中",precheck_failed:"预检失败",ready:"待发布",awaiting_approval:"待审批",approved:"待发布",publishing:"发布中",published:"已发布",publish_failed:"发布失败",verifying:"验证中",verified:"验证通过",verify_failed:"验证失败",rolled_back:"已回滚",cancelled:"已取消"};
  const releaseLabel = DC.releaseLabel || ((value) => statusLabels[value] || value || "未配置");
  const artifactStatusLabels = {registered:"已登记",available:"可用",reachable:"可达",missing:"缺失",unreachable:"不可达",invalid:"无效"};
  const artifactTypeLabels = {apk:"APK 安装包",resource:"资源包",config:"配置包",code:"代码热更包"};
  const bindingSourceLabels = {project_default:"项目默认",env_channel:"环境与渠道",env_channel_platform:"环境/渠道/平台",version:"大版本覆盖",version_override:"大版本覆盖",scope_default:"Scope默认",scope_override:"Scope覆盖",default:"项目默认"};
  const parseApiError = DC.parseApiError || ((result, fallback) => {
    if (!result || typeof result !== "object") return fallback;
    const err = result.error;
    if (typeof err === "string" && err) return err;
    if (err && typeof err === "object") return err.message || err.text || fallback;
    return result.error_text || result.error_legacy || fallback;
  });
  const esc = DC.esc || ((value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])));
  const parseJsonResponse = DC.parseJsonResponse || (async (response) => {
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      const text = await response.text();
      if (response.status === 401 || text.trim().startsWith("<")) {
        throw new Error(response.status >= 500 ? `服务异常 (${response.status})，请刷新后重试` : "会话已过期，请重新登录后重试");
      }
      throw new Error(`请求失败 (${response.status})`);
    }
    return response.json();
  });
  const api = DC.api || (async (path, options = {}) => {
    const response = await fetch(path, { ...options, credentials: "same-origin" });
    const result = await parseJsonResponse(response);
    if (!response.ok || result.ok === false) {
      const err = result.error;
      const message = typeof err === "string" ? err : err?.message || result.error_text || result.error_legacy || "请求失败";
      throw new Error(message);
    }
    return result.data;
  });
  const toast = DC.toast || ((message, type="success") => {
    let host = document.querySelector(".toast-stack");
    if (!host) { host = document.createElement("div"); host.className = "toast-stack"; document.body.append(host); }
    const node = document.createElement("div"); node.className = `toast ${type}`; node.textContent = message; host.append(node); setTimeout(() => node.remove(), 3500);
  });
  const status = DC.status || ((value) => `<span class="status-pill ${esc(value)}">${esc(releaseLabel(value))}</span>`);
  const detailRow = (label, value, extra = "", opts = {}) => {
    const tone = opts.tone ? `detail-tone ${opts.tone}` : "";
    const href = opts.href || "";
    const apiAction = opts.apiAction || "";
    let display;
    if (apiAction) {
      display = `<button type="button" class="ro-config-link" data-next-action="${esc(apiAction)}" style="border:0;background:transparent;padding:0;cursor:pointer">${esc(opts.linkLabel || "去处理")}</button>`;
    } else if (href && (!value || value === "-")) {
      display = `<a class="ro-config-link" href="${esc(href)}">${esc(opts.linkLabel || "去处理")}</a>`;
    } else {
      display = esc(value || "-");
    }
    const extraHtml = extra ? `<b class="${tone}">${esc(extra)}</b>` : "<b></b>";
    return `<div class="detail-row"><strong>${esc(label)}</strong><span>${display}</span>${extraHtml}</div>`;
  };
  const row = (label, value, extra = "") => detailRow(label, value, extra);
  const buildReleaseFocusUrl = (href, { section = "", highlightFields = [], focusReason = "", releaseOrderId = "" } = {}) => {
    if (!href) return "";
    try {
      const url = new URL(href, window.location.origin);
      if (section) url.searchParams.set("section", section);
      const fields = Array.isArray(highlightFields) ? highlightFields : String(highlightFields || "").split(",").map((x) => x.trim()).filter(Boolean);
      if (fields.length) url.searchParams.set("highlight", fields.join(","));
      if (focusReason) url.searchParams.set("focus_reason", focusReason);
      if (releaseOrderId) url.searchParams.set("release_order_id", releaseOrderId);
      if (!url.searchParams.get("from")) url.searchParams.set("from", "release-order");
      return `${url.pathname}${url.search}`;
    } catch (_error) {
      if (!section && !highlightFields.length) return href;
      const join = href.includes("?") ? "&" : "?";
      const parts = [];
      if (section) parts.push(`section=${encodeURIComponent(section)}`);
      if (highlightFields.length) parts.push(`highlight=${encodeURIComponent(highlightFields.join(","))}`);
      if (focusReason) parts.push(`focus_reason=${encodeURIComponent(focusReason)}`);
      if (releaseOrderId) parts.push(`release_order_id=${encodeURIComponent(releaseOrderId)}`);
      parts.push("from=release-order");
      return `${href}${join}${parts.join("&")}`;
    }
  };
  const buildTopologyDrawerHref = (scope = {}) => {
    const envKey = scope.env_key || page.dataset.envKey || "development";
    return scopeHref(`/admin/projects/${projectId}/environments/${encodeURIComponent(envKey)}`, scope, { open_topology_drawer: "1" });
  };
  const csrfHeaders = () => {
    const token = document.querySelector('meta[name="csrf-token"]');
    return token && token.content ? { "X-CSRFToken": token.content } : {};
  };
  const scopeApi = window.DeliveryScope || {};
  const parseScopeQuery = (search = location.search) => (scopeApi.parseQuery ? scopeApi.parseQuery(search) : Object.fromEntries(new URLSearchParams(search)));
  const buildScopeQuery = (scope = {}, extra = {}) => (scopeApi.buildQuery ? scopeApi.buildQuery(scope, extra) : "");
  const scopeHref = (path, scope = {}, extra = {}) => (scopeApi.href ? scopeApi.href(path, scope, extra) : `${path}${buildScopeQuery(scope, extra)}`);
  const currentContext = () => buildScopeQuery(parseScopeQuery());
  const renderJourneyProgress = (host, phases, phaseIndex, failed = false) => {
    if (!host || !phases?.length) return;
    host.innerHTML = phases.map((label, index) => {
      const cls = index < phaseIndex ? "done" : index === phaseIndex ? (failed ? "failed active" : "active") : "";
      return `<div class="ro-journey-segment ${cls}" data-phase="${index}"><span>${esc(label)}</span></div>`;
    }).join("");
  };
  const matrixActions = (line, envKey) => {
    const scopeApi = window.DeliveryScope || {};
    const scope = {
      env_key: envKey,
      channel_id: line.channel_id,
      platform: line.platform,
      version_id: line.version_id,
      version_name: line.version_name,
      version_code: line.version_code,
      release_order_id: line.release_order_id,
    };
    if (!line.configured || !line.version_id) {
      const addVcHref = scopeHref(`/admin/projects/${projectId}/versions`, scope, { action: "create_vc" });
      return `<a class="matrix-btn primary" href="${addVcHref}">新建 VC</a>`;
    }
    const actions = line.delivery_actions || {};
    const links = actions.links || {};
    return scopeApi.renderMatrixActions ? scopeApi.renderMatrixActions(actions, links, scope, projectId) : "";
  };
  const renderChannelList = (host, assigned, { manageable = false } = {}) => {
    if (!host) return;
    host.innerHTML = assigned.length
      ? assigned.map((item) => {
          const enabled = Boolean(item.enabled);
          const status = enabled ? "" : " is-disabled";
          const meta = enabled ? "" : " · 已禁用";
          const toggle = manageable
            ? (enabled
              ? `<button class="channel-disable" type="button" data-disable-channel="${esc(item.id)}">禁用</button>`
              : `<button class="channel-enable" type="button" data-enable-channel="${esc(item.id)}">启用</button>`)
            : "";
          const remove = manageable
            ? `<button class="channel-remove" type="button" data-remove-channel="${esc(item.id)}">移除</button>`
            : "";
          return `<div class="channel-item${status}"><div><strong>${esc(item.name)}</strong><small>ID: ${esc(item.id)}${meta}</small></div><div class="channel-actions">${toggle}${remove}</div></div>`;
        }).join("")
      : '<div class="ui-empty">尚未配置项目渠道</div>';
    if (!manageable) return;
    host.querySelectorAll("[data-disable-channel]").forEach((button) => {
      button.onclick = async () => {
        if (!confirm(`确认禁用渠道「${button.dataset.disableChannel}」？禁用后不会出现在交付线与发布流程。`)) return;
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/channels/disable`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...csrfHeaders() },
            credentials: "same-origin",
            body: JSON.stringify({ channel_id: button.dataset.disableChannel }),
          });
          const result = await response.json();
            if (!response.ok || result.error || result.ok === false) throw new Error(parseApiError(result, "禁用失败"));
          toast("渠道已禁用");
          await loadProjectChannels();
          if (page.dataset.deliveryPage === "overview") await loadOverview();
          if (page.dataset.deliveryPage === "environment") await loadEnvironmentDetail();
        } catch (error) {
          toast(error.message, "error");
        }
      };
    });
    host.querySelectorAll("[data-enable-channel]").forEach((button) => {
      button.onclick = async () => {
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/channels/enable`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...csrfHeaders() },
            credentials: "same-origin",
            body: JSON.stringify({ channel_id: button.dataset.enableChannel }),
          });
          const result = await response.json();
          if (!response.ok || result.error || result.ok === false) throw new Error(parseApiError(result, "启用失败"));
          toast("渠道已启用");
          await loadProjectChannels();
          if (page.dataset.deliveryPage === "overview") await loadOverview();
          if (page.dataset.deliveryPage === "environment") await loadEnvironmentDetail();
        } catch (error) {
          toast(error.message, "error");
        }
      };
    });
    host.querySelectorAll("[data-remove-channel]").forEach((button) => {
      button.onclick = async () => {
        if (!confirm(`确认从项目中移除渠道「${button.dataset.removeChannel}」？`)) return;
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/channels/remove`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...csrfHeaders() },
            credentials: "same-origin",
            body: JSON.stringify({ channel_id: button.dataset.removeChannel }),
          });
          const result = await response.json();
          if (!response.ok || result.error || result.ok === false) throw new Error(parseApiError(result, "移除失败"));
          toast("渠道已移除");
          await loadProjectChannels();
          if (page.dataset.deliveryPage === "overview") await loadOverview();
          if (page.dataset.deliveryPage === "environment") await loadEnvironmentDetail();
        } catch (error) {
          toast(error.message, "error");
        }
      };
    });
  };
  const loadProjectChannels = async () => {
    const listHost = document.getElementById("projectChannelList") || document.getElementById("envChannelList");
    const select = document.getElementById("projectChannelAddSelect");
    if (!listHost) return [];
    try {
      const [projectRes, catalogRes] = await Promise.all([
        fetch(`/admin/projects/get/${encodeURIComponent(projectId)}`, { credentials: "same-origin" }).then((r) => r.json()),
        fetch("/admin/channels", { credentials: "same-origin" }).then((r) => r.json()),
      ]);
      const project = projectRes.project || projectRes.data?.project || {};
      const catalog = catalogRes.channels || catalogRes.data?.channels || [];
      const assignedIds = Array.isArray(project.channels) && project.channels.length ? project.channels : catalog.map((item) => item.id);
      const disabledIds = new Set(
        Array.isArray(project.disabled_channels) ? project.disabled_channels.map((id) => String(id)) : []
      );
      const assigned = assignedIds.map((id) => {
        const row = catalog.find((item) => String(item.id) === String(id)) || { id, name: id };
        const cid = String(row.id || id);
        return {
          id: cid,
          name: String(row.name || row.id || id),
          enabled: !disabledIds.has(cid),
        };
      });
      renderChannelList(listHost, assigned, { manageable: listHost.id === "projectChannelList" });
      renderChannelChips(assigned);
      if (listHost.classList.contains("channel-list-inline") && assigned.length) {
        listHost.classList.add("has-channels");
      }
      if (select) {
        const available = catalog.filter((item) => !assignedIds.includes(String(item.id)));
        select.innerHTML = '<option value="">选择要添加的渠道</option>' + available.map((item) => `<option value="${esc(item.id)}">${esc(item.name)} (${esc(item.id)})</option>`).join("");
      }
      const filterChannel = document.getElementById("overviewChannelCount");
      if (filterChannel) {
        const enabledCount = assigned.filter((item) => item.enabled).length;
        const disabledCount = assigned.length - enabledCount;
        filterChannel.textContent = disabledCount
          ? `${enabledCount} 个启用 / ${assigned.length} 总计`
          : (assigned.length ? `${assigned.length} 个启用` : "未配置渠道");
      }
      return assigned;
    } catch (error) {
      if (listHost.id === "projectChannelList") {
        listHost.innerHTML = `<div class="ui-empty">${esc(error.message || "渠道加载失败")}</div>`;
      }
      return [];
    }
  };
  const renderChannelChips = (assigned) => {
    const host = document.getElementById("overviewChannelChipsList");
    if (!host) return;
    host.innerHTML = assigned.length
      ? assigned.map((item) => `<span class="channel-chip${item.enabled ? "" : " is-disabled"}">${esc(item.name)}${item.enabled ? "" : "（已禁用）"}</span>`).join("")
      : '<span class="channel-chip muted">未配置渠道</span>';
  };
  let platformCatalogCache = null;
  let platformCapabilityCache = null;
  const loadPlatformCapabilities = async () => {
    if (platformCapabilityCache) return platformCapabilityCache;
    const result = await fetch("/api/admin/platforms/capabilities", { credentials: "same-origin" }).then((r) => r.json());
    if (!result.ok) throw new Error(result.error || "平台能力加载失败");
    const rows = (result.data && result.data.platforms) || result.data || [];
    platformCapabilityCache = rows.reduce((acc, row) => {
      const id = String(row.platform_id || row.id || "").toLowerCase();
      if (id) acc[id] = row;
      return acc;
    }, {});
    return platformCapabilityCache;
  };
  const platformBadgeHtml = (cap) => {
    if (!cap) return "";
    const badge = String(cap.badge || "");
    const label = String(cap.badge_label || "");
    if (!label) return "";
    const cls = badge === "buildable" ? "cap-badge cap-badge--buildable" : badge === "client_only" ? "cap-badge cap-badge--client" : "cap-badge cap-badge--catalog";
    const icon = badge === "buildable" ? "🟢" : badge === "client_only" ? "🟡" : "⚪";
    return `<span class="${cls}" title="${esc(label)}">${icon} ${esc(label)}</span>`;
  };
  const loadPlatformCatalog = async () => {
    if (platformCatalogCache) return platformCatalogCache;
    const [catalogResult, capabilityMap] = await Promise.all([
      fetch("/api/release/platform-catalog", { credentials: "same-origin" }).then((r) => r.json()),
      loadPlatformCapabilities().catch(() => ({})),
    ]);
    if (!catalogResult.ok) throw new Error(catalogResult.error || "平台目录加载失败");
    platformCatalogCache = (catalogResult.data || []).map((row) => {
      const id = String(row.id || "").toLowerCase();
      const cap = capabilityMap[id] || row;
      return {
        id,
        name: String(row.name || row.id || ""),
        can_build: Boolean(cap.can_build),
        catalog_only: Boolean(cap.catalog_only),
        badge: String(cap.badge || ""),
        badge_label: String(cap.badge_label || ""),
      };
    });
    return platformCatalogCache;
  };
  const renderPlatformList = (host, assigned, { manageable = false } = {}) => {
    if (!host) return;
    host.innerHTML = assigned.length
      ? assigned.map((item) => {
          const enabled = Boolean(item.enabled);
          const status = enabled ? "" : " is-disabled";
          const meta = enabled ? "" : " · 已禁用";
          const toggle = manageable
            ? (enabled
              ? `<button class="channel-disable" type="button" data-disable-platform="${esc(item.id)}">禁用</button>`
              : `<button class="channel-enable" type="button" data-enable-platform="${esc(item.id)}">启用</button>`)
            : "";
          const remove = manageable
            ? `<button class="channel-remove" type="button" data-remove-platform="${esc(item.id)}">移除</button>`
            : "";
          const badge = platformBadgeHtml(item);
          const buildHint = item.can_build ? "" : " · 暂不支持构建";
          return `<div class="channel-item${status}"><div><strong>${esc(item.name)}</strong> ${badge}<small>ID: ${esc(item.id)}${meta}${buildHint}</small></div><div class="channel-actions">${toggle}${remove}</div></div>`;
        }).join("")
      : '<div class="ui-empty">尚未配置项目平台</div>';
    if (!manageable) return;
    host.querySelectorAll("[data-disable-platform]").forEach((button) => {
      button.onclick = async () => {
        if (!confirm(`确认禁用平台「${button.dataset.disablePlatform}」？禁用后不会出现在交付线与发布流程。`)) return;
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/platforms/disable`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...csrfHeaders() },
            credentials: "same-origin",
            body: JSON.stringify({ platform_id: button.dataset.disablePlatform }),
          });
          const result = await response.json();
          if (!response.ok || result.error || result.ok === false) throw new Error(parseApiError(result, "禁用失败"));
          toast("平台已禁用");
          await loadProjectPlatforms();
          if (page.dataset.deliveryPage === "overview") await loadOverview();
          if (page.dataset.deliveryPage === "environment") await loadEnvironmentDetail();
        } catch (error) {
          toast(error.message, "error");
        }
      };
    });
    host.querySelectorAll("[data-enable-platform]").forEach((button) => {
      button.onclick = async () => {
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/platforms/enable`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...csrfHeaders() },
            credentials: "same-origin",
            body: JSON.stringify({ platform_id: button.dataset.enablePlatform }),
          });
          const result = await response.json();
          if (!response.ok || result.error || result.ok === false) throw new Error(parseApiError(result, "启用失败"));
          toast("平台已启用");
          await loadProjectPlatforms();
          if (page.dataset.deliveryPage === "overview") await loadOverview();
          if (page.dataset.deliveryPage === "environment") await loadEnvironmentDetail();
        } catch (error) {
          toast(error.message, "error");
        }
      };
    });
    host.querySelectorAll("[data-remove-platform]").forEach((button) => {
      button.onclick = async () => {
        if (!confirm(`确认从项目中移除平台「${button.dataset.removePlatform}」？`)) return;
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/platforms/remove`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...csrfHeaders() },
            credentials: "same-origin",
            body: JSON.stringify({ platform_id: button.dataset.removePlatform }),
          });
          const result = await response.json();
          if (!response.ok || result.ok === false) throw new Error(parseApiError(result, "移除失败"));
          if (result.error && typeof result.error === "string") throw new Error(result.error);
          toast("平台已移除");
          await loadProjectPlatforms();
          if (page.dataset.deliveryPage === "overview") await loadOverview();
          if (page.dataset.deliveryPage === "environment") await loadEnvironmentDetail();
        } catch (error) {
          toast(error.message, "error");
        }
      };
    });
  };
  const loadProjectPlatforms = async () => {
    const listHost = document.getElementById("projectPlatformList") || document.getElementById("envPlatformList");
    const select = document.getElementById("projectPlatformAddSelect");
    if (!listHost) return [];
    try {
      const projectRes = await fetch(`/admin/projects/get/${encodeURIComponent(projectId)}`, { credentials: "same-origin" }).then((r) => r.json());
      const project = projectRes.project || projectRes.data?.project || {};
      const catalog = await loadPlatformCatalog();
      const assignedIds = Array.isArray(project.platforms) && project.platforms.length
        ? project.platforms.map((id) => String(id).toLowerCase())
        : ["android", "ios"];
      const disabledIds = new Set(
        Array.isArray(project.disabled_platforms) ? project.disabled_platforms.map((id) => String(id).toLowerCase()) : []
      );
      const assigned = assignedIds.map((id) => {
        const row = catalog.find((item) => item.id === id) || { id, name: id };
        const pid = String(row.id || id);
        return {
          id: pid,
          name: String(row.name || row.id || id),
          enabled: !disabledIds.has(pid),
          can_build: Boolean(row.can_build),
          catalog_only: Boolean(row.catalog_only),
          badge: String(row.badge || ""),
          badge_label: String(row.badge_label || ""),
        };
      });
      renderPlatformList(listHost, assigned, { manageable: listHost.id === "projectPlatformList" });
      renderPlatformChips(assigned);
      if (select) {
        const available = catalog.filter((item) => !assignedIds.includes(item.id));
        select.innerHTML = '<option value="">选择要添加的平台</option>' + available.map((item) => `<option value="${esc(item.id)}">${esc(item.name)} (${esc(item.id)})</option>`).join("");
      }
      return assigned;
    } catch (error) {
      if (listHost.id === "projectPlatformList") {
        listHost.innerHTML = `<div class="ui-empty">${esc(error.message || "平台加载失败")}</div>`;
      }
      return [];
    }
  };
  const renderPlatformChips = (assigned) => {
    const host = document.getElementById("overviewPlatformChipsList");
    if (!host) return;
    host.innerHTML = assigned.length
      ? assigned.map((item) => `<span class="channel-chip${item.enabled ? "" : " is-disabled"}">${esc(item.name)}${platformBadgeHtml(item)}${item.enabled ? "" : "（已禁用）"}</span>`).join("")
      : '<span class="channel-chip muted">未配置平台</span>';
  };
  const overviewFilterParams = () => {
    const params = new URLSearchParams(location.search);
    return {
      env_key: params.get("env_key") || "",
      channel_id: params.get("channel_id") || "",
      platform: params.get("platform") || "",
      health: params.get("health") || "",
    };
  };
  const overviewQueryString = (filters) => {
    const params = new URLSearchParams();
    if (location.search.includes("tab=channels")) params.set("tab", "channels");
    if (location.search.includes("tab=platforms")) params.set("tab", "platforms");
    if (location.search.includes("tab=environments")) params.set("tab", "environments");
    Object.entries(filters || overviewFilterParams()).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    const text = params.toString();
    return text ? `?${text}` : "";
  };
  const loadOverviewManifestStatus = async () => {
    const node = document.getElementById("overviewScopeSyncStatus");
    if (!node) return;
    try {
      const result = await fetch(`/api/release/manifests/${encodeURIComponent(projectId)}`, { credentials: "same-origin" }).then((r) => r.json());
      if (result.ok && result.manifest?.project_id) {
        const count = result.manifest.channels?.length || 0;
        node.textContent = `交付线 Scope：Manifest 已注册（${count} 个渠道）；变更白名单或环境范围后，请在渠道管理「初始化交付线 Scope」同步矩阵`;
      } else {
        node.textContent = "交付线 Scope：尚未注册 Manifest；请先在渠道管理配置渠道并点击「初始化交付线 Scope」";
      }
    } catch {
      node.textContent = "交付线 Scope：无法读取 Manifest 状态";
    }
  };
  const bindManifestBootstrap = () => {
    const manifestBtn = document.getElementById("btnOverviewBootstrapScopes");
    const manifestStatus = document.getElementById("overviewManifestStatus");
    if (!manifestBtn || !manifestStatus || manifestBtn.dataset.bound === "1") return;
    manifestBtn.dataset.bound = "1";
    fetch(`/api/release/manifests/${encodeURIComponent(projectId)}`, { credentials: "same-origin" })
      .then((r) => r.json())
      .then((d) => {
        manifestStatus.textContent = d.ok && d.manifest?.project_id ? `Manifest 已注册（${d.manifest.channels?.length || 0} 个渠道）` : "尚未注册 Manifest，初始化前请先配置项目渠道";
      })
      .catch(() => {
        manifestStatus.textContent = "无法读取 Manifest 状态";
      });
    manifestBtn.onclick = async () => {
      try {
        const result = await fetch(`/api/release/manifests/${encodeURIComponent(projectId)}/bootstrap-scopes`, {
          method: "POST",
          headers: { "X-CSRFToken": document.querySelector('meta[name="csrf-token"]')?.content || "" },
          credentials: "same-origin",
        }).then((r) => r.json());
        if (!result.ok) throw new Error(result.error || "初始化失败");
        toast(`已初始化 ${result.count || 0} 条交付线 Scope`);
        await loadOverview();
        await loadOverviewManifestStatus();
      } catch (error) {
        toast(error.message, "error");
      }
    };
  };
  const initOverviewTabs = () => {
    const params = new URLSearchParams(location.search);
    const root = document.querySelector(".p02-overview");
    const setTab = (name) => {
      const isConfig = name !== "overview";
      if (root) root.classList.toggle("is-config-mode", isConfig);
      document.querySelectorAll("[data-overview-tab]").forEach((btn) => btn.classList.toggle("active", btn.dataset.overviewTab === name));
      document.querySelectorAll("[data-overview-panel]").forEach((panel) => {
        panel.classList.toggle("is-active", panel.dataset.overviewPanel === name);
      });
      const url = new URL(location.href);
      if (name === "channels") url.searchParams.set("tab", "channels");
      else if (name === "platforms") url.searchParams.set("tab", "platforms");
      else if (name === "environments") url.searchParams.set("tab", "environments");
      else url.searchParams.delete("tab");
      history.replaceState(null, "", `${url.pathname}${url.search}`);
      if (name === "channels") {
        loadProjectChannels();
        bindProjectChannelAdd();
        bindManifestBootstrap();
      } else if (name === "platforms") {
        loadProjectPlatforms();
        bindProjectPlatformAdd();
      } else if (name === "environments") {
        bindProjectEnvAdd();
        loadProjectEnvironments();
      }
    };
    document.querySelectorAll("[data-overview-tab]").forEach((btn) => {
      btn.onclick = () => setTab(btn.dataset.overviewTab);
    });
    document.querySelectorAll("[data-overview-tab-jump]").forEach((btn) => {
      btn.onclick = () => setTab(btn.dataset.overviewTabJump);
    });
    const tab = params.get("tab");
    setTab(tab === "channels" || tab === "platforms" || tab === "environments" ? tab : "overview");
  };
  const populateOverviewFilters = (data) => {
    const envSelect = document.getElementById("filterEnvKey");
    const channelSelect = document.getElementById("overviewFilterChannel");
    const platformSelect = document.getElementById("filterPlatform");
    const healthSelect = document.getElementById("filterHealth");
    const filters = overviewFilterParams();
    if (envSelect) {
      const options = data.environment_options || [];
      envSelect.innerHTML = '<option value="">全部环境</option>' + options.map((row) => `<option value="${esc(row.env_key)}">${esc(row.env_label)}</option>`).join("");
      envSelect.value = filters.env_key;
    }
    if (channelSelect) {
      const options = data.channel_options || [];
      channelSelect.innerHTML = '<option value="">全部渠道</option>' + options.map((row) => `<option value="${esc(row.channel_id)}">${esc(row.channel_name)}</option>`).join("");
      channelSelect.value = filters.channel_id;
    }
    if (platformSelect) {
      const options = data.platform_options || [];
      platformSelect.innerHTML = '<option value="">全部平台</option>' + options.map((row) => `<option value="${esc(row.value)}">${esc(row.label)}</option>`).join("");
      platformSelect.value = filters.platform;
    }
    if (healthSelect) {
      const options = data.health_options || [];
      healthSelect.innerHTML = '<option value="">全部状态</option>' + options.map((row) => `<option value="${esc(row.value)}">${esc(row.label)}</option>`).join("");
      healthSelect.value = filters.health;
    }
  };
  const bindOverviewFilters = () => {
    const apply = () => {
      const filters = {
        env_key: document.getElementById("filterEnvKey")?.value || "",
        channel_id: document.getElementById("overviewFilterChannel")?.value || "",
        platform: document.getElementById("filterPlatform")?.value || "",
        health: document.getElementById("filterHealth")?.value || "",
      };
      const url = new URL(location.href);
      ["env_key", "channel_id", "platform", "health"].forEach((key) => {
        if (filters[key]) url.searchParams.set(key, filters[key]);
        else url.searchParams.delete(key);
      });
      history.replaceState(null, "", `${url.pathname}${url.search}`);
      loadOverview().catch((error) => toast(error.message, "error"));
    };
    ["filterEnvKey", "overviewFilterChannel", "filterPlatform"].forEach((id) => {
      const node = document.getElementById(id);
      if (node) node.onchange = apply;
    });
    document.getElementById("btnResetOverviewFilters")?.addEventListener("click", () => {
      const url = new URL(location.href);
      ["env_key", "channel_id", "platform", "health"].forEach((key) => url.searchParams.delete(key));
      history.replaceState(null, "", `${url.pathname}${url.search}`);
      loadOverview().catch((error) => toast(error.message, "error"));
    });
  };
  const envConfigIconFile = (envKey) => {
    const k = String(envKey || "").toLowerCase();
    if (k === "production") return "env_production.svg";
    if (k === "staging") return "env_staging.svg";
    if (k === "testing") return "env_testing.svg";
    if (k === "development") return "env_development.svg";
    return "nav_environment.svg";
  };
  const envConfigIconClass = (envKey) => {
    const k = String(envKey || "").toLowerCase();
    if (k === "production") return "prod";
    if (k === "staging") return "pre";
    if (k === "testing") return "test";
    if (k === "development") return "dev";
    return "custom";
  };
  const formatEnvScopeSummary = (row) => {
    const scope = row.delivery_scope || {};
    const channelLabels = scope.channel_labels || [];
    const platformLabels = scope.platform_labels || [];
    if (!channelLabels.length && !platformLabels.length) {
      return '<div class="env-scope-summary"><span class="env-scope-metrics muted">未读取到交付范围</span></div>';
    }
    const metrics = `${scope.enabled_channel_count || channelLabels.length} 渠道 × ${scope.enabled_platform_count || platformLabels.length} 平台 · ${scope.delivery_line_count || 0} 条交付线`;
    const inheritParts = [];
    if (scope.inherits_project_channels) inheritParts.push("渠道");
    if (scope.inherits_project_platforms) inheritParts.push("平台");
    const inheritNote = inheritParts.length
      ? `<span class="env-scope-inherit">${inheritParts.join("、")}继承项目白名单</span>`
      : "";
    const chips = [
      ...channelLabels.map((name) => `<span class="scope-chip">${esc(name)}</span>`),
      ...platformLabels.map((name) => `<span class="scope-chip platform">${esc(name)}</span>`),
    ].join("");
    return `<div class="env-scope-summary">${inheritNote}<span class="env-scope-metrics">${metrics}</span><div class="env-scope-chips">${chips}</div></div>`;
  };
  const loadProjectEnvironments = async () => {
    const host = document.getElementById("projectEnvList");
    if (!host) return;
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/environments`, { credentials: "same-origin" });
      const result = await response.json();
      const rows = result.data?.environments || result.environments || [];
      host.innerHTML = rows.length
        ? rows.map((row) => {
            const key = esc(row.env_key);
            const builtin = Boolean(row.builtin);
            const enabled = Boolean(row.enabled);
            const toggle = enabled
              ? `<button type="button" class="env-btn warn" data-env-toggle="${key}" data-enabled="0">禁用</button>`
              : `<button type="button" class="env-btn release" data-env-toggle="${key}" data-enabled="1">启用</button>`;
            const remove = builtin ? "" : `<button type="button" class="env-btn warn env-btn-full" data-env-remove="${key}">删除</button>`;
            const scopeBtn = `<button type="button" class="env-btn build" data-scope-env="${key}">配置</button>`;
            const scopeLink = `<a class="env-btn neutral" href="/admin/projects/${encodeURIComponent(projectId)}/environments/${key}">环境详情</a>`;
            const iconCls = envConfigIconClass(row.env_key);
            const iconFile = envConfigIconFile(row.env_key);
            const badgeClass = enabled ? (builtin ? "builtin" : "active") : "disabled";
            const badgeText = enabled ? (builtin ? "内置" : "启用") : "已禁用";
            const cardState = enabled ? " is-ready" : " is-pending is-disabled";
            return `<article class="env-config-card${cardState}">
              <header class="env-config-card-head">
                <div class="env-config-lead">
                  <span class="env-config-icon env-config-icon--${iconCls}"><img src="/static/project_ui/svg/${iconFile}" alt=""></span>
                  <div class="env-config-title">
                    <strong>${esc(row.label)}</strong>
                    <small>${key}</small>
                  </div>
                </div>
                <span class="env-config-badge ${badgeClass}">${badgeText}</span>
              </header>
              ${formatEnvScopeSummary(row)}
              <footer class="env-config-card-foot">
                ${scopeBtn}${scopeLink}${toggle}${remove}
              </footer>
            </article>`;
          }).join("")
        : '<div class="env-config-empty">暂无环境配置</div>';
      host.querySelectorAll("[data-scope-env]").forEach((button) => {
        button.onclick = () => openDeliveryScopeDialog({ envKey: button.dataset.scopeEnv });
      });
      host.querySelectorAll("[data-env-toggle]").forEach((button) => {
        button.onclick = async () => {
          try {
            const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(button.dataset.envToggle)}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json", ...csrfHeaders() },
              credentials: "same-origin",
              body: JSON.stringify({ enabled: button.dataset.enabled === "1" }),
            });
            const result = await response.json();
            if (!response.ok || result.ok === false) throw new Error(parseApiError(result, "更新失败"));
            toast(button.dataset.enabled === "1" ? "环境已启用" : "环境已禁用");
            await loadProjectEnvironments();
            await loadOverview();
          } catch (error) {
            toast(error.message, "error");
          }
        };
      });
      host.querySelectorAll("[data-env-remove]").forEach((button) => {
        button.onclick = async () => {
          if (!confirm(`确认删除环境「${button.dataset.envRemove}」？`)) return;
          try {
            const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(button.dataset.envRemove)}`, {
              method: "DELETE",
              headers: csrfHeaders(),
              credentials: "same-origin",
            });
            const result = await response.json();
            if (!response.ok || result.ok === false) throw new Error(parseApiError(result, "删除失败"));
            toast("环境已删除");
            await loadProjectEnvironments();
            await loadOverview();
          } catch (error) {
            toast(error.message, "error");
          }
        };
      });
    } catch (error) {
      host.innerHTML = `<div class="ui-empty">${esc(error.message || "环境加载失败")}</div>`;
    }
  };
  const platformIcon = (platform) => {
    const key = String(platform || "").toLowerCase();
    if (key.includes("ios")) return "file_ios.svg";
    if (key.includes("win")) return "file_windows.svg";
    return "file_android.svg";
  };
  const formatEnvTime = (raw) => {
    const text = String(raw || "").trim();
    if (!text) return "—";
    const date = new Date(text);
    if (Number.isNaN(date.getTime())) return text.slice(0, 16).replace("T", " ");
    return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).replace(/\//g, "-");
  };
  let scopeDialogEnvKey = "";
  const renderDeliveryMatrixHtml = (lines, envKey, channelJourneys = []) => {
    if (!lines.length) return '<div class="ui-empty">当前环境暂无交付线，请先在项目中配置渠道并初始化 Scope。</div>';
    const journeyMap = new Map((channelJourneys || []).map((row) => [String(row.channel_id || ""), row]));
    const groups = new Map();
    lines.forEach((line) => {
      const cid = String(line.channel_id || "").trim();
      if (!groups.has(cid)) groups.set(cid, { name: line.channel_name || cid, lines: [] });
      groups.get(cid).lines.push(line);
    });
    const scopeApi = window.DeliveryScope || {};
    let html = '<div class="env-line-groups">';
    groups.forEach((group, cid) => {
      html += `<section class="env-line-group"><header class="env-line-group-head"><div><strong>${esc(group.name)}</strong><span>${group.lines.length} 个平台</span></div></header><div class="env-line-cards">`;
      group.lines.forEach((line) => {
        const versionText = line.version_name ? `${line.version_name} / ${line.version_code}` : "未配置";
        const badgeClass = line.configured ? "ready" : "pending";
        const badgeText = line.configured ? "已配置" : "未配置";
        const cardVersionLink = scopeApi.renderCardVersionEntry
          ? scopeApi.renderCardVersionEntry(projectId, envKey, cid, line.platform)
          : `<a class="matrix-btn version env-line-version-btn" href="${esc(scopeApi.versionsPageHref ? scopeApi.versionsPageHref(projectId, { env_key: envKey, channel_id: cid, platform: line.platform }) : scopeHref(`/admin/projects/${projectId}/versions`, { env_key: envKey, channel_id: cid, platform: line.platform }))}">版本</a>`;
        const cardBuildHref = scopeApi.channelJourneyHref ? scopeApi.channelJourneyHref(projectId, envKey, cid, "build", line.platform) : "#";
        const cardReleaseHref = scopeApi.channelJourneyHref ? scopeApi.channelJourneyHref(projectId, envKey, cid, "release", line.platform) : "#";
        const gmHref = scopeHref(`/admin/projects/${projectId}/actions`, { env_key: envKey, channel_id: cid, platform: line.platform });
        const testHref = scopeHref(`/admin/projects/${projectId}/diagnostics`, { env_key: envKey, channel_id: cid, platform: line.platform });
        const topoName = line.topology_name || line.topology_id || "-";
        const topoSource = line.binding_source_label || bindingSourceLabels[line.binding_source] || line.binding_source || "-";
        html += `<article class="env-line-card env-line-card-v2 ${line.configured ? "configured" : "unconfigured"}" data-platform-card="${esc(line.platform || "")}" data-env-key="${esc(envKey)}" data-channel-id="${esc(cid)}" data-channel-name="${esc(group.name || cid)}" data-platform="${esc(line.platform || "")}" data-version-name="${esc(line.version_name || "")}">
          <div class="env-line-card-head">
            <span class="env-line-platform-icon"><img src="/static/project_ui/svg/${platformIcon(line.platform)}" alt=""></span>
            <div class="env-line-card-title">
              <span class="env-line-platform">${esc(line.platform_label || line.platform)}</span>
              <span class="env-line-badge ${badgeClass}">${badgeText}</span>
            </div>
          </div>
          <dl class="env-line-fields">
            <div><dt>版本</dt><dd class="${line.version_name ? "" : "muted"}" title="${esc(versionText)}">${esc(versionText)}</dd></div>
            <div><dt>Bundle</dt><dd class="mono" title="${esc(line.bundle_id || "-")}">${esc(line.bundle_id || "-")}</dd></div>
            <div><dt>拓扑</dt><dd title="${esc(topoName)}"><span class="env-line-topology-name">${esc(topoName)}</span><span class="env-line-topology-source">${esc(topoSource)}</span></dd></div>
          </dl>
          <div class="env-line-version-row">${cardVersionLink}</div>
          <div class="env-line-card-tabs" data-active-tab="client">
            <div class="env-line-tab-head">
              <button type="button" class="env-line-tab is-active" data-card-tab="client">客户端</button>
              <button type="button" class="env-line-tab" data-card-tab="server">服务端</button>
            </div>
            <div class="env-line-tab-pane is-active" data-card-pane="client">
              <div class="env-line-actions env-line-card-links"><a class="matrix-btn build" href="${esc(cardBuildHref)}">构建</a><a class="matrix-btn release" href="${esc(cardReleaseHref)}">发版</a></div>
            </div>
            <div class="env-line-tab-pane" data-card-pane="server">
              <div class="env-line-actions env-line-card-links"><button type="button" class="matrix-btn topology" data-open-topology-drawer>拓扑</button><a class="matrix-btn server-gm" href="${esc(gmHref)}">GM</a><a class="matrix-btn server-test" href="${esc(testHref)}">测试</a></div>
            </div>
          </div>
        </article>`;
      });
      html += "</div></section>";
    });
    html += "</div>";
    return html;
  };
  const renderDeliveryScopeChips = (scope) => {
    const hint = document.getElementById("envDeliveryScopeHint");
    const host = document.getElementById("envDeliveryScopeChips");
    if (!host) return;
    const channels = scope?.assigned_channels || [];
    const platforms = scope?.assigned_platforms || [];
    if (hint) {
      const inhCh = scope?.inherits_project_channels ? "渠道继承项目白名单" : "渠道已单独配置";
      const inhPl = scope?.inherits_project_platforms ? "平台继承项目白名单" : "平台已单独配置";
      const enabledCh = channels.filter((item) => item.enabled).length;
      const enabledPl = platforms.filter((item) => item.enabled).length;
      hint.textContent = `${inhCh} · ${inhPl} · ${enabledCh} 渠道 × ${enabledPl} 平台`;
    }
    const chips = [
      ...channels.map((item) => `<span class="scope-chip${item.enabled ? "" : " is-disabled"}">${esc(item.channel_name)}${item.enabled ? "" : "（禁用）"}</span>`),
      ...platforms.map((item) => `<span class="scope-chip platform${item.enabled ? "" : " is-disabled"}">${esc(item.platform_name)}${item.enabled ? "" : "（禁用）"}</span>`),
    ];
    host.innerHTML = chips.length ? chips.join("") : '<span class="scope-chip muted">继承项目白名单（未单独限制）</span>';
  };
  const loadEnvDeliveryScopeFor = async (envKey) => {
    if (!envKey) return null;
    const scope = await api(`/api/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(envKey)}/delivery-scope`);
    envDeliveryScopeState = scope;
    if (page.dataset.envKey === envKey) renderDeliveryScopeChips(scope);
    return scope;
  };
  const loadEnvDeliveryScope = async () => {
    const envKey = page.dataset.envKey;
    if (!envKey) return null;
    scopeDialogEnvKey = envKey;
    const hint = document.getElementById("envDeliveryScopeHint");
    try {
      return await loadEnvDeliveryScopeFor(envKey);
    } catch (error) {
      if (hint) hint.textContent = error.message || "交付范围加载失败";
      const host = document.getElementById("envDeliveryScopeChips");
      if (host) host.innerHTML = '<span class="scope-chip muted">交付范围暂不可用，请刷新或重启服务后重试</span>';
      return null;
    }
  };
  const clearDeliveryScopeDeepLink = () => {
    const params = new URLSearchParams(location.search);
    let changed = false;
    if (params.get("configure_delivery_scope") === "1") {
      params.delete("configure_delivery_scope");
      changed = true;
    }
    const qs = params.toString();
    const nextUrl = `${location.pathname}${qs ? `?${qs}` : ""}`;
    if (location.hash === "#delivery-scope" || changed) {
      history.replaceState(null, "", nextUrl);
    }
  };
  const openDeliveryScopeDialog = async (options = {}) => {
    const dialog = document.getElementById("deliveryScopeDialog");
    if (!dialog) return;
    const envKey = options.envKey || page.dataset.envKey || scopeDialogEnvKey;
    if (!envKey) return;
    scopeDialogEnvKey = envKey;
    try {
      const scope = await loadEnvDeliveryScopeFor(envKey);
      if (!scope) return;
      const chHost = document.getElementById("deliveryScopeChannels");
      const plHost = document.getElementById("deliveryScopePlatforms");
      const assignedCh = new Set((scope.assigned_channels || []).map((item) => item.channel_id));
      const assignedPl = new Set((scope.assigned_platforms || []).map((item) => item.platform_id));
      const catalogCh = scope.project_channel_catalog || [];
      const catalogPl = scope.project_platform_catalog || [];
      chHost.innerHTML = catalogCh.map((item) => {
        const checked = assignedCh.has(item.channel_id);
        return `<label class="scope-check"><input type="checkbox" value="${esc(item.channel_id)}"${checked ? " checked" : ""}>${esc(item.channel_name)}</label>`;
      }).join("");
      plHost.innerHTML = catalogPl.map((item) => `<label class="scope-check"><input type="checkbox" value="${esc(item.platform_id)}"${assignedPl.has(item.platform_id) ? " checked" : ""}>${esc(item.platform_name)}</label>`).join("");
      const title = document.querySelector("#deliveryScopeDialog h3");
      if (title) title.textContent = "配置环境交付范围";
      dialog.classList.remove("is-hidden");
      dialog.setAttribute("aria-hidden", "false");
    } catch (error) {
      toast(error.message, "error");
    }
  };
  const closeDeliveryScopeDialog = () => {
    const dialog = document.getElementById("deliveryScopeDialog");
    if (!dialog) return;
    dialog.classList.add("is-hidden");
    dialog.setAttribute("aria-hidden", "true");
    clearDeliveryScopeDeepLink();
  };
  const maybeOpenDeliveryScopeFromDeepLink = () => {
    const params = new URLSearchParams(location.search);
    const wantsDialog = params.get("configure_delivery_scope") === "1" || location.hash === "#delivery-scope";
    if (!wantsDialog) return;
    clearDeliveryScopeDeepLink();
    openDeliveryScopeDialog();
  };
  const saveDeliveryScope = async () => {
    const envKey = scopeDialogEnvKey || page.dataset.envKey;
    const btn = document.getElementById("btnSaveDeliveryScope");
    try {
      if (btn) btn.disabled = true;
      let channels = [...document.querySelectorAll("#deliveryScopeChannels input:checked")].map((node) => node.value);
      const platforms = [...document.querySelectorAll("#deliveryScopePlatforms input:checked")].map((node) => node.value);
      const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(envKey)}/delivery-scope`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...csrfHeaders() },
        credentials: "same-origin",
        body: JSON.stringify({ channels, platforms }),
      });
      const result = await parseJsonResponse(response);
      if (!response.ok || result.ok === false) throw new Error(parseApiError(result, "保存失败"));
      envDeliveryScopeState = result.data;
      if (page.dataset.envKey === envKey) renderDeliveryScopeChips(envDeliveryScopeState);
      closeDeliveryScopeDialog();
      toast("交付范围已更新");
      if (page.dataset.deliveryPage === "environment" && page.dataset.envKey === envKey) {
        const summary = await api(`/api/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(envKey)}`);
        const lines = summary.delivery_lines || [];
        document.getElementById("deliveryMatrix").innerHTML = renderDeliveryMatrixHtml(lines, envKey, summary.channel_journeys || []);
        if (typeof window.bindEnvLineCardTabs === "function") window.bindEnvLineCardTabs(document.getElementById("deliveryMatrix"));
      }
      if (page.dataset.deliveryPage === "overview") await loadOverview();
    } catch (error) {
      toast(error.message, "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  };
  const bindDeliveryScopeDialog = () => {
    const editBtn = document.getElementById("btnEditDeliveryScope");
    if (editBtn && editBtn.dataset.bound !== "1") {
      editBtn.dataset.bound = "1";
      editBtn.onclick = openDeliveryScopeDialog;
    }
    const closeBtn = document.getElementById("btnCloseDeliveryScope");
    const cancelBtn = document.getElementById("btnCancelDeliveryScope");
    const saveBtn = document.getElementById("btnSaveDeliveryScope");
    if (closeBtn && closeBtn.dataset.bound !== "1") {
      closeBtn.dataset.bound = "1";
      closeBtn.onclick = closeDeliveryScopeDialog;
    }
    if (cancelBtn && cancelBtn.dataset.bound !== "1") {
      cancelBtn.dataset.bound = "1";
      cancelBtn.onclick = closeDeliveryScopeDialog;
    }
    if (saveBtn && saveBtn.dataset.bound !== "1") {
      saveBtn.dataset.bound = "1";
      saveBtn.onclick = saveDeliveryScope;
    }
  };
  const bindProjectEnvAdd = () => {
    const button = document.getElementById("btnProjectEnvAdd");
    if (!button || button.dataset.bound === "1") return;
    button.dataset.bound = "1";
    button.onclick = async () => {
      const envKey = document.getElementById("projectEnvKeyInput")?.value?.trim() || "";
      const label = document.getElementById("projectEnvLabelInput")?.value?.trim() || "";
      if (!envKey || !label) {
        toast("请填写环境 key 与名称", "error");
        return;
      }
      try {
        button.disabled = true;
        const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/environments`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...csrfHeaders() },
          credentials: "same-origin",
          body: JSON.stringify({ env_key: envKey, label }),
        });
        const result = await response.json();
        if (!response.ok || result.ok === false) throw new Error(parseApiError(result, "添加失败"));
        toast("环境已添加");
        document.getElementById("projectEnvKeyInput").value = "";
        document.getElementById("projectEnvLabelInput").value = "";
        await loadProjectEnvironments();
        await loadOverview();
      } catch (error) {
        toast(error.message, "error");
      } finally {
        button.disabled = false;
      }
    };
  };
  const bindProjectChannelAdd = () => {
    const button = document.getElementById("btnProjectChannelAdd");
    const select = document.getElementById("projectChannelAddSelect");
    if (!button || !select || button.dataset.bound === "1") return;
    button.dataset.bound = "1";
    button.onclick = async () => {
      const channelId = select.value;
      if (!channelId) {
        toast("请先选择渠道", "error");
        return;
      }
      try {
        button.disabled = true;
        const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/channels/add`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...csrfHeaders() },
          credentials: "same-origin",
          body: JSON.stringify({ channel_id: channelId }),
        });
        const result = await response.json();
        if (!response.ok || result.error || result.ok === false) throw new Error(parseApiError(result, "添加失败"));
        toast("渠道已添加");
        select.value = "";
        await loadProjectChannels();
        if (page.dataset.deliveryPage === "overview") await loadOverview();
      } catch (error) {
        toast(error.message, "error");
      } finally {
        button.disabled = false;
      }
    };
  };
  const bindProjectPlatformAdd = () => {
    const button = document.getElementById("btnProjectPlatformAdd");
    const select = document.getElementById("projectPlatformAddSelect");
    if (!button || !select || button.dataset.bound === "1") return;
    button.dataset.bound = "1";
    button.onclick = async () => {
      const platformId = select.value;
      if (!platformId) {
        toast("请先选择平台", "error");
        return;
      }
      try {
        button.disabled = true;
        const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/platforms/add`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...csrfHeaders() },
          credentials: "same-origin",
          body: JSON.stringify({ platform_id: platformId }),
        });
        const result = await response.json();
        if (!response.ok || result.ok === false) throw new Error(parseApiError(result, "添加失败"));
        if (result.error && typeof result.error === "string") throw new Error(result.error);
        if (result.data?.already_exists || result.already_exists) {
          toast("该平台已在项目白名单中");
        } else {
          toast("平台已添加");
        }
        select.value = "";
        await loadProjectPlatforms();
        if (page.dataset.deliveryPage === "overview") await loadOverview();
      } catch (error) {
        toast(error.message, "error");
      } finally {
        button.disabled = false;
      }
    };
  };
  const renderOverviewChannelTabs = (channelOptions, activeChannelId) => {
    const host = document.getElementById("overviewChannelTabs");
    if (!host) return;
    const tabs = [{ id: "", name: "全部渠道" }, ...(channelOptions || []).map((row) => ({ id: row.channel_id, name: row.channel_name }))];
    host.innerHTML = tabs.map((tab) => `<button type="button" class="overview-channel-tab${activeChannelId === tab.id ? " active" : ""}" data-overview-channel-id="${esc(tab.id)}">${esc(tab.name)}</button>`).join("");
    host.querySelectorAll("[data-overview-channel-id]").forEach((button) => {
      button.onclick = () => {
        const channelId = button.dataset.overviewChannelId || "";
        const url = new URL(location.href);
        if (channelId) url.searchParams.set("channel_id", channelId);
        else url.searchParams.delete("channel_id");
        history.replaceState(null, "", `${url.pathname}${url.search}`);
        loadOverview().catch((error) => toast(error.message, "error"));
      };
    });
  };

  let overviewActivityEvents = [];
  const envCardIcon = (envKey) => {
    const key = String(envKey || "").toLowerCase();
    if (key === "production") return "status_warning.svg";
    if (key === "staging") return "action_filter.svg";
    if (key === "testing") return "status_info.svg";
    return "nav_environment.svg";
  };
  const envHealthPercent = (health) => {
    if (health === "healthy") return "98.6";
    if (health === "processing") return "92.0";
    if (health === "warning") return "78.5";
    if (health === "blocked") return "45.0";
    return "0.0";
  };
  const envShortKey = (envKey) => {
    const map = { development: "dev", testing: "test", staging: "pre", production: "prod" };
    return map[String(envKey || "").toLowerCase()] || String(envKey || "");
  };
  const formatPlatformLabels = (platforms) => {
    const labels = { android: "Android", ios: "iOS", windows: "Windows", webgl: "WebGL", macos: "macOS" };
    const list = (platforms || []).map((p) => labels[String(p || "").toLowerCase()] || p);
    return list.length ? list.join(" / ") : "多平台";
  };
  const renderOverviewActivity = (tab = "all") => {
    const host = document.getElementById("overviewActivity");
    if (!host) return;
    const filtered = tab === "all"
      ? overviewActivityEvents
      : overviewActivityEvents.filter((item) => item.kind === tab);
    host.innerHTML = filtered.length
      ? filtered.map((item) => `<a class="p02-activity-item" href="${esc(item.href)}"><span class="p02-activity-type ${esc(item.kind)}">${esc(item.typeLabel)}</span><div class="p02-activity-body"><strong>${esc(item.title)}</strong></div><span class="p02-activity-meta"><img src="/static/project_ui/svg/global_user.svg" alt="">${esc(item.actor)} ${esc(item.time)}</span></a>`).join("")
      : '<div class="p02-empty">暂无最近动态</div>';
  };
  const bindOverviewActivityTabs = () => {
    document.querySelectorAll(".p02-activity-tab[data-activity-tab]").forEach((button) => {
      button.onclick = () => {
        document.querySelectorAll(".p02-activity-tab[data-activity-tab]").forEach((b) => b.classList.toggle("active", b === button));
        renderOverviewActivity(button.dataset.activityTab || "all");
      };
    });
  };

  async function loadOverview() {
    if (typeof window.__P02_loadOverview === "function") {
      return window.__P02_loadOverview();
    }
    const data = await api(`/api/projects/${encodeURIComponent(projectId)}/overview${overviewQueryString()}`);
    populateOverviewFilters(data);
    const activeChannelId = overviewFilterParams().channel_id || "";
    const cards = data.environments || [];
    const allOrders = cards.flatMap((item) => item.latest_orders || []);
    const sortedOrders = [...allOrders].sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
    const latestOrder = sortedOrders[0];
    const memberCount = Number(page.dataset.memberCount || 0);
    const k = data.kpis || {};
    const links = k.links || {};
    const versionText = k.current_version && k.current_version !== "—"
      ? (k.current_version_code ? `${k.current_version} / ${k.current_version_code}` : k.current_version)
      : "—";
    const healthVal = k.service_health_pct == null ? "—" : `${k.service_health_pct}%`;
    const kpis = [
      ["kpi_version.svg", "当前版本", versionText, "blue", "", links.version || scopeHref(`/admin/projects/${projectId}/versions`, { env_key: overviewFilterParams().env_key || "production" })],
      ["kpi_health.svg", "服务健康度", healthVal, "green", k.service_health_source === "ops" ? "Ops 探针" : "", links.health || `/admin/projects/${projectId}/environments/${encodeURIComponent(overviewFilterParams().env_key || "production")}/runtime`],
      ["kpi_build.svg", "今日构建次数", String(k.today_build_count ?? 0), "violet", "", links.builds || `/admin/projects/${projectId}/build-history`],
      ["kpi_change.svg", "待处理变更", String(k.pending_changes ?? 0), "orange", "", links.changes || `/admin/projects/${projectId}/release-orders?status=awaiting_approval`],
      ["kpi_member.svg", "项目成员", String(k.member_count ?? memberCount), "cyan", "", links.members || `/admin/projects/${projectId}/settings?tab=members`],
    ];
    document.getElementById("overviewKpis").innerHTML = kpis.map(([icon, label, value, tone, sub, link], i) => {
      return `<article class="pm-kpi-card"><span class="pm-kpi-icon pm-kpi-icon--${tone}"><img src="/static/project_ui/svg/${icon}" alt=""></span><div class="pm-kpi-body"><span>${label}</span><strong>${value}</strong>${sub ? `<span class="pm-kpi-trend up">${sub}</span>` : ""}${link ? `<a class="pm-kpi-footlink" href="${link}">${label === "当前版本" ? "版本详情" : label === "服务健康度" ? "健康概览" : label === "今日构建次数" ? "构建与产物" : label === "待处理变更" ? "变更治理" : "成员管理"} &gt;</a>` : ""}</div></article>`;
    }).join("");
    const channelNameMap = Object.fromEntries((data.channel_options || []).map((row) => [row.channel_id, row.channel_name]));
    document.getElementById("environmentCards").innerHTML = cards.length
      ? cards.map((item) => {
          const channelText = activeChannelId
            ? (channelNameMap[activeChannelId] || activeChannelId)
            : ((item.channel_ids?.length ? `${item.channel_ids.length} 个渠道` : "全部渠道"));
          const platformText = formatPlatformLabels(item.platforms);
          const healthPctCard = envHealthPercent(item.health);
          const healthClass = Number(healthPctCard) >= 95 ? "good" : Number(healthPctCard) >= 80 ? "warn" : "bad";
          const instances = `${item.configured_line_count || 0} / ${item.delivery_line_count || 0}`;
          const agentStatus = item.health === "healthy" || item.health === "processing" ? `${item.configured_line_count || 0} 在线` : "异常";
          const updatedAt = new Date().toLocaleString("zh-CN", { hour: "2-digit", minute: "2-digit" });
          const badgeClass = item.env_key === "production" ? "production" : (item.health === "healthy" || item.health === "processing") ? "running" : item.health === "unconfigured" ? "muted" : "warning";
          const badgeText = item.env_key === "production" ? "生产" : (item.health === "healthy" || item.health === "processing") ? "运行中" : item.health === "unconfigured" ? "未配置" : "预警";
          return `<article class="p02-env-card">
      <header class="p02-env-card-head">
        <div class="p02-env-card-title"><img src="/static/project_ui/svg/${envCardIcon(item.env_key)}" alt=""><h3>${esc(item.env_label)}</h3></div>
        <span class="p02-env-badge ${badgeClass}">${esc(badgeText)}</span>
      </header>
      <div class="p02-env-fields">
        <div><span>环境</span><strong>${esc(envShortKey(item.env_key))}</strong></div>
        <div><span>渠道</span><strong>${esc(channelText)}</strong></div>
        <div><span>平台</span><strong>${esc(platformText)}</strong></div>
      </div>
      <div class="p02-env-metrics">
        <div><span>服务健康度</span><strong class="health ${healthClass}">${healthPctCard}%</strong></div>
        <div><span>在线实例</span><strong>${instances}</strong></div>
        <div><span>Agent 状态</span><strong>${esc(agentStatus)}</strong></div>
        <div><span>更新时间</span><strong>${updatedAt}</strong></div>
      </div>
      <footer class="p02-env-footer"><a href="/admin/projects/${projectId}/environments/${item.env_key}">环境详情<img src="/static/project_ui/svg/action_next.svg" alt=""></a></footer>
    </article>`;
        }).join("")
      : '<div class="p02-empty">当前筛选下无匹配环境</div>';
    overviewActivityEvents = (data.activities || []).map((item) => ({
      kind: item.kind || "release",
      typeLabel: item.type_label || item.typeLabel || "发布",
      title: item.title || "",
      actor: item.actor || "系统",
      time: item.time_short || String(item.time || "").slice(11, 16) || String(item.time || "").slice(0, 16),
      href: item.href || "#",
    }));
    const activeTab = document.querySelector("[data-activity-tab].active")?.dataset.activityTab || "all";
    renderOverviewActivity(activeTab);
    document.getElementById("overviewUpdatedAt").textContent = new Date().toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }).replace(/\//g, "-");
  }

  async function loadEnvironmentDetail() {
    const envKey = page.dataset.envKey;
    const data = await api(`/api/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(envKey)}`);
    document.getElementById("envDetailTitle").textContent = data.env_label || envKey;
    const lines = data.delivery_lines || [];
    document.getElementById("deliveryMatrix").innerHTML = renderDeliveryMatrixHtml(lines, envKey, data.channel_journeys || []);
    if (typeof window.bindEnvLineCardTabs === "function") window.bindEnvLineCardTabs(document.getElementById("deliveryMatrix"));
    const orders = data.release_orders || [];
    document.getElementById("envOrders").innerHTML = orders.length
      ? orders.slice(0, 6).map((item) => {
          const label = statusLabels[item.status] || item.status || "—";
          const tone = String(item.status || "").includes("failed") ? "blocked" : ["building", "prechecking", "publishing", "verifying"].includes(item.status) ? "processing" : item.status === "awaiting_approval" ? "warning" : item.status === "draft" ? "draft" : "ready";
          return `<a class="env-order-row" href="/admin/projects/${projectId}/release-orders/${item.release_order_id}"><span class="status-pill ${tone}">${esc(label)}</span><div class="env-order-main"><strong>${esc(item.version_name)} / ${esc(item.version_code)}</strong><small>${esc(item.channel_name || "")} · ${esc(item.platform || "")}</small></div><span class="env-order-time">${esc(formatEnvTime(item.updated_at))}</span></a>`;
        }).join("")
      : '<div class="ui-empty">本环境暂无进行中的发布单</div>';
    const manifest = data.manifest || {};
    document.getElementById("manifestStatus").textContent = manifest.project_id ? `Manifest 已注册（${manifest.channels?.length || 0} 个渠道）` : "尚未注册 Manifest";
    document.getElementById("btnBootstrapScopes").onclick = async () => {
      try {
        const result = await fetch(`/api/release/manifests/${encodeURIComponent(projectId)}/bootstrap-scopes`, {
          method: "POST",
          headers: { "X-CSRFToken": document.querySelector('meta[name="csrf-token"]')?.content || "" },
          credentials: "same-origin",
        }).then((r) => r.json());
        if (!result.ok) throw new Error(result.error || "初始化失败");
        toast(`已初始化 ${result.count || 0} 条交付线 Scope`);
        await loadEnvironmentDetail();
      } catch (error) {
        toast(error.message, "error");
      }
    };
    await loadEnvDeliveryScope();
    bindDeliveryScopeDialog();
    await loadProjectPlatforms();
    const scopeApi = window.DeliveryScope || {};
    if (scopeApi.bindQuickBuild) {
      scopeApi.bindQuickBuild(page, {
        projectId,
        request: api,
        onSuccess: (order) => {
          toast(order.status === "building" ? "构建已触发" : "操作已提交");
          const oid = order.release_order_id;
          if (oid) {
            const qs = buildScopeQuery({
              env_key: order.env_key,
              channel_id: order.channel_id,
              platform: order.platform,
              version_id: order.version_id,
              version_name: order.version_name,
              version_code: order.version_code,
              release_order_id: oid,
            });
            location.href = `/admin/projects/${projectId}/release-orders/${oid}${qs}`;
            return;
          }
          loadEnvironmentDetail().catch((error) => toast(error.message, "error"));
        },
        onError: (error) => toast(error.message || "操作失败", "error"),
      });
    }
    if (scopeApi.bindMatrixMoreMenus) scopeApi.bindMatrixMoreMenus(page);
    maybeOpenDeliveryScopeFromDeepLink();
  }

  const renderOrderTable = (items) => {
    const host = document.getElementById("releaseOrderList");
    host.innerHTML = `<div class="order-table-head"><span>发布单 / 版本</span><span>目标</span><span>状态</span><span>拓扑 / Runtime</span><span>更新时间</span><span>操作</span></div>` + (items.length ? items.map(item=>{
      const context=buildScopeQuery({env_key:item.env_key,channel_id:item.channel_id,platform:item.platform,version_id:item.version_id,version_name:item.version_name,version_code:item.version_code,release_order_id:item.release_order_id});
      return `<div class="order-table-row"><div><strong>${esc(item.release_order_id)}</strong><small>${esc(item.version_name)} / ${esc(item.version_code)}</small></div><div>${esc(envLabels[item.env_key])}<small>${esc(item.channel_name)} / ${esc(item.platform)}</small></div><div>${status(item.status)}</div><div>${esc(item.topology_id || "待解析")}<small>${esc(item.runtime_run_id || "未运行")}</small></div><div>${esc(item.updated_at)}</div><div class="row-actions"><a class="ui-secondary" href="/admin/projects/${projectId}/release-orders/${item.release_order_id}${context}">详情</a>${["draft","artifacts_ready","precheck_failed"].includes(item.status)?`<a class="ui-secondary" href="/admin/projects/${projectId}/release-orders/${item.release_order_id}/edit${context}">编辑</a>`:""}</div></div>`;
    }).join("") : '<div class="ui-empty">当前筛选条件下暂无发布单</div>');
  };
  async function setupOrders() {
    const options = await api(`/api/projects/${projectId}/context-options`);
    const fills = [["env_key",options.environments,"env_key","label"],["channel_id",options.channels,"channel_id","channel_name"],["platform",options.platforms,"value","label"]];
    fills.forEach(([name,items,key,label])=>{const select=page.querySelector(`[data-filter="${name}"]`);items.forEach(item=>select.insertAdjacentHTML("beforeend",`<option value="${esc(item[key])}">${esc(item[label])}</option>`));});
    const statusSelect=page.querySelector('[data-filter="status"]');Object.entries(statusLabels).forEach(([key,label])=>statusSelect.insertAdjacentHTML("beforeend",`<option value="${key}">${label}</option>`));
    const searchParams = new URLSearchParams(location.search);
    page.querySelectorAll("[data-filter]").forEach(select => searchParams.get(select.dataset.filter) && (select.value = searchParams.get(select.dataset.filter)));
    const load = async () => {
      const params=new URLSearchParams();page.querySelectorAll("[data-filter]").forEach(x=>x.value&&params.set(x.dataset.filter,x.value));
      let items=await api(`/api/projects/${projectId}/release-orders?${params}`);
      const search=page.querySelector("[data-order-search]").value.trim().toLowerCase();if(search)items=items.filter(x=>JSON.stringify(x).toLowerCase().includes(search));
      renderOrderTable(items);
      const summary=[["发布单总数",items.length],["处理中",items.filter(x=>["building","prechecking","publishing","verifying"].includes(x.status)).length],["待审批",items.filter(x=>x.status==="awaiting_approval").length],["阻断",items.filter(x=>["precheck_failed","publish_failed","verify_failed"].includes(x.status)).length]];
      document.getElementById("orderSummary").innerHTML=summary.map(([label,value],i)=>{const tones=["blue","orange","violet","red"];return `<article class="pm-kpi-card"><span class="pm-kpi-icon pm-kpi-icon--${tones[i]||"blue"}"><img src="/static/project_ui/svg/nav_release_order.svg" alt=""></span><div class="pm-kpi-body"><span>${label}</span><strong>${value}</strong></div></article>`;}).join("");
    };
    page.querySelectorAll("[data-filter]").forEach(x=>x.addEventListener("change",load));page.querySelector("[data-order-search]").addEventListener("input",load);page.querySelector("[data-refresh-orders]").addEventListener("click",load);
    document.addEventListener("pm-shell-search",(e)=>{const input=page.querySelector("[data-order-search]");if(input){input.value=e.detail?.query||"";load();}});
    load();
  }

  async function setupOrderForm() {
    return window.DeliveryOrderForm.setupOrderForm({ page, projectId, api, toast });
  }


  const type=page.dataset.deliveryPage;
  if(type==="overview"){
    if(window.__P02_OVERVIEW__){
      bindDeliveryScopeDialog();
      bindProjectEnvAdd();
      var tab=new URLSearchParams(location.search).get("tab");
      if(tab==="channels"){loadProjectChannels();bindProjectChannelAdd();bindManifestBootstrap();}
      else if(tab==="platforms"){loadProjectPlatforms();bindProjectPlatformAdd();}
      else if(tab==="environments"){loadProjectEnvironments();}
    }else{
      initOverviewTabs();
      bindOverviewFilters();
      bindOverviewActivityTabs();
      bindDeliveryScopeDialog();
      bindProjectEnvAdd();
      loadOverview().catch(error=>toast(error.message,"error"));
      page.querySelector("[data-refresh-overview]")?.addEventListener("click",()=>loadOverview().catch(error=>toast(error.message,"error")));
    }
    document.addEventListener("pm-shell-search",(e)=>{const q=e.detail?.query||"";if(!q)return;const cards=document.querySelectorAll(".p02-env-card,.p02-activity-item");cards.forEach(el=>{el.style.display=el.textContent?.toLowerCase().includes(q.toLowerCase())?"":"none";});});
  }
  if(type==="environment"){
    if(window.TopologyBindingDrawer){
      window.TopologyBindingDrawer.init({projectId,onSaved:loadEnvironmentDetail});
      window.TopologyBindingDrawer.maybeOpenFromQuery();
    }
    loadEnvironmentDetail().catch(error=>toast(error.message,"error"));
    page.querySelector("[data-refresh-env]")?.addEventListener("click",loadEnvironmentDetail);
  }
  if(type==="orders")setupOrders().catch(error=>toast(error.message,"error"));
  if(type==="order-form")setupOrderForm().catch(error=>toast(error.message,"error"));
})();
