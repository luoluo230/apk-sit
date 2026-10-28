/* Environment delivery matrix and scope editor. */
(function (global) {
  "use strict";

  function create(ctx) {
    const esc = ctx.esc;
    const projectId = ctx.projectId;
    const scopeHref = ctx.scopeHref;
    const bindingSourceLabels = ctx.bindingSourceLabels;
    const page = ctx.page;
    const api = ctx.api;
    const toast = ctx.toast;
    const csrfHeaders = ctx.csrfHeaders;
    const parseJsonResponse = ctx.parseJsonResponse;
    const parseApiError = ctx.parseApiError;
    const loadOverview = () => ctx.loadOverview();
    const loadProjectPlatforms = () => ctx.loadProjectPlatforms();
    let envDeliveryScopeState = null;

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
          : `<a class="matrix-btn version env-line-version-btn" href="${esc(scopeApi.versionsPageHref ? scopeApi.versionsPageHref(projectId, { env_key: envKey, channel_id: cid, platform: line.platform }) : scopeHref(`/admin/projects/${projectId}/versions`, { env_key: envKey, channel_id: cid, platform: line.platform }))}">版本与管线</a>`;
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

    return {
      formatEnvTime: formatEnvTime,
      renderDeliveryMatrixHtml: renderDeliveryMatrixHtml,
      loadEnvDeliveryScope: loadEnvDeliveryScope,
      bindDeliveryScopeDialog: bindDeliveryScopeDialog,
      maybeOpenDeliveryScopeFromDeepLink: maybeOpenDeliveryScopeFromDeepLink,
      openDeliveryScopeDialog: openDeliveryScopeDialog,
    };
  }

  global.DeliveryEnv = { create: create };
})(typeof window !== "undefined" ? window : globalThis);
