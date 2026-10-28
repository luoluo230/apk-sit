(() => {
  const root = document.querySelector(".version-workspace");
  if (!root) return;

  const projectId = root.dataset.projectId || "";
  const table = document.getElementById("vwMatrixTable");
  const caption = document.getElementById("vwLineCaption");
  const clearBtn = document.getElementById("vwMatrixClear");
  if (!table) return;

  const esc = (v) =>
    String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  let matrix = { channels: [], platforms: [], cells: [], env_label: "", env_key: "" };
  let selected = { channel_id: "", platform: "" };
  let userTouched = false;

  const envKey = () =>
    document.getElementById("versionEnv")?.value || root.dataset.envKey || "development";

  const cellKey = (channelId, platform) => `${channelId || ""}::${platform || ""}`;

  const findCell = (channelId, platform) =>
    (matrix.cells || []).find(
      (row) => row.channel_id === channelId && row.platform === platform
    );

  const updateCaption = () => {
    if (!caption) return;
    if (!selected.channel_id && !selected.platform) {
      caption.textContent = "未选择交付线：下面列出本环境全部大版本。点格子可按渠道过滤构建。";
      return;
    }
    const cell = findCell(selected.channel_id, selected.platform);
    const channelName = cell?.channel_name || selected.channel_id;
    const platformLabel = cell?.platform_label || selected.platform;
    caption.textContent = `当前：${matrix.env_label || envKey()} · ${channelName} · ${platformLabel}。版本组按环境+平台共享管线；VersionCode 已按该渠道过滤。`;
  };

  const paintSelection = () => {
    table.querySelectorAll("[data-matrix-cell]").forEach((btn) => {
      const on =
        btn.getAttribute("data-channel") === (selected.channel_id || "") &&
        btn.getAttribute("data-platform") === (selected.platform || "");
      btn.classList.toggle("is-selected", on);
    });
    updateCaption();
  };

  const emitSelection = (user) => {
    root.dispatchEvent(
      new CustomEvent("vw-select-line", {
        bubbles: true,
        detail: {
          channel_id: selected.channel_id,
          platform: selected.platform,
          user: Boolean(user),
        },
      })
    );
  };

  const render = () => {
    const channels = matrix.channels || [];
    const platforms = matrix.platforms || [];
    if (!channels.length || !platforms.length) {
      table.innerHTML = '<div class="version-empty">当前环境没有交付线，请先在项目总览配置渠道和平台。</div>';
      updateCaption();
      return;
    }
    const head = `<tr><th>渠道 \\ 平台</th>${platforms
      .map((p) => `<th>${esc(p.label || p.value)}</th>`)
      .join("")}</tr>`;
    const body = channels
      .map((ch) => {
        const cells = platforms
          .map((p) => {
            const cell = findCell(ch.channel_id, p.value) || {
              status: "empty",
              label: "未配管线",
              channel_id: ch.channel_id,
              platform: p.value,
            };
            return `<td><button type="button" class="vw-matrix-cell vw-matrix-cell--${esc(cell.status)}" data-matrix-cell data-channel="${esc(ch.channel_id)}" data-platform="${esc(p.value)}"><strong>${esc(cell.label)}</strong><span>${esc(cell.status === "live" ? "线上 Bundle" : cell.vc_count ? `${cell.vc_count} 个构建` : "点击查看")}</span></button></td>`;
          })
          .join("");
        return `<tr><th>${esc(ch.channel_name)}</th>${cells}</tr>`;
      })
      .join("");
    table.innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
    table.querySelectorAll("[data-matrix-cell]").forEach((btn) => {
      btn.addEventListener("click", () => {
        userTouched = true;
        selected = {
          channel_id: btn.getAttribute("data-channel") || "",
          platform: btn.getAttribute("data-platform") || "",
        };
        paintSelection();
        emitSelection(true);
      });
    });
    paintSelection();
  };

  const defaultSelection = () => {
    const url = new URLSearchParams(location.search);
    const urlChannel = url.get("channel_id") || root.dataset.channelFilter || "";
    const urlPlatform = url.get("platform") || root.dataset.platformFilter || "";
    if (urlChannel && urlPlatform && findCell(urlChannel, urlPlatform)) {
      return { channel_id: urlChannel, platform: urlPlatform };
    }
    const live = (matrix.cells || []).find((row) => row.status === "live");
    if (live) return { channel_id: live.channel_id, platform: live.platform };
    const first = (matrix.cells || [])[0];
    if (first) return { channel_id: first.channel_id, platform: first.platform };
    return { channel_id: "", platform: "" };
  };

  const loadMatrix = async () => {
    const env = envKey();
    const res = await fetch(
      `/api/projects/${encodeURIComponent(projectId)}/version-delivery-matrix?env_key=${encodeURIComponent(env)}`,
      { credentials: "same-origin" }
    );
    const body = await res.json();
    if (!res.ok || body.ok === false) throw new Error(body.error || "交付线加载失败");
    matrix = body.data || body;
    const previous = cellKey(selected.channel_id, selected.platform);
    if (userTouched) {
      const keepCell = selected.channel_id && selected.platform && findCell(selected.channel_id, selected.platform);
      if (!keepCell && (selected.channel_id || selected.platform)) selected = defaultSelection();
    } else {
      selected = defaultSelection();
    }
    render();
    if (cellKey(selected.channel_id, selected.platform) !== previous) {
      emitSelection(false);
    }
  };

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      userTouched = true;
      selected = { channel_id: "", platform: "" };
      paintSelection();
      emitSelection(true);
    });
  }

  root.addEventListener("vw-matrix-refresh", () => {
    loadMatrix().catch((err) => {
      table.innerHTML = `<div class="version-empty">${esc(err.message || "交付线加载失败")}</div>`;
    });
  });

  loadMatrix().catch((err) => {
    table.innerHTML = `<div class="version-empty">${esc(err.message || "交付线加载失败")}</div>`;
  });
})();
