(function () {
  const POLL_MS = 2000;
  const root = document.querySelector('.agent-console-shell[data-page="agent-control"]');
  if (!root || !window.OpsApi) return;

  const state = {
    projectId: String(root.dataset.projectId || ''),
    agents: [],
    filteredAgents: [],
    selectedIds: new Set(),
    page: 1,
    pageSize: 6,
    view: 'card',
    timer: null,
    createMode: false,
    filters: {
      status: '',
      query: '',
      serviceStatus: '',
      fresh: 'all',
    },
  };

  const elements = {
    summaryCards: document.getElementById('agentSummaryCards'),
    cards: document.getElementById('agentCards'),
    list: document.getElementById('agentList'),
    resultsMeta: document.getElementById('agentResultsMeta'),
    paginationMeta: document.getElementById('agentPaginationMeta'),
    selectedCount: document.getElementById('selectedCountLabel'),
    pageIndicator: document.getElementById('pageIndicator'),
    pageSize: document.getElementById('pageSizeSelect'),
    selectPage: document.getElementById('selectPage'),
    cardView: document.getElementById('btnCardView'),
    listView: document.getElementById('btnListView'),
    filterStatus: document.getElementById('filterStatus'),
    filterQuery: document.getElementById('filterQuery'),
    filterServiceStatus: document.getElementById('filterServiceStatus'),
    filterFresh: document.getElementById('filterFresh'),
    batchMoreMenu: document.getElementById('batchMoreMenu'),
    modal: document.getElementById('agentEditModal'),
    editTitle: document.getElementById('agentEditTitle'),
    editAgentId: document.getElementById('editAgentId'),
    editDeviceId: document.getElementById('editDeviceId'),
    editHostIp: document.getElementById('editHostIp'),
    editDisplayName: document.getElementById('editDisplayName'),
    editPort: document.getElementById('editPort'),
    editRunState: document.getElementById('editRunState'),
    editDesc: document.getElementById('editDesc'),
  };

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[char]));
  }

  function toast(message, tone) {
    let node = document.getElementById('opsToast');
    if (!node) {
      node = document.createElement('div');
      node.id = 'opsToast';
      node.className = 'ops-agent-toast';
      document.body.appendChild(node);
    }
    node.className = `ops-agent-toast ${tone || ''}`;
    node.textContent = message || '';
    clearTimeout(node._timer);
    node._timer = setTimeout(() => node.remove(), 2600);
  }

  function ensureOk(response, fallback) {
    if (response && (response.error_code === 'OPS_AUTH_REQUIRED' || response.error === 'auth_redirect')) {
      window.location.href = '/login';
      return false;
    }
    if (!response || !response.ok) {
      toast((response && (response.message || response.error)) || fallback || '请求失败', 'error');
      return false;
    }
    return true;
  }

  function statusMeta(status) {
    const value = String(status || 'UNKNOWN').toUpperCase();
    if (['ONLINE', 'RUNNING', 'READY', 'SUCCESS'].includes(value)) return { key: 'ok', label: '在线' };
    if (['DEGRADED', 'FAILED', 'ERROR'].includes(value)) return { key: 'warn', label: '异常' };
    if (['OFFLINE', 'TIMEOUT', 'STOPPED', 'CANCELED'].includes(value)) return { key: 'err', label: '离线' };
    return { key: 'info', label: '未知' };
  }

  function percentValue(metrics, key) {
    const source = metrics && typeof metrics === 'object'
      ? ((metrics.control && typeof metrics.control === 'object') ? metrics.control : metrics)
      : {};
    const raw = source[key];
    if (raw == null || raw === '') return '--';
    const number = Number(raw);
    return Number.isFinite(number) ? `${Math.round(number)}%` : String(raw);
  }

  function heartbeatAgeSeconds(agent) {
    const value = Number(agent.last_seen_age_sec);
    return Number.isFinite(value) ? value : Number.MAX_SAFE_INTEGER;
  }

  function serviceSummary(agent) {
    const services = Array.isArray(agent.services) ? agent.services : [];
    return services.reduce((acc, service) => {
      const status = String(service.status || service.run_state || '').toUpperCase();
      acc.total += 1;
      if (['ONLINE', 'RUNNING', 'READY', 'SUCCESS'].includes(status)) acc.online += 1;
      else if (['OFFLINE', 'STOPPED', 'TIMEOUT', 'CANCELED'].includes(status)) acc.offline += 1;
      else acc.abnormal += 1;
      return acc;
    }, { total: 0, online: 0, abnormal: 0, offline: 0 });
  }

  function serviceStatusLabel(summary) {
    if (!summary.total) return { text: '暂无服务', cls: 'service-muted' };
    if (summary.abnormal) return { text: `服务异常 ${summary.abnormal}`, cls: 'service-warn' };
    if (summary.offline === summary.total) return { text: '全部离线', cls: 'service-muted' };
    return { text: '全部正常', cls: 'service-ok' };
  }

  function probePayloadForAgent(agent) {
    const host = String(agent.host_ip || agent.host_name || '').trim();
    return {
      project_id: state.projectId,
      agent_id: String(agent.agent_id || ''),
      host_name: host,
      ip: host,
      port: Number(agent.port || agent.remote_game_server_port || 0),
    };
  }

  function matchesFilters(agent) {
    const status = String(agent.effective_status || agent.status || '').toUpperCase();
    if (state.filters.status && status !== state.filters.status) return false;

    const query = state.filters.query.trim().toLowerCase();
    if (query) {
      const haystack = [
        agent.display_name,
        agent.agent_id,
        agent.device_id,
        agent.host_ip,
        agent.host_name,
        agent.desc,
      ].map((item) => String(item || '').toLowerCase()).join(' ');
      if (!haystack.includes(query)) return false;
    }

    if (state.filters.fresh !== 'all') {
      const ttl = state.filters.fresh === 'active_600' ? 600 : 120;
      if (heartbeatAgeSeconds(agent) > ttl) return false;
    }

    if (state.filters.serviceStatus) {
      const summary = serviceSummary(agent);
      if (state.filters.serviceStatus === 'healthy' && !(summary.total > 0 && summary.online === summary.total)) return false;
      if (state.filters.serviceStatus === 'abnormal' && summary.abnormal < 1) return false;
      if (state.filters.serviceStatus === 'offline' && !(summary.total > 0 && summary.offline === summary.total)) return false;
    }

    return true;
  }

  function applyFilters() {
    state.filteredAgents = state.agents.filter(matchesFilters);
    const maxPage = Math.max(1, Math.ceil(state.filteredAgents.length / state.pageSize));
    if (state.page > maxPage) state.page = maxPage;
  }

  function pageRows() {
    const start = (state.page - 1) * state.pageSize;
    return state.filteredAgents.slice(start, start + state.pageSize);
  }

  function renderSummary(summaryResponse, agents) {
    const list = Array.isArray(agents) ? agents : [];
    const metrics = summaryResponse && summaryResponse.metrics ? summaryResponse.metrics : {};
    const onlineCount = list.filter((item) => ['ONLINE', 'RUNNING', 'READY', 'SUCCESS'].includes(String(item.effective_status || item.status || '').toUpperCase())).length;
    const cards = [
      { tone: 'blue', icon: 'device', title: '在线 Agent', value: onlineCount, desc: '实时在线设备数' },
      { tone: 'green', icon: 'user', title: '注册 Agent', value: list.length, desc: '已注册设备总数' },
      { tone: 'orange', icon: 'clock', title: '待执行任务', value: metrics.jobs_pending || 0, desc: '等待执行的任务数' },
      { tone: 'violet', icon: 'play', title: '运行任务', value: metrics.jobs_running || 0, desc: '正在运行的任务数' },
    ];
    elements.summaryCards.innerHTML = cards.map((card) => `
      <article class="agent-summary-card-mock tone-${esc(card.tone)}">
        <div class="agent-summary-icon"><span class="agent-summary-svg ${esc(card.icon)}"></span></div>
        <div class="agent-summary-copy">
          <div class="agent-summary-label">${esc(card.title)}</div>
          <div class="agent-summary-value">${esc(card.value)}</div>
          <div class="agent-summary-desc">${esc(card.desc)}</div>
        </div>
      </article>
    `).join('');
  }

  function renderResultsMeta() {
    const total = state.filteredAgents.length;
    const totalPages = Math.max(1, Math.ceil(total / state.pageSize));
    elements.resultsMeta.innerHTML = `
      <div class="agent-list-head-left"><b>${esc(total)}</b><span>个 Agent 符合当前筛选条件</span></div>
      <div class="agent-list-head-right">视图：${state.view === 'card' ? '卡片' : '列表'} · 第 ${state.page} / ${totalPages} 页</div>
    `;
    elements.paginationMeta.textContent = `共 ${total} 条`;
    elements.selectedCount.textContent = `已选择 ${state.selectedIds.size} 项`;
    elements.pageIndicator.textContent = String(state.page);
    const rows = pageRows();
    elements.selectPage.checked = rows.length > 0 && rows.every((item) => state.selectedIds.has(String(item.agent_id || '')));
  }

  function renderCard(agent) {
    const agentId = String(agent.agent_id || '');
    const status = statusMeta(agent.effective_status || agent.status);
    const summary = serviceSummary(agent);
    const summaryLabel = serviceStatusLabel(summary);
    const selected = state.selectedIds.has(agentId);
    const title = agent.display_name || agent.device_id || agentId;
    const titleHref = `/admin/ops-platform/agent-detail?project_id=${encodeURIComponent(state.projectId)}&agent_id=${encodeURIComponent(agentId)}`;
    return `
      <article class="agent-mock-card ${selected ? 'selected' : ''} ${status.key === 'warn' ? 'warn' : ''} ${status.key === 'err' ? 'offline' : ''}">
        <div class="agent-card-head">
          <label class="agent-card-check mock"><input type="checkbox" data-select-agent="${esc(agentId)}" ${selected ? 'checked' : ''}></label>
          <div class="agent-card-main mock">
            <div class="agent-card-title-row mock">
              <div class="agent-card-title-wrap">
                <span class="agent-card-device-svg"></span>
                <div class="agent-card-title">${esc(title)}</div>
                <span class="agent-status-pill ${esc(status.key)}"><span class="agent-status-pill-dot ${esc(status.key)}"></span>${esc(status.label)}</span>
              </div>
              <button class="agent-card-more" type="button" aria-label="更多">⋮</button>
            </div>
            <div class="agent-card-meta mock">
              <span>IP：${esc(agent.host_ip || agent.host_name || '-')}</span>
              <span>最后心跳：${esc(agent.last_seen || '-')}</span>
            </div>
            <div class="agent-card-metrics mock">
              <span class="agent-pill cpu">CPU ${esc(percentValue(agent.metrics, 'cpu_percent'))}</span>
              <span class="agent-pill mem">MEM ${esc(percentValue(agent.metrics, 'mem_percent'))}</span>
              <span class="agent-pill disk">DISK ${esc(percentValue(agent.metrics, 'disk_percent'))}</span>
            </div>
            <div class="agent-card-service mock">
              <span class="agent-card-service-main">服务 ${esc(summary.online)}/${esc(summary.total)}</span>
              <span class="${esc(summaryLabel.cls)}">${esc(summaryLabel.text)}</span>
            </div>
            <div class="agent-card-actions mock">
              <a class="agent-card-action-btn" href="${titleHref}"><span class="agent-action-inline"><span class="agent-btn-icon detail small"></span><span>查看详情</span></span></a>
              <button class="agent-card-action-btn" type="button" data-edit-agent="${esc(agentId)}"><span class="agent-action-inline"><span class="agent-btn-icon edit small"></span><span>编辑</span></span></button>
              <button class="agent-card-action-btn" type="button" data-probe-agent="${esc(agentId)}"><span class="agent-action-inline"><span class="agent-btn-icon probe small"></span><span>探测</span></span></button>
            </div>
          </div>
        </div>
      </article>
    `;
  }

  function renderTable() {
    const rows = pageRows();
    elements.list.innerHTML = `
      <div class="ops-table-wrap">
        <table class="agent-table">
          <thead>
            <tr>
              <th></th>
              <th>Agent / 设备</th>
              <th>状态</th>
              <th>IP / 最后心跳</th>
              <th>资源</th>
              <th>服务状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((agent) => {
              const agentId = String(agent.agent_id || '');
              const status = statusMeta(agent.effective_status || agent.status);
              const summary = serviceSummary(agent);
              const summaryLabel = serviceStatusLabel(summary);
              return `
                <tr>
                  <td><input type="checkbox" data-select-agent="${esc(agentId)}" ${state.selectedIds.has(agentId) ? 'checked' : ''}></td>
                  <td><div class="table-title">${esc(agent.display_name || agent.device_id || agentId)}</div><div class="table-sub">${esc(agent.device_id || '-')}</div></td>
                  <td><span class="agent-status-pill ${esc(status.key)}"><span class="agent-status-pill-dot ${esc(status.key)}"></span>${esc(status.label)}</span></td>
                  <td><div>${esc(agent.host_ip || agent.host_name || '-')}</div><div class="table-sub">${esc(agent.last_seen || '-')}</div></td>
                  <td>CPU ${esc(percentValue(agent.metrics, 'cpu_percent'))} / MEM ${esc(percentValue(agent.metrics, 'mem_percent'))} / DISK ${esc(percentValue(agent.metrics, 'disk_percent'))}</td>
                  <td><span>${esc(summary.online)}/${esc(summary.total)}</span> <span class="${esc(summaryLabel.cls)}">${esc(summaryLabel.text)}</span></td>
                  <td class="table-actions">
                    <a class="btn ghost" href="/admin/ops-platform/agent-detail?project_id=${encodeURIComponent(state.projectId)}&agent_id=${encodeURIComponent(agentId)}">详情</a>
                    <button class="btn ghost" type="button" data-edit-agent="${esc(agentId)}">编辑</button>
                    <button class="btn" type="button" data-probe-agent="${esc(agentId)}">探测</button>
                  </td>
                </tr>
              `;
            }).join('') || '<tr><td colspan="7"><div class="ops-empty">当前筛选条件下暂无 Agent</div></td></tr>'}
          </tbody>
        </table>
      </div>
    `;
  }

  function bindRowActions(container) {
    container.querySelectorAll('[data-select-agent]').forEach((node) => {
      node.onchange = () => {
        const id = String(node.getAttribute('data-select-agent') || '');
        if (!id) return;
        if (node.checked) state.selectedIds.add(id);
        else state.selectedIds.delete(id);
        renderResultsMeta();
      };
    });
    container.querySelectorAll('[data-edit-agent]').forEach((node) => {
      node.onclick = () => openEdit(String(node.getAttribute('data-edit-agent') || ''));
    });
    container.querySelectorAll('[data-probe-agent]').forEach((node) => {
      node.onclick = () => probeAgent(String(node.getAttribute('data-probe-agent') || ''));
    });
  }

  function renderCards() {
    const rows = pageRows();
    elements.cards.innerHTML = rows.length
      ? rows.map(renderCard).join('')
      : '<div class="ops-empty">当前筛选条件下暂无 Agent</div>';
  }

  function renderView() {
    applyFilters();
    renderResultsMeta();
    renderCards();
    renderTable();
    elements.cards.classList.toggle('hidden', state.view !== 'card');
    elements.list.classList.toggle('hidden', state.view !== 'list');
    elements.cardView.classList.toggle('active', state.view === 'card');
    elements.listView.classList.toggle('active', state.view === 'list');
    bindRowActions(elements.cards);
    bindRowActions(elements.list);
  }

  function findAgent(agentId) {
    return state.agents.find((item) => String(item.agent_id || '') === agentId) || null;
  }

  function selectedAgents() {
    return state.agents.filter((item) => state.selectedIds.has(String(item.agent_id || '')));
  }

  async function probeAgent(agentId) {
    const agent = findAgent(agentId);
    if (!agent) return;
    const response = await window.OpsApi.probeAgent(probePayloadForAgent(agent));
    if (!ensureOk(response, '探测失败')) return;
    toast('探测请求已提交', 'success');
    await loadPage();
  }

  async function batchProbe() {
    const agents = selectedAgents();
    if (!agents.length) return toast('请先选择 Agent', 'info');
    for (const agent of agents) {
      await window.OpsApi.probeAgent(probePayloadForAgent(agent));
    }
    toast(`已提交 ${agents.length} 个 Agent 的探测请求`, 'success');
    await loadPage();
  }

  async function batchRestart() {
    const agents = selectedAgents();
    if (!agents.length) return toast('请先选择 Agent', 'info');
    let count = 0;
    for (const agent of agents) {
      const services = Array.isArray(agent.services) ? agent.services : [];
      for (const service of services) {
        if (!service.service_id) continue;
        const response = await window.OpsApi.serviceAction({
          project_id: state.projectId,
          service_id: String(service.service_id),
          agent_id: String(service.agent_id || agent.agent_id || ''),
          action: 'restart',
        });
        if (response && response.ok) count += 1;
      }
    }
    if (!count) return toast('所选 Agent 暂无可重启服务', 'error');
    toast(`已提交 ${count} 个服务的重启请求`, 'success');
    await loadPage();
  }

  function fillEditForm(agent) {
    elements.editAgentId.value = String(agent.agent_id || '');
    elements.editDeviceId.value = String(agent.device_id || '');
    elements.editHostIp.value = String(agent.host_ip || agent.host_name || '');
    elements.editDisplayName.value = String(agent.display_name || '');
    elements.editPort.value = String(agent.port || agent.remote_game_server_port || '');
    elements.editRunState.value = '';
    elements.editDesc.value = String(agent.desc || '');
  }

  function openEdit(agentId) {
    const agent = findAgent(agentId);
    if (!agent) return;
    state.createMode = false;
    elements.editTitle.textContent = '编辑 Agent';
    fillEditForm(agent);
    elements.modal.classList.remove('hidden');
  }

  function openCreate() {
    state.createMode = true;
    elements.editTitle.textContent = '新建设备 Agent';
    elements.editAgentId.value = `agent-${Date.now()}`;
    elements.editDeviceId.value = '';
    elements.editHostIp.value = '';
    elements.editDisplayName.value = '';
    elements.editPort.value = '';
    elements.editRunState.value = 'ONLINE';
    elements.editDesc.value = '';
    elements.modal.classList.remove('hidden');
  }

  function closeEdit() {
    elements.modal.classList.add('hidden');
  }

  async function saveEdit() {
    const isCreate = state.createMode;
    const payload = {
      agent_id: String(elements.editAgentId.value || '').trim(),
      project_id: state.projectId,
      device_id: String(elements.editDeviceId.value || '').trim(),
      host_name: String(elements.editHostIp.value || '').trim(),
      host_ip: String(elements.editHostIp.value || '').trim(),
      display_name: String(elements.editDisplayName.value || '').trim(),
      port: Number(elements.editPort.value || 0),
      remote_game_server_port: Number(elements.editPort.value || 0),
      run_state: String(elements.editRunState.value || '').trim(),
      desc: String(elements.editDesc.value || '').trim(),
      create_if_missing: isCreate,
      status: 'ONLINE',
    };
    if (!payload.agent_id) return toast('Agent ID 不能为空', 'error');
    const response = await window.OpsApi.upsertAgent(payload);
    if (!ensureOk(response, '保存失败')) return;
    closeEdit();
    if (isCreate) {
      state.page = 1;
      state.filters = { status: '', query: '', serviceStatus: '', fresh: 'all' };
      elements.filterStatus.value = '';
      elements.filterQuery.value = '';
      elements.filterServiceStatus.value = '';
      elements.filterFresh.value = 'all';
    }
    toast(isCreate ? '新建设备 Agent 成功' : 'Agent 信息保存成功', 'success');
    await loadPage();
  }

  function readFilters() {
    state.filters.status = String(elements.filterStatus.value || '');
    state.filters.query = String(elements.filterQuery.value || '');
    state.filters.serviceStatus = String(elements.filterServiceStatus.value || '');
    state.filters.fresh = String(elements.filterFresh.value || 'all');
    state.page = 1;
  }

  function resetFilters() {
    elements.filterStatus.value = '';
    elements.filterQuery.value = '';
    elements.filterServiceStatus.value = '';
    elements.filterFresh.value = 'all';
    state.filters = { status: '', query: '', serviceStatus: '', fresh: 'all' };
    state.page = 1;
    renderView();
  }

  function toggleMenu(menu, open) {
    if (!menu) return;
    const next = typeof open === 'boolean' ? open : menu.classList.contains('hidden');
    menu.classList.toggle('hidden', !next);
  }

  async function loadPage() {
    const [summaryResponse, agentsResponse] = await Promise.all([
      window.OpsApi.controlPlaneSummary(),
      window.OpsApi.agents(state.projectId, '', '', 'all', ''),
    ]);
    if (!ensureOk(agentsResponse, 'Agent 列表加载失败')) return;
    state.agents = Array.isArray(agentsResponse.agents) ? agentsResponse.agents : [];
    if (summaryResponse && summaryResponse.ok) renderSummary(summaryResponse, state.agents);
    renderView();
  }

  function bindStaticActions() {
    document.getElementById('btnApplyFilter').onclick = () => {
      readFilters();
      renderView();
    };
    document.getElementById('btnResetFilter').onclick = resetFilters;
    elements.cardView.onclick = () => { state.view = 'card'; renderView(); };
    elements.listView.onclick = () => { state.view = 'list'; renderView(); };
    document.getElementById('btnPrevPage').onclick = () => {
      state.page = Math.max(1, state.page - 1);
      renderView();
    };
    document.getElementById('btnNextPage').onclick = () => {
      const maxPage = Math.max(1, Math.ceil(state.filteredAgents.length / state.pageSize));
      state.page = Math.min(maxPage, state.page + 1);
      renderView();
    };
    elements.pageSize.onchange = () => {
      state.pageSize = Math.max(1, Number(elements.pageSize.value || 6));
      state.page = 1;
      renderView();
    };
    elements.selectPage.onchange = () => {
      pageRows().forEach((agent) => {
        const id = String(agent.agent_id || '');
        if (elements.selectPage.checked) state.selectedIds.add(id);
        else state.selectedIds.delete(id);
      });
      renderView();
    };

    document.getElementById('btnBatchProbe').onclick = batchProbe;
    document.getElementById('btnBatchRestart').onclick = batchRestart;
    document.getElementById('btnBatchBind').onclick = () => toast('当前后端未提供批量绑定服务接口，入口已保留', 'info');
    document.getElementById('btnCleanupExpired').onclick = async () => {
      const response = await window.OpsApi.cleanupExpiredAgents({ project_id: state.projectId, ttl_hours: 24 });
      if (!ensureOk(response, '清理失败')) return;
      toast(`已清理 ${response.deleted_count || 0} 个过期 Agent`, 'success');
      await loadPage();
    };
    document.getElementById('btnCreateAgent').onclick = openCreate;
    document.getElementById('btnProbeAllAgent').onclick = async () => {
      const response = await window.OpsApi.probeAllAgents({ project_id: state.projectId });
      if (!ensureOk(response, '批量探测失败')) return;
      toast('已提交全量探测请求', 'success');
      await loadPage();
    };
    document.getElementById('btnProbeRepairAllAgent').onclick = async () => {
      const response = await window.OpsApi.probeRepairAgents({ project_id: state.projectId });
      if (!ensureOk(response, '批量修复并探测失败')) return;
      toast('已提交批量修复并探测请求', 'success');
      await loadPage();
    };

    document.getElementById('btnBatchMore').onclick = (event) => {
      event.stopPropagation();
      toggleMenu(elements.batchMoreMenu);
    };
    document.getElementById('btnClearSelection').onclick = () => {
      state.selectedIds.clear();
      toggleMenu(elements.batchMoreMenu, false);
      renderView();
    };
    document.getElementById('btnRefreshNow').onclick = async () => {
      toggleMenu(elements.batchMoreMenu, false);
      await loadPage();
      toast('列表已刷新', 'success');
    };

    document.getElementById('btnCloseAgentEdit').onclick = closeEdit;
    document.getElementById('btnCancelAgentEdit').onclick = closeEdit;
    document.getElementById('btnSaveAgentEdit').onclick = saveEdit;
    document.getElementById('btnProbeAgent').onclick = async () => {
      const editingId = String(elements.editAgentId.value || '').trim();
      if (editingId) await probeAgent(editingId);
    };

    document.addEventListener('click', () => toggleMenu(elements.batchMoreMenu, false));
  }

  function startPolling() {
    clearInterval(state.timer);
    state.timer = setInterval(() => {
      loadPage().catch(() => {});
    }, POLL_MS);
  }

  bindStaticActions();
  loadPage().catch((error) => {
    console.error('[agent-control] boot failed', error);
    toast('Agent 管控中心初始化失败', 'error');
  });
  startPolling();
})();
