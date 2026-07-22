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

  window.JourneyCommon = { esc, toast, api, chip, panel, summaryGrid, syncUrl, renderJourneyProgress: (host, phases, phaseIndex, failed = false) => {
    if (!host || !phases?.length) return;
    host.innerHTML = phases.map((label, index) => {
      const cls = index < phaseIndex ? "done" : index === phaseIndex ? (failed ? "failed active" : "active") : "";
      return `<div class="ro-journey-segment ${cls}" data-phase="${index}"><span>${esc(label)}</span></div>`;
    }).join("");
  } };
})();
