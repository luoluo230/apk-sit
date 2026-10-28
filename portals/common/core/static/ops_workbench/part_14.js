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
    const pathNodes = resolvePathNodesForTest(scope, startNode, endNode);
    if (!pathNodes.length) {
      toast("没有可测试的节点", "warn");
      logMode("测试路径为空", "warn");
      return;
    }
    computePathHighlight();
    const vizNodes = scope === "segment" ? pathNodes : Array.from(state.highlight.nodes || pathNodes);
    syncFlowViz("test", vizNodes.length ? vizNodes : pathNodes, {});
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
    const pathNodesForTest = pathNodes;
    if (!isRuntimeTopologyProject()) {
      const pre = await precheckAndStartRemoteForNodes(pathNodesForTest);
      if (!pre.ok) {
        toast("测试前置校验失败，请先修复失败节点", "error");
        appendJsonDetail("测试前置校验失败节点清单", pre.failures);
        return;
      }
    } else {
      logMode("Runtime 拓扑：跳过 Agent 前置校验，直接执行探活测试");
    }
    testLogHeader("单元测试开始", "scope=" + scope);
    testLogKV("path_nodes", pathNodesForTest.join(" -> "));
    testLogKV("path_len", pathNodesForTest.length);
    const stepStatus = {};
    const stepResults = [];
    let flowId = "-";
    let allOk = true;
    for (let i = 0; i < pathNodesForTest.length; i += 1) {
      const nid = pathNodesForTest[i];
      logMode("测试 Step " + (i + 1) + "/" + pathNodesForTest.length + ": 探活节点 " + nid + "...");
      stepStatus[nid] = "STARTING";
      syncFlowViz("test", pathNodesForTest.slice(0, i + 1), Object.assign({}, stepStatus), { edgesEnabled: false });
      redrawGraph();
      const d = await OpsApi.postJSON("/api/ops-platform/flow-smoke", Object.assign(currentScope(), { path_nodes: [nid] }));
      const step = (Array.isArray(d && d.steps) ? d.steps : [])[0] || {};
      const ok = !!(d && d.ok !== false && step.ok !== false);
      stepStatus[nid] = ok ? "RUNNING" : "FAILED";
      stepResults.push(step);
      testLogStep(i, step);
      if (!ok) allOk = false;
      if (d && d.flow_id) flowId = d.flow_id;
      await new Promise((r) => setTimeout(r, 350));
    }
    if (allOk) {
      logMode("单元测试完成: flow_id=" + flowId + " steps=" + stepResults.length + " ok=true");
      logMode("全部测试节点探活通过，开始连线流量动画", "");
      syncFlowViz("test", pathNodesForTest, stepStatus, { edgesEnabled: true });
      state.flowViz.metricsByEdge = {};
      (state.topology.edges || []).forEach((e) => {
        if (pathNodesForTest.includes(e.from) && pathNodesForTest.includes(e.to)) {
          state.flowViz.metricsByEdge[e.id] = edgeMetrics(e.id, "RUNNING");
        }
      });
      appendJsonDetail("单元测试原始响应", { flow_id: flowId, steps: stepResults, ok: true });
      toast("单元测试完成", "ok");
      redrawGraph();
    } else {
      const failCount = pathNodesForTest.filter((nid) => stepStatus[nid] === "FAILED").length;
      logMode("单元测试汇总: fail_steps=" + failCount + " flow_id=" + flowId, "warn");
      syncFlowViz("test", pathNodesForTest.filter((nid) => stepStatus[nid]), stepStatus, { edgesEnabled: false });
      appendJsonDetail("单元测试原始响应", { flow_id: flowId, steps: stepResults, ok: false });
      toast("单元测试含失败节点", "warn");
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

  function topoSortNodeIds(nodes, edges) {
    const ids = (nodes || []).map((n) => String(n.id || "")).filter(Boolean);
    if (!ids.length) return [];
    const indeg = {};
    const adj = {};
    ids.forEach((id) => { indeg[id] = 0; adj[id] = []; });
    (edges || []).forEach((e) => {
      const fromId = String(e.from || "");
      const toId = String(e.to || "");
      if (!fromId || !toId || indeg[fromId] == null || indeg[toId] == null) return;
      adj[fromId].push(toId);
      indeg[toId] += 1;
    });
    const q = ids.filter((id) => indeg[id] === 0);
    const out = [];
    while (q.length) {
      const cur = q.shift();
      out.push(cur);
      (adj[cur] || []).forEach((nx) => {
        indeg[nx] -= 1;
        if (indeg[nx] === 0) q.push(nx);
      });
    }
    return out.length === ids.length ? out : ids;
  }

  function resolveOrderedPathNodes(startNode, endNode) {
    const start = String(startNode || "").trim();
    const end = String(endNode || "").trim();
    if (!start && !end) return [];
    if (!start || !end || start === end) return [start || end].filter(Boolean);
    const edges = state.topology.edges || [];
    const adj = {};
    edges.forEach((e) => {
      if (!adj[e.from]) adj[e.from] = [];
      adj[e.from].push(e);
    });
    const q = [start];
    const prev = {};
    const visited = new Set([start]);
    let found = false;
    while (q.length) {
      const cur = q.shift();
      if (cur === end) { found = true; break; }
      (adj[cur] || []).forEach((e) => {
        const nx = e.to;
        if (visited.has(nx)) return;
        visited.add(nx);
        prev[nx] = cur;
        q.push(nx);
      });
    }
    if (!found) return [start, end];
    const path = [];
    let cursor = end;
    while (cursor) {
      path.unshift(cursor);
      if (cursor === start) break;
      cursor = prev[cursor] || "";
    }
    return path;
  }

  function resolvePathNodesForTest(scope, startNode, endNode) {
    if (scope === "full") {
      return topoSortNodeIds(state.topology.nodes || [], state.topology.edges || []);
    }
    return resolveOrderedPathNodes(startNode, endNode);
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

