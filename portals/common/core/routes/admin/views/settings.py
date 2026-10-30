# -*- coding: utf-8 -*-
"""Admin system settings page."""

import html
import sys

from config import Config, DATA_DIR
from models.data import get_system_config

DEFAULT_SYSTEM_KEYS = [
    ("LOGIN_ATTEMPTS_LIMIT", "登录失败次数上限", "number", "5", "超过此次数将锁定账号"),
    ("LOGIN_LOCKOUT_MINUTES", "锁定时长（分钟）", "number", "15", "锁定后等待分钟数"),
    ("AUDIT_LOG_RETENTION_DAYS", "操作日志保留天数", "number", "365", "超期可归档或清理"),
    ("NOTIFICATION_SITE_ENABLED", "站内通知开关", "boolean", "true", "是否启用站内通知"),
    ("PASSWORD_MIN_LENGTH", "密码最小长度", "number", "6", "新建/重置密码时的最小长度"),
    ("REQUIRE_APPROVAL_FOR_DELETE", "高危操作需审批", "boolean", "false", "开启后：删除项目、删除版本、删除 Jenkins 实例需先提交审批并通过"),
    ("webhook_url", "Webhook URL", "string", "", "构建/版本等事件推送地址，留空不启用"),
    ("USE_SQLITE", "启用 SQLite", "boolean", "true", "核心 JSON 数据与审计日志同步到 SQLite，便于长期留存与恢复"),
]


def password_min_length():
    v = get_system_config("PASSWORD_MIN_LENGTH")
    try:
        return max(4, int(v)) if v is not None and str(v).strip() else 6
    except (ValueError, TypeError):
        return 6


def render_settings_page():
    values = {}
    for key, *_ in DEFAULT_SYSTEM_KEYS:
        v = get_system_config(key)
        if v is not None:
            values[key] = v
        else:
            if key == 'LOGIN_ATTEMPTS_LIMIT':
                values[key] = getattr(Config, 'LOGIN_ATTEMPTS_LIMIT', 5)
            elif key == 'LOGIN_LOCKOUT_MINUTES':
                values[key] = getattr(Config, 'LOGIN_LOCKOUT_MINUTES', 15)
            elif key == 'webhook_url':
                values[key] = get_system_config('webhook_url') or ''
            elif key == 'USE_SQLITE':
                values[key] = get_system_config('USE_SQLITE') or 'false'
            elif key == 'REQUIRE_APPROVAL_FOR_DELETE':
                values[key] = get_system_config('REQUIRE_APPROVAL_FOR_DELETE') or 'false'
            else:
                values[key] = '365' if key == 'AUDIT_LOG_RETENTION_DAYS' else 'true'
    rows = []
    for key, label, vtype, default, desc in DEFAULT_SYSTEM_KEYS:
        val = values.get(key, default)
        if key == 'webhook_url':
            val = get_system_config('webhook_url') or default
        if vtype == 'boolean':
            inp = (
                f'<label class="flex items-center gap-2 text-sm">'
                f'<input type="checkbox" name="{key}" value="true" '
                + ('checked' if str(val).lower() in ('true', '1', 'yes') else '')
                + '><span>启用</span></label>'
            )
        elif vtype == 'string':
            inp = (
                f'<input type="text" name="{key}" value="{html.escape(str(val))}" '
                f'placeholder="https://...">'
            )
        else:
            inp = (
                f'<input type="number" name="{key}" value="{html.escape(str(val))}" min="1">'
            )
        rows.append(
            f'<tr><td><strong>{html.escape(label)}</strong></td>'
            f'<td>{inp}</td><td>{html.escape(desc)}</td></tr>'
        )
    table_rows = ''.join(rows)
    return f'''
    <header class="pm-page-head">
      <div class="pm-page-head-copy"><div>
        <h1>系统设置</h1>
        <p>登录安全、通知与 Webhook 等平台级参数，保存后立即生效。</p>
      </div></div>
    </header>
    <section class="studio-section">
      <div class="studio-section-head"><h2>登录与安全</h2></div>
      <form id="settingsForm" class="studio-config-panel">
        <div class="pm-table-panel overflow-x-auto">
          <table class="pm-table">
            <thead><tr><th>配置项</th><th>值</th><th>说明</th></tr></thead>
            <tbody>{table_rows}</tbody>
          </table>
        </div>
        <div><button type="submit" class="pm-btn pm-btn--primary">保存</button></div>
      </form>
    </section>
    <section class="studio-section">
      <div class="studio-section-head"><h2>环境信息</h2></div>
      <div class="studio-config-panel">
        <ul class="text-sm text-gray-500" style="margin:0;padding-left:18px;display:flex;flex-direction:column;gap:6px">
          <li>Python: {sys.version.split()[0]}</li>
          <li>数据目录: {html.escape(DATA_DIR)}</li>
          <li>APK 目录: {html.escape(Config.APK_DIR)}</li>
        </ul>
      </div>
    </section>
    <script>
    document.getElementById("settingsForm").onsubmit = function(e) {{
      e.preventDefault();
      var form = this;
      var data = {{}};
      [].forEach.call(form.querySelectorAll("input[name]"), function(inp) {{
        if (inp.type === "checkbox") data[inp.name] = inp.checked ? "true" : "false";
        else data[inp.name] = inp.value;
      }});
      fetch("/admin/settings/save", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        credentials: "same-origin",
        body: JSON.stringify(data)
      }}).then(function(r) {{ return r.json(); }}).then(function(d) {{
        if (d.error) alert(d.error); else alert("已保存");
      }});
    }};
    </script>
    '''
