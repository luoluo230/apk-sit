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
      btn.className = 'px-3 py-1.5 rounded-md ' + (active ? 'bg-indigo-600 text-white' : 'text-slate-600');
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
      head.innerHTML = '<tr><th class="px-4 py-2 text-left">节点</th><th class="px-4 py-2 text-left">角色</th><th class="px-4 py-2 text-left">Host</th><th class="px-4 py-2 text-left">Port</th><th class="px-4 py-2 text-left">状态</th><th class="px-4 py-2 text-left">最近心跳</th></tr>';
      return;
    }
    head.innerHTML = '<tr><th class="px-4 py-2 text-left">节点</th><th class="px-4 py-2 text-left">角色</th><th class="px-4 py-2 text-left">OS</th><th class="px-4 py-2 text-left">Unity</th><th class="px-4 py-2 text-left">状态</th><th class="px-4 py-2 text-left">最近心跳</th><th class="px-4 py-2 text-left">操作</th></tr>';
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
        var badge = ok ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800';
        var label = ok ? '可用' : '不可用';
        return (
          '<div class="rounded-xl border p-4 ' + (ok ? 'border-emerald-200 bg-emerald-50/40' : 'border-rose-200 bg-rose-50/40') + '">' +
          '<div class="flex items-center justify-between">' +
          '<div class="font-semibold text-slate-900">' + esc(r.display_name) + '</div>' +
          '<span class="text-xs px-2 py-0.5 rounded ' + badge + '">' + label + '</span></div>' +
          '<div class="mt-2 text-xs text-slate-600">label: ' + esc(r.label) + '</div>' +
          '<div class="text-xs text-slate-600">job: ' + esc(r.job_name) + '</div>' +
          '<div class="mt-2 text-sm">在线 ' + esc(r.online_count) + ' / 注册 ' + esc(r.total_count) + '</div>' +
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
      tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-6 text-center text-slate-500">' + esc(empty) + '</td></tr>';
      return;
    }
    if (currentPlane === 'runtime') {
      tbody.innerHTML = nodes.map(function (n) {
        return (
          '<tr>' +
          '<td class="px-4 py-2">' + esc(n.display_name || n.id) + '</td>' +
          '<td class="px-4 py-2">' + esc(n.role_display_name || n.role) + '</td>' +
          '<td class="px-4 py-2">' + esc(n.host || '-') + '</td>' +
          '<td class="px-4 py-2">' + esc(n.port || '-') + '</td>' +
          '<td class="px-4 py-2">' + esc(n.status || '-') + '</td>' +
          '<td class="px-4 py-2 text-xs">' + esc(n.last_heartbeat_at || '-') + '</td>' +
          '</tr>'
        );
      }).join('');
      return;
    }
    tbody.innerHTML = nodes.map(function (n) {
      var st = n.online ? '在线' : '离线';
      var cls = n.online ? 'text-emerald-700' : 'text-slate-500';
      return (
        '<tr>' +
        '<td class="px-4 py-2">' + esc(n.agent_name || n.hostname || n.id) + '</td>' +
        '<td class="px-4 py-2">' + esc(n.role_display_name || n.role) + '</td>' +
        '<td class="px-4 py-2">' + esc(n.os) + '</td>' +
        '<td class="px-4 py-2">' + esc(n.unity_version || '-') + '</td>' +
        '<td class="px-4 py-2 ' + cls + '">' + st + '</td>' +
        '<td class="px-4 py-2 text-xs">' + esc(n.last_heartbeat || n.last_heartbeat_at || '-') + '</td>' +
        '<td class="px-4 py-2"><button type="button" class="text-rose-600 text-xs" data-del="' + esc(n.id) + '">移除</button></td>' +
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

  document.getElementById('bnRefresh')?.addEventListener('click', function () {
    refreshAll().catch(function (e) { alert(e.message || e); });
  });

  setActiveTab('build');
  refreshAll().catch(function (e) { alert(e.message || e); });
  setInterval(function () { refreshAll().catch(function () {}); }, 30000);
})();
