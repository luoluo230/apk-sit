(function () {
  var STORAGE_KEY = "ops_shell_sidebar_collapsed";
  var app = document.querySelector(".ops-shell-app");
  var btn = document.querySelector(".ops-shell-collapse-btn");
  if (!app) return;

  if (localStorage.getItem(STORAGE_KEY) === "1") {
    app.classList.add("sidebar-collapsed");
  }

  function syncLabel() {
    if (!btn) return;
    var label = btn.querySelector("span");
    if (!label) return;
    label.textContent = app.classList.contains("sidebar-collapsed") ? "展开菜单" : "收起菜单";
  }

  syncLabel();

  if (btn) {
    btn.addEventListener("click", function () {
      var collapsed = app.classList.toggle("sidebar-collapsed");
      localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
      syncLabel();
    });
  }
})();
