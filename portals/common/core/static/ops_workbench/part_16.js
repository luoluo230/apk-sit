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
    bindEventsShell();
    bindEventsActions();
    bindEventsCanvas();
  }
  function bindEventsShell() {
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
        trySetMode(btn.getAttribute("data-mode-value") || "edit");
      };
    });

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
  }
