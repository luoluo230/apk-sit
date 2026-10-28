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
    runtimeStopping: false,
    runtimeStarting: false,
    runtimeAwaitLive: false,
    runtimeAwaitLiveUntil: 0,
    runtimeLiveWaitTimer: null,
    runtimeLastStatus: "",
    runtimeRequestedOp: "",
    runtimePartialRecovery: false,
    runtimeEdgesLogged: false,
    debugSeq: 0,
    agentsRefreshAt: 0,
    agentsHydrated: false,
    bindingsHydrated: false,
    agentsTickTimer: null,
    lockedMode: "",
    autoRunModeLogged: false,
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
      edgesEnabled: false,
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
  const MODE_LABELS = { edit: "编辑模式", run: "运行模式", test: "测试模式" };
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

