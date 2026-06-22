# -*- coding: utf-8 -*-
"""RBAC dynamic configuration UI (§11.5)."""

from __future__ import annotations

import html

from services.authz import ADMIN_MODULES


def render_rbac_page(username: str) -> str:
    module_options = "".join(
        f'<label class="flex items-center gap-2 text-sm"><input type="checkbox" class="module-opt" value="{html.escape(str(mid[0]))}"> {html.escape(str(mid[1] if len(mid) > 1 else mid[0]))}</label>'
        for mid in ADMIN_MODULES
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>RBAC 动态配置</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; background: #f8fafc; color: #0f172a; }}
    .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; max-width: 920px; }}
    .row {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }}
    input[type=text] {{ padding: 8px 10px; border: 1px solid #cbd5e1; border-radius: 8px; min-width: 220px; }}
    button {{ padding: 8px 14px; border: 0; border-radius: 8px; background: #0f172a; color: #fff; cursor: pointer; }}
    .modules {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 12px 0; }}
    pre {{ background: #f1f5f9; padding: 12px; border-radius: 8px; overflow: auto; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>RBAC 动态配置</h1>
    <p>当前操作者：<strong>{html.escape(username)}</strong></p>
    <div class="row">
      <input id="targetUser" type="text" placeholder="目标用户名">
      <button type="button" onclick="loadUser()">加载</button>
      <button type="button" onclick="saveUser()">保存权限</button>
    </div>
    <div class="modules">{module_options}</div>
    <pre id="output">选择用户后加载 allowed_modules</pre>
  </div>
  <script>
    let currentUser = '';
    function setModules(mods) {{
      document.querySelectorAll('.module-opt').forEach(el => {{
        el.checked = mods.indexOf(el.value) >= 0;
      }});
    }}
    function loadUser() {{
      const u = document.getElementById('targetUser').value.trim();
      if (!u) return alert('请输入用户名');
      fetch('/admin/rbac/users/' + encodeURIComponent(u), {{ credentials: 'same-origin' }})
        .then(r => r.json())
        .then(d => {{
          currentUser = u;
          const mods = d.allowed_modules || d.user?.allowed_modules || [];
          setModules(mods);
          document.getElementById('output').textContent = JSON.stringify(d, null, 2);
        }})
        .catch(err => alert('加载失败: ' + err));
    }}
    function saveUser() {{
      if (!currentUser) return alert('请先加载用户');
      const mods = Array.from(document.querySelectorAll('.module-opt:checked')).map(el => el.value);
      fetch('/admin/rbac/users/' + encodeURIComponent(currentUser), {{
        method: 'PUT',
        credentials: 'same-origin',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ allowed_modules: mods }})
      }}).then(r => r.json()).then(d => {{
        document.getElementById('output').textContent = JSON.stringify(d, null, 2);
        alert(d.error ? d.error : '已保存');
      }});
    }}
  </script>
</body>
</html>"""
