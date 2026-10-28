  function renderMonitorPanel(nodeId) {
    const empty = $("insNodeMonitorEmpty");
    const body = $("insNodeMonitorBody");
    if (!empty || !body) return;
    const nid = String(nodeId || "");
    if (!nid) {
      empty.style.display = "";
      body.innerHTML = "";
      return;
    }
    const flowSt = String((state.flowViz.statusByNode || {})[nid] || "").toUpperCase();
    const metrics = [];
    Object.keys(state.flowViz.metricsByEdge || {}).forEach((edgeId) => {
      const edge = (state.topology.edges || []).find((e) => String(e.id) === String(edgeId));
      if (!edge) return;
      if (String(edge.from) !== nid && String(edge.to) !== nid) return;
      const mm = state.flowViz.metricsByEdge[edgeId];
      if (mm) metrics.push({ edgeId, tps: mm.tps, latency: mm.latency });
    });
    if (!flowSt && !metrics.length) {
      empty.style.display = "";
      body.innerHTML = "";
      return;
    }
    empty.style.display = "none";
    body.innerHTML = '<div class="topology-monitor-grid">'
      + '<div><span>运行态</span><b>' + esc(flowSt || "IDLE") + '</b></div>'
      + metrics.map((m) => '<div><span>' + esc(m.edgeId) + '</span><b>TPS ' + esc(m.tps) + ' · ' + esc(m.latency) + 'ms</b></div>').join("")
      + '</div>';
  }

  function syncColorSwatch(value) {
    setInspectorNodeColor(value, { preview: false });
  }

  function colorPresetOptions() {
    const seen = new Set();
    const out = [];
    Object.keys(ROLE_COLOR).forEach((key) => {
      const color = String((ROLE_COLOR[key] || {}).border || "").trim();
      if (!color || seen.has(color.toLowerCase())) return;
      seen.add(color.toLowerCase());
      out.push({ key, color, label: ROLE_LABELS[key] || key });
    });
    return out;
  }

  function setInspectorNodeColor(hex, options) {
    const opts = options || {};
    const c = normalizeHexColor(hex, roleColor("business"));
    const hidden = $("insNodeColor");
    const picker = $("insNodeColorPicker");
    if (hidden) hidden.value = c;
    if (picker) picker.value = c;
    document.querySelectorAll(".topology-color-preset").forEach((btn) => {
      const btnColor = normalizeHexColor(btn.getAttribute("data-color") || "", "");
      btn.classList.toggle("is-active", btnColor === c);
      btn.setAttribute("aria-selected", btnColor === c ? "true" : "false");
    });
    if (opts.preview !== false) previewSelectedNodeColor(c);
  }

  function previewSelectedNodeColor(hex) {
    const id = selectedNodeId();
    if (!id || !isEditMode()) return;
    const n = getNode(id);
    if (!n) return;
    n.ui = n.ui || {};
    n.ui.color = hex;
    redrawGraph();
  }

  function renderColorPresets() {
    const box = $("insNodeColorPresets");
    if (!box) return;
    box.innerHTML = colorPresetOptions().map((item) => (
      '<button type="button" class="topology-color-preset" data-color="' + esc(item.color) + '" title="' + esc(item.label) + '" aria-label="' + esc(item.label) + '" style="background:' + esc(item.color) + ';"></button>'
    )).join("");
    box.querySelectorAll(".topology-color-preset").forEach((btn) => {
      btn.onclick = () => setInspectorNodeColor(btn.getAttribute("data-color") || "");
    });
  }

  function normalizeHexColor(raw, fallback) {
    const s = String(raw || "").trim();
    if (/^#[0-9a-fA-F]{6}$/.test(s)) return s.toLowerCase();
    if (/^#[0-9a-fA-F]{3}$/.test(s)) {
      return ("#" + s[1] + s[1] + s[2] + s[2] + s[3] + s[3]).toLowerCase();
    }
    return String(fallback || "#0f172a");
  }

  function renderTagChips(tags) {
    const box = $("insNodeTagChips");
    const hidden = $("insNodeTags");
    const list = Array.isArray(tags) ? tags : String(tags || "").split(",").map((x) => x.trim()).filter(Boolean);
    if (hidden) hidden.value = list.join(",");
    if (!box) return;
    if (!list.length) {
      box.innerHTML = '<span class="topology-tag-empty">暂无标签</span>';
      return;
    }
    box.innerHTML = list.map((tag) => (
      '<span class="topology-tag-chip" data-tag="' + esc(tag) + '">' + esc(tag)
      + '<button type="button" class="topology-tag-remove" data-tag="' + esc(tag) + '" aria-label="移除">×</button></span>'
    )).join("");
    box.querySelectorAll(".topology-tag-remove").forEach((btn) => {
      btn.onclick = () => {
        const t = btn.getAttribute("data-tag");
        const next = list.filter((x) => x !== t);
        renderTagChips(next);
      };
    });
  }

  function fillAgentSelect(nodeId) {
    const sel = $("insNodePrimaryAgent");
    const basicSel = $("insNodePrimaryAgentBasic");
    const agMeta = $("insNodeAgentMeta");
    const agents = effectiveAgents();
    const fillOptions = (target) => {
      if (!target) return;
      target.innerHTML = '<option value="">未绑定</option>';
      agents.forEach((a) => {
        const op = document.createElement("option");
        op.value = String(a.agent_id || "");
        op.textContent = String(a.display_name || a.agent_id || "-");
        target.appendChild(op);
      });
    };
    fillOptions(sel);
    fillOptions(basicSel);
    let current = String((state.nodeBindings || {})[nodeId] || "");
    if (!current && nodeId === "game-01" && isDesignReferenceTopology()) current = "agent-01";
    if (sel) sel.value = current;
    if (basicSel) basicSel.value = current;
    const hit = agents.find((a) => String(a.agent_id || "") === current);
    const metaText = (x) => {
      if (!x) return "未绑定";
      const h = agentHealthLabel(x);
      return h.text + " / " + (x.device_id || "-") + " / " + (x.host_name || "-") + ":" + (x.port || "-") + " / " + (x.last_seen || "-");
    };
    if (agMeta) agMeta.value = metaText(hit);
    fillServiceSelect(nodeId, current);
    updateInspectorDeployFields(nodeId);
    const onAgentChange = (source) => {
      const aid = String((source && source.value) || "");
      if (sel && source !== sel) sel.value = aid;
      if (basicSel && source !== basicSel) basicSel.value = aid;
      const x = agents.find((a) => String(a.agent_id || "") === aid);
      if (agMeta) agMeta.value = metaText(x);
      fillServiceSelect(nodeId, aid);
      updateInspectorDeployFields(nodeId);
    };
    if (sel) sel.onchange = () => onAgentChange(sel);
    if (basicSel) basicSel.onchange = () => onAgentChange(basicSel);
    const svcSel = $("insNodeService");
    if (svcSel) {
      svcSel.onchange = () => updateInspectorDeployFields(nodeId);
    }
  }

  function updateInspectorHeader(node) {
    const title = $("inspectorTitle");
    const idLine = $("inspectorNodeIdLine");
    const subline = $("inspectorSubline");
    const badge = $("inspectorNodeBadge");
    const pill = $("inspectorStatusPill");
    if (!node) {
      setInspectorEmpty(true);
      if (title) title.textContent = "节点属性";
      if (idLine) idLine.textContent = "未选中节点";
      if (subline) {
        subline.textContent = "点击画布节点查看详情";
        subline.style.display = "";
      }
      if (badge) {
        badge.textContent = "拓";
        badge.style.color = "#2563eb";
        badge.style.borderColor = "#dbeafe";
        badge.style.background = "linear-gradient(180deg,#eff6ff,#f8fbff)";
      }
      if (pill) {
        pill.textContent = "未选中";
        pill.className = "state-pill state-info";
      }
      return;
    }
    setInspectorEmpty(false);
    if (title) title.textContent = nodeDisplayTitle(node);
    if (idLine) idLine.textContent = "ID: " + String(node.id || "-");
    if (subline) {
      subline.textContent = roleLabel(node.role) + " · " + nodeSecondaryText(node);
      subline.style.display = "";
    }
    if (badge) {
      const iconRole = resolveIconRole(node);
      const palette = nodePalette(node);
      badge.innerHTML = roleBadge(node);
      badge.style.setProperty("--ico-accent", palette.border);
      badge.style.color = palette.border;
      badge.style.borderColor = "color-mix(in srgb, " + palette.border + " 28%, white)";
      badge.style.background = "color-mix(in srgb, " + palette.border + " 12%, white)";
    }
    if (pill) {
      const ag = resolveAgentForNode(node);
      const aid = String((state.nodeBindings || {})[node.id] || (ag && ag.agent_id) || "");
      const rs = nodeRuntimeStatus(node, ag, aid);
      pill.textContent = rs.text;
      pill.className = "state-pill " + (rs.cls === "ok" ? "state-ok" : rs.cls === "err" ? "state-err" : "state-info");
    }
  }

  function isInfraDaemonNode(node) {
    if (!node) return false;
    const profile = String(node.daemon_profile || "").trim().toLowerCase();
    if (profile === "external_daemon") return true;
    const role = String(node.role || "").toLowerCase();
    return ["cache", "database", "db", "mq", "scheduler", "pressure"].includes(role);
  }

  function toggleDaemonInspector(node) {
    const box = $("insDaemonSection");
    if (!box) return;
    const show = isInfraDaemonNode(node);
    box.classList.toggle("is-hidden", !show);
    box.setAttribute("aria-hidden", show ? "false" : "true");
  }

  function openNodeEditor(nodeId) {
    const n = getNode(nodeId);
    if (!n) return;
    state.selection.nodes = new Set([nodeId]);
    state.selection.edgeId = "";
    const card = $("nodeInspectorCard");
    if (card) card.setAttribute("data-selected-node-id", String(nodeId));
    if ($("insNodeName")) $("insNodeName").value = String(n.name || n.id || "");
    const insId = $("insNodeId");
    if (insId) insId.value = n.id;
    ensureRoleOption(n.role);
    const insRole = $("insNodeRole");
    if (insRole) insRole.value = n.role;
    if ($("insNodeBizStatus")) $("insNodeBizStatus").value = n.bizStatus;
    if ($("insNodeKind")) $("insNodeKind").value = n.kind || inferKind(n.role, n.kind);
    if ($("insNodeKindDisplay")) $("insNodeKindDisplay").value = semanticTypeLabel(n);
    if ($("insNodeOwner")) $("insNodeOwner").value = n.group || (n.id === "game-01" ? "游戏服务" : roleLabel(n.role));
    if ($("insNodeDesc")) $("insNodeDesc").value = String(n.desc || "");
    if ($("insNodeNotes")) $("insNodeNotes").value = String(n.notes || n.ui?.notes || "");
    if ($("insNodeColor")) setInspectorNodeColor(nodeCustomColor(n) || roleColor(n.role) || "#722ed1", { preview: false });
    $("insNodeTags").value = (n.tags || []).join(",");
    renderTagChips(n.tags || []);
    const remotePort = String(n.daemon_port || (((n.ui || {}).remote || {}).port || "") || (n.id === "game-01" ? "9501" : ""));
    $("insNodeRemotePort").value = remotePort;
    if ($("insNodeRemotePortBasic")) $("insNodeRemotePortBasic").value = remotePort;
    if ($("insNodeDaemonPort")) $("insNodeDaemonPort").value = String(n.daemon_port || remotePort || "");
    if ($("insNodeDaemonStart")) $("insNodeDaemonStart").value = String(n.daemon_start_cmd || "");
    if ($("insNodeDaemonStop")) $("insNodeDaemonStop").value = String(n.daemon_stop_cmd || "");
    toggleDaemonInspector(n);
    const eps = (((n.ui || {}).network || {}).endpoints || []);
    const epText = Array.isArray(eps) && eps.length ? eps.join(",") : (n.id === "game-01" ? "10.0.1.15:9501" : "");
    $("insNodeEndpoints").value = epText;
    syncInspectorPortFieldsFromMain();
    state.selectedPort = null;
    fillAgentSelect(nodeId);
    renderNodeConnections(nodeId);
    renderMonitorPanel(nodeId);
    refreshInspectorLayout(state.activeLeftTab || "tools");
    applyModeUI();
    updateInspectorHeader(n);
    drawNodes();
  }

  function refreshPortSummary(node) {
    if (!node) return;
    renderNodeConnections(String(node.id || selectedNodeId() || ""));
  }

  function newPortId(side, ports) {
    let idx = (ports || []).length + 1;
    let id = side + "-" + idx;
    const used = new Set((ports || []).map((p) => String(p.id || "")));
    while (used.has(id)) {
      idx += 1;
      id = side + "-" + idx;
    }
    return id;
  }

  function addPort(side) {
    if (!isEditMode()) { toast("仅编辑模式可改端口结构", "warn"); return; }
    const id = $("insNodeId").value;
    const n = getNode(id);
    if (!n) return;
    if (n.kind === "entry" && side === "in") { toast("入口节点不能新增输入端口", "warn"); return; }
    if (n.kind === "terminal" && side === "out") { toast("终止节点不能新增输出端口", "warn"); return; }
    const ports = (((n.ui || {}).ports || {})[side] || []);
    if (ports.length >= 8) { toast("同侧端口数量最多为 8 个", "warn"); return; }
    const pid = newPortId(side, ports);
    ports.push({ id: pid, label: pid, kind: side, max_links: 1, required: false });
    n.ui.ports = n.ui.ports || { in: [], out: [] };
    n.ui.ports[side] = ports;
    refreshPortSummary(n);
    renderPortLists(n);
    redrawGraph();
  }

  function removePort(side) {
    if (!isEditMode()) { toast("仅编辑模式可改端口结构", "warn"); return; }
    const id = $("insNodeId").value;
    const n = getNode(id);
    if (!n) return;
    const ports = ((n.ui && n.ui.ports && n.ui.ports[side]) || []);
    if (!ports.length) return;
    if (ports.length <= 1) { toast("该侧至少保留一个端口", "warn"); return; }
    if (!state.selectedPort || state.selectedPort.side !== side) {
      toast("请先在" + (side === "in" ? "输入" : "输出") + "针脚列表中选择要删除的针脚", "warn");
      return;
    }
    const pid = String(state.selectedPort.id || "");
    const hit = ports.find((p) => String(p.id) === pid);
    if (!hit) { toast("选中的针脚不存在，请重新选择", "warn"); state.selectedPort = null; renderPortLists(n); return; }
    const hasLinks = countLinks(n.id, side, pid) > 0;
    if (hasLinks) { toast("请先删除占用该端口的连线", "warn"); return; }
    n.ui.ports[side] = ports.filter((p) => String(p.id) !== pid);
    n.ui.ports = n.ui.ports || { in: [], out: [] };
    state.selectedPort = null;
    refreshPortSummary(n);
    renderPortLists(n);
    redrawGraph();
  }

  function closeNodeEditor() {
    state.selection.nodes.clear();
    const card = $("nodeInspectorCard");
    if (card) card.removeAttribute("data-selected-node-id");
    if ($("insNodeName")) $("insNodeName").value = "";
    ["insNodeId", "insNodeOwner", "insNodeAgentMeta", "insNodeRemotePort", "insNodeEndpoints", "insNodeDesc", "insNodeTags", "insNodeColor", "insNodeKindDisplay", "insNodeRemotePortBasic", "insNodeEndpointsBasic", "insNodeDeployVersionBasic", "insNodeServiceSummary", "insNodeNotes"].forEach((id) => {
      const el = $(id);
      if (el) el.value = "";
    });
    if ($("insNodeKind")) $("insNodeKind").value = "standard";
    if ($("insNodePrimaryAgentBasic")) $("insNodePrimaryAgentBasic").innerHTML = '<option value="">未绑定</option>';
    if ($("insNodeRole")) $("insNodeRole").selectedIndex = 0;
    if ($("insNodeBizStatus")) $("insNodeBizStatus").selectedIndex = 0;
    if ($("insNodePrimaryAgent")) $("insNodePrimaryAgent").innerHTML = '<option value="">未绑定</option>';
    if ($("insNodeService")) $("insNodeService").innerHTML = '<option value="">请先选择 Agent</option>';
    renderPortLists({ id: "" });
    renderTagChips([]);
    renderMonitorPanel("");
    updateInspectorHeader(null);
    drawNodes();
  }

