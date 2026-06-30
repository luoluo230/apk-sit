(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.PmDisplayLabels = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var RELEASE_STATUS = {
    verified: { label: "成功", tone: "success" },
    published: { label: "成功", tone: "success" },
    precheck_failed: { label: "失败", tone: "danger" },
    publish_failed: { label: "失败", tone: "danger" },
    verify_failed: { label: "失败", tone: "danger" },
    cancelled: { label: "失败", tone: "danger" },
    verifying: { label: "部分成功", tone: "warning" },
    publishing: { label: "部分成功", tone: "warning" },
    building: { label: "部分成功", tone: "warning" },
    prechecking: { label: "部分成功", tone: "warning" },
    awaiting_approval: { label: "待审批", tone: "warning" },
    ready: { label: "待发布", tone: "muted" },
    approved: { label: "待发布", tone: "muted" },
    draft: { label: "草稿", tone: "muted" },
    artifacts_ready: { label: "部分成功", tone: "warning" },
    rolled_back: { label: "已回滚", tone: "muted" },
  };

  var CARD_STATUS = {
    running: { label: "运行中", tone: "running", dot: "#52c41a" },
    warning: { label: "风险中", tone: "warning", dot: "#faad14" },
    blocked: { label: "阻塞中", tone: "blocked", dot: "#ff4d4f" },
    archived: { label: "已归档", tone: "archived", dot: "#98a2b3" },
  };

  function normalizeKey(raw) {
    return String(raw || "")
      .trim()
      .toLowerCase()
      .replace(/\s+/g, "_");
  }

  function releaseStatus(raw, fallbackLabel) {
    var key = normalizeKey(raw);
    var row = RELEASE_STATUS[key];
    if (row) return { label: row.label, tone: row.tone, raw: key };
    var fb = String(fallbackLabel || raw || "").trim();
    if (fb && !/^[a-z0-9_]+$/.test(fb)) return { label: fb, tone: "muted", raw: key };
    if (fb) {
      return {
        label: fb.replace(/_/g, " "),
        tone: "muted",
        raw: key,
      };
    }
    return { label: "--", tone: "muted", raw: key };
  }

  function cardStatus(raw, fallbackLabel) {
    var key = normalizeKey(raw);
    var row = CARD_STATUS[key];
    if (row) return row;
    return {
      label: String(fallbackLabel || raw || "运行中"),
      tone: "running",
      dot: "#52c41a",
    };
  }

  function healthSublabel(pct, archived) {
    if (archived) return "";
    if (pct == null || isNaN(pct)) return "";
    if (pct >= 90) return "良好";
    if (pct >= 70) return "风险";
    return "阻塞";
  }

  function healthTone(pct, archived) {
    if (archived || pct == null || isNaN(pct)) return "muted";
    if (pct >= 90) return "good";
    if (pct >= 70) return "warn";
    return "bad";
  }

  function formatShortTime(raw) {
    var text = String(raw || "").trim();
    if (!text) return "--";
    if (text.length >= 16 && text.indexOf("T") > 0) return text.slice(11, 16);
    if (text.length >= 16 && text.indexOf(" ") > 0) return text.slice(11, 16);
    if (text.length >= 10 && text.indexOf("-") === 4) return text.slice(5, 10);
    return text.slice(0, 16);
  }

  function formatReleaseDateTime(raw) {
    var text = String(raw || "").trim();
    if (!text) return "";
    if (text.length >= 16) return text.slice(0, 16).replace("T", " ");
    return text;
  }

  return {
    releaseStatus: releaseStatus,
    cardStatus: cardStatus,
    healthSublabel: healthSublabel,
    healthTone: healthTone,
    formatShortTime: formatShortTime,
    formatReleaseDateTime: formatReleaseDateTime,
  };
});
