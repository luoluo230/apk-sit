(() => {
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const toast = (msg, type = "info") => {
    if (window.DeliveryScopeToast) window.DeliveryScopeToast(msg, type);
    else if (window.DeliveryCommon && window.DeliveryCommon.toast) window.DeliveryCommon.toast(msg, type);
    else alert(msg);
  };

  const api = async (url, options = {}) => {
    if (window.DeliveryCommon && window.DeliveryCommon.api) {
      return window.DeliveryCommon.api(url, options);
    }
    const resp = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || data.ok === false) throw new Error(data.error || `请求失败 (${resp.status})`);
    return data.data ?? data;
  };

  const chip = (label, value, ready = true) =>
    `<span class="cj-context-chip ${ready ? "is-ready" : "is-pending"}">${label} <strong>${esc(value)}</strong></span>`;

  const panel = (title, desc, bodyHtml, actionsHtml = "", tone = "ready") => {
    const actionBlock = actionsHtml ? `<div class="cj-actions">${actionsHtml}</div>` : "";
    return `<div class="cj-main-inner is-${tone}${actionsHtml ? " has-actions" : ""}">
      <div class="cj-main-copy">
        <div class="cj-panel-head"><div><h3>${title}</h3><p>${desc}</p></div></div>
        <div class="cj-panel-body">${bodyHtml}</div>
      </div>
      ${actionBlock}
    </div>`;
  };

  const summaryGrid = (rows) => {
    const items = (rows || [])
      .filter((r) => r)
      .map(([k, v, tone]) => {
        const cls = tone === "pending" ? " is-pending" : tone === "ready" ? " is-ready" : "";
        return `<div class="cj-kv${cls}"><dt>${esc(k)}</dt><dd>${v}</dd></div>`;
      })
      .join("");
    return items ? `<dl class="cj-kv-grid">${items}</dl>` : "";
  };

  const syncUrl = (pathname, params) => {
    history.replaceState(null, "", `${pathname}?${params}`);
  };

  const currentEntryPath = () => `${location.pathname}${location.search || ""}`;

  const safeReturnPath = (raw, projectId = "") => {
    const value = String(raw || "").trim();
    if (!value || !value.startsWith("/") || value.startsWith("//")) return "";
    if (value.includes("://") || value.includes("\\")) return "";
    let parsed;
    try {
      parsed = new URL(value, location.origin);
    } catch {
      return "";
    }
    if (parsed.origin !== location.origin) return "";
    const path = `${parsed.pathname}${parsed.search || ""}`;
    const pid = String(projectId || "").trim();
    if (pid && !path.startsWith(`/admin/projects/${pid}/`) && path !== `/admin/projects/${pid}`) return "";
    // Do not bounce back onto the same journey surface.
    if (/\/channels\/[^/]+\/(build|release)(\?|$)/.test(parsed.pathname)) return "";
    return path;
  };

  const backLabelFor = (path) => {
    const bare = String(path || "").split("?")[0];
    if (/\/versions$/.test(bare)) return "返回版本与管线";
    if (/\/build-history$/.test(bare)) return "返回构建与产物";
    if (/\/environments\/[^/]+$/.test(bare)) return "返回环境详情";
    if (/\/overview$/.test(bare)) return "返回项目总览";
    if (/\/release-orders(\/|$)/.test(bare) || /\/release$/.test(bare)) return "返回发版";
    return "返回上一页";
  };

  const withReturnTo = (href, entryPath = "") => {
    try {
      const url = new URL(String(href || ""), location.origin);
      if (!url.searchParams.get("return_to")) {
        url.searchParams.set("return_to", entryPath || currentEntryPath());
      }
      return `${url.pathname}${url.search}`;
    } catch {
      return String(href || "");
    }
  };

  const resolveEntryBack = ({ projectId = "", envKey = "development" } = {}) => {
    const qs = new URLSearchParams(location.search);
    const fromQuery = safeReturnPath(qs.get("return_to"), projectId);
    if (fromQuery) return { href: fromQuery, label: backLabelFor(fromQuery) };

    const ref = String(document.referrer || "").trim();
    if (ref) {
      try {
        const refUrl = new URL(ref);
        if (refUrl.origin === location.origin) {
          const fromRef = safeReturnPath(`${refUrl.pathname}${refUrl.search || ""}`, projectId);
          if (fromRef) return { href: fromRef, label: backLabelFor(fromRef) };
        }
      } catch {
        /* ignore bad referrer */
      }
    }

    const fallback = `/admin/projects/${encodeURIComponent(projectId)}/versions?env_key=${encodeURIComponent(envKey || "development")}`;
    return { href: fallback, label: "返回版本与管线" };
  };

  const applyEntryBack = (anchor, opts = {}) => {
    const node = typeof anchor === "string" ? document.querySelector(anchor) : anchor;
    if (!node) return null;
    const resolved = resolveEntryBack(opts);
    node.setAttribute("href", resolved.href);
    const icon = node.querySelector("img");
    node.textContent = "";
    if (icon) node.appendChild(icon);
    node.appendChild(document.createTextNode(resolved.label));
    return resolved;
  };

  const preserveReturnTo = (qs) => {
    const params = qs instanceof URLSearchParams ? qs : new URLSearchParams(qs || "");
    const current = new URLSearchParams(location.search).get("return_to");
    if (current && !params.get("return_to")) params.set("return_to", current);
    return params;
  };

  window.JourneyCommon = {
    esc,
    toast,
    api,
    chip,
    panel,
    summaryGrid,
    syncUrl,
    withReturnTo,
    resolveEntryBack,
    applyEntryBack,
    preserveReturnTo,
    currentEntryPath,
    renderJourneyProgress: (host, phases, phaseIndex, failed = false) => {
      if (!host || !phases?.length) return;
      host.innerHTML = phases.map((label, index) => {
        const cls = index < phaseIndex ? "done" : index === phaseIndex ? (failed ? "failed active" : "active") : "";
        return `<div class="ro-journey-segment ${cls}" data-phase="${index}"><span>${esc(label)}</span></div>`;
      }).join("");
    },
  };
})();
