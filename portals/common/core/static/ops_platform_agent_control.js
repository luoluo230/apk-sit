(function () {
  const root = document.querySelector('.agent-screen--control');
  if (!root) return;

  const POLL_MS = 2000;
  const state = {
    projectId: String(root.dataset.projectId || ''),
    liveAgents: [],
    rows: [],
    filteredRows: [],
    selectedIds: new Set(),
    page: 1,
    pageSize: 6,
    view: 'card',
    timer: null,
    createMode: false,
    primaryAgentId: '',
    filters: {
      status: '',
      query: '',
      serviceStatus: '',
      fresh: 'active_120',
    },
  };

  const nodes = {
    summary: document.getElementById('agentSummaryCards'),
    cards: document.getElementById('agentCards'),
    list: document.getElementById('agentList'),
    meta: document.getElementById('agentResultsMeta'),
    paginationMeta: document.getElementById('agentPaginationMeta'),
    pageIndicator: document.getElementById('pageIndicator'),
    pageSize: document.getElementById('pageSizeSelect'),
    selectPage: document.getElementById('selectPage'),
    selectedCount: document.getElementById('selectedCountLabel'),
    cardView: document.getElementById('btnCardView'),
    listView: document.getElementById('btnListView'),
    filterStatus: document.getElementById('filterStatus'),
    filterQuery: document.getElementById('filterQuery'),
    filterServiceStatus: document.getElementById('filterServiceStatus'),
    filterFresh: document.getElementById('filterFresh'),
    batchMenu: document.getElementById('batchMoreMenu'),
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

  const SHOWCASE_SUMMARY = [
    { tone: 'blue', icon: '⌘', title: '在线 Agent', value: '4', desc: '实时在线设备数' },
    { tone: 'green', icon: '◌', title: '注册 Agent', value: '8', desc: '已注册设备总数' },
    { tone: 'orange', icon: '◔', title: '待执行任务', value: '2', desc: '等待执行的任务数' },
    { tone: 'purple', icon: '▶', title: '运行任务', value: '1', desc: '正在运行的任务数' },
  ];

  const SHOWCASE_AGENTS = [
    { preview: 'remote-device-127001', ip: '10.0.0.1', heartbeat: '2026-06-01 11:14:15', status: 'ONLINE', statusText: '在线', cpu: 42, mem: 79, disk: 67, serviceOnline: 3, serviceTotal: 3, serviceText: '全部正常', serviceTone: 'ok', selected: true },
    { preview: 'remote-device-127002', ip: '10.0.0.2', heartbeat: '2026-06-01 11:13:02', status: 'ONLINE', statusText: '在线', cpu: 25, mem: 56, disk: 48, serviceOnline: 2, serviceTotal: 3, serviceText: '服务异常 1', serviceTone: 'warn', selected: true },
    { preview: 'remote-device-127003', ip: '10.0.0.3', heartbeat: '2026-06-01 10:58:41', status: 'WARN', statusText: '异常', cpu: 92, mem: 88, disk: 93, serviceOnline: 1, serviceTotal: 3, serviceText: '服务异常 2', serviceTone: 'warn', selected: false },
    { preview: 'remote-device-127004', ip: '10.0.0.4', heartbeat: '2026-06-01 09:42:18', status: 'OFFLINE', statusText: '离线', cpu: 0, mem: 0, disk: 0, serviceOnline: 0, serviceTotal: 3, serviceText: '全部离线', serviceTone: 'offline', selected: false },
    { preview: 'remote-device-127005', ip: '10.0.0.5', heartbeat: '2026-06-01 11:12:33', status: 'ONLINE', statusText: '在线', cpu: 18, mem: 45, disk: 31, serviceOnline: 3, serviceTotal: 3, serviceText: '全部正常', serviceTone: 'ok', selected: false },
    { preview: 'remote-device-127006', ip: '10.0.0.6', heartbeat: '2026-06-01 11:10:59', status: 'ONLINE', statusText: '在线', cpu: 63, mem: 71, disk: 60, serviceOnline: 2, serviceTotal: 3, serviceText: '服务异常 1', serviceTone: 'warn', selected: false },
    { preview: 'remote-device-127007', ip: '10.0.0.7', heartbeat: '2026-06-01 11:09:17', status: 'ONLINE', statusText: '在线', cpu: 34, mem: 41, disk: 26, serviceOnline: 3, serviceTotal: 3, serviceText: '全部正常', serviceTone: 'ok', selected: false },
    { preview: 'remote-device-127008', ip: '10.0.0.8', heartbeat: '2026-06-01 11:06:48', status: 'WARN', statusText: '异常', cpu: 57, mem: 66, disk: 72, serviceOnline: 2, serviceTotal: 3, serviceText: '服务异常 1', serviceTone: 'warn', selected: false },
  ];

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (char) {
      return {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      }[char];
    });
  }

  function toast(message, tone) {
    const kind = tone === 'error' ? 'is-error' : 'is-success';
    let node = document.getElementById('agentControlToast');
    if (!node) {
      node = document.createElement('div');
      node.id = 'agentControlToast';
      node.className = 'agent-inline-note';
      node.style.position = 'fixed';
      node.style.right = '24px';
      node.style.bottom = '24px';
      node.style.zIndex = '50';
      node.style.minWidth = '240px';
      document.body.appendChild(node);
    }
    node.className = 'agent-inline-note ' + kind;
    node.textContent = message;
    clearTimeout(node._timer);
    node._timer = setTimeout(function () { node.remove(); }, 2600);
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

  function stateClass(status) {
    if (status === 'ONLINE') return 'agent-state-pill--ok';
    if (status === 'OFFLINE') return 'agent-state-pill--offline';
    if (status === 'WARN') return 'agent-state-pill--warn';
    return 'agent-state-pill--info';
  }

  function ageFromIso(value) {
    if (!value) return Number.MAX_SAFE_INTEGER;
    const ms = Date.parse(value);
    if (!Number.isFinite(ms)) return Number.MAX_SAFE_INTEGER;
    return Math.max(0, Math.round((Date.now() - ms) / 1000));
  }

  function formatDate(value) {
    if (!value) return '--';
    const ms = Date.parse(value);
    if (!Number.isFinite(ms)) return String(value);
    const date = new Date(ms);
    const pad = function (num) { return String(num).padStart(2, '0'); };
    return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate()) + ' ' + pad(date.getHours()) + ':' + pad(date.getMinutes()) + ':' + pad(date.getSeconds());
  }

  function percent(value, fallback) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.max(0, Math.round(number)) : fallback;
  }

  function summarizeServices(services) {
    const rows = Array.isArray(services) ? services : [];
    const summary = { total: rows.length, online: 0, abnormal: 0, offline: 0 };
    rows.forEach(function (service) {
      const status = String(service.status || service.run_state || '').toUpperCase();
      if (status === 'ONLINE' || status === 'RUNNING' || status === 'READY' || status === 'SUCCESS') summary.online += 1;
      else if (status === 'OFFLINE' || status === 'STOPPED') summary.offline += 1;
      else summary.abnormal += 1;
    });
    return summary;
  }

  function primaryAgent() {
    return state.liveAgents[0] || null;
  }

  function buildShowcaseRows() {
    const live = primaryAgent();
    const liveSummary = summarizeServices(live && live.services);
    const liveMetrics = live && live.metrics && live.metrics.control ? live.metrics.control : (live && live.metrics) || {};
    const primaryId = live ? String(live.agent_id || '') : '';
    state.primaryAgentId = primaryId;
    return SHOWCASE_AGENTS.map(function (item, index) {
      const isRealBacked = index === 0 && live;
      const row = {
        rowId: isRealBacked ? primaryId : item.preview,
        agentId: isRealBacked ? primaryId : '',
        preview: item.preview,
        title: item.preview,
        ip: item.ip,
        heartbeat: item.heartbeat,
        freshAge: 36 + index * 8,
        status: item.status,
        statusText: item.statusText,
        cpu: item.cpu,
        mem: item.mem,
        disk: item.disk,
        serviceOnline: item.serviceOnline,
        serviceTotal: item.serviceTotal,
        serviceText: item.serviceText,
        serviceTone: item.serviceTone,
        description: isRealBacked ? String(live.desc || '') : '设计态预览卡片',
        source: isRealBacked ? 'live-backed' : 'showcase',
        canAction: !!isRealBacked,
      };

      if (isRealBacked) {
        row.freshAge = 36;
      }

      return row;
    });
  }

  function matchesFilters(row) {
    if (state.filters.status) {
      if (state.filters.status === 'DEGRADED' && row.status !== 'WARN') return false;
      if (state.filters.status === 'OFFLINE' && row.status !== 'OFFLINE') return false;
      if (state.filters.status === 'ONLINE' && row.status !== 'ONLINE') return false;
    }

    const query = String(state.filters.query || '').trim().toLowerCase();
    if (query) {
      const haystack = [row.title, row.ip, row.description, row.preview].join(' ').toLowerCase();
      if (haystack.indexOf(query) < 0) return false;
    }

    if (state.filters.serviceStatus === 'healthy' && row.serviceTone !== 'ok') return false;
    if (state.filters.serviceStatus === 'abnormal' && row.serviceTone !== 'warn') return false;
    if (state.filters.serviceStatus === 'offline' && row.serviceTone !== 'offline') return false;

    if (state.filters.fresh === 'active_120' && row.freshAge > 120) return false;
    if (state.filters.fresh === 'active_600' && row.freshAge > 600) return false;

    return true;
  }

  function currentPageRows() {
    const start = (state.page - 1) * state.pageSize;
    return state.filteredRows.slice(start, start + state.pageSize);
  }

  function renderSummary() {
    nodes.summary.innerHTML = SHOWCASE_SUMMARY.map(function (card) {
      return '' +
        '<article class="agent-summary-card" data-tone="' + esc(card.tone) + '">' +
          '<div class="agent-summary-icon">' + esc(card.icon) + '</div>' +
          '<div>' +
            '<div class="agent-summary-label">' + esc(card.title) + '</div>' +
            '<div class="agent-summary-value">' + esc(card.value) + '</div>' +
            '<div class="agent-summary-desc">' + esc(card.desc) + '</div>' +
          '</div>' +
        '</article>';
    }).join('');
  }

  function updateMeta() {
    const totalPages = Math.max(1, Math.ceil(state.filteredRows.length / state.pageSize));
    nodes.meta.innerHTML = '' +
      '<div><strong>' + esc(state.filteredRows.length) + '</strong> 个 Agent 符合当前筛选条件</div>' +
      '<div>视图：' + (state.view === 'card' ? '卡片视图' : '列表视图') + ' · 第 ' + esc(state.page) + ' / ' + esc(totalPages) + ' 页</div>';
    nodes.paginationMeta.textContent = '共 ' + state.filteredRows.length + ' 条';
    nodes.pageIndicator.textContent = String(state.page);
    nodes.selectedCount.textContent = '已选择 ' + state.selectedIds.size + ' 项';
    const pageRows = currentPageRows();
    nodes.selectPage.checked = pageRows.length > 0 && pageRows.every(function (row) {
      return state.selectedIds.has(row.rowId);
    });
  }

  function cardHref(row) {
    const targetId = state.primaryAgentId || row.agentId || '';
    return '/admin/ops-platform/agent-detail?project_id=' +
      encodeURIComponent(state.projectId) +
      '&agent_id=' + encodeURIComponent(targetId) +
      '&preview=' + encodeURIComponent(row.preview);
  }

  function renderCard(row) {
    const selected = state.selectedIds.has(row.rowId);
    const cardClass = [
      'agent-card',
      selected ? 'is-selected' : '',
      row.status === 'WARN' ? 'is-warning' : '',
      row.status === 'OFFLINE' ? 'is-offline' : '',
    ].join(' ').trim();
    return '' +
      '<article class="' + cardClass + '">' +
        '<div class="agent-card-head">' +
          '<label class="agent-card-select">' +
            '<input type="checkbox" data-select-row="' + esc(row.rowId) + '"' + (selected ? ' checked' : '') + '>' +
          '</label>' +
          '<div class="agent-card-main">' +
            '<div class="agent-card-row">' +
              '<div class="agent-card-title-wrap">' +
                '<span class="agent-card-device">⌘</span>' +
                '<div class="agent-card-title">' + esc(row.title) + '</div>' +
                '<span class="agent-state-pill ' + stateClass(row.status) + '">' + esc(row.statusText) + '</span>' +
              '</div>' +
              '<button class="agent-card-more" type="button">⋮</button>' +
            '</div>' +
            '<div class="agent-card-meta">' +
              '<span>IP：' + esc(row.ip) + '</span>' +
              '<span>最后心跳：' + esc(row.heartbeat) + '</span>' +
            '</div>' +
            '<div class="agent-card-metrics">' +
              '<span class="agent-metric-pill" data-tone="cpu">CPU ' + esc(row.cpu) + '%</span>' +
              '<span class="agent-metric-pill" data-tone="mem">MEM ' + esc(row.mem) + '%</span>' +
              '<span class="agent-metric-pill" data-tone="disk">DISK ' + esc(row.disk) + '%</span>' +
            '</div>' +
            '<div class="agent-card-service">' +
              '<strong>服务 ' + esc(row.serviceOnline) + ' / ' + esc(row.serviceTotal) + '</strong>' +
              '<span class="agent-service-text agent-service-text--' + esc(row.serviceTone) + '">' + esc(row.serviceText) + '</span>' +
            '</div>' +
            '<div class="agent-card-actions">' +
              '<a class="agent-card-action" href="' + esc(cardHref(row)) + '">⚙ 查看详情</a>' +
              '<button class="agent-card-action" type="button" data-edit-row="' + esc(row.rowId) + '">✎ 编辑</button>' +
              '<button class="agent-card-action is-primary" type="button" data-probe-row="' + esc(row.rowId) + '">◎ 探测</button>' +
            '</div>' +
          '</div>' +
        '</div>' +
      '</article>';
  }

  function renderCards() {
    const rows = currentPageRows();
    if (!rows.length) {
      nodes.cards.innerHTML = '<div class="agent-empty">当前筛选条件下暂无 Agent</div>';
      return;
    }
    nodes.cards.innerHTML = rows.map(renderCard).join('');
  }

  function renderTable() {
    const rows = currentPageRows();
    if (!rows.length) {
      nodes.list.innerHTML = '<div class="agent-empty">当前筛选条件下暂无 Agent</div>';
      return;
    }
    nodes.list.innerHTML = '' +
      '<div class="agent-table-shell">' +
        '<table class="agent-table">' +
          '<thead><tr><th></th><th>Agent / 设备</th><th>状态</th><th>IP / 最后心跳</th><th>资源</th><th>服务状态</th><th>操作</th></tr></thead>' +
          '<tbody>' +
            rows.map(function (row) {
              const selected = state.selectedIds.has(row.rowId);
              return '' +
                '<tr>' +
                  '<td><input type="checkbox" data-select-row="' + esc(row.rowId) + '"' + (selected ? ' checked' : '') + '></td>' +
                  '<td><strong>' + esc(row.title) + '</strong><div class="table-sub">' + esc(row.description || '设计态主卡') + '</div></td>' +
                  '<td><span class="agent-state-pill ' + stateClass(row.status) + '">' + esc(row.statusText) + '</span></td>' +
                  '<td>' + esc(row.ip) + '<div class="table-sub">' + esc(row.heartbeat) + '</div></td>' +
                  '<td>CPU ' + esc(row.cpu) + '% / MEM ' + esc(row.mem) + '% / DISK ' + esc(row.disk) + '%</td>' +
                  '<td><strong>' + esc(row.serviceOnline) + ' / ' + esc(row.serviceTotal) + '</strong> <span class="agent-service-text agent-service-text--' + esc(row.serviceTone) + '">' + esc(row.serviceText) + '</span></td>' +
                  '<td><div class="agent-table-actions">' +
                    '<a class="agent-card-action" href="' + esc(cardHref(row)) + '">详情</a>' +
                    '<button class="agent-table-action" type="button" data-edit-row="' + esc(row.rowId) + '">编辑</button>' +
                    '<button class="agent-table-action" type="button" data-probe-row="' + esc(row.rowId) + '">探测</button>' +
                  '</div></td>' +
                '</tr>';
            }).join('') +
          '</tbody>' +
        '</table>' +
      '</div>';
  }

  function bindRows(container) {
    container.querySelectorAll('[data-select-row]').forEach(function (node) {
      node.onchange = function () {
        const rowId = String(node.getAttribute('data-select-row') || '');
        if (!rowId) return;
        if (node.checked) state.selectedIds.add(rowId);
        else state.selectedIds.delete(rowId);
        updateMeta();
      };
    });
    container.querySelectorAll('[data-edit-row]').forEach(function (node) {
      node.onclick = function () {
        openEdit(String(node.getAttribute('data-edit-row') || ''));
      };
    });
    container.querySelectorAll('[data-probe-row]').forEach(function (node) {
      node.onclick = function () {
        handleProbe(String(node.getAttribute('data-probe-row') || ''));
      };
    });
  }

  function applyFilters() {
    state.filteredRows = state.rows.filter(matchesFilters);
    const totalPages = Math.max(1, Math.ceil(state.filteredRows.length / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;
  }

  function render() {
    applyFilters();
    updateMeta();
    renderCards();
    renderTable();
    nodes.cards.classList.toggle('is-hidden', state.view !== 'card');
    nodes.list.classList.toggle('is-hidden', state.view !== 'list');
    nodes.cardView.classList.toggle('is-active', state.view === 'card');
    nodes.listView.classList.toggle('is-active', state.view === 'list');
    bindRows(nodes.cards);
    bindRows(nodes.list);
  }

  function rowById(rowId) {
    return state.rows.find(function (row) { return row.rowId === rowId; }) || null;
  }

  function openEdit(rowId) {
    const row = rowById(rowId);
    const live = primaryAgent();
    if (!row || !live) {
      toast('当前环境没有可编辑的真实 Agent', 'error');
      return;
    }
    state.createMode = false;
    nodes.editTitle.textContent = '编辑 Agent';
    nodes.editAgentId.value = String(live.agent_id || '');
    nodes.editDeviceId.value = String(live.device_id || row.preview || '');
    nodes.editHostIp.value = String(live.host_ip || live.host_name || row.ip || '');
    nodes.editDisplayName.value = String(live.display_name || row.title || '');
    nodes.editPort.value = String(live.port || live.remote_game_server_port || '');
    nodes.editRunState.value = '';
    nodes.editDesc.value = String(live.desc || row.description || '');
    nodes.modal.classList.remove('is-hidden');
  }

  function openCreate() {
    state.createMode = true;
    nodes.editTitle.textContent = '新建设备 Agent';
    nodes.editAgentId.value = 'agent-' + Date.now();
    nodes.editDeviceId.value = '';
    nodes.editHostIp.value = '';
    nodes.editDisplayName.value = '';
    nodes.editPort.value = '';
    nodes.editRunState.value = 'ONLINE';
    nodes.editDesc.value = '';
    nodes.modal.classList.remove('is-hidden');
  }

  function closeEdit() {
    nodes.modal.classList.add('is-hidden');
  }

  async function saveEdit() {
    const payload = {
      agent_id: String(nodes.editAgentId.value || '').trim(),
      project_id: state.projectId,
      device_id: String(nodes.editDeviceId.value || '').trim(),
      host_name: String(nodes.editHostIp.value || '').trim(),
      host_ip: String(nodes.editHostIp.value || '').trim(),
      display_name: String(nodes.editDisplayName.value || '').trim(),
      port: Number(nodes.editPort.value || 0),
      remote_game_server_port: Number(nodes.editPort.value || 0),
      run_state: String(nodes.editRunState.value || '').trim(),
      desc: String(nodes.editDesc.value || '').trim(),
      create_if_missing: state.createMode,
      status: 'ONLINE',
    };
    if (!payload.agent_id) {
      toast('Agent ID 不能为空', 'error');
      return;
    }
    if (!window.OpsApi) {
      toast('接口能力未加载', 'error');
      return;
    }
    const response = await window.OpsApi.upsertAgent(payload);
    if (!ensureOk(response, '保存失败')) return;
    closeEdit();
    toast(state.createMode ? '新建设备 Agent 成功' : 'Agent 信息保存成功');
    await loadPage();
  }

  async function handleProbe(rowId) {
    const row = rowById(rowId);
    const live = primaryAgent();
    if (!row || !live || row.source !== 'live-backed' || !window.OpsApi) {
      toast('该卡片为设计态预览，不执行真实探测', 'error');
      return;
    }
    const host = String(live.host_ip || live.host_name || '').trim();
    const response = await window.OpsApi.probeAgent({
      project_id: state.projectId,
      agent_id: String(live.agent_id || ''),
      host_name: host,
      ip: host,
      port: Number(live.port || live.remote_game_server_port || 0),
    });
    if (!ensureOk(response, '探测失败')) return;
    toast('探测请求已提交');
    await loadPage();
  }

  async function batchProbe() {
    if (!state.selectedIds.size) {
      toast('请先选择 Agent', 'error');
      return;
    }
    const liveRowSelected = state.selectedIds.has(state.primaryAgentId);
    if (!liveRowSelected) {
      toast('当前选择中没有真实 Agent，可执行卡片只有首卡', 'error');
      return;
    }
    await handleProbe(state.primaryAgentId);
  }

  async function batchRestart() {
    const live = primaryAgent();
    if (!live || !window.OpsApi) {
      toast('当前没有可重启的真实 Agent', 'error');
      return;
    }
    const services = Array.isArray(live.services) ? live.services : [];
    let count = 0;
    for (const service of services) {
      if (!service.service_id) continue;
      const response = await window.OpsApi.serviceAction({
        project_id: state.projectId,
        service_id: String(service.service_id),
        agent_id: String(service.agent_id || live.agent_id || ''),
        action: 'restart',
      });
      if (response && response.ok) count += 1;
    }
    if (!count) {
      toast('当前 Agent 没有可重启的服务', 'error');
      return;
    }
    toast('已提交 ' + count + ' 个服务的重启请求');
    await loadPage();
  }

  function readFilters() {
    state.filters.status = String(nodes.filterStatus.value || '');
    state.filters.query = String(nodes.filterQuery.value || '');
    state.filters.serviceStatus = String(nodes.filterServiceStatus.value || '');
    state.filters.fresh = String(nodes.filterFresh.value || 'active_120');
    state.page = 1;
  }

  function resetFilters() {
    nodes.filterStatus.value = '';
    nodes.filterQuery.value = '';
    nodes.filterServiceStatus.value = '';
    nodes.filterFresh.value = 'active_120';
    state.filters = {
      status: '',
      query: '',
      serviceStatus: '',
      fresh: 'active_120',
    };
    state.page = 1;
    render();
  }

  function toggleMenu(open) {
    const next = typeof open === 'boolean' ? open : nodes.batchMenu.classList.contains('is-hidden');
    nodes.batchMenu.classList.toggle('is-hidden', !next);
  }

  async function loadPage() {
    renderSummary();
    if (!window.OpsApi) {
      state.liveAgents = [];
      state.rows = buildShowcaseRows();
      state.selectedIds = new Set(state.rows.filter(function (row) { return row.preview === 'remote-device-127001' || row.preview === 'remote-device-127002'; }).map(function (row) { return row.rowId; }));
      render();
      return;
    }

    const response = await window.OpsApi.agents(state.projectId, '', '', 'all', '');
    if (response && response.ok && Array.isArray(response.agents)) {
      state.liveAgents = response.agents;
    } else {
      state.liveAgents = [];
    }
    state.rows = buildShowcaseRows();
    if (!state.selectedIds.size) {
      state.rows.forEach(function (row) {
        if (row.preview === 'remote-device-127001' || row.preview === 'remote-device-127002') state.selectedIds.add(row.rowId);
      });
    }
    render();
  }

  function bindStatic() {
    document.getElementById('btnApplyFilter').onclick = function () {
      readFilters();
      render();
    };
    document.getElementById('btnResetFilter').onclick = resetFilters;
    nodes.cardView.onclick = function () {
      state.view = 'card';
      render();
    };
    nodes.listView.onclick = function () {
      state.view = 'list';
      render();
    };
    document.getElementById('btnPrevPage').onclick = function () {
      state.page = Math.max(1, state.page - 1);
      render();
    };
    document.getElementById('btnNextPage').onclick = function () {
      const totalPages = Math.max(1, Math.ceil(state.filteredRows.length / state.pageSize));
      state.page = Math.min(totalPages, state.page + 1);
      render();
    };
    nodes.pageSize.onchange = function () {
      state.pageSize = Math.max(1, Number(nodes.pageSize.value || 6));
      state.page = 1;
      render();
    };
    nodes.selectPage.onchange = function () {
      currentPageRows().forEach(function (row) {
        if (nodes.selectPage.checked) state.selectedIds.add(row.rowId);
        else state.selectedIds.delete(row.rowId);
      });
      render();
    };

    document.getElementById('btnCreateAgent').onclick = openCreate;
    document.getElementById('btnBatchProbe').onclick = batchProbe;
    document.getElementById('btnBatchRestart').onclick = batchRestart;
    document.getElementById('btnBatchBind').onclick = function () {
      toast('批量绑定服务入口已保留，当前环境未接入批量接口', 'error');
    };
    document.getElementById('btnCleanupExpired').onclick = async function () {
      if (!window.OpsApi) {
        toast('接口能力未加载', 'error');
        return;
      }
      const response = await window.OpsApi.cleanupExpiredAgents({ project_id: state.projectId, ttl_hours: 24 });
      if (!ensureOk(response, '清理失败')) return;
      toast('已清理 ' + (response.deleted_count || 0) + ' 个过期 Agent');
      await loadPage();
    };
    document.getElementById('btnProbeAllAgent').onclick = async function () {
      if (!window.OpsApi) {
        toast('接口能力未加载', 'error');
        return;
      }
      const response = await window.OpsApi.probeAllAgents({ project_id: state.projectId });
      if (!ensureOk(response, '批量探测失败')) return;
      toast('已提交全量探测请求');
      await loadPage();
    };
    document.getElementById('btnProbeRepairAllAgent').onclick = async function () {
      if (!window.OpsApi) {
        toast('接口能力未加载', 'error');
        return;
      }
      const response = await window.OpsApi.probeRepairAgents({ project_id: state.projectId });
      if (!ensureOk(response, '批量修复并探测失败')) return;
      toast('已提交批量修复并探测请求');
      await loadPage();
    };
    document.getElementById('btnBatchMore').onclick = function (event) {
      event.stopPropagation();
      toggleMenu();
    };
    document.getElementById('btnClearSelection').onclick = function () {
      state.selectedIds.clear();
      toggleMenu(false);
      render();
    };
    document.getElementById('btnRefreshNow').onclick = async function () {
      toggleMenu(false);
      await loadPage();
      toast('列表已刷新');
    };

    document.getElementById('btnCloseAgentEdit').onclick = closeEdit;
    document.getElementById('btnCancelAgentEdit').onclick = closeEdit;
    document.getElementById('btnSaveAgentEdit').onclick = saveEdit;
    document.getElementById('btnProbeAgent').onclick = function () {
      handleProbe(state.primaryAgentId);
    };

    document.addEventListener('click', function () {
      toggleMenu(false);
    });
  }

  function startPolling() {
    clearInterval(state.timer);
    state.timer = setInterval(function () {
      loadPage().catch(function () {});
    }, POLL_MS);
  }

  bindStatic();
  loadPage().catch(function (error) {
    console.error('[agent-control] init failed', error);
    toast('Agent 管控中心初始化失败', 'error');
  });
  startPolling();
})();
