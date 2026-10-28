  const ROLE_OPTIONS = ["gateway", "auth", "business", "pressure", "database", "cache", "mq", "search", "scheduler", "admin", "edge", "transport", "analytics"];
  const STATUS_OPTIONS = ["normal", "observe", "degraded", "error", "offline"];
  const STATUS_LABELS = { normal: "运行中", observe: "观察中", degraded: "降级中", error: "异常", offline: "离线" };
  const DEFAULT_NODE_SEED_COLOR = "#0f172a";
  const ROLE_LABELS = {
    gateway: "网关服务",
    auth: "认证服务",
    business: "游戏服务",
    pressure: "压测服务",
    database: "数据库",
    cache: "缓存服务",
    mq: "消息队列",
    search: "检索服务",
    scheduler: "调度服务",
    admin: "运维服务",
    edge: "边缘节点",
    transport: "传输服务",
    tcp: "TCP 传输",
    analytics: "数据分析",
  };
  const ROLE_BADGES = {
    gateway: "网",
    auth: "认",
    business: "游",
    pressure: "压",
    database: "库",
    cache: "缓",
    mq: "列",
    search: "搜",
    scheduler: "调",
    admin: "运",
    edge: "边",
    transport: "传",
    analytics: "析",
  };
  const ROLE_COLOR = {
    gateway: { border: "#1890ff", bg1: "#e6f7ff", bg2: "#ffffff", glow: "rgba(24,144,255,.18)" },
    auth: { border: "#52c41a", bg1: "#f6ffed", bg2: "#ffffff", glow: "rgba(82,196,26,.18)" },
    business: { border: "#722ed1", bg1: "#f9f0ff", bg2: "#ffffff", glow: "rgba(114,46,209,.18)" },
    game: { border: "#722ed1", bg1: "#f9f0ff", bg2: "#ffffff", glow: "rgba(114,46,209,.18)" },
    pressure: { border: "#faad14", bg1: "#fffbe6", bg2: "#ffffff", glow: "rgba(250,173,20,.18)" },
    database: { border: "#13c2c2", bg1: "#e6fffb", bg2: "#ffffff", glow: "rgba(19,194,194,.18)" },
    cache: { border: "#13c2c2", bg1: "#e6fffb", bg2: "#ffffff", glow: "rgba(19,194,194,.16)" },
    mq: { border: "#722ed1", bg1: "#f9f0ff", bg2: "#ffffff", glow: "rgba(114,46,209,.16)" },
    search: { border: "#fa8c16", bg1: "#fff7e6", bg2: "#ffffff", glow: "rgba(250,140,22,.16)" },
    scheduler: { border: "#597ef7", bg1: "#f0f5ff", bg2: "#ffffff", glow: "rgba(89,126,247,.16)" },
    admin: { border: "#faad14", bg1: "#fffbe6", bg2: "#ffffff", glow: "rgba(250,173,20,.18)" },
    ops: { border: "#faad14", bg1: "#fffbe6", bg2: "#ffffff", glow: "rgba(250,173,20,.18)" },
    edge: { border: "#ff4d4f", bg1: "#fff1f0", bg2: "#ffffff", glow: "rgba(255,77,79,.18)" },
    transport: { border: "#ff4d4f", bg1: "#fff1f0", bg2: "#ffffff", glow: "rgba(255,77,79,.18)" },
    analytics: { border: "#1890ff", bg1: "#e6f7ff", bg2: "#ffffff", glow: "rgba(24,144,255,.16)" },
  };
  const KINDS = ["entry", "standard", "terminal"];
  const LAYOUT_SPACING_DEFAULTS = { rank_gap: 268, row_gap: 128 };
  const LAYOUT_SPACING_LIMITS = {
    rank_gap: { min: 160, max: 480 },
    row_gap: { min: 80, max: 240 },
  };
  function clampLayoutSpacing(key, value) {
    const lim = LAYOUT_SPACING_LIMITS[key] || { min: 0, max: 9999 };
    const fallback = LAYOUT_SPACING_DEFAULTS[key] || lim.min;
    const num = Number(value);
    if (!Number.isFinite(num)) return fallback;
    return Math.max(lim.min, Math.min(lim.max, Math.round(num)));
  }

  function layoutSpacing() {
    const raw = (((state.topology || {}).meta || {}).layout_spacing) || {};
    return {
      rank_gap: clampLayoutSpacing("rank_gap", raw.rank_gap),
      row_gap: clampLayoutSpacing("row_gap", raw.row_gap),
    };
  }

  function hasSavedNodeLayout() {
    const nodes = ((state.topology || {}).nodes) || [];
    const visible = nodes.filter((n) => !(n.ui || {}).list_only);
    if (!visible.length) return false;
    return visible.every((n) => {
      const ui = n.ui || {};
      return Number.isFinite(Number(ui.x)) && Number.isFinite(Number(ui.y));
    });
  }

  function medianInt(values, fallback) {
    const nums = (values || []).map((v) => Number(v)).filter((v) => Number.isFinite(v) && v > 0);
    if (!nums.length) return fallback;
    nums.sort((a, b) => a - b);
    const mid = Math.floor(nums.length / 2);
    const val = nums.length % 2 ? nums[mid] : Math.round((nums[mid - 1] + nums[mid]) / 2);
    return Number.isFinite(val) && val > 0 ? val : fallback;
  }

  function inferLayoutSpacingFromNodes() {
    const nodes = (((state.topology || {}).nodes) || []).filter((n) => !(n.ui || {}).list_only);
    const byRank = {};
    nodes.forEach((n) => {
      const ui = n.ui || {};
      const rank = ui.rank != null && Number.isFinite(Number(ui.rank))
        ? Number(ui.rank)
        : Math.round((Number(ui.x || 0) - 96) / LAYOUT_SPACING_DEFAULTS.rank_gap);
      if (!byRank[rank]) byRank[rank] = [];
      byRank[rank].push(n);
    });
    const ranks = Object.keys(byRank).map(Number).sort((a, b) => a - b);
    const rankGaps = [];
    for (let i = 1; i < ranks.length; i += 1) {
      const prevX = Number((byRank[ranks[i - 1]][0].ui || {}).x);
      const curX = Number((byRank[ranks[i]][0].ui || {}).x);
      if (Number.isFinite(prevX) && Number.isFinite(curX)) rankGaps.push(curX - prevX);
    }
    const rowGaps = [];
    ranks.forEach((rank) => {
      const rows = byRank[rank].slice().sort((a, b) => Number((a.ui || {}).y) - Number((b.ui || {}).y));
      for (let i = 1; i < rows.length; i += 1) {
        const prevY = Number((rows[i - 1].ui || {}).y);
        const curY = Number((rows[i].ui || {}).y);
        if (Number.isFinite(prevY) && Number.isFinite(curY)) rowGaps.push(curY - prevY);
      }
    });
    return {
      rank_gap: clampLayoutSpacing("rank_gap", medianInt(rankGaps, LAYOUT_SPACING_DEFAULTS.rank_gap)),
      row_gap: clampLayoutSpacing("row_gap", medianInt(rowGaps, LAYOUT_SPACING_DEFAULTS.row_gap)),
    };
  }

  function syncLayoutSpacingFromTopology() {
    if (!state.topology.meta || typeof state.topology.meta !== "object") state.topology.meta = {};
    const meta = state.topology.meta;
    if (meta.layout_spacing && typeof meta.layout_spacing === "object") {
      meta.layout_spacing = {
        rank_gap: clampLayoutSpacing("rank_gap", meta.layout_spacing.rank_gap),
        row_gap: clampLayoutSpacing("row_gap", meta.layout_spacing.row_gap),
      };
      return;
    }
    if (hasSavedNodeLayout()) {
      meta.layout_spacing = inferLayoutSpacingFromNodes();
      return;
    }
    persistLayoutSpacingMeta(null);
  }

  function shouldPreserveTopologyLayoutOnLoad() {
    const meta = ((state.topology || {}).meta) || {};
    if (meta.layout_locked) return true;
    // Structured graphs derive positions from ranks; only honor saved coords when locked.
    if (structuredMode()) return false;
    return hasSavedNodeLayout();
  }

  function nodeRenderHeight(node) {
    const h = Number(((node || {}).ui || {}).h || 104);
    return Math.max(h, 128);
  }

  function syncLayoutSpacingControls() {
    const sp = layoutSpacing();
    const rankEl = $("layoutRankGapRange");
    const rowEl = $("layoutRowGapRange");
    const rankVal = $("layoutRankGapValue");
    const rowVal = $("layoutRowGapValue");
    const bar = document.querySelector(".topology-canvas-spacing-bar");
    const editable = isEditMode() && structuredMode();
    if (rankEl) {
      rankEl.value = String(sp.rank_gap);
      rankEl.disabled = !editable;
    }
    if (rowEl) {
      rowEl.value = String(sp.row_gap);
      rowEl.disabled = !editable;
    }
    if (rankVal) rankVal.textContent = String(sp.rank_gap);
    if (rowVal) rowVal.textContent = String(sp.row_gap);
    if (bar) bar.classList.toggle("is-disabled", !editable);
  }

  function persistLayoutSpacingMeta(patch) {
    if (!state.topology.meta || typeof state.topology.meta !== "object") state.topology.meta = {};
    const cur = layoutSpacing();
    state.topology.meta.layout_spacing = {
      rank_gap: clampLayoutSpacing("rank_gap", patch && patch.rank_gap != null ? patch.rank_gap : cur.rank_gap),
      row_gap: clampLayoutSpacing("row_gap", patch && patch.row_gap != null ? patch.row_gap : cur.row_gap),
    };
    if (patch && (patch.rank_gap != null || patch.row_gap != null)) {
      state.topology.meta.layout_spacing_customized = true;
    }
  }

  let layoutSpacingRelayoutTimer = null;

  function flushLayoutSpacingRelayout(opts) {
    if (layoutSpacingRelayoutTimer) {
      clearTimeout(layoutSpacingRelayoutTimer);
      layoutSpacingRelayoutTimer = null;
    }
    if (!isEditMode()) return;
    persistLayoutSpacingMeta(null);
    state.topology.meta.layout_locked = false;
    layoutStructuredGraph({ force: true });
    if (!(opts && opts.skipHistory)) pushHistory();
    redrawGraph();
    syncLayoutSpacingControls();
  }

  function queueLayoutSpacingRelayout(patch) {
    persistLayoutSpacingMeta(patch);
    if (layoutSpacingRelayoutTimer) clearTimeout(layoutSpacingRelayoutTimer);
    layoutSpacingRelayoutTimer = setTimeout(() => {
      layoutSpacingRelayoutTimer = null;
      if (!isEditMode()) return;
      state.topology.meta.layout_locked = false;
      layoutStructuredGraph({ force: true });
      pushHistory();
      redrawGraph();
      syncLayoutSpacingControls();
    }, 120);
  }

  function applyLayoutSpacing(patch, opts) {
    if (!isEditMode()) {
      toast("运行/测试模式不可调整节点间距", "warn");
      syncLayoutSpacingControls();
      return;
    }
    if (layoutSpacingRelayoutTimer) {
      clearTimeout(layoutSpacingRelayoutTimer);
      layoutSpacingRelayoutTimer = null;
    }
    persistLayoutSpacingMeta(patch || {});
    state.topology.meta.layout_locked = false;
    layoutStructuredGraph({ force: true });
    if (!(opts && opts.skipHistory)) pushHistory();
    redrawGraph();
    syncLayoutSpacingControls();
  }

  async function saveTopologyNow() {
    if (isTestMode()) {
      toast("测试模式禁止保存拓扑", "warn");
      return null;
    }
    flushLayoutSpacingRelayout({ skipHistory: true });
    syncLayoutSpacingFromTopology();
    if (hasSavedNodeLayout()) {
      state.topology.meta.layout_spacing_customized = true;
      state.topology.meta.layout_locked = true;
    }
    const d = await OpsApi.saveTopology(Object.assign(currentScope(), { topology: state.topology }));
    if (d && d.ok !== false && d.topology && d.topology.meta) {
      state.topology.meta = Object.assign({}, state.topology.meta || {}, d.topology.meta || {});
      syncLayoutSpacingControls();
    }
    return d;
  }

  function roleColor(role) {
    const key = String(role || "").toLowerCase();
    const p = ROLE_COLOR[key] || ROLE_COLOR.business || { border: "#3b82f6" };
    return p.border || "#3b82f6";
  }

  function hexRgb(hex) {
    const h = normalizeHexColor(hex, "#722ed1").slice(1);
    return {
      r: parseInt(h.slice(0, 2), 16),
      g: parseInt(h.slice(2, 4), 16),
      b: parseInt(h.slice(4, 6), 16),
    };
  }

  function nodeCustomColor(node) {
    const raw = String((node && node.ui && node.ui.color) || "").trim();
    if (!raw || !/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(raw)) return "";
    const normalized = normalizeHexColor(raw, "");
    if (normalized.toLowerCase() === DEFAULT_NODE_SEED_COLOR) return "";
    return normalized;
  }

  function nodePalette(node) {
    const roleKey = String((node && node.role) || "").toLowerCase();
    const fallback = ROLE_COLOR[roleKey] || ROLE_COLOR.business || { border: "#9ab6e5", bg1: "#ffffff", bg2: "#ffffff", glow: "rgba(37,99,235,.18)" };
    const custom = nodeCustomColor(node);
    if (!custom) return fallback;
    const { r, g, b } = hexRgb(custom);
    return {
      border: custom,
      bg1: "rgb(" + Math.round(r * 0.08 + 255 * 0.92) + "," + Math.round(g * 0.08 + 255 * 0.92) + "," + Math.round(b * 0.08 + 255 * 0.92) + ")",
      bg2: "#ffffff",
      glow: "rgba(" + r + "," + g + "," + b + ",0.18)",
    };
  }

