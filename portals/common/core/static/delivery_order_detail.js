(() => {
  const DC = window.DeliveryCommon || {};
  const page = document.querySelector('[data-delivery-page="order-detail"]');
  if (!page) return;
  const projectId = page.dataset.projectId;
  const envLabels = {development:"开发环境",testing:"测试环境",staging:"预发环境",production:"生产环境"};
  const statusLabels = DC.statusLabels || {draft:"草稿",building:"构建中",build_failed:"构建失败",artifacts_ready:"产物就绪",prechecking:"预检中",precheck_failed:"预检失败",ready:"待发布",awaiting_approval:"待审批",approved:"待发布",publishing:"发布中",published:"已发布",publish_failed:"发布失败",verifying:"验证中",verified:"验证通过",verify_failed:"验证失败",rolled_back:"已回滚",cancelled:"已取消"};
  const releaseLabel = DC.releaseLabel || ((value) => statusLabels[value] || value || "未配置");
  const artifactStatusLabels = {registered:"已登记",available:"可用",reachable:"可达",missing:"缺失",unreachable:"不可达",invalid:"无效"};
  const artifactTypeLabels = {apk:"APK 安装包",resource:"资源包",config:"配置包",code:"代码热更包"};
  const bindingSourceLabels = {project_default:"项目默认",env_channel:"环境与渠道",env_channel_platform:"环境/渠道/平台",version:"大版本覆盖",version_override:"大版本覆盖",scope_default:"Scope默认",scope_override:"Scope覆盖",default:"项目默认"};
  const renderClientHealthPanel = (host, health = {}) => {
    if (!host) return;
    const checks = health.verify_checks || [];
    const gates = health.gate_results || [];
    const checkRows = checks.length
      ? `<ul class="precheck-checklist">${checks.map((row) => `<li><span class="mark ${row.ok ? "ok" : "fail"}">${row.ok ? "✓" : "!"}</span><span><strong>${esc(row.key || "check")}</strong><small>${esc(row.value || row.probe?.error || "")}</small></span></li>`).join("")}</ul>`
      : `<div class="ui-empty">暂无验证探针结果（发布验证后将显示 catalog/config/code HEAD 检查）</div>`;
    const gateRows = gates.length
      ? gates.map((row) => `<div class="timeline-row"><strong>${esc(row.gate || "gate")} · ${row.passed ? "PASS" : "FAIL"}</strong><span>${esc(row.at || "")}</span></div>`).join("")
      : `<div class="ui-empty">暂无 bootstrap gate 记录</div>`;
    host.innerHTML = [
      detailRow("验证探针", checks.length ? `${checks.filter((x) => x.ok).length}/${checks.length} 通过` : "未执行", health.verify_ok ? "通过" : checks.length ? "失败" : "待验证", { tone: health.verify_ok ? "success" : checks.length ? "danger" : "muted" }),
      checkRows,
      `<div class="rod-tab-section-title" style="margin-top:12px">Bootstrap Gate</div>`,
      gateRows,
    ].join("");
  };
  const esc = DC.esc || ((value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])));
  const api = DC.api || (async (path, options = {}) => {
    const response = await fetch(path, { ...options, credentials: "same-origin" });
    const result = await response.json();
    if (!response.ok || result.ok === false) throw new Error(result.error || "请求失败");
    return result.data;
  });
  const toast = DC.toast || ((message, type="success") => alert(message));
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const pollRuntimeActive = async (scope, tries = 24) => {
    const qs = new URLSearchParams({
      project_id: scope.project_id || projectId,
      env_key: scope.env_key || "",
      topology_id: scope.topology_id || "",
    });
    for (let i = 0; i < tries; i += 1) {
      const data = await api(`/api/ops-platform/runtime/active?${qs}`);
      if (data?.active) return data;
      await sleep(2500);
    }
    throw new Error("Runtime 启动超时，请稍后在 Ops 面板确认运行态");
  };
  const startRuntimeRemote = async (action) => {
    const nodeId = String(action?.node_id || "").trim();
    if (!nodeId) throw new Error("缺少拓扑节点，无法远端启动 Runtime");
    await api("/api/ops-platform/topology/node/start-remote", {
      method: "POST",
      body: JSON.stringify({
        project_id: action.project_id || projectId,
        env_key: action.env_key || "",
        topology_id: action.topology_id || "",
        node_id: nodeId,
      }),
    });
    return pollRuntimeActive(action);
  };
  const handleRuntimeStart = async (action) => {
    toast("正在启动 Runtime…");
    await startRuntimeRemote(action);
    await api(`/api/projects/${projectId}/release-orders/${page.dataset.orderId}/precheck`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "runtime started from order detail" }),
    });
    toast("Runtime 已启动，预检已自动重试");
    loadOrderDetail();
  };
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
  const scopeApi = window.DeliveryScope || {};
  const buildScopeQuery = (scope = {}, extra = {}) => (scopeApi.buildQuery ? scopeApi.buildQuery(scope, extra) : "");
  const scopeHref = (path, scope = {}, extra = {}) => (scopeApi.href ? scopeApi.href(path, scope, extra) : `${path}${buildScopeQuery(scope, extra)}`);
  const buildTopologyDrawerHref = (scope = {}) => {
    const envKey = scope.env_key || page.dataset.envKey || "development";
    return scopeHref(`/admin/projects/${projectId}/environments/${encodeURIComponent(envKey)}`, scope, { open_topology_drawer: "1" });
  };
  const renderJourneyProgress = (window.JourneyCommon && window.JourneyCommon.renderJourneyProgress)
    ? window.JourneyCommon.renderJourneyProgress
    : (host, phases, phaseIndex, failed = false) => {
      if (!host || !phases?.length) return;
      host.innerHTML = phases.map((label, index) => {
        const cls = index < phaseIndex ? "done" : index === phaseIndex ? (failed ? "failed active" : "active") : "";
        return `<div class="ro-journey-segment ${cls}" data-phase="${index}"><span>${esc(label)}</span></div>`;
      }).join("");
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
      runtime_action: issue.runtime_action || {},
    }));
  };
  const renderIssueAction = (issue, item) => {
    if (issue.fix === "runtime" && issue.runtime_action?.node_id) {
      const action = issue.runtime_action || {};
      return `<button type="button" class="rod-issue-action"
        data-runtime-project="${esc(action.project_id || projectId)}"
        data-runtime-env="${esc(action.env_key || "")}"
        data-runtime-topology="${esc(action.topology_id || "")}"
        data-runtime-node="${esc(action.node_id || "")}">${esc(issue.fixLabel || "启动运行态")}</button>`;
    }
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
      ? `<div class="rod-issue-stack">${issues.map((issue) => `<article class="rod-issue-card"><div class="rod-issue-icon">!</div><div class="rod-issue-body"><strong>${esc(issue.label)}</strong><p>${esc(issue.hint)}</p></div>${renderIssueAction(issue, item)}</article>`).join("")}</div>`
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

  async function loadOrderDetail(){
    const orderId=page.dataset.orderId;
    let item;
    let nextAction;
    try {
      item = await api(`/api/projects/${projectId}/release-orders/${orderId}`);
      try {
        nextAction = await api(`/api/projects/${projectId}/release-orders/${orderId}/next-action`);
      } catch (nextError) {
        const status = String(item.status || "");
        const scopeLinks = orderScopeLinks(item);
        const fallbackHref = status.includes("failed") || status === "artifacts_ready"
          ? scopeLinks.build || `/admin/projects/${projectId}/channels/${encodeURIComponent(item.channel_id || "wechat")}/build?env_key=${encodeURIComponent(item.env_key || "development")}&version_id=${encodeURIComponent(item.version_id || "")}`
          : `/admin/projects/${projectId}/release-orders/${encodeURIComponent(orderId)}`;
        nextAction = {
          primary: {
            label: status === "awaiting_approval" ? "前往审批" : status.includes("failed") ? "查看问题并修复" : "继续发版流程",
            href: fallbackHref,
            disabled: false,
            reason: nextError.message || "下一步动作接口暂不可用，已提供备用入口",
          },
          more: [],
          phases: ["准备", "构建", "发版"],
          phase_index: status.includes("published") ? 2 : status.includes("build") ? 1 : 0,
        };
      }
    } catch (error) {
      document.getElementById("orderSubtitle").textContent = error.message || "加载失败";
      toast(error.message || "加载失败", "error");
      return;
    }
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
      { ok: !issues.some((issue)=>issue.key==="runtime"), label: "Runtime 运行态", detail: issues.some((issue)=>issue.key==="runtime")?"未运行或不一致":"一致", href: links.runtime, runtimeAction: issues.find((issue)=>issue.key==="runtime")?.runtime_action || null },
      { ok: !issues.some((issue)=>issue.key==="scope"), label: "交付范围对齐", detail: issues.some((issue)=>issue.key==="scope")?"不一致":"一致", href: links.edit },
    ];
    document.getElementById("orderPrecheck").innerHTML=check.created_at
      ? `${detailRow(check.ok?"预检通过":"预检阻断", check.created_at, check.ok?"通过":"失败", { tone: check.ok?"success":"danger" })}<ul class="precheck-checklist">${precheckItems.map((entry)=>`<li><span class="mark ${entry.ok?"ok":"fail"}">${entry.ok?"✓":"!"}</span><span><strong>${esc(entry.label)}</strong><small>${esc(entry.detail)}</small></span>${entry.ok?"":entry.runtimeAction?.node_id?`<button type="button" data-runtime-project="${esc(entry.runtimeAction.project_id||projectId)}" data-runtime-env="${esc(entry.runtimeAction.env_key||"")}" data-runtime-topology="${esc(entry.runtimeAction.topology_id||"")}" data-runtime-node="${esc(entry.runtimeAction.node_id||"")}">启动运行态</button>`:entry.apiAction?`<button type="button" data-next-action="${esc(entry.apiAction)}">触发构建</button>`:entry.href?`<a href="${esc(entry.href)}">查看历史</a>`:""}</li>`).join("")}</ul>`
      : `<div class="ui-empty">尚未执行预检<button class="ui-secondary" type="button" data-next-action="precheck" style="margin-left:8px">执行预检</button></div>`;
    renderClientHealthPanel(document.getElementById("orderClientHealth"), item.client_health || {});
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
    page.querySelectorAll("[data-runtime-node]").forEach((button) => {
      button.addEventListener("click", async () => {
        const action = {
          project_id: button.dataset.runtimeProject || projectId,
          env_key: button.dataset.runtimeEnv || "",
          topology_id: button.dataset.runtimeTopology || "",
          node_id: button.dataset.runtimeNode || "",
        };
        button.disabled = true;
        try { await handleRuntimeStart(action); } catch (error) { toast(error.message, "error"); } finally { button.disabled = false; }
      });
    });
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

  loadOrderDetail().catch(error => toast(error.message, "error"));
})();
