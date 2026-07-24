(() => {
  "use strict";

  const CACHE_KEY = "pm_user_favorites_cache_v1";
  let cache = null;
  let loadPromise = null;

  function readCache() {
    if (cache) return cache;
    try {
      cache = JSON.parse(localStorage.getItem(CACHE_KEY) || "{}");
    } catch (_) {
      cache = {};
    }
    if (!cache.page_favorites || typeof cache.page_favorites !== "object") cache.page_favorites = {};
    if (!Array.isArray(cache.project_favorites)) cache.project_favorites = [];
    return cache;
  }

  function writeCache(data) {
    cache = {
      page_favorites: { ...(data.page_favorites || {}) },
      project_favorites: [...(data.project_favorites || [])],
    };
    localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
    document.dispatchEvent(new CustomEvent("pm-favorites-changed", { detail: cache }));
    return cache;
  }

  async function api(path, options) {
    const res = await fetch(path, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      ...options,
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok || payload.ok === false) {
      throw new Error(payload.error || res.statusText || "request failed");
    }
    return payload.data || {};
  }

  function collectLegacyFavorites() {
    const pageFavorites = {};
    const projectSet = new Set();
    try {
      const ids = JSON.parse(localStorage.getItem("p01_project_favorites") || "[]");
      if (Array.isArray(ids)) ids.forEach((id) => projectSet.add(String(id || "").trim()));
    } catch (_) {
      /* ignore */
    }
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i) || "";
      if (key.startsWith("pm_page_favorite_") && localStorage.getItem(key) === "1") {
        const parts = key.slice("pm_page_favorite_".length).split("_");
        if (parts.length >= 2) {
          const page = parts.pop();
          const projectId = parts.join("_");
          pageFavorites[`${projectId}::${page}`] = true;
        }
      }
    }
    return {
      page_favorites: pageFavorites,
      project_favorites: [...projectSet].filter(Boolean),
    };
  }

  function needsLegacyMigration(data) {
    const pageCount = Object.keys(data.page_favorites || {}).length;
    const projectCount = (data.project_favorites || []).length;
    if (pageCount || projectCount) return false;
    const legacy = collectLegacyFavorites();
    return Object.keys(legacy.page_favorites).length > 0 || legacy.project_favorites.length > 0;
  }

  async function migrateLegacyIfNeeded(data) {
    if (!needsLegacyMigration(data)) return data;
    const legacy = collectLegacyFavorites();
    const merged = {
      page_favorites: { ...(legacy.page_favorites || {}), ...(data.page_favorites || {}) },
      project_favorites: [...new Set([...(legacy.project_favorites || []), ...(data.project_favorites || [])])],
    };
    try {
      return await api("/api/user/favorites", {
        method: "PUT",
        body: JSON.stringify(merged),
      });
    } catch (_) {
      return merged;
    }
  }

  async function load() {
    if (loadPromise) return loadPromise;
    loadPromise = api("/api/user/favorites")
      .then((data) => migrateLegacyIfNeeded(data))
      .then((data) => writeCache(data))
      .catch(() => readCache())
      .finally(() => {
        loadPromise = null;
      });
    return loadPromise;
  }

  function pageKey(projectId, pageKey) {
    return `${projectId || ""}::${pageKey || ""}`;
  }

  function isPageFavorite(projectId, page) {
    const data = readCache();
    return !!data.page_favorites[pageKey(projectId, page)];
  }

  function isProjectFavorite(projectId) {
    const data = readCache();
    return data.project_favorites.indexOf(projectId) >= 0;
  }

  async function togglePageFavorite(projectId, page, active) {
    const key = pageKey(projectId, page);
    const legacyKey = `pm_page_favorite_${projectId}_${page}`;
    try {
      const data = await api("/api/user/favorites/toggle-page", {
        method: "POST",
        body: JSON.stringify({ key, active }),
      });
      writeCache(data);
      localStorage.setItem(legacyKey, data.page_favorites[key] ? "1" : "0");
      return !!data.page_favorites[key];
    } catch (_) {
      const next = active === undefined ? localStorage.getItem(legacyKey) !== "1" : !!active;
      localStorage.setItem(legacyKey, next ? "1" : "0");
      const data = readCache();
      if (next) data.page_favorites[key] = true;
      else delete data.page_favorites[key];
      writeCache(data);
      return next;
    }
  }

  async function toggleProjectFavorite(projectId, active) {
    try {
      const data = await api("/api/user/favorites/toggle-project", {
        method: "POST",
        body: JSON.stringify({ project_id: projectId, active }),
      });
      writeCache(data);
      localStorage.setItem("p01_project_favorites", JSON.stringify(data.project_favorites || []));
      return data.project_favorites.indexOf(projectId) >= 0;
    } catch (_) {
      let ids = [];
      try {
        ids = JSON.parse(localStorage.getItem("p01_project_favorites") || "[]");
      } catch (e) {
        ids = [];
      }
      const idx = ids.indexOf(projectId);
      const next = active === undefined ? idx < 0 : !!active;
      if (next && idx < 0) ids.push(projectId);
      if (!next && idx >= 0) ids.splice(idx, 1);
      localStorage.setItem("p01_project_favorites", JSON.stringify(ids));
      writeCache({ ...readCache(), project_favorites: ids });
      return next;
    }
  }

  window.PmUserFavorites = {
    load,
    readCache,
    pageKey,
    isPageFavorite,
    isProjectFavorite,
    togglePageFavorite,
    toggleProjectFavorite,
  };

  load();
})();
