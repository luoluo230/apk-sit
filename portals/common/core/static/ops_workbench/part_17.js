  function bindEventsActions() {
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
    if ($("btnDeleteEdge")) $("btnDeleteEdge").onclick = async () => {
      const id = state.selection.edgeId;
      if (!id) { toast("请先选中一条连线", "warn"); return; }
      await confirmStructuredDeleteEdge(id);
    };

    if ($("structuredAddClose")) $("structuredAddClose").onclick = closeStructuredAddMenu;
    const modeSelectEl = $("modeSelect");
    if (modeSelectEl) {
      modeSelectEl.onchange = () => {
        trySetMode(modeSelectEl.value || "edit");
      };
    }
    const modeLockEl = $("modeLockBtn");
    if (modeLockEl) {
      modeLockEl.onclick = () => { lockCurrentMode(); };
    }
    const modeUnlockEl = $("modeUnlockBtn");
    if (modeUnlockEl) {
      modeUnlockEl.onclick = () => { unlockMode(); };
    }
    const modeLockSwitch = $("modeLockSwitch");
    if (modeLockSwitch) {
      modeLockSwitch.onchange = () => {
        if (modeLockSwitch.checked) lockCurrentMode();
        else unlockMode();
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
  }
  function bindEventsCanvas() {
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
        if (state.lockedMode && state.lockedMode !== "edit") {
          toast("当前已锁定为" + (MODE_LABELS[state.lockedMode] || state.lockedMode) + "，无法进入编辑", "warn");
          return;
        }
        trySetMode("edit", { silent: true });
      }
      openStructuredAddMenu(from);
    } catch (_) {}
  }

