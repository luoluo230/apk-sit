(() => {
  const page = document.querySelector("[data-delivery-page]");
  if (!page) return;
  const projectId = page.dataset.projectId;
  const envLabels = {development:"开发环境",testing:"测试环境",staging:"预发环境",production:"生产环境"};
  const statusLabels = {draft:"草稿",building:"构建中",artifacts_ready:"产物已就绪",prechecking:"预检中",precheck_failed:"预检失败",ready:"可发布",awaiting_approval:"待审批",approved:"已审批",publishing:"发布中",published:"已发布",publish_failed:"发布失败",verifying:"验证中",verified:"验证通过",verify_failed:"验证失败",rolled_back:"已回滚",cancelled:"已取消"};
  const artifactStatusLabels = {registered:"已登记",available:"可用",reachable:"可达",missing:"缺失",unreachable:"不可达",invalid:"无效"};
  const artifactTypeLabels = {apk:"APK 安装包",resource:"资源包",config:"配置包",code:"代码热更包"};
  const bindingSourceLabels = {project_default:"项目默认",env_channel:"环境与渠道",version:"大版本覆盖",version_override:"大版本覆盖",default:"项目默认"};
  const parseApiError = (result, fallback) => {
    if (!result || typeof result !== "object") return fallback;
    const err = result.error;
    if (typeof err === "string" && err) return err;
    if (err && typeof err === "object") return err.message || err.text || fallback;
    return result.error_text || result.error_legacy || fallback;
  };
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const api = async (path, options) => {
    const response = await fetch(path, options);
    const result = await response.json();
    if (!response.ok || result.ok === false) throw new Error(result.error || "请求失败");
    return result.data;
  };
  const toast = (message, type="success") => {
    let host = document.querySelector(".toast-stack");
    if (!host) { host = document.createElement("div"); host.className = "toast-stack"; document.body.append(host); }
    const node = document.createElement("div"); node.className = `toast ${type}`; node.textContent = message; host.append(node); setTimeout(() => node.remove(), 3500);
  };
  const status = (value) => `<span class="status-pill ${esc(value)}">${esc(statusLabels[value] || value || "未配置")}</span>`;
  const row = (label, value, extra="") => `<div class="detail-row"><strong>${esc(label)}</strong><span>${esc(value || "-")}</span><b>${extra}</b></div>`;
  const csrfHeaders = () => {
    const token = document.querySelector('meta[name="csrf-token"]');
    return token && token.content ? { "X-CSRFToken": token.content } : {};
  };
  const matrixActions = (line, envKey) => {
    const query = `env_key=${encodeURIComponent(envKey)}&channel_id=${encodeURIComponent(line.channel_id)}&platform=${encodeURIComponent(line.platform)}`;
    const primary = line.configured
      ? `<a class="matrix-btn primary" href="/admin/projects/${projectId}/release-orders/new?${query}">发布</a>`
      : `<a class="matrix-btn primary" href="/admin/projects/${projectId}/versions?${query}">添加 VC</a>`;
    return `<div class="matrix-actions">${primary}<a class="matrix-btn" href="/admin/projects/${projectId}/versions?${query}">版本</a><a class="matrix-btn" href="/admin/projects/${projectId}/topology-bindings?${query}">拓扑</a></div>`;
  };
  const renderChannelList = (host, assigned, { manageable = false } = {}) => {
    if (!host) return;
    host.innerHTML = assigned.length
      ? assigned.map((item) => {
          const enabled = Boolean(item.enabled);
          const status = enabled ? "" : " is-disabled";
          const meta = enabled ? "" : " · 已禁用";
          const toggle = manageable
            ? (enabled
              ? `<button class="channel-disable" type="button" data-disable-channel="${esc(item.id)}">禁用</button>`
              : `<button class="channel-enable" type="button" data-enable-channel="${esc(item.id)}">启用</button>`)
            : "";
          const remove = manageable
            ? `<button class="channel-remove" type="button" data-remove-channel="${esc(item.id)}">移除</button>`
            : "";
          return `<div class="channel-item${status}"><div><strong>${esc(item.name)}</strong><small>ID: ${esc(item.id)}${meta}</small></div><div class="channel-actions">${toggle}${remove}</div></div>`;
        }).join("")
      : '<div class="ui-empty">尚未配置项目渠道</div>';
    if (!manageable) return;
    host.querySelectorAll("[data-disable-channel]").forEach((button) => {
      button.onclick = async () => {
        if (!confirm(`确认禁用渠道「${button.dataset.disableChannel}」？禁用后不会出现在交付线与发布流程。`)) return;
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/channels/disable`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...csrfHeaders() },
            credentials: "same-origin",
            body: JSON.stringify({ channel_id: button.dataset.disableChannel }),
          });
          const result = await response.json();
            if (!response.ok || result.error || result.ok === false) throw new Error(parseApiError(result, "禁用失败"));
          toast("渠道已禁用");
          await loadProjectChannels();
          if (page.dataset.deliveryPage === "overview") await loadOverview();
          if (page.dataset.deliveryPage === "environment") await loadEnvironmentDetail();
        } catch (error) {
          toast(error.message, "error");
        }
      };
    });
    host.querySelectorAll("[data-enable-channel]").forEach((button) => {
      button.onclick = async () => {
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/channels/enable`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...csrfHeaders() },
            credentials: "same-origin",
            body: JSON.stringify({ channel_id: button.dataset.enableChannel }),
          });
          const result = await response.json();
          if (!response.ok || result.error || result.ok === false) throw new Error(parseApiError(result, "启用失败"));
          toast("渠道已启用");
          await loadProjectChannels();
          if (page.dataset.deliveryPage === "overview") await loadOverview();
          if (page.dataset.deliveryPage === "environment") await loadEnvironmentDetail();
        } catch (error) {
          toast(error.message, "error");
        }
      };
    });
    host.querySelectorAll("[data-remove-channel]").forEach((button) => {
      button.onclick = async () => {
        if (!confirm(`确认从项目中移除渠道「${button.dataset.removeChannel}」？`)) return;
        try {
          const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/channels/remove`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...csrfHeaders() },
            credentials: "same-origin",
            body: JSON.stringify({ channel_id: button.dataset.removeChannel }),
          });
          const result = await response.json();
          if (!response.ok || result.error || result.ok === false) throw new Error(parseApiError(result, "移除失败"));
          toast("渠道已移除");
          await loadProjectChannels();
          if (page.dataset.deliveryPage === "overview") await loadOverview();
          if (page.dataset.deliveryPage === "environment") await loadEnvironmentDetail();
        } catch (error) {
          toast(error.message, "error");
        }
      };
    });
  };
  const loadProjectChannels = async () => {
    const listHost = document.getElementById("projectChannelList") || document.getElementById("envChannelList");
    const select = document.getElementById("projectChannelAddSelect");
    if (!listHost) return [];
    try {
      const [projectRes, catalogRes] = await Promise.all([
        fetch(`/admin/projects/get/${encodeURIComponent(projectId)}`, { credentials: "same-origin" }).then((r) => r.json()),
        fetch("/admin/channels", { credentials: "same-origin" }).then((r) => r.json()),
      ]);
      const project = projectRes.project || projectRes.data?.project || {};
      const catalog = catalogRes.channels || catalogRes.data?.channels || [];
      const assignedIds = Array.isArray(project.channels) && project.channels.length ? project.channels : catalog.map((item) => item.id);
      const disabledIds = new Set(
        Array.isArray(project.disabled_channels) ? project.disabled_channels.map((id) => String(id)) : []
      );
      const assigned = assignedIds.map((id) => {
        const row = catalog.find((item) => String(item.id) === String(id)) || { id, name: id };
        const cid = String(row.id || id);
        return {
          id: cid,
          name: String(row.name || row.id || id),
          enabled: !disabledIds.has(cid),
        };
      });
      renderChannelList(listHost, assigned, { manageable: listHost.id === "projectChannelList" });
      renderChannelChips(assigned);
      if (listHost.classList.contains("channel-list-inline") && assigned.length) {
        listHost.classList.add("has-channels");
      }
      if (select) {
        const available = catalog.filter((item) => !assignedIds.includes(String(item.id)));
        select.innerHTML = '<option value="">选择要添加的渠道</option>' + available.map((item) => `<option value="${esc(item.id)}">${esc(item.name)} (${esc(item.id)})</option>`).join("");
      }
      const filterChannel = document.getElementById("overviewChannelCount");
      if (filterChannel) {
        const enabledCount = assigned.filter((item) => item.enabled).length;
        const disabledCount = assigned.length - enabledCount;
        filterChannel.textContent = disabledCount
          ? `${enabledCount} 个启用 / ${assigned.length} 总计`
          : (assigned.length ? `${assigned.length} 个启用` : "未配置渠道");
      }
      return assigned;
    } catch (error) {
      if (listHost.id === "projectChannelList") {
        listHost.innerHTML = `<div class="ui-empty">${esc(error.message || "渠道加载失败")}</div>`;
      }
      return [];
    }
  };
  const renderChannelChips = (assigned) => {
    const host = document.getElementById("overviewChannelChipsList");
    if (!host) return;
    host.innerHTML = assigned.length
      ? assigned.map((item) => `<span class="channel-chip${item.enabled ? "" : " is-disabled"}">${esc(item.name)}${item.enabled ? "" : "（已禁用）"}</span>`).join("")
      : '<span class="channel-chip muted">未配置渠道</span>';
  };
  const overviewFilterParams = () => {
    const params = new URLSearchParams(location.search);
    return {
      env_key: params.get("env_key") || "",
      channel_id: params.get("channel_id") || "",
      platform: params.get("platform") || "",
      health: params.get("health") || "",
    };
  };
  const overviewQueryString = (filters) => {
    const params = new URLSearchParams();
    if (location.search.includes("tab=channels")) params.set("tab", "channels");
    Object.entries(filters || overviewFilterParams()).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    const text = params.toString();
    return text ? `?${text}` : "";
  };
  const bindManifestBootstrap = () => {
    const manifestBtn = document.getElementById("btnOverviewBootstrapScopes");
    const manifestStatus = document.getElementById("overviewManifestStatus");
    if (!manifestBtn || !manifestStatus || manifestBtn.dataset.bound === "1") return;
    manifestBtn.dataset.bound = "1";
    fetch(`/api/release/manifests/${encodeURIComponent(projectId)}`, { credentials: "same-origin" })
      .then((r) => r.json())
      .then((d) => {
        manifestStatus.textContent = d.ok && d.manifest?.project_id ? `Manifest 已注册（${d.manifest.channels?.length || 0} 个渠道）` : "尚未注册 Manifest，初始化前请先配置项目渠道";
      })
      .catch(() => {
        manifestStatus.textContent = "无法读取 Manifest 状态";
      });
    manifestBtn.onclick = async () => {
      try {
        const result = await fetch(`/api/release/manifests/${encodeURIComponent(projectId)}/bootstrap-scopes`, {
          method: "POST",
          headers: { "X-CSRFToken": document.querySelector('meta[name="csrf-token"]')?.content || "" },
          credentials: "same-origin",
        }).then((r) => r.json());
        if (!result.ok) throw new Error(result.error || "初始化失败");
        toast(`已初始化 ${result.count || 0} 条交付线 Scope`);
        await loadOverview();
      } catch (error) {
        toast(error.message, "error");
      }
    };
  };
  const initOverviewTabs = () => {
    const params = new URLSearchParams(location.search);
    const setTab = (name) => {
      document.querySelectorAll("[data-overview-tab]").forEach((btn) => btn.classList.toggle("active", btn.dataset.overviewTab === name));
      document.querySelectorAll("[data-overview-panel]").forEach((panel) => {
        const show = panel.dataset.overviewPanel === name;
        panel.classList.toggle("is-hidden", !show);
        panel.hidden = !show;
      });
      const url = new URL(location.href);
      if (name === "channels") url.searchParams.set("tab", "channels");
      else url.searchParams.delete("tab");
      history.replaceState(null, "", `${url.pathname}${url.search}`);
      if (name === "channels") {
        loadProjectChannels();
        bindProjectChannelAdd();
        bindManifestBootstrap();
        bindProjectEnvAdd();
        loadProjectEnvironments();
      }
    };
    document.querySelectorAll("[data-overview-tab]").forEach((btn) => {
      btn.onclick = () => setTab(btn.dataset.overviewTab);
    });
    document.querySelectorAll("[data-overview-tab-jump]").forEach((btn) => {
      btn.onclick = () => setTab(btn.dataset.overviewTabJump);
    });
    document.getElementById("btnManageEnvironments")?.addEventListener("click", () => setTab("channels"));
    setTab(params.get("tab") === "channels" ? "channels" : "overview");
  };
  const populateOverviewFilters = (data) => {
    const envSelect = document.getElementById("filterEnvKey");
    const channelSelect = document.getElementById("filterChannelId");
    const platformSelect = document.getElementById("filterPlatform");
    const healthSelect = document.getElementById("filterHealth");
    const filters = overviewFilterParams();
    if (envSelect) {
      const options = data.environment_options || [];
      envSelect.innerHTML = '<option value="">全部环境</option>' + options.map((row) => `<option value="${esc(row.env_key)}">${esc(row.env_label)}</option>`).join("");
      envSelect.value = filters.env_key;
    }
    if (channelSelect) {
      const options = data.channel_options || [];
      channelSelect.innerHTML = '<option value="">全部渠道</option>' + options.map((row) => `<option value="${esc(row.channel_id)}">${esc(row.channel_name)}</option>`).join("");
      channelSelect.value = filters.channel_id;
    }
    if (platformSelect) {
      const options = data.platform_options || [];
      platformSelect.innerHTML = '<option value="">全部平台</option>' + options.map((row) => `<option value="${esc(row.value)}">${esc(row.label)}</option>`).join("");
      platformSelect.value = filters.platform;
    }
    if (healthSelect) {
      const options = data.health_options || [];
      healthSelect.innerHTML = '<option value="">全部状态</option>' + options.map((row) => `<option value="${esc(row.value)}">${esc(row.label)}</option>`).join("");
      healthSelect.value = filters.health;
    }
  };
  const bindOverviewFilters = () => {
    const apply = () => {
      const filters = {
        env_key: document.getElementById("filterEnvKey")?.value || "",
        channel_id: document.getElementById("filterChannelId")?.value || "",
        platform: document.getElementById("filterPlatform")?.value || "",
        health: document.getElementById("filterHealth")?.value || "",
      };
      const url = new URL(location.href);
      ["env_key", "channel_id", "platform", "health"].forEach((key) => {
        if (filters[key]) url.searchParams.set(key, filters[key]);
        else url.searchParams.delete(key);
      });
      history.replaceState(null, "", `${url.pathname}${url.search}`);
      loadOverview().catch((error) => toast(error.message, "error"));
    };
    ["filterEnvKey", "filterChannelId", "filterPlatform", "filterHealth"].forEach((id) => {
      const node = document.getElementById(id);
      if (node) node.onchange = apply;
    });
    document.getElementById("btnResetOverviewFilters")?.addEventListener("click", () => {
      const url = new URL(location.href);
      ["env_key", "channel_id", "platform", "health"].forEach((key) => url.searchParams.delete(key));
      history.replaceState(null, "", `${url.pathname}${url.search}`);
      loadOverview().catch((error) => toast(error.message, "error"));
    });
  };
  const loadProjectEnvironments = async () => {
    const host = document.getElementById("projectEnvList");
    if (!host) return;
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/environments`, { credentials: "same-origin" });
      const result = await response.json();
      const rows = result.data?.environments || result.environments || [];
      host.innerHTML = rows.length
        ? rows.map((row) => {
            const key = esc(row.env_key);
            const builtin = Boolean(row.builtin);
            const enabled = Boolean(row.enabled);
            const toggle = enabled
              ? `<button type="button" class="env-disable" data-env-toggle="${key}" data-enabled="0">禁用</button>`
              : `<button type="button" class="env-enable" data-env-toggle="${key}" data-enabled="1">启用</button>`;
            const remove = builtin ? "" : `<button type="button" class="env-remove" data-env-remove="${key}">删除</button>`;
            return `<div class="env-config-item${enabled ? "" : " is-disabled"}"><div><strong>${esc(row.label)}</strong><small>${key}${builtin ? " · 内置" : ""}${enabled ? "" : " · 已禁用"}</small></div><div class="env-config-actions">${toggle}${remove}</div></div>`;
          }).join("")
        : '<div class="ui-empty">暂无环境配置</div>';
      host.querySelectorAll("[data-env-toggle]").forEach((button) => {
        button.onclick = async () => {
          try {
            const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(button.dataset.envToggle)}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json", ...csrfHeaders() },
              credentials: "same-origin",
              body: JSON.stringify({ enabled: button.dataset.enabled === "1" }),
            });
            const result = await response.json();
            if (!response.ok || result.ok === false) throw new Error(parseApiError(result, "更新失败"));
            toast(button.dataset.enabled === "1" ? "环境已启用" : "环境已禁用");
            await loadProjectEnvironments();
            await loadOverview();
          } catch (error) {
            toast(error.message, "error");
          }
        };
      });
      host.querySelectorAll("[data-env-remove]").forEach((button) => {
        button.onclick = async () => {
          if (!confirm(`确认删除环境「${button.dataset.envRemove}」？`)) return;
          try {
            const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(button.dataset.envRemove)}`, {
              method: "DELETE",
              headers: csrfHeaders(),
              credentials: "same-origin",
            });
            const result = await response.json();
            if (!response.ok || result.ok === false) throw new Error(parseApiError(result, "删除失败"));
            toast("环境已删除");
            await loadProjectEnvironments();
            await loadOverview();
          } catch (error) {
            toast(error.message, "error");
          }
        };
      });
    } catch (error) {
      host.innerHTML = `<div class="ui-empty">${esc(error.message || "环境加载失败")}</div>`;
    }
  };
  const bindProjectEnvAdd = () => {
    const button = document.getElementById("btnProjectEnvAdd");
    if (!button || button.dataset.bound === "1") return;
    button.dataset.bound = "1";
    button.onclick = async () => {
      const envKey = document.getElementById("projectEnvKeyInput")?.value?.trim() || "";
      const label = document.getElementById("projectEnvLabelInput")?.value?.trim() || "";
      if (!envKey || !label) {
        toast("请填写环境 key 与名称", "error");
        return;
      }
      try {
        button.disabled = true;
        const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/environments`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...csrfHeaders() },
          credentials: "same-origin",
          body: JSON.stringify({ env_key: envKey, label }),
        });
        const result = await response.json();
        if (!response.ok || result.ok === false) throw new Error(parseApiError(result, "添加失败"));
        toast("环境已添加");
        document.getElementById("projectEnvKeyInput").value = "";
        document.getElementById("projectEnvLabelInput").value = "";
        await loadProjectEnvironments();
        await loadOverview();
      } catch (error) {
        toast(error.message, "error");
      } finally {
        button.disabled = false;
      }
    };
  };
  const bindProjectChannelAdd = () => {
    const button = document.getElementById("btnProjectChannelAdd");
    const select = document.getElementById("projectChannelAddSelect");
    if (!button || !select || button.dataset.bound === "1") return;
    button.dataset.bound = "1";
    button.onclick = async () => {
      const channelId = select.value;
      if (!channelId) {
        toast("请先选择渠道", "error");
        return;
      }
      try {
        button.disabled = true;
        const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/channels/add`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...csrfHeaders() },
          credentials: "same-origin",
          body: JSON.stringify({ channel_id: channelId }),
        });
        const result = await response.json();
        if (!response.ok || result.error || result.ok === false) throw new Error(parseApiError(result, "添加失败"));
        toast("渠道已添加");
        select.value = "";
        await loadProjectChannels();
        if (page.dataset.deliveryPage === "overview") await loadOverview();
      } catch (error) {
        toast(error.message, "error");
      } finally {
        button.disabled = false;
      }
    };
  };
  const currentContext = () => {
    const source = new URLSearchParams(location.search);
    const query = new URLSearchParams();
    ["env_key","channel_id","platform","version_name","version_code","release_order_id"].forEach(key => source.get(key) && query.set(key, source.get(key)));
    return query.toString() ? `?${query}` : "";
  };

  async function loadOverview() {
    const assigned = await loadProjectChannels();
    renderChannelChips(assigned);
    const data = await api(`/api/projects/${encodeURIComponent(projectId)}/overview${overviewQueryString()}`);
    populateOverviewFilters(data);
    const cards = data.environments || [];
    const totalOrders = cards.reduce((sum, item) => sum + item.release_order_count, 0);
    const totalLines = cards.reduce((sum, item) => sum + (item.delivery_line_count || 0), 0);
    const configuredLines = cards.reduce((sum, item) => sum + (item.configured_line_count || 0), 0);
    const kpis = [
      ["kpi_health.svg", "交付线总数", totalLines],
      ["kpi_health.svg", "已配置交付线", configuredLines],
      ["kpi_build.svg", "处理中任务", cards.reduce((s, x) => s + x.processing_count, 0)],
      ["kpi_change.svg", "待处理变更", cards.reduce((s, x) => s + x.failed_count + x.pending_approval_count, 0)],
      ["kpi_member.svg", "发布单总数", totalOrders],
    ];
    document.getElementById("overviewKpis").innerHTML = kpis.map(([icon, label, value]) => `<article class="kpi-card"><img src="/static/project_ui/svg/${icon}" alt=""><div><span>${label}</span><strong>${value}</strong></div></article>`).join("");
    const healthLabels = { healthy: "运行中", blocked: "存在阻断", warning: "待处理", processing: "处理中", unconfigured: "未配置" };
    document.getElementById("environmentCards").innerHTML = cards.length
      ? cards.map((item) => `<article class="environment-card">
      <div class="environment-head"><h3>${esc(item.env_label)}</h3><span class="environment-status ${item.health}">${healthLabels[item.health] || item.health}</span></div>
      <div class="environment-summary">
        <div><span>交付线</span><strong>${item.configured_line_count || 0} / ${item.delivery_line_count || 0}</strong></div>
        <div><span>阻断</span><strong>${item.failed_count || 0}</strong></div>
        <div><span>进行中</span><strong>${item.processing_count || 0}</strong></div>
        <div><span>待审批</span><strong>${item.pending_approval_count || 0}</strong></div>
      </div>
      <p class="environment-hint">${esc(item.blocker_hint || (item.unconfigured_line_count ? `还有 ${item.unconfigured_line_count} 条交付线未配置` : "各渠道×平台交付线可在环境详情中查看"))}</p>
      <div class="environment-action-bar">
        <a class="matrix-btn primary" href="/admin/projects/${projectId}/environments/${item.env_key}">环境详情</a>
        <a class="matrix-btn" href="/admin/projects/${projectId}/versions?env_key=${item.env_key}">版本</a>
        <a class="matrix-btn" href="/admin/projects/${projectId}/topology-bindings?env_key=${item.env_key}">拓扑</a>
      </div>
      <div class="environment-actions"><a class="icon-link" href="/admin/projects/${projectId}/release-orders?env_key=${item.env_key}">查看发布单<img src="/static/project_ui/svg/action_next.svg" alt=""></a></div>
    </article>`).join("")
      : '<div class="ui-empty">当前筛选下无匹配环境</div>';
    const events = cards.flatMap((item) => item.latest_orders || []).sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at))).slice(0, 7);
    document.getElementById("overviewActivity").innerHTML = events.length ? events.map((item) => `<a class="activity-row" href="/admin/projects/${projectId}/release-orders/${item.release_order_id}"><span>${status(item.status)}</span><strong>${esc(item.version_name)} / ${esc(item.version_code)} 发布单更新</strong><span>${esc(item.updated_at)}</span></a>`).join("") : '<div class="ui-empty">暂无最近动态</div>';
    document.getElementById("overviewUpdatedAt").textContent = new Date().toLocaleString("zh-CN");
  }

  async function loadEnvironmentDetail() {
    const envKey = page.dataset.envKey;
    const data = await api(`/api/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(envKey)}`);
    const summary = data.summary || {};
    document.getElementById("envDetailTitle").textContent = data.env_label || envKey;
    document.getElementById("envDetailSummary").innerHTML = [
      ["交付线", `${summary.configured_line_count || 0} / ${summary.delivery_line_count || 0}`],
      ["未配置", summary.unconfigured_line_count || 0],
      ["阻断发布单", summary.failed_count || 0],
      ["进行中", summary.processing_count || 0],
      ["待审批", summary.pending_approval_count || 0],
    ].map(([label, value]) => `<article class="kpi-card"><div><span>${label}</span><strong>${value}</strong></div></article>`).join("");
    const lines = data.delivery_lines || [];
    document.getElementById("deliveryMatrix").innerHTML = lines.length
      ? `<div class="matrix-head"><span>渠道</span><span>平台</span><span>当前版本</span><span>拓扑</span><span>Bundle</span><span>操作</span></div>` +
        lines.map((line) => {
          const versionText = line.version_name ? `${line.version_name} / ${line.version_code}` : "未配置";
          return `<div class="matrix-row ${line.configured ? "" : "unconfigured"}">
            <div><strong>${esc(line.channel_name)}</strong></div>
            <div>${esc(line.platform_label || line.platform)}</div>
            <div>${esc(versionText)}</div>
            <div>${esc(line.topology_id || "-")}</div>
            <div>${esc(line.bundle_id || "-")}</div>
            ${matrixActions(line, envKey)}
          </div>`;
        }).join("")
      : '<div class="ui-empty">当前环境暂无交付线，请先在项目中配置渠道并初始化 Scope。</div>';
    const versions = data.versions || [];
    document.getElementById("envVersions").innerHTML = versions.length
      ? versions.slice(0, 8).map((row) => `<div class="detail-row"><strong>${esc(row.version_name)} / ${esc(row.version_code)}</strong><span>${esc(row.channel_name)} · ${esc(row.platform)}</span><b>${esc(row.version_status || "")}</b></div>`).join("")
      : '<div class="ui-empty">本环境暂无 VersionCode</div>';
    const orders = data.release_orders || [];
    document.getElementById("envOrders").innerHTML = orders.length
      ? orders.slice(0, 6).map((item) => `<a class="activity-row" href="/admin/projects/${projectId}/release-orders/${item.release_order_id}"><span>${status(item.status)}</span><strong>${esc(item.version_name)} / ${esc(item.version_code)}</strong><span>${esc(item.updated_at)}</span></a>`).join("")
      : '<div class="ui-empty">本环境暂无进行中的发布单</div>';
    const manifest = data.manifest || {};
    document.getElementById("manifestStatus").textContent = manifest.project_id ? `Manifest 已注册（${manifest.channels?.length || 0} 个渠道）` : "尚未注册 Manifest";
    document.getElementById("btnBootstrapScopes").onclick = async () => {
      try {
        const result = await fetch(`/api/release/manifests/${encodeURIComponent(projectId)}/bootstrap-scopes`, {
          method: "POST",
          headers: { "X-CSRFToken": document.querySelector('meta[name="csrf-token"]')?.content || "" },
          credentials: "same-origin",
        }).then((r) => r.json());
        if (!result.ok) throw new Error(result.error || "初始化失败");
        toast(`已初始化 ${result.count || 0} 条交付线 Scope`);
        await loadEnvironmentDetail();
      } catch (error) {
        toast(error.message, "error");
      }
    };
    await loadProjectChannels();
  }

  const renderOrderTable = (items) => {
    const host = document.getElementById("releaseOrderList");
    host.innerHTML = `<div class="order-table-head"><span>发布单 / 版本</span><span>目标</span><span>状态</span><span>拓扑 / Runtime</span><span>更新时间</span><span>操作</span></div>` + (items.length ? items.map(item=>{const context=`?env_key=${encodeURIComponent(item.env_key)}&channel_id=${encodeURIComponent(item.channel_id)}&platform=${encodeURIComponent(item.platform)}&version_name=${encodeURIComponent(item.version_name)}&version_code=${encodeURIComponent(item.version_code)}&release_order_id=${encodeURIComponent(item.release_order_id)}`;return `<div class="order-table-row"><div><strong>${esc(item.release_order_id)}</strong><small>${esc(item.version_name)} / ${esc(item.version_code)}</small></div><div>${esc(envLabels[item.env_key])}<small>${esc(item.channel_name)} / ${esc(item.platform)}</small></div><div>${status(item.status)}</div><div>${esc(item.topology_id || "待解析")}<small>${esc(item.runtime_run_id || "未运行")}</small></div><div>${esc(item.updated_at)}</div><div class="row-actions"><a class="ui-secondary" href="/admin/projects/${projectId}/release-orders/${item.release_order_id}${context}">详情</a>${["draft","artifacts_ready","precheck_failed"].includes(item.status)?`<a class="ui-secondary" href="/admin/projects/${projectId}/release-orders/${item.release_order_id}/edit${context}">编辑</a>`:""}</div></div>`;}).join("") : '<div class="ui-empty">当前筛选条件下暂无发布单</div>');
  };
  async function setupOrders() {
    const options = await api(`/api/projects/${projectId}/context-options`);
    const fills = [["env_key",options.environments,"env_key","label"],["channel_id",options.channels,"channel_id","channel_name"],["platform",options.platforms,"value","label"]];
    fills.forEach(([name,items,key,label])=>{const select=page.querySelector(`[data-filter="${name}"]`);items.forEach(item=>select.insertAdjacentHTML("beforeend",`<option value="${esc(item[key])}">${esc(item[label])}</option>`));});
    const statusSelect=page.querySelector('[data-filter="status"]');Object.entries(statusLabels).forEach(([key,label])=>statusSelect.insertAdjacentHTML("beforeend",`<option value="${key}">${label}</option>`));
    const searchParams = new URLSearchParams(location.search);
    page.querySelectorAll("[data-filter]").forEach(select => searchParams.get(select.dataset.filter) && (select.value = searchParams.get(select.dataset.filter)));
    const load = async () => {
      const params=new URLSearchParams();page.querySelectorAll("[data-filter]").forEach(x=>x.value&&params.set(x.dataset.filter,x.value));
      let items=await api(`/api/projects/${projectId}/release-orders?${params}`);
      const search=page.querySelector("[data-order-search]").value.trim().toLowerCase();if(search)items=items.filter(x=>JSON.stringify(x).toLowerCase().includes(search));
      renderOrderTable(items);
      const summary=[["发布单总数",items.length],["处理中",items.filter(x=>["building","prechecking","publishing","verifying"].includes(x.status)).length],["待审批",items.filter(x=>x.status==="awaiting_approval").length],["阻断",items.filter(x=>["precheck_failed","publish_failed","verify_failed"].includes(x.status)).length]];
      document.getElementById("orderSummary").innerHTML=summary.map(([label,value])=>`<article class="kpi-card"><div><span>${label}</span><strong>${value}</strong></div></article>`).join("");
    };
    page.querySelectorAll("[data-filter]").forEach(x=>x.addEventListener("change",load));page.querySelector("[data-order-search]").addEventListener("input",load);page.querySelector("[data-refresh-orders]").addEventListener("click",load);load();
  }

  async function setupOrderForm() {
    const form=document.getElementById("releaseOrderForm"), orderId=page.dataset.orderId;
    const options=await api(`/api/projects/${projectId}/context-options`);
    const fill=(select,items,key,label)=>{select.innerHTML=items.map(item=>`<option value="${esc(item[key])}">${esc(item[label])}</option>`).join("");};
    const valueText=value=>typeof value==="object"&&value!==null?JSON.stringify(value,null,2):String(value??"");
    fill(form.env_key,options.environments,"env_key","label");
    fill(form.channel_id,options.channels,"channel_id","channel_name");
    fill(form.platform,options.platforms,"value","label");
    const topologySelect = form.target_topology_id;
    if (topologySelect) {
      try {
        const topoResponse = await fetch(`/api/projects/${encodeURIComponent(projectId)}/topologies`, { credentials: "same-origin" });
        const topoData = await topoResponse.json();
        const topologies = topoData.data?.topologies || [];
        topologySelect.innerHTML = '<option value="">按绑定规则自动解析</option>' + topologies.map((item) => `<option value="${esc(item.topology_id)}">${esc(item.name || item.topology_id)}</option>`).join("");
      } catch (_error) {
        topologySelect.innerHTML = '<option value="">按绑定规则自动解析</option>';
      }
    }

    const selectedVersion=()=>options.versions.find(item=>String(item.id)===String(form.version_id.value))||{};
    const previewCard=(icon,label,value,detail="")=>`<div class="preview-card"><img src="/static/project_ui/svg/${icon}.svg" alt=""><div><span>${esc(label)}</span><strong>${esc(value||"未配置")}</strong>${detail?`<small>${esc(detail)}</small>`:""}</div></div>`;
    const renderPlanPreview=()=>{
      const version=selectedVersion();
      document.getElementById("buildPlanPreview").innerHTML=[
        previewCard("nav_build_artifact","Jenkins 实例",version.jenkins_instance_id||form.jenkins_instance_id.value),
        previewCard("nav_execute","构建任务",version.jenkins_job_id||version.jenkins_job||form.jenkins_job.value),
        previewCard("nav_download_center","资源与配置",version.resource_url||version.resource_path||version.config_url||version.config_path?"已登记":"尚未登记"),
        previewCard("file_android","APK 产物",version.apk_url||version.apk_path?"已登记":"尚未登记")
      ].join("");
      if(!form.jenkins_instance_id.value&&version.jenkins_instance_id)form.jenkins_instance_id.value=version.jenkins_instance_id;
      if(!form.jenkins_job.value&&(version.jenkins_job||version.jenkins_job_id))form.jenkins_job.value=version.jenkins_job||version.jenkins_job_id;
      if(!form.jenkins_params.value&&version.jenkins_params)form.jenkins_params.value=valueText(version.jenkins_params);
      updateCompleteness();
    };
    const renderVersions=()=>{
      const current=form.version_id.value;
      const items=options.versions.filter(x=>x.env_key===form.env_key.value&&x.channel_id===form.channel_id.value&&x.platform===form.platform.value);
      form.version_id.innerHTML=items.length?items.map(x=>`<option value="${esc(x.id)}">${esc(x.version_name)} / ${esc(x.version_code)}</option>`).join(""):'<option value="">当前目标暂无可用 VersionCode</option>';
      if(items.some(x=>String(x.id)===String(current)))form.version_id.value=current;
      renderPlanPreview();
    };
    const updateCompleteness=()=>{
      const required=["env_key","channel_id","platform","version_id","reason","owner","release_window","release_description","validation_plan","rollback_plan"];
      const complete=required.filter(key=>form[key]&&String(form[key].value||"").trim()).length;
      const percent=Math.round(complete/required.length*100);
      document.getElementById("planCompleteness").textContent=`${percent}%`;
      document.getElementById("planCompletenessBar").style.width=`${percent}%`;
      document.getElementById("planCompletenessHint").textContent=percent===100?"计划信息完整，可保存并进入构建。":`还有 ${required.length-complete} 项关键计划信息待补充。`;
    };
    [form.env_key,form.channel_id,form.platform].forEach(x=>x.addEventListener("change",renderVersions));
    form.version_id.addEventListener("change",renderPlanPreview);
    form.addEventListener("input",updateCompleteness);
    page.querySelectorAll("[data-form-step]").forEach(button=>button.addEventListener("click",()=>{
      page.querySelectorAll("[data-form-step]").forEach(item=>item.classList.toggle("active",item===button));
      page.querySelector(`[data-section="${button.dataset.formStep}"]`)?.scrollIntoView({behavior:"smooth",block:"start"});
    }));

    const search=new URLSearchParams(location.search);
    ["env_key","channel_id","platform"].forEach(key=>search.get(key)&&(form[key].value=search.get(key)));
    renderVersions();
    if(orderId){
      const order=await api(`/api/projects/${projectId}/release-orders/${orderId}`);
      ["env_key","channel_id","platform"].forEach(key=>form[key].value=order[key]);
      renderVersions();
      form.version_id.value=order.version_id;
      form.reason.value=order.reason||"";
      Object.entries(order.payload||{}).forEach(([key,value])=>{if(form[key])form[key].value=valueText(value);});
      if(form.target_topology_id&&order.payload?.target_topology_id)form.target_topology_id.value=order.payload.target_topology_id;
      document.getElementById("resolvedTopology").textContent=order.topology_id||"尚未解析";
      document.getElementById("resolvedRuntime").textContent=order.runtime_run_id||"预检后确认";
      [form.env_key,form.channel_id,form.platform,form.version_id].forEach(x=>x.disabled=true);
      renderPlanPreview();
    }
    updateCompleteness();
    const payload=()=>Object.fromEntries(new FormData(form).entries());
    const save=async(buildAfter=false)=>{
      try{
        if(!form.reportValidity())return;
        page.querySelectorAll("[data-save-order],[data-save-build]").forEach(button=>button.disabled=true);
        let order;
        if(orderId)order=await api(`/api/projects/${projectId}/release-orders/${orderId}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
        else order=await api(`/api/projects/${projectId}/release-orders`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
        document.getElementById("orderSaveStatus").textContent="草稿已保存";
        toast("发布单计划已保存");
        const context=`?env_key=${encodeURIComponent(order.env_key)}&channel_id=${encodeURIComponent(order.channel_id)}&platform=${encodeURIComponent(order.platform)}&version_name=${encodeURIComponent(order.version_name)}&version_code=${encodeURIComponent(order.version_code)}&release_order_id=${encodeURIComponent(order.release_order_id)}`;
        if(buildAfter){
          await api(`/api/projects/${projectId}/release-orders/${order.release_order_id}/build`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
          location.href=`/admin/projects/${projectId}/release-orders/${order.release_order_id}${context}`;
        }else if(!orderId)location.href=`/admin/projects/${projectId}/release-orders/${order.release_order_id}/edit${context}`;
      }catch(error){toast(error.message,"error");}
      finally{page.querySelectorAll("[data-save-order],[data-save-build]").forEach(button=>button.disabled=false);}
    };
    page.querySelector("[data-save-order]").addEventListener("click",()=>save(false));
    page.querySelector("[data-save-build]").addEventListener("click",()=>save(true));
  }

  async function loadOrderDetail(){
    const orderId=page.dataset.orderId,item=await api(`/api/projects/${projectId}/release-orders/${orderId}`);
    document.getElementById("orderTitle").innerHTML=`发布单详情 ${status(item.status)}`;document.getElementById("orderSubtitle").textContent=`发布单编号：${item.release_order_id}`;
    const actions=[["edit","编辑计划"],["build","触发构建"],["precheck","执行预检"],["approve","审批通过"],["publish","执行发布"],["verify","执行验证"],["rollback","回滚"],["cancel","取消发布单"]];
    const allowed={edit:["draft","artifacts_ready","precheck_failed"].includes(item.status),build:!["published","verified","rolled_back","cancelled"].includes(item.status),precheck:["draft","artifacts_ready","precheck_failed","ready"].includes(item.status),approve:item.status==="awaiting_approval",publish:["ready","approved"].includes(item.status),verify:["published","verify_failed"].includes(item.status),rollback:Boolean(item.bundle_id&&item.active_bundle_id&&item.bundle_id!==item.active_bundle_id),cancel:!["published","verified","rolled_back","cancelled"].includes(item.status)};
    document.getElementById("orderActions").innerHTML=actions.filter(([key])=>allowed[key]).map(([key,label])=>key==="edit"?`<a class="ui-secondary" href="/admin/projects/${projectId}/release-orders/${orderId}/edit${currentContext()}">${label}</a>`:`<button class="${["publish","verify"].includes(key)?"ui-primary":"ui-secondary"}" data-action="${key}">${label}</button>`).join("");
    document.getElementById("orderMeta").innerHTML=[["目标环境",envLabels[item.env_key]],["版本",`${item.version_name} / ${item.version_code}`],["渠道与平台",`${item.channel_name} / ${item.platform}`],["负责人",item.created_by],["总体状态",statusLabels[item.status]]].map(([label,value])=>`<div class="meta-item"><span>${label}</span><strong>${esc(value)}</strong></div>`).join("");
    const stages=["计划摘要","构建与产物","拓扑与运行态","预检结果","审批","发布执行","验证结果","Bundle 与回滚"];const index={draft:0,building:1,artifacts_ready:1,prechecking:3,precheck_failed:3,ready:3,awaiting_approval:4,approved:4,publishing:5,published:5,verifying:6,verified:7,verify_failed:6,rolled_back:7,cancelled:0}[item.status]??0;document.getElementById("orderSteps").innerHTML=stages.map((label,i)=>`<div class="delivery-step ${i<=index?"active":""} ${i===index&&item.status.includes("failed")?"failed":""}"><b>${i+1}</b>${label}</div>`).join("");
    const check=item.latest_precheck||{},payload=check.payload||{};const artifactProblems=(item.artifacts||[]).filter(x=>["missing","unreachable","invalid"].includes(String(x.status||"").toLowerCase())).map(x=>`${x.artifact_type} ${artifactStatusLabels[x.status]||x.status}`);const problems=[...artifactProblems,...(payload.missing_client_fields||[]),...(payload.missing_profile_fields||[]),...(payload.missing_artifact_fields||[])];payload.runtime_error&&problems.push(payload.runtime_error);document.getElementById("orderAlerts").innerHTML=problems.length?`<div class="alert-card danger"><strong>阻断问题（${problems.length}）</strong><p>${esc(problems.join("；"))}</p></div>`:'<div class="alert-card warning"><strong>下一步建议</strong><p>按发布单当前状态执行下一项交付动作。</p></div>';
    document.getElementById("orderArtifacts").innerHTML=(item.artifacts||[]).map(x=>row(artifactTypeLabels[x.artifact_type]||x.artifact_type,x.artifact_url||x.artifact_path,artifactStatusLabels[x.status]||x.status)).join("")||'<div class="ui-empty">暂无产物</div>';
    document.getElementById("orderRuntime").innerHTML=row("拓扑",item.topology_id,bindingSourceLabels[item.topology_binding_source]||item.topology_binding_source)+row("Runtime",item.runtime_run_id,item.runtime_run_id?"运行中":"未运行");
    document.getElementById("orderPrecheck").innerHTML=check.created_at?row(check.ok?"预检通过":"预检阻断",check.created_at,check.ok?"通过":"失败"):'<div class="ui-empty">尚未执行预检</div>';
    document.getElementById("orderApprovals").innerHTML=(item.approvals||[]).map(x=>row(x.status,x.approved_by||x.requested_by,x.note)).join("")||'<div class="ui-empty">暂无审批记录</div>';
    document.getElementById("orderExecution").innerHTML=row("发布时间",item.published_at,statusLabels[item.status]||item.status)+row("验证状态",statusLabels[item.status],statusLabels[item.status]||item.status);
    document.getElementById("orderBundle").innerHTML=row("Bundle",item.bundle_id,item.bundle_id?"已生成":"未生成")+row("Active Bundle",item.active_bundle_id,item.bundle_id===item.active_bundle_id&&item.bundle_id?"当前生效":"");
    document.getElementById("orderEvents").innerHTML=(item.events||[]).map(x=>`<div class="timeline-row"><strong>${esc(x.event_type)} · ${esc(statusLabels[x.to_status]||x.to_status||"")}</strong><span>${esc(x.actor)} · ${esc(x.created_at)}</span></div>`).join("");
    const dialog=document.getElementById("orderActionDialog"),reason=document.getElementById("orderActionReason");let pendingAction="";
    const closeDialog=()=>{pendingAction="";reason.value="";dialog.classList.add("is-hidden");dialog.setAttribute("aria-hidden","true");};
    const executeAction=async(action,operationReason="")=>{try{await api(`/api/projects/${projectId}/release-orders/${orderId}/${action}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reason:operationReason})});toast("操作已提交");loadOrderDetail();}catch(error){toast(error.message,"error");}};
    document.getElementById("orderActionDialogClose").onclick=closeDialog;document.getElementById("orderActionDialogCancel").onclick=closeDialog;
    document.getElementById("orderActionDialogConfirm").onclick=async()=>{const action=pendingAction,operationReason=reason.value.trim();if(["publish","rollback","cancel"].includes(action)&&!operationReason){toast("请填写操作原因","error");return;}closeDialog();await executeAction(action,operationReason);};
    document.querySelectorAll("[data-action]").forEach(button=>button.addEventListener("click",async()=>{const action=button.dataset.action;if(["build","precheck","verify"].includes(action)){await executeAction(action);return;}pendingAction=action;document.getElementById("orderActionDialogTitle").textContent=`确认${button.textContent}`;document.getElementById("orderActionDialogHint").textContent=["publish","rollback","cancel"].includes(action)?"该操作会改变发布状态，请填写原因后确认。":"请确认本次操作影响范围。";dialog.classList.remove("is-hidden");dialog.setAttribute("aria-hidden","false");}));
  }
  const type=page.dataset.deliveryPage;
  if(type==="overview"){
    initOverviewTabs();
    bindOverviewFilters();
    bindProjectEnvAdd();
    loadOverview().catch(error=>toast(error.message,"error"));
    page.querySelector("[data-refresh-overview]")?.addEventListener("click",()=>loadOverview().catch(error=>toast(error.message,"error")));
  }
  if(type==="environment"){loadEnvironmentDetail().catch(error=>toast(error.message,"error"));page.querySelector("[data-refresh-env]")?.addEventListener("click",loadEnvironmentDetail);}
  if(type==="orders")setupOrders().catch(error=>toast(error.message,"error"));
  if(type==="order-form")setupOrderForm().catch(error=>toast(error.message,"error"));
  if(type==="order-detail")loadOrderDetail().catch(error=>toast(error.message,"error"));
})();
