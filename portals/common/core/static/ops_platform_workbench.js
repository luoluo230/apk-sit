(function () {
  const ROLE_OPTIONS = ["gateway", "auth", "business", "pressure", "database", "cache", "mq", "search", "scheduler", "admin", "edge", "transport", "analytics"];
  const STATUS_OPTIONS = ["normal", "observe", "degraded", "error", "offline"];
  const STATUS_LABELS = { normal: "运行中", observe: "观察中", degraded: "降级中", error: "异常", offline: "离线" };
  const ROLE_LABELS = {
    gateway: "网关服务",
    auth: "认证服务",
    business: "游戏服务",
    pressure: "压测服务",
    database: "数据库",
    cache: "缓存服务",
    mq: "消息队列",
    search: "检索服务",
    scheduler: "调度服务",
    admin: "运维服务",
    edge: "边缘节点",
    transport: "传输服务",
    tcp: "TCP 传输",
    analytics: "数据分析",
  };
  const ROLE_BADGES = {
    gateway: "网",
    auth: "认",
    business: "游",
    pressure: "压",
    database: "库",
    cache: "缓",
    mq: "列",
    search: "搜",
    scheduler: "调",
    admin: "运",
    edge: "边",
    transport: "传",
    analytics: "析",
  };
  const ROLE_COLOR = {
    gateway: { border: "#1890ff", bg1: "#e6f7ff", bg2: "#ffffff", glow: "rgba(24,144,255,.18)" },
    auth: { border: "#52c41a", bg1: "#f6ffed", bg2: "#ffffff", glow: "rgba(82,196,26,.18)" },
    business: { border: "#722ed1", bg1: "#f9f0ff", bg2: "#ffffff", glow: "rgba(114,46,209,.18)" },
    game: { border: "#722ed1", bg1: "#f9f0ff", bg2: "#ffffff", glow: "rgba(114,46,209,.18)" },
    pressure: { border: "#faad14", bg1: "#fffbe6", bg2: "#ffffff", glow: "rgba(250,173,20,.18)" },
    database: { border: "#13c2c2", bg1: "#e6fffb", bg2: "#ffffff", glow: "rgba(19,194,194,.18)" },
    cache: { border: "#13c2c2", bg1: "#e6fffb", bg2: "#ffffff", glow: "rgba(19,194,194,.16)" },
    mq: { border: "#722ed1", bg1: "#f9f0ff", bg2: "#ffffff", glow: "rgba(114,46,209,.16)" },
    search: { border: "#fa8c16", bg1: "#fff7e6", bg2: "#ffffff", glow: "rgba(250,140,22,.16)" },
    scheduler: { border: "#597ef7", bg1: "#f0f5ff", bg2: "#ffffff", glow: "rgba(89,126,247,.16)" },
    admin: { border: "#faad14", bg1: "#fffbe6", bg2: "#ffffff", glow: "rgba(250,173,20,.18)" },
    ops: { border: "#faad14", bg1: "#fffbe6", bg2: "#ffffff", glow: "rgba(250,173,20,.18)" },
    edge: { border: "#ff4d4f", bg1: "#fff1f0", bg2: "#ffffff", glow: "rgba(255,77,79,.18)" },
    transport: { border: "#ff4d4f", bg1: "#fff1f0", bg2: "#ffffff", glow: "rgba(255,77,79,.18)" },
    analytics: { border: "#1890ff", bg1: "#e6f7ff", bg2: "#ffffff", glow: "rgba(24,144,255,.16)" },
  };
  const KINDS = ["entry", "standard", "terminal"];
  const LAYOUT_SPACING_DEFAULTS = { rank_gap: 268, row_gap: 128 };
  const LAYOUT_SPACING_LIMITS = {
    rank_gap: { min: 160, max: 480 },
    row_gap: { min: 80, max: 240 },
  };
  function clampLayoutSpacing(key, value) {
    const lim = LAYOUT_SPACING_LIMITS[key] || { min: 0, max: 9999 };
    const fallback = LAYOUT_SPACING_DEFAULTS[key] || lim.min;
    const num = Number(value);
    if (!Number.isFinite(num)) return fallback;
    return Math.max(lim.min, Math.min(lim.max, Math.round(num)));
  }

  function layoutSpacing() {
    const raw = (((state.topology || {}).meta || {}).layout_spacing) || {};
    return {
      rank_gap: clampLayoutSpacing("rank_gap", raw.rank_gap),
      row_gap: clampLayoutSpacing("row_gap", raw.row_gap),
    };
  }

  function hasSavedNodeLayout() {
    const nodes = ((state.topology || {}).nodes) || [];
    const visible = nodes.filter((n) => !(n.ui || {}).list_only);
    if (!visible.length) return false;
    return visible.every((n) => {
      const ui = n.ui || {};
      return Number.isFinite(Number(ui.x)) && Number.isFinite(Number(ui.y));
    });
  }

  function medianInt(values, fallback) {
    const nums = (values || []).map((v) => Number(v)).filter((v) => Number.isFinite(v) && v > 0);
    if (!nums.length) return fallback;
    nums.sort((a, b) => a - b);
    const mid = Math.floor(nums.length / 2);
    const val = nums.length % 2 ? nums[mid] : Math.round((nums[mid - 1] + nums[mid]) / 2);
    return Number.isFinite(val) && val > 0 ? val : fallback;
  }

  function inferLayoutSpacingFromNodes() {
    const nodes = (((state.topology || {}).nodes) || []).filter((n) => !(n.ui || {}).list_only);
    const byRank = {};
    nodes.forEach((n) => {
      const ui = n.ui || {};
      const rank = ui.rank != null && Number.isFinite(Number(ui.rank))
        ? Number(ui.rank)
        : Math.round((Number(ui.x || 0) - 96) / LAYOUT_SPACING_DEFAULTS.rank_gap);
      if (!byRank[rank]) byRank[rank] = [];
      byRank[rank].push(n);
    });
    const ranks = Object.keys(byRank).map(Number).sort((a, b) => a - b);
    const rankGaps = [];
    for (let i = 1; i < ranks.length; i += 1) {
      const prevX = Number((byRank[ranks[i - 1]][0].ui || {}).x);
      const curX = Number((byRank[ranks[i]][0].ui || {}).x);
      if (Number.isFinite(prevX) && Number.isFinite(curX)) rankGaps.push(curX - prevX);
    }
    const rowGaps = [];
    ranks.forEach((rank) => {
      const rows = byRank[rank].slice().sort((a, b) => Number((a.ui || {}).y) - Number((b.ui || {}).y));
      for (let i = 1; i < rows.length; i += 1) {
        const prevY = Number((rows[i - 1].ui || {}).y);
        const curY = Number((rows[i].ui || {}).y);
        if (Number.isFinite(prevY) && Number.isFinite(curY)) rowGaps.push(curY - prevY);
      }
    });
    return {
      rank_gap: clampLayoutSpacing("rank_gap", medianInt(rankGaps, LAYOUT_SPACING_DEFAULTS.rank_gap)),
      row_gap: clampLayoutSpacing("row_gap", medianInt(rowGaps, LAYOUT_SPACING_DEFAULTS.row_gap)),
    };
  }

  function syncLayoutSpacingFromTopology() {
    if (!state.topology.meta || typeof state.topology.meta !== "object") state.topology.meta = {};
    const meta = state.topology.meta;
    if (meta.layout_spacing && typeof meta.layout_spacing === "object") {
      meta.layout_spacing = {
        rank_gap: clampLayoutSpacing("rank_gap", meta.layout_spacing.rank_gap),
        row_gap: clampLayoutSpacing("row_gap", meta.layout_spacing.row_gap),
      };
      return;
    }
    if (hasSavedNodeLayout()) {
      meta.layout_spacing = inferLayoutSpacingFromNodes();
      return;
    }
    persistLayoutSpacingMeta(null);
  }

  function shouldPreserveTopologyLayoutOnLoad() {
    const meta = ((state.topology || {}).meta) || {};
    if (meta.layout_locked) return true;
    return hasSavedNodeLayout();
  }

  function syncLayoutSpacingControls() {
    const sp = layoutSpacing();
    const rankEl = $("layoutRankGapRange");
    const rowEl = $("layoutRowGapRange");
    const rankVal = $("layoutRankGapValue");
    const rowVal = $("layoutRowGapValue");
    const bar = document.querySelector(".topology-canvas-spacing-bar");
    const editable = isEditMode() && structuredMode();
    if (rankEl) {
      rankEl.value = String(sp.rank_gap);
      rankEl.disabled = !editable;
    }
    if (rowEl) {
      rowEl.value = String(sp.row_gap);
      rowEl.disabled = !editable;
    }
    if (rankVal) rankVal.textContent = String(sp.rank_gap);
    if (rowVal) rowVal.textContent = String(sp.row_gap);
    if (bar) bar.classList.toggle("is-disabled", !editable);
  }

  function persistLayoutSpacingMeta(patch) {
    if (!state.topology.meta || typeof state.topology.meta !== "object") state.topology.meta = {};
    const cur = layoutSpacing();
    state.topology.meta.layout_spacing = {
      rank_gap: clampLayoutSpacing("rank_gap", patch && patch.rank_gap != null ? patch.rank_gap : cur.rank_gap),
      row_gap: clampLayoutSpacing("row_gap", patch && patch.row_gap != null ? patch.row_gap : cur.row_gap),
    };
    if (patch && (patch.rank_gap != null || patch.row_gap != null)) {
      state.topology.meta.layout_spacing_customized = true;
    }
  }

  let layoutSpacingRelayoutTimer = null;

  function flushLayoutSpacingRelayout(opts) {
    if (layoutSpacingRelayoutTimer) {
      clearTimeout(layoutSpacingRelayoutTimer);
      layoutSpacingRelayoutTimer = null;
    }
    if (!isEditMode()) return;
    persistLayoutSpacingMeta(null);
    state.topology.meta.layout_locked = false;
    layoutStructuredGraph({ force: true });
    if (!(opts && opts.skipHistory)) pushHistory();
    redrawGraph();
    syncLayoutSpacingControls();
  }

  function queueLayoutSpacingRelayout(patch) {
    persistLayoutSpacingMeta(patch);
    if (layoutSpacingRelayoutTimer) clearTimeout(layoutSpacingRelayoutTimer);
    layoutSpacingRelayoutTimer = setTimeout(() => {
      layoutSpacingRelayoutTimer = null;
      if (!isEditMode()) return;
      state.topology.meta.layout_locked = false;
      layoutStructuredGraph({ force: true });
      pushHistory();
      redrawGraph();
      syncLayoutSpacingControls();
    }, 120);
  }

  function applyLayoutSpacing(patch, opts) {
    if (!isEditMode()) {
      toast("运行/测试模式不可调整节点间距", "warn");
      syncLayoutSpacingControls();
      return;
    }
    if (layoutSpacingRelayoutTimer) {
      clearTimeout(layoutSpacingRelayoutTimer);
      layoutSpacingRelayoutTimer = null;
    }
    persistLayoutSpacingMeta(patch || {});
    state.topology.meta.layout_locked = false;
    layoutStructuredGraph({ force: true });
    if (!(opts && opts.skipHistory)) pushHistory();
    redrawGraph();
    syncLayoutSpacingControls();
  }

  async function saveTopologyNow() {
    if (isTestMode()) {
      toast("测试模式禁止保存拓扑", "warn");
      return null;
    }
    flushLayoutSpacingRelayout({ skipHistory: true });
    syncLayoutSpacingFromTopology();
    if (hasSavedNodeLayout()) {
      state.topology.meta.layout_spacing_customized = true;
      state.topology.meta.layout_locked = true;
    }
    const d = await OpsApi.saveTopology(Object.assign(currentScope(), { topology: state.topology }));
    if (d && d.ok !== false && d.topology && d.topology.meta) {
      state.topology.meta = Object.assign({}, state.topology.meta || {}, d.topology.meta || {});
      syncLayoutSpacingControls();
    }
    return d;
  }

  function roleColor(role) {
    const key = String(role || "").toLowerCase();
    const p = ROLE_COLOR[key] || ROLE_COLOR.business || { border: "#3b82f6" };
    return p.border || "#3b82f6";
  }

  function hexRgb(hex) {
    const h = normalizeHexColor(hex, "#722ed1").slice(1);
    return {
      r: parseInt(h.slice(0, 2), 16),
      g: parseInt(h.slice(2, 4), 16),
      b: parseInt(h.slice(4, 6), 16),
    };
  }

  function nodeCustomColor(node) {
    const raw = String((node && node.ui && node.ui.color) || "").trim();
    if (!raw || !/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(raw)) return "";
    return normalizeHexColor(raw, "");
  }

  function nodePalette(node) {
    const roleKey = String((node && node.role) || "").toLowerCase();
    const fallback = ROLE_COLOR[roleKey] || ROLE_COLOR.business || { border: "#9ab6e5", bg1: "#ffffff", bg2: "#ffffff", glow: "rgba(37,99,235,.18)" };
    const custom = nodeCustomColor(node);
    if (!custom) return fallback;
    const { r, g, b } = hexRgb(custom);
    return {
      border: custom,
      bg1: "rgb(" + Math.round(r * 0.08 + 255 * 0.92) + "," + Math.round(g * 0.08 + 255 * 0.92) + "," + Math.round(b * 0.08 + 255 * 0.92) + ")",
      bg2: "#ffffff",
      glow: "rgba(" + r + "," + g + "," + b + ",0.18)",
    };
  }

  function nodeAccentColor(nodeOrRole) {
    if (nodeOrRole && typeof nodeOrRole === "object") {
      const custom = nodeCustomColor(nodeOrRole);
      if (custom) return custom;
      return roleColor(nodeOrRole.role);
    }
    return roleColor(nodeOrRole);
  }
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (s) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[s]));

  const state = {
    projectId: "",
    envKey: "",
    topologyId: "",
    topologies: [],
    topologyRegistry: null,
    nodesRaw: [],
    overviewNodes: [],
    topology: { nodes: [], edges: [], meta: { viewport: { x: 0, y: 0, zoom: 1 } } },
    presets: [],
    blueprints: [],
    activePresetId: "",
    presetCollapsed: {},
    selection: { nodes: new Set(), edgeId: "" },
    nodeBindings: {},
    serviceBindings: {},
    agents: [],
    drag: null,
    pan: null,
    spaceDown: false,
    structuredAddCtx: null,
    acceptanceStructuredAddFrom: "",
    mode: "edit",
    selectedPort: null,
    runtimeRunId: "",
    runtimePollTimer: null,
    runtimeLogSeen: new Set(),
    runtimeProgressSig: "",
    runtimeSteady: false,
    runtimeLastStatus: "",
    runtimeRequestedOp: "",
    debugSeq: 0,
    agentsRefreshAt: 0,
    agentsTickTimer: null,
    modeLocked: false,
    highlight: { nodes: new Set(), edges: new Set() },
    flowViz: {
      mode: "",
      nodes: new Set(),
      edges: new Set(),
      statusByNode: {},
      seed: 0,
      metricsByEdge: {},
      history: [],
      replayTimer: null,
    },
    inspectorTab: "basicInfoPanel",
    activeLeftTab: "tools",
    nodeLogs: {},
    services: [],
    history: { past: [], future: [], max: 40 },
    topologyManagerPage: 1,
    topologyManagerPageSize: 10,
    showGrid: true,
    sidebarCollapsed: false,
  };
  const MODE_STORAGE_KEY = "ops_topology_mode_v1";
  const RUNTIME_STORAGE_KEY = "ops_topology_runtime_v1";
  const ENV_LABELS = {
    development: "开发环境",
    testing: "测试环境",
    staging: "预发环境",
    production: "生产环境",
  };

  function currentScope(extra) {
    return Object.assign({
      project_id: state.projectId,
      env_key: state.envKey,
      topology_id: state.topologyId,
    }, extra || {});
  }

  function queryStringForScope(scope) {
    const s = scope || currentScope();
    const q = new URLSearchParams();
    if (s.project_id) q.set("project_id", s.project_id);
    if (s.env_key) q.set("env_key", s.env_key);
    if (s.topology_id) q.set("topology_id", s.topology_id);
    return q.toString();
  }

  function syncQueryString() {
    const qs = queryStringForScope();
    const next = window.location.pathname + (qs ? ("?" + qs) : "");
    window.history.replaceState({}, "", next);
  }

  function envLabel(key) {
    const k = String(key || "").trim().toLowerCase();
    return ENV_LABELS[k] || k || "未命名环境";
  }

  function envTagClass(key) {
    const k = String(key || "").trim().toLowerCase();
    if (k === "production") return "env-tag-production";
    if (k === "staging") return "env-tag-staging";
    if (k === "testing") return "env-tag-testing";
    return "env-tag-development";
  }

  function snapshotTopology() {
    try {
      return JSON.stringify(state.topology);
    } catch (_) {
      return "";
    }
  }

  function pushHistory() {
    const snap = snapshotTopology();
    if (!snap) return;
    const last = state.history.past.length ? state.history.past[state.history.past.length - 1] : "";
    if (last === snap) return;
    state.history.past.push(snap);
    if (state.history.past.length > state.history.max) state.history.past.shift();
    state.history.future = [];
    updateHistoryButtons();
  }

  function restoreTopologySnapshot(snap) {
    if (!snap) return;
    try {
      state.topology = JSON.parse(snap);
      normalizeTopology();
      layoutStructuredGraph();
      redrawGraph();
      renderRuntimeNodeList();
      fillTestNodeOptions();
    } catch (_) {}
  }

  function updateHistoryButtons() {
    const canUndo = state.history.past.length > 1;
    const canRedo = state.history.future.length > 0;
    ["toolUndo", "toolUndoInline", "canvasQuickUndo"].forEach((id) => {
      const el = $(id);
      if (el) el.disabled = !canUndo;
    });
    ["toolRedo", "toolRedoInline", "canvasQuickRedo"].forEach((id) => {
      const el = $(id);
      if (el) el.disabled = !canRedo;
    });
  }

  function undoTopology() {
    if (state.history.past.length <= 1) {
      toast("没有可撤销的操作", "warn");
      return;
    }
    const current = state.history.past.pop();
    state.history.future.unshift(current);
    const prev = state.history.past[state.history.past.length - 1];
    restoreTopologySnapshot(prev);
    updateHistoryButtons();
    logMode("已撤销上一步拓扑编辑", "info");
  }

  function redoTopology() {
    if (!state.history.future.length) {
      toast("没有可重做的操作", "warn");
      return;
    }
    const next = state.history.future.shift();
    state.history.past.push(next);
    restoreTopologySnapshot(next);
    updateHistoryButtons();
    logMode("已重做拓扑编辑", "info");
  }

  function alignNodesToGrid() {
    if (isTestMode()) { toast("测试模式禁止对齐", "warn"); return; }
    const grid = 20;
    (state.topology.nodes || []).forEach((n) => {
      if (!n.ui) n.ui = {};
      n.ui.x = Math.round((n.ui.x || 0) / grid) * grid;
      n.ui.y = Math.round((n.ui.y || 0) / grid) * grid;
    });
    pushHistory();
    redrawGraph();
    toast("节点已对齐到网格", "ok");
  }

  function toggleSidebar() {
    state.sidebarCollapsed = !state.sidebarCollapsed;
    const app = document.querySelector(".ops-topology-app");
    if (app) app.classList.toggle("sidebar-collapsed", state.sidebarCollapsed);
    const btn = document.querySelector(".topology-collapse-btn");
    if (btn) btn.textContent = state.sidebarCollapsed ? "展开菜单" : "收起菜单";
  }

  function updateCreateCharCounts() {
    const name = String((($("topologyCreateName") || {}).value || "")).length;
    const desc = String((($("topologyCreateDesc") || {}).value || "")).length;
    if ($("topologyCreateNameCount")) $("topologyCreateNameCount").textContent = name + "/50";
    if ($("topologyCreateDescCount")) $("topologyCreateDescCount").textContent = desc + "/200";
  }

  function exportCurrentLogs() {
    const activePane = document.querySelector(".topology-log-pane.active");
    const box = activePane ? activePane.querySelector(".mode-log, .mode-log-details") : null;
    const text = box ? box.innerText : "";
    const blob = new Blob([text || "（空日志）"], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "topology-logs-" + Date.now() + ".txt";
    a.click();
    URL.revokeObjectURL(a.href);
    toast("日志已导出", "ok");
  }

  function compactEdgeLabel(edge) {
    const note = String((edge && edge.note) || "").trim();
    if (note) return note;
    const fromNode = getNode(edge.from);
    const role = String((fromNode && fromNode.role) || "").toLowerCase();
    if (role === "tcp" || role === "transport") return "tcp:5501";
    const port = String(edge.from_port || "");
    const m = port.match(/(\d+)/);
    return "http:" + (m ? m[1] : "80");
  }

  function getTestScope() {
    const picked = document.querySelector('input[name="testScope"]:checked');
    return picked ? String(picked.value || "full") : "full";
  }

  function isTestSegmentScope() {
    return isTestMode() && getTestScope() === "segment";
  }

  function testNodeOptionLabel(node) {
    if (!node) return "-";
    const id = String(node.id || "").trim();
    const name = String(node.name || "").trim();
    if (!id) return name || "-";
    if (name && name !== id) return id + " · " + name;
    return id;
  }

  function setTestPathHint(message) {
    const hint = $("testPathHint");
    if (!hint) return;
    hint.textContent = String(message || "");
  }

  function syncTestScopeUI() {
    const showSegment = isTestSegmentScope();
    const segFields = $("testSegmentFields");
    if (segFields) segFields.classList.toggle("is-hidden", !showSegment);
    const shell = document.querySelector(".ops-topology-app");
    if (shell) shell.classList.toggle("test-scope-segment", showSegment);
    if (showSegment) {
      fillTestNodeOptions();
      computePathHighlight();
    } else if (isTestMode()) {
      setTestPathHint("");
      clearTestHighlight();
    }
  }

  function syncToolButtonsForMode() {
    const editable = isEditMode();
    ["toolConnect", "toolUndoInline", "toolRedoInline", "toolSaveInline", "btnApplyBlueprint", "btnAutoBindAgents"].forEach((id) => {
      const el = $(id);
      if (el) el.disabled = !editable;
    });
  }

  function logDeployment(message, level) {
    const box = $("deploymentLogMirror");
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
    while (box.childNodes.length > 300) box.removeChild(box.lastChild);
  }

  function setInspectorEmpty(empty) {
    const card = $("nodeInspectorCard");
    const body = $("inspectorBody");
    const emptyBox = $("inspectorEmptyState");
    const tabs = $("inspectorTabBar");
    const actions = card ? card.querySelectorAll(".topology-inspector-actions") : [];
    if (card) card.classList.toggle("is-empty", !!empty);
    if (body) body.classList.toggle("is-hidden", !!empty);
    if (emptyBox) emptyBox.classList.toggle("is-hidden", !empty);
    if (tabs) tabs.classList.toggle("is-hidden", !!empty);
    if (empty) {
      actions.forEach((el) => el.classList.add("is-hidden"));
    } else {
      refreshLeftPanelChrome(state.activeLeftTab || "tools");
    }
    const fields = body ? body.querySelectorAll("input, select, textarea, button") : [];
    fields.forEach((el) => { el.disabled = !!empty; });
  }

  function formatTime(value, withSeconds) {
    if (!value) return "-";
    const d = new Date(String(value));
    if (Number.isNaN(d.getTime())) return String(value);
    const pad = (n) => String(n).padStart(2, "0");
    const base = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
    return withSeconds ? base + ":" + pad(d.getSeconds()) : base;
  }

  function dbg(tag, payload) {
    state.debugSeq += 1;
    const body = payload ? " " + JSON.stringify(payload) : "";
    const line = "[DBG#" + state.debugSeq + "] " + tag + body;
    try { console.debug(line); } catch (_) {}
  }

  function toast(msg, type) {
    let n = $("opsToast");
    if (!n) {
      n = document.createElement("div");
      n.id = "opsToast";
      n.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:9999;padding:10px 12px;border-radius:10px;background:#0f172a;color:#e2e8f0;font-size:12px;box-shadow:0 10px 20px rgba(2,6,23,.25);opacity:0;transform:translateY(8px);transition:all .18s ease";
      document.body.appendChild(n);
    }
    n.style.background = type === "error" ? "#7f1d1d" : (type === "warn" ? "#78350f" : "#0f172a");
    n.textContent = String(msg || "");
    n.style.opacity = "1";
    n.style.transform = "translateY(0)";
    clearTimeout(n._t);
    n._t = setTimeout(() => {
      n.style.opacity = "0";
      n.style.transform = "translateY(8px)";
    }, 2200);
  }

  function view() { return ((state.topology.meta || {}).viewport || { x: 0, y: 0, zoom: 1 }); }
  function getNode(id) { return (state.topology.nodes || []).find((n) => n.id === id) || null; }

  function selectedNodeId() {
    const card = $("nodeInspectorCard");
    const fromCard = card ? String(card.getAttribute("data-selected-node-id") || "").trim() : "";
    if (fromCard) return fromCard;
    const fromIns = String((($("insNodeId") || {}).value || "")).trim();
    if (fromIns) return fromIns;
    const sel = Array.from(state.selection.nodes || []);
    return sel.length ? String(sel[0] || "").trim() : "";
  }

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
      if (role === "database" || role === "db" || id.includes("db") || id.includes("mongo") || id.includes("mysql") || name.includes("database")) return "database";
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
    const st = String(ag.status || "").toUpperCase();
    const age = agentHeartbeatAgeSec(ag);
    const freshSec = 300;
    if (!age && age !== 0) return { cls: "warn", text: "心跳未知" };
    if (st === "ONLINE" && age <= freshSec) return { cls: "ok", text: "设备在线 · " + age + "s" };
    return { cls: "err", text: "心跳过期 · " + age + "s" };
  }

  function saveModeState() {
    try { localStorage.setItem(MODE_STORAGE_KEY, JSON.stringify({ mode: state.mode, modeLocked: !!state.modeLocked, ts: Date.now() })); } catch (_) {}
  }

  function loadModeState() {
    try {
      const raw = localStorage.getItem(MODE_STORAGE_KEY);
      if (!raw) return;
      const obj = JSON.parse(raw);
      const mode = String((obj || {}).mode || "");
      if (["edit", "run", "test"].includes(mode)) state.mode = mode;
      state.modeLocked = !!((obj || {}).modeLocked);
    } catch (_) {}
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
      state.runtimeSteady = !!((obj || {}).runtimeSteady);
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

  function testLogStep(i, step) {
    const idx = i + 1;
    const nodeId = String((step && step.node_id) || "-");
    const ok = !!(step && step.ok);
    const msg = String((step && step.message) || "");
    const degraded = !!(step && step.degraded);
    const result = (step && step.result) || {};
    const latency = result.latency_ms != null ? result.latency_ms : "-";
    const status = result.status != null ? result.status : "-";
    const resultCode = result.result_code || "-";
    const traceId = result.trace_id || "-";
    logMode("[STEP " + idx + "] node=" + nodeId + " ok=" + ok + " degraded=" + degraded + " latency_ms=" + latency + " status=" + status + " code=" + resultCode);
    if (msg) logMode("         message=" + msg);
    if (traceId && traceId !== "-") logMode("         trace_id=" + traceId);
    if (result && result.data && typeof result.data === "object") {
      const keys = Object.keys(result.data).slice(0, 8).join(",");
      if (keys) logMode("         data_keys=" + keys);
    }
    if (!ok && result && (result.result_message || result.message)) {
      logMode("         error_detail=" + String(result.result_message || result.message), "error");
    }
    appendJsonDetail("STEP " + idx + " 原始响应", step || {});
  }

  function stopRuntimePolling() {
    if (state.runtimePollTimer) {
      clearInterval(state.runtimePollTimer);
      state.runtimePollTimer = null;
    }
  }

  function nodeSeed(id) {
    const s = String(id || "");
    let h = 0;
    for (let i = 0; i < s.length; i += 1) h = ((h << 5) - h) + s.charCodeAt(i);
    return Math.abs(h || 1);
  }

  function metricTriplet(nodeId, status) {
    const now = Date.now();
    const sd = nodeSeed(nodeId) + Math.floor(now / 1500) + (state.flowViz.seed || 0);
    const b = (n, m) => Math.max(6, Math.min(96, (n % m)));
    const risk = ["FAILED", "TIMEOUT", "CANCELED"].includes(String(status || "").toUpperCase()) ? 18 : 0;
    const cpu = b(sd * 7 + 31, 76) + risk;
    const mem = b(sd * 11 + 17, 70) + Math.floor(risk * 0.6);
    const qps = b(sd * 13 + 43, 66) + Math.floor(risk * 0.45);
    return { cpu, mem, qps };
  }

  function realMetricTriplet(nodeId) {
    const ag = boundAgentForNode(nodeId);
    const m = (ag && ag.metrics && typeof ag.metrics === "object") ? ag.metrics : null;
    if (!m) return null;
    const cpu = Number(m.cpu_percent);
    const mem = Number(m.mem_percent);
    const qps = Number(m.qps);
    const rtt = Number(m.rtt_ms);
    const hasAny = Number.isFinite(cpu) || Number.isFinite(mem) || Number.isFinite(qps) || Number.isFinite(rtt);
    if (!hasAny) return null;
    return {
      cpu: Number.isFinite(cpu) ? Math.max(0, Math.min(100, cpu)) : 0,
      mem: Number.isFinite(mem) ? Math.max(0, Math.min(100, mem)) : 0,
      qps: Number.isFinite(qps) ? Math.max(0, qps) : 0,
      rtt: Number.isFinite(rtt) ? Math.max(0, rtt) : 0,
      source: "real",
      updatedAt: String(m.updated_at || ""),
    };
  }

  function deviceMetricTriplet(deviceId) {
    const did = String(deviceId || "");
    if (!did) return null;
    const rows = (state.agents || []).filter((x) => String((x || {}).device_id || "") === did);
    if (!rows.length) return null;
    let latest = null;
    rows.forEach((ag) => {
      const m = (ag && ag.metrics && typeof ag.metrics === "object") ? ag.metrics : null;
      if (!m) return;
      const tRaw = String(m.updated_at || ag.last_seen || "");
      const t = new Date(tRaw).getTime();
      if (!Number.isFinite(t)) return;
      if (!latest || t > latest.t) latest = { t, m };
    });
    if (!latest || !latest.m) return null;
    const cpu = Number(latest.m.cpu_percent);
    const mem = Number(latest.m.mem_percent);
    const qps = Number(latest.m.qps);
    const rtt = Number(latest.m.rtt_ms);
    const hasAny = Number.isFinite(cpu) || Number.isFinite(mem) || Number.isFinite(qps) || Number.isFinite(rtt);
    if (!hasAny) return null;
    return {
      cpu: Number.isFinite(cpu) ? Math.max(0, Math.min(100, cpu)) : 0,
      mem: Number.isFinite(mem) ? Math.max(0, Math.min(100, mem)) : 0,
      qps: Number.isFinite(qps) ? Math.max(0, qps) : 0,
      rtt: Number.isFinite(rtt) ? Math.max(0, rtt) : 0,
    };
  }

  function nodeMetrics(nodeId, status) {
    const real = realMetricTriplet(nodeId);
    if (real) {
      const ag = boundAgentForNode(nodeId);
      const dev = deviceMetricTriplet((ag || {}).device_id);
      if (dev) {
        return {
          cpu: dev.cpu,
          mem: dev.mem,
          qps: dev.qps,
          rtt: dev.rtt,
          source: "real",
          updatedAt: real.updatedAt,
        };
      }
      return real;
    }
    return { cpu: 0, mem: 0, qps: 0, rtt: 0, source: "missing", updatedAt: "" };
  }

  async function refreshAgentsIfNeeded(force) {
    const d = await OpsApi.agents(state.projectId);
    if (d && d.ok === false && (d.error_code === 'OPS_AUTH_REQUIRED' || d.error === 'auth_redirect')) {
      window.location.href = '/login';
      return;
    }
    if (d && d.ok !== false && Array.isArray(d.agents)) {
      state.agents = d.agents;
      state.agentsRefreshAt = Date.now();
    }
  }

  function startAgentsRealtimeTick() {
    if (state.agentsTickTimer) clearInterval(state.agentsTickTimer);
    state.agentsTickTimer = setInterval(async () => {
      await refreshAgentsIfNeeded(false);
      redrawGraph();
    }, 2000);
  }

  function syncFlowViz(mode, nodeIds, statusByNode) {
    const nset = new Set((nodeIds || []).filter(Boolean));
    const eset = new Set();
    (state.topology.edges || []).forEach((e) => {
      if (nset.has(e.from) && nset.has(e.to)) eset.add(e.id);
    });
    state.flowViz.mode = mode || "";
    state.flowViz.nodes = nset;
    state.flowViz.edges = eset;
    state.flowViz.statusByNode = statusByNode || {};
    state.flowViz.seed = Date.now();
  }

  function clearFlowViz(force, reason) {
    dbg("clearFlowViz", { force: !!force, reason: reason || "", mode: state.mode, runtimeSteady: !!state.runtimeSteady });
    if (!force && state.mode === "run" && state.runtimeSteady) {
      logMode("已忽略一次可视化清理请求（运行态保护中）", "warn");
      return;
    }
    if (state.flowViz.replayTimer) {
      clearInterval(state.flowViz.replayTimer);
      state.flowViz.replayTimer = null;
    }
    state.flowViz.mode = "";
    state.flowViz.nodes = new Set();
    state.flowViz.edges = new Set();
    state.flowViz.statusByNode = {};
    state.flowViz.metricsByEdge = {};
    state.flowViz.history = [];
  }

  function edgeMetrics(edgeId, status) {
    const edge = (state.topology.edges || []).find((e) => String(e.id) === String(edgeId));
    if (edge) {
      const fm = nodeMetrics(edge.from, status);
      const tm = nodeMetrics(edge.to, status);
      const hasReal = fm.source === "real" || tm.source === "real";
      if (hasReal) {
        const qps = Math.max(0, Math.round((Number(fm.qps || 0) + Number(tm.qps || 0)) / (tm.qps ? 2 : 1)));
        const latency = Math.max(1, Math.round((Number(fm.rtt || 0) + Number(tm.rtt || 0)) / ((fm.rtt || tm.rtt) ? 2 : 1)));
        const fail = ["FAILED", "TIMEOUT", "CANCELED"].includes(String(status || "").toUpperCase());
        return { tps: qps || 0, latency: latency || 0, err: fail ? 12 : 0, source: "real" };
      }
    }
    return null;
  }

  function pushFlowSnapshot() {
    const snap = {
      ts: Date.now(),
      mode: state.flowViz.mode,
      nodes: Array.from(state.flowViz.nodes || []),
      edges: Array.from(state.flowViz.edges || []),
      statusByNode: Object.assign({}, state.flowViz.statusByNode || {}),
      metricsByEdge: Object.assign({}, state.flowViz.metricsByEdge || {}),
    };
    const h = state.flowViz.history || [];
    h.push(snap);
    const minTs = Date.now() - 10000;
    state.flowViz.history = h.filter((x) => x && x.ts >= minTs).slice(-80);
  }

  function replayFailureFlow() {
    const h = (state.flowViz.history || []).slice(-80);
    if (!h.length) return;
    const minTs = Date.now() - 10000;
    const frames = h.filter((x) => x.ts >= minTs);
    if (!frames.length) return;
    if (state.flowViz.replayTimer) clearInterval(state.flowViz.replayTimer);
    let i = 0;
    logMode("失败回放开始（最近10秒链路）", "warn");
    state.flowViz.replayTimer = setInterval(() => {
      const f = frames[i];
      if (!f) return;
      state.flowViz.mode = f.mode || "run";
      state.flowViz.nodes = new Set(f.nodes || []);
      state.flowViz.edges = new Set(f.edges || []);
      state.flowViz.statusByNode = Object.assign({}, f.statusByNode || {});
      state.flowViz.metricsByEdge = Object.assign({}, f.metricsByEdge || {});
      redrawGraph();
      i += 1;
      if (i >= frames.length) {
        clearInterval(state.flowViz.replayTimer);
        state.flowViz.replayTimer = null;
        logMode("失败回放结束", "warn");
      }
    }, 180);
  }

  function appendRuntimeLogs(logs) {
    (logs || []).forEach((row) => {
      if (!row || typeof row !== "object") return;
      const sig = [row.ts || "", row.node_id || "", row.job_id || "", row.message || ""].join("|");
      if (state.runtimeLogSeen.has(sig)) return;
      state.runtimeLogSeen.add(sig);
      const level = String(row.level || "").toLowerCase();
      logMode(String(row.message || ""), level === "error" ? "error" : (level === "warn" ? "warn" : ""));
    });
  }

  function clearDesignDemoLogs(box) {
    if (!box) return;
    box.querySelectorAll("[data-design-demo], [data-test-design-demo], [data-nodes-design-demo]").forEach((el) => el.remove());
  }

  function clearAllDesignDemoLogs() {
    clearDesignDemoLogs($("modeLog"));
    clearDesignDemoLogs($("modeLogDetails"));
  }

  function appendDemoLogLines(box, rows, attr, levelLabel) {
    if (!box) return;
    const tag = levelLabel || "【信息】";
    rows.forEach((row) => {
      const line = document.createElement("div");
      line.className = "mode-log-line info";
      line.setAttribute(attr, "1");
      line.innerHTML = '<span class="mode-log-icon" aria-hidden="true"></span>'
        + '<span class="mode-log-time">' + esc(row.t) + '</span>'
        + ' <span class="mode-log-level">' + esc(tag) + '</span>'
        + esc(row.msg);
      box.prepend(line);
    });
  }

  function activateDesignLogTab(paneId) {
    const visibleSet = document.querySelector(".topology-log-tabs:not(.is-hidden)");
    if (!visibleSet) return;
    visibleSet.querySelectorAll("[data-log-tab]").forEach((tab) => {
      const on = tab.getAttribute("data-log-tab") === paneId;
      tab.classList.toggle("active", on);
    });
    document.querySelectorAll(".topology-log-pane").forEach((pane) => {
      pane.classList.toggle("active", pane.id === paneId);
    });
  }

  function seedDesignDemoLogs() {
    const box = $("modeLog");
    if (!box || box.querySelector("[data-design-demo]")) return;
    appendDemoLogLines(box, [
      { t: "11:14:12", msg: "拓扑“生产环境”已加载完成，版本：v2.3.1" },
      { t: "11:13:58", msg: "节点 Game(game-01) 与 Ops(ops-01) 连接已更新 (tcp:5512)" },
      { t: "11:13:46", msg: "节点 Auth(auth-01) 与 Game(game-01) 连接已建立 (tcp:5501)" },
      { t: "11:13:35", msg: "自动布局完成，共 5 个节点，6 条连线" },
      { t: "11:13:20", msg: "拓扑“生产环境”保存成功" },
      { t: "11:13:05", msg: "拓扑“生产环境”已打开" },
    ], "data-design-demo", "【信息】");
  }

  function seedNodesDesignLogs() {
    const box = $("modeLogDetails");
    if (!box) return;
    clearAllDesignDemoLogs();
    appendDemoLogLines(box, [
      { t: "11:14:12", msg: "拓扑“生产环境主拓扑”已加载完成，版本：v2.3.1" },
      { t: "11:13:58", msg: "节点 Game(game-01) 与 Ops(ops-01) 连接已建立 (tcp:5512)" },
      { t: "11:13:46", msg: "节点 Auth(auth-01) 与 Game(game-01) 连接已建立 (tcp:5501)" },
      { t: "11:13:35", msg: "拓扑启动成功，共 6 个节点，6 条连线" },
      { t: "11:13:20", msg: "拓扑“生产环境主拓扑”保存成功" },
      { t: "11:13:05", msg: "拓扑“生产环境主拓扑”已打开" },
    ], "data-nodes-design-demo", "[信息]");
  }

  function seedTestModeDesignLogs() {
    const box = $("modeLog");
    if (!box) return;
    clearAllDesignDemoLogs();
    appendDemoLogLines(box, [
      { t: "15:30:15", msg: "开始测试：范围 完整架构，起点 Gateway，终点 TCP Transport" },
      { t: "15:30:16", msg: "节点 Auth(auth-01) 连接已建立 (tcp:5501)" },
      { t: "15:30:18", msg: "节点 Game(game-01) 连接已建立 (tcp:5512)" },
      { t: "15:30:21", msg: "开始执行单元测试：Gateway -> Auth -> Game -> TCP Transport" },
      { t: "15:30:28", msg: "单元测试通过，耗时 7.32 秒" },
      { t: "15:30:35", msg: "开始压力测试：并发 100，持续 60 秒" },
      { t: "15:31:05", msg: "压力测试完成，成功率 100%，平均响应 38ms，P95 82ms" },
    ], "data-test-design-demo", "[信息]");
  }

  function refreshLogDemoForChrome() {
    const leftTab = state.activeLeftTab || "tools";
    if (leftTab === "nodes") {
      activateDesignLogTab("modeLogDetailsPane");
      seedNodesDesignLogs();
      return;
    }
    if (leftTab === "mode" && state.mode === "test") {
      activateDesignLogTab("modeLogPane");
      seedTestModeDesignLogs();
      return;
    }
    activateDesignLogTab("modeLogPane");
    clearAllDesignDemoLogs();
    seedDesignDemoLogs();
  }

  function nodeDesignDesc(node, layout) {
    if (!node) return "";
    if (layout === "nodes" && String(node.id) === "game-01") {
      return "提供核心游戏逻辑服务，处理玩家会话与游戏逻辑。";
    }
    return node.desc || "";
  }

  function seedTestModeRuntimeDemo() {
    if (state.mode !== "test" || state.runtimePollTimer) return;
    updateRuntimeSummary({
      run_id: "run_20250608_153015",
      started_at: "2025-06-08T15:30:15",
      duration_human: "00:12:48",
      total: 19,
      done: 12,
      running: 5,
      success: 12,
      warn: 0,
      failed: 0,
      progress_pct: 63,
    });
    if ($("runtimeStatusPill")) {
      $("runtimeStatusPill").textContent = "运行中";
      $("runtimeStatusPill").className = "state-pill state-ok";
    }
  }

  function updateRuntimeSummary(snapshot) {
    const data = snapshot || {};
    const total = Number(data.total || 0);
    const done = Number(data.done || 0);
    const running = Number(data.running || 0);
    const success = Number(data.success || 0);
    const failed = Number(data.failed || 0);
    const warn = Number(data.warn || 0);
    const pct = Number.isFinite(Number(data.progress_pct))
      ? Math.max(0, Math.min(100, Math.round(Number(data.progress_pct))))
      : (total > 0 ? Math.max(0, Math.min(100, Math.round((done / total) * 100))) : 0);
    if ($("runtimeRunIdValue")) $("runtimeRunIdValue").textContent = String(data.run_id || state.runtimeRunId || "-");
    if ($("runtimeStartedAtValue")) $("runtimeStartedAtValue").textContent = formatTime(data.started_at || data.created_at || "", true);
    if ($("runtimeDurationValue")) $("runtimeDurationValue").textContent = String(data.duration_human || data.duration || "-");
    if ($("runtimeProgressValue")) $("runtimeProgressValue").textContent = pct + "%";
    if ($("runtimeProgressBar")) $("runtimeProgressBar").style.width = pct + "%";
    if ($("runtimeRunningCount")) $("runtimeRunningCount").textContent = String(running);
    if ($("runtimeSuccessCount")) $("runtimeSuccessCount").textContent = String(success);
    if ($("runtimeWarnCount")) $("runtimeWarnCount").textContent = String(warn);
    if ($("runtimeFailedCount")) $("runtimeFailedCount").textContent = String(failed);
  }

  async function pollRuntimeRun(runId) {
    if (!runId) return;
    await refreshAgentsIfNeeded(false);
    const d = await OpsApi.runtimeFlowStatus(runId);
    if (!d || d.ok === false) {
      logMode("运行状态拉取失败: " + ((d && (d.message || d.error)) || "未知错误"), "error");
      stopRuntimePolling();
      return;
    }
    appendRuntimeLogs(d.logs || []);
    if (d.debug && typeof d.debug === "object") {
      dbg("runtime-debug", d.debug);
    }
    const statusByNode = {};
    const activeNodes = [];
    (d.items || []).forEach((it) => {
      const nid = String((it && it.node_id) || "");
      const st = String((it && it.status) || "PENDING").toUpperCase();
      if (!nid) return;
      statusByNode[nid] = st;
      if (["PENDING", "LEASED", "RUNNING", "SUCCESS", "FAILED", "TIMEOUT", "CANCELED"].includes(st)) activeNodes.push(nid);
    });
    const metricsByEdge = {};
    (state.topology.edges || []).forEach((e) => {
      if (!activeNodes.includes(e.from) || !activeNodes.includes(e.to)) return;
      const toSt = statusByNode[String(e.to)] || "";
      metricsByEdge[e.id] = edgeMetrics(e.id, toSt);
    });
    syncFlowViz("run", activeNodes, statusByNode);
    state.flowViz.metricsByEdge = metricsByEdge;
    pushFlowSnapshot();
    updateRuntimeSummary(d);
    redrawGraph();
    renderRuntimeNodeList();
    const curNid = String((($("insNodeId") || {}).value || "")).trim();
    if (curNid) renderMonitorPanel(curNid);
    const total = Number(d.total || 0);
    const done = Number(d.done || 0);
    if (total > 0) {
      const sig = done + "/" + total + "/" + Number(d.failed || 0);
      if (sig !== state.runtimeProgressSig) {
        state.runtimeProgressSig = sig;
        logMode("运行进度: " + done + "/" + total + "，失败 " + Number(d.failed || 0));
      }
    }
    const st = String(d.status || "").toLowerCase();
    const op = String(d.op || "").toLowerCase();
    const effectiveOp = op || String(state.runtimeRequestedOp || "").toLowerCase() || "start";
    if (state.runtimeLastStatus !== st) {
      dbg("runtime-status-transition", { from: state.runtimeLastStatus || "-", to: st, op, effectiveOp, done: Number(d.done || 0), total: Number(d.total || 0), failed: Number(d.failed || 0) });
      state.runtimeLastStatus = st;
    }
    if (st === "success" || st === "failed") {
      stopRuntimePolling();
      const ok = st === "success";
      toast(ok ? "全流程执行完成" : "全流程执行结束（含失败）", ok ? "ok" : "warn");
      logMode("运行结束: " + st.toUpperCase(), ok ? "" : "warn");
      if (!ok) {
        replayFailureFlow();
        setTimeout(() => {
          clearFlowViz(true, "pollRuntimeRun-failed-finalize");
          redrawGraph();
        }, 2200);
        return;
      }
      if (effectiveOp === "start") {
        state.runtimeSteady = true;
        const steadyNodes = activeNodes.length ? activeNodes : (state.topology.nodes || []).map((n) => n.id);
        const steadyStatus = {};
        steadyNodes.forEach((nid) => { steadyStatus[String(nid)] = "RUNNING"; });
        syncFlowViz("run", steadyNodes, steadyStatus);
        const steadyMetrics = {};
        (state.topology.edges || []).forEach((e) => {
          if (steadyNodes.includes(e.from) && steadyNodes.includes(e.to)) steadyMetrics[e.id] = edgeMetrics(e.id, "RUNNING");
        });
        state.flowViz.metricsByEdge = steadyMetrics;
        redrawGraph();
        dbg("runtime-steady-on", { runId, activeNodes: steadyNodes.length });
        logMode("启动成功，已进入持续运行态可视化（直到手动停止）");
        saveRuntimeState();
        return;
      }
      setTimeout(() => {
        clearFlowViz(true, "pollRuntimeRun-stop-success");
        redrawGraph();
      }, 1200);
      state.runtimeSteady = false;
      saveRuntimeState();
    }
  }

  function inferKind(role, current) {
    const c = String(current || "").toLowerCase();
    if (c === "game") return "standard";
    if (KINDS.includes(c)) return c;
    const r = String(role || "").toLowerCase();
    if (["gateway", "edge"].includes(r)) return "entry";
    if (["database", "cache", "mq", "search", "transport"].includes(r)) return "terminal";
    return "standard";
  }

  function defaultPorts(kind) {
    if (kind === "entry") return { in: [], out: [{ id: "out-1", label: "out-1", kind: "out", max_links: 1 }] };
    if (kind === "terminal") return { in: [{ id: "in-1", label: "in-1", kind: "in", max_links: 1 }], out: [] };
    return {
      in: [{ id: "in-1", label: "in-1", kind: "in", max_links: 1 }],
      out: [{ id: "out-1", label: "out-1", kind: "out", max_links: 1 }],
    };
  }

  function normalizePorts(kind, ports) {
    const base = defaultPorts(kind);
    if (!ports || typeof ports !== "object") return base;
    const out = { in: [], out: [] };
    ["in", "out"].forEach((side) => {
      const rows = Array.isArray(ports[side]) ? ports[side] : [];
      rows.forEach((p, i) => {
        const id = String((p && p.id) || (side + "-" + (i + 1)));
        out[side].push({
          id,
          label: String((p && p.label) || id),
          kind: side,
          max_links: 1,
          required: !!(p && p.required),
        });
      });
    });
    if (kind === "entry") { out.in = []; if (!out.out.length) out.out = base.out; }
    if (kind === "terminal") { out.out = []; if (!out.in.length) out.in = base.in; }
    if (kind === "standard") { if (!out.in.length) out.in = base.in; if (!out.out.length) out.out = base.out; }
    return out;
  }

  function countLinks(nodeId, side, portId) {
    return (state.topology.edges || []).filter((e) => side === "in"
      ? (e.to === nodeId && String(e.to_port) === String(portId))
      : (e.from === nodeId && String(e.from_port) === String(portId))).length;
  }

  function world(clientX, clientY) {
    const r = $("canvasShell").getBoundingClientRect();
    const v = view();
    return { x: (clientX - r.left - v.x) / v.zoom, y: (clientY - r.top - v.y) / v.zoom };
  }

  function centerWorld() {
    const r = $("canvasShell").getBoundingClientRect();
    return world(r.left + r.width / 2, r.top + r.height / 2);
  }

  function portAnchor(node, side, portId) {
    const ports = (((node.ui || {}).ports || {})[side] || []);
    const idx = Math.max(0, ports.findIndex((p) => String(p.id) === String(portId)));
    const rowGap = 24;
    const topPad = 10;
    const dotRadius = 6;
    const y = Number(node.ui.y || 0) + topPad + dotRadius + idx * rowGap;
    return side === "out" ? { x: node.ui.x + node.ui.w, y } : { x: node.ui.x, y };
  }

  function cssEsc(value) {
    if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(String(value || ""));
    return String(value || "").replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  }

  function structuredMode() {
    return true;
  }

  function graphOut() {
    const out = {};
    (state.topology.nodes || []).forEach((n) => {
      if (n && n.id) out[n.id] = out[n.id] || [];
    });
    (state.topology.edges || []).forEach((e) => {
      if (!e || !e.from || !e.to) return;
      if (!out[e.from]) out[e.from] = [];
      if (!out[e.from].includes(e.to)) out[e.from].push(e.to);
    });
    return out;
  }

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
    return String(meta.design_reference || "") === "v4";
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
      maxY = Math.max(maxY, Number(ui.y || 0) + Number(ui.h || 104));
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
        n.ui.h = Number(n.ui.h || 104);
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
    const h = Number(node.ui.h || 104);
    const x0 = Number(node.ui.x || 0);
    const y0 = Number(node.ui.y || 0);
    const x = side === "out" ? x0 + w + 4 : x0;
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
    const m = edgeMid(edge);
    if (!m) return null;
    const gap = 14;
    const deleteR = 9;
    const labelH = 18;
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

  function renderMiniMap() {
    const canvas = $("topologyMiniMap");
    const shell = $("canvasShell");
    if (!canvas || !shell) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, w, h);
    const nodes = (state.topology.nodes || []).filter((n) => !(n.ui || {}).list_only);
    const edges = state.topology.edges || [];
    if (!nodes.length) return;
    let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
    nodes.forEach((n) => {
      const ui = n.ui || {};
      minX = Math.min(minX, ui.x || 0);
      minY = Math.min(minY, ui.y || 0);
      maxX = Math.max(maxX, (ui.x || 0) + (ui.w || 180));
      maxY = Math.max(maxY, (ui.y || 0) + (ui.h || 96));
    });
    const pad = 24;
    const worldW = Math.max(1, maxX - minX + pad * 2);
    const worldH = Math.max(1, maxY - minY + pad * 2);
    const scale = Math.min(w / worldW, h / worldH);
    const nodePos = {};
    edges.forEach((edge) => {
      const a = getNode(edge.from);
      const b = getNode(edge.to);
      if (!a || !b) return;
      const au = a.ui || {};
      const bu = b.ui || {};
      const ax = ((au.x || 0) - minX + pad) * scale + Math.max(4, (au.w || 180) * scale) / 2;
      const ay = ((au.y || 0) - minY + pad) * scale + Math.max(3, (au.h || 96) * scale) / 2;
      const bx = ((bu.x || 0) - minX + pad) * scale + Math.max(4, (bu.w || 180) * scale) / 2;
      const by = ((bu.y || 0) - minY + pad) * scale + Math.max(3, (bu.h || 96) * scale) / 2;
      ctx.strokeStyle = "#91d5ff";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(bx, by);
      ctx.stroke();
    });
    nodes.forEach((n) => {
      const ui = n.ui || {};
      const x = ((ui.x || 0) - minX + pad) * scale;
      const y = ((ui.y || 0) - minY + pad) * scale;
      const nw = Math.max(6, (ui.w || 180) * scale);
      const nh = Math.max(4, (ui.h || 96) * scale);
      nodePos[n.id] = { x, y, w: nw, h: nh };
      ctx.fillStyle = (ROLE_COLOR[String(n.role || "").toLowerCase()] || {}).bg1 || "#ffffff";
      ctx.fillRect(x, y, nw, nh);
      ctx.strokeStyle = roleColor(n.role);
      ctx.lineWidth = 1;
      ctx.strokeRect(x + 0.5, y + 0.5, nw - 1, nh - 1);
    });
    const rect = shell.getBoundingClientRect();
    const v = view();
    const vx = (-v.x / v.zoom - minX + pad) * scale;
    const vy = (-v.y / v.zoom - minY + pad) * scale;
    const vw = (rect.width / v.zoom) * scale;
    const vh = (rect.height / v.zoom) * scale;
    ctx.fillStyle = "rgba(24, 144, 255, 0.08)";
    ctx.fillRect(vx, vy, vw, vh);
    ctx.strokeStyle = "rgba(24, 144, 255, 0.45)";
    ctx.lineWidth = 1;
    ctx.strokeRect(vx + 0.5, vy + 0.5, vw - 1, vh - 1);
    canvas.onclick = (ev) => {
      const r = canvas.getBoundingClientRect();
      const cx = ev.clientX - r.left;
      const cy = ev.clientY - r.top;
      const worldX = minX - pad + cx / scale;
      const worldY = minY - pad + cy / scale;
      state.topology.meta.viewport = {
        x: rect.width / 2 - worldX * v.zoom,
        y: rect.height / 2 - worldY * v.zoom,
        zoom: v.zoom,
      };
      renderScene();
    };
  }

  function setTopologyHint(text, type) {
    const el = $("topologyLoadHint");
    if (!el) return;
    el.textContent = String(text || "");
    el.className = "topology-load-hint" + (type ? (" " + type) : "");
    el.style.display = text ? "" : "none";
  }

  function projectDisplayName(item) {
    const id = String((item && item.id) || "");
    const name = String((item && item.name) || id || "-");
    if (id === "RecycleTycoon" || name === "垃圾回收站") return "MMORPG";
    return name;
  }

  async function loadProjectOptions() {
    const projectSel = $("projectSelector");
    if (!projectSel) return;
    const resp = await OpsApi.loadProjects("active");
    const rows = (resp && Array.isArray(resp.projects)) ? resp.projects : [];
    if (resp && resp.ok === false && !rows.length) return;
    if (!rows.length) {
      projectSel.innerHTML = '<option value="' + esc(state.projectId) + '">' + esc(projectDisplayName({ id: state.projectId, name: state.projectId })) + "</option>";
      projectSel.value = state.projectId;
      return;
    }
    projectSel.innerHTML = rows.map((item) => (
      '<option value="' + esc(item.id) + '">' + esc(projectDisplayName(item)) + "</option>"
    )).join("");
    if (state.projectId && rows.some((item) => String(item.id) === String(state.projectId))) {
      projectSel.value = state.projectId;
    } else if (rows.length) {
      state.projectId = String(rows[0].id || state.projectId || "");
      projectSel.value = state.projectId;
    }
  }

  function renderScopeSelectors() {
    const projectSel = $("projectSelector");
    if (projectSel && !projectSel.options.length) {
      projectSel.innerHTML = '<option value="' + esc(state.projectId) + '">' + esc(projectDisplayName({ id: state.projectId, name: state.projectId })) + "</option>";
      projectSel.value = state.projectId;
    } else if (projectSel && state.projectId) {
      projectSel.value = state.projectId;
    }
    const createProjectName = $("topologyCreateProjectName");
    if (createProjectName) {
      createProjectName.value = projectDisplayName({ id: state.projectId, name: state.projectId });
    }
    const envSel = $("envSelector");
    const createEnvSel = $("topologyCreateEnv");
    const envOptions = (((state.topologyRegistry || {}).env_options || []).length ? (state.topologyRegistry || {}).env_options : [
      { key: "development", label: "开发环境" },
      { key: "testing", label: "测试环境" },
      { key: "staging", label: "预发环境" },
      { key: "production", label: "生产环境" },
    ]).map((item) => ({
      key: String((item || {}).key || ""),
      label: String((item || {}).label || envLabel((item || {}).key || "")),
    }));
    const envHtml = envOptions.map((item) => '<option value="' + esc(item.key) + '">' + esc(item.label) + "</option>").join("");
    if (envSel) {
      envSel.innerHTML = envHtml;
      envSel.value = state.envKey;
    }
    if (createEnvSel) {
      createEnvSel.innerHTML = envHtml;
      createEnvSel.value = state.envKey || "production";
    }
    const topoSel = $("topologySelector");
    if (topoSel) {
      topoSel.innerHTML = (state.topologies || []).map((item) => {
        const label = (item.name || item.topology_id || "-") + (item.version_label ? (" · " + item.version_label) : "");
        return '<option value="' + esc(item.topology_id) + '">' + esc(label) + "</option>";
      }).join("");
      topoSel.value = state.topologyId;
    }
    const copySel = $("topologyCopySource");
    if (copySel) {
      copySel.innerHTML = '<option value="">请选择要复制的拓扑（可选）</option>' + (state.topologies || []).map((item) => (
        '<option value="' + esc(item.topology_id) + '">' + esc(item.name || item.topology_id) + "</option>"
      )).join("");
    }
  }

  function renderTopologyManagerList() {
    const body = $("topologyRegistryRows");
    if (!body) return;
    const rows = state.managerTopologies || state.topologies || [];
    const pageSize = state.topologyManagerPageSize || 10;
    const page = Math.max(1, state.topologyManagerPage || 1);
    const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
    if (page > totalPages) state.topologyManagerPage = totalPages;
    const start = (state.topologyManagerPage - 1) * pageSize;
    const pageRows = rows.slice(start, start + pageSize);
    const info = $("topologyManagerPageInfo");
    if (info) info.textContent = "共 " + rows.length + " 条";
    const pageNum = $("topologyManagerPageNum");
    if (pageNum) pageNum.textContent = String(state.topologyManagerPage || 1);
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="9">暂无拓扑，请先创建。</td></tr>';
      return;
    }
    body.innerHTML = pageRows.map((item) => {
      const status = String(item.status || "draft").toUpperCase();
      const nodeCount = Number(item.node_count || 0);
      const edgeCount = Number(item.edge_count || 0);
      const envCls = envTagClass(item.env_key);
      const running = status === "RUNNING";
      return '<tr>'
        + '<td>' + esc(item.name || item.topology_id) + (item.is_default ? ' <span class="state-pill state-info">默认</span>' : '') + '</td>'
        + '<td><span class="env-tag ' + envCls + '">' + esc(envLabel(item.env_key)) + '</span></td>'
        + '<td><span class="status-dot-line"><span class="status-dot ' + (running ? 'ok' : 'muted') + '"></span>' + esc(running ? '运行中' : '已停止') + '</span></td>'
        + '<td>' + esc(item.version_label || "-") + '</td>'
        + '<td>' + esc(formatTime(item.updated_at)) + '</td>'
        + '<td>' + esc(item.owner || "-") + '</td>'
        + '<td>' + nodeCount + '</td>'
        + '<td>' + edgeCount + '</td>'
        + '<td class="topology-manager-actions-cell">'
        + '<button class="btn btn-link" type="button" data-topology-open="' + esc(item.topology_id) + '">打开</button>'
        + '<button class="btn btn-link" type="button" data-topology-copy="' + esc(item.topology_id) + '">复制</button>'
        + '<button class="btn btn-link" type="button" data-topology-default="' + esc(item.topology_id) + '">设为默认</button>'
        + '<button class="btn btn-link danger" type="button" data-topology-delete="' + esc(item.topology_id) + '">删除</button>'
        + '</td>'
        + '</tr>';
    }).join("");
  }

  function renderBlueprintSelectors() {
    const bpSel = $("flowBlueprintSelect");
    const createBpSel = $("topologyCreateBlueprint");
    const options = '<option value="">请选择蓝图（可选）</option>' + (state.blueprints || []).map((b) => (
      '<option value="' + esc(b.blueprint_id) + '">' + esc(b.name || b.blueprint_id) + "</option>"
    )).join("");
    if (bpSel) bpSel.innerHTML = '<option value="">请选择蓝图模板</option>' + (state.blueprints || []).map((b) => (
      '<option value="' + esc(b.blueprint_id) + '">' + esc(b.name || b.blueprint_id) + "</option>"
    )).join("");
    if (createBpSel) createBpSel.innerHTML = options;
  }

  function setModalOpen(open) {
    document.body.classList.toggle("topology-modal-open", !!open);
  }

  function openTopologyManager() {
    const modal = $("topologyManagerModal");
    if (modal) modal.classList.remove("hidden");
    setModalOpen(true);
    const body = $("topologyRegistryRows");
    if (body) body.innerHTML = '<tr><td colspan="9">正在加载拓扑列表...</td></tr>';
    OpsApi.loadTopologies({ project_id: state.projectId }).then((resp) => {
      if (resp && resp.ok !== false && Array.isArray(resp.topologies)) {
        state.managerTopologies = resp.topologies;
      }
      renderTopologyManagerList();
    });
    renderScopeSelectors();
  }

  function closeTopologyManager() {
    const modal = $("topologyManagerModal");
    if (modal) modal.classList.add("hidden");
    setModalOpen(false);
  }

  async function switchScope(next) {
    if (!next) return;
    if (next.project_id) state.projectId = String(next.project_id);
    if (next.env_key) state.envKey = String(next.env_key);
    if (next.topology_id) state.topologyId = String(next.topology_id);
    syncQueryString();
    await loadAll();
  }

  async function createOrCopyTopologyFromForm() {
    const name = String((($("topologyCreateName") || {}).value || "")).trim();
    if (!name) { toast("请输入拓扑名称", "warn"); return; }
    const envKey = String((($("topologyCreateEnv") || {}).value || state.envKey || "production")).trim();
    const blueprintId = String((($("topologyCreateBlueprint") || {}).value || "")).trim();
    const copySource = String((($("topologyCopySource") || {}).value || "")).trim();
    const owner = String((($("topologyCreateOwner") || {}).value || "运维管理员")).trim();
    const description = String((($("topologyCreateDesc") || {}).value || "")).trim();
    let resp;
    if (copySource) {
      resp = await OpsApi.copyTopology({
        project_id: state.projectId,
        env_key: envKey,
        source_topology_id: copySource,
        name,
        owner,
        description,
      });
    } else {
      resp = await OpsApi.createTopology({
        project_id: state.projectId,
        env_key: envKey,
        name,
        owner,
        description,
        blueprint_id: blueprintId || "",
      });
    }
    if (!resp || resp.ok === false) {
      toast((resp && (resp.message || resp.error)) || "创建拓扑失败", "error");
      return;
    }
    state.topologies = Array.isArray(resp.topologies) ? resp.topologies : state.topologies;
    if (resp.topology_id) {
      state.topologyId = String(resp.topology_id);
      state.envKey = envKey;
    }
    renderScopeSelectors();
    renderTopologyManagerList();
    closeTopologyManager();
    await loadAll();
  }

  async function setDefaultTopology(topologyId) {
    const resp = await OpsApi.setDefaultTopology({
      project_id: state.projectId,
      env_key: state.envKey,
      topology_id: topologyId,
    });
    if (!resp || resp.ok === false) {
      toast((resp && (resp.message || resp.error)) || "设置默认拓扑失败", "error");
      return;
    }
    state.topologies = Array.isArray(resp.topologies) ? resp.topologies : state.topologies;
    renderTopologyManagerList();
    renderScopeSelectors();
    toast("默认拓扑已更新", "ok");
  }

  async function deleteTopology(topologyId) {
    if (!window.confirm("删除该拓扑后不可恢复，确认继续？")) return;
    const resp = await OpsApi.deleteTopology({
      project_id: state.projectId,
      env_key: state.envKey,
      topology_id: topologyId,
    });
    if (!resp || resp.ok === false) {
      toast((resp && (resp.message || resp.error)) || "删除拓扑失败", "error");
      return;
    }
    state.topologies = Array.isArray(resp.topologies) ? resp.topologies : state.topologies;
    if (state.topologyId === topologyId && state.topologies.length) {
      const fallback = state.topologies[0];
      state.topologyId = String(fallback.topology_id || "");
      state.envKey = String(fallback.env_key || state.envKey);
      await loadAll();
    } else {
      renderTopologyManagerList();
      renderScopeSelectors();
    }
    toast("拓扑已删除", "ok");
  }

  function refreshRightPanelMode() {
    const runtimeCard = $("runtimeSummaryCard");
    const inspector = $("nodeInspectorCard");
    const inModeTab = state.activeLeftTab === "mode";
    const inRunTest = state.mode === "run" || state.mode === "test";
    const showRuntime = inModeTab && inRunTest;
    if (runtimeCard) runtimeCard.classList.toggle("is-hidden", !showRuntime);
    if (inspector) {
      inspector.classList.toggle("is-hidden", showRuntime);
      inspector.classList.toggle("is-runtime-mode", showRuntime);
    }
    if (showRuntime && $("runtimeTopologyInfo")) {
      const topo = (state.topologies || []).find((t) => String(t.topology_id) === String(state.topologyId));
      $("runtimeTopologyInfo").textContent = topo
        ? (topo.name || topo.topology_id) + " · " + envLabel(state.envKey) + " · " + String(topo.version_label || "-")
        : state.topologyId || "-";
    }
  }

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
    const ioTab = document.querySelector(".topology-inspector-tab[data-tab-nodes='输入输出端口']");
    if (ioTab) ioTab.setAttribute("data-inspector-tab", layout === "nodes" ? "ioPortsPanel" : "monitorPanel");
    if (layout === "nodes" && state.inspectorTab === "monitorPanel") {
      state.inspectorTab = "basicInfoPanel";
      document.querySelectorAll("[data-inspector-tab]").forEach((tab) => {
        tab.classList.toggle("active", tab.getAttribute("data-inspector-tab") === "basicInfoPanel");
      });
      document.querySelectorAll(".topology-inspector-pane").forEach((pane) => {
        pane.classList.toggle("active", pane.id === "basicInfoPanel");
      });
    }
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
      state.inspectorTab = name;
      tabs.forEach((tab) => tab.classList.toggle("active", tab.getAttribute("data-inspector-tab") === name));
      panes.forEach((pane) => pane.classList.toggle("active", pane.id === name));
    };
    tabs.forEach((tab) => {
      tab.onclick = () => activate(tab.getAttribute("data-inspector-tab") || "basicInfoPanel");
    });
    activate(state.inspectorTab || "basicInfoPanel");
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

  function redrawGraph() {
    drawNodes();
    drawEdges();
  }

  function ensureEdgeMarkers() {
    const svg = $("edgeSvg");
    if (!svg || svg.querySelector("#edge-arrow-marker")) return;
    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
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
    svg.appendChild(defs);
  }

  function drawEdges() {
    const svg = $("edgeSvg");
    if (!svg) return;
    svg.querySelectorAll(":scope > :not(defs)").forEach((el) => el.remove());
    ensureEdgeMarkers();
    let visible = 0;
    let skipped = 0;
    (state.topology.edges || []).forEach((edge) => {
      const d = edgePath(edge);
      if (!d) { skipped += 1; return; }
      visible += 1;
      const hit = document.createElementNS("http://www.w3.org/2000/svg", "path");
      hit.setAttribute("d", d);
      hit.setAttribute("fill", "none");
      hit.setAttribute("class", "edge-hit");
      hit.onclick = (ev) => { ev.stopPropagation(); state.selection.edgeId = edge.id; state.selection.nodes.clear(); redrawGraph(); };
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      path.setAttribute("fill", "none");
      path.setAttribute("marker-end", "url(#edge-arrow-marker)");
      const hl = state.highlight.edges.has(edge.id) ? " hl" : "";
      const segmentHl = isTestSegmentScope() && state.highlight.edges.size > 0;
      const dim = segmentHl && !state.highlight.edges.has(edge.id) ? " path-dim" : "";
      const flow = state.flowViz.edges.has(edge.id) ? " flow" : "";
      const fail = (state.flowViz.statusByNode[String(edge.to)] && ["FAILED", "TIMEOUT", "CANCELED"].includes(String(state.flowViz.statusByNode[String(edge.to)]).toUpperCase())) ? " fail" : "";
      path.setAttribute("class", "edge" + hl + dim + flow + fail + (state.selection.edgeId === edge.id ? " sel" : ""));
      const src = getNode(edge.from);
      if (!flow && !hl && !fail) {
        path.style.stroke = isEditMode() ? "#2563eb" : roleColor(src && src.role);
      }
      path.onclick = (ev) => { ev.stopPropagation(); state.selection.edgeId = edge.id; state.selection.nodes.clear(); redrawGraph(); };
      svg.appendChild(hit);
      svg.appendChild(path);
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
        if (isEditMode()) {
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
      const aid = String((state.nodeBindings || {})[n.id] || "");
      const ag = state.agents.find((x) => String(x.agent_id || "") === aid) || null;
      const bindText = ag ? ("Agent： " + (ag.display_name || ag.agent_id)) : "未绑定 Agent";
      const agHealth = agentHealthLabel(ag);
      const st = String(n.bizStatus || "normal");
      const stLabel = agHealth.cls === "err" ? "心跳过期" : (agHealth.cls === "warn" ? "Agent异常" : (STATUS_LABELS[st] || st));
      const flowSt = String((state.flowViz.statusByNode || {})[n.id] || "").toUpperCase();
      const isFlow = state.flowViz.nodes.has(n.id);
      const palette = nodePalette(n);
      const runtimeItem = runtime[n.id] || {};
      const displayTitle = nodeDisplayTitle(n);
      const metaId = String(runtimeItem.server_id || n.server_id || n.id || "-");
      const descLine = String(n.desc || "").trim() || roleLabel(n.role);
      let statusText;
      let statusCls;
      statusText = STATUS_LABELS[st] || "运行中";
      statusCls = st === "error" || st === "offline" ? "err" : (st === "degraded" || st === "observe" ? "warn" : "ok");
      if ((isRunMode() || isTestMode()) && isFlow) {
        const flowRunning = flowSt === "RUNNING" || flowSt === "SUCCESS";
        statusText = flowRunning ? "运行中" : (STATUS_LABELS[st] || stLabel);
        statusCls = flowRunning ? "ok" : (flowSt === "FAILED" ? "err" : "warn");
      }

      const hasIn = (state.topology.edges || []).some((e) => String(e.to) === String(n.id));
      const agentLine = aid ? ('<div class="node-agent-line">Agent: ' + esc(aid) + '</div>') : "";
      const segmentHl = isTestSegmentScope() && state.highlight.nodes.size > 0;

      const el = document.createElement("div");
      el.className = "node structured-node tw-node"
        + (hasIn ? " has-in-port" : "")
        + (state.selection.nodes.has(n.id) ? " sel" : "")
        + (segmentHl && state.highlight.nodes.has(n.id) ? " hl" : "")
        + (segmentHl && !state.highlight.nodes.has(n.id) ? " path-dim" : "")
        + (isFlow ? " flow-active" : "")
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
        + drawPorts(n, "in") + drawPorts(n, "out")
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
      const st = String(n.bizStatus || "normal");
      const flowSt = String((state.flowViz.statusByNode || {})[n.id] || "").toUpperCase();
      const stLabel = flowSt ? (flowSt === "RUNNING" ? "运行中" : flowSt) : (STATUS_LABELS[st] || st || "运行中");
      const stCls = flowSt === "FAILED" ? "state-err" : (flowSt === "RUNNING" || flowSt === "SUCCESS" ? "state-ok" : "state-info");
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
    if (role === "database") return pid.includes("mysql") ? "MySQL" : "DB";
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
    const d = await OpsApi.addNodeFromPreset({ preset_id: String(p.preset_id || ""), name: "", server_id: "", project_id: state.projectId, owner: "", env: "prod", channel: "", description: p.default_desc || "" });
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

  function renderPortLists(node) {
    const inBox = $("inPortList");
    const outBox = $("outPortList");
    const inIo = $("inPortListIo");
    const outIo = $("outPortListIo");
    if (!node) return;
    const render = (side, box, interactive) => {
      if (!box) return;
      const ports = ((node.ui && node.ui.ports && node.ui.ports[side]) || []);
      if (!ports.length) {
        box.innerHTML = '<span class="state-pill state-warn">无 ' + side + " 端口</span>";
        return;
      }
      if (interactive) {
        box.innerHTML = ports.map((p) => {
          const selected = state.selectedPort && state.selectedPort.side === side && String(state.selectedPort.id) === String(p.id);
          const cls = selected ? "port-pill selected" : "port-pill";
          return '<button type="button" class="' + cls + '" data-side="' + side + '" data-port-id="' + esc(p.id) + '">' + esc(p.label || p.id) + " (" + countLinks(node.id, side, p.id) + ")</button>";
        }).join(" ");
        box.querySelectorAll("[data-port-id]").forEach((btn) => {
          btn.onclick = () => {
            state.selectedPort = { side: btn.getAttribute("data-side"), id: btn.getAttribute("data-port-id") };
            renderPortLists(node);
          };
        });
      } else {
        box.innerHTML = ports.map((p) => (
          '<span class="port-pill readonly">' + esc(p.label || p.id) + "</span>"
        )).join(" ");
      }
    };
    render("in", inBox, true);
    render("out", outBox, true);
    render("in", inIo, false);
    render("out", outIo, false);
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
      pill.textContent = STATUS_LABELS[node.bizStatus] || node.bizStatus || "运行中";
      pill.className = "state-pill " + (node.bizStatus === "normal" ? "state-ok" : node.bizStatus === "error" ? "state-err" : "state-info");
    }
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
    const remotePort = String((((n.ui || {}).remote || {}).port || "") || (n.id === "game-01" ? "9501" : ""));
    $("insNodeRemotePort").value = remotePort;
    const eps = (((n.ui || {}).network || {}).endpoints || []);
    const epText = Array.isArray(eps) && eps.length ? eps.join(",") : (n.id === "game-01" ? "10.0.1.15:9501" : "");
    $("insNodeEndpoints").value = epText;
    syncInspectorPortFieldsFromMain();
    $("insNodePortsSummary").value = "in: " + ((((n.ui || {}).ports || {}).in || []).length) + " / out: " + ((((n.ui || {}).ports || {}).out || []).length);
    state.selectedPort = null;
    fillAgentSelect(nodeId);
    renderPortLists(n);
    renderMonitorPanel(nodeId);
    refreshInspectorLayout(state.activeLeftTab || "tools");
    applyModeUI();
    updateInspectorHeader(n);
    drawNodes();
  }

  function refreshPortSummary(node) {
    if (!node) return;
    $("insNodePortsSummary").value = "in: " + ((((node.ui || {}).ports || {}).in || []).length) + " / out: " + ((((node.ui || {}).ports || {}).out || []).length);
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
    ["insNodeId", "insNodePortsSummary", "insNodeOwner", "insNodeAgentMeta", "insNodeRemotePort", "insNodeEndpoints", "insNodeDesc", "insNodeTags", "insNodeColor", "insNodeKindDisplay", "insNodeRemotePortBasic", "insNodeEndpointsBasic", "insNodeDeployVersionBasic", "insNodeServiceSummary", "insNodeNotes"].forEach((id) => {
      const el = $(id);
      if (el) el.value = "";
    });
    if ($("insNodeKind")) $("insNodeKind").value = "standard";
    if ($("insNodePrimaryAgentBasic")) $("insNodePrimaryAgentBasic").innerHTML = '<option value="">未绑定</option>';
    if ($("insNodeRole")) $("insNodeRole").selectedIndex = 0;
    if ($("insNodeBizStatus")) $("insNodeBizStatus").selectedIndex = 0;
    if ($("insNodePrimaryAgent")) $("insNodePrimaryAgent").innerHTML = '<option value="">未绑定</option>';
    if ($("insNodeService")) $("insNodeService").innerHTML = '<option value="">请先选择 Agent</option>';
    renderPortLists({ ui: { ports: { in: [], out: [] } } });
    renderTagChips([]);
    renderMonitorPanel("");
    updateInspectorHeader(null);
    drawNodes();
  }

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
    const remotePort = Number(($("insNodeRemotePort") && $("insNodeRemotePort").value) || 0);
    n.ui.remote.port = (Number.isFinite(remotePort) && remotePort > 0) ? remotePort : 0;
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
    dbg("runFullLifecycle-click", { op, mode: state.mode, locked: !!state.modeLocked, currentRunId: state.runtimeRunId || "" });
    stopRuntimePolling();
    if (!start) clearFlowViz(true, "runFullLifecycle-stop-before-control");
    state.runtimeSteady = false;
    state.runtimeLastStatus = "";
    state.runtimeLogSeen = new Set();
    state.runtimeProgressSig = "";
    logMode((start ? "开始" : "开始") + (start ? "一键启动" : "一键停止") + "全流程");
    if (start) {
      const startupNodes = (state.topology.nodes || []).map((n) => n.id);
      const pre = await precheckAndStartRemoteForNodes(startupNodes);
      if (!pre.ok) {
        toast("前置校验失败：存在未通过联通或远端启动失败节点", "error");
        appendJsonDetail("运行前置校验失败节点清单", pre.failures);
        return;
      }
    }
    const d = await OpsApi.runtimeFlowControl(Object.assign(currentScope(), { op }));
    if (!d || d.ok === false) {
      toast((d && d.message) || "运行请求失败", "error");
      logMode("运行请求失败: " + ((d && (d.message || d.error)) || "未知错误"), "error");
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
    state.runtimePollTimer = setInterval(() => { pollRuntimeRun(state.runtimeRunId); }, 1200);
  }

  async function runSmokeOrStress(isStress) {
    const scope = getTestScope();
    const resolved = resolveTestEndpoints(scope);
    const startNode = resolved.start || "";
    const endNode = resolved.end || "";
    if (!resolved.ok) {
      toast(resolved.reason || "链路段测试需选择起点和终点", "warn");
      logMode("链路段测试参数不完整: start=" + (startNode || "-") + " end=" + (endNode || "-") + " reason=" + (resolved.reason || "未知原因"), "warn");
      return;
    }
    logMode("测试参数确认: scope=" + scope + " start=" + (startNode || "-") + " end=" + (endNode || "-"));
    computePathHighlight();
    syncFlowViz("test", Array.from(state.highlight.nodes || []), {});
    state.flowViz.metricsByEdge = {};
    Array.from(state.flowViz.edges || []).forEach((eid) => { state.flowViz.metricsByEdge[eid] = edgeMetrics(eid, "RUNNING"); });
    redrawGraph();
    if (isStress) {
      const target = scope === "segment" ? endNode : (startNode || ((state.topology.nodes || [])[0] || {}).id || "");
      testLogHeader("压力测试开始", "scope=" + scope + " target=" + target);
      testLogKV("qps", 500);
      testLogKV("duration_sec", 180);
      const d = await OpsApi.postJSON("/api/ops-platform/stress-test", Object.assign(currentScope(), {
        node_id: target,
        qps: 500,
        duration_sec: 180,
        reason: "拓扑测试模式压力测试",
      }));
      if (d && d.ok !== false) {
        logMode("压力测试提交成功: target=" + target + " trace_id=" + (d.trace_id || "-"));
        if (d.result) {
          testLogKV("http_status", d.result.status);
          testLogKV("result_code", d.result.result_code || "OPS_OK");
          testLogKV("result_message", d.result.result_message || d.result.message || "-");
          testLogKV("latency_ms", d.result.latency_ms);
          if (d.result.data) testLogKV("result_data", d.result.data);
        }
        appendJsonDetail("压力测试原始响应", d);
        toast("压力测试已提交", "ok");
        setTimeout(() => { clearFlowViz(true, "runSmokeOrStress-stress-success"); redrawGraph(); }, 2600);
      } else {
        logMode("压力测试失败: " + ((d && (d.message || d.error)) || "未知错误"), "error");
        if (d) {
          testLogKV("error_code", d.error_code || d.error || "-");
          testLogKV("http_status", d._http_status || "-");
          testLogKV("message", d.message || "-");
        }
        appendJsonDetail("压力测试失败原始响应", d || {});
        toast((d && d.message) || "压力测试失败", "error");
        setTimeout(() => { clearFlowViz(true, "runSmokeOrStress-stress-failed"); redrawGraph(); }, 2600);
      }
      return;
    }
    const pathNodes = scope === "full"
      ? (state.topology.nodes || []).map((n) => n.id)
      : [startNode, endNode].filter(Boolean);
    const pre = await precheckAndStartRemoteForNodes(pathNodes);
    if (!pre.ok) {
      toast("测试前置校验失败，请先修复失败节点", "error");
      appendJsonDetail("测试前置校验失败节点清单", pre.failures);
      return;
    }
    testLogHeader("单元测试开始", "scope=" + scope);
    testLogKV("path_nodes", pathNodes.join(" -> "));
    testLogKV("path_len", pathNodes.length);
    const d = await OpsApi.postJSON("/api/ops-platform/flow-smoke", Object.assign(currentScope(), { path_nodes: pathNodes }));
    if (d && d.ok !== false) {
      const flowId = d.flow_id || "-";
      const steps = Array.isArray(d.steps) ? d.steps : [];
      logMode("单元测试完成: flow_id=" + flowId + " steps=" + steps.length + " ok=" + (!!d.ok));
      steps.forEach((s, i) => testLogStep(i, s));
      const okCount = steps.filter((s) => s && s.ok).length;
      const failCount = steps.length - okCount;
      logMode("单元测试汇总: ok_steps=" + okCount + " fail_steps=" + failCount + " flow_id=" + flowId, failCount > 0 ? "warn" : "");
      appendJsonDetail("单元测试原始响应", d);
      toast("单元测试完成", "ok");
      const stepStatus = {};
      (steps || []).forEach((s) => { if (s && s.node_id) stepStatus[String(s.node_id)] = s.ok ? "SUCCESS" : "FAILED"; });
      syncFlowViz("test", Array.from(state.highlight.nodes || []), stepStatus);
      state.flowViz.metricsByEdge = {};
      Array.from(state.flowViz.edges || []).forEach((eid) => {
        const anyFail = Object.values(stepStatus || {}).some((x) => String(x).toUpperCase() === "FAILED");
        state.flowViz.metricsByEdge[eid] = edgeMetrics(eid, anyFail ? "FAILED" : "SUCCESS");
      });
      redrawGraph();
    } else {
      logMode("单元测试失败: " + ((d && (d.message || d.error)) || "未知错误"), "error");
      if (d) {
        testLogKV("error_code", d.error_code || d.error || "-");
        testLogKV("http_status", d._http_status || "-");
        testLogKV("message", d.message || "-");
      }
      appendJsonDetail("单元测试失败原始响应", d || {});
      toast((d && d.message) || "单元测试失败", "error");
      syncFlowViz("test", Array.from(state.highlight.nodes || []), {});
      state.flowViz.metricsByEdge = {};
      Array.from(state.flowViz.edges || []).forEach((eid) => { state.flowViz.metricsByEdge[eid] = edgeMetrics(eid, "FAILED"); });
      redrawGraph();
    }
  }

  function clearTestHighlight() {
    state.highlight = { nodes: new Set(), edges: new Set() };
    redrawGraph();
  }

  function computePathHighlight() {
    if (!isTestMode()) { clearTestHighlight(); return; }
    if (!isTestSegmentScope()) {
      setTestPathHint("");
      clearTestHighlight();
      return;
    }
    const startNode = $("testStartNode").value || "";
    const endNode = $("testEndNode").value || "";
    if (!startNode || !endNode) {
      setTestPathHint("请选择起点和终点节点");
      clearTestHighlight();
      return;
    }
    if (startNode === endNode) {
      setTestPathHint("起点和终点不能相同");
      clearTestHighlight();
      return;
    }
    const edges = state.topology.edges || [];
    const adj = {};
    edges.forEach((e) => {
      if (!adj[e.from]) adj[e.from] = [];
      adj[e.from].push(e);
    });
    const q = [startNode];
    const prev = {};
    const visited = new Set([startNode]);
    let found = false;
    while (q.length) {
      const cur = q.shift();
      if (cur === endNode) { found = true; break; }
      (adj[cur] || []).forEach((e) => {
        const nx = e.to;
        if (visited.has(nx)) return;
        visited.add(nx);
        prev[nx] = { node: cur, edge: e.id };
        q.push(nx);
      });
    }
    if (!found) {
      setTestPathHint("未找到从 " + startNode + " 到 " + endNode + " 的连通路径");
      clearTestHighlight();
      return;
    }
    const nodes = new Set();
    const hlEdges = new Set();
    let cursor = endNode;
    nodes.add(cursor);
    while (cursor !== startNode && prev[cursor]) {
      hlEdges.add(prev[cursor].edge);
      cursor = prev[cursor].node;
      nodes.add(cursor);
    }
    setTestPathHint("已高亮链路段：" + Array.from(nodes).join(" → "));
    state.highlight = { nodes, edges: hlEdges };
    redrawGraph();
  }

  function fillTestNodeOptions() {
    const nodes = state.topology.nodes || [];
    const startSel = $("testStartNode");
    const endSel = $("testEndNode");
    if (!startSel || !endSel) return;

    const prevStart = startSel.value || "";
    const prevEnd = endSel.value || "";
    const ids = nodes.map((n) => String(n.id || "")).filter(Boolean);
    const options = nodes.map((n) => (
      '<option value="' + esc(n.id) + '">' + esc(testNodeOptionLabel(n)) + "</option>"
    )).join("");

    startSel.innerHTML = '<option value="">请选择起点节点</option>' + options;
    endSel.innerHTML = '<option value="">请选择终点节点</option>' + options;

    const hasPrevStart = prevStart && ids.indexOf(prevStart) >= 0;
    const hasPrevEnd = prevEnd && ids.indexOf(prevEnd) >= 0;
    let nextStart = hasPrevStart ? prevStart : "";
    let nextEnd = hasPrevEnd ? prevEnd : "";

    if (!nextStart) nextStart = ids.includes("gateway-01") ? "gateway-01" : (ids[0] || "");
    if (!nextEnd) nextEnd = ids.includes("tcp-01") ? "tcp-01" : (ids.find((id) => id !== nextStart) || ids[0] || "");
    if (ids.length > 1 && nextStart === nextEnd) {
      nextEnd = ids.find((id) => id !== nextStart) || nextEnd;
    }

    startSel.value = nextStart;
    endSel.value = nextEnd;
  }

  function resolveTestEndpoints(scope) {
    const nodes = state.topology.nodes || [];
    const ids = nodes.map((n) => String(n.id || "")).filter(Boolean);
    const startSel = $("testStartNode");
    const endSel = $("testEndNode");
    let start = String((startSel && startSel.value) || "").trim();
    let end = String((endSel && endSel.value) || "").trim();

    if (scope === "full") return { ok: true, start, end };

    const picked = Array.from((state.selection && state.selection.nodes) || []);
    if (!start && picked[0]) start = picked[0];
    if (!end && picked[1]) end = picked[1];

    if (!start && ids.length) start = ids[0];
    if (!end && ids.length) end = ids.find((id) => id !== start) || ids[0];

    if (startSel) startSel.value = start || "";
    if (endSel) endSel.value = end || "";

    if (!start || !end) return { ok: false, start, end, reason: "链路段测试需选择起点和终点" };
    if (start === end && ids.length > 1) {
      const alt = ids.find((id) => id !== start);
      if (alt) {
        end = alt;
        if (endSel) endSel.value = end;
      }
    }
    if (start === end) return { ok: false, start, end, reason: "起点和终点不能相同" };
    return { ok: true, start, end };
  }

  function applyModeUI() {
    const map = {
      edit: { hint: "当前为编辑模式，可调整拓扑结构、节点属性与绑定关系。", run: "none", test: "none" },
      run: { hint: "当前为运行模式，聚焦全流程启动、停止与运行回放。", run: "flex", test: "none" },
      test: { hint: "测试模式支持完整架构与指定链路段验证；模式锁定后不可切换。", run: "none", test: "flex" },
    };
    const cfg = map[state.mode] || map.edit;
    const modeHint = $("modeHint");
    if (modeHint) modeHint.textContent = cfg.hint;
    const runBar = $("runBar");
    const testBar = $("testBar");
    if (runBar) runBar.style.display = cfg.run;
    if (testBar) testBar.style.display = cfg.test;
    const modeSelect = $("modeSelect");
    if (modeSelect) {
      modeSelect.value = state.mode;
      modeSelect.disabled = state.modeLocked;
    }
    document.querySelectorAll("[data-mode-value]").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-mode-value") === state.mode);
      btn.disabled = state.modeLocked;
    });
    if ($("modeLockBtn")) $("modeLockBtn").style.display = state.modeLocked ? "none" : "";
    if ($("modeUnlockBtn")) $("modeUnlockBtn").style.display = state.modeLocked ? "" : "none";
    if ($("modeLockSwitch")) $("modeLockSwitch").checked = !state.modeLocked;
    if ($("modeLockStatus")) {
      $("modeLockStatus").textContent = state.modeLocked ? "已锁定" : "已解锁";
      $("modeLockStatus").style.color = state.modeLocked ? "#2563eb" : "#16a34a";
    }
    const shell = document.querySelector(".ops-topology-app");
    if (shell) {
      shell.classList.remove("canvas-mode-edit", "canvas-mode-run", "canvas-mode-test");
      shell.classList.add("canvas-mode-" + state.mode);
    }
    refreshRightPanelMode();
    refreshLogDemoForChrome();
    syncLayoutSpacingControls();
    syncToolButtonsForMode();
    if (state.mode === "test") {
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
    if (state.mode === "edit") {
      clearFlowViz(true, "applyModeUI-edit-mode");
      redrawGraph();
    }

    const lock = state.mode !== "edit";
    ["insNodeName", "insNodeRole", "insNodeBizStatus", "insNodeKind", "insNodeColorPicker", "insNodeOwner", "insNodePrimaryAgent", "insNodePrimaryAgentBasic", "insNodeDesc", "insNodeTags", "insNodeRemotePort", "insNodeRemotePortBasic", "insNodeEndpoints", "insNodeEndpointsBasic", "insNodeNotes"]
      .forEach((id) => { const el = $(id); if (el) el.disabled = lock; });
    document.querySelectorAll(".topology-color-preset").forEach((btn) => { btn.disabled = lock; });
    ["btnPortInAdd", "btnPortOutAdd", "btnPortInRemove", "btnPortOutRemove", "btnDeleteSelectedPort", "btnDeleteNode", "btnSaveNode", "btnSaveNodeTools"]
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
    await loadProjectOptions();
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

    loadAuxiliaryData();
  }

  async function loadAuxiliaryData() {
    const settled = await Promise.allSettled([
      OpsApi.loadNodes(),
      OpsApi.loadOverview(state.projectId),
      OpsApi.loadTopologyBlueprints(),
      OpsApi.loadNodeBindings(currentScope()),
      OpsApi.agents(state.projectId),
      OpsApi.listServices(state.projectId),
    ]);
    const [nodes, overview, blueprints, bindings, agents, servicesResp] = settled.map((r) => r.status === "fulfilled" ? r.value : { ok: false, error: String(r.reason || "request_failed") });
    if (checkAuthExpired(nodes) || checkAuthExpired(overview) || checkAuthExpired(blueprints) || checkAuthExpired(bindings) || checkAuthExpired(agents) || checkAuthExpired(servicesResp)) return;

    const warns = [];
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
    if (overview && overview.ok !== false) state.overviewNodes = overview.nodes || [];
    else warns.push("总览");
    if (blueprints && blueprints.ok !== false && Array.isArray(blueprints.blueprints)) state.blueprints = blueprints.blueprints;
    else warns.push("流程模板");
    if (bindings && bindings.ok !== false) {
      state.nodeBindings = bindings.bindings || {};
      state.serviceBindings = bindings.service_bindings || {};
    }
    else warns.push("绑定");
    if (agents && agents.ok !== false) state.agents = agents.agents || [];
    else warns.push("Agent");
    if (servicesResp && servicesResp.ok !== false) state.services = servicesResp.services || servicesResp.items || [];
    else warns.push("服务实例");

    renderBlueprintSelectors();
    renderScopeSelectors();
    renderTopologyManagerList();

    const bpSel = $("flowBlueprintSelect");
    if (bpSel) {
      bpSel.innerHTML = '<option value="">流程模板</option>' + state.blueprints.map((b) => '<option value="' + esc(b.blueprint_id) + '">' + esc(b.name) + '</option>').join("");
    }

    redrawGraph();
    renderRuntimeNodeList();
    fillTestNodeOptions();
    applyModeUI();
    const currentNodeId = String((($("insNodeId") || {}).value || "")).trim();
    if (currentNodeId && getNode(currentNodeId)) openNodeEditor(currentNodeId);
    setTopologyHint(warns.length ? ("部分辅助数据加载失败: " + warns.join("、") + "，画布仍可操作") : "", warns.length ? "warn" : "");
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

  function bindLayoutSpacingControls() {
    const rankEl = $("layoutRankGapRange");
    const rowEl = $("layoutRowGapRange");
    if (!rankEl || !rowEl || rankEl.dataset.bound === "1") {
      syncLayoutSpacingControls();
      return;
    }
    rankEl.dataset.bound = "1";
    rowEl.dataset.bound = "1";
    rankEl.addEventListener("input", () => {
      const rank_gap = clampLayoutSpacing("rank_gap", rankEl.value);
      if ($("layoutRankGapValue")) $("layoutRankGapValue").textContent = String(rank_gap);
      queueLayoutSpacingRelayout({ rank_gap });
    });
    rowEl.addEventListener("input", () => {
      const row_gap = clampLayoutSpacing("row_gap", rowEl.value);
      if ($("layoutRowGapValue")) $("layoutRowGapValue").textContent = String(row_gap);
      queueLayoutSpacingRelayout({ row_gap });
    });
    syncLayoutSpacingControls();
  }

  function bindEvents() {
    bindLeftTabs();
    bindInspectorTabs();
    bindLogTabs();
    bindTopologyManagerTabs();
    setInspectorEmpty(true);
    let fitTimer = null;
    window.addEventListener("resize", () => {
      if (fitTimer) clearTimeout(fitTimer);
      fitTimer = setTimeout(() => { fitGraphToViewport(); }, 120);
    });
    const insRole = $("insNodeRole");
    if (insRole) ROLE_OPTIONS.forEach((v) => insRole.insertAdjacentHTML("beforeend", '<option value="' + v + '">' + esc(roleLabel(v)) + '</option>'));
    const insStatus = $("insNodeBizStatus");
    if (insStatus) STATUS_OPTIONS.forEach((v) => insStatus.insertAdjacentHTML("beforeend", '<option value="' + v + '">' + (STATUS_LABELS[v] || v) + '</option>'));
    renderColorPresets();
    if ($("insNodeColorPicker")) {
      $("insNodeColorPicker").oninput = () => setInspectorNodeColor($("insNodeColorPicker").value || "");
    }
    if ($("btnAddNodeTag")) {
      $("btnAddNodeTag").onclick = () => {
        const raw = window.prompt("输入标签名称", "");
        if (!raw) return;
        const tag = String(raw).trim();
        if (!tag) return;
        const cur = String(($("insNodeTags") || {}).value || "").split(",").map((x) => x.trim()).filter(Boolean);
        if (cur.includes(tag)) return;
        renderTagChips(cur.concat([tag]));
      };
    }

    document.querySelectorAll("[data-mode-value]").forEach((btn) => {
      btn.onclick = () => {
        if (state.modeLocked) return;
        state.mode = btn.getAttribute("data-mode-value") || "edit";
        applyModeUI();
        saveModeState();
      };
    });

    if ($("projectSelector")) $("projectSelector").onchange = async () => {
      const nextProject = String($("projectSelector").value || state.projectId);
      await switchScope({ project_id: nextProject, env_key: state.envKey, topology_id: state.topologyId });
    };
    if ($("envSelector")) $("envSelector").onchange = async () => {
      const nextEnv = String($("envSelector").value || state.envKey);
      const fallback = (state.topologies || []).find((item) => String(item.env_key || "") === nextEnv && item.is_default) || (state.topologies || []).find((item) => String(item.env_key || "") === nextEnv) || {};
      await switchScope({ project_id: state.projectId, env_key: nextEnv, topology_id: String(fallback.topology_id || "") });
    };
    if ($("topologySelector")) $("topologySelector").onchange = async () => {
      const nextTopology = String($("topologySelector").value || state.topologyId);
      const hit = (state.topologies || []).find((item) => String(item.topology_id || "") === nextTopology) || {};
      await switchScope({ project_id: state.projectId, env_key: String(hit.env_key || state.envKey), topology_id: nextTopology });
    };

    ["btnManageTopologyHeader", "btnManageTopologyInline"].forEach((id) => {
      const el = $(id);
      if (el) el.onclick = openTopologyManager;
    });
    if ($("btnCreateTopologyHeader")) $("btnCreateTopologyHeader").onclick = () => {
      openTopologyManager();
      document.querySelectorAll("[data-topology-manager-tab]").forEach((tab) => {
        if (tab.getAttribute("data-topology-manager-tab") === "topologyManagerCreatePane") tab.click();
      });
    };
    if ($("btnCreateTopologyFromModal")) $("btnCreateTopologyFromModal").onclick = () => {
      document.querySelectorAll("[data-topology-manager-tab]").forEach((tab) => {
        if (tab.getAttribute("data-topology-manager-tab") === "topologyManagerCreatePane") tab.click();
      });
    };
    if ($("btnCloseTopologyManager")) $("btnCloseTopologyManager").onclick = closeTopologyManager;
    if ($("btnCancelCreateTopology")) $("btnCancelCreateTopology").onclick = closeTopologyManager;
    if ($("btnSubmitCreateTopology")) $("btnSubmitCreateTopology").onclick = createOrCopyTopologyFromForm;
    if ($("btnCloseNodeLogModal")) $("btnCloseNodeLogModal").onclick = () => { $("nodeLogModal").classList.add("hidden"); setModalOpen(false); };
    if ($("btnClearModeLogs")) $("btnClearModeLogs").onclick = () => {
      if ($("modeLog")) $("modeLog").innerHTML = "";
      if ($("modeLogDetails")) $("modeLogDetails").innerHTML = "";
      if ($("deploymentLogMirror")) $("deploymentLogMirror").innerHTML = "";
    };

    const presetSearchEl = $("presetSearch");
    if (presetSearchEl) presetSearchEl.oninput = renderPresets;
    if ($("presetCategoryFilter")) $("presetCategoryFilter").onchange = renderPresets;
    document.querySelectorAll("#presetCategoryChips .topology-chip").forEach((chip) => {
      chip.onclick = () => {
        document.querySelectorAll("#presetCategoryChips .topology-chip").forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        if ($("presetCategoryFilter")) $("presetCategoryFilter").value = chip.getAttribute("data-category") || "";
        renderPresets();
      };
    });
    if ($("globalTopologySearch")) $("globalTopologySearch").oninput = () => {
      const keyword = String($("globalTopologySearch").value || "").trim().toLowerCase();
      if (!keyword) {
        state.highlight = { nodes: new Set(), edges: new Set() };
        redrawGraph();
        return;
      }
      const hitNodes = (state.topology.nodes || []).filter((n) => [n.id, n.name, n.role, n.owner].some((x) => String(x || "").toLowerCase().includes(keyword))).map((n) => n.id);
      const hitEdges = (state.topology.edges || []).filter((e) => hitNodes.includes(String(e.from || "")) || hitNodes.includes(String(e.to || ""))).map((e) => e.id);
      state.highlight = { nodes: new Set(hitNodes), edges: new Set(hitEdges) };
      redrawGraph();
    };

    const toolAutoEl = $("toolAuto");
    if (toolAutoEl) toolAutoEl.onclick = () => {
      if (isTestMode()) { toast("测试模式禁止自动布局", "warn"); return; }
      if (!state.topology.meta || typeof state.topology.meta !== "object") state.topology.meta = {};
      state.topology.meta.layout_locked = false;
      layoutStructuredGraph({ force: true });
      redrawGraph();
      toast("已按结构化规则重新排布", "ok");
    };

    const toolList = document.querySelector(".topology-tool-list");
    if (toolList) {
      toolList.addEventListener("click", (ev) => {
        const btn = ev.target.closest(".topology-tool-btn");
        if (!btn) return;
        ev.preventDefault();
        handleToolButtonClick(btn);
      });
    }
    if ($("toolCanvasZoom")) $("toolCanvasZoom").onclick = () => {
      fitGraphToViewport();
      renderScene();
    };
    ["toolUndo", "canvasQuickUndo"].forEach((id) => {
      const el = $(id);
      if (el) el.onclick = () => undoTopology();
    });
    ["toolRedo", "canvasQuickRedo"].forEach((id) => {
      const el = $(id);
      if (el) el.onclick = () => redoTopology();
    });
    if ($("canvasQuickFocus")) $("canvasQuickFocus").onclick = () => {
      fitGraphToViewport();
      renderScene();
      toast("视图已适应画布", "ok");
    };
    if ($("canvasZoomSelect")) {
      $("canvasZoomSelect").onchange = () => {
        const pct = Number($("canvasZoomSelect").value || 100) / 100;
        const v = view();
        v.zoom = pct;
        state.topology.meta.viewport = v;
        renderScene();
        if ($("zoomLabel")) $("zoomLabel").textContent = Math.round(pct * 100) + "%";
      };
    }
    if ($("canvasViewGrid")) {
      $("canvasViewGrid").classList.toggle("is-active", state.showGrid);
      $("canvasViewGrid").onclick = () => {
        state.showGrid = !state.showGrid;
        $("canvasViewGrid").classList.toggle("is-active", state.showGrid);
        renderScene();
      };
    }
    if ($("canvasViewAlign")) $("canvasViewAlign").onclick = () => alignNodesToGrid();
    const collapseBtn = document.querySelector(".topology-collapse-btn");
    if (collapseBtn) collapseBtn.onclick = () => toggleSidebar();
    if ($("btnTopologyHelp")) {
      $("btnTopologyHelp").onclick = () => {
        toast("快捷键：Ctrl+Z 撤销 · Ctrl+Y 重做 · Ctrl+S 保存 · Delete 删除选中", "ok");
      };
    }
    if ($("btnTopologyNotify")) {
      $("btnTopologyNotify").onclick = () => toast("暂无新通知", "ok");
    }
    if ($("topologyCreateName")) {
      $("topologyCreateName").oninput = updateCreateCharCounts;
      updateCreateCharCounts();
    }
    if ($("topologyCreateDesc")) {
      $("topologyCreateDesc").oninput = updateCreateCharCounts;
      updateCreateCharCounts();
    }
    if ($("topologyManagerPrev")) {
      $("topologyManagerPrev").onclick = () => {
        if (state.topologyManagerPage > 1) {
          state.topologyManagerPage -= 1;
          renderTopologyManagerList();
        }
      };
    }
    if ($("topologyManagerNext")) {
      $("topologyManagerNext").onclick = () => {
        const total = Math.ceil((state.topologies || []).length / (state.topologyManagerPageSize || 10));
        if (state.topologyManagerPage < total) {
          state.topologyManagerPage += 1;
          renderTopologyManagerList();
        }
      };
    }
    if ($("btnManageBlueprints")) {
      $("btnManageBlueprints").onclick = () => {
        openTopologyManager();
        document.querySelectorAll("[data-topology-manager-tab]").forEach((tab) => {
          if (tab.getAttribute("data-topology-manager-tab") === "topologyManagerCreatePane") tab.click();
        });
        const bp = $("topologyCreateBlueprint");
        if (bp) bp.focus();
      };
    }
    if ($("btnExportLogs")) $("btnExportLogs").onclick = exportCurrentLogs;
    if ($("btnLogSettings")) {
      $("btnLogSettings").onclick = () => toast("日志保留最近 300 条，可在清空日志后重新采集", "ok");
    }
    if ($("btnLogFullscreen")) {
      $("btnLogFullscreen").onclick = () => {
        const card = document.querySelector(".topology-log-card");
        if (card) {
          card.classList.toggle("is-fullscreen");
          $("btnLogFullscreen").textContent = card.classList.contains("is-fullscreen") ? "退出全屏" : "全屏";
        }
      };
    }
    if ($("zoomResetBtn")) $("zoomResetBtn").onclick = () => {
      fitGraphToViewport();
      renderScene();
    };
    if ($("zoomInBtn")) $("zoomInBtn").onclick = () => { state.topology.meta.viewport.zoom = Math.min(2.5, Number(view().zoom || 1) * 1.1); renderScene(); };
    if ($("zoomOutBtn")) $("zoomOutBtn").onclick = () => { state.topology.meta.viewport.zoom = Math.max(0.3, Number(view().zoom || 1) * 0.9); renderScene(); };
    bindLayoutSpacingControls();
    if ($("btnValidateTopology")) $("btnValidateTopology").onclick = () => {
      const result = validateTopologyLocal();
      if (result.ok) {
        toast("拓扑校验通过", "ok");
      } else {
        toast("拓扑校验发现问题", "warn");
        appendJsonDetail("拓扑校验问题", result.problems);
      }
    };
    if ($("btnTopologyMore")) $("btnTopologyMore").onclick = openTopologyManager;

    const toolResetEl = $("toolReset");
    if (toolResetEl) toolResetEl.onclick = () => {
      fitGraphToViewport();
      renderScene();
      toast("视图已适应画布", "ok");
    };

    const toolSaveEl = $("toolSave");
    if (toolSaveEl) toolSaveEl.onclick = async () => {
      const d = await saveTopologyNow();
      toast((d && d.ok !== false) ? "拓扑已保存" : ((d && d.message) || "保存失败"), (d && d.ok !== false) ? "ok" : "error");
      if (d && d.ok !== false) logMode("拓扑保存成功");
    };


    const btnSaveNodeEl = $("btnSaveNode");
    if (btnSaveNodeEl) btnSaveNodeEl.onclick = saveNode;
    const btnSaveNodeToolsEl = $("btnSaveNodeTools");
    if (btnSaveNodeToolsEl) btnSaveNodeToolsEl.onclick = saveNode;
    const btnDeleteNodeEl = $("btnDeleteNode");
    if (btnDeleteNodeEl) btnDeleteNodeEl.onclick = deleteNode;
    if ($("btnDeleteNodeNodes")) $("btnDeleteNodeNodes").onclick = deleteNode;
    if ($("btnCopyEndpoint")) {
      $("btnCopyEndpoint").onclick = async () => {
        const val = String(($("insNodeEndpoints") || {}).value || "");
        if (!val) return;
        try {
          await navigator.clipboard.writeText(val);
          toast("已复制节点通信地址", "ok");
        } catch (_) {
          toast("复制失败", "error");
        }
      };
    }
    if ($("btnCopyEndpointBasic")) {
      $("btnCopyEndpointBasic").onclick = async () => {
        syncInspectorPortFieldsFromBasic();
        const val = String(($("insNodeEndpointsBasic") || {}).value || "");
        if (!val) return;
        try {
          await navigator.clipboard.writeText(val);
          toast("已复制节点通信地址", "ok");
        } catch (_) {
          toast("复制失败", "error");
        }
      };
    }
    if ($("btnInsServiceDetail")) {
      $("btnInsServiceDetail").onclick = () => {
        const tabs = document.querySelectorAll("[data-inspector-tab]");
        tabs.forEach((tab) => {
          if (tab.getAttribute("data-inspector-tab") === "agentPanel") tab.click();
        });
      };
    }
    if ($("btnInsDeployHistory")) {
      $("btnInsDeployHistory").onclick = () => {
        toast("部署历史将在后续版本接入", "info");
      };
    }
    if ($("insNodeRemotePortBasic")) {
      $("insNodeRemotePortBasic").oninput = () => syncInspectorPortFieldsFromBasic();
    }
    if ($("insNodeEndpointsBasic")) {
      $("insNodeEndpointsBasic").oninput = () => syncInspectorPortFieldsFromBasic();
    }
    if ($("btnStartRemoteNode")) $("btnStartRemoteNode").onclick = async () => {
      const nid = String((($("insNodeId") || {}).value || "")).trim();
      if (!nid) return;
      const r = await startRemoteForNode(nid);
      if (!r || r.ok === false) {
        toast((r && (r.message || r.error)) || "远端启动失败", "error");
        appendJsonDetail("节点远端启动失败 " + nid, r || {});
        return;
      }
      toast("远端启动已提交", "ok");
      logMode("节点远端启动提交成功: " + nid + " job_id=" + (r.job_id || "-"));
    };
    if ($("btnDeleteSelectedPort")) $("btnDeleteSelectedPort").onclick = deleteSelectedPort;
    if ($("btnPortInAdd")) $("btnPortInAdd").onclick = () => addPort("in");
    if ($("btnPortOutAdd")) $("btnPortOutAdd").onclick = () => addPort("out");
    if ($("btnPortInRemove")) $("btnPortInRemove").onclick = () => removePort("in");
    if ($("btnPortOutRemove")) $("btnPortOutRemove").onclick = () => removePort("out");
    if ($("btnDeleteEdge")) $("btnDeleteEdge").onclick = async () => {
      const id = state.selection.edgeId;
      if (!id) { toast("请先选中一条连线", "warn"); return; }
      await confirmStructuredDeleteEdge(id);
    };

    if ($("structuredAddClose")) $("structuredAddClose").onclick = closeStructuredAddMenu;
    const modeSelectEl = $("modeSelect");
    if (modeSelectEl) {
      modeSelectEl.onchange = () => {
        if (state.modeLocked) return;
        state.mode = modeSelectEl.value || "edit";
        applyModeUI();
        logMode("切换到" + (state.mode === "edit" ? "编辑" : state.mode === "run" ? "运行" : "测试") + "模式");
        saveModeState();
      };
    }
    const modeLockEl = $("modeLockBtn");
    if (modeLockEl) {
      modeLockEl.onclick = () => {
        state.modeLocked = true;
        applyModeUI();
        logMode("模式已锁定");
        toast("模式已锁定", "ok");
        saveModeState();
      };
    }
    const modeUnlockEl = $("modeUnlockBtn");
    if (modeUnlockEl) {
      modeUnlockEl.onclick = () => {
        state.modeLocked = false;
        applyModeUI();
        logMode("模式已解锁");
        toast("模式已解锁", "ok");
        saveModeState();
      };
    }
    const modeLockSwitch = $("modeLockSwitch");
    if (modeLockSwitch) {
      modeLockSwitch.onchange = () => {
        state.modeLocked = !modeLockSwitch.checked;
        applyModeUI();
        logMode(state.modeLocked ? "模式已锁定" : "模式已解锁");
        toast(state.modeLocked ? "模式已锁定" : "模式已解锁", "ok");
        saveModeState();
      };
    }
    if ($("btnRunStartAll")) $("btnRunStartAll").onclick = () => runFullLifecycle(true);
    if ($("btnRunStopAll")) $("btnRunStopAll").onclick = () => runFullLifecycle(false);
    if ($("btnTestSmoke")) $("btnTestSmoke").onclick = () => runSmokeOrStress(false);
    if ($("btnTestStress")) $("btnTestStress").onclick = () => runSmokeOrStress(true);
    if ($("btnRuntimeDetails")) {
      $("btnRuntimeDetails").onclick = (ev) => {
        ev.preventDefault();
        showRuntimeDetails();
      };
    }
    if ($("btnCopyNode")) $("btnCopyNode").onclick = async () => {
      const nid = String(($("insNodeId") || {}).value || "").trim();
      if (!nid) return;
      const resp = await OpsApi.cloneNode(Object.assign(currentScope(), { node_id: nid }));
      if (!resp || resp.ok === false) {
        toast((resp && (resp.message || resp.error)) || "复制节点失败", "error");
        return;
      }
      state.topology = resp.topology || state.topology;
      normalizeTopology();
      redrawGraph();
      renderRuntimeNodeList();
      toast("节点已复制", "ok");
    };
    if ($("btnDisableNode")) $("btnDisableNode").onclick = async () => {
      const nid = String(($("insNodeId") || {}).value || "").trim();
      if (!nid) return;
      const node = getNode(nid);
      const nextDisabled = !(((node || {}).ui || {}).disabled);
      const resp = await OpsApi.disableNode(Object.assign(currentScope(), { node_id: nid, disabled: nextDisabled }));
      if (!resp || resp.ok === false) {
        toast((resp && (resp.message || resp.error)) || "更新节点状态失败", "error");
        return;
      }
      state.topology = resp.topology || state.topology;
      normalizeTopology();
      redrawGraph();
      openNodeEditor(nid);
      toast(nextDisabled ? "节点已禁用" : "节点已恢复", "ok");
    };
    if ($("btnRestartNode")) $("btnRestartNode").onclick = () => {
      const nid = String(($("insNodeId") || {}).value || "").trim();
      if (!nid) return;
      const serviceId = String((state.serviceBindings || {})[nid] || "");
      const agentId = String((state.nodeBindings || {})[nid] || "");
      if (!serviceId) {
        $("btnStartRemoteNode").click();
        return;
      }
      OpsApi.serviceAction(Object.assign(currentScope(), {
        service_id: serviceId,
        agent_id: agentId,
        node_id: nid,
        action: "restart",
      })).then((resp) => {
        if (!resp || resp.ok === false) {
          toast((resp && (resp.message || resp.error)) || "重启服务失败", "error");
          return;
        }
        toast("服务重启任务已提交", "ok");
      });
    };
    if ($("btnProbeNode")) $("btnProbeNode").onclick = async () => {
      const nid = String(($("insNodeId") || {}).value || "").trim();
      if (!nid) return;
      await refreshAgentsIfNeeded(true);
      const raw = rawNodeMeta(nid);
      const box = $("nodeLogModalBody");
      if (box) box.textContent = JSON.stringify({ node_id: nid, node: raw, binding: (state.nodeBindings || {})[nid] || "", runtime: (runtimeById() || {})[nid] || null, agent: (state.agents || []).find((item) => String((item || {}).agent_id || "") === String((state.nodeBindings || {})[nid] || "")) || null }, null, 2);
      $("nodeLogModal").classList.remove("hidden");
      setModalOpen(true);
    };
    if ($("btnViewNodeLogs")) $("btnViewNodeLogs").onclick = async () => {
      const nid = String(($("insNodeId") || {}).value || "").trim();
      if (!nid) return;
      const resp = await OpsApi.nodeLogs(Object.assign(currentScope(), { node_id: nid, limit: 50 }));
      const box = $("nodeLogModalBody");
      if (box) box.textContent = JSON.stringify(resp || { ok: false, error: "empty_response" }, null, 2);
      $("nodeLogModal").classList.remove("hidden");
      setModalOpen(true);
    };
    const registryRows = $("topologyRegistryRows");
    if (registryRows) {
      registryRows.onclick = async (ev) => {
        const target = ev.target;
        if (!(target instanceof HTMLElement)) return;
        const openId = target.getAttribute("data-topology-open");
        const copyId = target.getAttribute("data-topology-copy");
        const defaultId = target.getAttribute("data-topology-default");
        const deleteId = target.getAttribute("data-topology-delete");
        if (openId) {
          const hit = (state.topologies || []).find((item) => String(item.topology_id || "") === String(openId)) || {};
          closeTopologyManager();
          await switchScope({ project_id: state.projectId, env_key: String(hit.env_key || state.envKey), topology_id: String(openId) });
          return;
        }
        if (copyId) {
          if ($("topologyCopySource")) $("topologyCopySource").value = String(copyId);
          document.querySelectorAll("[data-topology-manager-tab]").forEach((tab) => {
            if (tab.getAttribute("data-topology-manager-tab") === "topologyManagerCreatePane") tab.click();
          });
          return;
        }
        if (defaultId) {
          await setDefaultTopology(String(defaultId));
          return;
        }
        if (deleteId) {
          await deleteTopology(String(deleteId));
        }
      };
    }
    if ($("btnDeleteEdgeInline")) $("btnDeleteEdgeInline").onclick = () => {
      if (state.selection.edgeId) confirmStructuredDeleteEdge(state.selection.edgeId);
      else toast("请先点击选择一条连线", "warn");
    };
    document.querySelectorAll('input[name="testScope"]').forEach((inp) => {
      inp.onchange = syncTestScopeUI;
    });
    if ($("testStartNode")) $("testStartNode").onchange = computePathHighlight;
    if ($("testEndNode")) $("testEndNode").onchange = computePathHighlight;

    const shell = $("canvasShell");
    if (!shell) return;
    shell.addEventListener("wheel", (ev) => {
      ev.preventDefault();
      const v = view();
      const p = world(ev.clientX, ev.clientY);
      const z = Math.max(0.3, Math.min(2.5, v.zoom * (ev.deltaY < 0 ? 1.08 : 0.92)));
      const r = shell.getBoundingClientRect();
      state.topology.meta.viewport = { x: ev.clientX - r.left - p.x * z, y: ev.clientY - r.top - p.y * z, zoom: z };
      renderScene();
    }, { passive: false });

    shell.addEventListener("mousedown", (ev) => {
      if (ev.button === 1 || state.spaceDown) {
        state.pan = { sx: ev.clientX, sy: ev.clientY, v: view() };
        ev.preventDefault();
        return;
      }
      if (ev.target === shell || (ev.target && ev.target.classList && ev.target.classList.contains("ops-grid-bg"))) {
        state.selection.nodes.clear();
        state.selection.edgeId = "";
        redrawGraph();
      }
    });

    window.addEventListener("keydown", (ev) => {
      if (ev.code === "Space") state.spaceDown = true;
      if ((ev.ctrlKey || ev.metaKey) && String(ev.key).toLowerCase() === "0") {
        ev.preventDefault();
        state.topology.meta.viewport = { x: 0, y: 0, zoom: 1 };
        renderScene();
      }
      if ((ev.ctrlKey || ev.metaKey) && String(ev.key).toLowerCase() === "z" && !ev.shiftKey) {
        ev.preventDefault();
        undoTopology();
      }
      if ((ev.ctrlKey || ev.metaKey) && (String(ev.key).toLowerCase() === "y" || (String(ev.key).toLowerCase() === "z" && ev.shiftKey))) {
        ev.preventDefault();
        redoTopology();
      }
      if ((ev.ctrlKey || ev.metaKey) && String(ev.key).toLowerCase() === "s") {
        ev.preventDefault();
        if ($("toolSave")) $("toolSave").click();
      }
      if (ev.key === "Delete" && state.selection.edgeId) $("btnDeleteEdge").click();
      if (ev.key === "Delete" && !state.selection.edgeId && state.selection.nodes.size) deleteSelectedNode();
      if (ev.key === "Escape") { closeStructuredAddMenu(); closeNodeEditor(); }
    });

    window.addEventListener("keyup", (ev) => { if (ev.code === "Space") state.spaceDown = false; });
    document.addEventListener("visibilitychange", () => {
      dbg("visibilitychange", { hidden: document.hidden, mode: state.mode, runtimeSteady: !!state.runtimeSteady, runId: state.runtimeRunId || "" });
    });
    window.addEventListener("beforeunload", () => {
      dbg("beforeunload", { mode: state.mode, runtimeSteady: !!state.runtimeSteady, runId: state.runtimeRunId || "" });
    });

    window.addEventListener("mousemove", (ev) => {
      if (state.pan) {
        state.topology.meta.viewport = { x: state.pan.v.x + (ev.clientX - state.pan.sx), y: state.pan.v.y + (ev.clientY - state.pan.sy), zoom: state.pan.v.zoom };
        renderScene();
        return;
      }
    });

    window.addEventListener("mouseup", async (ev) => {
      if (state.pan) { state.pan = null; return; }
    });

    shell.ondragover = (ev) => ev.preventDefault();
    shell.ondrop = async (ev) => {
      ev.preventDefault();
      const pid = ev.dataTransfer.getData("text/plain");
      if (!pid) return;
      state.activePresetId = pid;
      await addPresetAt(world(ev.clientX, ev.clientY));
    };
  }

  function maybeOpenStructuredAddFromQuery() {
    try {
      const from = String(state.acceptanceStructuredAddFrom || "").trim();
      if (!from) return;
      state.acceptanceStructuredAddFrom = "";
      if (state.mode !== "edit") {
        state.mode = "edit";
        state.modeLocked = false;
        applyModeUI();
      }
      openStructuredAddMenu(from);
    } catch (_) {}
  }

  async function boot() {
    const page = document.querySelector(".ops-topology-app");
    const ds = (page && page.dataset) ? page.dataset : {};
    state.projectId = String(ds.projectId || "");
    state.envKey = String(ds.envKey || "production");
    state.topologyId = String(ds.topologyId || "");
    try {
      state.acceptanceStructuredAddFrom = new URLSearchParams(location.search).get("structured_add_from") || "";
    } catch (_) {
      state.acceptanceStructuredAddFrom = "";
    }
    loadModeState();
    loadRuntimeState();
    bindEvents();
    await loadAll();
    startAgentsRealtimeTick();
    const act = await OpsApi.runtimeFlowActive(currentScope());
    if (act && act.ok !== false && act.active && act.run_id) {
      state.mode = "run";
      state.modeLocked = true;
      state.runtimeRunId = String(act.run_id || "");
      state.runtimeRequestedOp = "start";
      state.runtimeSteady = true;
      applyModeUI();
      logMode("后端检测为运行中，自动恢复运行跟踪: " + state.runtimeRunId, "warn");
      await pollRuntimeRun(state.runtimeRunId);
      stopRuntimePolling();
      state.runtimePollTimer = setInterval(() => { pollRuntimeRun(state.runtimeRunId); }, 1200);
      maybeOpenStructuredAddFromQuery();
      return;
    }
    if (state.mode === "run" && state.runtimeRunId) {
      logMode("检测到刷新前运行态，自动恢复运行跟踪: " + state.runtimeRunId, "warn");
      await pollRuntimeRun(state.runtimeRunId);
      stopRuntimePolling();
      state.runtimePollTimer = setInterval(() => { pollRuntimeRun(state.runtimeRunId); }, 1200);
    }
    maybeOpenStructuredAddFromQuery();
  }

  boot().catch((e) => {
    console.error(e);
    toast("拓扑工作台初始化失败，请刷新后重试", "error");
  });
})();
