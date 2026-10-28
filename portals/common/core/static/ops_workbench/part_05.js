  function testLogStep(i, step) {
    const idx = i + 1;
    const nodeId = String((step && step.node_id) || "-");
    const ok = !!(step && step.ok);
    const msg = String((step && step.message) || "");
    const degraded = !!(step && step.degraded);
    const result = (step && step.result) || {};
    const latency = result.latency_ms != null ? result.latency_ms : "-";
    const status = result.status != null ? result.status : "-";
    const resultCode = result.result_code || "-";
    const traceId = result.trace_id || "-";
    logMode("[STEP " + idx + "] node=" + nodeId + " ok=" + ok + " degraded=" + degraded + " latency_ms=" + latency + " status=" + status + " code=" + resultCode);
    if (msg) logMode("         message=" + msg);
    if (traceId && traceId !== "-") logMode("         trace_id=" + traceId);
    if (result && result.data && typeof result.data === "object") {
      const keys = Object.keys(result.data).slice(0, 8).join(",");
      if (keys) logMode("         data_keys=" + keys);
    }
    if (!ok && result && (result.result_message || result.message)) {
      logMode("         error_detail=" + String(result.result_message || result.message), "error");
    }
    appendJsonDetail("STEP " + idx + " 原始响应", step || {});
  }

  function stopRuntimePolling() {
    if (state.runtimePollTimer) {
      clearInterval(state.runtimePollTimer);
      state.runtimePollTimer = null;
    }
  }

  function stopRuntimeLiveWait() {
    state.runtimeAwaitLive = false;
    state.runtimeAwaitLiveUntil = 0;
    if (state.runtimeLiveWaitTimer) {
      clearInterval(state.runtimeLiveWaitTimer);
      state.runtimeLiveWaitTimer = null;
    }
  }

  async function finalizeRuntimeStartSteady(runId) {
    state.runtimeAwaitLive = false;
    stopRuntimeLiveWait();
    await refreshAgentsIfNeeded(true);
    const nodes = (state.topology.nodes || []).filter((n) => !(n.ui || {}).list_only);
    const healthy = healthyRunningNodeIdSet();
    if (!healthy.size) {
      state.runtimeSteady = false;
      clearFlowViz(true, "finalize-no-healthy-services");
      if ($("runtimeStatusPill")) {
        $("runtimeStatusPill").textContent = "已停止";
        $("runtimeStatusPill").className = "state-pill state-muted";
      }
      logMode("Agent 探活未通过，未进入运行态可视化", "warn");
      redrawGraph();
      return;
    }
    state.runtimeSteady = healthy.size >= nodes.length;
    state.mode = "run";
    state.lockedMode = state.runtimeSteady ? "run" : "";
    const steadyNodes = Array.from(healthy);
    const steadyStatus = {};
    steadyNodes.forEach((nid) => { steadyStatus[String(nid)] = "RUNNING"; });
    syncFlowViz("run", steadyNodes, steadyStatus, { edgesEnabled: state.runtimeSteady });
    const steadyMetrics = {};
    if (state.runtimeSteady) {
      (state.topology.edges || []).forEach((e) => {
        if (steadyNodes.includes(e.from) && steadyNodes.includes(e.to)) steadyMetrics[e.id] = edgeMetrics(e.id, "RUNNING");
      });
    }
    state.flowViz.metricsByEdge = steadyMetrics;
    if ($("runtimeStatusPill")) {
      $("runtimeStatusPill").textContent = state.runtimeSteady ? "运行中" : ("部分运行 " + steadyNodes.length + "/" + nodes.length);
      $("runtimeStatusPill").className = "state-pill " + (state.runtimeSteady ? "state-ok" : "state-warn");
    }
    applyModeUI();
    redrawGraph();
    dbg("runtime-steady-on", { runId, activeNodes: steadyNodes.length, allHealthy: state.runtimeSteady });
    logMode(state.runtimeSteady
      ? "启动成功，Agent 探活全部通过，运行动画已开启"
      : ("部分节点已就绪（" + steadyNodes.length + "/" + nodes.length + "），与 Agent 控制面板已同步"));
    saveModeState();
    if (state.runtimeSteady) persistWorkbenchMode({ lockedMode: "run" });
    saveRuntimeState();
  }

  function startRuntimeLiveWait(runId) {
    stopRuntimeLiveWait();
    state.runtimeAwaitLive = true;
    state.runtimeAwaitLiveUntil = Date.now() + 120000;
    logMode("GameServer 启动中，等待端口探活就绪...", "warn");
    const tick = async () => {
      if (!state.runtimeAwaitLive) return;
      await refreshAgentsIfNeeded(true);
      redrawGraph();
      if (clusterServicesRunning()) {
        await finalizeRuntimeStartSteady(runId);
        toast("GameServer 已就绪", "ok");
        return;
      }
      if (Date.now() >= state.runtimeAwaitLiveUntil) {
        stopRuntimeLiveWait();
        state.runtimeSteady = false;
        clearFlowViz(true, "runtime-live-wait-timeout");
        toast("GameServer 启动超时，请查看模式日志或 apk-site-service-start.log", "error");
        logMode("等待 GameServer 探活超时（120s），已清除运行态可视化", "error");
        redrawGraph();
      }
    };
    tick();
    state.runtimeLiveWaitTimer = setInterval(tick, 2000);
  }

  async function finalizeRuntimeStop(reason) {
    stopRuntimeLiveWait();
    state.runtimeStopping = false;
    state.runtimeSteady = false;
    state.runtimePartialRecovery = false;
    state.runtimeRunId = "";
    state.runtimeRequestedOp = "";
    state.runtimeLastStatus = "";
    state.runtimeProgressSig = "";
    state.runtimeLogSeen = new Set();
    state.lockedMode = "";
    stopRuntimePolling();
    clearFlowViz(true, reason || "finalizeRuntimeStop");
    saveRuntimeState();
    saveModeState();
    try {
      await persistWorkbenchMode({ lockedMode: "" });
    } catch (_) {}
    await refreshAgentsIfNeeded(true);
    updateRuntimeSummary({
      run_id: "-",
      total: 0,
      done: 0,
      running: 0,
      success: 0,
      failed: 0,
      warn: 0,
      progress_pct: 0,
    });
    if ($("runtimeStatusPill")) {
      $("runtimeStatusPill").textContent = "已停止";
      $("runtimeStatusPill").className = "state-pill state-muted";
    }
    applyModeUI();
    redrawGraph();
    renderRuntimeNodeList();
    logMode("全流程已停止，运行态已清除");
  }

  function nodeSeed(id) {
    const s = String(id || "");
    let h = 0;
    for (let i = 0; i < s.length; i += 1) h = ((h << 5) - h) + s.charCodeAt(i);
    return Math.abs(h || 1);
  }

  function metricTriplet(nodeId, status) {
    const now = Date.now();
    const sd = nodeSeed(nodeId) + Math.floor(now / 1500) + (state.flowViz.seed || 0);
    const b = (n, m) => Math.max(6, Math.min(96, (n % m)));
    const risk = ["FAILED", "TIMEOUT", "CANCELED"].includes(String(status || "").toUpperCase()) ? 18 : 0;
    const cpu = b(sd * 7 + 31, 76) + risk;
    const mem = b(sd * 11 + 17, 70) + Math.floor(risk * 0.6);
    const qps = b(sd * 13 + 43, 66) + Math.floor(risk * 0.45);
    return { cpu, mem, qps };
  }

  function realMetricTriplet(nodeId) {
    const aid = String((state.nodeBindings || {})[String(nodeId || "")] || "");
    const ag = (state.agents || []).find((x) => String((x || {}).agent_id || "") === aid) || null;
    if (!ag) return null;
    const services = Array.isArray(ag.services) ? ag.services : [];
    const svc = services.find((s) => String((s || {}).node_id || (s || {}).service_id || "") === String(nodeId || ""));
    const mRaw = (svc && svc.metrics && typeof svc.metrics === "object") ? svc.metrics : ((ag.metrics && typeof ag.metrics === "object") ? ag.metrics : null);
    const m = (mRaw && mRaw.control && typeof mRaw.control === "object") ? mRaw.control : mRaw;
    if (!m) return null;
    const cpu = Number(m.cpu_percent);
    const mem = Number(m.mem_percent);
    const qps = Number(m.qps);
    const rtt = Number(m.rtt_ms);
    const hasAny = Number.isFinite(cpu) || Number.isFinite(mem) || Number.isFinite(qps) || Number.isFinite(rtt);
    if (!hasAny) return null;
    const live = String(m.source || "") === "runtime.sample" || !!ag.metrics_live;
    return {
      cpu: Number.isFinite(cpu) ? Math.max(0, Math.min(100, cpu)) : 0,
      mem: Number.isFinite(mem) ? Math.max(0, Math.min(100, mem)) : 0,
      qps: Number.isFinite(qps) ? Math.max(0, qps) : 0,
      rtt: Number.isFinite(rtt) ? Math.max(0, rtt) : 0,
      source: live ? "runtime.sample" : String(m.source || "real"),
      updatedAt: String(m.updated_at || ag.last_seen || ""),
    };
  }

  function deviceMetricTriplet(deviceId) {
    const did = String(deviceId || "");
    if (!did) return null;
    const rows = (state.agents || []).filter((x) => String((x || {}).device_id || "") === did);
    if (!rows.length) return null;
    let latest = null;
    rows.forEach((ag) => {
      const m = (ag && ag.metrics && typeof ag.metrics === "object") ? ag.metrics : null;
      if (!m) return;
      const tRaw = String(m.updated_at || ag.last_seen || "");
      const t = new Date(tRaw).getTime();
      if (!Number.isFinite(t)) return;
      if (!latest || t > latest.t) latest = { t, m };
    });
    if (!latest || !latest.m) return null;
    const cpu = Number(latest.m.cpu_percent);
    const mem = Number(latest.m.mem_percent);
    const qps = Number(latest.m.qps);
    const rtt = Number(latest.m.rtt_ms);
    const hasAny = Number.isFinite(cpu) || Number.isFinite(mem) || Number.isFinite(qps) || Number.isFinite(rtt);
    if (!hasAny) return null;
    return {
      cpu: Number.isFinite(cpu) ? Math.max(0, Math.min(100, cpu)) : 0,
      mem: Number.isFinite(mem) ? Math.max(0, Math.min(100, mem)) : 0,
      qps: Number.isFinite(qps) ? Math.max(0, qps) : 0,
      rtt: Number.isFinite(rtt) ? Math.max(0, rtt) : 0,
    };
  }

  function nodeMetrics(nodeId, status) {
    const real = realMetricTriplet(nodeId);
    if (real) {
      const ag = boundAgentForNode(nodeId);
      const dev = deviceMetricTriplet((ag || {}).device_id);
      if (dev) {
        return {
          cpu: dev.cpu,
          mem: dev.mem,
          qps: dev.qps,
          rtt: dev.rtt,
          source: "real",
          updatedAt: real.updatedAt,
        };
      }
      return real;
    }
    return { cpu: 0, mem: 0, qps: 0, rtt: 0, source: "missing", updatedAt: "" };
  }

  function mergeAgentPayload(d) {
    if (!d || d.ok === false) return false;
    if (Array.isArray(d.agents)) {
      state.agents = d.agents;
      state.agentsRefreshAt = Date.now();
      state.agentsHydrated = true;
    }
    if (d.bindings && typeof d.bindings === "object") {
      state.nodeBindings = Object.assign({}, state.nodeBindings, d.bindings);
    }
    if (d.service_bindings && typeof d.service_bindings === "object") {
      state.serviceBindings = Object.assign({}, state.serviceBindings, d.service_bindings);
    }
    return true;
  }

  function agentsRequestOptions(force, extra) {
    const opts = Object.assign({
      topology_id: state.topologyId,
      env_key: state.envKey,
      live: !!force || !!state.runtimeStopping || !!state.runtimeStarting,
    }, extra || {});
    return opts;
  }

  async function refreshAgentsIfNeeded(force, extra) {
    const d = await OpsApi.agents(state.projectId, agentsRequestOptions(force, extra));
    if (d && d.ok === false && (d.error_code === 'OPS_AUTH_REQUIRED' || d.error === 'auth_redirect')) {
      window.location.href = '/login';
      return;
    }
    mergeAgentPayload(d);
  }

  function startAgentsRealtimeTick() {
    if (state.agentsTickTimer) clearInterval(state.agentsTickTimer);
    state.agentsTickTimer = setInterval(async () => {
      await refreshAgentsIfNeeded(state.runtimeStopping || state.runtimeStarting);
      if (state.runtimeStopping || state.runtimeStarting) {
        redrawGraph();
        renderRuntimeNodeList();
        const cur = String((($("insNodeId") || {}).value || "")).trim();
        const curNode = cur ? getNode(cur) : null;
        if (curNode) updateInspectorHeader(curNode);
        return;
      }
      const modeChanged = inferWorkbenchModeFromRuntime();
      if (modeChanged) applyModeUI();
      syncLiveFlowVisualsForMode();
      syncPartialRecoveryFromAgent();
      if (isRunMode()) reconcileFlowVizWithAgentTruth();
      redrawGraph();
    }, 2000);
  }

  function syncFlowViz(mode, nodeIds, statusByNode, opts) {
    const nset = new Set((nodeIds || []).filter(Boolean));
    const edgesEnabled = !!(opts && opts.edgesEnabled);
    const eset = new Set();
    if (edgesEnabled) {
      (state.topology.edges || []).forEach((e) => {
        if (nset.has(e.from) && nset.has(e.to)) eset.add(e.id);
      });
    }
    state.flowViz.mode = mode || "";
    state.flowViz.nodes = nset;
    state.flowViz.edges = eset;
    state.flowViz.statusByNode = statusByNode || {};
    state.flowViz.edgesEnabled = edgesEnabled;
    state.flowViz.seed = Date.now();
  }

  function clearFlowViz(force, reason) {
    dbg("clearFlowViz", { force: !!force, reason: reason || "", mode: state.mode, runtimeSteady: !!state.runtimeSteady });
    if (!force && state.mode === "run" && healthyRunningNodeIdSet().size > 0 && (state.runtimeSteady || liveRunningNodeIdSet().size > 0)) {
      logMode("已忽略一次可视化清理请求（运行态保护中）", "warn");
      return;
    }
    if (state.flowViz.replayTimer) {
      clearInterval(state.flowViz.replayTimer);
      state.flowViz.replayTimer = null;
    }
    state.flowViz.mode = "";
    state.flowViz.nodes = new Set();
    state.flowViz.edges = new Set();
    state.flowViz.statusByNode = {};
    state.flowViz.metricsByEdge = {};
    state.flowViz.history = [];
    state.flowViz.edgesEnabled = false;
  }

  function edgeMetrics(edgeId, status) {
    const edge = (state.topology.edges || []).find((e) => String(e.id) === String(edgeId));
    if (edge) {
      const fm = nodeMetrics(edge.from, status);
      const tm = nodeMetrics(edge.to, status);
      const hasReal = fm.source === "real" || tm.source === "real";
      if (hasReal) {
        const qps = Math.max(0, Math.round((Number(fm.qps || 0) + Number(tm.qps || 0)) / (tm.qps ? 2 : 1)));
        const latency = Math.max(1, Math.round((Number(fm.rtt || 0) + Number(tm.rtt || 0)) / ((fm.rtt || tm.rtt) ? 2 : 1)));
        const fail = ["FAILED", "TIMEOUT", "CANCELED"].includes(String(status || "").toUpperCase());
        return { tps: qps || 0, latency: latency || 0, err: fail ? 12 : 0, source: "real" };
      }
    }
    return null;
  }

  function pushFlowSnapshot() {
    const snap = {
      ts: Date.now(),
      mode: state.flowViz.mode,
      nodes: Array.from(state.flowViz.nodes || []),
      edges: Array.from(state.flowViz.edges || []),
      statusByNode: Object.assign({}, state.flowViz.statusByNode || {}),
      metricsByEdge: Object.assign({}, state.flowViz.metricsByEdge || {}),
    };
    const h = state.flowViz.history || [];
    h.push(snap);
    const minTs = Date.now() - 10000;
    state.flowViz.history = h.filter((x) => x && x.ts >= minTs).slice(-80);
  }

