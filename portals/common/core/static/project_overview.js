(function () {
  "use strict";

  var root = document.querySelector("[data-overview-page]");
  if (!root) return;

  window.__P02_OVERVIEW__ = true;

  var projectId = root.getAttribute("data-project-id") || "";
  var memberCount = Number(root.getAttribute("data-member-count") || 0);
  var STANDARD_ENVS = ["development", "testing", "staging", "production"];
  var activityEvents = [];

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
    var p = new URLSearchParams(location.search);
    return {
      env_key: p.get("env_key") || "",
      channel_id: p.get("channel_id") || "",
      platform: p.get("platform") || "",
    };
  }

  function queryString(extra) {
    var p = new URLSearchParams();
    var tab = new URLSearchParams(location.search).get("tab");
    if (tab) p.set("tab", tab);
    Object.entries(extra || filterParams()).forEach(function (pair) {
      if (pair[1]) p.set(pair[0], pair[1]);
    });
    var text = p.toString();
    return text ? "?" + text : "";
  }

  async function api(path) {
    var r = await fetch(path, { credentials: "same-origin" });
    var ct = r.headers.get("content-type") || "";
    if (!ct.includes("application/json")) throw new Error("请求失败 (" + r.status + ")");
    var d = await r.json();
    if (!d.ok) throw new Error((d.error && (d.error.message || d.error)) || "加载失败");
    return d.data;
  }

  function envIconClass(envKey) {
    var k = String(envKey || "").toLowerCase();
    if (k === "production") return "prod";
    if (k === "staging") return "pre";
    if (k === "testing") return "test";
    return "dev";
  }

  function envIconFile(envKey) {
    var k = String(envKey || "").toLowerCase();
    if (k === "production") return "env_production.svg";
    if (k === "staging") return "env_staging.svg";
    if (k === "testing") return "env_testing.svg";
    return "env_development.svg";
  }

  function envShortKey(envKey) {
    var map = { development: "dev", testing: "test", staging: "pre", production: "prod" };
    return map[String(envKey || "").toLowerCase()] || String(envKey || "");
  }

  function formatPlatforms(platforms) {
    var labels = { android: "Android", ios: "iOS", windows: "Windows", webgl: "WebGL", macos: "macOS" };
    var list = (platforms || []).map(function (p) {
      return labels[String(p || "").toLowerCase()] || p;
    });
    return list.length ? list.join(" / ") : "多平台";
  }

  function healthPercent(item) {
    if (item.health === "unconfigured") return { text: "—", cls: "muted" };
    var total = item.delivery_line_count || 0;
    var ok = item.configured_line_count || 0;
    if (!total) return { text: "—", cls: "muted" };
    var pct = Math.round((100 * ok) / total);
    var cls = pct >= 95 ? "good" : pct >= 80 ? "warn" : "bad";
    return { text: pct + "%", cls: cls };
  }

  function renderKpis(data) {
    var host = document.getElementById("overviewKpis");
    if (!host) return;
    var k = data.kpis || {};
    var links = k.links || {};
    var versionText = k.current_version && k.current_version !== "—"
      ? (k.current_version_code ? k.current_version + " / " + k.current_version_code : k.current_version)
      : "—";
    var healthVal = k.service_health_pct == null ? "—" : String(k.service_health_pct) + "%";
    var kpis = [
      { icon: "kpi_version.svg", label: "当前版本", value: versionText, tone: "violet", href: links.version },
      { icon: "kpi_health.svg", label: "服务健康度", value: healthVal, tone: "green", href: links.health },
      { icon: "kpi_build.svg", label: "今日构建次数", value: String(k.today_build_count != null ? k.today_build_count : 0), tone: "violet", href: links.builds },
      { icon: "kpi_change.svg", label: "待处理变更", value: String(k.pending_changes != null ? k.pending_changes : 0), tone: "orange", href: links.changes },
      { icon: "kpi_member.svg", label: "项目成员", value: String(k.member_count != null ? k.member_count : memberCount), tone: "cyan", href: links.members },
    ];
    host.innerHTML = kpis.map(function (card) {
      var foot = card.href ? '<a class="pm-kpi-footlink" href="' + esc(card.href) + '">查看详情 &gt;</a>' : "";
      return (
        '<article class="pm-kpi-card">' +
        '<span class="pm-kpi-icon pm-kpi-icon--' + card.tone + '"><img src="/static/project_ui/svg/' + card.icon + '" alt=""></span>' +
        '<div class="pm-kpi-body"><span class="pm-kpi-label">' + esc(card.label) + '</span><div class="pm-kpi-value-row"><strong>' + esc(card.value) + "</strong></div>" + foot + "</div></article>"
      );
    }).join("");
  }

  function renderEnvCards(data, cards) {
    var host = document.getElementById("environmentCards");
    if (!host) return;
    var visible = cards.filter(function (item) {
      return STANDARD_ENVS.indexOf(String(item.env_key || "").toLowerCase()) >= 0;
    });
    if (!visible.length) {
      host.innerHTML = '<div class="p02-empty">—</div>';
      return;
    }
    host.innerHTML = visible
      .map(function (item) {
        var hp = healthPercent(item);
        var instances = (item.configured_line_count || 0) + " / " + (item.delivery_line_count || 0);
        var badgeClass =
          item.env_key === "production"
            ? "production"
            : item.health === "healthy" || item.health === "processing"
              ? "running"
              : item.health === "unconfigured"
                ? "muted"
                : "warning";
        var badgeText =
          item.env_key === "production"
            ? "生产"
            : item.health === "healthy" || item.health === "processing"
              ? "稳定"
              : item.health === "unconfigured"
                ? "未配置"
                : "预警";
        var iconCls = envIconClass(item.env_key);
        return (
          '<article class="p02-env-card">' +
          '<header class="p02-env-card-head">' +
          '<div class="p02-env-card-lead">' +
          '<span class="p02-env-card-icon p02-env-card-icon--' +
          iconCls +
          '"><img src="/static/project_ui/svg/' +
          envIconFile(item.env_key) +
          '" alt=""></span>' +
          '<div class="p02-env-card-names">' +
          "<h3>" +
          esc(item.env_label) +
          "</h3></div></div>" +
          '<span class="p02-env-badge ' +
          badgeClass +
          '">' +
          esc(badgeText) +
          "</span></header>" +
          '<div class="p02-env-metrics">' +
          '<div class="p02-env-kv"><span class="p02-env-kv__label">健康度</span><strong class="p02-env-kv__value health ' +
          hp.cls +
          '">' +
          esc(hp.text) +
          "</strong></div>" +
          '<div class="p02-env-kv p02-env-kv--instances"><span class="p02-env-kv__label">实例</span><strong class="p02-env-kv__value p02-env-kv__value--instances">' +
          esc(instances) +
          "</strong></div></div>" +
          '<footer class="p16-env-footer p02-env-footer"><a href="/admin/projects/' +
          encodeURIComponent(projectId) +
          "/environments/" +
          encodeURIComponent(item.env_key) +
          '">环境详情<img src="/static/project_ui/svg/action_next.svg" alt=""></a><a class="p02-env-runtime-link" href="/admin/projects/' +
          encodeURIComponent(projectId) +
          "/environments/" +
          encodeURIComponent(item.env_key) +
          '/runtime">运行工作台<img src="/static/project_ui/svg/action_next.svg" alt=""></a></footer></article>'
        );
      })
      .join("");
  }

  function renderActivity(tab) {
    var host = document.getElementById("overviewActivity");
    if (!host) return;
    var filtered =
      tab === "all" ? activityEvents : activityEvents.filter(function (item) {
        return item.kind === tab;
      });
    host.innerHTML = filtered.length
      ? filtered
          .map(function (item) {
            return (
              '<a class="p02-activity-item" href="' +
              esc(item.href) +
              '"><span class="p02-activity-dot ' +
              esc(item.kind) +
              '"></span><span class="p02-activity-type ' +
              esc(item.kind) +
              '">' +
              esc(item.typeLabel) +
              '</span><div class="p02-activity-body"><strong>' +
              esc(item.title) +
              '</strong></div><span class="p02-activity-meta">' +
              esc(item.time) +
              "</span></a>"
            );
          })
          .join("")
      : '<div class="p02-empty">—</div>';
  }

  function populateFilters(data) {
    var filters = filterParams();
    var envSelect = document.getElementById("filterEnvKey");
    var channelSelect = document.getElementById("overviewFilterChannel");
    var platformSelect = document.getElementById("filterPlatform");
    var envOptions = (data.environment_options || []).filter(function (row) {
      return STANDARD_ENVS.indexOf(String(row.env_key || "").toLowerCase()) >= 0;
    });
    var envHtml =
      '<option value="">全部环境</option>' +
      envOptions
        .map(function (row) {
          return '<option value="' + esc(row.env_key) + '">' + esc(row.env_label) + "</option>";
        })
        .join("");
    if (envSelect) {
      envSelect.innerHTML = envHtml;
      envSelect.value = filters.env_key;
    }
    if (channelSelect) {
      channelSelect.innerHTML =
        '<option value="">全部渠道</option>' +
        (data.channel_options || [])
          .map(function (row) {
            return '<option value="' + esc(row.channel_id) + '">' + esc(row.channel_name) + "</option>";
          })
          .join("");
      channelSelect.value = filters.channel_id;
    }
    if (platformSelect) {
      platformSelect.innerHTML =
        '<option value="">多平台</option>' +
        (data.platform_options || [])
          .map(function (row) {
            return '<option value="' + esc(row.value) + '">' + esc(row.label) + "</option>";
          })
          .join("");
      platformSelect.value = filters.platform;
    }
  }

  function bindFilters() {
    function apply() {
      var url = new URL(location.href);
      var fields = {
        env_key: document.getElementById("filterEnvKey"),
        channel_id: document.getElementById("overviewFilterChannel"),
        platform: document.getElementById("filterPlatform"),
      };
      Object.keys(fields).forEach(function (key) {
        var node = fields[key];
        var val = node && node.value ? node.value : "";
        if (val) url.searchParams.set(key, val);
        else url.searchParams.delete(key);
      });
      history.replaceState(null, "", url.pathname + url.search);
      loadOverview().catch(function (e) {
        toast(e.message, "error");
      });
    }
    ["filterEnvKey", "overviewFilterChannel", "filterPlatform"].forEach(function (id) {
      var node = document.getElementById(id);
      if (node) node.onchange = apply;
    });
  }

  function bindActivityTabs() {
    document.querySelectorAll(".p02-activity-tab[data-activity-tab]").forEach(function (btn) {
      btn.onclick = function () {
        document.querySelectorAll(".p02-activity-tab[data-activity-tab]").forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        renderActivity(btn.getAttribute("data-activity-tab") || "all");
      };
    });
  }

  async function loadOverview() {
    var data = await api("/api/projects/" + encodeURIComponent(projectId) + "/overview" + queryString());
    populateFilters(data);
    var activeChannelId = filterParams().channel_id || "";
    var cards = data.environments || [];
    var allOrders = cards.flatMap(function (item) {
      return item.latest_orders || [];
    });
    var sortedOrders = allOrders.slice().sort(function (a, b) {
      return String(b.updated_at).localeCompare(String(a.updated_at));
    });
    var latestOrder = sortedOrders[0];
    renderKpis(data);
    renderEnvCards(data, cards);
    activityEvents = (data.activities || []).map(function (item) {
      return {
        kind: item.kind || "release",
        typeLabel: item.type_label || item.typeLabel || "发布",
        title: item.title || "",
        actor: item.actor || "系统",
        time: item.time_short || String(item.time || "").slice(11, 16) || String(item.time || "").slice(0, 16),
        href: item.href || "#",
      };
    });
    var activeTab =
      document.querySelector(".p02-activity-tab.active")?.getAttribute("data-activity-tab") || "all";
    renderActivity(activeTab);
    var updated = document.getElementById("overviewUpdatedAt");
    if (updated) {
      updated.textContent = new Date()
        .toLocaleString("zh-CN", {
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        })
        .replace(/\//g, "-");
    }
  }

  function bindEnvViewToggle() {
    var track = document.getElementById("environmentCards");
    document.querySelectorAll("[data-env-view]").forEach(function (btn) {
      btn.onclick = function () {
        document.querySelectorAll("[data-env-view]").forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        if (track) track.classList.toggle("is-list", btn.getAttribute("data-env-view") === "list");
      };
    });
  }

  bindFilters();
  bindActivityTabs();
  bindEnvViewToggle();
  window.__P02_loadOverview = loadOverview;
  var refreshBtn = document.querySelector("[data-refresh-overview]");
  if (refreshBtn) {
    refreshBtn.onclick = function () {
      loadOverview().catch(function (e) {
        toast(e.message, "error");
      });
    };
  }

  var tab = new URLSearchParams(location.search).get("tab");
  if (tab) {
    root.classList.add("is-config-mode");
  } else {
    loadOverview().catch(function (e) {
      toast(e.message, "error");
    });
  }
})();
