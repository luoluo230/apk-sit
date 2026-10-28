  function applyModeUI() {
    enforceLockedMode();
    const effectiveMode = displayWorkbenchMode();
    const map = {
      edit: { hint: "当前为编辑模式，可调整拓扑结构、节点属性与绑定关系。", run: "none", test: "none" },
      run: { hint: "当前为运行模式，聚焦全流程启动、停止与运行回放。", run: "flex", test: "none" },
      test: { hint: "测试模式支持完整架构与指定链路段验证；模式锁定后不可切换。", run: "none", test: "flex" },
    };
    const cfg = map[effectiveMode] || map.edit;
    const modeHint = $("modeHint");
    if (modeHint) modeHint.textContent = cfg.hint;
    const runBar = $("runBar");
    const testBar = $("testBar");
    if (runBar) runBar.style.display = cfg.run;
    if (testBar) testBar.style.display = cfg.test;
    const modeSelect = $("modeSelect");
    const locked = isModeLocked();
    const modeLabel = MODE_LABELS[effectiveMode] || effectiveMode;
    const lockLabel = locked ? ("已锁定 · " + (MODE_LABELS[state.lockedMode] || state.lockedMode)) : "已解锁";
    if ($("modeCurrentValue")) $("modeCurrentValue").textContent = modeLabel;
    if ($("modeCurrentBanner")) {
      $("modeCurrentBanner").dataset.mode = effectiveMode;
      $("modeCurrentBanner").classList.toggle("is-locked", locked);
    }
    const headerBadge = $("topologyModeBadge");
    if (headerBadge) {
      headerBadge.textContent = locked ? lockLabel : modeLabel;
      headerBadge.dataset.mode = effectiveMode;
      headerBadge.classList.toggle("is-locked", locked);
    }
    if (modeSelect) {
      modeSelect.value = effectiveMode;
      modeSelect.querySelectorAll("option").forEach((opt) => {
        opt.disabled = locked && opt.value !== state.lockedMode;
      });
    }
    document.querySelectorAll("[data-mode-value]").forEach((btn) => {
      const mv = btn.getAttribute("data-mode-value") || "";
      btn.classList.toggle("active", mv === effectiveMode);
      btn.disabled = locked && mv !== state.lockedMode;
    });
    if ($("modeLockSwitch")) $("modeLockSwitch").checked = locked;
    if ($("modeLockStatus")) {
      $("modeLockStatus").textContent = lockLabel;
      $("modeLockStatus").style.color = locked ? "#2563eb" : "#16a34a";
    }
    const shell = document.querySelector(".ops-topology-app");
    if (shell) {
      shell.classList.remove("canvas-mode-edit", "canvas-mode-run", "canvas-mode-test");
      shell.classList.add("canvas-mode-" + effectiveMode);
    }
    refreshRightPanelMode();
    refreshLogDemoForChrome();
    syncLayoutSpacingControls();
    syncToolButtonsForMode();
    if (effectiveMode === "test") {
      seedTestModeRuntimeDemo();
      syncTestScopeUI();
    } else {
      setTestPathHint("");
      clearTestHighlight();
      const shell = document.querySelector(".ops-topology-app");
      if (shell) shell.classList.remove("test-scope-segment");
      const segFields = $("testSegmentFields");
      if (segFields) segFields.classList.add("is-hidden");
    }
    if (effectiveMode === "edit") {
      clearFlowViz(true, "applyModeUI-edit-mode");
    } else {
      syncLiveFlowVisualsForMode();
    }
    redrawGraph();

    const lock = effectiveMode !== "edit";
    ["insNodeName", "insNodeRole", "insNodeBizStatus", "insNodeKind", "insNodeColorPicker", "insNodeOwner", "insNodePrimaryAgent", "insNodePrimaryAgentBasic", "insNodeDesc", "insNodeTags", "insNodeRemotePort", "insNodeRemotePortBasic", "insNodeEndpoints", "insNodeEndpointsBasic", "insNodeNotes"]
      .forEach((id) => { const el = $(id); if (el) el.disabled = lock; });
    document.querySelectorAll(".topology-color-preset").forEach((btn) => { btn.disabled = lock; });
    ["btnDeleteNode", "btnSaveNode", "btnSaveNodeTools"]
      .forEach((id) => { const el = $(id); if (el) el.disabled = lock; });
  }

  // 检测 session 过期
  function checkAuthExpired(resp) {
    if (resp && (resp.error_code === 'OPS_AUTH_REQUIRED' || resp.error === 'auth_redirect')) {
      window.location.href = '/login';
      return true;
    }
    return false;
  }

  async function loadAll() {
    setTopologyHint("正在加载拓扑核心数据...", "");
    const [topo, presets] = await Promise.all([
      OpsApi.loadTopology(currentScope()),
      OpsApi.loadPresets(),
    ]);
    if (checkAuthExpired(topo) || checkAuthExpired(presets)) return;
    if (!topo || topo.ok === false) {
      setTopologyHint((topo && (topo.message || topo.error)) || "拓扑核心数据加载失败", "error");
      return;
    }

    state.topology = topo.topology || { nodes: [], edges: [], meta: { viewport: { x: 0, y: 0, zoom: 1 } } };
    if (!state.topology.meta || typeof state.topology.meta !== "object") state.topology.meta = {};
    syncLayoutSpacingFromTopology();
    state.topologyRegistry = topo.registry || null;
    state.topologies = Array.isArray(topo.topologies) ? topo.topologies : [];
    if (topo.topology_id) state.topologyId = String(topo.topology_id || state.topologyId);
    if (topo.env_key) state.envKey = String(topo.env_key || state.envKey);
    state.nodesRaw = (state.topology.nodes || []).map((n) => ({
      id: n.id,
      name: n.name,
      role: n.role,
      kind: n.kind,
      desc: n.desc,
      bizStatus: n.bizStatus,
      owner: n.owner,
      tags: n.tags,
    }));
    state.presets = (presets && presets.presets) || [];
    if (!state.activePresetId && state.presets.length) state.activePresetId = state.presets[0].preset_id;

    normalizeTopology();
    applyWorkbenchModeFromMeta(state.topology.meta);
    const preserveLayout = shouldPreserveTopologyLayoutOnLoad();
    if (preserveLayout) {
      if (state.topology.meta.layout_locked == null) state.topology.meta.layout_locked = true;
    } else {
      applyDesignStructuredLayout();
      layoutStructuredGraph();
    }
    renderScene();
    redrawGraph();
    scheduleFitGraphToViewport();
    state.history.past = [snapshotTopology()];
    state.history.future = [];
    updateHistoryButtons();
    renderScopeSelectors();
    renderPresets();
    renderRuntimeNodeList();
    fillTestNodeOptions();
    applyModeUI();
    renderTopologyManagerList();
    syncLayoutSpacingControls();
    syncQueryString();
    seedDesignDemoLogs();
    const initialNodeId = preferredNodeId();
    if (initialNodeId) openNodeEditor(initialNodeId);
    else closeNodeEditor();
    setTopologyHint("拓扑已可操作，正在后台同步 Agent、绑定与总览数据...", "loading");

    await loadAuxiliaryData();
  }

  function touchRuntimeStatusUi() {
    const modeChanged = inferWorkbenchModeFromRuntime();
    syncLiveFlowVisualsForMode();
    redrawGraph();
    renderRuntimeNodeList();
    fillTestNodeOptions();
    applyModeUI();
    if (modeChanged) saveModeState();
    const currentNodeId = String((($("insNodeId") || {}).value || "")).trim();
    const curNode = currentNodeId ? getNode(currentNodeId) : null;
    if (curNode) {
      updateInspectorHeader(curNode);
      openNodeEditor(currentNodeId);
    }
  }

  function applyBindingsPayload(bindings) {
    if (!bindings || bindings.ok === false) return false;
    state.nodeBindings = Object.assign({}, state.nodeBindings, bindings.bindings || {});
    state.serviceBindings = Object.assign({}, state.serviceBindings, bindings.service_bindings || {});
    state.bindingsHydrated = true;
    return true;
  }

  async function loadAuxiliaryData() {
    const warns = [];
    const scope = currentScope();

    const applyNodes = (nodes) => {
      if (checkAuthExpired(nodes)) return;
      if (nodes && nodes.ok !== false && Array.isArray(nodes.nodes)) {
        state.nodesRaw = (state.topology.nodes || []).length
          ? (state.topology.nodes || []).map((n) => ({
            id: n.id,
            name: n.name || n.id,
            role: n.role,
            kind: n.kind,
            description: n.desc,
            desc: n.desc,
            biz_status: n.bizStatus,
            owner: n.owner,
            tags: n.tags,
          })).concat((nodes.nodes || []).filter((raw) => !(state.topology.nodes || []).some((n) => String(n.id) === String(raw.id))))
          : nodes.nodes;
        normalizeTopology();
        if (!shouldPreserveTopologyLayoutOnLoad()) layoutStructuredGraph();
      } else {
        warns.push("节点清单");
      }
    };

    const applyOverview = (overview) => {
      if (checkAuthExpired(overview)) return;
      if (overview && overview.ok !== false) state.overviewNodes = overview.nodes || [];
      else warns.push("总览");
    };

    const applyBlueprints = (blueprints) => {
      if (checkAuthExpired(blueprints)) return;
      if (blueprints && blueprints.ok !== false && Array.isArray(blueprints.blueprints)) {
        state.blueprints = blueprints.blueprints;
        renderBlueprintSelectors();
        const bpSel = $("flowBlueprintSelect");
        if (bpSel) {
          bpSel.innerHTML = '<option value="">流程模板</option>' + state.blueprints.map((b) => '<option value="' + esc(b.blueprint_id) + '">' + esc(b.name) + '</option>').join("");
        }
      } else {
        warns.push("流程模板");
      }
    };

    const applyServices = (servicesResp) => {
      if (checkAuthExpired(servicesResp)) return;
      if (servicesResp && servicesResp.ok !== false) state.services = servicesResp.services || servicesResp.items || [];
      else warns.push("服务实例");
    };

    const applyAgents = (agents, label) => {
      if (checkAuthExpired(agents)) return false;
      if (agents && agents.ok !== false) {
        mergeAgentPayload(agents);
        return true;
      }
      if (label) warns.push(label);
      return false;
    };

    // 关键路径：绑定 + 本机实时探活（并行），不等待 overview 等慢接口
    const critical = await Promise.allSettled([
      OpsApi.loadNodeBindings(scope),
      OpsApi.agents(state.projectId, agentsRequestOptions(true)),
    ]);
    const [bindingsRes, agentsRes] = critical.map((r) => r.status === "fulfilled" ? r.value : { ok: false, error: String(r.reason || "request_failed") });
    if (!applyBindingsPayload(bindingsRes)) warns.push("绑定");
    else touchRuntimeStatusUi();
    if (!applyAgents(agentsRes, "Agent")) {
      // keep bindings visible even when agents fails
    } else {
      touchRuntimeStatusUi();
    }

    setTopologyHint(warns.length ? ("部分状态数据加载失败: " + warns.join("、") + "，画布仍可操作") : "", warns.length ? "warn" : "");

    Promise.allSettled([
      OpsApi.loadNodes(),
      OpsApi.loadOverview(state.projectId),
      OpsApi.loadTopologyBlueprints(),
      OpsApi.listServices(state.projectId),
    ]).then((settled) => {
      const [nodes, overview, blueprints, servicesResp] = settled.map((r) => r.status === "fulfilled" ? r.value : { ok: false, error: String(r.reason || "request_failed") });
      applyNodes(nodes);
      applyOverview(overview);
      applyBlueprints(blueprints);
      applyServices(servicesResp);
      renderScopeSelectors();
      renderTopologyManagerList();
      touchRuntimeStatusUi();
      if (warns.length) {
        setTopologyHint("部分辅助数据加载失败: " + warns.join("、") + "，画布仍可操作", "warn");
      }
    });
  }

  async function pickBlueprintId() {
    let bid = String((($("flowBlueprintSelect") || {}).value || "")).trim();
    if (bid) return bid;
    const list = state.blueprints || [];
    if (!list.length) return "";
    if (list.length === 1) return String(list[0].blueprint_id || "");
    const lines = list.map((b, i) => (i + 1) + ". " + String(b.name || b.blueprint_id || "-"));
    const raw = window.prompt("请选择要应用的蓝图（输入序号）:\n" + lines.join("\n"), "1");
    if (raw == null) return "";
    const idx = Number(String(raw).trim()) - 1;
    if (!Number.isFinite(idx) || idx < 0 || idx >= list.length) return "";
    return String(list[idx].blueprint_id || "");
  }

  async function showRuntimeDetails() {
    if (!state.runtimeRunId) {
      toast("当前没有进行中的运行任务", "warn");
      appendJsonDetail("运行详情", { ok: false, message: "no_active_run", mode: state.mode, topology_id: state.topologyId });
      return;
    }
    const d = await OpsApi.runtimeFlowStatus(state.runtimeRunId);
    const box = $("nodeLogModalBody");
    const modal = $("nodeLogModal");
    if (box) box.textContent = JSON.stringify(d || { ok: false, error: "empty_response" }, null, 2);
    if (modal) modal.classList.remove("hidden");
    setModalOpen(true);
  }

  async function applyBlueprintFromToolbar() {
    const bid = await pickBlueprintId();
    if (!bid) { toast("请选择蓝图模板", "warn"); return; }
    const chosen = state.blueprints.find((x) => String(x.blueprint_id) === bid);
    const confirmText = "应用蓝图后会替换当前画布中的全部节点与连线。\n\n蓝图：" + (chosen ? chosen.name : bid) + "\n\n确认继续？";
    if (!window.confirm(confirmText)) return;
    const d = await OpsApi.applyTopologyBlueprint(Object.assign(currentScope(), { blueprint_id: bid, replace_existing: true }));
    if (!d.ok) { toast(d.message || d.error || "应用蓝图失败", "error"); return; }
    toast("蓝图已应用", "ok");
    await loadAll();
  }

  function handleToolButtonClick(btn) {
    if (!btn || !btn.id) return;
    document.querySelectorAll(".topology-tool-btn").forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    switch (btn.id) {
      case "toolSelect":
        break;
      case "toolConnect":
        if (!isEditMode()) { toast("仅编辑模式可重新布局", "warn"); return; }
        if (!state.topology.meta || typeof state.topology.meta !== "object") state.topology.meta = {};
        state.topology.meta.layout_locked = false;
        layoutStructuredGraph({ force: true });
        redrawGraph();
        toast("已按结构化规则重新排布", "ok");
        break;
      case "toolUndoInline":
        if (!isEditMode()) { toast("仅编辑模式可撤销", "warn"); return; }
        undoTopology();
        break;
      case "toolRedoInline":
        if (!isEditMode()) { toast("仅编辑模式可重做", "warn"); return; }
        redoTopology();
        break;
      case "toolResetInline":
        fitGraphToViewport();
        renderScene();
        toast("视图已适应画布", "ok");
        break;
      case "toolSaveInline":
        if (isTestMode()) { toast("测试模式禁止保存拓扑", "warn"); return; }
        if ($("toolSave")) $("toolSave").onclick && $("toolSave").onclick();
        break;
      case "btnApplyBlueprint":
        if (!isEditMode()) { toast("仅编辑模式可应用蓝图", "warn"); return; }
        applyBlueprintFromToolbar();
        break;
      case "btnAutoBindAgents":
        if (!isEditMode()) { toast("仅编辑模式可自动绑定", "warn"); return; }
        autoBindAgents();
        break;
      default:
        break;
    }
  }

