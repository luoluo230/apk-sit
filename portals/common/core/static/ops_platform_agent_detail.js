(function () {
  const root = document.querySelector('.agent-detail-page');
  if (!root) return;

  const state = {
    projectId: String(root.dataset.projectId || ''),
    agentId: String(root.dataset.agentId || ''),
    preview: new URLSearchParams(window.location.search).get('preview') || 'remote-device-127001',
    liveDetail: null,
    activeTab: 'overview',
  };

  const nodes = {
    flash: document.getElementById('detailFlash'),
    loading: document.getElementById('detailLoading'),
    name: document.getElementById('detailAgentName'),
    status: document.getElementById('detailStatusPill'),
    meta: document.getElementById('detailMetaLine'),
    tabs: Array.from(document.querySelectorAll('.agent-detail-tab')),
    panels: Array.from(document.querySelectorAll('.agent-detail-panel')),
    moreMenu: document.getElementById('detailMoreMenu'),
    editModal: document.getElementById('detailEditModal'),
    editAgentId: document.getElementById('detailEditAgentId'),
    editDeviceId: document.getElementById('detailEditDeviceId'),
    editHostIp: document.getElementById('detailEditHostIp'),
    editDisplayName: document.getElementById('detailEditDisplayName'),
    editPort: document.getElementById('detailEditPort'),
    editRunState: document.getElementById('detailEditRunState'),
    editDesc: document.getElementById('detailEditDesc'),
  };

  const SHOWCASE_DETAIL = {
    'remote-device-127001': {
      name: 'remote-device-127001',
      statusText: '运行中',
      statusClass: 'agent-state-pill--ok',
      metaLine: 'ID: agent-ops-cn-1 ｜ 分组: 华东-游戏服务 ｜ 环境: 生产环境 ｜ 版本: 1.3.2 ｜ 最近心跳: 2 秒前 ｜ 安装时间: 2026-06-01 11:14:15',
      summary: {
        health: '100%',
        cpu: 23,
        mem: 45,
        disk: 67,
        gateway: 'Gateway-01',
        ip: '10.0.0.10',
        port: '15050',
        onlineServices: 12,
        abnormalServices: 0,
        totalServices: 12,
        currentAlerts: 1,
        unackedAlerts: 0,
        recoveredAlerts: 3,
      },
      services: [
        ['Gateway', '运行中', '15050', '2026-06-01 11:14:15', '12%', '128MB', '查看'],
        ['Auth', '运行中', '5501', '2026-06-01 11:14:16', '8%', '96MB', '查看'],
        ['Game', '运行中', '5502', '2026-06-01 11:14:17', '15%', '256MB', '查看'],
        ['Match', '已停止', '5503', '-', '0%', '0MB', '启动'],
        ['Chat', '运行中', '5504', '2026-06-01 11:14:18', '6%', '64MB', '查看'],
      ],
      jobs: [
        ['重启 Game 服务', '成功', '2026-06-06 10:52:20', '运维管理员'],
        ['更新 Agent 配置', '成功', '2026-06-06 10:30:15', '运维管理员'],
        ['执行健康检查', '成功', '2026-06-06 10:25:10', '系统'],
        ['部署新版本 v1.3.2', '成功', '2026-06-06 09:15:30', '运维管理员'],
        ['清理日志文件', '成功', '2026-06-06 08:45:22', '系统'],
      ],
      events: [
        ['警告', '磁盘使用率超过 80%', '2026-06-06 10:48:15', '已恢复'],
        ['严重', 'Game 服务响应超时', '2026-06-06 10:35:20', '进行中'],
        ['提示', '配置文件已更新', '2026-06-06 09:20:10', '已恢复'],
        ['警告', '内存使用率超过 70%', '2026-06-06 08:15:30', '已恢复'],
        ['提示', 'Agent 版本检查完成', '2026-06-06 07:30:20', '已恢复'],
      ],
      config: [
        ['Agent 配置版本', 'v1.3.2'],
        ['配置文件校验', '通过'],
        ['最后更新时间', '2026-06-06 10:30:15'],
        ['配置来源', '手动更新'],
        ['描述', '-'],
      ],
      footer: ['系统信息', '操作系统：CentOS 7.9', '架构：x86_64', '内核版本：3.10.0-1160.el7.x86_64', '启动时间：2026-06-01 11:14:15', '运行时长：5 天 2 小时 45 分钟'],
      charts: {
        cpu: [18, 20, 18, 19, 17, 15, 18, 16, 19, 17, 20, 18, 18, 17, 19, 18, 17, 19],
        mem: [27, 28, 27, 29, 30, 28, 29, 31, 30, 32, 29, 31, 30, 33, 32, 31, 33, 34],
        disk: [35, 37, 34, 33, 36, 32, 31, 36, 39, 35, 38, 41, 37, 42, 40, 41, 43, 45],
      },
    },
    'remote-device-127002': {
      name: 'remote-device-127002',
      statusText: '运行中',
      statusClass: 'agent-state-pill--ok',
      metaLine: 'ID: agent-ops-cn-2 ｜ 分组: 华东-游戏服务 ｜ 环境: 生产环境 ｜ 版本: 1.3.2 ｜ 最近心跳: 5 秒前 ｜ 安装时间: 2026-06-01 11:13:02',
      summary: { health: '92%', cpu: 25, mem: 56, disk: 48, gateway: 'Gateway-02', ip: '10.0.0.11', port: '15051', onlineServices: 2, abnormalServices: 1, totalServices: 3, currentAlerts: 1, unackedAlerts: 1, recoveredAlerts: 0 },
      services: [['Gateway', '运行中', '15051', '2026-06-01 11:13:02', '10%', '120MB', '查看'], ['Game', '异常', '5502', '2026-06-01 11:13:08', '22%', '224MB', '查看'], ['Chat', '运行中', '5504', '2026-06-01 11:13:09', '8%', '72MB', '查看']],
      jobs: [['重新绑定服务', '成功', '2026-06-06 11:12:20', '运维管理员']],
      events: [['警告', 'Game 服务异常', '2026-06-06 11:12:15', '进行中']],
      config: [['Agent 配置版本', 'v1.3.2'], ['配置文件校验', '通过'], ['最后更新时间', '2026-06-06 11:10:15'], ['配置来源', '策略同步'], ['描述', '主力接入机']],
      footer: ['系统信息', '操作系统：CentOS 7.9', '架构：x86_64', '内核版本：3.10.0-1160.el7.x86_64', '启动时间：2026-06-01 11:13:02', '运行时长：5 天 2 小时 32 分钟'],
      charts: { cpu: [14, 16, 18, 17, 19, 21, 20, 19], mem: [25, 27, 28, 29, 31, 30, 32, 33], disk: [18, 19, 21, 20, 22, 25, 24, 26] },
    },
  };

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (char) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char];
    });
  }

  function flash(message, tone) {
    if (!message) {
      nodes.flash.className = 'agent-inline-note is-hidden';
      nodes.flash.textContent = '';
      return;
    }
    nodes.flash.className = 'agent-inline-note ' + (tone === 'error' ? 'is-error' : 'is-success');
    nodes.flash.textContent = message;
  }

  function ensureOk(response, fallback) {
    if (response && (response.error_code === 'OPS_AUTH_REQUIRED' || response.error === 'auth_redirect')) {
      window.location.href = '/login';
      return false;
    }
    if (!response || !response.ok) {
      flash((response && (response.message || response.error)) || fallback || '请求失败', 'error');
      return false;
    }
    return true;
  }

  function pickPreview() {
    return SHOWCASE_DETAIL[state.preview] || SHOWCASE_DETAIL['remote-device-127001'];
  }

  function chartMarkup(title, color, values, shownValue) {
    const points = values.map(function (value, index) {
      const x = values.length === 1 ? 0 : (index / (values.length - 1)) * 240;
      const y = 90 - (Math.max(0, Math.min(100, value)) * 0.72);
      return x + ',' + y;
    }).join(' ');
    return '' +
      '<div class="agent-chart">' +
        '<div class="agent-chart-head"><span>' + esc(title) + '</span><strong>' + esc(shownValue) + '%</strong></div>' +
        '<div class="agent-chart-scale"><span>100</span><span>50</span><span>0</span></div>' +
        '<svg viewBox="0 0 240 100" preserveAspectRatio="none">' +
          '<polyline points="' + esc(points) + '" fill="none" stroke="' + esc(color) + '" stroke-width="3" stroke-linecap="round"></polyline>' +
        '</svg>' +
        '<div class="agent-chart-scale"><span>10:30</span><span>11:00</span><span>11:30</span></div>' +
      '</div>';
  }

  function tableStatusClass(text) {
    if (text === '成功' || text === '运行中' || text === '已恢复' || text === '在线') return 'agent-state-pill--ok';
    if (text === '警告' || text === '异常' || text === '进行中') return 'agent-state-pill--warn';
    if (text === '严重' || text === '离线' || text === '已停止') return 'agent-state-pill--offline';
    return 'agent-state-pill--info';
  }

  function renderStatusPill(text) {
    return '<span class="agent-state-pill ' + tableStatusClass(text) + '">' + esc(text) + '</span>';
  }

  function card(title, body, action) {
    return '' +
      '<article class="agent-detail-white-card">' +
        '<div class="agent-detail-card-head"><strong>' + esc(title) + '</strong>' + (action || '') + '</div>' +
        '<div class="agent-detail-card-body">' + body + '</div>' +
      '</article>';
  }

  function renderOverview(preview) {
    const summary = preview.summary;
    document.getElementById('tab-overview').innerHTML = '' +
      '<div class="agent-detail-summary-grid">' +
        '<article class="agent-detail-summary-card">' +
          '<div class="agent-detail-summary-title">Agent 状态</div>' +
          '<div class="agent-detail-summary-status">运行中</div>' +
          '<div class="agent-detail-summary-foot"><span>健康度</span><strong>' + esc(summary.health) + '</strong></div>' +
        '</article>' +
        '<article class="agent-detail-summary-card">' +
          '<div class="agent-detail-summary-title">系统资源</div>' +
          '<div class="agent-detail-resource-grid">' +
            '<div><span>CPU</span><strong>' + esc(summary.cpu) + '%</strong></div>' +
            '<div><span>内存</span><strong>' + esc(summary.mem) + '%</strong></div>' +
            '<div><span>磁盘</span><strong>' + esc(summary.disk) + '%</strong></div>' +
          '</div>' +
        '</article>' +
        '<article class="agent-detail-summary-card">' +
          '<div class="agent-detail-summary-title">连接信息</div>' +
          '<div class="agent-detail-kv"><span>网关</span><strong>' + esc(summary.gateway) + '</strong><span>IP</span><strong>' + esc(summary.ip) + '</strong><span>端口</span><strong>' + esc(summary.port) + '</strong></div>' +
        '</article>' +
        '<article class="agent-detail-summary-card">' +
          '<div class="agent-detail-summary-title">服务健康</div>' +
          '<div class="agent-detail-kv"><span>在线服务</span><strong>' + esc(summary.onlineServices) + '</strong><span>异常服务</span><strong>' + esc(summary.abnormalServices) + '</strong><span>服务总数</span><strong>' + esc(summary.totalServices) + '</strong></div>' +
        '</article>' +
        '<article class="agent-detail-summary-card">' +
          '<div class="agent-detail-summary-title">告警事件</div>' +
          '<div class="agent-detail-kv"><span>当前告警</span><strong>' + esc(summary.currentAlerts) + '</strong><span>未确认</span><strong>' + esc(summary.unackedAlerts) + '</strong><span>已恢复</span><strong>' + esc(summary.recoveredAlerts) + '</strong></div>' +
        '</article>' +
      '</div>' +
      '<div class="agent-detail-main-grid">' +
        card('服务与进程', serviceTable(preview.services), '<a href="javascript:void(0)" data-jump-tab="services">查看更多</a>') +
        card('监控指标（最近 1 小时）', '' +
          '<div class="agent-chart-grid">' +
            chartMarkup('CPU 使用率 (%)', '#2f6bff', preview.charts.cpu, preview.summary.cpu) +
            chartMarkup('内存使用率 (%)', '#16c47f', preview.charts.mem, preview.summary.mem) +
            chartMarkup('磁盘使用率 (%)', '#8e4ef8', preview.charts.disk, preview.summary.disk) +
          '</div>', '<span>1小时</span>') +
      '</div>' +
      '<div class="agent-detail-bottom-grid">' +
        card('近期任务', simpleTable(['任务名称', '状态', '执行时间', '执行人'], preview.jobs, [0, 1, 2, 3]), '<a href="javascript:void(0)" data-jump-tab="jobs">查看更多</a>') +
        card('告警事件', simpleTable(['级别', '告警内容', '时间', '状态'], preview.events, [0, 1, 2, 3]), '<a href="javascript:void(0)" data-jump-tab="events">查看更多</a>') +
        card('配置信息', configList(preview.config), '<a href="javascript:void(0)" data-jump-tab="config">管理配置</a>') +
      '</div>' +
      '<div class="agent-system-footer">' + preview.footer.map(function (item, index) {
        return index === 0 ? '<strong>' + esc(item) + '</strong>' : '<span>' + esc(item) + '</span>';
      }).join('') + '</div>';
  }

  function serviceTable(rows) {
    return simpleTable(['服务名称', '状态', '端口', '启动时间', 'CPU', '内存', '操作'], rows, [0, 1, 2, 3, 4, 5, 6], 'service');
  }

  function simpleTable(headers, rows, indexes, mode) {
    return '' +
      '<table class="agent-table">' +
        '<thead><tr>' + headers.map(function (header) { return '<th>' + esc(header) + '</th>'; }).join('') + '</tr></thead>' +
        '<tbody>' + rows.map(function (row) {
          return '<tr>' + indexes.map(function (index) {
            if (index === 1 && mode !== 'config') return '<td>' + renderStatusPill(row[index]) + '</td>';
            if (index === 0 && mode === 'service') return '<td><strong>' + esc(row[index]) + '</strong></td>';
            if (index === 6 && mode === 'service') return '<td><button class="agent-table-action" type="button" data-service-demo="' + esc(row[0]) + '">' + esc(row[index]) + '</button></td>';
            if (index === 3 && mode !== 'service' && headers[3] === '状态') return '<td>' + renderStatusPill(row[index]) + '</td>';
            return '<td>' + esc(row[index]) + '</td>';
          }).join('') + '</tr>';
        }).join('') + '</tbody>' +
      '</table>';
  }

  function configList(rows) {
    return '<div class="agent-config-list">' + rows.map(function (row) {
      return '<span>' + esc(row[0]) + '</span><strong>' + esc(row[1]) + '</strong>';
    }).join('') + '</div>';
  }

  function renderDevice(preview) {
    document.getElementById('tab-device').innerHTML = '' +
      '<div class="agent-detail-two-col">' +
        '<article class="agent-detail-info-card">' +
          '<div class="agent-detail-card-head"><strong>设备基础信息</strong></div>' +
          '<div class="agent-detail-info-grid">' +
            '<span>Agent ID</span><strong>' + esc((state.liveDetail && state.liveDetail.agent && state.liveDetail.agent.agent_id) || 'agent-ops-cn-1') + '</strong>' +
            '<span>设备 ID</span><strong>' + esc(preview.name) + '</strong>' +
            '<span>IP 地址</span><strong>' + esc(preview.summary.ip) + '</strong>' +
            '<span>所属分组</span><strong>华东-游戏服务</strong>' +
            '<span>区域 / 可用区</span><strong>上海 / zone-a</strong>' +
            '<span>版本</span><strong>v1.3.2</strong>' +
          '</div>' +
        '</article>' +
        '<article class="agent-detail-info-card">' +
          '<div class="agent-detail-card-head"><strong>节点映射信息</strong></div>' +
          '<div class="agent-detail-info-grid">' +
            '<span>拓扑节点</span><strong>gateway-cn-1</strong>' +
            '<span>节点名称</span><strong>' + esc(preview.summary.gateway) + '</strong>' +
            '<span>项目</span><strong>' + esc(state.projectId || 'GomeKu') + '</strong>' +
            '<span>角色</span><strong>Gateway</strong>' +
            '<span>Ops 地址</span><strong>http://10.0.0.10:5003</strong>' +
            '<span>最近心跳</span><strong>2 秒前</strong>' +
          '</div>' +
        '</article>' +
      '</div>';
  }

  function renderServices(preview) {
    document.getElementById('tab-services').innerHTML = card('服务与进程', serviceTable(preview.services), '');
  }

  function renderMetrics(preview) {
    document.getElementById('tab-metrics').innerHTML = card('监控指标（最近 1 小时）', '' +
      '<div class="agent-chart-grid">' +
        chartMarkup('CPU 使用率 (%)', '#2f6bff', preview.charts.cpu, preview.summary.cpu) +
        chartMarkup('内存使用率 (%)', '#16c47f', preview.charts.mem, preview.summary.mem) +
        chartMarkup('磁盘使用率 (%)', '#8e4ef8', preview.charts.disk, preview.summary.disk) +
      '</div>', '<span>实时采样</span>');
  }

  function renderJobs(preview) {
    document.getElementById('tab-jobs').innerHTML = card('任务历史', simpleTable(['任务名称', '状态', '执行时间', '执行人'], preview.jobs, [0, 1, 2, 3]), '');
  }

  function renderLogs(preview) {
    const logs = (state.liveDetail && state.liveDetail.audits || []).slice(0, 8).map(function (item) {
      return [item.action || '审计操作', item.details || '-', item.timestamp || '-', item.user || 'admin'];
    });
    const rows = logs.length ? logs : [['配置更新', '同步 Agent 配置到目标节点', '2026-06-06 10:30:15', '运维管理员']];
    document.getElementById('tab-logs').innerHTML = card('操作日志', simpleTable(['操作', '内容', '时间', '操作人'], rows, [0, 1, 2, 3]), '');
  }

  function renderConfig(preview) {
    const live = state.liveDetail && state.liveDetail.agent ? state.liveDetail.agent : {};
    const payload = {
      transport: (state.liveDetail && state.liveDetail.config && state.liveDetail.config.transport) || { mode: 'remote', local_auth_mode: 'token' },
      agent: {
        agent_id: live.agent_id || state.agentId,
        device_id: live.device_id || preview.name,
        host_ip: live.host_ip || preview.summary.ip,
      },
    };
    document.getElementById('tab-config').innerHTML = '' +
      '<div class="agent-detail-two-col">' +
        '<article class="agent-detail-info-card">' +
          '<div class="agent-detail-card-head"><strong>设计态配置信息</strong></div>' +
          '<div class="agent-detail-card-body">' + configList(preview.config) + '</div>' +
        '</article>' +
        '<article class="agent-detail-info-card">' +
          '<div class="agent-detail-card-head"><strong>当前接口返回</strong></div>' +
          '<pre class="agent-detail-code">' + esc(JSON.stringify(payload, null, 2)) + '</pre>' +
        '</article>' +
      '</div>';
  }

  function renderEvents(preview) {
    document.getElementById('tab-events').innerHTML = card('告警事件', simpleTable(['级别', '告警内容', '时间', '状态'], preview.events, [0, 1, 2, 3]), '');
  }

  function renderAudit() {
    const rows = (state.liveDetail && state.liveDetail.audits || []).slice(0, 12).map(function (item) {
      return [item.action || '审计操作', item.details || '-', item.timestamp || '-', item.user || 'admin'];
    });
    const data = rows.length ? rows : [['配置变更', '当前环境暂无更多审计记录', '2026-06-06 10:30:15', '运维管理员']];
    document.getElementById('tab-audit').innerHTML = card('审计日志', simpleTable(['动作', '内容', '时间', '操作人'], data, [0, 1, 2, 3]), '');
  }

  function renderAll(preview) {
    nodes.name.textContent = preview.name;
    nodes.status.className = 'agent-state-pill ' + preview.statusClass;
    nodes.status.textContent = preview.statusText;
    nodes.meta.textContent = preview.metaLine;
    renderOverview(preview);
    renderDevice(preview);
    renderServices(preview);
    renderMetrics(preview);
    renderJobs(preview);
    renderLogs(preview);
    renderConfig(preview);
    renderEvents(preview);
    renderAudit();
    bindDynamic();
  }

  function switchTab(tab) {
    state.activeTab = tab;
    nodes.tabs.forEach(function (node) {
      node.classList.toggle('is-active', node.dataset.tab === tab);
    });
    nodes.panels.forEach(function (panel) {
      panel.classList.toggle('is-active', panel.id === 'tab-' + tab);
    });
  }

  function fillEdit() {
    const live = state.liveDetail && state.liveDetail.agent ? state.liveDetail.agent : {};
    const preview = pickPreview();
    nodes.editAgentId.value = String(live.agent_id || state.agentId || '');
    nodes.editDeviceId.value = String(live.device_id || preview.name || '');
    nodes.editHostIp.value = String(live.host_ip || live.host_name || preview.summary.ip || '');
    nodes.editDisplayName.value = String(live.display_name || preview.name || '');
    nodes.editPort.value = String(live.port || live.remote_game_server_port || preview.summary.port || '');
    nodes.editRunState.value = '';
    nodes.editDesc.value = String(live.desc || '设计态详情页');
  }

  function toggleMenu(open) {
    const next = typeof open === 'boolean' ? open : nodes.moreMenu.classList.contains('is-hidden');
    nodes.moreMenu.classList.toggle('is-hidden', !next);
  }

  async function probeLive() {
    const live = state.liveDetail && state.liveDetail.agent ? state.liveDetail.agent : null;
    if (!live || !window.OpsApi) {
      flash('当前没有可探测的真实 Agent', 'error');
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
    flash('探测请求已提交', 'success');
    await load();
  }

  async function restartLive() {
    const services = state.liveDetail && Array.isArray(state.liveDetail.services) ? state.liveDetail.services : [];
    if (!services.length || !window.OpsApi) {
      flash('当前没有可重启的真实服务', 'error');
      return;
    }
    let count = 0;
    for (const service of services) {
      if (!service.service_id) continue;
      const response = await window.OpsApi.serviceAction({
        project_id: state.projectId,
        service_id: String(service.service_id),
        agent_id: String(service.agent_id || state.agentId),
        action: 'restart',
      });
      if (response && response.ok) count += 1;
    }
    flash(count ? ('已提交 ' + count + ' 个服务的重启请求') : '重启请求提交失败', count ? 'success' : 'error');
    if (count) await load();
  }

  async function saveEdit() {
    if (!window.OpsApi) {
      flash('接口能力未加载', 'error');
      return;
    }
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
    };
    const response = await window.OpsApi.upsertAgent(payload);
    if (!ensureOk(response, '保存失败')) return;
    nodes.editModal.classList.add('is-hidden');
    flash('Agent 信息已保存', 'success');
    await load();
  }

  async function load() {
    const preview = pickPreview();
    if (window.OpsApi && state.agentId) {
      const response = await window.OpsApi.agentDetail(state.projectId, state.agentId);
      if (response && response.ok) {
        state.liveDetail = response;
      } else {
        state.liveDetail = null;
      }
    }
    nodes.loading.classList.add('is-hidden');
    renderAll(preview);
    fillEdit();
    switchTab(state.activeTab);
  }

  function bindDynamic() {
    document.querySelectorAll('[data-jump-tab]').forEach(function (node) {
      node.onclick = function () {
        switchTab(String(node.getAttribute('data-jump-tab') || 'overview'));
      };
    });
    document.querySelectorAll('[data-service-demo]').forEach(function (node) {
      node.onclick = function () {
        flash('当前为设计态服务表，真实操作仍绑定当前 Agent', 'success');
      };
    });
  }

  function bindStatic() {
    nodes.tabs.forEach(function (node) {
      node.onclick = function () {
        switchTab(String(node.dataset.tab || 'overview'));
      };
    });

    document.getElementById('detailOpenControl').onclick = function () {
      window.location.href = '/admin/ops-platform/agent-control?project_id=' + encodeURIComponent(state.projectId);
    };
    document.getElementById('detailEditBtn').onclick = function () {
      nodes.editModal.classList.remove('is-hidden');
    };
    document.getElementById('detailCloseEdit').onclick = function () {
      nodes.editModal.classList.add('is-hidden');
    };
    document.getElementById('detailCancelEdit').onclick = function () {
      nodes.editModal.classList.add('is-hidden');
    };

    document.getElementById('detailMoreBtn').onclick = function (event) {
      event.stopPropagation();
      toggleMenu();
    };
    document.getElementById('detailMoreProbe').onclick = async function () {
      toggleMenu(false);
      await probeLive();
    };
    document.getElementById('detailMoreRefresh').onclick = async function () {
      toggleMenu(false);
      await load();
      flash('详情已刷新', 'success');
    };
    document.getElementById('detailProbeBtn').onclick = probeLive;
    document.getElementById('detailRestartBtn').onclick = restartLive;
    document.getElementById('detailSaveEdit').onclick = saveEdit;

    document.addEventListener('click', function () {
      toggleMenu(false);
    });
  }

  bindStatic();
  load().catch(function (error) {
    console.error('[agent-detail] init failed', error);
    flash('Agent 详情初始化失败', 'error');
    nodes.loading.classList.add('is-hidden');
  });
})();
