(() => {
  const DIALOG_ID = "artifactDownloadDialog";
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const formatFileSize = (bytes) => {
    const n = Number(bytes || 0);
    if (!n) return "";
    if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MB`;
    if (n >= 1024) return `${Math.round(n / 1024)} KB`;
    return `${n} B`;
  };

  let bound = false;

  const ensureDialog = () => {
    if (document.getElementById(DIALOG_ID)) return document.getElementById(DIALOG_ID);
    document.body.insertAdjacentHTML(
      "beforeend",
      `<div id="${DIALOG_ID}" class="adl-dialog is-hidden" aria-hidden="true">
        <div class="adl-card" role="dialog" aria-modal="true" aria-labelledby="adlTitle">
          <div class="adl-head">
            <div><h2 id="adlTitle">安装包下载</h2><p id="adlSubtitle">扫码或打开链接安装</p></div>
            <button type="button" data-adl-close aria-label="关闭"><img src="/static/project_ui/svg/action_close.svg" alt=""></button>
          </div>
          <div class="adl-body" id="adlBody"></div>
          <div class="adl-foot"><button type="button" class="adl-btn neutral" data-adl-close>关闭</button></div>
        </div>
      </div>`,
    );
    if (!bound) {
      const root = document.getElementById(DIALOG_ID);
      root.querySelectorAll("[data-adl-close]").forEach((btn) => btn.addEventListener("click", close));
      root.addEventListener("click", (event) => {
        if (event.target?.id === DIALOG_ID) close();
      });
      bound = true;
    }
    return document.getElementById(DIALOG_ID);
  };

  const close = () => {
    const dialog = document.getElementById(DIALOG_ID);
    if (!dialog) return;
    dialog.classList.add("is-hidden");
    dialog.setAttribute("aria-hidden", "true");
  };

  const show = () => {
    const dialog = ensureDialog();
    dialog.classList.remove("is-hidden");
    dialog.setAttribute("aria-hidden", "false");
  };

  const buildTile = ({ title, badge, badgeClass, variant, url, qr, btnClass }) =>
    `<article class="adl-tile adl-tile-${esc(variant)}">
      <header class="adl-tile-head">
        <h3>${esc(title)}</h3>
        <span class="adl-badge ${esc(badgeClass || "")}">${esc(badge)}</span>
      </header>
      ${qr ? `<div class="adl-qr-wrap"><img class="adl-qr" src="${esc(qr)}" alt="${esc(title)}二维码"></div>` : ""}
      <div class="adl-actions"><a class="adl-btn ${esc(btnClass)}" href="${esc(url)}" target="_blank" rel="noopener">打开链接</a></div>
    </article>`;

  const defaultScopeText = (row = {}, labels = {}) => {
    const env = labels.env || row.env_key || row.env || "";
    const channel = labels.channel || row.channel_name || row.channel_label || row.channel_id || row.channel || "";
    const platform = labels.platform || row.platform_label || row.platform || "";
    return [env, channel, platform].filter(Boolean).join(" · ");
  };

  const defaultTitle = (row = {}, mode = "version") => {
    if (mode === "build") {
      const num = row.build_number || row.jenkins_build_number || row.number || "-";
      return `#${num} · ${row.version_name || "-"} · VC ${row.version_code || "-"}`;
    }
    return `${row.version_name || "-"} · VC ${row.version_code || "-"}`;
  };

  const renderDownloadBody = (downloadInfo = {}) => {
    const apkDl = downloadInfo && typeof downloadInfo === "object" ? downloadInfo : {};
    const publicUrl = apkDl.public_download_url || apkDl.oss_download_url || "";
    const publicQr = apkDl.public_qr_dataurl || apkDl.oss_qr_dataurl || "";
    const localUrl = apkDl.local_download_url || "";
    const localQr = apkDl.local_qr_dataurl || "";
    if (!publicUrl && !localUrl) {
      return `<div class="adl-empty"><strong>暂无可下载的安装包</strong><p>请先完成构建并成功归档 APK。</p></div>`;
    }
    if (!publicUrl) {
      return `<div class="adl-grid">${buildTile({
        title: "本机 / 内网测试",
        badge: "内网",
        badgeClass: "neutral",
        variant: "neutral",
        url: localUrl,
        qr: localQr,
        btnClass: "neutral",
      })}</div>`;
    }
    const cards = [
      buildTile({
        title: "外网下载",
        badge: "外网",
        badgeClass: "",
        variant: "primary",
        url: publicUrl,
        qr: publicQr,
        btnClass: "build",
      }),
    ];
    if (localUrl && localUrl !== publicUrl) {
      cards.push(
        buildTile({
          title: "本机 / 内网测试",
          badge: "内网",
          badgeClass: "neutral",
          variant: "neutral",
          url: localUrl,
          qr: localQr,
          btnClass: "neutral",
        }),
      );
    }
    return `<div class="adl-grid">${cards.join("")}</div>`;
  };

  const renderDownload = (row = {}, downloadInfo = {}, options = {}) => {
    ensureDialog();
    const titleEl = document.getElementById("adlTitle");
    const subtitleEl = document.getElementById("adlSubtitle");
    const bodyEl = document.getElementById("adlBody");
    if (!titleEl || !subtitleEl || !bodyEl) return;
    const apkDl = downloadInfo && typeof downloadInfo === "object" ? downloadInfo : {};
    const scope = options.subtitle || defaultScopeText(row, options.labels || {});
    const meta = [
      apkDl.build_time ? `归档 ${apkDl.build_time}` : "",
      apkDl.build_number ? `构建 #${apkDl.build_number}` : "",
      formatFileSize(apkDl.size_bytes),
    ].filter(Boolean).join(" · ");
    titleEl.textContent = options.title || defaultTitle(row, options.titleMode || "version");
    subtitleEl.textContent = [scope, meta].filter(Boolean).join(" · ") || "扫码或打开链接安装";
    bodyEl.innerHTML = renderDownloadBody(apkDl);
    show();
  };

  const setLoading = (title, subtitle) => {
    ensureDialog();
    document.getElementById("adlTitle").textContent = title || "安装包下载";
    document.getElementById("adlSubtitle").textContent = subtitle || "正在加载下载信息…";
    document.getElementById("adlBody").innerHTML = `<div class="adl-empty"><strong>正在加载</strong><p>请稍候…</p></div>`;
    show();
  };

  const fetchDownloadInfo = async (projectId, versionId, requestFn) => {
    const url = `/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}/apk-download-info`;
    if (typeof requestFn === "function") {
      const data = await requestFn(url);
      return data && typeof data === "object" ? data : {};
    }
    const response = await fetch(url, { credentials: "same-origin" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.error) {
      throw new Error(typeof data.error === "string" ? data.error : "下载信息加载失败");
    }
    return data.download || data;
  };

  const open = async ({
    projectId,
    versionId,
    row = {},
    downloadInfo = null,
    request,
    labels = {},
    title,
    titleMode = "version",
    subtitle,
    fetchInfo = true,
  } = {}) => {
    const vid = String(versionId || row.id || "").trim();
    if (!vid) return Promise.reject(new Error("缺少 VersionCode 标识"));
    const mergedRow = { ...row, id: vid };
    setLoading(title || defaultTitle(mergedRow, titleMode), subtitle || defaultScopeText(mergedRow, labels) || "正在加载下载信息…");
    let info = downloadInfo && typeof downloadInfo === "object" ? downloadInfo : mergedRow.apk_download;
    const hasCached = info && (info.public_download_url || info.oss_download_url || info.local_download_url);
    const hasQr = info && (info.public_qr_dataurl || info.oss_qr_dataurl || info.local_qr_dataurl);
    if (fetchInfo && projectId && (!hasCached || !hasQr)) {
      try {
        const fetched = await fetchDownloadInfo(projectId, vid, request);
        info = { ...(info || {}), ...fetched };
      } catch (error) {
        if (!hasCached) {
          document.getElementById("adlBody").innerHTML = `<div class="adl-empty"><strong>下载信息加载失败</strong><p>${esc(error.message || "请稍后重试")}</p></div>`;
          document.getElementById("adlSubtitle").textContent = subtitle || defaultScopeText(mergedRow, labels);
          return;
        }
      }
    }
    renderDownload(mergedRow, info || {}, { labels, title, titleMode, subtitle });
  };

  const openPicker = async ({ items = [], projectId, request, labels = {}, formatPickLabel, titleMode = "version" } = {}) => {
    const list = (items || []).filter(Boolean);
    if (!list.length) return Promise.reject(new Error("暂无可下载的产物"));
    if (list.length === 1) {
      return open({ projectId, versionId: list[0].id, row: list[0], request, labels, titleMode });
    }
    ensureDialog();
    document.getElementById("adlTitle").textContent = "选择 VersionCode 下载";
    document.getElementById("adlSubtitle").textContent = "该版本组下有多个可下载产物，请选择其一";
    document.getElementById("adlBody").innerHTML = `<div class="adl-pick-list">${list
      .map((row) => {
        const labelFn = typeof formatPickLabel === "function"
          ? formatPickLabel(row)
          : { main: `VC ${row.version_code || "-"}`, sub: `${row.version_name || ""}`.trim() };
        return `<button class="adl-pick" type="button" data-adl-pick="${esc(row.id || "")}"><strong>${esc(labelFn.main || "")}</strong>${labelFn.sub ? `<span>${esc(labelFn.sub)}</span>` : ""}</button>`;
      })
      .join("")}</div>`;
    show();
    document.getElementById("adlBody").querySelectorAll("[data-adl-pick]").forEach((button) => {
      button.onclick = () => {
        const id = button.getAttribute("data-adl-pick") || "";
        const row = list.find((item) => String(item.id || "") === id);
        if (row) open({ projectId, versionId: id, row, request, labels, titleMode });
      };
    });
  };

  window.ArtifactDownload = { open, openPicker, close, renderDownload, ensureDialog };
})();
