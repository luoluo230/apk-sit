(() => {
  const root = document.querySelector(".version-workspace");
  if (!root) return;
  const projectId = root.dataset.projectId;
  const canEdit = root.dataset.canEdit === "true";
  const envKey = root.dataset.envKey;
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const withReturnTo = (href) => {
    try {
      const url = new URL(String(href || ""), location.origin);
      if (!url.searchParams.get("return_to")) {
        url.searchParams.set("return_to", `${location.pathname}${location.search || ""}`);
      }
      return `${url.pathname}${url.search}`;
    } catch {
      return String(href || "");
    }
  };
  const envLabels = { development: "开发环境", testing: "测试环境", staging: "预发环境", production: "生产环境" };
  const statusLabels = { active: "有效", testing: "测试中", draft: "草稿", disabled: "失效", archived: "归档" };
  const groupModeLabels = { general: "通用", commercial: "商业化" };
  const urlParams = new URLSearchParams(location.search);
  const lockChannelId = urlParams.get("channel_id") || root.dataset.channelFilter || "";
  const lockPlatform = urlParams.get("platform") || root.dataset.platformFilter || "";
  const lockEnvKey = urlParams.get("env_key") || root.dataset.envKey || document.getElementById("versionEnvHidden")?.value || "";
  const lockDeliveryLine = urlParams.get("action") === "create_vc" && lockChannelId && lockPlatform;
  const envScoped = Boolean(lockEnvKey);
  const createVcAction = urlParams.get("action") === "create_vc";
  let rows = [];
  let versionGroups = [];
  let channels = [];
  let platforms = [];
  let filterVersionName = urlParams.get("version_name") || "";
  let activePlatformKey = lockPlatform || "";
  let selectedChannelId = lockChannelId || "";
  // 默认折叠：仅当用户点开时加入 expanded 集合
  const expandedPipelines = new Set();
  const expandedVcGroups = new Set();
  let matrixExpanded = false;
  let listPage = 1;
  const listPageSize = 20;
  let loadSeq = 0;
  let suppressChannelChange = false;
  let releaseOrderByVersion = new Map();
  let deliveryActionsByVersion = new Map();
  const scopeApi = window.DeliveryScope || {};
  const buildScopeQuery = (scope = {}, extra = {}) => (scopeApi.buildQuery ? scopeApi.buildQuery(scope, extra) : "");
  const scopeHref = (path, scope = {}, extra = {}) => (scopeApi.href ? scopeApi.href(path, scope, extra) : path);
  const startReleaseHref = (row) => scopeHref(`/admin/projects/${projectId}/versions`, {
    env_key: normalizedEnv(row),
    channel_id: channelIdOf(row),
    platform: row.platform || "",
    version_id: row.id,
    action: "edit_release",
  });
  const continueReleaseHref = startReleaseHref;
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
  const channelFilterValue = () =>
    document.getElementById("versionChannel")?.value || selectedChannelId || "";
  const platformLabelOf = (platformValue) => {
    const hit = platforms.find((item) => item.value === platformValue);
    return hit?.label || platformValue || "-";
  };
  const activeEnvKey = () => {
    const sel = document.getElementById("versionEnv");
    if (sel?.value) return sel.value;
    return lockEnvKey || document.getElementById("versionEnvHidden")?.value || "";
  };
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
  const platformTabsVisible = () => false;
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
    channel_id: document.getElementById("versionChannel")?.value || "",
    platform: activePlatform(),
  });

  const updateScopeBanner = () => {
    const env = activeEnvKey() || envKey || "production";
    const envLink = document.getElementById("versionScopeEnvLink");
    if (envLink) envLink.href = `/admin/projects/${projectId}/environments/${encodeURIComponent(env)}`;
  };

  const updateBuildHistoryLink = () => {
    const link = document.getElementById("versionBuildHistoryLink");
    if (!link) return;
    const scope = currentScope();
    link.href = scopeHref(`/admin/projects/${projectId}/build-history`, scope, { scoped: "1" });
  };

  const updateBuildJourneyLink = () => {
    const link = document.getElementById("versionBuildJourneyLink");
    if (!link) return;
    const scope = currentScope();
    const env = scope.env_key || envKey || "development";
    const channel = scope.channel_id || lockChannelId || "1001";
    const qs = new URLSearchParams();
    if (scope.platform) qs.set("platform", scope.platform);
    const query = qs.toString();
    link.href = withReturnTo(`/admin/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(env)}/channels/${encodeURIComponent(channel)}/build${query ? `?${query}` : ""}`);
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
    const progressWidth = artifactReady ? 100 : (building ? 55 : 0);
    const progressHtml = progressWidth > 0
      ? `<div class="current-progress" style="height:6px;background:#eef1f6;border-radius:3px;margin:10px 0"><span style="display:block;height:100%;width:${progressWidth}%;background:#1677ff;border-radius:3px"></span></div>`
      : "";
    body.innerHTML = `<div class="pm-drawer-tags">${versionNameTagHtml(row, null)}<span class="pm-tag pm-tag--muted">${esc(row.version_name || "")}</span><span class="pm-tag pm-tag--muted">${esc(normalizedEnv(row))}</span><span class="pm-tag pm-tag--muted">${esc(row.channel_name || channelNameOf(channelIdOf(row)))}</span><span class="pm-tag pm-tag--muted">${esc(row.platform_label || row.platform || "")}</span></div>
    <div class="pm-drawer-section"><h3>当前构建</h3><div class="pm-drawer-build-head"><strong>${buildHeadLabel}</strong>${latestBuildHtml(row)}</div>
    ${progressHtml}</div>
    <div class="pm-drawer-section"><h3>产物完整性</h3><div class="pm-drawer-meta"><div><span>状态</span><b>${artifactReady ? "完整" : "不完整"}</b></div><div><span>发布</span><b>${row.active_bundle_id ? "已发布" : "未发布"}</b></div></div></div>
    <div class="pm-drawer-section"><h3>关联发布单</h3><div class="pm-drawer-meta"><div><span>Bundle</span><b>${row.active_bundle_id ? "活跃" : "无"}</b></div></div></div>`;
    const primary = cached.primary || {};
    const drawerPrimary = primary.api_action === "quick_build" && primary.version_id
      ? `<button class="pm-btn pm-btn--primary" type="button" data-quick-build="${esc(primary.version_id)}">${esc(primary.label || "触发构建")}</button>`
      : primary.href
        ? `<a class="pm-btn pm-btn--primary" href="${esc(primary.href)}">${esc(primary.label || "继续发版")}</a>`
        : `<a class="pm-btn pm-btn--primary" href="${releaseOrderDetailHref(row, releaseOrderByVersion.get(String(row.id || "")))}">继续发版</a>`;
    const journeyQs = new URLSearchParams({
      platform: String(row.platform || "android").toLowerCase(),
      version_id: String(row.id || ""),
    });
    const journeyHref = withReturnTo(`/admin/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(normalizedEnv(row))}/channels/${encodeURIComponent(channelIdOf(row) || "1001")}/build?${journeyQs}`);
    foot.innerHTML = `${drawerPrimary}
      <a class="pm-btn" href="${esc(journeyHref)}">构建流程</a>
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
    const order = releaseOrderByVersion.get(String(row.id || ""));
    const orderStatus = order?.status || "";
    const vid = esc(row.id || "");
    const menuId = `vc-more-${vid}`;
    const canPublish = ["ready", "approved", "artifacts_ready"].includes(orderStatus);
    const canRollback = ["published", "verified", "verify_failed"].includes(orderStatus) || Boolean(row.active_bundle_id);
    const moreItems = [
      `<button type="button" class="version-action-link" data-release-action="edit" data-version-id="${vid}">发版编辑</button>`,
    ];
    if (canPublish) moreItems.push(`<button type="button" class="version-action-link" data-release-action="publish" data-version-id="${vid}">发布到线上</button>`);
    moreItems.push(`<button type="button" class="version-action-link" data-release-action="announce" data-version-id="${vid}">发布公告</button>`);
    if (canRollback) moreItems.push(`<button type="button" class="version-action-link" data-release-action="rollback" data-version-id="${vid}">回滚</button>`);
    moreItems.push(`<button type="button" class="version-action-link" data-release-action="server-pause" data-version-id="${vid}">服务器暂停</button>`);
    return `<div class="version-row-actions">
      <button type="button" class="version-btn release compact" data-edit-release="${vid}">发版编辑</button>
      <button type="button" class="version-btn build compact" data-quick-build="${vid}">构建</button>
      <div class="version-action-more-menu">
        <button type="button" class="version-action-more" data-toggle-vc-more="${menuId}" aria-expanded="false" aria-label="更多发版操作"><img src="/static/project_ui/svg/action_more.svg" alt=""></button>
        <div id="${menuId}" class="version-row-more-dropdown">${moreItems.join("")}</div>
      </div>
      <button type="button" class="version-btn neutral compact" data-open-vc-row="${vid}">详情</button>
    </div>`;
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

  const pickPrimaryVc = (children) => {
    if (!children.length) return null;
    const ranked = [...children].sort((a, b) => {
      const score = (row) => {
        let n = 0;
        if (row.active_bundle_id) n += 40;
        if (row.apk_status === "found") n += 20;
        if (isBuildInProgress(row)) n += 15;
        return n;
      };
      const diff = score(b) - score(a);
      if (diff) return diff;
      return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
    });
    return ranked[0];
  };

  const groupBuildConfigHref = (group, children, options = {}) => {
    const params = new URLSearchParams();
    params.set("from", options.highlightGate ? "prepare-gate" : "version-group");
    params.set("version_name", group.version_name || "");
    if (group.env_key) params.set("env_key", group.env_key);
    if (group.platform) params.set("platform", group.platform);
    if (options.highlightGate) {
      const readiness = group.pipeline_readiness || {};
      const checks = readiness.checks || {};
      const fields = [];
      if (checks.jenkins_instance === false || !String(group.jenkins_instance_id || readiness.jenkins_instance_id || "").trim()) {
        fields.push("jenkins_instance_id");
      }
      if (checks.jenkins_job === false || !String(group.jenkins_job_id || readiness.jenkins_job_id || "").trim()) {
        fields.push("jenkins_job_id");
      }
      if (
        checks.pipeline === false
        || (Array.isArray(readiness.missing_pipeline_steps) && readiness.missing_pipeline_steps.length)
      ) {
        fields.push("config_export_enabled", "resource_build_enabled", "hot_release_enabled", "apk_build_enabled");
      }
      // 打包实操常用必填：空着一并标红，避免进来后不知道改哪里
      ["git_branch", "unity_version", "app_name", "unity_project_path", "output_base_dir"].forEach((name) => fields.push(name));
      params.set("highlight", [...new Set(fields)].join(","));
      params.set("section", "jenkins");
      params.set(
        "focus_reason",
        readiness.blocker_hint
          || (Array.isArray(readiness.missing) && readiness.missing.length
            ? `待完善：${readiness.missing.join("、")}`
            : "请补全红色高亮的必填项并保存配置，准备通过后才会点亮「打包」。"),
      );
    }
    const anchorId = children[0]?.id || group.anchor_version_id || "";
    return anchorId
      ? `/admin/projects/${projectId}/versions/${encodeURIComponent(anchorId)}/build-config?${params}`
      : `/admin/projects/${projectId}/version-groups/build-config?${params}`;
  };

  const acceptanceOf = (row) => {
    const raw = row?.client_acceptance;
    if (!raw || typeof raw !== "object") return { status: "pending" };
    const status = String(raw.status || "pending").toLowerCase();
    return { status: ["passed", "failed", "pending"].includes(status) ? status : "pending", ...raw };
  };

  const planFieldLabels = {
    owner: "负责人",
    reason: "发布原因",
    release_window: "发布窗口",
    release_description: "对内说明",
    validation_plan: "验证计划",
    rollback_plan: "回滚计划",
  };

  const collectPrepareBlockers = (group, primary, order) => {
    const readiness = group?.pipeline_readiness || primary?.pipeline_readiness || {};
    const blockers = [];
    const missing = Array.isArray(readiness.missing) ? readiness.missing.filter(Boolean) : [];
    missing.forEach((item) => blockers.push({ kind: "pipeline", label: String(item), field: "" }));
    if (!Boolean(group?.pipeline_ready || readiness.ready || (primary && pipelineReadyOf(primary, group)))) {
      if (!missing.length) blockers.push({ kind: "pipeline", label: "管线未配置完整", field: "" });
    }
    if (readiness.can_trigger_build === false && readiness.checks && readiness.checks.build_node === false) {
      if (!blockers.some((b) => String(b.label).includes("构建节点"))) {
        blockers.push({ kind: "jenkins", label: "构建节点离线，无法触发打包", field: "" });
      }
    }
    if (!primary) {
      blockers.push({ kind: "vc", label: "当前交付线缺少 VersionCode", field: "" });
    }
    const payload = order?.payload || {};
    const planVals = {
      owner: String(payload.owner || order?.created_by || "").trim(),
      reason: String(order?.reason || payload.reason || "").trim(),
      release_window: String(payload.release_window || "").trim(),
      release_description: String(payload.release_description || "").trim(),
    };
    const env = String(primary?.env_key || group?.env_key || activeEnvKey() || "development");
    const required = ["owner", "reason"];
    if (["staging", "production", "canary"].includes(env)) required.push("release_window", "release_description");
    required.forEach((field) => {
      if (!planVals[field]) {
        blockers.push({ kind: "plan", label: `${planFieldLabels[field] || field}未填写`, field });
      }
    });
    return blockers;
  };

  const buildJourneyHref = (group, primary) => {
    const env = group.env_key || activeEnvKey() || envKey || "development";
    const channel = channelFilterValue() || (primary ? channelIdOf(primary) : "") || "1001";
    const platform = group.platform || activePlatform() || (primary?.platform || "android");
    const qs = new URLSearchParams({ platform, detail: "1" });
    if (primary?.id) qs.set("version_id", primary.id);
    return withReturnTo(`/admin/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(env)}/channels/${encodeURIComponent(channel)}/build?${qs}`);
  };

  const deriveGroupPipeline = (group, children) => {
    const channelGate = channelFilterValue();
    const scoped = channelGate ? children.filter((row) => channelIdOf(row) === channelGate) : children;
    const primary = pickPrimaryVc(scoped);
    const readiness = group?.pipeline_readiness || {};
    const pipelineOk = Boolean(group.pipeline_ready) || (primary ? pipelineReadyOf(primary, group) : false);
    const canTriggerBuild = readiness.can_trigger_build !== undefined
      ? Boolean(readiness.can_trigger_build)
      : (Boolean(group.can_trigger_build) || pipelineOk);
    const hasVc = scoped.length > 0;
    const order = primary ? releaseOrderByVersion.get(String(primary.id || "")) : null;
    const orderStatus = String(order?.status || "");
    const building = primary ? isBuildInProgress(primary) : false;
    const artifactOk = Boolean(primary && primary.apk_status === "found") || orderStatus === "artifacts_ready";
    const buildFailed = Boolean(
      primary && !building && !artifactOk && (orderStatus === "failed" || orderStatus === "build_failed" || primary.version_status === "disabled"),
    );
    const published = Boolean(primary?.active_bundle_id) || ["published", "verified"].includes(orderStatus);
    const accept = acceptanceOf(primary);
    const accepted = published || accept.status === "passed";
    const acceptFailed = !published && accept.status === "failed";
    const prepareBlockers = collectPrepareBlockers(group, primary, order);
    const prepareReady = prepareBlockers.length === 0 && canTriggerBuild && hasVc && pipelineOk;
    const prepareStatus = prepareReady ? "success" : "failed";
    const buildComplete = Boolean(published || artifactOk);
    let buildStatus = "pending";
    if (building) buildStatus = "running";
    else if (buildFailed) buildStatus = "failed";
    else if (buildComplete) buildStatus = "success";
    else if (prepareReady) buildStatus = "current";
    let verifyStatus = "pending";
    if (accepted) verifyStatus = "success";
    else if (acceptFailed) verifyStatus = "failed";
    else if (buildStatus === "success") verifyStatus = "current";
    let releaseStatus = "pending";
    if (published) releaseStatus = "success";
    else if (verifyStatus === "success") releaseStatus = "current";
    const prepareDesc = prepareReady
      ? "准备完成，可进入打包"
      : (prepareBlockers.slice(0, 2).map((b) => b.label).join("；") || "请完善管线、Jenkins 与发版必填项");
    const steps = [
      {
        id: "prepare",
        label: "准备",
        status: prepareStatus,
        desc: prepareDesc,
        blockers: prepareBlockers,
      },
      {
        id: "build",
        label: "打包",
        status: buildStatus,
        desc: building
          ? "Jenkins 构建中，需完整跑完准备阶段启用的步骤"
          : (buildFailed
            ? "打包未完整成功，请修复后重试"
            : (buildComplete ? "产物已就绪，可进入验收" : "触发并完成完整打包流程")),
      },
      {
        id: "verify",
        label: "验收",
        status: verifyStatus,
        desc: accepted
          ? "已通过验收"
          : (acceptFailed ? "验收未通过，请修复后重验" : (buildComplete ? "基于完整产物进行测试并标记结果" : "等待完整打包产物")),
      },
      {
        id: "release",
        label: "上线",
        status: releaseStatus,
        desc: published ? "已发布到线上" : (verifyStatus === "success" ? "填写上线信息并发布" : "验收通过后可上线"),
      },
    ];
    // 上一步未完成则锁定；已有进度的节点仍可回看。
    const openIndex = steps.findIndex((step) => step.status !== "success");
    const currentIndex = openIndex < 0 ? steps.length - 1 : openIndex;
    steps.forEach((step, index) => {
      if (index === 0) {
        step.locked = false;
        return;
      }
      const prevOk = steps[index - 1].status === "success";
      step.locked = !prevOk && step.status === "pending";
    });
    const current = steps[currentIndex] || steps[steps.length - 1];
    return {
      steps,
      current,
      primary,
      scoped,
      pipelineOk,
      canTriggerBuild,
      prepareReady,
      prepareBlockers,
      hasVc,
      building,
      artifactOk,
      buildFailed,
      published,
      accepted,
      acceptFailed,
      order,
    };
  };

  const groupPrimaryAction = (group, children, pipe) => {
    const { current, primary, pipelineOk, hasVc, building, buildFailed, published, accepted, prepareBlockers } = pipe;
    if (current.id === "prepare") {
      const needPipeline = !pipelineOk || prepareBlockers.some((b) => b.kind === "pipeline" || b.kind === "jenkins");
      if (needPipeline) {
        return {
          label: canEdit ? "去修正配置" : "查看管线",
          href: groupBuildConfigHref(group, children, { highlightGate: true }),
          warn: true,
        };
      }
      if (!hasVc) return { label: "添加 VersionCode", action: "add_vc", version_name: group.version_name };
      return { label: "修正发版信息", action: "edit_release", version_id: primary.id, highlight: true, warn: true };
    }
    if (current.id === "build") {
      if (building && primary) return { label: "查看打包进度", href: buildJourneyHref(group, primary) };
      if (buildFailed && primary) return { label: "进入打包流程", href: buildJourneyHref(group, primary), warn: true };
      if (primary) return { label: "进入打包流程", href: buildJourneyHref(group, primary) };
      return { label: "添加 VersionCode", action: "add_vc", version_name: group.version_name };
    }
    if (current.id === "verify") {
      if (primary) return { label: accepted ? "查看验收" : "产物验收", action: "open_accept", version_id: primary.id };
      return { label: "添加 VersionCode", action: "add_vc", version_name: group.version_name };
    }
    if (published && primary) return { label: "查看上线信息", action: "edit_release", version_id: primary.id };
    if (primary) return { label: "填写上线信息", action: "edit_release", version_id: primary.id };
    return { label: "添加 VersionCode", action: "add_vc", version_name: group.version_name };
  };

  const openAcceptDialog = (versionId) => {
    const row = rows.find((item) => String(item.id) === String(versionId));
    const mask = document.getElementById("vgpAcceptMask");
    const body = document.getElementById("vgpAcceptBody");
    if (!row || !mask || !body) return toast("请先选择 VersionCode", "error");
    const env = normalizedEnv(row);
    const historyHref = scopeHref(`/admin/projects/${projectId}/build-history`, {
      env_key: env,
      channel_id: channelIdOf(row),
      platform: row.platform || "",
      version_id: row.id,
    }, { scoped: "1" });
    const accept = acceptanceOf(row);
    const artifactOk = row.apk_status === "found";
    body.innerHTML = `<div class="vgp-vc-row">
        <div class="vgp-vc-main">
          <strong>${esc(row.version_name || "")} / VC ${esc(row.version_code || "-")}</strong>
          ${versionStatusHtml(row)}
          ${artifactStatusHtml(row)}
          ${latestBuildHtml(row)}
        </div>
      </div>
      <p>当前验收状态：<strong>${esc({ pending: "待验收", passed: "已通过", failed: "未通过" }[accept.status] || accept.status)}</strong>${accept.updated_at ? ` · ${esc(String(accept.updated_at).replace("T", " ").slice(0, 19))}` : ""}</p>
      <div class="vgp-accept-actions" style="justify-content:flex-start">
        <a class="vgp-link" href="${esc(historyHref)}">打开构建与产物</a>
        <a class="vgp-link" href="${esc(buildJourneyHref({ env_key: env, platform: row.platform }, row))}">打包流程</a>
        ${artifactOk ? `<button type="button" class="vgp-link" data-download-apk="${esc(row.id)}">下载产物</button>` : '<span class="vgp-hint">暂无产物可下载</span>'}
      </div>`;
    mask.hidden = false;
    mask.dataset.versionId = String(row.id || "");
    document.getElementById("vgpAcceptPass").disabled = !canEdit || (!artifactOk && !row.active_bundle_id);
    document.getElementById("vgpAcceptFail").disabled = !canEdit;
  };

  const closeAcceptDialog = () => {
    const mask = document.getElementById("vgpAcceptMask");
    if (mask) {
      mask.hidden = true;
      delete mask.dataset.versionId;
    }
  };

  const submitAcceptance = async (status) => {
    const mask = document.getElementById("vgpAcceptMask");
    const vid = mask?.dataset.versionId || "";
    if (!vid) return;
    try {
      const data = await request(`/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(vid)}/client-acceptance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (data?.ok === false) throw new Error(data.error || "验收提交失败");
      const row = rows.find((item) => String(item.id) === String(vid));
      if (row) row.client_acceptance = data?.data?.client_acceptance || { status };
      toast(status === "passed" ? "已标记验收通过" : status === "failed" ? "已标记验收不通过" : "已更新验收状态");
      closeAcceptDialog();
      render();
    } catch (error) {
      toast(error.message || "验收提交失败", "error");
    }
  };

  const enterPipelineStep = (groupName, stepId) => {
    const group = versionGroups.find((item) => item.version_name === groupName);
    if (!group) return;
    const platformGate = activePlatform();
    const children = rows.filter((row) => {
      if ((row.version_name || "") !== groupName) return false;
      if (platformGate && row.platform !== platformGate) return false;
      const channelGate = channelFilterValue();
      if (channelGate && channelIdOf(row) !== channelGate) return false;
      const envGate = lockEnvKey || document.getElementById("versionEnv")?.value || "";
      if (envGate && normalizedEnv(row) !== envGate) return false;
      return true;
    });
    const pipe = deriveGroupPipeline(group, children);
    const step = pipe.steps.find((item) => item.id === stepId);
    if (!step) return;
    if (step.locked) {
      toast("请先完成上一步，再进入该流程", "error");
      return;
    }
    if (stepId === "prepare") {
      const needPipelineFix = !pipe.pipelineOk || pipe.prepareBlockers.some((b) => b.kind === "pipeline" || b.kind === "jenkins");
      if (needPipelineFix) {
        if (pipe.prepareBlockers.length) {
          toast(`准备未就绪：${pipe.prepareBlockers.slice(0, 3).map((b) => b.label).join("；")}`, "error");
        }
        location.href = groupBuildConfigHref(group, children, { highlightGate: true });
        return;
      }
      if (!pipe.primary) return openVersionDialog(groupName);
      if (window.VersionReleaseEditor) {
        window.VersionReleaseEditor.open(pipe.primary, {
          highlightFields: pipe.prepareBlockers.filter((b) => b.field).map((b) => b.field),
          blockers: pipe.prepareBlockers,
        });
      } else openVcDrawer(pipe.primary);
      return;
    }
    if (stepId === "build") {
      if (pipe.prepareReady === false) {
        toast("请先完成准备节点全部校验，再进入打包", "error");
        return;
      }
      if (!pipe.primary) return openVersionDialog(groupName);
      location.href = buildJourneyHref(group, pipe.primary);
      return;
    }
    if (stepId === "verify") {
      if (pipe.steps.find((s) => s.id === "build")?.status !== "success") {
        toast("请先完成完整打包并产出可测产物，再进入验收", "error");
        return;
      }
      if (!pipe.primary) return openVersionDialog(groupName);
      openAcceptDialog(pipe.primary.id);
      return;
    }
    if (stepId === "release") {
      if (!pipe.primary) return openVersionDialog(groupName);
      if (pipe.steps.find((s) => s.id === "verify")?.status !== "success") {
        toast("请先完成验收，再进入上线", "error");
        return;
      }
      if (window.VersionReleaseEditor) window.VersionReleaseEditor.open(pipe.primary);
      else openVcDrawer(pipe.primary);
    }
  };

  const groupRowHtml = (group, children) => {
    const groupName = group.version_name;
    const pipe = deriveGroupPipeline(group, children);
    const primaryAct = groupPrimaryAction(group, children, pipe);
    const buildConfigHref = groupBuildConfigHref(group, children);
    const env = group.env_key || activeEnvKey() || envKey || "development";
    const channel = channelFilterValue() || (pipe.primary ? channelIdOf(pipe.primary) : "") || "";
    const platform = group.platform || activePlatform() || "android";
    const historyHref = scopeHref(`/admin/projects/${projectId}/build-history`, {
      env_key: env,
      channel_id: channel,
      platform,
      version_id: pipe.primary?.id || "",
      version_name: groupName,
    }, { scoped: "1" });
    const stepsHtml = pipe.steps.map((step, index) => {
      const cls = ["success", "running", "failed", "current", "pending"].includes(step.status) ? step.status : "pending";
      const lockedCls = step.locked ? " is-locked" : "";
      return `<button type="button" class="vgp-step is-${esc(cls)}${lockedCls}" data-vgp-step="${esc(step.id)}" data-group="${esc(groupName)}" ${step.locked ? 'aria-disabled="true"' : ""}>
        <span class="vgp-step-index">0${index + 1}</span>
        <strong class="vgp-step-name">${esc(step.label)}</strong>
        <span class="vgp-step-desc">${esc(step.desc)}</span>
        <span class="vgp-step-status">${esc({
          success: "已完成",
          running: "进行中",
          failed: step.id === "prepare" ? "待修正" : (step.id === "verify" ? "未通过" : "失败"),
          current: "当前 · 可进入",
          pending: step.locked ? "未解锁" : "未开始",
        }[step.status] || step.status)}</span>
      </button>`;
    }).join("");
    let primaryBtn = "";
    if (primaryAct.href) {
      primaryBtn = `<a class="vgp-primary${primaryAct.warn ? " is-warn" : ""}" href="${esc(primaryAct.href)}">${esc(primaryAct.label)}</a>`;
    } else if (primaryAct.action === "quick_build" && primaryAct.version_id) {
      primaryBtn = `<button type="button" class="vgp-primary${primaryAct.warn ? " is-warn" : ""}" data-quick-build="${esc(primaryAct.version_id)}">${esc(primaryAct.label)}</button>`;
    } else {
      primaryBtn = `<button type="button" class="vgp-primary${primaryAct.warn ? " is-warn" : ""}" data-vgp-action="${esc(primaryAct.action || "")}" data-version-id="${esc(primaryAct.version_id || "")}" data-version-name="${esc(primaryAct.version_name || groupName)}" data-group="${esc(groupName)}" data-highlight="${primaryAct.highlight ? "1" : "0"}">${esc(primaryAct.label)}</button>`;
    }
    const vcCollapsed = !expandedVcGroups.has(groupName);
    const vcRows = pipe.scoped.length
      ? pipe.scoped.slice(0, 6).map((row) => `<div class="vgp-vc-row">
          <div class="vgp-vc-main">
            <strong>VC ${esc(row.version_code || "-")}</strong>
            ${versionStatusHtml(row)}
            ${latestBuildHtml(row)}
          </div>
          <div class="vgp-vc-actions">
            <button type="button" class="version-btn neutral compact" data-open-vc-row="${esc(row.id || "")}">详情</button>
            ${canEdit ? `<button type="button" class="version-btn build compact" data-quick-build="${esc(row.id || "")}">构建</button>` : ""}
            <button type="button" class="version-btn release compact" data-edit-release="${esc(row.id || "")}">发版</button>
          </div>
        </div>`).join("")
      : `<div class="version-empty-inline">该交付线尚无 VersionCode。<button type="button" class="version-link-btn" data-add-vc="${esc(groupName)}">立即添加</button></div>`;
    const metaParts = [
      statusLabels[group.status] || group.status || "有效",
      platformLabelOf(platform),
      channel ? channelNameOf(channel) : "全部渠道",
      `${pipe.scoped.length} 个 VC`,
    ];
    const cardCollapsed = !expandedPipelines.has(groupName);
    const currentHint = `${pipe.current.label} · ${pipe.current.desc}`;
    return `<article class="vgp-card${cardCollapsed ? " is-collapsed" : ""}" data-group="${esc(groupName)}">
      <div class="vgp-side" aria-hidden="true">客户端</div>
      <div class="vgp-main">
        <div class="vgp-top">
          <div class="vgp-title">
            <div class="vgp-title-row">
              <button type="button" class="vgp-card-toggle" data-toggle-pipeline="${esc(groupName)}" aria-expanded="${cardCollapsed ? "false" : "true"}" aria-label="${cardCollapsed ? "展开管线" : "折叠管线"}">
                <img src="/static/project_ui/svg/action_next.svg" alt="">
              </button>
              <strong>${esc(groupName)}</strong>
              <span class="pm-tag pm-tag--muted">版本组</span>
              ${group.pipeline_ready ? '<span class="version-pill pipeline-ready">管线就绪</span>' : '<span class="version-pill pipeline-missing">管线未配置</span>'}
              ${cardCollapsed ? `<span class="vgp-hint">当前：${esc(currentHint)}</span>` : ""}
            </div>
            <div class="vgp-meta">${esc(metaParts.join(" · "))}</div>
          </div>
          <div class="vgp-links">
            <a class="vgp-link" href="${esc(buildConfigHref)}">配置管线</a>
            <a class="vgp-link" href="${esc(historyHref)}">发版记录</a>
            <a class="vgp-link" href="${esc(historyHref)}">产物</a>
            ${canEdit ? `<button type="button" class="vgp-link" data-edit-group="${esc(groupName)}">编辑</button>
            <button type="button" class="vgp-link is-danger" data-delete-group="${esc(groupName)}">删除</button>` : ""}
          </div>
        </div>
        <div class="vgp-body">
          <div class="vgp-track" aria-label="发版四步">${stepsHtml}</div>
          <div class="vgp-foot">
            ${primaryBtn}
            <span class="vgp-hint">当前：${esc(currentHint)}</span>
          </div>
          <div class="vgp-vc${vcCollapsed ? " is-collapsed" : ""}" data-vc-panel="${esc(groupName)}">
            <div class="vgp-vc-head">
              <div class="vgp-vc-head-left">
                <button type="button" class="vgp-vc-toggle" data-toggle-vc-panel="${esc(groupName)}" aria-expanded="${vcCollapsed ? "false" : "true"}">
                  <img src="/static/project_ui/svg/action_next.svg" alt="">本交付线 VersionCode
                </button>
                <span class="vgp-hint">${pipe.scoped.length} 个</span>
              </div>
              <button type="button" class="version-link-btn" data-add-vc="${esc(groupName)}">添加 VC</button>
            </div>
            <div class="vgp-vc-list">${vcRows}</div>
          </div>
        </div>
      </div>
    </article>`;
  };

  const emptyListHtml = (platformGate, channelGate) => {
    if (channelGate && platformGate) {
      return `<div class="vgp-empty">当前交付线（${esc(channelNameOf(channelGate))} · ${esc(platformLabelOf(platformGate))}）还没有版本组。<br>请先「新建版本组」，再按 准备 → 打包 → 验收 → 上线 推进。</div>`;
    }
    if (envScoped) {
      return `<div class="vgp-empty">本环境${platformGate ? ` · ${esc(platformLabelOf(platformGate))}` : ""}尚无版本组。请先「新建版本组」。</div>`;
    }
    return '<div class="vgp-empty">当前筛选条件下暂无版本组。</div>';
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
      : emptyListHtml(platformGate, document.getElementById("versionChannel")?.value || "");
    document.querySelectorAll("[data-edit-group]").forEach((button) => {
      button.onclick = () => openGroupDialog(button.dataset.editGroup);
    });
    document.querySelectorAll("[data-delete-group]").forEach((button) => {
      button.onclick = () => deleteGroup(button.dataset.deleteGroup);
    });
    document.querySelectorAll("[data-add-vc]").forEach((button) => {
      button.onclick = () => openVersionDialog(button.dataset.addVc);
    });
    document.querySelectorAll("[data-vgp-action]").forEach((button) => {
      button.onclick = () => {
        const action = button.getAttribute("data-vgp-action") || "";
        const vid = button.getAttribute("data-version-id") || "";
        const vname = button.getAttribute("data-version-name") || "";
        if (action === "add_vc") return openVersionDialog(vname);
        if (action === "open_accept") return openAcceptDialog(vid);
        if (action === "edit_release") {
          const row = rows.find((item) => String(item.id) === vid);
          const gname = button.getAttribute("data-group") || row?.version_name || "";
          const group = versionGroups.find((item) => item.version_name === gname);
          const children = rows.filter((item) => (item.version_name || "") === gname);
          const pipe = group ? deriveGroupPipeline(group, children) : null;
          const opts = button.getAttribute("data-highlight") === "1" || (pipe && !pipe.prepareReady)
            ? {
                highlightFields: (pipe?.prepareBlockers || []).filter((b) => b.field).map((b) => b.field),
                blockers: pipe?.prepareBlockers || [],
              }
            : {};
          if (row && window.VersionReleaseEditor) window.VersionReleaseEditor.open(row, opts);
          else if (row) openVcDrawer(row);
        }
      };
    });
    document.querySelectorAll("[data-vgp-step]").forEach((button) => {
      button.onclick = () => {
        enterPipelineStep(button.getAttribute("data-group") || "", button.getAttribute("data-vgp-step") || "");
      };
    });
    document.querySelectorAll("[data-toggle-vc-panel]").forEach((button) => {
      button.onclick = () => {
        const name = button.getAttribute("data-toggle-vc-panel") || "";
        if (!name) return;
        if (expandedVcGroups.has(name)) expandedVcGroups.delete(name);
        else expandedVcGroups.add(name);
        render();
      };
    });
    document.querySelectorAll("[data-toggle-pipeline]").forEach((button) => {
      button.onclick = () => {
        const name = button.getAttribute("data-toggle-pipeline") || "";
        if (!name) return;
        if (expandedPipelines.has(name)) expandedPipelines.delete(name);
        else expandedPipelines.add(name);
        render();
      };
    });
    document.querySelectorAll("[data-download-apk]").forEach((button) => {
      button.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        handleDownloadClick(button.getAttribute("data-download-apk") || "");
      };
    });
    document.querySelectorAll("[data-edit-release]").forEach((button) => {
      button.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        const vid = button.getAttribute("data-edit-release") || "";
        const row = rows.find((item) => String(item.id) === vid);
        if (row && window.VersionReleaseEditor) window.VersionReleaseEditor.open(row);
      };
    });
    document.querySelectorAll("[data-open-vc-row]").forEach((button) => {
      button.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        const vid = button.getAttribute("data-open-vc-row") || "";
        const row = rows.find((item) => String(item.id) === vid);
        if (row) openVcDrawer(row);
      };
    });
    document.querySelectorAll("[data-download-pick]").forEach((button) => {
      button.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        const groupName = button.getAttribute("data-download-pick") || "";
        const platformGate = activePlatform();
        const channelGate = document.getElementById("versionChannel")?.value || "";
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
    updateBuildJourneyLink();
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
      const current = selectedChannelId || filterChannel.value;
      suppressChannelChange = true;
      filterChannel.innerHTML = '<option value="">全部渠道</option>' + channels.map((x) => `<option value="${esc(x.channel_id)}">${esc(x.channel_name)}</option>`).join("");
      if (current && channels.some((x) => String(x.channel_id) === String(current))) filterChannel.value = current;
      else filterChannel.value = "";
      selectedChannelId = filterChannel.value || "";
      filterChannel.disabled = Boolean(lockDeliveryLine);
      suppressChannelChange = false;
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

  const applyLineSelection = ({ channel_id = "", platform = "" } = {}) => {
    selectedChannelId = channel_id || "";
    activePlatformKey = platform || "";
    const channelSelect = document.getElementById("versionChannel");
    if (channelSelect) channelSelect.value = selectedChannelId;
    root.classList.toggle("is-channel-scoped", Boolean(selectedChannelId && activePlatformKey));
  };

  const applyEnvScopedUi = () => {
    if (lockEnvKey) root.classList.add("is-env-scoped");
    const envSelect = document.getElementById("versionEnv");
    if (envSelect && lockEnvKey) envSelect.value = lockEnvKey;
    const channelSelect = document.getElementById("versionChannel");
    if (lockDeliveryLine) {
      root.classList.add("is-channel-scoped");
      if (channelSelect) {
        channelSelect.value = lockChannelId;
        channelSelect.disabled = true;
        channelSelect.classList.add("is-locked");
      }
      activePlatformKey = lockPlatform || activePlatformKey;
      return;
    }
    applyLineSelection({ channel_id: lockChannelId, platform: lockPlatform });
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
    const seq = ++loadSeq;
    try {
      const envFilterValue = lockEnvKey || document.getElementById("versionEnv")?.value || envKey || "";
      const [versionData, groupData, context, releaseOrdersRes] = await Promise.all([
        request(`/admin/projects/${projectId}/versions/list`),
        request(versionGroupsUrl()),
        request(contextOptionsUrl(envFilterValue)),
        request(`/api/projects/${projectId}/release-orders`).catch(() => ({ data: [] })),
      ]);
      if (seq !== loadSeq) return;
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
      const filterChannel = document.getElementById("versionChannel");
      if (filterChannel && !envFilterValue) {
        const uniq = new Map();
        rows.forEach((row) => {
          const cid = channelIdOf(row);
          if (cid) uniq.set(cid, channelNameOf(cid));
        });
        const current = filterChannel.value;
        filterChannel.innerHTML = '<option value="">全部渠道</option>' + [...uniq.entries()].map(([cid, name]) => `<option value="${esc(cid)}">${esc(name)}</option>`).join("");
        if (current && (current === "" || uniq.has(current))) filterChannel.value = current;
        filterChannel.disabled = Boolean(lockDeliveryLine);
      }
      renderPlatformTabs();
      refreshVersionNameSelect();
      render();
      syncScopeUrl();
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
  document.getElementById("btnRefreshVersions").onclick = () => {
    root.dispatchEvent(new CustomEvent("vw-matrix-refresh"));
    load().catch((error) => toast(error.message, "error"));
  };

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
      banner.textContent = "请先在「环境配置」中选择要操作的交付环境，再进入版本与管线。";
    } else if (hint === "use_versions_hub") {
      banner.textContent = "下载与产物管理已并入版本与管线。请在本环境筛选 VersionCode，使用行内「下载」或顶部「构建与产物」。";
    } else if (hint === "pick_vc") {
      banner.textContent = error
        ? `无法继续：${error}。请先配置版本组管线，再使用行内「触发构建」或「继续发版」。`
        : "请在本页选择 VersionCode，使用行内「触发构建」或「继续发版」。";
    } else {
      return;
    }
    panel.insertBefore(banner, panel.firstChild);
  };

  document.getElementById("vgpAcceptClose")?.addEventListener("click", closeAcceptDialog);
  document.getElementById("vgpAcceptPass")?.addEventListener("click", () => submitAcceptance("passed"));
  document.getElementById("vgpAcceptFail")?.addEventListener("click", () => submitAcceptance("failed"));
  document.getElementById("vgpAcceptMask")?.addEventListener("click", (event) => {
    if (event.target === event.currentTarget) closeAcceptDialog();
  });

  const syncMatrixCollapse = () => {
    const section = document.getElementById("vwMatrixSection");
    const toggle = document.getElementById("vwMatrixToggle");
    if (!section || !toggle) return;
    section.classList.toggle("is-collapsed", !matrixExpanded);
    toggle.setAttribute("aria-expanded", matrixExpanded ? "true" : "false");
  };
  document.getElementById("vwMatrixToggle")?.addEventListener("click", () => {
    matrixExpanded = !matrixExpanded;
    syncMatrixCollapse();
  });
  syncMatrixCollapse();

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
  if (envFilter) {
    if (lockEnvKey) envFilter.value = lockEnvKey;
    envFilter.addEventListener("change", () => {
      const env = envFilter.value || "development";
      location.href = `/admin/projects/${encodeURIComponent(projectId)}/versions?env_key=${encodeURIComponent(env)}`;
    });
  }

  document.getElementById("versionChannel")?.addEventListener("change", () => {
    if (lockDeliveryLine || suppressChannelChange) return;
    selectedChannelId = document.getElementById("versionChannel")?.value || "";
    listPage = 1;
    syncScopeUrl();
    render();
  });

  root.addEventListener("vw-select-line", async (event) => {
    const detail = event.detail || {};
    applyLineSelection({
      channel_id: detail.channel_id || "",
      platform: detail.platform || "",
    });
    listPage = 1;
    syncScopeUrl();
    try {
      await load();
    } catch (error) {
      toast(error.message, "error");
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!canEdit) return;
    const versionNameSelect = document.getElementById("versionNameSelect");
    if (versionNameSelect?.value === "__new__") {
      toast("请先创建版本组", "error");
      return;
    }
    try {
      const payload = buildVersionFormPayload();
      const result = await request(`/admin/projects/${projectId}/versions/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
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
      const createdVersion = result.version || (result.versions && result.versions[0]) || rows.find((r) => String(r.version_code) === String(payload.version_code));
      const target = createdVersion || rows.find((r) => String(r.id) === String(result.version_id || ""));
      if (target && window.VersionReleaseEditor) {
        window.VersionReleaseEditor.open({ ...target, release_order_id: releaseOrderByVersion.get(String(target.id))?.release_order_id });
      }
    } catch (error) {
      toast(error.message, "error");
    }
  });

  window.__versionToast = toast;
  window.__versionReload = load;

  load()
    .then(async () => {
      if (createVcAction && canEdit) {
        await openVersionDialog();
        urlParams.delete("action");
        const qs = urlParams.toString();
        history.replaceState({}, "", qs ? `${location.pathname}?${qs}` : location.pathname);
      }
      const editReleaseId = urlParams.get("version_id");
      if (urlParams.get("action") === "edit_release" && editReleaseId) {
        const row = rows.find((item) => String(item.id) === editReleaseId);
        if (row && window.VersionReleaseEditor) {
          window.VersionReleaseEditor.open(row);
          urlParams.delete("action");
          const qs = urlParams.toString();
          history.replaceState({}, "", qs ? `${location.pathname}?${qs}` : location.pathname);
        }
      }
      if (urlParams.get("action") === "open_build" || urlParams.get("action") === "focus_build") {
        const buildId = urlParams.get("version_id") || "";
        const row = buildId
          ? rows.find((item) => String(item.id) === buildId)
          : rows[0];
        if (row) {
          const card = root.querySelector(`.vgp-card[data-group="${CSS.escape(String(row.version_name || ""))}"]`)
            || root.querySelector(".vgp-card");
          if (card) {
            card.scrollIntoView({ behavior: "smooth", block: "center" });
            card.classList.add("is-focus-build");
            const buildNode = card.querySelector('[data-step="build"], .vgp-step[data-id="build"]');
            if (buildNode) buildNode.classList.add("is-pulse");
          }
          toast("已定位到打包节点；需要进度详情时再点「进入打包流程」", "info");
        }
        urlParams.delete("action");
        const qs = urlParams.toString();
        history.replaceState({}, "", qs ? `${location.pathname}?${qs}` : location.pathname);
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
    const releaseBtn = event.target.closest("[data-release-action]");
    if (releaseBtn) {
      event.preventDefault();
      event.stopPropagation();
      document.querySelectorAll(".version-row-more-dropdown.open").forEach((node) => node.classList.remove("open"));
      const vid = releaseBtn.getAttribute("data-version-id") || "";
      const action = releaseBtn.getAttribute("data-release-action") || "";
      const row = rows.find((item) => String(item.id) === vid);
      if (!row || !window.VersionReleaseEditor) return;
      const apiAction = action === "server-pause" ? "server-maintenance" : action;
      if (action === "edit") {
        window.VersionReleaseEditor.open(row);
        return;
      }
      window.VersionReleaseEditor.runRowAction(row, apiAction, { tab: action === "announce" ? "announce" : "" }).catch((error) => toast(error.message || "操作失败", "error"));
      return;
    }
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
    const channelGate = document.getElementById("versionChannel")?.value || "";
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
