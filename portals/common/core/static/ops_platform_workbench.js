(function () {
  const ROLE_OPTIONS = ["gateway", "business", "pressure", "database", "cache", "mq", "search", "scheduler", "admin", "edge", "analytics"];
  const STATUS_OPTIONS = ["normal", "observe", "degraded", "error", "offline"];
  const STATUS_LABELS = { normal: "正常", observe: "观察", degraded: "退化", error: "异常", offline: "离线" };
  const ROLE_COLOR = {
    gateway: { border: "#3b82f6", bg1: "#eff6ff", bg2: "#dbeafe" },
    business: { border: "#0ea5e9", bg1: "#ecfeff", bg2: "#cffafe" },
    scheduler: { border: "#6366f1", bg1: "#eef2ff", bg2: "#e0e7ff" },
    pressure: { border: "#f59e0b", bg1: "#fffbeb", bg2: "#fef3c7" },
    database: { border: "#10b981", bg1: "#ecfdf5", bg2: "#d1fae5" },
    cache: { border: "#14b8a6", bg1: "#f0fdfa", bg2: "#ccfbf1" },
    mq: { border: "#8b5cf6", bg1: "#f5f3ff", bg2: "#ede9fe" },
    search: { border: "#f97316", bg1: "#fff7ed", bg2: "#ffedd5" },
    admin: { border: "#64748b", bg1: "#f8fafc", bg2: "#e2e8f0" },
    edge: { border: "#2563eb", bg1: "#eff6ff", bg2: "#dbeafe" },
    analytics: { border: "#06b6d4", bg1: "#ecfeff", bg2: "#cffafe" },
  };
  const KINDS = ["entry", "standard", "terminal"];
  function roleColor(role) {
    const key = String(role || "").toLowerCase();
    const p = ROLE_COLOR[key] || ROLE_COLOR.business || { border: "#3b82f6" };
    return p.border || "#3b82f6";
  }
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (s) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[s]));

  const state = {
    projectId: "",
    nodesRaw: [],
    overviewNodes: [],
    topology: { nodes: [], edges: [], meta: { viewport: { x: 0, y: 0, zoom: 1 } } },
    presets: [],
    blueprints: [],
    activePresetId: "",
    presetCollapsed: {},
    selection: { nodes: new Set(), edgeId: "" },
    nodeBindings: {},
    agents: [],
    drag: null,
    pan: null,
    spaceDown: false,
    structuredAddCtx: null,
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
  };
  const MODE_STORAGE_KEY = "ops_topology_mode_v1";
  const RUNTIME_STORAGE_KEY = "ops_topology_runtime_v1";

  function dbg(tag, payload) {
    state.debugSeq += 1;
    const body = payload ? " " + JSON.stringify(payload) : "";
    const line = "[DBG#" + state.debugSeq + "] " + tag + body;
    try { console.debug(line); } catch (_) {}
    logMode(line, "warn");
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
  function runtimeName(id) {
    const n = getNode(id);
    return String((n && (n.name || n.node_name || n.title || n.id)) || id || "-");
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
    const prefix = level === "error" ? "[失败]" : (level === "warn" ? "[提示]" : "[信息]");
    const line = document.createElement("div");
    line.className = "mode-log-line " + (level === "error" ? "error" : (level === "warn" ? "warn" : "info"));
    line.textContent = "[" + t + "] " + prefix + " " + message;
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
        return { tps: qps || 1, latency: latency || 1, err: fail ? 12 : 0 };
      }
    }
    const s = nodeSeed(edgeId) + Math.floor(Date.now() / 1200) + (state.flowViz.seed || 0);
    const fail = ["FAILED", "TIMEOUT", "CANCELED"].includes(String(status || "").toUpperCase());
    const tps = Math.max(6, (s % 380) + (fail ? 0 : 40));
    const latency = Math.max(8, (s % 70) + (fail ? 55 : 12));
    const err = fail ? Math.min(42, (s % 35) + 6) : Math.max(0, (s % 5));
    return { tps, latency, err };
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

  async function pollRuntimeRun(runId) {
    if (!runId) return;
    await refreshAgentsIfNeeded(false);
    const d = await OpsApi.runtimeFlowStatus(runId);
    if (!d || d.ok === false) {
      logMode("运行状态拉取失败: " + ((d && (d.message || d.error)) || "unknown"), "error");
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
    redrawGraph();
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
    if (KINDS.includes(c)) return c;
    const r = String(role || "").toLowerCase();
    if (["gateway", "edge"].includes(r)) return "entry";
    if (["database", "cache", "mq", "search"].includes(r)) return "terminal";
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

  function layoutStructuredGraph() {
    if (!state.topology || !Array.isArray(state.topology.nodes)) return;
    if (!state.topology.meta || typeof state.topology.meta !== "object") state.topology.meta = {};
    state.topology.meta.layout_mode = "structured";
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
      if (rank[n.id] == null) {
        maxRank += 1;
        rank[n.id] = maxRank;
      }
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
    const startX = 120;
    const startY = 118;
    const rankGap = 340;
    const rowGap = 150;
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
    const x = Number(node.ui.x || 0) + (side === "out" ? Number(node.ui.w || 240) : 0);
    const y = Number(node.ui.y || 0) + Number(node.ui.h || 104) / 2;
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
    const midX = Math.round((a.x + b.x) / 2);
    const turnX = b.x > a.x ? Math.max(a.x + minGap, midX) : a.x + minGap;
    const ay = Math.round(a.y + offset);
    const by = Math.round(b.y + offset);
    if (structuredMode()) {
      edge.ui = Object.assign({}, edge.ui || {}, {
        route: [
          { x: Math.round(a.x), y: Math.round(a.y) },
          { x: turnX, y: Math.round(a.y) },
          { x: turnX, y: Math.round(b.y) },
          { x: Math.round(b.x), y: Math.round(b.y) },
        ],
      });
      return "M " + Math.round(a.x) + " " + Math.round(a.y)
        + " H " + turnX
        + " V " + Math.round(b.y)
        + " H " + Math.round(b.x);
    }
    return "M " + Math.round(a.x) + " " + ay
      + " H " + turnX
      + " V " + by
      + " H " + Math.round(b.x);
  }

  function edgeMid(edge) {
    const aNode = getNode(edge.from);
    const bNode = getNode(edge.to);
    if (!aNode || !bNode) return null;
    const a = structuredMode() ? structuredAnchor(aNode, "out") : portAnchor(aNode, "out", edge.from_port);
    const b = structuredMode() ? structuredAnchor(bNode, "in") : portAnchor(bNode, "in", edge.to_port);
    const offset = linkOffset(edge);
    const minGap = 96;
    const midX = Math.round((a.x + b.x) / 2);
    const turnX = b.x > a.x ? Math.max(a.x + minGap, midX) : a.x + minGap;
    return { x: turnX, y: Math.round((a.y + b.y) / 2 + offset) };
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
      return {
        id,
        role,
        kind,
        desc: String(prev.desc || raw.description || ""),
        bizStatus: String(prev.bizStatus || "normal"),
        owner: String(prev.owner || raw.owner || ""),
        tags: Array.isArray(prev.tags) ? prev.tags : [],
        ui: {
          x: Number(ui.x != null ? ui.x : 90 + (i % 5) * 280),
          y: Number(ui.y != null ? ui.y : 100 + Math.floor(i / 5) * 170),
          w: Number(ui.w || 240),
          h: Number(ui.h || 96),
          color: String(ui.color || "#0f172a"),
          ports: normalizePorts(kind, ui.ports),
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
    $("zoomLabel").textContent = Math.round(v.zoom * 100) + "%";
  }

  function setTopologyHint(text, type) {
    const el = $("topologyLoadHint");
    if (!el) return;
    el.textContent = String(text || "");
    el.className = "topology-load-hint" + (type ? (" " + type) : "");
    el.style.display = text ? "" : "none";
  }

  function bindLeftTabs() {
    const tabs = Array.from(document.querySelectorAll("[data-topology-left-tab]"));
    const panels = Array.from(document.querySelectorAll("[data-left-panel]"));
    if (!tabs.length || !panels.length) return;
    const activate = (name) => {
      tabs.forEach((tab) => {
        const on = tab.getAttribute("data-topology-left-tab") === name;
        tab.classList.toggle("active", on);
        tab.setAttribute("aria-selected", on ? "true" : "false");
      });
      panels.forEach((panel) => {
        panel.classList.toggle("is-hidden", panel.getAttribute("data-left-panel") !== name);
      });
    };
    tabs.forEach((tab) => {
      tab.onclick = () => activate(tab.getAttribute("data-topology-left-tab") || "tools");
    });
    activate("tools");
  }

  function redrawGraph() {
    drawNodes();
    drawEdges();
  }

  function drawEdges() {
    const svg = $("edgeSvg");
    svg.innerHTML = "";
    let visible = 0;
    let skipped = 0;
    (state.topology.edges || []).forEach((edge) => {
      const d = edgePath(edge);
      if (!d) { skipped += 1; return; }
      visible += 1;
      const hit = document.createElementNS("http://www.w3.org/2000/svg", "path");
      hit.setAttribute("d", d);
      hit.setAttribute("class", "edge-hit");
      hit.onclick = (ev) => { ev.stopPropagation(); state.selection.edgeId = edge.id; state.selection.nodes.clear(); redrawGraph(); };
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      const hl = state.highlight.edges.has(edge.id) ? " hl" : "";
      const flow = state.flowViz.edges.has(edge.id) ? " flow" : "";
      const fail = (state.flowViz.statusByNode[String(edge.to)] && ["FAILED", "TIMEOUT", "CANCELED"].includes(String(state.flowViz.statusByNode[String(edge.to)]).toUpperCase())) ? " fail" : "";
      path.setAttribute("class", "edge" + hl + flow + fail + (state.selection.edgeId === edge.id ? " sel" : ""));
      if (!flow && !hl && !fail) {
        const src = getNode(edge.from);
        path.style.stroke = roleColor(src && src.role);
      }
      path.onclick = (ev) => { ev.stopPropagation(); state.selection.edgeId = edge.id; state.selection.nodes.clear(); redrawGraph(); };
      svg.appendChild(hit);
      svg.appendChild(path);
      const m = edgeMid(edge);
      if (m) {
        const label = document.createElementNS("http://www.w3.org/2000/svg", "g");
        label.setAttribute("class", "edge-route-label");
        const txtValue = runtimeName(edge.from) + "." + String(edge.from_port || "out-1") + " → " + runtimeName(edge.to) + "." + String(edge.to_port || "in-1");
        const labelWidth = Math.max(120, Math.min(260, txtValue.length * 6 + 18));
        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", String(Math.round(m.x - labelWidth / 2)));
        rect.setAttribute("y", String(Math.round(m.y - 28)));
        rect.setAttribute("width", String(labelWidth));
        rect.setAttribute("height", "20");
        rect.setAttribute("rx", "10");
        const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
        txt.setAttribute("x", String(Math.round(m.x)));
        txt.setAttribute("y", String(Math.round(m.y - 14)));
        txt.setAttribute("text-anchor", "middle");
        txt.textContent = txtValue;
        label.appendChild(rect);
        label.appendChild(txt);
        svg.appendChild(label);
        if (isEditMode()) {
          const del = document.createElementNS("http://www.w3.org/2000/svg", "g");
          del.setAttribute("class", "edge-remove");
          del.setAttribute("transform", "translate(" + Math.round(m.x) + "," + Math.round(m.y - 42) + ")");
          del.setAttribute("title", "删除连线");
          const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
          c.setAttribute("r", "10");
          const minus = document.createElementNS("http://www.w3.org/2000/svg", "text");
          minus.setAttribute("text-anchor", "middle");
          minus.setAttribute("y", "4");
          minus.textContent = "-";
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
      logMode("连线重绘: 数据=" + ((state.topology.edges || []).length) + " 可见=" + visible + " 跳过=" + skipped, skipped ? "warn" : "info");
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
      const aid = String((state.nodeBindings || {})[n.id] || "");
      const ag = state.agents.find((x) => String(x.agent_id || "") === aid) || null;
      const bindText = ag ? ("Agent: " + (ag.display_name || ag.agent_id)) : "未绑定Agent";
      const bindCls = ag ? "state-ok" : "state-warn";
      const agHealth = agentHealthLabel(ag);
      const st = String(n.bizStatus || "normal");
      const stLabel = agHealth.cls === "err" ? "心跳过期" : (agHealth.cls === "warn" ? "Agent异常" : (STATUS_LABELS[st] || st));
      const flowSt = String((state.flowViz.statusByNode || {})[n.id] || "").toUpperCase();
      const isFlow = state.flowViz.nodes.has(n.id);
      const metrics = nodeMetrics(n.id, flowSt);
      const palette = ROLE_COLOR[String(n.role || "").toLowerCase()] || { border: "#9ab6e5", bg1: "#ffffff", bg2: "#f4f8ff" };

      const el = document.createElement("div");
      el.className = "node structured-node"
        + (state.selection.nodes.has(n.id) ? " sel" : "")
        + (state.highlight.nodes.has(n.id) ? " hl" : "")
        + (isFlow ? " flow-active" : "")
        + (["FAILED", "TIMEOUT", "CANCELED"].includes(flowSt) ? " flow-fail" : "")
        + (flowSt === "SUCCESS" ? " flow-ok" : "");
      el.style.left = n.ui.x + "px";
      el.style.top = n.ui.y + "px";
      el.style.width = n.ui.w + "px";
      el.style.minHeight = n.ui.h + "px";
      el.style.borderColor = palette.border;
      el.style.background = "linear-gradient(165deg," + palette.bg1 + "," + palette.bg2 + ")";
      el.innerHTML = '<div class="node-role-strip" style="background:' + esc(palette.border) + '"></div>'
        + drawPorts(n, "in") + drawPorts(n, "out")
        + (isEditMode() ? '<button class="node-remove-btn" type="button" data-node-id="' + esc(n.id) + '" title="删除节点">-</button>' : "")
        + (isEditMode() ? '<button class="node-add-btn" type="button" data-node-id="' + esc(n.id) + '" title="添加下游">+</button>' : "")
        + '<div class="t">' + esc((runtime[n.id] || {}).name || n.id) + '</div>'
        + '<div class="s">' + esc(n.role) + '</div>'
        + '<div class="s node-status-line status-' + esc(agHealth.cls) + '">状态: ' + esc(stLabel) + '</div>'
        + '<div class="s">' + esc(n.owner || "-") + '</div>'
        + '<div class="state-pill ' + bindCls + '" style="margin-top:4px">' + esc(bindText) + "</div>"
        + '<div class="state-pill state-' + esc(agHealth.cls) + '" style="margin-top:4px">' + esc(agHealth.text) + "</div>"
        + (isFlow ? (
          '<div class="node-metrics">'
          + '<div class="metric-src ' + ((metrics.source === "real" || metrics.source === "local" || metrics.source === "agent") ? "real" : "mock") + '">' + ((metrics.source === "real" || metrics.source === "local" || metrics.source === "agent") ? "实时" : "实时缺失") + (metrics.rtt ? (" · RTT " + Math.round(metrics.rtt) + "ms") : "") + '</div>'
          + '<div class="metric-row"><span>CPU</span><div class="metric-bar"><i style="width:' + Math.round(metrics.cpu) + '%"></i></div><em>' + Math.round(metrics.cpu) + '%</em></div>'
          + '<div class="metric-row"><span>MEM</span><div class="metric-bar"><i style="width:' + Math.round(metrics.mem) + '%"></i></div><em>' + Math.round(metrics.mem) + '%</em></div>'
          + '<div class="metric-row"><span>QPS</span><div class="metric-bar"><i style="width:' + Math.round(metrics.qps) + '%"></i></div><em>' + Math.round(metrics.qps) + '</em></div>'
          + '<div class="metric-flame"><b style="width:' + Math.max(metrics.cpu, metrics.mem) + '%"></b><b style="width:' + Math.max(8, metrics.qps * 0.9) + '%"></b><b style="width:' + Math.max(6, metrics.cpu * 0.7) + '%"></b></div>'
          + '</div>'
        ) : "");
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
    const box = $("runtimeNodeList");
    if (!box) return;
    const runtime = runtimeById();
    box.innerHTML = "";
    (state.topology.nodes || []).forEach((n) => {
      const item = document.createElement("div");
      item.className = "runtime-node-item";
      item.innerHTML = '<div class="id">' + esc((runtime[n.id] || {}).name || n.id) + '</div><div class="meta">' + esc(n.role) + " / " + esc(n.kind) + "</div>";
      item.onclick = () => openNodeEditor(n.id);
      box.appendChild(item);
    });
  }

  function canStructuredConnect(fromNodeId, toLike) {
    const fromNode = getNode(fromNodeId);
    if (!fromNode || !toLike) return { ok: false, msg: "节点不存在" };
    const toId = String(toLike.id || "");
    if (toId && toId === fromNodeId) return { ok: false, msg: "不能连接同一个节点" };
    const fromMeta = rawNodeMeta(fromNodeId);
    const fromRole = String(fromMeta.role || fromNode.role || "");
    const toRole = String(toLike.role || "");
    const toKind = inferKind(toRole, toLike.kind);
    if (fromNode.kind === "terminal" || toKind === "entry") return { ok: false, msg: "节点语义方向不允许连接" };
    const allowDown = Array.isArray(fromMeta.allowed_downstream_roles) ? fromMeta.allowed_downstream_roles.map(String) : [];
    const allowUp = Array.isArray(toLike.allowed_upstream_roles)
      ? toLike.allowed_upstream_roles.map(String)
      : (Array.isArray(toLike.fixed_upstream_roles) ? toLike.fixed_upstream_roles.map(String) : []);
    if (allowDown.length && toRole && !allowDown.includes(toRole)) return { ok: false, msg: "当前节点规则不允许该下游角色" };
    if (allowUp.length && fromRole && !allowUp.includes(fromRole)) return { ok: false, msg: "目标节点不接受该上游角色" };
    if (toId && (state.topology.edges || []).some((e) => String(e.from) === String(fromNodeId) && String(e.to) === toId)) {
      return { ok: false, msg: "两个节点之间已存在连线" };
    }
    return { ok: true };
  }

  function legalExistingTargetsForNode(nodeId) {
    return (state.topology.nodes || [])
      .filter((n) => n && n.id && n.id !== nodeId)
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
        allowed_upstream_roles: p.fixed_upstream_roles || [],
        allowed_downstream_roles: p.fixed_downstream_roles || [],
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
    redrawGraph();
    renderRuntimeNodeList();
    fillTestNodeOptions();
    toast(successText || d.message || "操作成功", "ok");
    logMode(successText || d.message || "结构化操作成功");
    return true;
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
    if (!modal || !existingBox || !presetBox) return;
    if (title) title.textContent = "从 “" + runtimeName(nodeId) + "” 添加下游";
    const existing = legalExistingTargetsForNode(nodeId);
    const presets = legalPresetsForNode(nodeId);
    existingBox.innerHTML = existing.length ? "" : '<div class="preset-empty">当前拓扑中没有可连接的已有节点</div>';
    existing.forEach((n) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "structured-menu-item";
      item.innerHTML = '<b>' + esc(runtimeName(n.id)) + '</b><span>' + esc((n.role || "-") + " / " + (n.kind || "-")) + '</span>';
      item.onclick = () => structuredAddExistingTarget(nodeId, n.id);
      existingBox.appendChild(item);
    });
    presetBox.innerHTML = presets.length ? "" : '<div class="preset-empty">当前节点没有可添加的下游类型</div>';
    const grouped = {};
    presets.forEach((p) => { const g = presetGroup(p.role); if (!grouped[g]) grouped[g] = []; grouped[g].push(p); });
    Object.keys(grouped).sort().forEach((g) => {
      const sec = document.createElement("div");
      sec.className = "structured-menu-group";
      sec.innerHTML = '<div class="structured-menu-group-title">' + esc(g) + '</div>';
      grouped[g].forEach((p) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "structured-menu-item";
        item.innerHTML = '<b>' + esc(p.name || p.preset_id || "-") + '</b><span>' + esc((p.role || "-") + " / " + inferKind(p.role, p.kind)) + '</span>';
        item.onclick = () => structuredAddNewTarget(nodeId, p.preset_id);
        sec.appendChild(item);
      });
      presetBox.appendChild(sec);
    });
    modal.classList.remove("hidden");
  }

  function closeStructuredAddMenu() {
    const modal = $("structuredAddModal");
    if (modal) modal.classList.add("hidden");
    state.structuredAddCtx = null;
  }

  async function structuredAddExistingTarget(fromNodeId, toNodeId) {
    const d = await OpsApi.structuredAddExistingTarget({ project_id: state.projectId, from_node_id: fromNodeId, to_node_id: toNodeId });
    if (applyStructuredTopologyResponse(d, "已连接已有下游节点")) closeStructuredAddMenu();
  }

  async function structuredAddNewTarget(fromNodeId, presetId) {
    const d = await OpsApi.structuredAddNewTarget({ project_id: state.projectId, from_node_id: fromNodeId, preset_id: presetId });
    if (applyStructuredTopologyResponse(d, "已新增并连接下游节点")) closeStructuredAddMenu();
  }

  async function confirmStructuredDeleteNode(nodeId) {
    if (!isEditMode()) { toast("运行/测试模式不可删除节点", "warn"); return; }
    const name = runtimeName(nodeId);
    if (!window.confirm("确认删除节点 “" + name + "”？\n\n删除会同时移除相关连线，关键链路会被系统拦截。")) return;
    const d = await OpsApi.structuredDeleteNode({ node_id: nodeId, project_id: state.projectId });
    applyStructuredTopologyResponse(d, "节点已删除");
  }

  async function confirmStructuredDeleteEdge(edgeId) {
    if (!isEditMode()) { toast("运行/测试模式不可删除连线", "warn"); return; }
    const edge = (state.topology.edges || []).find((e) => String(e.id) === String(edgeId));
    const label = edge ? (runtimeName(edge.from) + " → " + runtimeName(edge.to)) : edgeId;
    if (!window.confirm("确认删除连线 “" + label + "”？\n\n关键链路会被系统拦截。")) return;
    const d = await OpsApi.structuredDeleteEdge({ edge_id: edgeId, project_id: state.projectId });
    applyStructuredTopologyResponse(d, "连线已删除");
  }

  function presetGroup(role) {
    const r = String(role || "").toLowerCase();
    if (["gateway", "edge", "admin"].includes(r)) return "入口与边缘";
    if (["business", "scheduler", "analytics"].includes(r)) return "业务与调度";
    if (["pressure"].includes(r)) return "压测与实验";
    if (["database", "cache", "mq", "search"].includes(r)) return "数据与中间件";
    return "其他";
  }

  function renderPresets() {
    const box = $("presetList");
    const kw = String($("presetSearch").value || "").toLowerCase().trim();
    const category = $("presetCategoryFilter") ? String($("presetCategoryFilter").value || "") : "";
    box.innerHTML = "";
    const rows = (state.presets || []).filter((p) => {
      const group = presetGroup(p.role);
      const hay = (String(p.name || "") + " " + String(p.role || "") + " " + String(p.preset_id || "")).toLowerCase();
      return (!kw || hay.includes(kw)) && (!category || group === category);
    });
    const active = (state.presets || []).find((x) => x.preset_id === state.activePresetId);
    $("presetQuickBar").textContent = active ? ("已选择模板: " + (active.name || active.preset_id) + " / " + (active.role || "-")) : "未选择模板";
    if (!rows.length) { box.innerHTML = '<div class="preset-empty">没有匹配模板</div>'; return; }

    const groups = {};
    rows.forEach((p) => { const g = presetGroup(p.role); if (!groups[g]) groups[g] = []; groups[g].push(p); });

    Object.keys(groups).forEach((g) => {
      const sec = document.createElement("div");
      sec.className = "preset-group";
      const collapsed = !!state.presetCollapsed[g];
      const hd = document.createElement("div");
      hd.className = "preset-group-hd";
      hd.innerHTML = "<span>" + (collapsed ? "▶" : "▼") + " " + esc(g) + '</span><span class="preset-group-count">' + groups[g].length + "</span>";
      hd.onclick = () => { state.presetCollapsed[g] = !state.presetCollapsed[g]; renderPresets(); };
      sec.appendChild(hd);

      if (!collapsed) {
        groups[g].forEach((p) => {
          const card = document.createElement("div");
          card.className = "preset-card" + (state.activePresetId === p.preset_id ? " active" : "");
          card.draggable = true;
          card.innerHTML = '<div class="name">' + esc(p.name || "-") + '</div><div class="meta">' + esc((p.role || "-") + " / " + inferKind(p.role, p.kind)) + '</div><div class="desc">' + esc(p.default_desc || "暂无说明") + '</div><div class="act"><span class="tag">' + esc(p.preset_id || "-") + '</span><button type="button" class="add-btn">添加到流程</button></div>';
          card.onclick = () => { state.activePresetId = p.preset_id; renderPresets(); };
          card.ondragstart = (e) => e.dataTransfer.setData("text/plain", p.preset_id);
          card.querySelector(".add-btn").onclick = async (ev) => { ev.stopPropagation(); state.activePresetId = p.preset_id; await addPresetAt(centerWorld()); };
          sec.appendChild(card);
        });
      }

      box.appendChild(sec);
    });
  }

  async function addPresetAt(worldPos) {
    if (isTestMode()) { toast("测试模式禁止新增节点", "warn"); return; }
    const p = (state.presets || []).find((x) => x.preset_id === state.activePresetId);
    if (!p) return;
    const d = await OpsApi.addNodeFromPreset({ preset_id: String(p.preset_id || ""), name: "", server_id: "", project_id: state.projectId, owner: "", env: "prod", channel: "", description: p.default_desc || "" });
    if (!d.ok) { toast(d.message || "Add node failed", "error"); logMode("新增节点失败: " + (d.message || d.error || "unknown"), "error"); return; }
    await loadAll();
    if (d.node && d.node.id) {
      const n = getNode(d.node.id);
      if (n) {
        n.ui.x = Math.round(worldPos.x / 8) * 8;
        n.ui.y = Math.round(worldPos.y / 8) * 8;
        await OpsApi.saveTopology(state.topology);
        redrawGraph(); renderRuntimeNodeList();
        logMode("新增节点成功: " + d.node.id);
      }
    }
  }

  function renderPortLists(node) {
    const inBox = $("inPortList");
    const outBox = $("outPortList");
    if (!inBox || !outBox || !node) return;
    const render = (side, box) => {
      const ports = ((node.ui && node.ui.ports && node.ui.ports[side]) || []);
      if (!ports.length) {
        box.innerHTML = '<span class="state-pill state-warn">无 ' + side + " 端口</span>";
        return;
      }
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
    };
    render("in", inBox);
    render("out", outBox);
  }

  function fillAgentSelect(nodeId) {
    const sel = $("insNodePrimaryAgent");
    const agMeta = $("insNodeAgentMeta");
    sel.innerHTML = '<option value="">未绑定</option>';
    state.agents.forEach((a) => {
      const op = document.createElement("option");
      op.value = String(a.agent_id || "");
      op.textContent = (a.display_name || a.agent_id || "-") + " (" + (a.device_id || "-") + ")";
      sel.appendChild(op);
    });
    const current = String((state.nodeBindings || {})[nodeId] || "");
    sel.value = current;
    const hit = state.agents.find((a) => String(a.agent_id || "") === current);
    const metaText = (x) => {
      if (!x) return "未绑定";
      const h = agentHealthLabel(x);
      return h.text + " / " + (x.device_id || "-") + " / " + (x.host_name || "-") + ":" + (x.port || "-") + " / " + (x.last_seen || "-");
    };
    agMeta.value = metaText(hit);
    sel.onchange = () => {
      const aid = String(sel.value || "");
      const x = state.agents.find((a) => String(a.agent_id || "") === aid);
      agMeta.value = metaText(x);
    };
  }

  function openNodeEditor(nodeId) {
    const n = getNode(nodeId);
    if (!n) return;
    state.selection.nodes = new Set([nodeId]);
    state.selection.edgeId = "";
    $("insNodeId").value = n.id;
    $("insNodeRole").value = n.role;
    $("insNodeBizStatus").value = n.bizStatus;
    $("insNodeKind").value = n.kind;
    $("insNodeOwner").value = n.owner;
    $("insNodeDesc").value = n.desc;
    $("insNodeColor").value = n.ui.color || "#0f172a";
    $("insNodeTags").value = (n.tags || []).join(",");
    $("insNodeRemotePort").value = String((((n.ui || {}).remote || {}).port || ""));
    const eps = (((n.ui || {}).network || {}).endpoints || []);
    $("insNodeEndpoints").value = Array.isArray(eps) ? eps.join(",") : "";
    $("insNodePortsSummary").value = "in: " + ((((n.ui || {}).ports || {}).in || []).length) + " / out: " + ((((n.ui || {}).ports || {}).out || []).length);
    state.selectedPort = null;
    fillAgentSelect(nodeId);
    renderPortLists(n);
    applyModeUI();
    $("nodeEditModal").classList.remove("hidden");
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
    if (n.kind === "entry" && side === "in") { toast("Entry node cannot add input port", "warn"); return; }
    if (n.kind === "terminal" && side === "out") { toast("Terminal node cannot add output port", "warn"); return; }
    const ports = (((n.ui || {}).ports || {})[side] || []);
    if (ports.length >= 8) { toast("Port count limit reached", "warn"); return; }
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
    if (ports.length <= 1) { toast("At least one port must remain on this side", "warn"); return; }
    if (!state.selectedPort || state.selectedPort.side !== side) {
      toast("请先在" + (side === "in" ? "输入" : "输出") + "针脚列表中选择要删除的针脚", "warn");
      return;
    }
    const pid = String(state.selectedPort.id || "");
    const hit = ports.find((p) => String(p.id) === pid);
    if (!hit) { toast("选中的针脚不存在，请重新选择", "warn"); state.selectedPort = null; renderPortLists(n); return; }
    const hasLinks = countLinks(n.id, side, pid) > 0;
    if (hasLinks) { toast("Please remove connected edge first", "warn"); return; }
    n.ui.ports[side] = ports.filter((p) => String(p.id) !== pid);
    n.ui.ports = n.ui.ports || { in: [], out: [] };
    state.selectedPort = null;
    refreshPortSummary(n);
    renderPortLists(n);
    redrawGraph();
  }

  function closeNodeEditor() { $("nodeEditModal").classList.add("hidden"); }

  async function saveNode() {
    if (!isEditMode()) { toast("仅编辑模式可保存节点属性", "warn"); return; }
    const id = $("insNodeId").value;
    const n = getNode(id);
    if (!n) return;
    n.role = $("insNodeRole").value || n.role;
    n.bizStatus = $("insNodeBizStatus").value || n.bizStatus;
    n.kind = inferKind(n.role, $("insNodeKind").value || n.kind);
    n.owner = $("insNodeOwner").value || n.owner;
    n.desc = $("insNodeDesc").value || n.desc;
    n.tags = String($("insNodeTags").value || "").split(",").map((x) => x.trim()).filter(Boolean);
    n.ui.color = String($("insNodeColor").value || n.ui.color || "#0f172a");
    n.ui.remote = n.ui.remote || {};
    const remotePort = Number($("insNodeRemotePort").value || 0);
    n.ui.remote.port = (Number.isFinite(remotePort) && remotePort > 0) ? remotePort : 0;
    const epText = String($("insNodeEndpoints").value || "").trim();
    n.ui.network = { endpoints: epText ? epText.split(",").map((x) => x.trim()).filter(Boolean) : [] };
    n.ui.ports = normalizePorts(n.kind, n.ui.ports);

    const nodeRes = await OpsApi.updateNode(id, { role: n.role, kind: n.kind, desc: n.desc, bizStatus: n.bizStatus, owner: n.owner, x: n.ui.x, y: n.ui.y, ui: n.ui, tags: n.tags });
    if (!nodeRes.ok) { toast(nodeRes.message || "Save node failed", "error"); return; }

    const aid = String($("insNodePrimaryAgent").value || "");
    const serviceId = String((n.ui && n.ui.remote && n.ui.remote.service_id) || n.service_id || n.id || "").trim();
    const bindRes = await OpsApi.bindNodeService
      ? await OpsApi.bindNodeService({ node_id: id, agent_id: aid, service_id: serviceId, project_id: state.projectId })
      : await OpsApi.bindNodeAgent({ node_id: id, agent_id: aid, project_id: state.projectId });
    if (!bindRes.ok) { toast(bindRes.message || bindRes.error || "Bind agent failed", "error"); return; }

    state.nodeBindings = bindRes.bindings || state.nodeBindings;
    await OpsApi.saveTopology(state.topology);
    toast("Node and primary agent saved", "ok");
    logMode("节点保存成功: " + id);
    closeNodeEditor();
    drawNodes();
    renderRuntimeNodeList();
  }

  async function startRemoteForNode(nodeId, launchVisibleConsole) {
    const nid = String(nodeId || "").trim();
    if (!nid) return { ok: false, message: "missing_node_id" };
    const n = getNode(nid);
    if (!n) return { ok: false, message: "node_not_found" };
    const aid = String((state.nodeBindings || {})[nid] || "");
    if (!aid) return { ok: false, message: "节点未绑定Agent", error_code: "OPS_AGENT_NOT_BOUND" };
    const ag = (state.agents || []).find((x) => String((x || {}).agent_id || "") === aid) || null;
    if (!ag) return { ok: false, message: "绑定Agent不存在", error_code: "OPS_AGENT_NOT_REGISTERED" };
    const probe = String(ag.probe_status || "").toUpperCase();
    if (probe !== "PASS") return { ok: false, message: "Agent联通测试未通过", error_code: "OPS_AGENT_PROBE_REQUIRED" };
    const visible = (typeof launchVisibleConsole === "boolean")
      ? launchVisibleConsole
      : !!($("insNodeVisibleConsole") ? $("insNodeVisibleConsole").checked : true);
    const resp = await OpsApi.startRemoteNode({
      node_id: nid,
      project_id: state.projectId,
      service_id: String((n.ui && n.ui.remote && n.ui.remote.service_id) || n.service_id || n.id || ""),
      launch_visible_console: visible,
    });
    return resp || { ok: false, message: "remote_start_no_response" };
  }

  async function precheckAndStartRemoteForNodes(nodeIds) {
    await refreshAgentsIfNeeded(true);
    const uniq = Array.from(new Set((nodeIds || []).map((x) => String(x || "").trim()).filter(Boolean)));
    const failures = [];
    for (const nid of uniq) {
      const r = await startRemoteForNode(nid, true);
      if (!r || r.ok === false) {
        failures.push({ node_id: nid, error_code: (r && r.error_code) || "OPS_REMOTE_START_FAILED", message: (r && (r.message || r.error)) || "remote start failed" });
        logMode("远端启动失败 " + nid + ": " + ((r && (r.message || r.error)) || "unknown"), "error");
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
    const d = await OpsApi.deleteNode(nodeId);
    if (!d.ok) { toast(d.message || d.error || "Delete node failed", "error"); logMode("删除节点失败: " + (d.message || d.error || "unknown"), "error"); return; }
    state.topology = d.topology || state.topology;
    state.nodeBindings = d.bindings || state.nodeBindings;
    state.selection.nodes.clear();
    state.selection.edgeId = "";
    closeNodeEditor();
    redrawGraph();
    renderRuntimeNodeList();
    toast("Node deleted", "ok");
    logMode("删除节点成功: " + nodeId);
  }

  function deleteSelectedNode() {
    const ids = Array.from(state.selection.nodes || []);
    if (!ids.length) return;
    $("insNodeId").value = ids[0];
    deleteNode();
  }

  async function autoBindAgents() {
    const d = await OpsApi.autoBindAgents({ project_id: state.projectId });
    if (!d || d.ok === false) {
      toast((d && (d.message || d.error)) || "自动绑定失败", "error");
      return;
    }
    state.nodeBindings = d.bindings || state.nodeBindings;
    drawNodes();
    renderRuntimeNodeList();
    toast(`自动绑定完成：成功 ${d.bound_count || 0}，跳过 ${d.skipped_count || 0}`, "ok");
    logMode(`自动绑定完成：成功 ${d.bound_count || 0}，跳过 ${d.skipped_count || 0}`);
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
    const d = await OpsApi.runtimeFlowControl({ op, project_id: state.projectId });
    if (!d || d.ok === false) {
      toast((d && d.message) || "运行请求失败", "error");
      logMode("运行请求失败: " + ((d && (d.message || d.error)) || "unknown"), "error");
      return;
    }
    state.runtimeRunId = String(d.run_id || "");
    saveRuntimeState();
    dbg("runtime-flow-control-return", { op, runId: state.runtimeRunId, items: (d.items || []).length, status: d.status || "" });
    appendRuntimeLogs(d.logs || []);
    const total = (d.items || []).length;
    logMode("任务已入队，run_id=" + state.runtimeRunId + "，节点任务数=" + total);
    toast((start ? "启动" : "停止") + "任务已入队，开始实时跟踪", "ok");
    await pollRuntimeRun(state.runtimeRunId);
    state.runtimePollTimer = setInterval(() => { pollRuntimeRun(state.runtimeRunId); }, 1200);
  }

  async function runSmokeOrStress(isStress) {
    const scope = $("testScope").value || "full";
    const resolved = resolveTestEndpoints(scope);
    const startNode = resolved.start || "";
    const endNode = resolved.end || "";
    if (!resolved.ok) {
      toast(resolved.reason || "链路段测试需选择起点和终点", "warn");
      logMode("链路段测试参数不完整: start=" + (startNode || "-") + " end=" + (endNode || "-") + " reason=" + (resolved.reason || "unknown"), "warn");
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
      const d = await OpsApi.postJSON("/api/ops-platform/stress-test", {
        node_id: target,
        qps: 500,
        duration_sec: 180,
        reason: "拓扑测试模式压力测试",
      });
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
        logMode("压力测试失败: " + ((d && (d.message || d.error)) || "unknown"), "error");
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
    const d = await OpsApi.postJSON("/api/ops-platform/flow-smoke", { path_nodes: pathNodes });
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
      logMode("单元测试失败: " + ((d && (d.message || d.error)) || "unknown"), "error");
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
    const scope = ($("testScope") && $("testScope").value) || "full";
    const startNode = $("testStartNode").value || "";
    const endNode = $("testEndNode").value || "";
    if (scope === "full") {
      state.highlight = {
        nodes: new Set((state.topology.nodes || []).map((n) => n.id)),
        edges: new Set((state.topology.edges || []).map((e) => e.id)),
      };
      redrawGraph();
      return;
    }
    if (!startNode || !endNode) { clearTestHighlight(); return; }
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
    if (!found) { clearTestHighlight(); return; }
    const nodes = new Set();
    const hlEdges = new Set();
    let cursor = endNode;
    nodes.add(cursor);
    while (cursor !== startNode && prev[cursor]) {
      hlEdges.add(prev[cursor].edge);
      cursor = prev[cursor].node;
      nodes.add(cursor);
    }
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
    const options = ids.map((id) => '<option value="' + esc(id) + '">' + esc(id) + "</option>").join("");

    startSel.innerHTML = '<option value="">起点节点</option>' + options;
    endSel.innerHTML = '<option value="">终点节点</option>' + options;

    const hasPrevStart = prevStart && ids.indexOf(prevStart) >= 0;
    const hasPrevEnd = prevEnd && ids.indexOf(prevEnd) >= 0;
    let nextStart = hasPrevStart ? prevStart : "";
    let nextEnd = hasPrevEnd ? prevEnd : "";

    if (!nextStart && ids.length) nextStart = ids[0];
    if (!nextEnd && ids.length) nextEnd = ids.length > 1 ? ids[1] : ids[0];
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
      edit: { hint: "当前模式：编辑模式（可编辑节点属性、端口、删除）", run: "none", test: "none" },
      run: { hint: "当前模式：运行模式（锁定节点属性；允许新增节点与连线切换）", run: "flex", test: "none" },
      test: { hint: "当前模式：测试模式（可选全链路或链路段测试）", run: "none", test: "flex" },
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
    if ($("modeLockBtn")) $("modeLockBtn").style.display = state.modeLocked ? "none" : "";
    if ($("modeUnlockBtn")) $("modeUnlockBtn").style.display = state.modeLocked ? "" : "none";
    const shell = document.querySelector(".ops-shell");
    if (shell) {
      shell.classList.remove("canvas-mode-edit", "canvas-mode-run", "canvas-mode-test");
      shell.classList.add("canvas-mode-" + state.mode);
    }
    if (state.mode !== "test") clearTestHighlight();
    if (state.mode === "test") computePathHighlight();
    if (state.mode === "edit") {
      clearFlowViz(true, "applyModeUI-edit-mode");
      redrawGraph();
    }

    const lock = state.mode !== "edit";
    ["insNodeRole", "insNodeBizStatus", "insNodeKind", "insNodeColor", "insNodeOwner", "insNodePrimaryAgent", "insNodeDesc", "insNodeTags", "insNodeRemotePort", "insNodeEndpoints"]
      .forEach((id) => { const el = $(id); if (el) el.disabled = lock; });
    ["btnPortInAdd", "btnPortOutAdd", "btnPortInRemove", "btnPortOutRemove", "btnDeleteSelectedPort", "btnDeleteNode", "btnSaveNode"]
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
      OpsApi.loadTopology(state.projectId),
      OpsApi.loadPresets(),
    ]);
    if (checkAuthExpired(topo) || checkAuthExpired(presets)) return;
    if (!topo || topo.ok === false) {
      setTopologyHint((topo && (topo.message || topo.error)) || "拓扑核心数据加载失败", "error");
      return;
    }

    state.topology = topo.topology || { nodes: [], edges: [], meta: { viewport: { x: 0, y: 0, zoom: 1 } } };
    state.nodesRaw = (state.topology.nodes || []).map((n) => ({
      id: n.id,
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
    layoutStructuredGraph();
    renderScene();
    redrawGraph();
    renderPresets();
    renderRuntimeNodeList();
    fillTestNodeOptions();
    applyModeUI();
    setTopologyHint("拓扑已可操作，正在后台同步 Agent、绑定与总览数据...", "loading");

    loadAuxiliaryData();
  }

  async function loadAuxiliaryData() {
    const settled = await Promise.allSettled([
      OpsApi.loadNodes(),
      OpsApi.loadOverview(state.projectId),
      OpsApi.loadTopologyBlueprints(),
      OpsApi.loadNodeBindings(state.projectId),
      OpsApi.agents(state.projectId),
    ]);
    const [nodes, overview, blueprints, bindings, agents] = settled.map((r) => r.status === "fulfilled" ? r.value : { ok: false, error: String(r.reason || "request_failed") });
    if (checkAuthExpired(nodes) || checkAuthExpired(overview) || checkAuthExpired(blueprints) || checkAuthExpired(bindings) || checkAuthExpired(agents)) return;

    const warns = [];
    if (nodes && nodes.ok !== false && Array.isArray(nodes.nodes)) {
      state.nodesRaw = nodes.nodes;
      normalizeTopology();
      layoutStructuredGraph();
    } else {
      warns.push("节点清单");
    }
    if (overview && overview.ok !== false) state.overviewNodes = overview.nodes || [];
    else warns.push("总览");
    if (blueprints && blueprints.ok !== false && Array.isArray(blueprints.blueprints)) state.blueprints = blueprints.blueprints;
    else warns.push("流程模板");
    if (bindings && bindings.ok !== false) state.nodeBindings = bindings.bindings || {};
    else warns.push("绑定");
    if (agents && agents.ok !== false) state.agents = agents.agents || [];
    else warns.push("Agent");

    const bpSel = $("flowBlueprintSelect");
    if (bpSel) {
      bpSel.innerHTML = '<option value="">流程模板</option>' + state.blueprints.map((b) => '<option value="' + esc(b.blueprint_id) + '">' + esc(b.name) + '</option>').join("");
    }

    redrawGraph();
    renderRuntimeNodeList();
    fillTestNodeOptions();
    applyModeUI();
    setTopologyHint(warns.length ? ("部分辅助数据加载失败: " + warns.join("、") + "，画布仍可操作") : "", warns.length ? "warn" : "");
  }

  function bindEvents() {
    bindLeftTabs();
    ROLE_OPTIONS.forEach((v) => $("insNodeRole").insertAdjacentHTML("beforeend", '<option value="' + v + '">' + v + '</option>'));
    STATUS_OPTIONS.forEach((v) => $("insNodeBizStatus").insertAdjacentHTML("beforeend", '<option value="' + v + '">' + (STATUS_LABELS[v] || v) + '</option>'));

    $("presetSearch").oninput = renderPresets;
    if ($("presetCategoryFilter")) $("presetCategoryFilter").onchange = renderPresets;

    $("toolAuto").onclick = () => {
      if (isTestMode()) { toast("测试模式禁止自动布局", "warn"); return; }
      layoutStructuredGraph();
      redrawGraph();
      toast("已按结构化规则重新排布", "ok");
    };

    $("toolReset").onclick = () => { state.topology.meta.viewport = { x: 0, y: 0, zoom: 1 }; renderScene(); };

    $("toolSave").onclick = async () => {
      if (isTestMode()) { toast("测试模式禁止保存拓扑", "warn"); return; }
      const d = await OpsApi.saveTopology(state.topology);
      toast((d && d.ok !== false) ? "Topology saved" : ((d && d.message) || "Save failed"), (d && d.ok !== false) ? "ok" : "error");
      if (d && d.ok !== false) logMode("拓扑保存成功");
    };

    $("btnApplyBlueprint").onclick = async () => {
      const bid = String((($("flowBlueprintSelect") || {}).value || "")).trim();
      if (!bid) { toast("Please choose a blueprint", "warn"); return; }
      const chosen = state.blueprints.find((x) => String(x.blueprint_id) === bid);
      const confirmText = "Apply blueprint will clear all current canvas nodes and edges.\n\nBlueprint: " + (chosen ? chosen.name : bid) + "\n\nContinue?";
      if (!window.confirm(confirmText)) return;
      const d = await OpsApi.applyTopologyBlueprint({ blueprint_id: bid, project_id: state.projectId, replace_existing: true });
      if (!d.ok) { toast(d.message || d.error || "Apply blueprint failed", "error"); return; }
      toast("Blueprint applied", "ok");
      await loadAll();
    };
    if ($("btnAutoBindAgents")) $("btnAutoBindAgents").onclick = autoBindAgents;

    $("btnSaveNode").onclick = saveNode;
    $("btnDeleteNode").onclick = deleteNode;
    $("btnStartRemoteNode").onclick = async () => {
      const nid = String($("insNodeId").value || "").trim();
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
    $("btnDeleteSelectedPort").onclick = deleteSelectedPort;
    $("btnPortInAdd").onclick = () => addPort("in");
    $("btnPortOutAdd").onclick = () => addPort("out");
    $("btnPortInRemove").onclick = () => removePort("in");
    $("btnPortOutRemove").onclick = () => removePort("out");
    $("btnDeleteEdge").onclick = async () => {
      const id = state.selection.edgeId;
      if (!id) { toast("请先选中一条连线", "warn"); return; }
      await confirmStructuredDeleteEdge(id);
    };

    if ($("structuredAddClose")) $("structuredAddClose").onclick = closeStructuredAddMenu;
    $("nodeEditClose").onclick = closeNodeEditor;
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
    $("btnRunStartAll").onclick = () => runFullLifecycle(true);
    $("btnRunStopAll").onclick = () => runFullLifecycle(false);
    $("btnTestSmoke").onclick = () => runSmokeOrStress(false);
    $("btnTestStress").onclick = () => runSmokeOrStress(true);
    $("btnDeleteEdgeInline").onclick = () => {
      if (state.selection.edgeId) confirmStructuredDeleteEdge(state.selection.edgeId);
      else toast("请先点击选择一条连线", "warn");
    };
    $("testScope").onchange = computePathHighlight;
    $("testStartNode").onchange = computePathHighlight;
    $("testEndNode").onchange = computePathHighlight;

    const shell = $("canvasShell");
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

  async function boot() {
    state.projectId = ((document.querySelector(".ops-shell") || {}).dataset || {}).projectId || "";
    $("opsProjectFilter").value = state.projectId;
    loadModeState();
    loadRuntimeState();
    bindEvents();
    await loadAll();
    startAgentsRealtimeTick();
    const act = await OpsApi.runtimeFlowActive(state.projectId);
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
      return;
    }
    if (state.mode === "run" && state.runtimeRunId) {
      logMode("检测到刷新前运行态，自动恢复运行跟踪: " + state.runtimeRunId, "warn");
      await pollRuntimeRun(state.runtimeRunId);
      stopRuntimePolling();
      state.runtimePollTimer = setInterval(() => { pollRuntimeRun(state.runtimeRunId); }, 1200);
    }
  }

  boot().catch((e) => {
    console.error(e);
    toast("Topology editor initialization failed, refresh and retry", "error");
  });
})();
