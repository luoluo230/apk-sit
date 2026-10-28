  async function boot() {
    const page = document.querySelector(".ops-topology-app");
    const ds = (page && page.dataset) ? page.dataset : {};
    let queryProject = "";
    let queryEnv = "";
    let queryTopology = "";
    try {
      const q = new URLSearchParams(location.search);
      queryProject = String(q.get("project_id") || "");
      queryEnv = String(q.get("env_key") || "");
      queryTopology = String(q.get("topology_id") || "");
      state.acceptanceStructuredAddFrom = q.get("structured_add_from") || "";
    } catch (_) {
      state.acceptanceStructuredAddFrom = "";
    }
    state.projectId = String(ds.projectId || queryProject || "GomeKu");
    state.envKey = String(ds.envKey || queryEnv || "production");
    state.topologyId = String(ds.topologyId || queryTopology || "");
    if (!state.topologyId && state.projectId === "GomeKu" && state.envKey === "production") {
      state.topologyId = "topology-gomeku-production-default";
    }
    loadRuntimeState();
    bindEvents();
    await loadAll();
    startAgentsRealtimeTick();
    inferWorkbenchModeFromRuntime();
    syncLiveFlowVisualsForMode();
    applyModeUI();
    redrawGraph();
    const act = await OpsApi.runtimeFlowActive(currentScope());
    if (state.runtimeStopping || state.runtimeStarting) await refreshAgentsIfNeeded(true);
    if (act && act.ok !== false && act.active && act.run_id && String(act.reason || "") === "start_alive") {
      if (act.live_verified || clusterServicesRunning()) {
        state.mode = "run";
        if (!state.lockedMode) state.lockedMode = "run";
        state.runtimeRunId = String(act.run_id || "");
        state.runtimeRequestedOp = "start";
        await finalizeRuntimeStartSteady(state.runtimeRunId);
        logMode("后端探活确认服务运行中，已恢复运行跟踪: " + state.runtimeRunId, "");
      } else {
        logMode("检测到历史启动编排记录(" + act.run_id + ")，但 Agent 探活未通过（" + Number(act.live_count || 0) + "/" + Number(act.live_total || 0) + "），不恢复运行态", "warn");
        reconcileFlowVizWithAgentTruth();
      }
      maybeOpenStructuredAddFromQuery();
      return;
    }
    if (state.mode === "run" && state.runtimeRunId) {
      logMode("检测到刷新前运行态，自动恢复运行跟踪: " + state.runtimeRunId, "warn");
      await pollRuntimeRun(state.runtimeRunId);
      stopRuntimePolling();
      const terminal = String(state.runtimeLastStatus || "").toLowerCase();
      if (terminal !== "success" && terminal !== "failed") {
        state.runtimePollTimer = setInterval(() => { pollRuntimeRun(state.runtimeRunId); }, 1200);
      }
    } else if (state.mode === "run") {
      reconcileFlowVizWithAgentTruth();
      redrawGraph();
    }
    maybeOpenStructuredAddFromQuery();
  }

  boot().catch((e) => {
    console.error(e);
    toast("拓扑工作台初始化失败，请刷新后重试", "error");
  });
