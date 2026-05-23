# -*- coding: utf-8 -*-
"""Authentication: login, logout, and profile."""

import hashlib
import logging
from datetime import datetime

from flask import Blueprint, jsonify, make_response, redirect, render_template_string, request, session

from models.data import (
    check_login_attempts,
    log_audit,
    login_attempts,
    record_login_attempt,
    save_users,
    users_db,
)
from services import authz as authz_service
from services.company_profile import get_company_profile
from services.portal_content import get_dev_portal_content

logger = logging.getLogger(__name__)
bp = Blueprint("auth", __name__)

ADMIN_MODULES = authz_service.ADMIN_MODULES
ALL_MODULES_EXCEPT_USER_MANAGEMENT = authz_service.ALL_MODULES_EXCEPT_USER_MANAGEMENT
is_super_admin_or_admin = authz_service.is_super_admin_or_admin
has_scope = authz_service.has_scope
can_access_module = authz_service.can_access_module
get_visible_modules = authz_service.get_visible_modules
admin_required = authz_service.admin_required
admin_required_any = authz_service.admin_required_any
login_required = authz_service.login_required
is_admin = authz_service.is_admin


def _get_csrf_token():
    try:
        from flask_wtf.csrf import generate_csrf

        return generate_csrf()
    except ImportError:
        return ""


LOGIN_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ company_name }} - 登录工作台</title>
    <link rel="stylesheet" href="/static/tailwind.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Marcellus&family=Noto+Sans+SC:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Noto Sans SC', sans-serif; }
        .font-display { font-family: 'Marcellus', serif; }
    </style>
</head>
<body class="min-h-screen bg-slate-950 text-slate-100">
    <div class="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(125,211,252,0.18),_transparent_28%),radial-gradient(circle_at_85%_15%,_rgba(244,114,182,0.14),_transparent_24%),linear-gradient(135deg,_#081120,_#111827_48%,_#1f2937)]">
        <div class="mx-auto grid min-h-screen max-w-7xl items-center gap-8 px-4 py-10 lg:grid-cols-[1.08fr_0.92fr] lg:px-8">
            <section class="rounded-[36px] border border-white/10 bg-white/5 p-8 shadow-2xl shadow-slate-950/30 backdrop-blur-xl lg:p-12">
                <div class="inline-flex items-center gap-3 rounded-full border border-amber-300/25 bg-amber-300/10 px-4 py-2 text-xs font-extrabold uppercase tracking-[0.24em] text-amber-200">
                    <span class="h-2.5 w-2.5 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.9)]"></span>
                    {{ workspace_badge }}
                </div>
                <p class="mt-5 text-sm font-semibold uppercase tracking-[0.24em] text-sky-200/80">{{ company_name }}</p>
                <h1 class="font-display mt-4 max-w-3xl text-5xl leading-[0.96] text-white md:text-7xl">{{ workspace_title|replace('\n', '<br>')|safe }}</h1>
                <p class="mt-6 max-w-2xl text-base leading-8 text-slate-300 md:text-lg">{{ workspace_intro }}</p>
                <div class="mt-10 grid gap-4 sm:grid-cols-3">
                    <div class="rounded-3xl border border-white/10 bg-black/15 p-5">
                        <div class="text-xs font-extrabold uppercase tracking-[0.2em] text-slate-400">运营</div>
                        <div class="mt-3 text-lg font-semibold text-white">新闻、福利、论坛内容</div>
                    </div>
                    <div class="rounded-3xl border border-white/10 bg-black/15 p-5">
                        <div class="text-xs font-extrabold uppercase tracking-[0.2em] text-slate-400">开发</div>
                        <div class="mt-3 text-lg font-semibold text-white">项目、版本、产品资料</div>
                    </div>
                    <div class="rounded-3xl border border-white/10 bg-black/15 p-5">
                        <div class="text-xs font-extrabold uppercase tracking-[0.2em] text-slate-400">运维</div>
                        <div class="mt-3 text-lg font-semibold text-white">构建、分发、监控与日志</div>
                    </div>
                </div>
            </section>
            <section class="rounded-[32px] border border-white/10 bg-white p-8 text-slate-900 shadow-2xl shadow-black/30 lg:p-10">
                <div class="flex items-center justify-between gap-4">
                    <div>
                        <p class="text-xs font-extrabold uppercase tracking-[0.22em] text-violet-600">Sign in</p>
                        <h2 class="mt-2 text-3xl font-bold">登录工作台</h2>
                        <p class="mt-2 text-sm font-medium text-slate-500">{{ company_name }}</p>
                    </div>
                    <a href="/" class="text-sm font-semibold text-slate-500 hover:text-slate-900">返回官网</a>
                </div>
                <p class="mt-3 text-sm leading-7 text-slate-500">使用内部账号进入工作台。登录后会根据你的权限展示对应模块。</p>
                <div class="mt-6 space-y-3">
                    {% if error_msg %}{{ error_msg|safe }}{% endif %}
                    {% if locked_msg %}{{ locked_msg|safe }}{% endif %}
                </div>
                <form method="POST" class="mt-6 space-y-5">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token_value }}">
                    <div>
                        <label class="mb-2 block text-sm font-semibold text-slate-700">用户名</label>
                        <input type="text" name="username" class="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 outline-none transition focus:border-violet-500 focus:ring-4 focus:ring-violet-100" required>
                    </div>
                    <div>
                        <label class="mb-2 block text-sm font-semibold text-slate-700">密码</label>
                        <input type="password" name="password" class="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 outline-none transition focus:border-violet-500 focus:ring-4 focus:ring-violet-100" required>
                    </div>
                    <button type="submit" class="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-slate-900 px-5 py-3.5 text-sm font-bold text-white transition hover:-translate-y-0.5 hover:bg-slate-800">
                        <i class="fas fa-right-to-bracket"></i> 进入工作台
                    </button>
                </form>
            </section>
        </div>
    </div>
</body>
</html>
"""


PROFILE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ company_name }} - 个人中心</title>
    <link rel="stylesheet" href="/static/tailwind.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body class="min-h-screen bg-slate-50">
    <div class="container mx-auto max-w-lg px-4 py-8">
        <div class="mb-6 flex items-center justify-between">
            <div>
                <p class="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Profile</p>
                <h1 class="mt-2 text-3xl font-bold text-slate-900">个人中心</h1>
                <p class="mt-2 text-sm text-slate-500">{{ company_name }}</p>
            </div>
            <a href="/" class="text-indigo-600 hover:underline">返回首页</a>
        </div>
        <div class="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <meta name="csrf-token" content="{{ csrf_token_value }}">
            <p class="mb-4 text-sm text-slate-500">当前登录用户：<strong class="text-slate-900">{{ username }}</strong></p>
            <h2 class="mb-3 text-lg font-semibold text-slate-900">修改密码</h2>
            <form id="pwdForm" class="space-y-4">
                <div>
                    <label class="mb-1 block text-sm font-medium text-slate-700">当前密码</label>
                    <input type="password" name="current" id="pwdCurrent" class="w-full rounded-xl border border-slate-200 px-3 py-2" required>
                </div>
                <div>
                    <label class="mb-1 block text-sm font-medium text-slate-700">新密码</label>
                    <input type="password" name="new" id="pwdNew" class="w-full rounded-xl border border-slate-200 px-3 py-2" required>
                </div>
                <div>
                    <label class="mb-1 block text-sm font-medium text-slate-700">确认新密码</label>
                    <input type="password" name="confirm" id="pwdConfirm" class="w-full rounded-xl border border-slate-200 px-3 py-2" required>
                </div>
                <p id="pwdMsg" class="hidden text-sm"></p>
                <button type="submit" class="w-full rounded-xl bg-indigo-600 py-2.5 font-medium text-white hover:bg-indigo-700">保存新密码</button>
            </form>
        </div>
    </div>
    <script>
    document.getElementById('pwdForm').onsubmit = function(e) {
        e.preventDefault();
        var newPwd = document.getElementById('pwdNew').value;
        var confirmPwd = document.getElementById('pwdConfirm').value;
        var msg = document.getElementById('pwdMsg');
        msg.classList.add('hidden');
        if (newPwd !== confirmPwd) {
            msg.textContent = '两次输入的新密码不一致';
            msg.classList.remove('hidden', 'text-green-600');
            msg.classList.add('text-red-600');
            return;
        }
        var t = document.querySelector('meta[name=csrf-token]');
        var h = { 'Content-Type': 'application/json' };
        if (t && t.content) h['X-CSRFToken'] = t.content;
        fetch('/profile/change-password', {
            method: 'POST',
            headers: h,
            body: JSON.stringify({
                current: document.getElementById('pwdCurrent').value,
                new_password: newPwd
            }),
            credentials: 'same-origin'
        }).then(function(r) { return r.json(); }).then(function(d) {
            msg.classList.remove('hidden');
            if (d.error) {
                msg.textContent = d.error;
                msg.className = 'text-sm text-red-600';
            } else {
                msg.textContent = '密码已修改，请使用新密码重新登录';
                msg.className = 'text-sm text-green-600';
            }
        }).catch(function() {
            msg.textContent = '请求失败';
            msg.classList.remove('hidden');
            msg.className = 'text-sm text-red-600';
        });
    };
    </script>
</body>
</html>
"""


def _expand_brand_text(text, company_name):
    value = str(text or "").strip()
    if not value:
        return ""
    replacements = {
        "{company_name}": company_name,
        "{{ company_name }}": company_name,
        "{site_name}": company_name,
        "{{ site_name }}": company_name,
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    for legacy_name in ("星云游戏站", "Nebula Game Studio"):
        if legacy_name and legacy_name != company_name:
            value = value.replace(legacy_name, company_name)
    return value.strip()


def _default_workspace_intro(company_name):
    return (
        f"这里是{company_name}的内部入口。登录后按角色进入运营、开发、运维与配置分区，"
        "不再把后台能力暴露在玩家官网页面里。"
    )


def _login_page(error_msg="", locked_msg=""):
    dev_portal = get_dev_portal_content()
    company = get_company_profile()
    company_name = (company.get("company_name") or dev_portal.get("site_name") or "星云游戏站").strip()

    workspace_badge = _expand_brand_text(dev_portal.get("workspace_badge") or "Studio Workspace", company_name)
    workspace_title = _expand_brand_text(
        dev_portal.get("workspace_title") or "为项目、运营与发布准备的统一工作台。",
        company_name,
    )
    configured_intro = _expand_brand_text(dev_portal.get("workspace_intro") or "", company_name)
    workspace_intro = configured_intro or _default_workspace_intro(company_name)

    return render_template_string(
        LOGIN_TEMPLATE,
        error_msg=error_msg or "",
        locked_msg=locked_msg or "",
        csrf_token_value=_get_csrf_token(),
        company_name=company_name,
        workspace_badge=workspace_badge,
        workspace_title=workspace_title,
        workspace_intro=workspace_intro,
    )


@bp.route("/login", methods=["GET", "POST"])
def login():
    from services.rate_limit import rate_limit_login

    client_ip = request.remote_addr or "127.0.0.1"
    allowed_rl, retry_after = rate_limit_login()
    if not allowed_rl:
        response = make_response(
            _login_page(
                error_msg="",
                locked_msg='<div class="mb-4 rounded bg-yellow-100 p-3 text-yellow-700">请求过于频繁，请稍后再试</div>',
            ),
            429,
        )
        response.headers["Retry-After"] = str(retry_after)
        return response

    if request.method == "POST":
        allowed, _ = check_login_attempts(client_ip)
        if not allowed:
            remaining = int((login_attempts[client_ip]["locked_until"] - datetime.now().timestamp()) / 60) + 1
            locked_msg = f'<div class="mb-4 rounded bg-yellow-100 p-3 text-yellow-700">登录次数过多，请 {remaining} 分钟后再试</div>'
            return _login_page(error_msg="", locked_msg=locked_msg)

        username = request.form.get("username")
        password = request.form.get("password")
        if username in users_db:
            user = users_db[username]
            if user.get("disabled"):
                error_msg = '<div class="mb-4 rounded bg-red-100 p-3 text-red-700">账号已被禁用</div>'
                return _login_page(error_msg=error_msg, locked_msg="")
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            if user["password"] == password_hash:
                session["user"] = username
                users_db[username]["last_login"] = datetime.now().isoformat()
                save_users()
                record_login_attempt(client_ip, True)
                logger.info("用户 %s 登录成功 (IP: %s)", username, client_ip)
                return redirect("/")

        record_login_attempt(client_ip, False)
        logger.warning("登录失败：%s (IP: %s)", username, client_ip)
        error_msg = '<div class="mb-4 rounded bg-red-100 p-3 text-red-700">用户名或密码错误</div>'
        return _login_page(error_msg=error_msg, locked_msg="")

    allowed, _ = check_login_attempts(client_ip)
    locked_msg = ""
    if not allowed:
        lockout_time = int((login_attempts[client_ip]["locked_until"] - datetime.now().timestamp()) / 60) + 1
        locked_msg = f'<div class="mb-4 rounded bg-yellow-100 p-3 text-yellow-700">登录次数过多，请 {lockout_time} 分钟后再试</div>'
    return _login_page(error_msg="", locked_msg=locked_msg)


@bp.route("/logout")
def logout():
    session.pop("user", None)
    from services.portal import current_portal_mode

    if current_portal_mode() == "admin":
        return redirect("/login")
    return redirect("/")


@bp.route("/profile")
@login_required
def profile_page():
    username = session.get("user") or ""
    company_name = (get_company_profile().get("company_name") or "星云游戏站").strip()
    return render_template_string(
        PROFILE_TEMPLATE,
        username=username,
        csrf_token_value=_get_csrf_token(),
        company_name=company_name,
    )


@bp.route("/profile/change-password", methods=["POST"])
@login_required
def profile_change_password():
    username = session.get("user")
    if not username or username not in users_db:
        return jsonify({"error": "未登录或用户不存在"}), 401
    data = request.get_json(silent=True) or {}
    current = (data.get("current") or "").strip()
    new_password = (data.get("new_password") or "").strip()
    if not current or not new_password:
        return jsonify({"error": "当前密码和新密码不能为空"})
    current_hash = hashlib.sha256(current.encode()).hexdigest()
    if users_db[username]["password"] != current_hash:
        return jsonify({"error": "当前密码错误"})
    users_db[username]["password"] = hashlib.sha256(new_password.encode()).hexdigest()
    save_users()
    log_audit("change_password", username)
    return jsonify({"success": True})
