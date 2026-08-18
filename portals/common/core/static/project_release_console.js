(function () {
  "use strict";

  var root = document.querySelector("[data-release-console]");
  if (!root) return;

  var projectId = root.getAttribute("data-project-id") || "";
  var state = {
    envKey: root.getAttribute("data-env-key") || "",
    matrix: [],
    selected: {},
    batch: null,
    console: null,
    dirty: false,
    autosaveTimer: null,
  };

  var qs = new URLSearchParams(window.location.search);

  function api(path, options) {
    options = options || {};
    return fetch(path, {
      method: options.method || "GET",
      headers: Object.assign({ "Content-Type": "application/json" }, options.headers || {}),
      body: options.body ? JSON.stringify(options.body) : undefined,
      credentials: "same-origin",
    }).then(function (res) {
      return res.json().then(function (body) {
        if (!res.ok || body.ok === false) {
          throw new Error((body && body.error) || "请求失败");
        }
        return body.data;
      });
    });
  }

  function toast(msg) {
    var el = document.createElement("div");
    el.className = "rc-toast";
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 3200);
  }

  function lineKey(line) {
    return (line.channel_id || line.channelId) + ":" + (line.platform || "android");
  }

  function selectedLines() {
    return state.matrix.filter(function (line) {
      return state.selected[lineKey(line)];
    });
  }

  function readFormSharedPlan() {
    return {
      release_reason_type: val("rcReasonType"),
      owner: val("rcOwner"),
      release_window: val("rcReleaseWindow"),
      release_description: val("rcReleaseDescription"),
      server_release_id: val("rcServerArtifact"),
      target_topology_id: val("rcTargetTopology"),
      deploy_server_with_client: chk("rcDeployServer"),
      rollback_with_server: chk("rcRollbackWithServer"),
      min_server_version: val("rcMinServerVersion"),
      release_strategy: val("rcReleaseStrategy"),
      gray_ratio: val("rcGrayRatio"),
      validation_plan: val("rcValidationPlan"),
      rollback_plan: val("rcRollbackPlan"),
    };
  }

  function readAnnouncement() {
    return {
      title: val("rcAnnTitle"),
      body: val("rcAnnBody"),
      effective_at: val("rcAnnEffective"),
      audience: val("rcAnnAudience") || "all",
      sync_to_gm: chk("rcAnnSyncGm"),
    };
  }

  function val(id) {
    var el = document.getElementById(id);
    return el ? String(el.value || "").trim() : "";
  }

  function chk(id) {
    var el = document.getElementById(id);
    return !!(el && el.checked);
  }

  function setVal(id, value) {
    var el = document.getElementById(id);
    if (el) el.value = value == null ? "" : String(value);
  }

  function setChk(id, value) {
    var el = document.getElementById(id);
    if (el) el.checked = !!value;
  }

  function renderEnvSelect(envDefs) {
    var sel = document.getElementById("rcEnvSelect");
    if (!sel) return;
    sel.innerHTML = "";
    (envDefs || []).forEach(function (env) {
      if (env.enabled === false) return;
      var opt = document.createElement("option");
      opt.value = env.env_key;
      opt.textContent = env.label || env.env_key;
      sel.appendChild(opt);
    });
    if (state.envKey) sel.value = state.envKey;
  }

  function renderMatrix() {
    var host = document.getElementById("rcLineMatrix");
    if (!host) return;
    if (!state.envKey) {
      host.innerHTML = '<div class="rc-empty">请先选择环境</div>';
      return;
    }
    if (!state.matrix.length) {
      host.innerHTML = '<div class="rc-empty">当前环境无可用交付线</div>';
      return;
    }
    host.innerHTML = state.matrix.map(function (line) {
      var key = lineKey(line);
      var sel = state.selected[key];
      var dotClass = "rc-dot--" + (line.readiness || "empty");
      var vc = line.version_code || line.line_version_code || "—";
      return (
        '<label class="rc-line-row' + (sel ? " is-selected" : "") + '" data-line-key="' + key + '">' +
        '<input type="checkbox"' + (sel ? " checked" : "") + ' aria-label="' + (line.channel_name || line.channel_id) + '">' +
        '<span><strong>' + esc(line.channel_name || line.channel_id) + '</strong> · ' + esc(line.platform || "") +
        '<div class="rc-line-meta">线上 VC: ' + esc(vc) + '</div></span>' +
        '<span class="rc-dot ' + dotClass + '" title="' + esc(line.readiness || "") + '"></span>' +
        "</label>"
      );
    }).join("");
    host.querySelectorAll(".rc-line-row").forEach(function (row) {
      row.addEventListener("click", function (ev) {
        if (ev.target.tagName === "INPUT") return;
        var cb = row.querySelector("input");
        if (cb) cb.checked = !cb.checked;
        cb.dispatchEvent(new Event("change"));
      });
      var cb = row.querySelector("input");
      cb.addEventListener("change", function () {
        var key = row.getAttribute("data-line-key");
        state.selected[key] = cb.checked;
        row.classList.toggle("is-selected", cb.checked);
        document.getElementById("rcCreateBatchBtn").disabled = !selectedLines().length;
      });
    });
    document.getElementById("rcCreateBatchBtn").disabled = !selectedLines().length;
  }

  function esc(text) {
    return String(text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  }

  function fillFormFromBatch(batch) {
    var plan = batch.shared_plan || {};
    setVal("rcReasonType", plan.release_reason_type || "regular");
    setVal("rcOwner", plan.owner || batch.created_by || "");
    setVal("rcReleaseWindow", plan.release_window || "");
    setVal("rcReleaseDescription", plan.release_description || "");
    setVal("rcServerArtifact", plan.server_release_id || plan.linked_server_release_id || "");
    setVal("rcTargetTopology", plan.target_topology_id || "");
    setChk("rcDeployServer", plan.deploy_server_with_client);
    setChk("rcRollbackWithServer", plan.rollback_with_server !== false);
    setVal("rcMinServerVersion", plan.min_server_version || "");
    setVal("rcReleaseStrategy", plan.release_strategy || "full");
    setVal("rcGrayRatio", plan.gray_ratio || "");
    setVal("rcValidationPlan", plan.validation_plan || "");
    setVal("rcRollbackPlan", plan.rollback_plan || "");
    var ann = batch.announcement || {};
    setVal("rcAnnTitle", ann.title || "");
    setVal("rcAnnBody", ann.body || "");
    setVal("rcAnnEffective", ann.effective_at || "");
    setVal("rcAnnAudience", ann.audience || "all");
    setChk("rcAnnSyncGm", ann.sync_to_gm);
    document.getElementById("rcConfigPlaceholder").hidden = true;
    document.getElementById("rcConfigBody").hidden = false;
    var label = document.getElementById("rcBatchIdLabel");
    if (label) {
      label.hidden = false;
      label.textContent = batch.batch_id || "";
    }
    renderClientTabs(batch);
    renderExecPreview(batch);
  }

  function renderClientTabs(batch) {
    var host = document.getElementById("rcClientTabs");
    if (!host) return;
    var orders = batch.orders || [];
    if (!orders.length) {
      host.innerHTML = '<div class="rc-empty">暂无子发布单</div>';
      return;
    }
    var active = orders[0];
    host.innerHTML =
      orders.map(function (o, i) {
        return '<button type="button" class="rc-tab' + (i === 0 ? " active" : "") + '" data-oid="' + esc(o.release_order_id) + '">' +
          esc(o.channel_name || o.channel_id) + " · " + esc(o.platform) + "</button>";
      }).join("") +
      '<div class="rc-client-panel" id="rcClientPanel">' + clientPanelHtml(active) + "</div>";
    host.querySelectorAll(".rc-tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        host.querySelectorAll(".rc-tab").forEach(function (t) { t.classList.remove("active"); });
        tab.classList.add("active");
        var oid = tab.getAttribute("data-oid");
        var order = orders.find(function (o) { return o.release_order_id === oid; });
        document.getElementById("rcClientPanel").innerHTML = clientPanelHtml(order || {});
      });
    });
  }

  function clientPanelHtml(order) {
    var buildUrl =
      "/admin/projects/" + projectId + "/versions/" + encodeURIComponent(order.version_id || "") +
      "/build-config?env_key=" + encodeURIComponent(order.env_key || state.envKey) +
      "&channel_id=" + encodeURIComponent(order.channel_id || "") +
      "&platform=" + encodeURIComponent(order.platform || "android");
    return (
      "<div><strong>VersionCode:</strong> " + esc(order.version_code || "—") +
      " · 状态: " + esc(order.status || "draft") + "</div>" +
      '<p><a href="' + buildUrl + '" target="_blank" rel="noopener">展开编辑构建配置 →</a></p>'
    );
  }

  function renderExecPreview(batch) {
    var host = document.getElementById("rcExecPreview");
    if (!host) return;
    host.innerHTML = (batch.orders || []).map(function (o) {
      var plan = o.payload || {};
      var deploy = plan.server_coordinated_deploy || {};
      var coord = "";
      if (plan.deploy_server_with_client) {
        if (deploy.error) {
          coord = ' <span class="rc-coord rc-coord--fail">服务端: ' + esc(deploy.error) + "</span>";
        } else if (deploy.deploy_status) {
          coord = ' <span class="rc-coord rc-coord--ok">服务端: ' + esc(deploy.deploy_status) + "</span>";
        } else if (!deploy.skipped) {
          coord = ' <span class="rc-coord">服务端: 待部署</span>';
        }
      }
      var rollback = plan.server_coordinated_rollback || {};
      if (rollback && !rollback.skipped) {
        coord += rollback.ok
          ? ' <span class="rc-coord rc-coord--ok">联合回滚: ok</span>'
          : ' <span class="rc-coord rc-coord--fail">联合回滚: ' + esc(rollback.error || "failed") + "</span>";
      }
      return '<div class="rc-preview-row"><strong>' + esc(o.channel_id) + "/" + esc(o.platform) +
        "</strong> → " + esc(o.release_order_id) + " · " + esc(o.status) + coord + "</div>";
    }).join("") || '<div class="rc-empty">—</div>';
  }

  function renderReadiness(readiness) {
    var host = document.getElementById("rcReadiness");
    if (!host) return;
    if (!readiness || !readiness.lines) {
      host.innerHTML = '<div class="rc-empty">暂无批次</div>';
      return;
    }
    host.innerHTML = readiness.lines.map(function (line) {
      var fail = !line.ready;
      return '<div class="rc-readiness-item' + (fail ? " is-fail" : "") + '">' +
        "<span>" + esc(line.channel_name || line.channel_id) + " · " + esc(line.platform) + "</span>" +
        "<span>" + esc(line.status) + (line.issues && line.issues.length ? " — " + esc(line.issues.join("; ")) : "") + "</span></div>";
    }).join("");
  }

  function renderNextAction(action) {
    var primary = document.getElementById("rcPrimaryAction");
    var secondary = document.getElementById("rcSecondaryActions");
    var failed = document.getElementById("rcFailedLines");
    if (!primary || !action) return;
    primary.textContent = (action.primary && action.primary.label) || "—";
    primary.disabled = !!(action.primary && action.primary.disabled);
    primary.dataset.apiAction = (action.primary && action.primary.api_action) || "";
    secondary.innerHTML = (action.more_actions || []).map(function (item) {
      return '<button type="button" class="rc-btn rc-secondary-btn" data-api-action="' + esc(item.api_action || "") + '">' +
        esc(item.label) + "</button>";
    }).join("");
    secondary.querySelectorAll(".rc-secondary-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        runBatchAction(btn.getAttribute("data-api-action"));
      });
    });
    var fails = action.failed_lines || [];
    if (failed) {
      failed.innerHTML = fails.length
        ? "<h3>失败/进行中 (" + fails.length + ")</h3>" + fails.map(function (f) {
            return "<div>" + esc(f.channel_id) + "/" + esc(f.platform) + " — " + esc(f.status) + "</div>";
          }).join("")
        : "";
    }
  }

  function loadConsole() {
    var params = new URLSearchParams();
    if (state.envKey) params.set("env_key", state.envKey);
    if (state.batch && state.batch.batch_id) params.set("batch_id", state.batch.batch_id);
    return api("/api/projects/" + projectId + "/release-console?" + params.toString()).then(function (data) {
      state.console = data;
      renderEnvSelect(data.env_defs || []);
      state.matrix = data.delivery_matrix || [];
      if (!state.envKey && data.selected_env) state.envKey = data.selected_env;
      var envSel = document.getElementById("rcEnvSelect");
      if (envSel && state.envKey) envSel.value = state.envKey;
      preselectFromQuery();
      renderMatrix();
      if (data.active_batch && data.active_batch.batch_id) {
        state.batch = data.active_batch;
        fillFormFromBatch(state.batch);
        return refreshBatchUi();
      }
    });
  }

  function preselectFromQuery() {
    var ch = qs.get("channel") || qs.get("channel_id") || "";
    var plat = qs.get("platform") || "android";
    if (ch) {
      var key = ch + ":" + plat.toLowerCase();
      state.selected[key] = true;
    }
  }

  function createBatch() {
    var lines = selectedLines();
    if (!lines.length) {
      toast("请至少选择一条交付线");
      return;
    }
    var versionId = qs.get("version_id") || "";
    var payload = {
      env_key: state.envKey,
      line_targets: lines.map(function (line) {
        return {
          channel_id: line.channel_id,
          platform: line.platform || "android",
          version_id: line.recommended_version_id || versionId,
        };
      }),
      shared_plan: readFormSharedPlan(),
      announcement: readAnnouncement(),
    };
    var missing = payload.line_targets.filter(function (t) { return !t.version_id; });
    if (missing.length) {
      toast("部分交付线缺少 VersionCode，请先在版本代码中创建");
      return;
    }
    api("/api/projects/" + projectId + "/release-batches", { method: "POST", body: payload })
      .then(function (batch) {
        state.batch = batch;
        state.dirty = false;
        fillFormFromBatch(batch);
        toast("发版批次已创建");
        return refreshBatchUi();
      })
      .catch(function (err) { toast(err.message); });
  }

  function scheduleAutosave() {
    if (!state.batch || !state.batch.batch_id) return;
    state.dirty = true;
    clearTimeout(state.autosaveTimer);
    state.autosaveTimer = setTimeout(saveBatchPlan, 800);
  }

  function saveBatchPlan() {
    if (!state.batch || !state.batch.batch_id) return Promise.resolve();
    return api("/api/projects/" + projectId + "/release-batches/" + state.batch.batch_id, {
      method: "PATCH",
      body: { shared_plan: readFormSharedPlan(), announcement: readAnnouncement() },
    }).then(function (batch) {
      state.batch = batch;
      state.dirty = false;
    }).catch(function (err) { toast("自动保存失败: " + err.message); });
  }

  function refreshBatchUi() {
    if (!state.batch || !state.batch.batch_id) return Promise.resolve();
    var bid = state.batch.batch_id;
    return Promise.all([
      api("/api/projects/" + projectId + "/release-batches/" + bid + "/readiness"),
      api("/api/projects/" + projectId + "/release-batches/" + bid + "/next-action"),
      api("/api/projects/" + projectId + "/release-batches/" + bid),
    ]).then(function (results) {
      renderReadiness(results[0]);
      renderNextAction(results[1]);
      state.batch = results[2];
      renderExecPreview(state.batch);
    });
  }

  function runBatchAction(action, extraBody) {
    if (!state.batch || !state.batch.batch_id || !action) return;
    var body = extraBody || {};
    if (action === "publish" && state.envKey === "production") {
      var ok = window.confirm("确认生产发布？将发布所有就绪的交付线，此操作不可轻易撤销。");
      if (!ok) return;
      body.confirm_production = true;
    }
    if (action === "rollback") {
      var rbOk = window.confirm("确认批次联合回滚？各交付线将回滚至上一个可用 Bundle（含协同服务端）。");
      if (!rbOk) return;
    }
    document.getElementById("rcProgress").hidden = false;
    document.getElementById("rcProgress").textContent = "执行中…";
    saveBatchPlan().then(function () {
      return api("/api/projects/" + projectId + "/release-batches/" + state.batch.batch_id + "/" + action, {
        method: "POST",
        body: body,
      });
    }).then(function (result) {
      if (action === "publish" && result && result.results) {
        var serverNotes = (result.results || [])
          .filter(function (r) { return r.ok; })
          .map(function (r) { return r.release_order_id; });
        if (serverNotes.length) {
          toast("发布已提交 — 可在发版中心查看协同发布反馈");
        } else {
          toast("操作已提交");
        }
      } else {
        toast("操作已提交");
      }
      return refreshBatchUi();
    }).catch(function (err) {
      toast(err.message);
    }).finally(function () {
      document.getElementById("rcProgress").hidden = true;
    });
  }

  function bindEvents() {
    document.getElementById("rcEnvSelect").addEventListener("change", function (ev) {
      state.envKey = ev.target.value;
      state.selected = {};
      var url = new URL(window.location.href);
      url.searchParams.set("env", state.envKey);
      window.history.replaceState({}, "", url.toString());
      loadConsole();
    });
    document.getElementById("rcCreateBatchBtn").addEventListener("click", createBatch);
    document.getElementById("rcRefreshBtn").addEventListener("click", function () { loadConsole().catch(function (e) { toast(e.message); }); });
    document.getElementById("rcPrimaryAction").addEventListener("click", function () {
      runBatchAction(this.dataset.apiAction || "");
    });
    document.getElementById("rcSelectAllLines").addEventListener("click", function () {
      state.matrix.forEach(function (line) { state.selected[lineKey(line)] = true; });
      renderMatrix();
    });
    ["rcReasonType", "rcOwner", "rcReleaseWindow", "rcReleaseDescription",
      "rcAnnTitle", "rcAnnBody", "rcAnnEffective", "rcAnnAudience", "rcAnnSyncGm",
      "rcServerArtifact", "rcTargetTopology", "rcDeployServer", "rcRollbackWithServer", "rcMinServerVersion",
      "rcReleaseStrategy", "rcGrayRatio", "rcValidationPlan", "rcRollbackPlan"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("change", scheduleAutosave);
      if (el && el.tagName === "TEXTAREA") el.addEventListener("input", scheduleAutosave);
    });
    window.addEventListener("beforeunload", function (ev) {
      if (state.dirty) {
        ev.preventDefault();
        ev.returnValue = "";
      }
    });
  }

  if (qs.get("env") || qs.get("env_key")) {
    state.envKey = qs.get("env") || qs.get("env_key") || state.envKey;
  }

  bindEvents();
  loadConsole().catch(function (err) { toast(err.message); });
})();
