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
    import sys
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
            inp = f'<input type="checkbox" name="{key}" value="true" class="rounded" ' + ('checked' if str(val).lower() in ('true', '1', 'yes') else '') + '>'
        elif vtype == 'string':
            inp = f'<input type="text" name="{key}" value="{html.escape(str(val))}" class="w-full max-w-md px-3 py-1.5 border rounded-lg text-sm" placeholder="https://...">'
        else:
            inp = f'<input type="number" name="{key}" value="{html.escape(str(val))}" class="w-32 px-3 py-1.5 border rounded-lg text-sm" min="1">'
        rows.append(f'<tr><td class="px-4 py-3 font-medium text-gray-700">{html.escape(label)}</td><td class="px-4 py-3">{inp}</td><td class="px-4 py-3 text-sm text-gray-500">{html.escape(desc)}</td></tr>')
    table_rows = ''.join(rows)
    content = f'''
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden mb-6">
        <div class="p-6 border-b">
            <h2 class="text-lg font-semibold text-gray-800">登录与安全</h2>
            <p class="text-sm text-gray-500 mt-1">修改后立即生效。</p>
        </div>
        <form id="settingsForm" class="p-6">
            <table class="min-w-full"><thead class="bg-gray-50"><tr><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">配置项</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">值</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">说明</th></tr></thead><tbody>{table_rows}</tbody></table>
            <button type="submit" class="mt-4 px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700">保存</button>
        </form>
    </div>
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div class="p-6 border-b"><h3 class="font-medium text-gray-700">环境信息（只读）</h3></div>
        <div class="p-6">
            <ul class="text-sm text-gray-600 space-y-1">
                <li>Python: {sys.version.split()[0]}</li>
                <li>数据目录: {html.escape(DATA_DIR)}</li>
                <li>APK 目录: {html.escape(Config.APK_DIR)}</li>
            </ul>
        </div>
    </div>
    <script>
    document.getElementById("settingsForm").onsubmit = function(e) {{
        e.preventDefault();
        var form = this;
        var data = {{}};
        [].forEach.call(form.querySelectorAll("input[name]"), function(inp) {{
            if (inp.type === "checkbox") data[inp.name] = inp.checked ? "true" : "false";
            else data[inp.name] = inp.value;
        }});
        fetch("/admin/settings/save", {{ method: "POST", headers: {{ "Content-Type": "application/json" }}, credentials: "same-origin", body: JSON.stringify(data) }})
        .then(function(r) {{ return r.json(); }}).then(function(d) {{ if (d.error) alert(d.error); else alert("已保存"); }});
    }};
    </script>'''
    return content

