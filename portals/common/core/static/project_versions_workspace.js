(() => {
  const root = document.querySelector(".version-workspace");
  if (!root) return;
  const projectId = root.dataset.projectId;
  const canEdit = root.dataset.canEdit === "true";
  const envKey = root.dataset.envKey;
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const envLabels = { development: "开发环境", testing: "测试环境", staging: "预发环境", production: "生产环境" };
  const statusLabels = { active: "有效", testing: "测试中", draft: "草稿", disabled: "失效", archived: "归档" };
  const groupModeLabels = { general: "通用", commercial: "商业化" };
  const urlParams = new URLSearchParams(location.search);
  const lockChannelId = urlParams.get("channel_id") || root.dataset.channelFilter || "";
  const lockPlatform = urlParams.get("platform") || root.dataset.platformFilter || "";
  const lockEnvKey = urlParams.get("env_key") || root.dataset.envKey || envKey || "";
  const lockChannelScoped = Boolean(lockChannelId);
  const lockDeliveryLine = urlParams.get("action") === "create_vc" && lockChannelId && lockPlatform;
  const envScoped = true;
  const createVcAction = urlParams.get("action") === "create_vc";
  let rows = [];
  let versionGroups = [];
  let channels = [];
  let platforms = [];
  let filterVersionName = urlParams.get("version_name") || "";
  let activePlatformKey = lockPlatform || "";
  const collapsedGroups = new Set();
  let listPage = 1;
  const listPageSize = 20;
  let releaseOrderByVersion = new Map();
  let deliveryActionsByVersion = new Map();
  const scopeApi = window.DeliveryScope || {};
  const buildScopeQuery = (scope = {}, extra = {}) => (scopeApi.buildQuery ? scopeApi.buildQuery(scope, extra) : "");
  const scopeHref = (path, scope = {}, extra = {}) => (scopeApi.href ? scopeApi.href(path, scope, extra) : path);
  const startReleaseHref = (row) => scopeHref(`/admin/projects/${projectId}/release-orders/start`, {
    env_key: normalizedEnv(row),
    channel_id: channelIdOf(row),
    platform: row.platform || "",
    version_id: row.id,
    intent: "release",
  });
  const continueReleaseHref = (row) => scopeHref(`/admin/projects/${projectId}/release-orders/start`, {
    env_key: normalizedEnv(row),
    channel_id: channelIdOf(row),
    platform: row.platform || "",
    version_id: row.id,
    intent: "release",
  });
  const releaseOrderDetailHref = (row, order) => {
    if (!order?.release_order_id) return continueReleaseHref(row);
    return scopeHref(`/admin/projects/${projectId}/release-orders/${order.release_order_id}`, {
      env_key: normalizedEnv(row),
      channel_id: channelIdOf(row),
      platform: row.platform || "",
      version_id: row.id,
      version_name: row.version_name || "",
      version_code: row.version_code || "",
      release_order_id: order.release_order_id,
    });
  };
  const triggerBuildHref = (row) => scopeHref(`/admin/projects/${projectId}/release-orders/start`, {
    env_key: normalizedEnv(row),
    channel_id: channelIdOf(row),
    platform: row.platform || "",
    version_id: row.id,
    intent: "build",
  });
  const isMinimalEnv = (row) => ["development", "testing"].includes(normalizedEnv(row));
  const releaseOrderForRow = (row) => releaseOrderByVersion.get(String(row.id || "")) || null;
  const isBuildInProgress = (row) => releaseOrderForRow(row)?.status === "building";
  const pipelineReadyOf = (row, group) => Boolean(group?.pipeline_ready || row.pipeline_ready || row.jenkins_job_id || (row.pipeline || {}).jenkins_job_id);
  const RELEASE_CONTINUE_STATUSES = new Set(["artifacts_ready", "precheck_failed", "ready", "awaiting_approval", "approved", "published"]);
  const releaseStatusLabels = { draft: "草稿", building: "构建中", artifacts_ready: "产物就绪", precheck_failed: "预检失败", ready: "待发布", awaiting_approval: "待审批", approved: "已审批", published: "已发布" };

  const csrfHeaders = () => {
    const token = document.querySelector('meta[name="csrf-token"]');
    return token && token.content ? { "X-CSRFToken": token.content } : {};
  };
  const request = async (url, options = {}) => {
    const method = String(options.method || "GET").toUpperCase();
    const headers = { ...(options.headers || {}), ...(["POST", "PUT", "PATCH", "DELETE"].includes(method) ? csrfHeaders() : {}) };
    const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
    const text = await response.text();
    let data = null;
    try {
      data = JSON.parse(text);
    } catch (_error) {
      if (text.trim().startsWith("<")) throw new Error("会话已过期，请重新登录后重试");
      throw new Error(response.status === 400 && /CSRF/i.test(text) ? "安全校验失败，请刷新页面后重试" : `请求失败 (${response.status})`);
    }
    if (!response.ok || data.error || data.ok === false) throw new Error(typeof data.error === "string" ? data.error : data.error?.message || "请求失败");
    return data;
  };
  const toast = (message, type = "success") => {
    let host = document.querySelector(".toast-stack");
    if (!host) {
      host = document.createElement("div");
      host.className = "toast-stack";
      document.body.append(host);
    }
    const node = document.createElement("div");
    node.className = `toast ${type}`;
    node.textContent = message;
    host.append(node);
    setTimeout(() => node.remove(), 3500);
  };
  const normalizedEnv = (row) => row.env_key || ({ dev: "development", test: "testing", staging: "staging", production: "production" }[row.stage] || row.stage || "development");
  const channelIdOf = (row) => String(row.channel_id || row.channel || "").trim();
  const deliveryKey = (row) => `${normalizedEnv(row)}:${channelIdOf(row)}:${row.platform || "android"}`;
  const channelNameOf = (channelId) => {
    const hit = channels.find((item) => item.channel_id === channelId);
    return hit?.channel_name || channelId || "-";
  };
  const platformLabelOf = (platformValue) => {
    const hit = platforms.find((item) => item.value === platformValue);
    return hit?.label || platformValue || "-";
  };
  const activeEnvKey = () => lockEnvKey || document.getElementById("versionEnv")?.value || "";
  const activePlatform = () => {
    const tab = document.querySelector(".version-platform-tab.active");
    if (tab?.dataset.platform) return tab.dataset.platform;
    if (activePlatformKey) return activePlatformKey;
    return document.getElementById("versionPlatform")?.value || "";
  };
  const activeChannelId = () => {
    const filterValue = document.getElementById("versionChannel")?.value || "";
    if (lockDeliveryLine && lockChannelId) return lockChannelId;
    if (filterValue) return filterValue;
    return channels[0]?.channel_id || "";
  };
  const platformTabsVisible = () => Boolean(activeEnvKey() && platforms.length > 0);
  const scopeQueryString = () => {
    const parts = [];
    const env = activeEnvKey();
    const platform = activePlatform();
    const channel = document.getElementById("versionChannel")?.value || "";
    if (env) parts.push(`env_key=${encodeURIComponent(env)}`);
    if (platform) parts.push(`platform=${encodeURIComponent(platform)}`);
    if (channel) parts.push(`channel_id=${encodeURIComponent(channel)}`);
    if (filterVersionName) parts.push(`version_name=${encodeURIComponent(filterVersionName)}`);
    return parts.join("&");
  };
  const syncScopeUrl = () => {
    const env = activeEnvKey();
    const platform = activePlatform();
    const channel = document.getElementById("versionChannel")?.value || "";
    if (env) urlParams.set("env_key", env);
    else urlParams.delete("env_key");
    if (platform) urlParams.set("platform", platform);
    else urlParams.delete("platform");
    if (channel) urlParams.set("channel_id", channel);
    else urlParams.delete("channel_id");
    if (filterVersionName) urlParams.set("version_name", filterVersionName);
    else urlParams.delete("version_name");
    urlParams.delete("action");
    const qs = urlParams.toString();
    history.replaceState(null, "", `${location.pathname}${qs ? `?${qs}` : ""}`);
  };
  const useAllEnvChannels = () => false;
  const currentScope = () => ({
    env_key: activeEnvKey() || envKey || "production",
    channel_id: document.getElementById("versionChannel")?.value || lockChannelId || "",
    platform: activePlatform(),
  });

  const updateScopeBanner = () => {
    const title = document.getElementById("versionScopeTitle");
    const desc = document.getElementById("versionScopeDesc");
    const subtitle = document.getElementById("versionPageSubtitle");
    const env = activeEnvKey() || envKey || "production";
    const platform = activePlatform();
    const channel = lockChannelId || document.getElementById("versionChannel")?.value || "";
    const channelLabel = channel ? channelNameOf(channel) : "—";
    const parts = [envLabels[env] || env, channelLabel];
    if (platform) parts.push(platformLabelOf(platform));
    const text = parts.join(" · ");
    if (title) title.textContent = `版本代码 · ${envLabels[env] || env}`;
    if (desc) desc.textContent = `当前：${text}。环境/渠道/平台见顶部页签，表格仅展示版本组与 VC 明细。`;
    if (subtitle) subtitle.textContent = `渠道 ${channelLabel} · 按平台页签管理 VersionCode。`;
    const envLink = document.getElementById("versionScopeEnvLink");
    if (envLink) envLink.href = `/admin/projects/${projectId}/environments/${encodeURIComponent(env)}`;
  };

  const updateBuildHistoryLink = () => {
    const link = document.getElementById("versionBuildHistoryLink");
    if (!link) return;
    const scope = currentScope();
    link.href = scopeHref(`/admin/projects/${projectId}/build-history`, scope, { scoped: "1" });
  };

  const scopeSummaryText = () => {
    const env = activeEnvKey();
    const platform = activePlatform();
    if (env && platform && useAllEnvChannels()) {
      const names = channels.map((item) => item.channel_name).filter(Boolean);
      return [envLabels[env] || env, platformLabelOf(platform), names.join("、") || "-"].join(" · ");
    }
    const channel = activeChannelId();
    const parts = [];
    if (env) parts.push(envLabels[env] || env);
    if (platform) parts.push(platformLabelOf(platform));
    if (channel) parts.push(channelNameOf(channel));
    return parts.join(" · ");
  };

  const downloadLabels = (row = {}) => ({
    env: envLabels[normalizedEnv(row)] || normalizedEnv(row),
    channel: row.channel_name || row.channel_label || channelNameOf(channelIdOf(row)),
    platform: row.platform_label || row.platform || "",
  });

  const handleDownloadClick = async (versionId) => {
    const vid = String(versionId || "").trim();
    if (!vid) {
      toast("缺少 VersionCode 标识，无法下载", "error");
      return;
    }
    const row = rows.find((item) => String(item.id || "") === vid) || { id: vid };
    const adl = window.ArtifactDownload;
    if (!adl) {
      toast("下载组件未加载，请刷新页面后重试", "error");
      return;
    }
    try {
      await adl.open({
        projectId,
        versionId: vid,
        row,
        request: (url) => request(url),
        labels: downloadLabels(row),
      });
    } catch (error) {
      toast(error.message || "下载信息加载失败", "error");
    }
  };

  const platformIconOf = (platform) => {
    const p = String(platform || "").toLowerCase();
    if (p.includes("ios") || p === "iphone") return "file_ios.svg";
    if (p.includes("win")) return "file_windows.svg";
    return "file_android.svg";
  };
  const formatUpdatedAt = (row) => {
    const raw = row.updated_at || row.build_time || row.created_at || "";
    if (!raw) return "—";
    const text = String(raw);
    if (text.length >= 16) return text.slice(0, 16).replace("T", " ");
    return text;
  };
  const versionStatusHtml = (row) => {
    if (row.active_bundle_id) return '<span class="version-pill active">已发布</span>';
    if (isBuildInProgress(row)) return '<span class="version-pill building">构建中</span>';
    if (row.version_status === "disabled" || row.version_status === "archived") return '<span class="version-pill failed">构建失败</span>';
    const st = row.version_status || "draft";
    return `<span class="version-pill ${esc(st)}">${esc(row.version_status_label || statusLabels[st] || st)}</span>`;
  };
  const artifactStatusHtml = (row) => {
    if (row.apk_status === "found") return '<span class="version-artifact-status ready">完整</span>';
    if (isBuildInProgress(row)) return '<span class="version-artifact-status pending">构建中</span>';
    return '<span class="version-artifact-status missing">产物不完整</span>';
  };
  const latestBuildHtml = (row) => {
    const num = row.build_number || row.jenkins_build_number || (row.pipeline || {}).last_build_number;
    if (num) {
      const qs = new URLSearchParams({
        env_key: normalizedEnv(row),
        channel_id: channelIdOf(row),
        platform: row.platform || "",
        version_id: row.id || "",
        version_name: row.version_name || "",
        version_code: row.version_code || "",
        build_number: String(num),
        scoped: "1",
      });
      return `<a class="version-build-link" href="/admin/projects/${projectId}/build-history?${qs.toString()}">#${esc(num)}</a>`;
    }
    return '<span class="version-group-dash">—</span>';
  };
  const versionNameTagHtml = (row, group) => {
    const mode = group?.version_mode || row.version_mode || "general";
    if (mode === "commercial") return '<span class="pm-tag pm-tag--official">正式</span>';
    if (row.version_status === "draft") return '<span class="pm-tag pm-tag--draft">草稿</span>';
    if (row.version_status === "testing") return '<span class="pm-tag pm-tag--test">测试版</span>';
    return '<span class="pm-tag pm-tag--prerelease">预发布</span>';
  };

  const closeVcDrawer = () => {
    const drawer = document.getElementById("versionVcDrawer");
    if (!drawer) return;
    drawer.classList.add("is-hidden");
    drawer.setAttribute("aria-hidden", "true");
  };

  const openVcDrawer = async (row) => {
    if (!row) return;
    const drawer = document.getElementById("versionVcDrawer");
    const body = document.getElementById("versionVcDrawerBody");
    const foot = document.getElementById("versionVcDrawerFoot");
    if (!drawer || !body) return;
    document.getElementById("versionVcDrawerTitle").textContent = `${row.version_name || "-"} · VC ${row.version_code || "-"}`;
    document.getElementById("versionVcDrawerSubtitle").textContent = [
      envLabels[normalizedEnv(row)] || normalizedEnv(row),
      row.channel_name || channelNameOf(channelIdOf(row)),
      row.platform_label || row.platform || "-",
    ].join(" · ");
    body.innerHTML = `<div class="version-download-empty"><strong>正在加载详情…</strong></div>`;
    foot.innerHTML = "";
    drawer.classList.remove("is-hidden");
    drawer.setAttribute("aria-hidden", "false");
    let downloadInfo = row.apk_download || {};
    try {
      const data = await request(`/api/projects/${projectId}/versions/${encodeURIComponent(row.id)}/apk-download-info`);
      downloadInfo = { ...downloadInfo, ...data };
    } catch (_) { /* keep row data */ }
    if (!deliveryActionsByVersion.has(String(row.id || ""))) {
      await loadDeliveryActions([row.id]);
    }
    const cached = deliveryActionsByVersion.get(String(row.id || "")) || {};
    const building = isBuildInProgress(row);
    const artifactReady = row.apk_status === "found" || downloadInfo.public_download_url || downloadInfo.local_download_url;
    const buildHeadLabel = artifactReady ? "已完成" : (building ? "构建中" : "未构建");
    const statusHint = cached.status_hint || (artifactReady ? "产物已归档" : (building ? "构建进行中，请稍候刷新" : "暂无产物，可触发构建"));
    const progressWidth = artifactReady ? 100 : (building ? 55 : 0);
    const progressHtml = progressWidth > 0
      ? `<div class="current-progress" style="height:6px;background:#eef1f6;border-radius:3px;margin:10px 0"><span style="display:block;height:100%;width:${progressWidth}%;background:#1677ff;border-radius:3px"></span></div>`
      : "";
    body.innerHTML = `<div class="pm-drawer-tags">${versionNameTagHtml(row, null)}<span class="pm-tag pm-tag--muted">${esc(row.version_name || "")}</span><span class="pm-tag pm-tag--muted">${esc(normalizedEnv(row))}</span><span class="pm-tag pm-tag--muted">${esc(row.channel_name || channelNameOf(channelIdOf(row)))}</span><span class="pm-tag pm-tag--muted">${esc(row.platform_label || row.platform || "")}</span></div>
    <div class="pm-drawer-section"><h3>当前构建</h3><div class="pm-drawer-build-head"><strong>${buildHeadLabel}</strong>${latestBuildHtml(row)}</div>
    ${progressHtml}
    <p class="pm-drawer-hint">${esc(statusHint)}</p></div>
    <div class="pm-drawer-section"><h3>产物完整性</h3><div class="pm-drawer-meta"><div><span>状态</span><b>${artifactReady ? "完整" : "不完整"}</b></div><div><span>发布</span><b>${row.active_bundle_id ? "已发布" : "未发布"}</b></div></div></div>
    <div class="pm-drawer-section"><h3>关联发布单</h3><p class="pm-drawer-hint">${row.active_bundle_id ? "已有活跃 Bundle" : "构建与发版从版本代码行内操作"}</p></div>`;
    const primary = cached.primary || {};
    const drawerPrimary = primary.api_action === "quick_build" && primary.version_id
      ? `<button class="pm-btn pm-btn--primary" type="button" data-quick-build="${esc(primary.version_id)}">${esc(primary.label || "触发构建")}</button>`
      : primary.href
        ? `<a class="pm-btn pm-btn--primary" href="${esc(primary.href)}">${esc(primary.label || "继续发版")}</a>`
        : `<a class="pm-btn pm-btn--primary" href="${releaseOrderDetailHref(row, releaseOrderByVersion.get(String(row.id || "")))}">继续发版</a>`;
    foot.innerHTML = `${drawerPrimary}
      <button class="pm-btn" type="button" data-download-apk="${esc(row.id)}">查看产物</button>
      <a class="pm-btn" href="${scopeHref(`/admin/projects/${projectId}/build-history`, { env_key: normalizedEnv(row), channel_id: channelIdOf(row), platform: row.platform || "", version_id: row.id }, { scoped: "1" })}">构建历史</a>`;
  };

  const exportCsv = () => {
    const filterEnv = document.getElementById("versionEnv");
    const platformGate = activePlatform();
    const filtered = rows.filter((row) => {
      const rowChannel = channelIdOf(row);
      const envGate = lockEnvKey || filterEnv?.value || "";
      const channelGate = document.getElementById("versionChannel")?.value || "";
      const artifactGate = document.getElementById("versionArtifactStatus")?.value || "";
      const statusGate = document.getElementById("versionStatus")?.value || "";
      return (
        (!envGate || normalizedEnv(row) === envGate) &&
        (!channelGate || rowChannel === channelGate) &&
        (!platformGate || row.platform === platformGate) &&
        (!statusGate || row.version_status === statusGate) &&
        (!artifactGate || (artifactGate === "ready" ? row.apk_status === "found" : row.apk_status !== "found")) &&
        (!filterVersionName || (row.version_name || "") === filterVersionName)
      );
    });
    const header = ["version_name", "version_code", "env", "channel", "platform", "status", "apk_status"];
    const lines = [header.join(",")].concat(
      filtered.map((r) => [
        r.version_name, r.version_code, normalizedEnv(r), channelIdOf(r), r.platform, r.version_status, r.apk_status,
      ].map((c) => `"${String(c || "").replace(/"/g, '""')}"`).join(",")),
    );
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `versions-${projectId}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const openDownloadPicker = (candidates = []) => {
    const adl = window.ArtifactDownload;
    if (!adl) {
      toast("下载组件未加载，请刷新页面后重试", "error");
      return;
    }
    adl.openPicker({
      items: candidates,
      projectId,
      request: (url) => request(url),
      formatPickLabel: (row) => ({
        main: `VC ${row.version_code || "-"}`,
        sub: `${row.version_name || ""}${formatUpdatedAt(row) !== "—" ? ` · ${formatUpdatedAt(row)}` : ""}`,
      }),
      labels: downloadLabels(candidates[0] || {}),
    }).catch((error) => toast(error.message || "暂无可下载的产物", "error"));
  };

  const buildConfigHrefForRow = (row) => {
    const params = new URLSearchParams();
    params.set("from", "version-group");
    params.set("version_name", row.version_name || "");
    if (normalizedEnv(row)) params.set("env_key", normalizedEnv(row));
    if (row.platform) params.set("platform", row.platform);
    return `/admin/projects/${projectId}/versions/${encodeURIComponent(row.id || "")}/build-config?${params}`;
  };

  const resolveLocalRowActions = (row, group) => {
    const order = releaseOrderByVersion.get(String(row.id || ""));
    const orderStatus = order?.status || "";
    const artifactOk = row.apk_status === "found";
    const pipelineOk = pipelineReadyOf(row, group);
    const buildHistoryHref = scopeHref(
      `/admin/projects/${projectId}/build-history`,
      {
        env_key: normalizedEnv(row),
        channel_id: channelIdOf(row),
        platform: row.platform || "",
        version_id: row.id,
      },
      { scoped: "1" },
    );
    if (orderStatus === "building") {
      return {
        primary: { action: "view_build", label: "查看构建", href: releaseOrderDetailHref(row, order) },
        secondary: [{ action: "build_history", label: "构建日志", href: buildHistoryHref }],
      };
    }
    if (artifactOk || RELEASE_CONTINUE_STATUSES.has(orderStatus)) {
      return {
        primary: { action: "continue_release", label: "继续发版", href: releaseOrderDetailHref(row, order) },
        secondary: [{ action: "build_history", label: "构建产物", href: buildHistoryHref }],
      };
    }
    if (!pipelineOk) {
      return {
        primary: { action: "configure_pipeline", label: "配置管线", href: buildConfigHrefForRow(row) },
        secondary: [],
      };
    }
    if (isMinimalEnv(row)) {
      return {
        primary: { action: "trigger_build", label: "触发构建", api_action: "quick_build", version_id: row.id },
        secondary: [{ action: "build_history", label: "构建产物", href: buildHistoryHref }],
      };
    }
    return {
      primary: { action: "edit_plan", label: "填写计划", href: triggerBuildHref(row) },
      secondary: [{ action: "build_history", label: "构建产物", href: buildHistoryHref }],
    };
  };

  const rowActionsHtml = (row, group) => {
    const scope = {
      env_key: normalizedEnv(row),
      channel_id: channelIdOf(row),
      platform: row.platform || "",
      version_id: row.id,
      version_name: row.version_name || "",
      version_code: row.version_code || "",
      release_order_id: releaseOrderByVersion.get(String(row.id || ""))?.release_order_id || "",
      artifact_ready: row.apk_status === "found",
    };
    const cached = deliveryActionsByVersion.get(String(row.id || ""));
    const actionsPayload = cached && cached.primary
      ? { primary: cached.primary, secondary: cached.secondary || [] }
      : resolveLocalRowActions(row, group);
    const links = (cached && cached.links) || {};
    if (scopeApi.renderRowActions) {
      return scopeApi.renderRowActions(actionsPayload, links, scope, projectId);
    }
    const order = releaseOrderByVersion.get(String(row.id || ""));
    return `<div class="version-row-actions"><a class="version-action-link primary" href="${releaseOrderDetailHref(row, order)}">继续发版</a></div>`;
  };

  const loadDeliveryActions = async (versionIds = []) => {
    const ids = [...new Set((versionIds || []).map((id) => String(id || "").trim()).filter(Boolean))];
    await Promise.all(ids.map(async (vid) => {
      if (deliveryActionsByVersion.has(vid)) return;
      try {
        const data = await request(`/api/projects/${projectId}/versions/${encodeURIComponent(vid)}/delivery-actions`);
        deliveryActionsByVersion.set(vid, data.data || data);
      } catch (_error) {
        deliveryActionsByVersion.set(vid, null);
      }
    }));
  };

  const TABLE_COLS = "pm-table-cols-7";

  const readinessBarHtml = (row, group) => {
    const pipelineOk = pipelineReadyOf(row, group);
    const artifactOk = row.apk_status === "found";
    const order = releaseOrderByVersion.get(String(row.id || ""));
    const releaseText = row.active_bundle_id ? "已发布" : (order ? (releaseStatusLabels[order.status] || order.status) : "无发布单");
    return `<div class="version-readiness-bar"><span class="${pipelineOk ? "ok" : "no"}">管线${pipelineOk ? "✓" : "✗"}</span><span class="${artifactOk ? "ok" : "no"}">产物${artifactOk ? "✓" : "✗"}</span><span class="muted">${esc(releaseText)}</span></div>`;
  };

  const childRowHtml = (row, group) => `<div class="version-row version-row-child ${TABLE_COLS}" data-version-id="${esc(row.id || "")}" data-open-vc="${esc(row.id || "")}">
      <div class="version-vc-cell"><span class="version-vc-code">${esc(row.version_code || "-")}</span><span class="version-vc-label">${esc(row.version_name || "")}</span></div>
      <div>${versionNameTagHtml(row, group)}</div>
      <div class="version-status-stack">${versionStatusHtml(row)}${artifactStatusHtml(row)}</div>
      <div>${readinessBarHtml(row, group)}</div>
      <div>${latestBuildHtml(row)}</div>
      <div class="version-updated-at">${esc(formatUpdatedAt(row))}</div>
      ${rowActionsHtml(row, group)}
    </div>`;

  const groupRowHtml = (group, children) => {
    const groupName = group.version_name;
    const collapsed = collapsedGroups.has(groupName);
    const buildConfigParams = new URLSearchParams();
    buildConfigParams.set("from", "version-group");
    buildConfigParams.set("version_name", groupName);
    if (group.env_key) buildConfigParams.set("env_key", group.env_key);
    if (group.platform) buildConfigParams.set("platform", group.platform);
    const anchorId = children[0]?.id || group.anchor_version_id || "";
    const buildConfigHref = anchorId
      ? `/admin/projects/${projectId}/versions/${encodeURIComponent(anchorId)}/build-config?${buildConfigParams}`
      : `/admin/projects/${projectId}/version-groups/build-config?${buildConfigParams}`;
    const pipelineBadge = group.pipeline_ready
      ? `<span class="version-pill pipeline-ready">管线就绪</span>`
      : `<span class="version-pill pipeline-missing">管线未配置</span>`;
    const downloadable = children.filter((row) => row.apk_status === "found");
    const groupDownloadBtn = downloadable.length === 1
      ? `<button class="version-btn neutral compact" type="button" data-download-apk="${esc(downloadable[0].id || "")}">下载</button>`
      : downloadable.length > 1
        ? `<button class="version-btn neutral compact" type="button" data-download-pick="${esc(groupName)}">下载</button>`
        : "";
    const groupActions = canEdit
      ? `${groupDownloadBtn}<a class="version-btn build compact" href="${buildConfigHref}">配置管线</a>
         <button class="version-btn neutral compact" type="button" data-add-vc="${esc(groupName)}">添加 VC</button>
         <button class="version-btn neutral compact" type="button" data-edit-group="${esc(groupName)}">编辑</button>
         <button class="version-btn warn compact" type="button" data-delete-group="${esc(groupName)}">删除</button>`
      : `${groupDownloadBtn}<a class="version-btn build compact" href="${buildConfigHref}">查看管线</a>`;
    const emptyHint = children.length
      ? ""
      : `<div class="version-empty-inline ${TABLE_COLS}">尚无 VersionCode · <button type="button" class="version-link-btn" data-add-vc="${esc(groupName)}">立即添加</button></div>`;
    return `<section class="version-group-card${collapsed ? " is-collapsed" : ""}" data-group="${esc(groupName)}">
      <div class="version-row version-row-group ${TABLE_COLS}">
        <div class="version-group-title">
          <button class="version-group-toggle" type="button" data-toggle-group="${esc(groupName)}" aria-expanded="${collapsed ? "false" : "true"}">
            <img src="/static/project_ui/svg/action_next.svg" alt="">
          </button>
          <div class="version-group-head">
            <div class="version-group-name-line"><strong>${esc(groupName)}</strong><span class="pm-tag pm-tag--muted">版本组</span></div>
          </div>
        </div>
        <div>${versionNameTagHtml(children[0] || {}, group)}</div>
        <div><span class="version-pill ${esc(group.status || "active")}">${esc(statusLabels[group.status] || group.status || "有效")}</span></div>
        <div>${pipelineBadge}</div>
        <div class="version-group-dash">—</div>
        <div class="version-group-dash">—</div>
        <div class="version-row-actions version-group-actions">${groupActions}</div>
      </div>
      <div class="version-group-children">${emptyHint}${children.map((child) => childRowHtml(child, group)).join("")}</div>
    </section>`;
  };

  const render = () => {
    const query = (document.getElementById("versionSearch")?.value || "").trim().toLowerCase();
    const filterEnv = document.getElementById("versionEnv");
    const filterChannel = document.getElementById("versionChannel");
    const filterStatus = document.getElementById("versionStatus");
    const artifactFilter = document.getElementById("versionArtifactStatus");
    const platformGate = activePlatform();
    const filtered = rows.filter((row) => {
      const rowChannel = channelIdOf(row);
      const envGate = lockEnvKey || filterEnv?.value || "";
      const channelGate = document.getElementById("versionChannel")?.value || "";
      const artifactGate = artifactFilter?.value || "";
      return (
        (!envGate || normalizedEnv(row) === envGate) &&
        (!channelGate || rowChannel === channelGate) &&
        (!platformGate || row.platform === platformGate) &&
        (!filterStatus?.value || row.version_status === filterStatus.value) &&
        (!artifactGate || (artifactGate === "ready" ? row.apk_status === "found" : row.apk_status !== "found")) &&
        (!filterVersionName || (row.version_name || "") === filterVersionName) &&
        (!query || JSON.stringify(row).toLowerCase().includes(query))
      );
    });
    const visibleGroups = versionGroups.filter((group) => {
      if (platformGate && group.platform && group.platform !== platformGate) return false;
      if (filterVersionName) return group.version_name === filterVersionName;
      if (!query) return true;
      const name = (group.version_name || "").toLowerCase();
      if (name.includes(query)) return true;
      return filtered.some((row) => (row.version_name || "") === group.version_name);
    });
    const groupNames = visibleGroups.map((group) => group.version_name);
    const pages = Math.max(1, Math.ceil(visibleGroups.length / listPageSize));
    listPage = Math.min(listPage, pages);
    const pageGroups = visibleGroups.slice((listPage - 1) * listPageSize, listPage * listPageSize);
    const pagination = document.getElementById("versionPagination");
    if (pagination) {
      pagination.hidden = visibleGroups.length <= listPageSize;
      const countEl = pagination.querySelector("[data-version-count]");
      const pageText = pagination.querySelector("[data-version-page-text]");
      const prev = pagination.querySelector("[data-version-prev]");
      const next = pagination.querySelector("[data-version-next]");
      if (countEl) countEl.textContent = `共 ${visibleGroups.length} 个版本组，${filtered.length} 个 VersionCode`;
      if (pageText) pageText.textContent = `${listPage} / ${pages}`;
      if (prev) prev.disabled = listPage <= 1;
      if (next) next.disabled = listPage >= pages;
    }
    const groups = pageGroups.map((group) => {
      const children = filtered
        .filter((row) => (row.version_name || "") === group.version_name)
        .sort((a, b) => {
          const envCmp = normalizedEnv(a).localeCompare(normalizedEnv(b));
          if (envCmp) return envCmp;
          const channelCmp = channelIdOf(a).localeCompare(channelIdOf(b));
          if (channelCmp) return channelCmp;
          const platformCmp = String(a.platform || "").localeCompare(String(b.platform || ""));
          if (platformCmp) return platformCmp;
          return String(a.version_code || "").localeCompare(String(b.version_code || ""), undefined, { numeric: true });
        });
      return groupRowHtml(group, children);
    });
    document.getElementById("versionGroups").innerHTML = groups.length
      ? groups.join("")
      : (envScoped
        ? `<div class="version-empty">本环境${platformGate ? ` · ${platformLabelOf(platformGate)}` : ""}尚无 VersionCode。请在版本组行点击「添加 VC」创建。</div>`
        : '<div class="version-empty">当前筛选条件下暂无版本数据。</div>');
    document.querySelectorAll("[data-toggle-group]").forEach((button) => {
      button.onclick = () => {
        const name = button.dataset.toggleGroup;
        const card = button.closest(".version-group-card");
        if (card?.classList.contains("is-collapsed")) {
          collapsedGroups.delete(name);
          card.classList.remove("is-collapsed");
          button.setAttribute("aria-expanded", "true");
        } else {
          collapsedGroups.add(name);
          card?.classList.add("is-collapsed");
          button.setAttribute("aria-expanded", "false");
        }
      };
    });
    document.querySelectorAll("[data-edit-group]").forEach((button) => {
      button.onclick = () => openGroupDialog(button.dataset.editGroup);
    });
    document.querySelectorAll("[data-delete-group]").forEach((button) => {
      button.onclick = () => deleteGroup(button.dataset.deleteGroup);
    });
    document.querySelectorAll("[data-add-vc]").forEach((button) => {
      button.onclick = () => openVersionDialog(button.dataset.addVc);
    });
    document.querySelectorAll("[data-download-apk]").forEach((button) => {
      button.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        handleDownloadClick(button.getAttribute("data-download-apk") || "");
      };
    });
    document.querySelectorAll("[data-download-pick]").forEach((button) => {
      button.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        const groupName = button.getAttribute("data-download-pick") || "";
        const platformGate = activePlatform();
        const channelGate = document.getElementById("versionChannel")?.value || lockChannelId || "";
        const picks = rows.filter((row) => {
          if ((row.version_name || "") !== groupName) return false;
          if (row.apk_status !== "found") return false;
          if (platformGate && row.platform !== platformGate) return false;
          if (channelGate && channelIdOf(row) !== channelGate) return false;
          return true;
        });
        openDownloadPicker(picks);
      };
    });
    document.querySelectorAll("[data-open-vc]").forEach((el) => {
      el.onclick = (event) => {
        if (event.target.closest("a, button, [data-download-apk], [data-download-pick], [data-toggle-vc-more], .version-row-more-dropdown")) return;
        const id = el.getAttribute("data-open-vc");
        const row = rows.find((item) => String(item.id || "") === String(id));
        if (row) openVcDrawer(row);
      };
    });
    updateBuildHistoryLink();
    updateScopeBanner();
  };

  const contextOptionsUrl = (env) => {
    const query = env ? `?env_key=${encodeURIComponent(env)}` : "";
    return `/api/projects/${projectId}/context-options${query}`;
  };

  const ensureEnvSelectOption = (select, envKey, label) => {
    if (!select || !envKey) return;
    if (![...select.options].some((option) => option.value === envKey)) {
      const option = document.createElement("option");
      option.value = envKey;
      option.textContent = label || envLabels[envKey] || envKey;
      select.appendChild(option);
    }
    select.value = envKey;
  };

  const applyEnvironmentOptions = (environments) => {
    const envs = environments || [];
    const formEnv = document.getElementById("versionFormEnv");
    if (!formEnv) return;
    const current = formEnv.value;
    formEnv.innerHTML = envs.map((item) => `<option value="${esc(item.env_key)}">${esc(item.label || envLabels[item.env_key] || item.env_key)}</option>`).join("");
    if (current && [...formEnv.options].some((option) => option.value === current)) formEnv.value = current;
    else if (lockEnvKey) formEnv.value = lockEnvKey;
  };

  const applyContextOptions = (contextPayload, { env, channelSelect, platformSelect, filterPlatformSelect } = {}) => {
    const payload = contextPayload && contextPayload.data ? contextPayload.data : contextPayload;
    channels = payload.channels || [];
    platforms = payload.platforms || [];
    if (payload.environments?.length) applyEnvironmentOptions(payload.environments);
    if (channelSelect) {
      const current = channelSelect.value;
      channelSelect.innerHTML = channels.map((x) => `<option value="${esc(x.channel_id)}">${esc(x.channel_name)}</option>`).join("");
      if (channels.some((x) => x.channel_id === current)) channelSelect.value = current;
      else if (channels.length) channelSelect.value = channels[0].channel_id;
    }
    if (platformSelect) {
      const current = platformSelect.value;
      platformSelect.innerHTML = platforms.map((x) => `<option value="${esc(x.value)}">${esc(x.label)}</option>`).join("");
      if (platforms.some((x) => x.value === current)) platformSelect.value = current;
      else if (platforms.length) platformSelect.value = platforms[0].value;
    }
    if (filterPlatformSelect) {
      const current = filterPlatformSelect.value;
      filterPlatformSelect.innerHTML =
        '<option value="">全部平台</option>' + platforms.map((x) => `<option value="${esc(x.value)}">${esc(x.label)}</option>`).join("");
      if (current && platforms.some((x) => x.value === current)) filterPlatformSelect.value = current;
    }
    const filterChannel = document.getElementById("versionChannel");
    if (filterChannel && env) {
      const current = lockChannelId || filterChannel.value;
      filterChannel.innerHTML = channels.map((x) => `<option value="${esc(x.channel_id)}">${esc(x.channel_name)}</option>`).join("");
      if (current && channels.some((x) => x.channel_id === current)) filterChannel.value = current;
      else if (lockChannelId && channels.some((x) => x.channel_id === lockChannelId)) filterChannel.value = lockChannelId;
      else if (channels.length) filterChannel.value = channels[0].channel_id;
      if (lockChannelScoped) filterChannel.disabled = true;
    }
  };

  const refreshVersionNameSelect = (selected = "") => {
    const select = document.getElementById("versionNameSelect");
    if (!select) return;
    const names = versionGroups.map((group) => group.version_name).filter(Boolean);
    select.innerHTML =
      names.map((name) => `<option value="${esc(name)}">${esc(name)}</option>`).join("") +
      (canEdit ? `<option value="__new__">+ 新建版本组…</option>` : "");
    if (selected && names.includes(selected)) select.value = selected;
    else if (names.length) select.value = names[0];
  };

  const renderPlatformTabs = () => {
    const host = document.getElementById("versionPlatformTabs");
    if (!host) return;
    if (!platformTabsVisible()) {
      host.classList.add("is-hidden");
      host.innerHTML = "";
      return;
    }
    if (!activePlatformKey && platforms.length) activePlatformKey = platforms[0].value;
    host.classList.remove("is-hidden");
    host.innerHTML = platforms
      .map((item) => {
        const active = activePlatformKey === item.value;
        return `<button type="button" class="version-platform-tab${active ? " active" : ""}" data-platform="${esc(item.value)}" role="tab" aria-selected="${active ? "true" : "false"}">${esc(item.label)}</button>`;
      })
      .join("");
    host.querySelectorAll(".version-platform-tab").forEach((button) => {
      button.onclick = async () => {
        activePlatformKey = button.dataset.platform || "";
        renderPlatformTabs();
        syncScopeUrl();
        try {
          await load();
        } catch (error) {
          toast(error.message, "error");
        }
      };
    });
  };

  const applyEnvScopedUi = () => {
    root.classList.add("is-env-scoped", "is-channel-scoped");
    const channelSelect = document.getElementById("versionChannel");
    if (channelSelect && lockChannelId) {
      channelSelect.disabled = true;
      channelSelect.classList.add("is-locked");
    }
  };

  const versionGroupsUrl = () => {
    const env = activeEnvKey();
    const platform = activePlatform();
    const params = new URLSearchParams();
    if (env) params.set("env_key", env);
    if (platform) params.set("platform", platform);
    const qs = params.toString();
    return `/admin/projects/${projectId}/version-groups${qs ? `?${qs}` : ""}`;
  };

  const scopedPayload = (payload = {}) => {
    const env = activeEnvKey();
    const platform = activePlatform();
    if (env) payload.env_key = env;
    if (platform) payload.platform = platform;
    return payload;
  };

  const buildVersionFormPayload = () => {
    const payload = Object.fromEntries(new FormData(form).entries());
    const env = activeEnvKey();
    const platform = activePlatform();
    if (env) payload.env_key = env;
    if (platform) payload.platform = platform;
    if (useAllEnvChannels()) {
      payload.apply_all_channels = true;
      delete payload.channel_id;
    } else {
      const channel = activeChannelId();
      if (channel) payload.channel_id = form.channel_id?.value || channel;
    }
    return payload;
  };

  const updateScopeFormUi = () => {
    const scoped = Boolean(activeEnvKey());
    const allChannels = useAllEnvChannels();
    const scopeBox = document.getElementById("versionFormScope");
    const scopeText = document.getElementById("versionFormScopeText");
    const channelField = document.getElementById("versionFormChannelField");
    const submitBtn = document.getElementById("btnSubmitVersionCode");
    document.querySelectorAll("#versionForm .js-scope-field").forEach((node) => {
      node.classList.toggle("is-hidden", scoped);
    });
    if (channelField) channelField.classList.toggle("is-hidden", scoped || allChannels);
    if (scopeBox) scopeBox.classList.toggle("is-hidden", !scoped);
    if (scopeText) scopeText.textContent = scopeSummaryText();
    if (submitBtn) {
      submitBtn.textContent = allChannels && channels.length > 1
        ? `为 ${channels.length} 个渠道创建`
        : "创建 VersionCode";
    }
    const hint = document.getElementById("versionDialogHint");
    if (hint) {
      hint.textContent = allChannels
        ? "将为当前平台下全部可用渠道各创建一条 VersionCode（已存在的渠道将自动跳过）。"
        : scoped
          ? "平台由页签决定，本交付线渠道已锁定。"
          : "选择已有版本组后创建精确构建号。";
    }
    const groupHint = document.getElementById("versionGroupDialogHint");
    if (groupHint) {
      groupHint.textContent = scoped
        ? `将创建到：${scopeSummaryText()}。版本组归属当前环境与平台页签。`
        : "版本组可独立创建，用于组织多个 VersionCode。";
    }
  };

  const load = async () => {
    const host = document.getElementById("versionGroups");
    try {
      const envFilterValue = lockEnvKey || document.getElementById("versionEnv")?.value || envKey || "";
      const [versionData, groupData, context, releaseOrdersRes] = await Promise.all([
        request(`/admin/projects/${projectId}/versions/list`),
        request(versionGroupsUrl()),
        request(contextOptionsUrl(envFilterValue)),
        request(`/api/projects/${projectId}/release-orders`).catch(() => ({ data: [] })),
      ]);
      rows = versionData.versions || [];
      versionGroups = groupData.version_groups || [];
      releaseOrderByVersion = new Map();
      (releaseOrdersRes.data || []).forEach((order) => {
        const vid = String(order.version_id || "");
        if (!vid) return;
        const existing = releaseOrderByVersion.get(vid);
        if (!existing || String(order.updated_at || "") > String(existing.updated_at || "")) {
          releaseOrderByVersion.set(vid, order);
        }
      });
      deliveryActionsByVersion = new Map();
      await loadDeliveryActions(rows.map((row) => row.id));
      applyContextOptions(context, {
        env: envFilterValue,
        filterPlatformSelect: document.getElementById("versionPlatform"),
      });
      if (!activePlatformKey && platforms.length) activePlatformKey = lockPlatform || platforms[0].value;
      renderPlatformTabs();
      refreshVersionNameSelect();
      const channelFilter = document.getElementById("versionChannel");
      if (channelFilter && lockChannelId && !channelFilter.value) channelFilter.value = lockChannelId;
      render();
    } catch (error) {
      if (host) host.innerHTML = `<div class="version-empty">${esc(error.message || "加载失败")}</div>`;
      toast(error.message || "加载失败", "error");
    }
  };

  const groupDialog = document.getElementById("versionGroupDialog");
  const groupForm = document.getElementById("versionGroupForm");
  let groupEditMode = false;

  const closeGroupDialog = () => {
    groupDialog.classList.add("is-hidden");
    groupDialog.setAttribute("aria-hidden", "true");
    groupForm.reset();
    groupEditMode = false;
    document.getElementById("versionGroupDialogTitle").textContent = "新建版本组";
    document.getElementById("btnSubmitVersionGroup").textContent = "创建版本组";
    document.getElementById("versionGroupNameInput").disabled = false;
  };

  const openGroupDialog = (versionName = "") => {
    if (!canEdit) return;
    if (versionName) {
      const platform = activePlatform();
      const group = versionGroups.find(
        (item) =>
          item.version_name === versionName &&
          (!envScoped || item.env_key === lockEnvKey || !item.env_key) &&
          (!platform || item.platform === platform || !item.platform),
      );
      if (!group) return;
      groupEditMode = true;
      document.getElementById("versionGroupDialogTitle").textContent = "编辑版本组";
      document.getElementById("btnSubmitVersionGroup").textContent = "保存";
      groupForm.version_name.value = group.version_name;
      groupForm.version_mode.value = group.version_mode || "general";
      groupForm.status.value = group.status || "active";
      groupForm.notes.value = group.notes || "";
      groupForm.recommended.checked = Boolean(group.recommended);
      document.getElementById("versionGroupNameInput").disabled = true;
    } else {
      closeGroupDialog();
      document.getElementById("versionGroupDialogTitle").textContent = "新建版本组";
      document.getElementById("btnSubmitVersionGroup").textContent = "创建版本组";
      document.getElementById("versionGroupNameInput").disabled = false;
    }
    updateScopeFormUi();
    groupDialog.classList.remove("is-hidden");
    groupDialog.setAttribute("aria-hidden", "false");
  };

  const deleteGroup = async (versionName) => {
    if (!canEdit || !versionName) return;
    const group = versionGroups.find((item) => item.version_name === versionName);
    const count = group?.version_code_count || 0;
    const message = count
      ? `确认删除版本组「${versionName}」？将同时删除其下 ${count} 个 VersionCode。`
      : `确认删除版本组「${versionName}」？`;
    if (!confirm(message)) return;
    try {
      await request(`/admin/projects/${projectId}/versions/delete-group`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(scopedPayload({ version_name: versionName })),
      });
      toast("版本组已删除");
      if (filterVersionName === versionName) filterVersionName = "";
      await load();
    } catch (error) {
      toast(error.message, "error");
    }
  };

  const dialog = document.getElementById("versionDialog");
  const form = document.getElementById("versionForm");
  const closeVersionDialog = () => {
    dialog.classList.add("is-hidden");
    dialog.setAttribute("aria-hidden", "true");
    form.reset();
  };
  const setFieldLock = (field, locked) => {
    if (!field) return;
    field.disabled = Boolean(locked);
    field.classList.toggle("is-locked", Boolean(locked));
  };

  const openVersionDialog = async (presetGroup = "") => {
    if (!canEdit) return;
    refreshVersionNameSelect(presetGroup);
    const targetEnv = activeEnvKey() || envKey || "development";
    ensureEnvSelectOption(form.env_key, targetEnv, envLabels[targetEnv] || targetEnv);
    try {
      const context = await request(contextOptionsUrl(form.env_key.value));
      applyContextOptions(context, {
        env: form.env_key.value,
        channelSelect: document.getElementById("versionFormChannel"),
        platformSelect: document.getElementById("versionFormPlatform"),
      });
      const channelId = activeChannelId();
      if (channelId) form.channel_id.value = channelId;
      const platformValue = activePlatform();
      if (platformValue) form.platform.value = platformValue;
      if (activeEnvKey()) {
        setFieldLock(form.env_key, true);
        setFieldLock(form.platform, true);
        setFieldLock(form.channel_id, lockDeliveryLine);
      } else {
        setFieldLock(form.env_key, false);
        setFieldLock(form.platform, false);
        setFieldLock(form.channel_id, false);
      }
    } catch (error) {
      toast(error.message, "error");
    }
    updateScopeFormUi();
    if (presetGroup) document.getElementById("versionNameSelect").value = presetGroup;
    dialog.classList.remove("is-hidden");
    dialog.setAttribute("aria-hidden", "false");
  };

  document.getElementById("btnCreateVersionGroup")?.addEventListener("click", () => openGroupDialog());
  document.getElementById("btnCreateVersionCode")?.addEventListener("click", () => openVersionDialog());
  document.getElementById("btnExportVersions")?.addEventListener("click", exportCsv);
  document.getElementById("btnResetVersionFilters")?.addEventListener("click", () => {
    const search = document.getElementById("versionSearch");
    if (search) search.value = "";
    ["versionChannel", "versionStatus", "versionArtifactStatus"].forEach((id) => {
      const el = document.getElementById(id);
      if (el && id !== "versionChannel") el.value = "";
    });
    listPage = 1;
    render();
  });
  document.getElementById("versionPagination")?.addEventListener("click", (event) => {
    if (event.target.closest("[data-version-prev]")) {
      listPage = Math.max(1, listPage - 1);
      render();
    }
    if (event.target.closest("[data-version-next]")) {
      listPage += 1;
      render();
    }
  });
  document.querySelectorAll("[data-vc-drawer-close]").forEach((el) => el.addEventListener("click", closeVcDrawer));
  document.addEventListener("pm-shell-search", (event) => {
    const search = document.getElementById("versionSearch");
    if (search) {
      search.value = event.detail?.query || "";
      listPage = 1;
      render();
    }
  });
  document.getElementById("btnCloseVersionGroupDialog").onclick = closeGroupDialog;
  document.getElementById("btnCancelVersionGroupDialog").onclick = closeGroupDialog;
  document.getElementById("btnCloseVersionDialog").onclick = closeVersionDialog;
  document.getElementById("btnCancelVersionDialog").onclick = closeVersionDialog;
  document.getElementById("btnRefreshVersions").onclick = () => load().catch((error) => toast(error.message, "error"));

  groupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!canEdit) return;
    const payload = {
      version_name: groupForm.version_name.value.trim(),
      version_mode: groupForm.version_mode.value,
      status: groupForm.status.value,
      notes: groupForm.notes.value.trim(),
      recommended: groupForm.recommended.checked,
    };
    try {
      if (groupEditMode) {
        await request(`/admin/projects/${projectId}/version-groups/update`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(scopedPayload(payload)),
        });
        toast("版本组已更新");
      } else {
        await request(`/admin/projects/${projectId}/version-groups/create`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(scopedPayload(payload)),
        });
        toast("版本组已创建");
      }
      closeGroupDialog();
      await load();
    } catch (error) {
      toast(error.message, "error");
    }
  });

  document.getElementById("versionNameSelect")?.addEventListener("change", (event) => {
    if (event.target.value === "__new__") {
      closeVersionDialog();
      openGroupDialog();
    }
  });

  document.getElementById("versionFormEnv")?.addEventListener("change", async (event) => {
    if (lockEnvKey) return;
    try {
      const context = await request(contextOptionsUrl(event.target.value));
      applyContextOptions(context, {
        env: event.target.value,
        channelSelect: document.getElementById("versionFormChannel"),
        platformSelect: document.getElementById("versionFormPlatform"),
      });
    } catch (error) {
      toast(error.message, "error");
    }
  });

  const showJourneyHint = () => {
    const hint = urlParams.get("hint") || "";
    if (!hint) return;
    const panel = document.querySelector(".version-panel");
    if (!panel || document.getElementById("versionJourneyHint")) return;
    const banner = document.createElement("div");
    banner.id = "versionJourneyHint";
    banner.className = "version-hint-banner";
    const error = urlParams.get("error");
    if (hint === "pick_env") {
      banner.textContent = "请先在「环境配置」中选择要操作的交付环境，再进入版本代码工作台。";
    } else if (hint === "use_versions_hub") {
      banner.textContent = "下载与产物管理已并入版本代码页。请在本环境筛选 VersionCode，使用行内「下载」或顶部「构建与产物」。";
    } else if (hint === "pick_vc") {
      banner.textContent = error
        ? `无法继续：${error}。请先配置版本组管线，再使用行内「触发构建」或「继续发版」。`
        : "请在本页选择 VersionCode，使用行内「触发构建」或「继续发版」。";
    } else {
      return;
    }
    panel.insertBefore(banner, panel.firstChild);
  };

  applyEnvScopedUi();
  showJourneyHint();

  ["versionSearch", "versionStatus", "versionArtifactStatus"].forEach((id) => {
    const node = document.getElementById(id);
    if (!node) return;
    if (id === "versionSearch") {
      node.addEventListener("input", () => { listPage = 1; render(); });
      return;
    }
    node.addEventListener("change", () => { listPage = 1; render(); });
  });

  const envFilter = document.getElementById("versionEnv");
  if (envFilter) envFilter.value = lockEnvKey || envKey || "";

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!canEdit) return;
    const versionNameSelect = document.getElementById("versionNameSelect");
    if (versionNameSelect?.value === "__new__") {
      toast("请先创建版本组", "error");
      return;
    }
    try {
      const result = await request(`/admin/projects/${projectId}/versions/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildVersionFormPayload()),
      });
      const created = Number(result.created_count || 0) || (result.version ? 1 : 0);
      const skipped = Number(result.skipped_count || 0);
      if (created > 1) {
        toast(skipped ? `已为 ${created} 个渠道创建，${skipped} 个渠道已存在已跳过` : `已为 ${created} 个渠道创建 VersionCode`);
      } else {
        toast("VersionCode 已创建");
      }
      closeVersionDialog();
      await load();
    } catch (error) {
      toast(error.message, "error");
    }
  });

  load()
    .then(async () => {
      if (createVcAction && canEdit) {
        await openVersionDialog();
        urlParams.delete("action");
        const qs = urlParams.toString();
        history.replaceState(null, "", `${location.pathname}${qs ? `?${qs}` : ""}`);
      }
      const drawerId = urlParams.get("vc_drawer");
      if (drawerId) {
        const row = rows.find((item) => String(item.id || "") === drawerId);
        if (row) openVcDrawer(row);
      }
      const downloadVc = urlParams.get("download_vc");
      if (downloadVc) {
        await handleDownloadClick(downloadVc);
        urlParams.delete("download_vc");
        const qs = urlParams.toString();
        history.replaceState(null, "", `${location.pathname}${qs ? `?${qs}` : ""}`);
      }
    })
    .catch((error) => toast(error.message, "error"));

  root.addEventListener("click", (event) => {
    const moreBtn = event.target.closest("[data-toggle-vc-more]");
    if (moreBtn) {
      event.preventDefault();
      event.stopPropagation();
      const menuId = moreBtn.getAttribute("data-toggle-vc-more") || "";
      const menu = menuId ? document.getElementById(menuId) : null;
      const willOpen = !menu?.classList.contains("open");
      document.querySelectorAll(".version-row-more-dropdown.open").forEach((node) => node.classList.remove("open"));
      document.querySelectorAll("[data-toggle-vc-more]").forEach((node) => node.setAttribute("aria-expanded", "false"));
      if (willOpen && menu) {
        menu.classList.add("open");
        moreBtn.setAttribute("aria-expanded", "true");
      }
      return;
    }
    if (!event.target.closest(".version-action-more-menu")) {
      document.querySelectorAll(".version-row-more-dropdown.open").forEach((node) => node.classList.remove("open"));
      document.querySelectorAll("[data-toggle-vc-more]").forEach((node) => node.setAttribute("aria-expanded", "false"));
    }
  });
  root.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-download-apk]");
    if (!btn) return;
    event.preventDefault();
    event.stopPropagation();
    handleDownloadClick(btn.getAttribute("data-download-apk") || "");
  });
  root.addEventListener("click", (event) => {
    const pickBtn = event.target.closest("[data-download-pick]");
    if (!pickBtn) return;
    event.preventDefault();
    event.stopPropagation();
    const groupName = pickBtn.getAttribute("data-download-pick") || "";
    const platformGate = activePlatform();
    const channelGate = document.getElementById("versionChannel")?.value || lockChannelId || "";
    const picks = rows.filter((row) => {
      if ((row.version_name || "") !== groupName) return false;
      if (row.apk_status !== "found") return false;
      if (platformGate && row.platform !== platformGate) return false;
      if (channelGate && channelIdOf(row) !== channelGate) return false;
      return true;
    });
    openDownloadPicker(picks);
  });
  if (scopeApi.bindQuickBuild) {
    scopeApi.bindQuickBuild(root, {
      projectId,
      request,
      onSuccess: (order, versionId) => {
        toast(order.status === "building" ? "构建已触发" : order.status === "artifacts_ready" ? "产物已就绪，可继续发版" : "操作已提交");
        deliveryActionsByVersion.delete(String(versionId || order.version_id || ""));
        if (order.release_order_id) {
          const row = rows.find((item) => String(item.id || "") === String(versionId || order.version_id || ""));
          location.href = releaseOrderDetailHref(row || { id: order.version_id, env_key: order.env_key, channel_id: order.channel_id, platform: order.platform }, order);
          return;
        }
        load().catch((error) => toast(error.message, "error"));
      },
      onError: (error, versionId) => {
        toast(error.message || "操作失败", "error");
        if (/发布计划/.test(error.message || "")) {
          const row = rows.find((item) => String(item.id || "") === String(versionId || ""));
          if (row) location.href = startReleaseHref(row);
        }
      },
    });
  }
})();
