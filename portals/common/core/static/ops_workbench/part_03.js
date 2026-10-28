  function nodeCoords(node) {
    const n = node || {};
    const ui = n.ui || {};
    const x = ui.x != null ? ui.x : n.x;
    const y = ui.y != null ? ui.y : n.y;
    return {
      x: Number(x != null && x !== "" ? x : 0),
      y: Number(y != null && y !== "" ? y : 0),
    };
  }

  function serverNodeToClient(sn, fallback) {
    const fb = fallback || {};
    const fbUi = fb.ui || {};
    const srvUi = (sn && sn.ui) || {};
    const coords = nodeCoords(sn && Object.keys(sn).length ? sn : fb);
    const role = String((sn && sn.role) || fb.role || "business");
    const kind = inferKind(role, (sn && sn.kind) || fb.kind);
    return {
      id: String((sn && sn.id) || fb.id || ""),
      name: String((sn && sn.name) || fb.name || ""),
      role,
      kind,
      desc: String((sn && sn.desc != null) ? sn.desc : (fb.desc || "")),
      bizStatus: String((sn && sn.bizStatus) || fb.bizStatus || "normal"),
      owner: String((sn && sn.owner) || fb.owner || ""),
      group: String((sn && sn.group) || fb.group || ""),
      tags: Array.isArray(sn && sn.tags) ? sn.tags : (Array.isArray(fb.tags) ? fb.tags : []),
      notes: String((sn && sn.notes) || fb.notes || ""),
      ui: {
        ...fbUi,
        ...srvUi,
        x: coords.x,
        y: coords.y,
        w: Number(srvUi.w || fbUi.w || 240),
        h: Number(srvUi.h || fbUi.h || 104),
        color: String(srvUi.color || fbUi.color || "#0f172a"),
        ports: normalizePorts(kind, srvUi.ports || fbUi.ports),
        remote: (srvUi.remote && typeof srvUi.remote === "object") ? srvUi.remote : (fbUi.remote || {}),
        network: (srvUi.network && typeof srvUi.network === "object") ? srvUi.network : (fbUi.network || {}),
        disabled: !!(srvUi.disabled != null ? srvUi.disabled : fbUi.disabled),
        locked: !!(srvUi.locked != null ? srvUi.locked : fbUi.locked),
        list_only: !!(srvUi.list_only != null ? srvUi.list_only : fbUi.list_only),
      },
    };
  }

  function mergeServerNode(nodeId, serverNodes) {
    const nid = String(nodeId || "").trim();
    if (!nid || !Array.isArray(serverNodes)) return false;
    const sn = serverNodes.find((x) => String((x || {}).id || "") === nid);
    if (!sn) return false;
    const idx = (state.topology.nodes || []).findIndex((n) => String(n.id) === nid);
    if (idx < 0) return false;
    state.topology.nodes[idx] = serverNodeToClient(sn, state.topology.nodes[idx]);
    return true;
  }
  function runtimeName(id) {
    const n = getNode(id);
    return String((n && (n.name || n.node_name || n.title || n.id)) || id || "-");
  }
  function roleLabel(role) {
    return ROLE_LABELS[String(role || "").toLowerCase()] || String(role || "未分类节点");
  }
  function ensureRoleOption(role) {
    const sel = $("insNodeRole");
    if (!sel || !role) return;
    const val = String(role).toLowerCase();
    if (Array.from(sel.options || []).some((op) => String(op.value) === val)) return;
    const op = document.createElement("option");
    op.value = val;
    op.textContent = roleLabel(val);
    sel.appendChild(op);
  }
  function semanticTypeLabel(node) {
    if (!node) return "standard";
    const kind = String(node.kind || "").toLowerCase();
    if (kind === "game") return "game";
    if (String(node.role || "").toLowerCase() === "business") return "game";
    if (kind) return kind;
    return inferKind(node.role, node.kind) || "standard";
  }
  function resolveIconRole(nodeOrRole) {
    if (nodeOrRole && typeof nodeOrRole === "object") {
      const role = String(nodeOrRole.role || "").toLowerCase();
      const id = String(nodeOrRole.id || "").toLowerCase();
      const name = String(nodeOrRole.name || "").toLowerCase();
      if (role === "auth" || id.includes("auth") || name.includes("auth") || name.includes("认证")) return "auth";
      if (role === "transport" || role === "tcp" || role === "edge" || id.includes("tcp") || id.includes("transport") || name.includes("tcp") || name.includes("传输")) return "transport";
      if (role === "gateway" || id.includes("gateway") || name.includes("gateway") || name.includes("网关")) return "gateway";
      if (role === "admin" || role === "ops" || id.includes("ops") || name.includes("ops") || name.includes("运维")) return "admin";
      if (role === "business" || role === "game" || id.includes("game") || name.includes("game") || name.includes("游戏")) return "business";
      if (role === "database" || role === "db" || id.includes("db") || id.includes("mongo") || name.includes("database")) return "database";
      if (role === "cache" || id.includes("cache") || id.includes("redis") || name.includes("cache") || name.includes("缓存")) return "cache";
      if (role === "mq" || id.includes("mq") || id.includes("kafka") || name.includes("消息")) return "mq";
      if (role === "scheduler" || id.includes("scheduler") || name.includes("调度")) return "scheduler";
      if (role === "pressure" || id.includes("pressure") || name.includes("压测")) return "pressure";
      if (role === "search" || id.includes("search") || name.includes("检索")) return "search";
      if (role === "analytics" || id.includes("analytics") || name.includes("分析")) return "analytics";
      return role || "business";
    }
    return String(nodeOrRole || "business").toLowerCase();
  }

  function roleIconSvg(role, opts) {
    const key = resolveIconRole(role);
    const tile = opts == null || opts.tile !== false;
    const icons = {
      gateway: tile
        ? '<rect x="4" y="4" width="16" height="16" rx="8" fill="currentColor" opacity=".14"/><circle cx="12" cy="12" r="6.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M3 12h18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M12 4.5c2.8 2.4 4.5 5.6 4.5 7.5S14.8 17.1 12 19.5 7.5 14.1 7.5 12 9.2 6.9 12 4.5z" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        : '<circle cx="12" cy="12" r="9"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>',
      auth: tile
        ? '<path d="M12 2.8l7.5 4.2v5.8c0 4.1-2.6 7.6-6.1 8.9a1.6 1.6 0 01-1.3 0C8.6 20.4 6 16.9 6 12.8V7l6-4.2z" fill="currentColor" opacity=".16"/><path d="M12 3l8 4v6c0 4.6-2.8 8.4-6.5 9.9a2 2 0 01-1 0C7.8 21.4 5 17.6 5 13V7l7-4z" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M9.5 12.2l2 2 3.8-4.2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        : '<path d="M12 3l8 4v6c0 4.6-2.8 8.4-6.5 9.9a2 2 0 01-1 0C7.8 21.4 5 17.6 5 13V7l7-4z"/><path d="M9 12l2 2 4-4"/>',
      business: tile
        ? '<rect x="5" y="8" width="14" height="9" rx="4" fill="currentColor" opacity=".16"/><path d="M8 12h3M10.5 10.5v3M15.5 12.5h.01M17.5 11h.01" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M9 8.5V7a3 3 0 016 0v1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="5" y="8" width="14" height="9" rx="4" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        : '<line x1="6" y1="12" x2="10" y2="12"/><line x1="8" y1="10" x2="8" y2="14"/><line x1="15" y1="13" x2="15.01" y2="13"/><line x1="18" y1="11" x2="18.01" y2="11"/><path d="M17.32 5H6.68a4 4 0 00-3.978 3.59A4.984 4.984 0 006 9v.01A7 7 0 106 9.29"/>',
      game: tile
        ? '<rect x="5" y="8" width="14" height="9" rx="4" fill="currentColor" opacity=".16"/><path d="M8 12h3M10.5 10.5v3M15.5 12.5h.01M17.5 11h.01" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M9 8.5V7a3 3 0 016 0v1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="5" y="8" width="14" height="9" rx="4" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        : '<line x1="6" y1="12" x2="10" y2="12"/><line x1="8" y1="10" x2="8" y2="14"/><line x1="15" y1="13" x2="15.01" y2="13"/><line x1="18" y1="11" x2="18.01" y2="11"/><path d="M17.32 5H6.68a4 4 0 00-3.978 3.59A4.984 4.984 0 006 9v.01A7 7 0 106 9.29"/>',
      admin: tile
        ? '<circle cx="12" cy="12" r="3.2" fill="currentColor"/><path d="M12 1.8v2.4M12 19.8v2.4M4.2 4.2l1.7 1.7M18.1 18.1l1.7 1.7M1.8 12h2.4M19.8 12h2.4M4.2 19.8l1.7-1.7M18.1 5.9l1.7-1.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'
        : '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9c.26.604.852.997 1.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>',
      ops: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9c.26.604.852.997 1.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>',
      transport: tile
        ? '<rect x="3" y="5" width="18" height="5.5" rx="1.5" fill="currentColor" opacity=".16"/><rect x="3" y="13" width="18" height="5.5" rx="1.5" fill="currentColor" opacity=".16"/><rect x="3" y="5" width="18" height="5.5" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="3" y="13" width="18" height="5.5" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="7" cy="7.8" r=".9" fill="currentColor"/><circle cx="7" cy="15.8" r=".9" fill="currentColor"/>'
        : '<rect x="2" y="3" width="20" height="7" rx="1.5"/><rect x="2" y="14" width="20" height="7" rx="1.5"/><path d="M6 6h.01M6 17h.01"/>',
      edge: '<rect x="2" y="3" width="20" height="7" rx="1.5"/><rect x="2" y="14" width="20" height="7" rx="1.5"/><path d="M6 6h.01M6 17h.01"/>',
      tcp: '<rect x="2" y="3" width="20" height="7" rx="1.5"/><rect x="2" y="14" width="20" height="7" rx="1.5"/><path d="M6 6h.01M6 17h.01"/>',
      database: tile
        ? '<ellipse cx="12" cy="7" rx="7" ry="2.8" fill="currentColor" opacity=".18"/><path d="M5 7v10c0 1.5 3.1 2.7 7 2.7s7-1.2 7-2.7V7" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M5 12c0 1.5 3.1 2.7 7 2.7s7-1.2 7-2.7" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        : '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.66 3.58 3 8 3s8-1.34 8-3V6"/><path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/>',
      cache: tile
        ? '<rect x="5" y="7" width="14" height="11" rx="2" fill="currentColor" opacity=".16"/><path d="M8 7V5h8v2" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="5" y="7" width="14" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8.5 12h7M8.5 15h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'
        : '<path d="M4 7h16v12H4z"/><path d="M8 7V4h8v3"/><path d="M8 11h8M8 15h5"/>',
      mq: tile
        ? '<rect x="4" y="6" width="16" height="5" rx="1.5" fill="currentColor" opacity=".16"/><rect x="4" y="14" width="12" height="5" rx="1.5" fill="currentColor" opacity=".16"/><rect x="4" y="6" width="16" height="5" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="4" y="14" width="12" height="5" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        : '<path d="M4 6h16v5H4z"/><path d="M4 15h12v5H4z"/><path d="M18 15h2v5h-2z"/>',
      search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
      scheduler: tile
        ? '<circle cx="12" cy="12" r="8" fill="currentColor" opacity=".14"/><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 7.5v4.8l3.2 1.8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'
        : '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
      pressure: '<path d="M4 19h16"/><path d="M7 15l3-4 3 3 4-6 3 4"/>',
      analytics: '<path d="M4 19h16"/><path d="M7 15V9M12 15V7M17 15v-5"/>',
    };
    const body = icons[key] || icons.business;
    if (tile) {
      return '<svg viewBox="0 0 24 24" aria-hidden="true">' + body + "</svg>";
    }
    const strokeAttrs = 'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"';
    return '<svg viewBox="0 0 24 24" ' + strokeAttrs + ' aria-hidden="true">' + body + "</svg>";
  }

  function roleBadge(nodeOrRole) {
    return roleIconSvg(nodeOrRole, { tile: true });
  }

  function iconAccent(nodeOrRole) {
    return nodeAccentColor(nodeOrRole);
  }
  function nodeDisplayTitle(node) {
    if (!node) return "-";
    const raw = String(node.name || node.title || node.id || "-").trim();
    const first = raw.split(/[-_]/)[0].toLowerCase();
    const alias = {
      gateway: "Gateway",
      auth: "Auth",
      game: "Game",
      business: "Game",
      ops: "Ops",
      tcp: "TCP Transport",
      transport: "TCP Transport",
      pressure: "Pressure",
      database: "DB",
      db: "DB",
      cache: "Cache",
      mq: "MQ",
      scheduler: "Scheduler",
      search: "Search",
    };
    if (alias[first]) return alias[first];
    return raw || "-";
  }
  function nodeSecondaryText(node) {
    if (!node) return "-";
    const desc = String(node.desc || "").trim();
    return desc || roleLabel(node.role);
  }
  function preferredNodeId() {
    const nodes = Array.isArray(state.topology.nodes) ? state.topology.nodes : [];
    if (!nodes.length) return "";
    const selected = Array.from(state.selection.nodes || [])[0];
    if (selected && nodes.some((node) => String(node.id) === String(selected))) return String(selected);
    const gameNode = nodes.find((node) => String(node.id) === "game-01");
    if (gameNode) return "game-01";
    const score = (node) => {
      const role = String((node || {}).role || "").toLowerCase();
      if (role === "business") return 100;
      if (role === "gateway") return 90;
      if (role === "admin") return 80;
      return 10;
    };
    return String(nodes.slice().sort((a, b) => score(b) - score(a))[0].id || "");
  }
  function rawNodeMeta(id) {
    const key = String(id || "");
    const raw = (state.nodesRaw || []).find((n) => String((n || {}).id || "") === key) || {};
    const topo = getNode(key) || {};
    return Object.assign({}, raw, topo, {
      role: String(topo.role || raw.role || ""),
      allowed_upstream_roles: Array.isArray(raw.allowed_upstream_roles) ? raw.allowed_upstream_roles : [],
      allowed_downstream_roles: Array.isArray(raw.allowed_downstream_roles) ? raw.allowed_downstream_roles : [],
    });
  }
  function runtimeById() { const m = {}; (state.overviewNodes || []).forEach((n) => { m[n.id] = n; }); return m; }
  function boundAgentForNode(nodeId) {
    const aid = String((state.nodeBindings || {})[String(nodeId || "")] || "");
    if (!aid) return null;
    return (state.agents || []).find((x) => String((x || {}).agent_id || "") === aid) || null;
  }
  function isEditMode() { return state.mode === "edit"; }
  function isRunMode() { return state.mode === "run"; }
  function isTestMode() { return state.mode === "test"; }

  function agentHeartbeatAgeSec(ag) {
    if (!ag || !ag.last_seen) return null;
    const d = new Date(String(ag.last_seen));
    if (Number.isNaN(d.getTime())) return null;
    return Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  }

  function deviceHeartbeatAgeSec(deviceId) {
    const did = String(deviceId || "");
    if (!did) return null;
    const rows = (state.agents || []).filter((x) => String((x || {}).device_id || "") === did);
    if (!rows.length) return null;
    let newest = null;
    rows.forEach((ag) => {
      const raw = String((ag || {}).last_seen || "");
      if (!raw) return;
      const t = new Date(raw).getTime();
      if (!Number.isFinite(t)) return;
      if (newest == null || t > newest) newest = t;
    });
    if (newest == null) return null;
    return Math.max(0, Math.round((Date.now() - newest) / 1000));
  }

  function agentHealthLabel(ag) {
    if (!ag) return { cls: "warn", text: "Agent未绑定" };
    const probe = String(ag.probe_status || "").toUpperCase();
    if (probe === "FAIL") return { cls: "err", text: "连通失败" };
    const st = String(ag.effective_status || ag.status || "").toUpperCase();
    const age = agentHeartbeatAgeSec(ag);
    const freshSec = 300;
    if (!Number.isFinite(age)) return { cls: "warn", text: "心跳未知" };
    if (st === "OFFLINE" || age > freshSec) return { cls: "err", text: "心跳过期 · " + age + "s" };
    if (probe === "PASS" || st === "ONLINE") return { cls: "ok", text: "探活正常 · " + age + "s" };
    return { cls: "warn", text: "待探活 · " + age + "s" };
  }

  function serviceRuntimeStatusForNode(ag, nodeId) {
    if (!ag || !nodeId) return null;
    const services = Array.isArray(ag.services) ? ag.services : [];
    const svc = services.find((s) => {
      const sid = String((s && s.service_id) || "");
      const nid = String((s && s.node_id) || "");
      const target = String(nodeId || "");
      return sid === target || nid === target;
    });
    if (!svc) return null;
    const probe = String(svc.probe_status || "").toUpperCase();
    const st = String(svc.run_state || svc.status || "").toUpperCase();
    if (probe === "FAIL" || st === "STOPPED" || st === "OFFLINE" || st === "FAILED") {
      return { text: "已停止", cls: "err" };
    }
    if (st === "STARTING" || st === "STOPPING" || st === "RESTARTING") {
      return { text: st === "STOPPING" ? "停止中" : "启动中", cls: "warn" };
    }
    if (probe === "PASS") {
      return { text: "运行中", cls: "ok" };
    }
    if (st === "RUNNING" || st === "ONLINE" || st === "READY") {
      return { text: "未知", cls: "warn" };
    }
    if (st === "UNKNOWN" || (!probe && !st)) return { text: "未知", cls: "warn" };
    return { text: "未知", cls: "warn" };
  }

  function nodeRuntimeStatus(n, ag, aid) {
    const st = String(n.bizStatus || "normal");
    if (!aid) {
      if (!state.bindingsHydrated && !state.agentsHydrated) return { text: "状态同步中", cls: "warn" };
      return { text: "未绑定", cls: "warn" };
    }
    if (!ag) {
      if (!state.agentsHydrated) return { text: "探活中", cls: "warn" };
      return { text: "Agent缺失", cls: "err" };
    }
    const perSvc = serviceRuntimeStatusForNode(ag, n.id);
    if (perSvc) return perSvc;
    const health = agentHealthLabel(ag);
    if (health.cls === "err") return { text: health.text.indexOf("连通") >= 0 ? "连通失败" : "离线", cls: "err" };
    if (health.cls === "warn") return { text: "未知", cls: "warn" };
    if (st === "offline" || st === "error") return { text: STATUS_LABELS[st] || "异常", cls: "err" };
    if (st === "degraded" || st === "observe") return { text: STATUS_LABELS[st] || st, cls: "warn" };
    return { text: "未知", cls: "warn" };
  }

  function resolveAgentForNode(n) {
    const aid = String((state.nodeBindings || {})[String((n && n.id) || "")] || "");
    if (aid) {
      return (state.agents || []).find((x) => String(x.agent_id || "") === aid) || null;
    }
    for (const ag of (state.agents || [])) {
      if (!ag || ag.stale) continue;
      const services = Array.isArray(ag.services) ? ag.services : [];
      if (services.some((s) => String((s && s.node_id) || (s && s.service_id) || "") === String((n && n.id) || ""))) {
        return ag;
      }
    }
    return null;
  }

  function isRuntimeVizMode() {
    return isRunMode() || isTestMode();
  }

  function nodeIsLiveRunning(n, ag, aid, runtimeStatus) {
    if (!isRuntimeVizMode()) return false;
    const rs = runtimeStatus || nodeRuntimeStatus(n, ag, aid);
    if (!rs || rs.cls !== "ok") return false;
    const flowSt = String((state.flowViz.statusByNode || {})[n.id] || "").toUpperCase();
    if (flowSt) {
      if (["FAILED", "TIMEOUT", "CANCELED", "OFFLINE", "ERROR"].includes(flowSt)) return false;
      if (["PENDING", "LEASED"].includes(flowSt)) return false;
    }
    return true;
  }

  function healthyRunningNodeIdSet() {
    const ids = new Set();
    (state.topology.nodes || []).forEach((n) => {
      if ((n.ui || {}).list_only) return;
      const ag = resolveAgentForNode(n);
      const aid = String((state.nodeBindings || {})[n.id] || (ag && ag.agent_id) || "");
      const rs = nodeRuntimeStatus(n, ag, aid);
      if (rs && rs.cls === "ok") ids.add(String(n.id));
    });
    return ids;
  }

  function clusterServicesRunning() {
    const nodes = (state.topology.nodes || []).filter((n) => !(n.ui || {}).list_only);
    if (!nodes.length) return false;
    const healthy = healthyRunningNodeIdSet();
    return healthy.size >= nodes.length;
  }

  function enforceLockedMode() {
    if (!state.lockedMode) return false;
    if (state.mode === state.lockedMode) return false;
    state.mode = state.lockedMode;
    return true;
  }

  function displayWorkbenchMode() {
    enforceLockedMode();
    return state.lockedMode || state.mode || "edit";
  }

