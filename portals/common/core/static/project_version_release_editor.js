(() => {
  "use strict";

  const modal = document.getElementById("versionReleaseModal");
  const form = document.getElementById("versionReleaseForm");
  if (!modal || !form) return;

  const root = document.querySelector(".version-workspace");
  const projectId = root?.dataset.projectId || "";
  let currentRow = null;
  let currentOrderId = "";

  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const csrfHeaders = () => {
    const token = document.querySelector('meta[name="csrf-token"]');
    return token?.content ? { "X-CSRFToken": token.content } : {};
  };

  const request = async (url, options = {}) => {
    const method = String(options.method || "GET").toUpperCase();
    const headers = { "Content-Type": "application/json", ...(options.headers || {}), ...(["POST", "PUT", "PATCH", "DELETE"].includes(method) ? csrfHeaders() : {}) };
    const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || "请求失败");
    return data.data ?? data;
  };

  const toast = (msg, type = "success") => {
    if (typeof window.__versionToast === "function") window.__versionToast(msg, type);
  };

  const setStatus = (text) => {
    const node = document.getElementById("versionReleaseStatus");
    if (node) node.textContent = text || "";
  };

  const activateTab = (tabName) => {
    if (!tabName) return;
    const btn = modal.querySelector(`[data-release-tab="${tabName}"]`);
    if (btn) btn.click();
  };

  const closeModal = () => {
    modal.classList.add("is-hidden");
    modal.setAttribute("aria-hidden", "true");
    currentRow = null;
    currentOrderId = "";
    setStatus("");
  };

  const readPayload = () => {
    const fd = new FormData(form);
    return {
      release_reason_type: fd.get("release_reason_type") || "regular",
      owner: fd.get("owner") || "",
      release_window: fd.get("release_window") || "",
      release_description: fd.get("release_description") || "",
      reason: fd.get("reason") || "",
      release_strategy: fd.get("release_strategy") || "full",
      gray_ratio: fd.get("gray_ratio") || "",
      validation_plan: fd.get("validation_plan") || "",
      rollback_plan: fd.get("rollback_plan") || "",
      target_topology_id: fd.get("target_topology_id") || "",
      min_server_version: fd.get("min_server_version") || "",
      deploy_server_with_client: fd.get("deploy_server_with_client") === "1",
      announcement_title: fd.get("announcement_title") || "",
      announcement_body: fd.get("announcement_body") || "",
      announcement_effective_at: fd.get("announcement_effective_at") || "",
      sync_announcement: fd.get("sync_announcement") === "1",
      server_maintenance_message: fd.get("server_maintenance_message") || "",
    };
  };

  const fillForm = (order, row) => {
    const plan = order?.payload || {};
    const set = (name, val) => {
      const el = form.elements.namedItem(name);
      if (el) el.value = val == null ? "" : String(val);
    };
    set("release_reason_type", plan.release_reason_type || "regular");
    set("owner", plan.owner || order?.created_by || "");
    set("release_window", plan.release_window || "");
    set("release_description", plan.release_description || "");
    set("reason", order?.reason || plan.reason || "");
    set("release_strategy", plan.release_strategy || "full");
    set("gray_ratio", plan.gray_ratio || "");
    set("validation_plan", plan.validation_plan || "");
    set("rollback_plan", plan.rollback_plan || "");
    set("target_topology_id", plan.target_topology_id || "");
    set("min_server_version", plan.min_server_version || "");
    set("announcement_title", plan.announcement_title || "");
    set("announcement_body", plan.announcement_body || "");
    set("announcement_effective_at", plan.announcement_effective_at || "");
    set("server_maintenance_message", plan.server_maintenance_message || "");
    const deploy = form.elements.namedItem("deploy_server_with_client");
    if (deploy) deploy.checked = Boolean(plan.deploy_server_with_client);
    const syncAnn = form.elements.namedItem("sync_announcement");
    if (syncAnn) syncAnn.checked = Boolean(plan.sync_announcement);
    document.getElementById("versionReleaseTitle").textContent = `${row?.version_name || "-"} · VC ${row?.version_code || "-"}`;
    document.getElementById("versionReleaseSubtitle").textContent = [
      row?.env_key || row?.stage || "",
      row?.channel_name || row?.channel_id || "",
      row?.platform || "",
    ].filter(Boolean).join(" · ");
    setStatus(order?.status ? `发布单状态：${order.status}` : "");
  };

  const ensureOrder = async (row) => {
    const existing = row?.release_order_id || "";
    if (existing) {
      return request(`/api/projects/${projectId}/release-orders/${existing}`);
    }
    const payload = {
      env_key: row.env_key || row.stage || "development",
      channel_id: row.channel_id || row.channel || "",
      platform: row.platform || "android",
      version_id: row.id,
      version_code: row.version_code || "",
      reason: "",
      owner: "",
    };
    return request(`/api/projects/${projectId}/release-orders`, { method: "POST", body: JSON.stringify(payload) });
  };

  const openReleaseEditor = async (row, options = {}) => {
    if (!row?.id) return;
    currentRow = row;
    modal.classList.remove("is-hidden");
    modal.setAttribute("aria-hidden", "false");
    setStatus("加载中…");
    try {
      const order = await ensureOrder(row);
      currentOrderId = order.release_order_id || "";
      fillForm(order, row);
      activateTab(options.tab || "");
      setStatus(order.status ? `发布单状态：${order.status}` : "");
    } catch (error) {
      setStatus(error.message || "加载失败");
      toast(error.message || "加载失败", "error");
    }
  };

  const savePlan = async () => {
    if (!currentOrderId) throw new Error("无发布单");
    return request(`/api/projects/${projectId}/release-orders/${currentOrderId}`, {
      method: "PATCH",
      body: JSON.stringify(readPayload()),
    });
  };

  const postAction = async (action, body = {}) => {
    if (!currentOrderId) throw new Error("请先保存并创建发布单");
    return request(`/api/projects/${projectId}/release-orders/${currentOrderId}/${action}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  };

  const runAction = async (action) => {
    await savePlan();
    if (action === "publish" && (currentRow?.env_key === "production" || currentRow?.stage === "production")) {
      if (!window.confirm("确认发布到生产环境？")) return null;
    }
    if (action === "rollback" && !window.confirm("确认回滚该版本？")) return null;
    if (action === "server-maintenance" && !window.confirm("确认将目标服务器切换为维护状态？")) return null;
    return postAction(action, readPayload());
  };

  const runRowAction = async (row, action, options = {}) => {
    currentRow = row;
    const order = await ensureOrder(row);
    currentOrderId = order.release_order_id || "";
    if (options.openModal) {
      await openReleaseEditor(row, { tab: options.tab || "" });
      return null;
    }
    fillForm(order, row);
    if (action === "edit") {
      await openReleaseEditor(row, { tab: options.tab || "" });
      return null;
    }
    if (action === "announce") {
      setStatus("同步公告中…");
      await savePlan();
      const result = await postAction("sync-announcement");
      toast(result?.announcement_sync?.message || "公告已同步");
      return result;
    }
    setStatus(`${action}…`);
    const result = await runAction(action);
    if (result) fillForm(result, currentRow);
    if (typeof window.__versionReload === "function") await window.__versionReload();
    const labels = {
      publish: "发布已提交",
      rollback: "回滚已提交",
      build: "构建已触发",
      precheck: "预检完成",
      "server-maintenance": "服务器已进入维护",
    };
    if (labels[action]) toast(labels[action]);
    return result;
  };

  modal.querySelectorAll("[data-release-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      modal.querySelectorAll("[data-release-tab]").forEach((n) => n.classList.toggle("is-active", n === btn));
      modal.querySelectorAll("[data-release-pane]").forEach((pane) => {
        pane.classList.toggle("is-active", pane.getAttribute("data-release-pane") === btn.getAttribute("data-release-tab"));
      });
    });
  });

  document.getElementById("btnCloseVersionReleaseModal")?.addEventListener("click", closeModal);
  document.getElementById("btnReleaseSave")?.addEventListener("click", async () => {
    try {
      const order = await savePlan();
      fillForm(order, currentRow);
      toast("发版信息已保存");
      if (typeof window.__versionReload === "function") await window.__versionReload();
    } catch (error) {
      toast(error.message || "保存失败", "error");
    }
  });
  document.getElementById("btnReleaseBuild")?.addEventListener("click", async () => {
    try {
      setStatus("构建中…");
      const order = await runAction("build");
      if (order) fillForm(order, currentRow);
      toast("构建已触发");
      if (typeof window.__versionReload === "function") await window.__versionReload();
    } catch (error) {
      toast(error.message || "构建失败", "error");
    }
  });
  document.getElementById("btnReleasePrecheck")?.addEventListener("click", async () => {
    try {
      setStatus("预检中…");
      const order = await runAction("precheck");
      if (order) fillForm(order, currentRow);
      toast("预检完成");
    } catch (error) {
      toast(error.message || "预检失败", "error");
    }
  });
  document.getElementById("btnReleaseAnnounce")?.addEventListener("click", async () => {
    try {
      setStatus("同步公告中…");
      await savePlan();
      const result = await postAction("sync-announcement");
      toast(result?.announcement_sync?.message || "公告已同步");
    } catch (error) {
      toast(error.message || "公告同步失败", "error");
    }
  });
  document.getElementById("btnReleasePublish")?.addEventListener("click", async () => {
    try {
      setStatus("发布中…");
      const order = await runAction("publish");
      if (order) fillForm(order, currentRow);
      toast("发布已提交");
      if (typeof window.__versionReload === "function") await window.__versionReload();
    } catch (error) {
      toast(error.message || "发布失败", "error");
    }
  });
  document.getElementById("btnReleaseServerPause")?.addEventListener("click", async () => {
    try {
      setStatus("暂停服务器中…");
      const result = await runAction("server-maintenance");
      if (result) toast(result.message || "服务器已进入维护");
    } catch (error) {
      toast(error.message || "服务器暂停失败", "error");
    }
  });
  document.getElementById("btnReleaseRollback")?.addEventListener("click", async () => {
    try {
      setStatus("回滚中…");
      const order = await runAction("rollback");
      if (order) fillForm(order, currentRow);
      toast("回滚已提交");
    } catch (error) {
      toast(error.message || "回滚失败", "error");
    }
  });

  window.VersionReleaseEditor = { open: openReleaseEditor, close: closeModal, runRowAction };
})();
