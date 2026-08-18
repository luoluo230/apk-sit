(function () {
  var root = document.querySelector('.sm-hub-page');
  if (!root) return;

  var lockedProject = root.dataset.lockedProject || '';
  var showTopology = root.dataset.showTopology === 'true';
  var showBaas = root.dataset.showBaas === 'true';
  var state = {
    tab: root.dataset.defaultTab || (showTopology ? 'topology' : 'baas'),
    items: [],
    projects: [],
    editing: null,
    pollTimer: null,
  };

  var envNames = { development: '开发', testing: '测试', staging: '预发', production: '生产' };
  var statusNames = {
    running: '运行中', active: '运行中', validated: '已验证', draft: '草稿',
    stopped: '已停止', archived: '已归档', disabled: '已禁用', error: '异常', failed: '失败',
  };

  function esc(v) {
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function csrfHeaders() {
    var token = document.querySelector('meta[name="csrf-token"]');
    return token ? { 'X-CSRFToken': token.getAttribute('content') } : {};
  }

  function api(path, opts) {
    opts = opts || {};
    return fetch(path, Object.assign({
      credentials: 'same-origin',
      headers: Object.assign({ 'Content-Type': 'application/json' }, csrfHeaders(), opts.headers || {}),
    }, opts)).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok || j.ok === false) throw new Error((j && j.error) || ('HTTP ' + r.status));
        return j.data;
      });
    });
  }

  function queryParams() {
    var q = (document.getElementById('smSearch').value || '').trim();
    var project = lockedProject || (document.getElementById('smProject').value || '');
    var env = document.getElementById('smEnv').value || '';
    var status = document.getElementById('smStatus').value || '';
    var parts = ['tab=' + encodeURIComponent(state.tab)];
    if (project) parts.push('project_id=' + encodeURIComponent(project));
    if (env) parts.push('env_key=' + encodeURIComponent(env));
    if (status) parts.push('status=' + encodeURIComponent(status));
    if (q) parts.push('q=' + encodeURIComponent(q));
    return parts.join('&');
  }

  function defaultIconUrl() {
    return state.tab === 'baas'
      ? '/static/project_ui/svg/nav_project_setting.svg'
      : '/static/project_ui/svg/nav_topology.svg';
  }

  function setIconPreview(url) {
    var host = document.getElementById('smIconPreview');
    if (!host) return;
    var u = String(url || '').trim();
    if (u) host.innerHTML = '<img src="' + esc(u) + '" alt="">';
    else host.innerHTML = '<span class="p01-icon-upload__placeholder">图标</span>';
  }

  function uploadIconFile(file) {
    if (!file) return Promise.resolve();
    var fd = new FormData();
    fd.append('icon', file);
    return fetch('/admin/projects/upload-icon', {
      method: 'POST',
      body: fd,
      credentials: 'same-origin',
      headers: csrfHeaders(),
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (!d.url) throw new Error(d.error || '上传失败');
      document.getElementById('smIconUrl').value = d.url;
      setIconPreview(d.url);
      return d.url;
    });
  }

  function syncDeployPackBtn() {
    var btn = document.getElementById('smDeployPackBtn');
    if (!btn) return;
    var kind = state.tab === 'baas' ? 'baas' : 'topology';
    btn.href = '/api/server-management/deploy-pack/' + kind;
    btn.setAttribute('download', kind + '-server-architecture.zip');
    btn.hidden = false;
  }

  function syncUrl() {
    var base = lockedProject
      ? '/admin/projects/' + encodeURIComponent(lockedProject) + '/server-management'
      : '/admin/server-management';
    var qs = queryParams();
    history.replaceState(null, '', base + (qs ? '?' + qs : ''));
  }

  function filtersQuery() {
    var q = (document.getElementById('smSearch').value || '').trim();
    var project = lockedProject || (document.getElementById('smProject').value || '');
    var env = document.getElementById('smEnv').value || '';
    var status = document.getElementById('smStatus').value || '';
    var qs = new URLSearchParams();
    if (project) qs.set('project_id', project);
    if (env) qs.set('env_key', env);
    if (status) qs.set('status', status);
    if (q) qs.set('q', q);
    var s = qs.toString();
    return s ? '?' + s : '';
  }

  function loadProjects() {
    try {
      state.projects = JSON.parse(document.getElementById('smProjectsJson').textContent || '[]');
    } catch (e) {
      state.projects = [];
    }
    var sel = document.getElementById('smProject');
    var formSel = document.querySelector('#smForm select[name="project_id"]');
    [sel, formSel].forEach(function (host) {
      if (!host) return;
      var current = host.value || root.dataset.filterProject || lockedProject || '';
      host.innerHTML = host === sel ? '<option value="">全部项目</option>' : '';
      state.projects.forEach(function (p) {
        host.innerHTML += '<option value="' + esc(p.id) + '">' + esc(p.name || p.id) + '</option>';
      });
      if (current) host.value = current;
    });
    if (root.dataset.filterEnv) document.getElementById('smEnv').value = root.dataset.filterEnv;
    if (root.dataset.filterStatus) document.getElementById('smStatus').value = root.dataset.filterStatus;
  }

  function endpointList() {
    return state.tab === 'baas'
      ? '/api/server-management/baas-services' + filtersQuery()
      : '/api/server-management/topologies' + filtersQuery();
  }

  function loadCards(silent) {
    if (!silent) document.getElementById('smGrid').innerHTML = '<div class="ops-workspace-empty">正在加载…</div>';
    return api(endpointList(), { method: 'GET', headers: { 'Content-Type': 'application/json' } })
      .then(function (data) {
        state.items = (data && data.items) || [];
        render();
        syncUrl();
      })
      .catch(function (e) {
        document.getElementById('smGrid').innerHTML = '<div class="ops-workspace-empty">加载失败：' + esc(e.message) + '</div>';
      });
  }

  function renderMeta() {
    var host = document.getElementById('smMeta');
    if (!host) return;
    var running = state.items.filter(function (x) {
      var st = (x.runtime && x.runtime.status) || '';
      return st === 'running' || st === 'active' || st === 'validated';
    }).length;
    host.textContent = state.items.length ? ('共 ' + state.items.length + ' · 运行 ' + running) : '暂无匹配服务器';
  }

  function renderLogs(item) {
    var logs = item.log_snippets || [];
    if (!logs.length) return '<ul class="sm-hub-logs"><li>暂无告警日志</li></ul>';
    return '<ul class="sm-hub-logs">' + logs.map(function (lg) {
      var cls = lg.level === 'error' ? ' is-error' : '';
      return '<li class="' + cls + '">' + esc(lg.message || '') + '</li>';
    }).join('') + '</ul>';
  }

  function renderBindings(item) {
    var chips = (item.bindings || []).slice(0, 4).map(function (b) {
      var parts = [];
      if (b.env_key) parts.push(envNames[b.env_key] || b.env_key);
      if (b.platform) parts.push(b.platform);
      if (b.channel_name) parts.push(b.channel_name);
      return '<span class="sm-hub-chip">' + esc(parts.join(' / ') || b.level_label || '-') + '</span>';
    }).join('');
    return chips || '<span class="sm-hub-chip">未绑定</span>';
  }

  function renderStats(item) {
    if (item.kind === 'topology') {
      return '<div class="sm-hub-runtime"><div><dt>节点</dt><dd>' + esc((item.stats && item.stats.node_count) || 0) + '</dd></div>'
        + '<div><dt>连线</dt><dd>' + esc((item.stats && item.stats.edge_count) || 0) + '</dd></div></div>';
    }
    return '<div class="sm-hub-runtime"><div><dt>配置版本</dt><dd>v' + esc((item.stats && item.stats.config_version) || 0) + '</dd></div>'
      + '<div><dt>玩家</dt><dd>' + esc((item.stats && item.stats.player_count) || 0) + '</dd></div></div>';
  }

  function renderActions(item) {
    var btns = [];
    if (item.kind === 'topology') {
      btns.push('<a class="matrix-btn build" href="' + esc(item.actions.canvas_url) + '">画布</a>');
      btns.push('<a class="matrix-btn version" href="' + esc(item.actions.binding_url) + '">绑定</a>');
    } else {
      btns.push('<a class="matrix-btn build" href="' + esc(item.actions.config_url) + '">配置</a>');
      btns.push('<a class="matrix-btn version" href="' + esc(item.actions.gm_url) + '">GM</a>');
    }
    btns.push('<button type="button" class="matrix-btn server-test" data-edit="' + esc(item.id) + '">编辑</button>');
    btns.push('<button type="button" class="matrix-btn release" data-toggle="' + esc(item.id) + '">' + (item.disabled ? '启用' : '禁用') + '</button>');
    btns.push('<button type="button" class="matrix-btn topology" data-delete="' + esc(item.id) + '">删除</button>');
    return '<div class="sm-hub-card-actions env-line-actions env-line-card-links">' + btns.join('') + '</div>';
  }

  function renderCard(item) {
    var cls = item.card_class || 'neutral';
    var badge = item.badge_class || 'neutral';
    var st = (item.runtime && item.runtime.status) || 'unknown';
    var proj = item.project || {};
    return '<article class="env-line-card sm-hub-card ' + cls + '" data-id="' + esc(item.id) + '">'
      + '<div class="env-line-card-head"><span class="env-line-platform-icon"><img src="' + esc(item.icon_url) + '" alt=""></span>'
      + '<div class="env-line-card-title"><span class="env-line-platform">' + esc(item.name || item.id) + '</span>'
      + '<span class="env-line-badge ' + badge + '">' + esc(item.status_label || statusNames[st] || st) + '</span></div></div>'
      + '<p class="sm-hub-card-id" title="' + esc(item.id) + '">ID: ' + esc(item.id) + '</p>'
      + '<p class="sm-hub-card-desc">' + esc(item.description || '暂无描述') + '</p>'
      + '<div class="sm-hub-project-row"><img src="' + esc(proj.icon_url) + '" alt=""><span>' + esc(proj.name || proj.id || '-') + '</span></div>'
      + '<div class="sm-hub-chips">' + renderBindings(item) + '</div>'
      + '<div class="sm-hub-runtime"><div><dt>运行状态</dt><dd>' + esc(item.status_label || statusNames[st] || st)
      + ((item.runtime && item.runtime.has_error) ? ' ⚠' : '') + '</dd></div>'
      + '<div><dt>持续时长</dt><dd>' + esc((item.runtime && item.runtime.uptime_label) || '-') + '</dd></div></div>'
      + renderStats(item)
      + renderLogs(item)
      + renderActions(item)
      + '</article>';
  }

  function render() {
    renderMeta();
    var host = document.getElementById('smGrid');
    host.innerHTML = state.items.length ? state.items.map(renderCard).join('') : '<div class="ops-workspace-empty">无匹配服务器</div>';
    host.querySelectorAll('[data-edit]').forEach(function (btn) {
      btn.addEventListener('click', function () { openEdit(btn.getAttribute('data-edit')); });
    });
    host.querySelectorAll('[data-toggle]').forEach(function (btn) {
      btn.addEventListener('click', function () { toggleDisabled(btn.getAttribute('data-toggle')); });
    });
    host.querySelectorAll('[data-delete]').forEach(function (btn) {
      btn.addEventListener('click', function () { removeItem(btn.getAttribute('data-delete')); });
    });
  }

  function setTab(tab) {
    if (tab === 'topology' && !showTopology) tab = 'baas';
    if (tab === 'baas' && !showBaas) tab = 'topology';
    state.tab = tab;
    document.querySelectorAll('.sm-hub-tab').forEach(function (el) {
      el.classList.toggle('is-active', el.getAttribute('data-tab') === tab);
    });
    loadCards();
    syncDeployPackBtn();
  }

  function openDialog(mode, item) {
    var dlg = document.getElementById('smDialog');
    var form = document.getElementById('smForm');
    var isEdit = mode === 'edit';
    form.mode.value = mode;
    form.kind.value = state.tab;
    document.getElementById('smDialogTitle').textContent = mode === 'create' ? ('新建' + (state.tab === 'baas' ? '轻度服务器' : '拓扑')) : '编辑';
    form.name.value = item ? item.name : '';
    form.resource_id.value = item ? item.id : '';
    form.resource_id.readOnly = isEdit;
    form.resource_id.disabled = isEdit;
    form.name.readOnly = isEdit;
    form.name.disabled = isEdit;
    form.description.value = item ? (item.description || '') : '';
    var iconUrl = item ? (item.icon_url || '') : defaultIconUrl();
    document.getElementById('smIconUrl').value = iconUrl;
    setIconPreview(iconUrl);
    var iconFile = document.getElementById('smIconFile');
    if (iconFile) iconFile.value = '';
    form.env_key.value = item ? (item.env_key || 'development') : 'development';
    form.env_key.disabled = isEdit;
    if (lockedProject) form.project_id.value = lockedProject;
    else form.project_id.value = item ? ((item.project && item.project.id) || '') : (document.getElementById('smProject').value || '');
    document.querySelector('.sm-project-field').style.display = lockedProject ? 'none' : '';
    document.getElementById('smDialogFeedback').textContent = '';
    state.editing = item || null;
    dlg.hidden = false;
  }

  function closeDialog() {
    document.getElementById('smDialog').hidden = true;
    state.editing = null;
  }

  function detailPath(id) {
    return state.tab === 'baas'
      ? '/api/server-management/baas-services/' + encodeURIComponent(id)
      : '/api/server-management/topologies/' + encodeURIComponent(id);
  }

  function openEdit(id) {
    var item = state.items.find(function (x) { return x.id === id; });
    if (!item) return;
    openDialog('edit', item);
  }

  function toggleDisabled(id) {
    var item = state.items.find(function (x) { return x.id === id; });
    if (!item) return;
    var next = !item.disabled;
    api(detailPath(id), { method: 'PATCH', body: JSON.stringify({ disabled: next }) })
      .then(function () { loadCards(true); })
      .catch(function (e) { alert(e.message); });
  }

  function removeItem(id) {
    if (!confirm('确认删除？此操作不可撤销。')) return;
    api(detailPath(id), { method: 'DELETE' })
      .then(function () { loadCards(); })
      .catch(function (e) { alert(e.message); });
  }

  function submitForm(ev) {
    ev.preventDefault();
    var form = ev.target;
    var fb = document.getElementById('smDialogFeedback');
    var payload = {
      name: form.name.value.trim(),
      description: form.description.value.trim(),
      icon_url: (document.getElementById('smIconUrl').value || defaultIconUrl()).trim(),
      env_key: form.env_key.value,
      project_id: lockedProject || form.project_id.value,
    };
    var mode = form.mode.value;
    var path = mode === 'create'
      ? (state.tab === 'baas' ? '/api/server-management/baas-services' : '/api/server-management/topologies')
      : detailPath(form.resource_id.value.trim());
    if (mode === 'create') {
      if (state.tab === 'baas') payload.service_id = form.resource_id.value.trim();
      else payload.topology_id = form.resource_id.value.trim();
    }
    api(path, { method: mode === 'create' ? 'POST' : 'PATCH', body: JSON.stringify(payload) })
      .then(function (data) {
        if (data && data.api_secret) {
          fb.textContent = '已创建。API Secret（仅显示一次）：' + data.api_secret;
          loadCards();
          return;
        }
        closeDialog();
        loadCards();
      })
      .catch(function (e) { fb.textContent = e.message; });
  }

  function bindEvents() {
    document.querySelectorAll('.sm-hub-tab').forEach(function (btn) {
      btn.addEventListener('click', function () { setTab(btn.getAttribute('data-tab')); });
    });
    ['smSearch', 'smProject', 'smEnv', 'smStatus'].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('change', function () { loadCards(); });
      if (id === 'smSearch') el.addEventListener('input', debounce(function () { loadCards(); }, 300));
    });
    document.getElementById('smRefresh').addEventListener('click', function () { loadCards(); });
    document.getElementById('smCreateBtn').addEventListener('click', function () { openDialog('create', null); });
    document.getElementById('smForm').addEventListener('submit', submitForm);
    document.getElementById('smDialogClose').addEventListener('click', closeDialog);
    document.getElementById('smDialogCancel').addEventListener('click', closeDialog);
    var iconFile = document.getElementById('smIconFile');
    if (iconFile) {
      iconFile.addEventListener('change', function () {
        if (!iconFile.files || !iconFile.files[0]) return;
        var fb = document.getElementById('smDialogFeedback');
        uploadIconFile(iconFile.files[0]).catch(function (e) {
          if (fb) fb.textContent = e.message;
        });
      });
    }
  }

  function debounce(fn, ms) {
    var t;
    return function () {
      clearTimeout(t);
      var args = arguments;
      var self = this;
      t = setTimeout(function () { fn.apply(self, args); }, ms);
    };
  }

  function startPoll() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = setInterval(function () { loadCards(true); }, 25000);
  }

  loadProjects();
  bindEvents();
  syncDeployPackBtn();
  loadCards();
  startPoll();
})();
