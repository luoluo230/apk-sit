(function () {
  "use strict";

  var root = document.querySelector("[data-runtime-page]");
  if (!root) return;

  var projectId = root.getAttribute("data-project-id") || "";
  var envKey = root.getAttribute("data-env-key") || "production";
  var pollTimer = null;
  var loading = false;
  var API_TIMEOUT_MS = 15000;
  var serviceFilters = {
    service_q: "",
    service_cluster: "",
    service_category: "",
    service_health: "",
    service_status: "",
    service_page: "1",
    service_page_size: "5",
  };

  function readServiceFiltersFromUrl() {
    var p = new URLSearchParams(location.search);
    serviceFilters.service_q = p.get("service_q") || "";
    serviceFilters.service_cluster = p.get("service_cluster") || "";
    serviceFilters.service_category = p.get("service_category") || "";
    serviceFilters.service_health = p.get("service_health") || "";
    serviceFilters.service_status = p.get("service_status") || "";
    serviceFilters.service_page = p.get("service_page") || "1";
    serviceFilters.service_page_size = p.get("service_page_size") || "10";
  }

  function allQueryParams(extra) {
    var base = filterParams();
    var merged = Object.assign({}, base, serviceFilters, extra || {});
    var out = {};
    Object.keys(merged).forEach(function (key) {
      if (merged[key]) out[key] = merged[key];
    });
    return out;
  }

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
      channel_id: p.get("channel_id") || "",
      platform: p.get("platform") || "",
    };
  }

  function queryString(extra) {
    var p = new URLSearchParams();
    Object.entries(allQueryParams(extra)).forEach(function (pair) {
      if (pair[1]) p.set(pair[0], pair[1]);
    });
    var text = p.toString();
    return text ? "?" + text : "";
  }

  async function api(path) {
    var controller = new AbortController();
    var timer = window.setTimeout(function () {
      controller.abort();
    }, API_TIMEOUT_MS);
    try {
      var r = await fetch(path, { credentials: "same-origin", signal: controller.signal });
      var ct = r.headers.get("content-type") || "";
      if (!ct.includes("application/json")) throw new Error("请求失败 (" + r.status + ")");
      var d = await r.json();
      if (!d.ok) throw new Error((d.error && (d.error.message || d.error)) || "加载失败");
      return d.data;
    } catch (err) {
      if (err && err.name === "AbortError") throw new Error("加载超时，请稍后重试");
      throw err;
    } finally {
      window.clearTimeout(timer);
    }
  }

  function formatMetric(value, unit) {
    if (value === null || value === undefined || value === "") return "—";
    if (unit === "%") return String(value) + "%";
    if (unit === "ms") return String(value) + " ms";
    return String(value);
  }

  function renderKpiCard(opts) {
    var trendHtml = "";
    var trendLabel = String(opts.trendLabel || "");
    var trendDir = opts.trendDir || "flat";
    if (trendLabel && trendLabel !== "—" && trendDir !== "flat" && trendLabel.indexOf("持平") < 0) {
      trendHtml =
        '<span class="pm-kpi-trend ' +
        esc(trendDir) +
        '">' +
        esc(trendLabel) +
        "</span>";
    }
    return (
      '<article class="pm-kpi-card">' +
      '<span class="pm-kpi-icon pm-kpi-icon--' +
      opts.tone +
      '"><img src="/static/project_ui/svg/' +
      opts.icon +
      '" alt=""></span>' +
      '<div class="pm-kpi-body"><span class="pm-kpi-label">' +
      esc(opts.label) +
      '</span><div class="pm-kpi-value-row"><strong>' +
      esc(opts.value) +
      "</strong>" +
      trendHtml +
      "</div></div></article>"
    );
  }

  function renderKpis(data) {
    var host = document.getElementById("p16Kpis");
    if (!host) return;
    var k = data.kpis || {};
    var cards = [
      ["service_health", "kpi_health.svg", "green"],
      ["online_instances", "nav_agent_server.svg", "orange"],
      ["alerts_today", "global_bell.svg", "red"],
      ["avg_latency_ms", "status_running.svg", "blue"],
      ["error_rate", "card_kpi_blockers.svg", "violet"],
    ];
    host.innerHTML = cards
      .map(function (pair) {
        var key = pair[0];
        var item = k[key] || {};
        var value =
          key === "online_instances" && item.total != null
            ? String(item.value != null ? item.value : 0) + " / " + String(item.total)
            : formatMetric(item.value, item.unit || (key === "error_rate" ? "%" : key === "avg_latency_ms" ? "ms" : key === "service_health" ? "%" : ""));
        return renderKpiCard({
          icon: pair[1],
          tone: pair[2],
          label: item.label || key,
          value: value,
          trendLabel: item.trend_label,
          trendDir: item.trend_dir || "flat",
        });
      })
      .join("");
  }

  function renderDonut(hostId, donut) {
    var host = document.getElementById(hostId);
    if (!host || !donut) return;
    var segments = donut.segments || [];
    var total = segments.reduce(function (sum, seg) {
      return sum + Number(seg.count || 0);
    }, 0);
    var radius = 34;
    var cx = 44;
    var cy = 44;
    var circumference = 2 * Math.PI * radius;
    var offset = 0;
    var arcs = "";
    if (total > 0) {
      segments.forEach(function (seg) {
        var count = Number(seg.count || 0);
        if (!count) return;
        var len = (count / total) * circumference;
        arcs +=
          '<circle cx="' +
          cx +
          '" cy="' +
          cy +
          '" r="' +
          radius +
          '" fill="none" stroke="' +
          esc(seg.color || "#d9d9d9") +
          '" stroke-width="10" stroke-dasharray="' +
          len +
          " " +
          (circumference - len) +
          '" stroke-dashoffset="' +
          -offset +
          '" transform="rotate(-90 ' +
          cx +
          " " +
          cy +
          ')"></circle>';
        offset += len;
      });
    } else {
      arcs =
        '<circle cx="' +
        cx +
        '" cy="' +
        cy +
        '" r="' +
        radius +
        '" fill="none" stroke="#eef1f6" stroke-width="10"></circle>';
    }
    host.innerHTML =
      '<div class="p16-widget-head"><h3>' +
      esc(donut.title || "") +
      '</h3></div><div class="p16-widget-body"><div class="p16-donut-wrap"><svg class="p16-donut" viewBox="0 0 88 88" aria-hidden="true">' +
      arcs +
      '</svg><div class="p16-donut-center"><span>' +
      esc(donut.center_label || "") +
      "</span><strong>" +
      esc(String(donut.center_value != null ? donut.center_value : 0)) +
      '</strong></div><div class="p16-legend">' +
      segments
        .map(function (seg) {
          return (
            '<div class="p16-legend-row"><span><i class="p16-legend-dot" style="background:' +
            esc(seg.color || "#d9d9d9") +
            '"></i>' +
            esc(seg.label || "") +
            "</span><b>" +
            esc(String(seg.count || 0)) +
            "</b></div>"
          );
        })
        .join("") +
      "</div></div></div>";
  }

  function renderAgentOnline(agent) {
    var host = document.getElementById("p16AgentOnline");
    if (!host) return;
    agent = agent || {};
    host.innerHTML =
      '<div class="p16-widget-head"><h3>Agent</h3></div><div class="p16-stat-list">' +
      '<div class="p16-stat-row"><span>在线</span><strong>' +
      esc(String(agent.online != null ? agent.online : 0)) +
      " / " +
      esc(String(agent.total != null ? agent.total : 0)) +
      "</strong></div>" +
      (agent.link
        ? '<a class="p16-widget-link" href="' + esc(agent.link) + '">Agent</a>'
        : "") +
      "</div>";
  }

  function renderClientHealth(health) {
    var host = document.getElementById("p16ClientHealth");
    var badge = document.getElementById("p16ClientHealthBadge");
    if (!host) return;
    health = health || {};
    var checks = health.verify_checks || [];
    var gates = health.gate_results || [];
    var verifyLabel = checks.length
      ? checks.filter(function (x) { return x.ok; }).length + "/" + checks.length + " 通过"
      : "未执行";
    var gateLabel = gates.length ? (gates[0].passed ? "最近 Gate PASS" : "最近 Gate FAIL") : "无 Gate 记录";
    if (badge) {
      badge.textContent = gateLabel;
    }
    host.innerHTML =
      '<div class="p16-client-health-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:12px 16px">' +
      '<div><strong>验证探针</strong><div style="margin-top:6px;color:#64748b">' + esc(verifyLabel) + "</div>" +
      (checks.length
        ? "<ul style=\"margin:8px 0 0;padding-left:18px;font-size:13px\">" +
          checks.map(function (row) {
            return "<li>" + esc(row.key || "") + ": " + esc(row.ok ? "OK" : "FAIL") + "</li>";
          }).join("") +
          "</ul>"
        : "") +
      "</div><div><strong>Bootstrap Gate</strong><div style=\"margin-top:6px;color:#64748b\">" + esc(gateLabel) + "</div>" +
      (gates.length
        ? "<ul style=\"margin:8px 0 0;padding-left:18px;font-size:13px\">" +
          gates.slice(0, 5).map(function (row) {
            return "<li>" + esc(row.gate || "") + " · " + esc((row.at || "").slice(0, 19)) + "</li>";
          }).join("") +
          "</ul>"
        : "") +
      "</div></div>";
  }

  function renderRecentRelease(bundle) {
    var host = document.getElementById("p16RecentRelease");
    if (!host) return;
    bundle = bundle || {};
    if (!bundle.version) {
      host.innerHTML =
        '<div class="p16-widget-head"><h3>最近发布</h3></div><div class="p16-empty">—</div>';
      return;
    }
    var publisher = bundle.publisher || "";
    var publisherInitial = bundle.publisher_initial || (publisher ? publisher.slice(0, 1) : "李");
    var releasedAt = bundle.released_at
      ? esc(bundle.released_at.replace("T", " ").replace("Z", "").slice(0, 19))
      : "";
    host.innerHTML =
      '<div class="p16-widget-head"><h3>最近发布</h3></div><div class="p16-release-body">' +
      '<div class="p16-release-head"><div class="p16-release-version">' +
      esc(bundle.version) +
      "</div></div>" +
      (bundle.link
        ? '<a class="p16-widget-link" href="' + esc(bundle.link) + '">详情</a>'
        : "") +
      "</div>";
  }

  function renderTrend(hostId, trend) {
    var host = document.getElementById(hostId);
    if (!host) return;
    trend = trend || {};
    var delta = trend.delta;
    var deltaClass = "flat";
    var deltaText = "—";
    if (delta != null && delta !== "") {
      deltaClass = Number(delta) >= 0 ? "up" : "down";
      deltaText = (Number(delta) >= 0 ? "↑ " : "↓ ") + Math.abs(Number(delta)) + (trend.unit === "%" ? "%" : trend.unit === "ms" ? " ms" : "");
    }
    var series = trend.series || [];
    var sparkHtml = "";
    if (series.length > 1) {
      var width = 240;
      var height = 56;
      var values = series.map(function (p) {
        return Number(p.value || 0);
      });
      var min = Math.min.apply(null, values);
      var max = Math.max.apply(null, values);
      var range = max - min || 1;
      var points = series
        .map(function (p, idx) {
          var x = (idx / (series.length - 1)) * width;
          var y = height - ((Number(p.value || 0) - min) / range) * (height - 8) - 4;
          return x.toFixed(1) + "," + y.toFixed(1);
        })
        .join(" ");
      sparkHtml =
        '<svg class="p16-sparkline" viewBox="0 0 ' +
        width +
        " " +
        height +
        '" preserveAspectRatio="none"><polyline fill="none" stroke="#1677ff" stroke-width="2" points="' +
        points +
        '"></polyline></svg>';
    } else {
      sparkHtml = '<div class="p16-sparkline-empty">—</div>';
    }
    var deltaHtml =
      deltaClass !== "flat" && deltaText !== "—"
        ? '<div class="p16-trend-delta ' + deltaClass + '">' + esc(deltaText) + "</div>"
        : "";
    host.innerHTML =
      '<div class="p16-trend-head"><div><h3>' +
      esc(trend.label || "") +
      '</h3><div class="p16-trend-value">' +
      esc(formatMetric(trend.value, trend.unit || "")) +
      "</div></div>" +
      deltaHtml +
      "</div>" +
      sparkHtml;
  }

  function renderRecentChanges(items) {
    var host = document.getElementById("p16RecentChanges");
    if (!host) return;
    items = items || [];
    host.innerHTML = items.length
      ? items
          .map(function (item) {
            return (
              '<div class="p16-rail-change"><span class="p16-rail-change-dot ' +
              esc(item.tone || "config") +
              '"></span><div><b>' +
              esc(item.type_label || "变更") +
              "</b><span>" +
              esc(item.title || "") +
              (item.time ? " · " + esc(item.time) : "") +
              "</span></div></div>"
            );
          })
          .join("")
      : '<div class="p16-empty">—</div>';
  }

  function renderRisks(items) {
    var host = document.getElementById("p16CurrentRisks");
    var title = document.getElementById("p16RiskTitle");
    if (!host) return;
    items = items || [];
    if (title) title.textContent = items.length ? ("当前风险 " + String(items.length)) : "当前风险";
    host.innerHTML = items.length
      ? items
          .map(function (item) {
            var tag = item.href ? "a" : "div";
            var href = item.href ? ' href="' + esc(item.href) + '"' : "";
            return (
              "<" +
              tag +
              ' class="p16-rail-risk ' +
              esc(item.severity || "") +
              '"' +
              href +
              "><b>" +
              esc(item.title || "") +
              "</b></" +
              tag +
              ">"
            );
          })
          .join("")
      : '<div class="p16-empty">—</div>';
  }

  function renderDashboard(data) {
    var dash = data.dashboard || {};
    renderDonut("p16ServiceDistribution", dash.service_distribution);
    renderDonut("p16InstanceHealth", dash.instance_health);
    renderAgentOnline(dash.agent_online);
    renderRecentRelease(data.bundle);
    var trends = dash.resource_trends || {};
    renderTrend("p16TrendCpu", trends.cpu);
    renderTrend("p16TrendMemory", trends.memory);
    renderTrend("p16TrendQps", trends.qps);
    renderRecentChanges(dash.recent_changes);
    renderRisks(dash.risks);
  }

  function healthClass(pct) {
    if (pct >= 90) return "p16-health-good";
    if (pct >= 60) return "p16-health-warn";
    return "p16-health-bad";
  }

  function serviceLinks(row) {
    var base = "/admin/projects/" + encodeURIComponent(projectId);
    var envQs = "?env_key=" + encodeURIComponent(envKey);
    var agentQs = envQs + (row.agent_id ? "&agent_id=" + encodeURIComponent(row.agent_id) : "");
    var serviceQs = envQs + (row.service_id ? "&service_id=" + encodeURIComponent(row.service_id) : "");
    return {
      instances: base + "/agents" + agentQs,
      logs: base + "/diagnostics" + serviceQs,
      topology: base + "/topologies" + envQs + (row.node_id ? "&node_id=" + encodeURIComponent(row.node_id) : ""),
    };
  }

  var openRowMenuId = "";

  function bindRowMenus() {
    var tbody = document.getElementById("p16ServiceTable");
    if (!tbody) return;
    tbody.querySelectorAll("[data-row-menu]").forEach(function (btn) {
      btn.onclick = function (event) {
        event.stopPropagation();
        var rowId = String(btn.getAttribute("data-row-menu") || "");
        openRowMenuId = openRowMenuId === rowId ? "" : rowId;
        tbody.querySelectorAll(".p16-row-dropdown").forEach(function (menu) {
          var match = String(menu.getAttribute("data-row-dropdown") || "") === openRowMenuId;
          menu.classList.toggle("is-hidden", !match);
        });
      };
    });
  }

  function runStateLabel(row) {
    var bucket = String(row.run_bucket || "");
    if (bucket === "running") return "运行中";
    if (bucket === "degraded") return "降级";
    return "离线";
  }

  function renderServicePagination(pageInfo) {
    var host = document.getElementById("p16ServicePagination");
    if (!host) return;
    pageInfo = pageInfo || {};
    var total = Number(pageInfo.total || 0);
    var page = Number(pageInfo.page || 1);
    var totalPages = Number(pageInfo.total_pages || 1);
    var pageSize = Number(pageInfo.page_size || 10);
    if (!total) {
      host.innerHTML = '<span>共 0 条 live 实例</span><span></span>';
      return;
    }
    host.innerHTML =
      "<span>共 " +
      esc(String(total)) +
      " 条（live " +
      esc(String(pageInfo.live_total != null ? pageInfo.live_total : total)) +
      " / 运行中 " +
      esc(String(pageInfo.running_total != null ? pageInfo.running_total : 0)) +
      "）</span><nav>" +
      '<button type="button" id="p16PagePrev"' +
      (page <= 1 ? " disabled" : "") +
      ' aria-label="上一页">‹</button>' +
      "<span>第 " +
      esc(String(page)) +
      " / " +
      esc(String(totalPages)) +
      " 页 · 每页 " +
      esc(String(pageSize)) +
      " 条</span>" +
      '<button type="button" id="p16PageNext"' +
      (page >= totalPages ? " disabled" : "") +
      ' aria-label="下一页">›</button>' +
      "</nav>";
    var prev = document.getElementById("p16PagePrev");
    var next = document.getElementById("p16PageNext");
    if (prev) {
      prev.onclick = function () {
        if (page <= 1) return;
        serviceFilters.service_page = String(page - 1);
        syncServiceFiltersToUrl();
        loadRuntime().catch(function (e) {
          toast(e.message, "error");
        });
      };
    }
    if (next) {
      next.onclick = function () {
        if (page >= totalPages) return;
        serviceFilters.service_page = String(page + 1);
        syncServiceFiltersToUrl();
        loadRuntime().catch(function (e) {
          toast(e.message, "error");
        });
      };
    }
  }

  function populateServiceFilterOptions(pageInfo) {
    var opts = (pageInfo && pageInfo.filter_options) || {};
    var clusterSelect = document.getElementById("p16ServiceCluster");
    var categorySelect = document.getElementById("p16ServiceCategory");
    var searchInput = document.getElementById("p16ServiceSearch");
    var healthSelect = document.getElementById("p16ServiceHealth");
    var statusSelect = document.getElementById("p16ServiceStatus");
    if (clusterSelect) {
      var clusterVal = serviceFilters.service_cluster;
      clusterSelect.innerHTML =
        '<option value="">全部集群</option>' +
        (opts.clusters || [])
          .map(function (item) {
            return '<option value="' + esc(item) + '">' + esc(item) + "</option>";
          })
          .join("");
      clusterSelect.value = clusterVal;
    }
    if (categorySelect) {
      categorySelect.innerHTML =
        '<option value="">全部分类</option>' +
        (opts.categories || [])
          .map(function (item) {
            return '<option value="' + esc(item) + '">' + esc(item) + "</option>";
          })
          .join("");
      categorySelect.value = serviceFilters.service_category;
    }
    if (searchInput) searchInput.value = serviceFilters.service_q;
    if (healthSelect) healthSelect.value = serviceFilters.service_health;
    if (statusSelect) statusSelect.value = serviceFilters.service_status;
    var badge = document.getElementById("p16ServiceLiveBadge");
    if (badge) {
      badge.textContent =
        "Agent 上报 live · " + String(pageInfo.live_total != null ? pageInfo.live_total : 0) + " 实例";
    }
  }

  function syncServiceFiltersToUrl() {
    var url = new URL(location.href);
    Object.keys(serviceFilters).forEach(function (key) {
      if (serviceFilters[key]) url.searchParams.set(key, serviceFilters[key]);
      else url.searchParams.delete(key);
    });
    history.replaceState(null, "", url.pathname + url.search);
  }

  function bindServiceTableFilters() {
    var searchInput = document.getElementById("p16ServiceSearch");
    var clusterSelect = document.getElementById("p16ServiceCluster");
    var categorySelect = document.getElementById("p16ServiceCategory");
    var healthSelect = document.getElementById("p16ServiceHealth");
    var statusSelect = document.getElementById("p16ServiceStatus");
    function applyServiceFilters() {
      serviceFilters.service_q = searchInput ? searchInput.value.trim() : "";
      serviceFilters.service_cluster = clusterSelect ? clusterSelect.value : "";
      serviceFilters.service_category = categorySelect ? categorySelect.value : "";
      serviceFilters.service_health = healthSelect ? healthSelect.value : "";
      serviceFilters.service_status = statusSelect ? statusSelect.value : "";
      serviceFilters.service_page = "1";
      syncServiceFiltersToUrl();
      loadRuntime().catch(function (e) {
        toast(e.message, "error");
      });
    }
    if (searchInput) {
      var searchTimer = null;
      searchInput.oninput = function () {
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(applyServiceFilters, 300);
      };
    }
    [clusterSelect, categorySelect, healthSelect, statusSelect].forEach(function (node) {
      if (node) node.onchange = applyServiceFilters;
    });
  }

  function normalizeServicesPage(data) {
    var pageInfo = data.services_page;
    if (pageInfo && Array.isArray(pageInfo.items)) return pageInfo;
    return {
      items: [],
      total: 0,
      page: 1,
      page_size: Number(serviceFilters.service_page_size || 5),
      total_pages: 1,
      live_total: 0,
      running_total: 0,
      filter_options: { clusters: [], categories: [] },
      stale_api: true,
    };
  }

  function renderServices(data) {
    var tbody = document.getElementById("p16ServiceTable");
    if (!tbody) return;
    if (!document.getElementById("p16ServiceToolbar")) {
      tbody.innerHTML =
        '<tr><td colspan="11" class="p16-empty">页面模板版本过旧，请强制刷新（Ctrl+F5）或重启服务后重试。</td></tr>';
      return;
    }
    var pageInfo = normalizeServicesPage(data);
    var rows = pageInfo.items || [];
    populateServiceFilterOptions(pageInfo);
    renderServicePagination(pageInfo);
    if (pageInfo.stale_api) {
      tbody.innerHTML =
        '<tr><td colspan="11" class="p16-empty p16-empty--error">运行态 API 版本过旧，请重启后端服务并刷新页面。</td></tr>';
      return;
    }
    if (!rows.length) {
      tbody.innerHTML =
        '<tr><td colspan="11" class="p16-empty">' +
        (pageInfo.live_total
          ? "当前筛选条件下无匹配实例，请调整分类或搜索条件"
          : data.data_quality && data.data_quality.metrics_missing
            ? "暂无 live 服务实例（Agent 未上报或未配置 ops）"
            : "暂无 Agent 上报的服务实例") +
        "</td></tr>";
      return;
    }
    tbody.innerHTML = rows
      .map(function (row, idx) {
        var inst =
          String(row.instances_online != null ? row.instances_online : 0) +
          " / " +
          String(row.instances_total != null ? row.instances_total : 1);
        var links = serviceLinks(row);
        var rowId = String(row.service_id || row.node_id || idx);
        return (
          "<tr>" +
          "<td><strong>" +
          esc(row.name) +
          '</strong><span class="p16-live-tag">live</span></td>' +
          "<td class=\"p16-device-cell\">" +
          deviceCell(row) +
          "</td>" +
          "<td>" +
          esc(row.cluster) +
          "</td>" +
          "<td>" +
          esc(row.category || "—") +
          "</td>" +
          "<td>" +
          esc(inst) +
          " <span class=\"p16-run-tag p16-run-tag--" +
          esc(row.run_bucket || "offline") +
          '">' +
          esc(runStateLabel(row)) +
          "</span></td>" +
          "<td><span class=\"" +
          healthClass(Number(row.health_pct || 0)) +
          '">' +
          esc(String(row.health_pct != null ? row.health_pct : 0) + "%") +
          "</span></td>" +
          "<td>" +
          esc(row.cpu != null ? row.cpu : "—") +
          "</td>" +
          "<td>" +
          esc(row.memory != null ? row.memory : "—") +
          "</td>" +
          "<td>" +
          esc(row.qps != null ? row.qps : "—") +
          "</td>" +
          "<td>" +
          esc(row.updated_at || "—") +
          '</td><td class="p16-actions-cell"><a class="p16-action-link" href="' +
          esc(links.instances) +
          '">查看实例</a><div class="p16-row-menu-wrap"><button type="button" class="p16-row-menu" data-row-menu="' +
          esc(rowId) +
          '" aria-label="更多"><img src="/static/project_ui/svg/action_more.svg" alt=""></button><div class="p16-row-dropdown is-hidden" data-row-dropdown="' +
          esc(rowId) +
          '"><a href="' +
          esc(links.instances) +
          '">查看实例</a><a href="' +
          esc(links.logs) +
          '">查看日志</a><a href="' +
          esc(links.topology) +
          '">查看拓扑</a></div></div></td></tr>'
        );
      })
      .join("");
    openRowMenuId = "";
    bindRowMenus();
    var foot = document.getElementById("p16AllServicesLink");
    if (foot) {
      foot.href =
        "/admin/projects/" +
        encodeURIComponent(projectId) +
        "/agents?env_key=" +
        encodeURIComponent(envKey);
      foot.innerHTML =
        "查看全部服务列表 (" +
        String(pageInfo.live_total != null ? pageInfo.live_total : rows.length) +
        ')<img src="/static/project_ui/svg/action_next.svg" alt="">';
    }
  }

  function renderOnCall(onCall) {
    var host = document.getElementById("p16OnCall");
    if (!host) return;
    onCall = onCall || {};
    if (!onCall.name && !onCall.configured) {
      host.innerHTML = '<div class="p16-empty">—</div>';
      return;
    }
    var initial = String(onCall.name || "?").slice(0, 1);
    host.innerHTML =
      '<div class="p16-oncall-card"><div class="p16-oncall-avatar">' +
      esc(initial) +
      '</div><div class="p16-oncall-meta"><div class="p16-oncall-name-row"><b>' +
      esc(onCall.name || "—") +
      "</b>" +
      (onCall.role ? '<span class="p16-oncall-role-tag">' + esc(onCall.role) + "</span>" : "") +
      "</div>" +
      (onCall.phone ? "<span>" + esc(onCall.phone) + "</span>" : "") +
      (onCall.shift ? "<span>值班时段 " + esc(onCall.shift) + "</span>" : "") +
      "</div></div>";
  }

  function renderSidebar(data) {
    var sidebar = data.sidebar || {};
    renderOnCall(sidebar.on_call);
    var badgesHost = document.getElementById("p16AlertBadges");
    var listHost = document.getElementById("p16AlertList");
    var quickHost = document.getElementById("p16QuickLinks");
    var counts = sidebar.alerts && sidebar.alerts.counts_by_severity ? sidebar.alerts.counts_by_severity : {};
    if (badgesHost) {
      var badgeMeta = [
        ["critical", "紧急", "status_error.svg"],
        ["warning", "重要", "status_warning.svg"],
        ["info", "提示", "status_info.svg"],
        ["other", "其他", "status_pending.svg"],
      ];
      badgesHost.innerHTML = badgeMeta
        .map(function (pair) {
          return (
            '<div class="p16-alert-badge ' +
            pair[0] +
            '"><span class="p16-alert-badge-icon"><img src="/static/project_ui/svg/' +
            pair[2] +
            '" alt=""></span><strong>' +
            esc(String(counts[pair[0]] || 0)) +
            "</strong></div>"
          );
        })
        .join("");
    }
    if (listHost) {
      var recent = (sidebar.alerts && sidebar.alerts.recent) || [];
      listHost.innerHTML = recent.length
        ? recent
            .map(function (item) {
              return (
                '<div class="p16-alert-item ' +
                esc(item.severity || "") +
                '"><div class="p16-alert-item-head"><b>' +
                esc(item.title) +
                "</b>" +
                (item.env_label ? '<span class="p16-env-tag">' + esc(item.env_label) + "</span>" : "") +
                "</div><span>" +
                esc(item.time || "") +
                "</span></div>"
              );
            })
            .join("")
        : '<div class="p16-empty">—</div>';
    }
    if (quickHost) {
      quickHost.innerHTML = (sidebar.quick_links || [])
        .map(function (item) {
          return (
            '<a href="' +
            esc(item.href) +
            '"><img src="/static/project_ui/svg/' +
            esc(item.icon || "action_next") +
            '.svg" alt="">' +
            esc(item.label) +
            "</a>"
          );
        })
        .join("");
    }
  }

  function deviceCell(row) {
    var label = row.device_label || row.device_id || "—";
    var host = row.host_ip ? " (" + row.host_ip + ")" : "";
    var agent = row.agent_id ? '<span class="p16-device-agent">' + esc(row.agent_id) + "</span>" : "";
    return "<strong>" + esc(label) + esc(host) + "</strong>" + agent;
  }

  function renderQuality(data) {
    var banner = document.getElementById("p16QualityBanner");
    if (!banner) return;
    var q = data.data_quality || {};
    if (!q.can_ops) {
      banner.textContent = "无运维读取权限，运行指标不可用";
      banner.classList.remove("is-hidden");
      return;
    }
    banner.textContent = "";
    banner.classList.add("is-hidden");
  }

  function renderHeader(data) {
    var ctx = data.context || {};
    var runtime = data.runtime || {};
    var title = document.getElementById("p16MainTitle");
    var badge = document.getElementById("p16RuntimeBadge");
    var updated = document.getElementById("p16UpdatedAt");
    if (title) title.textContent = (ctx.env_label || ctx.env_key || envKey) + "概览";
    if (updated) {
      var raw = ctx.updated_at || "";
      updated.textContent = raw ? raw.replace("T", " ").replace("Z", "").slice(0, 19) : "--";
    }
    if (badge) {
      var badgeKey = runtime.badge || "stopped";
      var badgeText =
        badgeKey === "running"
          ? "运行中"
          : badgeKey === "blocked"
            ? "阻断"
            : badgeKey === "warning"
              ? "预警"
              : "未运行";
      badge.className = "p16-runtime-badge " + badgeKey;
      badge.textContent = badgeText;
    }
  }

  function renderErrorState(message) {
    var tbody = document.getElementById("p16ServiceTable");
    if (tbody) {
      tbody.innerHTML =
        '<tr><td colspan="11" class="p16-empty p16-empty--error">' +
        esc(message || "加载失败") +
        ' <button type="button" class="p16-retry-btn" id="p16RetryInline">重试</button></td></tr>';
      var retry = document.getElementById("p16RetryInline");
      if (retry) {
        retry.onclick = function () {
          loadRuntime().catch(function (e) {
            toast(e.message, "error");
          });
        };
      }
    }
  }

  function populateFilters(data) {
    var filters = filterParams();
    var opts = data.filter_options || {};
    var envSelect = document.getElementById("p16FilterEnv");
    var channelSelect = document.getElementById("p16FilterChannel");
    var platformSelect = document.getElementById("p16FilterPlatform");
    if (envSelect && (opts.environment_options || []).length) {
      envSelect.innerHTML = (opts.environment_options || [])
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
      envSelect.value = envKey;
    }
    if (channelSelect) {
      channelSelect.innerHTML =
        '<option value="">全部渠道</option>' +
        (opts.channel_options || [])
          .map(function (row) {
            return (
              '<option value="' +
              esc(row.channel_id) +
              '">' +
              esc(row.channel_name || row.channel_id) +
              "</option>"
            );
          })
          .join("");
      channelSelect.value = filters.channel_id;
    }
    if (platformSelect) {
      platformSelect.innerHTML =
        '<option value="">多平台</option>' +
        (opts.platform_options || [])
          .map(function (row) {
            return (
              '<option value="' +
              esc(row.value) +
              '">' +
              esc(row.label || row.value) +
              "</option>"
            );
          })
          .join("");
      platformSelect.value = filters.platform;
    }
  }

  function bindFilters() {
    function applyEnvChange() {
      var nextEnv = document.getElementById("p16FilterEnv");
      if (!nextEnv || !nextEnv.value || nextEnv.value === envKey) return;
      location.href =
        "/admin/projects/" +
        encodeURIComponent(projectId) +
        "/environments/" +
        encodeURIComponent(nextEnv.value) +
        "/runtime" +
        queryString();
    }
    function applyLocalFilters() {
      var url = new URL(location.href);
      var channel = document.getElementById("p16FilterChannel");
      var platform = document.getElementById("p16FilterPlatform");
      if (channel && channel.value) url.searchParams.set("channel_id", channel.value);
      else url.searchParams.delete("channel_id");
      if (platform && platform.value) url.searchParams.set("platform", platform.value);
      else url.searchParams.delete("platform");
      history.replaceState(null, "", url.pathname + url.search);
      loadRuntime().catch(function (e) {
        toast(e.message, "error");
      });
    }
    var envSelect = document.getElementById("p16FilterEnv");
    if (envSelect) envSelect.onchange = applyEnvChange;
    ["p16FilterChannel", "p16FilterPlatform"].forEach(function (id) {
      var node = document.getElementById(id);
      if (node) node.onchange = applyLocalFilters;
    });
  }

  async function loadRuntime() {
    if (loading) return;
    loading = true;
    try {
      var data = await api(
        "/api/projects/" +
          encodeURIComponent(projectId) +
          "/environments/" +
          encodeURIComponent(envKey) +
          "/runtime-overview" +
          queryString()
      );
      populateFilters(data);
      renderHeader(data);
      renderQuality(data);
      renderKpis(data);
      renderDashboard(data);
      renderClientHealth(data.client_health || {});
      renderServices(data);
      renderSidebar(data);
    } catch (err) {
      renderErrorState(err.message || "加载失败");
      throw err;
    } finally {
      loading = false;
    }
  }

  var refreshBtn = document.getElementById("p16RefreshBtn");
  if (refreshBtn) {
    refreshBtn.onclick = function () {
      loadRuntime().catch(function (e) {
        toast(e.message, "error");
      });
    };
  }

  readServiceFiltersFromUrl();
  bindFilters();
  bindServiceTableFilters();

  function applyReleaseOrderFocus() {
    var params = new URLSearchParams(location.search);
    if (params.get("from") !== "release-order") return;
    var reason = params.get("focus_reason") || "请确认并启动目标拓扑的运行态。";
    var releaseOrderId = params.get("release_order_id") || "";
    var banner = document.getElementById("p16ReleaseFocusBanner");
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "p16ReleaseFocusBanner";
      banner.className = "release-focus-banner";
      var head = document.querySelector(".p16-head");
      if (head) head.insertAdjacentElement("afterend", banner);
    }
    var returnHref = releaseOrderId
      ? "/admin/projects/" + encodeURIComponent(projectId) + "/release-orders/" + encodeURIComponent(releaseOrderId)
      : "";
    banner.innerHTML =
      "<div><strong>来自发布单 · 待启动运行态</strong><p>" +
      esc(reason) +
      "</p></div>" +
      (returnHref ? '<a class="release-focus-return" href="' + returnHref + '">返回发布单</a>' : "");
    ["p16RuntimeBadge", "p16MainTitle", "p16DashTop"].forEach(function (id) {
      var node = document.getElementById(id);
      if (node) node.classList.add("field-highlight-target");
    });
  }

  applyReleaseOrderFocus();
  document.addEventListener("click", function (event) {
    if (!event.target.closest(".p16-row-menu-wrap")) {
      openRowMenuId = "";
      document.querySelectorAll(".p16-row-dropdown").forEach(function (menu) {
        menu.classList.add("is-hidden");
      });
    }
  });
  loadRuntime().catch(function (e) {
    toast(e.message, "error");
  });

  pollTimer = window.setInterval(function () {
    loadRuntime().catch(function () {});
  }, 30000);

  window.addEventListener("beforeunload", function () {
    if (pollTimer) window.clearInterval(pollTimer);
  });
})();
