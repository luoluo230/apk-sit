(function () {
  'use strict';

  var currentPlane = 'build';

  function esc(v) {
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function setActiveTab(plane) {
    currentPlane = plane;
    document.querySelectorAll('#bnTabs [data-plane]').forEach(function (btn) {
      var active = btn.getAttribute('data-plane') === plane;
      btn.classList.toggle('is-active', active);
    });
    var buildSection = document.getElementById('bnBuildSection');
    var installHelp = document.getElementById('bnInstallHelp');
    if (buildSection) buildSection.style.display = plane === 'runtime' ? 'none' : '';
    if (installHelp) installHelp.style.display = plane === 'runtime' ? 'none' : '';
    var title = document.getElementById('bnTableTitle');
    if (title) title.textContent = plane === 'runtime' ? 'Runtime 节点（cluster 同步）' : '构建节点';
    renderTableHead(plane);
  }

  function renderTableHead(plane) {
    var head = document.getElementById('bnTableHead');
    if (!head) return;
    if (plane === 'runtime') {
      head.innerHTML = '<tr><th>节点</th><th>角色</th><th>Host</th><th>Port</th><th>状态</th><th>最近心跳</th></tr>';
      return;
    }
    head.innerHTML = '<tr><th>节点</th><th>角色</th><th>OS</th><th>Unity</th><th>状态</th><th>最近心跳</th><th>操作</th></tr>';
  }

  async function loadSummary() {
    var resp = await fetch('/api/admin/infra-nodes/summary', { credentials: 'same-origin' });
    var data = await resp.json();
    if (!data.ok) throw new Error(data.error || '加载失败');
    renderRoles(data.roles || []);
    return data;
  }

  async function loadNodes() {
    var qs = new URLSearchParams();
    if (currentPlane === 'build' || currentPlane === 'runtime') qs.set('plane', currentPlane);
    var resp = await fetch('/api/admin/infra-nodes?' + qs.toString(), { credentials: 'same-origin' });
    var data = await resp.json();
    if (!data.ok) throw new Error(data.error || '加载失败');
    renderNodes(data.nodes || []);
  }

  async function refreshAll() {
    await loadSummary();
    await loadNodes();
  }

  function renderRoles(roles) {
    var host = document.getElementById('bnRoleCards');
    if (!host) return;
    host.innerHTML = roles
      .filter(function (r) { return r.role_id !== 'control'; })
      .map(function (r) {
        var ok = r.healthy;
        return (
          '<div class="bn-role-card ' + (ok ? 'is-ok' : 'is-bad') + '">' +
          '<div class="bn-role-card__top">' +
          '<div class="bn-role-card__title">' + esc(r.display_name) + '</div>' +
          '<span class="bn-badge ' + (ok ? 'is-ok' : 'is-bad') + '">' + (ok ? '可用' : '不可用') + '</span></div>' +
          '<div class="bn-role-card__meta">label: ' + esc(r.label) + '</div>' +
          '<div class="bn-role-card__meta">job: ' + esc(r.job_name) + '</div>' +
          '<div class="bn-role-card__count">在线 ' + esc(r.online_count) + ' / 注册 ' + esc(r.total_count) + '</div>' +
          '</div>'
        );
      })
      .join('');
  }

  function renderNodes(nodes) {
    var tbody = document.getElementById('bnNodeRows');
    if (!tbody) return;
    if (!nodes.length) {
      var empty = currentPlane === 'runtime'
        ? '暂无 Runtime 节点，请执行 cluster 同步'
        : '暂无注册节点，请在各构建机运行 Install-ReleasePlatform';
      tbody.innerHTML = '<tr><td colspan="7" class="bn-empty">' + esc(empty) + '</td></tr>';
      return;
    }
    if (currentPlane === 'runtime') {
      tbody.innerHTML = nodes.map(function (n) {
        return (
          '<tr>' +
          '<td>' + esc(n.display_name || n.id) + '</td>' +
          '<td>' + esc(n.role_display_name || n.role) + '</td>' +
          '<td>' + esc(n.host || '-') + '</td>' +
          '<td>' + esc(n.port || '-') + '</td>' +
          '<td>' + esc(n.status || '-') + '</td>' +
          '<td class="bn-muted">' + esc(n.last_heartbeat_at || '-') + '</td>' +
          '</tr>'
        );
      }).join('');
      return;
    }
    tbody.innerHTML = nodes.map(function (n) {
      var st = n.online ? '在线' : '离线';
      var cls = n.online ? 'bn-online' : 'bn-offline';
      return (
        '<tr>' +
        '<td>' + esc(n.agent_name || n.hostname || n.id) + '</td>' +
        '<td>' + esc(n.role_display_name || n.role) + '</td>' +
        '<td>' + esc(n.os) + '</td>' +
        '<td>' + esc(n.unity_version || '-') + '</td>' +
        '<td class="' + cls + '">' + st + '</td>' +
        '<td class="bn-muted">' + esc(n.last_heartbeat || n.last_heartbeat_at || '-') + '</td>' +
        '<td><button type="button" class="bn-del" data-del="' + esc(n.id) + '">移除</button></td>' +
        '</tr>'
      );
    }).join('');
    tbody.querySelectorAll('[data-del]').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        var id = btn.getAttribute('data-del');
        if (!id || !window.confirm('移除节点记录？')) return;
        await fetch('/api/admin/infra-nodes/' + encodeURIComponent(id), { method: 'DELETE', credentials: 'same-origin' });
        refreshAll().catch(function (e) { alert(e.message || e); });
      });
    });
  }

  document.querySelectorAll('#bnTabs [data-plane]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      setActiveTab(btn.getAttribute('data-plane') || 'build');
      loadNodes().catch(function (e) { alert(e.message || e); });
    });
  });

  var refreshBtn = document.getElementById('bnRefresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', function () {
      refreshAll().catch(function (e) { alert(e.message || e); });
    });
  }

  setActiveTab('build');
  refreshAll().catch(function (e) { alert(e.message || e); });
  setInterval(function () { refreshAll().catch(function () {}); }, 30000);
})();
