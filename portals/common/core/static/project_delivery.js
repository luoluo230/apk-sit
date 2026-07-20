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
  const orderScopeLinks = (item) => {
    const scope = {
      env_key: item.env_key,
      channel_id: item.channel_id,
      platform: item.platform,
      version_id: item.version_id,
      version_name: item.version_name,
      version_code: item.version_code,
    };
    const ctx = buildScopeQuery(scope);
    const vid = item.version_id ? encodeURIComponent(item.version_id) : "";
    return {
      edit: buildReleaseFocusUrl(`/admin/projects/${projectId}/release-orders/${item.release_order_id}/edit${ctx}`, { releaseOrderId: item.release_order_id }),
      buildHistory: scopeHref(`/admin/projects/${projectId}/build-history`, scope, { scoped: "1" }),
      buildConfig: vid ? buildReleaseFocusUrl(`/admin/projects/${projectId}/versions/${vid}/build-config${buildScopeQuery(scope, { from: "release-order", release_order_id: item.release_order_id })}`, { releaseOrderId: item.release_order_id }) : "",
      versions: scopeHref(`/admin/projects/${projectId}/versions`, scope),
      topology: buildTopologyDrawerHref(scope),
      runtime: buildReleaseFocusUrl(scopeHref(`/admin/projects/${projectId}/overview/runtime`, { env_key: item.env_key }), { releaseOrderId: item.release_order_id, highlightFields: ["runtime_topology"], focusReason: "请确认并启动目标拓扑的运行态" }),
      network: buildReleaseFocusUrl(`/admin/projects/${projectId}/environments/${encodeURIComponent(item.env_key || "development")}${ctx}`, { releaseOrderId: item.release_order_id, highlightFields: ["gateway_ws", "login_http", "game_ws", "ops_http"], focusReason: "请补充环境网络接入配置" }),
    };
  };
  const FIX_LINK_LABELS = { buildHistory: "查看构建历史", buildConfig: "配置管线", trigger_build: "触发 Jenkins 构建", network: "配置网络", topology: "配置拓扑", runtime: "启动运行态", edit: "编辑计划", versions: "版本代码" };
  const appendBuildConfigSection = (href, section, extra = {}) => buildReleaseFocusUrl(href, { section, ...extra });
  const issueFocusParams = (issue, item) => ({
    section: issue.fix_section || issue.fixSection || "",
    highlightFields: issue.highlight_fields || issue.highlightFields || [],
    focusReason: issue.focus_reason || issue.focusReason || "",
    releaseOrderId: item?.release_order_id || "",
  });
  const resolveIssueFixHref = (issue, links, pipelineInfo, item) => {
    const focus = issueFocusParams(issue, item);
    const fix = issue.fix || "edit";
    if (fix === "buildConfig") {
      const base = pipelineInfo?.build_config_href || links.buildConfig;
      return buildReleaseFocusUrl(base, focus);
    }
    if (fix === "network") {
      return buildReleaseFocusUrl(links.network, focus);
    }
    if (fix === "runtime") {
      return buildReleaseFocusUrl(links.runtime, focus);
    }
    if (fix === "edit") {
      return buildReleaseFocusUrl(links.edit, { ...focus, highlightFields: focus.highlightFields.length ? focus.highlightFields : ["reason"] });
    }
    const fixMap = { buildHistory: links.buildHistory, topology: links.topology, versions: links.versions };
    return fixMap[fix] || links.edit || "";
  };
  const resolveIssueFixLabel = (issue) => issue.fix_label || issue.fixLabel || FIX_LINK_LABELS[issue.fix] || "去处理";
  const canonicalFailingKey = (key) => {
    const k = String(key || "").trim().toLowerCase();
    if (!k) return "";
    if (k === "code" || k === "code_url" || k === "code_manifest_url" || k.includes("code_manifest")) return "code";
    if (["apk", "apk_url", "apk_version", "catalog", "catalog_url"].includes(k) || k.startsWith("apk")) return "apk";
    if (["resource", "resource_url", "resource_version"].includes(k) || k.includes("resource")) return "resource";
    if (["config", "config_url", "config_version", "config_manifest_url"].includes(k) || k.includes("config")) return "config";
    if (["gateway_ws", "login_http", "game_ws", "ops_http"].includes(k)) return "network";
    if (["scope_id", "env_key", "channel_id"].includes(k)) return "scope";
    return k;
  };
  const summarizeOrderIssuesClient = (item, payload = {}, pipelineInfo = null) => {
    const pipeline = pipelineInfo?.effective_pipeline || {};
    const pipelineReady = Boolean(pipelineInfo?.readiness?.ready);
    const stepEnabled = (key) => Boolean((pipeline[key] || {}).enabled);
    const artifactRow = (type) => (item.artifacts || []).find((x) => String(x.artifact_type || "").toLowerCase() === type);
    const artifactPath = (type) => {
      const row = artifactRow(type);
      return Boolean(String(row?.artifact_path || row?.artifact_url || "").trim());
    };
    const artifactMissing = (type) => {
      const row = artifactRow(type);
      const status = String(row?.status || "").toLowerCase();
      return !row || ["missing", "unreachable", "invalid"].includes(status) || !artifactPath(type);
    };
    const highlightBySection = {
      hot_release: ["hot_release_enabled", "code_enabled"],
      artifact: ["apk_build_enabled"],
      resource_build: ["resource_build_enabled"],
      config_export: ["config_export_enabled"],
      client_policy: ["resource_server_url"],
    };
    const bootstrapConfigured = (payload) => {
      const targets = payload.artifact_targets || {};
      return Boolean(String(targets.catalog_url || targets.config_manifest_url || "").trim());
    };
    const artifactUnreachable = (groupId, payload) => {
      const keyMap = {
        code: ["code_manifest_url"],
        apk: ["apk_url", "catalog_url"],
        resource: ["resource_url", "catalog_url"],
        config: ["config_url", "config_manifest_url"],
      };
      const checks = payload.artifact_checks || {};
      const targets = payload.artifact_targets || {};
      const keys = keyMap[groupId] || [];
      let hasTarget = false;
      for (const key of keys) {
        const url = String(targets[key] || "").trim();
        if (!url) continue;
        hasTarget = true;
        if (!(checks[key] || {}).ok) return true;
      }
      return false;
    };
    const hintUnreachable = {
      code: "下载地址已配置，但 code manifest 不可达（404），需 Jenkins 构建并 upload",
      apk: "下载地址已配置，但 OSS 远程产物不可达（404），需 Jenkins 构建并 upload",
      resource: "下载地址已配置，但 OSS 远程产物不可达（404），需 Jenkins 构建并 upload",
      config: "下载地址已配置，但 OSS manifest 不可达（404），需 Jenkins 构建并 upload",
    };
    const resolveClientFix = (groupId) => {
      const stepMap = {
        code: { step: "hot_release", section: "hot_release", label: "开启热更发布", reason: "请开启热更发布并保存，然后返回发布单触发 Jenkins 构建" },
        apk: { step: "apk_build", section: "artifact", label: "配置安装包", reason: "请启用安装包步骤并保存，然后返回发布单触发构建" },
        resource: { step: "resource_build", section: "resource_build", label: "配置资源打包", reason: "请启用资源打包并保存，然后返回发布单触发构建" },
        config: { step: "config_export", section: "config_export", label: "配置导出", reason: "请启用配置导出并保存，然后返回发布单触发构建" },
      };
      const meta = stepMap[groupId];
      if (!meta) return { fix: "edit", fix_section: "", fix_label: "去处理", highlight_fields: [], focus_reason: "" };
      if (artifactMissing(groupId)) {
        if (stepEnabled(meta.step) && pipelineReady) return { fix: "trigger_build", fix_section: "", fix_label: "触发 Jenkins 构建", highlight_fields: [], focus_reason: "" };
        return { fix: "buildConfig", fix_section: meta.section, fix_label: meta.label, highlight_fields: highlightBySection[meta.section] || [], focus_reason: meta.reason };
      }
      if (bootstrapConfigured(payload) && artifactUnreachable(groupId, payload)) {
        if (groupId === "code" && stepEnabled("hot_release") && pipelineReady) {
          return { fix: "trigger_build", fix_section: "", fix_label: "触发 Jenkins 构建", highlight_fields: [], focus_reason: "客户端策略已配置，需完成 code 包构建并 upload 到 OSS" };
        }
        return { fix: "buildHistory", fix_section: "", fix_label: "查看构建历史", highlight_fields: [], focus_reason: "下载地址已生成，但 OSS 上产物不可达，需 Jenkins 构建并 upload" };
      }
      if (bootstrapConfigured(payload)) {
        if (groupId === "code" && stepEnabled("hot_release") && pipelineReady) {
          return { fix: "trigger_build", fix_section: "", fix_label: "触发 Jenkins 构建", highlight_fields: [], focus_reason: "客户端策略已配置，需完成 code 包构建并 upload 到 OSS" };
        }
        return { fix: "buildHistory", fix_section: "", fix_label: "查看构建历史", highlight_fields: [], focus_reason: "下载地址已生成，但 OSS 上产物不可达，需 Jenkins 构建并 upload" };
      }
      return { fix: "buildConfig", fix_section: "client_policy", fix_label: "补充下载地址", highlight_fields: ["resource_server_url"], focus_reason: "请填写资源服务器 URL 并保存，以生成对外下载地址" };
    };
    const groups = [
      { id: "code", label: "代码热更包", hintReady: "代码产物路径已登记，需在「客户端策略」补充下载基址", hintMissing: "需开启热更发布步骤、完成构建并登记 code 包", priority: 1 },
      { id: "apk", label: "APK 安装包", hintReady: "安装包路径已登记，需在「客户端策略」补充 resource_server_url / catalog", hintMissing: "需完成安装包构建并登记 APK 与 Catalog", priority: 2 },
      { id: "resource", label: "资源包", hintReady: "资源路径已登记，需在「客户端策略」补充 resource_server_url", hintMissing: "需完成资源打包并登记资源包 URL", priority: 3 },
      { id: "config", label: "配置包", hintReady: "配置路径已登记，需在「客户端策略」补充下载基址与 manifest", hintMissing: "需完成配置导出并登记配置包 URL", priority: 4 },
      { id: "network", label: "网络接入配置", hintMissing: "环境网络接入字段未配置完整", priority: 10 },
      { id: "scope", label: "交付范围对齐", hintMissing: "VersionCode 与发布单环境/渠道/Scope 不一致", priority: 11 },
    ];
    const failing = new Set();
    (payload.missing_client_fields || []).forEach((key) => { const c = canonicalFailingKey(key); if (c) failing.add(c); });
    (payload.missing_profile_fields || []).forEach((key) => { const c = canonicalFailingKey(key); if (c) failing.add(c); });
    (payload.missing_artifact_fields || []).forEach((key) => { const c = canonicalFailingKey(key); if (c) failing.add(c); });
    (payload.alignment_errors || []).forEach((key) => { const c = canonicalFailingKey(key); if (c) failing.add(c); });
    (item.artifacts || []).forEach((row) => {
      const status = String(row.status || "").toLowerCase();
      if (["missing", "unreachable", "invalid"].includes(status)) {
        const c = canonicalFailingKey(row.artifact_type);
        if (c) failing.add(c);
      }
    });
    const issues = [];
    groups.sort((a, b) => a.priority - b.priority).forEach((group) => {
      if (!failing.has(group.id)) return;
      let hint = group.hintMissing;
      if (["code", "apk", "resource", "config"].includes(group.id) && artifactPath(group.id)) {
        hint = bootstrapConfigured(payload)
          ? (hintUnreachable[group.id] || group.hintReady)
          : group.hintReady;
      }
      const fixMeta = group.id === "network"
        ? { fix: "network", fix_section: "", fix_label: "配置网络接入", highlight_fields: ["gateway_ws", "login_http", "game_ws", "ops_http"], focus_reason: "请补充环境网络接入配置" }
        : group.id === "scope"
          ? { fix: "edit", fix_section: "", fix_label: "编辑发布计划", highlight_fields: [], focus_reason: "请核对发布单与 VersionCode 交付范围" }
          : resolveClientFix(group.id);
      issues.push({ id: group.id, label: group.label, hint, ...fixMeta, fields: [group.id] });
    });
    if (payload.topology_runtime_aligned === false || payload.runtime_error) {
      let runtimeHint = String(payload.runtime_error || "").trim();
      if (payload.topology_runtime_aligned === false) {
        const topoHint = `设计拓扑 ${payload.topology_id || "-"}，运行拓扑 ${payload.runtime_topology_id || "-"}`;
        runtimeHint = runtimeHint ? `${runtimeHint}；${topoHint}` : topoHint;
      }
      issues.push({ id: "runtime", label: "Runtime 运行态", hint: runtimeHint || "目标拓扑未运行，需启动 Runtime", fix: "runtime", fix_section: "", fix_label: "启动运行态", highlight_fields: ["runtime_topology"], focus_reason: "请启动目标拓扑运行态后返回发布单重新预检", fields: ["runtime"] });
    }
    return issues;
  };
  const resolveOrderIssues = (item, links, pipelineInfo = null) => {
    const payload = item.latest_precheck?.payload || {};
    const raw = (item.diagnostic_issues && item.diagnostic_issues.length)
      ? item.diagnostic_issues
      : summarizeOrderIssuesClient(item, payload, pipelineInfo || item.pipeline_snapshot || null);
    return raw.map((issue) => ({
      key: issue.id || issue.label,
      label: issue.label || issue.id,
      hint: issue.hint || "预检未通过",
      href: issue.fix === "trigger_build" ? "" : resolveIssueFixHref(issue, links, pipelineInfo || item.pipeline_snapshot || null, item),
      fix: issue.fix || "edit",
      fixLabel: resolveIssueFixLabel(issue),
      apiAction: issue.fix === "trigger_build" ? "build" : "",
    }));
  };
  const renderIssueAction = (issue) => {
    if (issue.apiAction) {
      return `<button type="button" class="rod-issue-action" data-next-action="${esc(issue.apiAction)}">${esc(issue.fixLabel || FIX_LINK_LABELS[issue.fix] || "去处理")}</button>`;
    }
    if (issue.href) {
      return `<a class="rod-issue-action" href="${esc(issue.href)}">${esc(issue.fixLabel || FIX_LINK_LABELS[issue.fix] || "去处理")}</a>`;
    }
    return "";
  };
  const renderOrderIssues = (issues, primary) => {
    const focus = document.getElementById("orderFocus");
    if (!focus) return;
    const tone = issues.length ? "danger" : "ok";
    focus.className = `rod-focus-card rod-focus-card--${tone}`;
    const cards = issues.length
      ? `<div class="rod-issue-stack">${issues.map((issue) => `<article class="rod-issue-card"><div class="rod-issue-icon">!</div><div class="rod-issue-body"><strong>${esc(issue.label)}</strong><p>${esc(issue.hint)}</p></div>${renderIssueAction(issue)}</article>`).join("")}</div>`
      : `<p class="rod-focus-summary">${esc(primary.reason || "当前无阻断项，可继续下一步。")}</p>`;
    document.getElementById("orderIssues").innerHTML = `
      <div class="rod-focus-head">${issues.length ? `<span class="rod-focus-count">${issues.length}</span>` : ""}<h2>${issues.length ? "待处理问题" : "预检就绪"}</h2></div>
      ${issues.length ? `<p class="rod-focus-summary">预检未通过，请按下列 ${issues.length} 类问题逐项修复，右侧可快速跳转。</p>` : ""}
      ${cards}`;
  };
  const renderOrderFixRail = (item, links, pipelineInfo = null) => {
    const host = document.getElementById("orderFixRail");
    if (!host) return;
    const fixActions = [
      item.status === "precheck_failed" && (item.artifacts || []).some((x) => String(x.status || "").toLowerCase() === "missing") && (pipelineInfo?.readiness?.ready)
        ? { action: "build", label: "触发 Jenkins 构建", primary: true }
        : null,
      { href: links.edit, label: "编辑发布计划", primary: item.status === "precheck_failed" && !(item.artifacts || []).some((x) => String(x.status || "").toLowerCase() === "missing") },
      { href: links.buildHistory, label: "查看构建历史" },
      { href: links.buildConfig, label: "配置版本组管线" },
      item.status === "precheck_failed" ? { action: "precheck", label: "重新预检", primary: !(item.artifacts || []).some((x) => String(x.status || "").toLowerCase() === "missing") } : null,
    ].filter(Boolean);
    const fixHtml = fixActions.length
      ? `<div class="rod-fix-stack">${fixActions.map((action) => action.href
        ? `<a class="rod-fix-btn${action.primary ? " primary" : ""}" href="${esc(action.href)}">${esc(action.label)}</a>`
        : `<button type="button" class="rod-fix-btn${action.primary ? " primary" : ""}" data-next-action="${esc(action.action)}">${esc(action.label)}</button>`).join("")}</div>`
      : `<p>暂无可用修复动作。</p>`;
    host.innerHTML = `<h3>修复指引</h3>${fixHtml}`;
  };
  const renderOrderRiskRail = (issues, item) => {
    const host = document.getElementById("orderRiskRail");
    if (!host) return;
    const riskText = item.env_key === "production"
      ? "生产环境发布：请确认审批、灰度策略与回滚方案。"
      : issues.length
        ? `共 ${issues.length} 类问题待处理，修复后请重新预检。`
        : (item.reason || "关注产物、拓扑与 Runtime 一致性。");
    host.innerHTML = `<h3>风险提示</h3><p>${esc(riskText)}</p>`;
  };
  const ORDER_DETAIL_BUILD_KEYS = new Set(["code", "apk", "resource", "config"]);
  const ORDER_DETAIL_ENV_KEYS = new Set(["network", "runtime", "scope"]);
  let orderDetailTabsBound = false;
  const activateOrderDetailTab = (tabId) => {
    const root = document.getElementById("orderDetailTabs");
    if (!root || !tabId) return;
    root.querySelectorAll("[data-rod-tab]").forEach((btn) => {
      const active = btn.dataset.rodTab === tabId;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    root.querySelectorAll("[data-rod-panel]").forEach((panel) => {
      const active = panel.dataset.rodPanel === tabId;
      panel.classList.toggle("active", active);
      if (active) panel.removeAttribute("hidden");
      else panel.setAttribute("hidden", "");
    });
    page.dataset.orderDetailTab = tabId;
  };
  const bindOrderDetailTabs = () => {
    if (orderDetailTabsBound) return;
    const root = document.getElementById("orderDetailTabs");
    if (!root) return;
    orderDetailTabsBound = true;
    root.querySelectorAll("[data-rod-tab]").forEach((btn) => {
      btn.addEventListener("click", () => activateOrderDetailTab(btn.dataset.rodTab || "plan"));
    });
  };
  const updateOrderDetailTabBadges = (issues) => {
    const buildCount = issues.filter((issue) => ORDER_DETAIL_BUILD_KEYS.has(String(issue.key))).length;
    const envCount = issues.filter((issue) => ORDER_DETAIL_ENV_KEYS.has(String(issue.key))).length;
    const paintBadge = (name, count) => {
      const badge = document.querySelector(`[data-tab-badge="${name}"]`);
      if (!badge) return;
      if (count > 0) {
        badge.textContent = String(count);
        badge.classList.remove("is-hidden");
      } else {
        badge.textContent = "";
        badge.classList.add("is-hidden");
      }
    };
    paintBadge("build", buildCount);
    paintBadge("env", envCount);
  };
  const defaultOrderDetailTab = (issues, item) => {
    if (issues.some((issue) => ORDER_DETAIL_BUILD_KEYS.has(String(issue.key)))) return "build";
    if (String(item.status || "").includes("precheck_failed") || issues.some((issue) => ORDER_DETAIL_ENV_KEYS.has(String(issue.key)))) return "env";
    if (["published", "verified", "verify_failed", "approved"].includes(String(item.status || ""))) return "release";
    return "plan";
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
    const healthyCount = cards.filter((item) => item.health === "healthy").length;
    const healthPct = cards.length ? ((healthyCount / cards.length) * 100).toFixed(1) : "—";
    const processingTotal = cards.reduce((s, x) => s + (x.processing_count || 0), 0);
    const pendingChanges = cards.reduce((s, x) => s + (x.failed_count || 0) + (x.pending_approval_count || 0), 0);
    const memberCount = Number(page.dataset.memberCount || 0);
    const kpis = [
      ["kpi_version.svg", "当前版本", latestOrder?.version_name || "—", "blue", "", scopeHref(`/admin/projects/${projectId}/versions`, { env_key: overviewFilterParams().env_key || "production" })],
      ["kpi_health.svg", "服务健康度", `${healthPct}%`, "green", healthyCount > 0 ? `↑ ${healthyCount} 环境正常` : "", `/admin/projects/${projectId}/overview`],
      ["kpi_build.svg", "今日构建次数", processingTotal, "violet", "", `/admin/projects/${projectId}/versions?env_key=${encodeURIComponent(scope?.env_key || "production")}`],
      ["kpi_change.svg", "待处理变更", pendingChanges, "orange", "", `/admin/projects/${projectId}/change-governance`],
      ["kpi_member.svg", "项目成员", memberCount, "cyan", "", `/admin/projects/${projectId}/settings`],
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
    overviewActivityEvents = allOrders.map((item) => ({
      kind: "release",
      typeLabel: "发布",
      title: `发布单 ${item.release_order_id || ""} · ${item.version_name || ""} / ${item.version_code || ""}`,
      actor: "系统",
      time: String(item.updated_at || "").slice(11, 16) || String(item.updated_at || ""),
      href: `/admin/projects/${projectId}/release-orders/${item.release_order_id}`,
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
    const form=document.getElementById("releaseOrderForm"), orderId=page.dataset.orderId;
    const search=new URLSearchParams(location.search);
    const envFromUrl=search.get("env_key")||"";
    const draftKey=`release-order-draft:${projectId}:${orderId||"new"}`;
    const formatTime=()=>{const d=new Date();return `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}:${String(d.getSeconds()).padStart(2,"0")}`;};
    const touchAutosave=(saved=false)=>{
      const el=document.getElementById("orderAutosave");
      if(!el)return;
      el.textContent=saved?`已自动保存于 ${formatTime()}`:"编辑中…";
      el.classList.toggle("saved",saved);
    };
    const bindTagField=(input)=>{
      if(!input||input.dataset.tagBound)return;
      input.dataset.tagBound="1";
      const wrap=document.createElement("div");
      wrap.className="ro-tag-wrap";
      input.parentElement.appendChild(wrap);
      const render=()=>{
        const tags=String(input.value||"").split(/[,，;；\n]/).map(x=>x.trim()).filter(Boolean);
        wrap.innerHTML=tags.map((tag,i)=>`<span class="ro-tag">${esc(tag)}<button type="button" data-tag-remove="${i}" aria-label="移除">×</button></span>`).join("");
        wrap.querySelectorAll("[data-tag-remove]").forEach(btn=>btn.addEventListener("click",()=>{
          const idx=Number(btn.dataset.tagRemove);
          const next=tags.filter((_,j)=>j!==idx);
          input.value=next.join(", ");
          render();
          input.dispatchEvent(new Event("input",{bubbles:true}));
        }));
      };
      input.addEventListener("input",render);
      input.addEventListener("blur",render);
      render();
    };
    page.querySelectorAll("[data-tag-field]").forEach(bindTagField);
    const descArea=form.release_description;
    const descCount=document.getElementById("orderDescCount");
    const syncDescCount=()=>{if(descCount&&descArea)descCount.textContent=`${(descArea.value||"").length} / 500`;};
    if(descArea){descArea.addEventListener("input",syncDescCount);syncDescCount();}
    const updateRiskPanel=()=>{
      const levelEl=document.getElementById("orderRiskLevel");
      const listEl=document.getElementById("orderRiskList");
      if(!levelEl||!listEl)return;
      const env=form.env_key.value;
      const channel=form.channel_id.selectedOptions[0]?.textContent||form.channel_id.value;
      const platform=form.platform.selectedOptions[0]?.textContent||form.platform.value;
      const strategy=form.release_strategy?.value||"standard";
      const audience=form.target_audience?.selectedOptions[0]?.textContent||"全部用户";
      const isProd=env==="production";
      levelEl.textContent=isProd?"高风险":env==="staging"?"中风险":"低风险";
      levelEl.className=`ro-risk-tag ${isProd?"high":env==="staging"?"medium":"low"}`;
      const items=[
        `目标环境：${form.env_key.selectedOptions[0]?.textContent||env}${isProd?"（生产）":""}`,
        `影响范围：${audience}`,
        `渠道 / 平台：${channel} / ${platform}`,
        strategy==="gray"?"发布方式：灰度发布（推荐）":"发布方式：全量发布",
      ];
      const version=selectedVersion();
      if(version?.version_name)items.push(`VersionCode：${version.version_name} / ${version.version_code||""}`);
      listEl.innerHTML=items.map(x=>`<li>${esc(x)}</li>`).join("");
      form.env_key.dataset.risk=isProd?"production":"";
    };
    const updateRuntimeStats=()=>{
      const badge=document.getElementById("orderRuntimeBadge");
      const countEl=document.getElementById("orderInstanceCount");
      const topoVer=document.getElementById("orderTopologyVersion");
      const delivery=formContext.delivery_readiness||{};
      const checks=delivery.checks||{};
      if(badge){
        const ready=Boolean(checks.topology);
        badge.textContent=ready?"运行中":"待解析";
        badge.className=`ro-runtime-badge ${ready?"running":"unknown"}`;
      }
      if(countEl){
        const inst=delivery.runtime_instances;
        countEl.textContent=typeof inst==="object"&&inst?`${inst.ready||0} / ${inst.total||0} 台`:checks.topology?"— / — 台":"—";
      }
      if(topoVer&&!topoVer.value)topoVer.placeholder=checks.topology?"保存后解析":"保存后按绑定规则解析";
    };
    const updateJenkinsDisplay=(version, buildLinks={})=>{
      const instSel=document.getElementById("orderJenkinsDisplay");
      const jobSel=document.getElementById("orderJobDisplay");
      const paramsInput=document.getElementById("orderJenkinsParamsDisplay");
      const inst=version?.jenkins_instance_id||form.jenkins_instance_id?.value||"";
      const job=version?.jenkins_job_id||version?.jenkins_job||form.jenkins_job?.value||"";
      const ensureFieldLink=(selectEl,href,label)=>{
        if(!selectEl?.parentElement)return;
        let hint=selectEl.parentElement.querySelector(".ro-field-config-link");
        if(!href){hint?.remove();return;}
        if(!hint){
          hint=document.createElement("a");
          hint.className="ro-field-config-link ro-config-link";
          selectEl.parentElement.appendChild(hint);
        }
        hint.href=href;
        hint.textContent=label;
      };
      if(instSel){
        instSel.innerHTML=inst?`<option>${esc(inst)}</option>`:'<option>未配置</option>';
        ensureFieldLink(instSel,inst?"":(buildLinks.jenkinsInstance||buildLinks.jenkinsJob||""),"去配置 Jenkins 实例 →");
      }
      if(jobSel){
        jobSel.innerHTML=job?`<option>${esc(job)}</option>`:'<option>未配置</option>';
        ensureFieldLink(jobSel,job?"":(buildLinks.jenkinsJob||""),"去配置 Job / 任务 →");
      }
      if(paramsInput){
        const envKey=form.env_key.value||"prod";
        const channel=form.channel_id.value||"release";
        const platform=form.platform.value||"all";
        const existing=String(paramsInput.value||"").trim();
        if(!existing){
          paramsInput.value=`ENV=${envKey}, CHANNEL=${channel}, PLATFORM=${platform}`;
        }
        bindTagField(paramsInput);
      }
    };
    const applyOrderTemplate=(kind)=>{
      const templates={
        routine:{release_reason_type:"feature",release_strategy:"standard",gray_ratio:"",validation_items:"订单创建流程, 支付结果页跳转",validation_task:"RC-UI-官网验证"},
        hotfix:{release_reason_type:"hotfix",release_strategy:"standard",gray_ratio:"5",gray_duration:"15",validation_items:"核心链路回归",validation_task:""},
        gray:{release_reason_type:"feature",release_strategy:"gray",gray_strategy:"ratio",gray_ratio:"10",gray_duration:"30",gray_success_action:"automatic",validation_items:"订单创建流程, 支付结果页跳转, 消息推送验证"},
      };
      const preset=templates[kind]||{};
      Object.entries(preset).forEach(([key,val])=>{if(form[key])form[key].value=val;});
      page.querySelectorAll("[data-tag-field]").forEach((input)=>{if(input.dataset.tagBound){input.dispatchEvent(new Event("input",{bubbles:true}));}});
      syncDescCount();
      updateRiskPanel();
      updateCompleteness();
      touchAutosave(false);
      toast(kind==="hotfix"?"已应用紧急修复模板":kind==="gray"?"已应用灰度发布模板":"已应用常规发布模板");
    };
    page.querySelectorAll("[data-order-template]").forEach(btn=>btn.addEventListener("click",()=>applyOrderTemplate(btn.dataset.orderTemplate)));
    document.getElementById("btnCopyPlan")?.addEventListener("click",async()=>{
      try{
        await navigator.clipboard.writeText(JSON.stringify(payload(),null,2));
        toast("发布计划已复制到剪贴板");
      }catch(_e){toast("复制失败，请手动复制表单内容","error");}
    });
    let autosaveTimer=null;
    const scheduleDraft=()=>{
      touchAutosave(false);
      clearTimeout(autosaveTimer);
      autosaveTimer=setTimeout(()=>{
        try{localStorage.setItem(draftKey,JSON.stringify(payload()));touchAutosave(true);}catch(_e){/* ignore quota */}
      },1200);
    };
    form.addEventListener("input",scheduleDraft);
    form.addEventListener("change",scheduleDraft);
    touchAutosave(false);
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
    const effectivePipelineCache=new Map();
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
        syncDescCount();
      }catch(_error){/* keep defaults */}
      updateCompleteness();
      updatePipelineGate();
      refreshPipelineSourcePill();
    };
    const applyReleaseDefaults=(defaults)=>{
      if(!defaults||typeof defaults!=="object")return;
      Object.entries(defaults).forEach(([key,value])=>{
        if(!form[key])return;
        if(!String(form[key].value||"").trim()&&String(value||"").trim())form[key].value=String(value);
      });
    };
    const sectionJumpMap={target:"target",build:"build",runtime:"runtime",strategy:"strategy",verify:"verify",rollback:"rollback"};
    const unfoldSection=(key)=>{
      const section=form.querySelector(`[data-section="${sectionJumpMap[key]||key}"]`);
      if(!section)return null;
      section.classList.remove("is-folded");
      section.scrollIntoView({behavior:"smooth",block:"start"});
      return section;
    };
    const bindSectionNavigation=()=>{
      form.querySelectorAll(".ro-section .ro-section-head").forEach((head)=>{
        const section=head.closest(".ro-section");
        if(!section)return;
        const titleRow=head.querySelector(":scope > div")||head;
        let toggle=titleRow.querySelector(".ro-section-toggle");
        if(section.dataset.section!=="target"){
          if(!toggle){
            toggle=document.createElement("span");
            toggle.className="ro-section-toggle";
            titleRow.appendChild(toggle);
          }
          toggle.textContent=section.classList.contains("is-folded")?"展开查看":"收起";
          if(!head.dataset.sectionNavBound){
            head.dataset.sectionNavBound="1";
            head.addEventListener("click",()=>{
              section.classList.toggle("is-folded");
              toggle.textContent=section.classList.contains("is-folded")?"展开查看":"收起";
            });
          }
        }else if(toggle)toggle.remove();
      });
      const guideItems=page.querySelectorAll(".ro-guide-list li");
      const guideKeys=["target","build","runtime","strategy","verify","rollback"];
      guideItems.forEach((item,index)=>{
        item.classList.add("is-link");
        item.addEventListener("click",()=>unfoldSection(guideKeys[index]||"target"));
      });
      document.getElementById("orderFormJourneyProgress")?.querySelectorAll("[data-jump]").forEach((node)=>{
        node.addEventListener("click",()=>{
          const jump=node.dataset.jump||"target";
          if(jump==="plan")unfoldSection("build");
          else if(jump==="execute")unfoldSection("strategy");
          else unfoldSection("target");
        });
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
          ? "开发/测试快捷发布：填写发布原因与负责人；构建/策略等区块可点击下方标题或右侧指引展开查看。"
          : standard
            ? "标准发布：补充发布说明与策略；各区块可点击标题展开或收起。"
            : "完整发布计划：含验证、回滚与审批所需全部信息。";
      }
      form.querySelectorAll(".ro-section").forEach((section)=>{
        section.classList.remove("is-collapsed-section");
        const key=section.dataset.section||"";
        if(key==="target"){section.classList.remove("is-folded");return;}
        if(minimal|| (standard&&key==="rollback"))section.classList.add("is-folded");
        else section.classList.remove("is-folded");
        const toggle=section.querySelector(".ro-section-toggle");
        if(toggle)toggle.textContent=section.classList.contains("is-folded")?"展开查看":"收起";
      });
      page.querySelectorAll(".order-field-optional").forEach((el)=>{
        el.classList.toggle("is-hidden-field",minimal);
      });
      const miniSummary=document.getElementById("orderMinimalBuildSummary");
      if(miniSummary)miniSummary.hidden=!minimal;
      bindSectionNavigation();
    };
    const updatePipelineGate=()=>{
      const delivery=formContext.delivery_readiness||{};
      const pipelineReady=Boolean(delivery.pipeline_ready);
      const btnNext=document.getElementById("btnFormNext");
      const btnConfig=document.getElementById("btnConfigurePipeline");
      const artifactsReady=Boolean(delivery.checks?.artifacts);
      if(btnNext){
        btnNext.disabled=!pipelineReady;
        btnNext.textContent=pipelineReady?(artifactsReady?"下一步：保存并预检":"下一步：保存并触发构建"):"下一步：先配置管线";
        btnNext.title=pipelineReady?"":(delivery.blocker_hint||"请先在版本组配置 Jenkins 实例、Job 与四步管线。");
      }
      if(btnConfig){
        const href=formContext.build_config_href||"";
        if(!pipelineReady&&href){
          btnConfig.href=href;
          btnConfig.classList.remove("is-hidden");
        }else btnConfig.classList.add("is-hidden");
      }
      const gateHint=document.getElementById("orderPipelineGateHint");
      if(gateHint){
        const pipeline=delivery.pipeline||{};
        const hint=String(pipeline.blocker_hint||"").trim();
        if(pipelineReady){
          gateHint.textContent="管线已就绪，可保存并触发构建。";
        }else if(hint){
          gateHint.textContent=`${hint.startsWith("待")?hint:`待完善：${hint}`}。`;
        }else{
          const {label}=formatPipelinePillLabel(pipeline.ready?pipeline:buildLocalPipelineReadiness(selectedVersion())||pipeline);
          gateHint.textContent=`${label}。`;
        }
      }
    };
    const versionContextQuery=(version)=>{
      if(!version||(!version.id&&!version.version_name))return "";
      return buildScopeQuery({
        env_key:version.env_key,
        channel_id:version.channel_id,
        platform:version.platform,
        version_id:version.id,
        version_name:version.version_name,
        version_code:version.version_code,
      }).replace(/^\?/,"");
    };
    const updateFormJourney=()=>{
      const delivery=formContext.delivery_readiness||{};
      const pipelineReady=Boolean(delivery.pipeline_ready);
      const planPercent=Number(document.getElementById("planCompleteness")?.textContent?.replace("%","")||0);
      const phaseIndex=pipelineReady?(planPercent>=100?2:1):0;
      renderJourneyProgress(document.getElementById("orderFormJourneyProgress"), ["准备","构建","发版"], phaseIndex);
    };
    const previewCard=(icon,label,value,detail="",href="",linkLabel="去配置",sameWindow=false,missing=false)=>{
      const targetAttr=sameWindow?"":" target=\"_blank\" rel=\"noopener noreferrer\"";
      const link=href?`<a class="preview-card-link" href="${href}"${targetAttr}>${esc(linkLabel)}</a>`:"";
      const display=missing&&href?`<a class="ro-config-link" href="${esc(href)}">${esc(value||"未配置")}</a>`:esc(value||"未配置");
      return `<div class="preview-card"><img src="/static/project_ui/svg/${icon}.svg" alt=""><div><span>${esc(label)}</span><strong>${display}</strong>${detail?`<small>${esc(detail)}</small>`:""}${link}</div></div>`;
    };
    const isMissingConfigValue=(value)=>!value||value==="未配置"||value==="管线未配置"||value==="尚未登记";
    const resolveMissingPipelineSection=(pipeline={},jenkins={})=>{
      if(!String(jenkins.jenkins_instance_id||"").trim())return "jenkins";
      if(!String(jenkins.jenkins_job_id||jenkins.jenkins_job||"").trim())return "jenkins";
      if(!(pipeline.config_export||{}).enabled)return "config_export";
      if(!(pipeline.resource_build||{}).enabled)return "resource_build";
      if(!(pipeline.hot_release||{}).enabled)return "hot_release";
      if(!(pipeline.apk_build||{}).enabled)return "artifact";
      return "jenkins";
    };
    const setSummaryField=(cell,value,href)=>{
      if(!cell)return;
      const text=String(value||"").trim()||"未配置";
      if(isMissingConfigValue(text)&&href){
        cell.innerHTML=`<a class="ro-config-link" href="${esc(href)}">${esc(text)}</a>`;
      }else{
        cell.textContent=text;
      }
    };
    const formatPipelinePillLabel=(readiness)=>{
      if(!readiness||typeof readiness!=="object"){
        return {label:"待配置：Jenkins 实例、Jenkins Job、管线四步",isReady:false};
      }
      const status=String(readiness.status||"").trim();
      const missingSteps=Array.isArray(readiness.missing_pipeline_steps)?readiness.missing_pipeline_steps:[];
      const missing=Array.isArray(readiness.missing)?readiness.missing:[];
      const checks=readiness.checks||{};
      const infraMissing=missing.filter((x)=>x==="Jenkins 实例"||x==="Jenkins Job");
      if(status==="ready"||(!status&&readiness.ready&&!missingSteps.length)){
        return {label:"版本组管线模板",isReady:true};
      }
      let stepMissing=missingSteps.length?missingSteps:missing.filter((x)=>!["Jenkins 实例","Jenkins Job","管线四步配置"].includes(x));
      let parts=[...infraMissing,...stepMissing];
      if(!parts.length){
        if(checks.jenkins_instance===false)parts.push("Jenkins 实例");
        if(checks.jenkins_job===false)parts.push("Jenkins Job");
        if(checks.pipeline===false)parts.push("管线四步配置");
      }
      if(!parts.length){
        if(readiness.ready)return {label:"版本组管线模板",isReady:true};
        if(String(readiness.blocker_hint||"").trim()){
          const hint=String(readiness.blocker_hint).trim();
          return {label:hint.startsWith("待")?hint:`待完善：${hint}`,isReady:false};
        }
        return {label:"待完善：请检查版本组管线模板",isReady:false};
      }
      const prefix=status==="unconfigured"&&!checks.jenkins_instance&&!checks.jenkins_job&&!checks.pipeline?"待配置":"待完善";
      return {label:`${prefix}：${parts.join("、")}`,isReady:false};
    };
    const setSourcePill=(pillEl,readiness,href)=>{
      if(!pillEl)return;
      const {label,isReady}=formatPipelinePillLabel(readiness);
      pillEl.classList.toggle("ready",isReady);
      pillEl.classList.toggle("missing",!isReady);
      if(!isReady&&href){
        pillEl.innerHTML=`<a class="ro-config-link" href="${esc(href)}">${esc(label)}</a>`;
      }else{
        pillEl.textContent=label;
      }
      const hintEl=document.getElementById("orderPipelineStatusHint");
      if(hintEl){
        if(isReady){
          hintEl.textContent="Jenkins、Job 与管线四步已齐，可进入下一步。";
          hintEl.classList.add("is-ready");
          hintEl.classList.remove("is-missing");
        }else{
          hintEl.textContent=`${label}。点击状态标签可跳转对应配置页。`;
          hintEl.classList.remove("is-ready");
          hintEl.classList.add("is-missing");
        }
      }
    };
    const buildLocalPipelineReadiness=(version)=>{
      if(!version||(!version.id&&!version.version_name))return null;
      const cached=effectivePipelineCache.get(version.id);
      if(cached?.readiness)return cached.readiness;
      const pipeline=version.pipeline&&typeof version.pipeline==="object"?version.pipeline:{};
      const stepDefs=[
        ["config_export","配置导出"],
        ["resource_build","资源打包"],
        ["hot_release","热更发布"],
        ["apk_build","安装包"],
      ];
      const jenkinsInstance=String(version.jenkins_instance_id||form.jenkins_instance_id?.value||"").trim();
      const jenkinsJob=String(version.jenkins_job_id||version.jenkins_job||form.jenkins_job?.value||"").trim();
      const enabledSteps=stepDefs.filter(([key])=>Boolean((pipeline[key]||{}).enabled));
      const missingSteps=stepDefs.filter(([key])=>!(pipeline[key]||{}).enabled).map(([,label])=>label);
      const hasPipeline=enabledSteps.length>0;
      const checks={
        jenkins_instance:Boolean(jenkinsInstance),
        jenkins_job:Boolean(jenkinsJob),
        pipeline:hasPipeline,
      };
      const missing=[];
      if(!checks.jenkins_instance)missing.push("Jenkins 实例");
      if(!checks.jenkins_job)missing.push("Jenkins Job");
      if(!checks.pipeline)missing.push("管线四步配置");
      else if(missingSteps.length)missing.push(...missingSteps);
      const ready=Object.values(checks).every(Boolean);
      let status="partial";
      if(!checks.jenkins_instance&&!checks.jenkins_job&&!checks.pipeline)status="unconfigured";
      else if(ready&&!missingSteps.length)status="ready";
      return {
        ready,
        status,
        checks,
        missing,
        missing_pipeline_steps:hasPipeline?missingSteps:stepDefs.map(([,label])=>label),
        jenkins_instance_id:jenkinsInstance,
        jenkins_job_id:jenkinsJob,
        pipeline_summary:enabledSteps.map(([,label])=>label).join(" · "),
        source:"local",
      };
    };
    let lastPipelineConfigHref="";
    const refreshPipelineSourcePill=(readinessOverride=null,hrefOverride="")=>{
      const pillEl=document.getElementById("orderPipelineSourcePill");
      if(!pillEl)return;
      const version=selectedVersion();
      const readiness=readinessOverride
        ||formContext.delivery_readiness?.pipeline
        ||buildLocalPipelineReadiness(version);
      const href=(readiness&&readiness.ready)?"":(hrefOverride||formContext.build_config_href||lastPipelineConfigHref||"");
      setSourcePill(pillEl,readiness,href);
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
      const jenkinsConfigHref=buildConfigHref("jenkins");
      const pipelineConfigHref=buildConfigHref(resolveMissingPipelineSection(pipeline,{jenkins_instance_id:jenkinsInstance,jenkins_job_id:jenkinsJob}));
      lastPipelineConfigHref=formContext.build_config_href||pipelineConfigHref||jenkinsConfigHref;
      const buildLinks={jenkinsInstance:jenkinsConfigHref,jenkinsJob:jenkinsConfigHref,pipeline:pipelineConfigHref||jenkinsConfigHref};
      const summaryCard=document.getElementById("orderPipelineSummaryCard");
      if(summaryCard){
        const instCell=summaryCard.querySelector("[data-field='jenkins_instance_id']");
        const jobCell=summaryCard.querySelector("[data-field='jenkins_job']");
        const pipelineCell=summaryCard.querySelector("[data-field='pipeline_summary']");
        setSummaryField(instCell,jenkinsInstance||"未配置",!jenkinsInstance?jenkinsConfigHref:"");
        setSummaryField(jobCell,jenkinsJob||"未配置",!jenkinsJob?jenkinsConfigHref:"");
        setSummaryField(pipelineCell,pipelineSummary,isMissingConfigValue(pipelineSummary)?pipelineConfigHref:"");
        refreshPipelineSourcePill(null,lastPipelineConfigHref);
        const cta=document.getElementById("orderGoConfigurePipelineBtn");
        if(cta){
          const href=formContext.build_config_href||jenkinsConfigHref;
          if(href){cta.href=href;cta.removeAttribute("hidden");}
          else cta.setAttribute("hidden","");
        }
      }
      const resourceReady=version.resource_url||version.resource_path||version.config_url||version.config_path;
      const artifactReady=version.apk_url||version.apk_path||version.apk_status==="found";
      updateJenkinsDisplay(version,buildLinks);
      document.getElementById("buildPlanPreview").innerHTML=[
        previewCard("nav_build_artifact","Jenkins 实例",jenkinsInstance||"未配置","维护 Jenkins 实例连接",!jenkinsInstance?jenkinsConfigHref:jenkinsHref,!jenkinsInstance?"去配置实例":"管理实例",!jenkinsInstance,!jenkinsInstance),
        previewCard("nav_execute","构建任务",jenkinsJob||"未配置","Job 与四步开关在版本组管线模板维护",jenkinsConfigHref,"配置版本组模板",true,!jenkinsJob),
        previewCard("nav_download_center","管线摘要",pipelineSummary,"配置导出、资源打包与热更",pipelineConfigHref,"配置管线",true,isMissingConfigValue(pipelineSummary)),
        previewCard("file_android","APK 产物",artifactReady?"已登记":"尚未登记","查看构建历史与产物",buildHistoryHref,"查看产物",false,!artifactReady),
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
          const effBuildConfigHref=(section)=>{
            const base=data.build_config_href||buildConfigBase;
            if(!base)return "";
            const params=new URLSearchParams(buildConfigParams);
            params.set("section",section);
            return `${base.split("?")[0]}?${params.toString()}`;
          };
          const effJenkinsHref=effBuildConfigHref("jenkins");
          const effPipelineHref=effBuildConfigHref(resolveMissingPipelineSection(eff,j));
          lastPipelineConfigHref=data.build_config_href||effPipelineHref||effJenkinsHref||lastPipelineConfigHref;
          const readiness=data.readiness||{};
          const pillHref=readiness.ready?"":lastPipelineConfigHref;
          if(readiness&&typeof readiness==="object"){
            formContext.delivery_readiness=formContext.delivery_readiness||{};
            formContext.delivery_readiness.pipeline_ready=Boolean(readiness.ready);
            formContext.delivery_readiness.pipeline={...readiness};
            if(readiness.checks){
              formContext.delivery_readiness.checks={
                ...(formContext.delivery_readiness.checks||{}),
                ...readiness.checks,
              };
            }
            if(data.build_config_href)formContext.build_config_href=data.build_config_href;
          }
          refreshPipelineSourcePill(readiness,pillHref);
          updateCompleteness();
          setSummaryField(card.querySelector("[data-field='jenkins_instance_id']"),j.jenkins_instance_id||"未配置",!j.jenkins_instance_id?effJenkinsHref:"");
          setSummaryField(card.querySelector("[data-field='jenkins_job']"),j.jenkins_job_id||"未配置",!j.jenkins_job_id?effJenkinsHref:"");
          setSummaryField(card.querySelector("[data-field='pipeline_summary']"),summary,isMissingConfigValue(summary)?effPipelineHref:"");
          if(data.build_config_href){
            const cta=document.getElementById("orderGoConfigurePipelineBtn");
            if(cta){cta.href=data.build_config_href;cta.removeAttribute("hidden");}
          }
          updateJenkinsDisplay(version,{jenkinsInstance:effJenkinsHref,jenkinsJob:effJenkinsHref,pipeline:effPipelineHref});
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
      updateRuntimeStats();
      updateFormJourney();
      const readinessPanel=document.getElementById("orderReadinessPanel");
      if(readinessPanel)readinessPanel.classList.toggle("is-hidden",!form.version_id.value);
    };
    [form.env_key,form.channel_id,form.platform].forEach(x=>x.addEventListener("change",()=>{renderVersions();loadFormContext(selectedVersion());updateRiskPanel();const prod=document.getElementById("orderProductionBanner");if(prod)prod.classList.toggle("is-hidden",form.env_key.value!=="production");}));
    const prodBanner=document.getElementById("orderProductionBanner");if(prodBanner&&form.env_key.value==="production")prodBanner.classList.remove("is-hidden");
    form.version_id.addEventListener("change",()=>{renderPlanPreview();loadFormContext(selectedVersion());updateRiskPanel();});
    form.release_strategy?.addEventListener("change",updateRiskPanel);
    form.target_audience?.addEventListener("change",updateRiskPanel);
    form.addEventListener("input",updateCompleteness);

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
      if(!orderId){
        try{
          const raw=localStorage.getItem(draftKey);
          if(raw){
            const draft=JSON.parse(raw);
            Object.entries(draft||{}).forEach(([key,val])=>{if(form[key]&&String(form[key].value||"").trim()==="")form[key].value=String(val??"");});
            page.querySelectorAll("[data-tag-field]").forEach((input)=>input.dispatchEvent(new Event("input",{bubbles:true})));
            syncDescCount();
            touchAutosave(true);
          }
        }catch(_e){/* ignore bad draft */}
      }
    }
    updateRiskPanel();
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
        page.querySelectorAll("[data-save-order],[data-form-next]").forEach(button=>button.disabled=true);
        let order;
        if(orderId)order=await api(`/api/projects/${projectId}/release-orders/${orderId}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
        else order=await api(`/api/projects/${projectId}/release-orders`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
        document.getElementById("orderSaveStatus").textContent="草稿已保存";
        toast("发布单计划已保存");
        try{localStorage.removeItem(draftKey);}catch(_e){}
        touchAutosave(true);
        const context=buildScopeQuery({env_key:order.env_key,channel_id:order.channel_id,platform:order.platform,version_id:order.version_id,version_name:order.version_name,version_code:order.version_code,release_order_id:order.release_order_id});
        if(buildAfter){
          const artifactsReady=Boolean(formContext.delivery_readiness?.checks?.artifacts);
          if(artifactsReady){
            await api(`/api/projects/${projectId}/release-orders/${order.release_order_id}/precheck`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
          }else{
            await api(`/api/projects/${projectId}/release-orders/${order.release_order_id}/build`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
          }
          location.href=`/admin/projects/${projectId}/release-orders/${order.release_order_id}${context}`;
        }else if(!orderId)location.href=`/admin/projects/${projectId}/release-orders/${order.release_order_id}/edit${context}`;
      }catch(error){toast(error.message,"error");}
      finally{page.querySelectorAll("[data-save-order],[data-form-next]").forEach(button=>button.disabled=false);}
    };
    page.querySelector("[data-save-order]").addEventListener("click",()=>save(false));
    page.querySelector("[data-form-next]")?.addEventListener("click",()=>save(true));
  }

  async function loadOrderDetail(){
    const orderId=page.dataset.orderId;
    const [item, nextAction]=await Promise.all([
      api(`/api/projects/${projectId}/release-orders/${orderId}`),
      api(`/api/projects/${projectId}/release-orders/${orderId}/next-action`),
    ]);
    const links=orderScopeLinks(item);
    let pipelineInfo=item.pipeline_snapshot||null;
    if(!pipelineInfo&&item.version_id){
      try{
        pipelineInfo=await api(`/api/projects/${projectId}/versions/${encodeURIComponent(item.version_id)}/effective-pipeline`);
      }catch(_e){pipelineInfo=null;}
    }
    document.getElementById("orderTitle").innerHTML=`发布单详情 ${status(item.status)}`;
    document.getElementById("orderSubtitle").textContent=`发布单编号：${item.release_order_id} · 更新于 ${item.updated_at || item.created_at || "-"}`;
    const primary=nextAction.primary||{};
    const more=nextAction.more||[];
    const failed=String(item.status||"").includes("failed");
    renderJourneyProgress(document.getElementById("orderJourneyProgress"), nextAction.phases||["准备","构建","发版"], nextAction.phase_index??0, failed);
    const actionsHost=document.getElementById("orderActions");
    const primaryHtml=primary.href
      ? `<a class="ui-primary" href="${esc(primary.href)}">${esc(primary.label)}</a>`
      : `<button class="ui-primary" data-next-action="${esc(primary.api_action||primary.action||"")}" ${primary.disabled?"disabled":""} title="${esc(primary.reason||"")}">${esc(primary.label)}</button>`;
    const moreHtml=more.length?`<div class="order-more-menu"><button class="ui-secondary" type="button" data-toggle-order-more>更多操作 ▾</button><div class="order-more-dropdown" data-order-more>${more.map(action=>{
      if(action.href)return `<a href="${esc(action.href)}">${esc(action.label)}</a>`;
      return `<button type="button" data-next-action="${esc(action.api_action||action.action||"")}">${esc(action.label)}</button>`;
    }).join("")}</div></div>`:"";
    actionsHost.innerHTML=primaryHtml+moreHtml;
    document.getElementById("orderMeta").innerHTML=[["目标环境",envLabels[item.env_key]],["版本",`${item.version_name} / ${item.version_code}`],["渠道与平台",`${item.channel_name} / ${item.platform}`],["负责人",item.created_by],["总体状态",releaseLabel(item.status)]].map(([label,value])=>`<div class="meta-item"><span>${label}</span><strong>${esc(value)}</strong></div>`).join("");
    const check=item.latest_precheck||{},payload=check.payload||{};
    const issues=resolveOrderIssues(item, links, pipelineInfo);
    renderOrderIssues(issues, primary);
    renderOrderFixRail(item, links, pipelineInfo);
    renderOrderRiskRail(issues, item);
    const payloadData=item.payload||{};
    document.getElementById("orderPlan").innerHTML=[
      detailRow("发布原因", item.reason || "-", "", { tone: item.reason ? "success" : "muted" }),
      detailRow("负责人", payloadData.owner || item.created_by || "-"),
      detailRow("发布窗口", payloadData.release_window || "未设置", "", { tone: payloadData.release_window ? "success" : "muted" }),
      detailRow("验证计划", payloadData.validation_plan ? "已填写" : "未填写", payloadData.validation_plan ? "已填写" : "待补充", { tone: payloadData.validation_plan ? "success" : "warning", href: !payloadData.validation_plan ? links.edit : "", linkLabel: "去补充" }),
      detailRow("回滚计划", payloadData.rollback_plan ? "已填写" : "未填写", payloadData.rollback_plan ? "已填写" : "待补充", { tone: payloadData.rollback_plan ? "success" : "warning", href: !payloadData.rollback_plan ? links.edit : "", linkLabel: "去补充" }),
    ].join("");
    const readiness=pipelineInfo?.readiness||{};
    const jenkins=pipelineInfo?.jenkins||{};
    const eff=pipelineInfo?.effective_pipeline||{};
    const pipelineSummary=[
      (eff.config_export||{}).enabled?"配置导出":"",
      (eff.resource_build||{}).enabled?"资源打包":"",
      (eff.hot_release||{}).enabled?"热更发布":"",
      (eff.apk_build||{}).enabled?"安装包":"",
    ].filter(Boolean).join(" · ")||"未配置";
    const pipelineTone=readiness.status==="ready"?"success":readiness.status==="partial"?"warning":"danger";
    document.getElementById("orderPipeline").innerHTML=[
      detailRow("Jenkins 实例", jenkins.jenkins_instance_id || "-", readiness.checks?.jenkins_instance?"已配置":"缺失", { tone: readiness.checks?.jenkins_instance?"success":"danger", href: !jenkins.jenkins_instance_id ? (pipelineInfo?.build_config_href || links.buildConfig) : "", linkLabel: "去配置" }),
      detailRow("Job / 任务", jenkins.jenkins_job_id || "-", readiness.checks?.jenkins_job?"已配置":"缺失", { tone: readiness.checks?.jenkins_job?"success":"danger", href: !jenkins.jenkins_job_id ? (pipelineInfo?.build_config_href || links.buildConfig) : "", linkLabel: "去配置" }),
      detailRow("管线四步", pipelineSummary, readiness.blocker_hint || (readiness.ready?"就绪":"待完善"), { tone: pipelineTone, href: links.buildConfig, linkLabel: "配置管线" }),
      detailRow("产物登记", `${(item.artifacts||[]).filter(x=>x.status==="registered").length}/${(item.artifacts||[]).length||4}`, item.status==="artifacts_ready"||item.status==="precheck_failed"?"查看构建历史":"", { tone: (item.artifacts||[]).some(x=>x.status==="missing")?"warning":"success", href: links.buildHistory, linkLabel: "查看构建" }),
    ].join("");
    const artifactTone=(value)=>value==="registered"||value==="reachable"||value==="available"?"success":value==="missing"?"danger":"warning";
    document.getElementById("orderArtifacts").innerHTML=(item.artifacts||[]).map((x)=>{
      const label=artifactTypeLabels[x.artifact_type]||x.artifact_type;
      const statusText=artifactStatusLabels[x.status]||x.status;
      const missing=["missing","unreachable","invalid"].includes(String(x.status||"").toLowerCase());
      const needsUrl=Boolean(String(x.artifact_path||"").trim())&&!missing;
      const artifactLinkLabel=missing?(pipelineInfo?.readiness?.ready?"触发 Jenkins 构建":"配置管线"):needsUrl?"补充下载地址":"";
      const artifactAction=missing&&pipelineInfo?.readiness?.ready?"build":"";
      const artifactHref=missing
        ? (artifactAction ? "" : buildReleaseFocusUrl(pipelineInfo?.build_config_href||links.buildConfig, { section: x.artifact_type==="code"?"hot_release":x.artifact_type==="apk"?"artifact":x.artifact_type==="resource"?"resource_build":"config_export", highlightFields: x.artifact_type==="code"?["hot_release_enabled","code_enabled"]:x.artifact_type==="apk"?["apk_build_enabled"]:x.artifact_type==="resource"?["resource_build_enabled"]:["config_export_enabled"], focusReason: "请完成对应管线步骤并保存", releaseOrderId: item.release_order_id }))
        : needsUrl
          ? buildReleaseFocusUrl(pipelineInfo?.build_config_href||links.buildConfig, { section: "client_policy", highlightFields: ["resource_server_url"], focusReason: "请填写资源服务器 URL 并保存", releaseOrderId: item.release_order_id })
          : "";
      return detailRow(label, x.artifact_url||x.artifact_path||"-", statusText, {
        tone: artifactTone(String(x.status||"").toLowerCase()),
        href: artifactHref,
        apiAction: artifactAction,
        linkLabel: artifactLinkLabel,
      });
    }).join("")||'<div class="ui-empty">暂无产物</div>';
    document.getElementById("orderRuntime").innerHTML=[
      detailRow("拓扑", item.topology_id || "-", bindingSourceLabels[item.topology_binding_source]||item.topology_binding_source||"-", { tone: item.topology_id?"success":"warning", href: links.topology, linkLabel: "配置拓扑" }),
      detailRow("Runtime", item.runtime_run_id || "未运行", item.runtime_run_id?"运行中":"未运行", { tone: item.runtime_run_id?"success":"muted", href: links.runtime, linkLabel: "查看运行态" }),
      detailRow("Scope", item.scope_id || "-", payload.scope_alignment_ok===false?"不一致":"已对齐", { tone: payload.scope_alignment_ok===false?"danger":"success" }),
    ].join("");
    const precheckItems=[
      { ok: !issues.some((issue)=>["code","apk","resource","config"].includes(issue.key)), label: "构建产物与对外 URL", detail: issues.filter((issue)=>["code","apk","resource","config"].includes(issue.key)).map((issue)=>`${issue.label}${issue.key==="code"?"未构建":"缺下载地址"}`).join("；") || "齐全", href: links.buildHistory, apiAction: issues.some((issue)=>issue.key==="code"&&(issue.fix==="trigger_build"||issue.apiAction==="build"))?"build":"" },
      { ok: !issues.some((issue)=>issue.key==="network"), label: "网络接入配置", detail: issues.some((issue)=>issue.key==="network")?"未配置完整":"齐全", href: links.network },
      { ok: !issues.some((issue)=>issue.key==="runtime"), label: "Runtime 运行态", detail: issues.some((issue)=>issue.key==="runtime")?"未运行或不一致":"一致", href: links.runtime },
      { ok: !issues.some((issue)=>issue.key==="scope"), label: "交付范围对齐", detail: issues.some((issue)=>issue.key==="scope")?"不一致":"一致", href: links.edit },
    ];
    document.getElementById("orderPrecheck").innerHTML=check.created_at
      ? `${detailRow(check.ok?"预检通过":"预检阻断", check.created_at, check.ok?"通过":"失败", { tone: check.ok?"success":"danger" })}<ul class="precheck-checklist">${precheckItems.map((entry)=>`<li><span class="mark ${entry.ok?"ok":"fail"}">${entry.ok?"✓":"!"}</span><span><strong>${esc(entry.label)}</strong><small>${esc(entry.detail)}</small></span>${entry.ok?"":entry.apiAction?`<button type="button" data-next-action="${esc(entry.apiAction)}">触发构建</button>`:entry.href?`<a href="${esc(entry.href)}">查看历史</a>`:""}</li>`).join("")}</ul>`
      : `<div class="ui-empty">尚未执行预检<button class="ui-secondary" type="button" data-next-action="precheck" style="margin-left:8px">执行预检</button></div>`;
    document.getElementById("orderExecutionBundle").innerHTML=[
      (item.approvals||[]).length
        ? (item.approvals||[]).map(x=>detailRow("审批",x.status,x.approved_by||x.requested_by||"-")).join("")
        : detailRow("审批", "暂无记录", "-", { tone: "muted" }),
      detailRow("发布时间", item.published_at || "-", statusLabels[item.status]||item.status, { tone: item.published_at?"success":"muted" }),
      detailRow("验证状态", statusLabels[item.status]||item.status, item.status==="verified"?"通过":item.status==="verify_failed"?"失败":"待验证", { tone: item.status==="verified"?"success":item.status==="verify_failed"?"danger":"warning" }),
      detailRow("Bundle", item.bundle_id || "-", item.bundle_id?"已生成":"未生成", { tone: item.bundle_id?"success":"muted" }),
      detailRow("Active Bundle", item.active_bundle_id || "-", item.bundle_id===item.active_bundle_id&&item.bundle_id?"当前生效":"", { tone: item.bundle_id===item.active_bundle_id&&item.bundle_id?"success":"muted" }),
    ].join("");
    const eventLabels={created:"创建",draft_updated:"草稿更新",build_completed:"构建完成",prechecked:"预检",approved:"审批",published:"发布",verified:"验证",cancelled:"取消",rolled_back:"回滚"};
    document.getElementById("orderEvents").innerHTML=(item.events||[]).map(x=>`<div class="timeline-row"><strong>${esc(eventLabels[x.event_type]||x.event_type)} · ${esc(statusLabels[x.to_status]||x.to_status||"")}</strong><span>${esc(x.actor)} · ${esc(x.created_at)}</span></div>`).join("")||'<div class="ui-empty">暂无事件</div>';
    const dialog=document.getElementById("orderActionDialog"),reason=document.getElementById("orderActionReason");let pendingAction="";
    const closeDialog=()=>{pendingAction="";reason.value="";dialog.classList.add("is-hidden");dialog.setAttribute("aria-hidden","true");};
    const executeAction=async(action,operationReason="")=>{try{await api(`/api/projects/${projectId}/release-orders/${orderId}/${action}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reason:operationReason})});toast("操作已提交");loadOrderDetail();}catch(error){toast(error.message,"error");}};
    document.getElementById("orderActionDialogClose").onclick=closeDialog;document.getElementById("orderActionDialogCancel").onclick=closeDialog;
    document.getElementById("orderActionDialogConfirm").onclick=async()=>{const action=pendingAction,operationReason=reason.value.trim();if(["publish","rollback","cancel"].includes(action)&&!operationReason){toast("请填写操作原因","error");return;}closeDialog();await executeAction(action,operationReason);};
    const handleNextAction=async(button)=>{
      const action=button.dataset.nextAction;
      if(!action||button.disabled)return;
      if(action==="view_build"||action==="edit"||action==="view")return;
      if(["build","precheck","verify"].includes(action)){await executeAction(action);return;}
      pendingAction=action;
      document.getElementById("orderActionDialogTitle").textContent=`确认${button.textContent.trim()}`;
      document.getElementById("orderActionDialogHint").textContent=["publish","rollback","cancel"].includes(action)?"该操作会改变发布状态，请填写原因后确认。":"请确认本次操作影响范围。";
      dialog.classList.remove("is-hidden");dialog.setAttribute("aria-hidden","false");
    };
    actionsHost.querySelectorAll("[data-next-action]").forEach(button=>button.addEventListener("click",()=>handleNextAction(button)));
    page.querySelectorAll("#orderIssues [data-next-action], #orderFixRail [data-next-action], #orderArtifacts [data-next-action], #orderPrecheck [data-next-action]").forEach(button=>button.addEventListener("click",()=>handleNextAction(button)));
    const moreToggle=actionsHost.querySelector("[data-toggle-order-more]");
    const moreMenu=actionsHost.querySelector("[data-order-more]");
    if(moreToggle&&moreMenu){
      moreToggle.onclick=(event)=>{event.stopPropagation();moreMenu.classList.toggle("open");};
      const closeMoreMenu=(event)=>{if(!moreMenu.contains(event.target)&&event.target!==moreToggle)moreMenu.classList.remove("open");};
      document.addEventListener("click",closeMoreMenu);
      moreMenu.querySelectorAll("[data-next-action]").forEach(button=>button.addEventListener("click",(event)=>{event.stopPropagation();moreMenu.classList.remove("open");handleNextAction(button);}));
    }
    bindOrderDetailTabs();
    updateOrderDetailTabBadges(issues);
    const tabIds = new Set(["plan", "build", "env", "release"]);
    const savedTab = page.dataset.orderDetailTab || "";
    activateOrderDetailTab(tabIds.has(savedTab) ? savedTab : defaultOrderDetailTab(issues, item));
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
  if(type==="order-detail")loadOrderDetail().catch(error=>toast(error.message,"error"));
})();
