(() => {
  const root = document.querySelector('.build-center');
  if (!root) return;

  const projectId = root.dataset.projectId;
  const canEdit = root.dataset.canEdit === 'true';
  const pageQuery = new URLSearchParams(location.search);
  const scopeVersionId = (pageQuery.get('version_id') || root.dataset.scopeVersionId || '').trim();
  const scopeEnvKey = (pageQuery.get('env_key') || root.dataset.scopeEnvKey || '').trim();
  const scopePlatform = (pageQuery.get('platform') || root.dataset.scopePlatform || '').trim().toLowerCase();
  const scopeVersionName = (pageQuery.get('version_name') || root.dataset.scopeVersionName || '').trim();
  const scopeVersionCode = (pageQuery.get('version_code') || root.dataset.scopeVersionCode || '').trim();
  const scopeChannelId = (pageQuery.get('channel_id') || root.dataset.scopeChannelId || '').trim();
  const scopeBuildNumber = (pageQuery.get('build_number') || '').trim();
  const isScoped = pageQuery.get('scoped') === '1' || scopeVersionId || scopeEnvKey;

  const envLabels = {
    development: '开发环境',
    testing: '测试环境',
    staging: '预发环境',
    production: '生产环境',
  };
  const platformLabels = { android: 'Android', ios: 'iOS' };

  const ui = {
    rows: root.querySelector('[data-build-rows]'),
    state: root.querySelector('[data-state]'),
    tableWrap: root.querySelector('[data-table-wrap]'),
    artifactRows: root.querySelector('[data-artifact-rows]'),
    artifactTabs: root.querySelector('[data-artifact-tabs]'),
    search: root.querySelector('[data-search]'),
    status: root.querySelector('[data-status]'),
    platform: root.querySelector('[data-platform]'),
    dateFrom: root.querySelector('[data-date-from]'),
    dateTo: root.querySelector('[data-date-to]'),
    artifactType: root.querySelector('[data-artifact-type]'),
    pageSize: root.querySelector('[data-page-size]'),
    pageText: root.querySelector('[data-page-text]'),
    resultCount: root.querySelector('[data-result-count]'),
    prev: root.querySelector('[data-prev]'),
    next: root.querySelector('[data-next]'),
    checkAll: root.querySelector('[data-check-all]'),
    batchDelete: root.querySelector('[data-batch-delete]'),
    current: root.querySelector('[data-current]'),
    currentEmpty: root.querySelector('[data-current-empty]'),
    failurePanel: root.querySelector('[data-failure-panel]'),
    failure: root.querySelector('[data-failure]'),
    detail: root.querySelector('[data-detail]'),
    downloadLog: root.querySelector('[data-download-log]'),
    installApk: root.querySelector('[data-install-apk]'),
    console: root.querySelector('[data-console]'),
    deleteCurrent: root.querySelector('[data-delete-current]'),
  };

  let records = [];
  let filtered = [];
  let selected = null;
  let page = 1;
  let pendingDelete = [];
  let artifactView = 'latest';

  const icon = (name) => `/static/project_ui/svg/${name}.svg`;
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[c]));
  const dateText = (value) => (value ? String(value).replace('T', ' ').slice(0, 19) : '-');
  const rowDate = (row) => String(row.started_at || row.created_at || '').slice(0, 10);
  const statusKey = (item) => (item.building ? 'building' : String(item.result || 'UNKNOWN').toUpperCase());
  const statusText = (item) => ({
    building: '进行中',
    SUCCESS: '成功',
    FAILURE: '失败',
    ABORTED: '已取消',
    UNSTABLE: '部分成功',
    UNKNOWN: '未知',
    '': '未知',
  }[statusKey(item)] || statusKey(item));
  const statusClass = (item) => ({
    building: 'building',
    SUCCESS: 'success',
    FAILURE: 'failure',
    ABORTED: 'aborted',
    UNSTABLE: 'building',
    UNKNOWN: 'unknown',
    '': 'unknown',
  }[statusKey(item)] || 'unknown');
  const statusBadge = (item) => `<span class="build-status ${statusClass(item)}">${statusText(item)}</span>`;
  const rowStatusClass = (item) => {
    const key = statusKey(item);
    if (key === 'SUCCESS') return 'row-success';
    if (key === 'FAILURE') return 'row-failure';
    if (key === 'building') return 'row-building';
    return 'row-neutral';
  };

  const toast = (message) => {
    const el = document.querySelector('[data-toast]');
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
    clearTimeout(el._timer);
    el._timer = setTimeout(() => { el.hidden = true; }, 2600);
  };

  const hasArtifact = (row) => {
    const dl = row.apk_download && typeof row.apk_download === 'object' ? row.apk_download : {};
    const bn = String(row.build_number || row.number || '');
    const matchBuild = dl.build_number && String(dl.build_number) === bn;
    return row.apk_status === 'found'
      || matchBuild
      || Boolean(dl.public_download_url || dl.local_download_url || dl.oss_download_url);
  };

  const isMissingArtifact = (row) => statusKey(row) === 'SUCCESS' && !hasArtifact(row);

  const collectArtifacts = (sourceRecords) => {
    const out = [];
    sourceRecords.forEach((row) => {
      const dl = row.apk_download && typeof row.apk_download === 'object' ? row.apk_download : {};
      const url = dl.public_download_url || dl.local_download_url || dl.oss_download_url || '';
      const buildNumber = row.build_number || row.number || '-';
      const version = `${row.version_name || '-'} / ${row.version_code || '-'}`;
      if (hasArtifact(row)) {
        out.push({
          name: dl.filename || row.apk_name || `build-${buildNumber}.apk`,
          type: 'apk',
          buildNumber,
          version,
          sha256: dl.sha256 || row.apk_sha256 || row.sha256 || '-',
          url,
        });
      }
      if (isMissingArtifact(row)) {
        out.push({
          name: '缺失产物',
          type: 'missing',
          buildNumber,
          version,
          sha256: '-',
          url: '',
        });
      }
    });
    return out;
  };

  const renderArtifacts = () => {
    if (!ui.artifactRows) return;
    let items = collectArtifacts(records);
    if (artifactView === 'latest') {
      const seen = new Set();
      items = items.filter((item) => {
        const key = `${item.type}:${item.buildNumber}:${item.name}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }).slice(0, 40);
    } else if (artifactView === 'by-type') {
      items = [...items].sort((a, b) => String(a.type).localeCompare(String(b.type)));
    } else {
      items = [...items].sort((a, b) => String(b.buildNumber).localeCompare(String(a.buildNumber)));
    }
    ui.artifactRows.innerHTML = items.length
      ? items.map((item) => `<tr><td>${esc(item.name)}</td><td>${esc(item.type)}</td><td>${esc(item.buildNumber)}</td><td>${esc(item.version)}</td><td>${esc(item.sha256)}</td><td>${item.url ? `<a href="${esc(item.url)}" target="_blank" rel="noopener">下载</a>` : '-'}</td></tr>`).join('')
      : '<tr><td colspan="6">暂无产物记录</td></tr>';
  };

  const applyScopeUi = () => {
    if (!isScoped) return;
    const subtitle = document.getElementById('buildPageSubtitle');
    if (subtitle) subtitle.textContent = '仅展示当前交付范围内的构建记录，不混入其他环境或平台。';
    const panelDesc = document.querySelector('.build-table-panel .build-panel-title p');
    if (panelDesc) panelDesc.textContent = '点击记录查看详情，成功构建可在操作列下载产物。';
    if (scopePlatform && ui.platform) {
      const wanted = scopePlatform === 'android' ? 'Android' : scopePlatform === 'ios' ? 'iOS' : scopePlatform;
      ui.platform.value = wanted;
      ui.platform.disabled = true;
    }
  };

  const matchesScope = (row) => {
    if (!isScoped) return true;
    if (scopeVersionId && String(row.version_id || '') !== scopeVersionId) return false;
    if (scopeEnvKey && String(row.env_key || '') !== scopeEnvKey) return false;
    if (scopePlatform && String(row.platform || '').toLowerCase() !== scopePlatform) return false;
    if (scopeVersionName && String(row.version_name || '') !== scopeVersionName) return false;
    if (scopeVersionCode && String(row.version_code || '') !== scopeVersionCode) return false;
    if (scopeChannelId && String(row.channel_id || '') !== scopeChannelId) return false;
    return true;
  };

  function flatten(groups) {
    const output = [];
    (groups || []).forEach((group) => (group.version_codes || []).forEach((vc) => (vc.builds || []).forEach((build) => output.push({
      ...build,
      version_name: build.version_name || group.version_name || '',
      version_code: build.version_code || vc.version_code || '',
      version_id: build.version_id || vc.version_id || '',
      channel_id: vc.channel_id || '',
      channel_name: vc.channel_name || '',
      env_key: vc.env_key || '',
      platform: vc.platform || '',
      apk_status: vc.apk_status || '',
      apk_download: vc.apk_download || {},
    }))));
    return output.sort((a, b) => Number(b.build_number || b.number || 0) - Number(a.build_number || a.number || 0));
  }

  function setKpis() {
    const todayStr = new Date().toISOString().slice(0, 10);
    const todayCount = records.filter((row) => rowDate(row) === todayStr).length;
    const successCount = records.filter((row) => statusKey(row) === 'SUCCESS').length;
    const artifactCount = records.filter(hasArtifact).length;
    const missingCount = records.filter(isMissingArtifact).length;
    const staleCount = records.filter((row) => {
      const key = statusKey(row);
      return key === 'FAILURE' || key === 'ABORTED';
    }).length;
    const rate = records.length ? `${Math.round((successCount / records.length) * 100)}%` : '--';

    const set = (name, value) => {
      const el = root.querySelector(`[data-kpi="${name}"]`);
      if (el) el.textContent = value;
    };
    set('today', todayCount);
    set('rate', rate);
    set('artifacts', artifactCount);
    set('missing', missingCount);
    set('stale', staleCount);

    const note = root.querySelector('[data-kpi-note="success"]');
    if (note) note.textContent = records.length ? `${successCount} 次成功` : '等待加载';
  }

  function applyFilters() {
    const keyword = (ui.search?.value || '').trim().toLowerCase();
    const wantedStatus = ui.status?.value || '';
    const wantedPlatform = ui.platform?.value || '';
    const dateFrom = ui.dateFrom?.value || '';
    const dateTo = ui.dateTo?.value || '';
    const wantedArtifactType = ui.artifactType?.value || '';

    filtered = records.filter((row) => {
      if (!matchesScope(row)) return false;
      const haystack = [
        row.build_number,
        row.number,
        row.version_name,
        row.version_code,
        row.triggered_by,
        row.instance_id,
        row.channel_id,
        row.channel_name,
        row.env_key,
        row.platform,
      ].join(' ').toLowerCase();
      if (keyword && !haystack.includes(keyword)) return false;
      if (wantedStatus && statusKey(row) !== wantedStatus) return false;
      if (wantedPlatform && String(row.platform).toLowerCase() !== wantedPlatform.toLowerCase()) return false;
      const d = rowDate(row);
      if (dateFrom && d && d < dateFrom) return false;
      if (dateTo && d && d > dateTo) return false;
      if (wantedArtifactType === 'apk' && !hasArtifact(row)) return false;
      if (wantedArtifactType === 'missing' && !isMissingArtifact(row)) return false;
      return true;
    });

    page = 1;
    renderRows();
    renderArtifacts();
  }

  const formatFileSize = (bytes) => {
    const n = Number(bytes || 0);
    if (!n) return '';
    if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MB`;
    if (n >= 1024) return `${Math.round(n / 1024)} KB`;
    return `${n} B`;
  };

  const openDownloadDialog = async (row) => {
    if (!row) return;
    const adl = window.ArtifactDownload;
    if (!adl) {
      toast("下载组件未加载，请刷新页面后重试");
      return;
    }
    const versionId = String(row.version_id || scopeVersionId || row.id || "").trim();
    try {
      await adl.open({
        projectId,
        versionId,
        row: {
          ...row,
          build_number: row.build_number || row.number,
          version_id: versionId,
        },
        downloadInfo: row.apk_download,
        titleMode: "build",
        labels: {
          env: envLabels[row.env_key] || row.env_key || "-",
          channel: row.channel_name || row.channel_id || "-",
          platform: platformLabels[String(row.platform || "").toLowerCase()] || row.platform || "-",
        },
      });
    } catch (error) {
      toast(error.message || "下载信息加载失败");
    }
  };

  function renderRows() {
    const pageSize = Number(ui.pageSize?.value || 20);
    const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
    page = Math.min(page, pages);
    const visible = filtered.slice((page - 1) * pageSize, page * pageSize);

    ui.rows.innerHTML = visible.map((row) => {
      const num = row.build_number || row.number;
      const isSelected = selected
        && String(selected.instance_id) === String(row.instance_id)
        && Number(selected.build_number || selected.number) === Number(num);
      const consoleUrl = String(row.console_url || '').trim();
      const statusCls = rowStatusClass(row);
      const buildNumberCell = `<button type="button" class="build-number-link" data-build-task title="${consoleUrl ? `打开 Jenkins 构建 #${esc(num)}` : `查看构建 #${esc(num)}`}">#${esc(num)}</button>`;
      const downloadBtn = statusKey(row) === 'SUCCESS' && hasArtifact(row)
        ? `<button type="button" class="build-row-download" data-download-row title="下载产物"><img src="${icon('action_download')}" alt=""></button>`
        : '';
      const consoleBtn = consoleUrl
        ? `<button type="button" data-console title="打开 Jenkins 控制台"><img src="${icon('action_export')}" alt=""></button>`
        : '';
      return `<tr data-row data-instance="${esc(row.instance_id)}" data-number="${esc(num)}" data-version="${esc(row.version_id)}" class="${statusCls}${isSelected ? ' selected' : ''}">
        <td><input type="checkbox" data-check aria-label="选择构建 ${esc(num)}" ${row.building ? 'disabled' : ''}></td>
        <td>${buildNumberCell}</td>
        <td><span class="build-version"><strong>${esc(row.version_name || '未命名版本')}</strong><small>VC ${esc(row.version_code || '-')}</small></span></td>
        <td>${esc(envLabels[row.env_key] || row.env_key || '未配置')}</td>
        <td>${esc(row.channel_name || row.channel_id || '未配置')}</td>
        <td>${esc(platformLabels[String(row.platform || '').toLowerCase()] || row.platform || '未配置')}</td>
        <td>${statusBadge(row)}</td>
        <td>${esc(row.triggered_by || '-')}</td>
        <td>${esc(dateText(row.started_at))}</td>
        <td>${esc(row.duration || '-')}</td>
        <td><span class="build-row-actions">${consoleBtn}${downloadBtn}<button type="button" data-open title="查看完整详情"><img src="${icon('nav_doc')}" alt=""></button>${canEdit && !row.building ? `<button type="button" data-delete title="删除"><img src="${icon('action_delete')}" alt=""></button>` : ''}</span></td>
      </tr>`;
    }).join('');

    ui.state.hidden = true;
    ui.tableWrap.hidden = false;
    ui.resultCount.textContent = `共 ${filtered.length} 条记录`;
    ui.pageText.textContent = `${page} / ${pages}`;
    ui.prev.disabled = page <= 1;
    ui.next.disabled = page >= pages;
    ui.checkAll.checked = false;
    updateBatchState();

    if (!visible.length) {
      ui.state.hidden = false;
      ui.tableWrap.hidden = true;
      ui.state.innerHTML = `<img src="${icon('global_search')}" alt="" style="width:30px"><strong>没有匹配的构建记录</strong><p>请调整筛选条件后重试。</p>`;
    }
  }

  function findRow(target) {
    const rowEl = target.closest('[data-row]');
    if (!rowEl) return null;
    return records.find(
      (row) => String(row.instance_id) === rowEl.dataset.instance
        && Number(row.build_number || row.number) === Number(rowEl.dataset.number),
    );
  }

  function renderCurrent(row) {
    selected = row;
    ui.currentEmpty.hidden = true;
    ui.current.hidden = false;
    const progress = row.building ? 62 : 100;
    const num = row.build_number || row.number;
    ui.current.innerHTML = `<div class="current-number"><strong>#${esc(num)}</strong>${statusBadge(row)}</div><div class="current-progress"><span style="width:${progress}%"></span></div><dl class="build-kv-grid">
      <div class="build-kv is-ready"><dt>版本</dt><dd title="${esc(row.version_name || '-')}">${esc(row.version_name || '-')} (${esc(row.version_code || '-')})</dd></div>
      <div class="build-kv"><dt>环境 / 平台</dt><dd>${esc(envLabels[row.env_key] || '-')} / ${esc(platformLabels[String(row.platform || '').toLowerCase()] || row.platform || '-')}</dd></div>
      <div class="build-kv"><dt>Jenkins 实例</dt><dd>${esc(row.instance_id || '-')}</dd></div>
      <div class="build-kv"><dt>触发人</dt><dd>${esc(row.triggered_by || '-')}</dd></div>
      <div class="build-kv"><dt>触发时间</dt><dd>${esc(dateText(row.started_at))}</dd></div>
      <div class="build-kv"><dt>耗时</dt><dd>${esc(row.duration || '-')}</dd></div>
    </dl>`;
    ui.failurePanel.hidden = statusKey(row) !== 'FAILURE';
    ui.failure.textContent = row.failure_summary || '请打开完整详情读取真实失败日志。';
    [ui.detail, ui.downloadLog, ui.console, ui.deleteCurrent, ui.installApk].filter(Boolean).forEach((button) => {
      button.disabled = false;
    });
    if (ui.installApk) ui.installApk.disabled = !hasArtifact(row);
    ui.console.disabled = !row.console_url;
    document.querySelectorAll('[data-row]').forEach((el) => {
      el.classList.toggle(
        'selected',
        el.dataset.instance === String(row.instance_id) && Number(el.dataset.number) === Number(num),
      );
    });
  }

  async function loadDetail(row, openDrawer = true) {
    const num = row.build_number || row.number;
    if (openDrawer) {
      openDetailDrawer(row, '<div class="build-state"><span class="build-spinner"></span><strong>正在加载构建详情</strong><p>读取真实参数和日志。</p></div>');
    }
    try {
      const query = new URLSearchParams({
        instance_id: row.instance_id || '',
        version_id: row.version_id || '',
        project_id: projectId,
      });
      const response = await fetch(`/api/build/${encodeURIComponent(num)}/detail?${query}`, { credentials: 'same-origin' });
      const data = await response.json();
      if (!response.ok || !data.build) throw new Error(data.error || '构建详情加载失败');
      data.build.version_name = data.build.version_name || row.version_name;
      data.build.version_code = data.build.version_code || row.version_code;
      data.build.version_id = data.build.version_id || row.version_id;
      data.build.project_id = data.build.project_id || projectId;
      data.build.channel_id = data.build.channel_id || row.channel_id;
      data.build.channel_name = data.build.channel_name || row.channel_name;
      data.build.env_key = data.build.env_key || row.env_key;
      data.build.platform = data.build.platform || row.platform;
      Object.assign(row, data.build);
      renderCurrent(row);
      if (openDrawer) openDetailDrawer(row, detailHtml(data.build));
    } catch (error) {
      if (openDrawer) {
        openDetailDrawer(row, `<div class="build-state"><img src="${icon('status_error')}" alt="" style="width:32px"><strong>构建详情加载失败</strong><p>${esc(error.message)}</p></div>`);
      }
      toast(error.message);
    }
  }

  function detailHtml(row) {
    const params = Object.entries(row.parameters || {});
    return `<div class="detail-grid">${[
      ['构建状态', statusText(row)],
      ['版本', `${row.version_name || '-'} (${row.version_code || '-'})`],
      ['环境', envLabels[row.env_key] || row.env_key || '-'],
      ['渠道', row.channel_name || row.channel_id || '-'],
      ['平台', platformLabels[String(row.platform || '').toLowerCase()] || row.platform || '-'],
      ['Jenkins 实例', row.instance_id || '-'],
      ['触发人', row.triggered_by || '-'],
      ['开始时间', dateText(row.started_at)],
      ['结束时间', dateText(row.ended_at)],
      ['耗时', row.duration || '-'],
      ['日志大小', `${row.log_size || 0} 字符`],
    ].map(([k, v]) => `<div class="detail-card"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('')}</div>
      <section class="detail-section"><h3>构建参数</h3>${params.length ? `<table>${params.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>` : '<div class="build-current-empty"><strong>无构建参数</strong></div>'}</section>
      <section class="detail-section"><h3>构建日志</h3><pre>${esc(row.log || '暂无日志')}</pre></section>`;
  }

  function openDetailDrawer(row, html) {
    const mask = document.querySelector('[data-drawer-mask]');
    mask.hidden = false;
    document.querySelector('[data-drawer-title]').textContent = `构建 #${row.build_number || row.number}`;
    document.querySelector('[data-drawer-subtitle]').textContent = `${row.version_name || '未命名版本'} / VersionCode ${row.version_code || '-'}`;
    document.querySelector('[data-drawer-body]').innerHTML = html;
  }

  function updateBatchState() {
    if (!ui.batchDelete) return;
    const count = root.querySelectorAll('[data-check]:checked').length;
    ui.batchDelete.disabled = count === 0;
    const label = count ? `批量删除 (${count})` : '批量删除';
    const img = ui.batchDelete.querySelector('img');
    ui.batchDelete.textContent = label;
    if (img) ui.batchDelete.prepend(img);
  }

  function askDelete(items) {
    pendingDelete = items;
    const mask = document.querySelector('[data-confirm-mask]');
    mask.hidden = false;
    document.querySelector('[data-confirm-title]').textContent = items.length > 1
      ? `确认删除 ${items.length} 条构建记录`
      : `确认删除构建 #${items[0].build_number || items[0].number}`;
    document.querySelector('[data-confirm-text]').textContent = '将同时删除对应 Jenkins 构建目录；被发布单或 Bundle 引用的构建不允许删除。';
    document.querySelector('[data-confirm-reason]').value = '';
  }

  async function deletePending() {
    const reason = document.querySelector('[data-confirm-reason]').value.trim();
    if (!reason) {
      toast('请输入删除原因');
      return;
    }
    const button = document.querySelector('[data-confirm-action]');
    button.disabled = true;
    try {
      if (pendingDelete.length === 1) {
        const row = pendingDelete[0];
        const num = row.build_number || row.number;
        const query = new URLSearchParams({
          instance_id: row.instance_id || '',
          version_id: row.version_id || '',
          project_id: projectId,
        });
        const response = await fetch(`/api/build/${encodeURIComponent(num)}?${query}`, {
          method: 'DELETE',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ instance_id: row.instance_id, reason }),
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || '删除失败');
      } else {
        const response = await fetch('/api/build/records/batch-delete', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_id: projectId,
            reason,
            items: pendingDelete.map((row) => ({
              instance_id: row.instance_id,
              build_number: row.build_number || row.number,
              version_id: row.version_id || '',
            })),
          }),
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || '批量删除失败');
      }
      document.querySelector('[data-confirm-mask]').hidden = true;
      toast('构建记录已删除');
      await load();
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function load() {
    ui.state.hidden = false;
    ui.tableWrap.hidden = true;
    ui.state.innerHTML = '<span class="build-spinner"></span><strong>正在加载构建历史</strong><p>正在同步本地记录与 Jenkins 实时状态。</p>';
    try {
      let loaded = [];
      if (scopeVersionId) {
        const response = await fetch(`/api/build/history-by-version?version_id=${encodeURIComponent(scopeVersionId)}`, { credentials: 'same-origin' });
        const data = await response.json();
        if (!response.ok || data.ok === false) throw new Error(data.error || '构建历史加载失败');
        loaded = (data.builds || []).map((build) => ({
          ...build,
          version_id: scopeVersionId,
          version_name: build.version_name || scopeVersionName,
          version_code: build.version_code || scopeVersionCode,
          env_key: build.env_key || scopeEnvKey,
          platform: build.platform || scopePlatform,
          channel_id: build.channel_id || scopeChannelId,
          channel_name: build.channel_name || '',
        }));
      } else {
        const response = await fetch(`/api/build/history-by-project?project_id=${encodeURIComponent(projectId)}`, { credentials: 'same-origin' });
        const data = await response.json();
        if (!response.ok || data.ok === false) throw new Error(data.error || '构建历史加载失败');
        loaded = flatten(data.groups);
      }
      records = loaded.filter(matchesScope);
      selected = null;
      setKpis();
      applyFilters();
      renderArtifacts();
      const initial = scopeBuildNumber
        ? records.find((row) => String(row.build_number || row.number) === scopeBuildNumber)
        : records[0];
      if (initial) {
        renderCurrent(initial);
        loadDetail(initial, Boolean(scopeBuildNumber));
      }
    } catch (error) {
      ui.state.hidden = false;
      ui.tableWrap.hidden = true;
      ui.state.innerHTML = `<img src="${icon('status_error')}" alt="" style="width:32px"><strong>构建历史加载失败</strong><p>${esc(error.message)}</p>`;
    }
  }

  if (ui.artifactTabs) {
    ui.artifactTabs.addEventListener('click', (event) => {
      const btn = event.target.closest('[data-artifact-view]');
      if (!btn) return;
      artifactView = btn.getAttribute('data-artifact-view') || 'latest';
      ui.artifactTabs.querySelectorAll('button').forEach((node) => node.classList.toggle('active', node === btn));
      renderArtifacts();
    });
  }

  applyScopeUi();

  root.addEventListener('click', (event) => {
    if (event.target.closest('[data-refresh]')) load();

    if (event.target.closest('[data-reset]')) {
      if (ui.search) ui.search.value = '';
      if (ui.status) ui.status.value = '';
      if (!scopePlatform && ui.platform) ui.platform.value = '';
      if (ui.dateFrom) ui.dateFrom.value = '';
      if (ui.dateTo) ui.dateTo.value = '';
      if (ui.artifactType) ui.artifactType.value = '';
      applyFilters();
      return;
    }

    const row = findRow(event.target);
    if (event.target.closest('[data-build-task]') && row) {
      event.stopPropagation();
      renderCurrent(row);
      loadDetail(row, false);
      const consoleUrl = String(row.console_url || '').trim();
      if (consoleUrl) window.open(consoleUrl, '_blank', 'noopener');
      else loadDetail(row, true);
      return;
    }
    if (event.target.closest('[data-download-row]') && row) {
      event.stopPropagation();
      renderCurrent(row);
      openDownloadDialog(row);
      return;
    }
    if (event.target.closest('[data-console]') && row) {
      event.stopPropagation();
      renderCurrent(row);
      loadDetail(row, false);
      const consoleUrl = String(row.console_url || '').trim();
      if (consoleUrl) window.open(consoleUrl, '_blank', 'noopener');
      return;
    }
    if (event.target.closest('[data-delete]') && row) {
      event.stopPropagation();
      askDelete([row]);
      return;
    }
    if (event.target.closest('[data-open]') && row) {
      event.stopPropagation();
      renderCurrent(row);
      loadDetail(row, true);
      return;
    }
    if (row && !event.target.matches('input') && !event.target.closest('[data-check]')) {
      renderCurrent(row);
      loadDetail(row, false);
    }
  });

  [ui.search, ui.status, ui.platform, ui.pageSize, ui.dateFrom, ui.dateTo, ui.artifactType]
    .filter(Boolean)
    .forEach((control) => {
      control.addEventListener(control === ui.search ? 'input' : 'change', applyFilters);
    });

  ui.prev?.addEventListener('click', () => { page -= 1; renderRows(); });
  ui.next?.addEventListener('click', () => { page += 1; renderRows(); });
  ui.checkAll?.addEventListener('change', () => {
    root.querySelectorAll('[data-check]:not(:disabled)').forEach((box) => { box.checked = ui.checkAll.checked; });
    updateBatchState();
  });
  ui.rows?.addEventListener('change', updateBatchState);
  ui.batchDelete?.addEventListener('click', () => {
    askDelete([...root.querySelectorAll('[data-check]:checked')].map((box) => findRow(box)).filter(Boolean));
  });
  ui.installApk?.addEventListener('click', () => selected && openDownloadDialog(selected));
  ui.detail?.addEventListener('click', () => selected && loadDetail(selected, true));
  ui.downloadLog?.addEventListener('click', () => {
    if (selected) {
      location.href = `/api/build/log/${selected.build_number || selected.number}?instance_id=${encodeURIComponent(selected.instance_id || '')}`;
    }
  });
  ui.console?.addEventListener('click', () => {
    if (selected?.console_url) window.open(selected.console_url, '_blank', 'noopener');
  });
  ui.deleteCurrent?.addEventListener('click', () => selected && askDelete([selected]));

  document.querySelector('[data-close-drawer]')?.addEventListener('click', () => {
    document.querySelector('[data-drawer-mask]').hidden = true;
  });
  document.querySelector('[data-drawer-mask]')?.addEventListener('click', (event) => {
    if (event.target.matches('[data-drawer-mask]')) event.currentTarget.hidden = true;
  });
  document.querySelector('[data-cancel-confirm]')?.addEventListener('click', () => {
    document.querySelector('[data-confirm-mask]').hidden = true;
  });
  document.querySelector('[data-confirm-action]')?.addEventListener('click', deletePending);

  document.addEventListener('pm-shell-search', (event) => {
    if (!ui.search) return;
    ui.search.value = event.detail?.query || '';
    applyFilters();
  });

  load();
})();
