/**
 * Jenkins 实例管理页（/admin/jenkins）
 * v20260609 — 移除已废弃的 Git 表单绑定，所有按钮使用 null-safe 绑定
 */
(function (global) {
  'use strict';

  function _jmHeaders(isJson) {
    var t = document.querySelector('meta[name="csrf-token"]');
    var h = {};
    if (isJson) h['Content-Type'] = 'application/json';
    if (t && t.content) h['X-CSRFToken'] = t.content;
    return h;
  }

  function _jmBindClick(id, fn) {
    var el = document.getElementById(id);
    if (el) el.onclick = fn;
  }

  var _listFilter = 'all';
  var _allInstances = [];

  function filterList(type) {
    _listFilter = type;
    document.querySelectorAll('#listFilterTabs [data-filter]').forEach(function (btn) {
      var on = btn.getAttribute('data-filter') === type;
      btn.className = 'pm-btn pm-btn--compact' + (on ? ' pm-btn--primary is-active' : '');
    });
    renderList();
  }

  function _typeBadge(t) {
    return t === 'commercial'
      ? '<span class="jm-badge jm-badge--commercial">商业</span>'
      : '<span class="jm-badge jm-badge--general">通用</span>';
  }

  function renderList() {
    var tbody = document.getElementById('jenkinsInstanceList');
    var msg = document.getElementById('instanceListMsg');
    if (!tbody || !msg) return;
    var filtered =
      _listFilter === 'all'
        ? _allInstances
        : _allInstances.filter(function (i) {
            return (i.instance_type || 'general') === _listFilter;
          });
    if (!filtered.length) {
      tbody.innerHTML = '';
      msg.textContent = '暂无实例';
      return;
    }
    var rows = filtered
      .map(function (i) {
        var t = i.instance_type || 'general';
        var status =
          i.status === 'running'
            ? '<span class="jm-status-ok">运行中</span>'
            : '<span class="jm-status-off">已停止</span>';
        var stopBtn =
          i.status === 'running'
            ? '<button type="button" onclick="stopInstance(\'' +
              i.id +
              '\')" class="jm-link jm-link--danger">停止</button>'
            : '';
        var startBtn =
          i.status !== 'running'
            ? '<button type="button" onclick="startInstance(\'' +
              i.id +
              '\')" class="jm-link jm-link--ok">启动</button>'
            : '';
        var delBtn =
          '<button type="button" onclick="deleteInstance(\'' +
          i.id +
          '\')" class="jm-link">删除</button>';
        var consoleUrl = 'http://127.0.0.1:' + i.port + '/';
        var consoleBtn =
          i.status === 'running'
            ? '<a href="' + consoleUrl + '" target="_blank" class="jm-link">控制台</a>'
            : '<span class="jm-link jm-link--muted">控制台</span>';
        var logBtn =
          '<a href="/admin/jenkins/instance-log?instance_id=' +
          encodeURIComponent(i.id) +
          '" target="_blank" class="jm-link">日志</a>';
        var editBtn =
          '<a href="/admin/jenkins/edit?instance_id=' +
          encodeURIComponent(i.id) +
          '" class="jm-link">编辑</a>';
        var taskName = (i.task_name || '').trim() || '-';
        return (
          '<tr class="border-b"><td class="py-2">' +
          _typeBadge(t) +
          '</td><td class="py-2">' +
          i.port +
          '</td><td>' +
          taskName +
          '</td><td>' +
          status +
          '</td><td>' +
          (i.added_at || '') +
          '</td><td>' +
          (i.added_by || '') +
          '</td><td>' +
          (i.started_at || '') +
          '</td><td>' +
          (i.started_by || '') +
          '</td><td>' +
          consoleBtn +
          ' ' +
          logBtn +
          ' ' +
          editBtn +
          ' ' +
          startBtn +
          stopBtn +
          delBtn +
          '</td></tr>'
        );
      })
      .join('');
    tbody.innerHTML = rows;
    msg.textContent = '共 ' + filtered.length + ' 个实例';
  }

  function loadList() {
    fetch('/api/jenkins-manage/list', { credentials: 'same-origin' })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        _allInstances = d && d.instances ? d.instances : [];
        renderList();
      })
      .catch(function () {
        var msg = document.getElementById('instanceListMsg');
        if (msg) msg.textContent = '加载失败';
      });
  }

  function startInstance(id) {
    fetch('/api/jenkins-manage/start-instance', {
      method: 'POST',
      headers: _jmHeaders(true),
      credentials: 'same-origin',
      body: JSON.stringify({ instance_id: id }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (d.success) loadList();
        else alert(d.error || '启动失败');
      });
  }

  function stopInstance(id) {
    if (!confirm('确定停止该 Jenkins？')) return;
    fetch('/api/jenkins-manage/stop', {
      method: 'POST',
      headers: _jmHeaders(true),
      credentials: 'same-origin',
      body: JSON.stringify({ instance_id: id }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (d.success) loadList();
        else alert(d.error || '停止失败');
      });
  }

  function deleteInstance(id) {
    if (!confirm('确定从列表删除该实例？（不会删除 JENKINS_HOME 数据）')) return;
    fetch('/api/jenkins-manage/delete', {
      method: 'POST',
      headers: _jmHeaders(true),
      credentials: 'same-origin',
      body: JSON.stringify({ instance_id: id }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (d.success) loadList();
        else alert(d.error || '删除失败');
      });
  }

  function bindEvents() {
    function _setInstanceType( whichtype ) {
      var typeEl = document.getElementById('newInstanceType');
      if (typeEl) typeEl.value = whichtype;
      var g = document.getElementById('instanceTypeGeneral');
      var c = document.getElementById('instanceTypeCommercial');
      if (g) g.classList.toggle('is-active', whichtype === 'general');
      if (c) c.classList.toggle('is-active', whichtype === 'commercial');
    }
    _jmBindClick('instanceTypeGeneral', function () { _setInstanceType('general'); });
    _jmBindClick('instanceTypeCommercial', function () { _setInstanceType('commercial'); });
    _jmBindClick('btnCheckPort', function () {
      var portEl = document.getElementById('newPort');
      var resultEl = document.getElementById('portCheckResult');
      if (!portEl || !resultEl) return;
      var port = portEl.value.trim();
      resultEl.textContent = '检测中…';
      fetch('/api/jenkins-manage/check-port?port=' + encodeURIComponent(port), { credentials: 'same-origin' })
        .then(function (r) {
          return r.json();
        })
        .then(function (d) {
          resultEl.textContent = d.message;
          resultEl.className = 'text-sm ' + (d.ok ? 'text-green-600' : 'text-red-600');
        });
    });
    _jmBindClick('btnStartJenkins', function () {
      var portEl = document.getElementById('newPort');
      var el = document.getElementById('startResult');
      if (!portEl || !el) return;
      var port = portEl.value.trim();
      var taskNameEl = document.getElementById('newTaskName');
      var feishuEl = document.getElementById('newFeishuWebhook');
      var dingEl = document.getElementById('newDingtalkWebhook');
      var wecomEl = document.getElementById('newWecomWebhook');
      var taskName = taskNameEl && taskNameEl.value ? taskNameEl.value.trim() : '';
      var feishuWebhook = feishuEl && feishuEl.value ? feishuEl.value.trim() : '';
      var dingtalkWebhook = dingEl && dingEl.value ? dingEl.value.trim() : '';
      var wecomWebhook = wecomEl && wecomEl.value ? wecomEl.value.trim() : '';
      el.textContent = '启动中…';
      var body = { port: parseInt(port, 10) };
      var typeEl = document.getElementById('newInstanceType');
      body.instance_type = (typeEl && typeEl.value) || 'general';
      if (taskName) body.task_name = taskName;
      if (feishuWebhook) body.feishu_webhook = feishuWebhook;
      if (dingtalkWebhook) body.dingtalk_webhook = dingtalkWebhook;
      if (wecomWebhook) body.wecom_webhook = wecomWebhook;
      fetch('/api/jenkins-manage/start', {
        method: 'POST',
        headers: _jmHeaders(true),
        credentials: 'same-origin',
        body: JSON.stringify(body),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (d) {
          if (d.success) {
            el.textContent = '已启动，实例 ID: ' + d.instance_id;
            el.className = 'mt-2 text-sm text-green-600';
            loadList();
          } else {
            el.textContent = d.error || '启动失败';
            el.className = 'mt-2 text-sm text-red-600';
          }
        })
        .catch(function () {
          el.textContent = '请求失败';
        });
    });
    _jmBindClick('btnDeployEnv', function () {
      var logEl = document.getElementById('deployLog');
      if (!logEl) return;
      logEl.classList.remove('hidden', 'is-hidden');
      logEl.textContent = '部署已开始，请稍候…';
      fetch('/api/jenkins-manage/deploy-env', {
        method: 'POST',
        headers: _jmHeaders(false),
        credentials: 'same-origin',
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (d) {
          if (d.log_path) {
            fetch('/api/jenkins-manage/deploy-log?path=' + encodeURIComponent(d.log_path), {
              credentials: 'same-origin',
            })
              .then(function (r) {
                return r.text();
              })
              .then(function (t) {
                logEl.textContent = t || '无输出';
                setInterval(function () {
                  fetch('/api/jenkins-manage/deploy-log?path=' + encodeURIComponent(d.log_path), {
                    credentials: 'same-origin',
                  })
                    .then(function (r) {
                      return r.text();
                    })
                    .then(function (t) {
                      logEl.textContent = t || '无输出';
                      logEl.scrollTop = logEl.scrollHeight;
                    });
                }, 2000);
              });
          } else {
            logEl.textContent = d.error || '执行失败';
          }
        })
        .catch(function () {
          logEl.textContent = '请求失败';
        });
    });
  }

  var _TAB_HASH = {
    list: 'jm-list',
    start: 'jm-start',
    unity: 'unity-catalog',
    env: 'jm-env',
  };
  var _HASH_TAB = {
    'jm-list': 'list',
    list: 'list',
    'jm-start': 'start',
    start: 'start',
    'unity-catalog': 'unity',
    unity: 'unity',
    'jm-env': 'env',
    env: 'env',
  };

  function showJmTab(tab) {
    var key = _HASH_TAB[tab] || tab || 'list';
    if (!_TAB_HASH[key]) key = 'list';
    var root = document.querySelector('[data-jm-page]');
    if (!root) return;
    root.querySelectorAll('[data-jm-tab]').forEach(function (btn) {
      var on = btn.getAttribute('data-jm-tab') === key;
      btn.classList.toggle('is-active', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    root.querySelectorAll('[data-jm-panel]').forEach(function (panel) {
      var on = panel.getAttribute('data-jm-panel') === key;
      panel.classList.toggle('is-active', on);
      if (on) panel.removeAttribute('hidden');
      else panel.setAttribute('hidden', '');
    });
    var hash = _TAB_HASH[key];
    if (hash && location.hash.replace(/^#/, '') !== hash) {
      try {
        history.replaceState(null, '', '#' + hash);
      } catch (e) {
        location.hash = hash;
      }
    }
  }

  function bindJmTabs() {
    var root = document.querySelector('[data-jm-page]');
    if (!root) return;
    root.querySelectorAll('[data-jm-tab]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        showJmTab(btn.getAttribute('data-jm-tab'));
      });
    });
    root.querySelectorAll('[data-jm-goto]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        showJmTab(btn.getAttribute('data-jm-goto'));
      });
    });
    window.addEventListener('hashchange', function () {
      var h = (location.hash || '').replace(/^#/, '');
      if (h) showJmTab(h);
    });
    var initial = (location.hash || '').replace(/^#/, '');
    showJmTab(initial || 'list');
  }

  function init() {
    bindJmTabs();
    bindEvents();
    loadList();
  }

  global.filterList = filterList;
  global.startInstance = startInstance;
  global.stopInstance = stopInstance;
  global.deleteInstance = deleteInstance;
  global.showJmTab = showJmTab;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(typeof window !== 'undefined' ? window : this);
