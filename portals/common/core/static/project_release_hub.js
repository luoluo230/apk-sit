(function () {
  "use strict";

  var root = document.querySelector("[data-release-hub]");
  if (!root) return;

  var projectId = root.getAttribute("data-project-id") || "";
  var envSelect = document.getElementById("rhEnvSelect");
  var refreshBtn = document.getElementById("rhRefreshBtn");
  var moduleCards = document.getElementById("rhModuleCards");
  var prodWizard = document.getElementById("rhProdWizard");
  var promotionList = document.getElementById("rhPromotionList");
  var serverPromotionList = document.getElementById("rhServerPromotionList");
  var coordinatedList = document.getElementById("rhCoordinatedList");
  var pendingList = document.getElementById("rhPendingList");
  var successRate = document.getElementById("rhSuccessRate");
  var serverSuccessRate = document.getElementById("rhServerSuccessRate");
  var mttrEl = document.getElementById("rhMttr");
  var verifiedEl = document.getElementById("rhVerified");
  var verifyFailedEl = document.getElementById("rhVerifyFailed");
  var publishFailedEl = document.getElementById("rhPublishFailed");
  var healthBreakdown = document.getElementById("rhHealthBreakdown");
  var healthTrend = document.getElementById("rhHealthTrend");
  var prodStartBtn = document.getElementById("rhProdStartBtn");

  function esc(v) {
    return String(v || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function api(path, opts) {
    opts = opts || {};
    return fetch(path, {
      method: opts.method || "GET",
      headers: Object.assign({ "Content-Type": "application/json" }, opts.headers || {}),
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      credentials: "same-origin",
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok || data.ok === false) {
          throw new Error((data && data.error) || "请求失败");
        }
        return data.data;
      });
    });
  }

  function toast(msg) {
    var el = document.createElement("div");
    el.className = "rh-toast";
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function () {
      el.remove();
    }, 3600);
  }

  function selectedEnv() {
    return (envSelect && envSelect.value) || root.getAttribute("data-env-key") || "development";
  }

  function coordinatedStatusClass(state, opType) {
    if (state === "failed") return " rh-status--fail";
    if (state === "deploying") return " rh-status--deploy";
    if (state === "ok") return opType === "rollback" ? " rh-status--ok" : " rh-status--ok";
    return "";
  }

  function coordinatedOpLabel(row) {
    if (row.op_type === "rollback") {
      return row.label || "联合回滚";
    }
    return row.label || row.state || "协同发布";
  }

  function renderEnvSelect(envDefs, selected) {
    if (!envSelect) return;
    envSelect.innerHTML = (envDefs || [])
      .map(function (row) {
        var ek = row.env_key || "";
        var label = row.label || ek;
        var sel = ek === selected ? " selected" : "";
        return '<option value="' + esc(ek) + '"' + sel + ">" + esc(label) + "</option>";
      })
      .join("");
  }

  function renderModules(cards) {
    if (!moduleCards) return;
    moduleCards.innerHTML = (cards || [])
      .map(function (card) {
        var cls = card.primary ? " rh-card--primary" : "";
        return (
          '<a class="rh-card' +
          cls +
          '" href="' +
          esc(card.href) +
          '"><img src="/static/project_ui/svg/' +
          esc(card.icon) +
          '.svg" alt=""><div><strong>' +
          esc(card.title) +
          "</strong><span>" +
          esc(card.desc) +
          "</span></div></a>"
        );
      })
      .join("");
  }

  function renderWizard(steps) {
    if (!prodWizard) return;
    prodWizard.innerHTML = (steps || [])
      .map(function (step) {
        return "<li><strong>" + esc(step.label) + "</strong> — " + esc(step.desc) + "</li>";
      })
      .join("");
  }

  function renderHealth(health) {
    health = health || {};
    var client = health.client || health;
    var server = health.server || {};
    if (successRate) {
      var clientRate = client.success_rate_pct != null ? client.success_rate_pct : health.success_rate_pct;
      successRate.textContent = clientRate != null ? clientRate + "%" : "—";
    }
    if (serverSuccessRate) {
      serverSuccessRate.textContent =
        server.success_rate_pct != null ? server.success_rate_pct + "%" : "—";
    }
    if (mttrEl) {
      mttrEl.textContent = health.mttr_minutes != null ? health.mttr_minutes + " 分" : "—";
    }
    if (verifiedEl) verifiedEl.textContent = String(client.verified_count ?? health.verified_count ?? "—");
    if (verifyFailedEl) {
      verifyFailedEl.textContent = String(client.verify_failed_count ?? health.verify_failed_count ?? "—");
    }
    if (publishFailedEl) {
      publishFailedEl.textContent = String(client.publish_failed_count ?? health.publish_failed_count ?? "—");
    }

    if (healthBreakdown) {
      var envRows = health.by_env || [];
      var platRows = health.by_platform || [];
      if (!envRows.length && !platRows.length) {
        healthBreakdown.innerHTML = "";
      } else {
        var envHtml = envRows.length
          ? "<div class=\"rh-health-table-wrap\"><h3>按环境</h3><table class=\"rh-health-table\"><thead><tr><th>环境</th><th>客户端</th><th>服务端</th></tr></thead><tbody>" +
            envRows.map(function (row) {
              return "<tr><td>" + esc(row.env_key) + "</td><td>" +
                esc(row.client_success_rate_pct != null ? row.client_success_rate_pct + "%" : "—") +
                "</td><td>" + esc(row.server_success_rate_pct != null ? row.server_success_rate_pct + "%" : "—") + "</td></tr>";
            }).join("") + "</tbody></table></div>"
          : "";
        var platHtml = platRows.length
          ? "<div class=\"rh-health-table-wrap\"><h3>按平台</h3><table class=\"rh-health-table\"><thead><tr><th>平台</th><th>客户端成功率</th><th>失败</th></tr></thead><tbody>" +
            platRows.map(function (row) {
              return "<tr><td>" + esc(row.platform) + "</td><td>" +
                esc(row.client_success_rate_pct != null ? row.client_success_rate_pct + "%" : "—") +
                "</td><td>" + esc(row.client_failed_count ?? 0) + "</td></tr>";
            }).join("") + "</tbody></table></div>"
          : "";
        healthBreakdown.innerHTML = envHtml + platHtml;
      }
    }

    if (healthTrend) {
      var trend = health.daily_trend || [];
      if (!trend.length) {
        healthTrend.innerHTML = "";
      } else {
        healthTrend.innerHTML =
          "<h3>日趋势</h3><div class=\"rh-trend-bars\">" +
          trend.map(function (row) {
            var total = (row.client_verified || 0) + (row.client_failed || 0) + (row.server_deployed || 0) + (row.server_failed || 0);
            var ok = (row.client_verified || 0) + (row.server_deployed || 0);
            var pct = total ? Math.round((ok / total) * 100) : 0;
            return "<div class=\"rh-trend-bar\" title=\"" + esc(row.date) + " 成功 " + ok + " / " + total + "\">" +
              "<span class=\"rh-trend-bar__fill\" style=\"height:" + Math.max(8, pct) + "%\"></span>" +
              "<small>" + esc((row.date || "").slice(5)) + "</small></div>";
          }).join("") +
          "</div>";
      }
    }
  }

  function bindClientPromotionButtons() {
    if (!promotionList) return;
    promotionList.querySelectorAll(".rh-promote-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (btn.disabled) return;
        var bundleId = btn.getAttribute("data-bundle");
        var targetEnv = btn.getAttribute("data-target");
        btn.disabled = true;
        api("/api/projects/" + encodeURIComponent(projectId) + "/artifact-promotions", {
          method: "POST",
          body: { source_bundle_id: bundleId, target_env_key: targetEnv },
        })
          .then(function (data) {
            if (data && data.requires_promotion_approval) {
              toast("已提交 QA 审批，请至审批中心处理");
              loadHub();
              return;
            }
            if (data && data.edit_href) {
              window.location.href = data.edit_href;
            } else {
              toast("客户端制品已晋级");
              loadHub();
            }
          })
          .catch(function (err) {
            toast(err.message || "晋级失败");
            btn.disabled = false;
          });
      });
    });
  }

  function renderPromotions(candidates) {
    if (!promotionList) return;
    if (!candidates || !candidates.length) {
      promotionList.innerHTML = '<div class="rh-empty">暂无可晋级客户端制品</div>';
      return;
    }
    promotionList.innerHTML = candidates
      .map(function (row) {
        var targets = (row.target_envs || [])
          .map(function (t) {
            var disabled = t.version_ready ? "" : " disabled";
            var title = t.version_ready ? "晋级到 " + t.env_label : "目标环境缺少 VersionCode";
            if (t.version_ready && t.requires_promotion_approval) {
              title += "（需 QA 审批）";
            }
            return (
              '<button type="button" class="rh-btn rh-btn--sm rh-btn--primary rh-promote-btn"' +
              disabled +
              ' data-bundle="' +
              esc(row.bundle_id) +
              '" data-target="' +
              esc(t.env_key) +
              '" title="' +
              esc(title) +
              '">' +
              esc(t.env_label) +
              "</button>"
            );
          })
          .join("");
        return (
          '<div class="rh-promotion-row"><div class="rh-promotion-main"><strong>' +
          esc(row.version_name) +
          " / " +
          esc(row.version_code) +
          "</strong><small>" +
          esc(row.source_env_label) +
          " · " +
          esc(row.channel_name) +
          " · " +
          esc(row.platform) +
          '</small></div><div class="rh-promotion-actions">' +
          targets +
          "</div></div>"
        );
      })
      .join("");
    bindClientPromotionButtons();
  }

  function deployServerRelease(serverReleaseId, btn) {
    if (!serverReleaseId) return;
    if (btn) btn.disabled = true;
    api(
      "/api/admin/projects/" +
        encodeURIComponent(projectId) +
        "/server-releases/" +
        encodeURIComponent(serverReleaseId) +
        "/deploy",
      { method: "POST", body: {} }
    )
      .then(function () {
        toast("服务端部署已触发");
        loadHub();
      })
      .catch(function (err) {
        toast(err.message || "部署失败");
        if (btn) btn.disabled = false;
      });
  }

  function bindServerPromotionButtons() {
    if (!serverPromotionList) return;
    serverPromotionList.querySelectorAll(".rh-server-promote-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (btn.disabled) return;
        var sroId = btn.getAttribute("data-sro");
        var targetEnv = btn.getAttribute("data-target");
        btn.disabled = true;
        api("/api/projects/" + encodeURIComponent(projectId) + "/server-artifact-promotions", {
          method: "POST",
          body: { source_server_release_id: sroId, target_env_key: targetEnv },
        })
          .then(function (data) {
            if (data && data.requires_promotion_approval) {
              toast("已提交 QA 审批，审批通过后可部署");
              loadHub();
              return;
            }
            var newSro = (data && data.server_release_id) || "";
            toast("服务端制品已晋级至 " + ((data && data.target_env_label) || targetEnv));
            if (newSro && window.confirm("是否立即部署到目标环境？")) {
              deployServerRelease(newSro);
            } else {
              loadHub();
            }
          })
          .catch(function (err) {
            toast(err.message || "服务端晋级失败");
            btn.disabled = false;
          });
      });
    });
    serverPromotionList.querySelectorAll(".rh-server-deploy-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        deployServerRelease(btn.getAttribute("data-sro"), btn);
      });
    });
  }

  function renderServerPromotions(candidates) {
    if (!serverPromotionList) return;
    if (!candidates || !candidates.length) {
      serverPromotionList.innerHTML = '<div class="rh-empty">暂无可晋级服务端制品</div>';
      return;
    }
    serverPromotionList.innerHTML = candidates
      .map(function (row) {
        var targets = (row.target_envs || [])
          .map(function (t) {
            if (t.already_promoted) {
              var existing = t.existing_server_release_id || "";
              return (
                '<span class="rh-tag rh-tag--server" title="已晋级">' +
                esc(t.env_label) +
                " · 已晋级</span>" +
                (existing
                  ? '<button type="button" class="rh-btn rh-btn--sm rh-btn--secondary rh-server-deploy-btn" data-sro="' +
                    esc(existing) +
                    '">部署</button>'
                  : "")
              );
            }
            return (
              '<button type="button" class="rh-btn rh-btn--sm rh-btn--primary rh-server-promote-btn" data-sro="' +
              esc(row.server_release_id) +
              '" data-target="' +
              esc(t.env_key) +
              '" title="晋级到 ' +
              esc(t.env_label) +
              '">' +
              esc(t.env_label) +
              "</button>"
            );
          })
          .join("");
        var services = (row.target_services || []).join(", ");
        return (
          '<div class="rh-promotion-row"><div class="rh-promotion-main"><strong>' +
          esc(row.version_label || "—") +
          " · " +
          esc(row.protocol_version || "v1") +
          "</strong><small>" +
          esc(row.source_env_label) +
          " · 拓扑 " +
          esc(row.topology_id || "—") +
          (services ? " · 服务 " + esc(services) : "") +
          "</small></div><div class=\"rh-promotion-actions\">" +
          targets +
          "</div></div>"
        );
      })
      .join("");
    bindServerPromotionButtons();
  }

  function renderCoordinatedFeed(items) {
    if (!coordinatedList) return;
    if (!items || !items.length) {
      coordinatedList.innerHTML = '<div class="rh-empty">暂无协同发布记录</div>';
      return;
    }
    coordinatedList.innerHTML = items
      .map(function (row) {
        var opType = row.op_type || "deploy";
        var statusCls = coordinatedStatusClass(row.state, opType);
        var detail = row.detail
          ? '<div class="rh-coordinated-detail">' + esc(row.detail) + "</div>"
          : "";
        var opTag =
          '<span class="rh-tag rh-tag--server">' +
          (opType === "rollback" ? "联合回滚" : "协同发布") +
          "</span>";
        var meta =
          esc(row.env_label) +
          " · " +
          esc(row.channel_name || "") +
          " · " +
          esc(row.platform || "") +
          (row.server_release_id ? " · SRO " + esc(row.server_release_id) : "");
        var actions =
          '<a class="rh-btn rh-btn--sm rh-btn--ghost" href="' +
          esc(row.order_href) +
          '">发布单</a>';
        if (row.server_release_id) {
          actions +=
            '<a class="rh-btn rh-btn--sm rh-btn--ghost" href="' +
            esc(row.server_href) +
            '">服务器</a>';
          if (opType === "deploy" && (row.state === "deploying" || row.state === "pending")) {
            actions +=
              '<button type="button" class="rh-btn rh-btn--sm rh-btn--secondary rh-server-deploy-btn" data-sro="' +
              esc(row.server_release_id) +
              '">重试部署</button>';
          }
        }
        return (
          '<div class="rh-coordinated-row"><div class="rh-coordinated-main">' +
          opTag +
          "<strong>" +
          esc(row.version_name) +
          " / " +
          esc(row.version_code) +
          '</strong><small>' +
          meta +
          "</small>" +
          detail +
          '</div><div class="rh-coordinated-actions"><span class="rh-status' +
          statusCls +
          '">' +
          esc(coordinatedOpLabel(row)) +
          "</span>" +
          actions +
          "</div></div>"
        );
      })
      .join("");
    coordinatedList.querySelectorAll(".rh-server-deploy-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        deployServerRelease(btn.getAttribute("data-sro"), btn);
      });
    });
  }

  function renderPending(items) {
    if (!pendingList) return;
    if (!items || !items.length) {
      pendingList.innerHTML = '<div class="rh-empty">暂无待处理发布单</div>';
      return;
    }
    pendingList.innerHTML = items
      .map(function (row) {
        var action = row.next_action || {};
        var statusCls = row.status === "awaiting_approval" ? " rh-status--warn" : " rh-status--ok";
        var coord = row.coordinated_deploy;
        var coordBadge = "";
        if (coord && coord.label) {
          coordBadge =
            '<span class="rh-status rh-tag--server' +
            coordinatedStatusClass(coord.state) +
            '">' +
            esc(coord.label) +
            "</span>";
        }
        return (
          '<a class="rh-pending-row" href="' +
          esc(row.href) +
          '"><div class="rh-pending-main"><strong>' +
          esc(row.version_name) +
          " / " +
          esc(row.version_code) +
          '</strong><small>' +
          esc(row.env_label) +
          " · " +
          esc(row.channel_name || "") +
          " · " +
          esc(row.platform || "") +
          '</small></div><div class="rh-pending-badges">' +
          coordBadge +
          '<span class="rh-status' +
          statusCls +
          '">' +
          esc(action.label || row.status) +
          "</span></div></a>"
        );
      })
      .join("");
  }

  function loadHub() {
    var env = selectedEnv();
    return api(
      "/api/projects/" + encodeURIComponent(projectId) + "/release-hub?env_key=" + encodeURIComponent(env)
    ).then(function (data) {
      renderEnvSelect(data.env_defs, data.selected_env);
      renderModules(data.module_cards);
      renderWizard(data.prod_wizard_steps);
      renderHealth(data.release_health);
      renderPromotions(data.promotion_candidates);
      renderServerPromotions(data.server_promotion_candidates);
      renderCoordinatedFeed(data.coordinated_deploy_feed);
      renderPending(data.pending_actions);
      if (prodStartBtn && data.quick_actions) {
        prodStartBtn.href = data.quick_actions.prod_release || prodStartBtn.href;
      }
    });
  }

  if (envSelect) {
    envSelect.addEventListener("change", function () {
      loadHub().catch(function (err) {
        toast(err.message || "加载失败");
      });
    });
  }
  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () {
      loadHub().catch(function (err) {
        toast(err.message || "加载失败");
      });
    });
  }

  loadHub().catch(function (err) {
    var msg = esc(err.message || "加载失败");
    if (promotionList) promotionList.innerHTML = '<div class="rh-empty">' + msg + "</div>";
    if (serverPromotionList) serverPromotionList.innerHTML = '<div class="rh-empty">' + msg + "</div>";
    if (coordinatedList) coordinatedList.innerHTML = '<div class="rh-empty">' + msg + "</div>";
  });
})();
