(function () {
  "use strict";

  var initEl = document.getElementById("obWizardInitData");
  var INIT = {};
  try {
    INIT = JSON.parse((initEl && initEl.textContent) || "{}");
  } catch (e) {
    INIT = {};
  }

  var STEPS = [
    { id: "basic", title: "基本信息" },
    { id: "git", title: "Git / Unity" },
    { id: "channels", title: "渠道 / 平台" },
    { id: "envs", title: "环境" },
    { id: "jenkins", title: "Jenkins" },
    { id: "version", title: "首版本" },
    { id: "confirm", title: "确认" },
  ];

  var ENV_OPTIONS = [
    { value: "development", label: "开发环境" },
    { value: "testing", label: "测试环境" },
    { value: "staging", label: "预发环境" },
    { value: "production", label: "生产环境" },
  ];

  var PLATFORM_OPTIONS = INIT.platforms || [
    { value: "android", label: "Android" },
    { value: "ios", label: "iOS" },
  ];

  var state = {
    step: 0,
    form: {
      name: "",
      id: "",
      slug: "",
      git_url: "",
      unity_project_path: "",
      output_base_dir: "",
      default_git_branch: "main",
      channels: [],
      platforms: ["android"],
      env_keys: ["development", "testing"],
      jenkins_instance_id: "",
      jenkins_job_id: "",
      seed_version_group: {
        version_name: "1.0.0",
        env_key: "development",
        channel_id: "",
        platform: "android",
        version_code: "1",
      },
    },
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

  function showError(msg) {
    var box = el("obWizardError");
    if (!box) return;
    if (!msg) {
      box.classList.add("hidden");
      box.textContent = "";
      return;
    }
    box.textContent = msg;
    box.classList.remove("hidden");
  }

  function renderSteps() {
    var host = el("obWizardSteps");
    if (!host) return;
    host.innerHTML = STEPS.map(function (step, idx) {
      var active = idx === state.step ? " font-semibold text-indigo-600" : "";
      return '<li class="px-2 py-1 rounded-lg bg-slate-50' + active + '">' + (idx + 1) + ". " + escapeHtml(step.title) + "</li>";
    }).join("");
  }

  function checkboxList(name, options, selected) {
    return options
      .map(function (opt) {
        var val = opt.value || opt.id;
        var checked = selected.indexOf(val) >= 0 ? " checked" : "";
        var label = opt.label || opt.name || val;
        return (
          '<label class="inline-flex items-center gap-2 mr-4 mb-2">' +
          '<input type="checkbox" data-field="' +
          escapeHtml(name) +
          '" value="' +
          escapeHtml(val) +
          '"' +
          checked +
          ">" +
          escapeHtml(label) +
          "</label>"
        );
      })
      .join("");
  }

  function field(label, id, value, placeholder) {
    return (
      '<div><label class="block text-xs font-medium text-slate-500 mb-1">' +
      escapeHtml(label) +
      '</label><input type="text" id="' +
      id +
      '" value="' +
      escapeHtml(value || "") +
      '" placeholder="' +
      escapeHtml(placeholder || "") +
      '" class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"></div>'
    );
  }

  function readFormFromDom() {
    var f = state.form;
    f.name = (el("obName") && el("obName").value) || f.name;
    f.id = (el("obId") && el("obId").value) || f.id;
    f.slug = (el("obSlug") && el("obSlug").value) || f.slug;
    f.git_url = (el("obGitUrl") && el("obGitUrl").value) || f.git_url;
    f.unity_project_path = (el("obUnityPath") && el("obUnityPath").value) || f.unity_project_path;
    f.output_base_dir = (el("obOutputBase") && el("obOutputBase").value) || f.output_base_dir;
    f.default_git_branch = (el("obGitBranch") && el("obGitBranch").value) || f.default_git_branch;
    f.jenkins_instance_id = (el("obJenkinsInstance") && el("obJenkinsInstance").value) || f.jenkins_instance_id;
    f.jenkins_job_id = (el("obJenkinsJob") && el("obJenkinsJob").value) || f.jenkins_job_id;
    f.seed_version_group.version_name = (el("obVersionName") && el("obVersionName").value) || f.seed_version_group.version_name;
    f.seed_version_group.version_code = (el("obVersionCode") && el("obVersionCode").value) || f.seed_version_group.version_code;
    f.seed_version_group.env_key = (el("obSeedEnv") && el("obSeedEnv").value) || f.seed_version_group.env_key;

    ["channels", "platforms", "env_keys"].forEach(function (name) {
      var checked = document.querySelectorAll('input[data-field="' + name + '"]:checked');
      f[name] = Array.prototype.map.call(checked, function (node) {
        return node.value;
      });
    });

    if (f.channels.length) {
      f.seed_version_group.channel_id = f.seed_version_group.channel_id || f.channels[0];
    }
    if (f.platforms.length) {
      f.seed_version_group.platform = f.seed_version_group.platform || f.platforms[0];
    }
  }

  function renderPanel() {
    var panel = el("obWizardPanel");
    if (!panel) return;
    var f = state.form;
    var step = STEPS[state.step].id;
    var html = "";
    if (step === "basic") {
      html =
        '<div class="grid md:grid-cols-2 gap-4">' +
        field("项目名称", "obName", f.name, "如 GomeKu") +
        field("项目 ID", "obId", f.id, "如 GomeKu") +
        field("Slug（可选）", "obSlug", f.slug, "如 gomeku") +
        "</div>";
    } else if (step === "git") {
      html =
        '<div class="grid md:grid-cols-2 gap-4">' +
        field("Git 仓库 URL", "obGitUrl", f.git_url, "git@...") +
        field("Unity 项目路径", "obUnityPath", f.unity_project_path, "E:/maclient") +
        field("输出目录（可选）", "obOutputBase", f.output_base_dir, "E:/build/output") +
        field("默认 Git 分支", "obGitBranch", f.default_git_branch, "main") +
        "</div>";
    } else if (step === "channels") {
      html =
        "<div class='mb-4'><p class='text-sm text-slate-600 mb-2'>选择渠道</p>" +
        checkboxList("channels", INIT.channels || [], f.channels) +
        "</div><div><p class='text-sm text-slate-600 mb-2'>选择平台</p>" +
        checkboxList("platforms", PLATFORM_OPTIONS, f.platforms) +
        "</div>";
    } else if (step === "envs") {
      html = "<div><p class='text-sm text-slate-600 mb-2'>启用的发布环境</p>" + checkboxList("env_keys", ENV_OPTIONS, f.env_keys) + "</div>";
    } else if (step === "jenkins") {
      html =
        '<div class="grid md:grid-cols-2 gap-4">' +
        field("Jenkins 实例 ID（可选）", "obJenkinsInstance", f.jenkins_instance_id, "8082") +
        field("Jenkins Job ID（可选）", "obJenkinsJob", f.jenkins_job_id, "Android") +
        "</div>";
    } else if (step === "version") {
      html =
        '<div class="grid md:grid-cols-2 gap-4">' +
        field("首版本号", "obVersionName", f.seed_version_group.version_name, "1.0.0") +
        field("Version Code", "obVersionCode", f.seed_version_group.version_code, "1") +
        field("种子环境", "obSeedEnv", f.seed_version_group.env_key, "development") +
        "</div>";
    } else {
      readFormFromDom();
      html =
        '<dl class="grid md:grid-cols-2 gap-3 text-sm">' +
        "<dt class='text-slate-500'>项目</dt><dd>" +
        escapeHtml(f.name) +
        " (" +
        escapeHtml(f.id || f.slug) +
        ")</dd>" +
        "<dt class='text-slate-500'>Git</dt><dd>" +
        escapeHtml(f.git_url) +
        "</dd>" +
        "<dt class='text-slate-500'>Unity</dt><dd>" +
        escapeHtml(f.unity_project_path) +
        "</dd>" +
        "<dt class='text-slate-500'>渠道</dt><dd>" +
        escapeHtml((f.channels || []).join(", ")) +
        "</dd>" +
        "<dt class='text-slate-500'>平台</dt><dd>" +
        escapeHtml((f.platforms || []).join(", ")) +
        "</dd>" +
        "<dt class='text-slate-500'>环境</dt><dd>" +
        escapeHtml((f.env_keys || []).join(", ")) +
        "</dd>" +
        "<dt class='text-slate-500'>首版本</dt><dd>" +
        escapeHtml(f.seed_version_group.version_name) +
        " / VC " +
        escapeHtml(f.seed_version_group.version_code) +
        "</dd></dl>";
    }
    panel.innerHTML = html;
  }

  function validateStep() {
    readFormFromDom();
    var step = STEPS[state.step].id;
    if (step === "basic" && !(state.form.name && (state.form.id || state.form.slug || state.form.name))) {
      return "请填写项目名称与 ID";
    }
    if (step === "channels" && !(state.form.channels || []).length) {
      return "请至少选择一个渠道";
    }
    if (step === "envs" && !(state.form.env_keys || []).length) {
      return "请至少选择一个环境";
    }
    return "";
  }

  function syncNav() {
    el("obWizardPrev").disabled = state.step <= 0;
    var last = state.step >= STEPS.length - 1;
    el("obWizardNext").classList.toggle("hidden", last);
    el("obWizardSubmit").classList.toggle("hidden", !last);
    renderSteps();
    renderPanel();
  }

  function buildPayload() {
    readFormFromDom();
    var f = state.form;
    return {
      name: f.name,
      id: f.id || f.slug || f.name,
      slug: f.slug,
      git_url: f.git_url,
      unity_project_path: f.unity_project_path,
      output_base_dir: f.output_base_dir,
      default_git_branch: f.default_git_branch,
      channels: f.channels,
      platforms: f.platforms,
      env_keys: f.env_keys,
      jenkins_instance_id: f.jenkins_instance_id,
      jenkins_job_id: f.jenkins_job_id,
      seed_version_group: f.seed_version_group,
    };
  }

  function submitWizard() {
    showError("");
    var err = validateStep();
    if (err) {
      showError(err);
      return;
    }
    var btn = el("obWizardSubmit");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "创建中…";
    }
    fetch("/api/admin/projects/onboard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(buildPayload()),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { status: res.status, data: data };
        });
      })
      .then(function (pack) {
        if (pack.status >= 400) {
          throw new Error((pack.data && (pack.data.error || pack.data.error_message || pack.data.error_text)) || "创建失败");
        }
        var body = pack.data.data || pack.data;
        var resultBox = el("obWizardResult");
        if (resultBox) {
          var links = (body.next_actions || [])
            .map(function (item) {
              return '<a class="text-indigo-700 underline mr-3" href="' + escapeHtml(item.url) + '">' + escapeHtml(item.label) + "</a>";
            })
            .join("");
          resultBox.innerHTML =
            "<p class='font-medium mb-2'>项目 " +
            escapeHtml(body.project_id) +
            " 已创建。</p><p class='mb-2'>scope: " +
            escapeHtml((body.scope_ids || []).join(", ")) +
            "</p><div>" +
            links +
            "</div>";
          resultBox.classList.remove("hidden");
        }
        el("obWizardPanel").classList.add("hidden");
        el("obWizardPrev").classList.add("hidden");
        el("obWizardNext").classList.add("hidden");
        el("obWizardSubmit").classList.add("hidden");
      })
      .catch(function (error) {
        showError(error.message || String(error));
      })
      .finally(function () {
        if (btn) {
          btn.disabled = false;
          btn.textContent = "创建项目";
        }
      });
  }

  function bindEvents() {
    el("obWizardPrev").addEventListener("click", function () {
      showError("");
      if (state.step > 0) {
        readFormFromDom();
        state.step -= 1;
        syncNav();
      }
    });
    el("obWizardNext").addEventListener("click", function () {
      var err = validateStep();
      if (err) {
        showError(err);
        return;
      }
      showError("");
      state.step += 1;
      syncNav();
    });
    el("obWizardSubmit").addEventListener("click", submitWizard);
  }

  bindEvents();
  syncNav();
})();
