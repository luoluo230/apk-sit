(function () {
  "use strict";

  var root = document.querySelector('[data-delivery-page="casual-services"]');
  if (!root) return;

  var projectId = root.dataset.projectId || "";
  var serviceId = root.dataset.serviceId || "";
  var canEdit = root.dataset.canEdit === "true";
  var catalog = [];
  try {
    catalog = JSON.parse(document.getElementById("baasCatalogJson").textContent || "[]");
  } catch (e) {
    catalog = [];
  }

  var state = { service: null, activeKey: "login" };
  var toast = window.DeliveryCommon && window.DeliveryCommon.toast
    ? window.DeliveryCommon.toast
    : function (msg) { alert(msg); };

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function csrfHeaders() {
    var token = document.querySelector('meta[name="csrf-token"]');
    return token && token.content ? { "X-CSRFToken": token.content } : {};
  }

  async function api(url, options) {
    var opts = options || {};
    var method = String(opts.method || "GET").toUpperCase();
    var headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    if (["POST", "PUT", "PATCH", "DELETE"].indexOf(method) >= 0) {
      Object.assign(headers, csrfHeaders());
    }
    var response = await fetch(url, {
      method: method,
      headers: headers,
      credentials: "same-origin",
      body: opts.body,
    });
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok || data.ok === false) throw new Error(data.error || "请求失败");
    return data.data !== undefined ? data.data : data;
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast("已复制", "success"); }).catch(function () { toast("复制失败", "error"); });
      return;
    }
    toast(text, "success");
  }

  function groupLabel(group) {
    var map = { core: "核心", retention: "留存", social: "社交", compliance: "合规", pvp: "PVP" };
    return map[group] || group;
  }

  function renderNav() {
    var nav = document.getElementById("baasFeatureNav");
    if (!nav) return;
    var flags = (state.service && state.service.feature_flags) || {};
    var groups = {};
    catalog.forEach(function (item) {
      var g = item.group || "core";
      if (!groups[g]) groups[g] = [];
      groups[g].push(item);
    });
    var html = "";
    Object.keys(groups).forEach(function (group) {
      html += '<div class="baas-nav-group">' + esc(groupLabel(group)) + "</div>";
      groups[group].forEach(function (item) {
        var active = item.key === state.activeKey ? " is-active" : "";
        var on = flags[item.key] ? "开" : "关";
        html += (
          '<button type="button" class="baas-nav-item' + active + '" data-feature-key="' + esc(item.key) + '">' +
          "<span>" + esc(item.label) + "</span>" +
          '<span class="baas-phase">P' + esc(item.phase) + " · " + on + "</span></button>"
        );
      });
    });
    nav.innerHTML = html;
    nav.querySelectorAll("[data-feature-key]").forEach(function (btn) {
      btn.onclick = function () {
        state.activeKey = btn.getAttribute("data-feature-key");
        renderNav();
        renderPanel();
      };
    });
  }

  function configFields(key, cfg) {
    cfg = cfg || {};
    if (key === "login") {
      return (
        '<label class="baas-toggle"><input type="checkbox" data-cfg="guest_login_enabled"' + (cfg.guest_login_enabled !== false ? " checked" : "") + (canEdit ? "" : " disabled") + "> 游客登录</label>" +
        '<label class="baas-toggle"><input type="checkbox" data-cfg="password_login_enabled"' + (cfg.password_login_enabled !== false ? " checked" : "") + (canEdit ? "" : " disabled") + "> 账号密码登录</label>" +
        '<label><span>Token TTL（小时）</span><input type="number" data-cfg="token_ttl_hours" value="' + esc(cfg.token_ttl_hours != null ? cfg.token_ttl_hours : 168) + '"' + (canEdit ? "" : " disabled") + "></label>"
      );
    }
    if (key === "announce") {
      return '<label class="wide"><span>受众</span><input type="text" data-cfg="audience" value="' + esc(cfg.audience || "all") + '"' + (canEdit ? "" : " disabled") + "></label>";
    }
    if (key === "mail") {
      return (
        '<label><span>收件箱上限</span><input type="number" data-cfg="max_inbox" value="' + esc(cfg.max_inbox != null ? cfg.max_inbox : 100) + '"' + (canEdit ? "" : " disabled") + "></label>" +
        '<label><span>过期天数</span><input type="number" data-cfg="expire_days" value="' + esc(cfg.expire_days != null ? cfg.expire_days : 30) + '"' + (canEdit ? "" : " disabled") + "></label>"
      );
    }
    if (key === "cloudsave") {
      return (
        '<label><span>每玩家 Key 上限</span><input type="number" data-cfg="max_keys_per_player" value="' + esc(cfg.max_keys_per_player != null ? cfg.max_keys_per_player : 32) + '"' + (canEdit ? "" : " disabled") + "></label>" +
        '<label><span>单值最大字节</span><input type="number" data-cfg="max_value_bytes" value="' + esc(cfg.max_value_bytes != null ? cfg.max_value_bytes : 65536) + '"' + (canEdit ? "" : " disabled") + "></label>"
      );
    }
    return '<label class="wide"><span>配置 JSON</span><textarea data-cfg-json rows="8"' + (canEdit ? "" : " disabled") + ">" + esc(JSON.stringify(cfg, null, 2)) + "</textarea></label>";
  }

  function renderPanel() {
    var panel = document.getElementById("baasFeaturePanel");
    if (!panel || !state.service) return;
    var item = catalog.find(function (row) { return row.key === state.activeKey; }) || catalog[0];
    if (!item) {
      panel.innerHTML = '<div class="baas-panel-empty">暂无功能模块</div>';
      return;
    }
    var flags = state.service.feature_flags || {};
    var cfg = (state.service.feature_configs || {})[item.key] || {};
    var enabled = !!flags[item.key];
    panel.innerHTML = (
      '<div class="baas-panel-head">' +
      "<div><h2>" + esc(item.label) + "</h2><p>Phase " + esc(item.phase) + " · REST 公共 API</p></div>" +
      '<label class="baas-toggle"><input type="checkbox" id="baasFeatureEnabled"' + (enabled ? " checked" : "") + (canEdit ? "" : " disabled") + "> 启用模块</label></div>" +
      '<div class="baas-form-grid" id="baasConfigForm">' + configFields(item.key, cfg) + "</div>" +
      (item.key === "announce" ? '<div class="baas-list" id="baasAnnounceList"><h3>公告列表</h3><div class="baas-panel-empty">加载中...</div></div>' : "") +
      (item.key === "mail" ? '<div class="baas-list" id="baasMailList"><h3>最近邮件</h3><div class="baas-panel-empty">加载中...</div></div>' : "")
    );
    if (item.key === "announce") loadAnnouncements();
    if (item.key === "mail") loadMail();
  }

  async function loadAnnouncements() {
    var host = document.getElementById("baasAnnounceList");
    if (!host) return;
    try {
      var rows = await api("/api/projects/" + encodeURIComponent(projectId) + "/baas/services/" + encodeURIComponent(serviceId) + "/announcements");
      if (!rows || !rows.length) {
        host.innerHTML = "<h3>公告列表</h3><div class=\"baas-panel-empty\">暂无公告</div>";
        return;
      }
      host.innerHTML = "<h3>公告列表</h3>" + rows.map(function (row) {
        return '<div class="baas-list-row"><span><b>' + esc(row.title || "") + "</b> · " + esc(row.status || "") + "</span><span>" + esc(row.effective_at || "") + "</span></div>";
      }).join("");
    } catch (e) {
      host.innerHTML = "<h3>公告列表</h3><div class=\"baas-panel-empty\">" + esc(e.message) + "</div>";
    }
  }

  async function loadMail() {
    var host = document.getElementById("baasMailList");
    if (!host) return;
    try {
      var rows = await api("/api/projects/" + encodeURIComponent(projectId) + "/baas/services/" + encodeURIComponent(serviceId) + "/mail");
      if (!rows || !rows.length) {
        host.innerHTML = "<h3>最近邮件</h3><div class=\"baas-panel-empty\">暂无邮件</div>";
        return;
      }
      host.innerHTML = "<h3>最近邮件</h3>" + rows.slice(0, 10).map(function (row) {
        return '<div class="baas-list-row"><span><b>' + esc(row.subject || row.title || "") + "</b></span><span>" + esc(row.created_at || "") + "</span></div>";
      }).join("");
    } catch (e) {
      host.innerHTML = "<h3>最近邮件</h3><div class=\"baas-panel-empty\">" + esc(e.message) + "</div>";
    }
  }

  function readConfigForm(key) {
    var form = document.getElementById("baasConfigForm");
    if (!form) return {};
    var jsonArea = form.querySelector("[data-cfg-json]");
    if (jsonArea) {
      try { return JSON.parse(jsonArea.value || "{}"); } catch (e) { throw new Error("配置 JSON 无效"); }
    }
    var cfg = {};
    form.querySelectorAll("[data-cfg]").forEach(function (el) {
      var k = el.getAttribute("data-cfg");
      if (el.type === "checkbox") cfg[k] = el.checked;
      else if (el.type === "number") cfg[k] = Number(el.value);
      else cfg[k] = el.value;
    });
    return cfg;
  }

  async function loadService() {
    var env = document.getElementById("baasEnvSelect");
    var envKey = env ? env.value : root.dataset.envKey || "development";
    var data = await api("/api/projects/" + encodeURIComponent(projectId) + "/baas/services/" + encodeURIComponent(serviceId) + "?env_key=" + encodeURIComponent(envKey));
    state.service = data;
    serviceId = data.service_id || serviceId;
    root.dataset.serviceId = serviceId;
    var cfgNode = document.getElementById("baasConfigId");
    if (cfgNode) cfgNode.textContent = serviceId;
    renderNav();
    renderPanel();
  }

  async function saveService() {
    var enabledEl = document.getElementById("baasFeatureEnabled");
    var flags = Object.assign({}, state.service.feature_flags || {});
    if (enabledEl) flags[state.activeKey] = enabledEl.checked;
    var configs = Object.assign({}, state.service.feature_configs || {});
    configs[state.activeKey] = readConfigForm(state.activeKey);
    var payload = { feature_flags: flags, feature_configs: configs };
    var updated = await api("/api/projects/" + encodeURIComponent(projectId) + "/baas/services/" + encodeURIComponent(serviceId), {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    state.service = updated;
    toast("配置已保存", "success");
    renderNav();
  }

  async function rotateSecret() {
    var data = await api("/api/projects/" + encodeURIComponent(projectId) + "/baas/services/" + encodeURIComponent(serviceId) + "/rotate-secret", { method: "POST", body: "{}" });
    if (data.api_secret) showSecret(data.api_secret);
  }

  function showSecret(secret) {
    var banner = document.getElementById("baasSecretBanner");
    var val = document.getElementById("baasSecretValue");
    if (!banner || !val) return;
    val.textContent = secret;
    banner.classList.remove("is-hidden");
  }

  var envSelect = document.getElementById("baasEnvSelect");
  if (envSelect) {
    envSelect.value = root.dataset.envKey || "development";
    envSelect.onchange = function () {
      var url = "/admin/projects/" + encodeURIComponent(projectId) + "/casual-services/" + encodeURIComponent(serviceId) + "?env_key=" + encodeURIComponent(envSelect.value);
      location.href = url;
    };
  }

  var saveBtn = document.getElementById("baasSaveBtn");
  if (saveBtn) saveBtn.onclick = function () { saveService().catch(function (e) { toast(e.message, "error"); }); };
  var rotateBtn = document.getElementById("baasRotateSecretBtn");
  if (rotateBtn) rotateBtn.onclick = function () { rotateSecret().catch(function (e) { toast(e.message, "error"); }); };
  var copyCfg = document.getElementById("baasCopyConfigId");
  if (copyCfg) copyCfg.onclick = function () { copyText(serviceId); };
  var copyBoot = document.getElementById("baasCopyBootstrap");
  if (copyBoot) copyBoot.onclick = function () { copyText("/api/public/baas-bootstrap?game_id=&game_key=&env=" + (envSelect ? envSelect.value : "development") + "&service_id=" + serviceId); };
  var copySecret = document.getElementById("baasCopySecret");
  if (copySecret) copySecret.onclick = function () { copyText(document.getElementById("baasSecretValue").textContent || ""); };
  var dismissSecret = document.getElementById("baasDismissSecret");
  if (dismissSecret) dismissSecret.onclick = function () { document.getElementById("baasSecretBanner").classList.add("is-hidden"); };

  loadService().catch(function (e) {
    var panel = document.getElementById("baasFeaturePanel");
    if (panel) panel.innerHTML = '<div class="baas-panel-empty">' + esc(e.message) + "</div>";
  });
})();
