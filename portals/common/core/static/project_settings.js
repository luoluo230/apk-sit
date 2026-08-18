(function () {
  "use strict";

  var root = document.querySelector('[data-delivery-page="settings"]');
  if (!root) return;

  var projectId = root.dataset.projectId || "";
  var tab = new URLSearchParams(location.search).get("tab") || "";
  var toast = window.DeliveryCommon && window.DeliveryCommon.toast
    ? window.DeliveryCommon.toast
    : function (msg) { alert(msg); };

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function showMembersPanel() {
    var placeholder = document.querySelector(".pm-placeholder-page");
    var membersPanel = document.getElementById("projectSettingsMembers");
    var archPanel = document.getElementById("projectSettingsArchitecture");
    if (placeholder) placeholder.hidden = tab === "members" || tab === "architecture";
    if (membersPanel) membersPanel.hidden = tab !== "members";
    if (archPanel) archPanel.hidden = tab !== "architecture";
  }

  async function loadServerMode() {
    var response = await fetch("/api/projects/" + encodeURIComponent(projectId) + "/server-mode", { credentials: "same-origin" });
    var data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || "加载失败");
    var row = data.data || {};
    var sel = document.getElementById("settingsServerMode");
    var hint = document.getElementById("settingsCasualHint");
    if (sel) sel.value = row.server_mode === "casual_baas" ? "casual_baas" : "topology";
    if (hint) hint.hidden = sel && sel.value !== "casual_baas";
    if (sel) {
      sel.onchange = function () {
        if (hint) hint.hidden = sel.value !== "casual_baas";
      };
    }
  }

  async function saveServerMode() {
    var sel = document.getElementById("settingsServerMode");
    if (!sel) return;
    var response = await fetch("/api/projects/" + encodeURIComponent(projectId) + "/server-mode", {
      method: "PATCH",
      headers: Object.assign({ "Content-Type": "application/json" }, (function () {
        var token = document.querySelector('meta[name="csrf-token"]');
        return token && token.content ? { "X-CSRFToken": token.content } : {};
      })()),
      credentials: "same-origin",
      body: JSON.stringify({ server_mode: sel.value, env_key: "development" }),
    });
    var data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || "保存失败");
    if (data.data && data.data.api_secret) {
      toast("已切换为轻度 BaaS。API Secret: " + data.data.api_secret, "success");
    } else {
      toast("架构设置已保存", "success");
    }
  }

  function memberRole(username, project) {
    if (String(project.created_by || "") === username) return "owner";
    if ((project.editors || []).indexOf(username) >= 0) return "editor";
    return "viewer";
  }

  function renderMembers(members) {
    var host = document.getElementById("settingsMemberList");
    if (!host) return;
    if (!members.length) {
      host.innerHTML = '<div class="p02-empty">暂无项目成员</div>';
      return;
    }
    host.innerHTML = members.map(function (member) {
      var isOwner = member.role === "owner";
      var roleSelect = isOwner
        ? '<em class="p02-role">' + esc(member.role_label || "项目负责人") + "</em>"
        : (
          '<select class="p02-role-select" data-member-role data-username="' + esc(member.username) + '">' +
          '<option value="editor"' + (member.role === "editor" ? " selected" : "") + ">编辑者</option>" +
          '<option value="viewer"' + (member.role === "viewer" ? " selected" : "") + ">查看者</option>" +
          "</select>"
        );
      var removeBtn = isOwner
        ? ""
        : '<button type="button" class="pm-btn pm-btn--ghost" data-member-remove data-username="' + esc(member.username) + '">移除</button>';
      return (
        '<div class="p02-member-row">' +
        '<img class="p02-member-avatar" src="/static/project_ui/svg/global_user.svg" alt="">' +
        "<b>" + esc(member.username) + "</b>" +
        roleSelect +
        removeBtn +
        "</div>"
      );
    }).join("");
  }

  function buildUpdatePayload(project, mutate) {
    var payload = {
      id: projectId,
      name: project.name,
      name_en: project.name_en,
      intro: project.intro,
      editors: (project.editors || []).slice(),
      viewers: (project.viewers || []).slice(),
      member_roles: Object.assign({}, project.member_roles || {}),
    };
    mutate(payload);
    return payload;
  }

  async function saveProject(payload) {
    var response = await fetch("/admin/projects/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
    var data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || "保存失败");
    await loadProject();
    return data;
  }

  async function loadProject() {
    var response = await fetch("/admin/projects/get/" + encodeURIComponent(projectId), { credentials: "same-origin" });
    var data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || "加载项目失败");
    var project = data.project || data;
    var members = [];
    var seen = {};
    function append(username, role, roleLabel) {
      var user = String(username || "").trim();
      if (!user || seen[user]) return;
      seen[user] = true;
      members.push({ username: user, role: role, role_label: roleLabel });
    }
    append(project.created_by, "owner", "项目负责人");
    (project.editors || []).forEach(function (u) { append(u, "editor", "编辑者"); });
    (project.viewers || []).forEach(function (u) {
      if ((project.editors || []).indexOf(u) >= 0) return;
      append(u, "viewer", "查看者");
    });
    renderMembers(members);
    window.__settingsProject = project;
  }

  async function inviteMember() {
    var input = document.getElementById("settingsInviteUsername");
    var roleSelect = document.getElementById("settingsInviteRole");
    if (!input || !roleSelect) return;
    var username = String(input.value || "").trim();
    var role = String(roleSelect.value || "viewer");
    if (!username) {
      toast("请输入用户名", "error");
      return;
    }
    var project = window.__settingsProject || {};
    await saveProject(buildUpdatePayload(project, function (payload) {
      if (role === "editor" && payload.editors.indexOf(username) < 0) payload.editors.push(username);
      if (role === "viewer" && payload.viewers.indexOf(username) < 0) payload.viewers.push(username);
      payload.member_roles[username] = role === "editor" ? "编辑者" : "查看者";
    }));
    input.value = "";
    toast("成员已添加", "success");
  }

  async function removeMember(username) {
    var user = String(username || "").trim();
    if (!user) return;
    var project = window.__settingsProject || {};
    if (String(project.created_by || "") === user) {
      toast("不能移除项目负责人", "error");
      return;
    }
    await saveProject(buildUpdatePayload(project, function (payload) {
      payload.editors = payload.editors.filter(function (u) { return u !== user; });
      payload.viewers = payload.viewers.filter(function (u) { return u !== user; });
      delete payload.member_roles[user];
    }));
    toast("成员已移除", "success");
  }

  async function changeMemberRole(username, role) {
    var user = String(username || "").trim();
    if (!user) return;
    var project = window.__settingsProject || {};
    if (String(project.created_by || "") === user) return;
    await saveProject(buildUpdatePayload(project, function (payload) {
      payload.editors = payload.editors.filter(function (u) { return u !== user; });
      payload.viewers = payload.viewers.filter(function (u) { return u !== user; });
      if (role === "editor") payload.editors.push(user);
      if (role === "viewer") payload.viewers.push(user);
      payload.member_roles[user] = role === "editor" ? "编辑者" : "查看者";
    }));
    toast("成员角色已更新", "success");
  }

  showMembersPanel();
  if (tab === "architecture") {
    loadServerMode().catch(function (error) {
      toast(error.message || "加载失败", "error");
    });
    var archBtn = document.getElementById("settingsSaveServerMode");
    if (archBtn) archBtn.onclick = function () { saveServerMode().catch(function (e) { toast(e.message, "error"); }); };
  }
  if (tab === "members") {
    loadProject().catch(function (error) {
      toast(error.message || "加载失败", "error");
    });
    var btn = document.getElementById("settingsInviteBtn");
    if (btn) btn.onclick = function () { inviteMember().catch(function (e) { toast(e.message, "error"); }); };
    var list = document.getElementById("settingsMemberList");
    if (list) {
      list.addEventListener("click", function (event) {
        var removeBtn = event.target.closest("[data-member-remove]");
        if (removeBtn) {
          removeMember(removeBtn.getAttribute("data-username")).catch(function (e) { toast(e.message, "error"); });
        }
      });
      list.addEventListener("change", function (event) {
        var roleSelect = event.target.closest("[data-member-role]");
        if (roleSelect) {
          changeMemberRole(roleSelect.getAttribute("data-username"), roleSelect.value).catch(function (e) {
            toast(e.message, "error");
          });
        }
      });
    }
  }
})();
