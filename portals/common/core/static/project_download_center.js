(() => {
  const root = document.querySelector(".download-center-app");
  if (!root) return;
  const projectId = root.dataset.projectId;
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const envLabels = { development: "开发", testing: "测试", staging: "预发", production: "生产", canary: "灰度" };
  const platformLabels = { android: "Android", ios: "iOS", wechat_minigame: "微信小游戏" };
  let rows = [];
  const grid = root.querySelector("[data-dc-rows]");
  const dialog = root.querySelector("[data-dc-dialog]");
  const fillChannels = () => {
    const select = root.querySelector("[data-dc-channel]");
    const current = select.value;
    const seen = new Map();
    rows.forEach((row) => {
      if (row.channel_id) seen.set(row.channel_id, row.channel_name || row.channel_id);
    });
    select.innerHTML = `<option value="">全部渠道</option>` + [...seen.entries()].map(([id, name]) => `<option value="${esc(id)}">${esc(name)}</option>`).join("");
    if ([...select.options].some((opt) => opt.value === current)) select.value = current;
  };
  const filtered = () => {
    const q = (root.querySelector("[data-dc-search]").value || "").trim().toLowerCase();
    const env = root.querySelector("[data-dc-env]").value;
    const platform = root.querySelector("[data-dc-platform]").value;
    const channel = root.querySelector("[data-dc-channel]").value;
    return rows.filter((row) => {
      const hay = `${row.version_name} ${row.version_code} ${row.channel_name} ${row.notes}`.toLowerCase();
      return (!q || hay.includes(q)) && (!env || row.env_key === env) && (!platform || row.platform === platform) && (!channel || row.channel_id === channel);
    });
  };
  const entryBlock = (row) => {
    if (row.kind === "apk" && row.download_url) {
      return `<a class="dc-entry" href="${esc(row.download_url)}" target="_blank" rel="noopener">${row.qr_dataurl ? `<img src="${esc(row.qr_dataurl)}" alt="安装包二维码">` : ""}<span>安装包下载</span></a>`;
    }
    if (row.kind === "store" && row.store_url) {
      return `<a class="dc-entry" href="${esc(row.store_url)}" target="_blank" rel="noopener">${row.qr_dataurl ? `<img src="${esc(row.qr_dataurl)}" alt="商店二维码">` : ""}<span>${esc(row.store_label || "商店链接")}</span></a>`;
    }
    return `<div class="dc-entry is-empty"><span>未配置下载或商店链接</span></div>`;
  };
  const render = () => {
    const list = filtered();
    root.querySelector("[data-dc-count]").textContent = `共 ${list.length} 条`;
    if (!list.length) {
      grid.innerHTML = `<p class="dc-empty">当前筛选下没有版本入口</p>`;
      return;
    }
    grid.innerHTML = list.map((row, index) => `
      <article class="dc-card">
        <header>
          <strong>${esc(row.version_name || "未命名")} / ${esc(row.version_code || "-")}</strong>
          <span class="dc-mark" data-mark="${esc(row.release_mark)}">${esc(row.release_label)}</span>
        </header>
        <p>${esc(envLabels[row.env_key] || row.env_key)} · ${esc(row.channel_name)} · ${esc(platformLabels[row.platform] || row.platform)}</p>
        ${entryBlock(row)}
        <button type="button" class="pm-btn pm-btn--compact" data-dc-detail="${index}">详情</button>
      </article>
    `).join("");
    grid.querySelectorAll("[data-dc-detail]").forEach((button) => {
      button.onclick = () => openDetail(list[Number(button.dataset.dcDetail)]);
    });
  };
  const openDetail = (row) => {
    if (!row || !dialog) return;
    dialog.querySelector("[data-dc-detail-body]").innerHTML = [
      ["版本", `${row.version_name || "-"} / ${row.version_code || "-"}`],
      ["环境 / 渠道 / 平台", `${envLabels[row.env_key] || row.env_key} / ${row.channel_name} / ${platformLabels[row.platform] || row.platform}`],
      ["发版标记", row.release_label || "-"],
      ["构建号", row.build_number ? `#${row.build_number}` : "-"],
      ["打包人员", row.triggered_by || "-"],
      ["时间", row.finished_at || "-"],
      ["打包说明", row.notes || "无"],
      ["入口", row.kind === "apk" ? "安装包" : row.kind === "store" ? (row.store_label || "商店") : "未配置"],
    ].map(([label, value]) => `<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
    dialog.hidden = false;
  };
  const load = async () => {
    grid.innerHTML = `<p class="dc-empty">正在加载…</p>`;
    try {
      const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/download-catalog`, { credentials: "same-origin" });
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || "加载失败");
      rows = data.data || [];
      fillChannels();
      render();
    } catch (error) {
      grid.innerHTML = `<p class="dc-empty">${esc(error.message)}</p>`;
    }
  };
  root.querySelector("[data-dc-refresh]").onclick = load;
  root.querySelector("[data-dc-search]").oninput = render;
  root.querySelector("[data-dc-env]").onchange = render;
  root.querySelector("[data-dc-platform]").onchange = render;
  root.querySelector("[data-dc-channel]").onchange = render;
  dialog?.querySelector("[data-dc-close]")?.addEventListener("click", () => { dialog.hidden = true; });
  dialog?.addEventListener("click", (event) => { if (event.target === dialog) dialog.hidden = true; });
  document.addEventListener("pm-shell-search", (event) => {
    root.querySelector("[data-dc-search]").value = event.detail?.query || "";
    render();
  });
  load();
})();
