(function () {
  var STORAGE_KEY = "ops_shell_sidebar_collapsed";
  var ENV_KEY = "ops_shell_last_env";
  var app = document.querySelector(".ops-shell-app");
  var btn = document.querySelector(".ops-shell-collapse-btn");
  if (!app) return;

  if (localStorage.getItem(STORAGE_KEY) === "1") {
    app.classList.add("sidebar-collapsed");
  }

  if (btn) {
    btn.addEventListener("click", function () {
      var collapsed = app.classList.toggle("sidebar-collapsed");
      localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
      var label = btn.querySelector("span");
      if (label) {
        label.textContent = collapsed ? "展开菜单" : "收起菜单";
      }
    });
  }

  var envSelect = document.getElementById("opsShellEnvSelect");
  if (envSelect) {
    envSelect.addEventListener("change", function () {
      var url = new URL(window.location.href);
      url.searchParams.set("env_key", envSelect.value);
      localStorage.setItem(ENV_KEY, envSelect.value);
      window.location.href = url.toString();
    });
  }
})();
