(() => {
  const root = document.querySelector("[data-page='version-build-config']");
  if (!root) return;

  const projectId = root.dataset.projectId;
  const versionId = root.dataset.versionId;
  const canEdit = root.dataset.canEdit === "true";
  const entryFrom = (root.dataset.entryFrom || "version-group").trim().toLowerCase();
  const editScope = (root.dataset.editScope || "version_group").trim().toLowerCase();
  const groupVersionName = (root.dataset.versionName || "").trim();
  const groupPlatform = (root.dataset.platform || "").trim();
  const groupEnvKey = (root.dataset.envKey || "").trim();
  const defaultResourceServerUrl = (root.dataset.defaultResourceServerUrl || "").trim();
  const isGroupMode = editScope === "version_group";
  const form = document.getElementById("versionBuildConfigForm");
  const statusEl = document.getElementById("vcConfigStatus");
  const saveBtn = document.getElementById("btnSaveBuildConfig");
  let currentVersion = null;
  let currentGroupMeta = null;
  let previewTimer = null;

  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const toast = (message, type = "success") => {
    statusEl.textContent = message;
    statusEl.style.color = type === "error" ? "#d92d20" : "#38a45b";
  };

  const SECTION_ALIASES = { pipeline: "resource_build" };
  const SECTIONS = ["jenkins", "config_export", "resource_build", "hot_release", "artifact", "client_policy"];

  const STAGE_TO_RELEASE_ENV = {
    dev: "Development",
    development: "Development",
    test: "Testing",
    testing: "Testing",
    stage: "Staging",
    staging: "Staging",
    prod: "Production",
    production: "Production",
  };
  const ENV_KEY_TO_JENKINS = {
    development: "Development",
    testing: "Testing",
    staging: "Staging",
    production: "Production",
  };

  let activePolicyPreset = "";

  const normalizePlatform = (platform) => {
    const p = String(platform || "android").trim().toLowerCase();
    if (p === "ios" || p === "iphone" || p === "iphoneos") return "ios";
    return "android";
  };

  const safeAppSegment = (value, fallback = "GameKu") => {
    const text = String(value || "").trim();
    if (!text) return fallback;
    return text.replace(/[^\w.-]+/g, "_") || fallback;
  };

  const deriveVersionContext = (version) => {
    const envKey = String(version?.env_key || "").trim().toLowerCase();
    const stage = String(version?.stage || "dev").trim().toLowerCase();
    const releaseEnv = ENV_KEY_TO_JENKINS[envKey] || STAGE_TO_RELEASE_ENV[stage] || "Development";
    const channelKey = String(version?.channel || "common").trim() || "common";
    const channelDisplay = String(version?.channel_name || channelKey).trim() || channelKey;
    const platformSeg = normalizePlatform(version?.platform);
    const platformLabel = String(version?.platform_label || (platformSeg === "ios" ? "iOS" : "Android"));
    const versionName = String(version?.version_name || "").trim();
    const versionCode = String(version?.version_code || "").trim();
    const versionFolder = versionName ? `Version_${versionName}` : "";
    const codeSegment = versionCode ? `/${versionCode}` : "";
    const rel = `${releaseEnv}/${channelKey}/${platformSeg}/${versionFolder}${codeSegment}`.replace(/\/+/g, "/");
    return {
      releaseEnv,
      channelKey,
      channelDisplay,
      platformSeg,
      platformLabel,
      versionName,
      versionCode,
      rel,
      configPath: `${rel}/config`,
      resourcePath: rel,
    };
  };

  const apkExtension = (version, packageFormat) => {
    const plat = normalizePlatform(version?.platform);
    if (plat === "ios") return ".ipa";
    const fmt = String(packageFormat || "apk").trim().toLowerCase();
    if (fmt === "aab" || fmt === "iaa") return ".aab";
    return ".apk";
  };

  const apkFilename = (version, packageFormat) => {
    const vn = String(version?.version_name || "1.0.0").trim();
    const vc = String(version?.version_code || "").trim();
    const apkBuild = pipelinePart(version, "apk_build");
    const app =
      String(form.app_name?.value || "").trim() ||
      String(apkBuild.app_name || "").trim() ||
      String(version?.app_name || "").trim() ||
      projectId ||
      "GameKu";
    const ext = apkExtension(version, packageFormat);
    return `${safeAppSegment(app)}_${vn}_vc${vc}${ext}`;
  };

  const applyDerivedFields = (version) => {
    if (!version) return;
    const ctx = deriveVersionContext(version);
    const pkgFmt = form.package_format?.value || (normalizePlatform(version.platform) === "ios" ? "ipa" : "apk");
    if (form.config_client_version) form.config_client_version.value = ctx.versionName;
    if (form.config_environment) form.config_environment.value = ctx.releaseEnv;
    if (form.config_platform) form.config_platform.value = ctx.platformLabel;
    if (form.config_path) form.config_path.value = ctx.configPath;
    if (form.resource_path) form.resource_path.value = ctx.resourcePath;
    if (form.release_channel) form.release_channel.value = ctx.channelDisplay;
    if (form.apk_path && ctx.rel) form.apk_path.value = `${ctx.rel}/${apkFilename(version, pkgFmt)}`;
  };

  const setupPackageFormat = (version) => {
    const select = document.getElementById("packageFormatSelect");
    if (!select || !version) return;
    const plat = normalizePlatform(version.platform);
    const apkBuild = pipelinePart(version, "apk_build");
    const saved = String(apkBuild.package_format || "").trim().toLowerCase();
    select.innerHTML = "";
    if (plat === "ios") {
      select.insertAdjacentHTML("beforeend", '<option value="ipa">IPA（iOS App Store）</option>');
      select.value = "ipa";
      select.disabled = true;
      return;
    }
    select.insertAdjacentHTML(
      "beforeend",
      '<option value="apk">APK（侧载 / 测试分发）</option><option value="aab">AAB（Google Play）</option>',
    );
    select.value = saved === "aab" || saved === "iaa" ? "aab" : "apk";
    select.disabled = !canEdit;
  };

  const detectHotPreset = () => {
    if (!form.hot_release_enabled?.checked) return "hot-off";
    const { code, resource } = targetChips();
    if (code && !resource) return "code-only";
    if (!code && resource) return "resource-only";
    if (code && resource) return "code-resource";
    return "";
  };

  const syncHotPresetHighlight = (activePreset) => {
    const preset = activePreset || detectHotPreset();
    root.querySelectorAll("[data-preset]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.preset === preset);
    });
  };

  const setPolicyPresetActive = (preset) => {
    activePolicyPreset = preset || "";
    root.querySelectorAll("[data-policy-preset]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.policyPreset === activePolicyPreset);
    });
  };

  const loadUnityVersions = async (selected) => {
    const select = document.getElementById("unityVersionSelect");
    if (!select) return;
    try {
      const response = await fetch("/api/admin/unity-versions/detect", { credentials: "same-origin" });
      const data = await response.json();
      const versions = (data.versions || [])
        .map((row) => String(row.version || "").trim())
        .filter(Boolean);
      select.innerHTML = '<option value="">请选择 Unity 版本</option>';
      versions.forEach((ver) => {
        select.insertAdjacentHTML("beforeend", `<option value="${esc(ver)}">${esc(ver)}</option>`);
      });
      const picked = String(selected || "").trim();
      if (picked && !versions.includes(picked)) {
        select.insertAdjacentHTML(
          "beforeend",
          `<option value="${esc(picked)}">${esc(picked)}（已保存）</option>`,
        );
      }
      if (picked) select.value = picked;
    } catch (_error) {
      /* keep placeholder */
    }
  };

  const nativePathPick = async (fieldName, mode) => {
    const field = form.elements[fieldName];
    if (!field || !canEdit) return;
    try {
      const response = await fetch("/admin/fs/native-pick", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initial_path: field.value.trim(), mode: mode || "dir" }),
      });
      const data = await response.json();
      if (data.cancelled) return;
      if (!data.ok || !data.path) throw new Error(data.error || "选择失败");
      field.value = data.path;
      renderJenkinsPreview();
    } catch (error) {
      toast(error.message || "路径选择失败", "error");
    }
  };

  const sectionFromUrl = () => {
    const raw = new URLSearchParams(location.search).get("section") || "jenkins";
    const tab = SECTION_ALIASES[raw] || raw;
    return SECTIONS.includes(tab) ? tab : "jenkins";
  };

  const activateSection = (name) => {
    root.querySelectorAll("[data-section-tab]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.sectionTab === name);
    });
    root.querySelectorAll(".workflow-section[data-section]").forEach((section) => {
      const active = section.dataset.section === name;
      section.classList.toggle("active", active);
      section.hidden = !active;
    });
  };

  root.querySelectorAll("[data-section-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      activateSection(btn.dataset.sectionTab);
      renderJenkinsPreview();
    });
  });

  const pipelinePart = (version, key) => {
    const pipeline = version?.pipeline && typeof version.pipeline === "object" ? version.pipeline : {};
    const part = pipeline[key];
    return part && typeof part === "object" ? part : {};
  };

  const targetChips = () => {
    const code = root.querySelector("[data-target-chip='code']");
    const resource = root.querySelector("[data-target-chip='resource']");
    return {
      code: Boolean(code?.classList.contains("active")),
      resource: Boolean(resource?.classList.contains("active")),
    };
  };

  const setTargetChips = (targets) => {
    const parts = String(targets || "code,resource")
      .split(/[,;]+/)
      .map((x) => x.trim().toLowerCase())
      .filter(Boolean);
    const hasCode = parts.includes("code");
    const hasResource = parts.includes("resource");
    root.querySelectorAll("[data-target-chip]").forEach((chip) => {
      const kind = chip.dataset.targetChip;
      const on = kind === "code" ? hasCode : hasResource;
      chip.classList.toggle("active", on);
    });
  };

  const releaseTargetsString = () => {
    const { code, resource } = targetChips();
    const parts = [];
    if (code) parts.push("code");
    if (resource) parts.push("resource");
    return parts.join(",");
  };

  root.querySelectorAll("[data-target-chip]").forEach((chip) => {
    chip.addEventListener("click", () => {
      chip.classList.toggle("active");
      syncHotPresetHighlight();
      renderJenkinsPreview();
      scheduleRuntimePreview();
    });
  });

  const applyPreset = (preset) => {
    const hot = form.hot_release_enabled;
    const apk = form.apk_build_enabled;
    const configExport = form.config_export_enabled;
    const resourceBuild = form.resource_build_enabled;
    if (preset === "code-only") {
      if (hot) hot.checked = true;
      setTargetChips("code");
      if (form.code_enabled) form.code_enabled.checked = true;
      if (form.resource_hot_enabled) form.resource_hot_enabled.checked = false;
    } else if (preset === "resource-only") {
      if (hot) hot.checked = true;
      if (resourceBuild) resourceBuild.checked = true;
      setTargetChips("resource");
      if (form.code_enabled) form.code_enabled.checked = false;
      if (form.resource_hot_enabled) form.resource_hot_enabled.checked = true;
    } else if (preset === "code-resource") {
      if (hot) hot.checked = true;
      setTargetChips("code,resource");
      if (form.code_enabled) form.code_enabled.checked = true;
      if (form.resource_hot_enabled) form.resource_hot_enabled.checked = true;
    } else if (preset === "hot-off") {
      if (hot) hot.checked = false;
    }
    if (preset === "code-only" || preset === "resource-only") {
      if (apk) apk.checked = false;
    }
    syncHotPresetHighlight(preset);
    renderJenkinsPreview();
    scheduleRuntimePreview();
  };

  root.querySelectorAll("[data-preset]").forEach((btn) => {
    btn.addEventListener("click", () => applyPreset(btn.dataset.preset));
  });

  const applyPolicyPreset = (preset) => {
    const hot = form.hot_release_enabled;
    const apk = form.apk_build_enabled;
    const configExport = form.config_export_enabled;
    const resourceBuild = form.resource_build_enabled;
    const forceUpdate = form.force_update;
    const revoked = form.is_revoked;

    if (preset === "config-only") {
      if (configExport) configExport.checked = true;
      if (resourceBuild) resourceBuild.checked = false;
      if (hot) hot.checked = false;
      if (apk) apk.checked = false;
      if (forceUpdate) forceUpdate.checked = false;
      if (revoked) revoked.checked = false;
    } else if (preset === "code-only") {
      applyPreset("code-only");
      if (configExport) configExport.checked = false;
      if (resourceBuild) resourceBuild.checked = false;
    } else if (preset === "resource-only") {
      applyPreset("resource-only");
      if (configExport) configExport.checked = false;
    } else if (preset === "code-resource") {
      applyPreset("code-resource");
      if (configExport) configExport.checked = false;
    } else if (preset === "force-apk") {
      if (forceUpdate) forceUpdate.checked = true;
      if (apk) apk.checked = true;
      if (hot) hot.checked = false;
      if (configExport) configExport.checked = false;
      if (resourceBuild) resourceBuild.checked = false;
      if (revoked) revoked.checked = false;
    }
    setPolicyPresetActive(preset);
    renderJenkinsPreview();
    scheduleRuntimePreview();
  };

  root.querySelectorAll("[data-policy-preset]").forEach((btn) => {
    btn.addEventListener("click", () => applyPolicyPreset(btn.dataset.policyPreset));
  });

  const defaultCatalogName = (version) => {
    const vn = String(version?.version_name || "").trim();
    return vn ? `catalog_${vn}.bin` : "";
  };

  const fillForm = (version) => {
    const apkBuild = pipelinePart(version, "apk_build");
    const configExport = pipelinePart(version, "config_export");
    const resourceBuild = pipelinePart(version, "resource_build");
    const hotRelease = pipelinePart(version, "hot_release");
    const set = (name, value) => {
      const field = form.elements[name];
      if (field) field.value = value ?? "";
    };
    const setCheck = (name, value) => {
      const field = form.elements[name];
      if (field) field.checked = Boolean(value);
    };

    set("jenkins_job_id", version.jenkins_job_id || version.jenkins_job || "");
    set("git_branch", apkBuild.git_branch || version.pipeline?.git_branch || "");
    set("app_name", apkBuild.app_name || "");
    set("unity_project_path", apkBuild.unity_project_path || "");
    set("output_base_dir", apkBuild.output_base_dir || "");

    setCheck("config_export_enabled", configExport.enabled);
    set("config_remote_prefix", configExport.remote_prefix || "");
    setCheck("config_include_code", configExport.include_code);

    setCheck("resource_build_enabled", resourceBuild.enabled);
    set("resource_provider", resourceBuild.provider || "addressables-v2");
    set("resource_scenario", resourceBuild.scenario || "default");

    setCheck("hot_release_enabled", hotRelease.enabled);
    set("release_mode", hotRelease.release_mode || "build-upload");
    set("release_upload_mode", hotRelease.release_upload_mode || "incremental");
    set("release_hot_labels", hotRelease.release_hot_labels || "hotupdate,aotmeta");
    set("release_rollback_target", hotRelease.release_rollback_target || "");
    setTargetChips(hotRelease.release_targets || "code,resource");
    setCheck("code_enabled", hotRelease.code_enabled ?? true);
    set("code_compression", hotRelease.code_compression || "Zip");
    set("code_encryption", hotRelease.code_encryption || "Aes");
    set("code_signature", hotRelease.code_signature || "builtin-signature");
    set("code_units", hotRelease.code_units || "aotmeta, hotupdate, scriptpatch, symbols");
    setCheck("resource_hot_enabled", hotRelease.resource_enabled ?? true);
    set("resource_compression", hotRelease.resource_compression || "None");
    set("resource_encryption", hotRelease.resource_encryption || "None");
    set("resource_signature", hotRelease.resource_signature || "builtin-signature");
    set("resource_units", hotRelease.resource_units || "addressable, hotupdate, optional, platform, hd, streaming");
    set("release_compression_override", hotRelease.release_compression_override || "");
    set("release_encryption_override", hotRelease.release_encryption_override || "");
    set("release_signature_override", hotRelease.release_signature_override || "");

    setCheck("apk_build_enabled", apkBuild.enabled);

    set("resource_server_url", version.resource_server_url || defaultResourceServerUrl || "");
    set("catalog_file_name", version.catalog_file_name || defaultCatalogName(version));
    set("min_client_version", version.min_client_version || version.version_name || "");
    set("rollout_percentage", version.rollout_percentage ?? 100);
    setCheck("force_update", version.force_update);
    setCheck("is_revoked", version.is_revoked);

    const instanceSelect = document.getElementById("jenkinsInstanceSelect");
    if (instanceSelect && version.jenkins_instance_id) {
      const exists = Array.from(instanceSelect.options).some((opt) => opt.value === version.jenkins_instance_id);
      if (!exists) {
        instanceSelect.insertAdjacentHTML(
          "beforeend",
          `<option value="${esc(version.jenkins_instance_id)}">${esc(version.jenkins_instance_id)}</option>`,
        );
      }
      instanceSelect.value = version.jenkins_instance_id;
    }

    const overrideWrap = document.getElementById("channelJobOverrideWrap");
    const overrideInput = form.channel_jenkins_job_override;
    const channelKey = String(version.channel || version.channel_id || "").trim();
    if (isGroupMode && overrideWrap && overrideInput && channelKey) {
      overrideWrap.hidden = false;
      const overrides = currentGroupMeta?.jenkins_job_overrides || {};
      overrideInput.value = overrides[channelKey] || "";
    } else if (overrideWrap) {
      overrideWrap.hidden = true;
    }

    const historyLink = document.getElementById("buildHistoryLink");
    if (historyLink) {
      const params = new URLSearchParams();
      params.set("scoped", "1");
      if (version.id) params.set("version_id", version.id);
      if (version.env_key) params.set("env_key", version.env_key);
      if (version.channel_id || version.channel) params.set("channel_id", version.channel_id || version.channel);
      if (version.platform) params.set("platform", version.platform);
      if (version.version_name) params.set("version_name", version.version_name);
      if (version.version_code) params.set("version_code", version.version_code);
      const qs = params.toString();
      historyLink.href = `/admin/projects/${projectId}/build-history${qs ? `?${qs}` : ""}`;
    }

    setupPackageFormat(version);
    applyDerivedFields(version);
    syncHotPresetHighlight();
    loadUnityVersions(apkBuild.unity_version || "");
  };

  const buildPipelineFromForm = (version) => {
    const pipeline = version?.pipeline && typeof version.pipeline === "object" ? { ...version.pipeline } : {};
    const apkBuild = { ...(pipeline.apk_build || {}) };
    apkBuild.git_branch = form.git_branch.value.trim();
    apkBuild.unity_version = form.unity_version.value.trim();
    apkBuild.app_name = form.app_name.value.trim();
    apkBuild.unity_project_path = form.unity_project_path.value.trim();
    apkBuild.output_base_dir = form.output_base_dir.value.trim();
    apkBuild.enabled = form.apk_build_enabled.checked;
    apkBuild.package_format = form.package_format?.value || "apk";
    pipeline.apk_build = apkBuild;
    if (apkBuild.git_branch) pipeline.git_branch = apkBuild.git_branch;

    pipeline.config_export = {
      ...(pipeline.config_export || {}),
      enabled: form.config_export_enabled.checked,
      remote_prefix: form.config_remote_prefix.value.trim(),
      client_version: form.config_client_version.value.trim(),
      environment: form.config_environment.value.trim(),
      platform: form.config_platform.value.trim(),
      include_code: form.config_include_code.checked,
    };
    pipeline.resource_build = {
      ...(pipeline.resource_build || {}),
      enabled: form.resource_build_enabled.checked,
      provider: form.resource_provider.value,
      scenario: form.resource_scenario.value.trim(),
    };
    pipeline.hot_release = {
      ...(pipeline.hot_release || {}),
      enabled: form.hot_release_enabled.checked,
      release_mode: form.release_mode.value,
      release_upload_mode: form.release_upload_mode.value,
      release_channel: deriveVersionContext(version).channelKey,
      release_hot_labels: form.release_hot_labels.value.trim(),
      release_rollback_target: form.release_rollback_target.value.trim(),
      release_targets: releaseTargetsString(),
      code_enabled: form.code_enabled.checked,
      code_compression: form.code_compression.value,
      code_encryption: form.code_encryption.value,
      code_signature: form.code_signature.value,
      code_units: form.code_units.value.trim(),
      resource_enabled: form.resource_hot_enabled.checked,
      resource_compression: form.resource_compression.value,
      resource_encryption: form.resource_encryption.value,
      resource_signature: form.resource_signature.value,
      resource_units: form.resource_units.value.trim(),
      release_compression_override: form.release_compression_override.value,
      release_encryption_override: form.release_encryption_override.value,
      release_signature_override: form.release_signature_override.value,
    };
    return pipeline;
  };

  const buildPayload = (version) => {
    let rollout = form.rollout_percentage.value.trim();
    if (rollout === "") rollout = "100";
    return {
      id: versionId,
      edit_scope: isGroupMode ? "version_group" : "version_code",
      channel: version.channel_id || version.channel,
      stage: version.stage || "dev",
      platform: version.platform || "android",
      version_name: version.version_name,
      version_code: version.version_code,
      version_status: version.version_status || "active",
      version_mode: version.version_mode || "general",
      jenkins_job_id: form.jenkins_job_id.value.trim(),
      jenkins_instance_id: form.jenkins_instance_id.value.trim(),
      resource_path: form.resource_path.value.trim(),
      config_path: form.config_path.value.trim(),
      apk_path: form.apk_path.value.trim(),
      resource_server_url: form.resource_server_url.value.trim(),
      catalog_file_name: form.catalog_file_name.value.trim(),
      min_client_version: form.min_client_version.value.trim(),
      rollout_percentage: Number(rollout),
      force_update: form.force_update.checked,
      is_revoked: form.is_revoked.checked,
      pipeline: buildPipelineFromForm(version),
    };
  };

  const buildPlanFromForm = (version) => {
    const pipeline = buildPipelineFromForm(version);
    const ce = pipeline.config_export || {};
    const rb = pipeline.resource_build || {};
    const hr = pipeline.hot_release || {};
    const ab = pipeline.apk_build || {};
    const platform = (version.platform || "android").toString();
    const platformCap = platform.charAt(0).toUpperCase() + platform.slice(1).toLowerCase();
    return {
      configEnabled: ce.enabled,
      configRemotePrefix: ce.remote_prefix,
      configIncludeCode: ce.include_code,
      resourceEnabled: rb.enabled,
      resourceProvider: rb.provider,
      hotReleaseEnabled: hr.enabled,
      apkBuildEnabled: ab.enabled,
      releaseMode: hr.release_mode,
      releaseChannel: hr.release_channel,
      releaseTargets: hr.release_targets,
      releaseHotLabels: hr.release_hot_labels,
      releaseUploadMode: hr.release_upload_mode,
      releaseRollbackTarget: hr.release_rollback_target,
      codeEnabled: hr.code_enabled,
      codeCompression: hr.code_compression,
      codeEncryption: hr.code_encryption,
      codeSignature: hr.code_signature,
      codeUnits: hr.code_units,
      resourceCompression: hr.resource_compression,
      resourceEncryption: hr.resource_encryption,
      resourceSignature: hr.resource_signature,
      resourceUnits: hr.resource_units,
      appName: ab.app_name,
      unityVersion: ab.unity_version,
      gitBranch: ab.git_branch,
      outputBaseDir: ab.output_base_dir,
      unityProjectPath: ab.unity_project_path,
      packageFormat: ab.package_format || "apk",
      releaseVersion: version.version_name,
      versionCode: version.version_code,
      releasePlatform: ce.platform || platformCap,
      releaseEnvironment: ce.environment || "",
    };
  };

  const renderPreviewRows = (listEl, rows) => {
    if (!listEl) return;
    listEl.innerHTML = rows
      .map(([key, val]) => {
        const text = String(val ?? "-");
        return `<li><code>${esc(key)}</code><span title="${esc(text)}">${esc(text)}</span></li>`;
      })
      .join("");
  };

  const DOMAIN_LABELS = { config: "配置域", code: "代码域", resource: "资源域", apk: "安装包" };

  const renderDomainChips = (domain) => {
    const chips = document.getElementById("domainStatusChips");
    if (!chips) return;
    chips.querySelectorAll("[data-domain-chip]").forEach((chip) => {
      const key = chip.dataset.domainChip;
      const on = Boolean(domain && domain[key]);
      chip.classList.toggle("on", on);
      chip.textContent = `${DOMAIN_LABELS[key] || key} · ${on ? "开" : "关"}`;
    });
  };

  const renderBootstrapPreview = (preview) => {
    const list = document.getElementById("bootstrapPreviewList");
    const meta = document.getElementById("runtimeScopeMeta");
    if (!list) return;
    if (!preview) {
      list.innerHTML = "<li><code>status</code><span>加载中…</span></li>";
      if (meta) meta.textContent = "";
      return;
    }
    if (meta) {
      const scope = preview.scope_id || "-";
      const bundle = preview.active_bundle_id || "无";
      meta.innerHTML = `scope_id: <code>${esc(scope)}</code> · active_bundle: <code>${esc(bundle)}</code>`;
    }
    renderPreviewRows(list, [
      ["force_update", String(preview.force_update)],
      ["rollout_percentage", String(preview.rollout_percentage)],
      ["min_client_version", preview.min_client_version],
      ["is_revoked", String(preview.is_revoked)],
      ["resource_server_url", preview.resource_server_url],
      ["catalog_file_name", preview.catalog_file_name],
      ["resource_relative_path", preview.resource_relative_path],
      ["config_relative_path", preview.config_relative_path],
      ["code_relative_path", preview.code_relative_path],
      ["catalog_url", preview.catalog_url],
      ["config_manifest_url", preview.config_manifest_url],
      ["code_manifest_url", preview.code_manifest_url],
    ]);
    if (preview.domain_status) renderDomainChips(preview.domain_status);
  };

  const runtimePreviewQuery = () => {
    const params = new URLSearchParams();
    const rss = form.resource_server_url.value.trim();
    const catalog = form.catalog_file_name.value.trim();
    const minClient = form.min_client_version.value.trim();
    const rollout = form.rollout_percentage.value.trim();
    if (rss) params.set("resource_server_url", rss);
    if (catalog) params.set("catalog_file_name", catalog);
    if (minClient) params.set("min_client_version", minClient);
    if (rollout) params.set("rollout_percentage", rollout);
    const configEnv = form.config_environment.value.trim();
    if (configEnv) params.set("config_environment", configEnv);
    params.set("force_update", form.force_update.checked ? "true" : "false");
    params.set("is_revoked", form.is_revoked.checked ? "true" : "false");
    return params.toString();
  };

  const fetchRuntimePreview = async () => {
    if (!currentVersion) return null;
    const qs = runtimePreviewQuery();
    const url = `/admin/projects/${projectId}/versions/${versionId}/runtime-preview${qs ? `?${qs}` : ""}`;
    const response = await fetch(url, { credentials: "same-origin" });
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || "预览失败");
    return data.preview;
  };

  const scheduleRuntimePreview = () => {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(() => {
      fetchRuntimePreview()
        .then((preview) => renderBootstrapPreview(preview))
        .catch(() => renderBootstrapPreview(null));
    }, 200);
  };

  const renderJenkinsPreview = () => {
    const list = document.getElementById("jenkinsPreviewList");
    const warnings = document.getElementById("jenkinsPreviewWarnings");
    if (!list || !currentVersion) return;
    const plan = buildPlanFromForm(currentVersion);
    renderPreviewRows(list, [
      ["CONFIG_EXPORT_ENABLED", plan.configEnabled ? "true" : "false"],
      ["RESOURCE_BUILD_ENABLED", plan.resourceEnabled ? "true" : "false"],
      ["HOT_RELEASE_ENABLED", plan.hotReleaseEnabled ? "true" : "false"],
      ["APK_BUILD_ENABLED", plan.apkBuildEnabled ? "true" : "false"],
      ["RELEASE_TARGETS", plan.releaseTargets || "-"],
      ["RELEASE_MODE", plan.releaseMode || "-"],
      ["GIT_BRANCH", plan.gitBranch || "-"],
      ["UNITY_VERSION", plan.unityVersion || "-"],
      ["PACKAGE_FORMAT", plan.packageFormat || "-"],
      ["OUTPUT_BASE_DIR", plan.outputBaseDir || "-"],
    ]);
    const missing = [];
    if (plan.configEnabled && !String(plan.configRemotePrefix || "").trim()) missing.push("配置远端前缀");
    if (plan.hotReleaseEnabled && !String(plan.releaseTargets || "").trim()) missing.push("热更发布对象");
    if (plan.apkBuildEnabled && !String(plan.outputBaseDir || "").trim()) missing.push("APK 输出目录");
    warnings.textContent = missing.length ? `缺失：${missing.join("、")}` : "";

    const domain = {
      config: Boolean(plan.configEnabled),
      code: Boolean(plan.hotReleaseEnabled && String(plan.releaseTargets || "").includes("code")),
      resource: Boolean(
        plan.resourceEnabled || (plan.hotReleaseEnabled && String(plan.releaseTargets || "").includes("resource")),
      ),
      apk: Boolean(plan.apkBuildEnabled),
    };
    renderDomainChips(domain);
    scheduleRuntimePreview();
  };

  const loadJenkinsInstances = async () => {
    const select = document.getElementById("jenkinsInstanceSelect");
    if (!select) return;
    try {
      const response = await fetch("/api/jenkins-manage/list", { credentials: "same-origin" });
      const data = await response.json();
      (data.instances || []).forEach((item) => {
        if (!item.id) return;
        const label = `${item.port || item.id} — ${item.status === "running" ? "运行中" : "已停止"}`;
        select.insertAdjacentHTML("beforeend", `<option value="${esc(item.id)}">${esc(label)}</option>`);
      });
    } catch (_error) {
      /* keep default option */
    }
  };

  const mergeGroupTemplate = (version, groupMeta) => {
    if (!isGroupMode || !groupMeta) return version;
    const merged = { ...version };
    const template = groupMeta.pipeline_template;
    if (template && typeof template === "object") {
      merged.pipeline = template;
    }
    [
      "jenkins_instance_id",
      "jenkins_job_id",
      "resource_server_url",
      "catalog_file_name",
      "min_client_version",
      "rollout_percentage",
      "force_update",
      "is_revoked",
    ].forEach((key) => {
      if (groupMeta[key] !== undefined && groupMeta[key] !== null && String(groupMeta[key]).trim() !== "") {
        merged[key] = groupMeta[key];
      }
    });
    return merged;
  };

  const loadGroupTemplate = async (version) => {
    const params = new URLSearchParams();
    if (groupEnvKey) params.set("env_key", groupEnvKey);
    if (groupPlatform) params.set("platform", groupPlatform);
    const vn = groupVersionName || version?.version_name || "";
    if (!vn) return null;
    const response = await fetch(`/admin/projects/${projectId}/version-groups?${params.toString()}`, {
      credentials: "same-origin",
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "加载版本组模板失败");
    const meta = (data.version_groups || []).find((row) => String(row.version_name || "") === String(vn)) || null;
    currentGroupMeta = meta;
    return meta;
  };

  const applyBootstrapDefaults = (version, bootstrap) => {
    const merged = { ...version };
    Object.entries(bootstrap || {}).forEach(([key, value]) => {
      if (value === null || value === undefined) return;
      if (["rollout_percentage", "force_update", "is_revoked"].includes(key)) {
        if (merged[key] === undefined || merged[key] === null) merged[key] = value;
        return;
      }
      if (!String(merged[key] ?? "").trim() && String(value).trim()) merged[key] = value;
    });
    if (!String(merged.resource_server_url || "").trim() && defaultResourceServerUrl) {
      merged.resource_server_url = defaultResourceServerUrl;
    }
    return merged;
  };

  const loadEffectiveBootstrap = async () => {
    if (!versionId) return {};
    try {
      const response = await fetch(`/api/projects/${projectId}/versions/${encodeURIComponent(versionId)}/effective-pipeline`, {
        credentials: "same-origin",
      });
      const data = await response.json();
      if (!response.ok) return {};
      return data.bootstrap || {};
    } catch (_error) {
      return {};
    }
  };

  const loadVersion = async () => {
    if (!versionId) {
      const groupMeta = await loadGroupTemplate({ version_name: groupVersionName });
      const stub = {
        version_name: groupVersionName,
        platform: groupPlatform || "android",
        env_key: groupEnvKey,
        version_code: "",
        channel: "common",
        stage: "dev",
        pipeline: groupMeta?.pipeline_template || {},
      };
      currentVersion = mergeGroupTemplate(stub, groupMeta);
      currentVersion = applyBootstrapDefaults(currentVersion, {
        resource_server_url: defaultResourceServerUrl,
        catalog_file_name: defaultCatalogName(stub),
        min_client_version: groupVersionName,
      });
      fillForm(currentVersion);
      renderJenkinsPreview();
      return currentVersion;
    }
    const response = await fetch(`/admin/projects/${projectId}/versions/list`, { credentials: "same-origin" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "加载版本失败");
    const version = (data.versions || []).find((row) => String(row.id) === String(versionId));
    if (!version) throw new Error("VersionCode 不存在或无权访问");
    if (isGroupMode) {
      const groupMeta = await loadGroupTemplate(version);
      currentVersion = mergeGroupTemplate(version, groupMeta);
    } else {
      currentVersion = version;
    }
    const bootstrap = await loadEffectiveBootstrap();
    currentVersion = applyBootstrapDefaults(currentVersion, bootstrap);
    fillForm(currentVersion);
    renderJenkinsPreview();
    return currentVersion;
  };

  const saveGroupTemplateOnly = async () => {
    const pipeline = buildPipelineFromForm(currentVersion || { version_name: groupVersionName, platform: groupPlatform });
    const payload = {
      version_name: groupVersionName,
      env_key: groupEnvKey,
      platform: groupPlatform,
      pipeline_template: pipeline,
      jenkins_instance_id: form.jenkins_instance_id.value.trim(),
      jenkins_job_id: form.jenkins_job_id.value.trim(),
      resource_server_url: form.resource_server_url.value.trim(),
      catalog_file_name: form.catalog_file_name.value.trim(),
      min_client_version: form.min_client_version.value.trim(),
      rollout_percentage: Number(form.rollout_percentage.value.trim() || "100"),
      force_update: form.force_update.checked,
      is_revoked: form.is_revoked.checked,
    };
    const channelKey = String(currentVersion?.channel || currentVersion?.channel_id || "").trim();
    const overrideJob = form.channel_jenkins_job_override?.value.trim() || "";
    const overrides = { ...(currentGroupMeta?.jenkins_job_overrides || {}) };
    if (channelKey) {
      if (overrideJob) overrides[channelKey] = overrideJob;
      else delete overrides[channelKey];
    }
    if (Object.keys(overrides).length) payload.jenkins_job_overrides = overrides;
    const response = await fetch(`/admin/projects/${projectId}/version-groups/update`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || "保存失败");
  };

  const save = async (version) => {
    if (!canEdit) {
      toast("当前账号无编辑权限", "error");
      return;
    }
    saveBtn.disabled = true;
    try {
      if (!versionId && isGroupMode) {
        await saveGroupTemplateOnly();
        toast("版本组管线模板已保存");
        await loadVersion();
        return;
      }
      const response = await fetch(`/admin/projects/${projectId}/versions/update`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload(version)),
      });
      const data = await response.json();
      if (!response.ok || data.error) throw new Error(data.error || "保存失败");
      if (isGroupMode) {
        const channelKey = String(version?.channel || version?.channel_id || "").trim();
        const overrideJob = form.channel_jenkins_job_override?.value.trim() || "";
        const overrides = { ...(currentGroupMeta?.jenkins_job_overrides || {}) };
        if (channelKey) {
          if (overrideJob) overrides[channelKey] = overrideJob;
          else delete overrides[channelKey];
        }
        await fetch(`/admin/projects/${projectId}/version-groups/update`, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            version_name: version.version_name,
            env_key: version.env_key || groupEnvKey,
            platform: version.platform || groupPlatform,
            jenkins_job_overrides: overrides,
          }),
        });
      }
      toast(isGroupMode ? "版本组管线模板已保存并同步到组内 VersionCode" : "构建参数已保存");
      await loadVersion();
    } catch (error) {
      toast(error.message || "保存失败", "error");
    } finally {
      saveBtn.disabled = false;
    }
  };

  form.addEventListener("input", (event) => {
    if (currentVersion && (event.target === form.app_name || event.target === form.package_format)) {
      applyDerivedFields(currentVersion);
    }
    renderJenkinsPreview();
  });
  form.addEventListener("change", (event) => {
    if (currentVersion && event.target === form.package_format) {
      applyDerivedFields(currentVersion);
    }
    if (event.target === form.hot_release_enabled) {
      syncHotPresetHighlight();
    }
    renderJenkinsPreview();
  });
  root.querySelectorAll("[data-path-pick]").forEach((btn) => {
    btn.addEventListener("click", () => nativePathPick(btn.dataset.pathPick, btn.dataset.pathMode || "dir"));
  });
  root.querySelector("[data-refresh-preview]")?.addEventListener("click", () => renderJenkinsPreview());
  root.querySelector("[data-refresh-bootstrap]")?.addEventListener("click", () => scheduleRuntimePreview());
  saveBtn?.addEventListener("click", async () => {
    try {
      const version = currentVersion || await loadVersion();
      await save(version);
    } catch (error) {
      toast(error.message || "保存失败", "error");
    }
  });

  if (!canEdit) {
    saveBtn.disabled = true;
    form.querySelectorAll("input, select, textarea").forEach((field) => {
      field.disabled = true;
    });
    root.querySelectorAll("[data-path-pick]").forEach((btn) => {
      btn.disabled = true;
    });
  }

  const FIELD_SECTION_MAP = {
    jenkins_instance_id: "jenkins",
    jenkins_job_id: "jenkins",
    config_export_enabled: "config_export",
    resource_build_enabled: "resource_build",
    hot_release_enabled: "hot_release",
    code_enabled: "hot_release",
    apk_build_enabled: "artifact",
    resource_server_url: "client_policy",
  };

  function applyReleaseOrderFocus() {
    const params = new URLSearchParams(location.search);
    if (params.get("from") !== "release-order") return;
    const highlights = (params.get("highlight") || "").split(",").map((x) => x.trim()).filter(Boolean);
    const reason = params.get("focus_reason") || "请填写下方红色高亮字段并点击「保存配置」。";
    const releaseOrderId = params.get("release_order_id") || "";
    let banner = root.querySelector(".release-focus-banner");
    if (!banner) {
      banner = document.createElement("div");
      banner.className = "release-focus-banner";
      const anchor = root.querySelector(".build-config-journey-banner") || root.querySelector(".workflow-heading");
      anchor?.insertAdjacentElement("afterend", banner);
    }
    const returnHref = releaseOrderId
      ? `/admin/projects/${encodeURIComponent(projectId)}/release-orders/${encodeURIComponent(releaseOrderId)}`
      : "";
    banner.innerHTML = `<div><strong>来自发布单 · 待补充配置</strong><p>${esc(reason)}</p></div>${returnHref ? `<a class="release-focus-return" href="${returnHref}">返回发布单</a>` : ""}`;
    const rssField = form.querySelector('[name="resource_server_url"]');
    const rssFilled = rssField && String(rssField.value || "").trim();
    const allHighlightsFilled = highlights.every((name) => {
      const field = form.querySelector(`[name="${name}"]`) || document.getElementById(name);
      if (!field) return true;
      return field.type === "checkbox" ? field.checked : Boolean(String(field.value || "").trim());
    });
    if (rssFilled && allHighlightsFilled) {
      banner.classList.add("release-focus-banner-ready");
      banner.innerHTML = `<div><strong>来自发布单 · 客户端策略已填写</strong><p>请确认资源服务器 URL 无误后点击「保存配置」，再返回发布单点「重新预检」。剩余阻断项通常是：code 包未构建、OSS 产物未上传、Runtime 未启动。</p></div>${returnHref ? `<a class="release-focus-return" href="${returnHref}">返回发布单</a>` : ""}`;
    } else {
      banner.classList.remove("release-focus-banner-ready");
    }
    const touchedSections = new Set();
    highlights.forEach((name) => {
      const field = form.querySelector(`[name="${name}"]`) || document.getElementById(name);
      if (!field) return;
      const label = field.closest("label") || field.closest(".build-config-strategy-panel");
      const alreadyFilled = field.type === "checkbox" ? field.checked : String(field.value || "").trim();
      if (alreadyFilled) return;
      label?.classList.add("field-highlight-required");
      field.classList.add("field-highlight-required");
      const section = FIELD_SECTION_MAP[name] || params.get("section");
      if (section) touchedSections.add(section);
      const clearHighlight = () => {
        const filled = field.type === "checkbox" ? field.checked : String(field.value || "").trim();
        if (filled) {
          label?.classList.remove("field-highlight-required");
          field.classList.remove("field-highlight-required");
        }
      };
      field.addEventListener("input", clearHighlight);
      field.addEventListener("change", clearHighlight);
    });
    touchedSections.forEach((section) => {
      root.querySelector(`[data-section-tab="${section}"]`)?.classList.add("field-highlight-step");
    });
    requestAnimationFrame(() => {
      const first = form.querySelector(".field-highlight-required");
      first?.scrollIntoView({ behavior: "smooth", block: "center" });
      if (first && typeof first.focus === "function") first.focus();
    });
  }

  activateSection(sectionFromUrl());
  loadJenkinsInstances()
    .then(() => loadVersion())
    .then(() => applyReleaseOrderFocus())
    .catch((error) => toast(error.message || "加载失败", "error"));
})();
