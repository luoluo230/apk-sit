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
    await refreshAgentsIfNeeded(!!state.runtimeStopping || !!state.runtimeStarting);
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
    const op = String(d.op || "").toLowerCase();
    const effectiveOp = op || String(state.runtimeRequestedOp || "").toLowerCase() || "start";
    const seqViz = buildSequentialFlowVizFromItems(d.items || [], effectiveOp, { requireProbe: effectiveOp === "start" });
    const statusByNode = seqViz.statusByNode;
    const activeNodes = seqViz.vizNodes;
    const metricsByEdge = {};
    if (seqViz.edgesEnabled) {
      (state.topology.edges || []).forEach((e) => {
        if (!activeNodes.includes(e.from) || !activeNodes.includes(e.to)) return;
        const toSt = statusByNode[String(e.to)] || "";
        metricsByEdge[e.id] = edgeMetrics(e.id, toSt);
      });
    }
    syncFlowViz(effectiveOp === "stop" ? "run" : "run", activeNodes, statusByNode, { edgesEnabled: seqViz.edgesEnabled });
    if (seqViz.edgesEnabled && !state.runtimeEdgesLogged) {
      state.runtimeEdgesLogged = true;
      logMode("全部节点已就绪，开始连线流量动画", "");
    }
    state.flowViz.metricsByEdge = metricsByEdge;
    if (effectiveOp === "start") reconcileFlowVizWithAgentTruth();
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
    const effectiveOpFinal = effectiveOp;
    if (state.runtimeLastStatus !== st) {
      dbg("runtime-status-transition", { from: state.runtimeLastStatus || "-", to: st, op, effectiveOp: effectiveOpFinal, done: Number(d.done || 0), total: Number(d.total || 0), failed: Number(d.failed || 0) });
      state.runtimeLastStatus = st;
    }
    if (st === "success" || st === "failed") {
      stopRuntimePolling();
      state.runtimeStarting = false;
      const ok = st === "success";
      if (!ok) {
        stopRuntimeLiveWait();
        const partial = buildSequentialFlowVizFromItems(d.items || [], effectiveOpFinal);
        const runningNodes = partial.vizNodes.filter((nid) => String(statusByNode[nid] || "").toUpperCase() === "RUNNING");
        if (runningNodes.length) {
          state.runtimePartialRecovery = true;
          syncFlowViz("run", partial.vizNodes, partial.statusByNode, { edgesEnabled: false });
          state.flowViz.metricsByEdge = {};
          redrawGraph();
          toast("部分节点启动失败，已保留成功节点；可在 Agent 修复后自动同步", "warn");
          logMode("运行结束: FAILED（" + runningNodes.length + " 个节点仍运行，等待 Agent 修复同步）", "warn");
          return;
        }
        const errLog = (d.logs || []).slice().reverse().find((row) => String((row && row.level) || "").toLowerCase() === "error");
        const errMsg = errLog ? String(errLog.message || "") : "";
        toast(errMsg || "全流程启动失败，请查看模式日志", "error");
        logMode("运行结束: " + st.toUpperCase() + (errMsg ? (" — " + errMsg) : ""), "warn");
        replayFailureFlow();
        setTimeout(() => {
          clearFlowViz(true, "pollRuntimeRun-failed-finalize");
          redrawGraph();
        }, 2200);
        return;
      }
      toast("全流程执行完成", "ok");
      logMode("运行结束: " + st.toUpperCase(), "");
      if (effectiveOpFinal === "start") {
        state.runtimePartialRecovery = false;
        await refreshAgentsIfNeeded(true);
        if (!seqViz.edgesEnabled && !clusterServicesRunning()) {
          startRuntimeLiveWait(runId);
          return;
        }
        await finalizeRuntimeStartSteady(runId);
        toast("全流程执行完成", "ok");
        return;
      }
      await finalizeRuntimeStop("pollRuntimeRun-stop-success");
      toast("全流程已停止", "ok");
      return;
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

