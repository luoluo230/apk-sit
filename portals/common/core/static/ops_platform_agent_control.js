(function () {
  const POLL_MS = 2000;  // fallback: SSE 不可用时轮询间隔
  const SSE_ENDPOINT = "/api/ops-platform/agents/stream";
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (s) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[s]));

  const state = {
    projectId: "",
    filters: { status: "", hostIp: "", bound: "yes", fresh: "all" },
    agentsById: new Map(),
    modalOpen: false,
    pollTimer: null,
    editingAgentId: "",
    createMode: false,
    // 缓存上一次渲染数据
    lastAgents: [],
    lastDevices: [],
    lastSummary: null,
    authRedirectCount: 0,
    loadInflight: false,
    modalKind: "agent", // agent|service
  };

  function statusMeta(status) {
    const s = String(status || "UNKNOWN").toUpperCase();
    if (["ONLINE", "READY", "SUCCESS"].includes(s)) return { cls: "ok", label: s };
    if (["RUNNING", "PENDING", "DEGRADED", "LEASED"].includes(s)) return { cls: "warn", label: s };
    if (["OFFLINE", "ERROR", "FAILED", "TIMEOUT", "CANCELED"].includes(s)) return { cls: "err", label: s };
    return { cls: "info", label: s || "UNKNOWN" };
  }

  function metricValue(m, key) {
    const v = m && m[key];
    if (v == null || v === "") return "-";
    if (typeof v === "number") {
      if (key === "qps" || key === "conn") return String(Math.round(v));
      if (key === "rtt_ms" || key === "rtt_p95_ms" || key === "rtt_p99_ms") return `${Math.round(v)}ms`;
      if (key === "error_rate") return `${(v * 100).toFixed(2)}%`;
      return `${Math.round(v)}%`;
    }
    return String(v);
  }

  // auth expired redirect guard
  function checkAuthExpired(resp) {
    if (resp && (resp.error_code === "OPS_AUTH_REQUIRED" || resp.error === "auth_redirect")) {
      window.location.href = "/login";
      return true;
    }
    return false;
  }

  function renderSummary(payload) {
    const m = (payload && payload.metrics) || {};
    $("cpMetrics").innerHTML = [
      { n: "在线 Agent", v: m.agents_online ?? 0 },
      { n: "注册 Agent", v: m.agents_total ?? 0 },
      { n: "排队任务", v: m.jobs_pending ?? 0 },
      { n: "运行任务", v: m.jobs_running ?? 0 },
    ].map((x) => `<div class="m"><div class="n">${esc(x.n)}</div><div class="v">${esc(x.v)}</div></div>`).join("");

    const q = (payload && payload.queue) || {};
    $("cpQueue").innerHTML = `<div class="ops-kpi-grid">
      <div class="ops-kpi-pill"><span class="label">PENDING</span><span class="value">${esc(q.PENDING ?? 0)}</span></div>
      <div class="ops-kpi-pill"><span class="label">RUNNING</span><span class="value">${esc(q.RUNNING ?? 0)}</span></div>
      <div class="ops-kpi-pill"><span class="label">SUCCESS</span><span class="value">${esc(q.SUCCESS ?? 0)}</span></div>
      <div class="ops-kpi-pill"><span class="label">FAILED/TIMEOUT</span><span class="value">${esc((q.FAILED ?? 0) + (q.TIMEOUT ?? 0))}</span></div>
    </div>`;

    $("cpPolicy").textContent = JSON.stringify((payload && payload.policy) || {}, null, 2);
  }

  function applyLocalFilters(rows) {
    return rows.filter((a) => {
      if (state.filters.status && String(a.status || "").toUpperCase() !== state.filters.status) return false;
      if (state.filters.bound === "yes" && !a.is_bound) return false;
      if (state.filters.bound === "no" && a.is_bound) return false;
      if (state.filters.fresh !== "all") {
        const age = Number(a.last_seen_age_sec == null ? 999999 : a.last_seen_age_sec);
        const ttl = state.filters.fresh === "active_600" ? 600 : 120;
        if (age > ttl) return false;
      }
      const hostToken = state.filters.hostIp;
      if (hostToken) {
        const hay = [a.device_id, a.host_name, a.host, a.ip].map((x) => String(x || "").toLowerCase()).join(" ");
        if (!hay.includes(hostToken.toLowerCase())) return false;
      }
      return true;
    });
  }

  function pickDeviceAgent(rows) {
    if (!Array.isArray(rows) || !rows.length) return null;
    const byPriority = [...rows].sort((a, b) => {
      const an = String(a.node_id || "").toLowerCase();
      const bn = String(b.node_id || "").toLowerCase();
      const ap = an.includes("ops") ? 2 : (an.includes("gateway") ? 1 : 0);
      const bp = bn.includes("ops") ? 2 : (bn.includes("gateway") ? 1 : 0);
      return bp - ap;
    });
    return byPriority[0] || rows[0];
  }

  function renderDevices(devices, allAgents) {
    const groupsRoot = $("cpDevices");
    if (!devices.length && !allAgents.length) {
      groupsRoot.innerHTML = '<div class="ops-empty">当前项目暂无 Agent</div>';
      return;
    }
    if (!devices.length) {
      // agents 已有数据但 devices 未返回时，先按设备分组渲染
      const byDev = new Map();
      for (const a of allAgents) {
        const did = String(a.device_id || "unknown-device");
        if (!byDev.has(did)) byDev.set(did, []);
        byDev.get(did).push(a);
      }
      if (byDev.size === 0) {
        groupsRoot.innerHTML = '<div class="ops-empty">加载中...</div>';
        return;
      }
      // 用 agents 数据直接渲染
      const html = [];
      for (const [did, rows] of byDev) {
        const filtered = applyLocalFilters(rows);
        if (!filtered.length) continue;
        const online = filtered.filter(a => ["ONLINE","READY","RUNNING"].includes(String(a.effective_status || a.status || "").toUpperCase())).length;
        const deviceAgent = pickDeviceAgent(filtered);
        const serviceRows = filtered.filter((a) => String(a.agent_id || "") !== String((deviceAgent || {}).agent_id || ""));
        html.push(`<section class="agent-device-group">
          <header class="agent-device-head">
            <div><h4>${esc(did)}</h4><p>在线 ${online}/${filtered.length}</p></div>
            <div class="ops-header-actions">
              <button type="button" class="btn" data-create-service="${esc(did)}">在该设备下新增服务器</button>
            </div>
          </header>
          <div class="agent-device-wrap">
            <div class="agent-host-card">${deviceAgent ? renderAgentCard(deviceAgent, true) : '<div class="ops-empty">暂无设备Agent</div>'}</div>
            <div class="agent-card-grid">${serviceRows.map(a => renderAgentCard(a, false)).join("")}</div>
          </div>
        </section>`);
      }
      groupsRoot.innerHTML = html.join("") || '<div class="ops-empty">当前项目暂无 Agent</div>';
      groupsRoot.querySelectorAll("[data-agent-edit]").forEach(btn => {
        btn.addEventListener("click", () => openEditModal(btn.dataset.agentEdit || ""));
      });
      groupsRoot.querySelectorAll("[data-create-service]").forEach(btn => {
        btn.addEventListener("click", () => openCreateModal({ kind: "service", deviceId: btn.dataset.createService || "" }));
      });
      return;
    }

    const allByDevice = new Map();
    for (const a of allAgents) {
      const did = String(a.device_id || "unknown-device");
      if (!allByDevice.has(did)) allByDevice.set(did, []);
      allByDevice.get(did).push(a);
    }

    let hiddenTotal = 0;
    const html = devices.map((g) => {
      const did = String(g.device_id || "unknown-device");
      const rawRows = allByDevice.get(did) || [];
      const rows = applyLocalFilters(rawRows);
      hiddenTotal += Math.max(0, rawRows.length - rows.length);
      if (!rows.length) return "";
      const snap = g.device_metrics_snapshot || {};
      const snapC = snap.control || snap;
      const snapB = snap.business || {};
      const updatedAt = snap.updated_at ? String(snap.updated_at) : "-";
      const src = String(snap.source || "missing");
      const srcLabel = (src === "real" || src === "local" || src === "agent") ? "实时" : "实时缺失";
      const online = Number(g.online || 0);
      const total = Number(g.total || rows.length);

      const deviceAgent = pickDeviceAgent(rows);
      const serviceRows = rows.filter((a) => String(a.agent_id || "") !== String((deviceAgent || {}).agent_id || ""));
      return `<section class="agent-device-group">
        <header class="agent-device-head">
          <div>
            <h4>${esc(did)}</h4>
            <p>在线 ${online}/${total} · 快照更新时间 ${esc(updatedAt)} · ${esc(srcLabel)}</p>
          </div>
          <div class="agent-device-metrics">
            <span>业务QPS ${esc(metricValue(snapB, "qps"))}</span>
            <span>P95 ${esc(metricValue(snapB, "rtt_p95_ms"))}</span>
            <span>P99 ${esc(metricValue(snapB, "rtt_p99_ms"))}</span>
            <span>CPU ${esc(metricValue(snapC, "cpu_percent"))}</span>
            <span>MEM ${esc(metricValue(snapC, "mem_percent"))}</span>
            <span>DISK ${esc(metricValue(snapC, "disk_percent"))}</span>
          </div>
          <div class="ops-header-actions">
            <button type="button" class="btn" data-create-service="${esc(did)}">在该设备下新增服务器</button>
          </div>
        </header>
        <div class="agent-device-wrap">
          <div class="agent-host-card">
            <div class="ops-note" style="margin-bottom:6px">设备 Agent（1 台设备 1 个）</div>
            ${deviceAgent ? renderAgentCard(deviceAgent, true) : '<div class="ops-empty">暂无设备Agent</div>'}
          </div>
          <div>
            <div class="ops-note" style="margin-bottom:6px">该设备下游戏服务器</div>
            <div class="agent-card-grid">
              ${serviceRows.map((a) => renderAgentCard(a, false)).join("")}
            </div>
          </div>
        </div>
      </section>`;
    }).join("");

    if (hiddenTotal > 0) {
      $("agentRefreshHint").textContent = `自动刷新：每 2 秒（已隐藏历史失活 ${hiddenTotal} 个）`;
    }
    groupsRoot.innerHTML = html || '<div class="ops-empty">筛选后无匹配 Agent</div>';

    groupsRoot.querySelectorAll("[data-agent-edit]").forEach((btn) => {
      btn.addEventListener("click", () => openEditModal(btn.dataset.agentEdit || ""));
    });
    groupsRoot.querySelectorAll("[data-create-service]").forEach(btn => {
      btn.addEventListener("click", () => openCreateModal({ kind: "service", deviceId: btn.dataset.createService || "" }));
    });
  }

  function renderAgentCard(a, isHostAgent) {
    const s = statusMeta(a.effective_status || a.status);
    const isBound = !!a.is_bound;
    const bindPill = isBound ? '<span class="state-pill state-ok">已绑定</span>' : '<span class="state-pill state-warn">未绑定</span>';
    const age = a.last_seen_age_sec == null ? "-" : `${a.last_seen_age_sec}s`;
    const m = a.metrics || {};
    const mc = m.control || m;
    const mb = m.business || {};
    const source = String(mc.source || "missing");
    const sourceCls = (source === "real" || source === "local" || source === "agent") ? "real" : "mock";
    const sourceLabel = (source === "real" || source === "local" || source === "agent") ? "实时" : "实时缺失";
    const probeStatus = String(a.probe_status || "").toUpperCase();
    const probeAt = String(a.probe_at || "-");
    const probeRtt = a.probe_rtt_ms == null ? "-" : `${a.probe_rtt_ms}ms`;
    const probePill = probeStatus === "PASS"
      ? '<span class="state-pill state-ok">探测通过</span>'
      : (probeStatus === "FAIL" ? '<span class="state-pill state-err">探测失败</span>' : '<span class="state-pill state-info">未探测</span>');
    const remotePort = a.remote_game_server_port || "-";

    return `<article class="agent-card status-${s.cls}">
      <div class="agent-card-top">
        <strong title="${esc(a.display_name || a.agent_id || "-")}">${esc(a.display_name || a.agent_id || "-")}</strong>
        <span class="state-pill state-${s.cls}">${esc(s.label)}</span>
      </div>
      <div class="agent-card-meta">${isHostAgent ? '<span class="state-pill state-info">设备Agent</span>' : '<span class="state-pill state-info">服务器实例</span>'}${bindPill}${probePill}<span class="agent-card-dot">node: ${esc(a.node_id || "-")}</span></div>
      <div class="agent-card-kv">agent_id: ${esc(a.agent_id || "-")}</div>
      <div class="agent-card-kv">device: ${esc(a.device_id || "-")} · ip: ${esc(a.host_name || "-")} · port: ${esc(a.port || "-")}</div>
      <div class="agent-card-kv">remote_port: ${esc(remotePort)} · probe_rtt: ${esc(probeRtt)}</div>
      <div class="agent-card-kv">probe_at: ${esc(probeAt)}</div>
      <div class="agent-card-kv">last_seen_age: ${esc(age)}</div>
      <div class="agent-card-metrics">
        <span class="metric-src ${sourceCls}">${esc(sourceLabel)}</span>
        <span>业务QPS ${esc(metricValue(mb, "qps"))}</span>
        <span>P95 ${esc(metricValue(mb, "rtt_p95_ms"))}</span>
        <span>P99 ${esc(metricValue(mb, "rtt_p99_ms"))}</span>
        <span>错误率 ${esc(metricValue(mb, "error_rate"))}</span>
        <span>连接数 ${esc(metricValue(mb, "conn"))}</span>
        <span>CPU ${esc(metricValue(mc, "cpu_percent"))}</span>
        <span>MEM ${esc(metricValue(mc, "mem_percent"))}</span>
        <span>DISK ${esc(metricValue(mc, "disk_percent"))}</span>
        <span>任务QPS ${esc(metricValue(mc, "qps"))}</span>
        <span>心跳RTT ${esc(metricValue(mc, "rtt_ms"))}</span>
      </div>
      <div class="agent-card-actions">
        <button class="btn" data-agent-edit="${esc(a.agent_id || "")}">编辑</button>
        <a class="btn ghost" href="/admin/ops-platform/topology?project_id=${encodeURIComponent(state.projectId)}">拓扑定位</a>
      </div>
    </article>`;
  }

  // 3 个请求独立返回，谁先返回谁渲染

  async function loadSummary() {
    try {
      const summary = await OpsApi.controlPlaneSummary();
      if (checkAuthExpired(summary)) return;
      if (summary && summary.ok === false) {
        console.warn("[agent-control] summary failed", summary);
      } else {
        state.lastSummary = summary || {};
        renderSummary(state.lastSummary);
      }
    } catch (err) {
      console.error("[agent-control] summary error", err);
    }
  }

  async function loadAgents() {
    try {
      const agentsData = await OpsApi.agents(
        state.projectId,
        state.filters.status,
        "",
        state.filters.bound,
        state.filters.hostIp
      );
      if (checkAuthExpired(agentsData)) return;
      const agents = Array.isArray((agentsData || {}).agents) ? agentsData.agents : [];
      // 始终刷新缓存，即使返回 0 个 agent
      state.lastAgents = agents;
      state.agentsById = new Map(agents.map((a) => [String(a.agent_id || ""), a]));
      if (!state.modalOpen) {
        renderDevices(state.lastDevices, state.lastAgents);
      }
    } catch (err) {
      console.error("[agent-control] agents error", err);
    }
  }

  async function loadDevices() {
    try {
      const devicesData = await OpsApi.agentDevices(state.projectId);
      if (checkAuthExpired(devicesData)) return;
      const devices = Array.isArray((devicesData || {}).devices) ? devicesData.devices : [];
      // 始终刷新缓存，即使返回 0 个 device
      state.lastDevices = devices;
      if (!state.modalOpen) {
        renderDevices(state.lastDevices, state.lastAgents);
      }
    } catch (err) {
      console.error("[agent-control] devices error", err);
    }
  }

  function loadData() {
    if (state.loadInflight) return;
    state.loadInflight = true;
    // no lock between poll requests
    Promise.allSettled([loadSummary(), loadAgents(), loadDevices()]).finally(() => {
      state.loadInflight = false;
      const at = new Date();
      $("agentRefreshHint").textContent = `自动刷新：每 2 秒（最后同步 ${at.toLocaleTimeString()}）`;
    });
  }

  function readFilters() {
    state.filters.status = String($("filterStatus").value || "").trim().toUpperCase();
    state.filters.hostIp = String($("filterDevice").value || "").trim();
    state.filters.bound = String($("filterBound").value || "yes").trim();
    state.filters.fresh = String($("filterFresh").value || "active_120").trim();
  }

  function openEditModal(agentId) {
    const hit = state.agentsById.get(String(agentId || ""));
    if (!hit) return;
    state.createMode = false;
    state.modalOpen = true;
    state.modalKind = "agent";
    state.editingAgentId = String(hit.agent_id || "");

    $("agentEditTitle").textContent = "编辑设备 Agent";
    $("editAgentId").value = hit.agent_id || "";
    $("editAgentId").readOnly = true;
    $("editDeviceId").value = hit.device_id || "";
    $("editHostIp").value = hit.host_name || "";
    $("editServiceId").value = String(hit.service_id || "");
    $("editServiceType").value = String(hit.service_type || "");
    $("editDisplayName").value = hit.display_name || hit.agent_id || "";
    $("editPort").value = hit.port || "";
    $("editServicePort").value = hit.service_port || "";
    $("editRemotePort").value = hit.remote_game_server_port || hit.port || "";
    const endpoints = hit.network && Array.isArray(hit.network.endpoints) ? hit.network.endpoints : [];
    $("editNetworkEndpoints").value = endpoints.join(",");
    $("editRunState").value = "";
    $("editDesc").value = hit.desc || "";
    toggleFieldMode("agent", false);

    $("agentEditModal").classList.remove("hidden");
    $("agentEditModal").setAttribute("aria-hidden", "false");
  }

  function openCreateModal(opts) {
    const kind = String((opts && opts.kind) || "agent");
    const deviceId = String((opts && opts.deviceId) || "").trim();
    state.createMode = true;
    state.modalOpen = true;
    state.modalKind = kind === "service" ? "service" : "agent";
    state.editingAgentId = "";
    let defaultAgentId = "";
    let defaultHostIp = "";
    if (kind === "service" && deviceId) {
      const rows = (state.lastAgents || []).filter((x) => String((x || {}).device_id || "") === deviceId);
      const hostAgent = pickDeviceAgent(rows);
      if (hostAgent) {
        defaultAgentId = String(hostAgent.agent_id || "");
        defaultHostIp = String(hostAgent.host_name || "");
      }
    }
    $("editAgentId").value = defaultAgentId;
    $("editAgentId").readOnly = false;
    $("editDeviceId").value = deviceId;
    $("editHostIp").value = defaultHostIp;
    $("editServiceId").value = "";
    $("editServiceType").value = "";
    $("editDisplayName").value = "";
    $("editPort").value = "";
    $("editServicePort").value = "";
    $("editRemotePort").value = "";
    $("editNetworkEndpoints").value = "";
    $("editRunState").value = "ONLINE";
    $("editDesc").value = "";
    if (state.modalKind === "service") {
      $("agentEditTitle").textContent = "新增服务实例";
      $("agentEditHint").textContent = "服务实例只填写服务字段，保存后可在拓扑绑定 service_id";
    } else {
      $("agentEditTitle").textContent = "新建设备 Agent";
      $("agentEditHint").textContent = "设备Agent只填写设备与通信字段，保存后可在该设备下创建服务实例";
    }
    toggleFieldMode(state.modalKind, true);
    $("agentEditModal").classList.remove("hidden");
    $("agentEditModal").setAttribute("aria-hidden", "false");
  }

  function closeEditModal() {
    state.modalOpen = false;
    state.editingAgentId = "";
    state.createMode = false;
    state.modalKind = "agent";
    $("agentEditModal").classList.add("hidden");
    $("agentEditModal").setAttribute("aria-hidden", "true");
    $("agentEditHint").textContent = "编辑保存后 2 秒内会同步到卡片";
  }

  async function saveEditModal() {
    const isService = state.modalKind === "service";
    const agentId = state.createMode ? String($("editAgentId").value || "").trim() : state.editingAgentId;
    if (!agentId) {
      alert("请先填写 Agent ID");
      return;
    }
    const payload = {
      project_id: state.projectId,
      desc: String($("editDesc").value || "").trim(),
    };
    const endpointText = String($("editNetworkEndpoints").value || "").trim();
    if (endpointText) payload.network = { endpoints: endpointText.split(",").map((x) => x.trim()).filter(Boolean) };
    else payload.network = { endpoints: [] };
    const rs = String($("editRunState").value || "").trim();
    if (rs) payload.run_state = rs;

    const btn = $("btnSaveAgentEdit");
    const oldText = btn.textContent;
    btn.textContent = "保存中...";
    btn.disabled = true;
    try {
      let resp;
      if (isService) {
        const serviceId = String($("editServiceId").value || "").trim();
        if (!serviceId) {
          alert("请先填写服务实例 ID");
          return;
        }
        payload.agent_id = agentId;
        payload.service_id = serviceId;
        payload.display_name = String($("editDisplayName").value || "").trim() || serviceId;
        payload.device_id = String($("editDeviceId").value || "").trim();
        payload.host_name = String($("editHostIp").value || "").trim();
        payload.service_type = String($("editServiceType").value || "").trim() || "standard";
        payload.service_port = Number($("editServicePort").value || 0);
        payload.remote_game_server_port = Number($("editRemotePort").value || 0);
        payload.status = "ONLINE";
        resp = await OpsApi.upsertService(payload);
      } else {
        payload.agent_id = agentId;
        payload.display_name = String($("editDisplayName").value || "").trim();
        payload.device_id = String($("editDeviceId").value || "").trim();
        payload.host_name = String($("editHostIp").value || "").trim();
        payload.port = Number($("editPort").value || 0);
        payload.remote_game_server_port = Number($("editRemotePort").value || 0);
        if (state.createMode) {
          payload.create_if_missing = true;
          payload.status = "ONLINE";
          payload.run_state = "ONLINE";
        }
        resp = await OpsApi.upsertAgent(payload);
      }
      if (!resp || resp.ok === false) {
        alert((resp && (resp.message || resp.error_code || resp.error)) || "保存失败");
        return;
      }
      closeEditModal();
      loadData();
    } finally {
      btn.disabled = false;
      btn.textContent = oldText;
    }
  }

  function toggleFieldMode(kind, creating) {
    const isService = kind === "service";
    document.querySelectorAll("[data-field='service']").forEach((el) => {
      el.style.display = isService ? "" : "none";
    });
    document.querySelectorAll("[data-field='agent']").forEach((el) => {
      if (!isService) {
        el.style.display = "";
        return;
      }
      const id = el.querySelector("input") ? el.querySelector("input").id : "";
      if (id === "editAgentId" || id === "editDeviceId" || id === "editHostIp") el.style.display = "";
      else el.style.display = "none";
    });
    $("btnProbeAgent").style.display = isService ? "none" : "";
    if (creating && isService) {
      $("editAgentId").readOnly = false;
      $("editHostIp").readOnly = true;
      $("editDeviceId").readOnly = true;
    } else {
      $("editHostIp").readOnly = false;
      $("editDeviceId").readOnly = false;
    }
  }

  async function probeAgentConnectivity() {
    const host = String($("editHostIp").value || "").trim();
    const port = Number($("editRemotePort").value || $("editPort").value || 0);
    if (!host || !port) {
      alert("请先填写 IP 和端口");
      return;
    }
    const btn = $("btnProbeAgent");
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = "探测中...";
    try {
      const probePayload = { host_name: host, port };
      const aid = String($("editAgentId").value || "").trim();
      if (aid) probePayload.agent_id = aid;
      const resp = await OpsApi.probeAgent(probePayload);
      if (!resp || resp.ok === false) {
        alert((resp && (resp.message || resp.error || "连通性失败")) || "连通性失败");
        return;
      }
      alert(`连通性成功 RTT=${resp.rtt_ms}ms`);
      loadData();
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
  }

  async function probeAllAgents() {
    const btn = $("btnProbeAllAgent");
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = "全量探测中...";
    try {
      const resp = await OpsApi.probeAllAgents({ project_id: state.projectId });
      if (!resp || resp.ok === false) {
        alert((resp && (resp.message || resp.error || "全量探测失败")) || "全量探测失败");
        return;
      }
      const rows = Array.isArray(resp.results) ? resp.results : [];
      const pass = rows.filter((x) => x.ok).length;
      const fail = rows.length - pass;
      alert(`探测完成：通过 ${pass}，失败 ${fail}`);
      loadData();
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
  }

  async function probeRepairAllAgents() {
    const btn = $("btnProbeRepairAllAgent");
    if (!btn) return;
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = "修复并探测中...";
    try {
      const resp = await OpsApi.probeRepairAgents({ project_id: state.projectId, default_host: "127.0.0.1" });
      if (!resp || resp.ok === false) {
        alert((resp && (resp.message || resp.error || "批量修复失败")) || "批量修复失败");
        return;
      }
      const rows = Array.isArray(resp.results) ? resp.results : [];
      const pass = rows.filter((x) => x.ok).length;
      const fail = rows.length - pass;
      alert(`修复完成：修复 ${resp.fixed_count || 0} 项；探测通过 ${pass}，失败 ${fail}`);
      loadData();
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
  }

  function bindEvents() {
    $("btnRefreshCp").addEventListener("click", () => loadData());
    $("btnCreateAgent").addEventListener("click", () => openCreateModal({ kind: "agent" }));
    $("btnCreateServiceTop").addEventListener("click", () => openCreateModal({ kind: "service" }));
    $("btnProbeAllAgent").addEventListener("click", probeAllAgents);
    if ($("btnProbeRepairAllAgent")) $("btnProbeRepairAllAgent").addEventListener("click", probeRepairAllAgents);
    $("btnCleanupExpired").addEventListener("click", async () => {
      const ttlHours = 1;
      const ok = window.confirm(`确认清理超过 ${ttlHours} 小时未心跳的 Agent 吗？会移除失效绑定。`);
      if (!ok) return;
      const btn = $("btnCleanupExpired");
      const old = btn.textContent;
      btn.disabled = true;
      btn.textContent = "清理中...";
      try {
        const resp = await OpsApi.cleanupExpiredAgents({ project_id: state.projectId, ttl_hours: ttlHours });
        if (!resp || resp.ok === false) {
          alert((resp && (resp.message || resp.error_code || resp.error)) || "清理失败");
          return;
        }
        alert(`清理完成：删除 ${resp.deleted_count || 0} 个 Agent，移除 ${resp.removed_binding_count || 0} 条失效绑定。`);
        loadData();
      } finally {
        btn.disabled = false;
        btn.textContent = old;
      }
    });
    $("btnCleanupExpiredCustom").addEventListener("click", async () => {
      const raw = window.prompt("请输入过期小时数（默认 24）", "24");
      if (raw == null) return;
      const ttlHours = Number(raw || 24);
      if (!Number.isFinite(ttlHours) || ttlHours <= 0) {
        alert("请输入有效的小时数");
        return;
      }
      const ok = window.confirm(`确认清理超过 ${Math.round(ttlHours)} 小时未心跳的 Agent 吗？会移除失效绑定。`);
      if (!ok) return;
      const btn = $("btnCleanupExpiredCustom");
      const old = btn.textContent;
      btn.disabled = true;
      btn.textContent = "清理中...";
      try {
        const resp = await OpsApi.cleanupExpiredAgents({ project_id: state.projectId, ttl_hours: Math.round(ttlHours) });
        if (!resp || resp.ok === false) {
          alert((resp && (resp.message || resp.error_code || resp.error)) || "清理失败");
          return;
        }
        alert(`清理完成：删除 ${resp.deleted_count || 0} 个 Agent，移除 ${resp.removed_binding_count || 0} 条失效绑定。`);
        loadData();
      } finally {
        btn.disabled = false;
        btn.textContent = old;
      }
    });
    $("btnApplyFilter").addEventListener("click", () => {
      readFilters();
      loadData();
    });
    $("btnResetFilter").addEventListener("click", () => {
      $("filterStatus").value = "";
      $("filterDevice").value = "";
      $("filterBound").value = "";
      $("filterFresh").value = "all";
      readFilters();
      loadData();
    });

    $("btnCloseAgentEdit").addEventListener("click", closeEditModal);
    $("btnCancelAgentEdit").addEventListener("click", closeEditModal);
    $("btnSaveAgentEdit").addEventListener("click", saveEditModal);
    $("btnProbeAgent").addEventListener("click", probeAgentConnectivity);
    $("agentEditModal").addEventListener("click", (ev) => {
      if (ev.target && ev.target.id === "agentEditModal") closeEditModal();
    });
  }

  function startPolling() {
    // prefer SSE, fallback to polling
    if (typeof EventSource !== "undefined") {
      startSSE();
    } else {
      if (state.pollTimer) clearInterval(state.pollTimer);
      state.pollTimer = setInterval(() => {
        if (!state.modalOpen) loadData();
      }, POLL_MS);
    }
  }

  function startSSE() {
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
    const params = new URLSearchParams();
    if (state.projectId) params.set("project_id", state.projectId);
    const url = SSE_ENDPOINT + (params.toString() ? "?" + params.toString() : "");

    try {
      const es = new EventSource(url);
      state.eventSource = es;

      es.addEventListener("full", (event) => {
        try {
          const payload = JSON.parse(event.data);
          applySSEPayload(payload);
        } catch (e) { console.error("[agent-control] SSE full parse error", e); }
      });

      es.addEventListener("change", (event) => {
        try {
          const payload = JSON.parse(event.data);
          applySSEPayload(payload);
        } catch (e) { console.error("[agent-control] SSE change parse error", e); }
      });

      es.onerror = () => {
        // SSE 断开 -> 回退到轮询
        console.warn("[agent-control] SSE disconnected, falling back to polling");
        if (state.eventSource) {
          state.eventSource.close();
          state.eventSource = null;
        }
        if (!state.pollTimer) {
          state.pollTimer = setInterval(() => {
            if (!state.modalOpen) loadData();
          }, POLL_MS);
          // 30s 后重试 SSE
          setTimeout(() => {
            if (state.pollTimer) clearInterval(state.pollTimer);
            state.pollTimer = null;
            startSSE();
          }, 30000);
        }
      };

      // stop polling when SSE connected
      if (state.pollTimer) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
      }
    } catch (e) {
      console.warn("[agent-control] SSE init failed, using polling", e);
      if (!state.pollTimer) {
        state.pollTimer = setInterval(() => {
          if (!state.modalOpen) loadData();
        }, POLL_MS);
      }
    }
  }

  function applySSEPayload(payload) {
    if (!payload || payload.ok === false) return;
    // 更新 summary
    if (payload.metrics || payload.queue) {
      state.lastSummary = payload;
      renderSummary(payload);
    }
    // 更新 agents
    if (Array.isArray(payload.agents)) {
      state.lastAgents = payload.agents;
      state.agentsById = new Map(payload.agents.map((a) => [String(a.agent_id || ""), a]));
      // rebuild devices by agent list from SSE payload
      const byDev = new Map();
      for (const a of payload.agents) {
        const did = String(a.device_id || "unknown-device");
        if (!byDev.has(did)) byDev.set(did, []);
        byDev.get(did).push(a);
      }
      const rebuiltDevices = [];
      for (const [did, agents] of byDev) {
        const online = agents.filter(a => ["ONLINE","READY","RUNNING"].includes(String(a.effective_status || a.status || "").toUpperCase())).length;
        // 设备级指标从 agents 的 metrics 聚合
        const devMetrics = {
          control: { cpu_percent: null, mem_percent: null, disk_percent: null, qps: null, rtt_ms: null, updated_at: "", source: "missing" },
          business: { qps: null, rtt_p95_ms: null, rtt_p99_ms: null, error_rate: null, conn: null, updated_at: "", source: "missing" },
          updated_at: "",
          source: "missing",
        };
        for (const a of agents) {
          const m = a.metrics || {};
          const mc = m.control || m;
          const mb = m.business || {};
          if (mc.cpu_percent != null) devMetrics.control.cpu_percent = mc.cpu_percent;
          if (mc.mem_percent != null) devMetrics.control.mem_percent = mc.mem_percent;
          if (mc.disk_percent != null) devMetrics.control.disk_percent = mc.disk_percent;
          if (mc.qps != null) devMetrics.control.qps = mc.qps;
          if (mc.rtt_ms != null) devMetrics.control.rtt_ms = mc.rtt_ms;
          if (mc.updated_at) {
            devMetrics.control.updated_at = mc.updated_at;
            devMetrics.updated_at = mc.updated_at;
          }
          if (mc.source) {
            devMetrics.control.source = mc.source;
            devMetrics.source = mc.source;
          }
          if (mb.qps != null) devMetrics.business.qps = mb.qps;
          if (mb.rtt_p95_ms != null) devMetrics.business.rtt_p95_ms = mb.rtt_p95_ms;
          if (mb.rtt_p99_ms != null) devMetrics.business.rtt_p99_ms = mb.rtt_p99_ms;
          if (mb.error_rate != null) devMetrics.business.error_rate = mb.error_rate;
          if (mb.conn != null) devMetrics.business.conn = mb.conn;
          if (mb.updated_at) devMetrics.business.updated_at = mb.updated_at;
          if (mb.source) devMetrics.business.source = mb.source;
        }
        rebuiltDevices.push({
          device_id: did,
          project_id: payload.agents[0] && payload.agents[0].project_id || "",
          agents: agents,
          online: online,
          total: agents.length,
          device_metrics_snapshot: devMetrics,
        });
      }
      state.lastDevices = rebuiltDevices;
    }
    // 更新 bindings
    if (payload.bindings) {
      state.lastBindings = payload.bindings;
    }
    // 渲染
    if (!state.modalOpen) {
      renderDevices(state.lastDevices, state.lastAgents);
    }
    const at = new Date();
    const src = payload.probe_seq != null ? `SSE seq=${payload.probe_seq}` : "SSE";
    $("agentRefreshHint").textContent = `${src} · 实时推送 · ${at.toLocaleTimeString()}`;
  }

  async function boot() {
    const root = document.querySelector(".ops-page");
    state.projectId = String((root && root.dataset && root.dataset.projectId) || "").trim();
    bindEvents();
    // 首次：先用缓存渲染（如有），同时发起请求
    if (state.lastAgents.length || state.lastDevices.length) {
      renderDevices(state.lastDevices, state.lastAgents);
    }
    if (state.lastSummary) {
      renderSummary(state.lastSummary);
    }
    loadData();
    startPolling();
  }

  boot().catch((e) => console.error("[agent-control] boot failed", e));
})();


