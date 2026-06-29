(() => {
  const page = document.querySelector("[data-delivery-page]");
  if (!page) return;
  const projectId = page.dataset.projectId;
  const envLabels = {development:"开发环境",testing:"测试环境",staging:"预发环境",production:"生产环境"};
  const statusLabels = {draft:"草稿",building:"构建中",artifacts_ready:"产物已就绪",prechecking:"预检中",precheck_failed:"预检失败",ready:"可发布",awaiting_approval:"待审批",approved:"已审批",publishing:"发布中",published:"已发布",publish_failed:"发布失败",verifying:"验证中",verified:"验证通过",verify_failed:"验证失败",rolled_back:"已回滚",cancelled:"已取消"};
  const artifactStatusLabels = {registered:"已登记",available:"可用",reachable:"可达",missing:"缺失",unreachable:"不可达",invalid:"无效"};
  const artifactTypeLabels = {apk:"APK 安装包",resource:"资源包",config:"配置包",code:"代码热更包"};
  const bindingSourceLabels = {project_default:"项目默认",env_channel:"环境与渠道",version:"大版本覆盖",version_override:"大版本覆盖",default:"项目默认"};
  const parseApiError = (result, fallback) => {
    if (!result || typeof result !== "object") return fallback;
    const err = result.error;
    if (typeof err === "string" && err) return err;
    if (err && typeof err === "object") return err.message || err.text || fallback;
    return result.error_text || result.error_legacy || fallback;
  };
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const parseJsonResponse = async (response) => {
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      const text = await response.text();
      if (response.status === 401 || text.trim().startsWith("<")) {
        throw new Error(response.status >= 500 ? `服务异常 (${response.status})，请刷新后重试` : "会话已过期，请重新登录后重试");
      }
      throw new Error(`请求失败 (${response.status})`);
    }
    return response.json();
  };
  const api = async (path, options = {}) => {
    const response = await fetch(path, { ...options, credentials: "same-origin" });
    const result = await parseJsonResponse(response);
    if (!response.ok || result.ok === false) {
      const err = result.error;
      const message = typeof err === "string" ? err : err?.message || result.error_text || result.error_legacy || "请求失败";
      throw new Error(message);
    }
    return result.data;
  };
  const toast = (message, type="success") => {
    let host = document.querySelector(".toast-stack");
    if (!host) { host = document.createElement("div"); host.className = "toast-stack"; document.body.append(host); }
    const node = document.createElement("div"); node.className = `toast ${type}`; node.textContent = message; host.append(node); setTimeout(() => node.remove(), 3500);
  };
  const status = (value) => `<span class="status-pill ${esc(value)}">${esc(statusLabels[value] || value || "未配置")}</span>`;
  const row = (label, value, extra="") => `<div class="detail-row"><strong>${esc(label)}</strong><span>${esc(value || "-")}</span><b>${extra}</b></div>`;
  const csrfHeaders = () => {
    const token = document.querySelector('meta[name="csrf-token"]');
    return token && token.content ? { "X-CSRFToken": token.content } : {};
  };
  const matrixActions = (line, envKey) => {
    const baseQuery = `env_key=${encodeURIComponent(envKey)}&channel_id=${encodeURIComponent(line.channel_id)}&platform=${encodeURIComponent(line.platform)}`;
    const viewVersionsHref = `/admin/projects/${projectId}/versions?${baseQuery}`;
    const addVcHref = `${viewVersionsHref}&action=create_vc`;
    const primary = line.configured
      ? `<a class="matrix-btn primary" href="/admin/projects/${projectId}/release-orders/new?${baseQuery}">发布</a>`
      : `<a class="matrix-btn primary" href="${addVcHref}">添加 VC</a>`;
    return `<div class="matrix-actions">${primary}<a class="matrix-btn" href="${viewVersionsHref}">版本</a><a class="matrix-btn" href="/admin/projects/${projectId}/topology-bindings?${baseQuery}">拓扑</a></div>`;
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
  const loadPlatformCatalog = async () => {
    if (platformCatalogCache) return platformCatalogCache;
    const result = await fetch("/api/release/platform-catalog", { credentials: "same-origin" }).then((r) => r.json());
    if (!result.ok) throw new Error(result.error || "平台目录加载失败");
    platformCatalogCache = (result.data || []).map((row) => ({
      id: String(row.id || "").toLowerCase(),
      name: String(row.name || row.id || ""),
    }));
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
          return `<div class="channel-item${status}"><div><strong>${esc(item.name)}</strong><small>ID: ${esc(item.id)}${meta}</small></div><div class="channel-actions">${toggle}${remove}</div></div>`;
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
      ? assigned.map((item) => `<span class="channel-chip${item.enabled ? "" : " is-disabled"}">${esc(item.name)}${item.enabled ? "" : "（已禁用）"}</span>`).join("")
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
    const setTab = (name) => {
      document.querySelectorAll("[data-overview-tab]").forEach((btn) => btn.classList.toggle("active", btn.dataset.overviewTab === name));
      document.querySelectorAll("[data-overview-panel]").forEach((panel) => {
        const show = panel.dataset.overviewPanel === name;
        panel.classList.toggle("is-hidden", !show);
        panel.hidden = !show;
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
    document.getElementById("btnManageEnvironments")?.addEventListener("click", () => setTab("environments"));
    const tab = params.get("tab");
    setTab(tab === "channels" || tab === "platforms" || tab === "environments" ? tab : "overview");
  };
  const populateOverviewFilters = (data) => {
    const envSelect = document.getElementById("filterEnvKey");
    const platformSelect = document.getElementById("filterPlatform");
    const healthSelect = document.getElementById("filterHealth");
    const filters = overviewFilterParams();
    if (envSelect) {
      const options = data.environment_options || [];
      envSelect.innerHTML = '<option value="">全部环境</option>' + options.map((row) => `<option value="${esc(row.env_key)}">${esc(row.env_label)}</option>`).join("");
      envSelect.value = filters.env_key;
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
        channel_id: overviewFilterParams().channel_id || "",
        platform: document.getElementById("filterPlatform")?.value || "",
        health: document.getElementById("filterHealth")?.value || "",
      };
      const url = new URL(location.href);
      ["env_key", "platform", "health"].forEach((key) => {
        if (filters[key]) url.searchParams.set(key, filters[key]);
        else url.searchParams.delete(key);
      });
      if (filters.channel_id) url.searchParams.set("channel_id", filters.channel_id);
      else url.searchParams.delete("channel_id");
      history.replaceState(null, "", `${url.pathname}${url.search}`);
      loadOverview().catch((error) => toast(error.message, "error"));
    };
    ["filterEnvKey", "filterPlatform", "filterHealth"].forEach((id) => {
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
              ? `<button type="button" class="env-disable" data-env-toggle="${key}" data-enabled="0">禁用</button>`
              : `<button type="button" class="env-enable" data-env-toggle="${key}" data-enabled="1">启用</button>`;
            const remove = builtin ? "" : `<button type="button" class="env-remove" data-env-remove="${key}">删除</button>`;
            const scopeBtn = `<button type="button" class="env-scope-config" data-scope-env="${key}">配置</button>`;
            const scopeLink = `<a class="env-scope-link" href="/admin/projects/${encodeURIComponent(projectId)}/environments/${key}#delivery-scope">环境详情</a>`;
            return `<div class="env-config-item${enabled ? "" : " is-disabled"}"><div class="env-config-main"><strong>${esc(row.label)}</strong><small>${key}${builtin ? " · 内置" : ""}${enabled ? "" : " · 已禁用"}</small>${formatEnvScopeSummary(row)}</div><div class="env-config-actions">${scopeBtn}${scopeLink}${toggle}${remove}</div></div>`;
          }).join("")
        : '<div class="ui-empty">暂无环境配置</div>';
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
  let envDeliveryScopeState = null;
  let scopeDialogEnvKey = "";
  const renderDeliveryMatrixHtml = (lines, envKey) => {
    if (!lines.length) return '<div class="ui-empty">当前环境暂无交付线，请先在项目中配置渠道并初始化 Scope。</div>';
    const groups = new Map();
    lines.forEach((line) => {
      const cid = String(line.channel_id || "").trim();
      if (!groups.has(cid)) groups.set(cid, { name: line.channel_name || cid, lines: [] });
      groups.get(cid).lines.push(line);
    });
    let html = `<div class="matrix-head"><span>渠道</span><span>平台</span><span>当前版本</span><span>拓扑</span><span>Bundle</span><span>操作</span></div>`;
    groups.forEach((group) => {
      html += `<div class="matrix-group-head"><strong>${esc(group.name)}</strong><span>${group.lines.length} 个平台</span></div>`;
      group.lines.forEach((line) => {
        const versionText = line.version_name ? `${line.version_name} / ${line.version_code}` : "未配置";
        html += `<div class="matrix-row ${line.configured ? "" : "unconfigured"}">
          <div><strong>${esc(line.channel_name)}</strong></div>
          <div>${esc(line.platform_label || line.platform)}</div>
          <div>${esc(versionText)}</div>
          <div>${esc(line.topology_id || "-")}</div>
          <div>${esc(line.bundle_id || "-")}</div>
          ${matrixActions(line, envKey)}
        </div>`;
      });
    });
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
        document.getElementById("deliveryMatrix").innerHTML = renderDeliveryMatrixHtml(lines, envKey);
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
  const currentContext = () => {
    const source = new URLSearchParams(location.search);
    const query = new URLSearchParams();
    ["env_key","channel_id","platform","version_name","version_code","release_order_id"].forEach(key => source.get(key) && query.set(key, source.get(key)));
    return query.toString() ? `?${query}` : "";
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

  async function loadOverview() {
    const assignedChannels = await loadProjectChannels();
    renderChannelChips(assignedChannels);
    const assignedPlatforms = await loadProjectPlatforms();
    renderPlatformChips(assignedPlatforms);
    const activeChannelId = overviewFilterParams().channel_id || "";
    const data = await api(`/api/projects/${encodeURIComponent(projectId)}/overview${overviewQueryString()}`);
    populateOverviewFilters(data);
    renderOverviewChannelTabs(data.channel_options || [], activeChannelId);
    const cards = data.environments || [];
    const totalOrders = cards.reduce((sum, item) => sum + item.release_order_count, 0);
    const totalLines = cards.reduce((sum, item) => sum + (item.delivery_line_count || 0), 0);
    const configuredLines = cards.reduce((sum, item) => sum + (item.configured_line_count || 0), 0);
    const kpis = [
      ["kpi_health.svg", "交付线总数", totalLines],
      ["kpi_health.svg", "已配置交付线", configuredLines],
      ["kpi_build.svg", "处理中任务", cards.reduce((s, x) => s + x.processing_count, 0)],
      ["kpi_change.svg", "待处理变更", cards.reduce((s, x) => s + x.failed_count + x.pending_approval_count, 0)],
      ["kpi_member.svg", "发布单总数", totalOrders],
    ];
    document.getElementById("overviewKpis").innerHTML = kpis.map(([icon, label, value]) => `<article class="kpi-card"><img src="/static/project_ui/svg/${icon}" alt=""><div><span>${label}</span><strong>${value}</strong></div></article>`).join("");
    const healthLabels = { healthy: "运行中", blocked: "存在阻断", warning: "待处理", processing: "处理中", unconfigured: "未配置" };
    document.getElementById("environmentCards").innerHTML = cards.length
      ? cards.map((item) => {
          const channelHint = activeChannelId && item.channel_platform_labels?.length
            ? `本渠道平台：${item.channel_platform_labels.join("、")}`
            : (item.blocker_hint || (item.unconfigured_line_count ? `还有 ${item.unconfigured_line_count} 条交付线未配置` : "各渠道×平台交付线可在环境详情中查看"));
          const versionQuery = activeChannelId
            ? `env_key=${encodeURIComponent(item.env_key)}&channel_id=${encodeURIComponent(activeChannelId)}`
            : `env_key=${encodeURIComponent(item.env_key)}`;
          const scopeBtn = `<button type="button" class="matrix-btn" data-config-scope="${esc(item.env_key)}">配置范围</button>`;
          return `<article class="environment-card">
      <div class="environment-head"><h3>${esc(item.env_label)}</h3><span class="environment-status ${item.health}">${healthLabels[item.health] || item.health}</span></div>
      <div class="environment-summary">
        <div><span>交付线</span><strong>${item.configured_line_count || 0} / ${item.delivery_line_count || 0}</strong></div>
        <div><span>阻断</span><strong>${item.failed_count || 0}</strong></div>
        <div><span>进行中</span><strong>${item.processing_count || 0}</strong></div>
        <div><span>待审批</span><strong>${item.pending_approval_count || 0}</strong></div>
      </div>
      <p class="environment-hint">${esc(channelHint)}</p>
      <div class="environment-action-bar">
        <a class="matrix-btn primary" href="/admin/projects/${projectId}/environments/${item.env_key}">环境详情</a>
        <a class="matrix-btn" href="/admin/projects/${projectId}/versions?${versionQuery}">版本</a>
        <a class="matrix-btn" href="/admin/projects/${projectId}/topology-bindings?env_key=${item.env_key}">拓扑</a>
        ${scopeBtn}
      </div>
      <div class="environment-actions"><a class="icon-link" href="/admin/projects/${projectId}/release-orders?env_key=${item.env_key}">查看发布单<img src="/static/project_ui/svg/action_next.svg" alt=""></a></div>
    </article>`;
        }).join("")
      : '<div class="ui-empty">当前筛选下无匹配环境</div>';
    document.querySelectorAll("[data-config-scope]").forEach((button) => {
      button.onclick = () => openDeliveryScopeDialog({ envKey: button.dataset.configScope });
    });
    const events = cards.flatMap((item) => item.latest_orders || []).sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at))).slice(0, 7);
    document.getElementById("overviewActivity").innerHTML = events.length ? events.map((item) => `<a class="activity-row" href="/admin/projects/${projectId}/release-orders/${item.release_order_id}"><span>${status(item.status)}</span><strong>${esc(item.version_name)} / ${esc(item.version_code)} 发布单更新</strong><span>${esc(item.updated_at)}</span></a>`).join("") : '<div class="ui-empty">暂无最近动态</div>';
    document.getElementById("overviewUpdatedAt").textContent = new Date().toLocaleString("zh-CN");
    await loadOverviewManifestStatus();
  }

  async function loadEnvironmentDetail() {
    const envKey = page.dataset.envKey;
    const data = await api(`/api/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(envKey)}`);
    const summary = data.summary || {};
    document.getElementById("envDetailTitle").textContent = data.env_label || envKey;
    document.getElementById("envDetailSummary").innerHTML = [
      ["交付线", `${summary.configured_line_count || 0} / ${summary.delivery_line_count || 0}`],
      ["未配置", summary.unconfigured_line_count || 0],
      ["阻断发布单", summary.failed_count || 0],
      ["进行中", summary.processing_count || 0],
      ["待审批", summary.pending_approval_count || 0],
    ].map(([label, value]) => `<article class="kpi-card"><div><span>${label}</span><strong>${value}</strong></div></article>`).join("");
    const lines = data.delivery_lines || [];
    document.getElementById("deliveryMatrix").innerHTML = renderDeliveryMatrixHtml(lines, envKey);
    const orders = data.release_orders || [];
    document.getElementById("envOrders").innerHTML = orders.length
      ? orders.slice(0, 6).map((item) => `<a class="activity-row" href="/admin/projects/${projectId}/release-orders/${item.release_order_id}"><span>${status(item.status)}</span><strong>${esc(item.version_name)} / ${esc(item.version_code)}</strong><span>${esc(item.updated_at)}</span></a>`).join("")
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
    if (location.hash === "#delivery-scope") openDeliveryScopeDialog();
  }

  const renderOrderTable = (items) => {
    const host = document.getElementById("releaseOrderList");
    host.innerHTML = `<div class="order-table-head"><span>发布单 / 版本</span><span>目标</span><span>状态</span><span>拓扑 / Runtime</span><span>更新时间</span><span>操作</span></div>` + (items.length ? items.map(item=>{const context=`?env_key=${encodeURIComponent(item.env_key)}&channel_id=${encodeURIComponent(item.channel_id)}&platform=${encodeURIComponent(item.platform)}&version_name=${encodeURIComponent(item.version_name)}&version_code=${encodeURIComponent(item.version_code)}&release_order_id=${encodeURIComponent(item.release_order_id)}`;return `<div class="order-table-row"><div><strong>${esc(item.release_order_id)}</strong><small>${esc(item.version_name)} / ${esc(item.version_code)}</small></div><div>${esc(envLabels[item.env_key])}<small>${esc(item.channel_name)} / ${esc(item.platform)}</small></div><div>${status(item.status)}</div><div>${esc(item.topology_id || "待解析")}<small>${esc(item.runtime_run_id || "未运行")}</small></div><div>${esc(item.updated_at)}</div><div class="row-actions"><a class="ui-secondary" href="/admin/projects/${projectId}/release-orders/${item.release_order_id}${context}">详情</a>${["draft","artifacts_ready","precheck_failed"].includes(item.status)?`<a class="ui-secondary" href="/admin/projects/${projectId}/release-orders/${item.release_order_id}/edit${context}">编辑</a>`:""}</div></div>`;}).join("") : '<div class="ui-empty">当前筛选条件下暂无发布单</div>');
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
      document.getElementById("orderSummary").innerHTML=summary.map(([label,value])=>`<article class="kpi-card"><div><span>${label}</span><strong>${value}</strong></div></article>`).join("");
    };
    page.querySelectorAll("[data-filter]").forEach(x=>x.addEventListener("change",load));page.querySelector("[data-order-search]").addEventListener("input",load);page.querySelector("[data-refresh-orders]").addEventListener("click",load);load();
  }

  async function setupOrderForm() {
    const form=document.getElementById("releaseOrderForm"), orderId=page.dataset.orderId;
    const search=new URLSearchParams(location.search);
    const envFromUrl=search.get("env_key")||"";
    const options=await api(`/api/projects/${projectId}/context-options${envFromUrl?`?env_key=${encodeURIComponent(envFromUrl)}`:""}`);
    try {
      const listResponse=await fetch(`/admin/projects/${projectId}/versions/list`,{credentials:"same-origin"});
      const listPayload=await listResponse.json();
      if(listResponse.ok&&Array.isArray(listPayload.versions)){
        const enriched=new Map(listPayload.versions.map((item)=>[String(item.id),item]));
        options.versions=(options.versions||[]).map((item)=>({...item,...(enriched.get(String(item.id))||{})}));
      }
    }catch(_error){/* keep context-options versions */}
    const fill=(select,items,key,label)=>{select.innerHTML=items.map(item=>`<option value="${esc(item[key])}">${esc(item[label])}</option>`).join("");};
    const valueText=value=>typeof value==="object"&&value!==null?JSON.stringify(value,null,2):String(value??"");
    fill(form.env_key,options.environments,"env_key","label");
    fill(form.channel_id,options.channels,"channel_id","channel_name");
    fill(form.platform,options.platforms,"value","label");
    const topologySelect = form.target_topology_id;
    if (topologySelect) {
      try {
        const topoResponse = await fetch(`/api/projects/${encodeURIComponent(projectId)}/topologies`, { credentials: "same-origin" });
        const topoData = await topoResponse.json();
        const topologies = topoData.data?.topologies || [];
        topologySelect.innerHTML = '<option value="">按绑定规则自动解析</option>' + topologies.map((item) => `<option value="${esc(item.topology_id)}">${esc(item.name || item.topology_id)}</option>`).join("");
      } catch (_error) {
        topologySelect.innerHTML = '<option value="">按绑定规则自动解析</option>';
      }
    }

    const selectedVersion=()=>options.versions.find(item=>String(item.id)===String(form.version_id.value))||{};
    let formContext={required_fields:["reason","owner"],release_policy:{form_depth:"minimal"},delivery_readiness:{ready:false,pipeline_ready:false,percent:0},build_config_href:""};
    const loadFormContext=async(version)=>{
      const params=new URLSearchParams();
      if(version?.id)params.set("version_id",version.id);
      if(form.env_key.value)params.set("env_key",form.env_key.value);
      if(form.channel_id.value)params.set("channel_id",form.channel_id.value);
      if(form.platform.value)params.set("platform",form.platform.value);
      try{
        const data=await api(`/api/projects/${projectId}/release-order-form-context?${params}`);
        formContext=data||formContext;
        applyReleaseDefaults(formContext.release_defaults||{});
        applyFormDepth(formContext.form_depth||formContext.release_policy?.form_depth||"standard");
      }catch(_error){/* keep defaults */}
      updateCompleteness();
      updatePipelineGate();
    };
    const applyReleaseDefaults=(defaults)=>{
      if(!defaults||typeof defaults!=="object")return;
      Object.entries(defaults).forEach(([key,value])=>{
        if(!form[key])return;
        if(!String(form[key].value||"").trim()&&String(value||"").trim())form[key].value=String(value);
      });
    };
    const applyFormDepth=(depth)=>{
      const root=page.querySelector(".order-form-app")||page;
      const minimal=depth==="minimal";
      const standard=depth==="standard";
      root.classList.toggle("order-form-minimal",minimal);
      root.classList.toggle("order-form-standard",standard&&!minimal);
      const subtitle=document.getElementById("orderFormSubtitle");
      if(subtitle){
        subtitle.textContent=minimal
          ? "开发/测试快捷发布：交付目标已锁定，填写发布原因与负责人即可保存或触发构建。"
          : standard
            ? "标准发布：补充发布说明与策略；管线在版本组模板维护。"
            : "完整发布计划：含验证、回滚与审批所需全部信息。";
      }
      page.querySelectorAll(".workflow-steps [data-form-step]").forEach((btn)=>{
        const step=btn.dataset.formStep;
        const advanced=step==="runtime"||step==="strategy"||step==="verify"||step==="rollback";
        const hideBuild=minimal&&step==="build";
        if((minimal&&advanced)||hideBuild)btn.classList.add("is-collapsed-step");
        else btn.classList.remove("is-collapsed-step");
      });
      page.querySelectorAll(".order-section-advanced").forEach((section)=>{
        if(minimal)section.classList.add("is-collapsed-section");
        else if(standard&&section.dataset.section==="rollback")section.classList.add("is-collapsed-section");
        else section.classList.remove("is-collapsed-section");
      });
      const buildSection=page.querySelector(".order-section-build");
      if(buildSection){
        if(minimal)buildSection.classList.add("is-collapsed-section");
        else buildSection.classList.remove("is-collapsed-section");
      }
      page.querySelectorAll(".order-field-optional").forEach((el)=>{
        el.classList.toggle("is-hidden-field",minimal);
      });
      const miniSummary=document.getElementById("orderMinimalBuildSummary");
      if(miniSummary)miniSummary.hidden=!minimal;
    };
    const updatePipelineGate=()=>{
      const delivery=formContext.delivery_readiness||{};
      const pipelineReady=Boolean(delivery.pipeline_ready);
      const btnBuild=document.getElementById("btnSaveBuild");
      const btnConfig=document.getElementById("btnConfigurePipeline");
      if(btnBuild)btnBuild.disabled=!pipelineReady;
      if(btnConfig){
        const href=formContext.build_config_href||"";
        if(!pipelineReady&&href){
          btnConfig.href=href;
          btnConfig.classList.remove("is-hidden");
        }else btnConfig.classList.add("is-hidden");
      }
      const gateHint=document.getElementById("orderPipelineGateHint");
      if(gateHint){
        gateHint.textContent=pipelineReady?"管线已就绪，可保存并触发构建。":"管线未就绪：请先在版本组配置 Jenkins 实例、Job 与四步管线。";
      }
    };
    const versionContextQuery=(version)=>{
      if(!version||(!version.id&&!version.version_name))return "";
      const params=new URLSearchParams();
      if(version.env_key)params.set("env_key",version.env_key);
      if(version.channel_id)params.set("channel_id",version.channel_id);
      if(version.platform)params.set("platform",version.platform);
      if(version.version_name)params.set("version_name",version.version_name);
      if(version.version_code)params.set("version_code",version.version_code);
      return params.toString();
    };
    const previewCard=(icon,label,value,detail="",href="",linkLabel="去配置",sameWindow=false)=>{
      const targetAttr=sameWindow?"":" target=\"_blank\" rel=\"noopener noreferrer\"";
      const link=href?`<a class="preview-card-link" href="${href}"${targetAttr}>${esc(linkLabel)}</a>`:"";
      return `<div class="preview-card"><img src="/static/project_ui/svg/${icon}.svg" alt=""><div><span>${esc(label)}</span><strong>${esc(value||"未配置")}</strong>${detail?`<small>${esc(detail)}</small>`:""}${link}</div></div>`;
    };
    const lockTargetFields=()=>{
      [form.env_key,form.channel_id,form.platform,form.version_id].forEach((field)=>{
        field.classList.add("is-locked");
        field.setAttribute("aria-readonly","true");
        field.tabIndex=-1;
      });
      const banner=document.getElementById("orderTargetLockBanner");
      if(banner)banner.classList.remove("is-hidden");
    };
    const applyTargetFromUrl=()=>{
      if(orderId)return false;
      const vn=search.get("version_name");
      const vc=search.get("version_code");
      const vid=search.get("version_id");
      if(!vn&&!vc&&!vid)return false;
      ["env_key","channel_id","platform"].forEach((key)=>{if(search.get(key))form[key].value=search.get(key);});
      renderVersions();
      let match=null;
      if(vid)match=options.versions.find((item)=>String(item.id)===String(vid));
      if(!match&&vn){
        match=options.versions.find((item)=>
          String(item.version_name||"")===vn
          &&(!vc||String(item.version_code||"")===vc)
          &&String(item.env_key||"")===String(form.env_key.value||"")
          &&String(item.channel_id||"")===String(form.channel_id.value||"")
          &&String(item.platform||"")===String(form.platform.value||""),
        );
      }
      if(match)form.version_id.value=match.id;
      lockTargetFields();
      renderPlanPreview();
      return Boolean(match||vn||vc||vid);
    };
    const effectivePipelineCache=new Map();
    const loadEffectivePipeline=async(vid)=>{
      if(!vid)return null;
      if(effectivePipelineCache.has(vid))return effectivePipelineCache.get(vid);
      try{
        const data=await api(`/api/projects/${projectId}/versions/${encodeURIComponent(vid)}/effective-pipeline`);
        effectivePipelineCache.set(vid,data);
        return data;
      }catch(_e){return null;}
    };
    const renderPlanPreview=()=>{
      const version=selectedVersion();
      const ctx=versionContextQuery(version);
      const pipeline=version.pipeline&&typeof version.pipeline==="object"?version.pipeline:{};
      const apkBuild=pipeline.apk_build||{};
      const configExport=pipeline.config_export||{};
      const resourceBuild=pipeline.resource_build||{};
      const hotRelease=pipeline.hot_release||{};
      const pipelineSummary=[
        configExport.enabled?"配置导出":"",
        resourceBuild.enabled?"资源打包":"",
        hotRelease.enabled?"热更发布":"",
        apkBuild.enabled?"安装包":"",
      ].filter(Boolean).join(" · ")||"管线未配置";
      const buildConfigParams=new URLSearchParams();
      buildConfigParams.set("from","release-order");
      if(orderId)buildConfigParams.set("release_order_id",orderId);
      const ctxQs=versionContextQuery(version);
      if(ctxQs)new URLSearchParams(ctxQs).forEach((v,k)=>buildConfigParams.set(k,v));
      const anchorId=version.id||search.get("version_id")||"";
      const buildConfigBase=anchorId?`/admin/projects/${projectId}/versions/${encodeURIComponent(anchorId)}/build-config`:"";
      const buildConfigHref=(section)=>{
        if(!buildConfigBase)return "";
        buildConfigParams.set("section",section);
        return `${buildConfigBase}?${buildConfigParams.toString()}`;
      };
      const workflowHref=version.id?`/admin/projects/${projectId}/versions/${encodeURIComponent(version.id)}/workflow`:"";
      const buildHistoryHref=ctx?`/admin/projects/${projectId}/build-history?${ctx}`:`/admin/projects/${projectId}/build-history`;
      const jenkinsInstance=version.jenkins_instance_id||form.jenkins_instance_id.value;
      const jenkinsJob=version.jenkins_job_id||version.jenkins_job||form.jenkins_job.value;
      const jenkinsHref=jenkinsInstance?`/admin/jenkins/edit?instance_id=${encodeURIComponent(jenkinsInstance)}`:"/admin/jenkins";
      const summaryCard=document.getElementById("orderPipelineSummaryCard");
      if(summaryCard){
        const instCell=summaryCard.querySelector("[data-field='jenkins_instance_id']");
        const jobCell=summaryCard.querySelector("[data-field='jenkins_job']");
        const pipelineCell=summaryCard.querySelector("[data-field='pipeline_summary']");
        if(instCell)instCell.textContent=jenkinsInstance||"未配置";
        if(jobCell)jobCell.textContent=jenkinsJob||"未配置";
        if(pipelineCell)pipelineCell.textContent=pipelineSummary||"管线未配置";
        const sourcePill=document.getElementById("orderPipelineSourcePill");
        if(sourcePill){
          const ready=Boolean(formContext.delivery_readiness?.pipeline_ready);
          sourcePill.textContent=ready?"版本组管线模板":"管线未配置";
          sourcePill.classList.toggle("ready",ready);
          sourcePill.classList.toggle("missing",!ready);
        }
        const cta=document.getElementById("orderGoConfigurePipelineBtn");
        if(cta){
          const href=formContext.build_config_href||buildConfigHref("jenkins");
          if(href){cta.href=href;cta.removeAttribute("hidden");}
          else cta.setAttribute("hidden","");
        }
      }
      const resourceReady=version.resource_url||version.resource_path||version.config_url||version.config_path;
      const artifactReady=version.apk_url||version.apk_path||version.apk_status==="found";
      document.getElementById("buildPlanPreview").innerHTML=[
        previewCard("nav_build_artifact","Jenkins 实例",jenkinsInstance||"未配置","维护 Jenkins 实例连接",jenkinsHref,"管理实例"),
        previewCard("nav_execute","构建任务",jenkinsJob||"未配置","Job 与四步开关在版本组管线模板维护",buildConfigHref("jenkins"),"配置版本组模板",true),
        previewCard("nav_download_center","管线摘要",pipelineSummary,"配置导出、资源打包与热更",buildConfigHref("hot_release"),"配置管线",true),
        previewCard("file_android","APK 产物",artifactReady?"已登记":"尚未登记","查看构建历史与产物",buildHistoryHref,"查看产物"),
      ].join("");
      const miniSummary=document.getElementById("orderMinimalBuildSummary");
      if(miniSummary){
        miniSummary.innerHTML=`<div class="minimal-build-banner"><strong>构建与管线（只读）</strong><p>${esc(pipelineSummary||"管线未配置")} · Jenkins ${esc(jenkinsInstance||"未配置")} / ${esc(jenkinsJob||"未配置")}</p>${formContext.build_config_href?`<a class="preview-card-link" href="${esc(formContext.build_config_href)}">配置版本组模板</a>`:""}</div>`;
      }
      if(!form.jenkins_instance_id.value&&version.jenkins_instance_id)form.jenkins_instance_id.value=version.jenkins_instance_id;
      if(!form.jenkins_job.value&&(version.jenkins_job||version.jenkins_job_id))form.jenkins_job.value=version.jenkins_job||version.jenkins_job_id;
      loadFormContext(version);
      if(version.id){
        loadEffectivePipeline(version.id).then((data)=>{
          if(!data)return;
          const card=document.getElementById("orderPipelineSummaryCard");
          if(!card)return;
          const eff=data.effective_pipeline||{};
          const summary=[
            (eff.config_export||{}).enabled?"配置导出":"",
            (eff.resource_build||{}).enabled?"资源打包":"",
            (eff.hot_release||{}).enabled?"热更发布":"",
            (eff.apk_build||{}).enabled?"安装包":"",
          ].filter(Boolean).join(" · ")||"管线未配置";
          const j=data.jenkins||{};
          const pillEl=document.getElementById("orderPipelineSourcePill");
          if(pillEl){
            const ready=Boolean(data.readiness?.ready);
            pillEl.textContent=ready?"版本组管线模板":"管线未配置";
            pillEl.classList.toggle("ready",ready);
            pillEl.classList.toggle("missing",!ready);
          }
          const instCell=card.querySelector("[data-field='jenkins_instance_id']");
          const jobCell=card.querySelector("[data-field='jenkins_job']");
          const pipelineCell=card.querySelector("[data-field='pipeline_summary']");
          if(instCell)instCell.textContent=j.jenkins_instance_id||"未配置";
          if(jobCell)jobCell.textContent=j.jenkins_job_id||"未配置";
          if(pipelineCell)pipelineCell.textContent=summary;
          if(data.build_config_href){
            const cta=document.getElementById("orderGoConfigurePipelineBtn");
            if(cta){cta.href=data.build_config_href;cta.removeAttribute("hidden");}
          }
          const instInput=form.jenkins_instance_id;
          const jobInput=form.jenkins_job;
          if(instInput&&j.jenkins_instance_id)instInput.value=j.jenkins_instance_id;
          if(jobInput&&j.jenkins_job_id)jobInput.value=j.jenkins_job_id;
        }).catch(()=>{});
      }
    };
    const renderVersions=()=>{
      const current=form.version_id.value;
      const items=options.versions.filter(x=>x.env_key===form.env_key.value&&x.channel_id===form.channel_id.value&&x.platform===form.platform.value);
      form.version_id.innerHTML=items.length?items.map(x=>`<option value="${esc(x.id)}">${esc(x.version_name)} / ${esc(x.version_code)}</option>`).join(""):'<option value="">当前目标暂无可用 VersionCode</option>';
      if(items.some(x=>String(x.id)===String(current)))form.version_id.value=current;
      renderPlanPreview();
    };
    const updateCompleteness=()=>{
      const required=formContext.required_fields||["env_key","channel_id","platform","version_id","reason","owner"];
      const planComplete=required.filter(key=>form[key]&&String(form[key].value||"").trim()).length;
      const planPercent=required.length?Math.round(planComplete/required.length*100):0;
      document.getElementById("planCompleteness").textContent=`${planPercent}%`;
      document.getElementById("planCompletenessBar").style.width=`${planPercent}%`;
      document.getElementById("planCompletenessHint").textContent=planPercent===100?"计划信息完整，可保存并进入构建。":`还有 ${required.length-planComplete} 项计划信息待补充。`;
      const delivery=formContext.delivery_readiness||{};
      const delPercent=Number(delivery.percent||0);
      const delEl=document.getElementById("deliveryReadiness");
      const delBar=document.getElementById("deliveryReadinessBar");
      const delHint=document.getElementById("deliveryReadinessHint");
      if(delEl)delEl.textContent=`${delPercent}%`;
      if(delBar)delBar.style.width=`${delPercent}%`;
      if(delHint){
        const checks=delivery.checks||{};
        const missing=[];
        if(!checks.jenkins_instance)missing.push("Jenkins 实例");
        if(!checks.jenkins_job)missing.push("Jenkins Job");
        if(!checks.pipeline)missing.push("管线配置");
        if(!checks.topology)missing.push("拓扑绑定");
        if(!checks.artifacts)missing.push("产物登记");
        delHint.textContent=delivery.pipeline_ready?"交付链路基本就绪。":(missing.length?`待完成：${missing.join("、")}`:"选择 VersionCode 后评估就绪度。");
      }
      updatePipelineGate();
    };
    [form.env_key,form.channel_id,form.platform].forEach(x=>x.addEventListener("change",()=>{renderVersions();loadFormContext(selectedVersion());}));
    form.version_id.addEventListener("change",()=>{renderPlanPreview();loadFormContext(selectedVersion());});
    form.addEventListener("input",updateCompleteness);
    page.querySelectorAll("[data-form-step]").forEach(button=>button.addEventListener("click",()=>{
      page.querySelectorAll("[data-form-step]").forEach(item=>item.classList.toggle("active",item===button));
      page.querySelector(`[data-section="${button.dataset.formStep}"]`)?.scrollIntoView({behavior:"smooth",block:"start"});
    }));

    if(orderId){
      const order=await api(`/api/projects/${projectId}/release-orders/${orderId}`);
      ["env_key","channel_id","platform"].forEach(key=>form[key].value=order[key]);
      renderVersions();
      form.version_id.value=order.version_id;
      form.reason.value=order.reason||"";
      Object.entries(order.payload||{}).forEach(([key,value])=>{if(form[key])form[key].value=valueText(value);});
      if(form.target_topology_id&&order.payload?.target_topology_id)form.target_topology_id.value=order.payload.target_topology_id;
      document.getElementById("resolvedTopology").textContent=order.topology_id||"尚未解析";
      document.getElementById("resolvedRuntime").textContent=order.runtime_run_id||"预检后确认";
      lockTargetFields();
      renderPlanPreview();
      loadFormContext(selectedVersion());
    }else if(!applyTargetFromUrl()){
      ["env_key","channel_id","platform"].forEach((key)=>{if(search.get(key))form[key].value=search.get(key);});
      renderVersions();
      loadFormContext(selectedVersion());
    }
    updateCompleteness();
    const payload=()=>{
      const data=Object.fromEntries(new FormData(form).entries());
      ["env_key","channel_id","platform","version_id"].forEach((key)=>{
        if(form[key]?.classList.contains("is-locked"))data[key]=form[key].value;
      });
      return data;
    };
    const save=async(buildAfter=false)=>{
      try{
        if(buildAfter&&!formContext.delivery_readiness?.pipeline_ready){
          toast("管线未就绪，请先配置版本组管线模板","error");
          return;
        }
        if(!form.reportValidity())return;
        page.querySelectorAll("[data-save-order],[data-save-build]").forEach(button=>button.disabled=true);
        let order;
        if(orderId)order=await api(`/api/projects/${projectId}/release-orders/${orderId}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
        else order=await api(`/api/projects/${projectId}/release-orders`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
        document.getElementById("orderSaveStatus").textContent="草稿已保存";
        toast("发布单计划已保存");
        const context=`?env_key=${encodeURIComponent(order.env_key)}&channel_id=${encodeURIComponent(order.channel_id)}&platform=${encodeURIComponent(order.platform)}&version_name=${encodeURIComponent(order.version_name)}&version_code=${encodeURIComponent(order.version_code)}&release_order_id=${encodeURIComponent(order.release_order_id)}`;
        if(buildAfter){
          await api(`/api/projects/${projectId}/release-orders/${order.release_order_id}/build`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
          location.href=`/admin/projects/${projectId}/release-orders/${order.release_order_id}${context}`;
        }else if(!orderId)location.href=`/admin/projects/${projectId}/release-orders/${order.release_order_id}/edit${context}`;
      }catch(error){toast(error.message,"error");}
      finally{page.querySelectorAll("[data-save-order],[data-save-build]").forEach(button=>button.disabled=false);}
    };
    page.querySelector("[data-save-order]").addEventListener("click",()=>save(false));
    page.querySelector("[data-save-build]").addEventListener("click",()=>save(true));
  }

  async function loadOrderDetail(){
    const orderId=page.dataset.orderId,item=await api(`/api/projects/${projectId}/release-orders/${orderId}`);
    document.getElementById("orderTitle").innerHTML=`发布单详情 ${status(item.status)}`;document.getElementById("orderSubtitle").textContent=`发布单编号：${item.release_order_id}`;
    const actions=[["edit","编辑计划"],["build","触发构建"],["precheck","执行预检"],["approve","审批通过"],["publish","执行发布"],["verify","执行验证"],["rollback","回滚"],["cancel","取消发布单"]];
    const allowed={edit:["draft","artifacts_ready","precheck_failed"].includes(item.status),build:!["published","verified","rolled_back","cancelled"].includes(item.status),precheck:["draft","artifacts_ready","precheck_failed","ready"].includes(item.status),approve:item.status==="awaiting_approval",publish:["ready","approved"].includes(item.status),verify:["published","verify_failed"].includes(item.status),rollback:Boolean(item.bundle_id&&item.active_bundle_id&&item.bundle_id!==item.active_bundle_id),cancel:!["published","verified","rolled_back","cancelled"].includes(item.status)};
    document.getElementById("orderActions").innerHTML=actions.filter(([key])=>allowed[key]).map(([key,label])=>key==="edit"?`<a class="ui-secondary" href="/admin/projects/${projectId}/release-orders/${orderId}/edit${currentContext()}">${label}</a>`:`<button class="${["publish","verify"].includes(key)?"ui-primary":"ui-secondary"}" data-action="${key}">${label}</button>`).join("");
    document.getElementById("orderMeta").innerHTML=[["目标环境",envLabels[item.env_key]],["版本",`${item.version_name} / ${item.version_code}`],["渠道与平台",`${item.channel_name} / ${item.platform}`],["负责人",item.created_by],["总体状态",statusLabels[item.status]]].map(([label,value])=>`<div class="meta-item"><span>${label}</span><strong>${esc(value)}</strong></div>`).join("");
    const stages=["计划摘要","构建与产物","拓扑与运行态","预检结果","审批","发布执行","验证结果","Bundle 与回滚"];const index={draft:0,building:1,artifacts_ready:1,prechecking:3,precheck_failed:3,ready:3,awaiting_approval:4,approved:4,publishing:5,published:5,verifying:6,verified:7,verify_failed:6,rolled_back:7,cancelled:0}[item.status]??0;document.getElementById("orderSteps").innerHTML=stages.map((label,i)=>`<div class="delivery-step ${i<=index?"active":""} ${i===index&&item.status.includes("failed")?"failed":""}"><b>${i+1}</b>${label}</div>`).join("");
    const check=item.latest_precheck||{},payload=check.payload||{};const artifactProblems=(item.artifacts||[]).filter(x=>["missing","unreachable","invalid"].includes(String(x.status||"").toLowerCase())).map(x=>`${x.artifact_type} ${artifactStatusLabels[x.status]||x.status}`);const problems=[...artifactProblems,...(payload.missing_client_fields||[]),...(payload.missing_profile_fields||[]),...(payload.missing_artifact_fields||[])];payload.runtime_error&&problems.push(payload.runtime_error);document.getElementById("orderAlerts").innerHTML=problems.length?`<div class="alert-card danger"><strong>阻断问题（${problems.length}）</strong><p>${esc(problems.join("；"))}</p></div>`:'<div class="alert-card warning"><strong>下一步建议</strong><p>按发布单当前状态执行下一项交付动作。</p></div>';
    document.getElementById("orderArtifacts").innerHTML=(item.artifacts||[]).map(x=>row(artifactTypeLabels[x.artifact_type]||x.artifact_type,x.artifact_url||x.artifact_path,artifactStatusLabels[x.status]||x.status)).join("")||'<div class="ui-empty">暂无产物</div>';
    document.getElementById("orderRuntime").innerHTML=row("拓扑",item.topology_id,bindingSourceLabels[item.topology_binding_source]||item.topology_binding_source)+row("Runtime",item.runtime_run_id,item.runtime_run_id?"运行中":"未运行");
    document.getElementById("orderPrecheck").innerHTML=check.created_at?row(check.ok?"预检通过":"预检阻断",check.created_at,check.ok?"通过":"失败"):'<div class="ui-empty">尚未执行预检</div>';
    document.getElementById("orderApprovals").innerHTML=(item.approvals||[]).map(x=>row(x.status,x.approved_by||x.requested_by,x.note)).join("")||'<div class="ui-empty">暂无审批记录</div>';
    document.getElementById("orderExecution").innerHTML=row("发布时间",item.published_at,statusLabels[item.status]||item.status)+row("验证状态",statusLabels[item.status],statusLabels[item.status]||item.status);
    document.getElementById("orderBundle").innerHTML=row("Bundle",item.bundle_id,item.bundle_id?"已生成":"未生成")+row("Active Bundle",item.active_bundle_id,item.bundle_id===item.active_bundle_id&&item.bundle_id?"当前生效":"");
    document.getElementById("orderEvents").innerHTML=(item.events||[]).map(x=>`<div class="timeline-row"><strong>${esc(x.event_type)} · ${esc(statusLabels[x.to_status]||x.to_status||"")}</strong><span>${esc(x.actor)} · ${esc(x.created_at)}</span></div>`).join("");
    const dialog=document.getElementById("orderActionDialog"),reason=document.getElementById("orderActionReason");let pendingAction="";
    const closeDialog=()=>{pendingAction="";reason.value="";dialog.classList.add("is-hidden");dialog.setAttribute("aria-hidden","true");};
    const executeAction=async(action,operationReason="")=>{try{await api(`/api/projects/${projectId}/release-orders/${orderId}/${action}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reason:operationReason})});toast("操作已提交");loadOrderDetail();}catch(error){toast(error.message,"error");}};
    document.getElementById("orderActionDialogClose").onclick=closeDialog;document.getElementById("orderActionDialogCancel").onclick=closeDialog;
    document.getElementById("orderActionDialogConfirm").onclick=async()=>{const action=pendingAction,operationReason=reason.value.trim();if(["publish","rollback","cancel"].includes(action)&&!operationReason){toast("请填写操作原因","error");return;}closeDialog();await executeAction(action,operationReason);};
    document.querySelectorAll("[data-action]").forEach(button=>button.addEventListener("click",async()=>{const action=button.dataset.action;if(["build","precheck","verify"].includes(action)){await executeAction(action);return;}pendingAction=action;document.getElementById("orderActionDialogTitle").textContent=`确认${button.textContent}`;document.getElementById("orderActionDialogHint").textContent=["publish","rollback","cancel"].includes(action)?"该操作会改变发布状态，请填写原因后确认。":"请确认本次操作影响范围。";dialog.classList.remove("is-hidden");dialog.setAttribute("aria-hidden","false");}));
  }
  const type=page.dataset.deliveryPage;
  if(type==="overview"){
    initOverviewTabs();
    bindOverviewFilters();
    bindDeliveryScopeDialog();
    bindProjectEnvAdd();
    loadOverview().catch(error=>toast(error.message,"error"));
    page.querySelector("[data-refresh-overview]")?.addEventListener("click",()=>loadOverview().catch(error=>toast(error.message,"error")));
  }
  if(type==="environment"){loadEnvironmentDetail().catch(error=>toast(error.message,"error"));page.querySelector("[data-refresh-env]")?.addEventListener("click",loadEnvironmentDetail);}
  if(type==="orders")setupOrders().catch(error=>toast(error.message,"error"));
  if(type==="order-form")setupOrderForm().catch(error=>toast(error.message,"error"));
  if(type==="order-detail")loadOrderDetail().catch(error=>toast(error.message,"error"));
})();
