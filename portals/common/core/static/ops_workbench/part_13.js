  async function saveNode() {
    if (!isEditMode()) { toast("仅编辑模式可保存节点属性", "warn"); return; }
    syncInspectorPortFieldsFromBasic();
    syncInspectorAgentMainFromBasic();
    const id = selectedNodeId();
    if (!id) { toast("请先选中要保存的节点", "warn"); return; }
    const n = getNode(id);
    if (!n) { toast("节点不存在或已被删除", "error"); return; }
    const layoutPos = nodeCoords(n);
    n.name = String((($("insNodeName") || {}).value || n.name || n.id || "")).trim() || n.id;
    n.role = ($("insNodeRole") && $("insNodeRole").value) || n.role;
    n.bizStatus = ($("insNodeBizStatus") && $("insNodeBizStatus").value) || n.bizStatus;
    const kindDisplay = String(($("insNodeKindDisplay") || {}).value || "").trim();
    n.kind = kindDisplay === "game" ? "game" : inferKind(n.role, ($("insNodeKind") && $("insNodeKind").value) || n.kind);
    const card = $("nodeInspectorCard");
    const nodesLayout = card && card.getAttribute("data-inspector-layout") === "nodes";
    if (nodesLayout) {
      n.group = String(($("insNodeOwner") || {}).value || n.group || "");
      if ($("insNodeOwnerDisplay")) n.owner = String($("insNodeOwnerDisplay").value || n.owner || "运维团队");
    }
    n.desc = ($("insNodeDesc") && $("insNodeDesc").value) || n.desc;
    if ($("insNodeNotes")) n.notes = String($("insNodeNotes").value || "").trim();
    n.tags = String(($("insNodeTags") || {}).value || "").split(",").map((x) => x.trim()).filter(Boolean);
    const colorRaw = String(($("insNodeColor") && $("insNodeColor").value) || "").trim();
    if (colorRaw && !/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(colorRaw)) {
      toast("颜色格式无效，请使用 #RGB 或 #RRGGBB", "warn");
      return;
    }
    n.ui = n.ui || {};
    n.ui.color = normalizeHexColor(colorRaw || n.ui.color, n.ui.color || "#0f172a");
    n.ui.remote = n.ui.remote || {};
    const remotePort = Number(($("insNodeRemotePort") && $("insNodeRemotePort").value) || ($("insNodeDaemonPort") && $("insNodeDaemonPort").value) || 0);
    n.ui.remote.port = (Number.isFinite(remotePort) && remotePort > 0) ? remotePort : 0;
    if (isInfraDaemonNode(n)) {
      n.daemon_port = (Number.isFinite(remotePort) && remotePort > 0) ? remotePort : 0;
      if ($("insNodeDaemonStart")) n.daemon_start_cmd = String($("insNodeDaemonStart").value || "").trim();
      if ($("insNodeDaemonStop")) n.daemon_stop_cmd = String($("insNodeDaemonStop").value || "").trim();
    }
    const epText = String(($("insNodeEndpoints") && $("insNodeEndpoints").value) || "").trim();
    n.ui.network = { endpoints: epText ? epText.split(",").map((x) => x.trim()).filter(Boolean) : [] };
    n.ui.ports = normalizePorts(n.kind, n.ui.ports);
    n.ui.x = layoutPos.x;
    n.ui.y = layoutPos.y;

    const patch = {
      name: n.name,
      role: n.role,
      kind: n.kind,
      desc: n.desc,
      bizStatus: n.bizStatus,
      owner: n.owner,
      x: layoutPos.x,
      y: layoutPos.y,
      ui: Object.assign({}, n.ui, { x: layoutPos.x, y: layoutPos.y }),
      tags: n.tags,
    };
    if (isInfraDaemonNode(n)) {
      patch.daemon_port = n.daemon_port || n.ui.remote.port || 0;
      patch.daemon_start_cmd = n.daemon_start_cmd || "";
      patch.daemon_stop_cmd = n.daemon_stop_cmd || "";
    }
    const nodeRes = await OpsApi.updateNode(Object.assign(currentScope(), { node_id: id, patch }));
    if (!nodeRes || nodeRes.ok === false) {
      toast((nodeRes && (nodeRes.message || nodeRes.error)) || "保存节点失败", "error");
      appendJsonDetail("节点保存失败 " + id, nodeRes || {});
      return;
    }
    if (nodeRes.topology && nodeRes.topology.nodes) {
      mergeServerNode(id, nodeRes.topology.nodes);
    } else {
      const hit = getNode(id);
      if (hit) {
        hit.name = n.name;
        hit.role = n.role;
        hit.kind = n.kind;
        hit.desc = n.desc;
        hit.bizStatus = n.bizStatus;
        hit.owner = n.owner;
        hit.tags = n.tags;
        hit.ui = patch.ui;
      }
    }

    const aid = String((($("insNodePrimaryAgentBasic") && $("insNodePrimaryAgentBasic").value) || ($("insNodePrimaryAgent") && $("insNodePrimaryAgent").value) || ""));
    const serviceId = String(($("insNodeService") || {}).value || "").trim();
    let bindRes;
    if (serviceId && OpsApi.bindNodeService) {
      bindRes = await OpsApi.bindNodeService(Object.assign(currentScope(), { node_id: id, agent_id: aid, service_id: serviceId }));
    } else {
      bindRes = await OpsApi.bindNodeAgent(Object.assign(currentScope(), { node_id: id, agent_id: aid }));
    }
    if (!bindRes || bindRes.ok === false) {
      toast((bindRes && (bindRes.message || bindRes.error)) || "绑定失败", "error");
      appendJsonDetail("节点绑定失败 " + id, bindRes || {});
      return;
    }

    state.nodeBindings = bindRes.bindings || state.nodeBindings;
    state.serviceBindings = bindRes.service_bindings || state.serviceBindings;
    pushHistory();
    toast("节点与绑定信息已保存", "ok");
    logMode("节点保存成功: " + id);
    logDeployment("节点 " + id + " 属性与绑定已更新", "info");
    openNodeEditor(id);
    redrawGraph();
    renderRuntimeNodeList();
  }

  async function startRemoteForNode(nodeId, launchVisibleConsole) {
    const nid = String(nodeId || "").trim();
    if (!nid) return { ok: false, message: "missing_node_id" };
    const n = getNode(nid);
    if (!n) return { ok: false, message: "node_not_found" };
    const aid = String((state.nodeBindings || {})[nid] || "");
    if (!aid) return { ok: false, message: "节点未绑定 Agent", error_code: "OPS_AGENT_NOT_BOUND" };
    const ag = (state.agents || []).find((x) => String((x || {}).agent_id || "") === aid) || null;
    if (!ag) return { ok: false, message: "绑定的 Agent 不存在", error_code: "OPS_AGENT_NOT_REGISTERED" };
    const probe = String(ag.probe_status || "").toUpperCase();
    if (probe !== "PASS") return { ok: false, message: "Agent 连通性检测未通过", error_code: "OPS_AGENT_PROBE_REQUIRED" };
    const visible = (typeof launchVisibleConsole === "boolean")
      ? launchVisibleConsole
      : !!($("insNodeVisibleConsole") ? $("insNodeVisibleConsole").checked : true);
    const resp = await OpsApi.startRemoteNode(Object.assign(currentScope(), {
      node_id: nid,
      service_id: String((n.ui && n.ui.remote && n.ui.remote.service_id) || n.service_id || n.id || ""),
      launch_visible_console: visible,
    }));
    if (resp && resp.ok !== false) logDeployment("节点 " + nid + " 远端启动已提交 job_id=" + (resp.job_id || "-"), "info");
    return resp || { ok: false, message: "remote_start_no_response" };
  }

  async function precheckAndStartRemoteForNodes(nodeIds) {
    await refreshAgentsIfNeeded(true);
    const uniq = Array.from(new Set((nodeIds || []).map((x) => String(x || "").trim()).filter(Boolean)));
    const failures = [];
    for (const nid of uniq) {
      const r = await startRemoteForNode(nid, true);
      if (!r || r.ok === false) {
        failures.push({ node_id: nid, error_code: (r && r.error_code) || "OPS_REMOTE_START_FAILED", message: (r && (r.message || r.error)) || "远端启动失败" });
        logMode("远端启动失败 " + nid + ": " + ((r && (r.message || r.error)) || "未知错误"), "error");
        appendJsonDetail("远端启动失败 " + nid, r || {});
      } else {
        logMode("远端启动已提交 " + nid + " job_id=" + (r.job_id || "-") + " trace_id=" + (r.trace_id || "-"));
      }
    }
    return { ok: failures.length === 0, failures };
  }

  async function deleteNode() {
    const nodeId = String(($("insNodeId").value || "")).trim();
    if (!nodeId) return;
    if (!isEditMode()) { toast("仅编辑模式可删除节点", "warn"); return; }
    if (!window.confirm("删除该节点及其所有关联连线？")) return;
    const d = await OpsApi.deleteNode(Object.assign(currentScope(), { node_id: nodeId }));
    if (!d.ok) { toast(d.message || d.error || "删除节点失败", "error"); logMode("删除节点失败: " + (d.message || d.error || "未知错误"), "error"); return; }
    state.topology = d.topology || state.topology;
    state.nodeBindings = d.bindings || state.nodeBindings;
    state.selection.nodes.clear();
    state.selection.edgeId = "";
    closeNodeEditor();
    redrawGraph();
    renderRuntimeNodeList();
    toast("节点已删除", "ok");
    logMode("删除节点成功: " + nodeId);
  }

  function deleteSelectedNode() {
    const ids = Array.from(state.selection.nodes || []);
    if (!ids.length) return;
    $("insNodeId").value = ids[0];
    deleteNode();
  }

  async function autoBindAgents() {
    const d = await OpsApi.autoBindAgents(currentScope());
    if (!d || d.ok === false) {
      toast((d && (d.message || d.error)) || "自动绑定失败", "error");
      return;
    }
    state.nodeBindings = d.bindings || state.nodeBindings;
    drawNodes();
    renderRuntimeNodeList();
    toast(`自动绑定完成：成功 ${d.bound_count || 0}，跳过 ${d.skipped_count || 0}`, "ok");
    logMode(`自动绑定完成：成功 ${d.bound_count || 0}，跳过 ${d.skipped_count || 0}`);
    logDeployment("自动绑定 Agent：成功 " + (d.bound_count || 0) + "，跳过 " + (d.skipped_count || 0), "info");
  }

  function deleteSelectedPort() {
    const id = $("insNodeId").value;
    const n = getNode(id);
    if (!n || !state.selectedPort) { toast("请先选择要删除的针脚", "warn"); return; }
    if (!isEditMode()) { toast("仅编辑模式可删除针脚", "warn"); return; }
    const side = state.selectedPort.side;
    const pid = String(state.selectedPort.id || "");
    const ports = ((n.ui && n.ui.ports && n.ui.ports[side]) || []);
    if (!ports.length) return;
    if (ports.length <= 1) { toast("该侧至少保留一个针脚", "warn"); return; }
    if (countLinks(n.id, side, pid) > 0) { toast("该针脚仍有连线，请先删连线", "warn"); return; }
    const next = ports.filter((p) => String(p.id) !== pid);
    n.ui.ports[side] = next;
    state.selectedPort = null;
    refreshPortSummary(n);
    renderPortLists(n);
    redrawGraph();
    logMode("删除针脚: " + n.id + ":" + side + ":" + pid);
  }

  async function runFullLifecycle(start) {
    const op = start ? "start" : "stop";
    state.runtimeRequestedOp = op;
    state.runtimePartialRecovery = false;
    state.runtimeEdgesLogged = false;
    dbg("runFullLifecycle-click", { op, mode: state.mode, lockedMode: state.lockedMode || "", currentRunId: state.runtimeRunId || "" });
    stopRuntimePolling();
    if (!start) {
      state.runtimeStopping = true;
      clearFlowViz(true, "runFullLifecycle-stop-before-control");
    }
    state.runtimeSteady = false;
    state.runtimePartialRecovery = false;
    state.runtimeLastStatus = "";
    state.runtimeLogSeen = new Set();
    state.runtimeProgressSig = "";
    state.runtimeStarting = !!start;
    logMode((start ? "开始" : "开始") + (start ? "一键启动" : "一键停止") + "全流程");
    if (start && !isRuntimeTopologyProject()) {
      const startupNodes = (state.topology.nodes || []).map((n) => n.id);
      const pre = await precheckAndStartRemoteForNodes(startupNodes);
      if (!pre.ok) {
        toast("前置校验失败：存在未通过联通或远端启动失败节点", "error");
        appendJsonDetail("运行前置校验失败节点清单", pre.failures);
        return;
      }
    } else if (start) {
      logMode("Runtime 拓扑：跳过 Agent 前置校验，改走集群级直连启动");
    }
    const d = await OpsApi.runtimeFlowControl(Object.assign(currentScope(), { op }));
    if (!d || d.ok === false) {
      if (!start) state.runtimeStopping = false;
      if (start) state.runtimeStarting = false;
      if (start) {
        clearFlowViz(true, "runFullLifecycle-start-failed");
        redrawGraph();
      }
      toast((d && d.message) || "运行请求失败", "error");
      logMode("运行请求失败: " + ((d && (d.message || d.error)) || "未知错误"), "error");
      if (d && d.logs) appendRuntimeLogs(d.logs);
      if (d && d.status) {
        state.runtimeLastStatus = String(d.status).toLowerCase();
        updateRuntimeSummary(d);
      }
      return;
    }
    state.runtimeRunId = String(d.run_id || "");
    saveRuntimeState();
    dbg("runtime-flow-control-return", { op, runId: state.runtimeRunId, items: (d.items || []).length, status: d.status || "" });
    appendRuntimeLogs(d.logs || []);
    const total = (d.items || []).length;
    logMode("任务已入队，run_id=" + state.runtimeRunId + "，节点任务数=" + total);
    logDeployment((start ? "一键启动" : "一键停止") + "全流程已入队 run_id=" + state.runtimeRunId, "info");
    toast((start ? "启动" : "停止") + "任务已入队，开始实时跟踪", "ok");
    await pollRuntimeRun(state.runtimeRunId);
    const terminal = String(state.runtimeLastStatus || String(d.status || "")).toLowerCase();
    if (state.runtimeRunId && !state.runtimePollTimer && !state.runtimeAwaitLive && terminal !== "success" && terminal !== "failed") {
      state.runtimePollTimer = setInterval(() => { pollRuntimeRun(state.runtimeRunId); }, 1200);
    }
  }

