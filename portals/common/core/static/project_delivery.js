(() => {
  const page = document.querySelector("[data-delivery-page]");
  if (!page) return;
  const projectId = page.dataset.projectId;
  const api = (path, options) => fetch(path, options).then(async (response) => {
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || "请求失败");
    return data.data;
  });
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  const statusLabels = {
    draft: "草稿", building: "构建中", artifacts_ready: "产物已就绪", prechecking: "预检中",
    precheck_failed: "预检失败", ready: "可发布", awaiting_approval: "待审批", approved: "已审批",
    publishing: "发布中", published: "已发布", publish_failed: "发布失败", verifying: "验证中",
    verified: "验证通过", verify_failed: "验证失败", rolled_back: "已回滚", cancelled: "已取消"
  };
  const envLabels = { development: "开发环境", testing: "测试环境", staging: "预发环境", production: "生产环境" };
  const healthLabels = { healthy: "运行正常", processing: "处理中", warning: "待处理", blocked: "存在阻断", unconfigured: "尚未配置" };

  async function loadOverview() {
    const data = await api(`/api/projects/${encodeURIComponent(projectId)}/overview`);
    const cards = data.environments || [];
    const totals = {
      orders: cards.reduce((sum, row) => sum + row.release_order_count, 0),
      active: cards.filter((row) => row.active_bundle_id).length,
      pending: cards.reduce((sum, row) => sum + row.pending_approval_count, 0),
      blocked: cards.reduce((sum, row) => sum + row.failed_count, 0)
    };
    document.getElementById("deliverySummary").innerHTML = [
      ["发布单总数", totals.orders], ["已生效环境", totals.active], ["待审批", totals.pending], ["阻断项", totals.blocked]
    ].map(([label, value]) => `<div class="delivery-summary-card"><span>${label}</span><strong>${value}</strong></div>`).join("");
    document.getElementById("environmentCards").innerHTML = cards.map((row) => `
      <article class="environment-card ${esc(row.health)}">
        <div class="environment-head"><div><h2>${esc(row.env_label)}</h2><p>${esc((row.channels || []).join(" / ") || "尚未产生发布单")}</p></div><span class="environment-status">${esc(healthLabels[row.health] || row.health)}</span></div>
        <div class="environment-metrics">
          <div class="environment-metric"><span>当前版本</span><strong>${esc(row.version_name || "-")} ${esc(row.version_code || "")}</strong></div>
          <div class="environment-metric"><span>Active Bundle</span><strong>${esc(row.active_bundle_id || "-")}</strong></div>
          <div class="environment-metric"><span>当前拓扑</span><strong>${esc(row.topology_id || "-")}</strong></div>
          <div class="environment-metric"><span>发布单</span><strong>${row.release_order_count}</strong></div>
          <div class="environment-metric"><span>待审批</span><strong>${row.pending_approval_count}</strong></div>
          <div class="environment-metric"><span>阻断</span><strong>${row.failed_count}</strong></div>
        </div>
        <div class="environment-details">运行实例：${esc(row.runtime_run_id || "未运行")} · 平台：${esc((row.platforms || []).join(" / ") || "未配置")}</div>
        <div class="environment-actions">
          <a class="delivery-primary" href="/admin/projects/${encodeURIComponent(projectId)}/release-orders?env_key=${row.env_key}">查看发布单</a>
          <a class="delivery-secondary" href="/admin/projects/${encodeURIComponent(projectId)}/topologies?env_key=${row.env_key}">查看拓扑</a>
          <a class="delivery-secondary" href="/admin/projects/${encodeURIComponent(projectId)}/agents?env_key=${row.env_key}">进入运维</a>
        </div>
      </article>`).join("");
  }

  function orderCard(row) {
    return `<a class="order-card" href="/admin/projects/${encodeURIComponent(projectId)}/release-orders/${encodeURIComponent(row.release_order_id)}">
      <div class="order-main"><strong>${esc(row.version_name)} · ${esc(row.version_code)}</strong><span>${esc(row.release_order_id)}</span></div>
      <div class="order-field"><span>目标</span><strong>${esc(envLabels[row.env_key])} / ${esc(row.channel_name)}</strong></div>
      <div class="order-field"><span>平台</span><strong>${esc(row.platform)}</strong></div>
      <div class="order-field"><span>拓扑</span><strong>${esc(row.topology_id || "待解析")}</strong></div>
      <div class="order-field"><span>更新时间</span><strong>${esc(row.updated_at || "-")}</strong></div>
      <span class="order-status ${esc(row.status)}">${esc(statusLabels[row.status] || row.status)}</span>
    </a>`;
  }

  async function loadOrders() {
    const params = new URLSearchParams();
    page.querySelectorAll("[data-filter]").forEach((select) => { if (select.value) params.set(select.dataset.filter, select.value); });
    const rows = await api(`/api/projects/${encodeURIComponent(projectId)}/release-orders?${params}`);
    document.getElementById("releaseOrderList").innerHTML = rows.length ? rows.map(orderCard).join("") : '<div class="delivery-empty">当前筛选条件下暂无发布单。</div>';
  }

  async function setupOrders() {
    const options = await api(`/api/projects/${encodeURIComponent(projectId)}/context-options`);
    const fill = (select, rows, valueKey, labelKey) => {
      const first = select.options[0]?.outerHTML || "";
      select.innerHTML = first + rows.map((row) => `<option value="${esc(row[valueKey])}">${esc(row[labelKey])}</option>`).join("");
    };
    fill(page.querySelector('[data-filter="env_key"]'), options.environments, "env_key", "label");
    fill(page.querySelector('[data-filter="channel_id"]'), options.channels, "channel_id", "channel_name");
    fill(page.querySelector('[data-filter="platform"]'), options.platforms, "value", "label");
    const status = page.querySelector('[data-filter="status"]');
    Object.entries(statusLabels).forEach(([value, label]) => status.insertAdjacentHTML("beforeend", `<option value="${value}">${label}</option>`));
    const search = new URLSearchParams(location.search);
    page.querySelectorAll("[data-filter]").forEach((select) => { if (search.get(select.dataset.filter)) select.value = search.get(select.dataset.filter); });
    const dialog = document.getElementById("createOrderDialog");
    const form = document.getElementById("createOrderForm");
    fill(form.elements.env_key, options.environments, "env_key", "label");
    fill(form.elements.channel_id, options.channels, "channel_id", "channel_name");
    fill(form.elements.platform, options.platforms, "value", "label");
    const renderVersions = (preferredVersionCode = "") => {
      const envKey = form.elements.env_key.value;
      const channelId = form.elements.channel_id.value;
      const platform = form.elements.platform.value || "android";
      const versions = (options.versions || []).filter((row) =>
        (row.platform || "android") === platform &&
        row.env_key === envKey &&
        row.channel_id === channelId
      );
      form.elements.version_id.innerHTML = versions.map((row) => `<option value="${esc(row.id)}" data-platform="${esc(row.platform || "android")}">${esc(row.version_name || "-")} / ${esc(row.version_code || "-")} / ${esc(row.platform || "android")}</option>`).join("");
      const preferred = versions.find((row) => String(row.version_code || "") === preferredVersionCode);
      if (preferred) form.elements.version_id.value = preferred.id;
    };
    const applySearchToForm = () => {
      if (search.get("env_key")) form.elements.env_key.value = search.get("env_key");
      if (search.get("channel_id")) form.elements.channel_id.value = search.get("channel_id");
      if (search.get("platform")) form.elements.platform.value = search.get("platform");
      renderVersions(search.get("version_code") || "");
    };
    applySearchToForm();
    form.elements.env_key.addEventListener("change", () => renderVersions());
    form.elements.channel_id.addEventListener("change", () => renderVersions());
    form.elements.platform.addEventListener("change", () => renderVersions());
    document.querySelector("[data-open-create-order]").addEventListener("click", () => {
      applySearchToForm();
      dialog.showModal();
    });
    document.querySelector("[data-refresh-orders]").addEventListener("click", loadOrders);
    page.querySelectorAll("[data-filter]").forEach((select) => select.addEventListener("change", loadOrders));
    form.addEventListener("submit", async (event) => {
      if (event.submitter?.value === "cancel") return;
      event.preventDefault();
      const selected = form.elements.version_id.selectedOptions[0];
      form.elements.platform.value = selected?.dataset.platform || form.elements.platform.value;
      try {
        const row = await api(`/api/projects/${encodeURIComponent(projectId)}/release-orders`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(Object.fromEntries(new FormData(form).entries()))
        });
        location.href = `/admin/projects/${encodeURIComponent(projectId)}/release-orders/${encodeURIComponent(row.release_order_id)}`;
      } catch (error) { alert(error.message); }
    });
    if (search.get("create") === "1") {
      applySearchToForm();
      dialog.showModal();
    }
    loadOrders();
  }

  async function loadOrderDetail() {
    const orderId = page.dataset.orderId;
    const row = await api(`/api/projects/${encodeURIComponent(projectId)}/release-orders/${encodeURIComponent(orderId)}`);
    document.getElementById("orderTitle").textContent = `${row.version_name} · ${row.version_code}`;
    document.getElementById("orderSubtitle").textContent = `${envLabels[row.env_key]} / ${row.channel_name} / ${row.platform} · ${row.release_order_id}`;
    const steps = ["draft", "building", "artifacts_ready", "ready", "approved", "published", "verified"];
    const stepLabels = ["目标确认", "构建", "产物", "预检", "审批", "发布", "验证"];
    const currentIndex = Math.max(0, steps.indexOf(row.status));
    document.getElementById("orderSteps").innerHTML = stepLabels.map((label, index) => `<div class="delivery-step ${index <= currentIndex ? "active" : ""}">${index + 1}. ${label}</div>`).join("");
    document.getElementById("orderKpis").innerHTML = [
      ["当前状态", statusLabels[row.status] || row.status], ["Scope", row.scope_id || "-"], ["拓扑", row.topology_id || "-"],
      ["Runtime", row.runtime_run_id || "-"], ["Bundle", row.bundle_id || "-"]
    ].map(([label, value]) => `<div class="order-kpi"><span>${label}</span><strong title="${esc(value)}">${esc(value)}</strong></div>`).join("");
    document.getElementById("orderArtifacts").innerHTML = (row.artifacts || []).map((item) => `<div class="delivery-row"><strong>${esc(item.artifact_type)}</strong><span>${esc(item.artifact_url || item.artifact_path || "未登记")}</span><b>${esc(item.status)}</b></div>`).join("") || '<div class="delivery-empty">暂无产物</div>';
    document.getElementById("orderRuntime").innerHTML = [
      ["拓扑绑定来源", row.topology_binding_source || "待解析"], ["topology_id", row.topology_id || "-"], ["runtime_run_id", row.runtime_run_id || "-"]
    ].map(([label, value]) => `<div class="delivery-row"><strong>${label}</strong><span>${esc(value)}</span></div>`).join("");
    const check = row.latest_precheck || {};
    const checkPayload = check.payload || {};
    const checkProblems = (checkPayload.missing_client_fields || [])
      .concat(checkPayload.missing_profile_fields || [])
      .concat(checkPayload.missing_artifact_fields || []);
    if (checkPayload.runtime_error) checkProblems.push(checkPayload.runtime_error);
    document.getElementById("orderPrecheck").innerHTML = check.created_at ? `
      <div class="delivery-row"><strong>${check.ok ? "通过" : "阻断"}</strong><span>${esc(check.created_at)}</span><b>${esc(checkProblems.join("、") || "无缺失项")}</b></div>` : '<div class="delivery-empty">尚未执行预检</div>';
    document.getElementById("orderEvents").innerHTML = (row.events || []).map((event) => `<div class="delivery-row"><strong>${esc(event.event_type)}</strong><span>${esc(event.actor)} · ${esc(event.created_at)}</span><b>${esc(event.to_status || "-")}</b></div>`).join("");
    const actionRules = {
      build: !["published", "verified", "rolled_back", "cancelled"].includes(row.status),
      precheck: ["draft", "artifacts_ready", "precheck_failed", "ready"].includes(row.status),
      approve: row.status === "awaiting_approval",
      publish: ["ready", "approved"].includes(row.status),
      verify: ["published", "verify_failed"].includes(row.status),
      rollback: Boolean(row.bundle_id) && Boolean(row.active_bundle_id) && row.bundle_id !== row.active_bundle_id,
      cancel: !["published", "verified", "rolled_back", "cancelled"].includes(row.status)
    };
    const actions = [
      ["build", "触发构建", "delivery-secondary"], ["precheck", "执行预检", "delivery-primary"],
      ["approve", "审批通过", "delivery-secondary"], ["publish", "执行发布", "delivery-primary"],
      ["verify", "验证通过", "delivery-secondary"], ["rollback", "回滚至此版本", "delivery-secondary"], ["cancel", "取消发布单", "delivery-secondary"]
    ];
    document.getElementById("orderActions").innerHTML = actions.map(([action, label, cls]) => `<button class="${cls}" data-order-action="${action}" ${actionRules[action] ? "" : "disabled"}>${label}</button>`).join("");
    document.querySelectorAll("[data-order-action]").forEach((button) => button.addEventListener("click", async () => {
      if (!confirm(`确定执行“${button.textContent}”吗？`)) return;
      try {
        await api(`/api/projects/${encodeURIComponent(projectId)}/release-orders/${encodeURIComponent(orderId)}/${button.dataset.orderAction}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        loadOrderDetail();
      } catch (error) { alert(error.message); }
    }));
  }

  const type = page.dataset.deliveryPage;
  if (type === "overview") loadOverview().catch((error) => document.getElementById("environmentCards").innerHTML = `<div class="delivery-empty">${esc(error.message)}</div>`);
  if (type === "orders") setupOrders().catch((error) => alert(error.message));
  if (type === "order-detail") loadOrderDetail().catch((error) => alert(error.message));
})();
