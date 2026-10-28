  function resolveWorkbenchModePreferences(meta) {
    const serverLocked = String((meta || {}).workbench_locked_mode || "");
    const serverMode = String((meta || {}).workbench_mode || "");
    let localMode = "";
    let localLocked = "";
    try {
      const raw = localStorage.getItem(modeStorageKey());
      if (raw) {
        const obj = JSON.parse(raw);
        localMode = String((obj || {}).mode || "");
        localLocked = String((obj || {}).lockedMode || ((obj || {}).modeLocked ? localMode : "") || "");
      }
    } catch (_) {}

    state.lockedMode = "";
    if (serverLocked && ["edit", "run", "test"].includes(serverLocked)) {
      state.lockedMode = serverLocked;
      state.mode = serverLocked;
      return;
    }
    if (localLocked && ["edit", "run", "test"].includes(localLocked)) {
      state.lockedMode = localLocked;
      state.mode = localLocked;
      return;
    }
    if (serverMode && ["edit", "run", "test"].includes(serverMode)) {
      state.mode = serverMode;
      return;
    }
    if (localMode && ["edit", "run", "test"].includes(localMode)) {
      state.mode = localMode;
    }
  }

  function inferWorkbenchModeFromRuntime() {
    let changed = enforceLockedMode();
    if (state.lockedMode) return changed;
    if (clusterServicesRunning()) {
      if (state.mode !== "run") {
        state.mode = "run";
        if (!state.autoRunModeLogged) {
          logMode("检测到架构服务已运行，自动进入运行模式", "");
          state.autoRunModeLogged = true;
        }
        persistWorkbenchMode();
        return true;
      }
      return changed;
    }
    if (isTestInProgress() && state.mode !== "test") {
      state.mode = "test";
      return true;
    }
    return changed;
  }

  function liveRunningNodeIdSet() {
    const ids = new Set();
    if (!isRuntimeVizMode()) return ids;
    (state.topology.nodes || []).forEach((n) => {
      if ((n.ui || {}).list_only) return;
      const ag = resolveAgentForNode(n);
      const aid = String((state.nodeBindings || {})[n.id] || (ag && ag.agent_id) || "");
      if (nodeIsLiveRunning(n, ag, aid)) ids.add(String(n.id));
    });
    return ids;
  }

  function edgeIsLiveRunning(edge, liveNodeIds) {
    if (!isRuntimeVizMode() || !edge) return false;
    if (!state.flowViz.edgesEnabled) return false;
    const fromId = String(edge.from || "");
    const toId = String(edge.to || "");
    if (!liveNodeIds.has(fromId) || !liveNodeIds.has(toId)) return false;
    const toFlowSt = String((state.flowViz.statusByNode || {})[toId] || "").toUpperCase();
    if (toFlowSt && ["FAILED", "TIMEOUT", "CANCELED", "OFFLINE", "ERROR", "PENDING", "LEASED", "STARTING", "SKIPPED", "STOPPED"].includes(toFlowSt)) return false;
    return true;
  }

  function buildSequentialFlowVizFromItems(items, op, opts) {
    const requireProbe = !!(opts && opts.requireProbe);
    const effectiveOp = String(op || "start").toLowerCase();
    const ordered = (items || []).slice().sort((a, b) => Number(a.seq || 0) - Number(b.seq || 0));
    const statusByNode = {};
    const vizNodes = [];
    let hasFailure = false;
    ordered.forEach((it) => {
      const nid = String((it && it.node_id) || "");
      const st = String((it && it.status) || "PENDING").toUpperCase();
      if (!nid) return;
      if (effectiveOp === "stop") {
        if (st === "PENDING") {
          statusByNode[nid] = "RUNNING";
          vizNodes.push(nid);
        } else if (st === "RUNNING" || st === "LEASED") {
          statusByNode[nid] = "STARTING";
          vizNodes.push(nid);
        } else if (st === "FAILED" || st === "TIMEOUT") {
          statusByNode[nid] = "FAILED";
          vizNodes.push(nid);
          hasFailure = true;
        } else if (st === "SUCCESS") {
          statusByNode[nid] = "STOPPED";
        }
        return;
      }
      if (st === "SUCCESS") {
        let probeOk = true;
        if (requireProbe) {
          const topoNode = (state.topology.nodes || []).find((n) => String(n.id) === nid);
          const ag = topoNode ? resolveAgentForNode(topoNode) : null;
          const aid = String((state.nodeBindings || {})[nid] || (ag && ag.agent_id) || "");
          const rs = topoNode ? nodeRuntimeStatus(topoNode, ag, aid) : { cls: "err" };
          probeOk = rs.cls === "ok";
        }
        if (probeOk) {
          statusByNode[nid] = "RUNNING";
          vizNodes.push(nid);
        } else {
          statusByNode[nid] = "STARTING";
          vizNodes.push(nid);
          hasFailure = true;
        }
      } else if (st === "RUNNING" || st === "LEASED") {
        statusByNode[nid] = "STARTING";
        vizNodes.push(nid);
      } else if (st === "FAILED" || st === "TIMEOUT" || st === "CANCELED") {
        statusByNode[nid] = st;
        vizNodes.push(nid);
        hasFailure = true;
      } else if (st === "SKIPPED") {
        statusByNode[nid] = "SKIPPED";
      }
    });
    const total = ordered.length;
    const successCount = ordered.filter((it) => String((it && it.status) || "").toUpperCase() === "SUCCESS").length;
    const edgesEnabled = total > 0 && successCount === total && !hasFailure;
    return { statusByNode, vizNodes, edgesEnabled, successCount, total, hasFailure };
  }

  function syncPartialRecoveryFromAgent() {
    if (!state.runtimePartialRecovery || state.runtimeSteady) return false;
    const nodes = (state.topology.nodes || []).filter((n) => !(n.ui || {}).list_only);
    if (!nodes.length) return false;
    const healthy = healthyRunningNodeIdSet();
    if (!healthy.size) return false;
    const statusByNode = {};
    Array.from(healthy).forEach((nid) => { statusByNode[nid] = "RUNNING"; });
    const allHealthy = healthy.size >= nodes.length;
    syncFlowViz("run", Array.from(healthy), statusByNode, { edgesEnabled: allHealthy });
    redrawGraph();
    if (allHealthy) {
      state.runtimePartialRecovery = false;
      logMode("Agent 侧节点已全部就绪，拓扑连线动画已同步开启", "ok");
      finalizeRuntimeStartSteady(state.runtimeRunId || "");
      return true;
    }
    return true;
  }

  function modeStorageKey() {
    return MODE_STORAGE_KEY + ":" + [state.projectId, state.envKey, state.topologyId].map((x) => String(x || "")).join(":");
  }

  function isModeLocked() {
    return !!state.lockedMode;
  }

  function isTestInProgress() {
    if (state.mode !== "test") return false;
    if (state.runtimePollTimer && state.runtimeRunId) return true;
    return !!(state.flowViz.mode === "test" && state.flowViz.nodes && state.flowViz.nodes.size);
  }

  function reconcileFlowVizWithAgentTruth() {
    if (!isRunMode()) return;
    if (state.runtimeStopping) return;
    const nodes = (state.topology.nodes || []).filter((n) => !(n.ui || {}).list_only);
    const healthy = healthyRunningNodeIdSet();
    if (!healthy.size) {
      if (state.flowViz.mode === "run" || state.runtimeSteady) {
        clearFlowViz(true, "reconcile-all-stopped");
        state.runtimeSteady = false;
        state.runtimePartialRecovery = false;
        if ($("runtimeStatusPill")) {
          $("runtimeStatusPill").textContent = "已停止";
          $("runtimeStatusPill").className = "state-pill state-muted";
        }
      }
      return;
    }
    const statusByNode = {};
    Array.from(healthy).forEach((nid) => { statusByNode[nid] = "RUNNING"; });
    const allHealthy = healthy.size >= nodes.length;
    syncFlowViz("run", Array.from(healthy), statusByNode, { edgesEnabled: allHealthy });
    state.runtimeSteady = allHealthy;
    if ($("runtimeStatusPill")) {
      $("runtimeStatusPill").textContent = allHealthy ? "运行中" : ("部分运行 " + healthy.size + "/" + nodes.length);
      $("runtimeStatusPill").className = "state-pill " + (allHealthy ? "state-ok" : "state-warn");
    }
    if (allHealthy) {
      const steadyMetrics = {};
      (state.topology.edges || []).forEach((e) => {
        if (healthy.has(e.from) && healthy.has(e.to)) steadyMetrics[e.id] = edgeMetrics(e.id, "RUNNING");
      });
      state.flowViz.metricsByEdge = steadyMetrics;
    } else {
      state.flowViz.metricsByEdge = {};
    }
  }

  function syncLiveFlowVisualsForMode() {
    if (!isRuntimeVizMode()) return;
    if (state.runtimeStopping) return;
    if (state.runtimePartialRecovery) return;
    if (state.mode === "test" && !isTestInProgress()) return;
    if (isRunMode()) {
      reconcileFlowVizWithAgentTruth();
      return;
    }
    const liveIds = liveRunningNodeIdSet();
    const healthyIds = healthyRunningNodeIdSet();
    const sourceIds = liveIds.size ? liveIds : healthyIds;
    if (!sourceIds.size) return;
    const statusByNode = {};
    sourceIds.forEach((nid) => { statusByNode[nid] = "RUNNING"; });
    syncFlowViz("test", Array.from(sourceIds), statusByNode, { edgesEnabled: sourceIds.size >= (state.topology.nodes || []).filter((n) => !(n.ui || {}).list_only).length });
  }

  function applyWorkbenchModeFromMeta(meta) {
    resolveWorkbenchModePreferences(meta);
  }

  async function persistWorkbenchMode(opts) {
    saveModeState();
    const payload = Object.assign(currentScope(), {
      workbench_mode: state.mode,
      workbench_locked_mode: opts && Object.prototype.hasOwnProperty.call(opts, "lockedMode")
        ? (opts.lockedMode || "")
        : (state.lockedMode || ""),
    });
    try {
      const r = await OpsApi.saveWorkbenchMode(payload);
      if (r && r.ok !== false && state.topology.meta) {
        state.topology.meta.workbench_mode = r.workbench_mode || state.mode;
        state.topology.meta.workbench_locked_mode = r.workbench_locked_mode != null ? r.workbench_locked_mode : (state.lockedMode || "");
        state.topology.meta.workbench_mode_updated_at = r.workbench_mode_updated_at || "";
      }
    } catch (_) {}
  }

  function trySetMode(next, opts) {
    const mode = String(next || "edit");
    if (!["edit", "run", "test"].includes(mode)) return false;
    if (state.lockedMode && mode !== state.lockedMode) {
      toast("当前已锁定为" + (MODE_LABELS[state.lockedMode] || state.lockedMode) + "，无法切换", "warn");
      applyModeUI();
      return false;
    }
    if (state.mode === mode) return true;
    state.mode = mode;
    applyModeUI();
    if (!(opts && opts.silent)) logMode("切换到" + (MODE_LABELS[mode] || mode));
    saveModeState();
    if (!(opts && opts.skipPersist)) persistWorkbenchMode({ lockedMode: state.lockedMode || "" });
    return true;
  }

  async function lockCurrentMode() {
    state.lockedMode = state.mode;
    applyModeUI();
    logMode("模式已锁定为" + (MODE_LABELS[state.lockedMode] || state.lockedMode));
    toast("已锁定 · " + (MODE_LABELS[state.lockedMode] || state.lockedMode), "ok");
    await persistWorkbenchMode({ lockedMode: state.lockedMode });
  }

  async function unlockMode() {
    state.lockedMode = "";
    applyModeUI();
    logMode("模式已解锁");
    toast("模式已解锁", "ok");
    await persistWorkbenchMode({ lockedMode: "" });
  }

  function saveModeState() {
    try {
      localStorage.setItem(modeStorageKey(), JSON.stringify({
        mode: state.mode,
        lockedMode: state.lockedMode || "",
        ts: Date.now(),
      }));
    } catch (_) {}
  }

  function loadModeStateFromLocal() {
    resolveWorkbenchModePreferences(state.topology && state.topology.meta);
  }

  function saveRuntimeState() {
    try {
      localStorage.setItem(RUNTIME_STORAGE_KEY, JSON.stringify({
        runId: state.runtimeRunId || "",
        runtimeSteady: !!state.runtimeSteady,
        requestedOp: state.runtimeRequestedOp || "",
        ts: Date.now(),
      }));
    } catch (_) {}
  }

  function loadRuntimeState() {
    try {
      const raw = localStorage.getItem(RUNTIME_STORAGE_KEY);
      if (!raw) return;
      const obj = JSON.parse(raw);
      const runId = String((obj || {}).runId || "");
      if (runId) state.runtimeRunId = runId;
      state.runtimeSteady = false;
      state.runtimeRequestedOp = String((obj || {}).requestedOp || "");
    } catch (_) {}
  }

  function logMode(message, level) {
    const box = $("modeLog");
    if (!box) return;
    const t = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    const levelText = level === "error" ? "失败" : (level === "warn" ? "提示" : "信息");
    const line = document.createElement("div");
    line.className = "mode-log-line " + (level === "error" ? "error" : (level === "warn" ? "warn" : "info"));
    line.innerHTML = '<span class="mode-log-icon" aria-hidden="true"></span>'
      + '<span class="mode-log-time">' + esc(t) + '</span>'
      + ' <span class="mode-log-level">【' + levelText + '】</span>'
      + esc(message);
    box.prepend(line);
    while (box.childNodes.length > 500) box.removeChild(box.lastChild);
  }

  function appendJsonDetail(title, obj) {
    const box = $("modeLogDetails");
    if (!box) return;
    const wrap = document.createElement("details");
    wrap.className = "mode-json";
    const sm = document.createElement("summary");
    sm.textContent = title;
    const pre = document.createElement("pre");
    try {
      pre.textContent = JSON.stringify(obj == null ? {} : obj, null, 2);
    } catch (_) {
      pre.textContent = String(obj);
    }
    wrap.appendChild(sm);
    wrap.appendChild(pre);
    box.prepend(wrap);
    while (box.childNodes.length > 120) box.removeChild(box.lastChild);
  }

  function testLogHeader(title, detail) {
    logMode("========== " + title + " ==========");
    if (detail) logMode(detail);
  }

  function testLogKV(key, value) {
    let v = value;
    if (typeof v === "object") {
      try { v = JSON.stringify(v); } catch (_) { v = String(v); }
    }
    logMode("  - " + key + ": " + String(v == null ? "" : v));
  }

