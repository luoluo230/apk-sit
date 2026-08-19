(function () {
  "use strict";

  var root = document.querySelector('[data-delivery-page="baas-gm"]');
  if (!root) return;

  var projectId = root.dataset.projectId || "";
  var serviceId = root.dataset.serviceId || "";
  var canEdit = root.dataset.canEdit === "true";
  var base = "/api/projects/" + encodeURIComponent(projectId) + "/baas/services/" + encodeURIComponent(serviceId) + "/gm";
  var activePane = "overview";

  var toast = window.DeliveryCommon && window.DeliveryCommon.toast
    ? function (m, t) { window.DeliveryCommon.toast(m, t || "info"); }
    : function (m) { alert(m); };

  var NAV = [
    { group: "概览", items: [{ id: "overview", label: "运营概览" }] },
    { group: "玩家运营", items: [{ id: "players", label: "玩家查询" }, { id: "moderation", label: "封禁与禁言" }] },
    { group: "触达", items: [{ id: "mail", label: "邮件补偿" }, { id: "templates", label: "邮件模板" }, { id: "announce", label: "公告跑马灯" }] },
    { group: "活动留存", items: [{ id: "gifts", label: "兑换码" }, { id: "activities", label: "活动配置" }] },
    { group: "经济数据", items: [{ id: "wallet", label: "钱包调整" }, { id: "items", label: "道具发放" }, { id: "leaderboard", label: "排行榜" }, { id: "cloudsave", label: "云存档" }] },
    { group: "GameServer", items: [{ id: "gameserver", label: "在线运维" }] },
    { group: "治理", items: [{ id: "audit", label: "审计日志" }, { id: "coverage", label: "能力清单" }] }
  ];

  var COVERAGE = [
    { title: "玩家查询 / 详情", status: "done", note: "本页已支持搜索与 JSON 详情。" },
    { title: "账号封禁 / IP 封禁", status: "done", note: "moderation 页签；登录时校验 baas_player_bans。" },
    { title: "禁言", status: "done", note: "写入 profile.mute_until；客户端可按字段限制发言。" },
    { title: "邮件 + 链接 JSON", status: "done", note: "body_links 供客户端解析领奖。" },
    { title: "邮件模板库", status: "done", note: "templates 页签保存/复用标题、正文、附件。" },
    { title: "道具发放（邮件附件）", status: "done", note: "items 页签通过 attachments 发放道具。" },
    { title: "登录公告 / 跑马灯", status: "done", note: "display_type=login|marquee|all。" },
    { title: "兑换码（多类型）", status: "done", note: "共用 / 个人 / 补偿 + 单人上限。" },
    { title: "活动门槛配置", status: "done", note: "等级 / VIP / 充值门槛 + 客户端 active API。" },
    { title: "钱包 / 排行榜 / 云存档", status: "done", note: "经济类运维已覆盖。" },
    { title: "在线踢人 / 顶号", status: "done", note: "gameserver 页签 → Ops kick-session + NotifyKickOff。" },
    { title: "GameServer 运维停服广播", status: "done", note: "维护广播 + Gateway stop（StopAsync NotifyKickOff）。" },
    { title: "审计日志 UI", status: "done", note: "audit 页签展示 baas_gm* 操作记录。" }
  ];

  function csrf() {
    var t = document.querySelector('meta[name="csrf-token"]');
    return t && t.content ? { "X-CSRFToken": t.content } : {};
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
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

  function renderNav() {
    var host = document.getElementById("gmNav");
    if (!host) return;
    var html = "";
    NAV.forEach(function (g) {
      html += '<div class="baas-nav-group">' + esc(g.group) + "</div>";
      g.items.forEach(function (item) {
        var cls = item.id === activePane ? " baas-nav-item is-active" : " baas-nav-item";
        html += '<button type="button" class="' + cls.trim() + '" data-pane="' + esc(item.id) + '">' + esc(item.label) + "</button>";
      });
    });
    host.innerHTML = html;
    host.querySelectorAll("[data-pane]").forEach(function (btn) {
      btn.onclick = function () { switchPane(btn.getAttribute("data-pane")); };
    });
  }

  function switchPane(id) {
    activePane = id || "overview";
    renderNav();
    document.querySelectorAll(".baas-gm-pane").forEach(function (p) {
      p.classList.toggle("is-active", p.getAttribute("data-pane") === activePane);
    });
  }

  function renderCoverage() {
    var host = document.getElementById("gmCoverageGrid");
    if (!host) return;
    host.innerHTML = COVERAGE.map(function (c) {
      var cls = c.status === "done" ? "is-done" : (c.status === "bridge" ? "" : "is-pending");
      var tag = c.status === "done" ? '<span class="baas-tag baas-tag--ok">已覆盖</span>'
        : (c.status === "bridge" ? '<span class="baas-tag baas-tag--bridge">GameServer</span>' : '<span class="baas-tag baas-tag--todo">待补</span>');
      return '<article class="baas-gap-card ' + cls + '"><h3>' + esc(c.title) + " " + tag + "</h3><p>" + esc(c.note) + "</p></article>";
    }).join("");
  }

  async function loadDashboard() {
    var d = await api("/dashboard");
    var kpi = document.getElementById("baasGmKpis");
    var ov = document.getElementById("gmOverviewStats");
    var chips =
      '<span class="baas-kpi-chip">玩家 <b>' + esc(d.player_count) + "</b></span>" +
      '<span class="baas-kpi-chip">未读邮件 <b>' + esc(d.unread_mail_count) + "</b></span>" +
      '<span class="baas-kpi-chip">兑换码 <b>' + esc(d.gift_code_count) + "</b></span>" +
      '<span class="baas-kpi-chip">活动 <b>' + esc(d.activity_count || 0) + "</b></span>";
    if (kpi) kpi.innerHTML = chips;
    if (ov) ov.innerHTML = chips;
    var annHost = document.getElementById("gmOverviewAnnounce");
    if (annHost) {
      var anns = d.announcements || [];
      annHost.innerHTML = anns.length
        ? anns.map(function (a) {
          return '<div class="baas-list-row"><div><div>' + esc(a.title) + '</div><div class="meta">' + esc(a.display_type || "login") + " · " + esc(a.updated_at) + "</div></div></div>";
        }).join("")
        : '<div class="baas-list-row"><span>暂无公告</span></div>';
    }
  }

  async function loadPlayers(q) {
    var rows = await api("/players?q=" + encodeURIComponent(q || "") + "&limit=50");
    var host = document.getElementById("gmPlayerList");
    if (!host) return;
    host.innerHTML = rows.length
      ? rows.map(function (p) {
        return '<div class="baas-list-row"><div><div><b>' + esc(p.display_name || p.player_id) + "</b></div><div class=\"meta\">" + esc(p.player_id) + "</div></div>" +
          '<div class="actions">' +
          '<button type="button" class="pm-btn pm-btn--ghost" data-act="detail" data-pid="' + esc(p.player_id) + '">详情</button>' +
          (canEdit ? '<button type="button" class="pm-btn pm-btn--ghost" data-act="mail" data-pid="' + esc(p.player_id) + '">发邮件</button>' : "") +
          "</div></div>";
      }).join("")
      : '<div class="baas-list-row"><span>暂无玩家</span></div>';
    host.querySelectorAll("[data-act]").forEach(function (btn) {
      btn.onclick = function () {
        var pid = btn.getAttribute("data-pid");
        if (btn.getAttribute("data-act") === "mail") {
          switchPane("mail");
          document.getElementById("gmMailPlayers").value = pid;
        } else {
          showPlayer(pid);
        }
      };
    });
  }

  async function showPlayer(pid) {
    var d = await api("/players/" + encodeURIComponent(pid));
    var box = document.getElementById("gmPlayerDetail");
    if (!box) return;
    box.classList.remove("is-hidden");
    box.innerHTML = "<pre>" + esc(JSON.stringify(d, null, 2)) + "</pre>";
  }

  async function loadBans() {
    var d = await api("/bans");
    var host = document.getElementById("gmBanList");
    if (!host) return;
    var lines = (d.player_bans || []).map(function (r) {
      return '<div class="baas-list-row"><div><div>账号 ' + esc(r.player_id) + '</div><div class="meta">' + esc(r.reason) + " · 至 " + esc(r.expires_at || "永久") + "</div></div>" +
        (canEdit ? '<div class="actions"><button type="button" class="pm-btn pm-btn--ghost" data-unban-player="' + esc(r.player_id) + '">解封</button></div>' : "") + "</div>";
    }).concat((d.ip_bans || []).map(function (r) {
      return '<div class="baas-list-row"><div><div>IP ' + esc(r.ip_pattern) + '</div><div class="meta">' + esc(r.reason) + "</div></div>" +
        (canEdit ? '<div class="actions"><button type="button" class="pm-btn pm-btn--ghost" data-unban-ip="' + esc(r.ip_pattern) + '">解封</button></div>' : "") + "</div>";
    }));
    if ((d.mutes || []).length) {
      lines = lines.concat((d.mutes || []).map(function (r) {
        return '<div class="baas-list-row"><div><div>禁言 ' + esc(r.player_id) + '</div><div class="meta">至 ' + esc(r.mute_until || "") + " · " + esc(r.reason || "") + "</div></div>" +
          (canEdit ? '<div class="actions"><button type="button" class="pm-btn pm-btn--ghost" data-unmute="' + esc(r.player_id) + '">解除</button></div>' : "") + "</div>";
      }));
    }
    host.innerHTML = lines.join("") || '<div class="baas-list-row"><span>暂无封禁记录</span></div>';
    host.querySelectorAll("[data-unban-player]").forEach(function (btn) {
      btn.onclick = function () {
        api("/bans", { method: "DELETE", body: JSON.stringify({ player_id: btn.getAttribute("data-unban-player") }) })
          .then(function () { loadBans(); toast("已解封", "success"); })
          .catch(function (e) { toast(e.message, "error"); });
      };
    });
    host.querySelectorAll("[data-unban-ip]").forEach(function (btn) {
      btn.onclick = function () {
        api("/bans", { method: "DELETE", body: JSON.stringify({ ip_pattern: btn.getAttribute("data-unban-ip") }) })
          .then(function () { loadBans(); toast("已解封 IP", "success"); })
          .catch(function (e) { toast(e.message, "error"); });
      };
    });
    host.querySelectorAll("[data-unmute]").forEach(function (btn) {
      btn.onclick = function () {
        api("/mutes", { method: "DELETE", body: JSON.stringify({ player_id: btn.getAttribute("data-unmute") }) })
          .then(function () { loadBans(); toast("已解除禁言", "success"); })
          .catch(function (e) { toast(e.message, "error"); });
      };
    });
  }

  async function loadGifts() {
    var rows = await api("/gift-codes");
    var host = document.getElementById("gmGiftList");
    if (!host) return;
    host.innerHTML = rows.map(function (r) {
      return '<div class="baas-list-row"><div><div>' + esc(r.code) + " · " + esc(r.code_type || "shared") + '</div><div class="meta">已用 ' + esc(r.use_count) + " / " + esc(r.max_uses || "∞") + "</div></div></div>";
    }).join("") || '<div class="baas-list-row"><span>暂无兑换码</span></div>';
  }

  async function loadAnnouncements() {
    var rows = await api("/announcements");
    var host = document.getElementById("gmAnnList");
    if (!host) return;
    host.innerHTML = rows.map(function (r) {
      return '<div class="baas-list-row"><div><div>' + esc(r.title) + '</div><div class="meta">' + esc(r.display_type || "login") + " · P" + esc(r.priority) + "</div></div></div>";
    }).join("") || '<div class="baas-list-row"><span>暂无公告</span></div>';
  }

  async function loadActivities() {
    var rows = await api("/activities");
    var host = document.getElementById("gmActList");
    if (!host) return;
    host.innerHTML = rows.map(function (r) {
      return '<div class="baas-list-row"><div><div>' + esc(r.title) + '</div><div class="meta">' + esc(r.activity_type) + " · " + esc(r.starts_at) + " ~ " + esc(r.ends_at) + "</div></div></div>";
    }).join("") || '<div class="baas-list-row"><span>暂无活动</span></div>';
  }

  async function loadLb() {
    var bid = document.getElementById("gmBoardId").value.trim() || "default";
    var rows = await api("/leaderboards/" + encodeURIComponent(bid));
    var host = document.getElementById("gmLbList");
    if (!host) return;
    host.innerHTML = rows.map(function (r, i) {
      return '<div class="baas-list-row"><div>#' + (i + 1) + " " + esc(r.display_name || r.player_id) + '</div><div>' + esc(r.score) + "</div></div>";
    }).join("") || '<div class="baas-list-row"><span>暂无数据</span></div>';
  }

  async function loadTemplates() {
    var rows = await api("/mail-templates");
    var host = document.getElementById("gmTplList");
    if (!host) return;
    host.innerHTML = rows.map(function (r) {
      return '<div class="baas-list-row"><div><div>' + esc(r.title) + '</div><div class="meta">' + esc(r.template_id) + " · " + esc(r.updated_at || "") + '</div></div>' +
        (canEdit ? '<div class="actions"><button type="button" class="pm-btn pm-btn--ghost" data-use-tpl="' + esc(r.template_id) + '">套用</button>' +
        '<button type="button" class="pm-btn pm-btn--ghost" data-del-tpl="' + esc(r.template_id) + '">删除</button></div>' : "") + "</div>";
    }).join("") || '<div class="baas-list-row"><span>暂无模板</span></div>';
    host.querySelectorAll("[data-use-tpl]").forEach(function (btn) {
      btn.onclick = function () {
        var id = btn.getAttribute("data-use-tpl");
        var tpl = rows.find(function (x) { return x.template_id === id; });
        if (!tpl) return;
        switchPane("mail");
        document.getElementById("gmMailTitle").value = tpl.title || "";
        document.getElementById("gmMailBody").value = tpl.body || "";
        document.getElementById("gmMailLinks").value = JSON.stringify(tpl.body_links || [], null, 2);
        toast("已套用模板", "success");
      };
    });
    host.querySelectorAll("[data-del-tpl]").forEach(function (btn) {
      btn.onclick = function () {
        api("/mail-templates", { method: "DELETE", body: JSON.stringify({ template_id: btn.getAttribute("data-del-tpl") }) })
          .then(function () { loadTemplates(); toast("已删除", "success"); })
          .catch(function (e) { toast(e.message, "error"); });
      };
    });
  }

  async function loadAudit() {
    var rows = await api("/audit?limit=80");
    var host = document.getElementById("gmAuditList");
    if (!host) return;
    host.innerHTML = rows.map(function (r) {
      return '<div class="baas-list-row"><div><div>' + esc(r.action) + " · " + esc(r.user || "") + '</div><div class="meta">' + esc(r.timestamp) + " · " + esc(r.details || "") + "</div></div></div>";
    }).join("") || '<div class="baas-list-row"><span>暂无审计记录</span></div>';
  }

  async function loadGsHealth() {
    var host = document.getElementById("gmGsHealth");
    if (!host) return;
    try {
      var d = await api("/gameserver/health");
      host.innerHTML = '<span class="baas-kpi-chip">Ops <b>' + (d.success === true || d.ready ? "在线" : "可达") + "</b></span>";
    } catch (e) {
      host.innerHTML = '<span class="baas-kpi-chip">Ops <b>离线</b></span><span class="meta">' + esc(e.message) + "</span>";
    }
  }

  function bindActions() {
    document.getElementById("gmCopyServiceId").onclick = function () {
      var text = document.getElementById("gmServiceId").textContent;
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(function () { toast("已复制", "success"); });
    };
    document.getElementById("gmPlayerSearchBtn").onclick = function () {
      loadPlayers(document.getElementById("gmPlayerSearch").value).catch(function (e) { toast(e.message, "error"); });
    };
    document.getElementById("gmLbLoadBtn").onclick = function () { loadLb().catch(function (e) { toast(e.message, "error"); }); };
    document.getElementById("gmCsLoadBtn").onclick = function () {
      var pid = document.getElementById("gmCsPlayer").value.trim();
      var key = document.getElementById("gmCsKey").value.trim();
      var path = "/cloudsave/" + encodeURIComponent(pid) + (key ? "/" + encodeURIComponent(key) : "");
      api(path).then(function (d) {
        document.getElementById("gmCsOut").textContent = JSON.stringify(d, null, 2);
      }).catch(function (e) { toast(e.message, "error"); });
    };
    if (!canEdit) return;
    document.getElementById("gmMailSendBtn").onclick = function () {
      var raw = document.getElementById("gmMailPlayers").value.trim();
      var body = { title: document.getElementById("gmMailTitle").value, body: document.getElementById("gmMailBody").value };
      try {
        var linksRaw = document.getElementById("gmMailLinks").value.trim();
        if (linksRaw) body.body_links = JSON.parse(linksRaw);
      } catch (e) { toast("链接 JSON 无效", "error"); return; }
      if (raw) body.player_ids = raw.split(/[,，\s]+/).filter(Boolean);
      api("/mail/broadcast", { method: "POST", body: JSON.stringify(body) }).then(function (d) {
        toast("已发送 " + d.sent_count + " 封", "success");
      }).catch(function (e) { toast(e.message, "error"); });
    };
    document.getElementById("gmBanBtn").onclick = function () {
      var playerId = document.getElementById("gmBanPlayer").value.trim();
      var ip = document.getElementById("gmBanIp").value.trim();
      var payload = {
        reason: document.getElementById("gmBanReason").value.trim(),
        expires_at: document.getElementById("gmBanExpires").value.trim()
      };
      if (ip) payload.ip_pattern = ip; else payload.player_id = playerId;
      api("/bans", { method: "POST", body: JSON.stringify(payload) }).then(function () {
        loadBans(); toast("封禁已生效", "success");
      }).catch(function (e) { toast(e.message, "error"); });
    };
    document.getElementById("gmMuteBtn").onclick = function () {
      var pid = document.getElementById("gmBanPlayer").value.trim();
      if (!pid) { toast("请填写玩家 ID", "error"); return; }
      api("/mutes", {
        method: "POST",
        body: JSON.stringify({
          player_id: pid,
          hours: Number(document.getElementById("gmMuteHours").value || 0),
          reason: document.getElementById("gmBanReason").value.trim()
        })
      }).then(function () { loadBans(); toast("禁言已更新", "success"); })
        .catch(function (e) { toast(e.message, "error"); });
    };
    document.getElementById("gmAnnSaveBtn").onclick = function () {
      api("/announcements", {
        method: "POST",
        body: JSON.stringify({
          title: document.getElementById("gmAnnTitle").value.trim(),
          body: document.getElementById("gmAnnBody").value.trim(),
          display_type: document.getElementById("gmAnnDisplay").value,
          priority: Number(document.getElementById("gmAnnPriority").value || 0),
          status: "published"
        })
      }).then(function () { loadAnnouncements(); loadDashboard(); toast("公告已发布", "success"); })
        .catch(function (e) { toast(e.message, "error"); });
    };
    document.getElementById("gmActSaveBtn").onclick = function () {
      var gates, payload;
      try {
        gates = JSON.parse(document.getElementById("gmActGates").value || "{}");
        payload = JSON.parse(document.getElementById("gmActPayload").value || "{}");
      } catch (e) { toast("活动 JSON 无效", "error"); return; }
      api("/activities", {
        method: "POST",
        body: JSON.stringify({
          title: document.getElementById("gmActTitle").value.trim(),
          activity_type: document.getElementById("gmActType").value.trim(),
          starts_at: document.getElementById("gmActStart").value.trim(),
          ends_at: document.getElementById("gmActEnd").value.trim(),
          gates: gates,
          payload: payload,
          status: "published"
        })
      }).then(function () { loadActivities(); loadDashboard(); toast("活动已发布", "success"); })
        .catch(function (e) { toast(e.message, "error"); });
    };
    document.getElementById("gmWalletBtn").onclick = function () {
      api("/wallet", {
        method: "POST",
        body: JSON.stringify({
          player_id: document.getElementById("gmWalletPlayer").value.trim(),
          currency_id: document.getElementById("gmWalletCurrency").value.trim(),
          delta: Number(document.getElementById("gmWalletDelta").value),
          reason: document.getElementById("gmWalletReason").value.trim()
        })
      }).then(function (d) { toast("余额: " + d.balance, "success"); }).catch(function (e) { toast(e.message, "error"); });
    };
    document.getElementById("gmGiftSaveBtn").onclick = function () {
      var rewards;
      try { rewards = JSON.parse(document.getElementById("gmGiftRewards").value || "[]"); } catch (e) { toast("奖励 JSON 无效", "error"); return; }
      api("/gift-codes", {
        method: "POST",
        body: JSON.stringify({
          code: document.getElementById("gmGiftCode").value.trim(),
          code_type: document.getElementById("gmGiftType").value,
          assigned_player_id: document.getElementById("gmGiftPlayer").value.trim(),
          max_uses: Number(document.getElementById("gmGiftMax").value),
          per_player_limit: Number(document.getElementById("gmGiftPerPlayer").value),
          expires_at: document.getElementById("gmGiftExpires").value.trim(),
          rewards: rewards
        })
      }).then(function () { loadGifts(); toast("已保存", "success"); }).catch(function (e) { toast(e.message, "error"); });
    };
    document.getElementById("gmLbResetBtn").onclick = function () {
      if (!confirm("确认清空榜单？")) return;
      var bid = document.getElementById("gmBoardId").value.trim() || "default";
      api("/leaderboards/" + encodeURIComponent(bid), { method: "DELETE" }).then(function () { loadLb(); toast("已清空", "success"); })
        .catch(function (e) { toast(e.message, "error"); });
    };
    var itemBtn = document.getElementById("gmItemGrantBtn");
    if (itemBtn) itemBtn.onclick = function () {
      var items;
      try { items = JSON.parse(document.getElementById("gmItemJson").value || "[]"); } catch (e) { toast("道具 JSON 无效", "error"); return; }
      api("/grant-items", {
        method: "POST",
        body: JSON.stringify({
          player_id: document.getElementById("gmItemPlayer").value.trim(),
          title: document.getElementById("gmItemTitle").value.trim(),
          body: document.getElementById("gmItemBody").value.trim(),
          items: items
        })
      }).then(function () { toast("道具邮件已发送", "success"); loadAudit(); })
        .catch(function (e) { toast(e.message, "error"); });
    };
    var tplBtn = document.getElementById("gmTplSaveBtn");
    if (tplBtn) tplBtn.onclick = function () {
      var attachments, links;
      try {
        attachments = JSON.parse(document.getElementById("gmTplAttachments").value || "[]");
        links = JSON.parse(document.getElementById("gmTplLinks").value || "[]");
      } catch (e) { toast("模板 JSON 无效", "error"); return; }
      api("/mail-templates", {
        method: "POST",
        body: JSON.stringify({
          template_id: document.getElementById("gmTplId").value.trim(),
          title: document.getElementById("gmTplTitle").value.trim(),
          body: document.getElementById("gmTplBody").value.trim(),
          attachments: attachments,
          body_links: links
        })
      }).then(function () { loadTemplates(); toast("模板已保存", "success"); })
        .catch(function (e) { toast(e.message, "error"); });
    };
    var gsHealthBtn = document.getElementById("gmGsHealthBtn");
    if (gsHealthBtn) gsHealthBtn.onclick = function () { loadGsHealth().catch(function (e) { toast(e.message, "error"); }); };
    var gsKickBtn = document.getElementById("gmGsKickBtn");
    if (gsKickBtn) gsKickBtn.onclick = function () {
      var target = document.getElementById("gmGsKickTarget").value.trim();
      if (!target) { toast("请填写玩家 ID 或 token", "error"); return; }
      var body = target.indexOf("_") >= 0 && target.length < 64 ? { player_id: target } : { session_token: target };
      api("/gameserver/kick", { method: "POST", body: JSON.stringify(body) })
        .then(function () { toast("踢人请求已发送", "success"); loadAudit(); })
        .catch(function (e) { toast(e.message, "error"); });
    };
    var gsMaintBtn = document.getElementById("gmGsMaintBtn");
    if (gsMaintBtn) gsMaintBtn.onclick = function () {
      api("/gameserver/maintenance", {
        method: "POST",
        body: JSON.stringify({ message: document.getElementById("gmGsMessage").value.trim() })
      }).then(function () { toast("维护广播已触发", "success"); loadAudit(); })
        .catch(function (e) { toast(e.message, "error"); });
    };
    var gsStopBtn = document.getElementById("gmGsStopBtn");
    if (gsStopBtn) gsStopBtn.onclick = function () {
      if (!confirm("确认停服 Gateway？在线玩家将收到踢线通知。")) return;
      api("/gameserver/stop", {
        method: "POST",
        body: JSON.stringify({ message: document.getElementById("gmGsMessage").value.trim() })
      }).then(function () { toast("停服指令已发送", "success"); loadGsHealth(); loadAudit(); })
        .catch(function (e) { toast(e.message, "error"); });
    };
    var auditBtn = document.getElementById("gmAuditRefreshBtn");
    if (auditBtn) auditBtn.onclick = function () { loadAudit().catch(function (e) { toast(e.message, "error"); }); };
  }

  renderNav();
  renderCoverage();
  bindActions();
  loadDashboard().catch(function () {});
  loadPlayers("").catch(function () {});
  loadGifts().catch(function () {});
  loadBans().catch(function () {});
  loadAnnouncements().catch(function () {});
  loadActivities().catch(function () {});
  loadTemplates().catch(function () {});
  loadAudit().catch(function () {});
  loadGsHealth().catch(function () {});
})();
