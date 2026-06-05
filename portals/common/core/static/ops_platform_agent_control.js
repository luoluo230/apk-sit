(function () {
  const root = document.querySelector(".agent-screen--control");
  if (!root || !window.OpsApi) return;

  const POLL_MS = 2000;
  const state = {
    projectId: String(root.dataset.projectId || ""),
    agents: [],
    rows: [],
    filteredRows: [],
    selectedIds: new Set(),
    page: 1,
    pageSize: 6,
    view: "card",
    pollTimer: null,
    summaryExtra: { pending: 0, running: 0 },
    createMode: false,
    menuRowId: "",
    expandedServiceRowIds: new Set(),
    filters: {
      status: "",
      query: "",
      serviceStatus: "",
      fresh: "active_120",
    },
  };

  const nodes = {
    summary: document.getElementById("agentSummaryCards"),
    cards: document.getElementById("agentCards"),
    list: document.getElementById("agentList"),
    meta: document.getElementById("agentResultsMeta"),
    paginationMeta: document.getElementById("agentPaginationMeta"),
    pageIndicator: document.getElementById("pageIndicator"),
    pageSize: document.getElementById("pageSizeSelect"),
    selectPage: document.getElementById("selectPage"),
    selectedCount: document.getElementById("selectedCountLabel"),
    cardView: document.getElementById("btnCardView"),
    listView: document.getElementById("btnListView"),
    filterStatus: document.getElementById("filterStatus"),
    filterQuery: document.getElementById("filterQuery"),
    filterServiceStatus: document.getElementById("filterServiceStatus"),
    filterFresh: document.getElementById("filterFresh"),
    batchMenu: document.getElementById("batchMoreMenu"),
    modal: document.getElementById("agentEditModal"),
    editTitle: document.getElementById("agentEditTitle"),
    editAgentId: document.getElementById("editAgentId"),
    editDeviceId: document.getElementById("editDeviceId"),
    editHostIp: document.getElementById("editHostIp"),
    editDisplayName: document.getElementById("editDisplayName"),
    editPort: document.getElementById("editPort"),
    editRunState: document.getElementById("editRunState"),
    editDesc: document.getElementById("editDesc"),
  };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function toast(message, tone) {
    const kind = tone === "error" ? "is-error" : "is-success";
    let node = document.getElementById("agentControlToast");
    if (!node) {
      node = document.createElement("div");
      node.id = "agentControlToast";
      node.className = "agent-inline-note";
      node.style.position = "fixed";
      node.style.right = "24px";
      node.style.bottom = "24px";
      node.style.zIndex = "60";
      node.style.minWidth = "260px";
      document.body.appendChild(node);
    }
    node.className = "agent-inline-note " + kind;
    node.textContent = message;
    clearTimeout(node._timer);
    node._timer = setTimeout(function () {
      node.remove();
    }, 2600);
  }

  function ensureOk(response, fallback) {
    if (response && (response.error_code === "OPS_AUTH_REQUIRED" || response.error === "auth_redirect")) {
      window.location.href = "/login";
      return false;
    }
    if (!response || !response.ok) {
      toast((response && (response.message || response.error)) || fallback || "请求失败", "error");
      return false;
    }
    return true;
  }

  function normalizeStatus(value) {
    const status = String(value || "").toUpperCase();
    if (["ONLINE", "READY", "RUNNING", "SUCCESS"].indexOf(status) >= 0) return "ONLINE";
    if (["OFFLINE", "STOPPED", "TIMEOUT", "CANCELED"].indexOf(status) >= 0) return "OFFLINE";
    if (["DEGRADED", "ERROR", "FAILED", "WARN", "WARNING"].indexOf(status) >= 0) return "WARN";
    return "UNKNOWN";
  }

  function statusText(status) {
    if (status === "ONLINE") return "在线";
    if (status === "OFFLINE") return "离线";
    if (status === "WARN") return "异常";
    return "未知";
  }

  function stateClass(status) {
    if (status === "ONLINE") return "agent-state-pill--ok";
    if (status === "OFFLINE") return "agent-state-pill--offline";
    if (status === "WARN") return "agent-state-pill--warn";
    return "agent-state-pill--info";
  }

  function formatDate(value) {
    if (!value) return "--";
    const ms = Date.parse(value);
    if (!Number.isFinite(ms)) return String(value);
    const date = new Date(ms);
    const pad = function (num) { return String(num).padStart(2, "0"); };
    return [
      date.getFullYear(),
      pad(date.getMonth() + 1),
      pad(date.getDate()),
    ].join("-") + " " + [pad(date.getHours()), pad(date.getMinutes()), pad(date.getSeconds())].join(":");
  }

  function ageSeconds(value) {
    if (!value) return Number.MAX_SAFE_INTEGER;
    const ms = Date.parse(value);
    if (!Number.isFinite(ms)) return Number.MAX_SAFE_INTEGER;
    return Math.max(0, Math.round((Date.now() - ms) / 1000));
  }

  function metricSource(agent) {
    const metrics = agent && typeof agent.metrics === "object" ? agent.metrics : {};
    const control = metrics && typeof metrics.control === "object" ? metrics.control : metrics;
    const snapshot = agent && agent.device_metrics_snapshot && typeof agent.device_metrics_snapshot.control === "object"
      ? agent.device_metrics_snapshot.control
      : {};
    return { control: control || {}, snapshot: snapshot || {} };
  }

  function metricValue(agent, key) {
    const source = metricSource(agent);
    const primary = Number(source.control[key]);
    if (Number.isFinite(primary)) return Math.max(0, Math.round(primary));
    const fallback = Number(source.snapshot[key]);
    if (Number.isFinite(fallback)) return Math.max(0, Math.round(fallback));
    return null;
  }

  function metricLabel(agent, key, prefix) {
    const value = metricValue(agent, key);
    return value == null ? (prefix + " --") : (prefix + " " + value + "%");
  }

  function summarizeServices(services) {
    const rows = Array.isArray(services) ? services : [];
    const summary = { total: rows.length, online: 0, abnormal: 0, offline: 0 };
    rows.forEach(function (service) {
      const status = normalizeStatus(service.status || service.run_state);
      if (status === "ONLINE") summary.online += 1;
      else if (status === "OFFLINE") summary.offline += 1;
      else summary.abnormal += 1;
    });
    return summary;
  }

  function summarizeServiceText(summary) {
    if (!summary.total) {
      return { tone: "offline", text: "暂无服务" };
    }
    if (summary.online === summary.total) {
      return { tone: "ok", text: "全部正常" };
    }
    if (summary.offline === summary.total) {
      return { tone: "offline", text: "全部离线" };
    }
    return { tone: "warn", text: "服务异常 " + (summary.total - summary.online) };
  }

  function pickTitle(agent) {
    return String(agent.device_id || agent.display_name || agent.agent_id || "unknown-agent");
  }

  function buildRows(agents) {
    return (Array.isArray(agents) ? agents : []).map(function (agent) {
      const services = Array.isArray(agent.services) ? agent.services : [];
      const summary = summarizeServices(services);
      const summaryText = summarizeServiceText(summary);
      const status = normalizeStatus(agent.effective_status || agent.status);
      const rowId = String(agent.agent_id || agent.device_id || "");
      return {
        rowId: rowId,
        agentId: String(agent.agent_id || ""),
        deviceId: String(agent.device_id || ""),
        title: pickTitle(agent),
        status: status,
        statusText: statusText(status),
        ip: String(agent.host_ip || agent.host_name || (agent.placement || {}).host_ip || "--"),
        heartbeat: formatDate(agent.last_seen),
        freshAge: Number(agent.last_seen_age_sec),
        description: String(agent.desc || ""),
        services: services,
        serviceSummary: summary,
        serviceTone: summaryText.tone,
        serviceText: summaryText.text,
        cpuText: metricLabel(agent, "cpu_percent", "CPU"),
        memText: metricLabel(agent, "mem_percent", "MEM"),
        diskText: metricLabel(agent, "disk_percent", "DISK"),
        raw: agent,
      };
    });
  }

  function filteredByFresh(row) {
    if (state.filters.fresh === "all") return true;
    if (!Number.isFinite(row.freshAge)) return false;
    if (state.filters.fresh === "active_120") return row.freshAge <= 120;
    if (state.filters.fresh === "active_600") return row.freshAge <= 600;
    return true;
  }

  function matchesFilters(row) {
    if (state.filters.status) {
      if (state.filters.status === "DEGRADED" && row.status !== "WARN") return false;
      if (state.filters.status === "OFFLINE" && row.status !== "OFFLINE") return false;
      if (state.filters.status === "ONLINE" && row.status !== "ONLINE") return false;
    }

    const query = String(state.filters.query || "").trim().toLowerCase();
    if (query) {
      const haystack = [
        row.title,
        row.agentId,
        row.deviceId,
        row.ip,
        row.description,
        row.services.map(function (service) { return service.service_id || service.display_name || ""; }).join(" "),
      ].join(" ").toLowerCase();
      if (haystack.indexOf(query) < 0) return false;
    }

    if (state.filters.serviceStatus === "healthy" && row.serviceTone !== "ok") return false;
    if (state.filters.serviceStatus === "abnormal" && row.serviceTone !== "warn") return false;
    if (state.filters.serviceStatus === "offline" && row.serviceTone !== "offline") return false;

    return filteredByFresh(row);
  }

  function cardHref(row, extra) {
    let href = "/admin/ops-platform/agent-detail?project_id=" + encodeURIComponent(state.projectId) +
      "&agent_id=" + encodeURIComponent(row.agentId || row.rowId);
    if (row.deviceId) href += "&preview=" + encodeURIComponent(row.deviceId);
    if (extra) href += "&tab=" + encodeURIComponent(extra);
    return href;
  }

  function currentPageRows() {
    const start = (state.page - 1) * state.pageSize;
    return state.filteredRows.slice(start, start + state.pageSize);
  }

  function queueHref(status) {
    let href = "/admin/ops-platform/actions?project_id=" + encodeURIComponent(state.projectId);
    if (status) href += "&job_status=" + encodeURIComponent(status);
    href += "#queue";
    return href;
  }

  function renderSummary() {
    const online = state.rows.filter(function (row) { return row.status === "ONLINE"; }).length;
    const cards = [
      { tone: "blue", icon: "⌘", title: "在线 Agent", value: online, desc: "实时在线设备数", href: "" },
      { tone: "green", icon: "◌", title: "注册 Agent", value: state.rows.length, desc: "已注册设备总数", href: "" },
      { tone: "orange", icon: "◔", title: "待执行任务", value: state.summaryExtra.pending, desc: "等待执行的任务数", href: queueHref("PENDING") },
      { tone: "purple", icon: "▶", title: "运行任务", value: state.summaryExtra.running, desc: "正在运行的任务数", href: queueHref("RUNNING") },
    ];
    nodes.summary.innerHTML = cards.map(function (card) {
      return "" +
        '<article class="agent-summary-card' + (card.href ? " is-clickable" : "") + '" data-tone="' + esc(card.tone) + '"' + (card.href ? (' data-summary-href="' + esc(card.href) + '"') : "") + '>' +
          '<div class="agent-summary-icon">' + esc(card.icon) + "</div>" +
          "<div>" +
            '<div class="agent-summary-label">' + esc(card.title) + "</div>" +
            '<div class="agent-summary-value">' + esc(card.value) + "</div>" +
            '<div class="agent-summary-desc">' + esc(card.desc) + "</div>" +
          "</div>" +
        "</article>";
    }).join("");
  }

  function bindSummaryCards() {
    nodes.summary.querySelectorAll("[data-summary-href]").forEach(function (node) {
      node.onclick = function () {
        const href = String(node.getAttribute("data-summary-href") || "");
        if (!href) return;
        window.location.href = href;
      };
    });
  }

  function renderServiceList(row) {
    const allServices = Array.isArray(row.services) ? row.services : [];
    const expanded = state.expandedServiceRowIds.has(row.rowId);
    const visibleServices = expanded ? allServices : allServices.slice(0, 4);
    if (!visibleServices.length) {
      return '<div class="agent-card-service-empty">暂无已管理服务器</div>';
    }
    const items = visibleServices.map(function (service) {
      const status = normalizeStatus(service.status || service.run_state);
      const label = statusText(status);
      const text = service.display_name || service.service_id || "-";
      return "" +
        '<li class="agent-card-service-item">' +
          '<span class="agent-card-service-id" title="' + esc(text) + '">' + esc(text) + "</span>" +
          '<span class="agent-card-service-badge agent-card-service-badge--' + esc(status.toLowerCase()) + '">' + esc(label) + "</span>" +
        "</li>";
    }).join("");
    const more = allServices.length > 4
      ? '<li><button class="agent-card-service-more" type="button" data-toggle-services="' + esc(row.rowId) + '">' +
          (expanded ? "收起服务器列表" : ("更多 " + esc(allServices.length - 4) + " 项")) +
        "</button></li>"
      : "";
    return '<ul class="agent-card-service-list">' + items + more + "</ul>";
  }

  function renderCard(row) {
    const selected = state.selectedIds.has(row.rowId);
    const cardClass = [
      "agent-card",
      selected ? "is-selected" : "",
      row.status === "WARN" ? "is-warning" : "",
      row.status === "OFFLINE" ? "is-offline" : "",
    ].join(" ").trim();
    return "" +
      '<article class="' + cardClass + '">' +
        '<div class="agent-card-head">' +
          '<label class="agent-card-select">' +
            '<input type="checkbox" data-select-row="' + esc(row.rowId) + '"' + (selected ? " checked" : "") + ">" +
          "</label>" +
          '<div class="agent-card-main">' +
            '<div class="agent-card-row">' +
              '<div class="agent-card-title-wrap">' +
                '<span class="agent-card-device">▣</span>' +
                '<div class="agent-card-title">' + esc(row.title) + "</div>" +
                '<span class="agent-state-pill ' + stateClass(row.status) + '">' + esc(row.statusText) + "</span>" +
              "</div>" +
              '<div class="agent-card-menu-wrap">' +
                '<button class="agent-card-more" type="button" data-open-menu="' + esc(row.rowId) + '">⋮</button>' +
                '<div class="agent-dropdown-menu agent-card-menu' + (state.menuRowId === row.rowId ? "" : " is-hidden") + '">' +
                  '<button type="button" data-menu-action="detail" data-row-id="' + esc(row.rowId) + '">查看详情</button>' +
                  '<button type="button" data-menu-action="probe" data-row-id="' + esc(row.rowId) + '">立即探测</button>' +
                  '<button type="button" data-menu-action="restart" data-row-id="' + esc(row.rowId) + '">重启 Agent</button>' +
                  '<button type="button" data-menu-action="edit" data-row-id="' + esc(row.rowId) + '">编辑 Agent</button>' +
                  '<button type="button" data-menu-action="logs" data-row-id="' + esc(row.rowId) + '">查看日志</button>' +
                "</div>" +
              "</div>" +
            "</div>" +
            '<div class="agent-card-meta">' +
              "<span>IP: " + esc(row.ip) + "</span>" +
              "<span>最后心跳: " + esc(row.heartbeat) + "</span>" +
            "</div>" +
            '<div class="agent-card-body-split">' +
              '<div class="agent-card-left">' +
                '<div class="agent-card-metrics">' +
                  '<span class="agent-metric-pill" data-tone="cpu">' + esc(row.cpuText) + "</span>" +
                  '<span class="agent-metric-pill" data-tone="mem">' + esc(row.memText) + "</span>" +
                  '<span class="agent-metric-pill" data-tone="disk">' + esc(row.diskText) + "</span>" +
                "</div>" +
                '<div class="agent-card-service">' +
                  "<strong>服务 " + esc(row.serviceSummary.online) + " / " + esc(row.serviceSummary.total) + "</strong>" +
                  '<span class="agent-service-text agent-service-text--' + esc(row.serviceTone) + '">' + esc(row.serviceText) + "</span>" +
                "</div>" +
              "</div>" +
              '<div class="agent-card-right">' +
                '<div class="agent-card-service-panel">' +
                  '<div class="agent-card-service-panel-title">管理服务器</div>' +
                  renderServiceList(row) +
                "</div>" +
              "</div>" +
            "</div>" +
            '<div class="agent-card-actions">' +
              '<a class="agent-card-action" href="' + esc(cardHref(row)) + '">查看详情</a>' +
              '<button class="agent-card-action is-edit" type="button" data-edit-row="' + esc(row.rowId) + '">编辑</button>' +
              '<button class="agent-card-action is-primary" type="button" data-probe-row="' + esc(row.rowId) + '">探测</button>' +
            "</div>" +
          "</div>" +
        "</div>" +
      "</article>";
  }

  function renderTable() {
    const rows = currentPageRows();
    if (!rows.length) {
      nodes.list.innerHTML = '<div class="agent-empty">当前筛选条件下暂无 Agent</div>';
      return;
    }
    nodes.list.innerHTML = "" +
      '<div class="agent-table-shell">' +
        '<table class="agent-table">' +
          "<thead><tr><th></th><th>Agent / 设备</th><th>状态</th><th>IP / 最后心跳</th><th>资源</th><th>服务状态</th><th>操作</th></tr></thead>" +
          "<tbody>" +
            rows.map(function (row) {
              const selected = state.selectedIds.has(row.rowId);
              const servicesPreview = row.services.slice(0, 2).map(function (service) {
                return service.display_name || service.service_id || "-";
              }).join(" / ");
              return "" +
                "<tr>" +
                  '<td><input type="checkbox" data-select-row="' + esc(row.rowId) + '"' + (selected ? " checked" : "") + "></td>" +
                  "<td><strong>" + esc(row.title) + '</strong><div class="table-sub">' + esc(servicesPreview || "暂无服务") + "</div></td>" +
                  '<td><span class="agent-state-pill ' + stateClass(row.status) + '">' + esc(row.statusText) + "</span></td>" +
                  "<td>" + esc(row.ip) + '<div class="table-sub">' + esc(row.heartbeat) + "</div></td>" +
                  "<td>" + esc(row.cpuText) + " / " + esc(row.memText) + " / " + esc(row.diskText) + "</td>" +
                  '<td><strong>' + esc(row.serviceSummary.online) + " / " + esc(row.serviceSummary.total) + '</strong> <span class="agent-service-text agent-service-text--' + esc(row.serviceTone) + '">' + esc(row.serviceText) + "</span></td>" +
                  '<td><div class="agent-table-actions">' +
                    '<a class="agent-card-action" href="' + esc(cardHref(row)) + '">详情</a>' +
                    '<button class="agent-table-action" type="button" data-edit-row="' + esc(row.rowId) + '">编辑</button>' +
                    '<button class="agent-table-action" type="button" data-probe-row="' + esc(row.rowId) + '">探测</button>' +
                  "</div></td>" +
                "</tr>";
            }).join("") +
          "</tbody>" +
        "</table>" +
      "</div>";
  }

  function renderCards() {
    const rows = currentPageRows();
    if (!rows.length) {
      nodes.cards.innerHTML = '<div class="agent-empty">当前筛选条件下暂无 Agent</div>';
      return;
    }
    nodes.cards.innerHTML = rows.map(renderCard).join("");
  }

  function applyFilters() {
    state.filteredRows = state.rows.filter(matchesFilters);
    const totalPages = Math.max(1, Math.ceil(state.filteredRows.length / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;
  }

  function updateMeta() {
    const totalPages = Math.max(1, Math.ceil(state.filteredRows.length / state.pageSize));
    nodes.meta.innerHTML = "" +
      "<div><strong>" + esc(state.filteredRows.length) + "</strong> 个 Agent 符合当前筛选条件</div>" +
      "<div>视图：" + (state.view === "card" ? "卡片视图" : "列表视图") + " · 第 " + esc(state.page) + " / " + esc(totalPages) + " 页</div>";
    nodes.paginationMeta.textContent = "共 " + state.filteredRows.length + " 条";
    nodes.pageIndicator.textContent = String(state.page);
    nodes.selectedCount.textContent = "已选择 " + state.selectedIds.size + " 项";
    const pageRows = currentPageRows();
    nodes.selectPage.checked = pageRows.length > 0 && pageRows.every(function (row) {
      return state.selectedIds.has(row.rowId);
    });
  }

  function render() {
    applyFilters();
    renderSummary();
    updateMeta();
    renderCards();
    renderTable();
    nodes.cards.classList.toggle("is-hidden", state.view !== "card");
    nodes.list.classList.toggle("is-hidden", state.view !== "list");
    nodes.cardView.classList.toggle("is-active", state.view === "card");
    nodes.listView.classList.toggle("is-active", state.view === "list");
    bindSummaryCards();
    bindRows(nodes.cards);
    bindRows(nodes.list);
  }

  function rowById(rowId) {
    return state.rows.find(function (row) { return row.rowId === rowId; }) || null;
  }

  function setMenu(rowId) {
    state.menuRowId = rowId || "";
    render();
  }

  function bindRows(container) {
    container.querySelectorAll("[data-select-row]").forEach(function (node) {
      node.onchange = function () {
        const rowId = String(node.getAttribute("data-select-row") || "");
        if (!rowId) return;
        if (node.checked) state.selectedIds.add(rowId);
        else state.selectedIds.delete(rowId);
        updateMeta();
      };
    });
    container.querySelectorAll("[data-edit-row]").forEach(function (node) {
      node.onclick = function () {
        openEdit(String(node.getAttribute("data-edit-row") || ""));
      };
    });
    container.querySelectorAll("[data-probe-row]").forEach(function (node) {
      node.onclick = function () {
        handleProbe(String(node.getAttribute("data-probe-row") || ""));
      };
    });
    container.querySelectorAll("[data-open-menu]").forEach(function (node) {
      node.onclick = function (event) {
        event.stopPropagation();
        const rowId = String(node.getAttribute("data-open-menu") || "");
        setMenu(state.menuRowId === rowId ? "" : rowId);
      };
    });
    container.querySelectorAll("[data-menu-action]").forEach(function (node) {
      node.onclick = function (event) {
        event.stopPropagation();
        const rowId = String(node.getAttribute("data-row-id") || "");
        const action = String(node.getAttribute("data-menu-action") || "");
        setMenu("");
        handleMenuAction(rowId, action);
      };
    });
    container.querySelectorAll("[data-toggle-services]").forEach(function (node) {
      node.onclick = function () {
        const rowId = String(node.getAttribute("data-toggle-services") || "");
        if (!rowId) return;
        if (state.expandedServiceRowIds.has(rowId)) state.expandedServiceRowIds.delete(rowId);
        else state.expandedServiceRowIds.add(rowId);
        render();
      };
    });
  }

  function fillEditForm(row, createMode) {
    const agent = row ? row.raw : {};
    state.createMode = !!createMode;
    nodes.editTitle.textContent = createMode ? "新建设备 Agent" : "编辑 Agent";
    nodes.editAgentId.readOnly = !createMode;
    nodes.editAgentId.value = createMode ? ("agent-" + Date.now()) : String(agent.agent_id || "");
    nodes.editDeviceId.value = String(agent.device_id || "");
    nodes.editHostIp.value = String(agent.host_ip || agent.host_name || "");
    nodes.editDisplayName.value = String(agent.display_name || row && row.title || "");
    nodes.editPort.value = String(agent.remote_game_server_port || agent.port || "");
    nodes.editRunState.value = "";
    nodes.editDesc.value = String(agent.desc || "");
  }

  function openCreate() {
    fillEditForm(null, true);
    nodes.modal.classList.remove("is-hidden");
  }

  function openEdit(rowId) {
    const row = rowById(rowId);
    if (!row) {
      toast("未找到要编辑的 Agent", "error");
      return;
    }
    fillEditForm(row, false);
    nodes.modal.classList.remove("is-hidden");
  }

  function closeEdit() {
    nodes.modal.classList.add("is-hidden");
  }

  async function saveEdit() {
    const payload = {
      agent_id: String(nodes.editAgentId.value || "").trim(),
      project_id: state.projectId,
      device_id: String(nodes.editDeviceId.value || "").trim(),
      host_name: String(nodes.editHostIp.value || "").trim(),
      host_ip: String(nodes.editHostIp.value || "").trim(),
      display_name: String(nodes.editDisplayName.value || "").trim(),
      port: Number(nodes.editPort.value || 0),
      remote_game_server_port: Number(nodes.editPort.value || 0),
      run_state: String(nodes.editRunState.value || "").trim(),
      desc: String(nodes.editDesc.value || "").trim(),
      create_if_missing: state.createMode,
    };
    if (!payload.agent_id) {
      toast("请填写 Agent ID", "error");
      return;
    }
    const response = await window.OpsApi.upsertAgent(payload);
    if (!ensureOk(response, "保存 Agent 失败")) return;
    closeEdit();
    toast(state.createMode ? "Agent 已创建" : "Agent 信息已保存", "success");
    await loadAll();
  }

  async function probeAgentRow(row) {
    const agent = row.raw || {};
    const host = String(agent.host_ip || agent.host_name || "").trim();
    const port = Number(agent.port || agent.remote_game_server_port || 0);
    if (!host || !port) {
      toast("当前 Agent 缺少有效的探测地址或端口", "error");
      return;
    }
    const response = await window.OpsApi.probeAgent({
      project_id: state.projectId,
      agent_id: row.agentId,
      host_name: host,
      ip: host,
      port: port,
    });
    if (!ensureOk(response, "探测失败")) return;
    toast("探测请求已提交", "success");
    await loadAll();
  }

  async function handleProbe(rowId) {
    const row = rowById(rowId);
    if (!row) return;
    await probeAgentRow(row);
  }

  async function restartAgentRow(row) {
    if (!window.confirm("确认仅重启当前 Agent 进程，并在远端拉起 Agent 控制台窗口吗？")) return;
    if (!row || !row.agentId) {
      toast("当前 Agent 缺少可执行的目标标识", "error");
      return;
    }
    const response = await window.OpsApi.restartAgent({
      project_id: state.projectId,
      agent_id: row.agentId,
      launch_visible_console: true,
    });
    if (!ensureOk(response, "Agent 重启失败")) {
      return;
    }
    toast("Agent 重启任务已提交", "success");
    await loadAll();
  }

  function handleMenuAction(rowId, action) {
    const row = rowById(rowId);
    if (!row) return;
    if (action === "detail") {
      window.location.href = cardHref(row);
      return;
    }
    if (action === "logs") {
      window.location.href = cardHref(row, "logs");
      return;
    }
    if (action === "edit") {
      openEdit(rowId);
      return;
    }
    if (action === "probe") {
      probeAgentRow(row);
      return;
    }
    if (action === "restart") {
      restartAgentRow(row);
    }
  }

  async function fetchJobCounts() {
    const pendingResponse = await window.OpsApi.agentJobs("", "PENDING", 200);
    const runningResponse = await window.OpsApi.agentJobs("", "RUNNING", 200);
    state.summaryExtra.pending = pendingResponse && pendingResponse.ok ? Number(pendingResponse.count || 0) : 0;
    state.summaryExtra.running = runningResponse && runningResponse.ok ? Number(runningResponse.count || 0) : 0;
  }

  async function loadAgents() {
    const response = await window.OpsApi.agents(state.projectId);
    if (!ensureOk(response, "加载 Agent 失败")) return false;
    state.agents = Array.isArray(response.agents) ? response.agents : [];
    state.rows = buildRows(state.agents);
    return true;
  }

  async function loadAll() {
    const ok = await loadAgents();
    if (!ok) return;
    await fetchJobCounts();
    render();
  }

  function selectedRows() {
    return state.rows.filter(function (row) { return state.selectedIds.has(row.rowId); });
  }

  async function batchProbe() {
    const rows = selectedRows();
    if (!rows.length) {
      toast("请先选择 Agent", "error");
      return;
    }
    for (let index = 0; index < rows.length; index += 1) {
      await probeAgentRow(rows[index]);
    }
  }

  async function batchRestart() {
    const rows = selectedRows();
    if (!rows.length) {
      toast("请先选择 Agent", "error");
      return;
    }
    if (!window.confirm("确认批量重启所选 Agent 管理的服务吗？")) return;
    for (let index = 0; index < rows.length; index += 1) {
      await restartAgentRow(rows[index]);
    }
  }

  async function cleanupExpired() {
    const response = await window.OpsApi.cleanupExpiredAgents({ project_id: state.projectId });
    if (!ensureOk(response, "清理过期 Agent 失败")) return;
    toast("过期 Agent 已清理", "success");
    await loadAll();
  }

  function bindFilters() {
    nodes.filterStatus.onchange = function () {
      state.filters.status = String(nodes.filterStatus.value || "");
    };
    nodes.filterQuery.oninput = function () {
      state.filters.query = String(nodes.filterQuery.value || "");
    };
    nodes.filterServiceStatus.onchange = function () {
      state.filters.serviceStatus = String(nodes.filterServiceStatus.value || "");
    };
    nodes.filterFresh.onchange = function () {
      state.filters.fresh = String(nodes.filterFresh.value || "active_120");
    };

    document.getElementById("btnApplyFilter").onclick = function () {
      state.page = 1;
      render();
    };
    document.getElementById("btnResetFilter").onclick = function () {
      state.filters = { status: "", query: "", serviceStatus: "", fresh: "active_120" };
      nodes.filterStatus.value = "";
      nodes.filterQuery.value = "";
      nodes.filterServiceStatus.value = "";
      nodes.filterFresh.value = "active_120";
      state.page = 1;
      render();
    };
  }

  function bindStatic() {
    document.getElementById("btnCreateAgent").onclick = openCreate;
    document.getElementById("btnCloseAgentEdit").onclick = closeEdit;
    document.getElementById("btnCancelAgentEdit").onclick = closeEdit;
    document.getElementById("btnSaveAgentEdit").onclick = saveEdit;
    document.getElementById("btnProbeAgent").onclick = function () {
      const pseudoRow = {
        agentId: String(nodes.editAgentId.value || ""),
        raw: {
          host_ip: String(nodes.editHostIp.value || ""),
          host_name: String(nodes.editHostIp.value || ""),
          port: Number(nodes.editPort.value || 0),
          remote_game_server_port: Number(nodes.editPort.value || 0),
        },
      };
      probeAgentRow(pseudoRow);
    };

    nodes.cardView.onclick = function () { state.view = "card"; render(); };
    nodes.listView.onclick = function () { state.view = "list"; render(); };

    nodes.pageSize.onchange = function () {
      state.pageSize = Math.max(1, Number(nodes.pageSize.value || 6));
      state.page = 1;
      render();
    };
    document.getElementById("btnPrevPage").onclick = function () {
      state.page = Math.max(1, state.page - 1);
      render();
    };
    document.getElementById("btnNextPage").onclick = function () {
      const totalPages = Math.max(1, Math.ceil(state.filteredRows.length / state.pageSize));
      state.page = Math.min(totalPages, state.page + 1);
      render();
    };
    nodes.selectPage.onchange = function () {
      currentPageRows().forEach(function (row) {
        if (nodes.selectPage.checked) state.selectedIds.add(row.rowId);
        else state.selectedIds.delete(row.rowId);
      });
      render();
    };

    document.getElementById("btnBatchMore").onclick = function (event) {
      event.stopPropagation();
      nodes.batchMenu.classList.toggle("is-hidden");
    };
    document.getElementById("btnClearSelection").onclick = function () {
      state.selectedIds.clear();
      nodes.batchMenu.classList.add("is-hidden");
      render();
    };
    document.getElementById("btnRefreshNow").onclick = async function () {
      nodes.batchMenu.classList.add("is-hidden");
      await loadAll();
      toast("列表已刷新", "success");
    };

    document.getElementById("btnProbeAllAgent").onclick = async function () {
      const response = await window.OpsApi.probeAllAgents({ project_id: state.projectId });
      if (!ensureOk(response, "批量探测失败")) return;
      toast("全量探测请求已提交", "success");
      await loadAll();
    };
    document.getElementById("btnProbeRepairAllAgent").onclick = async function () {
      const response = await window.OpsApi.probeRepairAgents({ project_id: state.projectId });
      if (!ensureOk(response, "批量修复并探测失败")) return;
      toast("修复与探测请求已提交", "success");
      await loadAll();
    };
    document.getElementById("btnBatchProbe").onclick = batchProbe;
    document.getElementById("btnBatchRestart").onclick = batchRestart;
    document.getElementById("btnBatchBind").onclick = function () {
      toast("批量绑定服务入口保留，当前请在详情页完成绑定与运维操作", "success");
    };
    document.getElementById("btnCleanupExpired").onclick = cleanupExpired;

    bindFilters();

    document.addEventListener("click", function (event) {
      if (!event.target.closest(".agent-dropdown")) {
        nodes.batchMenu.classList.add("is-hidden");
      }
      if (!event.target.closest(".agent-card-menu-wrap")) {
        if (state.menuRowId) {
          state.menuRowId = "";
          render();
        }
      }
    });
  }

  function startPolling() {
    clearInterval(state.pollTimer);
    state.pollTimer = setInterval(function () {
      loadAll().catch(function (error) {
        console.error("[agent-control] poll failed", error);
      });
    }, POLL_MS);
  }

  bindStatic();
  loadAll().then(startPolling).catch(function (error) {
    console.error("[agent-control] init failed", error);
    toast("Agent 管理页初始化失败", "error");
  });
})();
