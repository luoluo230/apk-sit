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
    quickAddCtx: null,
    hoverPortKey: "",
    mode: "edit",
    selectedPort: null,
    runtimeRunId: "",
    runtimePollTimer: null,
    runtimeLogSeen: new Set(),
    runtimeProgressSig: "",
    modeLocked: false,
    highlight: { nodes: new Set(), edges: new Set() },
  };

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
  function runtimeById() { const m = {}; (state.overviewNodes || []).forEach((n) => { m[n.id] = n; }); return m; }
  function isEditMode() { return state.mode === "edit"; }
  function isRunMode() { return state.mode === "run"; }
  function isTestMode() { return state.mode === "test"; }

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
    const d = await OpsApi.runtimeFlowStatus(runId);
    if (!d || d.ok === false) {
      logMode("运行状态拉取失败: " + ((d && (d.message || d.error)) || "unknown"), "error");
      stopRuntimePolling();
      return;
    }
    appendRuntimeLogs(d.logs || []);
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
    if (st === "success" || st === "failed") {
      stopRuntimePolling();
      const ok = st === "success";
      toast(ok ? "全流程执行完成" : "全流程执行结束（含失败）", ok ? "ok" : "warn");
      logMode("运行结束: " + st.toUpperCase(), ok ? "" : "warn");
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
    const dot = document.querySelector('.port-dot[data-node-id="' + node.id + '"][data-side="' + side + '"][data-port-id="' + portId + '"]');
    if (dot) {
      const dr = dot.getBoundingClientRect();
      const p = world(dr.left + dr.width / 2, dr.top + dr.height / 2);
      return { x: p.x, y: p.y };
    }
    const ports = (((node.ui || {}).ports || {})[side] || []);
    const idx = Math.max(0, ports.findIndex((p) => String(p.id) === String(portId)));
    const y = node.ui.y + 20 + idx * 20;
    return side === "out" ? { x: node.ui.x + node.ui.w, y } : { x: node.ui.x, y };
  }

  function linkOffset(edge) {
    const siblings = (state.topology.edges || []).filter((e) => e.from === edge.from && e.to === edge.to).sort((a, b) => (a.id > b.id ? 1 : -1));
    const idx = Math.max(0, siblings.findIndex((e) => e.id === edge.id));
    return (idx - (siblings.length - 1) / 2) * 16;
  }

  function edgePath(edge) {
    const aNode = getNode(edge.from);
    const bNode = getNode(edge.to);
    if (!aNode || !bNode) return "";
    const a = portAnchor(aNode, "out", edge.from_port);
    const b = portAnchor(bNode, "in", edge.to_port);
    const bend = Math.max(72, Math.min(220, Math.abs(b.x - a.x) * 0.35));
    const offset = linkOffset(edge);
    return "M " + a.x + " " + a.y + " C " + (a.x + bend) + " " + (a.y + offset) + ", " + (b.x - bend) + " " + (b.y + offset) + ", " + b.x + " " + b.y;
  }

  function normalizeTopology() {
    const ids = (state.nodesRaw || []).map((n) => String(n.id || "")).filter(Boolean);
    const old = {};
    (state.topology.nodes || []).forEach((n) => { if (n && n.id) old[n.id] = n; });
    state.topology.nodes = ids.map((id, i) => {
      const raw = (state.nodesRaw || []).find((x) => String(x.id || "") === id) || {};
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
      }));
  }

  function renderScene() {
    const v = view();
    $("scene").style.transform = "translate(" + v.x + "px," + v.y + "px) scale(" + v.zoom + ")";
    $("zoomLabel").textContent = Math.round(v.zoom * 100) + "%";
  }

  function drawEdges() {
    const svg = $("edgeSvg");
    svg.innerHTML = "";
    (state.topology.edges || []).forEach((edge) => {
      const d = edgePath(edge);
      if (!d) return;
      const hit = document.createElementNS("http://www.w3.org/2000/svg", "path");
      hit.setAttribute("d", d);
      hit.setAttribute("class", "edge-hit");
      hit.onclick = (ev) => { ev.stopPropagation(); state.selection.edgeId = edge.id; state.selection.nodes.clear(); drawEdges(); drawNodes(); };
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      const hl = state.highlight.edges.has(edge.id) ? " hl" : "";
      path.setAttribute("class", "edge" + hl + (state.selection.edgeId === edge.id ? " sel" : ""));
      path.onclick = (ev) => { ev.stopPropagation(); state.selection.edgeId = edge.id; state.selection.nodes.clear(); drawEdges(); drawNodes(); };
      svg.appendChild(hit);
      svg.appendChild(path);
    });
    const delBtn = $("btnDeleteEdgeInline");
    if (delBtn) delBtn.disabled = !state.selection.edgeId;
  }

  function drawPorts(node, side) {
    const ports = (((node.ui || {}).ports || {})[side] || []);
    return '<div class="ports ' + side + '">' + ports.map((p) => {
      const key = node.id + ":" + side + ":" + p.id;
      const target = key === state.hoverPortKey ? " target" : "";
      const label = '<span class="port-label">' + esc(p.label || p.id) + ' (' + countLinks(node.id, side, p.id) + ")</span>";
      const dot = '<span class="port-dot" data-node-id="' + esc(node.id) + '" data-side="' + side + '" data-port-id="' + esc(p.id) + '" title="' + esc(p.label || p.id) + '"></span>';
      const inner = side === "in" ? (label + dot) : (dot + label);
      return '<div class="port-item ' + side + target + '" data-node-id="' + esc(node.id) + '" data-side="' + side + '" data-port-id="' + esc(p.id) + '">' + inner + "</div>";
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
      const st = String(n.bizStatus || "normal");
      const stLabel = STATUS_LABELS[st] || st;
      const palette = ROLE_COLOR[String(n.role || "").toLowerCase()] || { border: "#9ab6e5", bg1: "#ffffff", bg2: "#f4f8ff" };

      const el = document.createElement("div");
      el.className = "node" + (state.selection.nodes.has(n.id) ? " sel" : "") + (state.highlight.nodes.has(n.id) ? " hl" : "");
      el.style.left = n.ui.x + "px";
      el.style.top = n.ui.y + "px";
      el.style.width = n.ui.w + "px";
      el.style.minHeight = n.ui.h + "px";
      el.style.borderColor = palette.border;
      el.style.background = "linear-gradient(165deg," + palette.bg1 + "," + palette.bg2 + ")";
      el.innerHTML = drawPorts(n, "in") + drawPorts(n, "out")
        + '<div class="t">' + esc((runtime[n.id] || {}).name || n.id) + '</div>'
        + '<div class="s">' + esc(n.role) + '</div>'
        + '<div class="s">状态: ' + esc(stLabel) + '</div>'
        + '<div class="s">' + esc(n.owner || "-") + '</div>'
        + '<div class="state-pill ' + bindCls + '" style="margin-top:4px">' + esc(bindText) + "</div>";
      el.onmousedown = (ev) => onNodeDown(ev, n);
      el.onclick = (ev) => { ev.stopPropagation(); openNodeEditor(n.id); };
      layer.appendChild(el);
    });

    layer.querySelectorAll(".port-item").forEach((item) => {
      const nodeId = item.getAttribute("data-node-id");
      const side = item.getAttribute("data-side");
      const portId = item.getAttribute("data-port-id");
      item.onmousedown = (ev) => startLink(ev, nodeId, side, portId);
      item.onclick = (ev) => { ev.stopPropagation(); if (side === "out") openQuickAdd({ side: "out", fromNodeId: nodeId, fromPortId: portId }); };
      item.ondblclick = (ev) => { ev.stopPropagation(); if (side === "in") openQuickAdd({ side: "in", toNodeId: nodeId, toPortId: portId }); };
    });
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

  function nearestPort(pos, side) {
    let best = null;
    let min = Infinity;
    (state.topology.nodes || []).forEach((n) => {
      ((((n.ui || {}).ports || {})[side] || [])).forEach((p) => {
        const a = portAnchor(n, side, p.id);
        const d = Math.hypot(pos.x - a.x, pos.y - a.y);
        if (d < 24 && d < min) { min = d; best = { nodeId: n.id, portId: p.id, side, anchor: a }; }
      });
    });
    return best;
  }

  function validLink(fromNodeId, fromPortId, toNodeId, toPortId) {
    if (fromNodeId === toNodeId) return { ok: false, msg: "Cannot connect same node" };
    const fromNode = getNode(fromNodeId);
    const toNode = getNode(toNodeId);
    if (!fromNode || !toNode) return { ok: false, msg: "Node not found" };
    if (fromNode.kind === "terminal" || toNode.kind === "entry") return { ok: false, msg: "Node kind direction violation" };
    const dup = (state.topology.edges || []).some((e) => e.from === fromNodeId && e.to === toNodeId && e.from_port === fromPortId && e.to_port === toPortId);
    if (dup) return { ok: false, msg: "Duplicate edge" };
    const outLinks = countLinks(fromNodeId, "out", fromPortId);
    if (outLinks >= 1) return { ok: false, msg: "Output port already occupied" };
    const inLinks = countLinks(toNodeId, "in", toPortId);
    if (inLinks >= 1) return { ok: false, msg: "Input port already occupied" };
    return { ok: true };
  }

  async function commitLink(fromNodeId, fromPortId, toNodeId, toPortId) {
    const vr = validLink(fromNodeId, fromPortId, toNodeId, toPortId);
    if (!vr.ok) { toast(vr.msg, "warn"); return; }
    const d = await OpsApi.upsertEdge({ from: fromNodeId, to: toNodeId, from_port: fromPortId, to_port: toPortId, type: "depends_on", note: "" });
    if (!d.ok) { toast(d.message || "Link failed", "error"); return; }
    state.topology = d.topology || state.topology;
    drawEdges();
    drawNodes();
  }

  function startLink(ev, nodeId, side, portId) {
    ev.stopPropagation();
    if (ev.button !== 0) return;
    if (isTestMode()) { toast("测试模式禁止修改连线", "warn"); return; }
    if (side !== "out") { toast("Start link from output port", "warn"); return; }
    state.drag = { mode: "link", fromNodeId: nodeId, fromPortId: portId, target: null };
    state.hoverPortKey = "";
    logMode("开始从 " + nodeId + ":" + portId + " 拖拽连线");
  }

  function drawPreview(clientX, clientY) {
    drawEdges();
    const fromNode = getNode(state.drag.fromNodeId);
    if (!fromNode) return;
    const s = portAnchor(fromNode, "out", state.drag.fromPortId);
    const p = world(clientX, clientY);
    const target = nearestPort(p, "in");
    state.drag.target = target;
    const e = target ? target.anchor : p;
    state.hoverPortKey = target ? (target.nodeId + ":in:" + target.portId) : "";
    drawNodes();
    const bend = Math.max(72, Math.min(220, Math.abs(e.x - s.x) * 0.35));
    const d = "M " + s.x + " " + s.y + " C " + (s.x + bend) + " " + s.y + ", " + (e.x - bend) + " " + e.y + ", " + e.x + " " + e.y;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    path.setAttribute("class", "edge edge-preview");
    $("edgeSvg").appendChild(path);
  }

  function presetGroup(role) {
    const r = String(role || "").toLowerCase();
    if (["gateway", "edge", "admin"].includes(r)) return "入口与边缘";
    if (["business", "scheduler", "analytics"].includes(r)) return "业务与调度";
    if (["pressure"].includes(r)) return "压测与实验";
    if (["database", "cache", "mq", "search"].includes(r)) return "数据与中间件";
    return "其他";
  }

  function canPresetConnect(ctx, preset) {
    const k = inferKind(preset.role, preset.kind);
    if (ctx.side === "out") return k !== "entry";
    return k !== "terminal";
  }

  function openQuickAdd(ctx) {
    state.quickAddCtx = ctx;
    $("portModalTitle").textContent = ctx.side === "in" ? "为输入端口添加上游节点" : "为输出端口添加下游节点";
    $("portModalHint").textContent = "仅显示可连接模板";
    const list = $("portModalList");
    list.innerHTML = "";
    const rows = (state.presets || []).filter((p) => canPresetConnect(ctx, p));
    if (!rows.length) {
      list.innerHTML = '<div class="preset-empty">没有可连接模板</div>';
      $("portQuickAdd").classList.remove("hidden");
      return;
    }
    const groups = {};
    rows.forEach((p) => { const g = presetGroup(p.role); if (!groups[g]) groups[g] = []; groups[g].push(p); });
    Object.keys(groups).sort().forEach((g) => {
      const sec = document.createElement("div");
      sec.className = "port-modal-group";
      sec.innerHTML = '<div class="port-modal-group-hd"><span>' + esc(g) + '</span><span>' + groups[g].length + "</span></div>";
      groups[g].forEach((p) => {
        const item = document.createElement("div");
        item.className = "port-modal-item";
        item.innerHTML = '<div style="font-size:13px;font-weight:700">' + esc(p.name || "-") + '</div><div style="font-size:11px;color:#64748b;margin-top:4px">' + esc((p.role || "-") + " / " + inferKind(p.role, p.kind)) + "</div>";
        item.onclick = () => quickAddCreate(p);
        sec.appendChild(item);
      });
      list.appendChild(sec);
    });
    $("portQuickAdd").classList.remove("hidden");
  }

  function closeQuickAdd() { $("portQuickAdd").classList.add("hidden"); state.quickAddCtx = null; }

  async function quickAddCreate(preset) {
    const ctx = state.quickAddCtx;
    if (!ctx) return;
    const anchorNode = ctx.side === "in" ? getNode(ctx.toNodeId) : getNode(ctx.fromNodeId);
    const place = ctx.side === "in"
      ? { x: (anchorNode ? anchorNode.ui.x : 260) - 320, y: (anchorNode ? anchorNode.ui.y : 140) }
      : { x: (anchorNode ? anchorNode.ui.x : 260) + 320, y: (anchorNode ? anchorNode.ui.y : 140) };

    const d = await OpsApi.addNodeFromPreset({
      preset_id: String(preset.preset_id || ""),
      name: "",
      server_id: "",
      project_id: state.projectId,
      owner: "",
      env: "prod",
      channel: "",
      description: preset.default_desc || "",
    });
    if (!d.ok) { toast(d.message || "Add node failed", "error"); logMode("快捷建点失败: " + (d.message || d.error || "unknown"), "error"); return; }

    await loadAll();
    if (d.node && d.node.id) {
      const n = getNode(d.node.id);
      if (n) {
        n.ui.x = Math.round(place.x / 8) * 8;
        n.ui.y = Math.round(place.y / 8) * 8;
      }
      const fromId = ctx.side === "in" ? d.node.id : ctx.fromNodeId;
      const toId = ctx.side === "in" ? ctx.toNodeId : d.node.id;
      if (fromId && toId) await commitLink(fromId, "out-1", toId, "in-1");
      await OpsApi.saveTopology(state.topology);
      closeQuickAdd();
      drawEdges();
      drawNodes();
      renderRuntimeNodeList();
      logMode("快捷建点成功: " + (d.node.id || "-"));
    }
  }

  function renderPresets() {
    const box = $("presetList");
    const kw = String($("presetSearch").value || "").toLowerCase().trim();
    box.innerHTML = "";
    const rows = (state.presets || []).filter((p) => !kw || (String(p.name || "") + " " + String(p.role || "")).toLowerCase().includes(kw));
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
        drawEdges(); drawNodes(); renderRuntimeNodeList();
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
        const cls = selected ? "state-info" : "state-ok";
        return '<button type="button" class="state-pill ' + cls + '" data-side="' + side + '" data-port-id="' + esc(p.id) + '" style="cursor:pointer">' + esc(p.label || p.id) + " (" + countLinks(node.id, side, p.id) + ")</button>";
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
    agMeta.value = hit ? ((hit.device_id || "-") + " / " + (hit.port || "-") + " / " + (hit.last_seen || "-")) : "未绑定";
    sel.onchange = () => {
      const aid = String(sel.value || "");
      const x = state.agents.find((a) => String(a.agent_id || "") === aid);
      agMeta.value = x ? ((x.device_id || "-") + " / " + (x.port || "-") + " / " + (x.last_seen || "-")) : "未绑定";
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
    drawEdges();
    drawNodes();
  }

  function removePort(side) {
    if (!isEditMode()) { toast("仅编辑模式可改端口结构", "warn"); return; }
    const id = $("insNodeId").value;
    const n = getNode(id);
    if (!n) return;
    const ports = ((n.ui && n.ui.ports && n.ui.ports[side]) || []);
    if (!ports.length) return;
    if (ports.length <= 1) { toast("At least one port must remain on this side", "warn"); return; }
    const last = ports[ports.length - 1];
    const hasLinks = countLinks(n.id, side, last.id) > 0;
    if (hasLinks) { toast("Please remove connected edge first", "warn"); return; }
    ports.pop();
    n.ui.ports = n.ui.ports || { in: [], out: [] };
    n.ui.ports[side] = ports;
    refreshPortSummary(n);
    renderPortLists(n);
    drawEdges();
    drawNodes();
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
    n.ui.ports = normalizePorts(n.kind, n.ui.ports);

    const nodeRes = await OpsApi.updateNode(id, { role: n.role, kind: n.kind, desc: n.desc, bizStatus: n.bizStatus, owner: n.owner, x: n.ui.x, y: n.ui.y, ui: n.ui, tags: n.tags });
    if (!nodeRes.ok) { toast(nodeRes.message || "Save node failed", "error"); return; }

    const aid = String($("insNodePrimaryAgent").value || "");
    const bindRes = await OpsApi.bindNodeAgent({ node_id: id, agent_id: aid, project_id: state.projectId });
    if (!bindRes.ok) { toast(bindRes.message || bindRes.error || "Bind agent failed", "error"); return; }

    state.nodeBindings = bindRes.bindings || state.nodeBindings;
    await OpsApi.saveTopology(state.topology);
    toast("Node and primary agent saved", "ok");
    logMode("节点保存成功: " + id);
    closeNodeEditor();
    drawNodes();
    renderRuntimeNodeList();
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
    drawEdges();
    drawNodes();
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
    drawEdges();
    drawNodes();
    logMode("删除针脚: " + n.id + ":" + side + ":" + pid);
  }

  async function runFullLifecycle(start) {
    const op = start ? "start" : "stop";
    stopRuntimePolling();
    state.runtimeLogSeen = new Set();
    state.runtimeProgressSig = "";
    logMode((start ? "开始" : "开始") + (start ? "一键启动" : "一键停止") + "全流程");
    const d = await OpsApi.runtimeFlowControl({ op, project_id: state.projectId });
    if (!d || d.ok === false) {
      toast((d && d.message) || "运行请求失败", "error");
      logMode("运行请求失败: " + ((d && (d.message || d.error)) || "unknown"), "error");
      return;
    }
    state.runtimeRunId = String(d.run_id || "");
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
      } else {
        logMode("压力测试失败: " + ((d && (d.message || d.error)) || "unknown"), "error");
        if (d) {
          testLogKV("error_code", d.error_code || d.error || "-");
          testLogKV("http_status", d._http_status || "-");
          testLogKV("message", d.message || "-");
        }
        appendJsonDetail("压力测试失败原始响应", d || {});
        toast((d && d.message) || "压力测试失败", "error");
      }
      return;
    }
    const pathNodes = scope === "full"
      ? (state.topology.nodes || []).map((n) => n.id)
      : [startNode, endNode].filter(Boolean);
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
    } else {
      logMode("单元测试失败: " + ((d && (d.message || d.error)) || "unknown"), "error");
      if (d) {
        testLogKV("error_code", d.error_code || d.error || "-");
        testLogKV("http_status", d._http_status || "-");
        testLogKV("message", d.message || "-");
      }
      appendJsonDetail("单元测试失败原始响应", d || {});
      toast((d && d.message) || "单元测试失败", "error");
    }
  }

  function clearTestHighlight() {
    state.highlight = { nodes: new Set(), edges: new Set() };
    drawEdges();
    drawNodes();
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
      drawEdges();
      drawNodes();
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
    drawEdges();
    drawNodes();
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
    $("modeHint").textContent = cfg.hint;
    $("runBar").style.display = cfg.run;
    $("testBar").style.display = cfg.test;
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

    const lock = state.mode !== "edit";
    ["insNodeRole", "insNodeBizStatus", "insNodeKind", "insNodeColor", "insNodeOwner", "insNodePrimaryAgent", "insNodeDesc", "insNodeTags"]
      .forEach((id) => { const el = $(id); if (el) el.disabled = lock; });
    ["btnPortInAdd", "btnPortOutAdd", "btnPortInRemove", "btnPortOutRemove", "btnDeleteSelectedPort", "btnDeleteNode", "btnSaveNode"]
      .forEach((id) => { const el = $(id); if (el) el.disabled = lock; });
  }

  async function loadAll() {
    const [nodes, overview, topo, presets, blueprints, bindings, agents] = await Promise.all([
      OpsApi.loadNodes(),
      OpsApi.loadOverview(state.projectId),
      OpsApi.loadTopology(state.projectId),
      OpsApi.loadPresets(),
      OpsApi.loadTopologyBlueprints(),
      OpsApi.loadNodeBindings(state.projectId),
      OpsApi.agents(state.projectId),
    ]);

    state.nodesRaw = nodes.nodes || [];
    state.overviewNodes = overview.nodes || [];
    state.topology = topo.topology || { nodes: [], edges: [], meta: { viewport: { x: 0, y: 0, zoom: 1 } } };
    state.presets = presets.presets || [];
    state.blueprints = (blueprints && blueprints.ok && Array.isArray(blueprints.blueprints)) ? blueprints.blueprints : [];
    state.nodeBindings = (bindings && bindings.bindings) || {};
    state.agents = (agents && agents.agents) || [];

    if (!state.activePresetId && state.presets.length) state.activePresetId = state.presets[0].preset_id;

    const bpSel = $("flowBlueprintSelect");
    if (bpSel) {
      bpSel.innerHTML = '<option value="">流程模板</option>' + state.blueprints.map((b) => '<option value="' + esc(b.blueprint_id) + '">' + esc(b.name) + '</option>').join("");
    }

    normalizeTopology();
    renderScene();
    drawEdges();
    drawNodes();
    renderPresets();
    renderRuntimeNodeList();
    fillTestNodeOptions();
    applyModeUI();
  }

  function bindEvents() {
    ROLE_OPTIONS.forEach((v) => $("insNodeRole").insertAdjacentHTML("beforeend", '<option value="' + v + '">' + v + '</option>'));
    STATUS_OPTIONS.forEach((v) => $("insNodeBizStatus").insertAdjacentHTML("beforeend", '<option value="' + v + '">' + (STATUS_LABELS[v] || v) + '</option>'));

    $("presetSearch").oninput = renderPresets;

    $("toolAuto").onclick = () => {
      if (isTestMode()) { toast("测试模式禁止自动布局", "warn"); return; }
      const n = state.topology.nodes || [];
      const cols = Math.max(3, Math.min(6, Math.ceil(Math.sqrt(n.length || 1))));
      n.forEach((x, i) => { x.ui.x = 80 + (i % cols) * 280; x.ui.y = 100 + Math.floor(i / cols) * 170; });
      drawEdges(); drawNodes();
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

    $("btnSaveNode").onclick = saveNode;
    $("btnDeleteNode").onclick = deleteNode;
    $("btnDeleteSelectedPort").onclick = deleteSelectedPort;
    $("btnPortInAdd").onclick = () => addPort("in");
    $("btnPortOutAdd").onclick = () => addPort("out");
    $("btnPortInRemove").onclick = () => removePort("in");
    $("btnPortOutRemove").onclick = () => removePort("out");
    $("btnDeleteEdge").onclick = async () => {
      const id = state.selection.edgeId;
      if (!id) { toast("请先选中一条连线", "warn"); return; }
      const d = await OpsApi.deleteEdge(id);
      if (!d.ok) { toast(d.message || "Delete edge failed", "error"); logMode("连线删除失败: " + (d.message || d.error || "unknown"), "error"); return; }
      state.topology = d.topology || state.topology;
      normalizeTopology();
      state.selection.edgeId = "";
      logMode("连线删除成功: " + id);
      if (isTestMode()) computePathHighlight();
      drawEdges(); drawNodes();
    };

    $("portModalClose").onclick = closeQuickAdd;
    $("nodeEditClose").onclick = closeNodeEditor;
    $("modeSelect").onchange = () => {
      if (state.modeLocked) return;
      state.mode = $("modeSelect").value || "edit";
      applyModeUI();
      logMode("切换到" + (state.mode === "edit" ? "编辑" : state.mode === "run" ? "运行" : "测试") + "模式");
    };
    $("modeLockBtn").onclick = () => {
      state.modeLocked = true;
      applyModeUI();
      logMode("模式已锁定");
      toast("模式已锁定", "ok");
    };
    $("modeUnlockBtn").onclick = () => {
      state.modeLocked = false;
      applyModeUI();
      logMode("模式已解锁");
      toast("模式已解锁", "ok");
    };
    $("btnRunStartAll").onclick = () => runFullLifecycle(true);
    $("btnRunStopAll").onclick = () => runFullLifecycle(false);
    $("btnTestSmoke").onclick = () => runSmokeOrStress(false);
    $("btnTestStress").onclick = () => runSmokeOrStress(true);
    $("btnDeleteEdgeInline").onclick = () => $("btnDeleteEdge").click();
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
        drawEdges(); drawNodes();
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
      if (ev.key === "Escape") { closeQuickAdd(); closeNodeEditor(); }
    });

    window.addEventListener("keyup", (ev) => { if (ev.code === "Space") state.spaceDown = false; });

    window.addEventListener("mousemove", (ev) => {
      if (state.pan) {
        state.topology.meta.viewport = { x: state.pan.v.x + (ev.clientX - state.pan.sx), y: state.pan.v.y + (ev.clientY - state.pan.sy), zoom: state.pan.v.zoom };
        renderScene();
        return;
      }
      if (state.drag && state.drag.mode === "move") {
        if (isTestMode()) return;
        const p1 = world(state.drag.sx, state.drag.sy);
        const p2 = world(ev.clientX, ev.clientY);
        const dx = Math.round((p2.x - p1.x) / 8) * 8;
        const dy = Math.round((p2.y - p1.y) / 8) * 8;
        state.drag.ids.forEach((id) => {
          const n = getNode(id);
          if (n) { n.ui.x = state.drag.start[id].x + dx; n.ui.y = state.drag.start[id].y + dy; }
        });
        drawEdges(); drawNodes();
        return;
      }
      if (state.drag && state.drag.mode === "link") drawPreview(ev.clientX, ev.clientY);
    });

    window.addEventListener("mouseup", async (ev) => {
      if (state.pan) { state.pan = null; return; }
      if (state.drag && state.drag.mode === "move") { state.drag = null; if (!isTestMode()) await OpsApi.saveTopology(state.topology); return; }
      if (state.drag && state.drag.mode === "link") {
        const fromNodeId = state.drag.fromNodeId;
        const fromPortId = state.drag.fromPortId;
        const target = state.drag.target || nearestPort(world(ev.clientX, ev.clientY), "in");
        state.drag = null;
        state.hoverPortKey = "";
        drawNodes();
        if (target) await commitLink(fromNodeId, fromPortId, target.nodeId, target.portId);
        drawEdges();
      }
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

  function onNodeDown(ev, node) {
    if (ev.button !== 0) return;
    if (ev.target && ev.target.closest && ev.target.closest(".port-item")) return;
    if (isRunMode() || isTestMode()) return;
    state.selection.nodes = new Set([node.id]);
    const ids = [node.id];
    state.drag = { mode: "move", ids, sx: ev.clientX, sy: ev.clientY, start: {} };
    ids.forEach((id) => {
      const n = getNode(id);
      if (n) state.drag.start[id] = { x: n.ui.x, y: n.ui.y };
    });
    ev.preventDefault();
  }

  async function boot() {
    state.projectId = ((document.querySelector(".ops-shell") || {}).dataset || {}).projectId || "";
    $("opsProjectFilter").value = state.projectId;
    bindEvents();
    await loadAll();
  }

  boot().catch((e) => {
    console.error(e);
    toast("Topology editor initialization failed, refresh and retry", "error");
  });
})();
