(function () {
  "use strict";

  var root = document.querySelector("[data-activities-page]");
  if (!root) return;

  var projectId = root.getAttribute("data-project-id") || "";
  var STANDARD_ENVS = ["development", "testing", "staging", "production"];
  var activeTab = "all";

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function toast(msg, type) {
    if (window.opsToast) window.opsToast(msg, type);
    else if (type === "error") alert(msg);
  }

  function filterParams() {
    var env = document.getElementById("activitiesFilterEnv");
    var channel = document.getElementById("activitiesFilterChannel");
    var platform = document.getElementById("activitiesFilterPlatform");
    return {
      env_key: env ? env.value : "",
      channel_id: channel ? channel.value : "",
      platform: platform ? platform.value : "",
    };
  }

  function syncQuery(extra) {
    var p = new URLSearchParams();
    Object.entries(extra || filterParams()).forEach(function (pair) {
      if (pair[1]) p.set(pair[0], pair[1]);
    });
    if (activeTab && activeTab !== "all") p.set("tab", activeTab);
    var text = p.toString();
    history.replaceState(null, "", text ? "?" + text : location.pathname);
  }

  async function api(path) {
    var r = await fetch(path, { credentials: "same-origin" });
    var ct = r.headers.get("content-type") || "";
    if (!ct.includes("application/json")) throw new Error("请求失败 (" + r.status + ")");
    var d = await r.json();
    if (!d.ok) throw new Error((d.error && (d.error.message || d.error)) || "加载失败");
    return d.data;
  }

  function renderActivities(items) {
    var host = document.getElementById("activitiesList");
    var count = document.getElementById("activitiesCount");
    if (!host) return;
    if (count) count.textContent = String(items.length) + " 条";
    host.innerHTML = items.length
      ? items
          .map(function (item) {
            return (
              '<a class="p02-activity-item" href="' +
              esc(item.href) +
              '"><span class="p02-activity-dot ' +
              esc(item.kind) +
              '"></span><span class="p02-activity-type ' +
              esc(item.kind) +
              '">' +
              esc(item.type_label || item.typeLabel || item.kind) +
              '</span><div class="p02-activity-body"><strong>' +
              esc(item.title) +
              '</strong></div><span class="p02-activity-meta">' +
              esc(item.actor || "系统") +
              " · " +
              esc(item.time || item.time_short || "") +
              "</span></a>"
            );
          })
          .join("")
      : '<div class="p02-empty">暂无动态</div>';
  }

  function populateFilters(data) {
    var filters = filterParams();
    var envSelect = document.getElementById("activitiesFilterEnv");
    var channelSelect = document.getElementById("activitiesFilterChannel");
    var platformSelect = document.getElementById("activitiesFilterPlatform");
    var envOptions = (data.environment_options || []).filter(function (row) {
      return STANDARD_ENVS.indexOf(String(row.env_key || "").toLowerCase()) >= 0;
    });
    if (envSelect) {
      envSelect.innerHTML =
        '<option value="">全部环境</option>' +
        envOptions
          .map(function (row) {
            return (
              '<option value="' +
              esc(row.env_key) +
              '">' +
              esc(row.env_label || row.env_key) +
              "</option>"
            );
          })
          .join("");
      envSelect.value = filters.env_key || envSelect.value;
    }
    if (channelSelect) {
      var channels = data.channel_options || [];
      channelSelect.innerHTML =
        '<option value="">全部渠道</option>' +
        channels
          .map(function (row) {
            return (
              '<option value="' +
              esc(row.channel_id || row.id) +
              '">' +
              esc(row.channel_label || row.name || row.channel_id) +
              "</option>"
            );
          })
          .join("");
      channelSelect.value = filters.channel_id || "";
    }
    if (platformSelect) {
      var platforms = data.platform_options || [];
      platformSelect.innerHTML =
        '<option value="">多平台</option>' +
        platforms
          .map(function (row) {
            return (
              '<option value="' +
              esc(row.platform_id || row.id) +
              '">' +
              esc(row.platform_label || row.name || row.platform_id) +
              "</option>"
            );
          })
          .join("");
      platformSelect.value = filters.platform || "";
    }
  }

  function buildActivitiesUrl() {
    var p = new URLSearchParams();
    var filters = filterParams();
    Object.entries(filters).forEach(function (pair) {
      if (pair[1]) p.set(pair[0], pair[1]);
    });
    if (activeTab && activeTab !== "all") p.set("kind", activeTab);
    p.set("limit", "200");
    return "/api/projects/" + encodeURIComponent(projectId) + "/activities?" + p.toString();
  }

  async function loadActivities() {
    var updated = document.getElementById("activitiesUpdatedAt");
    try {
      var overview = await api("/api/projects/" + encodeURIComponent(projectId) + "/overview?" + new URLSearchParams(filterParams()).toString());
      populateFilters(overview);
      var data = await api(buildActivitiesUrl());
      renderActivities(data.activities || []);
      if (updated) updated.textContent = new Date().toLocaleTimeString();
      syncQuery();
    } catch (err) {
      renderActivities([]);
      toast(err.message || "加载动态失败", "error");
    }
  }

  function initTabs() {
    var params = new URLSearchParams(location.search);
    activeTab = params.get("tab") || params.get("kind") || "all";
    document.querySelectorAll(".p02-activity-tab[data-activity-tab]").forEach(function (btn) {
      var tab = btn.getAttribute("data-activity-tab") || "all";
      btn.classList.toggle("active", tab === activeTab);
      btn.addEventListener("click", function () {
        activeTab = tab;
        document.querySelectorAll(".p02-activity-tab[data-activity-tab]").forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        loadActivities();
      });
    });
  }

  function bindFilters() {
    ["activitiesFilterEnv", "activitiesFilterChannel", "activitiesFilterPlatform"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("change", loadActivities);
    });
    var refresh = document.querySelector("[data-refresh-activities]");
    if (refresh) refresh.addEventListener("click", loadActivities);
  }

  initTabs();
  bindFilters();
  loadActivities();
})();
