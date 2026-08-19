(function () {
  "use strict";
  var root = document.querySelector('[data-page="baas-gm"]');
  if (!root) return;
  var projectId = root.dataset.projectId || "";
  var serviceId = root.dataset.serviceId || "";
  var canEdit = root.dataset.canEdit === "true";
  var base = "/api/projects/" + encodeURIComponent(projectId) + "/baas/services/" + encodeURIComponent(serviceId) + "/gm";
  var toast = function (m) { alert(m); };

  function csrf() {
    var t = document.querySelector('meta[name="csrf-token"]');
    return t && t.content ? { "X-CSRFToken": t.content } : {};
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  }
  async function api(path, opts) {
    opts = opts || {};
    var method = opts.method || "GET";
    var headers = Object.assign({ "Content-Type": "application/json" }, csrf(), opts.headers || {});
    var r = await fetch(base + path, { method: method, headers: headers, credentials: "same-origin", body: opts.body });
    var d = await r.json().catch(function () { return {}; });
    if (!r.ok || d.ok === false) throw new Error(d.error || "请求失败");
    return d.data;
  }

  document.querySelectorAll("[data-gm-tab]").forEach(function (btn) {
    btn.onclick = function () {
      document.querySelectorAll("[data-gm-tab]").forEach(function (b) { b.classList.remove("is-active"); });
      document.querySelectorAll("[data-gm-pane]").forEach(function (p) { p.classList.remove("is-active"); });
      btn.classList.add("is-active");
      var pane = document.querySelector('[data-gm-pane="' + btn.getAttribute("data-gm-tab") + '"]');
      if (pane) pane.classList.add("is-active");
    };
  });

  async function loadDashboard() {
    var d = await api("/dashboard");
    var host = document.getElementById("baasGmKpis");
    if (!host) return;
    host.innerHTML =
      "<span>玩家 " + esc(d.player_count) + "</span>" +
      "<span>未读邮件 " + esc(d.unread_mail_count) + "</span>" +
      "<span>兑换码 " + esc(d.gift_code_count) + "</span>" +
      "<span>活动 " + esc(d.activity_count || 0) + "</span>";
  }

  async function loadPlayers(q) {
    var rows = await api("/players?q=" + encodeURIComponent(q || "") + "&limit=50");
    var host = document.getElementById("gmPlayerList");
    if (!host) return;
    host.innerHTML = rows.length
      ? rows.map(function (p) {
        return '<div class="baas-gm-row"><span><b>' + esc(p.display_name || p.player_id) + "</b> · " + esc(p.player_id) + "</span>" +
          '<button type="button" data-pid="' + esc(p.player_id) + '">详情</button></div>';
      }).join("")
      : "<div class='baas-gm-row'>暂无玩家</div>";
    host.querySelectorAll("[data-pid]").forEach(function (btn) {
      btn.onclick = function () { showPlayer(btn.getAttribute("data-pid")); };
    });
  }

  async function showPlayer(pid) {
    var d = await api("/players/" + encodeURIComponent(pid));
    var box = document.getElementById("gmPlayerDetail");
    if (!box) return;
    box.classList.remove("is-hidden");
    box.innerHTML = "<pre>" + esc(JSON.stringify(d, null, 2)) + "</pre>";
  }

  document.getElementById("gmPlayerSearchBtn").onclick = function () {
    loadPlayers(document.getElementById("gmPlayerSearch").value).catch(function (e) { toast(e.message); });
  };

  if (canEdit) {
    document.getElementById("gmMailSendBtn").onclick = function () {
      var raw = document.getElementById("gmMailPlayers").value.trim();
      var body = {
        title: document.getElementById("gmMailTitle").value,
        body: document.getElementById("gmMailBody").value,
      };
      try {
        var linksRaw = document.getElementById("gmMailLinks").value.trim();
        if (linksRaw) body.body_links = JSON.parse(linksRaw);
      } catch (e) { toast("链接 JSON 无效"); return; }
      if (raw) body.player_ids = raw.split(/[,，\s]+/).filter(Boolean);
      api("/mail/broadcast", { method: "POST", body: JSON.stringify(body) }).then(function (d) {
        toast("已发送 " + d.sent_count + " 封");
      }).catch(function (e) { toast(e.message); });
    };
    document.getElementById("gmBanBtn").onclick = function () {
      var playerId = document.getElementById("gmBanPlayer").value.trim();
      var ip = document.getElementById("gmBanIp").value.trim();
      var payload = {
        reason: document.getElementById("gmBanReason").value.trim(),
        expires_at: document.getElementById("gmBanExpires").value.trim(),
      };
      if (ip) payload.ip_pattern = ip;
      else payload.player_id = playerId;
      api("/bans", { method: "POST", body: JSON.stringify(payload) }).then(function () {
        loadBans(); toast("封禁已生效");
      }).catch(function (e) { toast(e.message); });
    };
    document.getElementById("gmAnnSaveBtn").onclick = function () {
      api("/announcements", {
        method: "POST",
        body: JSON.stringify({
          title: document.getElementById("gmAnnTitle").value.trim(),
          body: document.getElementById("gmAnnBody").value.trim(),
          display_type: document.getElementById("gmAnnDisplay").value,
          priority: Number(document.getElementById("gmAnnPriority").value || 0),
          status: "published",
        }),
      }).then(function () { loadAnnouncements(); toast("公告已发布"); }).catch(function (e) { toast(e.message); });
    };
    document.getElementById("gmActSaveBtn").onclick = function () {
      var gates, payload;
      try {
        gates = JSON.parse(document.getElementById("gmActGates").value || "{}");
        payload = JSON.parse(document.getElementById("gmActPayload").value || "{}");
      } catch (e) { toast("活动 JSON 无效"); return; }
      api("/activities", {
        method: "POST",
        body: JSON.stringify({
          title: document.getElementById("gmActTitle").value.trim(),
          activity_type: document.getElementById("gmActType").value.trim(),
          starts_at: document.getElementById("gmActStart").value.trim(),
          ends_at: document.getElementById("gmActEnd").value.trim(),
          gates: gates,
          payload: payload,
          status: "published",
        }),
      }).then(function () { loadActivities(); toast("活动已发布"); }).catch(function (e) { toast(e.message); });
    };
    document.getElementById("gmWalletBtn").onclick = function () {
      api("/wallet", {
        method: "POST",
        body: JSON.stringify({
          player_id: document.getElementById("gmWalletPlayer").value.trim(),
          currency_id: document.getElementById("gmWalletCurrency").value.trim(),
          delta: Number(document.getElementById("gmWalletDelta").value),
          reason: document.getElementById("gmWalletReason").value.trim(),
        }),
      }).then(function (d) { toast("余额: " + d.balance); }).catch(function (e) { toast(e.message); });
    };
    document.getElementById("gmGiftSaveBtn").onclick = function () {
      var rewards;
      try { rewards = JSON.parse(document.getElementById("gmGiftRewards").value || "[]"); } catch (e) { toast("奖励 JSON 无效"); return; }
      api("/gift-codes", {
        method: "POST",
        body: JSON.stringify({
          code: document.getElementById("gmGiftCode").value.trim(),
          code_type: document.getElementById("gmGiftType").value,
          assigned_player_id: document.getElementById("gmGiftPlayer").value.trim(),
          max_uses: Number(document.getElementById("gmGiftMax").value),
          per_player_limit: Number(document.getElementById("gmGiftPerPlayer").value),
          expires_at: document.getElementById("gmGiftExpires").value.trim(),
          rewards: rewards,
        }),
      }).then(function () { loadGifts(); toast("已保存"); }).catch(function (e) { toast(e.message); });
    };
    document.getElementById("gmLbResetBtn").onclick = function () {
      if (!confirm("确认清空榜单？")) return;
      var bid = document.getElementById("gmBoardId").value.trim() || "default";
      api("/leaderboards/" + encodeURIComponent(bid), { method: "DELETE" }).then(function () { loadLb(); }).catch(function (e) { toast(e.message); });
    };
  }

  async function loadGifts() {
    var rows = await api("/gift-codes");
    var host = document.getElementById("gmGiftList");
    if (!host) return;
    host.innerHTML = rows.map(function (r) {
      return '<div class="baas-gm-row"><span>' + esc(r.code) + " · " + esc(r.code_type || "shared") + " · " + esc(r.use_count) + "/" + esc(r.max_uses || "∞") + "</span></div>";
    }).join("") || "<div class='baas-gm-row'>暂无兑换码</div>";
  }

  async function loadBans() {
    var d = await api("/bans");
    var host = document.getElementById("gmBanList");
    if (!host) return;
    var lines = (d.player_bans || []).map(function (r) {
      return '<div class="baas-gm-row"><span>玩家 ' + esc(r.player_id) + " · " + esc(r.reason) + '</span></div>';
    }).concat((d.ip_bans || []).map(function (r) {
      return '<div class="baas-gm-row"><span>IP ' + esc(r.ip_pattern) + " · " + esc(r.reason) + '</span></div>';
    }));
    host.innerHTML = lines.join("") || "<div class='baas-gm-row'>暂无封禁</div>";
  }

  async function loadAnnouncements() {
    var rows = await api("/announcements");
    var host = document.getElementById("gmAnnList");
    if (!host) return;
    host.innerHTML = rows.map(function (r) {
      return '<div class="baas-gm-row"><span>' + esc(r.display_type || "login") + " · " + esc(r.title) + "</span></div>";
    }).join("") || "<div class='baas-gm-row'>暂无公告</div>";
  }

  async function loadActivities() {
    var rows = await api("/activities");
    var host = document.getElementById("gmActList");
    if (!host) return;
    host.innerHTML = rows.map(function (r) {
      return '<div class="baas-gm-row"><span>' + esc(r.title) + " · " + esc(r.activity_type) + " · " + esc(r.starts_at) + "~" + esc(r.ends_at) + "</span></div>";
    }).join("") || "<div class='baas-gm-row'>暂无活动</div>";
  }

  async function loadLb() {
    var bid = document.getElementById("gmBoardId").value.trim() || "default";
    var rows = await api("/leaderboards/" + encodeURIComponent(bid));
    var host = document.getElementById("gmLbList");
    if (!host) return;
    host.innerHTML = rows.map(function (r, i) {
      return '<div class="baas-gm-row"><span>#' + (i + 1) + " " + esc(r.display_name || r.player_id) + "</span><span>" + esc(r.score) + "</span></div>";
    }).join("") || "<div class='baas-gm-row'>暂无数据</div>";
  }

  document.getElementById("gmLbLoadBtn").onclick = function () { loadLb().catch(function (e) { toast(e.message); }); };
  document.getElementById("gmCsLoadBtn").onclick = function () {
    var pid = document.getElementById("gmCsPlayer").value.trim();
    var key = document.getElementById("gmCsKey").value.trim();
    var path = "/cloudsave/" + encodeURIComponent(pid) + (key ? "/" + encodeURIComponent(key) : "");
    api(path).then(function (d) {
      document.getElementById("gmCsOut").textContent = JSON.stringify(d, null, 2);
    }).catch(function (e) { toast(e.message); });
  };

  loadDashboard().catch(function () {});
  loadPlayers("").catch(function () {});
  loadGifts().catch(function () {});
  loadBans().catch(function () {});
  loadAnnouncements().catch(function () {});
  loadActivities().catch(function () {});
})();
