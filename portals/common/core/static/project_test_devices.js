(function () {
  "use strict";

  var root = document.querySelector('[data-delivery-page="test-devices"]');
  if (!root) return;

  var projectId = root.getAttribute("data-project-id") || "";
  var canEdit = root.getAttribute("data-can-edit") === "1";
  var devices = [];
  var editingId = "";

  var STAGE_LABELS = { dev: "开发", test: "测试", production: "线上" };
  var PLATFORM_LABELS = { android: "Android", ios: "iOS" };

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function toast(msg, isError) {
    if (window.opsToast) window.opsToast(msg, isError ? "error" : "success");
    else alert(msg);
  }

  function api(path, options) {
    options = options || {};
    return fetch(path, Object.assign({ credentials: "same-origin" }, options)).then(function (r) {
      return r.json().then(function (d) {
        return { ok: r.ok, data: d };
      });
    });
  }

  function renderRows() {
    var tbody = root.querySelector("[data-td-rows]");
    var count = root.querySelector("[data-td-count]");
    if (!tbody) return;
    if (count) count.textContent = "共 " + devices.length + " 台";
    if (!devices.length) {
      tbody.innerHTML = '<tr><td colspan="6">暂无测试设备，点击「添加设备」绑定 device_id 与阶段。</td></tr>';
      return;
    }
    tbody.innerHTML = devices
      .map(function (row) {
        var actions = canEdit
          ? '<button type="button" class="pm-btn pm-btn--compact" data-td-edit="' +
            esc(row.id) +
            '">编辑</button><button type="button" class="pm-btn pm-btn--compact" data-td-delete="' +
            esc(row.id) +
            '">删除</button>'
          : '<span class="pm-tag pm-tag--muted">只读</span>';
        return (
          "<tr>" +
          "<td><code>" +
          esc(row.device_id) +
          "</code></td>" +
          "<td>" +
          esc(row.label || "-") +
          "</td>" +
          "<td>" +
          esc(PLATFORM_LABELS[row.platform] || row.platform || "android") +
          "</td>" +
          "<td>" +
          esc(STAGE_LABELS[row.stage] || row.stage || "dev") +
          "</td>" +
          "<td>" +
          esc((row.notes || "").slice(0, 40) || "-") +
          "</td>" +
          "<td class=\"pm-table-actions\">" +
          actions +
          "</td></tr>"
        );
      })
      .join("");
    tbody.querySelectorAll("[data-td-edit]").forEach(function (btn) {
      btn.onclick = function () {
        openModal(btn.getAttribute("data-td-edit"));
      };
    });
    tbody.querySelectorAll("[data-td-delete]").forEach(function (btn) {
      btn.onclick = function () {
        removeDevice(btn.getAttribute("data-td-delete"));
      };
    });
  }

  function loadDevices() {
    var tbody = root.querySelector("[data-td-rows]");
    if (tbody) tbody.innerHTML = '<tr><td colspan="6">加载中…</td></tr>';
    return api("/api/admin/projects/" + encodeURIComponent(projectId) + "/test-devices").then(function (res) {
      if (!res.ok || res.data.error) throw new Error(res.data.error || "加载失败");
      devices = res.data.devices || [];
      renderRows();
    });
  }

  function openModal(recordId) {
    editingId = recordId || "";
    var modal = root.querySelector("[data-td-modal]");
    var row = devices.find(function (x) {
      return x.id === recordId;
    });
    root.querySelector("[data-td-device-id]").value = (row && row.device_id) || "";
    root.querySelector("[data-td-label]").value = (row && row.label) || "";
    root.querySelector("[data-td-platform]").value = (row && row.platform) || "android";
    root.querySelector("[data-td-stage]").value = (row && row.stage) || "dev";
    root.querySelector("[data-td-notes]").value = (row && row.notes) || "";
    root.querySelector("[data-td-modal-title]").textContent = editingId ? "编辑测试设备" : "添加测试设备";
    if (modal) modal.classList.remove("is-hidden");
  }

  function closeModal() {
    editingId = "";
    var modal = root.querySelector("[data-td-modal]");
    if (modal) modal.classList.add("is-hidden");
  }

  function saveDevice() {
    var payload = {
      id: editingId,
      device_id: root.querySelector("[data-td-device-id]").value.trim(),
      label: root.querySelector("[data-td-label]").value.trim(),
      platform: root.querySelector("[data-td-platform]").value,
      stage: root.querySelector("[data-td-stage]").value,
      notes: root.querySelector("[data-td-notes]").value.trim(),
    };
    if (!payload.device_id) {
      toast("设备 ID 不能为空", true);
      return;
    }
    api("/api/admin/projects/" + encodeURIComponent(projectId) + "/test-devices", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function (res) {
      if (!res.ok || res.data.error) throw new Error(res.data.error || "保存失败");
      closeModal();
      toast("已保存");
      loadDevices();
    }).catch(function (err) {
      toast(err.message || "保存失败", true);
    });
  }

  function removeDevice(recordId) {
    if (!recordId || !confirm("确定删除该测试设备？")) return;
    api(
      "/api/admin/projects/" + encodeURIComponent(projectId) + "/test-devices/" + encodeURIComponent(recordId),
      { method: "DELETE" }
    ).then(function (res) {
      if (!res.ok || res.data.error) throw new Error(res.data.error || "删除失败");
      toast("已删除");
      loadDevices();
    }).catch(function (err) {
      toast(err.message || "删除失败", true);
    });
  }

  var addBtn = root.querySelector("[data-td-add]");
  if (addBtn && canEdit) addBtn.onclick = function () {
    openModal("");
  };
  var refreshBtn = root.querySelector("[data-td-refresh]");
  if (refreshBtn) refreshBtn.onclick = loadDevices;
  var saveBtn = root.querySelector("[data-td-save]");
  if (saveBtn) saveBtn.onclick = saveDevice;
  var cancelBtn = root.querySelector("[data-td-cancel]");
  if (cancelBtn) cancelBtn.onclick = closeModal;
  var modal = root.querySelector("[data-td-modal]");
  if (modal) {
    modal.addEventListener("click", function (e) {
      if (e.target === modal) closeModal();
    });
  }

  loadDevices().catch(function (err) {
    var tbody = root.querySelector("[data-td-rows]");
    if (tbody) tbody.innerHTML = '<tr><td colspan="6">' + esc(err.message) + "</td></tr>";
  });
})();
