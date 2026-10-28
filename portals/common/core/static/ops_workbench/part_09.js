  function refreshLeftPanelChrome(leftTab) {
    const tabName = leftTab || state.activeLeftTab || "tools";
    const app = document.querySelector(".ops-topology-app");
    if (app) app.setAttribute("data-left-tab", tabName);
    document.querySelectorAll("[data-log-set]").forEach((box) => {
      const set = box.getAttribute("data-log-set");
      box.classList.toggle("is-hidden", set === "nodes" ? tabName !== "nodes" : tabName === "nodes");
    });
    const topbar = document.querySelector(".topology-canvas-float-left");
    if (topbar) topbar.classList.remove("is-hidden");
    const card = $("nodeInspectorCard");
    if (card) {
      card.setAttribute("data-inspector-layout", tabName === "nodes" ? "nodes" : "tools");
    }
    document.querySelectorAll(".topology-inspector-tab[data-tab-tools]").forEach((tab) => {
      const toolsLabel = tab.getAttribute("data-tab-tools");
      const nodesLabel = tab.getAttribute("data-tab-nodes");
      if (tabName === "nodes" && nodesLabel) tab.textContent = nodesLabel;
      else if (toolsLabel) tab.textContent = toolsLabel;
    });
    document.querySelectorAll(".topology-inspector-actions-tools").forEach((el) => {
      el.classList.toggle("is-hidden", tabName === "nodes");
    });
    document.querySelectorAll(".topology-inspector-actions-nodes").forEach((el) => {
      el.classList.toggle("is-hidden", tabName !== "nodes");
    });
    refreshInspectorLayout(tabName);
    if (tabName === "tools" && state.mode !== "run") clearTestHighlight();
    refreshRightPanelMode();
    const headerControls = document.querySelector(".topology-header-controls");
    if (headerControls) {
      headerControls.setAttribute("data-header-layout", tabName);
      const envLabelEl = headerControls.querySelector(".topology-header-env-label");
      const topoWide = headerControls.querySelector(".topology-header-select-wide");
      if (tabName === "tools") {
        if (envLabelEl) envLabelEl.textContent = "当前拓扑";
        if (topoWide) topoWide.classList.add("is-hidden");
      } else {
        if (envLabelEl) envLabelEl.textContent = "环境";
        if (topoWide) topoWide.classList.remove("is-hidden");
      }
    }
  }

  function validateTopologyLocal() {
    const nodes = state.topology.nodes || [];
    const edges = state.topology.edges || [];
    const ids = new Set(nodes.map((n) => String(n.id || "")));
    const problems = [];
    edges.forEach((edge) => {
      if (!ids.has(String(edge.from || "")) || !ids.has(String(edge.to || ""))) {
        problems.push("存在引用不存在节点的连线: " + String(edge.id || "-"));
      }
    });
    const isolated = nodes.filter((node) => !edges.some((e) => String(e.from) === String(node.id) || String(e.to) === String(node.id)));
    isolated.forEach((node) => problems.push("节点未接入链路: " + String(node.name || node.id || "-")));
    return { ok: problems.length === 0, problems };
  }

  function bindLeftTabs() {
    const tabs = Array.from(document.querySelectorAll("[data-topology-left-tab]"));
    const panels = Array.from(document.querySelectorAll("[data-left-panel]"));
    if (!tabs.length || !panels.length) return;
    const activate = (name) => {
      state.activeLeftTab = name;
      tabs.forEach((tab) => {
        const on = tab.getAttribute("data-topology-left-tab") === name;
        tab.classList.toggle("active", on);
        tab.setAttribute("aria-selected", on ? "true" : "false");
      });
      panels.forEach((panel) => {
        panel.classList.toggle("is-hidden", panel.getAttribute("data-left-panel") !== name);
      });
      refreshLeftPanelChrome(name);
      refreshLogDemoForChrome();
    };
    tabs.forEach((tab) => {
      tab.onclick = () => activate(tab.getAttribute("data-topology-left-tab") || "tools");
    });
    activate("tools");
  }

  function refreshInspectorLayout(leftTab) {
    const layout = leftTab === "nodes" ? "nodes" : "tools";
    const card = $("nodeInspectorCard");
    if (card) card.setAttribute("data-inspector-layout", layout);
    const roleLabelEl = document.querySelector("#basicInfoPanel .topology-field[data-field='role'] .topology-field-label");
    if (roleLabelEl) roleLabelEl.textContent = layout === "nodes" ? "节点类型" : "角色";
    const nid = String(($("insNodeId") || {}).value || "").trim() || selectedNodeId();
    if (nid) {
      const n = getNode(nid);
      if (n && $("insNodeDesc")) $("insNodeDesc").value = String(n.desc || "");
    }
  }

  function syncInspectorAgentBasicFromMain() {
    const main = $("insNodePrimaryAgent");
    const basic = $("insNodePrimaryAgentBasic");
    if (main && basic && basic.value !== main.value) basic.value = main.value;
  }

  function syncInspectorAgentMainFromBasic() {
    const main = $("insNodePrimaryAgent");
    const basic = $("insNodePrimaryAgentBasic");
    if (main && basic && main.value !== basic.value) main.value = basic.value;
  }

  function syncInspectorPortFieldsFromMain() {
    const port = $("insNodeRemotePort");
    const portBasic = $("insNodeRemotePortBasic");
    const eps = $("insNodeEndpoints");
    const epsBasic = $("insNodeEndpointsBasic");
    if (port && portBasic) portBasic.value = port.value;
    if (eps && epsBasic) epsBasic.value = eps.value;
  }

  function syncInspectorPortFieldsFromBasic() {
    const port = $("insNodeRemotePort");
    const portBasic = $("insNodeRemotePortBasic");
    const eps = $("insNodeEndpoints");
    const epsBasic = $("insNodeEndpointsBasic");
    if (port && portBasic) port.value = portBasic.value;
    if (eps && epsBasic) eps.value = epsBasic.value;
  }

  function bindInspectorTabs() {
    const tabs = Array.from(document.querySelectorAll("[data-inspector-tab]"));
    const panes = Array.from(document.querySelectorAll(".topology-inspector-pane"));
    if (!tabs.length || !panes.length) return;
    const activate = (name) => {
      if (name === "portsPanel" || name === "ioPortsPanel") name = "connectionsPanel";
      state.inspectorTab = name;
      tabs.forEach((tab) => tab.classList.toggle("active", tab.getAttribute("data-inspector-tab") === name));
      panes.forEach((pane) => pane.classList.toggle("active", pane.id === name));
      const nid = selectedNodeId();
      if (name === "connectionsPanel" && nid) renderNodeConnections(nid);
    };
    tabs.forEach((tab) => {
      tab.onclick = () => activate(tab.getAttribute("data-inspector-tab") || "basicInfoPanel");
    });
    activate(state.inspectorTab === "portsPanel" ? "connectionsPanel" : (state.inspectorTab || "basicInfoPanel"));
  }

  function bindLogTabs() {
    const tabs = Array.from(document.querySelectorAll("[data-log-tab]"));
    const panes = Array.from(document.querySelectorAll(".topology-log-pane"));
    tabs.forEach((tab) => {
      tab.onclick = () => {
        const id = tab.getAttribute("data-log-tab");
        tabs.forEach((it) => it.classList.toggle("active", it === tab));
        panes.forEach((pane) => pane.classList.toggle("active", pane.id === id));
      };
    });
  }

  function bindTopologyManagerTabs() {
    const tabs = Array.from(document.querySelectorAll("[data-topology-manager-tab]"));
    const panes = Array.from(document.querySelectorAll(".topology-manager-pane"));
    tabs.forEach((tab) => {
      tab.onclick = () => {
        const id = tab.getAttribute("data-topology-manager-tab");
        tabs.forEach((it) => it.classList.toggle("active", it === tab));
        panes.forEach((pane) => pane.classList.toggle("active", pane.id === id));
      };
    });
  }

  function agentServerHref(ag, aid, nodeId) {
    const agentId = String(aid || (ag && ag.agent_id) || "").trim();
    if (!agentId) return "";
    const nid = String(nodeId || "").trim();
    const boundService = nid ? String((state.serviceBindings || {})[nid] || "").trim() : "";
    let href = "/admin/projects/" + encodeURIComponent(state.projectId) + "/agent-detail?"
      + "&agent_id=" + encodeURIComponent(agentId)
      + "&tab=overview";
    if (boundService) href += "&service_id=" + encodeURIComponent(boundService);
    else if (nid) href += "&node_id=" + encodeURIComponent(nid);
    const deviceId = String((ag && ag.device_id) || "").trim();
    if (deviceId) href += "&preview=" + encodeURIComponent(deviceId);
    return href;
  }

  function redrawGraph() {
    drawEdgePaths();
    drawNodes();
    drawEdgeLabels();
  }

  function ensureEdgeMarkers() {
    const svg = $("edgeSvg");
    if (!svg) return;
    let defs = svg.querySelector("defs");
    if (!defs) {
      defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
      svg.appendChild(defs);
    }
    if (!defs.querySelector("#edge-arrow-marker")) {
      const marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
      marker.setAttribute("id", "edge-arrow-marker");
      marker.setAttribute("viewBox", "0 0 10 10");
      marker.setAttribute("refX", "10");
      marker.setAttribute("refY", "5");
      marker.setAttribute("markerWidth", "10");
      marker.setAttribute("markerHeight", "10");
      marker.setAttribute("markerUnits", "userSpaceOnUse");
      marker.setAttribute("orient", "auto");
      const head = document.createElementNS("http://www.w3.org/2000/svg", "path");
      head.setAttribute("d", "M 0 0 L 10 5 L 0 10 Z");
      head.setAttribute("fill", "#2563eb");
      marker.appendChild(head);
      defs.appendChild(marker);
    }
    if (!defs.querySelector("#edge-arrow-marker-live")) {
      const marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
      marker.setAttribute("id", "edge-arrow-marker-live");
      marker.setAttribute("viewBox", "0 0 10 10");
      marker.setAttribute("refX", "10");
      marker.setAttribute("refY", "5");
      marker.setAttribute("markerWidth", "10");
      marker.setAttribute("markerHeight", "10");
      marker.setAttribute("markerUnits", "userSpaceOnUse");
      marker.setAttribute("orient", "auto");
      const head = document.createElementNS("http://www.w3.org/2000/svg", "path");
      head.setAttribute("d", "M 0 0 L 10 5 L 0 10 Z");
      head.setAttribute("fill", "#52c41a");
      marker.appendChild(head);
      defs.appendChild(marker);
    }
    if (!defs.querySelector("#topology-live-flow-style")) {
      const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
      style.setAttribute("id", "topology-live-flow-style");
      style.textContent = ""
        + "@keyframes topology-edge-flow-svg { to { stroke-dashoffset: -40; } }"
        + ".live-flow { stroke: #22c55e !important; stroke-width: 3; stroke-dasharray: 14 10;"
        + " animation: topology-edge-flow-svg 0.9s linear infinite; filter: drop-shadow(0 0 2px rgba(34,197,94,.55)); }";
      defs.appendChild(style);
    }
  }

  function drawEdgePaths() {
    const svg = $("edgeSvg");
    if (!svg) return;
    svg.querySelectorAll(":scope > :not(defs)").forEach((el) => el.remove());
    ensureEdgeMarkers();
    const liveNodeIds = liveRunningNodeIdSet();
    let visible = 0;
    let skipped = 0;
    (state.topology.edges || []).forEach((edge) => {
      const d = edgePath(edge);
      if (!d) { skipped += 1; return; }
      visible += 1;
      const liveFlow = edgeIsLiveRunning(edge, liveNodeIds);
      const pathId = "edge-path-" + String(edge.id || "").replace(/[^a-zA-Z0-9_-]/g, "_");
      const hit = document.createElementNS("http://www.w3.org/2000/svg", "path");
      hit.setAttribute("d", d);
      hit.setAttribute("fill", "none");
      hit.setAttribute("class", "edge-hit");
      hit.onclick = (ev) => { ev.stopPropagation(); state.selection.edgeId = edge.id; state.selection.nodes.clear(); redrawGraph(); };
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("id", pathId);
      path.setAttribute("d", d);
      path.setAttribute("fill", "none");
      path.setAttribute("marker-end", liveFlow ? "url(#edge-arrow-marker-live)" : "url(#edge-arrow-marker)");
      const hl = state.highlight.edges.has(edge.id) ? " hl" : "";
      const segmentHl = isTestSegmentScope() && state.highlight.edges.size > 0;
      const dim = segmentHl && !state.highlight.edges.has(edge.id) ? " path-dim" : "";
      const flow = state.flowViz.edges.has(edge.id) ? " flow" : "";
      const fail = (state.flowViz.statusByNode[String(edge.to)] && ["FAILED", "TIMEOUT", "CANCELED"].includes(String(state.flowViz.statusByNode[String(edge.to)]).toUpperCase())) ? " fail" : "";
      path.setAttribute("class", "edge" + hl + dim + flow + fail + (liveFlow ? " live-flow" : "") + (state.selection.edgeId === edge.id ? " sel" : ""));
      const src = getNode(edge.from);
      if (!flow && !hl && !fail && !liveFlow) {
        path.style.stroke = isEditMode() ? "#2563eb" : roleColor(src && src.role);
      } else if (liveFlow) {
        path.style.stroke = "";
      }
      path.onclick = (ev) => { ev.stopPropagation(); state.selection.edgeId = edge.id; state.selection.nodes.clear(); redrawGraph(); };
      svg.appendChild(hit);
      svg.appendChild(path);
      if (liveFlow) {
        const particle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        particle.setAttribute("r", "4");
        particle.setAttribute("class", "edge-flow-particle");
        particle.setAttribute("fill", "#22c55e");
        const motion = document.createElementNS("http://www.w3.org/2000/svg", "animateMotion");
        motion.setAttribute("dur", "2s");
        motion.setAttribute("repeatCount", "indefinite");
        motion.setAttribute("path", d);
        particle.appendChild(motion);
        svg.appendChild(particle);
        const particle2 = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        particle2.setAttribute("r", "2.5");
        particle2.setAttribute("class", "edge-flow-particle edge-flow-particle-trail");
        particle2.setAttribute("fill", "#86efac");
        particle2.setAttribute("opacity", "0.85");
        const motion2 = document.createElementNS("http://www.w3.org/2000/svg", "animateMotion");
        motion2.setAttribute("dur", "2s");
        motion2.setAttribute("repeatCount", "indefinite");
        motion2.setAttribute("begin", "1s");
        motion2.setAttribute("path", d);
        particle2.appendChild(motion2);
        svg.appendChild(particle2);
      }
      const slots = edgeDecorSlots(edge);
      if (slots && isEditMode()) {
        const del = document.createElementNS("http://www.w3.org/2000/svg", "g");
        del.setAttribute("class", "edge-remove");
        del.setAttribute("transform", "translate(" + Math.round(slots.delete.x) + "," + Math.round(slots.delete.y) + ")");
        del.setAttribute("title", "删除连线");
        const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        c.setAttribute("r", "9");
        const minus = document.createElementNS("http://www.w3.org/2000/svg", "text");
        minus.setAttribute("text-anchor", "middle");
        minus.setAttribute("y", "4");
        minus.setAttribute("font-size", "14");
        minus.textContent = "−";
        del.appendChild(c);
        del.appendChild(minus);
        del.onclick = (ev) => { ev.stopPropagation(); confirmStructuredDeleteEdge(edge.id); };
        svg.appendChild(del);
      }
    });
    const sig = (state.topology.edges || []).map((e) => [e.id, e.from, e.from_port, e.to, e.to_port].join(":")).join("|");
    const drawSig = visible + "/" + skipped + "/" + sig;
    if (state.lastEdgeDrawSig !== drawSig) {
      state.lastEdgeDrawSig = drawSig;
      if (skipped) logMode("部分连线暂不可见，已按当前节点布局重新计算画布。", "warn");
    }
    const delBtn = $("btnDeleteEdgeInline");
    if (delBtn) delBtn.disabled = !state.selection.edgeId;
    const hint = $("edgeSelectionHint");
    if (hint) {
      hint.textContent = state.selection.edgeId ? ("已选中连线: " + state.selection.edgeId) : "未选中连线";
      hint.className = "state-pill " + (state.selection.edgeId ? "state-ok" : "state-info");
    }
    const nid = selectedNodeId();
    const connPane = $("connectionsPanel");
    if (nid && connPane && connPane.classList.contains("active")) renderNodeConnections(nid);
  }

