(() => {
  const JC = window.JourneyCommon || {};
  const esc = JC.esc || ((v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])));
  const page = document.querySelector('[data-journey="release"]');
  if (!page) return;

  const projectId = page.dataset.projectId || "";
  const envKey = page.dataset.envKey || "";
  const channelId = page.dataset.channelId || "";
  const params = new URLSearchParams(location.search);
  let platform = params.get("platform") || "";
  let versionId = params.get("version_id") || "";
  let bundleId = params.get("bundle_id") || "";

  const toast = JC.toast || ((msg, type = "info") => {
    if (window.DeliveryScopeToast) window.DeliveryScopeToast(msg, type);
    else alert(msg);
  });

  const api = JC.api || (async (url, options = {}) => {
    const resp = await fetch(url, { credentials: "same-origin", headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || data.ok === false) throw new Error(data.error || `请求失败 (${resp.status})`);
    return data.data ?? data;
  });

  const syncUrl = () => {
    const qs = new URLSearchParams({ env_key: envKey, channel_id: channelId });
    if (platform) qs.set("platform", platform);
    if (versionId) qs.set("version_id", versionId);
    if (bundleId) qs.set("bundle_id", bundleId);
    history.replaceState(null, "", `${location.pathname}?${qs}`);
  };

  const promptReason = (title) => {
    const reason = window.prompt(`${title}\n请填写原因：`);
    if (!reason || !String(reason).trim()) throw new Error("已取消：需填写原因");
    return String(reason).trim();
  };

  const chip = JC.chip || ((label, value, ready = true) =>
    `<span class="cj-context-chip ${ready ? "is-ready" : "is-pending"}">${label} <strong>${esc(value)}</strong></span>`);

  const panel = JC.panel || ((title, desc, bodyHtml, actionsHtml = "", tone = "ready") => {
    const actionBlock = actionsHtml ? `<div class="cj-actions">${actionsHtml}</div>` : "";
    return `<div class="cj-main-inner is-${tone}${actionsHtml ? " has-actions" : ""}">
      <div class="cj-main-copy">
        <div class="cj-panel-head"><div><h3>${title}</h3><p>${desc}</p></div></div>
        <div class="cj-panel-body">${bodyHtml}</div>
      </div>
      ${actionBlock}
    </div>`;
  });

  const summaryGrid = JC.summaryGrid || ((rows) => {
    const items = rows.filter((r) => r).map(([k, v, tone]) => {
      const cls = tone === "pending" ? " is-pending" : tone === "ready" ? " is-ready" : "";
      return `<div class="cj-kv${cls}"><dt>${esc(k)}</dt><dd>${v}</dd></div>`;
    }).join("");
    return items ? `<dl class="cj-kv-grid">${items}</dl>` : "";
  });

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const isDevEnv = () => String(envKey || "").toLowerCase() === "development";

  const precheckUrl = (orderId, forceAuto = false) => {
    const qs = new URLSearchParams();
    if (forceAuto || isDevEnv()) qs.set("auto_ensure_runtime", "1");
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return `/api/projects/${encodeURIComponent(projectId)}/release-orders/${encodeURIComponent(orderId)}/precheck${suffix}`;
  };

  const pollRuntimeActive = async (scope, tries = 24) => {
    const qs = new URLSearchParams({
      project_id: scope.project_id || projectId,
      env_key: scope.env_key || envKey,
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
        env_key: action.env_key || envKey,
        topology_id: action.topology_id || "",
        node_id: nodeId,
      }),
    });
    return pollRuntimeActive(action);
  };

  const renderEnvIssueCard = (issues) => {
    const runtimeIssue = (issues || []).find((row) => row.id === "runtime" || row.fix === "runtime");
    if (!runtimeIssue) return "";
    const action = runtimeIssue.runtime_action || {};
    return `<div class="cj-env-issue-card">
      <div class="cj-env-issue-head"><strong>${esc(runtimeIssue.label || "Runtime 运行态")}</strong><span class="cj-badge pending">环境问题</span></div>
      <p>${esc(runtimeIssue.hint || "目标拓扑未运行")}</p>
      <button type="button" class="cj-btn build" id="cjStartRuntime"
        data-runtime-project="${esc(action.project_id || projectId)}"
        data-runtime-env="${esc(action.env_key || envKey)}"
        data-runtime-topology="${esc(action.topology_id || "")}"
        data-runtime-node="${esc(action.node_id || "")}">自动启动 Runtime 并重试预检</button>
    </div>`;
  };

  const bindRuntimeStart = (state) => {
    const btn = document.getElementById("cjStartRuntime");
    if (!btn) return;
    btn.onclick = async () => {
      const oid = state.release_order_id || "";
      if (!oid) return toast("缺少发布单，无法重试预检", "error");
      btn.disabled = true;
      try {
        toast("正在自动启动 Runtime 并重试预检…");
        await api(precheckUrl(oid, true), { method: "POST", body: "{}" });
        toast("预检已重试");
        load();
      } catch (e) {
        toast(e.message, "error");
      } finally {
        btn.disabled = false;
      }
    };
  };

  const renderContext = (data, state) => {
    const host = document.getElementById("cjReleaseContext");
    if (!host) return;
    const vc = state.version_name ? `${state.version_name} / ${state.version_code}` : versionId ? "已选 VC" : "待选";
    host.innerHTML = [
      chip("环境", data.env_label || envKey, true),
      chip("渠道", data.channel_name || channelId, true),
      chip("平台", platform || "待选", Boolean(platform)),
      chip("目标", vc, Boolean(state.version_name || versionId)),
      chip("Bundle", bundleId || state.bundle_id || "待选", Boolean(bundleId || state.bundle_id)),
    ].join("");
  };

  const buildVersionGroups = (versions, filterFn = () => true) => {
    const groups = new Map();
    (versions || []).filter(filterFn).forEach((v) => {
      const name = String(v.version_name || "未命名").trim() || "未命名";
      if (!groups.has(name)) groups.set(name, []);
      groups.get(name).push(v);
    });
    return groups;
  };

  const resolveSelectedGroupName = (groups, vid, state) => {
    if (vid) {
      for (const [name, items] of groups) {
        if (items.some((row) => row.version_id === vid)) return name;
      }
    }
    const fromState = String(state.version_name || "").trim();
    if (fromState && groups.has(fromState)) return fromState;
    return groups.keys().next().value || "";
  };

  const mergeSelectedVersionState = (state) => {
    if (!versionId) return state;
    const selected = (state.versions || []).find((row) => row.version_id === versionId);
    if (!selected) return { ...state, version_id: versionId };
    return {
      ...state,
      version_id: versionId,
      version_name: selected.version_name || state.version_name,
      version_code: selected.version_code || state.version_code,
      release_order_id: selected.release_order_id || state.release_order_id,
      order_status: selected.release_order_status || state.order_status,
      artifact_ready: true,
    };
  };

  const versionsPageHref = () =>
    `/admin/projects/${encodeURIComponent(projectId)}/versions?env_key=${encodeURIComponent(envKey)}&channel_id=${encodeURIComponent(channelId)}&platform=${encodeURIComponent(platform)}`;

  const renderVersionPicker = (state) => {
    const host = document.getElementById("cjReleaseVersionPicker");
    if (!host) return;
    const filterFn = (row) => row.artifacts_ready;
    const groups = buildVersionGroups(state.versions || [], filterFn);
    if (!groups.size) {
      host.innerHTML = `<div class="cj-version-picker is-empty"><span class="cj-empty-hint">暂无产物就绪的 VersionCode，请先在版本页创建并完成构建。</span></div>`;
      return;
    }
    const groupNames = [...groups.keys()];
    const selectedGroup = resolveSelectedGroupName(groups, versionId, state) || groupNames[0];
    const vcList = groups.get(selectedGroup) || [];
    const selectedVc = (versionId && vcList.find((row) => row.version_id === versionId)) || vcList[0];
    const groupOptions = groupNames.map((name) =>
      `<option value="${esc(name)}"${name === selectedGroup ? " selected" : ""}>${esc(name)}</option>`,
    ).join("");
    const vcOptions = vcList.map((row) =>
      `<option value="${esc(row.version_id)}"${row.version_id === selectedVc?.version_id ? " selected" : ""}>${esc(`${row.version_name} / ${row.version_code}`)} · 产物就绪</option>`,
    ).join("");
    host.innerHTML = `<div class="cj-version-picker">
      <label class="cj-select-field"><span>版本组</span><select id="cjVersionGroupSelect">${groupOptions}</select></label>
      <label class="cj-select-field"><span>VersionCode</span><select id="cjVersionCodeSelect">${vcOptions}</select></label>
    </div>`;
  };

  const bindVersionPicker = (state) => {
    const groupSelect = document.getElementById("cjVersionGroupSelect");
    const vcSelect = document.getElementById("cjVersionCodeSelect");
    if (!groupSelect || !vcSelect) return;
    const filterFn = (row) => row.artifacts_ready;
    groupSelect.onchange = () => {
      const groups = buildVersionGroups(state.versions || [], filterFn);
      const items = groups.get(groupSelect.value) || [];
      versionId = items[0]?.version_id || "";
      bundleId = "";
      syncUrl();
      load();
    };
    vcSelect.onchange = () => {
      versionId = vcSelect.value || "";
      bundleId = "";
      syncUrl();
      load();
    };
  };

  const ensureDefaultVersionId = (state) => {
    const rows = (state.versions || []).filter((row) => row.artifacts_ready);
    if (!rows.length) return false;
    if (versionId && rows.some((row) => row.version_id === versionId)) return false;
    versionId = rows[0].version_id;
    syncUrl();
    return true;
  };

  const renderPlatforms = (host, platforms, active) => {
    if (!host) return;
    host.innerHTML = platforms.map((p) => {
      const cls = p.value === active ? "cj-platform-tab active" : "cj-platform-tab";
      return `<button type="button" class="${cls}" data-platform="${esc(p.value)}">${esc(p.label)}</button>`;
    }).join("");
    host.querySelectorAll("[data-platform]").forEach((btn) => {
      btn.onclick = () => {
        platform = btn.getAttribute("data-platform") || "";
        versionId = "";
        bundleId = "";
        syncUrl();
        load();
      };
    });
  };

  const grayPlanRows = (state) => {
    if (String(state.release_strategy || "") !== "gray") return [];
    const ratio = state.gray_ratio || state.rollout_percentage || "—";
    const strategy = state.gray_strategy || "ratio";
    const duration = state.gray_duration ? `${state.gray_duration} 分钟` : "—";
    return [
      ["发布方式", "灰度发布", "ready"],
      ["灰度策略", esc(strategy), "ready"],
      ["灰度比例", esc(`${ratio}%`), "ready"],
      ["灰度时长", esc(duration), state.gray_duration ? "ready" : "pending"],
    ];
  };

  const renderWorkspace = (data, state) => {
    const oid = state.release_order_id || "";
    const detailHref = oid ? `/admin/projects/${projectId}/release-orders/${oid}` : "";
    const editHref = oid ? `${detailHref}/edit` : "";
    const status = String(state.order_status || "");
    const vc = state.version_name && state.version_code ? `${state.version_name} / ${state.version_code}` : "未选择";
    const grayRows = grayPlanRows(state);
    const buildNode = data.recommended_build_node || {};
    const serverGate = (state.latest_precheck || {}).payload?.server_release_gate || state.server_release_gate || {};
    const serverRow = serverGate.server_release_id
      ? [["服务端发布", esc(serverGate.ok ? (serverGate.version_label || "已部署") : (serverGate.hint || "未就绪")), serverGate.ok ? "ready" : "pending"]]
      : [];
    const buildNodeRow = buildNode.display_name || buildNode.hint
      ? [["推荐构建节点", esc(buildNode.available ? (buildNode.display_name || buildNode.hostname || "在线") : (buildNode.hint || "无在线节点")), buildNode.available ? "ready" : "pending"]]
      : [];
    const rows = [
      ["版本组", esc(state.version_name || "—"), state.version_name ? "ready" : "pending"],
      ["VersionCode", esc(vc), versionId ? "ready" : "pending"],
      ["发布单", esc(oid || "—"), oid ? "ready" : "pending"],
      ["当前阶段", esc(status || "待开始"), status ? "ready" : "pending"],
      ["Bundle", esc(bundleId || state.bundle_id || state.active_bundle_id || "—"), bundleId || state.bundle_id || state.active_bundle_id ? "ready" : "pending"],
      ...buildNodeRow,
      ...serverRow,
      ...grayRows,
    ];

    if (!platform) {
      return panel("选择平台", "请在右上角切换 Android / iOS。", summaryGrid(rows.slice(0, 3)), "", "pending");
    }
    if (!versionId) {
      return panel("请选择发版目标", "在上方选择产物就绪的版本组与 VersionCode。", summaryGrid(rows), "", "pending");
    }

    if (!oid || status === "draft" || status === "artifacts_ready" || status === "precheck_failed" || status === "build_failed") {
      const ensureApi = state.ensure_order_api || "";
      const createHref = state.create_order_href || "";
      const noOrderActions = !oid && ensureApi
        ? `<button type="button" class="cj-btn release" id="cjEnsureOrder">创建发布单</button>
           ${createHref ? `<a class="cj-btn neutral" href="${esc(createHref)}">填写发布计划</a>` : ""}`
        : "";
      const failedHint = status === "build_failed"
        ? `<p class="cj-empty-hint">构建失败，请先在构建流程重新触发构建，或创建新的发布单。</p>`
        : "";
      const envIssues = status === "precheck_failed" ? renderEnvIssueCard(state.diagnostic_issues || []) : "";
      return panel(
        "发版计划",
        data.form_depth === "full" ? "生产环境需填写完整发布计划。" : "开发环境可使用极简计划。",
        `${failedHint}${envIssues}${summaryGrid([...rows, ["计划深度", esc(data.form_depth === "full" ? "完整计划" : "极简计划"), "ready"]])}`,
        `${noOrderActions}
        ${oid ? `<a class="cj-btn release" href="${esc(editHref)}">编辑计划</a>` : ""}
        ${oid ? `<a class="cj-btn neutral" href="${esc(detailHref)}">发布单详情</a>` : ""}
        ${oid && status !== "build_failed" ? `<button type="button" class="cj-btn release" id="cjPrecheck">执行预检</button>` : ""}`,
        oid ? "ready" : (versionId ? "pending" : "pending"),
      );
    }

    if (status === "awaiting_approval") {
      return panel(
        "待审批",
        "生产环境预检已通过，需审批后才能发布。",
        summaryGrid(rows),
        `${oid ? `<a class="cj-btn release" href="${esc(detailHref)}">前往审批</a>` : ""}
        ${oid ? `<a class="cj-btn neutral" href="${esc(detailHref)}">查看详情</a>` : ""}`,
        "pending",
      );
    }

    if (status === "prechecking" || status === "ready" || status === "approved") {
      const isGray = String(state.release_strategy || "") === "gray";
      const publishLabel = isGray
        ? `灰度发布 (${esc(state.gray_ratio || state.rollout_percentage || "10")}%)`
        : "全量发布";
      const publishHint = isGray
        ? "预检已通过，将按发布计划中的灰度比例写入 bootstrap rollout。"
        : (status === "approved" || data.form_depth !== "full" ? "预检已通过，可执行发布。" : "预检已通过，等待审批。");
      return panel(
        "发布操作",
        publishHint,
        summaryGrid(rows),
        `<button type="button" class="cj-btn release" id="cjPublish">${publishLabel}</button>
        ${oid ? `<a class="cj-btn neutral" href="${esc(editHref)}">编辑计划</a>` : ""}
        ${oid ? `<a class="cj-btn neutral" href="${esc(detailHref)}">查看详情</a>` : ""}`,
        "pending",
      );
    }

    if (status === "published") {
      const grayActive = !!state.is_gray_active;
      const rolloutPct = esc(state.rollout_percentage ?? state.gray_ratio ?? "100");
      const grayMonitor = grayActive
        ? `<p class="cj-section-label">灰度放量</p>
           <p class="cj-empty-hint">当前 rollout ${rolloutPct}%，客户端 bootstrap 仅对该比例设备生效。</p>`
        : "";
      const expandBtn = state.can_expand_gray
        ? `<button type="button" class="cj-btn release" id="cjExpandGray">扩大至 100%</button>`
        : "";
      return panel(
        grayActive ? "灰度验证" : "验证",
        grayActive ? "灰度发布已生效，请验证核心链路后再全量放量。" : "发布已完成，请验证核心链路。",
        `${grayMonitor}${summaryGrid([...rows, ["Rollout", `${rolloutPct}%`, grayActive ? "pending" : "ready"], ["验证", esc(state.verify_status || "待验证"), "pending"]])}`,
        `${expandBtn}
        <button type="button" class="cj-btn release" id="cjVerifyPass">验证通过</button>
        <button type="button" class="cj-btn warn" id="cjVerifyFail">验证失败</button>
        ${oid ? `<a class="cj-btn neutral" href="${esc(detailHref)}">查看详情</a>` : ""}`,
        "pending",
      );
    }

    if (status === "verified" || status === "verify_failed") {
      const bundleList = (state.publishable_bundles || []).length
        ? `<p class="cj-section-label">历史 Bundle（回滚目标）</p><ul class="cj-list">${(state.publishable_bundles || []).map((b) =>
          `<li><span>${esc(b.version_name)} / ${esc(b.version_code)} <span class="cj-badge ${b.is_active ? "live" : "ready"}">${b.is_active ? "线上" : esc(b.publish_status)}</span></span>
          <button type="button" class="cj-btn warn" data-pick-bundle="${esc(b.bundle_id)}">选为回滚目标</button></li>`).join("")}</ul>`
        : "";
      return panel(
        "回滚与下线",
        "可回滚到历史 Bundle 或撤回当前线上版本。",
        `${summaryGrid(rows)}${bundleList}`,
        `<button type="button" class="cj-btn warn" id="cjRollback">回滚到选定 Bundle</button>
        <button type="button" class="cj-btn warn" id="cjUnpublish">撤回下线</button>
        ${oid ? `<button type="button" class="cj-btn neutral" id="cjCancelOrder">取消发布单</button>` : ""}`,
        "pending",
      );
    }

    return panel(
      "发版监测",
      "跟踪当前发版单状态，必要时进入详情页。",
      summaryGrid(rows),
      `${oid ? `<a class="cj-btn neutral" href="${esc(detailHref)}">查看详情</a>` : ""}
      <button type="button" class="cj-btn release" id="cjPrecheck">执行预检</button>`,
      "ready",
    );
  };

  const bindPanelActions = (state) => {
    document.querySelectorAll("[data-pick-bundle]").forEach((btn) => {
      btn.onclick = () => { bundleId = btn.getAttribute("data-pick-bundle") || ""; syncUrl(); load(); };
    });
    const oid = state.release_order_id || "";
    const scopeId = state.scope_id || "";
    const ensureApi = state.ensure_order_api || "";

    document.getElementById("cjEnsureOrder")?.addEventListener("click", async () => {
      if (!ensureApi) return toast("缺少创建发布单接口", "error");
      try {
        const result = await api(ensureApi, { method: "POST", body: "{}" });
        toast("发布单已创建");
        if (result?.release_order_id) {
          versionId = versionId || result.version_id || "";
          syncUrl();
        }
        load();
      } catch (e) { toast(e.message, "error"); }
    });

    document.getElementById("cjPrecheck")?.addEventListener("click", async () => {
      let orderId = oid;
      if (!orderId && ensureApi) {
        try {
          const created = await api(ensureApi, { method: "POST", body: "{}" });
          orderId = created?.release_order_id || "";
        } catch (e) {
          return toast(e.message, "error");
        }
      }
      if (!orderId) return toast("请先选择 VersionCode 并创建发布单", "error");
      try {
        await api(precheckUrl(orderId), { method: "POST", body: "{}" });
        toast("预检已执行");
        load();
      } catch (e) { toast(e.message, "error"); }
    });

    const publish = async () => {
      if (!oid) throw new Error("请先选择目标版本并创建发布单");
      await api(`/api/projects/${encodeURIComponent(projectId)}/release-orders/${encodeURIComponent(oid)}/publish`, { method: "POST", body: "{}" });
      toast("发布已执行");
      load();
    };

    document.getElementById("cjPublish")?.addEventListener("click", () => publish().catch((e) => toast(e.message, "error")));

    document.getElementById("cjExpandGray")?.addEventListener("click", async () => {
      if (!oid) return toast("缺少发布单", "error");
      try {
        await api(`/api/projects/${encodeURIComponent(projectId)}/release-orders/${encodeURIComponent(oid)}/expand-gray`, {
          method: "POST",
          body: JSON.stringify({ target_ratio: 100 }),
        });
        toast("已扩大至 100%");
        load();
      } catch (e) { toast(e.message, "error"); }
    });

    document.getElementById("cjVerifyPass")?.addEventListener("click", async () => {
      if (!oid) return toast("缺少发布单", "error");
      try {
        await api(`/api/projects/${encodeURIComponent(projectId)}/release-orders/${encodeURIComponent(oid)}/verify`, { method: "POST", body: JSON.stringify({ ok: true }) });
        toast("验证通过");
        load();
      } catch (e) { toast(e.message, "error"); }
    });
    document.getElementById("cjVerifyFail")?.addEventListener("click", async () => {
      if (!oid) return toast("缺少发布单", "error");
      try {
        await api(`/api/projects/${encodeURIComponent(projectId)}/release-orders/${encodeURIComponent(oid)}/verify`, { method: "POST", body: JSON.stringify({ ok: false }) });
        toast("已标记验证失败");
        load();
      } catch (e) { toast(e.message, "error"); }
    });
    document.getElementById("cjRollback")?.addEventListener("click", async () => {
      if (!scopeId || !bundleId) return toast("请先在下方列表选择要回滚到的 Bundle", "error");
      try {
        const reason = promptReason("回滚");
        await api(`/api/projects/${encodeURIComponent(projectId)}/scopes/${encodeURIComponent(scopeId)}/rollback`, {
          method: "POST",
          body: JSON.stringify({ target_bundle_id: bundleId, reason }),
        });
        toast("已回滚");
        load();
      } catch (e) { toast(e.message, "error"); }
    });
    document.getElementById("cjUnpublish")?.addEventListener("click", async () => {
      if (!scopeId) return toast("缺少 Scope", "error");
      try {
        const reason = promptReason("撤回下线");
        await api(`/api/projects/${encodeURIComponent(projectId)}/scopes/${encodeURIComponent(scopeId)}/unpublish`, {
          method: "POST",
          body: JSON.stringify({ reason }),
        });
        toast("已撤回下线");
        load();
      } catch (e) { toast(e.message, "error"); }
    });
    document.getElementById("cjCancelOrder")?.addEventListener("click", async () => {
      if (!oid) return;
      try {
        const reason = promptReason("取消发布单");
        await api(`/api/projects/${encodeURIComponent(projectId)}/release-orders/${encodeURIComponent(oid)}/cancel`, {
          method: "POST",
          body: JSON.stringify({ reason }),
        });
        toast("发布单已取消");
        load();
      } catch (e) { toast(e.message, "error"); }
    });
  };

  const load = async () => {
    const main = document.getElementById("cjReleaseMain");
    try {
      const qs = new URLSearchParams();
      if (platform) qs.set("platform", platform);
      if (versionId) qs.set("version_id", versionId);
      if (bundleId) qs.set("bundle_id", bundleId);
      const data = await api(`/api/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(envKey)}/channels/${encodeURIComponent(channelId)}/release-journey?${qs}`);
      platform = data.platform || platform;
      if (!versionId && data.selected_version_id) versionId = data.selected_version_id;
      if (!bundleId && data.selected_bundle_id) bundleId = data.selected_bundle_id;
      let state = (data.per_platform || {})[platform] || {};
      if (ensureDefaultVersionId(state)) return load();
      state = mergeSelectedVersionState(state);
      document.getElementById("cjReleaseTitle").textContent = `发版流程 · ${data.channel_name || channelId}`;
      document.getElementById("cjReleaseSubtitle").textContent = `${data.env_label || envKey} · ${data.channel_name || channelId}`;
      renderPlatforms(document.getElementById("cjReleasePlatforms"), data.platforms || [], platform);
      renderContext(data, state);
      renderVersionPicker(state);
      bindVersionPicker(state);
      if (main) main.innerHTML = renderWorkspace(data, state);
      bindPanelActions(state);
      bindRuntimeStart(state);
    } catch (e) {
      if (main) main.innerHTML = `<div class="ui-empty">${esc(e.message)}</div>`;
    }
  };

  load();
})();
