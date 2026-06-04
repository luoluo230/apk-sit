(function () {
  const root = document.querySelector('.agent-detail-page');
  if (!root || !window.OpsApi) return;

  const state = {
    projectId: String(root.dataset.projectId || ''),
    agentId: String(root.dataset.agentId || ''),
    detail: null,
    activeTab: 'overview',
  };

  const elements = {
    flash: document.getElementById('detailFlash'),
    loading: document.getElementById('detailLoading'),
    name: document.getElementById('detailAgentName'),
    status: document.getElementById('detailStatusPill'),
    meta: document.getElementById('detailMetaLine'),
    tabs: Array.from(document.querySelectorAll('.agent-tab')),
    panels: Array.from(document.querySelectorAll('.agent-tab-panel')),
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

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[char]));
  }

  function flash(message, tone) {
    elements.flash.textContent = message || '';
    elements.flash.className = `ops-note detail-flash ${tone || ''}`;
    elements.flash.classList.toggle('hidden', !message);
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

  function statusMeta(status) {
    const value = String(status || 'UNKNOWN').toUpperCase();
    if (['ONLINE', 'RUNNING', 'READY', 'SUCCESS'].includes(value)) return { key: 'ok', label: '运行中' };
    if (['PENDING', 'LEASED'].includes(value)) return { key: 'warn', label: '处理中' };
    if (['DEGRADED', 'ERROR', 'FAILED'].includes(value)) return { key: 'warn', label: '异常' };
    if (['OFFLINE', 'TIMEOUT', 'CANCELED', 'STOPPED'].includes(value)) return { key: 'err', label: '离线' };
    return { key: 'info', label: '未知' };
  }

  function metricPercent(metrics, key) {
    const value = metrics && metrics[key];
    if (value == null || value === '') return '--';
    const number = Number(value);
    return Number.isFinite(number) ? `${Math.round(number)}%` : String(value);
  }

  function metricMb(service) {
    const value = Number(service.memory_mb);
    return Number.isFinite(value) ? `${Math.round(value)}MB` : '0MB';
  }

  function serviceSummary(detail) {
    return detail.service_summary || { total: 0, online: 0, abnormal: 0, offline: 0 };
  }

  function renderChart(series, title, color) {
    if (!Array.isArray(series) || !series.length) {
      return `
        <div class="mini-chart">
          <div class="mini-chart-head"><span>${esc(title)}</span><b>--</b></div>
          <div class="mini-chart-empty">暂无历史数据</div>
        </div>
      `;
    }
    const values = series.map((item) => Number(item.value || 0));
    const max = Math.max(1, ...values);
    const points = values.map((value, index) => {
      const x = (index / Math.max(1, values.length - 1)) * 220;
      const y = 76 - ((value / max) * 56);
      return `${x},${y}`;
    }).join(' ');
    const last = values[values.length - 1];
    return `
      <div class="mini-chart">
        <div class="mini-chart-head"><span>${esc(title)}</span><b>${esc(last)}%</b></div>
        <svg viewBox="0 0 220 86" preserveAspectRatio="none">
          <polyline fill="none" stroke="${esc(color)}" stroke-width="3" stroke-linecap="round" points="${esc(points)}"></polyline>
        </svg>
      </div>
    `;
  }

  function renderServiceTable(services, compact) {
    const rows = Array.isArray(services) ? (compact ? services.slice(0, 5) : services) : [];
    if (!rows.length) return '<div class="ops-empty">暂无服务数据</div>';
    return `
      <div class="ops-table-wrap">
        <table class="agent-table agent-detail-table">
          <thead>
            <tr>
              <th>服务名称</th>
              <th>状态</th>
              <th>端口</th>
              <th>启动时间</th>
              <th>CPU</th>
              <th>内存</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((service) => {
              const status = statusMeta(service.status || service.run_state);
              const actionLabel = ['OFFLINE', 'STOPPED'].includes(String(service.status || service.run_state || '').toUpperCase()) ? '启动' : '查看';
              const actionType = actionLabel === '启动' ? 'start' : 'status';
              return `
                <tr>
                  <td><div class="table-title">${esc(service.display_name || service.service_id || '-')}</div><div class="table-sub">${esc(service.service_type || '-')}</div></td>
                  <td><span class="agent-status-pill ${esc(status.key)}"><span class="agent-status-pill-dot ${esc(status.key)}"></span>${esc(status.label)}</span></td>
                  <td>${esc(service.service_port || service.remote_game_server_port || '-')}</td>
                  <td>${esc(service.updated_at || '-')}</td>
                  <td>${esc(metricPercent(service, 'cpu_percent'))}</td>
                  <td>${esc(metricMb(service))}</td>
                  <td class="table-actions">
                    <button class="btn ghost" type="button" data-service-action="${esc(actionType)}" data-service-id="${esc(service.service_id || '')}" data-service-agent-id="${esc(service.agent_id || '')}">${esc(actionLabel)}</button>
                  </td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderJobs(jobs, limit) {
    const rows = Array.isArray(jobs) ? jobs.slice(0, limit || jobs.length) : [];
    if (!rows.length) return '<div class="ops-empty">暂无任务记录</div>';
    return `
      <div class="ops-table-wrap">
        <table class="agent-table agent-detail-job-table">
          <thead><tr><th>任务名称</th><th>状态</th><th>执行时间</th><th>执行人</th></tr></thead>
          <tbody>
            ${rows.map((job) => {
              const status = statusMeta(job.status || '');
              return `<tr><td>${esc(job.action_type || job.job_id || '-')}</td><td><span class="agent-status-pill ${esc(status.key)}"><span class="agent-status-pill-dot ${esc(status.key)}"></span>${esc(status.label)}</span></td><td>${esc(job.updated_at || job.created_at || '-')}</td><td>${esc(job.approver || job.operator || '系统')}</td></tr>`;
            }).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderEvents(events, limit) {
    const rows = Array.isArray(events) ? events.slice(0, limit || events.length) : [];
    if (!rows.length) return '<div class="ops-empty">暂无告警事件</div>';
    return `
      <div class="ops-table-wrap">
        <table class="agent-table agent-detail-event-table">
          <thead><tr><th>级别</th><th>告警内容</th><th>时间</th><th>状态</th></tr></thead>
          <tbody>
            ${rows.map((event) => `<tr><td>${esc(event.severity || 'info')}</td><td>${esc(event.title || event.event || '事件')}</td><td>${esc(event.time || '-')}</td><td>${esc(event.status || '-')}</td></tr>`).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderAudit(audits) {
    const rows = Array.isArray(audits) ? audits : [];
    if (!rows.length) return '<div class="ops-empty">暂无审计日志</div>';
    return `
      <div class="ops-table-wrap">
        <table class="agent-table agent-detail-audit-table">
          <thead><tr><th>动作</th><th>内容</th><th>时间</th><th>操作人</th></tr></thead>
          <tbody>
            ${rows.map((item) => `<tr><td>${esc(item.action || '审计')}</td><td>${esc(item.details || '-')}</td><td>${esc(item.timestamp || '-')}</td><td>${esc(item.user || '-')}</td></tr>`).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderConfigSummary(detail) {
    const agent = detail.agent || {};
    const config = detail.config || {};
    return `
      <div class="detail-config-list">
        <div><span>Agent 配置版本</span><b>${esc(agent.version || '-')}</b></div>
        <div><span>配置文件校验</span><b>通过</b></div>
        <div><span>最后更新时间</span><b>${esc(agent.updated_at || agent.last_seen || '-')}</b></div>
        <div><span>配置来源</span><b>${esc(((config.transport || {}).mode) || 'remote')}</b></div>
        <div><span>描述</span><b>${esc(agent.desc || '-')}</b></div>
      </div>
    `;
  }

  function renderOverview(detail) {
    const agent = detail.agent || {};
    const overview = detail.overview || {};
    const node = detail.node || {};
    const config = detail.config || {};
    const metrics = (agent.metrics && agent.metrics.control) ? agent.metrics.control : (agent.metrics || {});
    const summary = serviceSummary(detail);
    const status = statusMeta(overview.status || agent.effective_status || agent.status);
    const openEvents = Array.isArray(detail.events) ? detail.events.filter((item) => String(item.status || '').toLowerCase() === 'open').length : 0;

    document.getElementById('tab-overview').innerHTML = `
      <div class="agent-detail-summary-grid">
        <article class="agent-detail-mini-card">
          <div class="agent-detail-mini-title">Agent 状态</div>
          <div class="agent-detail-mini-status"><span class="agent-status-dot ${esc(status.key)}"></span>${esc(status.label)}</div>
          <div class="agent-detail-mini-side"><span>健康度</span><b>${esc(overview.healthy_ratio || 0)}%</b></div>
        </article>
        <article class="agent-detail-mini-card">
          <div class="agent-detail-mini-title">系统资源</div>
          <div class="agent-detail-resource-inline">
            <div><span>CPU</span><b>${esc(metricPercent(metrics, 'cpu_percent'))}</b></div>
            <div><span>内存</span><b>${esc(metricPercent(metrics, 'mem_percent'))}</b></div>
            <div><span>磁盘</span><b>${esc(metricPercent(metrics, 'disk_percent'))}</b></div>
          </div>
        </article>
        <article class="agent-detail-mini-card">
          <div class="agent-detail-mini-title">连接信息</div>
          <div class="agent-detail-link-grid">
            <span>网关</span><b>${esc(node.name || node.id || '-')}</b>
            <span>IP</span><b>${esc(agent.host_ip || agent.host_name || '-')}</b>
            <span>端口</span><b>${esc(agent.port || '-')}</b>
          </div>
        </article>
        <article class="agent-detail-mini-card">
          <div class="agent-detail-mini-title">服务健康</div>
          <div class="agent-detail-link-grid">
            <span>在线服务</span><b>${esc(summary.online || 0)}</b>
            <span>异常服务</span><b>${esc(summary.abnormal || 0)}</b>
            <span>服务总数</span><b>${esc(summary.total || 0)}</b>
          </div>
        </article>
        <article class="agent-detail-mini-card">
          <div class="agent-detail-mini-title">告警事件</div>
          <div class="agent-detail-link-grid">
            <span>当前告警</span><b>${esc(overview.current_alerts || 0)}</b>
            <span>未确认</span><b>${esc(openEvents)}</b>
            <span>已恢复</span><b>${esc(overview.resolved_alerts || 0)}</b>
          </div>
        </article>
      </div>

      <div class="agent-detail-main-grid">
        <article class="agent-detail-white-card">
          <div class="agent-detail-section-head"><b>服务与进程</b><a href="javascript:void(0)" data-jump-tab="services">查看更多</a></div>
          ${renderServiceTable(detail.services || [], true)}
        </article>
        <article class="agent-detail-white-card">
          <div class="agent-detail-section-head"><b>监控指标（最近 1 小时）</b><span>1小时</span></div>
          <div class="detail-chart-grid">
            ${renderChart((detail.metrics_history || {}).cpu_percent || [], 'CPU 使用率 (%)', '#2563eb')}
            ${renderChart((detail.metrics_history || {}).mem_percent || [], '内存使用率 (%)', '#16a34a')}
            ${renderChart((detail.metrics_history || {}).disk_percent || [], '磁盘使用率 (%)', '#7c3aed')}
          </div>
        </article>
      </div>

      <div class="agent-detail-bottom-grid">
        <article class="agent-detail-white-card">
          <div class="agent-detail-section-head"><b>近期任务</b><a href="javascript:void(0)" data-jump-tab="jobs">查看更多</a></div>
          ${renderJobs(detail.jobs || [], 5)}
        </article>
        <article class="agent-detail-white-card">
          <div class="agent-detail-section-head"><b>告警事件</b><a href="javascript:void(0)" data-jump-tab="events">查看更多</a></div>
          ${renderEvents(detail.events || [], 5)}
        </article>
        <article class="agent-detail-white-card">
          <div class="agent-detail-section-head"><b>配置信息</b><a href="javascript:void(0)" data-jump-tab="config">管理配置</a></div>
          ${renderConfigSummary(detail)}
        </article>
      </div>

      <div class="agent-detail-system-footer">
        <span>系统信息</span>
        <span>操作系统：CentOS 7.9</span>
        <span>架构：${esc(agent.region || '-')}</span>
        <span>配置来源：${esc(((config.transport || {}).mode) || 'remote')}</span>
        <span>启动时间：${esc(agent.updated_at || '-')}</span>
        <span>最近心跳：${esc(agent.last_seen || '-')}</span>
      </div>
    `;
  }

  function renderDevice(detail) {
    const agent = detail.agent || {};
    const node = detail.node || {};
    document.getElementById('tab-device').innerHTML = `
      <div class="detail-two-col">
        <article class="panel">
          <div class="hd"><b>设备基础信息</b></div>
          <div class="bd detail-kv-grid detail-kv-grid-wide">
            <span>Agent ID</span><b>${esc(agent.agent_id || '-')}</b>
            <span>设备 ID</span><b>${esc(agent.device_id || '-')}</b>
            <span>IP 地址</span><b>${esc(agent.host_ip || agent.host_name || '-')}</b>
            <span>区域 / 可用区</span><b>${esc(agent.region || '-')} / ${esc(agent.zone || '-')}</b>
            <span>机架</span><b>${esc(agent.rack || '-')}</b>
            <span>版本</span><b>${esc(agent.version || '-')}</b>
          </div>
        </article>
        <article class="panel">
          <div class="hd"><b>节点映射信息</b></div>
          <div class="bd detail-kv-grid detail-kv-grid-wide">
            <span>拓扑节点</span><b>${esc(node.id || agent.node_id || '-')}</b>
            <span>节点名称</span><b>${esc(node.name || '-')}</b>
            <span>项目</span><b>${esc(agent.project_id || '-')}</b>
            <span>角色</span><b>${esc(node.role || node.node_category || '-')}</b>
            <span>Ops 地址</span><b>${esc(node.ops_base_url || '-')}</b>
            <span>最近心跳</span><b>${esc(agent.last_seen || '-')}</b>
          </div>
        </article>
      </div>
    `;
  }

  function renderServices(detail) {
    document.getElementById('tab-services').innerHTML = `<article class="panel"><div class="hd"><b>服务与进程</b></div><div class="bd">${renderServiceTable(detail.services || [], false)}</div></article>`;
  }

  function renderMetrics(detail) {
    const history = detail.metrics_history || {};
    document.getElementById('tab-metrics').innerHTML = `
      <div class="agent-detail-white-card agent-metrics-panel">
        <div class="agent-detail-section-head"><b>监控指标（最近 1 小时）</b><span>实时采样</span></div>
        <div class="detail-chart-grid detail-chart-grid-full">
          ${renderChart(history.cpu_percent || [], 'CPU 使用率 (%)', '#2563eb')}
          ${renderChart(history.mem_percent || [], '内存使用率 (%)', '#16a34a')}
          ${renderChart(history.disk_percent || [], '磁盘使用率 (%)', '#7c3aed')}
        </div>
      </div>
    `;
  }

  function renderLogs(detail) {
    const traces = Array.isArray(detail.traces) ? detail.traces : [];
    document.getElementById('tab-logs').innerHTML = traces.length ? `
      <div class="ops-table-wrap">
        <table class="agent-table agent-detail-log-table">
          <thead><tr><th>操作</th><th>内容</th><th>时间</th><th>结果</th></tr></thead>
          <tbody>${traces.map((item) => `<tr><td>${esc(item.action || item.trace_id || '操作')}</td><td>${esc(item.message || '-')}</td><td>${esc(item.time || '-')}</td><td>${esc(item.ok ? '成功' : '失败')}</td></tr>`).join('')}</tbody>
        </table>
      </div>
    ` : '<div class="ops-empty">暂无操作日志</div>';
  }

  function renderConfig(detail) {
    const config = detail.config || {};
    document.getElementById('tab-config').innerHTML = `
      <div class="detail-two-col">
        <article class="panel"><div class="hd"><b>Agent 配置</b></div><div class="bd"><pre class="ops-code">${esc(JSON.stringify({ transport: config.transport || {}, network: config.network || {}, capabilities: config.capabilities || [] }, null, 2))}</pre></div></article>
        <article class="panel"><div class="hd"><b>策略配置</b></div><div class="bd"><pre class="ops-code">${esc(JSON.stringify(config.policy || {}, null, 2))}</pre></div></article>
      </div>
    `;
  }

  function renderAllTabs(detail) {
    renderOverview(detail);
    renderDevice(detail);
    renderServices(detail);
    renderMetrics(detail);
    document.getElementById('tab-jobs').innerHTML = renderJobs(detail.jobs || [], detail.jobs ? detail.jobs.length : 0);
    renderLogs(detail);
    renderConfig(detail);
    document.getElementById('tab-events').innerHTML = renderEvents(detail.events || [], detail.events ? detail.events.length : 0);
    document.getElementById('tab-audit').innerHTML = renderAudit(detail.audits || []);
    bindDynamicActions();
  }

  function switchTab(tab) {
    state.activeTab = tab;
    elements.tabs.forEach((node) => node.classList.toggle('active', node.dataset.tab === tab));
    elements.panels.forEach((node) => node.classList.toggle('active', node.id === `tab-${tab}`));
  }

  function fillEdit(agent) {
    elements.editAgentId.value = String(agent.agent_id || '');
    elements.editDeviceId.value = String(agent.device_id || '');
    elements.editHostIp.value = String(agent.host_ip || agent.host_name || '');
    elements.editDisplayName.value = String(agent.display_name || '');
    elements.editPort.value = String(agent.port || agent.remote_game_server_port || '');
    elements.editRunState.value = '';
    elements.editDesc.value = String(agent.desc || '');
  }

  function probePayload() {
    const agent = (state.detail && state.detail.agent) ? state.detail.agent : {};
    const host = String(agent.host_ip || agent.host_name || '').trim();
    return {
      project_id: state.projectId,
      agent_id: state.agentId,
      host_name: host,
      ip: host,
      port: Number(agent.port || agent.remote_game_server_port || 0),
    };
  }

  async function loadDetail() {
    const response = await window.OpsApi.agentDetail(state.projectId, state.agentId);
    if (!ensureOk(response, 'Agent 详情加载失败')) {
      elements.loading.classList.remove('hidden');
      elements.loading.textContent = 'Agent 详情加载失败';
      return;
    }

    state.detail = response;
    const agent = response.agent || {};
    const status = statusMeta((response.overview || {}).status || agent.effective_status || agent.status);
    elements.name.textContent = agent.display_name || agent.device_id || agent.agent_id || 'Agent 详情';
    elements.status.className = `agent-status-pill ${status.key}`;
    elements.status.innerHTML = `<span class="agent-status-pill-dot ${esc(status.key)}"></span>${esc(status.label)}`;
    elements.meta.textContent = `ID: ${agent.agent_id || '-'} ｜ 分组: ${agent.device_id || '-'} ｜ 环境: ${agent.project_id || '-'} ｜ 版本: ${agent.version || '-'} ｜ 最近心跳: ${agent.last_seen || '-'} ｜ 安装时间: ${agent.updated_at || agent.last_seen || '-'}`;
    elements.loading.classList.add('hidden');
    fillEdit(agent);
    renderAllTabs(response);
    switchTab(state.activeTab);
    flash('', '');
  }

  function bindDynamicActions() {
    document.querySelectorAll('[data-jump-tab]').forEach((node) => {
      node.onclick = () => switchTab(String(node.getAttribute('data-jump-tab') || 'overview'));
    });
    document.querySelectorAll('[data-service-action]').forEach((node) => {
      node.onclick = async () => {
        const action = String(node.getAttribute('data-service-action') || 'status');
        const serviceId = String(node.getAttribute('data-service-id') || '');
        const ownerAgentId = String(node.getAttribute('data-service-agent-id') || state.agentId);
        if (!serviceId) return;
        const response = await window.OpsApi.serviceAction({
          project_id: state.projectId,
          service_id: serviceId,
          agent_id: ownerAgentId,
          action,
        });
        if (!ensureOk(response, '服务操作失败')) return;
        flash(action === 'start' ? '服务启动请求已提交' : '服务状态已刷新', 'success');
        await loadDetail();
      };
    });
  }

  function toggleMenu(open) {
    if (!elements.moreMenu) return;
    const next = typeof open === 'boolean' ? open : elements.moreMenu.classList.contains('hidden');
    elements.moreMenu.classList.toggle('hidden', !next);
  }

  function bindStaticActions() {
    elements.tabs.forEach((node) => {
      node.onclick = () => switchTab(String(node.dataset.tab || 'overview'));
    });

    document.getElementById('detailOpenControl').onclick = () => {
      window.location.href = `/admin/ops-platform/agent-control?project_id=${encodeURIComponent(state.projectId)}`;
    };
    document.getElementById('detailEditBtn').onclick = () => elements.editModal.classList.remove('hidden');
    document.getElementById('detailCloseEdit').onclick = () => elements.editModal.classList.add('hidden');
    document.getElementById('detailCancelEdit').onclick = () => elements.editModal.classList.add('hidden');

    document.getElementById('detailMoreBtn').onclick = (event) => {
      event.stopPropagation();
      toggleMenu();
    };
    document.getElementById('detailMoreProbe').onclick = async () => {
      toggleMenu(false);
      const response = await window.OpsApi.probeAgent(probePayload());
      if (!ensureOk(response, '探测失败')) return;
      flash('探测请求已提交', 'success');
      await loadDetail();
    };
    document.getElementById('detailMoreRefresh').onclick = async () => {
      toggleMenu(false);
      await loadDetail();
    };

    document.getElementById('detailProbeBtn').onclick = async () => {
      const response = await window.OpsApi.probeAgent(probePayload());
      if (!ensureOk(response, '探测失败')) return;
      flash('探测请求已提交', 'success');
      await loadDetail();
    };

    document.getElementById('detailRestartBtn').onclick = async () => {
      const services = state.detail && Array.isArray(state.detail.services) ? state.detail.services : [];
      if (!services.length) return flash('当前 Agent 暂无可重启服务', 'error');
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
      flash(count ? `已提交 ${count} 个服务的重启请求` : '重启请求提交失败', count ? 'success' : 'error');
      await loadDetail();
    };

    document.getElementById('detailSaveEdit').onclick = async () => {
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
      };
      const response = await window.OpsApi.upsertAgent(payload);
      if (!ensureOk(response, '保存失败')) return;
      elements.editModal.classList.add('hidden');
      flash('Agent 信息已保存', 'success');
      await loadDetail();
    };

    document.addEventListener('click', () => toggleMenu(false));
  }

  bindStaticActions();
  loadDetail().catch((error) => {
    console.error('[agent-detail] boot failed', error);
    flash('Agent 详情初始化失败', 'error');
  });
})();
