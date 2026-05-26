(function () {
  const POLL_MS = 2000;
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (s) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[s]));

  const state = {
    projectId: "",
    filters: { status: "", hostIp: "", bound: "", fresh: "active_120" },
    agentsById: new Map(),
    polling: false,
    pollTimer: null,
    modalOpen: false,
    editingAgentId: "",
    createMode: false,
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
      if (key === "qps") return String(Math.round(v));
      return `${Math.round(v)}${key === "rtt_ms" ? "ms" : "%"}`;
    }
    return String(v);
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

  function renderDevices(devices, allAgents) {
    const groupsRoot = $("cpDevices");
    if (!devices.length) {
      groupsRoot.innerHTML = '<div class="ops-empty">当前项目暂无 Agent</div>';
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
      const updatedAt = snap.updated_at ? String(snap.updated_at) : "-";
      const src = String(snap.source || "missing");
      const srcLabel = src === "real" ? "实时" : "实时缺失";
      const online = Number(g.online || 0);
      const total = Number(g.total || rows.length);

      return `<section class="agent-device-group">
        <header class="agent-device-head">
          <div>
            <h4>${esc(did)}</h4>
            <p>在线 ${online}/${total} · 快照更新时间 ${esc(updatedAt)} · ${esc(srcLabel)}</p>
          </div>
          <div class="agent-device-metrics">
            <span>CPU ${esc(metricValue(snap, "cpu_percent"))}</span>
            <span>MEM ${esc(metricValue(snap, "mem_percent"))}</span>
            <span>QPS ${esc(metricValue(snap, "qps"))}</span>
            <span>RTT ${esc(metricValue(snap, "rtt_ms"))}</span>
          </div>
        </header>
        <div class="agent-card-grid">
          ${rows.map((a) => renderAgentCard(a)).join("")}
        </div>
      </section>`;
    }).join("");

    if (hiddenTotal > 0) {
      $("agentRefreshHint").textContent = `自动刷新：每 2 秒（已隐藏历史残留 ${hiddenTotal} 个）`;
    }
    groupsRoot.innerHTML = html || '<div class="ops-empty">筛选后无匹配 Agent</div>';

    groupsRoot.querySelectorAll("[data-agent-edit]").forEach((btn) => {
      btn.addEventListener("click", () => openEditModal(btn.dataset.agentEdit || ""));
    });
  }

  function renderAgentCard(a) {
    const s = statusMeta(a.status);
    const isBound = !!a.is_bound;
    const bindPill = isBound ? '<span class="state-pill state-ok">已绑定</span>' : '<span class="state-pill state-warn">未绑定</span>';
    const age = a.last_seen_age_sec == null ? "-" : `${a.last_seen_age_sec}s`;
    const m = a.metrics || {};
    const source = String(m.source || "missing");
    const sourceCls = source === "real" ? "real" : "mock";
    const sourceLabel = source === "real" ? "实时" : "实时缺失";

    return `<article class="agent-card status-${s.cls}">
      <div class="agent-card-top">
        <strong title="${esc(a.display_name || a.agent_id || "-")}">${esc(a.display_name || a.agent_id || "-")}</strong>
        <span class="state-pill state-${s.cls}">${esc(s.label)}</span>
      </div>
      <div class="agent-card-meta">${bindPill}<span class="agent-card-dot">node: ${esc(a.node_id || "-")}</span></div>
      <div class="agent-card-kv">agent_id: ${esc(a.agent_id || "-")}</div>
      <div class="agent-card-kv">device: ${esc(a.device_id || "-")} · ip: ${esc(a.host_name || "-")} · port: ${esc(a.port || "-")}</div>
      <div class="agent-card-kv">last_seen_age: ${esc(age)}</div>
      <div class="agent-card-metrics">
        <span class="metric-src ${sourceCls}">${esc(sourceLabel)}</span>
        <span>CPU ${esc(metricValue(m, "cpu_percent"))}</span>
        <span>MEM ${esc(metricValue(m, "mem_percent"))}</span>
        <span>QPS ${esc(metricValue(m, "qps"))}</span>
        <span>RTT ${esc(metricValue(m, "rtt_ms"))}</span>
      </div>
      <div class="agent-card-actions">
        <button class="btn" data-agent-edit="${esc(a.agent_id || "")}">编辑</button>
        <a class="btn ghost" href="/admin/ops-platform/topology?project_id=${encodeURIComponent(state.projectId)}">拓扑定位</a>
      </div>
    </article>`;
  }

  async function loadData() {
    if (state.polling) return;
    state.polling = true;
    try {
      const [summary, agentsData, devicesData] = await Promise.all([
        OpsApi.controlPlaneSummary(),
        OpsApi.agents(
          state.projectId,
          state.filters.status,
          "",
          state.filters.bound,
          state.filters.hostIp
        ),
        OpsApi.agentDevices(state.projectId),
      ]);

      if (summary && summary.ok === false) {
        console.warn("[agent-control] summary failed", summary);
      } else {
        renderSummary(summary || {});
      }

      const agents = Array.isArray((agentsData || {}).agents) ? agentsData.agents : [];
      state.agentsById = new Map(agents.map((a) => [String(a.agent_id || ""), a]));

      const devices = Array.isArray((devicesData || {}).devices) ? devicesData.devices : [];
      if (!state.modalOpen) {
        renderDevices(devices, agents);
      }

      const at = new Date();
      $("agentRefreshHint").textContent = `自动刷新：每 2 秒（最后同步 ${at.toLocaleTimeString()}）`;
    } catch (err) {
      console.error("[agent-control] loadData failed", err);
    } finally {
      state.polling = false;
    }
  }

  function readFilters() {
    state.filters.status = String($("filterStatus").value || "").trim().toUpperCase();
    state.filters.hostIp = String($("filterDevice").value || "").trim();
    state.filters.bound = String($("filterBound").value || "").trim();
    state.filters.fresh = String($("filterFresh").value || "active_120").trim();
  }

  function openEditModal(agentId) {
    const hit = state.agentsById.get(String(agentId || ""));
    if (!hit) return;
    state.createMode = false;
    state.modalOpen = true;
    state.editingAgentId = String(hit.agent_id || "");

    $("editAgentId").value = hit.agent_id || "";
    $("editAgentId").readOnly = true;
    $("editDeviceId").value = hit.device_id || "";
    $("editHostIp").value = hit.host_name || "";
    $("editDisplayName").value = hit.display_name || hit.agent_id || "";
    $("editPort").value = hit.port || "";
    $("editRunState").value = "";
    $("editDesc").value = hit.desc || "";

    $("agentEditModal").classList.remove("hidden");
    $("agentEditModal").setAttribute("aria-hidden", "false");
  }

  function openCreateModal() {
    state.createMode = true;
    state.modalOpen = true;
    state.editingAgentId = "";
    $("editAgentId").value = "";
    $("editAgentId").readOnly = false;
    $("editDeviceId").value = "";
    $("editHostIp").value = "";
    $("editDisplayName").value = "";
    $("editPort").value = "";
    $("editRunState").value = "ONLINE";
    $("editDesc").value = "";
    $("agentEditHint").textContent = "新建后 2 秒内会同步到卡片，并可绑定到拓扑节点";
    $("agentEditModal").classList.remove("hidden");
    $("agentEditModal").setAttribute("aria-hidden", "false");
  }

  function closeEditModal() {
    state.modalOpen = false;
    state.editingAgentId = "";
    state.createMode = false;
    $("agentEditModal").classList.add("hidden");
    $("agentEditModal").setAttribute("aria-hidden", "true");
    $("agentEditHint").textContent = "编辑保存后 2 秒内会同步到卡片";
  }

  async function saveEditModal() {
    const agentId = state.createMode
      ? String($("editAgentId").value || "").trim()
      : state.editingAgentId;
    if (!agentId) {
      alert("请先填写 Agent ID");
      return;
    }

    const payload = {
      agent_id: agentId,
      display_name: String($("editDisplayName").value || "").trim(),
      device_id: String($("editDeviceId").value || "").trim(),
      host_name: String($("editHostIp").value || "").trim(),
      port: Number($("editPort").value || 0),
      desc: String($("editDesc").value || "").trim(),
      project_id: state.projectId,
    };
    if (state.createMode) {
      payload.create_if_missing = true;
      payload.status = "ONLINE";
      payload.run_state = "ONLINE";
    }
    const rs = String($("editRunState").value || "").trim();
    if (rs) payload.run_state = rs;

    const btn = $("btnSaveAgentEdit");
    const oldText = btn.textContent;
    btn.textContent = "保存中...";
    btn.disabled = true;
    try {
      const resp = await OpsApi.upsertAgent(payload);
      if (!resp || resp.ok === false) {
        alert((resp && (resp.message || resp.error_code || resp.error)) || "保存失败");
        return;
      }
      closeEditModal();
      await loadData();
    } finally {
      btn.disabled = false;
      btn.textContent = oldText;
    }
  }

  async function probeAgentConnectivity() {
    const host = String($("editHostIp").value || "").trim();
    const port = Number($("editPort").value || 0);
    if (!host || !port) {
      alert("请先填写 IP 和端口");
      return;
    }
    const btn = $("btnProbeAgent");
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = "探测中...";
    try {
      const resp = await OpsApi.probeAgent({ host_name: host, port });
      if (!resp || resp.ok === false) {
        alert((resp && (resp.message || resp.error || "连通性失败")) || "连通性失败");
        return;
      }
      alert(`连通性成功 RTT=${resp.rtt_ms}ms`);
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
  }

  function bindEvents() {
    $("btnRefreshCp").addEventListener("click", () => loadData());
    $("btnCreateAgent").addEventListener("click", openCreateModal);
    $("btnCleanupExpired").addEventListener("click", async () => {
      const raw = window.prompt("请输入过期阈值小时数（默认 24）", "24");
      if (raw == null) return;
      const ttlHours = Number(raw || 24);
      if (!Number.isFinite(ttlHours) || ttlHours <= 0) {
        alert("请输入有效的小时数");
        return;
      }
      const ok = window.confirm(`确认清理超过 ${Math.round(ttlHours)} 小时未心跳的 Agent 吗？该操作会同步移除对应失效绑定。`);
      if (!ok) return;
      const btn = $("btnCleanupExpired");
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
        await loadData();
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
      $("filterFresh").value = "active_120";
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
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = setInterval(() => {
      if (!state.modalOpen) loadData();
    }, POLL_MS);
  }

  async function boot() {
    const root = document.querySelector(".ops-page");
    state.projectId = String((root && root.dataset && root.dataset.projectId) || "").trim();
    bindEvents();
    await loadData();
    startPolling();
  }

  boot().catch((e) => console.error("[agent-control] boot failed", e));
})();
