/**
 * Jenkins 管理 - Unity 版本库（有效/失效、分类、备注）
 */
(function (global) {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function headersJson() {
    var t = document.querySelector('meta[name="csrf-token"]');
    var h = { 'Content-Type': 'application/json' };
    if (t && t.content) h['X-CSRFToken'] = t.content;
    return h;
  }

  function setStatus(el, text, isErr) {
    if (!el) return;
    el.textContent = text || '';
    el.className = 'text-sm mt-2 ' + (isErr ? 'text-red-600' : 'text-green-600');
  }

  var state = { filterStatus: 'all', filterCategory: '', categories: [], entries: [] };

  function filteredEntries() {
    return state.entries.filter(function (e) {
      if (state.filterStatus === 'active' && e.status !== 'active') return false;
      if (state.filterStatus === 'inactive' && e.status !== 'inactive') return false;
      if (state.filterCategory && e.category !== state.filterCategory) return false;
      return true;
    });
  }

  function renderTable() {
    var tb = document.getElementById('uvCatalogTableBody');
    var st = document.getElementById('uvCatalogListStatus');
    if (!tb) return;
    var rows = filteredEntries();
    if (!rows.length) {
      tb.innerHTML =
        '<tr><td colspan="6" class="px-3 py-4 text-gray-500 text-center">暂无记录，请添加或从本机检测导入</td></tr>';
      if (st) setStatus(st, '共 0 条', false);
      return;
    }
    tb.innerHTML = rows
      .map(function (e) {
        var statusBadge =
          e.status === 'active'
            ? '<span class="text-green-700 bg-green-50 px-1.5 py-0.5 rounded text-xs">有效</span>'
            : '<span class="text-gray-600 bg-gray-100 px-1.5 py-0.5 rounded text-xs">失效</span>';
        return (
          '<tr class="border-t border-gray-100">' +
          '<td class="px-2 py-2 font-mono text-xs">' +
          esc(e.version) +
          '</td>' +
          '<td class="px-2 py-2 text-xs">' +
          esc(e.category || '') +
          '</td>' +
          '<td class="px-2 py-2">' +
          statusBadge +
          '</td>' +
          '<td class="px-2 py-2 text-xs text-gray-600 max-w-[200px] truncate" title="' +
          esc(e.note || '') +
          '">' +
          esc(e.note || '-') +
          '</td>' +
          '<td class="px-2 py-2 text-[10px] text-gray-500 break-all max-w-[220px]">' +
          esc(e.path || '-') +
          '</td>' +
          '<td class="px-2 py-2 whitespace-nowrap">' +
          '<button type="button" class="text-indigo-600 hover:underline text-xs uv-edit" data-id="' +
          esc(e.id) +
          '">编辑</button> ' +
          '<button type="button" class="text-gray-600 hover:underline text-xs uv-toggle" data-id="' +
          esc(e.id) +
          '" data-status="' +
          (e.status === 'active' ? 'inactive' : 'active') +
          '">' +
          (e.status === 'active' ? '设为失效' : '设为有效') +
          '</button>' +
          '</td></tr>'
        );
      })
      .join('');
    if (st) setStatus(st, '显示 ' + rows.length + ' / 共 ' + state.entries.length + ' 条', false);
  }

  function fillCategorySelects() {
    var opts =
      '<option value="">全部分类</option>' +
      state.categories
        .map(function (c) {
          return '<option value="' + esc(c) + '">' + esc(c) + '</option>';
        })
        .join('');
    var fc = document.getElementById('uvFilterCategory');
    var fcForm = document.getElementById('uvFormCategory');
    var dl = document.getElementById('uvCategoryDatalist');
    if (fc) {
      var prev = fc.value;
      fc.innerHTML = opts;
      fc.value = prev || '';
    }
    if (dl) {
      dl.innerHTML = state.categories
        .map(function (c) {
          return '<option value="' + esc(c) + '"></option>';
        })
        .join('');
    }
    if (fcForm && !fcForm.value && state.categories.length) {
      fcForm.placeholder = '如 ' + state.categories[0];
    }
  }

  function loadCatalog() {
    var st = document.getElementById('uvCatalogListStatus');
    if (st) setStatus(st, '加载中…', false);
    return fetch('/api/jenkins-manage/unity-catalog', { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (d) {
        state.entries = (d && d.entries) || [];
        state.categories = (d && d.categories) || [];
        fillCategorySelects();
        renderTable();
      })
      .catch(function (e) {
        if (st) setStatus(st, '加载失败：' + (e.message || ''), true);
      });
  }

  function saveEntry(payload, entryId) {
    var url = entryId
      ? '/api/jenkins-manage/unity-catalog/' + encodeURIComponent(entryId)
      : '/api/jenkins-manage/unity-catalog';
    var method = entryId ? 'PUT' : 'POST';
    return fetch(url, {
      method: method,
      headers: headersJson(),
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    }).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok || !d.success) throw new Error((d && d.error) || '保存失败');
        return d;
      });
    });
  }

  function openForm(entry) {
    var panel = document.getElementById('uvFormPanel');
    if (!panel) return;
    panel.classList.remove('hidden');
    document.getElementById('uvFormEntryId').value = (entry && entry.id) || '';
    document.getElementById('uvFormVersion').value = (entry && entry.version) || '';
    document.getElementById('uvFormPath').value = (entry && entry.path) || '';
    document.getElementById('uvFormCategory').value = (entry && entry.category) || state.categories[0] || '其他';
    document.getElementById('uvFormStatus').value = (entry && entry.status) || 'active';
    document.getElementById('uvFormNote').value = (entry && entry.note) || '';
    document.getElementById('uvFormTitle').textContent = entry ? '编辑 Unity 版本' : '新增 Unity 版本';
    if (entry) document.getElementById('uvFormVersion').readOnly = false;
  }

  function closeForm() {
    var panel = document.getElementById('uvFormPanel');
    if (panel) panel.classList.add('hidden');
  }

  function bindEvents() {
    var root = document.getElementById('unity-catalog');
    if (!root) return;

    document.getElementById('uvBtnReload').onclick = loadCatalog;

    document.getElementById('uvBtnAdd').onclick = function () {
      openForm(null);
    };

    document.getElementById('uvBtnImportDetect').onclick = function () {
      var btn = document.getElementById('uvBtnImportDetect');
      var st = document.getElementById('uvCatalogListStatus');
      if (btn) btn.disabled = true;
      if (st) setStatus(st, '正在检测本机并导入…', false);
      fetch('/api/jenkins-manage/unity-catalog/import-detected', {
        method: 'POST',
        headers: headersJson(),
        credentials: 'same-origin',
        body: JSON.stringify({ as_active: true }),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (d) {
          if (!d.success) throw new Error(d.error || '导入失败');
          if (st)
            setStatus(
              st,
              '导入完成：新增 ' + (d.added_count || 0) + ' 条，本机检测到 ' + (d.detected_count || 0) + ' 个',
              false
            );
          return loadCatalog();
        })
        .catch(function (e) {
          if (st) setStatus(st, '导入失败：' + (e.message || ''), true);
        })
        .finally(function () {
          if (btn) btn.disabled = false;
        });
    };

    document.getElementById('uvFilterStatus').onchange = function () {
      state.filterStatus = this.value || 'all';
      renderTable();
    };
    document.getElementById('uvFilterCategory').onchange = function () {
      state.filterCategory = this.value || '';
      renderTable();
    };

    document.getElementById('uvFormCancel').onclick = closeForm;
    document.getElementById('uvFormSave').onclick = function () {
      var id = document.getElementById('uvFormEntryId').value.trim();
      var payload = {
        version: document.getElementById('uvFormVersion').value.trim(),
        path: document.getElementById('uvFormPath').value.trim(),
        category: document.getElementById('uvFormCategory').value.trim(),
        status: document.getElementById('uvFormStatus').value,
        note: document.getElementById('uvFormNote').value.trim(),
      };
      var st = document.getElementById('uvFormStatusMsg');
      if (!payload.version) {
        setStatus(st, '请填写版本号', true);
        return;
      }
      setStatus(st, '保存中…', false);
      saveEntry(payload, id || null)
        .then(function () {
          setStatus(st, '已保存', false);
          closeForm();
          return loadCatalog();
        })
        .catch(function (e) {
          setStatus(st, e.message || '保存失败', true);
        });
    };

    root.addEventListener('click', function (ev) {
      var editBtn = ev.target.closest('.uv-edit');
      if (editBtn) {
        var id = editBtn.getAttribute('data-id');
        var entry = state.entries.find(function (x) {
          return x.id === id;
        });
        if (entry) openForm(entry);
        return;
      }
      var toggleBtn = ev.target.closest('.uv-toggle');
      if (toggleBtn) {
        var tid = toggleBtn.getAttribute('data-id');
        var newStatus = toggleBtn.getAttribute('data-status');
        saveEntry({ status: newStatus }, tid)
          .then(loadCatalog)
          .catch(function (e) {
            alert(e.message || '操作失败');
          });
      }
    });
  }

  function init() {
    bindEvents();
    loadCatalog();
    if (location.hash === '#unity-catalog') {
      var el = document.getElementById('unity-catalog');
      if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth' });
    }
  }

  global.JenkinsUnityCatalog = { init: init, loadCatalog: loadCatalog };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(typeof window !== 'undefined' ? window : this);
