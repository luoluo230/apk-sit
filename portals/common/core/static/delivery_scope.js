(() => {
  const SCOPE_KEYS = ["env_key", "channel_id", "platform", "version_id", "release_order_id"];
  const DISPLAY_KEYS = ["version_name", "version_code"];

  const normalizeScope = (raw = {}) => {
    const out = {};
    SCOPE_KEYS.forEach((key) => {
      const val = String(raw[key] ?? "").trim();
      if (val) out[key] = key === "platform" ? val.toLowerCase() : val;
    });
    DISPLAY_KEYS.forEach((key) => {
      const val = String(raw[key] ?? "").trim();
      if (val) out[key] = val;
    });
    return out;
  };

  const parseQuery = (search = location.search) => {
    const params = new URLSearchParams(search);
    const scope = {};
    [...SCOPE_KEYS, ...DISPLAY_KEYS, "hint", "error", "from"].forEach((key) => {
      const val = params.get(key);
      if (val) scope[key] = val;
    });
    return normalizeScope(scope);
  };

  const buildQuery = (scope = {}, extra = {}) => {
    const merged = normalizeScope({ ...scope, ...extra });
    const params = new URLSearchParams();
    SCOPE_KEYS.forEach((key) => {
      if (merged[key]) params.set(key, merged[key]);
    });
    DISPLAY_KEYS.forEach((key) => {
      if (merged[key]) params.set(key, merged[key]);
    });
    Object.entries(extra).forEach(([key, val]) => {
      if (!SCOPE_KEYS.includes(key) && !DISPLAY_KEYS.includes(key) && val != null && String(val).trim()) {
        params.set(key, String(val));
      }
    });
    const qs = params.toString();
    return qs ? `?${qs}` : "";
  };

  const href = (path, scope = {}, extra = {}) => `${path}${buildQuery(scope, extra)}`;

  const versionsStartReleaseHref = (projectId, versionId, scope = {}) =>
    href(`/admin/projects/${encodeURIComponent(projectId)}/release-orders/start`, { ...scope, version_id: versionId });

  const versionsPageHref = (projectId, scope = {}, extra = {}) =>
    href(`/admin/projects/${encodeURIComponent(projectId)}/versions`, scope, extra);

  window.DeliveryScope = {
    SCOPE_KEYS,
    DISPLAY_KEYS,
    normalizeScope,
    parseQuery,
    buildQuery,
    href,
    versionsStartReleaseHref,
    versionsPageHref,
  };
})();
