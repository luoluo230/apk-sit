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
  const lockChannelId = urlParams.get("channel_id") || "";
  const lockPlatform = urlParams.get("platform") || "";
  const lockEnvKey = urlParams.get("env_key") || "";
  const lockDeliveryLine = urlParams.get("action") === "create_vc" && lockChannelId && lockPlatform;
  const envScoped = Boolean(lockEnvKey);
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
  const useAllEnvChannels = () => Boolean(activeEnvKey() && activePlatform() && !lockDeliveryLine);
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

  const formatFileSize = (bytes) => {
    const n = Number(bytes || 0);
    if (!n) return "";
    if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MB`;
    if (n >= 1024) return `${Math.round(n / 1024)} KB`;
    return `${n} B`;
  };

  const openDownloadDialog = (row, downloadInfo = null) => {
    const dialog = document.getElementById("versionDownloadDialog");
    const body = document.getElementById("versionDownloadBody");
    const title = document.getElementById("versionDownloadTitle");
    const subtitle = document.getElementById("versionDownloadSubtitle");
    if (!dialog || !body) {
      toast("下载弹窗未加载，请刷新页面后重试", "error");
      return;
    }
    const apkDl = downloadInfo && typeof downloadInfo === "object"
      ? downloadInfo
      : (row?.apk_download && typeof row.apk_download === "object" ? row.apk_download : {});
    const publicUrl = apkDl.public_download_url || apkDl.oss_download_url || "";
    const publicQr = apkDl.public_qr_dataurl || apkDl.oss_qr_dataurl || "";
    const localUrl = apkDl.local_download_url || "";
    const localQr = apkDl.local_qr_dataurl || "";
    const publicHint = apkDl.public_download_hint || "";
    const publicReachable = Boolean(apkDl.public_download_reachable);
    const scope = row
      ? [
        envLabels[normalizedEnv(row)] || normalizedEnv(row),
        row.channel_name || row.channel_label || channelNameOf(channelIdOf(row)),
        row.platform_label || row.platform || "-",
      ].join(" · ")
      : "";
    title.textContent = row
      ? `${row.version_name || "-"} · VC ${row.version_code || "-"}`
      : "安装包下载";
    subtitle.textContent = scope ? `${scope} · 外网下载与扫码安装` : "外网下载链接与二维码（可分享给他人）";
    if (!publicUrl && !localUrl) {
      body.innerHTML = `<div class="version-download-empty"><strong>暂无可下载的安装包</strong><p>请先完成构建并成功归档 APK。</p></div>`;
    } else if (!publicUrl) {
      body.innerHTML = `<div class="version-download-empty"><strong>外网下载暂不可用</strong><p>${esc(publicHint || "请配置 ADMIN_PUBLIC_URL 或 OSS_CUSTOM_DOMAIN")}</p>${localUrl ? `<p class="version-download-meta">本机测试：<a href="${esc(localUrl)}" target="_blank" rel="noopener">${esc(localUrl)}</a></p>` : ""}</div>`;
    } else {
      const cards = [
        `<article class="version-download-tile version-download-tile-primary"><h3>外网下载</h3><p class="version-download-url">${esc(publicUrl)}</p><div class="version-download-actions"><a class="version-btn primary" href="${esc(publicUrl)}" target="_blank" rel="noopener">打开链接</a>${publicQr ? `<img class="version-download-qr" src="${esc(publicQr)}" alt="外网下载二维码">` : ""}</div>${publicHint ? `<p class="version-download-meta">${esc(publicHint)}</p>` : ""}</article>`,
      ];
      if (localUrl && localUrl !== publicUrl) {
        cards.push(`<article class="version-download-tile"><h3>本机 / 内网测试</h3><p class="version-download-url">${esc(localUrl)}</p><div class="version-download-actions"><a class="version-btn" href="${esc(localUrl)}" target="_blank" rel="noopener">打开链接</a>${localQr ? `<img class="version-download-qr" src="${esc(localQr)}" alt="本机下载二维码">` : ""}</div></article>`);
      }
      const meta = [
        apkDl.build_time ? `归档 ${apkDl.build_time}` : "",
        apkDl.build_number ? `构建 #${apkDl.build_number}` : "",
        formatFileSize(apkDl.size_bytes),
        publicReachable ? "外网可达" : "外网未配置",
      ].filter(Boolean).join(" · ");
      body.innerHTML = `<div class="version-download-grid">${cards.join("")}</div>${meta ? `<p class="version-download-meta">${esc(meta)}</p>` : ""}`;
    }
    dialog.classList.remove("is-hidden");
    dialog.setAttribute("aria-hidden", "false");
    if (dialog.parentElement !== document.body) {
      document.body.appendChild(dialog);
    }
  };

  const handleDownloadClick = async (versionId) => {
    const vid = String(versionId || "").trim();
    if (!vid) {
      toast("缺少 VersionCode 标识，无法下载", "error");
      return;
    }
    let row = rows.find((item) => String(item.id || "") === vid);
    const dialog = document.getElementById("versionDownloadDialog");
    const body = document.getElementById("versionDownloadBody");
    if (dialog && body) {
      document.getElementById("versionDownloadTitle").textContent = row
        ? `${row.version_name || "-"} · VC ${row.version_code || "-"}`
        : "安装包下载";
      document.getElementById("versionDownloadSubtitle").textContent = "正在加载下载信息…";
      body.innerHTML = `<div class="version-download-empty"><strong>正在加载下载信息</strong><p>请稍候…</p></div>`;
      dialog.classList.remove("is-hidden");
      dialog.setAttribute("aria-hidden", "false");
      if (dialog.parentElement !== document.body) document.body.appendChild(dialog);
    }
    try {
      const data = await request(`/api/projects/${projectId}/versions/${encodeURIComponent(vid)}/apk-download-info`);
      const info = data && typeof data === "object" ? data : {};
      if (!info.local_download_url && !info.oss_download_url && !info.public_download_url) {
        if (body) {
          body.innerHTML = `<div class="version-download-empty"><strong>暂无可下载的安装包</strong><p>请先完成构建并成功归档 APK。</p></div>`;
        }
        toast("暂无可下载的安装包，请先完成构建归档", "error");
        return;
      }
      if (row) {
        row.apk_download = {
          ...(row.apk_download || {}),
          local_download_url: info.local_download_url || row.apk_download?.local_download_url,
          oss_download_url: info.oss_download_url || row.apk_download?.oss_download_url,
          local_qr_dataurl: info.local_qr_dataurl || row.apk_download?.local_qr_dataurl,
          oss_qr_dataurl: info.oss_qr_dataurl || row.apk_download?.oss_qr_dataurl,
          build_time: info.build_time || row.apk_download?.build_time,
          build_number: info.build_number || row.apk_download?.build_number,
          size_bytes: info.size_bytes || row.apk_download?.size_bytes,
        };
      } else {
        row = {
          id: vid,
          version_name: info.version_name || "",
          version_code: info.version_code || "",
          channel_name: info.channel_name || "",
          platform_label: info.platform_label || info.platform || "",
          env_key: info.env_key || "",
          apk_download: info,
        };
      }
      openDownloadDialog(row, info);
    } catch (error) {
      if (row && row.apk_status === "found") {
        openDownloadDialog(row);
        return;
      }
      if (body) {
        body.innerHTML = `<div class="version-download-empty"><strong>下载信息加载失败</strong><p>${esc(error.message || "请稍后重试")}</p></div>`;
      }
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
    if ((row.jenkins_job_id || (row.pipeline || {}).jenkins_job_id) && row.apk_status !== "found") return '<span class="version-pill building">构建中</span>';
    if (row.version_status === "disabled" || row.version_status === "archived") return '<span class="version-pill failed">构建失败</span>';
    const st = row.version_status || "draft";
    return `<span class="version-pill ${esc(st)}">${esc(row.version_status_label || statusLabels[st] || st)}</span>`;
  };
  const artifactStatusHtml = (row) => {
    if (row.apk_status === "found") return '<span class="version-artifact-status ready">完整</span>';
    if (row.jenkins_job_id) return '<span class="version-artifact-status pending">构建中</span>';
    return '<span class="version-artifact-status missing">产物不完整</span>';
  };
  const latestBuildHtml = (row) => {
    const num = row.build_number || row.jenkins_build_number || (row.pipeline || {}).last_build_number;
    if (num) return `<a class="version-build-link" href="/admin/projects/${projectId}/build-history?env_key=${encodeURIComponent(normalizedEnv(row))}&channel_id=${encodeURIComponent(channelIdOf(row))}&platform=${encodeURIComponent(row.platform || "")}&scoped=1">#${esc(num)}</a>`;
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
    const context = `env_key=${encodeURIComponent(normalizedEnv(row))}&channel_id=${encodeURIComponent(channelIdOf(row))}&platform=${encodeURIComponent(row.platform || "")}&version_id=${encodeURIComponent(row.id || "")}&version_name=${encodeURIComponent(row.version_name || "")}&version_code=${encodeURIComponent(row.version_code || "")}&scoped=1`;
    const workflowHref = row.id ? `/admin/projects/${projectId}/versions/${encodeURIComponent(row.id)}/workflow` : `/admin/projects/${projectId}/build-history?${context}`;
    let downloadInfo = row.apk_download || {};
    try {
      const data = await request(`/api/projects/${projectId}/versions/${encodeURIComponent(row.id)}/apk-download-info`);
      downloadInfo = { ...downloadInfo, ...data };
    } catch (_) { /* keep row data */ }
    const artifactReady = row.apk_status === "found" || downloadInfo.public_download_url || downloadInfo.local_download_url;
    body.innerHTML = `<div class="pm-drawer-tags">${versionNameTagHtml(row, null)}<span class="pm-tag pm-tag--muted">${esc(row.version_name || "")}</span><span class="pm-tag pm-tag--muted">${esc(normalizedEnv(row))}</span><span class="pm-tag pm-tag--muted">${esc(row.channel_name || channelNameOf(channelIdOf(row)))}</span><span class="pm-tag pm-tag--muted">${esc(row.platform_label || row.platform || "")}</span></div>
    <div class="pm-drawer-section"><h3>当前构建</h3><div class="pm-drawer-build-head"><strong>${artifactReady ? "已完成" : "构建中"}</strong>${latestBuildHtml(row)}</div>
    <div class="current-progress" style="height:6px;background:#eef1f6;border-radius:3px;margin:10px 0"><span style="display:block;height:100%;width:${artifactReady ? 100 : 10}%;background:#1677ff;border-radius:3px"></span></div>
    <p class="pm-drawer-hint">${artifactReady ? "产物已归档" : "构建进行中，请稍候刷新"}</p></div>
    <div class="pm-drawer-section"><h3>产物完整性</h3><div class="pm-drawer-meta"><div><span>状态</span><b>${artifactReady ? "完整" : "不完整"}</b></div><div><span>发布</span><b>${row.active_bundle_id ? "已发布" : "未发布"}</b></div></div></div>
    <div class="pm-drawer-section"><h3>关联发布单</h3><p class="pm-drawer-hint">${row.active_bundle_id ? "已有活跃 Bundle" : "暂无发布单"} · <a href="/admin/projects/${projectId}/release-orders/start?version_id=${encodeURIComponent(row.id)}">查看发布单</a></p></div>`;
    foot.innerHTML = `<a class="pm-btn" href="/admin/projects/${projectId}/release-orders/start?version_id=${encodeURIComponent(row.id)}">创建发布单</a>
      <a class="pm-btn pm-btn--primary" href="${workflowHref}">构建</a>
      <button class="pm-btn" type="button" data-download-apk="${esc(row.id)}">下载</button>
      <a class="pm-btn" href="/admin/projects/${projectId}/build-history?${context}">构建历史</a>`;
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

  const closeDownloadDialog = () => {
    const dialog = document.getElementById("versionDownloadDialog");
    if (!dialog) return;
    dialog.classList.add("is-hidden");
    dialog.setAttribute("aria-hidden", "true");
  };

  const childRowHtml = (row) => {
    const context = `env_key=${encodeURIComponent(normalizedEnv(row))}&channel_id=${encodeURIComponent(channelIdOf(row))}&platform=${encodeURIComponent(row.platform || "")}&version_id=${encodeURIComponent(row.id || "")}&version_name=${encodeURIComponent(row.version_name || "")}&version_code=${encodeURIComponent(row.version_code || "")}&scoped=1`;
    const workflowHref = row.id
      ? `/admin/projects/${projectId}/versions/${encodeURIComponent(row.id)}/workflow`
      : `/admin/projects/${projectId}/build-history?${context}`;
    const platform = row.platform || "android";
    return `<div class="version-row version-row-child pm-table-cols-10" data-version-id="${esc(row.id || "")}" data-open-vc="${esc(row.id || "")}">
      <div class="version-vc-cell"><span class="version-vc-code">${esc(row.version_code || "-")}</span><span class="version-vc-label">${esc(row.version_name || "")}</span></div>
      <div>${versionNameTagHtml(row, null)}</div>
      <div><span class="version-scope-env">${esc(envLabels[normalizedEnv(row)] || normalizedEnv(row))}</span></div>
      <div><span class="version-scope-meta">${esc(row.channel_name || row.channel_label || channelNameOf(channelIdOf(row)))}</span></div>
      <div class="version-platform-cell"><img src="/static/project_ui/svg/${platformIconOf(platform)}" alt="">${esc(row.platform_label || platform)}</div>
      <div>${versionStatusHtml(row)}</div>
      <div>${artifactStatusHtml(row)}</div>
      <div>${latestBuildHtml(row)}</div>
      <div class="version-updated-at">${esc(formatUpdatedAt(row))}</div>
      <div class="version-row-actions">
        <button class="version-action-link" type="button" data-download-apk="${esc(row.id)}">查看产物</button>
        <a class="version-action-link primary" href="/admin/projects/${projectId}/release-orders/start?version_id=${encodeURIComponent(row.id)}">创建发布单</a>
        <a class="version-action-link" href="${workflowHref}">重新构建</a>
        <a class="version-action-link" href="/admin/projects/${projectId}/build-history?${context}">查看日志</a>
      </div>
    </div>`;
  };

  const groupRowHtml = (group, children) => {
    const groupName = group.version_name;
    const activeCount = children.filter((x) => x.version_status === "active").length;
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
    const envLabel = envLabels[group.env_key] || group.env_key || "";
    const pipelineBadge = group.pipeline_ready
      ? `<span class="version-pill pipeline-ready">管线就绪</span>`
      : `<span class="version-pill pipeline-missing">未配置${envLabel ? ` · ${esc(envLabel)}` : ""}</span>`;
    const configuredBuilds = children.filter((x) => x.jenkins_job_id || (x.pipeline || {}).jenkins_job_id).length;
    const publishedCount = children.filter((x) => x.active_bundle_id).length;
    const groupActions = canEdit
      ? `<a class="version-btn compact primary" href="${buildConfigHref}">配置管线</a>
         <button class="version-btn compact" type="button" data-add-vc="${esc(groupName)}">添加 VC</button>
         <button class="version-btn compact ghost" type="button" data-edit-group="${esc(groupName)}">编辑</button>
         <button class="version-btn compact ghost danger" type="button" data-delete-group="${esc(groupName)}">删除</button>`
      : `<a class="version-btn compact" href="${buildConfigHref}">查看管线</a>`;
    const emptyHint = children.length
      ? ""
      : `<div class="version-empty-inline">尚无 VersionCode · <button type="button" class="version-link-btn" data-add-vc="${esc(groupName)}">立即添加</button></div>`;
    return `<div class="version-group${collapsed ? " is-collapsed" : ""}" data-group="${esc(groupName)}">
      <div class="version-row version-row-group pm-table-cols-10">
        <div class="version-group-title">
          <button class="version-group-toggle" type="button" data-toggle-group="${esc(groupName)}" aria-expanded="${collapsed ? "false" : "true"}">
            <img src="/static/project_ui/svg/action_next.svg" alt="">
          </button>
          <div class="version-group-head">
            <div class="version-group-name-line"><strong>${esc(groupName)}</strong><span class="pm-tag pm-tag--muted">默认分组</span>${pipelineBadge}</div>
            <div class="version-group-meta-line"><span>${children.length} VC</span><span>${activeCount} 有效</span><span>${configuredBuilds} 已配构建</span><span>${publishedCount} 已发布</span>${group.notes ? `<span class="group-notes-inline">${esc(group.notes)}</span>` : ""}</div>
          </div>
        </div>
        <div>${versionNameTagHtml(children[0] || {}, group)}</div>
        <div class="version-group-dash">${envLabel ? esc(envLabel) : "—"}</div>
        <div class="version-group-dash">—</div>
        <div class="version-group-dash">—</div>
        <div><span class="version-pill ${esc(group.status || "active")}">${esc(statusLabels[group.status] || group.status || "有效")}</span></div>
        <div class="version-group-dash">${configuredBuilds} / ${children.length}</div>
        <div class="version-group-dash">—</div>
        <div class="version-group-dash">—</div>
        <div class="version-row-actions version-group-actions">${groupActions}</div>
      </div>
      <div class="version-group-children">${emptyHint}${children.map(childRowHtml).join("")}</div>
    </div>`;
  };

  const render = () => {
    const query = (document.getElementById("versionSearch")?.value || "").trim().toLowerCase();
    const filterEnv = document.getElementById("versionEnv");
    const filterChannel = document.getElementById("versionChannel");
    const filterPlatform = document.getElementById("versionPlatform");
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
        (!filterPlatform?.value || !platformTabsVisible() || row.platform === filterPlatform.value) &&
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
    const buildingCount = filtered.filter((x) => (x.jenkins_job_id || (x.pipeline || {}).jenkins_job_id) && x.apk_status !== "found").length;
    const artifactReadyCount = filtered.filter((x) => x.apk_status === "found").length;
    const publishedKpiCount = filtered.filter((x) => x.active_bundle_id).length;
    const activeVcCount = filtered.filter((x) => x.version_status === "active").length;
    const completeRate = filtered.length ? ((artifactReadyCount / filtered.length) * 100).toFixed(1) : "0.0";
    document.getElementById("versionKpis").innerHTML = [
      ["nav_version_code.svg", "版本组数", groupNames.length, "blue", "", `/admin/projects/${projectId}/versions`],
      ["nav_version_code.svg", "有效 VersionCode", activeVcCount, "cyan", "", ""],
      ["kpi_build.svg", "构建中", buildingCount, "orange", "", `/admin/projects/${projectId}/build-history?scoped=1`],
      ["file_bundle.svg", "产物完整", artifactReadyCount, "green", `完整率 ${completeRate}%`, ""],
      ["nav_release_order.svg", "已发布", publishedKpiCount, "violet", "", `/admin/projects/${projectId}/release-orders`],
    ]
      .map(([icon, label, value, tone, sub, link]) => `<article class="pm-kpi-card"><span class="pm-kpi-icon pm-kpi-icon--${tone}"><img src="/static/project_ui/svg/${icon}" alt=""></span><div class="pm-kpi-body"><span>${label}</span><strong>${value}</strong>${sub ? `<span class="pm-kpi-sub">${sub}</span>` : ""}${link ? `<a class="pm-kpi-footlink" href="${link}">查看详情 &gt;</a>` : ""}</div></article>`)
      .join("");
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
        if (collapsedGroups.has(name)) collapsedGroups.delete(name);
        else collapsedGroups.add(name);
        render();
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
    document.querySelectorAll("[data-open-vc]").forEach((el) => {
      el.onclick = (event) => {
        if (event.target.closest("a, button, [data-download-apk]")) return;
        const id = el.getAttribute("data-open-vc");
        const row = rows.find((item) => String(item.id || "") === String(id));
        if (row) openVcDrawer(row);
      };
    });
    updateBuildHistoryLink();
  };

  const updateBuildHistoryLink = () => {
    const link = document.getElementById("versionBuildHistoryLink");
    if (!link) return;
    const params = new URLSearchParams();
    const env = activeEnvKey() || envKey || "production";
    params.set("env_key", env);
    params.set("scoped", "1");
    const platform = activePlatform();
    if (platform) params.set("platform", platform);
    if (filterVersionName) params.set("version_name", filterVersionName);
    link.href = `/admin/projects/${projectId}/build-history?${params.toString()}`;
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
    const syncSelect = (select, includeAll = false) => {
      if (!select) return;
      const current = select.value;
      const head = includeAll ? "<option value=\"\">全部环境</option>" : "";
      select.innerHTML =
        head + envs.map((item) => `<option value="${esc(item.env_key)}">${esc(item.label || envLabels[item.env_key] || item.env_key)}</option>`).join("");
      if (current && [...select.options].some((option) => option.value === current)) select.value = current;
    };
    syncSelect(document.getElementById("versionEnv"), true);
    syncSelect(document.getElementById("versionFormEnv"), false);
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
      const current = filterChannel.value;
      filterChannel.innerHTML =
        '<option value="">全部渠道</option>' + channels.map((x) => `<option value="${esc(x.channel_id)}">${esc(x.channel_name)}</option>`).join("");
      if (current && channels.some((x) => x.channel_id === current)) filterChannel.value = current;
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
    if (!envScoped) return;
    root.classList.add("is-env-scoped");
    const envSelect = document.getElementById("versionEnv");
    if (envSelect) {
      envSelect.value = lockEnvKey;
      envSelect.disabled = true;
      envSelect.classList.add("is-locked");
      const toolbar = envSelect.closest(".version-toolbar");
      if (toolbar) {
        const envLabel = document.createElement("span");
        envLabel.className = "version-env-badge";
        envLabel.textContent = envLabels[lockEnvKey] || lockEnvKey;
        envSelect.insertAdjacentElement("afterend", envLabel);
        envSelect.style.display = "none";
      }
    }
    const subtitle = root.querySelector(".version-head-copy p");
    if (subtitle) {
      subtitle.textContent = `当前环境：${envLabels[lockEnvKey] || lockEnvKey}。按平台页签管理 VersionCode，渠道在工具栏筛选。`;
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
      const [versionData, groupData, context] = await Promise.all([
        request(`/admin/projects/${projectId}/versions/list`),
        request(versionGroupsUrl()),
        request(contextOptionsUrl(envFilterValue)),
      ]);
      rows = versionData.versions || [];
      versionGroups = groupData.version_groups || [];
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
    ["versionChannel", "versionPlatform", "versionStatus", "versionArtifactStatus"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.value = "";
    });
    if (!envScoped) {
      const envEl = document.getElementById("versionEnv");
      if (envEl) envEl.value = "";
    }
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

  const envFilter = document.getElementById("versionEnv");
  if (envFilter && !envScoped) {
    if (envKey) envFilter.value = envKey;
    envFilter.addEventListener("change", async () => {
      try {
        await load();
      } catch (error) {
        toast(error.message, "error");
      }
    });
  }

  applyEnvScopedUi();

  ["versionSearch", "versionChannel", "versionPlatform", "versionStatus", "versionArtifactStatus"].forEach((id) => {
    const node = document.getElementById(id);
    if (!node) return;
    if (id === "versionSearch") {
      node.addEventListener("input", () => { listPage = 1; render(); });
      return;
    }
    if (id === "versionChannel") {
      node.addEventListener("change", async () => {
        syncScopeUrl();
        listPage = 1;
        render();
      });
      return;
    }
    node.addEventListener("change", () => { listPage = 1; render(); });
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
    })
    .catch((error) => toast(error.message, "error"));

  document.getElementById("btnCloseVersionDownloadDialog")?.addEventListener("click", closeDownloadDialog);
  document.getElementById("btnCancelVersionDownloadDialog")?.addEventListener("click", closeDownloadDialog);
  document.getElementById("versionDownloadDialog")?.addEventListener("click", (event) => {
    if (event.target?.id === "versionDownloadDialog") closeDownloadDialog();
  });
  root.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-download-apk]");
    if (!btn) return;
    event.preventDefault();
    event.stopPropagation();
    handleDownloadClick(btn.getAttribute("data-download-apk") || "");
  });
})();
