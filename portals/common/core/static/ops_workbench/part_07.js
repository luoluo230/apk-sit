  function firstEntryNodeId() {
    const nodes = state.topology.nodes || [];
    const entry = nodes.find((n) => String(n.kind || "").toLowerCase() === "entry");
    if (entry) return entry.id;
    const gateway = nodes.find((n) => ["gateway", "edge"].includes(String(n.role || "").toLowerCase()));
    return gateway ? gateway.id : ((nodes[0] || {}).id || "");
  }

  function linkOffset(edge) {
    const siblings = (state.topology.edges || [])
      .filter((e) => String(e.from) === String(edge.from) && String(e.to) === String(edge.to))
      .sort((a, b) => String(a.id || "").localeCompare(String(b.id || "")));
    const idx = Math.max(0, siblings.findIndex((e) => String(e.id) === String(edge.id)));
    return (idx - (siblings.length - 1) / 2) * 18;
  }

  function isDesignReferenceTopology() {
    const meta = (state.topology && state.topology.meta) || {};
    if (meta.runtime_topology || meta.cluster_source) return false;
    return String(meta.design_reference || "") === "v4";
  }

  function isRuntimeTopologyProject() {
    const meta = (state.topology && state.topology.meta) || {};
    if (meta.runtime_topology || meta.cluster_source) return true;
    return (state.topology.nodes || []).some((n) => String((n && n.id) || "").endsWith("-cn-1"));
  }

  function designDemoAgents() {
    return [{
      agent_id: "agent-01",
      display_name: "agent-01",
      probe_status: "PASS",
      status: "ONLINE",
      host_name: "10.0.1.15",
      port: 9501,
    }];
  }

  function effectiveAgents() {
    const rows = Array.isArray(state.agents) ? state.agents : [];
    if (rows.length) return rows;
    return isDesignReferenceTopology() ? designDemoAgents() : rows;
  }

  function applyDesignStructuredLayout() {
    if (!isDesignReferenceTopology() || !state.topology || !state.topology.meta) return;
    if (shouldPreserveTopologyLayoutOnLoad()) return;
    state.topology.meta.layout_locked = false;
    layoutStructuredGraph();
  }

  function fitGraphToViewport() {
    const nodes = (state.topology.nodes || []).filter((n) => !(n.ui || {}).list_only);
    if (!nodes.length) return;
    let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
    nodes.forEach((n) => {
      const ui = n.ui || {};
      minX = Math.min(minX, Number(ui.x || 0));
      minY = Math.min(minY, Number(ui.y || 0));
      maxX = Math.max(maxX, Number(ui.x || 0) + Number(ui.w || 240));
      maxY = Math.max(maxY, Number(ui.y || 0) + nodeRenderHeight(n));
    });
    const shell = $("canvasShell");
    if (!shell || !Number.isFinite(minX)) return;
    const pad = 72;
    const cw = shell.clientWidth || 960;
    const ch = shell.clientHeight || 520;
    const gw = Math.max(1, maxX - minX + pad * 2);
    const gh = Math.max(1, maxY - minY + pad * 2);
    const zoom = Math.min(1.1, Math.max(0.32, Math.min(cw / gw, ch / gh)));
    const x = Math.round((cw - gw * zoom) / 2 - (minX - pad) * zoom);
    const y = Math.round((ch - gh * zoom) / 2 - (minY - pad) * zoom);
    if (!state.topology.meta || typeof state.topology.meta !== "object") state.topology.meta = {};
    state.topology.meta.viewport = { x, y, zoom };
    renderScene();
  }

  function scheduleFitGraphToViewport() {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => fitGraphToViewport());
    });
  }

  function layoutStructuredGraph(options) {
    if (!state.topology || !Array.isArray(state.topology.nodes)) return;
    if (!state.topology.meta || typeof state.topology.meta !== "object") state.topology.meta = {};
    if (state.topology.meta.layout_locked && !(options && options.force)) return;
    state.topology.meta.layout_mode = "structured";
    const spacing = layoutSpacing();
    const rankGap = spacing.rank_gap;
    const rowGap = spacing.row_gap;
    const nodes = state.topology.nodes || [];
    const byId = {};
    nodes.forEach((n) => { if (n && n.id) byId[n.id] = n; });
    const out = graphOut();
    const entryId = firstEntryNodeId();
    const rank = {};
    if (entryId) {
      rank[entryId] = 0;
      const queue = [entryId];
      while (queue.length) {
        const cur = queue.shift();
        (out[cur] || []).forEach((next) => {
          const nextRank = (rank[cur] || 0) + 1;
          if (rank[next] == null || nextRank > rank[next]) {
            rank[next] = nextRank;
            queue.push(next);
          }
        });
      }
    }
    let maxRank = Object.keys(rank).reduce((m, k) => Math.max(m, rank[k] || 0), 0);
    nodes.forEach((n) => {
      if (rank[n.id] != null) return;
      const role = String(n.role || "").toLowerCase();
      const biz = nodes.find((x) => String(x.role || "").toLowerCase() === "business" && rank[x.id] != null);
      if (["database", "cache", "search", "mq"].includes(role) && biz) {
        rank[n.id] = (rank[biz.id] || 0) + 1;
        return;
      }
      maxRank += 1;
      rank[n.id] = maxRank;
    });
    const ranks = {};
    nodes.forEach((n) => {
      const r = rank[n.id] || 0;
      if (!ranks[r]) ranks[r] = [];
      ranks[r].push(n);
    });
    const roleOrder = ["gateway", "edge", "admin", "business", "scheduler", "pressure", "mq", "cache", "database", "search", "analytics"];
    const roleIndex = (role) => {
      const idx = roleOrder.indexOf(String(role || "").toLowerCase());
      return idx < 0 ? 99 : idx;
    };
    const startX = 96;
    const startY = 96;
    Object.keys(ranks).map(Number).sort((a, b) => a - b).forEach((r) => {
      const rows = ranks[r].sort((a, b) => {
        const rr = roleIndex(a.role) - roleIndex(b.role);
        if (rr !== 0) return rr;
        return String(a.id).localeCompare(String(b.id));
      });
      const totalH = Math.max(0, (rows.length - 1) * rowGap);
      const y0 = startY + Math.max(0, (360 - totalH) / 2);
      rows.forEach((n, i) => {
        if (!n.ui || typeof n.ui !== "object") n.ui = {};
        n.ui.w = Number(n.ui.w || 240);
        n.ui.h = nodeRenderHeight(n);
        n.ui.x = startX + r * rankGap;
        n.ui.y = y0 + i * rowGap;
        n.ui.rank = r;
        n.ui.order = i;
      });
    });
  }

  function structuredAnchor(node, side) {
    if (!node || !node.ui) return { x: 0, y: 0 };
    const w = Number(node.ui.w || 240);
    const h = nodeRenderHeight(node);
    const x0 = Number(node.ui.x || 0);
    const y0 = Number(node.ui.y || 0);
    const x = side === "out" ? x0 + w + 4 : x0 - 4;
    const y = y0 + h / 2;
    return { x, y };
  }

  function edgePath(edge) {
    const aNode = getNode(edge.from);
    const bNode = getNode(edge.to);
    if (!aNode || !bNode) return "";
    const a = structuredMode() ? structuredAnchor(aNode, "out") : portAnchor(aNode, "out", edge.from_port);
    const b = structuredMode() ? structuredAnchor(bNode, "in") : portAnchor(bNode, "in", edge.to_port);
    const offset = linkOffset(edge);
    const minGap = 96;
    const ax = Math.round(a.x);
    const ay = Math.round(a.y + offset);
    const bx = Math.round(b.x);
    const by = Math.round(b.y + offset);
    const midX = Math.round((ax + bx) / 2);
    const turnX = bx > ax ? Math.max(ax + minGap, midX) : ax + minGap;
    if (structuredMode()) {
      const approachGap = 24;
      const entryX = bx - approachGap;
      let pathD;
      if (Math.abs(by - ay) <= 2) {
        const stopX = bx > ax ? Math.max(ax + 12, Math.min(entryX, bx - 4)) : bx;
        pathD = "M " + ax + " " + ay + " H " + stopX + " H " + bx;
        edge.ui = Object.assign({}, edge.ui || {}, {
          route: [{ x: ax, y: ay }, { x: stopX, y: ay }, { x: bx, y: ay }],
        });
      } else {
        let vx = turnX;
        if (bx > ax) vx = Math.min(vx, entryX - 4);
        pathD = "M " + ax + " " + ay + " H " + vx + " V " + by + " H " + entryX + " H " + bx;
        edge.ui = Object.assign({}, edge.ui || {}, {
          route: [
            { x: ax, y: ay },
            { x: vx, y: ay },
            { x: vx, y: by },
            { x: entryX, y: by },
            { x: bx, y: by },
          ],
        });
      }
      return pathD;
    }
    return "M " + ax + " " + ay
      + " H " + turnX
      + " V " + by
      + " H " + bx;
  }

  function edgeMid(edge) {
    const aNode = getNode(edge.from);
    const bNode = getNode(edge.to);
    if (!aNode || !bNode) return null;
    const a = structuredMode() ? structuredAnchor(aNode, "out") : portAnchor(aNode, "out", edge.from_port);
    const b = structuredMode() ? structuredAnchor(bNode, "in") : portAnchor(bNode, "in", edge.to_port);
    const offset = linkOffset(edge);
    const ax = Math.round(a.x);
    const ay = Math.round(a.y + offset);
    const bx = Math.round(b.x);
    const by = Math.round(b.y + offset);
    const minGap = 96;
    const midX = Math.round((ax + bx) / 2);
    const turnX = bx > ax ? Math.max(ax + minGap, midX) : ax + minGap;
    if (structuredMode()) {
      const entryX = bx - 24;
      if (Math.abs(by - ay) <= 2) return { x: Math.round((ax + bx) / 2), y: ay, horizontal: true };
      return { x: Math.round((entryX + bx) / 2), y: by, horizontal: true };
    }
    const vertical = Math.abs(by - ay) > Math.abs(bx - ax);
    return { x: turnX, y: Math.round((ay + by) / 2), horizontal: !vertical };
  }

  function edgeDecorSlots(edge) {
    const gap = 14;
    const deleteR = 9;
    const labelH = 18;
    const route = (((edge || {}).ui || {}).route || []);
    if (structuredMode() && route.length >= 2) {
      let best = null;
      let bestLen = 0;
      for (let i = 0; i < route.length - 1; i += 1) {
        const a = route[i];
        const b = route[i + 1];
        if (!a || !b || Math.abs(Number(a.y) - Number(b.y)) > 2) continue;
        const len = Math.abs(Number(b.x) - Number(a.x));
        if (len > bestLen) {
          bestLen = len;
          best = { x: Math.round((Number(a.x) + Number(b.x)) / 2), y: Math.round(Number(a.y)), horizontal: true };
        }
      }
      if (best && bestLen >= 48) {
        return {
          delete: { x: best.x, y: best.y - gap - deleteR },
          label: { x: best.x, y: best.y + gap, h: labelH },
        };
      }
    }
    const m = edgeMid(edge);
    if (!m) return null;
    if (m.horizontal !== false) {
      return {
        delete: { x: m.x, y: m.y - gap - deleteR },
        label: { x: m.x, y: m.y + gap, h: labelH },
      };
    }
    return {
      delete: { x: m.x - gap - deleteR, y: m.y },
      label: { x: m.x + gap, y: m.y, h: labelH },
    };
  }

  function normalizeTopology() {
    const rawById = {};
    (state.nodesRaw || []).forEach((n) => {
      const id = String((n && n.id) || "");
      if (id) rawById[id] = n || {};
    });
    const ids = [];
    const seen = new Set();
    (state.topology.nodes || []).forEach((n) => {
      const id = String((n && n.id) || "");
      if (id && !seen.has(id)) {
        ids.push(id);
        seen.add(id);
      }
    });
    if (!ids.length) {
      (state.nodesRaw || []).forEach((n) => {
        const id = String((n && n.id) || "");
        if (id && !seen.has(id)) {
          ids.push(id);
          seen.add(id);
        }
      });
    }
    const old = {};
    (state.topology.nodes || []).forEach((n) => { if (n && n.id) old[String(n.id)] = n; });
    state.topology.nodes = ids.map((id, i) => {
      const raw = rawById[id] || {};
      const prev = old[id] || {};
      const role = String(prev.role || raw.role || "business");
      const kind = inferKind(role, prev.kind || raw.kind);
      const ui = prev.ui || {};
      const coords = nodeCoords(prev);
      return {
        id,
        name: String(prev.name || raw.name || id),
        role,
        kind,
        desc: String(prev.desc || raw.description || raw.desc || ""),
        bizStatus: String(prev.bizStatus || "normal"),
        owner: String(prev.owner || raw.owner || ""),
        group: String(prev.group || raw.group || ""),
        tags: Array.isArray(prev.tags) ? prev.tags : [],
        notes: String(prev.notes || ""),
        ui: {
          x: Number.isFinite(coords.x) ? coords.x : (90 + (i % 5) * 280),
          y: Number.isFinite(coords.y) ? coords.y : (100 + Math.floor(i / 5) * 170),
          w: Number(ui.w || 240),
          h: Number(ui.h || 96),
          color: String(ui.color || "#0f172a"),
          ports: normalizePorts(kind, ui.ports),
          list_only: (id === "db-01" && String(((state.topology && state.topology.meta) || {}).design_reference || "") === "v4")
            ? false
            : !!(ui.list_only || raw.list_only || (raw.ui && raw.ui.list_only)),
          locked: !!ui.locked,
          disabled: !!ui.disabled,
          remote: (ui.remote && typeof ui.remote === "object") ? ui.remote : {},
          network: (ui.network && typeof ui.network === "object") ? ui.network : {},
        },
      };
    });

    const valid = new Set(ids);
    state.topology.edges = (state.topology.edges || [])
      .filter((e) => e && valid.has(e.from) && valid.has(e.to) && e.from !== e.to)
      .map((e) => ({
        id: String(e.id || ("edge-" + Math.random().toString(16).slice(2, 10))),
        from: String(e.from),
        to: String(e.to),
        from_port: String(e.from_port || "out-1"),
        to_port: String(e.to_port || "in-1"),
        type: String(e.type || "depends_on"),
        note: String(e.note || ""),
        ui: (e.ui && typeof e.ui === "object") ? e.ui : {},
      }));
  }

  function renderScene() {
    const v = view();
    $("scene").style.transform = "translate(" + v.x + "px," + v.y + "px) scale(" + v.zoom + ")";
    if ($("zoomLabel")) $("zoomLabel").textContent = Math.round(v.zoom * 100) + "%";
    const shell = $("canvasShell");
    if (shell) shell.classList.toggle("grid-hidden", !state.showGrid);
    renderMiniMap();
  }

