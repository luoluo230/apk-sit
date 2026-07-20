(() => {
  const statusLabels = {
    draft: "草稿",
    building: "构建中",
    build_failed: "构建失败",
    artifacts_ready: "产物就绪",
    prechecking: "预检中",
    precheck_failed: "预检失败",
    ready: "待发布",
    awaiting_approval: "待审批",
    approved: "待发布",
    publishing: "发布中",
    published: "已发布",
    publish_failed: "发布失败",
    verifying: "验证中",
    verified: "验证通过",
    verify_failed: "验证失败",
    rolled_back: "已回滚",
    cancelled: "已取消",
  };

  const releaseLabel = (value) => {
    if (window.PmDisplayLabels && window.PmDisplayLabels.releaseStatus) {
      return window.PmDisplayLabels.releaseStatus(value).label;
    }
    return statusLabels[value] || value || "未配置";
  };

  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const parseApiError = (result, fallback) => {
    if (!result || typeof result !== "object") return fallback;
    const err = result.error;
    if (typeof err === "string" && err) return err;
    if (err && typeof err === "object") return err.message || err.text || fallback;
    return result.error_text || result.error_legacy || fallback;
  };

  const parseJsonResponse = async (response) => {
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      const text = await response.text();
      if (response.status === 401 || text.trim().startsWith("<")) {
        throw new Error(response.status >= 500 ? `服务异常 (${response.status})，请刷新后重试` : "会话已过期，请重新登录后重试");
      }
      throw new Error(`请求失败 (${response.status})`);
    }
    return response.json();
  };

  const api = async (path, options = {}) => {
    const response = await fetch(path, { ...options, credentials: "same-origin" });
    const result = await parseJsonResponse(response);
    if (!response.ok || result.ok === false) {
      throw new Error(parseApiError(result, "请求失败"));
    }
    return result.data;
  };

  const toast = (message, type = "success") => {
    if (window.DeliveryScopeToast) {
      window.DeliveryScopeToast(message, type);
      return;
    }
    let host = document.querySelector(".toast-stack");
    if (!host) {
      host = document.createElement("div");
      host.className = "toast-stack";
      document.body.append(host);
    }
    const node = document.createElement("div");
    node.className = `toast ${type}`;
    node.textContent = message;
    host.append(node);
    setTimeout(() => node.remove(), 3500);
  };

  const status = (value) => `<span class="status-pill ${esc(value)}">${esc(releaseLabel(value))}</span>`;

  window.DeliveryCommon = {
    statusLabels,
    releaseLabel,
    esc,
    parseApiError,
    parseJsonResponse,
    api,
    toast,
    status,
  };
})();
