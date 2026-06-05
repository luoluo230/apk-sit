(function () {
  const root = document.querySelector(".agent-detail-page");
  if (!root || !window.OpsApi) return;

  const state = {
    projectId: String(root.dataset.projectId || ""),
    agentId: String(root.dataset.agentId || ""),
    activeTab: new URLSearchParams(window.location.search).get("tab") || "overview",
    detail: null,
    selectedServiceIds: new Set(),
    pendingConfirm: null,
    serviceFormMode: "create",
    serviceFormAgentId: "",
  };

  const nodes = {
    flash: document.getElementById("detailFlash"),
    loading: document.getElementById("detailLoading"),
    name: document.getElementById("detailAgentName"),
    status: document.getElementById("detailStatusPill"),
    meta: document.getElementById("detailMetaLine"),
    tabs: Array.from(document.querySelectorAll(".agent-detail-tab")),
    panels: Array.from(document.querySelectorAll(".agent-detail-panel")),
    moreMenu: document.getElementById("detailMoreMenu"),
    editModal: document.getElementById("detailEditModal"),
    editAgentId: document.getElementById("detailEditAgentId"),
    editDeviceId: document.getElementById("detailEditDeviceId"),
    editHostIp: document.getElementById("detailEditHostIp"),
    editDisplayName: document.getElementById("detailEditDisplayName"),
    editPort: document.getElementById("detailEditPort"),
    editRunState: document.getElementById("detailEditRunState"),
    editDesc: document.getElementById("detailEditDesc"),
    serviceModal: document.getElementById("serviceEditModal"),
    serviceTitle: document.getElementById("serviceEditTitle"),
    serviceSub: document.getElementById("serviceEditSub"),
    serviceId: document.getElementById("serviceFormServiceId"),
    serviceDisplayName: document.getElementById("serviceFormDisplayName"),
    serviceType: document.getElementById("serviceFormType"),
    servicePort: document.getElementById("serviceFormPort"),
    serviceRemotePort: document.getElementById("serviceFormRemotePort"),
    serviceNodeId: document.getElementById("serviceFormNodeId"),
    serviceDesc: document.getElementById("serviceFormDesc"),
    confirmModal: document.getElementById("serviceConfirmModal"),
    confirmTitle: document.getElementById("serviceConfirmTitle"),
    confirmBody: document.getElementById("serviceConfirmBody"),
    confirmSubmit: document.getElementById("serviceConfirmSubmit"),
    logModal: document.getElementById("serviceLogModal"),
    logTitle: document.getElementById("serviceLogTitle"),
    logSub: document.getElementById("serviceLogSub"),
    logContent: document.getElementById("serviceLogContent"),
  };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function flash(message, tone) {
    if (!message) {
      nodes.flash.className = "agent-inline-note is-hidden";
      nodes.flash.textContent = "";
      return;
    }
    nodes.flash.className = "agent-inline-note " + (tone === "error" ? "is-error" : "is-success");
    nodes.flash.textContent = message;
  }

  function ensureOk(response, fallback) {
    if (response && (response.error_code === "OPS_AUTH_REQUIRED" || response.error === "auth_redirect")) {
      window.location.href = "/login";
      return false;
    }
    if (!response || !response.ok) {
      flash((response && (response.message || response.error)) || fallback || "请求失败", "error");
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
    if (status === "ONLINE") return "运行中";
    if (status === "OFFLINE") return "已停止";
    if (status === "WARN") return "异常";
    return "未知";
  }

  function pillClass(status) {
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

  function relativeTime(value) {
    if (!value) return "--";
    const ms = Date.parse(value);
    if (!Number.isFinite(ms)) return String(value);
    const diff = Math.max(0, Math.round((Date.now() - ms) / 1000));
    if (diff < 60) return diff + " 秒前";
    if (diff < 3600) return Math.floor(diff / 60) + " 分钟前";
    if (diff < 86400) return Math.floor(diff / 3600) + " 小时前";
    return Math.floor(diff / 86400) + " 天前";
  }

  function metricValue(key) {
    const detail = state.detail || {};
    const control = detail.agent && detail.agent.metrics && detail.agent.metrics.control
      ? detail.agent.metrics.control
      : (detail.agent && detail.agent.metrics) || {};
    const overview = detail.overview || {};
    const direct = Number(control[key]);
    if (Number.isFinite(direct)) return Math.max(0, Math.round(direct));
    const fallback = Number(overview[key]);
    if (Number.isFinite(fallback)) return Math.max(0, Math.round(fallback));
    return null;
  }

  function metricPercent(key) {
    const value = metricValue(key);
    return value == null ? "--" : String(value);
  }

  function agentStatus() {
    const detail = state.detail || {};
    return normalizeStatus((detail.overview || {}).status || (detail.agent || {}).effective_status || (detail.agent || {}).status);
  }

  function summaryNumbers() {
    const detail = state.detail || {};
    const overview = detail.overview || {};
    const services = detail.service_summary || {};
    const node = detail.node || {};
    const agent = detail.agent || {};
    return {
      healthyRatio: overview.healthy_ratio == null ? "--" : String(overview.healthy_ratio) + "%",
      cpuPercent: metricPercent("cpu_percent"),
      memPercent: metricPercent("mem_percent"),
      diskPercent: metricPercent("disk_percent"),
      onlineServices: Number(services.online || 0),
      abnormalServices: Number(services.abnormal || 0),
      totalServices: Number(services.total || 0),
      currentAlerts: Number(overview.current_alerts || 0),
      resolvedAlerts: Number(overview.resolved_alerts || 0),
      gateway: String(node.name || node.id || "Gateway-01"),
      ip: String(agent.host_ip || agent.host_name || "--"),
      port: String(agent.remote_game_server_port || agent.port || "--"),
    };
  }

  function serviceRows() {
    return Array.isArray((state.detail || {}).services) ? state.detail.services : [];
  }

  function selectedServices() {
    return serviceRows().filter(function (service) {
      return state.selectedServiceIds.has(String(service.service_id || ""));
    });
  }

  function primaryMemberAgentId() {
    const detail = state.detail || {};
    const memberIds = Array.isArray(detail.member_agent_ids) ? detail.member_agent_ids : [];
    return String(memberIds[0] || (detail.agent || {}).agent_id || state.agentId || "");
  }

  function lineChartData() {
    const detail = state.detail || {};
    const history = detail.metrics_history || {};
    const points = Array.isArray(history.points) ? history.points : [];
    const fallbackValues = {
      cpu_percent: Number(metricValue("cpu_percent") || 0),
      mem_percent: Number(metricValue("mem_percent") || 0),
      disk_percent: Number(metricValue("disk_percent") || 0),
    };
    function build(key) {
      const list = points.map(function (point) {
        return Number(point[key]);
      }).filter(Number.isFinite);
      if (list.length >= 2) return list.slice(-18);
      const base = fallbackValues[key];
      return [base, base, base, base, base, base];
    }
    return {
      cpu: build("cpu_percent"),
      mem: build("mem_percent"),
      disk: build("disk_percent"),
    };
  }

  function chartMarkup(title, color, values, shownValue) {
    const safeValues = values.length ? values : [0, 0, 0];
    const points = safeValues.map(function (value, index) {
      const x = safeValues.length === 1 ? 0 : (index / (safeValues.length - 1)) * 240;
      const y = 90 - (Math.max(0, Math.min(100, Number(value) || 0)) * 0.72);
      return x + "," + y;
    }).join(" ");
    return "" +
      '<div class="agent-chart">' +
        '<div class="agent-chart-head"><span>' + esc(title) + "</span><strong>" + esc(shownValue) + "%</strong></div>" +
        '<div class="agent-chart-scale"><span>100</span><span>50</span><span>0</span></div>' +
        '<svg viewBox="0 0 240 100" preserveAspectRatio="none">' +
          '<polyline points="' + esc(points) + '" fill="none" stroke="' + esc(color) + '" stroke-width="3" stroke-linecap="round"></polyline>' +
        "</svg>" +
        '<div class="agent-chart-scale"><span>10:30</span><span>11:00</span><span>11:30</span></div>' +
      "</div>";
  }

  function renderStatusPill(status) {
    const normalized = normalizeStatus(status);
    return '<span class="agent-state-pill ' + pillClass(normalized) + '">' + esc(statusText(normalized)) + "</span>";
  }

  function tableMarkup(headers, rows, mode) {
    return "" +
      '<div class="agent-table-shell">' +
        '<table class="agent-table">' +
          "<thead><tr>" + headers.map(function (header) { return "<th>" + esc(header) + "</th>"; }).join("") + "</tr></thead>" +
          "<tbody>" + rows.join("") + "</tbody>" +
        "</table>" +
      "</div>";
  }

  function serviceActionButtons(service) {
    const status = normalizeStatus(service.status || service.run_state);
    const serviceId = String(service.service_id || "");
    const buttons = [
      '<button class="agent-table-action" type="button" data-service-action="status" data-service-id="' + esc(serviceId) + '">查看状态</button>',
    ];
    if (status === "ONLINE") {
      buttons.push('<button class="agent-table-action" type="button" data-service-action="stop" data-service-id="' + esc(serviceId) + '">停止</button>');
      buttons.push('<button class="agent-table-action" type="button" data-service-action="restart" data-service-id="' + esc(serviceId) + '">重启</button>');
    } else {
      buttons.push('<button class="agent-table-action" type="button" data-service-action="start" data-service-id="' + esc(serviceId) + '">启动</button>');
    }
    buttons.push('<button class="agent-table-action" type="button" data-service-action="edit" data-service-id="' + esc(serviceId) + '">编辑</button>');
    buttons.push('<button class="agent-table-action" type="button" data-service-action="logs" data-service-id="' + esc(serviceId) + '">查看日志</button>');
    return buttons.join("");
  }

  function serviceTableRows() {
    return serviceRows().map(function (service) {
      const serviceId = String(service.service_id || "");
      const selected = state.selectedServiceIds.has(serviceId);
      const status = normalizeStatus(service.status || service.run_state);
      const metrics = service.metrics && typeof service.metrics === "object" ? service.metrics : {};
      const cpu = Number(metrics.cpu_percent);
      const memMb = Number(metrics.service_memory_mb);
      return "" +
        "<tr>" +
          '<td><input type="checkbox" data-service-select="' + esc(serviceId) + '"' + (selected ? " checked" : "") + "></td>" +
          "<td><strong>" + esc(service.display_name || serviceId) + "</strong><div class=\"table-sub\">" + esc(serviceId) + "</div></td>" +
          "<td>" + renderStatusPill(status) + "</td>" +
          "<td>" + esc(service.remote_game_server_port || service.service_port || "--") + "</td>" +
          "<td>" + esc(formatDate(service.updated_at)) + "</td>" +
          "<td>" + esc(Number.isFinite(cpu) ? (Math.round(cpu) + "%") : "--") + "</td>" +
          "<td>" + esc(Number.isFinite(memMb) ? (Math.round(memMb) + "MB") : "--") + "</td>" +
          '<td><div class="agent-table-actions agent-table-actions--wide">' + serviceActionButtons(service) + "</div></td>" +
        "</tr>";
    });
  }

  function serviceToolbar(title) {
    const selectedCount = state.selectedServiceIds.size;
    return "" +
      '<div class="agent-detail-card-head">' +
        "<strong>" + esc(title) + "</strong>" +
        '<div class="agent-detail-toolbar-inline">' +
          '<span class="agent-detail-toolbar-text">已选 ' + esc(selectedCount) + " 项</span>" +
          '<button class="agent-btn agent-btn--outline agent-btn--small" type="button" data-service-toolbar="create">新增服务器</button>' +
          '<button class="agent-btn agent-btn--outline agent-btn--small" type="button" data-service-toolbar="delete">删除服务器</button>' +
        "</div>" +
      "</div>";
  }

  function serviceConsole(title) {
    const rows = serviceTableRows();
    const body = rows.length
      ? tableMarkup(["", "服务名称", "状态", "端口", "最近更新时间", "CPU", "内存", "操作"], rows, "service")
      : '<div class="agent-empty">当前 Agent 暂无服务实例</div>';
    return '<article class="agent-detail-white-card">' + serviceToolbar(title) + '<div class="agent-detail-card-body">' + body + "</div></article>";
  }

  function jobsRows() {
    const jobs = Array.isArray((state.detail || {}).jobs) ? state.detail.jobs : [];
    if (!jobs.length) {
      return ['<tr><td colspan="4">暂无任务记录</td></tr>'];
    }
    return jobs.slice(0, 10).map(function (item) {
      const status = normalizeStatus(item.status || item.state || item.result);
      const name = item.title || item.action || item.target || item.ticket_id || "任务";
      return "" +
        "<tr>" +
          "<td>" + esc(name) + "</td>" +
          "<td>" + renderStatusPill(status) + "</td>" +
          "<td>" + esc(formatDate(item.updated_at || item.created_at || item.time || item.timestamp)) + "</td>" +
          "<td>" + esc(item.user || item.operator || item.approver || "系统") + "</td>" +
        "</tr>";
    });
  }

  function eventRows() {
    const events = Array.isArray((state.detail || {}).events) ? state.detail.events : [];
    if (!events.length) {
      return ['<tr><td colspan="4">暂无告警事件</td></tr>'];
    }
    return events.slice(0, 10).map(function (item) {
      const severity = String(item.severity || item.level || "提示");
      const status = String(item.status || item.state || "open");
      return "" +
        "<tr>" +
          "<td>" + esc(severity) + "</td>" +
          "<td>" + esc(item.title || item.message || item.details || "-") + "</td>" +
          "<td>" + esc(formatDate(item.time || item.updated_at || item.timestamp)) + "</td>" +
          "<td>" + renderStatusPill(status) + "</td>" +
        "</tr>";
    });
  }

  function auditRows() {
    const audits = Array.isArray((state.detail || {}).audits) ? state.detail.audits : [];
    if (!audits.length) {
      return ['<tr><td colspan="4">暂无审计日志</td></tr>'];
    }
    return audits.slice(0, 12).map(function (item) {
      return "" +
        "<tr>" +
          "<td>" + esc(item.action || "审计操作") + "</td>" +
          "<td>" + esc(item.details || item.message || "-") + "</td>" +
          "<td>" + esc(formatDate(item.timestamp || item.updated_at || item.time)) + "</td>" +
          "<td>" + esc(item.user || item.operator || "admin") + "</td>" +
        "</tr>";
    });
  }

  function traceRows() {
    const traces = Array.isArray((state.detail || {}).traces) ? state.detail.traces : [];
    if (!traces.length) {
      return ['<tr><td colspan="4">暂无操作日志</td></tr>'];
    }
    return traces.slice(0, 12).map(function (item) {
      return "" +
        "<tr>" +
          "<td>" + esc(item.action_type || item.action || "动作") + "</td>" +
          "<td>" + esc(item.target || item.desired_service_id || item.trace_id || "-") + "</td>" +
          "<td>" + esc(formatDate(item.updated_at || item.created_at || item.time)) + "</td>" +
          "<td>" + esc(item.status || item.state || "-") + "</td>" +
        "</tr>";
    });
  }

  function configList() {
    const detail = state.detail || {};
    const config = detail.config || {};
    const transport = config.transport || {};
    const policy = config.policy || {};
    const agent = detail.agent || {};
    const items = [
      ["Agent 配置版本", agent.version || "-"],
      ["配置模式", transport.mode || "-"],
      ["鉴权模式", transport.local_auth_mode || "-"],
      ["服务总数", String(serviceRows().length)],
      ["最后更新时间", formatDate(agent.updated_at || agent.last_seen)],
      ["策略来源", policy.updated_at ? "策略已下发" : "手动维护"],
      ["描述", agent.desc || "-"],
    ];
    return '<div class="agent-config-list">' + items.map(function (row) {
      return "<span>" + esc(row[0]) + "</span><strong>" + esc(row[1]) + "</strong>";
    }).join("") + "</div>";
  }

  function overviewMarkup() {
    const summary = summaryNumbers();
    const charts = lineChartData();
    return "" +
      '<div class="agent-detail-summary-grid">' +
        '<article class="agent-detail-summary-card">' +
          '<div class="agent-detail-summary-title">Agent 状态</div>' +
          '<div class="agent-detail-summary-status">' + esc(statusText(agentStatus())) + "</div>" +
          '<div class="agent-detail-summary-foot"><span>健康度</span><strong>' + esc(summary.healthyRatio) + "</strong></div>" +
        "</article>" +
        '<article class="agent-detail-summary-card">' +
          '<div class="agent-detail-summary-title">系统资源</div>' +
          '<div class="agent-detail-resource-grid">' +
            "<div><span>CPU</span><strong>" + esc(summary.cpuPercent) + "%</strong></div>" +
            "<div><span>内存</span><strong>" + esc(summary.memPercent) + "%</strong></div>" +
            "<div><span>磁盘</span><strong>" + esc(summary.diskPercent) + "%</strong></div>" +
          "</div>" +
        "</article>" +
        '<article class="agent-detail-summary-card">' +
          '<div class="agent-detail-summary-title">连接信息</div>' +
          '<div class="agent-detail-kv"><span>网关</span><strong>' + esc(summary.gateway) + '</strong><span>IP</span><strong>' + esc(summary.ip) + '</strong><span>端口</span><strong>' + esc(summary.port) + "</strong></div>" +
        "</article>" +
        '<article class="agent-detail-summary-card">' +
          '<div class="agent-detail-summary-title">服务健康</div>' +
          '<div class="agent-detail-kv"><span>在线服务</span><strong>' + esc(summary.onlineServices) + '</strong><span>异常服务</span><strong>' + esc(summary.abnormalServices) + '</strong><span>服务总数</span><strong>' + esc(summary.totalServices) + "</strong></div>" +
        "</article>" +
        '<article class="agent-detail-summary-card">' +
          '<div class="agent-detail-summary-title">告警事件</div>' +
          '<div class="agent-detail-kv"><span>当前告警</span><strong>' + esc(summary.currentAlerts) + '</strong><span>已恢复</span><strong>' + esc(summary.resolvedAlerts) + '</strong><span>未确认</span><strong>' + esc(Math.max(0, summary.currentAlerts - summary.resolvedAlerts)) + "</strong></div>" +
        "</article>" +
      "</div>" +
      '<div class="agent-detail-main-grid">' +
        serviceConsole("服务与进程") +
        '<article class="agent-detail-white-card">' +
          '<div class="agent-detail-card-head"><strong>监控指标（最近 1 小时）</strong><span>1 小时</span></div>' +
          '<div class="agent-detail-card-body">' +
            '<div class="agent-chart-grid">' +
              chartMarkup("CPU 使用率 (%)", "#2f6bff", charts.cpu, summary.cpuPercent === "--" ? 0 : summary.cpuPercent) +
              chartMarkup("内存使用率 (%)", "#16c47f", charts.mem, summary.memPercent === "--" ? 0 : summary.memPercent) +
              chartMarkup("磁盘使用率 (%)", "#8e4ef8", charts.disk, summary.diskPercent === "--" ? 0 : summary.diskPercent) +
            "</div>" +
          "</div>" +
        "</article>" +
      "</div>" +
      '<div class="agent-detail-bottom-grid">' +
        '<article class="agent-detail-white-card"><div class="agent-detail-card-head"><strong>近期任务</strong><button class="agent-detail-link-button" type="button" data-jump-tab="jobs">查看更多</button></div><div class="agent-detail-card-body">' +
          tableMarkup(["任务名称", "状态", "执行时间", "执行人"], jobsRows()) +
        "</div></article>" +
        '<article class="agent-detail-white-card"><div class="agent-detail-card-head"><strong>告警事件</strong><button class="agent-detail-link-button" type="button" data-jump-tab="events">查看更多</button></div><div class="agent-detail-card-body">' +
          tableMarkup(["级别", "告警内容", "时间", "状态"], eventRows()) +
        "</div></article>" +
        '<article class="agent-detail-white-card"><div class="agent-detail-card-head"><strong>配置信息</strong><button class="agent-detail-link-button" type="button" data-jump-tab="config">管理配置</button></div><div class="agent-detail-card-body">' +
          configList() +
        "</div></article>" +
      "</div>" +
      systemFooter();
  }

  function systemFooter() {
    const agent = (state.detail || {}).agent || {};
    const footer = [
      "系统信息",
      "操作系统: " + String(agent.os || "CentOS 7.9"),
      "架构: " + String(agent.arch || "x86_64"),
      "最近心跳: " + relativeTime(agent.last_seen),
      "安装时间: " + formatDate(agent.created_at || agent.install_time || agent.updated_at),
      "最后更新时间: " + formatDate(agent.updated_at || agent.last_seen),
      "Agent ID: " + String(agent.agent_id || state.agentId),
    ];
    return '<div class="agent-system-footer">' + footer.map(function (item, index) {
      return index === 0 ? ("<strong>" + esc(item) + "</strong>") : ("<span>" + esc(item) + "</span>");
    }).join("") + "</div>";
  }

  function deviceMarkup() {
    const detail = state.detail || {};
    const agent = detail.agent || {};
    const node = detail.node || {};
    return "" +
      '<div class="agent-detail-two-col">' +
        '<article class="agent-detail-info-card">' +
          '<div class="agent-detail-card-head"><strong>设备基础信息</strong></div>' +
          '<div class="agent-detail-info-grid">' +
            "<span>Agent ID</span><strong>" + esc(agent.agent_id || state.agentId) + "</strong>" +
            "<span>设备 ID</span><strong>" + esc(agent.device_id || "-") + "</strong>" +
            "<span>IP 地址</span><strong>" + esc(agent.host_ip || agent.host_name || "-") + "</strong>" +
            "<span>所属项目</span><strong>" + esc(agent.project_id || state.projectId || "-") + "</strong>" +
            "<span>区域 / 可用区</span><strong>" + esc((agent.region || "-") + " / " + (agent.zone || "-")) + "</strong>" +
            "<span>版本</span><strong>" + esc(agent.version || "-") + "</strong>" +
          "</div>" +
        "</article>" +
        '<article class="agent-detail-info-card">' +
          '<div class="agent-detail-card-head"><strong>节点映射信息</strong></div>' +
          '<div class="agent-detail-info-grid">' +
            "<span>拓扑节点</span><strong>" + esc(node.id || agent.node_id || "-") + "</strong>" +
            "<span>节点名称</span><strong>" + esc(node.name || "-") + "</strong>" +
            "<span>成员 Agent</span><strong>" + esc((detail.member_agent_ids || []).join(", ") || "-") + "</strong>" +
            "<span>成员节点</span><strong>" + esc((detail.member_node_ids || []).join(", ") || "-") + "</strong>" +
            "<span>探测状态</span><strong>" + esc(agent.probe_status || "-") + "</strong>" +
            "<span>最后心跳</span><strong>" + esc(relativeTime(agent.last_seen)) + "</strong>" +
          "</div>" +
        "</article>" +
      "</div>";
  }

  function metricsMarkup() {
    const charts = lineChartData();
    const summary = summaryNumbers();
    return '<article class="agent-detail-white-card"><div class="agent-detail-card-head"><strong>监控指标（最近 1 小时）</strong><span>实时采样</span></div><div class="agent-detail-card-body"><div class="agent-chart-grid">' +
      chartMarkup("CPU 使用率 (%)", "#2f6bff", charts.cpu, summary.cpuPercent === "--" ? 0 : summary.cpuPercent) +
      chartMarkup("内存使用率 (%)", "#16c47f", charts.mem, summary.memPercent === "--" ? 0 : summary.memPercent) +
      chartMarkup("磁盘使用率 (%)", "#8e4ef8", charts.disk, summary.diskPercent === "--" ? 0 : summary.diskPercent) +
      "</div></div></article>";
  }

  function logsMarkup() {
    return '<article class="agent-detail-white-card"><div class="agent-detail-card-head"><strong>操作日志</strong></div><div class="agent-detail-card-body">' +
      tableMarkup(["动作", "目标", "时间", "状态"], traceRows()) +
      "</div></article>";
  }

  function jobsMarkup() {
    return '<article class="agent-detail-white-card"><div class="agent-detail-card-head"><strong>任务历史</strong></div><div class="agent-detail-card-body">' +
      tableMarkup(["任务名称", "状态", "执行时间", "执行人"], jobsRows()) +
      "</div></article>";
  }

  function eventsMarkup() {
    return '<article class="agent-detail-white-card"><div class="agent-detail-card-head"><strong>告警事件</strong></div><div class="agent-detail-card-body">' +
      tableMarkup(["级别", "告警内容", "时间", "状态"], eventRows()) +
      "</div></article>";
  }

  function auditMarkup() {
    return '<article class="agent-detail-white-card"><div class="agent-detail-card-head"><strong>审计日志</strong></div><div class="agent-detail-card-body">' +
      tableMarkup(["动作", "内容", "时间", "操作人"], auditRows()) +
      "</div></article>";
  }

  function configMarkup() {
    const detail = state.detail || {};
    const config = detail.config || {};
    return "" +
      '<div class="agent-detail-two-col">' +
        '<article class="agent-detail-info-card">' +
          '<div class="agent-detail-card-head"><strong>配置摘要</strong></div>' +
          '<div class="agent-detail-card-body">' + configList() + "</div>" +
        "</article>" +
        '<article class="agent-detail-info-card">' +
          '<div class="agent-detail-card-head"><strong>当前配置回执</strong></div>' +
          '<pre class="agent-detail-code">' + esc(JSON.stringify(config, null, 2)) + "</pre>" +
        "</article>" +
      "</div>";
  }

  function renderAll() {
    const detail = state.detail || {};
    const agent = detail.agent || {};
    const status = agentStatus();
    nodes.name.textContent = agent.device_id || agent.display_name || agent.agent_id || state.agentId;
    nodes.status.className = "agent-state-pill " + pillClass(status);
    nodes.status.textContent = statusText(status);
    nodes.meta.textContent = [
      "ID: " + String(agent.agent_id || state.agentId || "-"),
      "分组: " + String(agent.region || "-"),
      "环境: " + String(agent.env || "生产环境"),
      "版本: " + String(agent.version || "-"),
      "最近心跳: " + relativeTime(agent.last_seen),
      "安装时间: " + formatDate(agent.created_at || agent.updated_at || agent.last_seen),
    ].join("  |  ");

    document.getElementById("tab-overview").innerHTML = overviewMarkup();
    document.getElementById("tab-device").innerHTML = deviceMarkup();
    document.getElementById("tab-services").innerHTML = serviceConsole("服务与进程");
    document.getElementById("tab-metrics").innerHTML = metricsMarkup();
    document.getElementById("tab-jobs").innerHTML = jobsMarkup();
    document.getElementById("tab-logs").innerHTML = logsMarkup();
    document.getElementById("tab-config").innerHTML = configMarkup();
    document.getElementById("tab-events").innerHTML = eventsMarkup();
    document.getElementById("tab-audit").innerHTML = auditMarkup();

    bindDynamic();
    switchTab(state.activeTab);
  }

  function switchTab(tab) {
    state.activeTab = tab;
    nodes.tabs.forEach(function (node) {
      node.classList.toggle("is-active", node.dataset.tab === tab);
    });
    nodes.panels.forEach(function (panel) {
      panel.classList.toggle("is-active", panel.id === "tab-" + tab);
    });
  }

  function fillEdit() {
    const agent = (state.detail || {}).agent || {};
    nodes.editAgentId.value = String(agent.agent_id || state.agentId || "");
    nodes.editDeviceId.value = String(agent.device_id || "");
    nodes.editHostIp.value = String(agent.host_ip || agent.host_name || "");
    nodes.editDisplayName.value = String(agent.display_name || agent.device_id || "");
    nodes.editPort.value = String(agent.remote_game_server_port || agent.port || "");
    nodes.editRunState.value = "";
    nodes.editDesc.value = String(agent.desc || "");
  }

  function openAgentEdit() {
    fillEdit();
    nodes.editModal.classList.remove("is-hidden");
  }

  function closeAgentEdit() {
    nodes.editModal.classList.add("is-hidden");
  }

  function openServiceModal(mode, service) {
    state.serviceFormMode = mode;
    state.serviceFormAgentId = service && service.agent_id ? String(service.agent_id) : primaryMemberAgentId();
    nodes.serviceTitle.textContent = mode === "edit" ? "编辑服务器" : "新增服务器";
    nodes.serviceSub.textContent = mode === "edit" ? "保存后会更新当前服务实例配置。" : "新增服务会写入当前 Agent 的 services[] 配置。";
    nodes.serviceId.readOnly = mode === "edit";
    nodes.serviceId.value = service ? String(service.service_id || "") : "";
    nodes.serviceDisplayName.value = service ? String(service.display_name || "") : "";
    nodes.serviceType.value = service ? String(service.service_type || "") : "";
    nodes.servicePort.value = service ? String(service.service_port || service.remote_game_server_port || "") : "";
    nodes.serviceRemotePort.value = service ? String(service.remote_game_server_port || service.service_port || "") : "";
    nodes.serviceNodeId.value = service ? String(service.node_id || "") : "";
    nodes.serviceDesc.value = service ? String(service.desc || "") : "";
    nodes.serviceModal.classList.remove("is-hidden");
  }

  function closeServiceModal() {
    nodes.serviceModal.classList.add("is-hidden");
  }

  function openConfirm(title, body, onConfirm) {
    nodes.confirmTitle.textContent = title;
    nodes.confirmBody.textContent = body;
    state.pendingConfirm = onConfirm;
    nodes.confirmModal.classList.remove("is-hidden");
  }

  function closeConfirm() {
    nodes.confirmModal.classList.add("is-hidden");
    state.pendingConfirm = null;
  }

  function openLogModal(title, subtitle, payload) {
    nodes.logTitle.textContent = title;
    nodes.logSub.textContent = subtitle;
    nodes.logContent.textContent = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
    nodes.logModal.classList.remove("is-hidden");
  }

  function closeLogModal() {
    nodes.logModal.classList.add("is-hidden");
  }

  function serviceById(serviceId) {
    return serviceRows().find(function (service) {
      return String(service.service_id || "") === serviceId;
    }) || null;
  }

  async function saveAgentEdit() {
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
    };
    const response = await window.OpsApi.upsertAgent(payload);
    if (!ensureOk(response, "保存 Agent 失败")) return;
    closeAgentEdit();
    flash("Agent 信息已保存", "success");
    await load();
  }

  async function probeLive() {
    const agent = (state.detail || {}).agent || {};
    const host = String(agent.host_ip || agent.host_name || "").trim();
    const port = Number(agent.port || agent.remote_game_server_port || 0);
    if (!host || !port) {
      flash("当前 Agent 缺少有效的探测地址或端口", "error");
      return;
    }
    const response = await window.OpsApi.probeAgent({
      project_id: state.projectId,
      agent_id: String(agent.agent_id || state.agentId),
      host_name: host,
      ip: host,
      port: port,
    });
    if (!ensureOk(response, "探测失败")) return;
    flash("探测请求已提交", "success");
    await load();
  }

  async function restartAgent() {
    const services = serviceRows();
    if (!services.length) {
      flash("当前 Agent 没有可重启的服务", "error");
      return;
    }
    openConfirm("重启 Agent", "确认重启该 Agent 管理的所有服务吗？", async function () {
      let count = 0;
      for (let index = 0; index < services.length; index += 1) {
        const service = services[index];
        const response = await window.OpsApi.serviceAction({
          project_id: state.projectId,
          service_id: String(service.service_id || ""),
          agent_id: String(service.agent_id || primaryMemberAgentId()),
          action: "restart",
        });
        if (response && response.ok) count += 1;
      }
      if (!count) {
        flash("未成功提交任何重启任务", "error");
        return;
      }
      flash("已提交 " + count + " 个服务的重启请求", "success");
      await load();
    });
  }

  async function saveServiceEdit() {
    const payload = {
      project_id: state.projectId,
      agent_id: state.serviceFormAgentId || primaryMemberAgentId(),
      service_id: String(nodes.serviceId.value || "").trim(),
      display_name: String(nodes.serviceDisplayName.value || "").trim(),
      service_type: String(nodes.serviceType.value || "").trim(),
      service_port: Number(nodes.servicePort.value || 0),
      remote_game_server_port: Number(nodes.serviceRemotePort.value || 0),
      node_id: String(nodes.serviceNodeId.value || "").trim(),
      desc: String(nodes.serviceDesc.value || "").trim(),
    };
    if (!payload.agent_id) {
      flash("当前缺少可写入的目标 Agent", "error");
      return;
    }
    if (!payload.service_id) {
      flash("请填写服务 ID", "error");
      return;
    }
    const response = await window.OpsApi.upsertService(payload);
    if (!ensureOk(response, state.serviceFormMode === "edit" ? "保存服务失败" : "新增服务失败")) return;
    closeServiceModal();
    flash(state.serviceFormMode === "edit" ? "服务已更新" : "服务已新增", "success");
    await load();
  }

  async function runServiceAction(service, action) {
    const response = await window.OpsApi.serviceAction({
      project_id: state.projectId,
      service_id: String(service.service_id || ""),
      agent_id: String(service.agent_id || primaryMemberAgentId()),
      node_id: String(service.node_id || ""),
      action: action,
    });
    if (!ensureOk(response, "服务操作失败")) return null;
    return response;
  }

  function actionLabel(action) {
    if (action === "start") return "启动";
    if (action === "stop") return "停止";
    if (action === "restart") return "重启";
    if (action === "status") return "查看状态";
    if (action === "logs") return "查看日志";
    return action;
  }

  async function handleServiceAction(serviceId, action) {
    const service = serviceById(serviceId);
    if (!service) {
      flash("未找到目标服务实例", "error");
      return;
    }
    if (action === "edit") {
      openServiceModal("edit", service);
      return;
    }
    if (action === "logs") {
      const response = await runServiceAction(service, "logs");
      if (!response) return;
      openLogModal(
        "服务日志: " + (service.display_name || service.service_id || ""),
        "日志拉取任务已提交，可根据 job_id / trace_id 跟进执行结果。",
        {
          service_id: service.service_id,
          agent_id: service.agent_id,
          action: "logs",
          job_id: response.job_id || "",
          trace_id: response.trace_id || "",
        }
      );
      flash("日志拉取任务已提交", "success");
      return;
    }
    if (action === "status") {
      const response = await runServiceAction(service, "status");
      if (!response) return;
      openLogModal(
        "服务状态回执: " + (service.display_name || service.service_id || ""),
        "当前接口返回的是状态查询任务回执。",
        response
      );
      flash("状态查询任务已提交", "success");
      return;
    }
    openConfirm(
      actionLabel(action) + "服务器",
      "确认" + actionLabel(action) + "服务 " + (service.display_name || service.service_id || "") + " 吗？",
      async function () {
        const response = await runServiceAction(service, action);
        if (!response) return;
        flash(actionLabel(action) + "请求已提交", "success");
        await load();
      }
    );
  }

  async function deleteSelectedServices() {
    const services = selectedServices();
    if (!services.length) {
      flash("请先选择要删除的服务器", "error");
      return;
    }
    openConfirm("删除服务器", "确认删除选中的 " + services.length + " 个服务器实例吗？", async function () {
      let count = 0;
      for (let index = 0; index < services.length; index += 1) {
        const service = services[index];
        const response = await window.OpsApi.postJSON("/api/ops-platform/services/delete", {
          project_id: state.projectId,
          agent_id: String(service.agent_id || primaryMemberAgentId()),
          service_id: String(service.service_id || ""),
        });
        if (response && response.ok) {
          count += 1;
        } else if (response && response.message) {
          flash(response.message, "error");
        }
      }
      if (!count) return;
      state.selectedServiceIds.clear();
      flash("已删除 " + count + " 个服务器实例", "success");
      await load();
    });
  }

  function bindDynamic() {
    document.querySelectorAll("[data-jump-tab]").forEach(function (node) {
      node.onclick = function () {
        switchTab(String(node.getAttribute("data-jump-tab") || "overview"));
      };
    });
    document.querySelectorAll("[data-service-select]").forEach(function (node) {
      node.onchange = function () {
        const serviceId = String(node.getAttribute("data-service-select") || "");
        if (!serviceId) return;
        if (node.checked) state.selectedServiceIds.add(serviceId);
        else state.selectedServiceIds.delete(serviceId);
        renderAll();
      };
    });
    document.querySelectorAll("[data-service-action]").forEach(function (node) {
      node.onclick = function () {
        handleServiceAction(
          String(node.getAttribute("data-service-id") || ""),
          String(node.getAttribute("data-service-action") || "")
        );
      };
    });
    document.querySelectorAll("[data-service-toolbar]").forEach(function (node) {
      node.onclick = function () {
        const action = String(node.getAttribute("data-service-toolbar") || "");
        if (action === "create") openServiceModal("create", null);
        if (action === "delete") deleteSelectedServices();
      };
    });
  }

  async function load() {
    const response = await window.OpsApi.agentDetail(state.projectId, state.agentId);
    if (!ensureOk(response, "加载 Agent 详情失败")) {
      nodes.loading.classList.add("is-hidden");
      return;
    }
    state.detail = response;
    nodes.loading.classList.add("is-hidden");
    renderAll();
    fillEdit();
  }

  function toggleMoreMenu(forceOpen) {
    const shouldOpen = typeof forceOpen === "boolean" ? forceOpen : nodes.moreMenu.classList.contains("is-hidden");
    nodes.moreMenu.classList.toggle("is-hidden", !shouldOpen);
  }

  function bindStatic() {
    nodes.tabs.forEach(function (node) {
      node.onclick = function () {
        switchTab(String(node.dataset.tab || "overview"));
      };
    });

    document.getElementById("detailOpenControl").onclick = function () {
      window.location.href = "/admin/ops-platform/agent-control?project_id=" + encodeURIComponent(state.projectId);
    };
    document.getElementById("detailEditBtn").onclick = openAgentEdit;
    document.getElementById("detailRestartBtn").onclick = restartAgent;
    document.getElementById("detailProbeBtn").onclick = probeLive;
    document.getElementById("detailSaveEdit").onclick = saveAgentEdit;
    document.getElementById("detailCloseEdit").onclick = closeAgentEdit;
    document.getElementById("detailCancelEdit").onclick = closeAgentEdit;

    document.getElementById("detailMoreBtn").onclick = function (event) {
      event.stopPropagation();
      toggleMoreMenu();
    };
    document.getElementById("detailMoreProbe").onclick = async function () {
      toggleMoreMenu(false);
      await probeLive();
    };
    document.getElementById("detailMoreLogs").onclick = function () {
      toggleMoreMenu(false);
      switchTab("logs");
    };
    document.getElementById("detailMoreRefresh").onclick = async function () {
      toggleMoreMenu(false);
      await load();
      flash("详情已刷新", "success");
    };

    document.getElementById("serviceCloseEdit").onclick = closeServiceModal;
    document.getElementById("serviceCancelEdit").onclick = closeServiceModal;
    document.getElementById("serviceSaveEdit").onclick = saveServiceEdit;

    document.getElementById("serviceConfirmClose").onclick = closeConfirm;
    document.getElementById("serviceConfirmCancel").onclick = closeConfirm;
    nodes.confirmSubmit.onclick = async function () {
      const current = state.pendingConfirm;
      closeConfirm();
      if (typeof current === "function") {
        await current();
      }
    };

    document.getElementById("serviceLogClose").onclick = closeLogModal;

    document.addEventListener("click", function (event) {
      if (!event.target.closest(".agent-dropdown")) {
        toggleMoreMenu(false);
      }
    });
  }

  bindStatic();
  load().catch(function (error) {
    console.error("[agent-detail] init failed", error);
    flash("Agent 详情初始化失败", "error");
    nodes.loading.classList.add("is-hidden");
  });
})();
