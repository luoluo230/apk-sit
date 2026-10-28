  function appendStructuredAddTile(parent, source, title, meta, onClick) {
    const accent = iconAccent(source);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "structured-add-tile";
    btn.style.setProperty("--tile-accent", accent);
    btn.innerHTML = structuredAddTileHtml(source, title, meta);
    btn.onclick = onClick;
    parent.appendChild(btn);
  }

  function setStructuredAddCount(el, count) {
    if (!el) return;
    if (!count) {
      el.textContent = "";
      el.classList.add("hidden");
      return;
    }
    el.textContent = String(count);
    el.classList.remove("hidden");
  }

  function openStructuredAddMenu(nodeId) {
    if (!isEditMode()) { toast("运行/测试模式不可修改结构", "warn"); return; }
    const node = getNode(nodeId);
    if (!node) return;
    state.structuredAddCtx = { fromNodeId: nodeId };
    const modal = $("structuredAddModal");
    const title = $("structuredAddTitle");
    const existingBox = $("structuredExistingList");
    const presetBox = $("structuredPresetList");
    const existingCount = $("structuredExistingCount");
    const presetCount = $("structuredPresetCount");
    if (!modal || !existingBox || !presetBox) return;
    if (title) title.textContent = "从 “" + runtimeName(nodeId) + "” 添加下游";
    const existing = legalExistingTargetsForNode(nodeId);
    const presets = legalPresetsForNode(nodeId);
    setStructuredAddCount(existingCount, existing.length);
    setStructuredAddCount(presetCount, presets.length);
    existingBox.innerHTML = "";
    if (!existing.length) {
      existingBox.innerHTML = '<div class="structured-add-empty">当前拓扑中没有可连接的已有节点</div>';
    } else {
      const grid = document.createElement("div");
      grid.className = "structured-add-grid";
      existing.forEach((n) => {
        appendStructuredAddTile(
          grid,
          n,
          nodeDisplayTitle(n),
          roleLabel(n.role) + " · " + semanticTypeLabel(n),
          () => structuredAddExistingTarget(nodeId, n.id)
        );
      });
      existingBox.appendChild(grid);
    }
    presetBox.innerHTML = "";
    if (!presets.length) {
      presetBox.innerHTML = '<div class="structured-add-empty">当前节点没有可添加的下游类型</div>';
    } else {
      const grouped = {};
      presets.forEach((p) => { const g = presetGroup(p); if (!grouped[g]) grouped[g] = []; grouped[g].push(p); });
      PRESET_GROUP_ORDER.filter((g) => grouped[g] && grouped[g].length).forEach((g) => {
        const sec = document.createElement("div");
        sec.className = "structured-add-group";
        const hd = document.createElement("div");
        hd.className = "structured-add-group-hd";
        hd.innerHTML = '<span class="structured-add-group-title">' + esc(g) + '</span>'
          + '<span class="structured-add-group-count">' + grouped[g].length + "</span>";
        sec.appendChild(hd);
        const grid = document.createElement("div");
        grid.className = "structured-add-grid";
        grid.setAttribute("data-group", g);
        grouped[g].forEach((p) => {
          appendStructuredAddTile(
            grid,
            p,
            p.name || presetTileLabel(p),
            roleLabel(p.role) + " · " + inferKind(p.role, p.kind),
            () => structuredAddNewTarget(nodeId, p.preset_id)
          );
        });
        sec.appendChild(grid);
        presetBox.appendChild(sec);
      });
    }
    modal.classList.remove("hidden");
    setModalOpen(true);
  }

  function closeStructuredAddMenu() {
    const modal = $("structuredAddModal");
    if (modal) modal.classList.add("hidden");
    setModalOpen(false);
    state.structuredAddCtx = null;
  }

  async function structuredAddExistingTarget(fromNodeId, toNodeId) {
    const check = canStructuredConnect(fromNodeId, getNode(toNodeId) || { id: toNodeId });
    if (!check.ok) {
      toast(check.msg || "当前节点不能作为下游", "warn");
      return;
    }
    const d = await OpsApi.structuredAddExistingTarget(Object.assign(currentScope(), { from_node_id: fromNodeId, to_node_id: toNodeId }));
    if (!d || d.ok === false) {
      toast((d && (d.message || d.error)) || "添加下游连线失败", "error");
      appendJsonDetail("添加已有下游失败原始响应", d || {});
      return;
    }
    if (applyStructuredTopologyResponse(d, "已连接已有下游节点")) closeStructuredAddMenu();
  }

  async function structuredAddNewTarget(fromNodeId, presetId) {
    const d = await OpsApi.structuredAddNewTarget(Object.assign(currentScope(), { from_node_id: fromNodeId, preset_id: presetId }));
    if (applyStructuredTopologyResponse(d, "已新增并连接下游节点")) closeStructuredAddMenu();
  }

  async function confirmStructuredDeleteNode(nodeId) {
    if (!isEditMode()) { toast("运行/测试模式不可删除节点", "warn"); return; }
    const name = runtimeName(nodeId);
    if (!window.confirm("确认删除节点 “" + name + "”？\n\n删除会同时移除相关连线，关键链路会被系统拦截。")) return;
    const d = await OpsApi.structuredDeleteNode(Object.assign(currentScope(), { node_id: nodeId }));
    applyStructuredTopologyResponse(d, "节点已删除");
  }

  async function confirmStructuredDeleteEdge(edgeId) {
    if (!isEditMode()) { toast("运行/测试模式不可删除连线", "warn"); return; }
    const edge = (state.topology.edges || []).find((e) => String(e.id) === String(edgeId));
    const label = edge ? (runtimeName(edge.from) + " → " + runtimeName(edge.to)) : edgeId;
    if (!window.confirm("确认删除连线 “" + label + "”？\n\n关键链路会被系统拦截。")) return;
    const d = await OpsApi.structuredDeleteEdge(Object.assign(currentScope(), { edge_id: edgeId }));
    applyStructuredTopologyResponse(d, "连线已删除");
  }

  function presetGroup(p) {
    const r = String((typeof p === "string" ? p : (p && p.role)) || "").toLowerCase();
    if (["gateway", "edge", "transport", "tcp"].includes(r)) return "网关与入口";
    if (["auth", "business", "admin", "analytics"].includes(r)) return "业务服务";
    if (["database", "cache", "search"].includes(r)) return "运维基础";
    if (["mq", "pressure", "scheduler"].includes(r)) return "中间件";
    return "其他";
  }

  const PRESET_GROUP_ORDER = ["网关与入口", "业务服务", "运维基础", "中间件", "其他"];

  function presetTileLabel(p) {
    const role = String((p && p.role) || "").toLowerCase();
    const pid = String((p && p.preset_id) || "").toLowerCase();
    if (role === "gateway" || pid.includes("gateway")) return "Gateway";
    if (role === "auth" || pid.includes("auth")) return "Auth";
    if (role === "business") return "Game";
    if (role === "admin" || pid.includes("ops")) return "Ops";
    if (role === "transport" || pid.includes("tcp")) return "TCP";
    if (role === "database") return pid.includes("mongo") ? "Mongo DB" : "DB";
    if (role === "cache") return "Cache";
    if (role === "mq") return "MQ";
    if (role === "scheduler") return "Scheduler";
    if (role === "pressure") return "Pressure";
    return String(p.name || p.preset_id || "-");
  }

  function presetIcon(role, opts) {
    return roleIconSvg(role, Object.assign({ tile: true }, opts || {}));
  }

  function renderPresets() {
    const box = $("presetList");
    const quickBar = $("presetQuickBar");
    const categorySelect = $("presetCategoryFilter");
    const kw = String($("presetSearch").value || "").toLowerCase().trim();
    if (categorySelect && !categorySelect.dataset.ready) {
      categorySelect.innerHTML = '<option value="">全部分类</option>'
        + ["网关与入口", "业务服务", "运维基础", "中间件", "其他"].map((g) => '<option value="' + esc(g) + '">' + esc(g) + "</option>").join("");
      categorySelect.dataset.ready = "1";
    }
    let category = categorySelect ? String(categorySelect.value || "") : "";
    const activeChip = document.querySelector("#presetCategoryChips .topology-chip.active");
    if (activeChip) category = String(activeChip.getAttribute("data-category") || "");
    box.innerHTML = "";
    if (quickBar) quickBar.innerHTML = "";
    const rows = (state.presets || []).filter((p) => {
      const group = presetGroup(p);
      const hay = (String(p.name || "") + " " + String(p.role || "") + " " + String(p.preset_id || "")).toLowerCase();
      return (!kw || hay.includes(kw)) && (!category || group === category);
    });

    if (quickBar) {
      quickBar.innerHTML = '<div class="topology-section-title sm">快捷模板</div><div class="topology-quick-row"></div>';
      const row = quickBar.querySelector(".topology-quick-row");
      const quickPick = [
        { label: "Gateway", match: (p) => String(p.role || "").toLowerCase() === "gateway" },
        { label: "Auth", match: (p) => String(p.role || "").toLowerCase() === "auth" },
        { label: "Game", match: (p) => String(p.role || "").toLowerCase() === "business" },
        { label: "DB", match: (p) => String(p.preset_id || "").toLowerCase() === "mongo_db" || String(p.name || "").toLowerCase().includes("mongo") },
      ];
      quickPick.forEach(({ label, match }) => {
        const hit = (state.presets || []).find(match);
        if (!hit || !row) return;
        const card = document.createElement("button");
        card.type = "button";
        card.className = "topology-quick-card" + (state.activePresetId === hit.preset_id ? " active" : "");
        card.innerHTML = '<span class="quick-ico" style="--ico-accent:' + esc(iconAccent(hit)) + '">' + presetIcon(hit.role, { tile: true }) + '</span>'
          + '<span class="quick-text"><span class="quick-name">' + esc(label) + '</span></span>';
        card.onclick = () => { state.activePresetId = hit.preset_id; renderPresets(); };
        card.ondblclick = async (ev) => { ev.preventDefault(); state.activePresetId = hit.preset_id; await addPresetAt(centerWorld()); };
        row.appendChild(card);
      });
    }

    if (!rows.length) { box.innerHTML = '<div class="preset-empty">没有匹配模板</div>'; return; }

    const groups = {};
    rows.forEach((p) => { const g = presetGroup(p); if (!groups[g]) groups[g] = []; groups[g].push(p); });

    PRESET_GROUP_ORDER.filter((g) => groups[g] && groups[g].length).forEach((g) => {
      const sec = document.createElement("div");
      sec.className = "preset-group";
      const collapsed = !!state.presetCollapsed[g];
      const hd = document.createElement("div");
      hd.className = "preset-group-hd";
      hd.innerHTML = "<span class=\"preset-group-title\">" + (collapsed ? "▸" : "▾") + " " + esc(g) + '</span><span class="preset-group-count">' + groups[g].length + "</span>";
      hd.onclick = () => { state.presetCollapsed[g] = !state.presetCollapsed[g]; renderPresets(); };
      sec.appendChild(hd);

      if (!collapsed) {
        const grid = document.createElement("div");
        grid.className = "preset-group-grid";
        grid.setAttribute("data-group", g);
        groups[g].forEach((p) => {
          const card = document.createElement("div");
          card.className = "preset-tile" + (state.activePresetId === p.preset_id ? " active" : "");
          card.draggable = true;
          const accent = iconAccent(p);
          card.innerHTML = '<button type="button" class="preset-tile-add" title="添加到画布">+</button>'
            + '<div class="preset-tile-main">'
            +   '<span class="preset-tile-ico" style="--ico-accent:' + esc(accent) + '">' + presetIcon(p.role, { tile: true }) + '</span>'
            +   '<span class="preset-tile-text">'
            +     '<span class="preset-tile-name">' + esc(presetTileLabel(p)) + '</span>'
            +     '<span class="preset-tile-meta">' + esc(roleLabel(p.role)) + '</span>'
            +   "</span>"
            + "</div>";
          card.onclick = () => { state.activePresetId = p.preset_id; renderPresets(); };
          card.ondragstart = (e) => e.dataTransfer.setData("text/plain", p.preset_id);
          const addBtn = card.querySelector(".preset-tile-add");
          if (addBtn) addBtn.onclick = async (ev) => { ev.stopPropagation(); state.activePresetId = p.preset_id; await addPresetAt(centerWorld()); };
          grid.appendChild(card);
        });
        sec.appendChild(grid);
      }

      box.appendChild(sec);
    });
  }

  async function addPresetAt(worldPos) {
    if (isTestMode()) { toast("测试模式禁止新增节点", "warn"); return; }
    const p = (state.presets || []).find((x) => x.preset_id === state.activePresetId);
    if (!p) return;
    const d = await OpsApi.addNodeFromPreset(Object.assign(currentScope(), {
      preset_id: String(p.preset_id || ""),
      name: "",
      server_id: "",
      project_id: state.projectId,
      owner: "",
      description: p.default_desc || "",
    }));
    if (!d.ok) { toast(d.message || "新增节点失败", "error"); logMode("新增节点失败: " + (d.message || d.error || "未知错误"), "error"); return; }
    await loadAll();
    if (d.node && d.node.id) {
      const n = getNode(d.node.id);
      if (n) {
        n.ui.x = Math.round(worldPos.x / 8) * 8;
        n.ui.y = Math.round(worldPos.y / 8) * 8;
        await saveTopologyNow();
        redrawGraph(); renderRuntimeNodeList();
        logMode("新增节点成功: " + d.node.id);
      }
    }
  }

  function renderNodeConnections(nodeId) {
    const nid = String(nodeId || "");
    const inBox = $("nodeIncomingEdges");
    const outBox = $("nodeOutgoingEdges");
    if (!inBox || !outBox) return;
    if (!nid) {
      inBox.innerHTML = '<div class="topology-connection-empty">无上流连接</div>';
      outBox.innerHTML = '<div class="topology-connection-empty">无下游连接</div>';
      return;
    }
    const edges = state.topology.edges || [];
    const incoming = edges.filter((e) => String(e.to) === nid);
    const outgoing = edges.filter((e) => String(e.from) === nid);
    const rowHtml = (edge, direction) => {
      const peerId = direction === "in" ? edge.from : edge.to;
      const route = direction === "in"
        ? (String(peerId) + " → " + nid)
        : (nid + " → " + String(peerId));
      const note = compactEdgeLabel(edge);
      const selected = String(state.selection.edgeId || "") === String(edge.id);
      return '<button type="button" class="topology-connection-item' + (selected ? " is-selected" : "") + '" data-edge-id="' + esc(edge.id) + '">'
        + '<span class="topology-connection-route">' + esc(route) + "</span>"
        + '<span class="topology-connection-meta">' + esc(note) + "</span>"
        + "</button>";
    };
    inBox.innerHTML = incoming.length
      ? incoming.map((e) => rowHtml(e, "in")).join("")
      : '<div class="topology-connection-empty">无上流连接</div>';
    outBox.innerHTML = outgoing.length
      ? outgoing.map((e) => rowHtml(e, "out")).join("")
      : '<div class="topology-connection-empty">无下游连接</div>';
    [inBox, outBox].forEach((box) => {
      box.querySelectorAll("[data-edge-id]").forEach((btn) => {
        btn.onclick = () => {
          state.selection.edgeId = btn.getAttribute("data-edge-id") || "";
          redrawGraph();
          renderNodeConnections(nid);
        };
      });
    });
  }

  function renderPortLists(node) {
    if (!node) return;
    const nid = String(node.id || selectedNodeId() || "");
    if (nid) renderNodeConnections(nid);
  }

  function fillServiceSelect(nodeId, agentId) {
    const sel = $("insNodeService");
    if (!sel) return;
    const aid = String(agentId || (state.nodeBindings || {})[nodeId] || "");
    const services = (state.services || []).filter((s) => !aid || String(s.agent_id || "") === aid);
    sel.innerHTML = '<option value="">' + (aid ? "请选择服务实例" : "请先选择 Agent") + "</option>"
      + services.map((s) => '<option value="' + esc(s.service_id || "") + '">' + esc(s.name || s.service_id || "-") + "</option>").join("");
    const current = String((state.serviceBindings || {})[nodeId] || "");
    sel.value = current;
    if ($("insNodeServiceCount")) $("insNodeServiceCount").value = String(services.length);
  }

  function updateInspectorDeployFields(nodeId) {
    const nid = String(nodeId || "");
    let aid = String((state.nodeBindings || {})[nid] || "");
    if (!aid && nid === "game-01" && isDesignReferenceTopology()) aid = "agent-01";
    const sid = String((state.serviceBindings || {})[nid] || "");
    const bindLabel = sid || aid ? "已绑定" : "未绑定";
    if ($("insNodeBindStatus")) $("insNodeBindStatus").value = sid ? "已绑定服务实例" : (aid ? "已绑定 Agent" : "未绑定");
    if ($("insNodeBindStatusDisplay")) $("insNodeBindStatusDisplay").value = bindLabel;
    if ($("insNodeDeployEnv")) $("insNodeDeployEnv").value = envLabel(state.envKey);
    if ($("insNodeDeployEnvDisplay")) $("insNodeDeployEnvDisplay").value = envLabel(state.envKey);
    const ag = effectiveAgents().find((a) => String(a.agent_id || "") === aid);
    const agentName = ag ? String(ag.display_name || ag.agent_id || aid) : (aid || "未绑定");
    if ($("insNodeAgentDisplay")) $("insNodeAgentDisplay").value = agentName;
    const node = getNode(nid);
    if ($("insNodeOwnerDisplay") && node) $("insNodeOwnerDisplay").value = String(node.owner || "运维团队");
    const svc = (state.services || []).find((s) => String(s.service_id || "") === sid);
    const services = (state.services || []).filter((s) => !aid || String(s.agent_id || "") === aid);
    const isGameDemo = nid === "game-01";
    let deployVer = svc ? String(svc.version || svc.deploy_version || "-") : "-";
    let serviceSummary = aid ? (String(services.length) + " 个实例") : "0 个实例";
    if (isGameDemo) {
      if (!deployVer || deployVer === "-") deployVer = "v2.3.1";
      if (aid) serviceSummary = "3 个实例";
    }
    if ($("insNodeDeployVersion")) $("insNodeDeployVersion").value = deployVer;
    if ($("insNodeDeployVersionBasic")) $("insNodeDeployVersionBasic").value = deployVer;
    if ($("insNodeServiceCount")) $("insNodeServiceCount").value = svc ? "1" : (aid ? String(services.length) : "0");
    if ($("insNodeServiceSummary")) $("insNodeServiceSummary").value = serviceSummary;
    const online = !!(ag && String(ag.probe_status || ag.status || "").toUpperCase() === "PASS");
    const showOnline = !!(aid && (online || isGameDemo));
    ["insNodeAgentOnlinePill", "insNodeAgentOnlinePillNodes"].forEach((id) => {
      const pill = $(id);
      if (!pill) return;
      pill.classList.toggle("is-hidden", !showOnline);
      pill.textContent = "在线";
      pill.className = "state-pill state-ok" + (showOnline ? "" : " is-hidden");
    });
  }

