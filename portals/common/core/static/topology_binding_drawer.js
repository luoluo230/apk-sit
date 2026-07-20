(() => {
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const statusClass = (status) => {
    const st = String(status || "").toLowerCase();
    if (st === "running" || st === "validated") return "ready";
    if (st === "draft" || st === "stopped") return "pending";
    return "neutral";
  };

  const cardClass = (status) => {
    const st = String(status || "").toLowerCase();
    if (st === "running" || st === "validated") return "configured";
    if (st === "draft" || st === "stopped") return "unconfigured";
    return "neutral";
  };

  function bindEnvLineCardTabs(root) {
    const host = root || document;
    host.querySelectorAll(".env-line-card-tabs").forEach((tabs) => {
      if (tabs.dataset.bound === "1") return;
      tabs.dataset.bound = "1";
      const card = tabs.closest(".env-line-card");
      tabs.querySelectorAll(".env-line-tab").forEach((btn) => {
        btn.addEventListener("click", () => {
          const key = btn.dataset.cardTab || "client";
          tabs.querySelectorAll(".env-line-tab").forEach((node) => node.classList.toggle("is-active", node === btn));
          tabs.querySelectorAll(".env-line-tab-pane").forEach((pane) => {
            pane.classList.toggle("is-active", pane.dataset.cardPane === key);
          });
          if (card) card.dataset.activeTab = key;
        });
      });
    });
  }

  function scopeHref(path, scope) {
    if (window.DeliveryScope && typeof window.DeliveryScope.href === "function") {
      return window.DeliveryScope.href(path, scope);
    }
    const params = new URLSearchParams();
    ["env_key", "channel_id", "platform"].forEach((key) => {
      if (scope[key]) params.set(key, scope[key]);
    });
    const qs = params.toString();
    return qs ? `${path}?${qs}` : path;
  }

  const TopologyBindingDrawer = {
    projectId: "",
    envKey: "",
    channelId: "",
    platform: "",
    channelName: "",
    versionName: "",
    selectedTopologyId: "",
    state: null,
    onSaved: null,

    init(options = {}) {
      this.projectId = String(options.projectId || "").trim();
      this.onSaved = typeof options.onSaved === "function" ? options.onSaved : null;
      const drawer = document.getElementById("topologyBindingDrawer");
      if (!drawer || drawer.dataset.bound === "1") return;
      drawer.dataset.bound = "1";
      drawer.querySelector("[data-drawer-close]")?.addEventListener("click", () => this.close());
      drawer.querySelector(".topology-drawer-backdrop")?.addEventListener("click", () => this.close());
      drawer.querySelector("#topologyDrawerSearch")?.addEventListener("input", () => this.renderList());
      drawer.querySelector("#topologyDrawerEnv")?.addEventListener("change", () => this.renderList());
      drawer.querySelector("#topologyDrawerStatus")?.addEventListener("change", () => this.renderList());
      drawer.querySelector("#topologyDrawerSameEnv")?.addEventListener("change", () => this.renderList());
      drawer.querySelector("#topologyDrawerSave")?.addEventListener("click", () => this.saveBinding());
      drawer.querySelector("#topologyDrawerClear")?.addEventListener("click", () => this.clearBinding());
      drawer.querySelector("#topologyDrawerAssets")?.addEventListener("click", (event) => {
        event.preventDefault();
        window.location.href = scopeHref(`/admin/projects/${encodeURIComponent(this.projectId)}/topologies`, {
          env_key: this.envKey,
          channel_id: this.channelId,
          platform: this.platform,
        });
      });
      document.addEventListener("click", (event) => {
        const btn = event.target.closest("[data-open-topology-drawer]");
        if (!btn) return;
        event.preventDefault();
        const card = btn.closest(".env-line-card");
        if (!card) return;
        this.open({
          envKey: card.dataset.envKey || "",
          channelId: card.dataset.channelId || "",
          platform: card.dataset.platform || "",
          channelName: card.dataset.channelName || "",
          versionName: card.dataset.versionName || "",
        });
      });
    },

    open(scope = {}) {
      this.envKey = String(scope.envKey || "").trim();
      this.channelId = String(scope.channelId || "").trim();
      this.platform = String(scope.platform || "").trim().toLowerCase();
      this.channelName = String(scope.channelName || "").trim();
      this.versionName = String(scope.versionName || "").trim();
      this.selectedTopologyId = "";
      const drawer = document.getElementById("topologyBindingDrawer");
      if (!drawer) return;
      drawer.classList.remove("is-hidden");
      drawer.setAttribute("aria-hidden", "false");
      document.body.classList.add("topology-drawer-open");
      this.loadPicker();
    },

    close() {
      const drawer = document.getElementById("topologyBindingDrawer");
      if (!drawer) return;
      drawer.classList.add("is-hidden");
      drawer.setAttribute("aria-hidden", "true");
      document.body.classList.remove("topology-drawer-open");
    },

    async loadPicker() {
      const summary = document.getElementById("topologyDrawerSummary");
      const list = document.getElementById("topologyDrawerList");
      if (summary) summary.textContent = "加载拓扑列表…";
      if (list) list.innerHTML = '<div class="topology-drawer-empty">加载中…</div>';
      try {
        const params = new URLSearchParams({
          env_key: this.envKey,
          channel_id: this.channelId,
          platform: this.platform,
        });
        if (this.versionName) params.set("version_name", this.versionName);
        const response = await fetch(
          `/api/projects/${encodeURIComponent(this.projectId)}/topology-binding-picker?${params.toString()}`,
          { credentials: "same-origin" }
        );
        const result = await response.json();
        if (!response.ok || result.ok === false) throw new Error(result.error || "加载失败");
        this.state = result.data || {};
        this.selectedTopologyId = String(this.state.resolved?.topology_id || "").trim();
        this.populateFilters();
        this.renderSummary();
        this.renderList();
      } catch (error) {
        if (summary) summary.textContent = error.message || "加载失败";
        if (list) list.innerHTML = `<div class="topology-drawer-empty">${esc(error.message || "加载失败")}</div>`;
      }
    },

    populateFilters() {
      const envSelect = document.getElementById("topologyDrawerEnv");
      const statusSelect = document.getElementById("topologyDrawerStatus");
      const filters = this.state?.filters || {};
      if (envSelect) {
        envSelect.innerHTML =
          '<option value="">全部环境</option>' +
          (filters.environments || [])
            .map((item) => `<option value="${esc(item.env_key)}">${esc(item.label || item.env_key)}</option>`)
            .join("");
        envSelect.value = this.envKey || "";
      }
      if (statusSelect) {
        statusSelect.innerHTML =
          '<option value="">全部状态</option>' +
          (filters.statuses || [])
            .map((item) => `<option value="${esc(item.value)}">${esc(item.label || item.value)}</option>`)
            .join("");
      }
      const sameEnv = document.getElementById("topologyDrawerSameEnv");
      if (sameEnv) sameEnv.checked = true;
    },

    renderSummary() {
      const host = document.getElementById("topologyDrawerSummary");
      if (!host || !this.state) return;
      const scope = this.state.scope || {};
      const resolved = this.state.resolved || {};
      const envLabels = { development: "开发环境", testing: "测试环境", staging: "预发环境", production: "生产环境" };
      const scopeText = [
        envLabels[scope.env_key] || scope.env_key || "-",
        scope.channel_name || scope.channel_id || "-",
        (scope.platform || "").toUpperCase() || "-",
      ].join(" · ");
      host.innerHTML = `<div class="topology-drawer-scope">${esc(scopeText)}</div>
        <div class="topology-drawer-hit"><span>当前命中</span><strong>${esc(resolved.topology_name || resolved.topology_id || "未绑定")}</strong>
        ${resolved.binding_source_label ? `<em>${esc(resolved.binding_source_label)}</em>` : ""}</div>`;
    },

    filteredTopologies() {
      const rows = this.state?.topologies || [];
      const kw = String(document.getElementById("topologyDrawerSearch")?.value || "")
        .trim()
        .toLowerCase();
      const env = String(document.getElementById("topologyDrawerEnv")?.value || "").trim();
      const status = String(document.getElementById("topologyDrawerStatus")?.value || "").trim();
      const sameEnvOnly = Boolean(document.getElementById("topologyDrawerSameEnv")?.checked);
      return rows.filter((item) => {
        const hay = [item.name, item.topology_id, item.env_label].join(" ").toLowerCase();
        if (kw && !hay.includes(kw)) return false;
        if (env && item.env_key !== env) return false;
        if (status && item.status !== status) return false;
        if (sameEnvOnly && this.envKey && item.env_key && item.env_key !== this.envKey) return false;
        return true;
      });
    },

    renderList() {
      const host = document.getElementById("topologyDrawerList");
      if (!host) return;
      const rows = this.filteredTopologies();
      if (!rows.length) {
        host.innerHTML = '<div class="topology-drawer-empty">无匹配拓扑，请调整筛选或先在拓扑资产中创建。</div>';
        return;
      }
      host.innerHTML = rows
        .map((item) => {
          const flags = item.flags || {};
          const runtime = item.runtime || {};
          const selected = item.topology_id === this.selectedTopologyId;
          const refs = (item.binding_refs || [])
            .slice(0, 3)
            .map((ref) => esc(ref.scope_label || ref.level_label || "绑定"))
            .join("；");
          const refMore = (item.binding_ref_count || 0) > 3 ? ` 等${item.binding_ref_count}处` : "";
          return `<article class="topology-picker-card ${cardClass(item.status)}${selected ? " is-selected" : ""}${flags.is_current_hit ? " is-current" : ""}" data-topology-id="${esc(item.topology_id)}" tabindex="0">
            <div class="topology-picker-head">
              <div class="topology-picker-title"><strong>${esc(item.name || item.topology_id)}</strong>
                <span class="env-line-badge ${statusClass(item.status)}">${esc(item.status_label || item.status)}</span>
                ${flags.is_current_hit ? '<span class="topology-picker-flag hit">当前命中</span>' : ""}
                ${runtime.active ? '<span class="topology-picker-flag runtime">Runtime</span>' : ""}
                ${item.binding_ref_count ? `<span class="topology-picker-flag bound">已绑定(${item.binding_ref_count})</span>` : ""}
              </div>
              <button type="button" class="matrix-btn topology topology-picker-select" data-select-topology="${esc(item.topology_id)}">${selected ? "已选" : "选择"}</button>
            </div>
            <p class="topology-picker-meta">${esc(item.env_label || item.env_key || "-")} · ${esc(item.node_count || 0)}节点 / ${esc(item.edge_count || 0)}连线 · 更新 ${esc(String(item.updated_at || "-").slice(0, 10))}</p>
            ${refs ? `<p class="topology-picker-refs">绑定：${refs}${esc(refMore)}</p>` : '<p class="topology-picker-refs muted">尚未绑定到任何 scope</p>'}
            <div class="topology-picker-actions">
              <a class="matrix-btn build" href="/admin/projects/${encodeURIComponent(this.projectId)}/topologies/canvas?env_key=${encodeURIComponent(item.env_key || this.envKey)}&topology_id=${encodeURIComponent(item.topology_id)}">画布</a>
            </div>
          </article>`;
        })
        .join("");
      host.querySelectorAll("[data-select-topology], .topology-picker-card").forEach((node) => {
        node.addEventListener("click", (event) => {
          if (event.target.closest("a")) return;
          const tid = node.dataset.selectTopology || node.dataset.topologyId;
          if (!tid) return;
          this.selectedTopologyId = tid;
          this.renderList();
          const preview = document.getElementById("topologyDrawerPreview");
          if (preview) preview.textContent = `保存后将绑定到：${tid}`;
        });
      });
    },

    csrfHeaders() {
      const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
      return token ? { "X-CSRFToken": token } : {};
    },

    async saveBinding() {
      if (!this.selectedTopologyId) {
        alert("请先选择一个拓扑");
        return;
      }
      const btn = document.getElementById("topologyDrawerSave");
      try {
        if (btn) btn.disabled = true;
        const response = await fetch(`/api/projects/${encodeURIComponent(this.projectId)}/topology-bindings`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...this.csrfHeaders() },
          credentials: "same-origin",
          body: JSON.stringify({
            env_key: this.envKey,
            channel_id: this.channelId,
            platform: this.platform,
            topology_id: this.selectedTopologyId,
          }),
        });
        const result = await response.json();
        if (!response.ok || result.ok === false) throw new Error(result.error || "保存失败");
        if (typeof this.onSaved === "function") await this.onSaved();
        this.close();
      } catch (error) {
        alert(error.message || "保存失败");
      } finally {
        if (btn) btn.disabled = false;
      }
    },

    async clearBinding() {
      if (!confirm("清除当前 scope 的覆盖绑定并恢复继承？")) return;
      const btn = document.getElementById("topologyDrawerClear");
      try {
        if (btn) btn.disabled = true;
        const response = await fetch(`/api/projects/${encodeURIComponent(this.projectId)}/topology-bindings/scope`, {
          method: "DELETE",
          headers: { "Content-Type": "application/json", ...this.csrfHeaders() },
          credentials: "same-origin",
          body: JSON.stringify({
            env_key: this.envKey,
            channel_id: this.channelId,
            platform: this.platform,
          }),
        });
        const result = await response.json();
        if (!response.ok || result.ok === false) throw new Error(result.error || "清除失败");
        if (typeof this.onSaved === "function") await this.onSaved();
        this.close();
      } catch (error) {
        alert(error.message || "清除失败");
      } finally {
        if (btn) btn.disabled = false;
      }
    },

    maybeOpenFromQuery() {
      const params = new URLSearchParams(window.location.search);
      if (params.get("open_topology_drawer") !== "1") return;
      this.open({
        envKey: params.get("env_key") || "",
        channelId: params.get("channel_id") || "",
        platform: params.get("platform") || "",
        channelName: params.get("channel_name") || "",
        versionName: params.get("version_name") || "",
      });
    },
  };

  window.TopologyBindingDrawer = TopologyBindingDrawer;
  window.bindEnvLineCardTabs = bindEnvLineCardTabs;
})();
