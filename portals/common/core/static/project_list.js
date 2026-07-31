(function () {
  "use strict";

  var initEl = document.getElementById("p01InitData");
  var INIT = {};
  try {
    INIT = JSON.parse((initEl && initEl.textContent) || "{}");
  } catch (e) {
    INIT = {};
  }

  var ROLES = INIT.roles || [];
  var ALL_CHANNELS = INIT.channels || [];
  var allProjectsCache = [];
  var newParticipants = [];
  var editParticipants = [];
  var _participantCtx = "";
  var _pendingParticipantUser = "";
  var _channelsCache = [];
  var state = {
    view: "card",
    page: 1,
    pageSize: 12,
    search: "",
    status: "",
    owner: "",
    health: "",
  };

  function el(id) {
    return document.getElementById(id);
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  var DL = window.PmDisplayLabels || {};

  var fav = window.PmUserFavorites;

  function favoriteIds() {
    if (fav && fav.readCache) {
      return fav.readCache().project_favorites || [];
    }
    try {
      return JSON.parse(localStorage.getItem("p01_project_favorites") || "[]");
    } catch (e) {
      return [];
    }
  }

  function isFavorite(id) {
    if (fav && fav.isProjectFavorite) return fav.isProjectFavorite(id);
    return favoriteIds().indexOf(id) >= 0;
  }

  function toggleFavorite(id) {
    if (fav && fav.toggleProjectFavorite) {
      fav.toggleProjectFavorite(id).catch(function () {
        var ids = favoriteIds();
        var idx = ids.indexOf(id);
        if (idx >= 0) ids.splice(idx, 1);
        else ids.push(id);
        localStorage.setItem("p01_project_favorites", JSON.stringify(ids));
      });
      return;
    }
    var ids = favoriteIds();
    var idx = ids.indexOf(id);
    if (idx >= 0) ids.splice(idx, 1);
    else ids.push(id);
    localStorage.setItem("p01_project_favorites", JSON.stringify(ids));
  }

  function formatTime(raw) {
    return DL.formatShortTime ? DL.formatShortTime(raw) : String(raw || "").slice(11, 16) || "--";
  }

  function releaseTagClass(tone) {
    if (tone === "success") return "success";
    if (tone === "danger") return "danger";
    if (tone === "warning") return "warning";
    return "muted";
  }

  function healthMetricClass(pct, archived) {
    return DL.healthTone ? DL.healthTone(pct, archived) : "muted";
  }

  function projectCardLinks(id) {
    var enc = encodeURIComponent(id);
    var base = "/admin/projects/" + enc;
    return {
      health: base + "/overview?tab=environments",
      version: base + "/versions",
      pending: "/admin/approval?project_id=" + enc,
      blockers: base + "/overview?tab=channels",
      releaseHub: base + "/versions",
    };
  }

  function releaseLink(p, archived) {
    if (archived) return "";
    return projectCardLinks(p.id).releaseHub;
  }

  function setMetricHref(node, key, href, archived) {
    var metric = node.querySelector('[data-metric="' + key + '"]');
    if (!metric) return;
    if (!archived && href) {
      metric.setAttribute("href", href);
      metric.classList.remove("is-disabled");
    } else {
      metric.removeAttribute("href");
      metric.classList.add("is-disabled");
    }
  }

  function fillProjectCard(node, p) {
    var archived = p.status === "archived" || p.card_status === "archived";
    var statusKey = archived ? "archived" : p.card_status || "running";
    var statusInfo = DL.cardStatus
      ? DL.cardStatus(statusKey, p.card_status_label)
      : { label: p.card_status_label || (archived ? "已归档" : "运行中"), tone: statusKey };

    node.setAttribute("data-project-id", p.id);
    node.classList.toggle("is-archived", archived);

    var iconImg = node.querySelector(".pm-project-card__icon img");
    if (iconImg) {
      iconImg.src = p.icon || "/static/project_ui/svg/nav_project_overview.svg";
      iconImg.alt = "";
    }
    var title = node.querySelector(".pm-project-card__title-row h3") || node.querySelector(".pm-project-card__title h3");
    if (title) title.textContent = p.name || p.id || "—";

    var statusEl = node.querySelector(".pm-project-card__status");
    if (statusEl) {
      statusEl.className = "pm-project-card__status " + (statusInfo.tone || statusKey);
      var statusLabel = node.querySelector(".pm-project-card__status-label");
      if (statusLabel) statusLabel.textContent = statusInfo.label || "运行中";
    }

    var starBtn = node.querySelector(".pm-project-card__star");
    if (starBtn) starBtn.classList.toggle("is-favorite", isFavorite(p.id));

    node.querySelectorAll("[data-card-menu]").forEach(function (btn) {
      btn.setAttribute("data-card-menu", p.id);
    });

    var ownerName = node.querySelector(".pm-project-card__owner-name");
    if (ownerName) ownerName.textContent = p.owner || p.created_by || "—";
    var updated = node.querySelector(".pm-project-card__updated");
    if (updated) updated.textContent = "最后更新: " + formatTime(p.updated_at || p.created_at);

    var healthTone = healthMetricClass(p.env_health_pct, archived);
    var healthText = archived || p.env_health_pct == null ? "—" : p.env_health_pct + "%";
    var healthSub = DL.healthSublabel ? DL.healthSublabel(p.env_health_pct, archived) : "";
    setMetric(node, "health", healthText, healthTone, healthSub);

    var prodText = archived || !p.prod_version ? "—" : String(p.prod_version);
    setMetric(node, "version", prodText, archived ? "muted" : "", "");

    var pendingNum = archived ? "—" : String(p.pending_approval || 0);
    setMetric(node, "pending", pendingNum, archived ? "muted" : Number(pendingNum) > 0 ? "warn" : "", "");

    var blockerNum = archived ? "—" : String(p.blocker_count || 0);
    setMetric(node, "blockers", blockerNum, archived ? "muted" : Number(blockerNum) > 0 ? "bad" : "", "");

    var links = projectCardLinks(p.id);
    setMetricHref(node, "health", links.health, archived);
    setMetricHref(node, "version", links.version, archived);
    setMetricHref(node, "pending", links.pending, archived);
    setMetricHref(node, "blockers", links.blockers, archived);

    var releaseHost = node.querySelector(".pm-project-card__release");
    if (releaseHost) {
      releaseHost.innerHTML = buildReleaseHtml(p, archived);
      var releaseHref = releaseLink(p, archived);
      if (releaseHref) {
        releaseHost.setAttribute("href", releaseHref);
        releaseHost.classList.remove("is-disabled");
      } else {
        releaseHost.removeAttribute("href");
        releaseHost.classList.add("is-disabled");
      }
    }

    var overview = node.querySelector(".pm-project-card__overview");
    if (overview) overview.href = "/admin/projects/" + encodeURIComponent(p.id) + "/overview";
  }

  function setMetric(node, key, value, tone, sub) {
    var metric = node.querySelector('[data-metric="' + key + '"]');
    if (!metric) return;
    var strong = metric.querySelector("strong");
    if (strong) {
      strong.textContent = value;
      strong.className = tone || "";
    }
    var em = metric.querySelector("em");
    if (em) em.textContent = sub || "";
  }

  function buildReleaseHtml(p, archived) {
    if (archived) {
      return "<span>最新发布</span><span class='p01-hint'>—</span>";
    }
    var rel = p.latest_release || null;
    if (!rel || !rel.version_name) {
      return "<span>版本管理</span><span class='p01-hint'>进入发版</span>";
    }
    var relInfo = DL.releaseStatus
      ? DL.releaseStatus(rel.status, rel.status_label)
      : { label: rel.status_label || "--", tone: "muted" };
    var when = DL.formatReleaseDateTime
      ? DL.formatReleaseDateTime(rel.updated_at)
      : String(rel.updated_at || "").slice(0, 16);
    return (
      "<span>版本管理</span><b>" +
      escapeHtml(rel.version_name) +
      "</b><time>" +
      escapeHtml(when) +
      "</time><span class='pm-project-card__release-tag " +
      releaseTagClass(relInfo.tone) +
      "'>" +
      escapeHtml(relInfo.label) +
      "</span>"
    );
  }

  function renderCard(p) {
    var tpl = el("pmProjectCardTemplate");
    if (!tpl || !tpl.content) return "";
    var node = tpl.content.querySelector(".pm-project-card").cloneNode(true);
    fillProjectCard(node, p);
    var wrap = document.createElement("div");
    wrap.appendChild(node);
    return wrap.innerHTML;
  }

  function openModal(id) {
    var node = el(id);
    if (node) node.classList.remove("is-hidden");
  }

  function closeModal(id) {
    var node = el(id);
    if (node) node.classList.add("is-hidden");
  }

  function closeTopModal() {
    var open = document.querySelector(".p01-modal-root.delivery-dialog:not(.is-hidden)");
    if (open && open.id) closeModal(open.id);
  }

  function resetCreateForm() {
    ["newProjectId", "newProjectName", "newProjectIntro", "newProjectIcon", "newProjectGameId", "newProjectGameKey", "newParticipantUser"].forEach(function (id) {
      var node = el(id);
      if (node) node.value = "";
    });
    var phaseEl = el("newProjectPhase");
    if (phaseEl) phaseEl.selectedIndex = 0;
    var iconFile = el("newProjectIconFile");
    if (iconFile) iconFile.value = "";
    setIconPreview("newProjectIconPreview", "");
    newParticipants = [];
    renderNewParticipants();
    setAddFeedback("", false);
  }

  function openCreateModal() {
    resetCreateForm();
    openModal("createProjectModal");
    if (!String((el("newProjectGameId") || {}).value || "").trim()) generateProjectCredentials();
  }

  function openCreateFromTemplate() {
    openCreateModal();
    var templates = (state.projects || []).filter(function (p) { return p.is_template; });
    if (!templates.length) return;
    var pick = templates[0];
    if (el("newProjectIntro")) {
      el("newProjectIntro").value = "基于模板项目「" + (pick.name || pick.id) + "」创建";
    }
  }

  function bindModalControls() {
    document.querySelectorAll("[data-close-modal]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        closeModal(btn.getAttribute("data-close-modal"));
      });
    });
    document.querySelectorAll(".p01-modal-root.delivery-dialog").forEach(function (modal) {
      modal.addEventListener("click", function (e) {
        if (e.target === modal) closeModal(modal.id);
      });
    });
    document.querySelectorAll("[data-path-picker]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        openPathPicker(btn.getAttribute("data-path-picker"), btn.getAttribute("data-path-mode"), btn);
      });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeTopModal();
    });
  }

  function setAddFeedback(msg, isError) {
    var node = el("addProjectFeedback");
    if (!node) return;
    node.textContent = msg || "";
    node.className = "p01-feedback" + (msg ? (isError ? " is-error" : " is-ok") : "");
  }

  function parseUserList(str) {
    return String(str || "")
      .split(/[,，\s]+/)
      .map(function (s) {
        return s.trim();
      })
      .filter(Boolean);
  }

  function openPathPicker(inputId, mode, triggerBtn) {
    var field = el(inputId);
    var start = field && field.value ? String(field.value).trim() : "";
    var btn = triggerBtn || null;
    var prevLabel = btn ? btn.textContent : "";
    if (btn) {
      btn.disabled = true;
      btn.textContent = "正在打开…";
    }
    fetch("/admin/fs/native-pick", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ mode: mode === "file" ? "file" : "dir", initial_path: start }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (d.ok && d.path && field) field.value = d.path;
        else if (!d.cancelled) alert(d.error || "未能选择路径");
      })
      .catch(function () {
        alert("调用系统选择框失败");
      })
      .finally(function () {
        if (btn) {
          btn.disabled = false;
          btn.textContent = prevLabel || "浏览";
        }
      });
  }

  function projectBuildPayload(prefix) {
    var branchesText = (el(prefix + "GitBranches") || {}).value || "";
    var gitBranches = branchesText
      ? branchesText
          .split("\n")
          .map(function (s) {
            return s.trim();
          })
          .filter(Boolean)
      : [];
    var o = {
      app_name: String((el(prefix + "AppName") || {}).value || "").trim(),
      git_url: String((el(prefix + "GitUrl") || {}).value || "").trim(),
      git_ssh_key_path: String((el(prefix + "GitSshKey") || {}).value || "").trim(),
      git_workspace: String((el(prefix + "GitWorkspace") || {}).value || "").trim(),
      default_git_branch: String((el(prefix + "DefaultGitBranch") || {}).value || "").trim(),
      unity_project_path: String((el(prefix + "UnityProjectPath") || {}).value || "").trim(),
      output_base_dir: String((el(prefix + "OutputBaseDir") || {}).value || "").trim(),
    };
    if (gitBranches.length) o.git_branches = gitBranches;
    return o;
  }

  function validateProjectGit(prefix, resultId) {
    var bp = projectBuildPayload(prefix);
    var node = el(resultId);
    if (node) {
      node.textContent = "验证中…";
      node.className = "p01-hint";
    }
    fetch("/api/jenkins-manage/validate-git", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        git_url: bp.git_url,
        git_workspace: bp.git_workspace,
        git_ssh_key_path: bp.git_ssh_key_path,
      }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (!node) return;
        if (d.ok) {
          node.textContent = "Git 配置有效";
          node.className = "p01-hint is-ok";
        } else {
          node.textContent = (d.errors && d.errors.length ? d.errors.join("；") : "配置有误");
          node.className = "p01-hint is-error";
        }
      })
      .catch(function () {
        if (node) {
          node.textContent = "验证请求失败";
          node.className = "p01-hint is-error";
        }
      });
  }

  function fillProjectBuildFields(prefix, p) {
    var bc = p.build_config || p || {};
    function setVal(id, v) {
      var node = el(id);
      if (node) node.value = v || "";
    }
    setVal(prefix + "AppName", bc.app_name || p.app_name);
    setVal(prefix + "OutputBaseDir", bc.output_base_dir || p.output_base_dir);
    setVal(prefix + "GitUrl", bc.git_url || p.git_url);
    setVal(prefix + "GitWorkspace", bc.git_workspace || p.git_workspace);
    setVal(prefix + "GitSshKey", bc.git_ssh_key_path || p.git_ssh_key_path);
    setVal(prefix + "DefaultGitBranch", bc.default_git_branch || p.default_git_branch);
    setVal(prefix + "UnityProjectPath", bc.unity_project_path || p.unity_project_path);
    var branches = bc.git_branches || p.git_branches || [];
    setVal(prefix + "GitBranches", Array.isArray(branches) ? branches.join("\n") : String(branches || ""));
  }

  function participantItemHtml(ctx, p) {
    return (
      "<li class='p01-participant-item'><span class='p01-participant-item__who'>" +
      escapeHtml(p.user) +
      " <em>" +
      escapeHtml(p.role) +
      "</em></span><span class='p01-participant-item__actions'><button type='button' data-edit-participant='" +
      ctx +
      "' data-user='" +
      escapeHtml(p.user) +
      "'>编辑</button><button type='button' data-remove-participant='" +
      ctx +
      "' data-user='" +
      escapeHtml(p.user) +
      "'>删除</button></span></li>"
    );
  }

  function renderNewParticipants() {
    var ul = el("newParticipantsList");
    if (!ul) return;
    ul.innerHTML =
      newParticipants.map(function (p) {
        return participantItemHtml("new", p);
      }).join("") || "<li class='p01-participant-empty'>暂无参与人员，可在上方添加</li>";
  }

  function renderEditParticipants() {
    var ul = el("editParticipantsList");
    if (!ul) return;
    ul.innerHTML =
      editParticipants.map(function (p) {
        return participantItemHtml("edit", p);
      }).join("") || "<li class='p01-participant-empty'>暂无参与人员，可在上方添加</li>";
  }

  function setIconPreview(previewId, url) {
    var prev = el(previewId);
    if (!prev) return;
    if (url) prev.innerHTML = "<img src='" + escapeHtml(url) + "' alt=''>";
    else prev.innerHTML = "<span class='p01-icon-upload__placeholder'>图标</span>";
  }

  function addNewParticipant() {
    var u = String((el("newParticipantUser") || {}).value || "").trim();
    if (!u) {
      alert("请输入用户名");
      return;
    }
    fetch("/admin/projects/validate-username?username=" + encodeURIComponent(u))
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (!d.exists) {
          alert("用户不存在或已禁用");
          return;
        }
        if (newParticipants.some(function (p) {
          return p.user === u;
        })) {
          alert("已添加过");
          return;
        }
        _participantCtx = "new";
        _pendingParticipantUser = u;
        el("roleModalUsername").textContent = u;
        el("roleModalRole").value = "其他";
        openModal("participantRoleModal");
      });
  }

  function addEditParticipant() {
    var u = String((el("editParticipantUser") || {}).value || "").trim();
    if (!u) {
      alert("请输入用户名");
      return;
    }
    fetch("/admin/projects/validate-username?username=" + encodeURIComponent(u))
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (!d.exists) {
          alert("用户不存在或已禁用");
          return;
        }
        if (editParticipants.some(function (p) {
          return p.user === u;
        })) {
          alert("已添加过");
          return;
        }
        _participantCtx = "edit";
        _pendingParticipantUser = u;
        el("roleModalUsername").textContent = u;
        el("roleModalRole").value = "其他";
        openModal("participantRoleModal");
      });
  }

  function confirmParticipantRole() {
    var r = String((el("roleModalRole") || {}).value || "其他");
    var arr = _participantCtx === "new" ? newParticipants : editParticipants;
    var exists = arr.find(function (x) {
      return x.user === _pendingParticipantUser;
    });
    if (exists) exists.role = r;
    else {
      arr.push({ user: _pendingParticipantUser, role: r });
      if (_participantCtx === "new") el("newParticipantUser").value = "";
      else el("editParticipantUser").value = "";
    }
    if (_participantCtx === "new") renderNewParticipants();
    else renderEditParticipants();
    closeModal("participantRoleModal");
  }

  function editParticipantRole(ctx, user) {
    var arr = ctx === "new" ? newParticipants : editParticipants;
    var p = arr.find(function (x) {
      return x.user === user;
    });
    if (!p) return;
    _participantCtx = ctx;
    _pendingParticipantUser = user;
    el("roleModalUsername").textContent = user;
    el("roleModalRole").value = p.role;
    openModal("participantRoleModal");
  }

  function removeParticipant(ctx, user) {
    if (ctx === "new") {
      newParticipants = newParticipants.filter(function (p) {
        return p.user !== user;
      });
      renderNewParticipants();
    } else {
      editParticipants = editParticipants.filter(function (p) {
        return p.user !== user;
      });
      renderEditParticipants();
    }
  }

  function uploadProjectIcon(fileInput, hiddenId, previewId) {
    if (!fileInput || !fileInput.files || !fileInput.files[0]) return;
    var fd = new FormData();
    fd.append("icon", fileInput.files[0]);
    fetch("/admin/projects/upload-icon", { method: "POST", body: fd, credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (d.url) {
          var h = el(hiddenId);
          if (h) h.value = d.url;
          setIconPreview(previewId, d.url);
        } else alert(d.error || "上传失败");
      });
  }

  function generateProjectCredentials() {
    var pid = String((el("newProjectId") || {}).value || "").trim() || "project";
    fetch("/admin/projects/generate-credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: pid }),
      credentials: "same-origin",
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (d.error) {
          alert(d.error);
          return;
        }
        el("newProjectGameId").value = d.game_id || "";
        el("newProjectGameKey").value = d.game_key || "";
      })
      .catch(function () {
        alert("生成凭据失败");
      });
  }

  function addProject() {
    var btn = el("addProjectBtn");
    try {
      if (btn) {
        btn.disabled = true;
        btn.textContent = "提交中…";
      }
      setAddFeedback("提交中…", false);
      var phaseEl = el("newProjectPhase");
      var phase = phaseEl ? phaseEl.value : "kickoff";
      var editors = newParticipants.map(function (p) {
        return p.user;
      });
      var member_roles = {};
      newParticipants.forEach(function (p) {
        member_roles[p.user] = p.role || "其他";
      });
      var payload = {
        id: String((el("newProjectId") || {}).value || "").trim(),
        name: String((el("newProjectName") || {}).value || "").trim(),
        phase: phase,
        icon: String((el("newProjectIcon") || {}).value || "").trim(),
        intro: String((el("newProjectIntro") || {}).value || "").trim(),
        viewers: [],
        editors: editors,
        member_roles: member_roles,
        game_id: String((el("newProjectGameId") || {}).value || "").trim(),
        game_key: String((el("newProjectGameKey") || {}).value || "").trim(),
      };
      if (!payload.id || !payload.name) {
        setAddFeedback("请填写项目ID和名称", true);
        if (btn) {
          btn.disabled = false;
          btn.textContent = "添加项目";
        }
        return;
      }
      if (!payload.game_id || !payload.game_key) {
        setAddFeedback("请先点击“系统生成凭据”", true);
        if (btn) {
          btn.disabled = false;
          btn.textContent = "添加项目";
        }
        return;
      }
      fetch("/admin/projects/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        credentials: "same-origin",
      })
        .then(function (r) {
          var ct = r.headers.get("Content-Type") || "";
          return r.text().then(function (t) {
            var d;
            try {
              d = ct.indexOf("json") >= 0 && t ? JSON.parse(t) : {};
            } catch (e) {
              d = { error: t && t.length < 200 ? t : "请求异常" };
            }
            return { ok: r.ok, status: r.status, data: d };
          });
        })
        .then(function (res) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = "添加项目";
          }
          var d = res.data;
          if (!res.ok || d.error) {
            setAddFeedback(d.error || "添加失败（" + res.status + "）", true);
            return;
          }
          setAddFeedback("添加成功。构建集成可在编辑项目或版本代码页配置。", false);
          closeModal("createProjectModal");
          loadProjects();
        })
        .catch(function (err) {
          if (btn) {
            btn.disabled = false;
            btn.textContent = "添加项目";
          }
          setAddFeedback("网络错误: " + (err.message || ""), true);
        });
    } catch (e) {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "添加项目";
      }
      setAddFeedback("错误: " + (e.message || String(e)), true);
    }
  }

  function filteredProjects() {
    var q = state.search.trim().toLowerCase();
    return allProjectsCache.filter(function (p) {
      if (state.owner && String(p.owner || p.created_by || "") !== state.owner) return false;
      if (state.health === "archived" && p.status !== "archived") return false;
      if (state.health && state.health !== "archived" && String(p.health_state || "") !== state.health) return false;
      if (!q) return true;
      return (
        String(p.id || "")
          .toLowerCase()
          .indexOf(q) >= 0 ||
        String(p.name || "")
          .toLowerCase()
          .indexOf(q) >= 0 ||
        String(p.name_en || "")
          .toLowerCase()
          .indexOf(q) >= 0 ||
        String(p.owner || p.created_by || "")
          .toLowerCase()
          .indexOf(q) >= 0 ||
        String(p.intro || "")
          .toLowerCase()
          .indexOf(q) >= 0
      );
    });
  }

  function paginatedProjects(list) {
    var total = list.length;
    var pages = Math.max(1, Math.ceil(total / state.pageSize));
    if (state.page > pages) state.page = pages;
    var start = (state.page - 1) * state.pageSize;
    return { rows: list.slice(start, start + state.pageSize), total: total, pages: pages };
  }

  function renderOwnerOptions() {
    var select = el("p01FilterOwner");
    if (!select) return;
    var owners = [];
    allProjectsCache.forEach(function (p) {
      var o = String(p.owner || p.created_by || "").trim();
      if (o && owners.indexOf(o) < 0) owners.push(o);
    });
    owners.sort();
    var html = "<option value=''>负责人：全部</option>";
    owners.forEach(function (o) {
      html += "<option value='" + escapeHtml(o) + "'" + (state.owner === o ? " selected" : "") + ">" + escapeHtml(o) + "</option>";
    });
    select.innerHTML = html;
  }

  function renderFilterRail(list, totalAll) {
    var rail = el("p01RailFilter");
    var chips = el("p01FilterChips");
    var empty = el("p01RailEmpty");
    var hasFilter = state.search || state.owner || state.health || state.status === "archived";
    if (!rail) return;
    if (!hasFilter) {
      rail.classList.add("is-hidden");
      return;
    }
    rail.classList.remove("is-hidden");
    var chipHtml = "";
    if (state.status === "archived") chipHtml += "<span class='p01-chip'>状态: 已归档<button type='button' data-clear-filter='status'>×</button></span>";
    if (state.health) {
      var healthLabel = el("p01FilterHealth").selectedOptions[0] ? el("p01FilterHealth").selectedOptions[0].textContent.replace("健康状态：", "") : state.health;
      chipHtml += "<span class='p01-chip'>健康状态: " + escapeHtml(healthLabel) + "<button type='button' data-clear-filter='health'>×</button></span>";
    }
    if (state.owner) chipHtml += "<span class='p01-chip'>负责人: " + escapeHtml(state.owner) + "<button type='button' data-clear-filter='owner'>×</button></span>";
    if (state.search) chipHtml += "<span class='p01-chip'>搜索: " + escapeHtml(state.search) + "<button type='button' data-clear-filter='search'>×</button></span>";
    if (chips) chips.innerHTML = chipHtml;
    if (empty) empty.style.display = list.length === 0 ? "block" : "none";
    if (el("p01TotalCount")) el("p01TotalCount").textContent = String(totalAll);
  }

  function renderTableRow(p) {
    var archived = p.status === "archived";
    var statusInfo = DL.cardStatus
      ? DL.cardStatus(archived ? "archived" : p.card_status || "running", p.card_status_label)
      : { label: p.card_status_label || p.status };
    var actions =
      "<a href='/admin/projects/" +
      encodeURIComponent(p.id) +
      "/overview'>总览</a>";
    if (p.can_edit) {
      actions +=
        "<button type='button' data-edit-project='" +
        escapeHtml(p.id) +
        "'>编辑</button>";
      actions +=
        "<button type='button' class='danger' data-delete-project='" +
        escapeHtml(p.id) +
        "'>删除</button>";
      if (!archived) {
        actions +=
          "<button type='button' data-archive-project='" +
          escapeHtml(p.id) +
          "' data-archive='1'>归档</button>";
      } else {
        actions +=
          "<button type='button' data-archive-project='" +
          escapeHtml(p.id) +
          "' data-archive='0'>取消归档</button>";
      }
    }
    return (
      "<tr><td>" +
      (p.icon ? "<img src='" + escapeHtml(p.icon) + "' alt='' style='width:32px;height:32px;border-radius:8px'>" : "—") +
      "</td><td>" +
      escapeHtml(p.id) +
      "</td><td>" +
      escapeHtml(p.name) +
      "</td><td>" +
      escapeHtml(statusInfo.label || p.card_status_label || p.status) +
      "</td><td>" +
      escapeHtml(p.owner || p.created_by || "—") +
      "</td><td>" +
      (archived || p.env_health_pct == null ? "—" : p.env_health_pct + "%") +
      "</td><td>" +
      escapeHtml(p.prod_version || "—") +
      "</td><td>" +
      (archived ? "—" : p.pending_approval || 0) +
      "</td><td>" +
      (archived ? "—" : p.blocker_count || 0) +
      "</td><td>" +
      (p.task_count || 0) +
      "</td><td class='p01-table-actions'>" +
      actions +
      "</td></tr>"
    );
  }

  function renderPagination(meta) {
    var node = el("p01Pagination");
    if (!node) return;
    var html =
      "<div>共 " +
      meta.total +
      " 条</div><div class='p01-page-size'><span>条/页</span><select id='p01PageSizeSelect'>" +
      [12, 24, 48]
        .map(function (n) {
          return "<option value='" + n + "'" + (state.pageSize === n ? " selected" : "") + ">" + n + "</option>";
        })
        .join("") +
      "</select></div><div class='p01-pagination-controls'>" +
      "<button type='button' class='p01-page-btn' data-page='prev'" +
      (state.page <= 1 ? " disabled" : "") +
      ">上一页</button>";
    for (var i = 1; i <= meta.pages; i++) {
      if (meta.pages > 7 && i > 2 && i < meta.pages - 1 && Math.abs(i - state.page) > 1) continue;
      html +=
        "<button type='button' class='p01-page-btn" +
        (i === state.page ? " active" : "") +
        "' data-page='" +
        i +
        "'>" +
        i +
        "</button>";
    }
    html +=
      "<button type='button' class='p01-page-btn' data-page='next'" +
      (state.page >= meta.pages ? " disabled" : "") +
      ">下一页</button></div><div class='p01-page-jump'><span>跳至</span><input type='number' id='p01PageJump' min='1' max='" +
      meta.pages +
      "' value='" +
      state.page +
      "'><span>页</span></div>";
    node.innerHTML = html;
    var sizeSelect = el("p01PageSizeSelect");
    if (sizeSelect) {
      sizeSelect.onchange = function () {
        state.pageSize = Number(sizeSelect.value) || 12;
        state.page = 1;
        renderProjects();
      };
    }
    var jump = el("p01PageJump");
    if (jump) {
      jump.onchange = function () {
        var v = Number(jump.value) || 1;
        state.page = Math.min(Math.max(1, v), meta.pages);
        renderProjects();
      };
    }
  }

  function renderProjects() {
    var filtered = filteredProjects();
    var meta = paginatedProjects(filtered);
    if (el("p01TotalCount")) el("p01TotalCount").textContent = String(allProjectsCache.length);
    renderFilterRail(filtered, allProjectsCache.length);
    var grid = el("p01CardGrid");
    var tablePanel = el("p01TablePanel");
    var tableBody = el("p01TableBody");
    if (state.view === "table") {
      if (grid) grid.innerHTML = "";
      if (tablePanel) tablePanel.classList.remove("is-hidden");
      if (tableBody) {
        tableBody.innerHTML =
          meta.rows.length
            ? meta.rows.map(renderTableRow).join("")
            : "<tr><td colspan='11' class='p01-center'>暂无项目</td></tr>";
      }
    } else {
      if (tablePanel) tablePanel.classList.add("is-hidden");
      if (grid) {
        grid.innerHTML = meta.rows.length
          ? meta.rows.map(renderCard).join("")
          : "<div class='p01-empty-grid'>暂无项目</div>";
      }
    }
    renderPagination(meta);
  }

  function loadProjects() {
    fetch("/admin/projects/list?status=" + encodeURIComponent(state.status || "active"), { credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok) throw new Error(String(r.status));
        return r.text();
      })
      .then(function (text) {
        var d = JSON.parse(text || "{}");
        allProjectsCache = d.projects || [];
        renderOwnerOptions();
        renderProjects();
      })
      .catch(function (e) {
        allProjectsCache = [];
        if (el("p01CardGrid")) el("p01CardGrid").innerHTML = "<div class='p01-empty-grid'>加载失败（" + escapeHtml(e.message) + "）</div>";
      });
  }

  function editProject(id) {
    fetch("/admin/projects/get/" + encodeURIComponent(id))
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (d.error) {
          alert(d.error);
          return;
        }
        var p = d.project;
        el("editProjectIdLabel").textContent = id;
        el("editProjectName").value = p.name || "";
        el("editProjectNameEn").value = p.name_en || "";
        var phaseSel = el("editProjectPhase");
        if (phaseSel) phaseSel.value = p.phase || "kickoff";
        el("editProjectIcon").value = p.icon || "";
        editParticipants = (p.editors || []).map(function (u) {
          return { user: u, role: (p.member_roles || {})[u] || "其他" };
        });
        renderEditParticipants();
        el("editProjectViewers").value = (p.viewers || []).join(", ");
        var projChans = p.channels || [];
        var chWrap = el("editProjectChannels");
        if (chWrap) {
          chWrap.innerHTML = ALL_CHANNELS
            .map(function (c) {
              return (
                "<label class='p01-channel-chip'><input type='checkbox' class='edit-channel-cb' value='" +
                escapeHtml(c.id) +
                "'" +
                (projChans.indexOf(c.id) >= 0 ? " checked" : "") +
                "><span>" +
                escapeHtml(c.name) +
                "</span></label>"
              );
            })
            .join("");
        }
        el("editProjectIntro").value = p.intro || "";
        el("editProjectDetail").value = p.detail || "";
        el("editProjectNetwork").value = p.network_connection || "";
        fillProjectBuildFields("editProject", p);
        if (el("editProjectPlayerPublicUrl")) el("editProjectPlayerPublicUrl").value = p.player_public_url || "";
        if (el("editProjectForumPublicUrl")) el("editProjectForumPublicUrl").value = p.forum_public_url || "";
        if (el("editProjectAdminPublicUrl")) el("editProjectAdminPublicUrl").value = p.admin_public_url || "";
        setIconPreview("editProjectIconPreview", p.icon || "");
        el("editProjectIconFile").value = "";
        openModal("editProjectModal");
      });
  }

  function saveEditProject() {
    var id = el("editProjectIdLabel").textContent;
    var viewers = parseUserList(el("editProjectViewers").value);
    var editors = editParticipants.map(function (p) {
      return p.user;
    });
    var member_roles = {};
    editParticipants.forEach(function (p) {
      member_roles[p.user] = p.role || "其他";
    });
    var phaseEl = el("editProjectPhase");
    var phase = phaseEl ? phaseEl.value : "kickoff";
    var channels = [];
    document.querySelectorAll(".edit-channel-cb:checked").forEach(function (cb) {
      channels.push(cb.value);
    });
    var payload = {
      id: id,
      name: el("editProjectName").value.trim(),
      name_en: el("editProjectNameEn").value.trim(),
      phase: phase,
      icon: el("editProjectIcon").value.trim(),
      intro: el("editProjectIntro").value.trim(),
      detail: el("editProjectDetail").value.trim(),
      network_connection: el("editProjectNetwork").value.trim(),
      player_public_url: String((el("editProjectPlayerPublicUrl") || {}).value || "").trim(),
      forum_public_url: String((el("editProjectForumPublicUrl") || {}).value || "").trim(),
      admin_public_url: String((el("editProjectAdminPublicUrl") || {}).value || "").trim(),
      viewers: viewers,
      editors: editors,
      member_roles: member_roles,
      channels: channels,
    };
    Object.assign(payload, projectBuildPayload("editProject"));
    fetch("/admin/projects/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        alert(d.error || "已保存");
        if (!d.error) {
          closeModal("editProjectModal");
          loadProjects();
        }
      });
  }

  function deleteProject(id) {
    if (!confirm("确定删除项目 " + id + "？")) return;
    fetch("/admin/projects/delete/" + encodeURIComponent(id), { method: "DELETE", credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        alert(d.error || "已删除");
        if (!d.error) loadProjects();
      });
  }

  function archiveProject(id, archive) {
    fetch("/admin/projects/" + encodeURIComponent(id) + "/archive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ archive: archive }),
      credentials: "same-origin",
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        alert(d.error || (archive ? "已归档" : "已取消归档"));
        if (!d.error) loadProjects();
      });
  }

  function openCardMenu(id, anchor) {
    var menu = el("p01CardMenu");
    if (!menu) return;
    var p = allProjectsCache.find(function (x) {
      return x.id === id;
    });
    if (!p) return;
    var html = "<button type='button' data-goto-overview='" + escapeHtml(id) + "'>进入项目总览</button>";
    if (p.can_edit) {
      html += "<button type='button' data-edit-project='" + escapeHtml(id) + "'>编辑项目</button>";
      html += "<button type='button' data-delete-project='" + escapeHtml(id) + "' class='danger'>删除项目</button>";
      if (p.status !== "archived") {
        html += "<button type='button' data-archive-project='" + escapeHtml(id) + "' data-archive='1'>归档项目</button>";
      } else {
        html += "<button type='button' data-archive-project='" + escapeHtml(id) + "' data-archive='0'>取消归档</button>";
      }
    }
    menu.innerHTML = html;
    menu.classList.remove("is-hidden");
    var rect = anchor.getBoundingClientRect();
    menu.style.top = String(rect.bottom + 4) + "px";
    menu.style.left = String(rect.left - 100) + "px";
  }

  function resetChannelForm() {
    el("channelFormEditingId").value = "";
    el("channelFormId").disabled = false;
    el("channelFormId").value = "";
    el("channelFormName").value = "";
    el("channelFormOrder").value = "0";
    el("channelFormDesc").value = "";
    if (el("channelFormApkSubdir")) el("channelFormApkSubdir").value = "";
    if (el("channelFormBuildParam")) el("channelFormBuildParam").value = "";
  }

  function renderChannelTable() {
    var tbody = el("channelTableBody");
    var empty = el("channelEmptyTip");
    if (!tbody) return;
    if (!_channelsCache || !_channelsCache.length) {
      tbody.innerHTML = "";
      if (empty) empty.classList.remove("is-hidden");
      return;
    }
    if (empty) empty.classList.add("is-hidden");
    tbody.innerHTML = _channelsCache
      .map(function (ch) {
        var chId = escapeHtml(ch.id || "");
        return (
          "<tr><td>" +
          chId +
          "</td><td>" +
          escapeHtml(ch.name || "-") +
          "</td><td>" +
          escapeHtml((ch.apk_subdir || "").slice(0, 12) || "-") +
          "</td><td>" +
          escapeHtml((ch.build_param || "").slice(0, 20) || "-") +
          "</td><td><button type='button' class='channel-edit-btn' data-channel-id='" +
          chId +
          "'>编辑</button> <button type='button' class='channel-delete-btn' data-channel-id='" +
          chId +
          "'>删除</button></td></tr>"
        );
      })
      .join("");
  }

  function loadChannels() {
    fetch("/admin/channels", { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        _channelsCache = d.channels || [];
        renderChannelTable();
      })
      .catch(function () {
        _channelsCache = [];
        renderChannelTable();
      });
  }

  function submitChannelForm() {
    var editingId = el("channelFormEditingId").value || "";
    var id = el("channelFormId").value.trim();
    var name = el("channelFormName").value.trim();
    var order = el("channelFormOrder").value;
    var desc = el("channelFormDesc").value.trim();
    var apkSubdir = String((el("channelFormApkSubdir") || {}).value || "").trim();
    var buildParam = String((el("channelFormBuildParam") || {}).value || "").trim();
    if (!id || !name) {
      alert("请填写渠道 ID 和名称");
      return;
    }
    var payload = { id: id, name: name, order: order, description: desc, apk_subdir: apkSubdir, build_param: buildParam };
    var url = editingId ? "/admin/channels/update" : "/admin/channels/create";
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      credentials: "same-origin",
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (d.error) {
          alert(d.error);
          return;
        }
        resetChannelForm();
        loadChannels();
      });
  }

  function deleteChannel(id) {
    if (!id) return;
    if (!confirm("确定删除渠道 " + id + "？")) return;
    fetch("/admin/channels/delete/" + encodeURIComponent(id), { method: "DELETE", credentials: "same-origin" })
      .then(function (r) {
        return r.text();
      })
      .then(function (text) {
        var d = JSON.parse(text || "{}");
        if (d.error) alert(d.error);
        else loadChannels();
      })
      .catch(function () {
        alert("删除失败");
      });
  }

  function resetFilters() {
    state.search = "";
    state.owner = "";
    state.health = "";
    state.status = "active";
    state.page = 1;
    if (el("p01Search")) el("p01Search").value = "";
    if (el("p01FilterStatus")) el("p01FilterStatus").value = "active";
    if (el("p01FilterOwner")) el("p01FilterOwner").value = "";
    if (el("p01FilterHealth")) el("p01FilterHealth").value = "";
    loadProjects();
  }

  function bindEvents() {
    if (el("p01CreateBtn")) el("p01CreateBtn").onclick = openCreateModal;
    if (el("p01QuickCreate")) el("p01QuickCreate").onclick = openCreateFromTemplate;
    if (el("p01QuickImport")) el("p01QuickImport").onclick = function () {
      var input = document.createElement("input");
      input.type = "file";
      input.accept = ".csv,text/csv";
      input.onchange = function () {
        var file = input.files && input.files[0];
        if (!file) return;
        var reader = new FileReader();
        reader.onload = function () {
          fetch("/admin/projects/import-csv", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ csv: String(reader.result || "") }),
          })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
            .then(function (res) {
              var d = res.data || {};
              if (!res.ok || d.error) {
                alert(d.error || (d.errors && d.errors.join("\n")) || "导入失败");
                return;
              }
              alert("成功导入 " + (d.created_count || (d.created && d.created.length) || 0) + " 个项目");
              loadProjects();
            })
            .catch(function () { alert("导入请求失败"); });
        };
        reader.readAsText(file, "utf-8");
      };
      input.click();
    };
    if (el("p01QuickArchive")) el("p01QuickArchive").onclick = function () {
      state.status = "archived";
      state.health = "";
      if (el("p01FilterStatus")) el("p01FilterStatus").value = "archived";
      state.page = 1;
      loadProjects();
    };
    if (el("p01Search")) {
      el("p01Search").oninput = function () {
        state.search = el("p01Search").value;
        state.page = 1;
        renderProjects();
      };
    }
    if (el("p01FilterStatus")) {
      el("p01FilterStatus").onchange = function () {
        state.status = el("p01FilterStatus").value;
        state.page = 1;
        loadProjects();
      };
    }
    if (el("p01FilterOwner")) {
      el("p01FilterOwner").onchange = function () {
        state.owner = el("p01FilterOwner").value;
        state.page = 1;
        renderProjects();
      };
    }
    if (el("p01FilterHealth")) {
      el("p01FilterHealth").onchange = function () {
        state.health = el("p01FilterHealth").value;
        state.page = 1;
        renderProjects();
      };
    }
    document.querySelectorAll(".p01-view-btn").forEach(function (btn) {
      btn.onclick = function () {
        document.querySelectorAll(".p01-view-btn").forEach(function (b) {
          b.classList.remove("active");
        });
        btn.classList.add("active");
        state.view = btn.getAttribute("data-view") || "card";
        renderProjects();
      };
    });
    if (el("p01ClearFilters")) el("p01ClearFilters").onclick = resetFilters;
    if (el("p01ResetFilters")) el("p01ResetFilters").onclick = resetFilters;
    if (el("btnGenerateCredentials")) el("btnGenerateCredentials").onclick = generateProjectCredentials;
    if (el("addProjectBtn")) el("addProjectBtn").onclick = addProject;
    if (el("btnAddNewParticipant")) el("btnAddNewParticipant").onclick = addNewParticipant;
    if (el("btnAddEditParticipant")) el("btnAddEditParticipant").onclick = addEditParticipant;
    if (el("btnConfirmParticipantRole")) el("btnConfirmParticipantRole").onclick = confirmParticipantRole;
    if (el("btnSaveEditProject")) el("btnSaveEditProject").onclick = saveEditProject;
    if (el("btnResetChannelForm")) el("btnResetChannelForm").onclick = resetChannelForm;
    if (el("btnSubmitChannelForm")) el("btnSubmitChannelForm").onclick = submitChannelForm;
    if (el("editProjectValidateGitBtn")) el("editProjectValidateGitBtn").onclick = function () {
      validateProjectGit("editProject", "editProjectGitValidateResult");
    };
    var newIcon = el("newProjectIconFile");
    if (newIcon) newIcon.onchange = function () {
      uploadProjectIcon(this, "newProjectIcon", "newProjectIconPreview");
    };
    var editIcon = el("editProjectIconFile");
    if (editIcon) editIcon.onchange = function () {
      uploadProjectIcon(this, "editProjectIcon", "editProjectIconPreview");
    };

    bindModalControls();

    document.addEventListener("click", function (e) {
      var pageBtn = e.target.closest("[data-page]");
      if (pageBtn && pageBtn.closest("#p01Pagination")) {
        var action = pageBtn.getAttribute("data-page");
        if (action === "prev") state.page = Math.max(1, state.page - 1);
        else if (action === "next") state.page += 1;
        else state.page = Number(action) || 1;
        renderProjects();
        return;
      }
      var clearFilter = e.target.closest("[data-clear-filter]");
      if (clearFilter) {
        var key = clearFilter.getAttribute("data-clear-filter");
        if (key === "search") {
          state.search = "";
          if (el("p01Search")) el("p01Search").value = "";
        } else if (key === "owner") {
          state.owner = "";
          if (el("p01FilterOwner")) el("p01FilterOwner").value = "";
        } else if (key === "health") {
          state.health = "";
          if (el("p01FilterHealth")) el("p01FilterHealth").value = "";
        } else if (key === "status") {
    state.status = "";
    if (el("p01FilterStatus")) el("p01FilterStatus").value = "";
          loadProjects();
          return;
        }
        state.page = 1;
        renderProjects();
        return;
      }
      var cardMenuBtn = e.target.closest("[data-card-menu]");
      if (cardMenuBtn) {
        openCardMenu(cardMenuBtn.getAttribute("data-card-menu"), cardMenuBtn);
        return;
      }
      var cardStarBtn = e.target.closest(".pm-project-card__star");
      if (cardStarBtn) {
        var card = cardStarBtn.closest(".pm-project-card");
        var pid = card && card.getAttribute("data-project-id");
        if (pid) {
          toggleFavorite(pid);
          cardStarBtn.classList.toggle("is-favorite", isFavorite(pid));
        }
        return;
      }
      var editBtn = e.target.closest("[data-edit-project]");
      if (editBtn) {
        el("p01CardMenu").classList.add("is-hidden");
        editProject(editBtn.getAttribute("data-edit-project"));
        return;
      }
      var archiveBtn = e.target.closest("[data-archive-project]");
      if (archiveBtn) {
        el("p01CardMenu").classList.add("is-hidden");
        archiveProject(archiveBtn.getAttribute("data-archive-project"), archiveBtn.getAttribute("data-archive") === "1");
        return;
      }
      var deleteBtn = e.target.closest("[data-delete-project]");
      if (deleteBtn) {
        el("p01CardMenu").classList.add("is-hidden");
        deleteProject(deleteBtn.getAttribute("data-delete-project"));
        return;
      }
      var gotoOverview = e.target.closest("[data-goto-overview]");
      if (gotoOverview) {
        location.href = "/admin/projects/" + encodeURIComponent(gotoOverview.getAttribute("data-goto-overview")) + "/overview";
        return;
      }
      var editParticipant = e.target.closest("[data-edit-participant]");
      if (editParticipant) {
        editParticipantRole(editParticipant.getAttribute("data-edit-participant"), editParticipant.getAttribute("data-user"));
        return;
      }
      var removeParticipantBtn = e.target.closest("[data-remove-participant]");
      if (removeParticipantBtn) {
        removeParticipant(removeParticipantBtn.getAttribute("data-remove-participant"), removeParticipantBtn.getAttribute("data-user"));
        return;
      }
      var channelEdit = e.target.closest(".channel-edit-btn");
      if (channelEdit) {
        var cid = channelEdit.getAttribute("data-channel-id");
        var ch = _channelsCache.find(function (c) {
          return (c.id || "") === cid;
        });
        if (ch) {
          el("channelFormEditingId").value = ch.id || "";
          el("channelFormId").value = ch.id || "";
          el("channelFormId").disabled = true;
          el("channelFormName").value = ch.name || "";
          el("channelFormOrder").value = ch.order != null ? ch.order : 0;
          el("channelFormDesc").value = ch.description || "";
          if (el("channelFormApkSubdir")) el("channelFormApkSubdir").value = ch.apk_subdir || "";
          if (el("channelFormBuildParam")) el("channelFormBuildParam").value = ch.build_param || "";
        }
        return;
      }
      var channelDel = e.target.closest(".channel-delete-btn");
      if (channelDel) deleteChannel(channelDel.getAttribute("data-channel-id"));
      if (!e.target.closest("#p01CardMenu")) el("p01CardMenu").classList.add("is-hidden");
    });
  }

  document.addEventListener("pm-favorites-changed", function () {
    renderProjects();
  });

  bindEvents();
  var boot = function () {
    loadProjects();
  };
  if (fav && fav.load) {
    fav.load().then(boot).catch(boot);
  } else {
    boot();
  }
})();
