(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (s) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[s]));
  const state = { projectId: "", status: "", deviceId: "", bound: "" };

  function statusBadge(status) {
    const s = String(status || "UNKNOWN").toUpperCase();
    const cls = (s === "ONLINE" || s === "SUCCESS" || s === "READY") ? "state-ok" : ((s === "RUNNING" || s === "PENDING" || s === "DEGRADED") ? "state-warn" : "state-err");
    return '<span class="state-pill ' + cls + '">' + esc(s) + "</span>";
  }

  async function loadSummary() {
    const d = await OpsApi.controlPlaneSummary();
    const m = d.metrics || {};
    $("cpMetrics").innerHTML =
      '<div class="m"><div class="n">在线 Agent</div><div class="v">' + esc(m.agents_online ?? 0) + '</div></div>' +
      '<div class="m"><div class="n">注册 Agent</div><div class="v">' + esc(m.agents_total ?? 0) + '</div></div>' +
      '<div class="m"><div class="n">排队任务</div><div class="v">' + esc(m.jobs_pending ?? 0) + '</div></div>' +
      '<div class="m"><div class="n">运行任务</div><div class="v">' + esc(m.jobs_running ?? 0) + "</div></div>";
    const q = d.queue || {};
    $("cpQueue").innerHTML = '<div class="row">' +
      '<div class="m"><div class="n">PENDING</div><div class="v">' + esc(q.PENDING ?? 0) + '</div></div>' +
      '<div class="m"><div class="n">RUNNING</div><div class="v">' + esc(q.RUNNING ?? 0) + '</div></div>' +
      '<div class="m"><div class="n">SUCCESS</div><div class="v">' + esc(q.SUCCESS ?? 0) + '</div></div>' +
      '<div class="m"><div class="n">FAILED/TIMEOUT</div><div class="v">' + esc((q.FAILED ?? 0) + (q.TIMEOUT ?? 0)) + "</div></div>" +
      "</div>";
    $("cpPolicy").textContent = JSON.stringify(d.policy || {}, null, 2);
  }

  async function loadAgents() {
    const d = await OpsApi.agents(state.projectId, state.status, state.deviceId, state.bound);
    const rows = Array.isArray(d.agents) ? d.agents : [];
    if (!rows.length) {
      $("cpAgents").innerHTML = '<div class="preset-empty">当前筛选无 Agent</div>';
      return;
    }
    $("cpAgents").innerHTML = rows.map((a) => {
      const local = ((a.transport || {}).mode || "remote").toLowerCase();
      const localEndpoint = (a.transport || {}).local_endpoint || "-";
      const bound = a.is_bound ? '<span class="state-pill state-ok">已绑定</span>' : '<span class="state-pill state-warn">未绑定</span>';
      return '<div style="border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc;padding:10px;margin-bottom:8px">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><b>' + esc(a.display_name || a.agent_id || "-") + '</b><div style="display:flex;gap:6px">' + statusBadge(a.status) + bound + "</div></div>" +
        '<div style="font-size:11px;color:#64748b;margin-top:4px">agent_id=' + esc(a.agent_id || "-") + " | node=" + esc(a.node_id || "-") + " | project=" + esc(a.project_id || "-") + "</div>" +
        '<div style="font-size:11px;color:#64748b">device=' + esc(a.device_id || "-") + " | port=" + esc(a.port || "-") + " | version=" + esc(a.version || "-") + "</div>" +
        '<div style="font-size:11px;color:#64748b">local_bus=' + esc(local) + " | endpoint=" + esc(localEndpoint) + " | last_seen=" + esc(a.last_seen || "-") + "</div>" +
        '<div style="display:flex;gap:8px;margin-top:8px">' +
        '<button class="btn" onclick="window.__opsAgentEdit(\'' + esc(a.agent_id || "") + "')\">编辑</button>" +
        '<a class="btn" href="/admin/ops-platform/topology?project_id=' + encodeURIComponent(state.projectId) + '">跳转拓扑</a>' +
        "</div></div>";
    }).join("");
  }

  async function loadDevices() {
    const d = await OpsApi.agentDevices(state.projectId);
    const rows = Array.isArray(d.devices) ? d.devices : [];
    if (!rows.length) {
      $("cpDevices").innerHTML = '<div class="preset-empty">暂无设备组</div>';
      return;
    }
    $("cpDevices").innerHTML = rows.map((g) => {
      const cnt = Array.isArray(g.agents) ? g.agents.length : 0;
      const online = (Array.isArray(g.agents) ? g.agents : []).filter((x) => ["ONLINE", "READY", "RUNNING"].includes(String(x.status || "").toUpperCase())).length;
      return '<div style="border:1px solid #e2e8f0;border-radius:10px;background:#f8fafc;padding:9px;margin-bottom:8px">' +
        '<div style="display:flex;justify-content:space-between;align-items:center"><b>' + esc(g.device_id || "-") + '</b><span class="state-pill state-info">online ' + online + "/" + cnt + "</span></div>" +
        '<div style="font-size:11px;color:#64748b;margin-top:4px">project=' + esc(g.project_id || state.projectId) + '</div>' +
        '<div style="margin-top:7px"><a class="btn" href="/admin/ops-platform/agent-device-local?project_id=' + encodeURIComponent(state.projectId) + "&device_id=" + encodeURIComponent(g.device_id || "") + '">本地管理页</a></div>' +
        "</div>";
    }).join("");
  }

  async function loadAll() {
    await Promise.all([loadSummary(), loadAgents(), loadDevices()]);
  }

  async function editAgent(agentId) {
    const d = await OpsApi.agents(state.projectId);
    const hit = (d.agents || []).find((x) => String(x.agent_id || "") === String(agentId || ""));
    if (!hit) return;
    const display_name = window.prompt("Agent名称", hit.display_name || hit.agent_id || "");
    if (display_name == null) return;
    const portStr = window.prompt("端口", String(hit.port || 0));
    if (portStr == null) return;
    const desc = window.prompt("描述", hit.desc || "");
    if (desc == null) return;
    const up = await OpsApi.upsertAgent({ agent_id: agentId, display_name, port: Number(portStr || 0), desc });
    if (!up.ok) { alert(up.message || up.error || "更新失败"); return; }
    await loadAll();
  }

  function bindEvents() {
    $("btnRefreshCp").onclick = loadAll;
    $("btnApplyFilter").onclick = async () => {
      state.status = String($("filterStatus").value || "").trim().toUpperCase();
      state.deviceId = String($("filterDevice").value || "").trim();
      state.bound = String($("filterBound").value || "").trim();
      await loadAgents();
    };
    window.__opsAgentEdit = (id) => { editAgent(id); };
  }

  async function boot() {
    state.projectId = (document.querySelector(".ops-page") || {}).dataset?.projectId || "";
    bindEvents();
    await loadAll();
    setInterval(loadAll, 5000);
  }

  boot().catch((e) => console.error(e));
})();
