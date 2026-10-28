  function drawEdgeLabels() {
    const svg = $("edgeLabelSvg");
    if (!svg) return;
    svg.innerHTML = "";
    (state.topology.edges || []).forEach((edge) => {
      const d = edgePath(edge);
      if (!d) return;
      const flow = state.flowViz.edges.has(edge.id);
      const fail = (state.flowViz.statusByNode[String(edge.to)] && ["FAILED", "TIMEOUT", "CANCELED"].includes(String(state.flowViz.statusByNode[String(edge.to)]).toUpperCase()));
      const slots = edgeDecorSlots(edge);
      if (slots) {
        const label = document.createElementNS("http://www.w3.org/2000/svg", "g");
        label.setAttribute("class", "edge-route-label");
        const txtValue = compactEdgeLabel(edge);
        const labelWidth = Math.max(44, Math.min(120, txtValue.length * 7 + 14));
        const labelX = Math.round(slots.label.x);
        const labelTop = Math.round(slots.label.y);
        const labelH = slots.label.h || 18;
        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", String(labelX - labelWidth / 2));
        rect.setAttribute("y", String(labelTop));
        rect.setAttribute("width", String(labelWidth));
        rect.setAttribute("height", String(labelH));
        rect.setAttribute("rx", "9");
        const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
        txt.setAttribute("x", String(labelX));
        txt.setAttribute("y", String(labelTop + Math.round(labelH * 0.72)));
        txt.setAttribute("text-anchor", "middle");
        txt.textContent = txtValue;
        label.appendChild(rect);
        label.appendChild(txt);
        svg.appendChild(label);
      }
      if (flow) {
        const m = edgeMid(edge);
        const mm = (state.flowViz.metricsByEdge || {})[edge.id];
        if (m && mm) {
          const grp = document.createElementNS("http://www.w3.org/2000/svg", "g");
          grp.setAttribute("class", "edge-metric" + (fail ? " fail" : ""));
          const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
          rect.setAttribute("x", String(Math.round(m.x - 56)));
          rect.setAttribute("y", String(Math.round(m.y - 14)));
          rect.setAttribute("width", "112");
          rect.setAttribute("height", "24");
          rect.setAttribute("rx", "11");
          const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
          txt.setAttribute("x", String(Math.round(m.x)));
          txt.setAttribute("y", String(Math.round(m.y + 2)));
          txt.setAttribute("text-anchor", "middle");
          txt.textContent = "TPS " + mm.tps + " · " + mm.latency + "ms";
          grp.appendChild(rect);
          grp.appendChild(txt);
          svg.appendChild(grp);
        }
      }
    });
  }

  function drawEdges() {
    drawEdgePaths();
    drawEdgeLabels();
  }

  function drawPorts(node, side) {
    const ports = (((node.ui || {}).ports || {})[side] || []);
    return '<div class="ports ' + side + '" aria-hidden="true">' + ports.map((p) => {
      const label = '<span class="port-label">' + esc(p.label || p.id) + ' (' + countLinks(node.id, side, p.id) + ")</span>";
      const dot = '<span class="port-dot" data-node-id="' + esc(node.id) + '" data-side="' + side + '" data-port-id="' + esc(p.id) + '" title="' + esc(p.label || p.id) + '"></span>';
      const inner = side === "in" ? (label + dot) : (dot + label);
      return '<div class="port-item ' + side + '" data-node-id="' + esc(node.id) + '" data-side="' + side + '" data-port-id="' + esc(p.id) + '">' + inner + "</div>";
    }).join("") + "</div>";
  }

  function drawNodes() {
    const layer = $("nodeLayer");
    layer.innerHTML = "";
    const runtime = runtimeById();
    (state.topology.nodes || []).forEach((n) => {
      if ((n.ui || {}).list_only) return;
      const ag = resolveAgentForNode(n);
      const aid = String((state.nodeBindings || {})[n.id] || (ag && ag.agent_id) || "");
      const bindText = ag ? ("Agent： " + (ag.display_name || ag.agent_id)) : "未绑定 Agent";
      const agHealth = agentHealthLabel(ag);
      const runtimeStatus = nodeRuntimeStatus(n, ag, aid);
      const st = String(n.bizStatus || "normal");
      const stLabel = runtimeStatus.text;
      const flowSt = String((state.flowViz.statusByNode || {})[n.id] || "").toUpperCase();
      const isFlow = state.flowViz.nodes.has(n.id);
      const palette = nodePalette(n);
      const runtimeItem = runtime[n.id] || {};
      const displayTitle = nodeDisplayTitle(n);
      const metaId = String(runtimeItem.server_id || n.server_id || n.id || "-");
      const descLine = String(n.desc || "").trim() || roleLabel(n.role);
      let statusText = runtimeStatus.text;
      let statusCls = runtimeStatus.cls;
      const probeOk = runtimeStatus.cls === "ok";
      const flowStarting = isFlow && (flowSt === "STARTING" || flowSt === "RUNNING");
      if (flowStarting && (statusText === "已停止" || statusText === "未知" || statusText === "探活中")) {
        statusText = flowSt === "RUNNING" ? "运行中" : "启动中";
        statusCls = flowSt === "RUNNING" ? "ok" : "warn";
      } else if (state.runtimeStarting && state.runtimeLastStatus === "running" && statusText === "已停止") {
        statusText = "等待启动";
        statusCls = "warn";
      }

      const hasIn = (state.topology.edges || []).some((e) => String(e.to) === String(n.id));
      const agentHref = agentServerHref(ag, aid, n.id);
      const agentLine = (ag || aid)
        ? ('<div class="node-agent-line">Agent: ' + esc(aid || (ag && ag.agent_id) || "") + '</div>'
          + (agentHref
            ? ('<div class="node-agent-actions"><button class="node-agent-open-btn" type="button" data-agent-href="' + esc(agentHref) + '" title="打开 Agent 服务器界面">服务器 ↗</button></div>')
            : ""))
        : "";
      const segmentHl = isTestSegmentScope() && state.highlight.nodes.size > 0;
      const seqAnim = probeOk && isFlow && (flowSt === "RUNNING" || flowSt === "STARTING");
      const liveRunning = probeOk && (nodeIsLiveRunning(n, ag, aid, runtimeStatus) || seqAnim);

      const el = document.createElement("div");
      el.className = "node structured-node tw-node"
        + (hasIn ? " has-in-port" : "")
        + (state.selection.nodes.has(n.id) ? " sel" : "")
        + (segmentHl && state.highlight.nodes.has(n.id) ? " hl" : "")
        + (segmentHl && !state.highlight.nodes.has(n.id) ? " path-dim" : "")
        + (isFlow ? " flow-active" : "")
        + (flowSt === "STARTING" ? " flow-starting" : "")
        + (liveRunning ? " live-running run-active" : "")
        + (["FAILED", "TIMEOUT", "CANCELED"].includes(flowSt) ? " flow-fail" : "")
        + (flowSt === "SUCCESS" ? " flow-ok" : "")
        + ((((n.ui || {}).disabled) ? " is-disabled" : ""));
      el.style.left = n.ui.x + "px";
      el.style.top = n.ui.y + "px";
      el.style.width = n.ui.w + "px";
      el.style.minHeight = Math.max(n.ui.h || 0, 128) + "px";
      el.style.setProperty("--node-accent", palette.border);
      el.style.setProperty("--node-glow", palette.glow || "rgba(37,99,235,.18)");
      el.style.setProperty("--node-bg", palette.bg1 || "#ffffff");
      el.innerHTML = '<div class="node-top-accent"></div>'
        + '<div class="node-role-strip"></div>'
        + (structuredMode() ? "" : (drawPorts(n, "in") + drawPorts(n, "out")))
        + (isEditMode() ? '<button class="node-remove-btn" type="button" data-node-id="' + esc(n.id) + '" title="删除节点"></button>' : "")
        + (isEditMode() ? '<button class="node-add-btn" type="button" data-node-id="' + esc(n.id) + '" title="添加下游" aria-label="从 ' + esc(displayTitle) + ' 添加下游"></button>' : "")
        + '<div class="node-shell">'
        +   '<div class="node-card-head">'
        +     '<span class="node-badge" style="--ico-accent:' + esc(iconAccent(n)) + '">' + roleBadge(n) + '</span>'
        +     '<div class="node-heading-block">'
        +       '<div class="node-title">' + esc(displayTitle) + '</div>'
        +       '<div class="node-desc">' + esc(descLine) + '</div>'
        +     '</div>'
        +   '</div>'
        +   '<div class="node-id-line">ID: ' + esc(metaId) + '</div>'
        +   '<div class="node-status-line status-' + esc(statusCls) + '"><span class="node-status-dot"></span>' + esc(statusText) + '</div>'
        +   agentLine
        + '</div>';
      el.onclick = (ev) => { ev.stopPropagation(); openNodeEditor(n.id); };
      layer.appendChild(el);
    });

    layer.querySelectorAll(".node-add-btn").forEach((btn) => {
      btn.onclick = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        openStructuredAddMenu(btn.getAttribute("data-node-id"));
      };
    });
    layer.querySelectorAll(".node-remove-btn").forEach((btn) => {
      btn.onclick = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        confirmStructuredDeleteNode(btn.getAttribute("data-node-id"));
      };
    });
    layer.querySelectorAll(".node-agent-open-btn").forEach((btn) => {
      btn.onclick = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const href = String(btn.getAttribute("data-agent-href") || "").trim();
        if (href) window.location.href = href;
      };
    });

    // Structured mode is the only exposed authoring model: ports remain data,
    // but users add/delete topology through node/edge +/- controls.
  }

  function renderRuntimeNodeList() {
    const body = $("runtimeNodeList");
    if (!body) return;
    const nodes = state.topology.nodes || [];
    if (!nodes.length) {
      body.innerHTML = '<tr><td colspan="5" class="topology-table-empty">暂无节点</td></tr>';
      return;
    }
    body.innerHTML = nodes.map((n) => {
      const aid = String((state.nodeBindings || {})[n.id] || "");
      const sid = String((state.serviceBindings || {})[n.id] || "");
      const bindLabel = sid || aid ? "已绑定" : "未绑定";
      const bindCls = sid || aid ? "state-ok" : "state-warn";
      const ag = state.agents.find((x) => String(x.agent_id || "") === aid) || null;
      const runtimeStatus = nodeRuntimeStatus(n, ag, aid);
      const stLabel = runtimeStatus.text;
      const stCls = runtimeStatus.cls === "ok" ? "state-ok" : (runtimeStatus.cls === "err" ? "state-err" : "state-warn");
      return '<tr data-node-row="' + esc(n.id) + '">'
        + '<td><span class="node-row-name"><span class="node-row-ico" style="--ico-accent:' + esc(iconAccent(n)) + '">' + roleBadge(n) + '</span>' + esc(nodeDisplayTitle(n)) + '</span></td>'
        + '<td>' + esc(roleLabel(n.role)) + '</td>'
        + '<td><span class="state-pill ' + bindCls + '">' + esc(bindLabel) + '</span></td>'
        + '<td><span class="state-pill ' + stCls + '">' + esc(stLabel) + '</span></td>'
        + '<td class="topology-node-row-actions">'
        + '<button type="button" class="btn linkish" data-node-open="' + esc(n.id) + '">打开</button>'
        + '<button type="button" class="btn linkish" data-node-probe="' + esc(n.id) + '">探测</button>'
        + '</td>'
        + '</tr>';
    }).join("");
    body.querySelectorAll("[data-node-open]").forEach((btn) => {
      btn.onclick = () => openNodeEditor(btn.getAttribute("data-node-open"));
    });
    body.querySelectorAll("[data-node-probe]").forEach((btn) => {
      btn.onclick = async () => {
        openNodeEditor(btn.getAttribute("data-node-probe"));
        if ($("btnProbeNode")) $("btnProbeNode").click();
      };
    });
  }

  const FALLBACK_ROLE_RULES = {
    gateway: { up: ["edge", "lb", "admin"], down: ["business", "pressure", "auth"] },
    auth: { up: ["gateway", "edge"], down: ["business"] },
    business: { up: ["gateway", "scheduler", "admin", "auth"], down: ["database", "cache", "mq", "search", "transport"] },
    admin: { up: ["gateway", "edge"], down: ["business"] },
    transport: { up: ["business", "gateway"], down: [] },
    pressure: { up: ["gateway", "admin"], down: ["business"] },
    database: { up: ["business", "scheduler", "admin"], down: [] },
    cache: { up: ["business", "gateway", "scheduler"], down: [] },
    mq: { up: ["business", "gateway", "scheduler"], down: ["business", "analytics"] },
    scheduler: { up: ["admin"], down: ["business", "database", "cache", "mq"] },
    search: { up: ["business", "gateway", "scheduler"], down: [] },
    analytics: { up: ["business", "gateway", "scheduler"], down: [] },
    edge: { up: [], down: ["gateway"] },
  };

  function presetRoleRules(role) {
    const r = String(role || "").toLowerCase();
    const up = new Set();
    const down = new Set();
    (state.presets || []).forEach((p) => {
      if (String(p.role || "").toLowerCase() !== r) return;
      (p.fixed_upstream_roles || []).forEach((x) => up.add(String(x).toLowerCase()));
      (p.fixed_downstream_roles || []).forEach((x) => down.add(String(x).toLowerCase()));
    });
    const fb = FALLBACK_ROLE_RULES[r];
    if (fb) {
      (fb.up || []).forEach((x) => up.add(String(x).toLowerCase()));
      (fb.down || []).forEach((x) => down.add(String(x).toLowerCase()));
    }
    return { allowed_upstream_roles: [...up], allowed_downstream_roles: [...down] };
  }

  function connectRuleMeta(nodeLike) {
    const role = String((nodeLike && nodeLike.role) || "business").toLowerCase();
    const presetRules = presetRoleRules(role);
    return {
      role,
      kind: inferKind(role, nodeLike && nodeLike.kind),
      allowed_upstream_roles: presetRules.allowed_upstream_roles,
      allowed_downstream_roles: presetRules.allowed_downstream_roles,
    };
  }

  function linkRoleBlockReason(fromNodeId, toLike) {
    const fromNode = getNode(fromNodeId);
    if (!fromNode || !toLike) return "节点不存在";
    const fromMeta = connectRuleMeta(fromNode);
    const toMeta = connectRuleMeta(toLike);
    const allowDown = fromMeta.allowed_downstream_roles || [];
    const allowUp = toMeta.allowed_upstream_roles || [];
    if (allowDown.length && toMeta.role && !allowDown.includes(toMeta.role)) {
      return "「" + fromMeta.role + "」不允许连接「" + toMeta.role + "」（可连下游：" + allowDown.join(", ") + "）";
    }
    if (allowUp.length && fromMeta.role && !allowUp.includes(fromMeta.role)) {
      return "「" + toMeta.role + "」不接受来自「" + fromMeta.role + "」（可接受上游：" + allowUp.join(", ") + "）";
    }
    return "";
  }

  function portLinkCount(nodeId, side, portId) {
    return (state.topology.edges || []).filter((e) => {
      if (side === "out") return String(e.from) === String(nodeId) && String(e.from_port || "out-1") === portId;
      return String(e.to) === String(nodeId) && String(e.to_port || "in-1") === portId;
    }).length;
  }

  function hasStructuredFreePort(nodeId, side) {
    const n = getNode(nodeId);
    if (!n) return false;
    const kind = inferKind(n.role, n.kind);
    const ports = normalizePorts(kind, (n.ui || {}).ports);
    const rows = ports[side] || [];
    for (let i = 0; i < rows.length; i += 1) {
      const p = rows[i];
      const pid = String(p.id || "");
      const maxLinks = Math.max(1, Number(p.max_links || 1));
      if (pid && portLinkCount(nodeId, side, pid) < maxLinks) return true;
    }
    const maxPorts = (kind === "entry" || kind === "terminal") ? 8 : 6;
    return rows.length < maxPorts;
  }

  function canStructuredConnect(fromNodeId, toLike) {
    const fromNode = getNode(fromNodeId);
    if (!fromNode || !toLike) return { ok: false, msg: "节点不存在" };
    const toId = String(toLike.id || "");
    if (toId && toId === fromNodeId) return { ok: false, msg: "不能连接同一个节点" };
    const fromMeta = connectRuleMeta(fromNode);
    const toMeta = connectRuleMeta(toLike);
    if (fromMeta.kind === "terminal" || toMeta.kind === "entry") return { ok: false, msg: "节点语义方向不允许连接" };
    const roleMsg = linkRoleBlockReason(fromNodeId, toLike);
    if (roleMsg) return { ok: false, msg: roleMsg };
    if (toId && (state.topology.edges || []).some((e) => String(e.from) === String(fromNodeId) && String(e.to) === toId)) {
      return { ok: false, msg: "两个节点之间已存在连线" };
    }
    if (toId && !hasStructuredFreePort(fromNodeId, "out")) {
      return { ok: false, msg: "源节点输出端口已满，请先释放或扩展端口" };
    }
    if (toId && !hasStructuredFreePort(toId, "in")) {
      return { ok: false, msg: "目标节点输入端口已满" };
    }
    return { ok: true };
  }

  function legalExistingTargetsForNode(nodeId) {
    return (state.topology.nodes || [])
      .filter((n) => n && n.id && n.id !== nodeId && !(n.ui || {}).list_only)
      .map((n) => ({ node: n, check: canStructuredConnect(nodeId, n) }))
      .filter((x) => x.check.ok)
      .map((x) => x.node);
  }

  function legalPresetsForNode(nodeId) {
    return (state.presets || [])
      .filter((p) => canStructuredConnect(nodeId, {
        id: "",
        role: p.role,
        kind: p.kind,
      }).ok);
  }

  function applyStructuredTopologyResponse(d, successText) {
    if (!d || d.ok === false) {
      toast((d && (d.message || d.error)) || "结构化操作失败", "error");
      appendJsonDetail("结构化操作失败原始响应", d || {});
      return false;
    }
    state.topology = d.topology || state.topology;
    normalizeTopology();
    layoutStructuredGraph();
    state.selection.edgeId = "";
    pushHistory();
    redrawGraph();
    renderRuntimeNodeList();
    fillTestNodeOptions();
    toast(successText || d.message || "操作成功", "ok");
    logMode(successText || d.message || "结构化操作成功");
    return true;
  }

  function structuredAddTileHtml(source, title, meta) {
    const accent = iconAccent(source);
    const iconHtml = source && source.preset_id
      ? presetIcon(source.role, { tile: true })
      : roleBadge(source);
    return '<span class="structured-add-tile-ico" style="--ico-accent:' + esc(accent) + '">' + iconHtml + "</span>"
      + '<span class="structured-add-tile-text">'
      + '<span class="structured-add-tile-name">' + esc(title) + "</span>"
      + '<span class="structured-add-tile-meta">' + esc(meta) + "</span>"
      + "</span>"
      + '<span class="structured-add-tile-action" aria-hidden="true">+</span>';
  }

