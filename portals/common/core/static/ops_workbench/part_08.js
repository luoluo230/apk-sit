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
    let rows = (resp && Array.isArray(resp.projects)) ? resp.projects.slice() : [];
    if (resp && resp.ok === false && !rows.length) return;
    if (state.projectId && !rows.some((item) => String(item.id) === String(state.projectId))) {
      rows.unshift({ id: state.projectId, name: state.projectId });
    }
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
      const prefer = rows.find((item) => String(item.id) === "GomeKu") || rows[0];
      state.projectId = String((prefer && prefer.id) || state.projectId || "GomeKu");
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
    state.autoRunModeLogged = false;
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

