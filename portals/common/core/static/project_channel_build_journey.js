(() => {
  const JC = window.JourneyCommon || {};
  const esc = JC.esc || ((v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])));
  const page = document.querySelector('[data-journey="build"]');
  if (!page) return;

  const projectId = page.dataset.projectId || "";
  const envKey = page.dataset.envKey || "";
  const channelId = page.dataset.channelId || "";
  const params = new URLSearchParams(location.search);
  let platform = params.get("platform") || "";
  let versionId = params.get("version_id") || "";
  let pollTimer = null;
  let buildEventSource = null;
  let buildEventsEtag = "";
  let latestBuild = null;
  let journeyLinks = {};

  const toast = JC.toast || ((msg, type = "info") => {
    if (window.DeliveryScopeToast) window.DeliveryScopeToast(msg, type);
    else alert(msg);
  });

  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || "";

  const api = JC.api || (async (url, options = {}) => {
    const resp = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || data.ok === false) throw new Error(data.error || `请求失败 (${resp.status})`);
    return data.data ?? data;
  });

  const dateText = (value) => (value ? String(value).replace("T", " ").slice(0, 19) : "—");

  const syncUrl = JC.syncUrl || (() => {
    const qs = new URLSearchParams({ env_key: envKey, channel_id: channelId });
    if (platform) qs.set("platform", platform);
    if (versionId) qs.set("version_id", versionId);
    history.replaceState(null, "", `${location.pathname}?${qs}`);
  });

  const statusKey = (item) => (item?.building ? "building" : String(item?.result || "UNKNOWN").toUpperCase());
  const statusText = (item) => ({
    building: "构建中",
    SUCCESS: "成功",
    FAILURE: "失败",
    ABORTED: "已取消",
    UNSTABLE: "部分成功",
    UNKNOWN: "未知",
    "": "未知",
  }[statusKey(item)] || statusKey(item));
  const statusBadgeClass = (item) => ({
    building: "live",
    SUCCESS: "ready",
    FAILURE: "pending",
    ABORTED: "pending",
    UNSTABLE: "live",
    UNKNOWN: "pending",
    "": "pending",
  }[statusKey(item)] || "pending");
  const statusBadge = (item) => `<span class="cj-badge ${statusBadgeClass(item)}">${esc(statusText(item))}</span>`;

  const chip = JC.chip || ((label, value, ready = true) =>
    `<span class="cj-context-chip ${ready ? "is-ready" : "is-pending"}">${label} <strong>${esc(value)}</strong></span>`);

  const renderContext = (data, state) => {
    const host = document.getElementById("cjBuildContext");
    if (!host) return;
    const vc = state.version_name ? `${state.version_name} / ${state.version_code}` : versionId ? "已选 VC" : "待选";
    host.innerHTML = [
      chip("环境", data.env_label || envKey, true),
      chip("渠道", data.channel_name || channelId, true),
      chip("平台", platform || "待选", Boolean(platform)),
      chip("VersionCode", vc, Boolean(state.version_name || versionId)),
    ].join("");
  };

  const panel = JC.panel || ((title, desc, bodyHtml, actionsHtml = "", tone = "ready") => {
    const actionBlock = actionsHtml ? `<div class="cj-actions">${actionsHtml}</div>` : "";
    return `<div class="cj-main-inner is-${tone}${actionsHtml ? " has-actions" : ""}">
      <div class="cj-main-copy">
        <div class="cj-panel-head"><div><h3>${title}</h3><p>${desc}</p></div></div>
        <div class="cj-panel-body">${bodyHtml}</div>
      </div>
      ${actionBlock}
    </div>`;
  });

  const summaryGrid = (rows) => {
    const items = rows.filter((r) => r).map(([k, v, tone]) => {
      const cls = tone === "pending" ? " is-pending" : tone === "ready" ? " is-ready" : "";
      return `<div class="cj-kv${cls}"><dt>${esc(k)}</dt><dd>${v}</dd></div>`;
    }).join("");
    return items ? `<dl class="cj-kv-grid">${items}</dl>` : "";
  };

  const buildVersionGroups = (versions) => {
    const groups = new Map();
    (versions || []).forEach((v) => {
      const name = String(v.version_name || "未命名").trim() || "未命名";
      if (!groups.has(name)) groups.set(name, []);
      groups.get(name).push(v);
    });
    return groups;
  };

  const resolveSelectedGroupName = (groups, vid, state) => {
    if (vid) {
      for (const [name, items] of groups) {
        if (items.some((row) => row.version_id === vid)) return name;
      }
    }
    const fromState = String(state.version_name || "").trim();
    if (fromState && groups.has(fromState)) return fromState;
    return groups.keys().next().value || "";
  };

  const renderVersionPicker = (state, links) => {
    const host = document.getElementById("cjBuildVersionPicker");
    if (!host) return;
    const groups = buildVersionGroups(state.versions || []);
    if (!groups.size) {
      host.innerHTML = `<div class="cj-version-picker is-empty"><span class="cj-empty-hint">暂无 VersionCode，请先在版本页创建。</span><a class="cj-btn neutral" href="${esc(links?.versions || "#")}">去版本页</a></div>`;
      return;
    }
    const groupNames = [...groups.keys()];
    const selectedGroup = resolveSelectedGroupName(groups, versionId, state) || groupNames[0];
    const vcList = groups.get(selectedGroup) || [];
    const selectedVc = (versionId && vcList.find((row) => row.version_id === versionId)) || vcList[0];
    const groupOptions = groupNames.map((name) =>
      `<option value="${esc(name)}"${name === selectedGroup ? " selected" : ""}>${esc(name)}</option>`,
    ).join("");
    const vcOptions = vcList.map((row) => {
      const label = `${row.version_name} / ${row.version_code}`;
      const status = row.apk_status || row.release_order_status || "";
      return `<option value="${esc(row.version_id)}"${row.version_id === selectedVc?.version_id ? " selected" : ""}>${esc(label)}${status ? ` · ${esc(status)}` : ""}</option>`;
    }).join("");
    host.innerHTML = `<div class="cj-version-picker">
      <label class="cj-select-field"><span>版本组</span><select id="cjVersionGroupSelect">${groupOptions}</select></label>
      <label class="cj-select-field"><span>VersionCode</span><select id="cjVersionCodeSelect">${vcOptions}</select></label>
      <a class="cj-btn neutral cj-picker-link" href="${esc(links?.versions || "#")}">管理版本</a>
    </div>`;
  };

  const bindVersionPicker = (state) => {
    const groupSelect = document.getElementById("cjVersionGroupSelect");
    const vcSelect = document.getElementById("cjVersionCodeSelect");
    if (!groupSelect || !vcSelect) return;
    groupSelect.onchange = () => {
      const groups = buildVersionGroups(state.versions || []);
      const items = groups.get(groupSelect.value) || [];
      versionId = items[0]?.version_id || "";
      syncUrl();
      load();
    };
    vcSelect.onchange = () => {
      versionId = vcSelect.value || "";
      syncUrl();
      load();
    };
  };

  const ensureDefaultVersionId = (state) => {
    const rows = state.versions || [];
    if (!rows.length) return false;
    if (versionId && rows.some((row) => row.version_id === versionId)) return false;
    versionId = rows[0].version_id;
    syncUrl();
    return true;
  };

  const mergeSelectedVersionState = (state) => {
    if (!versionId) return state;
    const selected = (state.versions || []).find((row) => row.version_id === versionId);
    if (!selected) return { ...state, version_id: versionId };
    return {
      ...state,
      version_id: versionId,
      version_name: selected.version_name || state.version_name,
      version_code: selected.version_code || state.version_code,
      release_order_id: selected.release_order_id || state.release_order_id,
      order_status: selected.release_order_status || state.order_status,
      artifact_ready: selected.artifacts_ready || state.artifact_ready,
    };
  };

  const renderPlatforms = (host, platforms, active) => {
    if (!host) return;
    host.innerHTML = platforms.map((p) => {
      const cls = p.value === active ? "cj-platform-tab active" : "cj-platform-tab";
      return `<button type="button" class="${cls}" data-platform="${esc(p.value)}">${esc(p.label)}</button>`;
    }).join("");
    host.querySelectorAll("[data-platform]").forEach((btn) => {
      btn.onclick = () => {
        platform = btn.getAttribute("data-platform") || "";
        versionId = "";
        syncUrl();
        load();
      };
    });
  };

  const buildRecordHref = (build, links) => {
    const base = links?.build_history || `/admin/projects/${encodeURIComponent(projectId)}/build-history`;
    try {
      const url = new URL(base, location.origin);
      if (build?.build_number) url.searchParams.set("build_number", String(build.build_number));
      if (versionId) url.searchParams.set("version_id", versionId);
      url.searchParams.set("scoped", "1");
      return `${url.pathname}${url.search}`;
    } catch {
      return base;
    }
  };

  const activityKvGrid = (build) => {
    const num = build.build_number || build.number;
    return `<dl class="cj-activity-kv">
      <div class="cj-kv"><dt>构建号</dt><dd>#${esc(num)}</dd></div>
      <div class="cj-kv"><dt>状态</dt><dd>${statusBadge(build)}</dd></div>
      <div class="cj-kv"><dt>Jenkins 实例</dt><dd>${esc(build.instance_id || "—")}</dd></div>
      <div class="cj-kv"><dt>触发人</dt><dd>${esc(build.triggered_by || "—")}</dd></div>
      <div class="cj-kv"><dt>开始时间</dt><dd>${esc(dateText(build.started_at))}</dd></div>
      <div class="cj-kv"><dt>耗时</dt><dd>${esc(build.duration || (build.building ? "进行中" : "—"))}</dd></div>
      ${build.ended_at ? `<div class="cj-kv"><dt>结束时间</dt><dd>${esc(dateText(build.ended_at))}</dd></div>` : ""}
    </dl>`;
  };

  const renderBuildActivity = (build, links, state) => {
    const host = document.getElementById("cjBuildActivity");
    const inner = document.getElementById("cjBuildActivityInner");
    if (!host || !inner) return;

    if (!versionId || !platform) {
      host.hidden = true;
      return;
    }
    host.hidden = false;

    if (!build) {
      inner.innerHTML = `<div class="cj-activity-inner is-empty">
        <div class="cj-activity-head"><div><h2>构建活动</h2><p>当前 VersionCode 暂无构建记录，触发构建后将在此显示进度与日志入口。</p></div></div>
      </div>`;
      return;
    }

    const num = build.build_number || build.number;
    const progress = Number.isFinite(Number(build.progress_pct))
      ? Math.max(0, Math.min(100, Number(build.progress_pct)))
      : (build.building ? 55 : (statusKey(build) === "SUCCESS" ? 100 : 38));
    const recordHref = buildRecordHref(build, links);
    const consoleUrl = String(build.console_url || "").trim();
    const failureBlock = statusKey(build) === "FAILURE" && build.failure_summary
      ? `<div class="cj-activity-failure"><strong>失败摘要</strong><pre>${esc(build.failure_summary)}</pre></div>`
      : "";

    if (build.building) {
      inner.innerHTML = `<div class="cj-activity-inner is-building">
        <div class="cj-activity-head">
          <div>
            <h2>构建进行中</h2>
            <p>Jenkins 正在构建 #${esc(num)}，可打开控制台查看实时日志或停止构建。</p>
          </div>
          ${statusBadge(build)}
        </div>
        <div class="cj-activity-progress" aria-hidden="true"><span style="width:${progress}%"></span></div>
        ${activityKvGrid(build)}
        ${failureBlock}
        <div class="cj-activity-actions">
          <button type="button" class="cj-btn warn" id="cjStopBuild">停止构建</button>
          ${consoleUrl ? `<a class="cj-btn build" href="${esc(consoleUrl)}" target="_blank" rel="noopener">打开控制台</a>` : `<button type="button" class="cj-btn build" disabled>控制台不可用</button>`}
          <button type="button" class="cj-btn neutral" id="cjRefreshActivity">刷新进度</button>
          <a class="cj-btn neutral" href="${esc(recordHref)}">构建与产物</a>
        </div>
      </div>`;
      return;
    }

    inner.innerHTML = `<div class="cj-activity-inner is-history">
      <div class="cj-activity-head">
        <div>
          <h2>最近构建</h2>
          <p>当前 VersionCode 最近一次构建详情，可跳转至构建与产物页查看完整记录。</p>
        </div>
        ${statusBadge(build)}
      </div>
      <div class="cj-activity-progress is-done" aria-hidden="true"><span style="width:${progress}%"></span></div>
      ${activityKvGrid(build)}
      ${failureBlock}
      <div class="cj-activity-actions">
        <a class="cj-btn build" href="${esc(recordHref)}">查看构建记录</a>
        ${consoleUrl ? `<a class="cj-btn neutral" href="${esc(consoleUrl)}" target="_blank" rel="noopener">打开控制台</a>` : `<button type="button" class="cj-btn neutral" disabled>控制台不可用</button>`}
        <a class="cj-btn neutral" href="${esc(links?.build_history || recordHref)}">全部构建记录</a>
        <button type="button" class="cj-btn neutral" id="cjRefreshActivity">刷新</button>
      </div>
    </div>`;
  };

  const bindActivityActions = () => {
    document.getElementById("cjRefreshActivity")?.addEventListener("click", () => load(true));
    document.getElementById("cjStopBuild")?.addEventListener("click", async (event) => {
      const btn = event.currentTarget;
      const build = latestBuild;
      if (!build) return;
      const num = build.build_number || build.number;
      if (!num) return toast("缺少构建号", "error");
      if (!window.confirm(`确认停止构建 #${num}？`)) return;
      try {
        btn.disabled = true;
        const qs = build.instance_id ? `?instance_id=${encodeURIComponent(build.instance_id)}` : "";
        const resp = await fetch(`/api/build/${encodeURIComponent(num)}/stop${qs}`, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
          body: JSON.stringify({ instance_id: build.instance_id || "" }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || data.success === false) throw new Error(data.error || "停止构建失败");
        toast("已请求停止构建");
        load(true);
      } catch (e) {
        toast(e.message, "error");
      } finally {
        btn.disabled = false;
      }
    });
  };

  const fetchBuildActivity = async (vid, fallbackBuild = null) => {
    const qs = new URLSearchParams({ version_id: vid, platform: platform || "" });
    const headers = {};
    if (buildEventsEtag) headers["If-None-Match"] = buildEventsEtag;
    const resp = await fetch(`/api/projects/${encodeURIComponent(projectId)}/build-events?${qs}`, {
      credentials: "same-origin",
      headers,
    });
    if (resp.status === 304) return latestBuild || fallbackBuild || null;
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || data.ok === false) throw new Error(data.error || "构建活动加载失败");
    const etag = resp.headers.get("ETag");
    if (etag) buildEventsEtag = etag;
    const build = data.data?.build || null;
    return build || fallbackBuild || null;
  };

  const stopBuildEventStream = () => {
    if (buildEventSource) {
      buildEventSource.close();
      buildEventSource = null;
    }
  };

  const applyBuildSnapshot = (snapshot, state, links) => {
    if (!snapshot || typeof snapshot !== "object") return;
    latestBuild = snapshot.build || latestBuild;
    if (snapshot.order_status && state) state.order_status = snapshot.order_status;
    renderBuildActivity(latestBuild, links || journeyLinks, state || {});
    bindActivityActions();
  };

  const startBuildEventStream = (vid, state, links) => {
    stopBuildEventStream();
    if (!vid || typeof EventSource === "undefined") return false;
    const qs = new URLSearchParams({ version_id: vid, platform: platform || "" });
    const es = new EventSource(`/api/projects/${encodeURIComponent(projectId)}/build-events/stream?${qs}`);
    buildEventSource = es;
    es.addEventListener("build", (event) => {
      try {
        const snapshot = JSON.parse(event.data || "{}");
        applyBuildSnapshot(snapshot, state, links);
        if (!snapshot.building) stopBuildEventStream();
      } catch (_e) { /* ignore malformed SSE payload */ }
    });
    es.addEventListener("done", () => {
      stopBuildEventStream();
      load(true);
    });
    es.onerror = () => {
      stopBuildEventStream();
    };
    return true;
  };

  const selectedVersionRow = (state) => (state.versions || []).find((row) => row.version_id === versionId) || null;

  const orderBuildFromResponse = (result, vid) => {
    const payload = result?.payload || {};
    const bnRaw = String(payload.build_job_id || "").trim();
    const iid = String(payload.jenkins_instance_id || "").trim();
    if (!bnRaw.match(/^\d+$/) || !iid) return null;
    return {
      build_number: Number(bnRaw),
      number: Number(bnRaw),
      instance_id: iid,
      version_id: vid,
      project_id: projectId,
      building: String(result?.status || "") === "building",
      status_label: String(result?.status || "") === "building" ? "构建中" : "未知",
      triggered_by: result?.created_by || "",
      started_at: result?.updated_at || result?.created_at || "",
      console_url: "",
    };
  };

  const renderWorkspace = (data, state) => {
    const links = data.links || {};
    const vc = state.version_name && state.version_code ? `${state.version_name} / ${state.version_code}` : "未选择";
    const status = String(state.order_status || "");
    const isBuilding = Boolean(latestBuild?.building) || status === "building";
    const isBuildFailed = status === "build_failed" || statusKey(latestBuild) === "FAILURE";
    const artifactHref = latestBuild ? buildRecordHref(latestBuild, links) : (links.build_history || "#");
    const rows = [
      ["版本组", esc(state.version_name || "—"), state.version_name ? "ready" : "pending"],
      ["VersionCode", esc(vc), versionId ? "ready" : "pending"],
      ["管线", state.pipeline_ready ? '<span class="cj-badge ready">已就绪</span>' : '<span class="cj-badge pending">未配置</span>', state.pipeline_ready ? "ready" : "pending"],
      ["构建状态", esc(isBuilding ? "building" : (isBuildFailed ? "build_failed" : (status || "待触发"))), isBuilding ? "pending" : isBuildFailed ? "pending" : state.artifact_ready ? "ready" : "pending"],
      ["发布单", esc(state.release_order_id || "—")],
    ];

    if (!platform) {
      return panel("选择平台", "请在右上角切换 Android / iOS 平台。", summaryGrid(rows.slice(0, 3)), "", "pending");
    }
    if (!state.pipeline_ready) {
      return panel(
        "管线未配置",
        "请先在版本组层级完成 Jenkins 管线配置，再触发构建。",
        summaryGrid(rows),
        `<a class="cj-btn build" href="${esc(state.build_config_href || links.versions || "#")}">配置管线</a>
        <a class="cj-btn neutral" href="${esc(links.versions || "#")}">管理版本</a>`,
        "pending",
      );
    }
    if (!versionId) {
      return panel("请选择 VersionCode", "在上方选择版本组与 VersionCode 后再触发构建。", summaryGrid(rows), `<a class="cj-btn neutral" href="${esc(links.versions || "#")}">管理版本</a>`, "pending");
    }
    if (isBuildFailed && !isBuilding) {
      return panel(
        "构建失败",
        "Jenkins 构建未成功，请查看失败摘要后重新触发构建。",
        summaryGrid([...rows, ["失败摘要", esc(latestBuild?.failure_summary || "—"), "pending"]]),
        `<button type="button" class="cj-btn build" id="cjRebuildBuild">重新构建</button>
        <a class="cj-btn neutral" href="${esc(artifactHref)}">查看构建记录</a>`,
        "pending",
      );
    }
    if (isBuilding) {
      return panel(
        "构建已触发",
        "Jenkins 正在执行，进度与控制台入口见上方「构建活动」区域。",
        summaryGrid(rows),
        `<button type="button" class="cj-btn neutral" id="cjRefreshBuild">刷新状态</button>`,
        "pending",
      );
    }
    if (state.artifact_ready || status === "artifacts_ready") {
      return panel(
        "产物就绪",
        "构建已完成，可查看产物或重新构建。发版请从环境详情平台卡「发版」入口进入。",
        summaryGrid([...rows, ["产物", '<span class="cj-badge ready">产物就绪</span>', "ready"]]),
        `<a class="cj-btn neutral" href="${esc(artifactHref)}">查看产物</a>
        <button type="button" class="cj-btn build" id="cjRebuildBuild">重新构建</button>`,
        "ready",
      );
    }
    return panel(
      "待触发构建",
      "已选定 VersionCode，确认后可触发 Jenkins 构建。",
      summaryGrid(rows),
      `<button type="button" class="cj-btn build" id="cjTriggerBuild">触发构建</button>
      <button type="button" class="cj-btn build" id="cjRebuildBuild">重新构建</button>`,
      "pending",
    );
  };

  const bindPanelActions = (state) => {
    const selected = selectedVersionRow(state);
    const orderIdForSelected = selected?.release_order_id || state.release_order_id;
    document.getElementById("cjTriggerBuild")?.addEventListener("click", async (event) => {
      const btn = event.currentTarget;
      const vid = versionId || state.version_id;
      if (!vid) return toast("请先选择 VersionCode", "error");
      try {
        btn.disabled = true;
        const result = await api(`/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(vid)}/quick-build`, { method: "POST", body: "{}" });
        if (String(result?.status || "") === "building") {
          latestBuild = orderBuildFromResponse(result, vid) || latestBuild;
          toast("构建已触发");
        } else if (String(result?.status || "") === "artifacts_ready") {
          toast("当前 VersionCode 产物已就绪，请使用「重新构建」", "error");
        } else {
          toast("构建已触发");
        }
        load(true);
      } catch (e) {
        toast(e.message, "error");
      } finally {
        btn.disabled = false;
      }
    });
    document.getElementById("cjRebuildBuild")?.addEventListener("click", async (event) => {
      const btn = event.currentTarget;
      const vid = versionId || state.version_id;
      const oid = orderIdForSelected;
      try {
        btn.disabled = true;
        let result = null;
        if (oid) {
          result = await api(`/api/projects/${encodeURIComponent(projectId)}/release-orders/${encodeURIComponent(oid)}/build`, { method: "POST", body: "{}" });
        } else if (vid) {
          result = await api(`/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(vid)}/quick-build`, { method: "POST", body: "{}" });
        } else {
          throw new Error("缺少 VersionCode");
        }
        latestBuild = orderBuildFromResponse(result, vid) || latestBuild;
        toast("重新构建已触发");
        load(true);
      } catch (e) {
        toast(e.message, "error");
      } finally {
        btn.disabled = false;
      }
    });
    document.getElementById("cjRefreshBuild")?.addEventListener("click", () => load(true));
  };

  const shouldPoll = (state) => Boolean(latestBuild?.building) || state.order_status === "building";

  const load = async (polling = false) => {
    const main = document.getElementById("cjBuildMain");
    try {
      const qs = new URLSearchParams();
      if (platform) qs.set("platform", platform);
      if (versionId) qs.set("version_id", versionId);
      const data = await api(`/api/projects/${encodeURIComponent(projectId)}/environments/${encodeURIComponent(envKey)}/channels/${encodeURIComponent(channelId)}/build-journey?${qs}`);
      platform = data.platform || platform;
      journeyLinks = data.links || {};
      if (!versionId && data.selected_version_id) versionId = data.selected_version_id;
      let state = (data.per_platform || {})[platform] || {};
      if (ensureDefaultVersionId(state)) return load(polling);
      state = mergeSelectedVersionState(state);

      if (versionId && platform) {
        try {
          latestBuild = await fetchBuildActivity(versionId, state.latest_build || null);
        } catch (e) {
          latestBuild = state.latest_build || null;
          if (!polling) toast(e.message, "error");
        }
      } else {
        latestBuild = null;
      }

      document.getElementById("cjBuildTitle").textContent = `构建流程 · ${data.channel_name || channelId}`;
      document.getElementById("cjBuildSubtitle").textContent = `${data.env_label || envKey} · ${data.channel_name || channelId}`;
      renderPlatforms(document.getElementById("cjBuildPlatforms"), data.platforms || [], platform);
      renderContext(data, state);
      renderVersionPicker(state, data.links || {});
      bindVersionPicker(state);
      renderBuildActivity(latestBuild, journeyLinks, state);
      bindActivityActions();
      if (main) main.innerHTML = renderWorkspace(data, state);
      bindPanelActions(state);

      if (pollTimer) clearInterval(pollTimer);
      pollTimer = null;
      stopBuildEventStream();
      if (shouldPoll(state) && versionId) {
        if (!startBuildEventStream(versionId, state, journeyLinks)) {
          pollTimer = setInterval(() => load(true), 3000);
        }
      }
    } catch (e) {
      if (main) main.innerHTML = `<div class="ui-empty">${esc(e.message)}</div>`;
    }
  };

  load();
})();
